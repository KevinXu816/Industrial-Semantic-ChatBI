"""V2.4 Connector SDK contracts and governed connector registry.

The platform core does not own vendor network clients. Connectors and edge agents
normalize source data into ConnectorBatch and submit it to the V2.3 IntegrationRuntime.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List
import hashlib
from .persistence import Repository
from .enterprise_identity import default_tenant_id
from .secrets import reject_inline_secrets


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseConnectorAdapter:
    """Minimal SDK contract implemented by edge-side vendor adapters.

    Adapters own vendor I/O and call build_batch() after normalizing records.
    The central platform intentionally never receives credentials through this object.
    """
    connector_type = "base"

    def build_batch(self, connector_id: str, binding_id: str, records: List[Dict[str, Any]], *,
                    batch_id: str = "", cursor: Any = None, schema: Dict[str, Any] | None = None,
                    diagnostics: Dict[str, Any] | None = None, agent_id: str = "") -> Dict[str, Any]:
        if not batch_id:
            raw=f"{connector_id}:{binding_id}:{cursor}:{_now()}"
            batch_id="CB-"+hashlib.sha1(raw.encode()).hexdigest()[:16]
        return {"batch_id": batch_id, "connector_id": connector_id, "binding_id": binding_id,
                "agent_id": agent_id, "source": {"type": self.connector_type},
                "schema": schema or {}, "cursor": cursor, "records": records,
                "diagnostics": diagnostics or {}, "observed_at": _now()}


class InfluxDBConnectorAdapter(BaseConnectorAdapter): connector_type = "influxdb"
class JDBCConnectorAdapter(BaseConnectorAdapter): connector_type = "jdbc"
class RESTConnectorAdapter(BaseConnectorAdapter): connector_type = "rest"
class MQTTConnectorAdapter(BaseConnectorAdapter): connector_type = "mqtt"
class FileConnectorAdapter(BaseConnectorAdapter): connector_type = "file"


CONNECTOR_TYPES = {
    "influxdb": {"mode": "pull", "cursor": "timestamp", "adapter": "InfluxDBConnectorAdapter"},
    "jdbc": {"mode": "pull", "cursor": "watermark", "adapter": "JDBCConnectorAdapter"},
    "rest": {"mode": "pull", "cursor": "opaque", "adapter": "RESTConnectorAdapter"},
    "mqtt": {"mode": "subscribe", "cursor": "message_id", "adapter": "MQTTConnectorAdapter"},
    "file": {"mode": "pull", "cursor": "file_offset", "adapter": "FileConnectorAdapter"},
}


class ConnectorRegistry:
    COLLECTION = "connectors"
    BATCHES = "connector_batches"

    def __init__(self, repository: Repository, bindings):
        self.repo = repository
        self.bindings = bindings

    def upsert(self, payload: Dict[str, Any], actor: str = "integration_engineer") -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        typ = str(payload.get("connector_type") or "").strip().lower()
        binding_id = str(payload.get("binding_id") or "").strip()
        if not name:
            raise ValueError("connector name is required")
        if typ not in CONNECTOR_TYPES:
            raise ValueError(f"unsupported connector_type: {typ}")
        if not binding_id or not self.bindings.get(binding_id):
            raise ValueError("a valid binding_id is required")
        key = str(payload.get("connector_id") or "CONN-" + hashlib.sha1(f"{name}:{typ}".encode()).hexdigest()[:12])
        reject_inline_secrets(payload.get("config") or {}, "connector.config")
        row = dict(payload)
        row.update({"connector_id": key, "name": name, "connector_type": typ, "binding_id": binding_id,
                    "updated_at": _now(), "updated_by": actor})
        row.setdefault("status", "draft")
        row.setdefault("config", {})
        row.setdefault("deployment", "edge")
        row.setdefault("tenant_id", default_tenant_id())
        row.setdefault("org_id", "")
        row.setdefault("site_id", "")
        row.setdefault("last_cursor", None)
        row.setdefault("last_batch_at", None)
        row.setdefault("last_status", "never_run")
        return self.repo.put(self.COLLECTION, key, row)

    def get(self, connector_id: str):
        return self.repo.get(self.COLLECTION, connector_id)

    def list(self, status: str = "", connector_type: str = "", limit: int = 200):
        rows = self.repo.list(self.COLLECTION, limit=limit)
        return [r for r in rows if (not status or r.get("status") == status) and (not connector_type or r.get("connector_type") == connector_type)]

    def approve(self, connector_id: str, actor: str = "integration_approver"):
        row = self.get(connector_id)
        if not row:
            raise KeyError(connector_id)
        binding = self.bindings.get(row["binding_id"])
        if not binding or binding.get("status") != "approved":
            raise ValueError("connector binding must be approved before connector approval")
        if (row.get("tenant_id") or default_tenant_id()) != (binding.get("tenant_id") or default_tenant_id()):
            raise ValueError("connector and binding tenant scope must match")
        if row.get("site_id") and binding.get("site_id") and row.get("site_id") != binding.get("site_id"):
            raise ValueError("connector and binding site scope must match")
        row.update({"status": "approved", "approved_at": _now(), "approved_by": actor})
        return self.repo.put(self.COLLECTION, connector_id, row)

    def retire(self, connector_id: str, actor: str = "integration_approver"):
        row = self.get(connector_id)
        if not row:
            raise KeyError(connector_id)
        row.update({"status": "retired", "retired_at": _now(), "retired_by": actor})
        return self.repo.put(self.COLLECTION, connector_id, row)

    def record_batch(self, connector_id: str, batch: Dict[str, Any], result: Dict[str, Any]):
        batch_id = str(batch["batch_id"])
        row = {"batch_id": batch_id, "connector_id": connector_id, "binding_id": batch["binding_id"],
               "source": batch.get("source") or {}, "cursor": batch.get("cursor"),
               "schema": batch.get("schema") or {}, "diagnostics": batch.get("diagnostics") or {},
               "record_count": len(batch.get("records") or []), "result": result, "processed_at": _now(),
               "tenant_id": (self.get(connector_id) or {}).get("tenant_id", default_tenant_id()),
               "org_id": (self.get(connector_id) or {}).get("org_id", ""), "site_id": (self.get(connector_id) or {}).get("site_id", "")}
        self.repo.put(self.BATCHES, batch_id, row)
        conn = self.get(connector_id)
        if conn:
            conn.update({"last_cursor": batch.get("cursor"), "last_batch_at": row["processed_at"],
                         "last_status": "success" if result.get("failed", 0) == 0 else "partial"})
            self.repo.put(self.COLLECTION, connector_id, conn)
        return row

    def batch(self, batch_id: str):
        return self.repo.get(self.BATCHES, batch_id)

    def batches(self, connector_id: str = "", limit: int = 100):
        rows = self.repo.list(self.BATCHES, limit=limit)
        return [r for r in rows if not connector_id or r.get("connector_id") == connector_id]


    def summary(self):
        rows=self.list(limit=1000); batches=self.batches(limit=1000)
        return {"registered":len(rows),"approved":sum(1 for x in rows if x.get("status")=="approved"),"retired":sum(1 for x in rows if x.get("status")=="retired"),"batches":len(batches),"partial":sum(1 for x in rows if x.get("last_status")=="partial")}

    def contract(self):
        return {
            "contract_version": "1.0",
            "connector_types": CONNECTOR_TYPES,
            "connector_lifecycle": ["draft", "approved", "retired"],
            "batch": {
                "required": ["batch_id", "connector_id", "binding_id", "records"],
                "optional": ["source", "schema", "cursor", "diagnostics", "agent_id", "observed_at"],
                "idempotency": "batch_id is globally idempotent; duplicate submissions return the stored result",
            },
            "responsibility": "Connector/Edge Agent performs vendor I/O; platform performs binding, schema, watermark, quality, DLQ and domain writes.",
        }


class ConnectorBatchProcessor:
    """Validates ConnectorBatch and forwards records into IntegrationRuntime."""
    def __init__(self, connectors: ConnectorRegistry, runtime, agents=None):
        self.connectors = connectors
        self.runtime = runtime
        self.agents = agents

    def submit(self, batch: Dict[str, Any], services: Dict[str, Any], actor: str = "edge_agent"):
        batch_id = str(batch.get("batch_id") or "").strip()
        connector_id = str(batch.get("connector_id") or "").strip()
        binding_id = str(batch.get("binding_id") or "").strip()
        records = batch.get("records")
        if not batch_id or not connector_id or not binding_id:
            raise ValueError("batch_id, connector_id and binding_id are required")
        if not isinstance(records, list):
            raise ValueError("records must be a list")
        previous = self.connectors.batch(batch_id)
        if previous:
            return {**previous["result"], "duplicate": True, "batch_id": batch_id}
        connector = self.connectors.get(connector_id)
        if not connector:
            raise KeyError(connector_id)
        if connector.get("status") != "approved":
            raise ValueError("only approved connectors may submit batches")
        if connector.get("binding_id") != binding_id:
            raise ValueError("batch binding_id does not match connector binding")
        agent_id = str(batch.get("agent_id") or "")
        if agent_id and self.agents:
            agent = self.agents.get(agent_id)
            if not agent or agent.get("status") not in {"online", "registered"}:
                raise ValueError("edge agent is not registered/online")
            if (agent.get("tenant_id") or default_tenant_id()) != (connector.get("tenant_id") or default_tenant_id()):
                raise ValueError("edge agent and connector tenant scope must match")
            agent_site = str(agent.get("site_id") or agent.get("site") or "")
            connector_site = str(connector.get("site_id") or "")
            if agent_site and connector_site and agent_site != connector_site:
                raise ValueError("edge agent and connector site scope must match")
        result = self.runtime.execute(binding_id, records, services, actor=actor)
        result.update({"batch_id": batch_id, "connector_id": connector_id, "connector_cursor": batch.get("cursor"),
                       "connector_diagnostics": batch.get("diagnostics") or {}, "duplicate": False})
        self.connectors.record_batch(connector_id, batch, result)
        return result
