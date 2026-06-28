#!/usr/bin/env python3
"""
Vision-only accuracy benchmark — PRODUCTION-REALISTIC.

Runs a plans PDF through the take-off pipeline WITHOUT any companion take-off
document (the real production scenario: only plans are available) and scores the
result against a golden reference CSV built from the human take-off.

The plans PDF is copied into an isolated temp directory so that
`find_companion_takeoff_pdf` cannot discover a sibling take-off — guaranteeing a
true vision-only run.

In addition to the overall pass score it reports PER-CATEGORY accuracy
(EA counts vs measured SF/LF/CY) and separates NAME accuracy (did we find/label
the item at all?) from QUANTITY accuracy (is the number right once found?) so a
correct value with the wrong label is not scored as a total miss.

Usage:
  # Full vision run (spends API credits):
  python3 scripts/vision_only_benchmark.py \
      --name "Crow Cass" \
      --plans tests/fixtures/crow_cass/crow_cass_plans.pdf \
      --golden tests/fixtures/crow_cass/crow_cass_golden.csv \
      [--manifest path/to/manifest.json]

  # Re-score a previously saved vision_summary.json (FREE, no API):
  python3 scripts/vision_only_benchmark.py \
      --name "Crow Cass" \
      --golden tests/fixtures/crow_cass/crow_cass_golden.csv \
      --rescore reports/vision_only/Crow_Cass/vision_summary.json
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_STOP = {"the", "a", "an", "of", "and", "to", "for", "in", "on", "alt", "h"}


def _tokens(name: str) -> set:
    toks = re.split(r"[-_/\s'\"]+", (name or "").lower())
    return {t for t in toks if t and t not in _STOP and not t.isdigit()}


def _load_golden(path: Path) -> list:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _category(g_unit: str, match_mode: str) -> str:
    if match_mode == "exact_or_within_1" or g_unit.upper() in ("EA", "EACH"):
        return "count"
    return "measured"  # SF / LF / CY


def _best_name_match(golden_name: str, ai_rows: list) -> Optional[dict]:
    """Find the AI row whose name plausibly refers to the same item, IGNORING qty.

    Strategy (loosest sensible): exact normalised -> token subset/overlap ->
    difflib ratio. Returns the matched row or None.
    """
    g_tokens = _tokens(golden_name)
    g_norm = " ".join(sorted(g_tokens))

    best = None
    best_score = 0.0
    for r in ai_rows:
        a_name = r.get("item", "")
        a_tokens = _tokens(a_name)
        if not a_tokens or not g_tokens:
            continue
        # Strong: one token-set is a subset of / equal to the other.
        if g_tokens <= a_tokens or a_tokens <= g_tokens:
            return r
        overlap = len(g_tokens & a_tokens) / max(1, len(g_tokens | a_tokens))
        ratio = difflib.SequenceMatcher(None, g_norm, " ".join(sorted(a_tokens))).ratio()
        score = max(overlap, ratio)
        if score > best_score:
            best_score = score
            best = r
    return best if best_score >= 0.6 else None


def _qty(row: dict):
    try:
        return float(row.get("quantity"))
    except (TypeError, ValueError):
        return None


def score(golden_rows: list, summary: list) -> dict:
    """Rich diagnostic scoring independent of GoldenValidator pass/fail."""
    items = []
    for g in golden_rows:
        g_name = g["item_name"]
        g_qty = float(g["quantity"])
        g_unit = g["unit"].upper()
        mode = g["match_mode"]
        tol = float(g["tolerance_pct"]) / 100
        cat = _category(g_unit, mode)

        ai = _best_name_match(g_name, summary)
        if ai is None:
            items.append({
                "item": g_name, "category": cat, "golden": g_qty, "unit": g_unit,
                "ai": None, "ai_name": None, "found": False,
                "qty_ok": False, "error_pct": None, "status": "MISSING",
            })
            continue
        ai_qty = _qty(ai)
        if ai_qty is None:
            qty_ok = False
            err = None
        elif mode == "exact_or_within_1":
            # A zero / not-found quantity is never a quantity pass, even for
            # golden==1 items (otherwise an injected needs_review placeholder
            # would be scored as correct, inflating accuracy dishonestly).
            qty_ok = ai_qty > 0 and ((ai_qty == g_qty) or (abs(ai_qty - g_qty) <= 1))
            err = round(abs(ai_qty - g_qty) / g_qty * 100, 1) if g_qty else None
        else:
            qty_ok = abs(ai_qty - g_qty) / g_qty <= tol if g_qty else (ai_qty == 0)
            err = round(abs(ai_qty - g_qty) / g_qty * 100, 1) if g_qty else None
        items.append({
            "item": g_name, "category": cat, "golden": g_qty, "unit": g_unit,
            "ai": ai_qty, "ai_name": ai.get("item"), "found": True,
            "qty_ok": qty_ok, "error_pct": err,
            "status": "PASS" if qty_ok else "FAIL_QTY",
        })

    def _rate(subset, key):
        subset = list(subset)
        return (sum(1 for x in subset if x[key]) / len(subset)) if subset else None

    counts = [i for i in items if i["category"] == "count"]
    measured = [i for i in items if i["category"] == "measured"]
    found = [i for i in items if i["found"]]

    golden_names = {g["item_name"].lower() for g in golden_rows}
    extra = []
    for r in summary:
        if r.get("item", "").lower() in golden_names:
            continue
        if _best_name_match(r.get("item", ""), [{"item": g} for g in golden_names]):
            continue
        extra.append(r)

    return {
        "items": items,
        "overall_qty": _rate(items, "qty_ok"),
        "name_found_rate": _rate(items, "found"),
        "qty_acc_when_found": _rate(found, "qty_ok"),
        "count_qty": _rate(counts, "qty_ok"),
        "count_found": _rate(counts, "found"),
        "measured_qty": _rate(measured, "qty_ok"),
        "measured_found": _rate(measured, "found"),
        "n_total": len(items),
        "n_count": len(counts),
        "n_measured": len(measured),
        "extra": extra,
    }


def _pct(x) -> str:
    return f"{x:.0%}" if isinstance(x, (int, float)) else "n/a"


def report_text(name: str, sc: dict, meta: dict) -> str:
    L = []
    L.append("=" * 84)
    L.append(f"VISION-ONLY BENCHMARK — {name}")
    L.append("=" * 84)
    L.append(
        f"Overall quantity accuracy: {_pct(sc['overall_qty'])}   "
        f"Name/found rate: {_pct(sc['name_found_rate'])}   "
        f"Qty acc when found: {_pct(sc['qty_acc_when_found'])}"
    )
    L.append(
        f"  Counts (EA)   n={sc['n_count']:>2}  found={_pct(sc['count_found'])}  qty_ok={_pct(sc['count_qty'])}"
    )
    L.append(
        f"  Measured(SF/LF) n={sc['n_measured']:>2}  found={_pct(sc['measured_found'])}  qty_ok={_pct(sc['measured_qty'])}"
    )
    if meta:
        L.append(
            f"  [{meta.get('mode','')}] runtime={meta.get('elapsed','?')}  "
            f"cost=${meta.get('cost',0):.4f}  sheets={meta.get('sheets','?')}"
        )
    L.append("")
    L.append(f"{'STATUS':10}{'ITEM':<30}{'GOLDEN':>14}{'AI':>14}{'ERR%':>8}  CAT")
    L.append("-" * 84)
    for it in sc["items"]:
        ai = it["ai"]
        ai_str = f"{ai:,.2f}" if isinstance(ai, (int, float)) else "—"
        err = f"{it['error_pct']}" if it["error_pct"] is not None else "—"
        label = it["item"]
        if it["ai_name"] and it["ai_name"].lower() != it["item"].lower():
            label = f"{it['item']}≈{it['ai_name']}"
        L.append(
            f"{it['status']:10}{label:<30}{it['golden']:>14,.2f}{ai_str:>14}{err:>8}  {it['category']}"
        )
    if sc["extra"]:
        L.append("")
        L.append("EXTRA items AI produced not in golden:")
        for e in sc["extra"]:
            L.append(f"  + {e.get('item','?'):<30} {e.get('quantity','?')} {e.get('unit','')}")
    return "\n".join(L)


def run_vision(name: str, plans: Path, manifest: Optional[Path]) -> tuple:
    from companion_takeoff import find_companion_takeoff_pdf
    from pdf_analyzer import run_pdf_analysis

    with tempfile.TemporaryDirectory(prefix="vision_only_") as tmp:
        isolated = Path(tmp) / plans.name
        shutil.copy2(plans, isolated)
        companion = find_companion_takeoff_pdf(str(isolated))
        assert companion is None, f"Expected NO companion take-off, found: {companion}"
        print(f"[{name}] vision-only confirmed (no companion take-off discoverable)")

        kwargs = {}
        if manifest:
            kwargs["manifest_path"] = str(manifest)
        t0 = time.time()
        result = run_pdf_analysis(str(isolated), project_name=f"VisionOnly {name}", **kwargs)
        elapsed = time.time() - t0

    summary = result.get("takeoff_summary", []) or []
    meta = {
        "mode": "manifest" if manifest else "vision-only",
        "elapsed": f"{elapsed:.0f}s",
        "cost": (result.get("api_usage") or {}).get("total_cost_usd", 0),
        "sheets": result.get("sheets_processed", "?"),
    }
    return summary, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--golden", required=True)
    ap.add_argument("--plans", help="plans PDF (omit when using --rescore)")
    ap.add_argument("--manifest", help="optional object manifest (JSON/CSV)")
    ap.add_argument("--rescore", help="path to a saved vision_summary.json to re-score (no API)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true", help="suppress pipeline progress logs")
    args = ap.parse_args()

    # Surface the pipeline's per-sheet INFO progress so a long run is visibly
    # working (otherwise large PDFs look hung — there's no output for minutes).
    if not args.quiet:
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            stream=sys.stdout,
        )

    def _abs(p):
        return (ROOT / p).resolve() if p and not Path(p).is_absolute() else (Path(p) if p else None)

    golden = _abs(args.golden)
    if not golden or not golden.exists():
        print(f"Golden CSV not found: {golden}")
        return 2
    golden_rows = _load_golden(golden)

    safe = args.name.replace(" ", "_").replace("/", "-")
    out_dir = Path(args.out) if args.out else (ROOT / "reports" / "vision_only" / safe)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {}
    if args.rescore:
        summary = json.loads(Path(args.rescore).read_text())
        meta = {"mode": "rescore"}
    else:
        plans = _abs(args.plans)
        if not plans or not plans.exists():
            print(f"Plans PDF not found: {plans}")
            return 2
        summary, meta = run_vision(args.name, plans, _abs(args.manifest))
        (out_dir / "vision_summary.json").write_text(json.dumps(summary, indent=2))

    sc = score(golden_rows, summary)
    text = report_text(args.name, sc, meta)
    (out_dir / "gap_report.txt").write_text(text)
    (out_dir / "score.json").write_text(json.dumps(
        {k: v for k, v in sc.items() if k not in ("items", "extra")}, indent=2))
    print("\n" + text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
