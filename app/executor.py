import os
from .secrets import resolve_bootstrap_secret
from typing import Any, Dict, List

class MockExecutor:
    def execute_plan(self, sql_list: List[str]) -> Dict[str, Any]:
        # Deterministic demo data representing a realistic industrial RCA response.
        return {
            "machine": {"device_id": "M-10001", "device_code": "A101", "device_name": "A101空压机"},
            "metric": {
                "current_specific_energy": 0.124,
                "baseline_specific_energy": 0.104,
                "change_pct": 19.23,
                "unit": "kWh/piece",
            },
            "energy_trend": [
                {"day": "D-6", "energy_kwh": 11980},
                {"day": "D-5", "energy_kwh": 12140},
                {"day": "D-4", "energy_kwh": 12380},
                {"day": "D-3", "energy_kwh": 13790},
                {"day": "D-2", "energy_kwh": 14120},
                {"day": "D-1", "energy_kwh": 14300},
                {"day": "D0", "energy_kwh": 14210},
            ],
            "alarms": [
                {"alarm_name": "Filter Differential Pressure High", "severity": "warning", "count": 7},
                {"alarm_name": "Discharge Temperature High", "severity": "warning", "count": 3},
            ],
            "work_orders": [
                {
                    "created_at": "2026-07-15 09:20:00",
                    "fault_description": "Air filter differential pressure rising",
                    "maintenance_action": "Inspection only; replacement deferred",
                }
            ],
            "executed_sql_count": len(sql_list),
            "execution_mode": "mock",
        }

class DorisExecutor:
    def __init__(self):
        import pymysql
        self.pymysql = pymysql
        self.cfg = {
            "host": os.getenv("DORIS_HOST", "127.0.0.1"),
            "port": int(os.getenv("DORIS_PORT", "9030")),
            "user": os.getenv("DORIS_USER", "root"),
            "password": resolve_bootstrap_secret("DORIS_PASSWORD_REF", "DORIS_PASSWORD"),
            "database": os.getenv("DORIS_DATABASE", "industrial_ai"),
            "cursorclass": pymysql.cursors.DictCursor,
        }

    def explain(self, sql: str):
        conn = self.pymysql.connect(**self.cfg)
        try:
            with conn.cursor() as cur:
                cur.execute("EXPLAIN " + sql)
                return cur.fetchall()
        finally:
            conn.close()

    def execute_plan(self, sql_list: List[str]) -> Dict[str, Any]:
        out = {"results": [], "execution_mode": "doris"}
        conn = self.pymysql.connect(**self.cfg)
        try:
            with conn.cursor() as cur:
                for sql in sql_list:
                    cur.execute(sql)
                    out["results"].append(cur.fetchall())
        finally:
            conn.close()
        return out

def get_executor():
    if os.getenv("EXECUTION_MODE", "mock").lower() == "doris":
        return DorisExecutor()
    return MockExecutor()
