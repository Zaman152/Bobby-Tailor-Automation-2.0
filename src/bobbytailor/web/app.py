"""
Flask web app factory — project selector UI + job runner.
"""
import logging
import os

from flask import Flask, jsonify, redirect, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from bobbytailor.web.auth import bcrypt, init_admin, limiter, login_manager
# Imported as a MODULE, not by-value: whether this box scrapes at all is a
# runtime decision made below, and `from ... import STACKCT_EMAIL` would freeze
# the answer at import time and make it untestable.
from bobbytailor import config
from bobbytailor.config import (
    MAX_UPLOAD_MB,
    OUTPUT_DIR,
    VISION_REQUIRED_ENV_VARS,
    WEB_REQUIRED_ENV_VARS,
    missing_env,
    validate_required_env,
)
from bobbytailor.web.blueprints import (
    auth_bp,
    jobs_bp,
    projects_bp,
    reports_bp,
    runs_bp,
    settings_bp,
    verify_bp,
)

logger = logging.getLogger(__name__)

PUBLIC_ENDPOINTS: frozenset = frozenset({"auth.login", "auth.logout", "static"})

_FALSEY = frozenset({"0", "false", "no", "off"})


def _session_cookie_secure() -> bool:
    """Whether the session cookie is marked Secure (HTTPS-only).

    Defaults to True, and that default is correct: a session cookie sent in
    clear text is a hijackable credential.

    But the failure mode when it is wrong is silent and total. Over plain HTTP
    the browser accepts the Secure cookie and then never sends it back, so
    /login reports success and every subsequent request redirects to /login
    again — forever, with no error logged anywhere and nothing on screen to
    explain it. The only escape used to be FLASK_ENV=development, a name no
    operator would guess and nobody should set in production just to reach a
    login form.

    So: an explicit, obviously-named opt-out (SESSION_COOKIE_SECURE=false) for
    the operator who genuinely controls the network path — an SSH tunnel to
    127.0.0.1, a local dev box. FLASK_ENV=development still works so existing
    setups do not break. TLS remains the documented, supported answer; see the
    README "Production — TLS is REQUIRED" section.
    """
    explicit = os.getenv("SESSION_COOKIE_SECURE")
    if explicit is not None and explicit.strip():
        return explicit.strip().lower() not in _FALSEY
    return os.getenv("FLASK_ENV") != "development"


def create_app() -> Flask:
    """Create and configure the Flask application."""
    # templates/ and static/ live inside this package, so Flask's default
    # resolution (relative to app.root_path == src/bobbytailor/web/) finds them.
    app = Flask(__name__)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Env validation is scoped to the surface being started, and this is the
    # web surface. It used to run at `import bobbytailor.config`, which made
    # StackCT credentials a precondition for importing the package on a
    # plans-only install (see config.py). Checked HERE the failure is named,
    # attributable, and confined to the app that actually needs the values —
    # rather than an unexplained crash on the first import in a container.
    #
    # These three are hard requirements: os.environ[...] below would raise a
    # bare KeyError naming one variable at a time; this names all of them at
    # once and says where to put them.
    validate_required_env(WEB_REQUIRED_ENV_VARS)

    # ANTHROPIC_API_KEY is deliberately a WARNING, not a refusal to boot. The
    # deterministic offline path is a legitimate way to run this product, and
    # crash-failing here would take it away from anyone who has not yet bought
    # API credit. The cost of the softer check is that a missing key surfaces
    # as a failed vision call mid-run instead of at startup — hence the log
    # line, which is what makes that later failure diagnosable.
    absent = missing_env(VISION_REQUIRED_ENV_VARS)
    if absent:
        logger.warning(
            "%s not set — deterministic/offline analysis will still run, but "
            "any vision pass will fail mid-run. Set it in .env or through "
            "Settings before starting a paid run.",
            ", ".join(absent),
        )

    app.config.update(
        SECRET_KEY=os.environ["SECRET_KEY"],
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=_session_cookie_secure(),
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=43200,
        WTF_CSRF_TIME_LIMIT=3600,
        # Upload size cap (WR-04): reject oversize request bodies with 413
        # before they are read to disk/memory (resource-exhaustion guard).
        MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,
    )

    # The supported deployment puts nginx in front of gunicorn, so without
    # this every request appears to originate from 127.0.0.1. Two things break
    # quietly as a result:
    #
    #   * the login rate limit keys on get_remote_address(), so "5 per minute;
    #     20 per hour" becomes a GLOBAL limit — one attacker, or one operator
    #     fat-fingering a password, locks out the only account on the box;
    #   * Flask-Login's session_protection="strong" compares the client IP
    #     between requests, and a constant 127.0.0.1 makes that check inert.
    #
    # x_for=1 / x_proto=1: trust exactly ONE hop, the nginx we document. Any
    # larger number would let a client forge its own X-Forwarded-For and
    # sidestep the rate limit entirely.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    csrf = CSRFProtect(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.session_protection = "strong"
    bcrypt.init_app(app)
    limiter.init_app(app)

    init_admin(
        email=os.environ["ADMIN_EMAIL"],
        password_hash=os.environ["ADMIN_PASSWORD_HASH"],
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs("output/screenshots", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)

    from bobbytailor.stores import stackct_store
    from bobbytailor.stores import job_store

    stackct_store.init_db()
    job_store.init_schema()

    # Both of these exist to keep the StackCT project catalog warm, and both
    # reach StackCT over the network: prefetch_in_background() spawns a
    # Playwright/Chromium Auth0 login whenever the catalog DB is empty, and
    # the scheduler repeats that every STACKCT_CACHE_TTL_HOURS.
    #
    # On a plans-only install there is no StackCT account, so what they
    # actually produce is a recurring failed third-party login from the
    # operator's box — plus a `playwright install chromium` that the install
    # docs demand for a deployment that never scrapes. Gate both on the
    # credential that decides whether this box scrapes at all.
    if config.STACKCT_EMAIL:
        from bobbytailor.stores.project_cache import prefetch_in_background

        prefetch_in_background()

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from bobbytailor.config import STACKCT_CACHE_TTL_HOURS
            from bobbytailor.scrape.stackct_sync import sync_projects_if_stale

            scheduler = BackgroundScheduler(daemon=True)
            scheduler.add_job(
                sync_projects_if_stale,
                "interval",
                hours=STACKCT_CACHE_TTL_HOURS,
                id="stackct_projects_sync",
                replace_existing=True,
            )
            scheduler.start()
            logger.info(
                "StackCT catalog scheduler started (interval=%sh)",
                STACKCT_CACHE_TTL_HOURS,
            )
        except Exception as e:
            logger.warning("APScheduler catalog sync not started: %s", e)
    else:
        logger.info(
            "STACKCT_EMAIL not set — skipping StackCT catalog prefetch and "
            "the periodic sync. This is the expected plans-only "
            "configuration; PDF upload and analysis are unaffected."
        )

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        return jsonify({"error": e.name, "message": e.description}), e.code

    @app.errorhandler(Exception)
    def handle_exception(e: Exception):
        logger.error("Unhandled exception in route", exc_info=True)
        return jsonify({
            "error": "Internal server error",
            "message": "An unexpected error occurred",
        }), 500

    @app.before_request
    def require_login():
        if not request.endpoint or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("auth.login", next=request.path))

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(runs_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(verify_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(jobs_bp)

    return app
