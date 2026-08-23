"""V3.6 工况上下文与可比基线服务。

把负荷、产量、环境温度、班次、产品类型和运行模式组合成 Operating Context，
从历史候选样本中选择真正可比的数据，再计算工况归一化 KPI 偏差。
"""
from __future__ import annotations
from typing import Any, Dict, List
from statistics import median
import math, uuid


class OperatingContextService:
    POLICIES = "operating_context_policies"
    ASSESSMENTS = "operating_context_assessments"

    DEFAULT_POLICY = {
        "policy_id": "pilot-default",
        "load_tolerance_pct": 10.0,
        "production_tolerance_pct": 15.0,
        "ambient_tolerance_c": 5.0,
        "require_same_shift": False,
        "require_same_product_type": True,
        "require_same_operating_mode": True,
        "min_comparable_samples": 3,
        "weights": {"load_pct": 0.35, "production_output": 0.25, "ambient_temp": 0.15, "shift": 0.05, "product_type": 0.10, "operating_mode": 0.10},
    }

    def __init__(self, repo): self.repo = repo

    def upsert_policy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        pid = str(payload.get("policy_id") or "pilot-default").strip()
        row = {**self.DEFAULT_POLICY, **payload, "policy_id": pid}
        for key in ("load_tolerance_pct", "production_tolerance_pct", "ambient_tolerance_c"):
            if float(row[key]) < 0: raise ValueError(f"{key} 不能小于 0")
        if int(row["min_comparable_samples"]) < 1: raise ValueError("min_comparable_samples 必须大于 0")
        return self.repo.put(self.POLICIES, pid, row)

    def policies(self) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.POLICIES, limit=1000)
        return rows or [dict(self.DEFAULT_POLICY)]

    def get_policy(self, policy_id="pilot-default"):
        return self.repo.get(self.POLICIES, policy_id) or dict(self.DEFAULT_POLICY)

    @staticmethod
    def _num(v):
        try:
            x=float(v); return x if math.isfinite(x) else None
        except Exception: return None

    def _is_comparable(self, current, row, p):
        cl, rl = self._num(current.get("load_pct")), self._num(row.get("load_pct"))
        if cl is not None and rl is not None and abs(rl-cl) > float(p["load_tolerance_pct"]): return False
        cp, rp = self._num(current.get("production_output")), self._num(row.get("production_output"))
        if cp not in (None,0) and rp is not None and abs(rp-cp)/max(abs(cp),1e-9)*100 > float(p["production_tolerance_pct"]): return False
        ca, ra = self._num(current.get("ambient_temp")), self._num(row.get("ambient_temp"))
        if ca is not None and ra is not None and abs(ra-ca) > float(p["ambient_tolerance_c"]): return False
        for field, flag in (("shift","require_same_shift"),("product_type","require_same_product_type"),("operating_mode","require_same_operating_mode")):
            if p.get(flag) and current.get(field) not in (None,"") and row.get(field) != current.get(field): return False
        return bool(row.get("baseline_eligible", True))

    def assess(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(payload.get("current") or {})
        history = list(payload.get("history") or [])
        metric = str(payload.get("metric") or "specific_energy")
        p = self.get_policy(str(payload.get("policy_id") or "pilot-default"))
        current_value = self._num(current.get(metric))
        if current_value is None: raise ValueError(f"current.{metric} 必须是有效数值")
        comparable=[r for r in history if self._num(r.get(metric)) is not None and self._is_comparable(current,r,p)]
        values=[float(r[metric]) for r in comparable]
        baseline = float(median(values)) if values else None
        deviation = None if baseline in (None,0) else (current_value-baseline)/abs(baseline)*100.0
        min_samples=int(p["min_comparable_samples"])
        quality = "good" if len(values)>=min_samples else ("limited" if values else "insufficient")
        result={
            "assessment_id": f"OC-{uuid.uuid4().hex[:12].upper()}", "metric": metric,
            "current": current, "history_count": len(history), "comparable_count": len(values),
            "baseline_median": None if baseline is None else round(baseline,6),
            "normalized_deviation_pct": None if deviation is None else round(deviation,3),
            "comparison_quality": quality, "ready_for_rca": len(values)>=min_samples,
            "policy": p, "comparable_samples": comparable[:100],
            "interpretation": "仅在可比工况样本数量满足策略阈值时，工况归一化偏差才建议用于 RCA/能效判断。",
        }
        self.repo.put(self.ASSESSMENTS, result["assessment_id"], result)
        return result

    def assessments(self, limit=200): return self.repo.list(self.ASSESSMENTS, limit=limit)
