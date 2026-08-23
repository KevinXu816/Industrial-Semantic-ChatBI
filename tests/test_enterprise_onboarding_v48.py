from fastapi.testclient import TestClient
from app.main import app
import io
import openpyxl

client=TestClient(app)

def test_contract_and_excel_two_step():
    assert client.get('/health').json()['version']=='4.9.0'
    c=client.get('/onboarding/contract').json()
    assert c['steps']==2 and c['security']['api_ssrf_guard'] is True
    wb=openpyxl.Workbook(); ws=wb.active; ws.title='Assets'; ws.append(['device_id','device_name','device_type']); ws.append(['A4801','Pump 4801','pump'])
    b=io.BytesIO(); wb.save(b)
    r=client.post('/onboarding/excel/discover', files={'file':('assets.xlsx',b.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}, data={'target':'asset'})
    assert r.status_code==200, r.text
    d=r.json(); assert d['recommended_mapping']['asset_id']=='device_id'; assert d['readiness_score']==100
    r=client.post(f"/onboarding/{d['session_id']}/confirm",json={'name':'V48 Excel Assets','target':'asset','mappings':d['recommended_mapping']})
    assert r.status_code==200, r.text
    out=r.json(); assert out['steps_completed']==2 and out['binding']['status']=='approved'

def test_api_sample_and_private_guard():
    r=client.post('/onboarding/api/discover',json={'url':'https://api.example.com/assets','target':'asset','sample_response':[{'equipment_code':'A48','equipment_name':'Compressor'}]})
    assert r.status_code==200, r.text
    assert r.json()['recommended_mapping']['asset_id']=='equipment_code'
    r=client.post('/onboarding/api/discover',json={'url':'http://127.0.0.1:8000/private','target':'asset','sample_response':[{'asset_id':'A'}]})
    assert r.status_code==400

def test_edge_mode_for_private_enterprise_sources():
    r=client.post('/onboarding/edge/discover',json={'source_type':'influxdb','target':'condition_series','sample_columns':['device_id','tag_name','value','timestamp']})
    assert r.status_code==200
    d=r.json(); assert d['connectivity']=='edge_agent_outbound'; assert d['recommended_mapping']['asset_id']=='device_id'; assert d['recommended_mapping']['sensor']=='tag_name'
