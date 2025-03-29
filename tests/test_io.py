"""Tests for the ``io`` module."""

from __future__ import annotations

import json
import os
import re
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

import pytest

import imap_data_access
from imap_data_access.io import _get_url_response

test_science_filename = "imap_swe_l1_test-description_20100101_v000.cdf"
test_science_path = "imap/swe/l1/2010/01/" + test_science_filename


def _set_mock_data(mock_urlopen: unittest.mock.MagicMock, data: bytes):
    """Set the data returned by the mock urlopen.

    Parameters
    ----------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    data : bytes
        The mock data
    """
    mock_response = mock_urlopen.return_value.__enter__.return_value
    mock_response.read.return_value = data


@patch("urllib.request.urlopen")
def test_redirect_followed(mock_urlopen):
    """Verify that we follow a 307 redirect from newly created s3 buckets.

    Fairly involved mocking of urlopen, but we need to add two responses to
    the urlopen mock. The first response is a 307 redirect, which we need to
    follow to get the final response. The second response is our good return.
    Then verify that our second response was actually followed in the request
    arguments.
    """
    # Mocking the first response (307 Redirect)
    # Mock the first call to raise a 307 HTTPError
    mock_error_response = HTTPError(
        url="http://test-example.com",
        code=307,
        msg="Temporary Redirect",
        hdrs={"Location": "http://followed-redirect.com"},
        fp=None,
    )

    # Mocking the second response (200 OK)
    mock_success_response = MagicMock()
    mock_success_response.__enter__.return_value.getcode.return_value = 200

    # Using side_effect to alternate between 307 and 200 responses
    mock_urlopen.side_effect = [mock_error_response, mock_success_response]

    with _get_url_response(Request("http://test-example.com")) as response:
        assert mock_urlopen.call_count == 2
        assert response.getcode() == 200
        second_call_args = mock_urlopen.call_args_list[1]
        assert second_call_args[0][0].full_url == "http://followed-redirect.com"


def test_request_errors(mock_urlopen: unittest.mock.MagicMock):
    """Test that invalid URLs raise an appropriate HTTPError or URLError.

    Parameters
    ----------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    """
    # Set up the mock to raise an HTTPError
    mock_urlopen.side_effect = HTTPError(
        url="http://example.com", code=404, msg="Not Found", hdrs={}, fp=BytesIO()
    )
    with pytest.raises(imap_data_access.io.IMAPDataAccessError, match="HTTP Error"):
        imap_data_access.download(test_science_path)

    # Set up the mock to raise a URLError
    mock_urlopen.side_effect = URLError(reason="Not Found")
    with pytest.raises(imap_data_access.io.IMAPDataAccessError, match="URL Error"):
        imap_data_access.download(test_science_path)


@pytest.mark.parametrize(
    ("file_path", "destination"),
    [
        # Directory structure inferred
        (
            test_science_filename,
            test_science_path,
        ),
        # Directory structure provided in the request
        (test_science_path, test_science_path),
        # Pathlib.Path object
        (Path(test_science_path), test_science_path),
        # SPICE file
        ("imap_1000_100_1000_100_01.ap.bc", "spice/ck/imap_1000_100_1000_100_01.ap.bc"),
    ],
)
def test_download(
    mock_urlopen: unittest.mock.MagicMock, file_path: str | Path, destination: str
):
    """Test that the download API works as expected.

    Parameters
    ----------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    file_path : str or Path
        The path to the file to download
    destination : str
        The path to which the file is expected to be downloaded
    """
    # Call the download function
    result = imap_data_access.download(file_path)

    # Assert that the file was created
    assert result.exists()
    # Test that the file was saved in the correct location
    expected_destination = imap_data_access.config["DATA_DIR"] / destination
    assert result == expected_destination

    # Assert that the file content matches the mock data
    with open(result, "rb") as f:
        assert f.read() == b"Mock file content"

    # Should have only been one call to urlopen
    mock_urlopen.assert_called_once()

    # Assert that the correct URL was used for the download
    urlopen_calls = mock_urlopen.mock_calls
    # Check the arguments passed to urlopen
    # We pass a Request object, so need to get that with args[0]
    request_sent = urlopen_calls[0].args[0]
    called_url = request_sent.full_url
    # url should be provided as path parameters
    expected_url_encoded = f"https://api.test.com/download/{destination}"
    assert called_url == expected_url_encoded
    assert request_sent.method == "GET"


def test_download_already_exists(mock_urlopen: unittest.mock.MagicMock):
    """Test that downloading a file that already exists does result in any requests.

    Parameters
    ----------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    """
    # Call the download function
    # set up the destination and create a file
    destination = imap_data_access.config["DATA_DIR"] / test_science_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.touch(exist_ok=True)
    result = imap_data_access.download(test_science_path)
    assert result == destination
    # Make sure we didn't make any requests
    assert mock_urlopen.call_count == 0


@pytest.mark.parametrize(
    "query_params",
    [
        # All parameters should send full query
        {
            "instrument": "swe",
            "data_level": "l0",
            "descriptor": "test-description",
            "start_date": "20100101",
            "end_date": "20100102",
            "repointing": "repoint00001",
            "version": "v000",
            "extension": "pkts",
        },
        # Make sure not all query params are sent if they are missing
        {"instrument": "swe", "data_level": "l0"},
    ],
)
def test_query(mock_urlopen: unittest.mock.MagicMock, query_params: list[dict]):
    """Test a basic call to the Query API.

    Parameters
    ----------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    query_params : list of dict
        A list of key/value pairs that set the query parameters
    """
    _set_mock_data(mock_urlopen, json.dumps([]).encode("utf-8"))
    response = imap_data_access.query(**query_params)
    # No data found, and JSON decoding works as expected
    assert response == list()

    # Should have only been one call to urlopen
    mock_urlopen.assert_called_once()
    # Assert that the correct URL was used for the query
    urlopen_call = mock_urlopen.mock_calls[0].args[0]
    called_url = urlopen_call.full_url
    expected_url_encoded = f"https://api.test.com/query?{urlencode(query_params)}"
    assert called_url == expected_url_encoded


def test_query_no_params(mock_urlopen: unittest.mock.MagicMock):
    """Test a call to the Query API that has no parameters.

    Parameters
    ----------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    """
    with pytest.raises(ValueError, match="At least one query"):
        imap_data_access.query()
    # Should not have made any calls to urlopen
    assert mock_urlopen.call_count == 0


def test_query_bad_params(mock_urlopen: unittest.mock.MagicMock):
    """Test a call to the Query API that has invalid parameters.

    Parameters
    ----------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    """
    with pytest.raises(TypeError, match="got an unexpected"):
        imap_data_access.query(bad_param="test")
    # Should not have made any calls to urlopen
    assert mock_urlopen.call_count == 0


@pytest.mark.parametrize(
    ("query_flag", "query_input", "expected_output"),
    [
        # All parameters should  not send query
        (
            "instrument",
            "badInput",
            "Not a valid instrument, please choose from "
            + ", ".join(imap_data_access.VALID_INSTRUMENTS),
        ),
        (
            "data_level",
            "badInput",
            "Not a valid data level, choose from "
            + ", ".join(imap_data_access.VALID_DATALEVELS),
        ),
        ("start_date", "badInput", "Not a valid start date, use format 'YYYYMMDD'."),
        ("end_date", "badInput", "Not a valid end date, use format 'YYYYMMDD'."),
        (
            "repointing",
            "badInput",
            "Not a valid repointing, use format repoint<num>, "
            "where <num> is a 5 digit integer.",
        ),
        ("version", "badInput", "Not a valid version, use format 'vXXX'."),
        (
            "extension",
            "badInput",
            re.escape("Not a valid extension, choose from ('pkts', 'cdf')."),
        ),
    ],
)
def test_bad_query_input(query_flag, query_input, expected_output):
    """Test a function call to query with correct params but bad values.

     Ensures correct error message is returned.

    Parameters
    ----------
    query_flag : str
        correct query flag.
    query_input : str
        incorrect query input.
    expected_output : str
        Output error expected to be given.
    """
    kwargs = {query_flag: query_input}

    # Check if the ValueError is raised and contains the correct message
    with pytest.raises(ValueError, match=expected_output):
        imap_data_access.query(**kwargs)


def test_upload_no_file(mock_urlopen: unittest.mock.MagicMock):
    """Test a call to the upload API that has no filename supplied.

    Parameters
    ----------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    """
    path = Path("/non-existant/file.txt")
    assert not path.exists()
    with pytest.raises(FileNotFoundError):
        imap_data_access.upload(path)
    # Should not have made any calls to urlopen
    assert mock_urlopen.call_count == 0


@pytest.mark.parametrize(
    "upload_file_path", ["a/b/test-file.txt", Path("a/b/test-file.txt")]
)
@pytest.mark.parametrize(
    ("api_key", "expected_header"),
    [(None, {}), ("test-api-key", {"X-api-key": "test-api-key"})],
)
def test_upload(
    mock_urlopen: unittest.mock.MagicMock,
    upload_file_path: str | Path,
    api_key: str | None,
    expected_header: dict,
    monkeypatch,
):
    """Test a basic call to the upload API.

    Parameters
    ----------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    upload_file_path : str or Path
        The upload file path to test with
    api_key : str or None
        The API key to use for the upload
    expected_header : dict
        The expected header to be sent with the request
    """
    monkeypatch.setitem(imap_data_access.config, "API_KEY", None)
    _set_mock_data(mock_urlopen, b'"https://s3-test-bucket.com"')
    # Call the upload function
    file_to_upload = imap_data_access.config["DATA_DIR"] / upload_file_path
    file_to_upload.parent.mkdir(parents=True, exist_ok=True)
    with open(file_to_upload, "wb") as f:
        f.write(b"test file content")
    assert file_to_upload.exists()

    os.chdir(imap_data_access.config["DATA_DIR"])
    imap_data_access.upload(upload_file_path, api_key=api_key)

    # Should have been two calls to urlopen
    # 1. To get the s3 upload url
    # 2. To upload the file to the url returned in 1.
    assert mock_urlopen.call_count == 2

    # We get all returned calls, but we only need the calls
    # where we sent requests
    mock_calls = [
        call
        for call in mock_urlopen.mock_calls
        if len(call.args) and isinstance(call.args[0], Request)
    ]

    # First urlopen call should be to get the s3 upload url
    urlopen_call = mock_calls[0]
    request_sent = urlopen_call.args[0]
    called_url = request_sent.full_url
    expected_url_encoded = "https://api.test.com/upload/test-file.txt"
    assert called_url == expected_url_encoded
    assert request_sent.method == "GET"
    # An API key needs to be added to the header for uploads
    assert request_sent.headers == expected_header

    # Verify that we put that response into our second request
    urlopen_call = mock_calls[1]
    request_sent = urlopen_call.args[0]
    called_url = request_sent.full_url
    expected_url_encoded = "https://s3-test-bucket.com"
    assert called_url == expected_url_encoded
    assert request_sent.method == "PUT"

    # Assert that the original data from the test file was sent
    assert request_sent.data == b"test file content"
