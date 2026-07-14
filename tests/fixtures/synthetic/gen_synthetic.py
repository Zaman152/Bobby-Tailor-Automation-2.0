#!/usr/bin/env python3
"""Generate synthetic PDF dimension fixtures with known ground truth.

Usage:
    python3 tests/fixtures/synthetic/gen_synthetic.py --out tests/fixtures/synthetic
"""
from __future__ import annotations

import argparse
import json
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

    payload = {
        "pages": [{"page": 0, "dims": truth}],
        "symbols": sym_truth,
    }
    truth_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {pdf_path}, {sym_pdf_path} and {truth_path}")


if __name__ == "__main__":
    main()
