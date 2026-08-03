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
from functools import lru_cache
from typing import Optional

from bobbytailor.config import (
    CLAUDE_MODEL,
    CLAUDE_MODEL_CLASSIFY,
    CLAUDE_MODEL_DENSE,
    CLAUDE_MODEL_SCHEDULES,
    CLAUDE_MODEL_SEMANTIC,
)
from bobbytailor.pipeline.text_shape import is_title_shaped_match

# Optional: fall back gracefully if _pick_model is not yet importable
try:
    from bobbytailor.vision.claude_analyzer import _pick_model as _ca_pick_model
except ImportError:
    def _ca_pick_model(sheet_name: str) -> str:  # type: ignore[misc]
        return CLAUDE_MODEL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PASS_MATRIX
# Maps canonical sheet_type → ordered list of extraction pass names.
# ---------------------------------------------------------------------------
PASS_MATRIX: dict[str, list[str]] = {
    "floor_plan":  ["count", "measure", "schedule"],  # + takeoff legend tables on plan body
    "elevation":   ["count", "measure"],   # facade items + linear dimensions
    "civil_site":  ["measure"],            # linear runs and areas; no symbol grid
    "schedule":    ["schedule"],           # dense table → Sonnet unconditionally
    "detail":      ["count", "measure"],   # Sonnet; dimension vs symbol disambiguation
    "title_sheet": [],                     # SKIP — no take-off data, zero API cost
    "roof_plan":   ["count", "measure"],   # drains, equipment, gas pipe
    "mep_plan":    ["count", "measure"],   # equipment count + linear pipe/duct/conduit
}

# ---------------------------------------------------------------------------
# MODEL_ROUTING (v2 — 21-RESEARCH.md §5 routing table, July 2026 line-up)
# Maps (sheet_type, pass_type) → model slug override.
#
# Key convention:
#   - Exact (sheet_type, pass_type) rows win.
#   - (WILDCARD_SHEET_TYPE, pass_type) rows apply to ANY sheet type running
#     that pass — used for passes the vision package registers phase-wide
#     (classify, semantic, legend, schedule, verify_retry).
#   - No entry → caller uses the default CLAUDE_MODEL.
#
# Every slug is sourced from config (env-driven) — NEVER hardcode model
# strings here (user decision, 21-CONTEXT.md). Escalation to
# CLAUDE_MODEL_ESCALATION is NOT routed here: it is budget-gated behind
# config.ESCALATION_ENABLED and applied by the ensemble layer (21-11).
# ---------------------------------------------------------------------------
WILDCARD_SHEET_TYPE = "*"

MODEL_ROUTING: dict[tuple[str, str], str] = {
    # Elevation measure pass: complex facade geometry needs better model
    ("elevation",  "measure"):   CLAUDE_MODEL_SCHEDULES,
    # Detail sheets: distinguish dimension callouts from countable symbols (RC-6 fix)
    ("detail",     "count"):     CLAUDE_MODEL_SCHEDULES,
    ("detail",     "measure"):   CLAUDE_MODEL_SCHEDULES,
    # Roof/MEP measure: pipe/duct runs require length precision
    ("roof_plan",  "measure"):   CLAUDE_MODEL_SCHEDULES,
    ("mep_plan",   "measure"):   CLAUDE_MODEL_SCHEDULES,
    ("floor_plan", "count"):     CLAUDE_MODEL_SCHEDULES,
    ("floor_plan", "measure"):   CLAUDE_MODEL_SCHEDULES,
    # Dense small-text structuring → high-res vision class (RESEARCH §5:
    # legend/schedule structuring fixes partial schedule rows)
    ("schedule",   "schedule"):  CLAUDE_MODEL_DENSE,
    ("floor_plan", "schedule"):  CLAUDE_MODEL_DENSE,
    ("floor_plan", "legend"):    CLAUDE_MODEL_DENSE,
    # Phase-wide pass routes consumed by the vision package (21-08/21-11/21-14)
    (WILDCARD_SHEET_TYPE, "classify"):     CLAUDE_MODEL_CLASSIFY,
    # Semantic labeling + the in-context symbol gallery (which routes through the
    # "semantic" row) are the passes that decide WHICH geometry candidate is
    # Columns / Bollards and WHICH wall thickness class is CMU vs tilt-up. On
    # Sonnet those bindings were the #1 accuracy blocker — run-to-run they flip
    # (CMU 8 ↔ 11,294 SF; Columns present ↔ missing) on the SAME plan, because
    # the geometry is stable but the label is stochastic. These calls carry no
    # numeric fields (candidate-ID enums only), so the model can only choose
    # among geometry-supplied candidates — spending the best model here buys
    # binding RELIABILITY, never a hallucinated quantity. Bounded: a handful of
    # semantic calls per sheet, not a per-object loop.
    (WILDCARD_SHEET_TYPE, "semantic"):     CLAUDE_MODEL_DENSE,
    # Project-vocabulary pass (hybrid naming, plans-only manifest replacement):
    # a semantic estimator read of the drawing + keynotes/notes/abbreviations.
    # Runs ONCE per project and seeds every downstream name → best model.
    (WILDCARD_SHEET_TYPE, "vocabulary"):   CLAUDE_MODEL_DENSE,
    # AI naming-convention pass (plans-only autonomous naming): reads the plan's
    # own notes/details/abbreviations/schedules and reports THIS plan's naming
    # library (name/aliases/basis/binding_hint/variant). This is the project's
    # ONE reader / manifest-builder — the #1 generalization surface — so it runs
    # on the DENSE model (Opus 4.8), NOT the semantic Sonnet row. Per-sheet
    # labeling stays on Sonnet; geometry stays deterministic. The pass runs ONCE
    # per project on lean, distilled naming text, so the Opus cost is bounded and
    # acceptable in exchange for a reliably valid naming manifest on ANY plan
    # (Sonnet returned invalid_json → no manifest → 8% accuracy on Bob's).
    (WILDCARD_SHEET_TYPE, "naming_conventions"): CLAUDE_MODEL_DENSE,
    (WILDCARD_SHEET_TYPE, "legend"):       CLAUDE_MODEL_DENSE,
    (WILDCARD_SHEET_TYPE, "schedule"):     CLAUDE_MODEL_DENSE,
    (WILDCARD_SHEET_TYPE, "verify_retry"): CLAUDE_MODEL_DENSE,
}


def resolve_routed_model(sheet_type: str, pass_type: str) -> Optional[str]:
    """Resolve a MODEL_ROUTING entry: exact key first, then wildcard row.

    Pure table lookup — no name heuristics — so claude_analyzer._pick_model
    can defer-import this single resolution function without recursing back
    into the name-based fallback below.

    Returns:
        Model slug string, or None when no routing entry applies.
    """
    routed = MODEL_ROUTING.get((sheet_type, pass_type))
    if routed:
        return routed
    return MODEL_ROUTING.get((WILDCARD_SHEET_TYPE, pass_type))

# ---------------------------------------------------------------------------
# Keyword sets for sheet-type classification
# Ordered from most-specific to least-specific to avoid early false matches.
# ---------------------------------------------------------------------------
# Title/cover keywords that are UNAMBIGUOUS wherever they appear. Bare "COVER"
# and "INDEX" are deliberately NOT here — see _KW_TITLE_BLOCK_ONLY.
_KW_TITLE    = frozenset(["SHEET INDEX", "DRAWING INDEX", "TITLE SHEET", "COVER SHEET"])
# Bare title words trusted ONLY inside the title block. In full-page text they
# are catastrophic: classifying a sheet "title_sheet" SKIPS IT ENTIRELY (zero
# API, no geometry), and a real drawing routinely mentions these words in its
# notes — a hotel's guestroom floor plans all say "WALL COVERING", a schedule
# says "COVER PLATE". Moxy lost 27 of 40 sheets (every guestroom floor plan,
# i.e. all 129,521 SF of Gyp Wall) to a bare "COVER" match; Bob's lost 3; Crow's
# OVERALL FLOOR PLAN survives only because its title block says "FLOOR PLAN"
# and is checked first.
_KW_TITLE_BLOCK_ONLY = frozenset(["INDEX", "COVER"])
_KW_SCHEDULE = frozenset(["SCHEDULE", "PANEL SCHEDULE", "EQUIPMENT SCHEDULE", "DOOR SCHEDULE",
                           "WINDOW SCHEDULE", "FINISH SCHEDULE"])
_KW_ROOF     = frozenset(["ROOF PLAN"])           # must precede generic PLAN/FLOOR PLAN
_KW_ELEV     = frozenset(["ELEVATION", "ELEVATIONS"])
_KW_CIVIL    = frozenset(["SITE PLAN", "GRADING", "UTILITY PLAN", "CIVIL PLAN", "PAVING PLAN"])
_KW_DETAIL   = frozenset(["DETAIL", "DETAILS", "SECTION", "SECTIONS"])
_KW_FLOOR    = frozenset(["FLOOR PLAN", "FLOOR PLANS", "PLAN", "LEVEL"])

# MEP sheet ID prefix: M (mechanical), P (plumbing), E (electrical) + digit
_MEP_PREFIX_RE = re.compile(r"^[MPE]\d", re.IGNORECASE)

# An explicit drawing-viewport title naming a measurable plan:
#   "KING SUITE B - AR PLAN"   "QQ A - RCP PLAN"   "LEVEL 7 - AR PLAN"
# AR = architectural, RCP = reflected ceiling. Deliberately NOT FF/EM/FC —
# furniture/electrical/finish plans carry no take-off geometry of their own.
_PLAN_VIEWPORT_RE = re.compile(r"-\s*(?:AR|RCP)\s+PLAN\b")


@lru_cache(maxsize=256)
def _kw_regex(keyword: str) -> "re.Pattern":
    """Word-boundary matcher for one keyword (cached — called per page)."""
    return re.compile(r"\b%s\b" % re.escape(keyword))


# Characters of surrounding text kept either side of a keyword match, so the
# ledger can show WHY a page was classified the way it was. ~25 each side is
# enough to read the phrase the keyword landed in ("...LIGHT SWITCH COVER PLATE
# INDICATING...") and short enough that the report never becomes a text dump of
# the drawing (INV-08 threat T-23-03).
_CONTEXT_PAD = 25


def _find_hit(text: str, keywords: "frozenset[str]") -> Optional[tuple]:
    """(keyword, start, end) for the deciding whole-word keyword match, or None.

    "Deciding" is defined deterministically as the EARLIEST match in *text*,
    tie-broken by the longest keyword and then alphabetically. Determinism
    matters: a frozenset iterates in hash order, which varies between processes
    under PYTHONHASHSEED, so "return whichever keyword `any()` happened to hit
    first" would make the recorded reason irreproducible — the exact opposite of
    what the coverage ledger exists to provide.

    The verdict itself is unaffected by the choice (any match means the same
    branch is taken), so this is a reporting refinement, never a routing change.
    """
    best: Optional[tuple] = None
    for kw in sorted(keywords):
        m = _kw_regex(kw).search(text)
        if m is None:
            continue
        cand = (m.start(), -len(kw), kw, m.end())
        if best is None or cand < best:
            best = cand
    if best is None:
        return None
    start, _neg_len, kw, end = best
    return kw, start, end


def _find_title_position_hit(text: str, keywords: "frozenset[str]") -> Optional[tuple]:
    """(keyword, start, end) for the earliest match sitting in a TITLE POSITION.

    The guard for the bare title words. "COVER" and "INDEX" are catastrophic
    when they are wrong — a title_sheet verdict discards the sheet entirely,
    zero API and zero geometry — and a real drawing says them constantly in its
    notes. Whole-word matching (which this codebase already does) fixed
    "COVERING" but NOT the live collision, because "LIGHT SWITCH COVER PLATE"
    contains "COVER" as a whole word. It discarded 16 Moxy guestroom prototypes
    (INV-08 §1.2), and the same shape reappears in every wall-covering note.

    So the deciding evidence is the match's POSITION, not the keyword. A
    title-block field value is a short token run bounded by sheet IDs, numbers
    and colons — "CS-00 COVER SHEET 25-13.01", "SHEET TITLE: COVER". A keynote
    is a long run of words containing English function words — "PROVIDE LABEL
    ON THE LIGHT SWITCH COVER PLATE INDICATING". text_shape.is_title_shaped_match
    tests exactly that, and both conditions must hold.

    This is deliberately NOT a deny list of product phrases: "COVER PLATE" and
    "WALL COVERING" are the two collisions we happen to have seen, and a list of
    them would miss the third. It is also NOT a change to the keyword sets —
    those are frozen, and a test pins them.

    Matches are considered in the same deterministic order as _find_hit
    (earliest, then longest keyword, then alphabetical) and the first one in a
    title position wins, so a page whose notes mention "COVER" before its title
    block says "COVER" is still classified by its title block.
    """
    candidates = []
    for kw in sorted(keywords):
        for m in _kw_regex(kw).finditer(text):
            candidates.append((m.start(), -len(kw), kw, m.end()))
    for start, _neg_len, kw, end in sorted(candidates):
        if is_title_shaped_match(text, start, end):
            return kw, start, end
    return None


def _hit(text: str, keywords: "frozenset[str]") -> bool:
    """True when any keyword appears in *text* as a WHOLE WORD (text is upper).

    Word-boundary matching, never a bare substring: a substring test made
    "COVER" match "WALL COVERING" and silently skipped every guestroom floor
    plan on Moxy (27 of 40 sheets). The same flaw makes "PLAN" match "PLANT",
    "SECTION" match "SECTIONAL" and "DETAIL" match "DETAILED". Multi-word
    keywords ("FLOOR PLAN") are matched with boundaries at each end, so normal
    phrase hits are unaffected.

    A thin projection of _find_hit — same matching, the reason discarded.
    """
    return _find_hit(text, keywords) is not None


def _context_around(text: str, start: int, end: int) -> str:
    """~25 characters either side of a match — the auditable trail of a verdict."""
    return text[max(0, start - _CONTEXT_PAD):min(len(text), end + _CONTEXT_PAD)]


def _verdict(sheet_type: str, source: str, src: str, hit: tuple) -> tuple:
    keyword, start, end = hit
    return sheet_type, source, keyword, _context_around(src, start, end)


def classify_sheet_type_verbose(
    title_block_text: str, full_page_text: str = "",
) -> "tuple":
    """Classify a page AND state the evidence that decided it.

    Identical routing to classify_sheet_type_from_text — this function IS the
    implementation, and the 1-arg-style wrapper below is a projection of its
    first element. It exists because "16 guestroom prototype sheets were dropped
    and no artifact anywhere says why" cost this project days: recording the
    deciding keyword and the phrase it landed in turns the next collision into a
    two-second diagnosis (INV-08 §1.2, risk 5).

    Args:
        title_block_text: Text from the title block area (bottom-right ~15%).
        full_page_text:   Complete page text used as secondary fallback.

    Returns:
        (sheet_type, source, keyword, context) where
          * sheet_type — one of the eight canonical types;
          * source     — "title_block" | "full_page_text" | "default";
          * keyword    — the keyword (or matched phrase) whose hit decided it,
                         "" when nothing matched;
          * context    — ~25 chars either side of that hit inside the text that
                         produced it, "" when nothing matched.
    """

    for is_title_block, src_raw in ((True, title_block_text), (False, full_page_text)):
        if not src_raw or not isinstance(src_raw, str):
            # A non-string text source is not usable evidence. Skipping it keeps
            # this function TOTAL: the page text comes from an untrusted PDF via
            # a parser that is entitled to hand back something unexpected, and a
            # classifier that raises turns one odd page into a dead run.
            continue
        src = src_raw.upper()
        source = "title_block" if is_title_block else "full_page_text"

        # Title / cover pages — checked before "schedule" to catch "INDEX".
        # Unambiguous phrases match anywhere; the bare words ("COVER", "INDEX")
        # are trusted ONLY in the title block, because title_sheet SKIPS the
        # sheet entirely and a real drawing's notes say "WALL COVERING".
        hit = _find_hit(src, _KW_TITLE)
        if hit is None and is_title_block:
            # Bare "COVER"/"INDEX" must additionally sit in a title POSITION —
            # a title word inside a sentence is a keynote, not a sheet title.
            hit = _find_title_position_hit(src, _KW_TITLE_BLOCK_ONLY)
        if hit is not None:
            return _verdict("title_sheet", source, src, hit)

        # Dense tabular content
        hit = _find_hit(src, _KW_SCHEDULE)
        if hit is not None:
            return _verdict("schedule", source, src, hit)

        # Roof plan — must come before generic ELEVATION / PLAN
        hit = _find_hit(src, _KW_ROOF)
        if hit is not None:
            return _verdict("roof_plan", source, src, hit)

        # An explicit "<NAME> - AR/RCP PLAN" viewport title is specific, strong
        # evidence that this sheet carries MEASURABLE plan drawings, and it
        # outranks the generic ELEVATION keyword below. A sheet is a COLLECTION
        # of drawings and the type is only its dominant one: Moxy's guestroom
        # prototypes carry interior elevations AND the AR/RCP plans that hold
        # every guestroom quantity (Gyp Ceiling/Gyp Wall). Classified
        # "elevation", they never reach the deterministic engine — the sheets
        # that matter most are the ones skipped.
        m = _PLAN_VIEWPORT_RE.search(src)
        if m:
            return _verdict(
                "floor_plan", source, src,
                (m.group(0).strip(), m.start(), m.end()),
            )

        # Elevations / facades
        hit = _find_hit(src, _KW_ELEV)
        if hit is not None:
            return _verdict("elevation", source, src, hit)

        # Civil / site plans
        hit = _find_hit(src, _KW_CIVIL)
        if hit is not None:
            return _verdict("civil_site", source, src, hit)

        # Details and sections
        hit = _find_hit(src, _KW_DETAIL)
        if hit is not None:
            return _verdict("detail", source, src, hit)

        # MEP: sheet ID prefix (M/P/E + digit) in title block + "PLAN" keyword
        first_token = src.split()[0] if src.split() else ""
        if _MEP_PREFIX_RE.match(first_token) and "PLAN" in src:
            return _verdict(
                "mep_plan", source, src, (first_token, 0, len(first_token)),
            )

        # Generic floor / area plans
        hit = _find_hit(src, _KW_FLOOR)
        if hit is not None:
            return _verdict("floor_plan", source, src, hit)

    logger.debug("classify_sheet_type: no keyword match in title block or page text — defaulting to floor_plan")
    return "floor_plan", "default", "", ""


def classify_sheet_type_from_text(title_block_text: str, full_page_text: str = "") -> str:
    """Classify a drawing page into a canonical sheet_type using keyword heuristics.

    The title block region is scanned first (most reliable), then the full page
    text as fallback when the title block is sparse or absent.

    Routing is content-driven — never based on project name or sheet-ID pattern.

    Thin projection of classify_sheet_type_verbose: the verdict without the
    reason. The signature and every outcome are unchanged for every input.

    Args:
        title_block_text: Text extracted from the title block area (bottom-right ~15%).
        full_page_text:   Complete page text used as secondary fallback.

    Returns:
        One of: "floor_plan", "elevation", "civil_site", "schedule", "detail",
                "title_sheet", "roof_plan", "mep_plan".
        Defaults to "floor_plan" when no keyword matches (safest: runs count+measure).
    """
    return classify_sheet_type_verbose(title_block_text, full_page_text)[0]


def plan_passes(sheet_type: str, title_block_text: str = "") -> list[str]:
    """Return the ordered extraction passes for a sheet type.

    Args:
        sheet_type: Canonical sheet_type value.
        title_block_text: Optional title-block OCR text; used to add a schedule
            pass on floor plans that include a quantity/takeoff legend table.

    Returns:
        Ordered list of pass names e.g. ["count", "measure"].
        Empty list for "title_sheet" (→ zero API calls).
        ["measure"] fallback for unknown sheet types (nothing is silently dropped).
    """
    if sheet_type not in PASS_MATRIX:
        logger.warning("plan_passes: unknown sheet_type %r — using measure-only fallback", sheet_type)
        return ["measure"]
    passes = list(PASS_MATRIX[sheet_type])
    if sheet_type == "floor_plan":
        try:
            from bobbytailor.pipeline.accuracy_config import is_high_accuracy_mode
            if is_high_accuracy_mode() and "legend" not in passes:
                passes.append("legend")
        except ImportError:
            pass
    return passes


def pick_model_for_pass(
    sheet_type: str,
    pass_type: str,
    sheet_name: str = "",
) -> Optional[str]:
    """Select the Claude model slug for a (sheet_type, pass_type) combination.

    Single resolution function for all pass-routing consumers
    (21-08 vision prompts, 21-11 ensemble, 21-14 verify-retry).

    Priority:
      1. MODEL_ROUTING lookup — exact (sheet_type, pass_type) key, then
         (WILDCARD_SHEET_TYPE, pass_type) row via resolve_routed_model().
      2. _pick_model(sheet_name) from claude_analyzer — name-based heuristic
         (returns the schedules model for E/M/P sheet codes and
         schedule-named sheets).
      3. None — caller uses CLAUDE_MODEL default.

    Args:
        sheet_type:  Canonical sheet type (e.g. "elevation").
        pass_type:   Pass name (e.g. "measure", "count", "schedule",
                     "semantic", "verify_retry", "classify").
        sheet_name:  Optional sheet identifier for name-based heuristic fallback.

    Returns:
        Model slug string, or None to indicate "use default".
    """
    # 1. Explicit routing table (exact key → wildcard row)
    routed = resolve_routed_model(sheet_type, pass_type)
    if routed:
        return routed

    # 2. Name-based fallback from claude_analyzer heuristic
    if sheet_name:
        fallback = _ca_pick_model(sheet_name)
        if fallback and fallback != CLAUDE_MODEL:
            return fallback

    return None
