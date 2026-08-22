# V2.5 Enterprise Identity & Multi-Tenant Governance

V2.5 adds an enterprise resource-scope control plane on top of the existing semantic RBAC/RLS layer.

## Two governance planes

- **Semantic governance** answers: which entities, metrics, columns and rows may a query use?
- **Enterprise scope governance** answers: which tenant, organization, site, asset, connector and edge-agent resources may a principal access?

They are intentionally independent and composable.

## Hierarchy

```text
Tenant
  -> Organization
      -> Site
          -> Asset / Connector / Edge Agent
```

A principal has roles plus optional `site_ids`, `asset_ids` and `connector_ids`. Empty scope lists mean all resources inside the principal's tenant; non-empty lists narrow the resource set.

## Backward compatibility

Records without `tenant_id` are interpreted as belonging to `DEFAULT_TENANT_ID` (default `default`). Existing single-enterprise installations therefore keep working without data migration.

## Operational isolation

Approved Data Bindings, Connectors and Edge Agents carry tenant/site scope. Connector approval checks Binding scope; ConnectorBatch submission checks Edge Agent vs Connector scope before V2.3 Integration Runtime execution.

## Human/AI domain isolation

FMEA and RCA Case objects also carry tenant/site context. Scoped APIs apply role permission plus tenant/site/asset filters, preventing cross-site reliability knowledge exposure.

## Audit

Every explicit access check and scoped-list operation produces an append-only enterprise access-audit entry containing principal, resource/action, allow/deny decision and evaluated resource scope.
