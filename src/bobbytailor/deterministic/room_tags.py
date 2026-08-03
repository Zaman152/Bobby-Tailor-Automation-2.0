"""Deterministic room-tag reader and the fail-closed unit-mix census.

**The long-standing claim that the unit multiplier is unrecoverable from the
drawings is FALSE.**  ``pipeline/takeoff_pipeline.py::_manifest_room_mix``
states in its docstring that a repeat count is "routinely not in the drawing set
at all … so no reading of the plan can recover it", and
``docs/PIPELINE-GROUND-TRUTH.md`` records the same claim as "BLOCKER A".

Moxy's pages 7 and 8 (ID-001 / ID-002) are stacked unit key plans carrying 214
room tags with 214 distinct room numbers and no duplicates.  Counting them blind
— before any comparison was made — yields ``QQ A 90``, ``KING A 26``,
``K SUITE B 2``, ``BUNK B 1``, a 4/4 exact match against the golden multipliers
(INV-05 §2 Key B).  The multiplier is in the input.  Correcting the pipeline
docstring is plan 23-08 and correcting the ground-truth document is plan 23-16
(decision D-01); this module supplies the evidence, and changes neither.

The convention is the drawing's, not ours
-----------------------------------------
Take-off page 2 (CS-02) prints this set's own symbol legend verbatim:
``ROOM TAG / ROOM NAME / ROOM NUMBER``.  A room tag is therefore a name line
with a number line beneath it — beneath in the text's own advance direction,
which on these rotated sheets is +x on the page.  That is why the pairing goes
through ``tag_pairing.pair_two_token_tags(..., axis=ACROSS)`` and not through a
second copy of the geometry.

Why the census must fail closed
-------------------------------
Every guestroom quantity in the take-off is a per-prototype area multiplied by a
unit count, so a census that double-counts multiplies the error into Gyp
Ceiling, Gyp Wall, Guestroom-Wall Covering and Doors at once (threat T-23-18).
Moxy's key plans happen to number levels 2-7 uniquely.  A set drawn with
per-floor key plans would repeat ``101`` on every floor, and a census that
quietly counted it once — or twice — would be a guess.  :func:`derive_room_mix`
therefore REFUSES on any duplicated number: it returns an empty mapping plus a
flag naming the duplicates, never a partial count (INV-05 risk 4).

This is a PURE EXTRACTOR: no pipeline import, no fusion import, no bundle key.
Wiring is plan 23-08.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from bobbytailor.deterministic.tag_pairing import (
    ACROSS,
    TagLine,
    bbox_inside_any,
    normalise_text,
    page_tag_lines,
    pair_two_token_tags,
    union_bbox,
)

logger = logging.getLogger(__name__)

#: A room number: three digits (``204``), or a discipline letter with one or two
#: digits (``T21`` for a stair, ``L1`` for a lobby core).  This is the shape the
#: set's own ROOM TAG legend prints.
ROOM_NUMBER_RE = re.compile(r"^(?:\d{3}|[A-Z]\d{1,2})$")

#: A room name: begins with a letter and holds only the characters a drawn room
#: label uses.  Prose is excluded by :data:`MAX_ROOM_NAME_CHARS` rather than by a
#: word list, because room names are the drawing's vocabulary, not ours.
ROOM_NAME_RE = re.compile(r"^[A-Z][A-Z0-9 .&()'/-]*$")

#: Longest accepted room name.  The longest observed on Moxy's key plans is
#: ``VALET HANGER`` at 12 characters; 24 leaves generous room for a compound
#: name while keeping a sentence of general notes out of the census.
MAX_ROOM_NAME_CHARS = 24

#: Largest advance-axis gap between a room tag's two lines, in points.  Pinned
#: from measurement: across every Moxy sheet the observed gap between the name
#: line and the number line runs 1.12 pt to 3.57 pt, because the two lines are
#: drawn as one symbol and set solid.  6.0 pt is under half the observed line
#: extent (11.7 pt), which is the geometric reason it is safe — a line belonging
#: to the text block below cannot reach into the window without first colliding
#: with its own block.  It is a different constant from the material tag's
#: 16.0 pt because it measures a different axis, not because it was relaxed.
ROOM_TAG_MAX_GAP_PT = 6.0

#: Overlap tolerance on the reading axis.  A room number is drawn centred under
#: its name, so the two lines overlap substantially; 3.0 pt only absorbs the
#: case where a long name is set slightly off-centre.
ROOM_TAG_PERP_TOL_PT = 3.0


@dataclass(frozen=True)
class RoomTag:
    """One ``ROOM NAME`` / ``ROOM NUMBER`` tag read from a plan."""

    name: str                                    # "KING A" — normalised
    number: str                                  # "204" — exactly as printed
    bbox_pt: Tuple[float, float, float, float]   # union of the two line boxes
    page_index: int = 0
    text_dir: Tuple[int, int] = (1, 0)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RoomMix:
    """The result of a room-tag census, including its refusal.

    ``refused`` is the whole point: an empty ``counts`` with ``refused=True`` and
    a populated ``duplicate_numbers`` is a REFUSAL, and an empty ``counts`` with
    ``refused=False`` means the drawing set carries no room tags at all.  Threat
    T-23-20 is exactly that those two states must be distinguishable.
    """

    counts: Dict[str, int] = field(default_factory=dict)
    total_tags: int = 0
    distinct_numbers: int = 0
    duplicate_numbers: Tuple[str, ...] = ()
    pages_censused: Tuple[int, ...] = ()
    refused: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def is_room_name(text: str) -> bool:
    """True for an alphabetic room label that is not itself a number."""
    t = normalise_text(text)
    if not t or len(t) > MAX_ROOM_NAME_CHARS:
        return False
    if ROOM_NUMBER_RE.match(t):
        return False
    if not ROOM_NAME_RE.match(t):
        return False
    return any(c.isalpha() for c in t)


def is_room_number(text: str) -> bool:
    """True for the room-number shape the set's own symbol legend prints."""
    return bool(ROOM_NUMBER_RE.match(normalise_text(text)))


def normalise_room_name(name: str) -> str:
    """The census key: whitespace-collapsed, lower case."""
    return " ".join(str(name or "").split()).strip().lower()


def extract_room_tags(
    page,
    mask_rects: Sequence = (),
    page_index: Optional[int] = None,
    max_gap_pt: float = ROOM_TAG_MAX_GAP_PT,
    perp_tol_pt: float = ROOM_TAG_PERP_TOL_PT,
) -> List[RoomTag]:
    """Every ``ROOM NAME`` / ``ROOM NUMBER`` tag on *page*, in document order.

    ``mask_rects`` carry the same obligation they carry for material tags: a
    door-schedule tag column reads exactly like a plan-body room tag.  On Moxy
    page index 6 — the door-schedule sheet, which holds no rooms at all — the
    unmasked reader pairs ``LEVEL 01 LOWER`` with ``003`` and ``LEVEL 07`` with
    ``715``, two rooms that do not exist.  Supplying the door schedule's own
    bbox from ``tables.extract_schedules`` removes them along with every other
    tag drawn inside the table (measured: 5 tags on that sheet become 1).
    """
    lines: List[TagLine] = page_tag_lines(page, page_index)
    pairs = pair_two_token_tags(
        lines,
        is_room_name,
        is_room_number,
        max_gap_pt=max_gap_pt,
        perp_tol_pt=perp_tol_pt,
        axis=ACROSS,
    )
    out: List[RoomTag] = []
    for name_line, number_line in pairs:
        bbox = union_bbox(name_line.bbox_pt, number_line.bbox_pt)
        if bbox_inside_any(bbox, mask_rects):
            continue
        out.append(
            RoomTag(
                name=normalise_text(name_line.text),
                number=normalise_text(number_line.text),
                bbox_pt=bbox,
                page_index=name_line.page_index,
                text_dir=name_line.text_dir,
            )
        )
    return out


def census_room_tags(tags: Sequence[RoomTag], pages: Sequence[int] = ()) -> RoomMix:
    """Turn a bag of room tags into a unit mix, or into a refusal.

    The uniqueness gate is the contract: a room number identifies a room, so a
    number appearing twice means the censused sheets overlap and the count would
    be inflated.  There is no partial answer for that case — the mapping comes
    back empty with the offending numbers named.
    """
    seen: Dict[str, List[str]] = {}
    counts: Dict[str, int] = {}
    for tag in tags:
        seen.setdefault(tag.number, []).append(tag.name)
        key = normalise_room_name(tag.name)
        counts[key] = counts.get(key, 0) + 1
    duplicates = tuple(sorted(n for n, names in seen.items() if len(names) > 1))
    if duplicates:
        shown = ", ".join(duplicates[:10])
        if len(duplicates) > 10:
            shown += ", … (%d more)" % (len(duplicates) - 10)
        return RoomMix(
            counts={},
            total_tags=len(tags),
            distinct_numbers=len(seen),
            duplicate_numbers=duplicates,
            pages_censused=tuple(pages),
            refused=True,
            reason=(
                "room numbers are not unique across the censused sheets, so the "
                "census would double-count: %d number(s) appear more than once "
                "(%s). No unit mix is published." % (len(duplicates), shown)
            ),
        )
    return RoomMix(
        counts=counts,
        total_tags=len(tags),
        distinct_numbers=len(seen),
        duplicate_numbers=(),
        pages_censused=tuple(pages),
        refused=False,
        reason="",
    )


def derive_room_mix(
    doc,
    pages: Optional[Sequence[int]] = None,
    mask_rects_by_page: Optional[Dict[int, Sequence]] = None,
) -> RoomMix:
    """Census the room tags of an open ``fitz.Document`` into a unit mix.

    ``pages`` restricts the census to the sheets that actually key the units.
    That restriction belongs to the CALLER, because deciding which sheet is a
    unit key plan is sheet classification, not tag reading — and because the
    whole-document default is the honest one: a set that draws the same room on
    a key plan and again on a floor plan does repeat its numbers, this function
    cannot tell a repeat from a re-use, and so it refuses.  On Moxy the whole
    document refuses and pages ``[7, 8]`` alone reproduce 4 of 4 golden unit
    multipliers.

    Never falls back to a partial census (threat T-23-18).
    """
    page_indices = (
        list(range(int(getattr(doc, "page_count", 0))))
        if pages is None
        else [int(p) for p in pages]
    )
    tags: List[RoomTag] = []
    for page_index in page_indices:
        try:
            page = doc[page_index]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Page %s unreadable: %s", page_index, exc)
            continue
        rects: Sequence = ()
        if mask_rects_by_page:
            rects = mask_rects_by_page.get(page_index, ())
        tags.extend(extract_room_tags(page, rects, page_index))
    return census_room_tags(tags, page_indices)


if __name__ == "__main__":  # quick measurement harness (free, no API)
    import sys

    import fitz

    from bobbytailor.deterministic.tag_pairing import sheet_mask_rects

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    page_args = [a for a in sys.argv[1:] if a.startswith("--pages=")]
    only = None
    if page_args:
        only = [int(v) for v in page_args[-1].split("=", 1)[1].split(",") if v.strip()]
    paths = args or ["uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"]
    for path in paths:
        doc = fitz.open(path)
        masks = {
            i: sheet_mask_rects(doc[i])
            for i in (only if only is not None else range(doc.page_count))
        }
        mix = derive_room_mix(doc, pages=only, mask_rects_by_page=masks)
        per_page = {}
        for i in sorted(masks):
            n = len(extract_room_tags(doc[i], masks[i], i))
            if n:
                per_page[i] = n
        doc.close()
        print("\n=== %s pages=%s ===" % (path.split("/")[-1], only or "all"))
        print("  tags=%d distinct numbers=%d duplicates=%d"
              % (mix.total_tags, mix.distinct_numbers, len(mix.duplicate_numbers)))
        print("  per-page tag counts: %s" % per_page)
        if mix.refused:
            print("  REFUSED: %s" % mix.reason)
        else:
            for key in sorted(mix.counts, key=lambda k: (-mix.counts[k], k)):
                print("    %-20s %d" % (key, mix.counts[key]))
