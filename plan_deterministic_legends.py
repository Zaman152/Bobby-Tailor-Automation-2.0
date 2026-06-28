"""Shared deterministic plan-layer extraction for PDF and StackCT runs.

Door schedules and building footprints are read from the PDF *text* layer — not
vision. This module centralises that logic so upload/PDF analysis and StackCT
screenshot runs share the same authoritative quantities.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def build_deterministic_legends(
    pdf_path: str,
    manifest=None,
    companion_present: bool = False,
) -> List[dict]:
    """Return authoritative legend schedule dicts from a plans PDF.

    When ``companion_present`` is True (companion take-off PDF beside the plans),
    footprint is skipped — the companion already carries exact areas.
    Door schedules are still extracted from the plans (type breakdown).
    """
    legends: List[dict] = []

    try:
        from schedule_extraction import extract_door_legend_from_pdf
        door_legend = extract_door_legend_from_pdf(pdf_path)
        if door_legend:
            legends.append(door_legend)
            logger.info(
                "Door schedule: %d row(s) from plans (pages %s)",
                len(door_legend.get("rows") or []),
                door_legend.get("_source_pages"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Door-schedule extraction failed: %s", exc)

    if not companion_present and manifest:
        try:
            from footprint_takeoff import extract_footprint_legend
            fp_legend = extract_footprint_legend(pdf_path, manifest)
            if fp_legend:
                legends.append(fp_legend)
                logger.info(
                    "Footprint: %d floor/roof item(s) (pages %s)",
                    len(fp_legend.get("rows") or []),
                    fp_legend.get("_source_pages"),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Footprint extraction failed: %s", exc)

    return legends


def merge_page_pdfs(pdf_paths: List[Path], out_path: Path) -> Optional[str]:
    """Merge single-page PDFs into one file for schedule/footprint scanning."""
    paths = [p for p in pdf_paths if p.is_file() and p.stat().st_size > 500]
    if not paths:
        return None
    if len(paths) == 1:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if paths[0].resolve() != out_path.resolve():
            import shutil
            shutil.copy2(paths[0], out_path)
        return str(out_path)
    try:
        import fitz
    except Exception:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged = fitz.open()
    try:
        for p in sorted(paths):
            src = fitz.open(str(p))
            merged.insert_pdf(src)
            src.close()
        if merged.page_count == 0:
            return None
        merged.save(str(out_path))
        return str(out_path)
    finally:
        merged.close()


def build_deterministic_legends_from_run_dir(
    run_dir: Path,
    manifest=None,
    companion_present: bool = False,
) -> List[dict]:
    """Build legends from per-page PDFs captured during a StackCT scrape."""
    pdf_dir = run_dir / "pdfs"
    if not pdf_dir.is_dir():
        return []
    page_pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not page_pdfs:
        return []
    combined = run_dir / "_plans_combined.pdf"
    merged = merge_page_pdfs(page_pdfs, combined)
    if not merged:
        return []
    return build_deterministic_legends(merged, manifest=manifest,
                                       companion_present=companion_present)


def inject_project_legends(all_extracted: List[dict], legends: List[dict]) -> None:
    """Attach authoritative legend schedules to extracted sheet dicts (once)."""
    if not legends or not all_extracted:
        return
    if any(e.get("_companion_legend_injected") for e in all_extracted):
        return
    for extracted in all_extracted:
        if extracted.get("_skipped") or "error" in extracted:
            continue
        if extracted.get("_sheet_type") == "floor_plan":
            existing = list(extracted.get("schedules") or [])
            extracted["schedules"] = existing + list(legends)
            extracted["_companion_legend_injected"] = True
            logger.info(
                "Injected %d deterministic legend row(s) into %r",
                sum(len(s.get("rows") or []) for s in legends),
                extracted.get("_sheet_name", extracted.get("_source_sheet", "?")),
            )
            return
    for extracted in all_extracted:
        if extracted.get("_skipped") or "error" in extracted:
            continue
        existing = list(extracted.get("schedules") or [])
        extracted["schedules"] = existing + list(legends)
        extracted["_companion_legend_injected"] = True
        logger.info(
            "Injected %d deterministic legend row(s) into %r (fallback)",
            sum(len(s.get("rows") or []) for s in legends),
            extracted.get("_sheet_name", extracted.get("_source_sheet", "?")),
        )
        return
