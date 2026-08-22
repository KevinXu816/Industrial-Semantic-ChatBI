# V2.9 Observability & SRE Control Plane

V2.9 separates **audit/compliance** from **runtime observability**. Audit answers *who did what and was it allowed?* Observability answers *where did the request spend time, what dependency is unhealthy, and are service objectives being met?*

## Runtime flow

```text
Client / Edge / Service
        ↓
W3C traceparent + X-Correlation-ID
        ↓
FastAPI server span
        ↓
Application / dependency spans
        ↓
Telemetry Store
        ├─ HTTP metrics (availability/error/latency)
        ├─ Trace explorer
        ├─ Dependency health snapshots
        ├─ SLO evaluation
        ├─ Alert rules/incidents
        └─ Prometheus exposition
```

`X-Correlation-ID` continues to connect operational traces to the V2.8 audit center. `trace_id/span_id` are for high-volume SRE telemetry and are not used as compliance records.

## Trace context

The API accepts the W3C `traceparent` header. If absent, it creates a 32-hex `trace_id` and 16-hex `span_id`. Responses include:

- `X-Correlation-ID`
- `X-Trace-ID`
- `traceparent`

This contract is OpenTelemetry-compatible. V2.9 remains dependency-light and does not require an OTLP collector for local demos.

## SLOs

Bundled defaults:

- Platform availability >= 99.9%
- HTTP p95 latency <= 1500 ms

SLO definitions are persisted and can be replaced with enterprise targets.

## Dependency health

Current probes cover persistence (JSON/PostgreSQL), knowledge backend (local/Qdrant/pgvector), Doris execution mode, authentication, secret provider, Edge Agents, Connectors and Integration Runtime.

## Prometheus

Prometheus text format is available at:

`GET /observability/prometheus`

The pre-existing `/metrics` endpoint remains the business Metric Registry and is intentionally not reused.
