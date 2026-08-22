from pathlib import Path

import yaml
import pytest

from app.evidence_graph import EvidenceGraphBuilder
from app.governance import GovernanceError, PolicyEngine, PolicyStore, QueryCostEstimator
from app.guardrail import SQLGuardrail
from app.models import SemanticIntent, SemanticSubject, SemanticTimeRange, SemanticFilter
from app.planner import QueryPlanner
from app.semantic import SemanticRegistry


def test_row_policy_is_injected_as_semantic_filter(tmp_path: Path):
    policy_file = tmp_path / "governance.yaml"
    policy_file.write_text(yaml.safe_dump({
        "roles": {"factory_analyst": {
            "allowed_entities": ["*"], "allowed_metrics": ["*"],
            "max_time_window_days": 31, "max_estimated_cost": 200,
            "denied_properties": [], "require_subject_reference": False,
        }},
        "row_policies": {"factory_analyst": [{
            "entity": "Machine", "property": "factory_id", "operator": "=", "value": "${factory_id}"
        }]},
    }), encoding="utf-8")
    registry = SemanticRegistry()
    engine = PolicyEngine(registry, PolicyStore(policy_file))
    intent = SemanticIntent(raw_question="A101最近7天能耗", subject=SemanticSubject(entity="Machine", reference="A101"), metrics=["energy_consumption"])
    governed, meta = engine.apply_intent(intent, roles=["factory_analyst"], attributes={"factory_id": "F01"})
    assert any(f.entity == "Machine" and f.property == "factory_id" and f.value == "F01" for f in governed.filters)
    assert meta["applied_row_filters"]


def test_column_policy_denies_dimension(tmp_path: Path):
    policy_file = tmp_path / "governance.yaml"
    policy_file.write_text(yaml.safe_dump({"roles": {"limited": {
        "allowed_entities": ["*"], "allowed_metrics": ["*"],
        "denied_properties": ["Machine.machine_type"],
        "max_time_window_days": 31, "max_estimated_cost": 200,
    }}}), encoding="utf-8")
    registry = SemanticRegistry()
    engine = PolicyEngine(registry, PolicyStore(policy_file))
    intent = SemanticIntent(raw_question="按设备类型看能耗", metrics=["energy_consumption"], dimensions=["Machine.machine_type"])
    with pytest.raises(GovernanceError):
        engine.apply_intent(intent, roles=["limited"])


def test_cost_limit_blocks_expensive_federated_plan(tmp_path: Path):
    policy_file = tmp_path / "governance.yaml"
    policy_file.write_text(yaml.safe_dump({"roles": {"tiny": {
        "allowed_entities": ["*"], "allowed_metrics": ["*"],
        "denied_properties": [], "max_time_window_days": 365,
        "max_estimated_cost": 10,
    }}}), encoding="utf-8")
    registry = SemanticRegistry()
    engine = PolicyEngine(registry, PolicyStore(policy_file))
    intent = SemanticIntent(raw_question="test", metrics=["energy_consumption"], time_range=SemanticTimeRange(value=30))
    with pytest.raises(GovernanceError):
        engine.evaluate_plan(intent, ["Machine", "EnergyObservation"], {"catalogs": ["mysql_mes", "internal"], "federated": True}, roles=["tiny"])


def test_sql_gateway_rejects_unknown_physical_table():
    guard = SQLGuardrail()
    with pytest.raises(ValueError):
        guard.validate("SELECT id FROM evil.public.secret_table LIMIT 1", allowed_tables=["mysql_mes.production.device_master"])


def test_sql_gateway_accepts_governed_plan():
    registry = SemanticRegistry()
    plan = QueryPlanner(registry).build(SemanticIntent(
        raw_question="A101最近7天单位能耗",
        subject=SemanticSubject(entity="Machine", reference="A101"),
        metrics=["specific_energy_consumption"],
    ))
    result = SQLGuardrail(registry).validate_plan(plan)
    assert result and all(x["statement_type"] == "select" for x in result)


def test_evidence_graph_contains_hypothesis_support_edges():
    registry = SemanticRegistry()
    plan = QueryPlanner(registry).build(SemanticIntent(
        raw_question="A101为什么能耗高",
        subject=SemanticSubject(entity="Machine", reference="A101"),
        metrics=["energy_consumption"],
    ))
    graph = EvidenceGraphBuilder().build(plan, {}, {"hypotheses": [{
        "cause": "过滤器堵塞", "confidence": 0.82,
        "evidence": ["压差升高"], "recommended_checks": ["检查过滤器"]
    }]})
    relations = {e["relation"] for e in graph["edges"]}
    assert "SUPPORTS" in relations
    assert "RECOMMENDS" in relations
    assert any(n["type"] == "hypothesis" for n in graph["nodes"])
