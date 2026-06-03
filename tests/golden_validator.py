"""
GoldenValidator — compare AI takeoff summary against a golden reference CSV.

Fully generic: accepts any golden CSV path; no hardcoded item names or project-specific logic.
Reusable for Crow Cass, Bob's Discount, or any future golden reference file.

Golden CSV format (required columns):
    item_name, quantity, unit, tolerance_pct, match_mode

match_mode values:
    exact_or_within_1  — EA/count items: must equal exactly or differ by at most 1
    pct                — SF/LF/CY items: error must be ≤ tolerance_pct %
"""
import csv
import difflib
from pathlib import Path
from typing import Dict, List, Optional


class GoldenValidator:
    """Compare AI takeoff summary against a golden reference CSV.

    Usage::

        validator = GoldenValidator("tests/fixtures/crow_cass/crow_cass_golden.csv")
        report = validator.validate(takeoff_summary, fixture_name="Crow Cass")
        assert report["pass"], report["items"]

    Args:
        golden_csv_path: Path to golden CSV with columns:
            item_name, quantity, unit, tolerance_pct, match_mode
        threshold: Fraction of items that must pass to report ``pass=True`` (default 0.97).
        fuzzy_cutoff: Minimum difflib similarity ratio for name matching (default 0.70).
    """

    def __init__(
        self,
        golden_csv_path: str,
        threshold: float = 0.97,
        fuzzy_cutoff: float = 0.70,
    ) -> None:
        self.golden_csv_path = str(golden_csv_path)
        self.threshold = threshold
        self.fuzzy_cutoff = fuzzy_cutoff
        self.golden: List[Dict] = self._load(golden_csv_path)

    # ── Load ─────────────────────────────────────────────────────────────────

    def _load(self, path: str) -> List[Dict]:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    # ── Fuzzy name matching ──────────────────────────────────────────────────

    def _normalise(self, name: str) -> str:
        """Lowercase + collapse separator characters to a single space."""
        import re
        return re.sub(r"[-_/]+", " ", name.lower()).strip()

    def _fuzzy_match(self, golden_name: str, ai_index: Dict[str, Dict]) -> Optional[Dict]:
        """Return the best fuzzy match from ai_index keys, or None if below cutoff.

        Both sides are normalised before matching so "CMU-Wall" finds "cmu wall".
        """
        norm_golden = self._normalise(golden_name)
        # Build a normalised → original key map
        norm_map: Dict[str, str] = {self._normalise(k): k for k in ai_index}

        # Exact normalised match first
        if norm_golden in norm_map:
            return ai_index[norm_map[norm_golden]]

        matches = difflib.get_close_matches(
            norm_golden, norm_map.keys(), n=1, cutoff=self.fuzzy_cutoff
        )
        if matches:
            return ai_index[norm_map[matches[0]]]
        return None

    # ── Validate ─────────────────────────────────────────────────────────────

    def validate(
        self,
        takeoff_summary: List[Dict],
        fixture_name: Optional[str] = None,
    ) -> Dict:
        """Compare AI takeoff_summary rows against golden reference.

        Args:
            takeoff_summary: List of dicts from ``aggregate_takeoff()``.
                Each dict must contain at least ``item`` (str) and ``quantity`` (numeric).
            fixture_name: Optional label included in result for diagnostics.

        Returns:
            {
                "pass":    bool — True when score >= threshold,
                "score":   float — fraction of golden items that passed,
                "items":   list  — per-item result dicts,
                "missing": list  — golden items not found in AI output,
                "extra":   list  — AI items not present in golden,
                "fixture": Optional[str],
            }
        """
        # Build lookup by lowercased item name
        ai_index: Dict[str, Dict] = {
            item["item"].lower(): item for item in takeoff_summary
        }

        golden_names_lower = {g["item_name"].lower() for g in self.golden}

        results: List[Dict] = []

        for g in self.golden:
            g_name = g["item_name"]
            g_qty = float(g["quantity"])
            g_unit = g["unit"].upper()
            tolerance = float(g["tolerance_pct"]) / 100
            mode = g["match_mode"]

            # Exact lookup first; fall back to fuzzy
            ai_item = ai_index.get(g_name.lower()) or self._fuzzy_match(g_name, ai_index)

            if ai_item is None:
                results.append({
                    "item": g_name,
                    "status": "MISSING",
                    "golden": g_qty,
                    "golden_unit": g_unit,
                    "ai": None,
                    "ai_unit": None,
                    "error_pct": None,
                })
                continue

            try:
                ai_qty = float(ai_item["quantity"])
            except (TypeError, ValueError):
                results.append({
                    "item": g_name,
                    "status": "MISSING",
                    "golden": g_qty,
                    "golden_unit": g_unit,
                    "ai": None,
                    "ai_unit": None,
                    "error_pct": None,
                })
                continue

            if mode == "exact_or_within_1":
                passed = (ai_qty == g_qty) or (abs(ai_qty - g_qty) <= 1)
            else:  # pct
                if g_qty == 0:
                    passed = ai_qty == 0
                else:
                    passed = abs(ai_qty - g_qty) / g_qty <= tolerance

            error_pct = (
                round(abs(ai_qty - g_qty) / g_qty * 100, 1) if g_qty else None
            )

            results.append({
                "item": g_name,
                "status": "PASS" if passed else "FAIL",
                "golden": g_qty,
                "golden_unit": g_unit,
                "ai": ai_qty,
                "ai_unit": (ai_item.get("unit") or "").upper(),
                "error_pct": error_pct,
                "match_mode": mode,
                "tolerance_pct": float(g["tolerance_pct"]),
            })

        passing = sum(1 for r in results if r["status"] == "PASS")
        score = passing / len(results) if results else 0.0

        # Extra items: AI produced items not in golden
        extra = [
            item for item in takeoff_summary
            if item["item"].lower() not in golden_names_lower
            and not self._fuzzy_match(item["item"], {g_n: {} for g_n in golden_names_lower})
        ]

        return {
            "pass": score >= self.threshold,
            "score": round(score, 4),
            "items": results,
            "missing": [r for r in results if r["status"] == "MISSING"],
            "extra": extra,
            "fixture": fixture_name,
            "threshold": self.threshold,
            "passing": passing,
            "total": len(results),
        }

    # ── Diagnostics ──────────────────────────────────────────────────────────

    def format_report(self, report: Dict) -> str:
        """Human-readable report string for pytest failure messages."""
        lines = []
        fixture = report.get("fixture") or Path(self.golden_csv_path).stem
        lines.append(
            f"Golden validation: {fixture}  "
            f"score={report['score']:.1%}  "
            f"({report['passing']}/{report['total']} pass)"
        )
        for item in report["items"]:
            status = item["status"]
            ai_str = f"{item['ai']:,.2f}" if item["ai"] is not None else "—"
            err_str = f"  err={item['error_pct']}%" if item["error_pct"] is not None else ""
            lines.append(
                f"  {status:6}  {item['item']:<38} "
                f"golden={item['golden']:,.2f}  ai={ai_str}{err_str}"
            )
        if report["missing"]:
            lines.append(f"  Missing: {[m['item'] for m in report['missing']]}")
        if report["extra"]:
            lines.append(f"  Extra (not in golden): {[e['item'] for e in report['extra']]}")
        return "\n".join(lines)
