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
    "give: its name, whether it is measured by count, area, or length, its "
    "unit, and any common aliases or abbreviations (e.g. \"HM\" for "
    "\"Hollow Metal\"). Name object TYPES only. Do NOT estimate, count, or "
    "measure any quantities — emit no numbers."
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
