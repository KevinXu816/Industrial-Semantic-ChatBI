from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)

def test_v43_dashboard_and_action_center_contract():
    assert client.get('/health').json()['version']=='4.9.0'
    d=client.get('/workspace/dashboard?principal_id=v43-user&role=reliability_engineer')
    assert d.status_code==200
    body=d.json()
    assert 'focus' in body['available_widgets']
    assert body['widgets']
    u=client.post('/workspace/dashboard',json={'principal_id':'v43-user','role':'reliability_engineer','widgets':['focus','inbox','quick_actions']})
    assert u.status_code==200
    assert u.json()['widgets']==['focus','inbox','quick_actions']
    a=client.get('/workspace/action-center?principal_id=v43-user&role=reliability_engineer')
    assert a.status_code==200
    assert a.json()['semantics'].startswith('Guided orchestration')

def test_v43_pin_action_and_ui_i18n_contract():
    q=client.get('/workspace/quick-actions').json()['actions']
    assert q
    client.post('/workspace/preferences',json={'principal_id':'v43-pin','pinned_actions':[]})
    r=client.post('/workspace/preferences/pin-action',json={'principal_id':'v43-pin','action_id':q[0]['id']})
    assert r.status_code==200
    assert q[0]['id'] in r.json()['pinned_actions']
    html=client.get('/').text
    for token in ['dashboard-layout-chips','action-center-list','loadDashboardLayout','loadActionCenter']:
        assert token in html
