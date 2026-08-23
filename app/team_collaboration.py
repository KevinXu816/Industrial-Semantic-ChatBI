"""V4.4 团队协作与责任闭环。

本模块只维护协作责任元数据（负责人、关注人、SLA、评论、交接），
不复制 RCA/CMMS/FMEA/Asset 的业务状态。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, List


UTC = timezone.utc
MENTION_RE = re.compile(r"@([A-Za-z0-9_.-]{2,80})")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str | None):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


class TeamCollaborationService:
    ITEM_COLLECTION = "team_collaboration_items"
    COMMENT_COLLECTION = "team_collaboration_comments"
    EVENT_COLLECTION = "team_collaboration_events"
    ALLOWED_RESOURCE_TYPES = {"asset", "rca", "work_order", "fmea"}

    def __init__(self, repository):
        self.repository = repository

    @staticmethod
    def _key(resource_type: str, resource_id: str) -> str:
        return f"{resource_type.strip().lower()}::{resource_id.strip()}"

    def _validate_resource(self, resource_type: str, resource_id: str):
        rt = (resource_type or "").strip().lower()
        rid = (resource_id or "").strip()
        if rt not in self.ALLOWED_RESOURCE_TYPES:
            raise ValueError("unsupported resource_type")
        if not rid:
            raise ValueError("resource_id is required")
        return rt, rid

    def _event(self, item: Dict[str, Any], event_type: str, actor: str, detail: Dict[str, Any] | None = None):
        at = _now()
        event_id = f"EV-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        row = {
            "event_id": event_id,
            "resource_type": item.get("resource_type"),
            "resource_id": item.get("resource_id"),
            "event_type": event_type,
            "actor": actor or "system",
            "detail": detail or {},
            "created_at": at,
        }
        self.repository.put(self.EVENT_COLLECTION, event_id, row)
        return row

    def get(self, resource_type: str, resource_id: str) -> Dict[str, Any] | None:
        rt, rid = self._validate_resource(resource_type, resource_id)
        row = self.repository.get(self.ITEM_COLLECTION, self._key(rt, rid))
        return self._decorate(dict(row)) if row else None

    def ensure(self, resource_type: str, resource_id: str, payload: Dict[str, Any] | None = None, actor: str = "system") -> Dict[str, Any]:
        rt, rid = self._validate_resource(resource_type, resource_id)
        payload = payload or {}
        key = self._key(rt, rid)
        current = self.repository.get(self.ITEM_COLLECTION, key)
        if current:
            row = dict(current)
            for field in ("title", "asset_id", "tenant_id", "site_id"):
                if payload.get(field):
                    row[field] = payload[field]
            row["updated_at"] = _now()
        else:
            row = {
                "collaboration_id": key,
                "resource_type": rt,
                "resource_id": rid,
                "title": payload.get("title") or rid,
                "asset_id": payload.get("asset_id") or (rid if rt == "asset" else ""),
                "tenant_id": payload.get("tenant_id") or "default",
                "site_id": payload.get("site_id") or "",
                "assignee": payload.get("assignee") or "",
                "watchers": list(dict.fromkeys(payload.get("watchers") or [])),
                "due_at": payload.get("due_at") or "",
                "status": "active",
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._event(row, "created", actor, {"title": row["title"]})
        self.repository.put(self.ITEM_COLLECTION, key, row)
        return self._decorate(row)

    def assign(self, resource_type: str, resource_id: str, assignee: str, actor: str, title: str = "", asset_id: str = ""):
        assignee = (assignee or "").strip()
        if not assignee:
            raise ValueError("assignee is required")
        row = self.ensure(resource_type, resource_id, {"title": title, "asset_id": asset_id}, actor=actor)
        raw = self.repository.get(self.ITEM_COLLECTION, row["collaboration_id"])
        before = raw.get("assignee") or ""
        raw["assignee"] = assignee
        raw["updated_at"] = _now()
        self.repository.put(self.ITEM_COLLECTION, raw["collaboration_id"], raw)
        self._event(raw, "assigned", actor, {"from": before, "to": assignee})
        return self._decorate(raw)

    def handoff(self, resource_type: str, resource_id: str, to_principal: str, actor: str, note: str = ""):
        to_principal = (to_principal or "").strip()
        if not to_principal:
            raise ValueError("to_principal is required")
        row = self.ensure(resource_type, resource_id, actor=actor)
        raw = self.repository.get(self.ITEM_COLLECTION, row["collaboration_id"])
        before = raw.get("assignee") or ""
        raw["assignee"] = to_principal
        raw["updated_at"] = _now()
        self.repository.put(self.ITEM_COLLECTION, raw["collaboration_id"], raw)
        self._event(raw, "handoff", actor, {"from": before, "to": to_principal, "note": note})
        return self._decorate(raw)

    def watch(self, resource_type: str, resource_id: str, principal_id: str, enabled: bool = True, actor: str = ""):
        principal_id = (principal_id or "").strip()
        if not principal_id:
            raise ValueError("principal_id is required")
        row = self.ensure(resource_type, resource_id, actor=actor or principal_id)
        raw = self.repository.get(self.ITEM_COLLECTION, row["collaboration_id"])
        watchers = list(raw.get("watchers") or [])
        if enabled and principal_id not in watchers:
            watchers.append(principal_id)
        if not enabled:
            watchers = [x for x in watchers if x != principal_id]
        raw["watchers"] = watchers
        raw["updated_at"] = _now()
        self.repository.put(self.ITEM_COLLECTION, raw["collaboration_id"], raw)
        self._event(raw, "watch" if enabled else "unwatch", actor or principal_id, {"principal_id": principal_id})
        return self._decorate(raw)

    def set_sla(self, resource_type: str, resource_id: str, actor: str, due_at: str = "", sla_hours: float | None = None):
        row = self.ensure(resource_type, resource_id, actor=actor)
        raw = self.repository.get(self.ITEM_COLLECTION, row["collaboration_id"])
        if sla_hours is not None:
            try:
                hours = float(sla_hours)
            except Exception as exc:
                raise ValueError("sla_hours must be numeric") from exc
            if hours <= 0:
                raise ValueError("sla_hours must be > 0")
            due = datetime.now(UTC) + timedelta(hours=hours)
        else:
            due = _parse_dt(due_at)
            if not due:
                raise ValueError("valid due_at or sla_hours is required")
        raw["due_at"] = due.isoformat().replace("+00:00", "Z")
        raw["updated_at"] = _now()
        self.repository.put(self.ITEM_COLLECTION, raw["collaboration_id"], raw)
        self._event(raw, "sla_updated", actor, {"due_at": raw["due_at"]})
        return self._decorate(raw)

    def add_comment(self, resource_type: str, resource_id: str, author: str, body: str):
        body = (body or "").strip()
        if not body:
            raise ValueError("comment body is required")
        row = self.ensure(resource_type, resource_id, actor=author)
        comment_id = f"CM-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        comment = {
            "comment_id": comment_id,
            "resource_type": row["resource_type"],
            "resource_id": row["resource_id"],
            "author": author or "anonymous",
            "body": body,
            "mentions": sorted(set(MENTION_RE.findall(body))),
            "created_at": _now(),
        }
        self.repository.put(self.COMMENT_COLLECTION, comment_id, comment)
        self._event(row, "comment", author or "anonymous", {"comment_id": comment_id, "mentions": comment["mentions"]})
        return comment

    def thread(self, resource_type: str, resource_id: str, limit: int = 200):
        rt, rid = self._validate_resource(resource_type, resource_id)
        item = self.get(rt, rid) or self.ensure(rt, rid)
        comments = [x for x in self.repository.list(self.COMMENT_COLLECTION, limit=1000) if x.get("resource_type") == rt and x.get("resource_id") == rid]
        events = [x for x in self.repository.list(self.EVENT_COLLECTION, limit=1000) if x.get("resource_type") == rt and x.get("resource_id") == rid]
        comments.sort(key=lambda x: x.get("created_at", ""))
        events.sort(key=lambda x: x.get("created_at", ""))
        return {"item": item, "comments": comments[-limit:], "events": events[-limit:]}

    def board(self, principal_id: str = "local-user", limit: int = 100):
        rows = [self._decorate(dict(x)) for x in self.repository.list(self.ITEM_COLLECTION, limit=1000) if x.get("status") != "closed"]
        rows.sort(key=lambda x: ({"overdue": 0, "due_soon": 1, "on_track": 2, "no_sla": 3}.get(x.get("sla_state"), 9), str(x.get("due_at") or "9999")))
        mine = [x for x in rows if x.get("assignee") == principal_id]
        watching = [x for x in rows if principal_id in (x.get("watchers") or []) and x.get("assignee") != principal_id]
        overdue = [x for x in rows if x.get("sla_state") == "overdue"]
        unassigned = [x for x in rows if not x.get("assignee")]
        summary = {
            "total": len(rows),
            "assigned_to_me": len(mine),
            "watching": len(watching),
            "overdue": len(overdue),
            "unassigned": len(unassigned),
        }
        return {
            "principal_id": principal_id,
            "summary": summary,
            "assigned_to_me": mine[:limit],
            "watching": watching[:limit],
            "overdue": overdue[:limit],
            "unassigned": unassigned[:limit],
            "all": rows[:limit],
            "semantics": "Collaboration metadata only; domain lifecycle remains owned by RCA/CMMS/FMEA/Asset services.",
        }

    @staticmethod
    def _decorate(row: Dict[str, Any]) -> Dict[str, Any]:
        due = _parse_dt(row.get("due_at"))
        if not due:
            state = "no_sla"
            remaining = None
        else:
            remaining = (due - datetime.now(UTC)).total_seconds() / 3600.0
            if remaining < 0:
                state = "overdue"
            elif remaining <= 24:
                state = "due_soon"
            else:
                state = "on_track"
        row["sla_state"] = state
        row["sla_remaining_hours"] = None if remaining is None else round(remaining, 2)
        return row


class CollaborationEscalationService:
    """V4.5 SLA 策略、升级、值班与通知契约。"""
    POLICY_COLLECTION = "collaboration_sla_policies"
    ONCALL_COLLECTION = "collaboration_oncall"
    ESCALATION_COLLECTION = "collaboration_escalations"
    NOTIFICATION_COLLECTION = "collaboration_notifications"

    def __init__(self, repository, collaboration: TeamCollaborationService):
        self.repository = repository
        self.collaboration = collaboration

    def upsert_policy(self, payload: Dict[str, Any], actor: str = "system"):
        policy_id = str(payload.get("policy_id") or f"SLA-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}")
        row = {
            "policy_id": policy_id,
            "name": str(payload.get("name") or policy_id),
            "resource_type": str(payload.get("resource_type") or "*").lower(),
            "sla_hours": float(payload.get("sla_hours") or 24),
            "due_soon_hours": float(payload.get("due_soon_hours") or 4),
            "escalate_after_hours": float(payload.get("escalate_after_hours") or 0),
            "escalate_to": str(payload.get("escalate_to") or ""),
            "channels": list(dict.fromkeys(payload.get("channels") or ["in_app"])),
            "enabled": bool(payload.get("enabled", True)),
            "updated_by": actor,
            "updated_at": _now(),
        }
        if row["sla_hours"] <= 0 or row["due_soon_hours"] < 0:
            raise ValueError("invalid SLA policy")
        self.repository.put(self.POLICY_COLLECTION, policy_id, row)
        return row

    def policies(self):
        return self.repository.list(self.POLICY_COLLECTION, limit=1000)

    def set_oncall(self, payload: Dict[str, Any], actor: str = "system"):
        schedule_id = str(payload.get("schedule_id") or f"ONCALL-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}")
        principals = [str(x).strip() for x in (payload.get("principals") or []) if str(x).strip()]
        if not principals:
            raise ValueError("principals are required")
        row = {
            "schedule_id": schedule_id,
            "name": str(payload.get("name") or schedule_id),
            "site_id": str(payload.get("site_id") or ""),
            "timezone": str(payload.get("timezone") or "UTC"),
            "principals": principals,
            "rotation_hours": int(payload.get("rotation_hours") or 8),
            "starts_at": str(payload.get("starts_at") or _now()),
            "enabled": bool(payload.get("enabled", True)),
            "updated_by": actor,
            "updated_at": _now(),
        }
        self.repository.put(self.ONCALL_COLLECTION, schedule_id, row)
        return {**row, "current_oncall": self.current_oncall(row)}

    def current_oncall(self, schedule: Dict[str, Any]):
        principals = schedule.get("principals") or []
        if not principals:
            return ""
        start = _parse_dt(schedule.get("starts_at")) or datetime.now(UTC)
        rotation = max(1, int(schedule.get("rotation_hours") or 8))
        elapsed = max(0, (datetime.now(UTC) - start).total_seconds())
        index = int(elapsed // (rotation * 3600)) % len(principals)
        return principals[index]

    def oncall(self):
        rows = []
        for row in self.repository.list(self.ONCALL_COLLECTION, limit=1000):
            rows.append({**row, "current_oncall": self.current_oncall(row)})
        return rows

    def notification_contract(self):
        return {
            "channels": ["in_app", "email", "teams", "slack", "webhook"],
            "payload": ["notification_id", "channel", "recipient", "severity", "title", "body", "resource", "correlation_id"],
            "semantics": "Core platform creates governed notification intents. External adapters perform actual delivery.",
        }

    def _policy_for(self, item: Dict[str, Any]):
        enabled = [x for x in self.policies() if x.get("enabled", True)]
        exact = [x for x in enabled if x.get("resource_type") == item.get("resource_type")]
        wildcard = [x for x in enabled if x.get("resource_type") == "*"]
        return (exact or wildcard or [None])[0]

    def evaluate(self, actor: str = "system"):
        board = self.collaboration.board("__system__", limit=1000)
        created = []
        for item in board.get("all") or []:
            if item.get("sla_state") not in {"overdue", "due_soon"}:
                continue
            policy = self._policy_for(item)
            if not policy:
                continue
            escalation_id = f"ESC::{item['collaboration_id']}::{item.get('due_at','')}::{item.get('sla_state')}"
            if self.repository.get(self.ESCALATION_COLLECTION, escalation_id):
                continue
            recipient = policy.get("escalate_to") or item.get("assignee") or ""
            if not recipient:
                # Fall back to current on-call for the same site.
                schedules = [x for x in self.oncall() if x.get("enabled", True) and (not x.get("site_id") or x.get("site_id") == item.get("site_id"))]
                recipient = schedules[0].get("current_oncall") if schedules else ""
            row = {
                "escalation_id": escalation_id,
                "resource_type": item.get("resource_type"),
                "resource_id": item.get("resource_id"),
                "collaboration_id": item.get("collaboration_id"),
                "severity": "critical" if item.get("sla_state") == "overdue" else "warning",
                "state": item.get("sla_state"),
                "recipient": recipient,
                "policy_id": policy.get("policy_id"),
                "status": "open",
                "created_by": actor,
                "created_at": _now(),
            }
            self.repository.put(self.ESCALATION_COLLECTION, escalation_id, row)
            created.append(row)
            for channel in policy.get("channels") or ["in_app"]:
                nid = f"NTF-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}-{channel}"
                notification = {
                    "notification_id": nid,
                    "channel": channel,
                    "recipient": recipient,
                    "severity": row["severity"],
                    "title": f"SLA {item.get('sla_state')}: {item.get('title') or item.get('resource_id')}",
                    "body": f"{item.get('resource_type')} {item.get('resource_id')} requires attention.",
                    "resource": {"type": item.get("resource_type"), "id": item.get("resource_id")},
                    "correlation_id": escalation_id,
                    "delivery_status": "intent_created",
                    "created_at": _now(),
                }
                self.repository.put(self.NOTIFICATION_COLLECTION, nid, notification)
        return {"created": len(created), "escalations": created, "semantics": "Escalation creates responsibility/notification intents only; domain approval remains unchanged."}

    def escalations(self, status: str = ""):
        rows = self.repository.list(self.ESCALATION_COLLECTION, limit=1000)
        if status:
            rows = [x for x in rows if x.get("status") == status]
        return rows

    def notifications(self, recipient: str = ""):
        rows = self.repository.list(self.NOTIFICATION_COLLECTION, limit=1000)
        if recipient:
            rows = [x for x in rows if x.get("recipient") == recipient]
        return rows
