from app.models import (
    ComparisonSpec,
    SemanticFilter,
    SemanticIntent,
    SemanticSubject,
    SemanticTimeRange,
)
from app.planner import QueryPlanner
from app.semantic import SemanticRegistry


def test_multi_metric_plan_compiles_shared_leaf_metrics():
    plan = QueryPlanner(SemanticRegistry()).build(SemanticIntent(
        raw_question="F01工厂最近30天能耗、产量和单位能耗",
        subject=SemanticSubject(entity="Factory", reference="F01"),
        metrics=["energy_consumption", "production_output", "specific_energy_consumption"],
        time_range=SemanticTimeRange(value=30, unit="day"),
        analysis_mode="descriptive",
    ))
    sql = plan.sql[1]
    assert "AS energy_consumption" in sql
    assert "AS production_output" in sql
    assert "AS specific_energy_consumption" in sql
    assert sql.count("m_energy_consumption_cur AS") == 1
    assert sql.count("m_production_output_cur AS") == 1


def test_dimension_group_by_uses_ontology_path():
    plan = QueryPlanner(SemanticRegistry()).build(SemanticIntent(
        raw_question="F01工厂各产线最近30天能耗",
        subject=SemanticSubject(entity="Factory", reference="F01"),
        metrics=["energy_consumption"],
        dimensions=["ProductionLine.line_name"],
        time_range=SemanticTimeRange(value=30, unit="day"),
        analysis_mode="descriptive",
    ))
    sql = plan.sql[1]
    assert "production_line" in sql
    assert "line_name AS productionline_line_name" in sql
    assert "GROUP BY" in sql
    assert plan.logical_plan["dimensions"][0]["entity"] == "ProductionLine"


def test_cross_entity_filter_is_compiled_as_exists():
    plan = QueryPlanner(SemanticRegistry()).build(SemanticIntent(
        raw_question="F01工厂A类设备最近7天能耗",
        subject=SemanticSubject(entity="Factory", reference="F01"),
        metrics=["energy_consumption"],
        filters=[SemanticFilter(entity="Machine", property="machine_type", operator="=", value="A")],
        time_range=SemanticTimeRange(value=7, unit="day"),
        analysis_mode="descriptive",
    ))
    sql = plan.sql[1]
    assert "EXISTS (SELECT 1 FROM mysql_mes.production.device_master" in sql
    assert "device_type = 'A'" in sql
    assert "Machine" in plan.required_entities


def test_previous_period_comparison_compiles_change_pct():
    plan = QueryPlanner(SemanticRegistry()).build(SemanticIntent(
        raw_question="F01工厂最近30天能耗与上期比较",
        subject=SemanticSubject(entity="Factory", reference="F01"),
        metrics=["energy_consumption"],
        time_range=SemanticTimeRange(value=30, unit="day"),
        comparison=ComparisonSpec(type="previous_period"),
        analysis_mode="descriptive",
    ))
    sql = plan.sql[1]
    assert "current_period AS" in sql
    assert "previous_period AS" in sql
    assert "energy_consumption_change_pct" in sql
    assert "INTERVAL 60 DAY" in sql
    assert "INTERVAL 30 DAY" in sql


def test_physical_plan_detects_doris_federation_across_catalogs():
    plan = QueryPlanner(SemanticRegistry()).build(SemanticIntent(
        raw_question="A101单位能耗并查看告警",
        subject=SemanticSubject(entity="Machine", reference="A101"),
        metrics=["specific_energy_consumption", "alarm_count"],
        related_entities=["WorkOrder"],
        time_range=SemanticTimeRange(value=7, unit="day"),
    ))
    assert plan.physical_plan["dialect"] == "doris"
    assert plan.physical_plan["federated"] is True
    assert {"internal", "mysql_mes", "pg_cmms"}.issubset(set(plan.physical_plan["catalogs"]))


def test_rule_resolver_emits_v06_dimensions_multiple_metrics_and_comparison():
    registry = SemanticRegistry()
    intent = registry.resolve("F01工厂各产线最近30天能耗和产量与上期相比")
    assert intent.subject.entity == "Factory"
    assert "energy_consumption" in intent.metrics
    assert "production_output" in intent.metrics
    assert "ProductionLine.line_name" in intent.dimensions
    assert intent.comparison.type == "previous_period"
