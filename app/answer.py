import json
from typing import Any, Dict
from .models import SemanticIntent


class AnswerComposer:
    def compose(self, intent: SemanticIntent, data: Dict[str, Any]) -> str:
        from .llm_service import LLMService
        llm = LLMService()
        if llm.is_available():
            return self._compose_llm(intent, data, llm)
        return self._compose_template(intent, data)

    def _compose_llm(self, intent: SemanticIntent, data: Dict[str, Any], llm) -> str:
        system = (
            "你是一个工业设备数据分析专家。根据用户问题和查询结果，用中文给出简洁专业的分析回答。"
            "重点关注异常原因、趋势变化和可操作建议。不要编造数据，只基于提供的查询结果回答。"
        )
        user_msg = (
            f"用户问题：{intent.raw_question}\n"
            f"语义解析：主体={intent.subject.entity if intent.subject else None}:{intent.subject.reference if intent.subject else None}, "
            f"指标={intent.metric}, 时间窗口={intent.time_window_days}天, 模式={intent.analysis_mode}\n"
            f"查询结果：{json.dumps(data, ensure_ascii=False, default=str)[:3000]}"
        )
        try:
            return llm.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ])
        except Exception:
            return self._compose_template(intent, data)

    def _compose_template(self, intent: SemanticIntent, data: Dict[str, Any]) -> str:
        if data.get("execution_mode") == "mock":
            metric = data.get("metric", {})
            subject_ref = intent.subject.reference if intent.subject else intent.machine_ref
            base = (
                f"{subject_ref or '目标对象'} 最近分析窗口的单位产量能耗约为 "
                f"{metric.get('current_specific_energy', 'N/A')} {metric.get('unit', '')}，"
                f"相对基线 {metric.get('baseline_specific_energy', 'N/A')} {metric.get('unit', '')} "
                f"变化 {metric.get('change_pct', 'N/A')}%。"
            )
            rca = data.get("rca") or {}
            hypotheses = rca.get("hypotheses") or []
            if hypotheses:
                top = hypotheses[0]
                evidence = top.get("evidence") or []
                evidence_text = []
                for ev in evidence[:4]:
                    evidence_text.append(str(ev.get("statement")) if isinstance(ev, dict) else str(ev))
                checks = "、".join(str(x) for x in (top.get("recommended_checks") or [])[:3])
                return (
                    base + f" RCA 当前排名第一的假设是“{top.get('cause', '未知原因')}”，"
                    f"置信度约 {round(float(top.get('confidence', 0)) * 100)}%。"
                    + ("主要证据包括：" + "；".join(evidence_text) + "。" if evidence_text else "")
                    + (f"建议优先：{checks}。" if checks else "")
                )
            return base + "当前证据不足以形成高置信度根因假设，建议继续采集告警、工单和相关时序信号。"
        return "Doris 查询已经执行。生产版本应将结构化结果交给受治理的 RCA/LLM 解释层，并保留查询血缘与证据来源。"
