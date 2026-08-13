"""
Flask web app factory — project selector UI + job runner.
"""
import logging
import os

from flask import Flask, jsonify, redirect, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import HTTPException

from bobbytailor.web.auth import bcrypt, init_admin, limiter, login_manager
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
        SESSION_COOKIE_SECURE=os.getenv("FLASK_ENV") != "development",
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=43200,
        WTF_CSRF_TIME_LIMIT=3600,
        # Upload size cap (WR-04): reject oversize request bodies with 413
        # before they are read to disk/memory (resource-exhaustion guard).
        MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,
    )

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
