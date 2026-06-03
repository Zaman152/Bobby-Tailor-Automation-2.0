---
phase: 20-takeoff-measurement-precision
plan: "04"
subsystem: calculator
tags: [content-first, project-type-profiles, material-note-map, gas-pipe, estimation-tables]

dependency-graph:
  requires: ["20-00", "20-01", "20-02", "20-03"]
  provides:
    - PROJECT_TYPE_PROFILES (8 building types)
    - MATERIAL_NOTE_MAP (content-first room note parsing)
    - content-first _calculate_from_room with priority chain
    - _detect_project_type heuristic
    - gas_pipe / lintel / sealed_concrete / cmu_wall / eifs / canopy / cmu_paint item types
    - Gas Piping + Sealed Concrete aggregator name mappings
  affects: ["20-05", "20-06", "20-07"]

tech-stack:
  added: []
  patterns:
    - content-first override (notes > profile defaults > fallback)
    - per-category priority chain (floor / ceiling / wall handled independently)
    - regex-based note-to-item-type mapping (MATERIAL_NOTE_MAP)
    - material-based pipe type detection (_detect_pipe_item_type)

key-files:
  created: []
  modified:
    - calculator.py
    - aggregator.py
    - tests/test_takeoff_generalization.py

decisions:
  - "Content note matches are NOT filtered by profile skip_items — explicit drawing content always overrides profile (VCT note on industrial project → flooring, not sealed_concrete)"
  - "skip_items in PROJECT_TYPE_PROFILES only prevent profile *defaults* from being applied when content is silent"
  - "Floor / ceiling / wall items handled as independent categories in _calculate_from_room; each category has its own content → profile → fallback chain"
  - "auto profile has empty default lists → universal fallback (flooring + ceiling_grid + paint + drywall) preserves prior behavior for projects without explicit project_type"
  - "Gas pipe detected by material keyword (black steel, gas, csst) in _detect_pipe_item_type; falls back to storm_pipe"
  - "_room_note_text() collects notes, material_notes, materials, ceiling, finish, spec fields for unified pattern matching"

metrics:
  duration: "~18 min"
  completed: "2026-06-03"
  tasks_completed: 2/2
  tests_before: "23 passed, 3 xfailed"
  tests_after: "27 passed, 1 xfailed"
  new_tests: 2
  xfail_removed: 2
---

# Phase 20 Plan 04: Content-First Room Mapping + Project Type Profiles — Summary

**One-liner:** Content-first `_calculate_from_room` with `PROJECT_TYPE_PROFILES` (8 types), `MATERIAL_NOTE_MAP` regex matching, and gas-pipe detection eliminates RC-2 Flooring-for-Sealed-Concrete and RC-4 Storm-Pipe-for-Gas mismappings.

---

## Objective

Fix RC-2 (`_calculate_from_room` unconditionally producing flooring for all area types) and RC-4 (`_calculate_from_pipe_runs` hardcoding `storm_pipe` for all pipe runs) by implementing a content-first mapping chain and expanded project-type profiles.

---

## Tasks Completed

### Task 1: ESTIMATION_TABLES + PROJECT_TYPE_PROFILES + MATERIAL_NOTE_MAP

**Files:** `calculator.py`

Added 8 new `ESTIMATION_TABLES` entries:

| Key | Unit | Description |
|-----|------|-------------|
| `sealed_concrete` | sq_ft | Sealed/polished concrete floor |
| `cmu_wall` | sq_ft | CMU masonry wall SF |
| `internal_tilt_up_wall` | sq_ft | Interior tilt-up panel SF |
| `canopy` | sq_ft | Metal/shade canopy SF |
| `eifs` | sq_ft | Exterior Insulation and Finish System (5% waste) |
| `cmu_paint` | gallons | CMU block paint (2 coats at 200 sf/gal) |
| `gas_pipe` | lf | Gas piping LF (5% waste) |
| `lintel` | lf | Steel lintel LF (5% waste) |

Added `PROJECT_TYPE_PROFILES` for 8 building types:

| Profile | Default Floor | Default Ceiling | Default Wall | Skip Items |
|---------|---------------|-----------------|--------------|------------|
| `industrial` | sealed_concrete | exposed_structure | — | flooring, ceiling_grid, drywall |
| `retail` | flooring | ceiling_grid | paint, drywall | sealed_concrete |
| `office` | flooring | ceiling_grid | paint, drywall | sealed_concrete, tilt_up_wall |
| `civil` | — | — | — | flooring, ceiling_grid, drywall |
| `residential` | flooring | — | paint, drywall, insulation | exposed_structure, tilt_up_wall |
| `institutional` | flooring | ceiling_grid | paint, drywall | sealed_concrete |
| `mixed_use` | flooring | — | paint, drywall | — |
| `auto` | — | — | — | — (fallback to universal) |

Added `MATERIAL_NOTE_MAP` regex list for content-first matching:
- `sealed\s*concrete|polished\s*concrete|sog\b` → `sealed_concrete`
- `\bvct\b|lvt|carpet|hardwood|vinyl\s*floor|floor\s*tile` → `flooring`
- `acoustic\s*tile|ceiling\s*tile|\bact\b|t.?bar\s*ceil` → `ceiling_grid`
- `exposed\s*structure|exposed\s*deck|bar\s*joist` → `exposed_structure`
- `tilt[- ]?up\s*panel?|precast\s*panel` → `tilt_up_wall`
- `\bcmu\b|block\s*wall|concrete\s*masonry\s*unit` → `cmu_wall`
- `\beifs\b|exterior\s*insulation|dryvit` → `eifs`
- `\bcanopy\b|metal\s*canopy|entrance\s*canopy` → `canopy`
- `cmu\s*paint|block\s*paint|masonry\s*paint` → `cmu_paint`

**Verification:** `python3 -c "from calculator import PROJECT_TYPE_PROFILES; assert set(PROJECT_TYPE_PROFILES) >= {'industrial','retail','office','civil','residential','institutional','mixed_use','auto'}"` → PASS

---

### Task 2: Content-First `_calculate_from_room` + `_detect_project_type`

**Files:** `calculator.py`, `aggregator.py`, `tests/test_takeoff_generalization.py`

**Rewrote `_calculate_from_room(room, sheet_name, project_type="auto")`:**

Four-step priority chain, applied independently per category (floor / ceiling / wall):

1. Parse `_room_note_text(room)` through `MATERIAL_NOTE_MAP`  
2. Content matches → produce matched items (skip_items NOT applied to content — explicit drawing notes always win)  
3. No content match → use `profile.default_{floor,ceiling,wall}_items` (skip_items applied)  
4. Profile defaults empty (auto) → universal fallback (flooring + ceiling_grid + paint + drywall)

Added `_room_note_text(room)` helper that collects: `notes`, `material_notes`, `materials`, `ceiling`, `finish`, `spec` fields.

**Added `_detect_project_type(all_pages)`:**

Keyword-scoring heuristic across sheet titles and notes. Returns `"auto"` when no category scores, `"mixed_use"` when multiple types tie.

**Added `_detect_pipe_item_type(run)`:**

Classifies pipe runs from `material` + `raw_text`:
- `gas|black steel|csst|yellow pe|gas line` → `gas_pipe`
- `trench drain|channel drain` → `trench_drain`
- Default → `storm_pipe`

**Fixed `_calculate_from_pipe_runs`:** Uses `_detect_pipe_item_type` instead of hardcoding `storm_pipe`.

**Extended `_apply_formula`:**
- Added `gas_pipe`, `lintel` to LF group
- Added `sealed_concrete`, `cmu_wall`, `internal_tilt_up_wall`, `canopy`, `eifs` to SF area group
- Added `cmu_paint` to gallon formula (same as paint)

**`aggregator.py` — ITEM_NAME_MAP additions:**
- `gas.*pip|black\s*steel.*pip` → "Gas Piping" (LF)
- `sealed.*concrete|polished.*concrete` → "Sealed Concrete" (SF)

**Test file changes:**
- Removed `@pytest.mark.xfail` from `test_floor_plan_industrial_no_flooring` (RC-2 fixed)
- Removed `@pytest.mark.xfail` from `test_mep_roof_gas_produces_gas_piping` (RC-4 fixed)
- Added `test_content_first_sealed_concrete_overrides_default` — verifies note parsing produces `sealed_concrete`, not `flooring`
- Added `test_content_first_vct_on_industrial_profile` — verifies VCT note produces `flooring` even with `project_type="industrial"` (content beats profile skip_items)

**Verification:** `pytest tests/test_takeoff_generalization.py tests/test_calculator_accuracy.py -q` → **27 passed, 1 xfailed** (door HM/WD deferred to 20-05)

---

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Content overrides skip_items | Plan must_have: "VCT produce flooring even on industrial profile when explicitly tagged" — skip_items only gate profile defaults |
| Floor / ceiling / wall as independent priority chains | Prevents one matched content type from suppressing unrelated categories (e.g. sealed_concrete floor + paint walls both needed) |
| `_room_note_text` collects `material_notes` and `ceiling` fields | Generalization fixtures use `material_notes` not `notes`; `ceiling` field carries exposed_structure hints |
| `auto` profile has empty lists → universal fallback | Preserves prior behavior (flooring+ceiling_grid+paint+drywall) for callers that don't pass project_type |
| Gas pipe detection from material keyword, not hardcoded material list | Handles "black steel", "csst", "yellow PE" variants without exhaustive enumeration |

---

## Deviations from Plan

None — plan executed exactly as written. The `skip_items`-vs-content decision is a clarification of the plan's intent, resolved by the must_have truths in the frontmatter.

---

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | `a5bce57` | feat(20-04): add PROJECT_TYPE_PROFILES, MATERIAL_NOTE_MAP, 8 new ESTIMATION_TABLES entries |
| Task 2 | `d611a5a` | feat(20-04): content-first _calculate_from_room + _detect_project_type + gas pipe fix |

---

## Next Phase Readiness

Plan 20-05 can proceed. Key context for next plan:
- `apply_estimation_tables` now accepts `project_type="auto"` — callers can pass detected type
- `_detect_project_type(all_pages)` is available in `calculator.py` for pipeline integration
- `MATERIAL_NOTE_MAP` is extensible — add new patterns without changing any function logic
- Remaining xfail: `test_schedule_doors_hm_wd_separate` — needs ITEM_NAME_MAP HM/WD extension
