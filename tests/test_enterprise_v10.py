from pathlib import Path
from fastapi.testclient import TestClient

from app.persistence import JsonRepository
from app.rca_cases import RCACaseStore
from app.runtime_stats import RuntimeQueryStore


def test_json_repository_roundtrip(tmp_path: Path):
    repo = JsonRepository(tmp_path / "repo")
    repo.put("demo", "1", {"id": "1", "value": 42})
    assert repo.get("demo", "1")["value"] == 42
    assert len(repo.list("demo")) == 1
    assert repo.health()["status"] == "ok"
    assert repo.delete("demo", "1") is True


def test_rca_case_lifecycle(tmp_path: Path):
    store = RCACaseStore(JsonRepository(tmp_path / "repo"))
    case = store.create({"question": "A101单位能耗为什么升高？", "subject": {"entity": "Machine", "reference": "A101"}}, actor="tester")
    assert case["status"] == "open"
    case = store.attach_analysis(case["case_id"], {"hypotheses": [{"cause": "filter_restriction", "confidence": 0.8}]})
    assert case["status"] == "analyzed"
    case = store.review(case["case_id"], {"accepted": True, "predicted_cause": "filter_restriction"}, actor="engineer")
    assert case["status"] == "reviewed"
    assert case["confirmed_root_cause"] == "filter_restriction"
    case = store.resolve(case["case_id"], {"action": "replace_filter"}, actor="engineer")
    assert case["status"] == "resolved"
    assert len(case["history"]) == 4


def test_runtime_query_summary(tmp_path: Path):
    store = RuntimeQueryStore(JsonRepository(tmp_path / "repo"))
    store.record({"success": True, "duration_ms": 100, "normalized_cost": 20})
    store.record({"success": False, "duration_ms": 300, "normalized_cost": 40})
    summary = store.summary()
    assert summary["total"] == 2
    assert summary["success_rate"] == 0.5
    assert summary["avg_duration_ms"] == 200.0
    assert summary["avg_normalized_cost"] == 30.0


def test_v10_health_and_case_api():
    from app.main import app
    client = TestClient(app)
    h = client.get("/health")
    assert h.status_code == 200
    assert h.json()["version"] == "4.9.0"
    created = client.post("/rca/cases", json={"question": "test enterprise case", "actor": "tester"})
    assert created.status_code == 200
    case_id = created.json()["case_id"]
    fetched = client.get(f"/rca/cases/{case_id}")
    assert fetched.status_code == 200
    reviewed = client.post(f"/rca/cases/{case_id}/review", json={"accepted": True, "predicted_cause": "demo", "actor": "engineer"})
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewed"
