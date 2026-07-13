"""
Diagnostic: navigate to one StackCT drawing page and log ALL network responses
(URL, content-type, size) so we can identify what image/PDF URLs are fetched.
Also tries clicking any visible download/export button.

Usage:
    python3 scripts/network_capture.py [project_id] [page_id]
Defaults to Baking Social / first cached page.
"""
import asyncio
import logging
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from browser import StackCTBrowser
import stackct_store as store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


async def main(project_id: int, page_id: int):
    store.init_db()
    responses: list[dict] = []

    browser = StackCTBrowser()
    await browser.start()

    try:
        # Capture ALL responses
        async def on_response(resp):
            ct = resp.headers.get("content-type", "")
            try:
                body = await resp.body()
                size = len(body)
            except Exception:
                size = 0
            responses.append({
                "url": resp.url,
                "status": resp.status,
                "content_type": ct,
                "size": size,
            })

        browser.page.on("response", on_response)

        print(f"\n{'='*70}")
        print(f"Logging in…")
        if not await browser.login():
            print("Login failed")
            return

        print(f"Navigating to project {project_id} / page {page_id}…")
        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}/Page/{page_id}/@0,0,0z"
        await browser.page.goto(url, wait_until="load")
        print("Waiting 15s for tiles/API calls to settle…")
        await asyncio.sleep(15)

        print(f"\n{'='*70}")
        print("ALL RESPONSES by size (desc):")
        print(f"{'SIZE':>10}  {'STATUS':>6}  {'CONTENT-TYPE':<35}  URL")
        print("-"*100)
        for r in sorted(responses, key=lambda x: x["size"], reverse=True)[:60]:
            short_url = r["url"][:80]
            print(f"{r['size']:>10,}  {r['status']:>6}  {r['content_type']:<35}  {short_url}")

        # Highlight image/PDF candidates
        print(f"\n{'='*70}")
        print("IMAGE / PDF CANDIDATES (size > 30 KB):")
        candidates = [
            r for r in responses
            if r["size"] > 30_000 and any(
                t in (r["content_type"] or "")
                for t in ("image/", "application/pdf", "application/octet")
            )
        ]
        candidates.sort(key=lambda x: x["size"], reverse=True)
        for r in candidates:
            print(f"  {r['size']:>10,}  {r['content_type']:<35}  {r['url']}")

        # Look for download/export buttons
        print(f"\n{'='*70}")
        print("SCANNING for download/export buttons…")
        for sel in [
            '[aria-label*="download" i]', '[aria-label*="export" i]',
            '[title*="download" i]', '[title*="export" i]', '[title*="print" i]',
            'button:has-text("Download")', 'button:has-text("Export")',
            'button:has-text("Print")', 'a[download]',
            '[class*="download" i]', '[class*="export" i]',
        ]:
            try:
                els = await browser.page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        text = (await el.inner_text()).strip()[:80]
                        cls = await el.get_attribute("class") or ""
                        tag = await el.evaluate("el => el.tagName")
                        print(f"  FOUND [{sel}] tag={tag} text='{text}' class='{cls[:60]}'")
            except Exception:
                pass

        # Save HAR-like dump
        import json
        out = "scripts/network_capture_output.json"
        with open(out, "w") as f:
            json.dump(sorted(responses, key=lambda x: x["size"], reverse=True)[:200], f, indent=2)
        print(f"\nFull response log saved to: {out}")

    finally:
        await browser.close()


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 6836123
    pgid = int(sys.argv[2]) if len(sys.argv) > 2 else 633967066
    asyncio.run(main(pid, pgid))
