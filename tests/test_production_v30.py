import os
from pathlib import Path
from fastapi.testclient import TestClient


def test_config_validator_production_fail_closed(monkeypatch):
    from app.production_runtime import ProductionConfigValidator
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    out=ProductionConfigValidator().validate()
    assert out["status"] == "error"
    codes={x["code"] for x in out["errors"]}
    assert "auth_disabled" in codes and "json_persistence" in codes


def test_migrations_idempotent(tmp_path):
    from app.persistence import JsonRepository
    from app.production_runtime import MigrationManager
    repo=JsonRepository(tmp_path)
    mgr=MigrationManager(repo)
    first=mgr.migrate(actor="test")
    second=mgr.migrate(actor="test")
    assert len(first["applied_now"]) == 3
    assert second["applied_now"] == []
    assert second["up_to_date"] is True


def test_json_backup_round_trip(tmp_path):
    from app.persistence import JsonRepository
    from app.production_runtime import BackupManager
    repo=JsonRepository(tmp_path/"repo")
    repo.put("demo","a",{"value":1})
    manager=BackupManager(repo)
    archive=tmp_path/"backup.tar.gz"
    result=manager.create(str(archive))
    assert archive.exists() and len(result["sha256"]) == 64
    repo.put("demo","a",{"value":2})
    manager.restore_json(str(archive), confirm=True)
    assert repo.get("demo","a")["value"] == 1


def test_v30_health_probes(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    import app.main as m
    m.auth_service.reload()
    with TestClient(m.app) as client:
        assert client.get('/health').json()['version'] == '4.9.0'
        assert client.get('/health/live').status_code == 200
        assert client.get('/health/startup').status_code == 200
        assert client.get('/health/ready').status_code == 200
        assert client.get('/production/migrations').json()['up_to_date'] is True
        check=client.get('/production/upgrade/check', params={'from_version':'2.9.0'}).json()
        assert check['current_version']=='4.9.0'
        assert check['major_upgrade'] is True
