"""Global pytest configuration for the package."""

from unittest.mock import patch

import pytest

import imap_data_access


@pytest.fixture(autouse=True)
def _set_global_config(monkeypatch: pytest.fixture, tmp_path: pytest.fixture):
    """Set the global data directory to a temporary directory."""
    monkeypatch.setitem(imap_data_access.config, "DATA_DIR", tmp_path)
    monkeypatch.setitem(
        imap_data_access.config, "DATA_ACCESS_URL", "https://api.test.com"
    )
    # Make sure we don't leak any of this content if a user has set them locally
    monkeypatch.setitem(imap_data_access.config, "API_KEY", "test_key")
    monkeypatch.setitem(imap_data_access.config, "WEBPODA_TOKEN", "test_token")


@pytest.fixture
def mock_urlopen():
    """Mock urlopen to return a file-like object.

    Yields
    ------
    mock_urlopen : unittest.mock.MagicMock
        Mock object for ``urlopen``
    """
    mock_data = b"Mock file content"
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.read.return_value = mock_data
        yield mock_urlopen
