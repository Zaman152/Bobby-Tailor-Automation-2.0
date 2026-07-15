"""Shared deterministic plan-layer extraction for PDF and StackCT runs.

Door schedules and building footprints are read from the PDF *text* layer — not
vision. This module centralises that logic so upload/PDF analysis and StackCT
screenshot runs share the same authoritative quantities.

Production is plans-only (V3-LEARN-04, 21-CONTEXT LOCKED): the default call
takes nothing but the plans PDF. Companion take-off awareness and the
manifest-driven footprint legend are gated behind explicit ``dev_*`` kwargs —
see benchmark scripts for ground-truth scoring.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def build_deterministic_legends(
    pdf_path: str,
    dev_manifest=None,
    dev_companion_present: bool = False,
) -> List[dict]:
    """Return authoritative legend schedule dicts from a plans PDF.

    Production is plans-only; see benchmark scripts for ground-truth scoring.
    The default call (``build_deterministic_legends(pdf_path)``) extracts door
    schedules from the plans text layer only — footprint quantities on the
    production path come from the 21-13 deterministic pipeline flow
    (tables/schedules/room polygons/printed dims), not from this module.

    Dev/benchmark-only kwargs:
        dev_manifest: An object manifest mapping footprint areas onto item
            names. Required for the footprint legend (it cannot exist without
            item names to attach areas to), so the footprint branch only runs
            when a manifest is supplied explicitly.
        dev_companion_present: True when a companion take-off PDF is being
            scored against (benchmark scenario) — skips the footprint legend
            because the companion already carries exact areas.
    """
    legends: List[dict] = []

    # Door schedule → authoritative legend. A *type + count* schedule (Crow-style:
    # Type / Count / Material columns) is read by the component-library harvester,
    # which counts every door and frame by material via the abbreviation key —
    # this recovers ALL rows, not just the handful a per-opening tag scan finds.
    # A per-opening schedule (Moxy-style: one row per opening tag) has no Count
    # column, so it keeps the proven per-opening extractor. Component path wins
    # when present; otherwise fall back.
    door_legend = None
    try:
        door_legend = build_door_component_legend(pdf_path)
        if door_legend:
            logger.info(
                "Door schedule (type+count): %d component row(s) from plans (pages %s)",
                len(door_legend.get("rows") or []),
                door_legend.get("_source_pages"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Door-component extraction failed: %s", exc)
        door_legend = None

    if not door_legend:
        try:
            from bobbytailor.deterministic.schedule_extraction import extract_door_legend_from_pdf
            door_legend = extract_door_legend_from_pdf(pdf_path)
            if door_legend:
                logger.info(
                    "Door schedule (per-opening): %d row(s) from plans (pages %s)",
                    len(door_legend.get("rows") or []),
                    door_legend.get("_source_pages"),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Door-schedule extraction failed: %s", exc)
            door_legend = None

    if door_legend:
        legends.append(door_legend)

    if not dev_companion_present and dev_manifest:
        try:
            from bobbytailor.deterministic.footprint_takeoff import extract_footprint_legend
            fp_legend = extract_footprint_legend(pdf_path, dev_manifest)
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


def build_door_component_legend(pdf_path: str) -> Optional[dict]:
    """Build an authoritative door/frame legend from a *type + count* schedule.

    Delegates to the component-library harvester, which reads the Type / Count /
    Material columns of a type+count door schedule and counts doors AND frames by
    material via the abbreviation key (with the printed-note HM reclassification).
    Each material group becomes an EXACT, auto-verifiable ``takeoff_legend`` row
    whose quantity passes through verbatim (never re-waste a counted door).

    Returns ``None`` when the set has no type+count door schedule (e.g. a
    per-opening schedule, which keeps its ``schedule_extraction`` path).
    """
    try:
        import fitz
    except Exception:  # noqa: BLE001
        return None
    try:
        doc = fitz.open(pdf_path)
    except Exception:  # noqa: BLE001
        return None
    try:
        from bobbytailor.deterministic.component_library import extract_door_component_counts
        page_text = "\n".join(
            (doc[i].get_text() or "") for i in range(doc.page_count)
        )
        counts = extract_door_component_counts(doc, notes_text=page_text)
        # Which pages carried a door schedule (for provenance).
        source_pages = [
            i + 1 for i in range(doc.page_count)
            if "DOOR SCHEDULE" in ((doc[i].get_text() or "").upper())
        ]
    except Exception:  # noqa: BLE001
        return None
    finally:
        doc.close()

    if not counts:
        return None

    rows: List[dict] = []
    total = 0
    for c in counts:
        n = c.get("quantity")
        if not n:
            continue
        total += int(n)
        rows.append({
            "ITEM": c["name"],
            "DESCRIPTION": c["name"],
            "QTY": str(n), "QUANTITY": str(n), "UNIT": c.get("unit") or "EA",
        })
    if not rows:
        return None

    return {
        "name": "Door Schedule (extracted from plans)",
        "table_purpose": "takeoff_legend",
        "schedule_type": "door",
        "use_for_takeoff": True,
        "description": (
            "{} scheduled doors/frames counted deterministically by material from "
            "the type+count door schedule on sheet page(s) {}. Materials decoded "
            "via the plan's abbreviation key; personnel doors carried in hollow "
            "metal frames are named per the plan's printed HOLLOW METAL DOOR note."
        ).format(total, source_pages),
        "columns": ["ITEM", "QTY", "UNIT"],
        "rows": rows,
        "_source_pages": source_pages,
    }


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
    dev_manifest=None,
    dev_companion_present: bool = False,
) -> List[dict]:
    """Build legends from per-page PDF blobs captured during a StackCT scrape.

    Production is plans-only; see benchmark scripts for ground-truth scoring.
    Scans ``run_dir/blobs/`` (canonical since 21-15) with a fallback to the
    legacy ``run_dir/pdfs/`` layout so resumed pre-21-15 runs keep working.
    """
    page_pdfs: List[Path] = []
    for sub in ("blobs", "pdfs"):
        pdf_dir = run_dir / sub
        if pdf_dir.is_dir():
            page_pdfs = sorted(pdf_dir.glob("*.pdf"))
            if page_pdfs:
                break
    if not page_pdfs:
        return []
    combined = run_dir / "_plans_combined.pdf"
    merged = merge_page_pdfs(page_pdfs, combined)
    if not merged:
        return []
    return build_deterministic_legends(merged, dev_manifest=dev_manifest,
                                       dev_companion_present=dev_companion_present)


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
