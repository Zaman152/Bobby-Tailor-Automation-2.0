# Phase 21: Accuracy & Learning Engine (v3) - Context

**Gathered:** 2026-07-13
**Status:** Ready for planning
**Source:** Direct user directives (upgrade brief) + full codebase accuracy analysis

<domain>
## Phase Boundary

Transform the take-off app from a manifest-assisted, vision-guessing pipeline into a plans-only, self-improving production system. In real client scenarios the ONLY input is the plan PDF (uploaded directly or pulled from StackCT) — no companion take-off PDFs, no golden CSVs, no hand-written manifests. The app must analyze all plans, auto-detect drawing scale, extract complete details, calculate quantities with maximum achievable accuracy, minimize human intervention to reviewing a small flagged subset, and learn from every human verification so that accuracy improves over time and manifest data is accumulated automatically instead of supplied by files.

In scope: measurement engine (vector-first), scale detection v2, ensemble vision extraction, model routing upgrade, human-verification learning store + runtime retrieval, package restructure, entry-point parity, plans-only accuracy gate, live-testing readiness.

Out of scope: FastAPI migration (ARCH-01, v2), Celery/Redis queue (ARCH-02), Excel export, multi-user SaaS, custom ML symbol training (zero-shot Claude Vision remains the extractor — learning is retrieval/context-based, not model fine-tuning).

</domain>

<decisions>
## Implementation Decisions

### Input contract (LOCKED)
- Production input is ONLY plan PDFs: direct upload or StackCT scrape. No helper take-offs, no golden takeoffs, no manifest files in real scenarios.
- Companion take-off ingestion (`companion_takeoff.py`) and object manifests (`object_manifest.py`) are demoted to optional dev/benchmark inputs. The production code path must not require them.

### Accuracy strategy (LOCKED — PRIMARY GOAL, sharpened by user 2026-07-13)
- **The goal is 100% accurate output from the plan PDF alone — no manifest, no companion take-off, no manual calibration, no human intervention in the extraction/measurement loop.** The app must detect EVERYTHING in the plan automatically (every item, count, measurement, size) and calculate with full accuracy. Nothing left out.
- **The technical thesis: AI vision + vector geometry combined so each does only what it is provably good at.** Vector geometry is deterministic and mathematically exact given scale — it must be the measurement engine on every vector PDF (~68k geometry items/sheet on fixtures). Numbers printed on the drawing (dimension strings, schedule cells, legend quantities, sizes) must be READ from the text layer deterministically, never estimated. AI vision is the semantic engine only: what is this region/symbol/room, which viewport is the main plan, what does this legend row mean — never the source of a quantity that geometry or text can provide.
- **Scale must be derived automatically with zero calibration**: dimension strings on the drawing give exact distance-in-feet between two geometric points → scale is solvable deterministically per viewport (cross-validated across many dimension strings + standard elements like 3'-0" doors). Printed scale notation is a cross-check, not the primary source. Multi-scale sheets (main plan vs detail callouts) must resolve per-viewport — known failure: frequency-based dominant scale picks detail scales; self-calibration landed 1"=24' vs true ~1"=20'.
- Every printed quantity on the plan (schedules, keynotes, legends, dimension callouts) is authoritative ground truth extracted from the PDF text layer — vision only helps locate/structure it.
- Ensemble/self-consistency for the residual cases where vision must produce a number (raster-only PDFs, symbol counting): N-run voting + tiled counting with dedup; agreement-based confidence. Known failure: run-to-run variance (397,500 SF vs 1,131,112 SF for the same item on identical runs) is unacceptable.
- Integrate higher/stronger models where they measurably help (user explicitly authorized higher-model cost). Route by sheet complexity; keep per-run cost visible and budget-guarded.
- Where a value genuinely cannot be established deterministically, it is still emitted with an explicit flag rather than silently guessed — but the design target is that flagged items approach zero on vector CAD PDFs.

### Learning behaviour (LOCKED — core user requirement)
- Every human verification (quantity correction, item rename, scale fix, wall height, missed item) is persisted to a durable learning store (SQLite — extend `stackct.db` or dedicated `learning.db`), keyed so it can be retrieved for future runs (project, project_type, sheet_type, item pattern).
- On each new run, relevant learned data is retrieved and applied: injected into prompts as hints, used by aggregation naming, and used for calculator assumptions.
- Over time the system accumulates what manifests used to provide (item vocabulary, units, wall heights, scales, expected-item checklists per project type) — "it should learn all manifest data". Auto-generate an internal manifest from verified runs; never require the user to supply one.
- Existing per-run `verification_overrides.json` / `scale_calibration.json` / `takeoff_measurements.json` flows are the capture surface — they must now feed the learning store instead of dying with the run folder.

### Structure (LOCKED)
- Restructure the 30 flat root modules into a proper package with clear boundaries (e.g. `src/bobbytailor/` or equivalent: pipeline, vision, scale, deterministic, learning, scrape, web/blueprints). Split the 1,817-line `app.py` into Flask blueprints. All existing tests must pass after the move.
- Each file properly integrated — no dead/experimental modules left in the production tree (dev scripts stay under `scripts/`).

### Process (LOCKED)
- Full app already pushed to GitHub (`Zaman152/Bobby-Tailor-Automation-2.0`, commit a715681) before the upgrade starts — keep pushing at meaningful milestones.
- Endpoint parity: StackCT path and PDF path must behave identically (StackCT currently hardcodes `companion_present=False` and skips manifest/companion logic — asymmetry must be eliminated by making both paths plans-only + learning-driven).
- Ready for live testing at phase end: 21-UAT.md, deployment docs, error recovery, cost guards.

### Claude's Discretion
- Exact package name/layout and blueprint split.
- Learning store schema design (tables, keys, confidence weighting, conflict resolution between learned values and fresh extraction).
- Ensemble size N, voting rules, and when tiled counting activates.
- Which model slugs to route where (verify current Anthropic model line-up during research; config-driven, not hardcoded).
- How to segment vector geometry semantically (room polygons, wall segments) — choose pragmatic techniques over research-grade CV.
- Whether "100% accuracy" claims are framed as completeness-guarantee + flagged-quantity review (the honest framing already established in reports/vision_only/RESULTS.md).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Accuracy evidence & honest baseline
- `reports/vision_only/RESULTS.md` — plans-only accuracy truth: Crow 40% / Bob 8% / Moxy 4% quantity accuracy; failure taxonomy (multi-scale, variance, footprint extent)
- `reports/accuracy/README.md` — Chelsea/Moxy "100%" is vs companion PDF, NOT vision accuracy
- `.planning/phases/20-takeoff-measurement-precision/20-UAT.md` — golden regression state
- `.planning/phases/20-takeoff-measurement-precision/20-14-SUMMARY.md` — convergence blockers
- `scripts/vision_only_benchmark.py` — the plans-only scoring harness (accuracy gate foundation)

### Pipeline core (to be extended/refactored)
- `takeoff_pipeline.py` — central orchestrator; ENABLE_VERIFY_RETRY stub at ~229-234
- `claude_analyzer.py` — prompts, model routing, merge_passes
- `sheet_pass_matrix.py` — PASS_MATRIX + MODEL_ROUTING
- `geometry_takeoff.py`, `scale_extraction.py`, `scale_utils.py`, `scale_recalc.py`, `footprint_takeoff.py` — existing scale/geometry foundation
- `calculator.py`, `aggregator.py` (ITEM_NAME_MAP ~lines 31-126), `reporter.py`
- `pdf_analyzer.py`, `scraper.py` — the two entry points (parity target)
- `companion_takeoff.py`, `object_manifest.py`, `plan_deterministic_legends.py` — to demote to optional

### Learning-loop capture surfaces (existing)
- `app.py` ~1329-1619 — scale verify + human override endpoints (`/api/reports/<run>/scale`, `/verify`)
- `job_store.py`, `stackct_store.py` — SQLite patterns to extend
- `takeoff_measurements.py` — manual measurement engine

### Project docs
- `Masterv2.md` — product source of truth
- `.planning/ROADMAP.md` Phase 21 section — requirement table V3-*

</canonical_refs>

<specifics>
## Specific Ideas

- Known concrete failures to fix (from benchmarks): Bollards 0-17 vs 28; Columns 90 vs 132; CMU Wall 17 vs 2,204 SF; Tilt-up walls MISSING; door schedule rows partial (3/5, 3/7); gas piping missed; WC-1 quantity duplicated across WC-2..10 on Moxy.
- Scale: Crow Cass truth is ~1"=20'; footprint via dimension strings (1136' × 350' → 397,600 SF) already proven in `footprint_takeoff.py` — generalize that approach.
- Success metric for this phase: Crow ≥70% / Bob ≥70% plans-only quantity accuracy (from 40%/8%), 100% completeness-or-flagged, ±5% run-to-run reproducibility, learning store demonstrably applied on repeat runs.
- Tiled counting exists behind `COUNT_TILING=1` — integrate with dedup/voting instead of leaving it off by default.
</specifics>

<deferred>
## Deferred Ideas

- Model fine-tuning / custom symbol detection ML — out of scope (retrieval-based learning only)
- FastAPI/Celery migration — v2
- Cross-client federated learning — future; learning store is per-installation
</deferred>

---

*Phase: 21-accuracy-learning-engine*
*Context gathered: 2026-07-13 from user upgrade brief + codebase analysis*
