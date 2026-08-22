import os
from fastapi.testclient import TestClient


def test_trace_context_and_metrics_contract(monkeypatch):
    import app.main as m
    monkeypatch.setenv('AUTH_MODE','disabled'); m.auth_service.reload()
    c=TestClient(m.app)
    r=c.get('/admin/cache',headers={'X-Correlation-ID':'COR-V29-TEST'})
    assert r.status_code==200
    assert r.headers.get('x-correlation-id')=='COR-V29-TEST'
    tid=r.headers.get('x-trace-id')
    assert tid and len(tid)==32
    assert r.headers.get('traceparent','').startswith('00-'+tid+'-')
    tr=c.get('/observability/traces/'+tid)
    assert tr.status_code==200
    assert tr.json()['span_count']>=1
    assert any(x.get('correlation_id')=='COR-V29-TEST' for x in tr.json()['spans'])
    metrics=c.get('/observability/metrics').json()
    assert metrics['requests']>=1
    assert 'p95' in metrics['latency_ms']


def test_slo_alert_dependency_and_prometheus(monkeypatch):
    import app.main as m
    monkeypatch.setenv('AUTH_MODE','disabled'); m.auth_service.reload()
    c=TestClient(m.app)
    dep=c.post('/observability/dependencies/check')
    assert dep.status_code==200
    assert dep.json()['total']>=4
    slo=c.get('/sre/slos')
    assert slo.status_code==200
    assert len(slo.json()['slos'])>=2
    rule=c.post('/sre/alert-rules',json={'name':'test latency','metric':'latency_p95_ms','operator':'gte','threshold':0,'severity':'warning'})
    assert rule.status_code==200
    ev=c.post('/sre/alerts/evaluate')
    assert ev.status_code==200
    assert ev.json()['open']>=1
    pm=c.get('/observability/prometheus')
    assert pm.status_code==200
    assert 'industrial_http_requests_total' in pm.text
