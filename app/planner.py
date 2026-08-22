"""V0.5 governed generic semantic query planner.

The LLM resolves semantic intent only. SQL is compiled deterministically from
approved metrics, ontology relationships and physical mappings.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .join_path import JoinPathFinder
from .metric_graph import MetricDependencyGraph
from .models import QueryPlan, SemanticIntent, SemanticSubject, SemanticFilter
from .semantic import SemanticRegistry


class QueryPlanner:
    def __init__(self, registry: SemanticRegistry):
        self.registry = registry

    def _table(self, entity: str) -> str:
        return self.registry.table_ref(entity)

    def _col(self, entity: str, prop: str) -> str:
        return self.registry.column(entity, prop)

    @staticmethod
    def _literal(value) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "''") + "'"

    def _entity_cfg(self, entity: str) -> dict:
        cfg = self.registry.ontology.get("entities", {}).get(entity)
        if not cfg:
            raise ValueError(f"Unknown semantic entity: {entity}")
        return cfg

    def _identifier_properties(self, entity: str, explicit_key: str | None = None) -> List[str]:
        cfg = self._entity_cfg(entity)
        props = cfg.get("properties", {})
        if explicit_key:
            if explicit_key not in props:
                raise ValueError(f"Subject key {explicit_key} is not a property of {entity}")
            return [explicit_key]
        declared = [p for p in cfg.get("identifiers", []) if p in props]
        # Prefer human-readable identifiers, then canonical ids.
        readable = [p for p in declared if any(k in p.lower() for k in ("code", "name", "no", "number"))]
        return list(dict.fromkeys(readable + declared))

    def _subject_predicate(self, subject: SemanticSubject, alias: str = "s0") -> str:
        if subject.reference is None:
            return "1=1"
        candidates = self._identifier_properties(subject.entity, subject.key)
        if not candidates:
            raise ValueError(f"Entity {subject.entity} has no governed identifiers")
        return " OR ".join(
            f"{alias}.{self._col(subject.entity, prop)} = {self._literal(subject.reference)}"
            for prop in candidates
        )

    def _subject_evidence_sql(self, subject: SemanticSubject) -> str:
        cfg = self._entity_cfg(subject.entity)
        props = cfg.get("properties", {})
        selected = self._identifier_properties(subject.entity, subject.key)
        for p in props:
            if p not in selected and len(selected) < 6:
                selected.append(p)
        select_sql = ", ".join(f"s0.{self._col(subject.entity, p)} AS {p}" for p in selected)
        return (
            f"SELECT {select_sql} FROM {self._table(subject.entity)} s0 "
            f"WHERE ({self._subject_predicate(subject, 's0')}) LIMIT 10"
        )

    def _compile_leaf_expression(self, metric_cfg: dict, entity: str, alias: str = "t") -> str:
        expression = str(metric_cfg.get("expression") or "").strip()
        if not expression:
            raise ValueError("Base metric expression is empty")
        props = self._entity_cfg(entity).get("properties", {})
        for prop in sorted(props.keys(), key=len, reverse=True):
            expression = re.sub(
                rf"{re.escape(prop)}",
                f"{alias}.{self._col(entity, prop)}",
                expression,
            )
        return expression

    def _relationship_condition(self, left_entity: str, left_alias: str, right_entity: str, right_alias: str, on) -> str:
        if isinstance(on, dict):
            left_prop = on.get("from") or on.get("left")
            right_prop = on.get("to") or on.get("right")
        else:
            left_prop = right_prop = str(on)
        if not left_prop or not right_prop:
            raise ValueError(f"Relationship {left_entity}->{right_entity} has no join key")
        return (
            f"{left_alias}.{self._col(left_entity, left_prop)} = "
            f"{right_alias}.{self._col(right_entity, right_prop)}"
        )

    def _subject_scope_exists(self, target_entity: str, subject: SemanticSubject, path: List[dict]) -> str:
        if target_entity == subject.entity:
            return f"({self._subject_predicate(subject, 't')})"
        if not path:
            raise ValueError(f"No ontology path from {subject.entity} to {target_entity}")

        from_sql = f"{self._table(subject.entity)} s0"
        joins: List[str] = []
        previous_alias = "s0"
        previous_entity = subject.entity
        for idx, step in enumerate(path):
            next_entity = step["to"]
            is_target = next_entity == target_entity and idx == len(path) - 1
            if is_target:
                condition = self._relationship_condition(previous_entity, previous_alias, next_entity, "t", step.get("on"))
                return (
                    "EXISTS (SELECT 1 FROM " + from_sql +
                    (" " + " ".join(joins) if joins else "") +
                    f" WHERE ({self._subject_predicate(subject, 's0')}) AND {condition})"
                )
            next_alias = f"s{idx + 1}"
            condition = self._relationship_condition(previous_entity, previous_alias, next_entity, next_alias, step.get("on"))
            joins.append(f"JOIN {self._table(next_entity)} {next_alias} ON {condition}")
            previous_alias, previous_entity = next_alias, next_entity
        raise ValueError(f"Invalid ontology path from {subject.entity} to {target_entity}")

    def _filter_sql(self, f: SemanticFilter, default_entity: str, alias: str = "t") -> str | None:
        entity = f.entity or default_entity
        if entity != default_entity:
            # Cross-entity filters require a dedicated semantic sub-plan; intentionally reject here
            # instead of silently producing a wrong query.
            return None
        self._entity_cfg(entity)
        col = f"{alias}.{self._col(entity, f.property)}"
        if f.operator == "in":
            vals = f.value if isinstance(f.value, list) else [f.value]
            return f"{col} IN ({', '.join(self._literal(v) for v in vals)})"
        if f.operator == "contains":
            return f"{col} LIKE {self._literal('%' + str(f.value) + '%')}"
        return f"{col} {f.operator} {self._literal(f.value)}"

    def _metric_cte(self, metric_name: str, metric_cfg: dict, subject: SemanticSubject,
                    finder: JoinPathFinder, days: int, filters: List[SemanticFilter]) -> str:
        entity = metric_cfg.get("entity")
        if not entity:
            raise ValueError(f"Leaf metric {metric_name} must declare an entity")
        self._entity_cfg(entity)
        expression = self._compile_leaf_expression(metric_cfg, entity)
        path = finder.find_path(subject.entity, entity)
        if path is None and subject.entity != entity:
            raise ValueError(f"No ontology relationship path from {subject.entity} to metric entity {entity}")
        predicates = [self._subject_scope_exists(entity, subject, path or [])]
        time_field = metric_cfg.get("time_field")
        props = self._entity_cfg(entity).get("properties", {})
        if time_field:
            if time_field not in props:
                raise ValueError(f"Metric {metric_name} time_field {time_field} is not a property of {entity}")
            predicates.append(f"t.{self._col(entity, time_field)} >= NOW() - INTERVAL {days} DAY")
        for f in filters:
            compiled = self._filter_sql(f, entity)
            if compiled:
                predicates.append(compiled)
        return (
            f"m_{metric_name} AS (\n"
            f"  SELECT {expression} AS value\n"
            f"  FROM {self._table(entity)} t\n"
            f"  WHERE {' AND '.join(predicates)}\n"
            f")"
        )

    def _metric_sql(self, metric_name: str, subject: SemanticSubject, finder: JoinPathFinder,
                    days: int, filters: List[SemanticFilter]) -> Tuple[str, List[str], List[str]]:
        graph = MetricDependencyGraph(self.registry.metrics)
        ordered = graph.ordered(metric_name)
        leaves = graph.leaves(metric_name)
        ctes = [self._metric_cte(name, graph.get(name), subject, finder, days, filters) for name in leaves]
        aliases: Dict[str, str] = {name: f"m_{name}.value" for name in leaves}
        for name in ordered:
            deps = graph.dependencies(name)
            if deps:
                aliases[name] = f"({graph.derived_expression(name, {d: aliases[d] for d in deps})})"
        if not leaves:
            raise ValueError(f"Metric {metric_name} has no executable leaf metrics")
        unit = graph.get(metric_name).get("unit", "")
        sql = (
            "WITH\n" + ",\n".join(ctes) + "\n"
            f"SELECT {aliases[metric_name]} AS metric_value, {self._literal(unit)} AS metric_unit\n"
            f"FROM {', '.join('m_' + name for name in leaves)}"
        )
        return sql, ordered, graph.entities(metric_name)

    def _diagnostic_sql(self, entity: str, subject: SemanticSubject, path: List[dict], days: int) -> str | None:
        cfg = self._entity_cfg(entity)
        props = cfg.get("properties", {})
        time_candidates = [p for p, pcfg in props.items() if pcfg.get("type") == "datetime"]
        time_field = time_candidates[0] if time_candidates else None
        preferred = ["alarm_name", "severity", "event_time", "created_at", "fault_description", "action"]
        selected = [p for p in preferred if p in props] or list(props.keys())[:6]
        if not selected:
            return None
        select_sql = ", ".join(f"t.{self._col(entity, p)} AS {p}" for p in selected)
        predicates = [self._subject_scope_exists(entity, subject, path)]
        if time_field:
            lookback = max(days * 4, 30) if "workorder" in entity.lower() else days
            predicates.append(f"t.{self._col(entity, time_field)} >= NOW() - INTERVAL {lookback} DAY")
        order = f" ORDER BY t.{self._col(entity, time_field)} DESC" if time_field else ""
        return f"SELECT {select_sql} FROM {self._table(entity)} t WHERE {' AND '.join(predicates)}{order} LIMIT 20"

    def build(self, intent: SemanticIntent) -> QueryPlan:
        subject = intent.subject or SemanticSubject(entity="Machine", reference=intent.machine_ref)
        if subject.entity not in self.registry.ontology.get("entities", {}):
            raise ValueError(f"Unknown subject entity: {subject.entity}")
        metric_names = list(intent.metrics or ([] if not intent.metric else [intent.metric]))
        if not metric_names:
            raise ValueError("Unable to resolve a governed metric from the question")
        if len(metric_names) > 1:
            raise ValueError("V0.5 planner currently executes one primary metric per plan")
        metric_name = metric_names[0]
        days = intent.time_range.normalized_days() if intent.time_range else max(1, min(intent.time_window_days, 365))

        finder = JoinPathFinder(self.registry.ontology)
        metric_sql, metric_order, metric_entities = self._metric_sql(
            metric_name, subject, finder, days, list(intent.filters or [])
        )
        required_entities: List[str] = [subject.entity]
        for entity in metric_entities + list(intent.related_entities or []):
            if entity in self.registry.ontology.get("entities", {}) and entity not in required_entities:
                required_entities.append(entity)

        join_paths: Dict[str, List[dict]] = {}
        for entity in required_entities:
            if entity == subject.entity:
                continue
            path = finder.find_path(subject.entity, entity)
            if path is None:
                raise ValueError(f"No ontology relationship path from {subject.entity} to required entity {entity}")
            join_paths[entity] = path

        sql: List[str] = [self._subject_evidence_sql(subject), metric_sql]
        if intent.analysis_mode == "diagnostic":
            metric_set = set(metric_entities)
            for entity in required_entities:
                if entity == subject.entity or entity in metric_set:
                    continue
                evidence_sql = self._diagnostic_sql(entity, subject, join_paths[entity], days)
                if evidence_sql:
                    sql.append(evidence_sql)

        logical_plan = {
            "subject": subject.model_dump(),
            "metrics": metric_names,
            "dimensions": list(intent.dimensions or []),
            "filters": [f.model_dump() for f in intent.filters or []],
            "time_range": intent.time_range.model_dump() if intent.time_range else None,
            "time_grain": intent.time_grain,
            "comparison": intent.comparison.model_dump(),
            "metric_dependencies": metric_order,
            "required_entities": required_entities,
        }
        return QueryPlan(
            intent=intent,
            sql=sql,
            notes=[
                "V0.5 uses a generic subject entity instead of a hard-coded Machine anchor.",
                "Metric dependencies are expanded from the governed Metric Registry.",
                "Entity connectivity is validated from the approved ontology before SQL compilation.",
                "Physical table/column names come only from governed semantic mappings.",
                "Cross-entity filters are rejected until a dedicated semantic sub-plan is available; the planner never guesses.",
                "The LLM may resolve semantic intent but never emits executable SQL.",
            ],
            metric_dependencies=metric_order,
            required_entities=required_entities,
            join_paths=join_paths,
            subject_entity=subject.entity,
            logical_plan=logical_plan,
        )
