"""The deployment instructions must agree with the code they start.

Every defect this module pins lives in the seam between the code and the
*documents that tell an operator how to run it* — which is precisely the seam
the rest of the suite cannot see. The existing ~123-test web surface passes
today and notices none of these, because nothing in it reads the README, the
systemd unit, or the nginx snippet.

Concretely pinned here:

* **`-w 2` destroys all run state.** `web/jobs_runtime.py` holds `jobs`,
  `uploads`, `object_manifests` and `job_lock` as module-level dicts in one
  process. Two gunicorn workers do not share them, so an upload handled by
  worker A 404s when the run request lands on worker B. Every documented
  gunicorn invocation must therefore say `-w 1`, and the day someone moves
  that state into a shared store is the day this test is allowed to change.
* **gunicorn is invoked by the docs but was not a declared dependency.**
* **nginx `client_max_body_size` vs `MAX_UPLOAD_MB`** — a mismatch is a bare
  413 that never reaches Flask, so no in-app error is ever shown.

Everything here is FREE: no paid marker, no credential, no network, no golden
comparison. The module audits itself for that at the bottom.
"""
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
DEPLOYMENT_DOC = REPO_ROOT / "docs" / "DEPLOYMENT.md"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
JOBS_RUNTIME = REPO_ROOT / "src" / "bobbytailor" / "web" / "jobs_runtime.py"

DEPLOYMENT_DOCS = (README, DEPLOYMENT_DOC)

# `-w 4`, `-w4`, `--workers 3`, `--workers=3` — every spelling gunicorn accepts.
_WORKER_FLAG = re.compile(r"(?:-w\s*|--workers[\s=])(\d+)")

# An actual command line, not prose mentioning the word. Matches both
# `gunicorn -w 1 ...` and `/home/ubuntu/.../bin/gunicorn -w 1 ...`; does not
# match "`app.py` (gunicorn/Flask, `app:app`)".
_INVOCATION = re.compile(r"gunicorn\s+-")


def _doc_lines_invoking_gunicorn(path: Path):
    """(line_number, text) for every line that starts a gunicorn process."""
    return [
        (n, line)
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if _INVOCATION.search(line)
    ]


# ─── the state that forces a single worker ──────────────────────────────────

def test_live_run_state_is_still_in_process_dicts():
    """The premise of the single-worker rule, asserted rather than assumed.

    If this ever fails because `jobs`/`uploads` moved into a shared store, the
    worker-count pin below is free to be relaxed — deliberately, by editing
    both tests together, not by quietly raising `-w` in a doc.
    """
    src = JOBS_RUNTIME.read_text()
    for name in ("jobs", "uploads", "object_manifests"):
        assert re.search(
            r"^%s\s*:\s*dict\s*=\s*\{\}" % name, src, re.MULTILINE
        ), (
            "%s is no longer a module-level dict in jobs_runtime.py. If run "
            "state now lives in a shared store, update this test AND the "
            "worker-count pin together." % name
        )


# ─── B1: no deployment doc may prescribe more than one worker ───────────────

@pytest.mark.parametrize("doc", DEPLOYMENT_DOCS, ids=lambda p: p.name)
def test_no_deployment_doc_prescribes_more_than_one_gunicorn_worker(doc):
    offenders = []
    for lineno, line in _doc_lines_invoking_gunicorn(doc):
        for count in _WORKER_FLAG.findall(line):
            if int(count) > 1:
                offenders.append("%s:%d: %s" % (doc.name, lineno, line.strip()))
    assert not offenders, (
        "These lines start gunicorn with more than one worker, which 404s "
        "roughly half of all uploads and status polls because jobs/uploads "
        "are per-process dicts:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("doc", DEPLOYMENT_DOCS, ids=lambda p: p.name)
def test_every_documented_gunicorn_invocation_states_the_worker_count(doc):
    """An invocation with no `-w` at all inherits gunicorn's default of 1 —
    correct by accident. Require it to be explicit so the constraint is
    visible to whoever copies the line."""
    lines = [line for _, line in _doc_lines_invoking_gunicorn(doc)]
    assert lines, "expected at least one documented gunicorn invocation in %s" % doc.name
    for line in lines:
        assert _WORKER_FLAG.search(line), (
            "%s documents a gunicorn invocation with no explicit worker "
            "count: %s" % (doc.name, line.strip())
        )


@pytest.mark.parametrize("doc", DEPLOYMENT_DOCS, ids=lambda p: p.name)
def test_deployment_docs_explain_why_a_single_worker_is_required(doc):
    """A bare `-w 1` reads like a typo and invites a well-meaning
    'optimisation' back to `-w 2`. The reason has to travel with the flag."""
    text = doc.read_text().lower()
    assert "jobs_runtime" in text, (
        "%s prescribes -w 1 but never names jobs_runtime.py, so a reader has "
        "no way to know why raising the worker count breaks uploads" % doc.name
    )


# ─── M2: gunicorn is invoked by the docs, so it must be a dependency ────────

def test_gunicorn_is_a_declared_dependency():
    text = REQUIREMENTS.read_text()
    assert re.search(r"^gunicorn>=", text, re.MULTILINE), (
        "both deployment docs and the systemd unit invoke gunicorn, but it is "
        "not pinned in requirements.txt"
    )


# ─── M5: nginx body cap must match the app's own cap ────────────────────────

def test_nginx_body_size_matches_max_upload_mb():
    from bobbytailor.config import MAX_UPLOAD_MB

    sizes = re.findall(r"client_max_body_size\s+(\d+)M", README.read_text())
    assert sizes, "README no longer documents client_max_body_size"
    for size in sizes:
        assert int(size) == MAX_UPLOAD_MB, (
            "nginx client_max_body_size is %sM but MAX_UPLOAD_MB is %s — the "
            "smaller of the two wins as a bare 413 that never reaches Flask, "
            "so the operator sees no in-app error"
            % (size, MAX_UPLOAD_MB)
        )


# ─── self-audit: this module costs nothing to run ───────────────────────────

def test_this_module_spends_no_money():
    source = Path(__file__).read_text()
    # Assembled from halves so the check cannot find itself.
    forbidden = [
        "ANTHRO" + "PIC",
        "vision_only" + "_benchmark",
        "accuracy" + "_gate",
        "mark." + "golden",
    ]
    for token in forbidden:
        assert token not in source, (
            "this module must stay free; found %r" % token
        )


def test_this_module_imports_nothing_that_could_reach_a_network():
    """Checked over the module's own import statements rather than by scanning
    its text — a substring scan for a networking library finds itself."""
    import ast

    tree = ast.parse(Path(__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {"ast", "re", "pathlib", "pytest", "bobbytailor"}
    assert imported <= allowed, (
        "this module must stay offline; unexpected imports %r"
        % sorted(imported - allowed)
    )
