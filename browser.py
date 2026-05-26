import asyncio
import hashlib
import logging
import os
import time
from typing import List
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
        """Return list of {id, name} for ALL projects (handles virtual scrolling)."""
        logger.info("Getting project list with virtual scroll handling")
        await self.page.goto(STACKCT_PROJECTS_URL, wait_until="load")
        await self.page.wait_for_selector("text=PROJECT NAME", timeout=15000)
        await asyncio.sleep(2)

        seen_ids = set()
        prev_count = 0
        stalled_iterations = 0
        max_stalls = 3

        for scroll_iteration in range(20):
            project_links = await self.page.query_selector_all('a[href*="Takeoff"]')
            for link in project_links:
                href = await link.get_attribute("href")
                if href and "Takeoff" in href:
                    try:
                        project_id = int(href.split("Takeoff/")[1].split("/")[0])
                        seen_ids.add(project_id)
                    except (IndexError, ValueError):
                        continue

            current_count = len(seen_ids)
            logger.debug(
                f"Scroll iteration {scroll_iteration + 1}: {current_count} projects found"
            )

            if current_count == prev_count:
                stalled_iterations += 1
                if stalled_iterations >= max_stalls:
                    logger.info(
                        f"No new projects after {max_stalls} scrolls — collection complete"
                    )
                    break
            else:
                stalled_iterations = 0

            prev_count = current_count

            await self.page.evaluate("""
                const container = document.querySelector(
                    '[class*="virtual-scroll"], [class*="cdk-virtual-scroll"]'
                );
                if (container) {
                    container.scrollTo(0, container.scrollHeight);
                } else {
                    window.scrollTo(0, document.body.scrollHeight);
                }
            """)
            await asyncio.sleep(1.5)

        project_map = {}
        await self.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

        for _ in range(10):
            project_links = await self.page.query_selector_all('a[href*="Takeoff"]')
            for link in project_links:
                href = await link.get_attribute("href")
                text = (await link.inner_text()).strip()
                if href and "Takeoff" in href and text:
                    try:
                        project_id = int(href.split("Takeoff/")[1].split("/")[0])
                        if project_id in seen_ids and project_id not in project_map:
                            project_map[project_id] = text
                    except (IndexError, ValueError):
                        continue

            if len(project_map) >= len(seen_ids):
                break

            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

        projects = [
            {"id": pid, "name": project_map.get(pid, f"Project_{pid}")}
            for pid in seen_ids
        ]
        projects.sort(key=lambda p: p["name"].lower())
        logger.info(f"Found {len(projects)} projects after virtual scroll handling")
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

    async def get_plan_sets(self, project_id: int) -> list[dict]:
        """
        Discover all plan sets (folders) for a project, with deduplication.
        Returns list of {folder_id, name, sheet_count}.
        
        For projects with no folder cards (direct grid), returns a single
        synthetic set with folder_id=0.
        """
        logger.info(f"Discovering plan sets for project {project_id}")
        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}"
        await self.page.goto(url, wait_until="load", timeout=60000)
        
        # Wait for plan set cards to render
        await asyncio.sleep(2.5)
        
        # Extract all folder cards
        raw_sets = await self.page.evaluate('''() => {
            const sets = [];
            const seen = new Set();
            document.querySelectorAll('[data-folder-id]').forEach(el => {
                const id = parseInt(el.getAttribute('data-folder-id'), 10);
                if (!id || seen.has(id)) return;
                const name = (el.textContent || '').trim().replace(/\\s+/g, ' ');
                if (!name || name.length < 4) return;
                // Prefer short labels (folder card / tree row)
                const short = name.split('>').pop().trim();
                if (short.length > 150) return;
                seen.add(id);
                sets.push({ folder_id: id, name: short });
            });
            return sets;
        }''')
        
        # Apply dedupe rules
        candidates = normalize_plan_sets(raw_sets)
        
        # For each candidate, click folder and count sheets
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
        
        # Direct-grid fallback: if zero sets after dedupe but pages exist on landing
        if len(plan_sets) == 0:
            logger.info("No plan set folders found — checking for direct grid...")
            # Re-navigate to ensure clean state
            await self.page.goto(url, wait_until="load", timeout=60000)
            # Wait up to 30s for page grid to appear
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
                        f"Direct-grid fallback: {landing_count} sheets "
                        f"(no folder cards)"
                    )
                    return [{
                        "folder_id": 0,
                        "name": "All drawing sheets",
                        "sheet_count": landing_count,
                    }]
            logger.warning("No plan sets and no landing grid pages found")
        
        logger.info(f"Discovered {len(plan_sets)} plan sets")
        return plan_sets

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

    async def _wait_for_canvas_stable(
        self,
        selector: str,
        timeout_s: int = None,
        stable_checks: int = None,
    ) -> bool:
        """Wait until canvas pixels stop changing (drawing fully rendered)."""
        if timeout_s is None:
            timeout_s = CANVAS_STABILITY_TIMEOUT
        if stable_checks is None:
            stable_checks = CANVAS_STABILITY_CHECKS

        prev_hash = None
        stable_count = 0
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
                if h == prev_hash:
                    stable_count += 1
                    if stable_count >= stable_checks:
                        elapsed = time.time() - start
                        logger.info(f"Canvas stable after {elapsed:.1f}s")
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

    async def screenshot_full_drawing(
        self, project_id: int, page_id: int, filepath: str, max_retries: int = 1
    ) -> bool:
        """Navigate to a drawing page and screenshot the actual drawing canvas
        directly (StackCT renders it into #canvas-interaction at high resolution)."""
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

                captured = False
                for sel in [
                    "#canvas-interaction",
                    "canvas#canvas-interaction",
                    '[id*="canvas-content"]',
                    'canvas[id*="canvas"]',
                ]:
                    try:
                        el = await self.page.query_selector(sel)
                        if el:
                            box = await el.bounding_box()
                            if box and box["width"] > 400 and box["height"] > 300:
                                await el.screenshot(path=filepath)
                                logger.info(
                                    f"Captured canvas '{sel}' at "
                                    f"{box['width']}x{box['height']}"
                                )
                                captured = True
                                break
                    except Exception:
                        continue

                if not captured:
                    logger.info("No canvas element found — using viewport screenshot")
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
