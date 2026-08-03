---
phase: 23-measurement-engine-completion
plan: 01
subsystem: pipeline/coverage
tags: [coverage-ledger, skip-veto, provenance, classifier, SP-8, four-set-gate]
status: complete
requires: []
provides:
  - pipeline.coverage.CoverageLedger / SheetCoverage / DrawingCoverage / ItemCoverage
  - pipeline.coverage sheet dispositions + ITEM_* status vocabulary
  - pipeline.provenance.provenance_of_row
  - sheet_pass_matrix.classify_sheet_type_verbose
  - takeoff_pipeline.page_measurable_signal
  - TakeoffPipeline.run_sheet(coverage=...) + the skip veto
  - TakeoffPipeline.run_project(coverage=...) + self.coverage_ledger
  - scripts/coverage_probe.py (the ledger's oracle)
  - tests/test_four_set_coverage.py (the D-05 gate)
affects:
  - pdf_analyzer.run_pdf_analysis
  - takeoff_pipeline.run_sheet / run_project / _route_deterministic
  - sheet_pass_matrix.classify_sheet_type_from_text (behaviour unchanged)
tech-stack:
  added: []
  patterns:
    - "register-before-route: the ledger row exists before any decision can discard the page"
    - "evidence outranks a keyword: a position/shape signal vetoes a bag-of-words verdict"
    - "None is not zero: unmeasured quantities are Optional[float] = None"
    - "one definition for the oracle and the thing it audits (page_measurable_signal)"
key-files:
  created:
    - src/bobbytailor/pipeline/coverage.py
    - src/bobbytailor/pipeline/provenance.py
    - scripts/coverage_probe.py
    - tests/test_coverage_ledger.py
    - tests/test_four_set_coverage.py
  modified:
    - src/bobbytailor/pipeline/sheet_pass_matrix.py
    - src/bobbytailor/pipeline/pdf_analyzer.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - tests/test_sheet_pass_matrix.py
    - tests/test_takeoff_pipeline.py
decisions:
  - "Full-page text was NOT wired into the routing classifier: measured, it delivers zero skip improvement and costs Chelsea 26 -> 17 deterministic-eligible pages. Recorded on SheetCoverage.sheet_type_full_text for plan 23-06 instead."
  - "measurable_signal counts what is MEASURABLE (titles that anchor a printed scale), not title-shaped strings, so an index page does not read as a 11-drawing silent loss."
  - "_route_deterministic gained deterministic_only=True under the veto: the raster branch is the ensemble vision path and would be unbudgeted spend."
  - "The deciding keyword is chosen deterministically (earliest match) because a frozenset iterates in hash order."
metrics:
  duration: ~3h
  completed: 2026-08-03
  tasks: 4
  commits: 5
  tests_added: 96
  suite: "1261 passed, 2 deselected (baseline 1132)"
---

# Phase 23 Plan 01: Coverage Ledger + Skip Veto Summary

Every page of a plans PDF now has exactly one ledger row stating what happened to it, and a page
carrying scaled plan geometry is measured deterministically even when a keyword called it a title
sheet — Moxy goes from 22 of 40 pages reaching the report to 38, at zero API cost.

## What shipped

**The ledger (`pipeline/coverage.py`).** `SheetCoverage` is one row per **page of the source PDF**,
not per processed sheet — the entire defect was that 18 of Moxy's 40 pages never became a processed
sheet and so left no row, no flag and no count in any artifact. Seven sheet dispositions, the
five-value item vocabulary lifted verbatim from `export_takeoff_excel.py` so client-facing strings
are unchanged, and `summary()` / `warnings()` / `assert_accounted()` / `to_dict()`.
`ItemCoverage.quantity` and `DrawingCoverage.area_sf` are `Optional[float]` defaulting to `None`.
Pure data — no I/O, no `fitz` — so the completeness invariant is provable in 40 ms with no fixture.

**Provenance (`pipeline/provenance.py`).** `provenance_of_row` reads the recorded status first and
treats `quantity is None` — never a comparison against zero — as NOT MEASURED. The old exporter
logic said `float(qty or 0) <= 0 -> NOT MEASURED`, which made a building with genuinely no CMU
indistinguishable from one whose CMU was never measured.

**The verbose classifier.** `classify_sheet_type_verbose` returns
`(sheet_type, source, keyword, context)`. `classify_sheet_type_from_text` is now a projection of its
first element, with the signature and every outcome unchanged. On Moxy page 23 it returns
`('title_sheet', 'title_block', 'COVER', 'ABEL ON THE LIGHT SWITCH COVER PLATE INDICATING MASTER')`
— character-for-character the reason INV-08 §1.2 had to reverse-engineer by hand.

**Registration and the veto.** `run_pdf_analysis` builds the ledger and registers every page
*before* any routing or page-selection filtering, so completeness is an invariant of construction
rather than something each code path must remember. `run_sheet` takes a keyword-only
`coverage=None`, and before returning the skip sentinel it asks the drawing: a plan title with a
printed scale beneath it, or a non-title-block viewport with a solved scale, overrules the keyword.
When the veto does not fire the skip is still **recorded** — keyword, context, measurable signal,
and `SKIPPED_CLASSIFIER` or `NOT_APPLICABLE`.

**The oracle and the gate.** `scripts/coverage_probe.py` computes what the ledger must contain
without running the pipeline; `tests/test_four_set_coverage.py` is the D-05 gate as a single
assertion over all four plan sets at once.

## Four-plan-set results (measured, zero API)

`pages skipped entirely`, from a real `scripts/coverage_probe.py` run — not from the plan text:

| Set | Pages | Before | After | Recovered | Silent loss | Reaches report |
|---|---|---|---|---|---|---|
| Moxy | 40 | 18 | **2** | 16 | `[]` | 22 → **38** |
| Crow | 4 | 0 | **0** | 0 | `[]` | 4 → 4 |
| Bob's | 7 | 1 | **1** | 0 | `[]` | 6 → 6 |
| Chelsea | 32 | 0 | **0** | 0 | `[]` | 32 → 32 |

Moxy's remaining two skips are pages 0 and 1 — the real cover, and the LIGHTING COVER SHEET whose
index lists 11 drawing names and carries **zero** printed scales. Bob's page 0 stays skipped and is
labelled `not_applicable`. Crow is untouched, which is the proof the veto is not a blanket "measure
everything".

The probe reproduces INV-08 §1.1 exactly on today's HEAD: Moxy's type histogram
`{'title_sheet': 18, 'floor_plan': 13, 'elevation': 9}`, the no-deterministic-geometry list
`[3,4,5,15,16,17,18,19,20]`, Crow's per-page scale counts 5/4/13/2, and Bob's page 6 reading
`floor_plan` on the title block but `detail` on full text.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1261 passed, 2 deselected** (baseline 1132) |
| Classifier invariance, all four sets | 83 pages × 3 text-source combos = **249 comparisons, 0 differing** |
| Four-set gate `tests/test_four_set_coverage.py` | 9 passed (2 min 20 s) |
| Gate fails when it should | Simulated Chelsea 0→10 + Moxy silent loss → fires, names both |
| Ledger invariant on real PDFs | rows == `pages_in_source` == `fitz.page_count` on all four |
| Zero-API veto | stub analyzer raises on any call; veto tests pass |
| Python 3.9 | `ast.parse(feature_version=(3,9))` clean on every changed file |
| `gitnexus detect_changes` / re-index | run; 9,436 nodes / 15,958 edges |

Impact analysis was run before editing, per CLAUDE.md: `classify_sheet_type_from_text` came back
**CRITICAL** (10 impacted symbols, 3 direct callers) and `run_sheet` **HIGH** (4 direct callers,
3 of them in `scrape/scraper.py`). Both were mitigated exactly as the plan specified — an unchanged
signature with byte-identical outcomes for the classifier, and keyword-only `None`-default
parameters for `run_sheet` — and both mitigations are pinned by tests.

## Deviations from Plan

### 1. [Rule 1 — prevented regression] Full-page text NOT wired into the routing classifier

- **Found during:** Task 3, before writing any code.
- **Plan asked for:** replacing `classify_sheet_type_from_text(title_block_text)` in
  `run_pdf_analysis` with `classify_sheet_type_verbose(title_block_text, doc[i].get_text())`, to
  "restore the classifier's documented two-source fallback".
- **Measured first, on all four sets:**

  | Set | Skips today | Skips +fulltext | Det-eligible today | Det-eligible +fulltext |
  |---|---|---|---|---|
  | Moxy | 18 | 18 | 13 | 13 |
  | Crow | 0 | 0 | 1 | 1 |
  | Bob's | 1 | 1 | 5 | **4** |
  | Chelsea | 0 | 2 | 26 | **17** |

- **Why it was not applied:** the change delivers **zero** skip improvement (Moxy 18 → 18 — the
  entire Moxy recovery comes from the veto) while costing 10 deterministic-eligible pages across
  Bob's and Chelsea. That is the documented fixture-blindness trap in a new disguise, and 23-CONTEXT
  is explicit that improving one fixture while regressing another is rejected. The plan's own Task 2
  also states that classification repair belongs to 23-06, gated on the four-set check.
- **What was done instead:** the full-text verdict is **recorded** on the new
  `SheetCoverage.sheet_type_full_text` field, so 23-06 has the evidence it needs to make the
  classification repair with the gate green. Routing input is unchanged.
- **Commit:** `c3bac3f`

### 2. [Rule 2 — missing critical functionality] The veto must not be able to buy a vision call

- **Found during:** Task 3, building the synthetic fixture.
- **Issue:** `_route_deterministic` chooses `raster = raster_force or not is_vector_sheet(page)`,
  and the raster branch is `_run_sheet_raster` — the **ensemble vision path**. On a scanned plan
  set the veto would have recovered keyword-discarded sheets straight onto paid vision calls,
  precisely what INV-08 risk 1 forbids.
- **Fix:** `_route_deterministic` gained `deterministic_only: bool = False`; the veto passes `True`,
  which refuses the raster branch and returns `None`. A raster page has no deterministic geometry
  to recover, so the honest outcome is the recorded skip.
- **Pinned by:** `test_a_raster_page_is_never_recovered_onto_the_vision_ensemble` and
  `test_overruled_branch_routes_deterministically`, both with a stub analyzer that raises on any
  call.
- **Commit:** `c3bac3f`

### 3. [Rule 1 — bug] `classify_sheet_type_verbose` raised on a non-string text source

- **Found during:** Task 3, full-suite run — `tests/test_pipeline_parity.py` mocks `fitz`, so
  `doc[i].get_text()` returned a `MagicMock` and `.upper()` fed a non-string into `re.search`.
- **Why it matters beyond the test:** page text comes from an untrusted PDF via a parser entitled to
  return something unexpected. A classifier that raises turns one odd page into a dead run — the
  opposite of this plan's contract.
- **Fix:** non-string sources are skipped as unusable evidence, making the classifier total.
  `run_pdf_analysis`'s classification block also degrades per-page instead of aborting.
- **Commit:** `c3bac3f`

### 4. [Rule 2] `measurable_signal` counts what is measurable, not what is title-shaped

- **Issue:** INV-08 §3.2 shows `measurable_signal["plan_titles"]` as a raw title count. Moxy page 1
  is the LIGHTING COVER SHEET: its sheet index lists 11 strings matching the plan-title pattern and
  it carries **zero** printed scales. A raw count makes `is_silent_loss` fire, so the ledger would
  report a lost 11-drawing sheet on an index page — a false alarm on every drawing set with an
  index, and it would have failed the plan's own `silent_loss_pages == []` criterion.
- **Fix:** `plan_titles` counts titles that anchor a printed scale, and `viewports` counts
  non-title-block viewports with a solved scale. A drawing with no scale of its own is not
  measurable; measuring it at a borrowed scale is a squared error.
- **Commit:** `c3bac3f`

### 5. [Minor] Reconciling two conflicting acceptance statements

Task 3's action text and Task 4's acceptance both require an all-zero-signal page to be
`NOT_APPLICABLE` (Bob's page 0), while Task 3's negative-test criterion asks for
`SKIPPED_CLASSIFIER` on a page with no title and no scale. Both behaviours are tested: all-zero →
`NOT_APPLICABLE`; signal-present-but-nothing-measurable (Chelsea page 0's real shape) →
`SKIPPED_CLASSIFIER` with a non-empty keyword and `is_silent_loss` True.

### 6. [Minor] `assert_accounted()` returns `List[int]`

INV-08 §3.2's stub annotates `List[str]`; the plan's prose says "the list of source page indices".
Indices are more useful to both the test and the log, so it returns `List[int]`.

## Known Stubs

None. `ItemCoverage` rows are not yet populated by the aggregator and `DrawingCoverage` rows are not
yet populated by `_measure_room_fills` — both are explicitly plan 23-03's scope, and the summary
counters return honest zeros rather than placeholder values in the meantime.

The four new report fields (`coverage`, `coverage_ledger`, `item_coverage`, `coverage_warnings`) are
**not** added here; `run_pdf_analysis` exposes the finished ledger via `pipeline.coverage_ledger`
and logs `assert_accounted()` + `warnings()`. Wiring it into `generate_report` is 23-03's task, per
the plan's own artifact index.

## Threat Flags

None. The plan's five registered threats are all mitigated: per-page signal computation is bounded
and degrades to `ERRORED` (T-23-01); `DrawingCoverage` stays flat and the ledger is bounded at
`page_count` (T-23-02); `classifier_context` is capped at ~25 characters either side (T-23-03); the
veto is deterministic-only and pinned by a raising-stub test (T-23-04); every skip records keyword,
context and signal, and `assert_accounted()` proves no page is missing (T-23-05).

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `526b96c` | Coverage ledger and provenance data layer |
| 2 | `c4b9fff` | `classify_sheet_type_verbose` — the classifier states its reason |
| 3 | `c3bac3f` | Register every source page, and let geometry veto the classifier |
| 4 | `42efddf` | `coverage_probe.py` oracle and the four-plan-set regression gate |

## What this unblocks

Every later plan's "we could not measure this" branch now has a place to terminate. 23-03 wires the
ledger into `generate_report`; 23-06 has `sheet_type_full_text` plus a gate that will fail loudly if
its classification repair regresses a fixture; every wave can use `scripts/coverage_probe.py` as its
free progress signal — while remembering INV-08 risk 4, that a green coverage number measures
accounting, not correctness, and must never become the target.

## Self-Check: PASSED

All five created artifacts exist on disk; all four task commits exist in git history.
