# SPDX-License-Identifier: AGPL-3.0-or-later
"""Book import: format detection, DRM checks, metadata, covers, content addressing."""

from __future__ import annotations

import codecs
import hashlib
import os
import re
import shutil
import struct
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pymupdf

MAX_BYTES = 500 * 1024 * 1024
MAX_MEMBER_BYTES = 50 * 1024 * 1024
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
FONT_OBFUSCATION = {"http://www.idpf.org/2008/embedding", "http://ns.adobe.com/pdf/enc#RC"}
NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}
FB2 = {"fb": "http://www.gribuser.ru/xml/fictionbook/2.0"}
_CORRUPT = (zipfile.BadZipFile, ET.ParseError, struct.error, KeyError, IndexError,
            AttributeError, UnicodeDecodeError, zlib.error, RuntimeError, EOFError)


class ImportRejected(Exception):
    """The file cannot enter the library. `reason` is shown to the user."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Metadata:
    title: str | None
    author: str | None
    language: str | None


@dataclass(frozen=True)
class BookRecord:
    id: str
    title: str
    author: str | None
    language: str | None
    format: str
    file_size: int
    file_path: str
    cover_path: str | None


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def detect_format(path: Path) -> str:
    with open(path, "rb") as f:
        head = f.read(4096)
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head[60:68] == b"BOOKMOBI":
        return "azw3" if _mobi_version(path) >= 8 else "mobi"
    if head.startswith(b"PK\x03\x04"):
        return _zip_kind(path)
    if b"<FictionBook" in head and head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        return "fb2"
    if _looks_like_text(path):
        return "txt"
    raise ImportRejected("unsupported format")


def _looks_like_text(path: Path) -> bool:
    with open(path, "rb") as f:
        chunk = f.read(65536)
    if b"\x00" in chunk:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(chunk, final=False)
    except UnicodeDecodeError:
        return False
    return True


def _read_member(z: zipfile.ZipFile, name: str) -> bytes:
    info = z.getinfo(name)
    if info.file_size > MAX_MEMBER_BYTES:
        raise ImportRejected("archive entry too large")
    return z.read(info)


def _is_comic_entry(name: str) -> bool:
    entry = PurePosixPath(name)
    return entry.suffix.lower() in IMAGE_EXTS or entry.name.lower() == "comicinfo.xml"


def _zip_kind(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            if "META-INF/container.xml" in names or (
                "mimetype" in names
                and _read_member(z, "mimetype").strip() == b"application/epub+zip"
            ):
                return "epub"
            images = [n for n in names if PurePosixPath(n).suffix.lower() in IMAGE_EXTS]
            if images and all(_is_comic_entry(n) for n in names):
                return "cbz"
    except zipfile.BadZipFile as e:
        raise ImportRejected("corrupt file") from e
    raise ImportRejected("unsupported format")


def _mobi_record0(path: Path) -> bytes:
    with open(path, "rb") as f:
        header = f.read(86)
        if len(header) < 86:
            raise ImportRejected("corrupt file")
        (num_records,) = struct.unpack_from(">H", header, 76)
        (offset,) = struct.unpack_from(">I", header, 78)
        if num_records == 0:
            raise ImportRejected("corrupt file")
        f.seek(offset)
        rec0 = f.read(65536)
    if len(rec0) < 132 or rec0[16:20] != b"MOBI":
        raise ImportRejected("corrupt file")
    return rec0


def _mobi_version(path: Path) -> int:
    return struct.unpack_from(">I", _mobi_record0(path), 36)[0]


def _mobi_encrypted(rec0: bytes) -> bool:
    return struct.unpack_from(">H", rec0, 12)[0] != 0


def _mobi_metadata(rec0: bytes) -> Metadata:
    (header_len,) = struct.unpack_from(">I", rec0, 20)
    encoding = "utf-8" if struct.unpack_from(">I", rec0, 28)[0] == 65001 else "cp1252"
    name_off, name_len = struct.unpack_from(">II", rec0, 84)
    full_name = rec0[name_off:name_off + name_len].decode(encoding, "replace") or None
    exth: dict[int, str] = {}
    if struct.unpack_from(">I", rec0, 128)[0] & 0x40:
        pos = 16 + header_len
        if rec0[pos:pos + 4] == b"EXTH":
            (count,) = struct.unpack_from(">I", rec0, pos + 8)
            pos += 12
            for _ in range(count):
                rtype, rlen = struct.unpack_from(">II", rec0, pos)
                if rlen < 8:
                    break
                exth.setdefault(rtype, rec0[pos + 8:pos + rlen].decode(encoding, "replace"))
                pos += rlen
    return Metadata(exth.get(503) or full_name, exth.get(100), exth.get(524))


def _epub_drm(z: zipfile.ZipFile) -> bool:
    names = set(z.namelist())
    if "META-INF/rights.xml" in names:
        return True
    if "META-INF/encryption.xml" in names:
        root = ET.fromstring(_read_member(z, "META-INF/encryption.xml"))
        for el in root.iter():
            if el.tag.endswith("EncryptionMethod") and el.get("Algorithm") not in FONT_OBFUSCATION:
                return True
    return False


def _epub_opf(z: zipfile.ZipFile) -> tuple[str, ET.Element]:
    container = ET.fromstring(_read_member(z, "META-INF/container.xml"))
    opf_path = container.find(".//c:rootfile", NS).get("full-path")
    return opf_path, ET.fromstring(_read_member(z, opf_path))


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


def _epub_metadata(opf: ET.Element) -> Metadata:
    md = opf.find("opf:metadata", NS)
    if md is None:
        return Metadata(None, None, None)
    return Metadata(_text(md.find("dc:title", NS)), _text(md.find("dc:creator", NS)),
                    _text(md.find("dc:language", NS)))


def _epub_cover(z: zipfile.ZipFile, opf_path: str, opf: ET.Element) -> bytes | None:
    items = opf.findall("opf:manifest/opf:item", NS)
    href = next((i.get("href") for i in items
                 if "cover-image" in (i.get("properties") or "").split()), None)
    if href is None:
        meta = opf.find("opf:metadata/opf:meta[@name='cover']", NS)
        if meta is not None:
            href = next((i.get("href") for i in items if i.get("id") == meta.get("content")), None)
    if href is None:
        return None
    full = str(PurePosixPath(opf_path).parent / urllib.parse.unquote(href))
    try:
        return _read_member(z, full)
    except KeyError:
        return None


def _fb2_metadata(path: Path) -> Metadata:
    root = ET.parse(path).getroot()
    info = root.find("fb:description/fb:title-info", FB2)
    if info is None:
        return Metadata(None, None, None)
    author = None
    a = info.find("fb:author", FB2)
    if a is not None:
        parts = [_text(a.find(f"fb:{p}", FB2)) for p in ("first-name", "middle-name", "last-name")]
        author = " ".join(p for p in parts if p) or None
    return Metadata(_text(info.find("fb:book-title", FB2)), author,
                    _text(info.find("fb:lang", FB2)))


def _natural_key(name: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _cbz_cover(z: zipfile.ZipFile) -> bytes:
    images = [n for n in z.namelist() if PurePosixPath(n).suffix.lower() in IMAGE_EXTS]
    return _read_member(z, min(images, key=_natural_key))


def _pdf_inspect(path: Path) -> tuple[Metadata, bytes | None]:
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except Exception as e:
        raise ImportRejected("corrupt file") from e
    with doc:
        if doc.needs_pass:
            raise ImportRejected("password-protected or DRM-encrypted PDF")
        if doc.page_count == 0:
            raise ImportRejected("corrupt file")
        meta = doc.metadata or {}
        cover = _render_cover(doc[0])
    return Metadata(meta.get("title") or None, meta.get("author") or None, None), cover


def _render_cover(page) -> bytes | None:
    longest = max(page.rect.width, page.rect.height)
    zoom = 600 / longest if longest else 1.0
    try:
        return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
    except Exception:
        return None


def _image_ext(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _inspect(path: Path, fmt: str) -> tuple[Metadata, bytes | None]:
    if fmt == "pdf":
        return _pdf_inspect(path)
    if fmt in ("mobi", "azw3"):
        rec0 = _mobi_record0(path)
        if _mobi_encrypted(rec0):
            raise ImportRejected("DRM-encrypted Kindle book")
        return _mobi_metadata(rec0), None
    if fmt == "epub":
        with zipfile.ZipFile(path) as z:
            if _epub_drm(z):
                raise ImportRejected("DRM-encrypted EPUB")
            opf_path, opf = _epub_opf(z)
            return _epub_metadata(opf), _epub_cover(z, opf_path, opf)
    if fmt == "cbz":
        with zipfile.ZipFile(path) as z:
            return Metadata(None, None, None), _cbz_cover(z)
    if fmt == "fb2":
        return _fb2_metadata(path), None
    return Metadata(None, None, None), None


def import_book(
    src: Path,
    library_dir: Path,
    original_name: str | None = None,
    max_bytes: int = MAX_BYTES,
) -> BookRecord:
    src = Path(src)
    size = src.stat().st_size
    if size == 0:
        raise ImportRejected("empty file")
    if size > max_bytes:
        raise ImportRejected("file too large")
    try:
        fmt = detect_format(src)
        meta, cover = _inspect(src, fmt)
    except _CORRUPT as e:
        raise ImportRejected("corrupt file") from e

    book_id = sha256_file(src)
    library_dir = Path(library_dir)
    library_dir.mkdir(parents=True, exist_ok=True)
    dest = library_dir / f"{book_id}.{fmt}"
    if not dest.exists():
        part = dest.with_name(dest.name + ".part")
        shutil.copyfile(src, part)
        os.replace(part, dest)
    cover_path = None
    if cover and (ext := _image_ext(cover)):
        cover_file = library_dir / f"{book_id}.cover{ext}"
        if not cover_file.exists():
            cover_file.write_bytes(cover)
        cover_path = str(cover_file)
    fallback = Path(original_name or src.name).stem
    return BookRecord(book_id, meta.title or fallback, meta.author, meta.language, fmt,
                      size, str(dest), cover_path)
