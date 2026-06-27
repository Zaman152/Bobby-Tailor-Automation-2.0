#!/usr/bin/env python3
"""
Run generalization + golden regression; exit 0 only when all present fixtures >= threshold.

Usage:
  python3 scripts/golden_convergence.py
  python3 scripts/golden_convergence.py --min-score 0.97 --fixture crow
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT))


def _run_pytest(args: list[str]) -> int:
    env = os.environ.copy()
    env.setdefault("TAKEOFF_ACCURACY_MODE", "high")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=str(ROOT),
        env=env,
        capture_output=False,
    )
    return proc.returncode


def _score_fixture(name: str, golden_csv: Path, plans_pdf: Path) -> dict:
    if not plans_pdf.exists():
        return {"name": name, "status": "skipped", "score": None, "reason": "PDF absent"}

    from pdf_analyzer import run_pdf_analysis
    from tests.golden_validator import GoldenValidator

    try:
        result = run_pdf_analysis(str(plans_pdf), project_name=f"Convergence {name}")
        summary = result.get("takeoff_summary", [])
        report = GoldenValidator(str(golden_csv)).validate(summary, fixture_name=name)
        return {
            "name": name,
            "status": "pass" if report["pass"] else "fail",
            "score": report["score"],
            "report": report,
        }
    except Exception as exc:
        return {"name": name, "status": "error", "score": None, "reason": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden accuracy convergence gate")
    parser.add_argument("--min-score", type=float, default=0.97)
    parser.add_argument("--fixture", choices=("all", "crow", "bob"), default="all")
    parser.add_argument("--skip-generalization", action="store_true")
    args = parser.parse_args()

    if not args.skip_generalization:
        print("=== Generalization tests ===")
        rc = _run_pytest(["tests/test_takeoff_generalization.py", "-q"])
        if rc != 0:
            print("Generalization tests failed.")
            return rc

    fixtures = []
    if args.fixture in ("all", "crow"):
        fixtures.append((
            "Crow Cass",
            FIXTURES / "crow_cass" / "crow_cass_golden.csv",
            FIXTURES / "crow_cass" / "crow_cass_plans.pdf",
        ))
    if args.fixture in ("all", "bob"):
        fixtures.append((
            "Bob's Discount",
            FIXTURES / "bobs_discount" / "bobs_discount_golden.csv",
            FIXTURES / "bobs_discount" / "bobs_discount_plans.pdf",
        ))

    print(f"\n=== Golden convergence (min {args.min_score:.0%}) ===\n")
    ok = True
    for name, golden_csv, plans_pdf in fixtures:
        companion = plans_pdf.parent / plans_pdf.name.replace("_plans", "_takeoff")
        if companion.with_suffix(".pdf").exists():
            print(f"  {name}: companion PDF {companion.with_suffix('.pdf').name}")

        outcome = _score_fixture(name, golden_csv, plans_pdf)
        if outcome["status"] == "skipped":
            print(f"  SKIP {name}: {outcome['reason']}")
            continue
        if outcome["status"] == "error":
            print(f"  ERROR {name}: {outcome['reason']}")
            ok = False
            continue
        score = outcome["score"]
        print(f"  {name}: {score:.1%} ({'PASS' if outcome['status'] == 'pass' else 'FAIL'})")
        if score < args.min_score:
            ok = False
            report = outcome["report"]
            for item in report.get("items", []):
                if item.get("status") != "PASS":
                    print(f"    - {item.get('item')}: {item.get('status')}")

    if ok:
        print("\nConvergence gate: PASSED")
        return 0
    print("\nConvergence gate: FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
