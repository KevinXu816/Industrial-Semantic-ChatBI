#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

printf '\n[1/6] health\n'
curl -fsS "$BASE_URL/health"; echo
printf '\n[2/6] bootstrap scenario\n'
curl -fsS -X POST "$BASE_URL/pilot/scenarios/air-compressor-energy-maintenance/bootstrap"; echo
printf '\n[3/6] prepare customer-data bindings (draft)\n'
curl -fsS -X POST "$BASE_URL/pilot/onboarding/prepare" -H 'Content-Type: application/json' -d '{"site_id":"F01"}'; echo
printf '\n[4/6] run synthetic end-to-end demo\n'
curl -fsS -X POST "$BASE_URL/pilot/run-demo"; echo
printf '\n[5/6] readiness + onboarding status\n'
curl -fsS "$BASE_URL/pilot/readiness"; echo
curl -fsS "$BASE_URL/pilot/onboarding/status"; echo
printf '\n[6/6] acceptance report (expected NO_GO until customer bindings are reviewed/approved and KPIs are measured)\n'
curl -fsS "$BASE_URL/pilot/report"; echo
