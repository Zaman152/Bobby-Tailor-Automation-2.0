---
phase: 23-measurement-engine-completion
plan: 04
subsystem: deterministic/schedule_extraction + component_library + plan_deterministic_legends
tags: [door-schedule, format-agnostic, legend-guard, canonical-naming, honest-zero, INV-07, gap-7]
status: complete

requires:
  - phase: 23-01
    provides: "pipeline.coverage ItemCoverage / ITEM_NOT_MEASURED / ITEM_NEEDS_REVIEW / _compact_ranges — the vocabulary the honest-zero warning reuses instead of inventing a second flag shape"
  - phase: 23-03
    provides: "the flagged-zero contract: quantity=None means NOT MEASURED, never a count of zero"
provides:
  - "schedule_extraction._normalise_material_text / _material_code / MATERIAL_CODES — phrase-based material reading"
  - "schedule_extraction.MATERIAL_CODE_ALIAS / canonical_material_code — the ONE estimator-code definition, shared with component_library"
  - "schedule_extraction._column_roles / _resolve_columns / _count_column — column roles with a content fallback"
  - "schedule_extraction._door_title_bands / _is_door_title_line / _table_in_door_band — part 1 of the legend guard"
  - "schedule_extraction.accepted_door_tables — the per-page unit of the guard, so a negative assertion can name a page"
  - "schedule_extraction._hm_door_notes / reclassified_panel_counts — the printed-note HM reclassification, now serving BOTH formats"
  - "DoorSchedule.rows / .tables_seen / .titled_pages / .notes_text; DoorRecord.count / .comment"
  - "schedule_extraction.door_schedule_coverage / door_schedule_coverage_warnings — the honest-zero records"
  - "door_schedule_to_legend emits canonical Doors-CODE / Door Frames-CODE ITEM names"
affects:
  - "23-17 (report-side surfacing consumes door_schedule_coverage records alongside 23-03's coverage_drops / item_coverage)"
  - "aggregator.ITEM_NAME_MAP consumers — door-schedule rows now arrive as canonical codes rather than prose, so they canonicalise instead of falling into the generic Doors bucket"
  - "component_library.harvest_component_library — door quantities now come from the unified extractor on all three formats"

tech-stack:
  added: []
  patterns:
    - "read a printed value by PHRASE, not by bare-token equality: punctuation and line splits are the drawing's, not the data's"
    - "leftmost-then-longest resolution, so a compound cell resolves to its head noun (the leaf material, not the glazing)"
    - "roles are advisory, content is authoritative — and content detection runs PER MISSING ROLE, not only when every role is missing"
    - "the ABSENCE of a column is a valid answer with its own meaning (no count column = one door per row)"
    - "widening a reader and adding its guard are ONE change; either alone is a regression"
    - "a fallback between two partial readers is not robustness — it is a coin toss over which vocabulary the report speaks"
    - "the name is part of the measurement: a correct count under an unmatched name is indistinguishable from a miss"

key-files:
  created: []
  modified:
    - src/bobbytailor/deterministic/schedule_extraction.py
    - src/bobbytailor/deterministic/component_library.py
    - src/bobbytailor/deterministic/plan_deterministic_legends.py
    - tests/test_schedule_extraction.py
    - tests/test_component_library.py
    - .planning/phases/23-measurement-engine-completion/deferred-items.md

key-decisions:
  - "`_tag_column` was changed from MAX-hits to LEFT-MOST-with-3-hits. Crow's nine-integer Count column outvoted its seven type codes and BECAME the tag column, so a 105-door schedule read as five openings. INV-07 §4.1 specifies left-most; the old rule was the bug."
  - "A pure-letter TYPE code (DSF, SF) was not a tag shape at all, so no single parser could read the type+count format. Added, but capped at 2-3 letters and excluding anything the material reader can name — four letters admits WORK/DATA, one letter admits the elevation grid letters A..H that make Moxy p15's drawing grid read as a tag column."
  - "Cell-pair joining is applied ONLY when the right neighbour carries no material of its own. Joining unconditionally makes Crow's thickness column read the IM beside it and masquerade as the leftmost material column."
  - "A title band's x-range is taken from the table it DIRECTLY titles, not from the title line. A printed 'DOOR SCHEDULE' is ~80pt wide over a ~900pt table, so the >=60%-of-table-width rule can never fire on the raw line and every set read zero."
  - "Reference callouts (REF:/REFER/SEE/PER) are rejected as titles. Bob's page 5 prints two 'REF: DOOR SCHEDULE' callouts that would otherwise own bands and lend a door schedule's authority to whatever table sits beneath them."
  - "The deny-word rule was made to actually bite: a deny word is fatal unless DOOR sits ADJACENT to the schedule word. Written literally ('unless the line also names a door') it is inert, because the title regex already requires DOOR. As implemented it correctly rejects DOOR HARDWARE SCHEDULE, which is a hardware-set schedule."
  - "`_hm_door_notes` MOVED to schedule_extraction and imported back by component_library, rather than duplicated. The must-have is that both formats receive the reclassification; two copies would satisfy it today and diverge later."
  - "`ds.panel_counts` keeps the RAW printed codes and `reclassified_panel_counts` applies the note; the canonical estimator code is applied only at the legend boundary. A caller can still see what the drawing printed."
  - "Frame material for Moxy's guestroom fragment resolves to NOTHING rather than to the panel column. The INV prototype mis-typed 2-3 frames as SCW; an empty frame is the honest reading of a fragment whose frame column is genuinely empty."
  - "No Moxy multiplier was invented. `door_schedule_coverage(absent_references=...)` takes the reference as an ARGUMENT and is not wired to any Moxy-specific detection — 23-CONTEXT records that INV-07's 'the multiplier is not in the input' claim was disproved for Moxy by the in-plan unit-tag census."

requirements-completed: []
requirements-advanced: [V4-MEAS-06]

coverage:
  - id: D1
    description: "A door schedule printing its materials as free text with punctuation is read, not rejected"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_material_normalisation_and_code (5 INV-07 §4.1 rows)"
        status: pass
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_split_frame_cell_pair_resolves_to_hollow_metal"
        status: pass
      - kind: integration
        ref: "tests/test_schedule_extraction.py::test_bobs_schedule_table_is_accepted_and_read — real PDF, HM 5 / SCW 7 / frame HM 12"
        status: pass
    human_judgment: false
  - id: D2
    description: "A schedule with no count column reports one door per printed row"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_count_column_absent_on_a_bobs_shaped_table_means_one_door_per_row"
        status: pass
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_count_column_found_on_a_crow_shaped_table"
        status: pass
    human_judgment: false
  - id: D3
    description: "One parser handles the type+count, per-opening and split-cell formats"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_the_type_plus_count_parser_is_gone"
        status: pass
      - kind: integration
        ref: "real PDFs: Crow (type+count) 105 openings, Moxy (per-opening) 59, Bob's (split-cell) 19 — one extractor"
        status: pass
    human_judgment: false
  - id: D4
    description: "A door quantity is named in the canonical estimator form, so a correct count is scorable"
    requirement: V4-MEAS-06
    verification:
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_bobs_legend_item_names_are_canonical_not_prose"
        status: pass
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_moxy_emits_canonical_names_instead_of_prose"
        status: pass
      - kind: unit
        ref: "tests/test_component_library.py::test_count_doors_solid_core_wood_is_named_with_the_wood_code"
        status: pass
    human_judgment: false
  - id: D5
    description: "A plan set referencing a door schedule it does not contain reports an honest zero with a stated reason"
    requirement: V4-MEAS-06
    verification:
      - kind: integration
        ref: "tests/test_schedule_extraction.py::test_chelsea_reports_zero_with_a_stated_reason — real PDF"
        status: pass
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_coverage_records_use_the_shared_item_status_vocabulary"
        status: pass
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_a_parsable_schedule_produces_no_coverage_warning (Bob's/Crow/Moxy)"
        status: pass
    human_judgment: false
  - id: D6
    description: "An interior-elevation grid PyMuPDF reads as a table contributes zero door rows"
    requirement: V4-MEAS-06
    verification:
      - kind: integration
        ref: "tests/test_schedule_extraction.py::test_moxy_elevation_grid_page_contributes_zero_door_rows — page 15 DOES produce a band and still yields nothing"
        status: pass
      - kind: unit
        ref: "tests/test_schedule_extraction.py::test_is_door_title_line (11 cases)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Crow's note-driven hollow-metal reclassification survives the parser merge"
    requirement: V4-MEAS-06
    verification:
      - kind: integration
        ref: "tests/test_schedule_extraction.py::test_crow_note_driven_hm_reclassification_survives_the_parser_merge"
        status: pass
      - kind: integration
        ref: "tests/test_component_library.py::test_crow_door_counts_by_material — HM 29 / Frame HM 29 / STL 70 / AL 6, pre-existing, still green"
        status: pass
    human_judgment: false

metrics:
  duration: ~2h50m
  completed: 2026-08-03
  tasks: 4
  commits: 3
  tests_added: 34
  suite: "1398 passed, 2 deselected (baseline 1353)"
---

# Phase 23 Plan 04: Door-Schedule Unification Summary

**Bob's nineteen printed opening rows were already being found and then thrown away by a
material-coverage gate that could not read `HM-STL.`; Moxy's forty solid-core-wood doors were
already being counted and then scored MISSING because they were called
`Doors - Solid Core Wood (door schedule)` instead of `Doors-WD`. One parser now reads all three
real schedule formats and names every result in the canonical estimator form — Bob's goes from
zero door items to three exact ones, Moxy's count becomes scorable, Crow does not move, and
Chelsea's zero acquires a reason.**

## Performance

- **Duration:** ~2h50m
- **Tasks:** 4 of 4 (3 commits — Tasks 1+2 share one, as the plan requires)
- **Files modified:** 6 (0 created) — 1,445 insertions, 219 deletions

## The result, measured through the production legend builder

`build_deterministic_legends(pdf)` — the real entry point, zero API:

| Set | Before | After |
|---|---|---|
| **Bob's** | *no door items at all* | `Doors-HM 5`, `Doors-WD 7`, `Door Frames-HM 12`, `Doors-AL 2`, `Door Frames-AL 2` |
| **Crow** | `Doors-HM 29`, `Door Frames-HM 29`, `Doors-STL 70`, `Doors-AL 6` | **identical** |
| **Moxy** | `Doors - Solid Core Wood (door schedule) 42` (unscorable) | `Doors-WD 40`, `Door Frames-HM 40`, `Doors-GL 6`, `Doors-HM 6` |
| **Chelsea** | silent nothing | `0` openings + a warning naming page 1 |

Bob's three headline numbers — **HM 5 / WD 7 / Frame-HM 12** — are its golden values exactly. That
is a *structural* result, not a tuned one: each is the count of printed rows whose material cell
reads as that material, one row per opening. No threshold was moved toward a golden count, and the
count is a consequence of reading the column, not of choosing a cut-off. The same code, unchanged,
produces Crow's 105 openings from its Count column and Chelsea's zero.

## What shipped

**Materials are read by phrase (`_normalise_material_text` + `_material_code`).** The old reader
compared whitespace-split tokens against a set, so `HM-STL.`, `S.C. WOOD` and `ALUM. & GLASS` — the
way Bob's actually prints its materials — matched nothing, and its coverage came out at 4 of 19
against a 40% gate. Normalisation collapses dotted initialisms then strips punctuation; resolution
is **leftmost-then-longest** over a phrase list. Leftmost is load-bearing: `S.C. WOOD & GLASS` is a
solid-core wood leaf *with* a glass lite, and must resolve to the leaf.

**Column roles, with content as the authority.** `_column_roles` joins up to four stacked header
rows per column, because schedules stack two or three. Roles are advisory and content fills every
gap — and content detection runs **per missing role**, not only when every role is missing. Bob's
is the case that forces this: it finds its panel column from a `MATERIAL` header but its frame
header is split across two cells (`'FRA|LABEL|MA'`), so the frame column must still come from
content. It does: column 12, exactly as INV-07 predicted.

**Cell-pair joining, conditionally.** PyMuPDF splits Bob's frame material across two cells
(`'--- H.'` + `'M. 6A'`). Joined and normalised that reads `HM`. But joining unconditionally makes
Crow's *thickness* column read the `IM` sitting beside it and masquerade as the leftmost material
column. The join is therefore applied only when the right neighbour carries no material of its own —
i.e. only when it is a fragment rather than a column.

**The count column, whose absence is an answer.** `_count_column` takes the header role first, else
a column within three of the tag that is >=60% small integers. Returning `None` is valid and means
one door per row. That single concept is what the old `_parse_count_door_rows` lacked — it
`return None`d when no Count column existed, with no row-counting fallback, which is why it read
Crow and gave up on both per-opening formats.

**The two-part legend guard.** Widening the material reader without a guard immediately fabricates
doors: Moxy page 15 is an interior-elevation sheet whose drawing grid PyMuPDF reads as a table, and
the prototype reported a phantom `WD 4` from the word WOOD inside prose. The guard is (1) a
STANDALONE door-schedule title band whose span contains the table, and (2) column-role evidence —
two distinct material columns, or one door-role header. Page 15 still produces a band and now
contributes zero rows.

**One parser, one vocabulary.** `_parse_count_door_rows` is deleted; `extract_door_component_counts`
delegates to the unified extractor; `build_deterministic_legends` makes one call instead of trying
two paths in order. `_hm_door_notes` moved into `schedule_extraction` so both formats receive the
plan's own printed `HOLLOW METAL DOOR` reclassification, and `MATERIAL_CODE_ALIAS` is now a single
definition imported by `component_library`.

**The name is part of the measurement.** `door_schedule_to_legend` emits `Doors-<CODE>` /
`Door Frames-<CODE>` in ITEM and keeps the prose in DESCRIPTION. `SCW` maps to `WD`, not `SC`:
`aggregator.ITEM_NAME_MAP` carries `door.*\bwd\b` and no `\bsc\b` rule at all, so `Doors-SC` matched
none of the door patterns and fell into the generic `Doors` bucket. One letter is the whole of
Moxy's zero.

**An input gap is reported as an input gap.** `door_schedule_coverage` emits an `ItemCoverage` with
`quantity=None` and a reason naming the pages when a set titles a door schedule and contains no
parsable table. The status vocabulary is imported from `pipeline.coverage`, not redefined.

## Verification

| Check | Result |
|---|---|
| `python3 -m pytest -q` | **1398 passed, 2 deselected** (baseline 1353) |
| Four-set gate `tests/test_four_set_coverage.py` | green — 9 passed, unchanged |
| Three plan-scope files (`test_schedule_extraction` / `test_component_library` / `test_plan_deterministic_legends`) | **79 passed** (baseline 41) |
| Bob's real PDF | panel HM **5**, SCW **7**; frame HM **12** |
| Crow real PDF | openings **105**; panel after note reclass **{HM 29, ALUM 6, STL 70}**; frame HM **29** |
| Moxy real PDF | pages `[7]` (page index 6); openings **59** (>= 53); items `Doors-WD` / `Door Frames-HM` |
| Moxy page index 15 | band produced, **0** accepted tables, **0** rows |
| Moxy page index 6 | **5 of 5** fragments accepted; 3 header-less continuations inherit the parent band |
| Chelsea real PDF | openings **0**, `titled_pages [1]`, **1** warning |
| `assert not hasattr(component_library,'_parse_count_door_rows')` | prints `merged` |
| Commit ordering | `ce915e0` = reader + guard together; `435b262` = parser deletion + reclassification move together |
| `gitnexus detect-changes` | run before each of the three commits |

**No paid command was run.** `pytest -m golden`, `scripts/accuracy_gate.sh`,
`scripts/vision_only_benchmark.py` and `scripts/golden_convergence.py` were not executed and are not
required by any step above.

### Impact analysis (CLAUDE.md), run before editing

| Symbol | Risk | Impacted | Processes | Mitigation |
|---|---|---|---|---|
| `extract_door_schedule` | **CRITICAL** | 16 | `_deterministic_bundle`, `extract_schedules`, `_run_sheet_vector`, `run_pdf_analysis`, `run_sheet` | Signature and return TYPE unchanged; every new `DoorSchedule` field is additive with a default. All callers reach it through `extract_door_legend_from_pdf` / `door_schedule_to_legend`. The new title-band guard is strictly MORE restrictive than the no-guard behaviour it replaces, so the change cannot widen what any caller sees. Pinned by real-PDF assertions on all four sets. |
| `build_deterministic_legends` | **HIGH** | 7 | `run_project_scrape`, `run_analyze_from_manifest`, `run_pdf_analysis` | Signature unchanged; the two-path fallback collapsed to the branch the existing tests already patch (`extract_door_legend_from_pdf`), so `test_plan_deterministic_legends.py`'s `calls == ["door"]` assertions pass untouched. |
| `door_schedule_to_legend` | LOW | 1 | 1 | — |
| `_parse_count_door_rows` | LOW | 1 | 1 | Deleted; its only caller was rewritten in the same commit. |

**The CRITICAL rating on `extract_door_schedule` was reported before editing, as required.**

## Deviations from Plan

### 1. [Rule 1 — bug] The COUNT column was being read as the TAG column

- **Found during:** Task 1, first harness run on Crow.
- **Issue:** `_tag_column` returned the column with the MOST tag-shaped cells. Crow's Count column
  holds `2, 68, 2, 24, 2, 1, 1, 1, 4` — nine cells, all tag-shaped — against seven type codes in
  column 0. The count column won, and a 105-door schedule read as **five openings**.
- **Fix:** left-most of columns 0-3 with at least three tag rows, which is what INV-07 §4.1
  specifies. The old rule was the defect.
- **Pinned by:** `test_tag_column_is_leftmost_not_most_hits`, and Crow's `(tag_col, count_col) == (0, 1)`.
- **Commit:** `ce915e0`

### 2. [Rule 3 — blocking] A pure-letter TYPE code was not a tag shape

- **Found during:** Task 1, reconciling Crow's `ALUM 6` against the harness's `ALUM 2`.
- **Issue:** `_TAG_RE` required a digit, so `DSF` and `SF` matched nothing and their rows were not
  door rows. One parser cannot read the type+count format if two of its nine rows are invisible.
- **Fix:** added the letters-only form, **capped at 2-3 characters** and excluding anything the
  material reader can name. Four letters admits `WORK` / `AREA` / `DATA`; one letter admits the
  elevation grid letters `A..H` that make Moxy page 15's drawing grid read as a tag column; `SCW`
  and `HM` are materials, not tags. `_is_header_row` additionally keeps `TAG` (a valid 3-letter
  shape) from counting as an opening.
- **Pinned by:** `test_tag_tokens` (13 cases, including the four negatives above).
- **Commit:** `ce915e0`

### 3. [Rule 3 — blocking] A title line is far narrower than the table it titles

- **Found during:** Task 2, first harness run — **all four sets returned zero**.
- **Issue:** the plan's rule is "a band qualifies a table when it overlaps >=60% of the table's
  width". A printed `DOOR SCHEDULE` line is ~80pt wide over a ~900pt table, so that test can never
  fire on the raw line and the guard rejected everything.
- **Fix:** `_directly_titled_table` attaches each band to the nearest table below it that it
  overlaps at all, and the band adopts that table's width; the >=60% rule then governs *sibling*
  qualification, which is what makes header-less continuation fragments inherit their parent's band.
  Two widening passes, bounded.
- **Commit:** `ce915e0`

### 4. [Rule 2 — missing critical functionality] Reference callouts were owning bands

- **Found during:** Task 2 acceptance, auditing Bob's page 5 bands.
- **Issue:** Bob's prints `REF: DOOR SCHEDULE (ABOVE)` and `REF: DOOR SCHEDULE`. Both are standalone
  lines under 60 characters naming a door and a schedule, so both qualified as titles — a callout
  lending a door schedule's authority to whatever table happens to sit beneath it.
- **Fix:** `_TITLE_REFERENCE_RE` rejects lines opening with `REF`/`REFER`/`SEE`/`PER`. This is the
  same defect class as the in-note reference the plan's unit test asks about; length alone only
  catches the long form.
- **Pinned by:** `test_is_door_title_line` — `REF: DOOR SCHEDULE (ABOVE)` and `SEE DOOR SCHEDULE`
  are both False, `DOOR SCHEDULE` is True.
- **Commit:** `ce915e0`

### 5. [Decision] The deny-word rule was made to actually bite

The plan specifies "no deny word unless that same line also names a door". Written literally that is
**inert**, because the title test already requires `DOOR` on the line — the exemption always fires
and no deny word can ever reject anything. Implemented instead as: a deny word is fatal unless
`DOOR` sits **adjacent** to the schedule word. `DOOR SCHEDULE` and `WINDOW & DOOR SCHEDULE` pass;
`DOOR HARDWARE SCHEDULE` is rejected, which is correct — that is a hardware-set schedule, not a door
schedule. Recorded here because it is a deliberate departure from the literal wording.

### 6. [Decision] Moxy's guestroom frame resolves to NOTHING, not to the panel column

INV-07 risk 6 predicted ~3 mis-typed frames on Moxy because the guestroom fragment's merged header
yields no roles and the pair-join picks the panel column twice — the prototype reported
`frame={'SCW': 2, 'GLASS': 1}`, i.e. wood frames. With the conditional pair-join and role
inheritance keyed on *material* roles, that fragment's frame column resolves to an empty column
instead. An empty frame is the honest reading of a fragment whose frame column is genuinely empty;
a wood door frame that the drawing never printed is not.

### 7. [Scope boundary — logged, NOT fixed] DEF-23-05 and DEF-23-06

- **DEF-23-05:** `aggregator.ITEM_NAME_MAP` has exactly one frame rule (hollow metal), so
  `Door Frames-AL` canonicalises to `Doors-AL` and `Door Frames-STL` to the generic `Doors` — a
  frame billed as a door. Pre-existing (`component_library` already emitted `Door Frames-AL`), and
  `aggregator.py` is not in this plan's `files_modified`. Adding frame rules changes the item
  vocabulary every scored fixture matches against; that is a naming decision with its own blast
  radius.
- **DEF-23-06:** the three synthetic fixture PDFs are rewritten by every full test run (embedded
  creation timestamp), dirtying the working tree. Pre-existing; harmless here only because commits
  stage files individually.

---

**Total deviations:** 4 auto-fixed (1x Rule 1, 2x Rule 3, 1x Rule 2), 2 decisions recorded, 2 logged
and not fixed.

## Issues Encountered

**The plan's own numbers had to be re-measured, not copied.** INV-07's prototype reported Moxy
`SCW 39` / `openings 53` and Crow `pnl=5`; production reads `SCW 40` / `openings 59` and `pnl=6`.
The differences come from the conditional pair-join (which stops Crow's thickness column
masquerading as a material column) and from header-row exclusion. Every assertion in this plan was
written from a measured run against the real PDF, never transcribed from the investigation — the
plan's `openings >= 53` was already written as a floor for exactly this reason.

## Known Stubs

None. Every new function is exercised by the production path on real PDFs.

`door_schedule_coverage`'s records are **produced but not yet surfaced in a client artifact** — that
is 23-17's scope, identical to the position 23-03 left `coverage_drops` and `item_coverage` in. The
records use 23-01's `ItemCoverage` shape precisely so 23-17 has nothing new to learn.

## Threat Flags

None — no new network, auth, filesystem or schema surface. The module reads a PDF it was already
reading.

Registered mitigations, all delivered:

- **T-23-13 (a drawing grid fabricating door counts)** — mitigated by the two-part guard and pinned
  by `test_moxy_elevation_grid_page_contributes_zero_door_rows`, which asserts page 15 *does*
  produce a title band and *still* yields zero, so the test cannot pass by the band detector
  silently failing.
- **T-23-14 (loosened material reading admitting prose)** — mitigated by the phrase vocabulary with
  leftmost-then-longest resolution plus the retained 40% coverage gate; negative unit tests on
  `FLOORING LEGEND` and `PAINT COLORS`.
- **T-23-15 (a pathological table)** — mitigated: role reading is bounded to the first four header
  rows, the count scan to three columns around the tag, and column scanning to `_MAX_TABLE_COLS = 80`.
- **T-23-16 (a referenced-but-absent schedule leaving no record)** — mitigated by `titled_pages` plus
  `door_schedule_coverage`.

## Commits

| Tasks | Commit | Description |
|---|---|---|
| 1 + 2 | `ce915e0` | Phrase materials, column roles, the count column — and the two-part legend guard, in ONE commit |
| 3 | `435b262` | One parser; `_parse_count_door_rows` deleted and `_hm_door_notes` moved, in ONE commit |
| 4 | `75d6fb7` | Honest zero: an input gap is reported as an input gap |

Both load-bearing orderings are verifiable in `git log -1 --stat`: `ce915e0` touches
`schedule_extraction.py` alone (reader and guard inseparable), and `435b262` touches
`component_library.py` (the deletion) and `schedule_extraction.py` (the move) together.

## Requirement status

`V4-MEAS-06` is **advanced, not completed** — left unchecked in `REQUIREMENTS.md`, exactly as 23-02
and 23-03 did.

Its first half — *"per-format door-schedule parsing across Crow, Bob's and Moxy formats"* — is
delivered here in full, and that half was the one 23-03 recorded as untouched. But the requirement is
claimed by **six** plans in this phase (23-01, 23-03, **23-04**, 23-06, 23-16, 23-17), and its second
half — *"zero-geometry sheets emit an explicit coverage flag (blank never reported as zero)"* —
still does not reach a client artifact. `door_schedule_coverage` produces the records; **23-17** owns
surfacing them. Checking the box now would claim a client-visible guarantee that no client can yet
see, which is the precise failure mode this phase exists to abolish.

## What this unblocks

Bob's has door line items for the first time, and Moxy's door counts are finally expressed in a
vocabulary the scorer and the aggregator both speak — so the next scoring run measures whether the
*count* is right rather than whether the *name* matched. Because `component_library` and the legend
now share one extractor and one code alias, a future material only has to be added to `_MAT_PHRASES`
once.

**The standing caution applies.** Moxy remains far from its golden 213/215 and that is CORRECT: the
schedule prints 40 guestroom-type doors, and the per-unit multiplier is not in the schedule. Scaling
40 up to 213 is the documented coincidence trap (D-07 / INV-07 risk 5). Chelsea remains at zero and
that is also correct — its schedule sheet is not in the file. This plan makes three of four sets
*readable*; it does not, and must not, make the two input gaps disappear.

## Self-Check: PASSED

- `src/bobbytailor/deterministic/schedule_extraction.py` — FOUND
- `src/bobbytailor/deterministic/component_library.py` — FOUND
- `src/bobbytailor/deterministic/plan_deterministic_legends.py` — FOUND
- `tests/test_schedule_extraction.py` — FOUND
- `tests/test_component_library.py` — FOUND
- `.planning/phases/23-measurement-engine-completion/deferred-items.md` — FOUND
- commit `ce915e0` (Tasks 1+2) — FOUND
- commit `435b262` (Task 3) — FOUND
- commit `75d6fb7` (Task 4) — FOUND
