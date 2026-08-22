from app.temporal_causality import TemporalCausalityEngine
from app.sensor_correlation import SensorCorrelationEngine
from app.operating_baseline import OperatingBaselineEngine
from app.knowledge import KnowledgeRetriever
from app.rca import RCAEngine
from app.rca_feedback import RCAFeedbackStore


def test_temporal_chain_orders_events_around_anchor():
    out = TemporalCausalityEngine().build_chain("2026-08-22T10:00:00+00:00", [
        {"type":"sensor", "label":"DP rise", "timestamp":"2026-08-22T09:30:00+00:00"},
        {"type":"alarm", "label":"High DP", "timestamp":"2026-08-22T10:05:00+00:00"},
    ], before_minutes=60, after_minutes=15)
    assert out["status"] == "ok"
    assert out["chain"][0]["temporal_relation"] == "PRECEDES"
    assert out["chain"][1]["temporal_relation"] == "FOLLOWS"
    assert out["chain"][0]["lag_minutes"] == -30.0


def test_sensor_lag_correlation_finds_positive_lag():
    driver = [{"value": v} for v in [1,2,3,4,5,6,7,8]]
    target = [{"value": v} for v in [0,0,1,2,3,4,5,6]]
    out = SensorCorrelationEngine().lag_correlation(driver, target, max_lag_points=3)
    assert out["status"] == "ok"
    assert abs(out["correlation"]) > 0.9
    assert out["best_lag_points"] > 0


def test_operating_baseline_detects_deviation():
    out = OperatingBaselineEngine().compare([{"value":12},{"value":13}], [{"value":10},{"value":10}])
    assert out["status"] == "ok"
    assert out["deviation_pct"] == 25.0


def test_knowledge_has_versioned_citation():
    hit = KnowledgeRetriever().search("filter pressure", top_k=1)[0]
    assert hit["citation"].startswith(hit["id"] + "@")
    assert hit["knowledge_digest"]
    assert hit["provenance"].startswith("knowledge:")


def test_rca_v09_combines_temporal_sensor_baseline():
    data = {
      "metric": {"change_pct": 19.0},
      "energy_trend": [{"day":f"D{i}","energy_kwh":v} for i,v in enumerate([10,10,11,18,19,20,21])],
      "anomaly_time":"2026-08-22T10:00:00+00:00",
      "alarms":[{"alarm_name":"Filter Differential Pressure High","timestamp":"2026-08-22T09:50:00+00:00"}],
      "work_orders":[{"fault_description":"filter pressure rising","timestamp":"2026-08-22T09:20:00+00:00"}],
      "sensor_series":[{"name":"filter_dp","rows":[{"value":v} for v in [1,2,3,4,5,6,7]]}],
      "target_series":[{"value":v} for v in [0,1,2,3,4,5,6]],
      "current_condition":[{"value":12},{"value":13}],
      "baseline_condition":[{"value":10},{"value":10}],
    }
    out = RCAEngine().analyze(data, "filter pressure energy")
    assert out["provenance_version"] == "0.9"
    assert out["temporal_causality"]["chain"]
    assert out["sensor_correlations"]
    assert out["operating_baseline"]["deviation_pct"] == 25.0
    assert out["hypotheses"][0]["cause_code"] == "filter_restriction"


def test_feedback_store_append_only(tmp_path):
    store = RCAFeedbackStore(tmp_path / "feedback.json")
    rec = store.add({"case_id":"RCA-1", "accepted":False, "correct_cause":"air_leak"})
    assert rec["id"]
    assert store.list()[0]["correct_cause"] == "air_leak"
