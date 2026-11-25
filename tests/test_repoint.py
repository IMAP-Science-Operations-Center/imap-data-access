"""Tests for looking up repointing maneuvers and pointings."""

from datetime import datetime, timezone

import pytest

import imap_data_access
from imap_data_access import Repoint, query_repoint, repoint

HEADER = (
    "repoint_start_sec_sclk,repoint_start_subsec_sclk,repoint_end_sec_sclk,"
    "repoint_end_subsec_sclk,repoint_start_utc,repoint_end_utc,repoint_id\n"
)

# Three maneuvers, as in a real repoint file, with a blank line at the end.
REPOINT_FILE = HEADER + (
    "1,0,2,0,2025-09-27 19:05:04.422138,2025-09-27 19:09:25.421900,1\n"
    "3,0,4,0,2025-09-29 10:00:06.294434,2025-09-29 10:04:27.294196,2\n"
    "5,0,6,0,2025-09-30T10:00:07.215668,2025-09-30T10:01:43.215581,3\n"
    ",,,,,,\n"
)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clear_repoint_cache():
    repoint._clear_cache()
    yield
    repoint._clear_cache()


@pytest.fixture
def sdc(monkeypatch):
    """Stand in for the SDC: one repoint file, and counts of the requests made."""
    state = {"files": {"imap/spice/repoint/a.repoint": REPOINT_FILE}, "lists": 0}
    state["newest"] = "imap/spice/repoint/a.repoint"
    state["reads"] = []

    def latest():
        state["lists"] += 1
        return state["newest"]

    def read(file_path):
        state["reads"].append(file_path)
        return state["files"][file_path]

    monkeypatch.setattr(repoint, "_latest_repoint_file", latest)
    monkeypatch.setattr(repoint, "_read_file", read)
    return state


def test_parse_repoints():
    repoints = repoint._parse_repoints(REPOINT_FILE)
    assert list(repoints) == [1, 2, 3]
    assert repoints[1] == Repoint(
        repoint_id=1,
        repoint_start=utc(2025, 9, 27, 19, 5, 4, 422138),
        repoint_end=utc(2025, 9, 27, 19, 9, 25, 421900),
        # A pointing runs from the end of its maneuver to the end of the next.
        pointing_start=utc(2025, 9, 27, 19, 9, 25, 421900),
        pointing_end=utc(2025, 9, 29, 10, 4, 27, 294196),
    )
    # Times with a "T" between the date and time are read too.
    assert repoints[2].pointing_end == utc(2025, 9, 30, 10, 1, 43, 215581)
    # The last pointing hasn't ended.
    assert repoints[3].pointing_end is None


def test_parse_repoints_missing_times():
    """Missing or unreadable times are None, as in the SDC's pointing table."""
    text = HEADER + (
        "1,0,2,0,2025-09-27 19:05:04.422138,nan,1\n"
        "3,0,4,0,2025-09-29 10:00:06.294434,2025-09-29 10:04:27,2\n"
        "5,0,6,0,,2025-09-30 10:01:43.215581,3\n"
    )
    repoints = repoint._parse_repoints(text)
    assert repoints[1].pointing_start is None
    # A time without fractional seconds isn't read, as in the pointing table.
    assert repoints[1].pointing_end is None
    assert repoints[2].pointing_start is None
    assert repoints[3].repoint_start is None
    assert repoints[2].pointing_end == utc(2025, 9, 30, 10, 1, 43, 215581)


def test_query_repoint(sdc):
    assert query_repoint(2).pointing_start == utc(2025, 9, 29, 10, 4, 27, 294196)
    assert query_repoint(1).repoint_id == 1
    # The file is read once, and reused for later lookups.
    assert sdc["lists"] == 1
    assert sdc["reads"] == ["imap/spice/repoint/a.repoint"]


@pytest.mark.parametrize("repoint_id", [3, 4], ids=["not ended", "not listed"])
def test_query_repoint_checks_for_a_newer_file(sdc, repoint_id):
    """A pointing that's missing or hasn't ended sends it back to the SDC."""
    query_repoint(1)
    sdc["files"]["imap/spice/repoint/b.repoint"] = REPOINT_FILE.replace(
        ",,,,,,\n",
        "7,0,8,0,2025-10-01 10:00:00.000000,2025-10-01 10:03:00.000000,4\n"
        "9,0,10,0,2025-10-02 10:00:00.000000,2025-10-02 10:03:00.000000,5\n",
    )
    sdc["newest"] = "imap/spice/repoint/b.repoint"

    found = query_repoint(repoint_id)
    assert found.pointing_end is not None
    assert sdc["reads"] == [
        "imap/spice/repoint/a.repoint",
        "imap/spice/repoint/b.repoint",
    ]


def test_query_repoint_unknown(sdc):
    """With no newer file, an unknown maneuver is None, and nothing is reread."""
    assert query_repoint(99) is None
    assert sdc["lists"] == 2
    assert sdc["reads"] == ["imap/spice/repoint/a.repoint"]


def test_query_repoint_no_files(sdc):
    sdc["newest"] = None
    assert query_repoint(1) is None
    assert sdc["reads"] == []


def test_latest_repoint_file(mock_send_request):
    mock_send_request.return_value.json.return_value = [
        {
            "file_path": "imap/spice/repoint/imap_2026_326_01.repoint",
            "end_date": "2026-11-22, 10:03:27",
            "version": "01",
            "ingestion_date": "2026-11-25, 13:50:12",
        },
        {
            "file_path": "imap/spice/repoint/imap_2026_327_01.repoint",
            "end_date": "2026-11-23, 10:03:27",
            "version": "01",
            "ingestion_date": "2026-11-24, 13:50:12",
        },
        {
            "file_path": "imap/spice/repoint/imap_2026_327_02.repoint",
            "end_date": "2026-11-23, 10:03:27",
            "version": "02",
            "ingestion_date": "2026-11-24, 13:50:12",
        },
    ]
    # The latest end date wins, then the highest version, even over a file
    # that was ingested later.
    assert (
        repoint._latest_repoint_file() == "imap/spice/repoint/imap_2026_327_02.repoint"
    )
    request = mock_send_request.call_args.args[0]
    assert request.url == f"{imap_data_access.config['DATA_ACCESS_URL']}/repoint-table"


def test_latest_repoint_file_none(mock_send_request):
    mock_send_request.return_value.json.return_value = []
    assert repoint._latest_repoint_file() is None


def test_read_file(mock_send_request, monkeypatch):
    """The file is read through the download endpoint, with the API key route."""
    monkeypatch.setitem(imap_data_access.config, "API_KEY", "test-key")
    mock_send_request.return_value.content = REPOINT_FILE.encode()
    assert repoint._read_file("imap/spice/repoint/a.repoint") == REPOINT_FILE
    request = mock_send_request.call_args.args[0]
    assert request.url == (
        f"{imap_data_access.config['DATA_ACCESS_URL']}"
        "/api-key/download/imap/spice/repoint/a.repoint"
    )
    assert request.headers["x-api-key"] == "test-key"
