---
phase: 23-measurement-engine-completion
plan: 14
subsystem: deterministic/room_fill + pipeline/takeoff_pipeline + vision/fusion
tags: [elevation, facade, silhouette, complement-labelling, datums, keynotes, wall-area, SP-9, D-11, INV-03, V4-MEAS-03, R3, T-23-55]
status: complete

requires:
  - phase: 23-02/23-07
    provides: "the printed-scale fixes (leading drawing number, stacked fractions, page-space pairing) the elevation callout anchoring depends on — Bob's p4 scales read 8.0, not 0.5"
  - phase: 23-09
    provides: "label_mask — THE one shared labeller, whose docstring already reserved consumer 3 for this plan's silhouette complement"
  - phase: 23-11
    provides: "_fill_clip_for_title's page-space clip discipline (the callout-anchored 'one drawing' pattern the elevation band clips follow) and the from_page_space inverse"
  - phase: 23-13
    provides: "BASIS_BINDERS — the SP-9 registry the elevation binder registers through; one-area-one-item arbitration inherited for free"
provides:
  - "room_fill.measure_facade_area — complement labelling: flood the FREE pixels from the clip border, invert, largest component; gross + voids + detached sub-components; per-clip pixel budget (zoom only ever lowered, R11/T-23-56); crop_band_pt datum cropping"
  - "room_fill.elevation_titles — elevations found by their OWN callout titles, with dedicated title-line recovery (Bob's FRONT ELEVATION DEMOLITION), orientation/demolition/interior classification; no orientation => excluded, never guessed"
  - "room_fill.elevation_datums + datum_wall_band + datum_scale_check — the drawing's own vertical ruler; zero-feet floor required (Moxy's sea-level ladder refuses); ±30% plausibility band that rejects a 16x misparse and never overrides a printed scale"
  - "room_fill.keynote_legend + keynote_tags — legends grouped BY HEADER through the 23-05 pairing primitive; a tag resolves through the legend of the drawing it sits in"
  - "component_library.wall_material_from_text — the wall-material vocabulary in the NAMING LAYER (CMU/split face, EIFS/Dryvit, stucco, brick, metal panel, storefront, tilt-up)"
  - "takeoff_pipeline._measure_elevation_areas + _elevation_clips + _flag_same_orientation_pairs — band clips anchored on callouts, each measured at its own scale, cropped to its own datum band, position-validated against the independent footprint"
  - "bundle keys elevation_areas + reference_footprint; _DETERMINISTIC_SHEET_TYPES gains 'elevation' while _PLAN_SHEET_TYPES is provably untouched"
  - "_resolve_project_wall_height Tier-0 'datum' source (Crow 36' plan-clear -> 48' datum) + _project_datum_span"
  - "fusion._fuse_elevation_areas + _bind_wall_area_basis — the elevation binder reached ONLY through BASIS_BINDERS['wall_area']; gross confident, splits flagged, cross-check flags and never publishes"
affects:
  - "23-15 (linear binder) — registers 'linear' beside the wall_area dispatcher; owns the civil half of V4-MEAS-03"
  - "23-16 (record) — the elevation capability is now committed evidence for the record correction"
  - "Phase 24 — Bob's exterior-painting scoring; DEF-23-14A (cross-sheet tilt-up vs facade dedupe) surfaces on the real Crow report"

tech-stack:
  added: []
  patterns:
    - "a facade is a filled silhouette, not a void: complement labelling (background = border-connected free space; facade = largest component of NOT background) through the ONE shared labeller"
    - "routing opens by widening the DETERMINISTIC set only; the plan-sheet tuple that gates every geometry engine stays untouched, so prior guarantees hold BY CONSTRUCTION and are pinned by a negative test"
    - "each drawing is measured at ITS OWN printed scale and cropped to ITS OWN printed datum band; the datum-derived scale is a plausibility band only and never overrides a printed scale"
    - "material attribution is TEXT-ANCHORED (keynote tag -> its drawing's own legend -> the naming layer); no anchor => the row exists under the drawing's own title, flagged — never a guessed material, never a ratio split"
    - "a second measurement route is a CROSS-CHECK: disagreement flags BOTH routes; the second route never publishes a quantity (D-11)"

key-files:
  created: []
  modified:
    - src/bobbytailor/deterministic/room_fill.py
    - src/bobbytailor/deterministic/component_library.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - src/bobbytailor/vision/fusion.py
    - tests/test_room_fill.py
    - tests/test_wall_height_resolver.py
    - tests/test_pipeline_deterministic.py
    - tests/test_fusion.py
    - .planning/phases/23-measurement-engine-completion/deferred-items.md

key-decisions:
  - "The no-datum flag is waived ONLY when the independently measured footprint width validates the blob (Bob's prints no ladder; its front facade reads 249.2 ft against the page-1 depth of 250.0). This reconciles Task 2's 'no datum pair must be flagged' with Task 4's 'Bob's emits gross at high confidence' — a plan-internal conflict on the real fixture. A synthetic no-datum clip with no footprint still flags."
  - "The resolver's datum span sits BELOW a learned human correction and ABOVE every keyword tier and the default — the plan mandates only the latter, and the learning-loop mandate keeps human corrections on top."
  - "'datum' is NOT added to _TRUSTED_HEIGHT_SOURCES: a project-level facade parapet multiplying an interior room-fill perimeter must still flag (T-23-51). The elevation binder never consults that set — each facade's datum band is its own drawing's ruler."
  - "The cross-check height is the MAX per-elevation datum span (Crow: 48' at the entry parapet), not a cherry-picked label: 133,478 SF vs 2,972 x 48 = 6.4% — and vs the typical T/ PANEL 45'-2\" it reads 0.6%, bracketing INV-03's 0.95%."
  - "Multi-material facades with nothing claimable emit ONE row (gross to the dominant-by-tag-count material) flagged with every tag named — no EIFS row is invented where no boundary exists."

requirements-completed: []
requirements-advanced: [V4-MEAS-03]

coverage:
  - id: T1
    description: "A facade is measured as ONE silhouette (not sixty-three voids), and elevations are found by their own callout titles with demolition/interior intent flagged"
    requirement: V4-MEAS-03
    verification:
      - kind: unit
        ref: "tests/test_room_fill.py::test_a_filled_rectangle_measures_its_known_area_and_bbox + ::test_a_subdivided_rectangle_is_still_one_component_of_the_same_area + ::test_an_opening_stays_in_the_gross_and_appears_in_the_void_list"
        status: pass
      - kind: integration
        ref: "tests/test_room_fill.py::test_elevation_titles_on_bobs_page_4_flags_the_demolition + ::test_chelsea_facades_have_one_dominant_component_per_titled_elevation + ::test_bobs_front_elevation_silhouette_and_its_detached_sign_band"
        status: pass
    human_judgment: false
  - id: T2
    description: "Each elevation is cropped to its own printed vertical ruler, and that ruler becomes the authoritative project wall height"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "tests/test_room_fill.py::test_elevation_datums_reads_the_crow_north_ladder + ::test_cropping_the_crow_facade_to_its_wall_band_lands_on_the_parapet + ::test_the_datum_scale_band_accepts_crow_and_rejects_a_16x_misparse + ::test_a_clip_with_no_datum_pair_yields_no_band"
        status: pass
      - kind: unit
        ref: "tests/test_wall_height_resolver.py::test_a_datum_span_beats_every_keyword_tier + ::test_no_datum_span_returns_exactly_what_it_returns_today"
        status: pass
    human_judgment: false
  - id: T3
    description: "Elevations reach the deterministic path and emit facade area, and the plan path is provably untouched (no fabricated walls, no thickness classes, no footprint)"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "tests/test_pipeline_deterministic.py::test_the_elevation_path_fabricates_no_walls_and_no_thickness_classes + ::test_routing_opened_and_the_plan_path_is_untouched + ::test_bobs_front_elevation_width_matches_the_independent_footprint + ::test_chelsea_yields_one_dominant_component_per_titled_elevation"
        status: pass
    human_judgment: false
  - id: T4
    description: "Elevation area binds through the SP-9 registry; materials attributed only where text-anchored; the perimeter x datum-height route flags and never publishes"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "tests/test_fusion.py::test_crow_two_route_identity_within_fifteen_percent + ::test_crow_publishes_no_perimeter_route_component + ::test_bobs_emits_a_gross_facade_component_at_high_confidence + ::test_a_keynote_number_resolves_to_the_legend_of_its_own_viewport"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py::test_no_parallel_frozenset_was_added + ::test_never_split_by_ratio_and_never_divide_by_material_count + ::test_the_cross_check_flags_both_and_publishes_no_second_quantity"
        status: pass
    human_judgment: false

metrics:
  duration: ~3h25m
  completed: 2026-08-04
  tasks: 4
  commits: 4
  tests_added: 46
  suite: "1810 passed, 2 deselected (baseline 1764)"
---

# Phase 23 Plan 14: Elevation Facade Measurement Summary

**An elevation sheet finally produces wall-area square feet: each facade is measured as a
complement-labelled silhouette at its own printed scale, cropped to its own printed datum
band, and bound through the SP-9 registry — while the plan path is provably untouched (the
elevation bundle returns ZERO walls and ZERO thickness classes where forcing floor_plan
fabricates 30 walls across 8 bogus classes), demolition and interior elevations are measured
but excluded, materials are attributed only where a keynote tag anchors them, and the
perimeter x datum-height route agrees with the silhouettes to 6.4% on Crow as a cross-check
that flags and never publishes.**

## Performance

- **Duration:** ~3h25m active (four full-suite gates at ~31-35 min each, run before every commit)
- **Started:** 2026-08-04T02:09:56Z — **Completed:** 2026-08-04T05:33Z
- **Tasks:** 4 of 4, one commit each
- **Files:** 0 created, 8 code/test files modified + 1 planning doc

## What shipped

### Task 1 — the facade primitive and the callout titles (`94fe831`)

`measure_facade_area` is the third consumer of THE one shared labeller, exactly as 23-09's
docstring reserved: flood the free pixels from the clip border (background), invert, take the
largest component. The same drawing the void fill fragments into 63 pieces returns one blob.
It reports gross, enclosed voids (so a net can be derived), and the DETACHED sub-components —
Bob's 141.7 SF EIFS sign band, 32.2 ft wide, with a page-space bbox a keynote tag can later
claim. Render resolution is chosen per clip against a pixel budget; the zoom is only ever
lowered (R11/T-23-56).

`elevation_titles` anchors on printed-scale callouts, NOT viewport segmentation (which merges
Crow's four elevations into two regions). The measured necessity: Bob's demolition callout
absorbed a keynote sentence ("10. PROVIDE BOLLARD PROTECTION…"), so a dedicated 25-pt title
line on the callout's own baseline outranks the callout text — recovering `FRONT ELEVATION
DEMOLITION`, flagged as demolition. Orientation must sit adjacent to the elevation word;
Moxy's forty-plus interior elevations ("UNISEX RESTROOM ELEVATION B"), "ELEVATION VIEW" and
"ELEVATION GUEST ENTRY DOOR" all classify to no orientation and are excluded, never guessed.

### Task 2 — the drawing's own vertical ruler (`91409b3`)

`elevation_datums` pairs label lines with value lines (Crow: `T/ PANEL` / `45' - 2"`,
`TRUCK COURT` / `-4' - 0"` with its sign), accepts inline `EL:` spot elevations (Chelsea),
and excludes mounting heights and dimensions by MARKER (`+16'-0" AFF` is an awning, `35'-3"
OPENING` is a dimension). `datum_wall_band` requires a genuine zero-feet floor — Moxy's civic
sea-level ladder (T/ ROOF 969'-2") correctly refuses. Cropping the Crow north blob to its band
brings the bbox height from 56 ft to 45.5 ft against the 45'-2" parapet; the sheet's cropped
silhouette sum is 133,478 SF. The datum-derived scale is a ±30% plausibility band ONLY
(measured 0.79-0.85x printed on Crow — noisy, exactly as INV-03 warned) and rejects a
16x misparse.

The resolver gains a Tier-0 `datum` source: Crow's project wall height moves from 36.0
(source `plan` — an interior clearance that understates the panels by 20%) to 48.0 (source
`datum` — the entry parapet), with byte-identical behaviour when no span exists, pinned by
test. Moxy and Bob's yield no span and are untouched.

### Task 3 — routing opened, plan path untouched (`408c3c8`)

`_DETERMINISTIC_SHEET_TYPES` gains `"elevation"`; `_PLAN_SHEET_TYPES` is deliberately
unchanged — the single restraint that keeps `extract_walls` / `extract_rooms` /
`cluster_symbols` / `footprint_from_page` off facades BY CONSTRUCTION. THE negative test pins
it with its contrast in the same test: Bob's page 4 as an elevation returns `walls == []`,
`wall_lf_by_class == {}`, `footprint is None` and 4 elevation areas; forced to `floor_plan`
the same page fabricates 30 walls across 8 thickness classes. A raster elevation still falls
back to the legacy flow.

`_measure_elevation_areas` builds band clips anchored on the callouts (viewport-hosted
x-bounds keep Bob's keyed-notes column and Chelsea's notes panel out of the silhouette;
midpoint splits separate Chelsea's side-by-side SIDE elevations), measures at each callout's
own feet-per-point, crops by each drawing's own datum band, and validates by POSITION: Bob's
front blob reads 249.2 ft against the page-1 footprint's independently measured depth of
250.0 (high confidence with no datum ladder); the truck-dock drawing — whose merged callout
binds ambiguously at 1/4" — reads 42.9 ft, fails the width check, and flags honestly. A
surviving same-orientation pair flags BOTH. Chelsea generality: 29 titled exterior elevations
across pages 9-16 and 18, one dominant component each, same code, no tuning.

### Task 4 — the binder, the keynotes, the cross-check (`895ecee`)

`keynote_legend` groups entries BY HEADER through the 23-05 pairing primitive
(`pair_two_token_tags`): Bob's `03` is NEW EIFS SCRATCH COAT under KEYED NOTES and REMOVE
EXISTING LIGHT SCONCE under DEMO KEYED NOTES, and `_legend_for_drawing` resolves a tag through
the legend of the DRAWING it sits in. The material vocabulary lives in the NAMING LAYER
(`component_library.wall_material_from_text`), not a fusion dict.

`_fuse_elevation_areas` registers against the wall-area basis through `BASIS_BINDERS`: one
dispatcher (`_bind_wall_area_basis`) answers both wall geometries, and the plans-only
backstop (no vocabulary at all) still dispatches through the same registry entry — no
parallel frozenset, asserted by test. The honesty boundary, measured on the real sheets:

| Facade | Outcome |
|---|---|
| Bob's REAR (CMU via keynote 11, width-validated) | `CMU Wall` 5,099.6 SF — **high confidence** |
| Bob's FRONT (CMU x12, storefront x7, EIFS x2 — EIFS tags sit OUTSIDE the sign-band sub-region) | `CMU Wall` 6,245.2 SF flagged, every tag named — no ratio split, no invented EIFS row |
| Bob's TRUCK DOCK (no tags) | named by its own title, flagged: no text anchor |
| Bob's FRONT DEMOLITION | measured 6,134.5 SF, EXCLUDED, coverage note |
| Crow x4 (no keynote legend) | title-named rows, flagged: no text anchor |

The D-11 cross-check: Crow's silhouette sum 133,478 SF vs the reference footprint's
2,972 LF x 48.00 ft = 142,656 SF — 6.4% agreement, recorded as a note; beyond 15% BOTH routes
flag; either way the component list contains NO item sourced from the perimeter route,
asserted on the real bundle. No test in this plan mentions the golden exterior-painting
figure.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` after each task | **1774 / 1784 / 1791 / 1810 passed, 2 deselected** (baseline 1764; +46) |
| Four-set gate (`test_four_set_coverage`, inside every full-suite run) | green all four times |
| Routing one-liner (`'elevation' in D`, `not in P`, `P == ('floor_plan','civil_site','roof_plan')`) | `routing opened, plan path untouched` |
| Negative test (elevation: 0 walls / 0 classes / no footprint; forced floor_plan: 30 / 8) | pinned |
| Bob's front width 245-255 vs footprint depth 250.0 | 249.2 ✓ |
| Crow two-route identity | 6.4% < 15% (vs T/ PANEL 45'-2": 0.6%) |
| Chelsea one-dominant per titled elevation | 29/29 |
| `ast.parse(..., feature_version=(3,9))` on every modified file | py39 ok |
| `git diff --diff-filter=D` after every commit | no deletions |
| `uploads/ human_inputs/ reports/ docs/PIPELINE-GROUND-TRUTH.md` | untouched |

**No paid command was run.** `pytest -m golden`, `accuracy_gate.sh`, `vision_only_benchmark.py`
and `golden_convergence.py` were not executed; `.env` was not read. Every number above comes
from a free offline probe or the offline suite.

### Impact analysis (CLAUDE.md), run before editing

| Symbol | Risk | Note |
|---|---|---|
| `_route_deterministic` | **CRITICAL** | 8 impacted, 5 processes |
| `run_sheet` | **HIGH** | 8 impacted, 4 direct, 4 processes |
| `_fuse_room_fills` | **HIGH** | 3 impacted, 3 processes |
| `_deterministic_bundle`, `_resolve_project_wall_height` | LOW | |

`detect-changes` before each commit read MEDIUM / **CRITICAL** (28 processes, the
run_project-resolver chain) / **HIGH** (15 processes) / MEDIUM. **Those HIGH/CRITICAL results
are hereby surfaced, as CLAUDE.md requires.** Mitigated, not accepted: the routing change is
one tuple literal pinned by the negative test; the resolver is byte-identical with no datum
span (pinned); the wall_area dispatcher is byte-identical on any bundle without elevation
areas (every 23-13 binder test passes untouched); and the full suite plus the four-set gate
were green before every commit.

## Deviations from Plan

### 1. [Measurement wins over the plan literal] Chelsea has 29 titled exterior elevations, not 21 — and Type A's front facade is 227 ft, not 106

INV-03 §1.3 tallied 21 drawings from callout titles alone; the dedicated title-line recovery
this plan shipped finds 29 (the same recovery that finds Bob's demolition). And INV-03 §3.2's
`FRONT ELEVATION TYPE A` figure (5,648 SF, 106 ft) came from a probe clip that truncated the
building: the rendered drawing shows one continuous three-storey block spanning ~227 ft, its
front (227) agreeing with its back (219) and its sides (89/102) with each other. The shipped
band clip measures the whole facade. The tests pin the measured truth (29 drawings, one
dominant component each), per the 23-09 rule that a pre-change measurement outranks a plan
literal.

### 2. [Measurement wins over the plan literal] The forced-floor_plan contrast is 30 walls / 8 classes today, not 22 / 4

INV-03's probe predates the 23-02/23-07 scale fixes; today's HEAD fabricates MORE. The
property the acceptance protects — the elevation path emits ZERO — is pinned exactly; the
contrast is pinned as ≥20 walls / ≥4 classes with the measured 30/8 recorded in the test's
docstring.

### 3. [Plan-internal conflict resolved] A no-datum facade is confident ONLY when position-validated

Task 2 demands "a drawing with no datum pair must be FLAGGED"; Task 4 demands "Bob's page 4
emits gross facade components at high confidence" — and Bob's prints no datum ladder at all
(probed: zero datum texts on the sheet). Resolution: the no-datum flag is waived only when
the blob's width matches the INDEPENDENTLY measured footprint dimension (249.2 vs 250.0 —
two measurements sharing no code path, no sheet, no scale). The synthetic no-datum acceptance
still flags: with no footprint to validate against, the reason names both absences.

### 4. [Design decision] A learned human correction still outranks the datum span

The plan mandates the datum span "beating every keyword tier and the default" — implemented
verbatim. It does not mention the learned tier; the learning-loop mandate (human corrections
outrank everything) keeps `learned` on top, pinned by test.

### 5. [Superseded test rewritten in-plan] The 23-13 registry name pin

`test_the_enclosed_region_bases_route_to_the_existing_binder` asserted
`BASIS_BINDERS["wall_area"].__name__ == "_bind_wall_area"`. The wall_area basis now routes
through the ONE dispatcher answering both wall geometries; the assertion is updated to
`_bind_wall_area_basis` with the supersession documented in the test. Every behavioural
23-13 binder test passes unchanged.

### 6. [Scope decision] "datum" is NOT a trusted height source for room-fill walls

Adding it to `_TRUSTED_HEIGHT_SOURCES` would let a 48-ft facade parapet multiply an interior
guest-room perimeter UNFLAGGED — the T-23-51 trap re-armed. The elevation binder never
consults that set (each facade's own datum band is its drawing's ruler); a room-fill wall row
that falls back to a datum-sourced project height flags with the source named, like `plan`.

### 7. [File-list note] Task 4 also touched takeoff_pipeline.py and component_library.py

The keynote attribution must run where the page is open (`_measure_elevation_areas`), and the
material vocabulary belongs in the naming layer — both files are in the plan's
`files_modified` frontmatter; the per-task file list named only fusion/room_fill/tests.

### 8. [Honest noise, accepted] Chelsea's genuine SIDE pairs fire the same-orientation flag

Two real side elevations of near-equal area are exactly what a missed demolition would look
like, so both flag (flag-don't-guess; a human confirms in seconds). Documented in the
helper's docstring.

### 9. [Scope boundary — logged, NOT fixed] DEF-23-14A: cross-sheet double-representation

Crow's tilt-up perimeter x height binding (floor-plan sheet, 23-08-era) and the new facade
rows (elevation sheet) measure the SAME exterior walls by two routes on two sheets;
one-area-one-item arbitration is per-sheet by 23-13's deliberate contract. Today the facade
rows are flagged and the cross-check note names both figures, so the overlap is visible,
never silent. Cross-sheet dedupe is an aggregation concern — logged as **DEF-23-14A** in
`deferred-items.md`.

### 10. [Pre-existing, reverted each time] The suite still rewrites three synthetic fixture PDFs

`tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` come back modified
after every full-suite run (23-08 dev 6 … 23-13 dev 7). Reverted before each commit, four
times, never committed.

---

**Total deviations:** 2 measurement-wins corrections, 1 plan-internal conflict resolved,
2 design decisions, 1 superseded test rewritten, 1 file-list note, 1 accepted noise,
1 deferred discovery, 1 pre-existing recurrence.

## Issues Encountered

**The demolition elevation's callout title is a keynote sentence.** The current
`extract_printed_scales` stacked-title logic hands the demolition callout "10. PROVIDE
BOLLARD PROTECTION…" — the acceptance's "demolition entry flagged as demolition" is
unreachable from callout titles alone. The drawing's own 25-pt title line, paired to the
callout by band intersection (with vertical-text and length filters that reject Chelsea's
rotated title-block strip and every note sentence), recovers all four Bob's titles exactly.

**Two legends, colliding numbers, one sheet.** Bob's `03` means opposite things in the two
keynote legends 300 pt apart. Grouping entries by the nearest header above them in their
column, then resolving each tag through the legend matching its drawing's demo flag, reads
both meanings correctly — pinned on the real PDF.

**The EIFS sign band is measurable but its tags don't claim it.** The fill finds the sign
band as a detached 141.7 SF component, but the `03` tags sit 17 pt above and 120+ pt left of
its bbox (leader-pointed). Per the honesty boundary the split is NOT invented: the gross goes
to the dominant CMU with the EIFS tags named in the flag. The claiming path is implemented
and pinned synthetically for the drawing set that does put a tag inside a closed sub-region.

## Known Stubs

None. **Deliberately absent, with named owners:** no `linear` basis binder (23-15 registers
it); no cross-sheet arbitration between the tilt-up and facade routes (DEF-23-14A, aggregation
scope); interior-elevation finish areas remain the flagged zero-quantity rows 23-06 shipped —
this plan adds no interior synthesis, by decision 4 of 23-CONTEXT.

## Threat Flags

None — no new network, auth, filesystem or schema surface. Registered mitigations, all
delivered:

- **T-23-55 (routing lets wall pairing fabricate facade walls)** — only the deterministic set
  changed; the plan tuple is asserted verbatim and the empty-walls negative test pins the
  contrast on the real sheet.
- **T-23-56 (wide-format clip exhausts memory)** — per-clip pixel budget; the zoom is only
  ever lowered; one shared labeller so each clip is labelled once; no resolution constant
  raised.
- **T-23-57 (silhouette absorbs bubbles/dimensions)** — datum-band crop (56 -> 45.5 ft on
  Crow) + fill-ratio floor 0.4 + width check against the independent footprint; no datum pair
  and no width validation => flagged.
- **T-23-58 (crafted datum ladder sets an implausible height)** — the datum-derived scale is
  a ±30% plausibility band that never overrides a printed scale and rejects an
  order-of-magnitude misparse; a datum-sourced project height is not a trusted source for
  room-fill walls.
- **T-23-59 (a confident split with no evidence)** — gross confident, split flagged with tags
  named, ratio splitting and equal division forbidden and pinned by test.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `94fe831` | Facade silhouette primitive + elevation callout titles |
| 2 | `91409b3` | Elevation datums — the drawing's own vertical ruler |
| 3 | `408c3c8` | Route elevations deterministically — without opening the plan path |
| 4 | `895ecee` | Elevation binder + keynote attribution + the flagging cross-check |

## Requirement status

- **V4-MEAS-03 — advanced, not completed.** The elevation wall-area half is delivered: a plan
  set with no floor plan now yields facade quantities, position-validated on three drafting
  offices. The requirement's civil-linework LF half is 23-15's (its frontmatter carries
  V4-MEAS-03 with the linear binder).

## What this unblocks

- **23-15** registers `linear` in the same registry; the wall_area dispatcher pattern shows
  the shape.
- **23-16** corrects the record with committed evidence: elevations are measurable, and the
  honest residual on Bob's (three of four facades drawn; the EIFS row is an ALT) is
  structural, never to be tuned closed (D-07).
- **Phase 24** scores Bob's exterior painting on the real report and surfaces DEF-23-14A on
  Crow.

## Self-Check: PASSED

- `src/bobbytailor/deterministic/room_fill.py` — FOUND
- `src/bobbytailor/deterministic/component_library.py` — FOUND
- `src/bobbytailor/pipeline/takeoff_pipeline.py` — FOUND
- `src/bobbytailor/vision/fusion.py` — FOUND
- commits `94fe831` / `91409b3` / `408c3c8` / `895ecee` — FOUND
- `git diff --stat human_inputs/ uploads/ reports/ docs/PIPELINE-GROUND-TRUTH.md` — EMPTY
