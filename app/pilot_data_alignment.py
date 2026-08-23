"""V3.4 真实工业数据对齐与可信化服务。

解决 Pilot 现场最常见的数据问题：设备 ID 异构、时区、采样粒度、零产量、
停机污染、传感器缺失和 CMMS Failure Code 不统一。该服务只做标准化/诊断，
不绕过既有 DataBinding 与 IntegrationRuntime 治理链路。
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List
from collections import defaultdict
import math


class PilotDataAlignmentService:
    ALIASES = "pilot_asset_aliases"
    FAILURE_CODES = "pilot_failure_codes"

    def __init__(self, repo):
        self.repo = repo

    def upsert_asset_alias(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        source_system = str(payload.get("source_system") or "").strip().lower()
        source_asset_id = str(payload.get("source_asset_id") or "").strip()
        canonical_asset_id = str(payload.get("canonical_asset_id") or "").strip()
        if not source_system or not source_asset_id or not canonical_asset_id:
            raise ValueError("source_system、source_asset_id、canonical_asset_id 不能为空")
        key = f"{source_system}:{source_asset_id}"
        row = {**payload, "source_system": source_system, "source_asset_id": source_asset_id,
               "canonical_asset_id": canonical_asset_id, "alias_key": key}
        return self.repo.put(self.ALIASES, key, row)

    def resolve_asset(self, source_system: str, source_asset_id: str) -> Dict[str, Any]:
        key = f"{str(source_system).lower()}:{source_asset_id}"
        row = self.repo.get(self.ALIASES, key)
        return row or {"alias_key": key, "canonical_asset_id": None, "resolved": False}

    def aliases(self) -> List[Dict[str, Any]]:
        return self.repo.list(self.ALIASES, limit=5000)

    def upsert_failure_code(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        source_system = str(payload.get("source_system") or "").strip().lower()
        source_code = str(payload.get("source_code") or "").strip()
        canonical_code = str(payload.get("canonical_code") or "").strip()
        if not source_system or not source_code or not canonical_code:
            raise ValueError("source_system、source_code、canonical_code 不能为空")
        key = f"{source_system}:{source_code}"
        row = {**payload, "source_system": source_system, "source_code": source_code,
               "canonical_code": canonical_code, "code_key": key}
        return self.repo.put(self.FAILURE_CODES, key, row)

    def failure_codes(self) -> List[Dict[str, Any]]:
        return self.repo.list(self.FAILURE_CODES, limit=5000)

    @staticmethod
    def _parse_time(value: Any, source_timezone: str = "UTC") -> datetime:
        if isinstance(value, (int, float)):
            # 自动识别秒/毫秒时间戳
            v = float(value)
            if abs(v) > 10_000_000_000:
                v /= 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc)
        text = str(value or "").strip()
        if not text:
            raise ValueError("timestamp 为空")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            if source_timezone.upper() != "UTC":
                # 无第三方时区依赖时拒绝猜测非 UTC 本地时间，避免静默错位。
                raise ValueError("无时区时间戳必须先带 UTC offset，例如 +08:00")
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def normalize_records(self, records: List[Dict[str, Any]], *, source_system: str = "",
                          asset_field: str = "asset_id", timestamp_field: str = "timestamp",
                          source_timezone: str = "UTC") -> Dict[str, Any]:
        out, errors, unresolved = [], [], []
        for idx, src in enumerate(records):
            row = dict(src)
            try:
                if timestamp_field in row and row.get(timestamp_field) not in (None, ""):
                    row[timestamp_field] = self._parse_time(row[timestamp_field], source_timezone).isoformat().replace("+00:00", "Z")
                if source_system and row.get(asset_field) not in (None, ""):
                    resolved = self.resolve_asset(source_system, str(row[asset_field]))
                    if resolved.get("canonical_asset_id"):
                        row[asset_field] = resolved["canonical_asset_id"]
                    else:
                        unresolved.append(str(row[asset_field]))
                out.append(row)
            except Exception as exc:
                errors.append({"index": idx, "error": str(exc), "record": src})
        return {"records": out, "errors": errors, "unresolved_asset_ids": sorted(set(unresolved)),
                "normalized": len(out), "failed": len(errors)}

    @staticmethod
    def assess_series(records: List[Dict[str, Any]], *, bucket_minutes: int = 5,
                      production_sensor: str = "production_output", power_sensor: str = "active_power",
                      required_sensors: List[str] | None = None, min_load_pct: float = 20.0) -> Dict[str, Any]:
        required_sensors = required_sensors or ["active_power", "production_output", "filter_dp", "discharge_temp", "load_pct"]
        buckets: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        invalid, stopped = 0, 0
        for r in records:
            try:
                ts = PilotDataAlignmentService._parse_time(r.get("timestamp"))
                minute = (ts.minute // bucket_minutes) * bucket_minutes
                b = ts.replace(minute=minute, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
                sensor = str(r.get("sensor") or "")
                value = float(r.get("value"))
                if not sensor or not math.isfinite(value): raise ValueError()
                buckets[b][sensor].append(value)
            except Exception:
                invalid += 1
        aligned=[]
        for ts, sensors in sorted(buckets.items()):
            vals={k: sum(v)/len(v) for k,v in sensors.items() if v}
            load=vals.get("load_pct")
            production=vals.get(production_sensor)
            operating = (load is None or load >= min_load_pct) and (production is None or production > 0)
            if not operating: stopped += 1
            energy=None
            if operating and production and production > 0 and power_sensor in vals:
                energy=vals[power_sensor] / production
            aligned.append({"timestamp":ts,"values":vals,"operating":operating,"specific_energy":energy})
        present={s for b in buckets.values() for s in b}
        missing=[s for s in required_sensors if s not in present]
        operating_rows=[x for x in aligned if x["operating"]]
        return {
            "bucket_minutes": bucket_minutes, "input_records": len(records), "aligned_buckets": len(aligned),
            "invalid_records": invalid, "stopped_buckets_excluded_from_baseline": stopped,
            "required_sensors": required_sensors, "missing_sensors": missing,
            "sensor_completeness": round((len(required_sensors)-len(missing))/max(len(required_sensors),1),4),
            "specific_energy_rule": "仅在 production_output>0 且 load_pct 达到运行阈值时计算 active_power/production_output",
            "baseline_candidate_buckets": len(operating_rows), "items": aligned[:500],
            "ready_for_baseline": not missing and len(operating_rows) > 0 and invalid == 0,
        }
