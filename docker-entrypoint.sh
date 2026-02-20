#!/usr/bin/env bash
set -euo pipefail

# Bootstrap / migrate database schema before starting the main process.
# On Postgres the migrate command retries until the DB container is ready.
# Set SKIP_MIGRATE=1 for containers that don't need a DB connection (e.g. beat).
if [[ -z "${SKIP_MIGRATE:-}" ]]; then
  python -m tracekit migrate
fi

exec "$@"
