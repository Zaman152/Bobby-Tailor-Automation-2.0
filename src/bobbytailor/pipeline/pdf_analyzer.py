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
from typing import Optional, Union

from PIL import Image

from bobbytailor.pipeline.calculator import resolve_spec_lookups
from bobbytailor.pipeline.coverage import ERRORED, NOT_APPLICABLE, CoverageLedger
from bobbytailor.pipeline.cross_references import resolve_cross_references
from bobbytailor.pipeline.reporter import generate_report
from bobbytailor.pipeline.takeoff_pipeline import (
    RunSettings,
    TakeoffPipeline,
    page_measurable_signal,
)
from bobbytailor.pipeline.page_text_enrichment import enrich_components_from_page_text
from bobbytailor.config import RENDER_TARGET_PX, SCREENSHOTS_DIR

logger = logging.getLogger(__name__)

# Anthropic vision hard cap: the API rejects images whose longest side
# exceeds 8000 px (RESEARCH §5 image constraints, verified July 2026).
# This is a SAFETY cap only — whole-sheet renders target RENDER_TARGET_PX
# (default 1568 px, the model's standard downscale resolution); detail
# zooms use render_clip_crop() instead of bigger full-page rasters.
_MAX_IMAGE_LONG_SIDE_PX = 8000


def _effective_render_scale(page: fitz.Page, scale: float) -> float:
    """Clamp *scale* so the rendered PNG longest side stays within the API cap.

    Shared by takeoff_pipeline's hi-res crop/tile renderers as the single
    source of the 8000 px API limit.
    """
    longest = max(page.rect.width, page.rect.height)
    if longest <= 0:
        return scale
    return min(scale, _MAX_IMAGE_LONG_SIDE_PX / longest)


def _target_render_scale(page: fitz.Page, target_px: int) -> float:
    """Zoom factor placing the page's long edge at *target_px* (API-capped)."""
    longest = max(page.rect.width, page.rect.height)
    if longest <= 0:
        return 1.0
    return _effective_render_scale(page, target_px / longest)

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


def _page_to_image(
    pdf_path: str,
    page_num: int,
    output_dir: str,
    target_px: Optional[int] = None,
) -> str:
    """Render a single PDF page to a PNG with its long edge at ≈*target_px*.

    Claude downscales standard whole-sheet vision input to ~1568 px long edge
    (RESEARCH §5) — rendering larger wastes tokens and upload size without
    adding model-visible detail. Regions that need legibility are zoomed via
    render_clip_crop() instead of inflating the full-page raster.

    Args:
        pdf_path:   Path to the PDF file.
        page_num:   0-based page index.
        output_dir: Directory to save the image.
        target_px:  Long-edge target in pixels; defaults to config
                    RENDER_TARGET_PX (1568). Always capped at the 8000 px
                    API limit.

    Returns:
        Absolute path to the saved PNG file.
    """
    if target_px is None:
        target_px = RENDER_TARGET_PX
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_num]
        scale = _target_render_scale(page, target_px)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        img_path = str(Path(output_dir) / f"page_{page_num + 1:04d}.png")
        pix.save(img_path)
        return img_path
    finally:
        doc.close()


def render_clip_crop(
    page: fitz.Page,
    rect_pt: Union[fitz.Rect, tuple],
    target_px: int = 1568,
) -> Image.Image:
    """Render a clip region of *page* at a zoom targeting *target_px* long edge.

    The shared zoom primitive for adaptive fidelity: verify-retry arbitration
    crops (21-14), crop galleries (21-08), and ensemble tiles (21-11) all zoom
    INTO a region at native detail rather than rendering bigger whole-sheet
    rasters.

    Args:
        page:      An open fitz.Page.
        rect_pt:   Clip rectangle in page points — a fitz.Rect or an
                   (x0, y0, x1, y1) tuple.
        target_px: Desired long-edge size of the rendered crop in pixels
                   (default 1568). Capped so the render never exceeds the
                   8000 px API limit.

    Returns:
        PIL.Image (RGB) of the rendered crop.

    Raises:
        ValueError: If the clip rectangle is empty, infinite, or degenerate.
    """
    clip = fitz.Rect(rect_pt)
    if clip.is_empty or clip.is_infinite:
        raise ValueError(f"render_clip_crop: invalid clip rect {rect_pt!r}")
    longest = max(clip.width, clip.height)
    if longest <= 0:
        raise ValueError(f"render_clip_crop: degenerate clip rect {rect_pt!r}")
    zoom = min(target_px, _MAX_IMAGE_LONG_SIDE_PX) / longest
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


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
        from bobbytailor.pipeline.sheet_pass_matrix import classify_sheet_type_from_text  # type: ignore
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

    Production input contract (V3-LEARN-04, LOCKED): the plans PDF is the ONLY
    pipeline input. No sibling companion take-off or manifest file is ever
    auto-discovered from the upload folder; ``manifest_path`` is an optional,
    explicitly provided dev input.

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
    # Coverage ledger (INV-08 / SP-8) — one row per PAGE OF THE SOURCE
    # PDF, created BEFORE any routing or page-selection filtering.
    #
    # This ordering is the whole point. Today a page the classifier
    # discards never becomes a processed sheet, so it leaves no row, no
    # flag and no count in any artifact: a 40-page Moxy run renders
    # "Sheets analyzed: 22" and is silent about the other 18. Registering
    # first makes the ledger's completeness an invariant of construction
    # rather than something each code path has to remember.
    # ----------------------------------------------------------------
    ledger = CoverageLedger(pages_in_source=total_pages)
    selected = set(pages_to_process)
    for i in range(total_pages):
        if i in selected:
            ledger.register_page(i)
        else:
            ledger.register_page(
                i,
                disposition=NOT_APPLICABLE,
                reason="not selected for analysis",
            )

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
                from bobbytailor.pipeline.sheet_pass_matrix import (
                    classify_sheet_type_verbose,
                )
                # Routing input is UNCHANGED (title-block text only). The
                # verbose form adds the reason, never a different verdict.
                sheet_type_hint, type_source, kw, ctx = classify_sheet_type_verbose(
                    title_block_text
                )
                ledger.register_page(
                    i,
                    sheet_name=sheet,
                    sheet_type=sheet_type_hint,
                    type_source=type_source,
                    classifier_keyword=kw,
                    classifier_context=ctx,
                    # Recorded for plan 23-06, NOT acted on here — see the
                    # field's comment in pipeline/coverage.py.
                    sheet_type_full_text=classify_sheet_type_verbose(
                        title_block_text, doc[i].get_text()
                    )[0],
                )
            except ImportError:
                pass
            except Exception as exc:  # noqa: BLE001 — per-page degradation
                logger.warning(
                    "coverage: classification failed on page %d (%s)", i, exc,
                )

            # Measurable signal, once per page, zero API (~0.2 s/page). A
            # malformed page records ERRORED with its message instead of
            # aborting the run — an untrusted PDF must not be able to stop
            # the analysis by carrying one broken page (threat T-23-01).
            try:
                ledger.register_page(
                    i, measurable_signal=page_measurable_signal(doc[i]),
                )
            except Exception as exc:  # noqa: BLE001 — per-page degradation
                logger.warning(
                    "coverage: measurable-signal probe failed on page %d (%s)",
                    i, exc,
                )
                ledger.register_page(
                    i,
                    disposition=ERRORED,
                    reason="measurable-signal probe failed: %s" % exc,
                )

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

    # Plans-only production input contract (V3-LEARN-04, 21-CONTEXT LOCKED):
    # the pipeline sees ONLY the plans PDF. Sibling `*takeoff*.pdf` files are
    # NEVER auto-discovered — a human take-off is an evaluation-only input
    # that benchmark scripts pass explicitly as the scoring reference
    # (scripts/vision_only_benchmark.py). Likewise, object-manifest files are
    # NEVER auto-discovered — neither from the plans PDF's folder nor from
    # the `manifests/` dir (allow_discovery=False, 21-REVIEW WR-08): a
    # manifest is an optional, explicitly uploaded dev input (manifest_path).
    from bobbytailor.devtools.object_manifest import resolve_project_manifest
    manifest = resolve_project_manifest(
        project_name, explicit_path=manifest_path, allow_discovery=False,
    )
    if manifest:
        logger.info("Using object manifest with %d objects", len(manifest))

    from bobbytailor.deterministic.plan_deterministic_legends import build_deterministic_legends
    project_legends: list = build_deterministic_legends(
        pdf_path, dev_manifest=manifest,
    )

    # Shared RunSettings (21-13/21-15, V3-STRUCT-02): both entry points
    # construct RunSettings.from_env() at run start — the scraper refreshes
    # its module-level singleton the same way, so StackCT and PDF-upload runs
    # are settings-identical by construction.
    pipeline = TakeoffPipeline(settings=RunSettings.from_env())
    # project_key threads the run into the learning store (21-16,
    # V3-LEARN-03): run_project retrieves the LearnedContext once at run
    # start and injects it into prompt hints, scale priors, wall-height
    # assumptions, and re_verify guardrail flags.
    all_extracted, all_estimates, _project_type = pipeline.run_project(
        pipeline_pages,
        progress_callback=_progress,
        project_legend_schedules=project_legends or None,
        manifest=manifest,
        scale_feet_per_inch=scale_feet_per_inch,
        project_key=project_name,
        coverage=ledger,
    )

    # The invariant (INV-08 §3.1): every page of the source PDF has exactly one
    # ledger row. If this ever fires the run's own accounting is incomplete, so
    # it is logged loudly rather than swallowed — but it never aborts a run that
    # otherwise produced numbers.
    unaccounted = ledger.assert_accounted()
    if unaccounted:
        logger.error(
            "coverage: %d source page(s) have no ledger row: %s — every total "
            "below is a lower bound", len(unaccounted), unaccounted,
        )
    for line in ledger.warnings():
        logger.warning("coverage: %s", line)

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
        learned=pipeline.learned_context,
        library=getattr(pipeline, "_project_vocabulary", None),
    )
