---
phase: 21-accuracy-learning-engine
plan: 11
subsystem: vision
tags: [ensemble, self-consistency, voting, budget-guard, tiled-counting, nms-dedup]

# Dependency graph
requires:
  - phase: 21-05
    provides: render_clip_crop shared zoom primitive; MODEL_ROUTING v2 env-driven slugs
  - phase: 21-08
    provides: candidate-ID-grounded schemas (raster_extraction_schema count_estimate); analyze_drawing output_schema/images params
provides:
  - vote(samples, unit_kind) with RESEARCH §4 exact thresholds (EA max−min ≤ max(1, 10% of median); SF/LF spread ≤10%; unanimous/majority/none confidence mapping)
  - EnsembleResult dataclass with persisted vote vectors (auditability) + to_dict()
  - run_ensemble N=3 fan-out with +2 escalation on disagreement, temperature ladder + cached runtime temperature-ignore probe with prompt-variation fallback
  - run_tiled_count — COUNT_TILING grid integration, 17.5% tile overlap, position-based NMS dedup in overlap bands; result is ONE ensemble member (extra_members)
  - BudgetGuard/BudgetExceeded — thread-safe hard per-run API spend cap; refused charges never accumulate
  - ensemble_settings() single (n, budget_usd) reader for 21-13 RunSettings
  - Config: API_BUDGET_PER_RUN_USD (default 10.0), ENSEMBLE_N (default 3)
affects: [21-13 pipeline integration, 21-14 verify-retry, 21-16 accuracy gate, raster fallback path]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Injectable analyze_call with signature-filtered kwargs (sample_index/temperature/prompt_variation) — zero direct Anthropic client usage in ensemble.py"
    - "BudgetGuard.charge() refuses (never accumulates) charges past the cap — ledger only holds paid-for work"
    - "Budget abort → current-best EnsembleResult with needs_review=True reason='budget_exhausted' — never a silent partial (Pitfall 7 verbatim)"

key-files:
  created:
    - src/bobbytailor/vision/ensemble.py
    - tests/test_ensemble.py
  modified:
    - src/bobbytailor/config.py
    - tests/conftest.py
    - .env.example

key-decisions:
  - "vote() acceptance: whole-vector band (max−min ≤ tol) OR strict-majority-within-tolerance-of-median both accept at medium — reconciles RESEARCH §4's vote rule with its confidence mapping; escalated 5-sample votes pass on 3-of-5 agreement while [5,9,16]-style 3-way disagreement still flags"
  - "Refused BudgetGuard charge is NOT accumulated and its sample is NOT voted — spent_usd ledger and vote vector only ever hold paid-for work ('exactly 2 calls charged' auditable after abort)"
  - "Temperature probe compares metadata-stripped JSON fingerprints of the first two dict samples only — identical scalars across temps are legitimate agreement, not evidence of ignoring temperature; cache keyed by probe_key (per model/route)"
  - "run_tiled_count NMS dedups ONLY detections covered by ≥2 tile rects (overlap band) from DIFFERENT tiles within 1.5 coarse cells — nearby same-tile detections are distinct objects"
  - "Tiled result joins run_ensemble via extra_members param; method becomes 'tiled+vote' — tiling is one member, never the sole answer"
  - "Single-sample and empty votes always flag needs_review (insufficient_samples/no_samples) — no consensus can be measured"

patterns-established:
  - "ensemble_settings() is the single config reader for (N, budget) — 21-13 RunSettings must construct from it"
  - "_call_with_supported_kwargs: injected callables declare any kwarg subset; real wrappers close over prompt/image"

requirements-completed: [V3-ACC-03, V3-PROD-02]

coverage:
  - id: D1
    description: "vote() median voting with RESEARCH §4 exact thresholds and unanimous/majority/none confidence mapping; vote vectors persisted; historical 397500-vs-1131112 pair pinned as regression"
    requirement: V3-ACC-03
    verification:
      - kind: unit
        ref: "tests/test_ensemble.py#test_vote_ea_unanimous_high..test_vote_vector_persisted_and_serializable (9 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "run_ensemble N=3 fan-out, exactly 5 calls on first-3 disagreement, temperature ladder + cached temperature-ignore probe with prompt-variation fallback"
    requirement: V3-ACC-03
    verification:
      - kind: unit
        ref: "tests/test_ensemble.py#test_run_ensemble_agreeing_stub_makes_exactly_three_calls, #test_run_ensemble_disagreement_escalates_to_exactly_five_calls, #test_temperature_ignored_switches_to_prompt_variation"
        status: pass
    human_judgment: false
  - id: D3
    description: "run_tiled_count with 15–20% overlap and position-based NMS dedup in overlap bands; tiled sum joins the vote as one ensemble member"
    requirement: V3-ACC-03
    verification:
      - kind: unit
        ref: "tests/test_ensemble.py#test_tiled_dedup_suppresses_overlap_duplicates_exactly, #test_run_ensemble_tiled_member_joins_vote"
        status: pass
    human_judgment: false
  - id: D4
    description: "BudgetGuard hard per-run cap: refused charge raises BudgetExceeded without accumulating; run_ensemble aborts to needs_review reason='budget_exhausted' — never silent truncation"
    requirement: V3-PROD-02
    verification:
      - kind: unit
        ref: "tests/test_ensemble.py#test_budget_guard_refuses_charge_past_cap, #test_run_ensemble_budget_exhausted_flags_never_truncates_silently, #test_run_tiled_count_propagates_budget_exceeded"
        status: pass
    human_judgment: false
  - id: D5
    description: "Config additive: API_BUDGET_PER_RUN_USD + ENSEMBLE_N env constants with .env.example docs and conftest determinism pins; ensemble_settings() reader"
    requirement: V3-PROD-02
    verification:
      - kind: unit
        ref: "tests/test_ensemble.py#test_ensemble_settings_reader"
        status: pass
      - kind: other
        ref: "python3 -m pytest -q -m 'not golden' → 706 passed (681 baseline + 25 new)"
        status: pass
    human_judgment: false

# Metrics
duration: 16min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 11: Ensemble Voting & Budget Guard Summary

**N-run self-consistency voting (N=3→5 on disagreement) with persisted vote vectors, tiled counting as an overlap-deduped ensemble member, and a hard BudgetGuard that flags budget_exhausted instead of silently truncating — kills the 397k-vs-1.13M variance failure and caps cost explosion**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-14T16:01:01Z
- **Completed:** 2026-07-14T16:17:05Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- `vote(samples, unit_kind)` implements RESEARCH §4 thresholds exactly: EA accepts when max−min ≤ max(1, 10% of median); SF/LF (raster only) when relative spread ≤ 10%; unanimous→high, majority-within-tolerance→medium, none→low+needs_review. Every `EnsembleResult` carries the full vote vector — disagreement can never silently pass (the 397,500-vs-1,131,112 SF pair is a pinned regression test).
- `run_ensemble(analyze_call, ...)` fans out exactly 3 samples (temperature ladder 0.4/0.55/0.7), escalates to exactly 5 on disagreement, and re-votes. A one-time cached runtime probe compares the first two t-varied payloads; when identical, later samples get a nonzero `prompt_variation` (prompt-ordering/tile-offset diversity fallback per Open Question 3).
- `run_tiled_count` integrates the existing `COUNT_TILING` machinery: `count_tiling_grid()` tiles with 17.5% overlap rendered via `render_clip_crop` (shared zoom primitive), coarse grid-cell positions, position-based NMS suppressing detections seen by both tiles inside the overlap band. The sum joins `run_ensemble` votes via `extra_members` (method `'tiled+vote'`) — one member, never the sole answer.
- `BudgetGuard` (thread-safe) + `BudgetExceeded`: charges the `_cost_usd` stamp of every completed call; a charge past the cap is refused WITHOUT accumulating, sampling stops, and the current-best result returns flagged `needs_review` reason `"budget_exhausted"` — never a silent partial (Pitfall 7 policy verbatim). An already-exhausted guard makes zero API calls.
- Config strictly additive: `API_BUDGET_PER_RUN_USD` (float env, default 10.0) and `ENSEMBLE_N` (int env, default 3) in config.py, documented in .env.example, pinned in conftest for determinism.
- Zero direct Anthropic client usage in ensemble.py — all API access via the injectable `analyze_call` (20-00 injection pattern), asserted at source level by a test.

## Task Commits

Each task was committed atomically:

1. **Task 1: vote() + BudgetGuard + config** - `e3dd195` (feat)
2. **Task 2: run_ensemble fan-out + tiled counting integration** - `e94443b` (feat)
3. **Task 3: Ensemble tests with stubbed analyzer** - `430d9b0` (test)

## Files Created/Modified

- `src/bobbytailor/vision/ensemble.py` - EnsembleResult, vote, run_ensemble, run_tiled_count, BudgetGuard, BudgetExceeded, ensemble_settings (693 lines)
- `tests/test_ensemble.py` - 25 tests: voting matrix, fan-out/escalation counts, overlap dedup, budget abort, temperature probe (all stubbed, zero API calls)
- `src/bobbytailor/config.py` - additive: API_BUDGET_PER_RUN_USD, ENSEMBLE_N (safe defaults, no new REQUIRED_ENV_VARS)
- `tests/conftest.py` - additive: ENSEMBLE_N=3 + API_BUDGET_PER_RUN_USD=10.0 setdefault pins
- `.env.example` - both new vars documented with budget/ensemble comments

## Decisions Made

- **Acceptance = whole-band OR strict majority:** RESEARCH §4 states both "max−min ≤ tol → accept, else needs_review" and "majority within tolerance → medium". Reconciled as: accept when the whole vector fits the band, OR when a strict majority (> n/2) of samples individually sit within tolerance of the median (the outlier minority loses the vote). This makes 5-sample escalation meaningful (3-of-5 agreement passes at medium) while `[5,9,16]` 3-way disagreement still flags.
- **Refused charge not accumulated:** `BudgetGuard.charge()` raises before adding, so `spent_usd` and the vote vector only ever contain paid-for work — "exactly 2 calls charged" is auditable after an abort.
- **Probe only on dict payloads:** identical scalar samples across temperatures are common legitimate agreement; the temperature-ignore heuristic requires byte-identical metadata-stripped JSON payloads, cached per `probe_key`.
- **Budget-exhausted forces low/needs_review** regardless of how well the paid samples agree — a partially-funded consensus is still a partial result.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The module docstring originally contained the literal string `client.messages` (describing what the module must NOT do), which would have tripped the plan's grep acceptance assertion — reworded to "the Anthropic client" so `grep client.messages ensemble.py` is clean.
- Full-suite run regenerated `tests/fixtures/synthetic/*.pdf` (known side effect); restored via `git checkout --` before committing Task 3.

## Known Stubs

None — all functions fully implemented; tests stub only the injected analyzer callable (the designed injection seam), not module internals.

## User Setup Required

None - no external service configuration required. Optional: tune `API_BUDGET_PER_RUN_USD` / `ENSEMBLE_N` in `.env` (safe defaults 10.0 / 3 apply otherwise).

## Next Phase Readiness

- BudgetGuard + `ensemble_settings()` ready for pipeline-wide enforcement in 21-13 (RunSettings construction) and verify-retry budget-guarding in 21-14.
- `run_ensemble` consumes any residual-path analyzer via injection; the raster fallback and unclusterable-symbol paths can wire it without touching claude_analyzer.
- Full non-golden suite green: 706 passed (681 baseline + 25 new), 2 golden deselected.

## Self-Check: PASSED

- Created files exist on disk (ensemble.py, test_ensemble.py) ✓
- Task commits e3dd195 / e94443b / 430d9b0 present in git log ✓
- All task acceptance criteria re-verified (vote matrix, 3/5 call counts, budget_exhausted, grep-clean) ✓
- `python3 -m pytest tests/test_ensemble.py -q` → 25 passed ✓
- `python3 -m pytest -q -m "not golden"` → 706 passed ✓

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*
