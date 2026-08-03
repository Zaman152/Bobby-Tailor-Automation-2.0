#!/usr/bin/env python3
"""Offline deterministic-geometry probe (ZERO API cost).

Runs ONLY the pure-geometry deterministic bundle (walls / wall-classes / symbol
clusters / footprint / keynote text) on a plans PDF, page by page, and dumps the
raw geometry the fusion layer would bind names to. This is the free iteration
loop for making the CMU/Columns/Bollards/Tilt-up bindings DETERMINISTIC instead
of vision-dependent (see docs/PIPELINE-GROUND-TRUTH.md §5, memory
crow-manifest-free-baseline "make those bindings deterministic").

Per page it reports the resolved feet-per-point, the room fills with their plan
names and kinds, and each viewport's OWN printed scale — the three facts a
scale/geometry change has to be diffed on. Later plans add more fields here
(23-RESEARCH §5.1), so every field is emitted from one flat per-page record
that is cheap to extend and cheap to diff.

Usage:
    python3 scripts/geom_probe.py "uploads/Crow - Cass White Road-Plans.pdf"
    python3 scripts/geom_probe.py <pdf> --json     # machine-diffable, stdout
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


def probe(pdf_path: str) -> dict:
    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})  # analyzer never called
    doc = fitz.open(pdf_path)
    out = {"pdf": pdf_path, "pages": []}
    for i in range(doc.page_count):
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

        # Every enclosed-region measurement, with the drawing it came off.
        rec["room_fills"] = [
            {
                "id": f.candidate_id,
                "plan_name": f.plan_name,
                "plan_kind": f.plan_kind,
                "title": f.viewport_title,
                "area_sf": f.area_sf,
                "scale_fpi": f.scale_fpi,
                "needs_review": f.needs_review,
            }
            for f in (bundle.get("room_fills") or [])
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


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pdf = args[0] if args else "uploads/Crow - Cass White Road-Plans.pdf"
    result = probe(pdf)
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
        own = pg.get("viewport_own_scale") or {}
        if isinstance(own, dict) and "error" not in own:
            for rid, v in sorted(own.items()):
                print(
                    "    %-4s kind=%-12s own_printed_fpi=%-10s %s"
                    % (rid, v["kind"], v["own_printed_fpi"],
                       (v["own_title"] or "")[:40])
                )
    print(f"\nwrote {dest}")
