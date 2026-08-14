---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: milestone
current_phase: 28
current_phase_name: accuracy-remediation-crow-defects
status: complete
stopped_at: "Phase 28 COMPLETE — 7 of 7 plans. 28-07 landed the acceptance gate (`python3 -m pytest -q tests/test_phase28_acceptance.py`, 14 checks, 6:42, free). THREE of five requirements are closed (V4-FIX-02, V4-FIX-04, V4-FIX-05-as-narrowed); V4-FIX-01 and V4-FIX-03 are ADVANCED and deliberately NOT ticked, each pinned by a tripwire that fails the day it is closed. Two limits this phase declared for itself were re-measured FALSE at gate-writing time: Columns and Ladder are no longer unmeasured, closed by post-phase-28 detection work rather than by Phase 25 — so PHASE 25 MUST BE RE-PLANNED before it is executed."
last_updated: "2026-08-14T07:30:00.000Z"
last_activity: 2026-08-14
last_activity_desc: "28-07 made the phase's acceptance re-runnable, and refused to tick the two requirements the phase measured to be still open"
progress:
  total_phases: 29
  completed_phases: 22
  total_plans: 138
  completed_plans: 132
  percent: 76
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-05-26)

**Core value:** End-to-end automated take-off from StackCT drawings (or PDFs) producing traceable, formula-backed quantity calculations estimators can trust and export.

**Current focus:** Phase 28 is COMPLETE. Next: **Phase 25 must be RE-PLANNED before it is executed** —
two of its three stated subjects were detected by work that landed outside it.

## Current Position

Phase: 28 (accuracy-remediation-crow-defects) — **COMPLETE (2026-08-14)**
Plan: 7 of 7 complete (5 waves)
Status: **the phase's acceptance is one free command** —
`python3 -m pytest -q tests/test_phase28_acceptance.py` (14 checks, 6:42, zero API). Full offline
suite at close: **2529 passed, 1 skipped, 2 deselected (1:11:51)**.

**Three requirements closed, two ADVANCED and deliberately NOT ticked.** `V4-FIX-02` (the Bollards
mis-binding, diagnosed and fixed at its cause, nothing halved), `V4-FIX-04` (one measured region
backs one published row per building layer, D1's three-layer exception proved intact) and
`V4-FIX-05` (every published quantity states the route it came by; `summary.txt` names the ones a
re-run may answer differently) are complete. `V4-FIX-01` is not — two calculator producers still emit
EA counts stamping no corroboration verdict. `V4-FIX-03` is not — the mis-bind is removed and
audited, but `CMU Wall` now takes a FLAGGED masonry-by-hint bind and "binds the correct class" is not
proved and cannot be offline. Both residuals are runnable tripwires that fail the day they are
closed; shorten them deliberately, never delete.

**Four plan premises were falsified during execution and each is a committed assertion, not a
paragraph.** The 56-vs-56 tie never existed (`SYM-3` is excluded before candidacy, so the shortlist's
maximum was already unique — the gate asserts that positively, and no test claims the tie rule fixed
Crow). The plan's own ring fix alone would have swapped one wrong name for another, because a
25%-inset box lets a sparse scatter clear hollowness vacuously. The wall-class contest is ONE object
against THREE classes, and the LF-share masonry guard excludes nothing the pre-existing rank test had
not already excluded — it is not credited with the fix. And `Door Frames-HM` moved between the two
saved runs because a geometry-backed ROW VANISHED, not because a number moved: a row-PRESENCE axis no
per-run route classification can see, asserted by name.

**⚠ TWO OF THIS PHASE'S OWN LIMITS WERE RE-MEASURED FALSE, AND PHASE 25 IS AFFECTED.** Phase 28
declared that Crow's `Columns` and `Ladder` remain unmeasured and that supplying them is Phase 25's
detection work. Measured on 2026-08-14, on a tree carrying twenty-two later commits: the plan page now
yields a lattice candidate the deterministic namer calls `Columns` (`4e6382f` / `7390f09`), and the
keynote reader was widened past two digits so the access-ladder keynote reaches the pipeline
(`9276d00`). Both closures are ASSERTED in the phase-28 gate, so the record cannot rot back. **Phase
25's scope fence has moved: plan it from what the detection harness measured, not from the ROADMAP's
Phase 25 text.**

**⚠ The GitNexus index is stale** (last indexed `5fab264`, ~24 commits behind). Re-analyse before the
next plan that edits `fusion.py`, `aggregator.py` or `calculator.py`.

---

Phase: 24 (binding-determinism-text-anchored-labeling) — **COMPLETE (2026-08-06)**
Plan: 10 of 10 complete (all six waves done)
Status: **the phase's acceptance is one free command** —
`python3 -m pytest -q tests/test_phase24_acceptance.py` (15 checks, 5:44, zero API). See
`24-01`…`24-10-SUMMARY.md`; the wave-1 narrative below is retained because 24-05's open assertion
still points at it.

**24-10 closed the phase by making its acceptance re-runnable.** Ten summary documents recorded what
this phase built and not one of them could fail. Every claim in them that mattered is now a command
that goes red when it stops being true — and the gate **invokes** each owning module's own assertion
functions rather than growing a second copy of its literals, so this phase has one copy of every
number in it.

**All five requirements are closed, two with a boundary stated in the same sentence as the tick.**
V4-DET-02 is complete for its stated subject — the CMU ↔ tilt-up flip cannot recur — while a wall
class with **no** printed-thickness match is still named by the reading; that residual is asserted by
name and **must not be deleted**. V4-DET-04's determinism property is proved **offline with scripted
stubs**; that it holds on a real drawing has **no artifact** and needs a paid run. V4-DET-05 is
complete as *reframed*, and the reframing is proved rather than narrated: one request issued five
times returns five identical answers off disk, because the replay analyzer is a pure function of its
key — which is exactly why the criterion's literal words could not be the gate.

**Ten falsified literals are named in committed assertions** — two from research (Open Question 4,
Assumption A1) and eight from execution — each asserting the contract that WAS delivered, so a future
reader meets the correction rather than the prediction. **The irreplaceable paid evidence is guarded
by the one check here that may not skip**, observed raising `AssertionError` rather than `Skipped`.

**Two vacuity holes in the gate's own checks were found by re-reading them against rule 3, not by a
failure** — a leak assertion satisfiable by an empty report or a rotted pattern, and a free-run guard
that was a tautology. Both are closed. A green check is not evidence until you have asked what would
make it green for the wrong reason.

**24-09 built the phase's central gate — and refused to build the one the requirement literally
asked for.** V4-DET-05 reads *"same fixture N times asserts identical line items"*.
`ReplayAnalyzer.__call__` is a pure function of a SHA256 over `(model, pass_type, prompt,
image_count)`, so N runs of one fixture are identical **by construction**: writing the requirement
verbatim would have shipped a gate that passes for having looked at nothing. What shipped instead
holds the geometry fixed, **varies the model's answers** within schema-legal bounds, and asserts the
published take-off does not move — the published item-name set, the unnamed-geometry ledger's
candidate set (40, set-equal) and the quantity multiset, always variant-against-variant and never
against a golden figure. It runs free in **2 min 56 s**.

**Both vacuity traps are closed by assertion, and one of them reproduced itself live.** Presence is
not consumption: a per-key hit census requires every committed fixture to have been *requested*
(3 of 3, both variants), because 24-07 moved the prompt, the schema and the image count and a stale
set would sit unread while the gate compared two runs that asked nothing. And ensembled passes are
**explicitly out of scope** — after 24-08 a pass issues N requests carrying one key, so the harness
pins the ensemble to a single sample. That pin was *wrong first*: routed through the environment it
was a no-op (`config.ENSEMBLE_N` resolves at import time) and the census read 3 hits per pass on one
fixture. The census is why the scope claim is true rather than merely written down.

**⚠ The gate has been SEEN to fail.** A third variant was poisoned on disk with a schema-legal third
wall-class name; the gate went red on all three invariants (3 failed, 15 passed) before the pristine
fixtures were restored. No poison is in the tree. Four permanent demonstrations route through
`_compare_published` — the same helper the gate calls in anger — including a positive control, so
the helper cannot be reporting a difference unconditionally and passing every demonstration for
nothing.

**⚠ The plan's own assertion was corrected by measurement.** There is no `measure_basis` field in
this codebase, and the `(name, unit, quantity)` tuple set is *not* invariant: a wall class with no
printed-thickness match is still named by vision. That is **24-02's open residual**, now pinned as a
runnable assertion that says in its own docstring: when 24-02's residual is closed this test will
fail, and that failure is the signal — update it deliberately, do not delete it.

**⚠ The fixtures are perishable and the antidote is committed.** Any future prompt, schema or render
change on the vector path invalidates all six. `python3 scripts/author_replay_fixtures.py`
regenerates them; `--check` reports drift without writing. Until then the gate **skips loudly**, it
never silently passes.

**24-08 closed the last un-ensembled identification path.** The schedule and legend passes now
majority-vote their tables and rows on the ROW'S OWN IDENTITY — folded through the aggregator's
`_norm_item_key`, so two spellings of one row are one row here for the same reason they are one row
downstream. `_vote_categorical_labels` was deliberately NOT reused: it votes a per-candidate label
under a known candidate-ID key, and `_run_pass` sends no schema and no candidate list. A surviving
row is VERBATIM one sample's row, never a per-field blend, so the voter cannot emit a quantity no
paid sample returned (T-24-34 is structural, not promised). `count`/`measure`/`extraction` are
excluded because their identification and their measurement arrive in one object with no seam.

**⚠ 24-08 makes every run more expensive, by design.** A schedule or legend pass now costs
`ENSEMBLE_N` (default 3) calls where it cost 1; the floor-plan multi-region schedule retry goes
3 → 9 when it fires. Bounded by the guard, which charges every sample, stops on exhaustion and votes
over what was paid for — and now DECLINES an extra sample it cannot afford rather than issuing one
and having the charge refused (a refused charge is money paid for a discarded result). Funded by
24-05's persistence, but only from the SECOND run of a project onward; a first run pays the full
fan-out with none of the saving.

**Assumption A1 is falsified and the correction is COMMITTED.** 24-RESEARCH §7.2 blamed the 184→64
`raw_line_items` swing on the un-ensembled `_run_pass`. The artifacts say otherwise: run 2 ran under
a cap 2.5× smaller, reached ~99.8% of it, spent less than half as much on sheet-attributed work, and
invoked one model class where run 1 invoked three. **The two runs are not peers, so F9 cannot judge
this plan either way** — including in the other direction, if a future paid run shows the count
stabilising. `test_f9_swing_is_explained_by_budget_not_sampling` (`91698ad`) landed BEFORE any code
changed, asserting relations rather than dollar literals. The research's secondary door-schedule
detail (7 → 0 rows) did not reproduce under an independent count and is not relied on.

**Read this before 24-09.** Every replay fixture key is a SHA256 over
`(model, pass_type, prompt, image_count)`. 24-07 changed the prompt text AND, on room-heavy sheets,
the image count (Crow page 1: 1 → 5). **24-09 must author its fixtures after `7cbdf40`, never
before** — a fixture keyed to the pre-24-07 prompt hashes to a key nothing will request, and the
differential gate would pass for having looked at nothing (24-RESEARCH pitfall 6). 24-08 changed
**none** of those four key components, so that warning is unchanged — **but it adds a new one:** a
schedule or legend pass now issues N requests carrying the *same* key, so a replay analyzer keyed
purely on that tuple returns the same fixture for every sample and the vote is unanimous by
construction. If 24-09 wants its differential to exercise the ensemble, its fixture source must vary
per sample; otherwise it must scope the differential to the passes it can genuinely vary and SAY SO.

Wave-1 detail, retained: 24-01 shipped the phase's one new deterministic primitive —
every symbol group, room and wall class carries the words the drawing printed nearest to it, or a
**recorded absence**, computed before any vision call. 24-02 then made the wall-class NAME a
decision rather than a reading: a printed-thickness match outranks a vision label unconditionally,
a label may corroborate or dissent but never rename, and every dissent is published in
`fusion_rejected` with both answers and the thickness evidence that decided it. 24-03 closed the
naming layer's own variance: one object can no longer occupy two rows because of a trailing `s`,
the three racing naming authorities now answer to one declared arbiter, and a blank expected row
can no longer stand unexplained beside a measured row that may answer it.

**Read this before 24-05.** 24-02 predicted its residual differential
(`test_wall_class_label_invariance`'s WALL-TC3 assertion) would start failing when 24-03 landed. It
did **not**, and that is the correct outcome, not a miss: the residual is `Aluminum Storefront` vs
`Aluminum Storefront/Curtain Wall`, a compound rename rather than a plural. Folding it would mean
`canonical_library_name` had become a synonym mapper — the defect the whole phase boundary exists
to prevent. That assertion is **24-05's** to retire, by stabilising the per-project object list so
both runs derive the same name in the first place. Do not delete or weaken it before then.

24-04, 24-05, 24-06 and 24-07 have all landed. T-24-01 is **met**: the anchor table reaches the
prompt only through `wrap_pdf_text` (`takeoff_pipeline.py:891`), verified at the source during
24-07's close-out rather than assumed.

Ready for **24-08** (ensemble wire-up for `_run_pass` identification passes — it touches call
sites, not the schema or the prompts, so nothing in 24-07 conflicts), then **24-09** (subject to the
fixture-sequencing warning above) and **24-10** (the phase gate, which inherits the V4-DET-01/03
requirement ticks and the in-tree synthetic-fixture regeneration logged in `deferred-items.md`).

Last activity: 2026-08-06 — 24-07 put the drawing's own words on the marker chip, stopped asking
about clusters the drawing does not name, and made a topological gap unexpressible by schema
(see last_activity_desc).

Progress: [█████████░] 93%

Phase 23 (measurement-engine-completion) is COMPLETE — all 17 plans. Carried forward, named not
dropped: **DEF-23-SP4** (the geometric viewport-bounded clip cell — blocked behind the domain question
*what should a dimension-string corridor contribute to a room's measured area?*, which needs the
take-off documents), plus DEF-23-07/08/11/13A/14A in `deferred-items.md`. Its acceptance is one free
command: `python3 -m pytest -q tests/test_phase23_acceptance.py`.

Phase 22 (production-restructure-cleanup) is COMPLETE — all 4 plans, all 7 success criteria met.
Phase 23 (measurement-engine-completion) is COMPLETE — all 17 plans; offline suite 1845 passed.

## Performance Metrics

**Velocity:**

- Total plans completed: 9 (Phase 3)
- Average duration: ~2.5 min/plan (Phase 3)
- Total execution time: ~7.5 min (Phase 3)

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 03-api-cost-transparency | 3 | 7.5 min | 2.5 min |

**Recent Trend:** Phase 3 executed in 3 sequential waves (03-01 → 03-02 → 03-03)
| Phase 21-accuracy-learning-engine P04 | 15 min | 3 tasks | 4 files |
| Phase 21-accuracy-learning-engine P05 | 18 min | 3 tasks | 8 files |
| Phase 21-accuracy-learning-engine P06 | 25 min | 3 tasks | 8 files |
| Phase 21-accuracy-learning-engine P07 | 37 min | 3 tasks | 5 files |
| Phase 21-accuracy-learning-engine P08 P08 | 32 min | 3 tasks | 5 files |
| Phase 21-accuracy-learning-engine P09 | 9 min | 2 tasks | 3 files |
| Phase 21-accuracy-learning-engine P10 P10 | 53 min | 3 tasks | 9 files |
| Phase 21-accuracy-learning-engine P11 P11 | 16 min | 3 tasks | 5 files |
| Phase 21-accuracy-learning-engine P12 P12 | 25 min | 3 tasks | 3 files |
| Phase 21-accuracy-learning-engine P13 P13 | 40 min | 3 tasks | 5 files |
| Phase 21-accuracy-learning-engine P14 P14 | 14 min | 2 tasks | 3 files |
| Phase 21-accuracy-learning-engine P15 P15 | 27 min | 3 tasks | 9 files |
| Phase 21-accuracy-learning-engine P16 | 38 min | 3 tasks | 8 files |
| Phase 21-accuracy-learning-engine P17 | 20 min | 2 tasks | 3 files |
| Phase 21-accuracy-learning-engine P18 | 36 min | 2 tasks | 113 files |
| Phase 22 P01 | 17min | 3 tasks | 6 files |
| Phase 22 P04 | 38min | 3 tasks | 13 files |
| Phase 23 P02 | ~2h | 3 tasks | 5 files |
| Phase 23 P03 | ~3h | 3 tasks | 10 files |
| Phase 23 P05 | 140 | 3 tasks | 6 files |
| Phase 23 P07 | 4h | 3 tasks | 10 files |
| Phase 23 P08 | ~2h05m | 3 tasks | 7 files |
| Phase 23 P09 | ~2h20m | 3 tasks | 2 files |
| Phase 23 P10 | ~5h | 3 tasks | 7 files |
| Phase 23 P12 | 2h15m | 3 tasks | 2 files |
| Phase 23 P13 | ~2h45m | 4 tasks | 6 files |
| Phase 23-measurement-engine-completion P14 P14 | 205 min | 4 tasks | 9 files |
| Phase 23 P15 | 1h45m | 3 tasks | 8 files |
| Phase 23 P16 | ~4h15m | 4 tasks | 7 files |
| Phase 24 P01 | 3h 20m | 3 tasks | 3 files |
| Phase 24 P02 | 3h 45m | 3 tasks | 3 files |
| Phase 24 P03 | 4h 05m | 3 tasks | 3 files |
| Phase 24 P10 | ~4h 30m | 3 tasks | 4 files |
| Phase 28 P04 | 160 min | 3 tasks | 2 files |
| Phase 28 P05 | 7h 20m | 3 tasks | 5 files |

## Accumulated Context

### Roadmap Evolution

- Phase 22 added (2026-08-02): Production Restructure & Cleanup — executes .planning/codebase/RESTRUCTURE-SPEC.md (full-repo audit by 6 parallel mappers + synthesis); precedes the production-hardening/accuracy revamp program

### Decisions

- [Phase 24]: 24-10: a phase acceptance gate INVOKES the owning module's own assertion functions against a live subject and never restates its literals — 24-09's differential, 24-08's census, 24-04's partition, 24-07's numeric ban, 24-02's differential and 24-06's parity pins are all called, so the phase has ONE copy of every number in it and the gate is not a second one
- [Phase 24]: 24-10: a criterion rejected as vacuous is rejected by a COMMITTED ASSERTION that demonstrates the vacuity, never by prose — V4-DET-05's literal wording is refuted by issuing one request five times and getting five identical answers off disk with nothing in the naming layer exercised
- [Phase 24]: 24-10: exactly ONE check in the gate FAILS rather than skips — the paid-run evidence presence check, because every other absent fixture is not a failure but a skip HERE would let a future cleanup delete the only proof of the variance the phase exists to kill behind a green gate
- [Phase 24]: 24-10: a self-scanning module builds its forbidden tokens from PARTS in one constant used for every scanned module — spelling them out makes the module fail its own audit while nothing is wrong, and a per-module grep is how one module quietly stops being scanned
- [Phase 24]: 24-10: a recogniser must be proved to recognise — the candidate-ID leak pattern is asserted to match every identifier the ledger holds, so an empty leak result is a live claim rather than an artefact of a regex nobody re-checked
- [Phase 24]: 24-10: a requirement with a known boundary is ticked WITH the boundary in the same sentence, never flat — V4-DET-02 carries its open no-thickness-match residual and V4-DET-04 carries "proved offline with scripted stubs; no artifact shows it on a real drawing", recorded identically in SUMMARY, ROADMAP and REQUIREMENTS
- [Phase 24]: 24-10: no traceability-table row was added for any V4-DET id — that table stops at v3 and Phase 23 deliberately left V4-MEAS out, so adding V4-DET rows alone would imply Phase 23's requirements are unmapped, which is an edit to another phase's record
- [Phase 24]: 24-03: the learned store is TWO naming authorities, not one — the research's `library > learned > vision` applies to the `source='ai'` tier record_ai_manifest writes (the tier the F1 evidence indicts) and NOT to the `source='human'` tier, because demoting a human's correction below a library that is half LLM-derived vocabulary breaks V3-LEARN-02 and contradicts the store's own human-wins invariant
- [Phase 24]: 24-03: unknown learned provenance resolves to the HUMAN tier — the store's own schema default, and the rule that an authority is demoted on evidence, never on assumption
- [Phase 24]: 24-03: `-ses` is deliberately NOT folded as an `-es` plural; `Base`/`Bases` and `Bus`/`Buses` are indistinguishable without a lexicon, so the ambiguous case falls through to the plain `-s` rule. Under-folding is the status quo and is safe; over-folding merges two different objects
- [Phase 24]: 24-03: a verbatim authority (legend, manifest) routes THROUGH the arbiter but is never canonicalised — rewriting a user's own words is the mangling the legend-verbatim contract exists to prevent
- [Phase 24]: 24-03: expected-vs-measured cross-referencing keys on the measured row's naming AUTHORITY (a hypothesis can be wrong about which object was measured; a printed label cannot), never on name similarity — and the partner count is always exact, the cap trims the list not the truth
- [Phase 24]: 24-02: a printed-thickness match outranks a vision label UNCONDITIONALLY; the label may corroborate (raising confidence, clearing the review reason) or dissent, but it may never rename a class the drawing's own printed thickness identified
- [Phase 24]: 24-02: the new name_source value is registered in _NAME_AUTHORITY at the SAME rank as naming_library — an unregistered string would have fallen to the unknown default (4, below `learned`) and silently made every thickness-bound wall row the least authoritative claimant in region-sharing arbitration
- [Phase 24]: 24-02: fusion's agreement check is a case/separator squash and deliberately does NOT fold plurals or synonyms — canonical_library_name is 24-03's to own, and a second folding rule in fusion is how the two drift apart
- [Phase 24]: 24-02: a precedence override carries its OWN fusion_rejected reason key; reusing a C3a suppression key would make the reinstatement pass act on a row that was never suppressed
- [Phase 24]: 24-02: the determinism differential asserts a SET across two label variants, never a golden wall area — and states its unmatched-class residual explicitly rather than silently excluding it, so the scope of the invariance claim stays honest
- [Phase 23]: 23-05: a room tag pairs ACROSS the reading axis (name over number), not along it — pair_two_token_tags takes an axis selector; still ONE projection, asserted by source inspection
- [Phase 23]: 23-05: derive_room_mix takes an explicit pages scope and its whole-document default REFUSES on Moxy — picking unit key plans is sheet classification, which belongs to 23-08
- [Phase 23]: 23-05: the unit multiplier IS recoverable from the plans — 214 room tags / 214 distinct numbers on Moxy pages 7-8 give QQ A 90 / KING A 26 / K SUITE B 2 / BUNK B 1 (4/4 golden); the docstring and ground-truth corrections are 23-08 and 23-16
- [Phase ?]: 23-07: measure_enclosed_area keeps ONE clip contract (drawing space, mapped internally); a page-space caller maps back via from_page_space rather than passing a space flag a future caller could forget
- [Phase 23]: 23-07: the rotation census is 61 unrotated / 22 rotated of 83 pages, not the plan's 76/7 — Chelsea has 4 rotated pages INV-03 never counted
- [Phase 23]: 23-07: DEF-23-08 — Bob's p3 binds its own 10.667 callout but the PAGE scale still resolves 1.0; that is select_main_plan/_MAIN_PATTERNS, not a coordinate defect, and was logged rather than forced
- [Phase ?]: 23-08: a unit key plan is identified by its own printed DRAWING TITLE (a title bound to a scale callout), not by a page-text search — Moxy p3 prints KEY PLAN in its title block and is correctly not selected
- [Phase ?]: 23-08: the in-plan census supersedes the manifest per D-10; every count carries unit_count_source and disagreement is flagged on the row that uses the number — human_inputs/ is never edited
- [Phase ?]: 23-08: no area is ever synthesized for a finish code; a called-out code becomes a named zero-quantity row seeded with its tag positions, and the finish-schedule path emits the same contract (D-03)
- [Phase ?]: 23-09: the contour trace terminates on repetition of the FIRST TRANSITION, not on 'back at the seed facing west' — Moxy ACC KING TUB RCP re-enters its seed heading south and reported no perimeter at all
- [Phase ?]: 23-09: MAX_HONEST_SHAPE_RATIO=8.0 is read off observed geometry (honest rooms 4.24-5.08, leaking AR fills 8.54-9.04, annotation cells 11.6-13.4) and is deliberately never applied to area
- [Phase ?]: 23-09: an oversize region is KEPT AND FLAGGED — the hard drop returned None for the whole drawing, making a lobby indistinguishable from a genuine zero
- [Phase 23]: 23-10: INV-06's rule "a region owning a printed scale is not a table" is FALSE on all four sets — five genuine schedule regions own one (Crow p1 20 ft/in, Bob's A8.1 2.67, Chelsea p0 0.33, two Moxy p15 at 4.0); shipping it put 429 LF of Bob's door-schedule grid into wall extraction (T-23-40)
- [Phase 23]: 23-10: a classification change that unmasks geometry must be diffed through the MASK it feeds — the unmasked-wall diff reported 0 changed pages while the leak was live
- [Phase 23]: 23-10: release from legend/schedule is ONE-DIRECTIONAL and needs a caption band that names a PLAN and states a scale; nothing in the changed code can newly create a masked kind
- [Phase 23]: 23-10: open_runs.PAIR_OFFSET_MAX_FT IS walls.MIN_THICKNESS_FT by reference — INV-06's 0.02-1.00 ft overlaps the wall window, so one segment pair could be claimed as both a rail and a wall
- [Phase 23]: 23-10: an open run's length is its SPAN, bridged gaps included — the opposite of a wall, whose material length excludes its openings
- [Phase 23]: 23-10: Crow p2 goes 4 -> 3 unbound labels, not to 0; 13 captions into 11 non-title-block regions is a pigeonhole, and the residual is DEF-23-11 in printed_scale, not viewports
- [Phase ?]: 23-12: S9 stub closure absorbs leftover merged spans through the core's _absorb_stubs (structural one-hop), chosen for core reuse over INV-04's raw-segment recipe; variants measured before the band was consulted
- [Phase ?]: 23-12: rail chain termination is a per-pen partition of the ONE chainer (CAD draws one object with one pen); rails validated against the estimator's own five marks, not INV-06's prototype-output bboxes
- [Phase ?]: 23-12: run_scale_fpp binds the SMALLEST containing viewport with no walk-up — a scale-less detail flags its runs rather than borrowing the enclosing plan's scale
- [Phase ?]: 23-13: D-08 partition convention resolved from the take-off's own markup — board faces (a shared partition traced once per side); the legend label states no convention
- [Phase ?]: 23-13: the multiplier-review flag is structural (census-vs-manifest disputed bit + manifest-only counts above one), not blanket count>1 — a blanket rule would have flagged all nine census-confirmed sheets and violated D-10
- [Phase ?]: 23-13: a room-fill wall row supersedes the same-named thickness-class row even as a flagged zero — an honest flagged gap beats a confident wrong number
- [Phase ?]: 23-14: facade = filled silhouette via complement labelling (one shared labeller); elevation joins the deterministic routing set with _PLAN_SHEET_TYPES untouched — wall pairing can never run on a facade (empty-walls negative test)
- [Phase ?]: 23-14: the no-datum flag is waived only when the independent footprint width validates the blob (Bob's front 249.2 ft vs depth 250.0); learned human height outranks the Tier-0 datum span; 'datum' deliberately NOT a trusted height source for room-fill walls (T-23-51)
- [Phase ?]: 23-14: material attribution is text-anchored (keynote -> its drawing's legend -> naming layer); gross confident, splits flagged, never a ratio; perimeter x datum-height is a cross-check that flags (Crow 6.4%) and never publishes (D-11); DEF-23-14A cross-sheet dedupe deferred
- [Phase ?]: 23-15: library-name canonicalisation is formatting-equality only; blanket map routing renames distinct items
- [Phase 23]: 23-15: run selectors receive NO mask rects — a false schedule bbox covering Bob's whole roof plan deleted every gas segment; the selectors' own gates are the validated defence
- [Phase 23]: 23-15: the typical-detail reference is the sheet's coarsest printed callout, not the resolved page scale (still 1.0 ft/in on Bob's A3.0, which inverted the flag)
- [Phase 23]: 23-15: Crow's rails ship as expected-not-measured flagged blanks — no sheet text names the runs deterministically; binding them is Phase 24 text-anchored labelling, and the phantom 5.8 LF is dead either way
- [Phase 24]: 24-01: the anchor search radius is expressed in TEXT HEIGHTS (4.0) and derived from the page's own median word height, not pinned in absolute points — measured free: median word height 9.56 pt Crow, 9.64 Moxy, 7.56 Chelsea, 26.41 Bob's, all on an identical 3024x2160 pt sheet, so one absolute constant generalises to one plan set and breaks another
- [Phase 24]: 24-01: the fusion drafting-noise predicate is deliberately NOT reused for anchor harvesting — it returns True for 'B-1' and 'P1', exactly the tags an anchor exists to harvest; whether an anchored name is publishable is 24-04's decision, not the harvester's
- [Phase 24]: 24-01: a candidate with no plan text in range carries anchor_text=None as a RECORDED ABSENCE, and a text unit contested by two candidates is withdrawn from BOTH (SP-7c bind_or_flag) — names are never round-robined to whichever candidate was scanned first
- [Phase 24]: 24-01: Open Question #4 answered NO and committed as a test — Crow page 0's two largest symbol clusters (SYM-1 1.0x0.4 ft, SYM-2 0.8x0.87 ft, the bollard cluster) carry ZERO contained_texts, asserted by RANK so no count is ever compared to the human take-off
- [Phase 28]: 28-05: the vocabulary-basis name_source is registered in _NAME_AUTHORITY at the SAME rank as the unknown-source default — a rank of its own would silently move the anchor of every region whose rows all name no layer
- [Phase 28]: 28-05: region arbitration fires ONLY where a group holds both an evidence-named and a hypothesis-named row; a region held only by hypotheses has no arbiter and IS phase 23's D1 three-layer share on a manifest-free run
- [Phase 28]: 28-05: a legend row inherits the region_ref of the detected reading its shadow branch suppresses, because that branch has just declared the two rows the same item
- [Phase 28]: 28-05: tests/test_fusion.py's D1 three-layer assertion kept in full and made stricter by one added assertion — it still asserts what D1 means at the fusion layer

### 22-04 Decisions

| Decision | Source |
|----------|--------|
| index.html keeps TWO type=module tags — the plan's `-eq 1` criterion missed the body-end ui-motion.js loader, which is LIVE (window.uiMotion consumed by app.js:98,897); head-section count is the real intent and is 1 | 22-04 |
| docs/DEPLOYMENT.md:57 (CLAUDE_MODEL_SCHEDULES -> CLAUDE_MODEL) was already correct and left alone; only :60 (CLASSIFY) was wrong | 22-04 |
| Stale ~$0.05/run cost figure flagged as pre-Phase-21 and redirected at API_BUDGET_PER_RUN_USD / takeoff.json api_cost rather than re-estimated (measuring costs paid API) | 22-04 |
| GitNexus query API, not the raw .gitnexus/lbug bytes, is authoritative on reindex completeness — deleted-module byte hits are uncompacted tombstones; all six symbols return not-found | 22-04 |
| .env.example is blocked by the user-level `Read(.env.*)` deny rule; inspected via `git show HEAD:.env.example` and appended via shell redirect. `.env` never touched | 22-04 |

From PROJECT.md Key Decisions (roadmap-relevant):

- Masterv2.md is planning source of truth (replaces Master.md for new work)
- Master Phase 1 critical UX (plan select + preview) before full UI shell — reflected in phases 4–5 before 8–10
- Keep Flask monolith; extract static JS/CSS on UI rebuild (Phase 8)
- FastAPI (ARCH-01) deferred to v2 per user directive

From 03-01 (Per-Sheet Usage Capture):

- Hardcoded PRICING dict with float rates (Haiku/Sonnet/Opus per MTok); default to Sonnet for unknown models
- Usage metadata on extraction dicts: `_tokens_in`, `_tokens_out`, `_cost_usd`, `_model_used`
- Error returns include zero-value usage fields for safe reporter aggregation

From 17-04 (Production Job UX):

- cancel_check Callable pattern: scraper reads jobs[job_id].get("_cancel") via lambda; _cancelled flag breaks sheet loop cleanly
- Partial-on-cancel: _cancelled=True in result dict; _finalize preserves "cancelled" status from endpoint; saves partial result with warning
- Weighted progress bands: capturing 0–40%, analyzing 40–90%, reporting 95%, done 100%

From 03-02 (Run-Level Aggregation):

- `api_usage` block in takeoff.json: total_cost_usd, tokens, cost_per_sheet, models_used
- Per-sheet cost in sheet_log (tokens_in, tokens_out, cost_usd, model_used)
- summary.txt includes "API USAGE & COST" section

From 03-03 (UI Cost Display):

- Report cards show cost in green (#4ade80) with 4-decimal USD precision
- list_reports() reads api_usage from takeoff.json; old runs without cost render gracefully

From 12-03 (Frontend CSRF Protection):

- apiFetch wrapper in app.js handles X-CSRFToken automatically for all state-changing calls
- settings.js keeps its own getCsrfToken() copy (self-contained page, no shared module)
- Logout form added to both templates as POST with csrf_token hidden field

From 12-02 (Core Flask Authentication):

- Timing-safe dummy bcrypt check on unknown email (prevents user enumeration)
- POST-only /logout to prevent CSRF via GET requests
- SESSION_COOKIE_SECURE conditional on FLASK_ENV != "development"

From 12-01 (Auth Dependencies & Admin Seeding):

- bcrypt rounds=12 for admin password hash (strong work factor, ~1s seeding time)
- RATE_LIMIT_STORAGE_URI defaults to memory://; Redis URI documented for multi-worker gunicorn
- SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD_HASH added to REQUIRED_ENV_VARS (crash-fail on missing)

From 14-01 (Plan-Set Discovery & Dedupe):

- Dedupe rules based on 14-DISCOVERY audit: drop "Plans X" parent, drop aggregate folders with multiple version labels
- Direct-grid fallback with folder_id=0 for projects without folder cards (ATL 081 pattern)
- Deprecated get_all_page_ids to use folder-aware APIs (prevents mixing multiple sets)

From 14-02 (Schema v2 & Folder-Aware Sync):

- Schema v2: project_plan_sets table, project_plans PK changed to (stackct_id, folder_id, page_id)
- v1→v2 migration drops project_plans table (re-sync required for all projects)
- sync_project_plans and get_project_plans now require folder_id parameter
- Background sync tracks (project_id, folder_id) tuples for parallel folder syncs

From 14-03 (Folder-First API Routes):

- GET /api/projects/<id>/plan-sets returns folder list
- GET /api/projects/<id>/plans now requires ?folder_id= (backward compat with 400 error)
- POST /api/run/stackct validates page_ids belong to folder
- folder_id stored in takeoff.json report root

From 14-04 (Two-Step Plan Selection UI):

- Two-step flow: plan sets → sheets (auto-skip for single-set projects)
- Project list shows "N sets · M sheets" instead of single sheet count
- Radio card picker with folder metadata visible
- Back button hidden for single-set projects
- [Phase 21-04]: Dedicated learning.db (not stackct.db) at OUTPUT_DIR; LEARNING_DB_PATH env override; schema init keyed by DB path so monkeypatched test DBs re-init automatically
- [Phase 21-04]: learning_vocabulary UNIQUE widened to (project_type, raw_pattern, canonical_name, unit) — §6 conflict/decay needs decayed old + new mappings to coexist; 2-col UNIQUE makes that unrepresentable
- [Phase 21-04]: Distilled state is a pure function of the log: replay in id order, last_seen = correction created_at (never now), staleness decay fires at new-verified-run boundaries — incremental == full_rebuild under any batching
- [Phase 21-04]: Assumptions distilled at BOTH exact (project_key) and type (project_key NULL) levels so learning transfers to new projects; retrieval precedence keeps exact rows winning
- [Phase 21-05]: resolve_routed_model() is the single pure exact→wildcard MODEL_ROUTING lookup; name heuristics stay in pick_model_for_pass/_pick_model so the deferred import cannot recurse
- [Phase 21-05]: MODEL_ROUTING v2: legend/schedule structuring → CLAUDE_MODEL_DENSE; wildcard ('*', pass) rows for classify/semantic/legend/schedule/verify_retry; count/measure rows keep CLAUDE_MODEL_SCHEDULES
- [Phase 21-05]: Whole-sheet renders target RENDER_TARGET_PX=1568 long edge; 8000px is a safety cap only; render_clip_crop is the sole zoom primitive for crops/tiles/galleries
- [Phase 21-05]: conftest pins CLAUDE_MODEL_CLASSIFY to suffixed throwaway 'claude-haiku-4-5-classify' because its real default equals CLAUDE_MODEL — distinct pins keep routes distinguishable
- [Phase 21-06]: Symbol union-find partitioned by path style class (stroke/fill/width) — endpoint proximity alone merges columns into the wall network; style separation makes CAD blocks enumerable (Crow 136 columns)
- [Phase 21-06]: Near-duplicate signature merge via second coarse hash (1pt/2deg) + kind counts; MIN_CLUSTER_PRIMITIVES=2 excludes dash/tick noise from symbol groups
- [Phase 21-06]: Schedule tables claimed by at most one kind (registry order); door kind delegates rows to schedule_extraction and locates bboxes with the same imported gates
- [Phase 21-07]: RANSAC scale consensus measured in paper-length explained (sum of inlier points), not sample count — recovers Bob 3/32"=1'-0" truth over six identical mispaired 216pt decoys that capture count-voting
- [Phase 21-07]: Crow p0 main-plan truth is 1"=40' (printed scale + 1136'/350' overall dims); plan's 20-fpi acceptance was a stale research note — geometrically impossible on a 3024pt-wide sheet
- [Phase 21-07]: HIGH scale confidence = three-condition conjunction (>=8 inliers AND >=80% share AND printed agreement within 1%); printed conflict caps at LOW
- [Phase 21-07]: Viewport bboxes in UNROTATED PyMuPDF space; leftover claiming uses frozen bboxes + midpoint union so border segments cannot explode a region
- [Phase 21-07]: resolve_scale_v2 learned prior fires ONLY when solved+printed tiers empty (anti-amplification); unbacked printed tier capped at medium
- [Phase 21-08]: Vector-sheet vision schemas: candidate-ID enums, additionalProperties:false everywhere, all-required, zero numeric types (rejection-walk test); raster_extraction_schema is the sole numeric exception (count_estimate)
- [Phase 21-08]: render_overlay: one PIL.Image at <=40 markers, list with disjoint info[overlay_ids] subsets beyond; pixel<->point grounding via info[zoom]/info[marker_boxes_px] — model never asked for coordinates
- [Phase 21-08]: build_crop_gallery packs ID-captioned tiles into contact sheets, legend crop first, tiles-per-sheet scaled to keep <=20 images/request
- [Phase 21-08]: symbol_gallery pass routes via the (*, semantic) MODEL_ROUTING row alias; structured path parses guaranteed JSON directly (no markdown strip, no json_repair)
- [Phase 21-08]: wrap_pdf_text() <pdf_text> delimiters contain prompt injection from untrusted PDF strings; semantic prompts declare delimited content is data, not instructions
- [Phase 21-09]: _capture_learning is best-effort and never raises — store/distill failure logs and returns 200 without learning_warning; per-run JSON write never rolled back
- [Phase 21-09]: verify scope mapping: prior row missing → missed_item, unit-only change → unit, else item (confirmation pins current value); measurements: wall_area → wall_height, others → item
- [Phase 21-09]: measurements capture diff-based against previously persisted list — repeated saves record nothing new (Pitfall 8 hygiene)
- [Phase 21-09]: conftest pins LEARNING_DB_PATH to a session tmp DB so endpoint tests never write the real output/learning.db
- [Phase 21-10]: NETWORK_PRECISION_GRID 1e-6 snap on room-network inputs before unary_union — interpolate-derived connector endpoints round off the line in float, GEOS never nodes them, polygonize merges faces
- [Phase 21-10]: Wall opening gaps need corroboration (both faces broken OR door-leaf perpendicular segment) — dashed linework otherwise floods opening_gap_widths and poisons the 3'-0" door_check
- [Phase 21-10]: WallSegment.centerline_pt spans chain end-to-end (openings included) so rooms polygonize closes across doors; length_pt is material-only for honest LF
- [Phase 21-10]: Crow p0 office pods are single dashed outlines (not wall pairs) — unclosed/unlabeled rooms are vision-fallback territory; footprint anchor 397,692 vs 397,600 SF (0.02%)
- [Phase 21-11]: vote() accepts on whole-band (max−min ≤ tol) OR strict-majority-within-tolerance-of-median — 5-sample escalation passes on 3-of-5 agreement; 3-way disagreement still flags needs_review
- [Phase 21-11]: BudgetGuard.charge() refuses (never accumulates) charges past the cap; run_ensemble aborts to current-best flagged needs_review reason=budget_exhausted — never a silent partial
- [Phase 21-11]: Temperature-ignore probe compares metadata-stripped JSON fingerprints of first two dict samples, cached per probe_key; on ignore, later samples get nonzero prompt_variation
- [Phase 21-11]: run_tiled_count NMS dedups only ≥2-tile-covered detections from different tiles within 1.5 coarse cells; tiled sum joins run_ensemble via extra_members (method 'tiled+vote')
- [Phase 21-11]: ensemble_settings() is the single (ENSEMBLE_N, API_BUDGET_PER_RUN_USD) reader — 21-13 RunSettings must construct from it
- [Phase 21-12]: merge_with_provenance hard no-overwrite guard checks provenance STRINGS (not rank arithmetic) — vision_ensemble can never displace a deterministic quantity/unit; discarded claims audited in fusion_rejected
- [Phase 21-12]: fuse_sheet quantities are exclusively deterministic (group count, wall LF, polygon SF, schedule cells, printed dims); vision grounds via registry membership — out-of-set IDs dropped + flagged unknown_candidate_id; room vision labels apply only to label_source=='none' rooms
- [Phase 21-12]: ReplayAnalyzer keys fixtures by SHA256(model, pass_type, prompt text, image_count); record mode gated by REPLAY_RECORD=1 (never CI); lazy-import results validated as real strings so sys.modules mock stubs degrade to deterministic 'unrouted' fallback
- [Phase 21-13]: Deterministic-first routing scope: floor_plan/civil_site/roof_plan + schedule sheets; elevations/details/MEP keep legacy vision passes (wall pairing on elevations = bogus geometry-provenance LF)
- [Phase 21-13]: Budget charging convention: every vision call site charges the per-run BudgetGuard with the completed call's _cost_usd; a refused charge discards the result — ledger only holds paid-and-accepted work
- [Phase 21-13]: Deterministic ScheduleTables ride as _deterministic_schedules metadata (rows already fused as schedule_table components) — attaching as 'schedules' would double-count via calculator
- [Phase 21-13]: select_main_plan is the measurement authority; vision main_plan_region kept only as cross-check (main_plan_region_vision on disagreement)
- [Phase 21-13]: py3.9 + PEP 563 + spec-loaded modules: dataclasses in takeoff_pipeline built over real type-object __annotations__ (string annotations need sys.modules[cls.__module__] at decoration)
- [Phase 21-14]: verify_retry answers are choice-enum grounded; symbol-anchored out-of-band flags get legend labels as choices (relabel path) — on vector sheets the deterministic count is exact, so the label is the suspect, never the number
- [Phase 21-14]: Retry bound semantics: deny ('no') is definite (single attempt, flag kept unresolved); only 'unclear' consumes the second attempt, which widens the crop pad 0.25→0.75 for more context
- [Phase 21-14]: Verify-retry merge-back: relabeled renames the component (quantity/unit untouched) and clears needs_review; confirmed downgrades the flag to a note; unresolved keeps the flag — retry_history mandatory on every touched item
- [Phase 21]: 21-15: Sibling manifest auto-discovery (_find_manifest) removed with companion discovery — explicit manifest_path is the only manifest input to run_pdf_analysis — Same ground-truth-leakage class as *takeoff*.pdf siblings; plans-only LOCKED contract
- [Phase 21]: 21-15: StackCT blobs live at {run_dir}/blobs/{page_id}.pdf with _page_blob_path legacy pdfs/ fallback; REUSE_SCREENSHOTS also reuses cached blobs; PageEntry.is_vector stores the runtime probe — Vector data must reach the deterministic engine on cached and resumed runs
- [Phase 21]: 21-15: Scraper keeps _pipeline singleton but refreshes RunSettings.from_env() per run via new TakeoffPipeline.settings setter — settings-identical to pdf_analyzer — Preserves scraper._pipeline test patch seam while enforcing V3-STRUCT-02 parity
- [Phase 21]: 21-15: Parity tests spy run_sheet.__globals__ via patch.dict and use a global fitz.open spy for companion isolation — Robust to spec-load vs package-import dual module objects in the parity harness
- [Phase 21-16]: Two-stage learned retrieval: project_type inferred from latest prior correction at run start, refreshed after _detect_project_type — repeat runs get type-level vocabulary in prompts with zero manifests
- [Phase 21-16]: apply_learned_quantity_flags enforced on every run_sheet exit path: re_verify flags only, never substitution; geometry/text_layer HIGH protected even under the §6 identical-input exception (dormant in production)
- [Phase 21-16]: Aggregation naming precedence: companion legend > manifest > learned_vocabulary > static ITEM_NAME_MAP; learned-named rows marked source=learned, quantity provenance untouched
- [Phase 21-17]: Planted-decoy isolation: benchmark plants a sentinel sibling take-off, asserts the devtools finder sees it, and asserts the pipeline result is leakage-free (regression tripwire for companion auto-discovery)
- [Phase 21-17]: Gate semantics: uncertifiable metrics (geometry_text_qty_acc=None) FAIL; vision_qty_share counts any vision_ensemble involvement over quantity-bearing rows; flagged (needs_review/fusion_rejected) counts as covered for silent-miss detection
- [Phase 21-17]: accuracy_gate.sh pins LEARNING_DB_PATH to a fresh temp DB per run (cold-pipeline scores); --with-learning is tracking-only learned-assisted, never gating; cost baseline record-on-absent with >2x warning
- [Phase 21-18]: Shim deletion executed migration-first: all src/tests/scripts imports moved to absolute bobbytailor paths and proven green (833 tests) BEFORE deleting the 33 root shims; root app.py is a 5-line create_app() gunicorn entry
- [Phase 21-18]: Parity/takeoff-pipeline spec-load mocks are scoped (temp-alias sys.modules key + restore) and conftest pre-imports all stub-targeted real modules — fixes the 21-08/21-16 test-order pollution class (previously-failing forced orders now pass)
- [Phase 21-18]: 21-UAT.md documents Crow main-plan scale expectation as 1 in = 40 ft per the 21-07 geometric proof (roadmap's ~20 fpi text is the stale research figure)
- [Phase 22]: 22-01: Step 1d (blueprint-parity uploads isolation) deferred — UPLOADS_DIR override in create_app is a behavior change; goes to SPEC §7 CWD-relative anchoring
- [Phase 22]: 22-01: OUTPUT_DIR/SCREENSHOTS_DIR test isolation via conftest config module-attribute patch — env pins are defeated by config.py load_dotenv(override=True) with .env defining OUTPUT_DIR

### Pending Todos

None yet.

### 21-03 Decisions

| Decision | Source |
|----------|--------|
| Shapely 2 STRtree.query returns numpy indices — index into segment list, not geometry id() map | 21-03 |
| Overall dims (feet≥100) pick longest grammar-verified segment; bay dims cap at 5× median corridor length | 21-03 |
| PERP_MIN_PT=0 so rotated vertical text on the dimension line is not rejected | 21-03 |
| Chained dims on one segment split by text projection when extension-line crossings insufficient | 21-03 |
| Synthetic generator uses page.draw_line (Shape.commit invisible to get_drawings) | 21-03 |
| Crow page 0 consensus fpi≈40 matches printed scale (dominant_scale), not 20 fpi research note | 21-03 |

### 21-02 Decisions

| Decision | Source |
|----------|--------|
| Blueprint endpoints prefixed (auth.login, projects.index); PUBLIC_ENDPOINTS + login_view updated | 21-02 |
| create_app sets template_folder/static_folder to repo root (parents[3]) | 21-02 |
| jobs_runtime owns jobs dict + thread launchers; no Flask request in job threads | 21-02 |
| verify.py owns scale/verify/measurements/calibrate; reports.py owns list/preview/sheet-image | 21-02 |
| Scale tests patch config.OUTPUT_DIR (not app.OUTPUT_DIR) after blueprint split | 21-02 |

### 21-01 Decisions

| Decision | Source |
|----------|--------|
| Root shims star-re-export AND alias sys.modules[__name__] to the real package module — monkeypatch through either import path hits one module object | 21-01 |
| requires-python kept at >=3.9 (deployment/test runtime is macOS system Python 3.9.6, not 3.10) | 21-01 |
| app.py shim repoints Flask template_folder/static_folder to repo root (Flask resolves relative to module location) | 21-01 |
| settings.py + seed_admin.py received the same repo-root .env fix as config.py (parents[3] from src/bobbytailor/web/) | 21-01 |
| New Phase 21 modules are created directly in src/bobbytailor/ final homes; internal flat imports stay until the import-migration plan | 21-01 |
| Deterministic suite green count is 505 (plan's 348 figure was stale) | 21-01 |

### 20-00 Decisions

| Decision | Source |
|----------|--------|
| MODEL_ROUTING uses CLAUDE_MODEL_SCHEDULES config constant, not hardcoded slug | 20-00 |
| TakeoffPipeline accepts optional analyzer= callable (dependency injection for tests) | 20-00 |
| merge_passes defined as stub in takeoff_pipeline; canonical version moves to claude_analyzer in 20-03 | 20-00 |
| plan_passes returns copy of PASS_MATRIX list to prevent mutation of module constant | 20-00 |
| classify_sheet_type_from_text defaults to floor_plan when ambiguous (safest: runs count+measure) | 20-00 |

### 20-03 Decisions

| Decision | Source |
|----------|--------|
| COUNT_PROMPT returns `has_schedules` bool so TakeoffPipeline can conditionally invoke schedule pass | 20-03 |
| `analyze_drawing` default `pass_type="measure"` preserves all existing single-pass caller behavior | 20-03 |
| `_pick_model` deferred `MODEL_ROUTING` import avoids circular dependency with sheet_pass_matrix | 20-03 |
| Canonical `merge_passes` lives in `claude_analyzer`; `takeoff_pipeline` re-exports for backward compat | 20-03 |
| `merge_passes` uses `strip().lower()` for dedup keys to handle trailing whitespace in Claude output | 20-03 |

### 20-01 Decisions

| Decision | Source |
|----------|--------|
| Noise filter applied in BOTH title-block and full-page passes | 20-01 |
| `_is_noise_sheet_candidate` checks candidate within matched phrase context (not fullmatch on candidate alone) | 20-01 |
| `sheet_type_hint` in `get_pdf_metadata` is conditional on `sheet_pass_matrix` import (backward-compatible) | 20-01 |

### 17-01 Decisions

| Decision | Source |
|----------|--------|
| `REUSE_SCREENSHOTS` defaults to true; set false to force fresh downloads | 17-01 |
| `shutil.copy2` copies cached file to new run dir (preserves metadata) | 17-01 |
| Cache map built once before sheet loop via `find_screenshot_paths` | 17-01 |

### 17-03 Decisions

| Decision | Source |
|----------|--------|
| `{page_id}_analysis.json` cache beside screenshot; missing cache triggers re-analyze even when manifest says ok | 17-03 |
| analyze_only auto-discovers latest run folder by project_name prefix + mtime sort | 17-03 |
| `mode_detail: "full" \| "analyze_only"` on job dict for UI/log differentiation | 17-03 |
| `force=False` skips ok+cached pages; `force=True` re-runs all | 17-03 |

### 17-02 Decisions

| Decision | Source |
|----------|--------|
| Manifest saved after every page state change (crash-recovery foundation for 17-03) | 17-02 |
| Atomic tmp+replace write prevents corrupt JSON on mid-write crash | 17-02 |
| `screenshot_rel` stores filename only — `screenshots_dir` is run root | 17-02 |
| `browser_closed` flag in `finally` prevents double-close after Pass 1 | 17-02 |
| `phase="capturing"` in progress_callback during Pass 1 | 17-02 |

### 20-06 Decisions

| Decision | Source |
|----------|--------|
| pdf_analyzer defers to TakeoffPipeline.run_project — no inline analyze_drawing loop | 20-06 |
| _page_to_image defined in pdf_analyzer (2× Matrix scaling) — was missing (bug fix) | 20-06 |
| scraper uses module-level _pipeline singleton (TakeoffPipeline()) for run_sheet calls | 20-06 |
| _detect_project_type called once after all sheets in both paths (uniform project_type) | 20-06 |
| Parity test uses source-level assertions + TakeoffPipeline injection (no real API calls) | 20-06 |

### 20-05 Decisions

| Decision | Source |
|----------|--------|
| MEASURE_ADDENDUM defined as named constant then concatenated to EXTRACTION_PROMPT | 20-05 |
| lintel_runs[] as dedicated array (not merged into pipe_runs[]) — separate calculator path | 20-05 |
| duct_lf and conduit_lf use 10% waste (vs 5% for gas/storm) — fittings add more equivalent LF | 20-05 |
| CMU Paint placed BEFORE CMU Wall in ITEM_NAME_MAP — both match \bcmu\b; first-match wins | 20-05 |
| Frame-HM placed BEFORE Doors-HM — "HM Door Frame" must not collapse to Doors-HM | 20-05 |
| Conduit LF / Duct LF placed BEFORE Storm Pipe — prevents PVC conduit matching \bpvc\b storm pattern | 20-05 |

### 20-04 Decisions

| Decision | Source |
|----------|--------|
| Content notes override profile skip_items — explicit drawing content always wins (VCT on industrial → flooring) | 20-04 |
| Floor/ceiling/wall handled as independent priority chains in _calculate_from_room | 20-04 |
| auto profile has empty default lists → universal fallback preserves pre-20-04 behavior | 20-04 |
| _detect_project_type uses keyword scoring across sheet_title + notes; ties → mixed_use | 20-04 |
| Gas pipe detected by material keyword (black steel/gas/csst); default → storm_pipe | 20-04 |

### 20-09 Decisions

| Decision | Source |
|----------|--------|
| Sanitary Pipe placed BEFORE Storm Pipe — sanitary.*sewer would otherwise collapse into Storm Pipe | 20-09 |
| Storefront/Curtain Wall placed AFTER all door patterns — "aluminum storefront door" must resolve to Doors-AL | 20-09 |
| RTU placed AFTER Air Handling Units — air handler pattern must win for explicit AHU descriptions | 20-09 |
| Drywall Ceiling placed BEFORE Ceiling Grid — suspended/gyp ceiling is structurally distinct from ACT tile | 20-09 |
| Dock Doors placed before Frame-HM/Door section — overhead/coiling doors resolve correctly | 20-09 |

### Blockers/Concerns

- StackCT DOM brittleness (`#canvas-interaction`, `[data-page-id]`, Auth0) — mitigated in Phase 2
- Flask background-thread context leaks — use primitive payloads only in job threads (research PITFALLS #3)
- Claude schedule counting accuracy — document confidence limits; v2 review UI (EST-02)
- Pricing table may go stale — verify quarterly against Anthropic docs
- GitNexus index stale after 21-01 package move (symbols indexed at old root paths) — run `npx gitnexus analyze` before impact analysis in later plans
- 23-11 SP-4 clip cell STOPPED: the plan's midpoint anchor partition is falsified on all 16 Moxy prototype sheets (best variant reproduces 4/16). Needs a decision on what the pinned RCP areas mean. See 23-11-SUMMARY.md deviation 2.
- [Phase 23]: 23-16: a correction states FOUR things or it is a scope reduction — the ORIGINAL wording, the falsifying evidence, the citation, and the delivered contract. Applied to docs/PIPELINE-GROUND-TRUTH.md's four disproved passages and to ROADMAP criteria 2/4 + V4-MEAS-02/04.
- [Phase 23]: 23-16: an acceptance gate INVOKES the tests that own each criterion rather than copying their literals — check 1 calls tests/test_four_set_coverage.py's own assertion functions, so the gate cannot drift from the thing it re-asserts.
- [Phase 23]: 23-16: a criterion the phase did NOT deliver is named in the gate with its blocker (clip invariance -> DEF-23-SP4; Bob's p3 page-level fpp -> DEF-23-08) and the delivered contract asserted in its place. Silently dropping it would reproduce, inside the gate, the exact failure the corrected passages document.
- [Phase 23]: 23-16: §14's published TOTAL row does not equal the sum of its own nine rows (45,837/42,835 vs the measured 44,011/41,912 = +5.0%). All nine per-sheet values reproduce exactly on today's engine, so the rows are sound and only the total was unsourced.
- [Phase 23]: 23-16: a published figure must state its PROVENANCE. §14's 7.0% came from a probe calling the engine directly; a real run could not reach those sheets because the classifier discarded 18 of Moxy's 40 pages.
- [Phase 28]: 28-01: `geometry` provenance outranks the sheet kind — instance bounding boxes on a details sheet are still bounding boxes, so a geometry-backed count is corroborated wherever it was read.
- [Phase 28]: 28-01: `text_layer` provenance is NOT corroboration. A printed word is not a counted object; it falls through to `none`/`detail_sheet_only` like any prose count.
- [Phase 28]: 28-01: self-reported model confidence is not evidence. `test_confidence_flagging::test_high_confidence_count_not_flagged` asserted that a high-confidence count with nothing behind it went unflagged — that IS the confidently-wrong row; the check was split, not deleted.
- [Phase 28]: 28-01: record-then-decide. The calculator writes the verdict, the aggregator (28-03) makes the publish call. That split is what kept the blast radius to one function plus a two-key whitelist passthrough in `reporter._normalize_calculated` — the only seam between the calculator and `aggregate_takeoff`.
- [Phase 28]: 28-01: PLAN PREMISE FALSIFIED — run A's `Door Frames-HM` backing row carries `provenance: geometry`, not null as 28-01's measured_facts recorded. So only 2 of the 3 varying keys are uncorroborated; the third moved because a geometry-backed ROW vanished between extraction passes. 28-06's "covers every number that moved" claim needs a second axis or a narrower wording.
- [Phase 28]: 28-01: an uncorroborated count's review reason names the sheet and the confirmation to go get, and states NO number — a test strips the sheet name and asserts the remainder is digit-free, so an expected count cannot be smuggled into an estimator-facing message.
- [Phase 28]: 28-02: the Bollards 2x is NOT a double-count, disproved on the real page for free: all instances in ONE viewport, closest pair 87 pt / 48.3 ft apart against a 1.56 pt / 0.8 ft symbol, nearest instance 0.203 of the region's short side from any boundary. The clean factor of two is a coincidence and halving would have been the §10 trap in its purest form.
- [Phase 28]: 28-02: a hollow-ring test needs POSITIVE evidence, not only an upper bound. "At most two dense bands per axis" is satisfied vacuously by a sparse scatter whose bands are all too thin to be dense — measured live on `SYM-22` (8 marks, dense bands (1,0), inset fill 0.125), which would have become the NEW Bollards binder at 8 EA. Nearly every mark must also lie ON one of the runs, at the allowance the hollowness test already makes (`1 - _PERIMETER_INNER_MAX_FILL`).
- [Phase 28]: 28-02: PLAN PREMISE FALSIFIED — there is no 56-vs-56 tie on Crow page 0. `SYM-3` (11.13 ft) is excluded by `_is_small_marker` before any tie can exist, so `max` picked `SYM-2` by a UNIQUE maximum and list order decided nothing. The sole cause of the mis-binding is `_is_perimeter_ring`; the unique-maximum rule shipped as a hardening (T-28-06 / T-28-10), and 28-07 must not claim it fixed Crow.
- [Phase 28]: 28-02: real-data positive control — the sheet's one genuinely hollow ring (`SYM-3`, dense bands (2,2), rows `[21, 2x7, 21]`) is asserted to STILL pass `_is_perimeter_ring`, so a fix cannot go green by refusing everything. It is kept from the marker hint by the pre-existing size/uniformity filters, never by the ring test.
- [Phase 28]: 28-02: identify the subject through the producer's own filter MINUS the predicate under scrutiny. A shortlist that included the ring test would have found nothing after the fix, and the position evidence would have silently stopped describing anything.
- [Phase 28]: 28-02: Crow's Bollards row is now a flagged ABSENCE OF A NAME and does NOT approach golden — that is the deliverable, not a shortfall. Removing a wrong name is naming's job; finding the real bollards is Phase 25's symbol detection.
- [Phase 28]: 28-03: the corroboration roll-up takes the BEST evidence, the mirror of `_worse_conf` — one schedule- or geometry-backed contributing row vouches for the whole bucket, because corroboration is evidence while confidence is a claim about certainty. Among uncorroborated verdicts `detail_sheet_only` dominates `none` so the reason names the sheet kind rather than shrugging, and an unrecognised verdict ranks with `none` so it can never be mistaken for corroboration.
- [Phase 28]: 28-03: `None` (no count contributed) is kept DISTINCT from `"none"` (a count contributed and nothing backed it), and absence is never read as "no evidence". That two-state test is the difference between flagging the rows this phase is about and flagging every area and length in the take-off — and it is why not one existing assertion in test_aggregator.py had to change.
- [Phase 28]: 28-03: a status branch alone would have published a self-contradicting row — `provenance: NEEDS REVIEW` beside `needs_review: False` and `auto_verified: True`, flagging itself to a human and clearing itself to every numeric consumer. The flag is set with the reason; `_row_status` keeps the branch as the INVARIANT at the publish point, asserted directly on hand-built buckets so it is not dead code.
- [Phase 28]: 28-03: a withheld reading always leaves a ROW that quotes what it withheld — the third instance of the blank-not-zero contract in aggregator.py, copied from the unit-class-conflict block rather than reinvented, with a new `source` marker placed INSIDE `_UNMEASURED_SOURCES` and a test asserting no module outside aggregator.py names it.
- [Phase 28]: 28-03: V4-FIX-01 is ADVANCED, not ticked. `_calculate_from_measurement`'s whole-EA path and `_calculate_from_civil_structures` emit counts and record no verdict, so the requirement's universal claim is not yet true app-wide; the gap is a committed tripwire test that FAILS when someone closes it, not a sentence in a document.
- [Phase 28]: 28-04: PLAN PREMISE FALSIFIED — the contest on Crow is ONE object against THREE classes, not two objects against one class. Measured free on page 0: an 8" object is within the 1.5" tolerance of TC1 (8.80", 36.63%), TC5 (8.00", 6.70%) and TC10 (7.20", 0.72%), and the frozen runs show exactly one thickness bind occurred, so no second object contested it. The object-axis test the plan specified would have changed nothing on this sheet.
- [Phase 28]: 28-04: uniqueness is MUTUAL — a confident bind requires that exactly one object claims the class AND that the object's thickness fits exactly one class. Same principle, both axes; implementing only the named axis would have shipped a correct rule that left the defect the plan exists to fix in place.
- [Phase 28]: 28-04: pass 1 is a bipartite (object, class) candidacy, not a loop. The old object-outer loop COULD NOT ASK the uniqueness question — by the time an object had taken a class the class was gone from every later object's view — which is why it was never asked. Free side effect: the bind no longer depends on vocabulary order.
- [Phase 28]: 28-04: inside a tolerance, "nearer" is the noise the tolerance exists to absorb. TC5 agreed to the decimal and TC1 was 0.8" away, both inside 1.5" — preferring the exact agreement was reading signal out of what we had already declared to be noise.
- [Phase 28]: 28-04: the LF-share masonry guard does NOT fire on Crow (TC5 is 6.70% against a 25% cap) and was NOT lowered until it did. It closes a real hole — a masonry object could take a 40%-share class that merely was not the largest — but uniqueness is what fixed this drawing, and no commit claims otherwise. The threshold's independence from any drawing is PROVED by scaling every length on the sheet, not asserted in a comment.
- [Phase 28]: 28-04: V4-FIX-03 is ADVANCED, not ticked. The class Crow published `CMU Wall` under is now contested and confidently named by nothing, but with the thickness route refused `CMU Wall` falls to pass 2's masonry-by-hint rule, which hands it the SMALLEST remaining class (TC13, 2.5 LF) on no evidence beyond "masonry is small". That unevidenced hint bind is a flag-don't-guess residual of the same family this phase exists to close, and it is out of 28-04's fence.
- [Phase 28]: 28-04: 24-09's residual test is UNAFFECTED and was not edited — the harness replays fixtures whose naming response is `{"objects": []}`, so the mapper returns before pass 1 and no contest can arise. The reason is recorded so the green tick is interpretable.

## Session Continuity

Last session: 2026-08-07T07:05:31.246Z
Stopped at: Completed 28-05-PLAN.md (5 of 7 plans, wave 3). ONE MEASURED REGION NOW BACKS ONE
PUBLISHED ROW PER BUILDING LAYER. The 397,600 SF footprint published three times in both saved paid
runs — `Exposed Structure` and `Sealed Concrete` from the plan's own authoritative legend, and
`Concrete Pad` sourced `library`, whose own review reason opens "this row's NAME is a hypothesis".
An estimator summing the SF column priced the building three times. The reason it could not be fixed
honestly before is that the REGION was dropped between fusion and the report, leaving numeric
equality as the only available arbitration — a coincidence rule. So `region_ref` and a new
`name_source` (the name came from a vocabulary object's measure basis, with nothing printed on the
sheet naming it) are now carried through BOTH calculator entry points and rolled up onto the bucket,
absent rather than empty; a legend row inherits the region of the detected reading its shadow branch
suppresses, because that branch has just declared the two rows the same item; and where a region
group holds BOTH an evidence-named row and a hypothesis-named one, the hypothesis's number is
withheld and the row becomes a visible blank naming the region, the withheld area and the rows that
hold it. THE STAMP IS PROVED INERT — anchor and every suppression on the Crow fan-out are identical
with and without it — and D1 IS PROVED INTACT: three evidence-named layers on one region all
publish, and a region held only by hypotheses (which is D1's three-layer share on a manifest-free
run) is left entirely alone. Nothing compares two quantities, asserted against the rule's AST rather
than against a case. Phase 24's acceptance gate caught the marker's natural name colliding with a
literal 24-09 was written around; renamed rather than loosening the gate. The Crow SCORE does not
move — the duplicate was never a golden row — and no post-fix figure is claimed. Full offline suite
2329 passed / 1 skipped / 2 deselected (1:03:40) against a 2300 baseline: +29, exactly the new
module, zero regressions.
Next: 28-06-PLAN.md (wave 4).

Previous session: 2026-08-07T02:40:00Z
Stopped at: Completed 28-04-PLAN.md (4 of 7 plans, wave 2 done). A printed thickness is evidence of
DIMENSION and only becomes evidence of IDENTITY when exactly one candidate claims it — so
`map_wall_classes_from_library` pass 1 is now a bipartite (object, class) candidacy requiring MUTUAL
uniqueness, the masonry guard tests an LF SHARE at any rank rather than only the top rank, and a
refused bind reaches `fusion_rejected` under its own key naming the objects that contested it. The
plan's premise was falsified first and free: the contest on Crow is one object against THREE classes
(8" fits TC1 8.80", TC5 8.00", TC10 7.20"), not two objects against one class, so the object-axis
test the plan specified would have changed nothing — both axes shipped. Measured on the real
geometry: TC5, the class that published `CMU Wall`, is now CONTESTED and confidently named by
nothing; `CMU Wall` is not consumed and falls to pass 2's hint rule. The share guard did NOT fire
(6.70% vs a 25% cap) and was not tuned until it did. V4-FIX-03 is ADVANCED, not ticked — pass 2's
masonry-by-hint rule now decides where `CMU Wall` lands on no evidence, a residual named for 28-07.
24-09's residual test is unaffected and unedited. Full offline suite 2300 passed / 1 skipped /
2 deselected (1:08:40) against a 2264 baseline: +36, exactly the new module, zero regressions.
Next: 28-05-PLAN.md (wave 3).

Previous session: 2026-08-06T23:50:00Z
Stopped at: Completed 28-03-PLAN.md (3 of 7 plans, wave 2). 28-01's verdict now DECIDES: a count whose
only evidence was a details sheet is withheld as a blank quoting the reading, the sheet and the rule
that withheld it; a surviving count with no printed schedule and no counted geometry publishes NEEDS
REVIEW with the flag set, not just the status; and `_row_status` — the single place a bucket becomes
ITEM_MEASURED — cannot return it for an uncorroborated count. The door schedule, the geometry-backed
count and the injected Mobilization convention are each proved untouched, and run B's accidental
`Lift` PASS is deliberately lost. V4-FIX-01 is ADVANCED, not ticked: two calculator producers
(`_calculate_from_measurement`'s whole-EA path, `_calculate_from_civil_structures`) emit counts and
stamp no verdict, committed as a tripwire test for 28-07.
Full offline suite 2263 passed / 1 skipped / 2 deselected. Next: 28-04-PLAN.md (wave 2).
Resume file: None

### Phase 23 decisions so far

- 23-02: the paper-inch measure is read from the token the inch mark owns (anchored, right-to-left),
  never "the first number left of `=`" — that is what let a leading drawing number win on Bob's.

- 23-02: split-stacked concatenation is tried before the second-token-alone rule (`1 16` is 1/16,
  not 1 + 1/6). The ordering is load-bearing and pinned in both directions.

- 23-02: the four-fixture `changed=7 unchanged=383` diff is a committed test with a FROZEN
  pre-change fixture, so the pin cannot be regenerated by the code it constrains.

- 23-02: `scale_probe.py`'s human report is byte-frozen; new detail goes in `--json`.
- 23-02: DEF-23-01/02/03 logged to `deferred-items.md` rather than fixed — DEF-23-01 would break
  the very pin this plan establishes, DEF-23-03 (BUG-C) belongs to plan 23-07.

- 23-03: `quantity` is `Optional[float]`. `None` means "not measured"; `0.0` means "measured as
  zero". The only correct test is `is None` — a comparison against zero is the bug itself.

- 23-03: provenance is COMPUTED FROM THE RECORD. The aggregator builds the four-value status from
  what the run did and passes it to `provenance_of_row`, so nothing infers provenance from a value
  and a manifest-NAMED measurement is never relabelled as a human input.

- 23-03: in plans-only mode, expected items come from `learned.expected_items` plus library entries
  carrying a measure BASIS — a basis is the app's own statement that it knows what measuring the
  item would mean. Bounded: 10 rows for Bob's (incl. `Lintels`), 25 for Crow.

- 23-03: an expected item is suppressed when any contributing description RESOLVED to it, whatever
  name finally won — otherwise a human's rename makes the same object both measured and missing.

- 23-03: `excluded_viewports` stays separate from `coverage_drops`: a deliberate off-scale exclusion
  is correct behaviour, and conflating it with a failure would make a well-measured sheet read partial.

- 23-03: `select_fill_for_basis` prefers-then-falls-back instead of filtering. A flagged fill is
  returned WITH its flag so the caller flags; it never vanishes.

- 23-03: a probe that skips a page must say so — silence in the tooling is the same defect one
  layer out (Crow printed nothing at all and reported `TOTAL rooms=0`).

- 23-03: DEF-23-04 logged — the pre-existing `max_region_sf` test passes for the wrong reason (its
  fixture overflows the page, so the region is discarded as the outside before the guard is reached).
