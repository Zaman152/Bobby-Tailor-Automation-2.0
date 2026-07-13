#!/usr/bin/env python3
"""Audit StackCT plan-set folders across multiple projects (one browser session)."""
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from browser import StackCTBrowser  # noqa: E402

# Child folders under "Plans" — exclude system roots
SKIP_NAMES = frozenset({
    "plans", "bookmarks", "supporting documents", "supporting docs",
})

EXTRACT_SETS_JS = """() => {
  const sets = [];
  const seen = new Set();
  document.querySelectorAll('[data-folder-id]').forEach(el => {
    const id = parseInt(el.getAttribute('data-folder-id'), 10);
    if (!id || seen.has(id)) return;
    const name = (el.textContent || '').trim().replace(/\\s+/g, ' ');
    if (!name || name.length < 4) return;
    // Prefer short labels (folder card / tree row)
    const short = name.split('>').pop().trim();
    if (short.length > 80) return;
    seen.add(id);
    sets.push({ folder_id: id, name: short, full_text: name.slice(0, 200) });
  });
  return sets;
}"""

COUNT_PAGES_JS = """() => {
  const ids = new Set();
  document.querySelectorAll('[data-page-id]').forEach(el => {
    const pid = el.getAttribute('data-page-id');
    if (pid) ids.add(pid);
  });
  return ids.size;
}"""


def _is_plan_set(entry: dict) -> bool:
    name = entry["name"].lower()
    if name in SKIP_NAMES:
        return False
    if name.startswith("plans >"):
        return False
    if "supporting" in name or name == "bookmarks":
        return False
    # Under Plans tree: names like "MSP3-..." not equal to "Plans"
    return True


async def audit_project(b, project_id: int, project_name: str) -> dict:
    url = f"https://go.stackct.com/app/#/Takeoff/{project_id}"
    await b.page.goto(url, wait_until="load", timeout=60000)
    await asyncio.sleep(2.5)
    raw_sets = await b.page.evaluate(EXTRACT_SETS_JS)
    candidates = [s for s in raw_sets if _is_plan_set(s)]

    # Dedupe by folder_id, keep shortest name
    by_id = {}
    for s in candidates:
        fid = s["folder_id"]
        if fid not in by_id or len(s["name"]) < len(by_id[fid]["name"]):
            by_id[fid] = s
    plan_sets = list(by_id.values())

    landing_count = await b.page.evaluate(COUNT_PAGES_JS)
    sets_with_counts = []
    for ps in plan_sets:
        fid = ps["folder_id"]
        try:
            await b.page.click(f'[data-folder-id="{fid}"]', timeout=8000)
            await asyncio.sleep(1.5)
            count = await b.page.evaluate(COUNT_PAGES_JS)
        except Exception as e:
            count = -1
            ps["error"] = str(e)[:120]
        sets_with_counts.append({
            "folder_id": fid,
            "name": ps["name"],
            "sheet_count": count,
        })

    if len(sets_with_counts) == 0:
        pattern = "no_sets_found"
    elif len(sets_with_counts) == 1:
        pattern = "single_set"
    else:
        pattern = "multi_set"

    return {
        "project_id": project_id,
        "project_name": project_name,
        "pattern": pattern,
        "plan_set_count": len(sets_with_counts),
        "landing_page_count": landing_count,
        "plan_sets": sets_with_counts,
    }


async def main(project_ids: Optional[List[int]] = None):
    from stackct_store import init_db, list_projects

    init_db()
    projects = list_projects()
    if project_ids:
        id_set = set(project_ids)
        projects = [p for p in projects if p["id"] in id_set]
    else:
        # Default audit sample: Morehouse + mix of sizes
        sample_names = [
            "Morehouse",
            "ATL 081",
            "Bid for Baking",
            "Athens Fire",
            "LaserAway",
            "Baking Social - The Battery",
            "SmartServ",
        ]
        picked = []
        for needle in sample_names:
            for p in projects:
                if needle.lower() in p["name"].lower() and p["id"] not in {x["id"] for x in picked}:
                    picked.append(p)
                    break
        projects = picked[:8]

    b = StackCTBrowser()
    results = []
    await b.start()
    try:
        await b.login()
        for p in projects:
            print(f"Auditing {p['id']} {p['name'][:50]}...", file=sys.stderr)
            results.append(await audit_project(b, p["id"], p["name"]))
    finally:
        await b.close()

    report = {
        "audited": len(results),
        "patterns": {},
        "projects": results,
    }
    for r in results:
        report["patterns"][r["pattern"]] = report["patterns"].get(r["pattern"], 0) + 1
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else None
    asyncio.run(main(ids))
