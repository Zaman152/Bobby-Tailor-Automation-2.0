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

    payload = {"pages": [{"page": 0, "dims": truth}]}
    truth_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {pdf_path} and {truth_path}")


if __name__ == "__main__":
    main()
