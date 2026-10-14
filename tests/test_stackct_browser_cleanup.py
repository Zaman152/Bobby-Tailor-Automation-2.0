"""The Playwright driver must be stopped even when the browser fails to start (no browser)."""
import asyncio
import unittest
from unittest import mock

from bobbytailor.scrape import browser as browser_mod
from bobbytailor.scrape import stackct_sync


class _FakePlaywright:
    def __init__(self):
        self.stopped = False
        self.chromium = mock.Mock()
        self.chromium.launch = mock.AsyncMock(side_effect=RuntimeError("Executable doesn't exist"))

    async def stop(self):
        self.stopped = True


class StackctBrowserCleanupTests(unittest.TestCase):
    def setUp(self):
        self.pw = _FakePlaywright()
        starter = mock.Mock()
        starter.start = mock.AsyncMock(return_value=self.pw)
        patcher = mock.patch.object(browser_mod, "async_playwright", return_value=starter)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_failed_launch_stops_driver(self):
        fetches = [
            lambda: stackct_sync._fetch_projects_from_browser(),
            lambda: stackct_sync._fetch_plan_sets_from_browser(1),
            lambda: stackct_sync._fetch_plans_in_folder_from_browser(1, 2),
        ]
        for fetch in fetches:
            self.pw.stopped = False
            with self.assertRaises(RuntimeError):
                asyncio.run(fetch())
            self.assertTrue(self.pw.stopped)

    def test_close_stops_driver_when_browser_close_fails(self):
        b = browser_mod.StackCTBrowser()
        b._playwright = self.pw
        b._browser = mock.Mock()
        b._browser.close = mock.AsyncMock(side_effect=RuntimeError("browser gone"))
        with self.assertRaises(RuntimeError):
            asyncio.run(b.close())
        self.assertTrue(self.pw.stopped)


if __name__ == "__main__":
    unittest.main()
