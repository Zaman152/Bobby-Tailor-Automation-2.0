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

from bobbytailor.vision.schemas import vocabulary_schema

logger = logging.getLogger(__name__)

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
        candidates = [obj.get("name")]
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
