"""V0.6 governed generic semantic analytics planner.

Capabilities:
- multiple governed metrics in one plan
- dimension/group-by planning across ontology paths
- cross-entity semantic filters using governed EXISTS subplans
- previous-period and explicit baseline comparisons
- Doris physical-plan metadata for federated execution

The LLM resolves semantic intent only. It never emits executable SQL.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any

from .join_path import JoinPathFinder
from .metric_graph import MetricDependencyGraph
from .models import QueryPlan, SemanticIntent, SemanticSubject, SemanticFilter
from .physical_planner import DorisPhysicalPlanner
from .semantic import SemanticRegistry


@dataclass
class DimensionSpec:
    raw: str
    entity: str
    property: str
    alias: str


class QueryPlanner:
    def __init__(self, registry: SemanticRegistry):
        self.registry = registry
        self.physical = DorisPhysicalPlanner(registry)

    def _table(self, entity: str) -> str:
        return self.physical.table(entity)

    def _col(self, entity: str, prop: str) -> str:
        return self.physical.column(entity, prop)

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
        readable = [p for p in declared if any(k in p.lower() for k in ("code", "name", "no", "number"))]
        return list(dict.fromkeys(readable + declared))

    def _default_dimension_property(self, entity: str) -> str:
        ids = self._identifier_properties(entity)
        if not ids:
            props = list(self._entity_cfg(entity).get("properties", {}).keys())
            if not props:
                raise ValueError(f"Entity {entity} has no properties for dimension grouping")
            return props[0]
        for p in ids:
            if "name" in p.lower():
                return p
        for p in ids:
            if "code" in p.lower():
                return p
        return ids[0]

    def _parse_dimensions(self, dimensions: List[str]) -> List[DimensionSpec]:
        result: List[DimensionSpec] = []
        used_aliases: set[str] = set()
        for raw in dimensions:
            text = str(raw).strip()
            if not text:
                continue
            if "." in text:
                entity, prop = text.split(".", 1)
            else:
                entity, prop = text, self._default_dimension_property(text)
            cfg = self._entity_cfg(entity)
            if prop not in cfg.get("properties", {}):
                raise ValueError(f"Unknown dimension property: {entity}.{prop}")
            alias = re.sub(r"[^A-Za-z0-9_]", "_", f"{entity}_{prop}").lower()
            base = alias
            idx = 2
            while alias in used_aliases:
                alias = f"{base}_{idx}"; idx += 1
            used_aliases.add(alias)
            result.append(DimensionSpec(raw=text, entity=entity, property=prop, alias=alias))
        return result

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
                rf"\b{re.escape(prop)}\b",
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

    def _path_exists(self, source_entity: str, source_alias: str, target_entity: str,
                     target_predicate_builder, finder: JoinPathFinder, alias_prefix: str) -> str:
        if source_entity == target_entity:
            return target_predicate_builder(source_alias)
        path = finder.find_path(source_entity, target_entity)
        if path is None:
            raise ValueError(f"No ontology relationship path from {source_entity} to {target_entity}")
        from_entity = path[0]["to"]
        first_alias = f"{alias_prefix}0"
        first_cond = self._relationship_condition(source_entity, source_alias, from_entity, first_alias, path[0].get("on"))
        from_sql = f"{self._table(from_entity)} {first_alias}"
        joins: List[str] = []
        prev_entity, prev_alias = from_entity, first_alias
        for idx, step in enumerate(path[1:], start=1):
            nxt = step["to"]
            nxt_alias = f"{alias_prefix}{idx}"
            cond = self._relationship_condition(prev_entity, prev_alias, nxt, nxt_alias, step.get("on"))
            joins.append(f"JOIN {self._table(nxt)} {nxt_alias} ON {cond}")
            prev_entity, prev_alias = nxt, nxt_alias
        return (
            f"EXISTS (SELECT 1 FROM {from_sql} "
            f"{' '.join(joins)} WHERE {first_cond} AND ({target_predicate_builder(prev_alias)}))"
        )

    def _subject_scope_exists(self, target_entity: str, subject: SemanticSubject, finder: JoinPathFinder) -> str:
        return self._path_exists(
            target_entity,
            "t",
            subject.entity,
            lambda alias: self._subject_predicate(subject, alias),
            finder,
            "s",
        )

    def _filter_predicate(self, f: SemanticFilter, entity: str, alias: str) -> str:
        self._entity_cfg(entity)
        if f.property not in self._entity_cfg(entity).get("properties", {}):
            raise ValueError(f"Unknown filter property: {entity}.{f.property}")
        col = f"{alias}.{self._col(entity, f.property)}"
        if f.operator == "in":
            vals = f.value if isinstance(f.value, list) else [f.value]
            return f"{col} IN ({', '.join(self._literal(v) for v in vals)})"
        if f.operator == "contains":
            return f"{col} LIKE {self._literal('%' + str(f.value) + '%')}"
        return f"{col} {f.operator} {self._literal(f.value)}"

    def _semantic_filter_sql(self, f: SemanticFilter, metric_entity: str, finder: JoinPathFinder, index: int) -> str:
        entity = f.entity or metric_entity
        if entity == metric_entity:
            return self._filter_predicate(f, entity, "t")
        return self._path_exists(
            metric_entity,
            "t",
            entity,
            lambda alias: self._filter_predicate(f, entity, alias),
            finder,
            f"flt{index}_",
        )

    def _time_predicate(self, entity: str, time_field: str, alias: str, intent: SemanticIntent,
                        period: str = "current") -> str:
        col = f"{alias}.{self._col(entity, time_field)}"
        tr = intent.time_range
        if tr and tr.type == "absolute" and tr.start and tr.end:
            if period == "current":
                return f"{col} >= {self._literal(tr.start)} AND {col} < {self._literal(tr.end)}"
            if intent.comparison.type == "baseline" and intent.comparison.baseline_start and intent.comparison.baseline_end:
                return f"{col} >= {self._literal(intent.comparison.baseline_start)} AND {col} < {self._literal(intent.comparison.baseline_end)}"
            raise ValueError("Absolute previous-period comparison requires an explicit baseline range in V0.6")
        days = tr.normalized_days() if tr else max(1, min(intent.time_window_days, 365))
        if period == "current":
            return f"{col} >= NOW() - INTERVAL {days} DAY"
        if intent.comparison.type == "baseline" and intent.comparison.baseline_start and intent.comparison.baseline_end:
            return f"{col} >= {self._literal(intent.comparison.baseline_start)} AND {col} < {self._literal(intent.comparison.baseline_end)}"
        return f"{col} >= NOW() - INTERVAL {days * 2} DAY AND {col} < NOW() - INTERVAL {days} DAY"

    def _dimension_join(self, metric_entity: str, dim: DimensionSpec, finder: JoinPathFinder,
                        index: int) -> Tuple[List[str], str]:
        if metric_entity == dim.entity:
            return [], f"t.{self._col(dim.entity, dim.property)}"
        path = finder.find_path(metric_entity, dim.entity)
        if path is None:
            raise ValueError(f"No ontology path from metric entity {metric_entity} to dimension {dim.entity}")
        joins: List[str] = []
        prev_entity, prev_alias = metric_entity, "t"
        final_alias = "t"
        for hop, step in enumerate(path):
            nxt = step["to"]
            nxt_alias = f"d{index}_{hop}"
            cond = self._relationship_condition(prev_entity, prev_alias, nxt, nxt_alias, step.get("on"))
            joins.append(f"JOIN {self._table(nxt)} {nxt_alias} ON {cond}")
            prev_entity, prev_alias, final_alias = nxt, nxt_alias, nxt_alias
        return joins, f"{final_alias}.{self._col(dim.entity, dim.property)}"

    def _leaf_cte(self, cte_name: str, metric_name: str, metric_cfg: dict, subject: SemanticSubject,
                  finder: JoinPathFinder, intent: SemanticIntent, dimensions: List[DimensionSpec],
                  period: str) -> str:
        entity = metric_cfg.get("entity")
        if not entity:
            raise ValueError(f"Leaf metric {metric_name} must declare an entity")
        self._entity_cfg(entity)
        expression = self._compile_leaf_expression(metric_cfg, entity)
        predicates = [self._subject_scope_exists(entity, subject, finder)]
        time_field = metric_cfg.get("time_field")
        props = self._entity_cfg(entity).get("properties", {})
        if time_field:
            if time_field not in props:
                raise ValueError(f"Metric {metric_name} time_field {time_field} is not a property of {entity}")
            predicates.append(self._time_predicate(entity, time_field, "t", intent, period))
        for idx, f in enumerate(intent.filters or []):
            predicates.append(self._semantic_filter_sql(f, entity, finder, idx))

        joins: List[str] = []
        dim_select: List[str] = []
        dim_group: List[str] = []
        seen_joins: set[str] = set()
        for idx, dim in enumerate(dimensions):
            dj, expr = self._dimension_join(entity, dim, finder, idx)
            for j in dj:
                if j not in seen_joins:
                    joins.append(j); seen_joins.add(j)
            dim_select.append(f"{expr} AS {dim.alias}")
            dim_group.append(expr)

        if intent.time_grain and time_field:
            bucket = self.physical.time_bucket(f"t.{self._col(entity, time_field)}", intent.time_grain)
            dim_select.append(f"{bucket} AS time_bucket")
            dim_group.append(bucket)

        select_parts = dim_select + [f"{expression} AS value"]
        group_by = f" GROUP BY {', '.join(dim_group)}" if dim_group else ""
        return (
            f"{cte_name} AS (\n"
            f"  SELECT {', '.join(select_parts)}\n"
            f"  FROM {self._table(entity)} t\n"
            f"  {' '.join(joins)}\n" if joins else
            f"{cte_name} AS (\n  SELECT {', '.join(select_parts)}\n  FROM {self._table(entity)} t\n"
        ) + f"  WHERE {' AND '.join(predicates)}{group_by}\n)"

    def _all_leaf_metrics(self, metric_names: List[str], graph: MetricDependencyGraph) -> Tuple[List[str], List[str]]:
        ordered_all: List[str] = []
        leaves_all: List[str] = []
        for metric in metric_names:
            for name in graph.ordered(metric):
                if name not in ordered_all:
                    ordered_all.append(name)
            for name in graph.leaves(metric):
                if name not in leaves_all:
                    leaves_all.append(name)
        return ordered_all, leaves_all

    def _derived_aliases(self, metric_names: List[str], graph: MetricDependencyGraph, leaf_aliases: Dict[str, str]) -> Dict[str, str]:
        aliases = dict(leaf_aliases)
        progress = True
        while progress:
            progress = False
            for metric in metric_names:
                for name in graph.ordered(metric):
                    if name in aliases:
                        continue
                    deps = graph.dependencies(name)
                    if deps and all(d in aliases for d in deps):
                        aliases[name] = f"({graph.derived_expression(name, {d: aliases[d] for d in deps})})"
                        progress = True
        return aliases

    def _metric_query(self, metric_names: List[str], subject: SemanticSubject, finder: JoinPathFinder,
                      intent: SemanticIntent, dimensions: List[DimensionSpec], period: str = "current") -> Tuple[str, List[str], List[str]]:
        graph = MetricDependencyGraph(self.registry.metrics)
        ordered, leaves = self._all_leaf_metrics(metric_names, graph)
        if not leaves:
            raise ValueError("No executable leaf metrics resolved")
        suffix = "cur" if period == "current" else "prev"
        ctes: List[str] = []
        for leaf in leaves:
            ctes.append(self._leaf_cte(f"m_{leaf}_{suffix}", leaf, graph.get(leaf), subject, finder, intent, dimensions, period))

        dim_aliases = [d.alias for d in dimensions] + (["time_bucket"] if intent.time_grain else [])
        base = leaves[0]
        base_alias = "q0"
        from_sql = f"m_{base}_{suffix} {base_alias}"
        joins: List[str] = []
        query_aliases = [base_alias]
        leaf_sql_aliases: Dict[str, str] = {base: f"{base_alias}.value"}
        for idx, leaf in enumerate(leaves[1:], start=1):
            qa = f"q{idx}"
            if dim_aliases:
                cond_parts = []
                for d in dim_aliases:
                    left_key = f"COALESCE({', '.join(a + '.' + d for a in query_aliases)})" if len(query_aliases) > 1 else f"{query_aliases[0]}.{d}"
                    cond_parts.append(f"{left_key} = {qa}.{d}")
                joins.append(f"FULL OUTER JOIN m_{leaf}_{suffix} {qa} ON {' AND '.join(cond_parts)}")
            else:
                joins.append(f"CROSS JOIN m_{leaf}_{suffix} {qa}")
            query_aliases.append(qa)
            leaf_sql_aliases[leaf] = f"{qa}.value"

        aliases = self._derived_aliases(metric_names, graph, leaf_sql_aliases)
        select_parts = []
        for d in dim_aliases:
            dim_expr = f"COALESCE({', '.join(a + '.' + d for a in query_aliases)})" if len(query_aliases) > 1 else f"{base_alias}.{d}"
            select_parts.append(f"{dim_expr} AS {d}")
        for metric in metric_names:
            if metric not in aliases:
                raise ValueError(f"Unable to compile metric dependency expression for {metric}")
            select_parts.append(f"{aliases[metric]} AS {metric}")
        sql = (
            "WITH\n" + ",\n".join(ctes) + "\n" +
            f"SELECT {', '.join(select_parts)}\nFROM {from_sql}" +
            ("\n" + "\n".join(joins) if joins else "")
        )
        entities = []
        for metric in metric_names:
            for entity in graph.entities(metric):
                if entity not in entities:
                    entities.append(entity)
        return sql, ordered, entities

    def _comparison_sql(self, metric_names: List[str], subject: SemanticSubject, finder: JoinPathFinder,
                        intent: SemanticIntent, dimensions: List[DimensionSpec]) -> Tuple[str, List[str], List[str]]:
        current_sql, ordered, entities = self._metric_query(metric_names, subject, finder, intent, dimensions, "current")
        previous_sql, _, _ = self._metric_query(metric_names, subject, finder, intent, dimensions, "previous")
        dim_aliases = [d.alias for d in dimensions] + (["time_bucket"] if intent.time_grain else [])
        join_cond = " AND ".join(f"cur.{d} = prev.{d}" for d in dim_aliases) if dim_aliases else "1=1"
        select_parts = [f"cur.{d}" for d in dim_aliases]
        for metric in metric_names:
            select_parts.extend([
                f"cur.{metric} AS {metric}_current",
                f"prev.{metric} AS {metric}_previous",
                f"((cur.{metric} - prev.{metric}) / NULLIF(prev.{metric}, 0) * 100) AS {metric}_change_pct",
            ])
        sql = (
            "WITH\ncurrent_period AS (\n" + current_sql + "\n),\n"
            "previous_period AS (\n" + previous_sql + "\n)\n"
            f"SELECT {', '.join(select_parts)}\n"
            "FROM current_period cur\n"
            f"LEFT JOIN previous_period prev ON {join_cond}"
        )
        return sql, ordered, entities

    def _diagnostic_sql(self, entity: str, subject: SemanticSubject, finder: JoinPathFinder, days: int) -> Optional[str]:
        cfg = self._entity_cfg(entity)
        props = cfg.get("properties", {})
        time_candidates = [p for p, pcfg in props.items() if pcfg.get("type") == "datetime"]
        time_field = time_candidates[0] if time_candidates else None
        preferred = ["alarm_name", "severity", "event_time", "created_at", "fault_description", "action"]
        selected = [p for p in preferred if p in props] or list(props.keys())[:6]
        if not selected:
            return None
        select_sql = ", ".join(f"t.{self._col(entity, p)} AS {p}" for p in selected)
        predicates = [self._subject_scope_exists(entity, subject, finder)]
        if time_field:
            lookback = max(days * 4, 30) if "workorder" in entity.lower() else days
            predicates.append(f"t.{self._col(entity, time_field)} >= NOW() - INTERVAL {lookback} DAY")
        order = f" ORDER BY t.{self._col(entity, time_field)} DESC" if time_field else ""
        return f"SELECT {select_sql} FROM {self._table(entity)} t WHERE {' AND '.join(predicates)}{order} LIMIT 20"

    def build(self, intent: SemanticIntent) -> QueryPlan:
        subject = intent.subject or SemanticSubject(entity="Machine", reference=intent.machine_ref)
        self._entity_cfg(subject.entity)
        metric_names = list(dict.fromkeys(intent.metrics or ([] if not intent.metric else [intent.metric])))
        if not metric_names:
            raise ValueError("Unable to resolve a governed metric from the question")
        dimensions = self._parse_dimensions(list(intent.dimensions or []))
        finder = JoinPathFinder(self.registry.ontology)

        if intent.comparison.type in ("previous_period", "baseline"):
            metric_sql, metric_order, metric_entities = self._comparison_sql(metric_names, subject, finder, intent, dimensions)
        else:
            metric_sql, metric_order, metric_entities = self._metric_query(metric_names, subject, finder, intent, dimensions)

        required_entities: List[str] = [subject.entity]
        for dim in dimensions:
            if dim.entity not in required_entities:
                required_entities.append(dim.entity)
        for f in intent.filters or []:
            if f.entity and f.entity not in required_entities:
                required_entities.append(f.entity)
        for entity in metric_entities + list(intent.related_entities or []):
            if entity in self.registry.ontology.get("entities", {}) and entity not in required_entities:
                required_entities.append(entity)

        join_paths: Dict[str, List[dict]] = {}
        # Preserve not only requested/metric entities but also every governed
        # intermediate ontology node used by the executable JOIN paths. This is
        # required for physical-table allowlisting, lineage and cost governance.
        targets = list(required_entities)
        for entity in targets:
            if entity == subject.entity:
                continue
            path = finder.find_path(subject.entity, entity)
            if path is None:
                raise ValueError(f"No ontology relationship path from {subject.entity} to required entity {entity}")
            join_paths[entity] = path
            for step in path:
                for path_entity in (step.get("from"), step.get("to")):
                    if path_entity and path_entity not in required_entities:
                        required_entities.append(path_entity)

        sql: List[str] = [self._subject_evidence_sql(subject), metric_sql]
        days = intent.time_range.normalized_days() if intent.time_range else max(1, min(intent.time_window_days, 365))
        if intent.analysis_mode == "diagnostic":
            metric_set = set(metric_entities)
            for entity in required_entities:
                if entity == subject.entity or entity in metric_set or any(d.entity == entity for d in dimensions):
                    continue
                evidence_sql = self._diagnostic_sql(entity, subject, finder, days)
                if evidence_sql:
                    sql.append(evidence_sql)

        dimension_plan = [{"raw": d.raw, "entity": d.entity, "property": d.property, "alias": d.alias} for d in dimensions]
        logical_plan = {
            "subject": subject.model_dump(),
            "metrics": metric_names,
            "dimensions": dimension_plan,
            "filters": [f.model_dump() for f in intent.filters or []],
            "time_range": intent.time_range.model_dump() if intent.time_range else None,
            "time_grain": intent.time_grain,
            "comparison": intent.comparison.model_dump(),
            "metric_dependencies": metric_order,
            "required_entities": required_entities,
        }
        physical_plan = self.physical.describe(required_entities, dimension_plan, intent.comparison.type)
        return QueryPlan(
            intent=intent,
            sql=sql,
            notes=[
                "V0.6 executes multiple governed metrics in one logical plan.",
                "Dimensions are resolved through ontology paths and compiled as governed GROUP BY keys.",
                "Cross-entity filters are compiled as ontology-driven EXISTS subplans instead of being ignored.",
                "Previous-period/baseline comparison is compiled deterministically from the semantic time contract.",
                "Doris physical-plan metadata identifies federated catalogs/tables before execution.",
                "The LLM resolves semantic intent only and never emits executable SQL.",
            ],
            metric_dependencies=metric_order,
            required_entities=required_entities,
            join_paths=join_paths,
            subject_entity=subject.entity,
            logical_plan=logical_plan,
            physical_plan=physical_plan,
        )
