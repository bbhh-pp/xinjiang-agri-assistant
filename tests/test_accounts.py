"""Account isolation and persistence tests; no paid API requests."""

import json
import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib import error, request

from account_store import activate_initial_admin, create_user, disable_user
from conversation_store import (database_path, get_conversation, get_turn, initialize_database,
                                recent_context, save_chinese_turn)
from server import Handler


@unittest.skip("Local demo mode intentionally has no account or login API.")
class AccountHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.env = patch.dict(os.environ, {"SHENNONG_CONVERSATIONS_DB": str(Path(self.tmp.name) / "accounts.sqlite3")})
        self.env.start()
        self.admin = activate_initial_admin("admin-test-password-123")
        self.alice = create_user("alice", "alice-test-password-123")
        self.bob = create_user("bob", "bob-test-password-123")
        self._start_server()

    def tearDown(self):
        self._stop_server()
        self.env.stop()
        self.tmp.cleanup()

    def _start_server(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def _json(self, path, method="GET", data=None, *, cookie=None, csrf=None, origin=None):
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        if origin:
            headers["Origin"] = origin
        req = request.Request(self.url + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response), response.headers
        except error.HTTPError as exc:
            return exc.code, json.load(exc), exc.headers

    def _login(self, username, password):
        status, payload, headers = self._json("/api/auth/login", "POST",
            {"username": username, "password": password}, origin=self.url)
        self.assertEqual(status, 200)
        cookie_header = headers["Set-Cookie"]
        for attribute in ("Secure", "HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(attribute, cookie_header)
        self.assertIn(SESSION_COOKIE, cookie_header)
        return cookie_header.split(";", 1)[0], payload["csrf_token"]

    def test_two_sessions_share_history_and_language_across_server_restart(self):
        first_cookie, first_csrf = self._login("alice", "alice-test-password-123")
        second_cookie, second_csrf = self._login("alice", "alice-test-password-123")
        self.assertNotEqual(first_cookie, second_cookie)
        status, conversation, _ = self._json("/api/conversations", "POST", {},
            cookie=first_cookie, csrf=first_csrf, origin=self.url)
        self.assertEqual(status, 201)
        save_chinese_turn(self.alice["id"], conversation["id"], input_kind="text",
            original_input="羊不吃草", question_zh="羊不吃草怎么办", answer_zh="观察饮水。")
        status, listed, _ = self._json("/api/conversations", cookie=second_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(listed["conversations"][0]["id"], conversation["id"])
        status, _, _ = self._json("/api/account/preferences", "POST", {"ui_language": "ug"},
            cookie=first_cookie, csrf=first_csrf, origin=self.url)
        self.assertEqual(status, 200)
        self.assertEqual(self._json("/api/auth/me", cookie=second_cookie)[1]["user"]["ui_language"], "ug")
        self._stop_server()
        self._start_server()
        self.assertEqual(self._json("/api/conversations/" + conversation["id"],
                                    cookie=second_cookie)[1]["turns"][0]["answer_zh"], "观察饮水。")
        self.assertEqual(self._json("/api/auth/me", cookie=first_cookie)[1]["user"]["ui_language"], "ug")
        status, _, _ = self._json("/api/auth/logout", "POST", {}, cookie=first_cookie,
                                  csrf=first_csrf, origin=self.url)
        self.assertEqual(status, 200)
        self.assertEqual(self._json("/api/auth/me", cookie=first_cookie)[0], 401)
        self.assertEqual(self._json("/api/conversations", cookie=second_cookie)[0], 200)
        new_cookie, _ = self._login("alice", "alice-test-password-123")
        self.assertEqual(self._json("/api/conversations/" + conversation["id"], cookie=new_cookie)[0], 200)

    def test_different_accounts_cannot_read_follow_up_retry_or_delete(self):
        alice_cookie, alice_csrf = self._login("alice", "alice-test-password-123")
        bob_cookie, bob_csrf = self._login("bob", "bob-test-password-123")
        status, conversation, _ = self._json("/api/conversations", "POST", {},
            cookie=alice_cookie, csrf=alice_csrf, origin=self.url)
        self.assertEqual(status, 201)
        turn = save_chinese_turn(self.alice["id"], conversation["id"], input_kind="text",
            original_input="羊", question_zh="羊不吃草", answer_zh="请观察饮水。")
        self.assertEqual(self._json("/api/conversations", cookie=bob_cookie)[1]["conversations"], [])
        self.assertEqual(self._json("/api/conversations/" + conversation["id"], cookie=bob_cookie)[0], 404)
        self.assertEqual(self._json("/api/conversations/" + conversation["id"], "DELETE",
            cookie=bob_cookie, csrf=bob_csrf, origin=self.url)[0], 404)
        self.assertEqual(self._json("/api/turns/" + turn + "/retry-translation", "POST", {},
            cookie=bob_cookie, csrf=bob_csrf, origin=self.url)[0], 404)
        self.assertEqual(self._json("/api/ask", "POST", {"question": "它怎么了", "conversation_id": conversation["id"]},
            cookie=bob_cookie, csrf=bob_csrf, origin=self.url)[0], 404)
        self.assertIsNone(get_turn(self.bob["id"], turn))
        self.assertEqual(recent_context(self.bob["id"], conversation["id"]), [])
        self.assertEqual(self._json("/api/conversations/" + conversation["id"], cookie=alice_cookie)[0], 200)

    def test_csrf_and_password_storage(self):
        cookie, csrf = self._login("alice", "alice-test-password-123")
        self.assertEqual(self._json("/api/conversations", "POST", {}, cookie=cookie, origin=self.url)[0], 403)
        self.assertEqual(self._json("/api/conversations", "POST", {}, cookie=cookie,
                                    csrf=csrf, origin="https://attacker.example")[0], 403)
        with closing(sqlite3.connect(database_path())) as db:
            stored = db.execute("SELECT password_hash FROM users WHERE username='alice'").fetchone()[0]
            self.assertTrue(stored.startswith("scrypt$"))
            self.assertNotIn("alice-test-password-123", stored)
            token_hash = db.execute("SELECT token_hash FROM sessions WHERE user_id=?",
                                    (self.alice["id"],)).fetchone()[0]
            self.assertNotIn(cookie.split("=", 1)[1], token_hash)

    def test_disabling_invited_user_revokes_sessions(self):
        cookie, _ = self._login("bob", "bob-test-password-123")
        self.assertEqual(self._json("/api/auth/me", cookie=cookie)[0], 200)
        disable_user("bob")
        self.assertEqual(self._json("/api/auth/me", cookie=cookie)[0], 401)


class LegacyMigrationTests(unittest.TestCase):
    def test_existing_rows_migrate_to_disabled_admin_without_loss(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE conversations(id TEXT PRIMARY KEY,title TEXT,created_at TEXT,updated_at TEXT)")
                db.execute("""CREATE TABLE turns(id TEXT PRIMARY KEY,conversation_id TEXT,input_kind TEXT,
                    original_input TEXT,question_zh TEXT,observation TEXT,answer_zh TEXT,answer_ug TEXT,
                    translation_status TEXT,created_at TEXT)""")
                db.execute("INSERT INTO conversations VALUES ('old','旧对话','t1','t2')")
                db.execute("INSERT INTO turns VALUES ('turn','old','text','原问题','中文问题','','中文回答','维文回答','complete','t3')")
                db.commit()
            with patch.dict(os.environ, {"SHENNONG_CONVERSATIONS_DB": str(path)}):
                initialize_database()
                with closing(sqlite3.connect(path)) as db:
                    admin_id, disabled = db.execute("SELECT id,disabled FROM users WHERE username='admin'").fetchone()
                    owner = db.execute("SELECT user_id FROM conversations WHERE id='old'").fetchone()[0]
                    self.assertEqual(owner, admin_id)
                    self.assertEqual(disabled, 1)
                self.assertEqual(get_conversation(admin_id, "old")["turns"][0]["answer_ug"], "维文回答")
                self.assertEqual(activate_initial_admin("migration-test-password-123")["id"], admin_id)
                initialize_database()
                self.assertEqual(get_conversation(admin_id, "old")["turns"][0]["answer_zh"], "中文回答")
