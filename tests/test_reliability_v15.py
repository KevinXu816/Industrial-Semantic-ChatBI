from app.persistence import JsonRepository
from app.fmea import FMEAStore
from app.reliability_intelligence import FailureSensorMappingStore, ReliabilityIntelligenceService


def _fmea(store):
    return store.create({
        'fmea_id':'FMEA-BRG-150','asset':'A101','component':'Bearing','failure_mode':'bearing_overheat','cause_code':'bearing_overheat',
        'severity':8,'occurrence':6,'detectability':5,'status':'approved','recommended_action':'inspect bearing'
    })


def test_dynamic_risk_and_priority(tmp_path):
    repo=JsonRepository(tmp_path/'repo'); f=FMEAStore(repo); row=_fmea(f); mappings=FailureSensorMappingStore(repo)
    mappings.upsert({'failure_mode':'bearing_overheat','sensor':'bearing_temp','weight':2})
    svc=ReliabilityIntelligenceService(repo,f,mappings)
    out=svc.assess({'asset':'A101','failure_mode':'bearing_overheat','condition_indicators':[{'sensor':'bearing_temp','score':90}], 'anomaly_score':80,'failure_history_score':60})
    risk=out['failure_modes'][0]
    assert risk['dynamic_risk_score'] > 60
    assert risk['condition_indicators'][0]['mapped'] is True
    assert risk['maintenance_priority'] in {'P1-critical','P2-high'}
    assert out['asset_health_score'] == round(100-risk['dynamic_risk_score'],2)


def test_threshold_condition_indicator_and_health_history(tmp_path):
    repo=JsonRepository(tmp_path/'repo'); f=FMEAStore(repo); _fmea(f); svc=ReliabilityIntelligenceService(repo,f,FailureSensorMappingStore(repo))
    a=svc.assess({'asset':'A101','condition_indicators':[{'sensor':'temp','value':85,'warn':70,'critical':90}], 'anomaly_score':50})
    b=svc.assess({'asset':'A101','condition_indicators':[{'sensor':'temp','value':90,'warn':70,'critical':90}], 'anomaly_score':80})
    h=svc.asset_health('A101')
    assert h['assessments']==2
    assert h['latest']['assessment_id']==b['assessment_id']
    assert h['health_trend'] in {'deteriorating','stable'}


def test_risk_ranking_keeps_latest_per_asset(tmp_path):
    repo=JsonRepository(tmp_path/'repo'); f=FMEAStore(repo)
    _fmea(f)
    f.create({'fmea_id':'FMEA-X','asset':'A102','component':'Motor','failure_mode':'motor_overheat','severity':9,'occurrence':7,'detectability':6,'status':'approved'})
    svc=ReliabilityIntelligenceService(repo,f,FailureSensorMappingStore(repo))
    svc.assess({'asset':'A101','condition_score':20})
    svc.assess({'asset':'A102','condition_score':90,'anomaly_score':90,'failure_history_score':80})
    ranked=svc.risk_ranking()
    assert ranked[0]['asset']=='A102'
