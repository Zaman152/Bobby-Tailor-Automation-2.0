---
phase: 24-binding-determinism-text-anchored-labeling
plan: 03
subsystem: pipeline-aggregator
tags: [naming, canonicalisation, precedence, determinism, reconciliation, pytest]

# Dependency graph
requires:
  - phase: 23-measurement-engine-completion
    provides: "SP-7a's canonical_library_name and its stated FORM-not-RENAME boundary; INV-08's 'a blank is never a zero' contract, which this plan applies to the expected-vs-measured pair"
  - phase: 24-binding-determinism-text-anchored-labeling
    plan: 02
    provides: "the deliberate NON-folding of _squash_wall_name, which reserved plural folding for this plan so two folding rules could not drift apart"
provides:
  - "_plural_stem — a pure trailing-plural suffix rule with no lexicon, no alias table and no similarity measure"
  - "plural-aware _norm_item_key — the bucket identity that decides whether two rows are ONE item"
  - "plural-aware canonical_library_name — the agreement test now compares plural-insensitive STEMS"
  - "NAME_AUTHORITY_PRECEDENCE + resolve_published_name — one declared order, one arbiter, every publication path routed through it"
  - "_learned_name_authority — the learned store's two provenances (human correction vs record_ai_manifest) separated for arbitration"
  - "canonicalisation on READ from the learned store, with no migration written against a store this module does not own"
  - "_cross_reference_unreconciled — a blank expected row and a measured row that may answer it are BOTH flagged, never merged and never deleted"
affects: [24-04 unnamed-geometry ledger, 24-05 vocabulary persistence, 24-06 ledger surfacing, 24-10 phase gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Form folding, never renaming: the only permitted transformation is a trailing plural suffix on an otherwise character-identical stem"
    - "Under-folding is safe, over-folding is the defect: an ambiguous plural (`-ses`) falls through to the rule that cannot merge two different words"
    - "One arbiter, not a branch race: every candidate name is offered with its authority and a declared total order decides"
    - "Canonicalise on READ: a persisted store is folded at the point of use, idempotently, instead of migrated destructively"
    - "Annotate both halves: information that cannot be reconciled is moved to where it reads correctly, never merged and never deleted"

key-files:
  created: []
  modified:
    - src/bobbytailor/pipeline/aggregator.py
    - tests/test_aggregator.py
    - .planning/ROADMAP.md

key-decisions:
  - "The learned store is TWO authorities, not one. 24-RESEARCH's `library > learned > vision` is applied to the store's AI tier — the rows record_ai_manifest writes — and NOT to its human tier, because demoting a human's correction below a machine-harvested library breaks V3-LEARN-02 and contradicts the store's own documented human-wins invariant"
  - "Unknown learned provenance resolves to the HUMAN tier, matching the store's schema default: an authority is demoted on evidence, never on assumption"
  - "`-ses` is deliberately NOT treated as an `-es` plural. `Base`/`Bases` and `Bus`/`Buses` are indistinguishable without a lexicon, so the ambiguous case falls through to the plain `-s` rule, which folds `Bases` correctly and merely fails to fold `Buses`"
  - "A verbatim authority (legend, manifest) is routed through the arbiter but never canonicalised — rewriting a user's own words is the mangling the legend-verbatim contract exists to prevent"
  - "Cross-reference pairing uses the measured row's naming AUTHORITY, not its name. A legend or manifest label is printed evidence; a library alias resolution or a learned recall is a hypothesis, and only a hypothesis can be confidently wrong about which object was measured"
  - "The partner count in a cross-reference is always exact; the cap trims the LIST, never the truth"

requirements-completed: []
# HONEST SCOPE NOTE: this plan carries `requirements: [V4-DET-02]` but does NOT tick it,
# for the same reason 24-02 did not. V4-DET-02 holds end to end only when the wall bind is
# invariant AND its object list is stable. 24-02 delivered the decision, this plan folds the
# name FORM and declares the arbiter, and 24-05 still owes the stable per-project object list
# (defect F3). The phase gate (24-10) verifies the whole requirement.

coverage:
  - id: P1
    description: "A singular and a plural spelling of one item fold to one canonical form and one bucket"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py#test_canonical_plural_folding_binds_the_singular_library_spelling"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_canonical_plural_folding_is_idempotent"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_norm_item_key_folds_singular_and_plural_into_one_bucket"
        status: pass
    human_judgment: false
  - id: P2
    description: "A genuinely different object never folds into another — a synonym is not a plural"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py#test_canonical_never_renames_dock_bumper_into_bollards"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_canonical_never_renames_a_stem_that_differs_by_more_than_a_plural"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_norm_item_key_keeps_two_genuinely_different_objects_apart"
        status: pass
      - kind: other
        ref: "grep -Ec 'difflib|SequenceMatcher|levenshtein|fuzz|rapidfuzz' src/bobbytailor/pipeline/aggregator.py -> 0"
        status: pass
    human_judgment: false
  - id: P3
    description: "Degenerate names are returned verbatim rather than collapsed to nothing"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py#test_canonical_folding_never_collapses_a_name_to_nothing"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_the_plural_stem_is_a_pure_suffix_rule_with_no_lexicon"
        status: pass
    human_judgment: false
  - id: P4
    description: "One declared naming-authority precedence exists and every publication path routes through it"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py#test_naming_authority_precedence"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_naming_authority_precedence_is_one_declared_total_order"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_every_published_naming_source_comes_from_the_one_precedence"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_resolve_published_name_ignores_blanks_and_unknown_authorities"
        status: pass
    human_judgment: false
  - id: P5
    description: "The library outranks a persisted MODEL answer; a human correction still outranks the library"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py#test_an_ai_recorded_learned_name_is_outranked_by_the_library"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_a_human_correction_still_outranks_the_library"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_an_unknown_learned_provenance_keeps_the_precedence_it_always_had"
        status: pass
      - kind: integration
        ref: "tests/test_naming_conventions.py#test_learned_correction_outranks_estimator_normalization (pre-existing, still green)"
        status: pass
    human_judgment: false
  - id: P6
    description: "Learned names are folded on READ, with no migration written against the store (T-24-10)"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py#test_a_learned_name_is_canonicalised_on_read_and_the_store_is_not_migrated"
        status: pass
      - kind: other
        ref: "grep -Ec 'DROP TABLE|DELETE FROM learning_vocabulary|ALTER TABLE learning_vocabulary' src/bobbytailor/pipeline/aggregator.py -> 0"
        status: pass
    human_judgment: false
  - id: P7
    description: "A verbatim authority's own words are never rewritten (T-24-11 boundary)"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py#test_a_manifest_name_is_never_canonicalised"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#test_a_legend_label_is_never_canonicalised"
        status: pass
    human_judgment: false
  - id: P8
    description: "The plural pair collapses to one row; the genuinely-different pair stays two rows, both cross-referenced (T-24-12)"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py#TestExpectedAndMeasuredReconcile::test_expected_and_measured_reconcile_a_plural_pair_into_one_row"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#TestExpectedAndMeasuredReconcile::test_expected_and_measured_reconcile_flags_both_halves_of_a_real_pair"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#TestExpectedAndMeasuredReconcile::test_a_cross_reference_is_never_a_merge_or_a_deletion"
        status: pass
      - kind: other
        ref: "replayed against the SAVED evidence names: run 1's blank `Bollards` row is suppressed by the fold; run 2's survives and is cross-referenced"
        status: pass
    human_judgment: false
  - id: P9
    description: "Cross-referencing is conservative and structural — never name similarity, never a merge"
    requirement: V4-DET-02
    verification:
      - kind: unit
        ref: "tests/test_aggregator.py#TestExpectedAndMeasuredReconcile::test_a_different_unit_or_basis_is_never_cross_referenced"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#TestExpectedAndMeasuredReconcile::test_a_printed_name_is_evidence_and_is_never_cross_referenced"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#TestExpectedAndMeasuredReconcile::test_the_partner_count_is_exact_even_when_the_list_is_capped"
        status: pass
      - kind: unit
        ref: "tests/test_aggregator.py#TestExpectedAndMeasuredReconcile::test_no_measured_row_means_no_cross_reference_at_all"
        status: pass
      - kind: other
        ref: "name-similarity grep unchanged versus the pre-task value (1 -> 1)"
        status: pass
    human_judgment: false

# Metrics
duration: 4h 05m
completed: 2026-08-05
status: complete
---

# Phase 24 Plan 03: Canonical Name Form Summary

**One object can no longer occupy two rows because of a trailing `s`, three naming authorities that used to race now answer to one declared arbiter, and where two names genuinely cannot be reconciled BOTH rows say so instead of a blank quietly reading as "not found".**

## Performance

- **Duration:** 4h 05m (three full 47-minute suites, one per commit, dominate it)
- **Started:** 2026-08-05
- **Completed:** 2026-08-05
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- **The fold is proven on the recorded names, not on invented ones.** Replaying the two saved paid runs' own `takeoff_summary` item names through the new `_norm_item_key`: the 14:19 run's blank `Bollards` row is now **suppressed**, because that run's measured row was named `Bollard`. That is defect **F2**, closed, on real data. The 18:13 run's blank survives — its measured row was `Dock Bumper`, a genuinely different name — which is exactly the split the plan predicted folding could not fix, and which the cross-reference now annotates instead.
- **The negative is load-bearing and lives alone.** `Dock Bumper` matches ITEM_NAME_MAP's `dock.*bumper` rule, whose canonical form is `Dock Leveler`. It resolves to itself. If that test ever fails, the folding rule has become a synonym mapper and a genuinely distinct object is disappearing from client reports.
- **The arbiter is real, not nominal.** `resolve_published_name` is the only function that decides which authority names a row, and the legend path is routed through it too — as a verbatim authority, so the assignment is unchanged and the claim becomes literally rather than nearly true.
- **A shipped requirement was caught before the plan's literal instruction broke it.** See the deviation below: inverting learned-above-library wholesale would have made an estimator re-type the same correction on every run.

## Task Commits

Each task was committed atomically:

1. **Task 1: Plural folding — a form transformation, never a rename** — `f821119` (feat)
2. **Task 2: One naming-authority precedence, enforced at one site** — `dcb72fe` (feat)
3. **Task 3: The measured row and the expected row must reconcile or both be flagged** — `887ac10` (feat)

## Files Created/Modified

- `src/bobbytailor/pipeline/aggregator.py`
  - `_plural_stem` + `_NOT_A_PLURAL_ENDINGS` / `_ES_PLURAL_STEM_ENDINGS` / `_MIN_PLURAL_STEM_LEN` — the suffix rule and its guards.
  - `_norm_item_key` — stems per token, so a singular and a plural spelling are ONE bucket identity.
  - `canonical_library_name` — the agreement test compares plural-insensitive stems; every other line, and the stated boundary, unchanged.
  - `NAME_AUTHORITY_*` constants, `NAME_AUTHORITY_PRECEDENCE`, `_VERBATIM_NAME_AUTHORITIES`, `_PUBLISHED_SOURCE_BY_AUTHORITY`, `resolve_published_name`, `_learned_name_authority`.
  - `aggregate_takeoff` — the three racing branches replaced by one candidate list and one arbiter call; the legend path routed through it as a verbatim authority.
  - `_expected_items_without_a_manifest` — learned expected-item names canonicalised on read, the same rule the library branch has applied since SP-7a.
  - `_cross_reference_unreconciled`, `_library_basis_by_key`, `_name_list`, `_HYPOTHESIS_NAME_SOURCES`, `_CROSS_REFERENCE_NAMES_SHOWN`.
- `tests/test_aggregator.py` — **25 new tests** in three documented 24-03 sections.
- `.planning/ROADMAP.md` — 24-03 ticked, plan count 2/10 -> 3/10.

## The precedence, top to bottom

| # | Authority | Named by | Published `source` | Canonicalised? |
|---|---|---|---|---|
| 1 | `plan_schedule_legend` | the drawing's own printed schedule | `plan_schedule_legend` | no — verbatim |
| 2 | `manifest` | the user's own object manifest | `manifest` | no — verbatim |
| 3 | `learned_human` | a prior estimator correction (`source='human'`) | `learned` | yes |
| 4 | `library` | component library + project vocabulary | `library` | yes |
| 5 | `learned_ai` | `record_ai_manifest`'s persisted model answer (`source='ai'`) | `learned` | yes |
| 6 | `vision` | the static-map / vision reading | `vision` | yes |

## Decisions Made

- **The learned store is two authorities, not one.** 24-RESEARCH §4.3.2 states the order as `library > learned > vision`. That is applied to the store's **AI** tier — the rows `record_ai_manifest` writes with `source='ai'`, which is the tier the F1 evidence indicts, because a persisted model answer is still a model answer. It is deliberately **not** applied to the store's **human** tier. `learning_vocabulary` carries both provenances (`store.py:142`) and the store's own retrieval already ranks human above ai — its documented "human-wins invariant". See the deviation below for why the wholesale inversion would have been a regression.
- **Unknown provenance resolves to the human tier.** That is the store's own schema default (`source TEXT NOT NULL DEFAULT 'human'`) and the conservative reading: an authority is demoted on evidence, never on assumption. Every existing test double, which supplies no `vocabulary` at all, therefore keeps exactly the precedence it had.
- **`-ses` is not treated as an `-es` plural.** `Base`/`Bases` and `Bus`/`Buses` are indistinguishable without a lexicon and this function has none. The ambiguous case falls through to the plain `-s` rule, which folds `Bases` -> `Base` correctly and merely fails to fold `Buses` -> `Bus`. **Under-folding is the status quo and is safe; over-folding is the defect the whole boundary exists to prevent.** `ss`/`us`/`is` endings and stems under three characters are protected outright, so `Glass`, `Truss`, `Radius`, `Axis` and `Gas` are untouched.
- **A verbatim authority is routed through the arbiter but never canonicalised.** Rewriting a user's manifest `Bollard` into ITEM_NAME_MAP's `Bollards` would be the app editing a human's own vocabulary — the mangling the legend-verbatim contract exists to prevent.
- **Cross-reference pairing keys on the measured row's naming AUTHORITY, not its name.** A legend or manifest label is printed evidence: had those been the bollards, the printed name would say so and `_norm_item_key` would already have matched. A `vision` row named from a bare candidate id is unnamed geometry, which is 24-04's ledger and not a naming question. What remains — a library alias resolution and a learned recall — is precisely the class of answer that can be confidently wrong about *which* object was measured. This is structural, and no name is ever compared to another name.
- **Measure basis is read from the same library list on both sides.** A measured bucket's `item_type` comes from the reading (`component`, `concrete_slab`) while an expected row's comes from the library's `basis` (`count`, `wall_area`). Comparing those directly would compare two different vocabularies, so the measured row's basis is looked up in the library that produced the expected row.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical] The precedence inversion had to spare the learned store's human tier**

- **Found during:** Task 2, reading the shipped precedence tests before changing the naming path.
- **Issue:** The plan's literal instruction is `deterministic library > learned store > vision`. Applied wholesale that inverts the shipped `learned > library` order and breaks two tests whose docstrings encode a deliberate design decision — `tests/test_naming_conventions.py::test_learned_correction_outranks_estimator_normalization` ("the learned rename must win... human correction wins") and `tests/test_aggregator.py::TestCompletenessDoesNotContradictItself::test_a_renamed_library_object_is_not_also_reported_as_missing`. Worse than the test breakage is what it means: **V3-LEARN-02's whole promise is that a correction made once never recurs.** Under the wholesale inversion an estimator renames a wall text, and the very next run the library overrides it again, forever. And the `library` argument is not purely deterministic — it is the harvested component library **merged with the LLM project vocabulary**, the exact list defect F3 shows is re-derived differently on every run. Ranking that above a human's explicit correction inverts the wrong pair.
- **Fix:** the learned store is split into the two provenances it already has. `record_ai_manifest`'s `source='ai'` rows — a persisted model answer, and the tier the F1 `Bollard` evidence actually came from — rank **below** the library, exactly as the research asks. `source='human'` rows keep their shipped rank above it, agreeing with the store's own documented human-wins ordering. `_learned_name_authority` re-finds the winning row the same way `_vocab_index` does, since `lookup_name` returns only `(name, unit)`.
- **Files modified:** `src/bobbytailor/pipeline/aggregator.py`
- **Verification:** `test_an_ai_recorded_learned_name_is_outranked_by_the_library` and `test_a_human_correction_still_outranks_the_library` pin both halves; both pre-existing tests stayed green without modification.
- **Committed in:** `dcb72fe`

**2. [Rule 1 — Bug] The module's own prose tripped its guard grep**

- **Found during:** Task 3, running the acceptance criteria.
- **Issue:** Task 1's criterion requires `grep -Ec "difflib|SequenceMatcher|levenshtein|fuzz|rapidfuzz"` over `aggregator.py` to return `0`. A docstring I wrote explaining *why* similarity matching is forbidden used the very word the guard searches for, taking the count from 0 to 1. A guard that its own explanatory prose can trip is a guard nobody trusts — and the next reader would have had to decide whether a real matcher had been added.
- **Fix:** the sentence was reworded to "the approximate name matcher", with a note in-file recording that the omission is deliberate.
- **Files modified:** `src/bobbytailor/pipeline/aggregator.py`
- **Verification:** the grep returns `0`; the name-similarity grep is unchanged at its pre-task value of `1`.
- **Committed in:** `887ac10`

**3. [Process] "Neither is already reconciled by name" was read structurally, not literally**

- **Found during:** Task 3, testing the rule against the saved evidence rather than against an invented fixture.
- **Issue:** Read literally as "the measured row answered no expected item", the rule **never fires on the real data**: `Dock Bumper` is itself an enumerated library object, so it reconciles the library's own `Dock Bumper` expectation, and the blank `Bollards` row beside it would have stayed unexplained — the precise defect the task exists to fix.
- **Fix:** "already reconciled by name" is implemented as *named by an authority that is evidence rather than hypothesis* (legend/manifest), plus the bucket-key fold. A library alias resolution does not prove the 56 things measured were dock bumpers rather than bollards; the NAME was a hypothesis, which is why it is a plausible answer. Recorded here rather than left implicit, because it is a reading of the plan and not a transcription of it.
- **Files modified:** `src/bobbytailor/pipeline/aggregator.py`
- **Committed in:** `887ac10`

---

**Total deviations:** 3 (1 missing-critical, 1 bug, 1 process). No scope creep, no new package, no new public surface beyond the arbiter, its constants and the cross-reference helper.

## 24-02's differential did NOT start failing — and that is the correct outcome

The 24-02 summary predicted that `tests/test_fusion.py::test_wall_class_label_invariance`'s residual assertion "should start failing when this plan lands". It did not, and deleting or weakening it was never on the table. The reason is specific and checkable:

That assertion pins `rows_a["WALL-TC3"]["name"] != rows_b["WALL-TC3"]["name"]`, where the two names are read from the evidence at runtime as **`Aluminum Storefront`** and **`Aluminum Storefront/Curtain Wall`**. Run through the new fold:

| F3 pair | folds? | why |
|---|---|---|
| `Metal Downspout` / `Metal Downspouts` | **yes** | trailing plural |
| `Metal Stair` / `Metal Stairs` | **yes** | trailing plural |
| `Bollard` / `Bollards` | **yes** | trailing plural — and both canonicalise to `Bollards` |
| `Aluminum Storefront` / `Aluminum Storefront/Curtain Wall` | **no** | the second carries an extra compound term. Folding it needs a substring or synonym rule — the rename this phase forbids |
| `Dock Bumper` / `Bollards` | **no** | different objects; the load-bearing negative |

So 24-03 closes the two F3 rows that are plural pairs and correctly leaves the storefront pair alone. **A green differential here is the boundary holding, not the plan missing.** Had it gone red, that would have meant `canonical_library_name` had grown into a synonym mapper. The residual assertion remains 24-05's to retire, by stabilising the per-project object list so both runs derive the same name in the first place.

## Measurements taken this plan (all FREE, zero API)

**The fold, replayed against the saved evidence's own recorded names:**

| run | measured 56-EA row | blank `Bollards` row after 24-03 |
|---|---|---|
| 14:19 | `Bollard` (source: learned) | **suppressed** — same bucket key |
| 18:13 | `Dock Bumper` (source: library) | survives, now **cross-referenced** on both rows |

**Cross-reference volume, predicted from the saved rows** (the aggregator cannot be re-run against the evidence — `takeoff.json` preserves the *output*, and the `library` argument that produced it was never saved):

| run | expected blanks | hypothesis-named measured rows (the only cross-reference candidates) |
|---|---|---|
| 14:19 | 31 | 7 — `Bollard`, `Concrete Curb`, `Concrete Pad`, `Pipe Guardrail`, `Pipe Handrail`, `Sealed Concrete`, `Tilt Up Wall` |
| 18:13 | 34 | 6 — `Concrete Pad`, `Dock Bumper`, `Exposed Structure`, `LED Wall Pack`, `Sealed Concrete`, `Tilt Up Wall` |

**Honest note on the noise:** the candidate set is small, but the *expected* side is not. On the 18:13 run roughly twenty EA/count expectations share a unit and basis with the single EA/count candidate (`Dock Bumper`; `LED Wall Pack` is excluded, its library basis is `wall_area`). So `Dock Bumper` will carry one reason naming three of them plus "and N more", and each of those blanks will carry one reason naming `Dock Bumper`. That is not tidy, but it is true: the run measured one hypothesis-named counted object and enumerated twenty it never measured, and no evidence available offline distinguishes them. The row that matters — `Bollards`, the one a client misreads as "not found" — now carries the pointer.

**Re-score of the saved evidence** (`scripts/score_report_dir.py`, exit **0**): **30%** overall quantity accuracy, 90% name/found rate. **Recorded, explicitly not acted on**, and it could not have moved: the scorer reads a *static saved artifact*, so it measures the 18:13 run, not this commit. Worth noting for whoever reads the score next — the scorer performs its own approximate name matching (`Stairs≈Metal Stairs`, `Internal Tilt up walls≈Tilt Up Wall`), which is a further reason an accuracy percentage is a poor judge of a naming-determinism change. Per the plan's own success criteria and 24-RESEARCH pitfall 4: judge this plan on whether one object now has one name.

## GitNexus (CLAUDE.md, mandatory)

- **Before editing the naming path:** `impact(..., direction=upstream)` on all three targets. **⚠️ HIGH risk warned before a line was changed**, as CLAUDE.md requires:
  - `canonical_library_name` — **HIGH**, 9 impacted, 3 direct callers, 4 affected processes (`run_project_scrape`, `run_analyze_from_manifest`, `aggregate_takeoff`, `run_pdf_analysis`), 3 modules.
  - `aggregate_takeoff` — **HIGH**, 7 impacted, 1 direct caller, 3 affected processes.
  - `_norm_item_key` (disambiguated to the aggregator symbol; a same-named function also exists in `reporter.py` and was deliberately **not** touched) — **HIGH**, 6 impacted, 2 direct callers, 4 affected processes.
  - Empirically the blast radius held: the full suite moved only by the count of tests added, at every one of the three commits.
- **`detect-changes` before each commit:** run before all three — risk low / medium / medium, 0 / 2 / 2 affected processes.
- The index remains stale (`c4f6e7d` vs HEAD). Re-running `npx gitnexus analyze` is left to the phase orchestrator, since re-indexing mid-plan would invalidate the impact readings quoted above.

## Test Results

| Gate | Result |
|---|---|
| Baseline (plan entry, post-24-02) | 1992 passed, 1 skipped, 2 deselected |
| Full suite before `f821119` | **2000 passed**, 1 skipped, 2 deselected (46:48) |
| Full suite before `dcb72fe` | **2010 passed**, 1 skipped, 2 deselected (46:59) |
| Full suite before `887ac10` | **2017 passed**, 1 skipped, 2 deselected (47:05) |
| `tests/test_reporter_accuracy.py` + `test_naming_conventions.py` + `test_learning_retrieval.py` + `test_component_library.py` + `test_coverage_ledger.py` + `test_phase23_acceptance.py` + `test_four_set_coverage.py` | 213 passed |

Net: **+25 tests, 0 regressions.** 1992 + 25 = 2017. The 1 skip is the pre-existing one; the 2 deselected are the paid golden tests, never run.

## Constraint Compliance

| Constraint | Evidence |
|---|---|
| No paid API | No `-m golden` run, `accuracy_gate.sh` / `vision_only_benchmark.py` / `golden_convergence.py` never invoked, `ANTHROPIC_API_KEY` never referenced, `.env` never read. `score_report_dir.py` reads a saved artifact and makes no call. |
| Offline gate green | 2017 passed / 1 skipped / 2 deselected, up from the 1992 baseline by exactly the 25 tests added. |
| `test_phase23_acceptance.py` + `test_four_set_coverage.py` green | Explicitly run together (213 passed) and inside every full-suite run. |
| Coincidence trap fenced | `grep -Ec '== *28\b\|== *132\b\|== *136\b\|== *56\b'` over all three new test sections -> **0**. No number moved toward golden; the 56 and the 136 were never touched. |
| No fuzzy / synonym folding | `grep -Ec 'difflib\|SequenceMatcher\|levenshtein\|fuzz\|rapidfuzz'` -> **0**; name-similarity grep unchanged at **1** (pre-existing). `_plural_stem` has no lexicon, no alias table and no distance measure. |
| `canonical_library_name` extended IN PLACE | One function, one added stem comparison. Not forked; SP-7's ownership intact. |
| No store migration | `grep -Ec 'DROP TABLE\|DELETE FROM learning_vocabulary\|ALTER TABLE learning_vocabulary'` -> **0**. Canonicalisation happens on read. |
| Paid-run evidence untouched | `git status --porcelain .planning/paid-run-evidence/ \| wc -l` -> **0**, checked before every commit. Every read was read-only. |
| `uploads/`, `human_inputs/`, `reports/`, `.env` untouched | `git status --porcelain` over all four -> **0**. Not in any commit. |
| No new packages | `git diff --stat requirements.txt setup.py pyproject.toml \| wc -l` -> **0**. |
| Python 3.9 | `python3 --version` -> 3.9.6; `Dict`/`List`/`Optional` from `typing`, no 3.10+ syntax. |
| No `--no-verify` | All three commits ran normally on the main working tree. |
| GitNexus before editing aggregator symbols | `impact` run on all three targets and HIGH risk warned; `detect-changes` before each commit. |
| Re-score recorded, not acted on | 30%, exit 0, stated above with the reason it cannot have moved. |

## Issues Encountered

- **`_plural_stem`'s sibilant rule had to be narrowed during design.** Including `s` in the `-es` stem endings (so `glasses` -> `glass`) also produces `houses` -> `hous` while `house` -> `house`, and `bases` -> `bas` while `base` -> `base` — a *failure to fold* in the common case, introduced in exchange for folding a rare one. Dropping `s` from the set folds `bases`/`base` and `houses`/`house` correctly and merely declines to fold `glasses`/`glass` and `buses`/`bus`. Declining to fold is the status quo; the alternative was a stem nothing else matches.
- **The learned store's provenance is not on `lookup_name`.** `LearnedContext.lookup_name` returns `(name, unit)` only, so the winning row is re-found by replicating `_vocab_index`'s rule (normalise `raw_pattern`, first match wins, rows arrive human-first). `retrieval.py` was deliberately not modified — it is outside this plan's file fence, and the aggregator already reads `learned.expected_items` directly, so reading `learned.vocabulary` is the same established pattern.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

**Blocks nothing; unblocks 24-05 and sharpens 24-04.**

**For 24-05 (vocabulary persistence):** this plan folds the name FORM and declares the ARBITER; 24-05 owes the stable per-project object LIST. The two remaining F3 rows are the storefront pair (`Aluminum Storefront` vs `Aluminum Storefront/Curtain Wall`) and the retaining-wall basis flip (LF vs SF) — neither is a plural and neither may be folded. 24-05 should also read `learning_vocabulary`'s `source` column when it decides what to persist: `NAME_AUTHORITY_LEARNED_AI` vs `NAME_AUTHORITY_LEARNED_HUMAN` is now a live distinction in the aggregator, and a persistence path that flattens it would silently promote model answers to the human tier. **Do not write a migration against the store** — the fold is idempotent on read and needs none.

**For 24-04 (unnamed-geometry ledger):** `_HYPOTHESIS_NAME_SOURCES` deliberately excludes `vision`, so a `SYM-*` row is not offered as an answer to a blank expected row. When 24-04 removes those rows from the take-off, no cross-reference assertion changes. If 24-04 introduces a new `source` marker, `test_every_published_naming_source_comes_from_the_one_precedence` will fail until it is registered — which is the intended alarm, not an obstacle.

**For 24-10 (the phase gate):** the gate can assert that no two published rows share a `_norm_item_key`, and that every published `source` is in `_PUBLISHED_SOURCE_BY_AUTHORITY` or the documented not-measured set. Both are structural and free.

**Honest expectations to carry into verification:**
- **No accuracy claim is made or measurable here.** The one score recorded is a re-score of a static saved artifact and cannot reflect this commit. Judge this plan on whether one object now has one name.
- **The cross-reference is deliberately noisy on the expected side** and the numbers are stated above rather than discovered at review. Narrowing it further would need evidence the run does not have offline, and guessing a narrower pairing rule is the coincidence trap in a new costume.

## Self-Check: PASSED

All claimed files exist on disk (`src/bobbytailor/pipeline/aggregator.py`, `tests/test_aggregator.py`, `.planning/ROADMAP.md`, this SUMMARY). All three claimed commits resolve in `git log` (`f821119`, `dcb72fe`, `887ac10`). `.planning/paid-run-evidence/` is untouched (0 porcelain entries).

---
*Phase: 24-binding-determinism-text-anchored-labeling*
*Completed: 2026-08-05*
