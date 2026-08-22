"""Persistent user overrides and custom industry templates."""

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from .template_models import IndustryTemplate
from .templates import TEMPLATES


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_FILE = ROOT / "data" / "industry_templates.json"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


class TemplateStoreError(Exception):
    """Base error for template storage and validation."""


class TemplateNotFoundError(TemplateStoreError):
    """Raised when a template does not exist."""


class TemplateConflictError(TemplateStoreError):
    """Raised when a template ID already exists."""


class TemplateOperationError(TemplateStoreError):
    """Raised when an operation is not valid for the template origin."""


class TemplateValidationError(TemplateStoreError):
    """Raised with field-level validation errors."""

    def __init__(self, message: str, errors: Optional[list[dict]] = None):
        super().__init__(message)
        self.errors = errors or []


class TemplateStore:
    def __init__(
        self,
        path: Path = DEFAULT_TEMPLATE_FILE,
        builtins: Optional[dict] = None,
    ):
        self.path = Path(path)
        self.builtins = copy.deepcopy(TEMPLATES if builtins is None else builtins)
        self._lock = threading.RLock()

    @staticmethod
    def _empty_data() -> dict:
        return {"version": 1, "overrides": {}, "custom": {}}

    def _load_data(self) -> dict:
        if not self.path.exists():
            return self._empty_data()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TemplateStoreError(f"行业模板存储文件读取失败：{exc}") from exc
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("overrides"), dict)
            or not isinstance(data.get("custom"), dict)
        ):
            raise TemplateStoreError("行业模板存储文件结构无效")
        return {
            "version": 1,
            "overrides": data["overrides"],
            "custom": data["custom"],
        }

    def _save_data(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
            temporary_name = None
        except OSError as exc:
            raise TemplateStoreError(f"行业模板存储文件写入失败：{exc}") from exc
        finally:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)

    @staticmethod
    def _serialize_template(template: IndustryTemplate) -> dict:
        return template.model_dump(
            by_alias=True,
            exclude={"id"},
            exclude_none=True,
        )

    @staticmethod
    def _pydantic_errors(exc: ValidationError) -> list[dict]:
        return [
            {
                "path": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
            }
            for item in exc.errors()
        ]

    def _validate(
        self,
        payload: dict,
        expected_id: Optional[str] = None,
    ) -> IndustryTemplate:
        try:
            template = IndustryTemplate.model_validate(payload)
        except ValidationError as exc:
            raise TemplateValidationError(
                "模板校验失败", self._pydantic_errors(exc)
            ) from exc

        errors = []
        if expected_id is not None and template.id != expected_id:
            errors.append({"path": "id", "message": "模板 ID 与请求路径不一致"})
        entity_names = set(template.entities)
        relationship_keys = set()
        for index, relationship in enumerate(template.relationships):
            relationship_key = (
                relationship.from_entity,
                relationship.relation,
                relationship.to_entity,
            )
            if relationship_key in relationship_keys:
                errors.append(
                    {
                        "path": f"relationships.{index}",
                        "message": "同一起点、关系和终点的关系重复",
                    }
                )
            relationship_keys.add(relationship_key)
            if relationship.from_entity not in entity_names:
                errors.append(
                    {
                        "path": f"relationships.{index}.from",
                        "message": "起点实体不存在",
                    }
                )
            if relationship.to_entity not in entity_names:
                errors.append(
                    {
                        "path": f"relationships.{index}.to",
                        "message": "终点实体不存在",
                    }
                )
        if errors:
            raise TemplateValidationError("模板校验失败", errors)
        return template

    @staticmethod
    def _counts(content: dict) -> dict:
        return {
            "entities": len(content.get("entities", {})),
            "relationships": len(content.get("relationships", [])),
            "metrics": len(content.get("metrics", {})),
            "aliases": len(content.get("aliases", {})),
        }

    def _detail(
        self,
        template_id: str,
        content: dict,
        origin: str,
        customized: bool,
    ) -> dict:
        normalized = self._validate({"id": template_id, **copy.deepcopy(content)})
        detail = {
            "id": template_id,
            **self._serialize_template(normalized),
            "origin": origin,
            "customized": customized,
        }
        detail["counts"] = self._counts(detail)
        return detail

    def _get_from_data(self, template_id: str, data: dict) -> dict:
        if template_id in self.builtins:
            customized = template_id in data["overrides"]
            content = data["overrides"].get(template_id, self.builtins[template_id])
            return self._detail(template_id, content, "builtin", customized)
        if template_id in data["custom"]:
            return self._detail(
                template_id,
                data["custom"][template_id],
                "custom",
                False,
            )
        raise TemplateNotFoundError(f"模板不存在：{template_id}")

    @staticmethod
    def _summary(detail: dict) -> dict:
        keys = ("id", "name", "description", "origin", "customized", "counts")
        return {key: copy.deepcopy(detail[key]) for key in keys}

    def list(self) -> list[dict]:
        data = self._load_data()
        template_ids = list(self.builtins)
        template_ids.extend(
            template_id
            for template_id in data["custom"]
            if template_id not in self.builtins
        )
        return [
            self._summary(self._get_from_data(template_id, data))
            for template_id in template_ids
        ]

    def get(self, template_id: str) -> dict:
        return self._get_from_data(template_id, self._load_data())

    def parse_upload(self, filename: str, content: str) -> dict:
        if len(content.encode("utf-8")) > MAX_UPLOAD_BYTES:
            raise TemplateValidationError(
                "模板文件不能超过 2 MiB",
                [{"path": "content", "message": "文件过大"}],
            )
        suffix = Path(filename).suffix.lower()
        try:
            if suffix == ".json":
                payload = json.loads(content)
            elif suffix in {".yaml", ".yml"}:
                payload = yaml.safe_load(content)
            else:
                raise TemplateValidationError(
                    "仅支持 JSON、YAML 或 YML 文件",
                    [{"path": "filename", "message": "文件扩展名不受支持"}],
                )
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise TemplateValidationError(
                "模板文件解析失败",
                [{"path": "content", "message": str(exc)}],
            ) from exc
        if not isinstance(payload, dict):
            raise TemplateValidationError(
                "模板顶层必须是对象",
                [{"path": "content", "message": "顶层结构不是对象"}],
            )
        return self._validate(payload).model_dump(by_alias=True, exclude_none=True)

    def create(self, payload: dict) -> dict:
        template = self._validate(payload)
        with self._lock:
            data = self._load_data()
            if template.id in self.builtins or template.id in data["custom"]:
                raise TemplateConflictError(f"模板 ID 已存在：{template.id}")
            data["custom"][template.id] = self._serialize_template(template)
            self._save_data(data)
            return self._get_from_data(template.id, data)

    def update(self, template_id: str, payload: dict) -> dict:
        template = self._validate(payload, expected_id=template_id)
        with self._lock:
            data = self._load_data()
            if template_id in self.builtins:
                data["overrides"][template_id] = self._serialize_template(template)
            elif template_id in data["custom"]:
                data["custom"][template_id] = self._serialize_template(template)
            else:
                raise TemplateNotFoundError(f"模板不存在：{template_id}")
            self._save_data(data)
            return self._get_from_data(template_id, data)

    def delete(self, template_id: str) -> dict:
        with self._lock:
            data = self._load_data()
            if template_id in self.builtins:
                raise TemplateOperationError("内置模板不能删除")
            if template_id not in data["custom"]:
                raise TemplateNotFoundError(f"模板不存在：{template_id}")
            del data["custom"][template_id]
            self._save_data(data)
        return {"deleted": template_id}

    def reset(self, template_id: str) -> dict:
        with self._lock:
            data = self._load_data()
            if template_id in data["custom"]:
                raise TemplateOperationError("自定义模板没有预置版本")
            if template_id not in self.builtins:
                raise TemplateNotFoundError(f"模板不存在：{template_id}")
            data["overrides"].pop(template_id, None)
            self._save_data(data)
            return self._get_from_data(template_id, data)
