from pathlib import Path
from app.lineage import SemanticVersionStore, QueryLineageStore
from app.models import SemanticIntent, SemanticSubject
from app.planner import QueryPlanner
from app.semantic import SemanticRegistry


def test_semantic_version_snapshot_deduplicates_identical_model(tmp_path: Path):
    store = SemanticVersionStore(tmp_path / "versions.json")
    registry = SemanticRegistry()
    a = store.snapshot(registry, "test")
    b = store.snapshot(registry, "test_again")
    assert a["digest"] == b["digest"]
    assert len(store.list()) == 1


def test_query_lineage_records_semantic_to_physical_mapping(tmp_path: Path):
    registry = SemanticRegistry()
    plan = QueryPlanner(registry).build(SemanticIntent(
        raw_question="A101能耗",
        subject=SemanticSubject(entity="Machine", reference="A101"),
        metrics=["energy_consumption"],
    ))
    store = QueryLineageStore(tmp_path / "lineage.json")
    row = store.record(plan, governance={"allowed": True}, user="tester")
    assert row["metrics"] == ["energy_consumption"]
    assert row["tables"]
    assert row["catalogs"]
    assert row["governance"]["allowed"] is True
