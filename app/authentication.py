"""V2.6 enterprise authentication and SSO integration.

Authentication (who are you?) is intentionally separate from the V2.5 enterprise
scope engine (what may you access?).  The default mode is ``disabled`` so local
POCs remain zero-config.  Enterprise deployments can enable ``dev``, ``jwt`` or
``oidc`` modes.

- disabled: no token required; existing V2.5 behavior remains unchanged.
- dev: HS256 tokens signed with AUTH_DEV_SECRET, useful for isolated demos/tests.
- jwt: HS256 bearer JWT verification with AUTH_JWT_SECRET.
- oidc: OIDC discovery/JWKS verification (PyJWT[crypto] optional dependency).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request

from .enterprise_identity import EnterpriseIdentityStore, default_tenant_id, PERMISSIONS
from .secrets import resolve_bootstrap_secret


class AuthenticationError(PermissionError):
    pass


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _json_b64(value: Dict[str, Any]) -> str:
    return _b64url_encode(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _claim(claims: Dict[str, Any], path: str) -> Any:
    """Resolve direct or dotted claim paths (e.g. realm_access.roles for Keycloak)."""
    current: Any = claims
    for part in str(path or "").split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _split_claim(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x)]
    if isinstance(value, str):
        # OIDC providers commonly emit either arrays or space/comma-delimited strings.
        raw = value.replace(",", " ").split()
        return [x for x in raw if x]
    return [str(value)]


@dataclass
class AuthConfig:
    mode: str
    issuer: str
    audience: str
    client_id: str
    auto_provision: bool
    principal_claim: str
    tenant_claim: str
    org_claim: str
    roles_claim: str
    sites_claim: str
    assets_claim: str
    connectors_claim: str
    name_claim: str
    email_claim: str
    stale_jwks_seconds: int

    @classmethod
    def from_env(cls) -> "AuthConfig":
        return cls(
            mode=os.getenv("AUTH_MODE", "disabled").strip().lower(),
            issuer=os.getenv("OIDC_ISSUER", "").rstrip("/"),
            audience=os.getenv("OIDC_AUDIENCE", ""),
            client_id=os.getenv("OIDC_CLIENT_ID", ""),
            auto_provision=os.getenv("AUTH_AUTO_PROVISION", "false").lower() in {"1", "true", "yes"},
            principal_claim=os.getenv("AUTH_PRINCIPAL_CLAIM", "sub"),
            tenant_claim=os.getenv("AUTH_TENANT_CLAIM", "tenant_id"),
            org_claim=os.getenv("AUTH_ORG_CLAIM", "org_id"),
            roles_claim=os.getenv("AUTH_ROLES_CLAIM", "roles"),
            sites_claim=os.getenv("AUTH_SITES_CLAIM", "site_ids"),
            assets_claim=os.getenv("AUTH_ASSETS_CLAIM", "asset_ids"),
            connectors_claim=os.getenv("AUTH_CONNECTORS_CLAIM", "connector_ids"),
            name_claim=os.getenv("AUTH_NAME_CLAIM", "name"),
            email_claim=os.getenv("AUTH_EMAIL_CLAIM", "email"),
            stale_jwks_seconds=int(os.getenv("OIDC_JWKS_CACHE_SECONDS", "3600")),
        )

    def public_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "enabled": self.mode != "disabled",
            "issuer": self.issuer,
            "audience": self.audience,
            "client_id": self.client_id,
            "auto_provision": self.auto_provision,
            "claims": {
                "principal": self.principal_claim,
                "tenant": self.tenant_claim,
                "organization": self.org_claim,
                "roles": self.roles_claim,
                "sites": self.sites_claim,
                "assets": self.assets_claim,
                "connectors": self.connectors_claim,
                "name": self.name_claim,
                "email": self.email_claim,
            },
        }


class JWTVerifier:
    def __init__(self, config: AuthConfig):
        self.config = config
        self._oidc_config: Dict[str, Any] = {}
        self._jwks: Dict[str, Any] = {}
        self._jwks_loaded_at = 0.0

    def _verify_hs256(self, token: str, secret: str) -> Dict[str, Any]:
        if not secret:
            raise AuthenticationError("JWT secret is not configured")
        try:
            h, p, s = token.split(".")
            header = json.loads(_b64url_decode(h))
            if header.get("alg") != "HS256":
                raise AuthenticationError("only HS256 is accepted by this verifier")
            expected = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(_b64url_encode(expected), s):
                raise AuthenticationError("invalid token signature")
            claims = json.loads(_b64url_decode(p))
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(f"malformed JWT: {exc}") from exc
        self._validate_standard_claims(claims)
        return claims

    def _validate_standard_claims(self, claims: Dict[str, Any]) -> None:
        now = int(time.time())
        if claims.get("exp") is not None and int(claims["exp"]) <= now:
            raise AuthenticationError("token expired")
        if claims.get("nbf") is not None and int(claims["nbf"]) > now:
            raise AuthenticationError("token not active yet")
        if self.config.issuer and claims.get("iss") != self.config.issuer:
            raise AuthenticationError("issuer mismatch")
        if self.config.audience:
            aud = claims.get("aud")
            allowed = aud if isinstance(aud, list) else [aud]
            if self.config.audience not in allowed:
                raise AuthenticationError("audience mismatch")

    def _load_oidc(self) -> None:
        if not self.config.issuer:
            raise AuthenticationError("OIDC_ISSUER is required")
        if self._jwks and (time.time() - self._jwks_loaded_at) < self.config.stale_jwks_seconds:
            return
        try:
            with urllib.request.urlopen(self.config.issuer + "/.well-known/openid-configuration", timeout=5) as r:
                self._oidc_config = json.loads(r.read())
            with urllib.request.urlopen(self._oidc_config["jwks_uri"], timeout=5) as r:
                self._jwks = json.loads(r.read())
            self._jwks_loaded_at = time.time()
        except Exception as exc:
            raise AuthenticationError(f"OIDC discovery/JWKS unavailable: {exc}") from exc

    def _verify_oidc(self, token: str) -> Dict[str, Any]:
        try:
            import jwt  # type: ignore
        except Exception as exc:
            raise AuthenticationError("OIDC mode requires PyJWT[crypto]; install the 'auth' extra") from exc
        self._load_oidc()
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            jwk = next((k for k in self._jwks.get("keys", []) if k.get("kid") == kid), None)
            if not jwk:
                # Key rotation: refresh once before failing closed.
                self._jwks_loaded_at = 0
                self._load_oidc()
                jwk = next((k for k in self._jwks.get("keys", []) if k.get("kid") == kid), None)
            if not jwk:
                raise AuthenticationError("signing key not found in JWKS")
            key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            opts = {"verify_aud": bool(self.config.audience)}
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[header.get("alg", "RS256")],
                audience=self.config.audience or None,
                issuer=self.config.issuer,
                options=opts,
            )
            return dict(claims)
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(f"OIDC token validation failed: {exc}") from exc

    def verify(self, token: str) -> Dict[str, Any]:
        mode = self.config.mode
        if mode == "dev":
            return self._verify_hs256(token, resolve_bootstrap_secret("AUTH_DEV_SECRET_REF", "AUTH_DEV_SECRET") or "change-me-dev-secret")
        if mode == "jwt":
            return self._verify_hs256(token, resolve_bootstrap_secret("AUTH_JWT_SECRET_REF", "AUTH_JWT_SECRET"))
        if mode == "oidc":
            return self._verify_oidc(token)
        raise AuthenticationError(f"unsupported authentication mode: {mode}")

    @staticmethod
    def issue_hs256(payload: Dict[str, Any], secret: str, ttl_seconds: int = 3600) -> str:
        now = int(time.time())
        claims = {**payload, "iat": now, "exp": now + ttl_seconds}
        h = _json_b64({"alg": "HS256", "typ": "JWT"})
        p = _json_b64(claims)
        sig = _b64url_encode(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
        return f"{h}.{p}.{sig}"


class PrincipalResolver:
    def __init__(self, store: EnterpriseIdentityStore, config: AuthConfig):
        self.store = store
        self.config = config

    def _find_existing(self, external_subject: str, email: str = "") -> Optional[Dict[str, Any]]:
        direct = self.store.principal(external_subject)
        if direct:
            return direct
        for row in self.store.principals(limit=5000):
            meta = row.get("metadata") or {}
            if str(meta.get("external_subject") or "") == external_subject:
                return row
            if email and str(meta.get("email") or "").lower() == email.lower():
                return row
        return None

    def resolve(self, claims: Dict[str, Any]) -> Dict[str, Any]:
        external_subject = str(_claim(claims, self.config.principal_claim) or "").strip()
        if not external_subject:
            raise AuthenticationError(f"token is missing principal claim '{self.config.principal_claim}'")
        email = str(_claim(claims, self.config.email_claim) or "")
        existing = self._find_existing(external_subject, email)
        if existing:
            if existing.get("status") != "active":
                raise AuthenticationError("principal is inactive")
            return existing
        if not self.config.auto_provision:
            raise AuthenticationError("authenticated identity is not provisioned as an enterprise principal")

        tenant_id = str(_claim(claims, self.config.tenant_claim) or default_tenant_id())
        if not self.store.repo.get(self.store.TENANTS, tenant_id):
            raise AuthenticationError("token tenant is not provisioned")
        roles = [r for r in _split_claim(_claim(claims, self.config.roles_claim)) if r in PERMISSIONS]
        if not roles:
            roles = ["viewer"]
        safe_pid = "OIDC-" + hashlib.sha1(f"{tenant_id}:{external_subject}".encode()).hexdigest()[:18]
        return self.store.upsert_principal({
            "principal_id": safe_pid,
            "tenant_id": tenant_id,
            "org_id": str(_claim(claims, self.config.org_claim) or ""),
            "name": str(_claim(claims, self.config.name_claim) or email or external_subject),
            "roles": roles,
            "site_ids": _split_claim(_claim(claims, self.config.sites_claim)),
            "asset_ids": _split_claim(_claim(claims, self.config.assets_claim)),
            "connector_ids": _split_claim(_claim(claims, self.config.connectors_claim)),
            "metadata": {"external_subject": external_subject, "email": email, "auth_provider": self.config.mode},
        }, actor="auth_auto_provision")


class AuthenticationService:
    AUDIT = "authentication_audit"

    def __init__(self, identity_store: EnterpriseIdentityStore):
        self.store = identity_store
        self.config = AuthConfig.from_env()
        self.verifier = JWTVerifier(self.config)
        self.resolver = PrincipalResolver(identity_store, self.config)

    def reload(self) -> Dict[str, Any]:
        self.config = AuthConfig.from_env()
        self.verifier = JWTVerifier(self.config)
        self.resolver = PrincipalResolver(self.store, self.config)
        return self.config.public_dict()

    def authenticate(self, authorization: str) -> Dict[str, Any]:
        if self.config.mode == "disabled":
            return {"authenticated": False, "mode": "disabled", "principal": None, "claims": {}}
        if not authorization or not authorization.lower().startswith("bearer "):
            raise AuthenticationError("Bearer token is required")
        token = authorization.split(None, 1)[1].strip()
        claims = self.verifier.verify(token)
        principal = self.resolver.resolve(claims)
        self._audit(principal.get("principal_id", ""), True, "authenticated", claims)
        return {"authenticated": True, "mode": self.config.mode, "principal": principal, "claims": claims}

    def _audit(self, principal_id: str, success: bool, reason: str, claims: Optional[Dict[str, Any]] = None) -> None:
        raw = f"{principal_id}:{time.time_ns()}"
        key = "AUTH-" + hashlib.sha1(raw.encode()).hexdigest()[:18]
        self.store.repo.put(self.AUDIT, key, {
            "audit_id": key, "principal_id": principal_id, "success": success, "reason": reason,
            "issuer": (claims or {}).get("iss", ""), "created_at": datetime.now(timezone.utc).isoformat(),
        })

    def audit(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.store.repo.list(self.AUDIT, limit=limit)

    def dev_token(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.config.mode != "dev":
            raise AuthenticationError("dev tokens are only available when AUTH_MODE=dev")
        ttl = max(60, min(int(payload.get("ttl_seconds", 3600)), 86400))
        tenant_id = str(payload.get("tenant_id") or default_tenant_id())
        claims = {
            "sub": str(payload.get("sub") or payload.get("principal_id") or "dev-user"),
            "name": str(payload.get("name") or "Development User"),
            "tenant_id": tenant_id,
            "roles": payload.get("roles") or ["tenant_admin"],
            "site_ids": payload.get("site_ids") or [],
            "asset_ids": payload.get("asset_ids") or [],
            "connector_ids": payload.get("connector_ids") or [],
        }
        token = self.verifier.issue_hs256(claims, resolve_bootstrap_secret("AUTH_DEV_SECRET_REF", "AUTH_DEV_SECRET") or "change-me-dev-secret", ttl)
        return {"access_token": token, "token_type": "Bearer", "expires_in": ttl, "claims": claims}

    def health(self) -> Dict[str, Any]:
        return {
            **self.config.public_dict(),
            "audit_records": len(self.audit(limit=5000)),
            "provider": "builtin" if self.config.mode in {"disabled", "dev", "jwt"} else "oidc",
        }
