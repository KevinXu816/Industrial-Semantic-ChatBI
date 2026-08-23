#!/usr/bin/env bash
set -euo pipefail
MODE="${1:-local}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
QS="$ROOT/deploy/quickstart"
ENV_FILE="$QS/.env.production"
SECRETS="$QS/runtime-secrets"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "缺少命令: $1" >&2; exit 1; }; }
need docker
need curl
need python3
if ! docker compose version >/dev/null 2>&1; then echo "需要 Docker Compose v2" >&2; exit 1; fi
mkdir -p "$SECRETS"; chmod 700 "$SECRETS"
rand(){ python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(36))
PY
}
if [ ! -f "$ENV_FILE" ]; then
  DBPASS="$(rand)"; JWTSECRET="$(rand)"
  printf '%s' "$JWTSECRET" > "$SECRETS/auth_jwt_secret"; chmod 600 "$SECRETS/auth_jwt_secret"
  cat > "$ENV_FILE" <<EOF
POSTGRES_DB=industrial_semantic
POSTGRES_USER=industrial_semantic
POSTGRES_PASSWORD=$DBPASS
DEFAULT_TENANT_ID=default
INSTALL_EXTRAS=postgres,governance,auth,qdrant
EXECUTION_MODE=${EXECUTION_MODE:-mock}
KNOWLEDGE_BACKEND=${KNOWLEDGE_BACKEND:-local}
DORIS_HOST=${DORIS_HOST:-}
DORIS_PORT=${DORIS_PORT:-9030}
DORIS_USER=${DORIS_USER:-root}
DORIS_DATABASE=${DORIS_DATABASE:-industrial_ai}
DORIS_PASSWORD_REF=${DORIS_PASSWORD_REF:-}
EOF
  chmod 600 "$ENV_FILE"
fi

set_env(){
  local key="$1" value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PYENV'
from pathlib import Path
import sys
p=Path(sys.argv[1]); key=sys.argv[2]; value=sys.argv[3]
rows=p.read_text().splitlines() if p.exists() else []
out=[]; found=False
for row in rows:
    if row.startswith(key+'='):
        if not found: out.append(f'{key}={value}'); found=True
    else: out.append(row)
if not found: out.append(f'{key}={value}')
p.write_text('\n'.join(out)+'\n')
PYENV
}

case "$MODE" in
  local)
    set_env PLATFORM_DOMAIN ":80"
    set_env TLS_DIRECTIVE ""
    set_env HTTP_PORT "${HTTP_PORT:-8080}"
    set_env HTTPS_PORT "${HTTPS_PORT:-8443}"
    BASE_URL="http://127.0.0.1:${HTTP_PORT:-8080}"
    ;;
  saas)
    : "${DOMAIN:?SaaS 模式请先设置 DOMAIN，例如 DOMAIN=ai.example.com}"
    set_env PLATFORM_DOMAIN "$DOMAIN"
    set_env TLS_DIRECTIVE ""
    set_env HTTP_PORT "${HTTP_PORT:-80}"
    set_env HTTPS_PORT "${HTTPS_PORT:-443}"
    BASE_URL="https://$DOMAIN"
    ;;
  *) echo "用法: $0 local | saas" >&2; exit 2;;
esac

cd "$QS"
docker compose --env-file "$ENV_FILE" -f docker-compose.production.yml up -d --build

echo "等待系统 Readiness..."
for i in $(seq 1 90); do
  if curl -fsS "$BASE_URL/health/ready" >/dev/null 2>&1; then break; fi
  sleep 2
  if [ "$i" = 90 ]; then docker compose --env-file "$ENV_FILE" -f docker-compose.production.yml ps; exit 1; fi
done

JWTSECRET="$(cat "$SECRETS/auth_jwt_secret")"
TOKEN="$(JWTSECRET="$JWTSECRET" python3 - <<'PY'
import os, json, base64, hmac, hashlib, time
enc=lambda b: base64.urlsafe_b64encode(b).rstrip(b'=').decode()
header=enc(json.dumps({'alg':'HS256','typ':'JWT'},separators=(',',':')).encode())
now=int(time.time())
claims={'sub':'bootstrap-admin','tenant_id':'default','roles':['tenant_admin'],'name':'Bootstrap Admin','iat':now,'exp':now+86400}
payload=enc(json.dumps(claims,separators=(',',':')).encode())
sig=enc(hmac.new(os.environ['JWTSECRET'].encode(),f'{header}.{payload}'.encode(),hashlib.sha256).digest())
print(f'{header}.{payload}.{sig}')
PY
)"
printf '%s\n' "$TOKEN" > "$QS/bootstrap-admin.token"; chmod 600 "$QS/bootstrap-admin.token"

echo
echo "============================================"
echo "工业语义智能平台 V4.9 已部署完成"
echo "访问地址: $BASE_URL"
echo "管理员快速登录: ${BASE_URL}/#bootstrap_token=${TOKEN}"
echo "临时管理员 Token 有效期 24 小时，文件: $QS/bootstrap-admin.token"
echo "生产配置: $ENV_FILE"
if grep -q '^EXECUTION_MODE=mock' "$ENV_FILE"; then
  echo "提示: 当前 Query Execution=mock；ChatBI 查询真实企业数仓前，请配置 Doris 后重新执行本脚本。"
fi
echo "============================================"
