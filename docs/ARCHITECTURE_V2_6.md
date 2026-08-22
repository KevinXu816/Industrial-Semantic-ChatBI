# V2.6 Enterprise Authentication & SSO Architecture

V2.6 connects the V2.5 enterprise Principal/Scope model to authenticated identities.

```text
OIDC / JWT / Dev Token
        ↓
Authentication Middleware
        ↓
Verified Claims
        ↓
Principal Resolver
        ↓
Enterprise Principal
        ↓
Tenant / Site / Asset / Connector Scope
        ↓
Semantic RBAC/RLS + Resource Authorization
```

## Authentication modes

- `disabled` — default, preserves zero-config local/demo compatibility.
- `dev` — local HS256 token issuer for isolated demonstrations and tests only.
- `jwt` — HS256 bearer-token validation using `AUTH_JWT_SECRET`.
- `oidc` — OIDC discovery + JWKS signature validation; intended for Keycloak, Microsoft Entra ID and other standards-compliant providers using RSA-signed JWT access tokens.

OIDC mode requires the `auth` extra: `pip install -e '.[auth]'`.

## Claim mapping

Claim names are configuration-driven and support dotted paths, e.g. `realm_access.roles` for Keycloak. Claims can map to `tenant_id`, `org_id`, roles, site scopes, asset scopes and connector scopes. Existing Principals are resolved by principal ID, external subject or email. Optional auto-provisioning is fail-closed when the token references an unknown tenant.

## Security boundaries

Authentication answers *who is calling*. V2.5 `EnterpriseScopeEngine` answers *what resources that Principal may access*. Semantic RBAC/RLS continues to govern query meaning. Authentication-enabled Scoped APIs use the Principal from the verified token rather than trusting a caller-supplied Principal ID. Only a same-tenant `tenant_admin` can explicitly act on behalf of another Principal.

## Frontend

The Identity panel exposes authentication mode/status and a session-only Bearer Token field for pilot operations. Tokens are stored in `sessionStorage`, not persisted to the server. Production browser SSO should normally use an OIDC Authorization Code + PKCE client or an authentication-aware reverse proxy/gateway.
