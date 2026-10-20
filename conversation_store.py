"""SQLite storage for account-owned conversations and login sessions."""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DB = Path(__file__).resolve().parent / "data" / "conversations.sqlite3"
_schema_lock = threading.Lock()
_initialized: set[Path] = set()


def database_path() -> Path:
    return Path(os.environ.get("SHENNONG_CONVERSATIONS_DB", str(DEFAULT_DB))).resolve()


def initialize_database() -> None:
    """Idempotently migrate legacy, ownerless rows to the disabled first admin."""
    path = database_path()
    with _schema_lock:
        if path in _initialized and path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT,
                role TEXT NOT NULL CHECK(role IN ('admin','user')),
                ui_language TEXT NOT NULL DEFAULT 'zh' CHECK(ui_language IN ('zh','ug')),
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '新对话',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                user_id TEXT REFERENCES users(id)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                input_kind TEXT NOT NULL,
                original_input TEXT NOT NULL,
                question_zh TEXT NOT NULL,
                observation TEXT NOT NULL DEFAULT '',
                answer_zh TEXT NOT NULL,
                answer_ug TEXT NOT NULL DEFAULT '',
                translation_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS login_attempts (
                username TEXT PRIMARY KEY,
                failures INTEGER NOT NULL,
                blocked_until INTEGER NOT NULL DEFAULT 0
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS request_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                endpoint TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS request_usage_by_user_time ON request_usage(user_id, created_at)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(conversations)")}
            if "user_id" not in columns:
                db.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT REFERENCES users(id)")
            admin = db.execute("SELECT id FROM users WHERE username='admin' AND role='admin'").fetchone()
            if admin is None:
                admin_id = uuid.uuid4().hex
                db.execute("INSERT INTO users(id, username, password_hash, role, disabled) VALUES (?,'admin',NULL,'admin',1)",
                           (admin_id,))
            else:
                admin_id = admin[0]
            db.execute("UPDATE conversations SET user_id=? WHERE user_id IS NULL", (admin_id,))
            db.execute("CREATE INDEX IF NOT EXISTS turns_by_conversation ON turns(conversation_id, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS conversations_by_user ON conversations(user_id, updated_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS sessions_by_user ON sessions(user_id)")
            db.execute("PRAGMA user_version=2")
            db.commit()
            _initialized.add(path)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


@contextmanager
def _connect():
    initialize_database()
    db = sqlite3.connect(database_path(), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    try:
        with db:
            yield db
    finally:
        db.close()


def _as_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def local_user_id() -> str:
    """Use the existing first admin as the owner of this PC's login-free history."""
    with _connect() as db:
        row = db.execute("SELECT id FROM users WHERE username='admin' AND role='admin'").fetchone()
        if row is None:
            raise RuntimeError("本机历史记录用户不存在。")
        return row["id"]


def create_conversation(user_id: str) -> dict:
    conversation_id = uuid.uuid4().hex
    with _connect() as db:
        db.execute("INSERT INTO conversations(id,user_id) VALUES (?,?)", (conversation_id, user_id))
        return _as_dict(db.execute("SELECT * FROM conversations WHERE id=? AND user_id=?",
                                   (conversation_id, user_id)).fetchone())


def list_conversations(user_id: str) -> list[dict]:
    with _connect() as db:
        return [_as_dict(row) for row in db.execute("""
            SELECT c.*, COUNT(t.id) AS turn_count FROM conversations c
            LEFT JOIN turns t ON t.conversation_id=c.id WHERE c.user_id=?
            GROUP BY c.id ORDER BY c.updated_at DESC, c.created_at DESC LIMIT 100
        """, (user_id,))]


def get_conversation(user_id: str, conversation_id: str) -> dict | None:
    with _connect() as db:
        row = db.execute("SELECT * FROM conversations WHERE id=? AND user_id=?",
                         (conversation_id, user_id)).fetchone()
        if row is None:
            return None
        turns = db.execute("SELECT * FROM turns WHERE conversation_id=? ORDER BY created_at, rowid",
                           (conversation_id,))
        return {**_as_dict(row), "turns": [_as_dict(turn) for turn in turns]}


def delete_conversation(user_id: str, conversation_id: str) -> bool:
    with _connect() as db:
        return db.execute("DELETE FROM conversations WHERE id=? AND user_id=?",
                          (conversation_id, user_id)).rowcount > 0


def get_turn(user_id: str, turn_id: str) -> dict | None:
    with _connect() as db:
        row = db.execute("""SELECT t.* FROM turns t JOIN conversations c ON c.id=t.conversation_id
                            WHERE t.id=? AND c.user_id=?""", (turn_id, user_id)).fetchone()
        return _as_dict(row) if row else None


def recent_context(user_id: str, conversation_id: str, max_turns: int = 5,
                   max_chars: int = 3000) -> list[tuple[str, str]]:
    """Newest complete Chinese turns that fit a strict total character budget."""
    with _connect() as db:
        rows = db.execute("""SELECT t.question_zh, t.observation, t.answer_zh FROM turns t
            JOIN conversations c ON c.id=t.conversation_id
            WHERE t.conversation_id=? AND c.user_id=? AND t.answer_zh<>''
            ORDER BY t.created_at DESC, t.rowid DESC LIMIT ?""",
            (conversation_id, user_id, max_turns)).fetchall()
    result = []
    remaining = max_chars
    for row in rows:
        question = row["question_zh"]
        if row["observation"]:
            question = f"照片观察：{row['observation']}\n问题：{question}"
        answer = row["answer_zh"]
        cost = len(question) + len(answer)
        if cost > remaining:
            break
        result.append((question, answer))
        remaining -= cost
    return list(reversed(result))


def save_chinese_turn(user_id: str, conversation_id: str, *, input_kind: str,
                      original_input: str, question_zh: str, answer_zh: str,
                      observation: str = "") -> str:
    turn_id = uuid.uuid4().hex
    with _connect() as db:
        row = db.execute("SELECT title FROM conversations WHERE id=? AND user_id=?",
                         (conversation_id, user_id)).fetchone()
        if row is None:
            raise RuntimeError("对话不存在或已被删除。")
        db.execute("""INSERT INTO turns(id, conversation_id, input_kind, original_input,
            question_zh, observation, answer_zh) VALUES (?,?,?,?,?,?,?)""",
            (turn_id, conversation_id, input_kind, original_input[:2000], question_zh[:2000],
             observation[:1000], answer_zh))
        if row["title"] == "新对话":
            title = question_zh.replace("\n", " ").strip()[:28] or "图片提问"
            db.execute("UPDATE conversations SET title=? WHERE id=? AND user_id=?",
                       (title, conversation_id, user_id))
        db.execute("""UPDATE conversations SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                      WHERE id=? AND user_id=?""", (conversation_id, user_id))
    return turn_id


def finish_translation(user_id: str, turn_id: str, answer_ug: str = "", *, failed: bool = False) -> bool:
    with _connect() as db:
        result = db.execute("""UPDATE turns SET answer_ug=?, translation_status=?
            WHERE id=? AND conversation_id IN (SELECT id FROM conversations WHERE user_id=?)""",
            (answer_ug, "failed" if failed else "complete", turn_id, user_id))
        return result.rowcount > 0


def consume_request_quota(user_id: str, endpoint: str, *, per_minute: int = 6,
                          per_day: int = 20) -> tuple[bool, int, str]:
    """Atomically charge one costly or compute-heavy request to an account.

    Returns (allowed, retry_after_seconds, limit_kind). Counts are persisted so
    a restart cannot reset an account's daily allowance.
    """
    import time

    now = int(time.time())
    minute_start = now - now % 60
    beijing_shift = 8 * 60 * 60
    day_start = ((now + beijing_shift) // 86400) * 86400 - beijing_shift
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM request_usage WHERE created_at < ?", (day_start,))
        minute_count = db.execute(
            "SELECT COUNT(*) FROM request_usage WHERE user_id=? AND created_at>=?",
            (user_id, minute_start),
        ).fetchone()[0]
        if minute_count >= per_minute:
            return False, max(1, 60 - (now - minute_start)), "minute"
        day_count = db.execute(
            "SELECT COUNT(*) FROM request_usage WHERE user_id=? AND created_at>=?",
            (user_id, day_start),
        ).fetchone()[0]
        if day_count >= per_day:
            return False, max(1, day_start + 86400 - now), "day"
        db.execute("INSERT INTO request_usage(user_id, endpoint, created_at) VALUES (?,?,?)",
                   (user_id, endpoint[:80], now))
        return True, 0, ""
