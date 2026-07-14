---
phase: 21-accuracy-learning-engine
plan: "07"
subsystem: deterministic-measurement
tags: [scale, ransac, viewports, pymupdf, zero-calibration]

requires:
  - phase: 21-03
    provides: DimensionSample records from grammar-verified dimension-line association
  - phase: 21-01
    provides: src/bobbytailor package layout (deterministic/ home for new modules)
provides:
  - Viewport segmentation cascade (clip rects > title anchors > density gutters > fallback) with title-block/schedule masking
  - Per-viewport zero-calibration scale solve (weighted RANSAC consensus over DimensionSamples)
  - resolve_scale_v2 priority chain (override > dimension_solve > printed cross-check > learned prior) on the existing ScaleResult contract
  - select_main_plan by real area under each viewport's own scale
  - Hand-recorded scale_truth.json tables (Crow 4 pages, Bob 7 pages) + layer-2 gate tests
affects: [21-10 walls/rooms (consume ViewportScale.fpp + door_check), 21-13 pipeline integration (consume solve_page_viewports records), 21-16 learning retrieval (learned_prior tier)]

tech-stack:
  added: []
  patterns:
    - "Weighted RANSAC consensus: consensus size = paper length explained (sum of inlier points), median of inlier ratios"
    - "Flag-don't-guess: degenerate inputs return confidence 'none' and fall through the priority chain"
    - "Two-phase region building: proto-regions then frozen-bbox leftover claiming with midpoint union"

key-files:
  created:
    - src/bobbytailor/deterministic/viewports.py
    - src/bobbytailor/deterministic/scale_solver.py
    - tests/test_scale_solver.py
    - tests/fixtures/crow_cass/scale_truth.json
    - tests/fixtures/bobs_discount/scale_truth.json
  modified: []

key-decisions:
  - "RANSAC consensus measured in paper-length explained (sum of inlier points), not raw sample count — recovers Bob's printed 3/32\"=1'-0\" truth (10.6667 fpi) over six identical mispaired 216pt decoys that capture count-voting"
  - "Crow p0 main-plan truth is 1\"=40' (printed scale + 1136'/350' overall dims at 39.74/39.16 fpi); the plan's 20-fpi acceptance traced to a stale research note — 20 fpi is geometrically impossible on the 3024pt-wide sheet (21-03 STATE decision honored)"
  - "HIGH confidence is a three-condition conjunction: >=8 inliers AND >=80% inlier share AND printed agreement within 1%; a printed conflict caps confidence at LOW"
  - "Viewport bboxes live in UNROTATED PyMuPDF space (text, drawings and clip scissors all report there, even on rotation=270 pages)"
  - "learned_prior tier fires ONLY when solved and printed tiers are both empty (anti-amplification); unbacked printed notation capped at medium"

patterns-established:
  - "Per-viewport printed cross-check precedence: local callout anchor > title-text scale notation > page-level notation (single-scale pages only)"
  - "Mask kinds (title_block/legend/schedule) are excluded from dimension harvesting, solving, and main-plan candidacy"

requirements-completed: [V3-ACC-02]

coverage:
  - id: D1
    description: "Viewport segmentation: four-tier cascade with detection provenance, title-block/schedule masks, >=1 viewport per page"
    requirement: V3-ACC-02
    verification:
      - kind: unit
        ref: "tests/test_scale_solver.py#test_segment_viewports_crow_page0_regions_and_title_block"
        status: pass
      - kind: unit
        ref: "tests/test_scale_solver.py#test_segment_viewports_bob_uses_authoritative_clip_rects"
        status: pass
    human_judgment: false
  - id: D2
    description: "Zero-calibration per-viewport scale solve with honest confidence rubric and recorded per-viewport records"
    requirement: V3-ACC-02
    verification:
      - kind: integration
        ref: "tests/test_scale_solver.py#test_gate_a_crow_main_plans_match_truth"
        status: pass
      - kind: integration
        ref: "tests/test_scale_solver.py#test_gate_a_bob_main_plans_match_truth"
        status: pass
      - kind: unit
        ref: "tests/test_scale_solver.py#test_high_requires_printed_agreement_conjunction"
        status: pass
      - kind: unit
        ref: "tests/test_scale_solver.py#test_viewport_scale_record_surfaces_confidence_fields"
        status: pass
    human_judgment: false
  - id: D3
    description: "No HIGH-confidence wrong scales on any truth-table sheet (blocking gate B)"
    requirement: V3-ACC-02
    verification:
      - kind: integration
        ref: "tests/test_scale_solver.py#test_gate_b_crow_no_high_confidence_wrong"
        status: pass
      - kind: integration
        ref: "tests/test_scale_solver.py#test_gate_b_bob_no_high_confidence_wrong"
        status: pass
    human_judgment: false
  - id: D4
    description: "resolve_scale_v2 priority chain: override > dimension-solved > printed (demoted cross-check) > learned prior > none"
    requirement: V3-ACC-02
    verification:
      - kind: unit
        ref: "tests/test_scale_solver.py#test_resolve_v2_override_wins_over_everything"
        status: pass
      - kind: unit
        ref: "tests/test_scale_solver.py#test_resolve_v2_solved_beats_printed_when_apart_and_flags"
        status: pass
      - kind: unit
        ref: "tests/test_scale_solver.py#test_resolve_v2_learned_prior_only_when_tiers_empty"
        status: pass
    human_judgment: false
  - id: D5
    description: "Main-plan selection by real area after per-viewport scale — detail-callout frequency can no longer win"
    requirement: V3-ACC-02
    verification:
      - kind: unit
        ref: "tests/test_scale_solver.py#test_select_main_plan_real_area_beats_detail_frequency"
        status: pass
      - kind: integration
        ref: "tests/test_scale_solver.py#test_crow_overall_plan_solves_verified_truth_not_24"
        status: pass
    human_judgment: false

duration: 37min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 07: Zero-Calibration Scale Solving Summary

**Per-viewport weighted-RANSAC scale solve over DimensionSamples: Crow overall plan resolves dimension_solve/HIGH at 40.0 fpi (n=30, share 0.89, printed-verified), Bob plan sheets recover the printed 3/32"=1'-0" truth over a six-decoy contamination cluster, and the layer-2 gates prove zero HIGH-confidence-wrong scales.**

## Performance

- **Duration:** 37 min
- **Started:** 2026-07-14T13:17:03Z
- **Completed:** 2026-07-14T13:54:18Z
- **Tasks:** 3
- **Files modified:** 5 (all new)

## Accomplishments

- `viewports.py` (Task 1): four-tier segmentation cascade — authoritative clip rects via `get_drawings(extended=True)` (fires on Bob p1/p2), title-anchor binding with whitespace-gutter cells (Crow p1/p2), density-gutter splitting (Crow p0), nearest-anchor fallback. Title block detected on any edge (rotation-agnostic boundary-line + dense-text strip); `table_bboxes` masked as schedules; every page returns ≥1 viewport with `detection_method` provenance and deterministic `R1..Rn` ids by area.
- `scale_solver.py` (Task 2): deterministic RANSAC (k=min(n,50) hypotheses, ±2% inlier tolerance, consensus median) with consensus measured in paper length explained; ladder snap and printed notation demoted to cross-checks; `resolve_scale_v2` returns the existing `ScaleResult` contract with `dimension_solve`/`learned_prior` methods added; `select_main_plan` ranks by real area under each viewport's own solved scale with floor-plan-label near-tie break; `solve_page_viewports` orchestrates segmentation + solve for tests and 21-13.
- Truth tables + gates (Task 3): hand-recorded `scale_truth.json` for all 4 Crow and all 7 Bob pages (verified against printed scale text on rendered sheets, grid-label pitch, and overall-dimension spans). 25 tests: Gate A (100% main-plan truth within ±2%), Gate B (blocking — no HIGH-confidence viewport off-truth anywhere, plus structural rubric assertions on real output), Crow not-24' acceptance, Bob decoy-cluster recovery, full resolve_scale_v2 tier matrix, Pitfall-5 contamination, degenerate input, bounds filtering, off-ladder flagging, main-plan selection.

## Task Commits

1. **Task 1: viewports.py segmentation cascade** - `9279115` (feat)
2. **Task 2: RANSAC solve + resolve_scale_v2 chain** - `8a3a643` (feat)
3. **Task 3: scale_truth tables + layer-2 gate suite** - `ee428fb` (test)

## Files Created/Modified

- `src/bobbytailor/deterministic/viewports.py` — Viewport dataclass + segment_viewports four-tier cascade (753 lines)
- `src/bobbytailor/deterministic/scale_solver.py` — ViewportScale, solve_viewport_scale, resolve_scale_v2, select_main_plan, solve_page_viewports (445 lines)
- `tests/test_scale_solver.py` — 25 layer-2 gate + unit tests
- `tests/fixtures/crow_cass/scale_truth.json` — hand-recorded page→viewport→fpi truth (4 pages, includes p1 elevation viewports at 20/40 fpi)
- `tests/fixtures/bobs_discount/scale_truth.json` — hand-recorded truth (7 pages, p1/p2 mains at 10.6667 fpi)

## Decisions Made

- **Weighted consensus (deviation from literal "count inliers"):** consensus size is the summed paper length of inliers. Rationale: grammar-verified long spans (overall building dims, full chains) are the strongest evidence; on Bob p1/p2, six identical mispaired 216pt decoys win count-voting (8 vs 2 samples) but lose weight-voting (1795pt vs 3065pt), and only the weighted form passes the plan's own blocking Gate A against the hand-verified 10.6667 truth.
- **Crow truth correction 20→40 fpi:** see Deviations below.
- **Confidence rubric interpreted strictly:** printed conflict → LOW even with a large consensus (spec: "LOW = fewer/conflict") — honest flagging for half-size prints until a human confirms.
- **Per-viewport printed cross-check precedence** local anchor > title-text notation > page notation (single-scale pages only), so a page-level scale never cross-checks the wrong viewport on genuine multi-scale sheets.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Stale spec vs ground truth] Crow main-plan acceptance corrected from 20.0 to 40.0 fpi**
- **Found during:** Task 2 (verify probe) / Task 3 (truth-table recording)
- **Issue:** The plan's must-have ("Crow main-plan viewport solves to 1\"=20' ±2%") and Task 2/3 acceptance values came from a research note that 21-03 already refuted: the page-0 sheet prints "SCALE: 1\" = 40'-0\"" under "1 OVERALL FLOOR PLAN", the 1136'-0"/350'-0" overall dims span 2058.2pt/643.6pt (39.74/39.16 fpi), and 20 fpi is geometrically impossible (1136ft would need 4090pt on a 3024pt page). The 1"=20' scale exists on this set only on the page-1 West/East elevation viewports (recorded as non-main truth entries).
- **Fix:** Truth tables record the hand-verified 40 fpi for the p0 main plan; the Crow acceptance test asserts 40.0 ±2%, NOT within 2% of 24.0 (the historical failure the requirement targets), and not a detail scale. Honors the 21-03 STATE decision ("Crow page 0 consensus fpi≈40 matches printed scale") per orchestrator instruction.
- **Files modified:** tests/fixtures/crow_cass/scale_truth.json, tests/test_scale_solver.py
- **Verification:** solver returns dimension_solve/high 40.0 fpi with printed agreement; gate tests green
- **Committed in:** ee428fb

**2. [Rule 1 - Estimator correctness] Consensus weighting by paper length (spec said "count inliers")**
- **Found during:** Task 2 (Bob p1/p2 probing)
- **Issue:** Literal count-based consensus selects the 10.0-fpi decoy cluster on Bob p1/p2 (six identical 216pt mispairings) and fails the plan's blocking Gate A against the printed 3/32"=1'-0" truth.
- **Fix:** Consensus size = Σ points of inliers (solved value stays the plain median of inlier ratios per spec); `inlier_share` is the weight share feeding the unchanged confidence rubric. All other RESEARCH §2 parameters (k, ±2% tolerance, median) kept literal.
- **Files modified:** src/bobbytailor/deterministic/scale_solver.py
- **Verification:** Bob p1/p2 solve 10.573 fpi (0.9% from truth, printed agreement True → medium); Crow p0 unchanged at 40.0/high; contamination test still caps near-split votes at medium
- **Committed in:** 8a3a643

**3. [Rule 2 - Missing critical] Leftover-segment claiming in segmentation**
- **Found during:** Task 1 (Crow p0 probe)
- **Issue:** Percentile-trimmed region bboxes excluded the dimension chains around the Crow plan (the 1136'/350' dims and the 40-fpi callout sat outside the region), which would have emptied the main viewport's sample set — a correctness requirement for the solver.
- **Fix:** Two-phase region building: proto-regions, then unclaimed segments join the nearest region within 300pt using frozen original bboxes and midpoint-only union (border segments cannot explode a region); clip-rect regions stay authoritative and never grow.
- **Files modified:** src/bobbytailor/deterministic/viewports.py
- **Verification:** Crow p0 R1 contains the overall dims + callout (printed_fpi=40); title reads "OVERALL FLOOR PLAN / SCALE: 1\" = 40'-0\""
- **Committed in:** 9279115

---

**Total deviations:** 3 auto-fixed (2 Rule 1, 1 Rule 2)
**Impact on plan:** All three were required to satisfy the plan's own blocking gates against physical ground truth. No scope creep; interfaces are supersets of the planned exports (extra: `solve_page_viewports`, `Viewport.printed_fpi`/`segment_count`, optional `scale_text`/`door_check` params).

## Issues Encountered

- Rotated pages (Bob, rotation=270): PyMuPDF reports text, drawings and clip scissors in the unrotated coordinate space while `page.rect` reflects rotation — segmentation derives working dimensions rotation-aware and stays consistent with 21-03's samples.
- Crow p1 (elevations): the North elevation shares a gutter cell with East and the anchor split is imperfect (few dimension samples on elevation sheets); all p1 viewports honestly land LOW/none and the chain falls through to printed_scale/medium. Recorded as non-gating truth entries.
- `tests/fixtures/synthetic/*.pdf` regenerated as a test-run side effect; restored via `git checkout --` before committing (per execution notes).

## Known Limitations (documented, non-blocking)

- A single mispaired LONG decoy could in principle outweigh several short correct dims in a sparse viewport; the confidence rubric (HIGH needs count AND share AND printed agreement) keeps such a solve at medium/low.
- `door_check` is a pass-through field (always None) until walls (21-10) populates it, as planned.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `ViewportScale.fpp` + per-viewport confidence records ready for walls/rooms (21-10) and pipeline integration (21-13); `solve_page_viewports` is the intended entry point.
- `resolve_scale_v2` accepts `learned_prior` — 21-16 retrieval can wire the learning store into tier 4 without touching the chain.
- Suite: 626 passed (601 baseline + 25 new), `-m "not golden"`.

## Self-Check: PASSED

- All 6 created files exist on disk
- Task commits 9279115, 8a3a643, ee428fb present in git history
- `python3 -m pytest tests/test_scale_solver.py -q` → 25 passed
- Full suite `-m "not golden"` → 626 passed (601 baseline + 25 new)

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*
