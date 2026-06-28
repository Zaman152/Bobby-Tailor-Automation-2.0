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
from config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def generate_report(project_name: str,
                    all_extracted: list,
                    all_estimates: Optional[list] = None,
                    folder_id: Optional[int] = None,
                    cross_references: Optional[list] = None,
                    linked_sheets: Optional[list] = None,
                    manifest=None) -> dict:
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
    from aggregator import aggregate_takeoff
    takeoff_summary = aggregate_takeoff(calculated_items, manifest=manifest)

    # Aggregate API usage across all sheets
    total_cost = sum(d.get("_cost_usd", 0) for d in all_extracted)
    total_tokens_in = sum(d.get("_tokens_in", 0) for d in all_extracted)
    total_tokens_out = sum(d.get("_tokens_out", 0) for d in all_extracted)

    model_counts: dict[str, int] = {}
    for d in all_extracted:
        m = d.get("_model_used", "")
        if m:
            model_counts[m] = model_counts.get(m, 0) + 1

    report = {
        "project_name": project_name,
        "folder_id": folder_id,
        "generated_at": datetime.now().isoformat(),
        "sheets_processed": len(all_extracted),
        "total_line_items": len(raw_line_items),
        "total_calculated_items": len(calculated_items),
        "api_usage": {
            "total_cost_usd": round(total_cost, 4),
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "cost_per_sheet": round(total_cost / max(len(all_extracted), 1), 4),
            "models_used": model_counts,
        },
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
        "raw_line_items": raw_line_items,               # Source-of-truth list
        "by_sheet": _group_by_sheet(raw_line_items + calculated_items),
        "by_category": _group_by_category(raw_line_items),
        "by_table": _group_by_table(calculated_items),  # which estimation table was used
        "sheet_log": [
            {
                "sheet": d.get("_source_sheet"),
                "page_id": d.get("_page_id"),
                "type": d.get("sheet_type"),
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
            }
            for d in all_extracted
        ],
    }

    # Scale calibration — per-sheet drawing scale + scale-independent raw geometry
    # so the Results "Scale & Verify" module can recompute measured quantities
    # exactly when a human corrects a scale (no vision re-run).
    scale_calibration = _build_scale_calibration(
        project_name, run_dir.name, all_extracted,
    )
    report["scale_calibration"] = scale_calibration

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
    report["_run_folder_name"] = run_dir.name
    return report


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
        from scale_utils import parse_scale
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


def _build_scale_calibration(project_name: str, run_folder: str,
                             all_extracted: list) -> Dict[str, Any]:
    """Per-sheet scale + scale-independent raw geometry for the Verify module.

    Only sheets that produced vector geometry (floor/site/roof plans) are
    scale-dependent and therefore recomputable. Each entry carries the detected
    scale, its confidence/source, the raw point measures, and the currently
    computed measured quantities, plus a link to the sheet image for tracing.
    """
    sheets: List[Dict[str, Any]] = []
    for d in all_extracted:
        geom = d.get("_geometry")
        if not geom:
            continue
        raw = geom.get("raw")
        scale_meta = geom.get("scale") or {}
        fpp = scale_meta.get("feet_per_point")
        fpi = round(fpp * 72.0, 4) if fpp else None
        confidence = geom.get("confidence") or scale_meta.get("confidence") or "none"
        # AUTO-VERIFIED: scale read cleanly from the sheet (ladder-snapped, high
        # confidence) — accepted automatically; the user only confirms if desired.
        auto_verified = bool(fpi and confidence == "high"
                             and not geom.get("needs_review", True))
        sheets.append({
            "sheet": d.get("_sheet_name") or d.get("_source_sheet") or "unknown",
            "page_id": d.get("_page_id"),
            "type": d.get("_sheet_type") or d.get("sheet_type") or "",
            "image": _image_rel_to_output(d.get("_source_sheet")),
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
            # Per-viewport breakdown for multi-scale sheets — each detail measured
            # with its own scale; the Verify tab can show one row per viewport.
            "viewports": geom.get("viewports") or [],
        })
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
        "description", "value", "unit",
        "location_on_sheet", "source_text"
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        if items:
            w.writerows(items)


def _write_takeoff_summary_csv(aggregated: list, path: Path):
    """StackCT-style consolidated takeoff summary."""
    fields = ["item", "quantity", "unit", "confidence", "needs_review",
              "source", "review_notes", "source_sheets", "line_count"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in aggregated:
            w.writerow({
                "item": row.get("item"),
                "quantity": row.get("quantity_fmt") or row.get("quantity"),
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
    lines.append(f"Input tokens:     {usage.get('total_tokens_in', 0):,}")
    lines.append(f"Output tokens:    {usage.get('total_tokens_out', 0):,}")
    lines.append(f"Cost per sheet:   ${usage.get('cost_per_sheet', 0):.4f} USD")
    lines.append("")

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
