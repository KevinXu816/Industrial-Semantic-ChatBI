"""V2.3 Integration Runtime & Data Quality control plane.

The core deliberately does not fetch vendor data. External adapters/collectors submit
records. This service governs incremental cursors, schema fingerprints, quality rules,
retry/dead-letter handling, schedule metadata and run monitoring.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List
import hashlib, json
from .persistence import Repository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _schema_of(records: List[Dict[str, Any]]) -> Dict[str, str]:
    schema: Dict[str, str] = {}
    for row in records[:100]:
        for k, v in row.items():
            t = "null" if v is None else type(v).__name__
            prev = schema.get(str(k))
            schema[str(k)] = t if prev in (None, t) else "mixed"
    return dict(sorted(schema.items()))


def _fingerprint(schema: Dict[str, str]) -> str:
    raw = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class IntegrationRuntimeService:
    STATE = "integration_binding_state"
    DLQ = "integration_dead_letters"
    EVENTS = "integration_runtime_events"
    RULES = "integration_quality_rules"

    def __init__(self, repository: Repository, bindings):
        self.repo = repository
        self.bindings = bindings

    def configure(self, binding_id: str, payload: Dict[str, Any], actor: str = "data_engineer"):
        binding = self.bindings.get(binding_id)
        if not binding:
            raise KeyError(binding_id)
        state = self.repo.get(self.STATE, binding_id) or {"binding_id": binding_id}
        state.update({
            "schedule": payload.get("schedule", state.get("schedule", binding.get("schedule", "on_demand"))),
            "watermark_field": payload.get("watermark_field", state.get("watermark_field", "")),
            "watermark": payload.get("watermark", state.get("watermark")),
            "max_retries": int(payload.get("max_retries", state.get("max_retries", 3))),
            "schema_policy": payload.get("schema_policy", state.get("schema_policy", "block")),
            "stale_after_minutes": int(payload.get("stale_after_minutes", state.get("stale_after_minutes", 60))),
            "updated_at": _now(), "updated_by": actor,
        })
        self.repo.put(self.STATE, binding_id, state)
        return state

    def state(self, binding_id: str):
        if not self.bindings.get(binding_id): raise KeyError(binding_id)
        return self.repo.get(self.STATE, binding_id) or self.configure(binding_id, {}, actor="bootstrap")

    def add_quality_rule(self, binding_id: str, payload: Dict[str, Any], actor: str = "data_governor"):
        if not self.bindings.get(binding_id): raise KeyError(binding_id)
        rule_type = str(payload.get("rule_type") or "").strip()
        if rule_type not in {"not_null", "range", "allowed_values", "freshness"}:
            raise ValueError("unsupported quality rule")
        field = str(payload.get("field") or "").strip()
        if not field: raise ValueError("quality rule field is required")
        rid = str(payload.get("rule_id") or "DQR-" + hashlib.sha1(f"{binding_id}:{field}:{rule_type}:{_now()}".encode()).hexdigest()[:12])
        row = {**payload, "rule_id": rid, "binding_id": binding_id, "rule_type": rule_type, "field": field,
               "status": payload.get("status", "active"), "updated_at": _now(), "updated_by": actor}
        return self.repo.put(self.RULES, rid, row)

    def quality_rules(self, binding_id: str = "", limit: int = 500):
        rows = self.repo.list(self.RULES, limit=limit)
        return [x for x in rows if (not binding_id or x.get("binding_id") == binding_id)]

    def inspect_schema(self, binding_id: str, records: List[Dict[str, Any]], accept: bool = False, actor: str = "runtime"):
        state = self.state(binding_id)
        schema = _schema_of(records)
        fp = _fingerprint(schema)
        previous = state.get("schema_fingerprint")
        drift = bool(previous and previous != fp)
        result = {"binding_id": binding_id, "schema": schema, "fingerprint": fp,
                  "previous_fingerprint": previous, "drift": drift, "policy": state.get("schema_policy", "block")}
        if not previous or accept:
            state.update({"schema": schema, "schema_fingerprint": fp, "schema_updated_at": _now(), "schema_updated_by": actor})
            self.repo.put(self.STATE, binding_id, state)
            result["accepted"] = True
        else:
            result["accepted"] = False
        return result

    def _quality(self, binding_id: str, records: List[Dict[str, Any]]):
        rules = [r for r in self.quality_rules(binding_id) if r.get("status") == "active"]
        passed, rejected, issues = [], [], []
        for idx, row in enumerate(records):
            errs = []
            for rule in rules:
                f, typ = rule["field"], rule["rule_type"]
                v = row.get(f)
                if typ == "not_null" and v in (None, ""):
                    errs.append(f"{f}: not_null")
                elif typ == "range" and v is not None:
                    try:
                        n=float(v); lo=rule.get("min"); hi=rule.get("max")
                        if lo is not None and n < float(lo): errs.append(f"{f}: below min {lo}")
                        if hi is not None and n > float(hi): errs.append(f"{f}: above max {hi}")
                    except Exception: errs.append(f"{f}: not numeric")
                elif typ == "allowed_values" and v not in (rule.get("values") or []):
                    errs.append(f"{f}: value not allowed")
                elif typ == "freshness" and v:
                    try:
                        ts=datetime.fromisoformat(str(v).replace("Z", "+00:00")); age=(datetime.now(timezone.utc)-ts.astimezone(timezone.utc)).total_seconds()/60
                        max_age=float(rule.get("max_age_minutes", 60))
                        if age > max_age: errs.append(f"{f}: stale {age:.1f}m > {max_age}m")
                    except Exception: errs.append(f"{f}: invalid timestamp")
            if errs:
                rejected.append(row); issues.append({"index": idx, "errors": errs})
            else: passed.append(row)
        return passed, rejected, issues

    def execute(self, binding_id: str, records: List[Dict[str, Any]], services: Dict[str, Any], actor: str = "runtime"):
        state = self.state(binding_id)
        schema = self.inspect_schema(binding_id, records, accept=False, actor=actor)
        if schema["drift"] and state.get("schema_policy", "block") == "block":
            event=self._event(binding_id, "schema_drift_blocked", {"schema": schema})
            raise ValueError(f"schema drift detected; approve schema before execution ({event['event_id']})")
        if not state.get("schema_fingerprint"):
            self.inspect_schema(binding_id, records, accept=True, actor=actor)
            state = self.state(binding_id)  # preserve schema baseline before watermark updates

        wf = state.get("watermark_field")
        incoming = records
        if wf and state.get("watermark") not in (None, ""):
            incoming = [r for r in records if r.get(wf) is not None and str(r.get(wf)) > str(state.get("watermark"))]

        good, bad, quality_issues = self._quality(binding_id, incoming)
        for row, issue in zip(bad, quality_issues): self._dead_letter(binding_id, row, "data_quality", issue, actor)

        result = self.bindings.execute(binding_id, good, services, actor=actor)
        for err in result.get("errors") or []:
            self._dead_letter(binding_id, err.get("record") or {}, "binding_execution", err, actor)

        if wf and good:
            values=[r.get(wf) for r in good if r.get(wf) is not None]
            if values:
                state["watermark"] = max(values, key=lambda x: str(x))
        state.update({"last_run_at": _now(), "last_run_id": result["run_id"], "last_status": "success" if not result["failed"] else "partial", "updated_at": _now()})
        self.repo.put(self.STATE, binding_id, state)
        result.update({"incremental_received": len(incoming), "quality_rejected": len(bad), "quality_issues": quality_issues[:50], "watermark": state.get("watermark"), "schema": schema})
        return result

    def accept_schema(self, binding_id: str, records: List[Dict[str, Any]], actor: str = "data_governor"):
        return self.inspect_schema(binding_id, records, accept=True, actor=actor)

    def _dead_letter(self, binding_id, record, category, error, actor):
        key="DLQ-"+hashlib.sha1(f"{binding_id}:{_now()}:{record}".encode()).hexdigest()[:16]
        row={"dead_letter_id":key,"binding_id":binding_id,"record":record,"category":category,"error":error,"status":"open","created_at":_now(),"created_by":actor,"retry_count":0}
        self.repo.put(self.DLQ,key,row); return row

    def dead_letters(self, binding_id: str = "", status: str = "", limit: int = 200):
        rows=self.repo.list(self.DLQ,limit=limit)
        return [r for r in rows if (not binding_id or r.get("binding_id")==binding_id) and (not status or r.get("status")==status)]

    def retry_dead_letter(self, dead_letter_id: str, services: Dict[str, Any], actor: str = "operator"):
        row=self.repo.get(self.DLQ,dead_letter_id)
        if not row: raise KeyError(dead_letter_id)
        state=self.state(row["binding_id"]); max_retries=int(state.get("max_retries",3))
        if int(row.get("retry_count",0)) >= max_retries: raise ValueError("maximum retries exceeded")
        row["retry_count"]=int(row.get("retry_count",0))+1; row["last_retry_at"]=_now(); row["last_retry_by"]=actor
        try:
            result=self.bindings.execute(row["binding_id"],[row["record"]],services,actor=actor)
            if result.get("failed",0)==0: row["status"]="resolved"; row["resolved_at"]=_now()
            else: row["last_error"]=result.get("errors")
        except Exception as exc: row["last_error"]=str(exc)
        self.repo.put(self.DLQ,dead_letter_id,row); return row

    def _event(self,binding_id,event_type,detail):
        key="IRE-"+hashlib.sha1(f"{binding_id}:{event_type}:{_now()}".encode()).hexdigest()[:16]
        row={"event_id":key,"binding_id":binding_id,"type":event_type,"detail":detail,"created_at":_now()}; self.repo.put(self.EVENTS,key,row); return row

    def monitoring(self):
        bindings=self.bindings.list(limit=1000); states=[self.state(b["binding_id"]) for b in bindings]
        dlq=self.dead_letters(limit=1000)
        return {"bindings":len(bindings),"configured":len(states),"with_watermark":sum(1 for s in states if s.get("watermark_field")),"schema_baselined":sum(1 for s in states if s.get("schema_fingerprint")),"dlq_open":sum(1 for x in dlq if x.get("status")=="open"),"quality_rules":len(self.quality_rules(limit=1000)),"states":states[:100]}
