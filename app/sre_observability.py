"""V2.9 Observability & SRE control plane.

The module is deliberately dependency-light. It implements W3C trace-context
compatible IDs and durable platform telemetry. If OpenTelemetry is installed,
operators can bridge the same trace/correlation IDs to an external collector
without changing the application contracts.
"""
from __future__ import annotations

import math
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from .persistence import Repository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_trace_id() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex[:0]  # 32 hex chars


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]


def parse_traceparent(value: str) -> Dict[str, str]:
    """Parse W3C traceparent: version-traceid-parentid-flags."""
    parts = str(value or "").strip().split("-")
    if len(parts) == 4 and len(parts[1]) == 32 and len(parts[2]) == 16:
        try:
            int(parts[1], 16); int(parts[2], 16); int(parts[3], 16)
            return {"trace_id": parts[1].lower(), "parent_span_id": parts[2].lower(), "trace_flags": parts[3].lower()}
        except Exception:
            pass
    return {}


def traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    return f"00-{trace_id}-{span_id}-{'01' if sampled else '00'}"


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    vals = sorted(float(x) for x in values)
    if len(vals) == 1:
        return round(vals[0], 2)
    idx = (len(vals) - 1) * p
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return round(vals[lo], 2)
    out = vals[lo] + (vals[hi] - vals[lo]) * (idx - lo)
    return round(out, 2)


class TelemetryStore:
    SPANS = "observability_spans"
    DEPENDENCIES = "observability_dependencies"
    SLOS = "observability_slos"
    ALERT_RULES = "observability_alert_rules"
    ALERTS = "observability_alerts"

    def __init__(self, repository: Repository):
        self.repo = repository
        self._bootstrap_defaults()

    def _bootstrap_defaults(self):
        defaults = [
            {"slo_id": "platform-availability", "name": "Platform Availability", "metric": "availability", "target": 99.9, "window_minutes": 60, "status": "active"},
            {"slo_id": "platform-latency-p95", "name": "HTTP p95 Latency", "metric": "latency_p95_ms", "target": 1500.0, "comparison": "lte", "window_minutes": 60, "status": "active"},
        ]
        for row in defaults:
            if not self.repo.get(self.SLOS, row["slo_id"]):
                row.update({"created_at": _now(), "updated_at": _now(), "created_by": "bootstrap"})
                self.repo.put(self.SLOS, row["slo_id"], row)

    def record_span(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(payload)
        row.setdefault("span_id", new_span_id())
        row.setdefault("trace_id", new_trace_id())
        row.setdefault("kind", "internal")
        row.setdefault("service", "industrial-semantic-platform")
        row.setdefault("status", "ok")
        row.setdefault("started_at", _now())
        row.setdefault("ended_at", _now())
        row.setdefault("duration_ms", 0.0)
        row.setdefault("attributes", {})
        row.setdefault("created_at", _now())
        key = f"{row['trace_id']}:{row['span_id']}"
        self.repo.put(self.SPANS, key, row)
        return row

    def spans(self, trace_id: str = "", service: str = "", status: str = "", limit: int = 500) -> List[dict]:
        rows = self.repo.list(self.SPANS, limit=min(max(limit, 1), 1000))
        out = []
        for row in rows:
            if trace_id and row.get("trace_id") != trace_id: continue
            if service and row.get("service") != service: continue
            if status and row.get("status") != status: continue
            out.append(row)
        return out

    def trace(self, trace_id: str) -> Dict[str, Any]:
        rows = self.spans(trace_id=trace_id, limit=1000)
        rows.sort(key=lambda x: str(x.get("started_at", "")))
        total = sum(float(x.get("duration_ms", 0) or 0) for x in rows if not x.get("parent_span_id"))
        return {"trace_id": trace_id, "spans": rows, "root_duration_ms": round(total, 2), "span_count": len(rows)}

    def http_metrics(self, limit: int = 1000) -> Dict[str, Any]:
        rows = [r for r in self.repo.list(self.SPANS, limit=limit) if r.get("kind") == "server"]
        durations = [float(r.get("duration_ms", 0) or 0) for r in rows]
        total = len(rows)
        errors = sum(1 for r in rows if r.get("status") == "error" or int((r.get("attributes") or {}).get("http.status_code", 200)) >= 500)
        denied = sum(1 for r in rows if int((r.get("attributes") or {}).get("http.status_code", 200)) in {401, 403})
        by_route: Dict[str, dict] = {}
        for r in rows:
            attrs = r.get("attributes") or {}
            route = str(attrs.get("http.route") or attrs.get("http.target") or "unknown")
            b = by_route.setdefault(route, {"requests": 0, "errors": 0, "durations": []})
            b["requests"] += 1
            if r.get("status") == "error": b["errors"] += 1
            b["durations"].append(float(r.get("duration_ms", 0) or 0))
        routes = []
        for route, b in by_route.items():
            routes.append({"route": route, "requests": b["requests"], "errors": b["errors"], "p95_ms": _percentile(b["durations"], .95)})
        routes.sort(key=lambda x: (x["errors"], x["p95_ms"]), reverse=True)
        return {
            "requests": total,
            "errors": errors,
            "denied": denied,
            "availability_pct": round(100.0 * (total-errors) / max(total, 1), 3),
            "error_rate_pct": round(100.0 * errors / max(total, 1), 3),
            "latency_ms": {"avg": round(sum(durations)/max(len(durations),1),2), "p50": _percentile(durations,.50), "p95": _percentile(durations,.95), "p99": _percentile(durations,.99)},
            "routes": routes[:30],
        }

    def set_dependency(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        row = {"name": name, **payload, "checked_at": _now(), "updated_at": _now()}
        self.repo.put(self.DEPENDENCIES, name, row)
        return row

    def dependencies(self) -> List[dict]:
        rows = self.repo.list(self.DEPENDENCIES, limit=1000)
        rows.sort(key=lambda x: str(x.get("name", "")))
        return rows

    def put_slo(self, payload: Dict[str, Any], actor: str = "sre_admin") -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        metric = str(payload.get("metric") or "").strip()
        if not name or not metric: raise ValueError("SLO name and metric are required")
        key = str(payload.get("slo_id") or "SLO-" + uuid.uuid4().hex[:12].upper())
        old = self.repo.get(self.SLOS, key) or {}
        row = {**old, **payload, "slo_id": key, "name": name, "metric": metric, "status": payload.get("status", "active"), "updated_at": _now(), "updated_by": actor}
        row.setdefault("created_at", _now())
        return self.repo.put(self.SLOS, key, row)

    def slos(self) -> List[dict]: return self.repo.list(self.SLOS, limit=1000)

    def evaluate_slos(self) -> Dict[str, Any]:
        metrics = self.http_metrics()
        evaluated = []
        for slo in self.slos():
            if slo.get("status") != "active": continue
            metric = slo.get("metric")
            if metric == "availability": actual = metrics["availability_pct"]
            elif metric == "latency_p95_ms": actual = metrics["latency_ms"]["p95"]
            elif metric == "error_rate_pct": actual = metrics["error_rate_pct"]
            else: continue
            target = float(slo.get("target", 0) or 0)
            comp = slo.get("comparison") or ("gte" if metric == "availability" else "lte")
            met = actual >= target if comp == "gte" else actual <= target
            evaluated.append({**slo, "actual": actual, "met": met, "comparison": comp, "error_budget_remaining_pct": round(max(0.0, actual-target),3) if metric == "availability" else None})
        return {"slos": evaluated, "met": sum(1 for x in evaluated if x["met"]), "breached": sum(1 for x in evaluated if not x["met"])}

    def put_alert_rule(self, payload: Dict[str, Any], actor: str = "sre_admin") -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        metric = str(payload.get("metric") or "").strip()
        if not name or not metric: raise ValueError("alert rule name and metric are required")
        key = str(payload.get("rule_id") or "ALR-" + uuid.uuid4().hex[:12].upper())
        row = {**payload, "rule_id": key, "name": name, "metric": metric, "operator": payload.get("operator", "gt"), "status": payload.get("status", "active"), "updated_at": _now(), "updated_by": actor}
        row.setdefault("created_at", _now())
        return self.repo.put(self.ALERT_RULES, key, row)

    def alert_rules(self) -> List[dict]: return self.repo.list(self.ALERT_RULES, limit=1000)
    def alerts(self, status: str = "", limit: int = 200) -> List[dict]:
        rows = self.repo.list(self.ALERTS, limit=limit)
        return [r for r in rows if not status or r.get("status") == status]

    def evaluate_alerts(self) -> Dict[str, Any]:
        m = self.http_metrics()
        lookup = {
            "error_rate_pct": m["error_rate_pct"],
            "latency_p95_ms": m["latency_ms"]["p95"],
            "availability_pct": m["availability_pct"],
        }
        fired = []
        for rule in self.alert_rules():
            if rule.get("status") != "active" or rule.get("metric") not in lookup: continue
            actual = float(lookup[rule["metric"]]); threshold = float(rule.get("threshold", 0) or 0); op = rule.get("operator", "gt")
            hit = {"gt": actual > threshold, "gte": actual >= threshold, "lt": actual < threshold, "lte": actual <= threshold}.get(op, False)
            if hit:
                fingerprint = f"{rule['rule_id']}:{int(time.time()//300)}"
                existing = self.repo.get(self.ALERTS, fingerprint)
                if existing: fired.append(existing); continue
                row = {"alert_id": fingerprint, "rule_id": rule["rule_id"], "name": rule["name"], "severity": rule.get("severity", "warning"), "metric": rule["metric"], "actual": actual, "threshold": threshold, "status": "open", "created_at": _now(), "updated_at": _now()}
                self.repo.put(self.ALERTS, fingerprint, row); fired.append(row)
        return {"fired": fired, "open": len(self.alerts(status="open", limit=1000))}

    def resolve_alert(self, alert_id: str, actor: str = "sre_admin") -> Dict[str, Any]:
        row = self.repo.get(self.ALERTS, alert_id)
        if not row: raise KeyError(alert_id)
        row.update({"status": "resolved", "resolved_by": actor, "resolved_at": _now(), "updated_at": _now()})
        return self.repo.put(self.ALERTS, alert_id, row)

    def summary(self) -> Dict[str, Any]:
        m = self.http_metrics()
        slos = self.evaluate_slos()
        return {"http": m, "slo": {"total": len(slos["slos"]), "met": slos["met"], "breached": slos["breached"]}, "dependencies": self.dependencies(), "alerts_open": len(self.alerts(status="open", limit=1000)), "traces": len({r.get('trace_id') for r in self.repo.list(self.SPANS, limit=1000) if r.get('trace_id')})}

    def prometheus(self) -> str:
        m = self.http_metrics(); slos = self.evaluate_slos()
        lines = [
            "# HELP industrial_http_requests_total HTTP requests observed by the platform",
            "# TYPE industrial_http_requests_total counter",
            f"industrial_http_requests_total {m['requests']}",
            "# HELP industrial_http_error_rate_percent HTTP 5xx error rate percent",
            "# TYPE industrial_http_error_rate_percent gauge",
            f"industrial_http_error_rate_percent {m['error_rate_pct']}",
            "# HELP industrial_http_latency_p95_ms HTTP p95 latency in milliseconds",
            "# TYPE industrial_http_latency_p95_ms gauge",
            f"industrial_http_latency_p95_ms {m['latency_ms']['p95']}",
            "# HELP industrial_slo_breached Number of breached SLOs",
            "# TYPE industrial_slo_breached gauge",
            f"industrial_slo_breached {slos['breached']}",
        ]
        for dep in self.dependencies():
            name = ''.join(c if c.isalnum() else '_' for c in str(dep.get('name','dependency'))).lower()
            val = 1 if dep.get("status") in {"ok","healthy","online"} else 0
            lines += [f'industrial_dependency_up{{dependency="{name}"}} {val}']
        return "\n".join(lines) + "\n"


class DependencyHealthService:
    def __init__(self, telemetry: TelemetryStore): self.telemetry = telemetry

    def check(self, probes: Dict[str, Callable[[], Dict[str, Any]]]) -> Dict[str, Any]:
        rows = []
        for name, fn in probes.items():
            started = time.perf_counter()
            try:
                detail = fn() or {}
                raw = str(detail.get("status", "ok")).lower()
                status = "ok" if raw in {"ok","healthy","online","disabled"} else raw
                error = ""
            except Exception as exc:
                detail = {}; status = "error"; error = str(exc)
            row = self.telemetry.set_dependency(name, {"status": status, "latency_ms": round((time.perf_counter()-started)*1000,2), "detail": detail, "error": error})
            rows.append(row)
        return {"dependencies": rows, "healthy": sum(1 for r in rows if r.get('status') == 'ok'), "total": len(rows)}
