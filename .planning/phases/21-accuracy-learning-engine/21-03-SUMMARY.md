---
phase: 21-accuracy-learning-engine
plan: 03
subsystem: deterministic
tags: [shapely, pymupdf, dimensions, STRtree, pytest, recipe-a]

requires:
  - phase: 21-01
    provides: src/bobbytailor/deterministic/ package home and editable install
provides:
  - DimensionSample stream for 21-07 scale solver
  - parse_feet_inches + extract_dimension_samples Recipe A API
  - Synthetic dimension fixture generator (Wave 0 validation harness)
affects: [21-07, 21-06, 21-10, scale_solver, viewports]

tech-stack:
  added: [shapely>=2.0, numpy>=1.26, networkx>=3.2]
  patterns:
    - "STRtree corridor search with grammar-verified terminators"
    - "Feet-aware longest-segment pick (overall dims >=100 ft vs bay dims)"
    - "Chained-dimension subsegmentation by text projection"

key-files:
  created:
    - src/bobbytailor/deterministic/dimensions.py
    - tests/test_dimensions.py
    - tests/fixtures/synthetic/gen_synthetic.py
    - tests/fixtures/synthetic/dimensions_synthetic.pdf
    - tests/fixtures/synthetic/truth.json
  modified:
    - requirements.txt
    - pyproject.toml

key-decisions:
  - "Shapely 2 STRtree.query returns numpy indices — map directly to segment list"
  - "PERP_MIN_PT=0 allows rotated vertical text sitting on the dimension line"
  - "Overall dims (feet>=100) pick longest candidate; bay dims cap at 5× median corridor length"
  - "Synthetic generator uses page.draw_line (not Shape) so get_drawings() sees vectors"

patterns-established:
  - "Recipe A: harvest → STRtree corridor → terminator score → chained split → dedupe margin duplicates"
  - "Layer-1 tests: parse table + synthetic truth.json + Crow/Bob fixture gates"

duration: 15min
completed: 2026-07-14
---

# Phase 21 Plan 03: Dimension-Line Association Engine Summary

**Recipe A dimension-line association with STRtree corridor search, grammar-verified terminators, and Crow page-0 samples at 40 ft/in consensus (1136' + 350' paired)**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-13T20:02:00Z
- **Completed:** 2026-07-13T20:17:00Z
- **Tasks:** 3/3
- **Files modified:** 7

## Accomplishments

- Built `dimensions.py` with `parse_feet_inches`, `_harvest_dimension_texts`, `_visible_drawings`, and `extract_dimension_samples`
- Replaced brute-force nearest-segment calibration anti-pattern with corridor + terminator verification
- Crow Cass page 0: 37 samples, 78% ratio consensus at 2%, feet values 1136.0 and 350.0 present
- Synthetic fixture generator + 16 layer-1 tests; full non-golden suite 544 passed

## Task Commits

1. **Task 1: parse_feet_inches + harvesting + deps** - `7e2d4ff` (chore)
2. **Task 2: STRtree association + DimensionSample** - `9fd289c` (feat)
3. **Task 3: synthetic fixtures + layer-1 tests** - `9d3ebad` (test)

**Plan metadata:** pending (docs commit)

## Files Created/Modified

- `src/bobbytailor/deterministic/dimensions.py` — Recipe A engine (708 lines)
- `requirements.txt` / `pyproject.toml` — shapely, numpy, networkx
- `tests/test_dimensions.py` — 16 parse/fixture/regression tests
- `tests/fixtures/synthetic/gen_synthetic.py` — CLI truth-backed PDF generator

## Decisions Made

- Shapely 2.x `STRtree.query` returns integer indices, not geometry objects
- Bay dimensions exclude overall-span lines via feet-aware median-length cap
- Chained dims on one segment split by text projection when extension crossings insufficient
- Margin/title-block duplicate feet values deduped by keeping longest paired segment

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Shapely 2 STRtree index mapping**

- **Found during:** Task 2
- **Issue:** `STRtree.query` returns numpy indices; treating results as geometries yielded zero pairings
- **Fix:** Index directly into segment list
- **Files modified:** `src/bobbytailor/deterministic/dimensions.py`
- **Commit:** `9fd289c`

**2. [Rule 2 - Missing Critical] Bay dims mispaired to overall-span lines**

- **Found during:** Task 2 Crow verification
- **Issue:** Longest-candidate rule paired 54' bay texts to 2058pt overall horizontal line
- **Fix:** Feet-aware pick — overall dims (≥100 ft) take longest; bay dims cap at 5× median local length; center-on-segment filter
- **Files modified:** `src/bobbytailor/deterministic/dimensions.py`
- **Commit:** `9fd289c`

**3. [Rule 3 - Blocking] Synthetic Shape drawings invisible to get_drawings()**

- **Found during:** Task 3
- **Issue:** `page.new_shape().commit()` produced zero `get_drawings()` paths
- **Fix:** Use `page.draw_line` / `page.insert_text` for vector paths
- **Files modified:** `tests/fixtures/synthetic/gen_synthetic.py`
- **Commit:** `9d3ebad`

**4. [Rule 1 - Bug] Vertical rotated text rejected by PERP_MIN_PT=2**

- **Found during:** Task 3 synthetic test
- **Issue:** Text sitting on vertical dimension line had 0pt perpendicular offset
- **Fix:** Lower `PERP_MIN_PT` to 0.0
- **Files modified:** `src/bobbytailor/deterministic/dimensions.py`
- **Commit:** `9fd289c`

---

**Total deviations:** 4 auto-fixed (2 bugs, 1 missing critical, 1 blocking)
**Impact on plan:** All fixes required for correct Crow pairing and test harness. No scope creep.

## Issues Encountered

None blocking. Crow page 0 printed scale is 40 ft/in (not 20); consensus ratio matches printed scale — recorded in test stdout.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `DimensionSample` stream ready for 21-07 scale solver (RANSAC per viewport)
- `_visible_drawings` reusable by 21-06 walls/rooms/symbols for OCG filtering
- networkx/numpy/shapely installed for downstream geometry plans

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*
