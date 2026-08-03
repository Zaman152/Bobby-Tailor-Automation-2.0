---
phase: 23-measurement-engine-completion
plan: 17
subsystem: pipeline/reporter + export
tags: [flagged-zero, SP-8, coverage-ledger, provenance, INV-08, client-artifacts]
status: complete

requires:
  - phase: 23-01
    provides: "pipeline.coverage (CoverageLedger / SheetCoverage / DrawingCoverage / ItemCoverage) and pipeline.provenance.provenance_of_row"
  - phase: 23-03
    provides: "the records this plan renders — quantity Optional[float] + provenance + measured on every row, _excluded_viewports / _coverage_drops / _coverage_notes / _item_coverage on every sheet dict"
provides:
  - "generate_report(coverage=..., source_pdf=...) — keyword-only, None-default"
  - "report fields: coverage, coverage_ledger, item_coverage, coverage_warnings, pages_in_source, source_pdf"
  - "<run>/coverage.json and _files['coverage_json']"
  - "sheet_log entry key: error (+ sheet-type fallback for an errored sheet)"
  - "summary.txt COVERAGE section, between API USAGE and SCALE CONFIDENCE"
  - "takeoff_summary.csv provenance column; a not-measured quantity is an EMPTY cell"
  - "workbook Coverage worksheet + About pages-in-source/measured/skipped"
  - "reporter._coverage_for_report / _coverage_lines / _takeoff_summary_csv_quantity"
affects:
  - "every client artifact — takeoff.json, coverage.json, summary.txt, takeoff_summary.csv, takeoff.xlsx"
  - "web/blueprints/verify._rebuild_summary — a rebuilt quantity now rebuilds its provenance with it"
  - "23-16 (record correction) — the coverage numbers it must not let drift are now emitted"

tech-stack:
  added: []
  patterns:
    - "additive-or-absent: a new field appears only when the input that justifies it was supplied, so a pre-23 caller's report is byte-identical"
    - "the published row wins: an item-coverage record is only added for a name the take-off never published, so the report cannot contradict itself"
    - "the reporting ledger is a COPY — generate_report never mutates the record the pipeline still holds"
    - "correct-by-construction over compensating change: an empty CSV cell is what the existing scorer already maps to nothing"
    - "one place decides provenance, and it reads the record; the exporter became a formatter"

key-files:
  created:
    - .planning/phases/23-measurement-engine-completion/23-17-SUMMARY.md
  modified:
    - src/bobbytailor/pipeline/reporter.py
    - src/bobbytailor/pipeline/pdf_analyzer.py
    - src/bobbytailor/web/blueprints/verify.py
    - scripts/export_takeoff_excel.py
    - tests/test_reporter_accuracy.py
    - .planning/phases/23-measurement-engine-completion/deferred-items.md

key-decisions:
  - "Every coverage field is ABSENT, not None, when no ledger is supplied. The acceptance criterion is byte-identity for a pre-23 report, and a key present with a null value is not byte-identity. Consumers use .get()."
  - "The sheet-log repair (`error` + the `_sheet_type` fallback) is applied UNCONDITIONALLY, so `sheet_log` entries gain exactly one key. The same task mandates the S11 fix, and gating a bug fix on an unrelated argument would leave the pre-23 path broken forever. Pinned by an exact-key-order assertion."
  - "`item_coverage` is built from the PUBLISHED take-off rows first and from the pipeline's own ItemCoverage records only for names those rows never mentioned. 23-03 deviation 1's precedent: a report that says NOT MEASURED two rows below the measurement of the same thing is worse than the silence being fixed."
  - "The reporting ledger is a copy with `sheets` shared by reference and a fresh `items` list. Calling generate_report twice with one ledger would otherwise double every item row — pinned by a test."
  - "`pdf_analyzer.py` was edited (one call site, two keyword arguments) although it is not in files_modified. Without it the ledger reaches no artifact in a real run, which is the entire objective. Recorded as deviation 1."
  - "Off-scale exclusions are counted in their own workbook column, never folded into 'dropped'. 23-03 kept `excluded_viewports` separate for the same reason: the exclusion is CORRECT behaviour and conflating them would make a well-measured Crow sheet read as partial."
  - "V4-MEAS-06 is left UNCHECKED, following 23-02/23-03/23-04. Its coverage-flag half is now closed end to end, but 23-04 recorded that six plans claim this requirement and DEF-23-07 (below) shows one of 23-04's own record producers still has no production caller."

requirements-completed: []
requirements-advanced: [V4-MEAS-06]

coverage:
  - id: D1
    description: "The run writes coverage.json and a COVERAGE section that states in words that a blank is not a zero"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_coverage_json_is_written_registered_and_round_trips_the_summary"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_the_summary_states_in_words_that_a_blank_is_not_a_zero"
        status: pass
      - kind: other
        ref: "rendered COVERAGE section for the real 40-page Moxy ledger, pasted below"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every page of the source PDF has a row in the report, and the ledger length equals the page count"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_the_ledger_becomes_five_additive_report_fields"
        status: pass
      - kind: integration
        ref: "all four real plan sets, offline: Moxy 40/40, Crow 4/4, Bob's 7/7, Chelsea 32/32 — in the report AND in coverage.json"
        status: pass
    human_judgment: false
  - id: D3
    description: "A not-measured quantity is written to the CSV as an empty cell, never as a zero"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_a_never_measured_quantity_is_an_empty_cell_never_a_zero (asserted through scripts/score_report_dir._num)"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_a_measured_zero_and_a_blank_stay_distinguishable_in_the_csv"
        status: pass
      - kind: other
        ref: "5 real saved runs re-rendered through the new writer: 0 rows publishing a number under NOT MEASURED, 0 blanks without a flag"
        status: pass
    human_judgment: false
  - id: D4
    description: "An errored sheet renders with its type and its error message instead of as a typeless row with no items"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_an_errored_sheet_carries_its_message_and_its_type"
        status: pass
    human_judgment: false
  - id: D5
    description: "A report generated without a ledger renders exactly as it does today"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_a_report_with_no_ledger_is_shaped_exactly_as_before"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_a_report_with_no_ledger_renders_the_pre_change_summary_byte_for_byte"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_a_pre_23_run_still_exports_the_same_two_worksheets"
        status: pass
    human_judgment: false
  - id: D6
    description: "Provenance is decided in one place, from the record — a measured zero is not an absence"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_the_exporter_no_longer_owns_the_provenance_classification"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py::test_the_workbook_renders_the_recorded_provenance_not_a_guess"
        status: pass
      - kind: other
        ref: "real saved Crow run: Dock Leveler 0.0 -> MEASURED, Bollards 0.0 -> HUMAN INPUT, Lift 0.0 -> NEEDS REVIEW; the deleted helper called all three NOT MEASURED"
        status: pass
    human_judgment: false

metrics:
  duration: ~2h
  completed: 2026-08-03
  tasks: 3
  commits: 3
  tests_added: 20
  suite: "1531 passed, 2 deselected (baseline 1511)"
---

# Phase 23 Plan 17: Report + Export Emission of the Coverage Record Summary

**The ledger 23-01 built and 23-03 filled reached no artifact: `pdf_analyzer` constructed it,
threaded it through `run_project`, logged its warnings — and then called `generate_report`
without it. A run KNEW what it had failed to measure and nothing a client opens said so. It
now says so in `takeoff.json`, `coverage.json`, `summary.txt`, the CSV and the workbook, and a
never-measured quantity is a BLANK in every one of them.**

## Performance

- **Duration:** ~2h
- **Tasks:** 3 of 3
- **Files modified:** 5 (0 source files created) — 1,067 insertions, 17 deletions

## What shipped

**Five additive report fields, and none of them when there is no ledger (`reporter.py`).**
`generate_report` takes `coverage` and `source_pdf` as keyword-only arguments defaulting to
`None`, and adds `coverage`, `coverage_ledger` (one row per **page of the source PDF**, not per
processed sheet), `item_coverage`, `coverage_warnings` and `pages_in_source`. `sheets_processed`
keeps exactly the meaning it has always had — `pages_in_source` is what makes the difference
legible, which is INV-08's opening complaint (`Sheets analyzed: 22` on a 40-page set). `source_pdf`
closes a provenance gap of its own: the report had no record of its own input, so the
ledger-completeness invariant could not be checked from the artifact alone.

**`coverage.json`** is written beside `scale_calibration.json` using the same pattern, registered in
`_files`, and carries the summary, the warnings, the per-page rows and the item rows — so the record
can be read and diffed run to run without parsing the whole take-off.

**The sheet-log repair (INV-08 §2 row S11).** `takeoff_pipeline._error_result` sets `_sheet_type`;
the log read `sheet_type`. An errored sheet therefore rendered as `type=None` with zero items —
**indistinguishable from a sheet that genuinely held nothing.** The entry now falls back to
`_sheet_type` and carries the error message.

**The COVERAGE section.** Between API USAGE and SCALE CONFIDENCE, headed by the sentence this whole
phase exists for, and empty on a pre-23 report. Rendered from the real 40-page Moxy ledger:

```
──────────────────────────────────────────────────────────────────────
COVERAGE  (a blank is NOT a zero — an unmeasured item has no number,
           which is a different fact from a measured zero)
──────────────────────────────────────────────────────────────────────
Pages in source PDF:             40
  measured (geometry):           29
  vision-only (no geometry):      9
  skipped by classifier:          0
  not applicable (cover/idx):     2
  errored:                        0
```

and, on a ledger carrying drop records, the escalations and the item block:

```
!! 1 page(s) carry 6 measurable plan drawing(s) but were NOT measured
   (pages 1) (deciding keyword: COVER) — their items are blank, NOT
   zero
!! 1 drawing(s) were dropped for having no printed scale of their own
   — measuring them at a borrowed scale would be a squared error

Expected line items:              3
  MEASURED                        1
  NEEDS REVIEW                    0
  HUMAN INPUT                     1
  NOT MEASURED                    1   ← do NOT read these as zero
```

**The CSV.** A `provenance` column appended LAST (every existing column keeps its position for a
consumer reading by index), and a never-measured quantity written as the **empty string**. It used
to write `quantity_fmt`'s em-dash. Scoring stays correct **by construction** — `score_report_dir._num`
already maps `""` to nothing — and that is asserted end to end here rather than assumed (T-23-74).
A measured zero still writes `0` with provenance `MEASURED`.

**The workbook (`export_takeoff_excel.py`).** The local `_provenance` is **deleted**; the script
imports `provenance_of_row` from the package and renders the provenance the run RECORDED. A new
`Coverage` worksheet shows one row per page of the source PDF, highlighting a page discarded despite
carrying measurable drawings, and counting dropped drawings apart from correctly-excluded off-scale
viewports. `About` gains pages in source / measured / skipped, and the Coverage sheet's caption keeps
About's *"Do NOT read a blank as zero"* reachable from it.

## Measured results (all free, zero API)

**Ledger completeness on all four real plan sets** — INV-08's one-line acceptance, checked in the
report AND in `coverage.json`:

| Set | PDF pages | `coverage_ledger` | `coverage.json` sheets |
|---|---|---|---|
| Moxy | 40 | **40** | **40** |
| Crow | 4 | **4** | **4** |
| Bob's | 7 | **7** | **7** |
| Chelsea | 32 | **32** | **32** |

**The value-sniffing provenance was wrong on real data.** Five real saved runs were re-rendered
through the new CSV writer and the new exporter. On `Crow_-_Cass_White_Road_20260701_000626`:

| Item | Quantity | Deleted helper said | Recorded/derived provenance now |
|---|---|---|---|
| Dock Leveler | 0.0 | NOT MEASURED | **MEASURED** — a real measured zero |
| Bollards | 0.0 | NOT MEASURED | **HUMAN INPUT** |
| Lift | 0.0 | NOT MEASURED | **NEEDS REVIEW** |

That is T-23-73 (repudiation) in three cells: the old sheet published an absence where the run had a
finding. Across all five runs the new writer produced **0 rows publishing a number under
NOT MEASURED** and **0 blank cells without a flag**.

## T-23-70 — the additive-field mitigation, checked rather than asserted

The pre-change report shape was captured from HEAD before any edit and is pinned in the test file:

| Surface | Pre-23 | After |
|---|---|---|
| top-level report keys | 28 | **28** (unchanged without a ledger) |
| `_files` keys | 8 | **8** (unchanged; `coverage_json` appears only when written) |
| `summary.txt` | 49 lines | **byte-identical** (timestamp masked) |
| `sheet_log` entry keys | 21 | 22 — exactly one added (`error`), none renamed |

## Deviations from Plan

### 1. [Rule 3 — blocking] `pdf_analyzer.py` was edited, though it is not in `files_modified`

- **Found during:** Task 1, reading the call site.
- **Issue:** `run_pdf_analysis` builds the ledger (line 371), threads it into `run_project`, and
  calls `generate_report` **without** it. Landing this plan's five fields without that call-site
  change would have produced a reporter that CAN surface the record and a pipeline that never hands
  it over — the objective's own words ("until this plan lands the record exists only in memory")
  would still be true afterwards.
- **Fix:** two keyword arguments at one call site — `coverage=ledger, source_pdf=pdf_path`.
- **Commit:** `c8236df`

### 2. [Rule 2 — missing critical functionality] A human-entered quantity published a stale provenance

- **Found during:** Task 2, auditing the consumers of the new CSV column.
- **Issue:** `verify._rebuild_summary` rebuilds a row's quantity in three layers and left
  `provenance` (added by 23-03) untouched. An item that was `NOT MEASURED`, then measured against a
  verified scale or entered by a human in the verification workspace, would keep publishing
  **`12 EA` under `NOT MEASURED`** the moment this column reached the CSV and the workbook. That is
  the same lie as a blank spelled as a zero, pointing the other way, and my column is what would
  have made it client-visible.
- **Fix:** both rebuild layers now set the provenance WITH the quantity — geometry against a verified
  scale is `MEASURED`, a number a human entered or confirmed is `HUMAN INPUT` (`measured=False`).
- **Pinned by:** `test_a_human_entered_quantity_never_publishes_a_stale_provenance`.
- **Commit:** `38b3919`

### 3. [Decision] The sheet-log repair is unconditional, so `sheet_log` gains exactly one key

The plan's acceptance asks for a byte-identical no-ledger report AND, in the same task, for the S11
repair. Gating a bug fix on an unrelated argument would leave the pre-23 path broken forever, so
`error` is added to every entry and `type` falls back to `_sheet_type` always. The addition is
additive (no key renamed, no key dropped), the top-level report and `_files` shapes are untouched,
and the summary text is unchanged for a healthy sheet. The exact key ORDER is asserted so the
addition can never silently grow into two.

### 4. [Scope boundary — logged, NOT fixed] DEF-23-07

`door_schedule_coverage` (23-04) returns exactly the right records and **nothing in `src/` calls
it**. 23-04 named 23-17 as the plan that surfaces them; the surfacing side is done and waiting —
`_item_coverage_records` accepts an `ItemCoverage` object OR a dict, which is the shape that function
returns — but the records are never produced during a run, so Chelsea's *"a door schedule is
referenced … and no parsable schedule table exists in this PDF"* still cannot reach the report.
Choosing the pipeline call site is not a report-rendering decision, so it is logged rather than
guessed at.

---

**Total deviations:** 2 auto-fixed (1× Rule 3, 1× Rule 2), 1 decision recorded, 1 logged and not
fixed.

## Issues Encountered

**`_isolated_output_dir()` does not isolate the reporter.** `reporter.py` binds `OUTPUT_DIR`
by value at import (`from bobbytailor.config import OUTPUT_DIR`), so patching `config.OUTPUT_DIR`
afterwards has no effect on it — the session-wide `conftest.py` attr-patch is what actually keeps
test runs out of the repo's `output/`. A scratch verification script that imported the reporter
before patching wrote two `Baseline_Proj_*` folders into the real `output/`; **both were deleted**,
and every later check set `config.OUTPUT_DIR` before importing or used a temp directory. The verify
test resolves the run folder from `report["_files"]["run_folder"]` for exactly this reason.

## Known Stubs

None. Every field is populated by real code paths and verified against the real PDFs and real saved
runs. Two things are deliberately not here: DEF-23-07's pipeline call site, and the scraper entry
point (`scrape/scraper.py`), which still calls `generate_report` with no ledger — that is INV-08
step 15, out of this plan's scope, and it renders unchanged by construction.

## Threat Flags

None — no new security-relevant surface. The register's dispositions were carried out:

- **T-23-70 (a new field breaks an existing consumer)** — mitigated and *measured*: the pre-change
  key sets and summary text were captured before any edit and are pinned in the test file.
- **T-23-71 (ledger inflates `takeoff.json`)** — mitigated: rows stay flat, drawing records carry no
  bitmaps and no region lists (23-01/23-03 shape, unchanged here); 3 pages produce 3 rows.
- **T-23-72 (drawing text in an exported workbook)** — accepted, as registered; reasons are truncated
  to 300 characters per cell.
- **T-23-73 (inferred rather than recorded provenance)** — mitigated: the inferring helper is deleted
  and the three real Crow zeros above are the proof it was wrong.
- **T-23-74 (an empty CSV cell read downstream as zero)** — mitigated: asserted end to end through
  `scripts/score_report_dir._num`, not assumed.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1531 passed, 2 deselected** (baseline 1511) |
| Four-set gate `tests/test_four_set_coverage.py` | green (runs inside the suite; no skips reported) |
| Ledger completeness, all four sets | 40/40, 4/4, 7/7, 32/32 — report and `coverage.json` |
| No-ledger report shape | 28 top-level keys, 8 `_files` keys, `summary.txt` byte-identical |
| No-silent-zero over 5 real saved runs | 0 numbers under NOT MEASURED, 0 unflagged blanks |
| Workbook smoke test on a real run | `['Take-Off', 'Coverage', 'About']`; Lintels quantity cell blank |
| Pre-23 run export | `['Take-Off', 'About']` — unchanged |
| `gitnexus detect-changes` | run before each of the three commits |

**Impact analysis was run before editing, per CLAUDE.md.** All three targets came back HIGH or
CRITICAL and are reported here as required:

| Symbol | Risk | Impacted | Processes | Mitigation |
|---|---|---|---|---|
| `generate_report` | **HIGH** | 6 | `run_project_scrape`, `run_analyze_from_manifest`, `run_pdf_analysis` | Both new parameters are keyword-only with `None` defaults, and every new field is absent when they are. The two scraper callers are untouched and their reports are byte-identical, pinned by test. |
| `_write_summary` | **HIGH** | 7 | + `generate_report` | The new renderer returns an EMPTY list for a report with no `coverage` key, so a pre-23 `summary.txt` is byte-identical — asserted against the captured pre-change text. |
| `_write_takeoff_summary_csv` | **CRITICAL** | 11 | + `save_measurements`, `verify_item`, `verify_batch` | `provenance` is appended LAST so no existing column moves. The quantity cell changes ONLY for `quantity is None`, which previously wrote `"—"` — and the offline scorer already mapped both to nothing. The three verify-path callers were audited, and one real defect they carried (deviation 2) was fixed. |

## Requirement status

`V4-MEAS-06` is **advanced, not completed** — left unchecked in `REQUIREMENTS.md`, following 23-02,
23-03 and 23-04.

Its second half — *"zero-geometry sheets emit an explicit coverage flag (blank never reported as
zero)"* — is now closed **end to end**: the records exist (23-03), and every artifact a client reads
states them (this plan). Its first half was delivered by 23-04. What stops the box from being checked
is DEF-23-07: one of 23-04's own record producers has no production caller, so a Chelsea run cannot
yet emit the door-schedule input gap it was built to state. Checking the box while that is true would
claim a client-visible guarantee that a client cannot yet see — the precise failure mode this phase
exists to abolish.

## What this unblocks

Every later plan can now be graded on what a client would actually receive rather than on what the
run held in memory. `coverage.json` is a diffable per-run record, which is what 23-16's
record-correction work needs to assert against, and the COVERAGE section makes a regression in
coverage visible in one file rather than requiring a JSON query.

The standing caution from INV-08 risk 4 applies with full force now that the numbers are printed:
**this plan makes the run honest, not accurate.** A run will now report more blanks and more flags
than before, and that is the intended direction. A green coverage number measures accounting, not
correctness, and must never become the target.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `c8236df` | The run's record of what it did not measure reaches the report |
| 2 | `38b3919` | The summary says what was not measured, and the CSV never spells a blank as a zero |
| 3 | `f4e18aa` | One place decides provenance, and the workbook shows the whole PDF |

## Self-Check: PASSED

- `src/bobbytailor/pipeline/reporter.py` — FOUND
- `src/bobbytailor/pipeline/pdf_analyzer.py` — FOUND
- `src/bobbytailor/web/blueprints/verify.py` — FOUND
- `scripts/export_takeoff_excel.py` — FOUND
- `tests/test_reporter_accuracy.py` — FOUND
- `.planning/phases/23-measurement-engine-completion/deferred-items.md` — FOUND
- commit `c8236df` (Task 1) — FOUND
- commit `38b3919` (Task 2) — FOUND
- commit `f4e18aa` (Task 3) — FOUND
