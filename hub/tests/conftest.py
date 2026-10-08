# SPDX-License-Identifier: AGPL-3.0-or-later
import pymupdf
import pytest

from hudhud_hub.config import Config
from hudhud_hub.db import MIGRATIONS, apply_migrations, connect, insert_book


def pdf_bytes(title: str = "Paper Title", author: str = "P. Author", text: str = "Hello") -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    doc.set_metadata({"title": title, "author": author})
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def config(tmp_path) -> Config:
    vault = tmp_path / "vault"
    vault.mkdir()
    return Config(data_dir=tmp_path / "data", vault_path=vault, public_url="http://hub.test:8765")


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "hub.db")
    apply_migrations(c, MIGRATIONS)
    yield c
    c.close()


BOOK_ID = "a" * 64


@pytest.fixture
def book(conn) -> str:
    insert_book(conn, {"id": BOOK_ID, "title": "Masnavi", "author": "Rumi", "language": "fa",
                       "format": "epub", "file_size": 1, "cover_path": None},
                "2026-10-08T09:00:00.000Z")
    return BOOK_ID
