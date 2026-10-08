# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-device reading positions and the resume rule."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

_COLUMNS = "book_id, device_id, locator, fraction, updated_at"
TIMESTAMP_RE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z")


@dataclass(frozen=True)
class Progress:
    book_id: str
    device_id: str
    locator: str
    fraction: float
    updated_at: str


def upsert_progress(conn: sqlite3.Connection, p: Progress) -> bool:
    if not 0.0 <= p.fraction <= 1.0:
        raise ValueError(f"fraction must be within [0, 1], got {p.fraction}")
    if not p.locator:
        raise ValueError("locator is required")
    if not TIMESTAMP_RE.fullmatch(p.updated_at):
        raise ValueError(f"updated_at must be YYYY-MM-DDTHH:MM:SS.mmmZ, got {p.updated_at!r}")
    cur = conn.execute(
        f"INSERT INTO progress ({_COLUMNS}) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (book_id, device_id) DO UPDATE SET "
        "locator = excluded.locator, fraction = excluded.fraction, "
        "updated_at = excluded.updated_at "
        "WHERE excluded.updated_at > progress.updated_at",
        (p.book_id, p.device_id, p.locator, p.fraction, p.updated_at),
    )
    return cur.rowcount == 1


def get_progress(conn: sqlite3.Connection, book_id: str, device_id: str) -> Progress | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM progress WHERE book_id = ? AND device_id = ?",
        (book_id, device_id),
    ).fetchone()
    return Progress(*row) if row else None


def latest_other_device(conn: sqlite3.Connection, book_id: str, device_id: str) -> Progress | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM progress WHERE book_id = ? AND device_id != ? "
        "ORDER BY updated_at DESC, device_id DESC LIMIT 1",
        (book_id, device_id),
    ).fetchone()
    return Progress(*row) if row else None


def should_offer_resume(own: Progress | None, other: Progress | None, total_pages: int) -> bool:
    if total_pages < 1:
        raise ValueError("total_pages must be at least 1")
    if other is None:
        return False
    if own is not None and other.updated_at <= own.updated_at:
        return False
    own_fraction = own.fraction if own is not None else 0.0
    return abs(other.fraction - own_fraction) > 1 / total_pages
