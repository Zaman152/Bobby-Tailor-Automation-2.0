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

import job_store
from app import app
from auth import get_admin

from tests.test_job_store import make_job


class JobHistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_jobs.db"
        self.patchers = [
            mock.patch("job_store.STACKCT_DB_PATH", self.db_path),
            mock.patch("config.STACKCT_DB_PATH", self.db_path),
            mock.patch("job_store.JOB_HISTORY_RETENTION_DAYS", 0),
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


if __name__ == "__main__":
    unittest.main()
