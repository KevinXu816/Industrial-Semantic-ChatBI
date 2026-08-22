from app.asset_reliability import AssetRegistry, AssetReliabilityCockpitService
from app.product_workspace import ProductWorkspaceService
from app.persistence import JsonRepository
from app.fmea import FMEAStore
from app.reliability_intelligence import FailureSensorMappingStore, ReliabilityIntelligenceService
from app.rca_cases import RCACaseStore
from app.predictive_maintenance import CMMSWorkOrderCandidateStore, TrendRULAdapter
from app.model_registry import PredictiveModelRegistry
from app.model_monitoring import ModelDeploymentManager


def test_v20_workspace_and_cockpit_timeline(tmp_path):
    repo=JsonRepository(tmp_path/'repo.json')
    assets=AssetRegistry(repo); fmea=FMEAStore(repo); maps=FailureSensorMappingStore(repo); rel=ReliabilityIntelligenceService(repo,fmea,maps)
    rca=RCACaseStore(repo); cmms=CMMSWorkOrderCandidateStore(repo); models=PredictiveModelRegistry(repo); deps=ModelDeploymentManager(repo,models)
    assets.upsert_asset({'asset_id':'A1','name':'Compressor A1','asset_type':'compressor'})
    fmea.create({'fmea_id':'F1','asset':'A1','component':'bearing','failure_mode':'bearing_overheat','severity':8,'occurrence':5,'detectability':5,'status':'approved'})
    rel.assess({'asset':'A1','condition_score':80,'anomaly_score':60,'failure_history_score':50})
    rca.create({'question':'why hot','subject':{'entity':'Asset','reference':'A1'}})
    cmms.create({'asset':'A1','priority':'P2-high','recommended_action':'inspect bearing'})
    cockpit=AssetReliabilityCockpitService(assets,rel,fmea,rca,cmms,deps,models,TrendRULAdapter())
    view=cockpit.cockpit('A1')
    assert view['timeline']
    assert view['health_history']
    assert view['failure_drilldown'][0]['failure_mode']=='bearing_overheat'
    home=ProductWorkspaceService(cockpit,rca,cmms).home('maintenance_planner')
    assert home['summary']['pending_work_orders']==1
    assert home['priorities'][0]['kind']=='work_order'
