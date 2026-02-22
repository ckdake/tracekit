"""Garmin authentication routes for the tracekit web app."""

import time
import uuid
from typing import Any

from db_init import _init_db
from flask import Blueprint, jsonify, request

garmin_bp = Blueprint("auth_garmin", __name__)

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
    from tracekit.appconfig import save_garmin_tokens

    save_garmin_tokens(email, garth_tokens)


@garmin_bp.route("/api/auth/garmin", methods=["POST"])
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
        return (
            jsonify({"error": f"Rate limit exceeded, please wait and try again: {e}"}),
            429,
        )
    except GarminConnectConnectionError as e:
        return jsonify({"error": f"Connection error: {e}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@garmin_bp.route("/api/auth/garmin/mfa", methods=["POST"])
def api_auth_garmin_mfa():
    """Complete Garmin MFA step. Accepts session_id + mfa_code."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "")
    mfa_code = data.get("mfa_code", "").strip()
    if not session_id or not mfa_code:
        return jsonify({"error": "session_id and mfa_code are required"}), 400

    entry = _pending_garmin_sessions.get(session_id)
    if not entry:
        return (
            jsonify({"error": "Session not found or expired. Please start authentication again."}),
            404,
        )

    garmin, client_state, email, expires_at = entry
    if time.time() > expires_at:
        del _pending_garmin_sessions[session_id]
        return (
            jsonify({"error": "Session expired. Please start authentication again."}),
            410,
        )

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
