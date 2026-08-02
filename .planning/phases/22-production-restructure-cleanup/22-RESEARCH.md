# Phase 22: Production Restructure & Cleanup - Research

**Researched:** 2026-08-02
**Domain:** Repo restructure — test isolation, filesystem cleanup, Flask asset relocation, doc drift (no behavior change)
**Confidence:** HIGH (every load-bearing claim verified against the live working tree this session)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Step order LOCKED** (RESTRUCTURE-SPEC §5): 0 preconditions → 1 safety rails → 2 DELETE → 3 ARCHIVE → 4 docs archive → 5 web-asset move → 6 doc truth fixes → 7 dead JS → 8 reindex.
- Every step ends: `python3 -m pytest -q -m "not golden"` green → `gitnexus_detect_changes()` → **one commit**.
- **NEVER** run `pytest -m golden`, `scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py`, `scripts/golden_convergence.py` — paid Anthropic API; user-authorized only.
- **Python 3.9 runtime** — no >3.9 syntax anywhere.
- No pytest process may be running when Step 2 (DELETE) executes.
- Safety rails (Step 1) is the mandatory FIRST commit: `pytest.ini` gains `addopts = -m "not golden"`; `tests/conftest.py` isolates OUTPUT_DIR/SCREENSHOTS_DIR to a session tmpdir; the 3 MagicMock stub files get explicit tmp-path dir attributes (keep the stubs, make attrs explicit — do NOT delete).
- DELETE bucket = §4.1 verbatim (~1.13 GB); untracked via `rm -rf`, tracked (`scripts/_diag_chelsea.json`, `scripts/network_capture.py`) via `git rm`. Screenshot deletions scripted with an EXPLICIT KEEP-LIST, never negated globs.
- ARCHIVE bucket = §4.2: single zip `output/_archive/stackct-era-20260802.zip`; verify `unzip -t` BEFORE removing originals. `git mv` for tracked legacy (M3–M8).
- MUST-SURVIVE contract = §4.3 verbatim (executor checklist): learning.db(+wal/shm), stackct.db, 16 report-referenced VisionOnly run dirs AND their paired screenshots dirs, one-of-a-kind runs (Chelsea, Moxy full-name, latest Crow), scraper reuse caches.
- **Sacred, never touched:** `uploads/`, `human_inputs/`, `reports/`, `tests/` fixtures (incl. ground-truth take-off PDFs and `replay/`), `.planning/`, `docs/PIPELINE-GROUND-TRUTH.md`, `.env`.
- Add `MagicMock/` and `output/_archive/` to `.gitignore`.
- M1/M2: `templates/` + `static/` → `src/bobbytailor/web/{templates,static}` via `git mv`; delete `parents[3]` + both folder args in `web/app.py:32-37`. Do NOT touch `web/settings.py:16` / `seed_admin.py:31` parents[3] (.env lookup). Add `[tool.setuptools.package-data]` in the same commit (R10 freebie). Run gitnexus impact on `create_app` first.
- M3/M4: Master.md + Masterv2.md → `docs/archive/`; update comment refs. M5: design-system/ → docs/design/. M6–M8: 3 StackCT scripts → scripts/archive/ + fix `Path(__file__)` parent count.
- REJECTED moves: any `src/bobbytailor/*.py` module move, takeoff_pipeline split, object_manifest re-home, tests/fixtures moves.
- Dead JS (separate commit): delete `js/ui/{drawer,modal,toast,focus-trap,icons}.js` + `js/data-grid.js`, script tags `index.html:13-14`, orphaned `#ui-modal-root`/`#ui-toast-root` divs `index.html:20-21`. Grep-verify zero references at execution time.
- Docs truth fixes per §6 (README 4 wrong claims, DEPLOYMENT sync, .env.example 9 vars).

### Claude's Discretion
- Exact keep-list script implementation for Step 2 (language, location under scratch — must NOT land in repo unless it earns a place under `scripts/`).
- Commit message wording (follow the spec's suggested messages).
- Whether Step 1d (blueprint-parity uploads isolation) lands in Step 1 or defers to Step 5.
- Minor doc wording in README fixes.

### Deferred Ideas (OUT OF SCOPE)
- RESTRUCTURE-SPEC §7 items 1–13: ALL behavior changes, code refactors, generalization work (config unification, god-module split, scraper parity gap, frontend refactor, CWD-relative anchoring, docs program). Carried forward to production-hardening phases. Do NOT touch in Phase 22.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| §4.1 DELETE | ~1.13 GB unambiguous junk purge | Keep-list deletion script design (Don't Hand-Roll + Code Examples); tracked deletes verified present |
| §4.2 ARCHIVE | Single zip + `git mv` legacy | Zip mechanics (`zip -r` + `unzip -t`); 3 archive scripts verified + parent-count fix |
| §4.3 KEEP | Must-survive checklist | Verified `output/learning.db`/`stackct.db` DB reads; pairing table is authoritative |
| §5 Step 0 | Preconditions / baseline | Collection verified: `1132/1134 collected (2 deselected)` — baseline exact |
| §5 Step 1 | Safety rails (paid-test exclusion + output isolation) | **CRITICAL correction**: env-pin defeated by `load_dotenv(override=True)` — use config attr-patch. See Pitfall 1 |
| §5 Step 5 | Web asset relocation | `create_app` verified; zero code refs to root templates/static outside app.py; test_client exercises factory |
| §5 Step 6 | Doc truth fixes | config.py defaults verified (lines 22/25/40); requires-python already `>=3.9` |
| §5 Step 7 | Dead JS removal | index.html:13-15 verified — only 13/14 are dead; :15 reports-workspace.js is LIVE |
| §6 R1–R12 | Risk register | All 12 risks addressed in Common Pitfalls + Runtime State Inventory |
</phase_requirements>

## Summary

Phase 22 is a mechanical restructure (moves + deletions + doc fixes + test-isolation) with a strict no-behavior-change contract. The RESTRUCTURE-SPEC is authoritative and largely accurate; this research **verifies, not re-derives**, and surfaces **one spec-breaking correction** the planner must design around.

**The one correction that changes the plan:** The spec's Step 1b says to isolate `OUTPUT_DIR`/`SCREENSHOTS_DIR` by "mirroring the existing `LEARNING_DB_PATH` env-pin pattern" (`os.environ.setdefault` before first import). **This does not work for OUTPUT_DIR.** `config.py:10` calls `load_dotenv(dotenv_path=_env_path, override=True)` at import, and `.env` **does define `OUTPUT_DIR`** (verified this session). `override=True` means the .env value clobbers any conftest `setdefault`, so `config.OUTPUT_DIR` stays `./output` and reporter/pdf_analyzer write into the **real** `output/` tree. The `LEARNING_DB_PATH` analogy is false because that var is read in `learning/store.py` (which does not call `load_dotenv(override=True)`), whereas OUTPUT_DIR is read inside the very module that does the override. The working mechanism — already proven in `test_blueprint_parity.py:162-165` — is a **module-attribute patch**: after importing config in conftest, set `config.OUTPUT_DIR = tmp` and `config.SCREENSHOTS_DIR = tmp/screenshots` directly, before any writer module (`reporter`, `pdf_analyzer`) is imported.

**Everything else in the spec verified clean:** the golden-marker deselection produces exactly `2 deselected` (baseline 1132 confirmed empirically via `--collect-only`); the web-asset move has zero code references outside `app.py:32-37` (grep-clean across scripts/docs/root-py); the 3 archive scripts use `parent.parent`/`parents[1]` (2 levels up) and need `parents[2]` after moving one level deeper; index.html dead-JS lines 13/14 are dead but **line 15 (reports-workspace.js) is LIVE — must not be touched**; Master.md comment refs are exactly where the spec says.

**Primary recommendation:** Execute the 8 locked steps in order, but replace Step 1b's env-`setdefault` approach with a **config module-attribute patch in conftest** (Pitfall 1 + Code Examples). Use a Python dry-run keep-list script (not bash negated globs) for Step 2. Exercise all web verification through the Flask **test_client** (no live server needed) — `test_blueprint_parity.py` already proves the factory + 40 routes this way.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Test env/config isolation | Test harness (`conftest.py`) | Config module (`config.py`) | conftest owns session pins; config owns the getenv defaults + the `load_dotenv(override=True)` that fights the pins |
| Run-dir / screenshot writes | Backend (`reporter.py`, `pdf_analyzer.py`) | Config (`OUTPUT_DIR`/`SCREENSHOTS_DIR`) | Writers capture config values by-value at import — isolation must land before their import |
| Template/static resolution | Frontend Server (Flask `create_app`) | Package layout (`src/bobbytailor/web/`) | Move aligns folders with `app.root_path`; deletes the `parents[3]` reach-up |
| Report file serving | Backend (`reports.py` `_output_root()`) | Config | Reads `config.OUTPUT_DIR` dynamically at call-time (already absolutized `92c48cc`) — patch-friendly |
| Filesystem cleanup / archival | Ops script (scratchpad) | git (tracked deletes/moves) | Untracked junk = `rm -rf`; tracked = `git rm`/`git mv` (history preserved) |
| Packaging (wheel data) | Build config (`pyproject.toml`) | — | `[tool.setuptools.package-data]` includes moved templates/static in built wheel (R10) |

## Standard Stack

This is a repo-hygiene phase — **no new libraries are installed**. It uses tools already present. The "stack" is the toolchain the steps invoke.

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| pytest | (installed) | Offline gate `-m "not golden"`; `--collect-only` for cheap verification | Project's test runner; marker expression verified working |
| git `mv`/`rm` | system | History-preserving moves + tracked deletes | Only correct way to move tracked files (never find-and-replace paths) |
| GitNexus MCP | (installed) | `gitnexus_impact` before `create_app` edit; `gitnexus_detect_changes` before each commit; `npx gitnexus analyze` after moves (Step 8) | Mandated by CLAUDE.md |
| `zip` / `unzip -t` | system (macOS) | Step 3 archival + integrity verify before removing originals | Portable, CRC-verifies via `unzip -t` (exit 0 = OK) |
| `sqlite3` | system | `sqlite3 output/learning.db ".tables"` post-delete integrity check | Confirms DB survivors intact (§4.3) |
| setuptools | `>=64` (verified in pyproject) | `[tool.setuptools.package-data]` for moved web assets (R10) | `**` recursive globs need `>=62`; satisfied |

### Supporting
| Tool | Purpose | When to Use |
|------|---------|-------------|
| Python (scratchpad script) | Keep-list deletion for Step 2 (set membership, size/count asserts, dry-run) | Step 2 — safer than bash negated globs |
| Flask `test_client()` | Web smoke via app factory, no live server | Every web verification (Steps 1d, 2, 5, 7) |
| `find <dir> -maxdepth 1` | Confirm moved dirs are gone (R12) | Post-move check in Steps 4/5 |
| `ditto` (macOS alt to zip) | Alternative archival | Only if resource forks matter — not needed here; `zip` preferred |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| conftest config attr-patch | env `setdefault` (spec's Step 1b) | **Rejected — verified broken**: `load_dotenv(override=True)` + `.env` defining OUTPUT_DIR clobbers the pin |
| Python keep-list script | bash `rm` with negated globs | Rejected by CONTEXT (locked): negated globs are error-prone; explicit KEEP set is auditable |
| `zip` + `unzip -t` | `ditto -c -k` | `ditto` adds `__MACOSX`, preserves resource forks (unneeded); `zip` is simpler + `unzip -t` verifies CRC |
| Flask `test_client` | live `python app.py` server | Live server useful for final human click-through (Step 5) but not required for automated verify |

**Installation:** None. No `pip install` in this phase (except the incidental `pip install -e .` regeneration of `src/bobbytailor.egg-info/` after it is deleted in §4.1 — editable install already active).

## Package Legitimacy Audit

Not applicable — **this phase installs zero external packages.** All tools (pytest, git, zip, sqlite3, setuptools, Flask) are already present in the verified runtime. No registry lookups required.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram — Test-Isolation Data Flow (Step 1, the critical mechanism)

```
pytest startup
   │
   ▼
tests/conftest.py  (loads FIRST, before any test module)
   │  ① os.environ.setdefault(model/ensemble/learning pins)   ← these SURVIVE (not read by load_dotenv module)
   │  ② _TMP = tempfile.mkdtemp()
   │  ③ import bobbytailor.config
   │        └─ config.py:10  load_dotenv(override=True) ──► reads .env ──► OUTPUT_DIR := "./output"  ✗ clobbers env pin
   │        └─ config.py:73  OUTPUT_DIR = getenv("OUTPUT_DIR","./output")   = "./output"
   │        └─ config.py:74  SCREENSHOTS_DIR = OUTPUT_DIR + "/screenshots"  (NOT env-driven)
   │  ④ config.OUTPUT_DIR = _TMP                     ◄── ATTR PATCH (the fix; mirrors test_blueprint_parity.py:165)
   │  ④ config.SCREENSHOTS_DIR = _TMP + "/screenshots"
   │  ⑤ _ensure_real loop imports reporter, ... AFTER the patch
   │        └─ reporter.py:16  from config import OUTPUT_DIR   ──► captures _TMP   ✓
   ▼
test run
   └─ reporter.write_report()  → Path(OUTPUT_DIR)=_TMP  ✓ NO writes to real output/
   └─ pdf_analyzer (imported lazily by a test) → from config import SCREENSHOTS_DIR → _TMP/screenshots  ✓
```

Reason this ordering is safe: pytest loads `conftest.py` before collecting any test file, so no `from config import OUTPUT_DIR` runs before the patch. `reporter` is in conftest's pre-import loop (line 102) and is imported *after* the patch line. `pdf_analyzer` is NOT in the loop but is imported lazily by the first test that needs it — always after conftest finishes.

### Recommended Project Structure (post-move target — from spec §2)
```
src/bobbytailor/web/
├── app.py            # create_app: parents[3] + both folder args DELETED
├── templates/        # ← git mv from repo-root templates/  (Flask default resolution)
└── static/           # ← git mv from repo-root static/
docs/
├── archive/          # ← Master.md, Masterv2.md (git mv)
└── design/           # ← design-system/ (git mv)
scripts/archive/      # ← audit_plan_sets.py, discover_plan_sets.py, diagnose_fixture.py (git mv, parent-count fix)
output/_archive/      # ← stackct-era-20260802.zip (gitignored)
```

### Pattern 1: Module-attribute patch for import-bound config values
**What:** Config values consumed via `from config import X` are captured by-value at the importing module's import time. To override them for tests, patch the config module attribute *before* the consumer imports.
**When to use:** Any value read as `from bobbytailor.config import OUTPUT_DIR/SCREENSHOTS_DIR` (reporter.py:16, pdf_analyzer.py:20). Env pins alone fail here because of `load_dotenv(override=True)`.
**Example:**
```python
# Source: tests/test_blueprint_parity.py:162-165 (proven in-repo pattern)
monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
from bobbytailor import config
monkeypatch.setattr(config, "OUTPUT_DIR", str(tmp_path))   # ← the attr patch is what actually takes
```

### Pattern 2: Flask default asset resolution (Step 5)
**What:** With `templates/` and `static/` living next to the package module, `Flask(__name__)` resolves them by default — the explicit `template_folder`/`static_folder` args and `parents[3]` become dead code.
**When to use:** Step 5 only. `app.root_path` is already `src/bobbytailor/web/` (derived from `__name__`), so the move *aligns* folders with root_path.
**Example:**
```python
# Source: src/bobbytailor/web/app.py:30-37 (BEFORE)
def create_app() -> Flask:
    repo_root = Path(__file__).resolve().parents[3]
    app = Flask(__name__,
        template_folder=str(repo_root / "templates"),
        static_folder=str(repo_root / "static"))
# AFTER (Step 5):
def create_app() -> Flask:
    app = Flask(__name__)   # templates/ + static/ resolve next to the package
```

### Anti-Patterns to Avoid
- **Env `setdefault` for OUTPUT_DIR isolation** — silently defeated by `load_dotenv(override=True)`; the suite "passes" but writes to real `output/`, letting junk regrow (defeats Step 1's entire purpose). Use the attr patch.
- **Negated-glob deletion** (`rm output/screenshots/VisionOnly_* ` then hoping keeps survive) — CONTEXT-locked against. Enumerate the KEEP set, delete the complement.
- **Deleting `index.html:15` (reports-workspace.js)** — it is LIVE (exposes `window.reportWorkspace`). Only lines 13 (icons.js) and 14 (data-grid.js) are dead.
- **Find-and-replace on moved paths** — use `git mv`; per CLAUDE.md never rename via find-and-replace.
- **Editing `web/settings.py:16` / `seed_admin.py:31` parents[3]** — those find `.env`, a different purpose. Leave untouched (verified: both are `parents[3] / ".env"`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Config isolation for tests | Custom env-var juggling | `monkeypatch.setattr(config, "OUTPUT_DIR", …)` / conftest attr-patch | Proven in-repo (test_blueprint_parity); env pins lose to `load_dotenv(override=True)` |
| Screenshot keep/delete decision | Negated shell globs | Explicit KEEP-set Python script with dry-run + size asserts | Auditable; CONTEXT-locked; §4.3 pairing is the authority |
| Archive integrity | "trust the zip" then delete | `zip -r … && unzip -t … && rm` | `unzip -t` CRC-verifies every entry before originals are gone (rollback safety) |
| Wheel data inclusion | MANIFEST.in hand-editing | `[tool.setuptools.package-data]` | setuptools>=64 present; cleaner for src-layout package-data |
| Moving tracked files | `mv` + `git add` | `git mv` | Preserves history/blame; keeps clone reproducible |
| Web smoke test | Spin up live server + curl | Flask `create_app().test_client()` | No port, no process; already the parity-test pattern; 40 routes exercised in-process |

**Key insight:** The single highest-leverage thing this phase gets wrong if under-researched is the OUTPUT_DIR isolation mechanism. The spec's stated approach compiles and the suite goes green, but real `output/` keeps getting polluted — the exact failure Step 1 exists to prevent. The fix is a two-line attr patch, not a new abstraction.

## Runtime State Inventory

This is a moves/deletions/refactor phase — inventory is mandatory.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | `output/learning.db{,-wal,-shm}` + `output/stackct.db` are the survivor DBs; run-dir `takeoff.json` files embed `screenshots/<dir>/page_NNNN.png` links (reporter.py:426) — deleting a paired screenshots dir orphans a kept run's images | Step 2 keep-list must honor §4.3 pairing; post-delete `sqlite3 output/learning.db ".tables"` + web sheet-image smoke for 2–3 kept runs (R3) |
| **Live service config** | None external. The Flask app + APScheduler catalog job run only when `python app.py` is up — no persisted external service state carries a moved path. No CI/scheduler references repo-root `templates/`/`static/` (grep-clean) | None — verified no external service embeds the moved paths |
| **OS-registered state** | None — no launchd/systemd/Task Scheduler entries in-repo reference these paths | None — verified none found |
| **Secrets/env vars** | `.env` (sacred, untouched) **defines `OUTPUT_DIR`** — this is load-bearing: it clobbers the conftest env pin via `load_dotenv(override=True)`. `web/settings.py:16` + `seed_admin.py:31` reach `parents[3]` for `.env` (NOT templates) — must stay | Do NOT edit `.env`. Step 1 must use config attr-patch, not env pin (Pitfall 1). `.env.example` gains 9 vars (Step 6) — additive only |
| **Build artifacts** | `src/bobbytailor.egg-info/` (§4.1 DELETE) — regenerated by the active editable install; deleting it is safe and it will reappear | After Step 2, editable install remains valid; optionally `pip install -e .` to regenerate egg-info. `.pytest_cache/` regenerable (KEEP, harmless) |

**The canonical question — after every repo file is updated, what still holds an old string?** Only two things matter: (1) `output/` run-dir `takeoff.json` files reference paired screenshot dirs by name — the §4.3 keep-list protects them; (2) `.env`'s `OUTPUT_DIR` key drives config at runtime — unchanged, but it dictates the Step 1 isolation mechanism. No OS/service/secret rename is required (this is a cleanup, not a rebrand).

## Common Pitfalls

### Pitfall 1: OUTPUT_DIR env pin defeated by `load_dotenv(override=True)` (R4 root cause)
**What goes wrong:** Step 1b as literally spec'd (`os.environ.setdefault("OUTPUT_DIR", tmp)` in conftest) does not isolate writes. Verified this session: with the setdefault applied *before* importing config, `config.OUTPUT_DIR` still equals `./output` (pin did not survive).
**Why it happens:** `config.py:10` runs `load_dotenv(dotenv_path=_env_path, override=True)` at import, and `.env` defines `OUTPUT_DIR`. `override=True` overwrites `os.environ` from `.env` *before* `config.py:73` reads it. (`LEARNING_DB_PATH` survives only because it is read in `learning/store.py`, which does not call load_dotenv.)
**How to avoid:** In conftest, after `import bobbytailor.config`, directly set `config.OUTPUT_DIR = <tmp>` and `config.SCREENSHOTS_DIR = os.path.join(<tmp>, "screenshots")` — placed before the `reporter`/`pdf_analyzer` imports in the `_ensure_real` loop. `SCREENSHOTS_DIR` is NOT env-driven (config.py:74 derives it), so it MUST be patched as an attribute; setting a `SCREENSHOTS_DIR` env var does nothing.
**Warning signs:** Step 1 verify shows new dirs appearing under real `output/` during the run despite "green" suite.

### Pitfall 2: Solo-file MagicMock regrowth (R5)
**What goes wrong:** `pytest tests/test_takeoff_pipeline.py` alone recreates root `MagicMock/` even after the conftest fix, because the bare `_CONFIG_MOCK = MagicMock()` (test_takeoff_pipeline.py:27-32, test_sheet_pass_matrix.py:27-40) yields `os.fspath(mock.SCREENSHOTS_DIR)` = literal `'MagicMock/…'` which pdf_analyzer.py:280 `mkdir -p`'s.
**Why it happens:** In full-suite runs conftest pre-imports the real config so the `setdefault` stubs are no-ops; in solo runs the bare stub wins and every dir attr is a child mock.
**How to avoid:** Set explicit tmp-path strings on EVERY dir attribute of the three stub configs (test_pipeline_parity.py:53-60 already sets `SCREENSHOTS_DIR="/tmp/test_screens"` but leaves `OUTPUT_DIR` a child mock — add it). Keep the stubs (hermetic solo runs); make attrs explicit.
**Warning signs:** `MagicMock/` dir reappears after a solo-file run. Verify by running the 3 files SOLO plus the full suite (CONTEXT-locked verification).

### Pitfall 3: Deleting the LIVE reports-workspace script (R-frontend)
**What goes wrong:** Removing `index.html:15` breaks the entire verify/measure/reports workspace.
**Why it happens:** Lines 13 (icons.js), 14 (data-grid.js), 15 (reports-workspace.js) are three adjacent `<script type="module">` tags; only 13/14 are dead. Verified: reports-workspace.js exposes `window.reportWorkspace`, consumed by app.js.
**How to avoid:** Delete ONLY the two tags at lines 13-14 and the two divs at 20-21. Grep `lucideIcon|mountGrid|ui-modal-root|ui-toast-root` returns hits only in defining/dead files — re-verify at execution time (files last changed at `92c48cc`/`92c48cc`-era).

### Pitfall 4: Archived scripts break on import (R8)
**What goes wrong:** After `git mv scripts/{audit_plan_sets,discover_plan_sets,diagnose_fixture}.py scripts/archive/`, their `sys.path.insert(0, ROOT)` computes the wrong repo root.
**Why it happens (verified):** `discover_plan_sets.py:8` and `audit_plan_sets.py:9` use `Path(__file__).resolve().parent.parent`; `diagnose_fixture.py:14` uses `Path(__file__).resolve().parents[1]`. Both = 2 levels up = repo root from `scripts/`. After moving one level deeper (`scripts/archive/`), repo root is 3 levels up.
**How to avoid:** Change to `parents[2]` (or `.parent.parent.parent`) — 1 line each. These are archived diagnostics, best-effort.

### Pitfall 5: Moved dirs linger due to `.DS_Store` (R12)
**What goes wrong:** `git mv templates … && git mv static …` moves tracked files but leaves the old `templates/`/`static/` dirs on disk if an untracked `.DS_Store` remains.
**How to avoid:** After the moves, `rm -f templates/.DS_Store static/.DS_Store 2>/dev/null; rmdir templates static 2>/dev/null`; assert `find templates static -maxdepth 0` fails (dirs gone). Also add `.DS_Store` handling to the zip step (`zip -r … -x '*.DS_Store'`).

### Pitfall 6: Wheel packaging regression (R10)
**What goes wrong:** After the move, a built wheel omits templates/static (package-data not declared) — non-blocking today (deploys are editable installs) but a latent break.
**How to avoid:** Add in the same Step 5 commit:
```toml
[tool.setuptools.package-data]
bobbytailor = ["web/templates/*.html", "web/static/**/*"]
```
Recursive `**` needs setuptools>=62; pyproject already pins `>=64`. (Verified.)

## Code Examples

### Keep-list deletion script skeleton (Step 2 — Python, scratchpad only, dry-run default)
```python
# Source: derived from §4.1 DELETE / §4.3 KEEP; lives in session scratchpad, NOT the repo
import sys, os, shutil
from pathlib import Path

OUT = Path("output")
KEEP_RUNS = {  # §4.3 verbatim — the 16 paired runs + one-of-a-kind + caches + DBs
    "learning.db", "learning.db-wal", "learning.db-shm", "stackct.db",
    "Crow_Cass_20260717_043721", "Invitation_to_Bid_-_25-382_AL,_Chelsea,_Bear_Creek_Rd_20260627_171054",
    # … full §4.3 list …
}
DELETE_PATTERNS = [  # §4.1 verbatim prefixes
    "Test_Proj_", "Scale_Proj_", "Fused_Proj_", "Old_Shape_", "Crow_Cass_20260802_222708",
    # … full §4.1 list …
]
apply = "--apply" in sys.argv
to_delete, total = [], 0
for entry in sorted(OUT.iterdir()):
    if entry.name in KEEP_RUNS:      # never touch a survivor
        continue
    if any(entry.name.startswith(p) for p in DELETE_PATTERNS):
        size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
        to_delete.append(entry); total += size
print(f"{len(to_delete)} entries, {total/1e6:.1f} MB")
assert (OUT/"learning.db").exists() and (OUT/"stackct.db").exists(), "survivor DB missing!"
for e in to_delete:
    print(("DELETE " if apply else "DRY   ") + str(e))
    if apply: shutil.rmtree(e) if e.is_dir() else e.unlink()
assert (OUT/"learning.db").exists() and (OUT/"stackct.db").exists(), "survivor DB vanished!"
```

### Archive-then-verify-then-remove (Step 3)
```bash
# Source: §4.2 + R-rollback (zip before remove)
mkdir -p output/_archive
zip -r output/_archive/stackct-era-20260802.zip <§4.2 paths…> -x '*.DS_Store'
unzip -t output/_archive/stackct-era-20260802.zip   # exit 0 = CRC OK
# ONLY after exit 0:
rm -rf <§4.2 original paths…>
```

### Web smoke via test_client (no live server) — reusable across Steps 1d/2/5/7
```python
# Source: tests/test_blueprint_parity.py:75-79 pattern
python3 -c "
from bobbytailor.web.app import create_app
c = create_app().test_client()
print('routes:', sum(1 for _ in c.application.url_map.iter_rules()))
print('login GET:', c.get('/login').status_code)   # 200 expected (public)
print('reports API unauth:', c.get('/api/reports').status_code)  # 401 expected
"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Repo-root `templates/` + `static/` via `parents[3]` reach-up | Package-local `src/bobbytailor/web/{templates,static}` + Flask defaults | This phase (Step 5) | Deletes fragile root hack; wheel-installable |
| `pytest tests/` runs paid golden E2E | `addopts = -m "not golden"` default, opt-IN via `-m golden` | This phase (Step 1a) | No accidental paid spend |
| `_output_root()` absolutizes OUTPUT_DIR in reports.py | (kept as-is this phase) | `92c48cc` | Report serving already CWD-safe; full config unification deferred §7 |

**Deprecated/outdated:**
- Root `MagicMock/` artifact — dead mock-`__fspath__` byproduct (0 bytes), deleted in §4.1.
- `.codegraph/` — stale pre-GitNexus index, superseded by `.gitnexus/`.
- `js/ui/{drawer,modal,toast,focus-trap,icons}.js` + `data-grid.js` — dead frontend modules (Step 7).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `.env.example` current contents match spec §6's "9 missing vars to append" (file is permission-blocked from reading this session) | Step 6 | Low — spec §6 enumerates exact vars; executor greps `.env.example` at Step 6 to avoid dup-appending |
| A2 | The full §4.1/§4.3 screenshot dir names on disk match the spec's lists exactly (not re-enumerated file-by-file this session — spec is authoritative per CONTEXT "verify don't re-derive") | Step 2 | Medium — mitigated by the dry-run script printing counts+sizes for human review before `--apply` (CONTEXT-locked manifest review) |
| A3 | README's 4 wrong claims + DEPLOYMENT.md:60 are still present as spec §6 describes (config.py defaults verified: CLAUDE_MODEL_SCHEDULES falls back to CLAUDE_MODEL at :25, CLAUDE_MODEL_CLASSIFY=claude-haiku-4-5 at :40, requires-python `>=3.9` verified) | Step 6 | Low — config-side facts verified; only the README prose wording is unverified |

**Note:** A1/A3 are doc-content assumptions the executor resolves trivially at the relevant step by reading the file then. The one config fact that would have broken the plan (OUTPUT_DIR isolation) was verified and is NOT assumed.

## Open Questions

1. **Step 1d — blueprint-parity uploads isolation**
   - What we know: `create_app` (app.py:67-69) does literal `os.makedirs("output/screenshots")` and `os.makedirs("uploads")` (CWD-relative), and `runs.py` saves uploads to CWD `"uploads/"`. `test_blueprint_parity.py` writes real `uploads/` via endpoints with `finally`-cleanup.
   - What's unclear: pointing uploads at tmp requires `create_app` to read an `UPLOADS_DIR` — that is a **behavior change**, out of scope for this no-behavior-change phase.
   - Recommendation: **Defer 1d** with an explicit note (as CONTEXT permits). The finally-blocks already self-clean; full CWD-relative anchoring is deferred to §7 (M5). Do not add an UPLOADS_DIR override in Phase 22.

2. **create_app literal `os.makedirs("output/screenshots")` during tests**
   - What we know: even with config.OUTPUT_DIR patched to tmp, create_app still makes CWD `./output/screenshots` + `./uploads` (empty dirs) when test_blueprint_parity instantiates the factory.
   - What's unclear: whether Step 1's "zero new entries under real output/" verification trips on this.
   - Recommendation: It does not — `output/screenshots` already exists so `makedirs(exist_ok=True)` is a no-op, and it creates no *run* dirs. Scope the verification to run-dir entries (the pollution the phase targets), not the pre-existing empty `screenshots/` dir. Note this in the Step 1 verify wording.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python3 | Suite gate, keep-list script | ✓ | 3.9 (project runtime) | — |
| pytest | Offline gate `-m "not golden"` | ✓ | collected 1132/1134 this session | — |
| git (mv/rm) | Moves + tracked deletes | ✓ | repo is git | — |
| zip / unzip | Step 3 archival + `-t` verify | ✓ (macOS default) | system | `ditto -c -k` (not preferred) |
| sqlite3 | Post-delete DB integrity | ✓ (assumed macOS default) | system | `python3 -c "import sqlite3"` (stdlib) always available |
| GitNexus (`npx gitnexus analyze`) | Step 8 reindex; impact/detect_changes | ✓ (indexed: 7692 symbols per CLAUDE.md) | — | — |
| setuptools | package-data (Step 5) | ✓ | `>=64` (pyproject verified) | — |

**Missing dependencies with no fallback:** none identified.
**Missing dependencies with fallback:** `sqlite3` CLI — if absent, use stdlib `python3 -c "import sqlite3; print(sqlite3.connect('output/learning.db').execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall())"`.

## Validation Architecture

`workflow.nyquist_validation` treated as enabled (not disabled in config). This phase's validation is per-step, not per-feature — each of the 8 steps ends green.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (markers: `golden`, `generalization` registered in pytest.ini) |
| Config file | `pytest.ini` (gains `addopts = -m "not golden"` at Step 1a) |
| Quick run command | `python3 -m pytest --collect-only -q -m "not golden"` (import health, ~1s, no execution) |
| Full suite command | `python3 -m pytest -q -m "not golden"` (baseline: **1132 passed, 2 deselected**, ~7m45s) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| §5 Step 0 | Baseline green, golden deselected | collect | `python3 -m pytest --collect-only -q -m "not golden"` → `2 deselected` | ✅ (verified this session) |
| §5 Step 1a | Paid tests excluded by default | integration | `python3 -m pytest --collect-only -q` (bare) then confirm golden run only with explicit `-m golden` | ✅ pytest.ini |
| §5 Step 1b | No writes to real `output/` during suite | integration | run suite; `find output -newer <marker> -type d` shows zero new **run** dirs | ⚠️ verify via conftest attr-patch (Pitfall 1) |
| §5 Step 1c | No `MagicMock/` regrowth solo | unit | `python3 -m pytest tests/test_takeoff_pipeline.py tests/test_sheet_pass_matrix.py tests/test_pipeline_parity.py -q; test ! -d MagicMock` | ✅ 3 files exist |
| §5 Step 2 | DB survivors intact post-delete | smoke | `sqlite3 output/learning.db ".tables"; sqlite3 output/stackct.db ".tables"` | ✅ DBs present |
| §5 Step 2/5/7 | Web renders + sheet images load | smoke | test_client one-liner (Code Examples) → routes count, 200/401 | ✅ test_blueprint_parity pattern |
| §5 Step 3 | Zip integrity before removal | smoke | `unzip -t output/_archive/stackct-era-20260802.zip` exit 0 | n/a (created at step) |
| §5 Step 4 | Archive doc refs updated, suite green | unit | full suite (only test_extraction_prompt.py docstring touched) + `grep -rn 'Master.md\|design-system/' src static templates` | ✅ |
| §5 Step 5 | Factory + 40 routes intact after move | integration | `python3 -m pytest tests/test_blueprint_parity.py -q` (exercises `create_app` + EXPECTED_PATHS) | ✅ verified |
| §5 Step 8 | Full suite green post-restructure | full | `python3 -m pytest -q -m "not golden"` → 1132 passed | ✅ |

### Sampling Rate
- **Per step commit:** full offline suite `python3 -m pytest -q -m "not golden"` must be green (CONTEXT-locked — every step ends green).
- **Cheap mid-step check:** `--collect-only -q -m "not golden"` (~1s) after conftest/test edits to catch import breakage before the 7-minute run.
- **Phase gate:** Step 8 full suite green + `gitnexus_detect_changes()` clean.

### Wave 0 Gaps
- [ ] **No new test files needed.** Test infrastructure (66 files + conftest) fully covers the phase; the only test edits are isolation fixes to conftest.py + 3 stub files (behavior-preserving).
- [ ] Step 1 verification helper: a `find output -type d -newer <start-marker>` (or a session-start dir snapshot diff) to assert zero new run dirs — inline bash, not a committed test.
- [ ] Framework install: none — pytest present and collecting.

## Security Domain

`security_enforcement` not disabled; but this phase is moves/deletions/doc-fixes with **no behavior change**, so no new attack surface is introduced. Relevant existing posture (from FRONTEND §e, unchanged by this phase):

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | no (no new inputs) | existing `secure_filename` + `.pdf` check in runs.py (unchanged) |
| V12 File Resources | **yes (indirectly)** | Path-traversal guards in reports.py:26-79 + sheet-image route stay intact; the templates/static move must not weaken `send_file` containment — verified `_output_root()` absolutizes OUTPUT_DIR (`92c48cc`) |
| V14 Config | **yes** | `.env` untouched; `.gitignore` gains `output/_archive/` so archived paid-run artifacts never enter git |

### Known Threat Patterns for this change
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Archived paid-run JSON leaking into git | Information Disclosure | `output/` already gitignored; add `output/_archive/` explicitly (Step 2) |
| Deleting a report referenced by tracked `reports/**` | Denial (broken audit trail) | §4.3 pairing keep-list + web sheet-image smoke (R3) |
| Static-asset path escaping package after move | Tampering | Flask default static handler + existing extension allow-list; test_client 200-check on `url_for('static',…)` |

## Sources

### Primary (HIGH confidence — verified in working tree this session)
- `src/bobbytailor/config.py:10,22,25,40,73-74,140` — `load_dotenv(override=True)`, model defaults, OUTPUT_DIR/SCREENSHOTS_DIR derivation, import-time env validation
- `tests/conftest.py:30-103` — env-pin pattern, `_ensure_real` pre-import loop (reporter at :102, pdf_analyzer absent)
- `tests/test_blueprint_parity.py:75-79,160-169` — test_client factory pattern + proven `monkeypatch.setattr(config,"OUTPUT_DIR",…)`
- `tests/test_takeoff_pipeline.py:27-32`, `test_sheet_pass_matrix.py:27-40`, `test_pipeline_parity.py:53-63` — MagicMock stub locations
- `src/bobbytailor/web/app.py:30-37,67-69` — create_app parents[3] + folder args + literal makedirs
- `src/bobbytailor/pipeline/reporter.py:16,54`, `pdf_analyzer.py:20,280` — import-bound OUTPUT_DIR/SCREENSHOTS_DIR
- `templates/index.html:8-21` — script tags (13 icons.js, 14 data-grid.js dead; 15 reports-workspace.js LIVE) + orphaned divs
- `scripts/{discover_plan_sets,audit_plan_sets,diagnose_fixture}.py` — ROOT parent-count (parent.parent / parents[1])
- `pyproject.toml:11,29-33` — requires-python `>=3.9`, setuptools>=64, src-layout
- **Empirical:** `pytest --collect-only -q -m "not golden"` → `1132/1134 collected (2 deselected)`; config attr-patch experiment → env `setdefault` pin did NOT survive (`.env` defines OUTPUT_DIR)

### Secondary (spec/mapper docs — authoritative per CONTEXT)
- `.planning/codebase/RESTRUCTURE-SPEC.md` (§4.1/4.2/4.3 buckets, §5 steps, §6 R1–R12)
- `.planning/codebase/TEST-AUDIT.md` (§c MagicMock mechanism, §d/§f isolation), `FRONTEND.md` (§b dead assets, §d root-path quirk)

### Tertiary (LOW confidence / assumed)
- `.env.example` current contents (permission-blocked) — spec §6 authoritative; verify at Step 6
- Exact on-disk enumeration of every §4.1 screenshot dir — spec authoritative; dry-run script surfaces actual counts

## Metadata

**Confidence breakdown:**
- Test isolation mechanism: HIGH — the load_dotenv-override defeat was empirically reproduced and the attr-patch fix is proven in-repo
- Web asset move: HIGH — grep-clean of code references; test_client pattern verified
- Cleanup buckets: MEDIUM-HIGH — spec authoritative; on-disk dir names not re-enumerated (dry-run script mitigates)
- Doc fixes: MEDIUM — config-side facts verified; README/.env.example prose read at execution step

**Research date:** 2026-08-02
**Valid until:** 2026-08-16 (14 days — working tree is active; re-grep dead-JS + on-disk dir names at execution time per CONTEXT)
