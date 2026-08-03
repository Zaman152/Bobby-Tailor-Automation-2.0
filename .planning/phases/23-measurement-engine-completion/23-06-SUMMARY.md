---
phase: 23-measurement-engine-completion
plan: 06
subsystem: pipeline/classification
tags: [title-block, classifier, signal-to-noise, four-set-gate, D-04, D-05, V4-MEAS-06]
status: complete
requires:
  - 23-01 (classify_sheet_type_verbose, coverage_probe, the four-set gate)
provides:
  - pipeline.text_shape (looks_like_title_block, is_title_shaped_match, word_runs, prose_runs)
  - pdf_analyzer._TITLE_BLOCK_WINDOWS + _window_text — the structural window search
  - sheet_pass_matrix._find_title_position_hit — the keyword-context guard
  - coverage_probe --no-veto + pages_classifier_discarded
  - the classification-alone four-plan-set gate
affects:
  - pdf_analyzer.get_title_block_text (window selection; extraction unchanged on 3 of 4 sets)
  - pdf_analyzer._sheet_name_from_doc (second consumer — output byte-identical, 83/83 pages)
  - sheet_pass_matrix.classify_sheet_type_verbose / classify_sheet_type_from_text
  - takeoff_pipeline.run_sheet (fewer sheets reach the skip sentinel)
tech-stack:
  added: []
  patterns:
    - "identify a region by what it CONTAINS, never by a fixed fraction of the page"
    - "two independent weak signals beat one strong one when neither alone separates the populations"
    - "a context predicate on the match, never a deny list of the phrases that collided"
    - "grade a fix with its backstop REMOVED, or you are grading the backstop"
    - "when a fix lands, invert the test that pinned the defect — never delete it"
key-files:
  created:
    - src/bobbytailor/pipeline/text_shape.py
  modified:
    - src/bobbytailor/pipeline/pdf_analyzer.py
    - src/bobbytailor/pipeline/sheet_pass_matrix.py
    - scripts/coverage_probe.py
    - tests/test_sheet_pass_matrix.py
    - tests/test_sheet_name.py
    - tests/test_takeoff_pipeline.py
    - tests/test_four_set_coverage.py
decisions:
  - "The two root causes are each INDEPENDENTLY SUFFICIENT: measured separately, each alone takes Moxy from 18 to 2 classifier-discarded pages. Both shipped anyway, per 23-CONTEXT — fixing whichever one moves the number would leave the other live for the next drafting office."
  - "text_shape.py is a new module rather than code in either consumer: sheet_pass_matrix cannot import pdf_analyzer (cycle), and the tokenizer plus function-word set are genuinely shared."
  - "Single-letter tokens are excluded from the function-word set. A lone 'A' on a drawing is a designator (PHASE A, KING TYPE A), not the English article — counting it made four genuine Moxy title blocks read as prose."
  - "PRE_CHANGE_SHEET_IDS pins the RECORDED output of _sheet_name_from_doc, several values of which are plainly poor ('Page_3', 'A117.1'). Pinning the honest current output is what makes the invariance claim mean anything; repairing sheet naming is not this plan's job."
  - "Chelsea's floor-plan/roof-plan floors are re-measured (22/4), not INV-00 §1d's (9/5). §1d was taken on an older HEAD; a regression test can only honestly compare against the HEAD the change landed on."
metrics:
  duration: ~2h
  completed: 2026-08-03
  tasks: 3
  commits: 3
  suite: "1511 passed, 2 deselected (baseline after 23-05: 1465)"
---

# Phase 23 Plan 06: Structural Title-Block Identification + Keyword-Context Guard Summary

The classifier no longer discards a drawing sheet because a keynote column outvoted its title block:
Moxy goes from 18 classifier-discarded pages to 2 — the genuine cover and index — with Crow, Bob's
and Chelsea byte-identical, no page fraction changed and no keyword touched.

## The defect, and why it was not a keyword defect

INV-00 §1c: on Moxy page 27 the sheet identifier `ID-411` and the unit name `KING SUITE` are present
in **both** the correct and the incorrect title-block window. The classifier was never failing to see
the title — it was being outvoted by 84 words of adjacent electrical keynote prose. That is a
signal-to-noise defect, which is exactly why the earlier whole-word repair could not catch it: `COVER`
inside `LIGHT SWITCH COVER PLATE` is a whole word.

Two independent causes, both fixed:

1. `get_title_block_text` took everything right of 55 % of page width, which on a 3024 pt sheet
   swallows the keynote column.
2. A bare `COVER` matched inside that prose and `_KW_TITLE_BLOCK_ONLY` fired, and `title_sheet`
   means an empty pass list, which means the sheet is skipped entirely — zero API, zero geometry.

## What shipped

**`pipeline/text_shape.py`** — one tokenizer, two consumers, no cycle (`sheet_pass_matrix` cannot
import `pdf_analyzer`). A "plain word" is letters only; any token carrying a digit, period, colon,
quote or hyphen breaks a run, because on a drawing those characters are precisely what separates one
title-block field from the next and what terminates a sentence.

**Task 1 — the window is found by what it contains.** `_TITLE_BLOCK_WINDOWS` is an introspectable
module-level ladder of `(width_frac, height_frac)` pairs running narrow to wide and **ending with
today's window**. `get_title_block_text` keeps the first candidate that passes
`looks_like_title_block`; when none does it returns the widest, which is the historical behaviour
unchanged — a strict refinement. The ladder is geometric, not fitted: ANSI/ASME Y14.1 puts the title
block in a strip against the right edge, and a standard 5–6 in strip on the 42 in sheets all four sets
use is 12–14 % of the width. **The height fraction is never varied** — every candidate uses 0.80.

**Task 2 — a title word inside a sentence is not a sheet title.** `_find_title_position_hit` accepts a
bare `COVER`/`INDEX` only when its match sits in a title-shaped token run. Matches are considered in
`_find_hit`'s existing deterministic order (earliest, longest keyword, alphabetical) and the first in
a title position wins, so a page whose notes mention `COVER` before its title block does is still
classified by its title block.

**Task 3 — the gate now measures the classifier, not its backstop.** `coverage_probe.py` gained
`--no-veto` and a `pages_classifier_discarded` column reported in both modes.

## The two thresholds, their observed values, and their margins

Required by the plan. Every value was read off the four real plan sets; none is fitted to a skip
count, a quantity or a golden take-off.

| Threshold | Value | Observed value it came from | Reason for the margin |
|---|---|---|---|
| `PROSE_MIN_RUN_TOKENS` | 6 | Genuine title-block field values run **2 tokens** between separators (`CS-00 COVER SHEET 25-13.01` → `["COVER","SHEET"]`, identically on Moxy p0/p1 and Bob's p0). The keynote prose that caused the defect runs **9–10 tokens** (`PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE INDICATING`). | 6 sits 3× above the observed genuine field value and 2–3 tokens below the observed prose, i.e. near the midpoint of a gap with no measured occupants. |
| `PROSE_MIN_FUNCTION_WORDS` | 2 | The genuine Moxy title block's longest run (`DATE SHEET TITLE PHASE A KING TYPE A GUESTROOM`, 9 tokens) carries **zero** function words. The two collisions carry **2** (`ON`, `THE`) and **4** (`AT`, `THIS`, `AT`, `IF`). | 2 is one more than the single `AND` a legitimate compound title (`COVER SHEET AND DRAWING INDEX`) can carry, and at or below every measured prose run. |
| `MIN_TITLE_BLOCK_EVIDENCE` | 2 | Moxy's tight window carries 5 field labels + a sheet ID; Chelsea's carries 0–1. | Two independent pieces, so neither a lone `DATE` in a revision note nor a lone cross-reference (`SEE A-101`) can pass a window off as a title block. |

**Why two signals and not one — the measurement that forced it.** Neither threshold alone separates
the populations. The *correct* Moxy window contains a 9-token run, so length alone would reject it;
a short instruction would pass function-words alone. This is pinned by
`test_length_alone_would_reject_the_correct_window`, which asserts the 9-token run exists *and* that
the window is still not prose-shaped.

## Results — measured, zero API

Classification alone (`coverage_probe --no-veto`), the column D-04 grades:

| Set | Pages | Classifier-discarded before | After | Which pages | Type histogram before → after |
|---|---|---|---|---|---|
| Moxy | 40 | **18** | **2** | `[0, 1]` — the real cover, and the LIGHTING COVER SHEET whose index lists 11 drawing names and carries zero printed scales | `title_sheet 18 → 2`, `floor_plan 13 → 29`, `elevation 9 → 9` |
| Crow | 4 | 0 | **0** | `[]` | unchanged: `floor_plan 1, elevation 1, detail 2` |
| Bob's | 7 | 1 | **1** | `[0]` — a genuine cover sheet | unchanged: `title_sheet 1, floor_plan 3, schedule 2, elevation 1` |
| Chelsea | 32 | 0 | **0** | `[]` | unchanged: `floor_plan 22, roof_plan 4, elevation 6` |

**No floor-plan or roof-plan count fell anywhere** — the specific damage a fraction sweep does
(INV-00 §1d measured Chelsea `floor_plan 9 → 1`, `roof_plan 5 → 1` at 0.88). Chelsea's three type
counts are byte-identical.

**Each cause is independently sufficient.** With Task 1's window search bypassed so only Task 2's
guard is active, the legacy 0.55 window alone gives Moxy `[0, 1]`, Crow `[]`, Bob's `[0]`,
Chelsea `[]` — the same result. Both shipped anyway, per 23-CONTEXT: fixing only whichever one moves
the number would leave the other live for the next drafting office.

**Sheet-identifier invariance.** `_sheet_name_from_doc` is the second consumer of this window
(gitnexus impact: direct caller, blast radius HIGH). 83 pages across all four sets, **0 changes**.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1511 passed, 2 deselected** (baseline after 23-05: 1465) |
| Four-set gate `tests/test_four_set_coverage.py` | 14 passed |
| Classification-alone gate, one test, four sets, veto disabled | passes; asserts the veto did not fire |
| `_TITLE_BLOCK_WINDOWS[-1] == (0.55, 0.80)`, resolved values | passes — no page fraction changed |
| `_KW_TITLE_BLOCK_ONLY == frozenset(['INDEX','COVER'])` | passes — keyword set untouched |
| Sheet IDs byte-identical, 4 PDFs | 83/83 pages, 0 differences |
| Python 3.9 | `ast.parse(feature_version=(3,9))` clean on every changed file |
| Zero API | no golden marker, no `ANTHROPIC_API_KEY`, no paid script invoked |
| `gitnexus impact` before editing / `detect-changes` before committing | run |

**Impact analysis, per CLAUDE.md.** `get_title_block_text` returned **HIGH** — 6 impacted symbols,
3 direct callers (`_sheet_name_from_doc`, `get_pdf_metadata`, `run_pdf_analysis`), 2 affected
execution flows (`upload_pdf`, `run_pdf_analysis`), 3 modules. Mitigated exactly as the plan
required: signature unchanged, the widest candidate preserves today's extraction, and the naming
consumer is pinned byte-for-byte on all four real PDFs. `classify_sheet_type_from_text` returned
**UNKNOWN / 0 impacted** because the index is stale for that symbol (the hook reports the index at
`06ea476`); plan 23-01 recorded it as **CRITICAL** (10 impacted, 3 direct callers) and that figure was
treated as authoritative — the signature and every non-collision outcome are unchanged, pinned by the
23-01 equivalence sweep.

## Deviations from Plan

### 1. [Rule 2 — missing critical functionality] A new module, `pipeline/text_shape.py`

- **Plan's `files_modified`** lists only `pdf_analyzer.py`, `sheet_pass_matrix.py`,
  `coverage_probe.py` and two test files.
- **Why:** both tasks need the same tokenizer, the same function-word set and the same run
  definition. `sheet_pass_matrix` cannot import `pdf_analyzer` — that is an import cycle — so the
  alternatives were to duplicate the logic in two modules that must then be kept in step, or to put
  it in one place. 23-CONTEXT's "build shared primitives ONCE (SP-1…SP-10)" decides this directly.
- **Impact:** none on behaviour; the module is pure text in, booleans out, with no I/O and no `fitz`.

### 2. [Rule 1 — a test that only passed while the bug was present] `test_moxy_guestroom_prototypes_are_recovered`

- **Found during:** Task 1, full-suite run — the only failure.
- **Issue:** the test required `len(pages_overruled) >= 16`, i.e. that plan 23-01's skip **veto** had
  rescued 16 pages. With the classifier repaired the pages are never misclassified, so the veto
  correctly recovers nothing and the assertion failed. The test was measuring the mechanism, and that
  mechanism only fires while the defect exists.
- **Fix:** renamed to `test_moxy_guestroom_prototypes_reach_the_engine` and re-expressed as an
  outcome — all 16 prototype pages (indices 23–38) are non-skipped **and** each carries a plan title
  with a printed scale or a scaled viewport. Validated by position/shape, never by a quantity. The
  overruled-pages invariant is retained for whichever pages the veto does still handle.
- **Commit:** `8d510fd`

### 3. [Expected] Two 23-01 tests changed expectation, both by their own instructions

- `test_cover_plate_collision_is_recorded_not_repaired` pinned the live defect and stated: *"The
  structural repair belongs to plan 23-06 … when it lands, this expectation changes deliberately, in
  that plan."* It has landed. **Inverted rather than deleted** — the phrase that cost 16 sheets stays
  in the suite forever as the regression it is.
- `test_the_sentinel_carries_the_reason` borrowed that same keynote purely because it produced a
  skip; its actual subject is the skip sentinel carrying its reason. It now uses a genuine cover
  sheet (`CS-00 COVER SHEET 25-13.01`), preserving the intent.
- **Commit:** `ae0c83b`

### 4. [Minor] Test placement

The plan lists Task 1's tests under `tests/test_sheet_pass_matrix.py`. That file's own header
guarantees "No PDF files or API keys required" and it spec-loads the classifier in isolation, so the
tests were placed by concern: pure-text structural tests in `test_sheet_pass_matrix.py`, the window
ladder and fallback pins in `test_sheet_name.py` (the existing home of `TestGetTitleBlockText`), and
the real-PDF assertions in `test_four_set_coverage.py`.

### 5. [Minor] Chelsea's floors were re-measured rather than taken from INV-00 §1d

§1d records Chelsea at `floor_plan 9, roof_plan 5`; the probe measures `22` and `4` on today's HEAD.
§1d was taken on an older HEAD. The literals in the gate are the re-measured ones, because a
regression test can only honestly compare against the state the change landed on — using §1d's
numbers would have made the floors trivially satisfiable. §1d remains cited as the source of the
trap the floors exist to catch.

## Known Stubs

None.

## Threat Flags

None. The plan's four registered threats are mitigated and pinned:

- **T-23-21** (crafted prose steering a sheet) — structural window selection plus the match-context
  guard, both gated by the four-set check.
- **T-23-22** (search multiplies extraction work) — the ladder is 4 fixed candidates and
  `page.get_text("words")` is served from the page's parsed display list, so the page is not
  re-parsed per candidate. Full-suite wall time is unchanged within noise.
- **T-23-23** (wider classification buying paid vision passes) — this plan changes classification
  only. 23-01's `deterministic_only` veto path and its raising-stub zero-API tests are untouched and
  still pass; no probe or gate in this plan can reach a paid entry point, asserted by
  `test_the_probe_spends_nothing`.
- **T-23-24** (fixing one office by regressing another) — the single-test four-set gate with per-set
  type floors, plus the resolved-value pin that no page fraction changed.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `8d510fd` | Identify the title block by its structure, not a page fraction |
| 2 | `ae0c83b` | A title word inside a sentence is not a sheet title |
| 3 | `b0be492` | Grade the classifier with the veto removed, on all four sets |

## What this unblocks

The 16 Moxy guestroom prototypes now reach the deterministic engine, so `_measure_room_fills` runs on
the sheets that carry every guestroom quantity — the precondition INV-00 §1e's end-to-end simulation
needed. **That simulation is not a promise of accuracy**: §1e's own caveats stand, the golden 58,680 SF
covers non-guestroom ceilings the prototypes cannot sum to, and four manifest `unit_count`s are known
wrong. The honest statement is that an item reporting nothing can now report something, and 23-08's
room-mix census decides what that something is.

23-01's skip veto is deliberately left in place though it now recovers nothing on all four fixtures.
It is the backstop for the fifth drafting office, and `test_the_veto_has_nothing_left_to_recover`
records that it is currently idle rather than removing it.

## Self-Check: PASSED

`src/bobbytailor/pipeline/text_shape.py` exists on disk; commits `8d510fd`, `ae0c83b`, `b0be492`
exist in git history.
