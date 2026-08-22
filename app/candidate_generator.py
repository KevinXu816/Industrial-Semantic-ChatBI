import re
from typing import Dict, List, Tuple
from .models import (
    MetadataSnapshot, SemanticCandidate, CandidateProperty, CandidateRelationship, CandidateMetric
)


ENTITY_HINTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"device|machine|equipment|asset", re.I), "Machine"),
    (re.compile(r"alarm|alert|fault_event", re.I), "AlarmEvent"),
    (re.compile(r"work.?order|maintenance", re.I), "WorkOrder"),
    (re.compile(r"production|output|yield", re.I), "ProductionObservation"),
    (re.compile(r"energy|power|electric", re.I), "EnergyObservation"),
]

PROPERTY_HINTS = {
    "device_id": "machine_id",
    "machine_id": "machine_id",
    "asset_id": "machine_id",
    "device_code": "machine_code",
    "machine_code": "machine_code",
    "device_name": "machine_name",
    "machine_name": "machine_name",
    "device_type": "machine_type",
    "factory_id": "factory_id",
    "ts": "ts",
    "stat_time": "ts",
    "event_time": "event_time",
    "created_at": "created_at",
    "energy_kwh": "energy_kwh",
    "active_power_kw": "active_power_kw",
    "good_qty": "output_qty",
    "alarm_code": "alarm_code",
    "alarm_name": "alarm_name",
    "severity": "severity",
    "fault_desc": "fault_description",
    "maintenance_action": "action",
}


def _entity_name(table: str) -> tuple[str, float]:
    for pattern, entity in ENTITY_HINTS:
        if pattern.search(table):
            return entity, 0.90
    return "BusinessEntity", 0.45


def _logical_type(dtype: str) -> str:
    d = dtype.lower()
    if any(x in d for x in ["int", "decimal", "double", "float", "real"]):
        return "number"
    if any(x in d for x in ["date", "time"]):
        return "datetime"
    if "bool" in d:
        return "boolean"
    return "string"


def generate_candidates(snapshot: MetadataSnapshot) -> List[SemanticCandidate]:
    out: List[SemanticCandidate] = []
    table_index: Dict[str, SemanticCandidate] = {}

    for catalog in snapshot.catalogs:
        for db in catalog.databases:
            for table in db.tables:
                entity, base_conf = _entity_name(table.name)
                props = []
                mapped_hits = 0
                for col in table.columns:
                    logical = PROPERTY_HINTS.get(col.name.lower(), col.name.lower())
                    if col.name.lower() in PROPERTY_HINTS:
                        mapped_hits += 1
                    props.append(CandidateProperty(
                        logical_name=logical,
                        physical_column=col.name,
                        data_type=_logical_type(col.data_type),
                    ))
                conf = min(0.99, base_conf + min(mapped_hits * 0.015, 0.08))
                candidate = SemanticCandidate(
                    id=f"{catalog.name}.{db.name}.{table.name}",
                    entity=entity,
                    description=f"Auto-discovered candidate for {catalog.name}.{db.name}.{table.name}",
                    confidence=round(conf, 2),
                    physical_mapping={"catalog": catalog.name, "schema": db.name, "table": table.name},
                    properties=props,
                    relationships=[],
                    metrics=[],
                    status="pending",
                    evidence=[f"table_name={table.name}", f"mapped_columns={mapped_hits}/{max(len(table.columns),1)}"],
                )
                table_index[candidate.id] = candidate
                out.append(candidate)

    # Relationship candidates: tables sharing machine_id-like columns.
    machines = [c for c in out if c.entity == "Machine"]
    for candidate in out:
        if candidate.entity == "Machine" or not machines:
            continue
        logical_props = {p.logical_name for p in candidate.properties}
        if "machine_id" in logical_props:
            relation = {
                "EnergyObservation": "HAS_ENERGY",
                "ProductionObservation": "HAS_PRODUCTION",
                "AlarmEvent": "HAS_ALARM",
                "WorkOrder": "HAS_WORK_ORDER",
            }.get(candidate.entity, "HAS_RELATED")
            candidate.relationships.append(CandidateRelationship(
                from_entity="Machine",
                relation=relation,
                to_entity=candidate.entity,
                on="machine_id",
                confidence=0.92,
            ))

        prop_map = {p.logical_name: p for p in candidate.properties}
        if "energy_kwh" in prop_map:
            candidate.metrics.append(CandidateMetric(
                name="energy_consumption",
                expression="SUM(energy_kwh)",
                unit="kWh",
                confidence=0.95,
            ))
        if "output_qty" in prop_map:
            candidate.metrics.append(CandidateMetric(
                name="production_output",
                expression="SUM(output_qty)",
                unit="piece",
                confidence=0.95,
            ))

    return out
