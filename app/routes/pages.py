"""Page routes (HTML views) for the tracekit web app."""

import os
from datetime import UTC, datetime

import pytz
from db_init import load_tracekit_config
from flask import Blueprint, g, redirect, render_template
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

    if stripe_enabled:
        user = g.get("current_user")
        if user:
            subscription_status = user.stripe_subscription_status
            if user.stripe_subscription_end:
                subscription_end = datetime.fromtimestamp(user.stripe_subscription_end, tz=UTC).strftime("%Y-%m-%d")

    return render_template(
        "settings.html",
        config=config,
        timezones=timezones,
        page_name="Settings",
        stripe_enabled=stripe_enabled,
        subscription_status=subscription_status,
        subscription_end=subscription_end,
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
