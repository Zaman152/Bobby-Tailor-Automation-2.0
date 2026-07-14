"""Scale, verify, measurements, and calibration routes.

Learning capture (V3-LEARN-01): every human verification through these
endpoints ALSO feeds the durable learning store in the same request — the
per-run JSON files remain the source of truth for the run, and the store
insert is strictly additive (a capture failure never rolls back the JSON
write or changes the response).

Scope mapping (endpoint → ``learning_corrections.scope``):

    POST /verify        → 'item'  (or 'unit' when only the unit changed;
                          'missed_item' when the item was absent from the
                          summary — the human added something the system
                          missed)
    POST /verify-batch  → per-entry 'item' (same 'missed_item' rule)
    POST /scale         → 'scale' — one correction per overridden sheet,
                          corrected value ``{"fpi": <feet_per_inch>}``
    POST /measurements  → 'wall_height' for wall_area measurements,
                          'item' for count/length/area measurements

No new endpoints, no URL changes; ``learning_warning`` is the only
(additive, optional) response field introduced.
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request
from flask_login import login_required

from bobbytailor import config

logger = logging.getLogger(__name__)

verify_bp = Blueprint("verify", __name__)


# ---------------------------------------------------------------------------
# Learning capture (V3-LEARN-01) — same-request feed into the durable store.
# ---------------------------------------------------------------------------

def _normalize_project_key(name) -> str:
    """Store project_key: lowercase, non-alphanumeric runs collapsed to '-'."""
    key = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return key or "unknown-project"


def _project_identity(run_folder: str):
    """``(project_key, project_type)`` resolved from the run's takeoff.json.

    ``project_key`` is the normalized project name; falls back to the
    normalized run folder name when takeoff.json is missing (scale-only
    runs). ``project_type`` comes from takeoff.json when present, else None.
    """
    name = None
    project_type = None
    tk = Path(config.OUTPUT_DIR) / run_folder / "takeoff.json"
    if tk.is_file():
        try:
            report = json.loads(tk.read_text(encoding="utf-8"))
            name = report.get("project_name")
            project_type = report.get("project_type")
        except (json.JSONDecodeError, OSError):
            pass
    return _normalize_project_key(name or run_folder), project_type


def _plausibility_warning(corrected_value) -> Optional[str]:
    """RESEARCH Pitfall 8: warn on out-of-band corrected quantities.

    Reuses QuantityVerifier's per-unit sanity bounds (imported, not copied)
    so capture-time plausibility stays in lockstep with pipeline
    verification. The correction persists regardless — the human is
    authoritative — but the response carries the warning so the UI can
    prompt a re-check.
    """
    if not isinstance(corrected_value, dict):
        return None
    qty = corrected_value.get("quantity")
    unit = str(corrected_value.get("unit") or "").strip().lower().rstrip(".")
    if qty is None or not unit:
        return None
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return None
    try:
        from bobbytailor.pipeline.takeoff_pipeline import QuantityVerifier
        rule = QuantityVerifier._RULES.get(unit)
    except Exception:  # noqa: BLE001 - plausibility is advisory, never fatal
        return None
    if rule is None:
        return None
    if q < rule["min"] or q > rule["max"]:
        return ("corrected value outside plausible range for %s — double-check"
                % unit.upper())
    return None


def _capture_learning(
    run_folder: str,
    scope: str,
    item_pattern: Optional[str],
    original_value,
    corrected_value,
    extra_context: Optional[dict] = None,
) -> Optional[str]:
    """Record one human correction in the durable learning store (best-effort).

    Resolves project_key/project_type from the run's takeoff.json (falling
    back to the run folder name), inserts via ``record_correction``, and
    triggers an incremental ``distill()`` pass — all in the current request.
    ``sheet_type`` is taken from ``extra_context`` when the correction is
    sheet-scoped. Returns a plausibility warning string (RESEARCH Pitfall 8)
    or None. NEVER raises: the per-run JSON write has already succeeded and
    must not be rolled back by a learning error — failures are logged and
    swallowed (response stays 200, without a warning).
    """
    try:
        from bobbytailor.learning import distill as learning_distill
        from bobbytailor.learning import store as learning_store

        project_key, project_type = _project_identity(run_folder)
        context = dict(extra_context or {})
        sheet_type = context.pop("sheet_type", None)
        learning_store.record_correction(
            run_id=run_folder,
            project_key=project_key,
            project_type=project_type,
            sheet_type=sheet_type,
            scope=scope,
            item_pattern=item_pattern,
            original_value=original_value,
            corrected_value=corrected_value,
            context=context or None,
        )
        learning_distill.distill()
    except Exception:  # noqa: BLE001 - capture is additive, never fatal
        logger.exception(
            "learning capture failed (run=%s scope=%s)", run_folder, scope)
        return None
    return _plausibility_warning(corrected_value)


def _current_summary_row(run_folder: str, key: str) -> Optional[dict]:
    """The run's current summary row for *key* (pre-correction state)."""
    tk = Path(config.OUTPUT_DIR) / run_folder / "takeoff.json"
    if not tk.is_file():
        return None
    try:
        report = json.loads(tk.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    for row in report.get("takeoff_summary") or []:
        if str(row.get("item", "")).strip().lower() == key:
            return row
    return None


def _capture_item_override(
    run_folder: str, ov: dict, prior_row: Optional[dict]
) -> Optional[str]:
    """Map one verified override to its learning correction (scope table above)."""
    item = ov.get("item") or ""
    key = str(item).strip().lower()
    context = {
        "provenance": (prior_row or {}).get("source"),
        "confidence": (prior_row or {}).get("confidence"),
        "note": ov.get("note") or None,
    }
    context = {k: v for k, v in context.items() if v is not None}
    qty = ov.get("quantity")
    unit = ov.get("unit") or ""
    if prior_row is None:
        # Human added an item the system missed entirely.
        return _capture_learning(
            run_folder, scope="missed_item", item_pattern=key,
            original_value=None,
            corrected_value={"item_name": item, "quantity": qty, "unit": unit},
            extra_context=context,
        )
    prior_qty = _row_qty_num(prior_row)
    prior_unit = prior_row.get("unit") or ""
    if qty is None and unit and unit.upper() != str(prior_unit).upper():
        # Only the unit changed → teach the unit mapping.
        return _capture_learning(
            run_folder, scope="unit", item_pattern=key,
            original_value={"unit": prior_unit},
            corrected_value={"unit": unit},
            extra_context=context,
        )
    # Quantity correction, or a confirmation pinning the current value.
    corrected_qty = qty if qty is not None else prior_qty
    return _capture_learning(
        run_folder, scope="item", item_pattern=key,
        original_value={"quantity": prior_qty, "unit": prior_unit},
        corrected_value={"quantity": corrected_qty, "unit": unit or prior_unit},
        extra_context=context,
    )


def _measurement_key(m: dict):
    """Identity key for diffing measurement saves (id wins, else composite)."""
    if m.get("id"):
        return ("id", m["id"])
    return (
        str(m.get("item") or "").strip().lower(),
        m.get("sheet") or "",
        m.get("measure_type") or "",
    )


def _capture_measurement_corrections(
    run_folder: str, previous: list, cleaned: list
) -> Optional[str]:
    """Diff-based capture: record only NEW or CHANGED verified measurements.

    The measurements POST replaces the whole list on every save; diffing
    against the previously persisted list keeps repeated saves from
    re-recording identical corrections (feedback-amplification hygiene,
    RESEARCH Pitfall 8). wall_area measurements teach the wall-height
    assumption (scope 'wall_height'); count/length/area teach item
    quantities (scope 'item').
    """
    prev_by_key = {_measurement_key(m): m for m in previous}
    warnings = []
    for m in cleaned:
        if not m.get("verified", True):
            continue
        qty = m.get("quantity")
        if qty is None:
            continue
        prev = prev_by_key.get(_measurement_key(m))
        item = (m.get("item") or "").strip()
        context = {
            "sheet": m.get("sheet"),
            "measure_type": m.get("measure_type"),
            "feet_per_inch": m.get("feet_per_inch"),
            "provenance": m.get("source"),
        }
        if m.get("measure_type") == "wall_area":
            height = m.get("height_ft")
            if height in (None, 0, ""):
                continue
            prev_height = prev.get("height_ft") if prev is not None else None
            if prev is not None and prev_height == height:
                continue  # unchanged assumption — nothing new to learn
            context["item"] = item
            warning = _capture_learning(
                run_folder, scope="wall_height", item_pattern=None,
                original_value=(
                    {"height_ft": prev_height} if prev is not None else None),
                corrected_value=float(height),
                extra_context=context,
            )
        else:
            if (prev is not None and prev.get("quantity") == qty
                    and (prev.get("unit") or "") == (m.get("unit") or "")):
                continue  # unchanged measurement — already captured
            warning = _capture_learning(
                run_folder, scope="item", item_pattern=item.lower() or None,
                original_value=(
                    {"quantity": prev.get("quantity"), "unit": prev.get("unit")}
                    if prev is not None else None),
                corrected_value={"quantity": qty, "unit": m.get("unit") or ""},
                extra_context=context,
            )
        if warning and warning not in warnings:
            warnings.append(warning)
    return "; ".join(warnings) if warnings else None


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
            from bobbytailor.pipeline.reporter import enrich_scale_calibration
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

    # Snapshot pre-override sheet state (the learning capture "original").
    prior_sheets = {
        s.get("sheet"): {
            "feet_per_inch": s.get("feet_per_inch"),
            "scale_source": s.get("scale_source"),
            "scale_confidence": s.get("scale_confidence"),
            "type": s.get("type"),
        }
        for s in (calib.get("sheets") or [])
    }

    from bobbytailor.deterministic.scale_recalc import apply_overrides
    calib = apply_overrides(calib, overrides)

    try:
        (sub / "scale_calibration.json").write_text(
            json.dumps(calib, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error(f"Failed to persist scale calibration: {e}")
        return jsonify({"error": "Failed to save"}), 500

    # Learning capture (V3-LEARN-01): one 'scale' correction per sheet whose
    # scale actually changed (mirrors apply_overrides validation).
    learning_warning = None
    for sheet_name, value in overrides.items():
        prior = prior_sheets.get(sheet_name)
        if prior is None or not value:
            continue
        try:
            fpi = float(value)
        except (TypeError, ValueError):
            continue
        if fpi <= 0:
            continue
        warning = _capture_learning(
            run_folder, scope="scale", item_pattern=sheet_name,
            original_value={"fpi": prior["feet_per_inch"]},
            corrected_value={"fpi": fpi},
            extra_context={
                "sheet": sheet_name,
                "sheet_type": prior.get("type"),
                "scale_source": prior.get("scale_source"),
                "scale_confidence": prior.get("scale_confidence"),
            },
        )
        learning_warning = learning_warning or warning

    calib["supported"] = True
    if learning_warning:
        calib["learning_warning"] = learning_warning
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
    from bobbytailor.deterministic import takeoff_measurements as tm
    from bobbytailor.pipeline.reporter import _write_takeoff_summary_csv
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

    from bobbytailor.deterministic import takeoff_measurements as tm
    data = request.json or {}
    incoming = data.get("measurements")
    if not isinstance(incoming, list):
        return jsonify({"error": "measurements must be a list"}), 400

    # Previously persisted list — the diff base for learning capture.
    previous = _load_measurements(run_folder)

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

    # Learning capture (V3-LEARN-01): new/changed verified measurements only.
    learning_warning = _capture_measurement_corrections(
        run_folder, previous, cleaned)

    resp = {"run_folder": run_folder, "measurements": cleaned,
            "aggregate": tm.aggregate_measurements(cleaned)}
    if learning_warning:
        resp["learning_warning"] = learning_warning
    return jsonify(resp)


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

    # Pre-correction summary row — the learning capture "original".
    prior_row = None if data.get("clear") else _current_summary_row(run_folder, key)

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

    # Learning capture (V3-LEARN-01): a verified human override is a
    # correction; clears and explicit un-verifications are not.
    learning_warning = None
    if not data.get("clear") and store.get(key, {}).get("verified"):
        learning_warning = _capture_item_override(run_folder, store[key], prior_row)

    summary = _rebuild_summary(run_folder)
    verified = sum(1 for r in summary
                   if not r.get("needs_review") and r.get("quantity") not in (None, "—"))
    total = len(summary)
    resp = {"run_folder": run_folder, "takeoff_summary": summary,
            "verified_count": verified, "total": total}
    if learning_warning:
        resp["learning_warning"] = learning_warning
    return jsonify(resp)


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

    applied, skipped_no_value, capture_jobs = [], [], []
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
        if verified:
            capture_jobs.append((dict(store[key]), by_name.get(key)))

    try:
        p.write_text(json.dumps({"run_folder": run_folder, "overrides": store},
                                indent=2), encoding="utf-8")
    except OSError as e:
        logger.error(f"Failed to persist verify overrides: {e}")
        return jsonify({"error": "Failed to save"}), 500

    # Learning capture (V3-LEARN-01): one correction per applied entry.
    warnings = []
    for ov, prior_row in capture_jobs:
        warning = _capture_item_override(run_folder, ov, prior_row)
        if warning and warning not in warnings:
            warnings.append(warning)

    summary = _rebuild_summary(run_folder)
    resp = {"run_folder": run_folder, "takeoff_summary": summary,
            "applied": applied, "skipped_no_value": skipped_no_value,
            **_summary_counts(summary)}
    if warnings:
        resp["learning_warning"] = "; ".join(warnings)
    return jsonify(resp)


@verify_bp.route("/api/reports/<run_folder>/calibrate", methods=["POST"])
@login_required
def calibrate_scale(run_folder: str):
    """Two-point scale calibration → feet_per_inch from a known real distance.

    Body: ``{"p1": [x,y], "p2": [x,y], "real_feet": <float>}`` (points in PDF
    point space). Returns ``{"feet_per_inch": <float>}`` or 400 if degenerate.
    """
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400
    from bobbytailor.deterministic import takeoff_measurements as tm
    data = request.json or {}
    try:
        p1 = data["p1"]; p2 = data["p2"]; real_feet = float(data["real_feet"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "p1, p2, real_feet required"}), 400
    fpi = tm.calibrate_two_point(p1, p2, real_feet)
    if fpi is None:
        return jsonify({"error": "Degenerate calibration"}), 400
    return jsonify({"feet_per_inch": fpi})

