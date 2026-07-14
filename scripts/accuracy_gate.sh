#!/usr/bin/env bash
# ============================================================================
# accuracy_gate.sh — one-command plans-only accuracy gate (V3-PROD-01)
# ============================================================================
#
# Runs scripts/vision_only_benchmark.py over the four uploads/ project pairs
# (21-CONTEXT Benchmark Protocol, LOCKED):
#
#   HARD GATE (exit code reflects these two only):
#     Crow Cass        — plans + "Take offs" pair, --repro double-run
#     Bobs Discount    — plans + "Take offds" pair (typo is in the real
#                        filename), --repro double-run
#   TRACKED (scored + recorded, never fail the gate):
#     Chelsea Bear Creek, Moxy Knoxville — --tracking-only
#
# Gate assertions per project (RESEARCH §8 layer 5 defaults, see benchmark):
#   geometry/text provenance qty accuracy >= 97%, overall >= 90%,
#   item-found >= 95%, zero silent misses, vision qty share ~ 0,
#   two-run reproducibility: per-item deltas <= 5%.
#
# COST (spends real API credits — CI/user-invoked only):
#   Each project run is low single-digit USD (RESEARCH §4 cost model); the
#   two gating projects run TWICE for the reproducibility check. Expect
#   roughly $5-15 per full gate run. Pass --budget USD to cap each run
#   (threaded to RunSettings via API_BUDGET_PER_RUN_USD). A cost-regression
#   check warns (never fails) when a project's run cost exceeds 2x the
#   recorded baseline in scripts/.cost_baseline.json (delete that file to
#   re-baseline).
#
# LEARNING ISOLATION (why LEARNING_DB_PATH is exported below):
#   The pipeline retrieves learned hints (vocabulary, scale priors, wall
#   heights) from the learning DB at run start (21-16). Corrections
#   accumulated in the dev output/learning.db would inject learned hints
#   into gate runs, silently turning "plans-only" scores into
#   learning-assisted, machine-dependent numbers. Exporting LEARNING_DB_PATH
#   to a fresh temp DB per gate run guarantees every score is a
#   cold-pipeline, machine-independent measurement.
#   Use --with-learning to deliberately skip the isolation: results are then
#   labeled "learned-assisted", run as tracking-only, and NEVER gate.
#
# Usage:
#   bash scripts/accuracy_gate.sh [--budget USD] [--with-learning]
# ============================================================================
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

WITH_LEARNING=0
BUDGET=""
while [ $# -gt 0 ]; do
  case "$1" in
    --with-learning) WITH_LEARNING=1 ;;
    --budget) shift; BUDGET="${1:-}" ;;
    -h|--help)
      sed -n '2,45p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown argument: $1 (see --help)"; exit 2 ;;
  esac
  shift
done

if [ "$WITH_LEARNING" -eq 0 ]; then
  # Fresh, empty learning DB per gate run — cold-pipeline scores only (see
  # LEARNING ISOLATION in the header for why this must happen before any
  # benchmark invocation).
  export LEARNING_DB_PATH="$(mktemp -d)/gate_learning.db"
  MODE_LABEL="cold-pipeline"
  echo "Learning isolation: LEARNING_DB_PATH=$LEARNING_DB_PATH (fresh temp DB)"
else
  MODE_LABEL="learned-assisted"
  echo "WARNING: --with-learning — dev learning.db hints WILL influence results."
  echo "         All runs are tracking-only in this mode; nothing gates."
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="$ROOT/reports/accuracy_gate/$STAMP"
mkdir -p "$REPORT_DIR"
echo "Reports: $REPORT_DIR"

GATE_FAIL=0

# run_bench <name> <plans-pdf> <takeoff-pdf> <gate|track>
run_bench() {
  name="$1"; plans="$2"; takeoff="$3"; mode="$4"
  safe="$(printf '%s' "$name" | tr ' /' '__')"
  echo ""
  echo "=== [$name] mode=$mode ($MODE_LABEL) ==="
  if [ ! -f "$plans" ] || [ ! -f "$takeoff" ]; then
    echo "MISSING INPUT: plans='$plans' takeoff='$takeoff'"
    if [ "$mode" = "gate" ] && [ "$WITH_LEARNING" -eq 0 ]; then GATE_FAIL=1; fi
    return
  fi

  set -- --name "$name" \
         --plans-pdf "$plans" \
         --takeoff-pdf "$takeoff" \
         --report-json "$REPORT_DIR/$safe.json"
  if [ -n "$BUDGET" ]; then set -- "$@" --budget "$BUDGET"; fi
  if [ "$mode" = "gate" ] && [ "$WITH_LEARNING" -eq 0 ]; then
    # Hard gate: default thresholds + two-run reproducibility (double cost).
    set -- "$@" --repro
  else
    # Chelsea/Moxy tracking, and every learned-assisted run: never fails.
    set -- "$@" --tracking-only
  fi

  python3 "$ROOT/scripts/vision_only_benchmark.py" "$@"
  rc=$?
  if [ "$mode" = "gate" ] && [ "$WITH_LEARNING" -eq 0 ] && [ $rc -ne 0 ]; then
    echo "[$name] GATE FAILED (exit $rc)"
    GATE_FAIL=1
  fi
}

# The four uploads/ pairs — exact filenames per 21-CONTEXT (note the spaces,
# the apostrophe in Bob's, and the "Take offds" typo which is in the real
# ground-truth filename).
run_bench "Crow Cass" \
  "uploads/Crow - Cass White Road-Plans.pdf" \
  "uploads/Crow - Cass White Road-Take offs.pdf" \
  gate

run_bench "Bobs Discount" \
  "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf" \
  "uploads/Bob's Discount Furniture - Kennesaw, GA-Take offds.pdf" \
  gate

run_bench "Chelsea Bear Creek" \
  "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf" \
  "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-take offs.pdf" \
  track

run_bench "Moxy Knoxville" \
  "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf" \
  "uploads/Moxy Knoxville - Addendum A City Comment Revision-Take offs.pdf" \
  track

# ── Cost regression check (warn, never fail) + final summary table ─────────
python3 - "$REPORT_DIR" "$ROOT/scripts/.cost_baseline.json" "$MODE_LABEL" <<'PY'
import json
import sys
from pathlib import Path

report_dir = Path(sys.argv[1])
baseline_path = Path(sys.argv[2])
mode_label = sys.argv[3]

try:
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
except Exception:
    baseline = {}

def pct(x):
    return "{:.0%}".format(x) if isinstance(x, (int, float)) else "n/a"

rows = []
warnings = []
new_baseline_entries = {}
for rj in sorted(report_dir.glob("*.json")):
    try:
        data = json.loads(rj.read_text())
    except Exception as exc:
        warnings.append("unreadable report {}: {}".format(rj.name, exc))
        continue
    name = data.get("name", rj.stem)
    sc = data.get("score") or {}
    gates = data.get("gates") or {}
    repro = data.get("reproducibility")
    cost = float(data.get("cost_total_usd") or 0)
    tracking = bool(data.get("tracking_only"))

    if mode_label == "learned-assisted":
        verdict = "LEARNED-ASSISTED"
    elif tracking:
        verdict = "TRACKED"
    else:
        verdict = "PASS" if gates.get("passed") else "FAIL"

    misses = sc.get("silent_misses")
    rows.append((
        name,
        verdict,
        pct(sc.get("overall_qty")),
        pct(sc.get("geometry_text_qty_acc")),
        pct(sc.get("name_found_rate")),
        str(len(misses)) if misses is not None else "n/a",
        pct(sc.get("vision_qty_share")),
        ("{:.3f}".format(repro["max_delta"]) if repro and repro.get("max_delta") is not None else "-"),
        "${:.2f}".format(cost),
    ))

    # Cost regression: warn when > 2x recorded baseline; record when absent.
    base = baseline.get(name)
    if base is None:
        if cost > 0:
            new_baseline_entries[name] = round(cost, 4)
    elif base > 0 and cost > 2.0 * float(base):
        warnings.append(
            "COST REGRESSION: {} cost ${:.2f} > 2x baseline ${:.2f}".format(name, cost, float(base))
        )

if new_baseline_entries:
    baseline.update(new_baseline_entries)
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n")
    warnings.append(
        "cost baseline recorded for: {} -> {}".format(
            ", ".join(sorted(new_baseline_entries)), baseline_path.name)
    )

hdr = ("PROJECT", "VERDICT", "OVERALL", "GEOM/TEXT", "FOUND", "SILENT", "VISION%", "REPRO_MAXD", "COST")
widths = [max(len(str(r[i])) for r in rows + [hdr]) for i in range(len(hdr))] if rows else [len(h) for h in hdr]
line = "  ".join(h.ljust(w) for h, w in zip(hdr, widths))
print("")
print("=" * len(line))
print("ACCURACY GATE SUMMARY ({})".format(mode_label))
print("=" * len(line))
print(line)
print("-" * len(line))
for r in rows:
    print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))
if not rows:
    print("(no report JSONs produced — every run failed before scoring)")
for w in warnings:
    print("! " + w)
PY

echo ""
if [ "$WITH_LEARNING" -eq 1 ]; then
  echo "learned-assisted tracking run complete (never gating) — exit 0"
  exit 0
fi
if [ "$GATE_FAIL" -ne 0 ]; then
  echo "ACCURACY GATE: FAILED (Crow/Bob hard gate)"
  exit 1
fi
echo "ACCURACY GATE: PASSED (Crow+Bob); Chelsea+Moxy tracked"
exit 0
