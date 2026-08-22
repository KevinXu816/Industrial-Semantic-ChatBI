from app.models import SemanticIntent, SemanticSubject, SemanticTimeRange
from app.planner import QueryPlanner
from app.semantic import SemanticRegistry


def test_backward_compatibility_syncs_generic_fields():
    intent = SemanticIntent(raw_question="A101能耗", machine_ref="A101", metric="energy_consumption", time_window_days=7)
    assert intent.subject.entity == "Machine"
    assert intent.subject.reference == "A101"
    assert intent.metrics == ["energy_consumption"]
    assert intent.time_range.normalized_days() == 7


def test_machine_subject_uses_ontology_path_not_machine_id_hardcoding():
    registry = SemanticRegistry()
    intent = SemanticIntent(
        raw_question="A101最近7天单位能耗",
        subject=SemanticSubject(entity="Machine", reference="A101"),
        metrics=["specific_energy_consumption"],
        time_range=SemanticTimeRange(value=7, unit="day"),
        related_entities=["AlarmEvent", "WorkOrder"],
    )
    plan = QueryPlanner(registry).build(intent)
    assert plan.subject_entity == "Machine"
    assert plan.logical_plan["subject"]["reference"] == "A101"
    assert "EnergyObservation" in plan.join_paths
    sql = "\n".join(plan.sql)
    assert "EXISTS (SELECT 1 FROM mysql_mes.production.device_master s0" in sql
    assert "t.machine_id" in sql


def test_factory_subject_can_scope_machine_metrics_through_multihop_ontology():
    registry = SemanticRegistry()
    intent = SemanticIntent(
        raw_question="F01工厂最近7天能耗",
        subject=SemanticSubject(entity="Factory", reference="F01"),
        metrics=["energy_consumption"],
        time_range=SemanticTimeRange(value=7, unit="day"),
        analysis_mode="descriptive",
    )
    plan = QueryPlanner(registry).build(intent)
    assert plan.subject_entity == "Factory"
    assert "EnergyObservation" in plan.join_paths
    assert len(plan.join_paths["EnergyObservation"]) == 3
    sql = "\n".join(plan.sql)
    assert "factory_master" in sql
    assert "production_line" in sql
    assert "device_master" in sql
