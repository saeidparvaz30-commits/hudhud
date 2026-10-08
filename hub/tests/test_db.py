# SPDX-License-Identifier: AGPL-3.0-or-later
import re
import sqlite3
import time

import pytest

from hudhud_hub.db import (
    MIGRATIONS,
    apply_migrations,
    connect,
    insert_book,
    list_books,
    new_ulid,
    schema_version,
    soft_delete,
    utc_now,
)


def book(book_id="a" * 64, title="Masnavi"):
    return {"id": book_id, "title": title, "author": "Rumi", "language": "fa",
            "format": "epub", "file_size": 123, "cover_path": None}


def migrated():
    conn = connect(":memory:")
    apply_migrations(conn, MIGRATIONS)
    return conn





def test_connect_pragmas(tmp_path):
    conn = connect(tmp_path / "hub.db")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.row_factory is sqlite3.Row


def test_fresh_database_gets_every_table():
    conn = connect(":memory:")
    assert apply_migrations(conn, MIGRATIONS) == [1, 2, 3]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"books", "progress", "highlights", "devices", "changes", "chunks",
            "schema_version"} <= tables


def test_migrations_are_idempotent():
    conn = migrated()
    assert apply_migrations(conn, MIGRATIONS) == []
    assert schema_version(conn) == 3


def test_failed_migration_rolls_back(tmp_path):
    (tmp_path / "0001_init.sql").write_text((MIGRATIONS / "0001_init.sql").read_text("utf-8"))
    (tmp_path / "0002_broken.sql").write_text("CREATE TABLE half (x);\nCREATE TABLE broken (")
    conn = connect(":memory:")
    with pytest.raises(sqlite3.Error):
        apply_migrations(conn, tmp_path)
    assert schema_version(conn) == 1
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'half'").fetchone() is None
    assert not conn.in_transaction


def test_duplicate_versions_rejected(tmp_path):
    (tmp_path / "0001_a.sql").write_text("CREATE TABLE a (x);")
    (tmp_path / "0001_b.sql").write_text("CREATE TABLE b (x);")
    with pytest.raises(ValueError):
        apply_migrations(connect(":memory:"), tmp_path)


def test_foreign_keys_enforced():
    conn = migrated()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO progress VALUES ('missing-book', 'dev', 'cfi', 0.5, ?)",
                     (utc_now(),))


def test_fraction_must_be_between_0_and_1():
    conn = migrated()
    insert_book(conn, book(), utc_now())
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO progress VALUES (?, 'dev', 'cfi', 1.5, ?)",
                     (book()["id"], utc_now()))


def test_ulids_are_unique_and_time_sortable():
    first = new_ulid()
    time.sleep(0.002)
    later = [new_ulid() for _ in range(100)]
    assert len(set(later)) == 100
    assert all(len(u) == 26 and re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", u) for u in later)
    assert all(first < u for u in later)


def test_utc_now_format():
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", utc_now())


def test_insert_book_is_idempotent():
    conn = migrated()
    assert insert_book(conn, book(), "2026-10-08T10:00:00.000Z") is True
    assert insert_book(conn, book(title="Changed"), "2026-10-08T11:00:00.000Z") is False
    rows = list_books(conn)
    assert len(rows) == 1 and rows[0]["title"] == "Masnavi"


def test_soft_delete_hides_once():
    conn = migrated()
    insert_book(conn, book(), utc_now())
    assert soft_delete(conn, "books", book()["id"], utc_now()) is True
    assert soft_delete(conn, "books", book()["id"], utc_now()) is False
    assert list_books(conn) == []
    assert conn.execute("SELECT deleted FROM books").fetchone()[0] == 1


def test_reimporting_a_deleted_book_restores_it():
    conn = migrated()
    insert_book(conn, book(), "2026-10-08T10:00:00.000Z")
    soft_delete(conn, "books", book()["id"], "2026-10-08T11:00:00.000Z")
    assert insert_book(conn, book(), "2026-10-08T12:00:00.000Z") is True
    rows = list_books(conn)
    assert len(rows) == 1 and rows[0]["updated_at"] == "2026-10-08T12:00:00.000Z"


def test_soft_delete_rejects_other_tables():
    conn = migrated()
    for table in ["devices", "books; DROP TABLE books"]:
        with pytest.raises(ValueError):
            soft_delete(conn, table, "x", utc_now())
