from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.main import app, repository


def test_v45_sla_escalation_oncall_and_notification_contract():
    c=TestClient(app)
    assert c.get('/health').json()['version']=='4.9.0'
    rid='RCA-V45-TEST'
    c.post(f'/collaboration/resources/rca/{rid}/assign',json={'assignee':'engineer-f01','actor':'tester','title':'V4.5 SLA test'})
    past=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat().replace('+00:00','Z')
    c.post(f'/collaboration/resources/rca/{rid}/sla',json={'due_at':past,'actor':'tester'})
    p=c.post('/collaboration/sla-policies',json={'policy_id':'SLA-V45','name':'RCA critical','resource_type':'rca','sla_hours':24,'escalate_to':'manager-f01','channels':['in_app','email'],'actor':'tester'})
    assert p.status_code==200
    r=c.post('/collaboration/escalations/evaluate',json={'actor':'tester'})
    assert r.status_code==200 and r.json()['created']>=1
    es=c.get('/collaboration/escalations?status=open').json()['items']
    assert any(x['resource_id']==rid and x['recipient']=='manager-f01' for x in es)
    ns=c.get('/collaboration/notifications').json()['items']
    assert any(x['resource']['id']==rid and x['delivery_status']=='intent_created' for x in ns)
    contract=c.get('/collaboration/notifications/contract').json()
    assert {'email','teams','slack','webhook'}.issubset(set(contract['channels']))


def test_v45_oncall_rotation_contract():
    c=TestClient(app)
    r=c.post('/collaboration/oncall',json={'schedule_id':'ONCALL-V45','name':'F01','principals':['engineer-f01','planner-f01'],'rotation_hours':8,'actor':'tester'})
    assert r.status_code==200 and r.json()['current_oncall'] in {'engineer-f01','planner-f01'}
