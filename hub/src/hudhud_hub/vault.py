# SPDX-License-Identifier: AGPL-3.0-or-later
"""Writes each book's highlights into a managed region of an Obsidian note."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

START = "<!-- hudhud:start (managed by Hudhud; edit highlights in the app) -->"
START_PREFIX = "<!-- hudhud:start"
END = "<!-- hudhud:end -->"
INTRO = "Anything written outside the markers is yours. Hudhud never changes it."
FORBIDDEN = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL",
                    *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_TITLE_BYTES = 150


@dataclass(frozen=True)
class BookMeta:
    id: str
    title: str
    author: str | None
    language: str | None


@dataclass(frozen=True)
class Highlight:
    id: str
    text: str
    comment: str
    fraction: float
    created_at: str


@dataclass(frozen=True)
class WriteResult:
    path: Path
    region_hash: str
    conflict_path: Path | None


def sanitize_title(title: str, fallback: str) -> str:
    s = re.sub(r"\s+", " ", FORBIDDEN.sub(" ", title)).strip().rstrip(". ")
    s = s.encode("utf-8")[:MAX_TITLE_BYTES].decode("utf-8", "ignore").rstrip(". ")
    if not s:
        return fallback
    if s.split(".")[0].upper() in WINDOWS_RESERVED:
        s += "_"
    return s


def block_id(highlight_id: str) -> str:
    return f"h-{highlight_id.lower()}"


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _escape(text: str) -> str:
    return text.replace("<!--", "&lt;!--")


def _normalize(text: str) -> str:
    return text.removeprefix("﻿").replace("\r\n", "\n")


def render_frontmatter(book: BookMeta) -> str:
    lines = ["---", f"hudhud_book_id: {book.id}", f"title: {_quote(book.title)}"]
    if book.author:
        lines.append(f"author: {_quote(book.author)}")
    if book.language:
        lines.append(f"language: {_quote(book.language)}")
    lines += ["tags: [book, hudhud]", "---"]
    return "\n".join(lines) + "\n"


def _render_highlight(book_id: str, h: Highlight, hub_url: str) -> str:
    quote = "\n".join(f"> {line}".rstrip() for line in _escape(h.text).strip().splitlines())
    parts = [quote, "", f"^{block_id(h.id)}", ""]
    if h.comment.strip():
        parts.append(f"*Comment:* {' '.join(_escape(h.comment).split())}")
    link = f"{hub_url.rstrip('/')}/read/{book_id}?h={h.id.upper()}"
    parts.append(f"*Location:* {round(h.fraction * 100)}% · [Open in reader]({link})")
    return "\n".join(parts)


def render_region(book: BookMeta, highlights: list[Highlight], hub_url: str) -> str:
    ordered = sorted(highlights, key=lambda h: (h.fraction, h.created_at, h.id))
    body = "\n\n".join(_render_highlight(book.id, h, hub_url) for h in ordered)
    return f"{START}\n## Highlights\n\n{body or '_No highlights yet._'}\n{END}"


def extract_region(text: str) -> str | None:
    text = _normalize(text)
    start = text.find(START_PREFIX)
    if start == -1:
        return None
    end = text.find(END, start)
    if end == -1:
        return None
    return text[start:end + len(END)]


def merge_region(existing: str | None, book: BookMeta, region: str) -> str:
    if existing is None:
        return f"{render_frontmatter(book)}\n# {book.title}\n\n{INTRO}\n\n{region}\n"
    text = _normalize(existing)
    current = extract_region(text)
    if current is None:
        return f"{text.rstrip(chr(10))}\n\n{region}\n"
    return text.replace(current, region, 1)


def region_hash(region: str) -> str:
    return hashlib.sha256(_normalize(region).strip().encode("utf-8")).hexdigest()


def frontmatter_book_id(text: str) -> str | None:
    m = re.match(r"---\n(.*?)\n---\n", _normalize(text), re.S)
    if not m:
        return None
    for line in m.group(1).splitlines():
        if line.startswith("hudhud_book_id:"):
            return line.split(":", 1)[1].strip()
    return None


def safe_join(root: Path, *parts: str) -> Path:
    base = Path(root).resolve()
    path = base.joinpath(*parts).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"path escapes the vault: {path}")
    return path


def atomic_write(path: Path, text: str, retries: int = 5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(retries):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == retries - 1:
                    raise
                time.sleep(0.1)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def note_path(vault_root: Path, subfolder: str, book: BookMeta) -> Path:
    base = sanitize_title(book.title, fallback=book.id[:12])
    path = safe_join(vault_root, subfolder, f"{base}.md")
    if path.exists():
        owner = frontmatter_book_id(path.read_text(encoding="utf-8"))
        if owner is not None and owner != book.id:
            path = safe_join(vault_root, subfolder, f"{base} ({book.id[:8]}).md")
    return path


def write_book_note(vault_root: Path, subfolder: str, book: BookMeta,
                    highlights: list[Highlight], hub_url: str,
                    last_hash: str | None, now: str) -> WriteResult:
    path = note_path(vault_root, subfolder, book)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    conflict = None
    if existing is not None and last_hash is not None:
        current = extract_region(existing)
        if current is not None and region_hash(current) != last_hash:
            stamp = re.sub(r"[-:]|\.\d+", "", now)
            conflict = path.with_name(f"{path.stem}.conflict-{stamp}.md")
            shutil.copy2(path, conflict)
    region = render_region(book, highlights, hub_url)
    atomic_write(path, merge_region(existing, book, region))
    return WriteResult(path, region_hash(region), conflict)
