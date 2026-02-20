# Production Deployment

This documents how to self-host tracekit on a cloud server as a single individual. The setup is:

- Docker container running the Flask web app on HTTP (port 5000), bound to localhost only
- A config file on the host filesystem that you control
- A reverse proxy in front doing SSL termination (not covered here — use Caddy, nginx, etc.)

The published image is `ghcr.io/ckdake/tracekit:latest`.

---

## Prerequisites

- A Linux server (VPS, EC2, Droplet, etc.) with Docker installed
- A domain name pointed at your server's IP
- Your `tracekit_config.json` already configured

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

---

## Config File

As the `tracekit` user, create the subdirectories and copy in your config and compose file:

```bash
mkdir -p ~/config ~/data/activities
cp tracekit_config.json ~/config/tracekit_config.json
cp docker-compose.yml ~/docker-compose.yml
```

Create a `.env` file with your provider credentials:

```bash
touch ~/.env
chmod 600 ~/.env
```

Edit `~/.env` with your credentials:

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
```

Docker Compose picks this up automatically from the working directory and injects it into the container via `env_file` in `docker-compose.yml`.

Update paths inside `tracekit_config.json` to reflect the data directory:

```json
{
  "metadata_db": "/opt/tracekit/data/metadata.sqlite3",
  "providers": {
    "file": {
      "glob": "/opt/tracekit/data/activities/*"
    }
  }
}
```

---

## Deploying

As the `tracekit` user, everything lives under `/opt/tracekit/`:

```bash
cd /opt/tracekit
docker compose up -d
```

The compose file binds to `127.0.0.1:5000` only, so the port is **not** publicly exposed. Your reverse proxy connects to it internally.

Key volume mounts (defined in `docker-compose.yml`):
- `/opt/tracekit/config` → `/config` (read-only) — contains `tracekit_config.json`
- `/opt/tracekit/data` → `/opt/tracekit/data` (read-write) — database and activity files

Verify it's running:

```bash
docker compose ps
docker compose logs -f
curl http://127.0.0.1:5000/health
```

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
