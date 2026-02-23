# Production Deployment

This documents how to self-host tracekit on a cloud server as a single individual. The setup is:

- Docker container running the Flask web app on HTTP (port 5000), bound to localhost only
- Configuration stored in PostgreSQL — no config file required; use the Settings UI after first boot
- A reverse proxy in front doing SSL termination (not covered here — use Caddy, nginx, etc.)

The published image is `ghcr.io/ckdake/tracekit:latest`.

---

## Prerequisites

- A Linux server (VPS, EC2, Droplet, etc.) with Docker installed
- A domain name pointed at your server's IP

---

## User Setup

Create a dedicated `tracekit` user with `/opt/tracekit` as its home directory, and add it to the `docker` group:

```bash
sudo useradd --system --home /opt/tracekit --create-home --shell /bin/bash tracekit
sudo usermod -aG docker tracekit
```

That's it for root. Switch to the tracekit user for everything from here on:

```bash
su - tracekit
```

Capture the uid/gid — these go into `.env` so compose can run every container as this user:

```bash
echo "TRACEKIT_UID=$(id -u)" >> ~/.env
echo "TRACEKIT_GID=$(id -g)" >> ~/.env
```

---

## First-Boot Setup

Create the directories and copy in the compose file:

```bash
mkdir -p ~/data/activities ~/pgdata ~/redis
chown -R tracekit:tracekit ~/data ~/pgdata ~/redis
cp docker-compose.yml ~/docker-compose.yml
```

Create a `.env` file:

```bash
touch ~/.env
chmod 600 ~/.env
```

Edit `~/.env`:

```sh
# Host uid/gid — all containers run as this user so bind-mount files
# are owned by tracekit:tracekit on the host. Set with:
#   echo "TRACEKIT_UID=$(id -u)" >> ~/.env
#   echo "TRACEKIT_GID=$(id -g)" >> ~/.env
TRACEKIT_UID=
TRACEKIT_GID=

# Flask session signing key — must be set and must be the same value across
# all web container replicas/workers. Without a consistent key, sessions
# encrypted by one worker cannot be decrypted by another and users will be
# randomly logged out. Generate once with:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
SESSION_KEY=change_me_to_a_long_random_string

# PostgreSQL — used by both the postgres container and the tracekit container.
# Choose a strong random password; it never needs to leave this file.
POSTGRES_PASSWORD=change_me_to_a_strong_random_password

# If you're running personally and dont want user/password, set this to true. If this
# is not set to true, you'll be required to create account, login, etc.
SINGLE_USER_MODE=true
```

Docker Compose picks this up automatically from the working directory. All provider credentials (Strava, RideWithGPS, Garmin) are stored in the database and configured through the Settings UI — no credentials belong in this file.

### Optional: Sentry error monitoring

Add your DSN to `.env` to enable Sentry. If unset, Sentry is completely disabled:

```sh
# Sentry error monitoring — leave unset to disable
SENTRY_DSN=https://<key>@o<org>.ingest.us.sentry.io/<project>
```

Get the DSN from your Sentry project under **Settings → Client Keys (DSN)**.

Tables are created automatically on every container start — the app retries the DB connection for up to 60 s, so containers can start in any order.

## Provider Authentication

All provider credentials are stored in the database. Visit `/settings` to enter and update them. The instructions below are also shown on the Settings page next to each provider card.

### RideWithGPS

No CLI step needed. Enter your email, password, and API key directly in the Settings UI under the RideWithGPS provider card.

### Strava

1. **Register the callback URL** in your Strava developer app at [strava.com/settings/api](https://www.strava.com/settings/api). Set the **Authorization Callback Domain** to the domain you are hosting tracekit on (e.g. `tracekit.example.com`). The exact callback path used is `/api/auth/strava/callback`.

2. **In the Settings UI**, enter your Strava `client_id` and `client_secret` under the Strava provider card and save.

3. **Click "Authenticate with Strava"** on the Strava provider card. A popup opens, redirects to Strava for authorization, and saves the tokens automatically on return.

> Re-authenticate any time tokens expire by clicking the button again.

### Garmin

Garmin uses garth for OAuth. Tokens are stored in the database and valid for roughly a year.

**In the Settings UI**, click **Authenticate** on the Garmin provider card. Enter your Garmin Connect email and password in the popup. If your account has MFA enabled, you will be prompted for the one-time code sent to your email. Tokens are saved automatically on success.

To re-authenticate after tokens expire, click the **Re-authenticate** button on the card.

---

## Deploying

As the `tracekit` user, everything lives under `/opt/tracekit/`:

```bash
cd /opt/tracekit
docker compose up -d
```

On first boot, visit `http://your-domain/settings` to configure your timezone, enabled providers, and credentials. Configuration is stored in PostgreSQL and persists across restarts.

The compose file binds to `127.0.0.1:5000` only, so the port is **not** publicly exposed. Your reverse proxy connects to it internally.

Key volume mounts (defined in `docker-compose.yml`):
- `/opt/tracekit/data` → `/opt/tracekit/data` (read-write) — activity files (FIT/GPX/TCX exports)
- `/opt/tracekit/pgdata` → PostgreSQL data directory — all database files live here
- `/opt/tracekit/redis` → Redis persistence directory

> **Config** is stored in PostgreSQL (the `appconfig` table) and managed entirely through the Settings UI at `/settings`. No config file needs to be mounted or maintained on the host.

Services started by `docker compose up -d`:
| Container | Role |
|---|---|
| `tracekit` | Flask web app (port 5000) |
| `tracekit-worker` | Celery worker — runs pull jobs, concurrency=1 |
| `tracekit-beat` | Celery beat scheduler — fires the daily no-op heartbeat |
| `tracekit-db` | PostgreSQL 17 |
| `tracekit-redis` | Redis (broker + result backend) |
| `tracekit-flower` | Flower task monitor (port 5555, localhost only) |

To back up the database:
```bash
docker exec tracekit-db pg_dump -U tracekit tracekit > tracekit_backup_$(date +%Y%m%d).sql
```

Verify it's running:

```bash
docker compose ps
docker compose logs -f
curl http://127.0.0.1:5000/health
```

**Flower** (task queue observability) is available at `http://127.0.0.1:5555` on the host. To expose it through your reverse proxy, add a vhost/location pointing at port 5555. Keep it behind auth — it shows all task history and can inspect results.

**Triggering a pull from the UI:** visit the `/calendar` page and click **Pull** on any month card. The job is enqueued immediately and runs in the worker container; Flower will show its progress and result.

> **Local network access (testing only):** To reach the app from another device on your LAN, change the port binding in `docker-compose.yml` from `"127.0.0.1:5000:5000"` to `"5000:5000"`. Do not use this in production — use a reverse proxy with SSL instead.

---

## Updates

```bash
cd /opt/tracekit
docker compose pull
docker compose down && docker compose up -d
```

---

## Health Check

The container exposes a health endpoint:

```bash
curl http://127.0.0.1:5000/health
```

Docker also checks this automatically every 30 seconds (`HEALTHCHECK` is defined in the image). Check container health with:

```bash
docker inspect --format='{{.State.Health.Status}}' tracekit
```
