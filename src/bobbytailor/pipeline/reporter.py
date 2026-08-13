"""
Generate takeoff report from Claude's extracted drawing data + calculated estimates.

Per requirements doc (Section 5):
- Complete set of quantity estimates derived from scraped drawings
- Summary report mapping each measurement to its source drawing section
- Clear identification of which part of the automation measured each quantity
- Consistent output format for easy review and handoff
"""
import json
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from bobbytailor.config import OUTPUT_DIR
from bobbytailor.pipeline.coverage import CoverageLedger, ItemCoverage
# The three routes a published quantity can come by (28-06). IMPORTED from the
# layer that assigns them, never restated: this module only READS the value the
# aggregator wrote, and a second spelling of `sheet_reading` here is how the
# REPRODUCIBILITY section quietly stops matching any row. `aggregate_takeoff`
# itself is still imported lazily at its call site, unchanged.
from bobbytailor.pipeline.aggregator import (
    QUANTITY_ROUTE_MEASURED,
    QUANTITY_ROUTE_PRINTED_SCHEDULE,
    QUANTITY_ROUTE_SHEET_READING,
)
from bobbytailor.pipeline.provenance import provenance_of_row

logger = logging.getLogger(__name__)

#: The ``fuse_sheet`` result key carrying the unnamed-geometry ledger — one
#: record per candidate the run MEASURED but could not identify (24-04).
#:
#: Mirrored by VALUE from :data:`bobbytailor.vision.fusion.UNNAMED_GEOMETRY_KEY`
#: rather than imported, for the same reason 24-04 mirrors ``text_anchor``'s
#: anchor-kind string: ``pipeline.reporter`` takes no dependency on
#: ``bobbytailor.vision`` today, and a report renderer is the wrong place to
#: start one. The one-line indirection is checked by a test that fails if the
#: two strings ever diverge, so the mirror cannot rot in silence.
UNNAMED_GEOMETRY_KEY = "unnamed_geometry"


def generate_report(project_name: str,
                    all_extracted: list,
                    all_estimates: Optional[list] = None,
                    folder_id: Optional[int] = None,
                    cross_references: Optional[list] = None,
                    linked_sheets: Optional[list] = None,
                    manifest=None,
                    screenshots_dir: Optional[str] = None,
                    learned=None,
                    library=None,
                    *,
                    coverage: Optional[CoverageLedger] = None,
                    source_pdf: Optional[str] = None,
                    run_settings: Optional[dict] = None) -> dict:
    """
    Build the final takeoff report.

    Args:
        project_name: Display name of the StackCT project
        all_extracted: list of Claude's raw extractions, one per drawing page
        all_estimates: list of items returned by calculator.apply_estimation_tables()
                       — already has calculated quantities, waste factors, source tracing
        folder_id: Optional StackCT folder/plan-set ID for this run
        cross_references: Optional list of cross-reference links between sheets
        linked_sheets: Optional list of linked-sheet metadata dicts from Phase 18;
                       each has at minimum {page_id, sheet_name, ref_from} and optional
                       suggested_only=True when AUTO_INCLUDE_LINKED_SHEETS is off
        learned: Optional bobbytailor.learning.retrieval.LearnedContext — the
                 run's retrieved learning bundle (21-16, V3-LEARN-02/03).
                 Threads learned vocabulary into aggregation naming.
        coverage: KEYWORD-ONLY, default None. The run's CoverageLedger
                  (INV-08 / 23-01): one row per PAGE OF THE SOURCE PDF, plus the
                  per-drawing drop records the pipeline wrote. Supplying it adds
                  the five additive coverage fields, writes ``coverage.json``
                  into the run folder and renders the COVERAGE section of
                  ``summary.txt``. Passing None renders EXACTLY as a pre-23
                  report: no new key appears anywhere, so a pre-23 caller (the
                  scraper path) is untouched.
        source_pdf: KEYWORD-ONLY, default None. Path of the PDF this report was
                    built from. generate_report has no record of its own input
                    today, which is itself a provenance gap — it is what makes
                    the ledger-completeness assertion (ledger length == source
                    page count == the PDF's own page count) checkable from the
                    artifact alone. Omitted from the report when not supplied.
        run_settings: KEYWORD-ONLY, default None. ``RunSettings.to_dict()`` —
                      the effective ensemble N, budget cap and feature toggles
                      the run actually used (21-13; both entry points already
                      construct one). Neither saved paid run records the N that
                      was in effect, which made 24-RESEARCH Open Question 1
                      permanently unanswerable for those runs: the environment
                      is not an artifact, so a setting that lives only there is
                      a setting nobody can audit afterwards. Omitted from the
                      report when not supplied, so a pre-24 caller is untouched
                      — the same contract ``coverage`` documents above.

    A blank is NOT a zero. Everything the coverage argument adds exists so the
    report can state what the run did NOT measure; the report has always been a
    complete account of what WAS found and a total silence about the rest
    (INV-08 §2 closing note).
    """
    all_estimates = all_estimates or []

    # Phase 18: linked sheet metadata — split into auto-added vs. suggested-only
    linked_added = [m for m in (linked_sheets or []) if not m.get("suggested_only")]
    linked_suggested = [m for m in (linked_sheets or []) if m.get("suggested_only")]

    output_root = Path(OUTPUT_DIR)
    output_root.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = project_name.replace(" ", "_").replace("/", "-")

    # Each run gets its own folder so files are not scattered in the root output dir
    run_dir = output_root / f"{safe}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Flatten raw extractions into line items (one row per measurement/component/room/material)
    raw_line_items = _flatten_raw_extractions(all_extracted)

    # Calculated takeoff = estimator output with full traceability
    calculated_items = _normalize_calculated(all_estimates)

    specification_tables = _collect_specification_tables(all_extracted)
    from bobbytailor.pipeline.aggregator import aggregate_takeoff
    takeoff_summary = aggregate_takeoff(
        calculated_items, manifest=manifest, learned=learned, library=library,
    )

    # Aggregate API usage across all sheets
    sheet_cost = sum(d.get("_cost_usd", 0) for d in all_extracted)
    total_tokens_in = sum(d.get("_tokens_in", 0) for d in all_extracted)
    total_tokens_out = sum(d.get("_tokens_out", 0) for d in all_extracted)

    model_counts: dict[str, int] = {}
    for d in all_extracted:
        m = d.get("_model_used", "")
        if m:
            model_counts[m] = model_counts.get(m, 0) + 1

    # Run-level budget block (21-13, V3-PROD-02): every sheet carries the
    # shared BudgetGuard state — surface the one with the highest spend
    # (the final accounting). None when no sheet recorded a budget
    # (pre-21 runs render unchanged).
    budget_block = None
    for d in all_extracted:
        b = d.get("_budget")
        if isinstance(b, dict) and b.get("cap_usd") is not None:
            if budget_block is None or (b.get("spent_usd") or 0) > (
                budget_block.get("spent_usd") or 0
            ):
                budget_block = b

    # ── THE run's cost is the guard's ledger, not the sum of sheet stamps ────
    #
    # Summing per-sheet ``_cost_usd`` under-reported Crow's paid run by 3.4x:
    # $0.1766 published against $0.5988 actually charged to the BudgetGuard.
    # Two independent leaks, both structural:
    #
    #   1. Project-level passes (the naming-convention and object-vocabulary
    #      reads run ONCE for the whole set, before the per-sheet loop) charge
    #      the guard and belong to no sheet, so no ``_cost_usd`` stamp can ever
    #      carry them.
    #   2. A sheet whose merged dict never inherits the analyzer's usage stamp
    #      reads $0 despite paid calls (Crow's sheets 2-4).
    #
    # The guard is the ONLY complete ledger — it is what actually refused the
    # last charge — so it is what ``total_cost_usd`` reports. The split is
    # published rather than fabricated: what a sheet stamped is attributed to
    # that sheet, and the whole remainder goes to ONE honest ``project_level``
    # bucket. Nothing is spread across sheets by ratio; an invented per-sheet
    # split would be a guess presented as accounting.
    #
    # Every cost estimate and every budget the user sets is downstream of this
    # number, so the invariant is pinned by test: reported total == guard spend.
    guard_spent = (
        budget_block.get("spent_usd") if isinstance(budget_block, dict) else None
    )
    if guard_spent is None:
        # No guard recorded (pre-21 runs, the scraper path without a budget):
        # the per-sheet sum is the only ledger there is — unchanged behaviour.
        total_cost = float(sheet_cost)
    else:
        total_cost = float(guard_spent)
    # Signed on purpose. A negative remainder would mean sheets stamped more
    # than the guard accepted (a refused charge stamped anyway) — a real
    # accounting discrepancy that must surface, not be clamped to zero.
    project_level_cost = round(total_cost - float(sheet_cost), 6)

    # Fusion audit trail (21-12/13): rejected vision quantity claims and
    # grounding violations, aggregated per sheet — never silently dropped.
    fusion_rejected: list = []
    for d in all_extracted:
        sheet = d.get("_sheet_name") or d.get("_source_sheet") or "unknown"
        for rej in d.get("fusion_rejected") or []:
            if isinstance(rej, dict):
                entry = dict(rej)
                entry["sheet"] = sheet
                fusion_rejected.append(entry)

    # ── The unnamed-geometry ledger (24-06, from 24-04's fuse_sheet key) ─────
    #
    # Same loop shape as the rejection list above, and deliberately NOT the same
    # list. An entry in the rejection list is a vision quantity claim that lost
    # to a measurement; a `coverage_ledger` row is one page of the source PDF.
    # An unnamed-geometry record is a THIRD thing — geometry the run measured
    # and could not name — and folding it into either would hand it to logic
    # written for a different fact (24-04 key decision).
    #
    # The sheet name is attached per record for the same reason it is attached
    # above: the record is written by `fuse_sheet`, which knows the candidate but
    # not which sheet it will be reported under.
    unnamed_geometry: list = []
    for d in all_extracted:
        sheet = d.get("_sheet_name") or d.get("_source_sheet") or "unknown"
        for rec in d.get(UNNAMED_GEOMETRY_KEY) or []:
            if isinstance(rec, dict):
                entry = dict(rec)
                entry["sheet"] = sheet
                unnamed_geometry.append(entry)

    report = {
        "project_name": project_name,
        "folder_id": folder_id,
        "generated_at": datetime.now().isoformat(),
        "sheets_processed": len(all_extracted),
        "total_line_items": len(raw_line_items),
        "total_calculated_items": len(calculated_items),
        "api_usage": {
            # Rounded to 6dp, matching the guard's own ledger precision — 4dp
            # silently shaved sub-tenth-of-a-cent off the equality.
            "total_cost_usd": round(total_cost, 6),
            # The split, published rather than fabricated (see above).
            "sheet_attributed_cost_usd": round(float(sheet_cost), 6),
            "project_level_cost_usd": project_level_cost,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "cost_per_sheet": round(total_cost / max(len(all_extracted), 1), 6),
            "models_used": model_counts,
        },
        # 21-13 additive fields (never rename existing keys — 03-02/03-03).
        "budget": budget_block,
        "fusion_rejected": fusion_rejected,
        "calculated_takeoff": calculated_items,         # Section 5 deliverable
        "takeoff_summary": takeoff_summary,
        # Pristine vision aggregate — preserved so the verification worksheet can
        # idempotently rebuild (base + measurements + manual overrides).
        "takeoff_summary_base": [dict(r) for r in takeoff_summary],
        "specification_tables": specification_tables,
        "cross_references": cross_references or [],
        "linked_sheets_added": linked_added,
        "linked_sheets_suggested": linked_suggested,
        "linked_sheets_added_count": len(linked_added),
        "linked_sheets_suggested_count": len(linked_suggested),
        "screenshots_dir": screenshots_dir or "",
        "raw_line_items": raw_line_items,               # Source-of-truth list
        "by_sheet": _group_by_sheet(raw_line_items + calculated_items),
        "by_category": _group_by_category(raw_line_items),
        "by_table": _group_by_table(calculated_items),  # which estimation table was used
        "sheet_log": [
            {
                "sheet": d.get("_source_sheet"),
                "page_id": d.get("_page_id"),
                # The per-sheet error dict sets `_sheet_type`, not `sheet_type`
                # (takeoff_pipeline._error_result), so an errored sheet used to
                # render as `type=None` with zero items — indistinguishable from
                # a sheet that genuinely held nothing (INV-08 §2 row S11).
                "type": d.get("sheet_type") or d.get("_sheet_type"),
                # None on every healthy sheet; the exception text on a degraded
                # one. A sheet that FAILED and a sheet that found nothing are
                # different facts and must not render alike.
                "error": d.get("error"),
                "title": d.get("sheet_title"),
                "scale": d.get("scale"),
                "scale_parsed": _parsed_scale(d.get("scale")),
                "geometry": d.get("_geometry"),
                "measurements": len(d.get("measurements", [])),
                "components": len(d.get("components", [])),
                "rooms": len(d.get("rooms", [])),
                "materials": len(d.get("materials", [])),
                "schedules": len(d.get("schedules", [])),
                "confidence": d.get("confidence"),
                "notes": d.get("notes"),
                "tokens_in": d.get("_tokens_in", 0),
                "tokens_out": d.get("_tokens_out", 0),
                "cost_usd": d.get("_cost_usd", 0),
                "model_used": d.get("_model_used", ""),
                # 21-13: deterministic-first surfacing (None on pre-21 runs).
                "measurement_mode": d.get("measurement_mode"),
                "scale_confidence": d.get("scale_confidence"),
                "main_plan_region": d.get("main_plan_region"),
            }
            for d in all_extracted
        ],
    }

    # ── Coverage ledger surfacing (23-17, INV-08 §3.3) ───────────────────────
    # Five ADDITIVE fields, and not one of them appears when the run carried no
    # ledger: a pre-23 report must still be a valid, unchanged report.
    report_ledger = _coverage_for_report(coverage, all_extracted, takeoff_summary)
    if report_ledger is not None:
        report["coverage"] = report_ledger.summary()
        # One row per PAGE OF THE SOURCE PDF — not per processed sheet. That is
        # the whole invariant: len(coverage_ledger) == pages_in_source.
        report["coverage_ledger"] = [s.to_dict() for s in report_ledger.sheets]
        report["item_coverage"] = [i.to_dict() for i in report_ledger.items]
        report["coverage_warnings"] = _coverage_warnings(
            report_ledger, all_extracted, budget_block,
        )
        report["pages_in_source"] = report_ledger.pages_in_source
    if source_pdf:
        report["source_pdf"] = str(source_pdf)

    # ── Unnamed geometry + effective run settings (24-06) ────────────────────
    # Two ADDITIVE keys, both absent when the run carried nothing to put in them.
    #
    # The empty ledger is emitted as an ABSENT key rather than as `[]`. An empty
    # list would be the better statement — "we identified everything" said out
    # loud beats silence — but T-23-70's mitigation is an exact top-level key-set
    # equality assertion for a pre-Phase-23 caller, and a key present with an
    # empty value is not key-set equality. The parity guarantee is load-bearing
    # for the two scraper entry points and outranks the nicer phrasing, so the
    # honest statement is made where it costs nothing: a run that DID carry
    # unnamed geometry always publishes it, and `summary.txt` says in words what
    # the list means. Consumers use `.get(..., [])`.
    if unnamed_geometry:
        report[UNNAMED_GEOMETRY_KEY] = unnamed_geometry
    if run_settings:
        # Copied, never aliased: the report is serialised after the caller may
        # still be holding (and mutating) its own settings dict.
        report["run_settings"] = dict(run_settings)

    # Scale calibration — per-sheet drawing scale + scale-independent raw geometry
    # so the Results "Scale & Verify" module can recompute measured quantities
    # exactly when a human corrects a scale (no vision re-run).
    scale_calibration = _build_scale_calibration(
        project_name, run_dir.name, all_extracted,
    )
    report["scale_calibration"] = scale_calibration
    report["sheet_assets"] = _build_sheet_assets(all_extracted)

    # All files for this run live inside the run's folder with clean names
    json_path = run_dir / "takeoff.json"
    csv_raw   = run_dir / "raw_items.csv"
    csv_calc  = run_dir / "calculations.csv"      # ← THE CALCULATIONS FILE
    csv_summary = run_dir / "takeoff_summary.csv"
    txt_path  = run_dir / "summary.txt"
    spec_json = run_dir / "spec_tables.json"
    calib_json = run_dir / "scale_calibration.json"

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    try:
        with open(calib_json, "w") as f:
            json.dump(scale_calibration, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write scale_calibration.json: {e}")

    # coverage.json — the record of what the run did NOT measure, as its own
    # artifact so it can be read (and diffed run to run) without parsing the
    # whole take-off. Written only when a ledger was supplied.
    coverage_json = run_dir / "coverage.json"
    coverage_written = False
    if report_ledger is not None:
        try:
            with open(coverage_json, "w") as f:
                json.dump({
                    "project_name": project_name,
                    "generated_at": report["generated_at"],
                    "source_pdf": str(source_pdf) if source_pdf else "",
                    "summary": report["coverage"],
                    "warnings": report["coverage_warnings"],
                    "sheets": report["coverage_ledger"],
                    "items": report["item_coverage"],
                }, f, indent=2)
            coverage_written = True
        except Exception as e:
            logger.error(f"Failed to write coverage.json: {e}")

    # Save each output file independently so one failure doesn't kill the others
    try:
        _write_raw_csv(raw_line_items, csv_raw)
    except Exception as e:
        logger.error(f"Failed to write raw CSV: {e}")

    try:
        _write_calculated_csv(calculated_items, csv_calc)
    except Exception as e:
        logger.error(f"Failed to write calculated CSV: {e}")

    try:
        _write_takeoff_summary_csv(takeoff_summary, csv_summary)
    except Exception as e:
        logger.error(f"Failed to write takeoff summary CSV: {e}")

    if specification_tables:
        try:
            with open(spec_json, "w") as f:
                json.dump(specification_tables, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write spec_tables.json: {e}")

    try:
        _write_summary(report, txt_path)
    except Exception as e:
        logger.error(f"Failed to write summary text: {e}")
        # Write a minimal fallback so the user gets something
        try:
            with open(txt_path, "w") as f:
                f.write(f"Report summary write failed: {e}\n\n"
                        f"Project: {project_name}\n"
                        f"Sheets processed: {report['sheets_processed']}\n"
                        f"Raw items: {report['total_line_items']}\n"
                        f"Calculated items: {report['total_calculated_items']}\n\n"
                        f"Full data is available in the JSON and CSV files.")
        except Exception:
            pass

    logger.info(f"Saved run to: {run_dir} "
                f"[Total cost: ${total_cost:.4f}, "
                f"{total_tokens_in + total_tokens_out:,} tokens]")
    report["_files"] = {
        "run_folder":     str(run_dir),
        "json":           str(json_path),
        "raw_csv":        str(csv_raw),
        "calculated_csv": str(csv_calc),   # NEW name: calculations.csv
        "takeoff_summary_csv": str(csv_summary),
        "summary_txt":    str(txt_path),
        "spec_tables_json": str(spec_json) if specification_tables else None,
        "scale_calibration_json": str(calib_json),
    }
    if coverage_written:
        # Registered only when it exists: a pre-23 report's files map keeps its
        # exact pre-change shape, and a consumer that finds the key can trust it.
        report["_files"]["coverage_json"] = str(coverage_json)
    report["_run_folder_name"] = run_dir.name
    return report


# ─── Coverage ledger → report (23-17, INV-08 §3.3) ───────────────────────────

def _item_coverage_records(all_extracted: list) -> List[ItemCoverage]:
    """Every ItemCoverage the pipeline recorded on a sheet, in sheet order.

    Fusion writes an explicit NOT MEASURED record when no drawing of the right
    discipline was measured for an item's basis (23-03). Those records are the
    only account of an item that produced no published row at all, which is
    precisely the defect — absence cannot be classified after the fact.
    """
    out: List[ItemCoverage] = []
    for d in all_extracted or []:
        if not isinstance(d, dict):
            continue
        for rec in d.get("_item_coverage") or []:
            if isinstance(rec, ItemCoverage):
                out.append(rec)
            elif isinstance(rec, dict) and rec.get("name"):
                out.append(ItemCoverage(**{
                    k: v for k, v in rec.items()
                    if k in ItemCoverage.__dataclass_fields__
                }))
    return out


def _norm_item_key(name: Any) -> str:
    return " ".join(str(name or "").split()).lower()


def _coverage_for_report(coverage: Optional[CoverageLedger],
                         all_extracted: list,
                         takeoff_summary: list) -> Optional[CoverageLedger]:
    """A REPORTING COPY of the run's ledger, with one item row per expected item.

    Returns None when the run carried no ledger, which is what keeps a pre-23
    report byte-identical.

    Why a copy: ``generate_report`` must never mutate the ledger the pipeline
    still holds — calling it twice with the same ledger would otherwise double
    every item row. ``sheets`` is shared by reference (those rows are the
    pipeline's record and are only ever read here); ``items`` is a new list.

    Item rows come from two places, in this order:

    1. **The published take-off rows.** They are the artifact a client actually
       reads, and 23-03 already made them complete — an expected item that was
       never measured has a row with ``quantity=None`` and provenance
       ``NOT MEASURED``.
    2. **Records the run made that never became a published row.** Deduplicated
       against (1) by name, so the report can never say NOT MEASURED two rows
       below the measurement of the same thing — 23-03 deviation 1 is the
       precedent: contradicting yourself is worse than the silence being fixed.
    """
    if coverage is None:
        return None

    led = CoverageLedger(
        pages_in_source=coverage.pages_in_source,
        sheets=coverage.sheets,
        items=[],
        # Carried, not recomputed: the sheets a set cites but does not contain
        # are read once, before any measurement. Dropping them here would lose
        # the run's only statement that its INPUT was incomplete.
        missing_sheets=list(getattr(coverage, "missing_sheets", ()) or ()),
    )

    seen = set()
    for row in takeoff_summary or []:
        if not isinstance(row, dict):
            continue
        name = row.get("item")
        key = _norm_item_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        quantity = row.get("quantity")
        led.add_item(ItemCoverage(
            name=str(name),
            unit=str(row.get("unit") or ""),
            # Read from the record. provenance_of_row is the ONE place that
            # decides this vocabulary, and it is only consulted here for a row
            # the aggregator has not already classified (a pre-23 row).
            status=str(row.get("provenance") or provenance_of_row(row)),
            quantity=quantity if isinstance(quantity, (int, float)) else None,
            basis=str(row.get("item_type") or ""),
            source_sheets=[str(s) for s in (row.get("source_sheets") or [])],
            reason="; ".join(str(x) for x in (row.get("review_reasons") or [])),
            expected_from=str(row.get("source") or "detected"),
        ))

    for rec in list(coverage.items) + _item_coverage_records(all_extracted):
        key = _norm_item_key(getattr(rec, "name", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        led.add_item(rec)

    return led


def _coverage_notes(all_extracted: list) -> List[str]:
    """Per-sheet coverage notes, deduplicated and named by their sheet.

    A note such as "N room fills measured (… SF) but no vocabulary item has an
    area basis — the measurements were discarded" is an escalation, not a log
    line: it says a real measurement was computed and then thrown away.
    """
    out: List[str] = []
    for d in all_extracted or []:
        if not isinstance(d, dict):
            continue
        sheet = str(d.get("_sheet_name") or d.get("_source_sheet") or "").strip()
        for note in d.get("_coverage_notes") or []:
            text = str(note).strip()
            if not text:
                continue
            line = f"[{sheet}] {text}" if sheet else text
            if line not in out:
                out.append(line)
    return out


def _budget_truncation_warning(budget) -> Optional[str]:
    """The run-level "this run stopped early" escalation, or None (C2).

    Fires off the BudgetGuard's own accounting rather than off any sheet, so a
    truncation taken on a PROJECT-level pass — the naming/vocabulary reads,
    which belong to no sheet and therefore leave no ledger row — is still loud.
    """
    if not isinstance(budget, dict):
        return None
    if not budget.get("truncated"):
        return None
    refused = int(budget.get("refused_charges") or 0)
    return (
        "THE API BUDGET WAS EXHAUSTED AND THIS RUN STOPPED EARLY — $%.4f of the "
        "$%.2f cap was spent and %d further charge(s) were refused, so passes "
        "that were scheduled never ran. Every quantity below is a LOWER BOUND "
        "and every item absent from it is unknown, not zero. Do not read this "
        "take-off as a complete account of the drawing set; raise the cap and "
        "re-run to close the gap"
        % (
            float(budget.get("spent_usd") or 0.0),
            float(budget.get("cap_usd") or 0.0),
            refused,
        )
    )


def _coverage_warnings(
    ledger: CoverageLedger, all_extracted: list, budget=None
) -> List[str]:
    """``report["coverage_warnings"]`` — the ledger's escalations plus the notes.

    A budget truncation leads, because it invalidates the completeness of
    everything that follows it.
    """
    out: List[str] = []
    truncation = _budget_truncation_warning(budget)
    if truncation:
        out.append(truncation)
    return out + list(ledger.warnings()) + _coverage_notes(all_extracted)


def _collect_specification_tables(all_extracted: list) -> List[Dict[str, Any]]:
    tables = []
    for d in all_extracted:
        sheet = d.get("_source_sheet", "unknown")
        for sched in d.get("schedules", []):
            if sched.get("table_purpose") != "specification_reference":
                continue
            tables.append({
                "name": sched.get("name"),
                "source_sheet": sheet,
                "lookup_key": sched.get("lookup_key"),
                "columns": sched.get("columns", []),
                "rows": sched.get("rows", []),
                "description": sched.get("description", ""),
            })
    return tables


# ─── Flatten raw extractions ─────────────────────────────────────────────────

def _flatten_raw_extractions(all_extracted: list) -> List[Dict[str, Any]]:
    items = []
    for d in all_extracted:
        sheet = d.get("_source_sheet", "unknown")
        sheet_type = d.get("sheet_type", "")
        page_id = d.get("_page_id", "")

        # MEASUREMENTS — primary dimensional data
        for m in d.get("measurements", []):
            items.append({
                "category": "measurement",
                "sheet": sheet,
                "sheet_type": sheet_type,
                "page_id": page_id,
                "description": m.get("description", ""),
                "value": m.get("value", ""),
                "unit": m.get("unit", ""),
                "location_on_sheet": m.get("location", ""),
                "source_text": m.get("raw_text", ""),
            })

        # COMPONENTS — counted items (doors, windows, fixtures, etc)
        for c in d.get("components", []):
            items.append({
                "category": "component",
                "sheet": sheet,
                "sheet_type": sheet_type,
                "page_id": page_id,
                "description": c.get("name", ""),
                "value": c.get("quantity"),
                "unit": c.get("unit", ""),
                "location_on_sheet": c.get("location", ""),
                "source_text": c.get("specification", ""),
                # 21-13: per-item quantity provenance (geometry | text_layer |
                # schedule_table | learned | vision_ensemble; "" pre-21).
                "provenance": c.get("provenance", ""),
            })

        # ROOMS — area-based
        for r in d.get("rooms", []):
            items.append({
                "category": "room",
                "sheet": sheet,
                "sheet_type": sheet_type,
                "page_id": page_id,
                "description": r.get("name", ""),
                "value": r.get("area", ""),
                "unit": "sq_ft",
                "location_on_sheet": r.get("dimensions", ""),
                "source_text": r.get("notes", ""),
            })

        # MATERIALS — specs/callouts
        for mat in d.get("materials", []):
            items.append({
                "category": "material",
                "sheet": sheet,
                "sheet_type": sheet_type,
                "page_id": page_id,
                "description": mat.get("type", ""),
                "value": mat.get("quantity", ""),
                "unit": mat.get("unit", ""),
                "location_on_sheet": "",
                "source_text": mat.get("specification", ""),
            })

        # SCHEDULES — flatten EVERY ROW into the CSV (real tabular takeoff data)
        for s in d.get("schedules", []):
            sched_name = s.get("name") or s.get("type") or "Unnamed Schedule"
            sched_type = s.get("schedule_type") or s.get("type") or "schedule"
            header_info = s.get("header_info", "")

            # Header summary row
            items.append({
                "category": "schedule_header",
                "sheet": sheet,
                "sheet_type": sheet_type,
                "page_id": page_id,
                "description": sched_name,
                "value": header_info,
                "unit": sched_type,
                "location_on_sheet": "",
                "source_text": s.get("totals", ""),
            })

            # Each row of the schedule becomes a line item
            rows = s.get("rows", [])
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    # Build a description from the most useful columns
                    desc_parts = []
                    for k in ("DESCRIPTION", "Description", "description",
                              "NAME", "Name", "TYPE", "Type",
                              "ITEM", "Item", "ROOM", "Room"):
                        if row.get(k):
                            desc_parts.append(str(row[k]))
                            break
                    desc = " ".join(desc_parts) or str(row)[:80]

                    # Find quantity-like value
                    qty = ""
                    qty_key = ""
                    for k in ("QTY", "Qty", "quantity", "COUNT", "Count",
                              "KVA", "AMPS", "CFM", "BKR", "SIZE"):
                        if row.get(k):
                            qty = str(row[k])
                            qty_key = k
                            break

                    # Identifier (circuit, door no, etc.)
                    ident = ""
                    for k in ("CKT", "MARK", "NO", "ID", "TAG", "REF"):
                        if row.get(k):
                            ident = str(row[k])
                            break

                    # Flatten the whole row into source_text for traceability
                    row_text = " | ".join(f"{k}={v}" for k, v in row.items() if v)

                    items.append({
                        "category": "schedule_row",
                        "sheet": sheet,
                        "sheet_type": sheet_type,
                        "page_id": page_id,
                        "description": f"[{sched_name}] {desc}",
                        "value": qty,
                        "unit": qty_key.lower() if qty_key else "",
                        "location_on_sheet": f"row {ident}" if ident else "",
                        "source_text": row_text,
                    })

    return items


def _parsed_scale(scale_text):
    """Parse a sheet's printed scale notation into a usable ratio (or None)."""
    try:
        from bobbytailor.deterministic.scale_utils import parse_scale
        s = parse_scale(scale_text)
        return s.to_dict() if s else None
    except Exception:  # noqa: BLE001 - scale parsing is best-effort metadata
        return None


def _image_rel_to_output(img_path) -> str:
    """Make a sheet image path relative to OUTPUT_DIR for safe serving.

    The sheet-image endpoint resolves links under OUTPUT_DIR, so we store a
    relative path (e.g. ``screenshots/Proj_ts/page_0003.png``). Returns "" when
    the path is outside OUTPUT_DIR (e.g. a temp file) so the UI omits the link.
    """
    if not img_path:
        return ""
    try:
        out_root = Path(OUTPUT_DIR).resolve()
        p = Path(img_path).resolve()
        return str(p.relative_to(out_root))
    except Exception:
        return ""


def _sheet_image_rel(d: dict) -> str:
    """Servable image path relative to OUTPUT_DIR for a sheet extraction dict."""
    rel = d.get("_image_rel") or ""
    if rel:
        if rel.startswith("screenshots/"):
            return rel
        return _image_rel_to_output(rel)
    return _image_rel_to_output(d.get("_source_sheet"))


def _build_sheet_assets(all_extracted: list) -> Dict[str, Any]:
    """Map sheet display names → image paths for UI traceability (lightbox / scale tab)."""
    assets: Dict[str, Any] = {}
    for d in all_extracted:
        if d.get("_skipped") or d.get("error"):
            continue
        name = d.get("_sheet_name") or d.get("_source_sheet")
        if not name:
            continue
        img = _sheet_image_rel(d)
        if img:
            assets[name] = {
                "image": img,
                "page_id": d.get("_page_id"),
                "type": d.get("_sheet_type") or d.get("sheet_type") or "",
            }
    return assets


_SCALE_SHEET_TYPES = frozenset({"floor_plan", "civil_site", "roof_plan"})
_SCALE_NAME_MARKERS = (
    "FLOOR PLAN", "ROOF PLAN", "SITE PLAN", "CIVIL", "LAYOUT PLAN",
    "PLOT PLAN", "MASTER PLAN",
)


def _is_scale_bearing(name: str, sheet_type: str = "") -> bool:
    """True when a sheet carries a drawing scale the user may need to verify."""
    typ = (sheet_type or "").strip().lower()
    if typ in _SCALE_SHEET_TYPES:
        return True
    upper = (name or "").upper()
    return any(m in upper for m in _SCALE_NAME_MARKERS)


def _scale_only_entry(
    sheet: str,
    image: str,
    sheet_type: str,
    scale_text: str = "",
    page_id=None,
    scale_source: str = "vision_detected",
) -> Dict[str, Any]:
    parsed = _parsed_scale(scale_text)
    fpi = parsed.get("feet_per_inch") if parsed else None
    return {
        "sheet": sheet,
        "page_id": page_id,
        "type": sheet_type,
        "image": image,
        "scale_text": scale_text or "",
        "feet_per_inch": fpi,
        "scale_confidence": "medium" if fpi else "low",
        "auto_verified": False,
        "scale_source": scale_source,
        "needs_scale_verify": True,
        "page_width_pt": None,
        "page_height_pt": None,
        "raw": None,
        "measured": {},
        "viewports": [],
    }


def enrich_scale_calibration(calib: dict, report: dict) -> dict:
    """Backfill scale rows for plan sheets missing from an older calibration file."""
    if not calib:
        calib = {"sheets": []}
    sheets = list(calib.get("sheets") or [])
    seen = {s["sheet"] for s in sheets if s.get("sheet")}
    assets = report.get("sheet_assets") or {}
    log_by_name = {
        e["sheet"]: e for e in (report.get("sheet_log") or [])
        if e.get("sheet")
    }

    def _append(name: str, image: str, sheet_type: str, scale_text: str, page_id=None):
        if not name or name in seen or not image:
            return
        if not _is_scale_bearing(name, sheet_type):
            return
        sheets.append(_scale_only_entry(name, image, sheet_type, scale_text, page_id))
        seen.add(name)

    for name, meta in assets.items():
        log_e = log_by_name.get(name) or {}
        _append(
            name,
            meta.get("image") or "",
            meta.get("type") or log_e.get("type") or "",
            log_e.get("scale") or "",
            meta.get("page_id") or log_e.get("page_id"),
        )

    calib["sheets"] = sheets
    return calib


def _build_scale_calibration(project_name: str, run_folder: str,
                             all_extracted: list) -> Dict[str, Any]:
    """Per-sheet scale + scale-independent raw geometry for the Verify module.

    Only sheets that produced vector geometry (floor/site/roof plans) are
    scale-dependent and therefore recomputable. Each entry carries the detected
    scale, its confidence/source, the raw point measures, and the currently
    computed measured quantities, plus a link to the sheet image for tracing.
    """
    sheets: List[Dict[str, Any]] = []
    seen: set = set()
    for d in all_extracted:
        geom = d.get("_geometry")
        sheet = d.get("_sheet_name") or d.get("_source_sheet") or "unknown"
        if sheet in seen:
            continue
        image = _sheet_image_rel(d)
        sheet_type = d.get("_sheet_type") or d.get("sheet_type") or ""

        if geom:
            raw = geom.get("raw")
            scale_meta = geom.get("scale") or {}
            fpp = scale_meta.get("feet_per_point")
            fpi = round(fpp * 72.0, 4) if fpp else None
            confidence = geom.get("confidence") or scale_meta.get("confidence") or "none"
            auto_verified = bool(fpi and confidence == "high"
                                 and not geom.get("needs_review", True))
            sheets.append({
                "sheet": sheet,
                "page_id": d.get("_page_id"),
                "type": sheet_type,
                "image": image,
                "scale_text": d.get("scale") or "",
                "feet_per_inch": fpi,
                "scale_confidence": confidence,
                "auto_verified": auto_verified,
                "scale_source": scale_meta.get("method") or "none",
                "page_width_pt": geom.get("page_width_pt"),
                "page_height_pt": geom.get("page_height_pt"),
                "raw": raw,
                "measured": {
                    "footprint_sf": geom.get("footprint_sf"),
                    "total_linework_lf": geom.get("total_linework_lf"),
                    "long_run_lf": geom.get("long_run_lf"),
                },
                "viewports": geom.get("viewports") or [],
            })
            seen.add(sheet)
            continue

        # No vector geometry — still list every scale-bearing plan sheet so the
        # user can verify per-sheet scales (partial floor plans often differ).
        if not image or not _is_scale_bearing(sheet, sheet_type):
            continue
        sheets.append(_scale_only_entry(
            sheet, image, sheet_type,
            d.get("scale") or "",
            d.get("_page_id"),
        ))
        seen.add(sheet)
    return {
        "project_name": project_name,
        "run_folder": run_folder,
        "generated_at": datetime.now().isoformat(),
        "sheets": sheets,
    }


def _normalize_calculated(estimates: list) -> List[Dict[str, Any]]:
    """Calculator output already has source tracing — just ensure consistent keys."""
    normalized = []
    for e in estimates:
        normalized.append({
            "item_type": e.get("item_type", ""),
            "description": e.get("description", ""),
            "raw_value": e.get("raw_value", ""),
            "raw_unit": e.get("raw_unit", ""),
            "calculated_quantity": e.get("quantity", ""),
            "calculated_unit": e.get("unit", ""),
            # Preserve deterministic provenance (geometry/text_layer/schedule_table)
            # so a symbol count is never surfaced as a null-provenance number.
            "provenance": e.get("provenance"),
            # What corroborated a counted quantity — geometry, a printed
            # schedule, or nothing — and the sheet kind it was read from. This
            # whitelist is the only gate between the calculator and
            # aggregate_takeoff, so a verdict left off it would be a verdict
            # nobody downstream can ever see (28-01).
            "count_corroboration": e.get("count_corroboration"),
            "count_evidence_sheet_kind": e.get("count_evidence_sheet_kind"),
            "waste_factor": e.get("waste_factor_applied", 1.0),
            "formula_applied": e.get("formula", ""),   # NEW: shows the actual math
            "approximate": e.get("approximate", False),
            "estimation_table": e.get("table_used", "none"),
            "source_sheet": e.get("source_sheet", ""),
            "source_location": e.get("source_location", ""),
            "source_text": e.get("source_raw", ""),
            "specification": e.get("specification", ""),
            # Preserve provenance so aggregation can treat authoritative companion
            # take-off legend items as the single source of truth for their item.
            "qty_source": e.get("qty_source", ""),
            # Uncertainty signals — rolled up per item in aggregate_takeoff so the
            # summary can highlight shaky rows for human review.
            "confidence": e.get("confidence"),
            "needs_review": bool(e.get("needs_review", False)),
            "review_reason": e.get("review_reason", ""),
        })
    return normalized


# ─── Grouping ────────────────────────────────────────────────────────────────

def _group_by_sheet(items: list) -> dict:
    out = {}
    for item in items:
        sheet = item.get("sheet") or item.get("source_sheet") or "unknown"
        out.setdefault(sheet, []).append(item)
    return {k: {"count": len(v), "items": v} for k, v in out.items()}


def _group_by_category(items: list) -> dict:
    out = {}
    for item in items:
        cat = item.get("category", "unknown")
        out.setdefault(cat, []).append(item)
    return {cat: {"count": len(v), "items": v} for cat, v in out.items()}


def _group_by_table(items: list) -> dict:
    """Group calculated items by which estimation table was applied."""
    out = {}
    for item in items:
        t = item.get("estimation_table", "none")
        out.setdefault(t, []).append(item)
    return {t: {"count": len(v), "items": v} for t, v in out.items()}


# ─── CSV writers ─────────────────────────────────────────────────────────────

def _write_raw_csv(items: list, path: Path):
    """Raw extraction CSV — every measurement/component/room/material Claude saw."""
    fields = [
        "category", "sheet", "sheet_type", "page_id",
        "description", "value", "unit", "provenance",
        "location_on_sheet", "source_text"
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        if items:
            w.writerows(items)


def _takeoff_summary_csv_quantity(row: dict):
    """The quantity cell for one take-off row. A blank is written BLANK.

    The old cell was ``quantity_fmt or quantity``, and ``quantity_fmt`` is the
    em-dash for a never-measured item — so the CSV said "—" where the JSON said
    ``0.0`` and the workbook inferred NOT MEASURED from the value. Writing the
    EMPTY STRING is the honest cell, and it keeps scoring correct BY
    CONSTRUCTION rather than by a compensating change on the scorer side:
    ``scripts/score_report_dir._num`` already maps ``""`` to nothing.

    A measured zero still writes ``0``. That is the whole distinction this phase
    exists to preserve — a building with no CMU is a finding, not an absence.
    """
    quantity = row.get("quantity")
    if quantity is None or quantity == "":
        return ""
    return row.get("quantity_fmt") or quantity


def _write_takeoff_summary_csv(aggregated: list, path: Path):
    """StackCT-style consolidated takeoff summary.

    ``provenance`` was appended LAST so every existing column kept its position
    for a consumer reading by index rather than by name; ``quantity_route``
    (28-06) is appended after it under the same contract.

    The two columns answer different questions and a reader needs both.
    ``provenance`` says what to make of the row — MEASURED, NEEDS REVIEW, NOT
    MEASURED. ``quantity_route`` says how the number was PRODUCED, and therefore
    whether a repeat run reproduces it. A row can be MEASURED and still be a
    number the next run answers differently; Crow's ``Stairs`` was exactly that.

    A row with no published number writes an EMPTY route cell, for the same
    reason :func:`_takeoff_summary_csv_quantity` writes an empty quantity cell:
    there is no number to characterise, and a pedigree printed beside a blank
    would read as evidence that a number exists.
    """
    fields = ["item", "quantity", "unit", "confidence", "needs_review",
              "source", "review_notes", "source_sheets", "line_count",
              "provenance", "quantity_route"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in aggregated:
            w.writerow({
                "item": row.get("item"),
                "quantity": _takeoff_summary_csv_quantity(row),
                # Read from the record; provenance_of_row is consulted only for
                # a pre-23 row the aggregator never classified. ONE place
                # decides this vocabulary (INV-08 §5).
                "provenance": row.get("provenance") or provenance_of_row(row),
                # Absent (a pre-28-06 row) and None (a blank) both write empty.
                "quantity_route": row.get("quantity_route") or "",
                "unit": row.get("unit"),
                "confidence": row.get("confidence") or "",
                "needs_review": "yes" if row.get("needs_review") else "",
                "source": row.get("source") or "vision",
                "review_notes": "; ".join(row.get("review_reasons", [])),
                "source_sheets": ", ".join(row.get("source_sheets", [])),
                "line_count": row.get("line_count", 0),
            })


def _write_calculated_csv(items: list, path: Path):
    """Calculated takeoff CSV — quantities with estimation tables applied + traceability."""
    fields = [
        "item_type", "description",
        "raw_value", "raw_unit",
        "calculated_quantity", "calculated_unit",
        "waste_factor", "formula_applied", "approximate", "estimation_table",
        "confidence", "needs_review", "review_reason",
        "source_sheet", "source_location", "source_text", "specification"
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        if items:
            w.writerows(items)


# ─── Human-readable summary ──────────────────────────────────────────────────

# Provenance values counted as deterministic — the numerator of the share the
# accuracy gate asserts ≥97% accurate (geometry/text-derived quantities).
_DETERMINISTIC_PROVENANCES = ("geometry", "text_layer", "schedule_table")


def _coverage_lines(report: dict) -> list:
    """COVERAGE section: what the run did NOT measure (23-17, INV-08 §3.3).

    Returns an EMPTY list when the report carries no ledger, so a pre-23 report
    renders byte-identically — the section simply does not exist, exactly as it
    did not exist before.

    Everything above this section is an account of what WAS found. This is the
    only part of ``summary.txt`` that states what was not, and it says so in
    words rather than leaving a client to infer it from a missing row.
    """
    cov = report.get("coverage")
    if not isinstance(cov, dict) or not cov:
        return []

    import textwrap

    def _n(key):
        value = cov.get(key)
        return 0 if value is None else value

    lines = [
        "─" * 70,
        "COVERAGE  (a blank is NOT a zero — an unmeasured item has no number,",
        "           which is a different fact from a measured zero)",
        "─" * 70,
        f"Pages in source PDF:          {_n('pages_in_source'):>5}",
        f"  measured (geometry):        {_n('sheets_measured'):>5}",
    ]

    # Its own line, and only when it happened: a page whose measurement was cut
    # short by the CAP is not a measured page and is not a skipped one either.
    truncated_pages = _n("sheets_budget_truncated")
    if truncated_pages:
        lines.append(
            f"  CUT SHORT (budget spent):   {truncated_pages:>5}"
            "   ← incomplete, not zero"
        )

    lines += [
        f"  vision-only (no geometry):  {_n('sheets_vision_only'):>5}",
        f"  skipped by classifier:      {_n('sheets_skipped'):>5}",
        f"  not applicable (cover/idx): {_n('sheets_not_applicable'):>5}",
        f"  errored:                    {_n('sheets_errored'):>5}",
        "{:<64}{:>5}".format("Drawings measured:", _n("drawings_measured")),
        "{:<64}{:>5}".format(
            "Drawings dropped (no printed scale of their own):",
            _n("drawings_dropped_no_scale"),
        ),
        "{:<64}{:>5}".format(
            "Viewports excluded as off-scale (measuring them would be wrong):",
            _n("drawings_excluded_off_scale"),
        ),
    ]

    silent = cov.get("silent_loss_pages") or []
    if silent:
        lines.append("{:<64}{:>5}".format(
            "Pages carrying measurable drawings that were NOT measured:",
            len(silent),
        ))

    warnings = report.get("coverage_warnings") or []
    if warnings:
        lines.append("")
        for warning in warnings:
            wrapped = textwrap.wrap(str(warning), width=66) or [""]
            lines.append(f"!! {wrapped[0]}")
            for cont in wrapped[1:]:
                lines.append(f"   {cont}")

    items = report.get("item_coverage") or []
    if items:
        lines.append("")
        lines.append(f"Expected line items:          {len(items):>5}")
        lines.append(f"  MEASURED                    {_n('items_measured'):>5}")
        lines.append(f"  NEEDS REVIEW                {_n('items_needs_review'):>5}")
        lines.append(f"  HUMAN INPUT                 {_n('items_human_input'):>5}")
        # C4: an app-injected estimating convention is neither measured nor
        # human-supplied. Only rendered when one exists, so a run without any
        # renders exactly as before.
        if _n("items_standard"):
            lines.append(f"  STANDARD ITEM               {_n('items_standard'):>5}")
        not_measured = _n("items_not_measured")
        marker = "   ← do NOT read these as zero" if not_measured else ""
        lines.append(f"  NOT MEASURED                {not_measured:>5}{marker}")

    lines.append("")
    return lines


#: Human-readable names for the record kinds ``fuse_sheet`` emits. A kind that
#: is not in this map renders its own raw value with underscores opened out — an
#: unrecognised kind must still be COUNTED and SHOWN, never quietly skipped,
#: which is the same failure this whole section exists to abolish.
_UNNAMED_KIND_LABELS = {
    "symbol_group": "symbol group",
    "wall_class": "wall thickness class",
    "room": "room",
}

#: How many individual candidates the section lists before deferring the rest to
#: ``takeoff.json``. Every record is always counted in the totals above the list
#: and the remainder is named on its own line, so the cap bounds the PAGE, never
#: the account (T-24-25).
_UNNAMED_GEOMETRY_LIST_CAP = 25


def _unnamed_quantity_text(value) -> Optional[str]:
    """A ledger quantity as a reader would write it, or None when there is none.

    ``None`` is returned for a record whose quantity was never bound to a scale
    — INV-08's recorded ABSENCE of a measurement. The caller renders that as a
    blank, never as a zero. A whole number keeps no decimal point, because a
    count of 56 repeated marks is 56 things and ``56.0 EA`` reads like a
    measurement that happened to land on an integer.
    """
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number == int(number):
        return "{:,.0f}".format(number)
    return "{:,.1f}".format(number)


def _unnamed_geometry_lines(report: dict) -> list:
    """UNIDENTIFIED GEOMETRY section: measured, but not identified (24-06).

    Returns an EMPTY list when the run carried no unnamed geometry, so a report
    without it renders byte-identically — the section does not exist rather than
    existing and saying zero, exactly as :func:`_coverage_lines` behaves for a
    pre-23 report.

    This sits immediately after COVERAGE because the two answer adjacent
    questions. COVERAGE says what the run did NOT measure. This says what it DID
    measure and could not name — a different fact, and one that has to be stated
    in words. 24-04 stopped these candidates publishing under our own handle for
    them (``SYM-6``, ``ROOM-3``, ``WALL-TC4``); leaving them out of the summary
    as well would replace one defect with its mirror image, because a
    silently-omitted 36-count cluster reads to a client as "there are no
    columns" (INV-08: a deletion and a zero read identically).
    """
    ledger = [
        r for r in (report.get(UNNAMED_GEOMETRY_KEY) or []) if isinstance(r, dict)
    ]
    if not ledger:
        return []

    lines = [
        "─" * 70,
        "UNIDENTIFIED GEOMETRY  (these were MEASURED — the quantities below",
        "                        are real and so are the objects; what the",
        "                        drawings do not say is what they ARE)",
        "─" * 70,
        "{:<64}{:>5}".format("Candidates measured but not identified:", len(ledger)),
        "",
        "They are held out of the take-off above on purpose. Naming one of them",
        "from our own internal handle for it would put an identifier this app",
        "invented in front of a client as the name of a thing to price. Their",
        "absence from the take-off is an absence of a NAME, never of an object.",
        "",
    ]

    # ── by kind, and by unit within it ───────────────────────────────────────
    # Grouped by (kind, unit) because a single total across mixed units would be
    # a number that means nothing. Insertion order is kept so the breakdown reads
    # in the order the sheets produced it.
    totals: dict = {}
    order: list = []
    for record in ledger:
        key = (str(record.get("kind") or "unrecorded"), str(record.get("unit") or ""))
        if key not in totals:
            totals[key] = {"count": 0, "quantity": 0.0, "unquantified": 0}
            order.append(key)
        slot = totals[key]
        slot["count"] += 1
        quantity = _unnamed_quantity_text(record.get("quantity"))
        if quantity is None:
            # INV-08 again: a record whose quantity is None is a measurement
            # that was never bound to a scale. Summing it in as a zero would
            # publish a number nobody measured, so it is counted apart.
            slot["unquantified"] += 1
        else:
            slot["quantity"] += float(record.get("quantity"))

    row = "  {:<14} {:>13}  {:<18} {}"
    for kind, unit in order:
        slot = totals[(kind, unit)]
        label = _UNNAMED_KIND_LABELS.get(kind, kind.replace("_", " "))
        measured = slot["count"] - slot["unquantified"]
        quantity_txt = (
            "{} {}".format(_unnamed_quantity_text(slot["quantity"]), unit).strip()
            if measured else ""
        )
        lines.append(
            "  {:<32}{:>4} candidate(s){:>18}".format(label, slot["count"], quantity_txt)
        )
        if slot["unquantified"]:
            lines.append(
                "      ({:,} with no measured quantity — unknown, not zero)".format(
                    slot["unquantified"]
                )
            )

    # ── the individual candidates ────────────────────────────────────────────
    lines.append("")
    lines.append(row.format("Candidate", "Quantity", "Sheet", "Why naming failed"))
    for record in ledger[:_UNNAMED_GEOMETRY_LIST_CAP]:
        quantity = _unnamed_quantity_text(record.get("quantity"))
        quantity_txt = (
            "(not measured)" if quantity is None
            else "{} {}".format(quantity, record.get("unit") or "").strip()
        )
        lines.append(
            row.format(
                str(record.get("candidate_id") or "?")[:14],
                quantity_txt,
                str(record.get("sheet") or "?")[:18],
                str(record.get("reason") or "").replace("_", " "),
            )
        )

    remainder = len(ledger) - _UNNAMED_GEOMETRY_LIST_CAP
    if remainder > 0:
        # Named, never silently truncated: a list that stops without saying it
        # stopped is the same lie as a missing row (T-24-25).
        lines.append(
            "  ... and {:,} more — every one of them is in the".format(remainder)
        )
        lines.append(
            "      `{}` list in takeoff.json".format(UNNAMED_GEOMETRY_KEY)
        )

    lines.append("")
    return lines


def _scale_confidence_lines(report: dict) -> list:
    """SCALE CONFIDENCE section: per-sheet main-plan solve summary (21-13).

    Every field access is None-guarded so pre-21 reports (no
    ``scale_confidence`` on sheet_log entries) render without KeyError.
    """
    lines = ["─" * 70, "SCALE CONFIDENCE", "─" * 70]
    any_row = False
    for entry in report.get("sheet_log") or []:
        sc = entry.get("scale_confidence")
        if not sc:
            continue
        viewports = [v for v in sc if isinstance(v, dict)]
        main = next((v for v in viewports if v.get("is_main")), None)
        if main is None:
            main = next((v for v in viewports if v.get("fpi")), None)
        sheet = str(entry.get("sheet") or "?")
        mode = entry.get("measurement_mode") or ""
        if main is None:
            lines.append(
                f"  [{sheet:<28}] no solved viewport scale"
                + (f"  (mode={mode})" if mode else "")
            )
            any_row = True
            continue
        fpi = main.get("fpi")
        fpi_txt = f"1\" = {fpi:g}'" if fpi else "unsolved"
        printed = main.get("printed_agreement")
        printed_txt = (
            "printed ✓" if printed is True
            else ("printed ✗" if printed is False else "printed n/a")
        )
        share = main.get("inlier_share") or 0.0
        lines.append(
            f"  [{sheet:<28}] main {str(main.get('region_id') or '?'):<4} "
            f"{fpi_txt:<12} conf={str(main.get('confidence') or '?'):<7} "
            f"method={str(main.get('method') or '?'):<26} "
            f"({main.get('n_inliers') or 0} dims, {share * 100.0:.0f}% share, {printed_txt})"
        )
        any_row = True
    if not any_row:
        lines.append("  (no per-viewport scale data recorded)")
    lines.append("")
    return lines


def _provenance_breakdown_lines(report: dict) -> list:
    """PROVENANCE BREAKDOWN section: item counts per quantity provenance.

    The deterministic share (geometry/text_layer/schedule_table) is the
    number the plans-only accuracy gate asserts ≥97% accurate. None-guarded
    for pre-21 reports (components without a provenance field).
    """
    lines = ["─" * 70, "PROVENANCE BREAKDOWN", "─" * 70]
    counts: dict = {}
    for item in report.get("raw_line_items") or []:
        if not isinstance(item, dict) or item.get("category") != "component":
            continue
        prov = str(item.get("provenance") or "").strip()
        if prov:
            counts[prov] = counts.get(prov, 0) + 1
    if not counts:
        lines.append("  (no provenance-tagged items recorded)")
        lines.append("")
        return lines
    total = sum(counts.values())
    for prov in sorted(counts, key=lambda p: -counts[p]):
        lines.append(f"  {prov:<18} {counts[prov]:>5} items")
    deterministic = sum(counts.get(p, 0) for p in _DETERMINISTIC_PROVENANCES)
    lines.append(
        f"  Geometry/text-derived quantities: {deterministic}/{total} "
        f"({deterministic * 100.0 / total:.1f}% of provenance-tagged items)"
    )
    lines.append("")
    return lines


#: How many reading-route rows are listed individually before the section
#: switches to a "and N more" tail. The cap bounds the PAGE, never the account —
#: same contract as :data:`_UNNAMED_GEOMETRY_LIST_CAP`.
_REPRODUCIBILITY_LIST_CAP = 40


def _reproducibility_lines(report: dict) -> list:
    """REPRODUCIBILITY section: which published numbers a repeat run may move.

    Returns an EMPTY list when no published row carries a ``quantity_route`` at
    all, so a report produced before 28-06 renders byte-identically — the same
    empty contract :func:`_coverage_lines` and :func:`_unnamed_geometry_lines`
    keep. Saying "no row took the reading route" about a run that never
    classified its rows would answer a question that run never asked.

    When the field IS present the section always renders, including when
    nothing took the reading route. An absent section and a clean run must not
    look the same: a reader who sees nothing cannot tell "we checked and every
    number is reproducible" from "nobody checked".

    The prose states the fact and fences the two conclusions a reader would
    otherwise draw, the way the unidentified-geometry section does when it says
    a candidate's absence is an absence of a NAME and never of an object:

    1. A number listed here is not thereby WRONG. It is not reproducible, which
       is a different property; the app has no opinion here about its accuracy.
    2. This section cannot see the other half of the variance. Whether a row is
       produced AT ALL is decided in the same per-sheet reading, and a single
       run has no way to know about its own absences — which is how Crow's
       ``Door Frames-HM`` published 4 EA in one run and nothing in the next off
       a row that was geometry-backed in the run that had it.
    """
    rows = [r for r in (report.get("takeoff_summary") or []) if isinstance(r, dict)]
    if not any("quantity_route" in r for r in rows):
        return []

    reading = [r for r in rows
               if r.get("quantity_route") == QUANTITY_ROUTE_SHEET_READING]

    lines = [
        "─" * 70,
        "REPRODUCIBILITY  (which of these numbers a repeat run may answer",
        "                  differently — this is not a claim that any one of",
        "                  them is wrong)",
        "─" * 70,
        "{:<64}{:>5}".format(
            "Published numbers that came from a model READING a sheet:",
            len(reading),
        ),
        "",
    ]

    if not reading:
        lines.extend([
            "There are none — no published number came from a model reading a sheet.",
            "Every quantity below was measured off the drawing's own geometry, read",
            "verbatim out of the PDF's text, or copied out of a table printed on the",
            "plans, and a repeat run over the same file reproduces all of them.",
            "",
            "This is stated rather than left out, because a section that disappeared",
            "when it had nothing to report would read exactly like a run that never",
            "asked the question.",
            "",
        ])
    else:
        lines.extend([
            "Every other number below was measured off the drawing or copied out of a",
            "table printed on the plans, and a repeat run reproduces it. These came",
            "from a model reading a sheet image, and two identical runs of this",
            "pipeline over one set of plans have read the same drawings as different",
            "numbers. A number here may be exactly right; what it is not is settled.",
            "",
        ])
        listed = reading[:_REPRODUCIBILITY_LIST_CAP]
        for row in listed:
            quantity = row.get("quantity_fmt")
            if quantity in (None, ""):
                quantity = row.get("quantity")
            lines.append(
                "  {:<34} {:>14}  {}".format(
                    str(row.get("item") or "?")[:34],
                    str(quantity),
                    str(row.get("unit") or ""),
                )
            )
        if len(reading) > len(listed):
            # The cap bounds the page, never the account: a list that stops
            # without saying it stopped is the same lie as a missing row.
            lines.append(
                "  ... and %d more, all of them in takeoff_summary.csv under "
                "quantity_route" % (len(reading) - len(listed))
            )
        lines.append("")

    lines.extend([
        "What this section CANNOT tell you: whether the row appears at all in a",
        "repeat run. That is decided in the same per-sheet reading, one layer",
        "above any number, and a single run has no way to see its own absences.",
        "Comparing two runs is the only thing that shows it.",
        "",
    ])
    return lines


def _write_summary(report: dict, path: Path):
    lines = [
        "═" * 70,
        "QUANTITY TAKEOFF SUMMARY",
        "═" * 70,
        f"Project:          {report['project_name']}",
        f"Generated:        {report['generated_at']}",
        f"Sheets analyzed:  {report['sheets_processed']}",
        f"Raw items:        {report['total_line_items']}",
        f"Calculated items: {report['total_calculated_items']}",
        "",
        "─" * 70,
        "API USAGE & COST",
        "─" * 70,
    ]

    usage = report.get("api_usage", {})
    lines.append(f"Total cost:       ${usage.get('total_cost_usd', 0):.4f} USD")
    # The attribution split, only when there is something project-level to
    # attribute. A run whose every dollar landed on a sheet renders as before.
    project_level = usage.get("project_level_cost_usd")
    if project_level:
        lines.append(
            f"  on sheets:      ${usage.get('sheet_attributed_cost_usd', 0):.4f} USD"
        )
        lines.append(
            f"  project-level:  ${project_level:.4f} USD  "
            "(charged to the run, stamped on no sheet — the naming/vocabulary "
            "passes and any sheet that lost its usage stamp)"
        )
    lines.append(f"Input tokens:     {usage.get('total_tokens_in', 0):,}")
    lines.append(f"Output tokens:    {usage.get('total_tokens_out', 0):,}")
    lines.append(f"Cost per sheet:   ${usage.get('cost_per_sheet', 0):.4f} USD")

    # 21-13: per-run budget guard accounting (None-guarded — pre-21 runs
    # simply omit the line, same graceful pattern as api_usage in 03-03).
    budget = report.get("budget")
    if isinstance(budget, dict) and budget.get("cap_usd") is not None:
        exhausted = "  (EXHAUSTED — remaining items flagged)" if budget.get("exhausted") else ""
        lines.append(
            f"Budget:           ${budget.get('spent_usd', 0):.4f} spent of "
            f"${budget.get('cap_usd', 0):.2f} cap{exhausted}"
        )
        # C2: `exhausted` asks whether budget REMAINS; `truncated` asks whether
        # the cap STOPPED work. Crow ended exhausted=False having refused a
        # charge and skipped two sheets' remaining passes, and summary.txt said
        # nothing at all. A truncated run must never read as a complete one.
        if budget.get("truncated"):
            refused = int(budget.get("refused_charges") or 0)
            lines.append(
                "!! BUDGET EXHAUSTED — THIS RUN IS INCOMPLETE: "
                f"{refused} charge(s) refused; scheduled passes never ran."
            )
            lines.append(
                "   Every quantity below is a LOWER BOUND and every absent item "
                "is unknown, not zero."
            )
    lines.append("")

    # Between API USAGE and SCALE CONFIDENCE, and empty on a pre-23 report.
    lines.extend(_coverage_lines(report))
    # Immediately after COVERAGE, and empty when the run named everything it
    # measured. The two answer adjacent questions: what did the run not measure,
    # then what did it measure but not identify.
    lines.extend(_unnamed_geometry_lines(report))
    lines.extend(_scale_confidence_lines(report))
    lines.extend(_provenance_breakdown_lines(report))
    # Immediately after PROVENANCE BREAKDOWN, whose question it extends. That
    # section counts what each RAW item was tagged with; this says which
    # PUBLISHED numbers a repeat run may answer differently — the fact the
    # 3-of-51 quantity deltas between two identical Crow runs turned on, and one
    # no other section of this file states (28-06).
    lines.extend(_reproducibility_lines(report))

    def _s(val, default=""):
        """Coerce None / non-string values to a safe string for formatting."""
        if val is None:
            return default
        return str(val)

    def _i(val, default=0):
        """Coerce None / missing to integer 0 for column formatting."""
        if val is None or val == "":
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    linked_added = report.get("linked_sheets_added") or []
    linked_suggested = report.get("linked_sheets_suggested") or []
    cross_refs = report.get("cross_references") or []

    if linked_added or linked_suggested or cross_refs:
        lines += ["─" * 70, "LINKED SHEETS & CROSS-REFERENCES", "─" * 70]

        if linked_added:
            lines.append(f"Auto-included linked detail sheets: {len(linked_added)}")
            for entry in linked_added:
                sheet = _s(entry.get("sheet_name"), "?")
                ref_from = _s(entry.get("ref_from"))
                suffix = f"  (referenced from {ref_from})" if ref_from else ""
                lines.append(f"  • {sheet}{suffix}")
            lines.append("")

        if linked_suggested:
            lines.append(
                f"Linked sheets discovered but not captured "
                f"(AUTO_INCLUDE_LINKED_SHEETS=false): {len(linked_suggested)}"
            )
            for entry in linked_suggested:
                sheet = _s(entry.get("sheet_name"), "?")
                ref_from = _s(entry.get("ref_from"))
                suffix = f"  (referenced from {ref_from})" if ref_from else ""
                lines.append(f"  • {sheet}{suffix}")
            lines.append("")

        if cross_refs:
            resolved_n = sum(
                1 for r in cross_refs if r.get("resolution_status") == "resolved"
            )
            lines.append(
                f"Drawing cross-references: {len(cross_refs)} total, "
                f"{resolved_n} resolved"
            )
            for ref in cross_refs:
                from_sheet = _s(ref.get("from_sheet"), "?")
                ref_sheet = _s(ref.get("ref_sheet"), "?")
                ref_num = _s(ref.get("ref_number"), "?")
                item = _s(ref.get("item_described"))
                status = _s(ref.get("resolution_status"), "unknown").replace("_", " ")
                detail = f" — {item}" if item else ""
                lines.append(
                    f"  • {from_sheet} → detail {ref_num} on {ref_sheet}{detail}  "
                    f"[{status.upper()}]"
                )
                if ref.get("resolution_status") == "resolved" and ref.get("resolved_spec"):
                    spec = ref["resolved_spec"]
                    if spec.get("schedule_name"):
                        lines.append(
                            f"      resolved via schedule: {_s(spec.get('schedule_name'))}"
                        )
            lines.append("")

    lines += [
        "─" * 70,
        "SHEET-BY-SHEET LOG (source traceability)",
        "─" * 70,
    ]

    for s in report.get("sheet_log", []):
        lines.append(
            f"  [{_s(s.get('sheet'), '?'):<35}] "
            f"type={_s(s.get('type'), '?'):<14} "
            f"meas={_i(s.get('measurements')):>3} "
            f"comp={_i(s.get('components')):>3} "
            f"rooms={_i(s.get('rooms')):>3} "
            f"mat={_i(s.get('materials')):>3} "
            f"conf={_s(s.get('confidence'), '?')}"
        )

    lines += ["", "─" * 70, "RAW ITEMS BY CATEGORY", "─" * 70]
    for cat, data in report.get("by_category", {}).items():
        lines.append(f"  {_s(cat).upper():15s}  {_i(data.get('count')):>4} items")

    lines += ["", "─" * 70, "CALCULATED TAKEOFF BY ESTIMATION TABLE", "─" * 70]
    for tbl, data in report.get("by_table", {}).items():
        lines.append(f"  {_s(tbl).upper():15s}  {_i(data.get('count')):>4} items")

    summary_rows = report.get("takeoff_summary", [])
    if summary_rows:
        lines += [
            "",
            "═" * 70,
            "PROJECT TAKEOFF SUMMARY (CONSOLIDATED)",
            "═" * 70,
            f"  {'ITEM':<40} {'QTY':>12}  {'UNIT':<8}",
            "─" * 70,
        ]
        for row in summary_rows:
            lines.append(
                f"  {row.get('item', ''):<40} {row.get('quantity_fmt', ''):>12}  {row.get('unit', ''):<8}"
            )

    lines += ["", "─" * 70, "DETAILED CALCULATED TAKEOFF (with sources)", "─" * 70]
    for item in report.get("calculated_takeoff", []):
        qty = _s(item.get("calculated_quantity"), "?")
        unit = _s(item.get("calculated_unit"))
        desc = _s(item.get("description"))
        sheet = _s(item.get("source_sheet"))
        loc = _s(item.get("source_location"))
        table = _s(item.get("estimation_table"))
        wf = item.get("waste_factor") or 1.0
        lines.append(f"  {qty} {unit:<6}  {desc:<40}  [table:{table}, waste:×{wf}]")
        lines.append(f"              source: {sheet} @ {loc}")

    lines += ["", "─" * 70, "RAW DIMENSIONAL MEASUREMENTS (by sheet)", "─" * 70]
    by_sheet_raw = {}
    for item in report.get("raw_line_items", []):
        if item.get("category") == "measurement":
            by_sheet_raw.setdefault(_s(item.get("sheet"), "unknown"), []).append(item)
    for sheet, items in by_sheet_raw.items():
        lines.append(f"\n  [{sheet}]  ({len(items)} measurements)")
        for item in items:
            v = _s(item.get("value"), "—")
            u = _s(item.get("unit"))
            lines.append(f"     {v} {u:<8}  {_s(item.get('description'))}")
            if item.get("location_on_sheet"):
                lines.append(f"                @ {_s(item.get('location_on_sheet'))}")

    with open(path, "w") as f:
        f.write("\n".join(lines))
