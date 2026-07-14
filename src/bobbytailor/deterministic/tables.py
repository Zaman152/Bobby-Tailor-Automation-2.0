"""Generalized deterministic schedule extraction (beyond door schedules).

Architectural drawing sets print window / finish / fixture / equipment /
keynote schedules as real tables in the PDF text layer. Those tables hold
EXACT printed data that must be *read* deterministically via
``page.find_tables()``, never vision-guessed. This module parameterizes the
proven ``schedule_extraction`` door pattern (token-density column detection +
coverage gate) by schedule kind — it generalizes the skeleton, it does not
fork it: door schedules stay in ``schedule_extraction.py`` and kind='door'
delegates to that extractor.

IMPORTANT — every schedule count is an exact lower bound / type breakdown,
NOT an installed count (Pitfall 10): a schedule enumerates *types/openings*; in
repetitive buildings (hotels) instances repeat per unit/floor and are counted
on the plans. Instance counts come from plan-body symbol clustering
(``deterministic/symbols.py``); reconciliation flags residuals. This mirrors
the honesty policy already documented in ``schedule_extraction.py``.

Every extracted ``ScheduleTable`` records its ``bbox_pt`` so the fusion layer
can mask schedule regions out of measurement and the symbols module can
exclude them from clustering.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from bobbytailor.deterministic.schedule_extraction import (
    _cells,
    extract_door_schedule,
    _is_door_table,
    _material_columns,
    _tag_column,
)

logger = logging.getLogger(__name__)

# Threat model: cap cell text before it can reach prompts/UI.
MAX_CELL_CHARS = 500
# Coverage gate thresholds mirroring schedule_extraction._is_door_table.
MIN_TAG_ROWS = 3
MIN_COVERAGE_RATIO = 0.4
# Tag columns live near the left edge of a schedule.
MAX_TAG_COL = 4

# ── Per-kind vocabularies ─────────────────────────────────────────────────────

_WINDOW_TAG_RE = re.compile(r"^(?:W-?\d{1,3}[A-Z]?|WIN-?\d{1,3}[A-Z]?)$", re.IGNORECASE)
_ROOM_TAG_RE = re.compile(r"^\d{2,4}[A-Z]?$")
_FIXTURE_TAG_RE = re.compile(
    r"^(?:P|PL|L|S|WC|UR|LAV|SK|MS|DF|EWC|WH)-?\d{1,3}[A-Z]?$", re.IGNORECASE
)
_EQUIPMENT_TAG_RE = re.compile(
    r"^(?:EF|RTU|AHU|FCU|CU|HP|UH|EUH|VAV|ERV|MAU|WH|GWH|EWH)-?\d{0,3}[A-Z]?$",
    re.IGNORECASE,
)
_KEYNOTE_TAG_RE = re.compile(r"^(?:\d{1,3}|\d{1,2}\.\d{1,2})$")

# Finish-material tokens (VCT/CPT/ACT plus common companions).
_FINISH_MAT_RE = re.compile(
    r"\b(?:VCT|CPT|ACT|SC|SV|LVT|RB|VB|CT|PT|GWB|GYP|EPXY|EPOXY|CONC)(?:-?\d{1,2}[A-Z]?)?\b",
    re.IGNORECASE,
)


def _window_value(cell: str) -> bool:
    """A window row carries a size, type, or material somewhere."""
    return bool(
        re.search(r"\d+['\"-]|\bALUM\b|\bVINYL\b|\bFIXED\b|\bCASEMENT\b|\bSTOREFRONT\b",
                  cell, re.IGNORECASE)
    )


def _finish_value(cell: str) -> bool:
    return bool(_FINISH_MAT_RE.search(cell))


def _nonempty_value(cell: str) -> bool:
    return bool(cell.strip())


def _keynote_value(cell: str) -> bool:
    """Keynote rows pair a numeric key with a prose description."""
    return len(cell.strip()) >= 15


# Each kind defines: (a) tag-token predicate vocabulary, (b) required header
# tokens (any-of, searched over the first rows), (c) coverage-gate thresholds
# mirroring _is_door_table (>=3 tag rows, >=40% value coverage).
SCHEDULE_KIND_VOCABULARIES: Dict[str, dict] = {
    "door": {
        # Delegated to schedule_extraction.extract_door_schedule — kept here so
        # the registry is the single source of truth for supported kinds.
        "delegate": True,
        "header_tokens": {"DOOR"},
        "min_rows": MIN_TAG_ROWS,
        "min_coverage": MIN_COVERAGE_RATIO,
    },
    "window": {
        "tag_re": _WINDOW_TAG_RE,
        "value_predicate": _window_value,
        "header_tokens": {"WINDOW", "WIN.", "GLAZING"},
        "min_rows": MIN_TAG_ROWS,
        "min_coverage": MIN_COVERAGE_RATIO,
    },
    "finish": {
        "tag_re": _ROOM_TAG_RE,
        "value_predicate": _finish_value,
        "header_tokens": {"FINISH", "FINISHES"},
        "min_rows": MIN_TAG_ROWS,
        "min_coverage": MIN_COVERAGE_RATIO,
    },
    "fixture": {
        "tag_re": _FIXTURE_TAG_RE,
        "value_predicate": _nonempty_value,
        "header_tokens": {"FIXTURE", "PLUMBING", "FIXTURES"},
        "min_rows": MIN_TAG_ROWS,
        "min_coverage": MIN_COVERAGE_RATIO,
    },
    "equipment": {
        "tag_re": _EQUIPMENT_TAG_RE,
        "value_predicate": _nonempty_value,
        "header_tokens": {"EQUIPMENT", "MECHANICAL", "HVAC", "SCHEDULE"},
        "min_rows": MIN_TAG_ROWS,
        "min_coverage": MIN_COVERAGE_RATIO,
    },
    "keynote": {
        "tag_re": _KEYNOTE_TAG_RE,
        "value_predicate": _keynote_value,
        "header_tokens": {"KEYNOTE", "KEYNOTES", "KEYED", "NOTES"},
        "min_rows": MIN_TAG_ROWS,
        "min_coverage": MIN_COVERAGE_RATIO,
    },
}


@dataclass
class ScheduleTable:
    """One deterministically parsed schedule table."""

    kind: str                      # door|window|finish|fixture|equipment|keynote
    rows: List[dict] = field(default_factory=list)
    page_index: int = 0
    bbox_pt: tuple = (0.0, 0.0, 0.0, 0.0)
    confidence: str = "medium"     # high | medium

    def to_dict(self) -> dict:
        return asdict(self)


# ── Generalized parsing helpers (parameterized door-pattern skeleton) ────────


def _sanitize_rows(table) -> List[List[str]]:
    """``_cells``-style sanitization plus a per-cell length cap (threat model)."""
    try:
        raw = table.extract()
    except Exception:  # noqa: BLE001
        return []
    return [[c[:MAX_CELL_CHARS] for c in _cells(r)] for r in raw]


def _kind_tag_column(rows: List[List[str]], tag_re) -> Optional[int]:
    """Leftmost-4 column with the highest tag-token density (door pattern)."""
    if not rows:
        return None
    width = max(len(r) for r in rows)
    best_col, best_hits = None, 0
    for c in range(min(width, MAX_TAG_COL)):
        hits = sum(
            1
            for r in rows
            if c < len(r) and any(tag_re.match(t) for t in r[c].split())
        )
        if hits > best_hits:
            best_col, best_hits = c, hits
    return best_col if best_hits >= MIN_TAG_ROWS else None


def _has_header_tokens(rows: List[List[str]], header_tokens: set) -> bool:
    """Any required header token appears in the table's first rows."""
    tokens = {t.upper() for t in header_tokens}
    for r in rows[:3]:
        for cell in r:
            up = cell.upper()
            if any(tok in up for tok in tokens):
                return True
    return False


def _coverage(
    rows: List[List[str]],
    tag_col: int,
    tag_re,
    value_predicate: Callable[[str], bool],
) -> tuple:
    """(tag_rows, covered): tag rows whose OTHER cells carry expected values.

    Mirrors ``schedule_extraction._material_coverage`` — a genuine schedule
    lists values on most rows; tag callout clusters on floor plans do not.
    """
    tag_rows = 0
    covered = 0
    for r in rows:
        toks = [t for t in (r[tag_col].split() if tag_col < len(r) else []) if tag_re.match(t)]
        if not toks:
            continue
        tag_rows += 1
        others = [c for i, c in enumerate(r) if i != tag_col]
        if any(value_predicate(c) for c in others):
            covered += 1
    return tag_rows, covered


def _passes_gate(tag_rows: int, covered: int, vocab: dict) -> bool:
    if tag_rows < vocab["min_rows"]:
        return False
    return covered >= vocab["min_rows"] and (covered / tag_rows) >= vocab["min_coverage"]


def _header_row_index(rows: List[List[str]], tag_re) -> Optional[int]:
    """First row before any tag row that looks like a header (alpha cells)."""
    for i, r in enumerate(rows[:3]):
        cells = [c for c in r if c.strip()]
        if not cells:
            continue
        if any(tag_re.match(t) for c in r for t in c.split()):
            return None  # tag rows started before any header row appeared
        if sum(1 for c in cells if re.search(r"[A-Za-z]{2,}", c)) >= max(1, len(cells) // 2):
            return i
    return None


def _structured_rows(
    rows: List[List[str]],
    tag_col: int,
    tag_re,
) -> List[dict]:
    """Structured row dicts: TAG plus header-keyed (or COL{i}) cells."""
    header_idx = _header_row_index(rows, tag_re)
    header = rows[header_idx] if header_idx is not None else []

    out: List[dict] = []
    for i, r in enumerate(rows):
        if header_idx is not None and i == header_idx:
            continue
        toks = [t for t in (r[tag_col].split() if tag_col < len(r) else []) if tag_re.match(t)]
        if not toks:
            continue
        row: dict = {"TAG": toks[0]}
        if len(toks) > 1:
            row["TAGS"] = toks
        for c, cell in enumerate(r):
            if c == tag_col or not cell.strip():
                continue
            if c < len(header) and header[c].strip():
                key = header[c].strip().upper()[:40]
            else:
                key = f"COL{c}"
            row[key] = cell
        out.append(row)
    return out


def _table_bbox(table) -> tuple:
    bbox = getattr(table, "bbox", None)
    if bbox is None:
        return (0.0, 0.0, 0.0, 0.0)
    try:
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError, IndexError):
        return (0.0, 0.0, 0.0, 0.0)


# ── Door delegation (generalize, don't fork) ─────────────────────────────────


def _door_schedule_tables(doc) -> List[ScheduleTable]:
    """Delegate door parsing to ``schedule_extraction`` and attach bboxes.

    Row extraction/counting is the existing extractor's verbatim output; this
    wrapper only locates each door table's bbox with the SAME imported gates
    so the fusion layer gets region masks for door schedules too.
    """
    ds = extract_door_schedule(doc)
    if not ds.found:
        return []

    # Locate door-table bboxes per page using the imported door gates.
    page_bboxes: Dict[int, list] = {}
    for page_no in ds.pages:
        page = doc[page_no - 1]
        try:
            tables = list(page.find_tables().tables)
        except Exception:  # noqa: BLE001
            tables = []
        for t in tables:
            rows = _sanitize_rows(t)
            if not rows:
                continue
            tag_col = _tag_column(rows)
            if tag_col is None:
                continue
            panel_col, frame_col = _material_columns(rows, tag_col)
            if not _is_door_table(rows, tag_col, panel_col, frame_col):
                continue
            page_bboxes.setdefault(page_no - 1, []).append(_table_bbox(t))

    out: List[ScheduleTable] = []
    by_page: Dict[int, List[dict]] = {}
    for rec in ds.records:
        by_page.setdefault(rec.page - 1, []).append(
            {
                "TAG": rec.tag,
                "ROOM": rec.room,
                "PANEL_MATERIAL": rec.panel_material,
                "FRAME_MATERIAL": rec.frame_material,
            }
        )
    for page_index, rows in sorted(by_page.items()):
        bboxes = page_bboxes.get(page_index, [])
        bbox = bboxes[0] if len(bboxes) == 1 else _union_bboxes(bboxes)
        out.append(
            ScheduleTable(
                kind="door",
                rows=rows,
                page_index=page_index,
                bbox_pt=bbox,
                confidence="high",
            )
        )
    return out


def _union_bboxes(bboxes: Sequence[tuple]) -> tuple:
    if not bboxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        max(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    )


# ── Public API ────────────────────────────────────────────────────────────────


def extract_schedules(doc, kinds: Optional[List[str]] = None) -> List[ScheduleTable]:
    """Extract all recognized schedule tables from an open fitz.Document.

    ``kinds`` filters which schedule kinds run (default: all registered in
    ``SCHEDULE_KIND_VOCABULARIES``). Each table is claimed by at most one
    kind — the first (registry order) whose tag/header/coverage gate passes.

    Returned quantities are exact printed data but remain LOWER BOUNDS for
    installed counts (see module docstring / Pitfall 10).
    """
    selected = list(SCHEDULE_KIND_VOCABULARIES) if kinds is None else [
        k for k in kinds if k in SCHEDULE_KIND_VOCABULARIES
    ]

    results: List[ScheduleTable] = []

    if "door" in selected:
        try:
            results.extend(_door_schedule_tables(doc))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Door schedule delegation failed: %s", exc)

    generic_kinds = [
        k for k in selected if not SCHEDULE_KIND_VOCABULARIES[k].get("delegate")
    ]
    if not generic_kinds:
        results.sort(key=lambda t: (t.page_index, t.bbox_pt))
        return results

    for i in range(doc.page_count):
        page = doc[i]
        try:
            tables = list(page.find_tables().tables)
        except Exception:  # noqa: BLE001
            tables = []
        for t in tables:
            rows = _sanitize_rows(t)
            if not rows:
                continue
            for kind in generic_kinds:
                vocab = SCHEDULE_KIND_VOCABULARIES[kind]
                tag_re = vocab["tag_re"]
                tag_col = _kind_tag_column(rows, tag_re)
                if tag_col is None:
                    continue
                if not _has_header_tokens(rows, vocab["header_tokens"]):
                    continue
                tag_rows, covered = _coverage(
                    rows, tag_col, tag_re, vocab["value_predicate"]
                )
                if not _passes_gate(tag_rows, covered, vocab):
                    continue
                structured = _structured_rows(rows, tag_col, tag_re)
                if not structured:
                    continue
                results.append(
                    ScheduleTable(
                        kind=kind,
                        rows=structured,
                        page_index=i,
                        bbox_pt=_table_bbox(t),
                        confidence="high" if (covered / tag_rows) >= 0.7 else "medium",
                    )
                )
                break  # each table claimed by at most one kind

    results.sort(key=lambda t: (t.page_index, t.bbox_pt))
    return results


def extract_schedules_from_pdf(
    pdf_path: str, kinds: Optional[List[str]] = None
) -> List[ScheduleTable]:
    """Open a plans PDF and return every recognized schedule table."""
    try:
        import fitz
    except Exception:  # noqa: BLE001
        return []
    try:
        doc = fitz.open(pdf_path)
    except Exception:  # noqa: BLE001
        return []
    try:
        return extract_schedules(doc, kinds=kinds)
    finally:
        doc.close()


if __name__ == "__main__":  # quick measurement harness
    import sys

    import fitz

    paths = sys.argv[1:] or [
        "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf",
        "uploads/Crow - Cass White Road-Plans.pdf",
    ]
    for p in paths:
        d = fitz.open(p)
        tables_found = extract_schedules(d)
        d.close()
        print(f"\n=== {p.split('/')[-1]} ===")
        for st in tables_found:
            print(
                f"  page {st.page_index}: kind={st.kind} rows={len(st.rows)} "
                f"bbox={tuple(round(v, 1) for v in st.bbox_pt)} conf={st.confidence}"
            )
