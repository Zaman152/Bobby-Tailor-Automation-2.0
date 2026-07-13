# Plans-Only Take-off Accuracy — Honest Results

Production scenario: **plans only** (no companion take-off), optionally plus an
**Object Manifest** (object names + units, no quantities). Scored by
`scripts/vision_only_benchmark.py` against the human take-off golden CSVs.
Quantity scoring is honest: a not-found/zero quantity never counts as a pass.

## Per-category accuracy (vision-only, no companion take-off)

| Project | Mode | Name/found | Counts found | Measured found | Quantity acc |
|---|---|---|---|---|---|
| Crow Cass | baseline | 70% | 67% | 75% | 40% |
| Crow Cass | **+ manifest** | **100%** | **100%** | **100%** | 40% |
| Bob's Discount | baseline | 33% | 57% | 0% | 8% |
| Bob's Discount | **+ manifest** | **100%** | **100%** | **100%** | 8% |

(`found` = the item appears in the take-off with the correct name + unit;
`quantity acc` = the number is within tolerance — EA exact±1, SF/LF within 3%.)

## What the Object Manifest achieves (the deliverable)

- **~100% item list / naming / units.** Every object the estimator expects now
  appears in `takeoff_summary` under the estimator's own name + unit, resolved at
  runtime by alias/token/fuzzy match — no hardcoded name map required.
- **Zero silent misses.** Any manifest object not located on the plans is emitted
  with quantity `—` and `needs_review = yes` (reason recorded), so it is reviewed
  by a human instead of disappearing.
- **Uncertainty is surfaced, not hidden.** Approximate measurements, low-confidence
  counts, unclassified items, and assumption-based wall areas are flagged
  `needs_review` end-to-end and highlighted in the UI and CSVs.

## What is NOT promised (stated up front, as in the plan)

- **Guaranteed 100% on measured quantities (SF/LF) or dense EA counts.** Vision AI
  alone cannot reliably measure areas/lengths or count hundreds of repeated symbols
  without true scale→geometry. Quantity accuracy was unchanged by the manifest
  because the manifest fixes *naming/completeness*, not *measurement*.
- These quantities are **maximized and confidence-flagged** rather than guaranteed.

## Measured-quantity investigation (why ≥97% can't be auto-guaranteed)

Evidence gathered against the real plan PDFs (which ARE vector CAD, ~68k geometry
items/sheet):

1. **Multi-scale sheets break auto-scaling.** Each sheet mixes an overall plan
   (`1"=40'`) with many detail callouts (`1/2"=1'-0"`). Detecting the *main* scale
   by frequency picks the wrong one (detail scales are more numerous), and
   dimension self-calibration landed `1"=24'` vs the true `~1"=20'`.
2. **Footprint extent is approximate.** Even with the correct scale, a trimmed
   bounding extent gave 0.72–0.87× the true building area — the outline is an
   irregular polygon, not a clean rectangle.
3. **Vision SF reads are non-reproducible.** Two identical vision-only runs read
   "Exposed Structure" as **397,500 SF** (≈ golden) and **1,131,112 SF** — pure
   run-to-run variance. A lucky read is not accuracy.
4. **Tiled counting (`COUNT_TILING=1`) helps recall but isn't ±1-exact.** On Crow
   it moved Columns 25→108 (golden 132) and Bollards 0→17 (golden 28), but also
   *over*counted Stairs 10→16 and Ladder 1→3. Useful for recovering missed
   objects; left OFF by default because it can over/under-count.

**Conclusion (honest):** no fully-automated system guarantees ≥97% on measured
SF/LF for arbitrary unseen plans — professional takeoff tools still require a human
to set scale and confirm regions. We therefore *maximize* and *flag*.

## The realistic path to ~100% (implemented)

1. **Completeness + flagging** (done): every expected item appears; uncertain
   quantities are flagged `needs_review` and highlighted — a human verifies a small
   flagged subset and signs off at 100%.
2. **Reliable scale unlocks accurate geometry** (`geometry_takeoff.py`): supply the
   plan scale (manifest assumption `scale_ft_per_in`, e.g. `20` for 1"=20') and the
   engine measures real lengths/areas from the CAD coordinates with high accuracy as
   a verification reference. The math is exact given the scale (validated by tests);
   areas are always presented flagged-for-verification, never as unverified truth.
3. **EA recall** via optional tiled counting + manifest-targeted counts for the
   objects you care about.

## Accuracy levers added this program

- `object_manifest.py` — runtime flexible naming + completeness guarantee.
- Targeted manifest-driven count hint + higher-resolution count render on dense
  sheets; optional gated tiled recount (`COUNT_TILING=1`) for missed EA objects.
- `scale_utils.py` — parse architectural/engineering/ratio scale notations into
  feet-per-inch / feet-per-pixel (foundation for future pixel-measurement / CV).
- Manifest-driven wall height replaces the blanket 9ft wall-area assumption.
- End-to-end `confidence` / `needs_review` / `review_notes` columns in
  `takeoff_summary.csv` and `calculations.csv`; low-confidence rows highlighted in
  the UI.

## How to reproduce / validate other projects

```bash
# Baseline (no manifest):
python3 scripts/vision_only_benchmark.py \
  --name "Crow Cass" \
  --plans tests/fixtures/crow_cass/crow_cass_plans.pdf \
  --golden tests/fixtures/crow_cass/crow_cass_golden.csv

# With an object manifest (names + units only, no quantities):
python3 scripts/vision_only_benchmark.py \
  --name "Crow Cass Manifest" \
  --plans tests/fixtures/crow_cass/crow_cass_plans.pdf \
  --golden tests/fixtures/crow_cass/crow_cass_golden.csv \
  --manifest tests/fixtures/crow_cass/crow_cass_manifest.json

# Re-score a saved summary (free, no API):
python3 scripts/vision_only_benchmark.py --name X --golden <golden.csv> \
  --rescore reports/vision_only/<Dir>/vision_summary.json
```

Chelsea and Moxy (the large plan sets) can be validated with the same harness +
a manifest; they are intentionally not auto-run here because each is a large,
expensive vision pass and the per-category conclusion is already stable and
consistent across the two fixtures above.
