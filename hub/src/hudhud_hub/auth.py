# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single-user device pairing: one-time codes exchanged for bearer tokens."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta

from .db import new_ulid

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base 32
CODE_LENGTH = 8
CODE_TTL = timedelta(minutes=10)
_CONFUSABLE = str.maketrans({"I": "1", "L": "1", "O": "0"})


class PairingError(Exception):
    pass


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _format(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_code(code: str) -> str:
    """Accept 'abcd-efgh', spaces and the usual Crockford look-alikes."""
    return "".join(code.split()).replace("-", "").upper().translate(_CONFUSABLE)


def format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def create_pairing_code(conn: sqlite3.Connection, now: str) -> str:
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    conn.execute(
        "INSERT INTO pairing_codes (code_hash, expires_at, used) VALUES (?, ?, 0)",
        (_hash(code), _format(_parse(now) + CODE_TTL)),
    )
    return code


def redeem_pairing_code(
    conn: sqlite3.Connection, code: str, device_name: str, now: str
) -> tuple[str, str]:
    """Spend a pairing code and return (device_id, token). The token is shown once."""
    cur = conn.execute(
        "UPDATE pairing_codes SET used = 1 WHERE code_hash = ? AND used = 0 AND expires_at > ?",
        (_hash(normalize_code(code)), now),
    )
    if cur.rowcount != 1:
        raise PairingError("invalid or expired pairing code")
    device_id = new_ulid()
    token = secrets.token_urlsafe(32)
    name = " ".join(device_name.split())[:80] or "Device"
    conn.execute(
        "INSERT INTO devices (id, name, token_hash, paired_at, last_seen) VALUES (?, ?, ?, ?, ?)",
        (device_id, name, _hash(token), now, now),
    )
    return device_id, token


def authenticate(conn: sqlite3.Connection, token: str, now: str) -> str | None:
    row = conn.execute("SELECT id FROM devices WHERE token_hash = ?", (_hash(token),)).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (now, row[0]))
    return row[0]


def list_devices(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, paired_at, last_seen FROM devices ORDER BY paired_at"
    ).fetchall()
    return [dict(zip(("id", "name", "paired_at", "last_seen"), r, strict=True)) for r in rows]


def revoke_device(conn: sqlite3.Connection, device_id: str) -> bool:
    return conn.execute("DELETE FROM devices WHERE id = ?", (device_id,)).rowcount == 1
