"""Apache Doris EXPLAIN adapter and cost normalizer.

The adapter can parse live EXPLAIN output when available; mock/POC mode can use
`estimate_from_plan` without contacting Doris.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable


class DorisExplainCostAdapter:
    ROW_PATTERNS = [r"cardinality\s*[:=]\s*([0-9]+)", r"rows\s*[:=]\s*([0-9]+)"]

    def parse(self, explain_rows: Iterable[Any]) -> Dict[str, Any]:
        text = "\n".join(" ".join(map(str, r)) if isinstance(r, (list, tuple)) else str(r) for r in explain_rows or [])
        cardinalities = []
        for pattern in self.ROW_PATTERNS:
            cardinalities.extend(int(x) for x in re.findall(pattern, text, flags=re.I))
        scans = len(re.findall(r"SCAN|OlapScanNode|VOlapScanNode", text, flags=re.I))
        joins = len(re.findall(r"JOIN", text, flags=re.I))
        max_rows = max(cardinalities) if cardinalities else None
        score = scans * 15 + joins * 25
        if max_rows:
            score += min(500, max_rows / 100000)
        return {"source": "doris_explain", "scan_nodes": scans, "join_nodes": joins,
                "max_cardinality": max_rows, "normalized_cost": round(score, 2), "raw_available": bool(text)}

    def estimate_from_plan(self, plan) -> Dict[str, Any]:
        physical = plan.physical_plan or {}
        tables = physical.get("tables", [])
        joins = sum(max(0, len(p) - 1) for p in (plan.join_paths or {}).values())
        days = plan.intent.time_range.normalized_days() if plan.intent.time_range else 7
        catalogs = len(physical.get("catalogs", []))
        score = len(tables) * 12 + joins * 18 + days * 0.8 + max(0, catalogs - 1) * 30
        if plan.intent.comparison.type != "none":
            score *= 1.4
        return {"source": "logical_estimate", "scan_nodes": len(tables), "join_nodes": joins,
                "time_window_days": days, "normalized_cost": round(score, 2)}
