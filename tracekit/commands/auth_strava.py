import os
import socket
import urllib.parse
import webbrowser

from stravalib.client import Client


def run():
    client = Client()
    client_id = int(os.environ["STRAVA_CLIENT_ID"])
    client_secret = os.environ["STRAVA_CLIENT_SECRET"]
    port = 8000
    redirect_uri = f"http://localhost:{port}/authorization_successful"
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
        s.bind(("127.0.0.1", port))
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
    access_token = token_dict["access_token"]
    refresh_token = token_dict.get("refresh_token")
    expires_at = token_dict.get("expires_at")
    print("\nPaste the following lines into your .env file:")
    print(f"STRAVA_ACCESS_TOKEN={access_token}")
    if refresh_token:
        print(f"STRAVA_REFRESH_TOKEN={refresh_token}")
    if expires_at:
        print(f"STRAVA_TOKEN_EXPIRES={expires_at}")
