"""V3.5 工业时序数据质量与对账服务。

面向真实 Pilot 数据，识别 Gap、异常值、Counter Reset、Sensor Frozen、Clock Drift、
Late-arriving Data、MES 班次边界和维护窗口。输出质量诊断以及可安全进入 Baseline / Reliability / RCA 的记录。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Tuple
import math
import uuid

from .pilot_data_alignment import PilotDataAlignmentService


class PilotTimeSeriesQualityService:
    POLICIES = "pilot_timeseries_quality_policies"
    MAINTENANCE = "pilot_maintenance_windows"
    ASSESSMENTS = "pilot_timeseries_quality_assessments"

    DEFAULT_POLICY = {
        "expected_interval_seconds": 300,
        "gap_factor": 2.5,
        "outlier_mad_z": 6.0,
        "frozen_min_points": 4,
        "clock_drift_seconds": 120,
        "late_arrival_seconds": 900,
        "counter_reset_drop": 0.0,
        "shift_hours": [0, 8, 16],
    }

    def __init__(self, repo):
        self.repo = repo

    def upsert_policy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        policy_id = str(payload.get("policy_id") or "pilot-default").strip()
        if not policy_id:
            raise ValueError("policy_id 不能为空")
        row = {**self.DEFAULT_POLICY, **payload, "policy_id": policy_id}
        for key in ("expected_interval_seconds", "frozen_min_points", "clock_drift_seconds", "late_arrival_seconds"):
            if float(row[key]) < 0:
                raise ValueError(f"{key} 不能小于 0")
        return self.repo.put(self.POLICIES, policy_id, row)

    def policies(self) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.POLICIES, limit=1000)
        return rows or [{**self.DEFAULT_POLICY, "policy_id": "pilot-default"}]

    def get_policy(self, policy_id: str = "pilot-default") -> Dict[str, Any]:
        return self.repo.get(self.POLICIES, policy_id) or {**self.DEFAULT_POLICY, "policy_id": policy_id}

    def add_maintenance_window(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = str(payload.get("asset_id") or "").strip()
        start = self._time(payload.get("start"))
        end = self._time(payload.get("end"))
        if not asset_id:
            raise ValueError("asset_id 不能为空")
        if end <= start:
            raise ValueError("维护窗口 end 必须晚于 start")
        window_id = str(payload.get("window_id") or f"MW-{uuid.uuid4().hex[:12].upper()}")
        row = {
            **payload,
            "window_id": window_id,
            "asset_id": asset_id,
            "start": self._iso(start),
            "end": self._iso(end),
            "reason": str(payload.get("reason") or "maintenance"),
        }
        return self.repo.put(self.MAINTENANCE, window_id, row)

    def maintenance_windows(self, asset_id: str = "") -> List[Dict[str, Any]]:
        rows = self.repo.list(self.MAINTENANCE, limit=5000)
        if asset_id:
            rows = [r for r in rows if str(r.get("asset_id")) == asset_id]
        return rows

    @staticmethod
    def _time(value: Any) -> datetime:
        return PilotDataAlignmentService._parse_time(value)

    @staticmethod
    def _iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _mad(values: List[float]) -> Tuple[float, float]:
        if not values:
            return 0.0, 0.0
        m = median(values)
        mad = median([abs(v - m) for v in values])
        return float(m), float(mad)

    @staticmethod
    def _shift_label(dt: datetime, shift_hours: List[int]) -> str:
        hours = sorted({int(h) % 24 for h in (shift_hours or [0, 8, 16])})
        selected = hours[-1]
        for h in hours:
            if dt.hour >= h:
                selected = h
            else:
                break
        idx = hours.index(selected) + 1
        return f"shift-{idx}@{selected:02d}:00Z"

    def _maintenance_index(self, asset_id: str) -> List[Tuple[datetime, datetime, Dict[str, Any]]]:
        out = []
        for row in self.maintenance_windows(asset_id):
            try:
                out.append((self._time(row["start"]), self._time(row["end"]), row))
            except Exception:
                continue
        return out

    @staticmethod
    def _inside(dt: datetime, windows: List[Tuple[datetime, datetime, Dict[str, Any]]]) -> Dict[str, Any] | None:
        for start, end, row in windows:
            if start <= dt <= end:
                return row
        return None

    def assess(self, records: List[Dict[str, Any]], *, policy_id: str = "pilot-default", asset_id: str = "") -> Dict[str, Any]:
        policy = self.get_policy(policy_id)
        expected = float(policy.get("expected_interval_seconds", 300))
        gap_factor = float(policy.get("gap_factor", 2.5))
        outlier_z = float(policy.get("outlier_mad_z", 6.0))
        frozen_min = int(policy.get("frozen_min_points", 4))
        drift_limit = float(policy.get("clock_drift_seconds", 120))
        late_limit = float(policy.get("late_arrival_seconds", 900))
        reset_drop = float(policy.get("counter_reset_drop", 0.0))
        shift_hours = list(policy.get("shift_hours") or [0, 8, 16])

        parsed = []
        invalid = []
        for idx, raw in enumerate(records):
            try:
                ts = self._time(raw.get("timestamp"))
                value = float(raw.get("value"))
                sensor = str(raw.get("sensor") or "").strip()
                if not sensor or not math.isfinite(value):
                    raise ValueError("sensor/value 无效")
                received = None
                if raw.get("received_at") not in (None, ""):
                    received = self._time(raw.get("received_at"))
                source_clock = None
                if raw.get("source_clock_at") not in (None, ""):
                    source_clock = self._time(raw.get("source_clock_at"))
                parsed.append({"index": idx, "raw": raw, "sensor": sensor, "value": value, "ts": ts, "received": received, "source_clock": source_clock})
            except Exception as exc:
                invalid.append({"index": idx, "error": str(exc), "record": raw})

        by_sensor: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in parsed:
            by_sensor[r["sensor"]].append(r)
        for rows in by_sensor.values():
            rows.sort(key=lambda x: x["ts"])

        gaps, outliers, resets, frozen, clock_drift, late = [], [], [], [], [], []
        flags_by_index: Dict[int, List[str]] = defaultdict(list)

        for sensor, rows in by_sensor.items():
            values = [r["value"] for r in rows]
            med, mad = self._mad(values)
            # Gap / counter reset / clock drift / late arrival
            same_run_start = 0
            for i, r in enumerate(rows):
                if i > 0:
                    delta = (r["ts"] - rows[i-1]["ts"]).total_seconds()
                    if expected > 0 and delta > expected * gap_factor:
                        item = {"sensor": sensor, "from": self._iso(rows[i-1]["ts"]), "to": self._iso(r["ts"]), "gap_seconds": delta}
                        gaps.append(item); flags_by_index[r["index"]].append("gap_after")
                    if r["value"] < rows[i-1]["value"] - reset_drop and self._looks_like_counter(sensor, r["raw"]):
                        item = {"sensor": sensor, "timestamp": self._iso(r["ts"]), "previous": rows[i-1]["value"], "current": r["value"]}
                        resets.append(item); flags_by_index[r["index"]].append("counter_reset")
                    if r["value"] == rows[i-1]["value"]:
                        pass
                    else:
                        run_len = i - same_run_start
                        if run_len >= frozen_min:
                            seq = rows[same_run_start:i]
                            frozen.append({"sensor": sensor, "from": self._iso(seq[0]["ts"]), "to": self._iso(seq[-1]["ts"]), "points": len(seq), "value": seq[0]["value"]})
                            for q in seq: flags_by_index[q["index"]].append("frozen")
                        same_run_start = i
                # robust outlier
                if mad > 0:
                    rz = 0.6745 * abs(r["value"] - med) / mad
                    if rz > outlier_z:
                        outliers.append({"sensor": sensor, "timestamp": self._iso(r["ts"]), "value": r["value"], "robust_z": round(rz, 3)})
                        flags_by_index[r["index"]].append("outlier")
                if r["source_clock"] is not None and r["received"] is not None:
                    drift = (r["source_clock"] - r["received"]).total_seconds()
                    if abs(drift) > drift_limit:
                        clock_drift.append({"sensor": sensor, "timestamp": self._iso(r["ts"]), "source_clock_at": self._iso(r["source_clock"]), "received_at": self._iso(r["received"]), "drift_seconds": drift})
                        flags_by_index[r["index"]].append("clock_drift")
                if r["received"] is not None:
                    lag = (r["received"] - r["ts"]).total_seconds()
                    if lag > late_limit:
                        late.append({"sensor": sensor, "timestamp": self._iso(r["ts"]), "received_at": self._iso(r["received"]), "late_seconds": lag})
                        flags_by_index[r["index"]].append("late_arrival")
            # close final frozen run
            if rows:
                run_len = len(rows) - same_run_start
                if run_len >= frozen_min:
                    seq = rows[same_run_start:]
                    signature = (sensor, self._iso(seq[0]["ts"]), self._iso(seq[-1]["ts"]))
                    if not any((x["sensor"], x["from"], x["to"]) == signature for x in frozen):
                        frozen.append({"sensor": sensor, "from": signature[1], "to": signature[2], "points": len(seq), "value": seq[0]["value"]})
                        for q in seq: flags_by_index[q["index"]].append("frozen")

        windows = self._maintenance_index(asset_id) if asset_id else []
        maintenance_hits = 0
        reconciled = []
        for r in parsed:
            mw = self._inside(r["ts"], windows)
            flags = list(dict.fromkeys(flags_by_index.get(r["index"], [])))
            if mw:
                flags.append("maintenance_window")
                maintenance_hits += 1
            severe = any(f in flags for f in ("frozen", "clock_drift"))
            baseline_eligible = not severe and not mw
            reconciled.append({
                **r["raw"],
                "timestamp": self._iso(r["ts"]),
                "quality_flags": flags,
                "shift": self._shift_label(r["ts"], shift_hours),
                "baseline_eligible": baseline_eligible,
            })

        valid_count = len(parsed)
        penalties = (
            len(invalid) * 8 + len(gaps) * 4 + len(outliers) * 2 + len(resets) * 3 +
            len(frozen) * 8 + len(clock_drift) * 5 + len(late) * 3
        )
        denom = max(valid_count, 1)
        score = max(0.0, min(100.0, 100.0 - penalties * 100.0 / denom / 10.0))
        critical = len(invalid) + len(frozen) + len(clock_drift)
        assessment_id = f"TSQ-{uuid.uuid4().hex[:12].upper()}"
        result = {
            "assessment_id": assessment_id,
            "policy_id": policy_id,
            "asset_id": asset_id,
            "input_records": len(records),
            "valid_records": valid_count,
            "invalid_records": invalid,
            "gaps": gaps,
            "outliers": outliers,
            "counter_resets": resets,
            "frozen_segments": frozen,
            "clock_drift": clock_drift,
            "late_arrivals": late,
            "maintenance_records_excluded": maintenance_hits,
            "quality_score": round(score, 2),
            "critical_issue_count": critical,
            "ready_for_baseline": critical == 0 and valid_count > 0,
            "reconciled_records": reconciled[:5000],
            "policy": policy,
            "assessed_at": self._iso(datetime.now(timezone.utc)),
        }
        self.repo.put(self.ASSESSMENTS, assessment_id, result)
        return result

    @staticmethod
    def _looks_like_counter(sensor: str, raw: Dict[str, Any]) -> bool:
        if bool(raw.get("counter")):
            return True
        s = sensor.lower()
        return any(k in s for k in ("counter", "total", "cumulative", "energy_import", "runtime_hours"))

    def assessments(self, asset_id: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.ASSESSMENTS, limit=max(1, min(limit, 5000)))
        if asset_id:
            rows = [r for r in rows if str(r.get("asset_id")) == asset_id]
        return rows
