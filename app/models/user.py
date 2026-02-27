"""User model for email/password authentication."""

from flask_login import UserMixin
from peewee import CharField, IntegerField, Model
from werkzeug.security import generate_password_hash

from tracekit.db import db


class User(UserMixin, Model):
    """A registered user account."""

    email = CharField(unique=True)
    password_hash = CharField()
    # "active" — can log in; "blocked" — pending admin approval
    status = CharField(default="blocked")
    # Stripe subscription fields (null when not subscribed)
    stripe_customer_id = CharField(null=True)
    # "active", "past_due", "canceled", etc. — mirrors Stripe's status
    stripe_subscription_status = CharField(null=True)
    # Unix timestamp of current period end (or cancellation date)
    stripe_subscription_end = IntegerField(null=True)

    class Meta:
        database = db
        table_name = "user"

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_admin(self) -> bool:
        return self.id == 1

    def get_id(self) -> str:
        return str(self.id)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
