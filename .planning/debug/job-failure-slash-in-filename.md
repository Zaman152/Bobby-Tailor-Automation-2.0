---
slug: job-failure-slash-in-filename
status: root_cause_found
fix_applied: 2026-06-01
fix_summary: "Per-sheet try/except, _safe_sheet_filename, partial reports, UI job errors — see scraper.py app.py"
created: 2026-06-01
symptoms:
  expected: Jobs complete and generate reports in output/
  actual: Jobs stall then fail mid-run (~71% on 45-sheet run); no takeoff.json produced
  errors: FileNotFoundError when saving screenshot — sheet name contains `/`
  reproduction: Run StackCT job on plan set with sheet "I-4.1 - ELECTRICAL/ COMMUNICATION PLAN"
---

# Debug: Jobs fail mid-run, no reports

## ROOT CAUSE FOUND

**Sheet names containing `/` are used raw in screenshot filenames**, creating invalid nested paths.

Example crash:
```
FileNotFoundError: output/screenshots/.../032_I-4.1 - ELECTRICAL/ COMMUNICATION PLAN.jpg
```

Python interprets `ELECTRICAL/` as a subdirectory that was never created.

### Evidence

| Job ID | Sheets | Failed at | Progress | Error |
|--------|--------|-----------|----------|-------|
| 9c279775 | 22 | sheet 9 | ~40% | Same `/` in `I-4.1 - ELECTRICAL/ COMMUNICATION PLAN` |
| 205c26c6 | 45 | sheet 32 | **71%** | Same sheet name pattern |
| b05ca691 | 45 | in progress at log end | 12/45 | Different naming (`ELECTRICAL-` with hyphen) — passed sheet 10 |

**Reports never generated** because `generate_report()` only runs after the full sheet loop completes. Any uncaught exception aborts the entire job — partial screenshots exist but no CSV/JSON output.

## Secondary finding: Screenshot reuse NOT wired into scraper

`sheet_preview.py` has `find_screenshot_paths()` for **UI thumbnails only**.  
`scraper.py` **always** creates a new timestamped folder and re-downloads every sheet from StackCT blob storage. User expectation (reuse existing captures) is **not implemented** in the run pipeline.

## Architecture: Current workflow (interleaved)

```
User clicks Run
  → POST /api/run/stackct (background thread)
  → run_project_scrape()
       1. Launch Playwright, login StackCT
       2. Discover pages (DB cache or browser)
       3. FOR EACH sheet (sequential):
            a. Screenshot/download blob → output/screenshots/{project}_{ts}/NNN_{sheet}.jpg
            b. analyze_drawing() → Claude Vision API (sync, ~10-30s/sheet)
            c. apply_estimation_tables() per sheet
       4. resolve_cross_references() across all sheets
       5. generate_report() → output/{project}_{ts}/takeoff.json, CSVs, summary.txt
       6. Close browser
```

Progress % = `current_sheet_index / total_sheets` (not phases weighted).

## Recommended fixes

1. **P0 — Sanitize sheet names for filenames** (replace `/`, `\`, etc. with `-`)
2. **P1 — Don't abort entire job on one sheet failure** — skip sheet, continue, report partial
3. **P2 — Screenshot reuse** — before download, check `find_screenshot_paths()` for existing file
4. **P3 — Optional two-phase mode** — capture all screenshots first, then batch Claude analysis (better for demos, easier retry)
