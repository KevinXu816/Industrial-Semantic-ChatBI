"""V4.6 交接班日志与责任连续性。

本模块维护班次交接元数据、班次日志和双方确认；不复制或修改
RCA/CMMS/FMEA/Asset 的领域生命周期状态。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

UTC = timezone.utc


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


class ShiftHandoverService:
    SHIFT_COLLECTION = "operations_shift_definitions"
    LOG_COLLECTION = "operations_logbook"
    HANDOVER_COLLECTION = "operations_handovers"
    ACK_COLLECTION = "operations_handover_acknowledgements"

    def __init__(self, repository, collaboration, escalation=None):
        self.repository = repository
        self.collaboration = collaboration
        self.escalation = escalation

    def upsert_shift(self, payload: Dict[str, Any], actor: str = "system"):
        shift_id = str(payload.get("shift_id") or f"SHIFT-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}")
        duration_hours = float(payload.get("duration_hours") or 8)
        if duration_hours <= 0 or duration_hours > 24:
            raise ValueError("duration_hours must be in (0, 24]")
        row = {
            "shift_id": shift_id,
            "name": str(payload.get("name") or shift_id),
            "site_id": str(payload.get("site_id") or ""),
            "timezone": str(payload.get("timezone") or "UTC"),
            "start_hour": int(payload.get("start_hour") or 0) % 24,
            "duration_hours": duration_hours,
            "enabled": bool(payload.get("enabled", True)),
            "updated_by": actor,
            "updated_at": _now(),
        }
        self.repository.put(self.SHIFT_COLLECTION, shift_id, row)
        return row

    def shifts(self):
        return self.repository.list(self.SHIFT_COLLECTION, limit=1000)

    def current_shift(self, site_id: str = ""):
        now = datetime.now(UTC)
        candidates = [x for x in self.shifts() if x.get("enabled", True) and (not site_id or not x.get("site_id") or x.get("site_id") == site_id)]
        for row in candidates:
            start_hour = int(row.get("start_hour") or 0)
            duration = float(row.get("duration_hours") or 8)
            base = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            if base > now:
                base -= timedelta(days=1)
            end = base + timedelta(hours=duration)
            if base <= now < end:
                return {**row, "current_start": base.isoformat().replace("+00:00", "Z"), "current_end": end.isoformat().replace("+00:00", "Z")}
        return candidates[0] if candidates else None

    def add_log(self, payload: Dict[str, Any], actor: str = "system"):
        body = str(payload.get("body") or "").strip()
        if not body:
            raise ValueError("body is required")
        log_id = str(payload.get("log_id") or f"LOG-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}")
        row = {
            "log_id": log_id,
            "site_id": str(payload.get("site_id") or ""),
            "shift_id": str(payload.get("shift_id") or ""),
            "category": str(payload.get("category") or "operations"),
            "severity": str(payload.get("severity") or "info"),
            "asset_id": str(payload.get("asset_id") or ""),
            "resource_type": str(payload.get("resource_type") or ""),
            "resource_id": str(payload.get("resource_id") or ""),
            "body": body,
            "author": actor or "system",
            "created_at": _now(),
        }
        self.repository.put(self.LOG_COLLECTION, log_id, row)
        return row

    def logs(self, site_id: str = "", shift_id: str = "", limit: int = 200):
        rows = self.repository.list(self.LOG_COLLECTION, limit=1000)
        if site_id:
            rows = [x for x in rows if x.get("site_id") == site_id]
        if shift_id:
            rows = [x for x in rows if x.get("shift_id") == shift_id]
        return rows[:limit]

    def _open_items_snapshot(self, site_id: str = "") -> List[Dict[str, Any]]:
        board = self.collaboration.board("__handover__", limit=1000)
        rows = []
        for item in board.get("all") or []:
            if site_id and item.get("site_id") and item.get("site_id") != site_id:
                continue
            rows.append({
                "resource_type": item.get("resource_type"),
                "resource_id": item.get("resource_id"),
                "title": item.get("title") or item.get("resource_id"),
                "asset_id": item.get("asset_id") or "",
                "assignee": item.get("assignee") or "",
                "sla_state": item.get("sla_state") or "no_sla",
                "due_at": item.get("due_at") or "",
            })
        rows.sort(key=lambda x: ({"overdue": 0, "due_soon": 1, "on_track": 2, "no_sla": 3}.get(x.get("sla_state"), 9), x.get("due_at") or "9999"))
        return rows

    def create_handover(self, payload: Dict[str, Any], actor: str = "system"):
        site_id = str(payload.get("site_id") or "")
        outgoing = str(payload.get("outgoing_principal") or actor or "").strip()
        incoming = str(payload.get("incoming_principal") or "").strip()
        if not outgoing or not incoming:
            raise ValueError("outgoing_principal and incoming_principal are required")
        handover_id = str(payload.get("handover_id") or f"HO-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}")
        current = self.current_shift(site_id) or {}
        shift_id = str(payload.get("shift_id") or current.get("shift_id") or "")
        items = self._open_items_snapshot(site_id)
        logs = self.logs(site_id=site_id, shift_id=shift_id, limit=100)
        escalations = []
        if self.escalation:
            escalations = [x for x in self.escalation.escalations("open") if not site_id or not x.get("site_id") or x.get("site_id") == site_id]
        summary = {
            "open_items": len(items),
            "overdue_items": sum(1 for x in items if x.get("sla_state") == "overdue"),
            "due_soon_items": sum(1 for x in items if x.get("sla_state") == "due_soon"),
            "log_entries": len(logs),
            "open_escalations": len(escalations),
        }
        row = {
            "handover_id": handover_id,
            "site_id": site_id,
            "shift_id": shift_id,
            "outgoing_principal": outgoing,
            "incoming_principal": incoming,
            "status": "pending_ack",
            "notes": str(payload.get("notes") or ""),
            "summary": summary,
            "open_items": items,
            "log_entries": logs,
            "open_escalations": escalations,
            "created_by": actor or outgoing,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.repository.put(self.HANDOVER_COLLECTION, handover_id, row)
        # Outgoing confirmation is implicit at creation and independently auditable.
        self._ack(handover_id, outgoing, "outgoing", actor or outgoing, "交班人已提交")
        return self.get_handover(handover_id)

    def _ack(self, handover_id: str, principal_id: str, role: str, actor: str, note: str = ""):
        ack_id = f"ACK::{handover_id}::{role}::{principal_id}"
        row = {
            "ack_id": ack_id,
            "handover_id": handover_id,
            "principal_id": principal_id,
            "role": role,
            "note": note,
            "actor": actor,
            "acknowledged_at": _now(),
        }
        self.repository.put(self.ACK_COLLECTION, ack_id, row)
        return row

    def acknowledge(self, handover_id: str, principal_id: str, actor: str = "system", note: str = ""):
        row = self.repository.get(self.HANDOVER_COLLECTION, handover_id)
        if not row:
            raise ValueError("handover not found")
        if principal_id != row.get("incoming_principal"):
            raise ValueError("only incoming_principal can acknowledge handover")
        self._ack(handover_id, principal_id, "incoming", actor or principal_id, note)
        row = dict(row)
        row["status"] = "accepted"
        row["accepted_at"] = _now()
        row["updated_at"] = _now()
        self.repository.put(self.HANDOVER_COLLECTION, handover_id, row)
        return self.get_handover(handover_id)

    def get_handover(self, handover_id: str):
        row = self.repository.get(self.HANDOVER_COLLECTION, handover_id)
        if not row:
            return None
        acks = [x for x in self.repository.list(self.ACK_COLLECTION, limit=1000) if x.get("handover_id") == handover_id]
        return {**row, "acknowledgements": acks, "outgoing_ack": any(x.get("role") == "outgoing" for x in acks), "incoming_ack": any(x.get("role") == "incoming" for x in acks)}

    def handovers(self, site_id: str = "", status: str = "", limit: int = 100):
        rows = self.repository.list(self.HANDOVER_COLLECTION, limit=1000)
        if site_id:
            rows = [x for x in rows if x.get("site_id") == site_id]
        if status:
            rows = [x for x in rows if x.get("status") == status]
        return [self.get_handover(x.get("handover_id")) for x in rows[:limit]]

    def dashboard(self, site_id: str = ""):
        current = self.current_shift(site_id)
        handovers = self.handovers(site_id=site_id, limit=20)
        pending = [x for x in handovers if x.get("status") == "pending_ack"]
        items = self._open_items_snapshot(site_id)
        logs = self.logs(site_id=site_id, shift_id=(current or {}).get("shift_id", ""), limit=50)
        return {
            "site_id": site_id,
            "current_shift": current,
            "summary": {
                "open_items": len(items),
                "overdue_items": sum(1 for x in items if x.get("sla_state") == "overdue"),
                "pending_handovers": len(pending),
                "shift_logs": len(logs),
            },
            "priority_items": items[:20],
            "pending_handovers": pending[:20],
            "recent_logs": logs[:20],
            "semantics": "Handover snapshots responsibility and acknowledgement only; RCA/CMMS/FMEA/Asset lifecycle remains authoritative in their domain services.",
        }
