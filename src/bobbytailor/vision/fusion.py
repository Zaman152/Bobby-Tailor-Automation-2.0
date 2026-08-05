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
import math
import re
from typing import Callable, Dict, List, Optional, Tuple

# Unit-count provenance, imported rather than restated so the report row and the
# resolver that produced the number cannot drift apart (threat T-23-32).
# ``room_tags`` is a pure extractor — it imports no pipeline and no PDF library
# at module scope — so this adds no import weight and no cycle.
from bobbytailor.deterministic.room_tags import (
    UNIT_COUNT_SOURCE_ASSUMED as _UNIT_COUNT_SOURCE_ASSUMED,
    UNIT_COUNT_SOURCE_MANIFEST as _UNIT_COUNT_SOURCE_MANIFEST,
)

# ONE definition of what a unit measures, shared with the aggregator (C3b).
# ``units`` is pure data with no pipeline imports, so this adds no cycle.
from bobbytailor.pipeline.units import (
    basis_class as _basis_class,
    unit_class as _unit_class,
    unit_conflict as _unit_conflict,
)

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


# ── Building LAYERS: what makes shared area DECLARED and not merely emergent ──
#
# A measured plan region is a plan AREA, and a building stacks several distinct
# LAYERS through that one area. On a shell warehouse the footprint legitimately
# backs the structural SLAB, the floor FINISH troweled onto it, and the exposed
# roof STRUCTURE overhead: three different objects an estimator prices
# separately and is right to. What is NOT legitimate is an object inheriting
# the footprint merely because its measure basis happens to be area-shaped —
# on Crow that handed the same 397,600 SF to Canopy, Vapor Barrier and Building
# Footprint as well, and an estimator bidding from that report priced the floor
# six times (INV-00 §4).
#
# So the exception INV-00 §4 asked for is layer-shaped: a measured region backs
# at most ONE line item PER BUILDING LAYER. Naming a layer is the DECLARATION —
# it is a statement about what the object is, made before any quantity exists,
# so the sharing can never be emergent. An object that names no layer declares
# nothing and is suppressed exactly as before.
#
# The order below is specific-first and load-bearing: "Sealed Concrete" is a
# FINISH laid on a slab, not the slab, so the finish patterns are tested before
# the slab patterns that its "concrete" token would otherwise match.
_BUILDING_LAYER_PATTERNS = (
    (
        "floor_finish",
        re.compile(
            r"\b(?:SEALED|POLISHED|STAINED|BURNISHED|DENSIFIED|TROWELED)\s+"
            r"CONCRETE\b"
            r"|\bFLOOR\s+(?:FINISH|SEALER|COATING|COVERING)\b"
            r"|\b(?:EPOXY|RESINOUS|TERRAZZO|CARPET|VCT|LVT)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ceiling",
        re.compile(r"\bCEILING\b|\bACT\b|\bSOFFIT\b", re.IGNORECASE),
    ),
    (
        "roof_structure",
        re.compile(
            r"\bEXPOSED\s+(?:STRUCTURE|STRUCTURAL|DECK|ROOF|FRAMING|JOISTS?)\b"
            r"|\bROOF\s+(?:STRUCTURE|DECK|FRAMING|SHEATHING|MEMBRANE)\b"
            r"|\bSTRUCTURE\s+ABOVE\b",
            re.IGNORECASE,
        ),
    ),
    (
        "slab",
        re.compile(
            r"\bSLAB\b|\bCONCRETE\s+(?:PAD|FLOOR)\b|\bFLOOR\s+DECK\b",
            re.IGNORECASE,
        ),
    ),
)

# ── name_source vocabulary for wall thickness classes (24-02, V4-DET-02) ─────
#
# Three authorities can name a wall thickness class, and a reader of the
# artifact must be able to tell WHICH one did. The first two strings are the
# ones fusion has always emitted and keep exactly their old meaning; the third
# is new and splits the case that used to hide inside "naming_library".
#
#: A vision label named the class (no confident deterministic bind existed).
_NAME_SOURCE_VISION = "vision"
#: A binding_hint bind named the class — NOT authoritative, always flagged.
_NAME_SOURCE_LIBRARY = "naming_library"
#: A printed-thickness match named the class — deterministic and authoritative.
#: This is the branch V4-DET-02 promoted out of the `elif` fallback.
_NAME_SOURCE_WALL_THICKNESS = "naming_library_thickness"

#: Case- and separator-insensitive squash, used ONLY to answer "did these two
#: authorities say the same thing?". Deliberately NOT a fuzzy matcher and
#: deliberately not plural-folding: `canonical_library_name` is plan 24-03's
#: to own, and duplicating a second name-folding rule here is how the two
#: drift apart.
_WALL_NAME_SQUASH_RE = re.compile(r"[^a-z0-9]+")


def _squash_wall_name(name) -> str:
    """Squash a wall object name for an AGREEMENT check (never for lookup)."""
    return _WALL_NAME_SQUASH_RE.sub("", str(name or "").strip().lower())


#: Naming authority, lowest number = most authoritative. A name the plan itself
#: printed outranks an estimator-standard library term, which in turn outranks a
#: verbatim learned string — so "Concrete Pad" (a learned verbatim) can never
#: anchor a region over "Sealed Concrete" merely by being emitted first.
_NAME_AUTHORITY = {
    "vision": 0,
    "plan_schedule_legend": 0,
    "schedule": 0,
    "text_layer": 1,
    "naming_library": 2,
    # A printed-thickness bind (24-02) is a REFINEMENT of "naming_library", not
    # a new authority: it is registered at the SAME rank so the precedence
    # inversion cannot silently re-order region-sharing arbitration. Omitting
    # it would drop the row to the unknown-source default (4) — BELOW
    # "learned" — which is the opposite of what the inversion means.
    _NAME_SOURCE_WALL_THICKNESS: 2,
    "library": 2,
    "learned": 3,
}


def _building_layer(name) -> Optional[str]:
    """The distinct building LAYER this object occupies, or None.

    None means the object declares no layer, so it may not share a measured
    region with anything: a Canopy is a discrete element with its own extent, a
    Vapor Barrier is part of the slab assembly rather than a layer occupied in
    its own right, and Building Footprint is the region itself, not a thing
    built in it. Each of those has to be MEASURED, never inherited.
    """
    text = str(name or "").strip()
    if not text:
        return None
    for layer, pattern in _BUILDING_LAYER_PATTERNS:
        if pattern.search(text):
            return layer
    return None


def _share_rank(component: dict) -> tuple:
    """Sort key picking which component ANCHORS a shared measured region.

    Deterministic and name-driven rather than emission-ordered: the old
    ``group[0]`` anchor meant vocabulary iteration order silently decided which
    line item an estimator saw.
    """
    layer = _building_layer(component.get("name"))
    authority = _NAME_AUTHORITY.get(
        str(component.get("name_source") or component.get("source") or "").strip().lower(),
        4,
    )
    return (0 if layer else 1, authority, str(component.get("name") or ""))


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

    # Open linear runs (23-15): every run is groundable like any other
    # candidate — a vision/label answer naming a run must ground-validate.
    for run in deterministic_bundle.get("linear_runs") or []:
        cid = _field(run, "candidate_id", "")
        if cid:
            registry[cid] = {
                "bbox_pt": tuple(_field(run, "bbox_pt", ()) or ()),
                "kind": "linear_run",
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


# ── Deterministic geometry fallback ("extract first, flag last") ─────────────
#
# When vision returns no/unknown label for a symbol group, an UNAMBIGUOUS
# geometric signal may still name it deterministically BEFORE we fall back to
# flagging. Conservative by design: only a large, dense, regular grid of
# identical repeated symbols — the unmistakable signature of a structural
# column grid — is named ("Columns"); everything weaker stays unnamed and
# flagged for human review. Never a replacement for a real vision/library label.

_GRID_MIN_COUNT = 20          # a "large" repeated grid; below this → flag, never guess
_GRID_MIN_LINES = 3           # need ≥3 columns AND ≥3 rows to call it a grid
_GRID_SPACING_CV_MAX = 0.25   # gap regularity: std/mean of line spacings must be tight
_GRID_MIN_FILL = 0.6          # points must fill ≥60% of rows×cols (dense, not a lucky scatter)


def _instance_centroids(group) -> List[Tuple[float, float]]:
    """(cx, cy) center of each instance bbox, skipping malformed boxes."""
    centroids: List[Tuple[float, float]] = []
    for box in _field(group, "instance_bboxes_pt", None) or []:
        try:
            x0, y0, x1, y1 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
        except (TypeError, ValueError, IndexError):
            continue
        centroids.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0))
    return centroids


def _median(values: List[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _cluster_lines(values: List[float], tol: float) -> List[float]:
    """Greedily snap sorted coordinates into gridlines within ``tol``."""
    lines: List[float] = []
    bucket: List[float] = []
    for v in sorted(values):
        if bucket and v - bucket[-1] > tol:
            lines.append(sum(bucket) / len(bucket))
            bucket = []
        bucket.append(v)
    if bucket:
        lines.append(sum(bucket) / len(bucket))
    return lines


def _spacing_is_regular(lines: List[float]) -> bool:
    """True when gridline spacings are tight (low coefficient of variation)."""
    if len(lines) < _GRID_MIN_LINES:
        return False
    gaps = [b - a for a, b in zip(lines, lines[1:]) if b - a > 0]
    if len(gaps) < _GRID_MIN_LINES - 1:
        return False
    mean = sum(gaps) / len(gaps)
    if mean <= 0:
        return False
    var = sum((g - mean) ** 2 for g in gaps) / len(gaps)
    cv = (var ** 0.5) / mean
    return cv <= _GRID_SPACING_CV_MAX


def _is_regular_grid(centroids: List[Tuple[float, float]], group) -> bool:
    """Do these instance centers form a dense, evenly-spaced rectangular grid?"""
    if len(centroids) < _GRID_MIN_COUNT:
        return False
    # Snap tolerance from the (identical) instance size — half a symbol
    # width/height, so instances in the same column/row collapse to one line.
    widths: List[float] = []
    heights: List[float] = []
    for box in _field(group, "instance_bboxes_pt", None) or []:
        try:
            widths.append(abs(float(box[2]) - float(box[0])))
            heights.append(abs(float(box[3]) - float(box[1])))
        except (TypeError, ValueError, IndexError):
            continue
    tol_x = max(_median(widths) * 0.5, 1.0)
    tol_y = max(_median(heights) * 0.5, 1.0)
    cols = _cluster_lines([c[0] for c in centroids], tol_x)
    rows = _cluster_lines([c[1] for c in centroids], tol_y)
    if len(cols) < _GRID_MIN_LINES or len(rows) < _GRID_MIN_LINES:
        return False
    if not (_spacing_is_regular(cols) and _spacing_is_regular(rows)):
        return False
    fill = len(centroids) / float(len(cols) * len(rows))
    return fill >= _GRID_MIN_FILL


# ── Naming-library-driven symbol binding (binding_hint → geometry) ───────────
#
# The AI naming pass (object_vocabulary.extract_naming_conventions), merged into
# the component library, tags each object with a ``binding_hint``. Two hints
# name unlabeled symbol clusters an estimator would recognise instantly:
#   - ``structural_grid_symbol`` → the LARGE repeated small marker on the
#     structural grid IS the columns (Crow: 136× → Columns);
#   - ``perimeter_jamb_symbol`` → a repeated small marker forming a perimeter
#     ring / door-jamb pattern IS the bollards (Crow: 56× ring → Bollards).
# Both are conservative: they fire ONLY when the library explicitly carries the
# hint AND the cluster geometry matches (uniform small markers; perimeter ring
# for bollards). Vision gallery labels stay primary; this fills unknowns.

_MARKER_MAX_SIZE_FT = 3.0        # a "marker" (column/bollard) is a small symbol
_MARKER_SIZE_CV_MAX = 0.5        # instances must be roughly uniform in size
_PERIMETER_MIN_COUNT = 8         # a plausible perimeter/jamb repetition
_PERIMETER_INNER_MAX_FILL = 0.25 # a ring is hollow: ≤25% of points in the centre


def _instance_dims(group) -> Tuple[List[float], List[float]]:
    """(widths, heights) of each instance bbox, skipping malformed boxes."""
    widths: List[float] = []
    heights: List[float] = []
    for box in _field(group, "instance_bboxes_pt", None) or []:
        try:
            widths.append(abs(float(box[2]) - float(box[0])))
            heights.append(abs(float(box[3]) - float(box[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return widths, heights


def _size_uniform(group) -> bool:
    """True when instance sizes are tight (low coefficient of variation)."""
    widths, heights = _instance_dims(group)
    if not widths:
        return False
    for dims in (widths, heights):
        mean = sum(dims) / len(dims)
        if mean <= 0:
            continue
        var = sum((d - mean) ** 2 for d in dims) / len(dims)
        if (var ** 0.5) / mean > _MARKER_SIZE_CV_MAX:
            return False
    return True


def _is_small_marker(group) -> bool:
    """True when the cluster's instances are small symbols (columns/bollards).

    Prefers the deterministic ``bbox_size_ft`` (real feet) when the group
    carries it — a marker is ≤ :data:`_MARKER_MAX_SIZE_FT` in both dims. Without
    it, falls back to a scale-independent test: the median instance is tiny
    relative to the cluster's overall spread.
    """
    size_ft = _field(group, "bbox_size_ft", None)
    if size_ft:
        try:
            return max(float(size_ft[0]), float(size_ft[1])) <= _MARKER_MAX_SIZE_FT
        except (TypeError, ValueError, IndexError):
            pass
    centroids = _instance_centroids(group)
    if len(centroids) < 2:
        return True
    xs = [c[0] for c in centroids]
    ys = [c[1] for c in centroids]
    span = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    widths, heights = _instance_dims(group)
    if not widths or span <= 0:
        return True
    med = _median([max(w, h) for w, h in zip(widths, heights)])
    return med <= 0.06 * span


# A structural column grid or a bollard ring is inherently a 2-D array of
# marks. A cluster whose instances lie on a SINGLE line (all at one Y, or one X)
# is a linear ANNOTATION — a dimension-tick strip or a grid-bubble row — never a
# 2-D object array, even when its count coincidentally matches an object total.
# (Crow ground truth §10: the 136-count "column" cluster is 136 ticks all at
# Y=1863.2 — a coincidence, not columns.) The MINOR-axis spread must exceed a
# few marker sizes, so a genuine grid/ring passes and a collinear strip fails.
_MARKER_2D_MIN_MINOR_FACTOR = 3.0   # minor-axis span ≥ this × the marker size …
_MARKER_2D_MIN_MINOR_PT = 6.0       # … and at least this many points, absolutely


def _minor_axis_span(group) -> Optional[float]:
    """Minor-axis (narrower) span of the instance centres, in points.

    Returns ``None`` when fewer than two centres are known — the spread cannot
    be judged, so callers must fall back to their unknown-case behaviour rather
    than treat absence of data as evidence either way.
    """
    centroids = _instance_centroids(group)
    if len(centroids) < 2:
        return None
    xs = [c[0] for c in centroids]
    ys = [c[1] for c in centroids]
    return min(max(xs) - min(xs), max(ys) - min(ys))


def _min_2d_span_pt(group) -> float:
    """The minor-axis span threshold separating a 2-D array from a collinear strip."""
    widths, heights = _instance_dims(group)
    marker = _median([max(w, h) for w, h in zip(widths, heights)]) if widths else 0.0
    return max(_MARKER_2D_MIN_MINOR_FACTOR * marker, _MARKER_2D_MIN_MINOR_PT)


def _is_2d_distributed(group) -> bool:
    """True when instance centres spread across 2-D (a real grid/ring), not a
    single collinear row/column of marks (dimension ticks, grid bubbles).

    Positive-evidence test: unknown spread (too few centres) → False. Guards the
    count-only grid/ring bindings, which must not CREATE a columns/bollards
    binding without proof of a 2-D layout (flag-don't-guess §10).
    """
    minor = _minor_axis_span(group)
    return minor is not None and minor >= _min_2d_span_pt(group)


def _is_collinear_strip(group) -> bool:
    """True only when a cluster is CONFIRMED collinear: enough marks to judge
    (``>= _GRID_MIN_COUNT``) AND their minor-axis span is below the 2-D
    threshold (a dimension-tick / grid-bubble strip).

    Negative-evidence test — used to DEMOTE an existing vision label, so it must
    never fire on sparse/absent instance data (that is merely unknown, not a
    strip). The asymmetry is deliberate: creating a columns binding needs proof
    of 2-D; overriding a vision label needs proof of collinearity.
    """
    centroids = _instance_centroids(group)
    if len(centroids) < _GRID_MIN_COUNT:
        return False
    minor = _minor_axis_span(group)
    return minor is not None and minor < _min_2d_span_pt(group)


def _is_perimeter_ring(group) -> bool:
    """True when instance centres hug the bbox edges (a hollow perimeter ring).

    Requires a genuine 2-D spread first — a collinear strip is all-boundary /
    zero-inner and would otherwise pass the hollow-ring test spuriously.
    """
    centroids = _instance_centroids(group)
    if len(centroids) < _PERIMETER_MIN_COUNT:
        return False
    if not _is_2d_distributed(group):
        return False
    xs = [c[0] for c in centroids]
    ys = [c[1] for c in centroids]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return False
    ix0, ix1 = x0 + 0.25 * w, x1 - 0.25 * w
    iy0, iy1 = y0 + 0.25 * h, y1 - 0.25 * h
    inner = sum(1 for px, py in centroids if ix0 < px < ix1 and iy0 < py < iy1)
    return inner / float(len(centroids)) <= _PERIMETER_INNER_MAX_FILL


def _binding_hint_map(vocabulary) -> Dict[str, dict]:
    """Map ``binding_hint -> {'name', 'basis'}`` from the naming library.

    First-seen object per hint wins. Accepts the object LIST form (merged
    component library / naming conventions, carrying ``binding_hint``) or a
    name→info dict. ``"other"`` / empty hints are ignored (no binding channel).
    Returns an empty map for None/empty vocabulary (additive-only).
    """
    out: Dict[str, dict] = {}
    items: List[dict] = []
    if isinstance(vocabulary, list):
        items = [o for o in vocabulary if isinstance(o, dict)]
    elif isinstance(vocabulary, dict):
        for name, info in vocabulary.items():
            entry = dict(info) if isinstance(info, dict) else {}
            entry.setdefault("name", name)
            items.append(entry)
    for obj in items:
        hint = str(obj.get("binding_hint") or "").strip().lower()
        if not hint or hint == "other":
            continue
        name = str(obj.get("name") or obj.get("canonical_name") or "").strip()
        if not name:
            continue
        basis = obj.get("basis") or obj.get("measure")
        out.setdefault(hint, {"name": name, "basis": basis})
    return out


def _library_symbol_bindings(groups, labels_by_id, binding_map) -> Dict[str, Tuple[str, str]]:
    """Bind unlabeled symbol clusters to naming-library objects by hint+geometry.

    Returns ``{candidate_id: (object_name, hint)}``. A cluster already given a
    real vision label is skipped (vision stays primary). ``structural_grid_symbol``
    binds the largest uniform small-marker cluster (count ≥ ``_GRID_MIN_COUNT``);
    ``perimeter_jamb_symbol`` binds the largest uniform small-marker cluster whose
    centres form a perimeter ring. Empty binding map → ``{}`` (unchanged behaviour).
    """
    if not binding_map:
        return {}
    unlabeled = []
    for g in groups or []:
        cid = _field(g, "candidate_id", "")
        if not cid:
            continue
        entry = labels_by_id.get(cid)
        if entry and entry.get("label") and entry["label"] != _UNKNOWN_LABEL:
            continue
        unlabeled.append(g)

    bindings: Dict[str, Tuple[str, str]] = {}

    grid = binding_map.get("structural_grid_symbol")
    if grid:
        cands = [
            g for g in unlabeled
            if int(_field(g, "count", 0) or 0) >= _GRID_MIN_COUNT
            and _size_uniform(g) and _is_small_marker(g)
            # A column grid is 2-D — reject a collinear dimension-tick strip
            # whose count coincidentally matches the column total (§10).
            and _is_2d_distributed(g)
        ]
        if cands:
            winner = max(cands, key=lambda g: int(_field(g, "count", 0) or 0))
            bindings[_field(winner, "candidate_id", "")] = (
                grid["name"], "structural_grid_symbol",
            )

    perim = binding_map.get("perimeter_jamb_symbol")
    if perim:
        cands = [
            g for g in unlabeled
            if _field(g, "candidate_id", "") not in bindings
            and int(_field(g, "count", 0) or 0) >= _PERIMETER_MIN_COUNT
            and _size_uniform(g) and _is_small_marker(g) and _is_perimeter_ring(g)
        ]
        if cands:
            winner = max(cands, key=lambda g: int(_field(g, "count", 0) or 0))
            bindings[_field(winner, "candidate_id", "")] = (
                perim["name"], "perimeter_jamb_symbol",
            )

    return bindings


def deterministic_symbol_name(group) -> Optional[str]:
    """Conservative geometry-only fallback label for an UNLABELED symbol group.

    Used ONLY when vision returns no/unknown label (see
    :func:`_fuse_symbol_groups`). A large (``count >= _GRID_MIN_COUNT``), dense,
    regular grid of identical repeated symbols is the unmistakable signature of
    a structural column grid → ``"Columns"``. Weak or ambiguous signals return
    ``None`` so the group stays flagged for human review (flag-don't-guess).
    This is a FALLBACK, never a replacement for a real vision/library label.
    """
    count = int(_field(group, "count", 0) or 0)
    if count < _GRID_MIN_COUNT:
        return None
    if _is_regular_grid(_instance_centroids(group), group):
        return "Columns"
    return None


# ── Bollard co-located 2×-dedup ──────────────────────────────────────────────
#
# A bollard is often drawn as TWO concentric marks (pipe + cap), so the
# deterministic clusterer counts each physical bollard twice (Crow: 56 marks →
# 28 bollards). When a cluster binds to a bollard object, near-coincident
# instance pairs are collapsed into one count. Conservative: it merges ONLY
# instances whose centres are within a small radius (a fraction of the marker
# size — never the inter-bollard spacing), and it is applied ONLY to
# bollard-type bindings so column grids and other symbols are never affected.

_BOLLARD_NAME_RE = re.compile(r"bollard", re.IGNORECASE)


def _is_bollard_name(name) -> bool:
    """True when a bound symbol name is a bollard (dedup applies only to these)."""
    return bool(name) and bool(_BOLLARD_NAME_RE.search(str(name)))


# Object types that are inherently a 2-D array on the plan (a column grid, a
# bollard ring). A collinear cluster labeled as one of these is a coincidence
# (dimension ticks), so its count is flagged for review rather than trusted.
_GRID_OBJECT_NAME_RE = re.compile(r"column|bollard", re.IGNORECASE)


def _is_grid_object_name(name) -> bool:
    """True when a name denotes an inherently 2-D object array (columns/bollards)."""
    return bool(name) and bool(_GRID_OBJECT_NAME_RE.search(str(name)))


# Only collapse when the co-location is SYSTEMATIC (each physical object drawn
# as ~2+ coincident marks). A ring/grid with a few incidentally-shared corners
# has a multiplicity near 1.0 and is left untouched — the dedup fires only on
# the concentric pipe+cap doubling signature.
_DEDUP_MIN_MULTIPLICITY = 1.5


def _dedup_colocated_count(group, raw_count: int) -> int:
    """Collapse SYSTEMATICALLY co-located marks (concentric pipe+cap) to one count.

    Two instances whose centres lie within a small radius (0.75× the median
    marker size, floored at 0.5 pt) map to the same location. The collapse is
    applied ONLY when the resulting multiplicity (raw ÷ locations) is ≥
    :data:`_DEDUP_MIN_MULTIPLICITY` — i.e. each object really was drawn as ~2+
    coincident marks (Crow: 56 marks → 28 bollards). Incidental corner overlaps
    (multiplicity ≈ 1) leave the count unchanged.
    """
    centroids = _instance_centroids(group)
    if len(centroids) < 2:
        return raw_count
    widths, heights = _instance_dims(group)
    sizes = [max(w, h) for w, h in zip(widths, heights)]
    med = _median(sizes) if sizes else 0.0
    radius = max(med * 0.75, 0.5) if med > 0 else 0.5
    r2 = radius * radius
    kept: List[Tuple[float, float]] = []
    for cx, cy in centroids:
        if any((cx - kx) ** 2 + (cy - ky) ** 2 <= r2 for kx, ky in kept):
            continue
        kept.append((cx, cy))
    deduped = len(kept)
    if deduped <= 0:
        return raw_count
    n = len(centroids)
    if n / float(deduped) < _DEDUP_MIN_MULTIPLICITY:
        return raw_count  # not a systematic duplication — leave the count as-is
    return max(1, min(deduped, raw_count))


# ── Noise-cluster filter (gridlines / dimensions / drafting tokens) ──────────
#
# A symbol cluster whose contained text is purely gridline bubbles (bay labels
# "1 / 2 / 3"), dimension strings ("48' - 4\"", "0\" - 60'"), or drafting / sheet
# tokens (TYP, SS, DW, SCALE, sheet ids like A-101) is a drafting annotation,
# NOT a countable object — it must never become an EA take-off line item. The
# filter is keyed on the DESCRIPTION content, not the count, so real object
# clusters (columns / bollards, which are named before the text fallback) are
# never dropped.

_NOISE_STOP_TOKENS = frozenset(
    {
        "SS", "DW", "TYP", "SIM", "NTS", "SCALE", "EQ", "OC", "UNO", "AFF",
        "DIA", "DN", "UP", "REF", "CL", "FT", "IN",
    }
)
# A feet-inch dimension string: "48'-4\"", "0\" - 60'", "350'", "1136'-0\"".
_DIMENSION_TOKEN_RE = re.compile(r"^\d{1,4}'?\s*-?\s*\d{0,2}\"?$")
# A sheet reference id: "A-101", "S1", "A101".
_SHEET_ID_RE = re.compile(r"^[A-Z]{1,3}-?\d{1,4}[A-Z]?$")
# A single gridline bubble label: "1", "12", "H", "G".
_GRID_LABEL_RE = re.compile(r"^[A-Z0-9]{1,3}$")


def _is_noise_token(tok: str) -> bool:
    """True when a single text token is drafting noise (never a real object)."""
    t = (tok or "").strip()
    if not t:
        return True
    if not any(ch.isalnum() for ch in t):
        return True  # pure punctuation ("-", "/")
    up = t.upper().strip(".:")
    if up in _NOISE_STOP_TOKENS:
        return True
    if t.replace(".", "").replace(",", "").isdigit():
        return True  # pure number (gridline bubble)
    if _DIMENSION_TOKEN_RE.match(t):
        return True  # feet-inch dimension string
    if _SHEET_ID_RE.match(up):
        return True  # sheet reference id
    if _GRID_LABEL_RE.match(up):
        return True  # single gridline bubble label
    return False


def _is_noise_cluster(contained_texts) -> bool:
    """True when EVERY text token in a cluster is drafting noise.

    A cluster with no text is NOT noise (it may be a real unlabeled object —
    kept flagged for review); only clusters whose text is entirely gridline /
    dimension / drafting tokens are dropped.
    """
    tokens: List[str] = []
    for txt in contained_texts or []:
        for piece in re.split(r"[\s/]+", str(txt)):
            if piece.strip():
                tokens.append(piece.strip())
    if not tokens:
        return False
    return all(_is_noise_token(t) for t in tokens)


def _fuse_symbol_groups(
    bundle: dict,
    labels_by_id: Dict[str, dict],
    components: List[dict],
    library_bindings: Optional[Dict[str, Tuple[str, str]]] = None,
) -> None:
    """Symbol groups → EA components; count is ALWAYS the deterministic size.

    ``library_bindings`` maps ``candidate_id -> (object_name, hint)`` for
    clusters the naming library binds by ``binding_hint`` (columns / bollards);
    it fills an unlabeled cluster BEFORE the conservative geometry fallback.
    """
    library_bindings = library_bindings or {}
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
            qty = _dedup_colocated_count(group, count) if _is_bollard_name(label) else count
            # Flag-don't-guess (§10): a columns/bollards label on a COLLINEAR
            # cluster is a coincidence — a dimension-tick strip whose count
            # happens to match the object total, never a real 2-D grid/ring.
            # Keep the count but force review + demote confidence so it is never
            # presented as a trusted quantity.
            collinear_grid_object = _is_grid_object_name(label) and _is_collinear_strip(group)
            review = group_review or collinear_grid_object
            reason = "symbol group has mixed text tags" if group_review else ""
            if collinear_grid_object:
                reason = (
                    "labeled %s but the cluster is a single collinear strip "
                    "(dimension ticks / grid bubbles), not a 2-D array — verify" % label
                )
            components.append(
                {
                    "name": label,
                    "quantity": qty,
                    "unit": "EA",
                    "provenance": "geometry",
                    "confidence": _min_confidence(
                        "low" if collinear_grid_object else group_conf,
                        entry.get("confidence"),
                    ),
                    "candidate_id": cid,
                    "needs_review": review,
                    "review_reason": reason,
                }
            )
            continue

        # Vision gave no usable label. First, the naming library may bind this
        # cluster by binding_hint + geometry (the LARGE grid marker → columns,
        # a perimeter ring → bollards) — an estimator's read driven by the
        # plan's OWN naming, not a hardcoded lexicon. Named, count carried,
        # flagged for verification since no vision label confirmed it.
        lib_bind = library_bindings.get(cid)
        if lib_bind:
            lib_name, lib_hint = lib_bind
            qty = _dedup_colocated_count(group, count) if _is_bollard_name(lib_name) else count
            components.append(
                {
                    "name": lib_name,
                    "quantity": qty,
                    "unit": "EA",
                    "provenance": "geometry",
                    "confidence": "medium",
                    "candidate_id": cid,
                    "name_source": "naming_library",
                    "binding_hint": lib_hint,
                    "needs_review": True,
                    "review_reason": (
                        "named by naming library (%s → %s); vision label "
                        "unavailable — verify" % (lib_hint, lib_name)
                    ),
                }
            )
            continue

        # No library binding. Before flagging, try a conservative deterministic
        # geometry fallback (a large regular grid → Columns): the count is
        # carried as a real EA quantity with a named line so a golden item is
        # never lost to a generic "Component" collapse — but the row is still
        # flagged for verification since a model label was unavailable.
        det_name = deterministic_symbol_name(group)
        if det_name:
            components.append(
                {
                    "name": det_name,
                    "quantity": count,
                    "unit": "EA",
                    "provenance": "geometry",
                    "confidence": "medium",
                    "candidate_id": cid,
                    "name_source": "deterministic_geometry",
                    "needs_review": True,
                    "review_reason": (
                        "named by deterministic geometry (regular grid → %s); "
                        "vision label unavailable — verify" % det_name
                    ),
                }
            )
            continue

        # No deterministic signal either. Before naming the cluster by its
        # contained text, drop it when that text is PURE drafting noise —
        # gridline bubbles ("1 / 2 / 3"), dimension strings ("48' - 4\"") or
        # sheet/drafting tokens (TYP, SS, DW, SCALE, A-101). These are
        # annotations, never countable objects, so they must not become EA line
        # items (Crow: ~60 junk gridline/dimension clusters). Keyed on the text
        # content, not the count — real object clusters are named above.
        texts = _field(group, "contained_texts", []) or []
        if _is_noise_cluster(texts):
            logger.debug(
                "fuse_sheet: dropped noise cluster %s (texts=%r)", cid, texts
            )
            continue

        # A genuine unknown cluster → the deterministic count is STILL emitted
        # (flag-don't-guess, never dropped), named by contained text or the
        # candidate ID so distinct unknown groups stay distinguishable.
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


# ── Naming-library-driven wall-class → wall-object mapping ───────────────────
#
# Wall thickness classes (TC1..TCn, each with LF) are named by mapping them to
# the naming library's wall objects by THICKNESS + binding_hint: a printed
# thickness match is authoritative (CMU "8\"" → the ~8" class); otherwise the
# dominant (most-LF, perimeter) unmatched class is the exterior tilt-up and a
# thinner tilt class is the interior tilt-up. Ambiguous / unmatched classes are
# left to the existing needs_review path — never a silent wrong bind.

_WALL_BINDING_HINTS = frozenset(
    {"exterior_wall", "interior_wall", "masonry_wall"}
)
_WALL_THICKNESS_TOL_IN = 1.5

# A tilt-up / precast / site-cast-concrete-panel exterior wall: its area is the
# building PERIMETER × clear height (the panels wrap the footprint), never a
# thickness-class linework length. Matched on the object's own printed naming.
_TILTUP_NAME_RE = re.compile(
    r"tilt.?up|tilt\s*panel|precast|s\.?c\.?c\.?p|site\s*cast|concrete\s*panel",
    re.IGNORECASE,
)
# A CMU / masonry wall — a SMALL interior wall class (low LF, thin), never the
# dominant perimeter class.
_MASONRY_NAME_RE = re.compile(
    r"\bcmu\b|masonry|block\s*wall|concrete\s*masonry", re.IGNORECASE
)


def _is_tiltup_name(name) -> bool:
    """True when the wall object name is a tilt-up / precast / S.C.C.P. panel."""
    return bool(name) and bool(_TILTUP_NAME_RE.search(str(name)))


def _is_masonry_object(obj: dict) -> bool:
    """True when a library wall object is CMU / masonry (by hint or its name)."""
    if not isinstance(obj, dict):
        return False
    hint = str(obj.get("binding_hint") or "").strip().lower()
    if hint == "masonry_wall":
        return True
    name = str(obj.get("name") or obj.get("canonical_name") or "")
    return bool(_MASONRY_NAME_RE.search(name))

# A thickness token in inches: "8", "8\"", "7 5/8", "8 in".
_THICKNESS_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)(?:\s+(\d+)\s*/\s*(\d+))?")


def _parse_thickness_in(value) -> Optional[float]:
    """Parse a printed thickness token (string/number) to inches, else None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    m = _THICKNESS_TOKEN_RE.search(str(value))
    if not m:
        return None
    whole = float(m.group(1))
    if m.group(2) and m.group(3):
        try:
            whole += float(m.group(2)) / float(m.group(3))
        except (ValueError, ZeroDivisionError):
            pass
    return whole if whole > 0 else None


def _wall_thickness_in_by_class(bundle: dict) -> Dict[str, float]:
    """LF-weighted mean thickness (inches) per wall thickness class, from geometry."""
    fpp = float(bundle.get("fpp") or 0.0)
    if fpp <= 0:
        return {}
    acc: Dict[str, List[float]] = {}
    for w in bundle.get("walls") or []:
        cls = _field(w, "thickness_class", "") or ""
        if not cls:
            continue
        tpt = float(_field(w, "thickness_pt", 0.0) or 0.0)
        ln = float(_field(w, "length_pt", 0.0) or 0.0)
        if ln <= 0:
            continue
        a = acc.setdefault(cls, [0.0, 0.0])
        a[0] += tpt * ln
        a[1] += ln
    out: Dict[str, float] = {}
    for cls, (sw, sl) in acc.items():
        if sl > 0:
            out[cls] = round(sw / sl * fpp * 12.0, 2)
    return out


def _wall_objects_from_vocabulary(vocabulary) -> List[dict]:
    """Wall-ish library objects: wall_area basis OR a wall binding_hint."""
    objs: List[dict] = []
    if isinstance(vocabulary, list):
        for o in vocabulary:
            if not isinstance(o, dict):
                continue
            hint = str(o.get("binding_hint") or "").strip().lower()
            basis = o.get("basis") or o.get("measure")
            if basis == _WALL_AREA_BASIS or hint in _WALL_BINDING_HINTS:
                objs.append(o)
    return objs


def map_wall_classes_from_library(
    lf_by_class: Dict[str, float],
    thickness_by_class: Dict[str, float],
    wall_objects: List[dict],
) -> Dict[str, Tuple[str, Optional[str], bool, Optional[float]]]:
    """Map wall thickness classes to naming-library wall objects.

    Returns ``{class: (object_name, basis, confident, matched_thickness_in)}``.
    ``confident`` is True only for a printed-thickness match (authoritative);
    hint-based binds are ``False`` so fusion flags them needs_review. A class
    that no object claims is absent from the map (it stays on the existing
    unlabeled needs_review path).

    ``matched_thickness_in`` is the printed thickness (inches) parsed off the
    library object that produced a confident bind, and ``None`` for a hint
    bind. It exists so the precedence audit record (24-02) can publish the
    EVIDENCE that decided a disagreement rather than making a reviewer
    re-derive it. Consumers that only need the first three fields index the
    tuple rather than unpacking it.
    """
    result: Dict[str, Tuple[str, Optional[str], bool, Optional[float]]] = {}
    if not lf_by_class or not wall_objects:
        return result
    classes = list(lf_by_class.keys())
    used_classes: set = set()
    used_objs: set = set()

    # The dominant (most-LF) class is the exterior perimeter wall — a CMU /
    # masonry object must NEVER bind to it (Crow: the small interior pump-room
    # "8\" CMU WALL" is ~61 LF, the perimeter tilt-up class is thousands of LF).
    dominant_class = (
        max(lf_by_class, key=lambda c: lf_by_class.get(c, 0.0)) if lf_by_class else None
    )

    # Pass 1 — printed-thickness match (authoritative).
    for oi, obj in enumerate(wall_objects):
        th = _parse_thickness_in(obj.get("thickness_in"))
        if th is None:
            continue
        exclude_dominant = _is_masonry_object(obj)
        best = None
        for cls in classes:
            if cls in used_classes:
                continue
            if exclude_dominant and cls == dominant_class:
                continue  # never bind CMU to the dominant perimeter class
            cth = thickness_by_class.get(cls)
            if cth is None:
                continue
            d = abs(cth - th)
            if d <= _WALL_THICKNESS_TOL_IN and (best is None or d < best[0]):
                best = (d, cls)
        if best is not None:
            obj_name = str(obj.get("name") or obj.get("canonical_name") or "").strip()
            if obj_name:
                result[best[1]] = (
                    obj_name,
                    obj.get("basis") or obj.get("measure"),
                    True,
                    th,
                )
                used_classes.add(best[1])
                used_objs.add(oi)

    # Pass 2 — hint-based (dominant/perimeter = exterior; thinner = interior).
    remaining = [c for c in classes if c not in used_classes]
    remaining.sort(key=lambda c: lf_by_class.get(c, 0.0), reverse=True)

    def _obj_indices(pred):
        return [i for i, o in enumerate(wall_objects)
                if i not in used_objs and pred(o)]

    def _hint(o) -> str:
        return str(o.get("binding_hint") or "").strip().lower()

    def _variant(o) -> str:
        return str(o.get("variant") or "").strip().lower()

    ext = _obj_indices(lambda o: _hint(o) == "exterior_wall" or _variant(o) == "exterior")
    inter = _obj_indices(lambda o: _hint(o) == "interior_wall" or _variant(o) == "interior")
    mas = _obj_indices(lambda o: _hint(o) == "masonry_wall")

    def _assign(obj_idx: int, cls: str) -> None:
        obj = wall_objects[obj_idx]
        name = str(obj.get("name") or obj.get("canonical_name") or "").strip()
        if not name or cls in result:
            return
        # A hint bind carries no printed thickness — the 4th slot is None, and
        # that None is what keeps a hint bind out of the authoritative branch.
        result[cls] = (name, obj.get("basis") or obj.get("measure"), False, None)
        used_classes.add(cls)
        used_objs.add(obj_idx)

    # Masonry by hint → the SMALLEST-LF non-dominant class (a CMU wall is a
    # small interior wall, never the dominant perimeter class). Keying on LF
    # (not just thickness) is what stops the giant perimeter class binding to
    # CMU when several classes share a thickness.
    if mas and remaining:
        thin = sorted(
            (
                c for c in remaining
                if c not in used_classes and c != dominant_class
            ),
            key=lambda c: lf_by_class.get(c, 0.0),
        )
        if thin:
            _assign(mas[0], thin[0])
    # Exterior → the dominant (most-LF) remaining class.
    for cls in remaining:
        if cls in used_classes:
            continue
        if ext:
            _assign(ext.pop(0), cls)
            break
    # Interior → the next remaining class.
    for cls in remaining:
        if cls in used_classes:
            continue
        if inter:
            _assign(inter.pop(0), cls)
            break

    return result


def _fuse_wall_classes(
    bundle: dict,
    labels_by_id: Dict[str, dict],
    components: List[dict],
    vocab_map: Optional[Dict[str, dict]] = None,
    wall_height_ft: Optional[float] = None,
    wall_height_source: Optional[str] = None,
    library_wall_map: Optional[
        Dict[str, Tuple[str, Optional[str], bool, Optional[float]]]
    ] = None,
) -> None:
    """Wall thickness classes → LF, or SF when the name is a wall_area object.

    LF always comes from geometry. When a wall class's resolved name maps (via
    the project vocabulary, case/alias-insensitive) to a ``wall_area`` object
    AND a positive wall height is available, the component is emitted as
    area = ``round(LF × height, 1)`` SF — the manifest-era wall-area binding,
    now driven by the autonomous vocabulary + resolved height. The height and
    its source are recorded in the formula; a ``default``-sourced height flags
    the item for review. Any other name (or none) keeps LF exactly as before.

    **Naming precedence (24-02, V4-DET-02) — deterministic evidence leads.**

    ``map_wall_classes_from_library`` is a complete zero-API classifier:
    printed-thickness match within ``_WALL_THICKNESS_TOL_IN``, plus the
    location guard that forbids a masonry object from binding the dominant-LF
    perimeter class. It used to sit in an ``elif`` BEHIND the vision label, so
    a stochastic reading could rename a class the drawing's own printed
    thickness had already identified — the same geometry publishing as CMU on
    one run and tilt-up on the next. The order is now:

    1. a ``confident=True`` printed-thickness bind names the class outright;
    2. a vision label may CORROBORATE it (raising the emitted confidence and
       clearing the "named by naming library" review reason) or DISSENT — a
       dissent never changes the name and is audited, never discarded;
    3. with no confident bind, a usable vision label names the class exactly as
       before (a hint bind is not evidence strong enough to override a reading,
       but the disagreement flags the row);
    4. a hint bind names the class when vision is silent — still ``confident``
       ``False``, still flagged;
    5. neither → the unlabeled ``needs_review`` branch, unchanged.
    """
    vocab_map = vocab_map or {}
    library_wall_map = library_wall_map or {}
    lf_by_class = bundle.get("wall_lf_by_class") or {}

    # Measured building perimeter (for tilt-up / precast panel area = perimeter ×
    # height). None when no footprint / perimeter was measured — a tilt-up wall
    # then falls back to its class LF and is flagged (never a silent guess).
    footprint = bundle.get("footprint")
    perimeter_lf: Optional[float] = None
    if footprint is not None:
        try:
            p = _field(footprint, "perimeter_lf", None)
            perimeter_lf = float(p) if p is not None else None
        except (TypeError, ValueError):
            perimeter_lf = None

    for cls in sorted(lf_by_class):
        lf = lf_by_class[cls]
        cid = _wall_candidate_id(cls)
        entry = labels_by_id.get(cid)
        label = (entry or {}).get("label")

        # Resolve the wall object name + basis for this class. DETERMINISTIC
        # EVIDENCE IS PRIMARY (see the docstring): a printed-thickness match
        # outranks a vision label unconditionally, a vision label names the
        # class only when no confident bind exists, and a hint-only bind is
        # always flagged. An unmapped, unlabeled class stays on the unlabeled
        # needs_review path below.
        name = None
        basis = None
        vision_conf = None
        from_vision = False
        confident = False
        name_source = None
        dissent_note = ""

        bind = library_wall_map.get(cls)
        bind_name = bind[0] if bind else None
        bind_basis = bind[1] if bind else None
        bind_confident = bool(bind[2]) if bind else False
        has_label = bool(entry and label and label != _UNKNOWN_LABEL)

        if bind_confident:
            # 1. Printed thickness wins outright — the drawing's own number.
            name, basis, confident = bind_name, bind_basis, True
            name_source = _NAME_SOURCE_WALL_THICKNESS
            if has_label:
                if _squash_wall_name(label) == _squash_wall_name(name):
                    # 2a. Vision corroborates: a second, independent reading of
                    #     the same answer. Raise confidence, clear the
                    #     "named by naming library" review reason.
                    from_vision = True
                    vision_conf = entry.get("confidence")
                else:
                    # 2b. Vision dissents. The name does NOT move — but two
                    #     naming authorities disagreed about a material
                    #     classification, and an estimator is owed that fact in
                    #     the row as well as in the audit trail.
                    dissent_note = (
                        "vision read this class as %r; the printed-thickness "
                        "match named it %r and outranks the reading (both "
                        "answers are in the fusion audit trail) — verify"
                        % (label, name)
                    )
        elif has_label:
            # 3. No confident bind — the vision label names the class, exactly
            #    as before. A hint bind is not evidence strong enough to
            #    override a reading, but a disagreeing hint bind flags the row.
            name = label
            basis = (vocab_map.get(str(label).strip().lower()) or {}).get("basis")
            vision_conf = entry.get("confidence")
            from_vision = True
            confident = True
            name_source = _NAME_SOURCE_VISION
            if bind_name and _squash_wall_name(bind_name) != _squash_wall_name(label):
                dissent_note = (
                    "the naming library's hint bind said %r and vision said "
                    "%r; the reading was kept because a hint bind is not a "
                    "thickness match — verify" % (bind_name, label)
                )
        elif bind is not None:
            # 4. Hint bind, vision silent — unchanged, still flagged below.
            # bind_confident is False here by construction (branch 1 took the
            # confident case), so this is the hint bind and nothing else.
            name, basis, confident = bind_name, bind_basis, False
            name_source = _NAME_SOURCE_LIBRARY
        # 5. Neither → falls through to the unlabeled else-branch below.

        if name is not None:
            if (
                basis == _WALL_AREA_BASIS
                and wall_height_ft is not None
                and float(wall_height_ft) > 0
            ):
                height = float(wall_height_ft)
                source = wall_height_source or "default"
                is_default = source == "default"

                # Tilt-up / precast panels: the exterior wall area is the building
                # PERIMETER × height (the panels wrap the footprint), not the
                # thickness-class linework LF. Bind to the measured perimeter when
                # available; without it, fall back to the class LF and flag.
                lf_value = float(lf)
                lf_basis = "wall class linework"
                tiltup_missing_perimeter = False
                if _is_tiltup_name(name):
                    if perimeter_lf is not None and perimeter_lf > 0:
                        lf_value = perimeter_lf
                        lf_basis = "building perimeter"
                    else:
                        tiltup_missing_perimeter = True

                # Flag when the height is a default OR the wall name came from a
                # non-authoritative (hint-only) library bind OR a tilt-up wall is
                # missing its perimeter — ambiguous binds are always reviewed.
                needs_review = (
                    is_default
                    or (not from_vision and not confident)
                    or tiltup_missing_perimeter
                )
                reasons = []
                if is_default:
                    reasons.append("wall height assumed (%s) — verify on sheet" % source)
                if not from_vision:
                    reasons.append(
                        "wall class named by naming library (%s bind) — verify"
                        % ("thickness" if confident else "hint")
                    )
                if tiltup_missing_perimeter:
                    reasons.append(
                        "tilt-up wall area needs the building perimeter "
                        "(unavailable) — using class LF; verify"
                    )
                if dissent_note:
                    # Two naming authorities disagreed. The name published is
                    # the one that won on evidence, and the row says so.
                    needs_review = True
                    reasons.append(dissent_note)
                components.append(
                    {
                        "name": name,
                        "quantity": round(lf_value * height, 1),
                        "unit": "SF",
                        "provenance": "geometry",
                        "confidence": _min_confidence(
                            "high" if (from_vision and not is_default and confident)
                            else "medium",
                            vision_conf,
                        ),
                        "candidate_id": cid,
                        "name_source": name_source,
                        "formula": "%.1f LF (%s) × %.1f ft height (%s)"
                        % (round(lf_value, 1), lf_basis, height, source),
                        "wall_height_ft": height,
                        "wall_height_source": source,
                        "needs_review": needs_review,
                        "review_reason": "; ".join(reasons),
                    }
                )
                continue
            lf_reasons = []
            if not from_vision and not confident:
                lf_reasons.append(
                    "wall class named by naming library (hint bind) — verify"
                )
            if dissent_note:
                lf_reasons.append(dissent_note)
            components.append(
                {
                    "name": name,
                    "quantity": round(float(lf), 1),
                    "unit": "LF",
                    "provenance": "geometry",
                    "confidence": _min_confidence(
                        "high" if from_vision else "medium", vision_conf
                    ),
                    "candidate_id": cid,
                    "name_source": name_source,
                    "needs_review": bool(lf_reasons),
                    "review_reason": "; ".join(lf_reasons),
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


def _item_not_measured(bundle: dict, info: dict, reason: str = "") -> None:
    """The explicit NOT MEASURED row for a basis no drawing answers.

    Substituting another discipline's area would be a guess (a ceiling is
    taken off the RCP, not off the architectural plan), so the honest outcome
    is an explicit blank — never a bare ``continue``, which leaves the item
    with no row at all and its quantity read as a zero (INV-08 §2 row S9).

    *reason* overrides the default wording — the selector's AMBIGUITY refusal
    (two drawings of one name both validating) is a different failure than
    "no drawing of the right discipline", and the record must say which.
    """
    from bobbytailor.deterministic.room_fill import (  # noqa: PLC0415
        BASIS_PLAN_KIND,
    )
    from bobbytailor.pipeline.coverage import (  # noqa: PLC0415
        ITEM_NOT_MEASURED,
        ItemCoverage,
    )

    want_kind = BASIS_PLAN_KIND.get(info["basis"], "?")
    bundle.setdefault("item_coverage", []).append(
        ItemCoverage(
            name=str(info["name"]),
            unit=str(info["unit"] or "SF"),
            status=ITEM_NOT_MEASURED,
            quantity=None,
            basis=info["basis"],
            source_sheets=[str(bundle.get("sheet_name") or "")],
            reason=reason or (
                "no %s plan drawing was measured on this sheet for "
                "basis %r — measuring it off a different discipline's "
                "drawing would be a guess" % (want_kind, info["basis"])
            ),
            expected_from="vocabulary",
        )
    )


def _unit_count_for(pick, ctx: dict) -> "Tuple[Optional[int], bool, str, dict]":
    """``(count, known, source, meta)`` for the pick's unit type.

    A known count with no stated source predates the census wiring (a caller
    passing a bare room_mix, i.e. the estimator's declaration), so it reports
    ``manifest``. An unknown count is ``assumed``: the prototype stands for
    one unit and the row says so.
    """
    room_mix = ctx.get("room_mix") or {}
    room_mix_meta = ctx.get("room_mix_meta") or {}
    plan_key = _norm_name(pick.plan_name)
    count = room_mix.get(plan_key)
    known = count is not None and int(count) > 0
    meta = room_mix_meta.get(plan_key) or {}
    source = str(meta.get("source") or "").strip() or (
        _UNIT_COUNT_SOURCE_MANIFEST if known else _UNIT_COUNT_SOURCE_ASSUMED
    )
    if not known:
        source = _UNIT_COUNT_SOURCE_ASSUMED
    return (int(count) if known else None), known, source, meta


#: The exact sentence fragment the D-10 acceptance greps for. On the real
#: defective Moxy sheets (ID-412/416/420/422 — a suite's entry + connecting
#: door counted as two units) this is precisely the sentence that would have
#: caught the error.
_MULTIPLIER_REVIEW_MARKER = "verify the count is units rather than doors"


def _multiplier_review_reason(pick, count, known, source, meta) -> str:
    """The multiplier-suspicion sentence, or "" when the count is trustworthy.

    Fires when the count is IN DISPUTE (the in-plan census and the manifest
    disagree — the census value is published, the manifest is a cross-check
    that FLAGS, never edits, per 23-CONTEXT resolution 3) or when a count
    above one comes from the manifest alone and nothing in the drawings
    confirms it. A census-confirmed count — QQ A's 90, KING A's 26 — does NOT
    fire: a number read off the drawing set's own key plans is the drawings
    speaking, not a human guess (SP-10).
    """
    if not known:
        return ""
    disputed = bool(meta.get("disputed"))
    # "Unconfirmed" means the RESOLUTION itself says the count came from the
    # manifest alone (its meta carries an explicit source) — not a legacy
    # caller passing a bare room_mix with no meta at all, which has nothing
    # to cross-check against and is handled by the count-source field alone.
    unconfirmed = (
        str(meta.get("source") or "") == _UNIT_COUNT_SOURCE_MANIFEST
        and count > 1
    )
    if not (disputed or unconfirmed):
        return ""
    if pick.extent_ratio is not None:
        return (
            "ONE %r unit was measured against its drawing's own printed "
            "extent at ratio %.2f and then multiplied by %d (count source: "
            "%s) — %s"
            % (pick.plan_name, pick.extent_ratio, count, source,
               _MULTIPLIER_REVIEW_MARKER)
        )
    return (
        "ONE %r unit was measured and multiplied by %d (count source: %s), "
        "a count the drawings do not confirm — %s"
        % (pick.plan_name, count, source, _MULTIPLIER_REVIEW_MARKER)
    )


def _bind_enclosed_area(
    bundle: dict, components: List[dict], info: dict, fills, ctx: dict
) -> None:
    """The enclosed-region AREA binder — today's behaviour, exactly.

    The number is geometry: an area flood-filled from the drawing at that
    drawing's own printed scale; the room mix supplies only the COUNT. A
    prototype sheet whose unit type is not in the room mix is emitted as the
    single measured unit and flagged — never silently multiplied by a guessed
    count, and never dropped.
    """
    from bobbytailor.deterministic.room_fill import (  # noqa: PLC0415
        select_fill_for_basis,
        total_for_units,
    )

    ambiguity: List[str] = []
    pick = select_fill_for_basis(fills, info["basis"], ambiguity_out=ambiguity)
    if pick is None:
        _item_not_measured(bundle, info, reason=ambiguity[0] if ambiguity else "")
        return
    count, known_count, count_source, meta = _unit_count_for(pick, ctx)
    qty = total_for_units(pick.area_sf, count if known_count else None)

    reasons = []
    if pick.needs_review:
        reasons.append(pick.review_reason)
    if not known_count and pick.plan_name:
        reasons.append(
            "measured ONE %r unit (%.1f SF); how many exist is not stated in "
            "the drawing set — supply the room mix to scale it"
            % (pick.plan_name, pick.area_sf)
        )
    if known_count and meta.get("note"):
        reasons.append(str(meta["note"]))
    multiplier_reason = _multiplier_review_reason(
        pick, count, known_count, count_source, meta
    )
    if multiplier_reason:
        reasons.append(multiplier_reason)
    components.append(
        {
            "name": info["name"],
            "quantity": qty,
            "unit": info["unit"],
            "provenance": "geometry",
            # A count above one is a number the drawing being measured does
            # not itself contain — it must not be reported as high-confidence
            # (SP-10, T-23-52). A single-unit clean row stays high.
            "confidence": "medium"
            if (reasons or (known_count and count > 1)) else "high",
            "candidate_id": pick.candidate_id,
            "name_source": "room_fill",
            "basis": info["basis"],
            # The measured region backing this row — the arbitration key. Two
            # line items claiming the same region must be a DECLARED sharing,
            # never an emergent double count (SP-9).
            "region_ref": "fill:%s" % pick.candidate_id,
            "formula": (
                "%.1f SF (%s, enclosed regions @ %.2f ft/in) × %d units "
                "(unit count source: %s)"
                % (pick.area_sf, pick.viewport_title or pick.plan_kind,
                   pick.scale_fpi or 0.0, int(count), count_source)
                if known_count else
                "%.1f SF (%s, enclosed regions @ %.2f ft/in)"
                % (pick.area_sf, pick.viewport_title or pick.plan_kind,
                   pick.scale_fpi or 0.0)
            ),
            "unit_count": count if known_count else None,
            "unit_count_source": count_source,
            "needs_review": bool(reasons),
            "review_reason": "; ".join(r for r in reasons if r),
        }
    )


#: Height sources the wall binder accepts WITHOUT flagging. Anything else —
#: "plan" (Moxy's 15 ft roof-plan clearance callout), "default" (the 30 ft
#: industrial fallback), or nothing at all — flags the row with the source
#: named, matching how the thickness-class binder treats a default height.
_TRUSTED_HEIGHT_SOURCES = frozenset({"drawing", "learned"})


def _bind_wall_area(
    bundle: dict, components: List[dict], info: dict, fills, ctx: dict
) -> None:
    """The wall-area binder: billable perimeter × drawing height × unit count.

    Flag-don't-guess, three ways:

    * A leaking fill (dominant region over the blind shape threshold) emits a
      ZERO quantity with the shape failure named — NEVER a silent ``continue``,
      because a missing row reads as "not required" while a flagged zero reads
      as "we could not measure this".
    * No trustworthy height → the row ships with ``quantity=None`` carrying the
      measured perimeter in its formula, flagged — never a guessed height.
    * A height whose source is not the drawing's own tag (or a learned value)
      multiplies but FLAGS with the source named: Moxy's project answer is
      15 ft from a roof-plan ``CLEAR REQ'D`` callout at source "plan", a ~67%
      overstatement that would otherwise arrive at confidence high (INV-01 §5).

    The partition convention is board faces, read off the take-off's own
    markup (:data:`room_fill.PARTITION_CONVENTION`, D-08) and named on the row.
    """
    from bobbytailor.deterministic.room_fill import (  # noqa: PLC0415
        select_fill_for_basis,
        total_for_units,
        wall_area_for_unit,
        wall_perimeter_for_unit,
    )

    ambiguity: List[str] = []
    pick = select_fill_for_basis(fills, info["basis"], ambiguity_out=ambiguity)
    if pick is None:
        _item_not_measured(bundle, info, reason=ambiguity[0] if ambiguity else "")
        return
    count, known_count, count_source, meta = _unit_count_for(pick, ctx)

    # The fill's own resolved height first (stamped per drawing by the
    # pipeline), then the sheet-level height fuse_sheet already receives.
    height = pick.wall_height_ft
    source = pick.wall_height_source or ""
    if height is None or float(height) <= 0:
        height = ctx.get("wall_height_ft")
        source = str(ctx.get("wall_height_source") or ("default" if height else ""))
    try:
        height = float(height) if height is not None else None
    except (TypeError, ValueError):
        height = None

    perimeter, perimeter_reason = wall_perimeter_for_unit(pick)
    drawing = pick.viewport_title or pick.plan_kind

    reasons = []
    if pick.needs_review:
        reasons.append(pick.review_reason)
    if perimeter_reason:
        reasons.append(perimeter_reason)
    if not known_count and pick.plan_name:
        reasons.append(
            "measured ONE %r unit; how many exist is not stated in the "
            "drawing set — supply the room mix to scale it" % pick.plan_name
        )
    if known_count and meta.get("note"):
        reasons.append(str(meta["note"]))
    multiplier_reason = _multiplier_review_reason(
        pick, count, known_count, count_source, meta
    )
    if multiplier_reason:
        reasons.append(multiplier_reason)

    base_fields = {
        "name": info["name"],
        "unit": info["unit"],
        "provenance": "geometry",
        "candidate_id": pick.candidate_id,
        "name_source": "room_fill",
        "basis": _WALL_AREA_BASIS,
        "region_ref": "fill:%s" % pick.candidate_id,
        "unit_count": count if known_count else None,
        "unit_count_source": count_source,
        "partition_convention": "board_faces",
    }

    if perimeter <= 0.0:
        # The shape gate refused: a fabricated linear-foot figure is never
        # emitted, and neither is silence.
        component = dict(base_fields)
        component.update(
            {
                "quantity": 0.0,
                "confidence": "low",
                "formula": "0.0 LF billable perimeter (%s @ %.2f ft/in) — %s"
                % (drawing, pick.scale_fpi or 0.0,
                   perimeter_reason or "no billable perimeter"),
                "needs_review": True,
                "review_reason": "; ".join(r for r in reasons if r),
            }
        )
        components.append(component)
        return

    if height is None or height <= 0:
        # Flag-don't-guess: the perimeter is measured and recorded; the
        # quantity is withheld rather than multiplied by an invented height.
        reasons.append(
            "no wall height resolved for this drawing — %.1f LF of billable "
            "perimeter is measured and awaits a height; a guessed height is "
            "never applied" % perimeter
        )
        component = dict(base_fields)
        component.update(
            {
                "quantity": None,
                "confidence": "low",
                "formula": "%.1f LF billable perimeter (%s @ %.2f ft/in) × "
                "UNRESOLVED height" % (perimeter, drawing, pick.scale_fpi or 0.0),
                "needs_review": True,
                "review_reason": "; ".join(r for r in reasons if r),
            }
        )
        components.append(component)
        return

    if source not in _TRUSTED_HEIGHT_SOURCES:
        reasons.append(
            "wall height %.2f ft came from source %r, not from the drawing's "
            "own ceiling tag — verify on sheet before billing"
            % (height, source or "unknown")
        )

    base = wall_area_for_unit(perimeter, height)
    qty = total_for_units(base, count if known_count else None)
    formula = (
        "%.1f LF billable perimeter (%s @ %.2f ft/in) × %.2f ft height (%s)"
        % (perimeter, drawing, pick.scale_fpi or 0.0, height, source or "unknown")
    )
    if known_count:
        formula += " × %d units (unit count source: %s)" % (count, count_source)
    formula += "; partition convention: board faces"

    component = dict(base_fields)
    component.update(
        {
            "quantity": qty,
            # A count above one is not in the drawing being measured — never
            # high-confidence (SP-10, T-23-52).
            "confidence": "medium"
            if (reasons or (known_count and count > 1)) else "high",
            "wall_height_ft": height,
            "wall_height_source": source,
            "formula": formula,
            "needs_review": bool(reasons),
            "review_reason": "; ".join(r for r in reasons if r),
        }
    )
    components.append(component)


#: The two-route disagreement threshold (23-14, D-11). INV-03 measured 0.95%
#: agreement between Crow's silhouette sum and the perimeter x datum-height
#: route — two measurements sharing no code path, no sheet and no scale — so
#: 15% is a loose net that catches structural disagreement without firing on
#: honest noise. When it trips, BOTH routes flag; neither is preferred, and
#: the second route NEVER publishes a quantity: only three of four facades
#: are drawn on one fixture, so a reconciled-looking number would be a
#: fabrication.
_ELEVATION_CROSS_CHECK_TOL = 0.15


def _fuse_elevation_areas(bundle, components, info, ctx) -> None:
    """Facade silhouettes → wall-area line items (23-14).

    Reached through ``BASIS_BINDERS["wall_area"]`` (the SP-9 registry — no
    parallel gate anywhere) and guarded to emit once per sheet however many
    wall-area vocabulary items ask.

    THE HONESTY BOUNDARY, which is the whole point:

    * the GROSS facade area per surviving elevation is emitted at high
      confidence — it is fully deterministic and position-validated;
    * a per-material SPLIT exists only where a keynote tag sits inside a
      closed sub-region whose boundary the fill actually found (a detached
      sign band), and it is FLAGGED by design;
    * the unclaimed remainder goes to the DOMINANT material (most tags) with
      needs-review naming every tag seen. NEVER split by a ratio, NEVER
      divided by the number of distinct materials;
    * no text-anchored material at all → the row is named by the drawing's
      own title and flagged. Attribution requires an anchor; a guess is
      forbidden.

    A demolition or interior elevation emits NO component — it is measured,
    and its exclusion is a coverage note, so the record shows the drawing was
    seen rather than missed.

    The perimeter x datum-height CROSS-CHECK (D-11): compared against the
    reference footprint measured on ANOTHER sheet by different code at a
    different scale. Disagreement beyond
    :data:`_ELEVATION_CROSS_CHECK_TOL` flags BOTH routes; agreement is
    recorded as a note. Either way the second route publishes NO quantity.
    """
    if bundle.get("_elevation_areas_bound"):
        return
    facades = bundle.get("elevation_areas") or []
    if not facades:
        return
    bundle["_elevation_areas_bound"] = True

    def _note(text: str) -> None:
        bundle.setdefault("coverage_notes", []).append(text)

    live = [f for f in facades if not _field(f, "excluded", False)]
    for facade in facades:
        if _field(facade, "excluded", False):
            _note(
                "elevation %r measured %.1f SF but is EXCLUDED from new-work "
                "quantities: %s"
                % (_field(facade, "title", "?"),
                   float(_field(facade, "area_sf", 0.0) or 0.0),
                   _field(facade, "excluded_reason", "") or "excluded")
            )

    # ── The cross-check: flags disagreement, never publishes a quantity ──────
    cross_reason = ""
    footprint = bundle.get("reference_footprint")
    perimeter = None
    if footprint is not None:
        try:
            p = _field(footprint, "perimeter_lf", None)
            perimeter = float(p) if p is not None else None
        except (TypeError, ValueError):
            perimeter = None
    datum_heights = [
        float(_field(f, "datum_height_ft", 0.0) or 0.0)
        for f in live
        if _field(f, "datum_height_ft", None)
    ]
    if perimeter and perimeter > 0 and datum_heights and live:
        datum_h = max(datum_heights)
        silhouette = sum(float(_field(f, "area_sf", 0.0) or 0.0) for f in live)
        expected = perimeter * datum_h
        if expected > 0:
            rel = abs(silhouette - expected) / expected
            if rel > _ELEVATION_CROSS_CHECK_TOL:
                cross_reason = (
                    "the facade silhouette sum %.0f SF DISAGREES with the "
                    "independent perimeter x datum-height route (%.1f LF x "
                    "%.2f ft = %.0f SF) by %.0f%% — BOTH routes are flagged; "
                    "neither is preferred, and the second route publishes no "
                    "quantity" % (silhouette, perimeter, datum_h, expected,
                                  rel * 100.0)
                )
                _note(cross_reason)
            else:
                _note(
                    "elevation cross-check: silhouette sum %.0f SF vs the "
                    "independent perimeter x datum-height route %.1f LF x "
                    "%.2f ft = %.0f SF — agreement within %.1f%%. The second "
                    "route is a cross-check only and publishes no quantity "
                    "(D-11)" % (silhouette, perimeter, datum_h, expected,
                                rel * 100.0)
                )

    # ── Emission: one component per (material, orientation) ──────────────────
    for facade in live:
        title = str(_field(facade, "title", "") or "facade")
        candidate_id = str(_field(facade, "candidate_id", "") or "ELEV")
        area_sf = float(_field(facade, "area_sf", 0.0) or 0.0)
        scale_fpi = float(_field(facade, "scale_fpi", 0.0) or 0.0)
        datum_height = _field(facade, "datum_height_ft", None)
        datum_txt = (
            ", datum band %.2f ft" % float(datum_height)
            if datum_height else ", no datum band"
        )
        base_formula = "%s @ %.2f ft/in%s" % (title, scale_fpi, datum_txt)
        facade_flag = (
            str(_field(facade, "review_reason", "") or "")
            if _field(facade, "needs_review", False) else ""
        )
        materials = list(_field(facade, "materials", None) or [])

        rows = []  # (name, quantity_sf, extra_reasons, region_ref)
        if not materials:
            rows.append((
                title,
                area_sf,
                ["no text-anchored material attribution — no keynote tag "
                 "inside this drawing names a wall material, so the facade "
                 "is named by its own title and flagged; a guessed material "
                 "is never applied"],
                "facade:%s" % candidate_id,
            ))
        else:
            dominant = materials[0]
            others = materials[1:]
            for m in others:
                claimed = m.get("claimed_sf")
                if claimed:
                    rows.append((
                        m["material"],
                        float(claimed),
                        ["per-material split from a closed sub-region whose "
                         "boundary the fill actually found, claimed by keynote "
                         "tag(s) %s — the split is flagged by design; the "
                         "gross facade is the confident figure"
                         % ", ".join(m.get("tags") or [])],
                        "facade:%s:%s" % (candidate_id, m["material"]),
                    ))
            reasons = []
            if others:
                seen = "; ".join(
                    "%s (tag %s x%d)" % (
                        m["material"], ",".join(m.get("tags") or []),
                        int(m.get("count") or 0),
                    )
                    for m in others
                )
                reasons.append(
                    "keynote tags name more than one material on this facade "
                    "— %s — but no tag draws the boundary, so the unclaimed "
                    "remainder goes to the dominant material %r (tag %s x%d); "
                    "never split by ratio and never divided by the material "
                    "count; verify the split"
                    % (seen, dominant["material"],
                       ",".join(dominant.get("tags") or []),
                       int(dominant.get("count") or 0))
                )
            rows.append((
                dominant["material"],
                area_sf,
                reasons,
                "facade:%s" % candidate_id,
            ))

        for name, quantity, extra_reasons, region_ref in rows:
            reasons = list(extra_reasons)
            if facade_flag:
                reasons.append(facade_flag)
            if cross_reason:
                reasons.append(cross_reason)
            components.append(
                {
                    "name": name,
                    "quantity": round(float(quantity), 1),
                    "unit": "SF",
                    "provenance": "geometry",
                    "confidence": "high" if not reasons else "medium",
                    "candidate_id": candidate_id,
                    "name_source": "elevation_fill",
                    "basis": _WALL_AREA_BASIS,
                    "region_ref": region_ref,
                    "orientation": str(_field(facade, "orientation", "") or ""),
                    "formula": "%.1f SF facade silhouette (%s)"
                               % (float(quantity), base_formula),
                    "needs_review": bool(reasons),
                    "review_reason": "; ".join(reasons),
                }
            )


def _bind_wall_area_basis(bundle, components, info, fills, ctx) -> None:
    """THE registered ``wall_area`` binder: room fills AND/OR facades.

    One registry entry answers the basis (SP-9 — no parallel frozenset):
    sheets with plan fills bind perimeter x height through
    :func:`_bind_wall_area` exactly as before; sheets with elevation areas
    bind facade silhouettes through :func:`_fuse_elevation_areas` (guarded to
    run once); Chelsea's mixed sheets do both. With no elevation areas on the
    bundle this is byte-identical to the 23-13 binder.
    """
    if fills:
        _bind_wall_area(bundle, components, info, fills, ctx)
    _fuse_elevation_areas(bundle, components, info, ctx)


# ── The linear binder (23-15, SP-7) ──────────────────────────────────────────

_LINEAR_BASIS = "linear"


def _linear_title_resolves(title: str, obj: dict) -> bool:
    """Does a drawing's own title name this linear object?

    Two deterministic steps, no numeric input and no model input:

    1. the library resolver — the object's name or any alias appears as a
       whole phrase in the title;
    2. THE one static naming map — ``normalize_item_name`` reads general
       construction vocabulary ("STAIR RAIL" → "Hand Rail"), and the title
       resolves when the map lands on the object's canonical form.
    """
    if not title:
        return False
    entry = {
        "name": obj.get("name") or "",
        "aliases": list(obj.get("aliases") or []),
        "unit": obj.get("unit") or "",
    }
    try:
        from bobbytailor.deterministic.component_library import (  # noqa: PLC0415
            resolve_library_name,
        )
        if resolve_library_name(title, [entry]) is not None:
            return True
    except Exception:  # noqa: BLE001 — resolution must never break fusion
        pass
    try:
        from bobbytailor.pipeline.aggregator import (  # noqa: PLC0415
            canonical_library_name,
            normalize_item_name,
        )
        mapped = _norm_name(normalize_item_name(title, "", "")[0])
        targets = {
            _norm_name(entry["name"]),
            _norm_name(canonical_library_name(entry["name"], "")[0]),
        }
        return mapped in targets
    except Exception:  # noqa: BLE001
        return False


def _shx_label_for_family(fam_runs, shx) -> str:
    """The SHX comment-annot label whose rectangle overlaps a family mark.

    AutoCAD's "capture SHX text as comments" export writes the literal
    linetype string into a ``Square`` annotation; when its rect overlaps one
    of the family's mark centres, that string IS the label — exactly and for
    free (INV-04 §5 priority 1). No overlap, no label; a glyph is NEVER read
    as text (template matching was tried and failed).
    """
    if not shx:
        return ""
    centers: List[tuple] = []
    for r in fam_runs:
        stats = _field(r, "mark_stats", None) or {}
        cs = stats.get("mark_centers") or []
        if cs:
            centers.extend(tuple(c) for c in cs)
        else:
            b = _field(r, "bbox_pt", None)
            if b:
                centers.append(((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0))
    for annot in shx:
        rect = annot.get("rect") or ()
        text = (annot.get("text") or "").strip()
        if len(tuple(rect)) != 4 or not text:
            continue
        x0, y0, x1, y1 = rect
        for cx, cy in centers:
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return text.title()
    return ""


def _emit_linear_component(
    bundle,
    components: List[dict],
    name: str,
    unit: str,
    runs,
    instance_counts,
    name_source: str,
    extra_reasons=(),
) -> None:
    """ONE line item from the selected runs of ONE linear object.

    Runs are summed PER VIEWPORT (per drawing) and exactly ONE viewport is
    billed: a main-plan drawing when one exists (as-built, count 1), else
    the typical detail with the largest measured total. A typical run is
    NEVER summed with a main-plan run of the same object, and two drawings
    of one object are never summed with each other — same rail, two
    drawings (INV-06 §2 step 5). Together with the 23-13 arbitration this
    is the whole defence against silent inflation.

    The instance-count contract (D-09, 23-CONTEXT resolution 2): when the
    count is unknown the PER-INSTANCE length ships with ``needs_review``
    and a reason stating what was measured and what is not stated on the
    sheet — the item is never withheld, because a withheld item is a
    silent zero.
    """
    by_vp: Dict[str, list] = {}
    for r in runs:
        by_vp.setdefault(str(_field(r, "viewport_title", "") or ""), []).append(r)
    totals: List[dict] = []
    for title, rs in by_vp.items():
        lf = 0.0
        best = None
        typical = False
        for r in rs:
            fpi = float(_field(r, "scale_fpi", 0.0) or 0.0)
            if fpi <= 0:
                continue
            lf += float(_field(r, "length_pt", 0.0) or 0.0) * (fpi / 72.0)
            typical = typical or bool(_field(r, "is_typical", False))
            if best is None or (
                float(_field(r, "length_pt", 0.0) or 0.0)
                > float(_field(best, "length_pt", 0.0) or 0.0)
            ):
                best = r
        if best is None or lf <= 0:
            continue
        totals.append({"title": title, "lf": lf, "typical": typical, "run": best})
    if not totals:
        return
    totals.sort(key=lambda t: (t["typical"], -t["lf"], t["title"]))
    chosen, others = totals[0], totals[1:]

    per_instance = chosen["lf"]
    reasons = list(extra_reasons)
    count = None
    if instance_counts:
        raw = instance_counts.get(name)
        try:
            count = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            count = None
        if count is not None and count <= 0:
            count = None
    quantity = per_instance * count if count else per_instance
    if count and count > 1:
        # A count above one is a number the drawing being measured does not
        # contain (SP-10) — never high-confidence.
        reasons.append(
            "multiplied by an instance count of %d that this drawing does "
            "not contain — verify the count" % count
        )
    elif not count and chosen["typical"]:
        reasons.append(
            "measured ONE %r run (%.1f LF) on a TYPICAL detail; how many "
            "exist is not stated on this sheet" % (name, per_instance)
        )
    if others:
        reasons.append(
            "the same object is also drawn in %d other drawing(s) (%s); "
            "only %r is billed — two drawings of one object are never summed"
            % (
                len(others),
                ", ".join(sorted((t["title"] or "untitled") for t in others)),
                chosen["title"] or "untitled",
            )
        )
    best = chosen["run"]
    scale_fpi = float(_field(best, "scale_fpi", 0.0) or 0.0)
    component = {
        "name": name,
        "quantity": round(float(quantity), 1),
        "unit": (unit or "LF").upper(),
        "provenance": "geometry",
        "confidence": "high" if not reasons else "medium",
        "candidate_id": str(_field(best, "candidate_id", "") or ""),
        "name_source": name_source,
        "basis": _LINEAR_BASIS,
        "region_ref": "linear:%s"
                      % (str(_field(best, "candidate_id", "") or "")
                         or chosen["title"]),
        "unit_count": count,
        "formula": "%.1f LF (%s, open runs @ %.2f ft/in)"
                   % (per_instance, chosen["title"] or "untitled drawing",
                      scale_fpi),
        "needs_review": bool(reasons),
        "review_reason": "; ".join(reasons),
    }
    if chosen["typical"]:
        component["typical_detail"] = True
    components.append(component)


def _fuse_linear_runs(bundle, components, ctx) -> None:
    """Measured open linear runs → LF line items (23-15, gaps 4 + 6).

    Reached ONLY through ``BASIS_BINDERS["linear"]`` — no parallel frozenset
    — and guarded to run once per sheet however many linear vocabulary items
    ask (the 23-14 dispatcher pattern).

    Naming, most-authoritative first, all deterministic (SP-7):

    * the drawing's OWN TITLE resolves to a linear object — the plan's own
      detail titles do the naming, with no model input and no numeric input;
    * for annotated-linetype families: an SHX comment annotation whose
      rectangle overlaps a mark, then the sheet's own note phrase — bound
      ONLY when exactly one family and exactly one label exist (the
      ambiguity gate, SP-7c). Otherwise the measured quantity ships flagged
      with a reason naming both counts. Names are NEVER round-robined and a
      glyph is never read as text.
    """
    if bundle.get("_linear_runs_bound"):
        return
    runs = bundle.get("linear_runs") or []
    if not runs:
        return
    bundle["_linear_runs_bound"] = True

    def _note(text: str) -> None:
        bundle.setdefault("coverage_notes", []).append(text)

    vocab_map = (ctx or {}).get("vocab_map") or {}
    instance_counts = (ctx or {}).get("room_mix") or {}

    # Linear-basis objects, with their vocabulary aliases folded back in so
    # a title can resolve through an alias.
    objects: Dict[str, dict] = {}
    for alias, info in vocab_map.items():
        if str(info.get("basis") or "").strip().lower() != _LINEAR_BASIS:
            continue
        name = info.get("name")
        if not name:
            continue
        entry = objects.setdefault(
            _norm_name(name),
            {"name": name, "unit": info.get("unit") or "LF", "aliases": []},
        )
        if alias and _norm_name(alias) != _norm_name(name):
            entry["aliases"].append(alias)

    measurable = [
        r for r in runs if float(_field(r, "scale_fpi", 0.0) or 0.0) > 0
    ]
    unmeasured = len(runs) - len(measurable)
    if unmeasured:
        _note(
            "%d linear run(s) have no containing drawing scale and were NOT "
            "measured — flagged, never measured at a borrowed scale"
            % unmeasured
        )
    plain = [r for r in measurable if not _field(r, "mark_signature", None)]
    signed = [r for r in measurable if _field(r, "mark_signature", None)]

    # ── Path 1: the drawing's own title names its runs ───────────────────────
    for entry in objects.values():
        selected = [
            r for r in plain
            if _linear_title_resolves(
                str(_field(r, "viewport_title", "") or ""), entry
            )
        ]
        if not selected:
            continue
        _emit_linear_component(
            bundle, components, entry["name"], entry["unit"], selected,
            instance_counts, "viewport_title",
        )

    # ── Path 2: annotated-linetype families (SHX → sheet note → flag) ────────
    if not signed:
        return
    families: Dict[tuple, list] = {}
    for r in signed:
        families.setdefault(
            tuple(_field(r, "mark_signature", ()) or ()), []
        ).append(r)
    shx = bundle.get("shx_labels") or []
    phrases = bundle.get("sheet_linear_phrases") or []

    unnamed: List[tuple] = []
    for sig, fam_runs in families.items():
        label = _shx_label_for_family(fam_runs, shx)
        if label:
            _emit_linear_component(
                bundle, components, label, "LF", fam_runs,
                instance_counts, "shx_annot",
            )
        else:
            unnamed.append((sig, fam_runs))

    if not unnamed:
        return
    if len(unnamed) == 1 and len(phrases) == 1:
        phrase = phrases[0]
        _emit_linear_component(
            bundle, components, phrase.get("name") or "Linear Run",
            phrase.get("unit") or "LF", unnamed[0][1], instance_counts,
            "sheet_note",
        )
        return
    # THE AMBIGUITY GATE (SP-7c): never round-robin. The measured quantity
    # ships flagged with a reason naming both counts; the row is named by
    # the drawing's own title, never by a guessed label.
    reason = (
        "%d linetype famil%s and %d linear-basis label%s on this sheet — "
        "cannot bind a name deterministically; names are never round-robined"
        % (
            len(unnamed), "y" if len(unnamed) == 1 else "ies",
            len(phrases), "" if len(phrases) == 1 else "s",
        )
    )
    for _sig, fam_runs in unnamed:
        title = next(
            (
                str(_field(r, "viewport_title", "") or "")
                for r in fam_runs
                if _field(r, "viewport_title", "")
            ),
            "",
        )
        _emit_linear_component(
            bundle, components, title or "Unnamed Linear Run", "LF",
            fam_runs, {}, "flagged", extra_reasons=[reason],
        )


def _bind_linear_basis(bundle, components, info, fills, ctx) -> None:
    """THE registered ``linear`` binder (SP-9): delegates to
    :func:`_fuse_linear_runs`, which is guarded to run once per sheet.

    ``info`` and ``fills`` (room fills) are part of the binder contract and
    deliberately unused — the linear pass is per-sheet and its candidates
    live on the bundle, not in the fills list.
    """
    del info, fills
    _fuse_linear_runs(bundle, components, ctx)


# ── The basis-to-binder registry (SP-9, D-03) ────────────────────────────────
#
# ONE registry answers every measure basis the enclosed-region engine can bind.
# Four investigations independently proposed adding a fourth parallel frozenset
# beside the old room-fill basis gate; the registry is what stops that. A new
# capability (23-14 elevation areas, 23-15 linear runs) REGISTERS a binder here
# — it must never add a parallel gate, and one-area-one-item arbitration
# (fuse_sheet) already covers whatever it emits.
BASIS_BINDERS: Dict[str, Callable] = {}


def register_basis_binder(basis: str, binder: Callable) -> None:
    """Register *binder* as THE answerer for *basis*.

    A binder's contract is ``binder(bundle, components, info, fills, ctx)``:
    it appends whatever component(s) answer ``info`` (a wanted vocabulary
    item) and must follow flag-don't-guess — an unanswerable item is an
    explicit flagged row or an item-coverage record, never silence.
    """
    BASIS_BINDERS[str(basis or "").strip().lower()] = binder


register_basis_binder("ceiling_area", _bind_enclosed_area)
register_basis_binder("roof_area", _bind_enclosed_area)
register_basis_binder("floor_area", _bind_enclosed_area)
# wall_area routes through ONE dispatcher answering both wall geometries —
# room-fill perimeter x height AND elevation facade silhouettes (23-14). The
# elevation binder is reached only through this registry entry.
register_basis_binder(_WALL_AREA_BASIS, _bind_wall_area_basis)
# linear (23-15): open runs — rails, annotated linetypes — bind through the
# same registry. Basis `linear` finally has a consumer (INV-06 §1.2 named
# this the exact silent-zero shape: the name existed, the unit existed, the
# measurement step did not exist).
register_basis_binder(_LINEAR_BASIS, _bind_linear_basis)


def _fuse_room_fills(
    bundle: dict,
    components: List[dict],
    vocab_map: Optional[Dict[str, dict]] = None,
    room_mix: Optional[Dict[str, int]] = None,
    room_mix_meta: Optional[Dict[str, dict]] = None,
    wall_height_ft: Optional[float] = None,
    wall_height_source: Optional[str] = None,
) -> None:
    """Measured enclosed-region geometry → line items, one binder per basis.

    The number is geometry: an area flood-filled from the drawing at that
    drawing's own printed scale, or a wall area from that fill's billable
    perimeter × its drawing's own height. ``room_mix`` supplies only the
    COUNT — how many of each unit type the building has; it never supplies a
    quantity.

    That count is no longer necessarily a human input. ``room_mix_meta`` carries
    ``{name: {"source": ..., "note": ...}}`` from
    ``TakeoffPipeline._resolve_room_mix``, where the source is
    ``unit_tag_census`` (counted off the drawing set's own unit key plans),
    ``manifest`` (the estimator declared it and the drawings did not confirm it)
    or ``assumed`` (no count exists, so the prototype stands for one unit). The
    source is written into the formula string and onto the row, because a count
    that silently switches provenance between runs is unauditable
    (threat T-23-32), and any note — a disagreement with the manifest, an
    abbreviation match — flags the row that USES the number.

    Binding is by DISCIPLINE, not size: a ceiling area comes off the Reflected
    Ceiling Plan, a floor or wall area off the Architectural plan. Which binder
    answers which basis is :data:`BASIS_BINDERS` — the SP-9 registry that
    replaced the parallel frozenset gates.
    """

    def _note(text: str) -> None:
        bundle.setdefault("coverage_notes", []).append(text)

    fills = bundle.get("room_fills") or []
    facades = bundle.get("elevation_areas") or []
    if not fills and not facades:
        _note(
            "no measurable plan drawing on this sheet — no enclosed-region area "
            "was produced, which is NOT the same as measuring zero area"
        )
        return
    vocab_map = vocab_map or {}
    ctx = {
        "room_mix": room_mix or {},
        "room_mix_meta": room_mix_meta or {},
        "wall_height_ft": wall_height_ft,
        "wall_height_source": wall_height_source,
        # 23-15: the linear binder reads the full object list from the ctx —
        # additive; every other binder ignores it.
        "vocab_map": vocab_map,
    }

    if fills:
        # Objects the vocabulary/manifest asks for whose basis has a registered
        # binder, deduped by canonical name.
        wanted: Dict[str, dict] = {}
        for info in vocab_map.values():
            basis = str(info.get("basis") or "").strip().lower()
            name = info.get("name")
            if not name or basis not in BASIS_BINDERS:
                continue
            wanted.setdefault(str(name).strip().lower(),
                              {"name": name, "basis": basis,
                               "unit": info.get("unit") or "SF"})
        if not wanted:
            # THE plans-only failure mode (INV-08 §2 row S8): with no manifest
            # the vocabulary frequently carries no `basis`, so every
            # successfully measured area on the sheet is discarded here —
            # silently, and after the work of measuring it was already done.
            _note(
                "%d room fill(s) measured totalling %.1f SF (%s) but no "
                "vocabulary or manifest item carries an area basis, so the "
                "measurements were DISCARDED — nothing was measured as zero; "
                "the areas exist and have no line item to bind to"
                % (
                    len(fills),
                    sum(float(getattr(f, "area_sf", 0.0) or 0.0) for f in fills),
                    ", ".join(
                        sorted(
                            {
                                str(getattr(f, "viewport_title", "") or
                                    getattr(f, "plan_kind", "") or "?")
                                for f in fills
                            }
                        )
                    ),
                )
            )
        else:
            for info in wanted.values():
                BASIS_BINDERS[info["basis"]](bundle, components, info, fills, ctx)

    # Elevation backstop (23-14): a measured facade is never discarded for
    # want of a vocabulary basis — the plans-only silent-zero failure this
    # phase abolishes. Still reached through THE registry: the lookup below
    # is the same ``wall_area`` entry the wanted-loop dispatches to, so there
    # is exactly one path to the elevation binder and no parallel gate.
    if facades and not bundle.get("_elevation_areas_bound"):
        binder = BASIS_BINDERS.get(_WALL_AREA_BASIS)
        if binder is not None:
            binder(
                bundle, components,
                {"name": "", "basis": _WALL_AREA_BASIS, "unit": "SF"},
                [], ctx,
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
                # Every one of these rows is backed by the SAME measured
                # region — the footprint. One-area-one-item arbitration
                # (fuse_sheet) keeps at most one of them unless the sharing is
                # DECLARED: on Crow this very loop bound one footprint value
                # to six line items at once (INV-00 §4).
                "region_ref": "footprint",
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
# The row's own tag/room identifier, so a flagged finish row says WHERE it
# applies — a reviewer who cannot find the room cannot close the flag.
_SCHEDULE_TAG_KEYS = ("TAG", "ROOM", "ROOM NO.", "ROOM NO", "MARK", "NO.")


def _row_lookup(row: dict, keys) -> Optional[str]:
    """Case-insensitive first-match lookup across candidate column names."""
    upper = {str(k).strip().upper(): v for k, v in row.items()}
    for key in keys:
        value = upper.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


#: Schedule kinds whose rows are TYPE DECLARATIONS, not installed quantities.
#:
#: A door-schedule row is one opening: counting it as one each is correct. A
#: FINISH-schedule row is "room 204's walls are WC-1" — it declares WHICH finish
#: applies, and the quantity is an area nobody has measured. Emitting ``1 EA``
#: for it is not a small error: it is a fabricated unit on a fabricated number,
#: and it renders as a completed line item. So a finish row takes the SAME shape
#: as the material-tag row above — zero SF, flagged, with the room tag in the
#: reason — and the two finish paths converge on one contract rather than
#: producing two different flag shapes for the same idea (D-03).
_TYPE_DECLARATION_SCHEDULE_KINDS = frozenset({"finish"})


def _fuse_schedules(bundle: dict, components: List[dict]) -> None:
    """Schedule rows (tables.py) → components with schedule_table provenance.

    Rows are grouped by their name column; an explicit QTY cell is parsed
    verbatim (text-layer ground truth), otherwise each row counts as one
    installed instance (e.g. one door per door-schedule row) — EXCEPT for the
    kinds in :data:`_TYPE_DECLARATION_SCHEDULE_KINDS`, which declare a type
    rather than an installed quantity and are emitted flagged at zero.
    """
    for sched in bundle.get("schedules") or []:
        kind = str(_field(sched, "kind", "schedule") or "schedule")
        table_conf = _field(sched, "confidence", "medium")
        declares_type = _norm_name(kind) in _TYPE_DECLARATION_SCHEDULE_KINDS
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
                grouped[key] = {"name": name, "quantity": qty, "unit": unit,
                                "tags": []}
                order.append(key)
            else:
                slot["quantity"] += qty
            if declares_type:
                tag = _row_lookup(row, _SCHEDULE_TAG_KEYS)
                if tag and tag not in grouped[key]["tags"]:
                    grouped[key]["tags"].append(tag)
        for key in order:
            slot = grouped[key]
            if declares_type:
                tags = slot["tags"]
                components.append(
                    {
                        "name": slot["name"],
                        "quantity": 0,
                        "unit": "SF",
                        "provenance": "schedule_table",
                        "confidence": "low",
                        "schedule_kind": kind,
                        "candidate_id": "FINISH-%s" % slot["name"],
                        "name_source": "schedule_table",
                        "tag_positions_pt": [],
                        "needs_review": True,
                        "review_reason": (
                            "%s is a %s-schedule row: it DECLARES which finish "
                            "applies%s, it does not state how much was "
                            "installed. The area was NOT measured and was NOT "
                            "estimated; measure it in the workspace."
                            % (slot["name"], kind,
                               " to %s" % ", ".join(tags) if tags else "")
                        ),
                    }
                )
                continue
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


# ── Finish/material callouts → named, flagged, ZERO-quantity rows ────────────
#
# Every wall-covering quantity in the Moxy take-off (WC-1..WC-10, 7,432 SF) sits
# on an interior-elevation sheet, and the pipeline emits NOTHING for any of them
# today — the worst of the three possible states, because silence is
# indistinguishable from zero. The area is NOT recoverable: INV-05 §3 seeded a
# flood fill at every WC tag and every fill leaked to the clip edge at four to
# ten times the estimator's own figure, because an elevation's wall face is
# bounded above and below and open laterally — it is not a closed ink region.
#
# So the honest output is a NAMED row with quantity zero, flagged for review and
# carrying the tag positions, which the measure workspace uses to pre-place the
# shapes. A flagged named row is a task a human closes in seconds; an absent row
# is invisible. NO AREA IS SYNTHESIZED, anywhere on this path.

#: Distinct finish codes that may open a review row in one run. Steps 2 and 8 of
#: the INV-05 map add roughly ten WC rows plus the PT/WD/AT/T/ST/RB vocabulary
#: per elevation sheet, and a review queue that becomes noise gets ignored —
#: which returns us to silent zeros by another route (INV-05 risk 5 / T-23-31).
#: Codes already admitted keep emitting on later sheets, because the workspace
#: needs THAT sheet's tag positions to place THAT sheet's shapes; the cap bounds
#: how many distinct codes may ever be admitted.
MAX_MATERIAL_TAG_CODES = 40


class MaterialTagLedger:
    """Which finish codes have opened a review row, across the whole run.

    Grouping is by CODE, not by row: the same code recurs on several sheets and
    each recurrence needs its own tag positions, but the review queue is bounded
    by how many distinct codes may ever be admitted. Threading one ledger
    through a run is what makes the cap a run-level guarantee rather than a
    per-sheet one.
    """

    def __init__(self, cap: int = MAX_MATERIAL_TAG_CODES) -> None:
        self.cap = int(cap)
        self.sheets_by_code: Dict[str, List[str]] = {}
        self.suppressed: Dict[str, int] = {}

    def admit(self, code: str, sheet_name: str) -> bool:
        """True when *code* may emit a row for *sheet_name*."""
        seen = self.sheets_by_code.get(code)
        if seen is None:
            if len(self.sheets_by_code) >= self.cap:
                self.suppressed[code] = self.suppressed.get(code, 0) + 1
                return False
            self.sheets_by_code[code] = [sheet_name]
            return True
        if sheet_name not in seen:
            seen.append(sheet_name)
        return True


def _fuse_material_tags(
    bundle: dict,
    components: List[dict],
    ledger: Optional[MaterialTagLedger] = None,
) -> None:
    """Finish codes the sheet prints → one flagged zero-quantity row per code.

    The row is named from the TEXT LAYER — ``WC-7`` is what the drawing prints,
    not what a model guessed — and its quantity is zero because the extent of a
    finish on an elevation is not a measurable region. ``tag_positions_pt``
    seeds the human measure workspace so the shapes can be pre-placed.

    A false positive here costs one review; it can never cost a wrong number,
    because there is no path from this function to a non-zero quantity
    (threat T-23-30).
    """
    tags = bundle.get("material_tags") or []
    if not tags:
        return
    sheet_name = str(bundle.get("sheet_name") or "")
    ledger = ledger if ledger is not None else MaterialTagLedger()

    # One entry per distinct code, in the order the sheet first prints it, so
    # the emitted set is deterministic.
    grouped: Dict[str, List[object]] = {}
    for tag in tags:
        code = str(_field(tag, "code", "") or "").strip()
        if not code:
            continue
        grouped.setdefault(code, []).append(tag)

    for code, code_tags in grouped.items():
        if not ledger.admit(code, sheet_name):
            bundle.setdefault("coverage_notes", []).append(
                "finish %s is called out %d time(s) on %s and was NOT given a "
                "review row: %d distinct finish codes already have one, which is "
                "the cap. It is unmeasured, not zero."
                % (code, len(code_tags), sheet_name or "this sheet", ledger.cap)
            )
            continue
        positions = []
        for tag in code_tags:
            bbox = _field(tag, "bbox_pt", None)
            if bbox:
                positions.append([float(v) for v in bbox])
        components.append(
            {
                "name": code,
                "quantity": 0,
                "unit": "SF",
                "provenance": "text_layer",
                "confidence": "low",
                "candidate_id": "FINISH-%s" % code,
                "name_source": "material_tag",
                "finish_code": code,
                "tag_count": len(code_tags),
                "tag_positions_pt": positions,
                "needs_review": True,
                "review_reason": (
                    "finish %s is called out %d time(s) on %s, but its extent is "
                    "not a closed region on this drawing — an elevation's wall "
                    "face is open laterally, so every seeded fill leaks. The "
                    "area was NOT measured and was NOT estimated; measure it in "
                    "the workspace, where the %d tag position(s) are pre-placed."
                    % (code, len(code_tags), sheet_name or "this sheet",
                       len(positions))
                ),
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
                # The same measured region as every _fuse_project_area_items
                # row — subject to one-area-one-item arbitration (SP-9).
                "region_ref": "footprint",
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


def _suppress_superseded_wall_items(
    components: List[dict],
    room_fill_walls,
    rejected: List[dict],
) -> List[tuple]:
    """A measured-region wall item SUPERSEDES the same-named thickness estimate.

    ``_fuse_wall_classes`` and the wall-area binder both append to the same
    list, and ``aggregate_takeoff`` SUMS same-named buckets — so without this,
    turning on the room-fill wall binding produces ``thickness-class SF +
    room-fill SF``: a wrong number that looks better (INV-01 risk 1, R5).

    Merging by provenance cannot resolve it: both rows carry
    ``provenance: "geometry"``, so ``merge_with_provenance`` falls through to
    a confidence-then-first-seen rule and drops one SILENTLY. The suppression
    here is explicit and audited: the thickness-class row lands in the
    rejected list with a reason naming the supersession, following the
    module's existing rejection pattern (:func:`_reject_unknown_id`).

    Args:
        room_fill_walls: ``{normalised name: [superseding component, ...]}``.
            The IDENTITY of the superseder matters, not merely its name — a
            supersession is only valid while the thing that superseded it is
            still going to be published (C3a).

    Returns:
        One ``(superseded, superseders, rejection_record)`` triple per
        suppression, so a later stage can undo any whose superseder does not
        survive. See :func:`_reinstate_orphaned_supersessions`.
    """
    supersessions: List[tuple] = []
    if not room_fill_walls:
        return supersessions
    kept: List[dict] = []
    for component in components:
        name_key = _norm_name(component.get("name"))
        cid = str(component.get("candidate_id") or "")
        from_room_fill = component.get("name_source") == "room_fill"
        if (
            name_key in room_fill_walls
            and not from_room_fill
            and cid.startswith("WALL-")
        ):
            record = {
                "candidate_id": cid,
                "source": "wall_classes",
                "answer": component.get("name"),
                "reason": "superseded_by_room_fill",
                "quantity": component.get("quantity"),
                "unit": component.get("unit"),
                "detail": "the same-named wall item is measured from an "
                          "actual enclosed region on this sheet; the "
                          "thickness-class estimate is superseded, not "
                          "summed with it",
            }
            rejected.append(record)
            supersessions.append(
                (component, list(room_fill_walls[name_key]), record)
            )
            continue
        kept.append(component)
    components[:] = kept
    return supersessions


def _reinstate_orphaned_supersessions(
    components: List[dict],
    supersessions: List[tuple],
    rejected: List[dict],
) -> None:
    """A supersession whose SUPERSEDER dies is not a supersession (C3a).

    Crow shipped the two-stage cascade this exists to break:

      1. ``WALL-TC1 "Tilt Up Wall" 106,992 SF`` (1.3% from golden) was
         suppressed as ``superseded_by_room_fill`` — correctly, at the time,
         because ``FILL-2`` was about to publish the same object from an
         actual enclosed region.
      2. ``FILL-2 "Tilt Up Wall" 31,104 SF`` was then itself rejected by
         ``one_area_one_item``, its region having been anchored by
         "Concrete Pad".

    Both died. Nothing named "Tilt Up Wall" was left to publish, so a symbol
    COUNT of five tilt-up panels inherited the name and shipped as
    ``5.0 SF``, ``confidence: high``, ``needs_review: false`` — a confident
    wrong number, with the right one sitting in the audit trail.

    Step 1 was conditional on step 2's row surviving, and that condition was
    never re-checked. It is re-checked here.

    Two guards keep the reinstatement from creating the double-count the
    supersession existed to prevent:

    * the superseder must actually be gone (identity, not name);
    * NOTHING else of that name may survive — if another row publishes the
      object, the original stays suppressed, because reinstating it would sum
      two readings of one thing.

    A reinstated row is FLAGGED. It is being restored after two independent
    arbitration decisions fired on it, and its route disagreed with the
    superseder's; an estimator is owed both facts, not just the number.
    """
    if not supersessions:
        return
    surviving_ids = {id(c) for c in components}
    surviving_names = {_norm_name(c.get("name")) for c in components}

    for original, superseders, record in supersessions:
        if any(id(s) in surviving_ids for s in superseders):
            continue  # the supersession stands — its superseder publishes
        name_key = _norm_name(original.get("name"))
        if name_key in surviving_names:
            # Something else publishes this object. Reinstating would SUM two
            # readings of one thing — the very failure the supersession
            # prevents. Leave it rejected.
            continue

        for i, entry in enumerate(rejected):
            if entry is record:
                del rejected[i]
                break

        others = ", ".join(
            "%s %s" % (s.get("quantity"), s.get("unit"))
            for s in superseders
            if s.get("quantity") is not None
        )
        note = (
            "reinstated: this reading was suppressed in favour of a "
            "region-measured %r, and that row was then itself rejected — a "
            "supersession whose superseder dies is not a supersession, so the "
            "measurement stands rather than leaving the object with no number "
            "at all%s. Verify which route is right before bidding"
            % (original.get("name"), (" (the superseding route read %s)" % others)
               if others else "")
        )
        original["reinstated_from"] = "superseded_by_room_fill"
        original["needs_review"] = True
        prior = str(original.get("review_reason") or "").strip()
        original["review_reason"] = "; ".join(p for p in (prior, note) if p)
        components.append(original)
        surviving_ids.add(id(original))
        surviving_names.add(name_key)
        logger.info(
            "fuse_sheet: reinstated %r (%s %s) — its superseder was itself "
            "rejected", original.get("name"), original.get("quantity"),
            original.get("unit"),
        )


def _arbitrate_one_area_one_item(
    components: List[dict], rejected: List[dict]
) -> None:
    """ONE measured region backs AT MOST ONE line item — unless DECLARED.

    Two live defects, one rule (SP-9 / INV-00 §4):

    * On Crow, one measured footprint value was bound to SIX line items at
      once (Building Footprint / Canopy / Concrete Pad / Exposed Structure /
      Sealed Concrete / Vapor Barrier, all 397,600 SF). An estimator bidding
      from that report prices the floor six times.
    * A quantity measured on a TYPICAL DETAIL must never be summed with the
      same quantity measured on the main plan (the 23-12 ``is_typical`` flag,
      inherited here so plan 23-15's binder gets it for free).

    Components carrying the same ``region_ref`` (and unit) are one measured
    region. The row with the strongest NAMING AUTHORITY anchors it
    (:func:`_share_rank` — never emission order, which let vocabulary
    iteration silently decide what an estimator saw); every suppressed row
    lands in the rejected list with a reason naming the survivor.

    The exception, and the whole point of the rule: a region backs at most one
    line item PER BUILDING LAYER. A shell warehouse's footprint genuinely
    carries the slab, the sealed-concrete finish troweled onto it and the
    exposed roof structure above — three distinct layers occupying one plan
    area, which is not the same thing as three copies of one quantity. Naming
    a layer (:func:`_building_layer`) IS the declaration; a producer may also
    say so directly with ``shared_area="declared"``. An object that names no
    layer inherited the region only because its measure basis is area-shaped
    (Canopy, Vapor Barrier, Building Footprint on Crow) and is suppressed.

    Every suppression is auditable; nothing vanishes silently (T-23-54).
    """
    suppressed = set()

    # ── A typical-detail row never sums with the main-plan row ──────────────
    by_name: Dict[str, List[dict]] = {}
    for component in components:
        by_name.setdefault(_norm_name(component.get("name")), []).append(component)
    for group in by_name.values():
        typical = [c for c in group if c.get("typical_detail")]
        main = [c for c in group if not c.get("typical_detail")]
        if typical and main:
            for component in typical:
                suppressed.add(id(component))
                rejected.append(
                    {
                        "candidate_id": component.get("candidate_id"),
                        "source": "arbitration",
                        "answer": component.get("name"),
                        "reason": "typical_detail_not_summed",
                        "quantity": component.get("quantity"),
                        "unit": component.get("unit"),
                        "detail": "measured on a typical detail; the same "
                                  "object is measured on the main plan and "
                                  "the two must never be summed",
                    }
                )

    # ── At most one line item per measured region ───────────────────────────
    by_region: Dict[tuple, List[dict]] = {}
    for component in components:
        if id(component) in suppressed:
            continue
        region = component.get("region_ref")
        if not region:
            continue
        key = (str(region), str(component.get("unit") or ""))
        by_region.setdefault(key, []).append(component)
    for (region, _unit), group in by_region.items():
        if len(group) < 2:
            continue
        # The anchor is chosen by naming authority, not by emission order.
        ordered = sorted(group, key=_share_rank)
        anchor = ordered[0]
        anchor_layer = _building_layer(anchor.get("name"))
        claimed_layers = {anchor_layer} if anchor_layer else set()
        shared_names = [str(anchor.get("name"))]
        for component in ordered[1:]:
            layer = _building_layer(component.get("name"))
            # Declared sharing: a DISTINCT building layer through the same plan
            # area is a different object, not a duplicate of the anchor. An
            # explicit ``shared_area="declared"`` from a producer says the same
            # thing directly and is honoured as-is.
            if component.get("shared_area") or (layer and layer not in claimed_layers):
                if layer:
                    claimed_layers.add(layer)
                    component["building_layer"] = layer
                component["shared_area"] = "deliberate"
                shared_names.append(str(component.get("name")))
                continue
            suppressed.add(id(component))
            if layer:
                why = (
                    "the %s layer of that region is already taken by %r — one "
                    "measured region backs at most one line item PER LAYER"
                    % (layer, anchor.get("name"))
                )
            else:
                why = (
                    "%r names no distinct building layer, so the sharing is "
                    "not declared — it inherited this region only because its "
                    "measure basis is area-shaped, and an inherited quantity "
                    "is not a measured one"
                    % (component.get("name"),)
                )
            rejected.append(
                {
                    "candidate_id": component.get("candidate_id"),
                    "source": "arbitration",
                    "answer": component.get("name"),
                    "reason": "one_area_one_item",
                    "quantity": component.get("quantity"),
                    "unit": component.get("unit"),
                    "detail": "backed by the same measured region (%s) as %r: %s"
                              % (region, anchor.get("name"), why),
                }
            )
        if anchor_layer:
            anchor["building_layer"] = anchor_layer
        if len(shared_names) > 1:
            for component in group:
                if id(component) not in suppressed:
                    component["shared_area"] = "deliberate"
                    component["shared_area_with"] = [
                        n for n in shared_names if n != str(component.get("name"))
                    ]

    # ── One OBJECT, one quantity per sheet ───────────────────────────────────
    #
    # The rule above arbitrates WITHIN a region. This one arbitrates ACROSS
    # them: the same named object measured on two different regions of one
    # sheet is two ROUTES to one quantity, and summing them prices the object
    # twice. Crow makes it concrete — once its main floor plan is enumerated as
    # a drawing, "Sealed Concrete" is measured BOTH as the 397,600 SF building
    # footprint and as a 1,717 SF enclosed sub-region of that same drawing.
    #
    # Only the case with a principle behind it is decided. A whole-building
    # plane bound to the measured FOOTPRINT outranks a fill-derived measurement
    # of the same object, because the footprint IS that object's extent:
    # _fuse_project_area_items exists precisely because these planes "fell back
    # to ~6 SF room slivers without a footprint binding". Where no footprint row
    # is involved there is no principle to apply, so nothing is suppressed —
    # a guessed precedence would be worse than a flagged duplicate.
    by_object: Dict[tuple, List[dict]] = {}
    for component in components:
        if id(component) in suppressed or not component.get("region_ref"):
            continue
        key = (_norm_name(component.get("name")), str(component.get("unit") or ""))
        by_object.setdefault(key, []).append(component)
    for group in by_object.values():
        if len(group) < 2:
            continue
        anchor = next(
            (c for c in group if str(c.get("region_ref")) == "footprint"), None
        )
        if anchor is None:
            continue
        for component in group:
            if str(component.get("region_ref")) == "footprint":
                continue
            suppressed.add(id(component))
            rejected.append(
                {
                    "candidate_id": component.get("candidate_id"),
                    "source": "arbitration",
                    "answer": component.get("name"),
                    "reason": "one_object_one_quantity",
                    "quantity": component.get("quantity"),
                    "unit": component.get("unit"),
                    "detail": "the same object is measured on this sheet as the "
                              "building footprint (%s %s); this %s reading is a "
                              "sub-region of that same plane, a second ROUTE to "
                              "one quantity and not a second quantity, so it is "
                              "NOT summed"
                              % (anchor.get("quantity"), anchor.get("unit"),
                                 component.get("region_ref")),
                }
            )

    if suppressed:
        components[:] = [c for c in components if id(c) not in suppressed]


def _withhold_unit_class_violations(components: List[dict]) -> None:
    """A number may not publish in a unit of a different measurement class.

    The publication gate for C3b, in the direction fusion owns: the BASIS says
    what the engine measured, the UNIT comes from whatever object the row was
    bound to, and nothing was checking that the two agreed. Crow published
    ``LED Wall Pack 34,214 EA`` — a 31,104 SF wall-area measurement bound to a
    COUNTED fixture, then multiplied by a waste factor. There is no conversion
    between "how much" and "how many", so the number means nothing under that
    unit.

    The quantity is withheld (``None``), never silently converted and never
    quietly deleted: the row survives, flagged, saying what was measured and
    what it was bound to. A blank with a reason is honest; a number in the
    wrong unit is not.

    Fires only where the contradiction is CERTAIN — an unrecognised unit or an
    unmapped basis is left alone (:func:`units.classes_conflict`).
    """
    for component in components:
        if component.get("quantity") is None:
            continue
        basis = component.get("basis")
        unit = component.get("unit")
        if not _unit_conflict(basis, unit):
            continue
        measured = component.get("quantity")
        component["quantity"] = None
        component["unit_class_violation"] = {
            "basis": str(basis or ""),
            "unit": str(unit or ""),
            "withheld_quantity": measured,
        }
        component["needs_review"] = True
        component["confidence"] = "low"
        note = (
            "UNIT-CLASS VIOLATION: %s was measured on a %r basis (%s) and this "
            "row's unit is %r (%s). There is no conversion between those, so "
            "the number is WITHHELD rather than published in a unit it does "
            "not mean — this is a BLANK, not a zero. Either the object's unit "
            "or its measure basis is wrong; fix the binding and re-run"
            % (measured, str(basis or ""), _basis_class(basis) or "unknown",
               str(unit or ""), _unit_class(unit) or "unknown")
        )
        prior = str(component.get("review_reason") or "").strip()
        component["review_reason"] = "; ".join(p for p in (prior, note) if p)
        logger.warning(
            "fuse_sheet: withheld %r — %s %s measured on basis %r cannot "
            "publish as %r", component.get("name"), measured,
            _basis_class(basis), basis, unit,
        )


def fuse_sheet(
    deterministic_bundle: dict,
    vision_labels: dict,
    registry: Optional[Dict[str, dict]] = None,
    vocabulary=None,
    wall_height_ft: Optional[float] = None,
    wall_height_source: Optional[str] = None,
    room_mix: Optional[Dict[str, int]] = None,
    room_mix_meta: Optional[Dict[str, dict]] = None,
    material_tag_ledger: Optional["MaterialTagLedger"] = None,
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
        room_mix: ``{unit type -> how many exist}``, the multiplier applied to a
            measured prototype. Resolved by
            ``TakeoffPipeline._resolve_room_mix`` from the drawing set's own
            unit key plans first and the estimator's manifest second.
        room_mix_meta: ``{unit type -> {"source": ..., "note": ...}}`` — where
            each count came from (``unit_tag_census`` | ``manifest`` |
            ``assumed``) and any disagreement between the two sources. The
            source lands in the formula string and on the row; the note flags
            the row that uses the disputed number. Omitting it leaves the
            binding behaviour unchanged.
        material_tag_ledger: Run-level :class:`MaterialTagLedger` bounding how
            many DISTINCT finish codes may open a review row across the whole
            run (threat T-23-31). None gives each sheet a fresh ledger, so a
            single-sheet caller behaves as if it were the whole run.

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

    # Naming-library-driven binding (binding_hint → geometry). Empty vocabulary
    # → empty maps → identical to prior behaviour (additive-only).
    binding_map = _binding_hint_map(vocabulary)
    library_bindings = _library_symbol_bindings(
        deterministic_bundle.get("symbol_groups") or [], symbol_labels, binding_map
    )
    wall_objects = _wall_objects_from_vocabulary(vocabulary)
    library_wall_map = map_wall_classes_from_library(
        deterministic_bundle.get("wall_lf_by_class") or {},
        _wall_thickness_in_by_class(deterministic_bundle),
        wall_objects,
    )

    _fuse_symbol_groups(
        deterministic_bundle, symbol_labels, components, library_bindings
    )
    _fuse_wall_classes(
        deterministic_bundle,
        wall_labels,
        components,
        vocab_map=vocab_map,
        wall_height_ft=wall_height_ft,
        wall_height_source=wall_height_source,
        library_wall_map=library_wall_map,
    )
    _fuse_project_area_items(deterministic_bundle, vocabulary, components)
    _fuse_room_fills(
        deterministic_bundle, components, vocab_map, room_mix, room_mix_meta,
        wall_height_ft=wall_height_ft, wall_height_source=wall_height_source,
    )
    # Linear-run binding backstop (23-15) — reached ONLY through
    # BASIS_BINDERS["linear"]. The room-fill wanted-loop dispatches the same
    # registry entry when the sheet also has fills; this covers the sheets
    # that don't (Crow's rails live on a detail sheet with no plan fill).
    # The binder's once-guard makes the two paths converge.
    if (
        deterministic_bundle.get("linear_runs")
        and not deterministic_bundle.get("_linear_runs_bound")
    ):
        linear_binder = BASIS_BINDERS.get(_LINEAR_BASIS)
        if linear_binder is not None:
            linear_binder(
                deterministic_bundle, components,
                {"name": "", "basis": _LINEAR_BASIS, "unit": "LF"}, [],
                {"vocab_map": vocab_map, "room_mix": room_mix or {}},
            )
    _fuse_rooms(deterministic_bundle, room_labels, components, rejected)
    _fuse_schedules(deterministic_bundle, components)
    _fuse_material_tags(deterministic_bundle, components, material_tag_ledger)
    _fuse_footprint(deterministic_bundle, components)

    # ── One-area-one-item arbitration (SP-9) — lands WITH the wall binder ────
    # A wall item measured from an actual enclosed region supersedes the
    # same-named thickness-class estimate, and a measured region backs at most
    # one line item unless the sharing is declared. Every suppression is in
    # ``fusion_rejected`` with a reason; ``aggregate_takeoff`` SUMS same-named
    # buckets, so this is the only thing standing between the new binder and
    # a wrong number that looks better (R5, T-23-50).
    room_fill_walls: Dict[str, List[dict]] = {}
    for c in components:
        if c.get("name_source") == "room_fill" and c.get("basis") == _WALL_AREA_BASIS:
            room_fill_walls.setdefault(_norm_name(c.get("name")), []).append(c)
    supersessions = _suppress_superseded_wall_items(
        components, room_fill_walls, rejected
    )
    _arbitrate_one_area_one_item(components, rejected)
    # A supersession is conditional on its superseder surviving arbitration,
    # and until now that condition was never re-checked — the two-stage
    # cascade that left Crow's tilt-up walls to a 5-panel symbol count (C3a).
    _reinstate_orphaned_supersessions(components, supersessions, rejected)
    # LAST: nothing publishes a number in a unit of a different measurement
    # class, whatever route produced it (C3b).
    _withhold_unit_class_violations(components)

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
