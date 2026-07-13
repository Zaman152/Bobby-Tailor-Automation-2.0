# Masterv2.md Gap Analysis

**Date:** 2026-05-26  
**Source of truth:** `Masterv2.md` v2.0 + Addendum v2.1 (Appendix C)  
**Compared against:** Implemented codebase + `.planning/ROADMAP.md` phases 1–15

## Executive summary

| Masterv2 scope | Roadmap coverage | Remaining gap |
|----------------|------------------|---------------|
| §6 Gaps 1–10, §7 Phases 1–3 (critical UX) | Phases 1–14 (mostly complete per STATE) | UX polish only (Phase 15) |
| §8 UI/UX redesign | Phase 8–10 + **Phase 15** (6 plans exist) | Execute Phase 15 |
| §7 Phase 4 (EST/AUTO/EXP) | v2 deferred in ROADMAP | Out of v1 scope |
| **Addendum v2.1 (Gaps A–G)** | **Not mapped** | **Phase 16 (new)** |

**Bottom line:** Functional and UX gaps from Masterv2 §6–8 are already phased (1–15). The **new** work in `Masterv2.md` is the **v2.1 accuracy addendum** — cross-references, spec-table classification, consolidated StackCT-style output, and civil/site extraction. That requires **Phase 16: Takeoff Accuracy (v2.1)**.

---

## §6 Known gaps — status vs codebase

| Gap | Masterv2 description | Phase / status |
|-----|----------------------|----------------|
| 1 | Project list truncation | Phase 2 FOUND-04 — scroll/lazy load in `browser.py` |
| 2 | No plan selection before run | Phase 4, 9, 14 — APIs + UI + plan sets |
| 3 | No in-browser report preview | Phase 5, 10 — preview APIs + accordion UI |
| 4 | Screenshot fixed sleep | Phase 2 FOUND-03 — canvas pixel-hash stability |
| 5 | No per-sheet progress | Phase 7 — job monitor + callbacks |
| 6 | No cost tracking | Phase 3 — `api_usage` in reports |
| 7 | PDF page selection | Phase 11 — page checkboxes |
| 8 | Hardcoded `.env` path | Phase 1 FOUND-01 — project-relative `.env` |
| 9 | No auth | Phase 12 — Flask sessions + bcrypt |
| 10 | Stack traces in API | Phase 1 FOUND-02 — sanitized errors |

**Verdict:** §6 items are **addressed in roadmap/implementation**. Remaining pain is **UX quality** (preview vs download confusion) → Phase 15.

---

## §7 Feature upgrade plan — status

| Masterv2 phase | Features | Roadmap |
|----------------|----------|---------|
| Phase 1 | Plan selection, report preview, config path | Phases 4, 5, 1 |
| Phase 2 | Cost, canvas stability, project scroll | Phases 3, 2 |
| Phase 3 | Full UI overhaul (§8) | Phases 8–11, **15** |
| Phase 4 | Confidence review, waste profiles, cron, Excel | v2 (`EST-*`, `AUTO-*`, `EXP-01`) |

---

## §8 UI/UX spec — status

| Spec area | Implemented (baseline) | Phase 15 upgrade |
|-----------|------------------------|------------------|
| Sidebar layout | `index.html` + `static/app.js` | Tokens, Lucide, polish |
| Projects + plan sets | Phase 14 two-step flow | Guided stepper (UX-07) |
| Job monitor | Dedicated page + sidebar card | Motion + layout (UX-08) |
| Reports preview | Inline accordion + tabs | Full-screen workspace (UX-03–06) |
| PDF upload | Upload + page selection | Visual parity (UX-12) |
| Settings | `settings.html` | Glass card + tests (UX-12) |

Phase 15 plans: `15-01` … `15-06` in `.planning/phases/15-premium-ui-ux-revamp/`.

---

## Addendum v2.1 — CRITICAL gaps (not in phases 1–15)

Evidence: three construction screenshots (civil cross-refs, manufacturer spec tables, StackCT consolidated output).

| ID | Gap | Code today | Impact |
|----|-----|------------|--------|
| **A** | Cross-reference link following | Prompt has no `cross_references[]`; no resolver in `scraper.py` | Missing specs for structures referenced to other sheets (e.g. BB CI#2 → C-4) |
| **B** | Spec tables ≠ takeoff schedules | All tables → `schedule` → `_calculate_from_schedule()` | Wrong quantities from manufacturer lookup tables |
| **C** | Output not consolidated | `calculations.csv` is per-sheet rows | Does not match StackCT summary (Striping 7,063 LF total) |
| **D** | Missing civil/site tables | No `storm_pipe`, `catch_basin`, `striping`, etc. in `ESTIMATION_TABLES` | Site/civil quantities missing or misclassified |
| **E** | Invert/GL as measurements | `_parse_numeric` may accept `845.0` from elevations | Phantom calculations from survey data |
| **F** | ± tolerance not flagged | No `approximate` field in pipeline | Estimator cannot see field-verify items |
| **G** | Pipe slope as quantity | `%` may become measurement value | e.g. 4.81% counted as quantity |

**New artifacts required (per Masterv2 §C.9):**

- `aggregator.py` — project-level `takeoff_summary`
- `takeoff_summary.csv` — StackCT-format export
- `specification_tables` in report JSON / `spec_tables.json`
- Revised `EXTRACTION_PROMPT` with `pipe_runs[]`, `civil_structures[]`, `table_purpose`
- Cross-reference resolution pass after all sheets analyzed

---

## Recommended execution order

```
Phases 1–14  (done / in progress per STATE)
    ↓
Phase 15     Premium UI/UX (Masterv2 §8 — execute existing plans)
    ↓
Phase 16     Takeoff Accuracy v2.1 (Masterv2 Addendum — NEW)
    ↓
v2 backlog   ARCH-01, EST-02, AUTO-*, EXP-01
```

**Why Phase 16 after 15:** Consolidated summary and spec tables need a clear preview surface (Phase 15 workspace). Core accuracy work (16-01–04) can run in parallel with 15 wave 1 if needed, but UAT for summary tab fits 15-03 + 16-05.

---

## Traceability to new requirements

See `REQUIREMENTS.md` — **ACCURACY-01** through **ACCURACY-12** mapped to Phase 16 plans.

---

*Generated by `/gsd-plan-phase` gap analysis against Masterv2.md*
