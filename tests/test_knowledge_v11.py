from pathlib import Path
from fastapi.testclient import TestClient

from app.historical_rca import HistoricalRCARetriever
from app.knowledge_backends import LocalHybridBackend
from app.knowledge_ingestion import KnowledgeIngestionPipeline
from app.knowledge_store import KnowledgeStore
from app.persistence import JsonRepository
from app.rca_cases import RCACaseStore


def _stack(tmp_path: Path):
    repo = JsonRepository(tmp_path / "repo")
    store = KnowledgeStore(repo)
    backend = LocalHybridBackend(store)
    ingest = KnowledgeIngestionPipeline(store, backend)
    return repo, store, backend, ingest


def test_ingestion_chunk_version_and_hybrid_retrieval(tmp_path: Path):
    repo, store, backend, ingest = _stack(tmp_path)
    result = ingest.ingest_documents([{
        "id": "FMEA-TEST-001", "version": "2.1", "type": "FMEA",
        "title": "空压机过滤器堵塞", "failure_mode": "filter_restriction",
        "content": "过滤器压差持续升高会增加吸气阻力，并导致单位能耗恶化。建议检查过滤器压差并更换滤芯。",
        "tags": ["filter_restriction", "pressure", "energy"],
    }], actor="tester", chunk_size=120, overlap=20)
    assert result["documents_ingested"] == 1
    assert result["chunks_created"] >= 1
    doc = store.get_document("FMEA-TEST-001", "2.1")
    assert doc["citation"].startswith("FMEA-TEST-001@2.1#")
    hits = backend.search("过滤器 压差 单位能耗", top_k=3)
    assert hits
    assert hits[0]["document_id"] == "FMEA-TEST-001"
    assert "lexical_score" in hits[0] and "vector_score" in hits[0]


def test_historical_confirmed_rca_becomes_retrievable_knowledge(tmp_path: Path):
    repo, *_ = _stack(tmp_path)
    cases = RCACaseStore(repo)
    case = cases.create({"question": "A101空压机单位能耗升高", "title": "A101过滤器异常"}, actor="tester")
    cases.review(case["case_id"], {"accepted": True, "predicted_cause": "filter_restriction"}, actor="engineer")
    cases.resolve(case["case_id"], {"confirmed_root_cause": "filter_restriction", "action": "replace_filter", "comment": "更换过滤器后恢复"}, actor="engineer")
    hits = HistoricalRCARetriever(repo).search("空压机 能耗 过滤器", top_k=3)
    assert hits
    assert hits[0]["type"] == "HistoricalRCA"
    assert hits[0]["confirmed_root_cause"] == "filter_restriction"
    assert hits[0]["provenance"].startswith("rca_case:")


def test_v11_knowledge_api_and_health():
    from app.main import app
    client = TestClient(app)
    h = client.get("/health")
    assert h.status_code == 200
    assert h.json()["version"] == "2.9.0"
    created = client.post("/knowledge/documents", json={
        "id": "SOP-V11-TEST", "version": "1.0", "type": "SOP",
        "title": "过滤器检查流程", "content": "检查过滤器压差，必要时更换滤芯。",
        "tags": ["filter", "pressure"], "actor": "tester"
    })
    assert created.status_code == 200
    search = client.get("/knowledge/search", params={"q": "过滤器 压差", "top_k": 5})
    assert search.status_code == 200
    assert any(x.get("document_id") == "SOP-V11-TEST" for x in search.json()["results"])
    stats = client.get("/knowledge/stats")
    assert stats.status_code == 200
    assert stats.json()["documents"] >= 1
