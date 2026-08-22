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
            metric = data["metric"]
            alarms = data.get("alarms", [])
            wo = data.get("work_orders", [])
            reasons = []
            if alarms:
                reasons.append(f"近期开启最多的异常为“{alarms[0]['alarm_name']}”，共 {alarms[0]['count']} 次")
            if len(alarms) > 1:
                reasons.append(f"同时出现“{alarms[1]['alarm_name']}” {alarms[1]['count']} 次")
            if wo:
                reasons.append("历史工单记录显示过滤器压差已上升，但当时仅检查、未更换")
            reason_text = "；".join(reasons)
            return (
                f"{(intent.subject.reference if intent.subject else intent.machine_ref)} 最近一周单位产量能耗约为 {metric['current_specific_energy']} {metric['unit']}，"
                f"相对基线 {metric['baseline_specific_energy']} {metric['unit']} 上升 {metric['change_pct']}%。"
                f"结合告警和维修事件，最值得优先验证的原因是过滤器阻力增加导致压缩机负载上升。{reason_text}。"
                "建议现场先检查过滤器压差、吸气阻力和排气温度，再与正常工况下的加载率/卸载率对比。"
            )
        return "Doris 查询已经执行。生产版本应将结果标准化后交给 LLM/RCA 组件完成解释，并附带查询证据。"
