# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reference answers for notebook 00."""

import sqlite3


def create_books_table(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT)")


def add_book(conn: sqlite3.Connection, title: str, author: str | None) -> int:
    cur = conn.execute("INSERT INTO books (title, author) VALUES (?, ?)", (title, author))
    return cur.lastrowid


def titles_by_author(conn: sqlite3.Connection, author: str) -> list[str]:
    rows = conn.execute("SELECT title FROM books WHERE author = ? ORDER BY title", (author,))
    return [title for (title,) in rows]
