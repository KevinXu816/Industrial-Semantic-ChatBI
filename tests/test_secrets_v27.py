import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.persistence import JsonRepository
from app.secrets import SecretRegistry, SecretManager, reject_inline_secrets


def test_environment_and_file_secret_providers(tmp_path, monkeypatch):
    repo=JsonRepository(tmp_path/'repo'); reg=SecretRegistry(repo); mgr=SecretManager(reg)
    monkeypatch.setenv('V27_TEST_SECRET','top-secret')
    reg.register({'secret_id':'env-test','secret_ref':'secret://env/V27_TEST_SECRET','purpose':'test'})
    assert mgr.resolve_id('env-test') == 'top-secret'
    root=tmp_path/'mounted'; root.mkdir(); (root/'db_password').write_text('file-secret\n')
    monkeypatch.setenv('SECRETS_FILE_ROOT',str(root))
    # New manager reloads provider root from environment.
    mgr=SecretManager(reg)
    reg.register({'secret_id':'file-test','secret_ref':'secret://file/db_password'})
    assert mgr.resolve_id('file-test') == 'file-secret'
    assert 'top-secret' not in str(reg.list())


def test_inline_connector_secret_rejected():
    with pytest.raises(ValueError): reject_inline_secrets({'password':'abc123'})
    assert reject_inline_secrets({'credential_ref':'secret://env/MES_PASSWORD'}) is True


def test_v27_api_secret_metadata_never_returns_value(monkeypatch):
    import app.main as m
    monkeypatch.setenv('AUTH_MODE','disabled'); m.auth_service.reload()
    monkeypatch.setenv('V27_API_SECRET','do-not-return-me')
    c=TestClient(m.app)
    assert c.get('/health').json()['version']=='2.7.0'
    r=c.post('/secrets',json={'secret_id':'V27-API','secret_ref':'secret://env/V27_API_SECRET','purpose':'api-test'})
    assert r.status_code==200
    body=c.get('/secrets').json()
    assert 'do-not-return-me' not in str(body)
    chk=c.post('/secrets/V27-API/check')
    assert chk.status_code==200 and chk.json()['available'] is True
    audits=c.get('/secrets/audit').json()['audit']
    assert any(x.get('secret_id')=='secret://env/V27_API_SECRET' and x.get('success') for x in audits)


def test_connector_inline_credentials_blocked(monkeypatch):
    import app.main as m
    monkeypatch.setenv('AUTH_MODE','disabled'); m.auth_service.reload()
    c=TestClient(m.app)
    bid='V27-BIND'
    c.post('/data-bindings',json={'binding_id':bid,'name':'v27','source_type':'jdbc','target':'asset','mappings':{'asset_id':'asset_id'}})
    c.post(f'/data-bindings/{bid}/approve',json={})
    r=c.post('/connectors',json={'name':'bad-connector','connector_type':'jdbc','binding_id':bid,'config':{'password':'plain-text'}})
    assert r.status_code==400
    ok=c.post('/connectors',json={'name':'good-connector','connector_type':'jdbc','binding_id':bid,'config':{'credential_ref':'secret://env/MES_PASSWORD'}})
    assert ok.status_code==200
