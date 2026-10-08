# SPDX-License-Identifier: AGPL-3.0-or-later
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from hudhud_hub.api import create_app
from hudhud_hub.auth import create_pairing_code
from hudhud_hub.db import connect, utc_now
from hudhud_hub.vault_writer import VaultWriter

from .conftest import pdf_bytes

HID = "01JB7X3K9Q2M4N5P6R7S8T9V0W"


@pytest.fixture
def app(config):
    return create_app(config, VaultWriter(config, delay=60))


@pytest.fixture
def client(app):
    return TestClient(app)


def pair(client, config, name="Test PC") -> dict:
    with closing(connect(config.db_path)) as conn:
        code = create_pairing_code(conn, utc_now())
    token = client.post("/pair", json={"code": code, "device_name": name}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, auth, data=None, name="book.pdf"):
    return client.post("/books", params={"filename": name}, headers=auth,
                       content=data or pdf_bytes("Thinking, Fast and Slow"))


def test_public_endpoints(client):
    assert client.get("/health").json()["search_ready"] is False
    assert client.get("/about").json()["license"] == "AGPL-3.0-or-later"


@pytest.mark.parametrize("method, path", [
    ("get", "/books"), ("get", "/sync/pull"), ("get", "/devices"),
    ("get", f"/books/{'a' * 64}/file"),
])
def test_everything_else_needs_a_token(client, method, path):
    assert getattr(client, method)(path).status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert getattr(client, method)(path, headers=wrong).status_code == 401


def test_bad_pairing_code(client):
    assert client.post("/pair", json={"code": "AAAA-AAAA"}).status_code == 403


def test_upload_list_download_cover(client, config):
    auth = pair(client, config)
    book = upload(client, auth).json()
    assert (book["title"], book["format"], book["has_cover"]) == ("Thinking, Fast and Slow", "pdf",
                                                                  True)
    assert [b["id"] for b in client.get("/books", headers=auth).json()] == [book["id"]]
    file = client.get(f"/books/{book['id']}/file", headers=auth)
    assert file.headers["content-type"] == "application/pdf"
    assert "immutable" in file.headers["cache-control"]
    assert file.content.startswith(b"%PDF-")
    assert client.get(f"/books/{book['id']}/cover", headers=auth).content.startswith(b"\x89PNG")
    assert not list(config.library_dir.glob(".upload-*"))


def test_reupload_is_idempotent_and_logged_once(client, config):
    auth = pair(client, config)
    data = pdf_bytes("Same File")
    first = upload(client, auth, data).json()
    second = upload(client, auth, data).json()
    assert first["id"] == second["id"]
    books = [c for c in client.get("/sync/pull", headers=auth).json()["changes"]
             if c["entity"] == "book"]
    assert len(books) == 1


def test_rejected_upload_is_422(client, config):
    auth = pair(client, config)
    response = upload(client, auth, data=bytes(range(256)) * 4, name="x.bin")
    assert response.status_code == 422 and response.json()["detail"] == "unsupported format"


def test_unknown_book_is_404(client, config):
    auth = pair(client, config)
    assert client.get(f"/books/{'b' * 64}/file", headers=auth).status_code == 404
    assert client.get("/books/../etc/file", headers=auth).status_code == 404


def test_highlight_push_reaches_the_vault(client, config, app):
    auth = pair(client, config)
    book = upload(client, auth).json()
    now = utc_now()
    change = {"entity": "highlight", "data": {
        "id": HID, "book_id": book["id"], "locator": "cfi", "fraction": 0.3,
        "text": "A passage worth keeping", "color": "green", "comment": "note",
        "created_at": now, "updated_at": now}}
    result = client.post("/sync/push", headers=auth, json={"changes": [change]}).json()
    assert result["results"][0]["status"] == "accepted"
    app.state.vault.flush()
    note = config.vault_path / "Hudhud" / "Thinking, Fast and Slow.md"
    text = note.read_text(encoding="utf-8")
    assert "> A passage worth keeping" in text and f"^h-{HID.lower()}" in text
    assert f"http://hub.test:8765/read/{book['id']}?h={HID}" in text
    assert client.get("/health").json()["vault_ok"] is True


def test_devices_and_revoke(client, config):
    auth = pair(client, config, "PC")
    other = pair(client, config, "Phone")
    devices = client.get("/devices", headers=auth).json()
    assert [d["current"] for d in devices] == [True, False]
    phone_id = devices[1]["id"]
    assert client.delete(f"/devices/{phone_id}", headers=auth).status_code == 200
    assert client.get("/books", headers=other).status_code == 401


def test_search_is_503_until_it_ships(client, config):
    auth = pair(client, config)
    assert client.post("/search", headers=auth, json={"text": "x"}).status_code == 503


def test_static_client_with_spa_fallback(config, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>reader</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    from dataclasses import replace
    client = TestClient(create_app(replace(config, client_dir=dist)))
    assert client.get("/").text == "<html>reader</html>"
    assert client.get(f"/read/{'a' * 64}").text == "<html>reader</html>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/../secret.txt").status_code == 404
    assert client.get("/nope").status_code == 404
    assert client.get("/health").json()["ok"] is True


def test_upload_without_a_token_is_refused_before_the_body_is_read(client):
    response = client.post("/books?filename=x.pdf", content=b"%PDF-1.7" + b"0" * 1024,
                           headers={"Content-Type": "application/octet-stream"})
    assert response.status_code == 401


def test_declared_oversize_upload_is_refused_up_front(client, config):
    auth = pair(client, config)
    response = client.post("/books?filename=big.pdf", content=b"x",
                           headers={**auth, "Content-Length": str(600 * 1024 * 1024)})
    assert response.status_code == 413


def test_raw_upload_uses_the_given_filename(client, config):
    auth = pair(client, config)
    response = client.post("/books?filename=My%20Notes.txt", content="سلام".encode(),
                           headers={**auth, "Content-Type": "application/octet-stream"})
    assert response.status_code == 201 and response.json()["title"] == "My Notes"


def test_static_cache_rules(config, tmp_path):
    """Hashed build assets are immutable; everything else (vendored foliate-js,
    pdf.js) must revalidate, or phones keep running stale code after an update."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "foliate-js").mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("1", encoding="utf-8")
    (dist / "foliate-js" / "view.js").write_text("2", encoding="utf-8")
    from dataclasses import replace
    client = TestClient(create_app(replace(config, client_dir=dist)))
    assert "immutable" in client.get("/assets/index-abc123.js").headers["cache-control"]
    assert client.get("/foliate-js/view.js").headers["cache-control"] == "no-cache"
    assert client.get("/").headers["cache-control"] == "no-cache"
