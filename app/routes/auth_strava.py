"""Strava OAuth routes for the tracekit web app."""

import os

from db_init import _init_db
from flask import Blueprint, redirect, request

strava_bp = Blueprint("auth_strava", __name__)


def _get_strava_client_credentials(strava_cfg: dict) -> tuple[str, str]:
    """Return the effective (client_id, client_secret) for the Strava OAuth flow.

    When the user has opted into personal credentials, their saved values are
    used directly.  Otherwise the operator's system-level env vars take
    precedence, falling back to any value the user has stored.
    """
    if strava_cfg.get("use_personal_credentials"):
        return strava_cfg.get("client_id", "").strip(), strava_cfg.get("client_secret", "").strip()
    client_id = os.environ.get("STRAVA_CLIENT_ID", "").strip() or strava_cfg.get("client_id", "").strip()
    client_secret = os.environ.get("STRAVA_CLIENT_SECRET", "").strip() or strava_cfg.get("client_secret", "").strip()
    return client_id, client_secret


def _strava_callback_page(success: bool, message: str) -> str:
    """Return an HTML page that notifies the opener then closes itself."""
    status = "ok" if success else "error"
    icon = "\u2713" if success else "\u2717"
    safe_msg = message.replace("'", "\\'").replace("<", "&lt;").replace(">", "&gt;")
    redirect_block = (
        """
  <p id="redirect-msg" style="font-size:0.95rem;color:#666;">
    Redirecting to <a href="/settings">Settings</a> in <span id="countdown">30</span>s…
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
<html><head><title>Strava Auth</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px;color:#2c3e50;">
  <p style="font-size:1.2rem;">{icon} {safe_msg}</p>
  {redirect_block}
  <p><a href="/settings" style="font-size:1rem;">Go to Settings</a></p>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{stravaAuth:true,status:'{status}',message:'{safe_msg}'}}, '*');
      window.close();
    }}
  </script>
</body></html>"""


@strava_bp.route("/api/auth/strava/authorize")
def api_auth_strava_authorize():
    """Redirect the browser to Strava's OAuth authorization page."""
    _init_db()
    from tracekit.appconfig import load_config

    config = load_config()
    strava_cfg = config.get("providers", {}).get("strava", {})
    client_id, client_secret = _get_strava_client_credentials(strava_cfg)

    if not client_id or not client_secret:
        return (
            "<h3>Configuration error</h3>"
            "<p>Strava <strong>client id</strong> and <strong>client secret</strong> "
            "are not configured. Enable personal credentials in Settings or ask the "
            "operator to set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET.</p>",
            400,
        )

    try:
        from stravalib.client import Client

        client = Client()
        redirect_uri = f"{request.scheme}://{request.host}/api/auth/strava/callback"
        authorize_url = client.authorization_url(
            client_id=int(client_id),
            redirect_uri=redirect_uri,
            scope=[
                "activity:read_all",
                "activity:write",
                "profile:read_all",
                "profile:write",
            ],
        )
        return redirect(str(authorize_url))
    except Exception as e:
        return f"<h3>Error</h3><p>{e}</p>", 500


@strava_bp.route("/api/auth/strava/callback")
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
        from tracekit.appconfig import load_config, save_strava_tokens

        config = load_config()
        strava_cfg = config.get("providers", {}).get("strava", {})
        client_id, client_secret = _get_strava_client_credentials(strava_cfg)

        if not client_id or not client_secret:
            return _strava_callback_page(False, "Strava client_id and client_secret not configured.")

        from stravalib.client import Client

        client = Client()
        token_dict = client.exchange_code_for_token(
            client_id=int(client_id),
            client_secret=client_secret,
            code=code,
        )
        save_strava_tokens(token_dict)

        return _strava_callback_page(True, "Strava authentication successful!")
    except Exception as e:
        return _strava_callback_page(False, f"Token exchange failed: {e}")
