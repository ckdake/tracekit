# AGENTS.md

Guidance for AI coding agents (Claude Code, Copilot Workspace, etc.) working on this repository.

---

## What this project is

Tracekit aggregates fitness activity data from multiple providers (Strava, Garmin, RideWithGPS, spreadsheets, local files), correlates activities across sources, and surfaces them through a CLI and a Flask web dashboard. It does **not** modify provider data without explicit user approval.

---

## Repository layout

```
tracekit/           # Python package — all business logic lives here
  __main__.py       # CLI entry point: python -m tracekit <command>
  commands/         # One module per CLI command (thin wrappers)
  providers/        # Six provider integrations (strava, garmin, …)
  activity.py       # Central Activity ORM model
  appconfig.py      # Config load/save + token helpers
  calendar.py       # Month-grid data queries
  core.py           # Tracekit class — provider orchestration
  database.py       # Schema migrations
  db.py             # SQLite / PostgreSQL connection
  notification.py   # In-app notification model
  provider_status.py# Per-provider last-op status + rate-limit tracking
  provider_sync.py  # Which provider/months have been pulled
  stats.py          # Activity count / recency queries
  sync.py           # Correlation, diff computation, change application
  utils.py          # Shared utilities (sort_providers, …)
  worker.py         # Celery task definitions (production async)

app/                # Flask web dashboard — presentation layer only
  main.py           # App factory + blueprint registration
  db_init.py        # Flask-context DB initialisation
  calendar_data.py  # Thin shims → tracekit.calendar
  helpers.py        # Thin shims → tracekit.stats / tracekit.utils
  routes/           # HTTP handlers (pages, API, auth, month, notifications)
  templates/        # Jinja2 HTML templates
  static/           # CSS, JS, logos
  tests/            # App-level tests (run from app/ directory)

tests/              # Package-level tests (run from repo root)
```

---

## The core rule: package vs app

> **Business logic belongs in `tracekit/`. The app is HTTP glue.**

| Belongs in `tracekit/` | Belongs in `app/` |
|------------------------|-------------------|
| Data queries and aggregation | Flask route handlers |
| Activity correlation / sync | HTML template rendering |
| Provider status tracking | Celery task enqueueing |
| Config load / save / token helpers | `_init_db()` Flask-context setup |
| CLI-renderable output data | Browser auth redirect flows |

When you find yourself writing a data-processing function inside an `app/routes/` file, it should live in the package instead. The app then calls it.

### Concrete examples

- `tracekit/sync.py::build_comparison_rows()` — computes the activity comparison table; both the CLI ANSI renderer and the web JSON API call it.
- `tracekit/calendar.py` — month-grid queries; `app/calendar_data.py` is a thin shim that adds the Flask `_init_db()` guard and delegates.
- `tracekit/stats.py` — activity counts and recency; `app/helpers.py` wraps with the same guard.
- `tracekit/appconfig.py::save_strava_tokens()` / `save_garmin_tokens()` — token persistence used by both CLI and web auth routes.

---

## Adding a CLI command

1. Create `tracekit/commands/<name>.py` with a `run(args=None)` function.
2. Register it in `tracekit/__main__.py`:
   - Add a `subparsers.add_parser(...)` entry with any arguments.
   - Add an `elif args.command == "<name>":` branch that imports and calls `run`.
   - Add it to the `help` command's printed command list.
3. Commands must be **thin**: orchestrate via `Tracekit` and package functions; do not contain data logic themselves.

```python
# tracekit/commands/mycommand.py
from tracekit.core import tracekit as tracekit_class

def run(args=None) -> None:
    with tracekit_class() as tk:
        # call package functions, print results
        ...
```

---

## Adding a provider

1. Create `tracekit/providers/<name>/` with `<name>_provider.py` and `<name>_activity.py`.
2. Subclass `FitnessProvider` (`base_provider.py`) and `BaseProviderActivity` (`base_provider_activity.py`).
3. Add the provider to `tracekit/providers/__init__.py` exports.
4. Wire it into `tracekit/core.py` (`Tracekit` class) so it is lazily instantiated from config.
5. Add it to the provider maps in `tracekit/calendar.py` and `tracekit/stats.py`.
6. Add default config keys to `DEFAULT_CONFIG` in `tracekit/appconfig.py`.

---

## Database

- **Default**: SQLite (`metadata.sqlite3`, path from `METADATA_DB` env var).
- **Production**: PostgreSQL via `DATABASE_URL` env var.
- Schema changes go in `tracekit/database.py` as idempotent migrations (safe to run on every boot).
- All models must appear in `get_all_models()` in `database.py` so migrations and the stats helper pick them up.

---

## Configuration

Config is stored in the `appconfig` DB table (key → JSON value). `tracekit_config.json` in the repo root is an optional seed/override file that is synced into the DB on each boot; the DB is always the source of truth at runtime.

Key helpers in `tracekit/appconfig.py`:
- `load_config()` — returns the merged config dict.
- `save_config(config)` — upserts all top-level keys.
- `save_strava_tokens(token_dict)` — saves OAuth tokens for Strava.
- `save_garmin_tokens(email, garth_tokens)` — saves Garmin tokens.

---

## Development flow

```bash
# Install (editable, with dev dependencies)
pip install -e .[dev]
pre-commit install

# Run the full test suite
python -m pytest --cov=tracekit --cov-report=term-missing -v

# Run app tests specifically
python -m pytest app/tests/ -v

# Lint / format (pre-commit does this automatically on commit)
pre-commit run --all-files

# Run the web dashboard locally
./scripts/run-dev.sh          # → http://localhost:5000

# Exercise the CLI
python -m tracekit help
python -m tracekit status
python -m tracekit calendar --months 6
python -m tracekit sync-month 2025-11
```

---

## Testing conventions

- **Package tests** live in `tests/` and mirror the `tracekit/` structure.
- **App tests** live in `app/tests/` and are run with `pytest` from the repo root or from `app/`.
- Use `unittest.mock.patch` to mock package imports in app tests; avoid mocking `builtins.__import__`.
- Heavy provider dependencies (stravalib, garminconnect) are import-guarded with `try/except ImportError` so tests can run without optional packages.
- Tests must pass and `pre-commit run --all-files` must be clean before merging.

---

## Code style

- **Formatter / linter**: Ruff (configured in `ruff.toml`). Pre-commit runs it automatically.
- **Type hints**: used throughout; run `mypy tracekit/` to check.
- **Imports**: lazy imports inside functions for heavy optional dependencies (keeps startup fast and allows test mocking).
- **No backwards-compat shims**: if something is unused, delete it.
