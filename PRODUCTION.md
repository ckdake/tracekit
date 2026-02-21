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
mkdir -p ~/data/activities ~/pgdata ~/redis ~/.garminconnect
chown -R tracekit:tracekit ~/data ~/pgdata ~/redis ~/.garminconnect
cp docker-compose.yml ~/docker-compose.yml
```

Create a `.env` file with your provider credentials:

```bash
touch ~/.env
chmod 600 ~/.env
```

Edit `~/.env`:

```sh
# Strava
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
STRAVA_ACCESS_TOKEN=your_access_token
STRAVA_REFRESH_TOKEN=your_refresh_token
STRAVA_TOKEN_EXPIRES=token_expiration_timestamp

# RideWithGPS
RIDEWITHGPS_EMAIL=your_email
RIDEWITHGPS_PASSWORD=your_password
RIDEWITHGPS_KEY=your_api_key

# Garmin
GARMIN_EMAIL=your_email
GARMINTOKENS=/opt/tracekit/.garminconnect

# Host uid/gid — all containers run as this user so bind-mount files
# are owned by tracekit:tracekit on the host. Set with:
#   echo "TRACEKIT_UID=$(id -u)" >> ~/.env
#   echo "TRACEKIT_GID=$(id -g)" >> ~/.env
TRACEKIT_UID=
TRACEKIT_GID=

# PostgreSQL — used by both the postgres container and the tracekit container.
# Choose a strong random password; it never needs to leave this file.
POSTGRES_PASSWORD=change_me_to_a_strong_random_password
```

Docker Compose picks this up automatically from the working directory and injects it into each container via `env_file` in `docker-compose.yml`.

Tables are created automatically on every container start — the app retries the DB connection for up to 60 s, so containers can start in any order.

## Garmin Authentication

Garmin tokens must exist on the host **before** the containers start. Run auth once as the `tracekit` user (with `GARMINTOKENS` pointing at the bind-mount path so the tokens land in the right place):

```bash
cd /opt/tracekit
GARMINTOKENS=/opt/tracekit/.garminconnect python -m tracekit auth-garmin
```

This creates `oauth1_token.json` and `oauth2_token.json` inside `/opt/tracekit/.garminconnect/`. The directory is bind-mounted into both the web and worker containers so all services share the same tokens.

> **Token refresh:** garth (the underlying auth library) rewrites the token files when it refreshes them during normal use. The mount is therefore **read-write** — not read-only.

To re-authenticate after tokens expire, stop the containers, re-run the command above, then restart:

```bash
docker compose down
GARMINTOKENS=/opt/tracekit/.garminconnect python -m tracekit auth-garmin
docker compose up -d
```

---

## Deploying

As the `tracekit` user, everything lives under `/opt/tracekit/`:

```bash
cd /opt/tracekit
docker compose up -d
```

On first boot, visit `http://your-domain/settings` to configure your timezone, enabled providers, and debug mode. Configuration is stored in PostgreSQL and persists across restarts.

The compose file binds to `127.0.0.1:5000` only, so the port is **not** publicly exposed. Your reverse proxy connects to it internally.

Key volume mounts (defined in `docker-compose.yml`):
- `/opt/tracekit/data` → `/opt/tracekit/data` (read-write) — activity files (FIT/GPX/TCX exports)
- `/opt/tracekit/.garminconnect` → `/opt/tracekit/.garminconnect` (read-write) — Garmin OAuth tokens (garth refreshes these in-place)
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
