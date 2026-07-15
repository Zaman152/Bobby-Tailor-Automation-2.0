"""Deterministic component-library harvester (plans-only naming authority).

An estimator reading a plan set knows what objects exist because the drawing
PRINTS them — in its ABBREVIATION key, its schedules, and its keynotes / general
notes. This module reproduces that read deterministically (no API): it harvests a
``{name, aliases, basis, unit, source}`` component library straight from the plan
text layer and schedule tables, so naming is STABLE run-to-run and anchored to the
plan's own printed vocabulary (it replaces the deleted hand-authored manifest).

What it harvests
----------------
1. **Abbreviation key** — ``CODE = EXPANSION`` pairs (``HM = HOLLOW METAL``). Each
   pair yields alias mappings (``HM`` <-> ``Hollow Metal``) and, for the door /
   frame construction codes, composes estimator names (``Doors-HM``,
   ``Door Frames-HM``) so a detected door binds to the plan's own naming.
2. **Door schedule** — a *type + count* door schedule (Type / Count / Material /
   Frame Material columns) is read row-by-row; doors and frames are counted by
   material using the abbreviation key. When a door row references a printed NOTE
   whose body says "HOLLOW METAL DOORS", the door material is reclassified to HM
   (reading the plan's own note text — never a guess).
3. **Keynotes + general notes** — conservative object-noun mentions (ladder,
   guardrail, handrail, bollard, column, stair, concrete pad, downspout, ...)
   become candidate library names.

Discipline (mirrors every deterministic pass):
  * additive & robust — empty / unparseable text yields prior behaviour; this
    module NEVER raises on messy input and NEVER makes an API call;
  * flag-don't-guess — quantities come only from printed counts; nothing is
    invented.

Python 3.9 compatible: typing.Optional/List/Dict, no ``X | Y`` runtime
annotations, no match statements.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, OrderedDict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# The vocabulary measure-basis set (mirrors object_vocabulary / schemas).
_VALID_BASES = {"count", "linear", "wall_area", "floor_area", "roof_area"}

# ── Abbreviation key ──────────────────────────────────────────────────────────

# A ``CODE = EXPANSION`` line. The expansion may be on the same line or (when the
# table finder splits the cell) on the following line — the parser handles both.
_ABBR_LINE_RE = re.compile(r"^\(?([A-Z]{1,4})\)?\s*=\s*(.*)$")
# An expansion must read as words (letters + spaces + a few separators), so junk
# such as "(X) =" or "PF =" with no real body is dropped.
_EXPANSION_RE = re.compile(r"^[A-Za-z][A-Za-z&/.\- ]{1,40}$")

# Door LEAF / FRAME material codes we compose estimator names for.
_DOOR_MATERIAL_CODES = ("HM", "AL", "SC", "HC", "IM", "STL", "WD", "GL", "SCW")


def _title(text: str) -> str:
    """Title-case an expansion, keeping short joiners lower (``&`` stays)."""
    return " ".join(w.capitalize() if len(w) > 2 else w for w in text.split())


def parse_abbreviations(text: str) -> "OrderedDict[str, str]":
    """Parse ``CODE = EXPANSION`` pairs from plan text.

    Returns an ordered ``{CODE: Title-Cased Expansion}`` map (first definition
    wins). Handles the PyMuPDF layout where a ``"HM ="`` cell and its
    ``"HOLLOW METAL"`` body land on consecutive lines. Never raises.
    """
    out: "OrderedDict[str, str]" = OrderedDict()
    if not text:
        return out
    lines = [ln.strip() for ln in text.splitlines()]
    for i, line in enumerate(lines):
        m = _ABBR_LINE_RE.match(line)
        if not m:
            continue
        code, body = m.group(1), m.group(2).strip()
        if not body:
            # Expansion on the following non-empty line (split cell).
            for nxt in lines[i + 1 : i + 3]:
                if nxt:
                    body = nxt
                    break
        body = body.strip().rstrip(".")
        if not body or not _EXPANSION_RE.match(body):
            continue
        if code in out:
            continue
        out[code] = _title(body)
    return out


# ── Curated keynote / general-note object nouns ───────────────────────────────

# (regex, canonical name, basis, unit). Conservative — only unambiguous object
# nouns an estimator would quantify, never full sentences.
_NOTE_OBJECTS = [
    (r"\baccess ladder\b|\bladder\b", "Ladder", "count", "EA"),
    (r"\bguard\s*rail\b|\bguardrail\b", "Guard Rail", "linear", "LF"),
    (r"\bhand\s*rail\b|\bhandrail\b", "Hand Rail", "linear", "LF"),
    (r"\bbollard\b", "Bollards", "count", "EA"),
    (r"\bcolumn\b", "Columns", "count", "EA"),
    (r"\bstair(?:case|way|s)?\b", "Stairs", "count", "EA"),
    (r"\bdownspout\b", "Downspout", "count", "EA"),
    (r"\bgutter\b", "Gutter", "linear", "LF"),
    (r"\bconcrete pad\b|\bequipment pad\b|\bhousekeeping pad\b", "Concrete Pad", "floor_area", "SF"),
    (r"\bramp\b", "Ramp", "count", "EA"),
    (r"\bcanopy\b", "Canopy", "roof_area", "SF"),
    (r"\bwheel stop\b", "Wheel Stops", "count", "EA"),
    (r"\bdock leveler\b", "Dock Leveler", "count", "EA"),
    (r"\bdock bumper\b", "Dock Bumper", "count", "EA"),
    (r"\bmezzanine\b", "Mezzanine", "floor_area", "SF"),
    (r"\blintels?\b", "Lintels", "linear", "LF"),
    (r"\bexpansion joint\b|\bcontrol joint\b", "Joint", "linear", "LF"),
    (r"\bcurb\b", "Curb & Gutter", "linear", "LF"),
    (r"\bcatch basin\b", "Catch Basins", "count", "EA"),
]


def harvest_from_notes(text: str) -> List[dict]:
    """Extract conservative object-noun library entries from keynote / note prose.

    Returns a de-duplicated list of ``{name, aliases, basis, unit, source}``.
    Only whole-word object nouns are matched; sentences are never emitted.
    """
    if not text:
        return []
    low = text.lower()
    seen = set()
    out: List[dict] = []
    for pattern, name, basis, unit in _NOTE_OBJECTS:
        if name in seen:
            continue
        if re.search(pattern, low, re.IGNORECASE):
            seen.add(name)
            out.append({
                "name": name,
                "aliases": [],
                "basis": basis,
                "unit": unit,
                "source": "keynote",
            })
    return out


# ── Abbreviation-key -> composed door / frame library entries ─────────────────


def abbreviations_to_library(abbr: Dict[str, str]) -> List[dict]:
    """Compose door / frame library entries from the abbreviation key.

    For every door-material code present (``HM = HOLLOW METAL``) emit a
    ``Doors-<CODE>`` and ``Door Frames-<CODE>`` entry whose aliases carry the
    expansion so a detected door text ("hollow metal door") resolves to the
    plan's own estimator name. Non-door abbreviations become alias hints only —
    they are not standalone components.
    """
    out: List[dict] = []
    for code in _DOOR_MATERIAL_CODES:
        expansion = abbr.get(code)
        if not expansion:
            continue
        out.append({
            "name": "Doors-{}".format(code),
            "aliases": [
                "Doors-{}".format(expansion),
                "{} Door".format(expansion),
                "{} Doors".format(expansion),
                "{} Door".format(code),
            ],
            "basis": "count",
            "unit": "EA",
            "source": "abbreviation",
        })
        out.append({
            "name": "Door Frames-{}".format(code),
            "aliases": [
                "Door Frames-{}".format(expansion),
                "{} Frame".format(expansion),
                "{} Frames".format(expansion),
                "{} Frame".format(code),
                "Frame-{}".format(code),
            ],
            "basis": "count",
            "unit": "EA",
            "source": "abbreviation",
        })
    return out


# ── Door schedule: type + count parsing (counted by material) ─────────────────

# Door / frame material tokens found in a schedule material cell.
_SCHED_MAT = {
    "AL", "STL", "IM", "HM", "SC", "HC", "WD", "GLASS", "GL", "ALUM", "FRP",
    "SCW", "HMG", "GALV", "KD",
}
# A door TYPE code: 1-3 leading letters then optional digits (DSF, OD1, P1, SF).
# Deliberately requires >=1 leading letter so numeric per-opening tags (003, 101B
# on per-opening schedules like Moxy) do NOT match — those keep their own path.
_TYPE_CODE_RE = re.compile(r"^[A-Z]{1,3}\d{0,2}[A-Z]?$")
_INT_CELL_RE = re.compile(r"^\d{1,3}$")
# "NOTE 1", "NOTE 3" note reference inside a comment cell.
_NOTE_REF_RE = re.compile(r"NOTE\s*(\d{1,2})", re.IGNORECASE)
# A note body that classifies its doors as hollow metal.
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


def _parse_count_door_rows(rows: List[List[str]]) -> Optional[List[dict]]:
    """Parse a *type + count* door schedule table into structured rows.

    Content-based (no header dependency — PyMuPDF often splits the header into a
    separate table): column 0 must read as door TYPE codes, a nearby column must
    be an integer COUNT, and there must be a material column. Returns
    ``[{type, count, door_material, frame_material, comment}]`` or ``None`` when
    the table is not a type+count door schedule (e.g. a per-opening schedule).
    """
    data = [
        r for r in rows
        if r and _TYPE_CODE_RE.match((r[0] or "").strip())
    ]
    if len(data) < 3:
        return None
    width = max(len(r) for r in data)

    # Count column: an early column (1..3) that is mostly small integers.
    count_col = None
    for c in range(1, min(width, 4)):
        hits = sum(
            1 for r in data
            if c < len(r) and _INT_CELL_RE.match((r[c] or "").strip())
        )
        if hits >= max(3, int(len(data) * 0.6)):
            count_col = c
            break
    if count_col is None:
        return None

    # Material columns by content density; earliest = door leaf, latest = frame.
    mat_cols = []
    for c in range(width):
        if c in (0, count_col):
            continue
        hits = sum(
            1 for r in data
            if c < len(r) and (r[c] or "").strip().upper() in _SCHED_MAT
        )
        if hits >= 2:
            mat_cols.append(c)
    if not mat_cols:
        return None
    mat_cols.sort()
    door_col = mat_cols[0]
    frame_col = mat_cols[-1] if len(mat_cols) > 1 else None

    out: List[dict] = []
    for r in data:
        type_code = (r[0] or "").strip()
        try:
            count = int((r[count_col] or "0").strip() or 0)
        except ValueError:
            count = 0
        if count <= 0:
            continue
        door_mat = (r[door_col] or "").strip().upper() if door_col < len(r) else ""
        frame_mat = (
            (r[frame_col] or "").strip().upper()
            if frame_col is not None and frame_col < len(r) else ""
        )
        comment = (r[-1] or "").strip() if r else ""
        out.append({
            "type": type_code,
            "count": count,
            "door_material": door_mat if door_mat in _SCHED_MAT else "",
            "frame_material": frame_mat if frame_mat in _SCHED_MAT else "",
            "comment": comment,
        })
    return out or None


# Normalise material codes onto the estimator-name code set (SCW->SC, ALUM->AL...).
_MAT_CODE_ALIAS = {
    "SCW": "SC", "ALUM": "AL", "GLASS": "GL", "HMG": "HM", "GALV": "STL",
}


def _canon_mat(code: str) -> str:
    return _MAT_CODE_ALIAS.get(code, code)


def count_doors_by_material(
    door_rows: List[dict],
    abbr: Optional[Dict[str, str]] = None,
    notes_text: str = "",
) -> List[dict]:
    """Count doors and frames by material from parsed type+count door rows.

    Each row is ``{type, count, door_material, frame_material, comment}``. Doors
    are grouped by ``door_material`` and frames by ``frame_material``; the counts
    are summed via the ``count`` column (a type schedule enumerates *types*, the
    Count column gives instances). A door whose comment references a NOTE that
    the plan classifies as "HOLLOW METAL DOOR" is reclassified to HM.

    Returns ``[{name, quantity, unit, provenance, material}]`` sorted by name.
    """
    hm_notes = _hm_door_notes(notes_text)
    door_counts: "Counter[str]" = Counter()
    frame_counts: "Counter[str]" = Counter()
    for row in door_rows or []:
        try:
            count = int(row.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            continue
        dm = _canon_mat((row.get("door_material") or "").strip().upper())
        fm = _canon_mat((row.get("frame_material") or "").strip().upper())
        # Note-aware HM reclassification (reads the plan's own note text).
        comment = row.get("comment") or ""
        note_ref = _NOTE_REF_RE.search(comment)
        if note_ref and note_ref.group(1) in hm_notes:
            dm = "HM"
        if dm:
            door_counts[dm] += count
        if fm:
            frame_counts[fm] += count

    out: List[dict] = []
    for code, n in door_counts.items():
        out.append({
            "name": "Doors-{}".format(code),
            "quantity": n,
            "unit": "EA",
            "provenance": "schedule_table",
            "material": code,
        })
    for code, n in frame_counts.items():
        out.append({
            "name": "Door Frames-{}".format(code),
            "quantity": n,
            "unit": "EA",
            "provenance": "schedule_table",
            "material": code,
        })
    out.sort(key=lambda d: d["name"])
    return out


def extract_door_component_counts(doc, notes_text: str = "") -> List[dict]:
    """Read a type+count door schedule from an open fitz.Document.

    Scans pages whose text mentions a DOOR SCHEDULE, finds the type+count door
    table, and returns material-grouped door / frame counts (or ``[]`` when the
    set has no type+count door schedule — e.g. a per-opening schedule, which
    keeps its existing ``schedule_extraction`` path). Never raises.
    """
    try:
        from bobbytailor.deterministic.schedule_extraction import _cells
    except Exception:  # noqa: BLE001
        return []
    all_notes = [notes_text] if notes_text else []
    door_rows: List[dict] = []
    try:
        page_count = doc.page_count
    except Exception:  # noqa: BLE001
        return []
    for i in range(page_count):
        try:
            page = doc[i]
            page_text = page.get_text() or ""
        except Exception:  # noqa: BLE001
            continue
        if "DOOR SCHEDULE" not in page_text.upper():
            continue
        all_notes.append(page_text)
        try:
            tables = list(page.find_tables().tables)
        except Exception:  # noqa: BLE001
            tables = []
        for t in tables:
            try:
                rows = [_cells(r) for r in t.extract()]
            except Exception:  # noqa: BLE001
                continue
            parsed = _parse_count_door_rows(rows)
            if parsed:
                door_rows.extend(parsed)
    if not door_rows:
        return []
    return count_doors_by_material(door_rows, notes_text="\n".join(all_notes))


# ── Comprehensive naming-relevant text extraction (AI naming-pass input) ──────

# A detail / section label line an estimator reads to learn the plan's naming
# ("TYPICAL S.C.C.P. JOINT DETAIL", "STAIR SECTION"). Whole-word DETAIL/SECTION.
_DETAIL_LABEL_RE = re.compile(r"\b(DETAIL|SECTION)\b", re.IGNORECASE)
# Pure callout references ("DETAIL 7/A-401") carry no naming signal — drop them.
_PURE_REF_RE = re.compile(r"^(DETAIL|SECTION)\s+\d+\s*/\s*[A-Z]?-?\d", re.IGNORECASE)
_MAX_DETAIL_LABELS = 120


def harvest_detail_labels(text: str) -> List[str]:
    """Distinct short detail / section label lines from plan text.

    These are the labels an estimator reads to learn a plan's own naming
    ("TYPICAL S.C.C.P. JOINT DETAIL", "STAIR SECTION", "RAMP RAIL SECTION").
    Pure callout refs ("DETAIL 7/A-401") are dropped. First-seen order,
    case-insensitive dedupe, capped. Never raises.
    """
    if not text:
        return []
    out: List[str] = []
    seen = set()
    for raw in text.splitlines():
        line = " ".join(raw.split()).strip()
        if not line or len(line) > 70:
            continue
        if not _DETAIL_LABEL_RE.search(line):
            continue
        if _PURE_REF_RE.match(line):
            continue
        # Must carry at least one word beyond the DETAIL/SECTION keyword.
        words = [w for w in re.split(r"[\s/]+", line) if w and not w.isdigit()]
        if len(words) < 2:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= _MAX_DETAIL_LABELS:
            break
    return out


def extract_naming_text(pages, doc=None) -> str:
    """Harvest the FULL naming-relevant plan text for the AI naming pass.

    An estimator learns a plan's OWN naming conventions by reading everything
    the drawing prints: keynotes, general notes, ALL detail / section labels,
    the abbreviation key, schedule headers / rows, legends and title blocks.
    This gathers that text (deterministically, no API) into ONE lightly
    structured document — the input to
    :func:`object_vocabulary.extract_naming_conventions`.

    The point is COMPLETENESS: rather than a truncated top-of-page snippet, it
    concatenates every page's text under ``=== PAGE n ===`` markers, then
    appends explicit ``=== ABBREVIATIONS ===`` and
    ``=== DETAIL / SECTION LABELS ===`` sections so those naming anchors are
    guaranteed present (and structured) even when a page's raw text buries or
    splits them.

    Args:
        pages: A list of page-text strings, or a list of page dicts with
               ``full_page_text`` / ``text`` / ``title_block_text`` keys.
        doc:   Optional open ``fitz.Document`` — when supplied, every page's
               ``get_text()`` is read directly (authoritative), superseding
               *pages* for the per-page body so the harvest is never limited to
               a caller-truncated snippet.

    Returns:
        One concatenated naming-text document (empty string for empty input).
        Never raises.
    """
    texts: List[str] = []
    if doc is not None:
        try:
            page_count = doc.page_count
        except Exception:  # noqa: BLE001
            page_count = 0
        for i in range(page_count):
            try:
                body = doc[i].get_text() or ""
            except Exception:  # noqa: BLE001
                body = ""
            if body.strip():
                texts.append(body)
    if not texts:
        texts = _pages_to_texts(pages)

    sections: List[str] = []
    for idx, body in enumerate(texts, 1):
        body = (body or "").strip()
        if body:
            sections.append("=== PAGE {} ===\n{}".format(idx, body))

    full_text = "\n".join(texts)

    try:
        abbr = parse_abbreviations(full_text)
    except Exception:  # noqa: BLE001
        abbr = OrderedDict()
    if abbr:
        lines = ["{} = {}".format(code, exp) for code, exp in abbr.items()]
        sections.append("=== ABBREVIATIONS ===\n" + "\n".join(lines))

    try:
        labels = harvest_detail_labels(full_text)
    except Exception:  # noqa: BLE001
        labels = []
    if labels:
        sections.append("=== DETAIL / SECTION LABELS ===\n" + "\n".join(labels))

    return "\n\n".join(sections)


# ── LEAN distilled naming text (AI naming-pass input, budget-capped) ──────────

# A construction naming-SIGNAL line: a plan line that mentions an object an
# estimator quantifies, or a schedule / keynote / general-note header. Used to
# distill the naming-relevant FRACTION of the page text (a small slice of a
# 30k-token plan) — never the full page body. Kept broad so it generalises
# across disciplines (structural, arch, civil, MEP) and plan vocabularies.
# A single leading ``\b`` gives every alternative a word-start boundary; there is
# deliberately NO trailing boundary so plurals / inflections match (BOLLARDS,
# DOORS, COLUMNS, ROOFING). Slight over-matching (e.g. "gasket") is harmless —
# the digest is char-capped and only used to seed the reader prompt.
_NAMING_SIGNAL_RE = re.compile(
    r"\b("
    r"bollard|column|ladder|guard\s*rail|guardrail|hand\s*rail|handrail|"
    r"stair|elevator|lift|escalator|downspout|gutter|canopy|mezzanine|"
    r"lintel|curb|catch\s*basin|manhole|hydrant|dock\s*leveler|dock\s*bumper|"
    r"wheel\s*stop|ramp|bench|sign|"
    r"cmu|masonry|block\s*wall|tilt.?up|tilt\s*panel|s\.?c\.?c\.?p|"
    r"concrete\s*panel|precast|eifs|partition|wall|"
    r"sealed\s*concrete|polished\s*concrete|slab|flooring|"
    r"exposed\s*structure|bar\s*joist|open\s*web\s*joist|roof|ceiling|"
    r"gas|pipe|piping|conduit|duct|fence|trench|"
    r"door|frame|window|"
    r"keynote|general\s+note|schedule|abbreviation"
    r")",
    re.IGNORECASE,
)
# Line-count and char-budget caps for the distilled naming digest. The char cap
# keeps the prompt LEAN (Bob's dumped ~35k input tokens of raw text → the reader
# pass returned invalid_json → no manifest). ~15k chars is comfortably under a
# safe request budget while retaining every naming anchor for the 4 real plans.
_MAX_NAMING_SIGNAL_LINES = 400
_MAX_DISTILLED_NAMING_CHARS = 15000


def harvest_naming_signal_lines(text: str, max_lines: int = _MAX_NAMING_SIGNAL_LINES) -> List[str]:
    """Distinct short plan lines carrying object-naming signal.

    Keeps ONLY lines matching :data:`_NAMING_SIGNAL_RE` (an object noun /
    schedule / keynote keyword) — the naming-relevant fraction an estimator
    reads, NOT the full page body. First-seen order, case-insensitive dedupe,
    length- and count-capped. Never raises.
    """
    if not text:
        return []
    out: List[str] = []
    seen = set()
    for raw in text.splitlines():
        line = " ".join(raw.split()).strip()
        if not line or len(line) > 160:
            continue
        if not _NAMING_SIGNAL_RE.search(line):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= max_lines:
            break
    return out


def distill_naming_text(
    pages,
    doc=None,
    max_chars: int = _MAX_DISTILLED_NAMING_CHARS,
) -> str:
    """Distill the LEAN, budget-capped naming text for the AI naming pass.

    Unlike :func:`extract_naming_text` (which concatenates every page's FULL
    body — 30k+ tokens on a large plan), this harvests only the naming-relevant
    slice — the abbreviation key, detail / section labels, and object-noun /
    keynote / schedule lines — into ONE compact digest capped at *max_chars*.
    This is the LEAN prompt input for
    :func:`object_vocabulary.extract_naming_conventions`: it preserves the
    naming signal an estimator reads while cutting the raw-page dump that
    starved / truncated the reader pass on Bob's (invalid_json → no manifest).

    Order is truncation-safe: the dense ABBREVIATIONS and DETAIL / SECTION
    LABELS sections come FIRST (highest naming density), then the object-noun /
    keynote lines, so the identifying signal survives even when a 40-page plan
    overflows the budget (truncated with an explicit marker). Never raises.

    Args:
        pages: A list of page-text strings, or page dicts with
               ``full_page_text`` / ``text`` / ``title_block_text`` keys.
        doc:   Optional open ``fitz.Document`` — when supplied every page's
               ``get_text()`` is read directly (authoritative), superseding
               *pages* for the per-page body.
        max_chars: Hard char cap for the returned digest (truncated with a
               marker when exceeded).

    Returns:
        A compact naming-text digest (empty string for empty input).
    """
    texts: List[str] = []
    if doc is not None:
        try:
            page_count = doc.page_count
        except Exception:  # noqa: BLE001
            page_count = 0
        for i in range(page_count):
            try:
                body = doc[i].get_text() or ""
            except Exception:  # noqa: BLE001
                body = ""
            if body.strip():
                texts.append(body)
    if not texts:
        texts = _pages_to_texts(pages)

    full_text = "\n".join(texts)
    if not full_text.strip():
        return ""

    sections: List[str] = []

    try:
        abbr = parse_abbreviations(full_text)
    except Exception:  # noqa: BLE001
        abbr = OrderedDict()
    if abbr:
        lines = ["{} = {}".format(code, exp) for code, exp in abbr.items()]
        sections.append("=== ABBREVIATIONS ===\n" + "\n".join(lines))

    try:
        labels = harvest_detail_labels(full_text)
    except Exception:  # noqa: BLE001
        labels = []
    if labels:
        sections.append("=== DETAIL / SECTION LABELS ===\n" + "\n".join(labels))

    try:
        signal = harvest_naming_signal_lines(full_text)
    except Exception:  # noqa: BLE001
        signal = []
    if signal:
        sections.append("=== KEYNOTES / NOTES / SCHEDULES ===\n" + "\n".join(signal))

    digest = "\n\n".join(sections)
    if len(digest) > max_chars:
        digest = digest[:max_chars].rstrip() + "\n… [naming text truncated]"
    return digest


# ── Library assembly + merge with the LLM vocabulary ──────────────────────────


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _dedup_library(entries: List[dict]) -> List[dict]:
    """De-duplicate library entries by normalised name; union aliases; keep the
    first non-empty basis/unit. First-seen order preserved."""
    by_name: "OrderedDict[str, dict]" = OrderedDict()
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        name = (e.get("name") or "").strip()
        if not name:
            continue
        key = _norm(name)
        aliases = [a for a in (e.get("aliases") or []) if isinstance(a, str) and a.strip()]
        if key not in by_name:
            by_name[key] = {
                "name": name,
                "aliases": list(dict.fromkeys(aliases)),
                "basis": e.get("basis") if e.get("basis") in _VALID_BASES else None,
                "unit": e.get("unit") or None,
                "source": e.get("source") or "",
            }
        else:
            cur = by_name[key]
            for a in aliases:
                if a not in cur["aliases"]:
                    cur["aliases"].append(a)
            if cur["basis"] is None and e.get("basis") in _VALID_BASES:
                cur["basis"] = e.get("basis")
            if not cur["unit"] and e.get("unit"):
                cur["unit"] = e.get("unit")
    return list(by_name.values())


def _pages_to_texts(pages) -> List[str]:
    """Normalise the ``pages`` argument to a list of page-text strings.

    Accepts a list of strings (page text) or a list of page dicts carrying
    ``full_page_text`` / ``title_block_text`` / ``text`` keys.
    """
    texts: List[str] = []
    for p in pages or []:
        if isinstance(p, str):
            if p.strip():
                texts.append(p)
        elif isinstance(p, dict):
            for key in ("full_page_text", "text", "title_block_text"):
                val = p.get(key)
                if isinstance(val, str) and val.strip():
                    texts.append(val)
    return texts


def harvest_component_library(pages, doc=None) -> List[dict]:
    """Harvest the deterministic component library from plan text (+ schedules).

    Args:
        pages: A list of page-text strings, or a list of page dicts with
               ``full_page_text`` / ``text`` / ``title_block_text`` keys.
        doc:   Optional open ``fitz.Document`` — when supplied, door / frame
               components are counted from a type+count door schedule and added
               to the library (with quantities). Absent, the library carries the
               abbreviation-composed door NAMES only (no quantities).

    Returns:
        A de-duplicated ``[{name, aliases, basis, unit, source}]`` library. The
        door-schedule entries additionally carry ``quantity`` / ``provenance``.
        Empty input yields ``[]`` (prior behaviour). Never raises.
    """
    texts = _pages_to_texts(pages)
    full_text = "\n".join(texts)

    entries: List[dict] = []

    # 1. Abbreviation key -> alias mappings + composed door / frame names.
    try:
        abbr = parse_abbreviations(full_text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("harvest_component_library: abbreviation parse failed: %s", exc)
        abbr = OrderedDict()
    entries.extend(abbreviations_to_library(abbr))

    # 2. Keynotes / general notes -> conservative object nouns.
    try:
        entries.extend(harvest_from_notes(full_text))
    except Exception as exc:  # noqa: BLE001
        logger.warning("harvest_component_library: note harvest failed: %s", exc)

    # 3. Door schedule counts (needs the PDF for table extraction).
    if doc is not None:
        try:
            counts = extract_door_component_counts(doc, notes_text=full_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("harvest_component_library: door count failed: %s", exc)
            counts = []
        for c in counts:
            entries.append({
                "name": c["name"],
                "aliases": [],
                "basis": "count",
                "unit": c.get("unit") or "EA",
                "source": c.get("provenance") or "schedule_table",
                "quantity": c.get("quantity"),
            })

    library = _dedup_library(entries)
    # Preserve any quantity harvested from the schedule (dedup drops unknown keys).
    qty_by_name = {}
    for e in entries:
        if isinstance(e, dict) and e.get("quantity") is not None:
            qty_by_name[_norm(e.get("name") or "")] = e["quantity"]
    for entry in library:
        q = qty_by_name.get(_norm(entry["name"]))
        if q is not None:
            entry["quantity"] = q
    return library


# ── Deterministic measure-basis classifier (authoritative over the LLM) ───────

# Ordered ``(compiled pattern, basis)`` rules — FIRST match wins, exactly like
# the aggregator's ITEM_NAME_MAP. The pattern is searched against a normalised
# ``name + aliases`` haystack, so classification is derived from the plan's own
# printed vocabulary with ZERO API variance. This is the authoritative measure
# basis: a match here overrides whatever basis the LLM vocabulary pass guessed,
# so floor/roof/wall-area binding (footprint SF, LF×height) is identical every
# run. Extend by adding rows — ordering is the only contract (specific before
# generic within a category; counted discrete items before area/linear so a
# "dock door" / "door frame" never collapses into a wall).
_MEASURE_BASIS_RULES = [
    # ── count: discrete items counted each ────────────────────────────────
    (r"\bbollard", "count"),
    (r"\bcolumn", "count"),
    (r"\bladder", "count"),
    (r"\bstair", "count"),
    (r"\blift\b|\belevator", "count"),
    (r"\bhydrant", "count"),
    (r"catch\s*basin", "count"),
    (r"\bmanhole", "count"),
    (r"\bdownspout", "count"),
    (r"dock\s*leveler", "count"),
    (r"dock\s*door", "count"),
    (r"dock\s*bumper", "count"),
    (r"\bdoor", "count"),          # doors AND door frames are counted
    (r"\bframe", "count"),
    (r"\bsign\b", "count"),
    (r"\bbench\b", "count"),
    # ── floor_area: slab / floor coverings spanning the building floor ─────
    (r"sealed\s*concrete|polished\s*concrete", "floor_area"),
    (r"slab.?on.?grade|\bsog\b", "floor_area"),
    (r"concrete\s*floor|concrete\s*slab", "floor_area"),
    (r"\bflooring\b|floor\s*tile", "floor_area"),
    (r"\bvct\b|\blvt\b|\bcarpet\b|ceramic\s*tile|porcelain\s*tile|vinyl\s*tile", "floor_area"),
    # ── wall_area: vertical walls quantified as length × height ────────────
    (r"\bcmu\b", "wall_area"),
    (r"masonry\s*wall|concrete\s*masonry", "wall_area"),
    (r"block\s*wall", "wall_area"),
    (r"tilt.?up|tilt\s*panel", "wall_area"),
    (r"s\.?c\.?c\.?p\.?", "wall_area"),   # site-cast concrete panel
    (r"concrete\s*panel|precast\s*panel", "wall_area"),
    (r"\bpartition", "wall_area"),
    (r"(?:interior|exterior)\s*wall|\bwall\b", "wall_area"),
    # ── roof_area: roof / ceiling / exposed structure spanning overhead ────
    (r"exposed\s*structure|exposed\s*deck|exposed\s*roof", "roof_area"),
    (r"open\s*web\s*joist|bar\s*joist", "roof_area"),
    (r"\broof\b", "roof_area"),
    (r"\bceiling", "roof_area"),
    # ── linear: linear-foot items that are NOT walls ──────────────────────
    (r"guard\s*rail|guardrail", "linear"),
    (r"hand\s*rail|handrail", "linear"),
    (r"\brail\b", "linear"),
    (r"\bcurb\b", "linear"),
    (r"\bgutter\b", "linear"),
    (r"\bpipe\b|piping", "linear"),
    (r"\bconduit\b", "linear"),
    (r"\bduct\b", "linear"),
    (r"\bfence\b", "linear"),
    (r"\btrench", "linear"),
    (r"\blintel", "linear"),
]

# Compile once at import — the rules never change at runtime.
_MEASURE_BASIS_MAP = [(re.compile(pat, re.IGNORECASE), basis) for pat, basis in _MEASURE_BASIS_RULES]


def classify_basis(name: str, aliases=()) -> Optional[str]:
    """Deterministically classify an object's MEASURE BASIS from its own text.

    Returns one of ``count`` / ``linear`` / ``wall_area`` / ``floor_area`` /
    ``roof_area`` when the name (or any alias) matches the standard
    construction-vocabulary rules, else ``None`` (unknown — the LLM basis may
    fill). No API call, no run-to-run variance — this is the authoritative
    basis in :func:`merge_with_vocabulary`.

    Args:
        name:    The object/component name (e.g. ``"Exposed Structure"``).
        aliases: Optional additional labels searched alongside the name.
    """
    parts = [name or ""]
    for a in aliases or ():
        if isinstance(a, str) and a.strip():
            parts.append(a)
    hay = _norm(" ".join(p for p in parts if p))
    if not hay:
        return None
    for pattern, basis in _MEASURE_BASIS_MAP:
        if pattern.search(hay):
            return basis
    return None


def apply_deterministic_basis(entries: List[dict]) -> List[dict]:
    """Overwrite each entry's ``basis`` with :func:`classify_basis` when known.

    Authoritative: a deterministic match REPLACES the (possibly LLM-guessed)
    basis; ``None`` leaves the existing basis untouched. Mutates and returns
    *entries* in place. Additive — an entry the classifier cannot place keeps
    whatever basis it already had.
    """
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        det = classify_basis(entry.get("name") or "", entry.get("aliases") or ())
        if det is not None:
            entry["basis"] = det
    return entries


# ── Estimator take-off name normalization (safety net) ────────────────────────

# General ``(regex, canonical estimator take-off name)`` rules — FIRST match
# wins, exactly like the aggregator's ITEM_NAME_MAP. An estimator reads the
# plan's own abbreviation ("S.C.C.P." = Site Cast Concrete Panel) or literal
# words ("exposed metal roof deck", "polished slab on grade") and WRITES the
# industry-standard take-off item name on the quantity take-off ("Tilt Up Wall",
# "Exposed Structure", "Sealed Concrete"). This table reproduces that read so a
# correctly-measured quantity carries the estimator's vocabulary — the scorer
# matches on the estimator term, not the plan's raw label (a raw "S.C.C.P."
# shares no tokens with "Tilt Up Wall" and scores MISSING).
#
# GENERAL construction terminology only (generalises to any plan — never a
# project-specific name). Data-driven / extensible: add a row to cover a new
# abbreviation. Authoritative over the raw plan label, but BELOW a human learned
# correction — it is applied to the naming library, which the aggregator resolves
# AFTER the learned-vocabulary lookup (learned > library > static), so a human
# rename always wins.
_ESTIMATOR_NAME_RULES = [
    # ── Tilt-up / site-cast concrete wall panels → "Tilt Up Wall" ──────────
    (r"\bs\.?\s*c\.?\s*c\.?\s*p\.?", "Tilt Up Wall"),   # S.C.C.P. = site cast concrete panel
    (r"site.?cast.*concrete.*panel", "Tilt Up Wall"),
    (r"tilt.?up|tilt\s*wall|tilt\s*panel", "Tilt Up Wall"),
    # ── Exposed metal roof deck / open structure → "Exposed Structure" ─────
    (r"metal\s*roof\s*deck", "Exposed Structure"),
    (r"roof\s*assembly", "Exposed Structure"),
    (r"(concrete\s*)?slab\s*on\s*metal\s*deck", "Exposed Structure"),
    (r"exposed.*(structure|deck|roof|joist)|open\s*web\s*joist|bar\s*joist", "Exposed Structure"),
    # ── Sealed / polished slab-on-grade → "Sealed Concrete" ───────────────
    (r"sealed\s*concrete|polished\s*concrete", "Sealed Concrete"),
    (r"(sealed|polished).*slab|slab.*(sealed|polished)", "Sealed Concrete"),
    # ── Masonry → "CMU Wall" ──────────────────────────────────────────────
    (r"\bcmu\b|concrete\s*masonry\s*unit", "CMU Wall"),
    (r"(masonry|block)\s*wall", "CMU Wall"),
    # ── Hollow-metal door LEAF (never a frame) → "Doors-HM" ────────────────
    (r"hollow.?metal.*door(?!\s*frame)|door(?!\s*frame).*hollow.?metal", "Doors-HM"),
]

# Compile once at import — the rules never change at runtime.
_ESTIMATOR_NAME_MAP = [
    (re.compile(pat, re.IGNORECASE), canonical) for pat, canonical in _ESTIMATOR_NAME_RULES
]


def normalize_estimator_name(name: str, aliases=()) -> tuple:
    """Map a detected/AI object name to its STANDARD estimator take-off name.

    First-match-wins over :data:`_ESTIMATOR_NAME_RULES`: a raw plan abbreviation
    ("S.C.C.P.") or the plan's own words ("site cast concrete panel", "metal roof
    deck", "polished slab on grade") normalise to the industry-standard take-off
    item name an estimator writes ("Tilt Up Wall", "Exposed Structure", "Sealed
    Concrete"). The name AND aliases are searched, so a correct alias rescues a
    mislabelled canonical.

    Returns ``(canonical_name, aliases)``. When a rule fires and the canonical
    differs from the input, the ORIGINAL name is PRESERVED (prepended) in the
    returned aliases so a later drawing-text lookup still resolves the object via
    its plan term (the drawing prints "S.C.C.P." next to the wall). An unmatched
    name is returned UNCHANGED — no false remap. Never raises.
    """
    original = (name or "").strip()
    out_aliases = [a for a in (aliases or []) if isinstance(a, str) and a.strip()]
    if not original:
        return original, list(out_aliases)
    haystack = _norm(" ".join([original] + out_aliases))
    for pattern, canonical in _ESTIMATOR_NAME_MAP:
        if pattern.search(haystack):
            if _norm(canonical) == _norm(original):
                return original, list(out_aliases)   # already the estimator term
            preserved = list(out_aliases)
            if not any(_norm(a) == _norm(original) for a in preserved):
                preserved.insert(0, original)        # keep the plan term for binding
            return canonical, preserved
    return original, list(out_aliases)


def apply_estimator_names(entries: List[dict]) -> List[dict]:
    """Rewrite each library entry's ``name`` to the estimator take-off term.

    Applies :func:`normalize_estimator_name` in place: a matched entry's ``name``
    becomes the standard take-off item name and its former label is preserved as
    an alias (so drawing-text binding is unaffected). Entries the table cannot
    place keep their name. Mutates and returns *entries*. Additive — never raises.
    """
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or ""
        canonical, aliases = normalize_estimator_name(name, entry.get("aliases") or ())
        if _norm(canonical) != _norm(name):
            entry["name"] = canonical
            entry["aliases"] = list(dict.fromkeys(aliases))
    return entries


def merge_with_vocabulary(
    deterministic: List[dict],
    llm_objects: Optional[List[dict]] = None,
) -> List[dict]:
    """Merge the deterministic library with the LLM vocabulary pass.

    Deterministic entries are AUTHORITATIVE for names + aliases. The LLM
    vocabulary (a) fills a deterministic entry's ``basis`` where the printed text
    could not classify it, and (b) contributes object types the text missed.
    Everything is additive — an empty deterministic library returns the LLM
    objects unchanged (prior behaviour), and vice-versa.
    """
    det = _dedup_library(deterministic or [])
    # Index deterministic coverage by every name + alias for cheap membership.
    covered = {}
    for entry in det:
        for label in [entry["name"]] + list(entry.get("aliases") or []):
            covered[_norm(label)] = entry

    for obj in llm_objects or []:
        if not isinstance(obj, dict):
            continue
        name = (obj.get("name") or "").strip()
        if not name:
            continue
        obj_basis = obj.get("basis") if obj.get("basis") in _VALID_BASES else None
        obj_aliases = [a for a in (obj.get("aliases") or []) if isinstance(a, str)]
        # Does the LLM object correspond to a deterministic entry (name/alias)?
        match = covered.get(_norm(name))
        if match is None:
            for a in obj_aliases:
                match = covered.get(_norm(a))
                if match is not None:
                    break
        if match is not None:
            # Deterministic name/aliases win; LLM only fills a missing basis/unit.
            if match.get("basis") is None and obj_basis is not None:
                match["basis"] = obj_basis
            if not match.get("unit") and obj.get("unit"):
                match["unit"] = obj.get("unit")
            continue
        # New object the text missed — add it (LLM-sourced).
        new_entry = {
            "name": name,
            "aliases": list(dict.fromkeys(obj_aliases)),
            "basis": obj_basis,
            "unit": obj.get("unit") or None,
            "source": "llm_vocabulary",
        }
        det.append(new_entry)
        for label in [name] + obj_aliases:
            covered.setdefault(_norm(label), new_entry)
    # Deterministic measure-basis is AUTHORITATIVE: a keyword match overrides
    # the LLM-provided basis (e.g. an LLM "Exposed Structure" basis=count is
    # corrected to roof_area), so area binding is identical every run. The LLM
    # basis only survives where classify_basis returns None.
    apply_deterministic_basis(det)
    return det


# ── Naming-convention merge (binding_hint / variant / thickness / height) ─────

# Default estimator unit per measure basis (only used to seed a NEW naming
# object the deterministic text never named — deterministic units are authoritative).
_UNIT_BY_BASIS = {
    "count": "EA",
    "linear": "LF",
    "wall_area": "SF",
    "floor_area": "SF",
    "roof_area": "SF",
}

# Binding-carrying fields an AI naming convention contributes to a library
# entry (never overwritten once set; deterministic names/aliases stay
# authoritative). Kept semantic-only — strings, never numbers.
_BINDING_FIELDS = ("binding_hint", "variant", "thickness_in", "height_ft")


def merge_with_naming_conventions(
    deterministic: List[dict],
    conventions: Optional[List[dict]] = None,
) -> List[dict]:
    """Merge the deterministic library with the AI NAMING-CONVENTION library.

    The naming conventions
    (:func:`object_vocabulary.extract_naming_conventions`) carry each object's
    ``canonical_name`` / ``aliases`` / ``basis`` PLUS the binding fields the
    geometry binder needs: ``binding_hint`` (structural_grid_symbol,
    perimeter_jamb_symbol, exterior_wall, interior_wall, masonry_wall, ...),
    ``variant`` (interior/exterior) and printed ``thickness_in`` / ``height_ft``
    (as strings).

    Merge discipline (same authority model as :func:`merge_with_vocabulary`):
    deterministic entries are AUTHORITATIVE for names + aliases; the AI naming
    pass (a) fills a deterministic entry's missing ``basis`` and the binding
    fields, and (b) contributes named objects the printed text missed. Additive:
    empty conventions return the deterministic library unchanged, and vice-versa.
    The deterministic measure-basis classifier stays authoritative at the end.
    """
    det = _dedup_library(deterministic or [])
    covered = {}
    for entry in det:
        for label in [entry["name"]] + list(entry.get("aliases") or []):
            covered[_norm(label)] = entry

    for conv in conventions or []:
        if not isinstance(conv, dict):
            continue
        name = (conv.get("canonical_name") or conv.get("name") or "").strip()
        if not name:
            continue
        aliases = [a for a in (conv.get("aliases") or []) if isinstance(a, str) and a.strip()]
        basis = conv.get("basis") if conv.get("basis") in _VALID_BASES else None

        match = covered.get(_norm(name))
        if match is None:
            for a in aliases:
                match = covered.get(_norm(a))
                if match is not None:
                    break

        if match is not None:
            # Deterministic name/aliases win; the AI fills basis + binding fields.
            for a in aliases:
                if a not in match["aliases"]:
                    match["aliases"].append(a)
            if match.get("basis") is None and basis is not None:
                match["basis"] = basis
            for field in _BINDING_FIELDS:
                val = conv.get(field)
                if isinstance(val, str) and val.strip() and not match.get(field):
                    match[field] = val.strip()
            continue

        # New object the printed text missed — add it (naming-convention-sourced).
        new_entry = {
            "name": name,
            "aliases": list(dict.fromkeys(aliases)),
            "basis": basis,
            "unit": _UNIT_BY_BASIS.get(basis or "", None),
            "source": "naming_convention",
        }
        for field in _BINDING_FIELDS:
            val = conv.get(field)
            if isinstance(val, str) and val.strip():
                new_entry[field] = val.strip()
        det.append(new_entry)
        for label in [name] + aliases:
            covered.setdefault(_norm(label), new_entry)

    # Deterministic measure-basis is AUTHORITATIVE (identical every run).
    apply_deterministic_basis(det)
    # Estimator take-off name normalization (safety net): rewrite a raw plan
    # label / abbreviation the naming pass emitted ("S.C.C.P.", "Metal Roof
    # Deck") to the standard take-off item name ("Tilt Up Wall", "Exposed
    # Structure"), preserving the plan term as an alias so binding is unchanged.
    # Runs AFTER basis classification (basis is derived from the plan's own
    # vocabulary before the rename) and is authoritative over the raw label; a
    # human learned correction still wins because the aggregator consults the
    # learned vocabulary BEFORE resolving this library.
    apply_estimator_names(det)
    return det


# ── Consumers: gallery labels + aggregation alias resolution ──────────────────


def library_labels(library: List[dict]) -> List[str]:
    """Flatten a library to a deduped ``names + aliases`` candidate-label feed.

    Case-insensitive dedupe, first-seen order preserved. Mirrors
    :func:`object_vocabulary.vocabulary_labels` so the two feeds merge cleanly.
    """
    labels: List[str] = []
    seen = set()
    for entry in library or []:
        if not isinstance(entry, dict):
            continue
        for value in [entry.get("name")] + list(entry.get("aliases") or []):
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text or len(text) > 80:
                continue
            norm = text.lower()
            if norm not in seen:
                seen.add(norm)
                labels.append(text)
    return labels


def resolve_library_name(description: str, library: List[dict]) -> Optional[tuple]:
    """Resolve a raw detected description to a library ``(name, unit)`` via aliases.

    Analogous to the removed ``manifest.resolve``: the LONGEST library name or
    alias that appears as a whole phrase in the description wins (so specific
    labels beat generic ones). Returns ``None`` on no match — conservative, so a
    library miss falls through to the existing naming path unchanged.
    """
    if not description or not library:
        return None
    low = _norm(description)
    best = None  # (match_len, name, unit)
    for entry in library:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or ""
        unit = entry.get("unit") or ""
        for label in [name] + list(entry.get("aliases") or []):
            if not isinstance(label, str):
                continue
            lab = _norm(label)
            if not lab:
                continue
            pattern = r"\b" + re.escape(lab) + r"\b"
            if re.search(pattern, low):
                if best is None or len(lab) > best[0]:
                    best = (len(lab), name, unit)
    if best is None:
        return None
    return best[1], best[2]
