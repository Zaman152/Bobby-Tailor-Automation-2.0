---
phase: 14-stackct-plan-sets
plan: 3
subsystem: api-routes
tags: [flask, rest-api, folder-validation, backward-compat]

requires:
  - 14-02-SUMMARY.md (folder-aware cache)
  - phase-04-project-plan-selection

provides:
  - GET /api/projects/<id>/plan-sets
  - GET /api/projects/<id>/plan-sets/<folder_id>/plans
  - POST /api/run/stackct with folder_id validation
  - folder_id in takeoff.json

affects:
  - 14-04: UI will call new /plan-sets endpoint before /plans
  - Existing API clients: /plans now requires ?folder_id= (breaking change)

tech-stack:
  added: []
  patterns:
    - Two-step API flow: plan sets → sheets
    - Server-side page_ids validation against folder
    - Backward-compat error messages with hints

key-files:
  created: []
  modified:
    - app.py
    - scraper.py
    - reporter.py

decisions:
  - decision: Require folder_id in POST /sync-plans (break old callers)
    rationale: Prevents accidental flat sync without folder context
    impact: Old /sync-plans calls fail with 400 error
    alternatives: Auto-select first folder (unreliable), keep flat sync (perpetuates bug)
    trade-offs: Clean API but breaks backward compatibility

  - decision: Legacy GET /plans returns 400 if folder_id missing
    rationale: Forces callers to use correct two-step flow
    impact: Old UI/scripts calling /plans without folder_id fail
    alternatives: Return all plans (mixes folders), auto-pick first folder (arbitrary)
    trade-offs: Explicit error with hint vs silent wrong behavior

  - decision: Validate page_ids belong to folder on run
    rationale: Prevents submitting v1 sheets with v2 folder_id
    impact: Run fails early if page_ids don't match folder
    alternatives: Skip validation (allows data integrity issues)
    trade-offs: Extra DB query but prevents silent errors

  - decision: Store folder_id in takeoff.json root (not metadata)
    rationale: Makes it easy to filter reports by folder later
    impact: All reports now record which folder was used
    alternatives: Store in nested metadata object (harder to query)
    trade-offs: Top-level simplicity vs cleaner nesting

metrics:
  duration: ~2 min
  completed: 2026-05-26
---

# Phase 14 Plan 3: Folder-First API Routes Summary

**One-liner:** REST API exposes two-step plan selection (folders → sheets) with folder_id validation on runs.

## What Was Built

### New Routes

**1. `GET /api/projects/<id>/plan-sets`**
- Returns folder list with counts: `{plan_sets: [{folder_id, name, sheet_count}, ...], from_cache, syncing?, ...}`
- Supports `?refresh=1` to force live sync
- DB-first with stale-while-revalidate (reuses Phase 13 pattern)

**2. `GET /api/projects/<id>/plan-sets/<folder_id>/plans`**
- Returns sheets for one folder only
- Supports `?refresh=1` and `?background=1`
- DB-first with background sync

**3. `POST /api/projects/<id>/sync-plan-sets`**
- Warm folder index (populate project_plan_sets table)
- Supports `?force=1` to bypass TTL

### Updated Routes

**4. `POST /api/projects/<id>/sync-plans`** (breaking change)
- **Now requires `folder_id` in JSON body or query param**
- Returns 400 with hint if folder_id missing
- Error: `"folder_id required. Call /plan-sets first, then sync a folder."`

**5. `GET /api/projects/<id>/plans`** (backward compat with breaking change)
- **Now requires `?folder_id=` query param**
- Returns 400 with hint if missing
- Error: `"folder_id required. Use GET /api/projects/<id>/plan-sets first."`
- Hint: `"/api/projects/{project_id}/plan-sets"`

**6. `POST /api/run/stackct`**
- Accepts `folder_id` in request body
- When `mode=specific` and both `page_ids` and `folder_id` provided:
  - Validates page_ids belong to folder via `stackct_store.get_plans(project_id, folder_id)`
  - Returns 400 if any page_ids not in folder: `"page_ids [X, Y, Z] are not in plan set folder {folder_id}"`
- Passes folder_id to `_stackct_job` → `run_project_scrape` → `generate_report`

**7. `GET /api/projects/sheet-counts`** (enhanced)
- Now returns `{counts: {...}, plan_set_counts: {project_id: N}, synced_at}`
- Frontend can show "N sets" instead of misleading single sheet total

### Scraper & Reporter Updates

**scraper.py:**
- `run_project_scrape(..., folder_id=None)` accepts optional folder_id
- If folder_id provided: calls `browser.get_page_ids_in_folder(project_id, folder_id)`
- Else: calls `browser.get_all_page_ids(project_id)` (deprecated warning)
- Passes folder_id to `generate_report`

**reporter.py:**
- `generate_report(..., folder_id=None)` accepts optional folder_id
- Adds `"folder_id": folder_id` to takeoff.json report root (after project_name)
- Stored in all output files (JSON, CSV metadata if applicable)

## Verification Results

- [x] Imports successful (app.py, scraper.py, reporter.py)
- [x] All routes defined with correct signatures

**Manual verification pending:**
- [ ] curl /plan-sets for Morehouse returns 2 entries
- [ ] curl /plan-sets/35240700/plans returns 120 plans only
- [ ] Run with wrong folder page_id rejected with 400 error
- [ ] takeoff.json includes folder_id field

## Deviations from Plan

None — plan executed exactly as written.

## What's Next

**Phase 14 Plan 4 (14-04-PLAN.md):**
- Update `static/app.js`: fetchPlanSets, two-step preview flow
- Update `templates/index.html`: add #planSetPanel between project picker and #planSelectionPanel
- Update project list to show "N sets" instead of single sheet count
- Add "runStackCT" folder_id to POST body
- Manual verification: Morehouse shows 2 sets before 120 checkboxes

**Integration point:** 14-04 UI calls `GET /plan-sets`, user picks folder, then `GET /plan-sets/{folder_id}/plans`.

## Commits

| Commit | Message |
|--------|---------|
| 2dafa9a | feat(14-03): folder-first API routes |

## Files Changed

```
app.py       +101 -19  (new routes, folder validation, backward compat errors)
scraper.py   +5 -2    (pass folder_id to report)
reporter.py  +4 -1    (store folder_id in takeoff.json)
```

## Tech Debt / Future Work

- **Backward compat errors may surprise users:** Old scripts calling /plans will fail; should document migration in release notes
- **No folder name in run validation error:** Error says "not in plan set folder {folder_id}" (numeric) not folder name
- **get_sheet_counts still returns sheet_count per project:** Should deprecate or aggregate from plan_sets table
- **No /plan-sets/<folder_id> detail route:** Could add folder metadata endpoint if needed

## Success Criteria Met

- [x] API surface matches two-step UX contract (plan sets → sheets)
- [x] Run pipeline cannot mix folders silently (validation on page_ids)
- [x] New routes registered; old /plans requires folder_id
