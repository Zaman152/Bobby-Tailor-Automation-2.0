---
phase: 20
plan: "05"
subsystem: takeoff-extraction-aggregation
tags: [claude-prompts, linear-runs, lintel, duct, conduit, item-name-map, aggregator, generalization]
depends_on: ["20-03", "20-04"]
provides:
  - "MEASURE_ADDENDUM constant extending EXTRACTION_PROMPT with 20+ linear run types"
  - "lintel_runs[] schema in extraction prompt + _calculate_from_lintel_runs() calculator path"
  - "duct_lf and conduit_lf ESTIMATION_TABLES entries with 10% waste"
  - "Extended _detect_pipe_item_type() routing (gas/duct/conduit/guardrail/striping/handrail)"
  - "Full ITEM_NAME_MAP covering Masterv2 §C taxonomy (55+ patterns)"
  - "33 aggregator generalization tests covering civil/structural/arch/MEP labels"
affects:
  - "20-06: duct/conduit measurements now flow through to aggregator canonical names"
  - "21-xx: any future golden-CSV accuracy tests benefit from complete item mapping"
tech-stack:
  added: []
  patterns:
    - "MEASURE_ADDENDUM constant pattern — named addendum appended to base prompt at module level"
    - "Ordered ITEM_NAME_MAP — specific-before-generic ordering prevents pattern collisions"
key-files:
  created: []
  modified:
    - claude_analyzer.py
    - calculator.py
    - aggregator.py
    - tests/test_takeoff_generalization.py
decisions:
  - "MEASURE_ADDENDUM defined as named constant then concatenated to EXTRACTION_PROMPT — preserves traceability"
  - "lintel_runs[] as dedicated array (not merged into pipe_runs[]) — cleaner schema, separate calculator path"
  - "duct_lf and conduit_lf use 10% waste (vs 5% for gas/storm) — fittings/connections add more LF equivalent"
  - "CMU Paint placed BEFORE CMU Wall in ITEM_NAME_MAP — both match \\bcmu\\b; first match wins"
  - "Frame-HM placed BEFORE Doors-HM — 'HM Door Frame' must not collapse to Doors-HM"
  - "Conduit LF / Duct LF placed BEFORE Storm Pipe — prevents PVC conduit matching \\bpvc\\b storm pattern"
  - "Resolved xfail test_schedule_doors_hm_wd_separate — now passes with HM/WD ITEM_NAME_MAP separation"
metrics:
  duration: "~11 min"
  completed: "2026-06-03"
  tests_added: 33
  tests_total: 61
  xfails_resolved: 1
---

# Phase 20 Plan 05: MEASURE_ADDENDUM + Full ITEM_NAME_MAP Summary

**One-liner:** MEASURE_ADDENDUM prompt extending 20+ linear run types (lintel/duct/conduit) + full Masterv2 §C ITEM_NAME_MAP with ordered HM/WD/frame separation and 33 aggregator tests.

---

## Objective

Extend measurement extraction and aggregation for all quantity types found on construction drawings — linear runs (20+ types), areas, counts — aligned with Masterv2 §C taxonomy. Golden CSV items must emerge from general rules, not hardcoded map entries.

---

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | MEASURE_ADDENDUM — all linear run types + calculators | `0d5de83` | claude_analyzer.py, calculator.py |
| 2 | Full ITEM_NAME_MAP from Masterv2 §C + 33 aggregator tests | `d889981` | aggregator.py, tests/test_takeoff_generalization.py |

---

## What Was Built

### Task 1 — MEASURE_ADDENDUM + Calculator

**`claude_analyzer.py`:**
- Added `lintel_runs[]` array to `EXTRACTION_PROMPT` JSON schema (after `pipe_runs[]`)
- Updated Rule 3 in EXTRACTION_PROMPT to reference gas/mechanical/lintel routing
- Added `MEASURE_ADDENDUM` constant covering all extended linear run types:
  - Gas: black steel, CSST, yellow PE
  - Mechanical: copper, CPVC, refrigerant lines, condensate
  - HVAC: rectangular duct, spiral duct, flex duct
  - Electrical: EMT conduit, PVC conduit, wireway, cable tray
  - Site: striping, guard rail, hand rail, trench drain, curb and gutter
  - Structural: `lintel_runs[]` with mark/size/count/total_lf schema
- Concatenated `MEASURE_ADDENDUM` to `EXTRACTION_PROMPT` at module level

**`calculator.py`:**
- Added `duct_lf` and `conduit_lf` to `ESTIMATION_TABLES` (10% waste each)
- Expanded `_detect_pipe_item_type()` with 6 new routing branches:
  - `gas` / `black steel` / `CSST` → `gas_pipe` (existing)
  - `duct` / `ductwork` / `rectangular/spiral/flex duct` → `duct_lf`
  - `conduit` / `EMT` / `wireway` / `cable tray` / `raceway` → `conduit_lf`
  - `guard rail` / `guardrail` / `w-beam` → `guard_rail`
  - `hand rail` / `handrail` → `hand_rail`
  - `strip` / `pavement marking` → `striping`
- Added `_calculate_from_lintel_runs()`: mark × count → LF with 5% waste
- Wired `lintel_runs` into `apply_estimation_tables()` step 5
- Extended `_apply_formula()` to include `duct_lf` and `conduit_lf` in LF group
- Added `duct`, `conduit`, `guard_rail`, `hand_rail`, `striping` to `_TYPE_LABEL` dict

### Task 2 — Full ITEM_NAME_MAP

**`aggregator.py`:**

Expanded `ITEM_NAME_MAP` from 35 patterns to 55+ patterns, with critical ordering fixes:

| Category | Key Additions | Ordering Note |
|----------|--------------|---------------|
| Civil/Site | Conduit LF, Duct LF, Curb & Gutter, Asphalt, Concrete Pavement | Conduit/Duct BEFORE Storm Pipe |
| Structure | CMU Paint, CMU Wall, Lintels, Ladder, Interior/Exterior tilt-up separated | CMU Paint BEFORE CMU Wall |
| Architectural | Frame-HM, Doors-HM, Doors-WD, Doors-AL, EIFS, Canopy | Frame-HM BEFORE Doors-HM; specific types before generic |
| MEP | Duct LF, Conduit LF (moved to civil for ordering) | — |

**`tests/test_takeoff_generalization.py`:**
- Resolved `xfail` on `test_schedule_doors_hm_wd_separate` — now passes (HM/WD separated)
- Added 33 aggregator generalization tests across 5 sections:
  - §9: Civil/Site labels (bollard, catch basin, manhole, gas piping, storm pipe, guard rail, striping, asphalt, concrete pavement)
  - §10: Structural labels (sealed concrete, exposed structure, tilt-up walls, CMU wall, lintels)
  - §11: Architectural labels (canopy, EIFS, CMU paint, Doors-HM, Doors-WD, Doors-AL, Frame-HM, ladder, lift)
  - §12: MEP labels (fan coil, AHU, exhaust fan, duct LF, conduit LF)
  - §13: Integration tests (door schedule HM/WD pipeline, lintel_runs canonical, duct pipe_run canonical)

---

## Verification

```
pytest tests/test_calculator_accuracy.py tests/test_takeoff_generalization.py -q
61 passed in 0.03s

pytest tests/test_takeoff_generalization.py -q -k "aggregator"
33 passed in 0.02s
```

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_TYPE_LABEL` missing duct/conduit/guardrail/handrail/striping entries**

- **Found during:** Task 2 test run — duct_lf items produced `'Duct Lf'` (fallback title-case) instead of `'Duct LF'` canonical
- **Issue:** `_calculate_from_pipe_runs` `_TYPE_LABEL` dict had no entry for `duct_lf`, `conduit_lf`, `guard_rail`, `hand_rail`, `striping`; the label fell back to `"pipe run"` causing mismatch with ITEM_NAME_MAP patterns
- **Fix:** Added all 5 new item types to `_TYPE_LABEL` dict
- **Files modified:** `calculator.py`
- **Commit:** `d889981`

**2. [Rule 1 - Bug] ITEM_NAME_MAP pattern collision: PVC conduit → Storm Pipe**

- **Found during:** Task 2 test run — `"PVC conduit underground"` matched `\bpvc\b` (Storm Pipe) before conduit pattern
- **Fix:** Moved Conduit LF and Duct LF entries BEFORE Storm Pipe in ITEM_NAME_MAP
- **Files modified:** `aggregator.py`
- **Commit:** `d889981`

**3. [Rule 1 - Bug] ITEM_NAME_MAP collision: CMU Wall matched before CMU Paint**

- **Found during:** Task 2 test — `"CMU paint epoxy block coat"` matched `\bcmu\b` (CMU Wall) first
- **Fix:** Moved CMU Paint entry above CMU Wall in structure section
- **Files modified:** `aggregator.py`
- **Commit:** `d889981`

**4. [Rule 1 - Bug] Frame-HM collapsing to Doors-HM ("HM Door Frame" → `hm.*door`)**

- **Found during:** Task 2 test — `\bhm\b.*frame` pattern never reached because `hm.*door` matched first
- **Fix:** Moved Frame-HM entry above all door type entries; added `(?!.*frame)` negative lookahead to Doors-HM pattern
- **Files modified:** `aggregator.py`
- **Commit:** `d889981`

---

## Test Results

| Suite | Before | After |
|-------|--------|-------|
| test_calculator_accuracy.py | 6 passed | 6 passed |
| test_takeoff_generalization.py | 21 passed, 1 xfailed | 55 passed |
| Total | 27 | 61 |

---

## Next Phase Readiness

Plan 20-06 can proceed. The extraction → calculator → aggregator path now handles:
- All 20+ linear run types (gas, duct, conduit, guard rail, striping, lintels, etc.)
- Full Masterv2 §C taxonomy items without project-specific hardcoding
- Door type separation (HM/WD/AL) as distinct canonical line items
- HM frame vs HM door disambiguation via pattern ordering
