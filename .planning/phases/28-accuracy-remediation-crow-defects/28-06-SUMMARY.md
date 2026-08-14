---
phase: 28-accuracy-remediation-crow-defects
plan: 06
status: complete
requirements:
  - V4-FIX-05
completed: 2026-08-07
closed_out_by: orchestrator (the executing agent was cut off by a usage limit after its final code commit; no work was redone)
---

# 28-06 Summary — every quantity states the route it came by

## What shipped

Five commits, all landed before the interruption:

| commit | |
|---|---|
| `85afdb3` | test (RED) — a published number must say which route produced it |
| `26bee89` | feat (GREEN) — roll the route onto every published row |
| `ca9d6c9` | test — hold the classification to what the two saved runs actually did |
| `d281755` | test (RED) — `summary.txt` must name the numbers a repeat run may move |
| `e4b4b6f` | feat (GREEN) — say it in the artifact a human reads |

`quantity_route` now rides on every published row beside `provenance`. Three constants: measured off
the drawing, copied out of a table printed on the plans, or read off a sheet by a model. **Only the
third is a route a re-run may answer differently** — which is precisely the disclosure V4-FIX-05
asks for.

**Two fields, two questions.** `provenance` says what a client should make of a row (MEASURED /
NEEDS REVIEW / NOT MEASURED). `quantity_route` says how the number was *produced*, and therefore
whether a repeat run reproduces it. The 3-of-51 quantity deltas between two identical paid Crow runs
turned on exactly this distinction, and the four-value provenance vocabulary cannot express it.

## Three design decisions worth recording

1. **The roll-up is the MIRROR of `_stronger_corroboration`.** Where corroboration takes the *best*
   witness, reproducibility takes the *least* reproducible contributor — because reproducibility is a
   property of the weakest link, whereas corroboration is a property of the strongest. Same
   accumulation loop that already rolls up confidence, corroboration and region: one mechanism, not a
   new one.

2. **It keys on recorded `provenance` + `qty_source`, never on description text.** In the two saved
   runs the *same* 136-count cluster is described as `personnel door` in one and `DOOR` in the other
   at an identical count. Keying on the text would have manufactured a difference where the number
   never moved.

3. **A blank carries no route** — and neither does a withheld number or an app-injected convention
   like Mobilization. There is no number to characterise, so the field is absent rather than
   defaulted. Same empty-contract discipline as `_coverage_lines` and `_unnamed_geometry_lines`.

## The plan's stronger claim is FALSE, and is not asserted

The plan predicted that *every* quantity that moved between the two runs would classify as the
model-reading route. It does not hold, and 28-01 had already measured the same fact from the
corroboration side:

> `Door Frames-HM` — run A published **4.0 EA** off a row recorded `provenance: geometry`; run B
> published **nothing**, because the backing row was never extracted at all. **The number did not
> move — the ROW vanished.**

Row *presence* is a second axis, and no per-run route classification can see it. The gate therefore
asserts the honest three-way disjunction and names the falsification in its docstring rather than
scoping around it. `.planning/ROADMAP.md`'s 28-06 line was narrowed to match before this plan was
marked done.

## Reaching a human

A REPRODUCIBILITY section in `summary.txt` (immediately after PROVENANCE BREAKDOWN, whose question it
extends) and a `quantity_route` column on `takeoff_summary.csv`. A human reads `summary.txt`, not
`takeoff.json` — the route is worth nothing as a JSON key alone.

One subtlety that took a deliberate decision: the section is **absent** from a report whose rows carry
no route at all, so a pre-28-06 report renders byte-identically — but **present with explicit
no-rows wording** when the field exists and nothing took the reading route. *An absent section and a
clean run must not look the same.*

## Verification

Assertions are falsifiable predictions over frozen evidence, computed at runtime from the two saved
paid runs (`.planning/paid-run-evidence/`, read-only) — the differing keys are never typed in.
Deterministic provenance values are cross-checked against fusion's own set rather than restated.

Full offline suite: see the closing commit; all four standing gates
(`test_phase23_acceptance`, `test_phase24_acceptance`, `test_four_set_coverage`, the 24-09
determinism harness) green. No paid API was invoked at any point.

## Requirement status

**V4-FIX-05 delivered as narrowed.** Every published quantity states its route, and the artifact a
human reads names the numbers a repeat run may answer differently — with the row-presence axis it
cannot cover stated as a limit rather than hidden.

## Handover note

This plan was closed out by the orchestrator after the executing agent hit a usage limit immediately
following `e4b4b6f`. Its code and tests were already committed; only this SUMMARY and the pending
ROADMAP edit remained. Nothing was re-implemented, and no assertion here was written without reading
the commit that backs it.
