# RESTRUCTURE-SPEC — the authoritative spec for the restructure + cleanup phase

Synthesized 2026-08-02 from the six mapper documents in `.planning/codebase/`
(ARCHITECTURE.md, TEST-AUDIT.md, CLEANUP-MANIFEST.md, FRONTEND.md, CONCERNS.md, DOCS-AUDIT.md).
Branch at synthesis time: `accuracy/flag-dont-guess-coincidental-detections`, HEAD `92c48cc`
(the previously in-flight working-tree changes are now committed; working tree is clean apart
from AGENTS.md/CLAUDE.md edits and the untracked `.planning/codebase/` docs). The pytest suite
that was running during the mapper audits has finished.

Ground rules inherited from the mission and mappers:

- **Python 3.9 runtime** — nothing in this phase may introduce >3.9 syntax.
- **The offline suite must be green after every step**: `pytest -m "not golden"` (~1,125 tests).
  NEVER run `-m golden`, `scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py`, or
  `scripts/golden_convergence.py` — they spend paid API credits (memory: never autonomously).
- **Sacred data**: `uploads/` (307 MB irreplaceable plan PDFs), `human_inputs/`,
  `output/learning.db{,-wal,-shm}`, `output/stackct.db`, `tests/fixtures/replay/` (the replay
  seam), all of `reports/` (scored paid-run history), `.planning/`,
  `docs/PIPELINE-GROUND-TRUTH.md`, `.env`.
- **This phase is moves + deletions + doc fixes + test-isolation fixes only.** Behavior changes
  (config unification, god-module split, parity-gap closure, generalization fixes) are deferred
  to the production-hardening phases (§7).
- Per CLAUDE.md: run `gitnexus_impact` before editing any symbol, `gitnexus_detect_changes()`
  before each commit, and `npx gitnexus analyze` after file moves (the index will go stale).

---

## 1. TL;DR

The codebase itself is healthy — five clean domains, zero true orphan modules, zero TODO/bare-except
debt, all 66 test files live. What is NOT healthy is everything around it:

1. **A landmine**: `pytest tests/` runs two PAID golden E2E tests because `pytest.ini` has no
   `addopts` exclusion, and the suite pollutes the real `output/` tree (297+ fake run dirs, 373
   empty screenshot dirs, root `MagicMock/`) because `OUTPUT_DIR`/`SCREENSHOTS_DIR` are not
   isolated suite-wide. **Fix both FIRST or the junk regrows and someone spends money by accident.**
2. **~1.13 GB of reclaimable junk** — 96% of it June-era duplicate HD screenshot renders in
   `output/screenshots/`, all regenerable free from `uploads/` PDFs. A precise 16-run + pairing
   MUST-SURVIVE list exists (CLEANUP-MANIFEST §a.4) and is restated in §4.3 here.
3. **One structural move with real payoff**: `templates/` + `static/` from repo root into
   `src/bobbytailor/web/`, deleting the fragile `parents[3]` hack in `create_app`. Zero Python
   import churn; templates use `url_for('static', …)` throughout.
4. **Docs**: archive `Master.md`/`Masterv2.md` (Master.md is 100% subsumed byte-for-byte), fix
   README's 4 concretely wrong claims, add the 9 missing env vars to `.env.example`.
5. Everything ambiguous stays KEEP or ARCHIVE — nothing UNSURE gets deleted. All src/ code
   restructuring beyond the web-asset move (takeoff_pipeline split, rendering extraction,
   object_manifest re-home, config unification) is **explicitly deferred** — those churn import
   paths the 1,125-test suite patches by module-name, and phase 21-18 already did the import
   migration once.

Estimated reclaim: ~1.13 GB disk. Estimated steps: 8 commits, each ending green.

---

## 2. Target directory layout

```
Bobby-Tailor-Automation-2.0/
├── app.py                        # Flask entry (5 lines, unchanged this phase; debug=True fix deferred §7)
├── main.py                       # StackCT scraper CLI entry (unchanged)
├── pyproject.toml / requirements.txt / pytest.ini   # pytest.ini gains addopts = -m "not golden"
├── README.md                     # front door; 4 wrong claims fixed (slimming deferred, §7)
├── AGENTS.md / CLAUDE.md         # kept as-is (twin agent-instruction files; sync mechanism deferred)
├── .env / .env.example           # .env untouched; .env.example gains 9 missing vars
├── src/
│   └── bobbytailor/              # PACKAGE INTERNALS UNCHANGED THIS PHASE (see §7 for deferred splits)
│       ├── config.py
│       ├── pipeline/  deterministic/  vision/  learning/
│       ├── scrape/  stores/  devtools/
│       └── web/
│           ├── app.py            # create_app loses the parents[3] template/static folder args
│           ├── auth.py  jobs_runtime.py  settings.py  seed_admin.py
│           ├── blueprints/
│           ├── templates/        # ← MOVED from repo-root templates/   (Flask default resolution)
│           │   ├── index.html  login.html  settings.html
│           └── static/           # ← MOVED from repo-root static/
│               ├── app.js  settings.js  ui-motion.js  style.css  ui-polish.css
│               └── js/           # (dead-JS deletion is a separate, user-confirmed step)
├── scripts/                      # first-class R&D tools, all kept at current paths
│   ├── accuracy_gate.sh  vision_only_benchmark.py  golden_convergence.py     # PAID gates
│   ├── setup_golden_fixtures.sh  export_takeoff_excel.py
│   ├── geom_probe.py  fusion_probe.py  scale_probe.py  room_probe.py  score_report_dir.py  # FREE probes
│   └── archive/                  # ← StackCT-era one-off diagnostics (git mv, history kept)
│       ├── audit_plan_sets.py  discover_plan_sets.py  diagnose_fixture.py
├── tests/                        # UNTOUCHED except isolation fixes in conftest.py + 3 stub files
│   ├── conftest.py  golden_validator.py  replay_analyzer.py
│   └── fixtures/                 # all fixtures kept, incl. ground-truth take-off PDFs + replay/
├── docs/
│   ├── DEPLOYMENT.md             # THE operator doc (2 small fixes)
│   ├── PIPELINE-GROUND-TRUTH.md  # protected, untouched
│   ├── design/                   # ← MOVED from repo-root design-system/ (UI token contract)
│   │   └── bobby-tailor/{MASTER.md, pages/reports.md, pages/projects.md}
│   └── archive/                  # ← git mv destination for tracked legacy docs
│       ├── Master.md  Masterv2.md
├── reports/                      # KEEP ALL (scored paid-run history, 82 tracked files)
├── uploads/  human_inputs/       # sacred inputs, untouched
├── output/                       # runtime data (gitignored): learning.db*, stackct.db,
│   │                             #   MUST-SURVIVE run dirs (§4.3) + paired screenshots/
│   └── _archive/                 # ← single archive location for untracked paid-run artifacts
│       └── stackct-era-20260802.zip
└── .planning/  .gitnexus/  .cursor/   # untouched (reindex .gitnexus after moves)
```

Two archive destinations by necessity, not sloppiness: **git-tracked** legacy docs go to
`docs/archive/` via `git mv` (history preserved, still cloneable); **untracked** paid-run output
artifacts are compressed into one zip under `output/_archive/` (gitignored — they must not enter
git; `output/` is already ignored via `.gitignore:8`).

What deliberately does NOT change: every `src/bobbytailor/*.py` path, every `tests/` path,
`scripts/` production/probe tool paths, `uploads/`, `human_inputs/`, `reports/`, entry points.

---

## 3. File-moves table

Only moves with clear payoff. No `src/bobbytailor` Python module moves this phase (phase 21-18
already did the import migration; the suite patches `takeoff_pipeline.X` by module path in ~14
files — churn there needs the deferred refactor plan, not a cleanup phase).

| # | Current path | New path | Payoff / evidence |
|---|---|---|---|
| M1 | `templates/` (3 files) | `src/bobbytailor/web/templates/` | Flask default resolution; delete `parents[3]` + both explicit folder args in `web/app.py:32-37`; package becomes self-contained (FRONTEND §d). Templates reference assets only via `url_for('static',…)` — no template edits needed. |
| M2 | `static/` (12 JS + 2 CSS + settings.js) | `src/bobbytailor/web/static/` | Same change as M1 — one `git mv` each, two-line factory diff. |
| M3 | `Master.md` | `docs/archive/Master.md` | 67 KB, byte-identical first 1,660 lines of Masterv2 (diff-verified, DOCS-AUDIT); comment-only refs at `static/style.css:5-6`, `static/app.js:5`, update in same commit. |
| M4 | `Masterv2.md` | `docs/archive/Masterv2.md` | Superseded planning doc; still cited by `.planning/MASTERv2-GAP-ANALYSIS.md` + `tests/test_extraction_prompt.py:1` docstring — archive not delete; update the docstring path. |
| M5 | `design-system/` (3 .md) | `docs/design/` | Design contract, not a served asset (FRONTEND §b); no code reads it; update the "Master §8.x" comment pointers in app.js/index.html only if trivially greppable — they cite section numbers, not paths, so likely zero edits. |
| M6 | `scripts/audit_plan_sets.py` | `scripts/archive/audit_plan_sets.py` | StackCT-era one-off; referenced only by historical `.planning/phases/14-*` docs (CLEANUP §e). `git mv`. |
| M7 | `scripts/discover_plan_sets.py` | `scripts/archive/discover_plan_sets.py` | Same — "diagnostic tool, optional" per 14-01-SUMMARY.md:146. |
| M8 | `scripts/diagnose_fixture.py` | `scripts/archive/diagnose_fixture.py` | CLEANUP said DELETE (zero inbound refs) but TEST-AUDIT shows it is the ONLY consumer of `tests/fixtures/moxy/moxy_golden.csv` + `chelsea/chelsea_golden.csv` — conservative resolution: ARCHIVE, keep runnable. |

Moves considered and REJECTED for this phase:

- `devtools/object_manifest.py` → `pipeline/` (ARCHITECTURE §e-5): imported by 3 production
  modules + 3 test files; pure import churn with modest payoff — deferred to the refactor phase.
- Splitting `takeoff_pipeline.py`, extracting `rendering`/`pdfio`, verify-blueprint service
  extraction, app.js split: all deferred (§7) — they are code refactors, not moves.
- `tests/fixtures/*` manifest JSONs out of tests/: `tests/` is protected; 16 KB; KEEP in place
  (open question for a later decision).

---

## 4. Cleanup actions

Conflict-resolution rule applied: any mapper UNSURE ⇒ KEEP or ARCHIVE, never DELETE.
Notable resolutions: `MagicMock/` (DOCS-AUDIT unsure → TEST-AUDIT proved the mechanism, 0 bytes,
empty dirs only ⇒ DELETE); `diagnose_fixture.py` (CLEANUP delete vs TEST-AUDIT reference ⇒
ARCHIVE, M8); `data/` (CLEANUP "delete, unsure of origin" ⇒ ARCHIVE into the zip — 12 KB);
`VisionOnly_Bobs_G2` screenshots (unsure ⇒ ARCHIVE); tests-fixture manifest JSONs (unsure ⇒ KEEP).

### 4.1 DELETE (unambiguous junk — ~1.13 GB)

Do NOT run any of this while a pytest suite is running. Execute only after Step 1 (test
isolation) is committed, or the pollution regrows.

Untracked filesystem junk (plain `rm -rf`):

| Path / pattern | Size | Evidence |
|---|---|---|
| `MagicMock/` (repo root) | 0 B, 17 empty dirs | mock-`__fspath__` artifact, mechanism proven (TEST-AUDIT §c) |
| `output/Test_Proj_*`, `output/Scale_Proj_*`, `output/Fused_Proj_*`, `output/Old_Shape_*` (297 dirs) | 8.5 MB | pytest pollution, names from `test_reporter_accuracy.py:64,122` |
| `output/Crow_Cass_20260802_222708` | 0.03 MB | fake run from the 2026-08-02 suite; takeoff.json references nonexistent fixture paths |
| `output/screenshots/{Test,Test_Project,Settings_Parity,Isolation_Project,Determinism_PDF}_*` (373 empty dirs) | ~0 | pytest pollution |
| `output/screenshots/VisionOnly_Moxy_Knoxville_20260628_*` (3 dirs) | 438 MB | superseded hi-DPI renders; regenerable free via fitz from `uploads/` |
| `output/screenshots/Bobs_Discount_Test_*` (18) + `output/Bobs_Discount_Test_*` (18) | 318 + ~2.5 MB | dead June test project |
| `output/screenshots/Crow_Cass_Test_*` (20) + `output/Crow_Cass_Test_*` (20) | 143 + ~2.6 MB | same era |
| `output/screenshots/Crow_-_Cass_White_Road_*` EXCEPT `_20260630_234238` | ~93 MB | keep only the newest full 21-page set (reuse cache) |
| `output/screenshots/Moxy_Diag_20260628_040321` | 44 MB | one-off diagnostic |
| `output/screenshots/VisionOnly_Bobs_Discount{,_Manifest}_202606*` | 35 MB | June benchmark era; scores tracked in `reports/vision_only/` |
| `output/screenshots/Crow_Cass_White_Road_*` (no-dash variant, 2 dirs) | 14 MB | superseded naming era |
| `output/screenshots/VisionOnly_Crow_Cass_*` EXCEPT `_20260715_062822`, `_20260715_070930` | ~10 MB | non-paired sets (pairing table §4.3) |
| `output/screenshots/VisionOnly_Crow_{Tiling,Cass_Manifest,Cass_Fresh}*` | 21 MB | experiments; scores tracked in git |
| `output/Crow_Cass_*` (Jun 28–Jul 17 iterations) EXCEPT `Crow_Cass_20260717_043721` | ~2.4 MB | superseded probe iterations (latest kept) |
| `output/Archive.zip` | 55 KB | verified duplicate of the two kept Chelsea/Moxy dirs |
| `output/stackct 2.db`, `output/stackct.db.empty-bak` | 0.5 MB | Finder dupe + empty backup, Jun 27 |
| `output/webapp.log`, `output/.DS_Store`, `./.DS_Store` | ~0.3 MB | dev log + Finder junk |
| `.codegraph/` | 2.6 MB | stale pre-GitNexus index, superseded by `.gitnexus/` |
| `src/bobbytailor.egg-info/` | small | build artifact, regenerated by `pip install -e` |

Git-tracked junk (`git rm` — history retains the content):

| Path | Size | Evidence |
|---|---|---|
| `scripts/_diag_chelsea.json` | 241 KB | one-off scratch dump, zero references (CONCERNS L2) |
| `scripts/network_capture.py` | — | StackCT network sniffing, zero references, superseded by plans-only mission |

### 4.2 ARCHIVE

Into `output/_archive/stackct-era-20260802.zip` (single zip, gitignored, verify readable before
removing originals):

| Item | Size | Why archive not delete |
|---|---|---|
| `output/screenshots/Bobs_Discount_Kennesaw_StackCT_20260627_*` + `output/Bobs_Discount_Kennesaw_StackCT_20260627_233154` | ~19 MB | StackCT browser captures — NOT regenerable without a StackCT account/session |
| ~12 non-report-referenced `VisionOnly_*` run dirs (older Crow_Cass stamps, `VisionOnly_Bobs_Discount{,_Manifest}`, `VisionOnly_Crow_{Tiling,Cass_Fresh,Cass_Manifest}`, `VisionOnly_Moxy_Knoxville_20260628_043339`, `VisionOnly_Crow_Cass_20260627_211339`) | ~7 MB | contain takeoff.json/spec_tables.json from PAID API runs — recorded-run rule: archive, never delete |
| `output/Crow_-_Cass_White_Road_20260628_061922`, `output/Crow_Cass_White_Road_20260628_045605` | ~1 MB | StackCT-era originals |
| `output/screenshots/VisionOnly_Bobs_G2_20260715_*` | 2.2 MB | only a `.log` (no .json) references it — UNSURE ⇒ archive |
| `data/` (`state_store.db/`, `stream_store/`) | 12 KB | zero in-repo references but unidentified origin — UNSURE ⇒ archive |

Via `git mv` (history preserved): M3–M8 in the moves table (`Master.md`, `Masterv2.md`,
`design-system/`→`docs/design/`, three StackCT-era scripts → `scripts/archive/`).

In place, no move (`.planning/` is protected): `.planning/CURSOR-POWERUP.md`,
`.planning/MASTERv2-GAP-ANALYSIS.md`, `.planning/milestone-UAT.md` — historical records, leave them.

### 4.3 KEEP (the must-survive contract)

- **All of `src/bobbytailor/`** — zero orphan modules (ARCHITECTURE §c); near-orphans
  (`scale_utils`, `takeoff_measurements`, `geometry_takeoff`, `aggregator`, `distill`,
  `seed_admin`, `companion_takeoff`) all have live consumers.
- **All 66 test files + conftest.py + golden_validator.py + replay_analyzer.py + ALL fixtures**,
  including the two "unreferenced" take-off PDFs (mission-protected ground truth), the 4
  unreferenced fixture JSONs (~16 KB, UNSURE ⇒ KEEP), and `tests/fixtures/replay/` (.gitkeep).
  Optional CONSOLIDATE of `test_extraction_prompt.py`/`test_scraper_errors.py` is NOT done this
  phase (touching tests for 1.3 KB is pure churn).
- **All of `reports/`** (82 tracked files, 18 MB) — the paid-run audit trail; the cheap
  substitute for re-spending API credits.
- **`uploads/` (307 MB), `human_inputs/`, `.planning/`, `.env`, `docs/PIPELINE-GROUND-TRUTH.md`.**
- **`output/` survivors** (verbatim from CLEANUP-MANIFEST §a.4 — the executor must treat this
  as a checklist):
  - Databases: `learning.db`, `learning.db-wal`, `learning.db-shm`, `stackct.db`.
  - The 16 report-referenced run dirs AND their paired screenshots dirs (each run's
    `takeoff.json` embeds `screenshots/<dir>/page_NNNN.png` links — `reporter.py:426`):
    `VisionOnly_Bobs_G1_20260715_173331`↔`…_172329`, `VisionOnly_Bobs_G3_20260715_182541`↔`…_181734`,
    `VisionOnly_Crow_A1_20260715_212614`↔`…_211904`, `VisionOnly_Crow_A2_20260715_215449`↔`…_214607`,
    `VisionOnly_Crow_Cass_20260715_063739`↔`…_062822`, `VisionOnly_Crow_Cass_20260715_071654`↔`…_070930`,
    `VisionOnly_Crow_F2_20260715_082130`↔`…_081606`, `VisionOnly_Crow_Final_20260715_072611`↔`…_071750`,
    `VisionOnly_Crow_MAN_20260715_220702`↔`…_215933`, `VisionOnly_Crow_N1_20260715_170939`↔`…_170034`,
    `VisionOnly_Crow_R1_20260715_085526`↔`…_084814`, `VisionOnly_Crow_S1_20260715_161536`↔`…_160808`,
    `VisionOnly_Moxy_Knoxville_20260717_013825`↔`…_011939`, `…_021348`↔`…_015307`,
    `…_043126`↔`…_041129`, `…_045741`↔`…_044247`.
  - One-of-a-kind / latest project runs: `Crow_Cass_20260717_043721`,
    `Crow_-_Cass_White_Road_20260701_000626`, `Crow_-_Cass_White_Road-Plans_20260715_192505`,
    `Invitation_to_Bid_-_25-382_AL,_Chelsea,_Bear_Creek_Rd_20260627_171054` (the ONLY Chelsea
    result — source of the 100% comparison), `Moxy_Knoxville_-_Addendum_A_City_Comment_Revision_20260627_171145`.
  - Screenshot caches: `screenshots/Crow_-_Cass_White_Road_20260630_234238` (newest full Crow
    set, scraper reuse cache) and `screenshots/Crow_-_Cass_White_Road-Plans_20260715_191703`.
- **`scripts/`** production + probe tools (accuracy_gate.sh, vision_only_benchmark.py,
  golden_convergence.py, setup_golden_fixtures.sh, export_takeoff_excel.py, geom_probe.py,
  fusion_probe.py, scale_probe.py, room_probe.py, score_report_dir.py) — first-class R&D tools.
- `.gitnexus/` (active index), `.cursor/rules/` (tracked, UNSURE ⇒ KEEP), `.pytest_cache/`
  (regenerable, harmless), `AGENTS.md` + `CLAUDE.md` (both live — different tools read each).

---

## 5. Ordered migration steps

Every step ends with: `pytest -m "not golden"` green → `gitnexus_detect_changes()` → one commit.
Work on a dedicated branch (e.g. `restructure/cleanup-phase`) cut from the current branch after
it merges, or directly after `92c48cc` lands on main — do not interleave with accuracy work.

**Step 0 — Preconditions (no commit).**
Confirm no pytest process is running (`ps aux | grep pytest`). Confirm working tree is clean
(the `92c48cc` checkpoint already landed the in-flight Moxy work; `reports/accuracy_gate/moxy_run{3,4}.json`
are committed). Baseline the suite once: `pytest -m "not golden"` must be green BEFORE any change
(also proves the marker expression deselects both paid tests — expect "2 deselected").

**Step 1 — Safety rails: paid-test exclusion + output isolation.** *(the mandatory first commit)*
1a. `pytest.ini`: add `addopts = -m "not golden"` (developers opt IN with `-m golden`); document
    the opt-in in the README testing section.
1b. `tests/conftest.py`: session-scoped isolation for `OUTPUT_DIR`/`SCREENSHOTS_DIR` mirroring
    the existing `LEARNING_DB_PATH` pattern (conftest.py:38-41) — set env/config to a session
    tmpdir so `reporter.py:54` and `pdf_analyzer.py:280` never write into real `output/`.
    Note: `config.py` reads these at import via `os.getenv` defaults — pin the env vars BEFORE
    the first bobbytailor import (same top-of-conftest position as the existing pins).
1c. Fix the bare-MagicMock config stubs: `tests/test_takeoff_pipeline.py:27-32` and
    `tests/test_sheet_pass_matrix.py:27-40` get explicit tmp-path strings on every dir attribute
    (as `test_pipeline_parity.py:57-63` already does for `SCREENSHOTS_DIR` — and give that file
    an explicit `OUTPUT_DIR` too). Kills the `MagicMock/` regrowth in solo-file runs.
1d. `tests/test_blueprint_parity.py`: point the upload dir at tmp (it currently WRITES real
    `uploads/` with finally-cleanup — TEST-AUDIT §d). If the app factory can't take an uploads
    override without code change, defer 1d to Step 5 and note it.
    Verify: suite green; `output/` gains zero new entries during the run; no `MagicMock/` appears.
    Commit: `test: exclude paid golden marker by default + isolate OUTPUT_DIR/SCREENSHOTS_DIR from real output/`.

**Step 2 — DELETE bucket.**
Execute §4.1 exactly (untracked `rm -rf` list + `git rm` for the two tracked scratch files).
Use the §4.3 pairing checklist as the do-not-touch list; script the screenshot deletions with an
explicit keep-list rather than negated globs. Add `MagicMock/` and `output/_archive/` to
`.gitignore` (belt-and-braces; `output/` is already ignored).
Verify: `sqlite3 output/learning.db ".tables"` intact; stackct.db intact; suite green
(nothing in tests reads real `output/` — TEST-AUDIT §d); start the web app and confirm the
Reports list renders and sheet images load for 2–3 kept runs (pairing intact).
Commit: `chore: purge test-pollution and superseded render junk from output/ (~1.1 GB)`.

**Step 3 — ARCHIVE bucket.**
Create `output/_archive/stackct-era-20260802.zip` from the §4.2 list; verify zip integrity
(`unzip -t`), then remove the originals. `git mv` the three StackCT-era scripts →
`scripts/archive/` (M6–M8; keep their sys.path bootstrap working — they insert ROOT relative to
`__file__`, so update the `Path(__file__)` parent count or leave a one-line note).
Commit: `chore: archive StackCT-era captures, paid-run leftovers, and one-off diagnostics`.

**Step 4 — Legacy docs archive.**
`git mv Master.md Masterv2.md docs/archive/`; `git mv design-system docs/design`; update the
comment refs: `static/style.css:5-6`, `static/app.js:5` ("Tokens: Master.md §8.1" → point at
`docs/design/bobby-tailor/MASTER.md`), `tests/test_extraction_prompt.py:1` docstring.
Verify: suite green (the docstring edit is the only test-file touch); grep repo for `Master.md`
and `design-system/` to catch stragglers (`.planning/` refs stay as-is — historical).
Commit: `docs: archive Master/Masterv2, move design-system under docs/design`.

**Step 5 — Web asset relocation (the one structural move).**
`git mv templates src/bobbytailor/web/templates` and `git mv static src/bobbytailor/web/static`.
Edit `src/bobbytailor/web/app.py:32-37`: delete `repo_root = …parents[3]` and both
`template_folder=`/`static_folder=` args (Flask defaults now resolve next to the package).
Run `gitnexus_impact` on `create_app` first per CLAUDE.md. Do NOT touch `web/settings.py:16` /
`seed_admin.py:31` — their `parents[3]` finds `.env`, not templates.
Verify: suite green (test_blueprint_parity exercises the factory + 35 routes); launch
`python app.py` from repo root AND from another cwd far enough to prove template resolution no
longer depends on the repo-root reach-up (note: uploads/output dirs are still CWD-relative —
known, deferred §7); click through login → dashboard → reports → settings; confirm
`url_for('static', …)` assets 200.
Commit: `refactor(web): templates/ and static/ live inside the package; drop parents[3] root hack`.

**Step 6 — Documentation truth fixes.**
README: (1) remove/correct the nonexistent `GET /api/jobs/<job_id>` reference (real routes:
`/api/jobs/active`, `/api/jobs/history`, `/api/jobs/history/<job_id>`); (2) `CLAUDE_MODEL_SCHEDULES`
default = falls back to `CLAUDE_MODEL` (config.py:25); (3) `CLAUDE_MODEL_CLASSIFY` default =
hardcoded `claude-haiku-4-5` (config.py:40) — fix in docs/DEPLOYMENT.md:60 too; (4) Python
"3.10+" → 3.9 (pyproject `requires-python = ">=3.9"`); (5) flag the ~$0.05/run cost claim as
pre-Phase-21. `.env.example`: append the 9 missing vars with defaults + one-line comments
(`TAKEOFF_ACCURACY_MODE`, `COUNT_TILING`, `COUNT_TILING_GRID`, `DETERMINISTIC_ENABLED`,
`LEARNING_ENABLED`, `VERIFY_RETRY_ENABLED`, `RASTER_FORCE`, `MAX_PREVIEW_ROWS`, plus a comment
pointing `ADMIN_SEED_*` at seed_admin). Update README/DEPLOYMENT path mentions of
`templates/`/`static/`/`design-system/` changed in Steps 4–5.
Verify: suite green (docs only). Commit: `docs: fix 4 wrong README claims, sync DEPLOYMENT, complete .env.example`.

**Step 7 — Dead frontend code removal (REQUIRES USER CONFIRMATION — skip if not granted).**
Delete `src/bobbytailor/web/static/js/ui/{drawer,modal,toast,focus-trap,icons}.js` and
`js/data-grid.js`; remove their two `<script>` tags (`index.html:13-14`) and the orphaned
`#ui-modal-root`/`#ui-toast-root` divs (`index.html:20-21`). Evidence: never loaded or
zero-importer exports (FRONTEND §b), ~21 KB.
Verify: suite green; manual click-through of dashboard/reports/settings; browser console free of
new errors. Commit: `chore(web): remove 6 dead JS modules (~21 KB) and their orphaned mounts`.

**Step 8 — Reindex + wrap-up.**
`npx gitnexus analyze` (the moves staled the index — CLAUDE.md requirement). Re-run the full
offline suite one final time. Update `.planning/` phase tracking. Final commit:
`chore: reindex GitNexus after restructure`.

Rollback story: every step is one commit; Steps 2–3 are the only non-revertible-by-git actions,
which is why Step 3 zips before removing and Step 2 deletes only regenerable-or-worthless items.

---

## 6. Risk register

| # | Risk | Trigger | Mitigation |
|---|---|---|---|
| R1 | **Paid API spend by accident** | Executor runs bare `pytest` before Step 1a, or runs a gate script "to verify" | Step 1 is first; `addopts` lands before anything else; hard rule restated at top of this spec |
| R2 | **Flask template/static resolution breaks** (Step 5) | Any code path expecting repo-root `templates/`/`static/`; non-obvious `send_file`/`render_template` relative paths | `app.root_path` was ALREADY `src/bobbytailor/web/` (FRONTEND §d) — the move aligns folders WITH root_path, reducing weirdness; `_output_root()` in reports.py already absolutizes OUTPUT_DIR (`92c48cc`); grep for `templates/`+`static/` literals across src/scripts/docs before the move; manual click-through in verify |
| R3 | **OUTPUT_DIR reference breakage after cleanup** | Deleting a run dir or screenshots dir referenced by tracked `reports/**` or by a kept run's `takeoff.json` | §4.3 pairing checklist is authoritative; delete via explicit keep-list script; post-delete web smoke test of the Reports workspace incl. sheet images |
| R4 | **Test suite writes junk mid-cleanup** | Running cleanup while pytest is active, or before Step 1b/1c land | Step 0 process check; Step 1 precedes Step 2 unconditionally |
| R5 | **conftest isolation collides with existing stubs** (Step 1) | The 3 test files' `sys.modules` MagicMock stubs vs new env pins; conftest pre-import list (conftest.py:92-103) must stay ahead of stub registration | Change stubs to explicit-attribute mocks (1c) rather than removing them (they exist for hermetic solo runs); keep pins as `setdefault` top-of-file; run the 3 files SOLO (`pytest tests/test_takeoff_pipeline.py` etc.) plus the full suite as verification |
| R6 | **GitNexus index staleness** | File moves (Steps 3–5, 7) invalidate the symbol index; subsequent impact analyses lie | `npx gitnexus analyze` at Step 8 (and mid-way after Step 5 if further symbol edits are needed); treat stale-index warnings as blocking |
| R7 | **Scraper screenshot-reuse cache loss** | Deleting the newest complete screenshot set for a real project breaks `sheet_preview.py:31-44` reuse and forces re-capture (needs StackCT login) | Keep-list explicitly retains `Crow_-_Cass_White_Road_20260630_234238` and `…-Plans_20260715_191703`; Kennesaw set goes to the zip, not the void |
| R8 | **Archived scripts break on import** | `scripts/archive/*.py` compute repo ROOT from `__file__` parents — one level deeper now | Adjust the parent count in the 3 moved files (they are ROOT-only-insert group, CONCERNS L4) — 1-line each; they are archived diagnostics, best-effort |
| R9 | **`uploads/` side-effect during suite runs** | `test_blueprint_parity.py` writes real `uploads/` until 1d lands | Its finally-blocks clean up; 1d (or its Step-5 deferral note) closes it; never run cleanup on `uploads/` at all — it is sacred |
| R10 | **Wheel/sdist packaging regression** (Step 5) | `pyproject.toml` (setuptools) does not declare package-data; templates/static inside the package are NOT included in a built wheel — editable installs (current runtime) are fine | Non-blocking today (deploys are editable-install per DEPLOYMENT.md); add `[tool.setuptools.package-data]` for `web/templates/*`+`web/static/*` in the same commit as a freebie, or log as a deferred hardening item |
| R11 | **Cross-branch collisions** | Another agent/session works on `static/app.js` or reports.py while paths move under them | Do the restructure on its own branch in a quiet window; Steps 5 and 7 touch the same files as active accuracy/UI work — merge or freeze first |
| R12 | **Empty-dir illusions in git** | `templates/`→moved and `static/`→moved leave stale untracked leftovers (e.g. `.DS_Store`) making the old dirs linger | `git mv` then `rmdir` check; `find templates static -maxdepth 1` must fail post-move |

---

## 7. Explicitly out of scope — deferred to production-hardening phases

Behavior changes, code refactors, and generalization work. Listed so nothing silently drops.

**Deferred code restructuring (needs its own planned phase; import churn against ~14 patch-by-module-path test files):**
1. Split `takeoff_pipeline.py` (3,209 LOC) into run_settings / orchestrator / project_context /
   quantity_verifier with re-export shims (ARCHITECTURE §e-1).
2. Extract `rendering`/`pdfio` module (`render_clip_crop`, `_page_to_image`, sheet-ID parsing)
   out of `pdf_analyzer.py` — deletes the entire lazy-import lattice (ARCHITECTURE §e-2).
3. Close the front-door parity gap: scraper re-implements `run_project`'s tail and NEVER runs
   the autonomous vocabulary/naming pass — a real behavior gap on StackCT runs (ARCHITECTURE §d-2).
4. Re-home `devtools/object_manifest.py` (production input surface in a devtools package).
5. Unify config: single typed settings reader; stop `validate_required_env()` at import
   (config.py:140, CONCERNS H3); fix `load_dotenv(override=True)` precedence inversion;
   regenerate `web/settings.py` ALLOWED_FIELDS/VALid_MODELS from config (stale model list,
   CONCERNS M3); collapse the 5 independent env readers; single dependency manifest.
6. Frontend refactor: split the 81 KB app.js monolith along its section headers, one
   `core/api.js` (CSRF ×3→1) + `core/dom.js` (escape ×3→1), replace 13 inline `onclick`
   globals, vendor `motion@11.13.5` (CDN-only today — workspace dies offline), self-host fonts,
   `base.html` Jinja inheritance, CSP + security headers (FRONTEND §c/§f).
7. Blueprint hygiene: verify.py (821 LOC) business logic → service module; deprecate the 5
   unconsumed routes (after user confirms no curl-only operator use); standardize
   `@login_required` consistency (CONCERNS L5).

**Deferred behavior/product fixes (CONCERNS findings):**
8. Room-engine generalization ceiling — `PLAN_TITLE_RE` matches one CAD-template's viewport
   titles; ≤900 SF unit cap; silent zero-output needs a coverage flag (H1 — mission-critical
   for plans-only 100%).
9. Warehouse-tuned 30 ft wall-height default + project-wide `max()` (H2).
10. `app.py` `debug=True` gating (H4); Mobilization auto-injection policy + scoring exclusion
    (M1); qty=1 text enrichment on boilerplate (M2); vision-fallback `measurement_mode` marker
    (M7); Excel export + accuracy-scoring engine promotion from scripts/ into src (M8);
    scrape/browser.py suppressed-failure counting (M6); upload magic-byte sniff (L6);
    seed-admin default email (L7); scripts sys.path bootstrap standardization (L4).
11. CWD-relative `output/`/`uploads/` anchoring in config (M5) — related to but bigger than
    Step 5; needs a data-root env design.
12. Docs program: README slimming + docs/{ARCHITECTURE,API,CONFIGURATION,TESTING}.md
    (DOCS-AUDIT §c); AGENTS.md/CLAUDE.md sync mechanism; rate-limit/storage hardening.
13. Optional test consolidations (two sub-1 KB files) and the `tests/fixtures` manifest-JSON
    decision (plans-only mission may want them gone; 16 KB, KEEP until decided).
