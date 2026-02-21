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

# PostgreSQL — used by both the postgres container and the tracekit container.
# Choose a strong random password; it never needs to leave this file.
POSTGRES_PASSWORD=change_me_to_a_strong_random_password
```

Docker Compose picks this up automatically from the working directory. All provider credentials (Strava, RideWithGPS, Garmin) are stored in the database and configured through the Settings UI — no credentials belong in this file.

Tables are created automatically on every container start — the app retries the DB connection for up to 60 s, so containers can start in any order.

## Provider Authentication

All provider credentials are stored in the database. Visit `/settings` to enter and update them. The instructions below are also shown on the Settings page next to each provider card.

### RideWithGPS

No CLI step needed. Enter your email, password, and API key directly in the Settings UI under the RideWithGPS provider card.

### Strava

1. **In the Settings UI**, enter your Strava `client_id` and `client_secret` under the Strava provider card and save.

2. **Expose port 8000 temporarily.** The auth command opens a local HTTP listener to capture the OAuth redirect. Add a temporary port binding to the `tracekit` service in `docker-compose.yml`:
   ```yaml
   ports:
     - "127.0.0.1:5000:5000"
     - "127.0.0.1:8000:8000"   # temporary — remove after auth
   ```
   Then restart: `docker compose up -d tracekit`

3. **Set up an SSH tunnel** from your local machine so the OAuth redirect reaches you:
   ```bash
   ssh -L 8000:localhost:8000 user@your-server
   ```

4. **Run the auth command** inside the container:
   ```bash
   docker exec -it tracekit python -m tracekit auth-strava
   ```
   It prints a Strava authorization URL. Open it in your local browser, authorize the app, and the browser's redirect to `http://localhost:8000/...` is captured through the SSH tunnel. Tokens are saved directly to the database.

5. **Clean up** — remove the temporary `8000` port line from `docker-compose.yml` and restart:
   ```bash
   docker compose up -d tracekit
   ```

> Re-authenticate any time tokens expire by repeating steps 2–5.

### Garmin

Garmin uses garth for OAuth. Tokens are stored in the database and valid for roughly a year.

```bash
docker exec -it tracekit python -m tracekit auth-garmin
```

The command checks the database for existing tokens first. If none are found (or you choose to re-authenticate), it prompts for your Garmin email, password, and MFA code if enabled. Tokens are saved directly to the database — no filesystem token files are used.

To re-authenticate after tokens expire, simply re-run the same command.

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
