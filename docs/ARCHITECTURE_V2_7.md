# V2.7 Enterprise Secrets & Credential Management

V2.7 separates credential metadata from secret values. Platform configuration stores only `secret://provider/name` references. Runtime providers resolve values only when needed.

## Providers
- `env`: process/environment secret
- `file`: Docker/Kubernetes mounted secret files under `SECRETS_FILE_ROOT`
- `vault`: HashiCorp Vault KV v2 adapter (`hvac` optional extra)
- `azure-key-vault`: Azure Key Vault adapter (`azure-identity` / `azure-keyvault-secrets` optional extra)

## Security boundaries
1. Secret values are never returned from platform Secret APIs.
2. Secret Registry persists only ID, reference, scope, version and rotation metadata.
3. Connector configs reject obvious inline credential fields.
4. Datasource and LLM configuration prefer `credential_ref` / `api_key_ref`.
5. Doris, Qdrant and JWT bootstrap secrets support `*_REF` environment settings.
6. Secret availability/access generates an audit event without persisting the secret value.

## Example
`DORIS_PASSWORD_REF=secret://file/doris_password`

The file `/run/secrets/doris_password` can be provided by Docker/Kubernetes secret mounting.
