# V2.8 Audit, Compliance & Policy Center

V2.8 introduces a unified enterprise audit event model without forcing every existing module to rewrite its own operational store immediately.

## Audit event contract

Every native V2.8 event can carry actor, tenant/org/site scope, resource type/id, action, allow/deny decision, success/failure status, before/after payloads, provenance, correlation ID and UTC timestamp. Sensitive fields are redacted before persistence.

## Compatibility model

Existing audit/history collections remain source-of-truth for their modules. `AuditCenter.import_legacy()` normalizes Authentication, Enterprise Access, Secret Access, Runtime Query, Connector Batch and Integration DLQ records into the unified audit center idempotently.

## Correlation trace

HTTP middleware issues or propagates `X-Correlation-ID`. Semantic query execution emits a child audit event under the same correlation ID, enabling request → semantic execution tracing. Future adapters can extend the same contract to RCA and maintenance chains.

## Compliance

Compliance policies match normalized audit fields. Denied or failed governed operations automatically create violations; administrators can add custom match policies, resolve violations, configure retention, dry-run/enforce retention, and export JSON/CSV.
