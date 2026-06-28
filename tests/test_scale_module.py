"""Integration tests for the Scale & Verify module.

Covers: reporter emits scale_calibration.json with scale-independent raw
geometry; the GET/POST scale endpoints read, recompute, and persist.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxnRp2./WyH1K8LK7xJQZHQKHQKHQ",
)

import config
from reporter import generate_report


def _extracted_with_geometry():
    raw = {
        "footprint_pt2": 720 * 360,
        "total_linework_pt": 1000.0,
        "long_run_pt": 600.0,
        "width_pt": 720.0,
        "height_pt": 360.0,
    }
    from scale_recalc import recompute
    return [{
        "_source_sheet": "A2.1",
        "_sheet_name": "A2.1",
        "_sheet_type": "floor_plan",
        "_page_id": 3,
        "scale": "1/4\" = 1'-0\"",
        "_tokens_in": 0, "_tokens_out": 0, "_cost_usd": 0,
        "_geometry": {
            "scale": {"feet_per_point": 48 / 72, "confidence": "low",
                      "method": "printed_scale"},
            "footprint_sf": recompute(raw, 48)["footprint_sf"],
            "total_linework_lf": recompute(raw, 48)["total_linework_lf"],
            "long_run_lf": recompute(raw, 48)["long_run_lf"],
            "confidence": "low",
            "needs_review": True,
            "raw": raw,
        },
    }]


class ScaleCalibrationReporterTests(unittest.TestCase):
    def test_reporter_writes_calibration_with_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = config.OUTPUT_DIR
            config.OUTPUT_DIR = tmp
            try:
                report = generate_report("Scale Proj", _extracted_with_geometry(), [])
                run_dir = Path(report["_files"]["run_folder"])
                calib_path = run_dir / "scale_calibration.json"
                self.assertTrue(calib_path.exists())
                calib = json.loads(calib_path.read_text())
                self.assertEqual(len(calib["sheets"]), 1)
                s = calib["sheets"][0]
                self.assertEqual(s["sheet"], "A2.1")
                self.assertEqual(s["feet_per_inch"], 48)
                self.assertIsNotNone(s["raw"])
                self.assertEqual(s["raw"]["footprint_pt2"], 720 * 360)
                self.assertGreater(s["measured"]["footprint_sf"], 0)
            finally:
                config.OUTPUT_DIR = old


class ScaleEndpointTests(unittest.TestCase):
    def setUp(self):
        from auth import get_admin
        self.tmp = tempfile.TemporaryDirectory()
        self.run = "Endpoint_Proj_20260101_000000"
        self.run_dir = Path(self.tmp.name) / self.run
        self.run_dir.mkdir(parents=True)
        raw = {"footprint_pt2": 720 * 360, "total_linework_pt": 1000.0,
               "long_run_pt": 600.0, "width_pt": 720.0, "height_pt": 360.0}
        from scale_recalc import recompute
        calib = {"project_name": "Endpoint Proj", "run_folder": self.run,
                 "sheets": [{
                     "sheet": "A2.1", "page_id": 3, "type": "floor_plan",
                     "image": "screenshots/x/page_0003.png",
                     "scale_text": "1/4\" = 1'-0\"", "feet_per_inch": 48,
                     "scale_confidence": "low", "scale_source": "printed_scale",
                     "raw": raw, "measured": recompute(raw, 48)}]}
        (self.run_dir / "scale_calibration.json").write_text(json.dumps(calib))

        import app as app_module
        self.patchers = [
            mock.patch.object(app_module, "OUTPUT_DIR", self.tmp.name),
            mock.patch("flask_login.utils._get_user", return_value=get_admin()),
        ]
        for p in self.patchers:
            p.start()
        app_module.app.config["TESTING"] = True
        app_module.app.config["WTF_CSRF_ENABLED"] = False
        self.client = app_module.app.test_client()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_get_scale(self):
        resp = self.client.get(f"/api/reports/{self.run}/scale")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["supported"])
        self.assertEqual(data["sheets"][0]["feet_per_inch"], 48)

    def test_post_override_recomputes_and_persists(self):
        resp = self.client.post(
            f"/api/reports/{self.run}/scale",
            json={"overrides": {"A2.1": 24}},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        s = data["sheets"][0]
        self.assertEqual(s["feet_per_inch"], 24)
        self.assertEqual(s["scale_source"], "user_verified")
        # area scales with the square of the scale: 24 vs 48 → 1/4 the footprint
        from scale_recalc import recompute
        raw = s["raw"]
        self.assertEqual(s["measured"]["footprint_sf"],
                         recompute(raw, 24)["footprint_sf"])
        # persisted to disk
        on_disk = json.loads((self.run_dir / "scale_calibration.json").read_text())
        self.assertEqual(on_disk["sheets"][0]["feet_per_inch"], 24)

    def test_post_rejects_non_object_overrides(self):
        resp = self.client.post(
            f"/api/reports/{self.run}/scale", json={"overrides": [1, 2]})
        self.assertEqual(resp.status_code, 400)

    def test_two_point_calibration_endpoint(self):
        resp = self.client.post(
            f"/api/reports/{self.run}/calibrate",
            json={"p1": [0, 0], "p2": [96, 0], "real_feet": 64})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["feet_per_inch"], 48.0)

    def test_measurements_save_recompute_and_override_summary(self):
        # Seed a takeoff.json with a vision estimate that is WRONG, then prove a
        # verified scale-bound measurement overrides it exactly.
        report = {
            "project_name": "Endpoint Proj",
            "takeoff_summary": [
                {"item": "gas piping", "quantity": 5000, "quantity_fmt": "5,000",
                 "unit": "LF", "confidence": "low", "needs_review": True,
                 "review_reasons": ["vision estimate"], "source": "vision",
                 "source_sheets": ["A2.1"], "line_count": 1, "detail": []},
            ],
        }
        (self.run_dir / "takeoff.json").write_text(json.dumps(report))

        # 100pt line at 48 ft/in → 100*48/72 = 66.67 LF (exact).
        m = {"item": "Gas Piping", "unit": "LF", "measure_type": "length",
             "sheet": "A2.1", "points_pt": [[0, 0], [100, 0]],
             "feet_per_inch": 48, "verified": True}
        resp = self.client.post(
            f"/api/reports/{self.run}/measurements",
            json={"measurements": [m]})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertAlmostEqual(data["aggregate"]["gas piping"]["quantity"],
                               round(100 * 48 / 72, 2), places=2)

        # takeoff.json summary row was overridden + marked measured/verified
        updated = json.loads((self.run_dir / "takeoff.json").read_text())
        row = next(r for r in updated["takeoff_summary"]
                   if r["item"] == "gas piping")
        self.assertEqual(row["source"], "measured_verified")
        self.assertFalse(row["needs_review"])
        self.assertAlmostEqual(row["quantity"], round(100 * 48 / 72, 2), places=2)

        # persisted measurements round-trip via GET
        g = self.client.get(f"/api/reports/{self.run}/measurements").get_json()
        self.assertEqual(len(g["measurements"]), 1)
        self.assertEqual(g["measurements"][0]["item"], "Gas Piping")

    def _seed_summary(self, rows):
        report = {"project_name": "P", "takeoff_summary": rows}
        (self.run_dir / "takeoff.json").write_text(json.dumps(report))

    def test_verify_override_sets_exact_and_locks(self):
        self._seed_summary([
            {"item": "bollards", "quantity": 12, "quantity_fmt": "12", "unit": "EA",
             "confidence": "medium", "needs_review": True, "review_reasons": ["count"],
             "source": "vision", "source_sheets": [], "line_count": 1, "detail": []},
        ])
        resp = self.client.post(
            f"/api/reports/{self.run}/verify",
            json={"item": "Bollards", "quantity": 11, "verified": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        row = next(r for r in data["takeoff_summary"] if r["item"].lower() == "bollards")
        self.assertEqual(row["quantity"], 11)
        self.assertEqual(row["source"], "user_verified")
        self.assertFalse(row["needs_review"])
        self.assertEqual(row["confidence"], "high")

    def test_verify_is_idempotent_and_clearable(self):
        self._seed_summary([
            {"item": "bollards", "quantity": 12, "quantity_fmt": "12", "unit": "EA",
             "confidence": "medium", "needs_review": True, "review_reasons": [],
             "source": "vision", "source_sheets": [], "line_count": 1, "detail": []},
        ])
        # apply twice → same result (idempotent rebuild from base)
        for _ in range(2):
            self.client.post(f"/api/reports/{self.run}/verify",
                             json={"item": "Bollards", "quantity": 11})
        report = json.loads((self.run_dir / "takeoff.json").read_text())
        self.assertEqual(report["takeoff_summary_base"][0]["quantity"], 12)
        row = next(r for r in report["takeoff_summary"] if r["item"].lower() == "bollards")
        self.assertEqual(row["quantity"], 11)
        # clear → reverts to base vision value
        self.client.post(f"/api/reports/{self.run}/verify",
                         json={"item": "Bollards", "clear": True})
        report = json.loads((self.run_dir / "takeoff.json").read_text())
        row = next(r for r in report["takeoff_summary"] if r["item"].lower() == "bollards")
        self.assertEqual(row["quantity"], 12)
        self.assertEqual(row["source"], "vision")

    def test_verify_confirm_without_quantity_keeps_value(self):
        self._seed_summary([
            {"item": "doors", "quantity": 8, "quantity_fmt": "8", "unit": "EA",
             "confidence": "low", "needs_review": True, "review_reasons": ["x"],
             "source": "vision", "source_sheets": [], "line_count": 1, "detail": []},
        ])
        resp = self.client.post(f"/api/reports/{self.run}/verify",
                                json={"item": "Doors", "verified": True})
        row = next(r for r in resp.get_json()["takeoff_summary"]
                   if r["item"].lower() == "doors")
        self.assertEqual(row["quantity"], 8)        # unchanged value
        self.assertFalse(row["needs_review"])       # but now confirmed
        self.assertEqual(row["source"], "user_verified")

    # ── Batch verification (Layer D fast path to 100%) ───────────────────────

    def _seed_mixed(self):
        self._seed_summary([
            {"item": "CMU Wall", "quantity": 105288, "quantity_fmt": "105,288",
             "unit": "SF", "confidence": "low", "needs_review": True,
             "review_reasons": ["approx"], "source": "vision",
             "source_sheets": [], "line_count": 1, "detail": []},
            {"item": "Columns", "quantity": 100, "quantity_fmt": "100", "unit": "EA",
             "confidence": "medium", "needs_review": True, "review_reasons": [],
             "source": "vision", "source_sheets": [], "line_count": 1, "detail": []},
            {"item": "Bollards", "quantity": None, "quantity_fmt": "—", "unit": "EA",
             "confidence": "low", "needs_review": True, "review_reasons": ["missing"],
             "source": "manifest_missing", "source_sheets": [], "line_count": 0,
             "detail": []},
            {"item": "Sealed Concrete", "quantity": 395673, "quantity_fmt": "395,673",
             "unit": "SF", "confidence": "high", "needs_review": False,
             "review_reasons": [], "source": "measured_auto", "auto_verified": True,
             "source_sheets": [], "line_count": 1, "detail": []},
        ])

    def test_batch_accept_all_estimates_reaches_only_valued_lines(self):
        self._seed_mixed()
        resp = self.client.post(
            f"/api/reports/{self.run}/verify-batch",
            json={"accept_all_estimates": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        # CMU Wall + Columns have estimates → confirmed. Bollards has no value, so
        # it is never an "estimate" to accept — it is left for manual entry and
        # surfaced via needs_value (not silently confirmed).
        self.assertIn("CMU Wall", data["applied"])
        self.assertIn("Columns", data["applied"])
        self.assertEqual(data["skipped_no_value"], [])
        rows = {r["item"]: r for r in data["takeoff_summary"]}
        self.assertEqual(rows["CMU Wall"]["source"], "user_verified")
        self.assertFalse(rows["Columns"]["needs_review"])
        # Bollards still unproven (needs a value); progress not yet 100%.
        self.assertTrue(rows["Bollards"]["needs_review"])
        self.assertEqual(data["needs_value"], 1)
        self.assertEqual(data["needs_review"], 1)

    def test_batch_explicit_items_with_values(self):
        self._seed_mixed()
        resp = self.client.post(
            f"/api/reports/{self.run}/verify-batch",
            json={"items": [{"item": "Bollards", "quantity": 28},
                            {"item": "CMU Wall", "quantity": 2204.33}]})
        data = resp.get_json()
        rows = {r["item"]: r for r in data["takeoff_summary"]}
        self.assertEqual(rows["Bollards"]["quantity"], 28)
        self.assertEqual(rows["CMU Wall"]["quantity"], 2204.33)
        self.assertEqual(rows["Bollards"]["source"], "user_verified")

    def test_batch_clear_all_resets_to_base(self):
        self._seed_mixed()
        # confirm everything possible, then reset
        self.client.post(f"/api/reports/{self.run}/verify-batch",
                         json={"items": [{"item": "Bollards", "quantity": 28}]})
        resp = self.client.post(f"/api/reports/{self.run}/verify-batch",
                                json={"clear_all": True})
        data = resp.get_json()
        self.assertTrue(data["cleared"])
        rows = {r["item"]: r for r in data["takeoff_summary"]}
        # Bollards reverts to base (no value, still unproven).
        self.assertIn(rows["Bollards"].get("quantity"), (None, "—"))
        self.assertEqual(rows["Bollards"]["source"], "manifest_missing")


if __name__ == "__main__":
    unittest.main()
