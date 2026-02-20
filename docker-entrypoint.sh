#!/usr/bin/env bash
set -euo pipefail

# Only run migrations when explicitly requested (web container only).
# Worker and beat wait for a healthy web container instead.
if [[ "${RUN_MIGRATIONS:-false}" == "true" ]]; then
  python -m tracekit migrate
fi

exec "$@"
