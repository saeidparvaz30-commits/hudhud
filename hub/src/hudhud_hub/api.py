# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP API: a thin adapter over the hub modules (spec section 4.2).

No `from __future__ import annotations` here: FastAPI must resolve the
dependency aliases defined inside create_app at decoration time.
"""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import __version__
from .auth import (
    PairingError,
    authenticate,
    create_pairing_code,
    format_code,
    list_devices,
    pairing_expiry,
    pairing_url,
    qr_svg,
    redeem_pairing_code,
    revoke_device,
)
from .config import Config
from .db import MIGRATIONS, apply_migrations, connect, insert_book, new_ulid, utc_now
from .library import MAX_BYTES, ImportRejected, import_book
from .sync import book_payload, get_book_row, pull, push, record_book_import
from .vault_writer import VaultWriter

SOURCE_URL = "https://github.com/saeidparvaz30-commits/hudhud"
BOOK_ID_RE = re.compile(r"[0-9a-f]{64}")
CHUNK = 1 << 20
MEDIA_TYPES = {
    "epub": "application/epub+zip",
    "pdf": "application/pdf",
    "mobi": "application/x-mobipocket-ebook",
    "azw3": "application/vnd.amazon.ebook",
    "fb2": "application/x-fictionbook+xml",
    "cbz": "application/vnd.comicbook+zip",
    "txt": "text/plain; charset=utf-8",
}
IMMUTABLE = {"Cache-Control": "private, max-age=31536000, immutable"}


class PairRequest(BaseModel):
    code: str = Field(max_length=32)
    device_name: str = Field(default="Device", max_length=200)


class PushRequest(BaseModel):
    changes: list = Field(max_length=1000)


class SearchRequest(BaseModel):
    text: str
    book_id: str | None = None
    k: int = 5


def create_app(config: Config, vault_writer: VaultWriter | None = None) -> FastAPI:
    config.library_dir.mkdir(parents=True, exist_ok=True)
    with closing(connect(config.db_path)) as conn:
        apply_migrations(conn, MIGRATIONS)
    writer = vault_writer or VaultWriter(config)

    app = FastAPI(title="Hudhud hub", version=__version__)
    app.state.config = config
    app.state.vault = writer
    # Rule R1: the client may be served from anywhere. Auth is a bearer token, never a
    # cookie, so an open CORS policy grants nothing without the token.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = connect(config.db_path)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[sqlite3.Connection, Depends(get_conn)]

    def current_device(conn: Conn, authorization: Annotated[str | None, Header()] = None) -> str:
        scheme, _, token = (authorization or "").partition(" ")
        device = authenticate(conn, token, utc_now()) if scheme.lower() == "bearer" else None
        if device is None:
            raise HTTPException(401, "pair this device first", {"WWW-Authenticate": "Bearer"})
        return device

    Device = Annotated[str, Depends(current_device)]

    def live_book(conn: sqlite3.Connection, book_id: str):
        row = get_book_row(conn, book_id) if BOOK_ID_RE.fullmatch(book_id) else None
        if row is None or row["deleted"]:
            raise HTTPException(404, "no such book")
        return row

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "version": __version__, "search_ready": False,
                "vault_enabled": writer.enabled, "vault_ok": writer.ok()}

    @app.get("/about")
    def about() -> dict:
        return {"name": "Hudhud", "version": __version__, "license": "AGPL-3.0-or-later",
                "source": SOURCE_URL}

    @app.post("/pair")
    def pair(body: PairRequest, conn: Conn) -> dict:
        try:
            device_id, token = redeem_pairing_code(conn, body.code, body.device_name, utc_now())
        except PairingError as e:
            raise HTTPException(403, str(e)) from e
        return {"device_id": device_id, "token": token}

    @app.post("/pairing-codes", status_code=201)
    def invite(conn: Conn, device: Device) -> dict:
        """A paired device invites another: one-time code, link and QR for the new one."""
        now = utc_now()
        code = create_pairing_code(conn, now)
        url = pairing_url(config.base_url, code)
        return {"code": code, "display": format_code(code), "url": url, "qr_svg": qr_svg(url),
                "expires_at": pairing_expiry(now)}

    @app.get("/devices")
    def devices(conn: Conn, device: Device) -> list[dict]:
        return [{**d, "current": d["id"] == device} for d in list_devices(conn)]

    @app.delete("/devices/{device_id}")
    def delete_device(device_id: str, conn: Conn, device: Device) -> dict:
        if not revoke_device(conn, device_id):
            raise HTTPException(404, "no such device")
        return {"revoked": device_id}

    @app.get("/books")
    def books(conn: Conn, device: Device) -> list[dict]:
        rows = conn.execute(
            "SELECT id FROM books WHERE deleted = 0 ORDER BY added_at DESC"
        ).fetchall()
        return [book_payload(get_book_row(conn, r["id"])) for r in rows]

    @app.post("/books", status_code=201)
    async def upload(request: Request, conn: Conn, device: Device,
                     filename: Annotated[str, Query(max_length=255)] = "book",
                     content_length: Annotated[int | None, Header()] = None) -> dict:
        """The book is the raw request body. Auth and the declared size are checked
        before a single byte is read, so nobody can fill the disk without a token."""
        if content_length is not None and content_length > MAX_BYTES:
            raise HTTPException(413, "books are limited to 500 MB")
        part = config.library_dir / f".upload-{new_ulid()}.part"
        try:
            size = 0
            with open(part, "wb") as out:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, "books are limited to 500 MB")
                    out.write(chunk)
            try:
                record = await run_in_threadpool(import_book, part, config.library_dir,
                                                 Path(filename).name)
            except ImportRejected as e:
                raise HTTPException(422, e.reason) from e
        finally:
            part.unlink(missing_ok=True)
        now = utc_now()
        fields = {k: getattr(record, k) for k in
                  ("id", "title", "author", "language", "format", "file_size", "cover_path")}
        if insert_book(conn, fields, now):
            return record_book_import(conn, record.id, device, now)
        return book_payload(get_book_row(conn, record.id))

    @app.get("/books/{book_id}/file")
    def book_file(book_id: str, conn: Conn, device: Device) -> FileResponse:
        row = live_book(conn, book_id)
        path = config.library_dir / f"{row['id']}.{row['format']}"
        if not path.is_file():
            raise HTTPException(410, "the book file is missing from the library")
        return FileResponse(path, media_type=MEDIA_TYPES[row["format"]], headers=IMMUTABLE)

    @app.get("/books/{book_id}/cover")
    def book_cover(book_id: str, conn: Conn, device: Device) -> FileResponse:
        row = live_book(conn, book_id)
        cover = Path(row["cover_path"]) if row["cover_path"] else None
        if cover is None or not cover.is_file():
            raise HTTPException(404, "this book has no cover")
        return FileResponse(cover, headers=IMMUTABLE)

    @app.post("/sync/push")
    def sync_push(body: PushRequest, conn: Conn, device: Device) -> dict:
        results, touched = push(conn, device, body.changes, utc_now())
        for book_id in touched:
            writer.schedule(book_id)
        return {"results": results}

    @app.get("/sync/pull")
    def sync_pull(conn: Conn, device: Device, since: Annotated[int, Query(ge=0)] = 0,
                  limit: Annotated[int, Query(ge=1, le=1000)] = 500) -> dict:
        return pull(conn, since, limit)

    @app.post("/search")
    def search(body: SearchRequest, device: Device) -> JSONResponse:
        return JSONResponse({"detail": "search is not available yet"}, status_code=503)

    if config.client_dir is not None:
        _mount_client(app, config.client_dir)
    return app


def _mount_client(app: FastAPI, client_dir: Path) -> None:
    root = client_dir.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def client(path: str) -> FileResponse:
        target = (root / path).resolve()
        if path and target.is_file() and target.is_relative_to(root):
            # Vite's hashed assets never change under the same name; everything else
            # (vendored foliate-js and pdf.js) revalidates so updates reach phones.
            cache = IMMUTABLE if path.startswith("assets/") else {"Cache-Control": "no-cache"}
            return FileResponse(target, headers=cache)
        if path == "" or path.startswith("read/") or path == "settings":
            if index.is_file():
                return FileResponse(index, headers={"Cache-Control": "no-cache"})
        raise HTTPException(404, "not found")
