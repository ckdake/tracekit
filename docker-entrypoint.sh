#!/usr/bin/env bash
set -euo pipefail

# docker-entrypoint.sh
# If CONFIG_PATH is provided and points to an existing file, copy it to /app/tracekit_config.json
# Then exec the provided command (default: python app/main.py)

if [[ -n "${CONFIG_PATH:-}" ]]; then
  if [[ -f "$CONFIG_PATH" ]]; then
    echo "🔧 Using config from $CONFIG_PATH -> /app/tracekit_config.json"
    cp "$CONFIG_PATH" /app/tracekit_config.json
  else
    echo "⚠️ CONFIG_PATH set but file not found: $CONFIG_PATH"
  fi
fi

exec "$@"
