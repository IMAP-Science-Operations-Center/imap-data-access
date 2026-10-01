import datetime
import hashlib
from unittest.mock import MagicMock, patch

import pytest

import imap_data_access
from imap_data_access import ScienceFilePath
from imap_data_access.io import IMAPDataAccessError
from imap_data_access.webpoda import (
    INSTRUMENT_APIDS,
    _compare_and_write_new_data,
    _get_webpoda_headers,
    _latest_l0_minor_version,
    _upload_if_requested,
    compare_files,
    download_daily_data,
    download_repointing_data,
    file_hash,
    format_size,
    get_packet_binary_data_sctime,
    get_packet_times_ert,
    get_repoint_file,
)

# A minimal set of repoint rows covering:
# - a completed pointing (1 -> 2) fully within the query range
# - a completed pointing (2 -> 3) fully within the query range
# - an incomplete repointing maneuver (NaN end time) that must be skipped
REPOINT_DATA = [
    {
        "repoint_end_utc": "2024-11-30 20:15:00.000",
        "repoint_id": "1",
    },
    {
        "repoint_end_utc": "2024-12-01 00:15:00.000",
        "repoint_id": "2",
    },
    {
        "repoint_end_utc": "2024-12-02 00:15:00.000",
        "repoint_id": "3",
    },
    {
        # An unfinished repointing maneuver may have NaNs in the end times
        "repoint_end_utc": "NaN",
        "repoint_id": "4",
    },
    {
        "repoint_end_utc": "2024-12-04 00:15:00.000",
        "repoint_id": "5",
    },
]


def test_get_webpoda_headers(monkeypatch):
    assert _get_webpoda_headers() == {"Authorization": "Basic test_token"}

    # Test that it raises with no authorization present
    monkeypatch.setitem(imap_data_access.config, "WEBPODA_TOKEN", None)
    with pytest.raises(ValueError, match="The IMAP_WEBPODA_TOKEN"):
        _get_webpoda_headers()


def test_get_packet_times_ert(mock_send_request, mock_request):
    mock_response = MagicMock()
    mock_response.text = "2024-12-01T00:00:00\n2024-12-01T00:00:01\n"
    mock_send_request.return_value = mock_response

    start_time = datetime.datetime(2024, 12, 1, 0, 0, 0)
    end_time = datetime.datetime(2024, 12, 1, 23, 59, 59)
    apid = 1136

    result = get_packet_times_ert(apid, start_time, end_time)

    # Verify the request was prepared correctly
    mock_request.assert_called_once_with(
        "GET",
        f"https://lasp.colorado.edu/ops/imap/poda/dap2/apids/SID1/apid_{apid}.txt",
        headers={"Authorization": "Basic test_token"},
        params=(
            f"ert>={start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')}"
            f"&ert<{end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')}"
            "&project(time)&formatTime(\"yyyy-MM-dd'T'HH:mm:ss\")"
        ),
    )

    # Verify the response was parsed correctly
    assert len(result) == 2
    assert result[0] == datetime.datetime(2024, 12, 1, 0, 0, 0)
    assert result[1] == datetime.datetime(2024, 12, 1, 0, 0, 1)


def test_get_packet_binary_data_sctime(mock_send_request, mock_request):
    mock_response = MagicMock()
    mock_response.content = b"\x00\x01\x02\x03"
    mock_send_request.return_value = mock_response

    start_time = datetime.datetime(2024, 12, 1, 0, 0, 0)
    end_time = datetime.datetime(2024, 12, 1, 23, 59, 59, 999999)
    apid = 1136

    result = get_packet_binary_data_sctime(apid, start_time, end_time)

    # Verify the request was prepared correctly
    mock_request.assert_called_once_with(
        "GET",
        f"https://lasp.colorado.edu/ops/imap/poda/dap2/apids/SID1/apid_{apid}.bin",
        headers={"Authorization": "Basic test_token"},
        params=(
            f"time>={start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')}"
            f"&time<{end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')}"
            "&project(packet)"
        ),
    )

    # Verify the response was parsed correctly
    assert result == b"\x00\x01\x02\x03"


@patch("imap_data_access.webpoda.get_packet_binary_data_sctime")
@patch("imap_data_access.webpoda.get_packet_times_ert")
@patch("imap_data_access.webpoda.imap_data_access.upload")
@patch("imap_data_access.webpoda.imap_data_access.query")
@pytest.mark.parametrize("upload_to_sdc", [True, False])
def test_download_daily_data(
    mock_query,
    mock_upload,
    mock_get_packet_times_ert,
    mock_get_packet_binary_data_sctime,
    upload_to_sdc,
):
    # No existing L0 files in production, so everything is written as minor
    # version 1 with no comparison needed.
    mock_query.return_value = []
    # We are mocking the upload, lets also verify that
    # duplicate files don't propagate any errors.
    mock_upload.side_effect = IMAPDataAccessError("File already exists")
    mock_get_packet_times_ert.return_value = [
        datetime.datetime(2024, 12, 1, 0, 0, 0),
        datetime.datetime(2024, 12, 2, 0, 0, 0),
    ]
    mock_get_packet_binary_data_sctime.return_value = b"\x00\x01\x02\x03"

    start_time = datetime.datetime(2024, 12, 1, 0, 0, 0)
    end_time = datetime.datetime(2024, 12, 3, 23, 59, 59)
    instrument = "swapi"

    download_daily_data(instrument, start_time, end_time, upload_to_sdc=upload_to_sdc)

    # Make sure swapi was called with a buffer of 1 minute on either side of midnight
    call = mock_get_packet_binary_data_sctime.call_args_list[0][0]
    assert call == (
        1184,
        start_time - datetime.timedelta(minutes=1),
        # end time + 1 day, then buffer of 1 minute
        start_time + datetime.timedelta(days=1) + datetime.timedelta(minutes=1),
    )

    # We expect two daily files to be created because we have packets
    # across two separate days
    for day in mock_get_packet_times_ert.return_value:
        expected_file_path = ScienceFilePath.generate_from_inputs(
            instrument=instrument,
            data_level="l0",
            descriptor="raw",
            start_time=day.strftime("%Y%m%d"),
            major_version=1,
            minor_version=1,
        ).construct_path()
        # There are two swapi apids, so we download the same byte stream twice
        n_apids = len(INSTRUMENT_APIDS[instrument])
        assert expected_file_path.read_bytes() == b"\x00\x01\x02\x03" * n_apids
        assert mock_upload.called is upload_to_sdc


@patch("imap_data_access.webpoda.get_packet_binary_data_sctime")
@patch("imap_data_access.webpoda.get_packet_times_ert")
@patch("imap_data_access.webpoda.imap_data_access.upload")
@patch("imap_data_access.webpoda.imap_data_access.query")
@pytest.mark.parametrize("upload_to_sdc", [True, False])
def test_download_repointing_data(
    mock_query,
    mock_upload,
    mock_get_packet_times_ert,
    mock_get_packet_binary_data_sctime,
    upload_to_sdc,
):
    mock_query.return_value = []
    # We are mocking the upload, lets also verify that
    # duplicate files don't propagate any errors.
    mock_upload.side_effect = IMAPDataAccessError("File already exists")
    mock_get_packet_binary_data_sctime.return_value = b"\x00\x01\x02\x03"

    start_time = datetime.datetime(2024, 12, 1, 0, 0, 0)
    end_time = datetime.datetime(2024, 12, 3, 23, 59, 59)
    instrument = "hi"

    # Test that no packets returned doesn't fail and doesn't produce any files
    mock_get_packet_times_ert.return_value = []
    download_repointing_data(
        instrument,
        start_time,
        end_time,
        repoint_data=REPOINT_DATA,
        upload_to_sdc=upload_to_sdc,
    )
    assert not (imap_data_access.config["DATA_DIR"] / "imap").exists()

    # Now test with some returned packets
    mock_get_packet_times_ert.return_value = [
        datetime.datetime(2024, 12, 1, 0, 0, 0),
        # This packet is right on a pointing boundary, it shouldn't be
        # in both files but only the second one.
        datetime.datetime(2024, 12, 1, 0, 15, 0),
        # This packet is after valid repointings in the file and shouldn't be counted
        datetime.datetime(2024, 12, 2, 12, 0, 0),
    ]
    download_repointing_data(
        instrument,
        start_time,
        end_time,
        repoint_data=REPOINT_DATA,
        upload_to_sdc=upload_to_sdc,
    )

    # We expect two repointing files to be created because we have packets
    # across two separate repointing periods
    for repoint_id, date in [(1, "20241130"), (2, "20241201")]:
        expected_file_path = ScienceFilePath.generate_from_inputs(
            instrument=instrument,
            data_level="l0",
            descriptor="raw",
            start_time=date,
            repointing=repoint_id,
            major_version=1,
            minor_version=1,
        ).construct_path()
        # There are two hi apids, so we download the same byte stream twice
        n_apids = len(INSTRUMENT_APIDS[instrument])
        assert expected_file_path.read_bytes() == b"\x00\x01\x02\x03" * n_apids
        assert mock_upload.called is upload_to_sdc
    assert (imap_data_access.config["DATA_DIR"] / "imap").exists()


@patch("imap_data_access.webpoda.imap_data_access.download")
@patch("imap_data_access.webpoda.get_packet_binary_data_sctime")
@patch("imap_data_access.webpoda.get_packet_times_ert")
@patch("imap_data_access.webpoda.imap_data_access.query")
def test_file_versioning(
    mock_query,
    mock_get_packet_times_ert,
    mock_get_packet_binary_data_sctime,
    mock_download,
    tmp_path,
):
    # One existing prod file (with different, smaller content) triggers the
    # comparison path for each day, and since the freshly queried data
    # differs, it should be kept as minor_version=3.
    prod_path = tmp_path / "prod.pkts"
    prod_path.write_bytes(b"\x00\x01")
    mock_download.return_value = prod_path
    mock_query.return_value = [
        {"minor_version": 1, "file_path": "imap_swapi_l0_raw_20241201_v001.pkts"},
        {"minor_version": 2, "file_path": "imap_swapi_l0_raw_20241201_v002.pkts"},
    ]

    mock_get_packet_times_ert.return_value = [
        datetime.datetime(2024, 12, 1, 0, 0, 0),
        datetime.datetime(2024, 12, 2, 0, 0, 0),
    ]
    mock_get_packet_binary_data_sctime.return_value = b"\x00\x01\x02\x03"

    start_time = datetime.datetime(2024, 12, 1, 0, 0, 0)
    end_time = datetime.datetime(2024, 12, 3, 23, 59, 59)
    instrument = "swapi"

    download_daily_data(instrument, start_time, end_time)

    # We expect two daily files to be created because we have packets
    # across two separate days
    for day in mock_get_packet_times_ert.return_value:
        expected_file_path = ScienceFilePath.generate_from_inputs(
            instrument=instrument,
            data_level="l0",
            descriptor="raw",
            start_time=day.strftime("%Y%m%d"),
            major_version=1,
            minor_version=3,
        ).construct_path()
        # There are two swapi apids, so we download the same byte stream twice
        n_apids = len(INSTRUMENT_APIDS[instrument])
        assert expected_file_path.read_bytes() == b"\x00\x01\x02\x03" * n_apids


def test_get_repoint_file_no_files(mock_send_request, mock_request):
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_send_request.return_value = mock_response

    result = get_repoint_file()

    assert result is None


@patch("imap_data_access.webpoda.imap_data_access.download")
def test_get_repoint_file(mock_download, mock_send_request, mock_request):
    mock_download.return_value = "downloaded_repoint_table_path"
    mock_response = MagicMock()
    # Both entries share the same end_date but the second is a more recently
    # ingested (and therefore fresher/more complete) snapshot.
    mock_response.json.return_value = [
        {"file_path": "older.repoint.csv", "ingestion_date": "2024-12-01, 00:00:00"},
        {"file_path": "newest.repoint.csv", "ingestion_date": "2024-12-02, 00:00:00"},
    ]
    mock_send_request.return_value = mock_response

    before_call = datetime.datetime.now()
    result = get_repoint_file()
    after_call = datetime.datetime.now()

    # The ingestion window queried is always "the last two weeks", regardless
    # of any spacecraft data range being downloaded. The end date is pushed
    # a day past "now" since the endpoint floors end_ingest_date to midnight.
    assert mock_request.call_count == 1
    call_args = mock_request.call_args
    assert call_args[0] == (
        "GET",
        f"{imap_data_access.config['DATA_ACCESS_URL']}/repoint-table",
    )
    queried_end = datetime.datetime.strptime(
        call_args.kwargs["params"]["end_ingest_date"], "%Y%m%d"
    )
    queried_start = datetime.datetime.strptime(
        call_args.kwargs["params"]["start_ingest_date"], "%Y%m%d"
    )
    assert (
        before_call.date() + datetime.timedelta(days=1)
        <= queried_end.date()
        <= after_call.date() + datetime.timedelta(days=1)
    )
    assert queried_end - queried_start == datetime.timedelta(weeks=2, days=1)
    mock_download.assert_called_once_with("newest.repoint.csv")
    assert result == "downloaded_repoint_table_path"


def test_file_hash(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"hello world")

    assert file_hash(path) == hashlib.sha256(b"hello world").hexdigest()


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (500_000, "0.5000 MB"),
        (2_000_000_000, "2.0000 GB"),
    ],
)
def test_format_size(size_bytes, expected):
    assert format_size(size_bytes) == expected


def test_compare_files_changed(tmp_path):
    current = tmp_path / "current.pkts"
    new = tmp_path / "new.pkts"
    current.write_bytes(b"\x00\x01")
    new.write_bytes(b"\x00\x01\x02")

    assert compare_files(current, new) is True


def test_compare_files_unchanged(tmp_path):
    current = tmp_path / "current.pkts"
    new = tmp_path / "new.pkts"
    current.write_bytes(b"\x00\x01\x02")
    new.write_bytes(b"\x00\x01\x02")

    assert compare_files(current, new) is False


def test_latest_l0_minor_version_no_existing_files():
    result = _latest_l0_minor_version([])

    assert result == 1


def test_latest_l0_minor_version_existing_files():
    result = _latest_l0_minor_version([{"minor_version": 1}, {"minor_version": 2}])

    assert result == 3


@patch("imap_data_access.webpoda.imap_data_access.upload")
def test_upload_if_requested(mock_upload, tmp_path):
    path = tmp_path / "data.pkts"
    path.write_bytes(b"data")

    _upload_if_requested(path, upload_to_sdc=False)
    mock_upload.assert_not_called()

    _upload_if_requested(path, upload_to_sdc=True)
    mock_upload.assert_called_once_with(path)


@patch("imap_data_access.webpoda.imap_data_access.upload")
def test_upload_if_requested_handles_failure(mock_upload, tmp_path):
    path = tmp_path / "data.pkts"
    path.write_bytes(b"data")
    mock_upload.side_effect = IMAPDataAccessError("File already exists")

    # Should not raise, just log the error
    _upload_if_requested(path, upload_to_sdc=True)


@patch("imap_data_access.webpoda.imap_data_access.query")
def test_compare_and_write_new_data_no_existing_file(mock_query):
    mock_query.return_value = []
    instrument = "swapi"
    start_time = datetime.datetime(2024, 12, 1)

    path = _compare_and_write_new_data(
        instrument=instrument, start_time=start_time, content=b"\x00\x01"
    )

    expected_path = ScienceFilePath.generate_from_inputs(
        instrument=instrument,
        data_level="l0",
        descriptor="raw",
        start_time=start_time.strftime("%Y%m%d"),
        major_version=1,
        minor_version=1,
    ).construct_path()
    assert path == expected_path
    assert path.read_bytes() == b"\x00\x01"


@patch("imap_data_access.webpoda.imap_data_access.download")
@patch("imap_data_access.webpoda.imap_data_access.query")
def test_compare_and_write_new_data_existing_minor_version_zero(
    mock_query, mock_download, tmp_path
):
    # A file at minor_version=0 also produces a next version of 1, so this
    # must still go through the comparison path instead of being treated as
    # if no L0 file exists yet.
    instrument = "swapi"
    start_time = datetime.datetime(2024, 12, 1)

    prod_path = tmp_path / "prod.pkts"
    prod_path.write_bytes(b"\x00\x01")
    mock_download.return_value = prod_path
    mock_query.return_value = [
        {"minor_version": 0, "file_path": "imap_swapi_l0_raw_20241201_v000.pkts"}
    ]

    path = _compare_and_write_new_data(
        instrument=instrument, start_time=start_time, content=b"\x00\x01\x02"
    )

    expected_path = ScienceFilePath.generate_from_inputs(
        instrument=instrument,
        data_level="l0",
        descriptor="raw",
        start_time=start_time.strftime("%Y%m%d"),
        major_version=1,
        minor_version=1,
    ).construct_path()
    assert path == expected_path
    mock_download.assert_called_once_with("imap_swapi_l0_raw_20241201_v000.pkts")


@patch("imap_data_access.webpoda.imap_data_access.download")
@patch("imap_data_access.webpoda.imap_data_access.query")
def test_compare_and_write_new_data_changed(mock_query, mock_download, tmp_path):
    instrument = "swapi"
    start_time = datetime.datetime(2024, 12, 1)

    prod_path = tmp_path / "prod.pkts"
    prod_path.write_bytes(b"\x00\x01")
    mock_download.return_value = prod_path

    # One existing L0 file; its file_path is used to download the prod file
    # to compare against, and its minor_version to compute the next one.
    mock_query.return_value = [
        {"minor_version": 1, "file_path": "imap_swapi_l0_raw_20241201_v001.pkts"}
    ]

    path = _compare_and_write_new_data(
        instrument=instrument, start_time=start_time, content=b"\x00\x01\x02"
    )

    expected_path = ScienceFilePath.generate_from_inputs(
        instrument=instrument,
        data_level="l0",
        descriptor="raw",
        start_time=start_time.strftime("%Y%m%d"),
        major_version=1,
        minor_version=2,
    ).construct_path()
    assert path == expected_path
    assert path.read_bytes() == b"\x00\x01\x02"
    # The production file used for comparison is left untouched
    assert prod_path.exists()


@patch("imap_data_access.webpoda.imap_data_access.download")
@patch("imap_data_access.webpoda.imap_data_access.query")
def test_compare_and_write_new_data_unchanged(mock_query, mock_download, tmp_path):
    instrument = "swapi"
    start_time = datetime.datetime(2024, 12, 1)

    prod_path = tmp_path / "prod.pkts"
    prod_path.write_bytes(b"\x00\x01\x02")
    mock_download.return_value = prod_path

    mock_query.return_value = [
        {"minor_version": 1, "file_path": "imap_swapi_l0_raw_20241201_v001.pkts"}
    ]

    path = _compare_and_write_new_data(
        instrument=instrument, start_time=start_time, content=b"\x00\x01\x02"
    )

    assert path is None
    # The duplicate new file and the downloaded prod file are left in place
    new_path = ScienceFilePath.generate_from_inputs(
        instrument=instrument,
        data_level="l0",
        descriptor="raw",
        start_time=start_time.strftime("%Y%m%d"),
        major_version=1,
        minor_version=2,
    ).construct_path()
    assert new_path.exists()
    assert prod_path.exists()
