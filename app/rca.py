"""Evidence-first RCA scaffolding.

This module deliberately separates causal hypotheses from data retrieval so it can
later be replaced by rules, a knowledge graph, statistical detectors, or an LLM
without weakening query governance.
"""
from __future__ import annotations

from typing import Any, Dict, List


class RCAEngine:
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if data.get("execution_mode") != "mock":
            return {"hypotheses": [], "status": "evidence_collected"}

        hypotheses: List[dict] = []
        alarms = data.get("alarms") or []
        work_orders = data.get("work_orders") or []
        metric = data.get("metric") or {}
        score = 0.35
        evidence = []
        if metric.get("change_pct", 0) > 10:
            score += 0.15
            evidence.append(f"目标指标较基线上升 {metric.get('change_pct')}%")
        alarm_names = " ".join(str(x.get("alarm_name", "")) for x in alarms).lower()
        if "filter" in alarm_names or "pressure" in alarm_names:
            score += 0.2
            evidence.append("出现过滤器/压差相关告警")
        wo_text = " ".join(str(x.get("fault_description", "")) + " " + str(x.get("maintenance_action", "")) for x in work_orders).lower()
        if "filter" in wo_text or "pressure" in wo_text:
            score += 0.12
            evidence.append("历史工单存在过滤器或压差异常记录")
        if evidence:
            hypotheses.append({
                "rank": 1,
                "cause": "过滤器阻力增加导致设备负载和单位能耗上升",
                "confidence": round(min(score, 0.95), 2),
                "evidence": evidence,
                "recommended_checks": ["检查过滤器压差", "检查吸气阻力", "核对排气温度与加载率"],
            })
        return {"hypotheses": hypotheses, "status": "analyzed"}
