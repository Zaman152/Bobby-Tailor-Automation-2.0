"""The browser-uploaded manifest must reach the pipeline. Nothing tested this.

The object manifest is half the product contract: it is how an operator tells
the engine which objects exist in a drawing set, and the plans-only run is
scored against it. A user attaches it in the browser, which means the value
travels:

    POST /api/pdf/manifest/upload   -> file saved, manifest_id minted
    object_manifests[manifest_id]   -> {"path": <file on disk>, ...}
    POST /api/pdf/run {object_manifest_id}
                                    -> manifest_path
    _pdf_job(..., manifest_path)    -> run_pdf_analysis(manifest_path=...)

Before this module, `grep -r object_manifest_id tests/` returned nothing. Every
hop above was uncovered — the manifest could stop arriving in a refactor and
every existing test would stay green, while runs quietly scored against no
manifest at all. That is a silent-wrong-answer failure, not a crash, which is
the kind this codebase is least able to notice.

What is pinned here is the WIRING, not the parsing (tests/test_object_manifest.py
owns the loader). No paid API, no network, no golden comparison: the pipeline
call itself is intercepted and its arguments inspected.
"""
import json
import os
from pathlib import Path
from unittest import mock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxnRp2./WyH1K8LK7xJQZHQKHQKHQ",
)

from bobbytailor.web.app import create_app  # noqa: E402


MANIFEST_CSV = (
    "name,unit,measure\n"
    "Columns - H-35',EA,count\n"
    "Ladder - H-20',EA,count\n"
    "Internal Tilt up walls,SF,area\n"
)


@pytest.fixture
def authed_client(tmp_path, monkeypatch):
    """Logged-in client with uploads/ redirected into a temp dir.

    The endpoints write to a relative "uploads/" path, so the cwd is moved
    rather than the constant patched — that is the behaviour a deployment
    actually has (uploads follow CWD; see docs/DEPLOYMENT.md).
    """
    from bobbytailor import config
    from bobbytailor.web.auth import get_admin

    (tmp_path / "uploads").mkdir()
    monkeypatch.chdir(tmp_path)

    # The plans-only configuration, which is the one these tests are about:
    # no StackCT account, so create_app skips the catalog prefetch. Without
    # this, boot reaches for a cwd-relative stackct.db that the chdir above
    # just moved out from under an already-"initialised" store.
    monkeypatch.setattr(config, "STACKCT_EMAIL", "")

    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with mock.patch("flask_login.utils._get_user", return_value=get_admin()):
        yield app.test_client()


@pytest.fixture(autouse=True)
def _clean_runtime_state():
    """The runtime dicts are module-level and shared across tests."""
    from bobbytailor.web import jobs_runtime

    jobs_runtime.uploads.clear()
    jobs_runtime.object_manifests.clear()
    jobs_runtime.jobs.clear()
    yield
    jobs_runtime.uploads.clear()
    jobs_runtime.object_manifests.clear()
    jobs_runtime.jobs.clear()


def _upload_manifest(client, content=MANIFEST_CSV, filename="manifest.csv"):
    import io

    return client.post(
        "/api/pdf/manifest/upload",
        data={"file": (io.BytesIO(content.encode()), filename)},
        content_type="multipart/form-data",
    )


def _register_upload(pdf_name="plans.pdf"):
    """Put a PDF in the uploads dict the way /api/pdf/upload would."""
    from bobbytailor.web import jobs_runtime

    path = Path("uploads") / pdf_name
    path.write_bytes(b"%PDF-1.4\n%stub\n")
    jobs_runtime.uploads["upload-1"] = {
        "save_path": str(path),
        "filename": pdf_name,
        "pages": 4,
    }
    return str(path)


# ── hop 1: upload → a manifest_id backed by a real file ─────────────────────

def test_uploading_a_manifest_records_a_path_that_exists(authed_client):
    resp = _upload_manifest(authed_client)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    body = resp.get_json()
    manifest_id = body["manifest_id"]
    assert body["count"] == 3

    from bobbytailor.web import jobs_runtime

    entry = jobs_runtime.object_manifests[manifest_id]
    assert os.path.isfile(entry["path"]), (
        "the manifest_id points at %r, which is not on disk — the pipeline "
        "would be handed a path it cannot read" % entry["path"]
    )


def test_a_json_manifest_is_accepted_too(authed_client):
    """The loader handles both, and the endpoint advertises both."""
    payload = json.dumps([
        {"name": "Bollards", "unit": "EA", "measure": "count"},
    ])
    resp = _upload_manifest(authed_client, payload, "manifest.json")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["count"] == 1


def test_a_manifest_with_an_unsupported_extension_is_refused(authed_client):
    resp = _upload_manifest(authed_client, MANIFEST_CSV, "manifest.txt")
    assert resp.status_code == 400
    assert "csv" in resp.get_json()["error"].lower()


# ── hop 2: object_manifest_id → manifest_path, into the job thread ──────────

def _run_with_manifest(client, manifest_id, capture):
    """POST /api/pdf/run and capture the args _pdf_job is started with."""
    def fake_thread(target=None, args=(), daemon=None, **kwargs):
        capture["target"] = target
        capture["args"] = args

        class _Stub:
            def start(self_inner):
                capture["started"] = True

        return _Stub()

    payload = {"upload_id": "upload-1", "project_name": "Crow"}
    if manifest_id is not None:
        payload["object_manifest_id"] = manifest_id

    with mock.patch("bobbytailor.web.blueprints.runs.threading.Thread", fake_thread):
        return client.post("/api/pdf/run", json=payload)


def test_the_manifest_id_becomes_the_manifest_path_the_job_receives(authed_client):
    """THE hop. `object_manifest_id` is what the browser sends;
    `manifest_path` is what the pipeline consumes. Nothing connected them in
    a test, so nothing would have noticed them coming apart."""
    _register_upload()
    manifest_id = _upload_manifest(authed_client).get_json()["manifest_id"]

    from bobbytailor.web import jobs_runtime

    expected_path = jobs_runtime.object_manifests[manifest_id]["path"]

    capture = {}
    resp = _run_with_manifest(authed_client, manifest_id, capture)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert capture.get("started"), "the analysis thread was never started"

    # _pdf_job(job_id, pdf_path, project_name, selected_pages, manifest_path)
    args = capture["args"]
    assert len(args) == 5, (
        "_pdf_job's signature changed to %d positional args — the manifest is "
        "passed positionally, so a reordering here silently swaps it with "
        "selected_pages" % len(args)
    )
    assert args[4] == expected_path, (
        "the job was started with manifest_path=%r, but the uploaded manifest "
        "lives at %r — the operator's manifest would be ignored and the run "
        "would score against nothing" % (args[4], expected_path)
    )
    assert os.path.isfile(args[4])


def test_the_path_handed_to_the_job_is_loadable_by_the_pipeline(authed_client):
    """A path that exists is not enough — it has to be the manifest the user
    uploaded, parseable by the same loader the pipeline uses."""
    from bobbytailor.devtools.object_manifest import load_manifest

    _register_upload()
    manifest_id = _upload_manifest(authed_client).get_json()["manifest_id"]

    capture = {}
    _run_with_manifest(authed_client, manifest_id, capture)

    manifest = load_manifest(capture["args"][4])
    names = [e.name for e in manifest.entries]
    assert "Columns - H-35'" in names, (
        "the file the pipeline will read is not the manifest that was "
        "uploaded; got %r" % names
    )
    assert len(manifest) == 3


def test_the_job_record_reports_the_manifest_count_to_the_ui(authed_client):
    """The count is how the operator confirms the attachment took effect —
    the only feedback that the manifest is in play at all."""
    _register_upload()
    manifest_id = _upload_manifest(authed_client).get_json()["manifest_id"]

    capture = {}
    resp = _run_with_manifest(authed_client, manifest_id, capture)
    job_id = resp.get_json()["job_id"]

    from bobbytailor.web import jobs_runtime

    assert jobs_runtime.jobs[job_id]["object_manifest_count"] == 3


# ── the negative halves: absent, unknown, and vanished manifests ────────────

def test_a_run_without_a_manifest_passes_none_not_a_stale_path(authed_client):
    """Plans-only with no manifest is a supported run. It must not inherit
    whatever manifest happened to be uploaded earlier in the session."""
    _register_upload()
    _upload_manifest(authed_client)   # present in the dict, deliberately unused

    capture = {}
    resp = _run_with_manifest(authed_client, None, capture)
    assert resp.status_code == 200

    assert capture["args"][4] is None, (
        "a run with no object_manifest_id was handed %r — a manifest the user "
        "did not attach would silently shape the results"
        % (capture["args"][4],)
    )


def test_an_unknown_manifest_id_is_refused_rather_than_ignored(authed_client):
    """Refusing is the whole point: silently dropping an unrecognised id
    starts a PAID run whose results the operator believes were
    manifest-guided."""
    _register_upload()

    capture = {}
    resp = _run_with_manifest(authed_client, "does-not-exist", capture)

    assert resp.status_code == 404, (
        "an unknown manifest id produced %s — the run must not start"
        % resp.status_code
    )
    assert "manifest" in resp.get_json()["error"].lower()
    assert not capture.get("started"), "a job was started despite the refusal"


def test_a_manifest_whose_file_vanished_is_refused(authed_client):
    """The id lives in memory and the file lives on disk; a restart, a tmp
    sweep, or a redeploy can separate them."""
    _register_upload()
    manifest_id = _upload_manifest(authed_client).get_json()["manifest_id"]

    from bobbytailor.web import jobs_runtime

    os.remove(jobs_runtime.object_manifests[manifest_id]["path"])

    capture = {}
    resp = _run_with_manifest(authed_client, manifest_id, capture)

    assert resp.status_code == 404
    assert not capture.get("started"), (
        "a job started with a manifest path that no longer exists"
    )


# ── hop 3: _pdf_job forwards it to the pipeline ─────────────────────────────

def test_pdf_job_forwards_manifest_path_to_run_pdf_analysis():
    """The last hop. _pdf_job could receive the path correctly and still drop
    it on the floor."""
    from bobbytailor.web import jobs_runtime

    jobs_runtime.jobs["job-x"] = {
        "id": "job-x", "status": "queued", "progress": 0, "log": [],
        "result": None, "error": None, "sheets_completed": [],
        "current_sheet": {}, "started_at": None,
    }

    seen = {}

    def fake_run(pdf_path, project_name, **kwargs):
        seen.update(kwargs)
        seen["pdf_path"] = pdf_path
        return {"total_line_items": 0, "sheets_processed": 0}

    with mock.patch(
        "bobbytailor.pipeline.pdf_analyzer.run_pdf_analysis", fake_run
    ), mock.patch.object(jobs_runtime, "_persist_job_history", lambda *a, **k: None):
        jobs_runtime._pdf_job(
            "job-x", "uploads/plans.pdf", "Crow", None, "uploads/manifest_ab.csv"
        )

    assert seen.get("manifest_path") == "uploads/manifest_ab.csv", (
        "_pdf_job received the manifest and did not pass it on; "
        "run_pdf_analysis saw %r" % seen.get("manifest_path")
    )


# ── self-audit ──────────────────────────────────────────────────────────────

def test_this_module_spends_no_money():
    source = Path(__file__).read_text()
    forbidden = [
        "ANTHRO" + "PIC",
        "vision_only" + "_benchmark",
        "accuracy" + "_gate",
        "mark." + "golden",
        "crow_cass" + "_golden",
    ]
    for token in forbidden:
        assert token not in source, (
            "this module must stay free; found %r" % token
        )
