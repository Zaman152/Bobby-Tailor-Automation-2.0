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


# ── fuse_sheet: ID-grounded label application ────────────────────────────────

# Label a symbol group as this when no legend item matches (must stay in sync
# with bobbytailor.vision.schemas.UNKNOWN_LABEL — imported lazily below to
# keep this module import-light).
_UNKNOWN_LABEL = "unknown"


def _field(obj, name: str, default=None):
    """Read a field from a dataclass-like object or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ── Project-vocabulary measure basis ─────────────────────────────────────────
#
# The autonomous project vocabulary (object_vocabulary.build_project_vocabulary)
# names every distinct object type AND carries its MEASURE BASIS: count, linear,
# wall_area, floor_area, roof_area. Fusion uses the basis to decide which
# deterministic geometry to bind to a named line item — walls become SF (LF ×
# height) when their vision label resolves to a wall_area object, and
# floor/roof-plane items get the measured building footprint area.

_WALL_AREA_BASIS = "wall_area"
_FLOOR_ROOF_BASES = frozenset({"floor_area", "roof_area"})


def _iter_vocabulary(vocabulary):
    """Yield ``(name, basis, unit)`` for each PRIMARY vocabulary object.

    Accepts either the parsed object LIST
    (``[{"name","measure","unit","aliases"}, ...]`` — the pipeline's
    ``self._project_vocabulary``) or a name→info DICT
    (``{"CMU Wall": {"basis": "wall_area", "unit": "SF"}, ...}``). Aliases are
    NOT yielded here (they are lookup-only — see :func:`_vocabulary_basis_map`).
    """
    if isinstance(vocabulary, dict):
        for name, info in vocabulary.items():
            if isinstance(info, dict):
                yield name, info.get("basis") or info.get("measure"), info.get("unit")
            elif isinstance(info, str):
                yield name, info, None
    elif isinstance(vocabulary, list):
        for obj in vocabulary:
            if isinstance(obj, dict):
                yield obj.get("name"), obj.get("measure") or obj.get("basis"), obj.get("unit")


def _vocabulary_basis_map(vocabulary) -> Dict[str, dict]:
    """Case/alias-insensitive ``normalized_name -> {'basis','unit','name'}`` map.

    Primary names win over aliases on a collision (``setdefault``). Aliases are
    included only for the object-LIST form (the name→info dict form has no
    alias channel). Returns an empty map for ``None`` / empty vocabulary so
    fusion behavior is unchanged when no vocabulary exists (additive-only).
    """
    result: Dict[str, dict] = {}
    for name, basis, unit in _iter_vocabulary(vocabulary):
        if isinstance(name, str) and name.strip():
            result.setdefault(
                name.strip().lower(), {"basis": basis, "unit": unit, "name": name}
            )
    if isinstance(vocabulary, list):
        for obj in vocabulary:
            if not isinstance(obj, dict):
                continue
            basis = obj.get("measure") or obj.get("basis")
            unit = obj.get("unit")
            name = obj.get("name")
            for alias in obj.get("aliases") or []:
                if isinstance(alias, str) and alias.strip():
                    result.setdefault(
                        alias.strip().lower(),
                        {"basis": basis, "unit": unit, "name": name},
                    )
    return result


def _wall_candidate_id(thickness_class: str) -> str:
    """Wall candidate ID for a thickness class ("TC1" → "WALL-TC1")."""
    cls = str(thickness_class)
    return cls if cls.startswith("WALL-") else "WALL-%s" % cls


def _polygon_bbox(polygon_wkt: str) -> tuple:
    """PDF-point bbox of a WKT polygon (shapely lazily; zeros on failure)."""
    try:
        from shapely import wkt as _wkt  # lazy — heavy import

        return tuple(round(v, 3) for v in _wkt.loads(polygon_wkt).bounds)
    except Exception:  # noqa: BLE001
        return (0.0, 0.0, 0.0, 0.0)


def _walls_bbox_by_class(walls) -> Dict[str, tuple]:
    """Union bbox of every wall centerline, grouped by candidate ID."""
    boxes: Dict[str, List[float]] = {}
    for wall in walls or []:
        cid = _field(wall, "candidate_id", "") or _wall_candidate_id(
            _field(wall, "thickness_class", "") or ""
        )
        if not cid or cid == "WALL-":
            continue
        for x, y in _field(wall, "centerline_pt", ()) or ():
            box = boxes.get(cid)
            if box is None:
                boxes[cid] = [x, y, x, y]
            else:
                box[0] = min(box[0], x)
                box[1] = min(box[1], y)
                box[2] = max(box[2], x)
                box[3] = max(box[3], y)
    return {cid: tuple(round(v, 3) for v in box) for cid, box in boxes.items()}


def build_registry(deterministic_bundle: dict) -> Dict[str, dict]:
    """Candidate registry ``{candidate_id: {"bbox_pt": ..., "kind": ...}}``.

    Built from ALL deterministic candidates in the bundle: symbol groups
    (``SYM-n``), wall thickness classes (``WALL-TCn``), room polygons
    (``ROOM-n``) and viewport regions (``Rn``). Every candidate carries its
    PDF-point bbox in OUR registry keyed by ID — the model is never asked
    for coordinates (RESEARCH §3 "Grounding answers back to geometry").
    """
    registry: Dict[str, dict] = {}

    for group in deterministic_bundle.get("symbol_groups") or []:
        cid = _field(group, "candidate_id", "")
        if cid:
            registry[cid] = {
                "bbox_pt": tuple(_field(group, "representative_bbox_pt", ()) or ()),
                "kind": "symbol_group",
            }

    walls = deterministic_bundle.get("walls") or []
    for cid, bbox in _walls_bbox_by_class(walls).items():
        registry[cid] = {"bbox_pt": bbox, "kind": "wall_class"}
    # Classes present in wall_lf_by_class but without segment records still
    # need registry entries so their label answers ground-validate.
    for cls in deterministic_bundle.get("wall_lf_by_class") or {}:
        registry.setdefault(
            _wall_candidate_id(cls), {"bbox_pt": (0.0, 0.0, 0.0, 0.0), "kind": "wall_class"}
        )

    for room in deterministic_bundle.get("rooms") or []:
        cid = _field(room, "candidate_id", "")
        if cid:
            registry[cid] = {
                "bbox_pt": _polygon_bbox(_field(room, "polygon_wkt", "") or ""),
                "kind": "room",
            }

    for viewport in deterministic_bundle.get("viewports") or []:
        cid = _field(viewport, "region_id", "")
        if cid:
            registry[cid] = {
                "bbox_pt": tuple(_field(viewport, "bbox_pt", ()) or ()),
                "kind": "region",
            }

    return registry


def _reject_unknown_id(candidate_id, source: str, answer, rejected: List[dict]) -> None:
    rejected.append(
        {
            "candidate_id": candidate_id,
            "source": source,
            "answer": answer,
            "reason": "unknown_candidate_id",
        }
    )


def _grounded_labels(
    entries,
    id_key: str,
    source: str,
    registry: Dict[str, dict],
    rejected: List[dict],
) -> Dict[str, dict]:
    """Index vision label entries by candidate ID, dropping out-of-registry IDs.

    Every vision answer ID is validated against the registry (membership
    check); unknown IDs are dropped and flagged in ``fusion_rejected`` —
    they can never produce a component (threat model: grounding bypass).
    """
    grounded: Dict[str, dict] = {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        cid = entry.get(id_key)
        if cid not in registry:
            _reject_unknown_id(cid, source, entry.get("label"), rejected)
            continue
        grounded[cid] = entry
    return grounded


def _fuse_symbol_groups(
    bundle: dict, labels_by_id: Dict[str, dict], components: List[dict]
) -> None:
    """Symbol groups → EA components; count is ALWAYS the deterministic size."""
    for group in bundle.get("symbol_groups") or []:
        cid = _field(group, "candidate_id", "")
        if not cid:
            continue
        count = int(_field(group, "count", 0) or 0)
        group_conf = _field(group, "confidence", "medium")
        group_review = bool(_field(group, "needs_review", False))
        entry = labels_by_id.get(cid)
        label = (entry or {}).get("label")

        if entry and label and label != _UNKNOWN_LABEL:
            components.append(
                {
                    "name": label,
                    "quantity": count,
                    "unit": "EA",
                    "provenance": "geometry",
                    "confidence": _min_confidence(group_conf, entry.get("confidence")),
                    "candidate_id": cid,
                    "needs_review": group_review,
                    "review_reason": (
                        "symbol group has mixed text tags" if group_review else ""
                    ),
                }
            )
        else:
            # Unlabeled / "unknown" label → the deterministic count is still
            # emitted (flag-don't-guess), named by contained text or the ID.
            texts = _field(group, "contained_texts", []) or []
            name = " / ".join(t for t in texts if t) or cid
            components.append(
                {
                    "name": name,
                    "quantity": count,
                    "unit": "EA",
                    "provenance": "geometry",
                    "confidence": "low",
                    "candidate_id": cid,
                    "needs_review": True,
                    "review_reason": (
                        "vision label unknown" if entry else "no vision label for symbol group"
                    ),
                }
            )


def _fuse_wall_classes(
    bundle: dict,
    labels_by_id: Dict[str, dict],
    components: List[dict],
    vocab_map: Optional[Dict[str, dict]] = None,
    wall_height_ft: Optional[float] = None,
    wall_height_source: Optional[str] = None,
) -> None:
    """Wall thickness classes → LF, or SF when the label is a wall_area object.

    LF always comes from geometry. When a wall class's vision label resolves
    (via the project vocabulary, case/alias-insensitive) to a ``wall_area``
    object AND a positive wall height is available, the component is emitted as
    area = ``round(LF × height, 1)`` SF — the manifest-era wall-area binding,
    now driven by the autonomous vocabulary + resolved height. The height and
    its source are recorded in the formula; a ``default``-sourced height flags
    the item for review. Any other label (or none) keeps LF exactly as before.
    """
    vocab_map = vocab_map or {}
    lf_by_class = bundle.get("wall_lf_by_class") or {}
    for cls in sorted(lf_by_class):
        lf = lf_by_class[cls]
        cid = _wall_candidate_id(cls)
        entry = labels_by_id.get(cid)
        label = (entry or {}).get("label")
        if entry and label and label != _UNKNOWN_LABEL:
            vocab = vocab_map.get(str(label).strip().lower())
            basis = (vocab or {}).get("basis")
            if (
                basis == _WALL_AREA_BASIS
                and wall_height_ft is not None
                and float(wall_height_ft) > 0
            ):
                height = float(wall_height_ft)
                source = wall_height_source or "default"
                is_default = source == "default"
                components.append(
                    {
                        "name": label,
                        "quantity": round(float(lf) * height, 1),
                        "unit": "SF",
                        "provenance": "geometry",
                        "confidence": _min_confidence(
                            "high" if not is_default else "medium",
                            entry.get("confidence"),
                        ),
                        "candidate_id": cid,
                        "formula": "%.1f LF × %.1f ft height (%s)"
                        % (round(float(lf), 1), height, source),
                        "wall_height_ft": height,
                        "wall_height_source": source,
                        "needs_review": is_default,
                        "review_reason": (
                            "wall height assumed (%s) — verify on sheet" % source
                            if is_default
                            else ""
                        ),
                    }
                )
                continue
            components.append(
                {
                    "name": label,
                    "quantity": round(float(lf), 1),
                    "unit": "LF",
                    "provenance": "geometry",
                    "confidence": _min_confidence("high", entry.get("confidence")),
                    "candidate_id": cid,
                    "needs_review": False,
                    "review_reason": "",
                }
            )
        else:
            components.append(
                {
                    "name": cid,
                    "quantity": round(float(lf), 1),
                    "unit": "LF",
                    "provenance": "geometry",
                    "confidence": "low",
                    "candidate_id": cid,
                    "needs_review": True,
                    "review_reason": "unlabeled wall thickness class",
                }
            )


def _fuse_project_area_items(
    bundle: dict, vocabulary, components: List[dict]
) -> None:
    """Whole-building floor/roof vocabulary items → footprint-area SF components.

    For each vocabulary object whose measure basis is ``floor_area`` or
    ``roof_area`` (sealed concrete, exposed structure, roof deck …), emit ONE
    component whose quantity is the measured building footprint area — these
    planes legitimately span the whole footprint for this building type, which
    is exactly why they fell back to ~6 SF room slivers without a footprint
    binding. Guarded: nothing is invented unless a footprint with
    ``area_sf > 0`` exists. Each name is emitted once (first-seen).
    """
    footprint = bundle.get("footprint")
    if not footprint:
        return
    area_sf = _field(footprint, "area_sf", None)
    try:
        area_val = float(area_sf) if area_sf is not None else 0.0
    except (TypeError, ValueError):
        area_val = 0.0
    if area_val <= 0:
        return
    confidence = _field(footprint, "confidence", "medium")
    needs_review = bool(_field(footprint, "needs_review", False))
    seen = set()
    for name, basis, _unit in _iter_vocabulary(vocabulary):
        if basis not in _FLOOR_ROOF_BASES:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        key = name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        components.append(
            {
                "name": name,
                "quantity": round(area_val, 1),
                "unit": "SF",
                "provenance": "geometry",
                "confidence": confidence,
                "basis": basis,
                "needs_review": needs_review,
                "review_reason": (
                    "whole-building %s bound to measured footprint" % basis
                ),
            }
        )


def _fuse_rooms(
    bundle: dict,
    labels_by_id: Dict[str, dict],
    components: List[dict],
    rejected: List[dict],
) -> None:
    """Rooms → SF components; SF from the polygon regardless of label source.

    Vision labels apply ONLY to rooms with ``label_source == 'none'`` — a
    deterministic text-in-polygon binding is never overridden; a vision
    attempt to relabel a text-bound room is audited in ``fusion_rejected``.
    """
    fpp = float(bundle.get("fpp") or 0.0)
    for room in bundle.get("rooms") or []:
        cid = _field(room, "candidate_id", "")
        if not cid:
            continue
        label = _field(room, "label", "") or ""
        source = _field(room, "label_source", "none") or "none"
        room_conf = _field(room, "confidence", "medium")
        area_pt2 = float(_field(room, "area_pt2", 0.0) or 0.0)

        quantity: Optional[float]
        if fpp > 0:
            quantity = round(area_pt2 * fpp * fpp, 1)
            no_scale = False
        else:
            quantity = None  # flag-don't-guess: no scale → no number
            no_scale = True

        entry = labels_by_id.get(cid)
        confidence = room_conf
        label_from_vision = False
        if source == "none":
            if entry and entry.get("label"):
                label = entry["label"]
                confidence = _min_confidence(room_conf, entry.get("confidence"))
                label_from_vision = True
        elif entry and entry.get("label") and entry["label"] != label:
            rejected.append(
                {
                    "candidate_id": cid,
                    "source": "room_labels",
                    "answer": entry.get("label"),
                    "reason": "label_override_blocked",
                    "kept_label": label,
                }
            )

        unlabeled = not label
        needs_review = no_scale or unlabeled
        reasons = []
        if no_scale:
            reasons.append("no scale bound (fpp missing)")
        if unlabeled:
            reasons.append("room unlabeled (vision fallback returned nothing)")
        components.append(
            {
                "name": label or cid,
                "quantity": quantity,
                "unit": "SF",
                "provenance": "geometry",
                "confidence": "low" if needs_review else confidence,
                "candidate_id": cid,
                "label_source": "vision" if label_from_vision else source,
                "needs_review": needs_review,
                "review_reason": "; ".join(reasons),
            }
        )


_ROW_NAME_KEYS = ("ITEM", "DESCRIPTION", "TYPE", "NAME")
_ROW_QTY_KEYS = ("QTY", "QUANTITY", "COUNT")
_ROW_UNIT_KEYS = ("UNIT", "UNITS", "UOM")


def _row_lookup(row: dict, keys) -> Optional[str]:
    """Case-insensitive first-match lookup across candidate column names."""
    upper = {str(k).strip().upper(): v for k, v in row.items()}
    for key in keys:
        value = upper.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _fuse_schedules(bundle: dict, components: List[dict]) -> None:
    """Schedule rows (tables.py) → components with schedule_table provenance.

    Rows are grouped by their name column; an explicit QTY cell is parsed
    verbatim (text-layer ground truth), otherwise each row counts as one
    installed instance (e.g. one door per door-schedule row).
    """
    for sched in bundle.get("schedules") or []:
        kind = str(_field(sched, "kind", "schedule") or "schedule")
        table_conf = _field(sched, "confidence", "medium")
        grouped: Dict[str, dict] = {}
        order: List[str] = []
        for row in _field(sched, "rows", []) or []:
            if not isinstance(row, dict):
                continue
            name = _row_lookup(row, _ROW_NAME_KEYS) or "%s schedule item" % kind.title()
            qty_text = _row_lookup(row, _ROW_QTY_KEYS)
            try:
                qty = float(qty_text) if qty_text is not None else 1.0
            except ValueError:
                qty = 1.0
            unit = (_row_lookup(row, _ROW_UNIT_KEYS) or "EA").upper()
            key = _norm_name(name)
            slot = grouped.get(key)
            if slot is None:
                grouped[key] = {"name": name, "quantity": qty, "unit": unit}
                order.append(key)
            else:
                slot["quantity"] += qty
        for key in order:
            slot = grouped[key]
            quantity = slot["quantity"]
            if quantity == int(quantity):
                quantity = int(quantity)
            components.append(
                {
                    "name": slot["name"],
                    "quantity": quantity,
                    "unit": slot["unit"],
                    "provenance": "schedule_table",
                    "confidence": table_conf,
                    "schedule_kind": kind,
                    "needs_review": False,
                    "review_reason": "",
                }
            )


def _fuse_footprint(bundle: dict, components: List[dict]) -> None:
    """Printed overall dimensions (footprint) → text_layer components."""
    footprint = bundle.get("footprint")
    if not footprint:
        return
    confidence = _field(footprint, "confidence", "medium")
    needs_review = bool(_field(footprint, "needs_review", False))
    reason = _field(footprint, "review_reason", "") or ""
    area_sf = _field(footprint, "area_sf", None)
    perimeter_lf = _field(footprint, "perimeter_lf", None)
    if area_sf:
        components.append(
            {
                "name": "Building Footprint",
                "quantity": area_sf,
                "unit": "SF",
                "provenance": "text_layer",
                "confidence": confidence,
                "needs_review": needs_review,
                "review_reason": reason,
            }
        )
    if perimeter_lf:
        components.append(
            {
                "name": "Building Perimeter",
                "quantity": perimeter_lf,
                "unit": "LF",
                "provenance": "text_layer",
                "confidence": confidence,
                "needs_review": needs_review,
                "review_reason": reason,
            }
        )


def fuse_sheet(
    deterministic_bundle: dict,
    vision_labels: dict,
    registry: Optional[Dict[str, dict]] = None,
    vocabulary=None,
    wall_height_ft: Optional[float] = None,
    wall_height_source: Optional[str] = None,
) -> dict:
    """Apply vision ID→label answers to deterministic candidates for a sheet.

    Every quantity in the output comes from the deterministic side (group
    counts, wall LF, room polygon SF, schedule cells, printed dimensions);
    vision supplies ONLY semantics: which legend item a symbol group is,
    which material a wall class is, what an unlabeled room is called, and
    which region is the main plan. A vision answer whose candidate ID is not
    in the registry is dropped and flagged in ``fusion_rejected``.

    Args:
        deterministic_bundle: Per-sheet deterministic candidates. Recognized
            keys (all optional): ``symbol_groups`` (SymbolGroup dicts or
            objects), ``walls`` + ``wall_lf_by_class`` ({"TC1": lf, ...}),
            ``rooms`` (RoomPolygon), ``viewports`` (Viewport),
            ``schedules`` (ScheduleTable), ``footprint`` (Footprint),
            ``fpp`` (feet per PDF point) and ``sheet_name``.
        vision_labels: Structured-output vision answers, keyed by the schema
            field names: ``matches`` (symbol gallery), ``wall_class_labels``
            + ``main_plan_region`` (semantic overlay pass) and
            ``room_labels`` (room fallback). Underscore metadata
            (``_cost_usd`` etc.) is carried through to the result.
        registry: ``{candidate_id: {"bbox_pt": ..., "kind": ...}}``. When
            None, built from the bundle via :func:`build_registry`.
        vocabulary: Optional project vocabulary — the parsed object LIST
            (``self._project_vocabulary``) or a name→info DICT. Carries each
            object's MEASURE BASIS (count/linear/wall_area/floor_area/
            roof_area) so wall classes labeled ``wall_area`` bind as SF
            (LF × height) and floor/roof-plane items bind to the footprint
            area. When None/empty, wall classes emit LF and no floor/roof
            items are invented (prior behavior).
        wall_height_ft: Resolved project wall height (ft) for the wall_area
            binding. When None or ≤ 0, wall classes stay LF.
        wall_height_source: Provenance of the height ("plan" | "learned" |
            "default"); a "default" height flags derived wall-area items.

    Returns:
        Extraction dict mirroring the analyze_drawing result shape:
        ``components`` (every one with ``provenance``/``needs_review``),
        ``fusion_rejected`` audit list, ``main_plan_region`` (when validly
        answered) and the standard underscore metadata fields.
    """
    vision_labels = vision_labels or {}
    if registry is None:
        registry = build_registry(deterministic_bundle)

    components: List[dict] = []
    rejected: List[dict] = []

    symbol_labels = _grounded_labels(
        vision_labels.get("matches"), "symbol_id", "matches", registry, rejected
    )
    wall_labels = _grounded_labels(
        vision_labels.get("wall_class_labels"),
        "wall_class_id",
        "wall_class_labels",
        registry,
        rejected,
    )
    room_labels = _grounded_labels(
        vision_labels.get("room_labels"), "room_id", "room_labels", registry, rejected
    )

    vocab_map = _vocabulary_basis_map(vocabulary)

    _fuse_symbol_groups(deterministic_bundle, symbol_labels, components)
    _fuse_wall_classes(
        deterministic_bundle,
        wall_labels,
        components,
        vocab_map=vocab_map,
        wall_height_ft=wall_height_ft,
        wall_height_source=wall_height_source,
    )
    _fuse_project_area_items(deterministic_bundle, vocabulary, components)
    _fuse_rooms(deterministic_bundle, room_labels, components, rejected)
    _fuse_schedules(deterministic_bundle, components)
    _fuse_footprint(deterministic_bundle, components)

    result: dict = {
        "components": components,
        "fusion_rejected": rejected,
        "_pass_type": "fusion",
        "_source_sheet": deterministic_bundle.get("sheet_name", ""),
        "_tokens_in": vision_labels.get("_tokens_in", 0),
        "_tokens_out": vision_labels.get("_tokens_out", 0),
        "_cost_usd": vision_labels.get("_cost_usd", 0),
        "_model_used": vision_labels.get("_model_used", ""),
    }

    main_region = vision_labels.get("main_plan_region")
    if main_region is not None:
        if main_region in registry:
            result["main_plan_region"] = main_region
        else:
            _reject_unknown_id(main_region, "main_plan_region", main_region, rejected)

    if rejected:
        logger.info(
            "fuse_sheet[%s]: %d vision answer(s) rejected (%s)",
            result["_source_sheet"],
            len(rejected),
            ", ".join(sorted({str(r.get("reason")) for r in rejected})),
        )
    return result
