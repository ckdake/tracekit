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

## Production vs local dev — Flask app runtime differences

The Flask app runs differently in the two environments. Changes that affect observability or logging must account for both.

| | Local dev (`python main.py`) | Production (gunicorn) |
|---|---|---|
| Entry point | `if __name__ == "__main__": app.run(...)` | `gunicorn ... main:app` |
| Process model | Single process, threaded | Multi-process pre-fork (`--workers N`) |
| Config file | n/a | `app/gunicorn.conf.py` |
| Sentry init | Module-level `sentry_sdk.init()` in `main.py` | Same, **plus** re-init in `post_fork` hook (gunicorn forks from master after import; threads don't survive `fork()`, killing Sentry's background transport) |
| Request logging | `logging.basicConfig(format="%(message)s")` takes effect | `basicConfig` is a no-op (gunicorn already owns root logger); `post_fork` resets handler formatters to `%(message)s` so JSON lines are clean |
| Access log | n/a | `accesslog = None` in `gunicorn.conf.py` — `_log_request` in `main.py` already emits structured JSON per request |

### Key rules for this gap

- **DB migrations run exactly once per boot**, in the gunicorn master process via the `on_starting` hook in `app/gunicorn.conf.py`, before any worker is forked. `preload_app = True` ensures workers inherit `_db_initialized = True` via fork and never re-run migrations. In request handlers, use `_ensure_db_connected()` (opens a connection) — never `_init_db()` (migrates).
- **Sentry tracing only works in production if `sentry_sdk.init()` is called inside `post_fork`** in `app/gunicorn.conf.py`. Without it, transactions are enqueued but never flushed (dead transport thread). Errors may still surface via a sync fallback, so error-only Sentry in prod with no traces is a symptom of this bug.
- **`traces_sampler` in `gunicorn.conf.py` must filter by `transaction_context["name"]`**, not `wsgi_environ["PATH_INFO"]`. Under gunicorn, `wsgi_environ` is not populated in the sampling context, so the `PATH_INFO` check silently falls through and health checks get sampled. The Flask dev server does populate `wsgi_environ`, so `main.py`'s sampler can use `PATH_INFO` and works correctly there.
- **Never rely on `logging.basicConfig()` taking effect under gunicorn.** Configure log formatting in `post_fork` instead.
- **Do not add `--access-logfile` to the gunicorn CMD.** `_log_request` in `main.py` is the single source of request logs.
- When adding new gunicorn CLI flags, prefer putting them in `app/gunicorn.conf.py` as Python assignments (e.g. `workers = 2`) so the config stays in one place.

---

## Authentication

Auth is enforced globally in `app/main.py::_setup_request()` — **do not add `@login_required` to individual routes**. In route handlers and templates, access the current user via `current_user` from `flask_login` (not `g.current_user`). The `User` model lives in `app/models/user.py` and is intentionally absent from `tracekit/database.py::get_all_models()`.

---

## API design conventions

- **Collection vs item**: follow the REST pattern — `/api/calendar` is the collection, `/api/calendar/YYYY-MM` is the item. New bulk endpoints go on the collection URL with query params, not a separate path.
- **Multi-resource responses**: return a **dict keyed by the resource identifier** (e.g. `{"2024-01": {...}, "2024-02": {...}}`), not an array. Dicts are easier to look up by key and more flexible for callers.
- **Query param naming**: use `from` / `to` for inclusive date/month ranges.
- **Don't allow open ended**: recommend pagination, or a hard limit in the query depending on the scenario.

---

## Code style

- **Formatter / linter**: Ruff (configured in `ruff.toml`). Pre-commit runs it automatically.
- **Type hints**: used throughout; run `mypy tracekit/` to check.
- **Imports**: lazy imports inside functions for heavy optional dependencies (keeps startup fast and allows test mocking).
- **No backwards-compat shims**: if something is unused, delete it.

---

## Key Rules For Agents

- **Kaizen**: After every interaction wrapps up and you see your change being the last change, include a recommendation for a single thing to add, remove, or change in this AGENTS.md file The goal of AGENTS.md is not completeness, it is correctness. Improvements to this file should
ensure the agent acts in the correct way in this project, which is usually the simpler approach.
