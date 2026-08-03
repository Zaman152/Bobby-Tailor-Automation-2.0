"""Deterministic material / finish tag reader for the plan body.

**There is no finish schedule in the Moxy input, and that is the finding.**
The sheet indexed as ``CS-03 NOTES, REQUIREMENTS, FINISH SCHEDULES`` is listed
in the page-1 drawing index and is **not in the 40-page PDF**, and
``tables.SCHEDULE_KIND_VOCABULARIES["finish"]`` fires **zero times on all four
real plan sets** (INV-05 §1.1-1.2).  So the room-number-to-finish-code join
that a finish schedule would provide does not exist to be built.

What does exist is the join key the drawing prints on the sheet itself: the
two-token material tag, ``WC`` + ``07``, drawn beside the spelled-out material.
Diffing Moxy's take-off PDF against its plans PDF shows every WC quantity the
estimator recorded living on an interior-ELEVATION sheet (ID-200..ID-205), and
a direction-generic reader of that tag recovers the exact per-sheet code SET on
six of six of those sheets, including a true negative (INV-05 §2 Key A).

Two hard boundaries, both load-bearing
--------------------------------------
1. **This module reports a printed CALLOUT, never an area.**  INV-05 §3 seeded a
   flood fill at every WC tag: every fill leaked to the clip edge at four to ten
   times the estimator's figure, because an elevation's wall face is bounded
   above and below but open laterally — it is not a closed ink region, which is
   the one precondition ``room_fill`` states.  A tag says a finish was called
   out here; it does not say how much of it there is.
2. **Validation is by SET, never by count.**  The tag counts (9 instances of
   WC-1 on page 15, and so on) are callout instances, not regions.  Comparing
   them to a square-foot figure is the documented coincidence trap (D-07).  The
   acceptance test asserts *which codes appear on which sheet*.

This is a PURE EXTRACTOR: no pipeline import, no fusion import, no bundle key.
Wiring is plan 23-08.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from bobbytailor.deterministic.tag_pairing import (
    MAX_GAP_PT,
    PERP_TOL_PT,
    TagLine,
    bbox_inside_any,
    normalise_text,
    page_tag_lines,
    pair_two_token_tags,
    union_bbox,
)

logger = logging.getLogger(__name__)

#: Finish / material prefixes an architectural set prints as a plan-body tag.
#: Wall covering, wood, paint, acoustic tile, tile, carpet, luxury vinyl tile,
#: sealed concrete, ceramic tile, rubber base, stone, metal and glass.  Every
#: one of these was observed on the Moxy interior elevations except CPT/LVT/CT/
#: MTL/GL, which are the same convention on other drawing sets.
#:
#: The registry is deliberately SHORT.  Each additional prefix — especially each
#: one- or two-letter prefix — widens the surface on which a stray two-digit
#: number can manufacture a finish code that was never printed (T-23-17).
FINISH_PREFIXES = (
    "WC",    # wall covering
    "WD",    # wood
    "PT",    # paint
    "AT",    # acoustic tile
    "T",     # tile
    "CPT",   # carpet
    "LVT",   # luxury vinyl tile
    "SC",    # sealed concrete
    "CT",    # ceramic tile
    "RB",    # rubber base
    "ST",    # stone
    "MTL",   # metal
    "GL",    # glass
)
_PREFIX_SET = frozenset(FINISH_PREFIXES)

#: A material tag's number token: two digits, optionally suffixed by a variant
#: letter (Moxy prints ``T-11A`` and ``T-11B`` on page index 15).
FINISH_NUMBER_RE = re.compile(r"^\d{2}[A-Z]?$")


@dataclass(frozen=True)
class MaterialTag:
    """One two-token material callout read from the plan body."""

    code: str                                    # "WC-7" — normalised
    prefix: str                                  # "WC"
    number: str                                  # "07" — exactly as printed
    bbox_pt: Tuple[float, float, float, float]   # union of the two token boxes
    page_index: int = 0
    text_dir: Tuple[int, int] = (1, 0)

    def to_dict(self) -> dict:
        return asdict(self)


def is_finish_prefix(text: str) -> bool:
    """True for a bare registry prefix, e.g. ``WC``. Case-insensitive."""
    return normalise_text(text) in _PREFIX_SET


def is_finish_number(text: str) -> bool:
    """True for a two-digit number with an optional trailing variant letter."""
    return bool(FINISH_NUMBER_RE.match(normalise_text(text)))


def normalise_code(prefix: str, number: str) -> str:
    """``('WC', '07') -> 'WC-7'``.

    Leading zeros are stripped so the code matches the way the estimator's own
    legend writes it (``WC-7``, not ``WC-07``); a number that is all zeros keeps
    a single ``0`` rather than becoming empty.
    """
    p = normalise_text(prefix)
    n = normalise_text(number).lstrip("0") or "0"
    return "%s-%s" % (p, n)


def extract_material_tags(
    page,
    mask_rects: Sequence = (),
    page_index: Optional[int] = None,
    max_gap_pt: float = MAX_GAP_PT,
    perp_tol_pt: float = PERP_TOL_PT,
) -> List[MaterialTag]:
    """Every plan-body material tag on *page*, in document order.

    ``mask_rects`` are rectangles whose contents are not plan-body callouts —
    schedule-table bboxes and title-block / legend viewports.  Supplying them is
    MANDATORY for any caller reading a real sheet: a door-schedule tag column
    and a finish legend key look exactly like a plan-body callout, and that is
    the same false-positive class ``schedule_extraction._is_door_table`` exists
    to reject (INV-05 risk 3).  ``tag_pairing.sheet_mask_rects`` computes them.

    The default of ``()`` exists so the function stays unit-testable on a
    synthetic page, not because masking is optional on a real one.
    """
    lines: List[TagLine] = page_tag_lines(page, page_index)
    pairs = pair_two_token_tags(
        lines,
        is_finish_prefix,
        is_finish_number,
        max_gap_pt=max_gap_pt,
        perp_tol_pt=perp_tol_pt,
    )
    out: List[MaterialTag] = []
    for prefix_line, number_line in pairs:
        bbox = union_bbox(prefix_line.bbox_pt, number_line.bbox_pt)
        if bbox_inside_any(bbox, mask_rects):
            continue
        prefix = normalise_text(prefix_line.text)
        number = normalise_text(number_line.text)
        out.append(
            MaterialTag(
                code=normalise_code(prefix, number),
                prefix=prefix,
                number=number,
                bbox_pt=bbox,
                page_index=prefix_line.page_index,
                text_dir=prefix_line.text_dir,
            )
        )
    return out


def code_set(tags: Sequence[MaterialTag], prefix: Optional[str] = None) -> set:
    """The SET of codes in *tags*, optionally restricted to one prefix.

    The set — not the count — is the unit of validation for this module.
    """
    if prefix is None:
        return {t.code for t in tags}
    want = normalise_text(prefix)
    return {t.code for t in tags if t.prefix == want}


def extract_material_tags_for_doc(
    doc, use_masks: bool = True
) -> Dict[int, List[MaterialTag]]:
    """``{page_index: [MaterialTag, ...]}`` over an open ``fitz.Document``.

    With ``use_masks`` (the default) the schedule and title-block / legend masks
    are computed per page and applied, which is the only correct way to read a
    real sheet.  ``use_masks=False`` exists for probes that want to SEE what the
    masks removed; it must not be used to produce a published quantity.
    """
    from bobbytailor.deterministic.tag_pairing import (
        schedule_bboxes_by_page,
        sheet_mask_rects,
    )

    per_page_schedules = schedule_bboxes_by_page(doc) if use_masks else {}
    out: Dict[int, List[MaterialTag]] = {}
    for page_index in range(doc.page_count):
        page = doc[page_index]
        rects: Sequence = ()
        if use_masks:
            rects = sheet_mask_rects(page, per_page_schedules.get(page_index, ()))
        out[page_index] = extract_material_tags(page, rects, page_index)
    return out


if __name__ == "__main__":  # quick measurement harness (free, no API)
    import sys

    import fitz

    paths = sys.argv[1:] or [
        "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"
    ]
    for path in paths:
        doc = fitz.open(path)
        print("\n=== %s ===" % path.split("/")[-1])
        by_page = extract_material_tags_for_doc(doc)
        doc.close()
        for page_index in sorted(by_page):
            tags = by_page[page_index]
            if not tags:
                continue
            wc = sorted(code_set(tags, "WC"))
            print(
                "  page %2d: WC=%s  all=%s"
                % (page_index, wc, sorted(code_set(tags)))
            )
        print(
            "  (a code SET is the unit of validation; the per-code tag counts are "
            "callout instances, NOT regions, and are never compared to an area)"
        )
