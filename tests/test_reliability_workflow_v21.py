from fastapi.testclient import TestClient
from app.main import app, repository, asset_registry, rca_case_store, cmms_candidates, reliability_service, fmea_store

client = TestClient(app)


def test_v21_health_version_and_asset_time_window():
    assert client.get('/health').json()['version'] == '3.3.0'
    aid='V21-ASSET-WINDOW'
    asset_registry.upsert_asset({'asset_id':aid,'name':'V21 Test','asset_type':'compressor'}, actor='test')
    fmea_store.create({'fmea_id':'V21-FMEA-WINDOW','asset':aid,'component':'Filter','failure_mode':'filter_restriction','cause_code':'filter_restriction','cause':'dust','effect':'energy rise','detection_method':'filter_dp','severity':8,'occurrence':5,'detectability':5,'recommended_action':'inspect filter','status':'approved'}, actor='test')
    # Existing reliability service owns history; assessments only provide source facts.
    reliability_service.assess({'asset':aid,'failure_mode':'filter_restriction','condition_indicators':[{'sensor':'filter_dp','score':80}], 'anomaly_score':60,'failure_history_score':40}, actor='test')
    r=client.get(f'/assets/{aid}/cockpit?days=7&health_limit=1000')
    assert r.status_code == 200
    data=r.json()
    assert data['time_window_days'] == 7
    assert isinstance(data['health_history'], list)


def test_v21_rca_workflow_and_close_guard():
    aid='V21-RCA-ASSET'
    asset_registry.upsert_asset({'asset_id':aid,'name':'RCA Asset','asset_type':'compressor'}, actor='test')
    case=rca_case_store.create({'question':'filter pressure abnormal','subject':{'entity':'Machine','reference':aid}}, actor='test')
    cid=case['case_id']
    workflow=client.get(f'/rca/cases/{cid}/workflow')
    assert workflow.status_code == 200
    assert workflow.json()['actions']['can_analyze'] is True
    # Cannot close before resolve.
    denied=client.post(f'/rca/cases/{cid}/close', json={'actor':'test'})
    assert denied.status_code == 400
    rca_case_store.update(cid, {'status':'resolved','confirmed_root_cause':'filter_restriction'}, actor='test', action='force_resolved_for_test')
    closed=client.post(f'/rca/cases/{cid}/close', json={'actor':'test','comment':'verified'})
    assert closed.status_code == 200
    assert closed.json()['status'] == 'closed'


def test_v21_workflow_aggregates_maintenance():
    aid='V21-MAINT-ASSET'
    asset_registry.upsert_asset({'asset_id':aid,'name':'Maintenance Asset'}, actor='test')
    case=rca_case_store.create({'question':'bearing risk','subject':{'entity':'Machine','reference':aid}}, actor='test')
    wo=cmms_candidates.create({'asset':aid,'failure_mode':'bearing_overheat','priority':'P2-high','recommended_action':'inspect bearing'}, actor='test')
    data=client.get(f"/rca/cases/{case['case_id']}/workflow").json()
    assert any(x.get('candidate_id') == wo.get('candidate_id') for x in data['maintenance'])
