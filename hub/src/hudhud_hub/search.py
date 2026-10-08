# SPDX-License-Identifier: AGPL-3.0-or-later
"""Semantic search over highlights, their notes, and the Obsidian vault (spec section 10).

Each highlight gives a 'text' chunk and, when it has one, a 'note' chunk, so a
selection can match either what you highlighted or what you wrote about it. Vault
notes are chunked by heading, with Hudhud's managed regions left out (those
highlights are already indexed directly). Embeddings live in the chunks table and
are searched in memory: at personal scale a matrix product is instant.
"""

from __future__ import annotations

import hashlib
import logging
import queue
import re
import sqlite3
import threading
import urllib.parse
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .config import Config
from .db import connect, utc_now
from .embedder import Embedder, FastEmbedder
from .vault import END, START_PREFIX

log = logging.getLogger(__name__)

MAX_CHUNK = 1200
SKIP_DIRS = {".obsidian", ".trash", ".git", "attachments"}
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)

EmbedderFactory = Callable[[str, Path], Embedder]


def _strip_managed(text: str) -> str:
    while (start := text.find(START_PREFIX)) != -1:
        end = text.find(END, start)
        if end == -1:
            break
        text = text[:start] + text[end + len(END):]
    return text


def vault_chunks(markdown: str) -> list[tuple[str, str]]:
    """(heading, chunk text) pairs: frontmatter and managed regions removed, split by
    heading, long sections split on paragraph boundaries."""
    text = _strip_managed(_FRONTMATTER.sub("", markdown.replace("\r\n", "\n"), count=1))
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.split("\n"):
        match = _HEADING.match(line)
        if match:
            sections.append((match.group(2).strip(), []))
        else:
            sections[-1][1].append(line)
    chunks: list[tuple[str, str]] = []
    for heading, lines in sections:
        paragraphs = [p.strip() for p in "\n".join(lines).split("\n\n") if p.strip()]
        piece = ""
        for paragraph in paragraphs:
            if piece and len(piece) + len(paragraph) > MAX_CHUNK:
                chunks.append((heading, piece))
                piece = ""
            piece = f"{piece}\n\n{paragraph}" if piece else paragraph
        if piece:
            chunks.append((heading, piece))
    return [(h, f"{h}\n{body}" if h else body) for h, body in chunks if len(body) >= 3]


class SearchIndex:
    def __init__(self, config: Config, embedder_factory: EmbedderFactory | None = None,
                 threshold: float | None = None):
        self.config = config
        self.threshold = config.similarity_threshold if threshold is None else threshold
        self._factory = embedder_factory or FastEmbedder
        self.embedder: Embedder | None = None
        self.error: str | None = None
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._lock = threading.Lock()
        self._matrix: np.ndarray | None = None
        self._rows: list[tuple] = []
        self._observer = None

    # -- lifecycle ---------------------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self.embedder is not None

    def load(self) -> None:
        self.config.models_dir.mkdir(parents=True, exist_ok=True)
        self.embedder = self._factory(self.config.embed_model, self.config.models_dir)

    def start(self) -> None:
        """Load the model, catch up on everything, then follow changes (background)."""
        threading.Thread(target=self._run, name="hudhud-search", daemon=True).start()

    def _run(self) -> None:
        try:
            self.load()
        except Exception as e:  # no network on first start, disk full, ...
            self.error = f"search model could not load: {e}"
            log.error(self.error)
            return
        self.enqueue_all()
        self._watch_vault()
        while True:
            self._process(self._queue.get())

    def _watch_vault(self) -> None:
        vault = self.config.vault_path
        if vault is None or not vault.is_dir():
            return
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        index = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                for path in (getattr(event, "src_path", ""), getattr(event, "dest_path", "")):
                    if str(path).endswith(".md"):
                        index._queue.put(("vault", str(path)))

        observer = Observer()
        observer.schedule(Handler(), str(vault), recursive=True)
        observer.daemon = True
        observer.start()
        self._observer = observer

    # -- queue -------------------------------------------------------------------------

    def enqueue_book(self, book_id: str) -> None:
        self._queue.put(("book", book_id))

    def enqueue_vault_all(self) -> None:
        self._queue.put(("vault_all", ""))

    def enqueue_all(self) -> None:
        self._queue.put(("all", ""))

    def process_pending(self) -> None:
        """Index everything queued, now, on this thread (tests and tools)."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            self._process(item)

    def _process(self, item: tuple[str, str]) -> None:
        if self.embedder is None:
            return
        kind, value = item
        conn = connect(self.config.db_path)
        try:
            if kind == "book":
                self._index_book(conn, value)
            elif kind == "vault":
                self._index_vault_file(conn, Path(value))
            elif kind == "vault_all":
                self._index_vault(conn)
            elif kind == "all":
                books = [r[0] for r in conn.execute("SELECT id FROM books")]
                for book_id in books:
                    self._index_book(conn, book_id)
                self._index_vault(conn)
        except Exception as e:
            log.exception("indexing %s %s failed: %s", kind, value, e)
        finally:
            conn.close()

    # -- indexing ----------------------------------------------------------------------

    def _hash(self, text: str) -> str:
        return hashlib.sha256(f"{self.embedder.model}\n{text}".encode()).hexdigest()

    def _sync_scope(self, conn: sqlite3.Connection, where: str, params: tuple,
                    wanted: list[tuple[str, str, str, str | None, str]]) -> None:
        """Make the chunks matching `where` exactly `wanted`
        ((source_kind, source_ref, field, book_id, text) rows), embedding only what changed."""
        existing = {(r[0], r[1], r[2]): (r[3], r[4]) for r in conn.execute(
            f"SELECT source_kind, source_ref, field, content_hash, model FROM chunks WHERE {where}",
            params)}
        model = self.embedder.model
        todo = [w for w in wanted
                if existing.get((w[0], w[1], w[2])) != (self._hash(w[4]), model)]
        keys = {(w[0], w[1], w[2]) for w in wanted}
        stale = [k for k in existing if k not in keys]
        if not todo and not stale:
            return
        vectors = self.embedder.embed_documents([w[4] for w in todo]) if todo else []
        now = utc_now()
        conn.execute("BEGIN IMMEDIATE")
        try:
            for w, vector in zip(todo, vectors, strict=True):
                conn.execute(
                    "INSERT INTO chunks (source_kind, source_ref, field, book_id, text, "
                    "content_hash, model, updated_at, embedding) VALUES (?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT (source_kind, source_ref, field) DO UPDATE SET "
                    "book_id = excluded.book_id, text = excluded.text, "
                    "content_hash = excluded.content_hash, model = excluded.model, "
                    "updated_at = excluded.updated_at, embedding = excluded.embedding",
                    (w[0], w[1], w[2], w[3], w[4], self._hash(w[4]), model, now,
                     np.asarray(vector, dtype=np.float32).tobytes()))
            for kind, ref, field in stale:
                conn.execute("DELETE FROM chunks WHERE source_kind = ? AND source_ref = ? "
                             "AND field = ?", (kind, ref, field))
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        with self._lock:
            self._matrix = None

    def _index_book(self, conn: sqlite3.Connection, book_id: str) -> None:
        wanted = []
        for r in conn.execute(
                "SELECT h.id, h.text, h.comment FROM highlights h JOIN books b ON b.id = h.book_id "
                "WHERE h.book_id = ? AND h.deleted = 0 AND b.deleted = 0", (book_id,)):
            if r[1].strip():
                wanted.append(("highlight", r[0], "text", book_id, r[1].strip()))
            if r[2].strip():
                wanted.append(("highlight", r[0], "note", book_id, r[2].strip()))
        self._sync_scope(conn, "source_kind = 'highlight' AND book_id = ?", (book_id,), wanted)

    def _vault_ref(self, path: Path) -> str | None:
        vault = self.config.vault_path
        if vault is None:
            return None
        try:
            rel = path.resolve().relative_to(vault.resolve())
        except ValueError:
            return None
        if set(rel.parts[:-1]) & SKIP_DIRS or ".conflict-" in rel.name:
            return None
        return rel.as_posix()

    def _index_vault_file(self, conn: sqlite3.Connection, path: Path) -> None:
        ref = self._vault_ref(path)
        if ref is None:
            return
        wanted = []
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            wanted = [("vault", f"{ref}#{i}", "vault", None, chunk)
                      for i, (_, chunk) in enumerate(vault_chunks(text))]
        prefix = ref.replace("%", r"\%").replace("_", r"\_") + "#%"
        self._sync_scope(conn, r"source_kind = 'vault' AND source_ref LIKE ? ESCAPE '\'",
                         (prefix,), wanted)

    def _index_vault(self, conn: sqlite3.Connection) -> None:
        vault = self.config.vault_path
        present = set()
        if vault is not None and vault.is_dir():
            for path in vault.rglob("*.md"):
                if self._vault_ref(path) is not None:
                    present.add(self._vault_ref(path))
                    self._index_vault_file(conn, path)
        # Notes deleted while the hub was off.
        known = {r[0].rsplit("#", 1)[0] for r in conn.execute(
            "SELECT DISTINCT source_ref FROM chunks WHERE source_kind = 'vault'")}
        for ref in known - present:
            self._sync_scope(conn, r"source_kind = 'vault' AND source_ref LIKE ? ESCAPE '\'",
                             (ref.replace("%", r"\%").replace("_", r"\_") + "#%",), [])

    # -- search ------------------------------------------------------------------------

    def _load_matrix(self) -> tuple[np.ndarray, list[tuple]]:
        with self._lock:
            if self._matrix is not None:
                return self._matrix, self._rows
        conn = connect(self.config.db_path)
        try:
            rows = conn.execute(
                "SELECT source_kind, source_ref, field, book_id, text, embedding FROM chunks "
                "WHERE model = ? AND embedding IS NOT NULL", (self.embedder.model,)).fetchall()
        finally:
            conn.close()
        meta = [tuple(r[:5]) for r in rows]
        matrix = (np.stack([np.frombuffer(r[5], dtype=np.float32) for r in rows])
                  if rows else np.zeros((0, 1), dtype=np.float32))
        with self._lock:
            self._matrix, self._rows = matrix, meta
        return matrix, meta

    def search(self, text: str, book_id: str | None = None, k: int = 5) -> list[dict]:
        if self.embedder is None:
            raise RuntimeError("search is not ready")
        matrix, rows = self._load_matrix()
        if not rows:
            return []
        scores = matrix @ self.embedder.embed_query(text)
        best: dict[tuple[str, str], tuple[float, tuple]] = {}
        for i in np.argsort(-scores):
            score = float(scores[i])
            if score < self.threshold:
                break
            kind, ref, field, chunk_book, chunk_text = rows[i]
            if kind == "highlight" and book_id and chunk_book == book_id:
                continue  # the point is to find what you wrote in *other* books
            key = (kind, ref if kind == "highlight" else ref.rsplit("#", 1)[0])
            if key not in best:
                best[key] = (score, rows[i])
            if len(best) >= k:
                break
        return self._describe(sorted(best.values(), key=lambda x: -x[0]))

    def _describe(self, hits: list[tuple[float, tuple]]) -> list[dict]:
        conn = connect(self.config.db_path)
        try:
            results = []
            for score, (kind, ref, field, book_id, text) in hits:
                result = {"kind": kind, "match": field, "score": round(score, 3), "text": text,
                          "book_id": book_id, "book_title": None, "highlight": None,
                          "path": None, "obsidian_url": None}
                if kind == "highlight":
                    h = conn.execute(
                        "SELECT h.id, h.book_id, h.locator, h.fraction, h.text, h.comment, "
                        "h.color, h.kind, b.title FROM highlights h JOIN books b "
                        "ON b.id = h.book_id WHERE h.id = ?", (ref,)).fetchone()
                    if h is None:
                        continue
                    result["highlight"] = dict(zip(
                        ("id", "book_id", "locator", "fraction", "text", "comment", "color",
                         "kind"), tuple(h)[:8], strict=True))
                    result["book_title"] = h[8]
                else:
                    path = ref.rsplit("#", 1)[0]
                    result["path"] = path
                    vault = self.config.vault_path
                    if vault is not None:
                        result["obsidian_url"] = (
                            "obsidian://open?vault=" + urllib.parse.quote(vault.name)
                            + "&file=" + urllib.parse.quote(path.removesuffix(".md")))
                results.append(result)
            return results
        finally:
            conn.close()
