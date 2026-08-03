---
phase: 23-measurement-engine-completion
plan: 05
subsystem: deterministic/tag_pairing + finish_tags + room_tags
tags: [SP-6, tag-pairing, rotation, finish-tags, room-census, fail-closed, INV-05, unit-multiplier]
status: complete

requires:
  - phase: 23-01
    provides: "the honest-failure vocabulary this plan's refusal path is shaped to fit; no code dependency, the modules are pure extractors"
provides:
  - "tag_pairing.project_bbox — one bbox-into-reading-frame rotation for all four cardinal text directions, with a SIGNED perpendicular axis so it advances the way the drawing stacks text lines"
  - "tag_pairing.pair_two_token_tags(..., axis=ALONG|ACROSS) — the one adjacency rule, serving reading-order tags (WC + 07) and next-line tags (room name over room number)"
  - "tag_pairing.TagLine / page_tag_lines / normalise_text / union_bbox / bbox_inside_any"
  - "tag_pairing.sheet_mask_rects / schedule_bboxes_by_page / MASKED_VIEWPORT_KINDS — the shared schedule + title-block + legend masks"
  - "tag_pairing.MAX_GAP_PT 16.0 / PERP_TOL_PT 3.0 — pinned from measured layouts, each with its observed value and geometric margin"
  - "finish_tags.MaterialTag / extract_material_tags / extract_material_tags_for_doc / code_set / FINISH_PREFIXES"
  - "room_tags.RoomTag / RoomMix / extract_room_tags / census_room_tags / derive_room_mix — the fail-closed unit-mix census"
affects:
  - "23-08 (room-mix census wiring + finish-tag flagged rows) — consumes derive_room_mix and extract_material_tags; owns the page scoping and the _manifest_room_mix docstring correction"
  - "23-14 (elevation facade measurement, keynote attribution) — the third consumer of pair_two_token_tags; must not grow a fourth copy"
  - "23-16 (correct the record) — owns the docs/PIPELINE-GROUND-TRUTH.md BLOCKER A correction this plan supplies the evidence for"

tech-stack:
  added: []
  patterns:
    - "measure adjacency in the TEXT's own reading frame, never in page x/y — a rotated tag and an unrotated tag are then the same measurement"
    - "the perpendicular axis must be SIGNED, not just swapped: without the negations on (-1,0) and (0,1), 'the next line' silently becomes 'the previous line'"
    - "two tokens can be adjacent along the reading axis OR across it; both are one projection with the two axes exchanged, not two rules"
    - "pin a threshold to an OBSERVED geometry with its margin stated, never to a quantity — and record the reason it is not wider"
    - "validate a detector by SET membership, not by count, when the thing counted is a callout instance rather than a region"
    - "a refusal must be distinguishable from an absence — same empty mapping, different flag"
    - "bound a pair scan with a spatial bucket rather than assuming document order"
    - "mask by CONTAINMENT, not intersection: a mask edge must not delete a plan-body callout it merely clips"

key-files:
  created:
    - src/bobbytailor/deterministic/tag_pairing.py
    - src/bobbytailor/deterministic/finish_tags.py
    - src/bobbytailor/deterministic/room_tags.py
    - tests/test_tag_pairing.py
    - tests/test_finish_tags.py
    - tests/test_room_tags.py
  modified: []

key-decisions:
  - "A ROOM TAG pairs ACROSS the reading axis, not along it. INV-05 §2 Key B says 'name to the left of the number', which is true on the page but is the NEXT TEXT LINE in the rotated text's own frame — the along-axis gap is −22.5 pt, i.e. negative. pair_two_token_tags therefore takes an axis selector. This is a generalisation of the one projection, not a second copy, and a test asserts neither consumer defines its own project_bbox or pair_two_token_tags."
  - "project_bbox NEGATES the perpendicular range for dir=(-1,0) and dir=(0,1). Swapping the axes alone is enough for the ALONG case but makes the ACROSS case read the previous line as the next one on two of the four directions. Signing it makes the projection a true rotation into (reading, advance)."
  - "MAX_GAP_PT is 16.0, and the comment records that the observed intra-tag gap runs 10.5–14.4 pt across all six Moxy elevation sheets — an 11% margin, not the ~50% the plan's prose assumed. Measured, not transcribed."
  - "The room tag's ACROSS gap is a SEPARATE constant (6.0 pt) because it measures a different axis, not because the 16.0 pt one was relaxed. Observed 1.12–3.57 pt; 6.0 is under half the 11.7 pt line extent."
  - "derive_room_mix takes an explicit `pages` argument and its whole-document default REFUSES on Moxy. Deciding which sheet is a unit key plan is sheet classification, not tag reading, so the scoping belongs to 23-08. The refusal is the honest answer for a function that cannot tell a repeat from a re-use."
  - "The census counts 214 tags on the key plans, not INV-05's 217. Re-measured, never transcribed (the discipline 23-04 established). The three-tag difference is multi-line room names, and it does not touch any of the four golden multipliers."
  - "Real-PDF tests pass viewport masks but not the whole-document schedule scan, because Moxy's only schedule table is on page index 6 and `extract_schedules` over 40 pages costs 146 s. The one test that needs that bbox transcribes it, with a comment saying detection is test_schedule_extraction's job."
  - "Synthetic pages are built as text DICTS, not by writing a PDF. PyMuPDF's insert_text merges two same-baseline tokens into one line ('WC 07'), which is not the shape a CAD set produces. The stub geometry is the MEASURED Moxy tag translated, so the synthetic case is the real case with the position freed."
  - "No WC area is produced, anywhere. INV-05 §3 proved every seeded fill at a WC tag leaks to the clip edge at 4–10x. The 7,432.05 SF figure appears in no module and in no test in this plan."

requirements-completed: []
requirements-advanced: [V4-MEAS-04]

coverage:
  - id: T1
    description: "A two-token tag is read along the text line's own reading direction, so a rotated and an unrotated tag both resolve"
    requirement: V4-MEAS-04
    verification:
      - kind: unit
        ref: "tests/test_tag_pairing.py::test_a_prefix_and_number_pair_in_every_orientation (4 directions) + ::test_all_four_orientations_resolve_in_ONE_call"
        status: pass
      - kind: unit
        ref: "tests/test_tag_pairing.py::test_both_real_moxy_layouts_pair_through_the_same_code_path — INV-05 §2 Key A bboxes verbatim"
        status: pass
      - kind: integration
        ref: "tests/test_finish_tags.py::test_page_18_is_non_empty_the_rotation_regression — real PDF, asserts dir=(0,-1) on p15 and dir=(1,0) on p18"
        status: pass
    human_judgment: false
  - id: T2
    description: "The exact set of wall-covering codes on each interior-elevation sheet is recovered, including the sheet that genuinely has none"
    requirement: V4-MEAS-04
    verification:
      - kind: integration
        ref: "tests/test_finish_tags.py::test_moxy_elevation_sheet_wall_covering_set_is_exact — real PDF, 6 parametrised sheets, SET equality"
        status: pass
      - kind: integration
        ref: "tests/test_finish_tags.py::test_the_true_negative_sheet_is_a_negative_and_not_a_failure — p17 WC empty AND other codes present"
        status: pass
      - kind: integration
        ref: "tests/test_finish_tags.py::test_the_guestroom_prototype_sheets_carry_no_material_tags — pages 23/26/31 empty"
        status: pass
    human_judgment: false
  - id: T3
    description: "Room name and room number pair on the unit key plans, yielding a census with no duplicate room numbers"
    requirement: V4-MEAS-04
    verification:
      - kind: integration
        ref: "tests/test_room_tags.py::test_moxy_key_plan_census_has_no_duplicate_room_numbers — 214 tags / 214 distinct / 0 dups"
        status: pass
      - kind: integration
        ref: "tests/test_room_tags.py::test_moxy_unit_multipliers_are_recovered_from_the_drawings — QQ A 90, KING A 26, K SUITE B 2, BUNK B 1"
        status: pass
      - kind: unit
        ref: "tests/test_room_tags.py::test_a_duplicated_room_number_refuses_rather_than_counting_partially"
        status: pass
      - kind: integration
        ref: "tests/test_room_tags.py::test_the_whole_document_refuses_because_sheets_genuinely_repeat_rooms — the fail-closed path on real data"
        status: pass
    human_judgment: false
  - id: T4
    description: "One projection helper serves finish tags, room tags and keynote pairing — there is not a second copy"
    requirement: V4-MEAS-04
    verification:
      - kind: unit
        ref: "tests/test_room_tags.py::test_no_consumer_grows_its_own_copy_of_the_projection — source inspection plus object identity"
        status: pass
    human_judgment: false
  - id: T5
    description: "Tags inside a schedule bbox or a title-block / legend viewport are masked out before pairing"
    requirement: V4-MEAS-04
    verification:
      - kind: unit
        ref: "tests/test_finish_tags.py::test_a_tag_inside_a_mask_rectangle_is_not_a_plan_body_callout + ::test_a_mask_that_merely_clips_a_tag_does_not_delete_it"
        status: pass
      - kind: integration
        ref: "tests/test_room_tags.py::test_the_door_schedule_sheet_holds_no_rooms_once_its_table_is_masked — real PDF, two invented rooms removed"
        status: pass
    human_judgment: false

metrics:
  duration: ~2h20m
  completed: 2026-08-03
  tasks: 3
  commits: 3
  tests_added: 67
  suite: "1465 passed, 2 deselected (baseline 1398)"
---

# Phase 23 Plan 05: Tag-Pairing Primitives Summary

**The gap this plan was written against does not exist, and that is the deliverable. There is no
finish schedule in the Moxy input to bind — CS-03 is indexed on page 1 and is not in the PDF, and
`kind="finish"` fires zero times on all four real plan sets, re-verified this run. What the drawing
does print is the two-token tag, and one direction-generic reader of it recovers the exact
wall-covering code SET on six of six interior-elevation sheets including the true negative, and
recovers the unit multiplier the pipeline's own docstring says "no reading of the plan can recover"
— 4 of 4 exact.**

## Performance

- **Duration:** ~2h20m
- **Tasks:** 3 of 3 (3 commits, one per task)
- **Files created:** 6 (3 modules, 3 test files) — 1,862 insertions, 0 deletions, 0 files modified

## The result, measured through the modules' own harnesses (zero API)

`python3 -m bobbytailor.deterministic.finish_tags "uploads/Moxy …-Plans.pdf"`:

| Sheet | Recovered WC set | Estimator's own Legend box (INV-05 §2 Key A) | |
|---|---|---|---|
| p15 (ID-200) | `WC-1, WC-2` | `WC-1, WC-2` | EXACT |
| p16 (ID-201) | `WC-1, WC-2, WC-4, WC-7` | `WC-1, WC-2, WC-4, WC-7` | EXACT |
| p17 (ID-202) | *(empty)* | *(empty — guard rail measured instead)* | EXACT |
| p18 (ID-203) | `WC-6, WC-7` | `WC-6, WC-7` | EXACT |
| p19 (ID-204) | `WC-9, WC-10` | `WC-9, WC-10` | EXACT |
| p20 (ID-205) | `WC-8` | `WC-8` | EXACT |

Pages 15–17 draw the tag rotated (`dir=(0,-1)`); pages 18–20 draw it unrotated (`dir=(1,0)`). Both
resolve through the one projection. The reader also recovers `PT/WD/AT/T/ST/RB` codes for free —
the whole public-space finish vocabulary — and returns `[]` on the three guestroom prototype sheets.

`python3 -m bobbytailor.deterministic.room_tags "uploads/Moxy …-Plans.pdf" --pages=7,8`:

```
tags=214  distinct numbers=214  duplicates=0
  qq a 90    king a 26    king b 15   qq c 15    hskp 6    lobby 6   qq b 6
  k suite a 5   king c 5   stair 1 5   ...   k suite b 2   bunk b 1
```

Against `docs/PIPELINE-GROUND-TRUTH.md`'s golden multipliers — ID-413 QQ A **90**, ID-407 KING A
**26**, ID-411 KING SUITE B **2**, ID-417 BUNK B **1** — that is **4 of 4 exact**. Nothing was tuned
toward it: the pairing rule is the set's own printed `ROOM TAG / ROOM NAME / ROOM NUMBER` legend,
and the comparison was made after the extraction.

## What shipped

**`tag_pairing.project_bbox` — the rotation, once.** It maps a bounding box into the text line's own
`(reading, advance)` frame for all four cardinal directions. The advance axis is **signed**, not
merely swapped: without the negations on `dir=(-1,0)` and `dir=(0,1)`, "the next line" silently
becomes "the previous line" on half the directions, which is precisely the class of bug that made a
first-pass reader return nothing on Moxy pages 18–20.

**`pair_two_token_tags(..., axis=ALONG|ACROSS)` — one adjacency rule, two axes.** A material tag's
number follows its prefix in reading order; a room tag's number sits on the next text line. Those
are the same measurement with the two axes exchanged, so they are one function. A pair is admitted
only when both lines share a direction, the gap is non-negative and under the maximum, the other
axis overlaps within tolerance, and neither line is already spoken for. Nearest-wins, ties broken by
document order, so the result is deterministic — asserted.

**The constants are pinned to geometry and say why they are not wider.** `MAX_GAP_PT = 16.0` against
an observed 10.5–14.4 pt across all six elevation sheets; the comment records that the registry holds
one- and two-letter codes and that drawings are dense with stray two-digit numbers, so every extra
point manufactures a code that was never printed. `PERP_TOL_PT = 3.0` is below a third of the
smallest observed token extent, which is the geometric reason a neighbouring text row cannot reach.

**The scan is bounded, not quadratic.** Candidates are indexed by `(direction, overlap-axis bucket)`
and each first token examines three buckets. Threat T-23-19 is pinned by a 4,000-line test that piles
every line into a handful of buckets and still completes. Bucketing also means the rule makes no
assumption about document order — it is spatial, which is what the drawing actually is.

**`finish_tags` reports a printed callout and cannot report an area.** INV-05 §3 seeded a flood fill
at every WC tag and every fill leaked to the clip edge at four to ten times the estimator's figure,
because an elevation's wall face is bounded above and below but open laterally — it is not a closed
ink region. The 7,432.05 SF that the five WC legends sum to appears in **no module and no test in
this plan**, and no code path here can produce a square foot.

**`room_tags.derive_room_mix` fails closed.** A duplicated room number means the censused sheets
overlap and the count would be inflated, so it returns an empty mapping plus a flag naming the
duplicates — never a partial census. A wrong multiplier is not a wrong line item; it multiplies Gyp
Ceiling, Gyp Wall, Guestroom-Wall Covering and Doors at once. An empty mapping with `refused=False`
(a set with no room tags) stays distinguishable from one with `refused=True` (threat T-23-20).

**Masks by containment, not intersection.** A mask that merely clips a plan-body callout must not
delete it, but a tag drawn *inside* a schedule table is not a plan-body callout at all. On Moxy's
door-schedule sheet the unmasked reader invents two rooms — `LEVEL 01 LOWER / 003` and
`LEVEL 07 / 715` — and supplying the schedule's own bbox removes them.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1465 passed, 2 deselected** (baseline 1398) |
| Four-set gate `tests/test_four_set_coverage.py` | green — **9 passed**, unchanged |
| Plan-scope files (`test_tag_pairing` / `test_finish_tags` / `test_room_tags`) | **67 passed** (28 / 20 / 19) |
| Moxy finish-tag harness | WC set EXACT on 6 of 6 elevation sheets, including the p17 true negative |
| Moxy rotation regression | p15 tags all `dir=(0,-1)`; p18 tags all `dir=(1,0)`; both non-empty |
| Moxy guestroom sheets 23 / 26 / 31 | `[]` on all three |
| Moxy room-tag harness, pages 7+8 | 214 tags / 214 distinct numbers / 0 duplicates |
| Moxy unit multipliers | QQ A 90, KING A 26, K SUITE B 2, BUNK B 1 — **4 of 4** vs golden |
| Moxy whole-document census | **REFUSED**, 18 duplicated numbers named — the fail-closed path on real data |
| INV-05 §6 item 1 regression guard | **PASS** — `finish=0` on Moxy, Crow, Bob's and Chelsea (kinds: door / door / door+keynote / none) |
| `ast.parse(..., feature_version=(3,9))` on all three modules | `py39 ok` |
| `gitnexus detect-changes` | run before each of the three commits — 0 affected processes, risk **low** (three new modules, no existing symbol touched) |

**No paid command was run.** `pytest -m golden`, `scripts/accuracy_gate.sh`,
`scripts/vision_only_benchmark.py` and `scripts/golden_convergence.py` were not executed and are
required by no step above. `.env` was not read.

### Impact analysis (CLAUDE.md), run before editing

All three files are **new modules importing no existing symbol's behaviour**, so no existing symbol
was modified and `detect-changes` reported **0 affected processes / risk low** before each commit.
The only functions reached outward are `viewports.segment_viewports` and `tables.extract_schedules`,
both called read-only through lazy imports inside `tag_pairing.sheet_mask_rects` /
`schedule_bboxes_by_page`, and both already exercised by their own suites. Nothing imports these
three modules yet — wiring is 23-08 — so the blast radius of this plan is zero by construction.

## Deviations from Plan

### 1. [Rule 1 — bug in the plan's premise] A room tag pairs ACROSS the reading axis, not along it

- **Found during:** Task 3, first probe of Moxy pages 7 and 8, which returned **0 pairs**.
- **Issue:** the plan (following INV-05 §2 Key B, *"rotated text, name to the left of the number"*)
  specifies room tags through the same ALONG-axis adjacency as material tags. That is true of the
  page coordinates and false of the reading frame. Measured::

      'KING A' (625.0, 1336.0, 636.7, 1369.4) dir=(0,-1)
      '204'    (637.9, 1346.7, 649.6, 1358.5) dir=(0,-1)

  Projected onto the reading axis the gap is **−22.5 pt** — the number is not after the name at all.
  It is the **next text line**: a room tag prints the name over the number, and on a rotated sheet
  "over" is +x on the page.
- **Fix:** `pair_two_token_tags` gained an `axis` selector, and `project_bbox` gained the sign on its
  perpendicular range so ACROSS is direction-generic too. This is a generalisation of the single
  helper — it is emphatically **not** a second copy, and
  `test_no_consumer_grows_its_own_copy_of_the_projection` asserts by source inspection *and* object
  identity that neither consumer defines its own.
- **Commits:** `b97ba1c` (the axis), `51f4cda` (the consumer)

### 2. [Rule 2 — missing critical functionality] `derive_room_mix` needs a page scope, and its default must refuse

- **Found during:** Task 3, whole-document census.
- **Issue:** the plan asks for a whole-document census with a fail-closed uniqueness gate, and
  asserts 217 tags / 217 distinct / 0 duplicates. Both cannot hold: Moxy's whole document yields
  **275 tags / 237 distinct / 18 duplicated numbers**, because pages 9–13, 21 and 26 draw the same
  rooms again on floor and enlarged plans. The plan's own assertion is the *key-plan* scope.
- **Fix:** `derive_room_mix(doc, pages=None, mask_rects_by_page=None)`. The uniqueness gate is
  implemented exactly as specified — any duplicate refuses, no partial fallback. The whole-document
  default therefore **refuses on Moxy**, which is the correct answer for a function that cannot
  distinguish a repeat from a re-use, and page scoping is left to 23-08 because deciding which sheet
  is a unit key plan is sheet classification, not tag reading.
- **Why this is better than deduping:** counting a number once when it appears twice would silently
  halve a set drawn with per-floor key plans — INV-05 risk 4 exactly. The refusal is pinned on real
  data by `test_the_whole_document_refuses_because_sheets_genuinely_repeat_rooms`, which is a
  stronger test than the synthetic one the plan asked for (both are present).
- **Commit:** `51f4cda`

### 3. [Rule 3 — blocking] `insert_text` cannot build a synthetic two-token tag

- **Found during:** Task 2, the masking tests.
- **Issue:** PyMuPDF merges two same-baseline tokens into a single text line — `'WC 07'` — at every
  offset tried, including a 3 pt baseline shift and a font-size change. A synthetic PDF therefore
  cannot express the shape a CAD set produces, and the masking tests failed on a fixture defect
  rather than on the code.
- **Fix:** synthetic pages are built as text **dicts** through a minimal stub exposing only
  `get_text("dict")`, using the **measured** Moxy tag geometry translated to the test position. The
  synthetic case is the real case with the position freed, and the reason is recorded in the fixture
  docstring so the next reader does not retry `insert_text`.
- **Commit:** `5a9e2e3`

### 4. [Decision] The measured census is 214 tags, not INV-05's 217

Re-measured rather than transcribed, which is the discipline 23-04 established after INV-07's
prototype numbers failed to reproduce. The three-tag difference is **multi-line room names**: Moxy
prints `KING` / `ADA (RIS)` / `202` as three lines, and the reader pairs the line immediately
adjacent to the number, so that tag's name reads `ADA (RIS)` rather than `KING ADA (RIS)`. Joining
preceding name lines is a real refinement and it touches **none** of the four golden multipliers,
every one of which is a single-line name. Recorded, not chased — chasing 217 would be tuning to a
throwaway probe's figure.

### 5. [Decision] The room tag's gap constant is separate from the material tag's

`ROOM_TAG_MAX_GAP_PT = 6.0` sits beside `MAX_GAP_PT = 16.0`. They are not two tunings of one
threshold: they measure **different axes**. The room-tag constant is pinned to an observed 1.12–3.57
pt advance gap and is under half the 11.7 pt line extent. Stated explicitly in the module because a
future reader seeing two gap constants will otherwise assume one was relaxed.

### 6. [Scope boundary — logged, NOT fixed] Two residuals

- Moxy page index 6 still yields one tag, `TAG` + `G1`, from the door schedule's own header band
  above the table bbox. It is a legend column heading, it is on a sheet that holds no rooms, and its
  number is not duplicated so it changes no census outcome. Excluding it would need a header word
  list, which is our vocabulary rather than the drawing's — the exact move
  `test_prose_is_kept_out_by_length_not_by_a_word_list` exists to prevent.
- Multi-line room names (deviation 4). Both are recorded here rather than in
  `deferred-items.md` because neither blocks 23-08 and both live inside this plan's own modules.

---

**Total deviations:** 3 auto-fixed (1× Rule 1, 1× Rule 2, 1× Rule 3), 2 decisions recorded, 2 logged
and not fixed.

## Issues Encountered

**The plan's headline premise had to be reported rather than implemented.** The objective is
"finish-schedule → room binding", and there is no finish schedule. The regression guard was re-run
this session across all four real sets and `kind="finish"` fired zero times on every one of them
(Moxy `door`, Crow `door`, Bob's `door` + `keynote`, Chelsea nothing). The plan anticipated this and
scoped the work to the primitive; the SUMMARY records it because the requirement text still says
otherwise.

**Masking is expensive at document scale.** `tables.extract_schedules` over Moxy's 40 pages costs
**146 s** — it runs `find_tables` on every sheet. The per-page viewport mask is cheap (0.02–1.34 s).
Real-PDF tests therefore supply viewport masks and transcribe the single door-schedule bbox where it
is needed, with the reason in the constant's comment. `extract_material_tags_for_doc` still does the
full computation for the harness and for 23-08.

## Known Stubs

None. All three modules are exercised against the real Moxy PDF, and every threshold is pinned by a
test that fails if it moves.

**Nothing is wired.** These are pure extractors by the plan's design: no pipeline import, no fusion
import, no bundle key, and no consumer yet. That is 23-08's scope, and it is a deliberate boundary
rather than an omission — the same position 23-04 left `door_schedule_coverage` in for 23-17.

## Threat Flags

None — no new network, auth, filesystem or schema surface. The modules read a PDF the project was
already reading, and write nothing.

Registered mitigations, all delivered:

- **T-23-17 (a stray number manufacturing a finish code)** — mitigated by the 16 pt gap, the
  perpendicular-overlap requirement and the schedule / legend masks. Pinned by the exact per-sheet
  SET assertions, by the empty set on three guestroom sheets, and by
  `test_a_stray_number_beyond_the_gap_does_not_manufacture_a_code`.
- **T-23-18 (a duplicated room number doubling a unit count)** — mitigated by the fail-closed
  uniqueness gate. Pinned by the synthetic duplicate test *and* by the real-PDF whole-document
  refusal.
- **T-23-19 (quadratic pairing on a dense page)** — mitigated by the `(direction, bucket)` spatial
  index. Pinned by a 4,000-line adversarial test that piles every line into a handful of buckets.
- **T-23-20 (a refusal indistinguishable from an absence)** — mitigated by `RoomMix.refused` plus
  `duplicate_numbers` and `reason`. Pinned by
  `test_a_refusal_is_distinguishable_from_a_set_with_no_room_tags`.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `b97ba1c` | One projection helper reads a tag in every text orientation |
| 2 | `5a9e2e3` | Read the finish code the drawing prints, since the schedule is absent |
| 3 | `51f4cda` | The unit multiplier IS in the drawings, and the census refuses when it is not |

## Requirement status

`V4-MEAS-04` is **advanced, not completed** — left unchecked in `REQUIREMENTS.md`, exactly as 23-02,
23-03 and 23-04 did with theirs.

The requirement reads *"Finish-schedule → room binding (WC-1…WC-10 assigned to the rooms carrying
those finishes)"*. Three things stand between that sentence and a tick:

1. There is **no finish schedule** in the input, so the binding as written cannot be built. The
   requirement's premise is disproved, and 23-16 owns correcting the record.
2. The tags are recovered but **nothing consumes them** — no line item, no report row. 23-08 owns
   the wiring.
3. WC-1…WC-10 have **no area**, and must not be given one. The correct end state is a named,
   flagged, zero-quantity row routed to the human measure workspace, which is again 23-08.

Ticking the box now would claim a client-visible guarantee no client can see — the precise failure
mode this phase exists to abolish.

## What this unblocks

23-08 can wire the room-mix census and the finish-tag rows without building anything new: it needs
`derive_room_mix(doc, pages=…)`, `extract_material_tags(page, mask_rects)`, and a decision about which
sheets are unit key plans. 23-14 gets its keynote pairing for the cost of two predicates.

**The standing caution applies.** Recovering the multiplier does **not** make Moxy's numbers correct
— it removes the largest human input from the path and, per 23-CONTEXT decision 3, the census
supersedes the manifest while the manifest is retained as a cross-check that FLAGS disagreement.
Correcting `human_inputs/moxy_knoxville.json` is out of scope for this phase. And recovering the WC
code set does **not** recover 7,432 SF: the area is not in the drawing in any form a fill can find,
and the honest output is a flagged zero-quantity row a human closes in seconds, not a number.

## Self-Check: PASSED

- `src/bobbytailor/deterministic/tag_pairing.py` — FOUND
- `src/bobbytailor/deterministic/finish_tags.py` — FOUND
- `src/bobbytailor/deterministic/room_tags.py` — FOUND
- `tests/test_tag_pairing.py` — FOUND
- `tests/test_finish_tags.py` — FOUND
- `tests/test_room_tags.py` — FOUND
- commit `b97ba1c` (Task 1) — FOUND
- commit `5a9e2e3` (Task 2) — FOUND
- commit `51f4cda` (Task 3) — FOUND
