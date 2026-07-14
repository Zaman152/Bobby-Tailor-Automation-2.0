#!/usr/bin/env python3
"""
Plans-only accuracy benchmark & CI gate (V3-PROD-01).

Runs a plans PDF through the take-off pipeline WITHOUT any companion take-off
document (the real production scenario: only plans are available) and scores
the result against an EXPLICITLY passed ground-truth reference:

  * ``--takeoff-pdf`` — the human take-off PDF (uploads/ pairs). It is parsed
    into golden rows via the devtools companion parser and used ONLY as the
    scoring reference. The runtime pipeline can never discover it.
  * ``--golden``     — a pre-built golden CSV fixture (legacy path).

Exactly one of the two must be supplied. There is NO auto-discovery: ground
truth enters the benchmark only through an explicit argument (21-CONTEXT
Benchmark Protocol, LOCKED).

Isolation is enforced BY CONSTRUCTION and verified per run:
  1. The plans PDF is copied into a fresh temp directory.
  2. A DECOY sibling take-off PDF (sentinel content) is planted next to it.
     The devtools finder is asserted to SEE the decoy (proving it is
     discoverable if anything went looking) …
  3. … and after the pipeline run the result is asserted to contain ZERO
     companion-legend rows and no sentinel values — proving the production
     pipeline never read the planted sibling. A regression re-introducing
     companion auto-discovery fails loudly here.

Gate assertions (RESEARCH §8 layer 5, thresholds overridable via flags):
  * geometry/text-layer/schedule-table provenance quantity accuracy ≥ 97%
  * overall quantity accuracy ≥ 90%
  * item-found rate ≥ 95%
  * zero silent misses (every golden category present or explicitly flagged)
  * vision-provenance quantity share ≈ 0 on vector fixtures
  * two-run reproducibility: per-item deltas ≤ 5% (``--repro``)

Budget: ``--budget USD`` pins ``API_BUDGET_PER_RUN_USD`` for the run (read by
``RunSettings.from_env()``). A ``--repro`` run spends roughly 2× a single run
(RESEARCH §4 cost model: low single-digit USD per fixture set).

Usage:
  # Gate run against the human take-off PDF (spends API credits):
  python3 scripts/vision_only_benchmark.py \
      --name "Crow Cass" \
      --plans-pdf "uploads/Crow - Cass White Road-Plans.pdf" \
      --takeoff-pdf "uploads/Crow - Cass White Road-Take offs.pdf" \
      --repro --report-json reports/accuracy_gate/crow.json

  # Legacy golden-CSV fixture run:
  python3 scripts/vision_only_benchmark.py \
      --name "Crow Cass" \
      --plans-pdf tests/fixtures/crow_cass/crow_cass_plans.pdf \
      --golden tests/fixtures/crow_cass/crow_cass_golden.csv

  # Re-score a previously saved result (FREE, no API):
  python3 scripts/vision_only_benchmark.py \
      --name "Crow Cass" \
      --golden tests/fixtures/crow_cass/crow_cass_golden.csv \
      --rescore reports/vision_only/Crow_Cass/takeoff_result.json
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:  # src/ fallback for fresh checkouts without `pip install -e .`
    import bobbytailor  # noqa: F401
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(ROOT / "src"))

_STOP = {"the", "a", "an", "of", "and", "to", "for", "in", "on", "alt", "h"}

# Quantity provenance classes (21-13 fusion contract). Deterministic sources
# are the ones the gate asserts ≥97% accurate on Crow+Bob.
_DETERMINISTIC_PROVENANCES = frozenset({"geometry", "text_layer", "schedule_table"})
_VISION_PROVENANCE = "vision_ensemble"

# Default tolerance applied to measured (SF/LF/CY…) golden rows built from a
# --takeoff-pdf reference — matches the phase's ±5% reproducibility band.
_MEASURED_DEFAULT_TOL_PCT = 5.0

# Sentinel content of the planted decoy sibling take-off. If either value ever
# surfaces in a pipeline result, the production path read the planted file.
_DECOY_SENTINEL_ITEM = "Decoy Sentinel Item"
_DECOY_SENTINEL_QTY = 999999.0

DEFAULT_THRESHOLDS = {
    "min_geometry_acc": 0.97,
    "min_overall_acc": 0.90,
    "min_item_found": 0.95,
    "max_vision_share": 0.05,
    "repro_tolerance": 0.05,
}


def _tokens(name: str) -> set:
    toks = re.split(r"[-_/\s'\"]+", (name or "").lower())
    return {t for t in toks if t and t not in _STOP and not t.isdigit()}


def _coverage_tokens(name: str) -> set:
    """Tokens with light plural folding for silent-miss coverage matching.

    Only strips a trailing 's' from tokens longer than 3 chars ("walls"->"wall"
    but "gas" stays "gas") — deterministic, no stemming library.
    """
    out = set()
    for t in _tokens(name):
        if len(t) > 3 and t.endswith("s"):
            t = t[:-1]
        out.add(t)
    return out


def _load_golden(path: Path) -> list:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_golden_from_takeoff_pdf(takeoff_pdf: Path) -> list:
    """Parse an EXPLICITLY passed human take-off PDF into golden rows.

    Uses the devtools companion parser (bobbytailor.devtools.companion_takeoff
    — dev/benchmark only, never imported by production entry points). EA rows
    score exact-or-within-1; measured rows get a ±5% tolerance band.
    """
    from bobbytailor.devtools.companion_takeoff import extract_legend_schedules

    rows = []
    for sched in extract_legend_schedules(str(takeoff_pdf)):
        for r in sched.get("rows") or []:
            raw_qty = str(r.get("QTY", "")).replace(",", "").strip()
            try:
                qty = float(raw_qty)
            except ValueError:
                continue
            if qty <= 0:
                continue
            unit = (r.get("UNIT") or "EA").strip().upper()
            if unit in ("EA", "EACH"):
                mode, tol = "exact_or_within_1", "0"
            else:
                mode, tol = "pct", str(_MEASURED_DEFAULT_TOL_PCT)
            rows.append({
                "item_name": r.get("ITEM", ""),
                "quantity": str(qty),
                "unit": unit,
                "tolerance_pct": tol,
                "match_mode": mode,
            })
    return rows


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


# ─── Provenance-split scoring (21-17, V3-PROD-01) ────────────────────────────

def _summary_of(result) -> list:
    """Accept either a full takeoff.json-style report dict or a bare summary list."""
    if isinstance(result, dict):
        return result.get("takeoff_summary") or []
    return result or []


def _provenance_entries(result) -> list:
    """(token_set, normalized_name, provenance) for every provenance-tagged
    component row in the report's raw_line_items (21-13 fields)."""
    entries = []
    if not isinstance(result, dict):
        return entries
    for item in result.get("raw_line_items") or []:
        if not isinstance(item, dict) or item.get("category") != "component":
            continue
        prov = str(item.get("provenance") or "").strip()
        if not prov:
            continue
        desc = str(item.get("description") or "")
        toks = _tokens(desc)
        if not toks:
            continue
        entries.append((toks, " ".join(sorted(toks)), prov))
    return entries


def _row_provenances(row: dict, prov_entries: list) -> set:
    """Set of quantity provenances contributing to an aggregated summary row.

    Matches the row's item name AND its detail-row descriptions against the
    provenance-tagged raw component lines (exact normalised, token subset,
    or ≥0.6 token overlap — same spirit as _best_name_match).
    """
    candidates = [row.get("item", "")]
    for d in row.get("detail") or []:
        if isinstance(d, dict) and d.get("description"):
            candidates.append(str(d["description"]))

    provs = set()
    cand_tok = []
    for c in candidates:
        toks = _tokens(c)
        if toks:
            cand_tok.append((toks, " ".join(sorted(toks))))
    for e_toks, e_norm, prov in prov_entries:
        for c_toks, c_norm in cand_tok:
            if c_norm == e_norm or c_toks <= e_toks or e_toks <= c_toks:
                provs.add(prov)
                break
            overlap = len(c_toks & e_toks) / max(1, len(c_toks | e_toks))
            if overlap >= 0.6:
                provs.add(prov)
                break
    return provs


def _prov_class(provs: set) -> str:
    if not provs:
        return "unknown"
    if _VISION_PROVENANCE in provs:
        return "vision" if provs == {_VISION_PROVENANCE} else "mixed"
    if provs <= _DETERMINISTIC_PROVENANCES:
        return "deterministic"
    if "learned" in provs:
        return "learned"
    return "other"


def _covered_by_flag(golden_name: str, summary: list, fusion_rejected: list) -> bool:
    """True when a MISSING golden category is still explicitly surfaced to a
    human — via a needs_review row (relaxed name match or review_reasons
    mention) or a fusion_rejected audit entry. Flagged counts as covered:
    the pipeline pointed a human at it instead of silently dropping it.
    """
    g_tok = _coverage_tokens(golden_name)
    if not g_tok:
        return False

    def _match(name: str, threshold: float) -> bool:
        a_tok = _coverage_tokens(name)
        if not a_tok:
            return False
        if g_tok <= a_tok or a_tok <= g_tok:
            return True
        overlap = len(g_tok & a_tok) / max(1, len(g_tok | a_tok))
        return overlap >= threshold

    for r in summary:
        if not r.get("needs_review"):
            continue
        if _match(str(r.get("item", "")), 0.45):
            return True
        reasons = " ".join(str(x) for x in (r.get("review_reasons") or []))
        if reasons and g_tok <= _coverage_tokens(reasons):
            return True
    for rej in fusion_rejected or []:
        if not isinstance(rej, dict):
            continue
        name = rej.get("item") or rej.get("name") or rej.get("description") or ""
        if name and _match(str(name), 0.45):
            return True
    return False


def score_with_provenance(result, golden_rows: list) -> dict:
    """Extend score() with the per-provenance accuracy split (V3-PROD-01).

    Adds to the base scoring dict:
      geometry_text_qty_acc — quantity accuracy over golden items whose
          matched summary row is backed EXCLUSIVELY by deterministic
          provenance (geometry / text_layer / schedule_table). None when no
          such items exist (gate treats None as a failure — cannot certify).
      vision_qty_share — fraction of quantity-bearing summary rows whose
          provenance set contains vision_ensemble ("≈0 on vector fixtures").
      silent_misses — golden categories neither present nor flagged (no
          name-matched row, no covering needs_review row, no fusion_rejected
          audit entry). MUST be empty to pass the gate.
      provenance_counts — quantity-bearing summary rows per provenance class.
      items[*].provenance / items[*].prov_class — per-item table.
    """
    summary = _summary_of(result)
    fusion_rejected = result.get("fusion_rejected") or [] if isinstance(result, dict) else []
    sc = score(golden_rows, summary)

    prov_entries = _provenance_entries(result)
    rows_by_name = {r.get("item", ""): r for r in summary}
    row_prov_cache = {}

    def _provs_for_row_name(name):
        if name not in row_prov_cache:
            row = rows_by_name.get(name)
            row_prov_cache[name] = _row_provenances(row, prov_entries) if row else set()
        return row_prov_cache[name]

    # Per-golden-item provenance annotation.
    for it in sc["items"]:
        if it["found"] and it["ai_name"] is not None:
            provs = _provs_for_row_name(it["ai_name"])
        else:
            provs = set()
        it["provenance"] = sorted(provs)
        it["prov_class"] = _prov_class(provs)

    det_items = [i for i in sc["items"] if i["found"] and i["prov_class"] == "deterministic"]
    sc["geometry_text_qty_acc"] = (
        sum(1 for i in det_items if i["qty_ok"]) / len(det_items) if det_items else None
    )
    sc["n_geometry_text"] = len(det_items)

    # Vision share over ALL quantity-bearing summary rows (not just matched
    # ones) — the honest project-wide measure the vector-fixture gate asserts.
    qty_rows = [r for r in summary if (_qty(r) or 0) > 0]
    prov_counts = {}
    n_vision = 0
    for r in qty_rows:
        provs = _provs_for_row_name(r.get("item", ""))
        cls = _prov_class(provs)
        prov_counts[cls] = prov_counts.get(cls, 0) + 1
        if _VISION_PROVENANCE in provs:
            n_vision += 1
    sc["vision_qty_share"] = (n_vision / len(qty_rows)) if qty_rows else None
    sc["n_quantity_bearing"] = len(qty_rows)
    sc["provenance_counts"] = prov_counts

    sc["silent_misses"] = [
        i["item"] for i in sc["items"]
        if not i["found"] and not _covered_by_flag(i["item"], summary, fusion_rejected)
    ]
    return sc


def check_reproducibility(result_a, result_b, tolerance: float = 0.05) -> dict:
    """Per-item relative deltas between two runs; pass iff every delta ≤ tolerance.

    Items are matched by normalised name over quantity-bearing rows. An item
    present in only one run is a reproducibility failure (delta None, ok
    False). Relative delta = |qa-qb| / max(|qa|, |qb|) — symmetric, and the
    exact 5% boundary passes (≤).
    """
    def _rows(result):
        out = {}
        for r in _summary_of(result):
            q = _qty(r)
            if q is None or q <= 0:
                continue
            key = " ".join(sorted(_tokens(r.get("item", "")))) or str(r.get("item", "")).lower()
            out[key] = out.get(key, 0.0) + q
        return out

    a_rows, b_rows = _rows(result_a), _rows(result_b)
    items = []
    for key in sorted(set(a_rows) | set(b_rows)):
        qa, qb = a_rows.get(key), b_rows.get(key)
        if qa is None or qb is None:
            items.append({
                "item": key, "run_a": qa, "run_b": qb, "delta": None,
                "ok": False,
                "status": "ONLY_RUN_A" if qb is None else "ONLY_RUN_B",
            })
            continue
        denom = max(abs(qa), abs(qb))
        delta = 0.0 if denom == 0 else abs(qa - qb) / denom
        ok = delta <= tolerance + 1e-12
        items.append({
            "item": key, "run_a": qa, "run_b": qb,
            "delta": round(delta, 6), "ok": ok,
            "status": "PASS" if ok else "FAIL_DELTA",
        })

    deltas = [i["delta"] for i in items if i["delta"] is not None]
    return {
        "items": items,
        "n_items": len(items),
        "max_delta": max(deltas) if deltas else None,
        "mean_delta": (sum(deltas) / len(deltas)) if deltas else None,
        "tolerance": tolerance,
        "pass": bool(items) and all(i["ok"] for i in items),
    }


def evaluate_gates(sc: dict, thresholds: dict, repro: Optional[dict] = None) -> dict:
    """Deterministic gate evaluation. None metrics FAIL (cannot certify)."""
    th = dict(DEFAULT_THRESHOLDS)
    th.update(thresholds or {})
    checks = {}
    failures = []

    def _check(name, value, ok, requirement):
        checks[name] = {"value": value, "requirement": requirement, "ok": bool(ok)}
        if not ok:
            failures.append(f"{name}: {value} (required {requirement})")

    v = sc.get("geometry_text_qty_acc")
    _check("geometry_text_qty_acc", v,
           v is not None and v >= th["min_geometry_acc"],
           f">= {th['min_geometry_acc']}")

    v = sc.get("overall_qty")
    _check("overall_qty", v,
           v is not None and v >= th["min_overall_acc"],
           f">= {th['min_overall_acc']}")

    v = sc.get("name_found_rate")
    _check("item_found_rate", v,
           v is not None and v >= th["min_item_found"],
           f">= {th['min_item_found']}")

    misses = sc.get("silent_misses")
    n_miss = len(misses) if misses is not None else None
    _check("silent_misses", misses if misses else [],
           n_miss == 0, "== 0 (every golden category present or flagged)")

    v = sc.get("vision_qty_share")
    _check("vision_qty_share", v,
           v is not None and v <= th["max_vision_share"],
           f"<= {th['max_vision_share']} (vision-provenance quantities ~0 on vector fixtures)")

    if repro is not None:
        _check("reproducibility", repro.get("max_delta"),
               bool(repro.get("pass")),
               f"all per-item deltas <= {repro.get('tolerance', th['repro_tolerance'])}")

    return {"passed": not failures, "failures": failures, "checks": checks}


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
    # Provenance split (present when scored via score_with_provenance).
    if "geometry_text_qty_acc" in sc:
        L.append(
            f"  Provenance split: geometry/text qty acc={_pct(sc.get('geometry_text_qty_acc'))} "
            f"(n={sc.get('n_geometry_text', 0)})  "
            f"vision qty share={_pct(sc.get('vision_qty_share'))} "
            f"of {sc.get('n_quantity_bearing', 0)} quantity-bearing rows"
        )
        counts = sc.get("provenance_counts") or {}
        if counts:
            L.append("  Provenance classes: " + ", ".join(
                f"{k}={counts[k]}" for k in sorted(counts)))
        misses = sc.get("silent_misses")
        if misses:
            L.append(f"  SILENT MISSES ({len(misses)}): " + "; ".join(misses))
        else:
            L.append("  Silent misses: 0 (every golden category present or flagged)")
    if meta:
        L.append(
            f"  [{meta.get('mode','')}] runtime={meta.get('elapsed','?')}  "
            f"cost=${meta.get('cost',0):.4f}  sheets={meta.get('sheets','?')}"
        )
    L.append("")
    L.append(f"{'STATUS':10}{'ITEM':<30}{'GOLDEN':>14}{'AI':>14}{'ERR%':>8}  CAT  PROV")
    L.append("-" * 84)
    for it in sc["items"]:
        ai = it["ai"]
        ai_str = f"{ai:,.2f}" if isinstance(ai, (int, float)) else "—"
        err = f"{it['error_pct']}" if it["error_pct"] is not None else "—"
        label = it["item"]
        if it["ai_name"] and it["ai_name"].lower() != it["item"].lower():
            label = f"{it['item']}≈{it['ai_name']}"
        prov = it.get("prov_class", "")
        L.append(
            f"{it['status']:10}{label:<30}{it['golden']:>14,.2f}{ai_str:>14}{err:>8}  "
            f"{it['category']}  {prov}"
        )
    if sc["extra"]:
        L.append("")
        L.append("EXTRA items AI produced not in golden:")
        for e in sc["extra"]:
            L.append(f"  + {e.get('item','?'):<30} {e.get('quantity','?')} {e.get('unit','')}")
    return "\n".join(L)


def gate_report_text(gates: dict, repro: Optional[dict], tracking_only: bool) -> str:
    L = ["", "-" * 84, "GATE CHECKS" + ("  [tracking-only — never fails the run]" if tracking_only else "")]
    for name, chk in gates["checks"].items():
        mark = "PASS" if chk["ok"] else "FAIL"
        L.append(f"  {mark:4}  {name:<24} value={chk['value']}  required {chk['requirement']}")
    if repro is not None:
        L.append(
            f"  Reproducibility: n={repro['n_items']}  max Δ={repro['max_delta']}  "
            f"mean Δ={repro['mean_delta']}  -> {'PASS' if repro['pass'] else 'FAIL'}"
        )
        bad = [i for i in repro["items"] if not i["ok"]]
        for i in bad[:20]:
            L.append(
                f"    Δ FAIL {i['item']:<40} run_a={i['run_a']} run_b={i['run_b']} delta={i['delta']}"
            )
    verdict = "TRACKED" if tracking_only else ("PASSED" if gates["passed"] else "FAILED")
    L.append(f"  GATE VERDICT: {verdict}")
    return "\n".join(L)


# ─── Isolation: tempdir + planted-decoy no-discovery assertion ───────────────

def _plant_decoy_takeoff(tmp_dir: Path, plans_stem: str) -> Path:
    """Plant a sentinel sibling take-off PDF next to the isolated plans copy.

    The decoy is deliberately discoverable by the devtools finder — the
    post-run leakage assertion then proves the production pipeline never read
    it. Sentinel content parses as '<item> 999999 EA' if anything ingests it.
    """
    import fitz

    decoy = tmp_dir / f"{plans_stem}-Take offs.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), _DECOY_SENTINEL_ITEM)
    page.insert_text((72, 90), f"{int(_DECOY_SENTINEL_QTY)} EA")
    doc.save(str(decoy))
    doc.close()
    return decoy


def _assert_no_ground_truth_leakage(result: dict, decoy: Path) -> None:
    """Fail loudly if the pipeline result shows ANY trace of the planted decoy
    or of companion-legend ingestion (regression tripwire for auto-discovery)."""
    summary = _summary_of(result)
    for row in summary:
        assert row.get("source") != "companion_takeoff_legend", (
            f"GROUND-TRUTH LEAKAGE: companion-legend row in takeoff_summary: {row.get('item')}"
        )
        name = str(row.get("item", "")).lower()
        assert _DECOY_SENTINEL_ITEM.lower() not in name, (
            f"GROUND-TRUTH LEAKAGE: planted decoy item surfaced: {row.get('item')}"
        )
        assert _qty(row) != _DECOY_SENTINEL_QTY, (
            f"GROUND-TRUTH LEAKAGE: planted decoy sentinel quantity surfaced on {row.get('item')}"
        )
    for item in (result.get("calculated_takeoff") or []) if isinstance(result, dict) else []:
        assert item.get("qty_source") != "companion_takeoff_legend", (
            f"GROUND-TRUTH LEAKAGE: companion-legend calculated item: {item.get('description')}"
            f" (pipeline read {decoy.name}?)"
        )


def run_vision(name: str, plans: Path, manifest: Optional[Path], run_tag: str = "") -> tuple:
    from bobbytailor.devtools.companion_takeoff import find_companion_takeoff_pdf
    from bobbytailor.pipeline.pdf_analyzer import run_pdf_analysis

    with tempfile.TemporaryDirectory(prefix="vision_only_") as tmp:
        isolated = Path(tmp) / plans.name
        shutil.copy2(plans, isolated)

        # Plant a discoverable decoy sibling take-off, then prove after the
        # run that production never read it (strengthened no-discovery
        # assertion — the old empty-tempdir check could not catch a
        # regression that re-introduced sibling auto-discovery).
        decoy = _plant_decoy_takeoff(Path(tmp), plans.stem)
        companion = find_companion_takeoff_pdf(str(isolated))
        assert companion is not None and Path(companion).resolve() == decoy.resolve(), (
            f"Decoy sibling should be discoverable by the devtools finder, got: {companion}"
        )
        print(f"[{name}{run_tag}] decoy sibling planted + discoverable by devtools finder "
              f"— production result will be asserted leakage-free")

        kwargs = {}
        if manifest:
            kwargs["manifest_path"] = str(manifest)
        t0 = time.time()
        result = run_pdf_analysis(
            str(isolated), project_name=f"VisionOnly {name}{run_tag}", **kwargs)
        elapsed = time.time() - t0

        _assert_no_ground_truth_leakage(result, decoy)
        print(f"[{name}{run_tag}] plans-only confirmed (planted sibling take-off NOT read)")

    meta = {
        "mode": "manifest" if manifest else "plans-only",
        "elapsed": f"{elapsed:.0f}s",
        "cost": (result.get("api_usage") or {}).get("total_cost_usd", 0),
        "sheets": result.get("sheets_processed", "?"),
    }
    return result, meta


def _load_rescore(path: Path):
    """Load a saved result: full takeoff.json-style dict OR bare summary list.

    A previously written --report-json gate artifact is only usable when it
    embeds the pipeline result (the "result" key, written by main()). A
    rescore against the wrong artifact type must FAIL LOUDLY — scoring an
    empty summary would print confidently wrong 0% numbers (WR-07).
    """
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "takeoff_summary" not in data and "score" in data:
        embedded = data.get("result")
        if not embedded:
            print(
                f"--rescore artifact {path} is a gate report WITHOUT an embedded "
                "pipeline result — every row would score MISSING against an "
                "empty summary. Pass the run's takeoff_result.json (or a "
                "report JSON written by a version that embeds 'result')."
            )
            sys.exit(2)
        data = embedded
    if isinstance(data, dict) and "takeoff_summary" not in data:
        print(
            f"--rescore artifact {path} has no 'takeoff_summary' — this is not "
            "a takeoff result. Pass takeoff_result.json or a bare summary list."
        )
        sys.exit(2)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Plans-only accuracy benchmark & CI gate (V3-PROD-01)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--golden",
                    help="golden CSV fixture (exactly one of --golden/--takeoff-pdf)")
    ap.add_argument("--takeoff-pdf",
                    help="EXPLICIT ground-truth human take-off PDF (evaluation only — "
                         "never visible to the pipeline)")
    ap.add_argument("--plans-pdf", "--plans", dest="plans",
                    help="plans PDF — the ONLY pipeline input (omit when using --rescore)")
    ap.add_argument("--manifest", help="optional object manifest (JSON/CSV, dev input)")
    ap.add_argument("--rescore",
                    help="path to a saved takeoff_result.json / vision_summary.json "
                         "to re-score (no API)")
    ap.add_argument("--repro", action="store_true",
                    help="run twice in fresh tempdirs and assert per-item deltas <= 5%%")
    ap.add_argument("--min-geometry-acc", type=float,
                    default=DEFAULT_THRESHOLDS["min_geometry_acc"],
                    help="gate: min geometry/text-layer provenance quantity accuracy")
    ap.add_argument("--min-overall-acc", type=float,
                    default=DEFAULT_THRESHOLDS["min_overall_acc"],
                    help="gate: min overall quantity accuracy")
    ap.add_argument("--min-item-found", type=float,
                    default=DEFAULT_THRESHOLDS["min_item_found"],
                    help="gate: min item-found rate")
    ap.add_argument("--max-vision-share", type=float,
                    default=DEFAULT_THRESHOLDS["max_vision_share"],
                    help="gate: max vision-provenance quantity share (~0 on vector fixtures)")
    ap.add_argument("--budget", type=float, default=None,
                    help="per-run API budget in USD (sets API_BUDGET_PER_RUN_USD for "
                         "RunSettings; a --repro run spends ~2x)")
    ap.add_argument("--report-json", default=None,
                    help="write the full scoring dict (CI artifact) to this path")
    ap.add_argument("--tracking-only", action="store_true",
                    help="score and report but NEVER exit non-zero (Chelsea/Moxy tracking)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true", help="suppress pipeline progress logs")
    args = ap.parse_args()

    if bool(args.golden) == bool(args.takeoff_pdf):
        print("Exactly one of --golden / --takeoff-pdf is required "
              "(explicit ground truth — no discovery).")
        return 2
    if args.repro and args.rescore:
        print("--repro requires live runs; it cannot be combined with --rescore.")
        return 2

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

    # Ground truth — EXPLICIT input only.
    if args.golden:
        golden = _abs(args.golden)
        if not golden or not golden.exists():
            print(f"Golden CSV not found: {golden}")
            return 2
        golden_rows = _load_golden(golden)
    else:
        takeoff_pdf = _abs(args.takeoff_pdf)
        if not takeoff_pdf or not takeoff_pdf.exists():
            print(f"Take-off PDF not found: {takeoff_pdf}")
            return 2
        golden_rows = load_golden_from_takeoff_pdf(takeoff_pdf)
        if not golden_rows:
            print(f"No quantity rows parsed from take-off PDF: {takeoff_pdf}")
            return 2
        print(f"[{args.name}] ground truth: {len(golden_rows)} golden rows "
              f"parsed from {takeoff_pdf.name} (explicit --takeoff-pdf)")

    if args.budget is not None:
        # RunSettings.from_env() reads API_BUDGET_PER_RUN_USD at run start —
        # this is the single budget knob threaded through the BudgetGuard.
        os.environ["API_BUDGET_PER_RUN_USD"] = str(args.budget)

    safe = args.name.replace(" ", "_").replace("/", "-")
    out_dir = Path(args.out) if args.out else (ROOT / "reports" / "vision_only" / safe)
    out_dir.mkdir(parents=True, exist_ok=True)

    thresholds = {
        "min_geometry_acc": args.min_geometry_acc,
        "min_overall_acc": args.min_overall_acc,
        "min_item_found": args.min_item_found,
        "max_vision_share": args.max_vision_share,
    }

    meta = {}
    meta2 = None
    result2 = None
    if args.rescore:
        result = _load_rescore(_abs(args.rescore))
        meta = {"mode": "rescore"}
    else:
        plans = _abs(args.plans)
        if not plans or not plans.exists():
            print(f"Plans PDF not found: {plans}")
            return 2
        result, meta = run_vision(args.name, plans, _abs(args.manifest))
        summary = _summary_of(result)
        (out_dir / "vision_summary.json").write_text(json.dumps(summary, indent=2))
        (out_dir / "takeoff_result.json").write_text(json.dumps(result, indent=2))
        if args.repro:
            result2, meta2 = run_vision(args.name, plans, _abs(args.manifest), run_tag=" run2")
            (out_dir / "takeoff_result_run2.json").write_text(json.dumps(result2, indent=2))

    sc = score_with_provenance(result, golden_rows)
    repro = None
    sc2 = None
    if result2 is not None:
        sc2 = score_with_provenance(result2, golden_rows)
        repro = check_reproducibility(result, result2,
                                      tolerance=DEFAULT_THRESHOLDS["repro_tolerance"])
    gates = evaluate_gates(sc, thresholds, repro=repro)

    text = report_text(args.name, sc, meta)
    text += gate_report_text(gates, repro, args.tracking_only)
    (out_dir / "gap_report.txt").write_text(text)
    (out_dir / "score.json").write_text(json.dumps(
        {k: v for k, v in sc.items() if k not in ("items", "extra")}, indent=2))

    cost1 = float(meta.get("cost") or 0)
    cost2 = float((meta2 or {}).get("cost") or 0)
    if args.report_json:
        report_path = _abs(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({
            "name": args.name,
            "tracking_only": bool(args.tracking_only),
            "thresholds": thresholds,
            "meta": meta,
            "meta_run2": meta2,
            "cost_total_usd": round(cost1 + cost2, 4),
            "score": sc,
            "score_run2": sc2,
            "reproducibility": repro,
            "gates": gates,
            # Embedded pipeline result so --rescore of this artifact scores
            # the REAL summary, never an empty one (WR-07).
            "result": result,
        }, indent=2, default=str))

    print("\n" + text)
    if args.tracking_only:
        return 0
    return 0 if gates["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
