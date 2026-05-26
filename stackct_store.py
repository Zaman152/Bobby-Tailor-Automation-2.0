"""
SQLite persistence for StackCT project catalog and plan lists.

No secrets are stored here — StackCT credentials remain in .env only.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from config import OUTPUT_DIR, STACKCT_CACHE_TTL_HOURS, STACKCT_DB_PATH

logger = logging.getLogger(__name__)

_write_lock = threading.Lock()
_initialized = False

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    stackct_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    sheet_count INTEGER,
    plans_synced_at TEXT,
    projects_synced_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_plans (
    stackct_id INTEGER NOT NULL,
    page_id INTEGER NOT NULL,
    sheet_name TEXT NOT NULL DEFAULT '',
    sheet_type TEXT,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (stackct_id, page_id),
    FOREIGN KEY (stackct_id) REFERENCES projects(stackct_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type TEXT NOT NULL,
    project_id INTEGER,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    records_written INTEGER DEFAULT 0,
    error_message TEXT,
    from_cache_fallback INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cache_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plans_project ON project_plans(stackct_id);
"""


def get_connection() -> sqlite3.Connection:
    STACKCT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STACKCT_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    row = conn.execute(
        "SELECT value FROM cache_metadata WHERE key = 'schema_version'"
    ).fetchone()
    if not row:
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO cache_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ("schema_version", "1", now),
        )
    conn.commit()


def _now() -> str:
    return datetime.now().isoformat()


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _is_fresh(ts: Optional[str]) -> bool:
    parsed = _parse_iso(ts)
    if not parsed:
        return False
    return datetime.now() - parsed <= timedelta(hours=STACKCT_CACHE_TTL_HOURS)


def get_metadata(key: str) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM cache_metadata WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None


def set_metadata(key: str, value: str) -> None:
    now = _now()
    with _write_lock:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cache_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, now),
            )
            conn.commit()


def is_projects_fresh() -> bool:
    return _is_fresh(get_metadata("projects_synced_at"))


def is_plans_fresh(stackct_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT plans_synced_at FROM projects WHERE stackct_id = ?",
            (stackct_id,),
        ).fetchone()
        if not row:
            return False
        return _is_fresh(row["plans_synced_at"])


def record_sync_run(sync_type: str, project_id: Optional[int] = None) -> int:
    now = _now()
    with _write_lock:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO sync_runs (sync_type, project_id, status, started_at)
                VALUES (?, ?, 'running', ?)
                """,
                (sync_type, project_id, now),
            )
            conn.commit()
            return int(cur.lastrowid)


def finish_sync_run(
    run_id: int,
    status: str,
    records_written: int = 0,
    error_message: Optional[str] = None,
    from_cache_fallback: bool = False,
) -> None:
    with _write_lock:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET status = ?, finished_at = ?, records_written = ?,
                    error_message = ?, from_cache_fallback = ?
                WHERE id = ?
                """,
                (
                    status,
                    _now(),
                    records_written,
                    error_message,
                    1 if from_cache_fallback else 0,
                    run_id,
                ),
            )
            conn.commit()


def upsert_projects(projects: list[dict], synced_at: str) -> int:
    now = _now()
    count = 0
    with _write_lock:
        with get_connection() as conn:
            for p in projects:
                pid = int(p.get("id", p.get("stackct_id", 0)))
                if not pid:
                    continue
                name = p.get("name") or f"Project_{pid}"
                conn.execute(
                    """
                    INSERT INTO projects (
                        stackct_id, name, projects_synced_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(stackct_id) DO UPDATE SET
                        name = excluded.name,
                        projects_synced_at = excluded.projects_synced_at,
                        updated_at = excluded.updated_at
                    """,
                    (pid, name, synced_at, now, now),
                )
                count += 1
            conn.commit()
    set_metadata("projects_synced_at", synced_at)
    return count


def upsert_plans(stackct_id: int, plans: list[dict], synced_at: str) -> int:
    now = _now()
    with _write_lock:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM project_plans WHERE stackct_id = ?", (stackct_id,)
            )
            for plan in plans:
                page_id = int(plan.get("page_id", 0))
                if not page_id:
                    continue
                sheet_name = plan.get("sheet_name") or ""
                sheet_type = plan.get("sheet_type")
                conn.execute(
                    """
                    INSERT INTO project_plans (
                        stackct_id, page_id, sheet_name, sheet_type, synced_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (stackct_id, page_id, sheet_name, sheet_type, synced_at),
                )
            sheet_count = len(plans)
            conn.execute(
                """
                UPDATE projects
                SET sheet_count = ?, plans_synced_at = ?, updated_at = ?
                WHERE stackct_id = ?
                """,
                (sheet_count, synced_at, now, stackct_id),
            )
            conn.execute(
                """
                INSERT INTO projects (
                    stackct_id, name, sheet_count, plans_synced_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(stackct_id) DO UPDATE SET
                    sheet_count = excluded.sheet_count,
                    plans_synced_at = excluded.plans_synced_at,
                    updated_at = excluded.updated_at
                """,
                (
                    stackct_id,
                    f"Project_{stackct_id}",
                    sheet_count,
                    synced_at,
                    now,
                    now,
                ),
            )
            conn.commit()
    return len(plans)


def list_projects() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT stackct_id, name, sheet_count, plans_synced_at, projects_synced_at
            FROM projects ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    return [
        {
            "id": r["stackct_id"],
            "name": r["name"],
            "sheet_count": r["sheet_count"],
            "plans_synced_at": r["plans_synced_at"],
            "projects_synced_at": r["projects_synced_at"],
        }
        for r in rows
    ]


def get_plans(stackct_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT page_id, sheet_name, sheet_type
            FROM project_plans WHERE stackct_id = ?
            ORDER BY sheet_name COLLATE NOCASE
            """,
            (stackct_id,),
        ).fetchall()
    return [
        {
            "page_id": r["page_id"],
            "sheet_name": r["sheet_name"],
            "sheet_type": r["sheet_type"],
        }
        for r in rows
    ]


def get_plans_synced_at(stackct_id: int) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT plans_synced_at FROM projects WHERE stackct_id = ?",
            (stackct_id,),
        ).fetchone()
        return row["plans_synced_at"] if row else None


def get_sheet_counts() -> dict[int, int]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT stackct_id, sheet_count FROM projects
            WHERE sheet_count IS NOT NULL
            """
        ).fetchall()
    return {int(r["stackct_id"]): int(r["sheet_count"]) for r in rows}


def project_count() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()
        return int(row["c"]) if row else 0


def migrate_from_json_caches() -> dict[str, int]:
    """Import legacy JSON caches into SQLite (idempotent)."""
    stats = {"projects_imported": 0, "plans_files_imported": 0}
    if project_count() > 0:
        logger.info("Projects table already populated — skipping JSON project import")
    else:
        cache_file = Path(OUTPUT_DIR) / "projects_cache.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                projects = data.get("projects") or []
                fetched_at = data.get("fetched_at") or _now()
                stats["projects_imported"] = upsert_projects(projects, fetched_at)
            except Exception as e:
                logger.warning(f"Project JSON migration failed: {e}")

    plans_dir = Path(OUTPUT_DIR) / "plans_cache"
    if plans_dir.is_dir():
        for path in plans_dir.glob("*.json"):
            if path.name.startswith("_"):
                continue
            try:
                data = json.loads(path.read_text())
                pid = int(data.get("project_id") or path.stem)
                plans = data.get("plans") or []
                fetched_at = data.get("fetched_at") or _now()
                if plans and not get_plans(pid):
                    upsert_plans(pid, plans, fetched_at)
                    stats["plans_files_imported"] += 1
                elif plans:
                    upsert_plans(pid, plans, fetched_at)
                    stats["plans_files_imported"] += 1
            except Exception as e:
                logger.warning(f"Plan JSON migration failed for {path}: {e}")

    return stats


def init_db() -> None:
    global _initialized
    if _initialized:
        return
    with get_connection() as conn:
        init_schema(conn)
    if get_metadata("migrated_from_json") != "1":
        stats = migrate_from_json_caches()
        logger.info(f"JSON cache migration: {stats}")
        set_metadata("migrated_from_json", "1")
    _initialized = True
