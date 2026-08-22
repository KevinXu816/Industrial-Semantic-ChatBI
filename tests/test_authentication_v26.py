import os
from fastapi.testclient import TestClient


def test_v26_dev_authentication_and_scope(monkeypatch):
    import app.main as m
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("AUTH_DEV_SECRET", "unit-test-secret")
    monkeypatch.setenv("AUTH_AUTO_PROVISION", "false")
    m.auth_service.reload()
    tid="AUTH-V26-T"
    m.enterprise_identity.upsert_tenant({"tenant_id":tid,"name":"Auth Tenant"}, actor="test")
    m.enterprise_identity.upsert_principal({
        "principal_id":"auth-v26-user","name":"Auth User","tenant_id":tid,
        "roles":["reliability_engineer"],"site_ids":["F01"],"asset_ids":["A101"]
    }, actor="test")
    c=TestClient(m.app)
    assert c.get('/enterprise/tenants').status_code == 401
    tok=c.post('/auth/dev/token',json={"sub":"auth-v26-user","tenant_id":tid,"roles":["reliability_engineer"]})
    assert tok.status_code==200
    headers={"Authorization":"Bearer "+tok.json()["access_token"]}
    me=c.get('/auth/me',headers=headers)
    assert me.status_code==200
    assert me.json()['principal']['principal_id']=='auth-v26-user'
    ok=c.post('/enterprise/access/check',headers=headers,json={"principal_id":"auth-v26-user","resource_type":"asset","action":"read","resource":{"tenant_id":tid,"site_id":"F01","asset_id":"A101"}})
    assert ok.status_code==200 and ok.json()['allowed'] is True
    denied=c.post('/enterprise/access/check',headers=headers,json={"principal_id":"auth-v26-user","resource_type":"asset","action":"read","resource":{"tenant_id":"OTHER","site_id":"F01","asset_id":"A101"}})
    assert denied.status_code==200 and denied.json()['allowed'] is False
    monkeypatch.setenv("AUTH_MODE", "disabled")
    m.auth_service.reload()


def test_v26_oidc_contract_default_disabled(monkeypatch):
    import app.main as m
    monkeypatch.setenv("AUTH_MODE", "disabled")
    cfg=m.auth_service.reload()
    assert cfg['mode']=='disabled'
    c=TestClient(m.app)
    assert c.get('/health').json()['version']=='2.7.0'
    auth=c.get('/auth/config').json()
    assert auth['enabled'] is False


def test_v26_principal_impersonation_is_blocked(monkeypatch):
    import app.main as m
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("AUTH_DEV_SECRET", "unit-test-secret")
    monkeypatch.setenv("AUTH_AUTO_PROVISION", "false")
    m.auth_service.reload()
    tid="AUTH-V26-IMP"
    m.enterprise_identity.upsert_tenant({"tenant_id":tid,"name":"Impersonation Tenant"}, actor="test")
    m.enterprise_identity.upsert_principal({"principal_id":"v26-viewer-a","name":"Viewer A","tenant_id":tid,"roles":["viewer"],"site_ids":["F01"]}, actor="test")
    m.enterprise_identity.upsert_principal({"principal_id":"v26-viewer-b","name":"Viewer B","tenant_id":tid,"roles":["viewer"],"site_ids":["F02"]}, actor="test")
    c=TestClient(m.app)
    token=c.post('/auth/dev/token',json={"sub":"v26-viewer-a","tenant_id":tid,"roles":["viewer"]}).json()['access_token']
    headers={"Authorization":"Bearer "+token}
    res=c.get('/enterprise/scoped/assets?principal_id=v26-viewer-b',headers=headers)
    assert res.status_code==403
    monkeypatch.setenv("AUTH_MODE", "disabled")
    m.auth_service.reload()
