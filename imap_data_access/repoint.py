"""Look up repointing maneuvers, and the pointings between them.

The SDC's repoint files are cumulative CSV tables: each one lists every
repointing maneuver since launch. A pointing is the time between two
maneuvers, and file names refer to it by the number of the maneuver that
starts it, as in ``repoint00123``. This module reads the newest repoint file
from the SDC and works out each pointing's start and end the same way the
SDC's pointing table does.
"""

import csv
import datetime
import io
import logging
from typing import NamedTuple

import requests

from imap_data_access.io import _get_base_url, _make_request

logger = logging.getLogger(__name__)

# The time formats the SDC's pointing table accepts in repoint files.
_TIME_FORMATS = ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f")


class Repoint(NamedTuple):
    """A repointing maneuver, and the pointing that follows it.

    All times are in UTC. A time is None if the repoint file doesn't give it.

    Attributes
    ----------
    repoint_id : int
        The maneuver's number. File names use it for the pointing that
        follows, as in ``repoint00123``.
    repoint_start : datetime.datetime or None
        When the maneuver starts.
    repoint_end : datetime.datetime or None
        When the maneuver ends.
    pointing_start : datetime.datetime or None
        When the pointing starts, which is when this maneuver ends.
    pointing_end : datetime.datetime or None
        When the pointing ends, which is when the next maneuver ends. None if
        there's no next maneuver yet, while the pointing is still going on.
    """

    repoint_id: int
    repoint_start: datetime.datetime | None
    repoint_end: datetime.datetime | None
    pointing_start: datetime.datetime | None
    pointing_end: datetime.datetime | None


# The newest repoint file read so far, and the table parsed from it.
_cache: dict = {"file_path": None, "repoints": {}}


def repoint_query(repoint_id: int) -> Repoint | None:
    """Return a repointing maneuver, and the pointing that follows it.

    The times come from the newest repoint file at the SDC, which is read once
    and then reused. If it doesn't have this maneuver, or the pointing after it
    hasn't ended, the SDC is checked again for a newer repoint file.

    Parameters
    ----------
    repoint_id : int
        The maneuver's number, which is also the number in the names of the
        files from the pointing that follows it.

    Returns
    -------
    Repoint or None
        The maneuver and the pointing after it, or None if the SDC's repoint
        files don't have it yet.

    Raises
    ------
    IMAPDataAccessError
        If the SDC can't be reached, or rejects a request.
    """
    repoint = _repoints().get(repoint_id)
    if repoint is None or repoint.pointing_end is None:
        repoint = _repoints(refresh=True).get(repoint_id)
    return repoint


def _repoints(refresh: bool = False) -> dict[int, Repoint]:
    """Return the repoint table, reading a newer repoint file if asked to."""
    if _cache["file_path"] is not None and not refresh:
        return _cache["repoints"]
    file_path = _latest_repoint_file()
    if file_path is not None and file_path != _cache["file_path"]:
        _cache["repoints"] = _parse_repoints(_read_file(file_path))
        _cache["file_path"] = file_path
    return _cache["repoints"]


def _clear_cache() -> None:
    """Forget the repoint table, so that the next lookup reads it again."""
    _cache["file_path"] = None
    _cache["repoints"] = {}


def _latest_repoint_file() -> str | None:
    """Return the path of the SDC's newest repoint file, or None if it has none."""
    url = f"{_get_base_url()}/repoint-table"
    request = requests.Request(method="GET", url=url).prepare()
    with _make_request(request) as response:
        repoint_files = response.json()
    if not repoint_files:
        logger.info("The SDC has no repoint files")
        return None
    # Each file holds every maneuver up to its end date, so the newest is the
    # one with the latest end date, then the highest version.
    newest = max(
        repoint_files,
        key=lambda item: (item["end_date"], item["version"], item["ingestion_date"]),
    )
    return newest["file_path"]


def _read_file(file_path: str) -> str:
    """Return the text of a file at the SDC, without saving it to disk."""
    url = f"{_get_base_url()}/download/{file_path}"
    logger.info("Reading repoint file %s", file_path)
    request = requests.Request(method="GET", url=url).prepare()
    with _make_request(request) as response:
        return response.content.decode()


def _parse_time(value: str | None) -> datetime.datetime | None:
    """Return a repoint file time in UTC, or None if it's missing or invalid."""
    if value is None or value.strip().lower() in ("", "nan", "none"):
        return None
    for time_format in _TIME_FORMATS:
        try:
            time = datetime.datetime.strptime(value.strip(), time_format)
        except ValueError:
            continue
        return time.replace(tzinfo=datetime.timezone.utc)
    return None


def _parse_repoints(text: str) -> dict[int, Repoint]:
    """Return the maneuvers and pointings in a repoint file, by repoint ID.

    Each pointing runs from the end of its maneuver to the end of the next
    maneuver in the file, as in the SDC's pointing table.
    """
    rows = [
        row
        for row in csv.DictReader(io.StringIO(text))
        if any(row.values()) and (row.get("repoint_id") or "").strip()
    ]
    repoints = {}
    for i, row in enumerate(rows):
        next_row = rows[i + 1] if i + 1 < len(rows) else None
        repoint_end = _parse_time(row["repoint_end_utc"])
        repoints[int(row["repoint_id"])] = Repoint(
            repoint_id=int(row["repoint_id"]),
            repoint_start=_parse_time(row["repoint_start_utc"]),
            repoint_end=repoint_end,
            pointing_start=repoint_end,
            pointing_end=(
                _parse_time(next_row["repoint_end_utc"]) if next_row else None
            ),
        )
    return repoints
