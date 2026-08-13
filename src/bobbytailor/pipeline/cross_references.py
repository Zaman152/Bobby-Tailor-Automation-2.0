"""
Resolve drawing cross-references against sheets analyzed in the same run.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _sheet_label(extracted: dict) -> str:
    return (
        extracted.get("_source_sheet")
        or extracted.get("sheet_title")
        or ""
    ).upper()


def find_detail_in_extraction(extracted: dict, detail_number: str) -> dict:
    """Search an extraction dict for a specific detail number."""
    results: Dict[str, Any] = {}
    detail_str = str(detail_number).strip()
    if not detail_str:
        return results

    for sched in extracted.get("schedules", []):
        for row in sched.get("rows", []):
            if not isinstance(row, dict):
                continue
            for v in row.values():
                if detail_str in str(v):
                    results["from_schedule"] = row
                    results["schedule_name"] = sched.get("name")
                    return results

    for comp in extracted.get("components", []):
        if detail_str in str(comp.get("name", "")):
            results["from_component"] = comp
            return results

    for struct in extracted.get("civil_structures", []):
        if detail_str in str(struct.get("detail_ref_number", "")):
            results["from_civil_structure"] = struct
            return results

    return results


def _match_target_sheet(all_extracted: List[dict], ref_sheet: str) -> Optional[dict]:
    ref = (ref_sheet or "").upper().strip()
    if not ref:
        return None
    for ext in all_extracted:
        label = _sheet_label(ext)
        if ref in label or label.endswith(ref) or ref.replace("/", "") in label.replace(" ", ""):
            return ext
    return None


def resolve_cross_references(all_extracted: List[dict]) -> List[dict]:
    """Collect and resolve cross-references from all sheets in a run."""
    resolved_list: List[dict] = []

    for ext in all_extracted:
        from_sheet = ext.get("_source_sheet", "unknown")
        for ref in ext.get("cross_references", []):
            if not isinstance(ref, dict):
                continue
            entry = {
                "from_sheet": from_sheet,
                "ref_sheet": ref.get("ref_sheet", ""),
                "ref_number": ref.get("ref_number", ""),
                "item_described": ref.get("item_described", ""),
                "context": ref.get("context", ""),
                "partial_data": ref.get("on_this_sheet_data", {}),
                "resolved_spec": None,
                "resolution_status": None,
            }
            target = _match_target_sheet(all_extracted, entry["ref_sheet"])
            if target:
                detail = find_detail_in_extraction(target, entry["ref_number"])
                if detail:
                    entry["resolved_spec"] = detail
                    entry["resolution_status"] = "resolved"
                else:
                    entry["resolution_status"] = "target_found_detail_missing"
            else:
                entry["resolution_status"] = "target_sheet_not_found"
            resolved_list.append(entry)

    return resolved_list


# ---------------------------------------------------------------------------
# Sheet-set completeness (deterministic, zero API)
# ---------------------------------------------------------------------------
#
# A plan set that CITES a sheet it does not CONTAIN has a hole in it, and every
# quantity that lives on the missing sheet is unknowable — not zero, not
# missing because the engine failed, but absent from the input.
#
# Crow is the case that forced this. Its golden take-off lists 10 stairs. The
# uploaded 4-page PDF contains A-101, A-201, A-401 and A-601, and it defers
# three times — "SEE 1/A-111", "SEE 1/A-112", "SEE 1/A-113" — to enlarged plans
# that are not in the file. A-401 (page 2) draws a STAIR PLAN, a STAIR SECTION
# and a STAIR RAIL, so the set shows what a stair looks like; the sheets that
# would say how many are installed and where are the ones missing. There is no
# detector — deterministic, ML or vision — that can count objects that are not
# in the file, and any number printed there is a fabrication.
#
# (Correcting INV-B on a point of fact: it reports the stairs as living on
# "A-401 details and the A-111/112/113 enlarged plans, which are not in the
# uploaded PDF". A-401 IS in the uploaded PDF — it is page 2. Only A-111, A-112
# and A-113 are absent, along with A-002 and A-501.)

import re as _re

_SHEET_ID_RE = _re.compile(r"\b([A-Z]{1,2}-\d{3}[A-Z]?)\b")


def sheet_ids_in_text(text: str) -> List[str]:
    """Every drawing-sheet identifier cited in *text* (``A-401``, ``M-101``)."""
    return _SHEET_ID_RE.findall((text or "").upper())


def missing_referenced_sheets(
    sheets_present: List[str],
    page_texts: List[str],
) -> List[Dict[str, Any]]:
    """Sheets the drawing set cites but does not contain.

    ``sheets_present`` are the sheet ids read from each page's own title block;
    ``page_texts`` is the full text of each page, in the same page order.

    Returns one record per missing sheet id, with the page indices that cite it
    and how many times — evidence a human can check against the drawing. Pure
    string work: no fitz, no I/O, no API.
    """
    present = {str(s).strip().upper() for s in sheets_present if str(s).strip()}
    cited: Dict[str, List[int]] = {}
    for index, text in enumerate(page_texts):
        for sheet_id in sheet_ids_in_text(text):
            if sheet_id in present:
                continue
            cited.setdefault(sheet_id, []).append(index)
    return [
        {
            "sheet_id": sheet_id,
            "cited_on_pages": sorted(set(pages)),
            "citations": len(pages),
        }
        for sheet_id, pages in sorted(cited.items())
    ]
