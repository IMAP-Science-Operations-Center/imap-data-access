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


@pytest.fixture(autouse=True)
def mock_send_request():
    """Mock session to return a requests-like object.

    Yields
    ------
    mock_send_request : unittest.mock.MagicMock
        Mock object for ``session.send()``
    """
    with patch("requests.Session") as mock_session:
        mock_session_instance = mock_session.return_value.__enter__.return_value
        mock_session_instance.send.return_value.content = b"Mock file content"
        yield mock_session_instance.send


@pytest.fixture
def mock_request():
    """Mock request to return a requests-like object.

    Yields
    ------
    mock_request : unittest.mock.MagicMock
        Mock object for ``urlopen``
    """
    with patch("requests.Request") as mock_request:
        yield mock_request
