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
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
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
            await self.page.goto("https://go.stackct.com/", wait_until="load", timeout=30000)

            # Auth0 redirects the page — wait for the login URL to appear
            await self.page.wait_for_url("**/id.stackct.com/**", timeout=15000)

            # Step 1: Enter email
            await self.page.wait_for_selector('input[name="username"], input[type="email"], input[type="text"]',
                                              timeout=10000)
            email_input = await self.page.query_selector('input[name="username"], input[type="email"], input[type="text"]')
            await email_input.fill(STACKCT_EMAIL)

            # Click the Continue / Next button
            await self.page.click('button[type="submit"], button[name="action"]')

            # Step 2: Enter password
            await self.page.wait_for_selector('input[type="password"]', timeout=10000)
            await self.page.fill('input[type="password"]', STACKCT_PASSWORD)
            await self.page.click('button[type="submit"], button[name="action"]')

            # Wait for redirect back to the StackCT app
            await self.page.wait_for_url("**/go.stackct.com/app/**", timeout=20000)
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
        # Wait for thumbnails to render
        try:
            await self.page.wait_for_selector('[data-page-id]', timeout=15000)
        except Exception:
            logger.error("No [data-page-id] elements found — plans grid may not have loaded")
            return []

        await asyncio.sleep(2)

        # Read all page containers with their IDs and names in one JS call
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
        for p in pages:
            logger.info(f"  Found page: {p['sheet_name']} (ID: {p['page_id']})")

        logger.info(f"Discovered {len(pages)} pages")
        return pages

    async def navigate_to_page(self, project_id: int, page_id: int) -> bool:
        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}/Page/{page_id}/@0,0,0z"
        try:
            await self.page.goto(url, wait_until="load")
            # Wait for drawing canvas to render
            await self.page.wait_for_selector("canvas, svg, [class*='drawing'], img[src*='blob.core']",
                                              timeout=20000)
            await asyncio.sleep(3)  # Extra wait for tiles to load
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to page {page_id}: {e}")
            return False

    async def screenshot_full_drawing(self, project_id: int, page_id: int, filepath: str) -> bool:
        """Navigate to page and capture a high-quality screenshot of the drawing."""
        try:
            if not await self.navigate_to_page(project_id, page_id):
                return False

            # Zoom to fit the full drawing on screen
            try:
                fit_btn = await self.page.query_selector('[title*="Fit"], [aria-label*="fit"], button[title*="fit"]')
                if fit_btn:
                    await fit_btn.click()
                    await asyncio.sleep(1)
            except Exception:
                pass

            # Take screenshot of the drawing area only (exclude toolbar/sidebar)
            drawing_area = await self.page.query_selector(
                '[class*="drawing-area"], [class*="canvas-container"], [class*="takeoff-canvas"], main canvas'
            )
            if drawing_area:
                await drawing_area.screenshot(path=filepath)
            else:
                # Fallback: screenshot the full viewport
                await self.page.screenshot(path=filepath, full_page=False)

            logger.info(f"Screenshot saved: {filepath}")
            return True

        except Exception as e:
            logger.error(f"Screenshot failed for page {page_id}: {e}")
            return False

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")
