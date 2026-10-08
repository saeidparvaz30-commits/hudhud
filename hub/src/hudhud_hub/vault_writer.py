# SPDX-License-Identifier: AGPL-3.0-or-later
"""Keeps each book's vault note in step with its highlights, debounced per book."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .config import Config
from .db import connect, utc_now
from .vault import BookMeta, Highlight, write_book_note

log = logging.getLogger(__name__)


class VaultWriter:
    def __init__(self, config: Config, delay: float = 2.0):
        self.config = config
        self.delay = delay
        self.last_error: str | None = None
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.config.vault_path is not None

    def ok(self) -> bool:
        vault = self.config.vault_path
        return vault is not None and vault.is_dir() and self.last_error is None

    def schedule(self, book_id: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            if (timer := self._timers.pop(book_id, None)) is not None:
                timer.cancel()
            timer = threading.Timer(self.delay, self._fire, [book_id])
            timer.daemon = True
            self._timers[book_id] = timer
            timer.start()

    def flush(self) -> None:
        """Write every pending note now (tests, shutdown)."""
        with self._lock:
            pending = list(self._timers)
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        for book_id in pending:
            self.write_now(book_id)

    def _fire(self, book_id: str) -> None:
        with self._lock:
            self._timers.pop(book_id, None)
        self.write_now(book_id)

    def write_now(self, book_id: str) -> Path | None:
        if not self.enabled:
            return None
        conn = connect(self.config.db_path)
        try:
            book = conn.execute(
                "SELECT id, title, author, language FROM books WHERE id = ? AND deleted = 0",
                (book_id,),
            ).fetchone()
            if book is None:
                return None
            highlights = [
                Highlight(r["id"], r["text"], r["comment"], r["fraction"], r["created_at"])
                for r in conn.execute(
                    "SELECT id, text, comment, fraction, created_at FROM highlights "
                    "WHERE book_id = ? AND deleted = 0",
                    (book_id,),
                )
            ]
            previous = conn.execute(
                "SELECT region_hash FROM vault_notes WHERE book_id = ?", (book_id,)
            ).fetchone()
            result = write_book_note(
                self.config.vault_path,
                self.config.vault_subfolder,
                BookMeta(book["id"], book["title"], book["author"], book["language"]),
                highlights,
                self.config.base_url,
                previous["region_hash"] if previous else None,
                utc_now(),
            )
            conn.execute(
                "INSERT INTO vault_notes (book_id, path, region_hash) VALUES (?, ?, ?) "
                "ON CONFLICT (book_id) DO UPDATE SET path = excluded.path, "
                "region_hash = excluded.region_hash",
                (book_id, str(result.path), result.region_hash),
            )
            if result.conflict_path:
                log.warning("vault note was edited inside the managed region; saved %s",
                            result.conflict_path)
            self.last_error = None
            return result.path
        except (OSError, ValueError) as e:
            self.last_error = str(e)
            log.error("could not write vault note for %s: %s", book_id, e)
            return None
        finally:
            conn.close()
