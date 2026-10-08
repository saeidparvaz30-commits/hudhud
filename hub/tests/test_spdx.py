# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPDX = "SPDX-License-Identifier: AGPL-3.0-or-later"
SUFFIXES = {".py", ".sql", ".ipynb", ".ts", ".tsx", ".css"}
SKIP = {".git", ".venv", ".design", ".planning", "__pycache__", ".ipynb_checkpoints",
        ".pytest_cache", ".ruff_cache", "node_modules", "dist", "public",
        ".playwright-mcp"}


def source_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in SUFFIXES and not set(p.relative_to(ROOT).parts) & SKIP:
            yield p


def test_every_source_file_has_spdx_header():
    missing = [
        str(p.relative_to(ROOT))
        for p in source_files()
        if SPDX not in p.read_text(encoding="utf-8")
    ]
    assert missing == []
