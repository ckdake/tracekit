"""Intervals.icu OAuth routes for the tracekit web app."""

import os

import requests
from db_init import _init_db
from flask import Blueprint, redirect, request

intervalsicu_bp = Blueprint("auth_intervalsicu", __name__)

_AUTHORIZE_URL = "https://intervals.icu/oauth/authorize"
_TOKEN_URL = "https://intervals.icu/api/oauth/token"
_SCOPES = "ACTIVITY:READ,ACTIVITY:WRITE"


def _get_intervalsicu_client_credentials(icu_cfg: dict) -> tuple[str, str]:
    """Return the effective (client_id, client_secret) for the Intervals.icu OAuth flow.

    When the user has opted into personal credentials, their saved values are
    used directly.  Otherwise the operator's system-level env vars take
    precedence, falling back to any value the user has stored.
    """
    if icu_cfg.get("use_personal_credentials"):
        return icu_cfg.get("client_id", "").strip(), icu_cfg.get("client_secret", "").strip()
    client_id = os.environ.get("INTERVALSICU_CLIENT_ID", "").strip() or icu_cfg.get("client_id", "").strip()
    client_secret = os.environ.get("INTERVALSICU_CLIENT_SECRET", "").strip() or icu_cfg.get("client_secret", "").strip()
    return client_id, client_secret


def _icu_callback_page(success: bool, message: str) -> str:
    """Return an HTML page that notifies the opener then closes itself."""
    status = "ok" if success else "error"
    icon = "\u2713" if success else "\u2717"
    safe_msg = message.replace("'", "\\'").replace("<", "&lt;").replace(">", "&gt;")
    redirect_block = (
        """
  <p id="redirect-msg" style="font-size:0.95rem;color:#666;">
    Redirecting to <a href="/settings">Settings</a> in <span id="countdown">30</span>s\u2026
  </p>
  <script>
    var sec = 30;
    var t = setInterval(function() {
      sec--;
      var el = document.getElementById('countdown');
      if (el) el.textContent = sec;
      if (sec <= 0) { clearInterval(t); window.location.href = '/settings'; }
    }, 1000);
  </script>"""
        if success
        else ""
    )
    return f"""<!DOCTYPE html>
<html><head><title>Intervals.icu Auth</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px;color:#2c3e50;">
  <p style="font-size:1.2rem;">{icon} {safe_msg}</p>
  {redirect_block}
  <p><a href="/settings" style="font-size:1rem;">Go to Settings</a></p>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{intervalsicuAuth:true,status:'{status}',message:'{safe_msg}'}}, '*');
      window.close();
    }}
  </script>
</body></html>"""


@intervalsicu_bp.route("/api/auth/intervalsicu/authorize")
def api_auth_intervalsicu_authorize():
    """Redirect the browser to Intervals.icu's OAuth authorization page."""
    _init_db()
    from tracekit.appconfig import load_config

    config = load_config()
    icu_cfg = config.get("providers", {}).get("intervalsicu", {})
    client_id, client_secret = _get_intervalsicu_client_credentials(icu_cfg)

    if not client_id or not client_secret:
        return (
            "<h3>Configuration error</h3>"
            "<p>Intervals.icu <strong>client id</strong> and <strong>client secret</strong> "
            "are not configured. Enable personal credentials in Settings or ask the "
            "operator to set INTERVALSICU_CLIENT_ID and INTERVALSICU_CLIENT_SECRET.</p>",
            400,
        )

    try:
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        redirect_uri = f"{scheme}://{request.host}/api/auth/intervalsicu/callback"
        authorize_url = f"{_AUTHORIZE_URL}?client_id={client_id}&redirect_uri={redirect_uri}&scope={_SCOPES}"
        return redirect(authorize_url)
    except Exception as e:
        return f"<h3>Error</h3><p>{e}</p>", 500


@intervalsicu_bp.route("/api/auth/intervalsicu/callback")
def api_auth_intervalsicu_callback():
    """Handle Intervals.icu OAuth callback — exchange code for token and save."""
    error = request.args.get("error")
    if error:
        return _icu_callback_page(False, f"Intervals.icu authorization denied: {error}")

    code = request.args.get("code")
    if not code:
        return _icu_callback_page(False, "No authorization code received from Intervals.icu.")

    try:
        _init_db()
        from tracekit.appconfig import load_config, save_intervalsicu_athlete_id, save_intervalsicu_tokens

        config = load_config()
        icu_cfg = config.get("providers", {}).get("intervalsicu", {})
        client_id, client_secret = _get_intervalsicu_client_credentials(icu_cfg)

        if not client_id or not client_secret:
            return _icu_callback_page(False, "Intervals.icu client_id and client_secret not configured.")

        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        redirect_uri = f"{scheme}://{request.host}/api/auth/intervalsicu/callback"

        resp = requests.post(
            _TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        if not resp.ok:
            return _icu_callback_page(False, f"Token exchange failed: {resp.text}")

        token_data = resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return _icu_callback_page(False, "No access token received from Intervals.icu.")

        save_intervalsicu_tokens(access_token)

        # Save the athlete ID for webhook event routing.
        athlete = token_data.get("athlete", {})
        athlete_id = str(athlete.get("id", "")) if athlete else ""
        if athlete_id:
            save_intervalsicu_athlete_id(athlete_id)

        return _icu_callback_page(True, "Intervals.icu authentication successful!")
    except Exception as e:
        return _icu_callback_page(False, f"Token exchange failed: {e}")
