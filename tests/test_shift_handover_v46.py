import uuid
from fastapi.testclient import TestClient
from app.main import app


def test_v46_shift_logbook_handover_and_acknowledgement():
    c=TestClient(app)
    assert c.get('/health').json()['version']=='4.9.0'
    suffix=uuid.uuid4().hex[:8]
    shift_id=f'SHIFT-V46-{suffix}'
    handover_id=f'HO-V46-{suffix}'
    asset_id=f'A101-{suffix}'
    s=c.post('/operations/shifts',json={'shift_id':shift_id,'name':'白班','site_id':'F01','start_hour':0,'duration_hours':24,'actor':'tester'})
    assert s.status_code==200
    log=c.post('/operations/logbook',json={'site_id':'F01','shift_id':shift_id,'category':'risk','severity':'warning','asset_id':asset_id,'body':'filter_dp 持续上升','actor':'engineer-f01'})
    assert log.status_code==200
    c.post(f'/collaboration/resources/asset/{asset_id}/assign',json={'assignee':'engineer-f01','actor':'tester','title':'风险跟踪','asset_id':asset_id})
    h=c.post('/operations/handovers',json={'handover_id':handover_id,'site_id':'F01','shift_id':shift_id,'outgoing_principal':'engineer-f01','incoming_principal':'engineer-f02','notes':'继续关注','actor':'engineer-f01'})
    assert h.status_code==200
    data=h.json()
    assert data['status']=='pending_ack' and data['outgoing_ack'] is True and data['incoming_ack'] is False
    assert any(x['resource_id']==asset_id for x in data['open_items'])
    bad=c.post(f'/operations/handovers/{handover_id}/acknowledge',json={'principal_id':'other-user','actor':'other-user'})
    assert bad.status_code==400
    ack=c.post(f'/operations/handovers/{handover_id}/acknowledge',json={'principal_id':'engineer-f02','actor':'engineer-f02','note':'已接班'})
    assert ack.status_code==200 and ack.json()['status']=='accepted' and ack.json()['incoming_ack'] is True


def test_v46_handover_dashboard_contract():
    c=TestClient(app)
    d=c.get('/operations/handover-dashboard?site_id=F01')
    assert d.status_code==200
    body=d.json()
    assert 'summary' in body and 'priority_items' in body and 'recent_logs' in body
