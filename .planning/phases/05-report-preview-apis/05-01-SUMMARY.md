---
phase: "05-report-preview-apis"
plan: "1"
subsystem: "api"
tags: ["flask", "security", "preview", "path-validation"]
requires: ["01-02"]
provides: ["_validate_preview_path()", "GET /api/reports/<run>/preview/<file>"]
affects: ["10-01"]
tech-stack:
  added: []
  patterns: ["path-containment-check", "content-type-routing"]
key-files:
  created: []
  modified: ["app.py"]
decisions:
  - "Use Path.resolve() + relative_to() — defense in depth against symlink attacks"
  - "Non-existent files return 400 (not 404) to avoid path enumeration"
metrics:
  duration: "2min"
  completed: "2026-05-26"
---

# Phase 05 Plan 01: Preview Endpoint Summary

**One-liner:** Added `_validate_preview_path()` with resolve()+relative_to() security and `/api/reports/<run>/preview/<file>` routing CSV/JSON/TXT responses.

## What Was Built

- `ALLOWED_PREVIEW_EXTENSIONS = {'.csv', '.json', '.txt'}` constant
- `_validate_preview_path()` — validates path containment, logs traversal attempts at WARNING level
- `GET /api/reports/<run_folder>/preview/<filename>` endpoint
- CSV returns `{type, headers, rows, count}` — enhanced by 05-02 with pagination
- JSON returns `{type, data}`
- TXT returns `{type, content}`

## Verification

- ✅ `_validate_preview_path` in app.py
- ✅ `preview_report` route in app.py
- ✅ `relative_to` security pattern in app.py

## Deviations from Plan

Combined 05-01, 05-02, 05-03 into single commit since they all modify app.py and build on each other.
