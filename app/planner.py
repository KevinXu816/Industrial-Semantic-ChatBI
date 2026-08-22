"""Governed semantic query planner.

The planner never asks the LLM to emit SQL.  It derives required entities from the
metric dependency graph, derives connectivity from the ontology, and only then
compiles physical SQL from approved mappings.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .join_path import JoinPathFinder
from .metric_graph import MetricDependencyGraph
from .models import QueryPlan, SemanticIntent
from .semantic import SemanticRegistry


class QueryPlanner:
    def __init__(self, registry: SemanticRegistry):
        self.registry = registry

    def _table(self, entity: str) -> str:
        return self.registry.table_ref(entity)

    def _col(self, entity: str, prop: str) -> str:
        return self.registry.column(entity, prop)

    @staticmethod
    def _literal(value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def _machine_id_subquery(self, business_ref: str) -> str:
        """Resolve a business machine code/name to the canonical identifier."""
        entity = "Machine"
        cfg = self.registry.ontology.get("entities", {}).get(entity, {})
        props = cfg.get("properties", {})
        if "machine_id" not in props:
            raise ValueError("Machine entity must expose logical property 'machine_id'")
        candidates = [p for p in ("machine_code", "machine_name", "machine_id") if p in props]
        if not candidates:
            raise ValueError("Machine entity has no business identifier properties")
        clauses = [f"{self._col(entity, p)} = {self._literal(business_ref)}" for p in candidates]
        return (
            f"SELECT {self._col(entity, 'machine_id')} FROM {self._table(entity)} "
            f"WHERE {' OR '.join(clauses)} LIMIT 1"
        )

    def _machine_evidence_sql(self, business_ref: str) -> str:
        cfg = self.registry.ontology["entities"]["Machine"]
        props = cfg.get("properties", {})
        selected = [p for p in ("machine_id", "machine_code", "machine_name", "machine_type") if p in props]
        select_sql = ", ".join(f"{self._col('Machine', p)} AS {p}" for p in selected)
        predicates = [p for p in ("machine_code", "machine_name", "machine_id") if p in props]
        where_sql = " OR ".join(
            f"{self._col('Machine', p)} = {self._literal(business_ref)}" for p in predicates
        )
        return f"SELECT {select_sql} FROM {self._table('Machine')} WHERE {where_sql} LIMIT 10"

    def _compile_leaf_expression(self, metric_cfg: dict, entity: str, alias: str = "t") -> str:
        expression = str(metric_cfg.get("expression") or "").strip()
        if not expression:
            raise ValueError("Base metric expression is empty")
        props = self.registry.ontology["entities"][entity].get("properties", {})
        # Replace logical properties with approved physical columns, longest first.
        for prop in sorted(props.keys(), key=len, reverse=True):
            physical = self._col(entity, prop)
            expression = re.sub(rf"\b{re.escape(prop)}\b", f"{alias}.{physical}", expression)
        return expression

    def _metric_cte(self, metric_name: str, metric_cfg: dict, machine_id_sql: str, days: int) -> str:
        entity = metric_cfg.get("entity")
        if not entity:
            raise ValueError(f"Leaf metric {metric_name} must declare an entity")
        entity_cfg = self.registry.ontology.get("entities", {}).get(entity)
        if not entity_cfg:
            raise ValueError(f"Metric {metric_name} references unknown entity {entity}")
        props = entity_cfg.get("properties", {})
        if "machine_id" not in props:
            raise ValueError(f"Metric entity {entity} must expose machine_id for equipment-scoped analysis")

        expression = self._compile_leaf_expression(metric_cfg, entity)
        filters = [f"t.{self._col(entity, 'machine_id')} = ({machine_id_sql})"]
        time_field = metric_cfg.get("time_field")
        if time_field:
            if time_field not in props:
                raise ValueError(f"Metric {metric_name} time_field {time_field} is not a property of {entity}")
            filters.append(f"t.{self._col(entity, time_field)} >= NOW() - INTERVAL {days} DAY")
        return (
            f"m_{metric_name} AS (\n"
            f"  SELECT {expression} AS value\n"
            f"  FROM {self._table(entity)} t\n"
            f"  WHERE {' AND '.join(filters)}\n"
            f")"
        )

    def _metric_sql(self, metric_name: str, machine_id_sql: str, days: int) -> Tuple[str, List[str], List[str]]:
        graph = MetricDependencyGraph(self.registry.metrics)
        ordered = graph.ordered(metric_name)
        leaves = graph.leaves(metric_name)
        ctes = [self._metric_cte(name, graph.get(name), machine_id_sql, days) for name in leaves]

        aliases: Dict[str, str] = {name: f"m_{name}.value" for name in leaves}
        from_parts = [f"m_{name}" for name in leaves]
        # Derived metrics are compiled recursively as scalar expressions over leaf CTE values.
        for name in ordered:
            deps = graph.dependencies(name)
            if not deps:
                continue
            dep_aliases = {dep: aliases[dep] for dep in deps}
            aliases[name] = f"({graph.derived_expression(name, dep_aliases)})"

        if not leaves:
            raise ValueError(f"Metric {metric_name} has no executable leaf metrics")
        select_expr = aliases[metric_name]
        unit = graph.get(metric_name).get("unit", "")
        sql = (
            "WITH\n" + ",\n".join(ctes) + "\n"
            f"SELECT {select_expr} AS metric_value, {self._literal(unit)} AS metric_unit\n"
            f"FROM {', '.join(from_parts)}"
        )
        return sql, ordered, graph.entities(metric_name)

    def _diagnostic_sql(self, entity: str, machine_id_sql: str, days: int) -> str | None:
        cfg = self.registry.ontology.get("entities", {}).get(entity, {})
        props = cfg.get("properties", {})
        if not cfg or "machine_id" not in props:
            return None
        time_candidates = [p for p, pcfg in props.items() if pcfg.get("type") == "datetime"]
        time_field = time_candidates[0] if time_candidates else None
        preferred = [
            "alarm_name", "severity", "event_time", "created_at",
            "fault_description", "action", "machine_id"
        ]
        selected = [p for p in preferred if p in props]
        if not selected:
            selected = list(props.keys())[:6]
        select_sql = ", ".join(f"t.{self._col(entity, p)} AS {p}" for p in selected)
        filters = [f"t.{self._col(entity, 'machine_id')} = ({machine_id_sql})"]
        if time_field:
            lookback = max(days * 4, 30) if entity.lower().endswith("workorder") or entity == "WorkOrder" else days
            filters.append(f"t.{self._col(entity, time_field)} >= NOW() - INTERVAL {lookback} DAY")
        order = f" ORDER BY t.{self._col(entity, time_field)} DESC" if time_field else ""
        return f"SELECT {select_sql} FROM {self._table(entity)} t WHERE {' AND '.join(filters)}{order} LIMIT 20"

    def build(self, intent: SemanticIntent) -> QueryPlan:
        if not intent.machine_ref:
            raise ValueError("A machine reference is required, e.g. A101")
        if not intent.metric:
            raise ValueError("Unable to resolve a governed metric from the question")

        days = max(1, min(int(intent.time_window_days), 365))
        machine_id_sql = self._machine_id_subquery(intent.machine_ref)
        metric_sql, metric_order, metric_entities = self._metric_sql(intent.metric, machine_id_sql, days)

        # Planner derives the required semantic graph; intent.related_entities is additive, not authoritative.
        required_entities: List[str] = ["Machine"]
        for entity in metric_entities + list(intent.related_entities or []):
            if entity in self.registry.ontology.get("entities", {}) and entity not in required_entities:
                required_entities.append(entity)

        finder = JoinPathFinder(self.registry.ontology)
        join_paths = {}
        for entity in required_entities[1:]:
            path = finder.find_path("Machine", entity)
            if path is None:
                raise ValueError(f"No ontology relationship path from Machine to required entity {entity}")
            join_paths[entity] = path

        sql: List[str] = [self._machine_evidence_sql(intent.machine_ref), metric_sql]
        if intent.analysis_mode == "diagnostic":
            metric_set = set(metric_entities)
            for entity in required_entities:
                if entity == "Machine" or entity in metric_set:
                    continue
                evidence_sql = self._diagnostic_sql(entity, machine_id_sql, days)
                if evidence_sql:
                    sql.append(evidence_sql)

        return QueryPlan(
            intent=intent,
            sql=sql,
            notes=[
                "Metric dependencies are expanded from the governed Metric Registry.",
                "Required entities and JOIN paths are derived from the approved ontology.",
                "Physical table/column names are compiled only from semantic mappings.",
                "The LLM may resolve semantic intent but never emits executable SQL.",
            ],
            metric_dependencies=metric_order,
            required_entities=required_entities,
            join_paths=join_paths,
        )
