import asyncio
import logging
from typing import List
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from config import (
    STACKCT_EMAIL, STACKCT_PASSWORD,
    STACKCT_LOGIN_URL, STACKCT_PROJECTS_URL,
    HEADLESS, PAGE_LOAD_TIMEOUT
)

logger = logging.getLogger(__name__)


class StackCTBrowser:
    def __init__(self):
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self.page: Page = None

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
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

            # Wait for redirect back to the StackCT app
            await self.page.wait_for_url("**/go.stackct.com/app/**", timeout=25000)
            logger.info("Login successful")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
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
        """Return list of {id, name} for all projects."""
        logger.info("Getting project list")
        await self.page.goto(STACKCT_PROJECTS_URL, wait_until="load")
        await asyncio.sleep(3)  # Let Angular render the project list
        await self.page.wait_for_selector("text=PROJECT NAME", timeout=15000)

        projects = []
        # Each project row has a link or clickable element
        rows = await self.page.query_selector_all('[class*="project-row"], tbody tr, [class*="project-item"]')

        if not rows:
            # Fallback: get project names from visible text
            items = await self.page.query_selector_all('text=/[A-Z]/')
            logger.warning("Using fallback project detection")

        # Extract project IDs from links — deduplicate by ID, keep the one with a name
        project_links = await self.page.query_selector_all('a[href*="Takeoff"]')
        seen_ids = {}
        for link in project_links:
            href = await link.get_attribute("href")
            text = (await link.inner_text()).strip()
            if href and "Takeoff" in href:
                try:
                    project_id = int(href.split("Takeoff/")[1].split("/")[0])
                except (IndexError, ValueError):
                    continue
                # Prefer the entry that has a non-empty name
                if project_id not in seen_ids or (text and not seen_ids[project_id]["name"]):
                    seen_ids[project_id] = {"id": project_id, "name": text}

        projects = [v for v in seen_ids.values() if v["name"]]
        logger.info(f"Found {len(projects)} projects")
        return projects

    async def get_all_page_ids(self, project_id: int) -> List[dict]:
        """
        Discover all drawing page IDs from the thumbnail grid.
        StackCT embeds data-page-id attributes directly in the DOM —
        no need to click through each page.
        Returns list of {page_id, sheet_name}.
        """
        logger.info(f"Discovering all pages for project {project_id}")

        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}"
        await self.page.goto(url, wait_until="load")
        # Wait for thumbnails to render — grid can be slow on first load
        pages_raw = []
        for attempt in range(3):
            try:
                await self.page.wait_for_selector('[data-page-id]', timeout=30000)
                await asyncio.sleep(2 + attempt)
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
                if pages_raw:
                    break
            except Exception:
                if attempt < 2:
                    logger.warning(f"Page grid not ready (attempt {attempt + 1}/3), retrying...")
                    await asyncio.sleep(3)
                    await self.page.goto(url, wait_until="load")
                else:
                    logger.error("No [data-page-id] elements found — plans grid may not have loaded")
                    return []

        pages = [p for p in pages_raw if p["page_id"]]
        for p in pages:
            logger.info(f"  Found page: {p['sheet_name']} (ID: {p['page_id']})")

        logger.info(f"Discovered {len(pages)} pages")
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

    async def screenshot_full_drawing(self, project_id: int, page_id: int, filepath: str) -> bool:
        """Navigate to a drawing page and screenshot the actual drawing canvas
        directly (StackCT renders it into #canvas-interaction at high resolution)."""
        try:
            if not await self.navigate_to_page(project_id, page_id):
                return False

            # Confirm we're on the per-page URL
            current_url = self.page.url
            if f"/Page/{page_id}" not in current_url:
                logger.warning(f"Wrong URL after nav: {current_url[:100]}")
                url = f"https://go.stackct.com/app/#/Takeoff/{project_id}/Page/{page_id}/@0,0,0z"
                await self.page.goto(url, wait_until="load")
                await asyncio.sleep(3)

            # Dismiss popups if present (best effort)
            await self._dismiss_popups()

            # Click "Fit to page" so the entire drawing is rendered into the canvas
            for selector in ['[data-id="fit-to-screen"]', '[data-id="fit-page"]',
                             '[title*="Fit" i]', '[aria-label*="fit" i]',
                             'button[title*="fit" i]']:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn and await btn.is_visible():
                        await btn.click()
                        break
                except Exception:
                    pass

            # Wait for tiles to fully render
            await asyncio.sleep(5)
            try:
                await self.page.wait_for_selector("text=Loading", state="hidden", timeout=8000)
            except Exception:
                pass

            # StackCT renders the drawing into a high-res canvas (#canvas-interaction or sibling).
            # Screenshot that element directly — no sidebar, no popup, just the drawing.
            captured = False
            for sel in ['#canvas-interaction',
                        'canvas#canvas-interaction',
                        '[id*="canvas-content"]',
                        'canvas[id*="canvas"]']:
                try:
                    el = await self.page.query_selector(sel)
                    if el:
                        box = await el.bounding_box()
                        if box and box["width"] > 400 and box["height"] > 300:
                            await el.screenshot(path=filepath)
                            logger.info(f"Captured canvas '{sel}' at {box['width']}x{box['height']}")
                            captured = True
                            break
                except Exception:
                    continue

            if not captured:
                # Fallback: full viewport screenshot
                logger.info("No canvas element found — using viewport screenshot")
                await self.page.screenshot(path=filepath, full_page=False)

            import os
            size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            logger.info(f"Screenshot saved: {filepath} ({size:,} bytes)")
            return size > 5000

        except Exception as e:
            logger.error(f"Screenshot failed for page {page_id}: {e}")
            return False

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")
