"""Temporal evidence ordering and lag analysis for industrial RCA V0.9."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


def _parse_ts(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000.0 if v > 1e12 else v
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


class TemporalCausalityEngine:
    """Build an auditable temporal evidence chain around an anomaly anchor."""

    def build_chain(self, anchor_time: Any, events: Iterable[Dict[str, Any]],
                    before_minutes: int = 120, after_minutes: int = 30) -> Dict[str, Any]:
        anchor = _parse_ts(anchor_time)
        if anchor is None:
            return {"status": "missing_anchor", "events": [], "chain": []}
        low, high = anchor - before_minutes * 60, anchor + after_minutes * 60
        selected: List[Dict[str, Any]] = []
        for ev in events or []:
            ts = _parse_ts(ev.get("timestamp") or ev.get("ts") or ev.get("event_time") or ev.get("time"))
            if ts is None or ts < low or ts > high:
                continue
            lag_min = (ts - anchor) / 60.0
            relation = "PRECEDES" if lag_min < -0.01 else "FOLLOWS" if lag_min > 0.01 else "COINCIDES"
            selected.append({**ev, "epoch": ts, "lag_minutes": round(lag_min, 2), "temporal_relation": relation})
        selected.sort(key=lambda x: x["epoch"])
        chain = [{
            "order": i + 1,
            "event_type": e.get("type", e.get("event_type", "event")),
            "label": e.get("label") or e.get("alarm_name") or e.get("signal") or e.get("fault_description") or "event",
            "lag_minutes": e["lag_minutes"],
            "temporal_relation": e["temporal_relation"],
            "provenance": e.get("provenance", e.get("source", "event")),
        } for i, e in enumerate(selected)]
        return {"status": "ok", "anchor_epoch": anchor, "window": {"before_minutes": before_minutes, "after_minutes": after_minutes},
                "events": selected, "chain": chain}
