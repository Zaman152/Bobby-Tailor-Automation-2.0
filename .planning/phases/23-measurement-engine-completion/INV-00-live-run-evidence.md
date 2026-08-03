# INV-00 — Evidence from scoring the saved runs (free, zero API)

Produced by the orchestrator on 2026-08-03 by scoring already-saved run artifacts with
`scripts/score_report_dir.py`. No API credits spent. This is **measured behaviour of the current
code**, not inference from the symptom log — it should anchor the Phase 23 plan.

---

## 1. The room-fill binding is completely non-functional in the pipeline

**This is the single highest-value finding.** `docs/PIPELINE-GROUND-TRUTH.md` §14 reports the room
engine measuring Moxy Gyp Ceiling to **7.0% blind error** — but those numbers came from a **probe**,
not from the pipeline. The pipeline emits nothing.

Timeline proves the run was not stale:

| Commit / run | Time (07-17) |
|---|---|
| `b4e084d` enclosed-region room engine | 03:37 |
| `9142713` wire the room engine in | 04:03 |
| `9eae50e` **bind measured room areas to line items** | 04:18 |
| `8d6b26f` **classify fix** (mixed sheet must still be measurable) | 04:41 |
| `VisionOnly_Moxy_Knoxville_20260717_045741` run START | **04:57** |

The run postdates **every** room-engine and classifier fix. Its `takeoff.json` nonetheless contains:

```
'room_fill'   appears 0 times
'room_fills'  appears 0 times
'unit_count'  appears 0 times
'plan_name'   appears 0 times
```

And the manifest's `unit_type` prototype entries landed as **empty line items**:

```
ACC BUNK      | 0.0 | (no unit)
ACC KING TUB  | 0.0 | (no unit)
ADA KING RIS  | 0.0 | (no unit)
BUNK A        | 0.0 | (no unit)
BUNK B        | 0.0 | (no unit)
```

**Conclusion:** `_fuse_room_fills` either never runs in the real pipeline, or its output never
survives into `takeoff_summary`. The measurement capability exists and is accurate; the wiring does
not. INV-01 must treat this as the primary defect — fixing it is likely the largest single accuracy
jump available in the whole program.

---

## 2. Scored Moxy run (with manifest) — 8% overall

`score_report_dir.py --golden tests/fixtures/moxy/moxy_golden.csv --dir output/VisionOnly_Moxy_Knoxville_20260717_045741`

```
Overall quantity accuracy: 8%   Name/found rate: 88%   Qty acc when found: 10%
  Counts (EA)     n= 6  found=50%   qty_ok=33%
  Measured(SF/LF) n=18  found=100%  qty_ok=0%     <-- ZERO
```

| Item | Golden | AI | Note |
|---|---|---|---|
| Gyp Wall | 129,521 SF | 191 | 99.9% off |
| Gyp Ceiling | 58,680 SF | — | no value emitted |
| Guestroom-Wall Covering | 27,014 SF | — | no value |
| WC-1 … WC-10 | 6,908 SF total | — | no values |
| Base / Lintels / Hand Rail | 3,541 / 1,530 / 65 LF | — | no values |
| CMU Wall | 6,916 SF | 474 | 93% off |
| Exposed Structure | 3,771 SF | 66 | 98% off |
| Gyp Soffit | 260 SF | 36 | 86% off |
| Guard Rail | 189 LF | 83 | 56% off |
| Doors-WD / Doors-HM / Door Frame-HM | 213 / 10 / 215 | — | schedule not parsed |
| Lift, Mobilization | 1, 1 | 1, 1 | PASS (Mobilization is a constant) |

**Name/found rate 88% is circular and meaningless** — the manifest supplied the names. Only the
QUANTITY column is a real measure, and it is 0% on everything measured.

---

## 3. Scored Crow run (plans-only) — 40% overall, and the split is diagnostic

`score_report_dir.py --golden tests/fixtures/crow_cass/crow_cass_golden.csv --dir output/VisionOnly_Crow_A2_20260715_215449`

```
Overall quantity accuracy: 40%   Name/found rate: 60%   Qty acc when found: 67%
  Counts (EA)     n= 6  found=33%   qty_ok=17%    <-- the whole gap
  Measured(SF/LF) n= 4  found=100%  qty_ok=75%    <-- works
```

| Item | Golden | AI | Status |
|---|---|---|---|
| Exposed Structure | 395,673 SF | 397,600 | PASS 0.5% |
| Sealed Concrete | 395,673 SF | 397,600 | PASS 0.5% |
| Internal Tilt up walls | 108,443 SF | 106,998 | PASS 1.3% |
| Mobilization | 1 | 1 | PASS (constant) |
| CMU Wall | 2,204 SF | 8 | FAIL — wall-class binding flip |
| Bollards | 28 | 0 | FAIL |
| Columns-H-35' | 132 | — | MISSING (emitted as "Structural Column 136" in EXTRAS) |
| Ladder-H-20', Lift, Stairs | 1, 1, 10 | — | MISSING |

**This cleanly separates the programme:**
- Crow's residual gap is **counts** (→ Phase 25 symbol detection) and **wall-class binding**
  (→ Phase 24). Its *measurement* is already good (75% qty_ok, three items inside 1.3%).
- Moxy's and Bob's gap is **measurement** (→ Phase 23).

So Phase 23 will barely move Crow and should move Moxy/Bob's enormously. Do not judge Phase 23 by a
Crow re-run.

---

## 4. Naming residue visible in Crow EXTRAS

The pipeline emitted, unmatched to golden: `Structural Column 136 EA`, `Canopy 397,600 SF`,
`Vapor Barrier 397,600 SF`, `Block Fill & Paint 40,086 SF`, `Dock Bumper 56 EA`, `Building Footprint
397,600 SF`, `Building Perimeter 2,972 LF`, plus ~25 unnamed `SYM-n` count rows.

Two separate problems visible here:
1. **The footprint value is bound to SIX line items at once** (verified by filtering `takeoff_summary`
   for the value):

   ```
   Building Footprint  397600.0 SF
   Canopy              397600.0 SF
   Concrete Pad        397600.0 SF
   Exposed Structure   397600.0 SF     <- correct (golden 395,673)
   Sealed Concrete     397600.1 SF     <- correct (golden 395,673)
   Vapor Barrier       397600.0 SF
   ```

   Anything roof/floor-shaped indiscriminately inherits the footprint. Two are genuinely correct;
   the other four are duplicates. **An estimator bidding from this report would price the floor six
   times.** This is a HIGH-severity fusion-binding defect (not a measurement defect) and it also
   inflates the apparent "found" rate. It needs an explicit one-area-one-item arbitration rule:
   a measured region may back at most one line item unless the plan states that two finishes
   genuinely occupy the same area (floor finish + slab, say), and any such sharing must be
   recorded as deliberate rather than emergent.
2. `Structural Column 136` is the documented §10 coincidence (136 collinear dimension ticks ≈ 132
   real columns). It must NOT be "fixed" by matching it to golden — Phase 25 handles this properly.

---

## 5. Tooling status

`scripts/score_report_dir.py` works correctly after the Phase 22 restructure and needs no changes.
It is the free scoring harness for every iteration — use it against saved run dirs before ever
spending on a live run.
