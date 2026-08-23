from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)

def test_v22_version_and_binding_governance():
    assert client.get('/health').json()['version']=='4.9.0'
    payload={"name":"asset-import-v22","target":"asset","source_type":"api","mappings":{"asset_id":"id","name":"label","asset_type":"type"}}
    row=client.post('/data-bindings',json=payload).json(); bid=row['binding_id']
    preview=client.post(f'/data-bindings/{bid}/preview',json={"records":[{"id":"V22-A1","label":"Pump A1","type":"pump"}]}).json()
    assert preview['records'][0]['asset_id']=='V22-A1'
    assert client.post(f'/data-bindings/{bid}/run',json={"records":[{"id":"V22-A1"}]}).status_code==400
    assert client.post(f'/data-bindings/{bid}/approve',json={}).status_code==200
    run=client.post(f'/data-bindings/{bid}/run',json={"records":[{"id":"V22-A1","label":"Pump A1","type":"pump"}]}).json()
    assert run['succeeded']==1
    assert client.get('/assets/V22-A1').status_code==200

def test_binding_contract_has_industrial_sources():
    c=client.get('/data-bindings/contract').json()
    assert 'influxdb' in c['source_types'] and 'historian' in c['source_types']
    assert 'condition_series' in c['targets']
