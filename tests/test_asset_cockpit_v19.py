from pathlib import Path
import tempfile
from app.persistence import JsonRepository
from app.asset_reliability import AssetRegistry, AssetReliabilityCockpitService
from app.fmea import FMEAStore
from app.reliability_intelligence import FailureSensorMappingStore, ReliabilityIntelligenceService
from app.rca_cases import RCACaseStore
from app.predictive_maintenance import CMMSWorkOrderCandidateStore, TrendRULAdapter
from app.model_registry import PredictiveModelRegistry
from app.model_monitoring import ModelDeploymentManager


def _services():
    td=tempfile.TemporaryDirectory(); repo=JsonRepository(Path(td.name))
    assets=AssetRegistry(repo); fmea=FMEAStore(repo); mappings=FailureSensorMappingStore(repo)
    rel=ReliabilityIntelligenceService(repo,fmea,mappings); rca=RCACaseStore(repo); cmms=CMMSWorkOrderCandidateStore(repo)
    models=PredictiveModelRegistry(repo); deps=ModelDeploymentManager(repo,models)
    cockpit=AssetReliabilityCockpitService(assets,rel,fmea,rca,cmms,deps,models,TrendRULAdapter())
    return td,repo,assets,fmea,rel,rca,cmms,models,deps,cockpit


def test_asset_hierarchy_components_and_sensors():
    td,repo,assets,*_= _services()
    try:
        assets.upsert_asset({"asset_id":"F01","name":"Factory","asset_type":"factory"})
        assets.upsert_asset({"asset_id":"A101","name":"Compressor","asset_type":"compressor","parent_asset_id":"F01"})
        comp=assets.upsert_component("A101",{"name":"Drive End Bearing"})
        sensor=assets.bind_sensor("A101",{"sensor":"bearing_temp","component_id":comp["component_id"],"unit":"degC"})
        tree=assets.hierarchy("F01")
        assert tree["roots"][0]["children"][0]["asset_id"]=="A101"
        assert sensor["component_id"]==comp["component_id"]
    finally: td.cleanup()


def test_cockpit_aggregates_domain_sources_without_copying():
    td,repo,assets,fmea,rel,rca,cmms,models,deps,cockpit = _services()
    try:
        assets.upsert_asset({"asset_id":"A101","name":"Compressor A101","asset_type":"compressor"})
        f=fmea.create({"fmea_id":"FMEA-A101","asset":"A101","component":"Air Filter","failure_mode":"filter_restriction","severity":8,"occurrence":5,"detectability":5,"cause":"dust","effect":"energy rises","detection_method":"dp","recommended_action":"replace filter"})
        fmea.approve(f["fmea_id"])
        rel.assess({"asset":"A101","failure_mode":"filter_restriction","condition_indicators":[{"sensor":"filter_dp","score":80}],"anomaly_score":70,"failure_history_score":50})
        case=rca.create({"subject":{"entity":"Machine","reference":"A101"},"question":"why"})
        cmms.create({"asset":"A101","failure_mode":"filter_restriction","priority":"P2-high","recommended_action":"inspect"})
        m=models.register({"name":"filter-risk","version":"1.0","model_type":"rule","parameters":{"field":"value","warn":1,"critical":2}}); models.approve(m["model_id"])
        deps.set_role("filter_restriction",m["model_id"],"champion")
        out=cockpit.cockpit("A101")
        assert out["current_health_score"] is not None
        assert out["summary"]["open_rca_cases"]==1
        assert out["summary"]["pending_work_orders"]==1
        assert out["models"][0]["champion"]==m["model_id"]
    finally: td.cleanup()


def test_fleet_ranks_highest_dynamic_risk_first():
    td,repo,assets,fmea,rel,rca,cmms,models,deps,cockpit = _services()
    try:
        for aid,sev in [("A1",5),("A2",9)]:
            assets.upsert_asset({"asset_id":aid,"status":"active"})
            f=fmea.create({"fmea_id":"F-"+aid,"asset":aid,"component":"C","failure_mode":"fm_"+aid,"severity":sev,"occurrence":7,"detectability":7,"cause":"c","effect":"e","detection_method":"d","recommended_action":"a"})
            fmea.approve(f["fmea_id"])
            rel.assess({"asset":aid,"condition_indicators":[{"sensor":"x","score":80 if aid=="A2" else 20}],"anomaly_score":50})
        fleet=cockpit.fleet()
        assert fleet["assets"][0]["asset_id"]=="A2"
    finally: td.cleanup()
