# Industrial Semantic ChatBI V0.5 — Generic Semantic Engine

## Goal
V0.5 removes the execution-time assumption that every analysis is anchored on `Machine/machine_id`. The semantic contract now starts from a generic **subject entity** and validates all metric access through the ontology.

## New semantic intent
```json
{
  "subject": {"entity": "Factory", "reference": "F01"},
  "metrics": ["energy_consumption"],
  "dimensions": [],
  "filters": [],
  "time_range": {"type": "relative", "value": 7, "unit": "day"},
  "time_grain": "day",
  "comparison": {"type": "previous_period"},
  "analysis_mode": "diagnostic"
}
```

Legacy `machine_ref`, `metric`, and `time_window_days` remain synchronized for API/UI compatibility.

## Planning pipeline
Question → SemanticIntent → MetricDependencyGraph → Subject Entity → Ontology Path → Logical Plan → Governed Physical SQL → Guardrail → Executor.

## Generic subject scoping
A metric leaf is no longer required to expose `machine_id`. The planner finds a path from the subject to the metric entity and emits an `EXISTS` scope using governed relationship keys. This supports multi-hop scopes such as:

`Factory → ProductionLine → Machine → EnergyObservation`

## Safety principle
V0.5 intentionally rejects unsupported cross-entity filters rather than guessing a JOIN. This keeps the semantic engine deterministic and auditable.

## Next V0.6 targets
- Multi-metric plans and shared grain alignment
- Dimension/group-by compiler
- Cross-entity filter sub-plans
- Absolute time windows and comparison periods
- SQL AST guardrail + RBAC/RLS policy injection
- Doris physical federation planner
