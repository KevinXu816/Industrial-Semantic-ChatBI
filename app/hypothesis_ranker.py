"""Evidence-weighted hypothesis ranking for industrial RCA."""
from __future__ import annotations

from typing import Any, Dict, List


CAUSES = {
    "filter_restriction": {
        "cause": "过滤器阻力增加/堵塞导致设备负载与单位能耗上升",
        "checks": ["检查过滤器压差", "检查吸气阻力", "核对排气温度与加载率"],
    },
    "thermal_overload": {
        "cause": "散热或冷却异常导致温度升高并降低设备效率",
        "checks": ["检查冷却器和风道", "核对环境温度", "检查排气温度趋势"],
    },
    "lubrication": {
        "cause": "润滑/轴承状态异常导致机械损耗增加",
        "checks": ["检查润滑油状态", "检查轴承温度和振动", "核对最近保养记录"],
    },
    "electrical": {
        "cause": "电气侧电压/电流/过载异常造成效率下降",
        "checks": ["检查三相电压电流", "核对过载记录", "检查功率因数和谐波"],
    },
}


class HypothesisRanker:
    def rank(self, correlation: Dict[str, Any], knowledge: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
        knowledge = knowledge or []
        out = []
        for c in correlation.get("candidates", []):
            code = c.get("cause_code")
            cfg = CAUSES.get(code, {"cause": code or "unknown", "checks": []})
            score = float(c.get("score", 0))
            evidence = list(c.get("evidence", []))
            for doc in knowledge:
                tags = " ".join(map(str, doc.get("tags", []))).lower()
                failure_mode = str(doc.get("failure_mode", "")).lower()
                if code and (code.replace("_", " ") in tags or code in tags or code in failure_mode):
                    score += min(0.12, float(doc.get("retrieval_score", 0)) * 0.2 + 0.03)
                    evidence.append({"type": "knowledge", "statement": doc.get("title", doc.get("content", "知识文档命中")),
                                     "provenance": doc.get("provenance")})
            out.append({"cause_code": code, "cause": cfg["cause"], "confidence": round(min(score, 0.98), 2),
                        "evidence": evidence, "recommended_checks": cfg["checks"]})
        out.sort(key=lambda x: x["confidence"], reverse=True)
        for i, item in enumerate(out, 1):
            item["rank"] = i
        return out
