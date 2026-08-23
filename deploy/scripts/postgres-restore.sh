#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
DUMP="${1:?usage: postgres-restore.sh <dump-file>}"
pg_restore --clean --if-exists --no-owner --no-acl --dbname "$DATABASE_URL" "$DUMP"
