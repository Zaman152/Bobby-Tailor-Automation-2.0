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
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from sheet_pass_matrix import (
    classify_sheet_type_from_text,
    plan_passes,
    pick_model_for_pass,
)

# Module-level imports make these symbols patchable in tests:
#   unittest.mock.patch("takeoff_pipeline.analyze_drawing", ...)
from claude_analyzer import analyze_drawing  # noqa: F401 (re-exported for patching)
from claude_analyzer import merge_passes  # noqa: F401 (canonical; stub below removed)

logger = logging.getLogger(__name__)


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

    def __init__(self, analyzer: Optional[Callable] = None) -> None:
        """
        Args:
            analyzer: Callable with the same signature as analyze_drawing.
                      Inject a mock in tests to avoid real API calls.
                      Defaults to the module-level analyze_drawing import.
        """
        if analyzer is not None:
            self._analyzer = analyzer
        else:
            # Use the module-level name so it can be patched by tests
            import takeoff_pipeline as _self_module
            self._analyzer = _self_module.analyze_drawing

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
    ) -> dict:
        """Run all applicable extraction passes for a single sheet image.

        Args:
            image_path:       Absolute path to the sheet screenshot/image.
            sheet_name:       Sheet identifier (e.g. "A2.1", "C1.0").
            sheet_type:       Pre-classified sheet type; if None, classified
                              from title_block_text / full_page_text.
            title_block_text: Text from the title block (bottom-right region).
            full_page_text:   Full page OCR text used as fallback classifier.

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

        logger.info(
            "run_sheet: %r sheet_type=%r passes=%s", sheet_name, resolved_type, passes
        )

        # Step 3 — execute each pass
        count_result: dict    = {}
        measure_result: dict  = {}
        schedule_result: Optional[dict] = None

        for pass_type in passes:
            model_override = pick_model_for_pass(resolved_type, pass_type, sheet_name)
            result = self._run_pass(image_path, sheet_name, pass_type, model_override)

            if pass_type == "count":
                count_result = result
            elif pass_type == "measure":
                measure_result = result
            elif pass_type == "schedule":
                schedule_result = result
            else:
                logger.warning("run_sheet: unknown pass_type %r — result discarded", pass_type)

        # Step 4 — merge
        merged = merge_passes(count_result, measure_result, schedule_result)

        # Attach pipeline metadata
        merged["_source_sheet"] = image_path
        merged["_sheet_type"]   = resolved_type
        merged["_sheet_name"]   = sheet_name
        merged["_passes_run"]   = passes

        return merged

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def run_project(
        self,
        pages: list[dict],
        progress_callback=None,
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
            )

            # Tag original page number for downstream reporters.
            extracted["_page_num"] = page.get("page_num", i)

            if extracted.get("_skipped"):
                logger.info(
                    "run_project: skipping %r (sheet_type=%s)",
                    sheet_name, extracted.get("sheet_type"),
                )
                continue

            all_extracted.append(extracted)

        # Project-type detection runs ONCE across all non-skipped sheets so
        # apply_estimation_tables uses a consistent type for the whole set.
        project_type = _detect_project_type(all_extracted)
        logger.info(
            "run_project: project_type=%r across %d sheets",
            project_type, len(all_extracted),
        )

        all_estimates: list[dict] = []
        for extracted in all_extracted:
            if "error" not in extracted:
                verifier.verify(
                    extracted,
                    sheet_name=extracted.get("_sheet_name", extracted.get("_source_sheet", "")),
                )
                all_estimates.extend(
                    apply_estimation_tables(extracted, project_type=project_type)
                )

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
    ) -> dict:
        """Execute a single extraction pass via analyze_drawing.

        Args:
            image_path:     Path to the sheet image.
            sheet_name:     Sheet identifier for logging and model selection.
            pass_type:      Name of the pass ("count", "measure", "schedule").
            model_override: Model slug to use, or None for default.

        Returns:
            Raw extraction dict from analyze_drawing.
        """
        if model_override:
            logger.info(
                "  pass=%r model=%r sheet=%r", pass_type, model_override, sheet_name
            )
        else:
            logger.info("  pass=%r sheet=%r (default model)", pass_type, sheet_name)

        result = self._analyzer(
            image_path,
            sheet_name,
            pass_type=pass_type,
            model_override=model_override,
        )

        if not isinstance(result, dict):
            logger.warning(
                "_run_pass: analyze_drawing returned non-dict for %r pass=%r",
                sheet_name, pass_type,
            )
            return {}

        return result
