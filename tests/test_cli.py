"""Tests for the CLI options."""

import sys
from unittest import mock

import pytest

from imap_data_access import cli


def test_cli_works():
    """Smoke test for the CLI module making sure it is callable."""
    with mock.patch.object(sys, "argv", ["imap-data-access", "-h"]):
        # Should have a 0 SystemExit return code if successful
        with pytest.raises(SystemExit, match="0"):
            cli.main()


def test_cli_spice_query(capsys):
    """Test the CLI SPICE query command."""
    with mock.patch.object(
        sys,
        "argv",
        [
            "imap-data-access",
            "query",
            "--table",
            "spice",
            "--type",
            "ephemeris_predicted",
        ],
    ):
        with mock.patch(
            "imap_data_access.cli.spice_query", return_value=[]
        ) as mock_spice_query:
            cli.main()
    captured = capsys.readouterr()
    assert "Found [0] matching files" in captured.out
    mock_spice_query.assert_called_once_with(type="ephemeris_predicted")


def test_cli_error_message(capsys):
    """Test the CLI error message when no arguments are passed."""
    with mock.patch.object(
        sys, "argv", ["imap-data-access", "upload", "/a/b/c/non-existant-file.pkts"]
    ):
        # Should have a 2 SystemExit return code if successful
        with pytest.raises(SystemExit, match="1"):
            cli.main()
    captured = capsys.readouterr()
    assert "FileNotFoundError" in captured.err


# ---------------------------------------------------------------------------
# release query CLI tests
# ---------------------------------------------------------------------------
RELEASE_VERSION_RECORD = {
    "release_number": 1,
    "updated_date": "2026-04-01T00:00:00",
}


def test_cli_release_query_table(capsys):
    """Test that `release query` prints a table of release versions."""
    with mock.patch.object(sys, "argv", ["imap-data-access", "release", "query"]):
        with mock.patch(
            "imap_data_access.cli.query_release_versions",
            return_value=[RELEASE_VERSION_RECORD],
        ) as mock_qrv:
            cli.main()

    captured = capsys.readouterr()
    assert "Found [1] global release records" in captured.out
    assert "Release Number" in captured.out
    assert "Updated Date" in captured.out
    mock_qrv.assert_called_once_with()


def test_cli_release_query_empty(capsys):
    """Test that `release query` handles an empty response gracefully."""
    with mock.patch.object(sys, "argv", ["imap-data-access", "release", "query"]):
        with mock.patch("imap_data_access.cli.query_release_versions", return_value=[]):
            cli.main()

    captured = capsys.readouterr()
    assert "Found [0] global release records" in captured.out


def test_cli_release_query_json(capsys):
    """Test that `release query --output-format json` prints raw JSON."""
    with mock.patch.object(
        sys,
        "argv",
        ["imap-data-access", "release", "query", "--output-format", "json"],
    ):
        with mock.patch(
            "imap_data_access.cli.query_release_versions",
            return_value=[RELEASE_VERSION_RECORD],
        ):
            cli.main()

    captured = capsys.readouterr()
    assert "release_number" in captured.out
