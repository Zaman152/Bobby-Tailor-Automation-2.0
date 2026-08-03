#!/usr/bin/env python3
"""Per-room measurement probe (ZERO API).

Answers: does the deterministic room engine find a building's ROOMS, and are
their areas physically plausible? Moxy's take-off is per-room (Gyp Ceiling
58,680 SF, Gyp Wall 129,521 SF across ~20 guestroom floor plans), so room
polygons are the missing measurement primitive.

Two engines, because the app has two and only one of them produces Moxy's
numbers:

``--engine vector``
    ``rooms.extract_rooms`` — polygonizes the wall CENTERLINE network. Needs a
    human-supplied ``--fpi`` because it measures the whole page at one scale.

``--engine fill``
    ``room_fill.measure_enclosed_area`` via the pipeline's own
    ``_measure_room_fills`` — renders each titled drawing and flood-fills it AT
    ITS OWN PRINTED SCALE. No ``--fpi``: the drawing states its scale, and
    borrowing another drawing's is a squared error.

Until now **no committed script exercised the fill engine**, which is precisely
why a wrong diagnosis of Moxy's areas went unchallenged for so long (INV-08
§1.5). It also means the fill engine must NOT be gated on sheet type: Moxy's
guestroom prototypes classify ``title_sheet`` and carry every guestroom
quantity, so a plan-type gate skips exactly the drawings that matter.

Non-circular validation: a hotel guestroom is ~250-350 SF. Golden ceiling SF
divided by the room count must land in that band — if it does, the scale AND the
polygons are both right, without ever peeking at a golden per-room number.

Usage:
    python3 scripts/room_probe.py "uploads/Moxy...-Plans.pdf" --engine vector --fpi 8.0
    python3 scripts/room_probe.py "uploads/Moxy...-Plans.pdf" --engine fill --pages 23,27,29,33
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

from bobbytailor.deterministic.dimensions import extract_dimension_samples  # noqa: E402
from bobbytailor.deterministic.rooms import extract_rooms  # noqa: E402
from bobbytailor.deterministic.scale_solver import (  # noqa: E402
    select_main_plan,
    solve_viewport_scale,
)
from bobbytailor.deterministic.viewports import segment_viewports  # noqa: E402
from bobbytailor.deterministic.walls import extract_walls  # noqa: E402
from bobbytailor.pipeline.sheet_pass_matrix import classify_sheet_type_from_text  # noqa: E402
from bobbytailor.pipeline.takeoff_pipeline import (  # noqa: E402
    _MASK_VIEWPORT_KINDS,
    _viewport_printed_fpi,
    TakeoffPipeline,
)

_MASK_KINDS = tuple(_MASK_VIEWPORT_KINDS)


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


def viewports_with_scales(page, doc=None, page_index: int = 0):
    """(viewport, ViewportScale) pairs, built exactly as the pipeline builds them.

    ``select_main_plan`` reads ``vs.fpp`` and ``vs.confidence`` off the second
    element, so pairing each viewport with ``None`` — as this probe did — makes
    it dereference a null scale on every page. That ``AttributeError: 'NoneType'
    object has no attribute 'fpp'`` was reported independently by INV-01 §7,
    INV-02 §9 and INV-08 §1.5, and it meant the probe never actually ran.
    """
    vps = segment_viewports(page)
    samples = extract_dimension_samples(page, page_index=page_index, doc=doc)
    printed_by_region = _viewport_printed_fpi(page, vps)
    pairs = []
    for vp in vps:
        if vp.kind in _MASK_KINDS:
            pairs.append((vp, solve_viewport_scale([], vp)))
            continue
        pairs.append(
            (
                vp,
                solve_viewport_scale(
                    samples, vp, printed_fpi=printed_by_region.get(vp.region_id)
                ),
            )
        )
    return vps, pairs


def probe_vector(pdf_path: str, fpi: float, only_pages=None) -> None:
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
            # NOT a silent continue. INV-08 §1.5 caught this probe reproducing
            # the pipeline's own blindness in the tooling: on Crow every page
            # classifies `schedule` on full-page text, so the old probe printed
            # NOTHING and reported `TOTAL rooms=0` — indistinguishable from a
            # building with no rooms. A skip must state itself.
            print(f"  page {i:>2} [{stype:<10}] SKIPPED — the vector engine is "
                  f"gated on the sheet type, and this is not a plan sheet")
            continue
        try:
            vps, pairs = viewports_with_scales(page, doc=doc, page_index=i)
            mask = [v.bbox_pt for v in vps if v.kind in _MASK_KINDS]
            main_id = select_main_plan(pairs)
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


def probe_fill(pdf_path: str, only_pages=None) -> None:
    """Run the ENCLOSED-REGION engine — the one that produces Moxy's numbers.

    Deliberately NOT gated on the sheet type. A sheet is a COLLECTION of
    drawings and its type is only the dominant one; Moxy's 16 guestroom
    prototypes classify ``title_sheet`` on the title-block crop and hold every
    guestroom quantity in the set.
    """
    from bobbytailor.deterministic.printed_scale import (
        extract_printed_scales,
        match_scales_to_viewports,
    )

    pipeline = TakeoffPipeline(analyzer=lambda *a, **k: {})
    doc = fitz.open(pdf_path)
    print(f"{Path(pdf_path).name}: {doc.page_count} pages, enclosed-region engine "
          f"(each drawing at ITS OWN printed scale — no assumed --fpi)")
    grand_fills = 0
    grand_area = 0.0
    grand_drops = 0
    for i in range(doc.page_count):
        if only_pages and i not in only_pages:
            continue
        page = doc[i]
        stype = classify_sheet_type_from_text("", page.get_text())
        try:
            vps = segment_viewports(page)
            by_region = match_scales_to_viewports(
                extract_printed_scales(page), vps, page=page
            )
            fills, drops = pipeline._measure_room_fills(
                page, vps, by_region, "page%d" % i
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  page {i:>2} [{stype}]: ERROR {type(exc).__name__}: {exc}")
            continue
        if not fills and not drops:
            # Same rule: say so. Crow's main floor plan carries zero
            # "<NAME> - <KIND> PLAN" titles, so the fill engine has nothing to
            # anchor on — an honest structural gap, not a measured zero.
            print(f"  page {i:>2} [{stype:<11}] no titled plan drawing to anchor "
                  f"a fill on — nothing measured, nothing dropped")
            continue
        page_area = sum(f.area_sf for f in fills)
        grand_fills += len(fills)
        grand_area += page_area
        grand_drops += len(drops)
        print(f"  page {i:>2} [{stype:<11}] fills={len(fills):>2} "
              f"dropped={len(drops):>2} area_sum={page_area:>9,.1f} SF")
        for f in sorted(fills, key=lambda f: -f.area_sf):
            print(f"        {f.plan_name:<22} {f.plan_kind:<4} "
                  f"{f.area_sf:>8,.1f} SF  @ {f.scale_fpi or 0.0:>6.2f} ft/in"
                  f"{'  [needs review] ' + f.review_reason if f.needs_review else ''}")
        for d in drops:
            print(f"        {d.title:<28} {d.disposition:<18} NOT MEASURED — "
                  f"{d.reason}")
    print(f"\n== TOTAL fills={grand_fills}  enclosed-area={grand_area:,.1f} SF  "
          f"drawings NOT measured (each with a reason)={grand_drops}")
    if grand_fills:
        print(f"== mean fill area = {grand_area/grand_fills:,.1f} SF "
              f"(a hotel guestroom is ~250-350 SF — that is the sanity band)")
    doc.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--engine", choices=("vector", "fill"), default="vector",
                    help="vector = wall-centerline polygons (needs --fpi); "
                         "fill = enclosed regions at each drawing's own printed scale")
    ap.add_argument("--fpi", type=float, default=8.0,
                    help="feet per inch (human-supplied scale; --engine vector only)")
    ap.add_argument("--pages", default="", help="comma-separated page indices")
    a = ap.parse_args()
    pages = {int(x) for x in a.pages.split(",") if x.strip()} or None
    if a.engine == "fill":
        probe_fill(a.pdf, pages)
    else:
        probe_vector(a.pdf, a.fpi, pages)
