#!/usr/bin/env python3
"""Multi-scale-per-page probe (ZERO API).

Shows, per page: every viewport, its own printed scale callout, the distinct
printed scales present, and the SINGLE page-level scale the pipeline resolves
and then uses to measure ALL geometry. Where a page carries >1 distinct scale,
every viewport whose scale differs from the resolved one is measured WRONG.

Usage:
    python3 scripts/scale_probe.py "uploads/Crow - Cass White Road-Plans.pdf"
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import fitz  # noqa: E402

from bobbytailor.deterministic.printed_scale import (  # noqa: E402
    extract_printed_scales,
    match_scales_to_viewports,
    identify_main_plan_scale,
)
from bobbytailor.deterministic.viewports import segment_viewports  # noqa: E402


def probe(pdf_path: str) -> None:
    doc = fitz.open(pdf_path)
    print(f"### {Path(pdf_path).name} — {doc.page_count} pages")
    total_multi = 0
    for i in range(doc.page_count):
        page = doc[i]
        try:
            vps = segment_viewports(page)
            printed = extract_printed_scales(page)
            by_region = match_scales_to_viewports(printed, vps)
            main = identify_main_plan_scale(printed)
        except Exception as exc:  # noqa: BLE001
            print(f"\npage {i}: ERROR {type(exc).__name__}: {exc}")
            continue

        fpis = sorted({round(p.feet_per_inch, 4) for p in printed})
        multi = len(fpis) > 1
        total_multi += 1 if multi else 0
        flag = "  <-- MULTI-SCALE PAGE" if multi else ""
        print(f"\npage {i}: viewports={len(vps)} printed_scales={len(printed)} "
              f"distinct_fpi={fpis} main={getattr(main,'feet_per_inch',None)}{flag}")
        for vp in vps[:12]:
            own = by_region.get(vp.region_id)
            own_fpi = getattr(own, "feet_per_inch", None)
            print(f"    {vp.region_id:4} kind={vp.kind:12} own_printed_fpi={own_fpi}")
        if multi:
            m = getattr(main, "feet_per_inch", None)
            wrong = [f for f in fpis if m is not None and abs(f - m) > 1e-6]
            if wrong and m:
                print(f"    !! geometry in viewports at {wrong} is measured with "
                      f"main fpi={m} -> off by factor {[round(f/m, 2) for f in wrong]}")
    print(f"\n== multi-scale pages: {total_multi}/{doc.page_count}")
    doc.close()


if __name__ == "__main__":
    for arg in (sys.argv[1:] or ["uploads/Crow - Cass White Road-Plans.pdf"]):
        probe(arg)
