"""
StackCT catalog facade — DB-first reads with stackct_sync for live refresh.

Legacy JSON caches (projects_cache.json, plans_cache/) are migrated once into
SQLite via stackct_store.init_db(). Normal API paths do not read JSON files.
"""
import logging
import threading
from datetime import datetime

import stackct_store as store
from stackct_sync import (
    get_browser_lock,
    sync_project_plan_sets,
    sync_project_plans,
    sync_projects,
)

logger = logging.getLogger(__name__)

# Re-export lock for documentation / tests
_browser_lock = get_browser_lock()

_plan_sets_bg_lock = threading.Lock()
_plan_sets_syncing: set[int] = set()
_plans_bg_lock = threading.Lock()
_plans_syncing: set[tuple[int, int]] = set()
_projects_bg_started = False


def _ensure_db():
    store.init_db()


def _mostly_placeholder_names(projects: list[dict]) -> bool:
    """True when > 50% of project names are still Project_{id} placeholders."""
    if not projects:
        return False
    placeholders = sum(
        1 for p in projects
        if (p.get("name") or "").startswith("Project_")
    )
    return placeholders / len(projects) > 0.5


def get_projects(force_refresh: bool = False) -> dict:
    """
    Return projects list (DB-first).
    Shape: {projects, fetched_at, from_cache, stale?, syncing?, error?}

    Auto-triggers a background refresh when > 50% of stored names are
    Project_{id} placeholders (indicates the name-collection pass failed).
    """
    _ensure_db()
    global _projects_bg_started

    if force_refresh:
        return sync_projects(force=True)

    projects = store.list_projects()
    names_need_fix = _mostly_placeholder_names(projects)

    if projects and store.is_projects_fresh() and not names_need_fix:
        return {
            "projects": [{"id": p["id"], "name": p["name"]} for p in projects],
            "fetched_at": store.get_metadata("projects_synced_at"),
            "from_cache": True,
        }

    if projects and (not store.is_projects_fresh() or names_need_fix):
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
            "names_refreshing": names_need_fix,
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
    """Plan-set and sheet counts from SQLite."""
    _ensure_db()
    counts = store.get_sheet_counts()
    synced_at = store.get_metadata("projects_synced_at")
    return {
        "counts": counts,
        "plan_set_counts": {
            int(pid): meta.get("plan_set_count")
            for pid, meta in counts.items()
            if meta.get("plan_set_count") is not None
        },
        "synced_at": synced_at,
    }


def _start_plan_sets_background_sync(project_id: int):
    with _plan_sets_bg_lock:
        if project_id in _plan_sets_syncing:
            return
        _plan_sets_syncing.add(project_id)

    def _run():
        try:
            sync_project_plan_sets(project_id, force=True, count_sheets=False)
        finally:
            with _plan_sets_bg_lock:
                _plan_sets_syncing.discard(project_id)

    threading.Thread(target=_run, daemon=True).start()


def get_project_plan_sets(
    project_id: int,
    force_refresh: bool = False,
    wait: bool = False,
) -> dict:
    """Return plan sets for a project (DB-first, stale-while-revalidate).

    wait: when True and cache is empty, run a fast names-only StackCT sync
    inline (folder list only — no per-sheet scrape). Used by Preview Plans.
    """
    _ensure_db()

    if force_refresh:
        return sync_project_plan_sets(project_id, force=True, count_sheets=True)

    plan_sets = store.get_plan_sets(project_id)
    fetched_at = store.get_plan_sets_synced_at(project_id)

    if plan_sets and store.is_plan_sets_fresh(project_id):
        return {
            "plan_sets": plan_sets,
            "project_id": project_id,
            "from_cache": True,
            "fetched_at": fetched_at,
        }

    if plan_sets and not store.is_plan_sets_fresh(project_id):
        _start_plan_sets_background_sync(project_id)
        return {
            "plan_sets": plan_sets,
            "project_id": project_id,
            "from_cache": True,
            "fetched_at": fetched_at,
            "stale": True,
            "syncing": True,
        }

    # First visit: Preview waits for fast folder discovery (no sheet list)
    if wait:
        return sync_project_plan_sets(project_id, force=False, count_sheets=False)

    _start_plan_sets_background_sync(project_id)
    return {
        "plan_sets": [],
        "project_id": project_id,
        "from_cache": False,
        "syncing": True,
    }


def _start_plans_background_sync(project_id: int, folder_id: int):
    key = (project_id, folder_id)
    with _plans_bg_lock:
        if key in _plans_syncing:
            return
        _plans_syncing.add(key)

    def _run():
        try:
            sync_project_plans(project_id, folder_id, force=True)
        finally:
            with _plans_bg_lock:
                _plans_syncing.discard(key)

    threading.Thread(target=_run, daemon=True).start()


def get_project_plans(
    project_id: int,
    folder_id: int,
    force_refresh: bool = False,
    background: bool = False,
) -> dict:
    """
    Return drawing pages for one plan set (DB-first, stale-while-revalidate).
    """
    _ensure_db()

    if force_refresh:
        return sync_project_plans(project_id, folder_id, force=True)

    if background:
        _start_plans_background_sync(project_id, folder_id)
        plans = store.get_plans(project_id, folder_id)
        return {
            "plans": plans or [],
            "project_id": project_id,
            "folder_id": folder_id,
            "from_cache": True,
            "syncing": True,
        }

    plans = store.get_plans(project_id, folder_id)
    fetched_at = store.get_plans_synced_at(project_id, folder_id)

    if plans and store.is_plans_fresh(project_id, folder_id):
        return {
            "plans": plans,
            "project_id": project_id,
            "folder_id": folder_id,
            "from_cache": True,
            "fetched_at": fetched_at,
        }

    if plans and not store.is_plans_fresh(project_id, folder_id):
        _start_plans_background_sync(project_id, folder_id)
        return {
            "plans": plans,
            "project_id": project_id,
            "folder_id": folder_id,
            "from_cache": True,
            "fetched_at": fetched_at,
            "stale": True,
            "syncing": True,
        }

    _start_plans_background_sync(project_id, folder_id)
    return {
        "plans": [],
        "project_id": project_id,
        "folder_id": folder_id,
        "from_cache": False,
        "syncing": True,
    }


# Deprecated JSON helpers — migration only (stackct_store.migrate_from_json_caches)
def load_cache():
    return None


def save_cache(projects: list):
    logger.debug("save_cache deprecated — use stackct_sync.sync_projects")


def save_plans_cache(project_id: int, plans: list) -> None:
    logger.debug("save_plans_cache deprecated — use stackct_sync.sync_project_plans")
