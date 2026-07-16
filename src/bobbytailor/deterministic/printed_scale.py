"""Printed-scale reading (PRIMARY per-viewport scale source).

Every architectural drawing prints its OWN scale label — e.g.
``SCALE: 1" = 40'-0"`` under the main plan, ``SCALE: 1 1/2" = 1'-0"`` under a
detail — usually accompanied by the drawing number and title. That printed
label IS the ground-truth scale the draughtsman used; reading it directly is
more reliable than inferring scale from dimension geometry (the RANSAC solver
in ``scale_solver``), which can be fooled by mispairings and detail-scale
contamination.

This module reads the printed label off ``page.get_text("blocks")`` and binds
each label to the viewport it belongs to (labels sit at a drawing's BOTTOM).
It is ADDITIVE: it never mutates geometry and never raises on a weird label —
a parse failure returns ``None`` and is skipped, leaving the RANSAC path to
behave exactly as before.

Priority chain (wired in ``scale_solver.resolve_scale_v2``):

    override > printed scale label (this module) > dimension-RANSAC-solved
             > printed-dominant heuristic > learned prior

When a viewport has a matched printed scale the solver adopts its
feet-per-point with source ``"printed_label"`` and confidence ``"high"``, and
records the RANSAC-solved value alongside as a CROSS-CHECK — a disagreement
> 5% keeps the printed value but flags ``needs_review`` in the detail string.

Coordinate space: PyMuPDF text/block coordinates are UNROTATED page points,
consistent with ``viewports.Viewport.bbox_pt``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

POINTS_PER_INCH = 72.0

# Viewport kinds that are never the drawing a scale label describes.
_MASK_KINDS = ("title_block", "legend", "schedule")

# Main-plan title patterns (case-insensitive), best first. A label whose title
# matches one of these — and NONE of the detail patterns — is a plan candidate.
_MAIN_PATTERNS = (
    "overall floor plan",
    "floor plan",
    "site plan",
    "overall plan",
    "key plan",
)
_DETAIL_PATTERNS = (
    "detail",
    "section",
    "typ",
    "corner",
    "joint",
    "elevation",
)

# Real-world feet side, e.g. "40'-0"" -> 40.0, "1'-0"" -> 1.0, "20'" -> 20.0.
_FEET_RE = re.compile(r"(\d+)\s*'\s*-?\s*(\d+)?\s*\"?")


@dataclass
class PrintedScale:
    """One printed scale label bound to a drawing on the sheet."""

    scale_text: str
    feet_per_inch: float
    feet_per_point: float
    center_pt: Tuple[float, float]
    bbox_pt: Tuple[float, float, float, float]
    drawing_number: Optional[str]
    title: str

    def to_dict(self) -> dict:
        return {
            "scale_text": self.scale_text,
            "feet_per_inch": self.feet_per_inch,
            "feet_per_point": self.feet_per_point,
            "center_pt": self.center_pt,
            "bbox_pt": self.bbox_pt,
            "drawing_number": self.drawing_number,
            "title": self.title,
        }


# ── Text normalisation ────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Fold smart quotes / primes to ASCII and collapse whitespace runs."""
    if not text:
        return ""
    trans = {
        "‘": "'", "’": "'", "′": "'",   # ‘ ’ ′  -> '
        "“": '"', "”": '"', "″": '"',   # “ ” ″  -> "
        "–": "-", "—": "-", "−": "-",   # – — −  -> -
        " ": " ",                                   # nbsp   -> space
    }
    out = text.translate({ord(k): v for k, v in trans.items()})
    return out


# ── Ratio parsing ─────────────────────────────────────────────────────────────


# Dropped-slash fraction repair (CAD PDFs with STACKED fraction glyphs).
#
# Many CAD exports typeset the fraction in a scale callout as a single stacked
# glyph in its own text span. The PDF text layer then flattens it to the bare
# digits and the slash is GONE:
#
#     spans: ['SCALE: ', '18', '" = 1\'-0"']      # really 1/8" = 1'-0"
#
# Parsed literally that reads "18 paper inches = 1 foot" -> 0.056 ft/in instead
# of 8.0 — a 144x scale error that would corrupt every quantity on the sheet.
# (Crow's PDF writes literal slashes and never hits this; Bob's does.)
#
# The repair is unambiguous because the literal readings are architecturally
# absurd: no drawing is labelled "18 inches = 1 foot" (1.5x life size). Each key
# below is the digit-concatenation of a STANDARD architectural scale fraction,
# and every one is an impossible paper-inch measure, so the mapping cannot
# silently rewrite a legitimate value.
_DROPPED_SLASH_FRACTIONS = {
    "132": 1 / 32,
    "116": 1 / 16,
    "332": 3 / 32,
    "316": 3 / 16,
    "18": 1 / 8,
    "14": 1 / 4,
    "38": 3 / 8,
    "12": 1 / 2,
    "34": 3 / 4,
    "58": 5 / 8,
}


def _paper_inches(text_before_eq: str) -> Optional[float]:
    """Parse the drawing-inch side left of '=' -> paper inches.

    Handles mixed numbers ("1 1/2"), plain fractions ("3/32", "1/4"), whole or
    decimal inches ("1", "1.5"), and stacked-fraction glyphs whose slash the PDF
    text layer dropped ("18" -> 1/8; see :data:`_DROPPED_SLASH_FRACTIONS`).
    Non-digit tokens (e.g. "SCALE:") are ignored.
    """
    s = text_before_eq
    # Mixed number: "1 1/2" -> 1.5
    m = re.search(r"(\d+)\s+(\d+)\s*/\s*(\d+)", s)
    if m:
        den = int(m.group(3))
        if den:
            return int(m.group(1)) + int(m.group(2)) / den
        return None
    # Plain fraction: "3/32" -> 0.09375
    m = re.search(r"(\d+)\s*/\s*(\d+)", s)
    if m:
        den = int(m.group(2))
        if den:
            return int(m.group(1)) / den
        return None
    # Whole or decimal inches: "1", "1.5" — but first repair a stacked fraction
    # whose slash the text layer dropped ("18" is 1/8, never 18 paper inches).
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if m:
        token = m.group(1)
        if token in _DROPPED_SLASH_FRACTIONS:
            return _DROPPED_SLASH_FRACTIONS[token]
        try:
            return float(token)
        except ValueError:
            return None
    return None


def _real_feet(text_after_eq: str) -> Optional[float]:
    """Parse the real-world side right of '=' -> feet ("1'-0"" -> 1.0)."""
    m = _FEET_RE.search(text_after_eq)
    if not m:
        return None
    feet = int(m.group(1))
    inches = int(m.group(2)) if m.group(2) else 0
    return feet + inches / 12.0


def parse_scale_ratio(text: str) -> Optional[float]:
    """Parse a printed scale notation -> FEET PER INCH, or ``None``.

    General rule ``A" = B'`` -> ``feet_per_inch = B / A`` where A is the
    drawing-inch value left of '=' and B is the real-world feet right of '='.
    Examples: ``1" = 40'-0"`` -> 40.0, ``1/4" = 1'-0"`` -> 4.0,
    ``1 1/2" = 1'-0"`` -> 0.6667, ``3/32" = 1'-0"`` -> 10.667,
    ``1" = 20'`` -> 20.0. Robust to whitespace, smart quotes, ``-0"``
    suffixes and a leading ``SCALE:`` prefix. Returns ``None`` on any form
    that does not yield a positive ratio (never raises).
    """
    if not text:
        return None
    try:
        t = _normalize(text)
        if "=" not in t:
            return None
        left, right = t.split("=", 1)
        paper_in = _paper_inches(left)
        feet = _real_feet(right)
        if not paper_in or paper_in <= 0:
            return None
        if feet is None or feet <= 0:
            return None
        return feet / paper_in
    except Exception:  # noqa: BLE001 — a weird label must never break a run
        return None


# ── Drawing number + title ────────────────────────────────────────────────────


def _number_and_title(text: str) -> Tuple[Optional[str], str]:
    """Extract the drawing number (a lone integer) and descriptive title.

    Architectural labels read ``SCALE: 1" = 40'-0"  1  OVERALL FLOOR PLAN`` —
    the drawing number is a lone integer sitting between the ratio and the
    title. Scan the block text with the whole scale expression removed; the
    first standalone integer is the number, the remaining words are the title.
    """
    t = _normalize(text)
    # Strip the "SCALE ... = X'-Y"" expression so its digits are not mistaken
    # for the drawing number.
    stripped = t
    if "=" in t:
        left, right = t.split("=", 1)
        fm = _FEET_RE.search(right)
        right_rem = right[fm.end():] if fm else right
        # Drop the "SCALE" keyword and paper-inch fragment from the left side.
        left_rem = re.sub(r"(?i)scale", " ", left)
        left_rem = re.sub(r"\d+(?:\s+\d+\s*/\s*\d+|\s*/\s*\d+|\.\d+)?\s*\"?", " ", left_rem)
        stripped = left_rem + " " + right_rem

    number: Optional[str] = None
    title_tokens: List[str] = []
    for raw in stripped.split():
        tok = raw.strip(".,:;-|/")
        if not tok:
            continue
        if number is None and tok.isdigit():
            number = tok
            continue
        title_tokens.append(raw.strip())
    title = " ".join(title_tokens).strip(" .,:;-|/")
    return number, title


# ── Extraction ────────────────────────────────────────────────────────────────


def _page_blocks(page) -> List[tuple]:
    """Text blocks as (x0, y0, x1, y1, text, ...), best effort."""
    try:
        blocks = page.get_text("blocks") or []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for b in blocks:
        try:
            x0, y0, x1, y1, text = float(b[0]), float(b[1]), float(b[2]), float(b[3]), b[4]
        except (TypeError, ValueError, IndexError):
            continue
        # Block type (index 6) 1 == image; keep text blocks only when present.
        if len(b) >= 7 and b[6] not in (0, None):
            continue
        out.append((x0, y0, x1, y1, str(text)))
    return out


# The canonical architectural scale ratio, WITHOUT the word "SCALE":
#   1/4" = 1'-0"   3/32" = 1'-0"   1 1/2" = 1'-0"   1" = 40'-0"   1" = 20'
# Requiring the literal word "SCALE" hardcodes one CAD template's habit: Crow
# writes `SCALE: 1" = 40'-0" 1 OVERALL FLOOR PLAN` in a single block, but Moxy
# prints the bare ratio on its own line under the viewport title — so every
# scale on all 40 Moxy sheets was discarded and the engine had NO scale at all.
# This pattern is specific enough to be safe: it needs a paper-inch measure, an
# '=', and a feet-and-inches value. Dimension strings ("12'-6\"") carry no '='.
_BARE_RATIO_RE = re.compile(
    r"""(?:\d+\s+)?          # optional whole part of a mixed number ("1 1/2")
        \d+(?:\s*/\s*\d+)?   # inches, plain or fraction
        \s*["″”]   # inch mark (straight or curly)
        \s*=\s*
        \d+\s*['′’]  # feet mark
    """,
    re.VERBOSE,
)


def _looks_like_scale_label(text: str) -> bool:
    """True when a block is a scale callout — by keyword OR by bare ratio form."""
    if "SCALE" in text.upper():
        return True
    return bool(_BARE_RATIO_RE.search(_normalize(text)))


def _title_above(blocks: List[tuple], x0: float, y0: float, x1: float) -> str:
    """Nearest text line directly ABOVE a bare ratio — its viewport title.

    Moxy stacks the callout as two lines ("KING SUITE B - AR PLAN" / "1/4\" =
    1'-0\""), so the title the main-plan picker needs lives in the previous
    block, not in the ratio block itself.
    """
    best, best_gap = "", None
    for bx0, by0, bx1, by1, btext in blocks:
        txt = " ".join(_normalize(btext).split())
        if not txt or _looks_like_scale_label(btext):
            continue
        gap = y0 - by1                      # block sits above the ratio
        if gap < -2.0 or gap > _TITLE_MAX_GAP_PT:
            continue
        if bx1 < x0 - _TITLE_X_TOL_PT or bx0 > x1 + _TITLE_X_TOL_PT:
            continue                        # not horizontally aligned with it
        if best_gap is None or gap < best_gap:
            best, best_gap = txt, gap
    return best


# A stacked title sits within ~2 text lines above its ratio, roughly x-aligned.
_TITLE_MAX_GAP_PT = 40.0
_TITLE_X_TOL_PT = 120.0


def extract_printed_scales(page) -> List[PrintedScale]:
    """Read every printed scale label on *page* -> one PrintedScale per label.

    Accepts BOTH printed forms: a block mentioning ``SCALE`` (Crow), and a bare
    architectural ratio on its own line (Moxy), whose title is then taken from
    the line directly above. Records feet-per-inch, feet-per-point, center,
    bbox, drawing number and title. Never raises — a defective page yields an
    empty list and the caller falls back to RANSAC unchanged.
    """
    out: List[PrintedScale] = []
    blocks = _page_blocks(page)
    for x0, y0, x1, y1, text in blocks:
        if not _looks_like_scale_label(text):
            continue
        fpi = parse_scale_ratio(text)
        if not fpi or fpi <= 0:
            continue
        number, title = _number_and_title(text)
        if not title:
            # Bare ratio ("1/4\" = 1'-0\"") — its title is the line above.
            title = _title_above(blocks, x0, y0, x1)
            if not number:
                number, _t = _number_and_title(title)
        out.append(
            PrintedScale(
                scale_text=" ".join(_normalize(text).split()),
                feet_per_inch=fpi,
                feet_per_point=fpi / POINTS_PER_INCH,
                center_pt=((x0 + x1) / 2.0, (y0 + y1) / 2.0),
                bbox_pt=(x0, y0, x1, y1),
                drawing_number=number,
                title=title,
            )
        )
    return out


# ── Viewport binding ──────────────────────────────────────────────────────────


def _area(bbox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _contains(bbox, x: float, y: float, margin: float = 0.0) -> bool:
    return (
        bbox[0] - margin <= x <= bbox[2] + margin
        and bbox[1] - margin <= y <= bbox[3] + margin
    )


def match_scales_to_viewports(
    printed_scales: Sequence[PrintedScale],
    viewports: Sequence,
) -> Dict[str, PrintedScale]:
    """Bind each printed scale to its drawing viewport -> {region_id: scale}.

    A label binds to the viewport whose bbox CONTAINS the label center (the
    smallest such, so a detail nested in a plan wins); failing containment, to
    the nearest viewport whose region sits directly ABOVE the label (scale
    labels sit at a drawing's bottom edge). Mask regions (title block, legend,
    schedule) are never drawing owners. Deterministic and tolerant of a label
    that sits slightly outside its bbox.
    """
    candidates = [vp for vp in viewports if getattr(vp, "kind", "") not in _MASK_KINDS]
    result: Dict[str, PrintedScale] = {}
    dist_by_region: Dict[str, float] = {}

    for ps in printed_scales:
        cx, cy = ps.center_pt
        target = None
        dist = 0.0

        containing = [
            vp for vp in candidates if _contains(vp.bbox_pt, cx, cy, margin=6.0)
        ]
        if containing:
            target = min(containing, key=lambda vp: (_area(vp.bbox_pt), vp.region_id))
            dist = 0.0
        else:
            best = None
            best_d = float("inf")
            for vp in candidates:
                x0, y0, x1, y1 = vp.bbox_pt
                # x-overlap with the label center and the region above it.
                if x0 - 6.0 <= cx <= x1 + 6.0 and y1 <= cy + 6.0:
                    d = cy - y1
                    if d < best_d or (d == best_d and best is not None
                                      and vp.region_id < best.region_id):
                        best_d, best = d, vp
            if best is not None:
                target, dist = best, best_d

        if target is None:
            continue
        rid = target.region_id
        if rid not in result or dist < dist_by_region.get(rid, float("inf")):
            result[rid] = ps
            dist_by_region[rid] = dist
    return result


def identify_main_plan_scale(
    printed_scales: Sequence[PrintedScale],
) -> Optional[PrintedScale]:
    """Pick the printed scale of the main measurement plan, or ``None``.

    A candidate's title matches an OVERALL/FLOOR/SITE PLAN pattern and NONE of
    the detail/section/elevation patterns. "Overall floor plan" is preferred;
    ties break by the larger label bbox area (a proxy for the larger drawing).
    """
    best: Optional[PrintedScale] = None
    best_key: Optional[tuple] = None
    for ps in printed_scales:
        title = (ps.title or "").lower()
        if any(d in title for d in _DETAIL_PATTERNS):
            continue
        rank: Optional[int] = None
        for i, pat in enumerate(_MAIN_PATTERNS):
            if pat in title:
                rank = i
                break
        if rank is None:
            continue
        # Higher preference (smaller index) first, then larger label area.
        key = (-rank, _area(ps.bbox_pt))
        if best_key is None or key > best_key:
            best_key = key
            best = ps
    return best
