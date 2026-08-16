"""
takeoff_pipeline.py — Single multi-pass extraction orchestrator.

Both pdf_analyzer.py and scraper.py import TakeoffPipeline so StackCT jobs
and PDF-upload jobs run identical pass logic.  Any future fix to extraction
automatically applies to both entry points.

Architecture:
  1. classify_sheet_type (from sheet_pass_matrix, or passed in by caller)
  2. plan_passes → PASS_MATRIX lookup (title_sheet → empty → skip entirely)
  3. For each pass: pick model → call analyze_drawing → collect result
  4. merge_passes → deduplicated unified result dict

Phase notes:
  - 20-00: pipeline skeleton + merge stub + routing wired in.
  - 20-03: analyze_drawing gained pass_type + model_override; stub removed;
           merge_passes canonical impl lives in claude_analyzer.
  - 20-06: pdf_analyzer.py and scraper.py swapped to call TakeoffPipeline.
  - 21-13: deterministic-first orchestration (V3-ACC-01/03). Vector plan
           sheets are measured by the deterministic engine (dimensions →
           viewports → scale solve → walls/rooms/symbols/tables); vision is
           the semantic labeler only (fuse_sheet). Raster sheets fall back
           to an ensemble-voted vision estimate (run_ensemble). One
           BudgetGuard per run is threaded through EVERY vision call site.
  - 21-14: targeted-crop verify-retry (V3-ACC-05). QuantityVerifier flags
           and ensemble disagreements get a bounded (<=2 attempts,
           budget-charged) narrow crop question to the dense model via
           vision/verify_retry.py before human review — resolving semantics
           or confirming flags, never suppressing them. Replaces the legacy
           env-flag logging stub with settings.verify_retry_enabled.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional, Sequence

import fitz

from bobbytailor.pipeline.sheet_pass_matrix import (
    classify_sheet_type_from_text,
    classify_sheet_type_verbose,
    plan_passes,
    pick_model_for_pass,
)
from bobbytailor.pipeline.coverage import (
    ERRORED,
    EXCLUDED_OFF_SCALE,
    MEASURED,
    MEASURED_PARTIAL,
    MEASURED_TRUNCATED,
    NOT_APPLICABLE,
    SKIPPED_CLASSIFIER,
    SKIPPED_NO_SCALE,
    CoverageLedger,
    DrawingCoverage,
    SheetCoverage,
)
from bobbytailor.pipeline.accuracy_config import count_tiling_enabled, count_tiling_grid

# Module-level imports make these symbols patchable in tests:
#   unittest.mock.patch("takeoff_pipeline.analyze_drawing", ...)
from bobbytailor.vision.claude_analyzer import (  # noqa: F401 (re-exported for patching)
    _SCHEDULE_LEGEND_USER_HINT,
    _merge_schedule_lists,
    analyze_drawing,
    apply_accuracy_rules,
    merge_passes,
)

# Deterministic measurement engine (21-03/06/07/10) — module-level names so
# tests can patch e.g. `takeoff_pipeline.extract_dimension_samples`.
from bobbytailor.deterministic.dimensions import extract_dimension_samples
from bobbytailor.deterministic.finish_tags import extract_material_tags
from bobbytailor.deterministic.footprint_takeoff import footprint_from_page
from bobbytailor.deterministic.rooms import extract_rooms
from bobbytailor.deterministic.scale_extraction import (
    dominant_scale,
    extract_scales_from_text,
)
from bobbytailor.deterministic.printed_scale import (
    extract_printed_scales,
    identify_main_plan_scale,
    match_scales_to_viewports,
)
from bobbytailor.deterministic.room_fill import (
    MAX_REGION_SF,
    from_page_space,
    to_page_space,
)
from bobbytailor.deterministic.scale_solver import (
    resolve_scale_v2,
    select_main_plan,
    solve_viewport_scale,
)
from bobbytailor.deterministic.grid_lattice import (
    detect_grid_lattices,
    lattice_shadowed_symbol_ids,
)
from bobbytailor.deterministic.symbols import SymbolGroup, cluster_symbols
from bobbytailor.deterministic.tables import extract_schedules
from bobbytailor.deterministic.text_anchor import anchors_for_candidates
from bobbytailor.deterministic.viewports import segment_viewports
from bobbytailor.deterministic.walls import extract_walls, wall_lf_by_class

# Fusion + ensemble (21-11/12): vision labels bind to deterministic candidate
# IDs; ensemble voting owns residual raster numbers; BudgetGuard is the hard
# per-run spend cap (V3-PROD-02).
from bobbytailor.vision.ensemble import (
    BudgetExceeded,
    BudgetGuard,
    ensemble_settings,
    run_ensemble,
    vote,
)
from bobbytailor.vision.fusion import (
    MaterialTagLedger,
    # The room record field carrying its bounding-wall citation (V4-DET-03).
    # Imported rather than re-spelled: fusion's orphan-room branch reads this
    # exact key, and a second copy of the name here is how one name becomes two.
    ROOM_WALL_REFERENCE_FIELD,
    build_registry,
    fuse_sheet,
    merge_with_provenance,
)

# Learned-context retrieval + anti-amplification guardrail (21-16,
# V3-LEARN-02/03/04). Module-level imports so tests can patch
# `takeoff_pipeline.load_learned_context` (patchability convention, 20-00).
from bobbytailor.learning.retrieval import (  # noqa: F401 (re-exported for patching)
    LearnedContext,
    apply_learned_quantity_flags,
    load_learned_context,
)
# AI-manifest persistence (learn-ai-manifest): module-level import so tests can
# patch `takeoff_pipeline.record_ai_manifest` and so the Opus naming manifest
# ACCUMULATES into learning_vocabulary (source='ai') for reuse on future runs.
from bobbytailor.learning.store import record_ai_manifest  # noqa: F401
# 24-05 (V4-DET-02/04, defect F3): the per-project vocabulary SNAPSHOT — a
# repeat run reuses the object list the first run derived instead of paying the
# API to re-invent it. Module-level imports so tests can patch
# `takeoff_pipeline.load_project_vocabulary` / `.save_project_vocabulary`
# (patchability convention, 20-00) — a deferred import inside the method would
# break that seam.
from bobbytailor.learning.store import (  # noqa: F401 (re-exported for patching)
    VOCAB_KIND_NAMING_CONVENTIONS,
    VOCAB_KIND_PROJECT,
    load_project_vocabulary,
    save_project_vocabulary,
)

# 24-03's naming arbiter, imported so a snapshot written by the earlier
# UN-canonicalised path is folded on READ. `_norm_item_key` is private to the
# aggregator and is imported deliberately rather than re-implemented: it IS the
# bucket identity that decides whether two rows are one item, and a second
# copy of that rule here is exactly how two folding rules drift apart (the
# mistake 24-02 and 24-03 both explicitly refused to make).
from bobbytailor.pipeline.aggregator import (
    NAME_AUTHORITY_LIBRARY,
    _norm_item_key,
    resolve_published_name,
)

# Verify-retry arbitration (21-14): module-level import so tests can patch
# `takeoff_pipeline.retry_flagged_items` (patchability convention, 20-00).
from bobbytailor.vision.verify_retry import retry_flagged_items
from bobbytailor.vision.schemas import (
    raster_extraction_schema,
    semantic_labeling_schema,
    symbol_gallery_schema,
)
# Delimiter wrapper for untrusted drawing text (T-24-27). The per-candidate
# anchor table threaded into the symbol hint is drawing-derived text and MUST
# pass through this before it enters a prompt; prompts.py declares the contract
# the model relies on.
from bobbytailor.vision.prompts import wrap_pdf_text
from bobbytailor.vision.object_vocabulary import (
    build_project_vocabulary,
    extract_naming_conventions,
    majority_keep_conventions,
    majority_vote_objects,
    vocabulary_labels,
)

logger = logging.getLogger(__name__)

# NOTE: bobbytailor.vision.overlay imports bobbytailor.pipeline.pdf_analyzer
# (render_clip_crop), which itself imports takeoff_pipeline — a module-level
# import here would be circular. The overlay renderers are therefore wrapped
# in lazy module-level functions (patch `takeoff_pipeline._render_overlay` /
# `takeoff_pipeline._build_crop_gallery` in tests).


def _render_overlay(page, candidates, kind_colors=None, anchors=None):
    """Lazy wrapper for overlay.render_overlay (circular-import avoidance)."""
    from bobbytailor.vision.overlay import render_overlay

    return render_overlay(page, candidates, kind_colors=kind_colors, anchors=anchors)


def _build_crop_gallery(page, symbol_groups, legend_crop_rect=None):
    """Lazy wrapper for overlay.build_crop_gallery (circular-import avoidance)."""
    from bobbytailor.vision.overlay import build_crop_gallery

    return build_crop_gallery(page, symbol_groups, legend_crop_rect=legend_crop_rect)


# ---------------------------------------------------------------------------
# RunSettings (21-13) — one shared configuration for both entry points
# ---------------------------------------------------------------------------

_TRUTHY = ("1", "true", "yes")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


class RunSettings:
    """Shared run configuration for pdf_analyzer and scraper (V3-STRUCT-02).

    A dataclass constructed identically by both entry points (parity
    foundation for 21-15). ``ensemble_n`` / ``budget_usd`` come from the
    single ``ensemble_settings()`` reader (21-11 decision — env
    ``ENSEMBLE_N`` / ``API_BUDGET_PER_RUN_USD``); the boolean toggles are
    env-driven flags.

    ``models`` records the slug each routing variable resolved to. It is here
    because the two saved paid runs recorded the ensemble size, the budget and
    every boolean toggle — and not one model name, which made "which model
    produced this number" unanswerable from the artifact. That is the same
    class of question 24-RESEARCH Open Question 1 was already burned by, and
    the environment is not an artifact: a slug changed in .env between two runs
    leaves no trace in either report.
    """

    deterministic_enabled = True
    ensemble_n = 3
    learning_enabled = True
    budget_usd = 10.0
    verify_retry_enabled = True
    raster_force = False
    models = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "RunSettings":
        n, budget = 3, 10.0
        try:
            settings = ensemble_settings()
            n = int(settings["n"])
            budget = float(settings["budget_usd"])
        except Exception:  # noqa: BLE001 — config stubbed (tests) → defaults
            logger.debug("RunSettings.from_env: config unavailable — defaults used")
        try:
            from bobbytailor import config as _config

            models = _config.active_models()
        except Exception:  # noqa: BLE001 — config stubbed (tests) → no slugs
            logger.debug("RunSettings.from_env: model slugs unavailable")
            models = {}
        return cls(
            deterministic_enabled=_env_flag("DETERMINISTIC_ENABLED", True),
            ensemble_n=n,
            learning_enabled=_env_flag("LEARNING_ENABLED", True),
            budget_usd=budget,
            verify_retry_enabled=_env_flag("VERIFY_RETRY_ENABLED", True),
            raster_force=_env_flag("RASTER_FORCE", False),
            models=models,
        )

    def to_dict(self) -> dict:
        return asdict(self)


# PEP 563 (`from __future__ import annotations`) turns class-body annotations
# into strings; on Python 3.9 a string-annotated dataclass resolves them via
# sys.modules[cls.__module__], which is absent when tests spec-load this
# module standalone (test_takeoff_pipeline / test_pipeline_parity pattern).
# Real type objects sidestep that resolution entirely, so the decorator is
# applied over an explicit annotations dict instead of inline annotations.
RunSettings.__annotations__ = {
    "deterministic_enabled": bool,
    "ensemble_n": int,
    "learning_enabled": bool,
    "budget_usd": float,
    "verify_retry_enabled": bool,
    "raster_force": bool,
    "models": dict,
}
RunSettings = dataclass(RunSettings)


# ---------------------------------------------------------------------------
# Vector/raster sheet mode detection (RESEARCH §2 raster-fallback heuristic)
# ---------------------------------------------------------------------------

# A sheet is raster-only when BOTH signals are below threshold: fewer than
# 200 vector drawing paths AND fewer than 100 text-layer words.
VECTOR_MIN_DRAWING_ITEMS = 200
VECTOR_MIN_WORDS = 100

# Sheet types the deterministic geometry engine measures (walls/rooms/symbols
# apply to plan bodies only — running them on elevations would pair facade
# lines as bogus "walls").
_PLAN_SHEET_TYPES = ("floor_plan", "civil_site", "roof_plan")
# Sheet types eligible for the deterministic-first vector branch. Schedule
# sheets join because find_tables() reads their rows verbatim (text-layer
# ground truth); elevation sheets join (23-14) because a facade is measured
# deterministically as a complement-labelled silhouette — while
# _PLAN_SHEET_TYPES above is DELIBERATELY untouched: that tuple is what gates
# extract_walls / extract_rooms / cluster_symbols / footprint_from_page, so
# leaving it alone is what keeps wall pairing off facades BY CONSTRUCTION
# (21-13's guarantee, pinned by the empty-walls negative test). Other types
# keep the legacy vision passes.
_DETERMINISTIC_SHEET_TYPES = _PLAN_SHEET_TYPES + ("schedule", "elevation")

# Half-width, in points, of the band searched either side of a plan title's
# centre for the printed scale callout that belongs to it. This is NOT a new
# constant: it is the same 260 pt the room-fill clip already uses
# (TakeoffPipeline._FILL_CLIP_SIDE_PT), pulled to module scope so the skip veto,
# the coverage ledger and scripts/coverage_probe.py all bind a title to a scale
# by exactly the same rule. One definition, so the oracle cannot drift from the
# thing it is the oracle for.
_TITLE_SCALE_SIDE_PT = 260.0
# A callout printed slightly ABOVE a title's baseline still belongs to it —
# 6 pt of tolerance for baseline/bbox rounding, matching _measure_room_fills.
_TITLE_SCALE_ABOVE_TOL_PT = -6.0


def _page_space_point(page, x: float, y: float) -> tuple:
    """One point, mapped by the ONE rect transform (``room_fill.to_page_space``).

    "Below" is a statement about the sheet as it is READ, and text coordinates
    are reported in the unrotated mediabox — so an adjacency test written in
    raw y is asking a question about a space nobody looks at. A degenerate
    rectangle is used deliberately rather than a second point-shaped copy of
    the rotation matrix: D-03 allows exactly one implementation of this
    mapping, and a rigid rotation sends the corners of a zero-area rectangle
    to the mapped point.

    On an unrotated page ``to_page_space`` hands back the caller's own object,
    so this returns ``(x, y)`` bit for bit.
    """
    try:
        import fitz  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return float(x), float(y)
    box = to_page_space(page, fitz.Rect(x, y, x, y))
    return float(box.x0), float(box.y0)


def _page_space_box(page, bbox) -> tuple:
    """``(x0, y0, x1, y1)`` of *bbox* in page space. Identity when unrotated."""
    try:
        import fitz  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return tuple(float(v) for v in bbox)
    box = to_page_space(page, fitz.Rect(*bbox))
    return float(box.x0), float(box.y0), float(box.x1), float(box.y1)


def page_measurable_signal(page) -> dict:
    """Count what can actually be MEASURED on *page*. Zero API.

    ``{"plan_titles": n, "printed_scales": n, "viewports": n, "schedules": n}``

    ``plan_titles`` counts only titles that have a printed scale beneath them,
    and ``viewports`` only non-title-block viewports with a solved scale —
    because a drawing with no scale of its own is NOT measurable, and measuring
    it at a borrowed scale is a squared error (flag-don't-guess).

    That distinction is load-bearing, not pedantry. Moxy page 1 is the LIGHTING
    COVER SHEET: its sheet index lists 11 strings that match the plan-title
    pattern ("QQ A - AR PLAN", ...) and it carries zero printed scales. Counting
    those 11 as measurable signal would make the ledger report a silent loss of
    11 drawings on an index page — a false alarm on every drawing set that has
    an index. A loud ledger is not accuracy (INV-08 risk 4).
    """
    from bobbytailor.deterministic.printed_scale import (  # noqa: PLC0415
        extract_printed_scales,
        match_scales_to_viewports,
    )
    from bobbytailor.deterministic.room_fill import plan_titles  # noqa: PLC0415
    from bobbytailor.deterministic.viewports import segment_viewports  # noqa: PLC0415

    scales = extract_printed_scales(page) or []
    scaled_titles = 0
    for _name, _kind, tbox in plan_titles(page) or []:
        # PAGE space, for exactly the reason _measure_room_fills uses it: a
        # callout is "beneath" a title as the SHEET IS READ. This oracle and
        # the engine it is the oracle for must agree page by page, and on
        # Moxy's /Rotate 90 lobby sheets an unrotated-y test answers zero
        # while the engine measures two 350+ SF drawings — a ledger reporting
        # no measurable signal on a page that measures 743 SF is the silent
        # zero this whole phase exists to abolish.
        tx0, _ty0, tx1, ty1 = _page_space_box(page, tbox)
        mid = (tx0 + tx1) / 2.0
        for s in scales:
            cx, cy = _page_space_point(page, *s.center_pt)
            if abs(cx - mid) > _TITLE_SCALE_SIDE_PT:
                continue
            if cy - ty1 < _TITLE_SCALE_ABOVE_TOL_PT:
                continue
            if float(getattr(s, "feet_per_point", 0.0) or 0.0) <= 0:
                continue
            scaled_titles += 1
            break

    scaled_viewports = 0
    try:
        vps = segment_viewports(page) or []
        by_region = match_scales_to_viewports(scales, vps, page=page) or {}
        for vp in vps:
            if vp.kind in _MASK_VIEWPORT_KINDS:
                continue
            own = by_region.get(vp.region_id)
            if float(getattr(own, "feet_per_point", 0.0) or 0.0) > 0:
                scaled_viewports += 1
    except Exception:  # noqa: BLE001 — the title signal alone still stands
        scaled_viewports = 0

    return {
        "plan_titles": scaled_titles,
        "printed_scales": len(scales),
        "viewports": scaled_viewports,
        "schedules": 0,
    }


# Viewport kinds masked out of measurement (matches scale_solver._MASK_KINDS).
_MASK_VIEWPORT_KINDS = ("title_block", "legend", "schedule")

# Relative tolerance when comparing a viewport's own printed scale to the
# resolved page scale. Drawing scales are discrete and far apart (1"=40' vs
# 1 1/2"=1'-0" is 60x), so a loose 5% band separates them without ever
# splitting a shared scale on floating-point noise.
_SCALE_MATCH_TOL = 0.05

# review_reason markers identifying ensemble-disagreement flags (needs_review
# set by a vote) — these join the verify-retry queue alongside the
# out-of-band QuantityVerifier flags (21-14, RESEARCH §3 handoff 3).
_ENSEMBLE_DISAGREEMENT_MARKERS = ("ensemble", "no_majority", "disagree")


def is_vector_sheet(page) -> bool:
    """True when *page* carries enough vector content to measure directly.

    RESEARCH §2 heuristic: a sheet is raster-only (scanned) when it has
    fewer than 200 drawing paths AND fewer than 100 text-layer words.
    Unreadable pages count as raster (the fallback path flags everything —
    flag-don't-guess).
    """
    try:
        n_drawings = len(page.get_drawings())
    except Exception:  # noqa: BLE001 — untrusted PDF must not crash the run
        n_drawings = 0
    try:
        n_words = len(page.get_text("words"))
    except Exception:  # noqa: BLE001
        n_words = 0
    return not (n_drawings < VECTOR_MIN_DRAWING_ITEMS and n_words < VECTOR_MIN_WORDS)


def _append_reason(existing, reason: str) -> str:
    """Append *reason* to a semicolon-joined review_reason string."""
    existing = str(existing or "").strip()
    if not existing:
        return reason
    if reason in existing:
        return existing
    return "%s; %s" % (existing, reason)


def _budget_state(guard) -> dict:
    """Serializable BudgetGuard state for reports.

    ``exhausted`` (does budget remain?) is kept verbatim, and ``truncated``
    (did the cap actually STOP work?) is added beside it — the two differ, and
    Crow's paid run is the proof: it ended ``exhausted: false`` with $0.0012 of
    a $0.60 cap unspent, after refusing a charge and skipping the remaining
    passes on two sheets. ``truncated`` is the field any consumer asking
    "is this run complete?" must read (C2).
    """
    if guard is None:
        return {
            "cap_usd": None, "spent_usd": 0.0, "exhausted": False,
            "refused_charges": 0, "truncated": False,
        }
    refused = int(getattr(guard, "refused_charges", 0) or 0)
    return {
        "cap_usd": round(float(guard.max_usd), 4),
        "spent_usd": round(float(guard.spent_usd), 6),
        "exhausted": bool(guard.exhausted),
        "refused_charges": refused,
        "truncated": bool(getattr(guard, "truncated", guard.exhausted)),
    }


def _result_cost_usd(result) -> float:
    """The ``_cost_usd`` metadata stamp of an analyzer result (0.0 fallback)."""
    if isinstance(result, dict):
        try:
            return float(result.get("_cost_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _sum_usage(results) -> dict:
    """Aggregate the claude_analyzer usage-metadata convention over *results*."""
    tokens_in = tokens_out = 0
    cost = 0.0
    model = ""
    for res in results:
        if not isinstance(res, dict):
            continue
        try:
            tokens_in += int(res.get("_tokens_in") or 0)
            tokens_out += int(res.get("_tokens_out") or 0)
        except (TypeError, ValueError):
            pass
        cost += _result_cost_usd(res)
        if not model and res.get("_model_used"):
            model = str(res.get("_model_used"))
    return {
        "_tokens_in": tokens_in,
        "_tokens_out": tokens_out,
        "_cost_usd": round(cost, 6),
        "_model_used": model,
    }


def _sched_field(obj, name: str, default=None):
    """Read a field from a dataclass-like object or a plain dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ── Categorical majority-vote for residual vision label passes (21-reliability)
# The single-shot symbol-gallery / wall-class passes are stochastic: one run a
# real cluster is "Column", the next it is "unknown", so items flip FOUND/
# MISSING between identical runs. Voting N samples per candidate id fixes that
# for the genuinely-visual residual (the deterministic basis handles the rest).

# Candidate-id field names carried by the voted label schemas, most-specific
# first; the fallback matches any ``*_id`` string field.
_CANDIDATE_ID_KEYS = ("symbol_id", "wall_class_id", "region_id", "candidate_id", "id")


def _extract_candidate_id(item: dict):
    """Return ``(id_value, id_key)`` for one voted label item, else ``(None, None)``."""
    if not isinstance(item, dict):
        return None, None
    for k in _CANDIDATE_ID_KEYS:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v, k
    for k, v in item.items():
        if k.endswith("_id") and isinstance(v, str) and v.strip():
            return v, k
    return None, None


def _vote_label_text(label) -> str:
    """Normalise a candidate label; missing/blank/non-string → ``"unknown"``."""
    if not isinstance(label, str):
        return "unknown"
    text = label.strip()
    return text if text else "unknown"


def _vote_categorical_labels(samples: list, vote_key: str) -> list:
    """Majority-vote the per-candidate labels under *vote_key* across *samples*.

    Every sample's ``vote_key`` is a list of ``{<id>, label, ...}`` dicts. For
    each candidate id the winning label is the plurality across samples (an id
    ABSENT from a sample counts as an "unknown" vote); a tie or an
    "unknown"/absent plurality yields ``"unknown"`` — flag-don't-guess.
    Confidence: unanimous → ``high``, strict majority → ``medium``, else
    ``low``. Candidate order is first-seen. Output items keep the id under the
    same key they arrived with, so the shape is identical to a single call.
    """
    order: list = []
    id_key_by_id: dict = {}
    per_sample: list = []
    for res in samples:
        mapping: dict = {}
        items = res.get(vote_key) if isinstance(res, dict) else None
        if isinstance(items, list):
            for it in items:
                cid, idk = _extract_candidate_id(it)
                if cid is None:
                    continue
                if cid not in id_key_by_id:
                    order.append(cid)
                    id_key_by_id[cid] = idk
                mapping[cid] = _vote_label_text(it.get("label"))
        per_sample.append(mapping)

    n = len(per_sample)
    voted: list = []
    for cid in order:
        tally: dict = {}
        display: dict = {}
        for mapping in per_sample:
            lab = mapping.get(cid, "unknown")   # absent → unknown vote
            low = lab.lower()
            tally[low] = tally.get(low, 0) + 1
            display.setdefault(low, lab)
        top = max(tally.values())
        winners = [low for low, c in tally.items() if c == top]
        if len(winners) == 1 and winners[0] != "unknown":
            low = winners[0]
            label = display[low]
            if top == n:
                conf = "high"
            elif top * 2 > n:
                conf = "medium"
            else:
                conf = "low"
        else:
            label, conf = "unknown", "low"
        voted.append({id_key_by_id[cid]: cid, "label": label, "confidence": conf})
    return voted


# ── 24-08: row-identity majority vote for the IDENTIFICATION passes ───────────
#
# WHY THIS EXISTS AND `_vote_categorical_labels` ABOVE DOES NOT SERVE.
# That voter votes a per-candidate LABEL under a known candidate-ID key, and it
# needs the candidate set to be fixed by the request's schema enums. `_run_pass`
# sends no schema and no candidate list: the schedule and legend passes return
# free-form tables of free-form rows, and what varies between two reads of one
# drawing is WHICH ROWS EXIST — not the label attached to an already-known row.
# So the vote key here has to be the ROW'S OWN IDENTITY: a schedule row's
# MARK/TAG, a legend row's ITEM/DESCRIPTION.
#
# That identity is folded through `_norm_item_key` — the AGGREGATOR's bucket
# identity, IMPORTED rather than re-implemented, because a second folding rule
# is precisely how two folding rules drift apart (the mistake 24-02, 24-03 and
# 24-05 each explicitly refused to make). Two spellings of one row are one row
# here for exactly the reason they are one row downstream.
#
# A surviving row's field values are taken VERBATIM from one sample that
# carried it — the most common exact payload, ties broken by first-seen sample
# order. Field values are never mixed across samples, so the voter can never
# synthesise a row, or a QUANTITY, that no paid sample actually returned
# (T-24-34). A quantity is also never part of a row's identity: a quantity is
# the field that may legitimately be misread between two passes, so making it
# part of "are these the same row?" would turn one row into two.
#
# NOT A TEMPERATURE PROBLEM. Hosted-API nondeterminism comes from
# batch-size-dependent GPU reduction kernels, not from sampling; pinning the
# temperature to zero cannot fix it, and `ensemble._probe_temperature_ignored`
# is this codebase's own recorded acknowledgement of that. No temperature
# parameter is introduced here, deliberately — and the grep that proves it
# would be defeated by writing one into a comment, so this says it in words.

# Pass types that are pure IDENTIFICATION — they READ a printed table off the
# drawing — and are therefore eligible for majority voting.
#
# `count`, `measure` and `extraction` are EXCLUDED. Their identification portion
# ("there is a bollard here") and their measurement portion ("its quantity is
# 24") arrive inside the SAME object with no seam between them, so there is no
# way to vote which objects exist without also voting their numbers. A
# majority-voted quantity would violate this phase's own contract that numbers
# come from geometry, so the passes are left single-shot rather than voted
# unsafely.
_VOTED_IDENTIFICATION_PASS_TYPES = frozenset({"schedule", "legend"})

# Row fields that may carry a row's identity, most specific first.
_ROW_IDENTITY_KEYS = (
    "mark", "tag", "item", "item_no", "description", "name", "label",
    "symbol", "type", "id",
)

# Row fields that may NEVER contribute to a row's identity — the quantity and
# unit columns are exactly what two honest reads are allowed to differ on.
_ROW_QUANTITY_KEYS = frozenset({
    "qty", "quantity", "count", "ea", "total", "totals", "amount", "sum",
    "unit", "units", "uom", "sf", "lf", "area", "length", "height", "width",
})

# Fields that may carry a TABLE's identity, most specific first.
_TABLE_IDENTITY_KEYS = ("name", "table_purpose", "schedule_type", "description")


def _canonical_signature(obj) -> str:
    """A stable, order-insensitive text signature of a JSON-ish value."""
    try:
        return json.dumps(obj, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(obj)


def _lowered_keys(row: dict) -> dict:
    """``row`` re-keyed by lowercased field name; first spelling wins.

    Column headers arrive as the drawing prints them ("MARK", "Mark", "mark"),
    so identity lookup must be case-insensitive or one sheet's casing would
    make two reads of one row two rows.
    """
    out: dict = {}
    for k, v in row.items():
        out.setdefault(str(k).strip().lower(), v)
    return out


def _row_identity(row) -> str:
    """The fold-normalised identity of one schedule/legend row.

    Falls back, in order, to: a named identity column → the first non-quantity
    text field the row carries → the row's own canonical signature (a row with
    no text at all IS its own identity, which is still deterministic).
    """
    if not isinstance(row, dict):
        return _canonical_signature(row)
    lowered = _lowered_keys(row)
    for key in _ROW_IDENTITY_KEYS:
        val = lowered.get(key)
        if isinstance(val, str) and val.strip():
            folded = _norm_item_key(val)
            if folded:
                return folded
    for key, val in lowered.items():
        if key in _ROW_QUANTITY_KEYS:
            continue
        if isinstance(val, str) and val.strip():
            folded = _norm_item_key(val)
            if folded:
                return folded
    return _canonical_signature(row)


def _table_identity(sched) -> str:
    """The fold-normalised identity of one schedule/legend TABLE."""
    if not isinstance(sched, dict):
        return _canonical_signature(sched)
    for key in _TABLE_IDENTITY_KEYS:
        val = sched.get(key)
        if isinstance(val, str) and val.strip():
            folded = _norm_item_key(val)
            if folded:
                return folded
    return _canonical_signature({k: v for k, v in sched.items() if k != "rows"})


def _majority_payload(payloads: list):
    """The most common EXACT payload among *payloads*; ties → first seen.

    Returns one of the inputs verbatim — fields are never merged across
    samples — so the vote cannot assemble a row, or a number, that no sample
    actually produced.
    """
    tally: dict = {}
    order: list = []
    first: dict = {}
    for payload in payloads:
        sig = _canonical_signature(payload)
        if sig not in tally:
            tally[sig] = 0
            order.append(sig)
            first[sig] = payload
        tally[sig] += 1
    top = max(tally.values())
    for sig in order:
        if tally[sig] == top:
            return first[sig]
    return payloads[0]


def _vote_schedule_rows(samples: list, vote_key: str = "schedules") -> list:
    """Majority-vote the identification passes' tables and rows on row identity.

    Contract:
      * a TABLE whose identity appears in a STRICT majority of samples survives;
      * within a surviving table, a ROW whose identity appears in a strict
        majority of ALL samples survives — counted against every sample, not
        only the ones that carried the table, because a table two of three
        reads saw is already weak evidence and its rows must clear the same bar;
      * a minority row, and a TIE, is DROPPED — flag-don't-guess, the same rule
        `_vote_categorical_labels` applies when it yields the unknown sentinel;
      * surviving payloads are verbatim from one sample (`_majority_payload`);
      * first-seen order is preserved, so the output is a deterministic function
        of the sample sequence.

    A surviving table may legitimately end with an EMPTY row list when the reads
    agree the table exists but agree on none of its rows. That is the honest
    answer, and `claude_analyzer._merge_schedule_lists` already ignores a table
    with no rows.
    """
    n = len(samples)
    if n <= 1:
        # Nothing to vote on. Folding a single read would silently EDIT it —
        # a one-sample "vote" must return that read untouched.
        first = samples[0] if n else {}
        items = first.get(vote_key) if isinstance(first, dict) else None
        return list(items) if isinstance(items, list) else []

    per_sample: list = []
    table_order: list = []
    for res in samples:
        buckets: dict = {}
        items = res.get(vote_key) if isinstance(res, dict) else None
        if isinstance(items, list):
            for sched in items:
                if not isinstance(sched, dict):
                    continue
                key = _table_identity(sched)
                if key not in buckets:
                    buckets[key] = {
                        "meta": {k: v for k, v in sched.items() if k != "rows"},
                        "rows": [],
                    }
                    if key not in table_order:
                        table_order.append(key)
                rows = sched.get("rows")
                if isinstance(rows, list):
                    buckets[key]["rows"].extend(r for r in rows if isinstance(r, dict))
        per_sample.append(buckets)

    voted: list = []
    for key in table_order:
        carriers = [b[key] for b in per_sample if key in b]
        if len(carriers) * 2 <= n:
            continue  # minority table, or a tie → dropped

        row_order: list = []
        row_by_sample: list = []
        for bucket in per_sample:
            mapping: dict = {}
            for row in (bucket.get(key) or {}).get("rows") or []:
                rkey = _row_identity(row)
                if rkey not in mapping:
                    mapping[rkey] = row
                    if rkey not in row_order:
                        row_order.append(rkey)
            row_by_sample.append(mapping)

        rows: list = []
        for rkey in row_order:
            carried = [m[rkey] for m in row_by_sample if rkey in m]
            if len(carried) * 2 <= n:
                continue  # minority row, or a tie → dropped
            rows.append(_majority_payload(carried))

        table = dict(_majority_payload([c["meta"] for c in carriers]))
        table["rows"] = rows
        voted.append(table)
    return voted


def _viewport_printed_fpi(page, viewports) -> dict:
    """Per-viewport printed-scale cross-check, keyed by region_id.

    Priority (mirrors scale_solver.solve_page_viewports): the viewport's own
    bound callout anchor → a scale notation in the viewport's title text →
    the page's printed notation, the last ONLY when the sheet carries exactly
    one distinct printed scale (a page-level value must not cross-check the
    wrong viewport on a genuine multi-scale sheet).
    """

    def _title_printed(vp) -> Optional[float]:
        if not getattr(vp, "title_text", ""):
            return None
        try:
            found = extract_scales_from_text(vp.title_text)
        except Exception:  # noqa: BLE001
            return None
        distinct = sorted({fpi for fpi, _ in found})
        return distinct[0] if len(distinct) == 1 else None

    page_printed: Optional[float] = None
    local_fpis = {
        round(vp.printed_fpi, 6)
        for vp in viewports
        if vp.printed_fpi and vp.kind not in _MASK_VIEWPORT_KINDS
    }
    try:
        dom_fpi, _, _ = dominant_scale(page)
    except Exception:  # noqa: BLE001
        dom_fpi = None
    if dom_fpi and len(local_fpis | {round(dom_fpi, 6)}) <= 1:
        page_printed = dom_fpi

    out = {}
    for vp in viewports:
        out[vp.region_id] = vp.printed_fpi or _title_printed(vp) or page_printed
    return out


# Candidate column names for legend-item labels in deterministic schedule
# rows (same convention as fusion._ROW_NAME_KEYS).
_LEGEND_NAME_KEYS = ("ITEM", "DESCRIPTION", "TYPE", "NAME", "SYMBOL", "LEGEND")
_MAX_LEGEND_LABELS = 60


def _legend_labels_from_schedules(schedules) -> List[str]:
    """Distinct legend-item labels harvested from deterministic table rows.

    These become the enum the symbol-gallery schema constrains answers to —
    when empty, the gallery pass is skipped and symbol groups stay flagged
    unlabeled (flag-don't-guess)."""
    labels: List[str] = []
    seen = set()
    for sched in schedules or []:
        for row in _sched_field(sched, "rows", []) or []:
            if not isinstance(row, dict):
                continue
            upper = {str(k).strip().upper(): v for k, v in row.items()}
            for key in _LEGEND_NAME_KEYS:
                value = upper.get(key)
                if value is None:
                    continue
                text = str(value).strip()
                if not text or len(text) > 80:
                    continue
                norm = text.lower()
                if norm not in seen:
                    seen.add(norm)
                    labels.append(text)
                break
            if len(labels) >= _MAX_LEGEND_LABELS:
                return labels
    return labels


def _dedupe_labels(labels: List[str], cap: int = _MAX_LEGEND_LABELS) -> List[str]:
    """Case-insensitive first-seen dedupe of a label list, capped at *cap*.

    Used to merge deterministic schedule labels with the autonomous
    project-vocabulary labels for the symbol-gallery candidate enum — the
    gallery pass only runs when this merged list is non-empty, so when
    vocabulary is empty the result is identical to schedule labels alone
    (additive-only guarantee)."""
    out: List[str] = []
    seen = set()
    for label in labels or []:
        if not isinstance(label, str):
            continue
        text = label.strip()
        if not text or len(text) > 80:
            continue
        norm = text.lower()
        if norm in seen:
            continue
        seen.add(norm)
        out.append(text)
        if len(out) >= cap:
            break
    return out


def _canonicalise_persisted_vocabulary(objects: list) -> list:
    """Fold a persisted vocabulary snapshot's names on READ (24-05, A4).

    A snapshot written before 24-03 landed can hold BOTH spellings of one
    object — the `Metal Downspout` / `Metal Downspouts` split defect F2
    produced. Promoting that split to authority would make the persistence
    change worse than the defect it fixes: the split would stop being a
    per-run accident and become a permanent property of the project.

    So every stored name is routed through 24-03's arbiter
    (:func:`resolve_published_name`, at the ``library`` authority, which is
    what a project vocabulary IS) and entries that then share a
    :func:`_norm_item_key` bucket collapse to one. This is idempotent, so
    NO migration is written against the store — running it twice yields the
    same list, and 24-RESEARCH §13 forbids a destructive migration outright.

    The loser's own spelling survives as an ALIAS rather than being deleted:
    it is a real label the plan may print, and the alias list is what the
    symbol gallery matches against. Nothing is lost, one name is published.

    Order is preserved and first-seen wins, so the fold is a pure function of
    the stored list — which is itself written once and read verbatim.
    """
    folded: list = []
    by_key: Dict[str, dict] = {}
    for obj in objects or []:
        if not isinstance(obj, dict):
            continue
        entry = dict(obj)
        # The two derivations use different name keys (`canonical_name` from
        # the naming-convention pass, `name` from the vocabulary pass); fold
        # whichever this object actually carries rather than inventing a third.
        field = None
        for candidate in ("canonical_name", "name"):
            if str(entry.get(candidate) or "").strip():
                field = candidate
                break
        if field is None:
            continue
        raw = str(entry[field]).strip()
        resolved = resolve_published_name(
            [(NAME_AUTHORITY_LIBRARY, raw, str(entry.get("unit") or ""))]
        )
        canon = resolved[0] if resolved else raw
        entry[field] = canon

        key = _norm_item_key(canon)
        winner = by_key.get(key)
        if winner is None:
            by_key[key] = entry
            folded.append(entry)
            continue

        aliases = [
            a for a in (winner.get("aliases") or [])
            if isinstance(a, str) and a.strip()
        ]
        held = {a.strip().lower() for a in aliases}
        held.add(str(winner.get(field) or winner.get("canonical_name")
                     or winner.get("name") or "").strip().lower())
        for extra in [raw] + [
            a for a in (entry.get("aliases") or []) if isinstance(a, str)
        ]:
            text = str(extra or "").strip()
            if text and text.lower() not in held:
                held.add(text.lower())
                aliases.append(text)
        winner["aliases"] = aliases
    return folded


def _lattice_as_symbol_group(lattice, fpp: float) -> SymbolGroup:
    """Present a :class:`LatticeGroup` as a candidate the registry already knows.

    Everything downstream — the candidate registry, the Set-of-Mark labelling
    pass, the unnamed-geometry ledger — is written against ``SymbolGroup``, and
    a lattice is a symbol candidate in every way that matters to them: a stable
    id, a deterministic count, and an instance bbox for each thing counted.

    Two properties are deliberate. ``needs_review`` is always True, because a
    lattice can be complete on the drawing and still leave the end-of-grid
    members undetermined (Crow: 120 drawn, and the drawing does not say whether
    12, 40 or 56 more are cast into the perimeter panels). And
    ``contained_texts`` stays EMPTY rather than being filled with the cell ids:
    the cells are where the markers are, not what the drawing calls them, and
    manufacturing an anchor out of a grid label is exactly the "name the shape"
    move the anchored-only restriction exists to prevent. An unnamed candidate
    with 120 positions and 100% grid occupancy is a good outcome — it is a
    flagged measurement, not a guess.
    """
    boxes = list(lattice.instance_bboxes_pt)
    rep = boxes[0] if boxes else (0.0, 0.0, 0.0, 0.0)
    return SymbolGroup(
        candidate_id=lattice.candidate_id,
        count=lattice.count,
        signature_hash=hashlib.sha1(
            ("grid-lattice|%s|%dx%d" % (
                lattice.marker_size_pt, lattice.n_cols, lattice.n_rows,
            )).encode("utf-8")
        ).hexdigest()[:16],
        instance_bboxes_pt=boxes,
        representative_bbox_pt=rep,
        bbox_size_ft=(
            round(lattice.marker_size_pt[0] * fpp, 3),
            round(lattice.marker_size_pt[1] * fpp, 3),
        ),
        contained_texts=[],
        confidence="high",
        needs_review=True,
    )


def _keynote_callout_as_symbol_group(callout, fpp: float) -> SymbolGroup:
    """Present a placed keynote as a candidate the registry already knows.

    Same adapter move as :func:`_lattice_as_symbol_group`, and for the same
    reason: the registry, the Set-of-Mark pass and the unnamed-geometry ledger
    are all written against ``SymbolGroup``, so a count that arrives in that
    shape needs no changes anywhere downstream.

    Where it deliberately differs from the lattice is ``contained_texts``. A
    lattice cell id is a coordinate, not a name, so filling it in would be
    manufacturing an anchor. A keynote's note text is the opposite — it is the
    sheet's OWN words for the thing the bubble points at, printed by the
    drafter in the legend. That is the text-anchored regime the whole engine
    prefers (recognition 0.65-0.92 anchored vs 0.03-0.39 symbol-conveyed), and
    it is the only reason a keynote count can carry a name at all.

    ``needs_review`` is always True. The count is a count of PLACEMENTS, and a
    keynote may mark a detail reference rather than an instance; the flag is
    what makes a miscount a 30-second confirm instead of a wrong bid, and it
    stays until repeated paid runs earn its removal.
    """
    boxes = [tuple(b) for b in callout.instance_bboxes_pt]
    rep = boxes[0] if boxes else (0.0, 0.0, 0.0, 0.0)
    return SymbolGroup(
        candidate_id="KEY-%s" % callout.number,
        count=int(callout.callout_count),
        signature_hash=hashlib.sha1(
            ("keynote-callout|%s|%s" % (callout.header, callout.number))
            .encode("utf-8")
        ).hexdigest()[:16],
        instance_bboxes_pt=boxes,
        representative_bbox_pt=rep,
        bbox_size_ft=(
            round(abs(rep[2] - rep[0]) * fpp, 3),
            round(abs(rep[3] - rep[1]) * fpp, 3),
        ),
        contained_texts=[callout.note_text] if callout.note_text else [],
        confidence="high",
        needs_review=True,
    )


def _build_symbol_count_hint(symbols) -> str:
    """User hint listing each marked cluster's deterministic repetition count.

    The clustering engine knows EXACTLY how many times each symbol repeats
    (``SymbolGroup.count``). Handing those counts to the model — alongside the
    in-context Set-of-Mark overlay of the FULL plan — is how an estimator
    reads a sheet: a symbol repeating on a regular structural grid is columns;
    one repeating along the building perimeter is bollards. A lone isolated
    crop carries none of that signal, which is why the tiny-crop gallery
    labelled everything "unknown". Pairs are sorted by count descending so the
    highest-signal clusters lead. Returns "" when there are no counted groups.
    """
    pairs = []
    for group in symbols or []:
        cid = _sched_field(group, "candidate_id", "")
        if not cid:
            continue
        count = int(_sched_field(group, "count", 0) or 0)
        pairs.append((cid, count))
    if not pairs:
        return ""
    pairs.sort(key=lambda pc: pc[1], reverse=True)
    counts_str = ", ".join("{}×{}".format(cid, count) for cid, count in pairs)
    return (
        "Each marked symbol ID repeats this many times on the sheet: "
        + counts_str
        + ". Identify what each marked symbol is by picking the best-matching "
        "object type. Use the repetition count and where it sits (a symbol "
        "repeating on a regular structural grid is columns; a symbol repeating "
        "along the building perimeter is bollards; etc.). Answer 'unknown' "
        "only if genuinely unidentifiable."
    )


def _anchor_texts(bundle) -> dict:
    """``{candidate_id: anchor_text}`` for every candidate the drawing NAMES.

    Reads ``bundle["candidate_anchors"]`` (24-01) and keeps only the records
    carrying real text. ``anchor_text is None`` is the RECORDED ABSENCE of an
    anchor and is dropped here — the absence is not a placeholder to fill in
    from the candidate's shape.

    Returns ``{}`` both when nothing is anchored and when no anchor map exists.
    Those two cases are NOT the same and must never be told apart from this
    map — use :func:`_anchor_absences` for that (INV-08).
    """
    anchors = (bundle or {}).get("candidate_anchors") or {}
    texts = {}
    for cid, record in anchors.items():
        text = record.get("anchor_text") if isinstance(record, dict) else record
        if text is None:
            continue
        text = " ".join(str(text).split())
        if text:
            texts[str(cid)] = text
    return texts


def _anchor_absences(bundle) -> set:
    """The candidate IDs whose anchor is a RECORDED ABSENCE (24-01).

    The drawing was interrogated for these candidates and printed nothing
    beside them, so nothing names them and the model must not be asked to.

    This is deliberately NOT "every ID missing from the text map". A candidate
    with NO record was never interrogated — an absent record is not a recorded
    zero (INV-08, the same rule 24-04's orphan-room branch applies to a
    bounding-wall reference that is present-and-empty versus simply absent).
    A bundle whose anchor computation failed carries no records at all, and
    that failure must not silently empty a whole vision pass.
    """
    anchors = (bundle or {}).get("candidate_anchors") or {}
    absent = set()
    for cid, record in anchors.items():
        text = record.get("anchor_text") if isinstance(record, dict) else record
        if text is None or not str(text).strip():
            absent.add(str(cid))
    return absent


def _build_anchor_hint(anchor_texts: dict, candidate_ids) -> str:
    """The per-candidate anchor table, delimiter-wrapped, for the user hint.

    The chip on the Set-of-Mark render carries the same text, but the render is
    downscaled to the model's 1568px standard and a few characters of drafting
    text can be hard to read at that scale. The table is the anchor's
    survivable delivery: it says, in text the model cannot mis-read, which
    words the drawing itself printed beside each marked candidate.

    The table is drawing-derived UNTRUSTED text, so it is wrapped in the
    ``<pdf_text>`` delimiters (T-24-27). Every semantic prompt declares that
    delimited content is data and never an instruction.

    Returns ``""`` when no listed candidate carries an anchor.
    """
    pairs = [
        (cid, anchor_texts[cid]) for cid in candidate_ids if anchor_texts.get(cid)
    ]
    if not pairs:
        return ""
    table = "\n".join("{}: {}".format(cid, text) for cid, text in pairs)
    return (
        "The drawing prints these words next to each marked candidate — this "
        "is the plan's own callout for it and is your primary evidence for "
        "identifying it:\n"
        + wrap_pdf_text(table)
    )


def _ids_shown_on(images) -> set:
    """The candidate IDs actually drawn on the images being sent.

    ``render_overlay`` partitions a large candidate set into several images and
    the request carries at most 20 of them, so the set MARKED can be a strict
    subset of the set proposed. Building the schema's enums from anything wider
    would ask the model about candidates whose markers it never received —
    the same defect, in a different costume, that asking about an unanchored
    cluster is.
    """
    shown = set()
    for img in images or []:
        for cid in (getattr(img, "info", None) or {}).get("overlay_ids") or []:
            shown.add(str(cid))
    return shown


def _main_region_from_answer(regions) -> Optional[str]:
    """The region the model flagged as the main plan, or ``None``.

    ``None`` when nothing claims it AND when more than one thing does: two
    claims are a contest, and picking the first would be guessing which of two
    disagreeing answers to trust. The deterministic main-plan selection is the
    measurement authority in either case; this answer is its cross-check.
    """
    claims = [
        r.get("region_id")
        for r in regions or []
        if isinstance(r, dict) and r.get("is_main_plan") and r.get("region_id")
    ]
    return claims[0] if len(claims) == 1 else None


def _apply_room_wall_references(rooms, answers) -> int:
    """Write each answered room's bounding-wall citation onto its bundle record.

    This is the field fusion's orphan-room branch reads (V4-DET-03): a room
    citing NO bounding wall is ledgered rather than published, because a face
    that cannot say which walls enclose it is a polygon, not a room.

    Only an answer that actually CARRIES the key writes anything. An answer
    that omits it leaves the record's field absent, and fusion reads an absent
    field as "not asked" rather than as "no walls" (INV-08) — writing an empty
    list for a room nobody answered about would manufacture the very citation
    failure the branch exists to detect.

    Returns the number of records populated.
    """
    by_id = {}
    for room in rooms or []:
        cid = _sched_field(room, "candidate_id", "")
        if cid:
            by_id[str(cid)] = room

    applied = 0
    for answer in answers or []:
        if not isinstance(answer, dict) or ROOM_WALL_REFERENCE_FIELD not in answer:
            continue
        room = by_id.get(str(answer.get("room_id") or ""))
        if room is None:
            continue
        refs = [
            str(w) for w in (answer.get(ROOM_WALL_REFERENCE_FIELD) or []) if str(w)
        ]
        if isinstance(room, dict):
            room[ROOM_WALL_REFERENCE_FIELD] = refs
        else:
            setattr(room, ROOM_WALL_REFERENCE_FIELD, refs)
        applied += 1
    return applied


def _legend_crop_rect(viewports, schedules):
    """PDF-point rect of the sheet's legend region for the gallery crop."""
    for vp in viewports or []:
        if vp.kind == "legend":
            return vp.bbox_pt
    for sched in schedules or []:
        bbox = _sched_field(sched, "bbox_pt", None)
        if bbox and any(v for v in bbox):
            return bbox
    return None


def _build_count_hint(manifest) -> Optional[str]:
    """Build a targeted-count user hint from the object manifest's EA/count items.

    Tells the count pass exactly which discrete objects to locate and tally, using
    the user's own names + aliases. Returns None when no manifest / no count items.
    """
    if not manifest:
        return None
    lines = []
    for e in manifest.entries:
        if e.measure not in ("count", "each"):
            continue
        names = [e.name, *[a for a in e.aliases if a]]
        lines.append("  - " + " / ".join(dict.fromkeys(names)))
    if not lines:
        return None
    return (
        "TARGETED COUNT — the estimator expects these discrete (EA) objects in this "
        "project. Scan the ENTIRE sheet carefully and report your best total count for "
        "each one you can see, with a confidence. If an object is not on this sheet, "
        "omit it (do not guess). Objects to look for:\n" + "\n".join(lines)
    )


def _build_measure_hint(manifest) -> Optional[str]:
    """Build a measure-pass hint from the manifest's area/length objects.

    Encourages the measure pass to estimate SF/LF totals for the expected objects
    using the drawing scale and any supplied assumptions (wall height, thickness),
    marking estimates ``approximate`` so they surface as needs_review downstream.
    """
    if not manifest:
        return None
    lines = []
    for e in manifest.entries:
        if e.measure not in ("area", "length", "volume"):
            continue
        names = " / ".join(dict.fromkeys([e.name, *[a for a in e.aliases if a]]))
        assume = ""
        if e.assumptions:
            parts = [f"{k}={v}" for k, v in e.assumptions.items()]
            assume = f" (assume {', '.join(parts)})"
        lines.append(f"  - {names} [{e.unit or e.measure}]{assume}")
    if not lines:
        return None
    return (
        "EXPECTED MEASURED QUANTITIES — the estimator expects these area/length "
        "objects. Where a total is printed on the sheet, report it. Where it is not "
        "printed but can be reasoned from the drawing using the stated SCALE and the "
        "assumptions below, provide your best estimate and set \"approximate\": true. "
        "Do not fabricate precise numbers — approximate is expected for unprinted "
        "quantities. Objects:\n" + "\n".join(lines)
    )


def _manifest_unit_counts(manifest) -> dict:
    """``{unit type -> how many the ESTIMATOR declared}`` from the manifest.

    A hotel/multifamily set draws ONE prototype of each unit type and the
    take-off multiplies by the mix.

    **This function's predecessor documented that multiplier as unrecoverable,
    and that was false.** ``_manifest_room_mix`` asserted the mix "is routinely
    not in the drawing set at all … so no reading of the plan can recover it",
    and ``docs/PIPELINE-GROUND-TRUTH.md`` recorded the same claim as BLOCKER A.
    A blind census of Moxy's own unit key plans (pages 7 and 8, ID-001 / ID-002,
    the two sheets whose printed drawing titles read ``LEVEL nn KEY PLAN``)
    reads **214 room tags with 214 distinct room numbers and no duplicates**,
    and counting them — before any comparison was made — yields ``QQ A 90``,
    ``KING A 26``, ``K SUITE B 2``, ``BUNK B 1``: **4 of 4 exact** against the
    golden multipliers. The multiplier is in the input, and
    :func:`bobbytailor.deterministic.room_tags.derive_room_mix` reads it
    (INV-05 §2 Key B; the matching correction to the ground-truth document is
    plan 23-16, decision D-01).

    So this is no longer THE room mix — it is the estimator's DECLARATION of it,
    one of two sources that :meth:`TakeoffPipeline._resolve_room_mix` merges
    under the D-10 precedence, where the drawings win and disagreement is
    flagged rather than silently resolved.

    Declared as manifest entries carrying ``unit_count``::

        {"name": "QQ A", "measure": "unit_type", "assumptions": {"unit_count": 90}}

    It is a COUNT, never a quantity: the app still measures every area.
    """
    mix: dict = {}
    if not manifest:
        return mix
    for e in getattr(manifest, "entries", None) or []:
        count = (e.assumptions or {}).get("unit_count")
        if count in (None, ""):
            continue
        try:
            n = int(float(count))
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        key = " ".join(str(e.name or "").split()).strip().lower()
        if key:
            mix[key] = n
    return mix


def _room_mix_meta_payload(resolution, manifest) -> dict:
    """The ``room_mix_meta`` dict ``fuse_sheet`` receives, in ONE place.

    Carries, per unit type: the count's ``source`` (census | manifest |
    assumed), any resolver ``note`` (a disagreement, an abbreviation match, a
    manifest fallback), and ``disputed`` — True when the estimator's manifest
    declares a DIFFERENT count than the one published. The binder's
    multiplier-review flag reads ``disputed`` structurally rather than
    grepping the note's wording, so the flag cannot rot when the note's prose
    changes (D-10: the manifest is a cross-check that FLAGS disagreement; the
    file itself is never edited).
    """
    declared = _manifest_unit_counts(manifest)
    return {
        name: {
            "source": resolution.sources.get(name, ""),
            "note": resolution.name_flags.get(name, ""),
            "disputed": (
                declared.get(name) is not None
                and int(declared[name]) != int(resolution.counts[name])
            ),
        }
        for name in resolution.counts
    }


def _manifest_scale_fpi(manifest) -> Optional[float]:
    """Project drawing scale (feet per inch) from a manifest assumption, if any.

    A manifest entry may carry ``assumptions.scale_ft_per_in`` (e.g. 20 for
    1"=20'); the first such value is used as the reliable scale for geometry
    measurement. Returns None when absent.
    """
    if not manifest:
        return None
    for e in manifest.entries:
        v = e.assumptions.get("scale_ft_per_in") or e.assumptions.get("scale_feet_per_inch")
        if v:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _manifest_wall_height(manifest) -> float:
    """Project wall height for derived wall areas, sourced from the manifest.

    Uses the largest ``height_ft`` assumption among wall-like area entries (or any
    entry that supplies one). Falls back to the conventional 9ft when absent.
    """
    default = 9.0
    if not manifest:
        return default
    heights = []
    for e in manifest.entries:
        h = e.assumptions.get("height_ft")
        if h:
            try:
                heights.append(float(h))
            except (TypeError, ValueError):
                pass
    return max(heights) if heights else default


def _join_hints(*hints: Optional[str]) -> Optional[str]:
    """Join non-empty user hints with a blank line; None when all are empty."""
    parts = [h for h in hints if h]
    if not parts:
        return None
    return "\n\n".join(parts)


def _resolve_wall_height(manifest, learned) -> "tuple[float, str]":
    """Wall/ceiling height for derived wall areas, with its source.

    Precedence (RESEARCH §6 injection point 3): an explicit manifest
    ``height_ft`` assumption wins (deterministic dev input for this run);
    otherwise a learned ``wall_height_ft`` assumption applies — learned data
    only fills the gap when no schedule/legend/manifest source exists;
    otherwise the conventional 9 ft cold-start default. The returned source
    ("manifest" | "learned" | "default") flags the assumption downstream
    (``assumption_source`` on derived wall-area items) — an assumption is
    never silent, whatever supplied it.
    """
    default = 9.0
    if manifest:
        heights = []
        for e in manifest.entries:
            h = e.assumptions.get("height_ft")
            if h:
                try:
                    heights.append(float(h))
                except (TypeError, ValueError):
                    pass
        if heights:
            return max(heights), "manifest"
    if learned is not None:
        try:
            value = learned.get_assumption_value("wall_height_ft")
        except Exception:  # noqa: BLE001 — learning must never break a run
            value = None
        if isinstance(value, dict):
            value = value.get("wall_height_ft") or value.get("height_ft") or value.get("value")
        try:
            height = float(value) if value is not None else None
        except (TypeError, ValueError):
            height = None
        if height and height > 0:
            return height, "learned"
    return default, "default"


# Autonomous wall-height resolution (manifest replacement, plans-only).
#
# Precedence is TIERED so an explicit clear-height callout is never outvoted by a
# stray plan dimension that happens to sit near a material keyword (the Crow bug:
# "48' - 4\"" bay dimensions near "PANEL" resolved 48' instead of the printed
# "36' CLEAR"). Tier 1 (CLEAR/CLR) is authoritative; Tier 2 is an explicit
# wall-height keyword; Tier 3 (material-adjacent / A.F.F) is the least-reliable
# fallback used only when no clear/wall-height callout parses.
#
# Tier 2 — explicit wall-height keywords (a feet-inches token in the window is a
# genuine wall-height callout).
_WALL_HEIGHT_PRIMARY_KEYWORDS = (
    "T.O. WALL",
    "TOP OF WALL",
    "T/WALL",
    "WALL HEIGHT",
    "WALL HT",
)
# Tier 3 — material-adjacent / above-finished-floor tokens (weakest signal; a
# nearby feet-inches token MAY be a wall height but is often a plan dimension, so
# this tier fires only when Tiers 1 & 2 are empty).
_WALL_HEIGHT_MATERIAL_KEYWORDS = (
    "TILT",
    "CMU",
    "PANEL",
    "A.F.F",
    "AFF",
)
# Back-compat alias (kept for any external reference); the union of the keyword
# tiers scanned by the feet-inches window search.
_WALL_HEIGHT_KEYWORDS = _WALL_HEIGHT_PRIMARY_KEYWORDS + _WALL_HEIGHT_MATERIAL_KEYWORDS
# Feet-inches token: "35'-0\"", "30' - 6", "24'". Feet 1-2 digits (heights are
# single/double-digit); inches optional.
_WALL_HEIGHT_TOKEN = re.compile(r"(\d{1,2})\s*'\s*-?\s*(\d{1,2})?\s*\"?")
# Dedicated CLEAR / CLR clear-height patterns (Tier 1, authoritative). A foot
# mark is REQUIRED so a bare "48" gridline number or an inch value
# ("48\" A.F.F.") can never match; the whole-word CLEAR boundary excludes
# "CLEARANCE" and "CLEAR ANODIZED".
_CLEAR_HEIGHT_PATTERNS = (
    # feet (opt. inches) immediately before the CLEAR / CLR keyword:
    #   "36' CLEAR", "BUILDING TO BE 36'-0\" CLEAR"
    re.compile(
        r"(\d{1,2})\s*'\s*(?:-\s*(\d{1,2})\s*\"?)?\s*(?:CLEAR|CLR)\b",
        re.IGNORECASE,
    ),
    # the keyword (opt. HEIGHT/HT) then the feet value:
    #   "CLEAR HEIGHT 36'", "CLR HT 24'-0\"", "CLEAR 18'-0\""
    re.compile(
        r"\b(?:CLEAR|CLR)\b(?:\s*(?:HEIGHT|HT))?\s*[:=]?\s*(\d{1,2})\s*'\s*"
        r"(?:-\s*(\d{1,2})\s*\"?)?",
        re.IGNORECASE,
    ),
)
# Plausible interior/clear wall heights (ft). Outside this band we are reading a
# plan dimension, a detail callout, or a spec code — not a wall height.
_WALL_HEIGHT_MIN_FT = 8.0
_WALL_HEIGHT_MAX_FT = 60.0
# Flagged fallback when nothing parses: a conventional industrial clear height.
_WALL_HEIGHT_DEFAULT_FT = 30.0


def _feet_inches_to_ft(feet_str, inches_str) -> Optional[float]:
    """(feet, inches) regex groups → feet within the plausible wall-height band."""
    try:
        feet = int(feet_str)
    except (TypeError, ValueError):
        return None
    inches = 0
    if inches_str:
        try:
            inches = int(inches_str)
        except (TypeError, ValueError):
            inches = 0
    if inches >= 12:
        return None
    val = feet + inches / 12.0
    if _WALL_HEIGHT_MIN_FT <= val <= _WALL_HEIGHT_MAX_FT:
        return val
    return None


def _parse_wall_height_token(match) -> Optional[float]:
    """Feet-inches regex match → feet within the plausible wall-height band."""
    return _feet_inches_to_ft(match.group(1), match.group(2))


def _clear_height_values(text: str) -> List[float]:
    """Plausible clear heights from explicit CLEAR / CLR callouts (Tier 1)."""
    out: List[float] = []
    for pat in _CLEAR_HEIGHT_PATTERNS:
        for m in pat.finditer(text):
            val = _feet_inches_to_ft(m.group(1), m.group(2))
            if val is not None:
                out.append(val)
    return out


def _keyword_window_heights(text: str, upper: str, keywords) -> List[float]:
    """Plausible heights from feet-inches tokens near each keyword's occurrence."""
    heights: List[float] = []
    for keyword in keywords:
        start = 0
        while True:
            idx = upper.find(keyword, start)
            if idx < 0:
                break
            start = idx + len(keyword)
            window = text[max(0, idx - 30): idx + len(keyword) + 40]
            for match in _WALL_HEIGHT_TOKEN.finditer(window):
                val = _parse_wall_height_token(match)
                if val is not None:
                    heights.append(val)
    return heights


def _resolve_project_wall_height(
    pages_text, footprint=None, learned=None, datum_span_ft=None,
) -> "tuple[float, str]":
    """Autonomously resolve the project wall/clear height, with its source.

    Replaces the manifest ``height_ft`` role under the plans-only mandate.
    Precedence (per the binding spec): a learned ``wall_height_ft`` assumption
    wins when present (a prior HUMAN correction outranks everything, matching
    the learning-loop mandate); then the plan text layer, read for a wall/clear
    height callout near a wall keyword (``T.O. WALL``, ``TOP OF WALL``,
    ``CLEAR``/``CLR``, ``WALL HEIGHT``, or a feet-inches token near
    ``TILT``/``CMU``/``PANEL``), taking a robust (max plausible, 8'-60')
    value; then the ELEVATION DATUM SPAN. When nothing parses at all, a
    flagged industrial default (30.0 ft) applies.

    The datum span sits BELOW the plan callout, not above it — 23-14 put it on
    top on the argument that "Crow's 36' CLEAR understates the panels by 20%",
    and the live run falsified that: the datum ladder reads 48 ft, and
    2,972 LF of measured perimeter x 48 ft published 142,661 SF of tilt-up
    wall against a golden 108,443 SF (31.6% error) where the plan's own 36'
    CLEAR gives 1.3%. Worse, that published figure IS the perimeter x
    datum-height product the elevation binder's own coverage note promises
    never to publish (D-11): the datum height simply left the elevation route
    through this resolver and multiplied the perimeter somewhere else. A
    second measurement route cross-checks the first; it does not replace it.

    Args:
        pages_text: Concatenated plan text layer (elevations / sections /
                    keynotes / general notes across all pages).
        footprint:  Optional Footprint (unused for the value today; reserved so
                    callers can pass the measured extent for future bounds).
        learned:    Optional LearnedContext; a stored ``wall_height_ft`` wins.
        datum_span_ft: Optional elevation datum span (ft) measured by
                    ``TakeoffPipeline._project_datum_span``. ``None`` keeps
                    this function byte-identical to its pre-23-14 behaviour.

    Returns:
        ``(height_ft, source)`` where source is ``"learned"`` | ``"datum"`` |
        ``"plan"`` | ``"default"`` — the assumption is never silent.
    """
    if learned is not None:
        try:
            value = learned.get_assumption_value("wall_height_ft")
        except Exception:  # noqa: BLE001 — learning must never break a run
            value = None
        if isinstance(value, dict):
            value = value.get("wall_height_ft") or value.get("height_ft") or value.get("value")
        try:
            height = float(value) if value is not None else None
        except (TypeError, ValueError):
            height = None
        if height and height > 0:
            return height, "learned"

    try:
        span = float(datum_span_ft) if datum_span_ft is not None else None
    except (TypeError, ValueError):
        span = None

    text = pages_text or ""
    if text:
        upper = text.upper()
        # Tier 1 (authoritative) — an explicit CLEAR / CLR clear-height callout
        # ("NN' CLEAR", "CLEAR HEIGHT NN'"). This is THE building/wall height on
        # tilt-up & industrial plans and must win over any material-adjacent
        # plan dimension (Crow: "36' CLEAR" beats stray "48' - 4\"" bay dims).
        clears = _clear_height_values(text)
        if clears:
            return round(max(clears), 2), "plan"
        # Tier 2 — an explicit wall-height keyword (T.O. WALL, WALL HEIGHT, ...).
        primary = _keyword_window_heights(text, upper, _WALL_HEIGHT_PRIMARY_KEYWORDS)
        if primary:
            return round(max(primary), 2), "plan"
        # Tier 3 (fallback) — material-adjacent / A.F.F tokens (least reliable);
        # used ONLY when no clear-height or wall-height callout parsed.
        material = _keyword_window_heights(text, upper, _WALL_HEIGHT_MATERIAL_KEYWORDS)
        if material:
            return round(max(material), 2), "plan"

    # The elevation datum span, LAST among the measured tiers. It is a second
    # measurement ROUTE, and D-11 says a second route cross-checks the first and
    # never replaces it: when the plan states its own height, that statement
    # stands and the datum ladder only flags disagreement
    # (:meth:`TakeoffPipeline._wall_height_cross_check`). Where the plan states
    # nothing there is no first route to displace and no reconciliation to
    # fabricate, so a measured ladder still beats the blind default.
    if span is not None and span > 0:
        return round(span, 2), "datum"

    return _WALL_HEIGHT_DEFAULT_FT, "default"


#: How far the elevation datum ladder may sit from the plan's own stated wall
#: height before the two are reported as disagreeing. Wide enough that parapet
#: vs. clear-height bookkeeping does not cry wolf, narrow enough that Crow's
#: 36 ft vs 48 ft (a third of the height) is caught.
_WALL_HEIGHT_CROSS_CHECK_TOL = 0.10


def _wall_height_cross_check_note(
    height_ft, source, datum_span_ft
) -> Optional[str]:
    """The datum ladder's verdict on the published wall height, or None.

    D-11 in one sentence: a second measurement route flags disagreement and
    publishes nothing. The elevation datum span is that second route for the
    wall height, so when the plan states a height of its own the ladder is
    reduced to this note — it never becomes the number that multiplies the
    measured perimeter.
    """
    try:
        span = float(datum_span_ft) if datum_span_ft is not None else None
        height = float(height_ft) if height_ft is not None else None
    except (TypeError, ValueError):
        return None
    if not span or span <= 0 or not height or height <= 0:
        return None
    if source == "datum":
        return None  # the ladder IS the published height; nothing to reconcile
    rel = abs(span - height) / height
    if rel <= _WALL_HEIGHT_CROSS_CHECK_TOL:
        return (
            "wall-height cross-check: the published %.2f ft (%s) agrees with "
            "the elevation datum ladder's %.2f ft within %.1f%%. The ladder is "
            "a cross-check only and publishes no height (D-11)"
            % (height, source, span, rel * 100.0)
        )
    return (
        "wall-height cross-check: the published %.2f ft (%s) DISAGREES with "
        "the elevation datum ladder's %.2f ft by %.0f%% — BOTH are flagged, "
        "neither is preferred, and the ladder publishes no height (D-11). "
        "Every wall area derived from the published height inherits this "
        "uncertainty; a datum ladder measures parapet-to-floor and a plan "
        "callout may state clear height, and which one the walls are bid at "
        "is an estimator's call, not a silent substitution"
        % (height, source, span, rel * 100.0)
    )


def _legend_for_drawing(legends: dict, is_demo: bool) -> dict:
    """The keynote legend belonging to THIS drawing — demo or new-work.

    A tag's meaning depends on which drawing it sits in: Bob's '03' is NEW
    EIFS SCRATCH COAT inside FRONT ELEVATION NEW and REMOVE EXISTING LIGHT
    SCONCE inside FRONT ELEVATION DEMOLITION. A demolition drawing resolves
    through the DEMO-headed legend(s); everything else through the rest.
    """
    picked = {
        header: entries
        for header, entries in (legends or {}).items()
        if ("DEMO" in header.upper()) == bool(is_demo)
    }
    merged: dict = {}
    for entries in picked.values():
        for number, text in entries.items():
            merged.setdefault(number, text)
    return merged


def _attribute_facade_materials(facade, tags, legend) -> list:
    """Text-anchored material attribution for one facade, sorted by evidence.

    Each positioned keynote tag inside the drawing resolves through ITS
    drawing's legend to a note text; the naming layer
    (:func:`component_library.wall_material_from_text`) says whether that
    text names a wall material. A tag whose legend text names no material
    attributes nothing — flagged downstream, never guessed.

    A tag sitting INSIDE a sub-component the fill actually found (a detached
    sign band) CLAIMS that sub-region's area as the material's measurable
    split; each sub-region is claimable once. Everything else is evidence of
    presence only — the tag count orders the materials, the boundary is never
    invented, and no ratio split ever happens here or downstream.
    """
    from bobbytailor.deterministic.component_library import (  # noqa: PLC0415
        wall_material_from_text,
    )

    if not tags or not legend:
        return []
    materials: dict = {}
    claimed_subs: set = set()
    subs = list(getattr(facade, "sub_components", None) or [])
    for number, x, y in tags:
        material = wall_material_from_text(legend.get(number))
        if not material:
            continue
        record = materials.setdefault(
            material, {"material": material, "tags": [], "count": 0,
                       "claimed_sf": None}
        )
        record["count"] += 1
        if number not in record["tags"]:
            record["tags"].append(number)
        for j, sub in enumerate(subs):
            if j in claimed_subs:
                continue
            bx0, by0, bx1, by1 = sub.get("bbox_pt", (0, 0, 0, 0))
            if bx0 <= x <= bx1 and by0 <= y <= by1:
                claimed_subs.add(j)
                record["claimed_sf"] = (
                    (record["claimed_sf"] or 0.0) + float(sub["area_sf"])
                )
                break
    return sorted(
        materials.values(), key=lambda m: (-m["count"], m["material"])
    )


def _flag_same_orientation_pairs(facades) -> None:
    """Two SURVIVING same-orientation facades flag each other.

    Bob's page 4 draws FRONT ELEVATION DEMOLITION beside FRONT ELEVATION NEW
    at almost the same area. Title-based exclusion removes the demolition;
    this guard is the backstop for the day a demolition title is NOT
    recognised — a same-orientation pair that both survive into new-work
    quantities is suspicious, and BOTH flag rather than one being silently
    picked. (Chelsea's genuine side-by-side SIDE pairs also flag: two real
    side elevations of near-equal area are exactly what a missed demolition
    would look like, and a human confirms in seconds.)
    """
    by_orientation: dict = {}
    for facade in facades or ():
        if getattr(facade, "excluded", False):
            continue
        orientation = getattr(facade, "orientation", "") or ""
        if not orientation:
            continue
        by_orientation.setdefault(orientation, []).append(facade)
    for orientation, group in by_orientation.items():
        if len(group) < 2:
            continue
        titles = ", ".join(repr(f.title) for f in group)
        reason = (
            "%d surviving %s elevations on one sheet (%s) — verify none is a "
            "demolition or duplicate of another before their areas are summed"
            % (len(group), orientation, titles)
        )
        for facade in group:
            facade.needs_review = True
            facade.review_reason = (
                "%s; %s" % (facade.review_reason, reason)
                if facade.review_reason else reason
            )


def _learned_scale_prior(learned, sheet_name: str) -> Optional[float]:
    """Learned feet-per-inch scale prior for *sheet_name*, if any.

    Reads the 21-04 assumption keys ``scale_fpi:<sheetname-pattern>`` (exact
    normalized sheet name first, then the ``*`` wildcard). The value feeds
    ``resolve_scale_v2(..., learned_prior=...)`` — which already ranks it
    LAST (21-07): the prior fires ONLY when the solved and printed tiers are
    empty, so a learned scale can never outrank deterministic evidence
    (anti-amplification, V3-LEARN-04).
    """
    if learned is None:
        return None
    pattern = str(sheet_name or "").strip().lower()
    for key in ("scale_fpi:%s" % pattern, "scale_fpi:*"):
        try:
            value = learned.get_assumption_value(key)
        except Exception:  # noqa: BLE001 — learning must never break a run
            return None
        if value is None:
            continue
        if isinstance(value, dict):
            value = (
                value.get("feet_per_inch")
                or value.get("fpi")
                or value.get("scale_ft_per_in")
                or value.get("value")
            )
        try:
            fpi = float(value)
        except (TypeError, ValueError):
            continue
        if fpi > 0:
            return fpi
    return None


# merge_passes is imported from claude_analyzer (canonical implementation, plan 20-03).
# It is also re-exported here so callers that imported it from takeoff_pipeline continue
# to work without modification.
# (The stub that previously lived here has been removed.)


# ---------------------------------------------------------------------------
# QuantityVerifier
# ---------------------------------------------------------------------------

class QuantityVerifier:
    """Post-extraction sanity checker.

    Applies generic min/max rules per unit category.  Items outside the sane
    range are flagged for review but never suppressed — report generation
    always proceeds.

    Flags feed the targeted-crop verify-retry loop (21-14, V3-ACC-05,
    ``bobbytailor.vision.verify_retry``) when
    ``RunSettings.verify_retry_enabled`` is set: out-of-band values get a
    bounded, budget-charged narrow crop question to the dense model before
    human review. The original extraction is preserved regardless; a flag is
    never removed without a recorded resolution + retry history.

    Rules are intentionally loose to catch only egregious outliers.
    Do NOT embed project-specific quantity thresholds (individual client
    values, Crow/Bob ranges, etc.) in this class.
    """

    # Generic per-unit sanity bounds (min inclusive, max inclusive).
    _RULES: dict[str, dict] = {
        "ea":  {"min": 1,       "max": 5_000},
        "sf":  {"min": 1,       "max": 500_000},
        "lf":  {"min": 1,       "max": 50_000},
        "cy":  {"min": 1,       "max": 10_000},
        "ton": {"min": 1,       "max": 5_000},
        "gal": {"min": 1,       "max": 100_000},
    }

    def verify(self, extracted: dict, sheet_name: str = "") -> list[dict]:
        """Check all quantities in *extracted*.

        Returns a (possibly empty) list of flag dicts.  Each flag contains:
        ``{"sheet", "item", "qty", "unit", "rule"}``.

        Logs a WARNING for each flagged item but does NOT raise.
        """
        flags: list[dict] = []

        def _check(item_name: Optional[str], qty, unit: str) -> None:
            unit_key = (unit or "").strip().lower().rstrip(".")
            rule = self._RULES.get(unit_key)
            if rule is None or qty is None:
                return
            try:
                q = float(qty)
            except (TypeError, ValueError):
                return
            if q < rule["min"] or q > rule["max"]:
                flags.append(
                    {
                        "sheet": sheet_name,
                        "item": item_name,
                        "qty": qty,
                        "unit": unit_key,
                        "rule": rule,
                    }
                )

        for comp in extracted.get("components", []):
            if isinstance(comp, dict):
                _check(comp.get("name"), comp.get("quantity"), comp.get("unit", "ea"))

        for meas in extracted.get("measurements", []):
            if isinstance(meas, dict):
                _check(meas.get("description"), meas.get("value"), meas.get("unit", ""))

        if flags:
            logger.warning(
                "QuantityVerifier: %d flag(s) on %r", len(flags), sheet_name
            )
            for f in flags:
                logger.warning(
                    "  flagged: %r qty=%s %s (allowed %s–%s)",
                    f["item"], f["qty"], f["unit"],
                    f["rule"]["min"], f["rule"]["max"],
                )

        return flags


# ---------------------------------------------------------------------------
# TakeoffPipeline
# ---------------------------------------------------------------------------

class TakeoffPipeline:
    """Multi-pass extraction orchestrator consumed by pdf_analyzer and scraper.

    Usage::

        pipeline = TakeoffPipeline()
        result = pipeline.run_sheet(
            image_path="path/to/sheet.png",
            sheet_name="A2.1",
            sheet_type="floor_plan",   # or None to auto-classify
            title_block_text="LEVEL 1 FLOOR PLAN",
        )

    The result dict matches the existing analyze_drawing output schema so
    downstream calculator.py / aggregator.py require no changes for 20-00.
    """

    def __init__(
        self,
        analyzer: Optional[Callable] = None,
        settings: Optional[RunSettings] = None,
    ) -> None:
        """
        Args:
            analyzer: Callable with the same signature as analyze_drawing.
                      Inject a mock in tests to avoid real API calls.
                      Defaults to the module-level analyze_drawing import.
            settings: Shared run configuration; defaults to
                      ``RunSettings.from_env()`` so the module-level scraper
                      singleton (``TakeoffPipeline()``) keeps working.
        """
        if analyzer is not None:
            self._analyzer = analyzer
        else:
            # Use the module-level name so it can be patched by tests.
            # sys.modules[__name__] resolves to THIS module object under both
            # the package import (bobbytailor.pipeline.takeoff_pipeline) and
            # the spec-loaded test pattern (test_pipeline_parity._load), so
            # patching either module's analyze_drawing attribute is honored.
            _self_module = sys.modules[__name__]
            self._analyzer = _self_module.analyze_drawing
        self._settings = settings if settings is not None else RunSettings.from_env()
        # Optional object manifest, set by run_project; drives targeted counting.
        self._manifest = None
        # Autonomous project vocabulary (hybrid-naming manifest replacement):
        # built ONCE per project by run_project. `_project_vocabulary` holds the
        # parsed object dicts; `_project_vocab_labels` is the flat deduped
        # names+aliases feed merged into the symbol-gallery candidate list.
        self._project_vocabulary: list = []
        self._project_vocab_labels: List[str] = []
        # Autonomous project wall/clear height (manifest replacement): resolved
        # ONCE per project by run_project from the plan text layer (or learned
        # context), and threaded into fuse_sheet so wall_area vocabulary items
        # bind as SF (LF × height). None until run_project resolves it.
        self._project_wall_height: Optional[float] = None
        self._project_wall_height_source: Optional[str] = None
        # The elevation datum ladder's verdict on that height (D-11: the second
        # route flags, it never publishes). Set by run_project.
        self._wall_height_cross_check: Optional[str] = None
        # Optional reliable drawing scale (feet per inch) for geometry measurement.
        self._scale_fpi = None
        # Finish-code review ledger: one per run so the cap on how many
        # distinct codes may open a review row is a run-level guarantee.
        # Replaced by run_project; this default keeps standalone run_sheet
        # callers bounded too.
        self._material_tag_ledger = MaterialTagLedger()
        # One BudgetGuard per run (set by run_project). The scraper path
        # threads its own run-level guard via run_sheet(budget=...) —
        # 21-REVIEW WR-05 parity. The per-sheet fallback in run_sheet exists
        # only for standalone/dev callers so no call site is ever unguarded.
        self._run_budget: Optional[BudgetGuard] = None
        # extract_schedules() scans the whole document — cache per pdf_path.
        self._schedules_cache: dict = {}
        # The unit-mix resolution (in-plan census + manifest, D-10 precedence)
        # is a DOCUMENT-level answer, not a per-sheet one: selecting the unit
        # key plans reads every sheet's drawing titles. Cached per pdf_path.
        self._room_mix_cache: dict = {}
        # Run-level LearnedContext (21-16, V3-LEARN-03): retrieved ONCE at
        # run start (never per-sheet DB churn) and injected forward into
        # prompt hints, the scale-prior feed, and the guardrail flags.
        self._learned_context: Optional[LearnedContext] = None

    @property
    def settings(self) -> RunSettings:
        """The shared RunSettings this pipeline was constructed with."""
        return self._settings

    @settings.setter
    def settings(self, value: RunSettings) -> None:
        """Replace the run configuration (V3-STRUCT-02 entry-point parity).

        The scraper keeps a module-level pipeline singleton, so it refreshes
        settings via ``RunSettings.from_env()`` at the start of every run —
        the identical construction pdf_analyzer performs per run.
        """
        self._settings = value

    @property
    def learned_context(self) -> Optional[LearnedContext]:
        """The run's retrieved LearnedContext (None: disabled / cold start)."""
        return self._learned_context

    def load_learning(
        self, project_key: Optional[str], project_type: Optional[str] = None
    ) -> Optional[LearnedContext]:
        """Load (or refresh) the run-level LearnedContext — best effort.

        Called by both entry points at run start (project_type inferred from
        prior corrections) and again once ``_detect_project_type`` has run,
        so type-level vocabulary/manifests join the bundle. Learning is
        strictly additive: any store failure logs and leaves the run
        learning-free (the 21-09 best-effort convention) — a broken
        learning DB must never break a take-off.
        """
        self._learned_context = None
        if not project_key or not self._settings.learning_enabled:
            return None
        try:
            # Module-level name lookup so tests can patch
            # `takeoff_pipeline.load_learned_context`.
            self._learned_context = load_learned_context(project_key, project_type)
        except Exception as exc:  # noqa: BLE001 — learning is best-effort
            logger.warning(
                "load_learning: learned-context retrieval failed for %r (%s) "
                "— run continues without learning", project_key, exc,
            )
            self._learned_context = None
        return self._learned_context

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _skip_veto_signal(
        self,
        pdf_path: Optional[str],
        page_index: Optional[int],
        sheet_name: str = "",
    ) -> "tuple":
        """Measurable signal for a page the classifier wants to discard.

        Returns ``(signal, veto_fires)``. The veto fires when the page carries
        at least one plan title with a printed scale beneath it, or at least one
        non-title-block viewport with a solved scale — i.e. when there is
        genuinely something on the page that can be measured correctly.

        Zero API and bounded per page. A malformed page degrades to "no signal,
        no veto" rather than aborting the run (threat T-23-01): an untrusted PDF
        must not be able to stop the analysis by carrying one broken page.
        """
        signal = {"plan_titles": 0, "printed_scales": 0, "viewports": 0,
                  "schedules": 0}
        if not pdf_path or page_index is None:
            # Image-only caller (the scraper's blob-less path): no page to ask.
            return signal, False
        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:  # noqa: BLE001 — unreadable PDF → no veto
            logger.warning(
                "run_sheet: %r — cannot open %s to check for measurable "
                "geometry (%s); the classifier verdict stands",
                sheet_name, pdf_path, exc,
            )
            return signal, False
        try:
            signal = page_measurable_signal(doc[page_index])
        except Exception as exc:  # noqa: BLE001 — per-page degradation
            logger.warning(
                "run_sheet: %r — measurable-signal probe failed on page %s "
                "(%s); the classifier verdict stands",
                sheet_name, page_index, exc,
            )
            return signal, False
        finally:
            doc.close()
        return signal, (signal["plan_titles"] > 0 or signal["viewports"] > 0)

    def run_sheet(
        self,
        image_path: str,
        sheet_name: str,
        sheet_type: Optional[str] = None,
        title_block_text: str = "",
        full_page_text: str = "",
        pdf_path: Optional[str] = None,
        page_index: Optional[int] = None,
        budget: Optional[BudgetGuard] = None,
        *,
        coverage: Optional[SheetCoverage] = None,
    ) -> dict:
        """Run the applicable extraction flow for a single sheet.

        21-13 routing (deterministic-first, V3-ACC-01/03):

        - title_sheet → skip sentinel (zero API cost, unchanged).
        - Deterministic-eligible sheet types (plan bodies + schedules) WITH a
          source PDF page: vector sheets run the deterministic engine with
          vision as semantic labeler only; raster plan sheets run the
          ensemble-voted vision estimate (``measurement_mode="raster"``).
        - Everything else (image-only callers, elevations/details/MEP):
          legacy multi-pass vision extraction, unchanged — but every vision
          call is charged to the per-run BudgetGuard.

        Args:
            image_path:       Absolute path to the sheet screenshot/image.
            sheet_name:       Sheet identifier (e.g. "A2.1", "C1.0").
            sheet_type:       Pre-classified sheet type; if None, classified
                              from title_block_text / full_page_text.
            title_block_text: Text from the title block (bottom-right region).
            full_page_text:   Full page OCR text used as fallback classifier.
            pdf_path:         Source PDF for the deterministic engine.
            page_index:       0-based page index into *pdf_path*.
            budget:           Per-run BudgetGuard (threaded by run_project);
                              None → the run-level guard, else a fresh
                              per-sheet guard so no call site is unguarded.
            coverage:         KEYWORD-ONLY, default None. This sheet's ledger
                              row, enriched in place with the classifier's
                              reason, the measurable signal and the final
                              disposition. None keeps every existing call site
                              (three in scrape/scraper.py) byte-identical.

        Returns:
            Merged extraction dict, or a skip sentinel for title_sheet:
            {"_skipped": True, "sheet_type": "title_sheet", "sheet_name": ...,
             "_skip_reason": ..., "_skip_keyword": ..., "_skip_context": ...,
             "_measurable_signal": {...}}
        """
        # Step 1 — classify if not provided
        classifier_keyword = getattr(coverage, "classifier_keyword", "") or ""
        classifier_context = getattr(coverage, "classifier_context", "") or ""
        if sheet_type:
            # Pre-classified by the caller (the PDF path): its ledger row
            # already carries the deciding keyword and context.
            resolved_type = sheet_type
        else:
            resolved_type, type_source, classifier_keyword, classifier_context = (
                classify_sheet_type_verbose(title_block_text, full_page_text)
            )
            if coverage is not None:
                coverage.sheet_type = resolved_type
                coverage.type_source = type_source
                coverage.classifier_keyword = classifier_keyword
                coverage.classifier_context = classifier_context

        # Step 2 — determine passes
        passes = plan_passes(resolved_type, title_block_text=title_block_text)

        guard = budget or self._run_budget or BudgetGuard(self._settings.budget_usd)

        if not passes:
            # The classifier wants to discard this sheet entirely. Before
            # honouring that, ask the drawing (INV-08 §3.4): measurable
            # geometry OUTRANKS a keyword.
            signal, veto_fires = self._skip_veto_signal(
                pdf_path, page_index, sheet_name
            )

            if veto_fires:
                # A keyword must not be able to veto measurable geometry.
                # 16 of Moxy's 40 pages are guestroom prototypes carrying 5-6
                # scaled "<NAME> - <KIND> PLAN" drawings each, discarded because
                # an electrical keynote saying "COVER PLATE" bled into the
                # title-block crop. The trigger here is the PRESENCE of scaled
                # plan geometry — a position/shape signal, never a tuned count.
                logger.info(
                    "run_sheet: %r classified %r but carries %d scaled plan "
                    "drawing(s) and %d scaled viewport(s) — classifier "
                    "OVERRULED; deterministic path only (zero API)",
                    sheet_name, resolved_type,
                    signal["plan_titles"], signal["viewports"],
                )
                resolved_type = "floor_plan"
                if coverage is not None:
                    coverage.sheet_type = resolved_type
                    coverage.classifier_overruled = True
                    coverage.disposition = MEASURED_PARTIAL
                    coverage.reason = (
                        "classifier overruled; deterministic geometry only"
                    )
                    coverage.measurable_signal = dict(signal)

                # DETERMINISTIC ONLY. Recovering these sheets onto the legacy
                # vision path would be real API spend on a sheet a keyword
                # already called worthless (INV-08 risk 1), so the veto never
                # falls through to the vision passes below: it either returns
                # deterministic geometry or returns an honest sentinel.
                routed = None
                if (
                    self._settings.deterministic_enabled
                    and pdf_path is not None
                    and page_index is not None
                ):
                    routed = self._route_deterministic(
                        image_path=image_path,
                        sheet_name=sheet_name,
                        resolved_type=resolved_type,
                        pdf_path=pdf_path,
                        page_index=page_index,
                        guard=guard,
                        full_page_text=full_page_text,
                        deterministic_only=True,
                    )
                if routed is not None:
                    self._apply_learned_flags_safe(routed)
                    return routed

                reason = (
                    "classifier overruled on measurable geometry, but the "
                    "deterministic engine produced nothing on this page"
                )
                logger.warning("run_sheet: %r — %s", sheet_name, reason)
                if coverage is not None:
                    coverage.disposition = SKIPPED_CLASSIFIER
                    coverage.reason = reason
                return {
                    "_skipped": True,
                    "sheet_type": resolved_type,
                    "sheet_name": sheet_name,
                    "sheet_source": image_path,
                    "_skip_reason": reason,
                    "_skip_keyword": classifier_keyword,
                    "_skip_context": classifier_context,
                    "_measurable_signal": dict(signal),
                    "_classifier_overruled": True,
                }

            # The veto did not fire: nothing scaled and measurable on the page.
            # This is a legitimate skip — and it is now RECORDED, with the
            # keyword that decided it and the phrase that keyword landed in.
            measurable = sum(signal.values()) > 0
            disposition = SKIPPED_CLASSIFIER if measurable else NOT_APPLICABLE
            reason = (
                "classified %s by keyword %r%s"
                % (
                    resolved_type,
                    classifier_keyword,
                    "" if measurable else "; no measurable geometry on the page",
                )
            )
            logger.info(
                "run_sheet: skipping %r (%s, zero API cost) — %s",
                sheet_name, resolved_type, reason,
            )
            if coverage is not None:
                coverage.sheet_type = resolved_type
                coverage.disposition = disposition
                coverage.reason = reason
                coverage.measurable_signal = dict(signal)
            return {
                "_skipped": True,
                "sheet_type": resolved_type,
                "sheet_name": sheet_name,
                "sheet_source": image_path,
                "_skip_reason": reason,
                "_skip_keyword": classifier_keyword,
                "_skip_context": classifier_context,
                "_measurable_signal": dict(signal),
            }

        # Step 2.5 — deterministic-first routing (21-13). Vector plan sheets
        # never reach the vision extraction passes; raster plan sheets go to
        # the ensemble path. Routing failures degrade to the legacy flow.
        if (
            self._settings.deterministic_enabled
            and pdf_path is not None
            and page_index is not None
            and resolved_type in _DETERMINISTIC_SHEET_TYPES
        ):
            routed = self._route_deterministic(
                image_path=image_path,
                sheet_name=sheet_name,
                resolved_type=resolved_type,
                pdf_path=pdf_path,
                page_index=page_index,
                guard=guard,
                full_page_text=full_page_text,
            )
            if routed is not None:
                # Guardrail (21-16, V3-LEARN-04): prior human quantity
                # corrections attach re_verify flags AFTER fusion — never a
                # quantity substitution.
                self._apply_learned_flags_safe(routed)
                return routed
            # None → fall through to the legacy vision flow (e.g. a vector
            # schedule sheet where find_tables() found nothing).

        logger.info(
            "run_sheet: %r sheet_type=%r passes=%s", sheet_name, resolved_type, passes
        )

        # Step 3 — execute each pass
        count_result: dict    = {}
        measure_result: dict  = {}
        schedule_result: Optional[dict] = None
        legend_result: Optional[dict] = None

        # Build a manifest-driven targeted-count hint once (focuses the count pass
        # on the exact EA objects the user expects — big recall win for Bollards,
        # Columns, Stairs, etc.).
        count_hint = _build_count_hint(getattr(self, "_manifest", None))
        measure_hint = _build_measure_hint(getattr(self, "_manifest", None))
        # Learned-context injection point 1 (RESEARCH §6): the expected-items
        # + naming-conventions block joins the existing user_hint slot. It is
        # a HINT (data-delimited, length-capped) — cold start renders None
        # and the hints are exactly what they were before learning existed.
        learned_hint = None
        ctx = getattr(self, "_learned_context", None)
        if ctx is not None:
            try:
                learned_hint = ctx.render_prompt_hint()
            except Exception as exc:  # noqa: BLE001 — learning is additive
                logger.warning("run_sheet: learned prompt hint failed: %s", exc)
        count_hint = _join_hints(count_hint, learned_hint)
        measure_hint = _join_hints(measure_hint, learned_hint)
        # Dense symbol sheets benefit from a higher-resolution count render so
        # small repeated symbols stay legible.
        count_hires = resolved_type in ("floor_plan", "civil_site", "roof_plan")

        budget_exhausted = False
        try:
            for pass_type in passes:
                model_override = pick_model_for_pass(resolved_type, pass_type, sheet_name)
                render_scale = None
                pass_hint = None
                if (
                    pass_type in ("schedule", "legend")
                    and resolved_type == "floor_plan"
                    and pdf_path is not None
                    and page_index is not None
                ):
                    render_scale = 2.5
                elif (
                    pass_type == "count"
                    and count_hires
                    and pdf_path is not None
                    and page_index is not None
                ):
                    render_scale = 2.5
                    pass_hint = count_hint
                elif pass_type == "count":
                    pass_hint = count_hint
                elif pass_type == "measure":
                    pass_hint = measure_hint
                result = self._run_pass(
                    image_path,
                    sheet_name,
                    pass_type,
                    model_override,
                    sheet_type=resolved_type,
                    pdf_path=pdf_path,
                    page_index=page_index,
                    render_scale=render_scale,
                    user_hint=pass_hint,
                    budget=guard,
                )

                if pass_type == "count":
                    count_result = result
                    # Optional, gated: tiled recount to recover manifest count-objects
                    # the full-sheet pass missed (quantity null/0).
                    if (
                        count_tiling_enabled()
                        and getattr(self, "_manifest", None)
                        and pdf_path is not None
                        and page_index is not None
                    ):
                        count_result = self._tiled_recount(
                            count_result, pdf_path, page_index,
                            sheet_name, resolved_type, model_override,
                            budget=guard,
                        )
                elif pass_type == "measure":
                    measure_result = result
                elif pass_type == "schedule":
                    schedule_result = result
                    if (
                        resolved_type == "floor_plan"
                        and not (schedule_result or {}).get("schedules")
                        and pdf_path is not None
                        and page_index is not None
                    ):
                        logger.info(
                            "run_sheet: schedule pass empty on floor_plan %r — multi-region legend retry",
                            sheet_name,
                        )
                        combined_scheds: list = []
                        for region in ("bottom", "left", "right"):
                            retry = self._run_pass(
                                image_path,
                                sheet_name,
                                "schedule",
                                model_override,
                                sheet_type=resolved_type,
                                pdf_path=pdf_path,
                                page_index=page_index,
                                render_scale=2.5,
                                user_hint=_SCHEDULE_LEGEND_USER_HINT,
                                legend_region=region,
                                budget=guard,
                            )
                            combined_scheds.extend(retry.get("schedules") or [])
                        if combined_scheds:
                            schedule_result = {"schedules": combined_scheds}
                elif pass_type == "legend":
                    legend_result = result
                else:
                    logger.warning("run_sheet: unknown pass_type %r — result discarded", pass_type)
        except BudgetExceeded as exc:
            # Never a silent partial (Pitfall 7): remaining passes are
            # skipped, the sheet is flagged, and the run continues to
            # reporting with the results already paid for.
            budget_exhausted = True
            logger.warning(
                "run_sheet: %r — API budget exhausted mid-sheet (%s); "
                "remaining passes skipped and sheet flagged", sheet_name, exc,
            )

        # Step 4 — merge
        merged = merge_passes(count_result, measure_result, schedule_result)
        if legend_result and legend_result.get("schedules"):
            merged["schedules"] = _merge_schedule_lists(
                merged, {"schedules": []}, legend_result
            )
        merged = apply_accuracy_rules(merged)

        if full_page_text:
            try:
                from bobbytailor.pipeline.page_text_enrichment import enrich_components_from_page_text
                merged = enrich_components_from_page_text(merged, full_page_text)
            except ImportError:
                pass

        # Vector-geometry measurement assist (floor/site/roof sheets only).
        # Provides scale + measured linework/footprint as a verification reference
        # — accurate when a reliable scale is supplied, flagged otherwise.
        if (
            resolved_type in ("floor_plan", "civil_site", "roof_plan")
            and pdf_path is not None
            and page_index is not None
        ):
            geom = self._measure_geometry_safe(
                pdf_path, page_index, merged.get("scale"),
            )
            if geom is not None:
                merged["_geometry"] = geom

        # Attach pipeline metadata
        merged["_source_sheet"] = image_path
        merged["_sheet_type"]   = resolved_type
        merged["_sheet_name"]   = sheet_name
        merged["_passes_run"]   = passes

        if budget_exhausted:
            merged["_budget_exhausted"] = True
            merged["needs_review"] = True
            merged["review_reason"] = "budget_exhausted"
            for comp in merged.get("components") or []:
                if isinstance(comp, dict):
                    comp["needs_review"] = True
                    comp["review_reason"] = _append_reason(
                        comp.get("review_reason"), "budget_exhausted"
                    )
        merged["_budget"] = _budget_state(guard)

        # Guardrail (21-16, V3-LEARN-04): re_verify flags for previously
        # human-corrected items — quantities are never substituted.
        self._apply_learned_flags_safe(merged)

        return merged

    def _apply_learned_flags_safe(self, merged: dict) -> None:
        """Attach learned re_verify flags to a sheet result — never fatal.

        Enforces the RESEARCH §6 anti-amplification guardrail via
        :func:`apply_learned_quantity_flags` (module-level import —
        patchable): a learned value can NEVER overwrite a quantity whose
        provenance is geometry/text_layer with HIGH confidence; prior human
        quantity corrections surface as re_verify flags only.
        """
        ctx = getattr(self, "_learned_context", None)
        if ctx is None or not isinstance(merged, dict):
            return
        try:
            apply_learned_quantity_flags(merged.get("components") or [], ctx)
        except Exception as exc:  # noqa: BLE001 — learning is additive
            logger.warning("run_sheet: learned quantity flags failed: %s", exc)

    # ------------------------------------------------------------------
    # Deterministic-first orchestration (21-13, V3-ACC-01/03)
    # ------------------------------------------------------------------

    def _route_deterministic(
        self,
        *,
        image_path: str,
        sheet_name: str,
        resolved_type: str,
        pdf_path: str,
        page_index: int,
        guard: BudgetGuard,
        full_page_text: str = "",
        deterministic_only: bool = False,
    ) -> Optional[dict]:
        """Dispatch a deterministic-eligible sheet to the vector or raster flow.

        Returns None to fall back to the legacy vision flow (routing failure
        or a vector schedule sheet with no deterministic tables). Exceptions
        inside a branch degrade per-sheet to the error-dict convention —
        never crash the run (threat model: untrusted PDF flow).

        Args:
            deterministic_only: When True, the raster branch is refused and
                None is returned instead. The raster branch is the ENSEMBLE
                VISION path — it costs real money. The skip veto sets this,
                because recovering sheets a keyword had already discarded must
                never turn into unbudgeted spend on a scanned drawing set
                (INV-08 risk 1). On a raster page there is no deterministic
                geometry to recover, so the honest outcome is the recorded
                skip, not a vision call.
        """
        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:  # noqa: BLE001 — unreadable PDF → legacy flow
            logger.warning(
                "run_sheet: %r — cannot open %s for deterministic flow (%s); "
                "legacy vision flow used", sheet_name, pdf_path, exc,
            )
            return None
        try:
            try:
                page = doc[page_index]
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "run_sheet: %r — page %s unavailable (%s); legacy flow used",
                    sheet_name, page_index, exc,
                )
                return None

            raster = self._settings.raster_force or not is_vector_sheet(page)
            if raster and deterministic_only:
                logger.info(
                    "run_sheet: %r — raster page, and the caller requires a "
                    "deterministic-only route; refusing the vision ensemble "
                    "(zero API)", sheet_name,
                )
                return None
            if raster:
                if resolved_type not in _PLAN_SHEET_TYPES:
                    # Raster schedule sheets: vision reads the table image —
                    # the raster estimate schema has no row structure.
                    return None
                try:
                    return self._run_sheet_raster(
                        image_path, sheet_name, resolved_type, guard,
                    )
                except Exception as exc:  # noqa: BLE001 — per-sheet degradation
                    logger.warning(
                        "run_sheet: %r — raster ensemble flow failed: %s",
                        sheet_name, exc,
                    )
                    return self._error_result(
                        image_path, sheet_name, resolved_type, exc, "raster"
                    )

            if resolved_type == "schedule" and not self._sheet_schedules(
                doc, pdf_path, page_index
            ):
                # find_tables() found nothing — vision reconciles the layout
                # (RESEARCH §3 handoff 4); quantities remain printed strings.
                logger.info(
                    "run_sheet: %r — no deterministic tables on schedule "
                    "sheet; legacy vision schedule pass used", sheet_name,
                )
                return None

            try:
                return self._run_sheet_vector(
                    page=page,
                    doc=doc,
                    image_path=image_path,
                    sheet_name=sheet_name,
                    resolved_type=resolved_type,
                    pdf_path=pdf_path,
                    page_index=page_index,
                    guard=guard,
                )
            except Exception as exc:  # noqa: BLE001 — per-sheet degradation
                logger.warning(
                    "run_sheet: %r — vector deterministic flow failed: %s",
                    sheet_name, exc,
                )
                return self._error_result(
                    image_path, sheet_name, resolved_type, exc, "vector"
                )
        finally:
            doc.close()

    @staticmethod
    def _error_result(
        image_path: str,
        sheet_name: str,
        resolved_type: str,
        exc: Exception,
        mode: str,
    ) -> dict:
        """Per-sheet error dict (existing degradation convention, 03-01)."""
        return {
            "error": str(exc),
            "measurement_mode": mode,
            "_source_sheet": image_path,
            "_sheet_name": sheet_name,
            "_sheet_type": resolved_type,
            "_tokens_in": 0,
            "_tokens_out": 0,
            "_cost_usd": 0.0,
        }

    def _sheet_schedules(self, doc, pdf_path: Optional[str], page_index: int) -> list:
        """Deterministic schedule tables on one page (whole-doc scan cached)."""
        key = pdf_path or ""
        if key not in self._schedules_cache:
            try:
                self._schedules_cache[key] = list(extract_schedules(doc))
            except Exception as exc:  # noqa: BLE001 — tables are additive
                logger.warning("deterministic schedule extraction failed: %s", exc)
                self._schedules_cache[key] = []
        return [
            s
            for s in self._schedules_cache[key]
            if _sched_field(s, "page_index", 0) == page_index
        ]

    # A unit key plan identifies itself by its own printed DRAWING TITLE — the
    # title bound to a scale callout, not stray page text. Moxy pages 7 and 8
    # title four and three drawings "LEVEL nn KEY PLAN" at 3/32" = 1'-0", and
    # no other sheet in any of the four real sets titles a drawing that way.
    # Page index 3 prints the words KEY PLAN in its title block and is NOT
    # selected, because its drawing titles are building elevations — which is
    # exactly why the test is the drawing title and not a text search.
    _KEY_PLAN_TITLE_RE = re.compile(r"\bKEY\s+PLANS?\b", re.IGNORECASE)

    def _unit_key_plan_pages(self, doc) -> List[int]:
        """Page indices whose own drawing titles name a key plan.

        Deciding which sheet keys the units is sheet CLASSIFICATION, which is
        why ``room_tags.derive_room_mix`` refuses to guess it and takes the
        scope from here (23-05 deviation 2). Returning ``[]`` is a valid answer
        — Crow, Bob's and Chelsea have no key plan at all — and the resolver
        then falls back to the manifest with that stated.
        """
        pages: List[int] = []
        for index in range(int(getattr(doc, "page_count", 0) or 0)):
            try:
                scales = extract_printed_scales(doc[index]) or []
            except Exception as exc:  # noqa: BLE001 — selection is additive
                logger.debug("key-plan title read failed on page %s: %s", index, exc)
                continue
            for scale in scales:
                title = str(getattr(scale, "title", "") or "")
                if self._KEY_PLAN_TITLE_RE.search(title):
                    pages.append(index)
                    break
        return pages

    def _document_plan_titles(self, doc) -> List[str]:
        """Every prototype drawing title in the set (the full, spelled-out names).

        These are the names a key plan's tag may be an abbreviation OF — the
        drawing's own vocabulary on both sides, so a plans-only run reaches the
        same answer with no manifest present.
        """
        from bobbytailor.deterministic.room_fill import plan_titles  # noqa: PLC0415

        names: List[str] = []
        seen = set()
        for index in range(int(getattr(doc, "page_count", 0) or 0)):
            try:
                titles = plan_titles(doc[index]) or []
            except Exception as exc:  # noqa: BLE001 — additive
                logger.debug("plan-title read failed on page %s: %s", index, exc)
                continue
            for entry in titles:
                name = str((entry[0] if entry else "") or "").strip()
                key = name.lower()
                if name and key not in seen:
                    seen.add(key)
                    names.append(name)
        return names

    def _project_datum_span(self, pages) -> Optional[float]:
        """The largest elevation datum span (ft) printed anywhere in the set.

        Scans every page's printed-scale callouts for exterior elevation
        titles, harvests each elevation's datum ladder from the band between
        consecutive callouts, and returns the MAX (top datum − finish floor)
        span — the parapet of the tallest facade, which is THE wall height
        the exterior envelope is built to. Zero API; text only.

        ``None`` when no elevation prints a usable ladder (Bob's has no
        datums at all; Moxy's civic ladder is sea-level based and yields no
        band), in which case the resolver behaves exactly as it did before
        23-14. Any failure is swallowed for the same reason.
        """
        from bobbytailor.deterministic.room_fill import (  # noqa: PLC0415
            datum_wall_band,
            elevation_datums,
            elevation_titles,
        )

        pdf_path = next(
            (p.get("pdf_path") for p in pages or [] if p.get("pdf_path")), None
        )
        if not pdf_path:
            return None
        spans: List[float] = []
        try:
            doc = fitz.open(pdf_path)
        except Exception:  # noqa: BLE001 — the span is additive
            return None
        try:
            for index in range(int(getattr(doc, "page_count", 0) or 0)):
                try:
                    page = doc[index]
                    entries = [
                        e for e in elevation_titles(page)
                        if e.orientation and not e.is_demo and not e.is_interior
                    ]
                    for e in entries:
                        y0c = e.callout_bbox_pt[1]
                        prev = 0.0
                        for o in entries:
                            if o.callout_bbox_pt[3] <= y0c and o.callout_bbox_pt[3] > prev:
                                prev = o.callout_bbox_pt[3]
                        clip = fitz.Rect(0.0, prev, page.rect.width, y0c)
                        band = datum_wall_band(elevation_datums(page, clip))
                        if band is not None:
                            spans.append(band[2])
                except Exception as exc:  # noqa: BLE001 — per-page degradation
                    logger.debug("datum-span scan failed on page %s: %s", index, exc)
        finally:
            doc.close()
        return round(max(spans), 2) if spans else None

    def _resolve_room_mix(self, manifest, doc, pdf_path: Optional[str] = None):
        """The unit mix actually used, with the SOURCE of every count (D-10).

        Two sources, one precedence: the in-plan unit-tag census read off the
        drawing set's own key plans WINS wherever it has a count, the manifest
        fills only the names the drawings never state, and a disagreement
        between them is FLAGGED naming both numbers and both sources rather than
        resolved in silence. ``human_inputs/*.json`` is never edited — the four
        Moxy ``unit_count``s a suite's "2 doors" inflated stay exactly as the
        estimator wrote them, and are surfaced instead.

        A census that refuses (duplicate room numbers ⇒ the censused sheets
        overlap) falls back to the manifest WHOLESALE with the refusal named. A
        partial census is never published: a wrong multiplier is not one wrong
        line item, it multiplies Gyp Ceiling, Gyp Wall, Guestroom-Wall Covering
        and Doors at once (threat T-23-18).

        Computed ONCE per document and cached: the census reads two sheets, but
        selecting them reads every sheet's drawing titles.
        """
        from bobbytailor.deterministic.room_tags import (  # noqa: PLC0415
            derive_room_mix,
            resolve_room_mix,
        )
        from bobbytailor.deterministic.tag_pairing import (  # noqa: PLC0415
            sheet_mask_rects,
        )

        cache_key = pdf_path or (id(doc) if doc is not None else "")
        cached = self._room_mix_cache.get(cache_key)
        if cached is not None:
            return cached

        manifest_counts = _manifest_unit_counts(manifest)
        alias_targets: List[str] = list(manifest_counts)
        census = None
        if doc is not None:
            try:
                pages = self._unit_key_plan_pages(doc)
                if pages:
                    masks = {p: sheet_mask_rects(doc[p]) for p in pages}
                    census = derive_room_mix(
                        doc, pages=pages, mask_rects_by_page=masks
                    )
                    alias_targets.extend(self._document_plan_titles(doc))
            except Exception as exc:  # noqa: BLE001 — census is additive
                # A swallowed census is not a census that found nothing. The
                # resolver flags the absence either way, so the run says so.
                logger.warning("in-plan unit-tag census failed: %s", exc)
                census = None

        resolution = resolve_room_mix(manifest_counts, census, alias_targets)
        if resolution.flags:
            logger.info(
                "room mix resolved: %d count(s), %d flag(s) — %s",
                len(resolution.counts), len(resolution.flags), resolution.flags[0],
            )
        self._room_mix_cache[cache_key] = resolution
        return resolution

    def _deterministic_bundle(
        self,
        page,
        doc,
        pdf_path: str,
        page_index: int,
        sheet_name: str,
        resolved_type: str,
    ) -> dict:
        """Build the per-sheet deterministic candidate bundle (fuse_sheet input).

        Order: schedules (mask input) → viewports → dimension samples →
        per-viewport RANSAC scale solve → main-plan selection →
        resolve_scale_v2 → walls / rooms / symbols (plan sheets with a
        solved scale only) → printed-dims footprint.
        """
        schedules = self._sheet_schedules(doc, pdf_path, page_index)
        table_bboxes = [_sched_field(s, "bbox_pt", None) for s in schedules]
        table_bboxes = [b for b in table_bboxes if b]

        viewports = segment_viewports(page, table_bboxes=table_bboxes or None)
        mask_rects = [
            vp.bbox_pt for vp in viewports if vp.kind in _MASK_VIEWPORT_KINDS
        ]

        samples = extract_dimension_samples(
            page, exclude_rects=mask_rects, page_index=page_index, doc=doc
        )

        printed_by_region = _viewport_printed_fpi(page, viewports)
        viewports_with_scales = []
        for vp in viewports:
            if vp.kind in _MASK_VIEWPORT_KINDS:
                viewports_with_scales.append((vp, solve_viewport_scale([], vp)))
                continue
            viewports_with_scales.append(
                (
                    vp,
                    solve_viewport_scale(
                        samples, vp, printed_fpi=printed_by_region.get(vp.region_id)
                    ),
                )
            )

        main_id = select_main_plan(viewports_with_scales)

        # PRIMARY scale source: the drawing's OWN printed scale label. Read the
        # printed labels, bind each to its viewport, and identify the main-plan
        # label. Fully additive — any failure yields empty results and the
        # RANSAC path below behaves exactly as before.
        printed_scales_by_region: dict = {}
        main_plan_printed = None
        try:
            printed_list = extract_printed_scales(page)
            printed_scales_by_region = match_scales_to_viewports(
                printed_list, viewports, page=page
            )
            main_plan_printed = identify_main_plan_scale(printed_list)
        except Exception as exc:  # noqa: BLE001 — printed scale is additive
            logger.debug("printed-scale reading failed on %r: %s", sheet_name, exc)

        # Learned-context injection point 3a (RESEARCH §6): the learned
        # scale prior feeds resolve_scale_v2, which ranks it LAST (21-07) —
        # it fires only when the printed, solved AND printed-heuristic tiers
        # are empty, so a learned scale can never displace deterministic
        # evidence.
        scale = resolve_scale_v2(
            page,
            viewports_with_scales,
            override_feet_per_inch=getattr(self, "_scale_fpi", None),
            learned_prior=_learned_scale_prior(
                getattr(self, "_learned_context", None), sheet_name
            ),
            printed_scales=printed_scales_by_region,
            main_plan_scale=main_plan_printed,
        )
        fpp = float(scale.feet_per_point or 0.0)

        main_bbox = None
        for vp, _vs in viewports_with_scales:
            if vp.region_id == main_id:
                main_bbox = vp.bbox_pt
                break

        # ── Multi-scale page guard (V3-ACC: one page, many drawing scales) ───
        # A sheet routinely carries the main plan (e.g. 1" = 40'-0") AND detail
        # viewports at their own, far larger scale (e.g. 1 1/2" = 1'-0"). Every
        # quantity below is computed at the ONE resolved page scale, so linework
        # inside an off-scale viewport is measured with the wrong fpp — Crow
        # page 0's four S.C.C.P. details are 60x off — and pollutes the wall
        # classes and symbol clusters with junk take-off rows. A detail is also
        # a BLOW-UP of an object already counted on the plan, so counting it
        # would double-count. Exclude any viewport whose OWN printed scale
        # disagrees with the resolved page scale (deterministic; a viewport with
        # no printed scale of its own is left alone).
        #
        # The exclusion is CORRECT and, until now, invisible: it existed as a
        # logger.info and nothing more (INV-08 §1.4 — the returned bundle had no
        # `excluded_viewports` key, so no consumer could ever surface it). A
        # client cannot see that four S.C.C.P. details were DELIBERATELY not
        # measured, which is indistinguishable from the app failing to find
        # them. Each exclusion now leaves a DrawingCoverage on the bundle.
        geometry_mask = list(mask_rects)
        excluded_viewports: List[DrawingCoverage] = []
        coverage_drops: List[DrawingCoverage] = []
        resolved_fpp = fpp
        if resolved_fpp > 0:
            for vp in viewports:
                ps = printed_scales_by_region.get(vp.region_id)
                if ps is None:
                    continue
                vp_fpp = float(getattr(ps, "feet_per_point", 0.0) or 0.0)
                if vp_fpp <= 0:
                    continue
                if abs(vp_fpp - resolved_fpp) > _SCALE_MATCH_TOL * resolved_fpp:
                    geometry_mask.append(vp.bbox_pt)
                    ratio = max(vp_fpp, resolved_fpp) / min(vp_fpp, resolved_fpp)
                    reason = (
                        "its printed scale %.4f ft/pt differs from the resolved "
                        "page scale %.4f ft/pt; measuring it at the page scale "
                        "would be %.0fx wrong, so it was deliberately excluded — "
                        "this is NOT a failed measurement"
                        % (vp_fpp, resolved_fpp, ratio)
                    )
                    excluded_viewports.append(
                        DrawingCoverage(
                            region_id=vp.region_id,
                            title=getattr(ps, "title", "") or vp.kind,
                            disposition=EXCLUDED_OFF_SCALE,
                            reason=reason,
                            printed_scale_fpi=round(vp_fpp * 72.0, 4),
                        )
                    )
                    logger.info(
                        "sheet %r: excluding off-scale viewport %s (%s) — %s",
                        sheet_name, vp.region_id,
                        getattr(ps, "title", "") or vp.kind, reason,
                    )

        walls: list = []
        wall_lf: dict = {}
        rooms: list = []
        symbols: list = []
        if resolved_type in _PLAN_SHEET_TYPES and fpp <= 0:
            # Every quantity below is gated on a positive feet-per-point, so an
            # unsolved scale silently leaves walls/rooms/symbols empty — a plan
            # sheet that measured NOTHING is reported identically to a plan
            # sheet with nothing on it (INV-08 §2 row S5). Record the reason.
            coverage_drops.append(
                DrawingCoverage(
                    region_id="page",
                    title=sheet_name,
                    disposition=SKIPPED_NO_SCALE,
                    reason="no drawing scale could be resolved for this %s sheet "
                           "(feet-per-point resolved to %r) — walls, rooms and "
                           "symbols were not measured, which is NOT the same as "
                           "measuring zero of them" % (resolved_type, fpp),
                )
            )
        if resolved_type in _PLAN_SHEET_TYPES and fpp > 0:
            walls = extract_walls(page, fpp, exclude_rects=geometry_mask)
            wall_lf = wall_lf_by_class(walls, fpp)
            rooms = extract_rooms(page, walls, main_bbox, fpp)
            symbols = cluster_symbols(
                page, fpp, exclude_rects=geometry_mask, doc=doc, page_index=page_index
            )

        # ── Structural grid lattices (additive, never touches symbols.py) ────
        #
        # cluster_symbols SHATTERS a marker lattice it can physically see: the
        # marker edges share a style class with the gridlines, and a gridline
        # dash endpoint lands 0.805 pt from a marker corner — inside
        # ENDPOINT_EPS_PT — so the dash unions into the component and the shape
        # signature depends on how much dash happened to attach. Crow page 0's
        # 120 column markers come back as SYM-2 (56) plus three fragments plus
        # 53 clusters below MIN_INSTANCES.
        #
        # This asks the same primitives a different, position-first question,
        # and it fires on exactly one page across all 83 pages of the four plan
        # sets (see tests/test_grid_lattice.py).
        #
        # The suppression matters as much as the detection: SYM-2's 56
        # instances ARE 56 of these markers, and the semantic pass named them
        # "Bollards" — the whole of the reported "Bollards 56 vs 28" defect.
        # Publishing the lattice AND the fragment would count the same drawn
        # objects twice.
        lattices: list = []
        if resolved_type in _PLAN_SHEET_TYPES and fpp > 0:
            lattices = detect_grid_lattices(
                page, fpp, exclude_rects=geometry_mask, doc=doc,
                page_index=page_index,
            )
            if lattices:
                shadowed = set(lattice_shadowed_symbol_ids(symbols, lattices))
                if shadowed:
                    logger.info(
                        "sheet %r: %d symbol group(s) %s are grid-lattice "
                        "markers already counted by %s — dropped so the same "
                        "geometry is not published twice",
                        sheet_name, len(shadowed), sorted(shadowed),
                        ", ".join(g.candidate_id for g in lattices),
                    )
                    symbols = [
                        g for g in symbols
                        if getattr(g, "candidate_id", None) not in shadowed
                    ]
                symbols = list(symbols) + [
                    _lattice_as_symbol_group(g, fpp) for g in lattices
                ]

        # ── Placed keynotes (additive, same adapter contract as the lattice) ──
        #
        # The detector below has been green in tests since 28-06 and had ZERO
        # callers on the plan path: `keynote_tags` is consumed only by the
        # elevation facade route, so a floor plan read its keynote legend and
        # threw the answer away. That is why the first paid run of the post-28
        # engine (2026-08-16) predicted "Ladder = 1, PASS expected" and
        # published nothing at all — a wiring gap, not a detection gap.
        #
        # A keynote bubble is the sheet's own pointer from a drawn thing to the
        # sheet's own words for it, so unlike every symbol cluster this count
        # arrives already anchored. What it is NOT is a count of objects when
        # the note states a requirement instead of naming a thing
        # (is_specification_note) — those are dropped, and the honest blank is
        # kept over a confidently wrong 1.
        keynote_callouts: list = []
        if resolved_type in _PLAN_SHEET_TYPES and fpp > 0 and symbols:
            try:
                from bobbytailor.deterministic.room_fill import (  # noqa: PLC0415
                    is_specification_note,
                    keynote_callout_counts,
                )

                published, refused = [], []
                for callout in keynote_callout_counts(page, symbols):
                    if callout.callout_count <= 0:
                        continue
                    if is_specification_note(callout.note_text):
                        refused.append(callout)
                    else:
                        published.append(callout)
                for c in refused:
                    logger.info(
                        "sheet %r: keynote %s placed %d time(s) is NOT published "
                        "as a count — %r states a requirement, not an object",
                        sheet_name, c.number, c.callout_count, c.note_text,
                    )
                if published:
                    # The per-number counts were split OUT of the bubble group,
                    # so publishing both counts the same drawn marks twice —
                    # the lattice_shadowed_symbol_ids contract. And that group
                    # is annotations either way: nobody buys a keynote bubble.
                    bubble_ids = {
                        c.source_candidate_id for c in published
                        if c.source_candidate_id
                    }
                    # `symbols` is rebound ONCE, at the end, so a raise anywhere
                    # above leaves the sheet exactly as it was measured.
                    kept = [
                        g for g in symbols
                        if getattr(g, "candidate_id", None) not in bubble_ids
                    ] + [
                        _keynote_callout_as_symbol_group(c, fpp) for c in published
                    ]
                    logger.info(
                        "sheet %r: published %d placed keynote(s) as flagged "
                        "counts (%s); dropped bubble group(s) %s",
                        sheet_name, len(published),
                        ", ".join(
                            "KEY-%s×%d" % (c.number, c.callout_count)
                            for c in published
                        ),
                        sorted(bubble_ids) or "none",
                    )
                    symbols = kept
                    keynote_callouts = published
            except Exception as exc:  # noqa: BLE001 — additive: never break a run
                logger.debug(
                    "keynote callout wiring failed on %r: %s", sheet_name, exc
                )

        footprint = None
        if resolved_type in _PLAN_SHEET_TYPES:
            try:
                footprint = footprint_from_page(
                    page, page_index=page_index, sheet_name=sheet_name
                )
            except Exception as exc:  # noqa: BLE001 — footprint is additive
                logger.debug("footprint_from_page failed on %r: %s", sheet_name, exc)
        # The most recent trustworthy footprint is kept for the elevation
        # width cross-check (23-14): a facade blob's width is validated
        # against the floor plan's INDEPENDENTLY measured dimension — two
        # measurements sharing no code path, no sheet and no scale. A
        # high-confidence footprint is never displaced by a weaker one.
        if footprint is not None:
            stored = getattr(self, "_project_footprint", None)
            if stored is None or (
                str(getattr(footprint, "confidence", "")) == "high"
                and str(getattr(stored, "confidence", "")) != "high"
            ):
                self._project_footprint = footprint

        # Enclosed-region room measurement (Recipe E). The centerline
        # polygonization above returns nothing usable on drawing styles that
        # render rooms as loose strokes (Moxy: 17 SF fragments where the room is
        # 353 SF, and no closed room path exists at all), so measure each
        # drawing viewport as a filled region AT ITS OWN PRINTED SCALE. Additive:
        # any failure leaves `room_fills` empty and the sheet behaves as before.
        #
        # NOT gated on the sheet-level type. A sheet is not one thing — it is a
        # COLLECTION of drawings, and the sheet type is only its dominant one.
        # Moxy's guestroom prototypes carry interior elevations AND the AR/RCP
        # plans that hold every guestroom quantity, so they classify "elevation"
        # and a plan-type gate skips exactly the drawings that matter. The
        # measurement gates on what is actually present: a titled plan viewport
        # with its own printed scale (see _measure_room_fills).
        room_fills: list = []
        try:
            room_fills, fill_drops = self._measure_room_fills(
                page, viewports, printed_scales_by_region, sheet_name
            )
            coverage_drops.extend(fill_drops)
        except Exception as exc:  # noqa: BLE001 — measurement is additive
            # A logger.debug is not a record. Losing EVERY fill on a sheet to a
            # swallowed exception is INV-08 §2 row S7, and it is the difference
            # between "this building has no guestroom ceilings" and "we crashed
            # measuring them".
            logger.debug("room_fill failed on %r: %s", sheet_name, exc)
            coverage_drops.append(
                DrawingCoverage(
                    region_id="page",
                    title=sheet_name,
                    disposition=ERRORED,
                    reason="enclosed-region measurement raised %s: %s — every "
                           "drawing on this sheet is unmeasured, not zero"
                           % (type(exc).__name__, exc),
                )
            )

        # Elevation facade measurement (23-14). Anchored on elevation-titled
        # printed-scale callouts, measured as complement-labelled silhouettes
        # at each callout's OWN scale, cropped to each drawing's own datum
        # band. Additive: any failure leaves `elevation_areas` empty and the
        # sheet behaves as before. NOT gated on the sheet type, for the same
        # reason room fills are not — Chelsea puts nine elevations on sheets
        # typed floor_plan — and NOT gated on _PLAN_SHEET_TYPES, which stays
        # exactly what it was so wall pairing can never run on a facade.
        elevation_areas: list = []
        try:
            elevation_areas, elev_drops = self._measure_elevation_areas(
                page, viewports, sheet_name
            )
            coverage_drops.extend(elev_drops)
        except Exception as exc:  # noqa: BLE001 — measurement is additive
            logger.debug("elevation measurement failed on %r: %s", sheet_name, exc)
            coverage_drops.append(
                DrawingCoverage(
                    region_id="page",
                    title=sheet_name,
                    disposition=ERRORED,
                    reason="elevation facade measurement raised %s: %s — every "
                           "elevation on this sheet is unmeasured, not zero"
                           % (type(exc).__name__, exc),
                )
            )

        # Open linear runs (23-15). UNGATED BY SHEET TYPE — the sheet holding
        # Crow's rails classifies as a detail, so a plan-type gate would skip
        # the ONLY sheet they are on. Additive: any failure leaves the list
        # empty and the sheet behaves as before. The runs land in the
        # candidate registry so a run is groundable like every other
        # candidate; basis `linear` finally has a consumer
        # (fusion BASIS_BINDERS["linear"]).
        linear_runs: list = []
        sheet_linear_phrases: list = []
        shx_labels: list = []
        try:
            linear_runs, sheet_linear_phrases, shx_labels = (
                self._measure_linear_runs(
                    page, doc, viewports, printed_scales_by_region,
                    sheet_name, fpp,
                )
            )
        except Exception as exc:  # noqa: BLE001 — measurement is additive
            logger.debug("linear-run measurement failed on %r: %s",
                         sheet_name, exc)
            coverage_drops.append(
                DrawingCoverage(
                    region_id="page",
                    title=sheet_name,
                    disposition=ERRORED,
                    reason="open linear-run measurement raised %s: %s — every "
                           "linear run on this sheet is unmeasured, not zero"
                           % (type(exc).__name__, exc),
                )
            )

        # Finish/material callouts (INV-05 §2 Key A). The masks the bundle
        # already computed are MANDATORY here — a door-schedule tag column and a
        # legend key look exactly like a plan-body callout (threat T-23-30).
        #
        # NOT gated on the sheet type. Every wall-covering quantity in the Moxy
        # take-off lives on an interior-elevation sheet, those sheets classify
        # as elevations, and a plan-type gate would skip precisely the sheets
        # holding the entire quantity. Additive: any failure leaves the list
        # empty and the sheet behaves exactly as before.
        material_tags: list = []
        try:
            material_tags = extract_material_tags(
                page,
                mask_rects=list(table_bboxes) + list(mask_rects),
                page_index=page_index,
            )
        except Exception as exc:  # noqa: BLE001 — material tags are additive
            logger.debug("material-tag reading failed on %r: %s", sheet_name, exc)

        bundle = {
            "symbol_groups": symbols,
            # Full lattice evidence — cell ids, occupancy, printed axis labels
            # and the flagged completion hypotheses. The SymbolGroup above
            # carries the COUNT; this carries why anyone should believe it, and
            # what the drawing declines to say.
            "grid_lattices": [g.to_dict() for g in lattices],
            # The keynotes that became KEY-<n> candidates above, with the
            # legend bubble and the placed bubbles they were counted from —
            # the evidence for a number that a reviewer has to be able to
            # check against the sheet in seconds.
            "keynote_callouts": [c.to_dict() for c in keynote_callouts],
            "walls": walls,
            "wall_lf_by_class": wall_lf,
            "rooms": rooms,
            "room_fills": room_fills,
            "elevation_areas": elevation_areas,
            # Open linear runs (23-15) + the sheet's own naming context for
            # the linear binder: note phrases and SHX comment annotations.
            "linear_runs": linear_runs,
            "sheet_linear_phrases": sheet_linear_phrases,
            "shx_labels": shx_labels,
            # The most recent trustworthy footprint from ANOTHER sheet — the
            # independent side of the elevation cross-check (D-11: the
            # perimeter x datum-height route FLAGS disagreement; it never
            # publishes a second quantity).
            "reference_footprint": getattr(self, "_project_footprint", None),
            "material_tags": material_tags,
            "viewports": viewports,
            "schedules": schedules,
            "footprint": footprint,
            "fpp": fpp,
            "sheet_name": sheet_name,
            # Additive coverage keys. `excluded_viewports` is the DELIBERATE
            # off-scale exclusion (correct, and previously log-only);
            # `coverage_drops` is every drawing this sheet SAW — what it failed
            # to measure, each with a named reason, and since 29-05 what it
            # measured, so `drawings_measured` can be something other than the
            # 0 it read on every saved run. The key keeps its name: it is the
            # ledger's `drawings` list under an older one, and renaming it
            # moves no number. No existing key is renamed or removed.
            "excluded_viewports": excluded_viewports,
            "coverage_drops": coverage_drops,
            # The schedule-table / title-block / legend rectangles this sheet
            # already computed, PUBLISHED on the bundle (24-04). Three readers
            # above consume them and every one of them had to be handed the
            # list explicitly; fusion cannot be, because it never sees the page.
            # Without them the room gate's masked-origin rule (T-24-15) would be
            # a mitigation that never runs. Same list, same computation — this
            # is a publication, not a second derivation.
            "mask_rects": [tuple(b) for b in table_bboxes] + [
                tuple(m) for m in mask_rects
            ],
            "_viewports_with_scales": viewports_with_scales,
            "_main_plan_region": main_id,
            "_scale_result": scale,
        }

        # Per-candidate text anchors (24-01, V4-DET-01). Computed HERE, before
        # any vision call, so every symbol group, room and wall thickness class
        # carries the words the drawing itself printed next to it — or a
        # recorded absence. A candidate with no anchor is never named from its
        # shape; plan 24-04 owns what happens to it.
        #
        # The masks assembled at the top of this method are MANDATORY, not
        # optional (threat T-24-02): without them a door-schedule tag column is
        # indistinguishable from a plan-body callout.
        #
        # Additive and fully guarded, exactly like `extract_material_tags`
        # above: any failure leaves the bundle byte-identical to before this
        # key existed and the sheet still measures.
        try:
            bundle["candidate_anchors"] = anchors_for_candidates(
                page,
                self._anchor_candidate_map(bundle),
                mask_rects=list(table_bboxes) + list(mask_rects),
            )
        except Exception as exc:  # noqa: BLE001 — anchors are additive
            logger.debug("anchor computation failed on %r: %s", sheet_name, exc)
            bundle["candidate_anchors"] = {}

        return bundle

    @staticmethod
    def _anchor_candidate_map(bundle: dict) -> dict:
        """``{candidate_id: bbox_pt}`` for every nameable candidate in *bundle*.

        Built from ``fusion.build_registry`` rather than re-deriving three bbox
        rules here, so a wall class is named exactly as ``_wall_candidate_id``
        names it and a room bbox is the same polygon bound fusion will ground
        against. Viewport regions are excluded: a region is a place on the
        sheet, not an object anyone names.

        A registry bbox of all zeros means "this class has no segment records",
        i.e. position UNKNOWN — never position (0, 0). Such a candidate is
        passed through with an empty bbox so it earns a recorded absence
        instead of harvesting whatever text sits at the page origin.
        """
        wanted = ("symbol_group", "wall_class", "room")
        out: dict = {}
        for cid, entry in (build_registry(bundle) or {}).items():
            if (entry or {}).get("kind") not in wanted:
                continue
            bbox = tuple(entry.get("bbox_pt") or ())
            if len(bbox) != 4 or (
                bbox[2] - bbox[0] == 0.0 and bbox[3] - bbox[1] == 0.0
            ):
                bbox = ()
            out[str(cid)] = bbox

        # A dict-shaped symbol group carries `bbox_pt` where the dataclass
        # carries `representative_bbox_pt`; `_sched_field` reads both alike.
        for group in bundle.get("symbol_groups") or []:
            cid = _sched_field(group, "candidate_id", "")
            if not cid or out.get(cid):
                continue
            rep = _sched_field(group, "representative_bbox_pt", None)
            if not rep:
                rep = _sched_field(group, "bbox_pt", None)
            if rep:
                out[str(cid)] = tuple(rep)
        return out

    # There is deliberately NO plausible-single-unit constant here any more
    # (23-11 / V4-MEAS-02). The 900 SF bound that used to live at this line was
    # a guest-room-shaped number — correct for a guest room, wrong for a lobby —
    # and it was applied on the WRONG SIDE of the room-mix multiplication, so it
    # never saw the quantity that was actually wrong (INV-02 §5). It is replaced
    # by room_fill.cross_check_extent, a scale-free RATIO against the drawing's
    # OWN printed overall dimensions. Re-introducing a size in square feet here
    # would re-introduce the defect.

    # A drawing occupies the space ABOVE its scale callout. These bound the clip
    # around one callout; the generic viewport segmentation cuts a unit plan into
    # several regions (Moxy ID-411 -> 167 + 65 + 41 SF instead of one 342 SF
    # unit), so the callout is the reliable anchor for "one drawing".
    _FILL_CLIP_UP_PT = 620.0
    # Same value, one definition: the skip veto, the coverage ledger and
    # scripts/coverage_probe.py bind a title to its scale callout with exactly
    # the rule _measure_room_fills uses, so the oracle cannot drift from the
    # thing it is the oracle for.
    _FILL_CLIP_SIDE_PT = _TITLE_SCALE_SIDE_PT

    def _fill_clip_for_title(self, page, scales, title_bbox) -> tuple:
        """``(printed_scale, clip)`` for one plan title, both in PAGE space.

        THE one definition of "which scale is this drawing's, and what rectangle
        is this drawing" (D-03). It is called twice per sheet — once to locate
        the architectural sibling whose printed dimensions bound the
        cross-check, and once per drawing to measure — and a second copy would
        let the rectangle the bound is harvested from drift away from the
        rectangle the area is measured in.

        Everything here is PAGE space: the space the sheet is read in, and the
        space the rasteriser's clip lives in. Identity on the 61 unrotated pages
        of the four fixtures. Returns ``(None, None)`` when no scale is printed
        beneath the title — measuring at a borrowed scale is a squared error.
        """
        import fitz  # noqa: PLC0415

        tx0, ty0, tx1, ty1 = _page_space_box(page, title_bbox)
        mid = (tx0 + tx1) / 2.0
        # This drawing's OWN scale = the ratio printed directly beneath its
        # title. Borrowing another drawing's scale is a squared error.
        ps, best_gap = None, float("inf")
        for s in scales:
            cx, cy = _page_space_point(page, *s.center_pt)
            if abs(cx - mid) > self._FILL_CLIP_SIDE_PT:
                continue
            gap = cy - ty1
            if _TITLE_SCALE_ABOVE_TOL_PT <= gap < best_gap:
                ps, best_gap = s, gap
        if ps is None:
            return None, None
        return ps, fitz.Rect(
            tx0 - self._FILL_CLIP_SIDE_PT,
            max(0.0, ty0 - self._FILL_CLIP_UP_PT),
            tx1 + self._FILL_CLIP_SIDE_PT,
            max(0.0, ty0 - 8.0),
        )

    # Cap on linear-run candidates kept per callout clip, longest first. The
    # chainer legitimately returns every open run >= min_run_ft inside a clip
    # (Crow p2's STAIR PLAN yields 62), and the candidates exist so a run is
    # groundable like any other candidate — but an unbounded list bloats the
    # bundle and the registry on dense sheets. The measurable objects are the
    # LONG runs; the cap is a bound, not a tuning knob (T-23-46 discipline).
    _LINEAR_RUNS_PER_CLIP = 40

    def _measure_linear_runs(
        self,
        page,
        doc,
        viewports: Sequence,
        printed_scales_by_region: dict,
        sheet_name: str,
        resolved_fpp: float,
    ) -> tuple:
        """Open linear runs (23-15): rails + annotated linetypes, per drawing.

        Two selectors from plan 23-12, both measured at the scale of the
        DRAWING that contains them, never a borrowed page scale:

        * :func:`extract_linetype_runs` — whole-page clip (its four gates are
          the false-positive defence: zero fires across the 76 non-gas pages),
          each run then resolved to its own drawing's callout scale through
          :func:`run_scale_fpp`; a run whose drawing prints no scale is
          flagged and NOT measured.
        * :func:`extract_rail_runs` — per printed-scale callout, inside the
          23-11 cell clip (the box above the callout), at that callout's own
          scale, stamped with the callout title and the typical-detail flag.
          Never offered unclipped (INV-06 risk 4: unclipped chaining swallowed
          a hatch field into a 369 LF phantom).

        Also harvests the sheet's own naming context for the linear binder:
        the sheet-note linear phrases ("ALL GAS PIPING TO BE ...") and any
        AutoCAD SHX text comment annotations, so naming needs no model call.

        Returns ``(runs, sheet_linear_phrases, shx_labels)``. Never raises
        past its caller's try/except; additive like the room-fill call site.
        """
        from bobbytailor.deterministic.component_library import (  # noqa: PLC0415
            harvest_from_notes,
        )
        from bobbytailor.deterministic.open_runs import (  # noqa: PLC0415
            extract_linetype_runs,
            extract_rail_runs,
            run_scale_fpp,
        )
        import fitz  # noqa: PLC0415

        runs: list = []
        # NO mask rects are passed to the selectors — deliberately. On Bob's
        # A3.0 a false table detection reports a "schedule" bbox covering the
        # ENTIRE roof plan, and masking with it deletes every gas segment
        # (measured: 14 runs -> 0). The selectors' own defences are the ones
        # 23-12 position-validated WITHOUT masks: the linetype selector's four
        # gates fire zero times across the 76 non-gas pages, and rail runs are
        # inert candidates until a name binds them. Masked viewports still
        # never OWN a run (run_scale_fpp skips them as scale owners).

        # The TYPICAL-DETAIL reference scale: the sheet's coarsest printed
        # callout (largest feet-per-inch) is the main drawing — a detail is a
        # BLOW-UP, drawn at a smaller feet-per-inch. The resolved page scale
        # is NOT a safe reference: on Bob's A3.0 it still reads a detail's
        # 1.0 ft/in, which would flag the roof plan's own gas run as
        # "typical" while passing the curb detail as main-plan (measured;
        # exactly inverted). Falls back to the resolved scale on a sheet
        # with no printed callouts. The comparison can only ADD flags for a
        # coarser inset (e.g. a vicinity map), never remove one.
        scales = extract_printed_scales(page)
        ref_fpp = 0.0
        for ps in scales:
            ref_fpp = max(ref_fpp, float(getattr(ps, "feet_per_point", 0.0) or 0.0))
        if ref_fpp <= 0:
            ref_fpp = float(resolved_fpp or 0.0)

        # 1) Annotated linetype runs, each at its own drawing's scale.
        rect = page.rect
        page_clip = (0.0, 0.0, max(rect.x1, rect.y1), max(rect.x1, rect.y1))
        for run in extract_linetype_runs(page, doc, page_clip):
            fpp_run = run_scale_fpp(
                page, run, viewports or (), printed_scales_by_region or {}
            )
            if fpp_run and ref_fpp > 0:
                run.is_typical = bool(
                    abs(fpp_run - ref_fpp) > _SCALE_MATCH_TOL * ref_fpp
                )
            runs.append(run)

        # 2) Rail-type runs per callout cell. "Above the callout" is decided
        # in PAGE space (rotation-aware, like _fill_clip_for_title), then
        # mapped back to the unrotated space the selector chains in.
        for ps in scales:
            fpp_cb = float(getattr(ps, "feet_per_point", 0.0) or 0.0)
            if fpp_cb <= 0:
                continue
            bx0, by0, bx1, by1 = _page_space_box(page, ps.bbox_pt)
            page_cell = fitz.Rect(
                bx0 - self._FILL_CLIP_SIDE_PT,
                max(0.0, by0 - self._FILL_CLIP_UP_PT),
                bx1 + self._FILL_CLIP_SIDE_PT,
                max(0.0, by0 - 8.0),
            )
            raw_clip = tuple(from_page_space(page, page_cell))
            rails = extract_rail_runs(
                page,
                doc,
                raw_clip,
                fpp_cb,
                viewport_title=getattr(ps, "title", "") or "",
                page_feet_per_point=(ref_fpp or None),
            )
            rails = sorted(rails, key=lambda r: -r.length_pt)
            runs.extend(rails[: self._LINEAR_RUNS_PER_CLIP])

        # 3) Unique candidate IDs across the whole sheet (each selector call
        # numbers from 1; the registry needs sheet-unique keys).
        for i, run in enumerate(runs):
            run.candidate_id = "LIN-%d" % (i + 1)

        # 4) The sheet's own naming context (no model call anywhere).
        phrases: list = []
        try:
            phrases = [
                e for e in harvest_from_notes(page.get_text() or "")
                if e.get("source") == "sheet_note"
            ]
        except Exception as exc:  # noqa: BLE001 — naming context is additive
            logger.debug("linear phrase harvest failed on %r: %s", sheet_name, exc)
        shx: list = []
        try:
            for annot in page.annots() or ():
                info = getattr(annot, "info", None) or {}
                if (info.get("title") or "") != "AutoCAD SHX Text":
                    continue
                content = (info.get("content") or "").strip()
                if not content:
                    continue
                r = annot.rect
                shx.append({
                    "rect": (r.x0, r.y0, r.x1, r.y1),
                    "text": content,
                })
        except Exception as exc:  # noqa: BLE001 — annots are additive
            logger.debug("SHX annot harvest failed on %r: %s", sheet_name, exc)

        return runs, phrases, shx

    def _measure_room_fills(
        self,
        page,
        viewports: Sequence,
        printed_scales_by_region: dict,
        sheet_name: str,
        max_region_sf: float = MAX_REGION_SF,
    ) -> tuple:
        """Measure each scaled DRAWING as an enclosed region, at its own scale.

        Anchored on the printed scale callouts: one callout marks one drawing,
        and the drawing sits above it. Each is measured at ITS OWN printed scale
        — a sheet routinely mixes a 1/4"=1'-0" unit plan with 1 1/2"=1'-0"
        details, and area scales by the SQUARE, so one page-level scale corrupts
        every region it touches. A drawing with no printed scale of its own is
        skipped rather than measured with a borrowed one (flag-don't-guess).

        "Above" is decided in PAGE space (23-07/SP-1). The title box, the
        callout centre, the adjacency gap and the clip are all mapped through
        ``room_fill.to_page_space`` first, because ``page.get_text`` answers in
        the unrotated mediabox while a reader — and the rasteriser — see
        ``page.rect``. On Moxy's ``/Rotate 90`` sheets the raw gap for
        ``LEVEL 1 LOBBY - AR PLAN`` is **-80 pt**, the guard rejects it, no
        scale binds and the drawing is skipped: pages 9 and 13 measured
        NOTHING. The tolerance is deliberately untouched — the defect is the
        coordinate space, and widening the guard would paper over it while
        moving unrotated sheets.

        Args:
            max_region_sf: the largest region still credible as ONE unit.
                Threaded rather than read from the module constant so a caller
                measuring something that is not a guest room (23-11, 23-14) can
                pass its own bound without editing a constant every other
                caller shares. Defaults to exactly today's
                ``room_fill.MAX_REGION_SF``, so this plan moves no measurement.

        Returns:
            ``(fills, coverage)`` — the measurements, and one
            :class:`DrawingCoverage` per drawing this method SAW, whatever
            became of it: the reason where it was not measured, and a MEASURED
            row where it was. The four bare ``continue``s this method used to
            take are exactly INV-08 §2 row S6: a named drawing (e.g.
            ``KING A - FC PLAN``) vanished with no row, no flag and no count in
            any artifact, so its item read as a zero rather than as a blank.
            The MEASURED row is the mirror of that: a drawing that produced
            1716.7 SF also left no row, so the ledger counted it as nothing.
        """
        from bobbytailor.deterministic.printed_scale import (  # noqa: PLC0415
            extract_printed_scales,
        )
        from bobbytailor.deterministic.room_fill import (  # noqa: PLC0415
            BASIS_PLAN_KIND,
            cross_check_extent,
            measure_enclosed_area,
            plan_titles,
            printed_extent_bound,
            resolve_drawing_height,
        )

        drops: List[DrawingCoverage] = []

        def _drop(i, plan_name, plan_kind, disposition, reason, fpi=None):
            drops.append(
                DrawingCoverage(
                    region_id="FILL-%d" % (i + 1),
                    title="%s - %s PLAN" % (plan_name, plan_kind),
                    plan_kind=plan_kind,
                    disposition=disposition,
                    reason=reason,
                    printed_scale_fpi=fpi,
                )
            )
            logger.info(
                "sheet %r: FILL-%d %r NOT measured — %s",
                sheet_name, i + 1, "%s - %s PLAN" % (plan_name, plan_kind), reason,
            )

        try:
            import fitz  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return [], drops

        scales = extract_printed_scales(page)
        titles = plan_titles(page)

        # The drawing's own printed OVERALL dimensions are what the measurement
        # is cross-checked against, and on this drawing set they are printed on
        # the ARCHITECTURAL plan only — a reflected-ceiling drawing carries no
        # dimension of its own. So the architectural sibling of the SAME plan
        # name is located first, by exactly the same clip recipe, and its
        # rectangle travels with every fill of that name.
        #
        # The dimension harvest walks every segment on the page, so it runs ONCE
        # here rather than once per drawing.
        ar_kind = BASIS_PLAN_KIND.get("floor_area")
        ar_rects: dict = {}
        for plan_name, plan_kind, tb in titles:
            if plan_kind != ar_kind:
                continue
            _ps, ar_clip = self._fill_clip_for_title(page, scales, tb)
            if ar_clip is not None:
                ar_rects.setdefault(plan_name, []).append(
                    from_page_space(page, ar_clip)
                )

        # The unit's WALL HEIGHT is printed inside its reflected-ceiling clip —
        # printing the room height is what an RCP is for — so the RCP sibling
        # of the SAME plan name is located by the same clip recipe and its
        # rectangle answers the height for every fill of that name. Reading the
        # architectural clip instead would mistake room DIMENSIONS
        # (10'-10 3/8") for heights; reading the project resolver instead
        # inherits the 15 ft roof-plan clearance callout at source "plan",
        # which does not flag (INV-01 §5). Page space, like the clip itself.
        rcp_kind = BASIS_PLAN_KIND.get("ceiling_area")
        rcp_rects: dict = {}
        for plan_name, plan_kind, tb in titles:
            if plan_kind != rcp_kind:
                continue
            _ps, rcp_clip = self._fill_clip_for_title(page, scales, tb)
            if rcp_clip is not None:
                rcp_rects.setdefault(plan_name, rcp_clip)
        mask_rects = [
            vp.bbox_pt for vp in (viewports or ())
            if getattr(vp, "kind", "") in _MASK_VIEWPORT_KINDS
            and getattr(vp, "bbox_pt", None)
        ]
        dim_samples = None
        try:
            dim_samples = extract_dimension_samples(page, exclude_rects=mask_rects)
        except Exception as exc:  # noqa: BLE001 — a cross-check never kills a run
            logger.debug("room_fill: dimension harvest failed: %s", exc)

        out: list = []
        for i, (plan_name, plan_kind, tb) in enumerate(titles):
            # Everything below is PAGE space: the space the sheet is read in,
            # and the space the rasteriser's clip lives in. Identity on the 61
            # unrotated pages of the four fixtures.
            tx0, ty0, tx1, ty1 = _page_space_box(page, tb)
            ps, clip = self._fill_clip_for_title(page, scales, tb)
            if ps is None:
                _drop(
                    i, plan_name, plan_kind, SKIPPED_NO_SCALE,
                    "no printed scale beneath the title — measuring it at a "
                    "borrowed scale would be a squared error",
                )
                continue
            fpp = float(getattr(ps, "feet_per_point", 0.0) or 0.0)
            if fpp <= 0:
                _drop(
                    i, plan_name, plan_kind, SKIPPED_NO_SCALE,
                    "the printed scale parsed to a non-positive feet-per-point "
                    "(%r)" % (getattr(ps, "text", "") or "",),
                )
                continue
            fpi = round(fpp * 72.0, 4)
            if clip is None or clip.is_empty or clip.height <= 0 or clip.width <= 0:
                _drop(
                    i, plan_name, plan_kind, ERRORED,
                    "the clip rectangle around the title is degenerate "
                    "(%.1f x %.1f pt) — there is no area to measure"
                    % ((clip.width, clip.height) if clip is not None else (0.0, 0.0)),
                    fpi,
                )
                continue
            oversize: List[float] = []
            result = measure_enclosed_area(
                # measure_enclosed_area has ONE contract — its clip is in
                # drawing space and it maps forward itself — so the page-space
                # rectangle reasoned about here is handed back through the
                # inverse rather than a second "which space is this?" flag that
                # a future caller could get wrong. Both maps are the identity
                # on an unrotated page, so this is the same object today's code
                # passed.
                page, from_page_space(page, clip), fpp,
                candidate_id="FILL-%d" % (i + 1),
                max_region_sf=max_region_sf,
                dropped_regions=oversize,
            )
            if result is None:
                extra = ""
                if oversize:
                    extra = (
                        "; %d region(s) of %s SF were rejected as larger than one "
                        "unit" % (
                            len(oversize),
                            ", ".join("%.0f" % a for a in sorted(oversize, reverse=True)),
                        )
                    )
                _drop(
                    i, plan_name, plan_kind, ERRORED,
                    "no enclosed region survived the minimum and maximum region "
                    "filter%s" % extra,
                    fpi,
                )
                continue
            # Cross-check against the drawing's OWN printed overall extent — a
            # scale-free RATIO, never a size in square feet, and a FLAG, never
            # a filter. No printed dimension pair means NEEDS REVIEW carrying
            # the measured area, not a dropped row.
            result = cross_check_extent(
                result,
                printed_extent_bound(
                    page, from_page_space(page, clip),
                    plan_name=plan_name,
                    mask_rects=mask_rects,
                    sibling_rects=ar_rects.get(plan_name, ()),
                    samples=dim_samples,
                ),
            )
            result.sheet_name = sheet_name
            result.plan_name = plan_name
            result.plan_kind = plan_kind
            result.viewport_title = "%s - %s PLAN" % (plan_name, plan_kind)
            # Height precedence, most specific first: the unit's own
            # reflected-ceiling tag ("drawing"), then the project resolver
            # (whose own precedence is learned → plan → default, source
            # carried), then nothing — and anything not read from the drawing
            # flags downstream rather than multiplying silently.
            result.wall_height_ft, result.wall_height_source = (
                resolve_drawing_height(
                    page,
                    rcp_rects.get(plan_name),
                    getattr(self, "_project_wall_height", None),
                    getattr(self, "_project_wall_height_source", None) or "",
                )
            )
            out.append(result)
            if oversize:
                # Measured, but not everything inside the clip was kept. The
                # rejection is correct and was invisible; it is now on the record.
                drops.append(
                    DrawingCoverage(
                        region_id=result.candidate_id,
                        title=result.viewport_title,
                        plan_kind=plan_kind,
                        disposition=MEASURED_PARTIAL,
                        reason="%d region(s) of %s SF were rejected as larger than "
                               "one unit" % (
                                   len(oversize),
                                   ", ".join(
                                       "%.0f" % a
                                       for a in sorted(oversize, reverse=True)
                                   ),
                               ),
                        printed_scale_fpi=fpi,
                        area_sf=result.area_sf,
                        needs_review=bool(result.needs_review),
                    )
                )
            else:
                # A drawing that MEASURED leaves a row too, not only one that
                # refused. Without this the ledger's `drawings` list held drops
                # exclusively, so `drawings_measured` — which counts MEASURED
                # and MEASURED_PARTIAL rows — read 0 on every saved run of all
                # four plan sets, including runs whose own `fusion_rejected`
                # records carry `fill:FILL-2` at 1716.7 SF. A counter that is
                # structurally zero is not a low number, it is a wrong one, and
                # it reads as "this sheet measured nothing" beside the single
                # skip row the sheet legitimately produced (Crow A-101: title
                # #1 is the title BLOCK's own "OVERALL FLOOR PLAN" string with
                # no callout within 573 pt, title #2 the real drawing title,
                # which pairs and measures). MEASURED here cannot move a sheet
                # disposition: _record_sheet_coverage's `dropped` filter
                # already excludes it.
                drops.append(
                    DrawingCoverage(
                        region_id=result.candidate_id,
                        title=result.viewport_title,
                        plan_kind=plan_kind,
                        disposition=MEASURED,
                        printed_scale_fpi=fpi,
                        area_sf=result.area_sf,
                        needs_review=bool(result.needs_review),
                    )
                )
            logger.info(
                "sheet %r: %s %r enclosed area %.1f SF at %.2f ft/in, "
                "perimeter %.1f LF, wall height %s (source %s)%s",
                sheet_name, result.candidate_id, result.viewport_title,
                result.area_sf, result.scale_fpi or 0.0,
                result.perimeter_lf,
                ("%.2f ft" % result.wall_height_ft)
                if result.wall_height_ft is not None else "UNRESOLVED",
                result.wall_height_source or "none",
                " [needs review]" if result.needs_review else "",
            )
        return out, drops

    # ── Elevation facades (23-14) ────────────────────────────────────────────
    #
    # The fill-ratio floor below which a "facade" blob is annotation rather
    # than facade (INV-03 step 7). Measured, not tuned: every real facade on
    # Bob's / Crow / Chelsea reads 0.44-0.93; Moxy's sparse partial-court
    # elevations read 0.11-0.33 and must flag.
    _ELEV_FILL_RATIO_FLOOR = 0.4
    # A facade blob's width should match one of the floor plan's measured
    # footprint dimensions — two measurements sharing no code path, no sheet
    # and no scale (INV-03 §3.3: Bob's front reads 249-250 ft against the
    # page-1 footprint's depth_ft=250.0). Beyond this relative tolerance the
    # facade flags.
    _ELEV_WIDTH_TOL = 0.20
    _ELEV_CLIP_PAD_PT = 2.0

    def _elevation_clips(self, page, entries, viewports) -> list:
        """``[(entry, clip)]`` — one PAGE-space band clip per elevation callout.

        The callout is the anchor (viewport segmentation merges Crow's four
        elevations into two regions — INV-03 §2.2): each drawing occupies the
        band from the PREVIOUS elevation callout (or the drawing-area edge) up
        to its own callout, x-bounded by the viewport hosting the callout
        (which is what keeps Bob's keyed-notes column and Chelsea's notes
        panel out of the silhouette), and split at x-midpoints between
        callouts sharing a band (Chelsea prints its two SIDE elevations side
        by side over side-by-side callouts).
        """
        vps = []
        for vp in viewports or ():
            bbox = getattr(vp, "bbox_pt", None)
            if not bbox:
                continue
            try:
                box = to_page_space(page, fitz.Rect(*bbox))
            except Exception:  # noqa: BLE001
                continue
            vps.append((getattr(vp, "kind", ""), box))
        out = []
        for e in entries:
            x0c, y0c, x1c, y1c = e.callout_bbox_pt
            prev = 0.0
            for o in entries:
                if o.callout_bbox_pt[3] <= y0c and o.callout_bbox_pt[3] > prev:
                    prev = o.callout_bbox_pt[3]
            cx = (x0c + x1c) / 2.0
            x0, x1 = 0.0, float(page.rect.width)
            best_overlap = 0.0
            for kind, vb in vps:
                if kind in _MASK_VIEWPORT_KINDS:
                    continue
                if not (vb.x0 <= cx <= vb.x1):
                    continue
                overlap = min(vb.y1, y0c) - max(vb.y0, prev)
                if overlap > best_overlap:
                    best_overlap = overlap
                    x0, x1 = vb.x0, vb.x1
            if best_overlap <= 0.0:
                # No hosting viewport: keep the full width minus the mask
                # viewports on this callout's side.
                for kind, vb in vps:
                    if kind not in _MASK_VIEWPORT_KINDS:
                        continue
                    if vb.x0 > cx:
                        x1 = min(x1, vb.x0)
                    elif vb.x1 < cx:
                        x0 = max(x0, vb.x1)
            for o in entries:
                if o is e:
                    continue
                ox0, oy0, ox1, oy1 = o.callout_bbox_pt
                if min(oy1, y1c) - max(oy0, y0c) <= 0:
                    continue
                ocx = (ox0 + ox1) / 2.0
                if ocx < cx:
                    x0 = max(x0, (ox1 + x0c) / 2.0)
                elif ocx > cx:
                    x1 = min(x1, (x1c + ox0) / 2.0)
            pad = self._ELEV_CLIP_PAD_PT
            out.append((e, fitz.Rect(x0 + pad, prev + pad, x1 - pad, y0c - pad)))
        return out

    def _facade_width_matches(self, facade, footprint):
        """``True``/``False``/``None`` — blob width vs the measured footprint.

        ``None`` when no footprint has been measured yet (nothing to check —
        never a flag for want of a cross-check that could not exist).
        """
        if footprint is None:
            return None
        dims = []
        for attr in ("width_ft", "depth_ft"):
            try:
                value = float(getattr(footprint, attr, None) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                dims.append(value)
        if not dims or not facade.bbox_ft or facade.bbox_ft[0] <= 0:
            return None
        width = float(facade.bbox_ft[0])
        return any(abs(width - d) / d < self._ELEV_WIDTH_TOL for d in dims)

    def _measure_elevation_areas(self, page, viewports, sheet_name: str) -> tuple:
        """Measure each titled elevation as a facade silhouette, at its own scale.

        ``(facades, coverage)`` — the elevation analogue of
        :func:`_measure_room_fills`, coverage row per elevation SEEN (measured
        or refused) exactly as that method does, anchored on the callouts
        (:func:`room_fill.elevation_titles`). Each facade is measured at THAT
        callout's own feet-per-point, cropped to its own datum band, and
        validated by POSITION: the blob width against the independently
        measured footprint dimension, the fill ratio against the annotation
        floor, and the printed scale against the datum ladder's plausibility
        band. A demolition/existing or interior elevation is measured but
        EXCLUDED from new-work quantities with the reason on the record.

        NOT gated on the sheet type — Chelsea puts nine elevations on sheets
        typed ``floor_plan``, so the measurement gates on what is actually
        present: an elevation-titled callout.
        """
        from bobbytailor.deterministic.room_fill import (  # noqa: PLC0415
            datum_scale_check,
            datum_wall_band,
            elevation_datums,
            elevation_titles,
            keynote_legend,
            keynote_tags,
            measure_facade_area,
        )

        drops: List[DrawingCoverage] = []
        try:
            entries = elevation_titles(page)
        except Exception as exc:  # noqa: BLE001 — additive
            logger.debug("elevation titles failed on %r: %s", sheet_name, exc)
            return [], drops
        if not entries:
            return [], drops

        # The sheet's keynote legends, harvested ONCE — grouped by header so
        # a demolition drawing's tags resolve through the DEMO legend and a
        # new-work drawing's through the keyed notes, even where the numbers
        # collide (Bob's '03': EIFS scratch coat vs. removed light sconce).
        legends: dict = {}
        try:
            legends = keynote_legend(page)
        except Exception as exc:  # noqa: BLE001 — attribution is additive
            logger.debug("keynote legend harvest failed on %r: %s", sheet_name, exc)

        def _drop(cid, title, disposition, reason, fpi=None):
            drops.append(
                DrawingCoverage(
                    region_id=cid,
                    title=title,
                    disposition=disposition,
                    reason=reason,
                    printed_scale_fpi=fpi,
                )
            )
            logger.info(
                "sheet %r: %s %r NOT measured — %s", sheet_name, cid, title, reason
            )

        footprint = getattr(self, "_project_footprint", None)
        facades: list = []
        for i, (entry, clip) in enumerate(
            self._elevation_clips(page, entries, viewports)
        ):
            cid = "ELEV-%d" % (i + 1)
            fpp = float(getattr(entry.scale, "feet_per_point", 0.0) or 0.0)
            if fpp <= 0:
                _drop(
                    cid, entry.title, SKIPPED_NO_SCALE,
                    "the printed scale beneath this elevation parsed to a "
                    "non-positive feet-per-point — measuring at a borrowed "
                    "scale would be a squared error",
                )
                continue
            fpi = round(fpp * 72.0, 4)
            if clip.is_empty or clip.height <= 10 or clip.width <= 10:
                _drop(
                    cid, entry.title, ERRORED,
                    "the band clip for this elevation is degenerate "
                    "(%.1f x %.1f pt)" % (clip.width, clip.height),
                    fpi,
                )
                continue
            datums = elevation_datums(page, clip)
            band = datum_wall_band(datums)
            facade = measure_facade_area(
                page,
                from_page_space(page, clip),
                fpp,
                candidate_id=cid,
                crop_band_pt=(band[0], band[1]) if band else None,
            )
            if facade is None:
                _drop(
                    cid, entry.title, ERRORED,
                    "no silhouette survived complement labelling inside this "
                    "elevation's band — the drawing is unmeasured, not zero",
                    fpi,
                )
                continue
            facade.sheet_name = sheet_name
            facade.title = entry.title
            facade.orientation = entry.orientation
            facade.is_demo = entry.is_demo
            facade.is_interior = entry.is_interior
            if band:
                facade.datum_height_ft = band[2]
            if legends:
                try:
                    facade.materials = _attribute_facade_materials(
                        facade,
                        keynote_tags(page, clip),
                        _legend_for_drawing(legends, entry.is_demo),
                    )
                except Exception as exc:  # noqa: BLE001 — attribution is additive
                    logger.debug(
                        "material attribution failed on %r %s: %s",
                        sheet_name, cid, exc,
                    )

            if entry.is_demo:
                facade.excluded = True
                facade.excluded_reason = (
                    "demolition/existing elevation — it describes what is "
                    "REMOVED and is excluded from new-work quantities"
                )
            elif entry.is_interior or not entry.orientation:
                facade.excluded = True
                facade.excluded_reason = (
                    "interior or detail elevation (%r) — not an exterior "
                    "facade; no interior finish area is synthesized from it"
                    % (entry.title,)
                )

            reasons: List[str] = []
            width_ok = self._facade_width_matches(facade, footprint)
            if band is None:
                if width_ok is not True:
                    reasons.append(
                        "no datum pair inside this elevation's band — its "
                        "height is unvalidated, and no independently measured "
                        "footprint width validates the blob either; verify "
                        "before billing"
                    )
                # else: position-validated by an independent measurement — the
                # blob width matches the floor plan's own footprint dimension.
            else:
                if datum_scale_check(datums, fpp) is False:
                    reasons.append(
                        "the printed scale is IMPLAUSIBLE against this "
                        "drawing's own datum ladder (outside the ±30%% band) "
                        "— a misparsed scale corrupts every quantity on the "
                        "drawing"
                    )
            if facade.fill_ratio < self._ELEV_FILL_RATIO_FLOOR:
                reasons.append(
                    "the dominant blob's fill ratio %.2f is below the %.1f "
                    "plausibility floor — it may be annotation rather than "
                    "facade" % (facade.fill_ratio, self._ELEV_FILL_RATIO_FLOOR)
                )
            if width_ok is False:
                dims = "%.1f x %.1f ft" % (
                    float(getattr(footprint, "width_ft", 0.0) or 0.0),
                    float(getattr(footprint, "depth_ft", 0.0) or 0.0),
                )
                reasons.append(
                    "the blob's %.0f ft width matches neither independently "
                    "measured footprint dimension (%s) within %.0f%%"
                    % (facade.bbox_ft[0], dims, self._ELEV_WIDTH_TOL * 100)
                )
            if reasons:
                facade.needs_review = True
                facade.review_reason = (
                    "%s; %s" % (facade.review_reason, "; ".join(reasons))
                    if facade.review_reason else "; ".join(reasons)
                )
            facades.append(facade)
            # Same asymmetry as the room fills, and it has to close with them:
            # every elevation this method REFUSED already lands in `drops`, so
            # a ledger that never records the measured ones counts elevation
            # coverage as pure loss. An excluded facade (demolition, interior)
            # is still a MEASURED drawing carrying its exclusion as the reason —
            # "was this drawing measured" and "does its number reach a
            # quantity" are different questions, and item_coverage answers the
            # second one.
            drops.append(
                DrawingCoverage(
                    region_id=cid,
                    title=entry.title,
                    disposition=MEASURED,
                    reason=facade.excluded_reason or "",
                    printed_scale_fpi=fpi,
                    area_sf=facade.area_sf,
                    needs_review=bool(facade.needs_review),
                )
            )
            logger.info(
                "sheet %r: %s %r facade %.1f SF at %.2f ft/in (%s)%s%s",
                sheet_name, cid, entry.title, facade.area_sf, fpi,
                "datum-cropped %.2f ft" % facade.datum_height_ft
                if facade.datum_height_ft else "no datum band",
                " [excluded: %s]" % facade.excluded_reason
                if facade.excluded else "",
                " [needs review]" if facade.needs_review else "",
            )
        _flag_same_orientation_pairs(facades)
        return facades, drops

    @staticmethod
    def _record_sheet_coverage(row: SheetCoverage, extracted: dict) -> None:
        """Copy one processed sheet's coverage records onto its ledger row.

        Additive and total: a sheet dict from a path that produced no records
        (the raster/legacy flow) leaves the row exactly as the earlier stages
        wrote it. The disposition is only ever moved DOWNWARDS in confidence —
        a sheet that dropped a drawing becomes MEASURED_PARTIAL — and never
        upgraded, so nothing here can quietly relabel a skip as a measurement.
        """
        drawings = list(extracted.get("_excluded_viewports") or [])
        drawings += list(extracted.get("_coverage_drops") or [])
        if drawings:
            row.drawings.extend(d for d in drawings if isinstance(d, DrawingCoverage))

        geometry = extracted.get("_geometry")
        if geometry is not None and not row.measurable_signal.get("geometry"):
            # Presence, not contents: the ledger stays flat (INV-08 risk 3 —
            # coverage_ledger rides inside takeoff.json, which the web UI loads
            # whole, so no bitmaps and no region lists go on this row).
            row.measurable_signal = dict(row.measurable_signal)
            row.measurable_signal["geometry"] = 1

        components = extracted.get("components") or []
        if components:
            row.items_emitted = len(components)

        cost = extracted.get("_cost_usd")
        if cost:
            try:
                row.cost_usd = float(cost)
            except (TypeError, ValueError):
                pass

        # A sheet that measured something AND dropped something is partial, not
        # whole. Only ever applied to a row still reading the MEASURED default.
        dropped = [
            d for d in row.drawings
            if getattr(d, "disposition", "") not in (MEASURED, EXCLUDED_OFF_SCALE)
        ]
        if dropped and row.disposition == MEASURED:
            row.disposition = MEASURED_PARTIAL
            if not row.reason:
                row.reason = (
                    "%d drawing(s) on this sheet were not measured — see the "
                    "per-drawing reasons" % len(dropped)
                )

        # ── The wallet stopped this sheet, and the row must say so (C2) ──────
        #
        # run_sheet already flags the SHEET DICT `_budget_exhausted` when the
        # guard refuses mid-pass, but that flag died there: Crow's A-401 and
        # A-601 skipped their remaining passes and their ledger rows still read
        # "measured", the report contained the phrase "budget exhausted" zero
        # times, and the run presented as complete.
        if extracted.get("_budget_exhausted"):
            row.budget_truncated = True
            if row.disposition in (MEASURED, MEASURED_PARTIAL):
                row.disposition = MEASURED_TRUNCATED
            row.reason = _append_reason(
                row.reason,
                "the API budget was exhausted part-way through this sheet — its "
                "remaining passes never ran, so what is here is a lower bound "
                "and what is absent is unknown, not zero",
            )

    def _structured_vision_call(
        self,
        image_path: str,
        sheet_name: str,
        pass_type: str,
        sheet_type: str,
        schema: dict,
        images: list,
        guard: Optional[BudgetGuard],
        user_hint: str = "",
    ) -> dict:
        """One structured-output vision call, charged to the budget guard.

        Raises BudgetExceeded when the guard is already exhausted or the
        charge for the completed call is refused (the refused result is
        discarded — the ledger only ever holds paid-and-accepted work).

        ``user_hint`` (default "") threads an optional per-pass instruction
        into ``analyze_drawing`` — e.g. the symbol-identification pass sends
        the per-cluster repetition counts. Empty string preserves the prior
        behaviour for every existing caller.
        """
        if guard is not None and guard.exhausted:
            raise BudgetExceeded(guard.spent_usd, guard.max_usd)
        result = self._analyzer(
            image_path,
            sheet_name,
            pass_type=pass_type,
            sheet_type=sheet_type,
            output_schema=schema,
            images=images,
            user_hint=user_hint,
        )
        if guard is not None:
            guard.charge(_result_cost_usd(result))
        if not isinstance(result, dict):
            logger.warning(
                "_structured_vision_call: non-dict result for %r pass=%r",
                sheet_name, pass_type,
            )
            return {}
        return result

    def _voted_structured_vision_call(
        self,
        image_path: str,
        sheet_name: str,
        pass_type: str,
        sheet_type: str,
        schema: dict,
        images: list,
        guard: Optional[BudgetGuard],
        user_hint: str = "",
        *,
        vote_key: str,
        n: Optional[int] = None,
    ) -> dict:
        """Majority-vote N structured vision calls over their per-candidate labels.

        Runs :meth:`_structured_vision_call` up to *n* times (default
        ``ensemble_settings()["n"]``), majority-voting the label list under
        *vote_key* per candidate id so a stochastic "unknown" cannot flip an
        item FOUND/MISSING between identical runs. Budget-guarded: sampling
        stops early when the guard is exhausted and votes over whatever paid
        samples were gathered (never a silent partial). ``n <= 1`` is exactly
        the single-shot :meth:`_structured_vision_call` (byte-identical result).

        The synthetic result keeps the SAME shape a single call returned — all
        non-``vote_key`` scalar fields are carried from a representative sample
        and usage/cost is summed across the voted samples — so downstream
        ``res.get(vote_key)`` and ``fuse_sheet`` are unchanged.
        """
        if n is None:
            try:
                n = int(ensemble_settings()["n"])
            except Exception:  # noqa: BLE001 — config stubbed → single-shot
                n = 1
        if n <= 1:
            return self._structured_vision_call(
                image_path, sheet_name, pass_type, sheet_type, schema, images,
                guard, user_hint=user_hint,
            )

        samples: list = []
        for _ in range(n):
            if guard is not None and getattr(guard, "exhausted", False):
                break
            try:
                res = self._structured_vision_call(
                    image_path, sheet_name, pass_type, sheet_type, schema, images,
                    guard, user_hint=user_hint,
                )
            except BudgetExceeded:
                break
            if isinstance(res, dict):
                samples.append(res)

        if not samples:
            # No paid samples — surface the same signal a single call would
            # (guard exhausted before the first call): the caller's
            # ``except BudgetExceeded`` flags the pass, never a silent empty.
            if guard is not None:
                raise BudgetExceeded(guard.spent_usd, guard.max_usd)
            return {}

        # Base carries the non-voted scalar fields (e.g. semantic pass's
        # ``main_plan_region``); prefer a non-error sample.
        base = next((s for s in samples if not s.get("error")), samples[0])
        result = dict(base)
        result[vote_key] = _vote_categorical_labels(samples, vote_key)
        result.update(_sum_usage(samples))  # aggregate paid usage/cost
        result["_voted"] = True
        result["_vote_samples"] = len(samples)
        return result

    def _run_sheet_vector(
        self,
        *,
        page,
        doc,
        image_path: str,
        sheet_name: str,
        resolved_type: str,
        pdf_path: str,
        page_index: int,
        guard: BudgetGuard,
    ) -> dict:
        """Deterministic-first vector flow: geometry proposes, vision disposes.

        Vision sees only ID-annotated overlays / crop galleries with
        structured schemas whose ID fields are candidate enums (quantities
        are grammatically impossible on this path); every output quantity
        comes from the deterministic side via fuse_sheet.
        """
        bundle = self._deterministic_bundle(
            page, doc, pdf_path, page_index, sheet_name, resolved_type
        )
        viewports_with_scales = bundle.pop("_viewports_with_scales")
        main_id = bundle.pop("_main_plan_region")
        scale = bundle.pop("_scale_result")
        viewports = bundle.get("viewports") or []
        schedules = bundle.get("schedules") or []
        symbols = bundle.get("symbol_groups") or []

        registry = build_registry(bundle)
        # Hybrid naming: merge deterministic schedule labels with the
        # autonomous project-vocabulary labels (manifest replacement). For a
        # plan whose only extracted schedule is a 2-row door table, the vocab
        # labels supply "Column"/"Bollard"/"Ladder"/... so the gallery runs
        # and geometry symbol clusters bind to real object names instead of
        # staying label=None. When vocabulary is empty this is identical to
        # schedule labels alone (additive-only).
        legend_labels = _dedupe_labels(
            _legend_labels_from_schedules(schedules)
            + list(getattr(self, "_project_vocab_labels", []) or [])
        )

        # ── Semantic vision passes (labels only — budget-guarded) ─────────
        vision_labels: dict = {}
        vision_results: list = []
        passes_run = ["deterministic"]
        budget_exhausted = False

        # The words the drawing itself printed beside each candidate (24-01).
        # They ride on the marker chips and, for the symbol pass, in the hint.
        # `anchor_absences` is the separate, structural question of which
        # candidates the drawing was asked about and printed NOTHING for.
        anchor_texts = _anchor_texts(bundle)
        anchor_absences = _anchor_absences(bundle)

        region_ids = [
            vp.region_id for vp in viewports if vp.kind not in _MASK_VIEWPORT_KINDS
        ]
        wall_ids = sorted(
            cid for cid, meta in registry.items() if meta.get("kind") == "wall_class"
        )
        # Room candidates complete the dependency-ordered topology (V4-DET-03):
        # the schema asks each room which walls bound it, so the rooms must be
        # MARKED or the model is being asked about geometry it never saw. A
        # registry bbox of all zeros is position UNKNOWN, never position (0,0),
        # so such a room is not marked and not asked about (24-01's rule).
        room_ids = sorted(
            cid for cid, meta in registry.items()
            if meta.get("kind") == "room" and any(meta.get("bbox_pt") or ())
        )
        if region_ids and wall_ids:
            try:
                candidates = {}
                for vp in viewports:
                    if vp.region_id in region_ids:
                        candidates[vp.region_id] = vp.bbox_pt
                for cid in wall_ids:
                    candidates[cid] = registry[cid]["bbox_pt"]
                for cid in room_ids:
                    candidates[cid] = registry[cid]["bbox_pt"]
                overlay = _render_overlay(page, candidates, anchors=anchor_texts)
                images = overlay if isinstance(overlay, list) else [overlay]
                images = images[:20]
                # Ask only about what was actually marked on the images sent.
                shown = _ids_shown_on(images)
                sent_regions = [c for c in region_ids if c in shown]
                sent_walls = [c for c in wall_ids if c in shown]
                sent_rooms = [c for c in room_ids if c in shown]
                if not (sent_regions and sent_walls):
                    raise ValueError(
                        "semantic pass: the request's image budget carries no "
                        "region or no wall-class marker"
                    )
                schema = semantic_labeling_schema(
                    sent_regions, sent_walls, sent_rooms
                )
                res = self._voted_structured_vision_call(
                    image_path, sheet_name, "semantic", resolved_type,
                    schema, images, guard,
                    vote_key="wall_classes",
                )
                passes_run.append("semantic")
                if res and not res.get("error"):
                    vision_results.append(res)
                    # Adapter: the SCHEMA is dependency-ordered, the internal
                    # label contract is unchanged. fusion, the reporter and the
                    # merged result keep reading exactly the keys they always
                    # read, so the topology change stops at this boundary.
                    vision_labels["main_plan_region"] = _main_region_from_answer(
                        res.get("regions")
                    )
                    vision_labels["wall_class_labels"] = res.get("wall_classes")
                    vision_labels["room_labels"] = res.get("rooms")
                    # The bounding-wall citation lands on the room records
                    # fusion reads (V4-DET-03); a room citing none is ledgered.
                    _apply_room_wall_references(
                        bundle.get("rooms") or [], res.get("rooms")
                    )
            except BudgetExceeded:
                budget_exhausted = True
            except Exception as exc:  # noqa: BLE001 — labels are additive
                logger.warning(
                    "run_sheet: %r — semantic overlay pass failed: %s",
                    sheet_name, exc,
                )

        if symbols and not budget_exhausted:
            if legend_labels:
                try:
                    # In-context Set-of-Mark identification (replaces the
                    # tiny-crop gallery): mark every symbol cluster on the FULL
                    # plan so the model sees WHERE each SYM-id sits on the real
                    # drawing, and thread the deterministic repetition counts
                    # so it can reason like an estimator (136× on a structural
                    # grid → columns; 28-56× around the perimeter → bollards).
                    # A lone crop of a column bubble is unidentifiable — which
                    # is exactly why the old gallery pass returned "unknown"
                    # for everything and Crow's 724 counted symbols never
                    # became named line items.
                    #
                    # And ask ONLY about clusters the drawing itself names
                    # (V4-DET-01). A cluster with no text anchor has nothing to
                    # read, so asking about it is asking the model to name a
                    # shape — the 0.03-0.39 condition. It is excluded from the
                    # request entirely rather than asked and then discarded:
                    # not asking is cheaper and it cannot flip. Those clusters
                    # flow to 24-04's unnamed-geometry ledger, which already
                    # carries their counts.
                    #
                    # The restriction fires on a RECORDED ABSENCE only. A
                    # candidate with no anchor record at all was never
                    # interrogated, and reading that as "nothing names it"
                    # would turn a failed anchor computation into a silently
                    # empty pass (INV-08).
                    sym_candidates = {}
                    unanchored: list = []
                    for group in symbols:
                        cid = _sched_field(group, "candidate_id", "")
                        if not cid:
                            continue
                        rep = _sched_field(group, "representative_bbox_pt", None)
                        if rep is None:
                            rep = _sched_field(group, "bbox_pt", None)
                        if not rep:
                            continue
                        if cid in anchor_absences:
                            unanchored.append(cid)
                            continue
                        sym_candidates[cid] = rep
                    if unanchored:
                        logger.info(
                            "run_sheet: %r — %d symbol group(s) carry no text "
                            "anchor and are not presented to the model; they "
                            "stay flagged unlabeled (%s)",
                            sheet_name, len(unanchored),
                            ", ".join(unanchored[:10]),
                        )
                    if sym_candidates:
                        overlay = _render_overlay(
                            page, sym_candidates, anchors=anchor_texts
                        )
                        images = overlay if isinstance(overlay, list) else [overlay]
                        images = images[:20]
                        # Ask only about clusters actually marked on the images
                        # sent — the request budget can truncate the partition.
                        shown = _ids_shown_on(images)
                        symbol_ids = [c for c in sym_candidates if c in shown]
                        if not symbol_ids:
                            raise ValueError(
                                "symbol pass: the request's image budget "
                                "carries no symbol marker"
                            )
                        schema = symbol_gallery_schema(symbol_ids, legend_labels)
                        asked = [
                            g for g in symbols
                            if _sched_field(g, "candidate_id", "") in set(symbol_ids)
                        ]
                        user_hint = _join_hints(
                            _build_symbol_count_hint(asked),
                            _build_anchor_hint(anchor_texts, symbol_ids),
                        ) or ""
                        res = self._voted_structured_vision_call(
                            image_path, sheet_name, "symbol_gallery",
                            resolved_type, schema, images, guard,
                            user_hint=user_hint,
                            vote_key="matches",
                        )
                        passes_run.append("symbol_gallery")
                        if res and not res.get("error"):
                            vision_results.append(res)
                            vision_labels["matches"] = res.get("matches")
                    else:
                        # Same path the empty-legend short circuit takes below:
                        # never issue a request with an empty candidate set —
                        # `_require_candidates` raises on one by design.
                        logger.info(
                            "run_sheet: %r — no symbol group carries a text "
                            "anchor; %d symbol group(s) stay flagged unlabeled",
                            sheet_name, len(symbols),
                        )
                except BudgetExceeded:
                    budget_exhausted = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "run_sheet: %r — symbol identification pass failed: %s",
                        sheet_name, exc,
                    )
            else:
                logger.info(
                    "run_sheet: %r — no legend labels for the symbol gallery; "
                    "%d symbol group(s) stay flagged unlabeled",
                    sheet_name, len(symbols),
                )

        vision_labels.update(_sum_usage(vision_results))

        # ── Fusion: labels bind to deterministic quantities only ──────────
        # Thread the autonomous project vocabulary (measure basis) + resolved
        # wall height so wall_area labels bind as SF (LF × height) and
        # floor/roof-plane vocabulary items bind to the measured footprint.
        # The unit multiplier comes from the DRAWINGS where the drawings state
        # it (D-10). Every count carries its source into the formula string, and
        # a disagreement with the human manifest rides on the row that uses the
        # number instead of being resolved in silence.
        room_mix_resolution = self._resolve_room_mix(
            getattr(self, "_manifest", None), doc, pdf_path
        )
        if room_mix_resolution.flags and bundle.get("room_fills"):
            # Recorded only where a unit count could actually be applied — a
            # sheet with no measured drawing has nothing to multiply.
            bundle.setdefault("coverage_notes", []).extend(room_mix_resolution.flags)
        # The wall-height cross-check rides on the sheet whose walls the height
        # actually multiplies, so the note sits beside the number it questions
        # rather than on an unrelated schedule page.
        cross_check = getattr(self, "_wall_height_cross_check", None)
        if cross_check and bundle.get("wall_lf_by_class"):
            bundle.setdefault("coverage_notes", []).append(cross_check)
        fused = fuse_sheet(
            bundle,
            vision_labels,
            registry,
            vocabulary=getattr(self, "_project_vocabulary", None),
            wall_height_ft=getattr(self, "_project_wall_height", None),
            wall_height_source=getattr(self, "_project_wall_height_source", None),
            material_tag_ledger=getattr(self, "_material_tag_ledger", None),
            room_mix=dict(room_mix_resolution.counts),
            room_mix_meta=_room_mix_meta_payload(
                room_mix_resolution, getattr(self, "_manifest", None)
            ),
        )
        merged = merge_with_provenance([fused])

        # QuantityVerifier on the fused result → targeted-crop verify-retry
        # (21-14, V3-ACC-05): out-of-band quantities and ensemble
        # disagreements get a bounded narrow crop question to the dense model
        # before human review — flags resolve or persist, never vanish.
        verifier_flags = QuantityVerifier().verify(merged, sheet_name=sheet_name)
        if verifier_flags:
            merged["_verifier_flags"] = verifier_flags
        if self._settings.verify_retry_enabled:
            self._verify_retry_pass(
                merged,
                page,
                registry,
                sheet_name=sheet_name,
                resolved_type=resolved_type,
                legend_labels=legend_labels,
                guard=guard,
            )

        # ── Result metadata (additive keys only) ──────────────────────────
        merged["measurement_mode"] = "vector"
        merged["scale_confidence"] = [
            dict(
                region_id=vp.region_id,
                kind=vp.kind,
                is_main=(vp.region_id == main_id),
                **vs.to_dict(),
            )
            for vp, vs in viewports_with_scales
        ]
        # Deterministic main-plan selection is the measurement authority;
        # the vision answer is kept as a semantic cross-check.
        merged["main_plan_region"] = main_id or fused.get("main_plan_region")
        vision_main = fused.get("main_plan_region")
        if vision_main and main_id and vision_main != main_id:
            logger.info(
                "run_sheet: %r — vision main-plan answer %s disagrees with "
                "deterministic selection %s (deterministic kept)",
                sheet_name, vision_main, main_id,
            )
            merged["main_plan_region_vision"] = vision_main
        try:
            merged["_scale_resolved"] = asdict(scale)
        except TypeError:
            merged["_scale_resolved"] = None
        merged["_deterministic_schedules"] = [
            s.to_dict() if hasattr(s, "to_dict") else s for s in schedules
        ]

        if budget_exhausted:
            merged["_budget_exhausted"] = True
            merged["needs_review"] = True
            merged["review_reason"] = "budget_exhausted"
            for comp in merged.get("components") or []:
                if not isinstance(comp, dict):
                    continue
                reason = str(comp.get("review_reason") or "")
                if comp.get("needs_review") and "label" in reason:
                    comp["review_reason"] = _append_reason(reason, "budget_exhausted")

        # Existing verify-UI support: scale-independent raw geometry.
        if resolved_type in _PLAN_SHEET_TYPES:
            geom = self._measure_geometry_safe(pdf_path, page_index, None)
            if geom is not None:
                merged["_geometry"] = geom

        # Coverage records travel with the sheet so run_project can copy them
        # onto the ledger row. `fuse_sheet` mutates the SAME bundle dict, so its
        # own notes and item-coverage rows are read back here after the call.
        merged["_excluded_viewports"] = bundle.get("excluded_viewports") or []
        merged["_coverage_drops"] = bundle.get("coverage_drops") or []
        merged["_coverage_notes"] = bundle.get("coverage_notes") or []
        merged["_item_coverage"] = bundle.get("item_coverage") or []

        merged["_source_sheet"] = image_path
        merged["_sheet_type"] = resolved_type
        merged["_sheet_name"] = sheet_name
        merged["_passes_run"] = passes_run
        merged["_budget"] = _budget_state(guard)
        return merged

    def _verify_retry_pass(
        self,
        merged: dict,
        page,
        registry: dict,
        *,
        sheet_name: str,
        resolved_type: str,
        legend_labels: List[str],
        guard: Optional[BudgetGuard],
    ) -> None:
        """Post-fusion targeted-crop verify-retry (21-14, V3-ACC-05).

        Builds the retry queue from the QuantityVerifier's out-of-band flags
        plus any ensemble-disagreement components (``needs_review`` from a
        vote), hands it to :func:`retry_flagged_items` (module-level import
        — patchable) with the run BudgetGuard, then merges resolutions back:

        - ``relabeled`` → the component is renamed (SEMANTICS only — its
          deterministic quantity/unit are untouched) and un-flagged with the
          retry history attached;
        - ``confirmed`` → the flag is downgraded to a note (``needs_review``
          cleared where it was set) with the retry history attached;
        - ``unresolved`` → the flag persists exactly as before, now carrying
          its retry history (flag, never suppress).
        """
        components = [
            c for c in merged.get("components") or [] if isinstance(c, dict)
        ]

        def _find_component(item_name, candidate_id=None) -> Optional[dict]:
            if candidate_id:
                for comp in components:
                    if comp.get("candidate_id") == candidate_id:
                        return comp
            norm = str(item_name or "").strip().lower()
            if not norm:
                return None
            for comp in components:
                if str(comp.get("name") or "").strip().lower() == norm:
                    return comp
            return None

        queue: List[dict] = []
        queued = set()

        # 1. Out-of-band QuantityVerifier flags. On vector sheets the
        # deterministic count of a symbol group is exact, so an out-of-band
        # value on a symbol-anchored item usually means the LABEL is wrong —
        # those flags get the plausible legend labels as their choice set
        # (relabel path); everything else gets the confirm/deny question.
        for flag in merged.get("_verifier_flags") or []:
            rec = dict(flag)
            rec.setdefault("flag_type", "out_of_band")
            comp = _find_component(rec.get("item"), rec.get("candidate_id"))
            if comp is not None and not rec.get("candidate_id"):
                rec["candidate_id"] = comp.get("candidate_id")
            cid = rec.get("candidate_id")
            kind = (registry.get(cid) or {}).get("kind") if cid else None
            if kind == "symbol_group" and legend_labels:
                rec["choices"] = list(legend_labels)
            queue.append(rec)
            queued.add(str(rec.get("item") or "").strip().lower())

        # 2. Ensemble-disagreement components (needs_review set by a vote)
        # also enter the retry queue (RESEARCH §3 handoff 3).
        for comp in components:
            if not comp.get("needs_review"):
                continue
            reason = str(comp.get("review_reason") or "").lower()
            if not any(m in reason for m in _ENSEMBLE_DISAGREEMENT_MARKERS):
                continue
            key = str(comp.get("name") or "").strip().lower()
            if not key or key in queued:
                continue
            queue.append(
                {
                    "sheet": sheet_name,
                    "item": comp.get("name"),
                    "qty": comp.get("quantity"),
                    "unit": comp.get("unit"),
                    "flag_type": "ensemble_disagreement",
                    "candidate_id": comp.get("candidate_id"),
                }
            )
            queued.add(key)

        if not queue:
            return

        try:
            updated = retry_flagged_items(
                queue,
                page,
                registry,
                self._analyzer,
                guard,
                sheet_type=resolved_type,
            )
        except Exception as exc:  # noqa: BLE001 — arbitration is additive
            logger.warning(
                "run_sheet: %r — verify-retry pass failed: %s", sheet_name, exc
            )
            return

        verifier_flags: List[dict] = []
        for rec in updated:
            comp = _find_component(rec.get("item"), rec.get("candidate_id"))
            history = rec.get("retry_history")
            resolution = rec.get("resolution")
            if comp is not None and history:
                # retry_history is mandatory on any changed item — a flag can
                # never be altered without its recorded resolution trail.
                comp["retry_history"] = list(history)
                comp["resolution"] = resolution
                if resolution == "relabeled" and rec.get("new_label"):
                    # Semantics only: the name changes; the deterministic
                    # quantity/unit are NEVER touched by a retry.
                    comp["name"] = rec["new_label"]
                    comp["needs_review"] = False
                    comp["review_reason"] = "relabeled by verify-retry"
                elif resolution == "confirmed" and comp.get("needs_review"):
                    # Flag downgraded to a note — the reason is kept for
                    # audit, review is no longer required.
                    comp["needs_review"] = False
                    comp["review_reason"] = _append_reason(
                        comp.get("review_reason"), "confirmed by verify-retry"
                    )
            if rec.get("flag_type") == "out_of_band":
                verifier_flags.append(rec)

        if merged.get("_verifier_flags"):
            merged["_verifier_flags"] = verifier_flags
        merged["_verify_retry"] = updated

    def _run_sheet_raster(
        self,
        image_path: str,
        sheet_name: str,
        resolved_type: str,
        guard: BudgetGuard,
    ) -> dict:
        """Raster fallback: N-sample ensemble vision estimate, all flagged.

        The existing extraction is wrapped in run_ensemble
        (N = settings.ensemble_n) using raster_extraction_schema — the ONLY
        schema with numeric fields. Per-item voting: unanimous across every
        sample → medium confidence (never high — these are estimates);
        anything else → low + needs_review. Budget exhaustion flags the
        remaining items with reason "budget_exhausted" (never a silent
        partial).
        """
        schema = raster_extraction_schema()
        samples: List[dict] = []

        def _sample_call(sample_index=0, temperature=None, prompt_variation=0):
            if guard is not None and guard.exhausted:
                raise BudgetExceeded(guard.spent_usd, guard.max_usd)
            res = self._analyzer(
                image_path,
                sheet_name,
                pass_type="measure",
                sheet_type=resolved_type,
                output_schema=schema,
            )
            if guard is not None:
                # Refused charge → the sample is discarded (unpaid work is
                # never voted); BudgetExceeded propagates out of run_ensemble.
                guard.charge(_result_cost_usd(res))
            if isinstance(res, dict):
                samples.append(res)
            return res

        budget_exhausted = False
        try:
            # Charging happens inside the closure (exact paid-sample ledger);
            # run_ensemble handles the fan-out/temperature ladder. Escalation
            # is off: per-item voting below decides agreement, not the
            # scalar-vote interim (which sees no numeric samples here).
            run_ensemble(
                _sample_call,
                n=self._settings.ensemble_n,
                escalate_on_disagreement=False,
                budget=None,
                unit_kind="EA",
                probe_key="raster:%s" % resolved_type,
            )
        except BudgetExceeded:
            budget_exhausted = True
            logger.warning(
                "run_sheet: %r — budget exhausted on the raster ensemble "
                "after %d paid sample(s); items flagged budget_exhausted",
                sheet_name, len(samples),
            )

        valid_samples = [s for s in samples if not s.get("error")]

        # Per-item vote over the sample vector (RESEARCH §4 thresholds).
        collected: dict = {}
        order: list = []
        for sample in valid_samples:
            for comp in sample.get("components") or []:
                if not isinstance(comp, dict) or not comp.get("name"):
                    continue
                unit = str(comp.get("unit") or "ea").strip().lower()
                key = (str(comp["name"]).strip().lower(), unit)
                entry = collected.get(key)
                if entry is None:
                    entry = {"name": comp["name"], "unit": unit, "votes": []}
                    collected[key] = entry
                    order.append(key)
                qty = comp.get("count_estimate", comp.get("quantity"))
                try:
                    if qty is not None:
                        entry["votes"].append(float(qty))
                except (TypeError, ValueError):
                    pass

        components: List[dict] = []
        n_valid = len(valid_samples)
        for key in order:
            entry = collected[key]
            unit = entry["unit"]
            result = vote(entry["votes"], "EA" if unit == "ea" else unit.upper())
            if result.value is None:
                continue
            unanimous = (
                result.confidence == "high"
                and result.n_samples >= 2
                and result.n_samples == n_valid
            )
            quantity = result.value
            if unit == "ea":
                quantity = int(round(quantity))
            if unanimous:
                confidence, needs_review, reason = "medium", False, ""
            else:
                confidence, needs_review = "low", True
                reason = "raster vision estimate (ensemble not unanimous)"
            components.append(
                {
                    "name": entry["name"],
                    "quantity": quantity,
                    "unit": unit,
                    "confidence": confidence,
                    "provenance": "vision_ensemble",
                    "needs_review": needs_review,
                    "review_reason": reason,
                    "votes": result.votes,
                    "vote_spread": round(result.spread, 4),
                    "method": "raster_ensemble",
                }
            )

        merged: dict = {
            "components": components,
            "measurements": [],
            "measurement_mode": "raster",
            "fusion_rejected": [],
        }
        merged.update(_sum_usage(samples))
        if budget_exhausted:
            merged["_budget_exhausted"] = True
            merged["needs_review"] = True
            merged["review_reason"] = "budget_exhausted"
            for comp in components:
                comp["needs_review"] = True
                comp["review_reason"] = _append_reason(
                    comp.get("review_reason"), "budget_exhausted"
                )

        verifier_flags = QuantityVerifier().verify(merged, sheet_name=sheet_name)
        if verifier_flags:
            merged["_verifier_flags"] = verifier_flags

        merged["_source_sheet"] = image_path
        merged["_sheet_type"] = resolved_type
        merged["_sheet_name"] = sheet_name
        merged["_passes_run"] = ["raster_ensemble"]
        merged["_budget"] = _budget_state(guard)
        logger.info(
            "run_sheet: %r measured on the RASTER fallback path — %d item(s), "
            "all vision_ensemble provenance", sheet_name, len(components),
        )
        return merged

    def _measure_geometry_safe(self, pdf_path, page_index, scale_text):
        """Run the vector-geometry measurement for a sheet; never fatal."""
        try:
            from bobbytailor.deterministic.geometry_takeoff import measure_geometry
            doc = fitz.open(pdf_path)
            try:
                page = doc[page_index]
                m = measure_geometry(
                    page, scale_text=scale_text,
                    override_feet_per_inch=getattr(self, "_scale_fpi", None),
                )
                return m.to_dict()
            finally:
                doc.close()
        except Exception as exc:  # noqa: BLE001 - measurement assist is best-effort
            logger.debug("geometry measurement skipped: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_vocabulary_page(self, pages: "list[dict]") -> Optional[dict]:
        """Pick a VECTOR plan-body page to seed the project vocabulary, or None.

        The vocabulary labels only feed the vector symbol-gallery candidate
        list (``_run_sheet_vector``). So the pass is gated on the existence of
        at least one vector-eligible plan page: deterministic routing enabled,
        not raster-forced, a source PDF page, a plan-body sheet type, and the
        PDF page actually being vector. Returns the first such page (its image
        is the estimator's main visual). Returns None when no sheet would ever
        consume the vocabulary — so no wasted spend on legacy/raster-only runs.
        """
        if not self._settings.deterministic_enabled or self._settings.raster_force:
            return None
        for page in pages or []:
            image_path = page.get("image_path")
            pdf_path = page.get("pdf_path")
            page_index = page.get("page_index")
            if not image_path or pdf_path is None or page_index is None:
                continue
            resolved = page.get("sheet_type_hint") or page.get("sheet_type")
            if not resolved:
                resolved = classify_sheet_type_from_text(
                    page.get("title_block_text", ""), page.get("full_page_text", "")
                )
            if resolved not in _PLAN_SHEET_TYPES:
                continue
            try:
                doc = fitz.open(pdf_path)
                try:
                    if is_vector_sheet(doc[page_index]):
                        return page
                finally:
                    doc.close()
            except Exception as exc:  # noqa: BLE001 — unreadable PDF → skip page
                logger.debug(
                    "_select_vocabulary_page: %s page %s unreadable (%s)",
                    pdf_path, page_index, exc,
                )
        return None

    def _load_persisted_vocabulary(
        self, project_key: Optional[str], kind: str
    ) -> list:
        """THIS project's stored vocabulary snapshot, canonicalised — or ``[]``.

        Best-effort in the module's established style: a missing key, learning
        disabled, an unreadable store or an un-foldable payload all return
        ``[]``, and ``[]`` means "derive fresh". A persisted vocabulary is an
        optimisation and a determinism aid; it may never break a run.
        """
        if not project_key or not getattr(
            self._settings, "learning_enabled", True
        ):
            return []
        try:
            stored = load_project_vocabulary(project_key, kind)
        except Exception as exc:  # noqa: BLE001 — additive, never break a run
            logger.warning(
                "_load_persisted_vocabulary: %s snapshot for %r unreadable "
                "(%s) — deriving fresh", kind, project_key, exc,
            )
            return []
        if not stored:
            return []
        try:
            return _canonicalise_persisted_vocabulary(stored)
        except Exception as exc:  # noqa: BLE001 — the fold is additive too
            logger.warning(
                "_load_persisted_vocabulary: canonicalising the %s snapshot "
                "for %r failed (%s) — using it unfolded",
                kind, project_key, exc,
            )
            return [obj for obj in stored if isinstance(obj, dict)]

    def _save_persisted_vocabulary(
        self, project_key: Optional[str], objects: list, kind: str
    ) -> int:
        """Store the just-derived vocabulary so the NEXT run reuses it.

        Saves the POST-VOTE list, never a single sample: the vote is what makes
        the list stable, and persisting one stochastic sample would freeze the
        noise instead of the answer. Best-effort — a store failure costs the
        next run its saving and nothing else.
        """
        if not project_key or not objects or not getattr(
            self._settings, "learning_enabled", True
        ):
            return 0
        try:
            n = save_project_vocabulary(project_key, objects, kind=kind)
        except Exception as exc:  # noqa: BLE001 — additive, never break a run
            logger.warning(
                "_save_persisted_vocabulary: storing the %s snapshot for %r "
                "failed (%s) — the next run re-derives", kind, project_key, exc,
            )
            return 0
        if n:
            logger.info(
                "run_project: persisted the %s snapshot for %r → %d object "
                "type(s); the next run reuses it instead of calling the API",
                kind, project_key, n,
            )
        return n

    def _build_project_vocabulary(
        self,
        image_path: str,
        plan_text: str,
        guard: Optional[BudgetGuard],
        project_key: Optional[str] = None,
    ) -> list:
        """Build the project vocabulary ONCE (budget-charged, best-effort).

        Delegates to :func:`object_vocabulary.build_project_vocabulary` with
        the injected analyzer so budget is charged uniformly via the guard;
        stores the parsed objects on ``self._project_vocabulary`` and the flat
        deduped names+aliases feed on ``self._project_vocab_labels``. Any
        failure leaves both empty (additive-only — never breaks a run).

        The vocabulary pass is run N times (``ensemble_settings()["n"]``,
        budget permitting) and object PRESENCE is majority-voted
        (:func:`object_vocabulary.majority_vote_objects`) so a stochastic
        "unknown" run can no longer drop a real object (Exposed Structure,
        Columns, ...) that every other run names. ``n <= 1`` (or a single paid
        sample) is exactly today's single-shot behaviour.

        PERSISTED FIRST (24-05, defect F3). When this project already has a
        stored snapshot, it is loaded, canonicalised and returned, and the
        sampling loop below is skipped ENTIRELY — no API call at all. That is
        the point: ``map_wall_classes_from_library``'s object list came from
        this method, so re-deriving it every run made a deterministic wall
        classifier non-deterministic (run 1 said `Metal Downspout`, run 2 said
        `Metal Downspouts`). A first run derives as before and saves the voted
        result. Every failure degrades to exactly today's behaviour.
        """
        persisted = self._load_persisted_vocabulary(project_key, VOCAB_KIND_PROJECT)
        if persisted:
            self._project_vocabulary = persisted
            self._project_vocab_labels = vocabulary_labels(persisted)
            logger.info(
                "run_project: project vocabulary REUSED from %r's persisted "
                "snapshot → %d object type(s), %d candidate label(s); no "
                "project-level vocabulary API call made",
                project_key, len(persisted), len(self._project_vocab_labels),
            )
            return self._project_vocabulary

        try:
            n = int(ensemble_settings()["n"])
        except Exception:  # noqa: BLE001 — config stubbed → single-shot
            n = 1
        n = max(1, n)

        samples: list = []
        for _ in range(n):
            if guard is not None and getattr(guard, "exhausted", False):
                break
            try:
                objs = build_project_vocabulary(
                    self._analyzer,
                    image_path,
                    plan_text,
                    guard=guard,
                    sheet_name="project",
                )
            except Exception as exc:  # noqa: BLE001 — vocabulary is strictly additive
                logger.warning("_build_project_vocabulary: failed: %s", exc)
                objs = []
            samples.append(objs or [])
            if n <= 1:
                break

        if len(samples) <= 1:
            objects = samples[0] if samples else []
        else:
            try:
                objects = majority_vote_objects(samples)
            except Exception as exc:  # noqa: BLE001 — additive, never break a run
                logger.warning("_build_project_vocabulary: vote failed: %s", exc)
                objects = samples[0] if samples else []
        self._project_vocabulary = objects or []
        self._project_vocab_labels = vocabulary_labels(self._project_vocabulary)
        # Save the POST-VOTE list so the next run reuses this exact object set.
        self._save_persisted_vocabulary(
            project_key, self._project_vocabulary, VOCAB_KIND_PROJECT
        )
        if self._project_vocab_labels:
            logger.info(
                "run_project: project vocabulary → %d object type(s), %d candidate label(s)",
                len(self._project_vocabulary), len(self._project_vocab_labels),
            )
        return self._project_vocabulary

    def _build_naming_conventions(
        self,
        image_path: str,
        naming_text: str,
        guard: Optional[BudgetGuard],
        project_key: Optional[str] = None,
    ) -> list:
        """Build THIS plan's naming-convention library ONCE (voted, best-effort).

        Delegates to :func:`object_vocabulary.extract_naming_conventions` with
        the injected analyzer (budget-charged uniformly). Run N times
        (``ensemble_settings()["n"]``, budget permitting) and majority-KEPT
        (:func:`object_vocabulary.majority_keep_conventions`) so a stochastic
        run cannot drop an object every other run names. Returns the cleaned
        convention objects (``canonical_name`` / ``aliases`` / ``basis`` /
        ``binding_hint`` / ``variant`` / ``thickness_in`` / ``height_ft``); any
        failure returns ``[]`` (additive-only — never breaks a run).

        PERSISTED FIRST (24-05, defect F3). This is the LIVE project-level API
        pass — the one the saved evidence charges $0.422 of a $0.599 run for,
        70% of it. A repeat run over the same project loads the stored
        snapshot, canonicalises it and skips the sampling loop entirely, which
        both removes that spend and stops the naming library changing
        underneath the deterministic wall classifier between runs.
        """
        persisted = self._load_persisted_vocabulary(
            project_key, VOCAB_KIND_NAMING_CONVENTIONS
        )
        if persisted:
            logger.info(
                "run_project: naming conventions REUSED from %r's persisted "
                "snapshot → %d object type(s); no naming-convention API call "
                "made", project_key, len(persisted),
            )
            return persisted

        try:
            n = int(ensemble_settings()["n"])
        except Exception:  # noqa: BLE001 — config stubbed → single-shot
            n = 1
        n = max(1, n)

        samples: list = []
        for _ in range(n):
            if guard is not None and getattr(guard, "exhausted", False):
                break
            try:
                objs = extract_naming_conventions(
                    self._analyzer,
                    image_path,
                    naming_text,
                    guard=guard,
                    sheet_name="project",
                )
            except Exception as exc:  # noqa: BLE001 — naming is strictly additive
                logger.warning("_build_naming_conventions: failed: %s", exc)
                objs = []
            samples.append(objs or [])
            if n <= 1:
                break

        if len(samples) <= 1:
            conventions = samples[0] if samples else []
        else:
            try:
                conventions = majority_keep_conventions(samples)
            except Exception as exc:  # noqa: BLE001 — additive, never break a run
                logger.warning("_build_naming_conventions: vote failed: %s", exc)
                conventions = samples[0] if samples else []
        # Save the POST-VOTE list so the next run reuses this exact object set.
        self._save_persisted_vocabulary(
            project_key, conventions, VOCAB_KIND_NAMING_CONVENTIONS
        )
        return conventions

    def run_project(
        self,
        pages: list[dict],
        progress_callback=None,
        project_legend_schedules: Optional[list] = None,
        manifest=None,
        scale_feet_per_inch: Optional[float] = None,
        project_key: Optional[str] = None,
        *,
        coverage: Optional[CoverageLedger] = None,
    ) -> "tuple[list[dict], list[dict], str]":
        """Run the full pipeline for every page in a project.

        Args:
            pages: List of page dicts.  Supported keys::

                   image_path        (str, required) — path to screenshot/image
                   sheet_name        (str, required) — sheet identifier
                   sheet_type_hint   (str, optional) — pre-classified sheet type;
                                     when absent, auto-classified from title-block text
                   title_block_text  (str, optional) — OCR text for auto-classification
                   page_num          (int, optional) — original page index for tagging

            progress_callback: Optional ``callable(current, total, sheet_name)``
                called once per page before extraction begins.
            coverage: KEYWORD-ONLY, default None. The run's CoverageLedger,
                already carrying one row per page of the source PDF. Each
                page's row is threaded into ``run_sheet`` and enriched in
                place, so a page that never becomes an entry in
                ``all_extracted`` still leaves a record of itself. Exposed
                afterwards as ``self.coverage_ledger``.

        Returns:
            A ``(all_extracted, all_estimates, project_type)`` tuple:

            - ``all_extracted`` — merged pipeline dicts for non-skipped sheets
              (title_sheet pages are excluded)
            - ``all_estimates``  — flat list from ``apply_estimation_tables``
              with ``project_type`` applied uniformly across all sheets
            - ``project_type``   — type key detected once from all extracted data

        Notes:
            ``_detect_project_type`` and ``apply_estimation_tables`` are imported
            lazily inside this method to avoid a circular dependency between
            ``takeoff_pipeline`` and ``calculator``.
        """
        # Lazy import — calculator does not import takeoff_pipeline.
        from bobbytailor.pipeline.calculator import apply_estimation_tables, _detect_project_type  # noqa: PLC0415

        # The run's coverage ledger (INV-08 / SP-8). pdf_analyzer builds it and
        # registers every source page BEFORE routing; run_sheet enriches each
        # row. Exposed so plan 23-03 can hand it to generate_report.
        self.coverage_ledger = coverage
        # Optional object manifest — used by targeted counting/measurement passes.
        self._manifest = manifest
        # Reliable scale (feet per inch): explicit arg wins, else a manifest
        # project-level assumption `scale_ft_per_in` if present.
        self._scale_fpi = scale_feet_per_inch or _manifest_scale_fpi(manifest)
        # ONE BudgetGuard per run (V3-PROD-02): every vision call in every
        # sheet — legacy passes, semantic/gallery labeling, raster ensemble —
        # charges this guard. Exhaustion flags remaining work, never truncates
        # silently.
        self._run_budget = BudgetGuard(self._settings.budget_usd)
        # Deterministic table cache is per-run (avoid stale cross-run reuse).
        self._schedules_cache = {}
        # Same for the document-level unit-mix resolution.
        self._room_mix_cache = {}
        # And for the elevation width cross-check's reference footprint — a
        # footprint measured in a PREVIOUS project must never validate this
        # project's facades.
        self._project_footprint = None
        # ONE finish-code review ledger per run: the cap on how many distinct
        # codes may open a review row is a RUN-level guarantee, and a per-sheet
        # ledger would be no cap at all (threat T-23-31).
        self._material_tag_ledger = MaterialTagLedger()
        # Learned-context retrieval (21-16, V3-LEARN-03): ONE bundle at run
        # start (project_type inferred from prior corrections for repeat
        # runs) — injected into prompt hints, the per-sheet scale-prior feed,
        # and the guardrail flags. Refreshed once more below when the
        # project_type detector has run, so type-level vocabulary/manifests
        # join for calculator/aggregation. Never per-sheet DB churn.
        self.load_learning(project_key)

        # ── Autonomous project vocabulary (hybrid-naming manifest replacement)
        # Built ONCE for the whole project BEFORE the per-sheet loop: an
        # estimator read of the main plan image + concatenated plan text
        # (keynotes/notes/abbreviations/schedule headers) yields candidate
        # object NAMES that seed the symbol-gallery candidate list so geometry
        # symbol clusters can bind to real names on plans whose schedules are
        # sparse. Best-effort: any failure stores [] and the run continues
        # exactly as before (additive-only). Gated on analyzer availability.
        self._project_vocabulary = []
        self._project_vocab_labels = []
        # Concatenated plan text layer (keynotes / notes / abbreviations /
        # schedule headers across every page) — the estimator's reading source
        # for BOTH the vocabulary pass and the autonomous wall-height resolver.
        plan_text = "\n\n".join(
            part for page in pages for part in (
                page.get("full_page_text", ""),
                page.get("title_block_text", ""),
            ) if part
        )
        # ── Autonomous wall/clear height (manifest replacement) ──────────────
        # Resolved ONCE for the whole project BEFORE the per-sheet loop so the
        # fusion wall_area binding (LF × height → SF) has a height on every
        # sheet. Precedence: learned wall_height_ft > plan-text callout >
        # elevation datum span > flagged 30 ft industrial default. Whatever the
        # source, it is flagged on derived wall-area items — never a silent
        # substitution.
        datum_span_ft = self._project_datum_span(pages)
        wall_height_ft, wall_height_source = _resolve_project_wall_height(
            plan_text, None, self._learned_context,
            datum_span_ft=datum_span_ft,
        )
        self._project_wall_height = wall_height_ft
        self._project_wall_height_source = wall_height_source
        self._wall_height_cross_check = _wall_height_cross_check_note(
            wall_height_ft, wall_height_source, datum_span_ft
        )
        if self._wall_height_cross_check:
            logger.info(
                "run_project: %s", self._wall_height_cross_check
            )
        logger.info(
            "run_project: project wall height → %.1f ft (source=%s)",
            wall_height_ft, wall_height_source,
        )
        # Deterministic component library FIRST (API-free, plans-only naming
        # authority): the plan's own ABBREVIATION key + keynotes/general notes
        # yield stable, run-to-run-identical object NAMES + aliases (Doors-HM,
        # Ladder, Guard Rail, ...) straight from the printed text. This is the
        # authoritative naming source that replaces the deleted manifest.
        deterministic_library: list = []
        naming_text = plan_text
        try:
            from bobbytailor.deterministic.component_library import (  # noqa: PLC0415
                harvest_component_library,
                merge_with_naming_conventions,
                distill_naming_text,
                library_labels,
            )
            deterministic_library = harvest_component_library([plan_text])
            # LEAN, budget-capped naming text (abbreviations / detail labels /
            # object-noun + keynote + schedule lines) — the DISTILLED estimator
            # reading source for the AI naming-convention pass. Deliberately NOT
            # the full 30k-token page dump (that starved the reader on Bob's →
            # invalid_json → no manifest). Falls back to plan_text on failure.
            try:
                naming_text = distill_naming_text(pages) or plan_text
            except Exception as exc:  # noqa: BLE001
                logger.warning("run_project: naming-text distillation failed: %s", exc)
                naming_text = plan_text
        except Exception as exc:  # noqa: BLE001 — library harvest is additive-only
            logger.warning("run_project: component-library harvest failed: %s", exc)
            deterministic_library = []

        # AI NAMING-CONVENTION pass (plans-only, voted, semantic-only): reads the
        # plan's OWN notes/details/abbreviations/schedules and reports THIS
        # plan's naming library — name/aliases/basis PLUS the binding_hint /
        # variant / thickness that DRIVE geometry binding (columns, bollards,
        # tilt-up interior/exterior, CMU). Best-effort: any failure leaves the
        # deterministic library unchanged (additive-only). Gated on analyzer.
        naming_conventions: list = []
        if self._analyzer is not None:
            vocab_page = self._select_vocabulary_page(pages)
            if vocab_page is not None:
                naming_conventions = self._build_naming_conventions(
                    vocab_page["image_path"], naming_text, self._run_budget,
                    project_key=project_key,
                ) or []

        # Merge: deterministic entries are AUTHORITATIVE for names/aliases; the
        # AI naming pass fills a missing basis + the binding fields and adds
        # objects the printed text missed. Additive: empty conventions ⇒ the
        # deterministic library unchanged (prior behavior).
        try:
            merged = merge_with_naming_conventions(
                deterministic_library, naming_conventions
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("run_project: naming-convention merge failed: %s", exc)
            merged = deterministic_library
        if merged:
            self._project_vocabulary = merged
            try:
                self._project_vocab_labels = library_labels(merged)
            except Exception:  # noqa: BLE001
                pass
            logger.info(
                "run_project: naming library → %d object type(s) "
                "(%d deterministic, %d naming), %d candidate label(s)",
                len(self._project_vocabulary), len(deterministic_library),
                len(naming_conventions), len(self._project_vocab_labels),
            )

        total = len(pages)
        all_extracted: list[dict] = []
        verifier = QuantityVerifier()

        for i, page in enumerate(pages, 1):
            image_path = page["image_path"]
            sheet_name = page.get("sheet_name", f"Page_{i}")
            sheet_type = page.get("sheet_type_hint") or page.get("sheet_type")
            title_block_text = page.get("title_block_text", "")

            if progress_callback:
                progress_callback(i, total, sheet_name)

            page_index = page.get("page_index")
            sheet_coverage = (
                coverage.sheet(page_index)
                if coverage is not None and page_index is not None
                else None
            )
            if sheet_coverage is not None:
                sheet_coverage.sheet_name = sheet_name

            extracted = self.run_sheet(
                image_path=image_path,
                sheet_name=sheet_name,
                sheet_type=sheet_type,
                title_block_text=title_block_text,
                full_page_text=page.get("full_page_text", ""),
                pdf_path=page.get("pdf_path"),
                page_index=page_index,
                budget=self._run_budget,
                coverage=sheet_coverage,
            )

            # Tag original page number for downstream reporters.
            extracted["_page_num"] = page.get("page_num", i)
            # ...and the SOURCE page index, so a later stage (the errored-sheet
            # guard below) can find this sheet's ledger row by identity rather
            # than by matching a display name.
            extracted["_page_index"] = page_index

            if extracted.get("_skipped"):
                # The sentinel stays OUT of all_extracted (every downstream
                # contract is preserved) — but the page is no longer invisible:
                # run_sheet has already written the reason, the deciding keyword
                # and the measurable signal onto its ledger row. Backstop that
                # here so a skip taken on a path that did NOT see the ledger
                # (a caller passing coverage=None into run_sheet, a future
                # sentinel) still lands as a recorded disposition rather than a
                # row that reads `measured` by default — the exact shape of
                # INV-08 §2 row S2.
                if sheet_coverage is not None:
                    if sheet_coverage.disposition == MEASURED:
                        sheet_coverage.disposition = (
                            NOT_APPLICABLE
                            if not sum(
                                (extracted.get("_measurable_signal") or {}).values()
                            )
                            else SKIPPED_CLASSIFIER
                        )
                    if not sheet_coverage.reason:
                        sheet_coverage.reason = str(
                            extracted.get("_skip_reason") or "no reason recorded"
                        )
                    sheet_coverage.items_emitted = 0
                logger.info(
                    "run_project: skipping %r (sheet_type=%s) — %s",
                    sheet_name, extracted.get("sheet_type"),
                    extracted.get("_skip_reason", "no reason recorded"),
                )
                continue

            # Prefer to attach the authoritative companion take-off legend to a
            # floor_plan sheet (most natural home), but only once per project.
            if project_legend_schedules and extracted.get("_sheet_type") == "floor_plan":
                if not any(
                    e.get("_companion_legend_injected")
                    for e in all_extracted
                ):
                    existing = list(extracted.get("schedules") or [])
                    extracted["schedules"] = existing + list(project_legend_schedules)
                    extracted["_companion_legend_injected"] = True
                    logger.info(
                        "Injected %d companion legend rows into %r",
                        sum(len(s.get("rows") or []) for s in project_legend_schedules),
                        sheet_name,
                    )

            all_extracted.append(extracted)

            # Copy this sheet's coverage records onto its ledger row. Without
            # this the drawing-level drops recorded in _deterministic_bundle
            # and _measure_room_fills die inside the sheet dict and never reach
            # a report — which is the whole defect, one layer down.
            if sheet_coverage is not None:
                self._record_sheet_coverage(sheet_coverage, extracted)

        # Fallback: a companion take-off is a PROJECT-level authoritative source.
        # If no floor_plan sheet existed to host it (e.g. an all-elevation/detail
        # set), attach it to the first non-skipped sheet so the take-off is never
        # silently dropped. Without this, plan sets lacking a "floor_plan" sheet
        # would fall back to vision-only and lose accuracy.
        if project_legend_schedules and not any(
            e.get("_companion_legend_injected") for e in all_extracted
        ):
            for extracted in all_extracted:
                existing = list(extracted.get("schedules") or [])
                extracted["schedules"] = existing + list(project_legend_schedules)
                extracted["_companion_legend_injected"] = True
                logger.info(
                    "Injected %d companion legend rows into %r (fallback — no floor_plan sheet)",
                    sum(len(s.get("rows") or []) for s in project_legend_schedules),
                    extracted.get("_sheet_name", extracted.get("_source_sheet", "?")),
                )
                break

        # Project-type detection runs ONCE across all non-skipped sheets so
        # apply_estimation_tables uses a consistent type for the whole set.
        project_type = _detect_project_type(all_extracted)
        logger.info(
            "run_project: project_type=%r across %d sheets",
            project_type, len(all_extracted),
        )

        # Refresh the learned context with the DETECTED project_type so the
        # type-level vocabulary/assumptions/expected-items join the bundle
        # for the calculator and downstream aggregation (RESEARCH §6).
        if project_key and self._settings.learning_enabled:
            self.load_learning(project_key, project_type)

        # Persist the AI naming manifest (learn-ai-manifest): the Opus-built
        # project vocabulary is upserted into learning_vocabulary as
        # source='ai' at a modest weight so it ACCUMULATES a growing autonomous
        # naming dictionary across runs (human corrections still outrank it —
        # retrieval ranks source='human' first). Best-effort: a store failure
        # must NEVER break a run (additive, wrapped, logged non-fatal).
        if (
            project_key
            and self._settings.learning_enabled
            and getattr(self, "_project_vocabulary", None)
        ):
            try:
                n = record_ai_manifest(
                    project_key, project_type, self._project_vocabulary
                )
                logger.info(
                    "run_project: persisted AI naming manifest → %d vocabulary "
                    "row(s) (source='ai', project_type=%r)",
                    n, project_type,
                )
            except Exception as exc:  # noqa: BLE001 — learning must never break a run
                logger.warning(
                    "run_project: AI-manifest persistence failed "
                    "(project_key=%r) — run continues without it: %s",
                    project_key, exc,
                )

        # Wall height for derived wall-area estimates: manifest assumption >
        # learned wall_height_ft (injection point 3b — applies ONLY when no
        # manifest/schedule source exists) > the 9 ft cold-start default.
        # Whatever the source, the assumption is flagged on derived items
        # (assumption_source) — never a silent substitution.
        wall_height_ft, wall_height_source = _resolve_wall_height(
            getattr(self, "_manifest", None), self._learned_context,
        )

        all_estimates: list[dict] = []
        for extracted in all_extracted:
            if "error" in extracted and coverage is not None:
                # An errored sheet is counted as processed but contributes zero
                # estimates, and its error never reaches the report (INV-08 §2
                # row S11) — it renders as a sheet with 0 items, i.e. as a
                # building with none of those things.
                row = coverage.sheet(extracted.get("_page_index")) if extracted.get(
                    "_page_index"
                ) is not None else None
                if row is None:
                    name = extracted.get("_sheet_name") or extracted.get(
                        "_source_sheet", ""
                    )
                    row = next(
                        (r for r in coverage.sheets if r.sheet_name == name), None
                    )
                if row is not None:
                    row.disposition = ERRORED
                    row.reason = str(extracted.get("error") or "sheet analysis failed")
            if "error" not in extracted:
                verifier.verify(
                    extracted,
                    sheet_name=extracted.get("_sheet_name", extracted.get("_source_sheet", "")),
                )
                all_estimates.extend(
                    apply_estimation_tables(
                        extracted, project_type=project_type,
                        wall_height_ft=wall_height_ft,
                        wall_height_source=wall_height_source,
                    )
                )

        # Final run-level budget accounting on every sheet dict (reporter
        # surfaces one run-level {cap_usd, spent_usd, exhausted} block).
        final_budget = _budget_state(self._run_budget)
        for extracted in all_extracted:
            extracted["_budget"] = final_budget

        return all_extracted, all_estimates, project_type

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_pass(
        self,
        image_path: str,
        sheet_name: str,
        pass_type: str,
        model_override: Optional[str],
        sheet_type: Optional[str] = None,
        pdf_path: Optional[str] = None,
        page_index: Optional[int] = None,
        render_scale: Optional[float] = None,
        user_hint: Optional[str] = None,
        legend_region: Optional[str] = None,
        budget: Optional[BudgetGuard] = None,
    ) -> dict:
        """Execute one extraction pass via analyze_drawing, voted where eligible.

        For the IDENTIFICATION pass types (:data:`_VOTED_IDENTIFICATION_PASS_TYPES`
        — the schedule and legend passes, which READ a printed table) this
        samples up to ``ensemble_settings()["n"]`` times and majority-votes the
        tables and rows on ROW IDENTITY (:func:`_vote_schedule_rows`), so a
        single stochastic read can no longer change the take-off's shape. Every
        other pass type, and an ensemble size of one, take the pre-24-08
        single-shot path unchanged and byte-identically.

        Args:
            image_path:     Path to the sheet image.
            sheet_name:     Sheet identifier for logging and model selection.
            pass_type:      Name of the pass ("count", "measure", "schedule").
            model_override: Model slug to use, or None for default.
            budget:         Per-run BudgetGuard; EVERY sample's ``_cost_usd`` is
                            charged. A refused charge raises BudgetExceeded and
                            that result is discarded (the ledger only holds
                            paid-and-accepted work). When the guard runs out
                            part-way through an ensemble, sampling stops and the
                            vote runs over the samples already paid for, with
                            ``_vote_samples`` recording the reduced count — a
                            partial vote is never presented as a full one.

        Raises:
            BudgetExceeded: When the guard is exhausted or refuses the charge
                            before any sample completed.
        """
        if budget is not None and budget.exhausted:
            raise BudgetExceeded(budget.spent_usd, budget.max_usd)
        if model_override:
            logger.info(
                "  pass=%r model=%r sheet=%r", pass_type, model_override, sheet_name
            )
        else:
            logger.info("  pass=%r sheet=%r (default model)", pass_type, sheet_name)

        n = self._identification_ensemble_n(pass_type)
        if n <= 1:
            return self._single_pass(
                image_path, sheet_name, pass_type, model_override, sheet_type,
                pdf_path, page_index, render_scale, user_hint, legend_region,
                budget,
            )

        samples: list = []
        per_sample_cost = 0.0
        for _ in range(n):
            if budget is not None and getattr(budget, "exhausted", False):
                break
            if samples and budget is not None and budget.would_exceed(per_sample_cost):
                # Look before leaping on the EXTRA samples only. A refused
                # charge means the vendor was paid for a call whose result is
                # then discarded; declining to make it is strictly cheaper and
                # cannot change the first sample, which is always attempted.
                logger.info(
                    "_run_pass: %r pass=%r — stopping ensemble at %d/%d samples, "
                    "no budget headroom for another", sheet_name, pass_type,
                    len(samples), n,
                )
                break
            try:
                res = self._single_pass(
                    image_path, sheet_name, pass_type, model_override, sheet_type,
                    pdf_path, page_index, render_scale, user_hint, legend_region,
                    budget,
                )
            except BudgetExceeded:
                break
            if isinstance(res, dict):
                samples.append(res)
                per_sample_cost = max(per_sample_cost, _result_cost_usd(res))

        if not samples:
            # No paid samples — surface the same signal a single call would, so
            # the caller's ``except BudgetExceeded`` flags the sheet. Never a
            # silent empty (phase-23 C2: budget exhaustion stays LOUD).
            if budget is not None:
                raise BudgetExceeded(budget.spent_usd, budget.max_usd)
            return {}

        if len(samples) == 1:
            # Exhausted after one sample. Return that read UNFOLDED — voting
            # over one sample would silently edit it — but record the reduced
            # count so a partial is never mistaken for a full vote (T-24-35).
            result = dict(samples[0])
            result["_voted"] = True
            result["_vote_samples"] = 1
            return result

        base = next((s for s in samples if not s.get("error")), samples[0])
        result = dict(base)
        result["schedules"] = _vote_schedule_rows(samples)
        result.update(_sum_usage(samples))  # aggregate paid usage/cost
        result["_voted"] = True
        result["_vote_samples"] = len(samples)
        return result

    @staticmethod
    def _identification_ensemble_n(pass_type: str) -> int:
        """Ensemble size for *pass_type*: N for identification, 1 for the rest.

        A stubbed or unreadable config degrades to 1 — single-shot, i.e. exactly
        the pre-24-08 behaviour — never to an unbounded fan-out.
        """
        if pass_type not in _VOTED_IDENTIFICATION_PASS_TYPES:
            return 1
        try:
            return int(ensemble_settings()["n"])
        except Exception:  # noqa: BLE001 — config stubbed → single-shot
            return 1

    def _single_pass(
        self,
        image_path: str,
        sheet_name: str,
        pass_type: str,
        model_override: Optional[str],
        sheet_type: Optional[str] = None,
        pdf_path: Optional[str] = None,
        page_index: Optional[int] = None,
        render_scale: Optional[float] = None,
        user_hint: Optional[str] = None,
        legend_region: Optional[str] = None,
        budget: Optional[BudgetGuard] = None,
    ) -> dict:
        """ONE analyze_drawing call: render → call → clean up → charge → guard.

        This is `_run_pass`'s pre-24-08 body verbatim, minus the entry budget
        pre-check and the pass logging, which `_run_pass` still owns so they
        happen once per PASS rather than once per SAMPLE. Each sample renders
        AND unlinks its own temporary pass image in the ``finally`` below, so an
        ensemble cannot leak temp files (T-24-37).
        """
        pass_image = image_path
        if render_scale and pdf_path is not None and page_index is not None:
            if (
                pass_type == "schedule"
                and sheet_type == "floor_plan"
                and legend_region
            ):
                pass_image = self._render_legend_crop(
                    pdf_path, page_index, render_scale, region=legend_region
                )
            elif pass_type == "legend" and pdf_path is not None and page_index is not None:
                pass_image = self._render_pdf_page(pdf_path, page_index, render_scale)
            elif render_scale and pdf_path is not None and page_index is not None:
                pass_image = self._render_pdf_page(pdf_path, page_index, render_scale)

        try:
            result = self._analyzer(
                pass_image,
                sheet_name,
                pass_type=pass_type,
                model_override=model_override,
                sheet_type=sheet_type,
                user_hint=user_hint,
            )
        finally:
            if pass_image != image_path and os.path.isfile(pass_image):
                try:
                    os.unlink(pass_image)
                except OSError:
                    pass

        if budget is not None:
            # Charge the completed call; a refusal raises BudgetExceeded so
            # the (over-budget) result is never merged into the take-off.
            budget.charge(_result_cost_usd(result))

        if not isinstance(result, dict):
            logger.warning(
                "_run_pass: analyze_drawing returned non-dict for %r pass=%r",
                sheet_name, pass_type,
            )
            return {}

        return result

    @staticmethod
    def _render_legend_crop(
        pdf_path: str,
        page_index: int,
        scale: float,
        region: str = "right",
    ) -> str:
        """Render a plan margin band where quantity takeoff legends often appear."""
        from bobbytailor.pipeline.pdf_analyzer import _effective_render_scale

        doc = fitz.open(pdf_path)
        try:
            page = doc[page_index]
            scale = _effective_render_scale(page, scale * 1.5)
            r = page.rect
            clips = {
                "right": fitz.Rect(r.width * 0.52, r.height * 0.02, r.width * 0.99, r.height * 0.48),
                "left": fitz.Rect(r.width * 0.01, r.height * 0.02, r.width * 0.48, r.height * 0.48),
                "bottom": fitz.Rect(r.width * 0.05, r.height * 0.50, r.width * 0.95, r.height * 0.95),
            }
            clip = clips.get(region, clips["right"])
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip)
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            pix.save(path)
            return path
        finally:
            doc.close()

    def _tiled_recount(
        self,
        count_result: dict,
        pdf_path: str,
        page_index: int,
        sheet_name: str,
        sheet_type: str,
        model_override: Optional[str],
        budget: Optional[BudgetGuard] = None,
    ) -> dict:
        """Recover manifest count-objects missed by the full-sheet count pass.

        For each manifest EA object that came back null/0 on the whole sheet, tile
        the page (no overlap), count that object per tile, and sum. Adopt the tiled
        sum only when it beats the full-sheet count (``max``), so this can only
        ADD recall, never silently lower an already-found count. Tiled counts are
        flagged low-confidence because boundary symbols are imperfectly handled.
        """
        manifest = getattr(self, "_manifest", None)
        if not manifest:
            return count_result

        components = list(count_result.get("components") or [])

        def _found_qty(entry) -> float:
            total = 0.0
            for c in components:
                if manifest.resolve(c.get("name", ""), c.get("unit", "")) is entry:
                    try:
                        total += float(c.get("quantity") or 0)
                    except (TypeError, ValueError):
                        pass
            return total

        missing = [
            e for e in manifest.entries
            if e.measure in ("count", "each") and _found_qty(e) <= 0
        ]
        if not missing:
            return count_result

        cols, rows = count_tiling_grid()
        hint = (
            "TARGETED COUNT (cropped region). Count ONLY these objects visible in "
            "this crop; report your best count with confidence. Omit objects not "
            "present:\n" + "\n".join(
                "  - " + " / ".join(dict.fromkeys([e.name, *e.aliases])) for e in missing
            )
        )

        tile_totals: dict = {e.name: 0.0 for e in missing}
        for cx in range(cols):
            for ry in range(rows):
                if budget is not None and budget.exhausted:
                    raise BudgetExceeded(budget.spent_usd, budget.max_usd)
                tile_path = self._render_tile(pdf_path, page_index, 2.5, cols, rows, cx, ry)
                try:
                    res = self._analyzer(
                        tile_path, sheet_name, pass_type="count",
                        model_override=model_override, sheet_type=sheet_type,
                        user_hint=hint,
                    )
                finally:
                    if os.path.isfile(tile_path):
                        try:
                            os.unlink(tile_path)
                        except OSError:
                            pass
                if budget is not None:
                    budget.charge(_result_cost_usd(res))
                for c in (res or {}).get("components") or []:
                    entry = manifest.resolve(c.get("name", ""), c.get("unit", ""))
                    if entry is None or entry.name not in tile_totals:
                        continue
                    try:
                        tile_totals[entry.name] += float(c.get("quantity") or 0)
                    except (TypeError, ValueError):
                        pass

        for e in missing:
            tiled = tile_totals.get(e.name, 0.0)
            if tiled > 0:
                components.append({
                    "name": e.name,
                    "quantity": round(tiled),
                    "unit": e.unit or "ea",
                    "method": "tile-sum",
                    "confidence": "low",
                    "location": f"tiled recount {cols}x{rows}",
                    "notes": "recovered via region tiling; verify count",
                })
                logger.info("Tiled recount recovered %s = %s", e.name, round(tiled))

        count_result = dict(count_result)
        count_result["components"] = components
        return count_result

    @staticmethod
    def _render_tile(
        pdf_path: str, page_index: int, scale: float,
        cols: int, rows: int, cx: int, ry: int,
    ) -> str:
        """Render one (cx, ry) tile of a grid over the page to a temp PNG."""
        from bobbytailor.pipeline.pdf_analyzer import _effective_render_scale

        doc = fitz.open(pdf_path)
        try:
            page = doc[page_index]
            scale = _effective_render_scale(page, scale)
            r = page.rect
            tw, th = r.width / cols, r.height / rows
            clip = fitz.Rect(cx * tw, ry * th, (cx + 1) * tw, (ry + 1) * th)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip)
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            pix.save(path)
            return path
        finally:
            doc.close()

    @staticmethod
    def _render_pdf_page(pdf_path: str, page_index: int, scale: float) -> str:
        """Render one PDF page to a temporary PNG at *scale* for hi-res schedule reads."""
        from bobbytailor.pipeline.pdf_analyzer import _effective_render_scale  # avoid duplicating API limit logic

        doc = fitz.open(pdf_path)
        try:
            page = doc[page_index]
            scale = _effective_render_scale(page, scale)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            pix.save(path)
            return path
        finally:
            doc.close()
