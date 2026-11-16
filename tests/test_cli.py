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


def test_cli_spice_query_table_shows_filename_only(capsys):
    """SPICE table output should show only the filename, not its directory."""
    results = [
        {
            "kernel_type": "leapseconds",
            "min_date_datetime": "",
            "max_date_datetime": "",
            "ingestion_date": "2025-01-01 00:00:00",
            "version": 1,
            "file_name": "lsk/naif0012.tls",
        }
    ]
    with mock.patch.object(
        sys,
        "argv",
        ["imap-data-access", "query", "--table", "spice", "--type", "leapseconds"],
    ):
        with mock.patch("imap_data_access.cli.spice_query", return_value=results):
            cli.main()
    out = capsys.readouterr().out
    assert "| naif0012.tls |" in out
    assert "lsk/" not in out


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
        "download": False,
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


@pytest.mark.parametrize(
    ("filename", "query_func", "expected_kwargs", "results"),
    [
        (
            "imap_swapi_l1_sci_20260808_v001.0003.cdf",
            "query",
            {
                "table": "science",
                "instrument": "swapi",
                "data_level": "l1",
                "descriptor": "sci",
                "start_date": "20260808",
                "end_date": "20260808",
                "repointing": None,
                "major_version": 1,
                "minor_version": 3,
                "extension": "cdf",
            },
            [{"file_path": "imap/swapi/l1/imap_swapi_l1_sci_20260808_v001.0003.cdf"}],
        ),
        (
            "imap_swapi_proton-density-temperature-lut_20240905_v002.dat",
            "query",
            {
                "table": "ancillary",
                "instrument": "swapi",
                "descriptor": "proton-density-temperature-lut",
                "start_date": "20240905",
                "end_date": "20240905",
                "repointing": None,
                "version": "v002",
                "extension": "dat",
            },
            [
                {
                    "file_path": "imap/ancillary/swapi/"
                    "imap_swapi_proton-density-temperature-lut_20240905_v002.dat"
                }
            ],
        ),
        (
            "imap_130.tf",
            "spice_query",
            {"type": "imap_frames"},
            [{"file_name": "fk/imap_130.tf"}, {"file_name": "fk/imap_129.tf"}],
        ),
    ],
)
def test_cli_query_filename(filename, query_func, expected_kwargs, results, capsys):
    """Test that the query subcommand works with a FILENAME."""
    args = Namespace(filename=filename, output_format="json", download=False)
    with mock.patch(
        f"imap_data_access.cli.{query_func}", return_value=results
    ) as mock_query:
        cli._query_parser(args)
    mock_query.assert_called_once_with(**expected_kwargs)
    assert json.loads(capsys.readouterr().out) == results[:1]


@pytest.mark.parametrize(
    ("filename", "query_func", "results", "expected_path"),
    [
        (
            "imap_swapi_l1_sci_20260808_v001.0003.cdf",
            "query",
            [{"file_path": "imap/swapi/l1/imap_swapi_l1_sci_20260808_v001.0003.cdf"}],
            "imap/swapi/l1/imap_swapi_l1_sci_20260808_v001.0003.cdf",
        ),
        (
            "imap_130.tf",
            "spice_query",
            [{"file_name": "fk/imap_130.tf"}, {"file_name": "fk/imap_129.tf"}],
            "fk/imap_130.tf",
        ),
    ],
)
def test_cli_query_download(filename, query_func, results, expected_path):
    """Test that --download downloads each matching query result."""
    args = Namespace(filename=filename, output_format="table", download=True)
    with (
        mock.patch(f"imap_data_access.cli.{query_func}", return_value=results),
        mock.patch("imap_data_access.download") as mock_download,
    ):
        cli._query_parser(args)
    mock_download.assert_called_once_with(expected_path)


def test_cli_spice_query_download(capsys):
    """Test that 'query --table spice --download' downloads every result."""
    results = [{"file_name": "lsk/naif0012.tls"}, {"file_name": "fk/imap_130.tf"}]
    with (
        mock.patch.object(
            sys,
            "argv",
            ["imap-data-access", "query", "--table", "spice", "--download"],
        ),
        mock.patch("imap_data_access.cli.spice_query", return_value=results),
        mock.patch(
            "imap_data_access.download", side_effect=lambda path: f"/data/{path}"
        ) as mock_download,
    ):
        cli.main()
    assert mock_download.call_args_list == [
        mock.call("lsk/naif0012.tls"),
        mock.call("fk/imap_130.tf"),
    ]
    captured = capsys.readouterr()
    assert "Found [2] matching files" in captured.out
    assert "Successfully downloaded" not in captured.out
    assert "Successfully downloaded the file to: /data/lsk/naif0012.tls" in captured.err
    assert "Successfully downloaded the file to: /data/fk/imap_130.tf" in captured.err


def test_cli_query_download_json_output(capsys):
    """Test that --download keeps stdout valid JSON with '--output-format json'."""
    results = [{"file_name": "lsk/naif0012.tls"}]
    with (
        mock.patch.object(
            sys,
            "argv",
            [
                "imap-data-access",
                "query",
                "--table",
                "spice",
                "--output-format",
                "json",
                "--download",
            ],
        ),
        mock.patch("imap_data_access.cli.spice_query", return_value=results),
        mock.patch("imap_data_access.download", return_value="/data/naif0012.tls"),
    ):
        cli.main()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == results
    assert "Successfully downloaded the file to: /data/naif0012.tls" in captured.err


def test_cli_query_filename_download():
    """Test that FILENAME can be combined with --download."""
    results = [{"file_name": "fk/imap_130.tf"}, {"file_name": "fk/imap_129.tf"}]
    with (
        mock.patch.object(
            sys, "argv", ["imap-data-access", "query", "imap_130.tf", "--download"]
        ),
        mock.patch("imap_data_access.cli.spice_query", return_value=results),
        mock.patch("imap_data_access.download") as mock_download,
    ):
        cli.main()
    mock_download.assert_called_once_with("fk/imap_130.tf")


def test_cli_query_download_no_results():
    """Test that --download does nothing when the query has no results."""
    args = Namespace(table="spice", filename=None, output_format="json", download=True)
    with (
        mock.patch("imap_data_access.cli.spice_query", return_value=[]),
        mock.patch("imap_data_access.download") as mock_download,
    ):
        cli._query_parser(args)
    mock_download.assert_not_called()


@pytest.mark.parametrize(
    "query_args",
    [
        ["imap_130.tf", "--instrument", "swapi"],
        ["imap_130.tf", "--table", "spice"],
        ["imap_130.tf", "--version", "v001"],
        ["imap_130.tf", "--table", "science"],
        ["--table", "science", "imap_130.tf"],
    ],
)
def test_cli_query_filename_with_options(query_args, capsys):
    """Test that FILENAME cannot be combined with other query options."""
    with mock.patch.object(sys, "argv", ["imap-data-access", "query", *query_args]):
        with pytest.raises(SystemExit, match="2"):
            cli.main()
    assert "FILENAME cannot be combined" in capsys.readouterr().err


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


def test_cli_reprocess(capsys):
    """Test that the CLI reprocess command prints the reprocess ID."""
    args = Namespace(start_date="20260101", end_date="20260102")
    with mock.patch("imap_data_access.reprocess", return_value="test-id"):
        cli._reprocess_parser(args)
    captured = capsys.readouterr()
    assert "Reprocess ID: test-id" in captured.out
