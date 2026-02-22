"""First-signup data ownership claim.

When the very first web user signs up, all rows currently tagged ``user_id=0``
(CLI-imported or pre-auth data) are re-tagged with that user's ID.  This
transfers ownership of existing data to the new account so they see a populated
app immediately rather than an empty one.

Only called once — subsequent signups skip this because ``user_id=0`` rows are
no longer the "unclaimed" pool once any web user exists.
"""

from tracekit.db import get_db


def claim_unscoped_data(user_id: int) -> None:
    """Bulk-update all user_id=0 rows to ``user_id`` across every scoped table.

    Safe to call multiple times — rows already tagged with a non-zero user_id
    are untouched.  Runs in a single transaction per table.
    """
    if user_id == 0:
        return  # nothing to do

    db = get_db()
    db.connect(reuse_if_open=True)

    tables = [
        "activity",
        "strava_activities",
        "garmin_activities",
        "ridewithgps_activities",
        "spreadsheet_activities",
        "file_activities",
        "stravajson_activities",
        "appconfig",
        "providersync",
        "provider_status",
        "provider_pull_status",
        "month_sync_status",
        "notification",
    ]

    uid = int(user_id)  # guarantee integer — safe to inline in SQL
    for table in tables:
        try:
            db.execute_sql(f'UPDATE "{table}" SET user_id = {uid} WHERE user_id = 0')
        except Exception as e:
            print(f"[data_claim] could not claim {table}: {e}")
