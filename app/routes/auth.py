"""Authentication routes — signup, login, logout."""

from flask import Blueprint, redirect, render_template, request, session, url_for
from models.user import User
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """Signup page — create a new account."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not email:
            error = "Email is required."
        elif not password:
            error = "Password is required."
        elif password != confirm:
            error = "Passwords do not match."

        if error is None and User.select().where(User.email == email).exists():
            error = "An account with that email already exists."

        if error is None:
            is_first_user = User.select().count() == 0
            user = User.create(
                email=email,
                password_hash=generate_password_hash(password),
                # The first user (admin) is active immediately; all others are blocked.
                status="active" if is_first_user else "blocked",
            )
            session["user_id"] = user.id
            if is_first_user:
                from data_claim import claim_unscoped_data

                from tracekit.user_context import set_user_id

                set_user_id(user.id)
                claim_unscoped_data(user.id)
            return redirect(url_for("pages.index"))

        return render_template("signup.html", error=error, email=email)

    return render_template("signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Login page — authenticate with email and password."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        error = None
        user = None
        if not email or not password:
            error = "Email and password are required."

        if error is None:
            try:
                user = User.get(User.email == email)
                if not check_password_hash(user.password_hash, password):
                    error = "Invalid email or password."
                elif user.status != "active":
                    error = "Your account is pending approval. Please contact the administrator."
            except User.DoesNotExist:
                error = "Invalid email or password."

        if error is None and user is not None:
            session["user_id"] = user.id
            return redirect(url_for("pages.index"))

        return render_template("login.html", error=error, email=email)

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Log the current user out."""
    session.pop("user_id", None)
    return redirect(url_for("pages.index"))
