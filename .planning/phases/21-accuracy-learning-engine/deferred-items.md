# Deferred Items — Phase 21

Out-of-scope discoveries logged during execution (not fixed; see executor scope boundary).

## From 21-05 (model routing & render fidelity)

- **`src/bobbytailor/web/settings.py` `VALID_MODELS` still lists only legacy slugs** (`claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-7`). The settings UI therefore cannot select the July 2026 models (`claude-sonnet-5`, `claude-opus-4-8`, `claude-fable-5`) as the `CLAUDE_MODEL` default. Routing itself is unaffected (env-driven `CLAUDE_MODEL_*` constants bypass this list). Not in 21-05 `files_modified`; pick up in a later web/settings plan or a phase-end sweep.

## 21-08 execution — pre-existing test-order pollution (out of scope)
- `pytest tests/test_takeoff_pipeline.py tests/test_render_fidelity.py` (forced non-alphabetical order) fails 2 tests in `TestPageToImage`: `test_takeoff_pipeline`/`test_pipeline_parity` leave a MagicMock in place that breaks `pdf_analyzer._effective_render_scale` (`float < MagicMock`). Reproduced at HEAD prior to 21-08 Task 2 changes. Standard alphabetical collection (full suite) never hits this order — 626-green baseline unaffected. Fix belongs to a test-hygiene pass, not 21-08.

## 21-16 execution — same pre-existing pollution class, more victims (out of scope)
- `tests/test_pipeline_parity.py` performs module-level `sys.modules` mutations (`sys.modules["claude_analyzer"] = _CA_MOCK`, `setdefault("takeoff_pipeline", ...)`, `setdefault("calculator", ...)`) that leak into any test module first imported AFTER it in the same session. Forced non-alphabetical orders reproduce: `parity → test_learning_capture` = 9 fixture errors (`create_app()` TypeError); `parity → test_confidence_flagging` = 3 failures (mocked CSV writers/aggregator). **Verified pre-existing at commit `ea60f2e` (before any 21-16 change) via a scratch worktree — parent commit fails the same orders with 9 failed + 9 errors.** Canonical alphabetical collection never hits these orders; full suite green. Fix idea: move the sys.modules stomps into a module-scoped fixture with teardown, or subprocess-isolate the parity source checks. Belongs to a test-hygiene pass.
