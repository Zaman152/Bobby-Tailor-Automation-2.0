---
phase: 20
plan: "03"
subsystem: extraction-prompts
tags: [claude, prompts, multi-pass, count, schedule, merge]

dependency_graph:
  requires: ["20-00", "20-01"]
  provides:
    - COUNT_PROMPT: generalized discrete-symbol counting for any EA item class
    - SCHEDULE_PROMPT: focused table/schedule extraction for any schedule type
    - analyze_drawing pass_type + model_override kwargs
    - merge_passes canonical implementation in claude_analyzer
  affects: ["20-04", "20-05", "20-06"]

tech_stack:
  added: []
  patterns:
    - Multi-pass extraction with per-pass prompt selection
    - Deferred lazy import to break circular dependency (sheet_pass_matrix ↔ claude_analyzer)
    - Canonical function in shared module re-exported from orchestrator for backward compat

key_files:
  created: []
  modified:
    - claude_analyzer.py
    - takeoff_pipeline.py

decisions:
  - "COUNT_PROMPT returns has_schedules bool so TakeoffPipeline can gate schedule pass on whether it's needed"
  - "analyze_drawing default pass_type='measure' preserves all existing single-pass caller behavior"
  - "_pick_model deferred MODEL_ROUTING import avoids circular dependency (sheet_pass_matrix imports _pick_model at module level)"
  - "merge_passes canonical lives in claude_analyzer; takeoff_pipeline re-exports it so external callers don't break"
  - "merge_passes uses strip().lower() for dedup keys — handles trailing whitespace variants from Claude output"
  - "_count_pass_upgrade flag set on upgraded components for traceability"

metrics:
  duration: "3m 31s"
  completed: "2026-06-03"
---

# Phase 20 Plan 03: Generalized Prompts + Multi-Pass Infrastructure Summary

**One-liner:** COUNT_PROMPT + SCHEDULE_PROMPT for any EA symbol/table class, plus `analyze_drawing(pass_type, model_override)` + canonical `merge_passes` wired into TakeoffPipeline.

---

## What Was Built

### Task 1 — COUNT_PROMPT + SCHEDULE_PROMPT (`claude_analyzer.py`)

**`COUNT_PROMPT`** — discipline-agnostic discrete-item counting:
- Counts ANY physical unit: bollards, columns, catch basins, manholes, drains, luminaires, fixtures, trees, fire hydrants, equipment tags, doors, windows, ladders, lifts, VAV boxes, RTUs, etc.
- 8 universal counting rules including the critical DIMENSION LINE RULE (numbers on dimension lines are dimensions, not counts)
- Grid count method (`method="grid"`) with axis description for regular grids
- `quantity=null` + `confidence=low` rule — never fabricates a count
- Returns `components[]`, `has_schedules` bool, `sheet_type` guess
- Zero project-specific examples (no "28 bollards", no "132 columns", no "886 LF")

**`SCHEDULE_PROMPT`** — any tabular takeoff schedule:
- Door, window, equipment, panel, pipe sizing, plumbing fixture schedules
- Reads QTY column exactly as printed; `use_for_takeoff=true` only when QTY column exists
- `table_purpose` classification: `takeoff_schedule` / `specification_reference` / `general_notes`
- Never invents rows; stops at last visible row; no off-page extrapolation

### Task 2 — Multi-Pass Infrastructure (`claude_analyzer.py` + `takeoff_pipeline.py`)

**`analyze_drawing(screenshot_path, sheet_name, pass_type="measure", model_override=None)`:**
- Selects `COUNT_PROMPT` / `SCHEDULE_PROMPT` / `EXTRACTION_PROMPT` based on `pass_type`
- `model_override` bypasses `_pick_model` entirely when set
- Backward compatible: `pass_type="measure"` default preserves all existing caller behavior
- `_pass_type` added to every result dict for traceability

**`_pick_model(sheet_name, pass_type="measure", sheet_type=None)` — updated:**
- When `sheet_type` is provided, consults `MODEL_ROUTING` from `sheet_pass_matrix` first
- Deferred lazy import prevents circular dependency (sheet_pass_matrix imports _pick_model at module level)
- Falls back to name-based heuristic (MEP sheet codes + schedule keywords)

**`merge_passes(count_result, measure_result, schedule_result=None)` — canonical:**
- Measure-pass is the base (SF/LF data, pipe_runs, rooms, measurements all preserved)
- Count-pass components merged in; high-confidence EA counts upgrade measure-pass nulls
- `_count_pass_upgrade=True` flag set on upgraded components for traceability
- Dedup by `name.strip().lower()` — handles whitespace variants in Claude output
- Schedule-pass replaces `schedules[]` only when non-empty (guards against empty schedule pass)

**`takeoff_pipeline.TakeoffPipeline._run_pass` — wired:**
- Now passes `pass_type=pass_type` and `model_override=model_override` to `analyze_drawing`
- Removes the 20-03 TODO comment — fully implemented

**`takeoff_pipeline.merge_passes` — stub removed:**
- Re-exported from `claude_analyzer` — single source of truth
- External callers importing from `takeoff_pipeline` continue to work unchanged

---

## Verification

```
$ python3 -c "from claude_analyzer import COUNT_PROMPT; assert 'dimension line' in COUNT_PROMPT.lower(); assert 'crow' not in COUNT_PROMPT.lower()"
$ python3 -m pytest tests/test_extraction_prompt.py -q
..  2 passed in 0.38s
```

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Next Phase Readiness

Plan 20-04 (EXTRACTION_PROMPT linear runs extension: gas pipe, lintels, `lintel_runs[]`) can proceed.  
`analyze_drawing` now accepts `pass_type` so 20-06 (pdf_analyzer + scraper TakeoffPipeline migration) is unblocked.

**No blockers.**
