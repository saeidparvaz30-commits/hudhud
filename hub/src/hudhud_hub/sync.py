# SPDX-License-Identifier: AGPL-3.0-or-later
"""Change-log sync: devices push changes, the hub applies last-write-wins and
records accepted changes; devices pull everything after their cursor."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import asdict

from .progress import TIMESTAMP_RE, Progress, upsert_progress

COLORS = {"yellow", "green", "blue", "pink", "purple"}
ULID_RE = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")
MAX_TEXT = 20_000
MAX_LOCATOR = 4_000
BOOK_COLUMNS = ("id", "title", "author", "language", "format", "file_size", "cover_path",
                "added_at", "updated_at", "deleted")
HIGHLIGHT_COLUMNS = ("id", "book_id", "locator", "fraction", "text", "color", "comment",
                     "created_at", "updated_at", "device_id", "deleted", "kind")
KINDS = {"text", "image"}


class Rejected(Exception):
    """One change is invalid. The rest of the batch still applies."""


def book_payload(row) -> dict:
    """The client-facing view of a books row (no server paths)."""
    data = dict(zip(BOOK_COLUMNS, row, strict=True))
    data["has_cover"] = data.pop("cover_path") is not None
    data["deleted"] = bool(data["deleted"])
    return data


def highlight_payload(row) -> dict:
    data = dict(zip(HIGHLIGHT_COLUMNS, row, strict=True))
    data["deleted"] = bool(data["deleted"])
    return data


def get_book_row(conn: sqlite3.Connection, book_id: str):
    return conn.execute(
        f"SELECT {', '.join(BOOK_COLUMNS)} FROM books WHERE id = ?", (book_id,)
    ).fetchone()


def _get_highlight_row(conn: sqlite3.Connection, highlight_id: str):
    return conn.execute(
        f"SELECT {', '.join(HIGHLIGHT_COLUMNS)} FROM highlights WHERE id = ?", (highlight_id,)
    ).fetchone()


def _append(conn, entity: str, entity_id: str, op: str, payload: dict, device_id: str,
            now: str) -> None:
    conn.execute(
        "INSERT INTO changes (entity, entity_id, op, payload, device_id, ts) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (entity, entity_id, op, json.dumps(payload, ensure_ascii=False), device_id, now),
    )


def _timestamp(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise Rejected(f"{key} must be YYYY-MM-DDTHH:MM:SS.mmmZ")
    return value


def _text(data: dict, key: str, *, max_len: int, required: bool = True) -> str:
    value = data.get(key)
    if value is None and not required:
        value = ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise Rejected(f"{key} is required")
    if len(value) > max_len:
        raise Rejected(f"{key} is longer than {max_len} characters")
    return value


def _fraction(data: dict) -> float:
    value = data.get("fraction")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise Rejected("fraction must be a number")
    value = float(value)
    if math.isnan(value) or not 0.0 <= value <= 1.0:
        raise Rejected("fraction must be between 0 and 1")
    return value


def _wins(new_ts: str, new_device: str, old_ts: str, old_device: str) -> bool:
    return (new_ts, new_device) > (old_ts, old_device)


def _apply_highlight(conn, device_id: str, op: str, data: dict, now: str) -> tuple[str, str]:
    highlight_id = data.get("id")
    if not isinstance(highlight_id, str) or not ULID_RE.fullmatch(highlight_id):
        raise Rejected("id must be a ULID")
    updated_at = _timestamp(data, "updated_at")
    existing = _get_highlight_row(conn, highlight_id)

    if op == "delete":
        if existing is None:
            raise Rejected("unknown highlight")
        current = highlight_payload(existing)
        if current["deleted"] or not _wins(updated_at, device_id, current["updated_at"],
                                           current["device_id"]):
            return "ignored", current["book_id"]
        conn.execute(
            "UPDATE highlights SET deleted = 1, updated_at = ?, device_id = ? WHERE id = ?",
            (updated_at, device_id, highlight_id),
        )
    else:
        book_id = _text(data, "book_id", max_len=64)
        if get_book_row(conn, book_id) is None:
            raise Rejected("unknown book")
        record = {
            "id": highlight_id,
            "book_id": book_id,
            "locator": _text(data, "locator", max_len=MAX_LOCATOR),
            "fraction": _fraction(data),
            "text": _text(data, "text", max_len=MAX_TEXT),
            "color": data.get("color", "yellow"),
            "comment": _text(data, "comment", max_len=MAX_TEXT, required=False),
            "created_at": _timestamp(data, "created_at"),
            "updated_at": updated_at,
            "device_id": device_id,
            "kind": data.get("kind", "text"),
        }
        if record["color"] not in COLORS:
            raise Rejected(f"color must be one of {sorted(COLORS)}")
        if record["kind"] not in KINDS:
            raise Rejected("kind must be text or image")
        if existing is not None:
            current = highlight_payload(existing)
            if current["book_id"] != book_id:
                raise Rejected("a highlight cannot move to another book")
            # Tombstones are final: an offline edit never resurrects a deleted highlight.
            if current["deleted"] or not _wins(updated_at, device_id, current["updated_at"],
                                               current["device_id"]):
                return "ignored", book_id
        conn.execute(
            "INSERT INTO highlights (id, book_id, locator, fraction, text, color, comment, "
            "created_at, updated_at, device_id, deleted, kind) "
            "VALUES (:id, :book_id, :locator, :fraction, :text, :color, :comment, "
            ":created_at, :updated_at, :device_id, 0, :kind) "
            "ON CONFLICT (id) DO UPDATE SET locator = excluded.locator, "
            "fraction = excluded.fraction, text = excluded.text, color = excluded.color, "
            "comment = excluded.comment, updated_at = excluded.updated_at, "
            "device_id = excluded.device_id",
            record,
        )
    payload = highlight_payload(_get_highlight_row(conn, highlight_id))
    _append(conn, "highlight", highlight_id, op, payload, device_id, now)
    return "accepted", payload["book_id"]


def _apply_progress(conn, device_id: str, data: dict, now: str) -> str:
    book_id = _text(data, "book_id", max_len=64)
    if get_book_row(conn, book_id) is None:
        raise Rejected("unknown book")
    progress = Progress(
        book_id=book_id,
        device_id=device_id,  # a device only ever writes its own position
        locator=_text(data, "locator", max_len=MAX_LOCATOR),
        fraction=_fraction(data),
        updated_at=_timestamp(data, "updated_at"),
    )
    if not upsert_progress(conn, progress):
        return "ignored"
    _append(conn, "progress", f"{book_id}:{device_id}", "upsert", asdict(progress), device_id,
            now)
    return "accepted"


def _apply_book(conn, device_id: str, op: str, data: dict, now: str) -> str:
    book_id = _text(data, "id", max_len=64)
    row = get_book_row(conn, book_id)
    if row is None:
        raise Rejected("unknown book")
    current = book_payload(row)
    updated_at = _timestamp(data, "updated_at")
    if current["deleted"] or updated_at <= current["updated_at"]:
        return "ignored"
    if op == "delete":
        conn.execute("UPDATE books SET deleted = 1, updated_at = ? WHERE id = ?",
                     (updated_at, book_id))
    else:
        title = _text(data, "title", max_len=500)
        author = data.get("author")
        if author is not None and (not isinstance(author, str) or len(author) > 500):
            raise Rejected("author must be text")
        conn.execute("UPDATE books SET title = ?, author = ?, updated_at = ? WHERE id = ?",
                     (title, author or None, updated_at, book_id))
    _append(conn, "book", book_id, op, book_payload(get_book_row(conn, book_id)), device_id, now)
    return "accepted"


def push(conn: sqlite3.Connection, device_id: str, changes: list, now: str
         ) -> tuple[list[dict], set[str]]:
    """Apply a batch. Returns per-change results and the books whose highlights changed."""
    results: list[dict] = []
    touched: set[str] = set()
    # One write transaction for the batch: concurrent pushes queue on the lock
    # (busy_timeout) instead of failing halfway with SQLITE_BUSY.
    conn.execute("BEGIN IMMEDIATE")
    try:
        _push_batch(conn, device_id, changes, now, results, touched)
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
    return results, touched


def _push_batch(conn, device_id: str, changes: list, now: str, results: list[dict],
                touched: set[str]) -> None:
    for index, change in enumerate(changes):
        try:
            if not isinstance(change, dict) or not isinstance(change.get("data"), dict):
                raise Rejected("change must be an object with a data object")
            entity, op, data = change.get("entity"), change.get("op", "upsert"), change["data"]
            if op not in ("upsert", "delete"):
                raise Rejected("op must be upsert or delete")
            conn.execute("SAVEPOINT change")
            try:
                if entity == "highlight":
                    status, book_id = _apply_highlight(conn, device_id, op, data, now)
                    if status == "accepted":
                        touched.add(book_id)
                elif entity == "progress":
                    status = _apply_progress(conn, device_id, data, now)
                elif entity == "book":
                    status = _apply_book(conn, device_id, op, data, now)
                else:
                    raise Rejected("entity must be highlight, progress or book")
            except BaseException:
                conn.execute("ROLLBACK TO change")
                conn.execute("RELEASE change")
                raise
            conn.execute("RELEASE change")
            results.append({"index": index, "status": status})
        except Rejected as e:
            results.append({"index": index, "status": "rejected", "reason": str(e)})
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            # Wrong JSON shapes (a list where text belongs, and so on) are the
            # sender's problem: reject that record, never fail the batch.
            results.append({"index": index, "status": "rejected",
                            "reason": f"malformed record ({type(e).__name__})"})


def record_book_import(conn: sqlite3.Connection, book_id: str, device_id: str, now: str) -> dict:
    """Log a new or restored book so other devices see it on their next pull."""
    payload = book_payload(get_book_row(conn, book_id))
    _append(conn, "book", book_id, "upsert", payload, device_id, now)
    return payload


def pull(conn: sqlite3.Connection, since: int, limit: int = 500) -> dict:
    rows = conn.execute(
        "SELECT seq, entity, entity_id, op, payload, device_id, ts FROM changes "
        "WHERE seq > ? ORDER BY seq LIMIT ?",
        (since, limit),
    ).fetchall()
    changes = [
        {"seq": r[0], "entity": r[1], "entity_id": r[2], "op": r[3],
         "data": json.loads(r[4]), "device_id": r[5], "ts": r[6]}
        for r in rows
    ]
    latest = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM changes").fetchone()[0]
    # `latest` lets a client whose cursor is ahead of the hub (the hub was reset)
    # notice, start again from zero and re-pull everything.
    return {"changes": changes, "cursor": rows[-1][0] if rows else since,
            "more": len(rows) == limit, "latest": latest}
