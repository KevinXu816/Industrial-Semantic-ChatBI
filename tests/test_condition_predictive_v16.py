import tempfile
from app.persistence import JsonRepository
from app.condition_analytics import ConditionIndicatorDefinitionStore, ConditionBaselineStore, ConditionAnalyticsService, TimeSeriesFeatureEngine
from app.predictive_maintenance import TrendRULAdapter, MaintenanceDecisionService, CMMSWorkOrderCandidateStore


def repo():
    return JsonRepository(tempfile.mkdtemp())


def test_feature_engine_rms_kurtosis_and_rolling():
    f=TimeSeriesFeatureEngine.features([1,2,3,4])
    assert f["mean"] == 2.5
    assert f["rms"] > f["mean"]
    assert len(TimeSeriesFeatureEngine.rolling([1,2,3,4], 2, "mean")) == 3


def test_condition_definition_baseline_analysis():
    r=repo(); defs=ConditionIndicatorDefinitionStore(r); bases=ConditionBaselineStore(r)
    d=defs.upsert({"indicator":"bearing_temp_mean","sensor":"bearing_temp","feature":"mean","baseline_sigma":2})
    bases.upsert("A101","bearing_temp_mean",[60,61,59,60])
    out=ConditionAnalyticsService(defs,bases).analyze({"asset":"A101","series":{"bearing_temp":[79,80,82]}})
    assert out["condition_indicators"]
    assert out["condition_indicators"][0]["score"] > 0
    assert out["condition_indicators"][0]["definition_id"] == d["definition_id"]


def test_trend_rul_and_maintenance_decision():
    rul=TrendRULAdapter().estimate({"health_scores":[80,70,60,50],"failure_threshold":20,"interval_hours":24})
    assert rul["estimated_rul_hours"] is not None
    decision=MaintenanceDecisionService().recommend({"asset":"A101","top_risk":{"dynamic_risk_score":70,"maintenance_priority":"P2-high","failure_mode":"bearing"}},rul)
    assert decision["priority"] in {"P1-critical","P2-high"}


def test_cmms_candidate_lifecycle_and_contract():
    store=CMMSWorkOrderCandidateStore(repo())
    row=store.create({"asset":"A101","priority":"P2-high","failure_mode":"bearing","recommended_action":"inspect bearing"})
    row=store.transition(row["candidate_id"],"approved")
    row=store.transition(row["candidate_id"],"dispatched",external_id="CMMS-123")
    contract=store.integration_contract(row)
    assert contract["operation"] == "create_work_order"
    assert contract["payload"]["source_reference"] == row["candidate_id"]


def test_v16_api_end_to_end(monkeypatch, tmp_path):
    # app uses its configured repository; use unique IDs to keep the test isolated.
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    assert client.get('/health').json()['version']=='2.9.0'
    ind='V16_TEMP_MEAN_TEST'
    r=client.post('/condition/definitions',json={"definition_id":ind,"indicator":ind,"sensor":"v16_temp","feature":"mean","warn":70,"critical":90})
    assert r.status_code==200
    b=client.post('/condition/baselines',json={"asset":"V16-A","indicator":ind,"values":[60,61,59,60]})
    assert b.status_code==200
    a=client.post('/condition/analyze',json={"asset":"V16-A","definition_ids":[ind],"series":{"v16_temp":[80,82,84]}})
    assert a.status_code==200 and a.json()['condition_indicators'][0]['score']>0
    rul=client.post('/predictive/rul',json={"health_scores":[80,70,60,50],"failure_threshold":20,"interval_hours":24})
    assert rul.status_code==200 and rul.json()['estimated_rul_hours'] is not None
    c=client.post('/cmms/work-order-candidates',json={"asset":"V16-A","priority":"P2-high","failure_mode":"bearing","recommended_action":"inspect"})
    assert c.status_code==200
    cid=c.json()['candidate_id']
    contract=client.get(f'/cmms/work-order-candidates/{cid}/contract')
    assert contract.status_code==200 and contract.json()['operation']=='create_work_order'
