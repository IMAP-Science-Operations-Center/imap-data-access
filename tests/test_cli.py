"""Tests for the CLI options."""

import json
import sys
from argparse import Namespace
from unittest import mock

import pytest

from imap_data_access import cli

from .test_io import (
    glows_l3e_hi_repoint1,
    glows_l3e_hi_repoint2_v1,
    glows_l3e_hi_repoint2_v2,
)


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


def test_cli_query_json(mock_send_request, capsys):
    """
    Test the CLI query subcommand's json output formatting

    Ensure the query subcommand with '--output-format json'
    produces valid, expected json
    """
    query_params = {
        "instrument": "glows",
        "data_level": "l3e",
        "version": "latest",
        "filename": None,
        "output_format": "json",
    }
    query_output_expected = [
        glows_l3e_hi_repoint1,
        glows_l3e_hi_repoint2_v1,
        glows_l3e_hi_repoint2_v2,
    ]
    json_output_expected = json.dumps(query_output_expected)

    mock_response = mock.MagicMock()
    mock_response.json.return_value = query_output_expected
    mock_send_request.return_value = mock_response

    args = Namespace(**query_params)
    cli._query_parser(args)
    captured = capsys.readouterr()
    assert captured.out.strip() == json_output_expected


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
