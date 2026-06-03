---
phase: 20
plan: "00"
subsystem: takeoff-pipeline
tags: [python, extraction, multi-pass, claude, sheet-type-routing]

dependency-graph:
  requires:
    - "16: claude_analyzer.py provides analyze_drawing + _pick_model"
    - "17: scraper.py and pdf_analyzer.py are the eventual callers (wired in 20-06)"
  provides:
    - "sheet_pass_matrix.py: PASS_MATRIX, MODEL_ROUTING, classify_sheet_type_from_text, plan_passes, pick_model_for_pass"
    - "takeoff_pipeline.py: TakeoffPipeline.run_sheet, merge_passes stub"
  affects:
    - "20-03: merge_passes moves from stub to claude_analyzer (canonical)"
    - "20-06: pdf_analyzer.py and scraper.py swap to call TakeoffPipeline"

tech-stack:
  added: []
  patterns:
    - "Sheet-type-driven pass routing via PASS_MATRIX lookup"
    - "Dependency injection for analyzer callable (testability)"
    - "Module-level import for mock-patchable analyze_drawing"

key-files:
  created:
    - sheet_pass_matrix.py
    - takeoff_pipeline.py
    - tests/test_sheet_pass_matrix.py
    - tests/test_takeoff_pipeline.py
  modified: []

decisions:
  - id: D1
    decision: "MODEL_ROUTING uses CLAUDE_MODEL_SCHEDULES config constant, not a hardcoded slug"
    rationale: "Admin can set CLAUDE_MODEL_SCHEDULES=claude-sonnet-4-6 and all Sonnet routing picks it up automatically"
  - id: D2
    decision: "TakeoffPipeline accepts optional analyzer= callable in __init__"
    rationale: "Dependency injection is cleaner than monkeypatching at module level; tests pass mock_analyzer= without patching"
  - id: D3
    decision: "merge_passes defined locally in takeoff_pipeline as stub; canonical version moves to claude_analyzer in 20-03"
    rationale: "Plan 20-00 creates the skeleton; plan 20-03 adds multi-prompt differentiation to analyze_drawing and owns the merge function"
  - id: D4
    decision: "plan_passes returns a copy of the PASS_MATRIX list, not the original"
    rationale: "Prevents callers from accidentally mutating the module-level constant"
  - id: D5
    decision: "classify_sheet_type_from_text scans title block first, then full page; defaults to floor_plan"
    rationale: "floor_plan is the safest default because it runs count+measure — no data is lost for ambiguous sheets"

metrics:
  duration: "~6 minutes"
  completed: "2026-06-03"
  tests_added: 67
  files_created: 4
---

# Phase 20 Plan 00: Takeoff Pipeline Skeleton Summary

**One-liner:** Sheet-type-driven PASS_MATRIX + TakeoffPipeline orchestrator with merge_passes stub; routes title_sheet to zero API calls, Sonnet to complex passes, Haiku to simple ones.

---

## What Was Built

### `sheet_pass_matrix.py`

| Export | Description |
|--------|-------------|
| `PASS_MATRIX` | 8 sheet types → ordered pass lists; `title_sheet → []` |
| `MODEL_ROUTING` | `(sheet_type, pass_type)` → model slug override for Sonnet passes |
| `classify_sheet_type_from_text` | Keyword heuristic; title block first, full page fallback |
| `plan_passes` | Returns PASS_MATRIX entry; unknown types → `["measure"]` fallback |
| `pick_model_for_pass` | MODEL_ROUTING → `_pick_model` fallback → None (use default) |

**PASS_MATRIX at a glance:**

| sheet_type   | Passes               | Model routing           |
|-------------|----------------------|-------------------------|
| floor_plan   | count, measure       | Haiku both              |
| elevation    | count, measure       | count=Haiku, measure=Sonnet |
| civil_site   | measure              | Haiku                   |
| schedule     | schedule             | Sonnet                  |
| detail       | count, measure       | Sonnet both             |
| title_sheet  | *(skip)*             | zero API calls          |
| roof_plan    | count, measure       | count=Haiku, measure=Sonnet |
| mep_plan     | count, measure       | count=Haiku, measure=Sonnet |

### `takeoff_pipeline.py`

- **`TakeoffPipeline.run_sheet`** — classify → plan_passes → pass loop → merge → attach metadata
- **`merge_passes`** (stub) — base on measure_result, deduplicate count-pass components, upgrade null quantities on high-confidence count hits, apply schedule_result
- Returns `{"_skipped": True, ...}` sentinel for title_sheet with zero `analyze_drawing` calls

---

## Must-Haves Verified

- [x] Pass routing uses `sheet_type + discipline`, NOT project name or `^[AS]` regex
- [x] `title_sheet` pages skip all Claude passes (zero API cost)
- [x] `takeoff_pipeline.py` is the single orchestrator for multi-pass extraction
- [x] No references to "Crow" or "Bob" in either module
- [x] 67 unit tests pass without `ANTHROPIC_API_KEY`

---

## Deviations from Plan

None — plan executed exactly as written.

---

## What's NOT Included (future plans)

| Feature | Plan |
|---------|------|
| `analyze_drawing` gains `pass_type` + `model_override` kwargs | 20-03 |
| `merge_passes` moved to `claude_analyzer` (canonical) | 20-03 |
| `pdf_analyzer.py` calls `TakeoffPipeline` | 20-06 |
| `scraper.py` calls `TakeoffPipeline` | 20-06 |

---

## Commits

| Hash    | Message |
|---------|---------|
| cbd20c9 | feat(20-00): add sheet_pass_matrix — PASS_MATRIX, MODEL_ROUTING, classify/plan/pick helpers |
| d1fd9df | feat(20-00): add takeoff_pipeline — TakeoffPipeline class + merge_passes stub |
