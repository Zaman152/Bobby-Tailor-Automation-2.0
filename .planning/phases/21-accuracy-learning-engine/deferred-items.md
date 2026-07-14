# Deferred Items — Phase 21

Out-of-scope discoveries logged during execution (not fixed; see executor scope boundary).

## From 21-05 (model routing & render fidelity)

- **`src/bobbytailor/web/settings.py` `VALID_MODELS` still lists only legacy slugs** (`claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-7`). The settings UI therefore cannot select the July 2026 models (`claude-sonnet-5`, `claude-opus-4-8`, `claude-fable-5`) as the `CLAUDE_MODEL` default. Routing itself is unaffected (env-driven `CLAUDE_MODEL_*` constants bypass this list). Not in 21-05 `files_modified`; pick up in a later web/settings plan or a phase-end sweep.
