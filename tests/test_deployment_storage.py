"""Persistent storage and per-account quota checks for deployment readiness."""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from account_store import activate_initial_admin, create_session
from conversation_store import (consume_request_quota, create_conversation,
                                save_chinese_turn)
from scripts.migrate_sqlite import migrate


class DeploymentStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.sqlite3"
        self.target = self.root / "persistent" / "conversations.sqlite3"
        self.env = patch.dict(os.environ, {"SHENNONG_CONVERSATIONS_DB": str(self.source)})
        self.env.start()
        self.user = activate_initial_admin("deployment-test-password-123")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_account_quota_survives_storage_and_is_enforced(self):
        allowed, _, _ = consume_request_quota(self.user["id"], "/api/ask-stream",
                                               per_minute=10, per_day=1)
        self.assertTrue(allowed)
        allowed, retry_after, kind = consume_request_quota(self.user["id"], "/api/ask-image-stream",
                                                            per_minute=10, per_day=1)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)
        self.assertEqual(kind, "day")

    def test_migration_preserves_history_and_clears_old_sessions(self):
        conversation = create_conversation(self.user["id"])
        save_chinese_turn(self.user["id"], conversation["id"], input_kind="text",
                          original_input="羊不吃草怎么办？", question_zh="羊不吃草怎么办？",
                          answer_zh="先检查饮水。")
        create_session(self.user["id"])
        before, after, backup = migrate(self.source, self.target)
        self.assertEqual(before, after)
        self.assertIsNone(backup)
        with closing(sqlite3.connect(self.target)) as db:
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM turns").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM request_usage").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
