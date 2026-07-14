---
phase: 21-accuracy-learning-engine
verified: 2026-07-15T10:45:00Z
status: human_needed
score: 2/7 must-haves verified
behavior_unverified: 4
overrides_applied: 0
behavior_unverified_items:
  - truth: "SC1: Uploading a plans-only PDF (no companion, no manifest, no calibration) produces a complete takeoff — zero silent misses, explicit flags, flags approach zero on vector CAD PDFs"
    test: "UAT 1 — upload uploads/Crow - Cass White Road-Plans.pdf alone via the PDF tab and run"
    expected: "Run completes with no manifest/companion prompt; every quantity row carries provenance; anything indeterminable is flagged needs_review with a reason; flagged subset is small"
    why_human: "End-to-end live outcome on a real upload with paid API calls; the flag-don't-guess conventions are unit-tested offline but the empirical completeness/flag-rate claim can only be observed on a live run"
  - truth: "SC2: Plans-only quantities on Crow Cass + Bob's Discount are ≥97% (geometry/text provenance) and ≥90% overall vs golden, item-found ≥95%, zero silent misses (scripts/vision_only_benchmark.py)"
    test: "UAT 2 / 21-17 Task 3 — bash scripts/accuracy_gate.sh (~$5–15 API spend; check ANTHROPIC_API_KEY credit first)"
    expected: "Exit 0; geometry/text accuracy ≥97% and overall ≥90% on both gating projects; item-found ≥95%; zero silent misses; Chelsea+Moxy tracked non-gating"
    why_human: "The gate spends real API credits (explicitly excluded from automated verification); offline scoring logic is fully tested (tests/test_benchmark_scoring.py) but the accuracy numbers themselves require the live run"
  - truth: "SC4: After a human verifies a run, corrections persist in the learning store and a repeat run of the same project applies them automatically (names, quantities context, scale, wall heights) without any manifest file"
    test: "UAT 4/9 — correct an item name + confirm a quantity via the web UI, check learning.db rows, delete the run folder, re-run the same PDF"
    expected: "Correction survives run-folder deletion; repeat run applies learned name (source=learned); learned data only re-flags conflicting quantities (re_verify), never overwrites geometry/text values"
    why_human: "Every layer is behaviorally tested offline (store round-trip/decay, endpoint capture, retrieval + 3-seam injection + anti-amplification) but the UI-driven verify→persist→repeat-run loop needs a live session. CAVEAT for the tester: no web endpoint records scope='name' renames (review IN-06, open) — rename learning currently accretes only indirectly via unit corrections; if UAT 4's rename step does not persist as vocabulary, that is the IN-06 gap surfacing, not a regression"
  - truth: "SC5: Two identical runs of the same PDF produce quantity results within ±5% of each other (ensemble kills run-to-run variance)"
    test: "UAT 5 — python3 scripts/vision_only_benchmark.py --name crow --plans-pdf ... --takeoff-pdf ... --repro (also covered by the gate's --repro double-runs)"
    expected: "All per-item quantity deltas ≤5%; no item present in one run silently vanishes in the other"
    why_human: "Run-to-run variance is a live stochastic property of paid API calls; ensemble voting/dedup/budget logic is unit-tested offline but the variance bound requires two real runs"
human_verification:
  - test: "UAT 2 / 21-17 Task 3 — run the budget-guarded accuracy gate: bash scripts/accuracy_gate.sh"
    expected: "Exit 0; geometry/text-provenance accuracy ≥97% on Crow+Bob; overall ≥90%; item-found ≥95%; zero silent misses; repro ≤5%; Chelsea+Moxy tracked non-gating; cost within warned baseline"
    why_human: "Spends real API credits (single-digit USD) — explicitly excluded from automated verification; this is the blocking checkpoint deferred from 21-17"
  - test: "UAT 1 + UAT 3 — plans-only Crow upload through the web UI, then open the Scale & Verify panel"
    expected: "Complete takeoff with per-row provenance and explicit flags; every sheet shows auto-detected scale with confidence and source; Crow page 1 main plan resolves 1\"=40' HIGH (the roadmap's ~1\"=20' example was disproven in 21-07 — geometrically impossible on a 3024pt sheet); footprint ≈397,600 SF"
    why_human: "Live paid run plus visual report/panel inspection"
  - test: "UAT 4 + UAT 9 — learning loop through the UI: verify a run, inspect learning.db, delete run folder, repeat-run the same project"
    expected: "Corrections persist and apply automatically on the repeat run with zero manifest files; learned data only re-flags (re_verify), never overwrites geometry/text quantities. Note the scope='name' rename-capture caveat (review IN-06, open)"
    why_human: "End-to-end UX loop across two live runs; cannot be exercised without API spend and human judgment"
  - test: "UAT 6 — StackCT parity run on a small sheet subset (≤15)"
    expected: "capture→analyze→report completes; report rows show the same provenance/flag structure as the PDF path (deterministic on vector blobs, ensemble on raster); scale/verify/learning capture behave identically"
    why_human: "Requires live StackCT credentials, Playwright scrape, and API spend"
  - test: "UAT 8 — reviewed-items workflow demo"
    expected: "Review panel surfaces exactly the flagged subset (needs_review / fusion_rejected / re_verify) with reasons; working the list clears or downgrades each flag; demo-grade UX"
    why_human: "UX quality judgment (V3-PROD-02 'demonstrable') on a completed live run"
  - test: "UAT 7 (runtime half) + sign-off checklist — gunicorn boot per docs/DEPLOYMENT.md, /login 200, learning.db backup+restore drill, then sign 21-UAT.md and push to GitHub Zaman152/Bobby-Tailor-Automation-2.0"
    expected: "Deployment docs work as written; backup procedure succeeds; 21-UAT.md signed (roadmap success criterion 7); milestone pushed (locked process decision)"
    why_human: "Server runtime, ops drill, sign-off authority, and the GitHub push are human-only actions"
---

# Phase 21: Accuracy & Learning Engine (v3) — Verification Report

**Phase Goal:** Plans-only runs become production-accurate and self-improving: vector-geometry-first measurement with vision as semantic labeler, per-viewport auto scale detection with confidence, ensemble/tiled EA voting, every human verification persisted to a learning store and retrieved on future runs, the codebase restructured from 30 flat root modules into a proper package, and the app ready for live testing.
**Verified:** 2026-07-15
**Status:** human_needed
**Re-verification:** No — initial verification

## Verification Basis

- Verified at HEAD `330e5c9` (includes all 10 Critical/Warning code-review fixes `d9949d5..8f50be6` per 21-REVIEW-FIX.md; independently confirmed present in `git log`).
- Full non-golden suite **run by this verifier**: `python3 -m pytest -q -m "not golden"` → **859 passed, 0 failed, 2 deselected (golden), exit 0** (309s). Golden/paid tests never run.
- Working tree deltas at verification time: only regenerated synthetic fixture PDFs (test side effects), no source changes.
- 18/18 SUMMARYs cross-referenced against code; SUMMARY commit hashes spot-checked and all resolve to real commits.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — the contract)

| # | Truth | Status | Evidence |
| --- | ------- | ---------- | -------------- |
| 1 | Plans-only PDF upload → complete takeoff, zero silent misses, explicit flags | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Mechanism present + wired: plans-only LOCKED contract in `pdf_analyzer.py` (no companion/manifest auto-discovery — WR-08 fix `8f50be6` verified: `find_companion_takeoff_pdf` referenced only by `scripts/vision_only_benchmark.py:728`; `allow_discovery=False` on all 3 production call sites); flag conventions unit-tested (`test_run_ensemble_budget_exhausted_flags_never_truncates_silently`, `test_fuse_unknown_label_keeps_deterministic_count_flagged`). Live completeness → UAT 1 |
| 2 | Crow+Bob plans-only ≥97% geometry/text, ≥90% overall, item-found ≥95% via benchmark | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `scripts/vision_only_benchmark.py` (provenance-split scoring, `--takeoff-pdf` explicit ground truth ×7 refs, repro mode) + `scripts/accuracy_gate.sh` (learning-isolated: `LEARNING_DB_PATH` pinned to fresh temp DB, line 67) exist and scoring logic is tested (`tests/test_benchmark_scoring.py`, incl. WR-07 rescore fix). Live numbers → UAT 2 (paid; deferred from 21-17 Task 3) |
| 3 | Scale auto-detected per viewport, zero calibration; main-plan viewport wins on multi-scale sheets | ✓ VERIFIED | `deterministic/viewports.py` + `scale_solver.py` (RANSAC solve, `resolve_scale_v2`, printed notation demoted to cross-check, `learned_prior` ranked last); behaviorally tested against hand-recorded truth tables `tests/fixtures/{crow_cass,bobs_discount}/scale_truth.json` in the green suite — Crow main plan solves dimension_solve/HIGH at 40.0 fpi (n=30, share 0.89), zero HIGH-confidence-wrong scales gate. **Documented deviation:** the SC's literal "~1\"=20'" example was disproven in 21-07 — 1136' over 2058pt ≈ 39.74 fpi; 20 fpi is geometrically impossible on the 3024pt sheet. Hand-verified truth is 1\"=40'. The SC's intent (main-plan scale wins, not 24'/detail scales, zero calibration) is what the tests assert |
| 4 | Human verification persists to learning store; repeat run applies it with no manifest | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Full chain present, wired, and offline-tested: endpoints→`record_correction`→`distill`→`load_learned_context`→3 seams (prompt hints; `aggregator.py:143-159` learned vocabulary before `ITEM_NAME_MAP`; calculator wall heights; `learned_prior` at pipeline `resolve_scale_v2` call `takeoff_pipeline.py:1249`); anti-amplification guardrail (`retrieval.py` — geometry/text HIGH never overwritten, `re_verify` flags only) tested in `test_learning_retrieval.py`. UI-driven live loop → UAT 4/9. WARNING: scope='name' rename capture unwired at web layer (review IN-06, open) |
| 5 | Two identical runs within ±5% (ensemble kills variance) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `vision/ensemble.py` (median voting, agreement-based confidence, tiled dedup member, `BudgetGuard`/`BudgetExceeded`) tested in `tests/test_ensemble.py` incl. disagreement→needs_review and budget-exhaustion flag paths; benchmark `--repro` harness scored offline. Live variance bound → UAT 5 |
| 6 | Structured package; pytest passes; app boots via blueprints; README documents layout | ✓ VERIFIED | Package tree `src/bobbytailor/{config.py,deterministic,devtools,learning,pipeline,scrape,stores,vision,web}` confirmed; **verifier-run suite: 859 passed, exit 0**; `create_app()` boots (40 routes registered, 7 `register_blueprint` calls); root has exactly `app.py` + `main.py` (all 33 shims deleted); zero legacy root imports in src/tests/scripts (exhaustive grep); 61 files import `bobbytailor.*`; README documents `src/bobbytailor/` layout (lines 14-28); docs/DEPLOYMENT.md covers env table, `LEARNING_DB_PATH`, `API_BUDGET_PER_RUN_USD`, error-recovery semantics, reviewed-items workflow |
| 7 | 21-UAT.md signed off for live-testing readiness | ? HUMAN PENDING | `21-UAT.md` exists (9 sections, maps every SC + both Manual-Only validation rows + sign-off checklist incl. GitHub push) but sign-off line is blank (line 175). This SC *is* the human checkpoint — cannot be true until UAT executes |

**Score:** 2/7 truths verified (4 present, behavior-unverified; 1 human sign-off pending). No truth FAILED.

### Required Artifacts (per-plan must_haves, gsd-tools 3-level + manual wiring)

All 18 plans' artifact sets pass existence + substantive checks (44/45 via `gsd-tools query verify.artifacts`; min_lines and contains patterns all satisfied). Highlights:

| Artifact | Expected | Status | Details |
| -------- | ----------- | ------ | ------- |
| `src/bobbytailor/` package (9 subpackages) | V3-STRUCT-01 restructure | ✓ VERIFIED | Importable (`import bobbytailor` OK), editable install works |
| `geometry_takeoff.py` root shim (21-01) | transitional shim | ✓ VERIFIED (superseded) | Deliberately deleted by 21-18's own must-have "Root shims are deleted"; suite green without any legacy path — planned supersession, not a gap |
| `src/bobbytailor/web/app.py` `create_app()` | blueprint factory | ✓ VERIFIED | Boots, 40 routes; root `app.py` = `app = create_app()` shim |
| `src/bobbytailor/deterministic/{dimensions,viewports,scale_solver,symbols,tables,walls,rooms}.py` | vector-first engine | ✓ VERIFIED | All substantive (STRtree, RANSAC, polygonize, find_tables, candidate registries); each has a fixture-driven test file in the green suite |
| `src/bobbytailor/learning/{store,distill,retrieval}.py` | learning engine | ✓ VERIFIED | Parameterized SQL throughout (multi-line style; zero f-string SQL), WR-01/WR-02 fixes in place; round-trip/decay/idempotency tested |
| `src/bobbytailor/vision/{schemas,overlay,prompts,ensemble,fusion,verify_retry}.py` | vision-as-labeler stack | ✓ VERIFIED | `semantic_labeling_schema` has **zero** numeric-typed fields and enum-grounds candidate IDs (executed check); only `raster_extraction_schema` (fallback) carries numbers; `MAX_RETRIES_PER_ITEM = 2` budget-guarded |
| `src/bobbytailor/pipeline/{takeoff_pipeline,reporter,pdf_analyzer,sheet_pass_matrix}.py` | deterministic-first orchestration | ✓ VERIFIED | `class RunSettings` (line 147); reporter surfaces per-item `provenance`, `scale_confidence`, `measurement_mode`; `ENABLE_VERIFY_RETRY` stub gone (zero grep hits); PRICING matches July 2026 table (sonnet-5 2/10, opus-4-8 5/25, haiku-4-5 1/5, fable-5 10/50); MODEL_ROUTING sources only `CLAUDE_MODEL_*` config, zero hardcoded slugs |
| `scripts/vision_only_benchmark.py` + `scripts/accuracy_gate.sh` | CI-invocable gate | ✓ VERIFIED | Explicit `--takeoff-pdf`, provenance split, learning isolation via temp `LEARNING_DB_PATH`, decoy tripwires |
| `README.md`, `docs/DEPLOYMENT.md`, `21-UAT.md` | live-testing docs | ✓ VERIFIED | Layout, env, learning DB, budget guard, error recovery, reviewed-items workflow all documented |

### Key Link Verification (manual grep — gsd-tools could not resolve descriptive from/to names)

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| web/app.py | 7 blueprints | register_blueprint | ✓ WIRED | 7 calls; root app.py uses `create_app()` |
| dimensions.py | shapely STRtree | corridor search | ✓ WIRED | 3 refs; test_dimensions.py drives crow_cass fixture |
| learning/store.py | SQLite | parameterized queries | ✓ WIRED | `?`-placeholder SQL confirmed (lines 163,172,198,381,416,479); no f-string SQL |
| verify.py endpoints | store.record_correction + distill | same-request capture | ✓ WIRED | `_capture_learning` helper → `record_correction` (line 128) + `distill()`; feeds all 7 verify/scale/measurements/verify-batch/calibrate routes |
| sheet_pass_matrix.MODEL_ROUTING | config.CLAUDE_MODEL_* | import, no literals | ✓ WIRED | 4 config imports; zero hardcoded slugs in routing |
| scale_solver | dimensions.extract_dimension_samples + snap_fpi | RANSAC over samples, ladder as cross-check | ✓ WIRED | 2 + 3 refs |
| symbols/tables/walls/rooms | candidate registries / polygonize / find_tables | Recipes B/C/D | ✓ WIRED | candidate_id ×4, polygonize ×8, find_tables ×3, centerline ×15 |
| claude_analyzer | output_config json_schema | structured outputs | ✓ WIRED | 2 refs |
| overlay.py / verify_retry.py | pdf_analyzer.render_clip_crop | crop primitive | ✓ WIRED | 6 + 4 refs |
| ensemble.run_ensemble | injectable analyzer + _cost_usd | test-injection + budget accumulation | ✓ WIRED | 8 + 8 refs |
| fusion | candidate registries + PROVENANCE_RANK | ID-grounded merge | ✓ WIRED | candidate_id ×19, PROVENANCE_RANK ×10 |
| takeoff_pipeline | deterministic modules + fuse_sheet + BudgetGuard + retry_flagged_items + load_learned_context | deterministic-first flow | ✓ WIRED | Module-level patchable imports (lines 62-77); fuse_sheet ×5; BudgetGuard ×21; retry ×4; learning ×4 |
| scraper + pdf_analyzer | RunSettings | identical construction both entry points | ✓ WIRED | 8 + 4 refs; parity tests assert shared guard + call sites (post-WR-05/WR-06) |
| devtools/companion_takeoff | benchmark only | explicit --takeoff-pdf | ✓ WIRED | Sole non-devtools reference is `vision_only_benchmark.py:728`; production paths pass `allow_discovery=False` |
| aggregator.normalize_item_name | LearnedContext.lookup_name before ITEM_NAME_MAP | learned-first naming | ✓ WIRED | aggregator.py:143-159 |
| calculator / pipeline scale call | learning_assumptions / learned_prior | guarded injection | ✓ WIRED | wall_height ×15; learned_prior at takeoff_pipeline.py:1249 ranked last in resolve_scale_v2 |
| tests/ + scripts/ + src internals | bobbytailor.* absolute imports | shim-free migration | ✓ WIRED | 61 files; zero legacy root-module imports by exhaustive grep |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| aggregator learned naming | `learned.lookup_name(description)` | learning_vocabulary ← distill ← learning_corrections ← verify endpoints | Yes (SQL-backed, tested round-trip) | ✓ FLOWING |
| reporter takeoff.json | `provenance`, `scale_confidence`, `measurement_mode` | fusion/pipeline per-item fields | Yes (fusion tests assert propagation) | ✓ FLOWING |
| verify.py scale panel | run scale calibration + solver output | run folder JSON + resolve_scale_v2 | Yes | ✓ FLOWING |
| rename→vocabulary (scope 'name') | `canonical_name` | **no producing endpoint** | Partial — application seam wired, capture seam absent (IN-06) | ⚠️ PARTIAL (see warning) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Package imports | `python3 -c "import bobbytailor"` | import-ok | ✓ PASS |
| App boots via factory | `python3 -c "from bobbytailor.web.app import create_app; create_app()"` | boot-ok, 40 routes | ✓ PASS |
| Full non-golden suite (run once) | `python3 -m pytest -q -m "not golden"` | 859 passed, 0 failed, 2 deselected, exit 0 | ✓ PASS |
| Semantic schema has no numeric fields + enum grounding | executed `semantic_labeling_schema(...)` introspection | zero integer/number types; candidate IDs enum-grounded; raster fallback (intended) has numbers | ✓ PASS |
| Live accuracy gate | `bash scripts/accuracy_gate.sh` | not run — paid API calls | ? SKIP → human (UAT 2) |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes exist or are declared by any plan. `scripts/accuracy_gate.sh` is a paid live gate explicitly excluded from automated verification (routed to UAT 2).

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| — | — | — | N/A (none declared) |

### Requirements Coverage

All 13 phase requirement IDs are claimed by plan frontmatter (no orphans: REQUIREMENTS.md maps exactly these 13 to Phase 21).

| Requirement | Source Plan(s) | Status | Evidence |
| ----------- | ---------- | ------ | -------- |
| V3-ACC-01 vector-first measurement | 03,06,08,10,12,13 | ✓ SATISFIED | Full chain closed: dimensions/symbols/tables/walls/rooms → fusion (provenance-ranked, vision can't overwrite geometry — `test_fuse_out_of_registry_id_rejected`, PROVENANCE_RANK) → pipeline deterministic-first flow. The 21-06-era premature-completion flag is resolved: fusion (21-12) and pipeline integration (21-13) exist, are wired, and are tested |
| V3-ACC-02 auto scale v2 | 03,07 | ✓ SATISFIED | Per-viewport RANSAC solve, confidence recorded, printed notation demoted; truth-table gated tests green |
| V3-ACC-03 ensemble extraction | 11,13 | ✓ SATISFIED | N-run voting, tiled dedup member, disagreement→needs_review tested |
| V3-ACC-04 model upgrade & fidelity | 05,08 | ✓ SATISFIED | Env-driven routing, July 2026 PRICING, 1568px retarget + render_clip_crop |
| V3-ACC-05 verify-retry loop | 14 | ✓ SATISFIED | ENABLE_VERIFY_RETRY stub gone; ≤2 retries/item, budget-guarded, flag-never-suppress |
| V3-LEARN-01 correction store | 04,09 | ✓ SATISFIED | SQLite store survives run deletion (tested); all verify endpoints capture in-request |
| V3-LEARN-02 learned vocabulary | 04,16 | ✓ SATISFIED (with warning) | Learned-first naming before ITEM_NAME_MAP wired + tested; auto-manifest distillation present. Warning: scope='name' rename capture unwired at web layer (IN-06 open) — vocabulary currently accretes via unit/missed_item paths |
| V3-LEARN-03 runtime feedback | 16 | ✓ SATISFIED | 3-seam injection + anti-amplification guardrail tested |
| V3-LEARN-04 manifest independence | 15,16 | ✓ SATISFIED (code) / live acceptance → UAT | No companion/manifest auto-discovery on any production path (WR-08 fix + decoy tripwires); target-accuracy half rides on UAT 2 |
| V3-STRUCT-01 package restructure | 01,02,18 | ✓ SATISFIED | 9-subpackage src layout, blueprints, shims deleted, 859 green |
| V3-STRUCT-02 entry-point parity | 15 | ✓ SATISFIED | Identical RunSettings + shared BudgetGuard + parity tests (incl. WR-05/WR-06 fixes); live parity → UAT 6 |
| V3-PROD-01 accuracy gate | 17 | ✓ SATISFIED (code) / NEEDS HUMAN (live run) | Gate + scoring + isolation + reproducibility implemented and offline-tested; the live gating numbers are the pending 21-17 Task 3 checkpoint |
| V3-PROD-02 live-testing readiness | 11,18 | ✓ SATISFIED (code) / NEEDS HUMAN (sign-off) | Budget guard on both entry points, reviewed-items workflow documented, error-recovery docs, 21-UAT.md exists; sign-off pending |

Note: REQUIREMENTS.md marks all 13 "Complete" and ROADMAP.md marks Phase 21 `[x]` (completed 2026-07-14) — **both overstate status** while the accuracy-gate run and UAT sign-off are pending (see Gaps Summary).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| src/bobbytailor/pipeline/calculator.py | 1043 | "TBD" | ℹ️ Info (false positive) | Comment describing rejection of "TBD" strings in input data — not a debt marker |
| src/bobbytailor/web/blueprints/verify.py (absence) | — | scope='name' never recorded by any endpoint | ⚠️ Warning | Review IN-06, open by design (`fix_scope=critical_warning`); rename learning loop partially wired — surfaced to UAT 4 tester |
| src/bobbytailor/web/settings.py | 24 | VALID_MODELS lists legacy slugs only | ℹ️ Info | Review IN-02 / deferred-items.md; settings UI can't select July 2026 models; routing unaffected (env-driven) |
| scripts/accuracy_gate.sh / vision_only_benchmark.py | 67 / 653-693 | temp dir not cleaned; bare asserts stripped under -O | ℹ️ Info | Review IN-05, open; informational |
| src/bobbytailor/web/app.py | 64-66 | hardcoded output/screenshots dir | ℹ️ Info | Review IN-04, open; masked downstream |

Zero unreferenced TBD/FIXME/XXX debt markers; zero TODO/HACK/PLACEHOLDER markers in phase-modified source. All 10 Critical/Warning review findings verified fixed at HEAD (commits d9949d5..8f50be6 present; spot-verified: no plaintext credential pattern, job_store imported, allow_discovery=False on production call sites, one run-level BudgetGuard on StackCT path).

### Human Verification Required

See frontmatter `human_verification` — six items, consolidated from 21-UAT.md (9 sections + sign-off checklist), the two pending checkpoints deferred from 21-17 Task 3 and 21-18 Task 3, and this verifier's behavior-unverified truths. The single sink is executing `21-UAT.md` end-to-end and signing it off.

### Gaps Summary

**No code gaps.** Every plan-level must-have (truths, artifacts, key links) is verified in the codebase; the full non-golden suite passes at HEAD (859/859, verifier-run); all 10 Critical/Warning code-review findings are fixed and regression-tested.

The phase is **not yet complete** because its own success criteria route through live, paid, human-judged checkpoints that were deliberately deferred to end-of-phase:

1. **Live accuracy gate run** (SC2, 21-17 Task 3) — the ≥97/≥90/≥95 numbers have never been measured on real API calls at this HEAD.
2. **UAT sign-off** (SC7, 21-18 Task 3) — 9-section live-testing script unsigned; includes plans-only upload, learning loop, StackCT parity, reviewed-items demo, deployment-docs walkthrough, and the locked GitHub-push decision.

**Flag for the orchestrator:** ROADMAP.md marks Phase 21 `[x] completed 2026-07-14` and REQUIREMENTS.md marks all 13 requirements "Complete" — both were pre-marked by the 21-18 executor before verification. Since this verdict is `human_needed` (not `passed`), those checkboxes currently overstate status until the UAT sign-off lands.

**Watch items for UAT (not gaps):** (a) rename capture (scope='name') is unwired at the web layer — IN-06; UAT 4's rename step is the empirical test; (b) settings-UI VALID_MODELS lags the July 2026 lineup — IN-02/deferred-items.md; (c) remaining Info-level review items IN-01/IN-04/IN-05 are open and tracked.

---

_Verified: 2026-07-15T10:45:00Z_
_Verifier: Claude (gsd-verifier)_
