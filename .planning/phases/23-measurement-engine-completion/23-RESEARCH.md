# 23-RESEARCH — Measurement Engine Completion (planning input)

Synthesis of `INV-00` … `INV-08` in this directory. Read-only investigation; the only file written
was this one. Every code claim below carries `file:line`; every behavioural claim is traceable to a
zero-API probe in one of the INV docs, or to a probe re-run here.

**Read the INV docs for detail.** This document exists to do the one thing no single INV doc could:
**find the capabilities that MULTIPLE gaps need and force them to be built ONCE.**

---

## 1. TL;DR

1. **The measurement engine is not missing — it is unreachable, unbound, and mis-scaled.**
   Three distinct classes of defect, in descending order of value:
   * **Unreachable**: 18 of Moxy's 40 pages never run geometry (`sheet_pass_matrix.py:153` matches
     `COVER` inside "LIGHT SWITCH COVER PLATE"), and elevations are excluded from
     `_DETERMINISTIC_SHEET_TYPES` (`takeoff_pipeline.py:236`). `docs/PIPELINE-GROUND-TRUTH.md` §14's
     published 7.0 % Gyp-Ceiling number came from a **probe calling the engine directly** —
     a real run cannot reach those sheets (INV-00 §1, INV-08 §1.1/§1.3).
   * **Unbound**: measured areas are computed and then thrown away.
     `_ROOM_FILL_BASES = frozenset({"ceiling_area","roof_area","floor_area"})`
     (`fusion.py:1601`) drops every `wall_area` object at the gate (`fusion.py:1550`); basis
     `linear` has **no consumer at all** in `fuse_sheet` (`fusion.py:1911-1927`) even though
     `component_library.py:101-102` already names `Guard Rail`/`Hand Rail` as `linear`/`LF`.
   * **Mis-scaled**: `_paper_inches` (`printed_scale.py:141`) takes the first digit run left of `=`,
     so a leading drawing number becomes the paper-inch value. Confirmed live on today's HEAD:

     ```
     $ python3 scripts/scale_probe.py "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
     page 1: printed_scales=1 distinct_fpi=[0.3333]                       main=None   (should be 10.6667)
     page 3: printed_scales=4 distinct_fpi=[0.3333, 1.0]                  main=None   (should be 10.6667)
     page 4: printed_scales=6 distinct_fpi=[0.2, 0.3333, 0.5, 2.0, 8.0]   main=None   (should be [2.0,4.0,8.0])
     == multi-scale pages: 4/7
     ```
     Every Bob's page is mis-scaled AND `main=None`. Nothing measured on Bob's can be right until
     this is fixed — it is a **16×–32× linear, 256×–1024× area** error underneath GAP 3 and GAP 4.

2. **Two headline premises in the symptom log are FALSE and the plan must not encode them.**
   * GAP 2 "the clip leaks into the adjacent plan" — falsified by three independent probes
     (INV-02 §2/§3/§4). ID-412 is **bit-identical across a 240 pt range of clip widths**; its fill
     (458.3 SF) matches the drawing's own printed `17'-0⅛" × 26'-9⅛"` = 455.2 SF at ratio **1.007**.
     The ~2× is `total_for_units()` (`room_fill.py:268`) multiplying a correct single-unit area by a
     manifest `unit_count` of 2 that was derived from a golden door count.
   * GAP 4 "civil linework" — there is **no civil sheet in the Bob's set** (7 sheets: CS-1, A1.1,
     A2.0, A3.0, A4.0, A8.1, A8.3). Gas Piping is an annotated CAD linetype on the **A3.0 roof plan**,
     already inside `_PLAN_SHEET_TYPES` (INV-04 §1).
   * GAP 5 "finish schedule → room binding" — **there is no finish schedule in the input**
     (CS-03 is indexed on page 1 and absent from the 40-page PDF; `kind="finish"` fires zero times on
     all four real sets). WC-1..WC-10 are interior-**elevation** quantities (INV-05 §1).
   `docs/PIPELINE-GROUND-TRUTH.md` §9, §14.2 and "BLOCKER A" (:352) must be corrected as part of
   this phase, with citations.

3. **The multiplier IS in the plans.** `_manifest_room_mix`'s docstring
   (`takeoff_pipeline.py:626-632`) and GROUND-TRUTH `:352` both assert the unit count is
   unrecoverable. A blind census of the ID-001/ID-002 unit key plans (Moxy pages 7–8) yields
   **217 tags / 217 distinct room numbers / 0 duplicates → QQ A 90, KING A 26, K SUITE B 2,
   BUNK B 1 — a 4/4 exact match** to the golden multipliers (INV-05 §2 Key B). This removes the
   single largest human input from the Moxy path.

4. **Nine of the eight gaps collapse into five shared primitives plus five thin binders.**
   Four different INV docs independently propose adding a new `frozenset` next to `fusion.py:1601`;
   three propose a new open-run module; three propose making `MAX_REGION_SF` a parameter; three
   propose the same rotation helper; three report `scripts/room_probe.py:82` broken. Building those
   once is the entire point of §2 and the reason the plan sequence in §3 is ordered the way it is.

5. **Expect some numbers to get WORSE, deliberately.** Rails go from "5.8 LF, confidently wrong"
   (a pipe diameter in inches pushed through a unit-blind LF formula, `calculator.py:1263-1266`) to
   "~53 LF per ramp, flagged, count unknown". Moxy will report many more `NEEDS REVIEW` rows.
   That is the correct direction and it needs explicit sign-off before shipping (INV-06 risk 2).

---

## 2. Shared primitives — build ONCE

This is the load-bearing section. Each primitive below is demanded by **two or more** gaps. If a
plan builds any of these inside a single gap's implementation, the phase has failed its main
objective.

### SP-1 — Page-space (rotation-correct) coordinate transform
**Needed by gaps 1, 2, 3, 4, 5.** *(INV-03 §4.2 + step 3; INV-04 BUG-C + step 2)*

`page.get_text()` / `page.get_drawings()` return **unrotated** coordinates; `page.get_pixmap(clip=)`
expects **display** (`page.rect`) coordinates. Bob's pages are `/Rotate 270`; **Moxy pages 7–17 are
`/Rotate 90`**. Three live consumers are wrong today:

| Consumer | Location | Symptom |
|---|---|---|
| raster clip for the flood fill | `room_fill.py:221` | renders the wrong region on rotated pages |
| title↔scale adjacency `cy - ty1` | `takeoff_pipeline.py:1817` | Moxy p9/p13 return **zero** room_fills today; page-space prototype returns `LEVEL 1 LOBBY - AR` 355.4 SF |
| callout↔viewport "below" test `y1 <= cy` | `printed_scale.py:415` (`match_scales_to_viewports:381`), `_title_above:303` | Bob's A3.0 binds a *detail's* 1"=1'-0" to the main viewport → page 3 resolves 1.0 ft/in |

**Build:** one `to_page_space(page, rect) -> fitz.Rect` (= `Rect(rect) * page.rotation_matrix`,
normalized; identity at `rotation == 0`), plus an optional `page`/`rotation_matrix` argument on
`match_scales_to_viewports` / `_title_above` **defaulted to `None` so rotation-0 sheets take a
literally unchanged code path** (76 of 83 pages across the four fixtures).

### SP-2 — Printed-scale parser hardening
**Needed by gaps 3, 4 (and any future measurement on Bob's).** *(INV-03 §4.1 + steps 1–2; INV-04 BUG-A/BUG-B + step 1)*

`_paper_inches` (`printed_scale.py:141`, digit scan at `:166`) is unanchored, and
`_DROPPED_SLASH_FRACTIONS` (`printed_scale.py:127`) keys only on the *concatenated* form.
Adopt INV-04's verified recipe (anchor at the last `"` before `=`, parse right-to-left, add
split-stacked-fraction rules `"N D"`), which passes 14/15 cases including every form the four
fixtures print. Also recover a **leading** drawing number in `_number_and_title`
(`printed_scale.py:220`, digit strip at `:243`).

**Pinned acceptance across all four fixtures: `changed=7 unchanged=383`** — all 7 on Bob's, zero
movement on Crow / Moxy / Chelsea (INV-03 §4.1).

### SP-3 — One raster labeller + region geometry (perimeter, shape ratio, parameterised caps)
**Needed by gaps 1, 2, 3, 5.** *(INV-01 §3/§4 steps 1–6; INV-02 steps 3–4; INV-03 step 4; INV-05 steps 5–6)*

`_label_regions` (`room_fill.py:148-191`) builds a labelled bitmap and **discards it**, returning
only `(area_sf, px, touches_edge)`. Probe-confirmed `RoomFillResult` field list:
`['area_sf','candidate_id','needs_review','plan_kind','plan_name','regions','review_reason',
'scale_fpi','sheet_name','viewport_title']` — **no perimeter, no contour** (INV-01 §1).

Build one shared mask labeller with three consumers and three outputs:

| Output | Method | Consumed by |
|---|---|---|
| **enclosed voids** (today) | keep non-edge-touching regions | gap 1 (ceiling), gap 2 |
| **silhouette / complement** | flood the *free* pixels from the clip border → `solid = NOT bg` → largest component | gap 3 (facade) |
| **outer contour → perimeter → `P/√A`** | Moore-neighbour trace from the topmost-leftmost pixel + Douglas–Peucker at ε=2 px | gaps 1, 3, 5 |

Two hazards proven in the probes and both must be in the shared code, not rediscovered per gap:
* **Closed-ring DP collapse** — plain DP on a ring whose endpoints coincide returns length 0
  (INV-01 step 3 hit exactly this). Split at the vertex farthest from `points[0]`, simplify halves,
  rejoin.
* **Raw raster boundary counting over-reads ~5.9×** (INV-05 §3: KING SUITE B AR perimeter × 9 ft ×
  2 = 9,297 SF vs golden 1,566.65). The traced+simplified contour is what works; INV-01 §4 shows
  DP changes the perimeter by < 1.5 % and `P/√A` lands at **4.24–5.08** on four real guestroom RCPs
  (square = 4.00). **The two docs are not in conflict — INV-05 measured the naive method to show it
  must not be shipped.** Ship the traced method AND INV-05's printed-dimension cross-check.
* `MAX_REGION_SF = 900.0` (`room_fill.py:73`, filter at `:235`) must become a **parameter**, not a
  module constant, and an oversize region must be **kept and flagged**, never dropped. It currently
  makes the engine return `None` on every lobby / ballroom / retail floor plate (INV-02 §5,
  INV-03 §4.2, INV-05).

`P/√A` is a **blind** validator (no golden consulted): it flags the leaking AR fills at 8.54–9.04
and annotation cells at 11.6–13.4, while honest rooms sit at 4.24–5.08 (INV-01 §4).

### SP-4 — Geometric, viewport-bounded clip cell
**Needed by gaps 2, 3, 5, 6.** *(INV-02 steps 1–2; INV-03 step 7; INV-05 §2; INV-06 step 3)*

`_FILL_CLIP_UP_PT = 620` / `_FILL_CLIP_SIDE_PT = 260` (`takeoff_pipeline.py:1770-1771`) is a
fixed box hung off a title bbox with **no knowledge of the drawing's extent**. It survives only by
accident: adjacent clips overlap **8–48 % on every one of the 16 prototype sheets**, and correctness
depends on leaked neighbours happening to touch the clip edge. It **collapses to a 33 pt strip** on
`ID-109 LEVEL 7 - RCP PLAN` (page 14, title near the page top) → that sheet measures nothing.

Build `room_fill.clip_cells(titles_or_callouts, page_rect, mask_rects=()) -> List[Rect]`:
bottom = `anchor.y0 - 8`; left/right = the **midpoint** to the nearest anchor in the same row, else
the page edge / nearest masked `title_block|legend|schedule` rect; top = the `y1` of the nearest
overlapping anchor above, else page top. Then intersect with the drawing's own **ink bounding box**
(reuse `viewports._segments_from_paths` / `_trimmed_bbox`, drop the outer 1 % as leader outliers),
recording `clip_source` on the result.

The same cell serves: room fills (gap 2), elevation bands between consecutive callouts (gap 3),
elevation sheets whose anchor is a printed-scale callout not a `PLAN` title (gap 5 — pages 15–20
have `plan_titles=[]` and 5–17 callouts each), and per-detail rail clips (gap 6, where an unclipped
chain swallowed a 369.80 LF hatch field).

### SP-5 — Open-polyline run chainer (ONE module, two selectors)
**Needed by gaps 4 and 6.** *(INV-04 §3 + step 3; INV-06 step 2)*

INV-04 proposes `deterministic/linetype_runs.py`; INV-06 proposes `deterministic/linear_runs.py`.
**These must be one module.** Both need the identical core and neither can use `walls.py`, whose
`_pair_straight` (`walls.py:295`) requires two parallel faces at 3"–16" offset — a single-stroke
pipe run can never be emitted, and `MIN_WALL_SEG_FT = 2.0` (`walls.py:48`) would discard the 3 pt
exploded dashes.

Shared core: `_harvest_styled(page, doc)` returning `(x0,y0,x1,y1,length,width,color)` — a widening
of `walls._harvest` (`walls.py:204-273`, today bare 4-tuples) with `_harvest` re-expressed as a
projection so wall behaviour stays byte-identical; angle binning (`walls._angle_bin:279`); the
interval-union / gap-bridging loop (`walls._merge_chains:500-572`); `MAX_SEGMENTS = 200_000`
(`walls.py:84`) and a never-raise wrapper.

Two selectors on top:
* **annotated-linetype** (gap 4): micro-stroke blobs → signature `(stroke_count, w, h)`; require
  ≥3 marks of one signature, `pitch ≤ 6 × glyph span`, `pitch CV ≤ 0.35`, and ≥80 % of marks
  **break** the line. Validated: **162/164 detected marks within 12 pt of the estimator's own traced
  polyline**, and **zero runs on all 76 pages of Crow + Chelsea + Moxy**. The `pitch/span` gate is
  what kills Crow's "K.O." dock-panel tag row — the §10 coincidence trap, caught in the act.
* **rail / open-run** (gap 6): direction-continuity chaining (20° window), parallel-pair collapse
  (offset 0.02–1.00 ft, deliberately *below* `walls.MIN_THICKNESS_FT = 0.25`), min run length.
  Validated by position against the estimator's five marks: 53.00 vs 53.10 LF at the same bbox
  (0.2 %), 10.35 vs 10.50 (1.6 %), 10.21 vs 10.52 (2.8 %).

### SP-6 — Direction-generic two-token tag pairing
**Needed by gap 5 (twice), gap 3, and the unit-count census.** *(INV-05 steps 1/3 + `tag_pairing.py`)*

A tag is `<PREFIX>` + `<NUMBER>` adjacent **along the text line's own `dir` axis**, not in page x/y.
One `_project_bbox(bbox, text_dir)` helper serves:
* finish/material tags `WC`+`07` (gap 5) — **exact code SET on 6/6 elevation sheets including a
  true negative on p17**;
* room/unit tags `NAME`+`NUMBER` on ID-001/ID-002 (the multiplier census, 4/4 exact);
* keynote number ↔ legend text pairing on elevations (gap 3 material attribution).

The rotation trap is the whole reason this is shared: a y-stacked-only reader finds tags on Moxy
p15/p16 (`dir=(0,-1)`) and **returns `{}` on p18/p19/p20** (`dir=(1,0)`).

### SP-7 — Text-anchored naming + a single ambiguity gate + one canonical name form
**Needed by gaps 3, 4, 6, 7.** *(INV-04 §5; INV-06 step 7; INV-07 steps 9–10; INV-03 step 10)*

The same defect recurs four times: a name is produced by a path that bypasses canonicalisation, so
a correct measurement scores MISSING.
* `schedule_extraction.door_schedule_to_legend` emits prose `"Doors - Solid Core Wood (door
  schedule)"` (`schedule_extraction.py:245`, labels at `:39-48`) which cannot match golden
  `Doors-WD`; and `component_library.py:303` aliases `SCW → SC`, which matches **none** of
  `aggregator.py:93-97`'s door patterns.
* `aggregator.py:50-51` already canonicalises `guard.*rail → "Guard Rail"`, yet the saved run emits
  `Guardrail` — the library-verbatim path bypasses it.

Build: (a) one canonical-name normalisation every naming path routes through; (b)
`component_library` `linear` basis classification for
`(<MATERIAL> )?(PIPING|PIPE|CONDUIT|DUCT|DRAIN|CURB|FENCE|RAIL|SEWER|WATER|STORM)` harvested from
general notes, so `Gas Piping` gets `basis=linear, unit=LF` with no vision pass; (c) **one
`bind_or_flag` rule**: bind only when exactly one candidate family and exactly one surviving label
exist; otherwise emit the measured quantity with `needs_review=True` and a reason naming the
ambiguity. **Never round-robin names.**

### SP-8 — Coverage ledger, `quantity: Optional[float]`, and the flagged-zero contract
**Needed by gap 8 (owner) and by EVERY other gap's honest-failure path.** *(INV-08 §3–§5)*

Every gap has a "we could not measure this" branch, and today every one of them is a bare
`continue`. INV-08 enumerates **fifteen** such paths (S1–S15); four of them
(`fusion.py:1540`, `:1554`, `:1559`, `room_fill.py:140`) discard a **successfully measured** area.
`fusion.py:1559-1560` `continue`s where `select_fill_for_basis`'s own docstring
(`room_fill.py:135-138`) states the caller *"must flag, never substitute"*.

Build first, so no gap invents its own flag shape:
* `src/bobbytailor/pipeline/coverage.py` — `SheetCoverage` (one row **per page of the source PDF**),
  `DrawingCoverage`, `ItemCoverage`, `CoverageLedger` with `summary()`/`warnings()`/
  `assert_accounted()`.
* `src/bobbytailor/pipeline/provenance.py` — move `MEASURED / HUMAN INPUT / NEEDS REVIEW /
  NOT MEASURED` out of `scripts/export_takeoff_excel.py:38-47` into `src`, computed from the
  ledger's *record* rather than sniffed from the value.
* `aggregator.py:435` — emit `"quantity": None` for a never-measured item instead of the
  defaultdict's `0.0`. Single highest-value one-line change in INV-08.
* **The skip veto** (INV-08 §3.4): measurable geometry outranks a classifier keyword. If
  `plan_passes` is empty **and** the page carries ≥1 `"<NAME> - <KIND> PLAN"` title with a printed
  scale beneath it (or ≥1 non-title-block viewport with a solved scale), overrule the `title_sheet`
  verdict and run the **deterministic path only** (zero API).

**Invariant, testable in one line:**
`len(report["coverage_ledger"]) == report["coverage"]["pages_in_source"] == fitz.open(pdf).page_count`.

### SP-9 — Fusion basis-binder registry + one-area-one-item arbitration
**Needed by gaps 1, 3, 4, 5, 6.** *(INV-01 steps 9/12; INV-03 step 11; INV-04 step 7; INV-05 step 7; INV-06 step 5; INV-00 §4)*

Four INV docs independently propose adding a new frozenset next to `fusion.py:1601`
(`wall_area`, `_ELEVATION_AREA_BASES`, `_LINETYPE_BASES`, `_LINEAR_BASES`). Refactor once into a
basis → binder registry so each gap registers a binder instead of a parallel gate.

The registry must carry **arbitration**, because `aggregate_takeoff` (`aggregator.py:235`) *sums*
same-named buckets and `fuse_sheet` (`fusion.py:1911-1927`) appends every `_fuse_*` output into the
same list with no dedupe:
* `_fuse_wall_classes` already emits `Gyp Wall` 2,745 SF. Turning on wall-area room fills without
  suppression yields `2,745 + room-fill` — a wrong number that looks better (INV-01 risk 1).
* Crow's footprint value is currently bound to **six** line items at once — Building Footprint,
  Canopy, Concrete Pad, Exposed Structure, Sealed Concrete, Vapor Barrier. Two are right; an
  estimator bidding from that report prices the floor six times (INV-00 §4).
* A rail measured on a *typical detail* must never be summed with the same rail on the main plan
  (`is_typical`, INV-06 step 5).

Rule: a measured region backs **at most one** line item unless the plan states two finishes occupy
the same area, and every suppression lands in `fusion_rejected` with a reason
(`_reject_unknown_id`, `fusion.py:1945`, is the existing pattern).

### SP-10 — Unit-count provenance + the in-plan multiplier census
**Needed by gaps 1, 2, 5, 6, 7.** *(INV-05 steps 3–4; INV-02 steps 6–7)*

Every `× units` quantity depends on this and it is currently an unverifiable human input applied
silently at `confidence: "high"` (`fusion.py:1581`).
* Derive the mix from the plans via SP-6 (`_derive_room_mix`), **failing closed** (`{}` + flag) if
  room numbers are not unique across sheets.
* `_manifest_room_mix` (`takeoff_pipeline.py:624-651`) becomes `_resolve_room_mix(manifest, doc)`:
  manifest wins where present, derived fills the rest, every count carries a `source`
  (`estimator` | `unit_tag_census` | `door_schedule` | `assumed`).
* `_fuse_room_fills` flags any count that is not `estimator`/`unit_tag_census`, and downgrades
  `confidence` when `count > 1`. **Do not edit the four wrong Moxy counts to 1** — let the flag fire
  on exactly ID-412/416/420/422 and on nothing else; that is the acceptance test (INV-02 step 7).

---

## 3. Plan sequence (dependency-ordered, 2–4 tasks each)

Waves are dependency layers; plans inside a wave are independent of each other.

### Wave A — foundations (nothing measures correctly until these land)

**P1 — Coverage ledger, skip veto, flagged-zero contract** *(SP-8)* — depends on nothing
1. New `pipeline/coverage.py` + `pipeline/provenance.py`; `classify_sheet_type_verbose` returning
   `(type, source, keyword, context)` with the 1-arg function as a thin wrapper.
2. Register **every** source page in `pdf_analyzer.run_pdf_analysis`; thread the ledger through
   `run_project` → `generate_report`; add `coverage` / `coverage_ledger` / `item_coverage` /
   `coverage_warnings` / `pages_in_source` + `coverage.json`; COVERAGE section in `summary.txt`.
3. Skip veto in `run_sheet` (deterministic-only, zero API); `aggregator.py:435` `quantity=None`;
   generalise the completeness guarantee beyond `if manifest:` (`aggregator.py:406`) so plans-only
   runs also emit `NOT MEASURED` rows.
4. Promote INV-08 §1.1's audit to `scripts/coverage_probe.py`; fix `scripts/room_probe.py:82`
   (broken `select_main_plan([(v, None)])`, reported by INV-01/INV-02/INV-08) and add
   `--engine {vector,fill}`.

**P2 — Coordinate & scale correctness** *(SP-1 + SP-2)* — depends on nothing
1. `_paper_inches` anchored right-to-left parse + split-stacked-fraction rules; `_number_and_title`
   leading drawing number.
2. `to_page_space` helper; apply in `measure_enclosed_area` (`room_fill.py:221`), the title↔scale
   adjacency in `_measure_room_fills` (`takeoff_pipeline.py:1815-1819`), and optionally-rotated
   `match_scales_to_viewports` / `_title_above`.
3. Four-fixture before/after diff pinned as a test: `changed=7 unchanged=383`; Bob's page 3
   `fpp 0.013889 → 0.148148`; Moxy pages 9 & 13 room_fills empty → non-empty.

**P3 — Tag pairing, room-mix census, finish-tag rows** *(SP-6 + SP-10 + gap 5)* — depends on P1
1. `deterministic/tag_pairing.py` (`_project_bbox` along `dir`) + `deterministic/room_tags.py`.
2. `_derive_room_mix` with the uniqueness fail-closed gate; `_manifest_room_mix` →
   `_resolve_room_mix` carrying `unit_count_source`; correct the docstring and GROUND-TRUTH `:352`.
3. `deterministic/finish_tags.py` + `fusion._fuse_material_tags` emitting one **named, flagged,
   zero-quantity** row per (code, sheet) with `tag_positions_pt` seeding the human measure
   workspace. Fix `_fuse_schedules` (`fusion.py:1741`) so a `finish`-kind row never emits `1 EA`.

**P4 — Door schedule unification** *(gap 7)* — depends on P1 only (parallelisable with P2/P3)
1. `_normalise_material_text` + `_material_code` phrase vocabulary (leftmost-then-longest) +
   cell-pair joining; `_column_roles`; `_count_column` (returning `None` = one door per row).
2. Two-part legend guard (standalone title band **and** column-role evidence) — must land in the
   **same commit** as task 1 or the Moxy p15 elevation-grid phantom returns.
3. Merge the two parsers: delete `_parse_count_door_rows` and move `_hm_door_notes` into
   `door_schedule_to_legend` in the **same commit** (else Crow silently regresses to `Doors-IM`);
   canonical `Doors-<CODE>` / `Door Frames-<CODE>`, `SCW → WD`.
4. Coverage warning for "title present, table absent" (Chelsea's honest zero).

### Wave B — measurement primitives

**P5 — Region geometry primitive** *(SP-3 + SP-4)* — depends on P2
1. One shared mask labeller; `_trace_outer_contour` + `_simplify_ring` (closed-ring split);
   `perimeter_lf` / `shape_ratio` on `FilledRegion` and `RoomFillResult` (+ `to_dict`);
   `px_len_ft = (1/zoom)·fpp` beside `px_area_sf`.
2. `clip_cells` midpoint partition + ink-extent tightening; delete `_FILL_CLIP_UP_PT` /
   `_FILL_CLIP_SIDE_PT`; record `clip_source`.
3. `printed_extent_bound` + `cross_check_extent` replacing `flag_implausible_unit`
   (`room_fill.py:250-265`, wrongly applied pre-multiplication at `takeoff_pipeline.py:1837`);
   `MAX_REGION_SF` parameterised, oversize regions kept-and-flagged.
4. Invariance regression: the 16-sheet RCP baseline within ±2 %, and `ID-109 LEVEL 7 - RCP PLAN`
   (page 14) returns a result instead of `None`.

**P6 — Open-run chainer + two selectors** *(SP-5)* — depends on P2, P5 (clip cells)
1. `walls._harvest_styled` (with `_harvest` projected from it, byte-identical) + the chainer core in
   one new `deterministic/open_runs.py`.
2. Annotated-linetype selector S1–S9 with the pitch/span and break-fraction gates.
3. Rail selector: continuity chaining + parallel-pair collapse, clipped per viewport.
4. `viewports.py:733-742` — do not assign `legend`/`schedule` when the region has its own printed
   scale, and test only the title band. (Unblocks Crow's `STAIR PLAN` R7, holder of 4 of 5 rail
   marks, and the 4 unbound printed labels on Crow page 2.)

### Wave C — binders (primitive → line item)

**P7 — Room-fill wall-area binder + multiplier honesty** *(gaps 1 + 2, SP-9 + SP-10)* — depends on P3, P5
1. `wall_perimeter_for_unit` (shape-ratio gate, flag-don't-guess) + `wall_area_for_unit`;
   `drawing_ceiling_heights` / `resolve_drawing_height` reading the RCP's own `9'-0"`/`8'-0"` tags
   from the clip, excluding `AFF`, with precedence drawing → learned → project → **flag**.
2. Basis-binder registry (SP-9); add `wall_area`; branch `_fuse_room_fills` on basis.
3. `_suppress_superseded_wall_items` + one-area-one-item arbitration with `fusion_rejected`
   provenance (kills the 6-way footprint binding and the `2,745 + room-fill` double count).
4. `select_fill_for_basis` — **one** coordinated change reconciling three INV proposals: prefer
   `extent_ratio` closest to 1.0 (INV-02), never silently switch `wall_area` off AR (INV-01),
   return a flagged fill rather than `None` when all candidates are flagged (INV-08).
   `unit_count_source` on the emitted row + confidence downgrade when `count > 1`.

**P8 — Elevation facade measurement** *(gap 3)* — depends on P2, P5
1. `measure_facade_area` (complement labelling, largest component, `fill_ratio`, void list) +
   `elevation_titles` driven off `extract_printed_scales` (viewport segmentation is unreliable on
   elevations — Crow merges four elevations into two regions and mislabels a band `legend`).
2. `elevation_datums` → wall-band crop + a ±30 % scale plausibility band; feed the datum span into
   `_resolve_project_wall_height` as a Tier-0 `"datum"` source.
3. `_measure_elevation_areas` + `elevation_areas` on the bundle; routing —
   `_DETERMINISTIC_SHEET_TYPES = _PLAN_SHEET_TYPES + ("schedule", "elevation")` with
   **`_PLAN_SHEET_TYPES` untouched**, plus the negative test pinning 21-13.
4. `_fuse_elevation_areas` + keynote-tag material attribution (gross confident, split flagged) +
   the perimeter × datum-height cross-check that flags both when they disagree by >15 %.

**P9 — Linear-run binders + the phantom-LF kill** *(gaps 4 + 6, SP-7)* — depends on P6
1. `calculator._apply_formula` LF/SF branches (`calculator.py:1263-1266`, `:1275-1280`) become
   unit-aware; widen the detail-sheet callout guard (`calculator.py:523`) to include
   `guard_rail`/`hand_rail`/`striping`/`trench_drain`. Seven phantom rows disappear.
2. `run_scale_fpp` — a run is measured at the fpp of **the drawing that contains it**, resolved in
   display space; no containing callout ⇒ flagged, never measured at a borrowed page scale.
3. `_fuse_linear_runs` registered under basis `linear`; `component_library` linear-phrase basis
   classification; the SHX-annot → sheet-note → **flag** naming priority.
4. The ambiguity gate + `is_typical` "never sum a typical-detail run with a main-plan run"; canonical
   name normalisation for library-verbatim names.

### Wave D — record and harness

**P10 — Correct the record + lock the free harness** — depends on all
1. `docs/PIPELINE-GROUND-TRUTH.md`: §9 (no civil sheet), §14.2 (the clip is exonerated; the
   multiplier is the defect), §12b, `:352` BLOCKER A (the mix IS in the input, with the 4/4 census
   citation), and §14's blind table recomputed on one basis.
2. Rewrite the tests that encode the wrong story: `tests/test_room_fill.py:114-122`
   (`test_oversize_unit_is_flagged_never_silently_halved`) and
   `test_max_region_guard_rejects_sheet_scale_regions` (a 2,400 SF room must now be **measured**).
3. Fold the scratchpad probes into `scripts/` (fill probe, perimeter probe, clip sweep, coverage
   probe) so every acceptance check in §5 is a committed command.

---

## 4. Per-gap implementation summary

| Gap | One-line fix shape | Shared primitives it consumes | Detail |
|---|---|---|---|
| **1 — room binding** | Open the `wall_area` gate **and** give `RoomFillResult` a perimeter; do not multiply by the 15 ft roof-plan `CLEAR REQ'D` height | SP-3, SP-4, SP-8, SP-9, SP-10 | `INV-01-room-binding.md` |
| **2 — "clip defect"** | The clip is exonerated: make it geometric anyway (lobby generality), and make the manifest multiplier visible + cross-checked against the drawing's printed extent | SP-3, SP-4, SP-8, SP-10 | `INV-02-clip-defect.md` |
| **3 — elevation area** | Route elevations deterministically *without* opening `_PLAN_SHEET_TYPES`; measure the facade as a complement-labelled silhouette at each callout's own scale, cropped to its datum band | SP-1, SP-2, SP-3, SP-4, SP-7, SP-8, SP-9 | `INV-03-elevation-area.md` |
| **4 — "civil" linework** | Not civil: an annotated linetype on the A3.0 roof plan. Fix the scale, chain the open run, name it from the sheet's own note or flag | SP-1, SP-2, SP-5, SP-7, SP-8, SP-9 | `INV-04-civil-linework.md` |
| **5 — finish binding** | No finish schedule exists. Read the two-token material tag, emit named flagged zero rows to the human workspace, and harvest the unit-count census while you are there | SP-6, SP-8, SP-9, SP-10 | `INV-05-finish-schedule-binding.md` |
| **6 — rails LF** | Kill the inches-as-LF phantom in `_apply_formula`; measure the per-instance run; flag the instance count | SP-5, SP-7, SP-8, SP-9 | `INV-06-rails-lf.md` |
| **7 — door schedules** | Bob's is already detected and thrown away by a material-coverage gate that cannot read free text; Moxy's zero is a naming bug; Chelsea's zero is honest | SP-7, SP-8 | `INV-07-door-schedules.md` |
| **8 — coverage flags** | One ledger row per source page, `quantity: Optional[float]`, and a skip veto in which measurable geometry outranks a keyword | SP-8 (owner) | `INV-08-coverage-flags.md` |
| **0 — live-run evidence** | Scored saved runs: Moxy 8 % (measured items **0 %**), Crow 40 % (measurement already good at 75 % qty_ok; its gap is counts → Phase 25) | — | `INV-00-live-run-evidence.md` |

**Scoping note for the planner:** Crow's residual gap is *counts* and *wall-class binding*, not
measurement — three of its four measured items are already inside 1.3 %. **Phase 23 will barely move
Crow and should move Moxy and Bob's enormously. Do not judge Phase 23 by a Crow re-run.**

---

## 5. Offline verification strategy (free — zero API)

Paid runs are reserved for final validation. Everything below is free and must be a committed
command or test before the phase closes.

### 5.1 The five existing probes, and what each must gain

| Probe | Interface today | Extension required |
|---|---|---|
| `scripts/scale_probe.py <pdf>...` | positional PDFs, no argparse | pin the four-fixture before/after diff; assert Bob's p3 `main=10.6667`, p4 `distinct_fpi=[2.0,4.0,8.0]`, Crow/Moxy/Chelsea byte-identical |
| `scripts/geom_probe.py <pdf>` | one positional, writes `scratch_geom_probe.json` | print `room_fills` (with perimeter / shape_ratio / height / height source), `elevation_areas`, `linear_runs`, `excluded_viewports` |
| `scripts/room_probe.py <pdf> --fpi --pages` | **broken** at `:82` (`select_main_plan([(v,None)])` → `AttributeError` on every page) | fix the call; add `--engine {vector,fill}` so the engine that produces Moxy's numbers is finally exercised by a committed script |
| `scripts/fusion_probe.py` | hardcoded Crow page 1 | parameterise the PDF/page; exercise the new basis binders on a saved bundle |
| `scripts/score_report_dir.py --golden --dir` | works, needs no change | the free end-to-end scorer — run it against **saved** run dirs after re-running fusion offline; never re-run the live pipeline to check a number |
| `scripts/coverage_probe.py` | **new** (promote INV-08 §1.1) | the ledger's oracle: computes what the ledger must contain without running the pipeline |

### 5.2 Fixtures to add

* **Synthetic, no PDF** (`tests/test_room_fill.py` already builds `fitz` pages with a known scale):
  known-rectangle perimeter; perimeter unchanged by an interior hole; perimeter scales linearly
  while area scales quadratically (the §14 rule-2 guard for the new primitive); `P/√A ≈ 4.0` for a
  square and `> 8.0` for a 1×40 ft sliver; closed-ring DP does not collapse.
* **Real-PDF pinned baselines** (literals in tests, diffed not eyeballed):
  the 16-sheet Moxy RCP table `229.4, 235.5, 217.6, 362.5, 341.7, 458.3, 272.6, 309.5, 284.3,
  454.7, 274.6, 347.2, 347.7, 451.0, 463.0, 458.5`; the scale sweep `changed=7 unchanged=383`;
  the five Crow rail bboxes with ±3 pt / ±5 %; the Crow "K.O." row (`sig (54,2,2)`, 34 marks,
  pitch 53) must be **rejected**; the five Chelsea 3-mark candidates must be **rejected**;
  Bob's door schedule `HM 5 / SCW 7 / frame HM 12`; Moxy WC code SET per sheet
  (`p15 {WC-1,WC-2}`, `p16 {WC-1,WC-2,WC-4,WC-7}`, `p17 {}`, `p18 {WC-6,WC-7}`,
  `p19 {WC-9,WC-10}`, `p20 {WC-8}`); the census `217 tags / 217 distinct numbers / 0 duplicates`.
* **Negative / anti-regression fixtures**: forcing Bob's page 4 to `floor_plan` yields
  `walls: 22, wall_lf_by_class: 4` — the elevation path must **never** do that; Moxy p15's
  elevation grid must contribute zero door rows.

### 5.3 The acceptance checks that prove Phase 23 worked

1. **Coverage** — Moxy pages skipped `18 → 2`; `silent_loss_pages` `16 → 0`; **Crow stays 0 and
   Bob's stays 1** (a real cover sheet, `titles=0 scales=0`, classified `NOT_APPLICABLE`).
   `len(coverage_ledger) == page_count` on all four PDFs.
2. **Scale** — `changed=7 unchanged=383`; Bob's p3 `fpp 0.148148`; Moxy p9/p13 room_fills non-empty
   with `LEVEL 1 LOBBY - AR PLAN` > 300 SF.
3. **No area regression** — the 16-sheet RCP baseline within ±2 %; `area_sf` per fill byte-identical
   across the perimeter work (diff the probe outputs).
4. **Clip is now geometric** — re-run the ±80 pt sweep; post-fix *every* sheet is invariant
   (today ID-407/413/415 move by +17 % to +20 %).
5. **Perimeter is physical, blindly** — dominant RCP region `P/√A ∈ [4.0, 6.0]`;
   `perimeter_lf / area_sf ∈ [0.20, 0.45]` per foot; every AR fill with `shape_ratio > 8` emits a
   **flagged row, not a number**.
6. **Height comes from the drawing** — every RCP prototype reports `wall_height_ft == 9.0`,
   `wall_height_source == "drawing"`, and specifically **not 15.0**.
7. **Multiplier flag fires on exactly four sheets** — ID-412/416/420/422 flagged, ID-407/408/409/
   410/411/413/414/415/417 clear.
8. **Elevations** — Bob's p4 blob width 245–255 ft against the *independently measured*
   `footprint_from_page(p1).depth_ft == 250.0`; Crow silhouette-sum vs `perimeter × datum height`
   agree within 15 % (measured 135,528 vs 134,246 = 0.95 %); Chelsea pages 9–12/13–16/18 give exactly
   one dominant component per titled elevation. **Never assert on 16,219.**
9. **Linetype runs** — ≥95 % of detected marks within 12 pt of the take-off's markup polyline
   (observed 162/164); **zero runs on all 76 pages** of Crow + Chelsea + Moxy;
   `840 ≤ Gas Piping LF ≤ 935`. Do not tune to close the last 4.4 %.
10. **Rails** — the five estimator bboxes reproduced within ±3 pt / ±5 %; `awk -F, '$1 ~ /rail/ &&
    $4 == "in"' output/*/calculations.csv` returns **empty**; at most one `Guard Rail` row whose
    formula names exactly one viewport. **Never assert on 420.35 / 438.80.**
11. **Doors** — Bob's `5 / 7 / 12`; Crow unchanged at `29 / 29` with the `IM → HM` note reclass
    intact; Moxy's existing 42 becomes a *scorable* `Doors-WD`; Chelsea `openings == 0` **and**
    `titled_pages != []`.
12. **No silent zeros** — no `takeoff_summary` row with `quantity == 0.0` and
    `provenance == "MEASURED"`; every `quantity is None` row carries `NOT MEASURED` or
    `NEEDS REVIEW`.
13. **Suite** — `python3 -m pytest -q` (1,132 offline tests; `pytest.ini` excludes the golden marker
    by default since `10cd7be`).

**Forbidden throughout, and not used by any check above:** `pytest -m golden`,
`scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py`, `scripts/golden_convergence.py`,
anything requiring `ANTHROPIC_API_KEY`.

**Answer-key discipline.** The `-Take offs.pdf` markup vectors (estimator polylines, per-sheet Legend
boxes) are used **only** as positional/set answer keys in tests, never as pipeline input, and never
as a count to tune toward.

---

## Validation Architecture

*(Required section — the Nyquist gate reads this.)*

### Test infrastructure — three tiers

| Tier | What it is | Cost | Where it lives |
|---|---|---|---|
| **T1 — synthetic unit** | `fitz`-drawn pages with exact known geometry and a known scale (the pattern already in `tests/test_room_fill.py:50`, `FPP_QUARTER`); pure-function tables for parsers | milliseconds | `tests/test_*.py` |
| **T2 — real-PDF probe with a pinned baseline** | a committed `scripts/*_probe.py` run over `uploads/`, its output diffed against literals recorded in this phase | seconds–minutes, zero API | `scripts/` + `tests/` assertions |
| **T3 — saved-run rescore** | `scripts/score_report_dir.py --golden … --dir output/<saved run>` after re-running fusion **offline** against the saved bundle | zero API | `scripts/score_report_dir.py` |

T1 proves a primitive is *correct*. T2 proves it *generalises across drafting offices*. T3 proves the
end-to-end binding did not regress. **No tier substitutes for another**, and a change that only has
T1 coverage is not shippable in this phase — every historical failure in this program (the 0.55 →
0.88 title-block constant, the 136-column coincidence, the guestroom-shaped `MAX_REGION_SF`) was a
change that passed T1 and had no T2.

### Sampling rate

The failure mode of this codebase is **a change validated on one plan set**. The sampling rate is
therefore set against fixture diversity, not against code volume:

* **Per task → T1.** Every new primitive (perimeter, contour, DP ring, `_paper_inches`,
  `_material_code`, `_project_bbox`, chainer, complement labeller) gets a synthetic test with exact
  ground truth before it is wired into anything.
* **Per plan → T2 on ALL FOUR plan sets, always.** Crow (4 pp), Moxy (40 pp), Bob's (7 pp),
  Chelsea (32 pp) = 83 pages, four different drafting offices, four rotation/scale/title-block
  conventions. A per-plan acceptance table must report a number for each of the four, including
  "unchanged" — an acceptance criterion that names only one fixture is rejected at review.
* **Per wave → T3 + full `pytest -q`.** Re-score every saved run directory; diff the probe outputs
  for all four fixtures against the wave's entry baseline.
* **Per constant → a stated non-golden rationale.** Any numeric constant introduced must carry a
  comment giving (a) the observed value it was read from, and (b) the geometric or physical reason
  for its margin. Examples that pass: `P/√A ≤ 8.0` (4.00 is a square, worst honest room measured
  5.08, so 8.0 is a ~2× margin); `TOL = 1.25` on `extent_ratio` (13 sheets ≤ 1.07, a real two-plan
  leak reads ≈ 2.0); `pitch ≤ 6 × glyph span` (GAS ratio 3.4, K.O. ratio 26.5, Chelsea 10–24).
  Examples that fail: any threshold whose justification is "this makes the total match".

### Per-task verification approach

Every task in §3 must state its verification in one of exactly four shapes, and the plan is
rejected if a task cannot:

1. **Exact-ground-truth assertion (T1)** — "a 10 ft × 20 ft synthetic room measures
   `perimeter_lf == 60.0 ± 2 %`". Use where the answer is known by construction.
2. **Position/shape assertion against an independent measurement (T2)** — "the facade blob is
   245–255 ft wide against `footprint_from_page(page 1).depth_ft == 250.0`", "162/164 detected marks
   within 12 pt of the estimator's polyline", "`P/√A ∈ [4.0, 6.0]`". **This is the only admissible
   way to validate a detector.** Never a count.
3. **Invariance / no-regression diff (T2)** — "byte-identical on Crow, Moxy, Chelsea";
   "the 16-sheet RCP baseline moves < 2 %"; "`changed=7 unchanged=383`". Use for every shared-path
   edit (SP-1, SP-2, SP-5's `_harvest` widening, SP-9's binder refactor).
4. **Negative / anti-regression assertion (T1 or T2)** — "the elevation path emits `walls == []` and
   `wall_lf_by_class == {}`"; "zero linetype runs on 76 non-Bob's pages"; "the Crow K.O. row is
   rejected"; "Moxy p15 contributes zero door rows"; "Bob's page 0 stays skipped". Every widening
   of a gate needs one.

**Coverage as a measurement of the tests themselves.** SP-8's ledger doubles as the phase's own
instrumentation: after each wave, `scripts/coverage_probe.py` reports how many source pages the
pipeline actually reaches. That number — not a golden score — is the wave's progress signal, because
a page that is never reached cannot be measured right or wrong. **But a green coverage number is not
accuracy** (INV-08 risk 4); it must never become the target.

---

## 6. Risk register

| # | Risk | Evidence it is real | Mitigation |
|---|---|---|---|
| **R1** | **Overfitting to Moxy/Crow.** A constant tuned on one CAD template silently destroys another. | Retuning the title-block x-fraction `0.55 → 0.88` fixes Moxy (18→2 skipped) and **breaks Chelsea** (2→10 skipped, floor_plan 9→1) — INV-00 §1d. | Never fix a classification by moving a fraction. The skip veto (SP-8) is structural: it triggers on *the presence of scaled plan geometry*, and is verified to change nothing on Crow and Bob's. Per-plan T2 on all four sets is mandatory (§Validation Architecture). |
| **R2** | **Breaking the 9 currently-correct room-fill sheets.** The clip rework and the perimeter work both touch the area path. | Pages 23,24,25,26,27,29,30,31,33 currently measure correctly; adjacent clips already overlap 8–48 % and survive only via `touches_edge` — INV-02 §3. | Pin the 16-sheet RCP baseline as literals; require `|new-old|/old ≤ 0.02` per sheet; require `area_sf` byte-identical across the perimeter change specifically (perimeter must not perturb area). |
| **R3** | **Re-opening what 21-13 deliberately closed** — elevations were kept out of the deterministic path because wall pairing fabricates facade "walls". | Forcing Bob's page 4 to `floor_plan` emits **22 bogus walls / 4 bogus thickness classes**; leaving it `elevation` emits 0 — INV-03 §1.2/§8. | Add `"elevation"` to `_DETERMINISTIC_SHEET_TYPES` **only**; leave `_PLAN_SHEET_TYPES` (`takeoff_pipeline.py:232`) untouched, which gates `extract_walls`/`extract_rooms`/`cluster_symbols`/`footprint_from_page` at `:1707`/`:1716`. Pin it with a negative test asserting `walls == [] and wall_lf_by_class == {} and footprint is None` while `elevation_areas` is non-empty. |
| **R4** | **Tuning to a golden count** — the documented §10 trap, and it has four live invitations in this phase. | "136 collinear dimension ticks ≈ 132 columns"; the four Moxy manifest counts; the rail multiplier (drawn 90.6 LF vs golden 859.15); Moxy doors 42 vs 213; a wall height back-solved to 11.06 ft to make Gyp Wall land. | Validate by **position/shape/set** only (§Validation Architecture case 2). Flag, never correct, the four manifest counts — the acceptance test is *the flag firing on exactly those four*. Never assert on 420.35 / 438.80 / 16,219 / 1,566.65 / 213. |
| **R5** | **Double counting.** `aggregate_takeoff` (`aggregator.py:235`) sums same-named buckets; `fuse_sheet` appends every binder into one list with no dedupe. | Crow's footprint value is bound to **six** line items; `_fuse_wall_classes` already emits `Gyp Wall` 2,745 SF; typical-detail rails would sum with main-plan rails. | SP-9's one-area-one-item arbitration must land **with** the first new binder (P7), not after. Every suppression recorded in `fusion_rejected`. |
| **R6** | **A wrong height that does not flag.** Moxy resolves 15.00 ft, `source="plan"`, from a roof-plan `15'-0" CLEAR REQ'D`; `is_default` is False (`fusion.py:1424`) so nothing flags. | INV-01 §5, probe output pasted there. | Per-drawing RCP tag first (`9'-0"`, extracted from the exact clip already computed), then learned, then project, then **flag**. Any height not read from that drawing's own clip sets `needs_review` with the source named. |
| **R7** | **Accuracy goes DOWN on naive metrics.** Confidently-wrong numbers become honestly-flagged ones. | Rails 5.8 LF → ~53 LF flagged (6–21× "under" golden); Moxy gains ~10 WC rows + PT/WD/AT/ST/RB rows at quantity 0; `select_fill_for_basis` ambiguity flags surface on sheets that were quietly resolved. | Get explicit sign-off before shipping P9 (INV-06 risk 2). Land the flag surfacing in the same change as the flag. Report measured-item accuracy and coverage separately. |
| **R8** | **Shared-path blast radius.** SP-1 touches every sheet's scale binding; SP-5 changes `walls._harvest`'s shape; SP-9 refactors the fusion binder gate. | INV-04 names BUG-C as the highest-blast-radius edit in its map. | Keep every new parameter optional and `None`-defaulted so rotation-0 sheets take an unchanged path; project `_harvest` from `_harvest_styled` so wall output is byte-identical; run `gitnexus_impact` on `_harvest`, `_measure_room_fills`, `_fuse_room_fills`, `select_fill_for_basis` before editing (CLAUDE.md mandates this). |
| **R9** | **Flag fatigue / a loud ledger mistaken for progress.** | INV-05 risk 5, INV-08 risk 4: an honest report of "16 sheets not measured" is still 4 % accurate. | Group flagged rows by code across sheets and cap the emitted set. Coverage is the wave progress signal, never the phase target. |
| **R10** | **`quantity: Optional[float]` is a type change on a public field.** | Audited safe: `score_report_dir.py:24-33`, `export_takeoff_excel.py:40`, `reporter._write_takeoff_summary_csv:700`. Web consumers unaudited. | `grep -rn 'quantity' src/bobbytailor/web/` before landing; any bare `float(row["quantity"])` must be found first. |
| **R11** | **Performance.** Pure-Python BFS over ~1.2 M px per clip; Moxy's 40-page fill probe took minutes; Crow page 0 harvests 33,018 segments; elevation clips are wide-format. | INV-01 risk, INV-03 risk, INV-06 risk 6. | Share one labeller so each clip is labelled once, not twice; pick DPI per clip so the pixel budget is bounded; keep `walls.MAX_SEGMENTS`; **do not raise `DEFAULT_DPI`** (`room_fill.py:65`) as part of this work. |
| **R12** | **One-sample generalisation on the linetype detector.** The whole recipe rests on ONE run family on ONE page. | INV-04 risk 2 — nothing in `uploads/` proves it fires on a second project. | Ship behind SP-7's ambiguity gate; keep the zero-false-positive sweep (76 pages) as a permanent test; let the learning loop supply the second sample. |
| **R13** | **Stale premises re-entering the plan.** INV-00 §1b/§1e reason from the "clip leak" hypothesis that INV-02 later falsified, and INV-00 §1e's 49,046 SF simulation is not a target. | INV-00 predates INV-02. | Where INV-00 and INV-02 disagree, **INV-02 wins** (it has the falsifying probes). INV-00's simulated total must never appear as an acceptance criterion. |

---

## 7. Open questions for the planner (decide before writing plans, do not resolve by tuning)

1. **Shared-partition accounting.** Summing every region's outer perimeter counts a bedroom/bath
   partition twice (once per side) — right if the estimator bills board faces, wrong if they bill
   wall length once. Resolve by reading the estimator's legend or asking the human,
   **not** by trying ratios until a total matches (INV-01 risk).
2. **Rail instance multiplier.** The drawings do not print it and the golden is 6–21× the drawn
   lengths. Ship per-instance + flagged, or hold the item back entirely? Needs a user decision.
3. **The four Moxy manifest counts.** Flag only in this phase (agreed); who owns correcting
   `human_inputs/moxy_knoxville.json`, and does the unit-tag census (SP-10) supersede the manifest
   outright once it proves 4/4?
4. **Bob's undrawn facades.** Only 3 of 4 elevations are drawn, so a silhouette-only sum can never
   reach a whole-building golden. Does the `perimeter × datum height` route publish a second
   quantity, or remain a cross-check that flags disagreement? (INV-03 recommends the latter.)
