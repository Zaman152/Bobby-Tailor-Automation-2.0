"""
Discover and parse companion quantity take-off PDFs uploaded alongside plan sets.

Generic filename heuristics only — no project names or hardcoded quantities.
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_TAKEOFF_NAME_RE = re.compile(
    r"take\s*-?\s*offs?|takeoff|quantity\s+take\s*-?\s*off",
    re.IGNORECASE,
)

_QTY_HEADER_ALIASES = frozenset({
    "qty", "quantity", "count", "amount", "no", "nos",
})
_ITEM_HEADER_ALIASES = frozenset({
    "item", "description", "desc", "name", "type", "work", "scope",
})
_UNIT_HEADER_ALIASES = frozenset({
    "unit", "uom", "u/m", "um",
})

# Construction quantity units accepted by the text-layer legend parser. Bounded
# whitelist so a bare "<number> <token>" line is only treated as a quantity when
# the token is a real unit — keeps narrative notes ("80 STEEL PIPE") from matching.
_KNOWN_UNITS = frozenset({
    "EA", "EACH", "SF", "SY", "SQ", "LF", "CY", "CF", "GAL", "GALLONS",
    "LS", "TON", "TONS", "MO", "HR", "DAY", "DAYS", "MSF", "MLF", "BF",
    "ROLL", "BAG", "BOX", "SET", "PR", "PAIR", "LOT",
})

# Private-use-area glyphs (takeoff-software map-pin icons) prefix each item name
# in exported legends. Strip any leading non-alphanumeric chars (incl. PUA).
_LEADING_NONALNUM_RE = re.compile(r"^[^0-9A-Za-z]+")

# A line that is *only* a quantity + unit, e.g. "28 EA", "2,204.33 SF".
_QTY_UNIT_LINE_RE = re.compile(
    r"^\(?\s*([\d,]+(?:\.\d+)?)\s+([A-Za-z/]{1,8})\.?\s*\)?$"
)
# Quantity + unit at the END of a line, e.g. "Bollards 28 EA".
_QTY_UNIT_INLINE_RE = re.compile(
    r"^(.+?)\s+([\d,]+(?:\.\d+)?)\s+([A-Za-z/]{1,8})\.?$"
)


def _clean_item_name(raw: str) -> str:
    return _LEADING_NONALNUM_RE.sub("", (raw or "").strip()).strip()


def _looks_like_item_name(text: str) -> bool:
    """Heuristic: a legend item label has letters and isn't a note/dimension."""
    t = _clean_item_name(text)
    if len(t) < 2 or len(t) > 60:
        return False
    if not re.search(r"[A-Za-z]", t):
        return False
    if t.endswith(":") or t.endswith("."):
        return False
    # Reject lines that are themselves a quantity+unit or a dimension callout.
    if _QTY_UNIT_LINE_RE.match(t):
        return False
    if re.search(r"\d+'\s*-\s*\d+\"", t):  # 54' - 0" dimension strings
        return False
    return True


def _parse_legend_from_text(page_text: str) -> List[dict]:
    """Extract (item, qty, unit) rows from a borderless legend in the text layer.

    Handles the common takeoff-software export shape where each row is rendered
    as an item-name line followed by a "<qty> <unit>" line (often with a leading
    icon glyph), as well as single-line "<item> <qty> <unit>" rows.
    """
    if not page_text:
        return []

    lines = [ln.strip() for ln in page_text.splitlines()]
    rows: List[dict] = []
    seen: set = set()

    def _add(item: str, qty_raw: str, unit: str) -> None:
        item = _clean_item_name(item)
        unit_u = unit.strip().upper().rstrip(".")
        if not item or unit_u not in _KNOWN_UNITS:
            return
        if not re.search(r"[A-Za-z]", item):  # reject pure-number "items"
            return
        qty = _parse_qty(qty_raw)
        if qty is None or qty <= 0:
            return
        key = (item.lower(), unit_u, round(qty, 2))
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "ITEM": item,
            "DESCRIPTION": item,
            "QTY": qty_raw.strip(),
            "UNIT": unit_u,
        })

    prev_item = ""
    for ln in lines:
        if not ln:
            continue
        # Case 1: standalone "<qty> <unit>" line → item is the previous label.
        m = _QTY_UNIT_LINE_RE.match(ln)
        if m and prev_item:
            _add(prev_item, m.group(1), m.group(2))
            prev_item = ""
            continue
        # Case 2: inline "<item> <qty> <unit>".
        m2 = _QTY_UNIT_INLINE_RE.match(ln)
        if m2 and _looks_like_item_name(m2.group(1)):
            _add(m2.group(1), m2.group(2), m2.group(3))
            prev_item = ""
            continue
        # Otherwise remember a potential item label for the next qty line.
        if _looks_like_item_name(ln):
            prev_item = ln
        else:
            prev_item = ""
    return rows


def find_companion_takeoff_pdf(plans_pdf_path: str) -> Optional[str]:
    """Return path to a sibling take-off PDF in the same folder, if any."""
    plans = Path(plans_pdf_path).resolve()
    if not plans.is_file():
        return None

    folder = plans.parent
    stem = plans.stem.lower()
    stem_tokens = set(re.findall(r"[a-z0-9]+", stem))

    best: Optional[Path] = None
    best_score = 0

    for candidate in folder.iterdir():
        if not candidate.is_file() or candidate.suffix.lower() != ".pdf":
            continue
        if candidate.resolve() == plans.resolve():
            continue
        name = candidate.name
        if not _TAKEOFF_NAME_RE.search(name):
            continue
        tokens = set(re.findall(r"[a-z0-9]+", candidate.stem.lower()))
        overlap = len(stem_tokens & tokens)
        if overlap > best_score:
            best_score = overlap
            best = candidate

    if best:
        logger.info("Companion take-off PDF: %s", best)
        return str(best)
    return None


def _normalize_header(cell: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (cell or "").lower())


def _map_columns(header_row: List[Optional[str]]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for idx, cell in enumerate(header_row or []):
        key = _normalize_header(str(cell) if cell is not None else "")
        if not key:
            continue
        if key in _QTY_HEADER_ALIASES and "qty" not in mapping:
            mapping["qty"] = idx
        elif key in _ITEM_HEADER_ALIASES and "item" not in mapping:
            mapping["item"] = idx
        elif key in _UNIT_HEADER_ALIASES and "unit" not in mapping:
            mapping["unit"] = idx
    return mapping


def _parse_qty(raw) -> Optional[float]:
    from calculator import _parse_numeric
    if raw is None:
        return None
    return _parse_numeric(str(raw).strip())


def _table_to_rows(table: List[List[Optional[str]]]) -> List[dict]:
    if not table or len(table) < 2:
        return []

    col_map = _map_columns(table[0])
    if "qty" not in col_map:
        for row in table[:3]:
            col_map = _map_columns(row)
            if "qty" in col_map:
                break
    if "qty" not in col_map:
        return []

    rows: List[dict] = []
    start = 1 if _map_columns(table[0]).get("qty") is not None else 0
    for row in table[start:]:
        if not row:
            continue
        item_idx = col_map.get("item", 0)
        qty_idx = col_map["qty"]
        unit_idx = col_map.get("unit")

        desc = str(row[item_idx]).strip() if item_idx < len(row) and row[item_idx] else ""
        qty_raw = row[qty_idx] if qty_idx < len(row) else None
        qty = _parse_qty(qty_raw)
        if not desc or qty is None or qty <= 0:
            continue
        # Reject mis-mapped rows: a real line item has a textual description,
        # and the quantity cell must be a clean number (not a door mark "001A").
        if not re.search(r"[A-Za-z]", desc):
            continue
        if not re.fullmatch(r"[\d,]+(?:\.\d+)?", str(qty_raw).strip()):
            continue

        unit = "EA"
        if unit_idx is not None and unit_idx < len(row) and row[unit_idx]:
            unit = str(row[unit_idx]).strip().upper() or "EA"

        rows.append({
            "ITEM": desc,
            "DESCRIPTION": desc,
            "QTY": str(qty_raw).strip() if qty_raw is not None else str(qty),
            "UNIT": unit,
        })
    return rows


def _dedupe_rows(rows: List[dict]) -> List[dict]:
    seen: set = set()
    out: List[dict] = []
    for r in rows:
        qty = _parse_qty(r.get("QTY"))
        key = ((r.get("ITEM") or "").lower(), (r.get("UNIT") or "").upper(),
               round(qty, 2) if qty is not None else None)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def extract_legend_schedules(takeoff_pdf_path: str) -> List[dict]:
    """Parse all quantity tables from a companion take-off PDF.

    Two complementary passes, since take-off exports vary widely:
      1. ``pdfplumber.extract_tables`` for ruled/bordered quantity tables.
      2. A text-layer parser for borderless legends rendered as
         ``Item`` / ``<qty> <unit>`` line pairs (the common Bluebeam/STACK/
         PlanSwift export shape). Rows are merged and de-duplicated.
    """
    path = Path(takeoff_pdf_path)
    if not path.is_file():
        return []

    schedules: List[dict] = []
    all_rows: List[dict] = []

    # Pass 1 — bordered tables (best-effort; pdfplumber optional).
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    all_rows.extend(_table_to_rows(table))
    except ImportError:
        logger.warning("pdfplumber not installed — bordered-table parsing skipped")
    except Exception as exc:  # noqa: BLE001 — never let table parsing crash ingest
        logger.warning("pdfplumber table parse failed for %s: %s", path.name, exc)

    # Pass 2 — text-layer borderless legend (PyMuPDF is always available).
    try:
        import fitz
        with fitz.open(str(path)) as doc:
            for page in doc:
                all_rows.extend(_parse_legend_from_text(page.get_text()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("text-layer legend parse failed for %s: %s", path.name, exc)

    all_rows = _dedupe_rows(all_rows)

    if not all_rows:
        logger.info("No quantity rows parsed from companion PDF %s", path.name)
        return []

    schedules.append({
        "name": "Quantity Takeoff (companion document)",
        "table_purpose": "takeoff_legend",
        "schedule_type": "other",
        "use_for_takeoff": True,
        "description": "Parsed from companion take-off PDF tables",
        "columns": ["ITEM", "QTY", "UNIT"],
        "rows": all_rows,
    })
    logger.info("Companion take-off: %d legend rows from %s", len(all_rows), path.name)
    return schedules
