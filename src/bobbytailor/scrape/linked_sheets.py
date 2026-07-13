"""
Linked sheet resolution: map ref_sheet codes to catalog page_ids and discover
unresolved refs from Claude extractions.

Two public functions consumed by scraper.py:
- collect_unresolved_refs: discover all ref_sheet codes not yet in the run
- match_ref_to_page: fuzzy-match a ref_sheet code to a catalog entry (page_id)
"""
import difflib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _normalize(s: str) -> str:
    """Normalize a sheet label for comparison.

    Uppercases, strips whitespace, and replaces '/' and '.' with '-'.
    """
    return s.upper().strip().replace("/", "-").replace(".", "-")


def match_ref_to_page(ref_sheet: str, catalog: list[dict]) -> Optional[dict]:
    """Map a short ref_sheet code to a catalog entry using fuzzy normalization.

    The catalog is the list returned by ``stackct_store.get_plans(stackct_id,
    folder_id)``.  Each entry has keys: ``page_id``, ``sheet_name``,
    ``sheet_type``, ``folder_id``.

    Scoring rules (higher wins):

    - 3 pts — sheet_name *prefix* (before first `` - ``) matches the normalized ref
    - 2 pts — normalized ref is a substring of the normalized sheet_name
    - 1 pt  — normalized sheet_name ends with the normalized ref

    If multiple entries share the highest score the one with the shortest
    ``sheet_name`` is returned.  Ties in length return the first candidate.

    If no entry scores > 0, a WARNING is logged with up to 3 near-miss
    suggestions (via ``difflib``) and ``None`` is returned.

    Args:
        ref_sheet: Short sheet reference code, e.g. ``"C-4"``, ``"3/A5"``.
        catalog: List of plan dicts from ``stackct_store.get_plans()``.

    Returns:
        The matching catalog dict, or ``None`` if no match found.
    """
    if not ref_sheet or not catalog:
        return None

    norm_ref = _normalize(ref_sheet)

    candidates: list[tuple[int, dict]] = []  # (score, entry)

    for entry in catalog:
        raw_name = entry.get("sheet_name") or ""
        norm_name = _normalize(raw_name)

        score = 0

        # 3 pts: prefix (before first " - ") equals normalized ref
        prefix = norm_name.split(" - ", 1)[0] if " - " in norm_name else norm_name
        if prefix == norm_ref:
            score = 3
        elif norm_ref in norm_name:
            # 2 pts: ref is a substring of the full normalized name
            score = 2
        elif norm_name.endswith(norm_ref):
            # 1 pt: name ends with the ref (covers "3-A5" suffix cases)
            score = 1

        if score > 0:
            candidates.append((score, entry))

    if not candidates:
        all_names = [_normalize(e.get("sheet_name") or "") for e in catalog]
        near = difflib.get_close_matches(norm_ref, all_names, n=3, cutoff=0.4)
        logger.warning(
            "match_ref_to_page: no match for %r (normalized: %r). "
            "Near-miss candidates: %s",
            ref_sheet,
            norm_ref,
            near or "none",
        )
        return None

    # Highest score wins; ties broken by shortest sheet_name
    best_score = max(s for s, _ in candidates)
    finalists = [e for s, e in candidates if s == best_score]
    result = min(finalists, key=lambda e: len(e.get("sheet_name") or ""))

    logger.debug(
        "match_ref_to_page: %r → %r (score=%d, page_id=%s)",
        ref_sheet,
        result.get("sheet_name"),
        best_score,
        result.get("page_id"),
    )
    return result


def collect_unresolved_refs(
    all_extracted: list[dict],
    already_in_run: set[int],
) -> list[dict]:
    """Collect all ref_sheet codes from Claude extractions not yet matched.

    Walks every extraction dict in ``all_extracted`` and harvests refs from:

    - ``extracted["cross_references"][].ref_sheet``
    - ``extracted["civil_structures"][].detail_ref_sheet``

    Deduplicates by ``ref_sheet`` (case-insensitive, first occurrence kept).
    Excludes empty/None ref values.

    Note: filtering against ``already_in_run`` page_ids is the *caller's*
    responsibility after matching refs to page_ids via ``match_ref_to_page``.
    The ``already_in_run`` parameter is accepted for API consistency but is not
    used to filter here — callers must do that step.

    Args:
        all_extracted: List of extraction dicts produced by the analyzer.
        already_in_run: Set of page_ids already present in the manifest
            (unused in collection; caller uses it for post-match filtering).

    Returns:
        List of ref record dicts, each with keys:
        ``ref_sheet``, ``from_sheet``, ``source`` (``"cross_ref"`` or
        ``"civil_structure"``).
    """
    seen: dict[str, bool] = {}  # normalized ref_sheet → True
    result: list[dict] = []

    for ext in all_extracted:
        from_sheet = ext.get("_source_sheet") or ""

        # Source 1: cross_references[].ref_sheet
        for ref_obj in ext.get("cross_references") or []:
            if not isinstance(ref_obj, dict):
                continue
            raw = ref_obj.get("ref_sheet")
            if not raw:
                continue
            key = raw.upper().strip()
            if key and key not in seen:
                seen[key] = True
                result.append(
                    {
                        "ref_sheet": raw,
                        "from_sheet": from_sheet,
                        "source": "cross_ref",
                    }
                )

        # Source 2: civil_structures[].detail_ref_sheet
        for struct in ext.get("civil_structures") or []:
            if not isinstance(struct, dict):
                continue
            raw = struct.get("detail_ref_sheet")
            if not raw:
                continue
            key = raw.upper().strip()
            if key and key not in seen:
                seen[key] = True
                result.append(
                    {
                        "ref_sheet": raw,
                        "from_sheet": from_sheet,
                        "source": "civil_structure",
                    }
                )

    return result
