import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import List, Optional
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from config import (
    STACKCT_EMAIL, STACKCT_PASSWORD,
    STACKCT_LOGIN_URL, STACKCT_PROJECTS_URL,
    HEADLESS, PAGE_LOAD_TIMEOUT,
    CANVAS_STABILITY_TIMEOUT, CANVAS_STABILITY_CHECKS,
)

logger = logging.getLogger(__name__)

# System folders to skip when discovering plan sets
SKIP_PLAN_SET_NAMES = frozenset({
    "plans", "bookmarks", "supporting documents", "supporting docs",
})


def normalize_plan_sets(raw: list[dict]) -> list[dict]:
    """
    Deduplicate and filter raw plan set folder list per discovery audit rules.
    
    Rules:
    1. Skip system folders (Plans, Bookmarks, Supporting Documents)
    2. Drop "Plans X" parent when child "X" exists with same sheet_count
    3. Drop aggregate names containing multiple issue labels (e.g. both "v1" and "v2")
    4. Prefer shorter names when same sheet_count
    """
    # Rule 1: Filter out system folders
    candidates = []
    for entry in raw:
        name_lower = entry["name"].lower()
        if name_lower in SKIP_PLAN_SET_NAMES:
            continue
        # Skip generic "Plans" or "Plans >" breadcrumb entries
        if name_lower == "plans" or name_lower.startswith("plans >"):
            continue
        candidates.append(entry)
    
    # Rule 3: Drop aggregate names with multiple version labels
    # Heuristic: if name contains multiple issue labels like "v1" and "v2"
    filtered = []
    for entry in candidates:
        name = entry["name"]
        # Check for common version patterns appearing together
        version_indicators = ["v1", "v2", "v3", "issue", "rev", "addendum"]
        found_indicators = [ind for ind in version_indicators if ind.lower() in name.lower()]
        # If we find multiple distinct version numbers in one name, likely an aggregate
        if "v1" in name.lower() and "v2" in name.lower():
            logger.debug(f"Dropping aggregate plan set: {name}")
            continue
        filtered.append(entry)
    
    # Rule 2: Drop "Plans X" when child "X" exists with same sheet_count
    # Build map by sheet_count for comparison
    by_count = {}
    for entry in filtered:
        count = entry.get("sheet_count", 0)
        if count not in by_count:
            by_count[count] = []
        by_count[count].append(entry)
    
    result = []
    for entry in filtered:
        name = entry["name"]
        count = entry.get("sheet_count", 0)
        
        # Check if this is a "Plans X" parent
        if name.lower().startswith("plans "):
            child_name = name[6:].strip()  # Remove "Plans " prefix
            # Look for matching child in same sheet_count group
            siblings = by_count.get(count, [])
            has_child = any(
                s["name"].strip() == child_name and s["folder_id"] != entry["folder_id"]
                for s in siblings
            )
            if has_child:
                logger.debug(f"Dropping parent plan set: {name} (child exists)")
                continue
        
        result.append(entry)
    
    # Rule 4: If multiple entries with same sheet_count, prefer shorter name
    # (already handled by audit script's preference for short labels)
    
    return result


class StackCTBrowser:
    def __init__(self):
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self.page: Page = None

    async def start(self):
        self._playwright = await async_playwright().start()
        # VPS-safe Chromium launch args:
        # --no-sandbox: Required in Docker/restricted environments
        # --disable-dev-shm-usage: Use /tmp instead of /dev/shm (prevents OOM on small VPS)
        # --disable-blink-features=AutomationControlled: Reduce detection fingerprint
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        # Large viewport + 2x device pixel ratio = high-DPI screenshots that
        # let Claude actually read small dimension annotations on drawings.
        self._context = await self._browser.new_context(
            viewport={"width": 2560, "height": 1600},
            device_scale_factor=2,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        # Intercept and log all network requests to discover APIs
        self._context.on("request", self._on_request)
        self.page = await self._context.new_page()
        self.page.set_default_timeout(PAGE_LOAD_TIMEOUT)
        logger.info("Browser started")

    def _on_request(self, request):
        url = request.url
        # Log API calls (not static assets)
        if any(x in url for x in ["agent.stackct", "api/", "/takeoff/", "/pages/", "signalr"]):
            logger.debug(f"API call: {request.method} {url[:120]}")

    def _login_error_message(self, exc: Exception) -> str:
        msg = str(exc)
        if "ERR_NAME_NOT_RESOLVED" in msg or "ENOTFOUND" in msg:
            return (
                "Cannot reach StackCT (DNS/network). "
                "Check your internet connection or VPN, then try again."
            )
        if "ERR_INTERNET_DISCONNECTED" in msg or "ERR_NETWORK_CHANGED" in msg:
            return "Network disconnected while connecting to StackCT. Try again."
        if "Timeout" in msg or "timeout" in msg:
            return "StackCT login timed out. Try again in a few seconds."
        return f"StackCT login failed: {msg}"

    async def login(self) -> bool:
        logger.info("Logging into StackCT...")
        try:
            # Use "load" — StackCT uses SignalR WebSockets that never reach networkidle
            await self.page.goto("https://go.stackct.com/", wait_until="load", timeout=45000)

            current_url = self.page.url
            logger.info(f"After goto, URL: {current_url[:80]}")

            # If already on the app (e.g. session active), we're done
            if "go.stackct.com/app" in current_url:
                logger.info("Already authenticated — skipping login form")
                return True

            # Auth0 may redirect immediately or after a short pause — wait up to 25s
            try:
                await self.page.wait_for_url("**/id.stackct.com/**", timeout=25000)
            except Exception:
                # Maybe it went straight to the app via a different redirect
                if "go.stackct.com/app" in self.page.url:
                    logger.info("Redirected directly to app — login successful")
                    return True
                raise

            # Step 1: Enter email
            await self.page.wait_for_selector(
                'input[name="username"], input[type="email"], input[type="text"]',
                timeout=10000
            )
            email_input = await self.page.query_selector(
                'input[name="username"], input[type="email"], input[type="text"]'
            )
            await email_input.fill(STACKCT_EMAIL)

            # Click the Continue / Next button
            await self.page.click('button[type="submit"], button[name="action"]')

            # Step 2: Enter password
            await self.page.wait_for_selector('input[type="password"]', timeout=10000)
            await self.page.fill('input[type="password"]', STACKCT_PASSWORD)
            await self.page.click('button[type="submit"], button[name="action"]')

            # Auth0 may pass through several /authorize redirects before the SPA loads
            if await self._wait_for_stackct_app(timeout_ms=60000):
                logger.info("Login successful")
                return True
            raise RuntimeError(
                "StackCT login timed out waiting for the app to load after Auth0."
            )

        except Exception as e:
            err = self._login_error_message(e)
            logger.error(err)
            raise RuntimeError(err) from e

    async def _wait_for_stackct_app(self, timeout_ms: int = 60000) -> bool:
        """Poll until the StackCT app shell is loaded (post-Auth0 redirect chain)."""
        deadline = time.time() + timeout_ms / 1000
        last_url = ""
        while time.time() < deadline:
            last_url = self.page.url
            if "go.stackct.com/app" in last_url:
                await asyncio.sleep(1.5)
                return True
            await asyncio.sleep(0.5)
        logger.error(f"Timed out waiting for StackCT app; last URL: {last_url[:160]}")
        return False

    async def navigate_to_project(self, project_id: int) -> bool:
        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}/Home"
        logger.info(f"Navigating to project {project_id}")
        try:
            await self.page.goto(url, wait_until="load")
            await self.page.wait_for_selector("text=PLANS & TAKEOFFS", timeout=15000)
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to project {project_id}: {e}")
            return False

    async def navigate_to_plans(self, project_id: int) -> bool:
        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}"
        logger.info("Navigating to Plans & Takeoffs")
        try:
            await self.page.goto(url, wait_until="load")
            await self.page.wait_for_selector("text=Plans and Documents", timeout=15000)
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to plans: {e}")
            return False

    async def get_all_projects(self) -> List[dict]:
        """
        Return list of {id, name} for ALL projects (handles virtual scrolling).

        Collects both IDs and names in a single pass during scrolling so
        projects below the fold are never saved as Project_{id}.
        """
        logger.info("Getting project list with virtual scroll handling")
        await self.page.goto(STACKCT_PROJECTS_URL, wait_until="load")
        try:
            await self.page.wait_for_selector("text=PROJECT NAME", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)

        project_map: dict[int, str] = {}   # id → name (collected as we scroll)
        prev_count = 0
        stalled_iterations = 0
        max_stalls = 4

        _SCROLL_JS = """
            (() => {
                const container = document.querySelector(
                    '[class*="cdk-virtual-scroll"], [class*="virtual-scroll-viewport"],' +
                    ' [class*="virtual-scroll"]'
                );
                if (container) {
                    container.scrollTop += container.clientHeight;
                    return 'container';
                }
                window.scrollBy(0, window.innerHeight);
                return 'window';
            })()
        """

        for scroll_iteration in range(60):   # allow many more scrolls for large lists
            project_links = await self.page.query_selector_all('a[href*="Takeoff"]')
            for link in project_links:
                try:
                    href = await link.get_attribute("href") or ""
                    if "Takeoff" not in href:
                        continue
                    project_id = int(href.split("Takeoff/")[1].split("/")[0])
                    if project_id in project_map:
                        continue
                    # Collect name in the same pass
                    text = (await link.inner_text()).strip()
                    if not text:
                        # Try parent row text if the link itself has no text
                        parent = await link.evaluate_handle(
                            "el => el.closest('tr, li, [role=\"row\"], [class*=\"project-row\"]') || el.parentElement"
                        )
                        try:
                            text = (await parent.inner_text()).strip().split("\n")[0].strip()
                        except Exception:
                            pass
                    project_map[project_id] = text or ""
                except (IndexError, ValueError, Exception):
                    continue

            current_count = len(project_map)
            logger.debug(
                f"Scroll {scroll_iteration + 1}: {current_count} projects "
                f"({sum(1 for v in project_map.values() if v)} named)"
            )

            if current_count == prev_count:
                stalled_iterations += 1
                if stalled_iterations >= max_stalls:
                    logger.info(
                        f"No new projects after {max_stalls} stalled scrolls — done"
                    )
                    break
            else:
                stalled_iterations = 0

            prev_count = current_count
            await self.page.evaluate(_SCROLL_JS)
            await asyncio.sleep(1.2)

        # Second pass: fill in any projects still missing names by scrolling back up
        unnamed = {pid for pid, name in project_map.items() if not name}
        if unnamed:
            logger.info(f"{len(unnamed)} projects still missing names — doing name-fill pass")
            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            for _ in range(20):
                project_links = await self.page.query_selector_all('a[href*="Takeoff"]')
                for link in project_links:
                    try:
                        href = await link.get_attribute("href") or ""
                        if "Takeoff" not in href:
                            continue
                        pid = int(href.split("Takeoff/")[1].split("/")[0])
                        if pid not in unnamed:
                            continue
                        text = (await link.inner_text()).strip()
                        if text:
                            project_map[pid] = text
                            unnamed.discard(pid)
                    except Exception:
                        continue
                if not unnamed:
                    break
                await self.page.evaluate(_SCROLL_JS)
                await asyncio.sleep(1)
            if unnamed:
                logger.warning(f"{len(unnamed)} projects still unnamed after fill pass")

        projects = [
            {"id": pid, "name": name if name else f"Project_{pid}"}
            for pid, name in project_map.items()
        ]
        projects.sort(key=lambda p: p["name"].lower())
        named_count = sum(1 for p in projects if not p["name"].startswith("Project_"))
        logger.info(
            f"Found {len(projects)} projects ({named_count} named, "
            f"{len(projects) - named_count} unnamed)"
        )
        return projects

    async def get_all_page_ids(self, project_id: int) -> List[dict]:
        """
        Deprecated: Use get_plan_sets() + get_page_ids_in_folder() instead.
        
        Thin wrapper for backward compatibility:
        - If one plan set exists, return its pages
        - If multiple sets exist, log warning and return empty list
        - If folder_id==0 (direct-grid), scrape landing page
        
        Returns list of {page_id, sheet_name}.
        """
        logger.warning(
            "get_all_page_ids is deprecated — use get_plan_sets + "
            "get_page_ids_in_folder for folder-scoped access"
        )
        
        plan_sets = await self.get_plan_sets(project_id)
        
        if len(plan_sets) == 0:
            logger.error(f"No plan sets found for project {project_id}")
            return []
        
        if len(plan_sets) == 1:
            # Single set — return its pages
            folder_id = plan_sets[0]["folder_id"]
            return await self.get_page_ids_in_folder(project_id, folder_id)
        
        # Multiple sets — caller must use folder API
        logger.warning(
            f"Project {project_id} has {len(plan_sets)} plan sets. "
            f"Callers must use get_plan_sets + get_page_ids_in_folder with "
            f"explicit folder_id. Returning empty list."
        )
        return []

    async def get_plan_sets(
        self, project_id: int, *, count_sheets: bool = False
    ) -> list[dict]:
        """
        Discover all plan sets (folders) for a project, with deduplication.
        Returns list of {folder_id, name, sheet_count}.

        When count_sheets is False (default), only reads folder cards — fast.
        Per-folder sheet counts require opening each set (slow); use
        count_sheets=True only for explicit "Sync from StackCT" refresh.

        For projects with no folder cards (direct grid), returns a single
        synthetic set with folder_id=0.
        """
        logger.info(f"Discovering plan sets for project {project_id}")
        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}"
        await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)

        # Poll for folder cards (faster than a fixed long sleep)
        raw_sets = []
        for attempt in range(24):
            raw_sets = await self.page.evaluate('''() => {
                const sets = [];
                const seen = new Set();
                document.querySelectorAll('[data-folder-id]').forEach(el => {
                    const id = parseInt(el.getAttribute('data-folder-id'), 10);
                    if (!id || seen.has(id)) return;
                    const name = (el.textContent || '').trim().replace(/\\s+/g, ' ');
                    if (!name || name.length < 4) return;
                    const short = name.split('>').pop().trim();
                    if (short.length > 150) return;
                    seen.add(id);
                    sets.push({ folder_id: id, name: short });
                });
                return sets;
            }''')
            if raw_sets:
                break
            await asyncio.sleep(0.5)
        if not raw_sets:
            logger.info(
                f"No folder cards after {attempt + 1} polls "
                f"({(attempt + 1) * 0.5:.1f}s)"
            )
        
        # Apply dedupe rules
        candidates = normalize_plan_sets(raw_sets)

        if not count_sheets:
            plan_sets = [
                {
                    "folder_id": ps["folder_id"],
                    "name": ps["name"],
                    "sheet_count": None,
                }
                for ps in candidates
            ]
            logger.info(
                f"Discovered {len(plan_sets)} plan sets (names only, no sheet counts)"
            )
            if plan_sets:
                return plan_sets
        else:
            # Explicit refresh: open each folder and count [data-page-id] nodes
            plan_sets = []
            for ps in candidates:
                fid = ps["folder_id"]
                try:
                    await self.page.click(f'[data-folder-id="{fid}"]', timeout=8000)
                    await asyncio.sleep(1.5)
                    sheet_count = await self.page.evaluate('''() => {
                        const ids = new Set();
                        document.querySelectorAll('[data-page-id]').forEach(el => {
                            const pid = el.getAttribute('data-page-id');
                            if (pid) ids.add(pid);
                        });
                        return ids.size;
                    }''')
                    plan_sets.append({
                        "folder_id": fid,
                        "name": ps["name"],
                        "sheet_count": sheet_count,
                    })
                    logger.info(f"  Plan set: {ps['name']} ({sheet_count} sheets)")
                except Exception as e:
                    logger.warning(f"Failed to query plan set {fid}: {e}")

            if plan_sets:
                logger.info(f"Discovered {len(plan_sets)} plan sets with sheet counts")
                return plan_sets

        # No folder cards: direct-grid projects (e.g. ATL 081)
        if not count_sheets:
            logger.info(
                "No folder cards — direct-grid plan set (sheet list loads on demand)"
            )
            return [{
                "folder_id": 0,
                "name": "All drawing sheets",
                "sheet_count": None,
            }]

        logger.info("No plan set folders found — checking direct grid for sheet counts...")
        await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        for attempt in range(6):
            await asyncio.sleep(5)
            landing_count = await self.page.evaluate('''() => {
                const ids = new Set();
                document.querySelectorAll('[data-page-id]').forEach(el => {
                    const pid = el.getAttribute('data-page-id');
                    if (pid) ids.add(pid);
                });
                return ids.size;
            }''')
            if landing_count > 0:
                logger.info(
                    f"Direct-grid fallback: {landing_count} sheets (no folder cards)"
                )
                return [{
                    "folder_id": 0,
                    "name": "All drawing sheets",
                    "sheet_count": landing_count,
                }]
        logger.warning("No plan sets and no landing grid pages found")
        return []

    async def get_page_ids_in_folder(
        self, project_id: int, folder_id: int
    ) -> list[dict]:
        """
        Get all drawing pages for a specific folder (plan set).
        
        If folder_id == 0 (direct-grid fallback), scrape landing page.
        Otherwise, navigate to project and click the folder before scraping.
        
        Returns list of {page_id, sheet_name}.
        """
        logger.info(
            f"Getting pages for project {project_id}, folder {folder_id}"
        )
        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}"
        await self.page.goto(url, wait_until="load", timeout=60000)
        
        if folder_id == 0:
            # Direct-grid fallback — scrape landing page
            logger.info("Using direct-grid fallback (folder_id=0)")
            await asyncio.sleep(3)
        else:
            # Click folder card to load its sheets
            try:
                await self.page.click(
                    f'[data-folder-id="{folder_id}"]', timeout=10000
                )
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed to click folder {folder_id}: {e}")
                return []
        
        # Wait for thumbnails
        try:
            await self.page.wait_for_selector('[data-page-id]', timeout=30000)
            await asyncio.sleep(2)
        except Exception:
            logger.warning("No [data-page-id] elements found")
            return []
        
        # Extract page IDs (reuse logic from get_all_page_ids)
        pages_raw = await self.page.evaluate('''() => {
            const result = [];
            const seen = new Set();
            document.querySelectorAll('[data-page-id]').forEach(el => {
                const pid = el.getAttribute('data-page-id');
                if (!pid || seen.has(pid)) return;
                seen.add(pid);
                const nameEl = el.querySelector('[data-id="thumbnail-page-name"]');
                const name = nameEl ? nameEl.textContent.trim() : "";
                result.push({page_id: parseInt(pid), sheet_name: name});
            });
            return result;
        }''')
        
        pages = [p for p in pages_raw if p["page_id"]]
        logger.info(f"Found {len(pages)} pages in folder {folder_id}")
        return pages

    async def navigate_to_page(self, project_id: int, page_id: int) -> bool:
        """Navigate to a specific drawing page and VERIFY the URL actually changed
        to that page (StackCT sometimes caches the previous page if you navigate too fast)."""
        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}/Page/{page_id}/@0,0,0z"
        try:
            # First navigate away to clear any cached page state — prevents StackCT
            # from keeping the previous drawing on screen when we hit the same hash route.
            current = self.page.url
            if f"/Page/" in current and f"/Page/{page_id}" not in current:
                # Force-clear by going to the project root first
                await self.page.goto(
                    f"https://go.stackct.com/app/#/Takeoff/{project_id}",
                    wait_until="load"
                )
                await asyncio.sleep(1)

            await self.page.goto(url, wait_until="load")

            # Verify the URL actually contains our target page ID
            for _ in range(3):
                if f"/Page/{page_id}" in self.page.url:
                    break
                await asyncio.sleep(1)
            else:
                logger.warning(f"URL didn't update to page {page_id} — current: {self.page.url[:120]}")
                # One more forceful attempt
                await self.page.goto(url, wait_until="load")

            # Wait for drawing canvas to appear
            try:
                await self.page.wait_for_selector(
                    "canvas, [class*='viewer'], [class*='drawing-area']",
                    timeout=15000
                )
            except Exception:
                pass

            # Wait for the "Loading" overlay to disappear
            try:
                await self.page.wait_for_selector(
                    "text=Loading",
                    state="hidden",
                    timeout=20000
                )
            except Exception:
                pass

            # Confirm DOM reflects this page (check the active tab text matches)
            try:
                await self.page.wait_for_function(
                    f'window.location.href.includes("/Page/{page_id}")',
                    timeout=5000
                )
            except Exception:
                pass

            await asyncio.sleep(3)  # buffer for tile rendering
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to page {page_id}: {e}")
            return False

    async def _dismiss_popups(self):
        """Hide StackCT's HubSpot marketing overlays via CSS so they don't appear in screenshots."""
        try:
            await self.page.add_style_tag(content="""
                /* StackCT uses HubSpot CTAs for promo popups (e.g. STACK LIVE webinar) */
                [id^="hs-overlay-cta"],
                [id^="hs-cta-"],
                [class*="hs-cta-embed"],
                iframe[src*="hs-sites.com"],
                iframe[src*="hubspot"],
                iframe[src*="hsforms"],
                /* Generic fallbacks */
                [class*="hs-cta-trigger"],
                [class*="webinar-promo"],
                div[class*="modal-backdrop"] {
                    display: none !important;
                    visibility: hidden !important;
                    opacity: 0 !important;
                    pointer-events: none !important;
                    width: 0 !important;
                    height: 0 !important;
                }
            """)
        except Exception:
            pass

        # Also try clicking common close buttons as backup
        for sel in [
            '[aria-label*="close" i]', '[aria-label*="dismiss" i]',
            'button[class*="close" i]', 'button:has-text("Close")',
            'button:has-text("No Thanks")', 'button:has-text("Maybe Later")',
        ]:
            try:
                for el in await self.page.query_selector_all(sel):
                    try:
                        if await el.is_visible():
                            await el.click(timeout=500)
                    except Exception:
                        continue
            except Exception:
                continue

        try:
            await self.page.keyboard.press("Escape")
        except Exception:
            pass

    async def _wait_for_tiles_loaded(self, timeout_s: int = 45) -> int:
        """
        Wait until StackCT tile/image fetching has settled.

        Watches for image responses from the network.  Returns when no new
        image response has arrived for 2 s, or when the timeout is reached.
        Returns the total number of image responses observed.
        """
        state: dict = {"last_img": time.time(), "count": 0}

        def _on_resp(resp: object) -> None:
            ct = resp.headers.get("content-type", "")
            if "image" in ct and "svg" not in ct:
                state["last_img"] = time.time()
                state["count"] += 1

        self.page.on("response", _on_resp)
        try:
            deadline = time.time() + timeout_s
            await asyncio.sleep(1.5)          # let requests start
            while time.time() < deadline:
                await asyncio.sleep(0.5)
                idle_for = time.time() - state["last_img"]
                if state["count"] > 0 and idle_for > 2.0:
                    logger.info(
                        f"Tiles settled: {state['count']} image responses, "
                        f"idle {idle_for:.1f}s"
                    )
                    break
                if state["count"] == 0 and idle_for > 8.0:
                    logger.info("No image tiles detected — proceeding")
                    break
        finally:
            try:
                self.page.remove_listener("response", _on_resp)
            except Exception:
                pass
        return state["count"]

    @staticmethod
    def _is_blank_png(buf: bytes) -> bool:
        """
        Heuristic: a grey/white 'blank' canvas produces a very small PNG because
        it's a near-solid colour.  Real drawings have much higher entropy.

        At 2 × DPR the canvas is at least 2000 × 1400 px.  A blank grey PNG at
        that resolution compresses to < 80 KB; a drawing with line work is > 400 KB.
        """
        return len(buf) < 120_000   # 120 KB threshold

    async def _wait_for_canvas_stable(
        self,
        selector: str,
        timeout_s: int = None,
        stable_checks: int = None,
    ) -> bool:
        """
        Wait until canvas pixels stop changing AND the canvas has actual content.

        Two conditions must both hold:
          1. The MD5 hash of the canvas screenshot is unchanged for `stable_checks`
             consecutive polls.
          2. The canvas screenshot is not blank/grey (size threshold).

        If condition 1 fires on a blank canvas we keep waiting, resetting the
        stable counter, until the canvas grows content or the timeout expires.
        """
        if timeout_s is None:
            timeout_s = CANVAS_STABILITY_TIMEOUT
        if stable_checks is None:
            stable_checks = CANVAS_STABILITY_CHECKS

        prev_hash = None
        stable_count = 0
        blank_streak = 0
        start = time.time()
        deadline = start + timeout_s

        while time.time() < deadline:
            try:
                el = await self.page.query_selector(selector)
                if not el:
                    await asyncio.sleep(0.5)
                    continue

                buf = await el.screenshot()
                if len(buf) < 5000:
                    logger.warning("Canvas screenshot < 5KB, waiting...")
                    await asyncio.sleep(0.8)
                    continue

                h = hashlib.md5(buf).hexdigest()
                is_blank = self._is_blank_png(buf)

                if is_blank:
                    blank_streak += 1
                    if blank_streak % 5 == 0:
                        logger.debug(
                            f"Canvas blank for {blank_streak} polls "
                            f"({len(buf):,} bytes) — waiting for tiles…"
                        )
                    # Reset stable counter — blank != ready
                    prev_hash = None
                    stable_count = 0
                    await asyncio.sleep(0.8)
                    continue

                blank_streak = 0
                if h == prev_hash:
                    stable_count += 1
                    if stable_count >= stable_checks:
                        elapsed = time.time() - start
                        logger.info(
                            f"Canvas stable+content after {elapsed:.1f}s "
                            f"({len(buf):,} bytes)"
                        )
                        return True
                else:
                    stable_count = 0

                prev_hash = h
            except Exception as e:
                logger.warning(f"Canvas polling error: {e}")

            await asyncio.sleep(0.8)

        elapsed = time.time() - start
        logger.warning(
            f"Canvas stability timeout after {elapsed:.1f}s — proceeding anyway"
        )
        return False

    # ── Azure Blob Storage patterns ──────────────────────────────────────────
    # StackCT stores every drawing page on Azure:
    #   Full-page JPEG:  .../pages/{page_id}/{uuid}.jpg          (~1-4 MB, clean)
    #   Full-page PDF:   .../pages/{page_id}/{uuid}.pdf          (~4 MB, lossless)
    #   Tile JPEG:       .../pages/{page_id}/{uuid}_files/{z}/{x}_{y}.jpg
    #   Thumbnail JPEG:  .../thumbnail/{project_id}_{page_id}.jpeg (~100-175 KB)
    _BLOB_HOST = "ctplanstore.blob.core.windows.net"

    async def download_drawing_image(
        self,
        project_id: int,
        page_id: int,
        filepath: str,
        pdf_filepath: Optional[str] = None,
    ) -> bool:
        """
        Download the source drawing image for a page by intercepting the
        Azure Blob Storage response that StackCT fetches when rendering.

        Returns True when a full-page JPEG (or fallback JPEG tile) has been
        saved to `filepath`.  Falls back to screenshot_full_drawing on failure.

        Why this is better than screenshotting:
         • Bypasses WebGL canvas (no blank images).
         • No browser chrome / toolbar / minimap overlay.
         • True source image quality, straight from StackCT's CDN.
        """
        # Holds the best candidate found so far: (size, bytes, url)
        full_page: list = []      # {uuid}.jpg  — full-page JPEG
        full_page_pdf: list = []  # {uuid}.pdf  — full-page PDF (text layer)
        best_tile: list = []      # largest tile as fallback

        async def _on_response(resp) -> None:
            url = resp.url
            if self._BLOB_HOST not in url:
                return
            ct = resp.headers.get("content-type", "")
            if "image" not in ct and "pdf" not in ct:
                return
            # Only care about this page's assets
            if f"/pages/{page_id}/" not in url:
                return

            try:
                body = await resp.body()
            except Exception:
                return

            if len(body) < 10_000:
                return

            # Full-page PDF (lossless vector source — used for text-layer takeoff).
            is_full_page_pdf = (
                "pdf" in ct
                and "_files/" not in url
                and url.split("?")[0].split("/")[-1].lower().endswith(".pdf")
            )
            # Full-page JPEG: ends with .jpg but NOT _files/
            is_full_page_jpeg = (
                ".jpg" in url.split("?")[0].split("/")[-1]
                and "_files/" not in url
                and "pdf" not in ct
            )
            is_tile = "_files/" in url and (".jpg" in url or ".jpeg" in url)

            if is_full_page_pdf:
                if not full_page_pdf or len(body) > full_page_pdf[0]:
                    full_page_pdf.clear()
                    full_page_pdf.extend([len(body), body, url])
            elif is_full_page_jpeg:
                if not full_page or len(body) > full_page[0]:
                    full_page.clear()
                    full_page.extend([len(body), body, url])
            elif is_tile:
                if not best_tile or len(body) > best_tile[0]:
                    best_tile.clear()
                    best_tile.extend([len(body), body, url])

        self.page.on("response", _on_response)
        try:
            if not await self.navigate_to_page(project_id, page_id):
                logger.warning(f"Navigation failed for page {page_id} — falling back to screenshot")
                return await self.screenshot_full_drawing(project_id, page_id, filepath)

            await self._dismiss_popups()

            # Wait up to 30 s for the full-page JPEG to arrive
            deadline = time.time() + 30
            while time.time() < deadline:
                await asyncio.sleep(0.5)
                if full_page:
                    break          # found what we need

            # Also wait a moment for tiles if no full-page JPEG arrived
            if not full_page:
                await asyncio.sleep(5)

            chosen = full_page or best_tile
            if chosen:
                size, body, url = chosen
                out = Path(filepath)
                out.parent.mkdir(parents=True, exist_ok=True)
                with open(out, "wb") as fh:
                    fh.write(body)
                logger.info(
                    f"Blob download saved: {filepath} ({size:,} bytes) "
                    f"{'[full-page]' if chosen is full_page else '[tile fallback]'} "
                    f"from {url[:80]}"
                )
                if pdf_filepath and full_page_pdf:
                    psize, pbody, purl = full_page_pdf
                    pdf_out = Path(pdf_filepath)
                    pdf_out.parent.mkdir(parents=True, exist_ok=True)
                    with open(pdf_out, "wb") as fh:
                        fh.write(pbody)
                    logger.info(
                        f"Blob PDF saved: {pdf_filepath} ({psize:,} bytes) "
                        f"from {purl[:80]}"
                    )
                return True

            logger.warning(
                f"No blob image intercepted for page {page_id} — falling back to screenshot"
            )
            return await self.screenshot_full_drawing(project_id, page_id, filepath)

        finally:
            try:
                self.page.remove_listener("response", _on_response)
            except Exception:
                pass

    async def fetch_page_thumbnail(
        self,
        project_id: int,
        page_id: int,
    ) -> "bytes | None":
        """
        Return the raw JPEG bytes of StackCT's pre-rendered thumbnail for a page.
        The thumbnail (~100-175 KB) is served from Azure Blob storage under
        .../thumbnail/{project_id}_{page_id}.jpeg and is always available.

        Navigates to the page to trigger the thumbnail request, then returns bytes.
        Does NOT save to disk — the caller decides where to store it.
        Returns None on failure.
        """
        thumbnail_bytes: list[bytes] = []

        async def _on_response(resp) -> None:
            url = resp.url
            if self._BLOB_HOST not in url:
                return
            if "/thumbnail/" not in url:
                return
            if f"_{page_id}." not in url:
                return
            try:
                body = await resp.body()
                if len(body) > 5_000:
                    thumbnail_bytes.append(body)
            except Exception:
                pass

        self.page.on("response", _on_response)
        try:
            await self.navigate_to_page(project_id, page_id)
            # Thumbnails are requested immediately on page load
            deadline = time.time() + 20
            while time.time() < deadline:
                await asyncio.sleep(0.5)
                if thumbnail_bytes:
                    break
            return thumbnail_bytes[0] if thumbnail_bytes else None
        finally:
            try:
                self.page.remove_listener("response", _on_response)
            except Exception:
                pass

    # Selectors for StackCT's minimap / thumbnail panel (bottom-left overlay).
    # It's a separate Canvas2D element and is always rendered correctly even when
    # the main WebGL canvas hasn't finished loading tiles.
    _MINIMAP_SELECTORS = [
        "#thumbnail-canvas",
        "canvas.thumbnail-canvas",
        '[class*="thumbnail"] canvas',
        '[class*="minimap"] canvas',
        '[class*="overview"] canvas',
        "canvas#overview-canvas",
    ]

    async def _screenshot_minimap(self, filepath: str) -> bool:
        """
        Capture StackCT's always-rendered minimap as a last-resort fallback.
        The minimap is a Canvas2D element that is never blank.
        Returns True and saves to filepath if captured.
        """
        for sel in self._MINIMAP_SELECTORS:
            try:
                el = await self.page.query_selector(sel)
                if not el:
                    continue
                box = await el.bounding_box()
                if not box or box["width"] < 40:
                    continue
                buf = await el.screenshot()
                if self._is_blank_png(buf) or len(buf) < 2000:
                    continue
                with open(filepath, "wb") as fh:
                    fh.write(buf)
                logger.info(
                    f"Minimap fallback captured ({sel}): "
                    f"{box['width']:.0f}×{box['height']:.0f}px, {len(buf):,} bytes"
                )
                return True
            except Exception:
                continue
        return False

    async def screenshot_full_drawing(
        self, project_id: int, page_id: int, filepath: str, max_retries: int = 1
    ) -> bool:
        """
        Navigate to a drawing page and capture the drawing canvas.

        Strategy (each attempt):
          1. Wait for tile network activity to settle  ← NEW
          2. Wait for canvas pixel stability (blank-aware)  ← FIXED
          3. Dismiss "Loading" overlay
          4. Screenshot the main canvas element
          5. Validate content (not blank)  ← NEW
          6. If still blank → minimap fallback  ← NEW
        """
        for attempt in range(max_retries + 1):
            try:
                if not await self.navigate_to_page(project_id, page_id):
                    raise Exception("Navigation to page failed")

                current_url = self.page.url
                if f"/Page/{page_id}" not in current_url:
                    logger.warning(f"Wrong URL after nav: {current_url[:100]}")
                    url = (
                        f"https://go.stackct.com/app/#/Takeoff/{project_id}"
                        f"/Page/{page_id}/@0,0,0z"
                    )
                    await self.page.goto(url, wait_until="load")
                    await asyncio.sleep(3)

                await self._dismiss_popups()

                # Click "fit to screen" so the full drawing is in view
                for selector in [
                    '[data-id="fit-to-screen"]', '[data-id="fit-page"]',
                    '[title*="Fit" i]', '[aria-label*="fit" i]',
                    'button[title*="fit" i]',
                ]:
                    try:
                        btn = await self.page.query_selector(selector)
                        if btn and await btn.is_visible():
                            await btn.click()
                            break
                    except Exception:
                        pass

                # ── NEW: wait for tile images to finish loading ──────────────
                tile_count = await self._wait_for_tiles_loaded(
                    timeout_s=45 + attempt * 15
                )
                logger.info(f"Tile load wait complete ({tile_count} tiles)")

                canvas_selector = "#canvas-interaction"
                timeout = (
                    CANVAS_STABILITY_TIMEOUT
                    if attempt == 0
                    else CANVAS_STABILITY_TIMEOUT + 10
                )
                stable = await self._wait_for_canvas_stable(
                    canvas_selector, timeout_s=timeout
                )
                if not stable:
                    logger.warning(
                        f"Canvas not stable after timeout (attempt {attempt + 1})"
                    )

                try:
                    await self.page.wait_for_selector(
                        "text=Loading", state="hidden", timeout=8000
                    )
                except Exception:
                    pass

                # ── Capture the main canvas ──────────────────────────────────
                captured = False
                for sel in [
                    "#canvas-interaction",
                    "canvas#canvas-interaction",
                    '[id*="canvas-content"]',
                    'canvas[id*="canvas"]',
                ]:
                    try:
                        el = await self.page.query_selector(sel)
                        if not el:
                            continue
                        box = await el.bounding_box()
                        if not box or box["width"] <= 400 or box["height"] <= 300:
                            continue
                        buf = await el.screenshot()
                        if self._is_blank_png(buf):
                            logger.warning(
                                f"Canvas '{sel}' appears blank "
                                f"({len(buf):,} bytes) — trying minimap fallback"
                            )
                            break   # blank canvas → fall through to minimap
                        with open(filepath, "wb") as fh:
                            fh.write(buf)
                        logger.info(
                            f"Captured canvas '{sel}' at "
                            f"{box['width']:.0f}×{box['height']:.0f}px, "
                            f"{len(buf):,} bytes"
                        )
                        captured = True
                        break
                    except Exception:
                        continue

                # ── Minimap fallback (blank main canvas) ─────────────────────
                if not captured:
                    logger.info("Trying minimap / thumbnail fallback…")
                    captured = await self._screenshot_minimap(filepath)

                # ── Last resort: viewport screenshot (has chrome, but better than nothing)
                if not captured:
                    logger.info("All canvas attempts failed — using viewport screenshot")
                    await self.page.screenshot(path=filepath, full_page=False)

                if not os.path.exists(filepath):
                    raise Exception("Screenshot file not created")

                size = os.path.getsize(filepath)
                if size < 5000:
                    raise Exception(
                        f"Screenshot too small ({size} bytes) — likely blank or partial"
                    )

                logger.info(f"Screenshot saved: {filepath} ({size:,} bytes)")
                return True

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f"Screenshot failed (attempt {attempt + 1}/"
                        f"{max_retries + 1}): {e}"
                    )
                    logger.info("Retrying with extended timeout...")
                    await asyncio.sleep(2)
                    continue
                logger.error(
                    f"Screenshot failed after {max_retries + 1} attempts: {e}"
                )
                return False
        return False

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")
