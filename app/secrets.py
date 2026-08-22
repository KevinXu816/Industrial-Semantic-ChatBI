"""V2.7 enterprise secret references and runtime secret providers.

The registry stores metadata/reference only. Secret values are never returned by APIs
or persisted in the generic repository. Runtime providers resolve values only at the
point of use.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import hashlib, os, re
from .persistence import Repository
from .enterprise_identity import default_tenant_id

SENSITIVE_KEYS = {
    "password", "passwd", "pwd", "api_key", "apikey", "token", "access_token",
    "client_secret", "secret", "private_key", "authorization"
}

def _now(): return datetime.now(timezone.utc).isoformat()

def is_secret_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("secret://")

def parse_secret_ref(ref: str, default_provider: str = "env"):
    if not is_secret_ref(ref): raise ValueError("secret reference must start with secret://")
    body = ref[len("secret://"):].strip("/")
    if not body: raise ValueError("secret reference name is required")
    parts = body.split("/", 1)
    if len(parts) == 1: return default_provider, parts[0]
    return parts[0].lower(), parts[1]

class SecretProvider:
    name = "provider"
    def resolve(self, name: str) -> str: raise NotImplementedError
    def health(self): return {"provider": self.name, "status": "ok"}

class EnvironmentSecretProvider(SecretProvider):
    name = "env"
    def resolve(self, name: str) -> str:
        value = os.getenv(name)
        if value is None: raise KeyError(f"environment secret not found: {name}")
        return value

class FileSecretProvider(SecretProvider):
    """Docker/Kubernetes mounted-secret provider.

    secret://file/foo resolves <SECRETS_FILE_ROOT>/foo. Path traversal is rejected.
    """
    name = "file"
    def __init__(self, root: str | None = None): self.root = Path(root or os.getenv("SECRETS_FILE_ROOT", "/run/secrets")).resolve()
    def resolve(self, name: str) -> str:
        target = (self.root / name).resolve()
        if self.root != target and self.root not in target.parents: raise PermissionError("secret file path escapes configured root")
        if not target.is_file(): raise KeyError(f"secret file not found: {name}")
        return target.read_text(encoding="utf-8").rstrip("\r\n")
    def health(self): return {"provider": self.name, "status": "ok" if self.root.exists() else "unavailable", "root": str(self.root)}

class VaultSecretProvider(SecretProvider):
    name = "vault"
    def resolve(self, name: str) -> str:
        try: import hvac
        except ImportError as exc: raise RuntimeError("Vault provider requires hvac") from exc
        client = hvac.Client(url=os.getenv("VAULT_ADDR"), token=os.getenv("VAULT_TOKEN"))
        mount = os.getenv("VAULT_KV_MOUNT", "secret")
        path, _, field = name.partition("#")
        result = client.secrets.kv.v2.read_secret_version(path=path, mount_point=mount)
        data = result["data"]["data"]
        key = field or "value"
        if key not in data: raise KeyError(f"Vault field not found: {key}")
        return str(data[key])

class AzureKeyVaultSecretProvider(SecretProvider):
    name = "azure-key-vault"
    def resolve(self, name: str) -> str:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
        except ImportError as exc: raise RuntimeError("Azure Key Vault provider requires azure-identity and azure-keyvault-secrets") from exc
        url = os.getenv("AZURE_KEY_VAULT_URL", "")
        if not url: raise RuntimeError("AZURE_KEY_VAULT_URL is required")
        secret_name, _, version = name.partition("#")
        client = SecretClient(vault_url=url, credential=DefaultAzureCredential())
        return client.get_secret(secret_name, version or None).value

class SecretRegistry:
    COLLECTION="secret_registry"; AUDIT="secret_access_audit"
    def __init__(self, repo: Repository): self.repo=repo
    def register(self, payload: Dict[str,Any], actor="security_admin"):
        secret_id=str(payload.get("secret_id") or "").strip()
        ref=str(payload.get("secret_ref") or "").strip()
        if not secret_id or not ref: raise ValueError("secret_id and secret_ref are required")
        provider,name=parse_secret_ref(ref, os.getenv("SECRETS_DEFAULT_PROVIDER","env"))
        row={"secret_id":secret_id,"secret_ref":ref,"provider":provider,"secret_name":name,
             "tenant_id":str(payload.get("tenant_id") or default_tenant_id()),"org_id":str(payload.get("org_id") or ""),
             "site_id":str(payload.get("site_id") or ""),"purpose":str(payload.get("purpose") or ""),
             "version":str(payload.get("version") or "1"),"status":str(payload.get("status") or "active"),
             "rotate_after":payload.get("rotate_after"),"updated_at":_now(),"updated_by":actor}
        return self.repo.put(self.COLLECTION,secret_id,row)
    def get(self, secret_id): return self.repo.get(self.COLLECTION,secret_id)
    def list(self, limit=200): return self.repo.list(self.COLLECTION,limit=limit)
    def rotate(self, secret_id, payload, actor="security_admin"):
        row=self.get(secret_id)
        if not row: raise KeyError(secret_id)
        if payload.get("secret_ref"):
            provider,name=parse_secret_ref(str(payload["secret_ref"]), os.getenv("SECRETS_DEFAULT_PROVIDER","env")); row.update({"secret_ref":payload["secret_ref"],"provider":provider,"secret_name":name})
        row["version"]=str(payload.get("version") or int(row.get("version","0"))+1 if str(row.get("version","0")).isdigit() else payload.get("version") or "next")
        row["rotated_at"]=_now(); row["rotated_by"]=actor; row["updated_at"]=_now()
        return self.repo.put(self.COLLECTION,secret_id,row)
    def audit(self, secret_id, principal, purpose, success, provider="", error=""):
        raw=f"{secret_id}:{principal}:{_now()}"; key="SEA-"+hashlib.sha1(raw.encode()).hexdigest()[:16]
        self.repo.put(self.AUDIT,key,{"audit_id":key,"secret_id":secret_id,"principal":principal,"purpose":purpose,"success":bool(success),"provider":provider,"error":error,"at":_now()})
    def audits(self, limit=200): return self.repo.list(self.AUDIT,limit=limit)
    def summary(self):
        rows=self.list(1000); return {"registered":len(rows),"active":sum(1 for r in rows if r.get("status")=="active"),"providers":sorted(set(r.get("provider","") for r in rows if r.get("provider"))) }

class SecretManager:
    def __init__(self, registry: SecretRegistry):
        self.registry=registry; self.providers={"env":EnvironmentSecretProvider(),"file":FileSecretProvider(),"vault":VaultSecretProvider(),"azure-key-vault":AzureKeyVaultSecretProvider()}
    def resolve_ref(self, ref: str, principal="runtime", purpose="runtime") -> str:
        provider_name,name=parse_secret_ref(ref,os.getenv("SECRETS_DEFAULT_PROVIDER","env")); provider=self.providers.get(provider_name)
        if not provider: raise ValueError(f"unsupported secret provider: {provider_name}")
        try:
            value=provider.resolve(name); self.registry.audit(ref,principal,purpose,True,provider_name); return value
        except Exception as exc:
            self.registry.audit(ref,principal,purpose,False,provider_name,str(exc)); raise
    def resolve_id(self, secret_id: str, principal="runtime", purpose="runtime") -> str:
        row=self.registry.get(secret_id)
        if not row or row.get("status")!="active": raise KeyError(f"active secret metadata not found: {secret_id}")
        return self.resolve_ref(row["secret_ref"],principal,purpose)
    def check(self, secret_id: str, principal="security_admin"):
        row=self.registry.get(secret_id)
        if not row: raise KeyError(secret_id)
        try:
            value=self.resolve_ref(row["secret_ref"],principal,"availability_check")
            return {"secret_id":secret_id,"available":bool(value),"provider":row["provider"],"version":row.get("version")}
        except Exception as exc: return {"secret_id":secret_id,"available":False,"provider":row.get("provider"),"version":row.get("version"),"error":str(exc)}
    def health(self):
        return {"default_provider":os.getenv("SECRETS_DEFAULT_PROVIDER","env"),"registry":self.registry.summary(),"providers":{k:v.health() for k,v in self.providers.items() if k in {"env","file"}}}

def reject_inline_secrets(payload: Dict[str,Any], path="config"):
    """Fail closed when a connector config persists obvious credential fields."""
    def walk(obj,p):
        if isinstance(obj,dict):
            for k,v in obj.items():
                lk=str(k).lower()
                if lk in SENSITIVE_KEYS and v not in (None, "", "***") and not is_secret_ref(v):
                    raise ValueError(f"inline secret is not allowed at {p}.{k}; use secret_ref/credential_ref")
                walk(v,f"{p}.{k}")
        elif isinstance(obj,list):
            for i,v in enumerate(obj): walk(v,f"{p}[{i}]")
    walk(payload,path)
    return True

def resolve_bootstrap_secret(ref_env: str, legacy_env: str = "") -> str:
    """Resolve a process/bootstrap secret without persisting it or creating audit state.

    Used by early infrastructure initialization (OIDC/JWT, Doris, Qdrant). Runtime
    business credentials should prefer SecretManager so access can be audited.
    """
    ref = os.getenv(ref_env, "").strip()
    if not ref:
        return os.getenv(legacy_env, "") if legacy_env else ""
    provider_name, name = parse_secret_ref(ref, os.getenv("SECRETS_DEFAULT_PROVIDER", "env"))
    providers = {"env": EnvironmentSecretProvider(), "file": FileSecretProvider(), "vault": VaultSecretProvider(), "azure-key-vault": AzureKeyVaultSecretProvider()}
    provider = providers.get(provider_name)
    if not provider: raise ValueError(f"unsupported secret provider: {provider_name}")
    return provider.resolve(name)
