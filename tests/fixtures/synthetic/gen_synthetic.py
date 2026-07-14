#!/usr/bin/env python3
"""Generate synthetic PDF dimension fixtures with known ground truth.

Usage:
    python3 tests/fixtures/synthetic/gen_synthetic.py --out tests/fixtures/synthetic
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Optional

import fitz


def _draw_dim_horizontal(
    page: fitz.Page,
    x0: float,
    y_line: float,
    length: float,
    text: str,
    *,
    text_y: Optional[float] = None,
) -> None:
    """Draw a horizontal dimension with ticks, extensions, and text."""
    x1 = x0 + length
    tick = 6.0
    ext = 10.0
    ty = text_y if text_y is not None else y_line - 12.0

    page.draw_line(fitz.Point(x0, y_line - ext), fitz.Point(x0, y_line + ext))
    page.draw_line(fitz.Point(x1, y_line - ext), fitz.Point(x1, y_line + ext))
    page.draw_line(fitz.Point(x0, y_line), fitz.Point(x1, y_line))
    page.draw_line(fitz.Point(x0, y_line), fitz.Point(x0 + tick, y_line - tick))
    page.draw_line(fitz.Point(x0, y_line), fitz.Point(x0 + tick, y_line + tick))
    page.draw_line(fitz.Point(x1, y_line), fitz.Point(x1 - tick, y_line - tick))
    page.draw_line(fitz.Point(x1, y_line), fitz.Point(x1 - tick, y_line + tick))
    page.insert_text(fitz.Point(x0 + length / 2 - 18, ty), text, fontsize=8)


def _draw_dim_vertical(
    page: fitz.Page,
    x_line: float,
    y0: float,
    length: float,
    text: str,
) -> None:
    """Draw a vertical dimension with rotated text."""
    y1 = y0 + length
    tick = 6.0
    ext = 10.0

    page.draw_line(fitz.Point(x_line - ext, y0), fitz.Point(x_line + ext, y0))
    page.draw_line(fitz.Point(x_line - ext, y1), fitz.Point(x_line + ext, y1))
    page.draw_line(fitz.Point(x_line, y0), fitz.Point(x_line, y1))
    page.draw_line(fitz.Point(x_line, y0), fitz.Point(x_line - tick, y0 + tick))
    page.draw_line(fitz.Point(x_line, y0), fitz.Point(x_line + tick, y0 + tick))
    page.draw_line(fitz.Point(x_line, y1), fitz.Point(x_line - tick, y1 - tick))
    page.draw_line(fitz.Point(x_line, y1), fitz.Point(x_line + tick, y1 - tick))
    page.insert_text(
        fitz.Point(x_line + 8, y0 + length / 2 - 4),
        text,
        fontsize=8,
        rotate=90,
    )


def generate_dimensions_page() -> tuple[fitz.Document, list[dict]]:
    """Build one page with several known dimension associations."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    truth: list[dict] = []

    _draw_dim_horizontal(page, 80, 120, 200, "50'-0\"")
    truth.append({"text": "50'-0\"", "feet": 50.0, "expected_associated": True})

    _draw_dim_vertical(page, 400, 80, 150, "40'-0\"")
    truth.append({"text": "40'-0\"", "feet": 40.0, "expected_associated": True})

    _draw_dim_horizontal(page, 80, 260, 120, "12'-6 1/2\"")
    truth.append({"text": "12'-6 1/2\"", "feet": 12.541666666666666, "expected_associated": True})

    chain_y = 380.0
    x = 80.0
    bays = [("20'-0\"", 20.0, 80.0), ("30'-0\"", 30.0, 80.0), ("25'-0\"", 25.0, 80.0)]
    for text, feet, span in bays:
        _draw_dim_horizontal(page, x, chain_y, span, text, text_y=chain_y - 14)
        truth.append({"text": text, "feet": feet, "expected_associated": True})
        x += span

    page.insert_text(fitz.Point(80, 520), "NOTE 36'-0\" TYP", fontsize=8)
    truth.append({"text": "NOTE 36'-0\" TYP", "feet": 36.0, "expected_associated": False})

    return doc, truth


# ── Symbol clustering fixtures (Recipe D, 21-06) ─────────────────────────────

# Asymmetric 4-segment polyline (open "flag") — asymmetry makes rotation and
# mirror invariance non-trivial, so the dihedral min-hash is actually proven.
_SYMBOL_PTS = [(0.0, 0.0), (20.0, 0.0), (20.0, 12.0), (8.0, 12.0), (8.0, 4.0)]
_SYMBOL_CENTER = (10.0, 6.0)


def _draw_symbol(page: fitz.Page, ox: float, oy: float, transform: Optional[str] = None) -> None:
    """Draw the 4-segment test symbol centered at (ox, oy), optionally transformed."""
    cx, cy = _SYMBOL_CENTER
    pts = []
    for x, y in _SYMBOL_PTS:
        dx, dy = x - cx, y - cy
        if transform == "rot90":
            dx, dy = -dy, dx
        elif transform == "rot180":
            dx, dy = -dx, -dy
        elif transform == "rot270":
            dx, dy = dy, -dx
        elif transform == "mirror":
            dx = -dx
        pts.append((ox + dx, oy + dy))
    for a, b in zip(pts, pts[1:]):
        page.draw_line(fitz.Point(*a), fitz.Point(*b))


def generate_symbols_page() -> tuple[fitz.Document, dict]:
    """Build one page with known symbol-group ground truth (Recipe D).

    Content:
      * 12 identical 4-segment symbols — 7 plain, 3 rotated (90/180/270),
        2 mirrored → ONE group of 12 (rotation/mirror invariance).
      * 5 identical circles → ONE group of 5.
      * A 20-stroke 45-degree hatch field (2.83 pt spacing) → collapsed, no group.
      * One unique triangle → excluded by the count >= 3 filter.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    transforms = [None] * 7 + ["rot90", "rot180", "rot270", "mirror", "mirror"]
    positions = [(90.0 + (i % 4) * 60.0, 90.0 + (i // 4) * 60.0) for i in range(12)]
    for (ox, oy), transform in zip(positions, transforms):
        _draw_symbol(page, ox, oy, transform)

    for i in range(5):
        page.draw_circle(fitz.Point(100.0 + i * 60.0, 320.0), 8.0)

    hatch_strokes = 20
    for i in range(hatch_strokes):
        x = 80.0 + i * 4.0
        page.draw_line(fitz.Point(x, 420.0), fitz.Point(x + 30.0, 450.0))

    page.draw_line(fitz.Point(450.0, 540.0), fitz.Point(480.0, 540.0))
    page.draw_line(fitz.Point(480.0, 540.0), fitz.Point(465.0, 510.0))
    page.draw_line(fitz.Point(465.0, 510.0), fitz.Point(450.0, 540.0))

    truth = {
        "pdf": "symbols_synthetic.pdf",
        "fpp": 0.1,
        "expected_groups": [
            {"count": 12, "shape": "4-segment flag (7 plain, 3 rotated, 2 mirrored)"},
            {"count": 5, "shape": "circle r=8pt"},
        ],
        "hatch_strokes": hatch_strokes,
        "unique_shapes": 1,
    }
    return doc, truth


# ── Floor-plan fixture (Recipes B & C, 21-10) ────────────────────────────────

# Truth scale: 0.1 ft per point (1 pt = 0.1 ft).
_FP_FPP = 0.1
# Wall thicknesses in points: exterior 8" (0.6667 ft), interior 6" (0.5 ft).
_FP_EXT_TH = 8.0 / 12.0 / _FP_FPP     # 6.6667 pt
_FP_INT_TH = 6.0 / 12.0 / _FP_FPP     # 5.0 pt
# Centerline rectangle of the exterior walls (80 ft x 60 ft).
_FP_X0, _FP_X1 = 100.0, 900.0
_FP_Y0, _FP_Y1 = 100.0, 700.0
# Interior wall centerlines (asymmetric quadrants).
_FP_XV = 550.0    # vertical interior wall
_FP_YH = 450.0    # horizontal interior wall
# Two 3'-0" door gaps (30 pt).
_FP_DOOR_V = (560.0, 590.0)   # in the vertical wall (y-range)
_FP_DOOR_H = (700.0, 730.0)   # in the horizontal wall (x-range)
# Curved wall: concentric quarter arcs (island in the OFFICE room).
_FP_ARC_CENTER = (200.0, 200.0)
_FP_ARC_R_IN, _FP_ARC_R_OUT = 55.0, 60.0
_BEZIER_K = 0.5522847498307936


def generate_floorplan_page() -> tuple[fitz.Document, dict]:
    """Build one floor-plan page with known wall/room/footprint ground truth.

    Content (all lengths deterministic at fpp = 0.1 ft/pt):
      * Exterior walls: 8" thick — outer/inner boundary rectangles drawn as
        line pairs around the 80 ft x 60 ft centerline rectangle.
      * Interior walls: 6" thick — one vertical + one horizontal line pair,
        each broken by a 3'-0" door gap on BOTH faces.
      * One curved wall: concentric quarter arcs (6" apart) as an island —
        proves Bezier flattening + constant-offset arc pairing (Pitfall 6).
      * A 20-stroke 45-degree hatch field in the STORAGE room — must collapse
        (Pitfall 2), never become a wall class.
      * Four room labels + overall dimension strings 80'-8" / 60'-8"
        (outer-face extents) for the footprint cross-check.
    """
    doc = fitz.open()
    page = doc.new_page(width=1000, height=800)

    ho = _FP_EXT_TH / 2.0
    hi = _FP_INT_TH / 2.0

    def _line(x0: float, y0: float, x1: float, y1: float) -> None:
        page.draw_line(fitz.Point(x0, y0), fitz.Point(x1, y1))

    # Exterior walls: outer + inner face rectangles (line pairs).
    xo0, xo1 = _FP_X0 - ho, _FP_X1 + ho
    yo0, yo1 = _FP_Y0 - ho, _FP_Y1 + ho
    xi0, xi1 = _FP_X0 + ho, _FP_X1 - ho
    yi0, yi1 = _FP_Y0 + ho, _FP_Y1 - ho
    _line(xo0, yo0, xo1, yo0)
    _line(xo1, yo0, xo1, yo1)
    _line(xo1, yo1, xo0, yo1)
    _line(xo0, yo1, xo0, yo0)
    _line(xi0, yi0, xi1, yi0)
    _line(xi1, yi0, xi1, yi1)
    _line(xi1, yi1, xi0, yi1)
    _line(xi0, yi1, xi0, yi0)

    # Interior vertical wall (6"), door gap on both faces.
    for x in (_FP_XV - hi, _FP_XV + hi):
        _line(x, yi0, x, _FP_DOOR_V[0])
        _line(x, _FP_DOOR_V[1], x, yi1)
    # Interior horizontal wall (6"), door gap on both faces.
    for y in (_FP_YH - hi, _FP_YH + hi):
        _line(xi0, y, _FP_DOOR_H[0], y)
        _line(_FP_DOOR_H[1], y, xi1, y)

    # Curved wall: concentric quarter arcs (0° → 90°), 6" apart.
    cx, cy = _FP_ARC_CENTER
    for radius in (_FP_ARC_R_IN, _FP_ARC_R_OUT):
        k = _BEZIER_K * radius
        page.draw_bezier(
            fitz.Point(cx + radius, cy),
            fitz.Point(cx + radius, cy + k),
            fitz.Point(cx + k, cy + radius),
            fitz.Point(cx, cy + radius),
        )

    # Hatch field in STORAGE (2.83 pt perpendicular spacing at 45°) — the
    # stroke spacing sits inside the wall-thickness window, so an uncollapsed
    # field WOULD pair into bogus walls (the test asserts it does not).
    hatch_strokes = 20
    for i in range(hatch_strokes):
        x = 600.0 + i * 4.0
        _line(x, 150.0, x + 30.0, 180.0)

    # Room labels (word centers inside their faces).
    page.insert_text(fitz.Point(300, 300), "OFFICE", fontsize=10)
    page.insert_text(fitz.Point(700, 300), "STORAGE", fontsize=10)
    page.insert_text(fitz.Point(300, 600), "LOBBY", fontsize=10)
    page.insert_text(fitz.Point(700, 600), "BREAK", fontsize=10)

    # Overall dimension strings — outer-face extents (80'-8" x 60'-8") for
    # the footprint_takeoff cross-check.
    page.insert_text(fitz.Point(480, 60), "80'-8\"", fontsize=10)
    page.insert_text(fitz.Point(960, 400), "60'-8\"", fontsize=10, rotate=90)

    # ── Ground truth (all real-feet at fpp = 0.1) ────────────────────────────
    ext_lf = 2.0 * ((xi1 - xi0) + (yi1 - yi0)) * _FP_FPP
    int_v_lf = (
        (_FP_DOOR_V[0] - yi0) + (yi1 - _FP_DOOR_V[1])
    ) * _FP_FPP
    int_h_lf = (
        (_FP_DOOR_H[0] - xi0) + (xi1 - _FP_DOOR_H[1])
    ) * _FP_FPP
    arc_lf = (
        math.pi / 2.0 * ((_FP_ARC_R_IN + _FP_ARC_R_OUT) / 2.0) * _FP_FPP
    )
    room_areas = {
        "OFFICE": (_FP_XV - _FP_X0) * (_FP_YH - _FP_Y0) * _FP_FPP * _FP_FPP,
        "STORAGE": (_FP_X1 - _FP_XV) * (_FP_YH - _FP_Y0) * _FP_FPP * _FP_FPP,
        "LOBBY": (_FP_XV - _FP_X0) * (_FP_Y1 - _FP_YH) * _FP_FPP * _FP_FPP,
        "BREAK": (_FP_X1 - _FP_XV) * (_FP_Y1 - _FP_YH) * _FP_FPP * _FP_FPP,
    }
    footprint_sf = (
        (xo1 - xo0) * (yo1 - yo0) * _FP_FPP * _FP_FPP
    )

    truth = {
        "pdf": "floorplan_synthetic.pdf",
        "fpp": _FP_FPP,
        "wall_lf_by_thickness_in": {
            "8.0": round(ext_lf, 3),
            "6.0": round(int_v_lf + int_h_lf + arc_lf, 3),
        },
        "curve_wall_lf": round(arc_lf, 3),
        "opening_widths_ft": [3.0, 3.0],
        "room_areas_sf": {k: round(v, 2) for k, v in room_areas.items()},
        "room_count": 4,
        "footprint_sf": round(footprint_sf, 2),
        "footprint_dims_text": ["80'-8\"", "60'-8\""],
        "hatch_strokes": hatch_strokes,
    }
    return doc, truth


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/fixtures/synthetic"),
        help="Output directory for generated PDFs and truth.json",
    )
    args = parser.parse_args()
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    doc, truth = generate_dimensions_page()
    pdf_path = out_dir / "dimensions_synthetic.pdf"
    truth_path = out_dir / "truth.json"

    doc.save(pdf_path)
    doc.close()

    sym_doc, sym_truth = generate_symbols_page()
    sym_pdf_path = out_dir / "symbols_synthetic.pdf"
    sym_doc.save(sym_pdf_path)
    sym_doc.close()

    fp_doc, fp_truth = generate_floorplan_page()
    fp_pdf_path = out_dir / "floorplan_synthetic.pdf"
    fp_doc.save(fp_pdf_path)
    fp_doc.close()

    payload = {
        "pages": [{"page": 0, "dims": truth}],
        "symbols": sym_truth,
        "floorplan": fp_truth,
    }
    truth_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {pdf_path}, {sym_pdf_path}, {fp_pdf_path} and {truth_path}")


if __name__ == "__main__":
    main()
