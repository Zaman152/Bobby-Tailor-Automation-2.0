#!/usr/bin/env python3
"""Export a run's take-off to a client-ready Excel workbook (ZERO API).

Every row carries its PROVENANCE, because a take-off a client bids from must say
where each number came from:

  MEASURED       — geometry measured it off the drawing (the app earned it)
  HUMAN INPUT    — an estimator supplied it (room mix, scale, wall height)
  NEEDS REVIEW   — measured but flagged; a human must confirm before use
  NOT MEASURED   — the app has no measurement path for this item yet

An honest sheet a client can act on beats a confident one they cannot verify.

Usage:
    python3 scripts/export_takeoff_excel.py output/<run_dir> [--out FILE.xlsx]
                                            [--golden <takeoff.pdf>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _load(run_dir: Path) -> dict:
    f = run_dir / "takeoff.json"
    if not f.exists():
        raise SystemExit(f"no takeoff.json in {run_dir}")
    return json.loads(f.read_text())


def _provenance(row: dict) -> str:
    qty = row.get("quantity")
    if qty in (None, "") or float(qty or 0) <= 0:
        return "NOT MEASURED"
    if row.get("needs_review"):
        return "NEEDS REVIEW"
    src = str(row.get("source") or "").lower()
    if src in ("manifest", "human", "learned"):
        return "HUMAN INPUT"
    return "MEASURED"


def build(run_dir: Path, out: Path, golden_pdf: Path = None) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    data = _load(run_dir)
    summary = data.get("takeoff_summary") or []

    golden = {}
    if golden_pdf and golden_pdf.exists():
        from scripts.vision_only_benchmark import load_golden_from_takeoff_pdf
        for r in load_golden_from_takeoff_pdf(golden_pdf):
            golden[r["item_name"].strip().lower()] = (
                golden.get(r["item_name"].strip().lower(), 0.0) + float(r["quantity"])
            )

    wb = Workbook()
    ws = wb.active
    ws.title = "Take-Off"

    headers = ["Item", "Quantity", "Unit", "Provenance", "Basis / Formula",
               "Sheets", "Review Notes"]
    if golden:
        headers[4:4] = ["Reference Qty", "Variance %"]
    ws.append(headers)
    head_fill = PatternFill("solid", fgColor="1F3864")
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", vertical="center")

    colors = {
        "MEASURED": "C6EFCE",
        "HUMAN INPUT": "DDEBF7",
        "NEEDS REVIEW": "FFEB9C",
        "NOT MEASURED": "F2F2F2",
    }
    for row in sorted(summary, key=lambda r: -(float(r.get("quantity") or 0))):
        prov = _provenance(row)
        name = str(row.get("item", ""))
        qty = row.get("quantity")
        detail = row.get("detail") or []
        formula = ""
        for d in detail:
            if isinstance(d, dict) and d.get("formula"):
                formula = str(d["formula"])
                break
        sheets = ", ".join(
            Path(str(s)).stem for s in (row.get("source_sheets") or [])[:3]
        )
        notes = "; ".join(str(x) for x in (row.get("review_reasons") or []))[:300]
        line = [name, qty, row.get("unit", ""), prov, formula, sheets, notes]
        if golden:
            g = golden.get(name.strip().lower())
            var = ""
            if g and qty not in (None, ""):
                try:
                    var = round(abs(float(qty) - g) / g * 100, 1)
                except (TypeError, ValueError, ZeroDivisionError):
                    var = ""
            line[4:4] = [g if g else "", var]
        ws.append(line)
        fill = PatternFill("solid", fgColor=colors.get(prov, "FFFFFF"))
        ws.cell(row=ws.max_row, column=4).fill = fill

    widths = [34, 13, 7, 15, 46, 22, 60]
    if golden:
        widths[4:4] = [14, 11]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w
    ws.freeze_panes = "A2"

    # ── provenance legend / run facts ────────────────────────────────────────
    ws2 = wb.create_sheet("About")
    api = data.get("api_usage") or {}
    facts = [
        ("Project", data.get("project_name", "")),
        ("Generated", data.get("generated_at", "")),
        ("Sheets processed", data.get("sheets_processed", "")),
        ("Line items", len(summary)),
        ("API cost (USD)", api.get("total_cost_usd", "")),
        ("", ""),
        ("PROVENANCE", "MEANING"),
        ("MEASURED", "Geometry measured this off the drawing at the drawing's own printed scale."),
        ("HUMAN INPUT", "An estimator supplied this (room mix / scale / wall height). Not measured."),
        ("NEEDS REVIEW", "Measured but flagged — confirm before bidding."),
        ("NOT MEASURED", "No measurement path for this item yet. Do NOT read a blank as zero."),
    ]
    for k, v in facts:
        ws2.append([k, v])
    for c in ws2["A"]:
        c.font = Font(bold=True)
    ws2.column_dimensions["A"].width = 20
    ws2.column_dimensions["B"].width = 92

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--golden", default=None, help="take-off PDF for a reference column")
    a = ap.parse_args()
    rd = Path(a.run_dir)
    out = Path(a.out) if a.out else rd / "takeoff.xlsx"
    p = build(rd, out, Path(a.golden) if a.golden else None)
    print(f"wrote {p}")
