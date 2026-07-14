"""Endpoint → learning_corrections capture tests (V3-LEARN-01, plan 21-09).

Proves the human-verification capture surface (verify / verify-batch /
scale / measurements) feeds the durable learning store in the same request:
rows round-trip, implausible corrections warn but persist, store failures
are isolated (endpoint stays 200), and captured rows survive run-folder
deletion. Uses the authenticated test-client pattern from
tests/test_scale_module.py and the tmp-DB monkeypatch pattern from
tests/test_learning_store.py.
"""
import json
import os
import shutil
from pathlib import Path
from unittest import mock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxnRp2./WyH1K8LK7xJQZHQKHQKHQ",
)

from bobbytailor.learning import store  # noqa: E402
from bobbytailor.web.app import create_app  # noqa: E402

RUN = "Endpoint_Proj_20260101_000000"


@pytest.fixture()
def learning_db(tmp_path, monkeypatch):
    """Isolated tmp learning DB per test (21-04 fixture pattern)."""
    db_path = tmp_path / "learning.db"
    monkeypatch.setattr(store, "LEARNING_DB_PATH", db_path)
    monkeypatch.setattr(store, "_initialized_for", None)
    return db_path


@pytest.fixture()
def run_dir(tmp_path, monkeypatch):
    """Tmp OUTPUT_DIR with a seeded run folder (takeoff.json + calibration)."""
    from bobbytailor import config

    out = tmp_path / "output"
    run = out / RUN
    run.mkdir(parents=True)
    monkeypatch.setattr(config, "OUTPUT_DIR", str(out))

    report = {
        "project_name": "Endpoint Proj",
        "project_type": "industrial",
        "takeoff_summary": [
            {"item": "Gas Piping", "quantity": 5000, "quantity_fmt": "5,000",
             "unit": "LF", "confidence": "low", "needs_review": True,
             "review_reasons": ["vision estimate"], "source": "vision",
             "source_sheets": ["A2.1"], "line_count": 1, "detail": []},
            {"item": "Bollards", "quantity": 17, "quantity_fmt": "17",
             "unit": "EA", "confidence": "medium", "needs_review": True,
             "review_reasons": ["count estimate"], "source": "vision",
             "source_sheets": ["A2.1"], "line_count": 1, "detail": []},
            {"item": "Doors-HM", "quantity": 12, "quantity_fmt": "12",
             "unit": "EA", "confidence": "high", "needs_review": False,
             "review_reasons": [], "source": "vision",
             "source_sheets": ["A2.1"], "line_count": 1, "detail": []},
        ],
    }
    (run / "takeoff.json").write_text(json.dumps(report), encoding="utf-8")

    from bobbytailor.deterministic.scale_recalc import recompute
    raw = {"footprint_pt2": 720 * 360, "total_linework_pt": 1000.0,
           "long_run_pt": 600.0, "width_pt": 720.0, "height_pt": 360.0}
    calib = {"project_name": "Endpoint Proj", "run_folder": RUN,
             "sheets": [{
                 "sheet": "A2.1", "page_id": 3, "type": "floor_plan",
                 "image": "screenshots/x/page_0003.png",
                 "scale_text": "1/4\" = 1'-0\"", "feet_per_inch": 48,
                 "scale_confidence": "low", "scale_source": "printed_scale",
                 "raw": raw, "measured": recompute(raw, 48)}]}
    (run / "scale_calibration.json").write_text(json.dumps(calib),
                                                encoding="utf-8")
    return run


@pytest.fixture()
def client(run_dir, learning_db):
    """Authenticated Flask test client (CSRF disabled per existing pattern)."""
    from bobbytailor.web.auth import get_admin

    # create_app() runs init_admin(), populating the singleton get_admin()
    # returns — so build the app BEFORE resolving the admin user.
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with mock.patch("flask_login.utils._get_user", return_value=get_admin()):
        yield app.test_client()


# ---------------------------------------------------------------------------
# 1. POST /verify — item correction → one scope='item' row, round-trip.
# ---------------------------------------------------------------------------

def test_verify_item_correction_captured(client):
    resp = client.post(
        f"/api/reports/{RUN}/verify",
        json={"item": "Gas Piping", "quantity": 120, "unit": "LF"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["run_folder"] == RUN  # existing response shape preserved
    assert "takeoff_summary" in data and "verified_count" in data
    assert "learning_warning" not in data  # 120 LF is in-band

    rows = store.get_corrections(scope="item")
    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == RUN
    assert row["project_key"] == "endpoint-proj"
    assert row["project_type"] == "industrial"
    assert row["item_pattern"] == "gas piping"
    assert row["corrected_value"] == {"quantity": 120.0, "unit": "LF"}
    assert row["original_value"]["quantity"] == 5000.0
    assert row["context"]["provenance"] == "vision"


# ---------------------------------------------------------------------------
# 2. POST /scale — scope='scale' row with fpi in corrected_value.
# ---------------------------------------------------------------------------

def test_scale_override_captured(client):
    resp = client.post(
        f"/api/reports/{RUN}/scale", json={"overrides": {"A2.1": 24}})
    assert resp.status_code == 200
    assert resp.get_json()["sheets"][0]["feet_per_inch"] == 24

    rows = store.get_corrections(scope="scale")
    assert len(rows) == 1
    row = rows[0]
    assert row["corrected_value"] == {"fpi": 24.0}
    assert row["original_value"] == {"fpi": 48}
    assert row["sheet_type"] == "floor_plan"
    assert row["context"]["scale_source"] == "printed_scale"
    assert row["context"]["scale_confidence"] == "low"

    # Distill fired in-request: the scale assumption is retrievable.
    assumptions = {a["key"]: a["value"]
                   for a in store.get_assumptions("endpoint-proj", "industrial")}
    assert assumptions["scale_fpi:a2.1"] == {"fpi": 24.0}


# ---------------------------------------------------------------------------
# 3. POST /verify-batch — 3 entries → 3 rows.
# ---------------------------------------------------------------------------

def test_verify_batch_captures_one_row_per_entry(client):
    resp = client.post(
        f"/api/reports/{RUN}/verify-batch",
        json={"items": [
            {"item": "Gas Piping", "quantity": 130, "unit": "LF"},
            {"item": "Bollards", "quantity": 20, "unit": "EA"},
            {"item": "Doors-HM"},  # confirm at current value (12 EA)
        ]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert sorted(data["applied"]) == ["Bollards", "Doors-HM", "Gas Piping"]

    rows = store.get_corrections(scope="item")
    assert len(rows) == 3
    by_pattern = {r["item_pattern"]: r for r in rows}
    assert by_pattern["gas piping"]["corrected_value"]["quantity"] == 130.0
    assert by_pattern["bollards"]["corrected_value"]["quantity"] == 20.0
    # Confirmation pins the current best estimate.
    assert by_pattern["doors-hm"]["corrected_value"]["quantity"] == 12.0


# ---------------------------------------------------------------------------
# 4. Implausible quantity → 200 + learning_warning AND the row persists.
# ---------------------------------------------------------------------------

def test_implausible_quantity_warns_but_persists(client):
    # EA rule max is 5,000 — 22,040 EA is out-of-band (typo scenario,
    # RESEARCH Pitfall 8).
    resp = client.post(
        f"/api/reports/{RUN}/verify",
        json={"item": "Bollards", "quantity": 22040, "unit": "EA"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "learning_warning" in data
    assert "plausible range" in data["learning_warning"]
    assert "EA" in data["learning_warning"]

    # Human is authoritative: the row persisted despite the warning.
    rows = store.get_corrections(scope="item", item_pattern="bollards")
    assert len(rows) == 1
    assert rows[0]["corrected_value"]["quantity"] == 22040.0


# ---------------------------------------------------------------------------
# 5. Store failure isolation — endpoint stays 200, run JSON still written.
# ---------------------------------------------------------------------------

def test_store_failure_does_not_break_endpoint(client, run_dir, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("learning store down")

    monkeypatch.setattr(store, "record_correction", boom)

    resp = client.post(
        f"/api/reports/{RUN}/verify",
        json={"item": "Gas Piping", "quantity": 150, "unit": "LF"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "learning_warning" not in data  # capture failed → no warning

    # The per-run JSON write (source of truth) still happened.
    overrides = json.loads(
        (run_dir / "verification_overrides.json").read_text(encoding="utf-8"))
    assert overrides["overrides"]["gas piping"]["quantity"] == 150.0
    # And the summary override applied.
    row = next(r for r in data["takeoff_summary"]
               if r["item"].lower() == "gas piping")
    assert row["quantity"] == 150.0
    assert row["source"] == "user_verified"


# ---------------------------------------------------------------------------
# 6. Survival — rows queryable after the run folder is deleted.
# ---------------------------------------------------------------------------

def test_capture_survives_run_folder_deletion(client, run_dir):
    resp = client.post(
        f"/api/reports/{RUN}/verify",
        json={"item": "Gas Piping", "quantity": 120, "unit": "LF"})
    assert resp.status_code == 200

    shutil.rmtree(run_dir)
    assert not run_dir.exists()

    rows = store.get_corrections(run_id=RUN)
    assert len(rows) == 1
    assert rows[0]["corrected_value"] == {"quantity": 120.0, "unit": "LF"}


# ---------------------------------------------------------------------------
# 7. Missed item — verifying an item the system never produced.
# ---------------------------------------------------------------------------

def test_verify_unknown_item_captured_as_missed_item(client):
    resp = client.post(
        f"/api/reports/{RUN}/verify",
        json={"item": "Tilt-Up Wall", "quantity": 8000, "unit": "SF"})
    assert resp.status_code == 200

    rows = store.get_corrections(scope="missed_item")
    assert len(rows) == 1
    assert rows[0]["item_pattern"] == "tilt-up wall"
    assert rows[0]["corrected_value"]["item_name"] == "Tilt-Up Wall"
    assert rows[0]["original_value"] is None

    # Distill fired: the missed item enters the project-type manifest.
    manifest = {m["item_name"] for m in store.get_manifest("industrial")}
    assert "Tilt-Up Wall" in manifest


# ---------------------------------------------------------------------------
# 8. Measurements — wall_area teaches wall_height; repeated saves don't
#    re-record identical corrections (diff-based capture).
# ---------------------------------------------------------------------------

def test_measurements_capture_wall_height_and_item(client):
    measurements = [
        {"item": "CMU Wall", "unit": "SF", "measure_type": "wall_area",
         "sheet": "A2.1", "points_pt": [[0, 0], [100, 0]],
         "feet_per_inch": 48, "height_ft": 10, "verified": True},
        {"item": "Gas Piping", "unit": "LF", "measure_type": "length",
         "sheet": "A2.1", "points_pt": [[0, 0], [100, 0]],
         "feet_per_inch": 48, "verified": True},
    ]
    resp = client.post(
        f"/api/reports/{RUN}/measurements",
        json={"measurements": measurements})
    assert resp.status_code == 200

    wall_rows = store.get_corrections(scope="wall_height")
    assert len(wall_rows) == 1
    assert wall_rows[0]["corrected_value"] == 10.0
    assert wall_rows[0]["context"]["item"] == "CMU Wall"

    item_rows = store.get_corrections(scope="item")
    assert len(item_rows) == 1
    assert item_rows[0]["item_pattern"] == "gas piping"
    # 100pt at 48 ft/in → 100 * 48 / 72 = 66.67 LF exactly.
    assert item_rows[0]["corrected_value"]["quantity"] == pytest.approx(66.67)

    # Re-saving the identical list records nothing new (Pitfall 8 hygiene).
    saved = resp.get_json()["measurements"]
    resp2 = client.post(
        f"/api/reports/{RUN}/measurements", json={"measurements": saved})
    assert resp2.status_code == 200
    assert len(store.get_corrections(scope="wall_height")) == 1
    assert len(store.get_corrections(scope="item")) == 1

    # Distill fired: wall height is now a retrievable assumption.
    assumptions = {a["key"]: a["value"]
                   for a in store.get_assumptions("endpoint-proj", "industrial")}
    assert assumptions["wall_height_ft"] == 10.0


# ---------------------------------------------------------------------------
# 9. Unit-only change → scope='unit' (teaches the unit mapping).
# ---------------------------------------------------------------------------

def test_verify_unit_only_change_captured_as_unit_scope(client):
    resp = client.post(
        f"/api/reports/{RUN}/verify",
        json={"item": "Gas Piping", "unit": "EA"})
    assert resp.status_code == 200

    rows = store.get_corrections(scope="unit")
    assert len(rows) == 1
    assert rows[0]["item_pattern"] == "gas piping"
    assert rows[0]["corrected_value"] == {"unit": "EA"}
    assert rows[0]["original_value"] == {"unit": "LF"}
