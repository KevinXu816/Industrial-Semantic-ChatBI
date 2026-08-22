"""Physical planning helpers for V0.6.

The semantic planner produces a logical query plan. This module translates
semantic entities/properties/time grains into Doris-compatible physical SQL
fragments without allowing the LLM to invent physical names.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class PhysicalDimension:
    entity: str
    property: str
    alias: str
    table: str
    column: str


class DorisPhysicalPlanner:
    dialect = "doris"

    def __init__(self, registry):
        self.registry = registry

    def table(self, entity: str) -> str:
        return self.registry.table_ref(entity)

    def column(self, entity: str, prop: str) -> str:
        return self.registry.column(entity, prop)

    def time_bucket(self, expression: str, grain: Optional[str]) -> str:
        if not grain:
            return expression
        grain = grain.lower()
        if grain == "hour":
            return f"DATE_FORMAT({expression}, '%Y-%m-%d %H:00:00')"
        if grain == "day":
            return f"DATE({expression})"
        if grain == "week":
            return f"DATE_TRUNC({expression}, 'week')"
        if grain == "month":
            return f"DATE_TRUNC({expression}, 'month')"
        raise ValueError(f"Unsupported time grain: {grain}")

    def describe(self, entities: List[str], dimensions: List[Dict[str, Any]], comparison: str) -> Dict[str, Any]:
        catalogs = []
        tables = []
        for entity in entities:
            cfg = self.registry.ontology.get("entities", {}).get(entity, {})
            pm = cfg.get("physical_mapping", {})
            catalog = pm.get("catalog")
            if catalog and catalog not in catalogs:
                catalogs.append(catalog)
            if pm:
                tables.append({
                    "entity": entity,
                    "catalog": pm.get("catalog"),
                    "schema": pm.get("schema"),
                    "table": pm.get("table"),
                    "table_ref": self.table(entity),
                })
        return {
            "dialect": self.dialect,
            "federated": len(catalogs) > 1,
            "catalogs": catalogs,
            "tables": tables,
            "dimensions": dimensions,
            "comparison": comparison,
            "execution_engine": "Apache Doris",
        }
