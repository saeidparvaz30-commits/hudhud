# SPDX-License-Identifier: AGPL-3.0-or-later
from contextlib import closing
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from hudhud_hub.api import create_app
from hudhud_hub.auth import create_pairing_code
from hudhud_hub.db import MIGRATIONS, apply_migrations, connect, insert_book, utc_now
from hudhud_hub.embedder import HashEmbedder
from hudhud_hub.search import SearchIndex, vault_chunks
from hudhud_hub.sync import push
from hudhud_hub.vault_writer import VaultWriter

from .conftest import pdf_bytes

A = "a" * 64
B = "b" * 64
T0 = "2026-10-08T10:00:00.000Z"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def hl(hid: str, book: str, text: str, comment: str = "", kind: str = "text") -> dict:
    return {"entity": "highlight", "data": {
        "id": hid, "book_id": book, "locator": "epubcfi(/6/4!/4/2/1:0)", "fraction": 0.3,
        "text": text, "comment": comment, "color": "yellow", "kind": kind,
        "created_at": T0, "updated_at": T0}}


@pytest.fixture
def library(config):
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with closing(connect(config.db_path)) as conn:
        apply_migrations(conn, MIGRATIONS)
        for book_id, title in ((A, "Thinking, Fast and Slow"), (B, "The Black Swan")):
            insert_book(conn, {"id": book_id, "title": title, "author": None, "language": "en",
                               "format": "epub", "file_size": 1, "cover_path": None}, T0)
    return config


@pytest.fixture
def index(library):
    idx = SearchIndex(library, embedder_factory=HashEmbedder, threshold=0.2)
    idx.load()
    return idx


def add(config, index, *changes):
    with closing(connect(config.db_path)) as conn:
        results, touched = push(conn, "pc", list(changes), T0)
    assert all(r["status"] == "accepted" for r in results), results
    for book in touched:
        index.enqueue_book(book)
    index.process_pending()


def chunk_rows(config):
    with closing(connect(config.db_path)) as conn:
        return conn.execute(
            "SELECT source_kind, source_ref, field FROM chunks ORDER BY source_ref, field"
        ).fetchall()


def test_a_highlight_and_its_note_are_indexed_separately(library, index):
    add(library, index, hl("01JB7X3K9Q2M4N5P6R7S8T9V0A", A, "intuitions are not reliable",
                           comment="compare with narrative fallacy"))
    assert [tuple(r) for r in chunk_rows(library)] == [
        ("highlight", "01JB7X3K9Q2M4N5P6R7S8T9V0A", "note"),
        ("highlight", "01JB7X3K9Q2M4N5P6R7S8T9V0A", "text")]


def test_deleting_a_highlight_removes_its_chunks(library, index):
    add(library, index, hl("01JB7X3K9Q2M4N5P6R7S8T9V0A", A, "some passage", comment="a note"))
    add(library, index, {"entity": "highlight", "op": "delete",
                         "data": {"id": "01JB7X3K9Q2M4N5P6R7S8T9V0A",
                                  "updated_at": "2026-10-08T11:00:00.000Z"}})
    assert chunk_rows(library) == []


def test_search_finds_a_note_in_another_book(library, index):
    add(library, index,
        hl("01JB7X3K9Q2M4N5P6R7S8T9V0A", A, "a passage about something else",
           comment="the narrative fallacy makes stories feel true"),
        hl("01JB7X3K9Q2M4N5P6R7S8T9V0B", B, "narrative fallacy stories"))
    results = index.search("why do stories feel true? the narrative fallacy", book_id=B, k=5)
    assert [r["highlight"]["id"] for r in results] == ["01JB7X3K9Q2M4N5P6R7S8T9V0A"]
    assert results[0]["match"] == "note"
    assert results[0]["book_title"] == "Thinking, Fast and Slow"


def test_unrelated_text_is_not_a_match(library, index):
    add(library, index, hl("01JB7X3K9Q2M4N5P6R7S8T9V0A", A, "intuition and confidence"))
    assert index.search("gardening tomatoes in spring soil", book_id=B, k=5) == []


def test_vault_notes_are_searched_but_managed_regions_are_not(library, index):
    vault = library.vault_path
    (vault / "Ideas.md").write_text(
        "---\ntags: [x]\n---\n# Stories\n\nWe trust stories over statistics.\n", encoding="utf-8")
    (vault / "Hudhud").mkdir()
    (vault / "Hudhud" / "Book.md").write_text(
        "# Book\n\nMy own words about statistics and stories.\n\n"
        "<!-- hudhud:start (managed by Hudhud; edit highlights in the app) -->\n"
        "## Highlights\n\n> statistics stories quoted text\n<!-- hudhud:end -->\n",
        encoding="utf-8")
    index.enqueue_vault_all()
    index.process_pending()
    results = index.search("stories and statistics", book_id=A, k=5)
    paths = sorted(r["path"] for r in results)
    assert paths == ["Hudhud/Book.md", "Ideas.md"]
    assert all("quoted text" not in r["text"] for r in results)
    assert results[0]["obsidian_url"].startswith("obsidian://open?vault=vault&file=")


def test_hudhud_book_notes_add_nothing_but_your_own_words():
    from hudhud_hub.vault import INTRO
    generated = "\n".join([
        "# Thinking, Fast and Slow", "", INTRO, "",
        "<!-- hudhud:start (x) -->", "> q", "<!-- hudhud:end -->", ""])
    assert vault_chunks(generated) == []
    assert vault_chunks(generated + "\nMy own thought.\n") == [
        ("Thinking, Fast and Slow", "Thinking, Fast and Slow\nMy own thought.")]


def test_vault_chunks_split_by_heading_and_drop_frontmatter():
    chunks = vault_chunks("---\na: 1\n---\nIntro line.\n\n## Part two\n\nSecond part text.\n")
    assert chunks == [("", "Intro line."), ("Part two", "Part two\nSecond part text.")]


def test_search_endpoint(library, index):
    client = TestClient(create_app(library, VaultWriter(library, delay=60), search_index=index))
    with closing(connect(library.db_path)) as conn:
        code = create_pairing_code(conn, utc_now())
    token = client.post("/pair", json={"code": code}).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    client.post("/sync/push", headers=auth, json={"changes": [
        hl("01JB7X3K9Q2M4N5P6R7S8T9V0A", A, "confidence in intuition", comment="not reliable")]})
    index.process_pending()
    assert client.get("/health").json()["search_ready"] is True
    found = client.post("/search", headers=auth,
                        json={"text": "is confidence in intuition reliable", "book_id": B}).json()
    assert found["results"][0]["highlight"]["id"] == "01JB7X3K9Q2M4N5P6R7S8T9V0A"


def test_search_is_503_until_the_model_is_loaded(library):
    idx = SearchIndex(library, embedder_factory=HashEmbedder)
    client = TestClient(create_app(library, VaultWriter(library, delay=60), search_index=idx))
    with closing(connect(library.db_path)) as conn:
        code = create_pairing_code(conn, utc_now())
    token = client.post("/pair", json={"code": code}).json()["token"]
    response = client.post("/search", headers={"Authorization": f"Bearer {token}"},
                           json={"text": "anything at all here"})
    assert response.status_code == 503


def test_picture_highlight_reaches_the_vault(library, index):
    app = create_app(library, VaultWriter(library, delay=60), search_index=index)
    client = TestClient(app)
    with closing(connect(library.db_path)) as conn:
        code = create_pairing_code(conn, utc_now())
    auth = {"Authorization": f"Bearer {client.post('/pair', json={'code': code}).json()['token']}"}
    book = client.post("/books", params={"filename": "b.pdf"}, headers=auth,
                       content=pdf_bytes("Pictures Book")).json()
    hid = "01JB7X3K9Q2M4N5P6R7S8T9V0C"
    change = hl(hid, book["id"], "Figure 1-13. Online learning", comment="nice loop", kind="image")
    assert client.post("/sync/push", headers=auth,
                       json={"changes": [change]}).json()["results"][0]["status"] == "accepted"
    assert client.put(f"/highlights/{hid}/image", headers=auth, content=b"not an image"
                      ).status_code == 422
    assert client.put(f"/highlights/{hid}/image", headers=auth, content=PNG).status_code == 200
    assert client.get(f"/highlights/{hid}/image", headers=auth).content == PNG
    app.state.vault.flush()
    note = (library.vault_path / "Hudhud" / "Pictures Book.md").read_text(encoding="utf-8")
    assert f"![[h-{hid.lower()}.png]]" in note
    attachment = library.vault_path / "Hudhud" / "attachments" / f"h-{hid.lower()}.png"
    assert attachment.read_bytes() == PNG
    assert "*Comment:* nice loop" in note


def test_image_upload_needs_a_picture_highlight(library, index):
    client = TestClient(create_app(library, VaultWriter(library, delay=60), search_index=index))
    with closing(connect(library.db_path)) as conn:
        code = create_pairing_code(conn, utc_now())
    auth = {"Authorization": f"Bearer {client.post('/pair', json={'code': code}).json()['token']}"}
    assert client.put("/highlights/01JB7X3K9Q2M4N5P6R7S8T9V0Z/image", headers=auth,
                      content=PNG).status_code == 404
    assert client.put("/highlights/01JB7X3K9Q2M4N5P6R7S8T9V0Z/image",
                      content=PNG).status_code == 401


def test_model_name_is_configurable(library):
    idx = SearchIndex(replace(library, embed_model="some/other-model"),
                      embedder_factory=lambda model, cache: HashEmbedder(model, cache))
    idx.load()
    assert idx.embedder.model == "some/other-model"
