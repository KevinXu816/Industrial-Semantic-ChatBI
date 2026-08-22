"""V2.2 governed industrial data binding and mapping contracts.

The studio maps external source records into existing domain APIs without creating a
second source of truth. Connector execution remains adapter-driven; preview/execute
accept records explicitly so the contract is testable without vendor dependencies.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List
import hashlib
from .persistence import Repository
from .enterprise_identity import default_tenant_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


TARGETS = {
    "asset": {"required": ["asset_id"], "allowed": ["asset_id", "name", "asset_type", "parent_asset_id", "status"]},
    "sensor_binding": {"required": ["asset_id", "sensor"], "allowed": ["asset_id", "sensor", "component_id", "unit", "source"]},
    "condition_series": {"required": ["asset_id", "sensor", "value"], "allowed": ["asset_id", "sensor", "value", "timestamp"]},
    "alarm": {"required": ["asset_id", "alarm"], "allowed": ["asset_id", "alarm", "severity", "timestamp", "status"]},
    "work_order": {"required": ["asset_id", "recommended_action"], "allowed": ["asset_id", "component", "failure_mode", "priority", "recommended_action", "external_work_order_id", "status"]},
}


class DataBindingStore:
    COLLECTION = "data_bindings"
    RUNS = "data_binding_runs"

    def __init__(self, repository: Repository):
        self.repo = repository

    def upsert(self, payload: Dict[str, Any], actor: str = "data_engineer") -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        target = str(payload.get("target") or "").strip()
        if not name:
            raise ValueError("binding name is required")
        if target not in TARGETS:
            raise ValueError(f"unsupported target: {target}")
        mappings = payload.get("mappings") or {}
        if not isinstance(mappings, dict) or not mappings:
            raise ValueError("mappings are required")
        missing = [f for f in TARGETS[target]["required"] if f not in mappings]
        if missing:
            raise ValueError("missing target mappings: " + ", ".join(missing))
        unknown = [f for f in mappings if f not in TARGETS[target]["allowed"]]
        if unknown:
            raise ValueError("unknown target fields: " + ", ".join(unknown))
        key = str(payload.get("binding_id") or hashlib.sha1(name.encode()).hexdigest()[:16])
        row = dict(payload)
        row.update({"binding_id": key, "name": name, "target": target, "updated_at": _now(), "updated_by": actor})
        row.setdefault("status", "draft")
        row.setdefault("source_type", "api")
        row.setdefault("source_id", "")
        row.setdefault("schedule", "on_demand")
        row.setdefault("tenant_id", default_tenant_id())
        row.setdefault("org_id", "")
        row.setdefault("site_id", "")
        return self.repo.put(self.COLLECTION, key, row)

    def get(self, key: str):
        return self.repo.get(self.COLLECTION, key)

    def list(self, status: str = "", target: str = "", limit: int = 200):
        rows = self.repo.list(self.COLLECTION, limit=limit)
        return [r for r in rows if (not status or r.get("status") == status) and (not target or r.get("target") == target)]

    def approve(self, key: str, actor: str = "data_governor"):
        row = self.get(key)
        if not row:
            raise KeyError(key)
        row.update({"status": "approved", "approved_at": _now(), "approved_by": actor})
        return self.repo.put(self.COLLECTION, key, row)

    def preview(self, key: str, records: List[Dict[str, Any]], limit: int = 20):
        row = self.get(key)
        if not row:
            raise KeyError(key)
        transformed, errors = self._transform(row, records[:limit])
        return {"binding_id": key, "target": row["target"], "records": transformed, "errors": errors, "preview": True}

    def execute(self, key: str, records: List[Dict[str, Any]], services: Dict[str, Any], actor: str = "system"):
        row = self.get(key)
        if not row:
            raise KeyError(key)
        if row.get("status") != "approved":
            raise ValueError("only approved data bindings may execute")
        transformed, errors = self._transform(row, records)
        succeeded = 0
        outputs = []
        for item in transformed:
            try:
                # Scope metadata is governed by the approved binding, never trusted from source records.
                item = dict(item)
                item.setdefault("tenant_id", row.get("tenant_id") or default_tenant_id())
                item.setdefault("org_id", row.get("org_id") or "")
                item.setdefault("site_id", row.get("site_id") or "")
                outputs.append(self._write(row["target"], item, services, actor))
                succeeded += 1
            except Exception as exc:
                errors.append({"record": item, "error": str(exc)})
        run_id = "DBR-" + hashlib.sha1(f"{key}:{_now()}".encode()).hexdigest()[:16]
        result = {"run_id": run_id, "binding_id": key, "target": row["target"], "received": len(records), "succeeded": succeeded, "failed": len(errors), "errors": errors[:50], "outputs": outputs[:50], "executed_at": _now(), "executed_by": actor}
        self.repo.put(self.RUNS, run_id, result)
        return result

    def runs(self, binding_id: str = "", limit: int = 100):
        rows = self.repo.list(self.RUNS, limit=limit)
        return [r for r in rows if not binding_id or r.get("binding_id") == binding_id]

    def contract(self):
        return {"targets": TARGETS, "source_types": ["influxdb", "historian", "doris", "mysql", "postgresql", "api", "mqtt", "csv"], "execution": "Adapter-driven. External collectors/schedulers fetch records, then invoke an approved binding; preview never writes domain data."}

    def _transform(self, binding, records):
        mappings = binding.get("mappings") or {}
        defaults = binding.get("defaults") or {}
        transformed, errors = [], []
        for idx, src in enumerate(records):
            out = dict(defaults)
            for target_field, source_field in mappings.items():
                if isinstance(source_field, str) and source_field.startswith("$literal:"):
                    out[target_field] = source_field[len("$literal:"):]
                else:
                    out[target_field] = src.get(str(source_field))
            missing = [f for f in TARGETS[binding["target"]]["required"] if out.get(f) in (None, "")]
            if missing:
                errors.append({"index": idx, "error": "missing required values: " + ", ".join(missing)})
            else:
                transformed.append(out)
        return transformed, errors

    def _write(self, target, item, services, actor):
        if target == "asset":
            return services["asset_registry"].upsert_asset(item, actor=actor)
        if target == "sensor_binding":
            asset_id = str(item.pop("asset_id"))
            return services["asset_registry"].bind_sensor(asset_id, item, actor=actor)
        if target == "condition_series":
            # Runtime samples remain explicit inputs to the governed condition pipeline.
            return {"accepted": True, **item, "semantics": "condition sample accepted for downstream feature-pipeline adapter"}
        if target == "alarm":
            return {"accepted": True, **item, "semantics": "alarm normalized; persist through customer alarm adapter/event store"}
        if target == "work_order":
            payload = dict(item); payload["asset"] = payload.pop("asset_id"); payload.pop("external_work_order_id", None); payload.pop("status", None)
            return services["cmms_candidates"].create(payload, actor=actor)
        raise ValueError(target)
