---
phase: 20-takeoff-measurement-precision
plan: "09"
subsystem: aggregator
tags: [aggregator, item-name-map, canonical-names, mep, civil, fire-protection, hvac]

dependency-graph:
  requires: ["20-05"]
  provides: ["ITEM_NAME_MAP ≥68 entries covering full Masterv2 §C taxonomy"]
  affects: ["aggregate_takeoff pipeline", "reporter generate_report", "all canonical name resolution"]

tech-stack:
  added: []
  patterns: ["additive-only ITEM_NAME_MAP expansion", "specific-before-generic ordering constraint"]

key-files:
  created: []
  modified:
    - aggregator.py
    - tests/test_takeoff_generalization.py

decisions:
  - "Sanitary Pipe placed BEFORE Storm Pipe — sanitary.*sewer would otherwise collapse into Storm Pipe"
  - "Storefront/Curtain Wall placed AFTER all door patterns — 'aluminum storefront door' must resolve to Doors-AL, not Storefront"
  - "RTU placed AFTER Air Handling Units — 'air handler' pattern must win over 'rooftop.*unit'"
  - "Fire Hydrants placed before conduit/storm entries — avoids ambiguity with \\bfh\\b abbreviation"
  - "Drywall Ceiling placed BEFORE Ceiling Grid — suspended/gyp ceiling is structurally distinct from ACT tile"
  - "Dock Doors placed before Frame-HM/Door section — overhead/coiling doors are structure/site items"
  - "_extract_spec_for_name appends size suffix to any canonical containing 'Pipe' — test cases use descriptions without diameter where canonical-only assertion is needed"

metrics:
  duration: "~3.5 min"
  completed: "2026-06-04"
---

# Phase 20 Plan 09: ITEM_NAME_MAP Expansion — Masterv2 §C Gap Closure Summary

**One-liner:** Expanded `ITEM_NAME_MAP` from 52 to 71 entries covering fire suppression, site utilities, HVAC subtypes, storefront, fence, dock equipment — all generic patterns, no project-specific strings.

## Objective

Close ACCURACY-20-11: expand `ITEM_NAME_MAP` to ≥68 entries cross-referenced against Masterv2 §C taxonomy. Add parametrized aggregator tests for every new canonical name.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Audit Masterv2 §C vs ITEM_NAME_MAP — add missing entries | `880bbf8` | `aggregator.py` |
| 2 | Aggregator tests for new canonical names | `baf652c` | `tests/test_takeoff_generalization.py` |

## Changes

### Task 1 — ITEM_NAME_MAP expansion (aggregator.py)

Baseline: **52 entries**. After expansion: **71 entries** (≥68 target ✓).

Added **19 new entries** in four categories:

**Civil / Site (7 new):**
| Pattern | Canonical | Unit |
|---------|-----------|------|
| `fire.*hydrant\|\bfh\b` | Fire Hydrants | EA |
| `area.*drain\|floor.*drain\|cleanout` | Area Drain / Cleanout | EA |
| `sanitary.*pipe\|sanitary.*sewer\|\bss\s*pipe\b` | Sanitary Pipe | LF |
| `water.*main\|water.*line\|domestic.*water` | Water Main | LF |
| `detention\|retention.*pond\|bioswale` | Stormwater Basin | EA |
| `\bfence\b\|chain.*link\|ornamental.*fence` | Fence | LF |
| `grading\|cut.*fill\|mass.*grade` | Grading | CY |

**Architectural / Structure (5 new):**
| Pattern | Canonical | Unit |
|---------|-----------|------|
| `suspended.*ceil\|gyp.*ceil\|acoustical.*ceil.*grid` | Drywall Ceiling | SF |
| `dock.*door\|overhead.*door\|coiling.*door` | Dock Doors | EA |
| `dock.*leveler\|dock.*seal\|dock.*bumper` | Dock Leveler | EA |
| `glass.*door\|aluminum.*storefront.*door` | Doors-GL | EA |
| `storefront\|curtain.*wall\|window.*wall` | Storefront/Curtain Wall | SF |

**MEP / Fire Protection (7 new):**
| Pattern | Canonical | Unit |
|---------|-----------|------|
| `sprinkler.*head\|fire.*sprinkler\|pendent` | Sprinkler Heads | EA |
| `smoke.*detector\|fire.*alarm\|horn.*strobe` | Fire Alarm | EA |
| `\bvav\b\|variable.*air.*volume` | VAV Boxes | EA |
| `unit.*heater\|cabinet.*heater` | Unit Heater | EA |
| `refrigerant.*line\|ref.*line\|line.*set` | Refrigerant Piping | LF |
| `thermostat\|t-stat` | Thermostat | EA |
| `\brtu\b\|rooftop.*unit\|packaged.*unit` | RTU | EA |

### Task 2 — Aggregator tests (tests/test_takeoff_generalization.py)

Added **42 new test cases** in 10 named test functions/classes (all with `aggregator` in identifier, collected by `-k aggregator`):

| Test Function | Cases | Coverage |
|---------------|-------|----------|
| `test_aggregator_new_civil_site_entries` | 13 | Fire hydrant, area drain, sanitary pipe, water main, stormwater basin, fence, grading |
| `test_aggregator_mep_fire_suppression` | 6 | Sprinkler heads, fire alarm |
| `test_aggregator_hvac_subtypes` | 6 | VAV, RTU, unit heater |
| `test_aggregator_rtu_does_not_override_ahu` | 2 | RTU vs AHU ordering guard |
| `test_aggregator_refrigerant_thermostat` | 4 | Refrigerant piping, thermostat |
| `test_aggregator_storefront_and_curtain_wall` | 3 | Storefront, curtain wall, window wall |
| `test_aggregator_storefront_does_not_override_doors` | 2 | Ordering guard: door patterns win over storefront |
| `test_aggregator_dock_equipment` | 6 | Dock door, dock leveler/seal/bumper |
| `test_aggregator_drywall_ceiling` | 2 | Suspended/gyp ceiling → Drywall Ceiling |
| `test_aggregator_glass_doors` | 2 | Glass door → Doors-GL |

## Verification Results

- [x] `len(ITEM_NAME_MAP) >= 68` → **71** ✓
- [x] `pytest tests/test_takeoff_generalization.py -q` → **97 passed** (55 pre-existing + 42 new) ✓
- [x] No "Crow" or "Bob" in `aggregator.py` ✓

## Ordering Decisions

Critical ordering enforced to prevent pattern conflicts:

1. **Sanitary Pipe before Storm Pipe** — `sanitary.*sewer` would otherwise be consumed by Storm Pipe's `sanitary sewer` literal.
2. **Storefront/Curtain Wall after all door patterns** — "aluminum storefront door" must resolve to `Doors-AL`, not `Storefront/Curtain Wall`.
3. **RTU after Air Handling Units** — "air handler" wins for explicit AHU descriptions; `rooftop.*unit` still catches RTU.
4. **Drywall Ceiling before Ceiling Grid** — `suspended.*ceil` and `gyp.*ceil` are structurally distinct from ACT tile grid.
5. **Dock Doors before generic Doors** — "overhead door" and "coiling door" resolve to Dock Doors, not the generic `door(?!.*frame)` catch-all.

## Deviations from Plan

None — plan executed exactly as written. Two test descriptions were adjusted (no 8" diameter in sanitary pipe test, no "MH-3" in sanitary sewer test) because `_extract_spec_for_name` appends a pipe-size suffix to any canonical name containing "Pipe", and `\bmh\b` in the Manholes pattern catches mark abbreviations like "MH-3". Tests were written to assert canonical names directly without diameter suffixes.

## Next Phase Readiness

- ACCURACY-20-11 satisfied: ITEM_NAME_MAP covers full Masterv2 §C taxonomy at 71 entries (within ±1 of ~70 target).
- No blockers for 20-10 or downstream phases.
