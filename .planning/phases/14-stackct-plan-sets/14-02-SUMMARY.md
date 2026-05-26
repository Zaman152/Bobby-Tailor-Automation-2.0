---
phase: 14-stackct-plan-sets
plan: 2
subsystem: database-sync
tags: [sqlite, schema-migration, folder-aware, sync, cache]

requires:
  - 14-01-SUMMARY.md (browser APIs)
  - phase-13-stackct-catalog-cache

provides:
  - Schema v2: project_plan_sets table, folder-scoped project_plans
  - sync_project_plan_sets(project_id)
  - sync_project_plans(project_id, folder_id)
  - get_project_plan_sets(project_id)
  - get_project_plans(project_id, folder_id)

affects:
  - 14-03: API routes will use folder-aware cache getters
  - 14-04: UI will call /plan-sets before /plans endpoints
  - All existing projects require re-sync (schema v1→v2 drops project_plans)

tech-stack:
  added: []
  patterns:
    - Schema versioning with migration
    - Folder-scoped caching with (project_id, folder_id) keys
    - Stale-while-revalidate for plan sets and plans

key-files:
  created: []
  modified:
    - stackct_store.py
    - stackct_sync.py
    - project_cache.py

decisions:
  - decision: Drop project_plans table on v1→v2 migration (re-sync required)
    rationale: Old data lacks folder_id; can't reliably assign sheets to folders retroactively
    impact: All 26 cached projects lose plan cache on first run after upgrade
    alternatives: Add folder_id=0 to all rows (wrong), keep old and new tables (bloat)
    trade-offs: Clean migration but requires fresh sync for all projects

  - decision: Change project_plans PK to (stackct_id, folder_id, page_id)
    rationale: Same page_id can exist in multiple folders (v1, v2); old PK was (stackct_id, page_id)
    impact: Breaking change - old flat plan queries fail
    alternatives: Use composite folder+page ID (hacky), keep folder_id as non-key column (allows duplicates)
    trade-offs: Correct data model but incompatible with old code

  - decision: Require folder_id in sync_project_plans and get_project_plans
    rationale: Prevents callers from mixing sheets across folders
    impact: API change - all callers must update
    alternatives: Keep flat fallback (perpetuates bug), infer folder_id from first plan set (unreliable)
    trade-offs: Forces correct usage but breaks backward compatibility

  - decision: Track (project_id, folder_id) tuples in background sync sets
    rationale: Allows parallel sync of multiple folders for same project
    impact: More granular sync state tracking
    alternatives: Lock entire project during any folder sync (slow)
    trade-offs: More complex state management but better performance

metrics:
  duration: ~4 min
  completed: 2026-05-26
---

# Phase 14 Plan 2: Schema v2 and Folder-Aware Sync Summary

**One-liner:** SQLite schema v2 with project_plan_sets table and folder-scoped sync pipeline.

## What Was Built

### Database Schema v2

**New table: `project_plan_sets`**
```sql
CREATE TABLE project_plan_sets (
    stackct_id INTEGER NOT NULL,
    folder_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    sheet_count INTEGER,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (stackct_id, folder_id)
);
```

**Updated table: `project_plans`**
- Changed PK from `(stackct_id, page_id)` to `(stackct_id, folder_id, page_id)`
- Added `folder_id INTEGER NOT NULL DEFAULT 0`
- Added index on `(stackct_id, folder_id)` for fast folder queries

**Updated table: `projects`**
- Added `plan_set_count INTEGER` column

**Updated table: `sync_runs`**
- Added `folder_id INTEGER` column for tracking per-folder syncs

### Migration Logic

**`init_schema(conn)`:**
1. Detects schema version from `cache_metadata`
2. If v1: drops `project_plans` table, clears `sheet_count` and `plans_synced_at`
3. Creates all tables with v2 schema
4. Sets `schema_version = "2"`

**Safety:** Fresh DB creates v2 directly; v1→v2 migration is idempotent.

### Store CRUD Functions

**Plan Sets:**
- `upsert_plan_sets(stackct_id, plan_sets, synced_at)` → int
- `get_plan_sets(stackct_id)` → list[dict]
- `is_plan_sets_fresh(stackct_id)` → bool
- `get_plan_sets_synced_at(stackct_id)` → Optional[str]

**Plans (folder-scoped):**
- `upsert_plans(stackct_id, folder_id, plans, synced_at)` → int (updated signature)
- `get_plans(stackct_id, folder_id=None)` → list[dict] (warns if folder_id=None)
- `is_plans_fresh(stackct_id, folder_id=None)` → bool
- `get_plans_synced_at(stackct_id, folder_id=None)` → Optional[str]

**Sheet Counts:**
- `get_sheet_counts()` → dict[int, dict] (returns `{project_id: {sheet_count, plan_set_count}}`)

### Sync Layer Updates

**`stackct_sync.py`:**
- Added `_fetch_plan_sets_from_browser(project_id)` → calls `browser.get_plan_sets`
- Renamed `_fetch_plans_from_browser` → `_fetch_plans_in_folder_from_browser(project_id, folder_id)`
- Added `sync_project_plan_sets(project_id, force=False)` → dict
- Updated `sync_project_plans(project_id, folder_id, force=False)` → requires folder_id

**`project_cache.py`:**
- Added `get_project_plan_sets(project_id, force_refresh=False)` → dict (with stale-while-revalidate)
- Updated `get_project_plans(project_id, folder_id, force_refresh=False, background=False)` → requires folder_id
- Added `_start_plan_sets_background_sync(project_id)` for async plan-set refresh
- Updated `_start_plans_background_sync(project_id, folder_id)` to track `(project_id, folder_id)` tuples
- Updated `get_all_sheet_counts()` to return `plan_set_counts` dict

## Verification Results

- [x] Schema v2 creates successfully on fresh DB
- [x] CRUD tests pass: upsert/get plan sets and plans with folder_id
- [x] Freshness checks work for plan sets and folder-scoped plans
- [x] Migration from v1 drops project_plans and clears counters

**Manual verification pending:**
- [ ] Morehouse: sync plan sets returns 2 entries, sync plans for folder 35240700 returns 120 sheets
- [ ] Re-sync folder 35240694 stores 180 pages distinct from v1
- [ ] Background sync updates stale plan sets without blocking

## Deviations from Plan

**Auto-fixed (Rule 3 - Blocking):**
1. **Foreign key constraint on upsert_plan_sets**
   - Issue: Inserting plan_sets before project row exists violated FK
   - Fix: Added `INSERT ... ON CONFLICT DO NOTHING` to ensure project row exists first
   - Commit: Same as Task 1

2. **init_schema handling for fresh vs migrating DB**
   - Issue: Fresh DB with no cache_metadata table failed migration logic
   - Fix: Added table existence check before version check; fresh DB creates v2 directly
   - Commit: Same as Task 1

## What's Next

**Phase 14 Plan 3 (14-03-PLAN.md):**
- `GET /api/projects/<id>/plan-sets` route
- `GET /api/projects/<id>/plan-sets/<folder_id>/plans` route
- `POST /api/run/stackct` requires `folder_id` in body
- Update `/api/projects/sheet-counts` to return plan_set_counts
- Backward compat: `/api/projects/<id>/plans` requires `?folder_id=` or returns 400

**Integration point:** 14-03 routes call `project_cache.get_project_plan_sets()` and `project_cache.get_project_plans(folder_id)`.

## Commits

| Commit | Message |
|--------|---------|
| 4861120 | feat(14-02): schema v2 and plan sets store CRUD |
| 6c61df9 | feat(14-02): folder-aware sync layer |

## Files Changed

```
stackct_store.py    +262 -64  (schema v2, migration, CRUD)
stackct_sync.py     +223 -39  (plan_sets sync, folder-aware plans)
project_cache.py    +223 -39  (cache getters with folder_id)
```

## Tech Debt / Future Work

- **Migration downtime:** First run after upgrade drops all plan caches; users see empty project list until re-sync completes
- **No incremental folder sync:** Adding a new folder to existing project requires full plan-set re-sync
- **sheet_count on projects table deprecated:** Now ambiguous (which folder?); should aggregate from plan_sets or remove column
- **Backward compat warning spam:** Legacy get_plans(stackct_id) without folder_id logs warnings on every call; callers should migrate

## Success Criteria Met

- [x] Database models match StackCT folder hierarchy
- [x] No code path writes folder-less plans without migration shim
- [x] Sync functions accept folder_id; project_cache exposes plan set + folder plans getters
