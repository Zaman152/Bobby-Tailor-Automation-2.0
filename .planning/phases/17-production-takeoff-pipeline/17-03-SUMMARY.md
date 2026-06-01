---
phase: 17-production-takeoff-pipeline
plan: "03"
subsystem: scraper-recovery
tags: [crash-recovery, analyze-only, manifest, api, resume]
requires: ["17-02"]
provides: ["analyze-only-api", "run-analyze-from-manifest", "analysis-cache"]
affects: ["17-04", "17-05"]
tech-stack:
  added: []
  patterns: ["analyze-only-mode", "per-page-analysis-cache", "manifest-driven-recovery"]
key-files:
  created:
    - tests/test_scraper_analyze_manifest.py
  modified:
    - scraper.py
    - app.py
    - README.md
decisions:
  - "{page_id}_analysis.json cache written beside screenshot on success; missing cache triggers re-analyze even when manifest says ok"
  - "analyze_only auto-discovers latest run folder by project_name prefix + mtime sort; explicit manifest_dir overrides"
  - "mode_detail field on job dict: 'full' | 'analyze_only' for UI/log differentiation"
  - "Page-ID/folder validation skipped for analyze-only requests (no new capture, no folder constraint)"
  - "force=False default: skips ok+cached pages; force=True re-runs all regardless of status"
metrics:
  duration: "~7 min"
  completed: "2026-06-02"
---

# Phase 17 Plan 03: Crash Recovery / Analyze-Only Summary

**One-liner:** Analyze-only pass from manifest.json — resume mid-run crashes and re-run Claude without browser using per-page analysis cache.

## What Was Built

### `run_analyze_from_manifest()` (scraper.py)

New async function that re-runs the Claude analysis pass from an existing run directory without launching a browser.

**Key behaviors:**
- Accepts `screenshots_dir` (directory) or `manifest_path_override` (explicit file)
- Skips pages with `analysis_status="ok"` if `{page_id}_analysis.json` cache exists
- Re-analyzes if cache missing (rebuilds it) or `force=True`
- Retries all `failed` and `pending` pages unconditionally
- Handles missing screenshots gracefully (marks failed, partial report continues)
- Writes `{page_id}_analysis.json` beside screenshot after each successful analysis
- Updates `manifest.json` after every page (crash-safe incremental progress)
- Generates full report (same shape as `run_project_scrape` result)

### API extension (app.py)

`POST /api/run/stackct` extended with:
- `analyze_only: bool` — skip capture pass entirely
- `manifest_dir: str` — explicit run folder (absolute or relative to `output/screenshots/`)

Internal additions:
- `_resolve_manifest_dir()` helper — finds manifest dir by explicit path or latest-mtime auto-discovery
- `_stackct_job()` extended with `analyze_only` / `manifest_dir` kwargs
- `mode_detail: "full" | "analyze_only"` added to job dict

### README documentation

New **API Reference** section documents both full-run and analyze-only request formats with examples.

### Tests (tests/test_scraper_analyze_manifest.py)

15 tests across 5 classes:
- `TestRunAnalyzeFromManifest` — core behavior, no-browser guarantee, error cases
- `TestSkipAlreadyAnalyzed` — skip/retry logic for ok/failed/pending pages, force=True
- `TestAnalysisCache` — cache written on success, not written on error
- `TestMissingScreenshot` — graceful handling, partial reports
- `TestManifestUpdates` — manifest persisted after each page

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Cache file `{page_id}_analysis.json` beside screenshot | Decoupled from manifest; survives manifest edits; easy to inspect/delete individually |
| `analysis_status=ok` + no cache → re-analyze | Rebuilds cache rather than silently missing data from report |
| Auto-discover latest run folder by `project_name` prefix + mtime | Zero-config UX for the common "re-analyze last crash" case |
| `mode_detail: "full" \| "analyze_only"` on job dict | Lets UI/logs distinguish run types without parsing log text |
| Page-ID/folder validation skipped for analyze-only | Manifest already has the correct page set; re-validation would require DB access for no benefit |

## Verification Results

```
tests/test_scraper_analyze_manifest.py  15 passed
tests/test_scraper_two_phase.py          4 passed  (regression: no regressions)
tests/test_capture_manifest.py          10 passed  (regression: no regressions)
Total: 29 passed in 0.34s
```

Must-have artifacts confirmed:
- `app.py` contains `analyze_only` ✓
- `scraper.py` contains `run_analyze_from_manifest` ✓
- API accepts `analyze_only` flag on `/api/run/stackct` ✓
- Analyze-only mode re-runs Claude on existing manifest without browser login ✓
- Failed analysis sheets can be retried without re-capture ✓

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

17-04 can proceed. `run_analyze_from_manifest` is importable and tested; API surface is stable.
