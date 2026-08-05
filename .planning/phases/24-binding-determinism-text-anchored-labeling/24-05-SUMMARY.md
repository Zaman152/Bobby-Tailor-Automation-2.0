---
phase: 24-binding-determinism-text-anchored-labeling
plan: 05
subsystem: learning-store + pipeline-vocabulary
tags: [persistence, determinism, vocabulary, cost, sqlite, canonicalisation, pytest]

# Dependency graph
requires:
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 02
    provides: "the deterministic wall-class decision, which is invariant GIVEN its object list — this plan supplies the stable list"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 03
    provides: "resolve_published_name + _norm_item_key — the ONE fold, applied here on READ so a pre-24-03 snapshot cannot promote a split spelling to authority"
provides:
  - "learning_project_vocabulary — a NEW additive table carrying one per-project vocabulary snapshot; learning_vocabulary untouched"
  - "save_project_vocabulary / load_project_vocabulary — replace-in-place write, degrade-to-empty read"
  - "VOCAB_KIND_PROJECT / VOCAB_KIND_NAMING_CONVENTIONS — two snapshot kinds so two derivations cannot overwrite each other"
  - "LEARNING_TABLES — the module's table enumeration, so a new table cannot be added without being registered"
  - "TakeoffPipeline._load_persisted_vocabulary / _save_persisted_vocabulary — best-effort wrappers gated on learning_enabled"
  - "persisted-first branch in _build_project_vocabulary AND _build_naming_conventions"
  - "_canonicalise_persisted_vocabulary — the idempotent fold on read that makes a migration unnecessary"
affects: [24-06 ledger surfacing, 24-08 ensemble wire-up (funded by the removed repeat-run spend), 24-10 phase gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive table over destructive migration: a new concern with a different scope gets its own table, never a UNIQUE rebuild"
    - "Replace-in-place, not accumulate: ONE current snapshot per project, so reuse cannot depend on which row was read first"
    - "Degrade to empty, never raise: every read failure path returns [] and [] means 'derive fresh'"
    - "Canonicalise on READ, idempotently: the alternative to a migration, and only valid because it is idempotent — which is itself asserted"
    - "Persist the POST-VOTE list: the vote is what makes the list stable; persisting one sample would freeze the noise instead of the answer"
    - "Judge a cost change on the call count, not on a dollar figure: the count is what a free test can observe"

key-files:
  created: []
  modified:
    - src/bobbytailor/learning/store.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - tests/test_learning_store.py
    - tests/test_object_vocabulary.py
    - .planning/ROADMAP.md

key-decisions:
  - "Open Question 2 resolved PER-PROJECT, implemented as a NEW additive table. learning_vocabulary is keyed UNIQUE(project_type, raw_pattern, canonical_name, unit) and has no project key; adding one means rebuilding that UNIQUE, which is the destructive migration 24-RESEARCH section 13 forbids. The two are different concerns with different scopes and now live in different tables."
  - "project_key is NOT NULL on the new table. A NULL/global row would be inherited by every project of every type — the exact cross-project naming leak the per-project scope exists to prevent (T-24-20). A falsy key is a no-op returning 0, not a global write."
  - "TWO snapshot kinds, not one. _build_project_vocabulary and _build_naming_conventions are two different API passes over the same project; sharing one row would make whichever ran last silently answer for both."
  - "The snapshot's payload cap is its OWN constant, not MAX_VALUE_LEN (2000). A snapshot is a whole object LIST, not one correction value, and 2000 chars would reject every real vocabulary. WR-02's reject-never-truncate discipline is unchanged."
  - "_norm_item_key is IMPORTED from the aggregator rather than re-implemented. It IS the bucket identity that decides whether two rows are one item, and a second copy here is precisely how two folding rules drift apart — the mistake 24-02 and 24-03 both explicitly refused to make."
  - "The fold keeps the loser's spelling as an ALIAS rather than deleting it. It is a real label the plan may print, and the alias list is what the symbol gallery matches against."
  - "Partial top-up is deferred, explicitly. Deciding an object is 'missing' from a snapshot requires a name comparison, and any comparison loose enough to be useful is the approximate matcher 24-03 forbids."

requirements-completed: []
# HONEST SCOPE NOTE: this plan carries `requirements: [V4-DET-02, V4-DET-04]` and ticks
# NEITHER, for the same reason 24-02 and 24-03 did not.
#
# V4-DET-02 now has all three of its parts in the tree — 24-02's invariant decision, 24-03's
# folded name FORM, and this plan's stable object LIST. What it does NOT yet have is an
# end-to-end demonstration: the only differential that exercises the real naming path
# (`test_wall_class_label_invariance`) is built from two ALREADY-RECORDED paid runs, and no
# code change can alter what those two runs wrote to disk. Ticking the requirement would be
# claiming an outcome no artifact in this repository shows. The phase gate (24-10) owns it.
#
# V4-DET-04 (ensemble on every flippable pass) is 24-08's. This plan is the FUNDING half of
# the pairing 24-RESEARCH section 7.3.2 asks for, not the delivery half.

coverage:
  - id: P1
    description: "A per-project snapshot round-trips, replaces in place, and is invisible to other projects"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_learning_store.py#test_persisted_vocabulary_round_trips_field_for_field"
        status: pass
      - kind: unit
        ref: "tests/test_learning_store.py#test_persisted_vocabulary_save_replaces_rather_than_accumulates"
        status: pass
      - kind: unit
        ref: "tests/test_learning_store.py#test_persisted_vocabulary_is_scoped_to_the_exact_project"
        status: pass
      - kind: unit
        ref: "tests/test_learning_store.py#test_persisted_vocabulary_kinds_do_not_overwrite_each_other"
        status: pass
    human_judgment: false
  - id: P2
    description: "learning_vocabulary is byte-identical in schema and content; no destructive statement exists (T-24-18)"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_learning_store.py#test_persisted_vocabulary_leaves_learning_vocabulary_untouched"
        status: pass
      - kind: other
        ref: "grep -Ec 'DROP TABLE|ALTER TABLE learning_vocabulary|DELETE FROM learning_vocabulary' src/bobbytailor/learning/store.py -> 0"
        status: pass
    human_judgment: false
  - id: P3
    description: "A falsy project key writes nothing — no global row every project would inherit (T-24-20)"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_learning_store.py#test_persisted_vocabulary_falsy_project_key_writes_nothing"
        status: pass
      - kind: unit
        ref: "tests/test_object_vocabulary.py#test_persisted_vocabulary_is_not_reused_across_projects"
        status: pass
      - kind: other
        ref: "schema: project_key TEXT NOT NULL — a global row is unrepresentable, not merely unwritten"
        status: pass
    human_judgment: false
  - id: P4
    description: "Every read failure degrades to empty and the run derives fresh; a broken store never breaks a take-off"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_learning_store.py#test_persisted_vocabulary_unreadable_store_degrades_to_empty"
        status: pass
      - kind: unit
        ref: "tests/test_learning_store.py#test_persisted_vocabulary_absent_project_returns_empty_not_an_error"
        status: pass
      - kind: unit
        ref: "tests/test_object_vocabulary.py#test_persisted_vocabulary_broken_store_still_derives"
        status: pass
      - kind: unit
        ref: "tests/test_learning_store.py#test_persisted_vocabulary_oversized_payload_is_rejected_not_truncated"
        status: pass
    human_judgment: false
  - id: P5
    description: "A repeat run makes ZERO additional analyzer calls and yields an identical object list"
    requirement: V4-DET-04
    verification:
      - kind: unit
        ref: "tests/test_object_vocabulary.py#test_persisted_vocabulary_is_preferred"
        status: pass
      - kind: other
        ref: "mutation check — forcing the persisted-first branch off makes this test FAIL"
        status: pass
    human_judgment: false
  - id: P6
    description: "A split spelling already in the store folds on read and is never promoted to authority (T-24-19, assumption A4)"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_object_vocabulary.py#test_persisted_vocabulary_is_canonicalised_on_read"
        status: pass
      - kind: unit
        ref: "tests/test_object_vocabulary.py#test_persisted_vocabulary_fold_is_idempotent"
        status: pass
      - kind: other
        ref: "mutation check — forcing the persisted-first branch off makes the canonicalisation test FAIL"
        status: pass
    human_judgment: false
  - id: P7
    description: "The functions are patchable at module scope, as the 20-00 convention requires"
    requirement: V4-DET-02
    verification:
      - kind: other
        ref: "python3 -c \"... hasattr(t,'load_project_vocabulary'), hasattr(t,'save_project_vocabulary')\" -> True True"
        status: pass
    human_judgment: false

# Metrics
duration: 3h 20m
completed: 2026-08-05
status: complete
---

# Phase 24 Plan 05: Per-Project Vocabulary Persistence Summary

**The app has stopped re-inventing the naming library on every run: a project's object list is now derived once, folded through the one arbiter on the way back out, and reused — which makes the deterministic wall classifier's input stable and removes the single largest line item from a repeat run's bill.**

## Performance

- **Duration:** 3h 20m (three full 47–50 minute suites, one per commit, dominate it)
- **Started:** 2026-08-05
- **Completed:** 2026-08-05
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- **Defect F3's mechanism is closed at its source.** `map_wall_classes_from_library`'s object list comes from the project vocabulary, and that vocabulary was rebuilt from the API on every single run. 24-02 made the *decision* invariant; this plan makes the *input* invariant. A repeat run now reads one stored list and makes no project-level API call at all.
- **The cost claim is proven by call count, not asserted by arithmetic.** `test_persisted_vocabulary_is_preferred` asserts the stub's invocation count does not increase **at all** on the second run. That is both the cost claim and the determinism claim, because they are the same fact — the list only changed between runs *because* it was re-derived.
- **The tests are mutation-checked, not trusted.** Forcing the persisted-first branch off (`if False:`) makes both load-bearing tests fail. They catch the real defect rather than passing on any implementation.
- **The fold on read is what makes a migration unnecessary — and that is asserted rather than assumed.** A snapshot written before 24-03 landed can carry both `Bollard` and `Bollards`; both now collapse to one entry under the canonical form, `Dock Bumper` still resolves to itself, and running the fold twice is proven to yield the same list.
- **A stale finding was caught by the impact analysis:** `_build_project_vocabulary` has **zero** upstream callers. See the deviation below — this materially changes which method carries the cost.

## Task Commits

Each task was committed atomically:

1. **Task 1: An additive per-project vocabulary snapshot store** — `d52e787` (feat)
2. **Task 2: Prefer the persisted vocabulary over a fresh derivation** — `5c1cd74` (feat)
3. **Task 3: Prove the repeat run is free and the vocabulary is identical** — `67b7087` (test)

## Files Created/Modified

- `src/bobbytailor/learning/store.py`
  - `learning_project_vocabulary` — the new table, created with the same `CREATE TABLE IF NOT EXISTS` idiom as its four siblings. `project_key TEXT NOT NULL`, `kind`, `objects` (JSON), `object_count`, `last_seen`, `UNIQUE(project_key, kind)`.
  - `save_project_vocabulary` / `load_project_vocabulary`.
  - `VOCAB_KIND_PROJECT`, `VOCAB_KIND_NAMING_CONVENTIONS`, `MAX_PROJECT_VOCABULARY_LEN`, `PROJECT_VOCABULARY_TABLE`, `LEARNING_TABLES`.
  - A module `logger` (the module had none; the best-effort paths need one).
- `src/bobbytailor/pipeline/takeoff_pipeline.py`
  - Module-scope imports of the two store functions plus 24-03's `resolve_published_name` / `NAME_AUTHORITY_LIBRARY` / `_norm_item_key`.
  - `_canonicalise_persisted_vocabulary` — the fold on read.
  - `TakeoffPipeline._load_persisted_vocabulary` / `_save_persisted_vocabulary`.
  - `_build_project_vocabulary` and `_build_naming_conventions` — optional `project_key`, persisted-first branch before the sampling loop, post-vote save after it.
  - `run_project` — passes its already-resolved `project_key` into the naming-convention pass.
- `tests/test_learning_store.py` — **10 new tests** in one documented 24-05 section.
- `tests/test_object_vocabulary.py` — **5 new tests** in one documented 24-05 section.
- `.planning/ROADMAP.md` — 24-05 ticked, plan count 4/10 → 5/10.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical] The snapshot needed a `kind`, or the two derivations would overwrite each other**

- **Found during:** Task 1, designing the table against the plan's stated `save_project_vocabulary(project_key, objects, ts=None)` signature.
- **Issue:** The plan asks for the persisted-first treatment on **both** `_build_project_vocabulary` and `_build_naming_conventions`. Those are two different API passes producing two different object lists for the **same project key**. Under the plan's literal single-row-per-project design, whichever ran last would silently answer for both — a repeat run would reuse a naming-convention list as its project vocabulary, or vice versa. That is a *worse* determinism defect than the one being fixed, because it would be stable and wrong rather than merely unstable.
- **Fix:** a `kind` column with `UNIQUE(project_key, kind)`, exposed as an optional trailing keyword so the plan's stated signature still works verbatim. Two named constants, no free-form strings at call sites.
- **Files modified:** `src/bobbytailor/learning/store.py`, `src/bobbytailor/pipeline/takeoff_pipeline.py`
- **Verification:** `test_persisted_vocabulary_kinds_do_not_overwrite_each_other`
- **Committed in:** `d52e787`

**2. [Rule 2 — Missing Critical] The snapshot needed its own payload cap**

- **Found during:** Task 1, applying the module's WR-02 discipline.
- **Issue:** `MAX_VALUE_LEN` is **2000 characters** — sized for one correction value. A real project vocabulary serialises to well over that, so reusing the existing constant would have rejected every genuine snapshot and silently disabled the whole feature while every test that used a two-object fixture still passed.
- **Fix:** `MAX_PROJECT_VOCABULARY_LEN = 200_000`, with the reject-never-truncate rule intact and its reasoning stated in-file: a JSON array cut mid-token cannot be parsed back, so a truncated write would poison **every** future load rather than one row.
- **Files modified:** `src/bobbytailor/learning/store.py`
- **Verification:** `test_persisted_vocabulary_oversized_payload_is_rejected_not_truncated`
- **Committed in:** `d52e787`

**3. [Rule 2 — Missing Critical] `project_key` is NOT NULL, not merely "a falsy key returns 0"**

- **Found during:** Task 1, modelling the column on `learning_assumptions` as the plan instructs.
- **Issue:** `learning_assumptions.project_key` is **nullable on purpose** — NULL there means "applies to the whole project type", which is a legitimate specificity tier for a wall-height assumption. Copying that shape here would make a global vocabulary row *representable*, and any future writer that passed `None` would install a snapshot every project of every type inherits. That is T-24-20 exactly, and a runtime guard alone leaves the hole open for the next caller.
- **Fix:** the column is `NOT NULL`; the falsy-key no-op is the *second* line of defence, not the only one. The divergence from the sibling table is documented in the schema comment with its reason.
- **Files modified:** `src/bobbytailor/learning/store.py`
- **Verification:** `test_persisted_vocabulary_falsy_project_key_writes_nothing`, `test_persisted_vocabulary_is_scoped_to_the_exact_project`
- **Committed in:** `d52e787`

**4. [Rule 3 — Blocking] The store module had no logger**

- **Found during:** Task 1, writing the best-effort degrade paths.
- **Issue:** every failure path in this plan must *log and continue*. `learning/store.py` imported no `logging` and defined no `logger`, so the degrade-to-empty behaviour would have been silent — a store that quietly stops working and a run that quietly pays full price, with nothing in the log to say so.
- **Fix:** `import logging` + a module `logger`, following the convention every other module in the package uses. No existing function's behaviour changed.
- **Files modified:** `src/bobbytailor/learning/store.py`
- **Committed in:** `d52e787`

**5. [Rule 1 — Bug] A test asserted an empty table by erroring on a missing one**

- **Found during:** Task 1, first run of the new tests.
- **Issue:** `save_project_vocabulary` returns **before** touching the DB when the key is falsy or the payload is over-length — correctly, but it means `_ensure_schema` never runs. The helper that reads back "no rows were written" therefore raised `no such table`, and under a less careful assertion shape that would have *looked* like a pass for the wrong reason. This is the same class of mistake 24-02 caught in its skip-proof guard.
- **Fix:** the raw-row helper forces the schema first, with the reason recorded in its docstring, so "no row was written" is an observation about an existing **empty** table.
- **Files modified:** `tests/test_learning_store.py`
- **Committed in:** `d52e787`

**6. [Process] `_build_project_vocabulary` is dead code — the LIVE cost is `_build_naming_conventions`**

- **Found during:** Task 2, running the mandatory GitNexus impact analysis before editing.
- **Issue:** `impact(_build_project_vocabulary, upstream)` returns **0 impacted, 0 direct callers, 0 affected processes**. A repo-wide grep confirms it: the only references are its own definition and its own log lines. `run_project` sets `self._project_vocabulary` from `merge_with_naming_conventions(deterministic_library, naming_conventions)` — the method the plan names *second* is the one that actually spends the money. The plan's cost narrative attaches to `_build_project_vocabulary`; had I treated the plan's ordering as the fact, this plan would have shipped a persistence layer wired to a method nothing calls and claimed a saving it did not make.
- **Fix:** both methods got the treatment as the plan asks, but `_build_naming_conventions` is the one wired into `run_project`'s call site and is where the reuse is proven — Task 3's tests exercise **that** path, not the orphan. Recorded here rather than left implicit, because the plan's own framing is what a later reader would otherwise trust.
- **Files modified:** `src/bobbytailor/pipeline/takeoff_pipeline.py`
- **Verification:** `impact` output quoted below; `test_persisted_vocabulary_is_preferred` drives `_build_naming_conventions`.
- **Committed in:** `5c1cd74`

---

**Total deviations:** 6 (3 missing-critical, 1 blocking, 1 bug, 1 process). No scope creep, no new package, no new public surface beyond the two store functions, their constants and the fold helper.

## 24-02's residual differential did NOT start failing — and it structurally cannot

The execution brief predicted that `tests/test_fusion.py::test_wall_class_label_invariance`'s residual assertion (`Aluminum Storefront` vs `Aluminum Storefront/Curtain Wall`) "SHOULD start failing when this plan lands", and instructed that the failure be treated as the signal it worked. **It did not fail, and no code change in this plan could have made it fail.** The reason is specific and checkable, and it is not a shortfall:

That test builds its fixture by reading names **out of the two saved paid-run artifacts at runtime** (`_published_names(run_a)`, `_observed_name(names_a, r"storefront", run_a)`) and passing them straight into `_emit_wall_classes` as the library. It never invokes `_build_naming_conventions`, never touches the learning store, and never exercises the vocabulary derivation path at all. `run_a` and `run_b` are frozen JSON on disk; the two storefront spellings they contain are historical facts about August's paid runs.

What this plan changes is what a **future** run derives. The differential can only retire when a new paid run is recorded whose naming pass was *skipped* because the snapshot existed — at which point run 3's storefront name is run 2's by construction. That belongs to whoever spends the next API budget, and it is exactly the kind of claim that must not be manufactured offline.

**The assertion was therefore left completely untouched** — not deleted, not weakened, not "fixed". Weakening it would destroy the only runnable record of the residual. 24-02's own instruction was "should not 'fix' it by deleting it", and the correct reading of a green differential here is that the evidence it reads has not moved, because saved evidence never does.

## Measurements taken this plan (all FREE, zero API)

**The call count, which is the whole claim:**

| Run over `proj-a` | Analyzer invocations | Object list |
|---|---|---|
| First (no snapshot) | `n` (the ensemble N; > 0, asserted) | derived, then stored |
| Second (same project key) | **+0** | **equal to the first, field for field** |
| Over `proj-b` (sibling project) | **> 0** — derives its own | independent |
| With no project key | **> 0** — never persists, never reuses | independent |

**Mutation check** — the differential against a disabled persisted-first branch:

| Branch state | `test_persisted_vocabulary_is_preferred` | `..._is_canonicalised_on_read` |
|---|---|---|
| As shipped | PASS | PASS |
| `if False:` (branch disabled) | **FAIL** | **FAIL** |

**The fold, run against the F3/F2 spellings:**

| Input pair | Folds? | Result |
|---|---|---|
| `Bollard` + `Bollards` | **yes** | one entry, `Bollards`, aliases `["BOL", "B"]` merged |
| `Dock Bumper` | **no** | resolves to itself — the load-bearing negative |
| the same list, folded twice | — | identical (idempotence, which is why no migration) |

**Cost, stated honestly and NOT asserted as a test:** 24-RESEARCH records the project-level passes at **$0.422 of run 2's $0.599**. Removing them from a repeat run removes that share. No test asserts a dollar figure — the saving is a *consequence* of the call count, and the call count is the only half a free test can see. Judge this plan on the count.

## GitNexus (CLAUDE.md, mandatory)

- **Before editing the store:** `impact(record_ai_manifest, upstream)` → risk **LOW**, 3 impacted, 1 direct caller (`run_project`), 2 affected processes (`run_project`, `run_pdf_analysis`), 1 module.
- **Before editing the pipeline:** `impact(_build_naming_conventions, upstream)` → risk **LOW**, 3 impacted, 1 direct caller, 2 affected processes. `impact(_build_project_vocabulary, upstream)` → **0 impacted, 0 callers, 0 processes** — the dead-code finding above, and the single most useful thing the mandatory check produced this plan.
- **`detect-changes` before each commit:** run before all three. **⚠️ Reported risk HIGH before commits 1 and 2**, and CLAUDE.md requires that be surfaced rather than swallowed — so it is, with what it actually measured: the tool reports on the whole dirty tree (including the pre-existing `AGENTS.md`/`CLAUDE.md` edits that are not mine) and its "changed symbols" list is dominated by **line-shift noise** (`SCOPE_ITEM`, `_write_lock`, `SCHEMA_SQL`, `best`, `entry`, …) caused by inserting an import near the top of the file. No existing function body was modified in either commit; both are pure additions. The empirical check agrees: the full suite moved by **exactly** the number of tests added, at every one of the three commits. Before commit 3 the tool reported risk **low**, 0 affected processes.
- The index remains stale (`c4f6e7d` vs HEAD). Re-running `npx gitnexus analyze` is left to the phase orchestrator, since re-indexing mid-plan would invalidate the impact readings quoted above.

## Test Results

| Gate | Result |
|---|---|
| Baseline (plan entry, post-24-04) | 2053 passed, 1 skipped, 2 deselected |
| Full suite before `d52e787` | **2063 passed**, 1 skipped, 2 deselected (48:51) |
| Full suite before `5c1cd74` | **2063 passed**, 1 skipped, 2 deselected (49:01) |
| Full suite before `67b7087` | **2068 passed**, 1 skipped, 2 deselected (49:57) |
| `tests/test_four_set_coverage.py` + `test_phase23_acceptance.py` | 28 passed, 1 skipped |
| `tests/test_object_vocabulary.py` + `test_naming_conventions.py` | 78 passed |
| `tests/test_takeoff_pipeline.py` + `test_pipeline_deterministic.py` | 106 passed |
| `tests/test_learning_store.py` + `test_learning_ai_manifest.py` + `test_learning_retrieval.py` | 54 passed |

Net: **+15 tests, 0 regressions.** 2053 + 15 = 2068. Commit 2 added behaviour and no tests, and the count held exactly — which is the point of running the suite there. The 1 skip is the pre-existing one; the 2 deselected are the paid golden tests, never run.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | No `-m golden` run; `accuracy_gate.sh` / `vision_only_benchmark.py` / `golden_convergence.py` never invoked; `ANTHROPIC_API_KEY` never referenced; `.env` never read. `grep -Ec 'ANTHROPIC_API_KEY\|analyze_drawing\|anthropic' src/bobbytailor/learning/store.py` → **0**. |
| Offline gate green | 2068 passed / 1 skipped / 2 deselected, up from the 2053 baseline by exactly the 15 tests added. |
| `test_phase23_acceptance.py` + `test_four_set_coverage.py` green | Explicitly run together (28 passed, 1 skipped) and inside every full-suite run. |
| No destructive migration | `grep -Ec 'DROP TABLE\|ALTER TABLE learning_vocabulary\|DELETE FROM learning_vocabulary' src/bobbytailor/learning/store.py` → **0**. New table only; the existing UNIQUE and every existing row untouched, asserted by a test that dumps and compares all three distilled tables. |
| Persistence is a NAMING suggestion, never a quantity | The stored payload is the vocabulary object dicts (`canonical_name` / `aliases` / `basis` / `binding_hint` / `variant` / `thickness_in` / `height_ft`). No count, no measurement, no quantity is written or read. Stated as a boundary comment at the top of the new section. |
| Never silently substitutes | The snapshot supplies the object LIST the deterministic mapper binds against; it does not rename a measured row, and 24-03's arbiter still decides every published name. |
| Coincidence trap fenced | `grep -Ec '== *28\b\|== *132\b\|== *136\b\|== *56\b'` over both new test sections → **0**. No number moved toward golden. |
| Paid-run evidence untouched | `git status --porcelain .planning/paid-run-evidence/ \| wc -l` → **0**, checked before every commit. |
| `uploads/`, `human_inputs/`, `reports/`, `.env` untouched | `git status --porcelain` over all four → **0**. Not in any commit. |
| Developer's real learning store untouched | Every new test monkeypatches `LEARNING_DB_PATH` to `tmp_path`. `git status --porcelain \| grep -c '\.db$'` after the run → **0**. |
| No new packages | `json` and `sqlite3` were already imported by this module. `git diff --stat requirements.txt setup.py pyproject.toml \| wc -l` → **0**. |
| Python 3.9 | `python3 --version` → 3.9.6; `Dict`/`List`/`Optional`/`Any` from `typing`, no 3.10+ syntax. |
| No `--no-verify` | All three commits ran normally on the main working tree. |
| GitNexus before editing store/pipeline symbols | `impact` run on all three targets; the HIGH `detect-changes` reading surfaced above with what it measured; `detect-changes` before each commit. |
| Only my files staged | `git diff --cached --name-only` checked before every commit. The pre-existing `AGENTS.md` / `CLAUDE.md` / `.planning/config.json` edits and the suite-regenerated synthetic PDF fixtures were deliberately left unstaged. |

## Issues Encountered

- **The suite regenerates three synthetic PDF fixtures** (`tests/fixtures/synthetic/*.pdf`) on every run, dirtying the tree. Pre-existing, unrelated to this plan, and deliberately never staged. Worth knowing before someone `git add -A`s them into a commit.
- **`_build_project_vocabulary`'s orphan status is not obvious from reading the file** — it is a complete, documented, tested-looking method with an ensemble loop and a majority vote, sitting immediately above the method that is actually used. It is now persisted-first as well, so if it is ever re-wired it inherits the fix; but nothing in this plan's cost claim rests on it. A future cleanup plan should decide whether to delete it, and that decision is out of this plan's fence.

## User Setup Required

None — no external service configuration required. The new table is created lazily by the existing `CREATE TABLE IF NOT EXISTS` init on first use; an existing `learning.db` upgrades in place with no migration step and no data loss.

## Next Phase Readiness

**Blocks nothing; funds 24-08 and hands 24-10 a checkable claim.**

**For 24-08 (ensemble wire-up):** the pairing 24-RESEARCH section 7.3.2 asks for is now half-delivered. The repeat-run project-level spend is gone, which is the headroom 24-08's fan-out consumes. 24-08 should note that a repeat run's *first* pass is still full price — persistence removes the second and subsequent runs' project-level cost, not the first run's.

**For 24-06 (ledger surfacing):** the reuse is logged at INFO naming the project and the object count (`project vocabulary REUSED from %r's persisted snapshot`). If 24-06 wants "was this run's naming derived or reused?" in `run_settings` telemetry, that fact is already in the log and cheap to lift; nothing here writes it into the artifact.

**For 24-10 (the phase gate):** two structural, free assertions are now available — that a second `run_project` over one project key issues no project-level vocabulary call, and that no two objects in the published vocabulary share a `_norm_item_key`. The gate should NOT try to retire `test_wall_class_label_invariance`'s residual; see the section above for why that requires a new paid run.

**Honest expectations to carry into verification:**
- **No accuracy claim is made or measurable here.** Nothing was scored, and nothing may be. Judge this plan on the analyzer call count and on list identity — both observable offline, both asserted.
- **No dollar figure is asserted anywhere in the test suite.** The 70% figure is quoted from 24-RESEARCH's reading of the saved artifacts and is a statement about what the two recorded runs cost, not a prediction this commit can verify.
- **A first run is unchanged** — same passes, same cost, same behaviour. Everything this plan does is visible only on the second run of the same project.

## Self-Check: PASSED

All claimed files exist on disk (`src/bobbytailor/learning/store.py`, `src/bobbytailor/pipeline/takeoff_pipeline.py`, `tests/test_learning_store.py`, `tests/test_object_vocabulary.py`, `.planning/ROADMAP.md`, this SUMMARY). All three claimed commits resolve in `git log` (`d52e787`, `5c1cd74`, `67b7087`). `.planning/paid-run-evidence/` is untouched (0 porcelain entries).

---
*Phase: 24-binding-determinism-text-anchored-labeling*
*Completed: 2026-08-05*
