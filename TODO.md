# TODO

Tracked here for visibility. PRs and issues welcome.

## Overall capabilitites

- [ ] users. database should have 'em and we should have to log in when in production
- [ ] know which months are pulling, show that
- [ ] add new source data files to file data when found in other places
- [ ] know which months are "fully synced" and only reset that when we get new data/etc
- [ ] know sync status, which months+providers are queued, their last sync state, etc.
- [ ] fix / view so that we get all "action" buttons on each month tile, for both on-load and pulled in


## Providers & Sync

- [ ] Go through all providers and manually fix them to work the same way as the file provider
- [ ] Ensure no API calls are made if the month is already synced
- [ ] Fix Strava gear matching to work for running shoes
- [ ] Fix "create" in providers to `create_from_activity`, get all that out of `sync_month` command
- [ ] Add TrainingPeaks as provider
- [ ] Add Wandrer.earth as provider
- [ ] What about choochoo?
- [ ] allow upload of data file, persist to it as it currently works, and allow download
- [ ] Back files from S3/compatabile or another remote source: [boto3](https://pypi.org/project/boto3/)

## Strava API Compliance

- [ ] **Delete synced Strava activities that have been deleted on Strava** — during daily sync,
      re-fetch the list of activity IDs for each synced month and remove any local records
      whose Strava ID no longer exists (Strava API §2.14.vi requires deletion within 48 hours).
- [ ] **Implement Strava webhook subscriptions** for real-time deletion events
      (`DELETE` event type on `/push_subscriptions`) so deletions propagate immediately rather
      than waiting for the next daily sync. See
      [Strava Webhook Events API](https://developers.strava.com/docs/webhooks/).
- [ ] **Handle token revocation gracefully** — detect 401 responses from Strava, mark the
      provider as disconnected, and prompt the user to re-authorize rather than failing silently.

## File Formats

- [ ] Get everything out of GPX files: [gpxpy](https://pypi.org/project/gpxpy/) *(basics in — fill out metadata, add fields to db)*
- [ ] Get everything out of TCX files: [python-tcxparser](https://pypi.org/project/python-tcxparser/) *(basics in — fill out metadata, add fields to db)*
- [ ] Get everything out of FIT files: [python-fitparse](https://github.com/dtcooper/python-fitparse/) *(basics in — fill out metadata, add fields to db)*
- [ ] Get everything out of KML files: [pykml](https://pypi.org/project/pykml/)
- [ ] Get everything out of spreadsheets with headers: [openpyxl](https://pypi.org/project/openpyxl/) *(basics in — work better with headers)*
- [ ] Switch from fitparse to [fitdecode](https://github.com/polyvertex/fitdecode)

## Output Formats

- [ ] Output as FIT *(lib already included)*
- [ ] Output as TCX *(lib already included)*
- [ ] Output as GPX *(lib already included)*
- [ ] Output as KML *(lib already included)*
- [ ] Output as GeoJSON: [geojson](https://pypi.org/project/geojson/)

## Data & Enrichment

- [ ] What about the weather?
- [ ] What else?

## Tests

- [ ] Write more tests across providers, commands, and file formats

## Getting Data Back Out

Quick reference for exporting to CSV:

```sql
sqlite3 metadata.sqlite3
.headers on
.mode csv
.output metadata.csv
SELECT date,activity_type,location_name,city,state,temperature,equipment,
       duration_hms,max_speed,avg_heart_rate,max_heart_rate,calories,
       max_elevation,total_elevation_gain,with_names,avg_cadence,
       strava_id,garmin_id,ridewithgps_id,notes
  FROM ActivityMetadata
 WHERE source="Main";
.quit
```
