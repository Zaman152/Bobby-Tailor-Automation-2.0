---
phase: 23-measurement-engine-completion
plan: 03
subsystem: pipeline/coverage + deterministic/room_fill + vision/fusion
tags: [flagged-zero, SP-8, optional-quantity, provenance, drop-records, flag-dont-drop, room-probe, INV-08]
status: complete

requires:
  - phase: 23-01
    provides: "pipeline.coverage (DrawingCoverage / ItemCoverage / SheetCoverage dispositions) and pipeline.provenance.provenance_of_row — this plan is the first code to populate them"
provides:
  - "takeoff_summary row contract: quantity Optional[float], provenance, measured"
  - "aggregator._expected_items_without_a_manifest — plans-only completeness"
  - "aggregator._row_status — the four-value status computed from the record"
  - "bundle keys: excluded_viewports, coverage_drops (takeoff_pipeline)"
  - "bundle keys: coverage_notes, item_coverage (fusion)"
  - "sheet-dict keys: _excluded_viewports, _coverage_drops, _coverage_notes, _item_coverage, _page_index"
  - "TakeoffPipeline._record_sheet_coverage — sheet records reach the ledger row"
  - "_measure_room_fills returns (fills, drops)"
  - "measure_enclosed_area(dropped_regions=...) out-list"
  - "select_fill_for_basis returns a flagged fill WITH its flag"
  - "scripts/room_probe.py --engine {vector,fill} — the first committed probe of the fill engine"
affects:
  - "23-17 (report-side surfacing consumes excluded_viewports / coverage_drops / coverage_notes / item_coverage and the new row fields)"
  - "every wave from 3 onward — the honest-failure branch now has somewhere to write"
  - "reporter.generate_report / export_takeoff_excel.py — quantity may now be None (audited, no change needed here; 23-17 owns their emission)"

tech-stack:
  added: []
  patterns:
    - "a drop is a record, not a log line: every `continue` that loses a measurement appends a named DrawingCoverage"
    - "None is not zero, and the test is `is None` — never a comparison against 0"
    - "status is computed from what the run DID, then read back; nothing infers provenance from the value"
    - "the disposition only ever moves downwards in confidence — a record can never upgrade a skip to a measurement"
    - "prefer-then-fall-back instead of filter-then-vanish (select_fill_for_basis)"
    - "a probe that skips a page says so — silence in the tooling is the same defect one layer out"

key-files:
  created: []
  modified:
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - src/bobbytailor/pipeline/aggregator.py
    - src/bobbytailor/vision/fusion.py
    - src/bobbytailor/deterministic/room_fill.py
    - scripts/room_probe.py
    - tests/test_takeoff_pipeline.py
    - tests/test_aggregator.py
    - tests/test_fusion.py
    - tests/test_room_fill.py
    - .planning/phases/23-measurement-engine-completion/deferred-items.md

key-decisions:
  - "`provenance_of_row` is called WITH an explicit status the aggregator computed. Its value-sniffing fallback maps source='manifest' to HUMAN INPUT, which would relabel a geometry-measured row that the manifest merely NAMED — the aggregator's own docstring says quantity provenance is never altered there. Passing the status exercises the record-first branch, which is what the must-have asks for."
  - "Expected items in plans-only mode come from library entries carrying a measure BASIS. A basis is the app's own statement that it knows what measuring the item would mean, so its absence is a gap rather than noise. Measured on the real sets this is 10 rows for Bob's and 25 for Crow — bounded, and `Lintels` is among them, which is INV-08's own S13 example."
  - "Library resolution is recorded BEFORE naming precedence is applied, so an object a human renamed is not also reported missing under the library's term for it. Found by an existing test; see deviation 1."
  - "A drawing-level drop uses SKIPPED_NO_SCALE only for the two genuine scale causes and ERRORED for the degenerate clip and the empty-region case. No new disposition constant was added: coverage.py is 23-01's file and is not in this plan's file list."
  - "`excluded_viewports` is kept SEPARATE from `coverage_drops` because an off-scale exclusion is CORRECT behaviour, not a failure — conflating them would make a well-measured Crow sheet read as partial."
  - "V4-MEAS-06 is ADVANCED, not satisfied — its door-schedule half is untouched. Left unchecked, per 23-02's precedent."

requirements-completed: []
requirements-advanced: [V4-MEAS-06]

coverage:
  - id: D1
    description: "A never-measured line item reports a blank quantity, never the number zero"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py::TestQuantityIsOptional::test_a_manifest_missing_item_is_none_not_zero"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py::TestQuantityIsOptional::test_a_measured_zero_stays_a_measured_zero"
        status: pass
      - kind: integration
        ref: "no-silent-zero assertion replayed over three real saved runs' calculated_takeoff"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every quantity row states a provenance computed from the run's record, not guessed from the value"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py::TestQuantityIsOptional::test_every_row_carries_a_provenance_from_the_four_value_vocabulary"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py::TestQuantityIsOptional::test_a_manifest_named_measurement_is_not_relabelled_as_human_input"
        status: pass
    human_judgment: false
  - id: D3
    description: "A plans-only run with no manifest emits a NOT MEASURED row for an expected item that never appeared"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py::TestPlansOnlyCompleteness (6 tests)"
        status: pass
      - kind: other
        ref: "real harvest: Bob's emits 10 NOT MEASURED rows including Lintels; Crow 25 — zero rows of any kind before"
        status: pass
    human_judgment: false
  - id: D4
    description: "A successfully measured area is never discarded without a trace"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_fusion.py::test_measured_fills_with_no_area_basis_leave_a_coverage_note"
        status: pass
      - kind: unit
        ref: "tests/test_room_fill.py::test_a_flagged_fill_is_returned_with_its_flag_not_dropped"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_a_flagged_fill_now_produces_a_flagged_row_instead_of_nothing"
        status: pass
    human_judgment: false
  - id: D5
    description: "Crow page 0's four deliberately excluded viewports are recorded on the bundle"
    requirement: V4-MEAS-06
    verification:
      - kind: other
        ref: "free real-PDF check: bundle['excluded_viewports'] == 4 S.C.C.P. details, each with its 60x ratio; the key did not exist pre-change (INV-08 §1.4)"
        status: pass
      - kind: unit
        ref: "tests/test_takeoff_pipeline.py::TestDeterministicBundleCoverageKeys"
        status: pass
    human_judgment: false
  - id: D6
    description: "scripts/room_probe.py runs both engines without raising"
    requirement: V4-MEAS-06
    verification:
      - kind: other
        ref: "--engine vector --fpi 4.0 on Moxy: exit 0, 40 page lines, 0 errors, TOTAL rooms=101 (was 0)"
        status: pass
      - kind: other
        ref: "--engine fill --pages 23,27,29,33 reproduces RCP 229.4 / 341.7 / 272.6 / 274.6 exactly"
        status: pass
    human_judgment: false

metrics:
  duration: ~3h
  completed: 2026-08-03
  tasks: 3
  commits: 3
  tests_added: 43
  suite: "1353 passed, 2 deselected (baseline 1310)"
---

# Phase 23 Plan 03: The Flagged-Zero Contract (SP-8, second half) Summary

**`quantity` is now `Optional[float]`: a never-measured item ships `None` and a measured zero
still ships `0.0`, so for the first time a blank and "the building has none of this" are different
facts — and all fifteen of INV-08's silent-drop paths inside this plan's scope leave a named
record instead of a `continue`.**

## Performance

- **Duration:** ~3h
- **Tasks:** 3 of 3
- **Files modified:** 10 (0 created) — 1,481 insertions, 47 deletions

## What shipped

**Drop records on every silent path (`takeoff_pipeline.py`).** `_deterministic_bundle` returns two
new keys. `excluded_viewports` carries the DELIBERATE off-scale exclusion, which until now existed
as a `logger.info` and nothing more — INV-08 §1.4's `RETURN KEYS` dump is the proof that no consumer
could ever surface it, so a client could not tell "we correctly declined to measure four S.C.C.P.
details at 60× the wrong scale" from "we failed to find them". `coverage_drops` carries everything
the sheet failed to measure. `_measure_room_fills` returns `(fills, drops)` and each of its four
bare `continue`s now appends a `DrawingCoverage` naming the cause. `measure_enclosed_area` takes an
optional `dropped_regions` out-list so an oversize rejection is *stated*, not merely applied — with
**no size constant moved** (INV-08 risk 6; `MAX_REGION_SF` is still 900.0 and a test asserts it).

**`quantity: Optional[float]` (`aggregator.py`).** `aggregator.py:435` shipped the defaultdict's
`0.0` for a `manifest_missing` row and put `"—"` only in `quantity_fmt`, so every NUMERIC consumer
read a blank as a zero. A never-measured item now ships `None`. Each row carries `provenance` (the
four-value client vocabulary) and `measured`, both **computed from the record** — `_row_status`
never looks at the number, and `provenance_of_row` is called with that status so its record-first
branch is what answers.

**Completeness without a manifest.** The guarantee used to be gated on `if manifest:`, so in
plans-only mode — the mission mode — nothing enumerated what was expected and an unmeasured item
had no row of any kind. Expected items now also come from `learned.expected_items` (at the prompt
renderer's own expectation threshold) and from library entries carrying a measure basis.

**Flag-don't-drop (`room_fill.py`, `fusion.py`).** `select_fill_for_basis` no longer filters flagged
fills away; an unflagged candidate still wins, and when every candidate of the right discipline is
flagged the smallest comes back **with its flag intact**. `_fuse_room_fills`'s three silent exits
became `bundle["coverage_notes"]` entries and an `ItemCoverage(status=NOT MEASURED, quantity=None)`.

**A room probe that actually runs (`scripts/room_probe.py`).** `select_main_plan` gets real
`(viewport, ViewportScale)` pairs built from the same printed-scales-by-region mapping the pipeline
builds. Pairing each viewport with `None` made it dereference a null scale on every page — the
`AttributeError` reported independently by INV-01 §7, INV-02 §9 and INV-08 §1.5. New `--engine fill`
runs the enclosed-region engine that produces Moxy's numbers; **no committed script exercised it
before**, which is precisely why a wrong diagnosis of those areas went unchallenged for so long.

## Measured results (all free, zero API)

**Crow page 0 — the off-scale exclusion is finally visible.** Pre-change `bundle['excluded_viewports']`
raised `KeyError`; the key did not exist.

```
excluded_viewports: 4
  R3 | TYPICAL S.C.C.P. JOINT DETAIL   | excluded_off_scale | printed 0.0093 vs page 0.5556 ft/pt -> 60x wrong
  R4 | TYPICAL S.C.C.P./ SF DETAIL     | excluded_off_scale | ...
  R5 | TYPICAL S.C.C.P. CORNER DETAIL  | excluded_off_scale | ...
  R6 | TYP. S.C.C.P. MITERED CORNER    | excluded_off_scale | ...
```

**Moxy page 23 — the drop INV-00 §1.3 had to catch by hand.** Five fills at exactly the INV-08 §1.3
areas (193.2 / 198.3 / 185.1 / 166.7 / 229.4), plus:

```
DROP FILL-4 | KING A - FC PLAN | skipped_no_scale |
  no printed scale beneath the title — measuring it at a borrowed scale would be a squared error
```

**The fill probe reproduces the four pinned RCP areas exactly:**

| Page | Drawing | RCP area |
|---|---|---|
| 23 | KING A | **229.4 SF** |
| 27 | KING SUITE B | **341.7 SF** |
| 29 | QQ A | **272.6 SF** |
| 33 | BUNK B | **274.6 SF** |

**The vector probe went from dead to working:**

| | Before | After |
|---|---|---|
| Moxy `--engine vector --fpi 4.0` | `AttributeError` on ~30 pages, `TOTAL rooms=0` | exit 0, **0 errors**, 40 page lines, `TOTAL rooms=101` |
| Crow, either engine | printed **nothing at all**, reported `TOTAL rooms=0` | one stated line per page, with the reason |

**Plans-only completeness on the real sets** — before this plan every one of these had NO ROW OF ANY
KIND (INV-08 §2 row S13):

| Set | Library entries | NOT MEASURED rows now emitted |
|---|---|---|
| Bob's | 10 | 10 — incl. **`Lintels`**, INV-08's own S13 example |
| Crow | 25 | 25 |

## T-23-09 — the mandatory consumer audit

`grep -rn 'quantity' src/bobbytailor/web/` → **45 hits**. Every one that touches a *summary-row*
quantity numerically was already `None`-safe; **no bare coercion was found, so no guard had to be
added**:

| Consumer | Line | Coerces? | How it is already guarded |
|---|---|---|---|
| `verify._qty_fmt` | 430-435 | `float(qty)` | inside `try/except (TypeError, ValueError)` → `float(None)` raises `TypeError` → returns `"—"` |
| `verify._row_qty_num` | 660-668 | `float(str(q)...)` | explicit `if q in (None, "—", ""): return None` **before** the coercion |
| `verify` verified-count | 650 | no | `r.get("quantity") not in (None, "—")` |
| `verify._rebuild_summary` | 482-483, 498-500 | `_qty_fmt` | operates on `aggregate_measurements` / override dicts, not aggregator rows; and `_qty_fmt` is safe anyway |
| `verify` override endpoints | 81, 174, 232, 621, 756 | `float(qty)` in `try` | user-supplied override bodies, not summary rows; `qty is not None` gate at 622 |
| `static/app.js` | 1877-1898 | no | renders strings into a table cell |
| `js/reports-workspace.js` | 363-364 | no | `r.quantity === null \|\| r.quantity === undefined` is the first branch |
| `js/reports-workspace.js` | 443 | no | `(r.quantity_fmt ?? r.quantity ?? '—')` |
| `js/reports-workspace.js` | 384, 589 | no | `r.quantity != null && r.quantity !== '—'` |

Audited **outside** `web/` as well, since the field is public:

| Consumer | Verdict |
|---|---|
| `reporter._write_takeoff_summary_csv:702` | `row.get("quantity_fmt") or row.get("quantity")` → writes `"—"`. No crash. Emitting `""` instead is **23-17's** task, deliberately not touched here. |
| `reporter._write_summary:945+` | reads `quantity_fmt` only |
| `scripts/score_report_dir.py:42` | `_num()` already maps `""` / `"—"` / `None` → `None` |
| `scripts/export_takeoff_excel.py:39,86,89` | `float(row.get("quantity") or 0)` (sort key only) and a value-sniffing `_provenance`; safe. 23-17 replaces it with `provenance_of_row`. |
| `scripts/vision_only_benchmark.py:207` | `try: float(...) except (TypeError, ValueError): return None` |
| `learning/retrieval.py:387` | `try/except (TypeError, ValueError)`; also operates on components, and has no production caller |
| `takeoff_pipeline.py:3651,3697` | `float(c.get("quantity") or 0)` on **components**, not summary rows |

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1353 passed, 2 deselected** (baseline 1310) |
| Four-set gate `tests/test_four_set_coverage.py` | green — Moxy 2, Crow 0, Bob's 1, Chelsea 0, unchanged |
| Crow page 0 `excluded_viewports` | exactly **4**, each an S.C.C.P. detail with its 60× ratio |
| Moxy page 23 drop record | 1 — `KING A - FC PLAN`, matching INV-00 §1.3 |
| `MAX_REGION_SF` untouched | prints `constant untouched` (900.0) |
| No-silent-zero assertion, 3 real saved runs | 0 rows pairing `quantity == 0.0` with `MEASURED`; 0 blank rows outside NOT MEASURED / NEEDS REVIEW |
| `room_probe --engine fill` on Moxy 23/27/29/33 | 229.4 / 341.7 / 272.6 / 274.6, within 0.1 SF |
| `room_probe --engine vector --fpi 4.0` on Moxy | exit 0, **0** errors on 40 pages |
| `gitnexus detect-changes` | run before each of the three commits |

**Impact analysis was run before editing, per CLAUDE.md.** Three targets came back **HIGH** and are
reported here as required:

| Symbol | Risk | Impacted | Processes | Mitigation |
|---|---|---|---|---|
| `aggregate_takeoff` | **HIGH** | 7 | `run_project_scrape`, `run_analyze_from_manifest`, `generate_report`, `run_pdf_analysis` | The `quantity` type change is the plan's deliverable. Mitigated by the full consumer audit above (T-23-09) — every numeric consumer on **both** entry points is already `None`-safe — plus 20 new aggregator tests. Signature unchanged. |
| `_measure_room_fills` | **HIGH** | 3 | `_run_sheet_vector`, `_deterministic_bundle`, `run_sheet` | Return type changed from `list` to `(list, list)`. It is a private method with **one** caller (verified by grep across `tests/` and `scripts/` too); the caller was updated in the same commit. |
| `_fuse_room_fills` | **HIGH** | 3 | `_run_sheet_vector`, `fuse_sheet`, `run_sheet` | Signature unchanged; all additions are new keys on the passed-in bundle. Pinned by a test asserting a clean binding writes **no** notes and **no** item-coverage, so the records cannot become noise. |

`_deterministic_bundle`, `select_fill_for_basis` and `measure_enclosed_area` returned LOW.

## Deviations from Plan

### 1. [Rule 1 — bug in this plan's own Task 2] A renamed object was reported both measured and missing

- **Found during:** Task 3 verification, by the pre-existing
  `test_naming_conventions.py::test_learned_correction_outranks_estimator_normalization`.
- **Issue:** the new plans-only completeness guarantee enumerated a library object whose bucket was
  named by a **human's learned rename** instead of by the library term. On that fixture the take-off
  published `Internal Tilt up walls = 106,997 SF` **and** a `Tilt Up Wall = NOT MEASURED` row for the
  very same physical walls. Telling a client "your tilt-up walls were not measured" two rows below
  the measurement is worse than the silence this plan exists to abolish.
- **Fix:** `_resolve_library_name` is now called **once, before naming precedence is applied**, and
  every resolved library name is recorded in `library_bound`. An expected item is skipped when some
  contributing description resolved to it, whatever name the run finally published.
- **Pinned by:** `TestCompletenessDoesNotContradictItself` (2 tests — one that the false row is gone,
  one that the guard has not swallowed the guarantee it protects).
- **Commit:** `5ce118a`

### 2. [Rule 2 — missing critical functionality] `provenance_of_row` is called with an explicit status

- **Found during:** Task 2, before writing code.
- **Issue:** the plan says "add `provenance` computed by `provenance_of_row`". Called on a bare
  aggregator row, its fallback maps `source in ("manifest", "learned", …)` → `HUMAN INPUT`. But
  `source` in the aggregator is a **NAMING** marker — its own docstring says *"quantities are summed
  from the underlying items untouched (quantity provenance is never altered here)"*. A row the
  manifest merely NAMED but the geometry MEASURED would have been published as a human input.
- **Fix:** the aggregator computes the status itself in `_row_status` from what it recorded
  (`is_unknown` / `has_rows` / `needs_review` / legend / standard-line-item) and passes it, so
  `provenance_of_row`'s **record-first** branch answers. That is exactly the must-have's wording —
  "computed from the run's record rather than guessed from the value" — and it keeps one definition
  of the vocabulary.
- **Pinned by:** `test_a_manifest_named_measurement_is_not_relabelled_as_human_input`.
- **Commit:** `97c2073`

### 3. [Rule 2] The room probe was still silent about the pages it skipped

- **Found during:** Task 3 acceptance, running the repaired probe on Crow.
- **Issue:** fixing the `AttributeError` made the probe run, and it then printed **nothing at all**
  for Crow and reported `TOTAL rooms=0` — because every Crow page classifies `schedule` on full-page
  text and the probe's type gate `continue`d past all four. INV-08 §1.5 names this exact thing: *"the
  probe itself silently continues past every non-plan sheet — the same blindness reproduced in the
  tooling."* Shipping a probe whose zero has no explanation would contradict the plan it belongs to.
- **Fix:** both engines print one line per page, stating the reason when nothing was measured. No
  gate was changed — the skip is still the skip; it just says so now.
- **Commit:** `5ce118a`

### 4. [Minor] Two drawing-level drops use `ERRORED` rather than a new constant

The degenerate-clip and no-surviving-region cases have no exact match in 23-01's disposition
vocabulary. `SKIPPED_NO_SCALE` is reserved for the two genuine scale causes (it feeds
`drawings_dropped_no_scale` and the ledger warning that says *"no printed scale of their own"*), and
`NOT_APPLICABLE` would claim the drawing set genuinely has none. Both use `ERRORED` with an explicit
reason string. A new constant was **not** added because `coverage.py` is 23-01's file and is not in
this plan's `files_modified`.

### 5. [Scope boundary — logged, NOT fixed] DEF-23-04

`tests/test_room_fill.py::test_max_region_guard_rejects_sheet_scale_regions` passes for the wrong
reason: its 60′×40′ room at 1/4″ is 1,080 × 720 pt on an 800 × 800 pt page, so the region **touches
the clip edge** and is discarded as the outside before the size filter is reached. Proven by the new
out-list coming back **empty**. Nothing is broken today, but the test would keep passing if
`MAX_REGION_SF` were deleted. Rewriting an existing pin is out of scope and would be
indistinguishable from tuning a guard, so it is logged in `deferred-items.md`; the new
`test_oversize_rejection_is_recorded_when_an_out_list_is_supplied` draws its 1,200 SF region at 1/8″
so it genuinely fits the page and **does** exercise the filter.

---

**Total deviations:** 3 auto-fixed (1× Rule 1, 2× Rule 2), 1 decision recorded, 1 logged and not fixed.

## Issues Encountered

**One existing test encoded the behaviour this plan exists to change.**
`test_unnamed_geometry_still_flagged_after_library_merge` asserted `len(rows) == 1` — i.e. that a
library entry producing no component gets no row. That IS S13. Its real intent ("a needs_review
component the library can't name is still emitted and stays flagged") was preserved and asserted
directly, and the new NOT MEASURED row was pinned alongside it rather than the count being relaxed.

## Known Stubs

None. Every new key is populated by real code paths and verified against the real PDFs.

Two things are deliberately **not** here and are **23-17's** scope, per this plan's own objective:
the four report fields / `coverage.json` / the `summary.txt` COVERAGE section / the CSV column and
workbook sheet, and rewriting `export_takeoff_excel._provenance` to read `row["provenance"]`. The
records they need are all on the bundle, the sheet dict and the ledger row as of this plan.

## Threat Flags

None — no new security-relevant surface.

- **T-23-09 (a consumer doing a bare float coercion)** — mitigated: the mandatory audit is recorded
  in full above, across `web/`, the reporter, both scripts and the learning store. Zero bare
  coercions of a summary-row quantity were found.
- **T-23-10 (unbounded drop records)** — mitigated: `DrawingCoverage` stays flat (no bitmaps, no
  region lists — the oversize areas are folded into one reason string), and records are bounded by
  the drawing count per sheet. `_record_sheet_coverage` writes `measurable_signal["geometry"] = 1`
  rather than the geometry payload.
- **T-23-11 (drawing text in reasons)** — accepted, as registered. Reasons embed a viewport title
  the report already renders.
- **T-23-12 (a measured area discarded with no trace)** — mitigated: all three fusion exits, all four
  measurement `continue`s and the flagged-fill return are each pinned by a test.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `08dc7cc` | Every drop inside the pipeline leaves a reason |
| 2 | `97c2073` | `quantity` becomes `Optional[float]`; every row states its provenance |
| 3 | `5ce118a` | Flag-don't-drop in the selector and the binder, and a working room probe |

## Requirement status

`V4-MEAS-06` is **advanced, not completed.** Its second half — *"zero-geometry sheets emit an
explicit coverage flag (blank never reported as zero)"* — is the contract this plan closes at the
data layer, but its first half — *"per-format door-schedule parsing across Crow, Bob's and Moxy
formats"* — is untouched, and the flag does not reach a client artifact until 23-17 surfaces it.
`REQUIREMENTS.md` was therefore deliberately left unchecked, exactly as 23-02 did for V4-MEAS-03.

## What this unblocks

Every wave from 3 onward inherits the contract this plan establishes: a measurement that fails now
has a typed place to say so (`DrawingCoverage` on the bundle, `ItemCoverage` on the fusion side,
`quantity=None` + `provenance` on the row), so no later plan has to invent one or fall back to a
zero. 23-17 has every record it needs to surface, already populated and verified against real PDFs.
And the fill engine — the one that produces Moxy's guestroom numbers — finally has a committed probe,
so the next diagnosis of those areas can be checked in one command instead of argued from a log.

The standing caution from INV-08 risk 4 applies to everything above: this plan makes the run
**honest**, not accurate. Moxy will report more blanks and more flags than before, and that is the
intended direction. A green coverage number measures accounting, not correctness, and must never
become the target.

## Self-Check: PASSED

- `src/bobbytailor/pipeline/takeoff_pipeline.py` — FOUND
- `src/bobbytailor/pipeline/aggregator.py` — FOUND
- `src/bobbytailor/vision/fusion.py` — FOUND
- `src/bobbytailor/deterministic/room_fill.py` — FOUND
- `scripts/room_probe.py` — FOUND
- `tests/test_takeoff_pipeline.py`, `tests/test_aggregator.py`, `tests/test_fusion.py`, `tests/test_room_fill.py` — FOUND
- `.planning/phases/23-measurement-engine-completion/deferred-items.md` — FOUND
- commit `08dc7cc` (Task 1) — FOUND
- commit `97c2073` (Task 2) — FOUND
- commit `5ce118a` (Task 3) — FOUND
