---
phase: "04-stackct-plan-selection"
plan: "1"
subsystem: "api"
tags: ["flask", "project-cache", "plans-api"]
requires: ["02-01"]
provides: ["GET /api/projects/<id>/plans", "get_project_plans()"]
affects: ["04-03", "09-01"]
tech-stack:
  added: []
  patterns: ["sync-wrapper-for-async"]
key-files:
  created: []
  modified: ["project_cache.py", "app.py"]
decisions:
  - "Use asyncio.new_event_loop() for sync wrapper — consistent with existing project_cache pattern"
  - "Return {plans, project_id} shape matching existing cache API conventions"
metrics:
  duration: "2min"
  completed: "2026-05-26"
---

# Phase 04 Plan 01: Plans Fetching API Summary

**One-liner:** Added `get_project_plans()` + `GET /api/projects/<id>/plans` reusing browser's `get_all_page_ids()`.

## What Was Built

- `_fetch_pages_for_project(project_id)` — async function in `project_cache.py` that logs in and calls `browser.get_all_page_ids()`
- `get_project_plans(project_id)` — sync wrapper returning `{plans: [{page_id, sheet_name}], project_id}` or `{plans: [], error: str}`
- `GET /api/projects/<int:project_id>/plans` route in `app.py` returning JSON plan list

## Verification

- ✅ `from project_cache import get_project_plans` — import ok
- ✅ `from app import app` — Flask app ok
- ✅ Pattern `get_project_plans` in project_cache.py
- ✅ Pattern `api/projects.*plans` in app.py

## Deviations from Plan

None — plan executed exactly as written.
