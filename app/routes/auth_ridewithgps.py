"""RideWithGPS OAuth routes for the tracekit web app."""

import os

from db_init import _init_db
from flask import Blueprint, redirect, request

ridewithgps_bp = Blueprint("auth_ridewithgps", __name__)


def _get_ridewithgps_client_credentials(rwgps_cfg: dict) -> tuple[str, str]:
    """Return the effective (client_id, client_secret) for the RideWithGPS OAuth flow.

    When the user has opted into personal credentials, their saved values are
    used directly.  Otherwise the operator's system-level env vars take
    precedence, falling back to any value the user has stored.
    """
    if rwgps_cfg.get("use_personal_credentials"):
        return rwgps_cfg.get("client_id", "").strip(), rwgps_cfg.get("client_secret", "").strip()
    client_id = os.environ.get("RIDEWITHGPS_CLIENT_ID", "").strip() or rwgps_cfg.get("client_id", "").strip()
    client_secret = (
        os.environ.get("RIDEWITHGPS_CLIENT_SECRET", "").strip() or rwgps_cfg.get("client_secret", "").strip()
    )
    return client_id, client_secret


def _rwgps_callback_page(success: bool, message: str) -> str:
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
<html><head><title>RideWithGPS Auth</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px;color:#2c3e50;">
  <p style="font-size:1.2rem;">{icon} {safe_msg}</p>
  {redirect_block}
  <p><a href="/settings" style="font-size:1rem;">Go to Settings</a></p>
  <script>
    if (window.opener) {{
      window.opener.postMessage({{rwgpsAuth:true,status:'{status}',message:'{safe_msg}'}}, '*');
      window.close();
    }}
  </script>
</body></html>"""


@ridewithgps_bp.route("/api/auth/ridewithgps/authorize")
def api_auth_ridewithgps_authorize():
    """Redirect the browser to RideWithGPS's OAuth authorization page."""
    _init_db()
    from tracekit.appconfig import load_config

    config = load_config()
    rwgps_cfg = config.get("providers", {}).get("ridewithgps", {})
    client_id, client_secret = _get_ridewithgps_client_credentials(rwgps_cfg)

    if not client_id or not client_secret:
        return (
            "<h3>Configuration error</h3>"
            "<p>RideWithGPS <strong>client id</strong> and <strong>client secret</strong> "
            "are not configured. Enable personal credentials in Settings or ask the "
            "operator to set RIDEWITHGPS_CLIENT_ID and RIDEWITHGPS_CLIENT_SECRET.</p>",
            400,
        )

    try:
        from pyrwgps import RideWithGPS

        client = RideWithGPS(client_id=client_id, client_secret=client_secret)
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        redirect_uri = f"{scheme}://{request.host}/api/auth/ridewithgps/callback"
        authorize_url = client.authorization_url(redirect_uri=redirect_uri)
        return redirect(str(authorize_url))
    except Exception as e:
        return f"<h3>Error</h3><p>{e}</p>", 500


@ridewithgps_bp.route("/api/auth/ridewithgps/callback")
def api_auth_ridewithgps_callback():
    """Handle RideWithGPS OAuth callback — exchange code for token and save."""
    error = request.args.get("error")
    if error:
        return _rwgps_callback_page(False, f"RideWithGPS authorization denied: {error}")

    code = request.args.get("code")
    if not code:
        return _rwgps_callback_page(False, "No authorization code received from RideWithGPS.")

    try:
        _init_db()
        from tracekit.appconfig import load_config, save_ridewithgps_tokens

        config = load_config()
        rwgps_cfg = config.get("providers", {}).get("ridewithgps", {})
        client_id, client_secret = _get_ridewithgps_client_credentials(rwgps_cfg)

        if not client_id or not client_secret:
            return _rwgps_callback_page(False, "RideWithGPS client_id and client_secret not configured.")

        from pyrwgps import RideWithGPS

        client = RideWithGPS(client_id=client_id, client_secret=client_secret)
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        redirect_uri = f"{scheme}://{request.host}/api/auth/ridewithgps/callback"
        token_response = client.exchange_code(code=code, redirect_uri=redirect_uri)

        access_token = getattr(token_response, "access_token", None) or client.access_token
        if not access_token:
            return _rwgps_callback_page(False, "No access token received from RideWithGPS.")

        save_ridewithgps_tokens(access_token)
        return _rwgps_callback_page(True, "RideWithGPS authentication successful!")
    except Exception as e:
        return _rwgps_callback_page(False, f"Token exchange failed: {e}")
