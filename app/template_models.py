"""Validated data models for industry templates."""

import re
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_PROPERTY_TYPES = {
    "string",
    "number",
    "integer",
    "boolean",
    "date",
    "datetime",
}
TEMPLATE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _required_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name}不能为空")
    return value


def _validate_mapping_names(value: dict, field_name: str) -> dict:
    for name in value:
        if not name.strip():
            raise ValueError(f"{field_name}名称不能为空")
    return value


class PropertyDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in ALLOWED_PROPERTY_TYPES:
            allowed = "、".join(sorted(ALLOWED_PROPERTY_TYPES))
            raise ValueError(f"属性类型必须是：{allowed}")
        return value


class PhysicalMapping(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    catalog: Optional[str] = None
    schema_name: Optional[str] = Field(default=None, alias="schema")
    table: Optional[str] = None
    columns: Dict[str, str] = Field(default_factory=dict)


class TemplateEntity(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str = ""
    properties: Dict[str, PropertyDefinition]
    physical_mapping: Optional[PhysicalMapping] = None

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("properties")
    @classmethod
    def validate_property_names(
        cls, value: Dict[str, PropertyDefinition]
    ) -> Dict[str, PropertyDefinition]:
        return _validate_mapping_names(value, "属性")


class TemplateRelationship(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    from_entity: str = Field(alias="from")
    relation: str
    to_entity: str = Field(alias="to")
    on: str

    @field_validator("from_entity", "relation", "to_entity", "on")
    @classmethod
    def validate_required_fields(cls, value: str, info) -> str:
        labels = {
            "from_entity": "关系起点",
            "relation": "关系名称",
            "to_entity": "关系终点",
            "on": "关联字段",
        }
        return _required_text(value, labels[info.field_name])


class TemplateMetric(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str = ""
    expression: str
    unit: Optional[str] = None
    synonyms: List[str] = Field(default_factory=list)
    entity: Optional[str] = None
    time_field: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("expression")
    @classmethod
    def validate_expression(cls, value: str) -> str:
        return _required_text(value, "指标表达式")

    @field_validator("unit", "entity", "time_field")
    @classmethod
    def trim_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("synonyms", "dependencies")
    @classmethod
    def trim_string_list(cls, value: List[str]) -> List[str]:
        return [item.strip() for item in value if item.strip()]


class IndustryTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    entities: Dict[str, TemplateEntity]
    relationships: List[TemplateRelationship] = Field(default_factory=list)
    metrics: Dict[str, TemplateMetric] = Field(default_factory=dict)
    aliases: Dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        value = value.strip()
        if not TEMPLATE_ID_PATTERN.fullmatch(value):
            raise ValueError("模板 ID 只能包含小写字母、数字和连字符")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _required_text(value, "模板名称")

    @field_validator("description")
    @classmethod
    def trim_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("entities")
    @classmethod
    def validate_entities(
        cls, value: Dict[str, TemplateEntity]
    ) -> Dict[str, TemplateEntity]:
        if not value:
            raise ValueError("模板至少需要一个实体")
        return _validate_mapping_names(value, "实体")

    @field_validator("metrics")
    @classmethod
    def validate_metric_names(
        cls, value: Dict[str, TemplateMetric]
    ) -> Dict[str, TemplateMetric]:
        return _validate_mapping_names(value, "指标")

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, value: Dict[str, str]) -> Dict[str, str]:
        normalized = {}
        for alias, field_name in value.items():
            alias = alias.strip()
            field_name = field_name.strip()
            if not alias or not field_name:
                raise ValueError("别名和值不能为空")
            if alias in normalized:
                raise ValueError(f"别名重复：{alias}")
            normalized[alias] = field_name
        return normalized


class TemplateUploadRequest(BaseModel):
    filename: str
    content: str

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        return _required_text(value, "文件名")
