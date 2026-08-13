"""The report SCREEN must say what the run's own ledger says.

The pipeline has recorded honest provenance since phase 23 and honest quantity
routes since 28-06. Every one of those records reached ``takeoff.json`` and
``takeoff_summary.csv``, and none of them reached the browser: the worksheet
classified rows from ``source``/``needs_review``/``quantity`` alone.

Replayed against the real saved Crow run, that produced this disagreement —
measured, not asserted, before any of this was written:

    the ledger said     MEASURED 8 · NEEDS REVIEW 11 · NOT MEASURED 31 · STANDARD 1
                        coverage_pct_items 15.7
    the screen said     "9 / 51 line items verified"  (18%)
                        "42 still need review · 31 need a value entered"
                        [Confirm 11 remaining estimates → 100%]

So all 31 rows the run had explicitly recorded as having NO measurement path
rendered as "Needs review", with the cell text **enter value** — indistinguish-
able from a row the estimator had simply not got to yet. That is the inversion
phase 23 exists to prevent, and it is what a bidder was reading.

What is pinned here:

* NOT MEASURED renders as a THIRD state — its own badge class, its own cell
  text, and never counted among the lines waiting on a human.
* The coverage headline is ``coverage_pct_items`` from the run's own ledger,
  used verbatim. Not a ratio this screen invented out of the rows it holds.
* No control offers to convert the take-off to "100%".
* A report written before this vocabulary existed still classifies exactly as
  it did — the same empty contract ``reporter._coverage_lines`` keeps.
* ``coverage.json`` is listed as a downloadable artifact by both report
  endpoints.
* An uploaded filename that reads like a completed take-off is warned about at
  upload AND on the run itself.

The classification rules are exercised by running the shipped
``report-provenance.js`` under node, against the real run's real rows — not by
matching source text. What a reader ends up believing about a blank is a
behaviour, and a string match cannot tell an honest blank from a dishonest one.

FREE: no paid marker, no network, no credential, no golden comparison.
"""
import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxnRp2./WyH1K8LK7xJQZHQKHQKHQ",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC = REPO_ROOT / "src" / "bobbytailor" / "web" / "static"
PROVENANCE_JS = STATIC / "js" / "report-provenance.js"
WORKSPACE_JS = STATIC / "js" / "reports-workspace.js"
APP_JS = STATIC / "app.js"
INDEX_HTML = REPO_ROOT / "src" / "bobbytailor" / "web" / "templates" / "index.html"
HARNESS = REPO_ROOT / "tests" / "js" / "report_provenance_harness.mjs"

#: The real saved Crow run. Read-only; nothing in this module writes to it.
CROW_RUN = (REPO_ROOT / ".planning" / "paid-run-evidence"
            / "VisionOnly_P24DET_Crow_20260806_194607")


# ─── the harness ────────────────────────────────────────────────────────────

def _classify(rows, coverage=None):
    """Run the shipped module over these rows and return what a reader sees."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed — browser-behaviour test skipped")
    proc = subprocess.run(
        [node, str(HARNESS), str(PROVENANCE_JS),
         json.dumps({"rows": rows, "coverage": coverage})],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
    )
    assert proc.returncode == 0, (
        "provenance harness failed:\n%s\n%s" % (proc.stdout, proc.stderr))
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def crow():
    """(takeoff_summary rows, coverage summary) from the real saved run."""
    if not CROW_RUN.is_dir():
        pytest.skip("saved Crow run not present in this checkout")
    takeoff = json.loads((CROW_RUN / "takeoff.json").read_text())
    coverage = json.loads((CROW_RUN / "coverage.json").read_text())
    return takeoff["takeoff_summary"], coverage["summary"]


@pytest.fixture(scope="module")
def crow_view(crow):
    rows, coverage = crow
    return _classify(rows, coverage)


# ─── 1. NOT MEASURED is a third state ───────────────────────────────────────

def test_every_not_measured_row_renders_as_its_own_state(crow_view):
    """31 rows on the real run. Not one may share a badge with NEEDS REVIEW."""
    not_measured = [s for s in crow_view["statuses"]
                    if s["provenance"] == "NOT MEASURED"]
    assert len(not_measured) == 31, (
        "the saved run's ledger records 31 items with no measurement path; the "
        "harness saw %d" % len(not_measured))

    review_classes = {s["cls"] for s in crow_view["statuses"]
                      if s["provenance"] == "NEEDS REVIEW"}
    for s in not_measured:
        assert s["third_state"], "%s is not rendered as the third state" % s["item"]
        assert s["cls"] not in review_classes, (
            "%s (NOT MEASURED) shares the badge class %r with the flagged rows "
            "— the two claims are different and must not look alike"
            % (s["item"], s["cls"]))


def test_a_row_with_no_measurement_path_never_says_enter_value(crow_view):
    """The single most misleading string on the old screen.

    ``enter value`` reads as "you forgot this". A row the app had no
    measurement path for is not a value anyone forgot to type.
    """
    assert crow_view["not_measured_cells"] == ["no measurement path"], (
        "NOT MEASURED cells rendered as %r" % (crow_view["not_measured_cells"],))
    assert crow_view["cells_saying_enter_value"] == [], (
        "these rows still invite the estimator to type a number the app never "
        "claimed was missing: %r" % (crow_view["cells_saying_enter_value"],))


def test_not_measured_rows_are_not_counted_as_lines_awaiting_a_human(crow_view, crow):
    """The screen said 42; the run's own ledger said 11."""
    _, coverage = crow
    assert crow_view["needs_verification_count"] == coverage["items_needs_review"] == 11
    assert crow_view["third_state_count"] == coverage["items_not_measured"] == 31


def test_no_bulk_action_can_reach_a_row_the_app_could_not_measure(crow_view):
    """A bulk confirm may only accept numbers that already exist."""
    assert crow_view["confirmable_count"] == 11
    for s in crow_view["statuses"]:
        if s["third_state"]:
            assert not s["confirmable"], (
                "%s has no measurement path and a bulk confirm offered to "
                "verify it anyway" % s["item"])


def test_the_engines_best_rows_keep_their_green_badge(crow_view):
    """Exposed Structure and Sealed Concrete are the run's two BEST numbers.

    Both are golden PASSes at 0.5% error (``vision_only_benchmark.py:240``
    computes ERR% as an ERROR percentage, which INV-A read as an accuracy).
    They keep the ``ok`` class and the ✓ they have always had; only the WORD
    changed, from "Confirmed" — which claimed a human had signed off on a
    number no human had seen — to "Measured", which is what the ledger says.
    """
    best = {s["item"]: s for s in crow_view["statuses"]
            if s["item"] in ("Exposed Structure", "Sealed Concrete")}
    assert set(best) == {"Exposed Structure", "Sealed Concrete"}
    for item, s in best.items():
        assert s["cls"] == "ok", "%s was demoted to %r" % (item, s["cls"])
        assert s["icon"] == "✓"
        assert s["label"] == "Measured"
        assert not s["third_state"]
        assert not s["needs_verification"]


# ─── 2. the coverage headline is the ledger's own number ────────────────────

def test_the_headline_percentage_is_coverage_pct_items_verbatim(crow_view, crow):
    _, coverage = crow
    facts = crow_view["coverage"]
    assert facts["derived"] is False
    assert facts["pct"] == coverage["coverage_pct_items"] == 15.7
    assert facts["measured"] == 8
    assert facts["needsReview"] == 11
    assert facts["notMeasured"] == 31
    assert facts["standard"] == 1


def test_the_old_headline_ratio_is_not_what_gets_published(crow_view):
    """9/51 = 18% was verified-rows over published-rows.

    Coverage is measured items over EXPECTED items. The two differ by more than
    rounding on this run (18 vs 15.7), and only one of them is a coverage
    figure. Recorded as a test because both are plausible-looking percentages
    and the wrong one is the flattering one.
    """
    assert crow_view["coverage"]["pct"] != 18


def test_a_run_with_no_ledger_never_invents_a_percentage():
    """Derive the counts, refuse to derive the headline."""
    rows = [{"item": "A", "quantity": 3, "provenance": "MEASURED"},
            {"item": "B", "quantity": None, "provenance": "NOT MEASURED"}]
    facts = _classify(rows, None)["coverage"]
    assert facts["derived"] is True
    assert facts["pct"] is None, (
        "a percentage computed from the rows on screen is a different quantity "
        "wearing coverage_pct_items' name")
    assert facts["measured"] == 1 and facts["notMeasured"] == 1


# ─── 3. no control promises 100% ────────────────────────────────────────────

_BANNED_UI_PROMISES = (
    "→ 100%",
    "-> 100%",
    "100% verified",
    "100% confirmed",
    "ws-confirm-all",
    "accept_all_estimates: true, ",   # guard against a re-added silent path
)


def _js_without_comments(path: Path) -> str:
    """Source with whole-line comments dropped.

    The prohibition is on what the SCREEN says. A comment recording what the
    old control was labelled is how the next reader learns why it went, and
    must not itself trip the guard.
    """
    keep = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        keep.append(line)
    return "\n".join(keep)


def test_the_worksheet_offers_no_route_to_a_100_percent_takeoff():
    text = _js_without_comments(WORKSPACE_JS)
    for banned in _BANNED_UI_PROMISES:
        assert banned not in text, (
            "reports-workspace.js still contains %r. On the saved Crow run one "
            "click of that control moved the screen from 18%% to 39%%, never to "
            "100%% — it was a destination the button could not reach and that "
            "the run's 15.7%% coverage did not support." % banned)


def test_the_bulk_confirm_states_what_it_does_not_touch():
    """It survives, scoped and renamed. It must say what it leaves alone."""
    text = WORKSPACE_JS.read_text()
    assert "ws-confirm-flagged" in text
    assert "does NOT touch" in text, (
        "the bulk confirm must tell the operator, at the moment they use it, "
        "that the lines with no measurement path stay blank")


def test_the_coverage_ledger_is_read_from_coverage_json():
    text = WORKSPACE_JS.read_text()
    assert "preview/coverage.json" in text
    assert "coverageFacts" in text


# ─── 4. pre-23 reports still render exactly as they did ─────────────────────

_LEGACY_ROWS = [
    {"item": "verified", "quantity": 5, "source": "user_verified"},
    {"item": "auto", "quantity": 5, "source": "measured_auto", "auto_verified": True},
    {"item": "scale-measured", "quantity": 5, "source": "measured_verified"},
    {"item": "flagged", "quantity": 5, "needs_review": True, "source": "vision"},
    {"item": "blank", "quantity": None, "source": "vision"},
    {"item": "plain", "quantity": 5, "source": "vision"},
]


def test_a_report_written_before_this_vocabulary_classifies_as_it_always_did():
    """The same empty contract the reporter's own sections keep.

    "This row has no measurement path" is a claim only a run that recorded one
    is entitled to make. A pre-23 report recorded nothing, so its blanks stay
    what they were — flagged — rather than being retroactively told apart.
    """
    view = _classify(_LEGACY_ROWS, None)
    labels = {s["item"]: (s["cls"], s["label"]) for s in view["statuses"]}
    assert labels == {
        "verified": ("verified", "Verified"),
        "auto": ("auto", "Auto"),
        "scale-measured": ("measured", "Measured"),
        "flagged": ("review", "Needs review"),
        "blank": ("review", "Needs review"),
        "plain": ("ok", "Confirmed"),
    }
    assert view["has_provenance"] is False
    assert view["third_state_count"] == 0


def test_a_legacy_blank_is_not_promoted_to_not_measured():
    view = _classify([{"item": "blank", "quantity": None, "source": "vision"}], None)
    assert view["not_measured_cells"] == []
    assert view["cells_saying_enter_value"] == ["blank"]


# ─── 5. quantity_route (28-06) reaches the screen ───────────────────────────

_ROUTED_ROWS = [
    {"item": "measured", "quantity": 10, "provenance": "MEASURED",
     "quantity_route": "measured_from_drawing"},
    {"item": "schedule", "quantity": 20, "provenance": "MEASURED",
     "quantity_route": "printed_schedule"},
    {"item": "read", "quantity": 30, "quantity_fmt": "30", "unit": "EA",
     "provenance": "MEASURED", "quantity_route": "sheet_reading"},
    {"item": "unrecognised", "quantity": 40, "provenance": "MEASURED",
     "quantity_route": "something_new"},
]


def test_each_published_row_says_which_route_produced_it():
    view = _classify(_ROUTED_ROWS, None)
    assert view["has_routes"] is True
    by_item = {s["item"]: s for s in view["statuses"]}
    assert by_item["measured"]["route_reproducible"] is True
    assert by_item["schedule"]["route_reproducible"] is True
    assert by_item["read"]["route_reproducible"] is False
    assert by_item["read"]["route_label"] == "model read the sheet"


def test_an_unrecognised_route_is_never_presented_as_reproducible():
    """The same safe floor ``aggregator._less_reproducible_route`` applies.

    A string this code has never seen must rank with the reading route, so a
    future typo cannot silently promote a model reading into a number a reader
    treats as settled.
    """
    view = _classify(_ROUTED_ROWS, None)
    by_item = {s["item"]: s for s in view["statuses"]}
    assert by_item["unrecognised"]["route_reproducible"] is False


def test_the_reproducibility_list_names_the_numbers_a_repeat_run_may_move():
    view = _classify(_ROUTED_ROWS, None)
    assert view["reproducibility_rows"] == ["read"]


def test_a_pre_28_06_run_grows_no_route_column(crow_view):
    """The saved Crow run predates 28-06 and carries no route on any row."""
    assert crow_view["has_routes"] is False
    assert crow_view["reproducibility_rows"] == []


# ─── 6. the vocabularies have not drifted from the pipeline's ───────────────

def _js_consts(path: Path):
    return dict(re.findall(r"export const (\w+) = '([^']*)'", path.read_text()))


def test_the_browser_copy_of_the_item_statuses_matches_the_pipeline():
    from bobbytailor.pipeline import coverage as cov
    js = _js_consts(PROVENANCE_JS)
    assert js["PROV_MEASURED"] == cov.ITEM_MEASURED
    assert js["PROV_HUMAN_INPUT"] == cov.ITEM_HUMAN_INPUT
    assert js["PROV_NEEDS_REVIEW"] == cov.ITEM_NEEDS_REVIEW
    assert js["PROV_NOT_MEASURED"] == cov.ITEM_NOT_MEASURED
    assert js["PROV_NOT_APPLICABLE"] == cov.ITEM_NOT_APPLICABLE
    assert js["PROV_STANDARD"] == cov.ITEM_STANDARD


def test_the_browser_copy_of_the_quantity_routes_matches_the_pipeline():
    from bobbytailor.pipeline import aggregator as agg
    js = _js_consts(PROVENANCE_JS)
    assert js["ROUTE_MEASURED"] == agg.QUANTITY_ROUTE_MEASURED
    assert js["ROUTE_PRINTED_SCHEDULE"] == agg.QUANTITY_ROUTE_PRINTED_SCHEDULE
    assert js["ROUTE_SHEET_READING"] == agg.QUANTITY_ROUTE_SHEET_READING


# ─── 7. coverage.json is a first-class artifact ─────────────────────────────

@pytest.fixture
def client():
    from bobbytailor.web.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False   # the token is covered elsewhere
    return app.test_client()


@pytest.fixture
def run_dir(tmp_path):
    """A minimal run folder, served through the real endpoints."""
    from bobbytailor import config
    out = tmp_path / "output"
    folder = out / "Demo_Project_20260101_120000"
    folder.mkdir(parents=True)
    (folder / "takeoff.json").write_text(json.dumps({
        "project_name": "Demo Project",
        "takeoff_summary": [],
        "coverage": {"coverage_pct_items": 15.7},
    }))
    (folder / "summary.txt").write_text("summary")
    (folder / "coverage.json").write_text(json.dumps({
        "summary": {"items_measured": 8, "items_not_measured": 31,
                    "coverage_pct_items": 15.7},
        "warnings": ["31 expected line item(s) have NO measurement path"],
    }))
    with mock.patch.object(config, "OUTPUT_DIR", str(out)):
        yield folder


def test_both_report_endpoints_offer_coverage_json(client, run_dir):
    from bobbytailor.web.auth import get_admin
    with mock.patch("flask_login.utils._get_user", return_value=get_admin()):
        listing = client.get("/api/reports").get_json()
        single = client.get("/api/reports/%s" % run_dir.name).get_json()

    assert listing["reports"], "the fixture run was not listed"
    assert "coverage_json" in listing["reports"][0]["files"], (
        "coverage.json has been written by every run since phase 23 and was in "
        "neither endpoint's file list, so the record of what a run did NOT "
        "measure was reachable from no button on the page")
    assert "coverage_json" in single["files"]
    assert single["files"]["coverage_json"]["filename"] == "coverage.json"


def test_the_two_file_lists_cannot_drift_apart():
    """They were two hand-maintained copies; that is how coverage.json was
    missed. One tuple now, and this asserts nothing re-forked it."""
    from bobbytailor.web.blueprints import reports as reports_bp
    names = [f for f, _ in reports_bp.RUN_ARTIFACTS]
    assert "coverage.json" in names
    src = (REPO_ROOT / "src" / "bobbytailor" / "web" / "blueprints"
           / "reports.py").read_text()
    assert src.count("(\"takeoff_summary.csv\"") == 1, (
        "a second hardcoded artifact list has reappeared in reports.py")


def test_coverage_json_downloads_and_previews(client, run_dir):
    from bobbytailor.web.auth import get_admin
    with mock.patch("flask_login.utils._get_user", return_value=get_admin()):
        dl = client.get("/api/reports/%s/coverage.json" % run_dir.name)
        pv = client.get("/api/reports/%s/preview/coverage.json" % run_dir.name)
    assert dl.status_code == 200
    assert pv.status_code == 200
    assert pv.get_json()["data"]["summary"]["coverage_pct_items"] == 15.7


def test_the_downloads_panel_links_coverage_json():
    assert "coverage_json" in WORKSPACE_JS.read_text()
    assert "coverage_json" in APP_JS.read_text()
    assert "coverage: 'coverage.json'" in WORKSPACE_JS.read_text()


# ─── 8. unnamed geometry is rendered ────────────────────────────────────────

def test_unnamed_geometry_is_rendered_rather_than_only_stored():
    """34 entries on the saved Crow run, previously rendered nowhere."""
    text = WORKSPACE_JS.read_text()
    assert "unnamed_geometry" in text
    assert "renderUnnamedGeometryPanel" in text
    if CROW_RUN.is_dir():
        takeoff = json.loads((CROW_RUN / "takeoff.json").read_text())
        assert len(takeoff["unnamed_geometry"]) == 34, (
            "the saved run's unnamed-geometry count moved; the panel is fed "
            "straight from this list")


# ─── 9. the plans-only upload guard ─────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "Crow - Cass White Road-Take offs.pdf",
    "crow_takeoff.pdf",
    "Project take-off FINAL.pdf",
    "PROJECT TAKEOFFS.pdf",
    "quantity take off v2.pdf",
])
def test_a_takeoff_shaped_filename_is_recognised(name):
    from bobbytailor.web.blueprints.runs import looks_like_completed_takeoff
    assert looks_like_completed_takeoff(name), name


@pytest.mark.parametrize("name", [
    "Crow - Cass White Road-Plans.pdf",
    "Bob's Discount Furniture - Kennesaw, GA-plans.pdf",
    "A-101 floor plan.pdf",
    "intake form.pdf",          # "take" alone must not fire
    "overtaken.pdf",
])
def test_an_ordinary_plan_set_is_not_warned_about(name):
    from bobbytailor.web.blueprints.runs import looks_like_completed_takeoff
    assert not looks_like_completed_takeoff(name), name


def _upload(client, filename):
    import io
    from bobbytailor.web.auth import get_admin
    pdf = b"%PDF-1.4\n%%EOF\n"
    with mock.patch("flask_login.utils._get_user", return_value=get_admin()), \
         mock.patch("bobbytailor.pipeline.pdf_analyzer.get_pdf_metadata",
                    return_value={"page_count": 1, "file_size_bytes": len(pdf),
                                  "pages": []}):
        return client.post(
            "/api/pdf/upload",
            data={"file": (io.BytesIO(pdf), filename)},
            content_type="multipart/form-data",
        )


def test_uploading_a_takeoff_returns_a_warning_but_still_accepts_the_file(
        client, tmp_path, monkeypatch):
    """WARN, never refuse. "Take-off Plaza - Plans.pdf" is a legitimate upload
    and no filename rule can know that."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    resp = _upload(client, "Crow - Cass White Road-Take offs.pdf")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["upload_id"]
    assert body["plans_only_warning"], (
        "POST /api/pdf/upload accepted a take-off PDF with a bare 200 and the "
        "operator got no signal at all (INV-A §3)")
    assert "TAKE-OFF" in body["plans_only_warning"]


def test_uploading_plans_carries_no_warning(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    body = _upload(client, "Crow - Cass White Road-Plans.pdf").get_json()
    assert body["plans_only_warning"] is None


def test_the_warning_travels_onto_the_run_not_only_the_upload_screen():
    """A dialog leaves no record; the job log does."""
    from bobbytailor.web.blueprints.runs import _plans_only_job_log
    assert _plans_only_job_log("Crow - Cass White Road-Plans.pdf") == []
    entries = _plans_only_job_log("Crow - Cass White Road-Take offs.pdf")
    assert len(entries) == 1
    assert entries[0]["type"] == "warning"
    assert "plans-only" in entries[0]["message"]


def test_both_pdf_entry_points_open_their_job_log_through_the_guard():
    """``/api/run/pdf`` uploads and starts in one step, so it never sees the
    upload screen's warning at all."""
    src = (REPO_ROOT / "src" / "bobbytailor" / "web" / "blueprints"
           / "runs.py").read_text()
    tree = ast.parse(src)
    guarded = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in ("run_pdf", "run_pdf_from_upload"):
            continue
        calls = {n.func.id for n in ast.walk(node)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "_plans_only_job_log" in calls, (
            "%s starts a PDF run without opening its job log through the "
            "plans-only guard" % node.name)
        guarded += 1
    assert guarded == 2


def test_the_upload_form_states_the_plans_only_contract_and_asks_for_a_confirm():
    html = INDEX_HTML.read_text()
    assert "plansOnlyWarning" in html
    assert "plansOnlyAck" in html
    js = APP_JS.read_text()
    assert "plansOnlyBlocksRun" in js
    # The acknowledgement must gate the run itself, not only the button — a
    # disabled attribute is only as good as the last event that set it, and
    # this run spends money.
    assert re.search(r"if \(plansOnlyBlocksRun\(\)\) \{", js), (
        "runPDF must refuse an unacknowledged take-off upload independently of "
        "the button's disabled state")


# ─── this module costs nothing ──────────────────────────────────────────────

def test_this_module_spends_no_money():
    """No paid marker, no network client, no credential — checked on the AST
    so the check cannot trip over its own wording."""
    tree = ast.parse(Path(__file__).read_text())

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & {"requests", "httpx", "urllib", "socket", "anthropic"}), (
        "this module reached for a network client: %r" % (imported,))

    markers = {
        d.attr
        for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        for d in node.decorator_list if isinstance(d, ast.Attribute)
    } | {
        d.func.attr
        for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        for d in node.decorator_list
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
    }
    assert "golden" not in markers
