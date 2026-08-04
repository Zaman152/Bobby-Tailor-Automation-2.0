#!/usr/bin/env python3
"""Offline deterministic-geometry probe (ZERO API cost).

Runs ONLY the pure-geometry deterministic bundle (walls / wall-classes / symbol
clusters / footprint / keynote text) on a plans PDF, page by page, and dumps the
raw geometry the fusion layer would bind names to. This is the free iteration
loop for making the CMU/Columns/Bollards/Tilt-up bindings DETERMINISTIC instead
of vision-dependent (see docs/PIPELINE-GROUND-TRUTH.md §5, memory
crow-manifest-free-baseline "make those bindings deterministic").

Per page it reports the full field set 23-RESEARCH §5.1 specifies:

  * the page rotation and the resolved feet-per-point;
  * every ``room_fill`` with its plan name and kind AND its **perimeter**,
    **shape ratio**, **wall height and the SOURCE of that height** — the four
    facts that decide whether a fill may be billed as a wall (a dominant region
    whose shape ratio is above ``MAX_HONEST_SHAPE_RATIO`` is a leak, and a
    height that did not come from the drawing must flag);
  * the ``elevation_areas`` — each facade's gross SF, its measured width, its
    datum crop and whether it was excluded;
  * the ``linear_runs`` — each open run's LF at its own drawing's scale, with
    the viewport that owns it and the typical-detail flag;
  * the ``excluded_viewports`` — a DELIBERATE off-scale exclusion is correct
    behaviour and must stay legible as such, never conflated with a failure.

Every field is emitted from one flat per-page record that is cheap to extend
and cheap to diff.

Usage:
    python3 scripts/geom_probe.py "uploads/Crow - Cass White Road-Plans.pdf"
    python3 scripts/geom_probe.py <pdf> --json         # machine-diffable, stdout
    python3 scripts/geom_probe.py <pdf> --pages=23,27  # a targeted subset
"""
from __future__ import annotations

import json
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
)
from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline  # noqa: E402
from bobbytailor.pipeline.sheet_pass_matrix import classify_sheet_type_from_text  # noqa: E402


def _page_text(page) -> str:
    try:
        return page.get_text() or ""
    except Exception:  # noqa: BLE001
        return ""


def _dominant_shape_ratio(fill):
    """The shape ratio of the fill's LARGEST region, or None.

    The dominant region is the one that carries the room; a sliver's ratio says
    nothing about whether the measurement leaked. `region_shape_ratios` is
    parallel to `regions`, so the pick is by index, not by sorting either list.
    """
    regions = list(fill.regions or [])
    ratios = list(fill.region_shape_ratios or [])
    if not regions or len(ratios) != len(regions):
        return None
    return ratios[regions.index(max(regions))]


def probe(pdf_path: str, pages=None) -> dict:
    """Probe *pages* (default: every page) of *pdf_path*.

    The page filter exists so a targeted check costs seconds rather than the
    whole set — Moxy is 40 pages and the raster fill is the dominant cost.
    """
    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})  # analyzer never called
    doc = fitz.open(pdf_path)
    wanted = range(doc.page_count) if pages is None else [
        p for p in pages if 0 <= p < doc.page_count
    ]
    out = {"pdf": pdf_path, "pages": []}
    for i in wanted:
        page = doc[i]
        text = _page_text(page)
        sheet_type = classify_sheet_type_from_text("", text)
        # Force plan-type so the walls/symbols/footprint engine runs regardless
        # of the text-only classifier (which lacks the rendered title block).
        if "--force-plan" in sys.argv and sheet_type not in (
            "floor_plan", "civil_site", "roof_plan"
        ) and i != 0:
            sheet_type = "floor_plan"
        sheet_name = f"page{i}"
        rec = {"page": i, "sheet_type": sheet_type, "text_len": len(text)}
        try:
            bundle = pipe._deterministic_bundle(
                page, doc, pdf_path, i, sheet_name, sheet_type
            )
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"
            out["pages"].append(rec)
            continue
        rec["fpp"] = bundle.get("fpp")
        rec["wall_lf_by_class"] = bundle.get("wall_lf_by_class")
        # wall thickness per class (avg, in inches) — the binding signal for
        # CMU (thin interior) vs tilt-up (thick perimeter).
        walls = bundle.get("walls") or []
        fpp = bundle.get("fpp") or 0.0
        cls_thk: dict = {}
        cls_n: dict = {}
        for w in walls:
            c = getattr(w, "thickness_class", "") or ""
            if not c:
                continue
            thk_ft = getattr(w, "thickness_pt", 0.0) * fpp
            cls_thk[c] = cls_thk.get(c, 0.0) + thk_ft
            cls_n[c] = cls_n.get(c, 0) + 1
        rec["wall_class_thickness_in"] = {
            c: round((cls_thk[c] / cls_n[c]) * 12.0, 2) for c in cls_thk
        }
        rec["wall_class_nseg"] = cls_n
        # symbol clusters — count + size + representative texts.
        groups = bundle.get("symbol_groups") or []
        rec["n_symbol_groups"] = len(groups)
        rec["symbol_groups"] = [
            {
                "id": g.candidate_id,
                "count": g.count,
                "size_ft": [round(x, 2) for x in (g.bbox_size_ft or (0, 0))],
                "texts": (g.contained_texts or [])[:6],
                "confidence": g.confidence,
                "needs_review": g.needs_review,
            }
            for g in sorted(groups, key=lambda g: -g.count)[:40]
        ]
        fp = bundle.get("footprint")
        if fp is not None:
            rec["footprint_sf"] = getattr(fp, "area_sf", None) or (
                fp.get("area_sf") if isinstance(fp, dict) else None
            )

        # Page rotation is reported because it is the difference between the
        # space these coordinates are STORED in and the space the sheet is
        # READ in — the whole subject of 23-07/SP-1, and the first thing to
        # look at when a page's numbers move.
        rec["rotation"] = getattr(page, "rotation", 0)

        # Every enclosed-region measurement, with the drawing it came off and
        # the geometry that decides what may be BILLED from it (23-RESEARCH
        # §5.1). `perimeter_lf` is traced from the same mask the area was
        # counted from; `shape_ratio` is the blind P/sqrt(A) validator (4.00 is
        # a square, the observed leaking architectural fills read 8.5-9.0); the
        # height and its SOURCE ride along because a height that did not come
        # from the drawing being measured must flag rather than multiply
        # silently.
        rec["room_fills"] = [
            {
                "id": f.candidate_id,
                "plan_name": f.plan_name,
                "plan_kind": f.plan_kind,
                "title": f.viewport_title,
                "area_sf": f.area_sf,
                "scale_fpi": f.scale_fpi,
                "perimeter_lf": f.perimeter_lf,
                "region_perimeters": list(f.region_perimeters or []),
                "region_shape_ratios": list(f.region_shape_ratios or []),
                "dominant_shape_ratio": _dominant_shape_ratio(f),
                "wall_height_ft": f.wall_height_ft,
                "wall_height_source": f.wall_height_source,
                "bound_sf": f.bound_sf,
                "extent_ratio": f.extent_ratio,
                "needs_review": f.needs_review,
                "review_reason": f.review_reason,
            }
            for f in (bundle.get("room_fills") or [])
        ]

        # Facade silhouettes (23-14). `excluded` is not a failure — a demolition
        # or interior elevation is MEASURED and then deliberately kept out of
        # new-work quantities, and the two must stay distinguishable.
        rec["elevation_areas"] = [
            {
                "id": e.candidate_id,
                "title": e.title,
                "orientation": e.orientation,
                "area_sf": e.area_sf,
                "width_ft": (e.bbox_ft or (None, None))[0],
                "height_ft": (e.bbox_ft or (None, None))[1],
                "component_count": e.component_count,
                "scale_fpi": e.scale_fpi,
                "datum_height_ft": e.datum_height_ft,
                "band_cropped": e.band_cropped,
                "is_demo": e.is_demo,
                "is_interior": e.is_interior,
                "excluded": e.excluded,
                "needs_review": e.needs_review,
                "review_reason": e.review_reason,
            }
            for e in (bundle.get("elevation_areas") or [])
        ]
        rfp = bundle.get("reference_footprint")
        if rfp is not None:
            rec["reference_footprint"] = {
                "area_sf": getattr(rfp, "area_sf", None),
                "perimeter_lf": getattr(rfp, "perimeter_lf", None),
            }

        # Open runs (23-12/23-15). Length is stored in POINTS and converted at
        # the run's OWN drawing scale, so a run with no containing callout has
        # no LF at all — flagged, never measured at a borrowed page scale.
        rec["linear_runs"] = [
            {
                "id": r.candidate_id,
                "length_pt": round(r.length_pt, 2),
                "length_lf": (
                    round(r.length_pt * r.scale_fpi / 72.0, 2)
                    if r.scale_fpi else None
                ),
                "scale_fpi": r.scale_fpi,
                "viewport_title": r.viewport_title,
                "is_typical": r.is_typical,
                "paired": r.paired,
                "mark_signature": r.mark_signature,
                "segment_count": r.segment_count,
                "needs_review": r.needs_review,
                "review_reason": r.review_reason,
            }
            for r in (bundle.get("linear_runs") or [])
        ]

        # A DELIBERATE off-scale exclusion is correct behaviour, and a client
        # must be able to tell "we correctly declined to measure four details at
        # 60x the wrong scale" from "we failed to find them" (23-03).
        rec["excluded_viewports"] = [
            {
                "region_id": d.region_id,
                "title": d.title,
                "disposition": d.disposition,
                "printed_scale_fpi": d.printed_scale_fpi,
                "reason": d.reason,
            }
            for d in (bundle.get("excluded_viewports") or [])
        ]
        rec["coverage_drops"] = [
            {
                "region_id": d.region_id,
                "title": d.title,
                "disposition": d.disposition,
                "reason": d.reason,
            }
            for d in (bundle.get("coverage_drops") or [])
        ]

        # Each viewport's OWN printed scale — the binding this plan changed.
        # A viewport with no callout of its own reports None, which is a
        # different fact from a viewport measured at a borrowed scale.
        own: dict = {}
        try:
            printed = extract_printed_scales(page) or []
            vps = bundle.get("viewports") or []
            by_region = match_scales_to_viewports(printed, vps, page=page) or {}
            for vp in vps:
                ps_own = by_region.get(vp.region_id)
                own[vp.region_id] = {
                    "kind": vp.kind,
                    "own_printed_fpi": (
                        round(ps_own.feet_per_inch, 6) if ps_own is not None else None
                    ),
                    "own_title": getattr(ps_own, "title", None),
                }
        except Exception as exc:  # noqa: BLE001 — the probe reports, never fails
            own = {"error": f"{type(exc).__name__}: {exc}"}
        rec["viewport_own_scale"] = own

        out["pages"].append(rec)
    doc.close()
    return out


def _fmt(v, nd=1):
    """A number, or the honest word for its absence — never a silent blank."""
    if v is None:
        return "n/a"
    try:
        return "%.*f" % (nd, float(v))
    except (TypeError, ValueError):
        return str(v)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pdf = args[0] if args else "uploads/Crow - Cass White Road-Plans.pdf"
    pages = None
    for a in sys.argv[1:]:
        if a.startswith("--pages="):
            pages = [int(x) for x in a.split("=", 1)[1].split(",") if x.strip()]
    result = probe(pdf, pages)
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        sys.exit(0)
    dest = ROOT / "scratch_geom_probe.json"
    dest.write_text(json.dumps(result, indent=2, default=str))
    for pg in result["pages"]:
        print(
            f"\n=== page {pg['page']} type={pg.get('sheet_type')} "
            f"rot={pg.get('rotation')} fpp={pg.get('fpp')} err={pg.get('error','')}"
        )
        if pg.get("wall_lf_by_class"):
            print("  wall_lf_by_class:", pg["wall_lf_by_class"])
            print("  wall_class_thickness_in:", pg.get("wall_class_thickness_in"))
        if pg.get("symbol_groups"):
            for g in pg["symbol_groups"][:12]:
                print(f"    {g['id']:10} count={g['count']:>4} size_ft={g['size_ft']} texts={g['texts']}")
        if pg.get("footprint_sf"):
            print("  footprint_sf:", pg["footprint_sf"])
        for f in pg.get("room_fills") or []:
            print(
                "    FILL %-8s %-34s %9.1f SF at %s ft/in%s"
                % (f["id"], f["title"], f["area_sf"], f["scale_fpi"],
                   "  [needs review]" if f["needs_review"] else "")
            )
            print(
                "         perimeter=%s LF  shape_ratio=%s  height=%s ft (%s)"
                % (
                    _fmt(f.get("perimeter_lf")),
                    _fmt(f.get("dominant_shape_ratio")),
                    _fmt(f.get("wall_height_ft")),
                    f.get("wall_height_source") or "no source",
                )
            )
        for e in pg.get("elevation_areas") or []:
            print(
                "    ELEV %-8s %-30s %9.1f SF  %s ft wide  datum=%s%s%s"
                % (e["id"], (e["title"] or "")[:30], e["area_sf"],
                   _fmt(e.get("width_ft")), _fmt(e.get("datum_height_ft")),
                   "  [EXCLUDED]" if e.get("excluded") else "",
                   "  [needs review]" if e.get("needs_review") else "")
            )
        runs = pg.get("linear_runs") or []
        if runs:
            print("    linear runs: %d  (longest first)" % len(runs))
            for r in sorted(runs, key=lambda r: -(r["length_pt"] or 0))[:8]:
                print(
                    "      RUN %-8s %10s LF at %-8s %-26s%s%s"
                    % (r["id"], _fmt(r.get("length_lf")), r.get("scale_fpi"),
                       (r.get("viewport_title") or "(no callout)")[:26],
                       "  [typical]" if r.get("is_typical") else "",
                       "  [needs review]" if r.get("needs_review") else "")
                )
        for x in pg.get("excluded_viewports") or []:
            print(
                "    EXCLUDED %-4s %-34s %s (printed %s ft/in)"
                % (x["region_id"], (x["title"] or "")[:34], x["disposition"],
                   x.get("printed_scale_fpi"))
            )
        for d in pg.get("coverage_drops") or []:
            print(
                "    DROP %-4s %-34s %s"
                % (d["region_id"], (d["title"] or "")[:34], d["disposition"])
            )
        own = pg.get("viewport_own_scale") or {}
        if isinstance(own, dict) and "error" not in own:
            for rid, v in sorted(own.items()):
                print(
                    "    %-4s kind=%-12s own_printed_fpi=%-10s %s"
                    % (rid, v["kind"], v["own_printed_fpi"],
                       (v["own_title"] or "")[:40])
                )
    print(f"\nwrote {dest}")
