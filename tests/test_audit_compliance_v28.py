from app.audit_center import AuditCenter
from app.persistence import JsonRepository


def test_audit_event_trace_policy_and_redaction(tmp_path):
    repo=JsonRepository(tmp_path)
    center=AuditCenter(repo)
    center.add_policy({"policy_id":"P-DENY","name":"deny access","severity":"high","match":{"decision":"deny"}})
    e=center.emit(category="authorization",action="asset:read",actor="u1",tenant_id="T1",resource_type="asset",resource_id="A1",
                  decision="deny",status="failure",correlation_id="COR-1",detail={"password":"never-store","reason":"scope mismatch"})
    assert e["detail"]["password"]=="***"
    assert center.trace("COR-1")[0]["event_id"]==e["event_id"]
    assert len(center.violations(status="open")) >= 1


def test_legacy_import_is_idempotent(tmp_path):
    repo=JsonRepository(tmp_path); center=AuditCenter(repo)
    repo.put("authentication_audit","AUTH-1",{"audit_id":"AUTH-1","principal_id":"u1","success":False,"reason":"bad token","created_at":"2026-08-22T00:00:00+00:00"})
    assert center.import_legacy()["imported"]==1
    assert center.import_legacy()["imported"]==0
    rows=center.search(category="authentication")
    assert rows and rows[0]["decision"]=="allow" and rows[0]["status"]=="failure"


def test_retention_dry_run_and_export(tmp_path):
    repo=JsonRepository(tmp_path); center=AuditCenter(repo)
    center.emit(category="api",action="GET",actor="u1",resource_type="http_endpoint",resource_id="/x",correlation_id="COR-X")
    center.set_retention(30)
    assert center.retention()["retention_days"]==30
    assert center.enforce_retention(dry_run=True)["deleted"]==0
    assert "event_id" in center.export(fmt="csv")


def test_v28_api_correlation_trace(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as m
    monkeypatch.setenv("AUTH_MODE","disabled"); m.auth_service.reload()
    c=TestClient(m.app)
    r=c.get('/admin/cache',headers={'X-Correlation-ID':'COR-V28-TEST'})
    assert r.status_code==200
    assert r.headers['x-correlation-id']=='COR-V28-TEST'
    trace=c.get('/audit/traces/COR-V28-TEST')
    assert trace.status_code==200
    events=trace.json()['events']
    assert any(e.get('resource_id')=='/admin/cache' for e in events)
