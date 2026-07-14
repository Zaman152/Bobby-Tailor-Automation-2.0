"""Vision + geometry fusion layer (21-12, V3-ACC-01 core).

Principle (21-RESEARCH.md §3, normative): **geometry proposes, vision
disposes.** Vision never sees a raw sheet and free-associates quantities; it
sees *candidates with IDs* and returns *labels for IDs*. Every take-off
component carries a ``provenance`` value from :data:`PROVENANCE_RANK`, and
merge precedence is provenance rank — a ``vision_ensemble`` row can NEVER
overwrite the quantity/unit of a ``geometry`` / ``text_layer`` /
``schedule_table`` row. That rule is enforced structurally in code (hard
guard + ``fusion_rejected`` audit list), not just by rank ordering.

Two public operations:

- :func:`merge_with_provenance` — successor to
  ``claude_analyzer.merge_passes``: normalized-name dedup where the higher
  :data:`PROVENANCE_RANK` wins (equal rank → higher confidence → first
  seen). Components missing ``provenance`` default to ``vision_ensemble``
  (the safest floor). Rejected quantity claims are appended to the
  ``fusion_rejected`` audit list on the merged result.
- :func:`fuse_sheet` — applies vision ID→label answers to deterministic
  candidates (symbol groups, wall thickness classes, room polygons,
  viewport regions). Quantities always come from the deterministic side;
  vision answers referencing IDs outside the candidate registry are dropped
  and flagged (threat model: grounding bypass).

``merge_passes`` in ``claude_analyzer`` keeps working unchanged (backward
compat for pre-fusion passes); the pipeline switches to this module in 21-13.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Provenance enum (RESEARCH §3 "Keeping vision away from numbers") ─────────

# Rank: higher wins a merge collision. Geometry is deterministic math from
# vector paths; text_layer is read verbatim from the PDF (dimension strings,
# printed footprint); schedule_table is find_tables() structured rows;
# learned is the cross-run learning store; vision_ensemble is the ONLY
# provenance a model-guessed number may carry.
PROVENANCE_RANK: Dict[str, int] = {
    "geometry": 5,
    "text_layer": 4,
    "schedule_table": 3,
    "learned": 2,
    "vision_ensemble": 1,
}

# Components with a missing/unknown provenance are treated as the safest
# floor: model output that must never displace deterministic values.
DEFAULT_PROVENANCE = "vision_ensemble"

# Deterministic sources: quantities from these can never be overwritten by a
# vision_ensemble row (threat model "grounding bypass" — hard guard below).
DETERMINISTIC_PROVENANCES = frozenset({"geometry", "text_layer", "schedule_table"})

_CONFIDENCE_ORDER: Dict[str, int] = {"high": 3, "medium": 2, "low": 1}

# Fields NEVER copied from a losing component into the winner during a merge
# collision. quantity/unit are the accuracy contract; provenance/confidence
# describe the winner's own value; name is the dedup identity (casing is
# handled separately); review/vote metadata describes the loser's value, not
# the winning item.
_PROTECTED_FIELDS = frozenset(
    {
        "quantity",
        "unit",
        "provenance",
        "confidence",
        "name",
        "needs_review",
        "review_reason",
        "vote",
        "votes",
        "fusion_rejected",
    }
)


# ── Provenance helpers ────────────────────────────────────────────────────────


def provenance_of(component: dict) -> str:
    """Component provenance, defaulting unknown/missing to the safest floor."""
    prov = component.get("provenance") if isinstance(component, dict) else None
    if prov in PROVENANCE_RANK:
        return str(prov)
    return DEFAULT_PROVENANCE


def provenance_rank(component: dict) -> int:
    """Numeric merge rank for a component (see :data:`PROVENANCE_RANK`)."""
    return PROVENANCE_RANK[provenance_of(component)]


def _confidence_rank(component: dict) -> int:
    conf = str(component.get("confidence") or "").strip().lower()
    return _CONFIDENCE_ORDER.get(conf, _CONFIDENCE_ORDER["low"])


def _min_confidence(*confidences: Optional[str]) -> str:
    """Lowest of the given confidence labels (unknown values count as low)."""
    best = "high"
    best_rank = _CONFIDENCE_ORDER["high"]
    for conf in confidences:
        label = str(conf or "").strip().lower()
        rank = _CONFIDENCE_ORDER.get(label, _CONFIDENCE_ORDER["low"])
        if rank < best_rank:
            best_rank = rank
            best = label if label in _CONFIDENCE_ORDER else "low"
    return best


def _norm_name(name) -> str:
    """merge_passes dedup convention: case-insensitive strip."""
    return str(name).strip().lower()


# ── merge_with_provenance ─────────────────────────────────────────────────────


def _resolve_collision(existing: dict, incoming: dict) -> Tuple[dict, dict]:
    """Pick the (winner, loser) of a normalized-name collision.

    HARD GUARD (threat model "grounding bypass"): a ``vision_ensemble``
    component can never displace a deterministic component — checked against
    the provenance STRINGS directly, independent of any rank arithmetic, so
    a future rank-table edit cannot silently weaken the invariant.

    Then: higher :data:`PROVENANCE_RANK` wins; equal rank → strictly higher
    confidence wins; otherwise first-seen (``existing``) wins.
    """
    existing_prov = provenance_of(existing)
    incoming_prov = provenance_of(incoming)

    # Structural no-overwrite guard — enforced in code, not just by ordering.
    if incoming_prov == DEFAULT_PROVENANCE and existing_prov in DETERMINISTIC_PROVENANCES:
        return existing, incoming
    if existing_prov == DEFAULT_PROVENANCE and incoming_prov in DETERMINISTIC_PROVENANCES:
        return incoming, existing

    existing_rank = PROVENANCE_RANK[existing_prov]
    incoming_rank = PROVENANCE_RANK[incoming_prov]
    if incoming_rank > existing_rank:
        return incoming, existing
    if incoming_rank < existing_rank:
        return existing, incoming
    # Equal rank → higher confidence; tie → first-seen wins.
    if _confidence_rank(incoming) > _confidence_rank(existing):
        return incoming, existing
    return existing, incoming


def _absorb_semantic_fields(winner: dict, loser: dict) -> None:
    """Copy the loser's extra semantic fields into the winner.

    Never touches quantity/unit (or any :data:`_PROTECTED_FIELDS` /
    underscore-metadata key). Adopts the loser's name CASING when the
    winner's is degenerate (all-lower or all-upper) and the loser's is not —
    same normalized identity, better presentation.
    """
    quantity_before = winner.get("quantity")
    unit_before = winner.get("unit")

    for key, value in loser.items():
        if key in _PROTECTED_FIELDS or key.startswith("_"):
            continue
        if key not in winner or winner[key] in (None, "", [], {}):
            winner[key] = value

    winner_name = str(winner.get("name") or "")
    loser_name = str(loser.get("name") or "")
    if (
        winner_name
        and loser_name
        and winner_name != loser_name
        and _norm_name(winner_name) == _norm_name(loser_name)
        and winner_name in (winner_name.lower(), winner_name.upper())
        and loser_name not in (loser_name.lower(), loser_name.upper())
    ):
        winner["name"] = loser_name

    # Post-condition assertion for the no-overwrite contract (threat model:
    # "assert + test"). Field absorption above excludes quantity/unit by
    # construction; this check makes any future regression loud.
    if winner.get("quantity") != quantity_before or winner.get("unit") != unit_before:
        raise AssertionError(
            "fusion invariant violated: quantity/unit of %r changed during "
            "semantic-field absorption" % winner.get("name")
        )


def _record_rejection(winner: dict, loser: dict, rejected: List[dict]) -> None:
    """Append an audit record when a losing component's quantity is discarded.

    Recorded cases:
    - a ``vision_ensemble`` loser carried ANY quantity against a
      deterministic winner (the hard no-overwrite guard firing), or
    - any lower-provenance loser carried a quantity/unit that CONFLICTS with
      the winner's value (a silent drop would hide a disagreement signal).

    Losers that agree with the winner (same quantity and unit) are plain
    duplicates, not rejections — they are absorbed silently.
    """
    loser_qty = loser.get("quantity")
    if loser_qty is None:
        return

    winner_prov = provenance_of(winner)
    loser_prov = provenance_of(loser)
    vision_blocked = (
        loser_prov == DEFAULT_PROVENANCE and winner_prov in DETERMINISTIC_PROVENANCES
    )
    conflicts = loser_qty != winner.get("quantity") or (
        loser.get("unit") is not None and loser.get("unit") != winner.get("unit")
    )
    if not (vision_blocked or conflicts):
        return

    rejected.append(
        {
            "name": loser.get("name"),
            "quantity": loser_qty,
            "unit": loser.get("unit"),
            "provenance": loser_prov,
            "confidence": loser.get("confidence"),
            "rejected_by": winner_prov,
            "reason": (
                "vision_quantity_blocked"
                if vision_blocked
                else "lower_provenance_quantity_conflict"
            ),
        }
    )


def merge_with_provenance(results: List[dict]) -> dict:
    """Merge extraction results into one dict with provenance-ranked dedup.

    Successor to ``claude_analyzer.merge_passes``: components are
    deduplicated by normalized name (``strip().lower()`` — the merge_passes
    convention), and on collision the component with the higher
    :data:`PROVENANCE_RANK` wins. The loser's extra semantic fields (better
    name casing, notes) are merged into the winner WITHOUT touching
    quantity/unit; equal rank keeps the higher confidence, then first-seen.
    Components missing ``provenance`` default to ``vision_ensemble``.

    Structural guard: a ``vision_ensemble`` component can never overwrite
    the quantity/unit of a ``geometry`` / ``text_layer`` /
    ``schedule_table`` component — the losing claim is appended to the
    ``fusion_rejected`` audit list on the result instead.

    Args:
        results: Extraction dicts (analyze_drawing / fuse_sheet shape). The
                 first dict's non-component keys seed the merged result;
                 later dicts only fill keys that are still missing.
                 ``schedules`` lists are concatenated; input
                 ``fusion_rejected`` lists are carried through.

    Returns:
        Merged extraction dict: deduplicated ``components`` (every one
        carrying ``provenance``), concatenated ``schedules`` (when any), and
        the ``fusion_rejected`` audit list.
    """
    merged: dict = {}
    components: List[dict] = []
    index_by_key: Dict[str, int] = {}
    rejected: List[dict] = []
    schedules: List = []

    for result in results or []:
        if not isinstance(result, dict):
            continue

        for key, value in result.items():
            if key in ("components", "fusion_rejected"):
                continue
            if key == "schedules":
                if value:
                    schedules.extend(value)
                continue
            merged.setdefault(key, value)

        rejected.extend(result.get("fusion_rejected") or [])

        for component in result.get("components") or []:
            if not isinstance(component, dict) or not component.get("name"):
                continue
            component = dict(component)
            component["provenance"] = provenance_of(component)
            key = _norm_name(component["name"])

            slot = index_by_key.get(key)
            if slot is None:
                index_by_key[key] = len(components)
                components.append(component)
                continue

            existing = components[slot]
            winner, loser = _resolve_collision(existing, component)
            _record_rejection(winner, loser, rejected)
            _absorb_semantic_fields(winner, loser)
            components[slot] = winner

    merged["components"] = components
    if schedules:
        merged["schedules"] = schedules
    merged["fusion_rejected"] = rejected
    return merged
