#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
OUT="${1:-industrial-semantic-$(date -u +%Y%m%dT%H%M%SZ).dump}"
pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" -f "$OUT"
sha256sum "$OUT" > "$OUT.sha256"
echo "$OUT"
