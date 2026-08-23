from fastapi.testclient import TestClient
from app.persistence import JsonRepository
from app.enterprise_identity import EnterpriseIdentityStore, EnterpriseScopeEngine, AccessDenied
from app.asset_reliability import AssetRegistry
from app.data_binding import DataBindingStore
from app.connector_sdk import ConnectorRegistry, ConnectorBatchProcessor
from app.edge_agent import EdgeAgentRegistry
from app.integration_runtime import IntegrationRuntimeService
from app.predictive_maintenance import CMMSWorkOrderCandidateStore


def test_tenant_site_asset_scope_and_audit(tmp_path):
    repo=JsonRepository(tmp_path)
    ids=EnterpriseIdentityStore(repo); scope=EnterpriseScopeEngine(ids); assets=AssetRegistry(repo)
    ids.upsert_tenant({"tenant_id":"T1","name":"Tenant 1"}); ids.upsert_tenant({"tenant_id":"T2","name":"Tenant 2"})
    ids.upsert_site({"tenant_id":"T1","site_id":"F01","name":"Factory 01"})
    ids.upsert_principal({"principal_id":"u1","tenant_id":"T1","name":"Engineer","roles":["reliability_engineer"],"site_ids":["F01"],"asset_ids":["A1"]})
    assets.upsert_asset({"asset_id":"A1","tenant_id":"T1","site_id":"F01"})
    assets.upsert_asset({"asset_id":"A2","tenant_id":"T1","site_id":"F02"})
    assets.upsert_asset({"asset_id":"B1","tenant_id":"T2","site_id":"F01"})
    rows=scope.filter_resources("u1","asset","read",assets.list_assets(limit=100))
    assert [x["asset_id"] for x in rows] == ["A1"]
    assert scope.check("u1","asset","read",assets.get_asset("A1"))["allowed"] is True
    assert scope.check("u1","asset","read",assets.get_asset("B1"))["allowed"] is False
    assert ids.audit_rows(principal_id="u1")


def test_connector_edge_agent_tenant_site_isolation(tmp_path):
    repo=JsonRepository(tmp_path); bindings=DataBindingStore(repo); runtime=IntegrationRuntimeService(repo,bindings)
    agents=EdgeAgentRegistry(repo); connectors=ConnectorRegistry(repo,bindings); processor=ConnectorBatchProcessor(connectors,runtime,agents)
    assets=AssetRegistry(repo); cmms=CMMSWorkOrderCandidateStore(repo)
    b=bindings.upsert({"name":"t1-assets","target":"asset","source_type":"api","mappings":{"asset_id":"id"},"tenant_id":"T1","site_id":"F01"}); bindings.approve(b["binding_id"])
    c=connectors.upsert({"name":"t1-edge","connector_type":"jdbc","binding_id":b["binding_id"],"tenant_id":"T1","site_id":"F01"}); connectors.approve(c["connector_id"])
    bad=agents.register({"name":"wrong-edge","tenant_id":"T2","site_id":"F01"})
    try:
        processor.submit({"batch_id":"x","connector_id":c["connector_id"],"binding_id":b["binding_id"],"agent_id":bad["agent_id"],"records":[{"id":"A1"}]},{"asset_registry":assets,"cmms_candidates":cmms})
        assert False
    except ValueError as exc:
        assert "tenant scope" in str(exc)
    good=agents.register({"name":"good-edge","tenant_id":"T1","site_id":"F01"})
    out=processor.submit({"batch_id":"y","connector_id":c["connector_id"],"binding_id":b["binding_id"],"agent_id":good["agent_id"],"records":[{"id":"A1"}]},{"asset_registry":assets,"cmms_candidates":cmms})
    assert out["succeeded"] == 1
    assert assets.get_asset("A1")["tenant_id"] == "T1"
    assert assets.get_asset("A1")["site_id"] == "F01"


def test_v25_api_contract():
    from app.main import app
    c=TestClient(app)
    assert c.get('/health').json()['version']=='3.3.0'
    contract=c.get('/enterprise/contract')
    assert contract.status_code==200
    assert 'tenant_admin' in contract.json()['roles']


def test_scoped_rca_and_fmea_resource_shapes(tmp_path):
    from app.fmea import FMEAStore
    from app.rca_cases import RCACaseStore
    repo=JsonRepository(tmp_path); ids=EnterpriseIdentityStore(repo); scope=EnterpriseScopeEngine(ids)
    ids.upsert_tenant({"tenant_id":"T1","name":"T1"})
    ids.upsert_principal({"principal_id":"rel","tenant_id":"T1","name":"Rel","roles":["reliability_engineer"],"asset_ids":["A1"]})
    f=FMEAStore(repo); r=RCACaseStore(repo)
    f.create({"fmea_id":"F1","tenant_id":"T1","asset":"A1","component":"Bearing","failure_mode":"fault","severity":5,"occurrence":4,"detectability":3})
    f.create({"fmea_id":"F2","tenant_id":"T1","asset":"A2","component":"Bearing","failure_mode":"fault","severity":5,"occurrence":4,"detectability":3})
    r.create({"case_id":"R1","tenant_id":"T1","subject":{"entity":"Machine","reference":"A1"}})
    r.create({"case_id":"R2","tenant_id":"T1","subject":{"entity":"Machine","reference":"A2"}})
    assert [x["fmea_id"] for x in scope.filter_resources("rel","fmea","read",f.list(limit=10))] == ["F1"]
    assert [x["case_id"] for x in scope.filter_resources("rel","rca","read",r.list(limit=10))] == ["R1"]
