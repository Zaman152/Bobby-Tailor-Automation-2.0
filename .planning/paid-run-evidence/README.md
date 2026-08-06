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

---

## Round 2 — the phase-24 determinism A/B (2026-08-06, $1.1573)

Human-in-the-loop contract: plans-only pipeline input **plus** `tests/fixtures/crow_cass/crow_cass_manifest.json`
as the estimator's manifest. Manifest verified to carry NO quantity/count/total — only
name/unit/measure/aliases and four `assumptions.height_ft`. Leakage tripwire passed on both runs
(decoy sibling take-off + decoy `manifests/default.json` planted, proven discoverable, proven unread).

| dir | run | overall | measured qty_ok | cost |
|---|---|---|---|---|
| `VisionOnly_P24DET_Crow_20260806_194607` | A | 40% | 75% | $0.768091 |
| `VisionOnly_P24DET_Crow_20260806_195704` | B | 50% | 75% | $0.389186 |

**Determinism verdict — SPLIT.** Published `(item, unit)` key sets **IDENTICAL** (51 rows, 0 only-in-A,
0 only-in-B), and 34 shared unnamed-geometry candidates **bit-identical** (every `SYM-*` count, every
`WALL-TC*` LF, `ROOM-1..6` SF). But **3 of 51 quantities differ**: `Door Frames-HM` 4.0 -> None,
`Lift` None -> 1.0, `Stairs` 1.0 -> 2.0. All three trace to the per-sheet vision **extraction** pass
reading different descriptions off the same pixels (raw items 113 vs 124). **The naming layer and the
geometry layer are both stable — phase 24 fixed what it targeted; the residual variance is one layer
upstream, in extraction.**

**24-05 persistence — live PASS.** Run B logged `naming conventions REUSED from persisted snapshot ->
27 object type(s); no naming-convention API call made` and was **49.3% cheaper**. Caveat: only the
`naming_conventions` snapshot kind persisted; the DB has zero `project_vocabulary` rows, so half that
path is still unexercised.

**Telemetry fix (91e3450) confirmed:** `api_usage.total_cost_usd` equals the budget guard's
`spent_usd` to six decimals in both runs. The phase-23 $0.1766-vs-$0.5988 divergence is gone.
No truncation fired (cap $2.50; A used 31%, B 16% — the old $0.60 cap would have truncated both).

**The one outright failure: `Stairs`.** Published `MEASURED`, `needs_review=False`, confidence medium,
value 1.00 (A) / 2.00 (B) against golden **10**. Unflagged, 90% wrong, and not reproducible — the worst
combination in the report. Everything else that was wrong was at least flagged.
