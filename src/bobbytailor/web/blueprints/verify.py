"""Scale, verify, measurements, and calibration routes."""
import json
import logging
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request
from flask_login import login_required

import config

logger = logging.getLogger(__name__)

verify_bp = Blueprint("verify", __name__)


def _load_scale_calibration(run_folder: str) -> Optional[dict]:
    """Load a run's scale_calibration.json, falling back to takeoff.json.

    Older runs (before the scale module) only have the calibration embedded in
    takeoff.json; newer runs have a dedicated file. Returns None if neither.
    """
    sub = Path(config.OUTPUT_DIR) / run_folder
    calib_path = sub / "scale_calibration.json"
    if calib_path.is_file():
        try:
            return json.loads(calib_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    tk = sub / "takeoff.json"
    if tk.is_file():
        try:
            data = json.loads(tk.read_text(encoding="utf-8"))
            return data.get("scale_calibration")
        except (json.JSONDecodeError, OSError):
            pass
    return None


@verify_bp.route("/api/reports/<run_folder>/scale", methods=["GET"])
@login_required
def get_scale_calibration(run_folder: str):
    """Return the per-sheet scale calibration table for the Verify module."""
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    if not (Path(config.OUTPUT_DIR) / run_folder).is_dir():
        return jsonify({"error": "Not found"}), 404
    sub = Path(config.OUTPUT_DIR) / run_folder
    calib = _load_scale_calibration(run_folder)
    if calib is None:
        return jsonify({"run_folder": run_folder, "sheets": [],
                        "supported": False})
    tk = sub / "takeoff.json"
    if tk.is_file():
        try:
            report = json.loads(tk.read_text(encoding="utf-8"))
            from reporter import enrich_scale_calibration
            calib = enrich_scale_calibration(calib, report)
        except (json.JSONDecodeError, OSError):
            pass
    calib["supported"] = bool(calib.get("sheets"))
    return jsonify(calib)


@verify_bp.route("/api/reports/<run_folder>/scale", methods=["POST"])
@login_required
def update_scale_calibration(run_folder: str):
    """Apply user-verified per-sheet scales and recompute measured quantities.

    Body: ``{"overrides": {"<sheet>": <feet_per_inch>, ...}}``. Recompute is
    pure deterministic math on stored raw point geometry — no vision re-run.
    Persists the updated calibration so corrections survive a reload.
    """
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    sub = Path(config.OUTPUT_DIR) / run_folder
    if not sub.is_dir():
        return jsonify({"error": "Not found"}), 404

    calib = _load_scale_calibration(run_folder)
    if calib is None or not calib.get("sheets"):
        return jsonify({"error": "No scale-dependent geometry for this run"}), 400

    data = request.json or {}
    overrides = data.get("overrides") or {}
    if not isinstance(overrides, dict):
        return jsonify({"error": "overrides must be an object"}), 400

    from scale_recalc import apply_overrides
    calib = apply_overrides(calib, overrides)

    try:
        (sub / "scale_calibration.json").write_text(
            json.dumps(calib, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error(f"Failed to persist scale calibration: {e}")
        return jsonify({"error": "Failed to save"}), 500

    calib["supported"] = True
    return jsonify(calib)


def _measurements_path(run_folder: str) -> Path:
    return Path(config.OUTPUT_DIR) / run_folder / "takeoff_measurements.json"


def _load_measurements(run_folder: str) -> list:
    p = _measurements_path(run_folder)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("measurements", []) if isinstance(data, dict) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _verify_path(run_folder: str) -> Path:
    return Path(config.OUTPUT_DIR) / run_folder / "verification_overrides.json"


def _load_verify_overrides(run_folder: str) -> dict:
    p = _verify_path(run_folder)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("overrides", {}) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _qty_fmt(qty) -> str:
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return "—"
    return f"{q:,.0f}" if q == int(q) else f"{q:,.1f}"


def _rebuild_summary(run_folder: str) -> dict:
    """Recompute takeoff_summary from base vision + measurements + manual overrides.

    Idempotent and layered (each layer wins over the previous):
      1. ``takeoff_summary_base`` — pristine vision aggregate (captured once).
      2. scale-bound measurements (exact geometry × verified scale).
      3. manual verified overrides (human-entered/confirmed) — always win.

    Rewrites takeoff.json's ``takeoff_summary`` + takeoff_summary.csv. Returns the
    rebuilt summary list.
    """
    import takeoff_measurements as tm
    from reporter import _write_takeoff_summary_csv
    import copy

    sub = Path(config.OUTPUT_DIR) / run_folder
    tk_path = sub / "takeoff.json"
    if not tk_path.is_file():
        return []
    try:
        report = json.loads(tk_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    if "takeoff_summary_base" not in report:
        report["takeoff_summary_base"] = copy.deepcopy(report.get("takeoff_summary") or [])
    summary = copy.deepcopy(report["takeoff_summary_base"])
    by_name = {str(r.get("item", "")).strip().lower(): r for r in summary}

    def _row_for(item_name):
        key = str(item_name).strip().lower()
        row = by_name.get(key)
        if row is None:
            row = {"item": item_name, "detail": [], "source_sheets": []}
            summary.append(row)
            by_name[key] = row
        return row

    # Layer 2 — measurements
    agg = tm.aggregate_measurements(_load_measurements(run_folder))
    for entry in agg.values():
        row = _row_for(entry["item"])
        is_auto = bool(entry.get("auto"))
        row.update({
            "quantity": entry["quantity"],
            "quantity_fmt": _qty_fmt(entry["quantity"]),
            "unit": (entry["unit"] or row.get("unit") or "").upper(),
            "confidence": "high", "needs_review": False, "review_reasons": [],
            "source": "measured_auto" if is_auto else "measured_verified",
            "auto_verified": is_auto,
            "line_count": entry["line_count"],
            "measured_sheets": entry.get("sheets", []),
        })

    # Layer 3 — manual verified overrides (win over everything)
    overrides = _load_verify_overrides(run_folder)
    for key, ov in overrides.items():
        if not ov.get("verified"):
            continue
        row = _row_for(ov.get("item") or key)
        if ov.get("quantity") is not None:
            row["quantity"] = ov["quantity"]
            row["quantity_fmt"] = _qty_fmt(ov["quantity"])
        if ov.get("unit"):
            row["unit"] = ov["unit"].upper()
        row["confidence"] = "high"
        row["needs_review"] = False
        row["review_reasons"] = []
        row["source"] = "user_verified"
        row["auto_verified"] = False  # explicit human confirmation, not auto
        if ov.get("note"):
            row["verify_note"] = ov["note"]

    report["takeoff_summary"] = summary
    try:
        tk_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        _write_takeoff_summary_csv(summary, sub / "takeoff_summary.csv")
    except OSError as e:
        logger.error(f"Failed to rewrite summary: {e}")
    return summary


@verify_bp.route("/api/reports/<run_folder>/measurements", methods=["GET"])
@login_required
def get_measurements(run_folder: str):
    """Return saved scale-bound takeoff measurements for a run."""
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    if not (Path(config.OUTPUT_DIR) / run_folder).is_dir():
        return jsonify({"error": "Not found"}), 404
    return jsonify({"run_folder": run_folder,
                    "measurements": _load_measurements(run_folder)})


@verify_bp.route("/api/reports/<run_folder>/measurements", methods=["POST"])
@login_required
def save_measurements(run_folder: str):
    """Persist measurements, recompute each exactly, and merge into the summary.

    Body: ``{"measurements": [ {item, unit, measure_type, sheet, points_pt,
    feet_per_inch, height_ft?, count?, verified?}, ... ]}``.
    """
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    sub = Path(config.OUTPUT_DIR) / run_folder
    if not sub.is_dir():
        return jsonify({"error": "Not found"}), 404

    import takeoff_measurements as tm
    data = request.json or {}
    incoming = data.get("measurements")
    if not isinstance(incoming, list):
        return jsonify({"error": "measurements must be a list"}), 400

    cleaned = []
    for m in incoming:
        if not isinstance(m, dict) or m.get("measure_type") not in tm.VALID_TYPES:
            continue
        try:
            cleaned.append(tm.recompute_measurement(m))
        except Exception as e:  # noqa: BLE001 - skip malformed rows, keep the rest
            logger.warning(f"Skipping bad measurement: {e}")

    payload = {"run_folder": run_folder, "measurements": cleaned}
    try:
        _measurements_path(run_folder).write_text(
            json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error(f"Failed to persist measurements: {e}")
        return jsonify({"error": "Failed to save"}), 500

    _rebuild_summary(run_folder)
    return jsonify({"run_folder": run_folder, "measurements": cleaned,
                    "aggregate": tm.aggregate_measurements(cleaned)})


@verify_bp.route("/api/reports/<run_folder>/verify", methods=["POST"])
@login_required
def verify_item(run_folder: str):
    """Set/clear a human verified-override for a takeoff item → exact + locked.

    Body: ``{"item": str, "quantity"?: number|null, "unit"?: str,
    "verified"?: bool (default true), "note"?: str, "clear"?: bool}``.
    The override wins over vision + measurements, marking the line verified
    (confidence high, no review). This is the universal path to 100%.
    """
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    sub = Path(config.OUTPUT_DIR) / run_folder
    if not sub.is_dir():
        return jsonify({"error": "Not found"}), 404

    data = request.json or {}
    item = (data.get("item") or "").strip()
    if not item:
        return jsonify({"error": "item required"}), 400
    key = item.lower()

    p = _verify_path(run_folder)
    store = {}
    if p.is_file():
        try:
            store = json.loads(p.read_text(encoding="utf-8")).get("overrides", {})
        except (json.JSONDecodeError, OSError):
            store = {}

    if data.get("clear"):
        store.pop(key, None)
    else:
        qty = data.get("quantity", None)
        if qty is not None:
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                return jsonify({"error": "quantity must be numeric"}), 400
        store[key] = {
            "item": item,
            "quantity": qty,
            "unit": data.get("unit") or "",
            "verified": bool(data.get("verified", True)),
            "note": data.get("note") or "",
        }

    try:
        p.write_text(json.dumps({"run_folder": run_folder, "overrides": store},
                                indent=2), encoding="utf-8")
    except OSError as e:
        logger.error(f"Failed to persist verify overrides: {e}")
        return jsonify({"error": "Failed to save"}), 500

    summary = _rebuild_summary(run_folder)
    verified = sum(1 for r in summary
                   if not r.get("needs_review") and r.get("quantity") not in (None, "—"))
    total = len(summary)
    return jsonify({"run_folder": run_folder, "takeoff_summary": summary,
                    "verified_count": verified, "total": total})


def _row_qty_num(row: dict):
    """Numeric quantity of a summary row, or None when missing/non-numeric."""
    q = row.get("quantity")
    if q in (None, "—", ""):
        return None
    try:
        return float(str(q).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _row_needs_verification(row: dict) -> bool:
    """A line is unproven if flagged for review or it has no usable quantity."""
    if _row_qty_num(row) is None:
        return True
    return bool(row.get("needs_review"))


def _summary_counts(summary: list) -> dict:
    total = len(summary)
    needs = [r for r in summary if _row_needs_verification(r)]
    no_value = [r for r in needs if _row_qty_num(r) is None]
    return {
        "total": total,
        "verified_count": total - len(needs),
        "needs_review": len(needs),
        "needs_value": len(no_value),
        "pct": round((total - len(needs)) / total * 100) if total else 100,
    }


@verify_bp.route("/api/reports/<run_folder>/verify-batch", methods=["POST"])
@login_required
def verify_batch(run_folder: str):
    """Confirm many takeoff lines at once — the fast, robust path to 100%.

    Body (choose one selector):
      {"items": ["Doors", "Stairs"]}                 verify these at current value
      {"items": [{"item","quantity"?,"unit"?,"note"?}]}  verify with explicit values
      {"accept_all_estimates": true}                 verify every unproven line that
                                                     already has a numeric estimate
      {"clear_all": true}                            drop ALL human overrides (reset)
    Optional: "verified": bool (default true), "note": str (applied to all).

    Lines with NO usable quantity are never silently confirmed — they are returned
    in ``skipped_no_value`` so the UI can ask the user to enter a number.
    """
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    sub = Path(config.OUTPUT_DIR) / run_folder
    if not sub.is_dir():
        return jsonify({"error": "Not found"}), 404

    data = request.json or {}
    verified = bool(data.get("verified", True))
    note = data.get("note") or ""

    p = _verify_path(run_folder)
    store = {}
    if p.is_file():
        try:
            store = json.loads(p.read_text(encoding="utf-8")).get("overrides", {})
        except (json.JSONDecodeError, OSError):
            store = {}

    if data.get("clear_all"):
        store = {}
        try:
            p.write_text(json.dumps({"run_folder": run_folder, "overrides": store},
                                    indent=2), encoding="utf-8")
        except OSError as e:
            logger.error(f"Failed to clear verify overrides: {e}")
            return jsonify({"error": "Failed to save"}), 500
        summary = _rebuild_summary(run_folder)
        return jsonify({"run_folder": run_folder, "takeoff_summary": summary,
                        "cleared": True, **_summary_counts(summary)})

    # Need the current state to resolve "current value" / "all estimates".
    current = _rebuild_summary(run_folder)
    by_name = {str(r.get("item", "")).strip().lower(): r for r in current}

    targets: list = []
    if data.get("accept_all_estimates"):
        for r in current:
            if _row_needs_verification(r) and _row_qty_num(r) is not None:
                targets.append({"item": r.get("item")})
    else:
        for it in (data.get("items") or []):
            targets.append({"item": it} if isinstance(it, str) else dict(it))

    applied, skipped_no_value = [], []
    for t in targets:
        item = (t.get("item") or "").strip()
        if not item:
            continue
        key = item.lower()
        row = by_name.get(key, {})
        qty = t.get("quantity", None)
        if qty is not None:
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                continue
        else:
            qty = _row_qty_num(row)  # pin the current best estimate
        if verified and qty is None:
            skipped_no_value.append(item)
            continue
        store[key] = {
            "item": item,
            "quantity": qty,
            "unit": t.get("unit") or (row.get("unit") or ""),
            "verified": verified,
            "note": t.get("note") or note,
        }
        applied.append(item)

    try:
        p.write_text(json.dumps({"run_folder": run_folder, "overrides": store},
                                indent=2), encoding="utf-8")
    except OSError as e:
        logger.error(f"Failed to persist verify overrides: {e}")
        return jsonify({"error": "Failed to save"}), 500

    summary = _rebuild_summary(run_folder)
    return jsonify({"run_folder": run_folder, "takeoff_summary": summary,
                    "applied": applied, "skipped_no_value": skipped_no_value,
                    **_summary_counts(summary)})


@verify_bp.route("/api/reports/<run_folder>/calibrate", methods=["POST"])
@login_required
def calibrate_scale(run_folder: str):
    """Two-point scale calibration → feet_per_inch from a known real distance.

    Body: ``{"p1": [x,y], "p2": [x,y], "real_feet": <float>}`` (points in PDF
    point space). Returns ``{"feet_per_inch": <float>}`` or 400 if degenerate.
    """
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    import takeoff_measurements as tm
    data = request.json or {}
    try:
        p1 = data["p1"]; p2 = data["p2"]; real_feet = float(data["real_feet"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "p1, p2, real_feet required"}), 400
    fpi = tm.calibrate_two_point(p1, p2, real_feet)
    if fpi is None:
        return jsonify({"error": "Degenerate calibration"}), 400
    return jsonify({"feet_per_inch": fpi})

