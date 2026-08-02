---
phase: 22
slug: production-restructure-cleanup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-02
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Python 3.9, macOS system python3) |
| **Config file** | pytest.ini (gains `addopts = -m "not golden"` in Step 1) |
| **Quick run command** | `python3 -m pytest -q -m "not golden" tests/<targeted files>` |
| **Full suite command** | `python3 -m pytest -q -m "not golden"` |
| **Estimated runtime** | ~465 seconds full suite (baseline 1132 passed, 2 deselected) |

**FORBIDDEN:** `pytest -m golden`, `scripts/accuracy_gate.sh`, `scripts/vision_only_benchmark.py`, `scripts/golden_convergence.py` — paid API credits, user-authorized only.

---

## Sampling Rate

- **After every task commit:** Run targeted quick command for touched test files (solo-file runs for the 3 stub files after isolation changes)
- **After every plan wave:** Run full suite (`python3 -m pytest -q -m "not golden"`)
- **Before `/gsd-verify-work`:** Full suite must be green at 1132 passed / 2 deselected
- **Max feedback latency:** 480 seconds

---

## Per-Task Verification Map

*Filled by the planner per PLAN.md task. Non-suite validations established by RESEARCH.md §Validation Architecture:*

| Behavior | Automated Command |
|----------|-------------------|
| Golden tests deselected by default | `python3 -m pytest --collect-only -q \| tail -3` → shows "2 deselected" |
| Suite writes nothing to real output/ | `ls output/ \| wc -l` before/after full suite → identical counts; `test ! -d MagicMock` |
| learning.db intact post-cleanup | `sqlite3 output/learning.db ".tables"` lists tables; same for stackct.db |
| Must-survive dirs intact | keep-list script `--verify` mode: every §4.3 name exists |
| Web app serves after asset move | Flask `test_client()` python one-liner: GET /login 200, static asset 200 (no live server) |
| Reports pairing intact | test_client GET /api/reports → kept runs listed; GET a sheet-image URL → 200 |
| Zip integrity before original removal | `unzip -t output/_archive/stackct-era-20260802.zip` exit 0 |
| No dangling doc refs after moves | `grep -rn "design-system/" --include="*.py" --include="*.js" --include="*.css" --include="*.html" src static templates scripts` → empty (moved-path greps per step) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements — the 1132-test offline suite plus the
non-suite commands above. No new test framework or stub files needed; Step 1 modifies
conftest.py and 3 existing test files (isolation only, no new test surface).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Browser click-through after dead-JS removal | §5 Step 7 | Console errors only visible in a real browser | Load dashboard/reports/settings in browser pane, check console clean (may be executed via the in-app Browser tools rather than a human) |

All other phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 480s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
