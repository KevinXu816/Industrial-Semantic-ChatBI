# V0.7 — Enterprise Governance & Evidence Architecture

V0.7 moves the project from a governed semantic analytics prototype toward an enterprise-ready control plane. It preserves the V0.6 generic planner and adds independent policy, SQL, cost, lineage and evidence boundaries around it.

## Execution pipeline

```text
Natural language / SemanticIntent
          |
          v
   Semantic RBAC Policy
          |
          +--> entity/metric authorization
          +--> column policy
          +--> time-window policy
          +--> trusted row-policy injection as SemanticFilter
          |
          v
 Generic Semantic Planner (V0.6)
          |
          v
 Logical + Physical Plan
          |
          +--> Query Cost Estimator
          +--> allowed physical table set
          |
          v
 SQL Governance Gateway
          |
          +--> SQLGlot AST validation when installed
          +--> conservative structural fallback offline
          +--> SELECT/CTE only
          +--> single statement
          +--> governed physical tables only
          +--> bounded time-series query
          |
          v
       Executor / Doris
          |
          +--> Query lineage
          +--> RCA evidence graph
```

## Governance principles

1. **LLM never receives authority to write executable SQL.** It resolves semantic intent only.
2. **RLS is semantic, not string concatenation.** Trusted caller attributes become `SemanticFilter` objects before planning.
3. **RBAC is evaluated before execution.** Roles can constrain entities, metrics, columns, time ranges and cost budgets.
4. **The SQL gateway distrusts the planner.** Generated SQL is checked again against the physical plan.
5. **Lineage is query-native.** Each plan records semantic metrics, ontology entities, physical tables/catalogs and the governance decision.
6. **Semantic changes are versioned.** Ontology/metric mutations create content-addressed snapshots.
7. **RCA is evidence-first.** Hypotheses, supporting evidence and recommended checks form a graph rather than an opaque LLM paragraph.

## Policy configuration

`config/governance.yaml` defines roles and optional row policies. Row policy values can reference trusted attributes:

```yaml
row_policies:
  factory_analyst:
    - entity: Machine
      property: factory_id
      operator: '='
      value: '${factory_id}'
```

A request can provide:

```json
{
  "question": "F01 工厂最近 7 天能耗",
  "user": "demo-user",
  "roles": ["factory_analyst"],
  "attributes": {"factory_id": "F01"}
}
```

The attribute becomes a governed semantic filter; it is not interpolated as arbitrary SQL.

## SQL AST mode

V0.7 works without new dependencies by using a conservative structural parser. Installing the optional governance extra enables SQLGlot AST validation:

```bash
pip install -e '.[governance]'
```

The fallback remains intentionally fail-closed for generated SQL patterns used by this project.

## Query cost

The initial estimator uses time window, entity count, metrics, dimensions, filters, catalogs, federation and comparison multipliers. This is a deterministic admission-control score, not a database optimizer estimate. A later version should combine it with Doris `EXPLAIN` cardinality/cost information.

## Evidence graph

For diagnostic queries, `EvidenceGraphBuilder` connects:

```text
Subject -> Metric
Subject -> Entity -> Physical Source
Evidence -> Hypothesis -> Recommendation
```

This gives RCA a traceable substrate that can later incorporate FMEA, SOP, alarms, time-series detectors, work orders, manuals and knowledge-graph relations.

## V0.8 recommended focus

- Doris `EXPLAIN`-based cost/cardinality estimation
- policy administration UI and external identity integration
- stronger tenant context propagation
- field-level output masking
- FMEA/SOP/manual knowledge ingestion
- statistical anomaly/event detector
- RCA hypothesis ranking with evidence provenance
