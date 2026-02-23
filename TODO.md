# TODO

Tracked here for visibility. PRs and issues welcome.

## Overall capabilitites

- [ ] admin UI for user=1 to manage users, see data volume per user, see data volume per provider

later:
- [ ] refactor auth to make it harder to write SQL that bypasses.
- [ ] fix user icons, they are stacked vertically and overflowing the navbar
- [ ] user limits and rate limiting. TBD!
- [ ] paid subscription: user must have active $5/mo subscription with Stripe to pull/sync.
- [ ] move app api keys from per-user to admin thing
- [ ] sentry cloud for exceptions
- [ ] move sessions to redis
- [ ] better top/right nav UI
- [ ] outbound email sending for email verificaiton on login, and password reset
- [ ] add new source data files to file data when found in other places
- [ ] i think we need a websocket or something for realtime updates
- [ ] file provider should have an upload button that uploads a new file. dont overwrite existing files! (check filename on clientside and server side)
- [ ] download file from providers if file is missing. see https://raw.githubusercontent.com/cyberjunky/python-garminconnect/master/demo.py in download_activities_by_date for garmin
- [ ] allow exporting all files

## Providers & Sync

- [ ] Go through all providers and manually fix them to work the same way as the file provider
- [ ] Ensure no API calls are made if the month is already synced
- [ ] Fix Strava gear matching to work for running shoes
- [ ] Fix "create" in providers to `create_from_activity`, get all that out of `sync_month` command
- [ ] Add intevals.icu as provider
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
