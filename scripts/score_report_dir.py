#!/usr/bin/env python3
"""Score an app-generated report directory against a golden fixture.

Reuses the vision_only_benchmark scoring so a report produced via the web app
(output/<Project>_<timestamp>/takeoff_summary.csv) is graded identically to the
CLI benchmark.

Usage:
  python3 scripts/score_report_dir.py --golden tests/fixtures/crow_cass/crow_cass_golden.csv \
      [--dir output/Crow_Cass_..._<ts>]   # omit --dir to auto-pick newest matching
  python3 scripts/score_report_dir.py --golden ... --match Crow   # newest output dir containing 'Crow'
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.vision_only_benchmark import _load_golden, score, report_text  # noqa: E402


def _num(s: str):
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "—", "-", "n/a", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _load_summary(csv_path: Path) -> list:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            q = _num(r.get("quantity"))
            rows.append({
                "item": r.get("item", ""),
                "quantity": q if q is not None else "",
                "unit": r.get("unit", ""),
                "confidence": r.get("confidence", ""),
                "needs_review": r.get("needs_review", ""),
                "source": r.get("source", ""),
            })
    return rows


def _pick_dir(match: str) -> Path | None:
    cands = sorted(
        (p for p in (ROOT / "output").glob(f"*{match}*") if (p / "takeoff_summary.csv").exists()),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    return cands[0] if cands else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--dir", help="explicit report dir (contains takeoff_summary.csv)")
    ap.add_argument("--match", default="Crow", help="substring to auto-pick newest output dir")
    ap.add_argument("--name", default="Crow Cass (app run)")
    args = ap.parse_args()

    report_dir = Path(args.dir) if args.dir else _pick_dir(args.match)
    if not report_dir or not (report_dir / "takeoff_summary.csv").exists():
        print(f"No report dir found (match={args.match!r}).")
        return 2
    print(f"Scoring report dir: {report_dir}")

    golden_rows = _load_golden(Path(args.golden) if Path(args.golden).is_absolute()
                               else ROOT / args.golden)
    summary = _load_summary(report_dir / "takeoff_summary.csv")
    sc = score(golden_rows, summary)
    print("\n" + report_text(args.name, sc, {"mode": "app-run", "sheets": "?"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
