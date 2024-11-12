"""Data Access for the IMAP Mission.

The Interstellar Mapping and Acceleration Probe (IMAP) is a NASA mission to study the
heliosphere. This package contains the data access tools for the IMAP mission. It
provides a convenient way to query the IMAP data archive and download data files.
"""

import os
from pathlib import Path

from imap_data_access.file_validation import ScienceFilePath, SPICEFilePath
from imap_data_access.io import download, query, upload

__all__ = [
    "query",
    "download",
    "upload",
    "ScienceFilePath",
    "SPICEFilePath",
    "VALID_INSTRUMENTS",
    "VALID_DATALEVELS",
    "VALID_FILE_EXTENSION",
    "FILENAME_CONVENTION",
]
__version__ = "0.11.0"


config = {
    "DATA_ACCESS_URL": os.getenv("IMAP_DATA_ACCESS_URL")
    or "https://api.dev.imap-mission.com",
    "DATA_DIR": Path(os.getenv("IMAP_DATA_DIR") or Path.cwd() / "data"),
    "API_KEY": os.getenv("IMAP_API_KEY"),
}
"""Settings configuration dictionary.

DATA_ACCESS_URL : This is the URL of the data access API.
DATA_DIR : This is where the file data is stored and organized by instrument and level.
    The default location is a 'data/' folder in the current working directory,
    "but this can be set on the command line using the --data-dir option, or through
    the environment variable IMAP_DATA_DIR.
API_KEY : This is the API key used to authenticate with the data access API.
    It can be set on the command line using the --api-key option, or through the
    environment variable IMAP_API_KEY. It is only necessary for uploading files.
"""


VALID_INSTRUMENTS = {
    "codice",
    "glows",
    "hit",
    "hi",
    "idex",
    "lo",
    "mag",
    "swapi",
    "swe",
    "ultra",
}

VALID_DATALEVELS = {
    "l0",
    "l1",
    "l1a",
    "l1b",
    "l1c",
    "l1ca",
    "l1cb",
    "l1d",
    "l2",
    "l2a",
    "l2b",
    "l3",
    "l3a",
    "l3b",
    "l3c",
    "l3d",
}

VALID_FILE_EXTENSION = {"pkts", "cdf"}

FILENAME_CONVENTION = (
    "<mission>_<instrument>_<datalevel>_<descriptor>_"
    "<startdate>(-<repointing>)_<version>.<extension>"
)
