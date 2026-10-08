# SPDX-License-Identifier: AGPL-3.0-or-later
"""Package the hub (with the built reader inside) as one hudhud.exe for the desktop app.

Run from the repo root:  uv run --project hub --with pyinstaller python desktop/build_sidecar.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "client" / "dist"
BINARIES = ROOT / "desktop" / "src-tauri" / "binaries"
WORK = ROOT / "desktop" / ".pyinstaller"
ENTRY = WORK / "hudhud_main.py"


def target_triple() -> str:
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64",
            "arm64": "aarch64", "aarch64": "aarch64"}[machine]
    if sys.platform == "win32":
        return f"{arch}-pc-windows-msvc"
    if sys.platform == "darwin":
        return f"{arch}-apple-darwin"
    return f"{arch}-unknown-linux-gnu"


def main() -> int:
    if not (DIST / "index.html").is_file():
        print("Build the reader first: pnpm --dir client build", file=sys.stderr)
        return 1
    WORK.mkdir(parents=True, exist_ok=True)
    ENTRY.write_text("from hudhud_hub.cli import main\n\nraise SystemExit(main())\n",
                     encoding="utf-8")
    # Ship the reader without any locally copied APK download.
    client = WORK / "client_dist"
    if client.exists():
        shutil.rmtree(client)
    shutil.copytree(DIST, client, ignore=shutil.ignore_patterns("*.apk"))
    sep = ";" if os.name == "nt" else ":"
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--name", "hudhud",
        "--distpath", str(WORK / "out"), "--workpath", str(WORK / "build"),
        "--specpath", str(WORK),
        "--add-data", f"{client}{sep}client_dist",
        "--collect-data", "hudhud_hub",
        "--collect-submodules", "uvicorn",
        "--collect-submodules", "hudhud_hub",
        # semantic search: fastembed's model registry plus the ONNX runtime and tokenizers
        "--collect-all", "fastembed",
        "--collect-binaries", "onnxruntime",
        "--collect-submodules", "onnxruntime",
        "--collect-binaries", "tokenizers",
        str(ENTRY),
    ], check=True)
    suffix = ".exe" if os.name == "nt" else ""
    BINARIES.mkdir(parents=True, exist_ok=True)
    target = BINARIES / f"hudhud-{target_triple()}{suffix}"
    shutil.copy2(WORK / "out" / f"hudhud{suffix}", target)
    print(f"sidecar: {target} ({target.stat().st_size // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
