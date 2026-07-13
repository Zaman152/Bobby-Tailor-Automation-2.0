---
phase: 21
slug: accuracy-learning-engine
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-13
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from 21-RESEARCH.md §8 "Validation Architecture" — 5 layers; only layer 5 spends API credits.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (existing; 348 deterministic tests green) |
| **Config file** | `tests/conftest.py` |
| **Quick run command** | `python3 -m pytest tests/ -x -q -m "not golden"` |
| **Full suite command** | `python3 -m pytest tests/ -q -m "not golden"` |
| **Estimated runtime** | ~60 seconds (deterministic layers only) |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest <touched test modules> -x -q`
- **After every plan wave:** Run `python3 -m pytest tests/ -q -m "not golden"`
- **Before `/gsd-verify-work`:** Full deterministic suite green + budget-guarded layer-5 accuracy gate (`scripts/vision_only_benchmark.py`) on Crow + Bob
- **Max feedback latency:** 90 seconds

---

## Validation Layers (from 21-RESEARCH.md §8)

1. **Geometry engine** — pure unit tests against fixture PDFs + synthetic PyMuPDF-generated fixtures (free)
2. **Scale solver** — per-viewport solve vs hand-recorded `scale_truth.json` truth tables; no HIGH-confidence wrong scales (free)
3. **Fusion layer** — record/replay Claude structured-output responses injected via `TakeoffPipeline(analyzer=...)`; provenance rules asserted (free)
4. **Learning store** — correction→distill→retrieval round-trips; anti-amplification guardrail; repeat-run application (free)
5. **End-to-end accuracy gate** — `scripts/vision_only_benchmark.py` on Crow+Bob: geometry/text-derived ≥97%, overall ≥90%, item-found ≥95%, zero silent misses, two-run reproducibility ±5% (API, budget-guarded)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-T1..T3 | 21-01 | 1 | V3-STRUCT-01 | auth/CSRF regression | git mv 100% renames; suite green through shims | regression (all layers) | `python3 -m pytest tests/ -q -m "not golden"` | ⬜ | ⬜ pending |
| 02-T1..T3 | 21-02 | 2 | V3-STRUCT-01 | auth bypass, CSRF, traversal | route/decorator parity gate | regression | `python3 -m pytest tests/test_blueprint_parity.py -q` | ⬜ | ⬜ pending |
| 03-T1..T3 | 21-03 | 2 | V3-ACC-01/02 | untrusted PDF caps, ReDoS | grammar-verified pairing, drop-don't-guess | layer 1 | `python3 -m pytest tests/test_dimensions.py -q` | ⬜ | ⬜ pending |
| 04-T1..T3 | 21-04 | 2 | V3-LEARN-01/02 | SQL injection (parameterized-only) | injection probe test | layer 4 | `python3 -m pytest tests/test_learning_store.py -q` | ⬜ | ⬜ pending |
| 05-T1..T3 | 21-05 | 2 | V3-ACC-04 | API-key log hygiene | no-key-in-logs grep | layer 3 (routing) | `python3 -m pytest tests/test_sheet_pass_matrix.py -q` | ⬜ | ⬜ pending |
| 06-T1..T3 | 21-06 | 3 | V3-ACC-01 | resource caps, cell sanitization | 200k primitive cap; cell caps | layer 1 | `python3 -m pytest tests/test_symbols.py tests/test_tables.py -q` | ⬜ | ⬜ pending |
| 07-T1..T3 | 21-07 | 3 | V3-ACC-02 | no HIGH-confidence-wrong scales | confidence rubric conjunction | layer 2 | `python3 -m pytest tests/test_scale_solver.py -q` | ⬜ | ⬜ pending |
| 08-T1..T3 | 21-08 | 3 | V3-ACC-01/04 | prompt-injection delimiters; no numeric fields | schema no-numbers walk | layer 3 | `python3 -m pytest tests/test_vision_schemas.py -q` | ⬜ | ⬜ pending |
| 09-T1..T2 | 21-09 | 3 | V3-LEARN-01 | injection (no raw SQL), amplification warning | capture best-effort isolation | layer 4 | `python3 -m pytest tests/test_learning_capture.py -q` | ⬜ | ⬜ pending |
| 10-T1..T3 | 21-10 | 4 | V3-ACC-01 | polygonize caps | footprint dual-method cross-check | layer 1 | `python3 -m pytest tests/test_walls.py tests/test_rooms.py -q` | ⬜ | ⬜ pending |
| 11-T1..T3 | 21-11 | 4 | V3-ACC-03, V3-PROD-02 | budget cap, no silent partials | budget_exhausted flag path | layer 3 | `python3 -m pytest tests/test_ensemble.py -q` | ⬜ | ⬜ pending |
| 12-T1..T3 | 21-12 | 5 | V3-ACC-01 | grounding bypass rejection | fusion_rejected audit | layer 3 | `python3 -m pytest tests/test_fusion.py -q` | ⬜ | ⬜ pending |
| 13-T1..T3 | 21-13 | 6 | V3-ACC-01/03 | budget threading, per-sheet degradation | provenance invariant at pipeline level | layer 3 | `python3 -m pytest tests/test_pipeline_deterministic.py -q` | ⬜ | ⬜ pending |
| 14-T1..T2 | 21-14 | 7 | V3-ACC-05 | retry caps, no flag suppression | retry_history mandatory | layer 3 | `python3 -m pytest tests/test_verify_retry.py -q` | ⬜ | ⬜ pending |
| 15-T1..T3 | 21-15 | 7 | V3-STRUCT-02, V3-LEARN-04 | ground-truth leakage isolation | companion never opened spy test | layer 3 | `python3 -m pytest tests/test_pipeline_parity.py -q` | ⬜ | ⬜ pending |
| 16-T1..T3 | 21-16 | 8 | V3-LEARN-02/03/04 | anti-amplification guardrail | HIGH-confidence quantity survives contradiction | layer 4 | `python3 -m pytest tests/test_learning_retrieval.py -q` | ⬜ | ⬜ pending |
| 17-T1..T2 | 21-17 | 9 | V3-PROD-01 | plans-only isolation in gate | planted-sibling not read | layer 5 scoring (offline) | `python3 -m pytest tests/test_benchmark_scoring.py -q` | ⬜ | ⬜ pending |
| 17-T3 | 21-17 | 9 | V3-PROD-01 | budget-guarded API spend | gate thresholds | layer 5 (API, checkpoint) | `bash scripts/accuracy_gate.sh` | ⬜ | ⬜ pending |
| 18-T1..T3 | 21-18 | 10 | V3-PROD-02, V3-STRUCT-01 | docs no-secrets; mechanical migration | suite green per batch | regression + manual UAT | `python3 -m pytest tests/ -q -m "not golden"` | ⬜ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/fixtures/*/scale_truth.json` — hand-recorded per-viewport scale truth tables (Crow, Bob minimum)
- [ ] Record/replay analyzer fixture harness (recorded structured-output responses per prompt hash)
- [ ] Synthetic geometry fixture generator (PyMuPDF `Shape`-drawn walls/dims/symbols with known truth)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live-testing readiness sign-off (21-UAT.md) | V3-PROD-02 | Human judgement on demo-grade UX and docs | Run UAT script in 21-UAT.md |
| Learning-loop UX (verify → correction persisted → repeat run applies it) | V3-LEARN-01..03 | End-to-end flow through the web UI | Verify a run in UI, re-run same project, confirm applied corrections badge |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (Wave 0 artifacts: synthetic generator → 21-03, scale_truth.json → 21-07, replay harness → 21-12)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task carries a pytest/CLI verify; only 17-T3 and 18-T3 are human checkpoints)
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s (deterministic suite ~60s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (checker)
