# Phase 20 Context — Takeoff Measurement Precision

**Created:** 2026-06-03  
**Updated:** 2026-06-03 — Generalization scope clarified  
**Trigger:** Client golden-file verification (Crow Cass + Bob's Discount) shows Phase 16 outputs do **not** match reference take-offs. User requires **≥97% accuracy** on quantities (not visual markup overlays).

## Product scope vs regression fixtures

| Scope | What it means |
|-------|----------------|
| **Product** | Accurate measurements from **any** construction PDF/StackCT plan set: industrial, retail, office, civil/site, MEP, residential, institutional, mixed-use |
| **Golden fixtures** | Crow Cass + Bob's Discount are **regression tests only** — they prove we hit 97% on known references; they do NOT define the only supported item types |
| **Generalization tests** | Synthetic JSON per `sheet_type` runs in CI without API keys — proves engine logic for all plan categories |

**Architecture principle:** Sheet-type + discipline driven (PASS_MATRIX), content-first room mapping, shared `takeoff_pipeline.py` for PDF and StackCT. No hardcoded project names, quantities, or `^[AS]\d`-only routing.

## Golden reference files (uploads/)

| File | Role |
|------|------|
| `Crow - Cass White Road-Plans.pdf` | 4-page industrial plan set |
| `Crow - Cass White Road-Take offs.pdf` | Client reference quantities (legend on A-101) |
| `Bob's Discount Furniture - Kennesaw, GA-plans.pdf` | 7-page retail plan set |
| `Bob's Discount Furniture - Kennesaw, GA-Take offds.pdf` | Client reference quantities (4 sheets) |

## Crow — Cass White Road (A-101 legend = ground truth)

| Item | Client qty | AI run `20260603_222253` | Error |
|------|------------|--------------------------|-------|
| Bollards | 28 EA | 10 EA | −64% (detail dims counted as bollards) |
| CMU Wall | 2,204.33 SF | — | Missing |
| Columns-H-35' | 132 EA | — | Missing |
| Exposed Structure | 395,673.42 SF | — | Missing |
| Internal Tilt up walls | 108,442.66 SF | — | Missing |
| Ladder-H-20' | 1 EA | — | Missing |
| Lift | 1 EA | — | Missing |
| Mobilization | 1 EA | — | Missing |
| Sealed Concrete | 395,673.42 SF | — | Missing (mislabeled as Flooring 437,311 SF) |
| Stairs | 10 EA | — | Missing |

**Partial win:** Raw extraction found **397,556 SF** labeled gross area (matches plan label; client sealed/exposed is 395,673 SF ≈ 0.5% lower).

## Bob's Discount (client take-off PDF pages)

| Sheet | Client items | AI run `20260603_222809` |
|-------|--------------|--------------------------|
| A3.0 Roof Plan | Gas Piping **886.77 LF** | Missing (0 pipe runs) |
| A4.0 Elevations | Bollards 11, Canopy 79.44 SF, CMU paint 16,218.94 SF, EIFS 3,053.04 SF, Lift 1, Lintels 179.24 LF, Mobilization 1 | Missing (page failed as `E283`) |
| A8.1 Door Schedule | Frame-HM 12, Doors-HM 5, Doors-WD 7 | 24 doors wrong breakdown; schedule hallucinated (101–115) |
| A8.3 Details | Ladder-H-24' 1 EA | Component found, qty null |

## Root cause taxonomy (verified in code)

1. **Wrong item mapping** — `_calculate_from_room()` applies flooring/ceiling/drywall/paint to any large area; industrial items (sealed concrete, exposed structure) never reached.
2. **No spatial counting** — `components[]` extracted with `quantity: null`; calculator drops them. Grid columns, bollards, stairs require symbol/grid counting.
3. **Detail vs plan confusion** — Detail sheet dimensions (6' bollard spacing) counted as EA bollards.
4. **No linear tracing** — Gas piping, lintels, guard rail need run-length summation; `pipe_runs[]` empty on roof plan.
5. **Sheet ID broken** — `pdf_analyzer._sheet_name_from_doc()` regex picks first match (E283 from ASTM E283, A156 vs A8.1); title block not parsed.
6. **Single-pass vision insufficient** — Haiku default; complex schedules need Sonnet + structured verification pass.
7. **Incomplete sheet coverage** — Crow cross-refs to A-111/112/113 unresolved; Bob elevations not in 7-page upload set alignment.
8. **No accuracy gate** — Phase 16 UAT checks format/guards, not numeric match to golden files.

## User requirements (non-negotiable)

- Values must match client reference within **≥97%** per line item (or exact for EA counts).
- No need to generate visual markup overlays — numeric `takeoff_summary.csv` only.
- Willing to use **best vision model** (Sonnet/Opus) where it improves accuracy.
- Iterative test loop until golden files pass.

## Existing code to extend (do not rewrite)

- `claude_analyzer.py` — EXTRACTION_PROMPT v2.1
- `calculator.py` — ESTIMATION_TABLES + `_calculate_from_*`
- `aggregator.py` — ITEM_NAME_MAP + `aggregate_takeoff`
- `reporter.py` — `takeoff_summary.csv`
- `pdf_analyzer.py` — PDF page → image pipeline
- `cross_references.py` / Phase 18 linked sheets
- `tests/test_calculator_accuracy.py` — extend for golden files

## Accuracy metric definition (proposed)

For each golden `(item_name, quantity, unit)`:
- **EA/LF counts:** exact match required (0% error) OR within ±1 for counts >10
- **SF/CY:** `|ai - ref| / ref ≤ 0.03` (3% tolerance → 97% accuracy)
- **Project score:** ≥97% of line items pass; **zero** wrong item types (e.g. Flooring ≠ Sealed Concrete)

Golden test command target: `pytest tests/test_golden_takeoff.py -v` exits 0 on Crow + Bob fixtures.
