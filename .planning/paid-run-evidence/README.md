# Paid-run evidence — DO NOT DELETE

Two Crow plans-only runs, $0.98 of real API spend, preserved here because `output/` is gitignored
and was purged of ~1.1 GB in commit `e2fa735`. These are the **only** artifacts proving the
run-to-run naming variance Phase 24 exists to kill, and the **only** seed material for its
determinism fixtures.

| dir | date | scored |
|---|---|---|
| `VisionOnly_P23V_Crow_20260804_141952` | 2026-08-04 14:19 | 10% (pre-regression-fix) |
| `VisionOnly_P23V2_Crow_20260804_181352` | 2026-08-04 18:13 | 30% (post-fix round 1, budget-truncated at $0.599) |

**The finding they carry (24-RESEARCH.md):** the geometry layer is already deterministic — 29 of
43/45 `(quantity, unit)` keys are bit-identical across the two runs, including every `SYM-*` count,
the 397,600 SF footprint, all `WALL-TC*` LF, `ROOM-3..6`, the elevations, the perimeter and every
door-schedule count. **100% of the variance is in the naming layer.** The same 56-EA candidate
publishes as `Bollard` (`source: learned`) in run 1 and `Dock Bumper` (`source: library`) in run 2.

**Confound to respect:** four commits landed between the runs (`286c326` 15:44; three at 18:03).
They touch arbitration / aggregator / wall-height / title-parsing — NOT the naming path. So naming
deltas are clean evidence; arbitration deltas (the 397,600 fan-out, the Tilt Up Wall cascade) are
confounded.

Re-score either for free:
`python3 scripts/score_report_dir.py --golden tests/fixtures/crow_cass/crow_cass_golden.csv --dir .planning/paid-run-evidence/<dir>`
