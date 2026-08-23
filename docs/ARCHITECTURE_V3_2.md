# V3.2 Enterprise Pilot Delivery Architecture

V3.2 keeps V3.1 domain services intact and adds a delivery layer around them.

```text
Customer Sources
 MES / IoT / CMMS
       ↓
Pilot Data Contract
       ↓
Data Binding Blueprint
       ↓
Preview / Approve
       ↓
Integration Runtime
Schema / Watermark / Quality
       ↓
Existing Platform Domains
       ↓
Structured RCA Evidence
       ↓
Pilot Acceptance Report
Technical + Business KPI
       ↓
GO / NO-GO
```

## Design rules

1. Pilot onboarding reuses governed Data Binding and Integration Runtime.
2. Evidence is structured with type/source/provenance; the Pilot layer does not invent a second RCA store.
3. Business acceptance remains separate from technical demo success.
4. Compose default remains a safe Pilot configuration; Doris/Qdrant/OIDC are enabled explicitly.
5. Production Kubernetes requires shared PostgreSQL and real external dependency configuration.
