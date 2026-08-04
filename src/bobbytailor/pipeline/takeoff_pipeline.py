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

import logging
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
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
from bobbytailor.deterministic.symbols import cluster_symbols
from bobbytailor.deterministic.tables import extract_schedules
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

# Verify-retry arbitration (21-14): module-level import so tests can patch
# `takeoff_pipeline.retry_flagged_items` (patchability convention, 20-00).
from bobbytailor.vision.verify_retry import retry_flagged_items
from bobbytailor.vision.schemas import (
    raster_extraction_schema,
    semantic_labeling_schema,
    symbol_gallery_schema,
)
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


def _render_overlay(page, candidates, kind_colors=None):
    """Lazy wrapper for overlay.render_overlay (circular-import avoidance)."""
    from bobbytailor.vision.overlay import render_overlay

    return render_overlay(page, candidates, kind_colors=kind_colors)


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
    """

    deterministic_enabled = True
    ensemble_n = 3
    learning_enabled = True
    budget_usd = 10.0
    verify_retry_enabled = True
    raster_force = False

    @classmethod
    def from_env(cls) -> "RunSettings":
        n, budget = 3, 10.0
        try:
            settings = ensemble_settings()
            n = int(settings["n"])
            budget = float(settings["budget_usd"])
        except Exception:  # noqa: BLE001 — config stubbed (tests) → defaults
            logger.debug("RunSettings.from_env: config unavailable — defaults used")
        return cls(
            deterministic_enabled=_env_flag("DETERMINISTIC_ENABLED", True),
            ensemble_n=n,
            learning_enabled=_env_flag("LEARNING_ENABLED", True),
            budget_usd=budget,
            verify_retry_enabled=_env_flag("VERIFY_RETRY_ENABLED", True),
            raster_force=_env_flag("RASTER_FORCE", False),
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
# ground truth); other types keep the legacy vision passes.
_DETERMINISTIC_SHEET_TYPES = _PLAN_SHEET_TYPES + ("schedule",)

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
    """Serializable BudgetGuard state for reports: {cap, spent, exhausted}."""
    if guard is None:
        return {"cap_usd": None, "spent_usd": 0.0, "exhausted": False}
    return {
        "cap_usd": round(float(guard.max_usd), 4),
        "spent_usd": round(float(guard.spent_usd), 6),
        "exhausted": bool(guard.exhausted),
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


def _resolve_project_wall_height(pages_text, footprint=None, learned=None) -> "tuple[float, str]":
    """Autonomously resolve the project wall/clear height, with its source.

    Replaces the manifest ``height_ft`` role under the plans-only mandate.
    Precedence (per the binding spec): a learned ``wall_height_ft`` assumption
    wins when present; otherwise the plan text layer is read for a wall/clear
    height callout near a wall keyword (``T.O. WALL``, ``TOP OF WALL``,
    ``CLEAR``/``CLR``, ``WALL HEIGHT``, or a feet-inches token near
    ``TILT``/``CMU``/``PANEL``); a robust (max plausible, 8'-60') value is
    taken. When nothing parses, a flagged industrial default (30.0 ft) applies.

    Args:
        pages_text: Concatenated plan text layer (elevations / sections /
                    keynotes / general notes across all pages).
        footprint:  Optional Footprint (unused for the value today; reserved so
                    callers can pass the measured extent for future bounds).
        learned:    Optional LearnedContext; a stored ``wall_height_ft`` wins.

    Returns:
        ``(height_ft, source)`` where source is ``"learned"`` | ``"plan"`` |
        ``"default"`` — the assumption is never silent.
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

    return _WALL_HEIGHT_DEFAULT_FT, "default"


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

        footprint = None
        if resolved_type in _PLAN_SHEET_TYPES:
            try:
                footprint = footprint_from_page(
                    page, page_index=page_index, sheet_name=sheet_name
                )
            except Exception as exc:  # noqa: BLE001 — footprint is additive
                logger.debug("footprint_from_page failed on %r: %s", sheet_name, exc)

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

        return {
            "symbol_groups": symbols,
            "walls": walls,
            "wall_lf_by_class": wall_lf,
            "rooms": rooms,
            "room_fills": room_fills,
            "material_tags": material_tags,
            "viewports": viewports,
            "schedules": schedules,
            "footprint": footprint,
            "fpp": fpp,
            "sheet_name": sheet_name,
            # Additive coverage keys. `excluded_viewports` is the DELIBERATE
            # off-scale exclusion (correct, and previously log-only);
            # `coverage_drops` is everything this sheet failed to measure, each
            # with a named reason. No existing key is renamed or removed.
            "excluded_viewports": excluded_viewports,
            "coverage_drops": coverage_drops,
            "_viewports_with_scales": viewports_with_scales,
            "_main_plan_region": main_id,
            "_scale_result": scale,
        }

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
            ``(fills, drops)`` — the measurements, and one
            :class:`DrawingCoverage` per drawing that was NOT measured, each
            naming the reason. The four bare ``continue``s this method used to
            take are exactly INV-08 §2 row S6: a named drawing (e.g.
            ``KING A - FC PLAN``) vanished with no row, no flag and no count in
            any artifact, so its item read as a zero rather than as a blank.
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

        region_ids = [
            vp.region_id for vp in viewports if vp.kind not in _MASK_VIEWPORT_KINDS
        ]
        wall_ids = sorted(
            cid for cid, meta in registry.items() if meta.get("kind") == "wall_class"
        )
        if region_ids and wall_ids:
            try:
                candidates = {}
                for vp in viewports:
                    if vp.region_id in region_ids:
                        candidates[vp.region_id] = vp.bbox_pt
                for cid in wall_ids:
                    candidates[cid] = registry[cid]["bbox_pt"]
                overlay = _render_overlay(page, candidates)
                images = overlay if isinstance(overlay, list) else [overlay]
                schema = semantic_labeling_schema(region_ids, wall_ids)
                res = self._voted_structured_vision_call(
                    image_path, sheet_name, "semantic", resolved_type,
                    schema, images[:20], guard,
                    vote_key="wall_class_labels",
                )
                passes_run.append("semantic")
                if res and not res.get("error"):
                    vision_results.append(res)
                    vision_labels["main_plan_region"] = res.get("main_plan_region")
                    vision_labels["wall_class_labels"] = res.get("wall_class_labels")
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
                    sym_candidates = {}
                    for group in symbols:
                        cid = _sched_field(group, "candidate_id", "")
                        if not cid:
                            continue
                        rep = _sched_field(group, "representative_bbox_pt", None)
                        if rep is None:
                            rep = _sched_field(group, "bbox_pt", None)
                        if rep:
                            sym_candidates[cid] = rep
                    if sym_candidates:
                        overlay = _render_overlay(page, sym_candidates)
                        images = overlay if isinstance(overlay, list) else [overlay]
                        symbol_ids = list(sym_candidates.keys())
                        schema = symbol_gallery_schema(symbol_ids, legend_labels)
                        count_hint = _build_symbol_count_hint(symbols)
                        res = self._voted_structured_vision_call(
                            image_path, sheet_name, "symbol_gallery",
                            resolved_type, schema, images[:20], guard,
                            user_hint=count_hint,
                            vote_key="matches",
                        )
                        passes_run.append("symbol_gallery")
                        if res and not res.get("error"):
                            vision_results.append(res)
                            vision_labels["matches"] = res.get("matches")
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
        fused = fuse_sheet(
            bundle,
            vision_labels,
            registry,
            vocabulary=getattr(self, "_project_vocabulary", None),
            wall_height_ft=getattr(self, "_project_wall_height", None),
            wall_height_source=getattr(self, "_project_wall_height_source", None),
            material_tag_ledger=getattr(self, "_material_tag_ledger", None),
            room_mix=dict(room_mix_resolution.counts),
            room_mix_meta={
                name: {
                    "source": room_mix_resolution.sources.get(name, ""),
                    "note": room_mix_resolution.name_flags.get(name, ""),
                }
                for name in room_mix_resolution.counts
            },
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

    def _build_project_vocabulary(
        self,
        image_path: str,
        plan_text: str,
        guard: Optional[BudgetGuard],
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
        """
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
        """
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
            return samples[0] if samples else []
        try:
            return majority_keep_conventions(samples)
        except Exception as exc:  # noqa: BLE001 — additive, never break a run
            logger.warning("_build_naming_conventions: vote failed: %s", exc)
            return samples[0] if samples else []

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
        # flagged 30 ft industrial default. Whatever the source, it is flagged
        # on derived wall-area items — never a silent substitution.
        wall_height_ft, wall_height_source = _resolve_project_wall_height(
            plan_text, None, self._learned_context,
        )
        self._project_wall_height = wall_height_ft
        self._project_wall_height_source = wall_height_source
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
                    vocab_page["image_path"], naming_text, self._run_budget
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
        """Execute a single extraction pass via analyze_drawing.

        Args:
            image_path:     Path to the sheet image.
            sheet_name:     Sheet identifier for logging and model selection.
            pass_type:      Name of the pass ("count", "measure", "schedule").
            model_override: Model slug to use, or None for default.
            budget:         Per-run BudgetGuard; the completed call's
                            ``_cost_usd`` is charged. A refused charge raises
                            BudgetExceeded and the result is discarded (the
                            ledger only holds paid-and-accepted work).

        Raises:
            BudgetExceeded: When the guard is exhausted or refuses the charge.
        """
        if budget is not None and budget.exhausted:
            raise BudgetExceeded(budget.spent_usd, budget.max_usd)
        if model_override:
            logger.info(
                "  pass=%r model=%r sheet=%r", pass_type, model_override, sheet_name
            )
        else:
            logger.info("  pass=%r sheet=%r (default model)", pass_type, sheet_name)

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
