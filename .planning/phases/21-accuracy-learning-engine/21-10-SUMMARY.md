---
phase: 21-accuracy-learning-engine
plan: 10
subsystem: deterministic-measurement
tags: [shapely, polygonize, pymupdf, walls, rooms, footprint, recipe-b, recipe-c]

# Dependency graph
requires:
  - phase: 21-03
    provides: dimensions.py (_visible_drawings OCG filter, DimensionSample scale ratios)
  - phase: 21-06
    provides: symbols.py _collapse_hatch_fields (Pitfall 2 hatch collapse)
  - phase: 21-07
    provides: viewports/scale_solver (solved fpp, main-plan viewport bbox, door_check slot)
provides:
  - "deterministic/walls.py — Recipe B parallel-pair wall extraction: WallSegment, extract_walls, extract_walls_detailed, wall_lf_by_class, opening_gap_widths"
  - "deterministic/rooms.py — Recipe C room polygonize: RoomPolygon, extract_rooms, building_footprint, rooms_to_legend"
  - "opening_gap_widths door-band cluster feeding scale solver door_check cross-validation"
  - "floorplan_synthetic.pdf fixture + truth.json floorplan key (known LF/areas/footprint)"
affects: [21-11, 21-12, 21-13, fusion, accuracy-gate, reporter]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "NETWORK_PRECISION_GRID: shapely.set_precision on network inputs before unary_union (GEOS float-noding robustness)"
    - "Opening gaps validated by two-face break OR door-leaf corroboration (dash-pattern immunity)"
    - "WallSegment/RoomPolygon store point-space measures only; LF/SF conversion is pure fpp math (RawGeometry recompute contract)"

key-files:
  created:
    - src/bobbytailor/deterministic/walls.py
    - src/bobbytailor/deterministic/rooms.py
    - tests/test_walls.py
    - tests/test_rooms.py
    - tests/fixtures/synthetic/floorplan_synthetic.pdf
  modified:
    - tests/fixtures/synthetic/gen_synthetic.py
    - tests/fixtures/synthetic/truth.json

key-decisions:
  - "Network inputs snapped to 1e-6 pt grid (shapely.set_precision) before unary_union — interpolate-derived connector endpoints round off the target line in float, GEOS never nodes them, and polygonize silently merges faces (found via polygonize_full cut edges)"
  - "Opening gaps require corroboration: both wall faces broken OR a door-leaf-like perpendicular segment at the gap — dashed wall linework (fire-rating/track lines) no longer pollutes the 3'-0\" door_check signal"
  - "WallSegment.centerline_pt spans the chain end-to-end (openings included) so rooms.py gets door closures for free; length_pt is material-only (gaps excluded) for honest LF"
  - "Curved walls paired as whole flattened polylines at constant offset (not per-chord) with closed-loop exclusion so concentric symbol circles never become walls"
  - "Crow p0 office pods are single dashed outlines, not parallel-pair walls — unclosed/unlabeled rooms are vision-fallback territory by design (2 labeled rooms on p0, not the 3 the verify probe hoped for)"

patterns-established:
  - "Precision-grid noding: any future polygonize over derived line networks must snap inputs first (NETWORK_PRECISION_GRID)"
  - "Candidate registries: WALL-TCn / ROOM-n ids with point-space geometry for vision labeling (geometry proposes, vision disposes)"

requirements-completed: [V3-ACC-01]

coverage:
  - id: D1
    description: "Recipe B wall engine: parallel-pair extraction, thickness classes (0.5\" bins, TCn by LF desc), Bezier-flattened curved walls, hatch collapse, opening gaps"
    requirement: V3-ACC-01
    verification:
      - kind: unit
        ref: "tests/test_walls.py (13 tests: LF per class ±2%, two 3.0-ft openings, curve LF ±3%, hatch immunity, Crow smoke with door-band median)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Recipe C room engine: polygonize wall network into labeled rooms, exterior footprint union with 2% overall-dims cross-check, rooms_to_legend geometry-provenance handoff"
    requirement: V3-ACC-01
    verification:
      - kind: unit
        ref: "tests/test_rooms.py (11 tests: exact 4-face count, areas ±2%, labels bound, footprint cross-check both ways, Crow 397,600 SF anchor ±5%)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Synthetic floor-plan fixture with known truth (LF per class, room areas, footprint, door gaps, curved wall, hatch field)"
    verification:
      - kind: integration
        ref: "python3 -m pytest -q -m 'not golden' — 681 passed (657 baseline + 24 new)"
        status: pass
    human_judgment: false

# Metrics
duration: 53min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 10: Wall & Room Measurement Engines Summary

**Recipe B/C deterministic measurement: wall LF by thickness class from parallel-pair linework and room/floor SF from polygonized faces — Crow footprint lands 397,692 SF vs the 397,600 SF dims anchor (0.02% delta) via room-polygon union**

## Performance

- **Duration:** 53 min
- **Started:** 2026-07-14T15:00:12Z
- **Completed:** 2026-07-14T15:53:23Z
- **Tasks:** 3
- **Files modified:** 9 (5 created, 2 modified, 2 fixture PDFs regenerated)

## Accomplishments

- `walls.py`: Recipe B end-to-end — angle-quantized offset pairing (3"–16" real), ≥70% projection overlap, interval-aware multi-pairing (one continuous face vs broken pieces), collinear chain merge with opening gaps, 0.5" thickness bins → TC1/TC2… candidate ids, Bézier flattening at 0.5 pt chordal tolerance plus constant-offset arc pairing for curved walls, hatch-field collapse reuse, curve-share ≥5% review flag (Pitfall 6), 200k-segment cap (threat model)
- `rooms.py`: Recipe C end-to-end — wall-centerline network with junction snap connectors, precision-grid noding, polygonize, viewport/sliver/exterior-envelope filters with island subtraction (holes respected), deterministic text-in-polygon label binding with drafting-annotation stopwords, `building_footprint` exterior-envelope union cross-checked against overall-dims at 2%, `rooms_to_legend` with `_provenance: "geometry"`
- Door-opening gaps on Crow p0 cluster in-band: door-band median 3.133 ft (3'-0" + frame), ready for the scale solver's `door_check`
- Synthetic floor-plan fixture with exact ground truth locks both recipes: LF per class within 2%, two 3.0-ft openings, curved wall within 3%, exact 4-face count, footprint 4893.78 SF with 0.01% cross-check delta

## Task Commits

Each task was committed atomically:

1. **Task 1: walls.py — parallel-pair extraction with thickness classes** - `c6ede6d` (feat)
2. **Task 2: rooms.py — polygonize + label binding + footprint union** - `d57057a` (feat)
3. **Task 3: Layer-1 tests — synthetic + fixture walls/rooms** - `725d9d0` (test)

## Files Created/Modified

- `src/bobbytailor/deterministic/walls.py` - Recipe B wall engine (WallSegment, extract_walls, extract_walls_detailed, wall_lf_by_class, opening_gap_widths)
- `src/bobbytailor/deterministic/rooms.py` - Recipe C room engine (RoomPolygon, extract_rooms, building_footprint, rooms_to_legend)
- `tests/test_walls.py` - 13 layer-1 tests (synthetic truth + Crow smoke/door-band)
- `tests/test_rooms.py` - 11 layer-1 tests (synthetic truth + Crow footprint anchor)
- `tests/fixtures/synthetic/gen_synthetic.py` - generate_floorplan_page appended (existing 21-03/21-06 generators untouched)
- `tests/fixtures/synthetic/floorplan_synthetic.pdf`, `truth.json` - known-truth fixture with `floorplan` key
- `tests/fixtures/synthetic/{dimensions,symbols}_synthetic.pdf` - regenerated by the generator CLI (byte-level timestamps only)

## Decisions Made

1. **Precision-grid noding for polygonize** — snap connector endpoints computed via `interpolate` land off the target line by ~1e-14 in float; GEOS then never nodes them and polygonize leaves cut edges, silently merging adjacent rooms. `shapely.set_precision(g, 1e-6)` on every network member before `unary_union` fixes it robustly (diagnosed with `polygonize_full` cut-edge output).
2. **Opening-gap corroboration** — a chain gap is an opening only if both wall faces break there OR a door-leaf-like perpendicular segment (0.7–1.4× gap length) touches the gap. Without this, dashed wall linework (fire-rating/overhead-track patterns on Crow) floods `opening_gap_widths` with 2.5-ft artifacts and poisons the door_check signal.
3. **Chain span vs material length** — `centerline_pt` spans end-to-end (openings included) so the room network closes across doors with zero extra work; `length_pt` sums only the drawn pieces so LF never counts openings.
4. **Curves paired as whole polylines** — concentric arcs are compared by sampled constant-offset distance instead of per-chord angle bins (chord angles never align between independently flattened arcs); closed loops are excluded so double-circle symbols (columns/bollards) can't become walls.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] GEOS noding failure merged adjacent rooms**
- **Found during:** Task 2 (mini-synthetic probe: OFFICE+LOBBY returned as one 2,700 SF face)
- **Issue:** `interpolate`-derived snap-connector endpoints round off the target line in floating point; `unary_union` never nodes them; `polygonize` leaves cut edges and faces merge silently
- **Fix:** `NETWORK_PRECISION_GRID = 1e-6` snap on all network inputs before union
- **Files modified:** src/bobbytailor/deterministic/rooms.py
- **Verification:** mini-synthetic yields exact 4 faces at all tested grids; test_synthetic_room_count_exact
- **Committed in:** d57057a (Task 2 commit)

**2. [Rule 1 - Bug] Duplicate consecutive Bézier polyline points → NaN in shapely distance**
- **Found during:** Task 1 (Crow p0 probe emitted `RuntimeWarning: invalid value encountered in distance`)
- **Issue:** curve chains from PyMuPDF can repeat a vertex; the zero-length sub-segment makes GEOS distance emit NaN, which poisoned curve pairing
- **Fix:** consecutive-duplicate/non-finite point dedup before LineString construction in `_pair_curves`
- **Files modified:** src/bobbytailor/deterministic/walls.py
- **Verification:** Crow probe re-run under `-W error::RuntimeWarning` — clean
- **Committed in:** c6ede6d (Task 1 commit)

**3. [Rule 2 - Missing critical] Dashed-line gaps reported as door openings**
- **Found during:** Task 1 (Crow p0: dominant 2.47–2.67 ft "opening" cluster traced to dashed wall linework, not doors)
- **Issue:** the plan records any ≤4 ft chain gap as an opening; dash patterns break one face periodically, flooding `opening_gap_widths` and corrupting the scale solver's 3'-0" door_check
- **Fix:** two-face-break test plus door-leaf perpendicular-segment corroboration (`_gap_is_open_on_both_faces` / `_has_door_leaf`)
- **Files modified:** src/bobbytailor/deterministic/walls.py
- **Verification:** Crow openings drop from 79 (mostly dash noise) to 4 real candidates; door-band median 3.133 ft; synthetic still reports exactly two 3.0-ft openings
- **Committed in:** c6ede6d (Task 1 commit)

### Known Limitation (verify-probe shortfall, documented not hacked)

**Crow p0 labeled rooms: 2, not the ≥3 the Task 2 verify probe expected.** The three OFFICE POD outlines on Crow p0 are drawn as single dashed lines — they are not parallel-pair walls, so Recipe B correctly refuses them and Recipe C cannot close their faces. Adding single dashed lines to the room network would polygonize the structural grid into fake rooms (Pitfall 1). Unclosed/unlabeled rooms are exactly the vision-fallback case the fusion layer (21-11+) is designed for. All hard acceptance criteria pass; test_rooms asserts ≥1 labeled room plus the 5% footprint anchor.

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 missing critical) + 1 documented limitation
**Impact on plan:** All fixes were required for correctness of the door_check signal and room closure. No scope creep — no new modules, no API changes beyond the plan's exports.

## Issues Encountered

- GEOS float-noding subtlety cost the bulk of Task 2 debugging; `polygonize_full`'s cut-edge output was the decisive diagnostic (worth reusing for future network debugging).

## Verification Summary

- `python3 -m pytest tests/test_walls.py tests/test_rooms.py -q` → 24 passed
- `python3 -m pytest -q -m "not golden"` → **681 passed** (657 baseline + 24 new), 2 golden deselected
- Task 1 probe: Crow p0 TC1 = 1,714 LF (> 100 ft), door-band cluster median 3.133 ft ∈ 3.0 ± 0.17
- Task 2 probe: Crow p0 footprint 397,691.9 SF vs 397,600 SF anchor (delta 0.02% ≤ 5%), dims_crosscheck 0.0002 ≤ 0.02
- Acceptance grep gates: walls.py has all three functions + `"c"` branch; rooms.py has `polygonize`, `building_footprint`, `_provenance`, and the 0.02 threshold; test_rooms.py carries the 397,600 anchor

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Wall LF-by-class and room SF are deterministic candidate registries (WALL-TCn / ROOM-n) ready for vision labeling in the fusion layer
- `opening_gap_widths` is ready to populate the scale solver's `door_check` slot (21-07 left it as a pass-through)
- `rooms_to_legend` / `building_footprint` provide the authoritative-row handoff with `_provenance: "geometry"` for merge logic
- Curve-support review flag and 50k-segment cap wired for the pipeline integration plan

## Self-Check: PASSED

- All 6 key files verified on disk (walls.py, rooms.py, test_walls.py, test_rooms.py, floorplan_synthetic.pdf, SUMMARY)
- All 3 task commits verified in git log (c6ede6d, d57057a, 725d9d0)
- All task acceptance criteria re-run and passing; full non-golden suite 681 passed

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*
