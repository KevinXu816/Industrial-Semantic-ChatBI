"""Correlation of metric anomalies with industrial alarms and maintenance events."""
from __future__ import annotations

from typing import Any, Dict, List


class EventCorrelationEngine:
    KEYWORDS = {
        "filter_restriction": ("filter", "differential pressure", "pressure", "滤芯", "压差"),
        "thermal_overload": ("temperature", "overheat", "thermal", "高温", "温度"),
        "lubrication": ("lubric", "oil", "bearing", "润滑", "轴承"),
        "electrical": ("current", "voltage", "phase", "overload", "电流", "电压", "过载"),
    }

    def correlate(self, analytics: Dict[str, Any], alarms: List[Dict[str, Any]] | None,
                  work_orders: List[Dict[str, Any]] | None) -> Dict[str, Any]:
        alarms = alarms or []
        work_orders = work_orders or []
        anomaly_strength = 0.0
        if analytics.get("change_point"):
            anomaly_strength += min(0.35, float(analytics["change_point"].get("score", 0)) / 10.0)
        anomaly_strength += min(0.25, len(analytics.get("anomalies", [])) * 0.05)
        anomaly_strength += min(0.20, abs(float(analytics.get("trend_pct", 0))) / 100.0)

        alarm_text = " ".join(
            str(a.get("alarm_name", "")) + " " + str(a.get("alarm_code", "")) + " " + str(a.get("severity", ""))
            for a in alarms
        ).lower()
        wo_text = " ".join(
            str(w.get("fault_description", "")) + " " + str(w.get("maintenance_action", w.get("action", "")))
            for w in work_orders
        ).lower()

        candidates = []
        for cause, terms in self.KEYWORDS.items():
            a_hits = sorted({t for t in terms if t in alarm_text})
            w_hits = sorted({t for t in terms if t in wo_text})
            if not a_hits and not w_hits:
                continue
            score = 0.25 + anomaly_strength + min(0.25, len(a_hits) * 0.08) + min(0.20, len(w_hits) * 0.10)
            evidence = []
            if analytics.get("trend_pct"):
                evidence.append({"type": "timeseries", "statement": f"指标趋势变化 {analytics['trend_pct']}%", "provenance": "analytics:trend"})
            if analytics.get("change_point"):
                evidence.append({"type": "timeseries", "statement": "检测到水平突变", "provenance": "analytics:change_point"})
            if a_hits:
                evidence.append({"type": "alarm", "statement": f"告警匹配关键词: {', '.join(a_hits)}", "provenance": "AlarmEvent"})
            if w_hits:
                evidence.append({"type": "work_order", "statement": f"工单匹配关键词: {', '.join(w_hits)}", "provenance": "WorkOrder"})
            candidates.append({"cause_code": cause, "score": round(min(score, 0.98), 3), "evidence": evidence})
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return {"status": "correlated", "candidates": candidates}
