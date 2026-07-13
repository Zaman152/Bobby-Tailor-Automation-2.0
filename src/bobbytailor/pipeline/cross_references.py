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
