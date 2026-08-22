from app.semantic import SemanticRegistry
from app.planner import QueryPlanner
from app.models import SemanticIntent, SemanticSubject
from app.metric_graph import MetricDependencyGraph


def test_metric_graph_specific_energy():
    registry = SemanticRegistry()
    graph = MetricDependencyGraph(registry.metrics)
    assert graph.ordered("specific_energy_consumption") == [
        "energy_consumption", "production_output", "specific_energy_consumption"
    ]
    assert graph.entities("specific_energy_consumption") == [
        "EnergyObservation", "ProductionObservation"
    ]


def test_planner_is_metric_and_ontology_driven():
    registry = SemanticRegistry()
    plan = QueryPlanner(registry).build(SemanticIntent(
        raw_question="A101最近7天单位能耗为什么升高",
        subject=SemanticSubject(entity="Machine", reference="A101"),
        metrics=["specific_energy_consumption"],
        time_window_days=7,
        analysis_mode="diagnostic",
        related_entities=["Machine", "AlarmEvent", "WorkOrder"],
    ))
    assert "energy_consumption" in plan.metric_dependencies
    assert "production_output" in plan.metric_dependencies
    assert "EnergyObservation" in plan.required_entities
    assert "ProductionObservation" in plan.required_entities
    assert "AlarmEvent" in plan.join_paths
    sql = "\n".join(plan.sql)
    assert "mysql_mes.production.production_hourly" in sql
    assert "internal.industrial_ai.energy_5min" in sql
    assert "pg_cmms.public.alarm_event" in sql
