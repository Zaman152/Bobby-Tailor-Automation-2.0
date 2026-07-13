# Phase 17 Research: Production Takeoff Pipeline

## Current architecture (verified in code)

| Step | Module | Behavior |
|------|--------|----------|
| Job start | `app.py` `_stackct_job` | Background thread, in-memory `jobs` dict |
| Orchestration | `scraper.run_project_scrape` | Single loop: capture → analyze per sheet |
| Capture | `browser.download_drawing_image` | Azure blob intercept; fallback canvas screenshot |
| Analyze | `claude_analyzer.analyze_drawing` | Sync Anthropic API call per sheet |
| Report | `reporter.generate_report` | Only after ALL sheets processed |
| Screenshot reuse | `sheet_preview.find_screenshot_paths` | **UI thumbnails only — not used in scraper** |

## Failure modes observed in production demo

| Failure | Cause | Fix tier |
|---------|-------|----------|
| Job dies at sheet N, no report | Uncaught exception (e.g. `/` in filename) | Hotfix: per-sheet resilience ✓ |
| Progress stuck at 71% | Crash on sheet 32/45; UI shows last completed index | Hotfix: error status + message ✓ |
| Re-downloads everything | New timestamp folder every run | Phase 17-01: reuse |
| 45-sheet demo = 30+ min | Interleaved capture+Claude | Phase 17-02: two-phase + reuse |
| UI stops updating on error | `if (job.error) return` in poll | Hotfix ✓ |

## Recommended pipeline (target state)

```
Phase A — CAPTURE (browser, once per stale sheet)
  For each page_id:
    if cached screenshot exists and fresh → skip download
    else → download_drawing_image → save to run manifest

Phase B — ANALYZE (no browser)
  For each page_id in manifest:
    if analysis.json exists and force_reanalyze=false → load cache
    else → analyze_drawing(screenshot_path)

Phase C — REPORT (always if ≥1 success)
  cross_references → generate_report → partial metadata if failures
```

## Manifest design

Store beside screenshots: `manifest.json`

```json
{
  "project_id": 7413817,
  "project_name": "Baking Social - The Battery",
  "folder_id": 35218946,
  "created_at": "ISO8601",
  "pages": [
    {
      "page_id": 715544736,
      "sheet_name": "I-4-1 - ELECTRICAL- COMMUNICATION PLAN",
      "screenshot": "010_I-4-1 - ELECTRICAL- COMMUNICATION PLAN.jpg",
      "capture_status": "ok|skipped|failed",
      "analysis_status": "pending|ok|failed"
    }
  ]
}
```

## Screenshot reuse strategy

1. On run start, call `find_screenshot_paths(project_id, project_name, pages)` 
2. Build map `{page_id: Path}` from newest matching run folder
3. Config flag `REUSE_SCREENSHOTS=true` (default true) — skip blob download if file exists and size > 1KB
4. Still create new run folder but **copy or symlink** cached files (prefer copy for portability on VPS)

## Progress model improvement

Weighted progress for UI:
- Capture phase: 0–40% of bar
- Analyze phase: 40–95%
- Report: 95–100%

Expose `job.current_phase` in `/api/status` for monitor labels.

## Browser lock coordination

Phase 13 `stackct_sync` holds global browser lock. Capture phase must acquire same lock or queue behind sync — document in 17-04.

## Testing strategy

- Unit: manifest read/write, reuse map, safe filenames (exists)
- Integration: mock browser, run analyze-only from fixture screenshots
- UAT: 17-UAT.md — 10-sheet subset, kill mid-run, verify partial report

## References

- Debug report: `.planning/debug/job-failure-slash-in-filename.md`
- `sheet_preview.py` — reuse matching logic
- `scraper.py` — orchestration point for refactor
