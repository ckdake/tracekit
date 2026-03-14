# TODO

Tracked here for visibility. PRs and issues welcome.

## Overall capabilitites

next:
- [ ] feat: trigger sync whenever new data is collected, for the month. use the Activity table as Source Of Truth for "matching", and ensure it stays update to date with a provider id for each activity. Update / page to show summary stats.
- [ ] feat: only users with active subscription, or admin, can go back further than current month.  all other users: data expires out at start of new month.
- [ ] feat: except admin, "full provider sync" is only allowed once per day.
- [ ] data: 2024-02-29 19:20 gamrin shows up on march 2024 review
- [ ] feat: "year by year" status, so can zoom in to months
- [ ] bug: worker logs are only on stdout, not in sentry logs
- [ ] feat: spreadsheet: ability to add
- [ ] feat: garmin: ability to create gear
- [ ] bug: pulling provider in ui for a month doesn't get new activites in the month
- [ ] bug: worker is running migrations
- [ ] bug: js error on toggle sync equipment for intervals.icu
- [ ] bug: strava: gear update sometimes not workign due to running shoe naming
- [ ] feat: as syncs are applied, update the visible table on /month/YYYY-MM to show as it updates
- [ ] refactor all the web/sync stuff to use list of providers from code/admin, not hardcoded individually
- [ ] file provider upload button shouldn't overwrite existing files! (check filename on clientside and server side). if its a zip, extrct safely
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
