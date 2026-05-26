"""
Process a PDF floor plan directly — no browser needed.
Converts each page to image, sends to Claude for vision extraction.
"""
import fitz
import re
import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from claude_analyzer import analyze_drawing
from calculator import apply_estimation_tables
from reporter import generate_report
from config import SCREENSHOTS_DIR

logger = logging.getLogger(__name__)


def _page_to_image(pdf_path: str, page_num: int, out_dir: str, zoom: float = 2.0) -> str:
    doc = fitz.open(pdf_path)
    pix = doc[page_num].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    out = os.path.join(out_dir, f"page_{page_num+1:03d}.png")
    pix.save(out)
    doc.close()
    return out


def _sheet_name_from_doc(doc: fitz.Document, page_num: int) -> str:
    text = doc[page_num].get_text()
    for pat in [r'\b([A-Z]\d{3})\b', r'\b([A-Z]\d+\.\d+)\b']:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return f"Page_{page_num + 1}"


def _sheet_name(pdf_path: str, page_num: int) -> str:
    doc = fitz.open(pdf_path)
    try:
        return _sheet_name_from_doc(doc, page_num)
    finally:
        doc.close()


def get_pdf_metadata(pdf_path: str) -> dict:
    """Extract page count, file size, and sheet names without rendering."""
    doc = fitz.open(pdf_path)
    try:
        pages = []
        for i in range(len(doc)):
            pages.append({
                "page_num": i + 1,
                "sheet_name": _sheet_name_from_doc(doc, i),
            })
        return {
            "page_count": len(doc),
            "file_size_bytes": os.path.getsize(pdf_path),
            "pages": pages,
        }
    finally:
        doc.close()


def run_pdf_analysis(
    pdf_path: str,
    project_name: str = "PDF Project",
    selected_pages: Optional[list[int]] = None,
    progress_callback=None,
) -> dict:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = project_name.replace(" ", "_").replace("/", "-")
    img_dir = Path(SCREENSHOTS_DIR) / f"{safe}_{ts}"
    img_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    if selected_pages:
        pages_to_process = sorted({
            p - 1 for p in selected_pages
            if isinstance(p, int) and 1 <= p <= total_pages
        })
    else:
        pages_to_process = list(range(total_pages))

    if not pages_to_process:
        raise ValueError("No valid pages selected for analysis")

    total = len(pages_to_process)
    logger.info(f"Processing PDF ({total} of {total_pages} pages): {pdf_path}")

    all_extracted = []
    all_estimates = []

    for idx, i in enumerate(pages_to_process):
        sheet = _sheet_name(pdf_path, i)
        logger.info(f"[{idx + 1}/{total}] {sheet}")

        if progress_callback:
            progress_callback(idx + 1, total, sheet, phase="converting")

        img_path = _page_to_image(pdf_path, i, str(img_dir))

        if progress_callback:
            progress_callback(idx + 1, total, sheet, phase="analyzing")

        extracted = analyze_drawing(img_path, sheet)
        extracted["_page_num"] = i + 1
        all_extracted.append(extracted)

        if "error" not in extracted:
            extraction_counts = {
                "measurements": len(extracted.get("measurements", [])),
                "components": len(extracted.get("components", [])),
                "rooms": len(extracted.get("rooms", [])),
                "schedules": len(extracted.get("schedules", [])),
            }
            if progress_callback:
                progress_callback(
                    idx + 1, total, sheet,
                    phase="complete", extraction=extraction_counts,
                )
            all_estimates.extend(apply_estimation_tables(extracted))

    return generate_report(project_name, all_extracted, all_estimates)
