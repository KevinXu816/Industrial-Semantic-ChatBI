"""Field aliases and enum value mappings for semantic resolution."""
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
ALIASES_FILE = ROOT / "data" / "field_aliases.json"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


class FieldAliasStore:
    """Manage field aliases and enum value business meanings.

    Structure:
    {
      "aliases": {
        "设备编号": "machine_code",
        "资产编号": "machine_code",
        "设备ID": "machine_id"
      },
      "enums": {
        "Machine.machine_type": {
          "A": "空压机",
          "B": "风机",
          "C": "水泵"
        }
      }
    }
    """

    def __init__(self):
        self._lock = threading.Lock()
        ALIASES_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _load(self, strict: bool = False) -> dict:
        if not ALIASES_FILE.exists():
            return {"aliases": {}, "enums": {}}
        try:
            data = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            if strict:
                raise RuntimeError(f"字段别名配置读取失败：{exc}") from exc
            return {"aliases": {}, "enums": {}}
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("aliases", {}), dict)
            or not isinstance(data.get("enums", {}), dict)
        ):
            if strict:
                raise RuntimeError("字段别名配置结构无效")
            return {"aliases": {}, "enums": {}}
        return {
            "aliases": data.get("aliases", {}),
            "enums": data.get("enums", {}),
        }

    def _save(self, data: dict):
        _atomic_write_text(
            ALIASES_FILE,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    def get_all(self, strict: bool = False) -> dict:
        return self._load(strict=strict)

    def validate_storage(self) -> None:
        self._load(strict=True)

    def snapshot_state(self) -> bytes | None:
        self.validate_storage()
        return ALIASES_FILE.read_bytes() if ALIASES_FILE.exists() else None

    def restore_state(self, snapshot: bytes | None) -> None:
        if snapshot is None:
            ALIASES_FILE.unlink(missing_ok=True)
        else:
            _atomic_write_text(ALIASES_FILE, snapshot.decode("utf-8"))

    def set_aliases(self, aliases: Dict[str, str]) -> dict:
        with self._lock:
            data = self._load()
            data["aliases"].update(aliases)
            self._save(data)
        return data["aliases"]

    def delete_alias(self, alias: str):
        with self._lock:
            data = self._load()
            data["aliases"].pop(alias, None)
            self._save(data)

    def set_enum(self, entity_field: str, mappings: Dict[str, str]) -> dict:
        with self._lock:
            data = self._load()
            data["enums"][entity_field] = mappings
            self._save(data)
        return data["enums"][entity_field]

    def delete_enum(self, entity_field: str):
        with self._lock:
            data = self._load()
            data["enums"].pop(entity_field, None)
            self._save(data)

    def resolve_alias(self, term: str) -> str:
        """Resolve a Chinese alias to its logical field name."""
        data = self._load()
        return data["aliases"].get(term, term)

    def resolve_enum_value(self, entity_field: str, business_value: str) -> str:
        """Resolve a business value to its DB value. E.g. '空压机' -> 'A'."""
        data = self._load()
        enums = data["enums"].get(entity_field, {})
        for db_val, biz_val in enums.items():
            if biz_val == business_value:
                return db_val
        return business_value
