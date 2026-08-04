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

# The classification is a RECORD, not a presentation choice, so it lives in the
# package (INV-08 §5). The local copy this import replaces inferred provenance
# from the value — `float(qty or 0) <= 0 -> NOT MEASURED` — which made a
# genuinely measured zero indistinguishable from a measurement never attempted,
# could not label an item that produced no row at all (and absence is precisely
# the defect), and was visible only to spreadsheet users while the JSON, the CSV,
# the web view and the API all shipped the bare number. This script keeps
# ownership of layout, colours and the About sheet; that is genuinely
# presentation.
from bobbytailor.pipeline.provenance import provenance_of_row  # noqa: E402


def _load(run_dir: Path) -> dict:
    f = run_dir / "takeoff.json"
    if not f.exists():
        raise SystemExit(f"no takeoff.json in {run_dir}")
    return json.loads(f.read_text())


def _row_provenance(row: dict) -> str:
    """The provenance the RUN recorded, falling back to the one place that
    decides the vocabulary for a pre-23 row that carries none."""
    return str(row.get("provenance") or provenance_of_row(row))


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
        prov = _row_provenance(row)
        name = str(row.get("item", ""))
        # A never-measured quantity keeps a BLANK cell. openpyxl writes None as
        # an empty cell, and an empty cell is the only honest rendering: a zero
        # here would be a number the run never measured.
        qty = row.get("quantity")
        if qty == "":
            qty = None
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

    # ── coverage: one row per PAGE OF THE SOURCE PDF ─────────────────────────
    # The take-off sheet above shows the pages that produced numbers. This one
    # shows the whole source PDF, so a page that produced nothing is visible as
    # a page that produced nothing rather than as no row at all.
    ledger = data.get("coverage_ledger") or []
    coverage = data.get("coverage") or {}
    if ledger:
        ws3 = wb.create_sheet("Coverage")
        ws3.append([
            "Every page of the source PDF is listed. A blank quantity on the "
            "Take-Off sheet is NOT a zero — see the About sheet for what each "
            "provenance means."
        ])
        ws3["A1"].font = Font(bold=True, color="9C0006")
        # "Excluded (off-scale)" is kept SEPARATE from "dropped": excluding a
        # viewport whose own printed scale disagrees with the page is CORRECT
        # behaviour — measuring it there would be ~60x wrong — and folding it in
        # would make a well-measured sheet read as a partial one.
        cov_headers = ["Page", "Sheet", "Type", "Disposition", "Reason",
                       "Plan titles", "Printed scales", "Drawings measured",
                       "Drawings dropped", "Excluded (off-scale)", "Items"]
        ws3.append(cov_headers)
        for c in ws3[2]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = head_fill
            c.alignment = Alignment(horizontal="center", vertical="center")
        for page in ledger:
            signal = page.get("measurable_signal") or {}
            drawings = page.get("drawings") or []
            measured_n = sum(
                1 for d in drawings if d.get("disposition") == "measured"
            )
            excluded_n = sum(
                1 for d in drawings
                if d.get("disposition") == "excluded_off_scale"
            )
            ws3.append([
                (page.get("page_index") or 0) + 1,
                page.get("sheet_name") or "",
                page.get("sheet_type") or "",
                str(page.get("disposition") or "").replace("_", " "),
                str(page.get("reason") or "")[:300],
                signal.get("plan_titles", ""),
                signal.get("printed_scales", ""),
                measured_n,
                len(drawings) - measured_n - excluded_n,
                excluded_n,
                page.get("items_emitted", 0),
            ])
            if page.get("is_silent_loss"):
                # Discarded although it carries measurable drawings — the one
                # row on this sheet a client must not skim past.
                flag = PatternFill("solid", fgColor="FFEB9C")
                for col in range(1, len(cov_headers) + 1):
                    ws3.cell(row=ws3.max_row, column=col).fill = flag
        for i, w in enumerate([7, 22, 16, 20, 60, 12, 14, 18, 17, 20, 8], start=1):
            ws3.column_dimensions[ws3.cell(row=2, column=i).column_letter].width = w
        ws3.freeze_panes = "A3"

    # ── provenance legend / run facts ────────────────────────────────────────
    ws2 = wb.create_sheet("About")
    api = data.get("api_usage") or {}
    facts = [
        ("Project", data.get("project_name", "")),
        ("Generated", data.get("generated_at", "")),
        ("Sheets processed", data.get("sheets_processed", "")),
        ("Line items", len(summary)),
        ("API cost (USD)", api.get("total_cost_usd", "")),
    ]
    if coverage:
        # sheets_processed counts sheets the run ANALYZED; these three say what
        # the source PDF actually held, which is the difference a client needs.
        facts += [
            ("Pages in source PDF", coverage.get("pages_in_source", "")),
            ("Pages measured", coverage.get("sheets_measured", "")),
            ("Pages skipped", (coverage.get("sheets_skipped") or 0)
                              + (coverage.get("sheets_not_applicable") or 0)),
        ]
        # C2: a workbook a client bids from must say when the run stopped early.
        if coverage.get("sheets_budget_truncated"):
            facts.append((
                "RUN INCOMPLETE",
                "%s page(s) were cut short when the API budget was exhausted — "
                "their remaining passes never ran. Every quantity here is a "
                "LOWER BOUND and every blank on those pages is unknown, not "
                "zero. Raise the budget cap and re-run."
                % coverage.get("sheets_budget_truncated"),
            ))
    facts += [
        ("", ""),
        ("PROVENANCE", "MEANING"),
        ("MEASURED", "Geometry measured this off the drawing at the drawing's own printed scale. A schedule the app read off the plans is a machine measurement and belongs here, not under HUMAN INPUT."),
        ("HUMAN INPUT", "A human supplied this IN A HUMAN INPUT FILE (an estimator's own companion take-off, a room mix, a scale, a wall height). Never used for anything the app read off the plans."),
        ("NEEDS REVIEW", "Measured but flagged — confirm before bidding."),
        ("NOT MEASURED", "No measurement path for this item yet. Do NOT read a blank as zero."),
        ("STANDARD ITEM", "An estimating convention this app injects (e.g. Mobilization). Nobody measured it and nobody supplied it — confirm it belongs on this bid."),
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
