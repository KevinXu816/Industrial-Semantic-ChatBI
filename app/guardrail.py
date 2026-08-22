"""V0.7 SQL governance boundary.

The planner is semantic-first, but generated SQL still crosses an independent
read-only gateway. When sqlglot is installed, the gateway performs AST
validation. A conservative structural fallback keeps offline deployments usable.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set


class SQLGuardrail:
    DENY = re.compile(
        r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|replace|load|outfile|into\s+outfile|copy|call)\b",
        re.I,
    )
    COMMENT = re.compile(r"(--|/\*)")
    TABLE_REF = re.compile(r"\b(?:from|join)\s+([`\w.-]+)", re.I)

    def __init__(self, registry=None):
        self.registry = registry

    @staticmethod
    def _strip_strings(sql: str) -> str:
        return re.sub(r"'(?:''|[^'])*'", "''", sql)

    def _fallback_structure(self, sql: str) -> Dict[str, object]:
        cleaned = sql.strip()
        no_strings = self._strip_strings(cleaned)
        # balanced parentheses is a useful fail-closed structural check
        depth = 0
        for ch in no_strings:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth < 0:
                    raise ValueError("Unbalanced SQL parentheses")
        if depth:
            raise ValueError("Unbalanced SQL parentheses")
        tables = [x.replace('`', '') for x in self.TABLE_REF.findall(no_strings)]
        return {"parser": "structural-fallback", "statement_type": "select", "tables": tables}

    def _ast_validate(self, sql: str) -> Optional[Dict[str, object]]:
        try:
            import sqlglot  # type: ignore
            from sqlglot import exp  # type: ignore
        except Exception:
            return None
        statements = sqlglot.parse(sql, read="mysql")
        if len(statements) != 1:
            raise ValueError("Exactly one SQL statement is required")
        tree = statements[0]
        forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command)
        if any(isinstance(node, forbidden) for node in tree.walk()):
            raise ValueError("AST contains a mutating/command statement")
        if tree.find(exp.Select) is None:
            raise ValueError("AST must contain SELECT")
        tables = []
        for t in tree.find_all(exp.Table):
            parts = [getattr(t, x, None) for x in ("catalog", "db", "name")]
            vals = []
            for p in parts:
                if p:
                    vals.append(str(p))
            if vals:
                tables.append(".".join(vals))
        return {"parser": "sqlglot", "statement_type": "select", "tables": tables}

    def validate(self, sql: str, allowed_tables: Optional[Iterable[str]] = None) -> Dict[str, object]:
        cleaned = sql.strip()
        lowered = cleaned.lower()
        if not cleaned:
            raise ValueError("Empty SQL is forbidden")
        if self.COMMENT.search(cleaned):
            raise ValueError("SQL comments are forbidden in generated plans")
        if not (lowered.startswith("select") or lowered.startswith("with")):
            raise ValueError("Only SELECT/CTE statements are allowed")
        if self.DENY.search(cleaned):
            raise ValueError("Mutating, command or export SQL is forbidden")
        if ";" in cleaned.rstrip(";"):
            raise ValueError("Multiple SQL statements are forbidden")

        parsed = self._ast_validate(cleaned) or self._fallback_structure(cleaned)

        if allowed_tables is not None:
            allowed: Set[str] = {str(t).replace('`', '').lower() for t in allowed_tables}
            cte_names = set(re.findall(r"(?:\bwith\b|,)\s*([A-Za-z_][\w]*)\s+as\s*\(", cleaned, re.I))
            for table in parsed.get("tables", []):
                t = str(table).replace('`', '').lower()
                if t in {x.lower() for x in cte_names}:
                    continue
                # tolerate AST renderings that omit catalog, but never unknown base table names
                if t not in allowed and not any(a.endswith("." + t) or t.endswith("." + a) for a in allowed):
                    raise ValueError(f"SQL references a table outside the governed physical plan: {table}")

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
        return parsed

    def validate_plan(self, plan) -> List[Dict[str, object]]:
        allowed = [x.get("table_ref") for x in plan.physical_plan.get("tables", []) if x.get("table_ref")]
        return [self.validate(sql, allowed_tables=allowed) for sql in plan.sql]
