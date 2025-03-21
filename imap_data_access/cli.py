#!/usr/bin/env python3

"""Command line interface to the IMAP Data Access API.

This module serves as a command line utility to invoke the IMAP Data Access API.
It provides the ability to interact with the Science Data Center (SDC)
by querying, downloading, and uploading files to the data center.

Use
---
    imap-data-access <command> [<args>]
    imap-data-access --help
    imap-data-access download <file_path>
    imap-data-access query <query-parameters>
    imap-data-access upload <file_path>
"""

import argparse
import datetime
import logging
import os
from pathlib import Path

import imap_data_access
from imap_data_access.file_validation import ScienceFilePath
from imap_data_access.webpoda import download_daily_data


def _download_parser(args: argparse.Namespace):
    """Download a file from the IMAP SDC.

    Parameters
    ----------
    args : argparse.Namespace
        An object containing the parsed arguments and their values
    """
    output_path = imap_data_access.download(args.file_path)
    print(f"Successfully downloaded the file to: {output_path}")


def _print_query_results_table(query_results: list[dict]):
    """Print the query results in a table.

    Parameters
    ----------
    query_results : list
        A list of dictionaries containing the query results
    """
    num_files = len(query_results)
    print(f"Found [{num_files}] matching files")
    if num_files == 0:
        return

    # Use the keys of the first item in query_results for the header
    headers = [
        "Instrument",
        "Data Level",
        "Descriptor",
        "Start Date",
        "Repointing",
        "Version",
        "Filename",
    ]

    # Calculate the maximum width for each column based on the header and the data
    column_widths = {}
    for header in headers[:-1]:
        column_widths[header] = max(
            len(header),
            *(len(str(item.get(header.lower(), ""))) for item in query_results),
        )
        # Calculate the maximum width for each column based on the header and the data

        column_widths["Filename"] = max(
            len("Filename"),
            *(
                len(os.path.basename(item.get("file_path", "")))
                for item in query_results
            ),
        )

    # Create the format string dynamically based on the number of columns
    format_string = (
        "| "
        + " | ".join([f"{{:<{column_widths[header]}}}" for header in headers])
        + " |"
    )

    # Add hyphens for a separator between header and data
    hyphens = "|" + "-" * (sum(column_widths.values()) + 3 * len(headers) - 1) + "|"
    print(hyphens)

    # Print header
    print(format_string.format(*headers))
    print(hyphens)

    # Print data
    for item in query_results:
        values = [
            str(item.get("instrument", "")),
            str(item.get("data_level", "")),
            str(item.get("descriptor", "")),
            str(item.get("start_date", "")),
            str(item.get("repointing", "")) or "",
            str(item.get("version", "")),
            os.path.basename(item.get("file_path", "")),
        ]
        print(format_string.format(*values))

    # Close the table
    print(hyphens)


def _query_parser(args: argparse.Namespace):
    """Query the IMAP SDC.

    Parameters
    ----------
    args : argparse.Namespace
        An object containing the parsed arguments and their values
    """
    # Filter to get the arguments of interest from the namespace
    valid_args = [
        "instrument",
        "data_level",
        "descriptor",
        "start_date",
        "end_date",
        "repointing",
        "version",
        "extension",
        "filename",
    ]

    query_params = {
        key: value
        for key, value in vars(args).items()
        if key in valid_args and value is not None
    }

    # Checking to see if a filename was passed.
    if args.filename is not None:
        del query_params["filename"]
        if query_params:
            raise TypeError("Too many arguments, '--filename' should be ran by itself")

        file_path = ScienceFilePath(args.filename)
        query_params = {
            "instrument": file_path.instrument,
            "data_level": file_path.data_level,
            "descriptor": file_path.descriptor,
            "start_date": file_path.start_date,
            "repointing": file_path.repointing,
            "version": file_path.version,
            "extension": file_path.extension,
        }

    query_results = imap_data_access.query(**query_params)

    if args.output_format == "table":
        _print_query_results_table(query_results)
    elif args.output_format == "json":
        # Dump the content directly
        print(query_results)


def _upload_parser(args: argparse.Namespace):
    """Upload a file to the IMAP SDC.

    Parameters
    ----------
    args : argparse.Namespace
        An object containing the parsed arguments and their values
    """
    imap_data_access.upload(args.file_path)
    print("Successfully uploaded the file to the IMAP SDC")


def _webpoda_parser(args: argparse.Namespace):
    """Download raw packet data from IMAP.

    Parameters
    ----------
    args : argparse.Namespace
        An object containing the parsed arguments and their values
    """
    if args.end_date:
        end_time = args.end_date
    else:
        end_time = args.start_date
    # Now push that out to 23:59:59
    end_time = datetime.datetime.combine(end_time, datetime.time.max)

    download_daily_data(
        instrument=args.instrument,
        start_time=args.start_date,
        end_time=end_time,
    )
    print("Successfully downloaded the data from webpoda.")


# PLR0915: too many statements
def main():  # noqa: PLR0915
    """Parse the command line arguments.

    Run the command line interface to the IMAP Data Access API.
    """
    api_key_help = (
        "API key to authenticate with the IMAP SDC. "
        "This can also be set using the IMAP_API_KEY environment variable. "
        "It is only necessary for uploading files."
    )
    webpoda_token_help = (
        "Used to authenticate with the IMAP Project. "  # noqa: S105
        "This can also be set using the IMAP_WEBPODA_TOKEN environment variable. "
        "It is only necessary for downloading binary packet data."
    )
    data_dir_help = (
        "Directory to use for reading and writing IMAP data. "
        "The default is a 'data/' folder in the "
        "current working directory. This can also be "
        "set using the IMAP_DATA_DIR environment variable."
    )
    description = (
        "This command line program accesses the IMAP SDC APIs to query, download, "
        "and upload data files."
    )
    download_help = (
        "Download a file from the IMAP SDC to the locally configured data directory. "
        "Run 'download -h' for more information. "
    )
    help_menu_for_download = (
        "Download a file from the IMAP SDC to the locally configured data directory. "
    )
    file_path_help = (
        "This must be the full path to the file."
        "\nE.g. imap/mag/l0/2025/01/imap_mag_l0_raw_20250101_v001.pkts"
    )
    query_help = (
        "Query the IMAP SDC for files matching the query parameters. "
        "The query parameters are optional, but at least one must be provided. "
        "Run 'query -h' for more information."
    )
    help_menu_for_query = (
        "Query the IMAP SDC for files matching the query parameters. "
        "The query parameters are optional, but at least one must be provided. "
    )
    upload_help = (
        "Upload a file to the IMAP SDC. This must be the full path to the file."
        "\nE.g. imap/mag/l0/2025/01/imap_mag_l0_raw_20250101_v001.pkts. "
        "Run 'upload -h' for more information."
    )
    help_menu_for_upload = (
        "Upload a file to the IMAP SDC. This must be the full path to the file."
        "\nE.g. imap/mag/l0/2025/01/imap_mag_l0_raw_20250101_v001.pkts. "
    )
    url_help = (
        "URL of the IMAP SDC API. "
        "The default is https://api.dev.imap-mission.com. This can also be "
        "set using the IMAP_DATA_ACCESS_URL environment variable."
    )

    parser = argparse.ArgumentParser(prog="imap-data-access", description=description)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {imap_data_access.__version__}",
        help="Show programs version number and exit. No other parameters needed.",
    )
    parser.add_argument("--api-key", type=str, required=False, help=api_key_help)
    parser.add_argument(
        "--webpoda-token", type=str, required=False, help=webpoda_token_help
    )
    parser.add_argument("--data-dir", type=Path, required=False, help=data_dir_help)
    parser.add_argument("--url", type=str, required=False, help=url_help)
    # Logging level
    parser.add_argument(
        "--debug",
        help="Print lots of debugging statements.",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.WARNING,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Add verbose output",
        action="store_const",
        dest="loglevel",
        const=logging.INFO,
    )

    # Download command
    subparsers = parser.add_subparsers(required=True)
    parser_download = subparsers.add_parser(
        "download", help=download_help, description=help_menu_for_download
    )
    parser_download.add_argument("file_path", type=Path, help=file_path_help)
    parser_download.set_defaults(func=_download_parser)

    # Query command (with optional arguments)
    query_parser = subparsers.add_parser(
        "query", help=query_help, description=help_menu_for_query
    )
    query_parser.add_argument(
        "--instrument",
        type=str,
        required=False,
        help="Name of the instrument",
        choices=imap_data_access.VALID_INSTRUMENTS,
    )
    query_parser.add_argument(
        "--data-level",
        type=str,
        required=False,
        help="Data level of the product (l0, l1a, l2, etc.)",
    )
    query_parser.add_argument(
        "--descriptor",
        type=str,
        required=False,
        help="Descriptor of the product (raw, burst, etc.)",
    )
    query_parser.add_argument(
        "--start-date",
        type=str,
        required=False,
        help="Start date for files in YYYYMMDD format",
    )
    query_parser.add_argument(
        "--end-date",
        type=str,
        required=False,
        help="End date for a range of file timestamps in YYYYMMDD format",
    )
    query_parser.add_argument(
        "--repointing", type=int, required=False, help="Repointing number (int)"
    )
    query_parser.add_argument(
        "--version",
        type=str,
        required=False,
        help="Version of the product in the format 'v001'."
        " Must have one other parameter to run."
        " Passing 'latest' will return latest version of a file",
    )
    query_parser.add_argument(
        "--extension", type=str, required=False, help="File extension (cdf, pkts)"
    )
    query_parser.add_argument(
        "--output-format",
        type=str,
        required=False,
        help="How to format the output, default is 'table'",
        choices=["table", "json"],
        default="table",
    )
    query_parser.add_argument(
        "--filename",
        type=str,
        required=False,
        help="Name of a file to be searched for. For convention standards see https://imap-"
        "processing.readthedocs.io/en/latest/development-guide/style-guide/naming-conventions"
        ".html#data-product-file-naming-conventions",
    )
    query_parser.set_defaults(func=_query_parser)

    # Upload command
    parser_upload = subparsers.add_parser(
        "upload", help=upload_help, description=help_menu_for_upload
    )
    parser_upload.add_argument("file_path", type=Path, help=file_path_help)
    parser_upload.set_defaults(func=_upload_parser)

    # Webpoda command
    parser_webpoda = subparsers.add_parser(
        "webpoda", help="Raw packet data download per instrument"
    )
    parser_webpoda.add_argument(
        "--instrument",
        type=str,
        required=True,
        help="Name of the instrument",
        choices=imap_data_access.VALID_INSTRUMENTS,
    )
    parser_webpoda.add_argument(
        "--start-date",
        type=lambda d: datetime.datetime.strptime(d, "%Y%m%d"),
        required=True,
        help="Start date for the query in YYYYMMDD format. "
        "The query uses Earth Received Time (ERT).",
    )
    parser_webpoda.add_argument(
        "--end-date",
        type=lambda d: datetime.datetime.strptime(d, "%Y%m%d"),
        required=False,
        help="End date for the query in YYYYMMDD format. "
        "The query uses Earth Received Time (ERT). If not provided "
        "the query will be for the start date only.",
    )
    parser_webpoda.set_defaults(func=_webpoda_parser)

    # Parse the arguments and set the values
    try:
        args = parser.parse_args()
    except TypeError:
        parser.exit(
            status=1,
            message="Please provide input parameters, "
            "or use '-h' for more information.",
        )

    logging.basicConfig(level=args.loglevel)

    if args.data_dir:
        # We got an explicit data directory from the command line
        data_path = args.data_dir.resolve()
        if not data_path.exists():
            parser.error(f"Data directory {args.data_dir} does not exist")
        # Set the data directory to the user-supplied value
        imap_data_access.config["DATA_DIR"] = data_path

    if args.url:
        # We got an explicit url from the command line
        imap_data_access.config["DATA_ACCESS_URL"] = args.url

    if args.api_key:
        # We got an explicit api key from the command line
        imap_data_access.config["API_KEY"] = args.api_key

    if args.webpoda_token:
        # We got an explicit webpoda token from the command line
        imap_data_access.config["WEBPODA_TOKEN"] = args.webpoda_token

    # Now process through the respective function for the invoked command
    # (set with set_defaults on the subparsers above)
    try:
        args.func(args)
    except Exception as e:
        # Make sure we are exiting with non-zero exit code and printing the message
        parser.exit(status=1, message=str(e) + "\n")


if __name__ == "__main__":
    main()
