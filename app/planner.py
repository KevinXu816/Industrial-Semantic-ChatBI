from .models import QueryPlan, SemanticIntent
from .semantic import SemanticRegistry


class QueryPlanner:
    """SQL plan builder driven by ontology physical mappings rather than hard-coded table names."""

    def __init__(self, registry: SemanticRegistry):
        self.registry = registry

    def _table(self, entity: str) -> str:
        return self.registry.table_ref(entity)

    def _col(self, entity: str, prop: str) -> str:
        return self.registry.column(entity, prop)

    def _machine_id_subquery(self, business_ref: str) -> str:
        mt = self._table("Machine")
        mid = self._col("Machine", "machine_id")
        mcode = self._col("Machine", "machine_code")
        mname = self._col("Machine", "machine_name")
        return (
            f"SELECT {mid} FROM {mt} "
            f"WHERE {mcode} = '{business_ref}' OR {mname} = '{business_ref}' LIMIT 1"
        )

    def build(self, intent: SemanticIntent) -> QueryPlan:
        if not intent.machine_ref:
            raise ValueError("Demo requires a machine reference, e.g. A101")
        if not intent.metric:
            raise ValueError("Unable to resolve a governed metric from the question")

        days = intent.time_window_days
        machine = intent.machine_ref.replace("'", "''")
        sql = []

        mt = self._table("Machine")
        mid = self._col("Machine", "machine_id")
        mcode = self._col("Machine", "machine_code")
        mname = self._col("Machine", "machine_name")
        machine_id_sql = self._machine_id_subquery(machine)

        # Evidence query: resolve the business reference to the canonical physical ID.
        sql.append(f"""
SELECT {mid} AS machine_id, {mcode} AS machine_code, {mname} AS machine_name
FROM {mt}
WHERE {mcode} = '{machine}' OR {mname} = '{machine}'
LIMIT 10
""".strip())

        et = self._table("EnergyObservation")
        emid = self._col("EnergyObservation", "machine_id")
        ets = self._col("EnergyObservation", "ts")
        ekwh = self._col("EnergyObservation", "energy_kwh")

        if intent.metric == "specific_energy_consumption":
            pt = self._table("ProductionObservation")
            pmid = self._col("ProductionObservation", "machine_id")
            pts = self._col("ProductionObservation", "ts")
            pout = self._col("ProductionObservation", "output_qty")
            sql.append(f"""
SELECT
    e.{emid} AS machine_id,
    SUM(e.{ekwh}) AS energy_kwh,
    SUM(p.{pout}) AS output_qty,
    SUM(e.{ekwh}) / NULLIF(SUM(p.{pout}), 0) AS specific_energy_kwh_per_piece
FROM {et} e
JOIN {pt} p
  ON e.{emid} = p.{pmid}
 AND DATE_TRUNC(e.{ets}, 'hour') = p.{pts}
WHERE e.{emid} = ({machine_id_sql})
  AND e.{ets} >= NOW() - INTERVAL {days} DAY
GROUP BY e.{emid}
""".strip())
            trend_days = days * 2
        else:
            trend_days = days

        sql.append(f"""
SELECT DATE({ets}) AS d,
       SUM({ekwh}) AS energy_kwh
FROM {et}
WHERE {emid} = ({machine_id_sql})
  AND {ets} >= NOW() - INTERVAL {trend_days} DAY
GROUP BY DATE({ets})
ORDER BY d
""".strip())

        if intent.analysis_mode == "diagnostic":
            at = self._table("AlarmEvent")
            amid = self._col("AlarmEvent", "machine_id")
            aname = self._col("AlarmEvent", "alarm_name")
            asev = self._col("AlarmEvent", "severity")
            atime = self._col("AlarmEvent", "event_time")
            sql.append(f"""
SELECT {aname} AS alarm_name, {asev} AS severity,
       COUNT(*) AS cnt, MAX({atime}) AS last_event_time
FROM {at}
WHERE {amid} = ({machine_id_sql})
  AND {atime} >= NOW() - INTERVAL {days} DAY
GROUP BY {aname}, {asev}
ORDER BY cnt DESC
LIMIT 20
""".strip())

            wt = self._table("WorkOrder")
            wmid = self._col("WorkOrder", "machine_id")
            wtime = self._col("WorkOrder", "created_at")
            wfault = self._col("WorkOrder", "fault_description")
            waction = self._col("WorkOrder", "action")
            sql.append(f"""
SELECT {wtime} AS created_at, {wfault} AS fault_desc, {waction} AS maintenance_action
FROM {wt}
WHERE {wmid} = ({machine_id_sql})
  AND {wtime} >= NOW() - INTERVAL {max(days * 4, 30)} DAY
ORDER BY {wtime} DESC
LIMIT 20
""".strip())

        return QueryPlan(
            intent=intent,
            sql=sql,
            notes=[
                "Ontology physical mappings are the source of table/column locations.",
                "Business machine references are resolved to a canonical machine_id before fact/event filtering.",
                "Metric definitions come from the governed semantic registry, not from the LLM.",
                "The LLM semantic planner, when enabled, may resolve intent but never emits executable SQL.",
            ],
        )
