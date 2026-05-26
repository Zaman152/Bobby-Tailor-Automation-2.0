# Phase 13: StackCT Data & Persistence — Verification Checklist

**Goal (outcome):** StackCT project and plan catalog is served from a proper database with TTL sync, so operators avoid repeated browser scrapes for list, sheet counts, and plan preview.

**Verified:** (pending execution)  
**Plans:** 4 (13-01 → 13-04)

---

## Goal-Backward Truths

| # | Observable truth | Verified by |
|---|------------------|-------------|
| T1 | Project dropdown/list loads from DB in &lt;1s without launching browser when data is fresh | T1: curl `/api/projects` timing + logs show no Playwright |
| T2 | Sheet counts visible on project list for synced projects without clicking Preview | T2: UI screenshot / `sheet-counts` API |
| T3 | Preview Plans shows plan checkboxes from DB when TTL fresh (&lt;2s typical) | T3: Network tab — no 30s wait on warm cache |
| T4 | Manual Refresh updates DB and `sync_runs` audit row | T4: DB query + API `fetched_at` changes |
| T5 | Only one StackCT browser login at a time (documented + lock held) | T5: parallel refresh test — second waits |
| T6 | JSON caches migrated; normal path does not read `projects_cache.json` | T6: grep / strace optional |
| T7 | No StackCT credentials stored in SQLite | T7: schema + spot-check DB file |
| T8 | Stale data still usable when live sync fails | T8: disconnect network mid-sync — UI shows stale + warning |

---

## Requirement Coverage (DATA-*)

| Requirement | Description | Plan(s) |
|-------------|-------------|---------|
| DATA-01 | Projects catalog persisted in SQLite under OUTPUT_DIR | 13-01 |
| DATA-02 | Per-project plans (page_id, sheet_name) persisted with TTL | 13-01, 13-02 |
| DATA-03 | `sheet_count` denormalized on project row; API serves without preview | 13-01, 13-03, 13-04 |
| DATA-04 | Sync operations audited in `sync_runs` | 13-01, 13-02 |
| DATA-05 | Single global browser lock for all StackCT catalog sync | 13-02 |
| DATA-06 | Background stale refresh (APScheduler + startup prefetch) | 13-02 |
| DATA-07 | One-time migration from JSON caches | 13-01 |
| DATA-08 | API responses include `from_cache`, `stale`, `syncing` where applicable | 13-03 |
| DATA-09 | UI shows counts on load; preview uses DB when fresh | 13-04 |

---

## Plan Summary

| Plan | Wave | depends_on | Autonomous | Tasks |
|------|------|------------|------------|-------|
| 13-01 | 1 | [] | yes | 2 |
| 13-02 | 2 | 13-01 | yes | 2 |
| 13-03 | 3 | 13-01, 13-02 | yes | 2 |
| 13-04 | 4 | 13-03 | no (human-verify) | 2 + checkpoint |

---

## Wave Structure

| Wave | Plans | Parallel | Notes |
|------|-------|----------|-------|
| 1 | 13-01 | — | Schema + migration |
| 2 | 13-02 | — | Sync service (needs DB) |
| 3 | 13-03 | — | API contract (needs sync) |
| 4 | 13-04 | — | UI (needs API) |

---

## Per-Plan Verification Commands

### 13-01
```bash
python -c "from stackct_store import init_db, list_projects; init_db(); print(len(list_projects()))"
sqlite3 output/stackct.db ".tables"
```

### 13-02
```bash
# With valid .env
python -c "from stackct_sync import sync_projects; print(sync_projects(force=True).get('from_cache'))"
sqlite3 output/stackct.db "SELECT sync_type, status, records_written FROM sync_runs ORDER BY id DESC LIMIT 3;"
```

### 13-03
```bash
curl -s http://localhost:5050/api/projects | python -m json.tool | head -30
curl -s http://localhost:5050/api/projects/sheet-counts | python -m json.tool
curl -s "http://localhost:5050/api/projects/PROJECT_ID/plans" | python -m json.tool | head -20
```

### 13-04
Manual UAT per 13-04-PLAN checkpoint (Projects page flows).

---

## Dimension Checks (Plan Checker Self-Assessment)

| Dimension | Status | Notes |
|-----------|--------|-------|
| Requirement coverage | PASS | DATA-01–09 mapped |
| Task completeness | PASS | All tasks have files, action, verify, done |
| Dependency correctness | PASS | Linear 01→04; no cycles |
| Key links planned | PASS | store↔sync↔browser↔API↔UI |
| Scope sanity | PASS | 2 tasks/plan, ~50% context each |
| must_haves derivation | PASS | Truths user-observable |

---

## Out of Scope (Phase 13)

- Replacing DOM scrape with internal StackCT HTTP (optional spike only)
- Redis/Celery (v2)
- FastAPI migration (v2)
- Bulk sync all projects' plans automatically (future enhancement post-13-02)

---

## Recommendation

Plans verified for execution. Run: `/gsd-execute-phase 13`
