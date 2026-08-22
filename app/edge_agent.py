"""V2.4 Edge/Data Agent registry and heartbeat contract."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict
import hashlib
from .persistence import Repository
from .enterprise_identity import default_tenant_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EdgeAgentRegistry:
    COLLECTION = "edge_agents"

    def __init__(self, repository: Repository):
        self.repo = repository

    def register(self, payload: Dict[str, Any], actor: str = "integration_engineer"):
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("edge agent name is required")
        key = str(payload.get("agent_id") or "EDGE-" + hashlib.sha1(name.encode()).hexdigest()[:12])
        row = dict(payload)
        row.update({"agent_id": key, "name": name, "status": payload.get("status", "registered"),
                    "registered_at": payload.get("registered_at", _now()), "updated_at": _now(), "updated_by": actor})
        row.setdefault("site", "")
        row.setdefault("tenant_id", default_tenant_id())
        row.setdefault("org_id", "")
        row.setdefault("site_id", row.get("site") or "")
        row.setdefault("version", "")
        row.setdefault("capabilities", [])
        row.setdefault("last_heartbeat_at", None)
        row.setdefault("diagnostics", {})
        return self.repo.put(self.COLLECTION, key, row)

    def get(self, agent_id: str):
        return self.repo.get(self.COLLECTION, agent_id)

    def list(self, status: str = "", limit: int = 200):
        rows = self.repo.list(self.COLLECTION, limit=limit)
        return [r for r in rows if not status or r.get("status") == status]

    def heartbeat(self, agent_id: str, payload: Dict[str, Any]):
        row = self.get(agent_id)
        if not row:
            raise KeyError(agent_id)
        row.update({"status": "online", "last_heartbeat_at": _now(), "version": payload.get("version", row.get("version", "")),
                    "diagnostics": payload.get("diagnostics", row.get("diagnostics", {})),
                    "capabilities": payload.get("capabilities", row.get("capabilities", [])), "updated_at": _now()})
        return self.repo.put(self.COLLECTION, agent_id, row)

    def set_offline(self, agent_id: str, actor: str = "operator"):
        row = self.get(agent_id)
        if not row:
            raise KeyError(agent_id)
        row.update({"status": "offline", "updated_at": _now(), "updated_by": actor})
        return self.repo.put(self.COLLECTION, agent_id, row)


    def health(self, stale_after_seconds: int = 180):
        now = datetime.now(timezone.utc)
        rows = self.list(limit=1000)
        out=[]
        for row in rows:
            effective=row.get("status", "registered")
            age=None
            hb=row.get("last_heartbeat_at")
            if hb:
                try:
                    ts=datetime.fromisoformat(str(hb).replace("Z", "+00:00")); age=(now-ts.astimezone(timezone.utc)).total_seconds()
                    if age > stale_after_seconds and effective == "online": effective="stale"
                except Exception:
                    effective="unknown"
            out.append({"agent_id":row.get("agent_id"),"name":row.get("name"),"site":row.get("site"),"status":effective,"heartbeat_age_seconds":age,"version":row.get("version"),"diagnostics":row.get("diagnostics") or {}})
        return {"registered":len(rows),"online":sum(1 for x in out if x["status"]=="online"),"stale":sum(1 for x in out if x["status"]=="stale"),"agents":out}

    def contract(self):
        return {"contract_version": "1.0", "heartbeat": {"recommended_seconds": 60},
                "capabilities": ["influxdb", "jdbc", "rest", "mqtt", "file"],
                "semantics": "Edge Agent owns source connectivity and submits normalized ConnectorBatch to the central platform."}
