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
from calculator import resolve_spec_lookups
from cross_references import resolve_cross_references
from reporter import generate_report
from takeoff_pipeline import TakeoffPipeline
from page_text_enrichment import enrich_components_from_page_text
from companion_takeoff import find_companion_takeoff_pdf, extract_legend_schedules
from config import SCREENSHOTS_DIR

logger = logging.getLogger(__name__)

# Anthropic vision limit: longest image side must be ≤ 8000 px
_MAX_IMAGE_LONG_SIDE_PX = 7900


def _effective_render_scale(page: fitz.Page, scale: float) -> float:
    """Clamp *scale* so rendered PNG longest side stays within API limits."""
    longest = max(page.rect.width, page.rect.height)
    if longest <= 0:
        return scale
    return min(scale, _MAX_IMAGE_LONG_SIDE_PX / longest)

# Generic noise patterns for building-code / standard references that can
# produce alphanumeric tokens matching sheet-ID regexes.  Adding a new
# standards body never requires touching _sheet_name_from_doc.
SHEET_ID_NOISE_PATTERNS: list[str] = [
    r"ASTM\s+[A-Z]\d+[\.\d]*",   # ASTM A36, ASTM E283, ASTM C90
    r"NFPA\s+\d+",                # NFPA 13, NFPA 72
    r"UL\s+\d+",                  # UL 300, UL 924
    r"IBC\s+\d{4}",               # IBC 2021
    r"ADA\s+\d+\.\d+",            # ADA 4.1.3
    r"ANSI\s+[A-Z]\d+",           # ANSI A117.1
    r"ASCE\s+\d+",                # ASCE 7-22
    r"AWC\s+NDS",                 # AWC NDS
    r"\d{1,2}/\d{1,2}",           # fractional annotations: 3/4, 1/2
]

# Sheet-ID candidate patterns in priority order (most-specific first).
# Covers: A4.0, S1.2, M3.1, G0.1, C-4, A-101, A101
_SHEET_ID_CANDIDATE_PATTERNS: list[str] = [
    r"[A-Z]\d+\.\d+",   # decimal form: A4.0, S1.2, M3.1
    r"[A-Z]-\d+",        # hyphenated form: A-101, C-4
    r"[A-Z]\d{3}",       # three-digit form: A101, S120
]


def _is_noise_sheet_candidate(candidate: str, page_text: str) -> bool:
    """Return True if *candidate* is part of a standards/code reference in *page_text*.

    Searches page_text for every noise pattern; if the candidate string appears
    inside any matched phrase it is classified as noise (e.g. "E283" inside
    "ASTM E283").
    """
    for pat in SHEET_ID_NOISE_PATTERNS:
        for match in re.finditer(pat, page_text, re.IGNORECASE):
            if candidate in match.group(0):
                return True
    return False


def _page_to_image(pdf_path: str, page_num: int, output_dir: str, scale: float = 2.5) -> str:
    """Render a single PDF page to a PNG (default 2.5×, clamped to API max dimensions).

    Args:
        pdf_path:   Path to the PDF file.
        page_num:   0-based page index.
        output_dir: Directory to save the image.

    Returns:
        Absolute path to the saved PNG file.
    """
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_num]
        scale = _effective_render_scale(page, scale)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        img_path = str(Path(output_dir) / f"page_{page_num + 1:04d}.png")
        pix.save(img_path)
        return img_path
    finally:
        doc.close()


def get_title_block_text(doc: fitz.Document, page_num: int) -> str:
    """Return the raw text of the title-block region (bottom-right quadrant).

    Construction drawings per ANSI/ASME Y14.1 place the title block in the
    bottom-right ~20 % (height) × 45 % (width) of the sheet.  Using
    word-level bounding boxes avoids merging text from unrelated regions.
    """
    page = doc[page_num]
    words = page.get_text("words")   # (x0, y0, x1, y1, word, ...)
    height = page.rect.height
    width = page.rect.width
    title_block_words = [
        w[4] for w in words
        if w[1] > height * 0.80 and w[0] > width * 0.55
    ]
    return " ".join(title_block_words)


def _sheet_name_from_doc(doc: fitz.Document, page_num: int) -> str:
    """Extract sheet ID from title-block region; fall back to full-page scan.

    Priority search order: decimal (A4.0) → hyphenated (A-101, C-4) →
    three-digit (A101).  Noise rejection via SHEET_ID_NOISE_PATTERNS is
    applied in both the title-block pass and the full-page fallback so that
    standards references like "ASTM E283" are never returned as a sheet ID
    regardless of where they appear on the page.
    """
    title_block_text = get_title_block_text(doc, page_num)

    # Primary: title-block region — apply noise filter using title-block context
    for pat in _SHEET_ID_CANDIDATE_PATTERNS:
        for m in re.finditer(r"\b(" + pat + r")\b", title_block_text):
            candidate = m.group(1)
            if not _is_noise_sheet_candidate(candidate, title_block_text):
                return candidate

    # Fallback: full-page scan with noise rejection against full-page context
    full_text = doc[page_num].get_text()
    for pat in _SHEET_ID_CANDIDATE_PATTERNS:
        for m in re.finditer(r"\b(" + pat + r")\b", full_text):
            candidate = m.group(1)
            if not _is_noise_sheet_candidate(candidate, full_text):
                return candidate

    return f"Page_{page_num + 1}"


def _sheet_name(pdf_path: str, page_num: int) -> str:
    doc = fitz.open(pdf_path)
    try:
        return _sheet_name_from_doc(doc, page_num)
    finally:
        doc.close()


def get_pdf_metadata(pdf_path: str) -> dict:
    """Extract page count, file size, sheet names, and optional type hints."""
    # Optional sheet-type classifier from Phase 20-00; skip gracefully if absent
    try:
        from sheet_pass_matrix import classify_sheet_type_from_text  # type: ignore
        _classify = classify_sheet_type_from_text
    except ImportError:
        _classify = None

    doc = fitz.open(pdf_path)
    try:
        pages = []
        for i in range(len(doc)):
            sheet_name = _sheet_name_from_doc(doc, i)
            entry: dict = {
                "page_num": i + 1,
                "sheet_name": sheet_name,
            }
            if _classify is not None:
                tb_text = get_title_block_text(doc, i)
                entry["sheet_type_hint"] = _classify(tb_text or doc[i].get_text())
            pages.append(entry)
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
    manifest_path: Optional[str] = None,
    scale_feet_per_inch: Optional[float] = None,
) -> dict:
    """Run multi-pass extraction on a PDF via TakeoffPipeline.

    Pass 1 converts each page to an image (emits "converting" progress).
    Pass 2 delegates to TakeoffPipeline.run_project which handles:
      - sheet-type classification per page (from title-block text)
      - title_sheet skip (zero API calls)
      - count + measure + schedule passes as appropriate
      - QuantityVerifier sanity check
      - project_type detection once across all sheets
      - apply_estimation_tables with uniform project_type

    The return value and downstream resolve/report calls are unchanged so
    app.py's _pdf_job requires no modification.
    """
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

    # ----------------------------------------------------------------
    # Pass 1 — Convert PDF pages to images
    # ----------------------------------------------------------------
    doc = fitz.open(pdf_path)
    pipeline_pages: list[dict] = []
    try:
        for idx, i in enumerate(pages_to_process):
            sheet = _sheet_name_from_doc(doc, i)
            title_block_text = get_title_block_text(doc, i)

            logger.info(f"[{idx + 1}/{total}] Converting {sheet} (page {i + 1})")
            if progress_callback:
                progress_callback(idx + 1, total, sheet, phase="converting")

            img_path = _page_to_image(pdf_path, i, str(img_dir))
            sheet_type_hint = None
            try:
                from sheet_pass_matrix import classify_sheet_type_from_text
                sheet_type_hint = classify_sheet_type_from_text(title_block_text)
            except ImportError:
                pass
            pipeline_pages.append({
                "image_path": img_path,
                "sheet_name": sheet,
                "sheet_type_hint": sheet_type_hint,
                "title_block_text": title_block_text,
                "full_page_text": doc[i].get_text(),
                "page_num": i + 1,
                "pdf_path": pdf_path,
                "page_index": i,
            })
    finally:
        doc.close()

    # ----------------------------------------------------------------
    # Pass 2 — Multi-pass extraction via TakeoffPipeline
    # ----------------------------------------------------------------
    def _progress(current: int, total_: int, sheet_name: str) -> None:
        if progress_callback:
            progress_callback(current, total_, sheet_name, phase="analyzing")

    project_legends: list = []
    companion = find_companion_takeoff_pdf(pdf_path)
    if companion:
        project_legends = extract_legend_schedules(companion)

    from object_manifest import resolve_project_manifest
    manifest = resolve_project_manifest(
        project_name,
        explicit_path=manifest_path or _find_manifest(pdf_path),
    )
    if manifest:
        logger.info("Using object manifest with %d objects", len(manifest))

    from plan_deterministic_legends import build_deterministic_legends
    det_legends = build_deterministic_legends(
        pdf_path, manifest=manifest, companion_present=bool(companion),
    )
    project_legends.extend(det_legends)

    pipeline = TakeoffPipeline()
    all_extracted, all_estimates, _project_type = pipeline.run_project(
        pipeline_pages,
        progress_callback=_progress,
        project_legend_schedules=project_legends or None,
        manifest=manifest,
        scale_feet_per_inch=scale_feet_per_inch,
    )

    # Emit "complete" progress for each successfully analyzed sheet
    if progress_callback:
        for idx, extracted in enumerate(all_extracted):
            if "error" not in extracted:
                extraction_counts = {
                    "measurements": len(extracted.get("measurements", [])),
                    "components": len(extracted.get("components", [])),
                    "rooms": len(extracted.get("rooms", [])),
                    "schedules": len(extracted.get("schedules", [])),
                }
                progress_callback(
                    idx + 1, total,
                    extracted.get("_sheet_name", extracted.get("_source_sheet", "")),
                    phase="complete", extraction=extraction_counts,
                )

    cross_refs = resolve_cross_references(all_extracted)
    all_estimates = resolve_spec_lookups(all_extracted, all_estimates)
    return generate_report(
        project_name, all_extracted, all_estimates,
        cross_references=cross_refs, manifest=manifest,
    )


def _find_manifest(pdf_path: str) -> Optional[str]:
    """Auto-discover a sibling object manifest next to the plans PDF.

    Looks for files whose name contains 'manifest' or 'objects' with a .json or
    .csv extension in the same folder. Returns the first match, or None.
    """
    try:
        folder = Path(pdf_path).resolve().parent
    except Exception:
        return None
    candidates = []
    for p in folder.iterdir():
        if not p.is_file() or p.suffix.lower() not in (".json", ".csv"):
            continue
        stem = p.stem.lower()
        if "manifest" in stem or "objects" in stem or stem.endswith("-scope"):
            candidates.append(p)
    if candidates:
        logger.info("Auto-discovered object manifest: %s", candidates[0].name)
        return str(candidates[0])
    return None
