#!/usr/bin/env bash
set -euo pipefail

# Bootstrap / migrate database schema before starting the main process.
# On Postgres the migrate command retries until the DB container is ready.
python -m tracekit migrate

exec "$@"
