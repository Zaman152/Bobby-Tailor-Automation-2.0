#!/usr/bin/env python3
"""Per-room measurement probe (ZERO API).

Answers: does the deterministic room engine find a building's ROOMS, and are
their areas physically plausible? Moxy's take-off is per-room (Gyp Ceiling
58,680 SF, Gyp Wall 129,521 SF across ~20 guestroom floor plans), so room
polygons are the missing measurement primitive.

Non-circular validation: a hotel guestroom is ~250-350 SF. Golden ceiling SF
divided by the room count must land in that band — if it does, the scale AND the
polygons are both right, without ever peeking at a golden per-room number.

Usage:
    python3 scripts/room_probe.py "uploads/Moxy...-Plans.pdf" --fpi 8.0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import fitz  # noqa: E402

from bobbytailor.deterministic.rooms import extract_rooms  # noqa: E402
from bobbytailor.deterministic.scale_solver import select_main_plan  # noqa: E402
from bobbytailor.deterministic.viewports import segment_viewports  # noqa: E402
from bobbytailor.deterministic.walls import extract_walls  # noqa: E402
from bobbytailor.pipeline.sheet_pass_matrix import classify_sheet_type_from_text  # noqa: E402


def _wkt_points(wkt: str):
    """[(x, y), ...] from a POLYGON((x y, x y, ...)) string."""
    try:
        inner = wkt[wkt.index("((") + 2: wkt.rindex("))")]
    except ValueError:
        return []
    pts = []
    for pair in inner.split(","):
        bits = pair.strip().split()
        if len(bits) >= 2:
            try:
                pts.append((float(bits[0]), float(bits[1])))
            except ValueError:
                pass
    return pts


def _perimeter_pt(wkt: str) -> float:
    pts = _wkt_points(wkt)
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return total


def probe(pdf_path: str, fpi: float, only_pages=None) -> None:
    fpp = fpi / 72.0
    doc = fitz.open(pdf_path)
    print(f"{Path(pdf_path).name}: {doc.page_count} pages, assumed scale {fpi} ft/in "
          f"(fpp={fpp:.4f})")
    grand_rooms = 0
    grand_area = 0.0
    grand_perim = 0.0
    for i in range(doc.page_count):
        if only_pages and i not in only_pages:
            continue
        page = doc[i]
        stype = classify_sheet_type_from_text("", page.get_text())
        if stype not in ("floor_plan", "roof_plan", "civil_site"):
            continue
        try:
            vps = segment_viewports(page)
            mask = [v.bbox_pt for v in vps
                    if v.kind in ("title_block", "legend", "schedule")]
            main_id = select_main_plan([(v, None) for v in vps])
            main_bbox = next((v.bbox_pt for v in vps if v.region_id == main_id), None)
            walls = extract_walls(page, fpp, exclude_rects=mask)
            rooms = extract_rooms(page, walls, main_bbox, fpp)
        except Exception as exc:  # noqa: BLE001
            print(f"  page {i:>2} [{stype}]: ERROR {type(exc).__name__}: {exc}")
            continue

        measured = []
        for r in rooms:
            area_sf = float(getattr(r, "area_pt2", 0.0) or 0.0) * fpp * fpp
            perim_lf = _perimeter_pt(getattr(r, "polygon_wkt", "") or "") * fpp
            measured.append((area_sf, perim_lf, r))
        areas = [a for a, _p, _r in measured if a > 0]
        n = len(rooms)
        grand_rooms += n
        grand_area += sum(areas)
        grand_perim += sum(p for _a, p, _r in measured)
        med = sorted(areas)[len(areas) // 2] if areas else 0
        print(f"  page {i:>2} [{stype:<10}] walls={len(walls):>4} rooms={n:>3} "
              f"area_sum={sum(areas):>10,.0f} SF  median_room={med:>7,.0f} SF")
        for area_sf, perim_lf, r in sorted(measured, key=lambda t: -t[0])[:3]:
            print(f"        room {getattr(r,'candidate_id','?'):<8} "
                  f"area={area_sf:>9,.0f} SF perim={perim_lf:>7,.0f} LF "
                  f"label={getattr(r,'label','') or ''!r:20} src={getattr(r,'label_source','')}")
    print(f"\n== TOTAL rooms={grand_rooms}  ceiling-area(sum of room polygons)="
          f"{grand_area:,.0f} SF  perimeter-sum={grand_perim:,.0f} LF")
    if grand_rooms:
        print(f"== mean room area = {grand_area/grand_rooms:,.0f} SF "
              f"(a hotel guestroom is ~250-350 SF — that is the sanity band)")
    doc.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--fpi", type=float, default=8.0, help="feet per inch (human-supplied scale)")
    ap.add_argument("--pages", default="", help="comma-separated page indices")
    a = ap.parse_args()
    pages = {int(x) for x in a.pages.split(",") if x.strip()} or None
    probe(a.pdf, a.fpi, pages)
