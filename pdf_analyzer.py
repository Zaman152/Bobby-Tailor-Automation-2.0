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


def _sheet_name(pdf_path: str, page_num: int) -> str:
    doc = fitz.open(pdf_path)
    text = doc[page_num].get_text()
    doc.close()
    for pat in [r'\b([A-Z]\d{3})\b', r'\b([A-Z]\d+\.\d+)\b']:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return f"Page_{page_num+1}"


def run_pdf_analysis(pdf_path: str, project_name: str = "PDF Project",
                     progress_callback=None) -> dict:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = project_name.replace(" ", "_").replace("/", "-")
    img_dir = Path(SCREENSHOTS_DIR) / f"{safe}_{ts}"
    img_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    total = len(doc)
    doc.close()
    logger.info(f"Processing PDF ({total} pages): {pdf_path}")

    all_extracted = []
    all_estimates = []

    for i in range(total):
        sheet = _sheet_name(pdf_path, i)
        logger.info(f"[{i+1}/{total}] {sheet}")
        if progress_callback:
            progress_callback(i + 1, total, sheet)

        img_path = _page_to_image(pdf_path, i, str(img_dir))
        extracted = analyze_drawing(img_path, sheet)
        extracted["_page_num"] = i + 1
        all_extracted.append(extracted)

        if "error" not in extracted:
            all_estimates.extend(apply_estimation_tables(extracted))

    return generate_report(project_name, all_extracted, all_estimates)
