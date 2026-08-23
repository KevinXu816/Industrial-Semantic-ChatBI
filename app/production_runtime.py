"""V3.0 production release control plane.

Keeps production lifecycle concerns separate from domain services:
configuration validation, preflight/readiness, migrations, backup/restore,
and upgrade compatibility checks.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ValidationIssue:
    level: str
    code: str
    message: str


class ProductionConfigValidator:
    """Fail-fast configuration validation for production deployments."""
    def validate(self) -> Dict[str, Any]:
        issues: List[ValidationIssue] = []
        auth = os.getenv("AUTH_MODE", "disabled").lower()
        persistence = os.getenv("PERSISTENCE_BACKEND", "json").lower()
        execution = os.getenv("EXECUTION_MODE", "mock").lower()
        env = os.getenv("DEPLOYMENT_ENV", "development").lower()

        if env in {"production", "prod"}:
            if auth == "disabled":
                issues.append(ValidationIssue("error", "auth_disabled", "AUTH_MODE must not be disabled in production"))
            if persistence == "json":
                issues.append(ValidationIssue("error", "json_persistence", "PERSISTENCE_BACKEND=json is not supported for HA production"))
            if execution == "mock":
                issues.append(ValidationIssue("warning", "mock_execution", "EXECUTION_MODE=mock is intended for demo/POC only"))
            if os.getenv("AUTH_DEV_SECRET", "change-me-dev-secret") == "change-me-dev-secret" and auth == "dev":
                issues.append(ValidationIssue("error", "default_dev_secret", "Default development authentication secret is forbidden in production"))

        if persistence in {"postgres", "postgresql"} and not (os.getenv("DATABASE_URL") or os.getenv("PGHOST")):
            issues.append(ValidationIssue("error", "postgres_config", "PostgreSQL backend requires DATABASE_URL or PGHOST configuration"))
        if auth == "oidc" and not os.getenv("OIDC_ISSUER"):
            issues.append(ValidationIssue("error", "oidc_issuer", "AUTH_MODE=oidc requires OIDC_ISSUER"))
        if auth == "jwt" and not (os.getenv("AUTH_JWT_SECRET") or os.getenv("AUTH_JWT_SECRET_REF")):
            issues.append(ValidationIssue("error", "jwt_secret", "AUTH_MODE=jwt requires AUTH_JWT_SECRET_REF or AUTH_JWT_SECRET"))
        if execution == "doris" and not os.getenv("DORIS_HOST"):
            issues.append(ValidationIssue("error", "doris_host", "EXECUTION_MODE=doris requires DORIS_HOST"))

        errors = [asdict(x) for x in issues if x.level == "error"]
        warnings = [asdict(x) for x in issues if x.level == "warning"]
        return {
            "status": "error" if errors else "ok",
            "deployment_env": env,
            "version": APP_VERSION,
            "errors": errors,
            "warnings": warnings,
        }


class MigrationManager:
    """Repository-backed migration ledger for application/schema upgrades."""
    COLLECTION = "platform_migrations"
    REQUIRED = [
        ("300000", "V3.0 production runtime baseline"),
        ("300001", "Health probe and deployment metadata baseline"),
        ("300002", "Backup/restore manifest baseline"),
    ]

    def __init__(self, repository): self.repo = repository

    def status(self) -> Dict[str, Any]:
        applied = {str(x.get("migration_id")): x for x in self.repo.list(self.COLLECTION, limit=1000)}
        pending = [{"migration_id": mid, "description": desc} for mid, desc in self.REQUIRED if mid not in applied]
        return {"required": len(self.REQUIRED), "applied": len(applied), "pending": pending, "up_to_date": not pending}

    def migrate(self, actor: str = "system") -> Dict[str, Any]:
        applied_now=[]
        current = {str(x.get("migration_id")) for x in self.repo.list(self.COLLECTION, limit=1000)}
        for mid, desc in self.REQUIRED:
            if mid in current: continue
            row={"migration_id":mid,"description":desc,"app_version":APP_VERSION,"applied_at":utcnow(),"applied_by":actor}
            self.repo.put(self.COLLECTION, mid, row); applied_now.append(row)
        return {"applied_now": applied_now, **self.status()}


class ProductionLifecycle:
    def __init__(self, repository, dependency_probe, secret_manager, auth_service):
        self.repo=repository; self.dependency_probe=dependency_probe; self.secrets=secret_manager; self.auth=auth_service
        self.validator=ProductionConfigValidator(); self.migrations=MigrationManager(repository)
        self._started=False; self._shutting_down=False; self._lock=threading.RLock(); self._startup_result={}

    def startup(self) -> Dict[str, Any]:
        with self._lock:
            validation=self.validator.validate()
            auto_migrate=os.getenv("AUTO_MIGRATE", "true").lower() in {"1","true","yes","on"}
            migrations=self.migrations.migrate() if auto_migrate else self.migrations.status()
            self._started=True; self._shutting_down=False
            self._startup_result={"at":utcnow(),"configuration":validation,"migrations":migrations}
            return self._startup_result

    def shutdown(self):
        with self._lock: self._shutting_down=True

    def live(self):
        return {"status":"ok" if self._started else "starting", "version":APP_VERSION, "started":self._started, "shutting_down":self._shutting_down}

    def startup_probe(self):
        cfg=self.validator.validate(); ms=self.migrations.status()
        ok=self._started and cfg["status"] == "ok" and ms["up_to_date"]
        return {"status":"ok" if ok else "not_ready", "version":APP_VERSION, "configuration":cfg, "migrations":ms}

    def ready(self):
        cfg=self.validator.validate(); dep=self.dependency_probe()
        required_fail=[]
        # Dependency service returns normalized rows; disabled optional dependencies are not readiness failures.
        for row in dep.get("dependencies", []):
            status=str(row.get("status", "unknown")).lower()
            if status in {"error","down","unhealthy","failed"}:
                required_fail.append(row.get("name") or row.get("dependency") or "unknown")
        repo_health=self.repo.health()
        if str(repo_health.get("status","ok")).lower() != "ok": required_fail.append("persistence")
        ok=self._started and not self._shutting_down and cfg["status"]=="ok" and not required_fail
        return {"status":"ok" if ok else "not_ready", "version":APP_VERSION, "failed_dependencies":sorted(set(required_fail)), "configuration":cfg, "persistence":repo_health, "dependencies":dep}


class BackupManager:
    """Portable backup for repository JSON/demo state and production metadata.

    PostgreSQL production data should additionally use native pg_dump/WAL backups; the
    manifest makes that expectation explicit instead of pretending an app export is DR.
    """
    def __init__(self, repository): self.repo=repository

    def create(self, destination: str | None = None) -> Dict[str, Any]:
        from .persistence import JsonRepository
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out=Path(destination or (ROOT / "backups" / f"industrial-semantic-{APP_VERSION}-{stamp}.tar.gz"))
        out.parent.mkdir(parents=True, exist_ok=True)
        backend=self.repo.health().get("backend", "unknown")
        with tempfile.TemporaryDirectory() as td:
            temp=Path(td); manifest={"app_version":APP_VERSION,"created_at":utcnow(),"backend":backend,"type":"application-metadata"}
            if isinstance(self.repo, JsonRepository):
                src=self.repo.root
                if src.exists(): shutil.copytree(src, temp/"repository", dirs_exist_ok=True)
                manifest["includes_repository_data"]=True
            else:
                manifest["includes_repository_data"]=False
                manifest["production_note"]="Use PostgreSQL pg_dump/base backup and WAL archiving for full data recovery."
            (temp/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
            with tarfile.open(out,"w:gz") as tar:
                for p in temp.iterdir(): tar.add(p, arcname=p.name)
        digest=hashlib.sha256(out.read_bytes()).hexdigest()
        return {"path":str(out),"sha256":digest,"size_bytes":out.stat().st_size,**manifest}

    def inspect(self, archive: str) -> Dict[str, Any]:
        p=Path(archive)
        if not p.exists(): raise FileNotFoundError(archive)
        with tarfile.open(p,"r:gz") as tar:
            member=tar.extractfile("manifest.json")
            if member is None: raise ValueError("backup manifest missing")
            manifest=json.load(member)
        return {"path":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"manifest":manifest}

    def restore_json(self, archive: str, *, confirm: bool = False) -> Dict[str, Any]:
        from .persistence import JsonRepository
        if not confirm: return {"status":"dry_run","backup":self.inspect(archive)}
        if not isinstance(self.repo, JsonRepository): raise RuntimeError("Application restore is only supported for JSON backend; use PostgreSQL native restore in production")
        with tempfile.TemporaryDirectory() as td:
            with tarfile.open(archive,"r:gz") as tar: tar.extractall(td, filter="data")
            src=Path(td)/"repository"
            if not src.exists(): raise ValueError("backup does not contain JSON repository data")
            self.repo.root.mkdir(parents=True,exist_ok=True)
            for old in self.repo.root.glob("*.json"): old.unlink()
            for f in src.glob("*.json"): shutil.copy2(f,self.repo.root/f.name)
        return {"status":"restored","at":utcnow(),"backup":self.inspect(archive)}


class UpgradeAdvisor:
    def __init__(self, migration_manager: MigrationManager, validator: ProductionConfigValidator):
        self.migrations=migration_manager; self.validator=validator
    def check(self, from_version: str = "") -> Dict[str, Any]:
        cfg=self.validator.validate(); ms=self.migrations.status()
        major_from=(from_version or APP_VERSION).split(".")[0]
        major_to=APP_VERSION.split(".")[0]
        return {"current_version":APP_VERSION,"from_version":from_version or APP_VERSION,"major_upgrade":major_from!=major_to,"configuration":cfg,"migrations":ms,"safe_to_start":cfg["status"]=="ok" and ms["up_to_date"],"recommendations":["Take a verified backup before upgrade","Run readiness checks after deployment","Use rolling deployment only when shared persistence is PostgreSQL"]}
