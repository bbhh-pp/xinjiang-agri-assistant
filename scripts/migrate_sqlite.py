"""Safely copy the account and conversation SQLite database to persistent storage."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def _counts(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(path)) as db:
        result = db.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {result}")
        foreign_key_errors = db.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError("SQLite foreign-key check failed; migration stopped.")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"users", "conversations", "turns", "sessions"}
        if not required.issubset(tables):
            raise RuntimeError("Source database is missing account/history tables; migration stopped.")
        return {name: db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                for name in ("users", "conversations", "turns")}


def migrate(source: Path, target: Path, *, replace_existing: bool = False) -> tuple[dict, dict, Path | None]:
    source = source.resolve(strict=True)
    target = target.resolve()
    if source == target:
        raise ValueError("Source and target must be different paths.")
    if not source.is_file():
        raise ValueError("Source database is not a file.")
    target.parent.mkdir(parents=True, exist_ok=True)
    if any(Path(str(target) + suffix).exists() for suffix in ("-wal", "-shm")):
        raise RuntimeError("Target has active SQLite sidecar files. Stop the app before migration.")
    if target.exists() and not replace_existing:
        raise RuntimeError("Target already exists. Stop the app and rerun with --replace-existing to keep a backup first.")

    source_counts = _counts(source)
    temp = target.with_name(target.name + ".migration.tmp")
    if temp.exists():
        temp.unlink()
    try:
        with closing(sqlite3.connect(source)) as source_db, closing(sqlite3.connect(temp)) as target_db:
            source_db.backup(target_db)
            target_db.execute("PRAGMA foreign_keys=ON")
            target_db.execute("DELETE FROM sessions")
            target_db.commit()
        target_counts = _counts(temp)
        if source_counts != target_counts:
            raise RuntimeError("Table counts changed during migration; original target was left untouched.")

        backup = None
        if target.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = target.with_name(f"{target.name}.before-migration-{stamp}")
            with closing(sqlite3.connect(target)) as old_db, closing(sqlite3.connect(backup)) as backup_db:
                old_db.backup(backup_db)
            _counts(backup)
        temp.replace(target)
        return source_counts, target_counts, backup
    finally:
        temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    try:
        before, after, backup = migrate(args.source, args.target, replace_existing=args.replace_existing)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"Migration stopped safely: {exc}", file=sys.stderr)
        return 1
    print(f"Migration verified: users={after['users']}, conversations={after['conversations']}, turns={after['turns']}")
    print("Existing account passwords were preserved; login sessions were cleared and users must sign in again.")
    print(f"Source and destination row counts match: {before == after}")
    if backup:
        print(f"Previous destination backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
