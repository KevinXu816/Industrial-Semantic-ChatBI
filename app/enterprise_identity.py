"""V2.5 enterprise identity, tenancy and resource-scope governance.

The existing semantic RBAC/RLS continues to govern query meaning.  This module adds
an orthogonal enterprise control plane for *who* may access *which enterprise
resources*: tenant -> organization -> site -> asset / connector / edge agent.

Compatibility principle: legacy records without tenant_id belong to DEFAULT_TENANT_ID
(default: ``default``), so existing single-enterprise deployments keep working.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set
import hashlib
import os

from .persistence import Repository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_tenant_id() -> str:
    return os.getenv("DEFAULT_TENANT_ID", "default")


PERMISSIONS = {
    "tenant_admin": ["*"],
    "reliability_engineer": [
        "asset:read", "asset:write", "fmea:read", "fmea:write", "rca:read", "rca:write",
        "reliability:read", "maintenance:read", "knowledge:read",
    ],
    "maintenance_planner": [
        "asset:read", "fmea:read", "rca:read", "rca:write", "maintenance:read", "maintenance:write",
    ],
    "integration_engineer": [
        "asset:read", "connector:read", "connector:write", "edge_agent:read", "edge_agent:write",
        "binding:read", "binding:write", "integration:read", "integration:write",
    ],
    "operator": ["asset:read", "reliability:read", "rca:read", "maintenance:read"],
    "viewer": ["asset:read", "reliability:read", "rca:read", "fmea:read", "maintenance:read"],
}


class IdentityError(ValueError):
    pass


class AccessDenied(PermissionError):
    pass


class EnterpriseIdentityStore:
    TENANTS = "enterprise_tenants"
    ORGS = "enterprise_organizations"
    SITES = "enterprise_sites"
    PRINCIPALS = "enterprise_principals"
    AUDIT = "enterprise_access_audit"

    def __init__(self, repository: Repository):
        self.repo = repository
        self.ensure_default_tenant()

    def ensure_default_tenant(self) -> Dict[str, Any]:
        tid = default_tenant_id()
        current = self.repo.get(self.TENANTS, tid)
        if current:
            return current
        row = {
            "tenant_id": tid,
            "name": "Default Enterprise",
            "status": "active",
            "created_at": _now(),
            "updated_at": _now(),
            "metadata": {"compatibility_tenant": True},
        }
        return self.repo.put(self.TENANTS, tid, row)

    def upsert_tenant(self, payload: Dict[str, Any], actor: str = "platform_admin") -> Dict[str, Any]:
        tid = str(payload.get("tenant_id") or "").strip()
        name = str(payload.get("name") or tid).strip()
        if not tid:
            raise IdentityError("tenant_id is required")
        current = self.repo.get(self.TENANTS, tid) or {}
        row = {**current, **payload, "tenant_id": tid, "name": name, "updated_at": _now(), "updated_by": actor}
        row.setdefault("status", "active")
        row.setdefault("created_at", current.get("created_at") or _now())
        row.setdefault("metadata", {})
        return self.repo.put(self.TENANTS, tid, row)

    def tenants(self, status: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.TENANTS, limit=limit)
        return [r for r in rows if not status or r.get("status") == status]

    def upsert_org(self, payload: Dict[str, Any], actor: str = "tenant_admin") -> Dict[str, Any]:
        tenant_id = str(payload.get("tenant_id") or default_tenant_id())
        if not self.repo.get(self.TENANTS, tenant_id):
            raise IdentityError("tenant does not exist")
        name = str(payload.get("name") or "").strip()
        if not name:
            raise IdentityError("organization name is required")
        oid = str(payload.get("org_id") or "ORG-" + hashlib.sha1(f"{tenant_id}:{name}".encode()).hexdigest()[:12])
        current = self.repo.get(self.ORGS, oid) or {}
        row = {**current, **payload, "org_id": oid, "tenant_id": tenant_id, "name": name,
               "updated_at": _now(), "updated_by": actor}
        row.setdefault("status", "active"); row.setdefault("created_at", current.get("created_at") or _now()); row.setdefault("metadata", {})
        return self.repo.put(self.ORGS, oid, row)

    def orgs(self, tenant_id: str = "", limit: int = 500) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.ORGS, limit=limit)
        return [r for r in rows if not tenant_id or self.normalize_tenant(r) == tenant_id]

    def upsert_site(self, payload: Dict[str, Any], actor: str = "tenant_admin") -> Dict[str, Any]:
        tenant_id = str(payload.get("tenant_id") or default_tenant_id())
        org_id = str(payload.get("org_id") or "")
        if not self.repo.get(self.TENANTS, tenant_id):
            raise IdentityError("tenant does not exist")
        if org_id:
            org = self.repo.get(self.ORGS, org_id)
            if not org or self.normalize_tenant(org) != tenant_id:
                raise IdentityError("organization does not belong to tenant")
        name = str(payload.get("name") or payload.get("site_id") or "").strip()
        if not name:
            raise IdentityError("site name is required")
        sid = str(payload.get("site_id") or "SITE-" + hashlib.sha1(f"{tenant_id}:{org_id}:{name}".encode()).hexdigest()[:12])
        current = self.repo.get(self.SITES, sid) or {}
        row = {**current, **payload, "site_id": sid, "tenant_id": tenant_id, "org_id": org_id, "name": name,
               "updated_at": _now(), "updated_by": actor}
        row.setdefault("status", "active"); row.setdefault("created_at", current.get("created_at") or _now()); row.setdefault("metadata", {})
        return self.repo.put(self.SITES, sid, row)

    def sites(self, tenant_id: str = "", org_id: str = "", limit: int = 1000) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.SITES, limit=limit)
        return [r for r in rows if (not tenant_id or self.normalize_tenant(r) == tenant_id) and (not org_id or r.get("org_id") == org_id)]

    def upsert_principal(self, payload: Dict[str, Any], actor: str = "tenant_admin") -> Dict[str, Any]:
        tenant_id = str(payload.get("tenant_id") or default_tenant_id())
        if not self.repo.get(self.TENANTS, tenant_id):
            raise IdentityError("tenant does not exist")
        name = str(payload.get("name") or payload.get("principal_id") or "").strip()
        if not name:
            raise IdentityError("principal name is required")
        pid = str(payload.get("principal_id") or "USR-" + hashlib.sha1(f"{tenant_id}:{name}".encode()).hexdigest()[:12])
        roles = list(dict.fromkeys(payload.get("roles") or ["viewer"]))
        unknown = [r for r in roles if r not in PERMISSIONS]
        if unknown:
            raise IdentityError(f"unknown enterprise roles: {unknown}")
        current = self.repo.get(self.PRINCIPALS, pid) or {}
        row = {**current, **payload, "principal_id": pid, "tenant_id": tenant_id, "name": name, "roles": roles,
               "updated_at": _now(), "updated_by": actor}
        row.setdefault("status", "active")
        row.setdefault("org_id", "")
        row.setdefault("site_ids", [])
        row.setdefault("asset_ids", [])
        row.setdefault("connector_ids", [])
        row.setdefault("permissions", [])
        row.setdefault("created_at", current.get("created_at") or _now())
        return self.repo.put(self.PRINCIPALS, pid, row)

    def principal(self, principal_id: str) -> Optional[Dict[str, Any]]:
        return self.repo.get(self.PRINCIPALS, principal_id)

    def principals(self, tenant_id: str = "", status: str = "", limit: int = 500) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.PRINCIPALS, limit=limit)
        return [r for r in rows if (not tenant_id or self.normalize_tenant(r) == tenant_id) and (not status or r.get("status") == status)]

    @staticmethod
    def normalize_tenant(resource: Dict[str, Any]) -> str:
        return str(resource.get("tenant_id") or default_tenant_id())

    def audit(self, principal_id: str, resource_type: str, action: str, resource_id: str, allowed: bool,
              reason: str = "", resource_scope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raw = f"{principal_id}:{resource_type}:{action}:{resource_id}:{_now()}"
        aid = "ACCESS-" + hashlib.sha1(raw.encode()).hexdigest()[:18]
        row = {"audit_id": aid, "principal_id": principal_id, "resource_type": resource_type, "action": action,
               "resource_id": resource_id, "allowed": allowed, "reason": reason, "resource_scope": resource_scope or {},
               "created_at": _now()}
        return self.repo.put(self.AUDIT, aid, row)

    def audit_rows(self, principal_id: str = "", allowed: Optional[bool] = None, limit: int = 200) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.AUDIT, limit=limit)
        return [r for r in rows if (not principal_id or r.get("principal_id") == principal_id) and (allowed is None or bool(r.get("allowed")) is allowed)]

    def summary(self) -> Dict[str, Any]:
        return {
            "tenants": len(self.tenants(limit=1000)),
            "organizations": len(self.orgs(limit=1000)),
            "sites": len(self.sites(limit=5000)),
            "principals": len(self.principals(limit=5000)),
            "active_principals": len(self.principals(status="active", limit=5000)),
            "access_audit": len(self.audit_rows(limit=5000)),
        }


@dataclass
class EnterpriseAccessContext:
    principal_id: str
    tenant_id: str
    org_id: str
    roles: List[str]
    permissions: Set[str]
    site_ids: Set[str]
    asset_ids: Set[str]
    connector_ids: Set[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "principal_id": self.principal_id, "tenant_id": self.tenant_id, "org_id": self.org_id,
            "roles": self.roles, "permissions": sorted(self.permissions), "site_ids": sorted(self.site_ids),
            "asset_ids": sorted(self.asset_ids), "connector_ids": sorted(self.connector_ids),
        }


class EnterpriseScopeEngine:
    def __init__(self, store: EnterpriseIdentityStore):
        self.store = store

    def context(self, principal_id: str) -> EnterpriseAccessContext:
        p = self.store.principal(principal_id)
        if not p:
            raise KeyError(principal_id)
        if p.get("status") != "active":
            raise AccessDenied("principal is not active")
        permissions: Set[str] = set(p.get("permissions") or [])
        for role in p.get("roles") or []:
            permissions.update(PERMISSIONS.get(role, []))
        return EnterpriseAccessContext(
            principal_id=principal_id,
            tenant_id=self.store.normalize_tenant(p),
            org_id=str(p.get("org_id") or ""), roles=list(p.get("roles") or []), permissions=permissions,
            site_ids=set(str(x) for x in (p.get("site_ids") or [])),
            asset_ids=set(str(x) for x in (p.get("asset_ids") or [])),
            connector_ids=set(str(x) for x in (p.get("connector_ids") or [])),
        )

    @staticmethod
    def _permission_matches(permissions: Iterable[str], resource_type: str, action: str) -> bool:
        perms = set(permissions)
        return "*" in perms or f"{resource_type}:{action}" in perms or f"{resource_type}:*" in perms

    def check(self, principal_id: str, resource_type: str, action: str, resource: Optional[Dict[str, Any]] = None,
              resource_id: str = "") -> Dict[str, Any]:
        resource = resource or {}
        ctx = self.context(principal_id)
        allowed = True
        reason = "allowed"
        if not self._permission_matches(ctx.permissions, resource_type, action):
            allowed, reason = False, f"permission denied: {resource_type}:{action}"
        tenant_id = self.store.normalize_tenant(resource)
        if allowed and tenant_id != ctx.tenant_id:
            allowed, reason = False, "tenant scope mismatch"
        site_id = str(resource.get("site_id") or resource.get("site") or "")
        if allowed and site_id and ctx.site_ids and site_id not in ctx.site_ids:
            allowed, reason = False, "site scope mismatch"
        asset_id = str(resource.get("asset_id") or resource.get("asset") or ((resource.get("subject") or {}).get("reference") if isinstance(resource.get("subject"), dict) else "") or "")
        if allowed and asset_id and ctx.asset_ids and asset_id not in ctx.asset_ids:
            allowed, reason = False, "asset scope mismatch"
        connector_id = str(resource.get("connector_id") or "")
        if allowed and connector_id and ctx.connector_ids and connector_id not in ctx.connector_ids:
            allowed, reason = False, "connector scope mismatch"
        self.store.audit(principal_id, resource_type, action, resource_id or asset_id or connector_id, allowed, reason,
                         {"tenant_id": tenant_id, "site_id": site_id, "asset_id": asset_id, "connector_id": connector_id})
        return {"allowed": allowed, "reason": reason, "context": ctx.as_dict()}

    def require(self, *args, **kwargs) -> Dict[str, Any]:
        result = self.check(*args, **kwargs)
        if not result["allowed"]:
            raise AccessDenied(result["reason"])
        return result

    def filter_resources(self, principal_id: str, resource_type: str, action: str, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Filtering does not write one audit record per invisible row; one summary audit is more useful operationally.
        ctx = self.context(principal_id)
        if not self._permission_matches(ctx.permissions, resource_type, action):
            self.store.audit(principal_id, resource_type, action, "*", False, "permission denied")
            return []
        out=[]
        for r in rows:
            if self.store.normalize_tenant(r) != ctx.tenant_id:
                continue
            site_id=str(r.get("site_id") or r.get("site") or "")
            if site_id and ctx.site_ids and site_id not in ctx.site_ids:
                continue
            subject = r.get("subject") if isinstance(r.get("subject"), dict) else {}
            asset_id=str(r.get("asset_id") or r.get("asset") or subject.get("reference") or "")
            if asset_id and ctx.asset_ids and asset_id not in ctx.asset_ids:
                continue
            connector_id=str(r.get("connector_id") or "")
            if connector_id and ctx.connector_ids and connector_id not in ctx.connector_ids:
                continue
            out.append(r)
        self.store.audit(principal_id, resource_type, action, "*", True, f"scoped {len(out)} resources")
        return out
