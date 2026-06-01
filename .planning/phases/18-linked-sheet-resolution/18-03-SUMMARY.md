---
phase: 18
plan: "03"
subsystem: config-and-manifest
tags: [config, env-vars, dataclass, backward-compat, linked-sheets]

depends_on:
  - "18-01"  # linked_sheets.py core module (match_ref_to_page, collect_unresolved_refs)

provides:
  - AUTO_INCLUDE_LINKED_SHEETS config constant (default true)
  - MAX_LINKED_SHEETS config constant (default 10)
  - MAX_LINKED_DEPTH config constant (default 1)
  - PageEntry.source optional field for linked-ref tagging

affects:
  - "18-04"  # scraper integration will import AUTO_INCLUDE_LINKED_SHEETS and use source field
  - "18-05"  # reporting may filter/display linked_ref pages distinctly

tech-stack:
  added: []
  patterns:
    - optional-dataclass-field-with-default
    - env-var-bool-coercion-pattern

key-files:
  created: []
  modified:
    - config.py
    - capture_manifest.py
    - .env.example

decisions:
  - id: D1
    choice: "source field uses Optional[str] with default None"
    rationale: "Backward-compatible with all existing manifests; no migration needed"
  - id: D2
    choice: "load() uses p.get('source') for deserialization"
    rationale: "Old manifests lack 'source' key; .get() returns None cleanly"
  - id: D3
    choice: "AUTO_INCLUDE_LINKED_SHEETS not added to REQUIRED_ENV_VARS"
    rationale: "Optional feature with safe defaults; app runs without them"

metrics:
  duration: "~91s"
  completed: "2026-06-02"
---

# Phase 18 Plan 03: Config + PageEntry Extension Summary

**One-liner:** Phase 18 env vars (AUTO_INCLUDE_LINKED_SHEETS/MAX_LINKED_SHEETS/MAX_LINKED_DEPTH) + backward-compatible PageEntry.source field for linked-ref tagging.

## What Was Done

Added operator controls for Phase 18 linked-sheet auto-follow behavior via three new
environment variables, and extended `PageEntry` with an optional `source` field so
auto-added linked pages are distinguishable from user-selected pages in manifests.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add config constants + update .env.example | 706e909 | config.py, .env.example |
| 2 | Add source field to PageEntry (backward-compatible) | 71df53e | capture_manifest.py |

## Changes Detail

### config.py — Three new constants after `REUSE_SCREENSHOTS`

```python
AUTO_INCLUDE_LINKED_SHEETS = os.getenv("AUTO_INCLUDE_LINKED_SHEETS", "true").lower() in ("1", "true", "yes")
MAX_LINKED_SHEETS = int(os.getenv("MAX_LINKED_SHEETS", "10"))
MAX_LINKED_DEPTH = int(os.getenv("MAX_LINKED_DEPTH", "1"))
```

### capture_manifest.py — `PageEntry.source` optional field

```python
source: Optional[str] = None  # "linked_ref" for auto-added pages; None for user-selected
```

`load()` updated to pass `source=p.get("source")` — old manifests without the key
load cleanly (Python returns `None` from `.get()`). `asdict()` serialization now
includes `source` in JSON output, enabling downstream phase filtering.

### .env.example — Phase 18 block appended

Documents all three new vars with their defaults and descriptions.

## Verification

- `python3 -c "from config import AUTO_INCLUDE_LINKED_SHEETS, MAX_LINKED_SHEETS, MAX_LINKED_DEPTH; print(...)"` → `True 10 1`
- `PageEntry(page_id=1, ..., source='linked_ref').source == 'linked_ref'` ✓
- `PageEntry(**old_dict_without_source).source is None` ✓ (backward compat)
- `grep "AUTO_INCLUDE_LINKED_SHEETS" .env.example` → found ✓
- `ruff check config.py capture_manifest.py` → All checks passed ✓

## Deviations from Plan

None — plan executed exactly as written.

## Impact Analysis (GitNexus)

- **PageEntry** upstream impact: LOW risk — 1 direct dependent (scraper.py), 2 transitive (main.py, app.py). Adding optional field with default is non-breaking.
- **REUSE_SCREENSHOTS** upstream impact: LOW risk — 0 dependents. New constants are additive.

## Next Phase Readiness

Phase 18-04 (scraper integration) can now:
- `from config import AUTO_INCLUDE_LINKED_SHEETS, MAX_LINKED_SHEETS, MAX_LINKED_DEPTH`
- Tag auto-added pages via `PageEntry(..., source="linked_ref")`
- Gate linked-sheet logic behind `if AUTO_INCLUDE_LINKED_SHEETS:`
