from app.semantic import SemanticRegistry
from app.planner import QueryPlanner
from app.guardrail import SQLGuardrail
from app.metadata import MockMetadataScanner
from app.candidate_generator import generate_candidates


def run():
    registry = SemanticRegistry()
    graph = registry.graph()
    assert len(graph["nodes"]) >= 7
    assert graph["edges"][0]["on"] == "machine_id"

    intent = registry.resolve("A101空压机最近一周单位产量能耗为什么增加？")
    assert intent.machine_ref == "A101"
    assert intent.metric == "specific_energy_consumption"
    assert intent.analysis_mode == "diagnostic"

    plan = QueryPlanner(registry).build(intent)
    assert len(plan.sql) >= 4
    assert plan.subject_entity == "Machine"
    assert "mysql_mes.production.device_master" in plan.sql[0]
    for sql in plan.sql:
        SQLGuardrail().validate(sql)

    candidates = generate_candidates(MockMetadataScanner().scan())
    by_entity = {c.entity: c for c in candidates}
    assert "Machine" in by_entity
    assert "EnergyObservation" in by_entity
    assert by_entity["EnergyObservation"].metrics[0].name == "energy_consumption"
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    run()
