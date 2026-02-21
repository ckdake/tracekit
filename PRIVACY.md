# Privacy Policy & Terms of Service

**Effective Date:** February 21, 2026

tracekit is a personal, self-hosted fitness data aggregation tool. This document describes
how tracekit handles your data when you run it yourself or use a hosted instance operated
by someone you trust.

---

## 1. What tracekit Is

tracekit is open-source software you install and operate yourself. It connects to third-party
fitness platforms (Strava, Garmin, RideWithGPS, etc.) using OAuth tokens that **you** provide
and stores a local cache of your activity metadata to power features like:

- Viewing your own activity history across providers in one calendar view
- Matching the same activity across providers (e.g. Garmin upload → Strava record)
- Updating activity titles and gear assignments on Strava

---

## 2. Data We Collect and Why

### What is stored
tracekit stores **activity metadata only** — no GPS tracks, no route geometry, no heart-rate
time series. The metadata stored includes:

- Activity name, type, date/time, and duration
- Distance and elevation
- Equipment / gear name
- Heart-rate averages and max values
- Temperature
- Provider-assigned activity ID

### What is NOT stored
- GPS coordinates, routes, or map data
- Granular time-series sensor data (per-second HR, power, cadence streams)
- Any data from other Strava users — only the authenticated user's own data is ever fetched or stored

### Why it is stored
Data is cached locally (in a SQLite database you control) to avoid unnecessary API calls and
to allow offline browsing of your own history. The cache is only ever read by you — the
person running the software.

---

## 3. How Data Is Used

- **Matching:** Activity records from different providers are compared by timestamp and
  distance to identify duplicates and link IDs across providers.
- **Display:** Your own cached activities are shown on the calendar and sync status pages.
- **Writeback:** You may use tracekit to update activity titles and gear assignments on Strava
  via the Strava API. No other write operations are performed on third-party platforms.

tracekit **never**:

- Shares your data with any third party
- Aggregates or analyzes data across multiple users
- Uses your data for advertising or machine learning
- Sells, licenses, or discloses your data to anyone

---

## 4. Third-Party Platforms

tracekit integrates with the following platforms. Your use of those platforms is governed by
their own terms and privacy policies.

### Strava
tracekit uses the [Strava API](https://www.strava.com/legal/api). Activity data obtained via
the Strava API is used solely to display your own activities to you and to perform gear/title
updates on your behalf. tracekit is not affiliated with or endorsed by Strava.

> Powered by Strava — [strava.com](https://www.strava.com)

### Garmin
tracekit can ingest activity data that originated on Garmin devices, either via Garmin Connect
or via Strava (where Garmin-sourced activities may appear). tracekit is not affiliated with or
endorsed by Garmin.

> Powered by Garmin — [garmin.com](https://www.garmin.com)

### RideWithGPS
tracekit can sync activities from RideWithGPS. tracekit is not affiliated with or endorsed by
RideWithGPS.

---

## 5. Data Retention

- Cached activity data is retained locally in your SQLite database until you delete it.
- You can delete all data for a provider at any time using the `reset` command or the settings
  page in the web app.
- If you request deletion of your data from a hosted instance, the operator must delete all
  stored data related to your account within a reasonable time (we target 24 hours).
- **Daily sync:** tracekit performs a daily background sync. If an activity has been deleted
  on a connected platform, tracekit will eventually remove it from the local cache. See the
  [TODO list](TODO.md) for planned improvements to deletion propagation.

---

## 6. Security

- OAuth tokens used to access third-party APIs are stored in your local configuration file.
  You are responsible for securing that file.
- All communication with third-party APIs uses HTTPS.
- tracekit does not expose your data to the internet unless you choose to run the web app on
  a public interface.

---

## 7. Your Rights

You have the right to:

- **Access** all data tracekit has stored about you (it is in your SQLite database file).
- **Delete** all stored data — use `python -m tracekit reset` or the settings page.
- **Revoke** tracekit's access to any connected platform at any time by disconnecting the app
  in that platform's settings (e.g. Strava's [Connected Apps](https://www.strava.com/settings/apps)
  page). Upon revocation, no further data will be fetched.

---

## 8. Changes to This Policy

This policy may be updated as tracekit's features evolve. The effective date at the top of
this document reflects when it was last changed. Continued use of the software constitutes
acceptance of the current policy.

---

## 9. Contact

tracekit is open-source software maintained on GitHub:
<https://github.com/ckdake/tracekit>

For questions or deletion requests, open an issue or contact the repository maintainer.
