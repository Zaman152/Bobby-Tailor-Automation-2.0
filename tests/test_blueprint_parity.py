"""Blueprint split parity — URL inventory, auth, and CSRF behavior."""
import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxnRp2./WyH1K8LK7xJQZHQKHQKHQ",
)

from bobbytailor.web.app import create_app

# Pre-split route inventory (41 registrations, 40 unique path patterns)
EXPECTED_PATHS = {
    "/",
    "/login",
    "/logout",
    "/api/projects",
    "/api/projects/refresh",
    "/api/projects/sheet-counts",
    "/api/projects/<int:project_id>/sync-plan-sets",
    "/api/projects/<int:project_id>/plan-sets",
    "/api/projects/<int:project_id>/plan-sets/<int:folder_id>/plans",
    "/api/projects/<int:project_id>/sheet-previews",
    "/api/projects/<int:project_id>/sheet-preview/<int:page_id>",
    "/api/projects/<int:project_id>/sync-plans",
    "/api/projects/<int:project_id>/plans",
    "/api/run/stackct",
    "/api/pdf/upload",
    "/api/pdf/run",
    "/api/pdf/manifest/template",
    "/api/pdf/manifest/upload",
    "/api/run/pdf",
    "/api/status/<job_id>",
    "/api/cancel/<job_id>",
    "/api/jobs/active",
    "/api/jobs/history",
    "/api/jobs/history/<job_id>",
    "/api/reports",
    "/api/reports/<run_folder>",
    "/api/reports/<run_folder>/<filename>",
    "/api/reports/<run_folder>/preview/<filename>",
    "/api/reports/<run_folder>/scale",
    "/api/reports/<run_folder>/sheet-image/<path:relpath>",
    "/api/reports/<run_folder>/measurements",
    "/api/reports/<run_folder>/verify",
    "/api/reports/<run_folder>/verify-batch",
    "/api/reports/<run_folder>/calibrate",
    # "/api/reports/<filename>" removed (21-REVIEW WR-03): the rule was
    # structurally identical to "/api/reports/<run_folder>" and registered
    # second, so it never matched a request — never a live route.
    "/settings",
    "/api/settings",
}

# Sample URLs for unauthenticated auth-guard checks (API → 401, pages → 302)
PROTECTED_API_GETS = [
    "/api/projects",
    "/api/projects/sheet-counts",
    "/api/projects/1/plan-sets",
    "/api/projects/1/plans?folder_id=1",
    "/api/status/fake-job",
    "/api/jobs/active",
    "/api/jobs/history",
    "/api/reports",
    "/api/reports/some_run/scale",
    "/api/reports/some_run/measurements",
    "/api/settings",
    "/api/pdf/manifest/template",
]


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_no_shadowed_duplicate_url_rules(client):
    """WR-03 regression: two structurally identical URL rules mean the
    later-registered one can never match — silent dead endpoint."""
    import re

    def shape(rule_str):
        # Normalize variable NAMES but keep converter TYPES: <run_folder>
        # and <filename> collide; <int:x> and <x> do not.
        return re.sub(
            r"<(?:([^:>]+):)?[^>]+>",
            lambda m: "<%s>" % (m.group(1) or "string"),
            rule_str,
        )

    seen = {}
    for rule in client.application.url_map.iter_rules():
        if rule.rule.startswith("/static"):
            continue
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}:
            key = (shape(rule.rule), method)
            assert key not in seen, (
                f"Shadowed duplicate URL rule: {rule.rule} [{method}] "
                f"collides with {seen[key]}"
            )
            seen[key] = rule.rule


def test_url_map_contains_expected_paths(client):
    rules = {
        str(rule.rule)
        for rule in client.application.url_map.iter_rules()
        if not rule.rule.startswith("/static")
    }
    missing = EXPECTED_PATHS - rules
    assert not missing, f"Missing routes: {sorted(missing)}"
    non_static_rules = [
        r for r in client.application.url_map.iter_rules()
        if not r.rule.startswith("/static")
    ]
    # 40 pre-split registrations minus the dead shadowed legacy download
    # rule removed in 21-REVIEW WR-03.
    assert len(non_static_rules) >= 39


@pytest.mark.parametrize("path", PROTECTED_API_GETS)
def test_protected_api_routes_require_auth(client, path):
    resp = client.get(path)
    assert resp.status_code in (401, 302), (
        f"{path} returned {resp.status_code}, expected 401 or 302"
    )


def test_logout_post_without_csrf_returns_400(client):
    resp = client.post("/logout")
    assert resp.status_code == 400


def test_logout_get_returns_405(client):
    resp = client.get("/logout")
    assert resp.status_code == 405
