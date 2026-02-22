import socket
import urllib.parse
import webbrowser

from stravalib.client import Client


def run():
    from tracekit.appconfig import load_config, save_strava_tokens

    config = load_config()
    strava_cfg = config.get("providers", {}).get("strava", {})
    client_id_raw = strava_cfg.get("client_id", "").strip()
    client_secret = strava_cfg.get("client_secret", "").strip()

    if not client_id_raw or not client_secret:
        print("Error: strava client_id and client_secret must be set in the Settings UI before running auth.")
        print("Visit http://localhost:5000/settings and fill in the Strava credentials.")
        return

    client_id = int(client_id_raw)
    client = Client()
    port = 8000
    redirect_uri = f"http://localhost:{port}/authorization_successful"
    # Bind on all interfaces so the callback works when port-forwarded through Docker.
    authorize_url = client.authorization_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=[
            "activity:read_all",
            "activity:write",
            "profile:read_all",
            "profile:write",
        ],
    )
    print("Opening browser for Strava authorization...")
    webbrowser.open(authorize_url)
    print(f"If your browser does not open, visit this URL: {authorize_url}")
    print("Waiting for Strava to redirect with authorization code...")
    # Start a simple HTTP server to capture the code
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        s.listen()
        conn, _addr = s.accept()
        request_bytes = b""
        with conn:
            while True:
                chunk = conn.recv(512)
                request_bytes += chunk
                if request_bytes.endswith(b"\r\n\r\n"):
                    break
            conn.sendall(b"HTTP/1.1 200 OK\r\n\r\nsuccess\r\n")
        request = request_bytes.decode("utf-8")
        status_line = request.split("\n", 1)[0]
        _method, raw_url, _protocol_version = status_line.split(" ")
        url = urllib.parse.urlparse(raw_url)
        query_params = urllib.parse.parse_qs(url.query, keep_blank_values=True)
        if url.path == "/authorization_successful":
            code = query_params.get("code")[0]
        else:
            raise RuntimeError("Did not receive code from Strava redirect.")
    token_dict = client.exchange_code_for_token(
        client_id=client_id,
        client_secret=client_secret,
        code=code,
    )
    save_strava_tokens(token_dict)
    print("✓ Strava tokens saved to database.")
