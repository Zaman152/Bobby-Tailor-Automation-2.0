"""
Centralized StackCT browser sync — one login at a time, writes to stackct_store.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Optional

import stackct_store as store

logger = logging.getLogger(__name__)

_browser_lock = threading.Lock()


def get_browser_lock() -> threading.Lock:
    return _browser_lock


async def _fetch_projects_from_browser() -> list[dict]:
    from browser import StackCTBrowser

    b = StackCTBrowser()
    await b.start()
    try:
        await b.login()
        return await b.get_all_projects()
    finally:
        await b.close()


async def _fetch_plan_sets_from_browser(
    project_id: int, *, count_sheets: bool = False
) -> list[dict]:
    from browser import StackCTBrowser

    b = StackCTBrowser()
    await b.start()
    try:
        await b.login()
        return await b.get_plan_sets(project_id, count_sheets=count_sheets)
    finally:
        await b.close()


async def _fetch_plans_in_folder_from_browser(
    project_id: int, folder_id: int
) -> list[dict]:
    from browser import StackCTBrowser

    b = StackCTBrowser()
    await b.start()
    try:
        await b.login()
        return await b.get_page_ids_in_folder(project_id, folder_id)
    finally:
        await b.close()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def sync_projects(force: bool = False) -> dict:
    """
    Sync project catalog from StackCT into SQLite.
    Returns: {projects, fetched_at, from_cache, stale?, error?}
    """
    store.init_db()

    if not force and store.is_projects_fresh():
        projects = store.list_projects()
        if projects:
            logger.info(f"Returning {len(projects)} projects from DB")
            return {
                "projects": [{"id": p["id"], "name": p["name"]} for p in projects],
                "fetched_at": store.get_metadata("projects_synced_at"),
                "from_cache": True,
            }

    run_id = store.record_sync_run("projects")
    try:
        with _browser_lock:
            if not force and store.is_projects_fresh():
                projects = store.list_projects()
                store.finish_sync_run(run_id, "success", len(projects))
                return {
                    "projects": [{"id": p["id"], "name": p["name"]} for p in projects],
                    "fetched_at": store.get_metadata("projects_synced_at"),
                    "from_cache": True,
                }
            logger.info("Fetching project list from StackCT...")
            raw = _run_async(_fetch_projects_from_browser())

        synced_at = datetime.now().isoformat()
        store.upsert_projects(raw, synced_at)
        store.finish_sync_run(run_id, "success", len(raw))
        return {
            "projects": raw,
            "fetched_at": synced_at,
            "from_cache": False,
        }
    except Exception as e:
        logger.error(f"Project sync failed: {e}")
        store.finish_sync_run(run_id, "error", error_message=str(e))
        projects = store.list_projects()
        if projects:
            return {
                "projects": [{"id": p["id"], "name": p["name"]} for p in projects],
                "fetched_at": store.get_metadata("projects_synced_at"),
                "from_cache": True,
                "stale": True,
                "error": "Could not refresh projects from StackCT. Showing cached list.",
            }
        return {
            "projects": [],
            "error": "Could not fetch projects from StackCT. Try again or check credentials.",
            "from_cache": False,
        }


def sync_project_plan_sets(
    project_id: int, force: bool = False, *, count_sheets: bool = False
) -> dict:
    """
    Sync plan-set (folder) index for one project into SQLite.
    Returns: {plan_sets, project_id, fetched_at, from_cache, stale?, error?}

    count_sheets: when True, opens each folder in StackCT to count sheets (slow).
    Default False — folder names only; sheet lists load on "Load sheets".
    """
    store.init_db()

    if not force and store.is_plan_sets_fresh(project_id):
        plan_sets = store.get_plan_sets(project_id)
        if plan_sets:
            logger.info(
                f"Returning {len(plan_sets)} plan sets from DB for project {project_id}"
            )
            return {
                "plan_sets": plan_sets,
                "project_id": project_id,
                "from_cache": True,
                "fetched_at": store.get_plan_sets_synced_at(project_id),
            }

    run_id = store.record_sync_run("plan_sets", project_id=project_id)
    try:
        with _browser_lock:
            if not force and store.is_plan_sets_fresh(project_id):
                plan_sets = store.get_plan_sets(project_id)
                store.finish_sync_run(run_id, "success", len(plan_sets))
                return {
                    "plan_sets": plan_sets,
                    "project_id": project_id,
                    "from_cache": True,
                    "fetched_at": store.get_plan_sets_synced_at(project_id),
                }
            logger.info(
                f"Fetching plan sets from StackCT for project {project_id} "
                f"(count_sheets={count_sheets})..."
            )
            sets = _run_async(
                _fetch_plan_sets_from_browser(project_id, count_sheets=count_sheets)
            )

        synced_at = datetime.now().isoformat()
        store.upsert_plan_sets(project_id, sets, synced_at)
        store.finish_sync_run(run_id, "success", len(sets))
        return {
            "plan_sets": sets,
            "project_id": project_id,
            "from_cache": False,
            "fetched_at": synced_at,
        }
    except Exception as e:
        logger.error(f"Plan-set sync failed for project {project_id}: {e}")
        err = str(e)
        store.finish_sync_run(run_id, "error", error_message=err)
        plan_sets = store.get_plan_sets(project_id)
        if plan_sets:
            return {
                "plan_sets": plan_sets,
                "project_id": project_id,
                "from_cache": True,
                "stale": True,
                "fetched_at": store.get_plan_sets_synced_at(project_id),
                "warning": "Live fetch failed; showing cached plan sets.",
            }
        return {"plan_sets": [], "error": err, "project_id": project_id}


def sync_project_plans(
    project_id: int,
    folder_id: int,
    force: bool = False,
) -> dict:
    """
    Sync drawing pages for one plan set (folder) into SQLite.
    Returns: {plans, project_id, folder_id, fetched_at, from_cache, stale?, warning?, error?}
    """
    store.init_db()

    if not force and store.is_plans_fresh(project_id, folder_id):
        plans = store.get_plans(project_id, folder_id)
        if plans is not None:
            logger.info(
                f"Returning {len(plans)} plans from DB for project {project_id} "
                f"folder {folder_id}"
            )
            return {
                "plans": plans,
                "project_id": project_id,
                "folder_id": folder_id,
                "from_cache": True,
                "fetched_at": store.get_plans_synced_at(project_id, folder_id),
            }

    run_id = store.record_sync_run(
        "plans", project_id=project_id, folder_id=folder_id
    )
    try:
        with _browser_lock:
            if not force and store.is_plans_fresh(project_id, folder_id):
                plans = store.get_plans(project_id, folder_id)
                store.finish_sync_run(run_id, "success", len(plans))
                return {
                    "plans": plans,
                    "project_id": project_id,
                    "folder_id": folder_id,
                    "from_cache": True,
                    "fetched_at": store.get_plans_synced_at(project_id, folder_id),
                }
            logger.info(
                f"Fetching plans from StackCT for project {project_id} "
                f"folder {folder_id}..."
            )
            pages = _run_async(
                _fetch_plans_in_folder_from_browser(project_id, folder_id)
            )

        synced_at = datetime.now().isoformat()
        store.upsert_plans(project_id, folder_id, pages, synced_at)
        store.finish_sync_run(run_id, "success", len(pages))
        return {
            "plans": pages,
            "project_id": project_id,
            "folder_id": folder_id,
            "from_cache": False,
            "fetched_at": synced_at,
        }
    except Exception as e:
        logger.error(
            f"Plan sync failed for project {project_id} folder {folder_id}: {e}"
        )
        err = str(e)
        store.finish_sync_run(run_id, "error", error_message=err)
        plans = store.get_plans(project_id, folder_id)
        if plans:
            return {
                "plans": plans,
                "project_id": project_id,
                "folder_id": folder_id,
                "from_cache": True,
                "stale": True,
                "fetched_at": store.get_plans_synced_at(project_id, folder_id),
                "warning": "Live fetch failed; showing cached plans.",
            }
        return {
            "plans": [],
            "error": err,
            "project_id": project_id,
            "folder_id": folder_id,
        }


def sync_projects_if_stale() -> None:
    """Background hook: refresh project list when TTL expired."""
    store.init_db()
    if store.is_projects_fresh() and store.project_count() > 0:
        logger.info("StackCT project catalog is fresh — skipping scheduled sync")
        return
    sync_projects(force=False)
