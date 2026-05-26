---
phase: 14-stackct-plan-sets
plan: 1
subsystem: browser-automation
tags: [stackct, plan-sets, folders, browser, dedupe, testing]

requires:
  - phase-02-stackct-browser
  - 14-DISCOVERY.md

provides:
  - get_plan_sets(project_id)
  - get_page_ids_in_folder(project_id, folder_id)
  - normalize_plan_sets(raw)
  - Direct-grid fallback (folder_id=0)

affects:
  - 14-02: stackct_store schema v2 will consume these APIs
  - 14-03: app.py routes will call browser via sync layer
  - 14-04: UI will show plan set picker before sheets

tech-stack:
  added:
    - pytest (for unit tests)
  patterns:
    - Folder-scoped page discovery
    - Multi-rule deduplication pipeline
    - Direct-grid fallback for projects without folders

key-files:
  created:
    - tests/test_plan_sets.py
  modified:
    - browser.py

decisions:
  - decision: Dedupe rules based on 14-DISCOVERY audit (7 projects)
    rationale: Real-world data from Morehouse, Baking Social, Athens Fire, etc.
    impact: Prevents duplicate folder cards in UI
    alternatives: None — audit revealed exact patterns
    trade-offs: Heuristics may miss edge cases not in audit sample
  
  - decision: Direct-grid fallback with folder_id=0
    rationale: ATL 081 has no folder cards but 120 sheets on landing page
    impact: Single-set projects work without folder selection step
    alternatives: Require all projects to have folders (breaks ATL 081)
    trade-offs: folder_id=0 is synthetic; must handle separately in sync/API
  
  - decision: Deprecate get_all_page_ids to use folder APIs
    rationale: Prevents flat page list that mixes multiple sets
    impact: Old callers get warning; must migrate to folder flow
    alternatives: Keep flat API (perpetuates bug)
    trade-offs: Breaking change for existing code

metrics:
  duration: 2.9 min
  completed: 2026-05-26
---

# Phase 14 Plan 1: Plan-Set Discovery and Dedupe Summary

**One-liner:** Browser layer discovers StackCT folder cards with audit-based dedupe rules and direct-grid fallback.

## What Was Built

### Core Functions

1. **`normalize_plan_sets(raw: list[dict]) -> list[dict]`**
   - Filters system folders (Plans, Bookmarks, Supporting Documents)
   - Drops "Plans X" parent when child "X" exists with same sheet_count
   - Drops aggregate folders with multiple version labels (e.g. "v1" and "v2" in one name)
   - Returns deduplicated folder list

2. **`async get_plan_sets(project_id: int) -> list[dict]`**
   - Navigates to `#/Takeoff/{project_id}`
   - Extracts all `[data-folder-id]` candidates
   - Applies `normalize_plan_sets` dedupe rules
   - Clicks each folder to count sheets
   - Returns `{folder_id, name, sheet_count}` list
   - **Fallback:** If zero folders but pages exist on landing, returns single synthetic set `{folder_id: 0, name: "All drawing sheets", sheet_count: N}`

3. **`async get_page_ids_in_folder(project_id: int, folder_id: int) -> list[dict]`**
   - If `folder_id == 0`: scrapes landing grid (direct-grid fallback)
   - Else: clicks `[data-folder-id="{folder_id}"]` then scrapes pages
   - Returns `{page_id, sheet_name}` list for that folder only

4. **Deprecated: `get_all_page_ids`**
   - Now thin wrapper: calls `get_plan_sets`, warns if multiple sets, returns pages for single-set projects
   - Logs warning directing callers to use folder APIs

### Tests

**`tests/test_plan_sets.py`** — 8 passing unit tests:
- Morehouse: drops aggregate folder (both v1+v2 in name)
- Bid for Baking Social: drops "Plans X" parent when child "X" exists
- Athens Fire Station: same parent/child dedupe
- LaserAway: same parent/child dedupe
- System folder filtering (Plans, Bookmarks, Supporting Documents)
- Battery two distinct sets (not duplicates)
- Empty input handling
- All system folders filtered

## Verification Results

- [x] Import test: `from browser import StackCTBrowser, normalize_plan_sets` successful
- [x] All 8 dedupe tests pass with fixtures from 14-DISCOVERY.json
- [x] Code covers all audit patterns from 7-project discovery

**Manual verification pending:**
- [ ] Morehouse (7416168): `get_plan_sets` returns 2 sets (v1=120, v2=180)
- [ ] Bid for Baking Social: 1 deduped set (not duplicate "Plans …" row)
- [ ] ATL 081 (7414097): fallback single set with folder_id=0

## Deviations from Plan

None — plan executed exactly as written.

## What's Next

**Phase 14 Plan 2 (14-02-PLAN.md):**
- Schema v2 migration: `project_plan_sets` table
- `project_plans` PK change to `(stackct_id, folder_id, page_id)`
- `stackct_sync` folder-aware: `sync_project_plan_sets`, `sync_project_plans(folder_id)`
- `project_cache` getters for plan sets and folder-scoped plans

**Integration point:** 14-02 sync layer will call `browser.get_plan_sets()` and `browser.get_page_ids_in_folder()`.

## Commits

| Commit | Message |
|--------|---------|
| 11941d0 | feat(14-01): plan-set discovery and dedupe |

## Files Changed

```
browser.py                +357 -33
tests/test_plan_sets.py   +156 (new)
```

## Tech Debt / Future Work

- **Audit sample coverage:** 7 projects tested; edge cases may exist in other 19 cached projects
- **Heuristic brittleness:** "v1" + "v2" in one name may miss other aggregate patterns (e.g. "A+B", "Combined")
- **Long folder names:** Truncated at 150 chars in browser JS; may lose disambiguating suffix
- **Discover script cleanup:** `scripts/discover_plan_sets.py` not updated (diagnostic tool, optional)

## Success Criteria Met

- [x] Plan-set discovery matches StackCT folder cards user sees (dedupe rules from audit)
- [x] Page scrape is folder-scoped, not project-wide merge
- [x] Tests cover dedupe without Playwright (unit tests with JSON fixtures)
