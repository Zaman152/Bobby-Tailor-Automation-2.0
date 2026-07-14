"""API tests for /api/jobs/history endpoints."""
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

from bobbytailor.stores import job_store
from bobbytailor.web.app import create_app
from bobbytailor.web.auth import get_admin

app = create_app()

from tests.test_job_store import make_job


class JobHistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_jobs.db"
        self.patchers = [
            mock.patch("bobbytailor.stores.job_store.STACKCT_DB_PATH", self.db_path),
            mock.patch("bobbytailor.config.STACKCT_DB_PATH", self.db_path),
            mock.patch("bobbytailor.stores.job_store.JOB_HISTORY_RETENTION_DAYS", 0),
            mock.patch("flask_login.utils._get_user", return_value=get_admin()),
        ]
        for p in self.patchers:
            p.start()
        job_store._initialized = False
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        job_store._initialized = False
        self.tmp.cleanup()

    def _auth_get(self, path):
        return self.client.get(path)

    def test_history_list_empty(self):
        resp = self._auth_get("/api/jobs/history")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["runs"], [])
        self.assertEqual(data["limit"], 50)
        self.assertEqual(data["offset"], 0)

    def test_history_list_newest_first(self):
        job_store.save_job_run(
            make_job(started_at="2026-06-01T09:00:00"),
            "old",
            "stackct",
        )
        job_store.save_job_run(
            make_job(started_at="2026-06-01T11:00:00"),
            "new",
            "stackct",
        )
        resp = self._auth_get("/api/jobs/history")
        data = resp.get_json()
        self.assertEqual(data["runs"][0]["job_id"], "new")

    def test_history_list_outcome_filter(self):
        job_store.save_job_run(make_job(status="done"), "ok", "stackct")
        job_store.save_job_run(make_job(status="error", error="x"), "bad", "stackct")
        ok_resp = self._auth_get("/api/jobs/history?outcome=success")
        bad_resp = self._auth_get("/api/jobs/history?outcome=failed")
        partial_resp = self._auth_get("/api/jobs/history?outcome=partial")
        self.assertEqual(len(ok_resp.get_json()["runs"]), 1)
        self.assertEqual(len(bad_resp.get_json()["runs"]), 1)
        self.assertEqual(len(partial_resp.get_json()["runs"]), 0)

    def test_history_list_invalid_outcome(self):
        resp = self._auth_get("/api/jobs/history?outcome=bogus")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

    def test_history_list_pagination(self):
        for i in range(3):
            job_store.save_job_run(
                make_job(started_at=f"2026-06-01T10:0{i}:00"),
                f"j{i}",
                "stackct",
            )
        page1 = self._auth_get("/api/jobs/history?limit=2&offset=0").get_json()
        page2 = self._auth_get("/api/jobs/history?limit=2&offset=2").get_json()
        self.assertEqual(len(page1["runs"]), 2)
        self.assertEqual(len(page2["runs"]), 1)

    def test_history_detail_found(self):
        job_store.save_job_run(make_job(), "detail1", "stackct")
        resp = self._auth_get("/api/jobs/history/detail1")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["job_id"], "detail1")
        self.assertIn("log_tail", data)
        self.assertIsInstance(data["log_tail"], list)

    def test_history_detail_not_found(self):
        resp = self._auth_get("/api/jobs/history/nonexistent99")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", resp.get_json())

    def test_history_detail_bad_jobid(self):
        resp = self._auth_get("/api/jobs/history/../../etc/passwd")
        self.assertIn(resp.status_code, (400, 404))

    def test_history_unauthenticated(self):
        anon = mock.Mock()
        anon.is_authenticated = False
        with mock.patch("flask_login.utils._get_user", return_value=anon):
            resp = self.client.get("/api/jobs/history")
        self.assertEqual(resp.status_code, 401)


class PersistJobHistoryTests(unittest.TestCase):
    """Regression: 21-REVIEW CR-02 — jobs_runtime must actually persist runs.

    The 21-02 extraction of jobs_runtime.py dropped the job_store import, so
    every _persist_job_history call raised NameError, silently swallowed by
    the broad except — NO job run ever reached /api/jobs/history. These tests
    prove persistence end-to-end through jobs_runtime itself.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_jobs.db"
        self.patchers = [
            mock.patch("bobbytailor.stores.job_store.STACKCT_DB_PATH", self.db_path),
            mock.patch("bobbytailor.stores.job_store.JOB_HISTORY_RETENTION_DAYS", 0),
        ]
        for p in self.patchers:
            p.start()
        job_store._initialized = False

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        job_store._initialized = False
        self.tmp.cleanup()

    def test_persist_job_history_writes_a_row(self):
        from bobbytailor.web import jobs_runtime

        job_id = "cr02unit"
        jobs_runtime.jobs[job_id] = make_job(status="done")
        try:
            jobs_runtime._persist_job_history(job_id, "stackct")
        finally:
            jobs_runtime.jobs.pop(job_id, None)
        row = job_store.get_job_run(job_id)
        self.assertIsNotNone(row, "job run was not persisted to history")
        self.assertEqual(row["outcome"], "success")
        self.assertEqual(row["job_type"], "stackct")

    def test_pdf_job_persists_history_on_success(self):
        from bobbytailor.web import jobs_runtime

        job_id = "cr02pdf"
        jobs_runtime.jobs[job_id] = {
            "id": job_id, "type": "pdf", "status": "queued",
            "progress": 0, "log": [], "result": None, "error": None,
            "project": "CR02 Project", "file": "x.pdf",
            "started_at": None,
            "current_sheet": {"index": 0, "total": 0, "name": None, "phase": None},
            "sheets_completed": [],
        }
        fake_result = {"total_line_items": 3, "sheets_processed": 1}
        try:
            with mock.patch(
                "bobbytailor.pipeline.pdf_analyzer.run_pdf_analysis",
                return_value=fake_result,
            ):
                jobs_runtime._pdf_job(job_id, "/tmp/fake.pdf", "CR02 Project")
            self.assertEqual(jobs_runtime.jobs[job_id]["status"], "done")
        finally:
            jobs_runtime.jobs.pop(job_id, None)
        row = job_store.get_job_run(job_id)
        self.assertIsNotNone(row, "finished PDF job never reached job history")
        self.assertEqual(row["job_type"], "pdf")
        self.assertEqual(row["outcome"], "success")

    def test_pdf_job_persists_history_on_error(self):
        from bobbytailor.web import jobs_runtime

        job_id = "cr02err"
        jobs_runtime.jobs[job_id] = {
            "id": job_id, "type": "pdf", "status": "queued",
            "progress": 0, "log": [], "result": None, "error": None,
            "project": "CR02 Project", "file": "x.pdf",
            "started_at": None,
            "current_sheet": {"index": 0, "total": 0, "name": None, "phase": None},
            "sheets_completed": [],
        }
        try:
            with mock.patch(
                "bobbytailor.pipeline.pdf_analyzer.run_pdf_analysis",
                side_effect=RuntimeError("boom"),
            ):
                jobs_runtime._pdf_job(job_id, "/tmp/fake.pdf", "CR02 Project")
            self.assertEqual(jobs_runtime.jobs[job_id]["status"], "error")
        finally:
            jobs_runtime.jobs.pop(job_id, None)
        row = job_store.get_job_run(job_id)
        self.assertIsNotNone(row, "failed PDF job never reached job history")
        self.assertEqual(row["outcome"], "failed")


if __name__ == "__main__":
    unittest.main()
