---
phase: 24-binding-determinism-text-anchored-labeling
plan: 01
subsystem: deterministic-extraction
tags: [pymupdf, fitz, text-anchoring, set-of-mark, determinism, pytest]

# Dependency graph
requires:
  - phase: 23-measurement-engine-completion
    provides: "tag_pairing SP-6 (direction-generic two-token pairing, sheet_mask_rects) and the SP-7c bind_or_flag 'one match or flag' semantics"
provides:
  - "deterministic/text_anchor.py — the nearest-non-masked-word anchor primitive (the one new deterministic function V4-DET-01 needs)"
  - "bundle['candidate_anchors'] — one anchor record per symbol group, room and wall thickness class, computed before any vision call"
  - "A committed, runnable answer to 24-RESEARCH Open Question #4 (the bollard cluster has NO text anchor)"
  - "page_radius_pt — a search radius expressed in the page's own text heights, not in absolute points"
affects: [24-04 unnamed-geometry ledger, 24-07 SoM chip and prompt hint, 25 detection]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Anchor record: a JSON-serialisable dict whose anchor_text=None is a RECORDED ABSENCE, never a placeholder"
    - "Radius expressed in text heights and derived per page, because measured drafting text height varies 3.5x across the four plan sets on an identical sheet size"
    - "Contested anchor withdrawal (SP-7c bind_or_flag) applied to geometry-to-text binding"

key-files:
  created:
    - src/bobbytailor/deterministic/text_anchor.py
    - tests/test_text_anchor.py
  modified:
    - src/bobbytailor/pipeline/takeoff_pipeline.py

key-decisions:
  - "The anchor radius is expressed in TEXT HEIGHTS and derived from the page's own median word height, not pinned as an absolute point constant — measured free: Crow 9.56 pt, Moxy 9.64, Chelsea 7.56, Bob's 26.41, all on the identical 3024x2160 pt sheet"
  - "The candidate map is built from fusion.build_registry rather than three re-derived bbox rules, so a wall class is named exactly as _wall_candidate_id names it"
  - "A registry bbox of all zeros means position UNKNOWN, never position (0,0) — such a candidate earns a recorded absence instead of harvesting text at the page origin"
  - "A paired two-token tag outranks a nearer loose word, because a tag is a printed identifier whereas a loose word may be a dimension fragment"
  - "The drafting-noise predicate in fusion.py is deliberately NOT reused: it returns True for 'B-1' and 'P1', exactly the tags an anchor exists to harvest"
  - "Anchor coverage is REPORTED and never asserted against a floor — a floor would create pressure to widen the radius until the floor is met"

patterns-established:
  - "Recorded absence: an anchor that does not exist is a result with its own record, not a gap to be filled from shape"
  - "Contested-unit withdrawal: when one text unit is the nearest anchor for two candidates, BOTH are left unanchored with the contest named — names are never round-robined"
  - "Positional validation: a geometric constant is validated by which word it selects on a real page, never by an accuracy score moving"

requirements-completed: [V4-DET-01]
# HONEST SCOPE NOTE: this plan delivers the DETERMINISTIC HALF of V4-DET-01 — every candidate now
# carries its nearest plan text, or a recorded absence, before any vision call. The requirement is
# not fully satisfied until 24-07 puts the anchor on the SoM marker chip and in the prompt hint, and
# 24-04 turns a missing anchor into the flag that keeps a candidate out of the take-off. The phase
# gate (24-10) verifies the whole requirement. REQUIREMENTS.md was deliberately NOT ticked here.

coverage:
  - id: D1
    description: "The nearest-non-masked-word anchor primitive: contained word -> SP-6 two-token tag -> nearest single word -> recorded absence, with masking mandatory and ties broken by document order"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_text_anchor.py (24 synthetic tests: contained, masked, absence, tie-break, tag pairing, rotation, contest, JSON shape, radius)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every symbol-group, room and wall-class candidate in the deterministic bundle carries an anchor record before any vision call"
    requirement: V4-DET-01
    verification:
      - kind: integration
        ref: "tests/test_text_anchor.py#test_every_crow_candidate_carries_one_well_formed_anchor_record"
        status: pass
      - kind: integration
        ref: "python3 -m pytest tests/test_pipeline_deterministic.py tests/test_fusion.py -x -q (182 passed)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Anchor resolution is byte-identical across repeated calls over the same real page, and the bundle key is the same computation, not a second drifting implementation"
    requirement: V4-DET-01
    verification:
      - kind: integration
        ref: "tests/test_text_anchor.py#test_anchors_over_the_real_page_are_byte_identical_on_repeat"
        status: pass
    human_judgment: false
  - id: D4
    description: "The measured Crow baseline (Open Question #4 answered NO) is committed as a test that SKIPS rather than passes when its fixture is absent"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_text_anchor.py#test_the_contained_text_branch_is_empty_on_the_crow_plan_set"
        status: pass
      - kind: other
        ref: "pytest with CROW_PDF patched to a nonexistent path — 24 passed, 4 skipped (no vacuous pass)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Masked regions (schedule tables, title blocks, legends) can never supply an anchor"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_text_anchor.py#test_a_masked_word_is_never_the_anchor"
        status: pass
      - kind: integration
        ref: "tests/test_text_anchor.py#test_a_masked_region_supplies_no_anchor_on_the_real_page"
        status: pass
    human_judgment: false

# Metrics
duration: 3h 20m
completed: 2026-08-05
status: complete
---

# Phase 24 Plan 01: Text-Anchor Primitive Summary

**Every geometry candidate in the deterministic bundle now carries the words the drawing itself printed nearest to it — or a recorded absence — computed with no model in the loop, so the naming layer can READ a label instead of RECOGNISING a shape.**

## Performance

- **Duration:** 3h 20m (three full 46-min suites, one per commit, dominate it)
- **Started:** 2026-08-05
- **Completed:** 2026-08-05
- **Tasks:** 3
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- **`deterministic/text_anchor.py`** — the one deterministic primitive 24-RESEARCH §2.2 identified as missing: *"words within radius R of this bbox, excluding masked rects, ranked by distance."* Public surface: `ANCHOR_RADIUS_PT`, `anchor_record`, `page_words`, `page_tag_units`, `page_radius_pt`, `nearest_anchor`, `anchors_for_candidates`, `box_distance_pt`.
- **`bundle["candidate_anchors"]`** — one anchor record per symbol group, room and wall thickness class, emitted by `_deterministic_bundle` *before any vision call*, fully guarded so a failure leaves the bundle byte-identical to before the key existed.
- **Open Question #4 committed as a test.** The Crow bollard cluster has no text anchor, and that finding is now a runnable assertion instead of a planning transcript.
- **The tag branch is proven live, not dead code.** Crow prints zero ALONG two-token tags, but the same code path harvests **166** on Moxy (`WC 01`, `WD 01`, `PT 04`, `PT 05` — exactly the SP-6 material tags), so the ladder's middle rung works on a real sheet set.
- **Bounded scan cost (T-24-03):** a uniform-cell spatial index resolves 120 candidates against 1,566 words in **0.055 s** on Crow page 0.

## Task Commits

Each task was committed atomically:

1. **Task 1: The nearest-non-masked-word anchor primitive** — `ea2fd44` (feat)
2. **Task 2: Attach anchor records to every candidate in the deterministic bundle** — `0266128` (feat)
3. **Task 3: Lock the measured anchor baseline as a committed regression test** — `e6f1ccb` (test)

## Files Created/Modified

- `src/bobbytailor/deterministic/text_anchor.py` — the anchor primitive. Precedence: contained word → SP-6 two-token tag → nearest single word → recorded absence. Masking mandatory, ties broken by document order, contested units withdrawn from all claimants.
- `tests/test_text_anchor.py` — 28 tests. 24 synthetic (no PDF, no API) proving the contract; 4 over the real Crow bundle that SKIP rather than pass when the fixture is absent.
- `src/bobbytailor/pipeline/takeoff_pipeline.py` — module-scope `anchors_for_candidates` import; new `TakeoffPipeline._anchor_candidate_map` static helper; guarded `candidate_anchors` computation before the `_deterministic_bundle` return.

## Measurements taken this plan (all FREE, zero API)

**Drafting text height, all four plan sets** — the evidence behind the radius decision. All four print on an identical 3024 × 2160 pt sheet:

| Set | Median word height |
|---|---|
| Crow | 9.56 pt |
| Moxy | 9.64 pt |
| Chelsea | 7.56 pt |
| Bob's | 26.41 pt |

**Crow anchor coverage, all four sheets** (reported, never asserted against a floor):

| Sheet | Candidates | symbols / rooms / wall classes |
|---|---|---|
| p0 | 55 | 36 / 6 / 13 |
| p1 | 230 | 56 / 156 / 18 |
| p2 | 27 | 10 / 1 / 16 |
| p3 | 8 | 5 / 0 / 3 |

Page 0 kind split: 10 `contained`, 16 `nearest_word`, 29 absent, 17 withdrawn as contested.

**Symbol-group population re-measured and confirmed:** 36 + 56 + 10 + 5 = **107** groups across the four Crow sheets, matching the planning probe exactly. Page 0's `SYM-1` (count 136, 1.0 × 0.4 ft) and `SYM-2` (count 56, 0.8 × 0.87 ft) both carry **zero** `contained_texts`, exactly as the plan stated. 24 of page 0's 36 groups carry no contained text at all.

**Wall-class contention damage:** page-spanning wall-class union boxes suppress only **2** symbol/room anchors across all four sheets (1 on p0, 1 on p2), so including wall candidates costs almost nothing and every withdrawal fails in the safe direction.

## Decisions Made

- **The radius is a rule, not a number.** `ANCHOR_RADIUS_TEXT_HEIGHTS = 4.0` (the geometric limit of an unleadered callout); `ANCHOR_RADIUS_PT = 38.0` survives as the constant the plan named and as the fallback for a page with no measurable text. `anchors_for_candidates` derives the working radius from the page's own median word height.
- **Reuse over re-derivation.** Masking is `tag_pairing.bbox_inside_any`; two-token tags are `tag_pairing.pair_two_token_tags` on the `ALONG` axis; the candidate map is `fusion.build_registry` filtered to the three nameable kinds. No primitive was forked.
- **`ACROSS`-axis pairing is deliberately not harvested** — that is the room-tag stacking layout and `room_tags` already owns it.
- **Viewport regions are excluded from the anchor map.** A region is a place on the sheet, not an object anyone names.
- **The `ambiguity_reason` field carries only ambiguity.** A candidate with an unusable bbox gets a plain absence plus a debug log, so the field's name remains its contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] The anchor radius is derived per page rather than pinned as one absolute point constant**

- **Found during:** Task 1 (choosing `ANCHOR_RADIUS_PT` from page-geometry reasoning)
- **Issue:** The plan specifies a single `ANCHOR_RADIUS_PT` constant. Measuring median word height across all four plan sets (free, `page.get_text("words")`) found a **3.5× spread** — 7.56 pt on Chelsea against 26.41 pt on Bob's — on the *identical* 3024 × 2160 pt sheet. A single absolute radius is therefore ~5 text-heights of reach on one set and ~1.4 on another. `tests/test_four_set_coverage.py`'s own docstring records precisely what that class of constant costs this project: *"sweeping the title-block width fraction 0.55 → 0.88 fixes Moxy and BREAKS Chelsea, and nothing caught it because nothing looked at Chelsea."*
- **Fix:** The rule is expressed as `ANCHOR_RADIUS_TEXT_HEIGHTS = 4.0` and `page_radius_pt(words)` returns `median(word height) × 4.0`. `ANCHOR_RADIUS_PT` is retained with the name and value the plan specified (4 × 9.5 = 38.0) as `nearest_anchor`'s default and as the empty-text-layer fallback. `anchors_for_candidates(page, ..., radius_pt=None)` derives; passing an explicit float pins it.
- **Why this is not tuning:** the value was never selected by running a take-off and watching a score. It comes from page geometry and is validated positionally (`test_the_radius_bounds_the_search_by_position`: 20 pt away is in at r=38, out at r=10).
- **Files modified:** `src/bobbytailor/deterministic/text_anchor.py`
- **Verification:** `test_the_radius_is_expressed_in_text_heights_of_the_page_it_reads`, `test_the_fallback_radius_is_four_nominal_text_heights`
- **Committed in:** `ea2fd44`

**2. [Rule 1 - Bug] A wall class with no segment records was about to anchor at the page origin**

- **Found during:** Task 2 (building the candidate map)
- **Issue:** `fusion.build_registry` gives a wall class with no segment records the bbox `(0, 0, 0, 0)`. That is "position unknown", but a naive pass-through would have made it a real 0-area box at the page corner, harvesting whatever text sits at the origin as that class's anchor — a fabricated name from a fabricated position.
- **Fix:** `_anchor_candidate_map` maps an all-zero registry bbox to an empty tuple, which `_resolve` records as an absence with a debug log.
- **Files modified:** `src/bobbytailor/pipeline/takeoff_pipeline.py`
- **Verification:** `test_a_candidate_with_an_unusable_bbox_is_an_absence_not_a_crash`
- **Committed in:** `0266128`

**3. [Process] TDD RED gate was proven, not committed separately**

- **Found during:** Task 1 (`tdd="true"`)
- **Issue:** The TDD cycle wants a `test(...)` RED commit before the `feat(...)` GREEN commit. The execution contract for this plan requires the **full suite green before each commit**, and a RED commit is red by construction.
- **Fix:** The RED gate was executed and observed — with `text_anchor.py` moved aside, `python3 -m pytest tests/test_text_anchor.py` fails at collection with `ModuleNotFoundError: No module named 'bobbytailor.deterministic.text_anchor'`. The module was then restored (GREEN, 24 passed) and test + implementation committed as one atomic `feat` commit. No knowingly-broken tree entered history.
- **Committed in:** `ea2fd44`

---

**Total deviations:** 3 (1 missing-critical, 1 bug, 1 process)
**Impact on plan:** All three strengthen the plan's own stated invariants — generalisation across the four plan sets, "never named from shape", and a green history. No scope creep; no new package; no new public surface beyond the primitive itself.

## GitNexus (CLAUDE.md, mandatory)

- **Before editing `_deterministic_bundle`:** `impact(_deterministic_bundle, direction=upstream)` → **risk LOW**, 3 impacted, 1 direct caller (`_run_sheet_vector`), 2 affected processes (`run_sheet`, `_run_sheet_vector`), 1 module (Pipeline). No HIGH/CRITICAL, so no warning was required before proceeding.
- **`detect_changes()` before each commit:** run before all three. Before the Task 2 commit it reported **risk HIGH / 10 affected flows**. **⚠️ Warning recorded as the plan requires.** The reading over-attributes: the index is stale at `c4f6e7d` and credits `_FILL_CLIP_UP_PT`, `_FILL_CLIP_SIDE_PT`, `_LINEAR_RUNS_PER_CLIP`, `_fill_clip_for_title`, `_measure_linear_runs` and `gap` — none of which this diff touches — to the change. The genuinely changed symbols are `_deterministic_bundle` and the new `_anchor_candidate_map`. Empirically the blast radius is zero: the full suite was **unchanged at 1968 passed** across that commit.
- The index remains stale (`c4f6e7d` vs HEAD). Re-running `npx gitnexus analyze` is left to the phase orchestrator, since re-indexing mid-plan would invalidate the impact readings quoted above.

## Test Results

| Gate | Result |
|---|---|
| Baseline (phase entry) | 1944 passed, 1 skipped, 2 deselected |
| Full suite before `ea2fd44` | **1968 passed**, 1 skipped, 2 deselected (47:14) |
| Full suite before `0266128` | **1968 passed**, 1 skipped, 2 deselected (46:14) — unchanged by the pipeline edit |
| Full suite before `e6f1ccb` | **1972 passed**, 1 skipped, 2 deselected (46:44) |
| `tests/test_pipeline_deterministic.py` + `tests/test_fusion.py` + `tests/test_text_anchor.py` | 182 passed |
| `tests/test_phase23_acceptance.py`, `tests/test_four_set_coverage.py` | green (inside every full-suite run; nothing deselected but the 2 paid tests) |

Net: **+28 tests, 0 regressions.** 1944 + 28 = 1972.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | `grep -Ec 'ANTHROPIC_API_KEY\|analyze_drawing\|anthropic' src/bobbytailor/deterministic/text_anchor.py` → **0**; `grep -Ec 'golden\|accuracy_gate\|vision_only_benchmark\|golden_convergence\|ANTHROPIC_API_KEY' tests/test_text_anchor.py` → **0**. `.env` never read. |
| Noise predicate not reused | `grep -c '_is_noise_token' src/bobbytailor/deterministic/text_anchor.py` → **0**; the module imports nothing from `bobbytailor.vision`. |
| Coincidence trap fenced | `grep -Ec '== *28\b\|== *132\b\|== *136\b\|== *56\b' tests/test_text_anchor.py` → **0**. The 56 and the 136 are identified by RANK, never by value, and neither is adjusted. |
| No numeric field in a vision schema | No schema file touched. |
| Paid-run evidence untouched | `git status --porcelain .planning/paid-run-evidence/ \| wc -l` → **0** (checked before every commit). |
| `uploads/`, `human_inputs/`, `reports/`, `.env` untouched | Not in any commit; `git status` clean of them throughout. |
| No new packages | None. `fitz` and `pytest` were already imported by the modules under edit. |
| Python 3.9 | `python3 --version` → 3.9.6; `from __future__ import annotations` used; no 3.10+ syntax. |
| No `--no-verify` | Every commit ran hooks normally. |

## Issues Encountered

- **The 11-way `CASS` contest.** On Crow page 0, eleven wall-class boxes plus `ROOM-1` all contain the title word `CASS`, so all eleven were withdrawn as contested. Investigated rather than assumed: measured that including wall candidates suppresses only 2 symbol/room anchors across all four sheets. The withdrawal is exactly the `bind_or_flag` semantics the plan mandates and it fails in the safe direction, so it was left as specified. Wall classes are named deterministically by thickness in plan 24-03 anyway; a text anchor was never their route to a name.
- **An early draft of the real-PDF masking test contained a vacuous `assert chosen or True`** and an O(n²) scan that re-extracted the page text per anchor. Rewritten as a linear set claim: no anchor text may be text that exists *only* inside a mask. A vacuous assertion is the exact anti-pattern `test_phase23_acceptance.py` rule 3 forbids.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

**Ready for 24-04 (unnamed-geometry ledger)** — `bundle["candidate_anchors"]` supplies exactly the signal the ledger gate needs: `anchor_text is None` marks a candidate that must not publish as a line item, and `ambiguity_reason` explains why when the cause is a contest.

**Ready for 24-07 (SoM chip + prompt hint)** — records are JSON-serialisable and keyed by candidate ID, so `overlay._draw_marker`'s `label = candidate_id` can become `f"{candidate_id} {anchor_text}"` with no further deterministic work.

**Carried forward for 24-07 (threat T-24-01):** anchor text is untrusted drawing text and is DATA in this plan — nothing interpolates it into a prompt yet, so it carries no escaping obligation here. Plan 24-07 owns delivery and **MUST** wrap it in the `<pdf_text>` delimiters via `prompts.wrap_pdf_text`.

**Honest expectations to carry into verification:**
- Anchor coverage on Crow is **low** — 26 of 55 candidates on page 0, 8 of 212 on page 1. That is an outcome of the drawing, not a defect to tune away. Crow's plan body is sparsely annotated and its symbol clusters carry no contained text at all. Widening the radius to raise this number is the tuning trap.
- **No accuracy claim is made or measurable here.** The 0.03→0.65 mechanism is published benchmark evidence on other datasets (24-RESEARCH assumption A3); confirming it on this codebase requires a paid run, which is user-authorised only. Judge this plan on determinism and honesty.

## Self-Check: PASSED

All claimed files exist on disk (`text_anchor.py`, `test_text_anchor.py`, `takeoff_pipeline.py`, this SUMMARY). All three claimed commits resolve in `git log` (`ea2fd44`, `0266128`, `e6f1ccb`). `.planning/paid-run-evidence/` is untouched (0 porcelain entries).

---
*Phase: 24-binding-determinism-text-anchored-labeling*
*Completed: 2026-08-05*
