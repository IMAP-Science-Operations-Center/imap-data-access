"""Download packet data from webpoda and compare it against production.

This module downloads instrument packet data from webpoda, either for whole
days (download_daily_data) or for individual repointings
(download_repointing_data). Each function supports querying either by Earth
Received Time (ERT, the default) -- which first looks up which dates/pointings
actually have packets before querying them -- or by Spacecraft Time (SCT),
which queries every date/pointing in the requested range directly.

For any instrument/date (and repointing, if applicable) that already has an
L0 file in production, the freshly downloaded data is compared against that
file via _compare_and_write_new_data (which uses compare_files), so only new
or changed data is kept and written as a new minor version.

Location of list of APIDs and associated instruments:
https://lasp.colorado.edu/galaxy/spaces/IMAP/pages/155648242/Packet+Decommutation+Resource+Page+-+IMAP
"""

import datetime
import hashlib
import logging
from pathlib import Path
from typing import Optional

import requests

import imap_data_access
from imap_data_access.io import IMAPDataAccessError, _make_request

logger = logging.getLogger(__name__)

WEBPODA_APID_URL = "https://lasp.colorado.edu/ops/imap/poda/dap2/apids"
# The system ID for the IMAP mission
# SID1 == FLIGHT instrument telemetry and spacecraft telemetry after launch
# SID2 == FLIGHT instrument telemetry and spacecraft telemetry before launch
# SID3 == Instrument simulator telemetry and spacecraft simulator telemetry
SYSTEM_ID = "SID1"

# https://lasp.colorado.edu/galaxy/spaces/IMAP/pages/155648242/Packet+Decommutation+Resource+Page+-+IMAP
INSTRUMENT_APIDS = {
    "codice": [
        1136,
        1152,
        1153,
        1155,
        1156,
        1157,
        1158,
        1159,
        1160,
        1161,
        1162,
        1168,
        1169,
        1170,
        1171,
        1172,
        1173,
        1174,
    ],
    "glows": [1480, 1481],
    "hi": [740, 754, 769, 770, 772, 804, 818, 833, 834, 836],
    "hit": [1251, 1252, 1253],
    "idex": [1418, 1419, 1424],
    "lo": [673, 676, 677, 705, 706, 707, 708],
    "mag": [1052, 1068],
    "swapi": [1184, 1188],
    "swe": [1330, 1334, 1344],
    "ultra": [
        865,
        866,
        867,
        868,
        869,
        870,
        871,
        872,
        873,
        874,
        875,
        876,
        877,
        880,
        881,
        882,
        883,
        884,
        885,
        886,
        887,
        888,
        889,
        896,
        897,
        898,
        899,
        900,
        901,
        929,
        930,
        931,
        932,
        933,
        934,
        935,
        936,
        937,
        938,
        939,
        940,
        941,
        944,
        945,
        946,
        947,
        948,
        949,
        950,
        951,
        952,
        953,
        960,
        961,
        962,
        963,
        964,
        965,
    ],
    "spacecraft": [594],
    "ialirt": [478],
}

_INSTRUMENT_BUFFER_MINUTES = {
    "hit": 20,
    "mag": 30,
    "swapi": 1,
    "swe": 1,
    "codice": 7,
}


def _get_webpoda_headers() -> dict:
    """Get the necessary headers for webpoda requests."""
    token = imap_data_access.config.get("WEBPODA_TOKEN", "")
    if not token:
        raise ValueError(
            "The IMAP_WEBPODA_TOKEN environment variable must be set. "
            "You can run the following command to get the token: "
            "echo -n 'username:password' | base64"
        )
    return {"Authorization": f"Basic {token}"}


def get_packet_times_ert(
    apid: int, start_time: datetime.datetime, end_time: datetime.datetime
) -> list[datetime.datetime]:
    """Get the packet dates for the apid between the start and end time.

    This function makes a query to the webpoda API to get the packet dates
    for the given APID between the start and end times in Earth Received Time (ERT).

    Notes
    -----
    If we want just the first or last, we can add the take(1) or takeRight(1) to the
    query string if needed. Without this, we'll get a list of all packets between
    the start and end time.

    Parameters
    ----------
    apid : int
        The APID to query for.
    start_time : datetime.datetime
        The start time of the query in Earth Received Time (ERT).
    end_time : datetime.datetime
        The end time of the query in Earth Received Time (ERT).

    Returns
    -------
    list[datetime.datetime]
        A list of packet times for the given APID between the start and end time.
    """
    logger.info(
        f"Getting packet times for apid [{apid}] between {start_time} and {end_time}"
    )

    # Add a .txt suffix to get the data in text format back
    query_range = f"{WEBPODA_APID_URL}/{SYSTEM_ID}/apid_{apid}.txt"
    # We need to properly encode the query string to make sure the special characters
    # are handled correctly, so pass them as params
    params = (
        # Query the ERT field between start and end date
        f"ert>={start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')}"
        f"&ert<{end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')}"
        # only get the time (packet time)
        # Represent all times in yyyy-MM-dd'T'HH:mm:ss format
        "&project(time)&formatTime(\"yyyy-MM-dd'T'HH:mm:ss\")"
    )

    headers = _get_webpoda_headers()
    request = requests.Request(
        "GET", query_range, headers=headers, params=params
    ).prepare()

    # Returns a text file with the packet times
    # 2024-12-01T00:00:00
    # 2024-12-01T00:00:01
    with _make_request(request) as response:
        data = response.text.split("\n")
        logger.debug("Received data: %s", data)

    # Iterate over each line in the response, converting them to dates.
    # We first strip the line to remove any whitespace (\r) and skip any trailing lines
    return [
        datetime.datetime.strptime(line.strip(), "%Y-%m-%dT%H:%M:%S")
        for line in data
        if line.strip()
    ]


def get_packet_binary_data_sctime(
    apid: int, start_time: datetime.datetime, end_time: datetime.datetime
) -> bytes:
    """Get the binary packet data for the apid between the start and end time.

    This function makes a query to the webpoda API to get the binary packet data
    for the given APID between the start and end times in Spacecraft Time (SCT).

    Parameters
    ----------
    apid : int
        The APID to query for.
    start_time : datetime.datetime
        The start time of the query in Spacecraft Time (SCT).
    end_time : datetime.datetime
        The end time of the query in Spacecraft Time (SCT).

    Returns
    -------
    bytes
        The binary packet data for the given APID between the start and end time.
    """
    logger.info(
        f"Getting binary packet data for apid [{apid}] between "
        f"{start_time} and {end_time}"
    )
    # Add a .bin suffix to get the binary data back
    query_range = f"{WEBPODA_APID_URL}/{SYSTEM_ID}/apid_{apid}.bin"
    params = (
        # Query the SCT field between start and end date
        f"time>={start_time.strftime('%Y-%m-%dT%H:%M:%S.%f')}"
        f"&time<{end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')}"
        # only the raw packet data
        "&project(packet)"
    )

    headers = _get_webpoda_headers()
    request = requests.Request(
        "GET", query_range, headers=headers, params=params
    ).prepare()

    with _make_request(request) as response:
        return response.content


def get_repoint_file() -> Optional[Path]:
    """Download the most recently ingested repoint table.

    The repoint file is a cumulative data set (each newly ingested file
    contains every repointing since launch), so this always looks at
    ingestion date rather than any particular spacecraft data range: we only
    need to look back over the last two weeks of ingests to find the latest
    and greatest table.

    Returns
    -------
    pathlib.Path or None
        The path to the downloaded repoint table file, or None if no repoint
        files have been ingested in the last two weeks.
    """
    end_date = datetime.datetime.now()
    start_date = end_date - datetime.timedelta(weeks=2)
    # The endpoint floors end_ingest_date to 00:00:00 UTC that day, rather
    # than the actual current time, so a file ingested today after midnight
    # (e.g. received at 2026-09-18T15:35:09 UTC) would be missed by a query
    # for "last week through 2026-09-18T00:00:00". Push the end date
    # forward a day so today's ingestions are always included. This isn't
    # critical for the data-gap-filling task, but it matters when running
    # the `webpoda` command locally for debugging.
    end_date = end_date + datetime.timedelta(days=1)
    url = f"{imap_data_access.config['DATA_ACCESS_URL']}/repoint-table"
    logger.debug(f"Query repoint files with ingestion data: {start_date} - {end_date}")
    params = {
        "start_ingest_date": start_date.strftime("%Y%m%d"),
        "end_ingest_date": end_date.strftime("%Y%m%d"),
    }
    request = requests.Request("GET", url, params=params).prepare()
    with _make_request(request) as response:
        repoint_files = response.json()

    if not repoint_files:
        logger.info("No repoint files found.")
        logger.info("-" * 80)
        return None

    # Entries are cumulative repoint-table snapshots, often sharing the same
    # end_date across multiple versions, so the most recently ingested one is
    # the freshest/most complete table.
    latest_repoint_file = max(
        repoint_files,
        key=lambda item: datetime.datetime.strptime(
            item["ingestion_date"], "%Y-%m-%d, %H:%M:%S"
        ),
    )
    return imap_data_access.download(latest_repoint_file["file_path"])


def download_daily_data(
    instrument: str,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    upload_to_sdc=False,
    query_by_ert=True,
):
    """Download data for the apid and start/end time range from webpoda.

    PODA stands for packet on demand access. This function requests the IMAP specific
    API endpoint, so all APIDs must be from the IMAP mission.

    For each spacecraft day, if no L0 file exists yet in production, the freshly
    queried data is written directly as a new file (empty days are skipped, no
    empty files are created). If an L0 file already exists, the freshly queried
    data is compared against the latest production file via
    _compare_and_write_new_data: if the data changed, a new minor version is
    written (and uploaded, if upload_to_sdc is True); if not, nothing is kept.

    Parameters
    ----------
    instrument : str
        The instrument to download data for.
    start_time : datetime.datetime
        The start time of the query. If query_by_ert is True, this uses Earth Received
        Time (ERT). If query_by_ert is False, this uses Spacecraft Time (SCT).
    end_time : datetime.datetime
        The end time of the query. If query_by_ert is True, this uses Earth Received
        Time (ERT). If query_by_ert is False, this uses Spacecraft Time (SCT).
    upload_to_sdc : bool, optional
        If True, upload the data to the SDC data bucket, by default False
    query_by_ert : bool, optional
        If True, queries all data for all APIDs using the Earth Received Time (ERT)
        date range. If False, queries all data for all APIDs with Spacecraft Time (SCT)
        within the specified start and end date range. Default to True.
    """
    apids = INSTRUMENT_APIDS[instrument]
    logger.info(f"Downloading data for instrument [{instrument}]")

    if query_by_ert:
        # Query by ERT to find unique spacecraft dates
        logger.info(
            f"Querying Earth Received Time (ERT) range from {start_time} to {end_time}"
        )
        packet_times = [
            p
            for apid in apids
            for p in get_packet_times_ert(apid, start_time, end_time)
        ]
        # Get the unique dates from the packet times
        unique_dates = sorted(set([dt.date() for dt in packet_times]))
        logger.info(
            f"Found [{len(packet_times)}] packets for instrument [{instrument}] "
            f"between earth received time {start_time} and {end_time}"
        )
        logger.info(f"Unique spacecraft dates with packets: {unique_dates}")
    else:
        # Query by SCT - generate all dates in the range
        logger.info(
            "Querying Spacecraft Time (SCT) data that are in the "
            f"range from {start_time} to {end_time}"
        )
        unique_dates = []
        current_date = start_time.date()
        end_date = end_time.date()
        while current_date <= end_date:
            unique_dates.append(current_date)
            current_date += datetime.timedelta(days=1)
        logger.info(
            f"Querying {len(unique_dates)} spacecraft dates for "
            f"instrument [{instrument}] between spacecraft time "
            f"{start_time} and {end_time}"
        )
        logger.info(f"Spacecraft dates to query: {unique_dates}")

    # Iterate over the packet dates to make a query for each individual spacecraft day
    # packet_date 00:00:00 -> packet_date+1 00:00:00
    for date in unique_dates:
        daily_start_time = datetime.datetime.combine(date, datetime.time.min)
        daily_end_time = daily_start_time + datetime.timedelta(days=1)

        # Some instruments request a buffer of packets on either side of the midnight
        # boundary to ensure their packet groupings work together.
        buffer_minutes = _INSTRUMENT_BUFFER_MINUTES.get(instrument, 0)
        buffer_timedelta = datetime.timedelta(minutes=buffer_minutes)
        daily_start_time -= buffer_timedelta
        daily_end_time += buffer_timedelta

        # Iterate over all apids, downloading the content for this time period
        # concatenating all the binary returns into a single binary file
        daily_packet_content = b"".join(
            [
                get_packet_binary_data_sctime(apid, daily_start_time, daily_end_time)
                for apid in apids
            ]
        )
        if not daily_packet_content:
            logger.info(
                f"No data found for instrument [{instrument}] on {date}. Skipping."
            )
            logger.info("-" * 80)
            continue

        new_l0_path = _compare_and_write_new_data(
            instrument=instrument,
            start_time=date,
            content=daily_packet_content,
        )

        # If data has changed, upload the new file to the SDC data bucket if requested
        if new_l0_path is not None:
            _upload_if_requested(new_l0_path, upload_to_sdc)

    logger.info(f"Finished downloading data for instrument [{instrument}]")


# ruff: noqa: PLR0912, PLR0913
def download_repointing_data(
    instrument: str,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    repoint_data: list,
    upload_to_sdc=False,
    query_by_ert=True,
):
    """Download data for the instrument and start/end time range from webpoda.

    PODA stands for packet on demand access. This function requests the IMAP specific
    API endpoint, so all APIDs must be from the IMAP mission.

    For each pointing, if no L0 file exists yet in production, the freshly queried
    data is written directly as a new file (pointings with no packets are skipped,
    no empty files are created). If an L0 file already exists, the freshly queried
    data is compared against the latest production file via
    _compare_and_write_new_data: if the data changed, a new minor version is
    written (and uploaded, if upload_to_sdc is True); if not, nothing is kept.

    Parameters
    ----------
    instrument : str
        The instrument to download data for.
    start_time : datetime.datetime
        The start time of the query. If query_by_ert is True, this uses Earth
        Received Time (ERT) to determine which pointings have any packets at
        all. If query_by_ert is False, this uses Spacecraft Time (SCT) to
        directly select which pointings in repoint_data overlap the range.
    end_time : datetime.datetime
        The end time of the query. If query_by_ert is True, this uses Earth
        Received Time (ERT). If query_by_ert is False, this uses Spacecraft
        Time (SCT).
    repoint_data : list
        A list of dictionaries containing the repointing data. Each row
        represents a row in the repointing file and contains the
        repointing times in the format:
            repoint_start_sec_sclk	UINT
            repoint_start_subsec_sclk	UINT
            repoint_end_sec_sclk	UINT
            repoint_end_subsec_sclk	UINT
            repoint_start_utc	str
            repoint_end_utc	str
            repoint_id	UINT
    upload_to_sdc : bool, optional
        If True, upload the data to the SDC data bucket, by default False
    query_by_ert : bool, optional
        If True, uses the Earth Received Time (ERT) date range to determine
        which pointings have any packets before querying them. If False,
        every pointing in repoint_data overlapping the Spacecraft Time
        (SCT) start_time/end_time range is queried directly. Default to True.
    """
    apids = INSTRUMENT_APIDS[instrument]
    logger.info(f"Downloading data for instrument [{instrument}]")

    packet_times = []
    if query_by_ert:
        # Make a query to get the timestamps of the packets during this ERT
        # range. We can/will get packets outside of this range because of the way
        # we are only getting data after the fact and potentially backfilling
        # data gaps.
        packet_times = sorted(
            [
                p
                for apid in apids
                for p in get_packet_times_ert(apid, start_time, end_time)
            ]
        )
        if len(packet_times) == 0:
            logger.warning(
                f"No packets found for instrument [{instrument}] "
                f"between earth received time {start_time} and {end_time}"
            )
            return

        logger.info(
            f"Found [{len(packet_times)}] packets for instrument [{instrument}] "
            f"between earth received time {start_time} and {end_time}"
        )
    else:
        logger.info(
            "Querying Spacecraft Time (SCT) pointings in the range from "
            f"{start_time} to {end_time}"
        )

    # Iterate over the packet dates to make a query for each individual "pointing"
    # A "pointing" is defined as the time between the end of one repointing maneuver
    # to the end of the next repointing maneuver.
    # NOTE: We iterate over the repoint_data rather than the packet times because it is
    #       assumed to be the shorter list (1/day vs 1000s of packets/day per apid)
    for i in range(len(repoint_data) - 1):
        current_repoint = repoint_data[i]
        next_repoint = repoint_data[i + 1]
        # skip i and i+1 values that are NaN
        if current_repoint["repoint_end_utc"].lower() == "nan":
            # This pointing never "started"
            continue
        if next_repoint["repoint_end_utc"].lower() == "nan":
            # Missing repointing end time, so it isn't a complete "pointing" yet.
            continue
        pointing_start = datetime.datetime.strptime(
            current_repoint["repoint_end_utc"], "%Y-%m-%d %H:%M:%S.%f"
        )
        # NOTE: We need to make sure we are not double grabbing packets into the
        #       pointings. The times included are [repointing_start, repointing_end),
        #       exclusive on the right edge
        pointing_end = datetime.datetime.strptime(
            next_repoint["repoint_end_utc"], "%Y-%m-%d %H:%M:%S.%f"
        )

        if query_by_ert:
            if pointing_start > packet_times[-1]:
                # This pointing is after the last packet time, so skip it
                logger.debug(
                    f"Pointing start {pointing_start} is after last packet time "
                    f"{packet_times[-1]}, skipping"
                )
                continue
            if pointing_end < packet_times[0]:
                # This pointing is before the first packet time, so skip it
                logger.debug(
                    f"Pointing end {pointing_end} is before first packet time "
                    f"{packet_times[0]}, skipping"
                )
                continue
            if not any(
                pointing_start <= p_time <= pointing_end for p_time in packet_times
            ):
                # This pointing didn't contain any packets within it
                logger.debug(
                    f"Pointing start {pointing_start} and end {pointing_end} "
                    f"didn't contain any packets, skipping"
                )
                continue
        elif pointing_end <= start_time or pointing_start > end_time:
            # Query by SCT - only consider pointings overlapping [start_time, end_time]
            logger.debug(
                f"Pointing start {pointing_start} and end {pointing_end} "
                f"don't overlap {start_time} to {end_time}, skipping"
            )
            continue

        logger.info(
            f"Found pointing [{current_repoint['repoint_id']}] "
            f"between {pointing_start} and {pointing_end}"
        )

        # Iterate over all apids, downloading the content for this time period
        # concatenating all the binary returns into a single binary file
        pointing_packet_content = b"".join(
            [
                get_packet_binary_data_sctime(apid, pointing_start, pointing_end)
                for apid in apids
            ]
        )
        if not pointing_packet_content:
            logger.info(
                f"No data found for instrument [{instrument}] repoint ID "
                f"[{current_repoint['repoint_id']}] for {pointing_start} to "
                f"{pointing_end}. Skipping."
            )
            logger.info("-" * 80)
            continue

        new_l0_path = _compare_and_write_new_data(
            instrument=instrument,
            start_time=pointing_start,
            content=pointing_packet_content,
            repointing=int(current_repoint["repoint_id"]),
        )

        # If data has changed, upload the new file to the SDC data bucket if requested
        if new_l0_path is not None:
            _upload_if_requested(new_l0_path, upload_to_sdc)

    logger.info(f"Finished downloading data for instrument [{instrument}]")


def file_hash(path, algo="sha256", chunk_size=8192):
    """Compute the hex digest of the file at path.

    Parameters
    ----------
    path : str
        The path to the file.
    algo : str, optional
        The hashing algorithm to use (default is "sha256").
    chunk_size : int, optional
        The size of the chunks to read at a time (default is 8192).

    Returns
    -------
    str
        The hex digest of the file.
    """
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def format_size(size_bytes):
    """Convert bytes to human-readable format (MB or GB).

    The precision is set to 4 decimal places for both MB and GB.

    Parameters
    ----------
    size_bytes : int
        The size in bytes to format.

    Returns
    -------
    str
        The size in human-readable format, either in MB or GB.
    """
    if size_bytes >= 1e9:
        return f"{size_bytes / 1e9:.4f} GB"
    return f"{size_bytes / 1e6:.4f} MB"


def compare_files(current_file_path, new_file_path):
    """Compare two files by hash/size and print the same log format for every check.

    Parameters
    ----------
    current_file_path : pathlib.Path
        The path to the current production file.
    new_file_path : pathlib.Path
        The path to the newly queried data file.

    Returns
    -------
    bool
        True if the files are different (new data), False if they are the same.
    """
    current_filename = current_file_path.name
    new_filename = new_file_path.name

    # If file size have changed, then we know the data has changed.
    # So we can skip the hash check if the sizes are different.
    current_size = current_file_path.stat().st_size
    new_size = new_file_path.stat().st_size

    if new_size < current_size:
        logger.warning(
            f"New file is smaller than production file "
            f"({format_size(current_size)} vs {format_size(new_size)})"
        )
        # We don't want to upload but log a warning and return False to
        # indicate no new data.
        return False
    elif current_size < new_size:
        logger.info("Data has changed")
        logger.info(f"Prod {current_filename}: (size: {format_size(current_size)})")
        logger.info(f"New     {new_filename}: (size: {format_size(new_size)})")
        logger.info("-" * 80)
        return True

    current_hash = file_hash(current_file_path)
    new_hash = file_hash(new_file_path)

    if current_hash != new_hash:
        logger.info("Data has changed")
        logger.info(
            f"Prod {current_filename}: (size: {format_size(current_size)}), "
            f"(hash: {current_hash})"
        )
        logger.info(
            f"New     {new_filename}: (size: {format_size(new_size)}), "
            f"(hash: {new_hash})"
        )
        logger.info("-" * 80)
        return True
    else:
        logger.info(f"Data has not changed for {current_filename}.")
        logger.info("-" * 80)
        return False


def _latest_l0_minor_version(current_l0_files: list) -> int:
    """Determine the next available L0 minor version given the existing files.

    Parameters
    ----------
    current_l0_files : list
        The L0 files already in production for this instrument/date/repointing,
        as returned by imap_data_access.query. May be empty.

    Returns
    -------
    int
        The next available minor version number: 1 if current_l0_files is
        empty, otherwise the highest existing minor version plus one.
    """
    if not current_l0_files:
        return 1
    # Get the latest minor version incremented by 1 (this is never reset)
    return max(file["minor_version"] for file in current_l0_files) + 1


def _compare_and_write_new_data(
    instrument: str,
    start_time: datetime.datetime,
    content: bytes,
    repointing: Optional[int] = None,
) -> Optional[Path]:
    """Write freshly queried packet content to disk, comparing against production.

    If no L0 file exists yet in production for this instrument/date/repointing,
    `content` is written directly as minor version 1. If one exists
    already, `content` is written to a new, minor-version-bumped file, then
    compared against the latest production file: if nothing changed,
    None is returned; if the data changed, the new version's
    path is returned.

    Parameters
    ----------
    instrument : str
        The instrument the content belongs to.
    start_time : datetime.datetime
        The start time used to build the file's path (day or pointing start).
    content : bytes
        The freshly queried packet content to write.
    repointing : int, optional
        The repointing ID to build the file's path for, by default None.

    Returns
    -------
    pathlib.Path or None
        The path of the newly written file (minor version 1, or a bumped
        version if the data changed from production), or None if a
        production file already exists and the freshly queried content
        matches it.
    """
    # See if any L0 files already exist for this instrument/date/repointing.
    # We branch on this explicitly rather than inferring it from the next
    # minor version, since an existing file at minor version 0 would also
    # produce a next version of 1.
    current_l0_files = imap_data_access.query(
        instrument=instrument,
        data_level="l0",
        descriptor="raw",
        start_date=start_time.strftime("%Y%m%d"),
        # start_date is >= so we need to add an end_date to restrict the query
        end_date=start_time.strftime("%Y%m%d"),
        repointing=repointing,
    )

    if not current_l0_files:
        new_l0_path = imap_data_access.ScienceFilePath.generate_from_inputs(
            instrument=instrument,
            data_level="l0",
            descriptor="raw",
            start_time=start_time.strftime("%Y%m%d"),
            repointing=repointing,
            major_version=1,
            minor_version=1,
        ).construct_path()

        logger.info(
            f"New L0 file. Saving binary data of size {len(content) // 1000} kB "
            f"to {new_l0_path} as minor version 1"
        )
        new_l0_path.parent.mkdir(parents=True, exist_ok=True)
        new_l0_path.write_bytes(content)
        return new_l0_path

    # If we get here, this means L0 files already exists and we need to compare
    # the new queried content and see if it has changed.
    latest_l0_minor_version = _latest_l0_minor_version(current_l0_files)

    # The highest minor version is always the latest, so download it to
    # compare against.
    latest_l0_file = max(current_l0_files, key=lambda file: file["minor_version"])
    prod_l0_path = imap_data_access.download(latest_l0_file["file_path"])

    new_l0_path = imap_data_access.ScienceFilePath.generate_from_inputs(
        instrument=instrument,
        data_level="l0",
        descriptor="raw",
        start_time=start_time.strftime("%Y%m%d"),
        repointing=repointing,
        major_version=1,
        minor_version=latest_l0_minor_version,
    ).construct_path()

    logger.info(
        f"Saving binary data of size {len(content) // 1000} kB to {new_l0_path} "
        f"to compare against existing {prod_l0_path}"
    )

    new_l0_path.parent.mkdir(parents=True, exist_ok=True)
    new_l0_path.write_bytes(content)

    data_changed = compare_files(prod_l0_path, new_l0_path)
    if not data_changed:
        logger.info(
            f"Data for {prod_l0_path} hasn't changed, {new_l0_path} is a duplicate"
        )
        return None

    logger.info(
        f"Data for {prod_l0_path} has changed, keeping new version {new_l0_path}"
    )
    return new_l0_path


def _upload_if_requested(path: Path, upload_to_sdc: bool) -> None:
    """Upload path to the SDC data bucket if requested, logging any failure."""
    if not upload_to_sdc:
        return
    logger.info("Uploading packet file to the server: %s", path)
    try:
        imap_data_access.upload(path)
    except IMAPDataAccessError as e:
        # We don't want to ruin all subsequent downloads if one fails
        # during upload, so log the error and continue
        logger.error(f"Failed to upload {path} to the server: {e}")
