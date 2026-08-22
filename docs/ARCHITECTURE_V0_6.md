# V0.6 Architecture — Generic Semantic Analytics + Doris Physical Planning

V0.6 turns the V0.5 generic subject planner into a multi-metric semantic analytics engine.

## Execution flow

```text
Natural Language / SemanticIntent
              ↓
      Governed Semantic Contract
              ↓
     Metric Dependency Graph
              ↓
Ontology Paths for Subject / Dimension / Filter
              ↓
        Logical Query Plan
              ↓
    Doris Physical Planner
              ↓
Federated SQL across governed catalogs
              ↓
          Evidence / RCA
```

## New capabilities

### Multi-metric execution
A single plan can request multiple base and derived metrics. Leaf metrics are calculated once and reused by derived metric expressions.

### Dimension planning
Dimensions use `Entity.property` syntax, for example `ProductionLine.line_name`. The planner discovers the ontology path from every metric entity to the dimension entity and produces governed JOIN + GROUP BY clauses.

### Cross-entity filters
A filter such as `Machine.machine_type = 'A'` can constrain an `EnergyObservation` metric even though the property lives on another entity. The planner builds an ontology-governed `EXISTS` subplan rather than ignoring the filter or asking the LLM to invent a join.

### Comparison
`previous_period` and explicit `baseline` comparisons generate current, previous/baseline, and percentage-change measures deterministically.

### Doris physical plan
`QueryPlan.physical_plan` reports the Doris dialect, physical tables, catalogs, whether the plan is federated, dimensions, and comparison mode. Physical names always come from semantic mappings.

## Example

```json
{
  "subject": {"entity": "Factory", "reference": "F01"},
  "metrics": [
    "energy_consumption",
    "production_output",
    "specific_energy_consumption"
  ],
  "dimensions": ["ProductionLine.line_name"],
  "time_range": {"type": "relative", "value": 30, "unit": "day"},
  "comparison": {"type": "previous_period"},
  "analysis_mode": "descriptive"
}
```

The physical plan spans the `internal` and `mysql_mes` Doris catalogs, while the metric formula remains governed by the Metric Registry.

## V0.7 recommended focus

1. SQL AST governance and policy injection (RBAC/RLS/column policies).
2. Query cost estimation and execution limits.
3. Cardinality-aware ontology join planning.
4. Semantic versioning/lineage and deployment lifecycle.
5. RCA evidence graph + SOP/FMEA/manual RAG.
6. Production-grade Doris catalog discovery and pushdown diagnostics.

## Known boundaries

V0.6 is still a product-development version, not a complete enterprise data virtualization engine. Doris remains the intended federation/execution layer. The Python service owns semantics, planning, governance and Agent-facing contracts; it should not duplicate Doris query optimization.
