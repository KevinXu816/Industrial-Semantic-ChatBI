"""Read-only SQL guardrails for semantic plans.

This is intentionally conservative. Production deployments should additionally
apply Doris account privileges, row/column policies and an AST parser at the
query gateway.
"""
import re


class SQLGuardrail:
    DENY = re.compile(
        r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|replace|load|outfile|into\s+outfile)\b",
        re.I,
    )
    COMMENT = re.compile(r"(--|/\*)")

    def validate(self, sql: str) -> None:
        cleaned = sql.strip()
        lowered = cleaned.lower()
        if not cleaned:
            raise ValueError("Empty SQL is forbidden")
        if self.COMMENT.search(cleaned):
            raise ValueError("SQL comments are forbidden in generated plans")
        # Generated plans are a single SELECT statement; WITH ... SELECT is allowed.
        if not (lowered.startswith("select") or lowered.startswith("with")):
            raise ValueError("Only SELECT/CTE statements are allowed")
        if self.DENY.search(cleaned):
            raise ValueError("Mutating or export SQL is forbidden")
        if ";" in cleaned.rstrip(";"):
            raise ValueError("Multiple SQL statements are forbidden")

        time_series_tables = ["energy_5min", "production_hourly", "alarm_event"]
        if any(t in lowered for t in time_series_tables):
            has_time_filter = any(k in lowered for k in [
                "ts >=", ".ts >=", "event_time >=", ".event_time >=",
                "stat_time >=", ".stat_time >="
            ])
            if not has_time_filter:
                raise ValueError("Time-series queries must include a bounded time filter")

        if re.search(r"\bselect\s+\*", lowered) and "limit" not in lowered:
            raise ValueError("SELECT * requires LIMIT")
