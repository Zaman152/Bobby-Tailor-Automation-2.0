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
* **`.env` must not outrank the process environment.** `load_dotenv` with
  `override=True` does not merely deprioritise a `docker run -e` or systemd
  `Environment=` value, it erases it — and writes the `.env` value through to
  `os.environ`, so every later `os.getenv` in the process sees it too.

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


# ─── B2: .env fills gaps in the environment, it does not outrank it ─────────

CONFIG_PY = REPO_ROOT / "src" / "bobbytailor" / "config.py"


def test_dotenv_does_not_override_the_process_environment():
    """Read off the source, not off behaviour: by the time a test can observe
    config, .env has already been loaded once and the damage (or its absence)
    is indistinguishable from a value that was simply never set."""
    calls = re.findall(r"load_dotenv\([^)]*\)", CONFIG_PY.read_text())
    assert calls, "config.py no longer calls load_dotenv"
    for call in calls:
        assert "override=False" in call, (
            "config.py loads .env as %r. With override=True a deployment "
            "environment variable is not lower priority, it is ERASED — and "
            "os.environ is mutated, so every later os.getenv sees the .env "
            "value. Deployment env vars must win." % call
        )


def test_a_process_environment_variable_survives_a_fresh_config_import():
    """The behaviour the source pin exists to protect, exercised end to end in
    a child interpreter so this process's already-imported config is
    irrelevant."""
    import subprocess
    import sys
    import os

    env = dict(os.environ)
    # A name .env is overwhelmingly likely to define — the whole point is that
    # a colliding name must still be won by the process environment.
    env["OUTPUT_DIR"] = "/srv/bobby/data-from-the-deployment"
    proc = subprocess.run(
        [sys.executable, "-c",
         "import bobbytailor.config as c; print(c.OUTPUT_DIR)"],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "/srv/bobby/data-from-the-deployment", (
        "a deployment-supplied OUTPUT_DIR was discarded in favour of .env; "
        "got %r" % proc.stdout.strip()
    )


# ─── B3: importing a constants module is not a reason to demand secrets ─────

def _child_python(code: str, env_overrides: dict):
    """Run *code* in a clean interpreter with *env_overrides* applied.

    A subprocess is the only honest way to test import-time behaviour: this
    process imported config long ago and cannot un-import it.
    """
    import subprocess
    import sys
    import os

    env = dict(os.environ)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
    )


# A .env in the repo root would refill these behind our back, so the child is
# pointed at an empty cwd-relative path by running from a directory with no
# .env AND by clearing the names outright. `_env_path` falls back to
# Path.cwd()/".env" only if the repo-root file is missing, so we clear rather
# than relocate.
_PLANS_ONLY_ENV = {
    "STACKCT_EMAIL": "",
    "STACKCT_PASSWORD": "",
}


def test_config_imports_without_stackct_credentials():
    """The plans-only operator's actual situation. This product does not ship
    StackCT; requiring two fake passwords to import a constants module was a
    container-start failure with no discoverable cause."""
    proc = _child_python(
        "import bobbytailor.config as c; print('IMPORTED', c.CLAUDE_MODEL)",
        _PLANS_ONLY_ENV,
    )
    assert proc.returncode == 0, (
        "importing bobbytailor.config without StackCT credentials failed:\n%s"
        % proc.stderr
    )
    assert "IMPORTED" in proc.stdout


def test_importing_config_validates_nothing():
    """Stronger than the import test above: even with EVERY required variable
    absent, importing the module must not raise. Import-time validation is what
    forced the fake credentials, so the absence of it is the actual fix."""
    blanked = {name: "" for name in (
        "STACKCT_EMAIL", "STACKCT_PASSWORD", "ANTHROPIC_API_KEY",
        "SECRET_KEY", "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
    )}
    proc = _child_python("import bobbytailor.config; print('IMPORTED')", blanked)
    assert proc.returncode == 0, (
        "bobbytailor.config still crash-fails at import on missing env "
        "vars:\n%s" % proc.stderr
    )
    assert "IMPORTED" in proc.stdout


def test_config_source_has_no_import_time_validate_call():
    """A module-level call is what made this an import-time precondition.
    Checked over the parsed module body so a mention inside a function or a
    docstring does not trip it."""
    import ast

    tree = ast.parse(CONFIG_PY.read_text())
    top_level_calls = [
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    ]
    assert "validate_required_env" not in top_level_calls, (
        "config.py calls validate_required_env() at module level again — that "
        "makes every listed secret a precondition for importing the package"
    )


def test_the_web_surface_validates_only_what_it_needs():
    from bobbytailor import config

    assert set(config.WEB_REQUIRED_ENV_VARS) == {
        "SECRET_KEY", "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
    }
    # StackCT is not part of the plans-only web surface.
    assert not set(config.WEB_REQUIRED_ENV_VARS) & set(
        config.SCRAPE_REQUIRED_ENV_VARS
    )
    # A missing API key must not be a refusal to boot — the deterministic
    # offline path is a supported way to run this product.
    assert "ANTHROPIC_API_KEY" not in config.WEB_REQUIRED_ENV_VARS


def test_validate_required_env_names_every_missing_variable_at_once():
    from bobbytailor.config import validate_required_env

    with pytest.raises(ValueError) as excinfo:
        validate_required_env(["__BT_ABSENT_A__", "__BT_ABSENT_B__"])
    message = str(excinfo.value)
    assert "__BT_ABSENT_A__" in message and "__BT_ABSENT_B__" in message, (
        "one variable at a time turns a config error into a guessing game"
    )


def test_create_app_refuses_to_start_without_a_session_secret():
    """The web-scoped check has to actually fire, and it has to say what is
    missing — the bare os.environ[...] it replaces raised a KeyError naming a
    single variable with no remedy attached."""
    proc = _child_python(
        "from bobbytailor.web.app import create_app; create_app()",
        {"SECRET_KEY": "", "ADMIN_EMAIL": "", "ADMIN_PASSWORD_HASH": ""},
    )
    assert proc.returncode != 0, "create_app() started with no SECRET_KEY"
    assert "SECRET_KEY" in proc.stderr and "ADMIN_EMAIL" in proc.stderr, (
        "create_app() failed without naming the missing variables:\n%s"
        % proc.stderr
    )


def test_stackct_login_is_where_stackct_credentials_are_required():
    """Checked on the source rather than by driving Playwright: the assertion
    is about WHERE the requirement lives, and browser.login() cannot be
    called offline."""
    browser_src = (
        REPO_ROOT / "src" / "bobbytailor" / "scrape" / "browser.py"
    ).read_text()
    assert "validate_required_env(SCRAPE_REQUIRED_ENV_VARS)" in browser_src, (
        "StackCT credentials are no longer validated at login; if they are "
        "not checked here they are checked nowhere, and a blank password "
        "becomes an Auth0 form that silently fails to submit"
    )


# ─── self-audit: this module costs nothing to run ───────────────────────────

def test_this_module_spends_no_money():
    source = Path(__file__).read_text()
    # Assembled from halves so the check cannot find itself.
    forbidden = [
        "vision_only" + "_benchmark",
        "accuracy" + "_gate",
        "mark." + "golden",
        "sk-" + "ant-",
    ]
    for token in forbidden:
        assert token not in source, (
            "this module must stay free; found %r" % token
        )
    # The API key NAME appears here on purpose — every occurrence blanks it or
    # asserts it is absent, which is the opposite of spending. What must never
    # appear is an assignment of a real-looking value to it.
    for match in re.finditer(r'ANTHROPIC_API_KEY"?\s*:\s*"([^"]*)"', source):
        assert match.group(1) == "", (
            "this module assigns a value to the API key: %r" % match.group(1)
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
    # subprocess is here to re-import config in a clean interpreter, never to
    # reach off the box; sys/os supply that child's argv and environment.
    allowed = {"ast", "os", "re", "subprocess", "sys", "pathlib", "pytest",
               "bobbytailor"}
    assert imported <= allowed, (
        "this module must stay offline; unexpected imports %r"
        % sorted(imported - allowed)
    )
