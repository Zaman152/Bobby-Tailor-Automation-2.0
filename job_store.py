"""
SQLite persistence for job run history. Uses same stackct.db file.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Any, Optional

from config import JOB_HISTORY_RETENTION_DAYS, STACKCT_DB_PATH

logger = logging.getLogger(__name__)

_write_lock = threading.Lock()
_initialized = False

JOB_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_runs (
    job_id              TEXT PRIMARY KEY,
    job_type            TEXT NOT NULL,
    project_name        TEXT,
    status              TEXT,
    outcome             TEXT,
    error_message       TEXT,
    warning_message     TEXT,
    mode                TEXT,
    mode_detail         TEXT,
    started_at          TEXT,
    finished_at         TEXT,
    duration_sec        REAL,
    sheets_total        INTEGER,
    sheets_succeeded    INTEGER,
    sheets_failed       INTEGER,
    linked_sheets_added INTEGER,
    progress_final      INTEGER,
    run_folder          TEXT,
    report_json_path    TEXT,
    log_tail_json       TEXT,
    meta_json           TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_runs_started ON job_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_runs_outcome ON job_runs(outcome);
"""


def _get_connection() -> sqlite3.Connection:
    STACKCT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STACKCT_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema() -> None:
    global _initialized
    if _initialized:
        return
    with _write_lock:
        if _initialized:
            return
        conn = _get_connection()
        try:
            conn.executescript(JOB_RUNS_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialized = True


def init_schema() -> None:
    """Public alias for schema initialization."""
    _ensure_schema()


def _derive_outcome(job: dict) -> str:
    status = job.get("status")
    result = job.get("result") if isinstance(job.get("result"), dict) else {}

    if status == "cancelled" or result.get("_cancelled"):
        return "cancelled"
    if status == "error":
        return "failed"
    if status == "done":
        if result.get("partial") or job.get("warning"):
            return "partial"
        return "success"
    return "failed"


def _compute_duration_sec(started_at: Optional[str], finished_at: Optional[str]) -> Optional[float]:
    if not started_at or not finished_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at)
        return (end - start).total_seconds()
    except ValueError:
        return None


def save_job_run(job: dict, job_id: str, job_type: str) -> None:
    _ensure_schema()

    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    log_entries = job.get("log") or []
    log_tail = log_entries[-80:] if len(log_entries) > 80 else log_entries

    started_at = job.get("started_at")
    finished_at = job.get("finished_at")
    duration_sec = _compute_duration_sec(started_at, finished_at)

    row = {
        "job_id": job_id,
        "job_type": job_type,
        "project_name": job.get("project") or job.get("project_name"),
        "status": job.get("status"),
        "outcome": _derive_outcome(job),
        "error_message": job.get("error"),
        "warning_message": job.get("warning"),
        "mode": job.get("mode"),
        "mode_detail": job.get("mode_detail"),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": duration_sec,
        "sheets_total": result.get("sheets_total") or result.get("total_sheets"),
        "sheets_succeeded": result.get("sheets_succeeded") or result.get("sheets_processed", 0),
        "sheets_failed": len(result.get("sheets_failed") or []),
        "linked_sheets_added": job.get("linked_sheets_count", 0),
        "progress_final": job.get("progress"),
        "run_folder": result.get("_run_folder_name"),
        "report_json_path": None,
        "log_tail_json": json.dumps(log_tail, default=str),
        "meta_json": json.dumps(
            {
                "job_type_ui": job.get("type"),
                "file": job.get("file"),
            },
            default=str,
        ),
    }

    with _write_lock:
        conn = _get_connection()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO job_runs (
                    job_id, job_type, project_name, status, outcome,
                    error_message, warning_message, mode, mode_detail,
                    started_at, finished_at, duration_sec,
                    sheets_total, sheets_succeeded, sheets_failed,
                    linked_sheets_added, progress_final, run_folder,
                    report_json_path, log_tail_json, meta_json
                ) VALUES (
                    :job_id, :job_type, :project_name, :status, :outcome,
                    :error_message, :warning_message, :mode, :mode_detail,
                    :started_at, :finished_at, :duration_sec,
                    :sheets_total, :sheets_succeeded, :sheets_failed,
                    :linked_sheets_added, :progress_final, :run_folder,
                    :report_json_path, :log_tail_json, :meta_json
                )
                """,
                row,
            )
            if JOB_HISTORY_RETENTION_DAYS > 0:
                conn.execute(
                    "DELETE FROM job_runs WHERE started_at < datetime('now', ?)",
                    (f"-{JOB_HISTORY_RETENTION_DAYS} days",),
                )
            conn.commit()
        except Exception:
            logger.exception("Failed to save job run %s", job_id)
            raise
        finally:
            conn.close()


def list_job_runs(
    limit: int = 50,
    offset: int = 0,
    outcome: str | None = None,
) -> list[dict[str, Any]]:
    _ensure_schema()
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    query = """
        SELECT
            job_id, job_type, project_name, status, outcome,
            error_message, warning_message, mode, mode_detail,
            started_at, finished_at, duration_sec,
            sheets_total, sheets_succeeded, sheets_failed,
            linked_sheets_added, progress_final, run_folder,
            report_json_path
        FROM job_runs
    """
    params: list[Any] = []
    if outcome:
        query += " WHERE outcome = ?"
        params.append(outcome)
    query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    conn = _get_connection()
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_job_run(job_id: str) -> dict[str, Any] | None:
    _ensure_schema()
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM job_runs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        log_raw = data.pop("log_tail_json", None)
        if log_raw:
            try:
                data["log_tail"] = json.loads(log_raw)
            except json.JSONDecodeError:
                data["log_tail"] = []
        else:
            data["log_tail"] = []
        meta_raw = data.pop("meta_json", None)
        if meta_raw:
            try:
                data["meta"] = json.loads(meta_raw)
            except json.JSONDecodeError:
                data["meta"] = {}
        return data
    finally:
        conn.close()
