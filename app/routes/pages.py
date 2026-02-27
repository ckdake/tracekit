"""Page routes (HTML views) for the tracekit web app."""

import os
from datetime import UTC, datetime

import pytz
from db_init import load_tracekit_config
from flask import Blueprint, redirect, render_template
from flask_login import current_user
from helpers import get_current_date_in_timezone

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/settings")
def settings():
    """Settings page — edit providers, timezone and debug flag."""
    config = load_tracekit_config()
    timezones = pytz.common_timezones

    stripe_enabled = bool(os.environ.get("STRIPE_SECRET_KEY"))
    subscription_status = None
    subscription_end = None

    if stripe_enabled and current_user.is_authenticated:
        subscription_status = current_user.stripe_subscription_status
        if current_user.stripe_subscription_end:
            subscription_end = datetime.fromtimestamp(current_user.stripe_subscription_end, tz=UTC).strftime("%Y-%m-%d")

    # Indicate which providers have system-level credentials configured in env.
    # These booleans are passed to the settings UI so it can show/hide helpful
    # messages — the actual credential values are never sent to the browser.
    system_credentials = {
        "strava": bool(os.environ.get("STRAVA_CLIENT_ID") and os.environ.get("STRAVA_CLIENT_SECRET")),
        "ridewithgps": bool(os.environ.get("RIDEWITHGPS_KEY")),
    }

    return render_template(
        "settings.html",
        config=config,
        timezones=timezones,
        page_name="Settings",
        stripe_enabled=stripe_enabled,
        subscription_status=subscription_status,
        subscription_end=subscription_end,
        allow_impersonation=current_user.allow_impersonation,
        system_credentials=system_credentials,
    )


@pages_bp.route("/calendar")
def calendar():
    """Redirect legacy /calendar URL to /."""
    return redirect("/", code=301)


@pages_bp.route("/")
def index():
    """Main status/calendar page — last 12 months, most recent first."""
    config = load_tracekit_config()

    current_date = get_current_date_in_timezone(config)
    current_month = f"{current_date.year:04d}-{current_date.month:02d}"

    months = []
    year, month = current_date.year, current_date.month
    for _ in range(12):
        ym = f"{year:04d}-{month:02d}"
        months.append(
            {
                "year_month": ym,
                "year": year,
                "month": month,
                "month_name": datetime(year, month, 1).strftime("%B"),
            }
        )
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    return render_template(
        "index.html",
        config=config,
        initial_months=months,
        current_month=current_month,
        page_name="Status",
    )
