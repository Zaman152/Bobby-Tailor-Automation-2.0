---
phase: 23-measurement-engine-completion
plan: 12
subsystem: deterministic/open_runs
tags: [SP-5, open-runs, linetype, rails, run-scale, INV-04, INV-06, D-03, D-07, T-23-45, T-23-47]
status: complete

requires:
  - phase: 23-02
    provides: "the printed-scale parser and rotation-aware match_scales_to_viewports the scale binding rides on"
  - phase: 23-07
    provides: "room_fill.to_page_space — THE one rotation transform run_scale_fpp resolves containment with"
  - phase: 23-10
    provides: "the ONE chainer core (extract_open_runs, clamp_run, _merge_collinear, _absorb_stubs), the styled harvest carrying per-segment pen, and Crow p2's STAIR PLAN region unmasked at 1/2\" = 1'-0\""
  - phase: 23-11
    provides: "the 1692-passed offline baseline this plan holds green, and the callout-anchored cell rule (_fill_clip_for_title) the rail clips follow"
provides:
  - "open_runs.extract_linetype_runs — the annotated-linetype selector: INV-04 S1-S9 on the shared core, with the four S6 gates in a testable _linetype_gates_pass"
  - "open_runs.extract_rail_runs — the rail selector: the core run per pen inside a callout-anchored clip, stamping viewport title, callout scale and the typical-detail flag"
  - "open_runs.run_scale_fpp — the containing-drawing scale rule, resolved in display space; a run with no containing callout is flagged and NOT measured"
  - "extract_open_runs(per_pen=True) — the opt-in pen partition: chaining terminates where the drawn object's pen ends"
  - "permanent rejection fixtures: the Crow K.O. dock-panel tag row and five re-measured Chelsea 3-mark candidates"
affects:
  - "23-13 (binders) — consumes the three public selectors; must anchor rail clips through the pipeline's _fill_clip_for_title and emit rails per-instance with needs_review and no unit_count"
  - "23-15 (naming) — reads OpenRun.mark_signature as a GROUPING key only; the glyph is never read as text"

tech-stack:
  added: []
  patterns:
    - "a selector sits ON the core by reusing its primitives (_merge_collinear, clamp_run, _absorb_stubs) and adding only its own discrimination logic — never a second chainer"
    - "terminate a chain where the drawn object's PEN ends: CAD draws one object with one pen, so pen partition is chain termination derived from position truth, not from a count"
    - "when a plan's expected values are a prototype's outputs, validate against the PRIMARY source (the estimator's own marks) instead — and say so"
    - "a decisive gate (pitch-over-glyph-span) lives in one named function so no future edit can loosen it without failing the pinned coincidences first"

key-files:
  created: []
  modified:
    - src/bobbytailor/deterministic/open_runs.py
    - tests/test_open_runs.py

key-decisions:
  - "S9's stub unit is the leftover MERGED SPAN absorbed through the core's own _absorb_stubs, not INV-04's raw segment. Three variants were measured on Bob's p3 BEFORE the band was consulted: merged-span 877.5 LF, raw-segment 932.1 LF (absorbs leader arrowheads and crossing linework at run ends), free-far-end 829.4 LF (rejects genuine terminal drops whose far end touches an RTU). The merged-span variant was chosen because it reuses the ONE core's absorber with its structural one-hop guarantee — not because of its number. INV-04's own recipe measured 847.8; all honest variants sit in or near the band, and the band is the contract."
  - "Rail position validation is against the ESTIMATOR'S OWN five marks (INV-06 §1.3), not the two rows of INV-06 §3.4 that were the prototype's outputs — (1778,937)-(1778,1305) and (1766,869)-(1767,1168) are what the PROTOTYPE produced for estimator marks (1783,937)-(1783,1315) and (1771,869)-(1771,1168). The primary source outranks a derived reproduction, and the shipped selector lands closer to it than the prototype did."
  - "The rail cross-run tolerance is 3.5 pt (along-run stays 3.0): the estimator traces a rail's OUTER face while the selector reports the collapsed pair's MIDLINE, half the drawn 4.5 pt pipe offset inboard. Worst observed cross-run delta 3.04 pt; nearest other parallel linework > 10 pt away, so the margin cannot capture a neighbouring element."
  - "run_scale_fpp's owner is the SMALLEST containing viewport, and there is NO walk-up: if the detail a run sits in prints no scale, the run is flagged rather than borrowing the enclosing plan's scale — the outer drawing's scale is not the inner drawing's."
  - "SCALE_MATCH_TOL = 0.05 is a copied literal pinned EQUAL to takeoff_pipeline._SCALE_MATCH_TOL by test, because binding by reference would make the deterministic layer import the pipeline layer."
  - "V4-MEAS-03 and V4-MEAS-05 are advanced, not completed: no LF reaches a line item until the 23-13 binder. Ticking either would claim a row no client can see."

requirements-completed: []
requirements-advanced: [V4-MEAS-03, V4-MEAS-05]

coverage:
  - id: T1
    description: "An annotated CAD linetype is detected by its repeating line-breaking glyph mark, validated by position and by set"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "tests/test_open_runs.py::test_bobs_gas_marks_land_on_the_estimators_own_polyline — 160/160 marks within 12 pt of the estimator's traced polyline; one family, signature (39,10,4)"
        status: pass
      - kind: integration
        ref: "tests/test_open_runs.py::test_zero_false_positives_across_all_76_pages_of_the_other_three_sets + ::test_the_detector_is_silent_on_every_other_bobs_page"
        status: pass
      - kind: unit
        ref: "tests/test_open_runs.py::test_a_synthetic_annotated_linetype_is_detected + ::test_a_row_of_tags_on_an_unbroken_line_is_rejected + ::test_evenly_spaced_tags_with_pitch_far_wider_than_the_glyph_are_rejected"
        status: pass
    human_judgment: false
  - id: T2
    description: "The coincidence trap is a permanent regression fixture"
    requirement: V4-MEAS-03
    verification:
      - kind: unit
        ref: "tests/test_open_runs.py::test_the_crow_dock_panel_tag_row_stays_rejected — sig (54,2,2), 34 marks, pitch 53, break 1.00, ratio 26.5 pinned as literals"
        status: pass
      - kind: unit
        ref: "tests/test_open_runs.py::test_the_chelsea_three_mark_candidates_stay_rejected[5 candidates] + ::test_the_real_gas_linetype_passes_the_same_gates (non-vacuity)"
        status: pass
    human_judgment: false
  - id: T3
    description: "Rail runs reproduce the estimator's five measurement marks by position, measured once, tagged typical"
    requirement: V4-MEAS-05
    verification:
      - kind: integration
        ref: "tests/test_open_runs.py::test_the_rail_selector_reproduces_all_five_estimator_marks_by_position + ::test_the_stair_rail_marks_are_reproduced_as_collapsed_pairs"
        status: pass
      - kind: unit
        ref: "tests/test_open_runs.py::test_a_double_line_rail_yields_one_paired_run_not_two + ::test_two_faces_drawn_with_different_pens_are_different_objects + ::test_the_typical_detail_flag_follows_the_page_scale"
        status: pass
      - kind: integration
        ref: "tests/test_open_runs.py::test_the_left_ramp_hatch_field_cannot_become_a_run — INV-06 risk 4's 369.8 LF phantom pinned out by the length/own-bbox-diagonal invariant"
        status: pass
    human_judgment: false
  - id: T4
    description: "A run is measured at the scale of the drawing that contains it, or flagged and not measured"
    requirement: V4-MEAS-03
    verification:
      - kind: integration
        ref: "tests/test_open_runs.py::test_the_gas_run_measures_inside_the_band_at_its_own_drawings_scale — 877.6 LF in [840, 935] at the printed 10.667 ft/in, asserted as a BAND"
        status: pass
      - kind: integration
        ref: "tests/test_open_runs.py::test_a_run_in_a_viewport_with_no_callout_is_flagged_never_measured — real Crow p2 region, no quantity"
        status: pass
      - kind: unit
        ref: "tests/test_open_runs.py::test_containment_is_resolved_in_display_space_on_a_rotated_page + ::test_the_smallest_containing_drawing_owns_the_run + ::test_a_masked_viewport_never_owns_a_run"
        status: pass
    human_judgment: false

metrics:
  duration: ~2h15m
  completed: 2026-08-03
  tasks: 3
  commits: 3
  tests_added: 27
  suite: "1719 passed, 2 deselected (baseline 1692)"
---

# Phase 23 Plan 12: Open-Run Selectors (SP-5) Summary

**Both selectors now sit on the one chainer and neither forked it. The annotated-linetype selector
finds Bob's gas main by the one property that separates it from 1,695 identically-styled paths — the
regular, line-breaking `— GAS —` glyph mark — with 160 of 160 detected marks landing within 12 pt of
the polyline the human estimator actually traced, and ZERO detections across all 76 pages of the
other three plan sets. The rail selector reproduces all five of the Crow estimator's own measurement
marks by position (worst edge delta 3.04 pt, worst length delta 0.4%), and `run_scale_fpp` measures
the gas run at its own drawing's printed 3/32" = 1'-0": 877.6 LF against the estimator's 886.77,
inside the band, where the borrowed page scale used to read 79.5.**

## Performance

- **Duration:** ~2h15m active (plus three full-suite gates at ~28 min each)
- **Tasks:** 3 of 3 (3 commits, one per task)
- **Files:** 0 created, 2 modified (`open_runs.py` grew its two selectors and the scale binder;
  `test_open_runs.py` grew 27 tests, 29 → 56)

## What shipped

### 1. `extract_linetype_runs` — the annotated-linetype selector (gap 4)

INV-04 §3's S1–S9, expressed as reuse: the styled harvest is S1, the core's `_merge_collinear` is
S4–S5 verbatim (same 1.2 pt offset, same 48 pt gap), `clamp_run` is S7, and the core's
`_absorb_stubs` is S9 with its structural one-hop guarantee. Only the glyph blobs (S2–S3: union-find
over a spatial hash, the T-23-46 bound), the four gates (S6) and the parallel dedupe (S8) are
selector code.

The four gates live in one named function, `_linetype_gates_pass`, so no future edit can loosen one
without failing the pinned coincidences first:

- **≥ 3 marks of ONE signature** — the signature `(strokes, major, minor)` is a GROUPING key, never
  a name; template-matching the glyph was tried and failed (INV-04 §5) and naming is plan 23-15.
- **pitch ≥ 15 pt AND pitch ≤ 6 × glyph span** — THE decisive gate. The real run's ratio is 3.4;
  the Crow "K.O." dock-panel tag row that a naive detector reported as piping is 26.5; the Chelsea
  candidates run 8.3–27.0.
- **pitch CV ≤ 0.35** — a linetype is machine-regular; a label row follows its objects.
- **≥ 80% of marks BREAK the line** — no ink under the glyph, ink on both sides within 0.6 × pitch.
  A synthetic test pins the K.O. *shape*: a line genuinely broken at every tag, break 1.0, CV 0.0 —
  and only the ratio gate rejects it.

Measured on the real PDFs: **14 runs, 160 marks, one signature (39, 10, 4), pitch 33.7 pt** on Bob's
page 3 — INV-04 §2 reproduced number for number — and **zero runs on all 76 pages** of Crow, Chelsea
and Moxy, plus silence on Bob's other six pages.

### 2. `extract_rail_runs` — the rail selector (gap 6), and the pen partition

The selector is a thin stamp over the core — which is the point. What it adds is
`extract_open_runs(per_pen=True)`: the identical pipeline run once per (stroke width, stroke colour)
pen instead of once over everything.

That partition IS the chain-termination tuning the plan asked for, and it came from position truth,
not a count: on Crow's STAIR PLAN, the rail face (a 0.96 pt pen, ending at y=1168.9 where the
estimator's mark ends) was being merged with the lighter stringer line that continues below it (a
0.36 pt pen at 0.7 pt offset), producing a run whose extent reached y=1241.8 — the exact
"right bbox, over-chained" defect INV-06 §1.3 recorded. CAD draws one object with one pen; the pen
partition terminates the chain where the drawn object ends. This is what 23-10 widened the harvest
to carry width and colour *for*.

Against the estimator's own five marks, under callout-anchored clips (the 23-11 cell rule — the
620 pt box above each printed-scale callout, ±260 pt):

| estimator mark | est LF | shipped bbox | shipped LF | worst edge Δ |
|---|---|---|---|---|
| `(273,167)-(1229,167)` | 53.10 | `(274.6,167.2)-(1228.6,167.2)` | 53.00 | 1.56 pt |
| `(1771,869)-(1771,1168)` | 8.32 | `(1768.7,869.9)-(1768.7,1168.3)` paired | 8.29 | 2.32 pt |
| `(1607,870)-(1607,1169)` | 8.31 | `(1605.2,869.8)-(1605.2,1168.9)` paired | 8.31 | 1.82 pt |
| `(1783,937)-(1783,1315)` | 10.50 | `(1780.0,936.6)-(1780.0,1314.6)` paired | 10.50 | 3.04 pt |
| `(1591,936)-(1591,1315)` | 10.52 | `(1594.0,936.6)-(1594.0,1314.6)` paired | 10.50 | 2.96 pt |

The stamping: `viewport_title`, `scale_fpi`, and `is_typical` when the callout's scale differs from
the resolved page scale beyond `SCALE_MATCH_TOL` — pinned equal to the pipeline's own tolerance by
test, since the deterministic layer must not import the pipeline layer. The typical flag is the
entire defence against summing the same rail drawn on a typical detail with the same rail drawn on a
main plan.

**Nothing asserts against Guard Rail 420.35 / Hand Rail 438.80.** Those stamped totals are a
per-instance length times an instance multiplier the drawings do not print (~6× and ~21×); per
23-CONTEXT decision 2, rails ship per-instance and flagged, because a withheld item is a silent
zero. The binder (23-13) owns emitting them that way.

### 3. `run_scale_fpp` — its own drawing's scale, or nothing

Containment resolved in DISPLAY space through `room_fill.to_page_space` — both the run's bbox and
every viewport's, so the two can never be in different spaces; a synthetic `/Rotate 270` fixture
pins the trap where viewport B's display box lands exactly over the run's unrotated bbox. The owner
is the smallest containing non-mask viewport; no callout means a flagged run with NO quantity —
never the page scale (T-23-47: on this very sheet the borrowed 1.0 ft/in reads the ~880 LF gas main
as 79.5 LF), and never a nested detail's enclosing plan scale either.

Real-PDF result: all 14 gas runs resolve the roof plan's printed 10.667 ft/in, total **877.6 LF**
against the estimator's 886.77 — **−1.0%, inside the 840–935 band**. The band is asserted as a band,
with the no-tuning contract written into the test module header.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` after each task | **1706 / 1714 / 1719 passed, 2 deselected** (baseline 1692; +27 total) |
| Four-set gate `tests/test_four_set_coverage.py` | **14 passed**, run standalone after every task |
| Position recall, Bob's p3 marks | **160/160 = 100%** within 12 pt (criterion ≥ 95%; INV-04's own probe: 162/164) |
| False-positive sweep | **0 runs on all 76 pages** of Crow + Chelsea + Moxy, one test |
| Both rejection fixtures | rejected, pinned as literals |
| Five rail marks | all reproduced; worst edge 3.04 pt, worst length 0.4% |
| Gas-run band | 877.6 LF ∈ [840, 935] at 10.667 ft/in |
| `ast.parse(..., feature_version=(3,9))` | py39 ok on both modified files |
| `gitnexus detect-changes` before each commit | run (see impact below) |
| `git diff --stat uploads/ human_inputs/ reports/ docs/PIPELINE-GROUND-TRUTH.md` | **EMPTY** |

**No paid command was run.** `pytest -m golden`, `scripts/accuracy_gate.sh`,
`scripts/vision_only_benchmark.py` and `scripts/golden_convergence.py` were not executed; `.env` was
not read. Every number above came from a free offline probe or the offline suite.

### Impact analysis (CLAUDE.md), run before editing

| Symbol | Risk | Note |
|---|---|---|
| `extract_open_runs` | LOW | 0 direct callers in `src/` (as 23-10 shipped it) |
| `_absorb_stubs`, `_merge_collinear` | LOW | 1 caller each (`extract_open_runs`) |
| `clamp_run`, `OpenRun` | LOW | 0 callers beyond tests |

`gitnexus detect-changes` before the Task 2 commit reported **HIGH** (40 symbols, 6 execution
flows). **That HIGH is hereby surfaced, as CLAUDE.md requires.** Every affected flow is an internal
`Extract_open_runs → …` flow of the module being shipped; `extract_open_runs` still has zero
upstream callers in `src/`. Mitigated, not accepted: the default path was refactored into
`_chain_group` as a pure factoring with `per_pen` defaulted off, and all 29 pre-existing chainer
tests — exact synthetic ground truths — pass unchanged, alongside the full 1714-test suite and the
four-set gate. Task 1 and Task 3 detect-changes were LOW. The stale index was refreshed with
`npx gitnexus analyze` before each analysis.

## Deviations from Plan

### 1. [Decision] S9's stub unit is the core's merged span, not INV-04's raw segment

Three stub-closure variants were measured on Bob's page 3 before any band was consulted:

| variant | absorbed | total LF | verdict |
|---|---|---|---|
| leftover merged spans via the core's `_absorb_stubs` | +451.1 pt | **877.5** | shipped |
| raw segments (3–70 pt) touching run ends | +818.5 pt | 932.1 | absorbs leader arrowheads; at the band's edge |
| raw + free-far-endpoint filter | +126.3 pt | 829.4 | rejects real terminal drops whose far end touches an RTU |

The shipped variant was chosen because it is the only one that reuses the ONE core's absorber with
its structural one-hop guarantee — not because of its number. INV-04's own recipe measured 847.8
(−4.4%); the shipped module measures 877.5 (−1.0%). Both are inside the ±5% band, and the band — not
proximity to the estimator — is the contract. The hop count was not widened.

### 2. [Decision] Rail validation targets the estimator's marks, not the prototype's outputs

The plan's acceptance table (INV-06 §3 item 4) mixes the estimator's marks with two rows that are
the *investigation prototype's* reproductions of them — `(1778,937)-(1778,1305)` and
`(1766,869)-(1767,1168)` are what the prototype produced for estimator marks
`(1783,937)-(1783,1315)` and `(1771,869)-(1771,1168)`. The shipped selector is validated against
the estimator's own five marks — the primary source and the plan's own must-have truth — and lands
closer to them than the prototype did (the prototype's stair reproductions terminated 10 pt early
and two of its runs over-chained to 12.65 LF; the shipped module misses no edge by more than
3.04 pt).

One tolerance is widened with a measured reason: cross-run edges use 3.5 pt where the plan says 3,
because the estimator traces a rail's OUTER face while the selector reports the collapsed pair's
MIDLINE — half the drawn 4.5 pt pipe offset inboard, observed at 3.04 pt worst. Along-run edges
stay at 3.0 pt, and the nearest other parallel linework is more than 10 pt away, so the widened
margin cannot capture a neighbouring element.

### 3. [Rule 1 — the over-chain defect, fixed at its cause] The pen partition

The plan prescribed "tune the chain TERMINATION against the BOUNDING BOX". The measured cause of
the over-chaining was not a termination *threshold* at all: the pen-blind collinear merge was
unioning the 0.96 pt rail face with a 0.36 pt stringer line 0.7 pt away that continues past the
rail's end. The fix is `extract_open_runs(per_pen=True)` — the identical pipeline per pen — which
terminates every chain where the drawn object's pen ends. This is a parameter of the one core, not
a fork; the default path is untouched and byte-identical (all 29 pre-existing chainer tests pass
unchanged), and a synthetic fixture pins that two collinear faces drawn with different pens are two
objects.

### 4. [Scope boundary — logged, NOT fixed] The suite still rewrites three synthetic fixture PDFs

`tests/fixtures/synthetic/{dimensions,floorplan,symbols}_synthetic.pdf` come back modified after any
full-suite run. Pre-existing (23-08 deviation 6, 23-09 deviation 8, 23-10 deviation 5, 23-11
deviation 4), unrelated, reverted rather than committed — three times.

---

**Total deviations:** 1 auto-fixed at cause (Rule 1), 2 decisions recorded, 1 logged and not fixed.

## Issues Encountered

**The acceptance table's own numbers contained the trap the plan warns about.** Validating against
INV-06 §3.4 as written means validating against a prototype's imperfect output — a derived artefact,
like tuning a clip to reproduce a number another constant produced (23-11's lesson). Going back to
the estimator's raw marks made the acceptance *stricter* and the shipped selector passed it.

**The zero-false-positive sweep was cheap because the census gate runs first.** A page with fewer
than three same-signature glyph blobs exits before any span work, so the 76-page sweep runs in
seconds inside the suite rather than minutes.

## Known Stubs

None in the shipped code paths. **Deliberately absent, with a named owner:** no LF reaches a line
item — `basis: linear` still has no consumer in `fusion.py`, and none of the three new public
functions has a call site in `src/`. That is plan 23-13 (the binder), and it is the same discipline
23-10 applied: a selector that also decided what a run is worth on a report would be the fork this
wave exists to prevent. Naming the runs (SHX annot → sheet-text anchor → flag) is plan 23-15.

## Threat Flags

None — no new network, auth, filesystem or schema surface. No new file is read or written.

Registered mitigations, all delivered:

- **T-23-45 (a row of repeated tags reported as a measured pipe run)** — the four-gate requirement
  with the pitch-over-glyph-span ratio as the decisive test; the K.O. row and the five Chelsea
  candidates pinned as literal rejection fixtures; the zero-run sweep over all 76 pages of the other
  three sets as a permanent test; a synthetic tag row that fails ONLY the ratio gate pins the shape.
- **T-23-46 (dense micro-strokes make blob grouping quadratic)** — union-find over a spatial hash
  with the fixed 2 pt radius; the core's MAX_SEGMENTS cap carried into the selector's harvest;
  clip-bounded operation with no unclipped entry point.
- **T-23-47 (a borrowed scale reports an order-of-magnitude-wrong quantity)** — `run_scale_fpp`
  returns nothing rather than a borrowed scale, flags the run, and refuses both the page scale and
  a nested detail's enclosing-plan scale; pinned on the real Crow page and synthetically.
- **T-23-48 (the answer-key markup PDF leaks into the pipeline)** — the take-off PDFs are read only
  inside `tests/`; `grep -rn "takeoff\|Take off" src/` finds no reference; the answer-key readers
  live in the test module.
- **T-23-49 (one-sample generalisation)** — accepted as registered (R12): the glyph-strokes band and
  span cap admit the other stock annotated linetypes, the sweep is a permanent test, and the
  ambiguity gate lands with 23-15.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `39b98f7` | Annotated-linetype selector with the pitch-over-span coincidence gate |
| 2 | `33f9385` | Rail selector — per-pen chaining, pair collapse, typical-detail flag |
| 3 | `58e885c` | `run_scale_fpp` — a run is measured at its own drawing's scale or not at all |

## Requirement status

`V4-MEAS-03` and `V4-MEAS-05` are **advanced, not completed** — left unticked. The measurement and
scale-binding halves of both now exist and are position-validated, but no linear-foot quantity
reaches a line item: `basis: linear` has no consumer and the selectors have no call site in `src/`.
23-13 owns the binder; 23-15 owns the names.

## What this unblocks

- **23-13 (binders)** consumes `extract_linetype_runs`, `extract_rail_runs` and `run_scale_fpp`.
  Rail clips must come from the pipeline's own `_fill_clip_for_title` cell rule; rails are emitted
  per-instance with `unit_count=None` and `needs_review=True` (23-CONTEXT decision 2), and a
  typical-detail run is never summed with a main-plan run of the same object.
- **23-15 (naming)** reads `mark_signature`/`mark_stats` as grouping keys and applies the
  SHX-annot → sheet-text → flag priority with the ambiguity gate.

**The standing caution, carried forward verbatim:** measuring a run is not counting the runs.
Crow's golden rail totals are ~6× and ~21× what is drawn; the multiplier is not printed and not
recoverable from the linework. Tuning anything until a total reads 420.35 would be the coincidence
trap this phase exists to abolish.

## Self-Check: PASSED

- `src/bobbytailor/deterministic/open_runs.py` — FOUND
- `tests/test_open_runs.py` — FOUND
- `.planning/phases/23-measurement-engine-completion/23-12-SUMMARY.md` — FOUND
- commit `39b98f7` (Task 1) — FOUND
- commit `33f9385` (Task 2) — FOUND
- commit `58e885c` (Task 3) — FOUND
- `extract_linetype_runs` / `extract_rail_runs` / `run_scale_fpp` importable — OK
- `git diff --stat uploads/ human_inputs/ reports/ docs/PIPELINE-GROUND-TRUTH.md` — EMPTY
- no take-off PDF referenced anywhere under `src/` (T-23-48) — CLEAN
