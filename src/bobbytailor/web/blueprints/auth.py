"""Authentication routes — login and logout."""
import logging

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user, login_required

from auth import bcrypt, get_admin, limiter

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour")
def login():
    """Login page and credential verification endpoint."""
    if current_user.is_authenticated:
        return redirect(url_for("projects.index"))

    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        admin = get_admin()

        # Always run bcrypt to prevent timing-based user enumeration
        _dummy = bcrypt.generate_password_hash("__dummy__").decode()
        check_hash = admin.password_hash if (admin and email == admin.email) else _dummy
        credentials_valid = (
            admin is not None
            and email == admin.email
            and bcrypt.check_password_hash(check_hash, password)
        )

        if credentials_valid:
            login_user(admin, remember=False)
            nxt = request.args.get("next", "")
            from urllib.parse import urlparse
            parsed = urlparse(nxt)
            if nxt and parsed.scheme == "" and parsed.netloc == "" and nxt.startswith("/"):
                return redirect(nxt)
            return redirect(url_for("projects.index"))

        error = "Invalid credentials"

    return render_template("login.html", error=error)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """POST-only logout — prevents logout CSRF via GET requests or embedded images."""
    logout_user()
    return redirect(url_for("auth.login"))

