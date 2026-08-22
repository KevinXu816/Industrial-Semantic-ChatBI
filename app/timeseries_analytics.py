"""Deterministic time-series analytics used by the RCA pipeline.

The module intentionally avoids LLM inference.  It extracts auditable signals
(trend, robust z-score anomalies and a simple level-shift/change-point) that can
be attached to Evidence Graph nodes.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class SeriesPoint:
    index: int
    value: float
    timestamp: Optional[str] = None


class TimeSeriesAnalyticsEngine:
    def _points(self, rows: Iterable[Dict[str, Any]], value_field: str, time_field: str | None) -> List[SeriesPoint]:
        out: List[SeriesPoint] = []
        for i, row in enumerate(rows or []):
            value = row.get(value_field)
            if value is None:
                continue
            try:
                fv = float(value)
            except (TypeError, ValueError):
                continue
            out.append(SeriesPoint(i, fv, str(row.get(time_field)) if time_field and row.get(time_field) is not None else None))
        return out

    @staticmethod
    def _slope(values: List[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        xbar = (n - 1) / 2.0
        ybar = mean(values)
        denom = sum((i - xbar) ** 2 for i in range(n))
        return 0.0 if denom == 0 else sum((i - xbar) * (v - ybar) for i, v in enumerate(values)) / denom

    @staticmethod
    def _mad(values: List[float]) -> float:
        if not values:
            return 0.0
        m = median(values)
        return median([abs(v - m) for v in values])

    def analyze(self, rows: Iterable[Dict[str, Any]], value_field: str, time_field: str | None = None,
                anomaly_threshold: float = 3.5) -> Dict[str, Any]:
        points = self._points(rows, value_field, time_field)
        values = [p.value for p in points]
        if not values:
            return {"status": "no_data", "count": 0, "anomalies": [], "signals": []}

        avg = mean(values)
        med = median(values)
        mad = self._mad(values)
        slope = self._slope(values)
        span = max(values) - min(values)
        trend_pct = 0.0 if avg == 0 else slope * max(1, len(values) - 1) / abs(avg) * 100.0

        anomalies = []
        if mad > 0:
            for p in points:
                robust_z = 0.6745 * (p.value - med) / mad
                if abs(robust_z) >= anomaly_threshold:
                    anomalies.append({
                        "index": p.index, "timestamp": p.timestamp, "value": p.value,
                        "robust_z": round(robust_z, 3), "method": "median_mad",
                    })

        change = None
        if len(values) >= 6:
            best = None
            for cut in range(3, len(values) - 2):
                left, right = values[:cut], values[cut:]
                delta = mean(right) - mean(left)
                scale = mad or (span / 6.0 if span else 1.0)
                score = abs(delta) / max(scale, 1e-9)
                if best is None or score > best["score"]:
                    best = {"cut": cut, "delta": delta, "score": score}
            if best and best["score"] >= 1.5:
                p = points[best["cut"]]
                change = {
                    "index": p.index, "timestamp": p.timestamp,
                    "delta": round(best["delta"], 6), "score": round(best["score"], 3),
                    "direction": "up" if best["delta"] > 0 else "down",
                    "method": "two_segment_level_shift",
                }

        signals = []
        if abs(trend_pct) >= 5:
            signals.append({"type": "trend", "direction": "up" if trend_pct > 0 else "down", "magnitude_pct": round(abs(trend_pct), 2)})
        if anomalies:
            signals.append({"type": "anomaly", "count": len(anomalies), "max_abs_robust_z": max(abs(x["robust_z"]) for x in anomalies)})
        if change:
            signals.append({"type": "change_point", **change})

        return {
            "status": "ok", "count": len(values), "mean": round(avg, 6), "median": round(med, 6),
            "mad": round(mad, 6), "slope_per_point": round(slope, 6), "trend_pct": round(trend_pct, 2),
            "min": min(values), "max": max(values), "anomalies": anomalies, "change_point": change,
            "signals": signals,
        }
