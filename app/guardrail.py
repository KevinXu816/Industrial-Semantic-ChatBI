import re

class SQLGuardrail:
    DENY = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke)\b", re.I)

    def validate(self, sql: str) -> None:
        cleaned = sql.strip()
        if not cleaned.lower().startswith("select"):
            raise ValueError("Only SELECT statements are allowed")
        if self.DENY.search(cleaned):
            raise ValueError("Mutating SQL is forbidden")

        lowered = cleaned.lower()
        time_series_tables = ["energy_5min", "production_hourly", "alarm_event"]
        if any(t in lowered for t in time_series_tables):
            has_time_filter = any(k in lowered for k in ["ts >=", "event_time >=", "stat_time >="])
            if not has_time_filter:
                raise ValueError("Time-series queries must include a bounded time filter")

        if "select *" in lowered and "limit" not in lowered:
            raise ValueError("SELECT * requires LIMIT")
