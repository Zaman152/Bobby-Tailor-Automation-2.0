---
phase: 24-binding-determinism-text-anchored-labeling
plan: 09
subsystem: test harness (replay fixtures + end-to-end determinism differential)
tags: [determinism, replay-fixtures, differential, provenance, non-vacuity, V4-DET-05, offline]

# Dependency graph
requires:
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 01
    provides: "the per-candidate text anchor and the RECORDED-ABSENCE distinction that decides which candidates the symbol pass is even allowed to ask about"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 02
    provides: "the wall-class precedence inversion, and the committed precedent for a label-invariance differential that asserts its own residual"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 04
    provides: "the unnamed-geometry ledger — the third set this gate compares"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 06
    provides: "the `unnamed_geometry` report key, without which the ledger comparison would have nothing to read"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 07
    provides: "the FINAL prompts, schemas and render shapes every fixture key hashes — fixtures authored before 7cbdf40 would be dead on arrival"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 08
    provides: "the identification ensemble, whose same-key fan-out is the second vacuity trap this plan had to close"
provides:
  - "scripts/author_replay_fixtures.py — the committed, re-runnable fixture authoring procedure"
  - "tests/fixtures/replay/variant_a/ and variant_b/ — two label variants over one geometry, with per-fixture provenance"
  - "tests/test_determinism_harness.py — the end-to-end two-variant differential (14 gate tests + 4 failure demonstrations)"
  - "_published_item_sets / _compare_published — the ONE comparison the gate and its failure demonstrations share"
  - "a per-key fixture HIT CENSUS at the replay seam, so presence can never be mistaken for consumption"
  - "the residual assertion: a vision-named wall class still moves with its label (24-02's open item), pinned end to end"
affects: [24-10 phase gate, any future prompt or schema edit on the vector path]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A differential varies the ANSWER and holds the REQUEST fixed — an answer that becomes the next request's schema is fixed context, not a varied dimension"
    - "Presence is not consumption: a fixture-backed gate must keep a hit census and require every committed fixture to have been REQUESTED"
    - "A gate whose subject swallows exceptions must record the miss at the SEAM, because the swallow turns a drift into a quieter run and a green comparison"
    - "Author fixtures with a committed script, never by hand: every key dies on the next prompt edit, and a set nobody can regenerate is a trap for the next phase"
    - "State the invariance boundary as an ASSERTION, not a note — the residual test is what keeps the invariance claim honest"
    - "A self-grep audit must assemble its own forbidden tokens from halves, or the module fails its own check"

key-files:
  created:
    - scripts/author_replay_fixtures.py
    - tests/fixtures/replay/variant_a/ (3 fixtures)
    - tests/fixtures/replay/variant_b/ (3 fixtures)
    - tests/test_determinism_harness.py
    - .planning/phases/24-binding-determinism-text-anchored-labeling/24-09-SUMMARY.md
  modified:
    - .planning/ROADMAP.md
    - .planning/STATE.md

key-decisions:
  - "The requirement's literal wording was NOT implemented. `ReplayAnalyzer.__call__` is a pure function of a SHA256 over (model, pass_type, prompt, image_count), so N runs of one fixture are identical by construction and would detect nothing. The gate holds geometry fixed and VARIES the model's answers instead."
  - "The project naming-convention answer is FIXED across both variants, deliberately. It becomes the NEXT request's label enum, so varying it varies the REQUEST — a different experiment, and one that would put the two variants on disjoint fixture keys and break the same-key-set contract outright. Defect F3 is therefore explicitly out of scope; 24-05's persistence owns it."
  - "ENSEMBLE PASSES ARE OUT OF SCOPE, and the scope claim is a test rather than a comment. After 24-08 a pass fans out to N requests carrying ONE key, so a key-addressed replay source votes unanimously by construction. The harness pins the ensemble to one sample — 24-08's own byte-identical single-shot path — and a test asserts each per-sheet pass was hit exactly once, so the pin cannot silently stop working."
  - "The plan's `(name, unit, quantity, measure_basis)` tuple set is NOT the gate's assertion. `measure_basis` does not exist anywhere in this codebase, and the `(name, unit, quantity)` set is MEASURABLY not invariant. The gate asserts the three invariants that hold and a separate test asserts the residual that does not — phase-23 rule 1, applied to this plan's own plan."
  - "The symbol pass answers `unknown` for every marked cluster in BOTH variants, because that is what both saved runs observably answered. It is deliberately NOT varied by inventing two enum labels for one marked cluster: the pipeline makes no claim that a text-anchored cluster the model names differently publishes the same, so varying it would manufacture a failure the codebase never promised to prevent."
  - "The gate compares against ITSELF, never against a golden figure. If both variants are wrong in the same way it correctly passes — it measures invariance, not correctness."
  - "The scope is Crow's vector sheet A-101, not the whole plan set. The other three sheets reach the LEGACY vision path, where identification and quantity arrive in one object with no seam; varying those answers would vary QUANTITIES, which is exactly why 24-08 excluded count/measure/extraction from voting."

requirements-completed: []
# HONEST SCOPE NOTE: this plan carries `requirements: [V4-DET-05]` and does NOT tick it,
# consistent with 24-01…24-08. The harness exists, runs free, is demonstrated to fail on a
# naming flip, and asserts three real invariants end to end. What it does NOT have is a
# demonstration that the determinism held on a PAID run — that needs a paid run, which is
# forbidden autonomously. The phase gate (24-10) owns the tick.

coverage:
  - id: F1
    description: "Two schema-legal label variants over one fixed geometry publish the same take-off"
    requirement: V4-DET-05
    verification:
      - kind: integration
        ref: "tests/test_determinism_harness.py#test_two_schema_legal_answer_sets_publish_the_same_takeoff"
        status: pass
      - kind: integration
        ref: "tests/test_determinism_harness.py#test_the_unnamed_geometry_ledger_carries_the_same_candidates, #test_no_published_quantity_moves_when_only_the_labels_move"
        status: pass
    human_judgment: false
  - id: F2
    description: "The fixtures were actually CONSUMED — the gate cannot pass for having looked at nothing (24-07's trap)"
    requirement: V4-DET-05
    verification:
      - kind: unit
        ref: "tests/test_determinism_harness.py#test_every_committed_fixture_was_actually_consumed"
        status: pass
      - kind: other
        ref: "per-key hit census at the replay seam; 3 fixtures on disk per variant, 3 requested per variant, set equality asserted"
        status: pass
    human_judgment: false
  - id: F3
    description: "The ensemble's same-key fan-out cannot make the vote unanimous by construction (24-08's trap)"
    requirement: V4-DET-05
    verification:
      - kind: unit
        ref: "tests/test_determinism_harness.py#test_the_ensemble_is_pinned_to_one_sample_so_the_scope_is_honest"
        status: pass
      - kind: other
        ref: "measured: with the pin absent each per-sheet pass was hit 3x; with it in effect, exactly 1x"
        status: pass
    human_judgment: false
  - id: F4
    description: "A missing fixture SKIPS with a named reason and can never report a false green"
    requirement: V4-DET-05
    verification:
      - kind: unit
        ref: "tests/test_determinism_harness.py#test_missing_fixture_skips_and_never_passes, #test_an_absent_plan_set_skips_rather_than_passing"
        status: pass
    human_judgment: false
  - id: F5
    description: "The gate is a proven DETECTOR — it has been seen to fail on a deliberate naming flip"
    requirement: V4-DET-05
    verification:
      - kind: unit
        ref: "tests/test_determinism_harness.py#test_the_gate_detects_a_naming_flip, #test_the_gate_detects_a_candidate_named_in_one_variant_and_ledgered_in_the_other, #test_the_gate_detects_a_quantity_that_moved, #test_two_identical_reports_report_no_difference"
        status: pass
      - kind: other
        ref: "a THIRD variant poisoned on disk during execution; the gate went RED on all three invariants; pristine fixtures restored and the poison never committed"
        status: pass
    human_judgment: false
  - id: F6
    description: "The 56-EA candidate the two paid runs disagreed about is ledgered in both variants and named in neither"
    requirement: V4-DET-05
    verification:
      - kind: integration
        ref: "tests/test_determinism_harness.py#test_the_candidate_that_flipped_between_the_paid_runs_is_named_in_neither"
        status: pass
    human_judgment: false
  - id: F7
    description: "Every fixture records which saved run it came from, or states its gap in words"
    requirement: V4-DET-05
    verification:
      - kind: unit
        ref: "tests/test_determinism_harness.py#test_every_fixture_records_which_saved_run_it_came_from"
        status: pass
    human_judgment: false
  - id: F8
    description: "The whole gate runs free — no paid marker, no paid script name, no credential"
    requirement: V4-DET-05
    verification:
      - kind: unit
        ref: "tests/test_determinism_harness.py#test_the_whole_module_runs_free, #test_record_mode_is_off_on_every_analyzer_this_module_builds, #test_this_module_asserts_no_golden_total"
        status: pass
    human_judgment: false
  - id: F9
    description: "Whether the determinism this gate proves offline actually held on a real paid run"
    requirement: V4-DET-05
    verification: []
    human_judgment: true
    rationale: "Unmeasurable offline BY THE PLAN'S OWN SUCCESS CRITERIA. Judging it needs a paid run, which is forbidden autonomously. This plan is judged on whether the differential detects the defect class — proved by making it fail — never on an accuracy percentage."

# Metrics
duration: ~4h 15m (three full 52–56 minute suites and two 14½-minute gate runs dominate it)
completed: 2026-08-06
status: complete
---

# Phase 24 Plan 09: The Determinism Harness Summary

**The phase's central gate exists, runs free in under three minutes, holds one geometry fixed while the model's answers move, asserts three invariants against itself rather than against any golden figure — and has been made to fail, on disk, on a deliberate naming flip.**

## The requirement's literal words were not implemented, and that was the point

V4-DET-05 reads *"same fixture N times asserts identical line items"*. `ReplayAnalyzer.__call__`
resolves a SHA256 over `(model, pass_type, prompt text, image count)` and returns that file's
response verbatim. It is a **pure function of the key**. Running one fixture N times is identical
*by construction*, would detect none of defects F1–F9, and would have shipped a gate that passes for
having looked at nothing — the exact failure `test_phase23_acceptance.py` rule 3 forbids.

What shipped instead: **hold the geometry fixed, VARY the model's answers within schema-legal
bounds, assert the published take-off does not move.**

## The two vacuity traps, and the evidence each is closed

Both were discovered by earlier plans in this phase and handed forward. Neither is hypothetical.

### Trap 1 (from 24-07) — a fixture nothing ever requests

Every key hashes the prompt text, the schema-driven model routing **and** the image count. 24-07
moved all three. A set authored before `7cbdf40` hashes to keys nothing asks for; the harness would
then observe zero replayed calls and pass for having looked at nothing.

**Closed two ways, and neither is a promise:**

1. **The fixtures were authored against the current tree, by a script that computes the key from the
   pipeline itself.** `scripts/author_replay_fixtures.py` drives the real deterministic half over the
   real Crow PDF with a *responder* analyzer and resolves each key through `ReplayAnalyzer.key_for`
   — the public derivation — rather than a second copy of the hash. The key it records is by
   construction the key replay will ask for.
2. **The gate asserts CONSUMPTION, not presence.** `_ReplayProbe` keeps a per-key hit census, and
   `test_every_committed_fixture_was_actually_consumed` asserts set equality between the fixtures on
   disk and the fixtures actually requested.

| Variant | fixtures on disk | fixtures REQUESTED | assertion |
|---|---|---|---|
| `variant_a` | 3 | 3 | set equality, both directions |
| `variant_b` | 3 | 3 | set equality, both directions |

There is a third guard the plan did not ask for and the tree demanded. **The vector path wraps each
semantic/symbol pass in `except Exception` so a failed pass leaves labels additive.** That is right
for production and lethal for a gate: a `KeyError` from a drifted key would be swallowed, the run
would simply produce fewer names, and both variants would produce fewer names *identically* — a
green comparison over a degraded run. So the miss is recorded **at the seam** and
`_require_no_fixture_drift` converts it into a named skip. `ReplayAnalyzer`'s `KeyError` is
untouched; a prompt drift stays loud.

### Trap 2 (from 24-08) — a vote that is unanimous by construction

After 24-08 an ensembled pass issues N requests carrying the **same** replay key, so a key-addressed
analyzer hands every sample the same fixture and the vote proves nothing about voting.

**Explicitly scoped OUT, and the scope is a test, not a sentence.** The harness pins the ensemble to
**one sample** — 24-08's own byte-identical single-shot path (`E2`) — and
`test_the_ensemble_is_pinned_to_one_sample_so_the_scope_is_honest` asserts every per-sheet pass was
hit **exactly once**. This was not assumed: the first working harness pinned `ENSEMBLE_N` through
the *environment* and the census showed **3 hits per pass**, because `config.ENSEMBLE_N` is resolved
from the environment at IMPORT time. The pin now sets `config.ENSEMBLE_N` directly, and the census
reads 1. If it ever stops working the test fails rather than the claim quietly rotting.

**So: are ensembled passes in or out of the differential's scope? OUT, unambiguously.** Voting
behaviour is covered by `tests/test_reliability_voting.py`, whose scripted stubs genuinely differ
per sample. This gate covers what a replay source can honestly cover.

## What varies, and what does not — stated rather than implied

| | Fixed across both variants | Varied between the variants |
|---|---|---|
| PDF, page, deterministic geometry | ✔ | |
| every prompt, every schema, every image count | ✔ | |
| the project naming-convention answer | ✔ | |
| the symbol pass's per-cluster labels | ✔ (`unknown` in both — the observed answer) | |
| the semantic pass's wall-class labels | | ✔ |

**Why the naming-convention answer is FIXED and not varied.** It becomes the *next* request's label
enum (`run_project` → `_project_vocab_labels` → `legend_labels` → `symbol_gallery_schema`). Varying
it would change the symbol pass's prompt, hence its SHA256, hence which fixture is even addressed —
two experiments at once, and two **disjoint** key sets, which would break the plan's own
same-key-set acceptance criterion outright. The naming-library variance the two runs really do
exhibit (defect F3) is therefore **out of this gate's scope**; 24-05's per-project persistence owns
it.

**Why the symbol pass is identical in both variants.** Because that is what both runs observably
answered. Every symbol row in both artifacts is a raw `SYM-` identifier except the single cluster
the naming *library* named. It is deliberately not varied by inventing two enum labels for one
marked cluster: the pipeline makes no claim that a text-anchored cluster the model names differently
publishes the same — the model's word is what names it, which is precisely why the phase's answer is
to only ASK about candidates the drawing itself names. Manufacturing that failure would be testing a
promise the codebase never made.

## Assumption A2, resolved in writing — including its gap

The research rated the recoverability of the two runs' per-pass responses **MEDIUM**. The honest
outcome:

| Pass | Recoverable? | Route |
|---|---|---|
| **semantic** (wall classes, regions, rooms) | **YES** | The object names come from `takeoff_summary[].item` where `source` is `library` / `learned` / `expected_not_measured` — that set IS the run's naming library. Which classes and rooms the run could NOT name is read straight off `raw_line_items[].description` beginning `WALL-` / `ROOM-`. |
| **symbol_gallery** (matches) | **YES** | Every symbol row in both artifacts is a raw `SYM-` identifier except one, so the pass bound nothing in either run — `unknown` is the *observed* answer, not a placeholder. |
| **naming_conventions** (the object library) | **NO — DOCUMENTED GAP** | Neither saved run records this pass's response, nor the `basis` / `binding_hint` / `aliases` / `thickness_in` / `height_ft` its schema requires. |

**The gap was recorded, not filled.** The naming-convention fixture is the schema-legal **empty
object list** in both variants — a real answer the pipeline already handles, which leaves
`run_project` on the deterministic component library harvested from the plan's own printed text —
and its `provenance.gap` says so in words. `test_every_fixture_records_which_saved_run_it_came_from`
requires every fixture to name either its source run or its gap; silence is not an option.

## What the gate asserts, and what it refuses to assert

Three invariants, every one **set equality between variant A and variant B**, never against a golden
figure:

| # | Assertion | Result |
|---|---|---|
| 1 | the published item-name set (`takeoff_summary[].item`) | **equal** |
| 2 | the unnamed-geometry ledger's candidate-ID set | **equal** — 40 candidates each |
| 3 | the published quantity multiset | **equal** |

Plus the phase's central defect, asserted end to end:

**`SYM-2` — the 56-EA cluster that published as `Bollard` (source: learned) in the 14:19 run and as
`Dock Bumper` (source: library) in the 18:13 run — carries a recorded text absence, is excluded from
the symbol request entirely (24-07), lands in the ledger in BOTH variants, and neither of the two
names the paid runs gave it reaches either published take-off.** The quantity is read off the record
the producer wrote and never restated as a literal, and the candidate is named by ID so no count
appears in the test.

### The residual, asserted by name rather than quietly excluded

The plan specified a `(name, unit, quantity, measure_basis)` tuple set. Two corrections, both
measurement-driven:

1. **There is no `measure_basis` field anywhere in this codebase** (`grep -rn "measure_basis" src`
   returns nothing). The nearest recorded fact is the row's `provenance`.
2. **The `(name, unit, quantity)` tuple set is measurably NOT invariant.** Swapping the two observed
   wall-class labels between the variants swaps which class publishes under which name:

   | | variant A | variant B |
   |---|---|---|
   | | `('CMU Wall', 'LF', 33.9)` | `('CMU Wall', 'LF', 1714.0)` |
   | | `('Tilt Up Wall', 'LF', 1714.0)` | `('Tilt Up Wall', 'LF', 33.9)` |

   That is **24-02's own documented, still-open residual**: a printed-thickness match outranks a
   vision label, but a wall class with no thickness match is still named by vision.
   `test_the_residual_a_vision_named_wall_class_still_moves_with_its_label` pins it, and pins that
   nothing else drifts with it — the moved rows' NAME set is equal, their QUANTITY set is equal, and
   every moved name is one of the two labels the fixtures swapped, read off the fixtures rather than
   typed into the test. **When 24-02's residual is closed this test will fail, and that failure is
   the signal the fix worked.** It says so in its own docstring.

Asserting the residual is what keeps the invariance claim honest instead of quietly scoped to
whatever happened to pass — 24-02's precedent, applied to its own successor.

## The gate was made to FAIL — on disk, not only in memory

A gate nobody has seen fail is a gate nobody knows works.

**On disk (the hard evidence).** A third variant was poisoned during execution: `variant_b`'s
semantic fixture answered one wall class with a **third** schema-legal name
(`Concrete Retaining Wall`, read from run B's own published object list) that variant A never uses.
The gate went **RED on all three invariants**:

```
FAILED test_two_schema_legal_answer_sets_publish_the_same_takeoff
    published item names moved: only-A=['CMU Wall'] only-B=['Wall Framing']
FAILED test_no_published_quantity_moves_when_only_the_labels_move
FAILED test_the_residual_a_vision_named_wall_class_still_moves_with_its_label
3 failed, 15 passed in 177.31s
```

The pristine fixture was then restored. **The poison is not in the tree:**
`git status --porcelain tests/fixtures/replay/` returns `0`, and
`grep -rl "POISONED" tests/fixtures/replay/` finds nothing.

**In the suite (the permanent evidence).** Four demonstrations, all routed through
`_compare_published` — the same helper the gate calls in anger, never a parallel reimplementation
that could drift:

| Demonstration | What it poisons | Where |
|---|---|---|
| `test_the_gate_detects_a_naming_flip` | one published item renamed | in memory, from variant A's REAL report |
| `test_the_gate_detects_a_candidate_named_in_one_variant_and_ledgered_in_the_other` | a ledgered candidate published instead | in memory, from the real report |
| `test_the_gate_detects_a_quantity_that_moved` | a number that moved | hand-built pair |
| `test_two_identical_reports_report_no_difference` | **nothing — the positive control** | hand-built pair |

The positive control matters as much as the three failures: without it the helper could be reporting
a difference unconditionally, and every demonstration above would pass for nothing.

## Task Commits

1. **Task 1: Author variant A and variant B fixtures offline, with recorded provenance** — `e31d254` (test)
2. **Task 2: The two-variant differential gate** — `1a1d8f6` (test)
3. **Task 3: Prove the gate can fail** — `7993ad1` (test)

**Plan metadata:** see the `docs(24-09)` commit accompanying this file.

## Files Created

- **`scripts/author_replay_fixtures.py`** (~480 lines) — the committed authoring procedure. Drives
  `run_project` over Crow's vector sheet with a responder analyzer, reads both runs' object names
  from their `takeoff.json` **read-only** at authoring time, computes every key through
  `ReplayAnalyzer.key_for`, and writes fixture + provenance. `--check` reports drift without writing.
  **Every key dies on the next prompt edit; this is how they come back in one command.**
- **`tests/fixtures/replay/variant_a/`, `variant_b/`** — 3 fixtures each, the SAME three keys:
  `semantic` (the varied one), `symbol_gallery`, `naming_conventions`.
- **`tests/test_determinism_harness.py`** (~690 lines, 18 tests) — the gate, its non-vacuity
  guards, the residual, the skips and the failure demonstrations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug in the plan's own assertion] `measure_basis` does not exist, and the calculated tuple set is not invariant**
- **Found during:** Task 2, first end-to-end measurement.
- **Issue:** the plan specifies asserting the SET of `(name, unit, quantity, measure_basis)` tuples.
  `grep -rn "measure_basis" src` returns nothing — the field is not in this codebase — and the
  `(name, unit, quantity)` set is measurably NOT equal across the variants, because a wall class
  with no printed-thickness match is still named by vision (24-02's open residual).
- **Fix:** the gate asserts the three invariants that DO hold (summary item names, ledger candidate
  set, quantity multiset) and a separate test asserts the residual that does not, by name, with the
  drift confined to the swapped labels. Phase-23 rule 1: lock what SHIPPED, and never quietly drop
  a check.
- **Files:** `tests/test_determinism_harness.py` — **Committed in:** `1a1d8f6`

**2. [Rule 2 — Missing critical] A drifted fixture would have been SWALLOWED, not raised**
- **Found during:** Task 2, reading `_run_sheet_vector` against the plan's "keep the `KeyError`,
  wrap at the TEST level" instruction.
- **Issue:** the vector path wraps each semantic/symbol pass in `except Exception` so labels stay
  additive. A `KeyError` from a drifted key never reaches the test — the run just produces fewer
  names, *identically in both variants*, and the comparison passes over a degraded run. Catching the
  `KeyError` at the test level, as written, would catch nothing.
- **Fix:** `_ReplayProbe` records the miss at the seam before re-raising, and
  `_require_no_fixture_drift` turns any miss into a named skip at fixture-setup time.
- **Files:** `tests/test_determinism_harness.py` — **Committed in:** `1a1d8f6`

**3. [Rule 1 — Bug, self-inflicted] The environment pin on `ENSEMBLE_N` was a no-op**
- **Found during:** Task 1, reading the hit census — 9 naming / 3 semantic / 3 symbol hits where 1
  each was expected.
- **Issue:** `config.ENSEMBLE_N` is resolved from the environment at IMPORT time, so setting the env
  var after config is imported changes nothing. Every pass was silently running the 24-08 ensemble
  and reading one fixture three times — **exactly the trap 24-08 warned about**, reproduced live.
- **Fix:** the harness sets `config.ENSEMBLE_N` directly (restored in a `finally`), and
  `test_the_ensemble_is_pinned_to_one_sample_so_the_scope_is_honest` asserts the census reads 1 so
  the pin cannot silently stop working again.
- **Files:** `scripts/author_replay_fixtures.py`, `tests/test_determinism_harness.py` —
  **Committed in:** `e31d254`, `1a1d8f6`

**4. [Rule 1 — Bug, self-inflicted] The free-module self-grep failed on its own source**
- **Found during:** Task 2, first module run.
- **Issue:** `test_the_whole_module_runs_free` scans this very file for six paid-gate markers, and
  spelling them out in the check's own tuple made the module fail its own audit — the same
  self-defeating shape 24-08 hit with its temperature grep.
- **Fix:** the tokens are assembled from halves, with the reason in the file. The plan's acceptance
  grep over the module now returns `0`.
- **Files:** `tests/test_determinism_harness.py` — **Committed in:** `1a1d8f6`

**5. [Rule 3 — Blocking] The plan's `<files>` named `.gitkeep` placeholders**
- **Found during:** Task 1.
- **Issue:** the plan lists `tests/fixtures/replay/variant_a/.gitkeep` as the artifact. A `.gitkeep`
  in a directory that holds real fixtures is dead weight and would make the directory look
  intentionally empty.
- **Fix:** the real fixture files are committed instead; the acceptance criteria (non-zero JSON
  count, identical key sets, differing contents, provenance on every file) are all satisfied by
  them.
- **Committed in:** `e31d254`

### Scope decision, recorded rather than assumed

**The differential runs over Crow's vector sheet A-101 only, not the whole four-sheet set.** A-101 is
the phase's entire subject: the only vector sheet, all 36 symbol clusters, all 13 wall classes, every
room candidate, and the sheet whose 56-EA candidate flipped between the runs. The other three sheets
reach the **legacy** vision path, where a pass returns identification and quantity inside one object
with no seam — varying those answers would vary QUANTITIES, which this phase's contract forbids and
which 24-08 excluded from voting for exactly the same reason. The harness threads the deterministic
legend schedules exactly as `pdf_analyzer.run_pdf_analysis` does, so the prompts it hashes are the
prompts a production run hashes.

---

**Total deviations:** 5 (2 self-inflicted bugs, 1 bug in the plan's own assertion, 1 missing-critical,
1 blocking). No scope creep, no new packages, no source file outside `tests/` and `scripts/` touched.

## Measurements taken this plan (all FREE, zero API)

| Measurement | Result |
|---|---|
| fixtures per variant | **3** (`semantic`, `symbol_gallery`, `naming_conventions`) — identical key sets |
| fixtures differing between variants | **1** (`semantic`) — asserted non-empty by `test_the_two_variants_really_do_carry_different_answers` |
| fixture hits per per-sheet pass, ensemble pin ABSENT | **3** (the 24-08 trap, reproduced) |
| fixture hits per per-sheet pass, pin IN EFFECT | **1** |
| unnamed-geometry ledger, both variants | **40 candidates**, set-equal |
| `SYM-2` in the ledger / `Bollard` or `Dock Bumper` published | **yes / no**, both variants |
| calculated rows differing between variants | **2** — the wall-class pairing only, names and quantities each set-equal |
| gate runtime | **2 min 56 s** for the whole module, two full pipeline runs included |
| gate under a poisoned third variant | **3 failed, 15 passed** — RED on all three invariants |

## Threat Model Outcomes

| Threat ID | Disposition | Outcome |
|---|---|---|
| T-24-39 | mitigate | **Met.** Record mode never enabled; fixtures authored offline by a committed script and reviewed as code; every file carries provenance. `test_record_mode_is_off_on_every_analyzer_this_module_builds` asserts the analyzers this module builds are in replay mode and that the authoring script contains no forced-record construction. |
| T-24-40 | mitigate | **Met.** Every fixture names the run it was reconstructed from and the fields it was derived from, or states its gap in words — asserted, not conventional. The one unreconstructable pass is a recorded gap, not an invention. |
| T-24-41 | mitigate | **Met, twice over.** A missing fixture SKIPS (and the swallow that would have hidden it is closed at the seam); a fixture nobody requested FAILS the consumption census; and the gate was made to go red on a poisoned variant on disk. |
| T-24-42 | mitigate | **Met, unchanged.** Keys are SHA256 hex with no path separators and the fixture directories are fixed test-local paths. |
| T-24-43 | mitigate | **Met.** The key is derived through the public `ReplayAnalyzer.key_for` in both the authoring script and the test seam. No second hash implementation exists to drift. |
| T-24-44 | mitigate | **Met.** No credential is read and record mode is never enabled. The acceptance grep over the fixture tree for the record-mode variable and the credential name returns `0`, and the module's own free-grep returns `0`. |
| T-24-SC | mitigate | **Met.** No new packages. |

## Test Results

| Gate | Result |
|---|---|
| Baseline (plan entry, post-24-08) | 2150 passed, 1 skipped, 2 deselected |
| Full suite before `e31d254` (fixtures + script only) | **2150 passed**, 1 skipped, 2 deselected (52:49) |
| Full suite before `1a1d8f6` (+ the 14 gate tests) | **2164 passed**, 1 skipped, 2 deselected (55:50) |
| Full suite before `7993ad1` (+ the 4 demonstrations) | **2168 passed**, 1 skipped, 2 deselected (55:55) |
| `test_four_set_coverage.py` + `test_phase23_acceptance.py`, standalone | **28 passed, 1 skipped** ×2 (14:32, 14:35) |
| `tests/test_determinism_harness.py` standalone | 18 passed in 2:56 |

Net: **+18 tests, 0 regressions.** 2150 + 14 + 4 = 2168, and the arithmetic held at every commit.
The 1 skip is the pre-existing one; the 2 deselected are the paid golden tests, never run.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | No `-m golden` run; no paid gate script invoked; the API-key env var never referenced; `.env` never read; the record-mode env var never set. The module's own free-grep returns **0**. |
| Record mode never enabled | Asserted by test and by grep over both the fixture tree and the authoring script. |
| Offline gate green | 2150 → 2168, up by exactly the 18 tests added. |
| Four-set + phase-23 acceptance green | 28 passed, 1 skipped, run standalone as well as inside every full-suite run. |
| Gate demonstrated FAILING | 3 failed / 15 passed under a poisoned third variant, output quoted above; poison restored and never committed. |
| No poison committed | `git status --porcelain tests/fixtures/replay/` → **0**; `grep -rl POISONED tests/fixtures/replay/` → nothing. |
| Paid-run evidence untouched | `git status --porcelain .planning/paid-run-evidence/ \| wc -l` → **0**, checked before every commit. Both `takeoff.json` files opened read-only. |
| Coincidence trap fenced | `grep -Ec '== *28\b\|== *132\b\|== *136\b\|== *56\b'` over the new module → **0**, and a test in the module asserts it of itself. The 56-EA candidate is referenced by ID; its quantity is read off the record the producer wrote. |
| No whole-blob comparison | `grep -Ec "assert +report_a *== *report_b\|assert +json.dumps"` → **0**. Four named sets, nothing broader. |
| `uploads/`, `human_inputs/`, `reports/`, `.env` untouched | Not in any commit. |
| `AGENTS.md` / `CLAUDE.md` / synthetic PDFs never staged | `git diff --cached --name-only` checked before each of the three commits; the pre-existing edits and the suite-regenerated fixtures were left unstaged every time. |
| Python 3.9 | `python3 --version` → 3.9.6; `typing` generics throughout, no 3.10+ syntax. |
| No `--no-verify` | All three commits ran normally on the main working tree. |
| GitNexus | No existing symbol was edited — all three commits add new files — so no `impact` was required. `detect-changes` was run before each commit: **0 affected processes, risk LOW** each time (the only changed symbols it sees are the pre-existing `AGENTS.md`/`CLAUDE.md` edits). |

## Issues Encountered

- **The 24-08 trap reproduced itself on my first run.** The ensemble pin through the environment was
  a no-op, and the census read 3 hits per pass on one fixture — a vote that would have been unanimous
  by construction. It was caught only because the census existed. **The census is the reason the
  scope claim is true rather than merely written down.**
- **The plan's central assertion did not survive contact with the tree.** `measure_basis` does not
  exist, and the calculated tuple set genuinely moves. Writing the plan's words would have produced
  a red gate or, worse, a gate quietly narrowed until it passed. The measurement won, and the
  residual is now a runnable assertion with an explicit instruction not to "repair" it by deletion.
- **A swallowed exception nearly made the skip contract a lie.** The plan says to keep
  `ReplayAnalyzer`'s `KeyError` and wrap at the test level. The `KeyError` never gets there — the
  vector path swallows it. Recording the miss at the seam is what makes "a missing fixture SKIPS"
  actually true rather than nominally true.
- **The full suite exceeds the 10-minute per-call tool cap** (52:49, 55:50, 55:55, plus two 14½-minute
  gate runs — roughly 3 h 15 m of the plan's ~4 h 15 m). Run in the foreground and blocked on inline.
- **`tests/fixtures/synthetic/*.pdf` are still regenerated in-tree by every suite run**, so a suite
  leaves a dirty tree. Pre-existing, never staged; already logged in `deferred-items.md`, owner 24-10.

## Next Phase Readiness

**Blocks nothing. Hands 24-10 four things.**

1. **V4-DET-05 is NOT ticked here**, consistent with 24-01…24-08. The gate owns it. Three free
   structural assertions are now available to it: that `tests/test_determinism_harness.py` exists and
   contains no paid marker; that the two variant directories hold identical key sets with differing
   contents and provenance on every file; and that the differential passes (or skips loudly).
2. **The residual is a live, named open item.** `test_the_residual_a_vision_named_wall_class_still_
   moves_with_its_label` is the runnable form of 24-02's unclosed residual. Whoever closes it should
   expect that test to fail and must update it deliberately.
3. **The fixtures are perishable and the antidote is committed.** Any future prompt, schema or render
   change on the vector path invalidates all six. `python3 scripts/author_replay_fixtures.py`
   regenerates them; `--check` reports drift without writing. The gate will SKIP, not silently pass,
   in the meantime.
4. **Two scoped-out dimensions, both stated.** Ensembled voting (a same-key fan-out cannot be varied
   by a key-addressed replay source) and the naming-library variance F3 (varying it varies the
   request). Neither is a gap in this gate; both are covered elsewhere or owned elsewhere, and 24-10
   should not read this gate as making a claim about either.

**Honest expectations to carry into verification:**

- **No accuracy claim is made or measurable here.** Nothing was scored and nothing may be. Judge this
  plan on whether the differential DETECTS the defect class — proved by making it fail — never on an
  accuracy percentage, and never by running a paid validation.
- **If both variants are wrong in the same way, this gate correctly passes.** It measures invariance,
  not correctness. Conflating the two is what this phase exists to separate.

## Self-Check: PASSED

- `scripts/author_replay_fixtures.py` FOUND · `tests/test_determinism_harness.py` FOUND ·
  `tests/fixtures/replay/variant_a/` FOUND (3 fixtures) · `tests/fixtures/replay/variant_b/` FOUND
  (3 fixtures) · this SUMMARY FOUND
- `e31d254` FOUND · `1a1d8f6` FOUND · `7993ad1` FOUND
- `.planning/paid-run-evidence/` unmodified (0 porcelain entries) ·
  `tests/fixtures/replay/` clean (0 porcelain entries, no poison)

---
*Phase: 24-binding-determinism-text-anchored-labeling*
*Completed: 2026-08-06*
