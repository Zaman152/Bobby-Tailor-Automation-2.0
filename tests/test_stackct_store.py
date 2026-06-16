"""Unit tests for StackCT SQLite store (no browser)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import stackct_store as store


class StackctStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_stackct.db"
        self.patchers = [
            mock.patch("stackct_store.STACKCT_DB_PATH", self.db_path),
            mock.patch("stackct_store.OUTPUT_DIR", self.tmp.name),
        ]
        for p in self.patchers:
            p.start()
        store._initialized = False

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        store._initialized = False
        self.tmp.cleanup()

    def test_schema_and_upsert(self):
        conn = store.get_connection()
        try:
            store.init_schema(conn)
        finally:
            conn.close()
        store.set_metadata("migrated_from_json", "1")
        store._initialized = True
        synced = "2026-05-26T12:00:00"
        store.upsert_projects([{"id": 1, "name": "Test Project"}], synced)
        store.upsert_plans(
            1,
            10,
            [{"page_id": 100, "sheet_name": "A1.01"}],
            synced,
        )
        projects = store.list_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], "Test Project")
        # v2 schema is folder-aware: query plans scoped to the folder we wrote.
        plans = store.get_plans(1, folder_id=10)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["page_id"], 100)


if __name__ == "__main__":
    unittest.main()
