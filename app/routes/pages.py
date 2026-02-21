"""Page routes (HTML views) for the tracekit web app."""

from datetime import datetime

import pytz
from db_init import load_tracekit_config
from flask import Blueprint, redirect, render_template
from helpers import get_current_date_in_timezone

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/privacy")
def privacy():
    """Privacy policy and terms of service page."""
    return render_template("privacy.html", page_name="Privacy Policy")


@pages_bp.route("/settings")
def settings():
    """Settings page — edit providers, timezone and debug flag."""
    config = load_tracekit_config()
    timezones = pytz.common_timezones
    return render_template("settings.html", config=config, timezones=timezones, page_name="Settings")


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
