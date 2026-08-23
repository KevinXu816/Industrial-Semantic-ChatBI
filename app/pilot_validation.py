"""V3.3 客户真实数据验证与接入诊断。

该模块不直接连接客户系统；它验证客户提供的样例记录、字段映射和数据质量，
通过后再交给既有 DataBinding / IntegrationRuntime 执行，避免建立第二套接入链路。
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PilotCustomerDataValidator:
    COLLECTION = "pilot_customer_validation"

    def __init__(self, repo, bindings, runtime):
        self.repo = repo
        self.bindings = bindings
        self.runtime = runtime

    def validate(self, binding_id: str, records: List[Dict[str, Any]], actor: str = "pilot_data_engineer") -> Dict[str, Any]:
        binding = self.bindings.get(binding_id)
        if not binding:
            raise KeyError(binding_id)
        if not records:
            raise ValueError("records 不能为空")

        preview = self.bindings.preview(binding_id, records, limit=min(len(records), 100))
        schema = self.runtime.inspect_schema(binding_id, records, accept=False, actor=actor)
        mappings = binding.get("mappings") or {}
        source_fields = sorted({str(k) for row in records[:100] for k in row.keys()})
        mapped_source_fields = sorted({str(v) for v in mappings.values() if isinstance(v, str) and not v.startswith("$literal:")})
        missing_source_fields = [f for f in mapped_source_fields if f not in source_fields]
        null_rates = {}
        for field in mapped_source_fields:
            nulls = sum(1 for row in records if row.get(field) in (None, ""))
            null_rates[field] = round(nulls / len(records), 4)

        valid = len(preview.get("records") or [])
        invalid = len(preview.get("errors") or [])
        transform_success_rate = round(valid / max(valid + invalid, 1), 4)
        timestamp_candidates = [f for f in source_fields if any(x in f.lower() for x in ("time", "date", "timestamp"))]
        warnings = []
        if missing_source_fields:
            warnings.append("映射引用了样例数据中不存在的源字段")
        if transform_success_rate < 0.95:
            warnings.append("字段转换成功率低于 95%")
        high_null = [k for k, v in null_rates.items() if v > 0.05]
        if high_null:
            warnings.append("关键映射字段空值率超过 5%: " + ", ".join(high_null))
        if binding.get("target") == "condition_series" and not timestamp_candidates:
            warnings.append("时序数据未发现明显的时间字段")

        score = 100
        score -= min(40, len(missing_source_fields) * 15)
        score -= int((1 - transform_success_rate) * 40)
        score -= min(20, len(high_null) * 5)
        score = max(0, score)
        ready = score >= 80 and not missing_source_fields and transform_success_rate >= 0.95
        row = {
            "binding_id": binding_id, "binding_name": binding.get("name"), "target": binding.get("target"),
            "sample_count": len(records), "source_fields": source_fields, "mapped_source_fields": mapped_source_fields,
            "missing_source_fields": missing_source_fields, "null_rates": null_rates,
            "transform_success_rate": transform_success_rate, "schema": schema.get("schema"), "schema_drift": schema.get("drift"),
            "timestamp_candidates": timestamp_candidates, "warnings": warnings, "readiness_score": score,
            "ready_for_approval": ready, "validated_at": _now(), "validated_by": actor,
        }
        self.repo.put(self.COLLECTION, binding_id, row)
        return row

    def latest(self, binding_id: str = "") -> Dict[str, Any]:
        if binding_id:
            row = self.repo.get(self.COLLECTION, binding_id)
            return row or {"binding_id": binding_id, "status": "not_validated"}
        rows = self.repo.list(self.COLLECTION, limit=1000)
        ready = sum(1 for x in rows if x.get("ready_for_approval"))
        return {"validated": len(rows), "ready": ready, "items": rows}

    def dry_run(self, binding_id: str, records: List[Dict[str, Any]], actor: str = "pilot_data_engineer") -> Dict[str, Any]:
        validation = self.validate(binding_id, records, actor=actor)
        preview = self.bindings.preview(binding_id, records, limit=min(len(records), 100))
        return {
            "binding_id": binding_id,
            "write_performed": False,
            "validation": validation,
            "preview": preview,
            "next_step": "验证通过后由数据治理人员批准 Binding，再使用 Integration Runtime 执行真实写入。",
        }
