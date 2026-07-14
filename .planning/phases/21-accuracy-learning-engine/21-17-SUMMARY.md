---
phase: 21-accuracy-learning-engine
plan: 17
subsystem: testing
tags: [benchmark, accuracy-gate, provenance, reproducibility, ci, plans-only]

requires:
  - phase: 21-13
    provides: takeoff.json per-item provenance, budget block, fusion_rejected audit
  - phase: 21-15
    provides: plans-only entry points (no companion/manifest auto-discovery)
  - phase: 21-16
    provides: learning retrieval seams (why gate runs pin LEARNING_DB_PATH)
provides:
  - CI-invocable plans-only accuracy gate (V3-PROD-01) with explicit ground-truth args
  - score_with_provenance: geometry/text qty accuracy split, vision_qty_share, silent_misses
  - check_reproducibility: per-item deltas, 5% boundary, one-sided-item failure
  - scripts/accuracy_gate.sh: one-command gate over the four uploads/ pairs
  - Planted-decoy isolation assertion (regression tripwire for companion auto-discovery)
affects: [21-18, accuracy-gate, verify-work, live-testing]

tech-stack:
  added: []
  patterns:
    - "Explicit ground truth only: --takeoff-pdf/--golden args; runtime can never discover the reference"
    - "Planted-decoy isolation: devtools finder must SEE the decoy; pipeline result must show zero traces"
    - "Gate runs pin LEARNING_DB_PATH to a fresh temp DB — cold-pipeline, machine-independent scores"

key-files:
  created:
    - scripts/accuracy_gate.sh
    - tests/test_benchmark_scoring.py
  modified:
    - scripts/vision_only_benchmark.py

key-decisions:
  - "Planted-decoy isolation replaces the empty-tempdir check: a sentinel sibling take-off is planted, asserted discoverable by the devtools finder, and the pipeline result is asserted leakage-free (no companion-legend rows, no sentinel values)"
  - "--takeoff-pdf golden rows: EA units score exact-or-within-1; measured units get ±5% tolerance (matches the phase reproducibility band)"
  - "geometry_text_qty_acc is None when no deterministic-provenance items exist — and None FAILS the gate (cannot certify 97% without evidence)"
  - "vision_qty_share denominator = ALL quantity-bearing summary rows; any vision_ensemble involvement (incl. mixed) counts toward the share"
  - "Silent-miss coverage: flagged counts as covered — needs_review rows (relaxed 0.45 token overlap or review_reasons superset, light plural folding) and fusion_rejected audit entries"
  - "Reproducibility delta = |qa-qb|/max(|qa|,|qb|); exact 5% boundary passes (≤); item present in only one run fails"
  - "Cost baseline: record-on-absent into scripts/.cost_baseline.json, warn (never fail) at >2x; delete the file to re-baseline"
  - "--with-learning turns every run tracking-only labeled learned-assisted and always exits 0 — learned scores can never gate"
  - "--budget sets API_BUDGET_PER_RUN_USD so RunSettings.from_env() threads it into the BudgetGuard"

patterns-established:
  - "Gate scripts export LEARNING_DB_PATH to mktemp before any pipeline invocation"
  - "Benchmark CLI exit codes: 0 pass/tracking-only, 1 gate failure, 2 usage error"

requirements-completed: [V3-PROD-01]

coverage:
  - id: D1
    description: "vision_only_benchmark.py upgraded: explicit --takeoff-pdf/--golden ground truth, score_with_provenance (geometry/text split, vision_qty_share, silent_misses, per-item provenance table), check_reproducibility, threshold flags with RESEARCH defaults, --report-json, --budget, planted-decoy isolation"
    requirement: "V3-PROD-01"
    verification:
      - kind: unit
        ref: "tests/test_benchmark_scoring.py (27 tests: TestScoreWithProvenance, TestReproducibility, TestGateThresholds, TestCliPlumbing, TestTakeoffPdfIngestion)"
        status: pass
      - kind: other
        ref: "python3 scripts/vision_only_benchmark.py --help (shows --takeoff-pdf, --repro, --min-geometry-acc)"
        status: pass
    human_judgment: false
  - id: D2
    description: "scripts/accuracy_gate.sh: one-command CI gate — Crow+Bob hard gate with --repro, Chelsea+Moxy --tracking-only, LEARNING_DB_PATH isolation, cost-regression warning, summary table, exit reflects gating projects only"
    requirement: "V3-PROD-01"
    verification:
      - kind: unit
        ref: "tests/test_benchmark_scoring.py#TestGateScript (syntax, filenames, gating split, isolation ordering, cost baseline)"
        status: pass
      - kind: other
        ref: "bash -n scripts/accuracy_gate.sh; offline smoke of the embedded summary/cost-regression block"
        status: pass
    human_judgment: false
  - id: D3
    description: "Live budget-guarded gate run on the four uploads/ projects (Task 3 checkpoint) — certifies waves 1-8 integration on real API calls"
    requirement: "V3-PROD-01"
    verification: []
    human_judgment: true
    rationale: "Spends real API credits (single-digit USD; Crow+Bob double-run for repro). Only a human can authorize the spend, run `bash scripts/accuracy_gate.sh`, and review the summary table against the thresholds. Executor is forbidden from live API invocation by the phase test architecture."

duration: 20min
completed: 2026-07-14
status: complete
---

# Phase 21 Plan 17: Plans-Only Accuracy Gate Summary

**CI-invocable plans-only accuracy gate: explicit --takeoff-pdf ground truth, per-provenance accuracy splits, zero-silent-miss + ±5% reproducibility assertions, and a one-command accuracy_gate.sh with learning-isolated cold-pipeline scoring (V3-PROD-01)**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-14T19:37:55Z
- **Completed:** 2026-07-14T19:58:02Z
- **Tasks:** 2 of 3 executed (Task 3 is a blocking human-verify checkpoint — live API spend)
- **Files modified:** 3

## Accomplishments

- **Explicit ground truth, no discovery:** `--takeoff-pdf` parses the human take-off PDF via the devtools companion parser into golden rows (EA → exact-or-within-1, measured → ±5%); exactly one of `--golden`/`--takeoff-pdf` is required. The runtime pipeline can never discover the reference.
- **Strengthened isolation (regression tripwire):** every run plants a sentinel decoy sibling take-off in the isolated tempdir, asserts the devtools finder CAN see it, then asserts the pipeline result contains zero companion-legend rows and no sentinel values — a regression re-introducing sibling auto-discovery fails loudly.
- **Provenance-split scoring:** `score_with_provenance` computes `geometry_text_qty_acc` over items backed exclusively by {geometry, text_layer, schedule_table} provenance (from the 21-13 raw_line_items fields), `vision_qty_share` over all quantity-bearing rows, `silent_misses` (golden categories neither present nor flagged — needs_review rows and fusion_rejected audit entries count as covered), and a per-item table with provenance class.
- **Reproducibility check:** `check_reproducibility` matches quantity-bearing rows by normalized name across two fresh-tempdir runs; symmetric relative deltas, max/mean reported, exact 5% boundary passes, one-sided items fail.
- **Gate evaluation:** threshold flags with RESEARCH §8 defaults (`--min-geometry-acc 0.97 --min-overall-acc 0.90 --min-item-found 0.95 --max-vision-share 0.05`); None metrics fail (cannot certify); `--report-json` writes the full CI artifact; exit 1 on any gate failure, `--tracking-only` never fails.
- **accuracy_gate.sh:** one command runs all four uploads/ pairs with exact quoted filenames (incl. the "Take offds" typo) — Crow+Bob hard gate with `--repro`, Chelsea+Moxy tracked; `export LEARNING_DB_PATH="$(mktemp -d)/gate_learning.db"` before any invocation so scores are cold-pipeline and machine-independent; `--with-learning` records a separate, never-gating learned-assisted run; cost-regression warning at >2× the recorded baseline in `scripts/.cost_baseline.json`; final summary table; exit code reflects gating projects only.
- **27 offline tests** (zero API calls) pin the scoring math, coverage rules, 5% boundary, threshold plumbing (0.96 < 0.97 fails), CLI exit codes, take-off-PDF ingestion, and gate-script structure. Full suite: **833 passed** (806 baseline + 27 new).

## Task Commits

Each task was committed atomically:

1. **Task 1: Benchmark upgrade — explicit ground truth + provenance scoring** - `163f0ef` (feat)
2. **Task 2: accuracy_gate.sh + offline scoring tests** - `7591e97` (test)
3. **Task 3: Run the budget-guarded accuracy gate** - NOT RUN (blocking `checkpoint:human-verify` — spends API credits; awaiting human)

## Files Created/Modified

- `scripts/vision_only_benchmark.py` - Plans-only benchmark → CI gate: explicit ground-truth args, provenance-split scoring, reproducibility, gate thresholds, report-json, budget, planted-decoy isolation
- `scripts/accuracy_gate.sh` - One-command gate over the four uploads/ pairs with learning isolation and cost-regression warning
- `tests/test_benchmark_scoring.py` - 27 offline tests pinning scoring math, gates, CLI plumbing, and gate-script structure

## Decisions Made

See `key-decisions` frontmatter — most notable: planted-decoy isolation (the old empty-tempdir assertion could not catch a re-introduced auto-discovery; the decoy proves discoverable-yet-unread), None-fails gate semantics (an uncertifiable metric can never pass), and flagged-counts-as-covered silent-miss rules (the pipeline pointing a human at a category is the honest opposite of a silent miss).

## Deviations from Plan

None - plan executed exactly as written. (Backward compatibility with `scripts/score_report_dir.py`, which imports `_load_golden`/`score`/`report_text`, was preserved — signatures unchanged, `report_text` renders both base and provenance-extended scoring dicts.)

## Issues Encountered

None. The synthetic fixture PDFs (`tests/fixtures/synthetic/*.pdf`) regenerated as a known test side effect and were restored before committing.

## User Setup Required

None - no external service configuration required. The live gate run (Task 3) requires `ANTHROPIC_API_KEY` with credit — see Next Phase Readiness.

## Next Phase Readiness

- **PENDING HUMAN CHECKPOINT (Task 3, blocking):** run `bash scripts/accuracy_gate.sh` (expected cost single-digit USD; Crow+Bob gating incl. reproducibility double-run; Chelsea+Moxy tracked). Verify: geometry/text accuracy ≥97% on Crow+Bob, overall ≥90%, item-found ≥95%, zero silent misses, repro ≤5%. Check ANTHROPIC_API_KEY credit first (Phase 20 was blocked on this).
- If a gate fails, the per-layer design localizes it: scale wrong → layer 2 (21-07), wall/room quantity wrong → layer 1 (21-10), provenance leakage → layer 3 (21-12/13).
- 21-18 (final plan) can proceed once the gate run is reviewed.

## Self-Check: PASSED

- FOUND: scripts/vision_only_benchmark.py
- FOUND: scripts/accuracy_gate.sh
- FOUND: tests/test_benchmark_scoring.py
- FOUND: commit 163f0ef (Task 1)
- FOUND: commit 7591e97 (Task 2)
- Full non-golden suite: 833 passed, 0 failed (exit 0)

---
*Phase: 21-accuracy-learning-engine*
*Completed: 2026-07-14*
