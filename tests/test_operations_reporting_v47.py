import uuid
from fastapi.testclient import TestClient
from app.main import app


def test_v47_operations_shift_report_and_markdown():
    c=TestClient(app)
    assert c.get('/health').json()['version']=='4.9.0'
    suffix=uuid.uuid4().hex[:8]
    shift=f'SHIFT-V47-{suffix}'
    asset=f'A47-{suffix}'
    c.post('/operations/shifts',json={'shift_id':shift,'name':'V47 Shift','site_id':'F47','start_hour':0,'duration_hours':24,'actor':'tester'})
    c.post('/operations/logbook',json={'site_id':'F47','shift_id':shift,'category':'risk','asset_id':asset,'body':'风险观察','actor':'tester'})
    c.post(f'/collaboration/resources/asset/{asset}/assign',json={'assignee':'eng-v47','actor':'tester','title':'风险事项','asset_id':asset})
    c.post(f'/collaboration/resources/asset/{asset}/sla',json={'sla_hours':8,'actor':'tester'})
    r=c.post('/operations/reports/generate',json={'kind':'shift','site_id':'F47','shift_id':shift,'actor':'tester'})
    assert r.status_code==200
    body=r.json()
    assert body['kind']=='shift'
    assert body['summary']['new_logs']>=1
    assert 'risk_top5' in body and 'next_shift_focus' in body
    md=c.get(f"/operations/reports/{body['report_id']}/markdown")
    assert md.status_code==200 and '工业语义智能平台运营班报' in md.text


def test_v47_daily_report_contract_and_ui_i18n():
    c=TestClient(app)
    r=c.post('/operations/reports/generate',json={'kind':'daily','site_id':'F01','actor':'tester'})
    assert r.status_code==200 and r.json()['kind']=='daily'
    assert c.get('/operations/reports?kind=daily').status_code==200
    html=c.get('/').text
    assert 'panel-reports' in html and '运营班报' in html and 'generateOperationsReport' in html
    for lang in ('zh-CN','en-US','de-DE','ja-JP'):
        d=c.get(f'/static/i18n/{lang}.json').json()
        assert '运营班报' in d['phrases']
