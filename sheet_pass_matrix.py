"""
sheet_pass_matrix.py — Pass routing by sheet type and drawing discipline.

PASS_MATRIX:   sheet_type → ordered list of extraction passes to run.
MODEL_ROUTING: (sheet_type, pass_type) → Claude model slug override.

Consumed by takeoff_pipeline.py, which is in turn consumed by both
pdf_analyzer.py and scraper.py so StackCT and PDF uploads run identical logic.

Design rules:
  - Routing is driven by sheet_type enum, NEVER by project name, file name,
    or sheet-ID regex (e.g. '^[AS]\\d' covers only architectural sheets).
  - title_sheet always returns an empty pass list → zero API cost.
  - Unknown sheet types fall back to ["measure"] so no sheet is silently dropped.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from config import CLAUDE_MODEL, CLAUDE_MODEL_SCHEDULES

# Optional: fall back gracefully if _pick_model is not yet importable
try:
    from claude_analyzer import _pick_model as _ca_pick_model
except ImportError:
    def _ca_pick_model(sheet_name: str) -> str:  # type: ignore[misc]
        return CLAUDE_MODEL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PASS_MATRIX
# Maps canonical sheet_type → ordered list of extraction pass names.
# ---------------------------------------------------------------------------
PASS_MATRIX: dict[str, list[str]] = {
    "floor_plan":  ["count", "measure", "schedule"],  # + legend/qty tables on plan sheets
    "elevation":   ["count", "measure"],   # facade items + linear dimensions
    "civil_site":  ["count", "measure"],   # bollards/hydrants/drains (count) + linear runs (measure)
    "schedule":    ["schedule"],           # dense table → Sonnet unconditionally
    "detail":      ["count", "measure"],   # Sonnet; dimension vs symbol disambiguation
    "title_sheet": [],                     # SKIP — no take-off data, zero API cost
    "roof_plan":   ["count", "measure"],   # drains, equipment, gas pipe
    "mep_plan":    ["count", "measure"],   # equipment count + linear pipe/duct/conduit
}

# ---------------------------------------------------------------------------
# MODEL_ROUTING
# Maps (sheet_type, pass_type) → model slug for passes that need Sonnet.
# All entries not listed here use the default CLAUDE_MODEL (Haiku).
# ---------------------------------------------------------------------------
MODEL_ROUTING: dict[tuple[str, str], str] = {
    # Elevation measure pass: complex facade geometry needs better model
    ("elevation",  "measure"):   CLAUDE_MODEL_SCHEDULES,
    # Detail sheets: distinguish dimension callouts from countable symbols (RC-6 fix)
    ("detail",     "count"):     CLAUDE_MODEL_SCHEDULES,
    ("detail",     "measure"):   CLAUDE_MODEL_SCHEDULES,
    # Schedules: always Sonnet for table accuracy
    ("schedule",   "schedule"):  CLAUDE_MODEL_SCHEDULES,
    # Roof/MEP measure: pipe/duct runs require length precision
    ("roof_plan",  "measure"):   CLAUDE_MODEL_SCHEDULES,
    ("mep_plan",   "measure"):   CLAUDE_MODEL_SCHEDULES,
    # Floor-plan legends (Crow A-101 style takeoff tables) need Sonnet schedule pass
    ("floor_plan", "schedule"):  CLAUDE_MODEL_SCHEDULES,
}

# ---------------------------------------------------------------------------
# Keyword sets for sheet-type classification
# Ordered from most-specific to least-specific to avoid early false matches.
# ---------------------------------------------------------------------------
_KW_TITLE    = frozenset(["INDEX", "COVER", "SHEET INDEX", "DRAWING INDEX", "TITLE SHEET"])
_KW_SCHEDULE = frozenset(["SCHEDULE", "PANEL SCHEDULE", "EQUIPMENT SCHEDULE", "DOOR SCHEDULE",
                           "WINDOW SCHEDULE", "FINISH SCHEDULE"])
_KW_ROOF     = frozenset(["ROOF PLAN"])           # must precede generic PLAN/FLOOR PLAN
_KW_ELEV     = frozenset(["ELEVATION", "ELEVATIONS"])
_KW_CIVIL    = frozenset(["SITE PLAN", "GRADING", "UTILITY PLAN", "CIVIL PLAN", "PAVING PLAN"])
_KW_DETAIL   = frozenset(["DETAIL", "DETAILS", "SECTION", "SECTIONS"])
_KW_FLOOR    = frozenset(["FLOOR PLAN", "FLOOR PLANS", "PLAN", "LEVEL"])

# MEP sheet ID prefix: M (mechanical), P (plumbing), E (electrical) + digit
_MEP_PREFIX_RE = re.compile(r"^[MPE]\d", re.IGNORECASE)


def classify_sheet_type_from_text(title_block_text: str, full_page_text: str = "") -> str:
    """Classify a drawing page into a canonical sheet_type using keyword heuristics.

    The title block region is scanned first (most reliable), then the full page
    text as fallback when the title block is sparse or absent.

    Routing is content-driven — never based on project name or sheet-ID pattern.

    Args:
        title_block_text: Text extracted from the title block area (bottom-right ~15%).
        full_page_text:   Complete page text used as secondary fallback.

    Returns:
        One of: "floor_plan", "elevation", "civil_site", "schedule", "detail",
                "title_sheet", "roof_plan", "mep_plan".
        Defaults to "floor_plan" when no keyword matches (safest: runs count+measure).
    """

    def _hit(text: str, keywords: frozenset[str]) -> bool:
        return any(kw in text for kw in keywords)

    for src_raw in (title_block_text, full_page_text):
        if not src_raw:
            continue
        src = src_raw.upper()

        # Title / cover pages — checked before "schedule" to catch "INDEX"
        if _hit(src, _KW_TITLE):
            return "title_sheet"

        # Dense tabular content
        if _hit(src, _KW_SCHEDULE):
            return "schedule"

        # Roof plan — must come before generic ELEVATION / PLAN
        if _hit(src, _KW_ROOF):
            return "roof_plan"

        # Elevations / facades
        if _hit(src, _KW_ELEV):
            return "elevation"

        # Civil / site plans
        if _hit(src, _KW_CIVIL):
            return "civil_site"

        # Details and sections
        if _hit(src, _KW_DETAIL):
            return "detail"

        # MEP: sheet ID prefix (M/P/E + digit) in title block + "PLAN" keyword
        first_token = src.split()[0] if src.split() else ""
        if _MEP_PREFIX_RE.match(first_token) and "PLAN" in src:
            return "mep_plan"

        # Generic floor / area plans
        if _hit(src, _KW_FLOOR):
            return "floor_plan"

    logger.debug("classify_sheet_type: no keyword match in title block or page text — defaulting to floor_plan")
    return "floor_plan"


def plan_passes(sheet_type: str) -> list[str]:
    """Return the ordered extraction passes for a sheet type.

    Args:
        sheet_type: Canonical sheet_type value.

    Returns:
        Ordered list of pass names e.g. ["count", "measure"].
        Empty list for "title_sheet" (→ zero API calls).
        ["measure"] fallback for unknown sheet types (nothing is silently dropped).
    """
    if sheet_type not in PASS_MATRIX:
        logger.warning("plan_passes: unknown sheet_type %r — using measure-only fallback", sheet_type)
        return ["measure"]
    return list(PASS_MATRIX[sheet_type])


def pick_model_for_pass(
    sheet_type: str,
    pass_type: str,
    sheet_name: str = "",
) -> Optional[str]:
    """Select the Claude model slug for a (sheet_type, pass_type) combination.

    Priority:
      1. MODEL_ROUTING lookup — explicit per-pass Sonnet override.
      2. _pick_model(sheet_name) from claude_analyzer — name-based heuristic
         (returns Sonnet for E/M/P sheet codes and schedule-named sheets).
      3. None — caller uses CLAUDE_MODEL default.

    Args:
        sheet_type:  Canonical sheet type (e.g. "elevation").
        pass_type:   Pass name (e.g. "measure", "count", "schedule").
        sheet_name:  Optional sheet identifier for name-based heuristic fallback.

    Returns:
        Model slug string, or None to indicate "use default".
    """
    # 1. Explicit routing table
    routed = MODEL_ROUTING.get((sheet_type, pass_type))
    if routed:
        return routed

    # 2. Name-based fallback from claude_analyzer heuristic
    if sheet_name:
        fallback = _ca_pick_model(sheet_name)
        if fallback and fallback != CLAUDE_MODEL:
            return fallback

    return None
