---
phase: 21
slug: accuracy-learning-engine
status: draft
nyquist_compliant: false
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
| *(filled by planner — every task must map to one of the 5 layers above)* | | | | | | | | | ⬜ pending |

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
