"""User model for email/password authentication."""

from peewee import CharField, IntegerField, Model
from werkzeug.security import check_password_hash, generate_password_hash

from tracekit.db import db


class User(Model):
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
    def is_admin(self) -> bool:
        return self.id == 1

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
