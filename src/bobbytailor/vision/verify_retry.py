"""Targeted-crop verify-retry arbitration (21-14, V3-ACC-05).

Implements 21-RESEARCH.md §3 handoff pattern 3 — the bounded arbitration
step between QuantityVerifier flags and human review. When a quantity is
flagged out-of-band or an ensemble vote disagrees, the specific geometry is
re-rendered as a high-detail clip crop (``render_clip_crop`` — the shared
zoom primitive, 21-05 decision) and the dense arbitration model is asked ONE
narrow choice question through :func:`~bobbytailor.vision.schemas.verify_retry_schema`.

Design contract (normative):

- **Bounded**: at most ``max_retries_per_item`` (default 2) attempts per
  flag. A definite answer (confirm / deny / relabel) stops immediately; only
  an "unclear" answer (or an error result) consumes another attempt, with a
  wider crop for more context.
- **Budget-guarded**: every completed call's ``_cost_usd`` is charged to the
  run :class:`~bobbytailor.vision.ensemble.BudgetGuard` (21-13 convention: a
  refused charge discards the answer — the ledger only ever holds
  paid-and-accepted work). Once the budget is exhausted the remaining flags
  are returned untouched and stay flagged (Pitfall 7: never a silent
  partial).
- **ID/choice-grounded**: answers are constrained by the
  ``verify_retry_schema`` choice enum — free-text (and any number) is
  grammatically impossible. A retry can adjust SEMANTICS (relabel) or
  confirm/deny; it can never invent a quantity on a vector sheet — the
  relabel branch touches the ``new_label`` name field only, quantities and
  units pass through unchanged.
- **Flag, never suppress**: every processed flag comes back with a
  ``resolution`` (``'relabeled' | 'confirmed' | 'unresolved'``) and a full
  ``retry_history`` audit trail (question, answer, confidence, model, cost
  per attempt). Items with no geometry anchor are skipped (zero API calls)
  and stay flagged unresolved.

All API access goes through the injectable ``analyze_call`` callable
(TakeoffPipeline analyzer-injection pattern) — this module never touches the
Anthropic client directly, so tests stub it with zero API spend. Routing is
the caller's: ``pass_type="verify_retry"`` resolves to ``CLAUDE_MODEL_DENSE``
via the ``('*', 'verify_retry')`` MODEL_ROUTING row (21-05).
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple

import fitz

from bobbytailor.vision.ensemble import BudgetExceeded
from bobbytailor.vision.schemas import verify_retry_schema

logger = logging.getLogger(__name__)

# Confirm/deny choice set for out-of-band quantity questions (RESEARCH §3
# handoff 3: "does this region actually show N <item>? yes/no/unclear").
CONFIRM_CHOICES: Tuple[str, ...] = ("yes", "no", "unclear")

# The decline sentinel — always answerable so the model is never forced to
# pick a wrong label (prefer unclear over guessing, mirroring UNKNOWN_LABEL).
UNCLEAR_ANSWER = "unclear"

# Hard retry cap per flagged item (RESEARCH §3: "Bounded: <=2 retries per
# item, budget-guarded"). Callers may lower it, never raise it silently —
# the threat model's cost-runaway mitigation depends on this bound.
MAX_RETRIES_PER_ITEM = 2

# Crop rendering: the shared 1568px long-edge target (21-05 decision — zoom
# INTO the region at native detail, not bigger whole-sheet rasters). The
# second attempt widens the context window around the anchor geometry.
_CROP_TARGET_PX = 1568
_PAD_FRACTIONS: Tuple[float, ...] = (0.25, 0.75)
_MIN_PAD_PT = 12.0


def _result_cost_usd(result) -> float:
    """The ``_cost_usd`` metadata stamp of an analyzer result (0.0 fallback)."""
    if isinstance(result, dict):
        try:
            return float(result.get("_cost_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _flag_bbox(flag: dict, registry: Dict[str, dict]) -> Optional[Tuple[float, float, float, float]]:
    """Geometry anchor for *flag*: registry lookup by candidate_id, else an
    explicit ``bbox_pt`` carried on the flag record. None = no anchor."""
    bbox = None
    cid = flag.get("candidate_id")
    if cid:
        meta = registry.get(cid) or {}
        bbox = meta.get("bbox_pt")
    if not bbox:
        bbox = flag.get("bbox_pt")
    if not bbox:
        return None
    try:
        x0, y0, x1, y1 = [float(v) for v in tuple(bbox)]
    except (TypeError, ValueError):
        return None
    if x1 - x0 <= 0 or y1 - y0 <= 0:
        return None
    return (x0, y0, x1, y1)


def _padded_rect(page, bbox_pt, pad_frac: float) -> Optional[fitz.Rect]:
    """*bbox_pt* padded by ``pad_frac`` of its long edge, clamped to the page."""
    rect = fitz.Rect(bbox_pt)
    if rect.is_empty or rect.is_infinite:
        return None
    pad = max(_MIN_PAD_PT, pad_frac * max(rect.width, rect.height))
    rect = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)
    page_rect = getattr(page, "rect", None)
    if page_rect is not None:
        rect = rect & fitz.Rect(page_rect)
    if rect.is_empty or rect.width <= 0 or rect.height <= 0:
        return None
    return rect


def _render_crop(page, bbox_pt, pad_frac: float):
    """High-detail clip crop around the flagged geometry (PIL image or None).

    Defers the ``render_clip_crop`` import: ``pdf_analyzer`` imports
    ``takeoff_pipeline``, which imports this module — a module-level import
    here would be circular (same pattern as ``ensemble._render_tile``).
    """
    rect = _padded_rect(page, bbox_pt, pad_frac)
    if rect is None:
        return None
    from bobbytailor.pipeline.pdf_analyzer import render_clip_crop  # deferred (circular-import avoidance)

    return render_clip_crop(page, rect, target_px=_CROP_TARGET_PX)


def _question_and_choices(flag: dict) -> Tuple[str, List[str], str]:
    """Build the narrow arbitration question for *flag*.

    Returns ``(question, choices, mode)`` where mode is:

    - ``"label"`` when the flag carries a plausible-label ``choices`` list
      (label dispute — e.g. "ladder or stair?"). The decline sentinel
      ``"unclear"`` is always appended so the model is never forced to pick.
    - ``"confirm"`` otherwise (out-of-band quantity — confirm/deny question,
      RESEARCH §3: "does this region actually show N <item>? yes/no/unclear").
    """
    item = str(flag.get("item") or "this item").strip() or "this item"
    qty = flag.get("qty")
    unit = str(flag.get("unit") or "").strip()

    raw_choices = [str(c).strip() for c in flag.get("choices") or [] if str(c).strip()]
    if raw_choices:
        choices = list(dict.fromkeys(raw_choices))
        if UNCLEAR_ANSWER not in [c.lower() for c in choices]:
            choices.append(UNCLEAR_ANSWER)
        question = (
            'Geometric clustering found a symbol currently labeled "%s"'
            % item
        )
        if qty is not None:
            question += " (deterministic instance count: %s%s)" % (
                qty, " %s" % unit if unit else "",
            )
        question += (
            ". Which of the listed legend items does the cropped symbol "
            'actually show? Pick exactly one choice; answer "%s" only if the '
            "crop is genuinely ambiguous." % UNCLEAR_ANSWER
        )
        return question, choices, "label"

    qty_text = "a quantity of %s%s" % (qty, " %s" % unit if unit else "")
    question = (
        'A verification rule flagged "%s" with %s as out-of-band. '
        "Does the cropped region actually show %s of %s? "
        'Answer "yes" to confirm the flagged value is real, "no" to deny it, '
        'or "%s" if the crop cannot settle it.'
        % (item, qty_text, qty_text, item, UNCLEAR_ANSWER)
    )
    return question, list(CONFIRM_CHOICES), "confirm"


def _apply_answer(record: dict, answer, mode: str) -> Optional[str]:
    """Arbitrate one answer. Returns the resolution, or None to retry.

    Confirm mode: ``yes`` → ``'confirmed'``; ``no`` → ``'unresolved'`` (a
    definite deny keeps the flag — never suppressed); ``unclear`` → retry.

    Label mode: a label equal to the current item name → ``'confirmed'``;
    a different label → ``'relabeled'`` (``new_label`` set — SEMANTICS ONLY,
    the record's quantity/unit are never touched); ``unclear`` → retry.
    """
    norm = str(answer or "").strip().lower()
    if mode == "confirm":
        if norm == "yes":
            return "confirmed"
        if norm == "no":
            # Definite deny: the flag stays (flag, never suppress) and there
            # is nothing further to ask — re-querying a definite answer would
            # only burn budget.
            return "unresolved"
        return None  # unclear → widen the crop and re-ask (bounded)

    if norm == UNCLEAR_ANSWER:
        return None
    current = str(record.get("item") or "").strip().lower()
    if norm == current:
        return "confirmed"
    # Relabel branch: touches the name/label field ONLY — quantity and unit
    # pass through unchanged (no quantity-mutation path exists for vector
    # items; counts stay deterministic).
    record["new_label"] = str(answer).strip()
    return "relabeled"


def retry_flagged_items(
    flags: List[dict],
    page,
    registry: Dict[str, dict],
    analyze_call: Callable,
    budget=None,
    max_retries_per_item: int = MAX_RETRIES_PER_ITEM,
    sheet_type: Optional[str] = None,
) -> List[dict]:
    """Arbitrate flagged items with bounded targeted-crop re-queries.

    Per flag: locate the geometry anchor (registry lookup by the flag's
    ``candidate_id``), render a high-DPI clip crop around it, and ask ONE
    narrow choice question through ``verify_retry_schema``. Apply the answer:
    relabel (semantics only), confirm (flag downgraded to a note), or
    deny/unclear (flag kept). Every touched item gets ``retry_history``
    entries; nothing is ever silently suppressed.

    Args:
        flags:        Flag records. Recognized keys: ``sheet``, ``item``,
                      ``qty``, ``unit`` (QuantityVerifier shape),
                      ``candidate_id`` (registry anchor), ``choices``
                      (plausible labels → label-dispute mode) and
                      ``flag_type`` (carried through for audit).
        page:         Open ``fitz.Page`` the flags refer to.
        registry:     ``{candidate_id: {"bbox_pt": ..., "kind": ...}}`` —
                      the fusion candidate registry (bboxes in PDF points).
        analyze_call: Injectable analyzer with the ``analyze_drawing``
                      signature; called with ``pass_type="verify_retry"``,
                      the crop image and the choice schema. Model routing is
                      the analyzer's (``('*', 'verify_retry')`` → dense).
        budget:       Optional :class:`~bobbytailor.vision.ensemble.BudgetGuard`;
                      every completed call is charged. Exhaustion (or a
                      refused charge) stops the pass — remaining flags are
                      returned untouched and stay flagged.
        max_retries_per_item: Hard attempt cap per flag (default 2).
        sheet_type:   Sheet type forwarded to the analyzer for routing.

    Returns:
        Updated flag records (one per input flag, same order). Processed
        records carry ``resolution`` (``'relabeled'|'confirmed'|'unresolved'``),
        ``retry_history`` and — for relabels — ``new_label``. Records skipped
        for budget carry no additions; records without a geometry anchor get
        ``resolution='unresolved'`` + ``retry_skipped='no_geometry_anchor'``
        with zero API calls.
    """
    results: List[dict] = []
    if not flags:
        return results
    registry = registry or {}
    budget_stop = False

    for flag in flags:
        if budget_stop or (budget is not None and budget.exhausted):
            # Budget exhausted: the retry pass is skipped for everything
            # left — remaining flags are returned untouched and stay flagged
            # (threat model: cost-runaway mitigation; Pitfall 7 honesty).
            budget_stop = True
            results.append(dict(flag))
            continue

        record = dict(flag)
        bbox = _flag_bbox(record, registry)
        if bbox is None:
            # No geometry anchor — nothing to crop; stays flagged unresolved
            # with zero API spend.
            record["resolution"] = "unresolved"
            record["retry_history"] = []
            record["retry_skipped"] = "no_geometry_anchor"
            results.append(record)
            continue

        question, choices, mode = _question_and_choices(record)
        schema = verify_retry_schema(choices)
        history: List[dict] = []
        resolution: Optional[str] = None

        attempts = max(1, int(max_retries_per_item))
        for attempt in range(attempts):
            if budget is not None and budget.exhausted:
                budget_stop = True
                break

            pad = _PAD_FRACTIONS[min(attempt, len(_PAD_FRACTIONS) - 1)]
            try:
                crop = _render_crop(page, bbox, pad)
            except Exception as exc:  # noqa: BLE001 — arbitration is additive
                logger.warning(
                    "verify_retry: crop render failed for %r (%s)",
                    record.get("item"), exc,
                )
                crop = None
            if crop is None:
                record["retry_skipped"] = "crop_render_failed"
                break

            try:
                res = analyze_call(
                    "",  # screenshot_path unused — images supplies content
                    record.get("sheet") or "",
                    pass_type="verify_retry",
                    sheet_type=sheet_type,
                    output_schema=schema,
                    images=[crop],
                    user_hint=question,
                )
            except BudgetExceeded:
                budget_stop = True
                break
            if budget is not None:
                try:
                    budget.charge(_result_cost_usd(res))
                except BudgetExceeded:
                    # Refused charge → the answer is discarded (the ledger
                    # only ever holds paid-and-accepted work — 21-13
                    # charging convention) and the pass stops.
                    budget_stop = True
                    break

            if not isinstance(res, dict) or res.get("error"):
                history.append(
                    {
                        "attempt": attempt + 1,
                        "question": question,
                        "answer": None,
                        "confidence": None,
                        "model": res.get("_model_used", "") if isinstance(res, dict) else "",
                        "cost_usd": _result_cost_usd(res),
                        "error": (
                            str(res.get("error"))
                            if isinstance(res, dict)
                            else "non-dict analyzer result"
                        ),
                    }
                )
                continue  # error consumes an attempt; bounded by the cap

            answer = res.get("answer")
            history.append(
                {
                    "attempt": attempt + 1,
                    "question": question,
                    "answer": answer,
                    "confidence": res.get("confidence"),
                    "model": str(res.get("_model_used") or ""),
                    "cost_usd": _result_cost_usd(res),
                }
            )
            resolution = _apply_answer(record, answer, mode)
            if resolution is not None:
                break
            # unclear → the next attempt uses a wider crop for more context.

        record["retry_history"] = history
        record["resolution"] = resolution or "unresolved"
        results.append(record)
        logger.info(
            "verify_retry: %r → %s after %d attempt(s)",
            record.get("item"), record["resolution"], len(history),
        )

    return results
