#!/usr/bin/env python3
"""Discover StackCT plan-set (folder) cards on a project's Takeoff page."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from browser import StackCTBrowser  # noqa: E402


DISCOVER_JS = """() => {
  const out = { folders: [], pageIdsOnLanding: [], hints: [] };

  // Folder / plan-set cards (StackCT Plans view)
  const folderSelectors = [
    '[data-folder-id]',
    '[data-id*="folder"]',
    'a[href*="Folder"]',
    '[class*="folder"]',
    '[class*="Folder"]',
  ];
  for (const sel of folderSelectors) {
    document.querySelectorAll(sel).forEach(el => {
      const id = el.getAttribute('data-folder-id')
        || el.getAttribute('data-id')
        || el.getAttribute('href');
      const name = (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 120);
      if (name && name.length > 2) {
        out.folders.push({ selector: sel, id, name, tag: el.tagName });
      }
    });
  }

  // Dedupe folders by name
  const seen = new Set();
  out.folders = out.folders.filter(f => {
    const k = f.name + '|' + f.id;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });

  document.querySelectorAll('[data-page-id]').forEach(el => {
    out.pageIdsOnLanding.push(el.getAttribute('data-page-id'));
  });
  out.pageIdsOnLanding = [...new Set(out.pageIdsOnLanding)];

  // Clickable cards with folder icon pattern (user screenshot)
  document.querySelectorAll('button, a, [role="button"], [class*="card"]').forEach(el => {
    const t = (el.textContent || '').trim();
    if (/ISSUE|MSP|CDs|Set/i.test(t) && t.length < 80) {
      out.hints.push({
        tag: el.tagName,
        text: t.replace(/\\s+/g, ' '),
        className: (el.className || '').toString().slice(0, 80),
        dataAttrs: [...el.attributes]
          .filter(a => a.name.startsWith('data-'))
          .map(a => ({ name: a.name, value: a.value.slice(0, 80) })),
      });
    }
  });

  return out;
}"""


async def main(project_id: int):
    b = StackCTBrowser()
    await b.start()
    try:
        await b.login()
        url = f"https://go.stackct.com/app/#/Takeoff/{project_id}"
        await b.page.goto(url, wait_until="load", timeout=60000)
        await asyncio.sleep(3)
        data = await b.page.evaluate(DISCOVER_JS)
        print(json.dumps({"project_id": project_id, "url": b.page.url, **data}, indent=2))
    finally:
        await b.close()


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 7416168
    asyncio.run(main(pid))
