# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from hudhud_hub.vault import (
    END,
    INTRO,
    START,
    START_PREFIX,
    BookMeta,
    Highlight,
    atomic_write,
    block_id,
    extract_region,
    frontmatter_book_id,
    region_hash,
    render_frontmatter,
    safe_join,
    sanitize_title,
    write_book_note,
)

BOOK = BookMeta(id="3f2a9c" + "0" * 58, title="Thinking, Fast and Slow",
                author="Daniel Kahneman", language="en")
H42 = Highlight(id="01JB7X3K9Q2M4N5P6R7S8T9V0W",
                text="The confidence people have in their intuitions is not a reliable "
                     "guide to their validity.",
                comment="Compare with Taleb on narrative fallacy.", fraction=0.42,
                created_at="2026-10-08T10:00:00.000Z")
H10 = Highlight(id="01JB7X0000000000000000000A",
                text="A reliable way to make people believe in falsehoods is frequent repetition.",
                comment="", fraction=0.10, created_at="2026-10-08T11:00:00.000Z")
HUB = "https://hub.example:8765/"
NOW = "2026-10-08T12:34:56.789Z"

GOLDEN = """---
hudhud_book_id: BID
title: "Thinking, Fast and Slow"
author: "Daniel Kahneman"
language: "en"
tags: [book, hudhud]
---

# Thinking, Fast and Slow

Anything written outside the markers is yours. Hudhud never changes it.

<!-- hudhud:start (managed by Hudhud; edit highlights in the app) -->
## Highlights

> A reliable way to make people believe in falsehoods is frequent repetition.

^h-01jb7x0000000000000000000a

*Location:* 10% · [Open in reader](https://hub.example:8765/read/BID?h=01JB7X0000000000000000000A)

> The confidence people have in their intuitions is not a reliable guide to their validity.

^h-01jb7x3k9q2m4n5p6r7s8t9v0w

*Comment:* Compare with Taleb on narrative fallacy.
*Location:* 42% · [Open in reader](https://hub.example:8765/read/BID?h=01JB7X3K9Q2M4N5P6R7S8T9V0W)
<!-- hudhud:end -->
""".replace("BID", BOOK.id)


def write(vault, highlights, last_hash=None, book=BOOK):
    return write_book_note(vault, "Hudhud", book, highlights, HUB, last_hash, NOW)





@pytest.mark.parametrize("title, expected", [
    ("What/If: A?", "What If A"),
    ("CON", "CON_"),
    ("کتاب: نمونه", "کتاب نمونه"),
    ("Note [draft] #1 ^x|y", "Note draft 1 x y"),
    ("Ends with dots...", "Ends with dots"),
    ("...", "FALLBACK"),
    ("x" * 300, "x" * 150),
])
def test_sanitize_title(title, expected):
    assert sanitize_title(title, "FALLBACK") == expected


def test_long_farsi_title_fits_filesystem_limits():
    name = sanitize_title("کتاب " * 100, "FALLBACK")
    assert 0 < len(name.encode("utf-8")) <= 150
    worst = f"{name} (3f2a9c00).conflict-20261008T123456Z.md"
    assert len(worst.encode("utf-8")) <= 255
    assert "\ufffd" not in name


def test_block_id():
    assert block_id("01JB7X3K9Q2M4N5P6R7S8T9V0W") == "h-01jb7x3k9q2m4n5p6r7s8t9v0w"


def test_new_file_matches_golden(tmp_path):
    result = write(tmp_path, [H42, H10])
    assert result.path == tmp_path / "Hudhud" / "Thinking, Fast and Slow.md"
    assert result.path.read_text(encoding="utf-8") == GOLDEN
    assert result.conflict_path is None
    assert result.region_hash == region_hash(extract_region(GOLDEN))


def test_empty_highlights_placeholder(tmp_path):
    text = write(tmp_path, []).path.read_text(encoding="utf-8")
    assert "## Highlights\n\n_No highlights yet._\n" + END in text


def test_multiline_highlight_is_quoted_line_by_line(tmp_path):
    h = Highlight(H10.id, "line one\nline two", "", 0.5, H10.created_at)
    assert "> line one\n> line two\n" in write(tmp_path, [h]).path.read_text(encoding="utf-8")


def test_frontmatter_quotes_yaml_hostile_titles():
    fm = render_frontmatter(BookMeta("x", 'Re: "Kahneman"', None, None))
    assert 'title: "Re: \\"Kahneman\\""' in fm
    assert "author" not in fm





def test_user_text_outside_markers_survives(tmp_path):
    first = write(tmp_path, [H10])
    original = first.path.read_text(encoding="utf-8")
    edited = original.replace(INTRO, INTRO + "\n\nMy own thoughts.") + "\nAfterword.\n"
    first.path.write_text(edited, encoding="utf-8")
    second = write(tmp_path, [H10, H42], last_hash=first.region_hash)
    text = second.path.read_text(encoding="utf-8")
    assert "My own thoughts." in text and text.endswith("Afterword.\n")
    assert "^h-01jb7x3k9q2m4n5p6r7s8t9v0w" in text
    assert second.conflict_path is None


def test_missing_markers_appends_region(tmp_path):
    folder = tmp_path / "Hudhud"
    folder.mkdir()
    (folder / "Thinking, Fast and Slow.md").write_text("# My notes\n\nHand-written.\n",
                                                       encoding="utf-8")
    text = write(tmp_path, [H10]).path.read_text(encoding="utf-8")
    assert text.startswith("# My notes\n\nHand-written.\n\n" + START)
    assert text.endswith(END + "\n")


def test_edited_region_gets_a_conflict_copy(tmp_path):
    first = write(tmp_path, [H10])
    tampered = first.path.read_text(encoding="utf-8").replace("frequent repetition", "MY EDIT")
    first.path.write_text(tampered, encoding="utf-8")
    second = write(tmp_path, [H10], last_hash=first.region_hash)
    assert second.conflict_path == first.path.with_name(
        "Thinking, Fast and Slow.conflict-20261008T123456Z.md")
    assert second.conflict_path.read_text(encoding="utf-8") == tampered
    assert "frequent repetition" in second.path.read_text(encoding="utf-8")


def test_crlf_only_change_is_not_a_conflict(tmp_path):
    first = write(tmp_path, [H10])
    first.path.write_bytes(first.path.read_bytes().replace(b"\n", b"\r\n"))
    assert write(tmp_path, [H10], last_hash=first.region_hash).conflict_path is None


def test_no_known_hash_means_no_conflict(tmp_path):
    first = write(tmp_path, [H10])
    first.path.write_text(first.path.read_text("utf-8").replace("frequent", "X"), "utf-8")
    assert write(tmp_path, [H10], last_hash=None).conflict_path is None


def test_marker_text_in_highlight_is_escaped(tmp_path):
    evil = Highlight(H10.id, "before <!-- hudhud:end --> after", "see <!-- hudhud:start", 0.5,
                     H10.created_at)
    text = write(tmp_path, [evil]).path.read_text(encoding="utf-8")
    assert text.count(END) == 1 and text.count(START_PREFIX) == 1
    assert "&lt;!-- hudhud:end --> after" in extract_region(text)


def test_same_title_different_books_do_not_collide(tmp_path):
    other = BookMeta("9" * 64, BOOK.title, "Someone Else", "en")
    a = write(tmp_path, [H10])
    b = write(tmp_path, [H42], book=other)
    assert a.path != b.path
    assert b.path.name == "Thinking, Fast and Slow (99999999).md"
    assert frontmatter_book_id(a.path.read_text("utf-8")) == BOOK.id
    assert write(tmp_path, [H10]).path == a.path


def test_bom_does_not_hide_ownership(tmp_path):
    a = write(tmp_path, [H10])
    a.path.write_bytes(b"\xef\xbb\xbf" + a.path.read_bytes())
    assert frontmatter_book_id(a.path.read_text("utf-8")) == BOOK.id
    other = BookMeta("9" * 64, BOOK.title, None, None)
    assert write(tmp_path, [H42], book=other).path != a.path


def test_safe_join_blocks_escape(tmp_path):
    with pytest.raises(ValueError):
        safe_join(tmp_path, "..", "outside.md")
    with pytest.raises(ValueError):
        write_book_note(tmp_path, "../outside", BOOK, [H10], HUB, None, NOW)


def test_atomic_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "note.md"
    atomic_write(target, "a\nb\n")
    atomic_write(target, "c\n")
    assert [p.name for p in tmp_path.iterdir()] == ["note.md"]
    assert target.read_bytes() == b"c\n"
