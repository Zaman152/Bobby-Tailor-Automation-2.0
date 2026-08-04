"""Deterministic schedule extraction from the PDF text/table layer.

Architectural drawings print door / frame / finish / wall-type schedules as real
tables in the PDF text layer. Those tables hold EXACT data — door panel and frame
materials, fire ratings, finishes — that should be *read*, not vision-guessed.

This module recovers that structured data with PyMuPDF's table finder and a set of
content-based heuristics that do not depend on a fixed column order, so the same
parser works across drawing sets from different architects.

Three real schedule FORMATS, one parser (INV-07)
------------------------------------------------
1. **type + count** (Crow) — one row per door TYPE with a printed ``Count``
   column; the quantity is that column.
2. **per-opening** (Moxy) — one row per opening tag, no count column; the
   quantity is one door per printed row.
3. **split-cell per-opening** (Bob's) — as (2), but the materials are printed as
   free text with punctuation (``HM-STL.``, ``S.C. WOOD``, ``ALUM. & GLASS``) and
   the frame material is split across two PyMuPDF cells (``'--- H.'`` +
   ``'M. 6A'``).

The three differences are absorbed by three concepts rather than three parsers:
a phrase-based material reader (:func:`_material_code`), a column-role reader
with a content fallback (:func:`_column_roles` / :func:`_material_columns`), and
a count column whose ABSENCE is a valid answer meaning one door per row
(:func:`_count_column`).

The two-part legend guard (INV-07 §4.3)
---------------------------------------
Reading materials by phrase is deliberately permissive, so it must be paired with
a guard or an interior-elevation drawing grid that PyMuPDF happens to read as a
table starts fabricating doors (Moxy page index 15: the column of grid letters
reads as a tag column and the word WOOD inside prose supplies a pseudo material).
The guard is two-part and both parts are required:

  1. a STANDALONE door-schedule title band whose horizontal span contains the
     table (:func:`_door_title_bands`), and
  2. column-role evidence — at least two distinct door-material columns, or at
     least one header cell carrying a door role (:func:`_is_door_table`).

IMPORTANT — what schedules can and cannot tell you:
  * A door schedule enumerates door *openings/types* with their exact materials.
    Counting its rows (or summing its count column) gives the exact count of
    *scheduled* openings.
  * It does NOT always equal the total *installed* count: in repetitive buildings
    (e.g. hotels) guest-room doors repeat per unit/floor and are counted on the
    plans, not re-listed per instance. So treat schedule counts as an exact LOWER
    bound / type breakdown, and flag the residual for plan-based verification.
  * A plan set that REFERENCES a door schedule it does not contain reports an
    honest zero with a stated reason (:func:`door_schedule_coverage`), never a
    fabricated count and never a silent nothing.

Python 3.9 compatible: typing.Optional/List/Dict/Tuple, no ``X | Y`` runtime
annotations, no walrus in comprehensions.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# A door/opening tag OR a door TYPE code. The first two alternatives are the
# per-opening tags (003, 006A, 101B, 113A, T1, T7B, D-12); the last two are the
# door TYPE code a type+count schedule prints in the same position (OD1, P1,
# DSF, SF). One parser reads all three formats, so one shape has to cover both —
# a type schedule's letters-only code is a door row exactly as much as an
# opening tag is.
#
# The letters-only form is capped at THREE characters and requires at least two:
# four letters admits ordinary words ("WORK", "AREA", "DATA"), and one letter
# admits the elevation grid letters A..H that make Moxy page 15's drawing grid
# read as a tag column.
_TAG_RE = re.compile(
    r"^[A-Z]{0,2}[-]?\d{1,4}[A-Z]?$"
    r"|^T\d+[A-Z]?$"
    r"|^[A-Z]{1,3}\d{1,2}[A-Z]?$"
    r"|^[A-Z]{2,3}$"
)

# A small integer cell — the shape of a printed door COUNT.
_INT_CELL_RE = re.compile(r"^\d{1,3}$")

# Bound the column scan so a pathological table cannot dominate a run (T-23-15).
_MAX_TABLE_COLS = 80
# Schedules stack 2-3 header rows (Moxy t5, Crow t0) — read at most four.
_MAX_HEADER_ROWS = 4
# The count column is looked for in a narrow window right of the tag column.
_COUNT_WINDOW = 3

# ── Material reading: normalise, then resolve by PHRASE ───────────────────────

# Two or more single-letter groups written as an initialism: "H.M.", "H. M. ",
# "S.C. ". Collapsed to one token so a split/punctuated material cell is
# readable ("--- H. M. 6A" -> "HM 6A", "S.C. WOOD" -> "SC WOOD").
_DOTTED_INITIALISM_RE = re.compile(r"\b(?:[A-Z]\.\s*){2,}")


def _normalise_material_text(cell) -> str:
    """Uppercase a schedule cell and reduce its punctuation to readable tokens.

    Three transforms, in order:
      1. uppercase;
      2. collapse dotted initialisms of two or more single-letter groups into one
         token (``H. M.`` -> ``HM``, ``S.C.`` -> ``SC``);
      3. reduce every remaining non-alphanumeric run to a single space.

    Pure function, no I/O. Verified against the five INV-07 §4.1 rows::

        '--- H. M. 6A'               -> 'HM 6A'
        'HM-STL.'                    -> 'HM STL'
        'S.C. WOOD & GLASS'          -> 'SC WOOD GLASS'
        'ALUM. & 1" INSULATED GLASS' -> 'ALUM 1 INSULATED GLASS'
        '*'                          -> ''
    """
    if cell is None:
        return ""
    text = str(cell).upper()
    if not text:
        return ""
    # Keep a trailing space so the collapsed initialism stays its own token.
    text = _DOTTED_INITIALISM_RE.sub(
        lambda m: re.sub(r"[^A-Z0-9]", "", m.group(0)) + " ", text
    )
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


# Phrase -> canonical material code. Resolution is LEFTMOST then LONGEST, which
# is load-bearing: a solid-core wood leaf with a glass lite must resolve to the
# LEAF material (SCW, not GLASS), and an aluminium door with insulated glazing
# must resolve to ALUM. Canonical codes: HM SCW WD HC ALUM GALV GLASS STL KD
# FRP IM. Extend by adding a row — order inside the list does not matter
# (leftmost-then-longest decides), it is grouped for readability only.
_MAT_PHRASES = [
    ("SOLID CORE WOOD", "SCW"),
    ("SOLID CORE", "SCW"),
    ("SC WOOD", "SCW"),
    ("SCW", "SCW"),
    ("HOLLOW CORE WOOD", "HC"),
    ("HOLLOW CORE", "HC"),
    ("HC", "HC"),
    ("HOLLOW METAL", "HM"),
    ("HM STL", "HM"),
    ("HMG", "HM"),
    ("HM", "HM"),
    ("ALUMINUM", "ALUM"),
    ("ALUMINIUM", "ALUM"),
    ("ALUM", "ALUM"),
    ("AL", "ALUM"),
    ("GALVANIZED", "GALV"),
    ("GALVANISED", "GALV"),
    ("GALV", "GALV"),
    ("GLASS", "GLASS"),
    ("GL", "GLASS"),
    ("WOOD", "WD"),
    ("WD", "WD"),
    ("WG", "WD"),
    ("STEEL", "STL"),
    ("STL", "STL"),
    ("KNOCK DOWN", "KD"),
    ("KD", "KD"),
    ("FRP", "FRP"),
    ("IM", "IM"),
]

_MAT_PHRASE_RE = [
    (re.compile(r"\b" + phrase.replace(" ", r"\s+") + r"\b"), code)
    for phrase, code in _MAT_PHRASES
]

# Every canonical code the resolver can emit.
MATERIAL_CODES = tuple(sorted({code for _, code in _MAT_PHRASES}))

# Canonical ESTIMATOR code for a read material code — the ONE definition, shared
# by door_schedule_to_legend and component_library.count_doors_by_material so the
# formats can never disagree about a name again (INV-07 risk 4).
#
# SCW maps to the WOOD code, NOT to "SC": aggregator.py's door patterns include
# ``door.*\bwd\b`` and no ``\bsc\b``, so ``Doors-SC`` matches none of them and
# falls into the generic "Doors" bucket. That single letter is why Moxy's
# correctly-parsed solid-core-wood doors scored MISSING (INV-07 §3).
MATERIAL_CODE_ALIAS = {
    "SCW": "WD",
    "ALUM": "AL",
    "GLASS": "GL",
    "HMG": "HM",
    "GALV": "STL",
}


def canonical_material_code(code: str) -> str:
    """Map a read material code onto the canonical estimator code."""
    key = (code or "").strip().upper()
    return MATERIAL_CODE_ALIAS.get(key, key)


def _material_code(cell) -> str:
    """The door/frame material a schedule cell names, or ``""``.

    Leftmost match wins; ties at the same offset go to the longest phrase. Every
    bare-token membership test in this module resolves through here.
    """
    text = _normalise_material_text(cell)
    if not text:
        return ""
    best_key = None
    best_code = ""
    for pattern, code in _MAT_PHRASE_RE:
        m = pattern.search(text)
        if m is None:
            continue
        key = (m.start(), -(m.end() - m.start()))
        if best_key is None or key < best_key:
            best_key = key
            best_code = code
    return best_code


# Human-readable names for material codes.
_PANEL_LABEL = {
    "SCW": "Solid Core Wood", "WD": "Wood", "HC": "Hollow Core Wood",
    "HM": "Hollow Metal", "GLASS": "Glass / Aluminum", "GL": "Glass / Aluminum",
    "ALUM": "Aluminum", "AL": "Aluminum", "FRP": "FRP", "STL": "Steel",
    "IM": "Intermediate Metal", "KD": "Knock-Down", "GALV": "Galvanized Steel",
}
_FRAME_LABEL = {
    "HM": "Hollow Metal", "GALV": "Galvanized Steel", "ALUM": "Aluminum",
    "AL": "Aluminum", "KD": "Knock-Down", "WD": "Wood", "STL": "Steel",
    "SCW": "Solid Core Wood", "GLASS": "Glass / Aluminum", "GL": "Glass / Aluminum",
    "IM": "Intermediate Metal", "HC": "Hollow Core Wood", "FRP": "FRP",
}

# A note body that classifies its doors as hollow metal, and the reference to it
# printed in a schedule row's comment cell. These live HERE, not in
# component_library, so BOTH schedule formats receive the reclassification: the
# type+count format got it and the per-opening format did not, which is half the
# reason two parsers disagreed (INV-07 §5 step 9).
_NOTE_REF_RE = re.compile(r"NOTE\s*(\d{1,2})", re.IGNORECASE)
_HM_DOOR_NOTE_RE = re.compile(r"HOLLOW\s+METAL\s+DOOR", re.IGNORECASE)


def _hm_door_notes(text: str) -> set:
    """Note numbers whose printed body says "HOLLOW METAL DOOR(S)".

    Reads the plan's own note text (e.g. ``NOTE 1 - ... HOLLOW METAL DOORS
    ...``) so P-series personnel doors carried in HM frames are named as HM
    doors — the estimator's reading, taken verbatim from the plan, not guessed.
    """
    hm: set = set()
    if not text:
        return hm
    for m in re.finditer(r"NOTE\s*(\d{1,2})\s*-\s*(.+)", text, re.IGNORECASE):
        num, body = m.group(1), m.group(2)
        # Only look at the remainder of the same line for the classifier.
        body = body.splitlines()[0] if body else ""
        if _HM_DOOR_NOTE_RE.search(body):
            hm.add(num)
    return hm


# ── The two-part legend guard, part 1: standalone door-schedule title bands ───

_DOOR_WORD_RE = re.compile(r"\bDOORS?\b", re.IGNORECASE)
_SCHEDULE_WORD_RE = re.compile(r"\b(SCHEDULE|TYPES?)\b", re.IGNORECASE)
# DOOR sitting directly beside the schedule word ("DOOR SCHEDULE", "SCHEDULE OF
# DOORS", "WINDOW & DOOR SCHEDULE"). Only non-letters may separate them.
_DOOR_ADJACENT_RE = re.compile(
    r"\bDOORS?\b[^A-Za-z]{0,20}\b(SCHEDULE|TYPES?)\b"
    r"|\b(SCHEDULE|TYPES?)\b[^A-Za-z]{0,20}\bDOORS?\b",
    re.IGNORECASE,
)
# A legend that is about something else. Present + DOOR not adjacent to the
# schedule word => the line titles a different legend (a DOOR HARDWARE SCHEDULE
# is a hardware-set schedule, not a door schedule).
_TITLE_DENY_RE = re.compile(
    r"\b(FLOORING|FINISH(?:ES)?|PAINT|COLOU?RS?|RCP|REFLECTED|CEILING|LIGHTING"
    r"|PLUMBING|EQUIPMENT|HARDWARE|WINDOWS?|LOUVERS?|SIGNAGE|ROOMS?"
    r"|WALL\s+COVERING)\b",
    re.IGNORECASE,
)
# A line that POINTS AT a schedule rather than titling one ("REF: DOOR SCHEDULE
# (ABOVE)", "SEE DOOR SCHEDULE"). A callout must not own a band, or the table
# that happens to sit beneath the callout inherits a door schedule's authority.
_TITLE_REFERENCE_RE = re.compile(r"^(REF\.?|REFER|SEE|PER)\b", re.IGNORECASE)
# A title is a LINE OF ITS OWN. Anything longer is prose that happens to contain
# the phrase ("REFER TO ARCHITECTURAL DOOR SCHEDULE WC 01 FOR ...").
_MAX_TITLE_CHARS = 60
# A table qualifies under a band when the band covers this much of its width.
_BAND_WIDTH_OVERLAP = 0.6


def _is_door_title_line(text: str) -> bool:
    """True when *text* reads as a STANDALONE door-schedule / door-type title.

    Three requirements, all necessary (INV-07 §4.3.1):
      * a line of its own, at most :data:`_MAX_TITLE_CHARS` characters, and not a
        reference callout — this is what rejects a schedule phrase buried inside
        an elevation note, and a "REF: DOOR SCHEDULE" pointer;
      * it names a door AND a schedule/type word;
      * it carries no deny word unless the door word sits directly beside the
        schedule word — this rejects unrelated legends and hardware schedules.
    """
    line = " ".join((text or "").split())
    if not line or len(line) > _MAX_TITLE_CHARS:
        return False
    if _TITLE_REFERENCE_RE.match(line):
        return False
    if not _DOOR_WORD_RE.search(line):
        return False
    if not _SCHEDULE_WORD_RE.search(line):
        return False
    if _TITLE_DENY_RE.search(line) and not _DOOR_ADJACENT_RE.search(line):
        return False
    return True


def _text_lines(page) -> List[Tuple[str, tuple]]:
    """``[(line_text, bbox)]`` for every text line on *page*. Never raises."""
    try:
        data = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return []
    out: List[Tuple[str, tuple]] = []
    for block in (data.get("blocks") or []):
        for line in (block.get("lines") or []):
            text = "".join(s.get("text", "") for s in (line.get("spans") or []))
            bbox = line.get("bbox")
            if text.strip() and bbox and len(bbox) == 4:
                out.append((text.strip(), tuple(bbox)))
    return out


def _door_title_bands(page, table_bboxes: Optional[List[tuple]] = None) -> List[dict]:
    """Horizontal bands of the page owned by a standalone door-schedule title.

    A band is ``{"x0", "x1", "y0", "title"}`` for every qualifying title line.
    Each band's horizontal range is then EXTENDED with the bounding box of any
    table it directly titles, so a header-less continuation fragment inherits its
    parent's band (Moxy p6 t10/t13/t14). Never raises.
    """
    bands: List[dict] = []
    for text, bbox in _text_lines(page):
        if not _is_door_title_line(text):
            continue
        bands.append({
            "x0": float(bbox[0]), "x1": float(bbox[2]), "y0": float(bbox[1]),
            "title": " ".join(text.split()),
        })
    if not bands or not table_bboxes:
        return bands
    # A printed title line is typically far NARROWER than the table it titles
    # ("DOOR SCHEDULE" is 80pt wide over a 900pt table), so the >=60% rule can
    # never fire on the raw line. First attach each band to the table it DIRECTLY
    # titles — the nearest table below it that it overlaps at all — and adopt
    # that table's width.
    for band in bands:
        titled = _directly_titled_table(band, table_bboxes)
        if titled is not None:
            band["x0"] = min(band["x0"], float(titled[0]))
            band["x1"] = max(band["x1"], float(titled[2]))
    # Then two widening passes: a stacked continuation fragment that qualifies
    # under the widened band contributes its own width in turn, so a column of
    # header-less fragments stitches onto its parent's band.
    for _ in range(2):
        for band in bands:
            for bb in table_bboxes:
                if _band_covers(band, bb):
                    band["x0"] = min(band["x0"], float(bb[0]))
                    band["x1"] = max(band["x1"], float(bb[2]))
    return bands


def _directly_titled_table(band: dict, table_bboxes: List[tuple]) -> Optional[tuple]:
    """The table *band* directly titles: nearest below it, with any x-overlap."""
    best = None
    best_dy = None
    for bb in table_bboxes:
        x0, y0, x1, y1 = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
        if band["y0"] > y1:
            continue  # the title sits BELOW the table — it does not title it
        if min(band["x1"], x1) - max(band["x0"], x0) <= 0:
            continue  # no horizontal relationship at all
        dy = max(y0 - band["y0"], 0.0)
        if best_dy is None or dy < best_dy:
            best, best_dy = bb, dy
    return best


def _band_covers(band: dict, bbox) -> bool:
    """True when *band* sits at/above *bbox* and spans most of its width."""
    x0, y0, x1, y1 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    width = x1 - x0
    if width <= 0:
        return False
    if band["y0"] > y1:
        return False  # the title sits BELOW the table — it does not title it
    overlap = min(band["x1"], x1) - max(band["x0"], x0)
    return (overlap / width) >= _BAND_WIDTH_OVERLAP


def _table_in_door_band(bbox, bands: List[dict]) -> bool:
    """True when any door-title band qualifies the table at *bbox*."""
    for band in bands or []:
        if _band_covers(band, bbox):
            return True
    return False


# ── Column roles (advisory) + content detection (authoritative fallback) ──────

_ROLE_COUNT_RE = re.compile(r"\b(QTY|QUANTITY|COUNT|NO OF|NUMBER OF)\b")
_ROLE_TAG_RE = re.compile(r"\b(TAG|MARK|DOOR NO|NUMBER|NO)\b")


def _header_role(header: str) -> str:
    """The door role a NORMALISED header string names, or ``""``.

    Order is the contract: count, then frame material, then panel material
    (a bare MATERIAL is the panel), then tag.
    """
    if not header:
        return ""
    if _ROLE_COUNT_RE.search(header):
        return "count"
    if "FRAME" in header and "MATERIA" in header:
        return "frame_mat"
    if "MATERIA" in header:
        return "panel_mat"
    if _ROLE_TAG_RE.search(header):
        return "tag"
    return ""


def _column_roles(rows: List[List[str]]) -> Dict[int, str]:
    """``{column_index: role}`` read from the table's stacked header rows.

    Schedules stack two or three header rows, so the first
    :data:`_MAX_HEADER_ROWS` rows of each column are joined before the role is
    read. Roles are ADVISORY — content detection fills every gap, and a role is
    never trusted over content that contradicts it (see :func:`_resolve_columns`).
    """
    roles: Dict[int, str] = {}
    if not rows:
        return roles
    width = min(max((len(r) for r in rows), default=0), _MAX_TABLE_COLS)
    header_rows = rows[:_MAX_HEADER_ROWS]
    for c in range(width):
        joined = " ".join(
            r[c] for r in header_rows if c < len(r) and r[c]
        )
        role = _header_role(_normalise_material_text(joined))
        if role:
            roles[c] = role
    return roles


def _cells(row) -> List[str]:
    return [(str(c).strip() if c is not None else "") for c in row]


def _is_tag_token(token: str) -> bool:
    """True when *token* reads as a door tag / type code and not as a MATERIAL.

    A letters-only type code and a material abbreviation share a shape (``SCW``,
    ``HM``, ``AL`` all match the type-code form), so a material column two
    columns from the left would otherwise win the tag role. The material reader
    is the arbiter: anything it can name is a material, not a tag.
    """
    if not _TAG_RE.match(token):
        return False
    if token.isalpha() and _material_code(token):
        return False
    return True


def _tag_tokens(cell: str) -> List[str]:
    """Split a (possibly merged) tag cell into individual valid tags."""
    return [t for t in cell.split() if _is_tag_token(t)]


def _is_header_row(row: List[str]) -> bool:
    """True when a row reads as a stacked HEADER rather than a door row.

    Two or more cells naming a door column role is a header, not data. Needed
    because a type code and a header word share a shape: ``TAG`` matches the
    type-code form, so Moxy's ``['TAG','ROOM NAME','LEAF QTY.',...]`` header
    would otherwise be counted as an opening.
    """
    hits = 0
    for cell in row or []:
        if cell and _header_role(_normalise_material_text(cell)):
            hits += 1
            if hits >= 2:
                return True
    return False


def _data_rows(rows: List[List[str]], tag_col: int) -> List[List[str]]:
    """The rows of *rows* that carry a door tag and are not a header."""
    return [
        r for r in rows
        if tag_col < len(r) and _tag_tokens(r[tag_col]) and not _is_header_row(r)
    ]


def _tag_column(rows: List[List[str]]) -> Optional[int]:
    """The LEFT-MOST of columns 0-3 with at least three tag-shaped cells.

    Left-most, not most-hits: a type+count schedule prints its Count column
    immediately right of the Type column, and a column of small integers is
    itself tag-shaped, so "most hits" hands the tag role to the COUNT column
    (Crow: 9 integer counts beat 7 type codes) and the schedule reads as five
    openings instead of one hundred and five.
    """
    if not rows:
        return None
    width = max(len(r) for r in rows)
    for c in range(min(width, 4)):  # tag is always near the left
        hits = 0
        for r in rows:
            if c < len(r) and _tag_tokens(r[c]) and not _is_header_row(r):
                hits += 1
        if hits >= 3:
            return c
    return None


def _cell_material(row: List[str], c: int) -> str:
    """The material at column *c* of *row*, joining a SPLIT neighbour cell.

    PyMuPDF sometimes splits one printed material across two cells (Bob's frame
    column: ``'--- H.'`` + ``'M. 6A'``). The neighbour is only joined when it
    carries no material of its OWN — otherwise a dimension column would read the
    next column's material and masquerade as a material column (Crow's thickness
    column sitting left of ``IM``).
    """
    if c >= len(row):
        return ""
    code = _material_code(row[c])
    if code:
        return code
    if c + 1 < len(row) and not _material_code(row[c + 1]):
        return _material_code(row[c] + " " + row[c + 1])
    return ""


def _material_column_scores(rows: List[List[str]], tag_col: int) -> "Counter[int]":
    """Per-column count of data rows carrying a readable door material."""
    scores: "Counter[int]" = Counter()
    width = min(max((len(r) for r in rows), default=0), _MAX_TABLE_COLS)
    for r in _data_rows(rows, tag_col):
        for c in range(width):
            if c == tag_col:
                continue
            if _cell_material(r, c):
                scores[c] += 1
    return scores


def _material_columns(rows: List[List[str]], tag_col: int, exclude=()):
    """``(panel_col, frame_col)`` by content — leftmost, then rightmost != it.

    Schedules print the leaf material before the frame material, so position is
    the classifier once the materials are readable. Columns in *exclude* are
    already claimed by a header role.
    """
    scores = _material_column_scores(rows, tag_col)
    cols = [c for c in sorted(scores) if scores[c] >= 2 and c not in exclude]
    if not cols:
        return None, None
    panel_col = cols[0]
    frame_col = cols[-1] if cols[-1] != panel_col else None
    return panel_col, frame_col


def _count_column(rows: List[List[str]], tag_col: Optional[int],
                  roles: Optional[Dict[int, str]] = None) -> Optional[int]:
    """The printed COUNT column, or ``None`` meaning ONE DOOR PER ROW.

    Header role first; else a column within :data:`_COUNT_WINDOW` of the tag
    column that is at least sixty percent small integers.

    Returning ``None`` is a VALID and expected answer — it is what makes a
    per-opening schedule (Bob's, Moxy) readable at all, and it is the concept
    whose absence made ``_parse_count_door_rows`` give up on both of them.
    """
    for col, role in sorted((roles or {}).items()):
        # A merged header cell can put the count role on the TAG column itself
        # (Moxy's guestroom fragment). A column cannot be both.
        if role == "count" and col != tag_col:
            return col
    if tag_col is None:
        return None
    width = min(max((len(r) for r in rows), default=0), _MAX_TABLE_COLS)
    data_rows = _data_rows(rows, tag_col)
    if len(data_rows) < 3:
        return None
    for c in range(tag_col + 1, min(tag_col + 1 + _COUNT_WINDOW, width)):
        hits = 0
        for r in data_rows:
            value = (r[c] or "").strip() if c < len(r) else ""
            if _INT_CELL_RE.match(value):
                hits += 1
        if hits >= 3 and (hits / len(data_rows)) >= 0.6:
            return c
    return None


def _resolve_columns(rows: List[List[str]], roles: Dict[int, str]):
    """``(tag_col, count_col, panel_col, frame_col)`` — roles first, content fills.

    Content detection runs PER MISSING ROLE, not only when every role is missing:
    Bob's finds its panel column from a ``MATERIAL`` header but its frame header
    is split across two cells, so the frame column must still come from content.
    """
    role_tag = next((c for c, r in sorted(roles.items()) if r == "tag"), None)
    tag_col = None
    if role_tag is not None:
        if len(_data_rows(rows, role_tag)) >= 3:
            tag_col = role_tag
    if tag_col is None:
        tag_col = _tag_column(rows)
    if tag_col is None:
        return None, None, None, None

    count_col = _count_column(rows, tag_col, roles)
    panel_col = next((c for c, r in sorted(roles.items()) if r == "panel_mat"), None)
    frame_col = next((c for c, r in sorted(roles.items()) if r == "frame_mat"), None)

    claimed = set(c for c in (panel_col, frame_col, count_col) if c is not None)
    if panel_col is None or frame_col is None:
        content_panel, content_frame = _material_columns(rows, tag_col, exclude=claimed)
        if panel_col is None:
            panel_col = content_panel
            if frame_col is None:
                frame_col = content_frame
        elif frame_col is None:
            # The panel came from a header; the frame must still come from
            # content, and it is the RIGHT-most readable material column.
            frame_col = content_frame if content_frame is not None else content_panel
            if frame_col == panel_col:
                frame_col = None
    return tag_col, count_col, panel_col, frame_col


def _material_coverage(rows, tag_col, panel_col, frame_col) -> tuple:
    """(door_rows, covered_rows): how many tag rows carry a panel/frame material.

    Floor-plan door *callouts* have tags but no material columns, so coverage is
    near zero there; a real schedule table covers most of its rows.
    """
    door_rows = 0
    covered = 0
    for r in _data_rows(rows, tag_col):
        door_rows += 1
        pm = _cell_material(r, panel_col) if panel_col is not None else ""
        fm = _cell_material(r, frame_col) if frame_col is not None else ""
        if pm or fm:
            covered += 1
    return door_rows, covered


def _is_door_table(rows, tag_col, panel_col, frame_col, roles=None) -> bool:
    """Part 2 of the legend guard: statistical gate PLUS column-role evidence.

    The statistical gate (>=3 tag rows, >=40% material coverage) is unchanged.
    The evidence requirement is new and is what keeps the widened material reader
    from fabricating doors out of an interior-elevation drawing grid: the table
    must present at least TWO distinct door-material columns, or at least ONE
    header cell carrying a door role.
    """
    if tag_col is None or (panel_col is None and frame_col is None):
        return False
    door_rows, covered = _material_coverage(rows, tag_col, panel_col, frame_col)
    if door_rows < 3:
        return False
    # A genuine door schedule lists a material on most rows. Floor-plan tag
    # clusters do not — this gate rejects those false positives.
    if covered < 3 or (covered / door_rows) < 0.4:
        return False
    distinct_material_cols = len({c for c in (panel_col, frame_col) if c is not None})
    if distinct_material_cols >= 2:
        return True
    return bool(roles)


_MATERIAL_ROLES = ("panel_mat", "frame_mat")


def _has_material_role(roles: Dict[int, str]) -> bool:
    return any(r in _MATERIAL_ROLES for r in (roles or {}).values())


def _inherit_roles(roles: Dict[int, str], siblings: List[Dict[int, str]],
                   width: int) -> Dict[int, str]:
    """Borrow a sibling table's column roles when this table names no materials.

    Mitigates the merged-header fragment (INV-07 risk 6): Moxy's guestroom
    schedule prints its whole header inside ONE cell, so its only role is a
    spurious ``count`` on the tag column and its frame column cannot be told from
    its panel column. A sibling table under the same title band DID yield real
    material roles at the same column indices — inherit those by index rather
    than guessing. A table that already names a material column keeps its own
    reading; inheritance never overrules content.
    """
    if _has_material_role(roles):
        return roles
    usable = [s for s in siblings if _has_material_role(s) and max(s) < width]
    if not usable:
        return roles
    return dict(max(usable, key=len))


@dataclass
class DoorRecord:
    tag: str
    room: str = ""
    panel_material: str = ""
    frame_material: str = ""
    page: int = 0
    count: int = 1
    comment: str = ""


@dataclass
class DoorSchedule:
    # Scheduled openings: the SUM of the printed counts, not the number of
    # distinct tags. A type row reading "P1 / 24" is twenty-four doors.
    openings: int = 0
    panel_counts: Counter = field(default_factory=Counter)
    frame_counts: Counter = field(default_factory=Counter)
    pages: List[int] = field(default_factory=list)
    records: List[DoorRecord] = field(default_factory=list)
    # Every parsed DATA ROW, in the shape count_doors_by_material consumes. This
    # is what lets ONE extractor serve both the legend and the component library.
    rows: List[dict] = field(default_factory=list)
    # How many band-qualified tables were examined across the document.
    tables_seen: int = 0
    # 1-based pages printing a standalone door-schedule TITLE, whether or not a
    # table was parsed there. A non-empty list with openings == 0 is Chelsea: the
    # plan set references a schedule it does not contain. Without this field that
    # state cannot be told from "we never looked".
    titled_pages: List[int] = field(default_factory=list)
    # Text of the pages that carried a schedule — the source for the printed
    # HOLLOW METAL DOOR note reclassification.
    notes_text: str = ""

    @property
    def found(self) -> bool:
        return self.openings > 0


def reclassified_panel_counts(ds: "DoorSchedule") -> "Counter[str]":
    """Panel counts with the plan's OWN printed NOTE reclassification applied.

    A door row whose comment references a NOTE the plan classifies as
    "HOLLOW METAL DOOR" is counted as hollow metal whatever code the row printed:
    Crow prints ``IM`` on the twenty-nine rows its ``NOTE 1`` / ``NOTE 2`` bodies
    describe as *16 GA. HOLLOW METAL DOORS IN ... WELDED HOLLOW METAL FRAMES*.

    Codes stay RAW here — canonicalisation to the estimator form happens in
    :func:`door_schedule_to_legend`, so a caller can still see what was printed.
    """
    counts: "Counter[str]" = Counter()
    if ds is None:
        return counts
    hm_notes = _hm_door_notes(ds.notes_text or "")
    for row in ds.rows or []:
        code = (row.get("door_material") or "").strip().upper()
        if not code:
            continue
        try:
            n = int(row.get("count") or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            continue
        note = _NOTE_REF_RE.search(row.get("comment") or "")
        if note and note.group(1) in hm_notes:
            code = "HM"
        counts[code] += n
    return counts


def _page_tables(page):
    """``([rows_per_table], [bbox_per_table])`` for a page. Never raises."""
    try:
        tables = list(page.find_tables().tables)
    except Exception:  # noqa: BLE001
        return [], []
    table_rows: List[List[List[str]]] = []
    table_bboxes: List[tuple] = []
    for t in tables:
        try:
            rows = [_cells(r) for r in t.extract()]
            bbox = tuple(t.bbox)
        except Exception:  # noqa: BLE001
            continue
        if not rows or len(bbox) != 4:
            continue
        table_rows.append(rows)
        table_bboxes.append(bbox)
    return table_rows, table_bboxes


def accepted_door_tables(page) -> List[dict]:
    """Every table on *page* that BOTH parts of the legend guard accept.

    Returns ``[{rows, bbox, roles, own_roles, tag_col, count_col, panel_col,
    frame_col}]`` — empty when the page carries no standalone door-schedule
    title band, or when every table under one fails the guard (Moxy page index
    15's interior-elevation drawing grid).

    Public because it is the unit of the guard: a negative assertion wants to
    say "this page contributes zero door rows", not "the whole document's total
    happens to be unchanged".
    """
    table_rows, table_bboxes = _page_tables(page)
    bands = _door_title_bands(page, table_bboxes)
    if not bands:
        return []
    return _accept_under_bands(table_rows, table_bboxes, bands)


def _accept_under_bands(table_rows, table_bboxes, bands) -> List[dict]:
    """The guard's part 2, applied to every table the bands already qualified."""
    qualified = [
        idx for idx, bb in enumerate(table_bboxes)
        if _table_in_door_band(bb, bands)
    ]
    if not qualified:
        return []

    # Roles of every qualified table on this page, so a merged-header fragment
    # can inherit a sibling's columns by index.
    own_roles = {idx: _column_roles(table_rows[idx]) for idx in qualified}
    sibling_roles = [r for r in own_roles.values() if r]

    accepted: List[dict] = []
    for idx in qualified:
        rows = table_rows[idx]
        width = min(max((len(r) for r in rows), default=0), _MAX_TABLE_COLS)
        roles = own_roles[idx]
        tag_col, count_col, panel_col, frame_col = _resolve_columns(rows, roles)
        if tag_col is None:
            continue
        distinct = len({c for c in (panel_col, frame_col) if c is not None})
        if distinct < 2 and not _has_material_role(roles):
            # A single material column with no material header of its own —
            # borrow a sibling's roles before rejecting (INV-07 risk 6).
            inherited = _inherit_roles(roles, sibling_roles, width)
            if inherited is not roles:
                roles = inherited
                tag_col, count_col, panel_col, frame_col = _resolve_columns(rows, roles)
                if tag_col is None:
                    continue
        if not _is_door_table(rows, tag_col, panel_col, frame_col, roles):
            continue
        accepted.append({
            "rows": rows,
            "bbox": table_bboxes[idx],
            "roles": roles,
            "own_roles": own_roles[idx],
            "tag_col": tag_col,
            "count_col": count_col,
            "panel_col": panel_col,
            "frame_col": frame_col,
        })
    return accepted


def _row_count(row: List[str], count_col: Optional[int]) -> int:
    """The quantity a data row carries: its printed count, else ONE.

    "Else one" is the whole point. A schedule with no count column prints one row
    per opening, so its row IS its quantity — the concept whose absence made the
    old type+count parser return ``None`` on both per-opening formats.
    """
    if count_col is None or count_col >= len(row):
        return 1
    raw = (row[count_col] or "").strip()
    if not _INT_CELL_RE.match(raw):
        return 1
    try:
        return int(raw)
    except ValueError:
        return 1


def extract_door_schedule(doc) -> DoorSchedule:
    """Extract a deterministic door schedule from an open fitz.Document.

    ONE parser for all three real formats. Per page: compute the standalone
    door-schedule title bands, keep only the tables those bands qualify, resolve
    the tag / count / panel / frame columns by header role with a content
    fallback, then read one row at a time. A row's quantity is its printed count
    when the schedule prints one, otherwise ONE.

    Tag de-duplication stays for the RECORDS — a tag repeated across continuation
    fragments is one opening — but the QUANTITY is the summed count, because a
    type row reading "P1 / 24" is twenty-four doors under one tag.
    """
    out = DoorSchedule()
    seen_tags = set()
    notes: List[str] = []
    for i in range(doc.page_count):
        page = doc[i]
        table_rows, table_bboxes = _page_tables(page)
        bands = _door_title_bands(page, table_bboxes)
        if not bands:
            continue
        # The page NAMES a door schedule. Recorded before any table is judged, so
        # "referenced but absent" is representable (Chelsea).
        out.titled_pages.append(i + 1)
        accepted = _accept_under_bands(table_rows, table_bboxes, bands)
        out.tables_seen += len(accepted)

        page_used = False
        for table in accepted:
            rows = table["rows"]
            tag_col = table["tag_col"]
            count_col = table["count_col"]
            panel_col = table["panel_col"]
            frame_col = table["frame_col"]
            for r in _data_rows(rows, tag_col):
                toks = _tag_tokens(r[tag_col])
                room = r[tag_col + 1] if tag_col + 1 < len(r) else ""
                panel = _cell_material(r, panel_col) if panel_col is not None else ""
                frame = _cell_material(r, frame_col) if frame_col is not None else ""
                comment = r[-1] if r else ""
                n = _row_count(r, count_col)
                if n <= 0:
                    continue
                out.rows.append({
                    "type": toks[0],
                    "count": n,
                    "door_material": panel,
                    "frame_material": frame,
                    "comment": comment,
                })
                if panel:
                    out.panel_counts[panel] += n
                if frame:
                    out.frame_counts[frame] += n
                out.openings += n
                page_used = True
                for tg in toks:
                    if tg in seen_tags:
                        continue
                    seen_tags.add(tg)
                    out.records.append(DoorRecord(
                        tag=tg, room=room, panel_material=panel,
                        frame_material=frame, page=i + 1, count=n, comment=comment,
                    ))
        if page_used:
            out.pages.append(i + 1)
            try:
                notes.append(page.get_text() or "")
            except Exception:  # noqa: BLE001
                pass
    out.notes_text = "\n".join(notes)
    return out


def door_schedule_to_legend(ds: "DoorSchedule") -> Optional[dict]:
    """Convert an extracted door schedule into an authoritative legend schedule.

    Each panel/frame material becomes an EXACT, auto-verifiable count of
    *scheduled* openings. Quantities pass through verbatim (``takeoff_legend``)
    so the pipeline never re-applies waste/formulas to a counted door.

    The ITEM field carries the CANONICAL estimator form — ``Doors-<CODE>`` and
    ``Door Frames-<CODE>`` — because that is what ``aggregator.ITEM_NAME_MAP``
    and the scorer match on. Emitting the prose name there is the entire reason
    Moxy's correctly-parsed doors scored MISSING: it published
    ``Doors - Solid Core Wood (door schedule)`` against a golden asking for
    ``Doors-WD``, and no token-overlap matcher can bridge that (INV-07 §3). The
    prose survives in DESCRIPTION for the human report.

    The plan's own printed HOLLOW METAL DOOR note reclassification is applied
    HERE, so BOTH schedule formats receive it.

    Returns ``None`` when nothing reliable was extracted.
    """
    if not ds or not ds.found:
        return None
    panel_counts = reclassified_panel_counts(ds)
    frame_counts = ds.frame_counts
    if not panel_counts and not frame_counts:
        return None

    rows: List[dict] = []
    for code, n in panel_counts.most_common():
        rows.append({
            "ITEM": "Doors-{}".format(canonical_material_code(code)),
            "DESCRIPTION": f"Doors - {_PANEL_LABEL.get(code, code)} (door schedule)",
            "QTY": str(n), "QUANTITY": str(n), "UNIT": "EA",
        })
    for code, n in frame_counts.most_common():
        rows.append({
            "ITEM": "Door Frames-{}".format(canonical_material_code(code)),
            "DESCRIPTION": f"Door Frames - {_FRAME_LABEL.get(code, code)} (door schedule)",
            "QTY": str(n), "QUANTITY": str(n), "UNIT": "EA",
        })
    if not rows:
        return None

    return {
        "name": "Door Schedule (extracted from plans)",
        "table_purpose": "takeoff_legend",
        # Machine-read off the plans — NOT a human input file, so it must
        # never publish as HUMAN INPUT (C4): parsed from the door schedule printed on the plans.
        "legend_origin": "plan_parsed",
        "schedule_type": "door",
        "use_for_takeoff": True,
        "description": (
            f"{ds.openings} scheduled door openings parsed deterministically from "
            f"the door schedule on sheet page(s) {ds.pages}. Exact type/material "
            f"breakdown; repeated guest-room/instance counts are taken from the "
            f"floor plans and verified separately."
        ),
        "columns": ["ITEM", "QTY", "UNIT"],
        "rows": rows,
        "_source_pages": list(ds.pages),
    }


# ── Honest zero: an input gap is reported as an input gap ────────────────────


def door_schedule_coverage(ds: "DoorSchedule", absent_references=()) -> List[dict]:
    """Coverage records for a door schedule that could NOT produce a quantity.

    Two shapes of input gap, both reported the same way:

    1. **Title present, table absent.** The plan set names a door schedule and
       the sheet holding it is not in the PDF. Chelsea's 32-page set prints
       ``DOOR SCHEDULE GENERAL NOTES`` and thirteen ``SEE SCHEDULE`` callouts,
       and contains no opening-tag table on any page. Its golden asks for 236 /
       2,378 / 2,687 doors — multifamily per-unit-type numbers that are simply
       unreachable from this input.
    2. **Schedule parsed, a referenced sheet absent.** A schedule that prints a
       per-type multiplier reference the PDF does not contain reports the
       reference and the absence. It does NOT reconstruct the multiplier —
       inventing one is the coincidence trap this phase exists to refuse.

    Returns ``[]`` when the schedule produced openings and nothing is missing,
    which is the case for Bob's, Crow and Moxy.

    The status vocabulary is IMPORTED from :mod:`bobbytailor.pipeline.coverage`
    (23-01), never redefined here: a second flag shape for the same fact is how a
    report ends up with two disagreeing accounts of the same gap (D-03).
    """
    from bobbytailor.pipeline import coverage as _coverage

    out: List[dict] = []
    if ds is None:
        return out

    if ds.titled_pages and ds.openings == 0:
        pages = _coverage._compact_ranges(list(ds.titled_pages))
        out.append(_coverage.ItemCoverage(
            name="Doors (door schedule)",
            unit="EA",
            status=_coverage.ITEM_NOT_MEASURED,
            quantity=None,
            basis="count",
            reason=(
                "a door schedule is referenced on page(s) %s but no parsable "
                "schedule table exists in this PDF — the sheet holding it is not "
                "in the file. This is an INPUT gap, not a count of zero." % pages
            ),
            expected_from="schedule",
        ).to_dict())

    for reference in absent_references or ():
        label = str(reference).strip()
        if not label:
            continue
        out.append(_coverage.ItemCoverage(
            name="Doors (door schedule)",
            unit="EA",
            status=_coverage.ITEM_NEEDS_REVIEW,
            quantity=float(ds.openings) if ds.openings else None,
            basis="count",
            reason=(
                "the door schedule references %r, which is not in this PDF. The "
                "scheduled count stands as a lower bound; the per-type multiplier "
                "it would supply was NOT reconstructed." % label
            ),
            expected_from="schedule",
        ).to_dict())
    return out


def door_schedule_coverage_warnings(ds: "DoorSchedule", absent_references=()) -> List[str]:
    """Human-readable escalation strings for the records above."""
    return [record["reason"] for record in door_schedule_coverage(ds, absent_references)]


def extract_door_legend_from_pdf(pdf_path: str) -> Optional[dict]:
    """Open a plans PDF and return an authoritative door-schedule legend (or None)."""
    try:
        import fitz
    except Exception:
        return None
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None
    try:
        ds = extract_door_schedule(doc)
    finally:
        doc.close()
    return door_schedule_to_legend(ds)


if __name__ == "__main__":  # quick measurement harness
    import sys
    import fitz
    paths = sys.argv[1:] or [
        "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
        "uploads/Crow - Cass White Road-Plans.pdf",
    ]
    for p in paths:
        d = fitz.open(p)
        ds = extract_door_schedule(d)
        d.close()
        print(f"\n=== {p.split('/')[-1]} ===")
        print(f"  scheduled openings : {ds.openings}  (pages {ds.pages})")
        print(f"  titled pages       : {ds.titled_pages}  tables_seen={ds.tables_seen}")
        print(f"  panel materials    : {dict(ds.panel_counts)}")
        print(f"  panel (notes app.) : {dict(reclassified_panel_counts(ds))}")
        print(f"  frame materials    : {dict(ds.frame_counts)}")
        legend = door_schedule_to_legend(ds)
        print(f"  legend items       : {[r['ITEM'] for r in (legend or {}).get('rows', [])]}")
