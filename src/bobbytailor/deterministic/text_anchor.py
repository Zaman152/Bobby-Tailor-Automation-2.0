"""Nearest-plan-text anchors for geometry candidates (V4-DET-01).

Why this is a NEW module and not more of ``tag_pairing``
--------------------------------------------------------
``tag_pairing`` answers exactly one question: *which two printed tokens form
one tag?*  Its inputs are text lines and its output is a statement about text.
This module answers a different question: *which printed text is nearest to
this piece of geometry?*  Its inputs are a candidate bbox plus the page's text,
and its output is a statement binding geometry to text.  Growing ``tag_pairing``
to hold both would give one module two subjects and two vocabularies.
24-RESEARCH section 10 challenges every new module in this phase; section 2.2
sanctions this one by name — *"What does NOT exist is a 'words within radius R
of this bbox, excluding masked rects, ranked by distance' primitive. That is
the one new deterministic function this requirement needs."*

It reuses rather than forks: masking is ``tag_pairing.bbox_inside_any`` over
``sheet_mask_rects``' rectangles, and two-token tags come from
``tag_pairing.pair_two_token_tags`` (SP-6), so a rotated sheet pairs correctly
here for free.

What an anchor is for
---------------------
The Set-of-Mark marker chip presently carries only the candidate ID
(``overlay.py:110``, ``label = candidate_id``).  That is the *symbol-conveyed*
condition the evidence base measures at 0.03-0.39 accuracy, against 0.65-0.92
for text-anchored classes.  An anchor record is the deterministic half of
closing that gap: it says which words the drawing itself printed next to this
geometry, computed with no model in the loop.

**An absence is a result.**  A candidate with no plan text inside the radius
carries ``anchor_text=None``.  It is never filled from the shape, never from
the candidate ID, and never from whichever word happened to be scanned first.
Deciding what to do with an unanchored candidate belongs to plan 24-04.

**Anchor harvesting is UNFILTERED.**  The drafting-noise predicate in
``vision/fusion.py`` must not be reused here, and this module deliberately does
not import it.  It answers a different question (is this cluster's own contained
text an object name?) and it returns True for precisely the tags an anchor
needs: ``"B-1"`` matches its sheet-id pattern and ``"P1"`` matches its
gridline-label pattern.  Filtering anchors through it would reject the anchors
this requirement exists to harvest.  Whether an anchored name is *publishable*
is a separate decision, made later, by plan 24-04.

Every public function here is pure over its inputs plus the ``fitz.Page`` text
layer.  No API, no network, no environment read, no file written.

A measured finding this module is sized against
-----------------------------------------------
A zero-API deterministic-bundle probe over all four Crow sheets (Phase 24
planning, 2026-08-05) returns 107 symbol groups.  **81 carry no
``contained_texts`` at all**, 26 carry pure drafting noise, and **0 carry a
genuine object name**.  The 56-EA bollard candidate is page-0 ``SYM-2`` and the
136 candidate is ``SYM-1``; both have zero contained text.  So on the mission's
primary plan set the ``contained`` branch below contributes *nothing*, and the
nearest-non-masked-word query is not an enhancement to the anchor ladder — it
IS the anchor ladder.
"""
from __future__ import annotations

import logging
import math
import re
import statistics
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bobbytailor.deterministic.tag_pairing import (
    ALONG,
    bbox_inside_any,
    page_tag_lines,
    pair_two_token_tags,
    union_bbox,
)

logger = logging.getLogger(__name__)

Box = Tuple[float, float, float, float]
#: One anchor candidate: its box, the text printed in it, and its document order.
Unit = Tuple[Box, str, int]

# ── The search radius, chosen from PAGE GEOMETRY ──────────────────────────────
#
# ANCHOR_RADIUS_TEXT_HEIGHTS — the rule.  A label a draughtsman intends to be
# read as belonging to a piece of geometry is set beside it, within a few
# text-heights.  Past roughly four text-heights a human reader cannot attribute
# the label without following a leader line, and this module does not read
# leader lines.  Four is therefore the geometric limit of an *unleadered*
# callout, not a fitted number.
#
# It is expressed in TEXT HEIGHTS, not points, because the measured drafting
# text height varies 3.5x across this project's four plan sets while every one
# of them prints on the identical 3024 x 2160 pt sheet (measured free, this
# session, over `page.get_text("words")`):
#
#     Crow     median word height  9.56 pt
#     Moxy     median word height  9.64 pt
#     Chelsea  median word height  7.56 pt
#     Bob's    median word height 26.41 pt
#
# A single absolute radius is therefore ~5 text-heights of reach on Chelsea and
# ~1.4 on Bob's.  `tests/test_four_set_coverage.py`'s own docstring records what
# that class of constant costs: sweeping the title-block width fraction fixed
# Moxy and broke Chelsea, and nothing caught it because nothing looked at
# Chelsea.  `anchors_for_candidates` therefore derives the radius from the
# median word height of the page it was handed (`page_radius_pt`), and the
# absolute constant below is the FALLBACK for a page whose text layer is empty.
#
# NOTHING here may ever be selected by running a take-off and watching an
# accuracy score move (24-RESEARCH pitfall 1).  The validation for this rule is
# positional: the word it selects must be the geometrically nearest non-masked
# word, provable by hand on a real page.
ANCHOR_RADIUS_TEXT_HEIGHTS = 4.0

#: Median annotation word height on Crow and Moxy, measured this session.
NOMINAL_TEXT_HEIGHT_PT = 9.5

#: Fallback radius for a page with no measurable text (4 x 9.5 pt).
ANCHOR_RADIUS_PT = ANCHOR_RADIUS_TEXT_HEIGHTS * NOMINAL_TEXT_HEIGHT_PT

# Spatial-index cell, in points.  Threat T-24-03: Crow page 1 carries 56 symbol
# groups plus 156 room candidates against a few thousand words, and an
# all-pairs scan is quadratic.  Words are indexed by the cells their box
# overlaps and a candidate only visits the cells its own box (grown by the
# radius) overlaps, mirroring `pair_two_token_tags`' bucketing at
# tag_pairing.py:333.
_CELL_PT = 64.0

# Generic two-token tag shape for the SP-6 pairer: a short alphabetic prefix
# followed, in the text's own reading direction, by a short number.  This is
# deliberately NOT the noise predicate — see the module docstring.
_TAG_PREFIX_RE = re.compile(r"^[A-Z]{1,3}$")
_TAG_NUMBER_RE = re.compile(r"^\d{1,3}[A-Z]?$")

#: Anchor kinds, in precedence order.  ``None`` is a fourth, honest outcome.
KIND_CONTAINED = "contained"
KIND_TAG = "tag"
KIND_NEAREST_WORD = "nearest_word"

SOURCE_PAGE_WORDS = "page_words"
SOURCE_TAG_PAIRING = "tag_pairing"


# ── The record ────────────────────────────────────────────────────────────────


def anchor_record(
    candidate_id: str,
    text: Optional[str],
    kind: Optional[str],
    dist_pt: Optional[float],
    source: Optional[str],
    ambiguity_reason: str = "",
) -> dict:
    """The per-candidate anchor record (24-RESEARCH section 2.3).

    A plain dict of JSON-serialisable scalars, so it survives into the
    deterministic bundle, into ``takeoff.json`` and into a committed fixture
    without a codec.

    ``anchor_text is None`` is the recorded ABSENCE of an anchor.  It is a
    result in its own right, never a placeholder to be filled in later from the
    candidate's shape.
    """
    return {
        "candidate_id": str(candidate_id or ""),
        "anchor_text": None if text is None else str(text),
        "anchor_kind": None if kind is None else str(kind),
        "anchor_dist_pt": None if dist_pt is None else round(float(dist_pt), 3),
        "anchor_source": None if source is None else str(source),
        "ambiguity_reason": str(ambiguity_reason or ""),
    }


# ── Geometry helpers ──────────────────────────────────────────────────────────


def _norm_box(bbox) -> Optional[Box]:
    """``(x0, y0, x1, y1)`` with corners ordered, or ``None`` if unreadable."""
    try:
        x0, y0, x1, y1 = (float(v) for v in tuple(bbox)[:4])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        return None
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def box_distance_pt(a: Box, b: Box) -> float:
    """Edge-to-edge distance between two boxes; ``0.0`` when they overlap."""
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def _centre_inside(item: Box, box: Box) -> bool:
    """True when *item*'s centre lies within *box*.

    Centre-in-box (not intersection) mirrors ``symbols._texts_in_bbox``, so
    "contained" means the same thing here as it does where ``contained_texts``
    is populated.
    """
    cx = (item[0] + item[2]) / 2.0
    cy = (item[1] + item[3]) / 2.0
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


# ── Text harvest ──────────────────────────────────────────────────────────────


def page_words(page) -> List[Tuple[float, float, float, float, str]]:
    """Every non-empty word on *page* as ``(x0, y0, x1, y1, text)``.

    Mirrors ``symbols._page_words`` (``page.get_text("words")``) rather than
    inventing a second harvest shape, and tolerates PyMuPDF's longer 8-tuple.
    An unreadable text layer yields ``[]`` — a page with no words, never a
    crash on an untrusted PDF.
    """
    try:
        raw = page.get_text("words") or []
    except Exception as exc:  # noqa: BLE001 — untrusted PDFs must not crash
        logger.warning("Word extraction failed: %s", exc)
        return []
    out: List[Tuple[float, float, float, float, str]] = []
    for word in raw:
        try:
            text = str(word[4]).strip()
        except (IndexError, TypeError):
            continue
        if not text:
            continue
        box = _norm_box(word)
        if box is None:
            continue
        out.append((box[0], box[1], box[2], box[3], text))
    return out


def page_tag_units(page) -> List[Tuple[float, float, float, float, str]]:
    """Every two-token tag printed on *page*, as one ``(x0,y0,x1,y1,text)`` each.

    Pairing is delegated to ``tag_pairing.pair_two_token_tags`` on the ``ALONG``
    axis — the callout layout, where the number follows the prefix in the
    text's own reading direction.  That is why a rotated sheet works here with
    no second code path (SP-6; tag_pairing's module docstring records the bug a
    naive y-stacking reader ships).  The ``ACROSS`` axis is deliberately not
    harvested: it is the room-tag stacking layout, and ``room_tags`` already
    owns it.
    """
    try:
        lines = page_tag_lines(page)
        pairs = pair_two_token_tags(
            lines,
            lambda t: bool(_TAG_PREFIX_RE.match(str(t).strip().upper())),
            lambda t: bool(_TAG_NUMBER_RE.match(str(t).strip().upper())),
            axis=ALONG,
        )
    except Exception as exc:  # noqa: BLE001 — tags are additive to the harvest
        logger.warning("Tag pairing unavailable: %s", exc)
        return []
    out: List[Tuple[float, float, float, float, str]] = []
    for first, second in pairs:
        box = _norm_box(union_bbox(first.bbox_pt, second.bbox_pt))
        if box is None:
            continue
        text = "%s %s" % (str(first.text).strip(), str(second.text).strip())
        out.append((box[0], box[1], box[2], box[3], text))
    return out


def page_radius_pt(
    words: Sequence, text_heights: float = ANCHOR_RADIUS_TEXT_HEIGHTS
) -> float:
    """The anchor radius for a page, in points, from its own text height.

    ``median(word height) * text_heights``.  The median is used rather than the
    mean because a sheet's title block prints at 87 pt against a 9.5 pt body on
    Crow, and one giant title must not move the radius.  A page with no
    measurable text falls back to :data:`ANCHOR_RADIUS_PT`.
    """
    heights = []
    for word in words or ():
        box = _norm_box(word)
        if box is None:
            continue
        height = box[3] - box[1]
        if height > 0.0:
            heights.append(height)
    if not heights:
        return float(ANCHOR_RADIUS_PT)
    return float(statistics.median(heights)) * float(text_heights)


# ── Spatial index ─────────────────────────────────────────────────────────────


class _Grid:
    """Uniform-cell index over anchor units (threat T-24-03)."""

    def __init__(self, units: Sequence[Unit], cell_pt: float = _CELL_PT):
        self._cell = float(cell_pt) or _CELL_PT
        self.units: List[Unit] = list(units)
        self._cells: Dict[Tuple[int, int], List[int]] = {}
        for idx, (box, _text, _order) in enumerate(self.units):
            for key in self._keys(box, 0.0):
                self._cells.setdefault(key, []).append(idx)

    def _keys(self, box: Box, pad: float) -> Iterable[Tuple[int, int]]:
        cell = self._cell
        i0 = int(math.floor((box[0] - pad) / cell))
        i1 = int(math.floor((box[2] + pad) / cell))
        j0 = int(math.floor((box[1] - pad) / cell))
        j1 = int(math.floor((box[3] + pad) / cell))
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                yield (i, j)

    def near(self, box: Box, pad: float) -> List[int]:
        """Indices of every unit whose cell is within *pad* of *box*."""
        seen = set()
        for key in self._keys(box, pad):
            for idx in self._cells.get(key, ()):
                seen.add(idx)
        return sorted(seen)


def _as_units(seq: Sequence, mask_rects: Sequence = ()) -> List[Unit]:
    """``(x0,y0,x1,y1,text)`` tuples -> units, dropping masked and malformed.

    Masking uses ``tag_pairing.bbox_inside_any``, i.e. CONTAINMENT: a word
    drawn inside a schedule table or a title block is not a plan-body callout
    and can never become an anchor, however near it happens to sit.  A mask that
    merely clips a plan-body word does not delete it.
    """
    rects = [r for r in (mask_rects or ()) if r]
    units: List[Unit] = []
    for order, item in enumerate(seq or ()):
        box = _norm_box(item)
        if box is None:
            continue
        try:
            text = str(item[4]).strip()
        except (IndexError, TypeError):
            continue
        if not text:
            continue
        if rects and bbox_inside_any(box, rects):
            continue
        units.append((box, text, order))
    return units


def _nearest_unit(
    grid: _Grid, box: Box, radius_pt: float
) -> Optional[Tuple[float, int, str]]:
    """``(distance, document order, text)`` of the nearest unit within radius.

    Ties are broken by document order, so the same page and bbox always yield
    the same anchor.  Distances are rounded before comparison so two
    mathematically-equal distances cannot be separated by float jitter.
    """
    best: Optional[Tuple[Tuple[float, int], str]] = None
    for idx in grid.near(box, radius_pt):
        unit_box, text, order = grid.units[idx]
        dist = box_distance_pt(box, unit_box)
        if dist > radius_pt:
            continue
        key = (round(dist, 6), order)
        if best is None or key < best[0]:
            best = (key, text)
    if best is None:
        return None
    return (best[0][0], best[0][1], best[1])


def _resolve(
    candidate_id: str,
    bbox_pt,
    word_grid: _Grid,
    tag_grid: _Grid,
    radius_pt: float,
) -> Tuple[dict, Optional[Tuple[str, int]]]:
    """One candidate's anchor, plus the identity of the unit it claimed.

    Precedence: contained word -> two-token tag within radius -> nearest single
    word within radius -> recorded absence.  A paired tag outranks a nearer
    loose word because a tag is a printed IDENTIFIER, whereas a loose word may
    be a fragment of a dimension string; the radius is what bounds the reach of
    either.
    """
    box = _norm_box(bbox_pt)
    if box is None:
        logger.debug("candidate %r carries no usable bbox", candidate_id)
        return anchor_record(candidate_id, None, None, None, None), None

    # 1. Contained: a word whose centre lies inside the candidate's own box.
    contained: Optional[Tuple[int, str]] = None
    for idx in word_grid.near(box, 0.0):
        unit_box, text, order = word_grid.units[idx]
        if _centre_inside(unit_box, box) and (
            contained is None or order < contained[0]
        ):
            contained = (order, text)
    if contained is not None:
        return (
            anchor_record(
                candidate_id, contained[1], KIND_CONTAINED, 0.0, SOURCE_PAGE_WORDS
            ),
            ("word", contained[0]),
        )

    # 2. A two-token tag within the radius, returned as ONE anchor.
    hit = _nearest_unit(tag_grid, box, radius_pt)
    if hit is not None:
        dist, order, text = hit
        return (
            anchor_record(candidate_id, text, KIND_TAG, dist, SOURCE_TAG_PAIRING),
            ("tag", order),
        )

    # 3. The nearest single non-masked word within the radius.
    hit = _nearest_unit(word_grid, box, radius_pt)
    if hit is not None:
        dist, order, text = hit
        return (
            anchor_record(
                candidate_id, text, KIND_NEAREST_WORD, dist, SOURCE_PAGE_WORDS
            ),
            ("word", order),
        )

    # 4. No text in range.  The absence is the answer.
    return anchor_record(candidate_id, None, None, None, None), None


# ── Public entry points ───────────────────────────────────────────────────────


def nearest_anchor(
    bbox_pt,
    words: Sequence,
    mask_rects: Sequence = (),
    radius_pt: float = ANCHOR_RADIUS_PT,
    tag_pairs: Sequence = (),
    candidate_id: str = "",
) -> dict:
    """The anchor record for one bbox against one page's text.

    *words* and *tag_pairs* are both sequences of ``(x0, y0, x1, y1, text)``;
    PyMuPDF's longer word tuples are accepted unchanged.  Words lying inside any
    rectangle of *mask_rects* are never returned.

    This is the pure primitive: it takes an explicit *radius_pt* and builds its
    own index, so a single call is self-contained and hand-provable.
    :func:`anchors_for_candidates` is the page-scale entry point and shares one
    index across every candidate.
    """
    word_units = _as_units(words, mask_rects)
    tag_units = _as_units(tag_pairs, mask_rects)
    record, _claim = _resolve(
        candidate_id,
        bbox_pt,
        _Grid(word_units),
        _Grid(tag_units),
        float(radius_pt),
    )
    return record


def anchors_for_candidates(
    page,
    candidates: Dict[str, tuple],
    mask_rects: Sequence = (),
    radius_pt: Optional[float] = None,
) -> Dict[str, dict]:
    """``{candidate_id: anchor_record}`` for every candidate on *page*.

    *candidates* is ``{candidate_id: bbox_pt}``.  The page's words and tags are
    harvested ONCE, masked ONCE and indexed ONCE; candidates are then resolved
    in candidate-ID order so the scan order is fixed and the result is
    byte-identical on repeated calls.

    *radius_pt* defaults to the page's own :func:`page_radius_pt`.  Pass a float
    to pin it (a test proving a positional claim by hand should).

    **Ambiguity is a flag, never a tiebreak.**  After the first pass, any text
    unit claimed by more than one candidate is WITHDRAWN from all of its
    claimants; each is re-emitted as a recorded absence naming the contested
    text and the competing candidate IDs.  This is SP-7c ``bind_or_flag``: bind
    only when exactly one candidate and exactly one surviving text remain.
    Names are never round-robined to whichever candidate was scanned first.
    """
    words = page_words(page)
    radius = page_radius_pt(words) if radius_pt is None else float(radius_pt)

    tags = page_tag_units(page)
    tag_units = _as_units(tags, mask_rects)
    # A word already spoken for by a two-token tag must not also be offered as
    # a loose single word, or a lone "B" could anchor a candidate whose drawing
    # actually prints "B 1".
    tag_boxes = [unit[0] for unit in tag_units]
    if tag_boxes:
        words = [w for w in words if not bbox_inside_any(w[:4], tag_boxes)]
    word_units = _as_units(words, mask_rects)

    word_grid = _Grid(word_units)
    tag_grid = _Grid(tag_units)

    records: Dict[str, dict] = {}
    claims: Dict[Tuple[str, int], List[str]] = {}
    for cid in sorted(candidates or {}):
        record, claim = _resolve(
            str(cid), candidates[cid], word_grid, tag_grid, radius
        )
        records[str(cid)] = record
        if claim is not None:
            claims.setdefault(claim, []).append(str(cid))

    for claim in sorted(claims):
        claimants = sorted(claims[claim])
        if len(claimants) < 2:
            continue
        contested = records[claimants[0]].get("anchor_text")
        reason = (
            "anchor text %r is the nearest anchor for %d candidates (%s); "
            "bound to none" % (contested, len(claimants), ", ".join(claimants))
        )
        for cid in claimants:
            records[cid] = anchor_record(cid, None, None, None, None, reason)

    return records
