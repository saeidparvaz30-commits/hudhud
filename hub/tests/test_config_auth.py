# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from hudhud_hub.auth import (
    PairingError,
    authenticate,
    create_pairing_code,
    list_devices,
    normalize_code,
    redeem_pairing_code,
    revoke_device,
)
from hudhud_hub.cli import main
from hudhud_hub.config import Config, lan_addresses, load_config, write_template

NOW = "2026-10-08T10:00:00.000Z"
LATER = "2026-10-08T10:11:00.000Z"


def test_defaults_without_a_settings_file(tmp_path):
    config = load_config(tmp_path)
    assert config.vault_path is None
    assert config.port == 8765
    assert config.db_path == tmp_path / "hudhud.db"
    assert config.library_dir == tmp_path / "books"


def test_settings_file_is_read(tmp_path):
    (tmp_path / "hudhud.toml").write_text(
        'vault_path = "C:/Vault"\nport = 9000\npublic_url = "http://pc.ts.net:9000/"\n',
        encoding="utf-8")
    config = load_config(tmp_path)
    assert (config.port, str(config.vault_path).replace("\\", "/")) == (9000, "C:/Vault")
    assert config.base_url == "http://pc.ts.net:9000"


def test_hub_urls_list_the_public_url_then_every_lan_address(tmp_path, monkeypatch):
    monkeypatch.setattr("hudhud_hub.config.lan_addresses", lambda: ["192.168.1.5", "10.0.0.7"])
    config = Config(data_dir=tmp_path, port=9000, public_url="https://pc.ts.net/")
    assert config.hub_urls == ["https://pc.ts.net", "http://192.168.1.5:9000",
                               "http://10.0.0.7:9000"]
    assert Config(data_dir=tmp_path, port=9000).hub_urls == ["http://192.168.1.5:9000",
                                                             "http://10.0.0.7:9000"]


def test_lan_addresses_skip_loopback_and_link_local(monkeypatch):
    monkeypatch.setattr("hudhud_hub.config.lan_address", lambda: "192.168.1.5")
    infos = [(2, 1, 6, "", (ip, 0)) for ip in
             ["127.0.0.1", "169.254.3.4", "10.0.0.7", "192.168.1.5", "10.0.0.7"]]
    monkeypatch.setattr("hudhud_hub.config.socket.getaddrinfo", lambda *a, **k: infos)
    assert lan_addresses() == ["192.168.1.5", "10.0.0.7"]


def test_unknown_setting_is_an_error(tmp_path):
    (tmp_path / "hudhud.toml").write_text('valt_path = "typo"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="valt_path"):
        load_config(tmp_path)


def test_template_is_valid_and_written_once(tmp_path):
    config = load_config(tmp_path)
    assert write_template(config) is True
    assert write_template(config) is False
    assert load_config(tmp_path).vault_path is None


def test_pairing_round_trip(conn):
    code = create_pairing_code(conn, NOW)
    assert len(code) == 8
    typed = f"{code[:4].lower()}-{code[4:]}"
    device_id, token = redeem_pairing_code(conn, typed, " Pixel  9 ", NOW)
    assert authenticate(conn, token, NOW) == device_id
    assert list_devices(conn)[0]["name"] == "Pixel 9"
    assert conn.execute("SELECT token_hash FROM devices").fetchone()[0] != token


def test_code_is_single_use(conn):
    code = create_pairing_code(conn, NOW)
    redeem_pairing_code(conn, code, "a", NOW)
    with pytest.raises(PairingError):
        redeem_pairing_code(conn, code, "b", NOW)


def test_code_expires(conn):
    code = create_pairing_code(conn, NOW)
    with pytest.raises(PairingError):
        redeem_pairing_code(conn, code, "late", LATER)


def test_wrong_token_and_revoked_device_are_rejected(conn):
    device_id, token = redeem_pairing_code(conn, create_pairing_code(conn, NOW), "x", NOW)
    assert authenticate(conn, "nope", NOW) is None
    assert revoke_device(conn, device_id) is True
    assert authenticate(conn, token, NOW) is None


def test_normalize_accepts_lookalikes():
    assert normalize_code(" abcd-efgo ") == "ABCDEFG0"
    assert normalize_code("il") == "11"


def test_expired_codes_are_cleaned_up_when_a_new_one_is_made(conn):
    create_pairing_code(conn, NOW)
    create_pairing_code(conn, LATER)  # the first has expired by now
    assert conn.execute("SELECT COUNT(*) FROM pairing_codes").fetchone()[0] == 1


def test_desktop_url_pairs_the_local_window(conn, tmp_path):
    from hudhud_hub.cli import desktop_url
    from hudhud_hub.config import load_config

    url = desktop_url(load_config(tmp_path), 8765)
    assert url.startswith("http://127.0.0.1:8765/?pair=")
    code = url.rsplit("=", 1)[1]
    from hudhud_hub.db import connect, utc_now
    with connect(tmp_path / "hudhud.db") as c:
        assert redeem_pairing_code(c, code, "Desktop", utc_now())


def test_frozen_app_finds_its_bundled_client(tmp_path, monkeypatch):
    import sys

    from hudhud_hub.config import default_client_dir
    (tmp_path / "client_dist").mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert default_client_dir() == tmp_path / "client_dist"


def test_port_flag_reaches_the_printed_invite(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("hudhud_hub.config.lan_addresses", lambda: ["192.168.1.5"])
    assert main(["--data-dir", str(tmp_path), "pair", "--port", "9100"]) == 0
    assert "http://192.168.1.5:9100/?pair=" in capsys.readouterr().out
