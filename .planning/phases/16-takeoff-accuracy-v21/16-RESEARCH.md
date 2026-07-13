# Phase 16: Takeoff Accuracy (Masterv2 v2.1) — Research

**Date:** 2026-05-26  
**Status:** Ready for execution  
**Depends on:** Phases 1–3 (calculator/reporter), Phase 5 (preview APIs — extended in 16-05)  
**Source:** `Masterv2.md` Addendum v2.1 (Appendix C), `.planning/MASTERv2-GAP-ANALYSIS.md`

## Problem

The pipeline produces **per-sheet formula rows** but human/StackCT takeoff expects:

1. **Consolidated** trade-item totals across the project
2. **No false quantities** from spec/reference tables or survey elevations
3. **Linked detail** when drawings cross-reference other sheets
4. **Civil/site** line items (pipe LF, catch basins, striping, etc.)

## Architecture target (from Masterv2 §C.9)

```
Claude (revised prompt)
  → measurements, components, rooms, schedules (typed), cross_references,
    pipe_runs, civil_structures
  → scraper: cross-ref resolution pass
  → calculator: table_purpose guards + civil tables + noise filters
  → resolve_spec_lookups (calculator)
  → aggregator.aggregate_takeoff
  → reporter: takeoff_summary.csv + spec_tables.json + existing outputs
```

## Key files

| File | Change |
|------|--------|
| `claude_analyzer.py` | Replace `EXTRACTION_PROMPT` (§C.8); parse new JSON keys |
| `calculator.py` | `table_purpose` guard; civil tables; `_parse_numeric` elevation/slope rejection; `resolve_spec_lookups` |
| `scraper.py` | Collect cross-refs; `_find_detail_in_extraction`; resolution after all pages |
| `aggregator.py` | **New** — `normalize_item_name`, `aggregate_takeoff` |
| `reporter.py` | `takeoff_summary`, `specification_tables`, CSV/TXT writers |
| `tests/` | Unit tests for dedupe, aggregation, numeric filters (no live API) |

## Risk notes

- **Prompt size:** Full §C.8 prompt is long — monitor token usage; keep one prompt constant, no duplication.
- **Cross-ref resolution:** Only resolves sheets **in the same run** — document `target_sheet_not_found` in report JSON.
- **ITEM_NAME_MAP:** Client-specific — start with Masterv2 list; make extensible via JSON config in v2 if needed.
- **Backward compat:** Keep `calculations.csv` as audit trail; add `takeoff_summary.csv` as primary client-facing export.

## GitNexus

Before editing: `gitnexus_impact` on `analyze_drawing`, `apply_estimation_tables`, `generate_report`, `run_project_scrape`.

## Requirements (Phase 16)

| ID | Summary |
|----|---------|
| ACCURACY-01 | Extraction prompt v2.1 with table_purpose, cross_references, pipe_runs, civil_structures |
| ACCURACY-02 | Calculator skips specification_reference and general_notes schedules |
| ACCURACY-03 | Spec tables stored in report as reference library (not calculated) |
| ACCURACY-04 | Cross-reference resolution pass links refs to in-run sheet data |
| ACCURACY-05 | aggregator.py produces consolidated takeoff_summary |
| ACCURACY-06 | takeoff_summary.csv matches StackCT column format (item, quantity, unit) |
| ACCURACY-07 | Civil/site estimation tables (storm_pipe, catch_basin, striping, etc.) |
| ACCURACY-08 | GL/INV/elevation values rejected from measurement math |
| ACCURACY-09 | Approximate (±) flag preserved in calculations output |
| ACCURACY-10 | Pipe slope % not treated as quantity |
| ACCURACY-11 | resolve_spec_lookups enriches pipe-related rows where tables exist |
| ACCURACY-12 | Report preview exposes Summary tab data from takeoff_summary (Phase 15 workspace or fallback) |

## Human verification

Use civil drawing sample (if available in repo fixtures) or re-run known project:

- [ ] `specification_reference` tables appear in JSON, zero rows in calculations from those tables
- [ ] `takeoff_summary.csv` has one row per trade item with summed qty
- [ ] No row with `formula` driven by GL= or INV= values
- [ ] cross_references[] in takeoff.json with resolution_status when target missing
