# Phase 18 Context: Linked Sheet Resolution

## User request (2026-06-02)

Production readiness for **drawing pages linked to other pages** — detail bubbles (e.g. "17 / C-4"), civil structure refs, and StackCT sheet cross-references. User confirmed the scraper currently only resolves refs **when the target sheet was already in the same run**; it does not auto-fetch linked pages.

## Current behavior (verified in code)

| Layer | Status |
|-------|--------|
| Claude extraction | `cross_references[]` + `civil_structures[].detail_ref_sheet` in prompt |
| Post-run resolver | `cross_references.resolve_cross_references()` matches `ref_sheet` by **substring** on `_source_sheet` among **already-analyzed** sheets |
| Missing target | `resolution_status: target_sheet_not_found` — no browser trip |
| Calculator | Does **not** consume `resolved_spec` — audit JSON only |
| Page discovery | `stackct_store.get_plans(stackct_id, folder_id)` has full catalog with `page_id` + `sheet_name` |
| Scraper selection | Only user-selected `page_ids_filter` — no expansion |

## Production gaps to close

1. **Map ref_sheet → page_id** using SQLite catalog + fuzzy sheet-name matching (not just in-run substring).
2. **Discover linked pages** after analyzing selected sheets; queue targets not in manifest.
3. **Second capture/analyze pass** for linked pages (respect `REUSE_SCREENSHOTS`, manifest, cancel, phase progress).
4. **Re-resolve cross-refs** after linked sheets analyzed; surface `linked_sheets_added` in job + report JSON.
5. **Safety limits**: `MAX_LINKED_SHEETS` (default 10), `AUTO_INCLUDE_LINKED_SHEETS` (default true), skip refs outside folder_id unless explicit.
6. **Tests + README + UAT** extension for linked-sheet scenarios.

## Depends on

- Phase 16: cross-ref extraction + resolver foundation
- Phase 17: two-phase pipeline, manifest, reuse, progress phases
- Phase 13/14: `get_plans(stackct_id, folder_id)` catalog

## Out of scope (v1)

- Feeding `resolved_spec` back into `calculator.py` quantities (future EST enhancement)
- Multi-hop recursive link following beyond `MAX_LINKED_DEPTH=1`
- StackCT platform-native "linked page" DOM metadata (if it exists — not found in browser.py)
