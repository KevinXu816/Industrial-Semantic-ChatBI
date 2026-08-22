"""V0.7 enterprise query governance.

The governance layer is intentionally independent from the semantic planner:
- RBAC authorizes semantic entities/metrics before SQL generation.
- Row policies become governed SemanticFilter objects, never raw SQL from users.
- Column policies validate semantic dimensions/filters.
- Query-cost limits inspect logical/physical plans before execution.
- SQLGuardrail remains the final read-only SQL boundary.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import yaml

from .models import SemanticFilter, SemanticIntent

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "governance.yaml"


DEFAULT_POLICY = {
    "roles": {
        "viewer": {
            "allowed_entities": ["*"],
            "allowed_metrics": ["*"],
            "denied_properties": [],
            "max_time_window_days": 31,
            "max_estimated_cost": 80,
            "require_subject_reference": False,
        },
        "analyst": {
            "allowed_entities": ["*"],
            "allowed_metrics": ["*"],
            "denied_properties": [],
            "max_time_window_days": 365,
            "max_estimated_cost": 250,
            "require_subject_reference": False,
        },
        "semantic_admin": {
            "allowed_entities": ["*"],
            "allowed_metrics": ["*"],
            "denied_properties": [],
            "max_time_window_days": 3650,
            "max_estimated_cost": 1000,
            "require_subject_reference": False,
        },
    },
    "row_policies": {},
}


class GovernanceError(ValueError):
    pass


@dataclass
class GovernanceDecision:
    allowed: bool
    roles: List[str]
    applied_row_filters: List[Dict[str, Any]]
    estimated_cost: float = 0.0
    reasons: List[str] | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "roles": self.roles,
            "applied_row_filters": self.applied_row_filters,
            "estimated_cost": round(self.estimated_cost, 2),
            "reasons": self.reasons or [],
        }


class PolicyStore:
    def __init__(self, path: Path = POLICY_PATH):
        self.path = path
        self.reload()

    def reload(self) -> None:
        data = {}
        if self.path.exists():
            try:
                data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
        self.policy = copy.deepcopy(DEFAULT_POLICY)
        self.policy["roles"].update(data.get("roles", {}))
        self.policy["row_policies"].update(data.get("row_policies", {}))

    def role(self, name: str) -> Dict[str, Any]:
        return self.policy.get("roles", {}).get(name, {})


class QueryCostEstimator:
    """Cheap deterministic cost model used before Doris EXPLAIN is available.

    V0.8 can replace/augment this with Doris EXPLAIN JSON/cardinality estimates.
    """

    def estimate(self, intent: SemanticIntent, required_entities: Iterable[str], physical_plan: Dict[str, Any]) -> Dict[str, Any]:
        entities = list(dict.fromkeys(required_entities))
        days = intent.time_range.normalized_days() if intent.time_range else intent.time_window_days
        metrics = max(1, len(intent.metrics or ([intent.metric] if intent.metric else [])))
        dimensions = len(intent.dimensions or [])
        filters = len(intent.filters or [])
        catalogs = len(physical_plan.get("catalogs", []))
        federated = bool(physical_plan.get("federated"))
        comparison_multiplier = 2 if intent.comparison.type != "none" else 1

        score = 8.0
        score += min(days, 3650) * 0.15
        score += max(0, len(entities) - 1) * 10
        score += max(0, metrics - 1) * 7
        score += dimensions * 8
        score += filters * 3
        score += max(0, catalogs - 1) * 18
        score *= comparison_multiplier
        if federated:
            score *= 1.15
        return {
            "score": round(score, 2),
            "days": days,
            "entity_count": len(entities),
            "metric_count": metrics,
            "dimension_count": dimensions,
            "filter_count": filters,
            "catalog_count": catalogs,
            "federated": federated,
            "comparison_multiplier": comparison_multiplier,
            "class": "low" if score < 60 else "medium" if score < 150 else "high",
        }


class PolicyEngine:
    def __init__(self, registry, store: Optional[PolicyStore] = None):
        self.registry = registry
        self.store = store or PolicyStore()
        self.cost = QueryCostEstimator()

    @staticmethod
    def _allowed(value: str, rules: Iterable[str]) -> bool:
        rules = list(rules or [])
        return "*" in rules or value in rules

    def _effective_role(self, roles: List[str]) -> Dict[str, Any]:
        roles = roles or ["viewer"]
        configs = [self.store.role(r) for r in roles if self.store.role(r)]
        if not configs:
            raise GovernanceError(f"No known role in {roles}")
        # Union allows; strongest numeric limit wins. Denies always accumulate.
        entities: Set[str] = set()
        metrics: Set[str] = set()
        denied: Set[str] = set()
        max_days = 0
        max_cost = 0.0
        require_subject = True
        for cfg in configs:
            entities.update(cfg.get("allowed_entities", []))
            metrics.update(cfg.get("allowed_metrics", []))
            denied.update(cfg.get("denied_properties", []))
            max_days = max(max_days, int(cfg.get("max_time_window_days", 31)))
            max_cost = max(max_cost, float(cfg.get("max_estimated_cost", 80)))
            require_subject = require_subject and bool(cfg.get("require_subject_reference", False))
        return {
            "allowed_entities": entities,
            "allowed_metrics": metrics,
            "denied_properties": denied,
            "max_time_window_days": max_days,
            "max_estimated_cost": max_cost,
            "require_subject_reference": require_subject,
        }

    def apply_intent(self, intent: SemanticIntent, roles: Optional[List[str]] = None,
                     attributes: Optional[Dict[str, Any]] = None) -> tuple[SemanticIntent, Dict[str, Any]]:
        roles = roles or ["analyst"]
        attrs = attributes or {}
        effective = self._effective_role(roles)
        cloned = intent.model_copy(deep=True)
        subject = cloned.subject
        if subject and not self._allowed(subject.entity, effective["allowed_entities"]):
            raise GovernanceError(f"Role cannot access entity {subject.entity}")
        for metric in cloned.metrics or ([] if not cloned.metric else [cloned.metric]):
            if not self._allowed(metric, effective["allowed_metrics"]):
                raise GovernanceError(f"Role cannot access metric {metric}")
        days = cloned.time_range.normalized_days() if cloned.time_range else cloned.time_window_days
        if days > effective["max_time_window_days"]:
            raise GovernanceError(
                f"Requested time window {days}d exceeds role limit {effective['max_time_window_days']}d"
            )
        if effective["require_subject_reference"] and (not subject or subject.reference is None):
            raise GovernanceError("This role requires a concrete subject reference")

        denied = effective["denied_properties"]
        for dim in cloned.dimensions:
            if dim in denied or dim.split(".")[-1] in denied:
                raise GovernanceError(f"Column policy denies dimension {dim}")
        for f in cloned.filters:
            qualified = f"{f.entity}.{f.property}" if f.entity else f.property
            if qualified in denied or f.property in denied:
                raise GovernanceError(f"Column policy denies filter property {qualified}")

        applied: List[Dict[str, Any]] = []
        # Row policies are semantic templates, e.g. ${factory_id} resolves from trusted attributes.
        for role in roles:
            for rule in self.store.policy.get("row_policies", {}).get(role, []):
                entity = rule.get("entity")
                prop = rule.get("property")
                if not entity or not prop:
                    continue
                if entity not in self.registry.ontology.get("entities", {}):
                    continue
                if prop not in self.registry.ontology["entities"][entity].get("properties", {}):
                    continue
                raw_value = rule.get("value")
                value = raw_value
                if isinstance(raw_value, str):
                    m = re.fullmatch(r"\$\{([^}]+)\}", raw_value)
                    if m:
                        if m.group(1) not in attrs:
                            continue
                        value = attrs[m.group(1)]
                sf = SemanticFilter(
                    entity=entity,
                    property=prop,
                    operator=rule.get("operator", "="),
                    value=value,
                )
                if sf.model_dump() not in [x.model_dump() for x in cloned.filters]:
                    cloned.filters.append(sf)
                    applied.append(sf.model_dump())
        return cloned, {"roles": roles, "applied_row_filters": applied, "limits": effective}

    def evaluate_plan(self, intent: SemanticIntent, required_entities: List[str], physical_plan: Dict[str, Any],
                      roles: Optional[List[str]] = None, applied_row_filters: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        roles = roles or ["analyst"]
        effective = self._effective_role(roles)
        for entity in required_entities:
            if not self._allowed(entity, effective["allowed_entities"]):
                raise GovernanceError(f"Role cannot access required entity {entity}")
        estimate = self.cost.estimate(intent, required_entities, physical_plan)
        if estimate["score"] > effective["max_estimated_cost"]:
            raise GovernanceError(
                f"Estimated query cost {estimate['score']} exceeds role limit {effective['max_estimated_cost']}"
            )
        decision = GovernanceDecision(
            allowed=True,
            roles=roles,
            applied_row_filters=applied_row_filters or [],
            estimated_cost=estimate["score"],
            reasons=[f"cost_class={estimate['class']}", "semantic RBAC/column/time policies passed"],
        ).as_dict()
        decision["cost"] = estimate
        return decision
