#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/deploy/quickstart"
docker compose --env-file .env.production -f docker-compose.production.yml down "$@"
