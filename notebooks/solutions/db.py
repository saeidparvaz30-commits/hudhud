# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite connection, migrations, ids, timestamps and tombstones."""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ulid import ULID

MIGRATIONS = Path("../hub/src/hudhud_hub/migrations")
SOFT_DELETABLE = {"books", "highlights"}
MIGRATION_RE = re.compile(r"^(\d{4})_[\w-]+\.sql$")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def new_ulid() -> str:
    return str(ULID())


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def schema_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> list[int]:
    current = schema_version(conn)
    found = sorted(
        (int(m.group(1)), p)
        for p in Path(migrations_dir).iterdir()
        if (m := MIGRATION_RE.match(p.name))
    )
    versions = [v for v, _ in found]
    if len(versions) != len(set(versions)):
        raise ValueError("two migration files share a version number")
    applied = []
    for version, path in found:
        if version <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(
                f"BEGIN;\n{sql}\n"
                f"INSERT INTO schema_version (version, applied_at) "
                f"VALUES ({version}, '{utc_now()}');\nCOMMIT;"
            )
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        applied.append(version)
    return applied


def insert_book(conn: sqlite3.Connection, book: dict, now: str) -> bool:
    cur = conn.execute(
        "INSERT INTO books "
        "(id, title, author, language, format, file_size, cover_path, added_at, updated_at) "
        "VALUES (:id, :title, :author, :language, :format, :file_size, :cover_path, :now, :now) "
        "ON CONFLICT (id) DO UPDATE SET deleted = 0, updated_at = excluded.updated_at "
        "WHERE books.deleted = 1",
        {**book, "now": now},
    )
    return cur.rowcount == 1


def list_books(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM books WHERE deleted = 0 ORDER BY added_at DESC, title"
    ).fetchall()


def soft_delete(conn: sqlite3.Connection, table: str, entity_id: str, ts: str) -> bool:
    if table not in SOFT_DELETABLE:
        raise ValueError(f"not soft-deletable: {table!r}")
    cur = conn.execute(
        f"UPDATE {table} SET deleted = 1, updated_at = ? WHERE id = ? AND deleted = 0",
        (ts, entity_id),
    )
    return cur.rowcount == 1
