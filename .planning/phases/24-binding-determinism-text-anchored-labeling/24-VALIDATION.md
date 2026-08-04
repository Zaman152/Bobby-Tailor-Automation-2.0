---
phase: 24
slug: binding-determinism-text-anchored-labeling
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-05
---

# Phase 24 — Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Python 3.9, macOS system python3) |
| **Config** | pytest.ini — `addopts = -m "not golden"` (paid tests excluded by default since Phase 22) |
| **Quick run** | `python3 -m pytest -q tests/<targeted file>` |
| **Full suite** | `python3 -m pytest -q` |
| **Baseline** | **1944 passed, 1 skipped, 2 deselected** (~46 min) |

**FORBIDDEN — spends real money:** `pytest -m golden`, `scripts/accuracy_gate.sh`,
`scripts/vision_only_benchmark.py`, `scripts/golden_convergence.py`. Every plan asserts their
absence with a prohibition grep returning 0.

## Sampling Rate

- **Per task:** targeted pytest for the touched module.
- **Per plan, before every commit:** full suite + `tests/test_phase23_acceptance.py` +
  `tests/test_four_set_coverage.py`.
- **Max feedback latency:** ~46 min (full suite).

## Wave 0

**Existing infrastructure covers this phase.** No new framework needed. Wave 0 is complete because
the two prerequisite harnesses already exist and are green: the phase-23 acceptance gate and the
four-plan-set coverage gate. `tests/test_vision_schemas.py` already covers the schema and overlay
surfaces that 24-07 extends — the research's proposal to add `test_schemas.py` / `test_overlay.py`
was rejected during planning to avoid splitting one contract across three files.

## Per-Task Verification Approach

Every task in all 10 plans carries an `<automated>` command; no task relies on manual inspection.
The phase-specific verifications beyond the suite:

| Behaviour | Free automated check |
|---|---|
| Determinism (criterion 5) | `tests/test_determinism_harness.py` — two-variant differential holding geometry fixed while varying the model's schema-legal answers (run 1's labels vs run 2's), asserting the published item set is invariant. **The literal "run N× and assert identical" is vacuous** — `ReplayAnalyzer` keys on SHA256(model, pass_type, prompt, image_count), so N× on one fixture is identical by construction. |
| The gate actually detects a flip | 24-09 task 3 poisons a third variant with a deliberate naming flip and asserts the gate FAILS; the poisoned fixture must not be committed. |
| No numeric field in a vision schema | Walk every vector-path schema builder; assert `'integer' in t or 'number' in t` is `False`. |
| Coincidence trap fenced | grep new tests for `== 28\|== 132\|== 136\|== 56` → must return 0. |
| Unnamed geometry has its own key | `fusion_rejected` occurrence count must NOT increase (protects C3a reinstatement). |
| Paid-run evidence untouched | `git status --porcelain .planning/paid-run-evidence/ \| wc -l` → 0. |
| Classification/scale changes | four-plan-set gate: Moxy 2, Crow 0, Bob's 1, Chelsea 0. |

## Manual-Only Verifications

None. All phase behaviours have automated, free verification.

## Explicitly NOT a success signal

The naive accuracy percentage is expected to **DROP** when the unnamed-geometry contract lands
(`SYM-*`, `ROOM-*` and an item literally named `"4"` stop publishing as line items). That is the
correct outcome and mirrors the phase-23 rails precedent. No `must_haves` truth in any plan is a
score delta, and 24-03/24-04 require the re-score be RECORDED and not acted upon.

## Sign-Off

- [x] All tasks have `<automated>` verify
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 needs nothing new
- [x] No watch-mode flags
- [x] `nyquist_compliant: true`

**Approved:** 2026-08-05 (orchestrator; W1 from the plan-checker resolved by authoring this file
rather than accepting the phase-23 precedent)
