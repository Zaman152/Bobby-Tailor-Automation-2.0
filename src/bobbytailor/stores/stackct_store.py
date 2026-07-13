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
    plan_set_count INTEGER,
    plans_synced_at TEXT,
    projects_synced_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_plan_sets (
    stackct_id INTEGER NOT NULL,
    folder_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    sheet_count INTEGER,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (stackct_id, folder_id),
    FOREIGN KEY (stackct_id) REFERENCES projects(stackct_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_plans (
    stackct_id INTEGER NOT NULL,
    folder_id INTEGER NOT NULL DEFAULT 0,
    page_id INTEGER NOT NULL,
    sheet_name TEXT NOT NULL DEFAULT '',
    sheet_type TEXT,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (stackct_id, folder_id, page_id),
    FOREIGN KEY (stackct_id) REFERENCES projects(stackct_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type TEXT NOT NULL,
    project_id INTEGER,
    folder_id INTEGER,
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
CREATE INDEX IF NOT EXISTS idx_plans_folder ON project_plans(stackct_id, folder_id);
CREATE INDEX IF NOT EXISTS idx_plan_sets_project ON project_plan_sets(stackct_id);
"""


def get_connection() -> sqlite3.Connection:
    STACKCT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STACKCT_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    # Check if cache_metadata table exists
    table_check = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cache_metadata'"
    ).fetchone()
    
    if not table_check:
        # Fresh database - just create all tables with v2 schema
        conn.executescript(SCHEMA_SQL)
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO cache_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ("schema_version", "2", now),
        )
        conn.commit()
        logger.info("Created fresh database with schema v2")
        return
    
    # Get current schema version
    row = conn.execute(
        "SELECT value FROM cache_metadata WHERE key = 'schema_version'"
    ).fetchone()
    current_version = row["value"] if row else None
    
    # Migrate from v1 to v2 if needed
    if current_version == "1":
        logger.info("Migrating schema from v1 to v2 (folder-aware plan sets)")
        # Safe migration: drop old project_plans (requires re-sync)
        # Alternative: could preserve data by adding folder_id=0 to all rows,
        # but we don't know which folder they belonged to, so re-sync is cleaner
        conn.execute("DROP TABLE IF EXISTS project_plans")
        conn.execute("UPDATE projects SET sheet_count = NULL, plans_synced_at = NULL")
        
        # Add new columns to projects table
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN plan_set_count INTEGER")
        except Exception:
            pass  # Column might already exist
        
        logger.info("Dropped project_plans table — re-sync required for all projects")
    
    # Create/update schema (handles new tables, indexes)
    conn.executescript(SCHEMA_SQL)
    
    # Set schema version to 2
    now = datetime.now().isoformat()
    if current_version:
        conn.execute(
            """
            UPDATE cache_metadata SET value = ?, updated_at = ?
            WHERE key = 'schema_version'
            """,
            ("2", now),
        )
    else:
        conn.execute(
            "INSERT INTO cache_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ("schema_version", "2", now),
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


def is_plans_fresh(stackct_id: int, folder_id: Optional[int] = None) -> bool:
    """Check if plans are within TTL (optionally scoped to folder)."""
    ts = get_plans_synced_at(stackct_id, folder_id)
    return _is_fresh(ts)


def record_sync_run(
    sync_type: str,
    project_id: Optional[int] = None,
    folder_id: Optional[int] = None,
) -> int:
    now = _now()
    with _write_lock:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO sync_runs (sync_type, project_id, folder_id, status, started_at)
                VALUES (?, ?, ?, 'running', ?)
                """,
                (sync_type, project_id, folder_id, now),
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


def upsert_plan_sets(
    stackct_id: int, plan_sets: list[dict], synced_at: str
) -> int:
    """Store plan sets (folders) for a project."""
    now = _now()
    with _write_lock:
        with get_connection() as conn:
            # Ensure project row exists FIRST (for foreign key).
            # Use DO NOTHING so a real project name from a prior sync is never
            # overwritten with the fallback "Project_{id}" placeholder.
            conn.execute(
                """
                INSERT INTO projects (
                    stackct_id, name, plan_set_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(stackct_id) DO NOTHING
                """,
                (
                    stackct_id,
                    f"Project_{stackct_id}",   # placeholder only; real name preserved
                    0,
                    now,
                    now,
                ),
            )
            # Delete existing plan sets for this project
            conn.execute(
                "DELETE FROM project_plan_sets WHERE stackct_id = ?", (stackct_id,)
            )
            # Insert new plan sets
            for ps in plan_sets:
                folder_id = int(ps.get("folder_id", 0))
                name = ps.get("name") or f"Folder_{folder_id}"
                sheet_count = ps.get("sheet_count")
                conn.execute(
                    """
                    INSERT INTO project_plan_sets (
                        stackct_id, folder_id, name, sheet_count, synced_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (stackct_id, folder_id, name, sheet_count, synced_at),
                )
            # Update project metadata
            plan_set_count = len(plan_sets)
            conn.execute(
                """
                UPDATE projects
                SET plan_set_count = ?, updated_at = ?
                WHERE stackct_id = ?
                """,
                (plan_set_count, now, stackct_id),
            )
            conn.commit()
    return len(plan_sets)


def get_plan_sets(stackct_id: int) -> list[dict]:
    """Get all plan sets for a project."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT folder_id, name, sheet_count, synced_at
            FROM project_plan_sets WHERE stackct_id = ?
            ORDER BY folder_id
            """,
            (stackct_id,),
        ).fetchall()
    return [
        {
            "folder_id": r["folder_id"],
            "name": r["name"],
            "sheet_count": r["sheet_count"],
            "synced_at": r["synced_at"],
        }
        for r in rows
    ]


def is_plan_sets_fresh(stackct_id: int) -> bool:
    """Check if plan sets are within TTL for a project."""
    ts = get_plan_sets_synced_at(stackct_id)
    return _is_fresh(ts)


def get_plan_sets_synced_at(stackct_id: int) -> Optional[str]:
    """Get last sync timestamp for plan sets."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT synced_at FROM project_plan_sets
            WHERE stackct_id = ? ORDER BY synced_at DESC LIMIT 1
            """,
            (stackct_id,),
        ).fetchone()
        return row["synced_at"] if row else None


def upsert_plans(
    stackct_id: int, folder_id: int, plans: list[dict], synced_at: str
) -> int:
    """Store plans for a specific folder in a project."""
    now = _now()
    with _write_lock:
        with get_connection() as conn:
            # Ensure project row exists FIRST (for foreign key)
            conn.execute(
                """
                INSERT INTO projects (
                    stackct_id, name, plans_synced_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(stackct_id) DO UPDATE SET
                    plans_synced_at = excluded.plans_synced_at,
                    updated_at = excluded.updated_at
                """,
                (
                    stackct_id,
                    f"Project_{stackct_id}",
                    synced_at,
                    now,
                    now,
                ),
            )
            # Delete existing plans for this folder
            conn.execute(
                "DELETE FROM project_plans WHERE stackct_id = ? AND folder_id = ?",
                (stackct_id, folder_id),
            )
            # Insert new plans
            for plan in plans:
                page_id = int(plan.get("page_id", 0))
                if not page_id:
                    continue
                sheet_name = plan.get("sheet_name") or ""
                sheet_type = plan.get("sheet_type")
                conn.execute(
                    """
                    INSERT INTO project_plans (
                        stackct_id, folder_id, page_id, sheet_name, sheet_type, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (stackct_id, folder_id, page_id, sheet_name, sheet_type, synced_at),
                )
            conn.commit()
    return len(plans)


def list_projects() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT stackct_id, name, sheet_count, plan_set_count,
                   plans_synced_at, projects_synced_at
            FROM projects ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    return [
        {
            "id": r["stackct_id"],
            "name": r["name"],
            "sheet_count": r["sheet_count"],
            "plan_set_count": r["plan_set_count"],
            "plans_synced_at": r["plans_synced_at"],
            "projects_synced_at": r["projects_synced_at"],
        }
        for r in rows
    ]


def get_plans(stackct_id: int, folder_id: Optional[int] = None) -> list[dict]:
    """
    Get plans for a project.
    If folder_id is provided, return only plans for that folder.
    If folder_id is None, return all plans (legacy behavior - discouraged).
    """
    with get_connection() as conn:
        if folder_id is not None:
            rows = conn.execute(
                """
                SELECT page_id, sheet_name, sheet_type, folder_id
                FROM project_plans WHERE stackct_id = ? AND folder_id = ?
                ORDER BY sheet_name COLLATE NOCASE
                """,
                (stackct_id, folder_id),
            ).fetchall()
        else:
            # Legacy: return all plans across folders
            logger.warning(
                f"get_plans called without folder_id for project {stackct_id} "
                f"— use get_plan_sets + get_plans(folder_id) for folder-scoped access"
            )
            rows = conn.execute(
                """
                SELECT page_id, sheet_name, sheet_type, folder_id
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
            "folder_id": r["folder_id"],
        }
        for r in rows
    ]


def get_plans_synced_at(stackct_id: int, folder_id: Optional[int] = None) -> Optional[str]:
    """Get last sync timestamp for plans (optionally scoped to folder)."""
    with get_connection() as conn:
        if folder_id is not None:
            row = conn.execute(
                """
                SELECT synced_at FROM project_plans
                WHERE stackct_id = ? AND folder_id = ?
                ORDER BY synced_at DESC LIMIT 1
                """,
                (stackct_id, folder_id),
            ).fetchone()
            return row["synced_at"] if row else None
        else:
            # Legacy: project-level timestamp
            row = conn.execute(
                "SELECT plans_synced_at FROM projects WHERE stackct_id = ?",
                (stackct_id,),
            ).fetchone()
            return row["plans_synced_at"] if row else None


def get_sheet_counts() -> dict[int, dict]:
    """
    Get sheet and plan-set counts for all projects.
    Returns: {project_id: {sheet_count, plan_set_count}}
    
    Note: sheet_count may be None for projects with only plan sets synced.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT stackct_id, sheet_count, plan_set_count FROM projects
            WHERE sheet_count IS NOT NULL OR plan_set_count IS NOT NULL
            """
        ).fetchall()
    return {
        int(r["stackct_id"]): {
            "sheet_count": r["sheet_count"],
            "plan_set_count": r["plan_set_count"],
        }
        for r in rows
    }


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
                if plans:
                    upsert_plans(pid, 0, plans, fetched_at)
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
