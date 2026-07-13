"""
Authentication module — Flask-Login, Flask-Bcrypt, Flask-Limiter setup.

Exports:
    AdminUser       — UserMixin model for the single admin account
    login_manager   — LoginManager instance (call init_app in app.py)
    bcrypt          — Bcrypt instance (call init_app in app.py)
    limiter         — Limiter instance (call init_app in app.py)
    init_admin      — Populate the in-process singleton from env vars
    get_admin       — Return the singleton AdminUser (or None)
"""

import logging
import os
from typing import Optional

from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, UserMixin

logger = logging.getLogger(__name__)

# ── Extension instances (not yet bound to an app) ────────────────────────────

login_manager: LoginManager = LoginManager()

bcrypt: Bcrypt = Bcrypt()

limiter: Limiter = Limiter(
    get_remote_address,
    default_limits=[],
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
)


# ── AdminUser model ───────────────────────────────────────────────────────────

class AdminUser(UserMixin):
    """Single-admin user model backed by environment credentials.

    Flask-Login requires `get_id()` which UserMixin derives from `self.id`.
    """

    def __init__(self, user_id: str, email: str, password_hash: str) -> None:
        """Initialise the admin user with immutable credentials.

        Args:
            user_id:       Stable string ID used by Flask-Login's user_loader.
            email:         Lower-cased admin email address.
            password_hash: bcrypt hash ($2b$…) loaded from environment.
        """
        self.id: str = user_id
        self.email: str = email
        self.password_hash: str = password_hash


# ── Singleton store ───────────────────────────────────────────────────────────

_admin: Optional[AdminUser] = None


def init_admin(email: str, password_hash: str) -> None:
    """Populate the in-process AdminUser singleton from env-supplied credentials.

    Called once at app startup after extensions are init_app'd.

    Args:
        email:         Raw ADMIN_EMAIL value from environment.
        password_hash: Raw ADMIN_PASSWORD_HASH bcrypt string from environment.

    Raises:
        ValueError: If either argument is empty/None.
    """
    global _admin
    if not email or not password_hash:
        raise ValueError("ADMIN_EMAIL and ADMIN_PASSWORD_HASH must be set")
    _admin = AdminUser(
        user_id="1",
        email=email.strip().lower(),
        password_hash=password_hash,
    )
    logger.info("Admin user initialised: %s", email)


def get_admin() -> Optional[AdminUser]:
    """Return the singleton AdminUser or None if not yet initialised.

    Returns:
        AdminUser instance, or None before init_admin() is called.
    """
    return _admin


# ── Flask-Login user loader ───────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id: str) -> Optional[AdminUser]:
    """Reload the user object from the session-stored user_id.

    Flask-Login calls this on every request where a session exists.

    Args:
        user_id: String user ID stored in the session cookie.

    Returns:
        AdminUser if the ID matches the singleton, otherwise None.
    """
    admin = get_admin()
    return admin if (admin and admin.id == user_id) else None
