# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hub configuration, read from hudhud.toml in the data directory."""

from __future__ import annotations

import os
import socket
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import platformdirs

DEFAULT_PORT = 8765
CONFIG_NAME = "hudhud.toml"
_KNOWN = {"vault_path", "vault_subfolder", "host", "port", "public_url", "client_dir",
          "embed_model", "similarity_threshold"}
_RESERVED: set[str] = set()
# Multilingual (about 50 languages, Persian included) and small enough for any CPU.
DEFAULT_EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# Measured on Farsi/English pairs: translations ~0.75, related ideas 0.42-0.55, unrelated ~0.
DEFAULT_THRESHOLD = 0.35

TEMPLATE = """\
# Hudhud hub settings. Uncomment and edit, then restart `hudhud serve`.

# Obsidian vault: highlights are written to <vault_path>/<vault_subfolder>/<Title>.md
# vault_path = "C:/Users/you/Documents/Vault"
# vault_subfolder = "Hudhud"

# Address your phone uses to reach this hub (for example a Tailscale name).
# Defaults to this computer's LAN address.
# public_url = "http://my-pc.tailnet-name.ts.net:8765"

# host = "0.0.0.0"
# port = 8765

# Semantic search: the embedding model (downloaded on first start) and how similar a
# note must be to count as related (0 to 1).
# embed_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# similarity_threshold = 0.35
"""


@dataclass(frozen=True)
class Config:
    data_dir: Path
    vault_path: Path | None = None
    vault_subfolder: str = "Hudhud"
    host: str = "0.0.0.0"
    port: int = DEFAULT_PORT
    public_url: str | None = None
    client_dir: Path | None = None
    embed_model: str = DEFAULT_EMBED_MODEL
    similarity_threshold: float = DEFAULT_THRESHOLD

    @property
    def library_dir(self) -> Path:
        return self.data_dir / "books"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "hudhud.db"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def config_path(self) -> Path:
        return self.data_dir / CONFIG_NAME

    @property
    def base_url(self) -> str:
        return (self.public_url or f"http://{lan_address()}:{self.port}").rstrip("/")


def default_data_dir() -> Path:
    env = os.environ.get("HUDHUD_DATA_DIR")
    return Path(env) if env else Path(platformdirs.user_data_dir("hudhud", appauthor=False))


def default_client_dir() -> Path | None:
    if getattr(sys, "frozen", False):  # the packaged hudhud.exe carries the reader with it
        bundled = Path(getattr(sys, "_MEIPASS", "")) / "client_dist"
        return bundled if bundled.is_dir() else None
    candidate = Path(__file__).resolve().parents[3] / "client" / "dist"
    return candidate if candidate.is_dir() else None


def lan_address() -> str:
    """This machine's address on the local network, or localhost if offline."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # no packet is sent for UDP connect
            return s.getsockname()[0]
        except OSError:
            return "localhost"


def load_config(data_dir: Path | None = None) -> Config:
    data_dir = Path(data_dir) if data_dir else default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / CONFIG_NAME
    raw = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    unknown = set(raw) - _KNOWN - _RESERVED
    if unknown:
        raise ValueError(f"unknown settings in {path}: {', '.join(sorted(unknown))}")
    vault = raw.get("vault_path")
    client = raw.get("client_dir")
    return Config(
        data_dir=data_dir,
        vault_path=Path(vault).expanduser() if vault else None,
        vault_subfolder=raw.get("vault_subfolder", "Hudhud"),
        host=raw.get("host", "0.0.0.0"),
        port=int(raw.get("port", DEFAULT_PORT)),
        public_url=raw.get("public_url"),
        client_dir=Path(client).expanduser() if client else default_client_dir(),
        embed_model=raw.get("embed_model", DEFAULT_EMBED_MODEL),
        similarity_threshold=float(raw.get("similarity_threshold", DEFAULT_THRESHOLD)),
    )


def write_template(config: Config) -> bool:
    """Create a commented hudhud.toml if none exists. True if one was written."""
    if config.config_path.exists():
        return False
    config.config_path.write_text(TEMPLATE, encoding="utf-8")
    return True
