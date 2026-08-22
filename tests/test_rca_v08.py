from app.timeseries_analytics import TimeSeriesAnalyticsEngine
from app.event_correlation import EventCorrelationEngine
from app.knowledge import KnowledgeRetriever
from app.hypothesis_ranker import HypothesisRanker
from app.rca import RCAEngine
from app.doris_explain import DorisExplainCostAdapter
from app.evidence_graph import EvidenceGraphBuilder
from app.semantic import SemanticRegistry
from app.planner import QueryPlanner
from app.models import SemanticIntent, SemanticSubject, SemanticTimeRange


def test_timeseries_detects_upward_change():
    rows = [{"ts": f"T{i}", "value": v} for i, v in enumerate([10, 10, 11, 18, 19, 20, 21])]
    out = TimeSeriesAnalyticsEngine().analyze(rows, "value", "ts")
    assert out["status"] == "ok"
    assert out["trend_pct"] > 5
    assert any(x["type"] == "trend" for x in out["signals"])


def test_event_correlation_matches_filter_pressure():
    analytics = {"trend_pct": 19.0, "anomalies": [], "change_point": {"score": 2.0}}
    out = EventCorrelationEngine().correlate(
        analytics,
        [{"alarm_name": "Filter Differential Pressure High"}],
        [{"fault_description": "filter pressure rising"}],
    )
    assert out["candidates"][0]["cause_code"] == "filter_restriction"
    assert out["candidates"][0]["score"] > 0.5


def test_knowledge_retrieval_returns_provenance():
    rows = KnowledgeRetriever().search("filter differential pressure energy", top_k=3)
    assert rows
    assert rows[0]["provenance"].startswith("knowledge:")


def test_rca_pipeline_ranks_hypothesis_and_provenance():
    data = {
        "execution_mode": "mock",
        "metric": {"change_pct": 19.23},
        "energy_trend": [
            {"day": "D-6", "energy_kwh": 100}, {"day": "D-5", "energy_kwh": 101},
            {"day": "D-4", "energy_kwh": 101}, {"day": "D-3", "energy_kwh": 120},
            {"day": "D-2", "energy_kwh": 122}, {"day": "D-1", "energy_kwh": 124},
            {"day": "D0", "energy_kwh": 125},
        ],
        "alarms": [{"alarm_name": "Filter Differential Pressure High", "severity": "warning"}],
        "work_orders": [{"fault_description": "Air filter pressure rising", "maintenance_action": "replacement deferred"}],
    }
    out = RCAEngine().analyze(data, question="为什么空压机能耗升高 filter pressure")
    assert out["hypotheses"]
    assert out["hypotheses"][0]["cause_code"] == "filter_restriction"
    assert out["hypotheses"][0]["confidence"] >= 0.6
    assert any(e.get("provenance") for e in out["hypotheses"][0]["evidence"] if isinstance(e, dict))


def test_evidence_graph_has_provenance_nodes():
    registry = SemanticRegistry()
    plan = QueryPlanner(registry).build(SemanticIntent(
        raw_question="A101最近7天能耗",
        subject=SemanticSubject(entity="Machine", reference="A101"),
        metrics=["energy_consumption"],
        time_range=SemanticTimeRange(value=7, unit="day"),
    ))
    rca = {"hypotheses": [{
        "cause": "过滤器堵塞", "confidence": 0.8,
        "evidence": [{"type": "alarm", "statement": "压差高", "provenance": "AlarmEvent"}],
        "recommended_checks": ["检查过滤器"],
    }], "analytics": {"signals": [{"type": "trend", "direction": "up", "magnitude_pct": 12}]}, "knowledge_hits": []}
    graph = EvidenceGraphBuilder().build(plan, {}, rca)
    types = {n["type"] for n in graph["nodes"]}
    relations = {e["relation"] for e in graph["edges"]}
    assert "provenance" in types
    assert "analytic_signal" in types
    assert "PRODUCED" in relations


def test_doris_explain_parser_and_logical_estimate():
    adapter = DorisExplainCostAdapter()
    parsed = adapter.parse(["OlapScanNode cardinality=200000", "HASH JOIN", "VOlapScanNode rows=50000"])
    assert parsed["scan_nodes"] >= 2
    assert parsed["join_nodes"] >= 1
    assert parsed["max_cardinality"] == 200000


def test_query_cache_isolated_by_governance_context(tmp_path, monkeypatch):
    import app.cache_audit as ca
    monkeypatch.setattr(ca, "CACHE_FILE", tmp_path / "cache.json")
    cache = ca.QueryCache(ttl_seconds=300)
    q = "F01工厂最近7天能耗"
    cache.set(q, {"factory": "F01"}, context={"roles": ["analyst"], "attributes": {"factory_id": "F01"}})
    assert cache.get(q, context={"roles": ["analyst"], "attributes": {"factory_id": "F01"}}) == {"factory": "F01"}
    assert cache.get(q, context={"roles": ["analyst"], "attributes": {"factory_id": "F02"}}) is None
