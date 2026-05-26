---
phase: "07-live-job-monitoring"
plan: "3"
subsystem: "ui"
tags: ["html", "javascript", "mini-card", "polling"]
requires: ["07-02"]
provides: ["active-job mini-card", "pollActiveJob()", "visibility-aware polling"]
affects: ["08-01"]
tech-stack:
  added: []
  patterns: ["fixed-position-widget", "visibility-aware-polling"]
key-files:
  created: []
  modified: ["templates/index.html"]
decisions:
  - "Fixed-position bottom-right placement works with existing tab layout, integrates in sidebar in Phase 8"
  - "Orange left border (--accent-construction) matches Master.md spec for active job indicators"
  - "1.5s polling interval — responsive without excessive requests"
metrics:
  duration: "3min"
  completed: "2026-05-26"
---

# Phase 07 Plan 03: Active Job Mini-Card Summary

**One-liner:** Added fixed-position mini-card with pulsing status dot, progress bar, sheet count (N/M), and visibility-aware 1.5s polling of /api/jobs/active.

## Deviations from Plan

- Implemented as fixed bottom-right widget instead of sidebar footer slot — sidebar doesn't exist yet (Phase 8). Will be moved to sidebar in 08-01.
