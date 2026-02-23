"""Stripe subscription routes — checkout, customer portal, and webhooks."""

import logging
import os

import stripe
from flask import Blueprint, abort, g, jsonify, request

log = logging.getLogger(__name__)

stripe_bp = Blueprint("stripe", __name__)


def _stripe_enabled() -> bool:
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def _get_stripe():
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return stripe


def _app_url() -> str:
    return os.environ.get("APP_URL", "http://localhost:5000").rstrip("/")


# ---------------------------------------------------------------------------
# Checkout — create a Stripe Checkout Session and redirect the user
# ---------------------------------------------------------------------------


@stripe_bp.route("/api/stripe/checkout", methods=["POST"])
def create_checkout_session():
    if not _stripe_enabled():
        abort(404)

    plan = request.json.get("plan") if request.is_json else request.form.get("plan")
    if plan == "monthly":
        price_id = os.environ.get("STRIPE_MONTHLY_PRICE_ID")
    elif plan == "annual":
        price_id = os.environ.get("STRIPE_ANNUAL_PRICE_ID")
    else:
        return jsonify({"error": "Invalid plan. Choose 'monthly' or 'annual'."}), 400

    if not price_id:
        return jsonify({"error": f"Price ID for plan '{plan}' is not configured."}), 500

    user = g.get("current_user")
    if not user:
        abort(401)

    s = _get_stripe()
    app_url = _app_url()

    # Reuse an existing Stripe customer if we have one
    customer_kwargs = {}
    if user.stripe_customer_id:
        customer_kwargs["customer"] = user.stripe_customer_id
    else:
        customer_kwargs["customer_email"] = user.email

    try:
        session = s.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{app_url}/settings?subscription=success",
            cancel_url=f"{app_url}/settings?subscription=cancel",
            **customer_kwargs,
        )
    except stripe.StripeError as exc:
        log.error("Stripe checkout error: %s", exc)
        return jsonify({"error": str(exc)}), 502

    return jsonify({"url": session.url})


# ---------------------------------------------------------------------------
# Customer portal — let users manage / cancel their subscription
# ---------------------------------------------------------------------------


@stripe_bp.route("/api/stripe/portal", methods=["POST"])
def customer_portal():
    if not _stripe_enabled():
        abort(404)

    user = g.get("current_user")
    if not user:
        abort(401)

    if not user.stripe_customer_id:
        return jsonify({"error": "No Stripe customer found for your account."}), 400

    s = _get_stripe()
    app_url = _app_url()

    try:
        session = s.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{app_url}/settings",
        )
    except stripe.StripeError as exc:
        log.error("Stripe portal error: %s", exc)
        return jsonify({"error": str(exc)}), 502

    return jsonify({"url": session.url})


# ---------------------------------------------------------------------------
# Webhook — Stripe posts events here; must be a public endpoint
# ---------------------------------------------------------------------------


@stripe_bp.route("/api/stripe/webhook", methods=["POST"])
def webhook():
    if not _stripe_enabled():
        abort(404)

    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    s = _get_stripe()

    try:
        if webhook_secret:
            event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            import json

            event = json.loads(payload)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        log.warning("Stripe webhook validation failed: %s", exc)
        return jsonify({"error": "Invalid payload or signature"}), 400

    _handle_event(event)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Event handler
# ---------------------------------------------------------------------------


def _handle_event(event: dict) -> None:
    """Update the user record based on Stripe subscription lifecycle events."""
    from models.user import User as UserModel

    etype = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if etype == "checkout.session.completed":
        customer_id = data.get("customer")
        customer_email = data.get("customer_email") or data.get("customer_details", {}).get("email")
        _upsert_customer(UserModel, customer_id, customer_email)

    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        customer_id = data.get("customer")
        status = data.get("status")
        period_end = data.get("current_period_end")
        _update_subscription(UserModel, customer_id, status, period_end)

    elif etype == "customer.subscription.deleted":
        customer_id = data.get("customer")
        _update_subscription(UserModel, customer_id, "canceled", None)

    else:
        log.debug("Unhandled Stripe event type: %s", etype)


def _upsert_customer(user_model, customer_id: str, customer_email: str | None) -> None:
    """Store the Stripe customer ID on the matching user row."""
    if not customer_id:
        return
    try:
        if customer_email:
            user = user_model.get_or_none(user_model.email == customer_email)
            if user and not user.stripe_customer_id:
                user.stripe_customer_id = customer_id
                user.save()
                log.info("Linked Stripe customer %s to user %s", customer_id, user.id)
        # If we already stored the customer_id we don't need to do anything else;
        # the subscription.created/updated event will set the status.
    except Exception as exc:
        log.error("Error upserting Stripe customer: %s", exc)


def _update_subscription(user_model, customer_id: str, status: str | None, period_end: int | None) -> None:
    """Update subscription status + end date for the user with this customer_id."""
    if not customer_id:
        return
    try:
        user = user_model.get_or_none(user_model.stripe_customer_id == customer_id)
        if not user:
            log.warning("No user found for Stripe customer %s", customer_id)
            return
        user.stripe_subscription_status = status
        user.stripe_subscription_end = period_end
        user.save()
        log.info(
            "Updated subscription for user %s: status=%s end=%s",
            user.id,
            status,
            period_end,
        )
    except Exception as exc:
        log.error("Error updating subscription for customer %s: %s", customer_id, exc)
