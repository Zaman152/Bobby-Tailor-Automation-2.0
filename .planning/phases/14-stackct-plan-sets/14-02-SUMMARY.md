# 14-02 Summary — Schema v2 & folder-aware sync

**Status:** Complete

## Delivered

- `stackct_store.py`: `project_plan_sets`, folder-scoped `project_plans`, `upsert_plan_sets`, `get_plan_sets`, `is_plan_sets_fresh`
- `stackct_sync.py`: `sync_project_plan_sets`, `sync_project_plans(project_id, folder_id)`
- `project_cache.py`: `get_project_plan_sets`, folder-scoped `get_project_plans`

## UAT note

Morehouse `7416168` synced to DB: 2 plan sets (v1=120, v2=180 sheets).
