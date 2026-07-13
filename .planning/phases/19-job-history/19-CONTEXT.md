# Phase 19 Context: Job History Tab

## User request (2026-06-02)

Add a **Job History** tab so operators can see past runs: last status, full success vs partial vs failed, errors/warnings, and enough detail to decide whether to re-run or open the report.

## Current behavior (verified)

| Aspect | Today |
|--------|--------|
| Job state | In-memory `jobs: dict = {}` in `app.py` — **lost on Flask restart** |
| Live monitor | `page-job-monitor` — only current job via polling `/api/status/<id>` |
| Nav | Job Monitor link hidden until a job starts (`#navJobMonitor`) |
| Completion | `_finalize_stackct_job` sets `status`: `done` \| `error` \| `cancelled`; optional `warning`, `error`, `partial` in result |
| Reports | Run folder in `OUTPUT_DIR`; linked to job via `result["_run_folder_name"]` |
| Persistence precedent | `stackct_store.sync_runs` table — audit trail pattern already exists |

## What users need to see

1. **List view** — recent jobs (newest first): project name, type (StackCT/PDF), status badge, started/finished time, duration, sheet count, partial/linked flags
2. **Outcome clarity** — distinguish: success, partial success (warning), failed (error), cancelled
3. **Error text** — user-facing `job.error` / `job.warning` (not stack traces)
4. **Drill-down** — expand row or detail panel: last log lines, sheets failed count, link to report if `has_result`
5. **Survive restart** — history must persist in SQLite (same DB file or dedicated `job_store.py`)

## Out of scope (v1)

- Multi-user job ownership / RBAC per job
- Celery queue (ARCH-02) — still background threads
- Full log replay megabytes — cap stored log at ~100 lines JSON
- Re-run job from history (future: one-click "Run again")

## Depends on

- Phase 7 job monitor fields (`current_phase`, `sheets_completed`, structured log)
- Phase 17/18 finalize metadata (`partial`, `linked_sheets_*`, `mode_detail`)
