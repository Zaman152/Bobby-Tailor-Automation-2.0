#!/usr/bin/env python3
"""Offline deterministic-geometry probe (ZERO API cost).

Runs ONLY the pure-geometry deterministic bundle (walls / wall-classes / symbol
clusters / footprint / keynote text) on a plans PDF, page by page, and dumps the
raw geometry the fusion layer would bind names to. This is the free iteration
loop for making the CMU/Columns/Bollards/Tilt-up bindings DETERMINISTIC instead
of vision-dependent (see docs/PIPELINE-GROUND-TRUTH.md §5, memory
crow-manifest-free-baseline "make those bindings deterministic").

Usage:
    python3 scripts/geom_probe.py "uploads/Crow - Cass White Road-Plans.pdf"
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
        out["pages"].append(rec)
    doc.close()
    return out


if __name__ == "__main__":
    pdf = sys.argv[1] if len(sys.argv) > 1 else "uploads/Crow - Cass White Road-Plans.pdf"
    result = probe(pdf)
    dest = ROOT / "scratch_geom_probe.json"
    dest.write_text(json.dumps(result, indent=2, default=str))
    for pg in result["pages"]:
        print(f"\n=== page {pg['page']} type={pg.get('sheet_type')} fpp={pg.get('fpp')} err={pg.get('error','')}")
        if pg.get("wall_lf_by_class"):
            print("  wall_lf_by_class:", pg["wall_lf_by_class"])
            print("  wall_class_thickness_in:", pg.get("wall_class_thickness_in"))
        if pg.get("symbol_groups"):
            for g in pg["symbol_groups"][:12]:
                print(f"    {g['id']:10} count={g['count']:>4} size_ft={g['size_ft']} texts={g['texts']}")
        if pg.get("footprint_sf"):
            print("  footprint_sf:", pg["footprint_sf"])
    print(f"\nwrote {dest}")
