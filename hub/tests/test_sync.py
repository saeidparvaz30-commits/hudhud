# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from hudhud_hub.sync import pull, push, record_book_import

from .conftest import BOOK_ID

T0 = "2026-10-08T10:00:00.000Z"
T1 = "2026-10-08T11:00:00.000Z"
T2 = "2026-10-08T12:00:00.000Z"
HID = "01JB7X3K9Q2M4N5P6R7S8T9V0W"


def hl(**overrides) -> dict:
    data = {"id": HID, "book_id": BOOK_ID, "locator": "epubcfi(/6/4!/4/2/1:3)", "fraction": 0.42,
            "text": "The confidence people have", "color": "yellow", "comment": "",
            "created_at": T0, "updated_at": T0}
    data.update(overrides)
    return {"entity": "highlight", "op": "upsert", "data": data}


def statuses(results):
    return [r["status"] for r in results]


def test_new_highlight_is_accepted_and_logged(conn, book):
    results, touched = push(conn, "phone", [hl()], T0)
    assert statuses(results) == ["accepted"] and touched == {BOOK_ID}
    change = pull(conn, 0)["changes"][-1]
    assert (change["entity"], change["data"]["id"], change["device_id"]) == ("highlight", HID,
                                                                           "phone")


def test_older_edit_loses(conn, book):
    push(conn, "phone", [hl(updated_at=T1, comment="newer")], T1)
    results, touched = push(conn, "pc", [hl(updated_at=T0, comment="older")], T1)
    assert statuses(results) == ["ignored"] and touched == set()
    assert conn.execute("SELECT comment FROM highlights").fetchone()[0] == "newer"


def test_equal_timestamps_break_ties_by_device(conn, book):
    push(conn, "a-device", [hl(comment="a")], T0)
    assert statuses(push(conn, "b-device", [hl(comment="b")], T0)[0]) == ["accepted"]
    assert statuses(push(conn, "a-device", [hl(comment="a2")], T0)[0]) == ["ignored"]


def test_delete_is_final_even_against_a_later_offline_edit(conn, book):
    push(conn, "phone", [hl()], T0)
    delete = {"entity": "highlight", "op": "delete", "data": {"id": HID, "updated_at": T1}}
    assert statuses(push(conn, "pc", [delete], T1)[0]) == ["accepted"]
    assert statuses(push(conn, "phone", [hl(updated_at=T2, comment="edit")], T2)[0]) == ["ignored"]
    assert conn.execute("SELECT deleted FROM highlights").fetchone()[0] == 1


@pytest.mark.parametrize("bad, reason", [
    (hl(id="not-a-ulid"), "ULID"),
    (hl(book_id="b" * 64), "unknown book"),
    (hl(fraction=1.5), "fraction"),
    (hl(color="red"), "color"),
    (hl(text="   "), "text"),
    (hl(updated_at="yesterday"), "updated_at"),
    ({"entity": "note", "data": {}}, "entity"),
    ({"entity": "highlight"}, "data"),
])
def test_invalid_records_are_rejected_individually(conn, book, bad, reason):
    results, _ = push(conn, "phone", [bad, hl()], T0)
    assert statuses(results) == ["rejected", "accepted"]
    assert reason in results[0]["reason"]


def test_progress_is_written_for_the_pushing_device_only(conn, book):
    change = {"entity": "progress", "data": {"book_id": BOOK_ID, "device_id": "spoofed",
                                             "locator": "cfi", "fraction": 0.5, "updated_at": T0}}
    assert statuses(push(conn, "phone", [change], T0)[0]) == ["accepted"]
    assert [r[0] for r in conn.execute("SELECT device_id FROM progress")] == ["phone"]
    assert statuses(push(conn, "phone", [change], T0)[0]) == ["ignored"]


def test_book_rename_and_delete(conn, book):
    rename = {"entity": "book", "data": {"id": BOOK_ID, "title": "Masnavi-ye Ma'navi",
                                         "author": "Rumi", "updated_at": T1}}
    delete = {"entity": "book", "op": "delete", "data": {"id": BOOK_ID, "updated_at": T2}}
    assert statuses(push(conn, "pc", [rename, delete], T2)[0]) == ["accepted", "accepted"]
    last = pull(conn, 0)["changes"][-1]["data"]
    assert last["deleted"] is True and "cover_path" not in last and last["has_cover"] is False


def test_failed_record_leaves_no_partial_change(conn, book):
    before = pull(conn, 0)["cursor"]
    push(conn, "phone", [hl(color="red")], T0)
    assert pull(conn, before)["changes"] == []


def test_pull_pages_by_cursor(conn, book):
    record_book_import(conn, BOOK_ID, "pc", T0)
    push(conn, "phone", [hl(id=f"01JB7X3K9Q2M4N5P6R7S8T9V0{c}") for c in "ABC"], T0)
    first = pull(conn, 0, limit=2)
    assert len(first["changes"]) == 2 and first["more"] is True
    rest = pull(conn, first["cursor"], limit=10)
    assert len(rest["changes"]) == 2 and rest["more"] is False
    assert pull(conn, rest["cursor"])["changes"] == []


def test_two_devices_converge(conn, book):
    """Both devices edit offline, then sync in either order: the hub keeps the newest."""
    phone = [hl(updated_at=T1, comment="from phone")]
    pc = [hl(updated_at=T2, comment="from pc"),
          hl(id="01JB7X3K9Q2M4N5P6R7S8T9V0Z", text="another", updated_at=T1)]
    push(conn, "pc", pc, T2)
    push(conn, "phone", phone, T2)
    rows = {r[0]: r[1] for r in conn.execute("SELECT id, comment FROM highlights")}
    assert rows == {HID: "from pc", "01JB7X3K9Q2M4N5P6R7S8T9V0Z": ""}


@pytest.mark.parametrize("bad", [
    hl(color=[]),
    hl(fraction=None),
    {"entity": "highlight", "data": {"id": HID, "updated_at": T0, "book_id": ["x"]}},
    {"entity": ["highlight"], "data": {}},
])
def test_malformed_values_are_rejections_not_crashes(conn, book, bad):
    results, _ = push(conn, "phone", [bad, hl()], T0)
    assert statuses(results) == ["rejected", "accepted"]


def test_pull_reports_the_latest_seq_so_clients_detect_a_reset_hub(conn, book):
    record_book_import(conn, BOOK_ID, "pc", T0)
    page = pull(conn, 999)
    assert page["changes"] == [] and page["latest"] == 1
