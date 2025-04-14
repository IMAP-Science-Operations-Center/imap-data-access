import datetime
from unittest.mock import MagicMock, patch

import pytest

import imap_data_access
from imap_data_access import ScienceFilePath
from imap_data_access.io import IMAPDataAccessError
from imap_data_access.webpoda import (
    INSTRUMENT_APIDS,
    _get_webpoda_headers,
    download_daily_data,
    download_repointing_data,
    get_packet_binary_data_sctime,
    get_packet_times_ert,
)


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
        f"https://lasp.colorado.edu/ops/imap/poda/dap2/apids/SID2/apid_{apid}.txt",
        headers={"Authorization": "Basic test_token"},
        params=(
            f"ert>={start_time.strftime('%Y-%m-%dT%H:%M:%S')}"
            f"&ert<={end_time.strftime('%Y-%m-%dT%H:%M:%S')}"
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
    end_time = datetime.datetime(2024, 12, 1, 23, 59, 59)
    apid = 1136

    result = get_packet_binary_data_sctime(apid, start_time, end_time)

    # Verify the request was prepared correctly
    mock_request.assert_called_once_with(
        "GET",
        f"https://lasp.colorado.edu/ops/imap/poda/dap2/apids/SID2/apid_{apid}.bin",
        headers={"Authorization": "Basic test_token"},
        params=(
            f"time>={start_time.strftime('%Y-%m-%dT%H:%M:%S')}"
            f"&time<={end_time.strftime('%Y-%m-%dT%H:%M:%S')}"
            "&project(packet)"
        ),
    )

    # Verify the response was parsed correctly
    assert result == b"\x00\x01\x02\x03"


@patch("imap_data_access.webpoda.get_packet_binary_data_sctime")
@patch("imap_data_access.webpoda.get_packet_times_ert")
@patch("imap_data_access.webpoda.imap_data_access.upload")
@pytest.mark.parametrize("upload_to_server", [True, False])
def test_download_daily_data(
    mock_upload,
    mock_get_packet_times_ert,
    mock_get_packet_binary_data_sctime,
    upload_to_server,
):
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

    download_daily_data(
        instrument, start_time, end_time, upload_to_server=upload_to_server
    )

    # We expect two daily files to be created because we have packets
    # across two separate days
    for day in mock_get_packet_times_ert.return_value:
        expected_file_path = ScienceFilePath.generate_from_inputs(
            instrument=instrument,
            data_level="l0",
            descriptor="raw",
            start_time=day.strftime("%Y%m%d"),
            version="v001",
        ).construct_path()
        # There are two swapi apids, so we download the same byte stream twice
        n_apids = len(INSTRUMENT_APIDS[instrument])
        assert expected_file_path.read_bytes() == b"\x00\x01\x02\x03" * n_apids
        assert mock_upload.called is upload_to_server


@patch("imap_data_access.webpoda.get_packet_binary_data_sctime")
@patch("imap_data_access.webpoda.get_packet_times_ert")
@patch("imap_data_access.webpoda.imap_data_access.upload")
@pytest.mark.parametrize("upload_to_server", [True, False])
def test_download_repointing_data(
    mock_upload,
    mock_get_packet_times_ert,
    mock_get_packet_binary_data_sctime,
    upload_to_server,
    tmpdir,
):
    # We are mocking the upload, lets also verify that
    # duplicate files don't propagate any errors.
    mock_upload.side_effect = IMAPDataAccessError("File already exists")
    mock_get_packet_binary_data_sctime.return_value = b"\x00\x01\x02\x03"
    # Create a fake repointing file
    # We only use repoint_end_time_utc and repoint_id
    repointing_file = tmpdir / "imap_2025_001_00.repoint.csv"
    with open(repointing_file, "w") as f:
        f.write(
            "repoint_start_sec_sclk,repoint_start_subsec_sclk,"
            "repoint_end_sec_sclk,repoint_end_subsec_sclk,"
            "repoint_start_utc,repoint_end_utc,"
            "repoint_id\n"
            # One packet per pointing period
            "0,0,1,0,2024-11-30 00:00:00.000,2024-11-30 20:15:00.000,1\n"
            "0,0,1,0,2024-12-01 00:00:00.000,2024-12-01 00:15:00.000,2\n"
            "10,0,11,0,2024-12-02 00:00:00.000,2024-12-02 00:15:00.000,3\n"
            # An unfinished repointing maneuver may have NaNs in the end times
            # Make sure we can handle this and ignore it
            "10,0,NaN,NaN,2024-12-03T00:00:00.000000,NaN,4\n"
        )

    start_time = datetime.datetime(2024, 12, 1, 0, 0, 0)
    end_time = datetime.datetime(2024, 12, 3, 23, 59, 59)
    instrument = "hi"

    # Test that no packets returned doesn't fail and doesn't produce any files
    mock_get_packet_times_ert.return_value = []
    download_repointing_data(
        instrument,
        start_time,
        end_time,
        repointing_file=repointing_file,
        upload_to_server=upload_to_server,
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
        repointing_file=repointing_file,
        upload_to_server=upload_to_server,
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
            version="v001",
        ).construct_path()
        # There are two hi apids, so we download the same byte stream twice
        n_apids = len(INSTRUMENT_APIDS[instrument])
        assert expected_file_path.read_bytes() == b"\x00\x01\x02\x03" * n_apids
        assert mock_upload.called is upload_to_server
    assert (imap_data_access.config["DATA_DIR"] / "imap").exists()
