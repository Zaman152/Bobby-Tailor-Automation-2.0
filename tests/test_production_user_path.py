"""The production user path, end to end, through the Flask test client.

Everything else in this suite tests one track. This module tests that the
tracks COMPOSE, over the one scenario this product actually ships for: an
estimator opens a browser, logs in, uploads a set of PLANS (plus an optional
object manifest), and reads a report. No StackCT, no take-offs, no live server.

Three seams are only visible from here, and each of them was open:

1. **config → create_app.** Day 1 moved environment validation off import and
   onto the surface that reads each variable. Nothing asserted that the web
   surface still boots on a box with NO StackCT credentials at all, which is
   the shipping configuration.
2. **blueprint → static → browser module.** Day 2 put the honesty rules in a
   separate ES module that ``reports-workspace.js`` imports by relative path.
   ``test_report_honesty.py`` runs that module against rows read off DISK. If
   the file stops being SERVED, or ``index.html`` stops loading the workspace
   as ``type="module"``, every one of those green tests stays green and the
   screen renders nothing.
3. **HTTP → classification.** The 31 NOT MEASURED rows have to survive the
   round trip through ``/api/reports/<run>/preview/takeoff.json`` — the actual
   route the browser fetches — and still classify as the third state.

Cost: zero. No paid marker, no API key, no network. ``/api/pdf/run`` is
exercised only on its REFUSAL paths, because the success path starts a real
analysis thread that would call the vision API.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC = REPO_ROOT / "src" / "bobbytailor" / "web" / "static"
PROVENANCE_JS = STATIC / "js" / "report-provenance.js"
HARNESS = REPO_ROOT / "tests" / "js" / "report_provenance_harness.mjs"
INDEX_HTML = REPO_ROOT / "src" / "bobbytailor" / "web" / "templates" / "index.html"

#: The real saved Crow run — read-only, copied out, never written to.
CROW_RUN = (REPO_ROOT / ".planning" / "paid-run-evidence"
            / "VisionOnly_P24DET_Crow_20260806_194607")
CROW_PLANS = REPO_ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"

RUN_FOLDER = "Crow_Cass_White_Road_20260806_194607"

ADMIN_EMAIL = "estimator@production-user-path.test"
ADMIN_PASSWORD = "correct-horse-battery-staple"


# ─── the app, built the way a plans-only box builds it ──────────────────────

@pytest.fixture
def plans_only_app(tmp_path, monkeypatch):
    """``create_app()`` with NO StackCT credentials — the shipping config.

    The admin singleton in ``bobbytailor.web.auth`` is process-global, so it is
    saved and restored: this module logs in for real and must not leave another
    module's admin replaced.
    """
    from bobbytailor import config
    from bobbytailor.web import auth as auth_mod
    from bobbytailor.web.blueprints import reports as reports_mod

    out = tmp_path / "output"
    out.mkdir()
    if CROW_RUN.is_dir():
        shutil.copytree(CROW_RUN, out / RUN_FOLDER)

    monkeypatch.chdir(tmp_path)          # uploads/ is relative to cwd
    monkeypatch.setenv("OUTPUT_DIR", str(out))
    monkeypatch.setattr(config, "OUTPUT_DIR", str(out))
    monkeypatch.setattr(config, "SCREENSHOTS_DIR", str(out / "screenshots"))
    monkeypatch.setattr(reports_mod.config, "OUTPUT_DIR", str(out), raising=False)
    monkeypatch.setenv("SECRET_KEY", "production-user-path-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")   # test client is http
    monkeypatch.delenv("STACKCT_EMAIL", raising=False)
    monkeypatch.delenv("STACKCT_PASSWORD", raising=False)
    monkeypatch.setattr(config, "STACKCT_EMAIL", "", raising=False)
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)

    from flask_bcrypt import Bcrypt
    monkeypatch.setenv(
        "ADMIN_PASSWORD_HASH",
        Bcrypt().generate_password_hash(ADMIN_PASSWORD).decode(),
    )

    previous_admin = auth_mod._admin
    from bobbytailor.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    try:
        yield app, out
    finally:
        auth_mod._admin = previous_admin


def _login(app, client):
    """Log in through the real form, with the real CSRF token.

    Every request carries its own REMOTE_ADDR. The Flask-Limiter instance is a
    session-wide singleton keyed on the client address, so a fixed address
    would make ``5 per minute`` a shared budget across every test in this
    module and turn a real failure into a 429 flake.
    """
    import re
    import uuid

    ip = "10.%d.%d.%d" % (
        uuid.uuid4().int % 250 + 1, uuid.uuid4().int % 250, uuid.uuid4().int % 250)
    base = {"REMOTE_ADDR": ip}
    page = client.get("/login", environ_base=base).get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    resp = client.post(
        "/login",
        data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "csrf_token": token},
        environ_base=base,
    )
    assert resp.status_code == 302, (
        "the real login form did not authenticate: %s" % resp.status_code)
    return base


@pytest.fixture
def browser(plans_only_app):
    """A logged-in client, plus the CSRF token the page hands the JS."""
    import re

    app, out = plans_only_app
    client = app.test_client()
    base = _login(app, client)
    shell = client.get("/", environ_base=base).get_data(as_text=True)
    token = re.search(r'name="csrf-token" content="([^"]+)"', shell).group(1)
    return client, out, {"X-CSRFToken": token}, shell, base


# ─── 1. the box boots, and the door is shut ─────────────────────────────────

def test_the_web_app_boots_with_no_stackct_credentials(plans_only_app):
    """The shipping configuration is plans-only. It must not need a scraper.

    B3 scoped ``validate_required_env`` to the surface that reads each
    variable; this is the assertion that the surface in question still starts
    when the StackCT half of the environment is simply absent.
    """
    app, _ = plans_only_app
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/pdf/upload" in rules and "/api/reports" in rules


def test_an_unauthenticated_browser_reaches_nothing(plans_only_app):
    """Somebody else's quantities are behind the login, on every route."""
    app, _ = plans_only_app
    client = app.test_client()

    page = client.get("/")
    assert page.status_code == 302 and "/login" in page.headers.get("Location", "")

    for url in (
        "/api/reports",
        "/api/reports/%s" % RUN_FOLDER,
        "/api/reports/%s/preview/takeoff.json" % RUN_FOLDER,
        "/api/reports/%s/preview/coverage.json" % RUN_FOLDER,
        "/api/reports/%s/takeoff_summary.csv" % RUN_FOLDER,
    ):
        assert client.get(url).status_code == 401, (
            "%s served report data to an unauthenticated client" % url)


def test_the_real_login_form_authenticates_and_logout_ends_it(plans_only_app):
    """A round trip through the shipped form, CSRF included.

    Every other endpoint test in this suite patches ``_get_user`` and disables
    CSRF. That is the right trade for endpoint behaviour and it means nothing
    exercises the login itself — which is exactly where B4's silent
    redirect-loop lived.
    """
    app, _ = plans_only_app
    client = app.test_client()
    base = _login(app, client)

    assert client.get("/", environ_base=base).status_code == 200
    assert client.get("/api/reports", environ_base=base).status_code == 200

    import re
    shell = client.get("/", environ_base=base).get_data(as_text=True)
    token = re.search(r'name="csrf-token" content="([^"]+)"', shell).group(1)
    assert client.post("/logout", headers={"X-CSRFToken": token},
                       environ_base=base).status_code in (200, 302)
    assert client.get("/api/reports", environ_base=base).status_code == 401


# ─── 2. the report screen's own code is actually served ─────────────────────

def test_every_asset_the_report_screen_imports_is_served(browser):
    """A 404 on the provenance module empties the worksheet, silently.

    ``reports-workspace.js`` imports ``./report-provenance.js`` at module
    load. An ES module import that 404s aborts the whole module — no rows, no
    banner, no error the estimator can read. Nothing else in this suite makes
    an HTTP request for either file.
    """
    client, _, _, shell, base = browser
    for path in ("/static/js/reports-workspace.js",
                 "/static/js/report-provenance.js",
                 "/static/app.js",
                 "/static/style.css"):
        resp = client.get(path, environ_base=base)
        assert resp.status_code == 200, "%s is not served (%s)" % (path, resp.status_code)

    body = client.get("/static/js/reports-workspace.js",
                      environ_base=base).get_data(as_text=True)
    assert "./report-provenance.js" in body, (
        "the workspace no longer imports the provenance module by the relative "
        "path this test resolved against /static/js/")


def test_the_page_serves_the_controller_the_shell_depends_on(browser):
    """The shell is inert without its controller, and a 404 here is silent.

    The v2 UI replaced the ES-module workspace with a single classic script, so
    the old `type="module"` assertion no longer describes anything. What still
    matters is unchanged: the page must REFERENCE its controller and the server
    must SERVE it. A shell that loads with a broken script tag renders a static
    skeleton — every button dead — and nothing on screen says so.
    """
    client, _, _, shell, _ = browser
    tag = [line for line in shell.splitlines() if "v2/app.js" in line]
    assert tag, "index.html no longer loads the v2 controller"
    served = client.get("/static/v2/app.js")
    assert served.status_code == 200, "the controller 404s; the shell would be inert"
    body = served.get_data(as_text=True)
    assert "addEventListener" in body and "/api/pdf/upload" in body


def test_the_upload_form_states_the_plans_only_contract(browser):
    """The contract belongs on the screen, not only in the docs."""
    _, _, _, shell, _ = browser
    # Matched on the CLAIM rather than on any one phrasing: the v2 shell states
    # it in the page head and again on the upload card, and a redesign that
    # keeps the words but drops the meaning should still fail here.
    assert "not a completed take-off" in shell, (
        "the plans-only contract is no longer stated on the upload screen")
    assert "cannot tell a finished take-off apart" in shell, (
        "the screen no longer says WHY it matters, only that it does")


# ─── 3. uploading ───────────────────────────────────────────────────────────

@pytest.mark.skipif(not CROW_PLANS.is_file(), reason="Crow plans fixture absent")
def test_a_plan_set_uploads_and_returns_the_page_picker(browser):
    client, _, headers, _, base = browser
    resp = client.post(
        "/api/pdf/upload",
        data={"file": (io.BytesIO(CROW_PLANS.read_bytes()),
                       "Crow - Cass White Road - Plans.pdf")},
        content_type="multipart/form-data", headers=headers, environ_base=base,
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["page_count"] > 0
    assert len(body["pages"]) == body["page_count"]
    assert body["plans_only_warning"] in (None, ""), (
        "a file named '... - Plans.pdf' must not be warned about")


@pytest.mark.skipif(not CROW_PLANS.is_file(), reason="Crow plans fixture absent")
def test_a_takeoff_named_file_uploads_with_the_warning(browser):
    """Warn, never refuse — the guard is the sign on the door (Day 2 2.6)."""
    client, _, headers, _, base = browser
    resp = client.post(
        "/api/pdf/upload",
        data={"file": (io.BytesIO(CROW_PLANS.read_bytes()),
                       "Crow - Cass White Road-Take offs.pdf")},
        content_type="multipart/form-data", headers=headers, environ_base=base,
    )
    assert resp.status_code == 200
    assert "TAKE-OFF" in (resp.get_json().get("plans_only_warning") or "")


def test_a_corrupt_pdf_is_refused_with_a_message_the_operator_can_act_on(browser):
    """It used to be ``Error: Internal server error``.

    A file that will not open is the user's file, not a server fault. The 500
    told an estimator to call support; the actual remedy is to re-export the
    drawing set. Found by driving this path end to end — every unit test of
    ``/api/pdf/upload`` mocks ``get_pdf_metadata`` and so never meets a real
    unreadable file.
    """
    from bobbytailor.web.blueprints.runs import UNREADABLE_PDF_ERROR

    client, _, headers, _, base = browser
    resp = client.post(
        "/api/pdf/upload",
        data={"file": (io.BytesIO(b"not a pdf at all\n" * 40), "scan.pdf")},
        content_type="multipart/form-data", headers=headers, environ_base=base,
    )
    assert resp.status_code == 400, (
        "an unreadable PDF still escapes as %s" % resp.status_code)
    assert resp.get_json()["error"] == UNREADABLE_PDF_ERROR


def test_a_password_protected_pdf_names_the_password(browser, tmp_path):
    """Encryption and corruption need different remedies, so they get different words.

    Measured rather than assumed: on this PyMuPDF a corrupt file raises
    ``FileDataError`` from ``fitz.open`` while an encrypted one opens and
    raises ``ValueError: document closed or encrypted`` on first page access.
    The exception type alone cannot tell the operator which they have.
    """
    fitz = pytest.importorskip("fitz")
    from bobbytailor.web.blueprints.runs import ENCRYPTED_PDF_ERROR

    locked = tmp_path / "locked.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "A-101 FLOOR PLAN")
    doc.save(str(locked), encryption=fitz.PDF_ENCRYPT_AES_256,
             owner_pw="owner", user_pw="user")
    doc.close()

    client, _, headers, _, base = browser
    resp = client.post(
        "/api/pdf/upload",
        data={"file": (io.BytesIO(locked.read_bytes()), "locked.pdf")},
        content_type="multipart/form-data", headers=headers, environ_base=base,
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == ENCRYPTED_PDF_ERROR


def test_a_refused_upload_leaves_no_orphan_on_disk(browser):
    """The file is saved before it can be read. A refusal must clean up."""
    client, _, headers, _, base = browser
    before = set(Path("uploads").glob("*")) if Path("uploads").is_dir() else set()
    client.post(
        "/api/pdf/upload",
        data={"file": (io.BytesIO(b"%PDF-1.4 truncated"), "half.pdf")},
        content_type="multipart/form-data", headers=headers, environ_base=base,
    )
    after = set(Path("uploads").glob("*")) if Path("uploads").is_dir() else set()
    assert after == before, "refused upload left %s behind" % sorted(after - before)


def test_the_object_manifest_uploads_and_returns_a_usable_id(browser):
    """The optional half of the product contract, over HTTP."""
    client, _, headers, _, base = browser

    assert client.get("/api/pdf/manifest/template",
                      environ_base=base).status_code == 200

    csv = b"name,unit,measure\nCMU Wall,SF,area\nBollards,EA,count\n"
    resp = client.post(
        "/api/pdf/manifest/upload",
        data={"file": (io.BytesIO(csv), "manifest.csv")},
        content_type="multipart/form-data", headers=headers, environ_base=base,
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["manifest_id"] and body["count"] == 2


def test_the_run_endpoint_refuses_rather_than_starting_an_unguided_run(browser):
    """Refusal paths only. The success path spends money.

    A manifest the operator selected and the server cannot find must stop the
    run: starting it anyway produces a report the operator believes was
    manifest-guided.
    """
    client, _, headers, _, base = browser

    assert client.post("/api/pdf/run", json={"project_name": "X"},
                       headers=headers, environ_base=base).status_code == 400
    assert client.post("/api/pdf/run", json={"upload_id": "deadbeef"},
                       headers=headers, environ_base=base).status_code == 404


# ─── 4. reading the report ──────────────────────────────────────────────────

@pytest.fixture
def crow_report(browser):
    """The saved run, fetched the way the browser fetches it."""
    if not CROW_RUN.is_dir():
        pytest.skip("saved Crow run not present in this checkout")
    client, _, _, _, base = browser

    listing = client.get("/api/reports", environ_base=base)
    assert listing.status_code == 200
    card = next(r for r in listing.get_json()["reports"]
                if r["run_folder"] == RUN_FOLDER)

    detail = client.get("/api/reports/%s" % RUN_FOLDER, environ_base=base)
    assert detail.status_code == 200

    takeoff = client.get("/api/reports/%s/preview/takeoff.json" % RUN_FOLDER,
                         environ_base=base)
    coverage = client.get("/api/reports/%s/preview/coverage.json" % RUN_FOLDER,
                          environ_base=base)
    assert takeoff.status_code == 200 and coverage.status_code == 200
    return {
        "client": client, "base": base,
        "card": card, "detail": detail.get_json(),
        "takeoff": takeoff.get_json()["data"],
        "coverage": coverage.get_json()["data"],
    }


def test_coverage_json_is_listed_by_both_report_endpoints(crow_report):
    """It was written by every run since phase 23 and offered by neither.

    The two endpoints used to carry two hand-maintained copies of the artifact
    tuple, which is how it was missed. This asserts the composed result rather
    than the shared constant.
    """
    assert "coverage_json" in crow_report["card"]["files"]
    assert "coverage_json" in crow_report["detail"]["files"]


def test_every_listed_artifact_actually_downloads(crow_report):
    client, base = crow_report["client"], crow_report["base"]
    for key, entry in crow_report["card"]["files"].items():
        resp = client.get("/api/reports/%s/%s" % (RUN_FOLDER, entry["filename"]),
                          environ_base=base)
        assert resp.status_code == 200, "%s (%s) does not download" % (key, entry)
        assert len(resp.data) == entry["size"]


def test_a_run_folder_cannot_be_escaped(crow_report):
    client, base = crow_report["client"], crow_report["base"]
    for url in ("/api/reports/%s/preview/..%%2fsecrets.json" % RUN_FOLDER,
                "/api/reports/%s/preview/notes.exe" % RUN_FOLDER,
                "/api/reports/%s/..%%2f..%%2fetc%%2fpasswd" % RUN_FOLDER):
        assert client.get(url, environ_base=base).status_code in (400, 404), url


# ─── 5. NOT MEASURED survives the round trip ────────────────────────────────

def _classify(rows, coverage):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed — browser-behaviour test skipped")
    proc = subprocess.run(
        [node, str(HARNESS), str(PROVENANCE_JS),
         json.dumps({"rows": rows, "coverage": coverage})],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
    )
    assert proc.returncode == 0, "%s\n%s" % (proc.stdout, proc.stderr)
    return json.loads(proc.stdout)


@pytest.fixture
def served_view(crow_report):
    """What the browser renders from what the SERVER sent it."""
    return _classify(crow_report["takeoff"]["takeoff_summary"],
                     crow_report["coverage"]["summary"])


def test_not_measured_is_a_distinct_third_state_on_the_served_rows(served_view):
    """The whole product contract, in one assertion, over the real route.

    ``test_report_honesty.py`` proves this against rows read off disk. This
    proves it against the bytes ``/api/reports/<run>/preview/takeoff.json``
    actually returned — the JSON round trip, the preview wrapper and the
    classifier composed.
    """
    not_measured = [s for s in served_view["statuses"]
                    if s["provenance"] == "NOT MEASURED"]
    assert not_measured, "the served run carries no NOT MEASURED rows to check"

    review_classes = {s["cls"] for s in served_view["statuses"]
                      if s["provenance"] == "NEEDS REVIEW"}
    for s in not_measured:
        assert s["third_state"], "%s is not the third state" % s["item"]
        assert s["cls"] not in review_classes, (
            "%s shares a badge with the flagged rows" % s["item"])
        assert s["cell"] == "no measurement path", (
            "%s renders %r — a blank the app could not measure must never read "
            "as one somebody forgot to type" % (s["item"], s["cell"]))
        assert not s["needs_verification"]


def test_the_screen_reproduces_the_served_ledger_rather_than_recomputing_it(
        served_view, crow_report):
    """The headline the customer reads first is the run's own number.

    Not a ratio derived from the rows on screen: that is a different quantity
    wearing ``coverage_pct_items``' name.
    """
    ledger = crow_report["coverage"]["summary"]
    facts = served_view["coverage"]

    assert facts["derived"] is False
    assert facts["pct"] == ledger["coverage_pct_items"]
    assert facts["notMeasured"] == ledger["items_not_measured"]
    assert facts["needsReview"] == ledger["items_needs_review"]
    assert served_view["needs_verification_count"] == ledger["items_needs_review"], (
        "the screen presents %d lines as awaiting a human; the run's ledger "
        "says %d" % (served_view["needs_verification_count"],
                     ledger["items_needs_review"]))
    assert served_view["third_state_count"] == ledger["items_not_measured"]


def test_no_served_row_with_no_measurement_path_says_enter_value(served_view):
    """``enter value`` on a NOT MEASURED row is the defect, stated directly."""
    assert served_view["not_measured_cells"] == ["no measurement path"], (
        "NOT MEASURED rows render %s" % served_view["not_measured_cells"])


# ─── 6. this module costs nothing ───────────────────────────────────────────

def test_this_module_spends_no_money():
    """A paid token in the deployment gate would be a trap for the next run."""
    text = Path(__file__).read_text()
    key = "ANTHROPIC" + "_API_KEY"
    for token in (key, "accuracy" + "_gate", "vision_only" + "_benchmark",
                  "golden" + "_convergence", "pytest.mark." + "golden"):
        assert token not in text, "%s appears in the free user-path gate" % token
