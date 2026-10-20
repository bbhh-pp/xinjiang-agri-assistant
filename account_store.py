"""Invite-only accounts and server-side sessions. No plaintext passwords are stored."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid

from conversation_store import _connect


SESSION_SECONDS = 7 * 24 * 60 * 60
USERNAME_RE = re.compile(r"[a-zA-Z0-9_.-]{3,32}\Z")
_DUMMY_HASH = None


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12 or len(password) > 128:
        raise ValueError("密码需要 12 至 128 个字符。")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, n, r, p, salt, expected = stored.split("$")
        if algorithm != "scrypt" or (int(n), int(r), int(p)) != (16384, 8, 1):
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=_decode(salt),
                                n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(digest, _decode(expected))
    except (ValueError, TypeError):
        return False


def _public(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "username": row["username"], "role": row["role"],
            "ui_language": row["ui_language"]}


def activate_initial_admin(password: str) -> dict:
    encoded = hash_password(password)
    with _connect() as db:
        row = db.execute("SELECT * FROM users WHERE username='admin' AND role='admin'").fetchone()
        if row is None:
            raise RuntimeError("初始管理员记录不存在。")
        if row["password_hash"]:
            raise ValueError("初始管理员已激活；请使用重置密码命令。")
        db.execute("UPDATE users SET password_hash=?, disabled=0 WHERE id=?", (encoded, row["id"]))
        db.execute("DELETE FROM login_attempts WHERE username='admin'")
        return _public(row)


def create_user(username: str, password: str) -> dict:
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("用户名需为 3–32 位英文字母、数字、点、下划线或短横线。")
    if username.lower() == "admin":
        raise ValueError("admin 是初始管理员账号。")
    encoded = hash_password(password)
    with _connect() as db:
        try:
            user_id = uuid.uuid4().hex
            db.execute("INSERT INTO users(id,username,password_hash,role) VALUES (?,?,?,'user')",
                       (user_id, username, encoded))
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在。") from exc
        return {"id": user_id, "username": username, "role": "user", "ui_language": "zh"}


def reset_password(username: str, password: str) -> None:
    encoded = hash_password(password)
    with _connect() as db:
        row = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if row is None:
            raise ValueError("账号不存在。")
        db.execute("UPDATE users SET password_hash=?, disabled=0 WHERE id=?", (encoded, row["id"]))
        db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
        db.execute("DELETE FROM login_attempts WHERE username=?", (username.lower(),))


def disable_user(username: str) -> None:
    if username.lower() == "admin":
        raise ValueError("不能用此命令禁用初始管理员。")
    with _connect() as db:
        row = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if row is None:
            raise ValueError("账号不存在。")
        db.execute("UPDATE users SET disabled=1 WHERE id=?", (row["id"],))
        db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))


def authenticate(username: str, password: str) -> dict | None:
    global _DUMMY_HASH
    now = int(time.time())
    with _connect() as db:
        attempt = db.execute("SELECT failures, blocked_until FROM login_attempts WHERE username=?",
                             (username.lower(),)).fetchone()
        if attempt and attempt["blocked_until"] > now:
            return None
        previous_failures = 0 if attempt and attempt["blocked_until"] else (attempt["failures"] if attempt else 0)
        row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password("unused-dummy-password-for-timing")
        valid = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
        if not valid or row is None or row["disabled"]:
            failures = previous_failures + 1
            blocked_until = now + 15 * 60 if failures >= 5 else 0
            db.execute("""INSERT INTO login_attempts(username,failures,blocked_until) VALUES (?,?,?)
                ON CONFLICT(username) DO UPDATE SET failures=excluded.failures,
                blocked_until=excluded.blocked_until""", (username.lower(), failures, blocked_until))
            return None
        db.execute("DELETE FROM login_attempts WHERE username=?", (username.lower(),))
        return _public(row)


def create_session(user_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    with _connect() as db:
        db.execute("DELETE FROM sessions WHERE expires_at<=?", (int(time.time()),))
        db.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES (?,?,?,?)",
                   (token_hash, user_id, csrf, int(time.time()) + SESSION_SECONDS))
    return token, csrf


def get_session(token: str | None) -> dict | None:
    if not token or len(token) > 128:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _connect() as db:
        row = db.execute("""SELECT u.*, s.csrf_token FROM sessions s
            JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?
            AND u.disabled=0 AND u.password_hash IS NOT NULL""",
            (token_hash, int(time.time()))).fetchone()
        return {**_public(row), "csrf_token": row["csrf_token"]} if row else None


def revoke_session(token: str | None) -> None:
    if token:
        with _connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?",
                       (hashlib.sha256(token.encode("utf-8")).hexdigest(),))


def set_ui_language(user_id: str, language: str) -> dict:
    if language not in ("zh", "ug"):
        raise ValueError("不支持的界面语言。")
    with _connect() as db:
        db.execute("UPDATE users SET ui_language=? WHERE id=?", (language, user_id))
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise ValueError("账号不存在。")
        return _public(row)
