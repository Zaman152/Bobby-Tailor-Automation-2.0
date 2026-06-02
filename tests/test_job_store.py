"""Unit tests for job_store.py — outcome derivation and persistence."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Required before app/job_store import in some test runners
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxnRp2./WyH1K8LK7xJQZHQKHQKHQ",
)

import job_store


def make_job(status="done", **kwargs):
    base = {
        "status": status,
        "project": kwargs.pop("project", "Test Project"),
        "mode": "all",
        "mode_detail": "full",
        "started_at": kwargs.pop("started_at", "2026-06-01T10:00:00"),
        "finished_at": kwargs.pop("finished_at", "2026-06-01T10:05:00"),
        "progress": 100,
        "log": kwargs.pop("log", [{"timestamp": "2026-06-01T10:00:01", "type": "info", "message": "done"}]),
        "result": kwargs.pop("result", {}),
        "error": kwargs.pop("error", None),
        "warning": kwargs.pop("warning", None),
        "linked_sheets_count": 0,
        "sheets_completed": [],
    }
    base.update(kwargs)
    return base


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_jobs.db"
        self.patchers = [
            mock.patch("job_store.STACKCT_DB_PATH", self.db_path),
            mock.patch("config.STACKCT_DB_PATH", self.db_path),
            mock.patch("job_store.JOB_HISTORY_RETENTION_DAYS", 0),
        ]
        for p in self.patchers:
            p.start()
        job_store._initialized = False

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        job_store._initialized = False
        self.tmp.cleanup()

    def test_derive_outcome_success(self):
        self.assertEqual(
            job_store._derive_outcome(make_job(status="done")),
            "success",
        )

    def test_derive_outcome_partial_warning(self):
        self.assertEqual(
            job_store._derive_outcome(make_job(status="done", warning="Partial report")),
            "partial",
        )

    def test_derive_outcome_partial_result_flag(self):
        self.assertEqual(
            job_store._derive_outcome(make_job(status="done", result={"partial": True})),
            "partial",
        )

    def test_derive_outcome_failed(self):
        self.assertEqual(job_store._derive_outcome(make_job(status="error")), "failed")

    def test_derive_outcome_cancelled(self):
        self.assertEqual(job_store._derive_outcome(make_job(status="cancelled")), "cancelled")

    def test_save_and_list_round_trip(self):
        job = make_job()
        job_store.save_job_run(job, job_id="test01", job_type="stackct")
        rows = job_store.list_job_runs()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["job_id"], "test01")
        self.assertEqual(rows[0]["outcome"], "success")
        self.assertEqual(rows[0]["project_name"], "Test Project")
        self.assertEqual(rows[0]["job_type"], "stackct")

    def test_save_and_get_round_trip(self):
        job = make_job()
        job_store.save_job_run(job, job_id="test02", job_type="stackct")
        row = job_store.get_job_run("test02")
        self.assertIsNotNone(row)
        self.assertIsInstance(row["log_tail"], list)
        self.assertEqual(len(row["log_tail"]), 1)

    def test_get_job_run_not_found(self):
        self.assertIsNone(job_store.get_job_run("nonexistent"))

    def test_list_filters_by_outcome(self):
        job_store.save_job_run(make_job(status="done"), "ok1", "stackct")
        job_store.save_job_run(make_job(status="error", error="fail"), "bad1", "stackct")
        success_rows = job_store.list_job_runs(outcome="success")
        failed_rows = job_store.list_job_runs(outcome="failed")
        self.assertEqual(len(success_rows), 1)
        self.assertEqual(len(failed_rows), 1)

    def test_list_newest_first(self):
        job_store.save_job_run(
            make_job(started_at="2026-06-01T09:00:00"),
            "older",
            "stackct",
        )
        job_store.save_job_run(
            make_job(started_at="2026-06-01T11:00:00"),
            "newer",
            "stackct",
        )
        rows = job_store.list_job_runs()
        self.assertEqual(rows[0]["job_id"], "newer")

    def test_log_tail_truncated_to_80(self):
        log = [{"message": f"line {i}"} for i in range(120)]
        job = make_job(log=log)
        job_store.save_job_run(job, "logjob", "stackct")
        row = job_store.get_job_run("logjob")
        self.assertEqual(len(row["log_tail"]), 80)
        self.assertEqual(row["log_tail"][0]["message"], "line 40")

    def test_save_idempotent(self):
        job = make_job()
        job_store.save_job_run(job, "same", "stackct")
        job_store.save_job_run(job, "same", "stackct")
        self.assertEqual(len(job_store.list_job_runs()), 1)

    def test_duration_computed(self):
        job = make_job(
            started_at="2026-01-01T10:00:00",
            finished_at="2026-01-01T10:05:30",
        )
        job_store.save_job_run(job, "dur", "stackct")
        row = job_store.get_job_run("dur")
        self.assertAlmostEqual(row["duration_sec"], 330.0, places=0)


if __name__ == "__main__":
    unittest.main()
