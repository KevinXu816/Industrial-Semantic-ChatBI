# V2.4 Connector SDK & Edge/Data Agent Contract

## Goal
V2.4 stabilizes the OT/Edge-to-platform boundary. Vendor clients remain outside the platform core and normalize data into a governed `ConnectorBatch` contract.

```text
OT / Edge Site
  InfluxDB | JDBC | REST | MQTT | Files
             ↓
       Connector Adapter
             ↓
         Edge Agent
             ↓
       ConnectorBatch
             ↓
Central Platform
  Connector Registry
             ↓
  V2.3 Integration Runtime
  Schema → Watermark → Quality → DLQ
             ↓
  Asset / Condition / Alarm / Work Order
```

## Connector lifecycle
`draft → approved → retired`. A connector can be approved only when its referenced Data Binding is approved.

## ConnectorBatch v1
Required fields: `batch_id`, `connector_id`, `binding_id`, `records`.
Optional fields: `agent_id`, `source`, `schema`, `cursor`, `diagnostics`, `observed_at`.

`batch_id` is idempotent. A network retry of an already processed batch returns the stored result and does not write domain data twice.

## Edge Agent
Edge Agent registration persists site, version, capabilities and diagnostics. Heartbeats expose effective health (`online`, `stale`, `unknown`) without pretending the core platform owns source connectivity.

## SDK adapters
The package exposes `BaseConnectorAdapter` plus InfluxDB/JDBC/REST/MQTT/File adapter contracts. They build normalized batches; real vendor I/O is implemented in the edge deployment or customer adapter package.

## Security boundary
Connector configuration stored centrally should contain logical configuration, not raw OT credentials. Secrets remain in edge-side secret stores or vendor adapter runtime.
