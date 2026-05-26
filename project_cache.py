"""
Cache the StackCT project list locally so the UI dropdown is instant.
Projects are fetched via a single browser login and saved to disk.
Re-fetch only happens when explicitly requested (Refresh button) or cache is stale.
"""
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from config import OUTPUT_DIR

logger = logging.getLogger(__name__)

CACHE_FILE = Path(OUTPUT_DIR) / "projects_cache.json"
CACHE_TTL_HOURS = 24   # consider cache stale after 24 hours


def load_cache() -> dict:
    """Load cached project list from disk. Returns {projects, fetched_at} or None."""
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text())
            return data
    except Exception:
        pass
    return None


def save_cache(projects: list):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({
        "projects": projects,
        "fetched_at": datetime.now().isoformat(),
    }, indent=2))
    logger.info(f"Cached {len(projects)} projects to {CACHE_FILE}")


def is_stale(cache: dict) -> bool:
    try:
        fetched = datetime.fromisoformat(cache["fetched_at"])
        return datetime.now() - fetched > timedelta(hours=CACHE_TTL_HOURS)
    except Exception:
        return True


async def _fetch_from_stackct() -> list:
    from browser import StackCTBrowser
    b = StackCTBrowser()
    await b.start()
    try:
        if not await b.login():
            raise RuntimeError("Login failed")
        return await b.get_all_projects()
    finally:
        await b.close()


def get_projects(force_refresh: bool = False) -> dict:
    """
    Return projects list. Uses cache if fresh, otherwise fetches live.
    Returns: {"projects": [...], "fetched_at": "...", "from_cache": bool}
    """
    cache = load_cache()

    if not force_refresh and cache and not is_stale(cache):
        logger.info(f"Returning {len(cache['projects'])} projects from cache")
        return {**cache, "from_cache": True}

    # Fetch live
    logger.info("Fetching project list from StackCT...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        projects = loop.run_until_complete(_fetch_from_stackct())
        loop.close()

        save_cache(projects)
        return {
            "projects": projects,
            "fetched_at": datetime.now().isoformat(),
            "from_cache": False,
        }
    except Exception as e:
        logger.error(f"Live fetch failed: {e}")
        # Fall back to stale cache if available
        if cache:
            logger.warning("Using stale cache as fallback")
            return {**cache, "from_cache": True, "stale": True}
        return {
            "projects": [],
            "error": "Could not fetch projects from StackCT. Try again or check credentials.",
            "from_cache": False
        }


def prefetch_in_background():
    """Call this on app startup — fetches in a background thread if cache is missing/stale."""
    import threading
    cache = load_cache()
    if cache and not is_stale(cache):
        logger.info("Project cache is fresh, skipping prefetch")
        return
    logger.info("Starting background project prefetch...")
    t = threading.Thread(target=get_projects, kwargs={"force_refresh": True}, daemon=True)
    t.start()
