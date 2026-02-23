# Privacy Policy — Self-Hosted tracekit

**Effective Date:** February 23, 2026

This document applies when you run tracekit yourself on your own hardware or a server you
control. When you self-host tracekit, **you are the operator** and you are responsible for
your own data.

If you are using the hosted SaaS product at [app.tracekit.app](https://app.tracekit.app),
that service has its own privacy policy displayed within the application.

---

## What tracekit stores

tracekit stores data in a database that **you own and control** — SQLite by default, or
PostgreSQL if you configure it. Data stored includes:

- **Activity metadata:** name, type, date/time, duration, distance, elevation, equipment,
  heart-rate averages, temperature, and provider-assigned activity IDs
- **Provider credentials:** OAuth tokens and API credentials for connected services (Strava,
  Garmin, RideWithGPS). These are stored in your database or `.env` file on your machine.
- **Optionally, source activity files:** if you place GPX, FIT, or TCX files in your data
  directory, tracekit will read and index them. Those files remain on your own filesystem.

tracekit does **not** store GPS tracks, per-second sensor streams, or any data belonging to
other users.

---

## How data is used

- **Display:** your cached activities are shown in the tracekit calendar and sync status pages.
- **Matching:** records from different providers are compared by timestamp and distance to
  identify the same activity across platforms.
- **Writeback:** tracekit only writes to a third-party platform (e.g. updating an activity
  title or gear assignment on Strava) when you explicitly click a button to trigger that
  action. No automatic writes happen without your instruction.

tracekit never aggregates data across users, never shares your data with third parties, and
never uses your data for advertising or machine learning.

---

## Third-party platforms

tracekit connects to Strava, Garmin Connect, and RideWithGPS using the credentials you
supply. Your use of those platforms is governed by their own terms and privacy policies.
tracekit is not affiliated with or endorsed by any of them.

- Strava API terms: [strava.com/legal/api](https://www.strava.com/legal/api)
- Garmin: [garmin.com](https://www.garmin.com)
- RideWithGPS: [ridewithgps.com](https://ridewithgps.com)

---

## Your control

Because you operate the software, you have full control:

- **Access:** all data is in the database file on your server.
- **Delete:** use the Settings page → Danger Zone, or `python -m tracekit reset`.
- **Revoke:** disconnect tracekit from any provider via that provider's connected-apps page
  (e.g. [strava.com/settings/apps](https://www.strava.com/settings/apps)).

---

## Contact

tracekit is open-source: <https://github.com/ckdake/tracekit>

For questions, open an issue on GitHub.
