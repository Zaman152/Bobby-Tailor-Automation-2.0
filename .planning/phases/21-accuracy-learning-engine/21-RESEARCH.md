# Phase 21: Accuracy & Learning Engine (v3) - Research

**Researched:** 2026-07-13
**Domain:** Deterministic PDF vector-geometry take-off + AI-vision semantic fusion + retrieval-based learning
**Confidence:** HIGH (geometry/scale/model APIs verified), MEDIUM (fusion protocol, ensemble parameters — sound engineering judgment, not vendor-documented)

## Summary

The central question of this phase — how to combine AI vision and PDF vector geometry so a plans-only take-off is ~100% accurate with zero manifests, zero calibration, zero human loop — has a clear, well-supported answer that the codebase is already 60% of the way toward proving. The fixture PDFs are vector CAD (~68k geometry items/sheet). Everything measurable on them is *literally encoded* as coordinates and text: dimension strings, schedule tables, legend quantities, wall linework, symbol blocks. `footprint_takeoff.py` (397,600 SF vs 395,673 golden, 0.5% error from two dimension strings) and `schedule_extraction.py` (exact door schedule rows) already prove the pattern. What is missing is generalizing it: (a) a **dimension-line association engine** that pairs every printed dimension string with its physical dimension-line geometry, yielding dozens of (feet, points) samples per viewport, from which scale is solved by robust regression with zero calibration; (b) a **wall/room/symbol segmentation layer** over `page.get_drawings()` (parallel-pair walls, `shapely.polygonize` rooms, hash-clustered repeated symbol blocks); (c) a **fusion protocol** where Claude only *labels* geometry candidates the deterministic engine found (via annotated overlay renders and crop galleries, answering with candidate IDs through structured outputs) and never emits a number that geometry or the text layer can provide; and (d) ensemble voting confined to the residual raster-only/ambiguous cases.

This is exactly how the commercial state of the art works. Kreo, Togal, and STACK all read native vector data when available ("reads native PDF and CAD vector data, so measurements are accurate to the original file" — Kreo docs), auto-detect drawing boundaries/viewports, use reference-element matching for Auto Count (find-all-similar to a selected cluster — the same repeated-block clustering recommended below), and treat scale verification against a known dimension as non-negotiable. None of them let a vision model guess a quantity when geometry exists. Our differentiator is replacing their "human selects the reference symbol / confirms the region" step with Claude Vision as the semantic selector, and persisting every human verification into a learning store so the semantic layer improves per project type.

**Primary recommendation:** Build a `deterministic/` measurement package (dimension graph → per-viewport scale solve → wall/room/symbol extraction) as pure-Python + `shapely` on top of PyMuPDF, make it the sole source of numeric quantities on vector PDFs, and demote vision to a candidate-labeling role fed by annotated renders with structured-output responses keyed to geometry IDs. Route semantics to Sonnet 5 (current price/perf sweet spot at $2/$10 per MTok through Aug 2026), escalate to Opus 4.8 only for legend/schedule structuring and disagreement arbitration, and keep Haiku 4.5 for cheap classification. Model slugs verified July 2026.

## Current-State Analysis (what exists, what breaks)

| Layer | Module(s) | State | Gap for Phase 21 |
|---|---|---|---|
| Scale | `geometry_takeoff.resolve_scale`, `scale_extraction.py` | 3-tier: override > printed (rawdict stacked-fraction recovery + ladder snap) > dimension self-calibration (median of nearest-segment ratios, marked "low") | Self-calibration uses *nearest* segment per dim (no arrowhead/extension-line verification → wrong pairings → 1"=24' vs true 1"=20' on Crow). Frequency-based dominant scale picks detail-callout scales. No viewport segmentation beyond nearest-callout-anchor bucketing. |
| Geometry measurement | `geometry_takeoff.measure_geometry` | Whole-sheet total linework LF + density-trimmed bounding-box SF | No semantic segmentation: cannot say which linework is CMU wall vs gridline; footprint is a rectangle assumption (0.72–0.87× true area on irregular outlines) |
| Deterministic reads | `footprint_takeoff.py`, `schedule_extraction.py`, `plan_deterministic_legends.py` | Overall-dims footprint (proven 0.5% error); door schedule table parse; legend readers | Only two item classes covered; footprint assumes rectangle; schedule parser is door-specific |
| Vision pipeline | `takeoff_pipeline.py`, `claude_analyzer.py`, `sheet_pass_matrix.py` | Multi-pass (count/measure/schedule/legend), Haiku default + Sonnet routing, `COUNT_TILING=1` gated off, `ENABLE_VERIFY_RETRY` no-op | Vision estimates SF/LF/EA directly → 40%/8%/4% accuracy and 3× run-to-run variance; no grounding to geometry; retry stub |
| Human verification | `app.py` ~1329–1619, `takeoff_measurements.py` | Per-run JSON files (`verification_overrides.json`, `scale_calibration.json`, `takeoff_measurements.json`) | Dies with the run folder — no learning store, no retrieval |
| Persistence | `stackct_store.py`, `job_store.py` (`output/stackct.db`) | Projects/plans/sync_runs/job_runs, WAL-mode SQLite patterns | No corrections/vocabulary/assumption tables |
| Structure | 30 flat root modules, `app.py` 1,817 lines | Works; 348 deterministic tests green | Import graph is flat; StackCT path hardcodes `companion_present=False` (scraper.py:787); blueprints needed |

Failure taxonomy to design against (from `reports/vision_only/RESULTS.md` + CONTEXT): multi-scale sheets (detail callouts outnumber the main-plan scale), self-calibration mispairing, irregular footprint vs bounding box, vision SF non-reproducibility (397,500 vs 1,131,112 SF identical runs), tiled counting over/undercount (Columns 108 vs 132; Stairs 16 vs 10), partial schedule rows (3/5, 3/7), silent misses (tilt-up walls, gas piping), quantity duplication across similar items (WC-1 across WC-2..10).

## 1. Deterministic Geometry Take-off Engine (the core)

### PyMuPDF API surface (verified against official docs; PyMuPDF ≥1.24 already pinned; recommend bumping to ≥1.26 for table-finder and drawings fixes)

| Need | API | Notes |
|---|---|---|
| Vector paths | `page.get_drawings()` | Path dicts with `items` list: `("l", p1, p2)`, `("re", rect, orient)`, `("qu", quad)`, `("c", p1..p4)` Béziers; plus `stroke`/`fill` colors, `width` (stroke weight), `even_odd`, `closePath`. OCG/hidden-layer content IS included (see Pitfalls). `extended=True` adds clip/group hierarchy — useful for viewport detection via clip rects. |
| Words with boxes | `page.get_text("words")` | `(x0,y0,x1,y1, word, block, line, word_no)` — dimension-string harvesting |
| Char-level + rotation | `page.get_text("rawdict")` / `("dict")` | Per-char bboxes (stacked-fraction recovery — already used by `scale_extraction.py`); `line["dir"]` = (cos, sin) rotation for vertical dim strings (already used by `footprint_takeoff.py`) |
| Tables | `page.find_tables()` | Already used by `schedule_extraction.py`; generalize beyond doors (finish/fixture/equipment/window schedules, keynote legends) |
| Region-scoped extraction | `clip=fitz.Rect(...)` on `get_text`/`get_drawings` (via filtering) and `page.get_pixmap(clip=...)` | Viewport-scoped text/geometry; targeted crop renders for the vision verify-retry loop |

### Recommended libraries

| Library | Version | Purpose | Why |
|---|---|---|---|
| `shapely` | ≥2.0 (2.x has vectorized ops, `shapely.polygonize`, STRtree) | Room polygon closure, area/length math with holes, buffering, STRtree spatial index | The standard; polygonize a noded line network into faces = room polygons; `Polygon(shell, holes).area` handles atriums/openings exactly (irregular-footprint fix) |
| `networkx` | ≥3.2 | Wall-segment connectivity graph, connected components for symbol clustering | Pure-Python, no build issues; components over a "segments within ε" adjacency = drawing clusters |
| `numpy` | ≥1.26 | Vectorized segment math, RANSAC-style regression | Already transitively present via Pillow workflows; makes 68k-segment sheets fast |
| (optional) `scipy` | skip | KD-tree could help but `shapely.STRtree` covers spatial queries | avoid extra dependency |

Pure Python is fine for parsing/association logic; use shapely/numpy for the O(n²)-flavored geometry (nearest-line queries over 68k segments need STRtree or grid hashing, not brute force — the current `_calibrate_from_dimensions` is brute-force O(dims×segs) and slow/wrong).

### Recipe A — Dimension-line association (the highest-value single component)

Architectural dimensions have a rigid graphical grammar: a **dimension line** (long segment parallel to the measured direction), two **terminators** (arrowheads = tiny 2–3-segment chevrons, or tick slashes = short 45° segments) at its ends, two **extension/witness lines** perpendicular at each end, and the **text** centered on/above the line (rotated with `line["dir"]` matching the dimension direction).

Algorithm (all in PDF points):
1. Harvest dimension strings from `get_text("rawdict")` lines: regex for feet-inch tokens including fractions — `(\d+)'\s*-?\s*(\d+)?\s*(?:(\d+)/(\d+))?"?` plus stacked-fraction recovery reusing `scale_extraction._paper_inches_from_chars` logic (numerator/denominator split by char y). Record text center, bbox, rotation vector `dir`.
2. Index all straight segments in an STRtree. For each dim string, search a corridor: segments whose direction matches the text rotation (within ~3°), whose midpoint lies within ~2–15 pt of the text bbox on the perpendicular axis, and which are the *longest* such candidate (dimension lines run the full measured span; stroke width is typically thin and consistent).
3. Verify terminators: at each end of the candidate segment, look for a cluster of ≥2 short segments (< 6 pt) within ~4 pt (arrowhead/tick), and/or a perpendicular extension line crossing near the endpoint. Require at least one verification signal; score the pair.
4. Emit `DimensionSample(feet, points, text_bbox, line_bbox, rotation, score)`.

This replaces "nearest aligned segment" with "grammar-verified pairing" — the root fix for the 1"=24' mispairing. Chained dimension strings (a row of bay dims along one line) each pair with their own sub-segment between consecutive extension lines; if sub-segmentation is ambiguous, drop the sample rather than guess (plenty of samples remain).

Parsing formats to support (unit tests): `1136' - 0"`, `350'-0`, `25'-4 1/2"`, `3'-0"`, stacked `1'-6¹/₂"` variants, bare `60'`, metric absent (US fixtures). Reject elevations/GL/INV (existing ACCURACY-08 rule), slopes, and tags.

### Recipe B — Wall segment extraction (parallel-pair detection)

Walls in CAD PDFs are drawn as two parallel lines at wall-thickness distance (typically 4"–12" real ≈ scale-dependent points), often with fill or hatch between.
1. Filter segments: stroke-drawn, length ≥ 2 ft-equivalent, group by angle (quantize to 1°).
2. Within an angle group, sort by perpendicular offset; pair segments whose offset differs by a plausible wall thickness (after scale solve: 3"–16" real) and whose projections overlap ≥70%.
3. Merge collinear chains (gap ≤ door-width tolerance — openings break wall lines; record gaps as opening candidates).
4. Output `WallSegment(centerline, length_ft, thickness_ft, angle)`; sum by thickness class → LF per wall type. Wall SF = LF × height (height from learning store / schedule / wall-type legend; flag if assumed).
Vision's role: label which thickness class is "CMU" vs "tilt-up" vs "stud partition" (from the wall-type legend/hatch pattern), never the LF number. This is the CMU 17 vs 2,204 SF fix.

### Recipe C — Room polygon closure

1. Take wall centerlines + door-opening gap closures, node the network (`shapely.node`/`unary_union` of lines), run `shapely.polygonize` (via `shapely.ops.polygonize` or `shapely.polygonize` in 2.x) → candidate faces.
2. Discard faces outside the main-plan viewport, tiny slivers (< 10 SF), and the exterior face.
3. Bind room names: `get_text("words")` room labels ("OFFICE", "WAREHOUSE", numbers) that fall inside a face — deterministic text-in-polygon, vision only as fallback for ambiguous label placement.
4. Floor/ceiling SF per room = polygon area (holes respected). Building footprint = union of exterior wall polygon — replaces the rectangular assumption and the 0.72–0.87× trimmed-extent error; cross-check against the overall-dims footprint (both deterministic, should agree ≤2%; disagreement flags review).

### Recipe D — Symbol instance clustering (countable EA items)

Repeated CAD blocks (bollards, columns, fixtures, sprinkler heads) are byte-identical geometry clusters repeated at translations (sometimes rotations/mirrors).
1. Cluster primitives into connected components: spatial grid hash (cell ≈ 2–5 pt); union segments/curves whose endpoints are within ε. `networkx` connected components or union-find.
2. Compute a **normalized shape signature** per cluster: translate to centroid-origin, scale-preserve, build a multiset of `(item_type, quantized_dx, quantized_dy, quantized_len, quantized_angle)` tuples, hash it. For rotation/mirror invariance, hash the 8 dihedral transforms and take the min (cheap geometric hashing — same idea as Kreo Auto Count's "allow rotation and flipping").
3. Group clusters by hash → instance groups with counts and locations. Filter: instance count ≥ 3, bbox between ~0.5 ft and ~15 ft equivalent (excludes text glyph boxes and whole-building outlines), exclude clusters inside schedule/legend/title-block regions.
4. Hand each group's representative crop(s) to vision for labeling (§3). Count = deterministic group size; the "columns 90 vs 132" class of failure becomes exact because every grid intersection block instance is enumerated, not eye-counted.
Caveats: some plans explode blocks inconsistently (hatch variations); near-duplicate hashes should be merged by signature distance (tolerance quantization ~0.5 pt). Text-labeled symbols (e.g. door tags) can be split by contained text — Kreo's "Split by Text" pattern — using text-in-cluster-bbox lookup.

### Recipe E — Length/area math

All trivial once segments/polygons are associated: polyline LF = Σ segment lengths × ft/pt; Bézier curves flattened via sampling (PyMuPDF gives control points; flatten at 0.5 pt chordal tolerance) for curved walls/arcs. Keep every quantity in points until the per-viewport scale is bound, mirroring the existing `RawGeometry` rescale pattern.

### How professional tools do it (verification, MEDIUM confidence — vendor docs + industry guides)

- **Vector-first when possible**: "For vector PDFs the geometry is already encoded, so the system reads line weights, layer data, and annotation text rather than inferring them from pixels" (2026 GC guide). Kreo explicitly "reads native PDF and CAD vector data (not rasterized images)".
- **Reference-based Auto Count**: user picks one symbol; engine finds all similar with rotation/flip options, similarity slider, search-area restriction, split-by-text. Our Recipe D automates the "pick one" step via clustering + vision labeling.
- **Auto viewport/boundary detection**: Kreo "Auto Measure and Auto Count now detect drawing boundaries" — validates our per-viewport segmentation direction.
- **Scale verification is non-negotiable**: every guide says to validate auto-scale against a known dimension. Our design goes further: scale is *derived* from many known dimensions (Recipe A), and printed notation becomes the cross-check.
- Even the best tools position AI output as human-reviewed. Our honest framing (completeness + flagged subset) matches industry reality; "flagged approaches zero on vector CAD" is the differentiator target.

## 2. Zero-Calibration Scale Solving (V3-ACC-02)

### Per-viewport segmentation

Viewports on a sheet = the main plan + detail callouts + title block + legends. Detection signals, in priority order:
1. **Clip rectangles**: `page.get_drawings(extended=True)` exposes clip paths; CAD exporters often clip each viewport — when present this is authoritative.
2. **Title-text anchors**: detail titles follow the "N / SCALE: x" pattern under a drawing; `extract_scale_callouts()` already yields positioned callout anchors. A viewport region = the geometry mass above/near its title anchor, bounded by whitespace gutters.
3. **Whitespace gutters + geometry density**: project segment density onto x/y axes; low-density bands separate viewports (works when no clips). Also: border rectangles (details are often boxed) and detail-bubble circles (circle with section number) are direct region markers.
4. Fall back to current nearest-anchor bucketing only when 1–3 all fail.
The title block region (bottom/right strip with dense small text) and legend/schedule regions (from `find_tables()` bboxes) must be masked out of all measurement.

### Solving feet-per-point per viewport

With N `DimensionSample`s inside a viewport (N is typically 20–200 on a floor plan):
- Each sample is a ratio `r_i = feet_i / points_i`. The estimator must resist mispairings and detail-dim contamination.
- **Recommended: RANSAC-style consensus** — for k iterations sample one `r_i`, count inliers within ±2% relative; take the largest consensus set, return its median. Simpler and equally robust: mode of `log(r_i)` histogram at 2% bin width, then median of the mode bin. Since all valid `r_i` are identical up to noise, this is a 1-parameter fit; full regression is unnecessary.
- **Snap to the ladder** (`scale_extraction.snap_fpi`) *only as a cross-check*: report both the solved value and the snapped value; if they differ >2%, prefer the solved value but flag (some site plans use non-ladder scales, e.g. 1"=25').
- **Cross-validation** (each adds/subtracts confidence): printed scale callout inside the viewport; door openings — the gap-in-wall candidates from Recipe B should cluster at 3'-0" (±2"); grid bubbles spacing vs printed grid dims; overall-dims footprint vs polygon footprint agreement.
- **Confidence scoring**: HIGH = ≥8 inlier dims, inlier share ≥80%, agrees with printed scale (snapped) within 1%; MEDIUM = ≥4 inliers or printed-scale agreement only; LOW = <4 inliers or conflicts. Persist per-viewport `{fpp, n_inliers, share, printed_agreement, door_check}` in the report for the UI.
- **Main-plan selection**: the viewport with the largest *real* area after its own scale is applied AND containing floor-plan text labels. This fixes "frequency picks detail scales" — detail callouts are many but tiny in real terms.

Crow acceptance test: solved main-plan scale must land at 1"=20' (±2%), not 24' — and the fixtures give a known-truth harness (dimension strings are on the sheet; the golden footprint pins the answer).

### Raster-only fallback

When `get_drawings()` returns trivial geometry and there's no text layer (scanned plans): skip the deterministic engine entirely, mark `measurement_mode="raster"`, use the vision ensemble path (§4) with printed-scale OCR + explicit low confidence, and flag all measured quantities. Do not attempt pixel-level CV wall detection in this phase (out of scope, research-grade). Detection heuristic: < 200 drawing items AND < 100 words on a plan-classified sheet.

## 3. Vision + Geometry Fusion Protocol (V3-ACC-01, V3-ACC-05)

Principle: **geometry proposes, vision disposes.** Vision never sees a raw sheet and free-associates quantities; it sees *candidates with IDs* and returns *labels for IDs*.

### Handoff patterns (in order of use)

1. **Annotated overlay render** ("Set-of-Mark" prompting): rasterize the sheet at working DPI, draw numbered markers/boxes on each candidate (viewport regions, symbol-group representatives, wall-thickness classes color-coded, room polygons tinted). Ask: "Region 3 is the main floor plan? Which wall class (A=red, B=blue) is CMU per the wall legend?" Model answers with IDs only. PyMuPDF or Pillow draws the overlay; keep marker density ≤ ~40 per image, else split into multiple queries.
2. **Crop galleries for symbol groups**: render each symbol group's representative instance (plus 1–2 more members) as small crops on a contact sheet with IDs + the sheet's legend crop alongside. Ask: "Match each symbol ID to a legend item or 'unknown'." One call labels every countable group on a sheet. Multiple images per request are fine (≤20 keeps the relaxed 8000px per-image limit; >20 images triggers the 2000px per-image cap — verified in vision docs).
3. **Targeted crop verify-retry** (replaces the `ENABLE_VERIFY_RETRY` stub): when QuantityVerifier flags an out-of-band value or ensemble disagreement, render a `clip=` crop around the specific geometry at high DPI and re-ask a narrow question ("does this show a ladder or a stair?"). Bounded: ≤2 retries per item, budget-guarded.
4. **Legend/schedule structuring**: crop the legend/table region; ask for structured rows. Quantities in those rows come from `find_tables()` text when available — vision only reconciles layout when the table finder fails.

### Structured outputs (verified July 2026)

Anthropic now has GA structured outputs: `output_config.format = {type: "json_schema", schema: {...}}` (Python SDK convenience: `client.messages.parse(output_format=...)`), plus `strict: true` tool use with grammar-constrained sampling. Requirements: `additionalProperties: false` everywhere, all properties in `required`. Use enums of candidate IDs in the schema (e.g. `"region_id": {"enum": ["R1","R2","R3"]}`) so the model *cannot* answer outside the candidate set — this is the strongest possible grounding. Beta header `structured-outputs-2025-11-13` is no longer needed on the GA path. (Source: platform.claude.com structured-outputs docs, HIGH confidence.)

### Grounding answers back to geometry

Every candidate carries its PDF-point bbox in our own registry keyed by ID; the model only ever returns IDs + labels + optional confidence. Never ask the model for coordinates (vision-model pixel coordinates are unreliable and unnecessary here). Rendered-pixel ↔ PDF-point mapping is the existing `page_width_pt`/zoom bookkeeping.

### Keeping vision away from numbers

Prompt-level rule plus schema-level enforcement: extraction schemas for vector sheets have **no numeric quantity fields** except `count_estimate` on the raster fallback path. Merge logic (`merge_passes`) must prefer deterministic sources by construction: quantity provenance enum `{geometry, text_layer, schedule_table, learned, vision_ensemble}` on every item; reporter surfaces provenance; the accuracy gate asserts vision-provenance quantities ≈ 0 on the vector fixtures.

## 4. Ensemble / Self-Consistency for Residual Vision Numbers (V3-ACC-03)

Scope: raster-only PDFs, ambiguous symbols the clusterer can't isolate, and semantic label disagreements. NOT for anything geometry/text can answer.

- **N-sample voting**: N=3 default, N=5 when the first 3 disagree. Temperature 0.4–0.7 for diversity (identical t=0 runs can repeat the same error; note newer Anthropic reasoning models may ignore/limit temperature — verify per model at implementation, LOW confidence detail). Vote per item: EA counts → median; if max−min ≤ max(1, 10% of median) → accept with HIGH/MEDIUM; else needs_review. SF/LF (raster path only) → median, accept only if spread ≤10%, else flag. This directly kills the 397k-vs-1.13M variance failure: disagreement can no longer silently pass through.
- **Tiled counting integration**: activate tiling (existing `COUNT_TILING=1` machinery) when symbol density is high (heuristic: >50 expected instances or sheet renders above the legibility threshold). Tiles overlap 15–20%; each tile's counts come with approximate cell positions; dedup by suppressing detections within the overlap band that appear in both tiles (position-based NMS at tile granularity — even coarse "grid-cell" positions from the model suffice). Tiled result becomes one ensemble member, not the sole answer — voting reconciles it with whole-sheet counts (fixes Stairs 10→16 overcount).
- **Agreement→confidence mapping**: unanimous → high; majority within tolerance → medium; no majority → low + needs_review. Persist per-item vote vectors in the report for auditability.
- **Cost model** (verified pricing, July 2026): a 1568-px-long-edge image ≈ 1.1–1.6k tokens. Whole-sheet pass on Sonnet 5 ≈ $0.01–0.02 in; ~1–2k out ≈ $0.01–0.02. N=3 ensemble on a 30-sheet raster set ≈ 90 calls ≈ $2–4 — acceptable; guard with a per-run budget (V3-PROD-02). Prompt caching: put the (long, stable) extraction instructions in a cached system block — 90% discount on cache hits ($0.20/MTok cache-hit on Sonnet 5 vs $2 base); images themselves don't cache across differing sheets. Batch API gives 50% off and fits the ensemble fan-out (all N samples of all sheets submitted as one batch in the two-phase pipeline where the browser is already closed); worth adopting for the analyze phase since it's already asynchronous.

## 5. Anthropic Model Line-up & Routing (V3-ACC-04) — verified July 2026

Available vision-capable API models (all support image input; source: platform.claude.com models overview + pricing, HIGH confidence):

| Model | API ID | $/MTok in/out | Context | Notes |
|---|---|---|---|---|
| Claude Fable 5 | `claude-fable-5` | $10 / $50 | 1M | Frontier; overkill for per-sheet extraction |
| Claude Opus 4.8 | `claude-opus-4-8` | $5 / $25 | 1M | High-res vision class (2576px long edge before downscale vs 1568 standard — MEDIUM confidence detail); best for dense tables/legends |
| Claude Sonnet 5 | `claude-sonnet-5` | $2 / $10 (intro through Aug 31 2026; then $3/$15) | 1M | Default workhorse; effort levels available |
| Claude Haiku 4.5 | `claude-haiku-4-5` (`claude-haiku-4-5-20251001`) | $1 / $5 | 200k | Classification, cheap ensemble members |

Image/API constraints (verified): 8000×8000 px max per image, 10 MB base64 on the direct API (the current 3.6 MB clamp can be relaxed), ≤20 images per request to keep full resolution (>20 → 2000px cap), model downscales long edge to ~1568px (standard) / ~2576px (high-res models). Practical consequence: **the current 7900px render clamp wastes tokens/quality** — render at DPI targeting ≈1568px long edge for whole-sheet semantic passes, and use *crops/tiles at native detail* instead of giant whole-sheet images when legibility matters (adaptive fidelity = zoom via clip crops, not bigger full-page rasters).

Recommended routing (config-driven replacement for MODEL_ROUTING; accuracy-first per user authorization):

| (sheet_type, pass) | Model | Rationale |
|---|---|---|
| classify (all) | Haiku 4.5 | trivial |
| semantic labeling (floor/roof/MEP plans — overlay + crop galleries) | Sonnet 5 | main workhorse |
| legend/schedule structuring; wall-legend interpretation | Opus 4.8 | dense small text, high-res vision class; fixes partial schedule rows |
| verify-retry arbitration crops | Opus 4.8 | one-shot decisive answers |
| raster-fallback ensemble members | Sonnet 5 ×2 + Haiku 4.5 ×1 | diversity + cost |
| escalation on repeated disagreement | Fable 5 (budget-gated, off by default) | last resort |

Keep slugs in `config.py`/env (`CLAUDE_MODEL_*`), never hardcoded (user decision). Update the `PRICING` dict with the July 2026 table above; note Sonnet 5's price change on Sep 1, 2026.

## 6. Learning Store Design (V3-LEARN-01..04)

### Schema (extend `output/stackct.db` — one DB keeps ops simple; a `learning_` table prefix isolates it; dedicated `learning.db` is fine too if migration risk is a concern — Claude's discretion per CONTEXT)

```sql
-- every human action, append-only (audit + decay computation)
CREATE TABLE learning_corrections (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  run_id TEXT NOT NULL,               -- surviving reference even after run folder deletion
  project_key TEXT NOT NULL,          -- normalized project name / stackct id
  project_type TEXT,                  -- industrial / hotel / retail ... (existing detector)
  sheet_type TEXT,                    -- floor_plan / schedule / ...
  scope TEXT NOT NULL,                -- 'item' | 'scale' | 'wall_height' | 'name' | 'missed_item' | 'unit'
  item_pattern TEXT,                  -- normalized item key (lowercased canonical-ish name)
  original_value TEXT,                -- JSON: what the system said
  corrected_value TEXT NOT NULL,      -- JSON: what the human said
  context TEXT                        -- JSON: page, viewport, provenance, confidence at time of correction
);
CREATE INDEX ix_corr_lookup ON learning_corrections(project_type, sheet_type, scope, item_pattern);

-- distilled, retrievable state (rebuilt/updated from corrections)
CREATE TABLE learning_vocabulary (
  id INTEGER PRIMARY KEY,
  project_type TEXT,                  -- NULL = global
  raw_pattern TEXT NOT NULL,          -- what extraction produces (regex-safe literal or token set)
  canonical_name TEXT NOT NULL,
  unit TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,   -- votes; incremented per confirming correction
  last_seen TEXT NOT NULL,
  UNIQUE(project_type, raw_pattern)
);

CREATE TABLE learning_assumptions (   -- wall heights, waste factors, default scales...
  id INTEGER PRIMARY KEY,
  project_key TEXT,                   -- exact project beats project_type beats global
  project_type TEXT,
  key TEXT NOT NULL,                  -- 'wall_height_ft', 'scale_fpi:sheetname-pattern', ...
  value TEXT NOT NULL,                -- JSON
  weight REAL NOT NULL DEFAULT 1.0,
  last_seen TEXT NOT NULL
);

CREATE TABLE learning_manifests (     -- auto-generated expected-item checklists
  id INTEGER PRIMARY KEY,
  project_type TEXT NOT NULL,
  item_name TEXT NOT NULL,
  unit TEXT NOT NULL,
  seen_in_runs INTEGER NOT NULL DEFAULT 1,   -- how many verified runs contained it
  verified_runs_total INTEGER NOT NULL,      -- denominator for expectation strength
  UNIQUE(project_type, item_name)
);
```

### Retrieval + injection

At run start, one query bundle keyed by `(project_key, project_type)` produces a `LearnedContext` object injected at three points:
1. **Prompts**: a short "expected items for this project type" + "known naming conventions" block (from `learning_manifests` + `learning_vocabulary`) — a *hint*, appended to the semantic-pass prompt (cached system block).
2. **Aggregation**: `learning_vocabulary` rows are consulted *before* `ITEM_NAME_MAP` (exact/normalized match first, then the static regex list as fallback). Over time the learned table supersedes the static map (V3-LEARN-02); never delete ITEM_NAME_MAP — it's the cold-start floor.
3. **Calculator**: `learning_assumptions` supplies wall heights, waste-factor overrides, and per-sheet scale priors (a scale prior is a *cross-check*, never overriding a HIGH-confidence solved scale — see guardrail below).

### Capture surface rewiring

`app.py` verify/scale endpoints currently write per-run JSON; they must additionally INSERT into `learning_corrections` and update the distilled tables in the same transaction. A `learning/distill.py` job (idempotent, re-runnable from the append-only log) computes vocabulary/assumption/manifest rows — so the distilled state can always be rebuilt.

### Conflict/decay policy

- Confidence-weighted votes: each confirming correction +1 weight; a *contradicting* correction (same key, different value) decays the old row (weight × 0.5) and inserts/boosts the new one. Retrieval takes the max-weight row; ties → most recent.
- Specificity precedence: exact `project_key` > `project_type` > global.
- Staleness: `last_seen` older than N verified runs → weight decays at distill time.
- **Anti-amplification guardrail (critical, per CONTEXT)**: learned values may adjust *semantics* (names, units, expected items, assumptions with no deterministic source) but must NEVER override a quantity whose provenance is `geometry`/`text_layer` with HIGH confidence. A learned scale/height only applies when the deterministic solver returned MEDIUM/LOW/none. This keeps learning from becoming a hidden manifest dependency for correctness (V3-LEARN-04) and prevents a bad correction from silently poisoning future geometry-derived numbers. Learned quantity corrections apply only as *flags* ("human previously corrected this item on this project — re-verify") rather than silent substitutions, except for the exact same `(project_key, run-identical inputs)` re-run case.

## 7. Package Restructure (V3-STRUCT-01..02)

### Layout

```
src/bobbytailor/
├── __init__.py
├── config.py                # moved as-is
├── pipeline/                # takeoff_pipeline, sheet_pass_matrix, calculator, aggregator, reporter, cross_references
├── vision/                  # claude_analyzer (prompts/, client, ensemble.py, fusion.py)
├── deterministic/           # geometry_takeoff, scale_extraction, scale_utils, scale_recalc,
│                            # footprint_takeoff, schedule_extraction, plan_deterministic_legends,
│                            # + NEW: dimensions.py, viewports.py, walls.py, rooms.py, symbols.py
├── learning/                # store.py, distill.py, retrieval.py
├── scrape/                  # scraper, browser, stackct_sync, sheet_preview, capture_manifest, linked_sheets
├── stores/                  # stackct_store, job_store, project_cache
├── devtools/                # companion_takeoff, object_manifest (demoted optional inputs)
└── web/                     # Flask app factory + blueprints/
    ├── app.py               # create_app()
    └── blueprints/          # auth.py, projects.py, runs.py, reports.py, verify.py, settings.py, jobs.py
```

### Migration strategy: import shims, not big-bang

1. `git mv` every module into its package home in ONE commit (git tracks renames by content; history follows with `git log --follow`). Do not edit content in the move commit.
2. Add a root-level shim per old module name for the transition: `geometry_takeoff.py` containing `from bobbytailor.deterministic.geometry_takeoff import *  # noqa` (plus explicit re-exports for names `import *` misses, e.g. private helpers tests import). This keeps all 40 test modules and any stray scripts green immediately.
3. Convert internals to absolute package imports; then migrate tests to package imports in batches; finally delete shims in a closing plan. Add `pyproject.toml` with `[tool.setuptools] package-dir = {"" = "src"}` (or hatchling) and `pip install -e .` so `pytest` resolves the package without sys.path hacks; keep a `conftest.py` fallback path insert during transition.
4. **app.py split**: extract the app factory first (`create_app()` registering blueprints), move route groups one blueprint at a time, keeping the in-memory `jobs` dict and Playwright thread-launch code in a single `web/jobs_runtime.py` owned module — background threads must not import through Flask's app context (existing known pitfall: primitive payloads only in job threads). The `main.py` entry point becomes `app = create_app()` for gunicorn parity.
5. Risks: circular imports currently hidden by lazy `from x import y` inside functions (geometry_takeoff ↔ scale_recalc pattern) — preserve lazy imports during the move, untangle later; `scripts/` invoke root modules by path — update to `python -m bobbytailor...` or keep shims until scripts are migrated; Playwright browser threads hold module references — a restart is required on deploy, no hot-reload of moved modules.

### Entry-point parity (V3-STRUCT-02)

Both `pdf_analyzer` and `scraper` already defer to `TakeoffPipeline`. Parity work: remove `companion_present=False` hardcode (scraper.py:787); route StackCT per-page blob PDFs (which are vector) through the *same* deterministic engine (StackCT path currently rasterizes to screenshots — it must ALSO fetch/keep the per-page PDF blobs for geometry); one shared `RunSettings` dataclass (deterministic flags, ensemble N, learning retrieval on/off) constructed identically by both entry points; extend `test_pipeline_parity.py` to assert the deterministic + learning call-sites fire on both paths.

## 8. Validation Architecture

Layered so every layer is testable without API credits (only layer 5 spends money):

1. **Geometry engine (pure unit tests, free)**: run dimensions/walls/rooms/symbols extractors against the four fixture PDFs (`tests/fixtures/{crow_cass,bobs_discount,moxy,chelsea}`); assert known truths — Crow overall dims 1136'×350' found and associated; dimension-sample inlier scale = 20 ft/in ±2%; door-opening gap widths cluster at 3'; symbol clusterer finds a group of ≥28 identical bollard-scale clusters and ≥132 column-grid clusters on the right sheets (counts pinned from goldens); synthetic-PDF fixtures (generated with PyMuPDF `Shape` drawing — walls/dims/symbols with known ground truth) for edge cases (curved walls, rotated text, chained dims), extending the existing 99/99 synthetic-generalization pattern.
2. **Scale solver (known-truth fixtures, free)**: per-viewport solve on each fixture sheet vs a hand-recorded truth table (`tests/fixtures/*/scale_truth.json`: page → viewport → fpi). Gate: main-plan viewport correct on 100% of truth-table sheets; no HIGH-confidence wrong scales (a HIGH-confidence wrong answer is the worst failure class).
3. **Fusion layer (recorded vision responses, free)**: record real Claude structured-output responses once (fixture JSON per prompt hash — extend the existing `{page_id}_analysis.json` cache pattern into a proper record/replay analyzer injected via `TakeoffPipeline(analyzer=...)`); tests assert merge behavior, provenance rules (vision never overwrites geometry quantities), ID-grounding round-trips, and verify-retry triggering logic.
4. **Learning store (free)**: correction → distill → retrieval round-trip tests; conflict/decay; anti-amplification guardrail (learned value must NOT displace HIGH-confidence geometry quantity); repeat-run application test (same project second run picks up vocabulary).
5. **End-to-end accuracy gate (API, budget-guarded)**: `scripts/vision_only_benchmark.py` as the CI-invocable gate (V3-PROD-01) with new assertions: per-provenance accuracy split — geometry/text-layer-derived quantities ≥97% vs golden on Crow+Bob; overall quantity accuracy ≥90%; item-found ≥95%; zero silent misses (every golden category present or flagged); reproducibility — two runs within ±5% per item (run the ensemble path twice on one fixture). "≥97% geometry-derived" concretely requires: correct main-plan scale (layer 2 gate), footprint via room-polygon union or overall-dims (both deterministic), wall LF from parallel-pair extraction bound to the right wall class, and schedule/legend quantities read via `find_tables()` — i.e., layers 1–3 all green; the E2E gate then only certifies integration, and failures point at a specific layer.

Also: cost regression check (per-run cost recorded; gate warns if >2× baseline) and a raster-fallback smoke test (rasterized copy of a fixture page → ensemble path → everything flagged, nothing silently missed).

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| Polygon math (area w/ holes, buffering, point-in-polygon, nearest) | custom computational geometry | `shapely` ≥2.0 | edge cases (self-intersection, precision) are brutal |
| Line-network → faces | custom face tracing | `shapely.ops.polygonize` (+`unary_union` noding) | exactly this job |
| Spatial nearest-segment queries at 68k scale | brute-force O(n²) loops | `shapely.STRtree` | current calibration loop is the slow/wrong version |
| Connected components / union-find | ad-hoc clustering | `networkx` or 30-line union-find | fine either way, but don't re-derive per module |
| JSON schema enforcement of vision output | prompt-begging + regex repair | Anthropic structured outputs (`output_config.format`, strict tools) | grammar-constrained sampling, GA |
| Table extraction | custom row/col inference | `page.find_tables()` (already proven in schedule_extraction) | generalize the door pattern, don't fork it |
| DB migrations | ad-hoc ALTERs | the existing schema-version pattern in `stackct_store.py` (v1→v2 precedent) | consistency |

**Key insight:** every hand-rolled geometry or parsing shortcut in this domain eventually meets a drawing that breaks it; the deterministic engine's credibility rests on boring, well-tested primitives plus *rejecting* what it can't verify (the ladder-snap philosophy already in `scale_extraction.py`).

## Common Pitfalls

### 1. Over-trusting geometry without semantics
Total linework LF is meaningless (gridlines, hatches, leaders). Every measured quantity must pass through a semantic binding (wall class, room label, symbol label) before becoming a take-off line; unbound geometry is reported as coverage stats, not quantities.

### 2. Hatch/fill patterns inflating drawings
Hatched regions explode into thousands of tiny parallel segments; they'll dominate segment counts, poison wall-pair detection and clustering. Filter early: drop segments shorter than ~0.5 ft-equivalent from wall detection; detect hatch fields (dense same-angle same-spacing groups) and collapse them to their boundary. Hatch *patterns are also signals* (CMU hatch vs concrete hatch) — keep the collapsed hatch-class per region for vision labeling.

### 3. OCG layers / xrefs / hidden content
`get_drawings()` returns content on hidden optional-content layers. Check `doc.get_ocgs()`/`doc.layer_ui_configs()` and exclude paths under OFF layers; demolition/alternate layers otherwise double geometry. Same for text: hidden-layer dims can contaminate scale solving.

### 4. Rotated/vertical text
Vertical dimension strings arrive with `line["dir"] = (0, ±1)`; per-char x/y ordering flips. `footprint_takeoff._axis_dims` handles the axis split; the new dimension-association must transform char order and corridor geometry by the rotation. Also handle 180° (upside-down dims on the far side of a plan).

### 5. Multi-scale contamination in the solver
A viewport boundary error leaks detail dims into the main-plan sample set. RANSAC tolerates ≤40–50% contamination; keep the inlier-share confidence input so a near-split vote lands MEDIUM, not HIGH-wrong.

### 6. Curved/arc walls
Bézier ("c") items must be flattened for length and included in wall pairing (arc pairs at constant offset). If skipped silently, curved buildings under-measure — flag sheets where curve length ≥5% of linework as needing curve support verification.

### 7. Ensemble cost explosion
N×tiles×retries multiplies fast. Hard per-run budget guard (V3-PROD-02) enforced in the pipeline (abort→flag remaining as needs_review, never silent partial); Batch API for the fan-out; cache system prompts.

### 8. Learning-store feedback amplification
A wrong human correction (typo: 2,204 → 22,040) becomes a learned "truth". Mitigations: anti-amplification guardrail (§6), plausibility bounds (reuse QuantityVerifier rules on corrections at capture time — warn the human), append-only log so any distilled state is auditable/rebuildable.

### 9. Restructure breaking background jobs
Playwright threads + module-level singletons (`_pipeline` in scraper) + Flask app context: move code without changing thread/context patterns; blueprints must not capture app-context objects into job threads (primitive payloads only — existing decision). Run the full test suite + a manual StackCT and PDF job between move waves.

### 10. Schedule counts ≠ installed counts
Door schedules list types/openings, not per-instance guest-room repeats (hotel fixture: WC-1 duplication bug is the same class). Keep schedule counts as exact lower bounds / type breakdowns; instance counts come from plan-body symbol clustering; reconcile and flag residuals (already documented in `schedule_extraction.py` docstring — preserve that honesty).

### 11. Blind trust in printed scale
Printed scale can be wrong ("NTS", half-size prints, mislabeled details). Dimension-solved scale is primary (it survives half-size printing because both dims and geometry shrink together — printed notation does not). This ordering (solved > printed > learned prior) must be explicit in the new resolve_scale v2.

## Open Questions

1. **StackCT per-page vector PDFs** — the brief says StackCT downloads per-page blob PDFs (vector). Verify in `scraper.py`/network capture that blobs are retained (not just screenshots) and are truly vector for real projects; if some are raster-only exports, the parity path needs the raster fallback more often than the PDF-upload path. Recommendation: make blob retention a Phase 21 task with a runtime vector/raster probe.
2. **Anthropic high-res vision tier details** — the 2576px long-edge claim for Opus-class models comes from the vision docs snapshot (MEDIUM); confirm exact per-model resolution behavior and visual-token multipliers at implementation time against platform.claude.com/docs vision page before tuning render DPI.
3. **Temperature on current models** — whether Sonnet 5/Opus 4.8 honor `temperature` for sampling diversity in ensemble mode (adaptive-thinking models sometimes restrict it). If not honored, achieve diversity via prompt variation (ordering, tile offsets) instead. LOW confidence; test with 3 calls at implementation start.
4. **Wall height source when no schedule/legend states it** — learning store fills over time, but the cold-start default (current blanket 9 ft) remains an assumption; keep flagged. Not resolvable by research — it's a genuinely non-plan datum on some sets.
5. **Chelsea/Moxy goldens as secondary gates** — Moxy's 4% baseline and hotel repetition (schedule-vs-instance) make it the hardest fixture; recommend keeping Crow+Bob as the hard gate (per success criteria) and Moxy as a tracked-not-gating metric this phase.

## Sources

### Primary (HIGH confidence)
- Codebase: `geometry_takeoff.py`, `scale_extraction.py`, `footprint_takeoff.py`, `schedule_extraction.py`, `sheet_pass_matrix.py`, `takeoff_pipeline.py` (verify stub 229–234), `aggregator.py` ITEM_NAME_MAP, `requirements.txt`, `reports/vision_only/RESULTS.md`, `21-CONTEXT.md`
- platform.claude.com — Models overview (API IDs, context, pricing incl. Sonnet 5 intro pricing), Pricing (cache-write/hit rates), Vision (8000px, 10MB, 20-image threshold → 2000px cap, ~1568px downscale, Files API), Structured outputs GA (`output_config.format`, strict tools, `additionalProperties: false`)
- PyMuPDF official docs — `get_drawings()` path dict schema (`l`/`re`/`qu`/`c` items, stroke/fill/width), Shape round-trip recipe

### Secondary (MEDIUM confidence)
- Kreo help docs — Auto Count (reference matching, rotation/flip, similarity slider, split-by-text, search areas), Auto Measure 2.0 (rooms/walls/doors/GIA), "reads native PDF and CAD vector data", auto drawing-boundary detection
- Struvia 2026 GC guide — vector-vs-raster pipeline description, scale-verification discipline, tool landscape (STACK/Togal/Bluebeam/PlanSwift)
- ryant.io vector symbol counting write-up — geometric-predicate detection over `get_drawings()`, NMS dedup, vectors-beat-pixels argument (matches our Recipe D)
- Anthropic API guides (developersdigest, stacknotice) — 1568px preferred render target, prompt caching mechanics, Batch API 50% discount, tool-use-schema-over-prose for structured extraction

### Tertiary (LOW confidence — flagged for validation)
- Opus-class 2576px high-res vision limit (single doc snapshot)
- Temperature behavior on adaptive-thinking models in ensemble use
- VecFormer/CADSpotting (arXiv 2505.23395) — research-grade symbol spotting; cited as context only, explicitly NOT recommended for this phase (custom ML out of scope)

## Metadata

**Confidence breakdown:**
- Standard stack (PyMuPDF/shapely/networkx, Anthropic APIs): HIGH — official docs verified this week
- Architecture (dimension graph, viewport solve, fusion protocol): MEDIUM-HIGH — grounded in proven in-repo patterns (footprint, schedule, scale ladder) + commercial-tool corroboration; the dimension-association and symbol-hash recipes are engineering designs, not copied implementations, so fixture-driven layer-1 tests are the real validation
- Pitfalls: HIGH — most are already-observed failures in this repo's own benchmark reports
- Ensemble parameters (N, temperatures, thresholds): MEDIUM — start values, tune against the reproducibility gate

**Research date:** 2026-07-13
**Valid until:** ~2026-08-15 (Anthropic pricing/models move fast; Sonnet 5 price change lands 2026-09-01 — update PRICING then)
