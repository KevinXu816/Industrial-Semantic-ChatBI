# Industrial Semantic ChatBI V0.4 Architecture

## Goal

V0.4 moves query planning from scenario-specific SQL assembly to a governed semantic execution chain:

`Question -> SemanticIntent -> Metric Dependency Graph -> Required Entities -> Ontology Paths -> Physical SQL -> Guardrail -> Executor -> RCA Evidence`

The LLM can resolve intent, but it is not allowed to emit executable SQL.

## New core components

### MetricDependencyGraph

`app/metric_graph.py` recursively expands derived metrics, detects dependency cycles, discovers leaf metrics, and derives the physical entities required to calculate the requested metric.

Example:

` specific_energy_consumption -> energy_consumption + production_output `

The planner therefore discovers `EnergyObservation` and `ProductionObservation` from configuration rather than hard-coding them.

### Ontology-driven QueryPlanner

`app/planner.py` now:

1. resolves the business machine reference to canonical `machine_id`;
2. expands the requested metric through the Metric Registry;
3. compiles leaf metric expressions using logical-to-physical column mappings;
4. derives required semantic entities;
5. validates connectivity through `JoinPathFinder`;
6. emits evidence queries for diagnostic entities;
7. records metric dependencies, required entities and join paths in `QueryPlan`.

### Evidence-first RCA

`app/rca.py` adds a small RCA contract. The current mock implementation produces ranked hypotheses with confidence, evidence and recommended checks. It is intentionally isolated so future implementations can combine statistical detection, rules, RAG, knowledge graphs and LLM reasoning without changing query governance.

### Safer semantic overrides

Custom metric YAML now performs a field-level overlay. Editing a display description or synonym no longer accidentally removes governed execution fields such as `entity`, `time_field` or `dependencies`.

### Guardrails

The SQL guardrail now supports governed `WITH ... SELECT` plans, rejects multiple statements/comments/export patterns, and continues enforcing bounded time-series queries. Database permissions and an AST SQL gateway are still required for production.

## Recommended next iteration

V0.5 should focus on:

- generic dimensions/group-by/time-grain in `SemanticIntent`;
- datasource dialect abstraction (Doris as the preferred federation execution engine);
- PostgreSQL-backed semantic/version/audit storage;
- RBAC plus row/column-level policies;
- metric validation and deployment workflow;
- RCA rules/knowledge graph and evidence scoring;
- standardized executor result sets instead of mock-specific response shapes.
