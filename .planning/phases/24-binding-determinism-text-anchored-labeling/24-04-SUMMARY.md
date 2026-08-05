---
phase: 24-binding-determinism-text-anchored-labeling
plan: 04
subsystem: vision-fusion
tags: [naming, ledger, flag-dont-guess, determinism, text-anchor, pytest]

# Dependency graph
requires:
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 01
    provides: "bundle['candidate_anchors'] — the masked, contest-aware nearest-plan-text answer per candidate, and the recorded ABSENCE that this plan turns into the flag keeping a candidate out of the take-off"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 02
    provides: "the inverted wall-class precedence, which makes the identifier else-branch reachable only when NEITHER a printed-thickness bind NOR a vision label exists"
  - phase: 23-measurement-engine-completion
    provides: "INV-08's 'a blank is never a zero'; sheet_mask_rects and its containment rule; the C3a arbitration record shape this ledger's `detail` field mirrors"
provides:
  - "UNNAMED_GEOMETRY_KEY — a THIRD top-level audit list on the fuse_sheet result, neither a vision-answer rejection nor a coverage gap"
  - "unnamed_geometry_record — one measured-but-unidentified candidate with its quantity, unit, position, evidence text, machine reason and human detail"
  - "is_name_worthy + NAME_WORTHY_SOURCES — one closed declared set of admissible naming routes"
  - "the name-worthiness gate at all three `or cid` leak sites (symbols, wall classes, rooms)"
  - "_room_name_failure — the room name-plausibility rules, including the live orphan-room branch 24-07 only has to populate"
  - "bundle['mask_rects'] — the sheet's own schedule/title-block/legend rectangles, published so a reader with no page access can apply them"
affects: [24-05 vocabulary persistence, 24-06 ledger surfacing, 24-07 SoM chip + wall reference schema, 24-10 phase gate, 25 detection]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Relocation, never deletion: an excluded quantity is moved to a ledger with its evidence, and the test asserts BOTH halves so neither can be satisfied alone"
    - "Explicit source over inferred source: a name's provenance is an argument, never a string-match of the name against the candidate ID"
    - "Harvesting and publishing are different decisions: an anchor is collected unfiltered and gated only at publication"
    - "A closed declared set as an alarm: a new publication path cannot publish until it is registered"
    - "A bound validated by what the drawings PRINT, never by an accuracy figure moving"
    - "An absent field is not a zero (INV-08) applied to a forward handoff: the orphan branch fires on present-and-empty, never on absent"

key-files:
  created: []
  modified:
    - src/bobbytailor/vision/fusion.py
    - src/bobbytailor/pipeline/takeoff_pipeline.py
    - tests/test_fusion.py
    - tests/test_naming_conventions.py
    - tests/test_symbol_binding.py
    - tests/test_symbol_identification.py
    - .planning/ROADMAP.md

key-decisions:
  - "The ledger gets its OWN top-level key. Overloading fusion_rejected would hand these records to Phase 23's C3a reinstatement logic, which keys on suppression records; overloading coverage_ledger would break its one-row-per-source-page invariant. A measured-but-unidentified candidate is a third thing."
  - "is_name_worthy takes the source EXPLICITLY. Inferring it by matching the name against the candidate ID would discard Moxy's genuine `WC 01` / `PT 04` material tags (24-01 measured 166) while still admitting any identifier that happened not to match."
  - "Harvesting an anchor and PUBLISHING it are different decisions, exactly as 24-01's docstring reserved for this plan. A paired two-token tag publishes; a loose nearest word must first clear the drafting-noise predicate. The split is by anchor KIND, so genuine printed tags survive on evidence rather than by luck."
  - "The room token bound is 6 = the longest printed room name this project's plan sets contain (3, measured over 424 tags) + its room number (1) + two tokens of slack. It was NOT chosen by lowering it until Crow's 19-token label disappeared."
  - "The orphan-room branch fires on a PRESENT-AND-EMPTY wall reference, never on an ABSENT field. rooms.py builds every face FROM wall centrelines, so the walls exist and merely go unrecorded until 24-07; reading the absent field as 'no walls' would assert something false about the geometry and would stop every room on every plan set from publishing."
  - "`deterministic_geometry` is a DECLARED member of NAME_WORTHY_SOURCES rather than an implicit survivor — it is the one entry that names from geometry rather than text, and it is measured to fire zero times on Crow pages 0 and 1."
  - "A vision answer echoing the candidate ID is the identifier arriving by a second route, and falls through to the naming ladder on both the symbol and the room path."

requirements-completed: []
# HONEST SCOPE NOTE: this plan carries `requirements: [V4-DET-01]` and does NOT tick it, for
# the same reason 24-01 did not. 24-01 delivered the deterministic half (every candidate carries
# its nearest plan text or a recorded absence); this plan delivers the half that turns a missing
# anchor into the flag keeping a candidate out of the take-off; 24-07 still owes the SoM marker
# chip and the prompt hint. The phase gate (24-10) verifies the whole requirement.

coverage:
  - id: U1
    description: "A raw candidate ID is never a line item — no SYM, ROOM or WALL-TC identifier reaches components as a name"
    requirement: V4-DET-01
    verification:
      - kind: integration
        ref: "tests/test_fusion.py#test_no_raw_candidate_ids_reach_the_takeoff (real Crow page 0)"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_unnamed_geometry_a_vision_answer_echoing_the_candidate_id_is_not_a_name"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_name_plausibility_a_vision_answer_echoing_the_room_id_is_not_a_name"
        status: pass
      - kind: other
        ref: "measured on Crow page 0: published_with_id_name 0 (was 41 of 45 components)"
        status: pass
    human_judgment: false
  - id: U2
    description: "Every candidate excluded from the take-off appears in an unnamed-geometry record carrying its quantity, unit, position, contained text and the named reason"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_unnamed_geometry_record_carries_the_whole_evidence"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_unnamed_geometry_symbol_group_with_no_name_source_is_ledgered"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_unnamed_geometry_unlabeled_wall_class_is_ledgered_with_its_lf"
        status: pass
      - kind: integration
        ref: "measured on Crow page 0: ledger 42, ledger_with_qty 42 (equal)"
        status: pass
    human_judgment: false
  - id: U3
    description: "The set of candidates that left the take-off equals the set that entered the ledger — nothing deleted, nothing invented (T-24-14)"
    requirement: V4-DET-01
    verification:
      - kind: integration
        ref: "tests/test_fusion.py#test_no_raw_candidate_ids_reach_the_takeoff — six assertions, both directions, one function"
        status: pass
      - kind: other
        ref: "probed on all four Crow sheets: 0 in both lists, 0 unexplained, 0 invented, 0 duplicated; the only candidates in neither are the pure-noise drops (12/12, 7/7, 5/5, 2/2)"
        status: pass
    human_judgment: false
  - id: U4
    description: "A numeric-only or drafting-noise token is not a name, on the room path AS WELL AS the symbol path"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_name_plausibility_a_bare_digit_never_names_a_room_from_either_source (all three label_source values)"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_name_plausibility_a_room_number_is_not_a_room_name"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_name_plausibility_a_drafting_noise_anchor_never_names_a_symbol_group"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_name_plausibility_a_paired_two_token_tag_still_names_a_symbol_group (the rule that must NOT fire)"
        status: pass
    human_judgment: false
  - id: U5
    description: "A room whose label was harvested from a masked schedule region is not named from it (T-24-15)"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_name_plausibility_a_masked_origin_room_is_never_named_from_its_text (positional: the same room outside the mask publishes)"
        status: pass
      - kind: other
        ref: "bundle['mask_rects'] published by _deterministic_bundle; 1 mask rect present on Crow page 0"
        status: pass
    human_judgment: false
  - id: U6
    description: "The token bound was validated against real printed room names, never against a golden figure (T-24-17)"
    requirement: V4-DET-01
    verification:
      - kind: other
        ref: "424 genuine printed room tags read off Moxy / Chelsea / Bob's text layers; longest is 3 tokens; 100% at <= 3"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_the_token_bound_was_validated_against_real_room_names"
        status: pass
      - kind: other
        ref: "grep -A30 'def test_name_plausibility' tests/test_fusion.py | grep -Ec '279\\.5|396059|396053' -> 0"
        status: pass
    human_judgment: false
  - id: U7
    description: "The unnamed-geometry records live under their own key and do not touch fusion_rejected (T-24-16)"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_unnamed_geometry_key_is_its_own_key_not_an_overload"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_unnamed_geometry_the_rejection_audit_list_is_untouched"
        status: pass
      - kind: other
        ref: "grep -c fusion_rejected src/bobbytailor/vision/fusion.py: 16 before -> 15 after (decreased, never increased)"
        status: pass
    human_judgment: false
  - id: U8
    description: "The orphan-room branch (V4-DET-03) is live now and 24-07 only has to populate the field"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_fusion.py#test_orphan_room_with_an_empty_wall_reference_is_ledgered_never_published"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_orphan_room_with_a_populated_wall_reference_publishes"
        status: pass
      - kind: unit
        ref: "tests/test_fusion.py#test_orphan_room_an_absent_wall_reference_is_not_read_as_an_absent_wall"
        status: pass
    human_judgment: false

# Metrics
duration: 5h 01m
completed: 2026-08-05
status: complete
---

# Phase 24 Plan 04: The Unnamed-Geometry Contract Summary

**A raw candidate ID is never a line item: the 27 rows named `SYM-6`, `ROOM-3`, `WALL-TC4` and the one named `4` that both saved paid runs shipped to the client — 34% of a 79-row take-off — now arrive in an unnamed-geometry ledger carrying every quantity intact, and the test that proves it fails as loudly on a deletion as on a leak.**

## Performance

- **Duration:** 5h 01m (three full 47–48 minute suites, one per commit, dominate it)
- **Started:** 2026-08-05
- **Completed:** 2026-08-05
- **Tasks:** 3
- **Files modified:** 7

## The defect, measured on the real deliverable

Not on a probe — on the two saved paid runs' own `takeoff.json`, the artifacts a client would have received:

| saved run | take-off rows | rows named with a raw candidate ID | rows named with a bare digit |
|---|---|---|---|
| `VisionOnly_P23V2_Crow_20260804_181352` | 79 | **27** (34%) | 1 — `4` at 279.5 SF |
| `VisionOnly_P23V_Crow_20260804_141952` | 77 | **27** (35%) | 1 — `4` at 279.5 SF |

Both lists open `ROOM-3, ROOM-4, ROOM-5, ROOM-6, SYM-1, SYM-10, SYM-11, SYM-17, …` — exactly the objective's `SYM-1`…`SYM-35`, `ROOM-3`…`ROOM-6` and the item literally named `"4"`. The scorer's own output prints them as unmatched additions: `+ SYM-6  36.0 EA`, `+ SYM-7  32.0 EA`, `+ SYM-9  14.0 EA`.

And at the fusion layer on Crow page 0, before this plan: **41 of 45 published components were named with their own candidate ID**, beside one room named `4` and one named by a 19-token text harvest at 396,059 SF.

**After:** `published_with_id_name 0`, `digit_named 0`, `long_named 0`, ledger 42, every one of the 42 carrying a quantity.

## Accomplishments

- **The gate at all three leak sites**, plus two the plan did not name: a vision answer that echoes the candidate ID (on both the symbol and the room path) is the identifier arriving by a second route and no longer publishes.
- **The relocation is asserted in both directions by one function that cannot be half-satisfied**, over the real Crow page 0 bundle. Probed across all four sheets the partition is exact: **0 candidates in both lists, 0 unexplained, 0 invented, 0 duplicated**, and the only candidates in neither are the pre-existing pure-noise drops — re-derived in-test with `_is_noise_cluster` rather than waved away (12/12, 7/7, 5/5, 2/2).
- **The token bound is validated by what the drawings PRINT.** 424 genuine room tags read off three plan sets' text layers; the longest is 3 tokens. The bound sits 3× above the longest genuine polygon harvest and 3.2× below the accident it catches, so it is nowhere near doing delicate work.
- **Four shipped tests that pinned the abolished contract were converted, never deleted** — each now asserts both halves, so the count each used to protect is still protected, in the place it now lives.
- **The 56 and the 136 were not touched.** `SYM-2` (56) and `SYM-1` (136) are both ledgered with their counts exactly as measured. No count was adjusted in either direction.

## Task Commits

Each task was committed atomically:

1. **Task 1: The unnamed-geometry record and the name-worthiness gate** — `6a6b338` (feat)
2. **Task 2: The room name-plausibility gate** — `7b44bb0` (feat)
3. **Task 3: Prove the relocation both ways** — `805a6a9` (test)

## Files Created/Modified

- `src/bobbytailor/vision/fusion.py`
  - `UNNAMED_GEOMETRY_KEY`, `unnamed_geometry_record`, `is_name_worthy`, `NAME_WORTHY_SOURCES`, `_anchor_for`, the seven stable reason keys, `_ROOM_LABEL_MAX_TOKENS`, `ROOM_WALL_REFERENCE_FIELD`, `_ANCHOR_KIND_PAIRED_TAG`.
  - `_fuse_symbol_groups` — the `or cid` fallback replaced by the anchor branch, the drafting-noise gate and the ledger; the vision branch guarded against an ID echo.
  - `_fuse_wall_classes` — the `"name": cid` else-branch replaced by a ledger record carrying the class LF and its linework bbox.
  - `_room_name_failure` (new) + `_fuse_rooms` — the five room rules and the ledger.
  - `_is_noise_token` — one structural addition: a two-sided size callout.
  - `fuse_sheet` — the ledger list, the additive result key, the docstring and a log line.
  - `bbox_inside_any` imported at module scope (pure, no cycle, same rule every other plan-body reader uses).
- `src/bobbytailor/pipeline/takeoff_pipeline.py` — `bundle["mask_rects"]`, a publication of the list the method already computed.
- `tests/test_fusion.py` — **36 new tests** in three documented 24-04 sections.
- `tests/test_naming_conventions.py`, `tests/test_symbol_binding.py`, `tests/test_symbol_identification.py` — four shipped tests converted to the both-halves form.
- `.planning/ROADMAP.md` — 24-04 ticked, 3/10 → 4/10.

## Measurements taken this plan (all FREE, zero API)

**Genuine printed room names, read off the drawings' own text layers** — the evidence behind the token bound:

| Set | Room tags | Token-count histogram | Longest |
|---|---|---|---|
| Moxy | 271 | `{1: 84, 2: 175, 3: 12}` | `K SUITE C` (3) |
| Chelsea | 119 | `{1: 6, 2: 113}` | `UNITS B1B` (2) |
| Bob's | 34 | `{1: 34}` | `VESTIBULE` (1) |
| **All** | **424** | `{1: 124, 2: 288, 3: 12}` | **3 tokens, 100% at ≤ 3** |

Crow prints **zero** paired room tags — its plan-body faces carry room numbers and wall-type codes, never names.

**The actual polygon-label harvest, nine real sheets** (Crow p0–p3, Moxy p4/p5/p23, Chelsea p0/p1): `{0 tokens: 300, 1: 25, 2: 1, 19: 1}`. Every genuine harvest is ≤ 2 tokens; the single 19-token outlier is Crow page 0's `ROOM-1`.

**Crow page 0, before → after this plan:**

| | before | after |
|---|---|---|
| published components | 45 | 3 |
| named with own candidate ID | **41** | **0** |
| bare-digit names | 1 (`4`) | 0 |
| >12-token names | 1 (19 tokens) | 0 |
| unnamed-geometry records | — | 42 (23 symbol, 13 wall class, 6 room) |
| records carrying a quantity | — | 42 of 42 |
| `fusion_rejected` | 0 | 0 |

**Ledger population, all four Crow sheets:** p0 42, p1 223, p2 20, p3 6.

**`deterministic_symbol_name` fires ZERO times** on Crow pages 0 and 1 — measured, which is why keeping that branch (per task 1's behaviour contract) costs the mission plan set nothing.

## Decisions Made

- **The ledger gets its own key.** Phase 23's C3a reinstatement logic keys on the suppression records inside `fusion_rejected` and would have acted on these; `coverage_ledger`'s invariant is one row per source page. The occurrence grep is asserted not to increase and in fact went **16 → 15**.
- **`is_name_worthy` takes the source explicitly.** Inferring it by matching the name against the candidate ID would throw away Moxy's genuine `WC 01` / `PT 04` material tags — 24-01 measured 166 of them — while still admitting any identifier that happened not to match. Pinned by `test_is_name_worthy_takes_the_source_explicitly_never_by_resemblance`, where `SYM-1` from a text anchor publishes and `SYM-1` from the ID route does not.
- **`NAME_WORTHY_SOURCES` is a closed set and therefore an alarm.** A new publication path cannot publish until it is registered, and 24-03's `test_every_published_naming_source_comes_from_the_one_precedence` is its counterpart at the aggregator.
- **The room rules run for BOTH `label_source` values.** The measured single-digit room name arrived via `text_in_polygon`, so a gate guarding only the vision fallback would have missed the actual defect. Pinned by parametrising the digit test across all three values.
- **A room NUMBER is not a room NAME.** Crow page 1 published rooms named `101` and `102`; the noise rule refuses them. A number says where a room is, never what it is.
- **The masked-origin rule claims containment only.** A face drawn *inside* a mask is not a plan-body room. The converse — a face so large it *swallows* a mask — is deliberately **not** claimed, because fusion never sees the page and cannot say which harvested words came from inside the mask. That case is what the token-run rule catches, and it is what catches Crow's `ROOM-1`. Stating the limit beats a rule that quietly over-reaches.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical] The unfiltered anchor branch was publishing drafting noise as EA line items**

- **Found during:** Task 1, running the plan's own real-sheet acceptance command.
- **Issue:** The plan says to consult `bundle["candidate_anchors"]` and name the component from the anchor text, and my hard constraints forbid reusing `_is_noise_token` where genuine tags must survive. Implemented literally, Crow page 0 published EA line items named `12`, `DWG`, `1/A-112`, `A-101` and `14'-0"x16'-0"` — a gridline bubble, a drafting abbreviation, a detail reference, a sheet id and a door size. That is the plan's own defect wearing a new costume: a report row reading "12 × 14'-0"x16'-0"" is not better than one reading "12 × SYM-9". The plan's must-have is explicit that it must not happen: *"A numeric-only or drafting-noise token is not a name, on the room path **as well as the symbol path**."*
- **Fix:** the split is by anchor **KIND**, which 24-01 already records. An SP-6 paired two-token tag (`WC 01`, `PT 04` — the 166 Moxy tags the constraint protects) is an identifier the drawing itself formed by pairing, and publishes. A loose nearest word must first clear `_is_noise_cluster`. So genuine tags survive on **evidence**, not on luck — every one of `WC 01`, `PT 04`, `WD 01` is drafting noise to the token predicate and would have been lost to a blanket filter.
- **Why this does not contradict 24-01:** that module's own docstring reserves this exact question for this plan — *"Whether an anchored name is publishable is a separate decision, made later, by plan 24-04."* Harvesting is unchanged; only publication is gated.
- **Files modified:** `src/bobbytailor/vision/fusion.py`
- **Verification:** `test_name_plausibility_a_drafting_noise_anchor_never_names_a_symbol_group`, `test_name_plausibility_a_paired_two_token_tag_still_names_a_symbol_group` (the rule that must NOT fire), `test_the_paired_tag_anchor_kind_string_has_not_drifted`
- **Committed in:** `6a6b338`

**2. [Rule 3 — Blocking] The masks were not on the bundle, so the masked-origin rule would never have run**

- **Found during:** Task 2, threading `sheet_mask_rects` as instructed.
- **Issue:** The plan states *"The masks are already computed in the bundle; thread them rather than recomputing."* They are computed in `_deterministic_bundle`'s **local scope** — three readers above are each handed the list explicitly — and never stored on the bundle. Fusion cannot be handed them, because it never sees the page. Left as-is, the T-24-15 mitigation would have been a rule that compiles, tests green against a synthetic mask list, and fires on no real sheet ever: the worst kind of security control.
- **Fix:** `bundle["mask_rects"]` publishes the same `table_bboxes + mask_rects` list the method already built. A publication, not a second derivation. This required editing `takeoff_pipeline.py`, one file outside the plan's stated fence — recorded here rather than left for a reader to discover in the diff.
- **Files modified:** `src/bobbytailor/pipeline/takeoff_pipeline.py`
- **Verification:** `test_name_plausibility_a_masked_origin_room_is_never_named_from_its_text` asserts positionally — the same room *outside* the mask still publishes — so the rule cannot be quietly rejecting everything. 1 mask rect measured present on Crow page 0.
- **Committed in:** `7b44bb0`

**3. [Rule 1 — Bug] `_is_noise_token` did not recognise a two-sided size callout**

- **Found during:** Task 1, reading the list of names the anchor branch published.
- **Issue:** `14'-0"x16'-0"` is an overhead-door opening size. It survived every existing rule (the dimension regex matches one side, not a pair) and was about to name a counted EA line item.
- **Fix:** a structural rule — split on `x`/`X`/`×`, and **both** sides must themselves be feet-inch dimensions. It cannot swallow a real object name: `6x6 Post` has a second token that is a word, and a cluster is noise only when *every* token is.
- **Files modified:** `src/bobbytailor/vision/fusion.py`
- **Verification:** `test_a_size_callout_is_drafting_noise_but_a_product_name_is_not`
- **Committed in:** `6a6b338`

### Readings of the plan, recorded rather than left implicit

**4. The orphan-room branch fires on a PRESENT-AND-EMPTY reference, never on an ABSENT field**

The plan says to *"write the branch now against the absence of the reference so 24-07 only has to populate it."* Read literally — absent field means no bounding wall — the branch would fire on **every room on every plan set**, including `WAREHOUSE`, and the entire room path would stop publishing until 24-07 lands. Worse, it would assert something false: `rooms.py` builds every face **from wall centrelines**, so the bounding walls demonstrably exist and merely go unrecorded. Reading an absent field as a zero is precisely what INV-08 forbids, and this phase inherits that contract.

The branch is therefore live, tested and complete — it reads `ROOM_WALL_REFERENCE_FIELD` and ledgers on an explicit empty — and 24-07 has exactly one thing left to do: populate it. The tests construct the reference explicitly, as the plan requires, and a third test pins the absent case so the handoff cannot be silently changed.

**5. `deterministic_geometry` is a declared member of `NAME_WORTHY_SOURCES`**

The must-have truth says a candidate may be named *"never from a bare shape"*; task 1's behaviour contract says a symbol group with *"no deterministic geometry name"* produces no component — which preserves that branch. `deterministic_symbol_name` names a large regular grid `"Columns"`, which is naming from a shape. The behaviour contract won, because it is the half the acceptance criteria test. Rather than leave the tension implicit, the entry sits in the declared set with a comment naming the tension, it is already unconditionally `needs_review=True`, and it is **measured to fire zero times** across Crow pages 0 and 1. Removing it is one line and one decision, not an archaeology.

### Process

**6. Four shipped tests pinned the contract this plan abolishes**

`test_fuse_unknown_label_keeps_deterministic_count_flagged`, `test_fuse_wall_classes_labeled_and_unlabeled`, `test_no_bind_and_no_label_still_reaches_the_unlabeled_branch`, `test_ambiguous_wall_class_stays_needs_review`, `test_two_unnamed_clusters_stay_distinct_flagged_rows`, `test_unlabeled_non_grid_group_surfaces_flagged_with_its_count` and `test_unknown_symbol_label_never_emits_the_sentinel_as_a_named_item` all asserted that an unidentified candidate publishes as a flagged row named with its ID. Every one was **converted, never deleted**: each now asserts that the row does not publish **and** that the count it protected is in the ledger. One of them — `test_no_bind_and_no_label_still_reaches_the_unlabeled_branch` — carried the docstring *"Plan 24-04 owns this branch"*, written by 24-02 in anticipation.

`test_unknown_symbol_label_never_emits_the_sentinel_as_a_named_item` needed particular care: its assertion *"unknown is not among the names"* would have become **vacuously true** once the row stopped publishing at all. It now asserts the ledger record too, so it still checks something.

**7. The TDD RED gate, honestly**

This plan is `tdd="true"`, and the strict RED-first cycle was **not** run: within each task the implementation and its tests were written together and committed atomically, because the execution contract requires the full suite green before every commit and a RED commit is red by construction. What *was* observed is a genuine falsification signal of the same kind and arguably stronger: the pre-existing suite went **red in exactly seven places**, all of them assertions of the contract being abolished, and none anywhere else. Recorded plainly rather than dressed up as a RED gate that was not run.

---

**Total deviations:** 3 auto-fixed (1 missing-critical, 1 blocking, 1 bug), 2 recorded readings, 2 process. No scope creep, no new package, no new public surface beyond the ledger, its record builder, the gate and the room predicate.

## The re-score, recorded and explicitly not acted on

`python3 scripts/score_report_dir.py --golden tests/fixtures/crow_cass/crow_cass_golden.csv --dir .planning/paid-run-evidence/VisionOnly_P23V2_Crow_20260804_181352`, **exit 0**:

> **Overall quantity accuracy: 30%   Name/found rate: 90%   Qty acc when found: 33%**
> Counts (EA) n=6 found=83% qty_ok=17% · Measured(SF/LF) n=4 found=100% qty_ok=50%

Unchanged from 24-03's recorded 30%, **and it could not have moved**: the scorer reads a *static saved artifact*, so it measures the 2026-08-04 18:13 run, not this commit. The number is recorded because the plan requires it to be recorded, and it is not acted on.

**The naive metric is expected to DROP when this reaches a live run, and that is the correct outcome.** Crow page 0 went from 45 published components to 3. The plan says so in advance, 24-RESEARCH pitfall 4 says so, and Phase 23's rails set the precedent. Judge this plan on whether the report now tells the truth about what it could not identify — not on a percentage. A success criterion phrased as an accuracy percentage is forbidden here.

Worth noting for whoever reads the score next: the scorer's own unmatched-additions list is where the defect this plan closes is most visible — `+ SYM-6 36.0 EA`, `+ SYM-7 32.0 EA`, `+ SYM-9 14.0 EA` and twenty-four more.

## GitNexus (CLAUDE.md, mandatory)

- **Before editing any fusion symbol**, `impact(..., direction=upstream)` on all four targets:
  - `fuse_sheet` — **LOW**, 3 impacted, 1 direct caller (`_run_sheet_vector`), 2 affected processes.
  - `_fuse_symbol_groups` — **HIGH**, 3 impacted, 1 direct caller, 3 affected processes.
  - `_fuse_rooms` — **HIGH**, 3 impacted, 1 direct caller, 3 affected processes.
  - `_fuse_wall_classes` — **HIGH**, 3 impacted, 1 direct caller, 3 affected processes.
  - **⚠️ HIGH risk warned before a line was changed**, as CLAUDE.md requires. All three helpers are private and single-caller (`fuse_sheet`), so the blast radius is bounded by the full suite.
- **`detect-changes` before each commit:** low / **HIGH (15 affected processes)** / low. **⚠️ The HIGH reading before the task-2 commit is recorded as the plan requires.** It over-attributes: the index is stale at `c4f6e7d` and credits `_GRID_MIN_LINES`, `_GRID_SPACING_CV_MAX`, `centroids`, `gaps` and dozens more that this diff never touches. Empirically the blast radius was zero — the full suite moved only by the count of tests added, at every one of the three commits.
- The index remains stale (`c4f6e7d` vs HEAD). Re-running `npx gitnexus analyze` is left to the phase orchestrator, since re-indexing mid-plan would invalidate the impact readings quoted above.

## Test Results

| Gate | Result |
|---|---|
| Baseline (plan entry, post-24-03) | 2017 passed, 1 skipped, 2 deselected |
| Full suite before `6a6b338` | **2038 passed**, 1 skipped, 2 deselected (48:06) |
| Full suite before `7b44bb0` | **2051 passed**, 1 skipped, 2 deselected (47:12) |
| Full suite before `805a6a9` | **2053 passed**, 1 skipped, 2 deselected (48:24) |
| `tests/test_four_set_coverage.py` + `tests/test_phase23_acceptance.py` | 28 passed, 1 skipped (14:39) |
| `tests/test_fusion.py` alone | 172 → 187 passed |

Net: **+36 tests, 0 regressions.** 2017 + 36 = 2053, and the 36 is exactly the number of `def test_` in the three 24-04 sections — the four converted tests changed in place and added no count. The 1 skip is pre-existing; the 2 deselected are the paid golden tests, never run.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | No `-m golden`, no `accuracy_gate.sh`, no `vision_only_benchmark.py`, no `golden_convergence.py`, `ANTHROPIC_API_KEY` never referenced, `.env` never read. `score_report_dir.py` reads a saved artifact and makes no call. The two `golden` grep hits in the new tests are prose explaining why a golden figure is NOT asserted. |
| Offline gate green | 2053 passed / 1 skipped / 2 deselected, up from the 2017 baseline by exactly the 36 tests added. |
| `test_phase23_acceptance.py` + `test_four_set_coverage.py` green | Run together (28 passed, 1 skipped) and inside every full-suite run. |
| `fusion_rejected` not overloaded | `grep -c` **16 before → 15 after** (it decreased: one docstring mention was reworded to "the rejection list"). Asserted by `test_unnamed_geometry_the_rejection_audit_list_is_untouched`. |
| `coverage_ledger` untouched | No coverage file in any of the three diffs. |
| The 56 / 136 / 28 / 132 never adjusted | `grep -Ec '== *28\b\|== *132\b\|== *136\b\|== *56\b'` over the three 24-04 sections → **0**. `SYM-1` (136) and `SYM-2` (56) are ledgered with their counts exactly as measured; the one place a count is compared, it is read off the fixture rather than restated as a literal. |
| No golden SF asserted | `grep -A30 'def test_name_plausibility' \| grep -Ec '279\.5\|396059\|396053'` → **0**. Both Crow targets are asserted by SHAPE — a bare digit is refused, a long token run is refused. |
| Paid-run evidence untouched | `git status --porcelain .planning/paid-run-evidence/ \| wc -l` → **0**, checked before every commit. Every read was read-only. |
| `uploads/`, `human_inputs/`, `reports/`, `.env` untouched | `git status --porcelain` over all four → **0**. Not in any commit. |
| No new packages | `git diff HEAD~3 --stat requirements.txt setup.py pyproject.toml \| wc -l` → **0**. |
| Python 3.9 | `python3 --version` → 3.9.6; `Dict`/`List`/`Optional`/`Tuple` from `typing`, no 3.10+ syntax. |
| No `--no-verify` | All three commits ran hooks normally on the main working tree. |
| GitNexus before editing fusion symbols | `impact` run on all four targets and HIGH risk warned; `detect-changes` before each commit, with the HIGH reading recorded. |
| Re-score recorded, not acted on | 30%, exit 0, stated above with the reason it cannot have moved. |

## Issues Encountered

- **The plan's `NAME_SOURCE_SCHEDULE_ROW` would have been a dead entry.** The literal string in the plan is `schedule_row`; `_fuse_schedules` has always emitted `schedule_table`. Declared as the string the module actually produces — a closed set whose members nothing emits is a set nobody can check.
- **The `_is_noise_cluster` gate on room labels rejects nearly every non-empty Crow and Moxy room label**, because those labels are room numbers (`101`, `102`, `4`) and wall-type codes (`W3`, `S6`), not names. That is not the gate being too strict; it is the honest finding that these plan-body faces carry no room name at all. The SF of every one of them is in the ledger. Making rooms nameable is Phase 25's.
- **Naming a symbol group from a *loose nearest word* remains the weakest rung** even after the noise gate. On Crow page 0 exactly one group survives it, named `DOOR`. That is a low yield and it is reported rather than tuned: widening what counts as a name is how a coincidence becomes a line item.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

**Unblocks 24-06 directly.** `result["unnamed_geometry"]` is a list of JSON-serialisable dicts, one per candidate, each carrying `candidate_id`, `kind`, `quantity`, `unit`, `position_pt`, `evidence_texts`, `reason` and `detail`. 24-06 surfaces it — a report key, a `summary.txt` section, an Excel sheet. **Every field a reviewer needs is already there; 24-06 should not need to reopen `fusion.py`.** Note that `merge_with_provenance` does **not** yet carry the key across sheets — that is 24-06's first job, and its absence is why this plan asserts the ledger per sheet.

**For 24-07 (SoM chip + the wall-reference schema):** the orphan-room branch is live and reads `ROOM_WALL_REFERENCE_FIELD` (`"bounding_wall_ids"`). 24-07 has exactly one thing to do — populate it on the room record. The moment it does, the branch begins refusing rooms that cite no wall, so 24-07 must populate it for the rooms that genuinely have walls in the same change, not after. `test_orphan_room_an_absent_wall_reference_is_not_read_as_an_absent_wall` pins the handoff.

**For 24-05 (vocabulary persistence):** a ledgered candidate has no name and therefore nothing to persist. The ledger is the correct place to look for what the project could not name — and, per 24-03's note, `_HYPOTHESIS_NAME_SOURCES` already excludes `vision`, so removing these rows changed no cross-reference assertion.

**For 24-10 (the phase gate):** two structural, free claims are now assertable across a whole run — no published row's name equals its own `candidate_id`, and every candidate is either published or ledgered exactly once. The second is the stronger one, and it is the one that catches a future "fix" that deletes rather than relocates.

**Honest expectations to carry into verification:**
- **Crow page 0 publishes 3 components where it published 45.** That is the intended shape change, it is recorded here in advance rather than discovered at review, and reversing it by relaxing the gate is forbidden by the plan's own success criteria.
- **The ledger is legitimately larger than the number of take-off rows lost** — 42 on page 0 against 27 identifier rows in the shipped report — because merging and deduplication run downstream of `fuse_sheet`. One record per measured candidate is what a reviewer needs.
- **No accuracy claim is made or measurable here.** The one score recorded is a re-score of a static saved artifact and cannot reflect this commit.

## Self-Check: PASSED

All claimed files exist on disk (`src/bobbytailor/vision/fusion.py`, `src/bobbytailor/pipeline/takeoff_pipeline.py`, `tests/test_fusion.py`, `tests/test_naming_conventions.py`, `tests/test_symbol_binding.py`, `tests/test_symbol_identification.py`, `.planning/ROADMAP.md`, this SUMMARY). All three claimed commits resolve in `git log` (`6a6b338`, `7b44bb0`, `805a6a9`). `.planning/paid-run-evidence/` is untouched (0 porcelain entries), as are `uploads/`, `human_inputs/` and `reports/`.

---
*Phase: 24-binding-determinism-text-anchored-labeling*
*Completed: 2026-08-05*
