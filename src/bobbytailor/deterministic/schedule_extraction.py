"""Deterministic schedule extraction from the PDF text/table layer.

Architectural drawings print door / frame / finish / wall-type schedules as real
tables in the PDF text layer. Those tables hold EXACT data — door panel and frame
materials, fire ratings, finishes — that should be *read*, not vision-guessed.

This module recovers that structured data with PyMuPDF's table finder and a set of
content-based heuristics that do not depend on a fixed column order, so the same
parser works across drawing sets from different architects.

IMPORTANT — what schedules can and cannot tell you:
  * A door schedule enumerates door *openings/types* with their exact materials.
    Counting its rows gives the exact count of *scheduled* openings.
  * It does NOT always equal the total *installed* count: in repetitive buildings
    (e.g. hotels) guest-room doors repeat per unit/floor and are counted on the
    plans, not re-listed per instance. So treat schedule counts as an exact LOWER
    bound / type breakdown, and flag the residual for plan-based verification.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

# A door/opening tag: 003, 006A, 101B, 113A, T1, T7B, D-12, etc.
_TAG_RE = re.compile(r"^[A-Z]{0,2}[-]?\d{1,4}[A-Z]?$|^T\d+[A-Z]?$")

# Door LEAF (panel) materials.
_PANEL_MATS = {"SCW", "HM", "HC", "WD", "GLASS", "GL", "FRP", "ALUM", "AL", "HMG", "WG"}
# Door FRAME materials.
_FRAME_MATS = {"HM", "GALV", "ALUM", "AL", "KD", "WD", "HMG"}
# Tokens that ONLY make sense as a leaf material (disambiguates the panel column).
_PANEL_ONLY = {"SCW", "HC", "WD", "GLASS", "GL", "FRP", "WG"}
# Tokens that ONLY make sense as a frame material.
_FRAME_ONLY = {"GALV", "KD"}

# Human-readable names for material codes.
_PANEL_LABEL = {
    "SCW": "Solid Core Wood", "WD": "Wood", "HC": "Hollow Core Wood",
    "HM": "Hollow Metal", "GLASS": "Glass / Aluminum", "GL": "Glass / Aluminum",
    "ALUM": "Aluminum", "AL": "Aluminum", "FRP": "FRP", "HMG": "Hollow Metal (Glazed)",
    "WG": "Wood / Glass",
}
_FRAME_LABEL = {
    "HM": "Hollow Metal", "GALV": "Galvanized Steel", "ALUM": "Aluminum",
    "AL": "Aluminum", "KD": "Knock-Down", "WD": "Wood", "HMG": "Hollow Metal (Glazed)",
}


@dataclass
class DoorRecord:
    tag: str
    room: str = ""
    panel_material: str = ""
    frame_material: str = ""
    page: int = 0


@dataclass
class DoorSchedule:
    openings: int = 0                      # distinct scheduled openings
    panel_counts: Counter = field(default_factory=Counter)
    frame_counts: Counter = field(default_factory=Counter)
    pages: List[int] = field(default_factory=list)
    records: List[DoorRecord] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.openings > 0


def _cells(row) -> List[str]:
    return [(str(c).strip() if c is not None else "") for c in row]


def _tag_tokens(cell: str) -> List[str]:
    """Split a (possibly merged) tag cell into individual valid tags."""
    toks = [t for t in cell.split() if _TAG_RE.match(t)]
    return toks


def _tag_column(rows: List[List[str]]) -> Optional[int]:
    """The column whose cells most consistently look like door tags."""
    if not rows:
        return None
    width = max(len(r) for r in rows)
    best_col, best_hits = None, 0
    for c in range(min(width, 4)):  # tag is always near the left
        hits = 0
        for r in rows:
            if c < len(r) and _tag_tokens(r[c]):
                hits += 1
        if hits > best_hits:
            best_col, best_hits = c, hits
    return best_col if best_hits >= 3 else None


def _material_columns(rows: List[List[str]], tag_col: int):
    """Identify (panel_col, frame_col) by content, order-independent.

    Picks the two columns with the highest density of door-material tokens, then
    classifies them: a column carrying leaf-only tokens (SCW/GLASS/...) is the
    panel; one carrying frame-only tokens (GALV/KD) is the frame. When both are
    ambiguous (e.g. both full of HM) the earlier column is the panel, the later
    is the frame — matching how schedules are laid out (panel before frame).
    """
    width = max((len(r) for r in rows), default=0)
    panel_score = Counter()
    frame_score = Counter()
    panel_only = Counter()
    frame_only = Counter()
    for r in rows:
        toks = _tag_tokens(r[tag_col]) if tag_col < len(r) else []
        if not toks:
            continue
        for c in range(width):
            if c == tag_col or c >= len(r):
                continue
            for v in r[c].split():
                vu = v.upper()
                if vu in _PANEL_MATS:
                    panel_score[c] += 1
                if vu in _FRAME_MATS:
                    frame_score[c] += 1
                if vu in _PANEL_ONLY:
                    panel_only[c] += 1
                if vu in _FRAME_ONLY:
                    frame_only[c] += 1
    if not panel_score and not frame_score:
        return None, None

    # Panel column: prefer the column with the most leaf-only tokens; else the
    # earliest material-heavy column.
    if panel_only:
        panel_col = panel_only.most_common(1)[0][0]
    else:
        panel_col = min(panel_score, key=lambda c: c) if panel_score else None

    # Frame column: prefer frame-only tokens; else the latest material-heavy
    # column that isn't the panel column.
    if frame_only:
        frame_col = frame_only.most_common(1)[0][0]
    else:
        cands = [c for c in frame_score if c != panel_col]
        frame_col = max(cands) if cands else None
    return panel_col, frame_col


def _material_coverage(rows, tag_col, panel_col, frame_col) -> tuple:
    """(door_rows, covered_rows): how many tag rows carry a panel/frame material.

    Floor-plan door *callouts* have tags but no material columns, so coverage is
    near zero there; a real schedule table covers most of its rows.
    """
    door_rows = 0
    covered = 0
    for r in rows:
        toks = _tag_tokens(r[tag_col]) if tag_col < len(r) else []
        if not toks:
            continue
        door_rows += 1
        pm = r[panel_col].upper().split() if (panel_col is not None and panel_col < len(r)) else []
        fm = r[frame_col].upper().split() if (frame_col is not None and frame_col < len(r)) else []
        if any(v in _PANEL_MATS for v in pm) or any(v in _FRAME_MATS for v in fm):
            covered += 1
    return door_rows, covered


def _is_door_table(rows, tag_col, panel_col, frame_col) -> bool:
    if tag_col is None or (panel_col is None and frame_col is None):
        return False
    door_rows, covered = _material_coverage(rows, tag_col, panel_col, frame_col)
    if door_rows < 3:
        return False
    # A genuine door schedule lists a material on most rows. Floor-plan tag
    # clusters do not — this gate rejects those false positives.
    return covered >= 3 and (covered / door_rows) >= 0.4


def extract_door_schedule(doc) -> DoorSchedule:
    """Extract a deterministic door schedule from an open fitz.Document."""
    out = DoorSchedule()
    seen_tags = set()
    for i in range(doc.page_count):
        page = doc[i]
        try:
            tables = list(page.find_tables().tables)
        except Exception:
            tables = []
        page_used = False
        for t in tables:
            try:
                rows = [_cells(r) for r in t.extract()]
            except Exception:
                continue
            tag_col = _tag_column(rows)
            if tag_col is None:
                continue
            panel_col, frame_col = _material_columns(rows, tag_col)
            if not _is_door_table(rows, tag_col, panel_col, frame_col):
                continue
            for r in rows:
                toks = _tag_tokens(r[tag_col]) if tag_col < len(r) else []
                if not toks:
                    continue
                room = r[tag_col + 1] if tag_col + 1 < len(r) else ""
                pm = r[panel_col].split() if (panel_col is not None and panel_col < len(r)) else []
                fm = r[frame_col].split() if (frame_col is not None and frame_col < len(r)) else []
                for k, tg in enumerate(toks):
                    if tg in seen_tags:
                        continue
                    seen_tags.add(tg)
                    p = (pm[k] if k < len(pm) else (pm[0] if pm else "")).upper()
                    f = (fm[k] if k < len(fm) else (fm[0] if fm else "")).upper()
                    out.records.append(DoorRecord(
                        tag=tg, room=room, panel_material=p, frame_material=f, page=i + 1,
                    ))
                    if p in _PANEL_MATS:
                        out.panel_counts[p] += 1
                    if f in _FRAME_MATS:
                        out.frame_counts[f] += 1
                    page_used = True
        if page_used:
            out.pages.append(i + 1)
    out.openings = len(seen_tags)
    return out


def door_schedule_to_legend(ds: "DoorSchedule") -> Optional[dict]:
    """Convert an extracted door schedule into an authoritative legend schedule.

    Each panel/frame material becomes an EXACT, auto-verifiable count of
    *scheduled* openings. Quantities pass through verbatim (``takeoff_legend``)
    so the pipeline never re-applies waste/formulas to a counted door.

    Returns ``None`` when nothing reliable was extracted.
    """
    if not ds or not ds.found or (not ds.panel_counts and not ds.frame_counts):
        return None

    rows: List[dict] = []
    for code, n in ds.panel_counts.most_common():
        rows.append({
            "ITEM": f"Doors - {_PANEL_LABEL.get(code, code)} (door schedule)",
            "DESCRIPTION": f"Doors - {_PANEL_LABEL.get(code, code)} (door schedule)",
            "QTY": str(n), "QUANTITY": str(n), "UNIT": "EA",
        })
    for code, n in ds.frame_counts.most_common():
        rows.append({
            "ITEM": f"Door Frames - {_FRAME_LABEL.get(code, code)} (door schedule)",
            "DESCRIPTION": f"Door Frames - {_FRAME_LABEL.get(code, code)} (door schedule)",
            "QTY": str(n), "QUANTITY": str(n), "UNIT": "EA",
        })
    if not rows:
        return None

    return {
        "name": "Door Schedule (extracted from plans)",
        "table_purpose": "takeoff_legend",
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
        print(f"  panel materials    : {dict(ds.panel_counts)}")
        print(f"  frame materials    : {dict(ds.frame_counts)}")
