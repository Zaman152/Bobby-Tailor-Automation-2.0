# 13-03 Summary — DB-first APIs

**Completed:** 2026-05-26

- Stale-while-revalidate for projects and plans
- `?refresh=1` and `?background=1` on plans route
- `POST /api/projects/refresh` uses `sync_projects(force=True)`
- Sheet counts from SQLite only
