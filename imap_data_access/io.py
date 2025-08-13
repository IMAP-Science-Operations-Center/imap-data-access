"""Input/output capabilities for the IMAP data processing pipeline."""

import contextlib
import logging
from pathlib import Path
from typing import Optional, Union

import requests

import imap_data_access
from imap_data_access import file_validation
from imap_data_access.file_validation import (
    AncillaryFilePath,
    ScienceFilePath,
    generate_imap_file_path,
)

logger = logging.getLogger(__name__)


class IMAPDataAccessError(Exception):
    """Base class for exceptions in this module."""

    pass


@contextlib.contextmanager
def _make_request(request: requests.PreparedRequest):
    """Get the response from a URL request using the requests library.

    This is a helper function to handle different types of errors that can occur
    when making HTTP requests and yield the response body.
    """
    logger.debug("Making request: %s", request)
    if imap_data_access.config["API_KEY"]:
        # Add the API key to the request headers if it exists
        request.headers["x-api-key"] = imap_data_access.config["API_KEY"]

    try:
        with requests.Session() as session:
            response = session.send(request)
            response.raise_for_status()
            yield response
    except requests.exceptions.HTTPError as e:
        # e.response.reason captures the error message from the API
        error_msg = f"{e.response.status_code} {e.response.reason}: {e.response.text}"
        raise IMAPDataAccessError(error_msg) from e
    except requests.exceptions.RequestException as e:
        error_msg = f"{e.response.status_code} {e.response.reason}: {e.response.text}"
        raise IMAPDataAccessError(error_msg) from e


def download(file_path: Union[Path, str]) -> Path:
    """Download a file from the data archive.

    Parameters
    ----------
    file_path : pathlib.Path or str
        Name of the file to download, optionally including the directory path

    Returns
    -------
    pathlib.Path
        Path to the downloaded file
    """
    # Create the proper file path object based on the extension and filename
    file_path = Path(file_path)
    path_obj = generate_imap_file_path(file_path.name)

    destination = path_obj.construct_path()

    # Update the file_path with the full path for the download below
    file_path = destination.relative_to(imap_data_access.config["DATA_DIR"]).as_posix()

    # Only download if the file doesn't already exist
    # TODO: Do we want to verify any hashes to make sure we have the right file?
    if destination.exists():
        logger.info("The file %s already exists, skipping download", destination)
        return destination

    url = f"{imap_data_access.config['DATA_ACCESS_URL']}/download/{file_path}"
    logger.info("Downloading file %s from %s to %s", file_path, url, destination)

    # Create a request with the provided URL
    request = requests.Request("GET", url).prepare()
    # Open the URL and download the file
    with _make_request(request) as response:
        logger.debug("Received response: %s", response)
        # Save the file locally with the same filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)

    logger.info("File %s downloaded successfully", destination)
    return destination


# Too many branches (16 >12)
# ruff: noqa: PLR0912
def _validate_query_parameters(**kwargs) -> None:
    """Validate all parameters used in the query function.

    This methods keyword arguments will match that of the query() parameters.
    """
    table = kwargs.get("table")
    instrument = kwargs.get("instrument")
    data_level = kwargs.get("data_level")
    start_date = kwargs.get("start_date")
    end_date = kwargs.get("end_date")
    ingestion_start_date = kwargs.get("ingestion_start_date")
    ingestion_end_date = kwargs.get("ingestion_end_date")
    repointing = kwargs.get("repointing")
    version = kwargs.get("version")
    extension = kwargs.get("extension")

    # Check table name
    if table is not None and table not in imap_data_access.VALID_TABLES:
        raise ValueError(
            "Not a valid database table, please choose from "
            + ", ".join(imap_data_access.VALID_TABLES)
        )
    # Check instrument name
    if instrument is not None and instrument not in imap_data_access.VALID_INSTRUMENTS:
        raise ValueError(
            "Not a valid instrument, please choose from "
            + ", ".join(imap_data_access.VALID_INSTRUMENTS)
        )

    # Check data-level
    # do an if statement that checks that data_level was passed in,
    # then check it against all options, l0, l1a, l1b, l2, l3 etc.
    if data_level is not None and data_level not in imap_data_access.VALID_DATALEVELS:
        raise ValueError(
            "Not a valid data level, choose from "
            + ", ".join(imap_data_access.VALID_DATALEVELS)
        )

    # Check start-date
    if start_date is not None and not file_validation.ImapFilePath.is_valid_date(
        start_date
    ):
        raise ValueError("Not a valid start date, use format 'YYYYMMDD'.")

    # Check end-date
    if end_date is not None and not file_validation.ImapFilePath.is_valid_date(
        end_date
    ):
        raise ValueError("Not a valid end date, use format 'YYYYMMDD'.")

    # Check ingestion-start-date
    if (
        ingestion_start_date is not None
        and not file_validation.ImapFilePath.is_valid_date(ingestion_start_date)
    ):
        raise ValueError("Not a valid ingestion start date, use format 'YYYYMMDD'.")

    # Check ingestion-end-date
    if (
        ingestion_end_date is not None
        and not file_validation.ImapFilePath.is_valid_date(ingestion_end_date)
    ):
        raise ValueError("Not a valid ingestion end date, use format 'YYYYMMDD'.")

    if repointing is not None:
        # check repointing follows 'repoint00000' format
        if not file_validation.ScienceFilePath.is_valid_repointing(repointing):
            try:
                int(repointing)
            except ValueError as err:
                raise ValueError(
                    "Not a valid repointing, use format repoint<num>,"
                    " where <num> is a 5 digit integer."
                ) from err

    # Check version make sure to include 'latest'
    if version is not None and not file_validation.ImapFilePath.is_valid_version(
        version
    ):
        raise ValueError("Not a valid version, use format 'vXXX'.")

    # check extension
    if extension is not None:
        if table == "science":
            valid_extensions = ScienceFilePath.VALID_EXTENSIONS
        elif table == "ancillary":
            valid_extensions = AncillaryFilePath.VALID_EXTENSIONS
        else:
            raise ValueError("Not a valid table.")

        if extension not in valid_extensions:
            raise ValueError(
                f"Not a valid extension for '{table}', choose from {valid_extensions}."
            )


def query(
    *,
    table: Optional[str] = "science",
    instrument: Optional[str] = None,
    data_level: Optional[str] = None,
    descriptor: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ingestion_start_date: Optional[str] = None,
    ingestion_end_date: Optional[str] = None,
    repointing: Optional[Union[str, int]] = None,
    version: Optional[str] = None,
    extension: Optional[str] = None,
) -> list[dict[str, str]]:
    """Query the data archive for files matching the parameters.

    Before running the query it will be checked if a version 'latest' command
    was passed and that at least one other parameter was passed. After the
    query is run, if a 'latest' was passed then the query results will be
    filtered before being returned.

    Parameters
    ----------
    table : str, optional
        The desired table for the query to be performed against.
        Defaults to the science table.
    instrument : str, optional
        Instrument name (e.g. ``mag``)
    data_level : str, optional
        Data level (e.g. ``l1a``)
    descriptor : str, optional
        Descriptor of the data product / product name (e.g. ``burst``)
    start_date : str, optional
        Start date in YYYYMMDD format. Note this is to search for all files
        with start dates on or after this value.
    end_date : str, optional
        End date in YYYYMMDD format. Note this is to search for all files
        with start dates before the requested end_date.
    ingestion_start_date : str, optional
        Ingestion start date in YYYYMMDD format. Note this is to search
        for all files with ingestion start dates on or after this value.
    ingestion_end_date : str, optional
        Ingestion end date in YYYYMMDD format. Note this is to search
        for all files with ingestion start dates before the requested end_date.
    repointing : str, optional
        Repointing string, in the format 'repoint00000'.
    version : str, optional
        Data version in the format ``vXXX`` or 'latest'.
    extension : str, optional
        File extension (``cdf``, ``pkts``)

    Returns
    -------
    list
        List of files matching the query
    """
    # locals() gives us the keyword arguments passed to the function
    # and allows us to filter out the None values
    query_params = {key: value for key, value in locals().items() if value is not None}
    logger.debug("Input query parameters: %s", query_params)

    # removing version from query if it is 'latest',
    # ensuring other parameters are passed
    if version == "latest":
        del query_params["version"]
        if not query_params:
            raise ValueError("One other parameter must be run with 'version'")

    # Copy params and remove table to ensure one other param was passed
    non_table_params = query_params.copy()
    non_table_params.pop("table", None)
    if not non_table_params:
        raise ValueError(
            "At least one query parameter must be provided. "
            "Run 'query -h' for more information."
        )

    # Use validation function to check parameters
    _validate_query_parameters(**query_params)

    # Transform repointing from string to integer if provided
    if repointing is not None:
        if file_validation.ScienceFilePath.is_valid_repointing(repointing):
            query_params["repointing"] = int(repointing[-5:])
        else:
            query_params["repointing"] = int(repointing)

    url = f"{imap_data_access.config['DATA_ACCESS_URL']}/query"
    request = requests.Request(method="GET", url=url, params=query_params).prepare()

    logger.info("Querying data archive for %s with url %s", query_params, request.url)
    with _make_request(request) as response:
        # Decode the JSON response as a list of items
        items = response.json()
        logger.debug("Received JSON: %s", items)

    # if latest version was included in search then filter returned query for largest.
    if (version == "latest") and items:
        latest_per_day = {}
        for item in items:
            day = item["start_date"]
            version_num = int(item["version"][1:4])
            # filter by highest version per day
            if (day not in latest_per_day) or (
                version_num > latest_per_day[day]["_version_num"]
            ):
                # add extra field to identify version number
                latest_per_day[day] = {**item, "_version_num": version_num}
        # remove the extra field
        items = [
            {k: version for k, version in val.items() if k != "_version_num"}
            for val in latest_per_day.values()
        ]

    return items


def reprocess(
    *,
    start_date: str,
    end_date: str,
    instrument: Optional[str] = None,
    data_level: Optional[str] = None,
    descriptor: Optional[str] = None,
):
    """Trigger reprocessing of files in the IMAP data archive.

    Start date and end date are required for a reprocessing Event. If data_level is
    provided, instrument and descriptor are required. If descriptor is specified,
    instrument must be specified as well.

    Parameters
    ----------
    start_date : str
        Start date in YYYYMMDD format. Note this is the date to search for files to
        reprocess.
    end_date : str
        End date in YYYYMMDD format. Note this is the end date to search for files to
        reprocess.
    instrument : str, optional
        Instrument name (e.g. ``mag``)
    data_level : str, optional
        Data level (e.g. ``l1a``)
    descriptor : str, optional
        Descriptor of the data product / product name (e.g. ``burst``)
    """
    # locals() gives us the keyword arguments passed to the function
    # and allows us to filter out the None values
    reprocess_params = {
        key: value for key, value in locals().items() if value is not None
    }
    logger.debug("Input reprocessing parameters: %s", reprocess_params)

    # ensuring other parameters are passed
    if not end_date or not start_date:
        raise ValueError(
            "Start date and end date are required for a reprocessing Event."
        )
    if data_level:
        if not instrument or not descriptor:
            raise ValueError(
                "If data_level is provided, instrument and descriptor are required."
            )
    elif not instrument and descriptor:
        raise ValueError("If descriptor is provided, instrument must also be provided.")
    # Check instrument name
    if instrument is not None and instrument not in imap_data_access.VALID_INSTRUMENTS:
        raise ValueError(
            "Not a valid instrument, please choose from "
            + ", ".join(imap_data_access.VALID_INSTRUMENTS)
        )
    # Check data-level
    # Validate the data_level parameter to ensure it is one of the allowed options
    # (e.g., l0, l1a, l1b, l2, l3). Raise an error if the value is invalid.
    if data_level is not None and data_level not in imap_data_access.VALID_DATALEVELS:
        raise ValueError(
            "Not a valid data level, choose from "
            + ", ".join(imap_data_access.VALID_DATALEVELS)
        )
    # Check start-date
    if start_date is not None and not file_validation.ImapFilePath.is_valid_date(
        start_date
    ):
        raise ValueError("Not a valid start date, use format 'YYYYMMDD'.")

    # Check end-date
    if end_date is not None and not file_validation.ImapFilePath.is_valid_date(
        end_date
    ):
        raise ValueError("Not a valid end date, use format 'YYYYMMDD'.")
    reprocess_params["reprocessing"] = "True"
    url = f"{imap_data_access.config['DATA_ACCESS_URL']}/reprocess"
    request = requests.Request(
        method="POST", url=url, params=reprocess_params
    ).prepare()

    logger.info(
        "Triggering reprocessing for %s with url %s", reprocess_params, request.url
    )
    with _make_request(request) as response:
        # Decode the JSON response as a list of items
        items = response.json()
        logger.debug("Received JSON: %s", items)


def upload(file_path: Union[Path, str]) -> None:
    """Upload a file to the data archive.

    Parameters
    ----------
    file_path : pathlib.Path or str
        Path to the file to upload.
    """
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    # The upload name needs to be given as a path parameter
    url = f"{imap_data_access.config['DATA_ACCESS_URL']}/upload/{file_path.name}"
    logger.info("Uploading file %s to %s", file_path, url)

    # We send a GET request with the filename and the server
    # will respond with an s3 presigned URL that we can use
    # to upload the file to the data archive
    request = requests.Request("GET", url).prepare()

    with _make_request(request) as response:
        s3_url = response.json()
        logger.debug("Received s3 presigned URL: %s", s3_url)

    # Follow the presigned URL to upload the file with a PUT request
    upload_request = requests.Request(
        "PUT", s3_url, data=file_path.read_bytes(), headers={"Content-Type": ""}
    ).prepare()
    with _make_request(upload_request) as response:
        logger.debug(
            "Received status code [%s] with response: %s",
            response.status_code,
            response.text,
        )

    logger.info("File %s uploaded successfully", file_path)
