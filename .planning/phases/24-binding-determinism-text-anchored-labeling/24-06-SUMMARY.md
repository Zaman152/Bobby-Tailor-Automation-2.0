---
phase: 24-binding-determinism-text-anchored-labeling
plan: 06
subsystem: pipeline/reporter + export
tags: [ledger, unnamed-geometry, summary-txt, excel, openpyxl, telemetry, INV-08, client-artifacts]

# Dependency graph
requires:
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 04
    provides: "the `unnamed_geometry` fuse_sheet key and `unnamed_geometry_record` — one measured-but-unidentified candidate with quantity, unit, position, evidence text, machine reason and human detail"
  - phase: 23-measurement-engine-completion
    plan: 17
    provides: "the additive-or-absent convention, `_coverage_lines`' empty contract, the Coverage worksheet pattern, and the T-23-70 exact key-set parity pins this plan had to satisfy"
  - phase: 21-production-hardening
    provides: "RunSettings.to_dict() and the single ensemble_settings() reader, already constructed by both entry points"
provides:
  - "`unnamed_geometry` top-level report key — the ledger aggregated with per-record sheet attribution"
  - "`run_settings` top-level report key — the effective ensemble N, budget cap and toggles (keyword-only, None-default)"
  - "generate_report(run_settings=...) and both entry points passing it"
  - "reporter.UNNAMED_GEOMETRY_KEY + `_unnamed_geometry_lines` + `_unnamed_quantity_text`"
  - "the UNIDENTIFIED GEOMETRY section of summary.txt, immediately after COVERAGE"
  - "the Unidentified Geometry worksheet + its About row"
  - "export_takeoff_excel._write_text — drawing-derived text written as text, never as a formula"
affects: [24-07, 24-09, 24-10, 25 detection, any consumer of takeoff.json]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive-or-absent, extended to a list: a ledger key appears only when the run carried records, because the parity contract downstream is exact key-set equality and not merely 'no key renamed'"
    - "Mirror a cross-package constant by VALUE with a divergence test, rather than importing across an architectural boundary that does not exist yet"
    - "The cap bounds the page, never the account: a truncated listing states its own remainder and points at the artifact holding the rest"
    - "A recorded absence is counted apart, never summed in as a zero — INV-08 applied inside an aggregate as well as inside a cell"
    - "Untrusted text is written with an explicit cell type, and the claim is proven by inspecting the emitted XML rather than asserted"

key-files:
  created:
    - .planning/phases/24-binding-determinism-text-anchored-labeling/24-06-SUMMARY.md
  modified:
    - src/bobbytailor/pipeline/reporter.py
    - src/bobbytailor/pipeline/pdf_analyzer.py
    - src/bobbytailor/scrape/scraper.py
    - scripts/export_takeoff_excel.py
    - tests/test_reporter_accuracy.py
    - .planning/phases/24-binding-determinism-text-anchored-labeling/deferred-items.md
    - .planning/ROADMAP.md

key-decisions:
  - "The ledger key is gated on NON-EMPTINESS rather than emitted as `[]`. The plan asked for the empty list and named the check that would override it: `test_a_report_with_no_ledger_is_shaped_exactly_as_before` asserts `list(report.keys()) == PRE_23_TOP_LEVEL_KEYS`, and a key present with an empty value is not key-set equality. The parity guarantee protects two live scraper entry points and outranks the nicer phrasing."
  - "`UNNAMED_GEOMETRY_KEY` is mirrored by VALUE in reporter.py, not imported from bobbytailor.vision.fusion. pipeline.reporter takes no dependency on the vision package today and a report renderer is the wrong place to open one; a test asserts the two strings are equal so the mirror cannot rot."
  - "The breakdown groups by (kind, unit), never by kind alone. A single total across EA, LF and SF would be a number that means nothing."
  - "An unrecognised record kind renders its own raw value rather than being skipped. A renderer that silently drops a kind it has not met is the exact defect this section exists to abolish."
  - "T-24-24 is mitigated on the new sheet by forcing `data_type='s'`, and the pre-existing exposure on the Take-Off and Coverage sheets is logged rather than fixed — the plan's register scopes the threat to ledger text, and re-typing every cell on two shipped worksheets is a workbook-wide change that should be made and verified as one."
  - "`run_settings` required editing two files outside the plan's fence (pdf_analyzer, scraper). Without them the key would exist and no run would ever populate it — 23-17 deviation 1's precedent exactly."

patterns-established:
  - "Empty-contract renderer: `_unnamed_geometry_lines({}) == []` and `_unnamed_geometry_lines({'key': []}) == []`, pinned as its own test, so the section cannot start rendering a zero"
  - "Assertions read quantities off the record the producer wrote, never off a restated literal"

requirements-completed: []
# HONEST SCOPE NOTE: this plan carries `requirements: [V4-DET-01]` and does NOT tick it,
# for the same reason 24-01 and 24-04 did not. 24-01 delivered the deterministic anchor,
# 24-04 turned a missing anchor into the flag that keeps a candidate out of the take-off,
# and this plan makes that flag visible in the artifacts. 24-07 still owes the SoM marker
# chip and the prompt hint. The phase gate (24-10) verifies the whole requirement.

coverage:
  - id: D1
    description: "Every candidate the take-off could not identify is visible in summary.txt as a named section, not absent"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_summary_renders_the_unnamed_geometry_section_when_there_is"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_unnamed_section_breaks_down_by_kind_with_its_measured_quantity"
        status: pass
      - kind: other
        ref: "the section rendered from a 30-record ledger through the real renderer, pasted into this summary"
        status: pass
    human_judgment: false
  - id: D2
    description: "The same candidates appear in the Excel workbook as their own named section"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_excel_workbook_carries_an_unidentified_geometry_sheet"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_excel_unidentified_sheet_says_measurements_not_absences"
        status: pass
      - kind: integration
        ref: "real saved run VisionOnly_P23V2_Crow_20260804_181352 exported to a temp path: ['Take-Off','Coverage','Unidentified Geometry','About']"
        status: pass
    human_judgment: false
  - id: D3
    description: "A report carrying no unnamed geometry renders byte-identically to a pre-Phase-24 report — the section simply does not exist"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_a_report_with_no_unnamed_geometry_still_renders_byte_for_byte (against 23-17's captured pre-change text)"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_a_run_that_named_everything_is_shaped_exactly_as_it_was_before (exact top-level key-set equality)"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_unnamed_geometry_section_is_absent_when_there_is_nothing_to_say"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_a_run_that_named_everything_gains_no_empty_excel_worksheet"
        status: pass
      - kind: integration
        ref: "the real saved pre-24 run exports ['Take-Off','Coverage','About'] — unchanged"
        status: pass
    human_judgment: false
  - id: D4
    description: "The section states the count and the measured quantity, so a reader can tell 'we measured these and could not name them' from 'these do not exist'"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_unnamed_section_breaks_down_by_kind_with_its_measured_quantity"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_a_record_with_no_measured_quantity_is_never_rendered_as_a_zero"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_individual_listing_is_capped_but_never_silently_truncated"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_an_unrecognised_record_kind_is_still_counted_and_shown"
        status: pass
    human_judgment: false
  - id: D5
    description: "takeoff.json records the effective ensemble and budget settings the run used, so 'what N was in effect' is never unanswerable from an artifact again"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_run_settings_key_records_the_ensemble_the_run_actually_used (asserted on disk, not only in memory)"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_run_settings_key_is_absent_when_no_caller_supplied_it"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_both_entry_points_hand_the_reporter_their_run_settings"
        status: pass
    human_judgment: false
  - id: D6
    description: "The ledger is aggregated under its own key with per-record sheet attribution and never touches the rejection list (T-24-16)"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_unnamed_geometry_ledger_is_aggregated_with_its_sheet_attribution"
        status: pass
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_the_ledger_is_its_own_key_and_never_touches_the_rejection_list"
        status: pass
      - kind: other
        ref: "grep -c fusion_rejected src/bobbytailor/pipeline/reporter.py: 4 before -> 4 after"
        status: pass
    human_judgment: false
  - id: D7
    description: "Drawing-derived text in the workbook cannot be interpreted as a formula (T-24-24)"
    requirement: V4-DET-01
    verification:
      - kind: unit
        ref: "tests/test_reporter_accuracy.py#test_excel_drawing_text_beginning_with_an_equals_is_not_a_formula"
        status: pass
      - kind: other
        ref: "emitted sheet XML inspected directly: ws.append(['=1+1']) -> <f>1+1</f>; data_type='s' -> <is><t>=1+1</t></is>"
        status: pass
    human_judgment: false

# Metrics
duration: 5h 34m
completed: 2026-08-05
status: complete
---

# Phase 24 Plan 06: Ledger Surfacing Summary

**The 42 candidates Crow page 0 measured and could not name existed only in memory: 24-04 stopped
them publishing as `SYM-6` and nothing a client opens said they had been measured at all. They now
have a named section in `summary.txt`, their own worksheet in the workbook, their own top-level key
in `takeoff.json` — and the run finally records the ensemble N it actually ran under, closing
24-RESEARCH Open Question 1 for every future run.**

## Performance

- **Duration:** 5h 34m (four full 48–50 minute suites, one per commit, dominate it)
- **Tasks:** 3
- **Files modified:** 7 (0 source files created)
- **Tests added:** 24

## The defect this closes

24-04 did the hard half and said so plainly in its handoff: `result["unnamed_geometry"]` is a list
of JSON-serialisable dicts, one per candidate, *"every field a reviewer needs is already there"*.
What it could not do is make anyone see them. Until this plan, a run measured 42 candidates on Crow
page 0, published 3 components, and the other 39 vanished between `fuse_sheet` and the client.

That is the mirror image of the defect 24-04 closed, and 24-RESEARCH pitfall 3 names it: **deletion
is the shortest path to "no identifiers in the report", and it silently loses hundreds of counted
symbols.** Phase 23's INV-08 established the same rule one level up — a deletion and a zero read
identically to a client. A 36-count cluster that is measured, unnameable and unlisted reads as
*"there are no columns."*

## Accomplishments

- **Three additive surfaces, none of which exist when there is nothing to say.** A run that named
  everything it measured produces a report with the same top-level key set as before Phase 23, a
  `summary.txt` that is byte-identical to 23-17's captured pre-change text, and a workbook with the
  same two worksheets. All four are asserted, not assumed.
- **The section says in WORDS what the reader is looking at**, because INV-08's whole point is that
  a number cannot carry that meaning: *"these were MEASURED — the quantities below are real and so
  are the objects; what the drawings do not say is what they ARE"*, followed by an explicit
  statement that the exclusion is deliberate and *"an absence of a NAME, never of an object."*
- **`run_settings` closes Open Question 1 permanently.** Neither saved paid run records the N that
  was in effect and the environment file is off limits, so the question is unanswerable for those
  two runs forever. It is answerable for every run from here.
- **T-24-24 was measured rather than assumed**, and the measurement changed what needed doing: the
  existing exporter genuinely does emit `<f>1+1</f>` for drawing text starting with `=`.
- **The 56 and the 136 were not touched.** They appear in this plan only as fixture data carried
  through unchanged, and the two assertions that restated a count as a literal were rewritten to
  read it off the record instead.

## Task Commits

Each task was committed atomically, with the full offline suite green before every one:

1. **Task 1: the ledger and the run settings reach the report** — `bde8fab` (feat)
2. **Task 2: the UNIDENTIFIED GEOMETRY section of summary.txt** — `7738257` (feat)
3. **Task 3: the Unidentified Geometry worksheet** — `6388f35` (feat)
4. **Constraint correction: quantities compared against the record** — `537cbf4` (test)

## Files Created/Modified

- `src/bobbytailor/pipeline/reporter.py`
  - `UNNAMED_GEOMETRY_KEY` (mirrored by value), the per-sheet aggregation loop, the two gated
    additive keys, and the `run_settings` keyword-only argument with its docstring.
  - `_unnamed_geometry_lines`, `_unnamed_quantity_text`, `_UNNAMED_KIND_LABELS`,
    `_UNNAMED_GEOMETRY_LIST_CAP`; spliced into `_write_summary` after `_coverage_lines`.
- `src/bobbytailor/pipeline/pdf_analyzer.py` — one call site, one keyword argument.
- `src/bobbytailor/scrape/scraper.py` — two call sites, one keyword argument each.
- `scripts/export_takeoff_excel.py` — `_write_text`, the Unidentified Geometry worksheet, the
  About row.
- `tests/test_reporter_accuracy.py` — **24 new tests** in one documented 24-06 section.
- `.planning/phases/.../deferred-items.md` — the pre-existing half of T-24-24, with the
  measurement and the one-line fix.
- `.planning/ROADMAP.md` — 24-06 ticked, 5/10 → 6/10.

## The section, rendered by the real renderer

From a 30-record ledger (23 symbol groups, 4 wall classes, 2 rooms one of which has no scale-bound
quantity, 1 drafting-noise cluster), through `generate_report` into a temp output dir:

```
UNIDENTIFIED GEOMETRY  (these were MEASURED — the quantities below
                        are real and so are the objects; what the
                        drawings do not say is what they ARE)
──────────────────────────────────────────────────────────────────────
Candidates measured but not identified:                            30

They are held out of the take-off above on purpose. Naming one of them
from our own internal handle for it would put an identifier this app
invented in front of a client as the name of a thing to price. Their
absence from the take-off is an absence of a NAME, never of an object.

  symbol group                      24 candidate(s)            564 EA
  wall thickness class               4 candidate(s)          8,125 LF
  room                               2 candidate(s)          279.5 SF
      (1 with no measured quantity — unknown, not zero)

  Candidate           Quantity  Sheet              Why naming failed
  SYM-1                  35 EA  A-101              no name source
  ...
  WALL-TC2            1,625 LF  A-101              wall class unlabeled
  ... and 5 more — every one of them is in the
      `unnamed_geometry` list in takeoff.json
```

Three things in that output are deliberate and each has a test:

- **`279.5 SF` for two rooms, with the second counted apart.** Summing the unmeasured room in as a
  zero would publish a number nobody measured. INV-08 inside an aggregate.
- **`564 EA`, not `564.0 EA`.** A count of repeated marks is a number of things.
- **`... and 5 more`** — the cap bounds the page, never the account. The total above it is the whole
  population.

## Measurements taken this plan (all FREE, zero API)

**T-24-24, measured against the real library rather than assumed.** openpyxl 3.1.5, emitted
`xl/worksheets/sheet1.xml` read straight out of the zip:

| written as | data_type | emitted XML |
|---|---|---|
| `ws.append(["=1+1"])` | `f` | `<c r="A1"><f>1+1</f><v></v></c>` — **a live formula** |
| `cell.value = "=1+1"; cell.data_type = "s"` | `s` | `<c r="A3" t="inlineStr"><is><t>=1+1</t></is></c>` |
| `"@SUM(A1)"`, `"+1"`, `"-1"` via `append` | `s` | already inline strings |

So a leading `=` is the only trigger openpyxl itself honours, and forcing `data_type='s'` is the
complete mitigation for xlsx (the `@`/`+`/`-` prefixes are a CSV vector, and an inline-string cell
is not re-parsed). This is what turned the plan's *"match whatever the existing Coverage sheet
already does"* into a finding: the existing sheet does **nothing**, and matching it would have left
the most drawing-derived sheet in the workbook exposed.

**The exporter on a real saved run** (`.planning/paid-run-evidence/VisionOnly_P23V2_Crow_20260804_181352`,
copied read-only into a temp dir — the evidence directory was never written to):

| input | worksheets |
|---|---|
| the saved run exactly as shipped (pre-24, no ledger key) | `['Take-Off', 'Coverage', 'About']` — **unchanged** |
| the same run with one ledger record injected | `['Take-Off', 'Coverage', 'Unidentified Geometry', 'About']` |

and the injected `=1+1` evidence cell came back with `data_type == 's'`.

## Decisions Made

- **The empty ledger is an ABSENT key, not `[]`.** The plan explicitly preferred the empty list and
  explicitly named the check that would override it. `test_a_report_with_no_ledger_is_shaped_exactly_as_before`
  asserts exact top-level key-set equality against a list captured from the commit before 23-17;
  a key present with an empty value fails it. That pin protects two live scraper entry points, so
  it wins. The honest statement is made where it costs nothing: a run that *did* carry unnamed
  geometry always publishes it, in three places, with the meaning spelled out in words. Consumers
  use `.get(..., [])`, and the reasoning is recorded in the code beside the gate rather than left
  for a reader to reconstruct.
- **The key name is mirrored by value, not imported.** `pipeline.reporter` imports from
  `pipeline.coverage`, `pipeline.provenance` and (lazily) `pipeline.aggregator`, and nothing from
  `bobbytailor.vision`. A report renderer is the wrong place to open that dependency for one
  string. 24-04 set this precedent with `_ANCHOR_KIND_PAIRED_TAG`, including the divergence test,
  and this follows it exactly.
- **Grouped by (kind, unit), not by kind.** Symbol groups are EA, wall classes LF, rooms SF. One
  total across them would be a number that means nothing, and a per-kind total that silently
  ignored a second unit would be worse.
- **An unrecognised kind renders its raw value.** `fixture_cluster` shows up as `fixture cluster`
  and is counted. A renderer that skips a kind it has not met would reintroduce, inside the very
  section built to abolish silent omission, exactly that.
- **The About sheet carries a row too.** The caption in row 1 of the new worksheet follows the
  Coverage sheet's convention, but a reader who never clicks the fourth tab would still miss it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] The plan's own acceptance criterion failed on my first commit attempt, and the fix was to reword a comment**

- **Found during:** Task 1, running the acceptance criteria.
- **Issue:** the criterion is that `grep -c "fusion_rejected" src/bobbytailor/pipeline/reporter.py`
  must not increase (4 before). My new comment explained the distinction by naming the key in
  prose, taking it to 5.
- **Fix:** reworded to "an entry in the rejection list", exactly as 24-04 did when its own grep
  moved (16 → 15). The comment says the same thing.
- **Verification:** 4 before → **4 after**.
- **Committed in:** `bde8fab`

**2. [Rule 3 — Blocking] `run_settings` would have reached no artifact without editing two files outside the plan's fence**

- **Found during:** Task 1, reading the call sites.
- **Issue:** the plan's `files_modified` lists `reporter.py`, `export_takeoff_excel.py` and the
  test file. Adding the argument alone would have produced a reporter that CAN record the settings
  and a pipeline that never hands them over — Open Question 1 would be exactly as unanswerable
  afterwards as before, which is this half of the plan's entire purpose. This is 23-17 deviation 1
  in the same file, one plan later.
- **Fix:** one keyword argument at `pdf_analyzer.py`'s call site and at both of the scraper's
  (`_pipeline.settings` and `pipeline.settings` are the existing public accessors — no new state).
- **Verification:** `test_both_entry_points_hand_the_reporter_their_run_settings` greps both
  modules, so deleting either call site fails a test rather than silently re-opening the gap.
- **Committed in:** `bde8fab`

**3. [Rule 2 — Missing Critical] The workbook's new sheet writes drawing text as text, because the sheet it was told to copy does not**

- **Found during:** Task 3, checking what convention to follow.
- **Issue:** the plan says to *"match whatever the existing Coverage sheet already does for its own
  free-text cells."* Measured, the existing Coverage sheet does nothing — `ws3.append([... str(page.get("reason"))[:300] ...])`
  lets openpyxl infer the type, and a reason beginning with `=` becomes `<f>…</f>`. Matching that
  would have left T-24-24 (disposition: **mitigate**) unmitigated on the one worksheet whose
  evidence column is literally text harvested off the plan.
- **Fix:** `_write_text` forces `data_type='s'` for every text cell on the new sheet. The docstring
  carries the measurement so the next reader does not have to redo it.
- **Verification:** `test_excel_drawing_text_beginning_with_an_equals_is_not_a_formula` asserts
  `data_type == "s"` **and** that the value survives verbatim, so the mitigation cannot degrade
  into silently stripping the character.
- **Committed in:** `6388f35`

**4. [Rule 2 — Missing Critical] Two assertions restated a contested count as a literal**

- **Found during:** the end-of-plan constraint sweep.
- **Issue:** `assert by_id["SYM-2"]["quantity"] == 56` and `assert "56 EA" in section`. The 56 was
  fixture data I chose (it echoes the real bollard count 24-04 ledgered) and neither assertion
  tuned anything — but the constraint forbids the literal outright, and rightly: a reader cannot
  tell intent from a literal, and the rule exists so no count can ever be quietly moved toward a
  take-off PDF.
- **Fix:** both read the value off the record the producer wrote. Strictly stronger — the first now
  checks quantity, unit **and** reason for every record rather than three hand-picked ones.
- **Verification:** `git diff de3cdbc -- tests/test_reporter_accuracy.py | grep -cE '== *28\b|== *132\b|== *136\b|== *56\b'` → **0**.
- **Committed in:** `537cbf4`

### Scope boundary — logged, NOT fixed

**5. The pre-existing half of T-24-24 on the Take-Off and Coverage worksheets**

Logged to `deferred-items.md` with the emitted-XML measurement and the exact one-line fix. Not
fixed here because it is pre-existing, because the plan's own register scopes the threat to
*"Ledger text is drawing-derived and untrusted"*, and because re-typing every cell on two shipped
worksheets is a workbook-wide change that should be made and verified as one rather than smuggled
in beside a new sheet. The helper it needs already exists in that file.

### Readings of the plan, recorded rather than left implicit

**6. The plan's `-k excel` acceptance criterion selected nothing**

`python3 -m pytest tests/test_reporter_accuracy.py -k excel` matched zero tests: the shipped 23-17
workbook tests are named `test_the_workbook_*`. A criterion that selects nothing passes for having
looked at nothing. Rather than rename shipped tests, this plan's six export tests are named so
`-k excel` selects exactly them — the criterion now runs the thing it was written to run
(**6 passed, 49 deselected**).

**7. The merge-across-sheets concern 24-04 flagged does not arise**

24-04's handoff warned that `merge_with_provenance` does not carry the ledger key across sheets and
called that *"24-06's first job"*. Read at the call site, it is not one: `_run_sheet_vector` calls
`merge_with_provenance([fused])` with a **single** result, and the loop's `merged.setdefault(key, value)`
copies every non-component key through. The multi-result `setdefault` weakness is real but
unreachable — nothing in `src/` or `scripts/` calls it with more than one result. Aggregating in
the reporter across `all_extracted` is the correct level regardless, because that is where the
sheet name is known. Recorded rather than "fixed" by changing a function no caller exercises that
way.

---

**Total deviations:** 4 auto-fixed (2 blocking, 2 missing-critical), 1 logged and not fixed,
2 recorded readings. No scope creep, no new package, no new public surface beyond the two report
keys, the section renderer and the worksheet.

## The re-score, recorded and explicitly not acted on

`python3 scripts/score_report_dir.py --golden tests/fixtures/crow_cass/crow_cass_golden.csv --dir .planning/paid-run-evidence/VisionOnly_P23V2_Crow_20260804_181352`, **exit 0**:

> **Overall quantity accuracy: 30%   Name/found rate: 90%   Qty acc when found: 33%**
> Counts (EA) n=6 found=83% qty_ok=17% · Measured(SF/LF) n=4 found=100% qty_ok=50%

Unchanged from 24-03/24-04's recorded 30%, **and it could not have moved**: the scorer reads a
static saved artifact from 2026-08-04 18:13, not this commit. Recorded because the plan requires it
to be recorded, and not acted on.

**This plan does not move the metric at all, in either direction — it changes what the report SAYS,
not what it measures.** The plan's own success criteria forbid judging it on a percentage, and the
naive metric remains expected to DROP when 24-04 reaches a live run. That is the correct outcome and
it was stated in advance.

## GitNexus (CLAUDE.md, mandatory)

- **Before editing the reporter**, `impact("generate_report", direction=upstream)`:
  **HIGH**, 6 impacted, 3 direct callers, 3 affected processes (`run_project_scrape`,
  `run_analyze_from_manifest`, `run_pdf_analysis`), 1 module.
  **⚠️ HIGH risk was warned before a line was changed**, as CLAUDE.md requires.
  *Mitigation, by construction:* `run_settings` is keyword-only with a `None` default and its key is
  absent when omitted; the ledger key is absent when empty. The two scraper reports are therefore
  byte-identical unless the run genuinely carried unnamed geometry — pinned by the exact key-set and
  byte-for-byte tests, not asserted.
- **`detect-changes` before each commit:** **HIGH (8 affected processes)** / low / low.
  **⚠️ The HIGH reading before the task-1 commit is recorded as required.** It over-attributes: the
  index is stale at `c4f6e7d` and credits `ts`, `safe`, `run_dir` and other reporter locals this
  diff never touches, and the "affected flows" it lists are scraper login/normalisation paths
  downstream of a keyword argument with a default. Empirically the blast radius was zero — the
  suite moved only by the count of tests added, at every commit.
- The index remains stale (`c4f6e7d` vs HEAD); re-running `npx gitnexus analyze` is left to the
  phase orchestrator, since re-indexing mid-plan would invalidate the impact readings quoted above.

## Test Results

| Gate | Result |
|---|---|
| Baseline (plan entry, post-24-05) | 2068 passed, 1 skipped, 2 deselected |
| Full suite before `bde8fab` | **2079 passed**, 1 skipped, 2 deselected (48:28) |
| Full suite before `7738257` | **2086 passed**, 1 skipped, 2 deselected (49:44) |
| Full suite before `6388f35` | **2092 passed**, 1 skipped, 2 deselected (50:06) |
| Full suite before `537cbf4` | **2092 passed**, 1 skipped, 2 deselected (49:39) |
| `tests/test_four_set_coverage.py` + `tests/test_phase23_acceptance.py` | **28 passed, 1 skipped** (15:06) |
| `tests/test_reporter_accuracy.py` alone | 31 → **55** passed |
| `tests/test_coverage_ledger.py` + `tests/test_fusion.py` | 230 passed |
| `-k excel` | 6 passed, 49 deselected |

Net: **+24 tests, 0 regressions.** 2068 + 24 = 2092, and 24 is exactly the number of `def test_`
added. The final suite is unchanged from the third because `537cbf4` strengthens two existing
assertions and adds none. The 1 skip is pre-existing; the 2 deselected are the paid golden tests,
never run.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | No `-m golden`, no `accuracy_gate.sh`, no `vision_only_benchmark.py`, no `golden_convergence.py`; `ANTHROPIC_API_KEY` never referenced; `.env` never read. `score_report_dir.py` reads a saved artifact and makes no call. `grep -Ec "ANTHROPIC_API_KEY\|analyze_drawing\|pytest.mark.golden" scripts/export_takeoff_excel.py` → **0**, pinned by `test_the_excel_exporter_makes_no_paid_call`. |
| Offline gate green | 2092 passed / 1 skipped / 2 deselected, up from the 2068 baseline by exactly the 24 tests added. |
| `test_phase23_acceptance.py` + `test_four_set_coverage.py` green | Run together (28 passed, 1 skipped) **and** inside all four full-suite runs. |
| `unnamed_geometry` not folded into `coverage_ledger` or `fusion_rejected` | Its own top-level key. `grep -c fusion_rejected src/bobbytailor/pipeline/reporter.py` **4 before → 4 after** (asserted as a task acceptance criterion, and it caught a real violation on the first attempt — deviation 1). Pinned by `test_the_ledger_is_its_own_key_and_never_touches_the_rejection_list`. |
| Re-score recorded, not acted on | 30%, exit 0, stated above with the reason it cannot have moved. No percentage appears in any success claim. |
| The 56 / 136 / 28 / 132 never adjusted | `git diff de3cdbc -- tests/test_reporter_accuracy.py \| grep -cE '== *28\b\|== *132\b\|== *136\b\|== *56\b'` → **0**. The one place a count is compared, it is read off the record (deviation 4). |
| `uploads/`, `human_inputs/`, `reports/`, `.env`, `.planning/paid-run-evidence/` untouched | `git status --porcelain` over all five → **0**, checked before every commit. The saved run was copied into a temp dir to smoke-test the exporter; every read was read-only. |
| `output/` untouched | `git status --porcelain output/ \| wc -l` → **0** (a task-3 acceptance criterion). Every workbook this plan built went to a `tempfile` path. |
| No new packages | `git diff de3cdbc..HEAD --stat requirements.txt setup.py pyproject.toml \| wc -l` → **0**. openpyxl was already a dependency exercised by the shipped suite. |
| Python 3.9 | `python3 --version` → 3.9.6; `Optional`/`dict`/`list` annotations consistent with the module, no 3.10+ syntax. |
| No `--no-verify` | All four commits ran hooks normally on the main working tree. |
| GitNexus before editing reporter symbols | `impact` run on `generate_report` and **HIGH warned before any edit**; `detect-changes` before each commit, with the HIGH reading recorded. |

## Issues Encountered

- **The plan's preferred empty-list behaviour was incompatible with a shipped parity pin**, and the
  plan anticipated this precisely (*"if any of them require strict key-set equality, gate the key on
  non-emptiness instead and say so"*). Recorded here and in the code. The cost is that a report
  cannot say "we identified everything" out loud in JSON; the compensation is that when there IS
  something to say, three artifacts say it and one of them says it in sentences.
- **`-k excel` selected zero tests** (deviation 6). A green criterion that ran nothing is worth
  less than no criterion, since it reads as evidence.
- **The evidence directory's saved runs predate 24-04**, so neither carries `unnamed_geometry`. The
  end-to-end export check therefore had to inject a synthetic record onto a real report body to
  exercise the new sheet. The unchanged-workbook half of that check is the more valuable one and it
  ran against the artifact exactly as shipped.

## Known Stubs

None. Every field is populated by real code paths: the ledger by 24-04's producer, the sheet
attribution by the reporter, the settings by both entry points. The one thing deliberately not here
is any change to `fusion.py` — 24-04's handoff said 24-06 should not need to reopen it, and it did
not.

## Threat Flags

None — no new security-relevant surface. The register's dispositions were carried out:

- **T-24-23 (a silently-omitted candidate read as "does not exist")** — mitigated in three
  artifacts. The empty case renders nothing; a non-empty one cannot be hidden.
- **T-24-24 (spreadsheet formula injection via drawing-derived text)** — mitigated on the new sheet,
  with the emitted XML inspected rather than the behaviour assumed. The pre-existing exposure on two
  neighbouring worksheets is logged with its fix, not left for a reader to discover.
- **T-24-25 (an unbounded candidate list flooding summary.txt)** — mitigated: capped at 25 with an
  explicit remainder line naming the count and the artifact holding the rest.
- **T-24-26 (effective ensemble settings unrecorded)** — mitigated: `run_settings` reaches
  `takeoff.json` from both entry points.
- **T-24-SC (npm/pip/cargo installs)** — no new packages; **0** lines changed across
  `requirements.txt`, `setup.py` and `pyproject.toml`.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

**For 24-07 (SoM chip + wall-reference schema):** when 24-07 populates `bounding_wall_ids`, the
orphan-room branch 24-04 left live begins ledgering rooms that cite no wall — and those rooms are
now *visible* the moment they are ledgered, in the summary and in the workbook, instead of
disappearing. That makes 24-07's change observable at review rather than only in a JSON query.

**For 24-09 / 24-10 (the determinism harness and the phase gate):** `report["unnamed_geometry"]` is
a stable, artifact-level list carrying per-record sheet attribution, so two structural free claims
are assertable across a whole run without reopening fusion — every candidate is either published or
ledgered exactly once, and no published row's name equals its own `candidate_id`. `run_settings`
additionally lets the gate assert that two runs being compared ran under the same N, which was
previously unknowable from the artifacts.

**For Phase 25 (making these candidates nameable):** the ledger is now the project's readable
worklist of what it cannot name, with the machine reason on every row. `summary.txt` prints the
breakdown by kind, so the shape of the problem — how much is symbol groups with no text at all
versus rooms carrying only a number — is legible without writing a script.

**Honest expectations to carry into verification:**

- **The section only appears on a run whose fusion produced a ledger.** Both saved paid runs predate
  24-04 and carry no `unnamed_geometry`, so re-exporting either shows the workbook *unchanged* —
  which is the correct result and is itself one of this plan's acceptance criteria, not a failure to
  surface anything.
- **No accuracy claim is made or measurable here.** This plan changes what the report says about
  what it could not identify. It moves no quantity, adds no line item and removes none.

## Self-Check: PASSED

All claimed files exist on disk: `src/bobbytailor/pipeline/reporter.py`,
`src/bobbytailor/pipeline/pdf_analyzer.py`, `src/bobbytailor/scrape/scraper.py`,
`scripts/export_takeoff_excel.py`, `tests/test_reporter_accuracy.py`,
`.planning/phases/24-binding-determinism-text-anchored-labeling/deferred-items.md`,
`.planning/ROADMAP.md`, and this SUMMARY. All four claimed commits resolve in `git log`
(`bde8fab`, `7738257`, `6388f35`, `537cbf4`). `.planning/paid-run-evidence/`, `uploads/`,
`human_inputs/`, `reports/` and `output/` are all untouched (0 porcelain entries each).

---
*Phase: 24-binding-determinism-text-anchored-labeling*
*Completed: 2026-08-05*
