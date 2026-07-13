# Phase 18 Research: Linked Sheet Auto-Follow

## Problem statement

Construction drawings reference other sheets via detail bubbles (`17` on sheet `C-4`). Phase 16 extracts these and Phase 16/17 resolves them **only if C-4 was analyzed in the same job**. Operators selecting 10 plan sheets miss specs on linked detail sheets → incomplete takeoffs and `target_sheet_not_found` in reports.

## Existing assets to reuse

| Asset | Location | Use |
|-------|----------|-----|
| Sheet catalog | `stackct_store.get_plans(stackct_id, folder_id)` | Map `ref_sheet` → `page_id` |
| Fuzzy label match | `cross_references._match_target_sheet()` | Adapt for catalog lookup |
| Two-phase scraper | `scraper.run_project_scrape` Pass 1 capture / Pass 2 analyze | Insert linked pass between analyze and report |
| Manifest | `capture_manifest.py` | Append linked pages with `source: linked_ref` |
| Reuse | `REUSE_SCREENSHOTS` + `find_screenshot_paths` | Linked pages benefit same as primary |
| Progress | `_weighted_progress(phase=...)` | New phase label `linking` or fold into capturing/analyzing |

## ref_sheet → page_id matching strategy

Sheet names in StackCT are verbose: `"C-4 - CIVIL SITE PLAN"`, refs are short: `"C-4"`, `"3/A5"`, `"I-4.1"`.

**Recommended matcher** (`linked_sheets.py`):

1. Normalize: uppercase, strip spaces, replace `/` and `.` with `-` for comparison.
2. Score candidates from `get_plans()`:
   - Exact token match on sheet number prefix (before first ` - `)
   - Substring: `ref_sheet` in normalized `sheet_name`
   - Suffix match: sheet_name ends with ref
3. If multiple matches → prefer shortest sheet_name distance; log ambiguity.
4. If zero matches → keep `target_sheet_not_found`; optionally log suggested near-misses.

Also collect refs from:
- `extracted["cross_references"][].ref_sheet`
- `extracted["civil_structures"][].detail_ref_sheet`

## Pipeline insertion point

After **Pass 2 Analyze** on user-selected pages, before **resolve_cross_references**:

```
Pass 2a — DISCOVER LINKS (no browser)
  unresolved_refs = collect from all_extracted
  linked_page_ids = match to catalog, exclude already in manifest

Pass 2b — CAPTURE LINKED (browser, if AUTO_INCLUDE and linked_page_ids)
  append to manifest, capture/reuse screenshots

Pass 2c — ANALYZE LINKED (no browser)
  analyze_drawing for new manifest entries

Pass 3 — RESOLVE + REPORT (existing)
```

If `AUTO_INCLUDE_LINKED_SHEETS=false`: only log discovered links in report `linked_sheets_suggested[]` for operator.

## Config

```env
AUTO_INCLUDE_LINKED_SHEETS=true   # default true for production demos
MAX_LINKED_SHEETS=10              # cap per run to control cost/time
MAX_LINKED_DEPTH=1                # no recursive follow in v1
```

## API / UI

- Job dict: `linked_sheets_added: [{page_id, sheet_name, ref_from}]`
- `/api/status`: expose count for monitor
- Optional UI toast: "Added 3 linked detail sheets automatically"
- README section under Production takeoff runs

## Risks

| Risk | Mitigation |
|------|------------|
| Wrong sheet matched | Log match score; unit tests with real Baking Social names |
| Cost explosion | MAX_LINKED_SHEETS cap |
| Cross-folder ref | Scope to same `folder_id`; warn if ref maps to different folder |
| Duplicate analyze | Check manifest `analysis_status=ok` before re-analyze |

## Test plan

- Unit: `match_ref_to_page("C-4", catalog)` → correct page_id
- Unit: discover from mock extractions with 2 unresolved refs
- Integration: mock browser — selected 2 pages, 1 linked added, resolver status `resolved`
- Integration: MAX_LINKED_SHEETS=1 truncates queue

## Files likely touched

- **New:** `linked_sheets.py`, `tests/test_linked_sheets.py`
- **Modify:** `scraper.py`, `config.py`, `.env.example`, `app.py`, `static/app.js`, `README.md`, `cross_references.py` (optional: export match helper)
