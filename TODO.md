# TODO

Tracked here for visibility. PRs and issues welcome.

## Overall capabilitites

in fitler python package:
- [ ] after updating an activity in a provider, pull that activity again to our local so "our version" is "in sync" with the upstream.

in web app:
- [ ] Order providers by provider priority in the UI, not ABC
- [ ] The chicklet "check" status showing success should turn into a "pull" icon on hover to indicate what it will do when clicked. Make the
- [ ] The pull button for month no longer needs to jam in status text, it just makes the jobs. each chiclet should spin (as it does) until synced, and should reload one by one as sync finishes
- [ ] Remove extra padding in bottom of months, and improve UI for months. The chicklets are refined, but the "month" block is not yet.  More visual consistency with pull and sync buttons and how the providers work. Something better than "X activities". Additionally, when we pull in additional months, they have a "reset" button that is missing from initial page load, and intial page load months have a "sync review" button that is missing from additional. All should have same actions.
- [ ] Each month has a "sync review" page that shows changes that need to be applied for a given month so that everything "matches up".  It's run on-demand when this page is viewed, lets store this "sync status" for the month, similar to how we store "provider status".  a month can be "synchronized" (all good) when "no changes needed" is the calcualted state. It's "requires action" when changes are needed, and "unknown" when we have not yet run. any changes (pull or activity modification in any provider in the month) should reset the status to "unknown" until the sync review page is visited again. (later, we'll automate this up). Most of this change will be in the python package, with just some UI in the app.
- [ ] We have too many notifications. Now that we have provider sync status, we don't need any notifications about "normal" things like daily job running or successes. We only need notifications when a sync fails and will not be retried (e.g. strava rate limit) Most of this change will be in the python package, with just some UI in the app.

later:
- [ ] users. database should have 'em and we should have to log in when in production
- [ ] user limits and rate limiting. TBD!
- [ ] paid subscription: user must have active $5/mo subscription with Stripe to pull/sync.
- [ ] add new source data files to file data when found in other places
- [ ] i think we need a websocket or something for realtime updates
- [ ] file provider should have an upload button that uploads a new file. dont overwrite existing files! (check filename on clientside and server side)
- [ ] download file from providers if file is missing. see https://raw.githubusercontent.com/cyberjunky/python-garminconnect/master/demo.py in download_activities_by_date for garmin

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
