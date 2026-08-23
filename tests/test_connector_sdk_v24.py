from fastapi.testclient import TestClient
from app.persistence import JsonRepository
from app.data_binding import DataBindingStore
from app.integration_runtime import IntegrationRuntimeService
from app.connector_sdk import ConnectorRegistry, ConnectorBatchProcessor
from app.edge_agent import EdgeAgentRegistry
from app.asset_reliability import AssetRegistry
from app.predictive_maintenance import CMMSWorkOrderCandidateStore


def build(tmp_path):
    repo=JsonRepository(tmp_path)
    bindings=DataBindingStore(repo)
    runtime=IntegrationRuntimeService(repo,bindings)
    agents=EdgeAgentRegistry(repo)
    connectors=ConnectorRegistry(repo,bindings)
    processor=ConnectorBatchProcessor(connectors,runtime,agents)
    assets=AssetRegistry(repo)
    cmms=CMMSWorkOrderCandidateStore(repo)
    b=bindings.upsert({"name":"edge-asset-sync","target":"asset","source_type":"api","mappings":{"asset_id":"id","name":"name"}})
    bindings.approve(b["binding_id"])
    c=connectors.upsert({"name":"plant-edge-jdbc","connector_type":"jdbc","binding_id":b["binding_id"]})
    return repo,bindings,runtime,agents,connectors,processor,assets,cmms,b,c


def test_connector_approval_batch_idempotency_and_agent(tmp_path):
    repo,bindings,runtime,agents,connectors,processor,assets,cmms,b,c=build(tmp_path)
    try:
        processor.submit({"batch_id":"B1","connector_id":c["connector_id"],"binding_id":b["binding_id"],"records":[]},{"asset_registry":assets,"cmms_candidates":cmms})
        assert False
    except ValueError as exc:
        assert "approved connectors" in str(exc)
    connectors.approve(c["connector_id"])
    a=agents.register({"name":"edge-tokyo-01","site":"F01","capabilities":["jdbc"]})
    agents.heartbeat(a["agent_id"],{"version":"1.0.0","diagnostics":{"cpu_pct":12}})
    payload={"batch_id":"B1","connector_id":c["connector_id"],"binding_id":b["binding_id"],"agent_id":a["agent_id"],"cursor":"101","records":[{"id":"A1","name":"Pump"}],"diagnostics":{"fetch_ms":12}}
    out=processor.submit(payload,{"asset_registry":assets,"cmms_candidates":cmms})
    assert out["succeeded"]==1 and out["duplicate"] is False
    assert assets.get_asset("A1")["name"]=="Pump"
    dup=processor.submit(payload,{"asset_registry":assets,"cmms_candidates":cmms})
    assert dup["duplicate"] is True
    assert connectors.get(c["connector_id"])["last_cursor"]=="101"


def test_connector_binding_mismatch_is_blocked(tmp_path):
    repo,bindings,runtime,agents,connectors,processor,assets,cmms,b,c=build(tmp_path)
    connectors.approve(c["connector_id"])
    try:
        processor.submit({"batch_id":"B2","connector_id":c["connector_id"],"binding_id":"other","records":[]},{"asset_registry":assets,"cmms_candidates":cmms})
        assert False
    except ValueError as exc:
        assert "does not match" in str(exc)


def test_v24_api_contract():
    from app.main import app
    client=TestClient(app)
    assert client.get('/health').json()['version']=='4.9.0'
    contract=client.get('/connectors/contract')
    assert contract.status_code==200
    assert 'influxdb' in contract.json()['connector']['connector_types']
