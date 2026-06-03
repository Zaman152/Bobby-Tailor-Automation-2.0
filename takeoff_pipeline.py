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
  - 20-00 (this file): pipeline skeleton + merge stub + routing wired in.
  - 20-03: analyze_drawing gains pass_type + model_override kwargs → remove stub.
  - 20-06: pdf_analyzer.py and scraper.py swapped to call TakeoffPipeline.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from sheet_pass_matrix import (
    classify_sheet_type_from_text,
    plan_passes,
    pick_model_for_pass,
)

# Module-level import makes analyze_drawing patchable in tests:
#   unittest.mock.patch("takeoff_pipeline.analyze_drawing", ...)
from claude_analyzer import analyze_drawing  # noqa: F401 (re-exported for patching)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# merge_passes — stub implementation (canonical version moved to claude_analyzer in 20-03)
# ---------------------------------------------------------------------------

def merge_passes(
    count_result: dict,
    measure_result: dict,
    schedule_result: Optional[dict],
) -> dict:
    """Merge three pass results into a single extraction dict.

    Strategy:
      - measure_result is the base (SF/LF quantities, pipe_runs, rooms).
      - count_result components are merged in, preferring high-confidence EA counts
        over measure-pass nulls.
      - schedule_result replaces the schedules[] list when present.

    This stub is superseded by claude_analyzer.merge_passes in plan 20-03.
    Both implementations must produce identical output for the same inputs.

    Args:
        count_result:    Extraction dict from the "count" pass.
        measure_result:  Extraction dict from the "measure" pass.
        schedule_result: Extraction dict from the "schedule" pass, or None.

    Returns:
        Merged extraction dict with deduplicated components.
    """
    merged = dict(measure_result)

    # Index measure-pass components by normalised name for deduplication
    seen: dict[str, dict] = {
        c["name"].lower(): c
        for c in merged.get("components", [])
    }

    for c in count_result.get("components", []):
        key = c["name"].lower()
        if key not in seen:
            # New component from count pass — add to merged list
            merged.setdefault("components", []).append(c)
            seen[key] = c
        else:
            existing = seen[key]
            # Upgrade quantity if count-pass is high-confidence and measure-pass is null
            if c.get("confidence") == "high" and existing.get("quantity") is None:
                existing["quantity"] = c["quantity"]

    if schedule_result:
        merged["schedules"] = schedule_result.get("schedules", [])

    return merged


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
        passes = plan_passes(resolved_type)

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

    def _run_pass(
        self,
        image_path: str,
        sheet_name: str,
        pass_type: str,
        model_override: Optional[str],
    ) -> dict:
        """Execute a single extraction pass via analyze_drawing.

        NOTE (20-03): analyze_drawing will gain pass_type + model_override
        kwargs in plan 20-03.  Until then, the call uses the current
        signature (screenshot_path, sheet_name) and pass differentiation
        is implemented via the model routing table only.

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

        # TODO(20-03): add pass_type=pass_type, model_override=model_override
        # once claude_analyzer.analyze_drawing accepts those kwargs.
        result = self._analyzer(image_path, sheet_name)

        if not isinstance(result, dict):
            logger.warning(
                "_run_pass: analyze_drawing returned non-dict for %r pass=%r",
                sheet_name, pass_type,
            )
            return {}

        return result
