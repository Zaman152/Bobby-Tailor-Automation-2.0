#!/usr/bin/env python3
"""Offline fusion-binding probe (ZERO API).

Feeds a REAL page's geometry into the deterministic binding predicates so we can
see exactly what `_is_regular_grid` / `deterministic_symbol_name` /
`_library_symbol_bindings` / the perimeter ring produce, and — since phase 23 —
which **basis binder** each measured primitive would route through. That is the
free iteration loop for making the bindings deterministic (memory
crow-manifest-free-baseline).

The PDF and the page are ARGUMENTS. They used to be two module constants
hardcoded to Crow page 1, which meant the new basis binders (`wall_area` from a
room fill or a facade silhouette, `linear` from an open run) could not be
exercised against any other saved bundle — the probe could only ever ask its
question of one sheet in one drafting office.

Usage:
    python3 scripts/fusion_probe.py                              # Crow page 1
    python3 scripts/fusion_probe.py <pdf> <page>
    python3 scripts/fusion_probe.py <pdf> <page> --type elevation
    python3 scripts/fusion_probe.py <pdf> <page> --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import fitz  # noqa: E402

from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline  # noqa: E402
from bobbytailor.vision import fusion as F  # noqa: E402

DEFAULT_PDF = "uploads/Crow - Cass White Road-Plans.pdf"
DEFAULT_PAGE = 1


def probe(pdf_path: str, page_index: int, sheet_type: str = "floor_plan") -> dict:
    """Run the deterministic bundle for ONE page and report what would bind."""
    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})  # analyzer never called
    doc = fitz.open(pdf_path)
    try:
        if not 0 <= page_index < doc.page_count:
            raise SystemExit(
                "page %d is outside %s (%d pages)"
                % (page_index, pdf_path, doc.page_count)
            )
        page = doc[page_index]
        bundle = pipe._deterministic_bundle(
            page, doc, pdf_path, page_index, "page%d" % page_index, sheet_type
        )
        out = {
            "pdf": pdf_path,
            "page": page_index,
            "sheet_type": sheet_type,
            "fpp": bundle.get("fpp"),
            "registered_bases": sorted(F.BASIS_BINDERS),
        }

        groups = bundle.get("symbol_groups") or []
        out["symbol_groups"] = []
        for g in sorted(groups, key=lambda g: -g.count)[:20]:
            cents = F._instance_centroids(g)
            out["symbol_groups"].append({
                "id": g.candidate_id,
                "count": g.count,
                "size_ft": [round(x, 2) for x in (g.bbox_size_ft or (0, 0))],
                "is_regular_grid": F._is_regular_grid(cents, g),
                "is_small_marker": F._is_small_marker(g),
                "size_uniform": F._size_uniform(g),
                "is_perimeter_ring": F._is_perimeter_ring(g),
                "deterministic_name": F.deterministic_symbol_name(g),
            })

        lf = bundle.get("wall_lf_by_class") or {}
        walls = bundle.get("walls") or []
        fpp = bundle.get("fpp") or 0.0
        thk: dict = {}
        n: dict = {}
        for w in walls:
            c = w.thickness_class or ""
            if not c:
                continue
            thk[c] = thk.get(c, 0.0) + w.thickness_pt * fpp
            n[c] = n.get(c, 0) + 1
        out["wall_classes"] = [
            {
                "class": c,
                "lf": round(lf[c], 1),
                "thickness_in": round((thk[c] / n[c]) * 12, 2) if n.get(c) else None,
                "nseg": n.get(c),
            }
            for c in sorted(lf, key=lambda c: -lf[c])
        ]

        fp = bundle.get("footprint")
        out["footprint"] = None if fp is None else {
            "area_sf": getattr(fp, "area_sf", None),
            "perimeter_lf": getattr(fp, "perimeter_lf", None),
        }

        # The phase-23 primitives, and the basis each would bind through. A
        # primitive with no registered binder is the defect SP-9 exists to make
        # visible — `basis: linear` sat with no consumer at all for a whole
        # release.
        out["room_fills"] = [
            {
                "id": f.candidate_id, "plan_name": f.plan_name,
                "plan_kind": f.plan_kind, "area_sf": f.area_sf,
                "perimeter_lf": f.perimeter_lf,
                "wall_height_ft": f.wall_height_ft,
                "wall_height_source": f.wall_height_source,
                "needs_review": f.needs_review,
            }
            for f in (bundle.get("room_fills") or [])
        ]
        out["elevation_areas"] = [
            {
                "id": e.candidate_id, "title": e.title, "area_sf": e.area_sf,
                "excluded": e.excluded, "needs_review": e.needs_review,
                "materials": [m.get("material") for m in (e.materials or [])],
            }
            for e in (bundle.get("elevation_areas") or [])
        ]
        out["linear_runs"] = [
            {
                "id": r.candidate_id,
                "length_lf": (
                    round(r.length_pt * r.scale_fpi / 72.0, 2)
                    if r.scale_fpi else None
                ),
                "scale_fpi": r.scale_fpi,
                "viewport_title": r.viewport_title,
                "is_typical": r.is_typical,
                "needs_review": r.needs_review,
            }
            for r in (bundle.get("linear_runs") or [])
        ]
        out["sheet_linear_phrases"] = list(bundle.get("sheet_linear_phrases") or [])
        out["material_tags"] = len(bundle.get("material_tags") or [])
        out["excluded_viewports"] = len(bundle.get("excluded_viewports") or [])
        out["coverage_drops"] = len(bundle.get("coverage_drops") or [])
        return out
    finally:
        doc.close()


def _render(out: dict) -> None:
    print("%s  page %s  type=%s  fpp=%s"
          % (out["pdf"], out["page"], out["sheet_type"], out["fpp"]))
    print("registered measure bases:", ", ".join(out["registered_bases"]))

    print("\n=== per-group deterministic predicates ===")
    print("%-8s%6s%16s  %-5s %-6s %-7s %-5s %s"
          % ("id", "count", "size_ft", "grid?", "marker?", "uniform?", "perim?",
             "det_name"))
    for g in out["symbol_groups"]:
        print("%-8s%6d%16s  %-5s %-6s %-7s %-5s %s"
              % (g["id"], g["count"], str(tuple(g["size_ft"])),
                 g["is_regular_grid"], g["is_small_marker"], g["size_uniform"],
                 g["is_perimeter_ring"], g["deterministic_name"]))

    if out["wall_classes"]:
        print("\n=== wall classes: LF + thickness(in) ===")
        for c in out["wall_classes"]:
            print("  %-6s LF=%8.1f  thick=%5sin  nseg=%s"
                  % (c["class"], c["lf"], c["thickness_in"], c["nseg"]))

    if out["footprint"]:
        print("\nfootprint area_sf=%s perimeter_lf=%s"
              % (out["footprint"]["area_sf"], out["footprint"]["perimeter_lf"]))

    for key, label in (("room_fills", "room fills (-> ceiling_area / wall_area)"),
                       ("elevation_areas", "elevation areas (-> wall_area)"),
                       ("linear_runs", "linear runs (-> linear)")):
        rows = out[key]
        print("\n=== %s: %d ===" % (label, len(rows)))
        for r in rows[:12]:
            print("  " + json.dumps(r, default=str))
    if out["sheet_linear_phrases"]:
        print("\nsheet linear phrases:", out["sheet_linear_phrases"])
    print("\nmaterial_tags=%d  excluded_viewports=%d  coverage_drops=%d"
          % (out["material_tags"], out["excluded_viewports"],
             out["coverage_drops"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", nargs="?", default=DEFAULT_PDF)
    ap.add_argument("page", nargs="?", type=int, default=DEFAULT_PAGE)
    ap.add_argument("--type", dest="sheet_type", default="floor_plan",
                    help="sheet type to route as (floor_plan, elevation, ...)")
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args()
    result = probe(ns.pdf, ns.page, ns.sheet_type)
    if ns.json:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        _render(result)
