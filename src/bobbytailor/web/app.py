"""
Flask web app factory — project selector UI + job runner.
"""
import logging
import os
from pathlib import Path

from flask import Flask, jsonify, redirect, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import HTTPException

from bobbytailor.web.auth import bcrypt, init_admin, limiter, login_manager
from bobbytailor.config import MAX_UPLOAD_MB, OUTPUT_DIR
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
    repo_root = Path(__file__).resolve().parents[3]
    app = Flask(
        __name__,
        template_folder=str(repo_root / "templates"),
        static_folder=str(repo_root / "static"),
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
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
