"""Flask blueprints for the Bobby Tailor web app."""
from bobbytailor.web.blueprints.auth import auth_bp
from bobbytailor.web.blueprints.jobs import jobs_bp
from bobbytailor.web.blueprints.projects import projects_bp
from bobbytailor.web.blueprints.reports import reports_bp
from bobbytailor.web.blueprints.runs import runs_bp
from bobbytailor.web.blueprints.settings import settings_bp
from bobbytailor.web.blueprints.verify import verify_bp

__all__ = [
    "auth_bp",
    "jobs_bp",
    "projects_bp",
    "reports_bp",
    "runs_bp",
    "settings_bp",
    "verify_bp",
]
