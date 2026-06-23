"""Input/output capabilities for the IMAP data processing pipeline."""

import contextlib
import logging
import os
from pathlib import Path
from time import sleep
from typing import Optional, Union

import requests

import imap_data_access
from imap_data_access import file_validation
from imap_data_access.file_validation import (
    AncillaryFilePath,
    ScienceFilePath,
    generate_imap_file_path,
)
from imap_data_access.utils import ReleaseType

logger = logging.getLogger(__name__)


class IMAPDataAccessError(Exception):
    """Base class for exceptions in this module."""

    pass


_RETRY_ADAPTER = requests.adapters.HTTPAdapter(max_retries=3)


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
    elif imap_data_access.config["ACCESS_TOKEN"]:
        # Add the access token to the request headers if it exists
        # and API key does not exist
        request.headers["Authorization"] = (
            f"Bearer {imap_data_access.config['ACCESS_TOKEN']}"
        )
    try:
        with requests.Session() as session:
            session.mount("https://", _RETRY_ADAPTER)
            response = session.send(request)
            response.raise_for_status()
            yield response
    except requests.exceptions.HTTPError as e:
        # e.response.reason captures the error message from the API
        error_msg = f"{e.response.status_code} {e.response.reason}: {e.response.text}"
        raise IMAPDataAccessError(error_msg) from e
    except requests.exceptions.RequestException as e:
        # Handle cases where response may not exist (connection errors, timeouts, etc.)
        raise IMAPDataAccessError(str(e)) from e


def _get_base_url() -> str:
    """Get the base URL of the data access API.

    Adds in the /api-key and /authorized to direct the url
    to the proper authorized endpoints as needed.
    """
    url = imap_data_access.config["DATA_ACCESS_URL"]

    # Only add these if someone hasn't already added the /api-key themselves.
    if imap_data_access.config["API_KEY"] and not url.endswith("/api-key"):
        url = f"{url}/api-key"
    elif imap_data_access.config["ACCESS_TOKEN"] and not url.endswith("/authorized"):
        url = f"{url}/authorized"

    return url


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

    url = f"{_get_base_url()}/download/{file_path}"
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

    elif version is not None and not file_validation.ImapFilePath.is_valid_version(
        version
    ):
        raise ValueError("Not a valid version, use format 'vXXX'.")

    # Check the explicit major/minor version params (science only). Omit
    # major_version entirely to get the latest major version.
    major_version = kwargs.get("major_version")
    minor_version = kwargs.get("minor_version")
    if major_version is not None and not str(major_version).isdigit():
        raise ValueError("Not a valid major_version, use an integer.")
    if minor_version is not None and not str(minor_version).isdigit():
        raise ValueError("Not a valid minor_version, use an integer.")

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


def spice_query(
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    ingestion_start_date: Optional[str] = None,
    ingestion_end_date: Optional[str] = None,
    type: Optional[str] = None,
    version: Optional[str] = None,
) -> list[dict[str, str]]:
    """Query the SPICE data archive via the /spice-query endpoint.

    Parameters
    ----------
    start_date : str, optional
        Start date in YYYYMMDD format.
    end_date : str, optional
        End date in YYYYMMDD format.
    ingestion_start_date : str, optional
        Ingestion start date in YYYYMMDD format.
    ingestion_end_date : str, optional
        Ingestion end date in YYYYMMDD format.
    type : str, optional
        SPICE kernel type (e.g. ``ephemeris_predicted``).
    version : str, optional
        Version in the format ``vXXX`` or ``latest``.

    Returns
    -------
    list
        List of SPICE files matching the query
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
        query_params["latest"] = "true"

    if "type" not in query_params:
        raise ValueError(
            "The 'type' parameter is required for SPICE queries. "
            "Run 'query -h' for more information."
        )

    # Remap ingestion date params to /spice-query naming convention
    if "ingestion_start_date" in query_params:
        query_params["start_ingest_date"] = query_params.pop("ingestion_start_date")
    if "ingestion_end_date" in query_params:
        query_params["end_ingest_date"] = query_params.pop("ingestion_end_date")

    url = f"{_get_base_url()}/spice-query"
    request = requests.Request(method="GET", url=url, params=query_params).prepare()

    logger.info("Querying data archive for %s with url %s", query_params, request.url)
    with _make_request(request) as response:
        # Decode the JSON response as a list of items
        items = response.json()
        logger.debug("Received JSON: %s", items)

    return items


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
    major_version: Optional[Union[str, int]] = None,
    minor_version: Optional[Union[str, int]] = None,
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
        Science data version in the format ``vMMM.mmmm`` (full) or the
        deprecated minor-only ``vXXX``. ``latest`` returns the latest version
        of a file per dataset. For science files this is a convenience that maps
        to ``minor_version`` (and ``major_version`` for the full form);
        prefer ``major_version`` / ``minor_version`` for new code.
    major_version : str or int, optional
        Science major version to filter on. When omitted, science queries
        default to the latest major version (with all of its minor versions).
    minor_version : str or int, optional
        Science minor version to filter on.
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

    # the science table is resolved server-side via a
    # `latest=true` flag (mirrors spice_query); other tables are still filtered
    # client-side after the query.
    # Server-side filtering reduces the server errors seen by users when queries return
    # too much data.
    request_latest = version == "latest"
    science_latest = request_latest and table == "science"
    if request_latest:
        del query_params["version"]

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

    # Let the server resolve 'latest' for science instead of filtering here.
    if science_latest:
        query_params["latest"] = "true"

    url = f"{_get_base_url()}/query"
    request = requests.Request(method="GET", url=url, params=query_params).prepare()

    logger.info("Querying data archive for %s with url %s", query_params, request.url)
    with _make_request(request) as response:
        # Decode the JSON response as a list of items
        items = response.json()
        logger.debug("Received JSON: %s", items)

    # Non-science tables still resolve 'latest' client-side
    if request_latest and not science_latest and items:

        def get_key(file_entry):
            return (
                file_entry["instrument"],
                file_entry["descriptor"],
                file_entry.get("data_level"),
                file_entry["start_date"],
                file_entry.get("repointing"),
            )

        latest_files = {}
        for item in items:
            key = get_key(item)
            version_sort_var = "minor_version" if "minor_version" in item else "version"
            if (key not in latest_files) or (
                item[version_sort_var] > latest_files[key][version_sort_var]
            ):
                latest_files[key] = item
        items = list(latest_files.values())

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
    url = f"{_get_base_url()}/reprocess"
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
    url = f"{_get_base_url()}/upload/{file_path.name}"
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


def release(
    *,
    instrument: Optional[str] = None,
    release_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    release_number: Optional[int] = None,
    exclude_file: Optional[Union[Path, str]] = None,
    manifest_file: Optional[Union[Path, str]] = None,
) -> None:
    """Submit a release file to the data archive API.

    Parameters
    ----------
    instrument : str, optional
        Instrument name (e.g., ``mag``, ``swe``)
    release_type : str, optional
        Type of release:
        - 'release': IMAP mission-wide public release. By default, all files
          are released unless specified in the exception list to be withheld.
        - 'early-release': Early release of selected files approved by both
          instrument and project.
        - 'unrelease': Unrelease previously released files due to various
          causes and reasons.
    start_date : str, optional
        Start date in YYYYMMDD format
    end_date : str, optional
        End date in YYYYMMDD format
    release_number : int, optional
        Release number. Defaults to ``None``. Required if release_type is
        'release' or 'reprocess' and should be an integer value.
    exclude_file : str, optional
        Path to exclude file containing list of files to exclude from public release.
    manifest_file : str, optional
        Path to manifest file containing list of files to apply action to in
        'early-release' or 'unrelease' types.

    Raises
    ------
    ValueError
        If API key is not configured or if any of the required parameters are invalid
    IMAPDataAccessError
        If the API request fails
    """
    # Check for API key - required for release operations
    if not imap_data_access.config["API_KEY"]:
        raise ValueError(
            "API key is required for release operations. "
            "Set the IMAP_API_KEY environment variable or use --api-key argument."
        )

    # Validate release_type
    valid_release_types = [e.value for e in ReleaseType]
    if release_type not in valid_release_types:
        raise ValueError(
            f"Not a valid release type, please choose from {valid_release_types}"
        )

    if release_type == ReleaseType.RELEASE.value:
        # Validate required inputs for 'release' type
        if instrument not in imap_data_access.VALID_INSTRUMENTS:
            raise ValueError(
                "Not a valid instrument, please choose from "
                + ", ".join(imap_data_access.VALID_INSTRUMENTS)
            )

        # Validate release_type == "release" requires release_number
        if release_type == ReleaseType.RELEASE.value and release_number is None:
            raise ValueError(
                "The 'release_number' parameter is required for 'release' release type."
            )

        # Validate start_date
        if not file_validation.ImapFilePath.is_valid_date(start_date):
            raise ValueError("Not a valid start date, use format 'YYYYMMDD'.")

        # Validate end_date
        if not file_validation.ImapFilePath.is_valid_date(end_date):
            raise ValueError("Not a valid end date, use format 'YYYYMMDD'.")

    if (
        release_type in [ReleaseType.EARLY_RELEASE.value, ReleaseType.UNRELEASE.value]
        and manifest_file is None
    ):
        raise ValueError(
            "The 'manifest_file' parameter is required for "
            f"'{release_type}' release type."
        )

    if release_type == ReleaseType.REPROCESS.value and release_number is None:
        raise ValueError(
            "The 'release_number' parameter is required for 'reprocess' release type."
        )
    # Handle exclude file upload if provided
    if exclude_file is not None:
        # Upload the exclude file using the standard upload function
        upload(exclude_file)
        # Sleep few seconds to ensure file is uploaded and indexed
        # before the release API tries to access it.
        sleep(10)
        logger.info("Exclude file uploaded successfully")

    # Handle manifest file upload if provided
    if manifest_file is not None:
        # Upload the manifest file using the standard upload function
        upload(manifest_file)
        # Sleep few seconds to ensure file is uploaded and indexed
        # before the release API tries to access it.
        sleep(10)
        logger.info("Manifest file uploaded successfully")

    # Build release parameters
    release_params = {
        "instrument": instrument,
        "release_type": release_type,
        "start_date": start_date,
        "end_date": end_date,
    }

    # Add release_number only if release_type is 'release' or 'reprocess'
    if release_type in {ReleaseType.RELEASE.value, ReleaseType.REPROCESS.value}:
        release_params["release_number"] = release_number

    # Add optional parameters if provided
    if exclude_file is not None:
        # API only needs the filename, not the full path
        release_params["exclude_file"] = os.path.basename(exclude_file)

    if manifest_file is not None:
        # API only needs the filename, not the full path
        release_params["manifest_file"] = os.path.basename(manifest_file)

    logger.debug("Input release parameters: %s", release_params)

    url = f"{_get_base_url()}/release"
    request = requests.Request(method="GET", url=url, params=release_params).prepare()

    logger.info("Submitting release request to %s with params %s", url, release_params)
    with _make_request(request) as response:
        result = response.json()
        logger.debug("Received JSON: %s", result)

    logger.info(
        f"Release request submitted successfully for {instrument} "
        f"from {start_date} to {end_date}."
    )
