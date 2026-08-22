"""Lagged sensor correlation utilities for V0.9 RCA."""
from __future__ import annotations

from math import sqrt
from statistics import mean
from typing import Any, Dict, Iterable, List


def _values(rows: Iterable[Dict[str, Any]], field: str) -> List[float]:
    out = []
    for row in rows or []:
        try:
            if row.get(field) is not None:
                out.append(float(row[field]))
        except (TypeError, ValueError):
            pass
    return out


def _pearson(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or len(a) < 3:
        return 0.0
    ma, mb = mean(a), mean(b)
    num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    da = sqrt(sum((x-ma)**2 for x in a)); db = sqrt(sum((y-mb)**2 for y in b))
    return 0.0 if da == 0 or db == 0 else num/(da*db)


class SensorCorrelationEngine:
    def lag_correlation(self, driver_rows: Iterable[Dict[str, Any]], target_rows: Iterable[Dict[str, Any]],
                        driver_field: str = "value", target_field: str = "value", max_lag_points: int = 6) -> Dict[str, Any]:
        x, y = _values(driver_rows, driver_field), _values(target_rows, target_field)
        n = min(len(x), len(y)); x, y = x[:n], y[:n]
        if n < 4:
            return {"status": "insufficient_data", "best_lag_points": 0, "correlation": 0.0, "candidates": []}
        candidates = []
        for lag in range(-max_lag_points, max_lag_points + 1):
            if lag > 0:
                xa, ya = x[:-lag], y[lag:]
            elif lag < 0:
                xa, ya = x[-lag:], y[:lag]
            else:
                xa, ya = x, y
            if len(xa) < 3:
                continue
            r = _pearson(xa, ya)
            candidates.append({"lag_points": lag, "correlation": round(r, 4), "abs_correlation": round(abs(r), 4)})
        best = max(candidates, key=lambda z: z["abs_correlation"], default={"lag_points": 0, "correlation": 0.0})
        return {"status": "ok", "best_lag_points": best["lag_points"], "correlation": best["correlation"],
                "direction": "positive" if best["correlation"] >= 0 else "negative", "candidates": candidates}
