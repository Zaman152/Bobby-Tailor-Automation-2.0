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
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional

import fitz

from sheet_pass_matrix import (
    classify_sheet_type_from_text,
    plan_passes,
    pick_model_for_pass,
)
from accuracy_config import count_tiling_enabled, count_tiling_grid

# Module-level imports make these symbols patchable in tests:
#   unittest.mock.patch("takeoff_pipeline.analyze_drawing", ...)
from claude_analyzer import (  # noqa: F401 (re-exported for patching)
    _SCHEDULE_LEGEND_USER_HINT,
    _merge_schedule_lists,
    analyze_drawing,
    apply_accuracy_rules,
    merge_passes,
)

# Deterministic measurement engine (21-03/06/07/10) — module-level names so
# tests can patch e.g. `takeoff_pipeline.extract_dimension_samples`.
from bobbytailor.deterministic.dimensions import extract_dimension_samples
from bobbytailor.deterministic.footprint_takeoff import footprint_from_page
from bobbytailor.deterministic.rooms import extract_rooms
from bobbytailor.deterministic.scale_extraction import (
    dominant_scale,
    extract_scales_from_text,
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
from bobbytailor.vision.fusion import build_registry, fuse_sheet, merge_with_provenance
from bobbytailor.vision.schemas import (
    raster_extraction_schema,
    semantic_labeling_schema,
    symbol_gallery_schema,
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

# Viewport kinds masked out of measurement (matches scale_solver._MASK_KINDS).
_MASK_VIEWPORT_KINDS = ("title_block", "legend", "schedule")


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

    Enable optional re-query to Claude for flagged items by setting the
    ``ENABLE_VERIFY_RETRY`` environment variable to ``"1"``.  The retry
    is a best-effort logging aid only; the original extraction is preserved
    regardless.

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
            if os.environ.get("ENABLE_VERIFY_RETRY") == "1":
                logger.info(
                    "QuantityVerifier: ENABLE_VERIFY_RETRY=1 set — "
                    "%d item(s) flagged on %r (log only, no re-query in this build)",
                    len(flags), sheet_name,
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
            # Use the module-level name so it can be patched by tests
            import takeoff_pipeline as _self_module
            self._analyzer = _self_module.analyze_drawing
        self._settings = settings if settings is not None else RunSettings.from_env()
        # Optional object manifest, set by run_project; drives targeted counting.
        self._manifest = None
        # Optional reliable drawing scale (feet per inch) for geometry measurement.
        self._scale_fpi = None
        # One BudgetGuard per run (set by run_project); run_sheet falls back
        # to a per-sheet guard when called standalone (scraper path — 21-15
        # parity will thread the run-level guard there too).
        self._run_budget: Optional[BudgetGuard] = None
        # extract_schedules() scans the whole document — cache per pdf_path.
        self._schedules_cache: dict = {}

    @property
    def settings(self) -> RunSettings:
        """The shared RunSettings this pipeline was constructed with."""
        return self._settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

        Returns:
            Merged extraction dict, or a skip sentinel for title_sheet:
            {"_skipped": True, "sheet_type": "title_sheet", "sheet_name": ...}
        """
        # Step 1 — classify if not provided
        resolved_type = sheet_type or classify_sheet_type_from_text(
            title_block_text, full_page_text
        )

        # Step 2 — determine passes
        passes = plan_passes(resolved_type, title_block_text=title_block_text)

        if not passes:
            # title_sheet — skip entirely; zero API calls
            logger.info("run_sheet: skipping title_sheet %r (zero API cost)", sheet_name)
            return {
                "_skipped": True,
                "sheet_type": resolved_type,
                "sheet_name": sheet_name,
                "sheet_source": image_path,
            }

        guard = budget or self._run_budget or BudgetGuard(self._settings.budget_usd)

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
                from page_text_enrichment import enrich_components_from_page_text
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

        return merged

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
    ) -> Optional[dict]:
        """Dispatch a deterministic-eligible sheet to the vector or raster flow.

        Returns None to fall back to the legacy vision flow (routing failure
        or a vector schedule sheet with no deterministic tables). Exceptions
        inside a branch degrade per-sheet to the error-dict convention —
        never crash the run (threat model: untrusted PDF flow).
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
        scale = resolve_scale_v2(
            page,
            viewports_with_scales,
            override_feet_per_inch=getattr(self, "_scale_fpi", None),
        )
        fpp = float(scale.feet_per_point or 0.0)

        main_bbox = None
        for vp, _vs in viewports_with_scales:
            if vp.region_id == main_id:
                main_bbox = vp.bbox_pt
                break

        walls: list = []
        wall_lf: dict = {}
        rooms: list = []
        symbols: list = []
        if resolved_type in _PLAN_SHEET_TYPES and fpp > 0:
            walls = extract_walls(page, fpp, exclude_rects=mask_rects)
            wall_lf = wall_lf_by_class(walls, fpp)
            rooms = extract_rooms(page, walls, main_bbox, fpp)
            symbols = cluster_symbols(
                page, fpp, exclude_rects=mask_rects, doc=doc, page_index=page_index
            )

        footprint = None
        if resolved_type in _PLAN_SHEET_TYPES:
            try:
                footprint = footprint_from_page(
                    page, page_index=page_index, sheet_name=sheet_name
                )
            except Exception as exc:  # noqa: BLE001 — footprint is additive
                logger.debug("footprint_from_page failed on %r: %s", sheet_name, exc)

        return {
            "symbol_groups": symbols,
            "walls": walls,
            "wall_lf_by_class": wall_lf,
            "rooms": rooms,
            "viewports": viewports,
            "schedules": schedules,
            "footprint": footprint,
            "fpp": fpp,
            "sheet_name": sheet_name,
            "_viewports_with_scales": viewports_with_scales,
            "_main_plan_region": main_id,
            "_scale_result": scale,
        }

    def _structured_vision_call(
        self,
        image_path: str,
        sheet_name: str,
        pass_type: str,
        sheet_type: str,
        schema: dict,
        images: list,
        guard: Optional[BudgetGuard],
    ) -> dict:
        """One structured-output vision call, charged to the budget guard.

        Raises BudgetExceeded when the guard is already exhausted or the
        charge for the completed call is refused (the refused result is
        discarded — the ledger only ever holds paid-and-accepted work).
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
                res = self._structured_vision_call(
                    image_path, sheet_name, "semantic", resolved_type,
                    schema, images[:20], guard,
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
            legend_labels = _legend_labels_from_schedules(schedules)
            if legend_labels:
                try:
                    legend_rect = _legend_crop_rect(viewports, schedules)
                    gallery = _build_crop_gallery(
                        page, symbols, legend_crop_rect=legend_rect
                    )
                    if gallery:
                        symbol_ids = [
                            _sched_field(g, "candidate_id", "") for g in symbols
                        ]
                        symbol_ids = [s for s in symbol_ids if s]
                        schema = symbol_gallery_schema(symbol_ids, legend_labels)
                        res = self._structured_vision_call(
                            image_path, sheet_name, "symbol_gallery",
                            resolved_type, schema, gallery, guard,
                        )
                        passes_run.append("symbol_gallery")
                        if res and not res.get("error"):
                            vision_results.append(res)
                            vision_labels["matches"] = res.get("matches")
                except BudgetExceeded:
                    budget_exhausted = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "run_sheet: %r — symbol gallery pass failed: %s",
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
        fused = fuse_sheet(bundle, vision_labels, registry)
        merged = merge_with_provenance([fused])

        # QuantityVerifier on the fused result (flags feed 21-14 verify-retry).
        verifier_flags = QuantityVerifier().verify(merged, sheet_name=sheet_name)
        if verifier_flags:
            merged["_verifier_flags"] = verifier_flags

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

        merged["_source_sheet"] = image_path
        merged["_sheet_type"] = resolved_type
        merged["_sheet_name"] = sheet_name
        merged["_passes_run"] = passes_run
        merged["_budget"] = _budget_state(guard)
        return merged

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
            from geometry_takeoff import measure_geometry
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

    def run_project(
        self,
        pages: list[dict],
        progress_callback=None,
        project_legend_schedules: Optional[list] = None,
        manifest=None,
        scale_feet_per_inch: Optional[float] = None,
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
        from calculator import apply_estimation_tables, _detect_project_type  # noqa: PLC0415

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

            extracted = self.run_sheet(
                image_path=image_path,
                sheet_name=sheet_name,
                sheet_type=sheet_type,
                title_block_text=title_block_text,
                full_page_text=page.get("full_page_text", ""),
                pdf_path=page.get("pdf_path"),
                page_index=page.get("page_index"),
                budget=self._run_budget,
            )

            # Tag original page number for downstream reporters.
            extracted["_page_num"] = page.get("page_num", i)

            if extracted.get("_skipped"):
                logger.info(
                    "run_project: skipping %r (sheet_type=%s)",
                    sheet_name, extracted.get("sheet_type"),
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

        # Manifest-driven wall height for derived wall-area estimates (replaces the
        # blanket 9ft assumption when the manifest supplies a wall height_ft).
        wall_height_ft = _manifest_wall_height(getattr(self, "_manifest", None))

        all_estimates: list[dict] = []
        for extracted in all_extracted:
            if "error" not in extracted:
                verifier.verify(
                    extracted,
                    sheet_name=extracted.get("_sheet_name", extracted.get("_source_sheet", "")),
                )
                all_estimates.extend(
                    apply_estimation_tables(
                        extracted, project_type=project_type,
                        wall_height_ft=wall_height_ft,
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
        from pdf_analyzer import _effective_render_scale

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
        from pdf_analyzer import _effective_render_scale

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
        from pdf_analyzer import _effective_render_scale  # avoid duplicating API limit logic

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
