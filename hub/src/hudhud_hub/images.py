# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pictures saved with picture highlights, stored by highlight id."""

from __future__ import annotations

import os
from pathlib import Path

from .config import Config
from .library import _image_ext

MAX_IMAGE_BYTES = 8 * 1024 * 1024
_EXTENSIONS = (".png", ".jpg", ".gif", ".webp")


def image_path(config: Config, highlight_id: str) -> Path | None:
    for ext in _EXTENSIONS:
        path = config.images_dir / f"{highlight_id}{ext}"
        if path.is_file():
            return path
    return None


def save_image(config: Config, highlight_id: str, data: bytes) -> Path:
    """Store the picture; ValueError if the bytes are not a PNG, JPEG, GIF or WebP."""
    ext = _image_ext(data)
    if ext is None:
        raise ValueError("not a PNG, JPEG, GIF or WebP image")
    config.images_dir.mkdir(parents=True, exist_ok=True)
    for old in _EXTENSIONS:  # a re-upload may change the format
        (config.images_dir / f"{highlight_id}{old}").unlink(missing_ok=True)
    target = config.images_dir / f"{highlight_id}{ext}"
    part = target.with_name(target.name + ".part")
    part.write_bytes(data)
    os.replace(part, target)
    return target
