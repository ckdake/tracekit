# TODO

Tracked here for visibility. PRs and issues welcome.

## Overall capabilitites

next:
- [ ] feat: remove "reject" button. its dumb.
- [ ] feat: on sync, use Activty table to link up to all provider activities
- [ ] bug: pulling provider in ui for a month doesn't get new activites in the month
- [ ] bug: worker is running migrations
- [ ] bug: js error on toggle sync equipment for intervals.icu
- [ ] bug: intervals.icu gear update not working (make sure gear exists)
- [ ] bug: strava gear update sometimes not workign due to running shoe naming
- [ ] feat: as syncs are applied, update the visible table on /month/YYYY-MM to show as it updates
- [ ] for web app, require subscription to be active for providers to sync
- [ ] refactor all the web/sync stuff to use list of providers from code/admin, not hardcoded individually
- [ ] discord?
- [ ] file provider should have an upload button that uploads a new file. dont overwrite existing files! (check filename on clientside and server side). if its a zip, extrct safely

later
- [ ] better top/right nav UI
- [ ] better "month status" UI and logic
- [ ] allow exporting all files
- [ ] metrics to Sentry for providers/syncing
- [ ] longer caching of static pages, so cloudflare can cache. rotate filenames on build
- [ ] refactor auth to make it harder to write SQL that bypasses.
- [ ] user limits and rate limiting. TBD!
- [ ] outbound email sending for email verificaiton on login, and password reset
- [ ] i think we need a websocket or something for realtime updates
- [ ] add inbound webhooks from ridewithgps on trips -> verify

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
