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
                    all_estimates: Optional[list] = None) -> dict:
    """
    Build the final takeoff report.

    Args:
        project_name: Display name of the StackCT project
        all_extracted: list of Claude's raw extractions, one per drawing page
        all_estimates: list of items returned by calculator.apply_estimation_tables()
                       — already has calculated quantities, waste factors, source tracing
    """
    all_estimates = all_estimates or []
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

    # All files for this run live inside the run's folder with clean names
    json_path = run_dir / "takeoff.json"
    csv_raw   = run_dir / "raw_items.csv"
    csv_calc  = run_dir / "calculations.csv"      # ← THE CALCULATIONS FILE
    txt_path  = run_dir / "summary.txt"

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

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
        "summary_txt":    str(txt_path),
    }
    report["_run_folder_name"] = run_dir.name
    return report


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
            "estimation_table": e.get("table_used", "none"),
            "source_sheet": e.get("source_sheet", ""),
            "source_location": e.get("source_location", ""),
            "source_text": e.get("source_raw", ""),
            "specification": e.get("specification", ""),
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


def _write_calculated_csv(items: list, path: Path):
    """Calculated takeoff CSV — quantities with estimation tables applied + traceability."""
    fields = [
        "item_type", "description",
        "raw_value", "raw_unit",
        "calculated_quantity", "calculated_unit",
        "waste_factor", "formula_applied", "estimation_table",
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
        "SHEET-BY-SHEET LOG (source traceability)",
        "─" * 70,
    ]

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
