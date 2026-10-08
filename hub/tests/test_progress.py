# SPDX-License-Identifier: AGPL-3.0-or-later
import math
import sqlite3

import pytest
from hudhud_hub.db import MIGRATIONS
from hudhud_hub.progress import (
    Progress,
    get_progress,
    latest_other_device,
    should_offer_resume,
    upsert_progress,
)

SCHEMA = (MIGRATIONS / "0001_init.sql").read_text(encoding="utf-8")
BOOK = "b" * 64


def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO books (id, title, format, file_size, added_at, updated_at) "
        "VALUES (?, 'Divan', 'epub', 1, 't', 't')", (BOOK,))
    return conn


def p(device="pc", fraction=0.5, at="2026-10-08T10:00:00.000Z", locator="epubcfi(/6/4!/4/2/1:3)"):
    return Progress(BOOK, device, locator, fraction, at)





def test_first_write_is_stored():
    conn = db()
    assert upsert_progress(conn, p()) is True
    assert get_progress(conn, BOOK, "pc") == p()


def test_newer_wins_older_is_ignored():
    conn = db()
    upsert_progress(conn, p(fraction=0.5, at="2026-10-08T10:00:00.000Z"))
    assert upsert_progress(conn, p(fraction=0.6, at="2026-10-08T11:00:00.000Z")) is True
    assert upsert_progress(conn, p(fraction=0.1, at="2026-10-08T09:00:00.000Z")) is False
    assert get_progress(conn, BOOK, "pc").fraction == 0.6


def test_equal_timestamp_is_ignored():
    conn = db()
    upsert_progress(conn, p(fraction=0.5))
    assert upsert_progress(conn, p(fraction=0.9)) is False
    assert get_progress(conn, BOOK, "pc").fraction == 0.5


@pytest.mark.parametrize("fraction", [-0.01, 1.01, math.nan])
def test_bad_fraction_rejected(fraction):
    with pytest.raises(ValueError):
        upsert_progress(db(), p(fraction=fraction))


@pytest.mark.parametrize("at", ["2026-10-08T10:00:00Z", "2026-10-08 10:00:00.000Z", "zzz", ""])
def test_malformed_timestamp_rejected(at):
    with pytest.raises(ValueError):
        upsert_progress(db(), p(at=at))


def test_empty_locator_rejected():
    with pytest.raises(ValueError):
        upsert_progress(db(), p(locator=""))


def test_locator_is_stored_verbatim():
    conn = db()
    weird = "epubcfi(/6/14!/4/2[فصل-۱]/1:0)"
    upsert_progress(conn, p(locator=weird))
    assert get_progress(conn, BOOK, "pc").locator == weird


def test_unknown_device_has_no_progress():
    assert get_progress(db(), BOOK, "phone") is None


def test_latest_other_device_skips_own_and_picks_newest():
    conn = db()
    upsert_progress(conn, p("pc", 0.9, "2026-10-08T12:00:00.000Z"))
    upsert_progress(conn, p("phone", 0.3, "2026-10-08T10:00:00.000Z"))
    upsert_progress(conn, p("tablet", 0.4, "2026-10-08T11:00:00.000Z"))
    assert latest_other_device(conn, BOOK, "pc").device_id == "tablet"
    assert latest_other_device(conn, BOOK, "tablet").device_id == "pc"


def test_no_other_device():
    conn = db()
    upsert_progress(conn, p("pc"))
    assert latest_other_device(conn, BOOK, "pc") is None


def test_resume_rule():
    early, late = "2026-10-08T10:00:00.000Z", "2026-10-08T11:00:00.000Z"
    assert should_offer_resume(None, None, 300) is False
    assert should_offer_resume(None, p("phone", 0.63, late), 300) is True
    assert should_offer_resume(p("pc", 0.20, early), p("phone", 0.63, late), 300) is True
    assert should_offer_resume(p("pc", 0.500, early), p("phone", 0.502, late), 300) is False
    assert should_offer_resume(p("pc", 0.20, late), p("phone", 0.63, early), 300) is False
    assert should_offer_resume(p("pc", 0.63, early), p("phone", 0.20, late), 300) is True


def test_resume_rule_needs_pages():
    with pytest.raises(ValueError):
        should_offer_resume(None, p(), 0)
