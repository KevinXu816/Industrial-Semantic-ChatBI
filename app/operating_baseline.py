"""Operating-condition baseline comparison for V0.9."""
from __future__ import annotations
from statistics import mean, median
from typing import Any, Dict, Iterable, List


class OperatingBaselineEngine:
    def compare(self, current_rows: Iterable[Dict[str, Any]], baseline_rows: Iterable[Dict[str, Any]], value_field: str = "value") -> Dict[str, Any]:
        def vals(rows):
            out: List[float] = []
            for r in rows or []:
                try:
                    if r.get(value_field) is not None: out.append(float(r[value_field]))
                except (TypeError, ValueError): pass
            return out
        cur, base = vals(current_rows), vals(baseline_rows)
        if not cur or not base:
            return {"status": "insufficient_data"}
        c, b = mean(cur), mean(base)
        pct = 0.0 if b == 0 else (c-b)/abs(b)*100.0
        return {"status": "ok", "current_mean": round(c,6), "baseline_mean": round(b,6),
                "current_median": round(median(cur),6), "baseline_median": round(median(base),6),
                "deviation_pct": round(pct,2), "direction": "up" if pct > 0 else "down" if pct < 0 else "flat",
                "sample_count": {"current": len(cur), "baseline": len(base)}}
