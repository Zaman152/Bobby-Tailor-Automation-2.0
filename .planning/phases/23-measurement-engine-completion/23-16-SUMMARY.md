---
phase: 23-measurement-engine-completion
plan: 16
subsystem: docs + testing (record correction + acceptance harness)
tags: [record-correction, D-01, D-07, acceptance-gate, probes, INV-02, INV-04, INV-05, INV-08, DEF-23-SP4]
status: complete

requires:
  - phase: 23-01
    provides: "tests/test_four_set_coverage.py — the D-05 gate this plan's check 1 INVOKES rather than restates"
  - phase: 23-05
    provides: "the in-plan unit-tag census that falsifies §13.3's BLOCKER A"
  - phase: 23-09
    provides: "the sixteen-sheet RCP baseline, the shape-ratio primitive, and the first of the two superseded-test rewrites"
  - phase: 23-11
    provides: "cross_check_extent (the second superseded-test rewrite) and the measured falsification of the clip-cell partition rule (DEF-23-SP4)"
  - phase: 23-12
    provides: "the position-validated linetype and rail selectors checks 9 and 10 assert"
  - phase: 23-15
    provides: "the 1831-passed offline baseline this plan holds green, and the phantom-LF kill check 10 asserts at the unit"
provides:
  - "tests/test_phase23_acceptance.py — THE phase gate: 23-RESEARCH §5.3's thirteen checks as 15 named tests, check 1 invoking the four-set gate"
  - "scripts/geom_probe.py: the full §5.1 field set (perimeter, shape ratio, height + source, elevation areas, linear runs, excluded viewports) + --pages="
  - "scripts/fusion_probe.py: PDF/page arguments and per-basis-binder routing, replacing two constants hardcoded to Crow page 1"
  - "docs/PIPELINE-GROUND-TRUTH.md: four corrected passages, each with old claim / falsifying evidence / citation / delivered contract"
  - "the §14 blind table recomputed on ONE stated basis (44,010.9 vs 41,912 = +5.0%)"
  - "amended ROADMAP Phase 23 criteria 2 and 4, and amended REQUIREMENTS V4-MEAS-02 and V4-MEAS-04"
affects:
  - "/gsd-verify-work — it now reads criteria that describe the contract this phase delivered, not a falsified premise"
  - "Phase 24 — the acceptance gate is the regression floor every later phase must keep green"
  - "any future session reading docs/PIPELINE-GROUND-TRUTH.md — it no longer points at three dead ends"

tech-stack:
  added: []
  patterns:
    - "a correction states four things or it is a scope reduction: the ORIGINAL wording, the falsifying evidence, the citation, and the delivered contract"
    - "an acceptance gate INVOKES the tests that own each criterion rather than copying their literals, so it cannot drift from them"
    - "a published figure states its PROVENANCE — a probe calling the engine directly is not a run"
    - "a criterion that was NOT delivered is named with its blocker, never quietly dropped from the gate"
    - "a check that cannot run SKIPS by name; a gate that passes for having looked at nothing is worse than no gate"
    - "a deny list is assembled from fragments when the file is itself grepped for those literals — otherwise the check fails on its own definition"

key-files:
  created:
    - tests/test_phase23_acceptance.py
  modified:
    - docs/PIPELINE-GROUND-TRUTH.md
    - scripts/geom_probe.py
    - scripts/fusion_probe.py
    - tests/test_room_fill.py
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "The §14 blind table was RECOMPUTED offline rather than reasoned about, and the recomputation surfaced a second defect the plan did not anticipate: the published TOTAL row (45,837 / 42,835 = 7.0%) does not equal the sum of its own nine rows (44,011 / 41,912 = +5.0%). All nine per-sheet values reproduce exactly on today's engine, so the rows are right and only the total was unsourced. Both facts are recorded."
  - "Check 4 does NOT assert clip invariance, because the phase did not deliver it. 23-11 closed on Task 3 of 4 by orchestrator decision and SP-4 is blocked behind DEF-23-SP4. The check names that by name and asserts the two halves that WERE delivered. Asserting a criterion nobody met would be the same failure as the passages this plan exists to correct."
  - "Check 2 does not assert Bob's p3 page-level fpp 0.148148 (DEF-23-08 — select_main_plan returns None on that sheet and both fixes are the retune-a-constant trap). It asserts the VIEWPORT binding of 10.666667, which is what every measurement on that sheet actually uses."
  - "The FORBIDDEN deny list is assembled from string fragments. The phase's own acceptance command greps this very file for those five literals, so writing them out would fail the no-paid-command check while nothing was wrong; the assembled string is what is searched for, so the check is not weakened."
  - "Check 12 was SPLIT into 12 (the contract, always asserts) and 12b (the saved-run replay, skips when absent). Folded together, a clean checkout reported the whole check as 'skipped' — which reads as 'nothing was verified' when the contract had in fact been asserted. That is the blank-versus-zero ambiguity one layer up."
  - "Task 2's substance had already been delivered by 23-09 and 23-11, which rewrote both superseded tests IN PLAN rather than leaving a red suite standing across seven plans. This plan closed the remaining gap — section-level citations and both directions asserted in one place — rather than manufacturing work to match the plan text."
  - "No src/ file is touched by this plan at all, so no symbol impact analysis was owed. The gitnexus MCP tools were not available in this executor; the claim is verified directly by `git diff --stat 16a5741..HEAD -- src/` returning empty."

requirements-completed: [V4-MEAS-01, V4-MEAS-02, V4-MEAS-03, V4-MEAS-04, V4-MEAS-05, V4-MEAS-06]

coverage:
  - id: D1
    description: "The honesty anchor no longer asserts a falsified cause: four corrected passages, each with its old claim, the evidence that disproved it, a citation and the delivered contract"
    requirement: V4-MEAS-02
    verification:
      - kind: other
        ref: "python3 -c \"...('INV-02','INV-04','INV-05','INV-08') all present in docs/PIPELINE-GROUND-TRUTH.md\" -> 'citations present'"
        status: pass
      - kind: other
        ref: "git diff -U0 docs/PIPELINE-GROUND-TRUTH.md — 21 removed lines, every one inside the four corrected passages; no section deleted"
        status: pass
    human_judgment: false
  - id: D2
    description: "A published accuracy figure states whether it came from a run or from a direct call to the engine, and its table is recomputed on ONE named basis"
    requirement: V4-MEAS-01
    verification:
      - kind: other
        ref: "offline recomputation probe: measured RCP fill x census count = 44,010.9 vs golden 41,912 (+5.0%), all nine rows reproducing §14 exactly"
        status: pass
    human_judgment: false
  - id: D3
    description: "The two shipped tests that encoded the superseded story assert the corrected behaviour, cite the section that superseded it, and were not deleted"
    requirement: V4-MEAS-02
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_the_measured_area_is_checked_against_the_drawings_own_printed_extent (both directions in one test)"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_an_oversize_region_is_kept_and_flagged_never_dropped"
        status: pass
      - kind: other
        ref: "104 test functions before and after; python3 -m pytest -q tests/test_room_fill.py -> 120 passed"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every acceptance check for this phase is a committed command, gathered into ONE runnable gate, with check 1 invoking the four-plan-set gate"
    requirement: V4-MEAS-06
    verification:
      - kind: integration
        ref: "python3 -m pytest -q tests/test_phase23_acceptance.py tests/test_four_set_coverage.py -> 28 passed, 1 skipped (14m37s)"
        status: pass
      - kind: unit
        ref: "tests/test_phase23_acceptance.py::test_check_01_coverage_the_four_plan_set_gate_is_re_asserted — calls nine of the gate module's own assertion functions"
        status: pass
    human_judgment: false
  - id: D5
    description: "The whole phase acceptance runs free — no paid script, no paid marker, no credential anywhere in it"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_phase23_acceptance.py::test_check_13_the_whole_gate_runs_free"
        status: pass
      - kind: other
        ref: "the plan's own one-liner grepping the module for the five literals -> 'free gate'"
        status: pass
    human_judgment: false
  - id: D6
    description: "The five probes cover the §5.1 field set: geom_probe reports perimeter/shape ratio/height+source/elevations/runs/exclusions; fusion_probe takes a PDF and a page"
    requirement: V4-MEAS-03
    verification:
      - kind: other
        ref: "python3 scripts/geom_probe.py <Moxy> --pages=23,27 -> FILL ... perimeter=271.7 LF shape_ratio=5.1 height=9.0 ft (drawing), plus ELEV/RUN/EXCLUDED/DROP rows"
        status: pass
      - kind: other
        ref: "python3 scripts/fusion_probe.py <pdf> <page> [--type] [--json] — argparse, no hardcoded fixture"
        status: pass
    human_judgment: false
  - id: D7
    description: "No success criterion or requirement in the planning record still asserts a premise this phase's investigation falsified, and each amendment is distinguishable from a scope reduction"
    requirement: V4-MEAS-04
    verification:
      - kind: other
        ref: "the plan's verify one-liner -> 'amendments cited, roadmap intact'; the phase-23 structural one-liner -> 'phase 23 section intact'"
        status: pass
      - kind: other
        ref: "git diff -U0 on ROADMAP + REQUIREMENTS — exactly 3 removed lines, all of them the amended lines; 28 phase entries retained"
        status: pass
    human_judgment: false
  - id: D8
    description: "The offline suite stays green at or above its baseline"
    requirement: V4-MEAS-06
    verification:
      - kind: integration
        ref: "python3 -m pytest -q -> 1845 passed, 1 skipped, 2 deselected in 45m56s (baseline after 23-15: 1831 passed / 2 deselected)"
        status: pass
    human_judgment: false

metrics:
  duration: ~4h15m
  completed: 2026-08-04
  tasks: 4
  commits: 4
  tests_added: 15
  suite: "1845 passed, 1 skipped, 2 deselected (baseline 1831 passed / 2 deselected)"
---

# Phase 23 Plan 16: Correct the Record + Lock the Free Harness Summary

**The project's honesty anchor no longer asserts three causes that probes disproved, its headline
accuracy figure now says it came from a probe calling the engine directly rather than from a run
that could not reach those sheets, and its blind table is recomputed on ONE stated basis — a
recomputation that turned up a second defect nobody had noticed: the published TOTAL row does not
equal the sum of its own nine rows. The planning record was corrected to match, with each amendment
stating the original wording, the falsifying evidence, its citation and the delivered contract so a
reader can tell a correction from a scope reduction. And the phase's acceptance, which lived in
investigation transcripts, is now ONE runnable gate of fifteen named tests whose first check invokes
the four-plan-set gate rather than restating it — 28 passed, 1 skipped, and not one paid command in
it.**

## Performance

- **Duration:** ~4h15m (of which ~1h05m is offline measurement: the acceptance gate at 14m37s and
  the full suite at 45m56s)
- **Tasks:** 4 of 4, one commit each
- **Files:** 1 created, 6 modified — 1,597 insertions, 94 deletions
- **`src/` files touched: ZERO.** This plan corrects a record and locks a harness; it changes no
  production behaviour, and that is verifiable in one command.

## What shipped

### Task 1 — the four corrections, each traceable to the probe that produced it (`5380bab`)

Every correction is written as a block stating **the old claim, the falsifying evidence, the
citation, and the delivered contract**, with the superseded sentences struck through in place rather
than deleted — a reader arriving at the original wording is carried to the correction instead of
finding a silent gap.

**§9 — there is no civil sheet.** The claim that Bob's Gas Piping 886 LF is "civil linework"
requiring a "civil-sheet engine reading piping/curb/utilities on C-sheets" is replaced by the sheet
listing: seven sheets, **no C-sheet and no P-sheet**, and the `C402.4` cited as proof is an IECC
energy-code table reference inside a note on A4.0, matched by a sheet-number regex. The run is an
annotated CAD linetype on the **A3.0 roof plan** — a sheet type already inside `_PLAN_SHEET_TYPES`.
The frontier was open-run linear measurement on any plan sheet, and that is what shipped
(INV-04 §1–§3).

**§13.3 — the multiplier IS in the input.** "BLOCKER A" asserted that nothing in the PDF states
"90 × QQ A" and that a human must therefore supply the counts. A blind census of the set's own two
unit key plans reads **214 tags / 214 distinct room numbers / 0 duplicates** and reproduces **4 of 4**
golden multipliers. The correction records the census figure as **214**, not INV-05's 217 — the
three-tag difference is multi-line room names and touches none of the four multipliers (INV-05 §2
Key B; 23-05, 23-08).

**§14 — the provenance of the 7.0% figure, and the table recomputed.** See below; this is the
correction that grew.

**§14.2 — the clip is exonerated.** The three probes are stated as evidence rather than referenced:
bit-identical across a 240 pt range of clip widths while ID-407/ID-415 move +17%/+20%; every counted
region inside 47% of the clip; fill against the drawing's own printed `17'-0 1/8" × 26'-9 1/8"` at a
ratio of **1.007**. The real defect is an unverified `unit_count` of 2 derived from a golden
`Doors-WD 2 EA` — on a suite, an entry door plus a connecting door in ONE unit. **The passage's
correct instruction — "fix the clip, not the threshold" — is kept**, and the correction says which
half of it was delivered and which is still open under DEF-23-SP4.

The superseded docstring in `src/` needed no work: 23-11 had already corrected it inside
`cross_check_extent`, with the three falsifying probes named.

### The recomputation, and the defect it found

The plan asked for §14's blind table to be recomputed on ONE basis, with that basis stated. The
basis chosen: **the shipped engine's measured RCP fill × the unit count the in-plan census
resolves**. Run offline, zero API:

| | measured | golden | err |
|---|---|---|---|
| the same nine rows | **44,010.9** | **41,912** | **+5.0%** |
| as published in §14 | 45,837 | 42,835 | 7.0% |

All nine per-sheet values reproduce §14's originals **exactly** on today's engine — so the rows were
right. What was not right is the TOTAL row: it does not equal the sum of the rows above it, on
either side. That was not in the plan's brief and is recorded because a total nobody can reconstruct
is exactly the kind of figure this plan exists to stop.

The document also now states that the table **excluded four sheets** and that all four carry a
multiplier flag today — ID-412/ID-416 publish the census's 1 against a manifest declaring 2, and
ID-420/ID-422's 2 is manifest-only with no key-plan tag confirming it — so correcting the multiplier
legitimately moves the total **away** from golden, and that movement is not a regression.

### Task 2 — the two superseded tests (`9dfe9c6`)

**Both had already been rewritten, and that is the honest finding.** 23-09 inverted the oversize
test (deviation 5: "leaving a red suite standing across seven plans would mean every plan from 23-10
to 23-15 executes against a baseline that already fails") and 23-11 replaced the plausibility cap
with `cross_check_extent`. Manufacturing work to match the plan text would have been theatre.

What was genuinely missing, and what this task added: the cross-check test now asserts **both
directions in one place** (a fill matching its printed extent is not flagged; roughly double the
bound is), and both docstrings now cite the investigation **by section** — INV-02 §2/§3/§4 for the
three probes, INV-02 §5 for the guard that sat on the wrong side of the multiplication — rather than
by document alone. The oversize test records that it is the **inversion** of
`test_max_region_guard_rejects_sheet_scale_regions` and why a guest-room-shaped constant silenced
every lobby, ballroom and retail floor plate. 104 test functions before and after; nothing deleted.

### Task 3 — the probes, and ONE runnable gate (`346d9b4`)

**`scripts/geom_probe.py`** now emits the full 23-RESEARCH §5.1 field set per page: every room fill
with its **perimeter, shape ratio, wall height and height SOURCE** (plus bound and extent ratio), the
**elevation areas** with width, datum crop and exclusion, the **linear runs** converted at each run's
own drawing scale, and the **excluded viewports** kept separate from failures — because a deliberate
off-scale exclusion is correct behaviour and must stay legible as such. Gained `--pages=` so a
targeted check costs seconds. On Moxy p23 it prints `perimeter=271.7 LF shape_ratio=5.1 height=9.0 ft
(drawing)` for the RCP fill and `shape_ratio=8.6` for the architectural one — INV-01's leak signature,
visible in one command.

**`scripts/fusion_probe.py`** takes a PDF and a page instead of two constants hardcoded to Crow page 1,
and reports which **basis binder** each measured primitive would route through — the question that
could not be asked of any other sheet before, and the reason `basis: linear` sat with no consumer for
a whole release.

**`tests/test_phase23_acceptance.py`** gathers §5.3's thirteen checks into fifteen named tests. Three
rules are written into the module header and enforced by its contents:

- **Check 1 INVOKES the four-plan-set gate.** It calls nine of `tests/test_four_set_coverage.py`'s
  own assertion functions against a live audit rather than copying its literals, so the gate that
  guarded every classification and scale change in this phase is exercised one last time and cannot
  drift from a second copy.
- **The gate locks what SHIPPED.** Chelsea titles **29** exterior elevations, not §5.3's 21; BUNK A's
  ceiling is **9'-8"**, not 9'-0"; Bob's p3 binds 10.667 at the **viewport**, not the page (DEF-23-08);
  ID-412/416 are among the *tightest* extent fits in the set, which is the falsifying evidence itself
  turned into an assertion.
- **A criterion that was not delivered is named, never dropped.** Check 4 does not assert clip
  invariance; it states that 23-11 closed on Task 3 of 4, that the partition rule is falsified on the
  fixtures (best variant: 4 of 16 sheets), that it is blocked behind **DEF-23-SP4**, and it asserts
  the two halves that were delivered.

Nothing in the module asserts against Guard Rail 420.35, Hand Rail 438.80, the 16,219 SF painting
figure, or INV-00 §1e's simulated total. Bands, positions and sets only.

### Task 4 — the planning record (`a2a5eec`)

**ROADMAP criterion 2 + V4-MEAS-02.** Amended to record the clip exoneration and name the unverified
unit count as the real defect, while still asserting **both surviving halves**: the guest-room-sized
threshold is gone and replaced by a dimensionless printed-extent ratio, and the clip is
rotation-correct and page-space bounded. **V4-MEAS-02's "not by a guestroom-sized plausibility
threshold" clause is retained verbatim** — it is delivered as written and is explicitly not weakened.
SP-4 is recorded as still open under DEF-23-SP4 rather than dropped.

**ROADMAP criterion 4 + V4-MEAS-04.** Neither still asserts that an AREA is assigned to a room. Three
findings are stated: no finish schedule exists in the input (CS-03 indexed, absent from the PDF; the
`finish` kind fires zero times on all four sets), the wall-covering quantities are interior-ELEVATION
quantities, and no area is obtainable (a seeded fill leaks 4–10× because an elevation wall face is
not a closed ink region). Rewritten to the delivered contract: a **named, flagged, zero-quantity row**
per called-out code, seeded with its tag positions, validated by exact code SET on six of six sheets
including a true negative — and **no synthesized area**, because emitting one would violate the
phase's own flag-don't-guess contract.

Diff discipline: **3 lines removed across both files, every one of them an amended line**, each
re-emitted with its original wording quoted. No phase entry, no plan entry, no goal line, no other
criterion and no other requirement touched; the roadmap keeps all **28** phase entries.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1845 passed, 1 skipped, 2 deselected** (45m56s; baseline 1831 passed / 2 deselected) |
| `pytest -q tests/test_phase23_acceptance.py tests/test_four_set_coverage.py` | **28 passed, 1 skipped** (14m37s) |
| Check 1 invokes the four-set gate | 9 of its assertion functions called against a live audit |
| The gate contains no paid command | plan's own one-liner prints `free gate` |
| Ground-truth citations | `citations present` (INV-02 / INV-04 / INV-05 / INV-08) |
| `git diff -U0 docs/PIPELINE-GROUND-TRUTH.md` | 21 removed lines, all inside the four passages; 15 `##` sections before and after |
| ROADMAP / REQUIREMENTS amendments | `amendments cited, roadmap intact` + `phase 23 section intact` |
| `git diff -U0` on both planning files | 3 removed lines, all of them the amended lines |
| `tests/test_room_fill.py` | **120 passed**; 104 test functions before and after |
| `geom_probe` §5.1 field set | perimeter / shape ratio / height + source / elevations / runs / exclusions all printed |
| `fusion_probe` parameterised | `<pdf> <page> [--type] [--json]`, no hardcoded fixture |
| `ast.parse(..., feature_version=(3,9))` | `py39 ok` on all three changed/created Python files |
| `git diff --stat uploads/ human_inputs/ reports/` | **EMPTY** |
| `git diff --stat 16a5741..HEAD -- src/` | **EMPTY** — no production code touched |

**No paid command was run.** None of the four paid scripts was executed, the paid pytest marker was
never selected, and `.env` was not read. Every number above came from a free offline probe or the
offline suite.

### Impact analysis (CLAUDE.md)

**No symbol impact analysis was owed: this plan modifies no `src/` file**, verified by
`git diff --stat 16a5741..HEAD -- src/` returning empty. The gitnexus MCP tools were not available in
this executor (only the CLI skill, which has no `detect-changes` verb), so the pre-commit check was
satisfied by that direct verification rather than by the tool. The index is stale at `9a0a45d` and
should be refreshed with `npx gitnexus analyze`; nothing this plan changed can move the call graph.

## Deviations from Plan

### 1. [Rule 1 — bug found by the work itself] §14's TOTAL row does not equal the sum of its own rows

- **Found during:** Task 1, recomputing the blind table.
- **Issue:** the plan asks for the table to be recomputed on one basis. Doing so revealed that the
  nine per-sheet rows sum to **44,011 / 41,912 (+5.0%)** while the published TOTAL reads
  **45,837 / 42,835 (7.0%)** — a 1,826 SF discrepancy on the measured side and 923 SF on the golden
  side, with no visible source. All nine per-sheet values reproduce exactly, so the rows are sound.
- **Fix:** both facts are stated in the correction — the recomputed total on its named basis, and
  that the published total was not computed over this table.
- **Committed in:** `5380bab`

### 2. [Rule 1 — my own transcription error, caught by the harness] Crow's HM count lives on the reclassified counter

- **Found during:** Task 3, first run of check 11 — it FAILED.
- **Issue:** I asserted `crow.panel_counts.get("HM") == 29`. Crow's `panel_counts` deliberately keeps
  the codes the drawing PRINTED (`IM` 29); the plan's own printed `HOLLOW METAL DOOR` note is applied
  by `reclassified_panel_counts`, so a caller can still see what the sheet said (23-04).
- **Fix:** the check now asserts **both** — the raw `IM` 29 and the reclassified `HM` 29 — because
  the distinction is the point, plus Crow's 105 openings (the count column that used to be mistaken
  for the tag column, reading a 105-door schedule as five).
- **Committed in:** `346d9b4`

### 3. [Rule 1 — a check that validated a measurement no run performs] Bob's facade must be measured through the full bundle

- **Found during:** Task 3, first run of check 8 — it FAILED at 319.4 ft against a 245–255 band.
- **Issue:** I called `_measure_elevation_areas(page, [], ...)` with an empty viewport list. The
  viewports are load-bearing: they host the band clip's x-bounds, which is what keeps Bob's
  keyed-notes column out of the silhouette. Without them the front blob reads 319.4 ft instead of
  249.2 — so the check would have been validating a measurement no run performs.
- **Fix:** the check goes through `_deterministic_bundle(..., "elevation")`, as a run does, and
  additionally asserts the negative that routing protects (zero walls, zero thickness classes).
- **Committed in:** `346d9b4`

### 4. [Rule 2 — missing critical functionality] Check 12 was split so the contract cannot report as "skipped"

- **Found during:** Task 3, first green run.
- **Issue:** check 12 asserted the provenance contract and then called `pytest.skip` when no saved
  run directories existed. The whole test then reported **skipped**, which reads as "nothing was
  verified" — while the contract had in fact been asserted. That is the blank-versus-zero ambiguity
  this phase exists to abolish, one layer up, inside the gate meant to prove it gone.
- **Fix:** split into check 12 (the contract — always asserts, on every machine) and check 12b (the
  saved-run replay — skips by name when there is nothing to replay).
- **Committed in:** `346d9b4`

### 5. [Decision] The deny list is assembled from string fragments

The plan's own acceptance command greps `tests/test_phase23_acceptance.py` for the five forbidden
literals. Spelling them out in the module's `FORBIDDEN` tuple would make the gate fail its own
no-paid-command check while nothing was actually wrong. The names are assembled from fragments, with
the reason in a comment; the string that is searched for is the assembled one, so the check is not
weakened. Both the module's own check 13 and the plan's one-liner now pass.

### 6. [Decision] Task 2's substance was already delivered, and is reported as such

23-09 and 23-11 rewrote both superseded tests in-plan (23-09 deviation 5 states why: a red suite
across seven plans camouflages every real regression that lands in between). This plan closed the
remaining gap — section-level citations, both directions in one test — rather than inventing work to
match the plan text. The plan's acceptance criteria are all met; the credit belongs to those plans.

### 7. [Decision] Two §5.3 criteria are asserted in their delivered form, with the undelivered part named

Check 4 (clip invariance) and check 2 (Bob's p3 page-level fpp) name **DEF-23-SP4** and **DEF-23-08**
respectively and assert what shipped instead. Silently dropping either would have reproduced, inside
the acceptance gate, exactly the failure the four corrected passages document.

### 8. [Scope boundary — logged, NOT fixed] The acceptance gate costs ~12 minutes on its own

The full suite moved from ~36 min to **45m56s**. Roughly half the gate's cost is deliberate
duplication: it re-runs the four-set audit and the 76-page false-positive sweep that
`test_four_set_coverage.py` and `test_open_runs.py` already run, because the phase's acceptance
requires them exercised **as one gate at the end**. Trimming that would be a runtime optimisation
bought with coverage. A session-scoped shared audit fixture is the obvious future fix and is noted
here rather than taken.

### 9. [Pre-existing, reverted] The suite still rewrites three synthetic fixture PDFs

`tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` came back modified after the
full run (23-08 dev 6 … 23-15 dev 7). Restored with `git checkout --`, never staged.

---

**Total deviations:** 3 auto-fixed (3× Rule 1), 1 missing-critical fix (Rule 2), 3 decisions
recorded, 2 logged and not fixed.
**Impact on plan:** no scope creep. Two of the three Rule 1 fixes were the harness catching my own
errors before they were committed — which is the argument for the harness.

## Issues Encountered

**Writing an acceptance gate is where transcription errors surface.** Two of this plan's three
auto-fixes were checks I had written from the SUMMARY prose and that FAILED on first run against the
real PDFs — Crow's HM count sitting on the reclassified counter, and Bob's facade measured without
the viewports a run supplies. Both would have been plausible-looking assertions in a transcript. That
is the difference the plan was written to capture: a transcript cannot fail.

**The recomputation was worth doing rather than reasoning about.** Reading §14's rows and its total
as consistent would have been the natural assumption; measuring them showed they are not. The nine
rows reproduce to the decimal on an engine eight plans younger than the table.

## Known Stubs

None. Every check either asserts or skips by name, and no check passes on missing data.

**Deliberately still open, each with a named owner:** **DEF-23-SP4** — the geometric viewport-bounded
clip cell, blocked behind the domain question *what should a dimension-string corridor contribute to
a room's measured area?*, which needs the take-off documents rather than the plans; **DEF-23-08** —
Bob's p3 page-level scale resolution; **DEF-23-11**, **DEF-23-13A**, **DEF-23-14A** and **DEF-23-07**,
all carried in `deferred-items.md`. Every one of them is named inside the gate or the corrected
record, so none is invisible.

## Threat Flags

None — no new network, auth, filesystem or schema surface, and no `src/` file changed. The plan's
five registered threats are all mitigated:

- **T-23-65** (a published figure not stating how it was produced) — the corrected §14 states the
  figure came from a direct engine call, that a run could not reach those sheets, and names the basis
  of the recomputed table.
- **T-23-66** (a superseded test deleted rather than corrected) — both tests are rewritten in place
  with citing docstrings; 104 test functions before and after.
- **T-23-67** (a gate passing because its fixtures are absent) — every check asserts or skips by
  name, and check 12 was split precisely so its contract half can never report as skipped.
- **T-23-68** (a paid command entering the gate) — check 13 greps the module for all four scripts and
  the credential, and asserts `pytest.ini` still deselects the paid marker by default.
- **T-23-69** (editing the honesty anchor beyond the agreed corrections) — 21 removed lines, every
  one inside the four passages; no section deleted; 15 `##` sections before and after.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `5380bab` | Correct the four disproved passages in the honesty anchor |
| 2 | `9dfe9c6` | The two superseded room-fill tests cite the probes that inverted them |
| 3 | `346d9b4` | Fold the probes in and lock ONE runnable acceptance gate |
| 4 | `a2a5eec` | Amend the two criteria and the requirement written on falsified premises |

## Requirement status

All six of `V4-MEAS-01 … V4-MEAS-06` are now claimable, and the last two blockers were **record**
blockers rather than code blockers:

- **V4-MEAS-01** — completed in 23-13 (ceiling and wall area both bind through one registry).
- **V4-MEAS-02** — the premise is corrected and the delivered contract stated; the guestroom-sized
  threshold is gone, the multiplier flag is sheet-exact, and SP-4 is carried openly as DEF-23-SP4.
- **V4-MEAS-03 / V4-MEAS-05** — completed in 23-15 (elevation SF in 23-14, civil-linework LF here).
- **V4-MEAS-04** — the premise is corrected and rewritten to the flagged-zero-row contract this phase
  actually delivered, which is what a verifier can now check.
- **V4-MEAS-06** — door parsing landed in 23-04 and the coverage flag reaches every client artifact
  as of 23-17.

## What this unblocks

**Phase 23 is closed.** `/gsd-verify-work` now reads criteria that describe what was built rather
than a falsified assumption, so it can fail the phase for a real reason instead of for doing the
honest thing. `tests/test_phase23_acceptance.py` is the regression floor Phase 24 inherits: a single
free command that re-asserts coverage, scale, area, the extent cross-check, perimeter, height, the
multiplier flag, elevations, linetype runs, rails, doors and the no-silent-zero contract across four
drafting offices.

**The standing caution, one last time.** This phase made the run **honest**, not accurate. It will
report more blanks and more flags than before; four Moxy unit counts are flagged and correcting them
moves Gyp Ceiling *away* from golden; Crow's rails surface as flagged blanks until Phase 24 names
their runs. A green gate measures accounting and discipline, not correctness — and it must never
become the target.

## Self-Check: PASSED

- `tests/test_phase23_acceptance.py` — FOUND
- `docs/PIPELINE-GROUND-TRUTH.md` / `scripts/geom_probe.py` / `scripts/fusion_probe.py` /
  `tests/test_room_fill.py` — FOUND
- `.planning/ROADMAP.md` / `.planning/REQUIREMENTS.md` — FOUND
- commits `5380bab` (Task 1), `9dfe9c6` (Task 2), `346d9b4` (Task 3), `a2a5eec` (Task 4) — FOUND
- `git diff --stat uploads/ human_inputs/ reports/` — EMPTY
- `git diff --stat 16a5741..HEAD -- src/` — EMPTY

---
*Phase: 23-measurement-engine-completion*
*Completed: 2026-08-04*
