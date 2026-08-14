---
phase: 28-accuracy-remediation-crow-defects
plan: 07
subsystem: acceptance
tags: [acceptance-gate, self-auditing, flag-dont-guess, falsified-premises, phase-limits,
       coincidence-trap, crow, paid-run-evidence]

# Dependency graph
requires:
  - phase: 28-accuracy-remediation-crow-defects
    provides: "the six test modules 28-01…28-06 added, each of which this gate INVOKES rather than restates"
  - phase: 23-measurement-engine
    provides: "`test_phase23_acceptance.py` — the three rules this gate inherits, and D1's declared-layer exception it re-proves"
  - phase: 24-determinism
    provides: "`test_phase24_acceptance.py` and the 24-09 differential, both invoked here off ONE shared run; the assemble-from-halves and `importlib` idioms"
provides:
  - "tests/test_phase28_acceptance.py — 14 checks, free, self-auditing, 6:42"
  - "one check per requirement, each asserting shipped behaviour or skipping by a named reason"
  - "a three-way census proving every phase-28 module was consulted: intended == invoked == on disk"
  - "the phase's four declared limits as runnable claims, TWO of which are measured to have been closed by later work"
  - "a shape-based golden-comparison scan over every module this phase added, with its own limits documented"
affects: [25, 29]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "a gate written after the tree has moved on separates what the phase DELIVERED from what the phase LEFT BEHIND, and re-measures the second"
    - "a limit is a check, and a limit that has been CLOSED is also a check — otherwise the record rots into a claim nobody re-verifies"
    - "the census asserts three sets equal, not two: intended, invoked, and the modules on disk — only the third sees a module nobody declared"
    - "a self-grep excises its own function by source text where it must state the shape it hunts, and assembles from halves everywhere else"

key-files:
  created:
    - tests/test_phase28_acceptance.py
  modified:
    - tests/test_phase28_region_fanout.py

key-decisions:
  - "V4-FIX-01 and V4-FIX-03 are NOT ticked, and in both cases the reason is a check invoked from inside the requirement's own gate rather than a sentence anywhere."
  - "No check claims the tie refusal fixed Crow. The shortlist's maximum is asserted UNIQUE on the plan page — the positive form of 'there was no tie' — so the account of what fixed the drawing cannot drift."
  - "The LF-share masonry guard is measured to exclude only the DOMINANT class, which the pre-existing rank test already excluded; more than one class survives both guards, so mutual uniqueness is what refuses. The guard is not credited."
  - "`Door Frames-HM` is named as a literal, deliberately, and compared against a set COMPUTED at runtime from the frozen evidence — a falsification only a computation implies is one no future reader can grep for."
  - "The phase's Columns and Ladder limits were re-measured on today's tree and are FALSE: later detection work closed both. The gate asserts the closure."
  - "One differential is built here and handed to both the 24-09 harness and the 24-10 gate, so re-proving phase 24 costs one offline pipeline pair rather than two."

patterns-established:
  - "Re-measure a phase's declared limits at gate-writing time. A limit inherited from a summary is a prediction; a limit asserted against the current tree is a fact."
  - "Assert an exemption explicitly instead of filtering it out of a loop — an exemption nobody checks is a hole (the injected-convention route)."
  - "Locate a published row through its audit trail rather than by its canonical name, so the check pins the behaviour and not the canonicaliser."

# V4-FIX-02, V4-FIX-04 and V4-FIX-05 are closed by this gate, each with its narrowing
# asserted in the same module. V4-FIX-01 and V4-FIX-03 remain ADVANCED: their residuals were
# measured to be open by 28-03 and 28-04 respectively, are unchanged, and are pinned by
# tripwires this gate invokes. Ticking either would be the over-claim this phase exists to end.
requirements-completed: [V4-FIX-02, V4-FIX-04, V4-FIX-05]
requirements-advanced: [V4-FIX-01, V4-FIX-03]

coverage:
  - id: D1
    description: "Each of the five requirements has a check that asserts shipped behaviour or skips with a reason naming what was missing"
    verification:
      - kind: unit
        ref: "tests/test_phase28_acceptance.py#test_v4_fix_01_an_uncorroborated_count_cannot_publish_measured_and_is_not_ticked"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_acceptance.py#test_v4_fix_02_the_ring_test_refuses_a_filled_lattice_and_no_tie_decided_crow"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_acceptance.py#test_v4_fix_03_a_non_discriminating_thickness_binds_nothing_and_is_not_ticked"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_acceptance.py#test_v4_fix_04_one_region_one_row_per_layer_and_d1_survives"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_acceptance.py#test_v4_fix_05_every_quantity_states_its_route_and_a_blank_carries_none"
        status: pass
      - kind: integration
        ref: "tests/test_phase28_acceptance.py#test_v4_fix_05_the_row_presence_axis_is_named_and_it_is_door_frames_hm"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every module this phase added is invoked and PROVED invoked — intended, invoked and on-disk sets asserted equal"
    verification:
      - kind: unit
        ref: "tests/test_phase28_acceptance.py#test_every_module_this_phase_added_was_consulted_and_the_sets_agree"
        status: pass
    human_judgment: false
  - id: D3
    description: "Phase 24's determinism guarantee still holds under this phase's three fusion changes and three aggregator changes"
    verification:
      - kind: integration
        ref: "tests/test_phase28_acceptance.py#test_phase_24_still_holds_under_this_phases_fusion_changes"
        status: pass
    human_judgment: false
  - id: D4
    description: "The gate is free and compares no Crow golden figure, asserted of itself and of every module it invokes"
    verification:
      - kind: unit
        ref: "tests/test_phase28_acceptance.py#test_the_whole_gate_runs_free"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_acceptance.py#test_no_module_in_this_phase_compares_a_quantity_to_a_crow_golden"
        status: pass
    human_judgment: false
  - id: D5
    description: "The frozen paid evidence is present, non-hollow and unmodified, and this check FAILS rather than skips"
    verification:
      - kind: unit
        ref: "tests/test_phase28_acceptance.py#test_the_paid_run_evidence_is_intact_and_this_check_fails_rather_than_skips"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_acceptance.py#test_the_evidence_check_fails_rather_than_skipping_when_the_directory_is_absent"
        status: pass
    human_judgment: false
  - id: D6
    description: "The phase's four declared limits are runnable claims, and the two later work closed are asserted as closed"
    verification:
      - kind: integration
        ref: "tests/test_phase28_acceptance.py#test_the_limits_phase_28_declared_two_of_which_later_work_closed"
        status: pass
      - kind: unit
        ref: "tests/test_phase28_acceptance.py#test_no_requirement_is_ticked_that_this_phase_measured_to_be_open"
        status: pass
    human_judgment: false
  - id: D7
    description: "An estimator reading a phase-28 report — a withheld Stairs blank, a flagged CMU hint bind, a reproducibility section — acts on it correctly"
    verification: []
    human_judgment: true
    rationale: "Every one of those artifacts is estimator-facing prose whose STRUCTURE is pinned by tests but whose readability cannot be judged without a paid run, which is a human spend decision. `score_report_dir.py` re-scores frozen artifacts and returns the same numbers whatever the code does."

# Metrics
completed: 2026-08-14
status: complete
---

# Phase 28 Plan 07: The Acceptance Gate Summary

**Fourteen checks, free, six minutes and forty-two seconds — and the two things it refuses to say
are worth more than the twelve it does: `V4-FIX-01` and `V4-FIX-03` are not ticked, and the reason
each is not ticked is a check invoked from inside that requirement's own gate. Re-measured on today's
tree, two of the four limits this phase declared for itself have been CLOSED by later detection work
rather than by Phase 25, and the gate asserts the closure instead of repeating a claim that has
stopped being true.**

## What this gate asserts, and what it refuses to

| requirement | status | what the gate holds |
|---|---|---|
| V4-FIX-01 | **advanced** | an uncorroborated count cannot publish `MEASURED`; a printed-schedule count still does; a detail-sheet count publishes a blank quoting its withheld reading. **Not ticked:** two calculator producers still emit EA counts with no verdict, and 28-03's tripwire — invoked here — fails the day either is fixed. |
| V4-FIX-02 | **complete** | on the real plan page the perimeter hint's candidate list is non-empty and its binding set is empty, so the refusal is a decision. A hollow ring still passes; a filled lattice and a sparse scatter do not. |
| V4-FIX-03 | **advanced** | a thickness two objects both print binds neither; a thickness fitting two classes binds neither; a unique match still binds. **Not ticked:** the masonry object still falls through to a non-confident hint bind, asserted here as non-confident. |
| V4-FIX-04 | **complete** | two evidence-named rows and one hypothesis-named row on one region publish two numbers and one blank; three evidence-named layers on one region publish three. |
| V4-FIX-05 | **complete as narrowed** | every published quantity states its route, a blank and an injected convention state none, `summary.txt` names exactly the reading-route rows — and the one quantity the classification cannot explain is named. |

## Four falsified plan premises, each an assertion rather than a paragraph

1. **The 56-vs-56 tie does not exist.** `SYM-3` is excluded by `_is_small_marker` before candidacy,
   so the shortlist already had a unique maximum and list order decided nothing on Crow. The gate
   asserts the POSITIVE form — `counts.count(top) == 1` on the real page — so no future reader can
   infer that the tie rule is what fixed the drawing. The tie rule is invoked as a hardening, on
   synthetic candidates, where a tie can actually be built.
2. **The plan's own fix alone would have swapped one wrong name for another.** An 8-mark cluster
   clears the 25%-inset hollowness test *vacuously*, because a quarter-area inset lets a sparse
   scatter through by luck. The positive-evidence clause is what closes it, and both the vacuity
   demonstration and the sparse-scatter refusal are invoked here.
3. **The wall-class contest is ONE object against THREE classes, not two objects against one.** The
   gate builds both axes synthetically and then measures the real sheet. **The LF-share guard did not
   fire:** computed here, the share test excludes only the dominant class, which the pre-existing
   rank test already excluded — and more than one class survives both guards, which is exactly why
   mutual uniqueness is what refuses. The guard is not credited anywhere.
4. **`Door Frames-HM` moved because a ROW vanished, not because a number moved.** The differing keys
   are computed at runtime from the two frozen runs and each is classified through 28-06's own
   helpers; only then is the vanished-row set compared against the name. The literal is deliberate —
   a falsification a computation only implies is one nobody can grep for.

## The limits, re-measured — and two of them are no longer true

This gate was written a week after the phase's last code commit, on a tree carrying twenty-two later
commits (production Day 1 / Day 2 and the detection harness). The five DELIVERED contracts all still
hold. Two of the four LIMITS do not, and pretending otherwise would have shipped a green gate
asserting a falsehood.

**Still standing**

- The perimeter hint names nothing on the plan page, and its candidate list is non-empty — so this is
  a refusal, not an absence of input. 28-02's fix is in fact *more* load-bearing than when it
  shipped: the cluster it now refuses is the full 120-marker lattice.
- The extraction pass is disclosed, not stabilised. Stabilising it needs repeated sampling of a paid
  pass, which is not autonomously authorised. The disclosure exists and the variance is still
  measurable in the frozen evidence.

**CLOSED BY LATER WORK — not by Phase 25, which this phase named as their owner**

- **Columns.** The plan text for this gate says "Crow's `Columns` and `Ladder` remain unmeasured —
  they need detection, which is Phase 25". Measured on today's tree, the plan page yields a lattice
  candidate the deterministic namer calls `Columns` and the structural-grid hint binds. That landed
  in `4e6382f` / `7390f09`. It changes nothing phase 28 delivered; it changes what may be said about
  what phase 28 left behind.
- **The Ladder route.** `_KEYNOTE_NUM_RE` accepted exactly two digits, so keynotes 1-9 were
  structurally invisible and the access-ladder keynote never entered the pipeline. It is widened
  (`9276d00`) and the plan page's legend carries that note. Whether the published count is right is
  not claimed — only that the route is no longer absent.

Both closures are asserted, so the record cannot rot back into a claim nobody re-checks, and a
REOPENING of either goes red with a message saying the gate's account must be rewritten rather than
deleted.

## Non-vacuity: the gate has been seen to fail

- `_count_is_uncorroborated` forced to `False` → the V4-FIX-01 check goes red.
- `_is_built_from_ring_runs` forced to `True` → the V4-FIX-02 check AND the limits check both go red.
- Both mutations were reverted and `git status --porcelain src/` confirmed empty before the commit.
- The evidence check was observed raising `AssertionError`, not `Skipped`, when pointed at an absent
  directory — the committed demonstration patches through the function's own `__globals__`, because
  this file can be imported under more than one module name and a patch landing elsewhere would leave
  the check quietly passing against the real tree.
- The golden-shape scanner is proved on a text built to trip it, and proved NOT to fire on a
  coincidental number inside a tuple, before it is trusted on a clean result.

## Deviations from Plan

### 1. [Rule 1 — the plan's stated limits were measured FALSE] Columns and Ladder are no longer unmeasured

- **Plan asked for:** checks recording that "Crow's `Columns` and `Ladder` remain unmeasured — they
  need detection, which is Phase 25".
- **Measured:** false on today's tree, for both, by post-phase-28 work. Writing the plan's checks as
  specified would have produced a RED gate, and narrowing them until they passed would have been the
  coincidence trap in a different costume.
- **What was done:** the limits check asserts the two that still stand and asserts the two that were
  closed, naming the commits and stating that the closure was not Phase 25's. Reopening either is a
  failure with an instruction attached.

### 2. [Rule 2 — Missing Critical] A phase-28 module carried literal paid tokens

- **Found during:** the first run of the free-scan.
- **Issue:** `tests/test_phase28_region_fanout.py` spelled `ANTHROPIC_API_KEY`, `accuracy_gate`,
  `vision_only_benchmark` and `golden_convergence` out as literals inside its own audit function. It
  kept itself honest by excising that function from the source it scanned — which works for a module
  auditing itself and fails the moment an OUTSIDE scanner reads the file whole, which is precisely
  what this gate does. A paid token sat in the free acceptance path with nothing actually wrong.
- **Fix:** the tokens are assembled from halves, the phase-wide idiom every other module in this
  phase already used, with a non-vacuity positive control added. The excision is kept; the two are
  complementary.
- **Verification:** `tests/test_phase28_region_fanout.py` → 29 passed (unchanged count);
  `test_the_whole_gate_runs_free` green over all nine scanned modules.

### 3. [Rule 1 — the gate's own self-grep found itself] The golden-shape check states the shape it hunts

- **Issue:** the check's docstring must say which shape it catches and which it does not, and its
  positive control must contain a real comparison. Both made the check find itself.
- **Fix:** every other literal in the module is assembled from halves; this ONE function's source is
  excised from the text it scans, by source text rather than by line range so it cannot drift. The
  free-token scan is unaffected and still reads the whole file with nothing excised.

### 4. [Plan expectation that did not materialise] An injected convention publishes a number and no route

- **Plan asked:** "assert every published quantity carries a route".
- **Measured:** `Mobilization` publishes `1.0` and carries no route, deliberately — it is an
  app-injected convention, not a reading of the drawing, so there is nothing to characterise (28-06's
  decision 3).
- **What was done:** the exemption is asserted EXPLICITLY — identified by published status rather
  than by name, with a non-vacuity guard that the fixture actually produced one — instead of being
  filtered out of the loop. An exemption nobody checks is a hole.

### 5. Runtime is 6:42, not "about five minutes"

The plan estimated ~5 min. Measured: **6:42**, of which roughly three are the shared 24-09
differential (two full offline pipeline runs) and the rest is three deterministic parses of the Crow
fixture page — one for this gate and one each for the two sibling modules the census consults, whose
caches are per-module. It was not trimmed: dropping the differential would have removed the only
thing in this gate that re-proves phase 24 under this phase's six fusion/aggregator changes.

## The offline suite, and why the plan's baseline arithmetic could not be used

**`python3 -m pytest -q` → 2529 passed, 1 skipped, 2 deselected in 1:11:51.** Zero failures. The four
standing gates — `test_phase23_acceptance.py`, `test_phase24_acceptance.py`,
`test_four_set_coverage.py` and the 24-09 determinism harness — are all inside that run.

The plan's verification block names a baseline of **2183**, and 28-04's summary reconciles a baseline
of **2264**. Neither can be used here: twenty-two commits of production and detection work landed
between phase 28's last code commit and this one, adding tests of their own. The arithmetic that CAN
be shown is this plan's own delta — this module contributes exactly the 14 checks it defines
(`tests/test_phase28_acceptance.py` → 14 passed standalone) and
`tests/test_phase28_region_fanout.py` is unchanged in count at 29, so the pre-plan tree stood at
**2515** runnable. Reporting 2183 + N would have been arithmetic against a tree that no longer
exists.

The first attempt at this run was lost: the tool backgrounded it at its own 600 s ceiling and then
killed it at ~62 minutes with an empty output file. It was relaunched orphaned (`nohup python3 -u -m
pytest -q > log`) and polled in the foreground until the summary line appeared.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | No paid marker, script or credential anywhere in the gate or in the nine modules it scans; `pytest.ini` asserted to deselect the paid marker by default. `.env` never read. |
| Python 3.9 | `from __future__ import annotations`; no 3.10+ syntax. |
| Never tune to golden | `test_no_module_in_this_phase_compares_a_quantity_to_a_crow_golden` — a shape scan across this gate and all six phase-28 modules; zero hits. Its limits are stated in its own docstring. |
| `.planning/paid-run-evidence/` read-only | `git status --porcelain` over that path → `0`, asserted inside the gate as well as at the shell. |
| `uploads/`, `human_inputs/`, `reports/`, `.env` untouched | Not read, not written, in no commit. The real-geometry checks use the committed fixture PDF. |
| `AGENTS.md`, `CLAUDE.md`, `tests/fixtures/synthetic/*.pdf` not committed | Those five carry pre-existing unstaged modifications; no commit of this plan contains them. |

## Risk Warning (CLAUDE.md gitnexus mandate)

The GitNexus index is **stale** (last indexed `5fab264`, twenty-three commits behind). No production
symbol was edited by this plan — the only source change is one test module's token spelling — so no
impact analysis was run against a stale graph and none was needed. **The index should be re-analysed
before the next plan that edits `fusion.py`, `aggregator.py` or `calculator.py`.**

## Next Phase Readiness

- **Phase 28's acceptance is one free command:** `python3 -m pytest -q tests/test_phase28_acceptance.py`.
- **Phase 25's scope fence has moved and it must be re-planned before it is executed.** Its stated
  subjects were Columns, Ladder and Bollards detection. Two of those now have working deterministic
  routes that landed outside it. Whoever plans Phase 25 should start from what the harness measured,
  not from this ROADMAP's Phase 25 text.
- **Two requirements stay open with named, greppable residuals.** V4-FIX-01 needs a verdict stamped
  on `_calculate_from_measurement`'s whole-EA path and on `_calculate_from_civil_structures`;
  V4-FIX-03 needs an evidenced masonry binder to replace pass 2's "masonry is the smallest class"
  assumption. Each has a tripwire that fails when it is closed — shorten it deliberately, never
  delete it.
- **No accuracy figure was produced and none can be.** `score_report_dir.py` re-scores frozen
  artifacts and returns the same numbers whatever the code does. A post-fix Crow number requires a
  paid run, which is a human spend decision.

---
*Phase: 28-accuracy-remediation-crow-defects*
