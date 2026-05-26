"""
StackCT catalog facade — DB-first reads with stackct_sync for live refresh.

Legacy JSON caches (projects_cache.json, plans_cache/) are migrated once into
SQLite via stackct_store.init_db(). Normal API paths do not read JSON files.
"""
import logging
import threading
from datetime import datetime

import stackct_store as store
from stackct_sync import get_browser_lock, sync_project_plans, sync_projects

logger = logging.getLogger(__name__)

# Re-export lock for documentation / tests
_browser_lock = get_browser_lock()

_plans_bg_lock = threading.Lock()
_plans_syncing: set[int] = set()
_projects_bg_started = False


def _ensure_db():
    store.init_db()


def get_projects(force_refresh: bool = False) -> dict:
    """
    Return projects list (DB-first).
    Shape: {projects, fetched_at, from_cache, stale?, syncing?, error?}
    """
    _ensure_db()
    global _projects_bg_started

    if force_refresh:
        return sync_projects(force=True)

    projects = store.list_projects()
    if projects and store.is_projects_fresh():
        return {
            "projects": [{"id": p["id"], "name": p["name"]} for p in projects],
            "fetched_at": store.get_metadata("projects_synced_at"),
            "from_cache": True,
        }

    if projects and not store.is_projects_fresh():
        if not _projects_bg_started:
            _projects_bg_started = True
            threading.Thread(
                target=_background_sync_projects, daemon=True
            ).start()
        return {
            "projects": [{"id": p["id"], "name": p["name"]} for p in projects],
            "fetched_at": store.get_metadata("projects_synced_at"),
            "from_cache": True,
            "stale": True,
            "syncing": True,
        }

    return sync_projects(force=False)


def _background_sync_projects():
    global _projects_bg_started
    try:
        sync_projects(force=True)
    finally:
        _projects_bg_started = False


def prefetch_in_background():
    """On app startup — refresh project catalog if DB empty or stale."""
    _ensure_db()
    if store.is_projects_fresh() and store.project_count() > 0:
        logger.info("StackCT catalog is fresh, skipping prefetch")
        return
    logger.info("Starting background StackCT project sync...")
    threading.Thread(target=lambda: sync_projects(force=False), daemon=True).start()


def get_all_sheet_counts() -> dict:
    """Sheet counts from SQLite (all projects with synced plans)."""
    _ensure_db()
    counts = store.get_sheet_counts()
    synced_at = store.get_metadata("projects_synced_at")
    return {"counts": counts, "synced_at": synced_at}


def _start_plans_background_sync(project_id: int):
    with _plans_bg_lock:
        if project_id in _plans_syncing:
            return
        _plans_syncing.add(project_id)

    def _run():
        try:
            sync_project_plans(project_id, force=True)
        finally:
            with _plans_bg_lock:
                _plans_syncing.discard(project_id)

    threading.Thread(target=_run, daemon=True).start()


def get_project_plans(
    project_id: int,
    force_refresh: bool = False,
    background: bool = False,
) -> dict:
    """
    Return drawing pages for a project (DB-first, stale-while-revalidate).
    """
    _ensure_db()

    if force_refresh:
        return sync_project_plans(project_id, force=True)

    plans = store.get_plans(project_id)
    fetched_at = store.get_plans_synced_at(project_id)

    if plans and store.is_plans_fresh(project_id):
        return {
            "plans": plans,
            "project_id": project_id,
            "from_cache": True,
            "fetched_at": fetched_at,
        }

    if plans and not store.is_plans_fresh(project_id):
        _start_plans_background_sync(project_id)
        return {
            "plans": plans,
            "project_id": project_id,
            "from_cache": True,
            "fetched_at": fetched_at,
            "stale": True,
            "syncing": True,
        }

    if background and not plans:
        _start_plans_background_sync(project_id)
        return {
            "plans": [],
            "project_id": project_id,
            "from_cache": False,
            "syncing": True,
        }

    return sync_project_plans(project_id, force=False)


# Deprecated JSON helpers — migration only (stackct_store.migrate_from_json_caches)
def load_cache():
    return None


def save_cache(projects: list):
    logger.debug("save_cache deprecated — use stackct_sync.sync_projects")


def save_plans_cache(project_id: int, plans: list) -> None:
    logger.debug("save_plans_cache deprecated — use stackct_sync.sync_project_plans")
