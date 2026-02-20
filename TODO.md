# TODO

Tracked here for visibility. PRs and issues welcome.

## Overall capabilitites

- [ ] Move config to be in the database, and give us a GUI to update config
- [ ] users. database should have 'em and we should have to log in when in production
- [ ] improve / on webapp to be what we care about, most recent months first

## Providers & Sync

- [ ] Go through all providers and manually fix them to work the same way as the file provider
- [ ] Ensure no API calls are made if the month is already synced
- [ ] Fix Strava gear matching to work for running shoes
- [ ] Fix "create" in providers to `create_from_activity`, get all that out of `sync_month`
- [ ] What is in TrainingPeaks?
- [ ] What is in Wandrer.earth?
- [ ] What about choochoo?
- [ ] Load files from S3 or another remote source: [boto3](https://pypi.org/project/boto3/)

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
