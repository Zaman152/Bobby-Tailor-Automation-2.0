"""
Generate takeoff report directly from Claude's extracted drawing data.
No estimation tables needed — Claude's vision output IS the takeoff.
"""
import json
import csv
import logging
from datetime import datetime
from pathlib import Path
from config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def generate_report(project_name: str, all_extracted: list) -> dict:
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = project_name.replace(" ", "_").replace("/", "-")

    # Flatten Claude's extraction into line items
    line_items = _flatten_to_line_items(all_extracted)

    report = {
        "project_name": project_name,
        "generated_at": datetime.now().isoformat(),
        "sheets_processed": len(all_extracted),
        "total_line_items": len(line_items),
        "line_items": line_items,
        "by_sheet": _group_by_sheet(line_items),
        "by_category": _group_by_category(line_items),
        "sheet_log": [
            {
                "sheet": d.get("_source_sheet"),
                "type": d.get("sheet_type"),
                "title": d.get("sheet_title"),
                "scale": d.get("scale"),
                "measurements": len(d.get("measurements", [])),
                "components": len(d.get("components", [])),
                "rooms": len(d.get("rooms", [])),
                "materials": len(d.get("materials", [])),
                "confidence": d.get("confidence"),
            }
            for d in all_extracted
        ],
    }

    # Save files
    json_path = output_dir / f"{safe}_{ts}_takeoff.json"
    csv_path  = output_dir / f"{safe}_{ts}_takeoff.csv"
    txt_path  = output_dir / f"{safe}_{ts}_summary.txt"

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    _write_csv(line_items, csv_path)
    _write_summary(report, txt_path)

    logger.info(f"Saved: {json_path.name}, {csv_path.name}, {txt_path.name}")
    report["_files"] = {
        "json": str(json_path),
        "csv":  str(csv_path),
        "txt":  str(txt_path),
    }
    return report


def _flatten_to_line_items(all_extracted: list) -> list:
    items = []
    for d in all_extracted:
        sheet = d.get("_source_sheet", "unknown")
        page_id = d.get("_page_id", "")

        for m in d.get("measurements", []):
            items.append({
                "category": "measurement",
                "sheet": sheet,
                "page_id": page_id,
                "description": m.get("description", ""),
                "quantity": m.get("value", ""),
                "unit": m.get("unit", ""),
                "location": m.get("location", ""),
                "notes": m.get("raw_text", ""),
            })

        for c in d.get("components", []):
            items.append({
                "category": "component",
                "sheet": sheet,
                "page_id": page_id,
                "description": c.get("name", ""),
                "quantity": c.get("quantity", ""),
                "unit": c.get("unit", "ea"),
                "location": c.get("location", ""),
                "notes": c.get("specification", ""),
            })

        for r in d.get("rooms", []):
            items.append({
                "category": "room",
                "sheet": sheet,
                "page_id": page_id,
                "description": r.get("name", ""),
                "quantity": r.get("area", ""),
                "unit": "sq_ft",
                "location": r.get("name", ""),
                "notes": r.get("notes", ""),
            })

        for mat in d.get("materials", []):
            items.append({
                "category": "material",
                "sheet": sheet,
                "page_id": page_id,
                "description": mat.get("type", ""),
                "quantity": mat.get("quantity", ""),
                "unit": "",
                "location": "",
                "notes": mat.get("specification", ""),
            })

    return items


def _group_by_sheet(items: list) -> dict:
    out = {}
    for item in items:
        sheet = item["sheet"]
        out.setdefault(sheet, []).append(item)
    return out


def _group_by_category(items: list) -> dict:
    out = {}
    for item in items:
        cat = item["category"]
        out.setdefault(cat, []).append(item)
    # Summary counts
    return {cat: {"count": len(v), "items": v} for cat, v in out.items()}


def _write_csv(items: list, path: Path):
    if not items:
        return
    fields = ["category", "sheet", "page_id", "description", "quantity", "unit", "location", "notes"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(items)


def _write_summary(report: dict, path: Path):
    lines = [
        "TAKEOFF SUMMARY",
        "=" * 60,
        f"Project:  {report['project_name']}",
        f"Date:     {report['generated_at']}",
        f"Sheets:   {report['sheets_processed']}",
        f"Items:    {report['total_line_items']}",
        "",
    ]

    lines += ["BREAKDOWN BY CATEGORY", "-" * 40]
    for cat, data in report["by_category"].items():
        lines.append(f"  {cat.upper():15s}  {data['count']:4d} items")

    lines += ["", "BREAKDOWN BY SHEET", "-" * 40]
    for sheet, items in report["by_sheet"].items():
        lines.append(f"\n  [{sheet}]  ({len(items)} items)")
        for item in items:
            qty = f"{item['quantity']}" if item["quantity"] else "—"
            unit = item["unit"] or ""
            lines.append(f"    {qty:>10} {unit:<8}  {item['description']}")
            if item["location"]:
                lines.append(f"              @ {item['location']}")

    with open(path, "w") as f:
        f.write("\n".join(lines))
