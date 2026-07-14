"""Offline scoring tests for the plans-only accuracy gate (21-17, V3-PROD-01).

Pins the benchmark's scoring math on canned takeoff.json-style data — NO API
calls, NO pipeline runs. Covers:

  * score_with_provenance: per-provenance accuracy split, vision quantity
    share, silent-miss detection (incl. the flagged-counts-as-covered rule)
  * check_reproducibility: pass/fail at the 5% boundary, one-sided items
  * evaluate_gates: threshold plumbing (0.96 geometry acc fails the 0.97 gate)
  * CLI plumbing: --rescore + threshold flags drive the exit code;
    --tracking-only never exits non-zero
  * --takeoff-pdf ingestion: explicit ground-truth PDF -> golden rows
  * accuracy_gate.sh structural assertions (filenames, tracking-only split,
    LEARNING_DB_PATH isolation export)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.vision_only_benchmark import (
    DEFAULT_THRESHOLDS,
    check_reproducibility,
    evaluate_gates,
    load_golden_from_takeoff_pdf,
    score_with_provenance,
)

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "scripts" / "vision_only_benchmark.py"
GATE_SH = ROOT / "scripts" / "accuracy_gate.sh"


# ─── canned-data builders ────────────────────────────────────────────────────

def _gold(name, qty, unit="EA", mode=None, tol=None):
    if mode is None:
        mode = "exact_or_within_1" if unit.upper() in ("EA", "EACH") else "pct"
    if tol is None:
        tol = "0" if mode == "exact_or_within_1" else "5"
    return {
        "item_name": name, "quantity": str(qty), "unit": unit,
        "tolerance_pct": str(tol), "match_mode": mode,
    }


def _row(item, qty, unit="EA", needs_review=False, reasons=None):
    return {
        "item": item, "quantity": qty, "unit": unit,
        "needs_review": needs_review,
        "review_reasons": list(reasons or []),
        "detail": [{"description": item}],
        "source": "",
    }


def _comp(desc, prov):
    return {"category": "component", "description": desc,
            "provenance": prov, "value": 1}


def _report(summary, components=None, fusion_rejected=None):
    return {
        "takeoff_summary": summary,
        "raw_line_items": list(components or []),
        "fusion_rejected": list(fusion_rejected or []),
        "api_usage": {"total_cost_usd": 0.0},
    }


# ─── score_with_provenance ───────────────────────────────────────────────────

class TestScoreWithProvenance:
    def test_geometry_text_accuracy_split(self):
        """geometry_text_qty_acc counts ONLY deterministic-provenance items;
        a vision item's pass/fail never moves the deterministic number."""
        golden = [
            _gold("Bollards", 28),                       # geometry, correct
            _gold("Columns", 132),                       # geometry, WRONG qty
            _gold("CMU Wall", 2204.0, unit="SF"),        # text_layer, within 5%
            _gold("Signage", 5),                         # vision_ensemble, correct
        ]
        summary = [
            _row("Bollards", 28),
            _row("Columns", 90),
            _row("CMU Wall", 2200.0, unit="SF"),
            _row("Signage", 5),
        ]
        comps = [
            _comp("Bollards", "geometry"),
            _comp("Columns", "geometry"),
            _comp("CMU Wall", "text_layer"),
            _comp("Signage", "vision_ensemble"),
        ]
        sc = score_with_provenance(_report(summary, comps), golden)

        # 2 of 3 deterministic items pass (Columns fails on quantity).
        assert sc["n_geometry_text"] == 3
        assert sc["geometry_text_qty_acc"] == pytest.approx(2 / 3)
        # Overall covers all 4 golden items: 3 pass.
        assert sc["overall_qty"] == pytest.approx(3 / 4)
        # Per-item table carries the provenance class.
        by_name = {i["item"]: i for i in sc["items"]}
        assert by_name["Bollards"]["prov_class"] == "deterministic"
        assert by_name["Signage"]["prov_class"] == "vision"
        assert by_name["Signage"]["provenance"] == ["vision_ensemble"]

    def test_vision_qty_share_fraction_of_quantity_bearing_rows(self):
        """vision_qty_share = vision-provenance rows / ALL quantity-bearing rows."""
        golden = [_gold("Bollards", 28)]
        summary = [
            _row("Bollards", 28),
            _row("CMU Wall", 2200.0, unit="SF"),
            _row("Signage", 5),
            _row("Ghost Item", 0),  # not quantity-bearing — excluded
        ]
        comps = [
            _comp("Bollards", "geometry"),
            _comp("CMU Wall", "text_layer"),
            _comp("Signage", "vision_ensemble"),
        ]
        sc = score_with_provenance(_report(summary, comps), golden)
        assert sc["n_quantity_bearing"] == 3
        assert sc["vision_qty_share"] == pytest.approx(1 / 3)
        assert sc["provenance_counts"]["deterministic"] == 2
        assert sc["provenance_counts"]["vision"] == 1

    def test_vision_share_zero_on_pure_deterministic_result(self):
        """The vector-fixture assertion: no vision-provenance rows -> share 0."""
        golden = [_gold("Bollards", 28)]
        summary = [_row("Bollards", 28), _row("CMU Wall", 2200.0, unit="SF")]
        comps = [_comp("Bollards", "geometry"), _comp("CMU Wall", "schedule_table")]
        sc = score_with_provenance(_report(summary, comps), golden)
        assert sc["vision_qty_share"] == 0.0

    def test_silent_miss_detected(self):
        """A golden category with no matching row and no flag is a SILENT miss."""
        golden = [_gold("Bollards", 28), _gold("Canopies", 4)]
        summary = [_row("Bollards", 28)]
        sc = score_with_provenance(_report(summary, [_comp("Bollards", "geometry")]), golden)
        assert sc["silent_misses"] == ["Canopies"]

    def test_flagged_row_counts_as_covered(self):
        """A needs_review row whose review_reasons mention the missing golden
        category means the pipeline surfaced it to a human — NOT silent."""
        golden = [_gold("Gas Piping", 120, unit="LF")]
        summary = [
            _row("Site Utilities", 1, needs_review=True,
                 reasons=["gas piping run not measurable from plans"]),
        ]
        sc = score_with_provenance(_report(summary), golden)
        # Not name-matched (found=False) …
        assert sc["name_found_rate"] == 0.0
        # … but flagged coverage keeps it out of silent_misses.
        assert sc["silent_misses"] == []

    def test_fusion_rejected_entry_counts_as_covered(self):
        """A fusion_rejected audit entry covering the category is not silent."""
        golden = [_gold("Tilt Up Walls", 108442.66, unit="SF")]
        summary = [_row("Bollards", 28)]
        rejected = [{"item": "Internal Tilt up walls", "reason": "vision qty rejected"}]
        sc = score_with_provenance(
            _report(summary, [_comp("Bollards", "geometry")], fusion_rejected=rejected),
            golden,
        )
        assert sc["silent_misses"] == []

    def test_no_provenance_data_yields_none_geometry_acc(self):
        """A bare summary (no raw_line_items) cannot certify the deterministic
        split — geometry_text_qty_acc is None and the gate must fail it."""
        golden = [_gold("Bollards", 28)]
        sc = score_with_provenance([_row("Bollards", 28)], golden)
        assert sc["geometry_text_qty_acc"] is None
        gates = evaluate_gates(sc, DEFAULT_THRESHOLDS)
        assert not gates["passed"]
        assert any("geometry_text_qty_acc" in f for f in gates["failures"])


# ─── check_reproducibility ───────────────────────────────────────────────────

class TestReproducibility:
    def test_passes_at_exact_5pct_boundary(self):
        a = _report([_row("Bollards", 100.0)])
        b = _report([_row("Bollards", 95.0)])  # |100-95|/100 = 0.05 exactly
        rep = check_reproducibility(a, b, tolerance=0.05)
        assert rep["pass"] is True
        assert rep["max_delta"] == pytest.approx(0.05)

    def test_fails_just_above_5pct(self):
        a = _report([_row("Bollards", 100.0)])
        b = _report([_row("Bollards", 94.0)])  # delta 0.06
        rep = check_reproducibility(a, b, tolerance=0.05)
        assert rep["pass"] is False
        assert rep["max_delta"] == pytest.approx(0.06)
        assert rep["mean_delta"] == pytest.approx(0.06)
        assert [i["status"] for i in rep["items"]] == ["FAIL_DELTA"]

    def test_item_present_in_only_one_run_fails(self):
        a = _report([_row("Bollards", 28), _row("Columns", 132)])
        b = _report([_row("Bollards", 28)])
        rep = check_reproducibility(a, b)
        assert rep["pass"] is False
        one_sided = [i for i in rep["items"] if i["status"] == "ONLY_RUN_A"]
        assert len(one_sided) == 1 and one_sided[0]["delta"] is None

    def test_identical_runs_pass_with_zero_deltas(self):
        a = _report([_row("Bollards", 28), _row("CMU Wall", 2204.33, unit="SF")])
        rep = check_reproducibility(a, a)
        assert rep["pass"] is True
        assert rep["max_delta"] == 0.0
        assert rep["n_items"] == 2

    def test_empty_runs_do_not_pass(self):
        rep = check_reproducibility(_report([]), _report([]))
        assert rep["pass"] is False


# ─── evaluate_gates threshold plumbing ───────────────────────────────────────

class TestGateThresholds:
    BASE_SC = {
        "geometry_text_qty_acc": 0.98,
        "overall_qty": 0.95,
        "name_found_rate": 1.0,
        "silent_misses": [],
        "vision_qty_share": 0.0,
    }

    def test_gate_fails_when_geometry_acc_096_below_097(self):
        sc = dict(self.BASE_SC, geometry_text_qty_acc=0.96)
        gates = evaluate_gates(sc, {"min_geometry_acc": 0.97})
        assert gates["passed"] is False
        assert gates["checks"]["geometry_text_qty_acc"]["ok"] is False
        assert any(f.startswith("geometry_text_qty_acc") for f in gates["failures"])

    def test_gate_passes_at_thresholds(self):
        sc = dict(self.BASE_SC, geometry_text_qty_acc=0.97,
                  overall_qty=0.90, name_found_rate=0.95)
        gates = evaluate_gates(sc, DEFAULT_THRESHOLDS)
        assert gates["passed"] is True
        assert gates["failures"] == []

    def test_silent_miss_fails_gate(self):
        sc = dict(self.BASE_SC, silent_misses=["Gas Piping"])
        gates = evaluate_gates(sc, DEFAULT_THRESHOLDS)
        assert gates["passed"] is False
        assert gates["checks"]["silent_misses"]["ok"] is False

    def test_vision_share_above_max_fails_gate(self):
        sc = dict(self.BASE_SC, vision_qty_share=0.20)
        gates = evaluate_gates(sc, DEFAULT_THRESHOLDS)
        assert gates["passed"] is False
        assert gates["checks"]["vision_qty_share"]["ok"] is False

    def test_failed_reproducibility_fails_gate(self):
        repro = {"pass": False, "max_delta": 0.30, "tolerance": 0.05}
        gates = evaluate_gates(dict(self.BASE_SC), DEFAULT_THRESHOLDS, repro=repro)
        assert gates["passed"] is False
        assert gates["checks"]["reproducibility"]["ok"] is False


# ─── CLI plumbing (subprocess, --rescore path — zero API) ────────────────────

def _write_cli_fixtures(tmp_path, geometry_acc_pass=True):
    """Canned full-result JSON + golden CSV for a --rescore CLI run."""
    golden_csv = tmp_path / "golden.csv"
    golden_csv.write_text(
        "item_name,quantity,unit,tolerance_pct,match_mode\n"
        "Bollards,28,EA,0,exact_or_within_1\n"
        "Columns,132,EA,0,exact_or_within_1\n"
    )
    columns_qty = 132 if geometry_acc_pass else 90
    result = _report(
        [_row("Bollards", 28), _row("Columns", columns_qty)],
        [_comp("Bollards", "geometry"), _comp("Columns", "geometry")],
    )
    result_json = tmp_path / "takeoff_result.json"
    result_json.write_text(json.dumps(result))
    return golden_csv, result_json


def _run_cli(tmp_path, golden_csv, result_json, *extra):
    cmd = [
        sys.executable, str(BENCH),
        "--name", "CLI Test",
        "--golden", str(golden_csv),
        "--rescore", str(result_json),
        "--out", str(tmp_path / "out"),
        "--quiet",
    ] + list(extra)
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)


class TestCliPlumbing:
    def test_exit_zero_when_gates_pass(self, tmp_path):
        golden_csv, result_json = _write_cli_fixtures(tmp_path, geometry_acc_pass=True)
        proc = _run_cli(tmp_path, golden_csv, result_json,
                        "--report-json", str(tmp_path / "report.json"))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        report = json.loads((tmp_path / "report.json").read_text())
        assert report["gates"]["passed"] is True
        assert report["score"]["geometry_text_qty_acc"] == 1.0

    def test_exit_nonzero_when_geometry_gate_fails(self, tmp_path):
        golden_csv, result_json = _write_cli_fixtures(tmp_path, geometry_acc_pass=False)
        proc = _run_cli(tmp_path, golden_csv, result_json)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "geometry_text_qty_acc" in proc.stdout

    def test_tracking_only_never_fails(self, tmp_path):
        golden_csv, result_json = _write_cli_fixtures(tmp_path, geometry_acc_pass=False)
        proc = _run_cli(tmp_path, golden_csv, result_json, "--tracking-only")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "TRACKED" in proc.stdout

    def test_requires_exactly_one_ground_truth_source(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(BENCH), "--name", "X", "--quiet"],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        assert proc.returncode == 2
        assert "Exactly one of --golden / --takeoff-pdf" in proc.stdout


# ─── --takeoff-pdf ingestion (explicit ground truth, offline) ────────────────

class TestTakeoffPdfIngestion:
    def test_legend_pdf_parses_to_golden_rows(self, tmp_path):
        import fitz

        pdf = tmp_path / "Sample-Take offs.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Bollards")
        page.insert_text((72, 90), "28 EA")
        page.insert_text((72, 120), "CMU Wall")
        page.insert_text((72, 138), "2,204.33 SF")
        doc.save(str(pdf))
        doc.close()

        rows = load_golden_from_takeoff_pdf(pdf)
        by_name = {r["item_name"]: r for r in rows}
        assert set(by_name) == {"Bollards", "CMU Wall"}
        assert by_name["Bollards"]["match_mode"] == "exact_or_within_1"
        assert float(by_name["Bollards"]["quantity"]) == 28.0
        assert by_name["CMU Wall"]["match_mode"] == "pct"
        assert float(by_name["CMU Wall"]["tolerance_pct"]) == 5.0
        assert float(by_name["CMU Wall"]["quantity"]) == pytest.approx(2204.33)


# ─── accuracy_gate.sh structural assertions ──────────────────────────────────

class TestGateScript:
    def test_shell_syntax_clean(self):
        proc = subprocess.run(["bash", "-n", str(GATE_SH)],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr

    def test_contains_all_four_upload_plan_filenames(self):
        src = GATE_SH.read_text()
        assert "Crow - Cass White Road-Plans.pdf" in src
        assert "Bob's Discount Furniture - Kennesaw, GA-plans.pdf" in src
        assert "Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf" in src
        assert "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf" in src
        # Ground-truth pair filenames — including the real "Take offds" typo.
        assert "Crow - Cass White Road-Take offs.pdf" in src
        assert "Bob's Discount Furniture - Kennesaw, GA-Take offds.pdf" in src

    def test_gating_vs_tracking_split(self):
        """Crow+Bob invoke in gate mode (repro hard gate); Chelsea+Moxy track."""
        src = GATE_SH.read_text()
        blocks = {}
        for name in ("Crow Cass", "Bobs Discount", "Chelsea Bear Creek", "Moxy Knoxville"):
            idx = src.index('run_bench "{}"'.format(name))
            blocks[name] = src[idx:src.index("\n\n", idx)]
        assert blocks["Crow Cass"].rstrip().endswith("gate")
        assert blocks["Bobs Discount"].rstrip().endswith("gate")
        assert blocks["Chelsea Bear Creek"].rstrip().endswith("track")
        assert blocks["Moxy Knoxville"].rstrip().endswith("track")
        # --tracking-only exists only on the track/learned-assisted branch.
        assert "--tracking-only" in src

    def test_learning_isolation_export_before_any_benchmark_call(self):
        src = GATE_SH.read_text()
        export_idx = src.index("export LEARNING_DB_PATH=")
        first_bench_idx = src.index('python3 "$ROOT/scripts/vision_only_benchmark.py"')
        assert export_idx < first_bench_idx
        assert "mktemp -d" in src[export_idx:export_idx + 120]

    def test_cost_baseline_and_regression_warning_present(self):
        src = GATE_SH.read_text()
        assert ".cost_baseline.json" in src
        assert "COST REGRESSION" in src
        assert "2.0 *" in src or "2x" in src
