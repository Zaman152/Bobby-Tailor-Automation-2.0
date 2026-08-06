---
phase: 24-binding-determinism-text-anchored-labeling
plan: 08
subsystem: pipeline (identification-pass ensemble) + reliability test suite
tags: [ensemble, majority-vote, row-identity, budget-guard, census, determinism, V4-DET-04, evidence-correction]

# Dependency graph
requires:
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 03
    provides: "`_norm_item_key` as the ONE fold — reused verbatim as the row-identity key, not re-implemented"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 05
    provides: "per-project vocabulary persistence — the repeat-run project-level spend it removes is the headroom this fan-out consumes"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 07
    provides: "the vector passes as they now stand; this plan touches `_run_pass` only, so nothing conflicts"
provides:
  - "`_VOTED_IDENTIFICATION_PASS_TYPES` — the named, small set of pass types eligible for voting"
  - "`_vote_schedule_rows` — a row-identity voter for free-form results with no candidate IDs"
  - "`_row_identity` / `_table_identity` / `_majority_payload` / `_canonical_signature` — its parts"
  - "`TakeoffPipeline._single_pass` — `_run_pass`'s pre-24-08 body, extracted verbatim"
  - "`TakeoffPipeline._identification_ensemble_n` — eligibility + config read, degrading to 1"
  - "voted branch in `_run_pass`, budget-charged per sample, with `_voted` / `_vote_samples`"
  - "the committed analyzer call-site census, with exactly one recorded exemption"
  - "the committed correction of 24-RESEARCH's F9 attribution"
affects: [24-09 determinism harness, 24-10 phase gate, every run's schedule/legend spend]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Vote on ROW IDENTITY when there is no candidate ID: what varies between two reads of a free-form table is which rows EXIST, not the label on a known row"
    - "Reuse the one fold: the vote key is the aggregator's `_norm_item_key`, so two spellings are one row here for the same reason they are one row downstream"
    - "A voted payload is VERBATIM from one sample, never blended — the vote cannot synthesise a value no sample produced"
    - "A quantity may never be part of an identity: it is precisely the field two honest reads are allowed to differ on"
    - "Look before you leap on EXTRA samples only: a refused charge is money paid for a discarded result, so decline the sample instead of issuing it"
    - "A partial vote DECLARES itself (`_vote_samples`) rather than passing as a full one"
    - "A census is guarded from BOTH sides: zero sites is a failure, and a positive control proves the detector detects"
    - "Correct a research assumption as a TEST, before writing the code the assumption was used to justify"

key-files:
  created:
    - .planning/phases/24-binding-determinism-text-anchored-labeling/24-08-SUMMARY.md
  modified:
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - tests/test_reliability_voting.py
    - tests/test_takeoff_pipeline.py
    - tests/test_pipeline_parity.py
    - .planning/ROADMAP.md
    - .planning/STATE.md

key-decisions:
  - "This plan does NOT stand on defect F9. The two saved paid runs are not peers — run 2 ran under a cap 2.5x smaller, reached 99.8% of it, spent less than half as much on sheet-attributed work, and invoked one model class where run 1 invoked three. The 184→64 swing is dominated by budget. That correction is committed as a test BEFORE any code changed. The plan stands on V4-DET-04's own justification: an un-voted identification pass can flip."
  - "`_vote_categorical_labels` was NOT reused. It votes a per-candidate LABEL under a known candidate-ID key and needs the candidate set fixed by the request's schema enums. `_run_pass` sends no schema and no candidate list, so the vote key had to be the ROW's own identity."
  - "The identity fold is the AGGREGATOR's `_norm_item_key`, imported. A second folding rule here is exactly how two folding rules drift apart — the mistake 24-02, 24-03 and 24-05 each refused to make."
  - "A surviving row is VERBATIM one sample's row (most common exact payload, ties → first seen), never a per-field blend. This is what makes T-24-34 structurally true rather than promised: the voter cannot emit a quantity no paid sample returned."
  - "A quantity/unit column can never contribute to a row's identity. Including QTY would make two reads of one row two rows, which is the opposite of the fix."
  - "`extraction`, `count` and `measure` are EXCLUDED. Their identification and their measurement arrive inside the SAME object with no seam, so there is no way to vote which objects exist without also voting their numbers."
  - "A tie DROPS the row — flag-don't-guess, the same rule `_vote_categorical_labels` applies when it yields the unknown sentinel."
  - "A ONE-sample outcome returns that read UNFOLDED. Folding a single read would silently edit it. But `_vote_samples: 1` is still stamped, so a partial never passes as a full vote (T-24-35)."
  - "An EXTRA sample with no budget headroom is declined via the guard's existing `would_exceed` rather than issued and refused. A refused charge means the vendor was paid for a result that is then discarded. The FIRST sample is always attempted, so budget exhaustion stays LOUD."
  - "No temperature parameter, deliberately. The grep count of `temperature=` in the module is unchanged at 1 — and the comment explaining why is worded to avoid defeating that very grep."
  - "The census identifies sites by ENCLOSING FUNCTION NAME via AST, never by line number. A census that fails on ordinary refactoring is a census people delete."

requirements-completed: []
# HONEST SCOPE NOTE: this plan carries `requirements: [V4-DET-04]` and does NOT tick it,
# consistent with 24-01…24-07.
#
# V4-DET-04 ("ensemble on every flippable pass") now has its last identification path closed
# in the tree, and the census makes a future un-voted path a test failure. What it does NOT
# have is a demonstration that the determinism actually held on a real drawing — that requires
# a paid run, which is forbidden autonomously. The phase gate (24-10) owns the tick.

coverage:
  - id: E1
    description: "The identification pass types routed through _run_pass are majority-voted on row identity"
    requirement: V4-DET-04
    verification:
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_voted_identical_samples_equal_any_one_sample"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_voted_majority_row_survives_minority_row_dropped"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_voted_a_tie_drops_the_row"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_voted_folds_two_spellings_of_one_row_into_one"
        status: pass
      - kind: unit
        ref: "tests/test_takeoff_pipeline.py#TestSchedulePass::test_schedule_pass_fans_out_to_the_ensemble (through run_sheet, not only the unit path)"
        status: pass
      - kind: other
        ref: "mutation check — emptying _VOTED_IDENTIFICATION_PASS_TYPES fails 8 of the new tests"
        status: pass
    human_judgment: false
  - id: E2
    description: "An ensemble size of one is byte-identical to the pre-24-08 single-shot behaviour"
    requirement: V4-DET-04
    verification:
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_voted_at_n1_is_byte_identical_to_single_shot"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_voted_only_the_identification_pass_types"
        status: pass
      - kind: other
        ref: "`_single_pass` is `_run_pass`'s prior body extracted verbatim; the call sequence (pre-check → log → render → call → cleanup → charge → non-dict guard) is unchanged"
        status: pass
    human_judgment: false
  - id: E3
    description: "Every sample is charged; exhaustion votes over the paid samples and never silently partials (T-24-33, T-24-35)"
    requirement: V4-DET-04
    verification:
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_budget_charges_every_sample"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_budget_exhausted_partway_votes_over_the_paid_samples"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_budget_no_paid_sample_raises_rather_than_returning_empty"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_budget_already_exhausted_raises_before_any_call"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_budget_declines_an_extra_sample_it_cannot_afford"
        status: pass
    human_judgment: false
  - id: E4
    description: "A majority-voted QUANTITY is structurally impossible, not merely avoided (T-24-34)"
    requirement: V4-DET-04
    verification:
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_voted_never_synthesises_a_quantity_no_sample_returned"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_the_identification_pass_types_are_exactly_the_table_reading_passes"
        status: pass
      - kind: other
        ref: "`_majority_payload` returns one of its inputs verbatim; `_ROW_QUANTITY_KEYS` is excluded from identity"
        status: pass
    human_judgment: false
  - id: E5
    description: "No temp-render leak across N samples (T-24-37)"
    requirement: V4-DET-04
    verification:
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_run_pass_voted_cleans_up_every_sample_render"
        status: pass
      - kind: other
        ref: "`git status --porcelain | grep -c '^??'` → 0 after every run"
        status: pass
    human_judgment: false
  - id: E6
    description: "A future un-voted call site is a test failure; the one exemption is recorded (T-24-36)"
    requirement: V4-DET-04
    verification:
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_every_analyzer_call_site_is_voted_or_exempt_so_every_pass_is_voted"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_the_census_detector_catches_a_newly_added_call_site"
        status: pass
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_the_census_exemption_list_is_explicit_and_singular"
        status: pass
      - kind: other
        ref: "non-vacuity demonstrated — narrowing the scan to a module with no analyzer call FAILS with 'census found ZERO call sites'"
        status: pass
    human_judgment: false
  - id: E7
    description: "The corrected F9 diagnosis is committed with its evidence, as relations rather than literals"
    requirement: V4-DET-04
    verification:
      - kind: unit
        ref: "tests/test_reliability_voting.py#test_f9_swing_is_explained_by_budget_not_sampling"
        status: pass
      - kind: other
        ref: "`grep -A30 'def test_f9_swing' | grep -Ec '<the four dollar figures>'` → 0; the evidence directory is unmodified"
        status: pass
    human_judgment: false
  - id: E8
    description: "Whether the ensemble actually improves a real run's determinism or accuracy"
    requirement: V4-DET-04
    verification: []
    human_judgment: true
    rationale: "Unmeasurable offline BY THE PLAN'S OWN SUCCESS CRITERIA. Judging this would require a paid run, which is forbidden autonomously. This plan is judged on the determinism PROPERTY and on budget safety — both proved with scripted stubs — never on an accuracy percentage."

# Metrics
duration: ~3h 50m (three full 52-minute suites plus three 14-minute gate runs dominate it)
completed: 2026-08-06
status: complete
---

# Phase 24 Plan 08: Ensemble Wire-Up for the Identification Passes Summary

**The last un-ensembled identification path is closed: the schedule and legend passes now majority-vote their tables and rows on the row's own identity, every sample is charged through the budget guard, and a committed census makes a future un-voted pass a test failure — while the research assumption this plan was originally justified by is committed, first, as a correction.**

## The correction came first, and it changed the justification

24-RESEARCH §7.2 attributed defect F9 — `raw_line_items` swinging 184 → 64 between the two saved paid runs — to `_run_pass` being un-ensembled. Its own Assumptions Log entry A1 recorded the competing risk (budget truncation) and prescribed the check. That check was run, free, against the two artifacts:

| | run 1 (14:19) | run 2 (18:13) |
|---|---|---|
| `budget.cap_usd` | larger | **2.5× smaller** |
| `budget.spent_usd / cap_usd` | ~55% | **~99.8%** |
| `api_usage.total_cost_usd` | — | **less than half** |
| `models_used` (total invocations) | 3 | **1** |
| `raw_line_items` | 184 | 64 |

**The runs are not peers.** Budget, not sampling, dominates the swing. Assumption A1's stated risk is the actual situation.

**Task 1 committed that as a test before a line of voting code was written** (`91698ad`). It asserts RELATIONS between the two runs, never dollar literals — a literal would pin a number nobody may adjust and would tell a future reader nothing about *why*. It skips cleanly when the evidence directory is absent. The research's secondary door-schedule detail (7 → 0 rows) did not reproduce under an independent count during planning and is **not** relied on.

**Consequence carried into the code, not just the prose:** this plan stands on V4-DET-04's own justification — an un-voted identification pass can flip — which is true regardless of what caused F9. And because tripling schedule/legend spend on a run already at ~99.8% of its cap would make the artifact *worse*, the budget-awareness below is load-bearing rather than decorative.

## ⚠ GitNexus impact on `_run_pass` returned **CRITICAL** — surfaced, as CLAUDE.md requires

```
impact(_run_pass, upstream) → risk CRITICAL
  impactedCount 8 · direct 1 · processes_affected 5 · modules_affected 2
  d=1: run_sheet
  d=2: _discover_and_add_linked_sheets, run_project_scrape,
       run_analyze_from_manifest, run_project
  d=3: run_pdf_analysis, run_all_projects, _stackct_job
  modules: Pipeline (direct), Scrape (indirect)
```

`_run_pass` is on the path of every sheet of every project run through either entry point. **This was not ignored.** The mitigations are structural rather than hopeful:

1. `_run_pass`'s entire prior body was **extracted verbatim** into `_single_pass`. Nothing inside it changed — same render branches, same `finally` cleanup, same charge, same non-dict guard.
2. The dispatcher takes the new branch **only** when `pass_type` is in a two-element named set **and** N > 1. Every other pass type on every sheet type reaches byte-identical code.
3. `test_run_pass_voted_at_n1_is_byte_identical_to_single_shot` asserts full dict equality against the raw analyzer return, including the absence of the vote metadata keys.
4. `detect-changes` before each commit reported **risk LOW, 0 affected processes**.
5. The full suite ran green at every commit, and the two named gates ran standalone at every commit.

**Note the GitNexus index is stale** (`c4f6e7d` vs HEAD), so the impact reading describes the graph as of that commit. Re-indexing is left to the phase orchestrator; doing it mid-plan would invalidate the reading quoted above.

## Performance

- **Duration:** ~3h 50m (07:00 → 10:50 +0500)
- **Tasks:** 3 of 3
- **Files modified:** 4 source/test files
- **Suite:** 2131 (plan entry) → 2132 (T1) → 2146 (T2) → **2150 passed, 1 skipped, 2 deselected** (T3)

## Task Commits

1. **Task 1: Commit the corrected F9 diagnosis before changing any code** — `91698ad` (test)
2. **Task 2: Vote the identification pass types, keyed on row identity** — `bcfe73e` (feat)
3. **Task 3: Commit the call-site census** — `c02f0ad` (test)

## Accomplishments

- **The vote key is the row, not a label.** `_vote_categorical_labels` was the wrong shape and was deliberately not reused: it votes a per-candidate LABEL under a known candidate-ID key, and it needs the candidate set fixed by the request's schema enums. `_run_pass` sends no schema and no candidate list — the schedule and legend passes return free-form tables of free-form rows, and what varies between two reads is **which rows exist**. So the vote key is the row's own identity: a MARK/TAG, an ITEM/DESCRIPTION.
- **Two spellings of one row are one row, for the same reason they are downstream.** The identity is folded through the aggregator's `_norm_item_key` — imported, not re-implemented. `Bollard` and `Bollards` collapse here exactly as they collapse in the bucket identity, which is the whole point of 24-03 having made that fold plural-aware. A second copy would be how two folding rules drift apart.
- **A majority-voted quantity is unrepresentable, not merely avoided.** `_majority_payload` returns **one of its inputs verbatim** — the most common exact payload, ties broken by first-seen order. Fields are never mixed across samples. So the voter cannot emit a row, or a number, that no paid sample actually returned. Asserted directly: given reads of `24`, `24`, `26`, the published quantity is `24` and never `25`.
- **A quantity can never be part of an identity.** `_ROW_QUANTITY_KEYS` fences QTY/QUANTITY/UNIT/COUNT/AREA/… out of the identity lookup. Including a quantity would make two reads of one row into two rows — the opposite of the fix.
- **A tie drops the row.** Flag-don't-guess, the same rule `_vote_categorical_labels` applies when it yields the unknown sentinel. Pinned by a 4-sample test where a row appearing in exactly 2 is dropped.
- **Budget exhaustion stays loud, and got cheaper.** Every sample is charged. Exhaustion mid-ensemble stops sampling and votes over what was paid for, with `_vote_samples` declaring the reduced count. No paid sample raises `BudgetExceeded` rather than returning `{}`. And an *extra* sample with no headroom is now **declined** via the guard's own `would_exceed` rather than issued and then refused — a refused charge is money the vendor was paid for a result that gets binned.
- **The census is guarded from both sides.** Zero sites found is a **failure**, not a clean bill of health (phase-23 rule 3). A positive control proves the detector really detects — a brand-new `self._analyzer(` call is found *and* reported unknown. And losing a site the census covers fails too, so the scan cannot quietly shrink.
- **The tests were mutation-checked, then fixed when two of them passed for the wrong reason.** See the deviation below — this is the most useful thing the mutation check produced.

## Files Created/Modified

- `src/bobbytailor/pipeline/takeoff_pipeline.py`
  - `import json` (for canonical payload signatures).
  - `_VOTED_IDENTIFICATION_PASS_TYPES = frozenset({"schedule", "legend"})`, with the exclusion of `count`/`measure`/`extraction` reasoned in-file.
  - `_ROW_IDENTITY_KEYS`, `_ROW_QUANTITY_KEYS`, `_TABLE_IDENTITY_KEYS`.
  - `_canonical_signature`, `_lowered_keys`, `_row_identity`, `_table_identity`, `_majority_payload`, `_vote_schedule_rows`.
  - `TakeoffPipeline._run_pass` — now the dispatcher: pre-check, logging, eligibility, sampling loop with per-sample charge + headroom check, the no-paid-sample raise, the one-sample unfolded return, and the voted result.
  - `TakeoffPipeline._identification_ensemble_n` — eligibility + config read, degrading to 1.
  - `TakeoffPipeline._single_pass` — the prior `_run_pass` body, verbatim.
- `tests/test_reliability_voting.py` — **+18 tests** in three documented 24-08 sections (Part A correction, Part B voting, Part C census), 9 → 27.
- `tests/test_takeoff_pipeline.py` — an autouse N=1 pin (documented, with a positive control) plus `test_schedule_pass_fans_out_to_the_ensemble`.
- `tests/test_pipeline_parity.py` — one N=1 pin on the pass-parity test, documented in its docstring.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug, in my own tests] Two of the new tests passed under mutation — for the wrong reason**

- **Found during:** Task 2, running the mutation check (emptying `_VOTED_IDENTIFICATION_PASS_TYPES`).
- **Issue:** `test_run_pass_voted_majority_row_survives_minority_row_dropped` and `..._folds_two_spellings_of_one_row_into_one` still **passed** with voting disabled. Both had the *winning* answer in the first scripted sample, so a single-shot read happened to produce the expected output. They would have shipped as tests that assert the right thing and detect nothing.
- **Fix:** the scripts were reordered so the **losing** answer is in sample 1 — the minority `Ladder` row, and the losing `Bollard` spelling. A single-shot read now produces the wrong answer by construction.
- **Verification:** second mutation round fails **8** tests instead of 6; both fixed tests are among them.
- **Committed in:** `bcfe73e`

**2. [Rule 3 — Blocking] 15 existing tests asserted PASS counts that the fan-out turned into SAMPLE counts**

- **Found during:** Task 2, first run of `tests/test_takeoff_pipeline.py` and `tests/test_pipeline_parity.py`.
- **Issue:** 14 tests in `test_takeoff_pipeline.py` and 1 in `test_pipeline_parity.py` failed with `StopIteration` from their scripted analyzer. None of them is about ensemble size — they assert which passes run, in what order, and what the merged output looks like. At the default N a `call_count == 3` assertion about the number of **passes** would silently become an assertion about the number of **samples**, and `test_schedule_calls_analyzer_once` would stop being true under its own name.
- **Fix:** an autouse fixture pinning N=1 for `test_takeoff_pipeline.py` (documented in full), and one `monkeypatch` on the single parity test. Each test keeps testing exactly what it was written to test.
- **Why this hides nothing:** the fan-out gained a positive control **in the same file** — `test_schedule_pass_fans_out_to_the_ensemble` re-pins N=3, drives `run_sheet`, and asserts the analyzer is called three times with `pass_type="schedule"`. It fails under the mutation check.
- **Files modified:** `tests/test_takeoff_pipeline.py`, `tests/test_pipeline_parity.py`
- **Committed in:** `bcfe73e`

**3. [Rule 2 — Missing Critical] An extra sample with no headroom was being issued and then refused**

- **Found during:** Task 2, reading `BudgetGuard.charge` against the plan's "must be budget-aware and must degrade rather than starve".
- **Issue:** copying `_voted_structured_vision_call`'s loop verbatim would attempt every sample up to N and rely on the charge being refused to stop. But a refused charge means the **API call already happened and was already billed by the vendor** — the guard's ledger simply declines to count it. On a run near its cap, N-1 extra samples per pass could be paid for and binned.
- **Fix:** after the first sample, an extra sample is only issued when `guard.would_exceed(observed_per_sample_cost)` is false. The guard exposes `would_exceed` for exactly this ("an optional before-call reservation... for callers that can estimate cost up front"). The **first** sample is always attempted, so exhaustion still surfaces loudly.
- **Verification:** `test_run_pass_budget_declines_an_extra_sample_it_cannot_afford` asserts one call, `refused_charges == 0`, and `_vote_samples == 1`.
- **Committed in:** `bcfe73e`

**4. [Rule 1 — Bug, self-inflicted] My own comment defeated the plan's temperature grep**

- **Found during:** Task 2, checking the acceptance criterion.
- **Issue:** the acceptance criterion is `grep -Ec "temperature *=" takeoff_pipeline.py` must not increase from **1**. My explanatory comment contained the literal `temperature=0` while arguing that it cannot help — pushing the count to **2**. The criterion is a mechanical grep and a comment is not a parameter, but a check that my own prose can defeat is not a check.
- **Fix:** the comment now says "pinning the temperature to zero" in words, and says so explicitly: *"the grep that proves it would be defeated by writing one into a comment, so this says it in words."*
- **Verification:** count back to **1**, the single pre-existing `_sample_call(sample_index=0, temperature=None, ...)`.
- **Committed in:** `bcfe73e`

**5. [Process] The plan named the census test twice, differently — reconciled rather than picked**

- **Found during:** Task 3.
- **Issue:** the plan's `must_haves.artifacts` requires a test named `every_pass_is_voted` and its acceptance criterion runs `-k every_pass_is_voted`; the task action names it `test_every_analyzer_call_site_is_voted_or_exempt` and its own grep criterion looks for that `def`. Either name alone fails one of the two stated criteria.
- **Fix:** `test_every_analyzer_call_site_is_voted_or_exempt_so_every_pass_is_voted` — matched by both. Recorded rather than silently picking one, because a future reader comparing the plan to the tree would otherwise see a criterion that appears unmet.
- **Committed in:** `c02f0ad`

---

**Total deviations:** 5 (2 bugs, 1 blocking, 1 missing-critical, 1 process). No scope creep, no new packages, no new public surface beyond the module-private voter and two methods.

## The cost of this wire-up, stated plainly

This is the honest half of the plan's own warning, and it is not hidden in a footnote.

**A schedule or legend pass now costs N times what it cost yesterday**, where N is `ENSEMBLE_N` (default **3**). The arithmetic on the passes affected:

| Path | Calls before | Calls after (N=3) |
|---|---|---|
| one `schedule` pass on a sheet | 1 | **3** |
| one `legend` pass on a sheet | 1 | **3** |
| the floor-plan multi-region schedule retry (3 regions), when it fires | 3 | **9** |
| `count` / `measure` / `extraction` | 1 | **1** (unchanged) |

Two things bound it, and neither is a promise — both are asserted:

1. **The guard charges every sample and stops when it runs out**, voting over what was paid for. It cannot exceed the cap, and it now declines samples it cannot afford rather than burning a refused charge on them.
2. **Plan 24-05 removed the project-level passes from every repeat run** — 24-RESEARCH records those at $0.422 of run 2's $0.599. That is the headroom this fan-out consumes, and it is why the pairing was load-bearing.

**No dollar figure is asserted anywhere in the suite.** The call count is the half a free test can see, and it is what every cost claim here rests on. Judge it on the count.

## Measurements taken this plan (all FREE, zero API)

**Mutation check** — the differential against a disabled `_VOTED_IDENTIFICATION_PASS_TYPES`:

| Round | Tests failing under mutation |
|---|---|
| First (before the coincidence fix) | 6 of the new tests — and **2 more that should have failed, passed** |
| After reordering the two scripts | **8**, including the `run_sheet`-level fan-out control |
| Reverted | **0** — all 27 pass |

**Census non-vacuity**, demonstrated live and then reverted:

| Scan scope | Result |
|---|---|
| As shipped (2 modules) | **6 sites found**, all classified — PASS |
| Narrowed to a module with no analyzer call | **FAIL** — "census found ZERO call sites. The scan is broken or pointed at the wrong modules — this is a census failure, not a clean bill of health." |

**The census, as it stands today:**

| Site (enclosing function) | Module | Disposition |
|---|---|---|
| `_structured_vision_call` | pipeline | voted, witnessed by `_voted_structured_vision_call` |
| `_single_pass` | pipeline | voted, witnessed by `_run_pass` *(new this plan)* |
| `_sample_call` | pipeline | voted, witnessed by `_run_sheet_raster` → `run_ensemble` |
| `build_project_vocabulary` | vision | voted, witnessed by `_build_project_vocabulary` → `majority_vote_objects` |
| `extract_naming_conventions` | vision | voted, witnessed by `_build_naming_conventions` → `majority_keep_conventions` |
| `_tiled_recount` | pipeline | **EXEMPT**, reason recorded inline |

Each "voted" claim is **witnessed**: the test asserts that the named fan-out really does invoke the call site in that module's *current* source, so the routing cannot change without the census noticing.

**Temperature, as the plan requires both numbers:**

| | `grep -Ec "temperature *=" takeoff_pipeline.py` |
|---|---|
| Pre-task | **1** |
| Post-task | **1** |

The one match is the pre-existing `_sample_call(sample_index=0, temperature=None, prompt_variation=0)`.

## The manifest-gated tiled count path — recorded, not skipped

24-RESEARCH §7.3.3 asks that this decision be recorded rather than silently skipped. It is now a committed artifact: the single entry in `_EXEMPT_CALL_SITES`, with its reason in the file. Two reasons, both of which stand alone:

1. **It is out of the mission.** `_tiled_recount` is reachable only when a human supplies a count manifest **and** count tiling is enabled. The mission is plans-only.
2. **It is a COUNT pass.** Its identification ("there is a bollard in this tile") and its quantity arrive in one object with no seam, exactly as for `count`/`measure`/`extraction`. Voting it would vote quantities by majority, which this phase's own contract forbids.

## Threat Model Outcomes

| Threat ID | Disposition | Outcome |
|---|---|---|
| T-24-33 | mitigate | **Met.** Every sample charged; sampling stops on exhaustion and votes over paid samples. Strengthened beyond the plan: an unaffordable extra sample is declined rather than issued and refused. The cost multiplier is stated with its arithmetic above rather than buried. |
| T-24-34 | mitigate | **Met, structurally.** Only `schedule`/`legend` are eligible; `count`/`measure`/`extraction` are excluded with the reason in-file. `_majority_payload` returns one sample verbatim, so a blended or computed quantity is unrepresentable; a quantity column can never be part of a row's identity. |
| T-24-35 | mitigate | **Met.** `_vote_samples` records the reduced count, including the one-sample case, which is returned UNFOLDED so a single read is never silently edited. No paid sample raises rather than returning `{}`. |
| T-24-36 | mitigate | **Met.** The census fails on zero sites, on an unclassified site, on a vanished site, and carries a positive control proving the detector detects. |
| T-24-37 | mitigate | **Met.** Each sample renders and unlinks its own pass image in the existing `finally`; asserted by a test that counts renders and checks every one is gone. No untracked files after any run. |
| T-24-38 | mitigate | **Met.** No temperature parameter; the grep count is unchanged at 1, and the comment explaining why is worded so it cannot defeat that grep. |
| T-24-SC | mitigate | **Met.** No new packages. `json` was already a stdlib import elsewhere in the package; every voting and budget primitive already existed. |

## Test Results

| Gate | Result |
|---|---|
| Baseline (plan entry, post-24-07) | 2131 passed, 1 skipped, 2 deselected |
| Full suite before `91698ad` | **2132 passed**, 1 skipped, 2 deselected (52:40) |
| Full suite before `bcfe73e` | **2146 passed**, 1 skipped, 2 deselected (52:43) |
| Full suite before `c02f0ad` | **2150 passed**, 1 skipped, 2 deselected (52:38) |
| `test_four_set_coverage.py` + `test_phase23_acceptance.py` (standalone, before each of the three commits) | **28 passed, 1 skipped** ×3 (~14:30 each) |
| `tests/test_reliability_voting.py` | 27 passed |
| `tests/test_takeoff_pipeline.py` | 80 passed |
| `tests/test_pipeline_parity.py` | 30 passed |

Net: **+19 tests, 0 regressions** (18 in `test_reliability_voting.py`, 1 in `test_takeoff_pipeline.py`). 2131 + 19 = 2150, and the arithmetic held at every commit (T1 +1, T2 +14, T3 +4). The 1 skip is the pre-existing one; the 2 deselected are the paid golden tests, never run.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | No `-m golden` run; the paid gate scripts were never invoked; the API-key env var was never referenced; `.env` never read. `grep -Ec` for all five paid-gate markers over `tests/test_reliability_voting.py` → **0**. |
| Offline gate green | 2150 passed / 1 skipped / 2 deselected, up from 2131 by exactly the 19 tests added. |
| `test_phase23_acceptance.py` + `test_four_set_coverage.py` green | Run **standalone** before each of the three commits (28 passed, 1 skipped each time) as well as inside every full-suite run. |
| BudgetGuard contract respected | A refused charge still discards its result and raises; no-paid-samples raises rather than returning empty; the guard's ledger still only holds paid-and-accepted work. Budget exhaustion remains LOUD — the first sample is always attempted, and `run_sheet`'s `except BudgetExceeded` flag path is untouched. |
| No numeric field in any vision schema | No schema was touched by this plan. `tests/test_vision_schemas.py`'s introspective no-numeric guard is green inside the full suite. |
| Coincidence trap fenced | `grep -Ec '== *28\b\|== *132\b\|== *136\b\|== *56\b'` over the new test sections → **0**. No number moved toward golden; the only integers asserted are sample counts (1–4) and call counts. |
| Paid-run evidence untouched | `git status --porcelain .planning/paid-run-evidence/ \| wc -l` → **0**, checked before every commit. The F9 test opens `takeoff.json` read-only. |
| `uploads/`, `human_inputs/`, `reports/`, `.env` untouched | Not in any commit; `git status --porcelain` clean over all four. |
| `AGENTS.md` / `CLAUDE.md` / synthetic PDFs never staged | `git diff --cached --name-only` checked before each of the three commits; the pre-existing `AGENTS.md`/`CLAUDE.md` edits and the suite-regenerated fixtures were deliberately left unstaged every time. |
| No new packages | `git diff --stat requirements.txt setup.py pyproject.toml \| wc -l` → 0. `json` is stdlib. |
| Python 3.9 | `python3 --version` → 3.9.6; `Optional`/`List`/`Dict` from `typing`, no 3.10+ syntax, no walrus in a comprehension target. |
| No `--no-verify` | All three commits ran normally on the main working tree. |
| GitNexus before editing pipeline symbols | `impact(_run_pass, upstream)` run and its **CRITICAL** verdict surfaced above with the mitigations; `detect-changes` before each commit (risk LOW, 0 affected processes each time). |

## Issues Encountered

- **The mutation check caught my own tests, not the code.** Two of the seven behaviour tests passed with voting disabled because the winning answer happened to be in sample 1. This is the same class of failure the coincidence-trap constraint exists to prevent, and it is worth stating loudly: **a new test is not evidence until it has been shown to fail.** Both were reordered so a single-shot read produces the wrong answer by construction.
- **The full suite exceeds the 10-minute per-call tool cap** (52m 40s each, three times, plus three 14m 30s gate runs — roughly 3h 20m of the plan's 3h 50m). Run in the foreground and blocked on inline.
- **`tests/fixtures/synthetic/*.pdf` are regenerated in-tree by every full-suite run**, so a suite run always leaves a dirty tree. Pre-existing, unrelated to this plan, never staged. Already logged in `deferred-items.md`; owner remains the 24-10 gate. Worth repeating: a clean tree is **not** a usable pre-commit gate in this repo — stage files individually.
- **The GitNexus index is stale** (`c4f6e7d` vs HEAD) and its `detect-changes` "changed symbols" list is dominated by line-shift noise from inserting a ~200-line block near line 611. The empirical check is the one that matters, and it agreed at every commit: the suite moved by **exactly** the number of tests added.

## User Setup Required

None. `ENSEMBLE_N` already exists and already defaults to 3; a deployment that wants the pre-24-08 behaviour sets it to 1 and gets it byte for byte.

## Next Phase Readiness

**Blocks nothing. Hands 24-09 one warning and 24-10 two open items.**

**For 24-09 (determinism harness):** ⚠ **the replay fixture key is a SHA256 over `(model, pass_type, prompt, image_count)`, and this plan does NOT change any of those four.** No prompt text, no schema, no image count was touched. 24-07's sequencing warning still stands unchanged: fixtures must be authored after `7cbdf40`. **But note a NEW interaction:** a `schedule` or `legend` pass now issues **N** requests where it issued one, and each carries the *same* key. A replay analyzer keyed purely on that tuple will return the *same* fixture for all N samples, so the vote will be unanimous by construction and prove nothing about the voting. If 24-09 wants its differential to exercise the ensemble, its fixture source must vary per sample — otherwise it should scope the differential to the passes it can genuinely vary and say so, rather than passing for having looked at nothing.

**For 24-10 (the phase gate):** V4-DET-04 is **not** ticked here. The gate owns it, and two free structural assertions are now available: that the census test exists and covers every analyzer call site, and that a `schedule` pass through `run_sheet` issues `ENSEMBLE_N` requests and returns a result declaring `_vote_samples`.

**Honest expectations to carry into verification:**

- **No accuracy claim is made or measurable here.** Nothing was scored, and nothing may be. Judge this plan on the determinism property (proved with scripted stubs) and on budget safety (proved by call counts and guard state) — never on an accuracy percentage, and never by running a paid validation.
- **This plan makes runs more expensive, by design.** The multiplier is in the table above. It is bounded by the guard, and it is funded by 24-05 only on the *second and subsequent* runs of a project — a **first** run pays the full fan-out with none of 24-05's saving.
- **F9 remains confounded and cannot be used to judge this plan either way.** If a future paid run shows the line-item count stabilising, that is evidence only if the two runs share a budget cap.

## Self-Check: PASSED

All claimed files exist on disk: `src/bobbytailor/pipeline/takeoff_pipeline.py` FOUND · `tests/test_reliability_voting.py` FOUND · `tests/test_takeoff_pipeline.py` FOUND · `tests/test_pipeline_parity.py` FOUND · this SUMMARY FOUND.

All three claimed commits resolve in `git log`: `91698ad` FOUND · `bcfe73e` FOUND · `c02f0ad` FOUND.

`.planning/paid-run-evidence/` is unmodified (0 porcelain entries).

---
*Phase: 24-binding-determinism-text-anchored-labeling*
*Completed: 2026-08-06*
