"""Direction-generic two-token tag pairing (shared primitive SP-6).

Architectural drawing sets print a great many *two-token tags*: a material
callout is ``WC`` + ``07``, a room tag is ``QQ A`` + ``204``, a keynote is a
symbol letter + a number.  Every one of them is two short text lines drawn in a
fixed relationship to each other — and the relationship is expressed in the
**text's own reading frame**, not in page x/y.

This module owns that one relationship, once, for all three consumers
(``finish_tags``, ``room_tags``, and the keynote pairing of plan 23-14).

Why it has to be direction-generic
----------------------------------
``INV-05-finish-schedule-binding.md`` §2 Key A records the same Moxy material
tag drawn two ways.  On page index 15 the text is rotated (``dir=(0,-1)``) and
the tokens advance in −y::

    'WC'  (116.6, 2123.2, 128.3, 2138.5)  dir=(0,-1)
    '01'  (116.6, 2103.0, 128.3, 2112.5)  dir=(0,-1)

On page index 18 the same tag is unrotated (``dir=(1,0)``) and the tokens
advance in +x::

    'WC'  (908.4, 217.4, 923.7, 228.8)  dir=(1,0)
    '07'  (934.2, 217.4, 943.6, 228.8)  dir=(1,0)

A reader written against the first layout alone finds tags on pages 15/16 and
returns **nothing** on pages 18/19/20 — that is the bug a naive implementation
ships, and it silently loses 2,742 SF of the estimator's own quantity.
:func:`project_bbox` removes the choice: it rotates a bounding box into the
line's own ``(reading, advance)`` frame, so both layouts are the *same*
measurement.

Two adjacency axes, one projection
----------------------------------
Once boxes are in the reading frame there are exactly two ways two tokens can
sit next to each other, and real drawings use both:

* :data:`ALONG` — the second token follows the first *in reading order*
  (``WC`` then ``07``).  This is the material-tag layout above.
* :data:`ACROSS` — the second token is the *next text line* (a room tag prints
  the name over the number).  Measured on Moxy's ID-001/ID-002 unit key plans::

      'KING A'  (625.0, 1336.0, 636.7, 1369.4)  dir=(0,-1)
      '204'     (637.9, 1346.7, 649.6, 1358.5)  dir=(0,-1)

  In the reading frame the number is 1.2 pt further along the *advance* axis
  and overlaps the name on the reading axis.

Both axes use the one projection, so there is no second copy of the geometry.

This module is a PURE EXTRACTOR helper: it imports no pipeline and no fusion
code, and it never invents a quantity.  Pairing a tag says a tag was *printed*;
it says nothing about how much of anything was installed.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# ── Pinned adjacency constants ────────────────────────────────────────────────
#
# MAX_GAP_PT — the largest permitted gap between the two tokens, measured along
# whichever axis the caller pairs on.  Pinned at 16.0 pt from the MEASURED Moxy
# material-tag layouts (INV-05 §2 Key A): the observed intra-tag gap runs 10.5 pt
# (unrotated, page 18) to 14.4 pt (page 17) across all six interior-elevation
# sheets, so 16.0 leaves ~11% headroom for a slightly larger type size on
# another sheet.  It is deliberately NOT wider.  The finish-prefix registry
# contains one- and two-letter codes (``T``, ``SC``) and construction drawings
# are dense with stray two-digit numbers, so every extra point of gap
# manufactures finish codes that were never printed (INV-05 risk 2).  Tighten
# before loosening: the acceptance test is the exact per-sheet code SET, and a
# wider gap breaks it.
MAX_GAP_PT = 16.0

# PERP_TOL_PT — how far the two tokens may fail to overlap on the *other* axis
# and still be one tag.  Pinned at 3.0 pt.  On both measured layouts the two
# tokens share their off-axis range exactly (116.6–128.3 pt rotated,
# 217.4–228.8 pt unrotated), so this tolerance only has to absorb glyph-metric
# rounding between two differently-shaped tokens.  3.0 pt is below a third of
# the smallest observed token extent (9.5 pt), which is the geometric reason it
# is safe: a token belonging to the neighbouring text row cannot reach into the
# window without overlapping the row it actually belongs to.
PERP_TOL_PT = 3.0

# Axis selectors for :func:`pair_two_token_tags`.
ALONG = "along"    # second token follows the first in reading order
ACROSS = "across"  # second token is the next text line (advance direction)

# Spatial-index bucket, in points, on the axis the pair must OVERLAP on.
# Threat T-23-19: a sheet with several thousand text lines must not become a
# quadratic all-pairs scan.  Candidates are bucketed by their overlap-axis
# midpoint and each first token only examines its own bucket and the two
# neighbours, so the scan is linear in lines with a bounded constant.  64 pt of
# window (2 x 32) is an order of magnitude more than any observed tag extent.
_BUCKET_PT = 32.0

#: The four cardinal text directions PyMuPDF reports for a text line.
CARDINAL_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass(frozen=True)
class TagLine:
    """One text line considered as a possible tag token."""

    text: str
    bbox_pt: Tuple[float, float, float, float]  # (x0, y0, x1, y1) unrotated PDF points
    text_dir: Tuple[int, int]                   # rounded PyMuPDF line ``dir``
    page_index: int = 0


def round_dir(text_dir) -> Optional[Tuple[int, int]]:
    """Round a PyMuPDF line ``dir`` to a cardinal direction, or ``None``.

    Skewed text (a dir that is not within rounding distance of a cardinal) has
    no well-defined reading frame here and is dropped rather than guessed at.
    """
    try:
        dx = int(round(float(text_dir[0])))
        dy = int(round(float(text_dir[1])))
    except (TypeError, ValueError, IndexError):
        return None
    cand = (dx, dy)
    return cand if cand in CARDINAL_DIRS else None


def project_bbox(bbox, text_dir) -> Optional[Tuple[float, float, float, float]]:
    """Rotate *bbox* into the reading frame of a line drawn along *text_dir*.

    Returns ``(start, end, perp_lo, perp_hi)`` where ``start``/``end`` advance
    in **reading order** and ``perp_lo``/``perp_hi`` advance in the direction
    the drawing stacks successive text lines (i.e. reading-direction rotated a
    quarter turn clockwise in PDF page coordinates, where y grows downward).

    All four cardinal directions are handled by the same rule, which is the
    whole point of this function::

        (1, 0)   ->  ( x0,  x1,  y0,  y1)
        (-1, 0)  ->  (-x1, -x0, -y1, -y0)
        (0, -1)  ->  (-y1, -y0,  x0,  x1)
        (0, 1)   ->  ( y0,  y1, -x1, -x0)

    The negations are not cosmetic.  Without them a right-to-left or
    bottom-to-top line reports its tokens in the wrong order, and "the next
    token" silently becomes "the previous token".  Returns ``None`` for a
    non-cardinal direction.
    """
    d = round_dir(text_dir)
    if d is None:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    # Normalise a bbox drawn with inverted corners before rotating it.
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if d == (1, 0):
        return (x0, x1, y0, y1)
    if d == (-1, 0):
        return (-x1, -x0, -y1, -y0)
    if d == (0, -1):
        return (-y1, -y0, x0, x1)
    # d == (0, 1)
    return (y0, y1, -x1, -x0)


def page_tag_lines(page, page_index: Optional[int] = None) -> List[TagLine]:
    """Every non-empty text line on *page* as a :class:`TagLine`.

    Lines whose direction is not cardinal are dropped — they have no reading
    frame, so no adjacency statement about them would be meaningful.
    """
    if page_index is None:
        page_index = int(getattr(page, "number", 0) or 0)
    out: List[TagLine] = []
    try:
        blocks = page.get_text("dict")["blocks"]
    except Exception as exc:  # noqa: BLE001 — untrusted PDFs must not crash
        logger.warning("Text extraction failed on page %s: %s", page_index, exc)
        return out
    for block in blocks:
        for line in block.get("lines", []):
            text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if not text:
                continue
            d = round_dir(line.get("dir", (1.0, 0.0)))
            if d is None:
                continue
            try:
                bbox = tuple(float(v) for v in line["bbox"])
            except (KeyError, TypeError, ValueError):
                continue
            if len(bbox) != 4:
                continue
            out.append(TagLine(text=text, bbox_pt=bbox, text_dir=d, page_index=page_index))
    return out


def normalise_text(text: str) -> str:
    """Upper-case, whitespace-collapsed form used by every tag vocabulary."""
    return " ".join(str(text or "").upper().split())


def bbox_inside_any(bbox, rects: Sequence, margin: float = 1.0) -> bool:
    """True when *bbox* is contained in any rectangle of *rects*.

    Containment (not intersection) is deliberate: a mask that merely clips a
    plan-body tag must not delete it, but a tag drawn *within* a schedule table
    or a title block is not a plan-body callout at all.
    """
    try:
        bx0, by0, bx1, by1 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return False
    for rect in rects or ():
        try:
            rx0, ry0, rx1, ry1 = (float(v) for v in rect)
        except (TypeError, ValueError):
            continue
        if rx1 < rx0:
            rx0, rx1 = rx1, rx0
        if ry1 < ry0:
            ry0, ry1 = ry1, ry0
        if (
            bx0 >= rx0 - margin
            and by0 >= ry0 - margin
            and bx1 <= rx1 + margin
            and by1 <= ry1 + margin
        ):
            return True
    return False


def union_bbox(a, b) -> Tuple[float, float, float, float]:
    """The smallest box containing both token boxes — the tag's own bbox."""
    return (
        min(a[0], b[0]),
        min(a[1], b[1]),
        max(a[2], b[2]),
        max(a[3], b[3]),
    )


#: Viewport kinds whose contents are never plan-body callouts.
MASKED_VIEWPORT_KINDS = ("title_block", "legend", "schedule")


def sheet_mask_rects(page, schedule_bboxes: Sequence = ()) -> List[tuple]:
    """Rectangles on *page* whose contents must not be read as plan-body tags.

    These are the masks the deterministic bundle already computes: every
    schedule-table bbox from ``tables.extract_schedules`` plus every
    title-block / legend / schedule viewport from ``viewports.segment_viewports``.
    A door-schedule tag column and a finish legend key look exactly like a
    plan-body callout — the same false-positive class ``_is_door_table`` exists
    to reject — so these masks are MANDATORY for any consumer reading the plan
    body, not optional (INV-05 risk 3).

    Imports are local so this module stays importable with no PyMuPDF-dependent
    side effects and so it takes on no import cycle.
    """
    rects: List[tuple] = [tuple(b) for b in (schedule_bboxes or ()) if b]
    try:
        from bobbytailor.deterministic.viewports import segment_viewports

        for vp in segment_viewports(page, table_bboxes=list(rects) or None):
            if vp.kind in MASKED_VIEWPORT_KINDS:
                rects.append(tuple(vp.bbox_pt))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Viewport masking unavailable: %s", exc)
    return rects


def schedule_bboxes_by_page(doc) -> Dict[int, List[tuple]]:
    """``{page_index: [schedule bbox, ...]}`` for an open ``fitz.Document``."""
    out: Dict[int, List[tuple]] = {}
    try:
        from bobbytailor.deterministic.tables import extract_schedules

        for table in extract_schedules(doc):
            out.setdefault(int(table.page_index), []).append(tuple(table.bbox_pt))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Schedule masking unavailable: %s", exc)
    return out


def _axes(proj, axis: str) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Split a projection into (gap-axis, overlap-axis) ranges for *axis*."""
    if axis == ACROSS:
        return (proj[2], proj[3]), (proj[0], proj[1])
    return (proj[0], proj[1]), (proj[2], proj[3])


def pair_two_token_tags(
    lines: Sequence[TagLine],
    first_pred: Callable[[str], bool],
    second_pred: Callable[[str], bool],
    max_gap_pt: float = MAX_GAP_PT,
    perp_tol_pt: float = PERP_TOL_PT,
    axis: str = ALONG,
) -> List[Tuple[TagLine, TagLine]]:
    """Pair every ``first_pred`` line with the ``second_pred`` line beside it.

    A pair is admitted when **all four** hold:

    1. both lines carry the *same* text direction — a tag is one piece of text,
       so a rotated token never pairs with an unrotated one;
    2. the gap from the first token's end to the second token's start, measured
       on the chosen *axis* in the lines' own reading frame, is non-negative and
       below ``max_gap_pt``;
    3. the two tokens overlap on the other axis to within ``perp_tol_pt``;
    4. neither token is already spoken for — each line participates in at most
       one tag, so a single number cannot serve two prefixes.

    Where several candidates qualify the nearest one wins, ties broken by
    document order, so the result is deterministic.

    Returns ``[(first_line, second_line), ...]`` in document order.  It reports
    what is *printed*; deciding what a printed tag means is the caller's job.
    """
    if axis not in (ALONG, ACROSS):
        raise ValueError("axis must be %r or %r, got %r" % (ALONG, ACROSS, axis))

    # Index the second candidates by (direction, overlap-axis bucket) so the
    # scan is bounded rather than quadratic (threat T-23-19).
    buckets: Dict[Tuple[Tuple[int, int], int], List[int]] = {}
    projections: Dict[int, Tuple[float, float, float, float]] = {}
    second_ids: List[int] = []
    for idx, line in enumerate(lines):
        proj = project_bbox(line.bbox_pt, line.text_dir)
        if proj is None:
            continue
        projections[idx] = proj
        if not second_pred(line.text):
            continue
        second_ids.append(idx)
        _, overlap_range = _axes(proj, axis)
        mid = (overlap_range[0] + overlap_range[1]) / 2.0
        buckets.setdefault((line.text_dir, int(mid // _BUCKET_PT)), []).append(idx)

    taken: set = set()
    pairs: List[Tuple[TagLine, TagLine]] = []
    for idx, line in enumerate(lines):
        if idx in taken or idx not in projections or not first_pred(line.text):
            continue
        proj_f = projections[idx]
        gap_f, ov_f = _axes(proj_f, axis)
        mid = (ov_f[0] + ov_f[1]) / 2.0
        home = int(mid // _BUCKET_PT)
        best: Optional[Tuple[float, int]] = None
        for offset in (-1, 0, 1):
            for jdx in buckets.get((line.text_dir, home + offset), ()):
                if jdx == idx or jdx in taken:
                    continue
                gap_s, ov_s = _axes(projections[jdx], axis)
                gap = gap_s[0] - gap_f[1]
                if gap < 0.0 or gap >= max_gap_pt:
                    continue
                overlap = min(ov_f[1], ov_s[1]) - max(ov_f[0], ov_s[0])
                if overlap < -perp_tol_pt:
                    continue
                if best is None or gap < best[0] or (gap == best[0] and jdx < best[1]):
                    best = (gap, jdx)
        if best is None:
            continue
        taken.add(idx)
        taken.add(best[1])
        pairs.append((line, lines[best[1]]))
    return pairs


if __name__ == "__main__":  # quick measurement harness (free, no API)
    import sys

    import fitz

    _NUM = re.compile(r"^\d{2}[A-Z]?$")
    paths = sys.argv[1:] or [
        "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"
    ]
    for path in paths:
        doc = fitz.open(path)
        print("\n=== %s ===" % path.split("/")[-1])
        for page_index in range(doc.page_count):
            tag_lines = page_tag_lines(doc[page_index], page_index)
            dirs: Dict[Tuple[int, int], int] = {}
            for tl in tag_lines:
                dirs[tl.text_dir] = dirs.get(tl.text_dir, 0) + 1
            found = pair_two_token_tags(
                tag_lines,
                lambda t: len(t) <= 3 and t.isalpha(),
                lambda t: bool(_NUM.match(normalise_text(t))),
            )
            if found:
                print(
                    "  page %2d: %3d lines %s -> %d two-token pairs"
                    % (page_index, len(tag_lines), dict(sorted(dirs.items())), len(found))
                )
        doc.close()
