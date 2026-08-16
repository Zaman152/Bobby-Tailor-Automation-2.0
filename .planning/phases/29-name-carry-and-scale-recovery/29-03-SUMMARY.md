---
phase: 29-name-carry-and-scale-recovery
plan: 03
status: complete (code + tests; the paid re-run of T-29-03-06 is NOT run)
requirements:
  - V5-FIX-02
completed: 2026-08-16
---

# 29-03 Summary — a keynote drawn N times now reaches the report as N

## What shipped

One commit. `keynote_callout_counts` — green in tests since 28-06, **zero callers in `src/`** — is
now wired into the floor-plan path, and each keynote a sheet actually PLACES publishes as a flagged
candidate carrying the sheet's own words for it.

| file | what changed |
|---|---|
| `src/bobbytailor/pipeline/takeoff_pipeline.py` | `_keynote_callout_as_symbol_group` adapter; the wiring block at the lattice injection point; `keynote_callouts` evidence in the bundle |
| `src/bobbytailor/deterministic/room_fill.py` | `is_specification_note` guard; `KeynoteCallout.source_candidate_id` so the caller can suppress the bubble group it split |
| `tests/test_phase29_keynote_wiring.py` | 28 tests, new file |

On Crow page 0 the registry now receives **KEY-1 = 1, anchored "ACCESS LADDER TO CONCRETE ROOF OF
ELECTRICAL"** — the exact row the first paid run of the post-28 engine predicted (DEPLOYMENT-READINESS
§6, "Ladder-H-20' = 1, PASS expected") and published nothing for. The detector was never wrong; the
answer had nowhere to go.

## The three properties the wiring had to hold

1. **Anchored, not invented.** Unlike `_lattice_as_symbol_group`, which deliberately leaves
   `contained_texts` empty because a grid cell id is a coordinate rather than a name, a keynote's
   note text IS the drafter's own name for the thing the bubble points at. This is the one candidate
   in the engine that arrives already in the text-anchored regime.
2. **Drawn once, published once.** The per-number counts are split OUT of one bubble symbol group
   (Crow SYM-4: 54 = 12 legend bubbles + 42 callouts). That group is dropped — the
   `lattice_shadowed_symbol_ids` contract — and it is annotation either way: nobody buys a keynote
   bubble.
3. **Flagged.** `needs_review=True` on every KEY row. The count is a count of PLACEMENTS, measured
   on one page of one set; the flag is what makes a miscount a 30-second confirm instead of a wrong bid.

The wiring is additive in the strict sense: `symbols` is rebound exactly ONCE, at the end of the
`try`, so any raise anywhere inside leaves the sheet exactly as it was measured.

## The finding the plan did not anticipate — 180 rows of nothing on Moxy

The plan specified one guard shape: the universal quantifier (`ALL`, `TYP`, `PROVIDE ... AT`), aimed
at Crow general note 13, "ALL BOLLARDS TO BE PAINTED SAFETY YELLOW. (PROVIDE BOLLARDS AT ALL DRIVE-IN
OVERHEAD DOOR JAMBS ...)", which placed once would publish **Bollards = 1 against a golden 28** — worse
than the blank it replaces, because a blank is visibly missing and a 1 is silently wrong.

Sweeping all 83 pages of the four plan sets before writing the tests found the guard was sized for
the wrong sheet. **Crow produces 9 placed keynotes. Moxy produces 180**, across its 16 guestroom
prototype sheets — and Moxy's keynote legend is not a list of objects at all:

> "PROVIDE BLOCKING AS REQUIRED FOR CEILING MOUNTED", "USE PAINTERS TAPE TO CREATE LINE BETWEEN THE",
> "COORDINATE LOCATION AND INSTALLATION OF OUTLET AND", "GANG OUTLET & SWITCHES TOGETHER AT THIS
> LOCATION AT", "NO TRANSITION STRIP. FLOORING IN GUESTROOM"

Those are jobs, not things. Worse, those pages are exactly the ones the classifier-overrule promotes
to `floor_plan` (the 16-page skip-veto), so the plan-sheet gate does NOT hold them back — shipping
the plan's guard as written would have handed the naming pass 180 counted rows of nothing.

So the guard was widened, from measurement:

* **requirement words anywhere** — `ALL`, `TYP(ICAL)`, `PROVIDE(D/S)`, `REQUIRED`, `TO BE`
* **an instruction verb at the START** — `PROVIDE|INSTALL|COORDINATE|USE|GANG|VERIFY|REFER|SEE|PAINT|APPLY`.
  Leading-only, because "MULTI-USE ROOM" and "RAMP GUARDRAIL - SEE DETAILS 4, 12 & 13" are names that
  merely contain those words.
* **a declared absence at the START** — `NO`. "NO TRANSITION STRIP" is not one transition strip.

Measured effect, four sets, 83 pages: **180 → 32 on Moxy, 9 → 9 on Crow** (Ladder untouched), 0 on
Bob's and Chelsea, which print no placed keynotes at all. Every one of the 15 distinct refusals is a
directive; every survivor names an object.

**And the generalization claim got stronger, not weaker.** The route fires on a SECOND set with the
right answers: Moxy's exterior elevation sheets publish `CONTROL JOINT ×13`, `LOUVER ×5`,
`WALL PACK LIGHTING ×3`, `GAS METER ×1`. Nothing in the route knows Crow — it reads whatever legend
the sheet defines and counts whatever bubbles the sheet draws.

## What is deliberately still wrong, and flagged rather than fixed

* **A count of placements is not always a count of objects.** Crow KEY-9, "DOMESTIC WATER LINE - SEE
  PLUMBING", publishes 12 — twelve bubbles marking one line. The plan's `<limits>` accepts exactly
  this, and the flag is the defence. Removing it needs repeated paid runs, not an argument.
* **The guard reads only the ONE line the legend reader pairs with the number block.** A note whose
  quantifier wraps onto a dropped line passes it (the truncation limit recorded in
  `keynote_legend_rows` and pinned by `test_keynote_callouts`). It is a floor, not a ceiling.
* **The word lists are what four drafting offices printed**, not a lexicon of English. A fifth office
  will need them extended, and the four-set gate is where that must be measured.

## Verification

`pytest -q tests/test_phase29_keynote_wiring.py tests/test_keynote_callouts.py
tests/test_grid_lattice.py tests/test_four_set_coverage.py` — green. No paid API was invoked at any
point; every number above comes from reading the PDFs on disk.

**Non-vacuity, checked not assumed.** With the wiring gated off (`if False and ...`), four of the new
tests go red — the ladder row, the ladder-vs-hatch distinction, the SYM-4 suppression, and the bundle
evidence — and the two property tests that stayed green were then strengthened so they cannot pass on
an empty publish (`assert keynotes` / `assert "KEY-9" in groups`).

## Requirement status

**V5-FIX-02 delivered on the deterministic side.** T-29-03-06 (the ~$0.82 paid Crow re-run, expected
Ladder — → 1 flagged, overall 40% → 50%) is **NOT run** — paid runs are the operator's call. The
prediction stands as written; anything else that moves in that run is a finding, not a win to claim.
