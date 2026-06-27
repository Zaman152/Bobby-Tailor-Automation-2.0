#!/usr/bin/env python3
"""Run a golden fixture end-to-end and dump extracted vs golden for diagnosis.

Usage:
  python3 scripts/diagnose_fixture.py crow
  python3 scripts/diagnose_fixture.py bob
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES = {
    "crow": (
        ROOT / "tests/fixtures/crow_cass/crow_cass_plans.pdf",
        ROOT / "tests/fixtures/crow_cass/crow_cass_golden.csv",
        "Crow Cass",
    ),
    "bob": (
        ROOT / "tests/fixtures/bobs_discount/bobs_discount_plans.pdf",
        ROOT / "tests/fixtures/bobs_discount/bobs_discount_golden.csv",
        "Bob's Discount",
    ),
    # Large real projects — plans + companion take-off live in uploads/.
    "chelsea": (
        ROOT / "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf",
        ROOT / "tests/fixtures/chelsea/chelsea_golden.csv",
        "Chelsea Bear Creek",
    ),
    "moxy": (
        ROOT / "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
        ROOT / "tests/fixtures/moxy/moxy_golden.csv",
        "Moxy Knoxville",
    ),
}


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "crow"
    pdf, golden, name = FIXTURES[key]

    from pdf_analyzer import run_pdf_analysis
    from tests.golden_validator import GoldenValidator

    print(f"=== Running {name} ===", flush=True)
    result = run_pdf_analysis(str(pdf), project_name=f"Diagnose {name}")
    summary = result.get("takeoff_summary", [])

    print("\n=== EXTRACTED takeoff_summary ===", flush=True)
    for it in summary:
        nm = it.get('item') or it.get('item_name') or it.get('name')
        print(f"  {str(nm):40} {str(it.get('quantity')):>14} {str(it.get('unit'))}", flush=True)

    print("\n=== PER-SHEET extracted (schedules + components) ===", flush=True)
    by_sheet = result.get("by_sheet") or {}
    if isinstance(by_sheet, dict):
        items = by_sheet.items()
    else:
        items = enumerate(by_sheet)
    for sheet_key, data in items:
        if not isinstance(data, dict):
            continue
        scheds = data.get("schedules") or []
        comps = data.get("components") or []
        if scheds or comps:
            print(f"  -- {sheet_key} ({data.get('_sheet_type','?')}) "
                  f"schedules={len(scheds)} components={len(comps)}", flush=True)
            for s in scheds:
                rows = s.get("rows") or []
                print(f"       schedule {s.get('name','?')!r} "
                      f"purpose={s.get('table_purpose','?')} rows={len(rows)}", flush=True)

    print("\n=== GOLDEN VALIDATION ===", flush=True)
    validator = GoldenValidator(str(golden))
    report = validator.validate(summary, fixture_name=name)
    print(validator.format_report(report), flush=True)

    out = ROOT / f"scripts/_diag_{key}.json"
    out.write_text(json.dumps({"summary": summary, "report": report}, indent=2, default=str))
    print(f"\nWrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
