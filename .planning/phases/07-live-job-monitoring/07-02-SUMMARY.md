---
phase: "07-live-job-monitoring"
plan: "2"
subsystem: "api"
tags: ["flask", "job-monitoring", "structured-log", "active-job"]
requires: ["07-01"]
provides: ["extended job schema", "enriched /api/status", "GET /api/jobs/active"]
affects: ["07-03"]
tech-stack:
  added: []
  patterns: ["structured-job-state", "active-job-polling"]
key-files:
  created: []
  modified: ["app.py"]
decisions:
  - "Log arrays capped at 200 entries trimmed to 150 — prevents memory growth on long jobs"
  - "sheet_log in status response: last 5 completed sheets with extraction counts"
metrics:
  duration: "2min"
  completed: "2026-05-26"
---

# Phase 07 Plan 02: Job Status API Enhancement Summary

**One-liner:** Extended job dict with current_sheet/sheets_completed/started_at, updated /api/status to return enriched live data, added /api/jobs/active for sidebar mini-card.

## What Was Built

- job dict fields: started_at, current_sheet {index, total, name, phase}, sheets_completed []
- _stackct_job log()/progress() handlers consuming structured entries from 07-01
- _pdf_job same enriched log/progress handlers
- /api/status/<id> returning: started_at, current_sheet, sheets_completed count, sheet_log, structured log
- GET /api/jobs/active returning running job or {active: false}

## Deviations from Plan

None.
