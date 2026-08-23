from fastapi.testclient import TestClient
from app.main import app, peer_benchmark, peer_outcomes, rca_case_store


def test_v39_version_and_peer_outcome_closed_loop():
    c=TestClient(app)
    assert c.get('/health').json()['version']=='4.9.0'
    a=peer_benchmark.assess({
      'current':{'asset_id':'A101','load_pct':84,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':12.0},
      'peers':[
        {'asset_id':'A102','load_pct':83,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':10.0},
        {'asset_id':'A103','load_pct':85,'ambient_temp':30,'product_type':'P1','operating_mode':'auto','specific_energy':10.1},
        {'asset_id':'A104','load_pct':82,'ambient_temp':28,'product_type':'P1','operating_mode':'auto','specific_energy':9.9}],
      'metric':'specific_energy'})
    case=rca_case_store.create({'question':'why','subject':{'entity':'Machine','reference':'A101'}},actor='test')
    case=rca_case_store.resolve(case['case_id'],{'confirmed_root_cause':'filter_restriction','action':'replace_filter'},actor='test')
    samples=[{'load_pct':83,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':x} for x in (10.0,10.1,9.9)]
    out=peer_outcomes.verify(a['assessment_id'],{'rca_case_id':case['case_id'],'post_maintenance_samples':samples,'actor':'test'})
    assert out['verified_success'] is True
    assert out['improvement_pct'] >= 15
    assert abs(out['deviation_vs_peer_after_pct']) <= 10


def test_v39_unresolved_rca_is_not_verified():
    a=peer_benchmark.assess({'current':{'asset_id':'A201','load_pct':84,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':12},'peers':[{'asset_id':'P1','load_pct':84,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':10},{'asset_id':'P2','load_pct':84,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':10.2},{'asset_id':'P3','load_pct':84,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':9.8}]})
    case=rca_case_store.create({'question':'why','subject':{'entity':'Machine','reference':'A201'}},actor='test')
    samples=[{'load_pct':84,'ambient_temp':29,'product_type':'P1','operating_mode':'auto','specific_energy':x} for x in (10,10.1,9.9)]
    out=peer_outcomes.verify(a['assessment_id'],{'rca_case_id':case['case_id'],'post_maintenance_samples':samples})
    assert out['improvement_target_met'] is True
    assert out['returned_to_peer_range'] is True
    assert out['rca_lifecycle_ready'] is False
    assert out['verified_success'] is False
