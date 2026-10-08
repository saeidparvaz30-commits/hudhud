# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import struct
import zipfile
from pathlib import Path

import pymupdf
import pytest

from hudhud_hub.library import (
    MAX_MEMBER_BYTES,
    ImportRejected,
    detect_format,
    import_book,
    sha256_file,
)

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"


def make_pdf(path, title="Paper Title", author="P. Author", user_pw=None, owner_pw=None):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Hello, Hudhud.")
    doc.set_metadata({"title": title, "author": author})
    if owner_pw:
        doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                 owner_pw=owner_pw, user_pw=user_pw or "")
    else:
        doc.save(path)
    doc.close()


def make_epub(path, title="کتاب نمونه", author="نویسنده", language="fa",
              cover="epub3", encryption_alg=None, rights=False):
    cover_meta = '<meta name="cover" content="cov"/>' if cover == "epub2" else ""
    cover_props = ' properties="cover-image"' if cover == "epub3" else ""
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id">urn:uuid:1</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>{language}</dc:language>
    {cover_meta}
  </metadata>
  <manifest>
    <item id="cov" href="images/cover%20art.png" media-type="image/png"{cover_props}/>
    <item id="c1" href="text/c1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/></spine>
</package>"""
    container = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/text/c1.xhtml", "<html><body><p>Salam</p></body></html>")
        z.writestr("OEBPS/images/cover art.png", FAKE_PNG)
        if encryption_alg:
            z.writestr("META-INF/encryption.xml",
                '<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
                'xmlns:enc="http://www.w3.org/2001/04/xmlenc#"><enc:EncryptedData>'
                f'<enc:EncryptionMethod Algorithm="{encryption_alg}"/>'
                "</enc:EncryptedData></encryption>")
        if rights:
            z.writestr("META-INF/rights.xml", "<rights/>")


def make_mobi(path, title="Test Book", author="A. Writer", language="en",
              version=6, encryption=0):
    exth_records = b""
    fields = [(100, author), (503, title), (524, language)]
    for rtype, value in fields:
        data = value.encode("utf-8")
        exth_records += struct.pack(">II", rtype, 8 + len(data)) + data
    exth = b"EXTH" + struct.pack(">II", 12 + len(exth_records), len(fields)) + exth_records
    header_len = 232
    full_name = title.encode("utf-8")
    rec0 = bytearray(16 + header_len)
    struct.pack_into(">H", rec0, 12, encryption)
    rec0[16:20] = b"MOBI"
    struct.pack_into(">I", rec0, 20, header_len)
    struct.pack_into(">I", rec0, 28, 65001)
    struct.pack_into(">I", rec0, 36, version)
    struct.pack_into(">II", rec0, 84, 16 + header_len + len(exth), len(full_name))
    struct.pack_into(">I", rec0, 128, 0x40)
    rec0 += exth + full_name + b"\0\0"
    pdb = bytearray(78)
    pdb[0:4] = b"test"
    pdb[60:68] = b"BOOKMOBI"
    struct.pack_into(">H", pdb, 76, 1)
    pdb += struct.pack(">I", 78 + 8 + 2) + b"\0\0\0\0" + b"\0\0"
    Path(path).write_bytes(bytes(pdb) + bytes(rec0))


FB2_SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">
  <description><title-info>
    <author><first-name>Lev</first-name><last-name>Tolstoy</last-name></author>
    <book-title>War and Peace</book-title><lang>ru</lang>
  </title-info></description>
  <body><section><p>Well, Prince...</p></section></body>
</FictionBook>"""


def corrupt_member(path, name):
    """Overwrite the compressed bytes of one entry, keeping the zip structure."""
    data = bytearray(Path(path).read_bytes())
    header = data.find(name.encode()) - 30  # first hit is the local header
    csize, = struct.unpack_from("<I", data, header + 18)
    name_len, extra_len = struct.unpack_from("<HH", data, header + 26)
    start = header + 30 + name_len + extra_len
    data[start:start + csize] = b"\xff" * csize
    Path(path).write_bytes(bytes(data))


def encrypt_flag(path):
    """Mark every entry as password-protected without encrypting it."""
    data = bytearray(Path(path).read_bytes())
    for sig, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        i = data.find(sig)
        while i != -1:
            data[i + flag_offset] |= 1
            i = data.find(sig, i + 4)
    Path(path).write_bytes(bytes(data))


def make_cbz(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("page10.png", b"\x89PNG\r\n\x1a\nten")
        z.writestr("page2.png", b"\x89PNG\r\n\x1a\ntwo")
        z.writestr("page1.png", b"\x89PNG\r\n\x1a\none")





def test_sha256_matches_hashlib(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hudhud" * 1000)
    assert sha256_file(p) == hashlib.sha256(b"hudhud" * 1000).hexdigest()


def test_detect_every_format(tmp_path):
    make_pdf(tmp_path / "a.pdf")
    make_epub(tmp_path / "a.epub")
    make_mobi(tmp_path / "a.mobi")
    make_mobi(tmp_path / "a.azw3", version=8)
    make_cbz(tmp_path / "a.cbz")
    (tmp_path / "a.fb2").write_text(FB2_SAMPLE, encoding="utf-8")
    (tmp_path / "a.txt").write_text("سلام دنیا\nHello world\n", encoding="utf-8")
    found = {p.suffix[1:]: detect_format(p) for p in tmp_path.iterdir()}
    assert found == {"pdf": "pdf", "epub": "epub", "mobi": "mobi", "azw3": "azw3",
                     "cbz": "cbz", "fb2": "fb2", "txt": "txt"}


def test_extension_is_ignored(tmp_path):
    p = tmp_path / "really-a-pdf.epub"
    make_pdf(p)
    assert detect_format(p) == "pdf"


def test_binary_garbage_is_unsupported(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(ImportRejected) as e:
        detect_format(p)
    assert e.value.reason == "unsupported format"


def test_broken_zip_is_corrupt(tmp_path):
    p = tmp_path / "x.epub"
    p.write_bytes(b"PK\x03\x04" + b"not really a zip" * 10)
    with pytest.raises(ImportRejected) as e:
        detect_format(p)
    assert e.value.reason == "corrupt file"





def test_import_pdf_metadata_and_cover(tmp_path):
    src = tmp_path / "in.pdf"
    make_pdf(src, title="Thinking, Fast and Slow", author="Daniel Kahneman")
    rec = import_book(src, tmp_path / "lib")
    assert rec.id == sha256_file(src)
    assert (rec.title, rec.author, rec.format) == (
        "Thinking, Fast and Slow", "Daniel Kahneman", "pdf")
    assert Path(rec.file_path) == tmp_path / "lib" / f"{rec.id}.pdf"
    assert Path(rec.cover_path).read_bytes().startswith(b"\x89PNG")
    assert rec.file_size == src.stat().st_size


def test_import_is_idempotent(tmp_path):
    src = tmp_path / "in.pdf"
    make_pdf(src)
    a = import_book(src, tmp_path / "lib")
    b = import_book(src, tmp_path / "lib")
    assert a == b
    assert sorted(p.name for p in (tmp_path / "lib").iterdir()) == sorted(
        [f"{a.id}.pdf", f"{a.id}.cover.png"])


def test_password_pdf_rejected(tmp_path):
    src = tmp_path / "locked.pdf"
    make_pdf(src, user_pw="user", owner_pw="owner")
    with pytest.raises(ImportRejected):
        import_book(src, tmp_path / "lib")


def test_owner_password_only_pdf_imports(tmp_path):
    src = tmp_path / "restricted.pdf"
    make_pdf(src, title="Restricted", owner_pw="owner")
    assert import_book(src, tmp_path / "lib").title == "Restricted"


def test_epub3_farsi_metadata_and_cover(tmp_path):
    src = tmp_path / "in.epub"
    make_epub(src)
    rec = import_book(src, tmp_path / "lib")
    assert (rec.title, rec.author, rec.language, rec.format) == (
        "کتاب نمونه", "نویسنده", "fa", "epub")
    assert Path(rec.cover_path).read_bytes() == FAKE_PNG


def test_epub2_cover_meta(tmp_path):
    src = tmp_path / "in.epub"
    make_epub(src, cover="epub2")
    assert Path(import_book(src, tmp_path / "lib").cover_path).read_bytes() == FAKE_PNG


def test_epub_without_cover(tmp_path):
    src = tmp_path / "in.epub"
    make_epub(src, cover=None)
    assert import_book(src, tmp_path / "lib").cover_path is None


def test_epub_font_obfuscation_is_not_drm(tmp_path):
    src = tmp_path / "in.epub"
    make_epub(src, encryption_alg="http://www.idpf.org/2008/embedding")
    assert import_book(src, tmp_path / "lib").format == "epub"


@pytest.mark.parametrize("kwargs", [
    {"encryption_alg": "http://www.w3.org/2001/04/xmlenc#aes128-cbc"},
    {"rights": True},
])
def test_epub_drm_rejected(tmp_path, kwargs):
    src = tmp_path / "in.epub"
    make_epub(src, **kwargs)
    with pytest.raises(ImportRejected):
        import_book(src, tmp_path / "lib")


def test_mobi_and_azw3_metadata(tmp_path):
    make_mobi(tmp_path / "a.mobi", title="Shahnameh", author="Ferdowsi", language="fa")
    make_mobi(tmp_path / "b.azw3", title="Gulistan", author="Saadi", version=8)
    a = import_book(tmp_path / "a.mobi", tmp_path / "lib")
    b = import_book(tmp_path / "b.azw3", tmp_path / "lib")
    assert (a.title, a.author, a.language, a.format) == ("Shahnameh", "Ferdowsi", "fa", "mobi")
    assert (b.title, b.format, b.cover_path) == ("Gulistan", "azw3", None)


def test_mobi_drm_rejected(tmp_path):
    make_mobi(tmp_path / "a.azw3", version=8, encryption=2)
    with pytest.raises(ImportRejected):
        import_book(tmp_path / "a.azw3", tmp_path / "lib")


def test_fb2_metadata(tmp_path):
    src = tmp_path / "in.fb2"
    src.write_text(FB2_SAMPLE, encoding="utf-8")
    rec = import_book(src, tmp_path / "lib")
    assert (rec.title, rec.author, rec.language) == ("War and Peace", "Lev Tolstoy", "ru")


def test_cbz_cover_is_first_page_in_natural_order(tmp_path):
    src = tmp_path / "comic.cbz"
    make_cbz(src)
    rec = import_book(src, tmp_path / "lib", original_name="My Comic.cbz")
    assert rec.title == "My Comic"
    assert Path(rec.cover_path).read_bytes().endswith(b"one")


def test_txt_title_from_original_name(tmp_path):
    src = tmp_path / "upload-123.tmp"
    src.write_text("یک روز...", encoding="utf-8")
    rec = import_book(src, tmp_path / "lib", original_name="Ruzi Ruzegari.txt")
    assert (rec.title, rec.format, rec.cover_path) == ("Ruzi Ruzegari", "txt", None)


def test_rejections_store_nothing(tmp_path):
    lib = tmp_path / "lib"
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    big = tmp_path / "big.txt"
    big.write_text("x" * 100)
    locked = tmp_path / "locked.pdf"
    make_pdf(locked, user_pw="u", owner_pw="o")
    for src, kwargs in [(empty, {}), (big, {"max_bytes": 10}), (locked, {})]:
        with pytest.raises(ImportRejected):
            import_book(src, lib, **kwargs)
    assert not lib.exists() or list(lib.iterdir()) == []


def test_truncated_mobi_is_corrupt(tmp_path):
    src = tmp_path / "a.mobi"
    make_mobi(src)
    src.write_bytes(src.read_bytes()[:100])
    with pytest.raises(ImportRejected) as e:
        import_book(src, tmp_path / "lib")
    assert e.value.reason == "corrupt file"





def test_huge_archive_entry_rejected(tmp_path):
    src = tmp_path / "bomb.cbz"
    with zipfile.ZipFile(src, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("page1.png", b"\x89PNG\r\n\x1a\n" + bytes(MAX_MEMBER_BYTES + 1))
    with pytest.raises(ImportRejected) as e:
        import_book(src, tmp_path / "lib")
    assert e.value.reason == "archive entry too large"


def test_bad_compressed_data_is_corrupt(tmp_path):
    src = tmp_path / "in.epub"
    with zipfile.ZipFile(src, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip" * 20)
    corrupt_member(src, "mimetype")
    with pytest.raises(ImportRejected) as e:
        import_book(src, tmp_path / "lib")
    assert e.value.reason == "corrupt file"


def test_password_protected_comic_page_is_corrupt(tmp_path):
    src = tmp_path / "in.cbz"
    make_cbz(src)
    encrypt_flag(src)
    with pytest.raises(ImportRejected) as e:
        import_book(src, tmp_path / "lib")
    assert e.value.reason == "corrupt file"


def test_extreme_page_shape_still_imports(tmp_path):
    src = tmp_path / "tall.pdf"
    doc = pymupdf.open()
    doc.new_page(width=3, height=14400)
    doc.save(src)
    doc.close()
    assert import_book(src, tmp_path / "lib").format == "pdf"


def test_epub_without_mimetype_is_still_checked_for_drm(tmp_path):
    src = tmp_path / "in.epub"
    make_epub(src, rights=True)
    with zipfile.ZipFile(src) as z:
        entries = {n: z.read(n) for n in z.namelist() if n != "mimetype"}
    with zipfile.ZipFile(src, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    with pytest.raises(ImportRejected) as e:
        import_book(src, tmp_path / "lib")
    assert "DRM" in e.value.reason


def test_office_document_is_not_a_comic(tmp_path):
    src = tmp_path / "report.docx"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
        z.writestr("word/media/image1.png", FAKE_PNG)
    with pytest.raises(ImportRejected) as e:
        detect_format(src)
    assert e.value.reason == "unsupported format"
