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


# ── Upload hardening (21-REVIEW WR-04) ──────────────────────────────────────

@pytest.fixture
def authed_client():
    """Logged-in test client with CSRF disabled (endpoint behavior tests)."""
    from unittest import mock

    from bobbytailor.web.auth import get_admin

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with mock.patch("flask_login.utils._get_user", return_value=get_admin()):
        yield app.test_client()


def test_max_content_length_is_configured(client):
    from bobbytailor.config import MAX_UPLOAD_MB

    assert client.application.config["MAX_CONTENT_LENGTH"] == MAX_UPLOAD_MB * 1024 * 1024


def test_oversize_upload_rejected_with_413(authed_client):
    import io

    authed_client.application.config["MAX_CONTENT_LENGTH"] = 1024  # 1 KB cap
    resp = authed_client.post(
        "/api/pdf/upload",
        data={"file": (io.BytesIO(b"x" * 4096), "big.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413


def test_upload_filename_is_sanitized_on_disk(authed_client, tmp_path):
    import io
    import os
    from unittest import mock

    from bobbytailor.web import jobs_runtime

    canned_meta = {"page_count": 1, "file_size_bytes": 10, "pages": []}
    with mock.patch(
        "bobbytailor.pipeline.pdf_analyzer.get_pdf_metadata",
        return_value=canned_meta,
    ):
        resp = authed_client.post(
            "/api/pdf/upload",
            data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "../../etc/evil name.pdf")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    upload_id = resp.get_json()["upload_id"]
    try:
        save_path = jobs_runtime.uploads[upload_id]["save_path"]
        # The raw client filename must never dictate directories: the saved
        # file is a single path segment directly under uploads/.
        assert os.path.dirname(save_path) == "uploads"
        assert "/" not in os.path.basename(save_path)
        assert ".." not in save_path
        assert os.path.isfile(save_path)
    finally:
        meta = jobs_runtime.uploads.pop(upload_id, None)
        if meta and os.path.isfile(meta["save_path"]):
            os.remove(meta["save_path"])


# ── Single-active-job guard (21-REVIEW WR-06) ───────────────────────────────

def test_second_concurrent_job_rejected_with_409(authed_client):
    """The scraper pipeline keeps per-run state on a shared singleton —
    overlapping jobs would bleed learned context/manifest between projects.
    A second job while one is queued/running must be refused with 409."""
    import glob
    import io
    import os
    from unittest import mock

    from bobbytailor.web import jobs_runtime

    created = []
    try:
        with mock.patch("bobbytailor.web.blueprints.runs._pdf_job"):
            r1 = authed_client.post(
                "/api/run/pdf",
                data={"file": (io.BytesIO(b"%PDF-1.4"), "first.pdf")},
                content_type="multipart/form-data",
            )
            assert r1.status_code == 200
            first_id = r1.get_json()["job_id"]
            created.append(first_id)

            # First job still queued (worker mocked) → second is refused.
            r2 = authed_client.post(
                "/api/run/pdf",
                data={"file": (io.BytesIO(b"%PDF-1.4"), "second.pdf")},
                content_type="multipart/form-data",
            )
            assert r2.status_code == 409
            assert r2.get_json()["active_job_id"] == first_id

            # The StackCT endpoint honors the same guard.
            r3 = authed_client.post(
                "/api/run/stackct",
                json={"mode": "specific", "project_id": 1, "project_name": "X"},
            )
            assert r3.status_code == 409

            # A finished job frees the slot.
            jobs_runtime.jobs[first_id]["status"] = "done"
            r4 = authed_client.post(
                "/api/run/pdf",
                data={"file": (io.BytesIO(b"%PDF-1.4"), "third.pdf")},
                content_type="multipart/form-data",
            )
            assert r4.status_code == 200
            created.append(r4.get_json()["job_id"])
    finally:
        for jid in created:
            jobs_runtime.jobs.pop(jid, None)
        for pattern in ("*_first.pdf", "*_second.pdf", "*_third.pdf"):
            for leftover in glob.glob(os.path.join("uploads", pattern)):
                os.remove(leftover)


def test_run_pdf_missing_or_uppercase_filename_handled(authed_client):
    import io

    # No filename → clean 400, never an AttributeError 500.
    resp = authed_client.post(
        "/api/run/pdf",
        data={"file": (io.BytesIO(b"%PDF-1.4"), "")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400

    # Uppercase extension is accepted (parity with upload_pdf).
    from unittest import mock

    from bobbytailor.web import jobs_runtime

    with mock.patch("bobbytailor.web.blueprints.runs._pdf_job"):
        resp = authed_client.post(
            "/api/run/pdf",
            data={"file": (io.BytesIO(b"%PDF-1.4"), "PLANS.PDF")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    job_id = resp.get_json()["job_id"]
    jobs_runtime.jobs.pop(job_id, None)
    # Remove the file the endpoint saved.
    import glob
    import os
    for leftover in glob.glob(os.path.join("uploads", "*_PLANS.PDF")):
        os.remove(leftover)
