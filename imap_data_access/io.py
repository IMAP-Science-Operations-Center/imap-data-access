"""Input/output capabilities for the IMAP data processing pipeline."""
# ruff: noqa: PLR0913 S310
# too many arguments, but we want all of these explicitly listed
# potentially unsafe usage of urlopen, but we aren't concerned here
import contextlib
import json
import logging
import urllib.request
from pathlib import Path
from typing import Optional, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

import imap_data_access

logger = logging.getLogger(__name__)


class IMAPDataAccessError(Exception):
    """Base class for exceptions in this module."""

    pass


@contextlib.contextmanager
def _get_url_response(request: urllib.request.Request):
    """Get the response from a URL request.

    This is a helper function to make it easier to handle
    the different types of errors that can occur when
    opening a URL and write out the response body.
    """
    try:
        # Open the URL and yield the response
        with urllib.request.urlopen(request) as response:
            yield response

    except HTTPError as e:
        message = (
            f"HTTP Error: {e.code} - {e.reason}\n"
            f"Server Message: {e.read().decode('utf-8')}"
        )
        raise IMAPDataAccessError(message) from e
    except URLError as e:
        message = f"URL Error: {e.reason}"
        raise IMAPDataAccessError(message) from e


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
    destination = imap_data_access.config["DATA_DIR"]
    if isinstance(file_path, str) and "/" not in file_path:
        # Construct the directory structure from the filename
        # This is for science files that contain the directory structure in the filename
        # Otherwise, we assume the full path to the file was given

        science_file_path = imap_data_access.ScienceFilePath(file_path)

        destination = science_file_path.construct_path()
    else:
        destination /= file_path

    # Only download if the file doesn't already exist
    # TODO: Do we want to verify any hashes to make sure we have the right file?
    if destination.exists():
        logger.info("The file %s already exists, skipping download", destination)
        return destination

    # encode the query parameters
    url = f"{imap_data_access.config['DATA_ACCESS_URL']}"
    url += f"/download/{file_path}"
    logger.info("Downloading file %s from %s to %s", file_path, url, destination)

    # Create a request with the provided URL
    request = urllib.request.Request(url, method="GET")
    # Open the URL and download the file
    with _get_url_response(request) as response:
        logger.debug("Received response: %s", response)
        # Save the file locally with the same filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "wb") as local_file:
            local_file.write(response.read())

    return destination


def query(
    *,
    instrument: Optional[str] = None,
    data_level: Optional[str] = None,
    descriptor: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    version: Optional[str] = None,
    extension: Optional[str] = None,
):
    """Query the data archive for files matching the parameters.

    Parameters
    ----------
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
        with start dates before the enddate, not the enddate of the file.
        For example, if a file spans three months 20100101 to 20100330,
        and the enddate query was 20100201, the file would still be returned
        because the startdate is within the query range.
    version : str, optional
        Data version in the format ``vXX-YY``
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
    if not query_params:
        raise ValueError("At least one query parameter must be provided")
    url = f"{imap_data_access.config['DATA_ACCESS_URL']}"
    url += f"/query?{urlencode(query_params)}"

    logger.info("Querying data archive for %s with url %s", query_params, url)
    request = urllib.request.Request(url, method="GET")
    with _get_url_response(request) as response:
        # Retrieve the response as a list of files
        items = response.read().decode("utf-8")
        logger.debug("Received response: %s", items)
        # Decode the JSON string into a list
        items = json.loads(items)
        logger.debug("Decoded JSON: %s", items)
    return items


def upload(file_path: Union[Path, str]) -> None:
    """Upload a file to the data archive.

    Parameters
    ----------
    file_path : pathlib.Path or str
        Path to the file to upload. It must be located within
        the ``imap_data_access.config["DATA_DIR"]`` directory.
    """
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    if not file_path.is_relative_to(imap_data_access.config["DATA_DIR"]):
        raise ValueError(
            f"File {file_path} is not within the data directory: "
            f"{imap_data_access.config['DATA_DIR']}"
        )

    # Strip off the data directory to get the upload path + name
    # Must be posix style for the URL
    upload_name = str(
        file_path.relative_to(imap_data_access.config["DATA_DIR"]).as_posix()
    )

    url = f"{imap_data_access.config['DATA_ACCESS_URL']}"
    # The upload name needs to be given as a path parameter
    url += f"/upload/{upload_name}"
    logger.info("Uploading file %s to %s", file_path, url)

    # We send a GET request with the filename and the server
    # will respond with an s3 presigned URL that we can use
    # to upload the file to the data archive
    request = urllib.request.Request(url, method="GET")

    with _get_url_response(request) as response:
        # Retrieve the key for the upload
        s3_url = response.read().decode("utf-8")
        logger.debug("Received s3 presigned URL: %s", s3_url)
        s3_url = json.loads(s3_url)

    # Follow the presigned URL to upload the file with a PUT request
    with open(file_path, "rb") as local_file:
        request = urllib.request.Request(
            s3_url, data=local_file.read(), method="PUT", headers={"Content-Type": ""}
        )
        with _get_url_response(request) as response:
            logger.debug("Received response: %s", response.read().decode("utf-8"))
