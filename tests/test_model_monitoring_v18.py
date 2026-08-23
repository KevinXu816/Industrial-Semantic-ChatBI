from pathlib import Path
from fastapi.testclient import TestClient
from app.persistence import JsonRepository
from app.model_registry import PredictiveModelRegistry
from app.model_monitoring import ModelDatasetRegistry, ModelEvaluationService, ModelDeploymentManager, ModelMonitoringService


def test_offline_evaluation_and_champion_challenger(tmp_path):
    repo=JsonRepository(tmp_path); models=PredictiveModelRegistry(repo); datasets=ModelDatasetRegistry(repo)
    evals=ModelEvaluationService(repo,models,datasets); deploy=ModelDeploymentManager(repo,models)
    m1=models.register({"name":"temp-risk","version":"1","model_type":"rule","parameters":{"field":"temp","warn":60,"critical":80}}); models.approve(m1["model_id"])
    m2=models.register({"name":"temp-risk","version":"2","model_type":"rule","parameters":{"field":"temp","warn":55,"critical":75}}); models.approve(m2["model_id"])
    d=datasets.register({"name":"bearing-validation","task":"regression","records":[{"inputs":{"temp":60},"expected":0},{"inputs":{"temp":70},"expected":50},{"inputs":{"temp":80},"expected":100}]})
    ev=evals.evaluate(m1["model_id"],d["dataset_id"])
    assert ev["metrics"]["mae"] == 0
    deploy.set_role("bearing_risk",m1["model_id"],"champion"); deploy.set_role("bearing_risk",m2["model_id"],"challenger")
    row=deploy.promote("bearing_risk")
    assert row["champion"]==m2["model_id"] and row["challenger"]==m1["model_id"]
    rb=deploy.rollback("bearing_risk")
    assert rb["champion"]==m1["model_id"]


def test_feature_drift_monitoring(tmp_path):
    repo=JsonRepository(tmp_path); mon=ModelMonitoringService(repo)
    mon.set_baseline("m1",{"vibration_rms":{"mean":1.0,"std":0.1},"temp":{"mean":60,"std":2}})
    stable=mon.monitor("m1",{"vibration_rms":{"mean":1.1},"temp":{"mean":61}})
    drift=mon.monitor("m1",{"vibration_rms":{"mean":1.5},"temp":{"mean":61}})
    assert stable["status"]=="stable"
    assert drift["status"]=="drift"
    assert mon.summary()["drift"]==1


def test_v18_api_and_ui_version():
    from app.main import app
    c=TestClient(app)
    assert c.get('/health').json()['version']=='4.9.0'
    html=c.get('/').text
    assert 'sidebar-version' in html and 'topbar-version' in html and '模型运维' in html
