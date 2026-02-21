"""Simple Flask web application to view tracekit configuration and database status."""

import calendar as _cal
import time
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytz
from flask import Flask, jsonify, render_template, request

# Get the directory where this script is located
app_dir = Path(__file__).parent
app = Flask(__name__, template_folder=str(app_dir / "templates"), static_folder=str(app_dir / "static"))

# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

_db_initialized = False


def _init_db() -> bool:
    """Configure the DB and ensure all tables exist.

    Resolution order (no config file needed):
      1. DATABASE_URL env var  → PostgreSQL
      2. METADATA_DB env var   → SQLite at that path
      3. Default               → metadata.sqlite3 in cwd
    """
    global _db_initialized
    if not _db_initialized:
        try:
            from tracekit.appconfig import get_db_path_from_env
            from tracekit.database import get_all_models, migrate_tables
            from tracekit.db import configure_db

            configure_db(get_db_path_from_env())
            migrate_tables(get_all_models())
            _db_initialized = True
        except Exception as e:
            print(f"DB init failed: {e}")
            return False
    return True


def load_tracekit_config() -> dict[str, Any]:
    """Load tracekit config — always returns a valid dict.

    Priority: DB rows → JSON file (migrated in on first call) → built-in defaults.
    Never returns an error dict; the app always has a working config.
    """
    _init_db()
    from tracekit.appconfig import load_config

    return load_config()


def get_current_date_in_timezone(config: dict[str, Any]) -> date:
    """Get the current date in the configured timezone."""
    try:
        timezone_str = config.get("home_timezone", "UTC")
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        return now.date()
    except Exception:
        # Fallback to UTC if timezone is invalid
        return datetime.now(pytz.UTC).date()


def get_database_info(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get basic information about the configured database."""
    if not _init_db():
        return {"error": "Database not available"}

    try:
        from tracekit.database import get_all_models
        from tracekit.db import get_db

        db = get_db()
        db.connect(reuse_if_open=True)

        models = get_all_models()
        table_counts = {}
        for model in models:
            table_name = model._meta.table_name
            table_counts[table_name] = model.select().count()

        return {
            "tables": table_counts,
            "total_tables": len(table_counts),
        }
    except Exception as e:
        return {"error": f"Database error: {e}"}


def get_most_recent_activity(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the timestamp and timezone-formatted datetime of the most recent activity."""
    if not _init_db():
        return {"error": "Database not available"}

    try:
        from tracekit.providers.file.file_activity import FileActivity
        from tracekit.providers.garmin.garmin_activity import GarminActivity
        from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
        from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
        from tracekit.providers.strava.strava_activity import StravaActivity
        from tracekit.providers.stravajson.stravajson_activity import StravaJsonActivity

        models = [
            StravaActivity,
            GarminActivity,
            RideWithGPSActivity,
            SpreadsheetActivity,
            FileActivity,
            StravaJsonActivity,
        ]

        max_ts: int | None = None
        for model in models:
            try:
                row = (
                    model.select(model.start_time)
                    .where(model.start_time.is_null(False))
                    .order_by(model.start_time.desc())
                    .first()
                )
                if row and row.start_time:
                    ts = int(row.start_time)
                    if max_ts is None or ts > max_ts:
                        max_ts = ts
            except Exception:
                pass

        if max_ts is None:
            return {"timestamp": None, "formatted": None}

        tz_str = (config or {}).get("home_timezone", "UTC")
        try:
            tz = pytz.timezone(tz_str)
        except Exception:
            tz = pytz.UTC

        dt = datetime.fromtimestamp(max_ts, tz=UTC).astimezone(tz)
        formatted = dt.strftime("%-d %b %Y, %H:%M %Z")
        return {"timestamp": max_ts, "formatted": formatted}
    except Exception as e:
        return {"error": f"Database error: {e}"}


def get_sync_calendar_data(config: dict[str, Any]) -> dict[str, Any]:
    """Compatibility shim — returns full calendar data (used by tests).

    In production the page uses get_calendar_shell + get_single_month_data
    so that each month loads independently.  This function still works for
    the test suite which imports it directly.
    """
    shell = get_calendar_shell(config)
    if shell.get("error"):
        return shell

    months_with_data = []
    for stub in shell["months"]:
        month_data = get_single_month_data(config, stub["year_month"])
        if month_data.get("error"):
            months_with_data.append(stub)
        else:
            months_with_data.append(month_data)

    return {
        "months": months_with_data,
        "providers": shell["providers"],
        "date_range": shell["date_range"],
        "total_months": shell["total_months"],
    }


def get_calendar_shell(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return month stubs and providers list — no activity table scans."""
    if not _init_db():
        return {"error": "Database not available"}

    try:
        from tracekit.db import get_db
        from tracekit.provider_sync import ProviderSync

        db = get_db()
        db.connect(reuse_if_open=True)

        rows = ProviderSync.select(ProviderSync.year_month, ProviderSync.provider).order_by(
            ProviderSync.year_month, ProviderSync.provider
        )
        records = [(r.year_month, r.provider) for r in rows]

        if not records:
            return {"months": [], "providers": [], "date_range": (None, None), "total_months": 0}

        year_months_all = [r[0] for r in records]
        date_range = (min(year_months_all), max(year_months_all))
        providers = sorted({r[1] for r in records})

        start_year, start_month = map(int, date_range[0].split("-"))
        end_year, end_month = map(int, date_range[1].split("-"))

        current_date = get_current_date_in_timezone(config)
        current_ym = f"{current_date.year:04d}-{current_date.month:02d}"
        if current_ym > date_range[1]:
            end_year, end_month = current_date.year, current_date.month

        all_months = []
        year, month = start_year, start_month
        while year < end_year or (year == end_year and month <= end_month):
            ym = f"{year:04d}-{month:02d}"
            all_months.append(
                {
                    "year_month": ym,
                    "year": year,
                    "month": month,
                    "month_name": datetime(year, month, 1).strftime("%B"),
                }
            )
            month += 1
            if month > 12:
                month = 1
                year += 1

        return {
            "months": all_months,
            "providers": providers,
            "date_range": date_range,
            "total_months": len(all_months),
        }
    except Exception as e:
        return {"error": f"Database error: {e}"}


def get_single_month_data(config: dict[str, Any] | None, year_month: str) -> dict[str, Any]:
    """Return sync status and activity counts for one month.

    Activity queries are scoped to the month's timestamp range so this is
    fast even for large databases.
    """
    if not _init_db():
        return {"error": "Database not available"}

    try:
        from tracekit.db import get_db
        from tracekit.provider_sync import ProviderSync
        from tracekit.providers.file.file_activity import FileActivity
        from tracekit.providers.garmin.garmin_activity import GarminActivity
        from tracekit.providers.ridewithgps.ridewithgps_activity import RideWithGPSActivity
        from tracekit.providers.spreadsheet.spreadsheet_activity import SpreadsheetActivity
        from tracekit.providers.strava.strava_activity import StravaActivity
        from tracekit.providers.stravajson.stravajson_activity import StravaJsonActivity

        db = get_db()
        db.connect(reuse_if_open=True)

        synced_rows = ProviderSync.select(ProviderSync.provider).where(ProviderSync.year_month == year_month)
        synced_providers = [r.provider for r in synced_rows]

        all_rows = ProviderSync.select(ProviderSync.provider).distinct()
        providers = sorted({r.provider for r in all_rows})

        provider_status = {p: p in synced_providers for p in providers}

        year_int, month_int = map(int, year_month.split("-"))
        start_ts = int(datetime(year_int, month_int, 1, tzinfo=UTC).timestamp())
        last_day = _cal.monthrange(year_int, month_int)[1]
        end_ts = int(datetime(year_int, month_int, last_day, 23, 59, 59, tzinfo=UTC).timestamp())

        provider_models = {
            "strava": StravaActivity,
            "garmin": GarminActivity,
            "ridewithgps": RideWithGPSActivity,
            "spreadsheet": SpreadsheetActivity,
            "file": FileActivity,
            "stravajson": StravaJsonActivity,
        }

        activity_counts: dict[str, int] = {}
        for provider, model in provider_models.items():
            try:
                count = (
                    model.select()
                    .where(
                        model.start_time.is_null(False) & (model.start_time >= start_ts) & (model.start_time <= end_ts)
                    )
                    .count()
                )
                if count > 0:
                    activity_counts[provider] = count
            except Exception as e:
                print(f"Error counting {provider} activities for {year_month}: {e}")

        total_activities = sum(activity_counts.values())

        return {
            "year_month": year_month,
            "year": year_int,
            "month": month_int,
            "month_name": datetime(year_int, month_int, 1).strftime("%B"),
            "providers": providers,
            "synced_providers": synced_providers,
            "provider_status": provider_status,
            "activity_counts": activity_counts,
            "total_activities": total_activities,
        }
    except Exception as e:
        return {"error": f"Database error: {e}"}


def sort_providers(providers: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Sort providers by priority (lowest first) with disabled providers at the end."""
    enabled: list[tuple[int, str, dict[str, Any]]] = []
    disabled: list[tuple[str, dict[str, Any]]] = []
    for name, cfg in providers.items():
        if cfg.get("enabled", False):
            enabled.append((cfg.get("priority", 999), name, cfg))
        else:
            disabled.append((name, cfg))
    enabled.sort(key=lambda x: x[0])
    result = [(name, cfg) for _, name, cfg in enabled]
    result.extend(disabled)
    return result


@app.route("/settings")
def settings():
    """Settings page — edit providers, timezone and debug flag."""
    config = load_tracekit_config()
    import pytz

    timezones = pytz.common_timezones
    return render_template("settings.html", config=config, timezones=timezones, page_name="Settings")


@app.route("/calendar")
def calendar():
    """Redirect legacy /calendar URL to /."""
    from flask import redirect

    return redirect("/", code=301)


@app.route("/")
def index():
    """Main status/calendar page — last 12 months, most recent first."""
    config = load_tracekit_config()

    current_date = get_current_date_in_timezone(config)
    current_month = f"{current_date.year:04d}-{current_date.month:02d}"

    # Build last 12 months, most recent first
    months = []
    year, month = current_date.year, current_date.month
    for _ in range(12):
        ym = f"{year:04d}-{month:02d}"
        months.append(
            {
                "year_month": ym,
                "year": year,
                "month": month,
                "month_name": datetime(year, month, 1).strftime("%B"),
            }
        )
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    return render_template(
        "index.html",
        config=config,
        initial_months=months,
        current_month=current_month,
        page_name="Status",
    )


@app.route("/api/config", methods=["GET"])
def api_config():
    """Return the current configuration as JSON."""
    return jsonify(load_tracekit_config())


@app.route("/api/config", methods=["PUT"])
def api_config_save():
    """Persist a new configuration to the DB."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400
    _init_db()
    from tracekit.appconfig import save_config

    save_config(data)
    return jsonify({"status": "saved"})


@app.route("/api/database")
def api_database():
    """API endpoint for database information."""
    return jsonify(get_database_info())


@app.route("/api/recent-activity")
def api_recent_activity():
    """Return the most recent activity timestamp and formatted datetime."""
    config = load_tracekit_config()
    return jsonify(get_most_recent_activity(config))


@app.route("/api/calendar/<year_month>")
def api_calendar_month(year_month: str):
    """Return sync status and activity counts for a single month."""
    import re

    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400
    config = load_tracekit_config()
    return jsonify(get_single_month_data(config, year_month))


@app.route("/api/sync/<year_month>", methods=["POST"])
def sync_month(year_month: str):
    """Enqueue a pull job for the given YYYY-MM month."""
    import re

    if not re.fullmatch(r"\d{4}-\d{2}", year_month):
        return jsonify({"error": "Invalid month format, expected YYYY-MM"}), 400
    try:
        from tracekit.notification import create_notification
        from tracekit.worker import pull_month

        create_notification(f"Pull scheduled for {year_month}", category="info")
        task = pull_month.delay(year_month)
        return jsonify({"task_id": task.id, "year_month": year_month, "status": "queued"})
    except Exception as e:
        return jsonify({"error": f"Failed to enqueue task: {e}"}), 503


@app.route("/api/sync/status/<task_id>")
def sync_status(task_id: str):
    """Return the current state of a Celery task."""
    try:
        from celery.result import AsyncResult

        from tracekit.worker import celery_app

        result = AsyncResult(task_id, app=celery_app)
        info = None
        if result.failed():
            info = str(result.info)
        return jsonify({"task_id": task_id, "state": result.state, "info": info})
    except Exception as e:
        return jsonify({"error": str(e)}), 503


# ---------------------------------------------------------------------------
# Notifications API
# ---------------------------------------------------------------------------


def _get_notifications_list() -> list[dict]:
    """Return all notifications ordered newest-first."""
    if not _init_db():
        return []
    try:
        from tracekit.db import get_db
        from tracekit.notification import Notification

        get_db().connect(reuse_if_open=True)
        rows = Notification.select().order_by(Notification.created.desc())
        return [r.to_dict() for r in rows]
    except Exception as e:
        print(f"notifications list error: {e}")
        return []


@app.route("/api/notifications")
def api_notifications():
    """Return all notifications ordered newest-first."""
    return jsonify(_get_notifications_list())


@app.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def api_notification_read(notification_id: int):
    """Mark a single notification as read."""
    if not _init_db():
        return jsonify({"error": "Database not available"}), 503
    try:
        from tracekit.db import get_db
        from tracekit.notification import Notification

        get_db().connect(reuse_if_open=True)
        n = Notification.get_by_id(notification_id)
        n.read = True
        n.save()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/notifications/read-all", methods=["POST"])
def api_notifications_read_all():
    """Mark all notifications as read."""
    if not _init_db():
        return jsonify({"error": "Database not available"}), 503
    try:
        from tracekit.db import get_db
        from tracekit.notification import Notification

        get_db().connect(reuse_if_open=True)
        Notification.update(read=True).where(Notification.read == False).execute()  # noqa: E712
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/notifications/<int:notification_id>", methods=["DELETE"])
def api_notification_delete(notification_id: int):
    """Delete a single notification."""
    if not _init_db():
        return jsonify({"error": "Database not available"}), 503
    try:
        from tracekit.db import get_db
        from tracekit.notification import Notification

        get_db().connect(reuse_if_open=True)
        n = Notification.get_by_id(notification_id)
        n.delete_instance()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 404


# ---------------------------------------------------------------------------
# Garmin auth — pending MFA sessions (in-memory, single-process only)
# ---------------------------------------------------------------------------

# Maps session_id -> (Garmin instance, client_state dict, email, expiry timestamp)
_pending_garmin_sessions: dict[str, tuple[Any, Any, str, float]] = {}
_GARMIN_SESSION_TTL = 600  # 10 minutes


def _cleanup_garmin_sessions() -> None:
    now = time.time()
    expired = [k for k, (*_, exp) in _pending_garmin_sessions.items() if now > exp]
    for k in expired:
        del _pending_garmin_sessions[k]


def _save_garmin_tokens(email: str, garth_tokens: str) -> None:
    """Persist Garmin email + garth tokens to the config store."""
    _init_db()
    from tracekit.appconfig import load_config, save_config

    config = load_config()
    providers = config.get("providers", {})
    garmin_cfg = providers.get("garmin", {}).copy()
    garmin_cfg["email"] = email
    garmin_cfg["garth_tokens"] = garth_tokens
    providers["garmin"] = garmin_cfg
    save_config({**config, "providers": providers})


@app.route("/api/auth/garmin", methods=["POST"])
def api_auth_garmin():
    """Start Garmin authentication. Returns needs_mfa + session_id or ok."""
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    try:
        import garminconnect
        from garminconnect import (
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
            GarminConnectTooManyRequestsError,
        )
    except ImportError:
        return jsonify({"error": "garminconnect library not installed"}), 500

    _cleanup_garmin_sessions()

    try:
        garmin = garminconnect.Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
        result, client_state = garmin.login()

        if result == "needs_mfa":
            session_id = str(uuid.uuid4())
            _pending_garmin_sessions[session_id] = (
                garmin,
                client_state,
                email,
                time.time() + _GARMIN_SESSION_TTL,
            )
            return jsonify({"status": "needs_mfa", "session_id": session_id})

        # No MFA required — tokens are ready
        garth_tokens = garmin.garth.dumps()
        _save_garmin_tokens(email, garth_tokens)
        return jsonify({"status": "ok", "full_name": garmin.get_full_name()})

    except GarminConnectAuthenticationError as e:
        return jsonify({"error": f"Authentication failed: {e}"}), 401
    except GarminConnectTooManyRequestsError as e:
        return jsonify({"error": f"Rate limit exceeded, please wait and try again: {e}"}), 429
    except GarminConnectConnectionError as e:
        return jsonify({"error": f"Connection error: {e}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/auth/garmin/mfa", methods=["POST"])
def api_auth_garmin_mfa():
    """Complete Garmin MFA step. Accepts session_id + mfa_code."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    mfa_code = data.get("mfa_code", "").strip()
    if not session_id or not mfa_code:
        return jsonify({"error": "session_id and mfa_code are required"}), 400

    entry = _pending_garmin_sessions.get(session_id)
    if not entry:
        return jsonify({"error": "Session not found or expired. Please start authentication again."}), 404

    garmin, client_state, email, expires_at = entry
    if time.time() > expires_at:
        del _pending_garmin_sessions[session_id]
        return jsonify({"error": "Session expired. Please start authentication again."}), 410

    try:
        from garminconnect import (
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
        )
    except ImportError:
        return jsonify({"error": "garminconnect library not installed"}), 500

    try:
        garmin.resume_login(client_state, mfa_code)
        del _pending_garmin_sessions[session_id]

        garth_tokens = garmin.garth.dumps()
        _save_garmin_tokens(email, garth_tokens)
        return jsonify({"status": "ok", "full_name": garmin.get_full_name()})

    except GarminConnectAuthenticationError as e:
        return jsonify({"error": f"MFA verification failed: {e}"}), 401
    except GarminConnectConnectionError as e:
        return jsonify({"error": f"Connection error: {e}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Strava OAuth endpoints
# ---------------------------------------------------------------------------


def _strava_callback_page(success: bool, message: str) -> str:
    """Return an HTML page that notifies the opener then closes itself."""
    status = "ok" if success else "error"
    icon = "\u2713" if success else "\u2717"
    safe_msg = message.replace("'", "\\'").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html><head><title>Strava Auth</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px;color:#2c3e50;">
  <p style="font-size:1.2rem;">{icon} {safe_msg}</p>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{stravaAuth:true,status:'{status}',message:'{safe_msg}'}}, '*');
      window.close();
    }}
  </script>
</body></html>"""


@app.route("/api/auth/strava/authorize")
def api_auth_strava_authorize():
    """Redirect the browser to Strava's OAuth authorization page."""
    from flask import redirect as flask_redirect

    _init_db()
    from tracekit.appconfig import load_config

    config = load_config()
    strava_cfg = config.get("providers", {}).get("strava", {})
    client_id = strava_cfg.get("client_id", "").strip()
    client_secret = strava_cfg.get("client_secret", "").strip()

    if not client_id or not client_secret:
        return (
            "<h3>Configuration error</h3>"
            "<p>Strava <strong>client id</strong> and <strong>client secret</strong> "
            "must be saved in Settings before authenticating.</p>",
            400,
        )

    try:
        from stravalib.client import Client

        client = Client()
        redirect_uri = f"{request.scheme}://{request.host}/api/auth/strava/callback"
        authorize_url = client.authorization_url(
            client_id=int(client_id),
            redirect_uri=redirect_uri,
            scope=["activity:read_all", "activity:write", "profile:read_all", "profile:write"],
        )
        return flask_redirect(str(authorize_url))
    except Exception as e:
        return f"<h3>Error</h3><p>{e}</p>", 500


@app.route("/api/auth/strava/callback")
def api_auth_strava_callback():
    """Handle Strava OAuth callback — exchange code for tokens and save."""
    error = request.args.get("error")
    if error:
        return _strava_callback_page(False, f"Strava authorization denied: {error}")

    code = request.args.get("code")
    if not code:
        return _strava_callback_page(False, "No authorization code received from Strava.")

    try:
        _init_db()
        from tracekit.appconfig import load_config, save_config

        config = load_config()
        strava_cfg = config.get("providers", {}).get("strava", {})
        client_id = strava_cfg.get("client_id", "").strip()
        client_secret = strava_cfg.get("client_secret", "").strip()

        if not client_id or not client_secret:
            return _strava_callback_page(False, "Strava client_id and client_secret not configured.")

        from stravalib.client import Client

        client = Client()
        token_dict = client.exchange_code_for_token(
            client_id=int(client_id),
            client_secret=client_secret,
            code=code,
        )

        providers = config.get("providers", {})
        strava_updated = providers.get("strava", {}).copy()
        strava_updated["access_token"] = str(token_dict["access_token"])
        strava_updated["refresh_token"] = str(token_dict.get("refresh_token", ""))
        strava_updated["token_expires"] = str(token_dict.get("expires_at", "0"))
        providers["strava"] = strava_updated
        save_config({**config, "providers": providers})

        return _strava_callback_page(True, "Strava authentication successful!")
    except Exception as e:
        return _strava_callback_page(False, f"Token exchange failed: {e}")


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "app": "tracekit-web"})


if __name__ == "__main__":
    print("Starting tracekit Web App...")

    config = load_tracekit_config()
    print(f"Config loaded: timezone={config.get('home_timezone')}, debug={config.get('debug')}")

    print("Server starting at: http://localhost:5000")
    print("  Dashboard:    http://localhost:5000")
    print("  Settings:     http://localhost:5000/settings")
    print("  Config API:   http://localhost:5000/api/config")
    print("  Database API: http://localhost:5000/api/database")
    print("  Health:       http://localhost:5000/health")
    print("\nPress Ctrl+C to stop")

    try:
        app.run(debug=config.get("debug", False), host="0.0.0.0", port=5000, threaded=True)
    except Exception as e:
        print(f"Server failed to start: {e}")
        exit(1)
