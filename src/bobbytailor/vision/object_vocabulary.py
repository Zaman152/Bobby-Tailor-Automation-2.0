"""Autonomous project-vocabulary pass (hybrid naming).

Replaces the permanently-deleted hand-authored manifest under the plans-only
mandate. An estimator reading a plan knows that a "Column", "Bollard",
"Ladder", "Stair", "Lift" exist because the drawing body AND its keynotes /
general notes / abbreviations / schedule headers say so — not because a table
row was cleanly extracted. This pass reproduces that read as ONE structured
vision call: it NAMES every distinct object type a take-off would quantify and
returns those names (plus aliases) to seed the symbol-gallery candidate list.

Semantic-only discipline (same as every vector-path schema):
  - the schema (:func:`bobbytailor.vision.schemas.vocabulary_schema`) carries
    ZERO numeric fields — this pass must never emit counts / areas / lengths;
  - the call is additive: on ANY model error it returns ``[]`` and logs a
    warning; it never raises and never blocks a run.

Python 3.9 compatible (typing.Optional/List/Dict, no ``X | Y`` runtime
annotations, no match statements).
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from bobbytailor.vision.schemas import naming_convention_schema, vocabulary_schema

logger = logging.getLogger(__name__)

# Recognised binding hints (mirrors schemas.NAMING_BINDING_HINTS) — a hint
# outside this set is normalised to "other" so a stochastic model answer can
# never smuggle an unrecognised binding category into the geometry binder.
_VALID_BINDING_HINTS = frozenset(
    {
        "structural_grid_symbol",
        "perimeter_jamb_symbol",
        "exterior_wall",
        "interior_wall",
        "masonry_wall",
        "floor_slab",
        "roof_deck",
        "count_from_schedule",
        "other",
    }
)
_VALID_NAMING_BASES = frozenset(
    {"count", "linear", "wall_area", "floor_area", "roof_area"}
)

# Cap the plan text fed to the model so a huge multi-page concatenation cannot
# blow the request budget — keynotes/notes/abbreviations live near the top of
# each page's text and this keeps the essential estimator context.
_MAX_PLAN_TEXT_CHARS = 24000

VOCABULARY_INSTRUCTION = (
    "You are a construction estimator preparing a take-off. List every "
    "distinct object TYPE that would be quantified in a take-off of this "
    "project. Read BOTH the drawing AND the keynotes, general notes, "
    "abbreviations, and schedule headers in the text below. For each type "
    "give: its name, its MEASURE BASIS, its unit, and any common aliases or "
    "abbreviations (e.g. \"HM\" for \"Hollow Metal\"). The measure basis "
    "classifies HOW the type is quantified — choose exactly one:\n"
    "- \"count\": discrete items counted each (columns, bollards, doors, "
    "ladders, stairs, lifts).\n"
    "- \"linear\": items measured in linear feet that are NOT walls (curbs, "
    "rails, guardrail).\n"
    "- \"wall_area\": vertical walls quantified as area = length × height "
    "(CMU wall, tilt-up wall, tilt panel).\n"
    "- \"floor_area\": slab / floor coverings that span the building floor "
    "(sealed concrete, flooring, concrete slab).\n"
    "- \"roof_area\": roof / ceiling / exposed structure that spans the "
    "building overhead (roof deck, exposed structure, ceiling).\n"
    "Name object TYPES only. Do NOT estimate, count, or measure any "
    "quantities — emit no numbers."
)


def build_vocabulary_hint(plan_text: Optional[str]) -> str:
    """Build the user-message hint: estimator instruction + plan text.

    The instruction frames the semantic-only naming task; the plan text
    (keynotes / notes / abbreviations / schedule headers, concatenated across
    pages by the caller) is what an estimator reads to know what objects
    exist. Truncated to ``_MAX_PLAN_TEXT_CHARS`` to bound request size.
    """
    text = (plan_text or "").strip()
    if len(text) > _MAX_PLAN_TEXT_CHARS:
        text = text[:_MAX_PLAN_TEXT_CHARS]
    if not text:
        return VOCABULARY_INSTRUCTION
    return "{}\n\nPROJECT TEXT (keynotes, notes, abbreviations, schedules):\n{}".format(
        VOCABULARY_INSTRUCTION, text
    )


def _result_cost_usd(result) -> float:
    """The ``_cost_usd`` metadata stamp of an analyzer result (0.0 fallback).

    Mirrors ``takeoff_pipeline._result_cost_usd`` — duplicated here (trivially)
    to avoid a circular import (takeoff_pipeline imports this module).
    """
    if isinstance(result, dict):
        try:
            return float(result.get("_cost_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def build_project_vocabulary(
    analyzer: Callable,
    image_path: str,
    plan_text: str,
    guard=None,
    sheet_name: str = "project",
) -> List[Dict]:
    """Make ONE structured vision call to name the project's object types.

    Args:
        analyzer:   Callable with the ``analyze_drawing`` signature
                    (``screenshot_path, sheet_name, pass_type, sheet_type,
                    output_schema, images, user_hint``). Injected so tests can
                    stub it — this function NEVER makes a real API call itself.
        image_path: Path to the project's main floor-plan image.
        plan_text:  Concatenated plan text (keynotes / notes / abbreviations /
                    schedule headers) passed as the user hint / context.
        guard:      Optional BudgetGuard. When supplied, the completed call is
                    charged via ``guard.charge(_result_cost_usd(result))`` —
                    the same accounting pattern the pipeline uses elsewhere.
        sheet_name: Label for logging / model routing.

    Returns:
        The parsed ``objects`` list (each a dict). Returns ``[]`` on ANY model
        error or malformed response — never raises (this pass is additive).
    """
    try:
        if guard is not None and getattr(guard, "exhausted", False):
            logger.info(
                "build_project_vocabulary: budget exhausted — skipping vocabulary pass"
            )
            return []
        hint = build_vocabulary_hint(plan_text)
        result = analyzer(
            image_path,
            sheet_name,
            pass_type="vocabulary",
            sheet_type="",
            output_schema=vocabulary_schema(),
            images=[image_path] if image_path else None,
            user_hint=hint,
        )
    except Exception as exc:  # noqa: BLE001 — vocabulary is strictly additive
        logger.warning("build_project_vocabulary: vision call failed: %s", exc)
        return []

    # Charge whatever the call cost, even on a model-side error result, so the
    # ledger reflects paid work (mirrors _structured_vision_call accounting).
    if guard is not None:
        try:
            guard.charge(_result_cost_usd(result))
        except Exception as exc:  # noqa: BLE001 — never let accounting break the run
            logger.warning("build_project_vocabulary: budget charge failed: %s", exc)

    if not isinstance(result, dict) or result.get("error"):
        logger.warning(
            "build_project_vocabulary: no vocabulary (%s)",
            (result or {}).get("error") if isinstance(result, dict) else type(result),
        )
        return []

    objects = result.get("objects")
    if not isinstance(objects, list):
        return []
    return [obj for obj in objects if isinstance(obj, dict)]


def _norm_name(text) -> str:
    """Normalise an object name for cross-sample identity (lower, collapsed)."""
    if not isinstance(text, str):
        return ""
    return " ".join(text.split()).strip().lower()


def majority_vote_objects(samples: List[List[Dict]]) -> List[Dict]:
    """Majority-vote object PRESENCE across N vocabulary samples.

    Each element of *samples* is one vocabulary pass's ``objects`` list. An
    object is KEPT only when its (normalised) name appears in a strict majority
    of samples — this stops a stochastic "unknown" run from dropping a real
    object (Exposed Structure, Columns, ...) that every other run names. For a
    kept object: aliases are the union across the samples that named it, and
    the basis is the plurality of the sample bases (ties → ``None`` so the
    deterministic classifier / merge decides). First-seen name casing and order
    are preserved.

    N==1 (or a single sample) returns that sample's objects unchanged
    (single-shot behaviour). Never raises.
    """
    clean = [s for s in (samples or []) if isinstance(s, list)]
    n = len(clean)
    if n == 0:
        return []
    if n == 1:
        return [o for o in clean[0] if isinstance(o, dict)]

    from collections import OrderedDict

    counts: "OrderedDict[str, int]" = OrderedDict()
    display: Dict[str, str] = {}
    aliases: Dict[str, list] = {}
    basis_votes: Dict[str, list] = {}
    unit_votes: Dict[str, list] = {}

    for sample in clean:
        seen_this_sample = set()
        for obj in sample:
            if not isinstance(obj, dict):
                continue
            name = (obj.get("name") or "").strip()
            key = _norm_name(name)
            if not key or key in seen_this_sample:
                continue
            seen_this_sample.add(key)
            counts[key] = counts.get(key, 0) + 1
            display.setdefault(key, name)
            aliases.setdefault(key, [])
            for a in obj.get("aliases") or []:
                if isinstance(a, str) and a.strip() and a not in aliases[key]:
                    aliases[key].append(a)
            b = obj.get("basis")
            if b:
                basis_votes.setdefault(key, []).append(b)
            u = obj.get("unit")
            if u:
                unit_votes.setdefault(key, []).append(u)

    def _plurality(values):
        if not values:
            return None
        tally: Dict[str, int] = {}
        for v in values:
            tally[v] = tally.get(v, 0) + 1
        top = max(tally.values())
        winners = [v for v, c in tally.items() if c == top]
        return winners[0] if len(winners) == 1 else None

    kept: List[Dict] = []
    for key, count in counts.items():
        if count * 2 <= n:          # not a strict majority — drop it
            continue
        kept.append({
            "name": display[key],
            "aliases": list(aliases.get(key, [])),
            "basis": _plurality(basis_votes.get(key, [])),
            "unit": _plurality(unit_votes.get(key, [])),
        })
    return kept


_MAX_NAMING_TEXT_CHARS = 48000

NAMING_CONVENTION_INSTRUCTION = (
    "You are a construction estimator preparing a take-off. Read THIS plan's "
    "keynotes, general notes, detail/section labels, abbreviation key and "
    "schedule headers below. List EVERY object a take-off would quantify and, "
    "for each, the naming convention THIS plan uses for it. For each object "
    "give:\n"
    "- canonical_name: the name the plan itself uses (e.g. a plan that writes "
    "\"S.C.C.P.\" for tilt-up panels, or \"ALL INTERIOR COLUMNS\", tells you "
    "its own name).\n"
    "- aliases: abbreviations / synonyms the plan prints for it (e.g. "
    "\"S.C.C.P.\" = site cast concrete panel = tilt-up wall).\n"
    "- basis: HOW it is measured — one of count | linear | wall_area | "
    "floor_area | roof_area.\n"
    "- binding_hint: HOW to recognise it in the drawing geometry — one of: "
    "structural_grid_symbol (the repeated symbol on the structural column "
    "grid → columns); perimeter_jamb_symbol (a symbol repeating along the "
    "perimeter or at door jambs → bollards); exterior_wall / interior_wall "
    "(tilt-up / S.C.C.P. panel faces, interior vs exterior); masonry_wall "
    "(CMU / block wall); floor_slab; roof_deck; count_from_schedule; or other.\n"
    "- variant: \"interior\" or \"exterior\" where the plan distinguishes the "
    "face, else \"\".\n"
    "- thickness_in / height_ft: the thickness or height the plan PRINTS for "
    "it, copied VERBATIM as text (e.g. \"8\", \"36'-0\\\"\"), else \"\".\n"
    "Name and classify only. Do NOT estimate, count or measure any quantities "
    "— emit no numbers except inside the thickness_in / height_ft text tokens."
)


def build_naming_hint(naming_text: Optional[str]) -> str:
    """Build the user-message hint: naming instruction + the plan's naming text.

    The instruction frames the naming-convention task; *naming_text* is the
    comprehensive plan text harvested by
    :func:`component_library.extract_naming_text` (keynotes / notes / detail
    labels / abbreviations / schedules). Truncated to ``_MAX_NAMING_TEXT_CHARS``
    to bound request size while keeping far more context than the vocabulary
    pass (naming conventions live throughout the notes, not just the top).
    """
    text = (naming_text or "").strip()
    if len(text) > _MAX_NAMING_TEXT_CHARS:
        text = text[:_MAX_NAMING_TEXT_CHARS]
    if not text:
        return NAMING_CONVENTION_INSTRUCTION
    return "{}\n\nPLAN NAMING TEXT (keynotes, notes, details, abbreviations, schedules):\n{}".format(
        NAMING_CONVENTION_INSTRUCTION, text
    )


def _clean_convention(obj: Dict) -> Optional[Dict]:
    """Normalise one raw naming-convention object; drop it when unnamed.

    Coerces every field to its semantic-only shape: unknown ``binding_hint`` →
    ``"other"``, unknown ``basis`` → ``None`` (the deterministic classifier /
    merge decides), thickness/height forced to strings, aliases deduped.
    """
    if not isinstance(obj, dict):
        return None
    name = (obj.get("canonical_name") or obj.get("name") or "").strip()
    if not name:
        return None
    hint = (obj.get("binding_hint") or "").strip().lower()
    if hint not in _VALID_BINDING_HINTS:
        hint = "other"
    basis = obj.get("basis") or obj.get("measure")
    if basis not in _VALID_NAMING_BASES:
        basis = None
    aliases = []
    for a in obj.get("aliases") or []:
        if isinstance(a, str) and a.strip() and a not in aliases:
            aliases.append(a.strip())

    def _as_text(value) -> str:
        return value.strip() if isinstance(value, str) else ""

    return {
        "canonical_name": name,
        "aliases": aliases,
        "basis": basis,
        "binding_hint": hint,
        "variant": _as_text(obj.get("variant")).lower(),
        "thickness_in": _as_text(obj.get("thickness_in")),
        "height_ft": _as_text(obj.get("height_ft")),
    }


def extract_naming_conventions(
    analyzer: Callable,
    image_path: str,
    naming_text: str,
    guard=None,
    sheet_name: str = "project",
) -> List[Dict]:
    """ONE structured vision call → THIS plan's naming CONVENTION library.

    Reads the plan's own notes / details / abbreviations / schedules (plus
    optionally the main-plan image) and returns the naming library the plan
    uses: a list of ``{canonical_name, aliases, basis, binding_hint, variant,
    thickness_in, height_ft}`` objects (see
    :func:`schemas.naming_convention_schema`). Semantic-only — no numeric
    fields. Additive: on ANY model error or malformed response returns ``[]``
    (never raises, never blocks a run).

    Args:
        analyzer:    Callable with the ``analyze_drawing`` signature (injected
                     so tests stub it — this function NEVER makes a real call).
        image_path:  Path to the project's main floor-plan image (optional
                     visual context).
        naming_text: Comprehensive plan naming text (from
                     :func:`component_library.extract_naming_text`).
        guard:       Optional BudgetGuard; the completed call is charged.
        sheet_name:  Label for logging / model routing.
    """
    try:
        if guard is not None and getattr(guard, "exhausted", False):
            logger.info(
                "extract_naming_conventions: budget exhausted — skipping naming pass"
            )
            return []
        hint = build_naming_hint(naming_text)
        result = analyzer(
            image_path,
            sheet_name,
            pass_type="naming_conventions",
            sheet_type="",
            output_schema=naming_convention_schema(),
            images=[image_path] if image_path else None,
            user_hint=hint,
        )
    except Exception as exc:  # noqa: BLE001 — naming is strictly additive
        logger.warning("extract_naming_conventions: vision call failed: %s", exc)
        return []

    if guard is not None:
        try:
            guard.charge(_result_cost_usd(result))
        except Exception as exc:  # noqa: BLE001 — never let accounting break the run
            logger.warning("extract_naming_conventions: budget charge failed: %s", exc)

    if not isinstance(result, dict) or result.get("error"):
        logger.warning(
            "extract_naming_conventions: no naming library (%s)",
            (result or {}).get("error") if isinstance(result, dict) else type(result),
        )
        return []

    objects = result.get("objects")
    if not isinstance(objects, list):
        return []
    cleaned: List[Dict] = []
    for obj in objects:
        entry = _clean_convention(obj)
        if entry is not None:
            cleaned.append(entry)
    return cleaned


def majority_keep_conventions(samples: List[List[Dict]]) -> List[Dict]:
    """Majority-KEEP naming-convention objects across N voted samples.

    Each element of *samples* is one naming pass's cleaned object list. An
    object is KEPT only when its (normalised) ``canonical_name`` appears in a
    strict majority of samples — so a stochastic run that omits Columns cannot
    drop it when every other run names it. For a kept object: aliases are the
    union across the naming samples; basis / binding_hint / variant /
    thickness_in / height_ft are the plurality of the non-empty sample values
    (ties → the first-seen non-empty). First-seen name casing / order preserved.
    N==1 returns that sample unchanged. Never raises.
    """
    clean = [s for s in (samples or []) if isinstance(s, list)]
    n = len(clean)
    if n == 0:
        return []
    if n == 1:
        return [o for o in clean[0] if isinstance(o, dict)]

    from collections import OrderedDict

    counts: "OrderedDict[str, int]" = OrderedDict()
    display: Dict[str, str] = {}
    aliases: Dict[str, list] = {}
    field_votes: Dict[str, Dict[str, list]] = {}
    _voted_fields = ("basis", "binding_hint", "variant", "thickness_in", "height_ft")

    for sample in clean:
        seen_this_sample = set()
        for obj in sample:
            entry = _clean_convention(obj)
            if entry is None:
                continue
            key = _norm_name(entry["canonical_name"])
            if not key or key in seen_this_sample:
                continue
            seen_this_sample.add(key)
            counts[key] = counts.get(key, 0) + 1
            display.setdefault(key, entry["canonical_name"])
            aliases.setdefault(key, [])
            for a in entry["aliases"]:
                if a not in aliases[key]:
                    aliases[key].append(a)
            votes = field_votes.setdefault(key, {f: [] for f in _voted_fields})
            for f in _voted_fields:
                val = entry.get(f)
                if val:
                    votes[f].append(val)

    def _plurality(values):
        if not values:
            return None
        tally: Dict[str, int] = {}
        order = []
        for v in values:
            if v not in tally:
                order.append(v)
            tally[v] = tally.get(v, 0) + 1
        top = max(tally.values())
        winners = [v for v in order if tally[v] == top]
        return winners[0]  # first-seen among the top → deterministic

    kept: List[Dict] = []
    for key, count in counts.items():
        if count * 2 <= n:  # not a strict majority — drop it
            continue
        votes = field_votes.get(key, {})
        kept.append(
            {
                "canonical_name": display[key],
                "aliases": list(aliases.get(key, [])),
                "basis": _plurality(votes.get("basis", [])),
                "binding_hint": _plurality(votes.get("binding_hint", [])) or "other",
                "variant": _plurality(votes.get("variant", [])) or "",
                "thickness_in": _plurality(votes.get("thickness_in", [])) or "",
                "height_ft": _plurality(votes.get("height_ft", [])) or "",
            }
        )
    return kept


def vocabulary_labels(objects: List[Dict]) -> List[str]:
    """Flatten a vocabulary object list to a deduped list of names + aliases.

    Case-insensitive dedupe, first-seen order preserved. Non-string / empty
    values are dropped. This is the flat candidate feed merged into the
    symbol-gallery legend labels.
    """
    labels: List[str] = []
    seen = set()
    for obj in objects or []:
        if not isinstance(obj, dict):
            continue
        candidates = [obj.get("name"), obj.get("canonical_name")]
        aliases = obj.get("aliases")
        if isinstance(aliases, list):
            candidates.extend(aliases)
        for value in candidates:
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
