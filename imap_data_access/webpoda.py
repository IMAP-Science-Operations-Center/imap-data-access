"""Download all data since the last contact from webpoda.

This script goes through and downloads all the newly arrived data from webpoda since
the last contact.

1. Iterate over each APID
2. Make a query to webpoda for ERTs between the last contact time and now.
3. Create a list of S/C dates with data from the last contact time.
   NOTE: This is not the same as the ERTs because there could be backfilled gaps.
4. Iterate over the S/C dates and download the binary data for each date.
5. Save the data to a local file

Location of list of APIDs and associated instruments:
https://lasp.colorado.edu/galaxy/spaces/IMAP/pages/155648242/Packet+Decommutation+Resource+Page+-+IMAP
"""

import csv
import datetime
import logging
import urllib.parse
import urllib.request
import urllib.response
from pathlib import Path

import imap_data_access
from imap_data_access.io import _get_url_response

logger = logging.getLogger(__name__)


WEBPODA_APID_URL = "https://lasp.colorado.edu/ops/imap/poda/dap2/apids"
# The system ID for the IMAP mission
# SID1 == FLIGHT instrument telemetry and spacecraft telemetry after launch
# SID2 == FLIGHT instrument telemetry and spacecraft telemetry before launch
# SID3 == Instrument simulator telemetry and spacecraft simulator telemetry
SYSTEM_ID = "SID2"

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
    "hi": [754, 769, 770, 818, 833, 834, 818, 833, 834],
    "hit": [1251, 1252, 1253],
    "idex": [1377, 1420, 1424],
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


def _add_webpoda_headers(request: urllib.request.Request) -> urllib.request.Request:
    """Add the necessary headers for webpoda requests.

    This function adds the necessary headers for webpoda requests to the provided
    request object. It returns the modified request object.
    """
    if not imap_data_access.config.get("WEBPODA_TOKEN", ""):
        raise ValueError(
            "The IMAP_WEBPODA_TOKEN environment variable must be set. "
            "You can run the following command to get the token: "
            "echo -n 'username:password' | base64"
        )
    request.add_header(
        "Authorization", f"Basic {imap_data_access.config['WEBPODA_TOKEN']}"
    )
    return request


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
    logger.debug(
        f"Getting packet times for apid [{apid}] between "
        f"{start_time} and {end_time}"
    )

    # Add a .txt suffix to get the data in text format back
    query_range = f"{WEBPODA_APID_URL}/{SYSTEM_ID}/apid_{apid}.txt?"

    # We need to properly encode the query string to make sure the special characters
    # are handled correctly
    query_range += urllib.parse.quote(
        # Query the ERT field between start and end date
        f'ert>={start_time.strftime("%Y-%m-%dT%H:%M:%S")}'
        + f'&ert<={end_time.strftime("%Y-%m-%dT%H:%M:%S")}'
        # only get the time (packet time)
        # Represent all times in yyyy-MM-dd'T'HH:mm:ss format
        + "&project(time)&formatTime(\"yyyy-MM-dd'T'HH:mm:ss\")"
    )

    request = urllib.request.Request(query_range, method="GET")
    request = _add_webpoda_headers(request)
    # Returns a text file with the packet times
    # 2024-12-01T00:00:00
    # 2024-12-01T00:00:01
    with _get_url_response(request) as response:
        data = response.read().decode().split("\n")

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
    logger.debug(
        f"Getting binary packet data for apid [{apid}] between "
        f"{start_time} and {end_time}"
    )

    # Add a .bin suffix to get the binary data back
    query_range = f"{WEBPODA_APID_URL}/{SYSTEM_ID}/apid_{apid}.bin?"

    # We need to properly encode the query string to make sure the special characters
    # are handled correctly
    query_range += urllib.parse.quote(
        # Query the SCT field between start and end date
        f'time>={start_time.strftime("%Y-%m-%dT%H:%M:%S")}'
        + f'&time<={end_time.strftime("%Y-%m-%dT%H:%M:%S")}'
        # only the raw packet data
        + "&project(packet)"
    )
    request = urllib.request.Request(query_range, method="GET")
    request = _add_webpoda_headers(request)

    with _get_url_response(request) as response:
        return response.read()


def download_daily_data(
    instrument: str,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    version: str = "v001",
    upload_to_server=False,
):
    """Download data for the apid and start/end time range from webpoda.

    PODA stands for packet on demand access. This function requests the IMAP specific
    API endpoint, so all APIDs must be from the IMAP mission.

    The query is based on earth received time (ert), so all packets received during
    a specific downlink to the ground, not the spacecraft time.

    Parameters
    ----------
    instrument : str
        The instrument to download data for.
    start_time : datetime.datetime
        The start time of the query in Earth Received Time (ERT).
    end_time : datetime.datetime
        The end time of the query in Earth Received Time (ERT).
    version : str, optional
        The version to use on the downloaded data file, by default "v001"
    upload_to_server : bool, optional
        If True, upload the data to the SDC data bucket, by default False
    """
    apids = INSTRUMENT_APIDS[instrument]
    logger.info(f"Downloading data for instrument [{instrument}]")
    # Make a query to get the timestamps of the packets during this ERT
    # range. We can/will get packets outside of this range because of the way we are
    # only getting data after the fact and potentially backfilling data gaps.
    packet_times = [
        p for apid in apids for p in get_packet_times_ert(apid, start_time, end_time)
    ]

    # Get the unique dates from the packet times
    unique_dates = set([dt.date() for dt in packet_times])
    logger.info(
        f"Found [{len(packet_times)}] packets for instrument [{instrument}] "
        f"between earth received time {start_time} and {end_time}"
    )
    logger.info(f"Unique spacecraft dates with packets: {unique_dates}")

    # Iterate over the packet dates to make a query for each individual spacecraft day
    # packet_date 00:00:00 -> packet_date 23:59:59
    for date in unique_dates:
        science_file = imap_data_access.ScienceFilePath.generate_from_inputs(
            instrument=instrument,
            data_level="l0",
            descriptor="raw",
            start_time=date.strftime("%Y%m%d"),
            version=version,
        )
        path = science_file.construct_path()
        if path.exists():
            logger.info(f"Skipping {path} because it already exists.")
            continue

        daily_start_time = datetime.datetime.combine(date, datetime.time.min)
        daily_end_time = datetime.datetime.combine(date, datetime.time.max)

        # Iterate over all apids, downloading the content for this time period
        # concatenating all the binary returns into a single binary file
        daily_packet_content = b"".join(
            [
                get_packet_binary_data_sctime(apid, daily_start_time, daily_end_time)
                for apid in apids
            ]
        )

        logger.info(
            f"Saving binary data of size {len(daily_packet_content) // 1000} kB "
            f"to {path}"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(daily_packet_content)
        if upload_to_server:
            # Upload the data to the server
            imap_data_access.upload(path)


def download_repointing_data(  # noqa: PLR0913
    instrument: str,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    repointing_file: Path,
    version: str = "v001",
    upload_to_server=False,
):
    """Download data for the instrument and start/end time range from webpoda.

    PODA stands for packet on demand access. This function requests the IMAP specific
    API endpoint, so all APIDs must be from the IMAP mission.

    The query is based on earth received time (ert), so all packets received during
    a specific downlink to the ground, not the spacecraft time.

    Parameters
    ----------
    instrument : str
        The instrument to download data for.
    start_time : datetime.datetime
        The start time of the query in Earth Received Time (ERT).
    end_time : datetime.datetime
        The end time of the query in Earth Received Time (ERT).
    repointing_file : Path
        The path to the repointing file. This file should contain the repointing
        times in the format:
            repoint_start_sec_sclk	UINT
            repoint_start_subsec_sclk	UINT
            repoint_end_sec_sclk	UINT
            repoint_end_subsec_sclk	UINT
            repoint_start_time_utc	str
            repoint_end_time_utc	str
            repoint_id	UINT
    version : str, optional
        The version to use on the downloaded data file, by default "v001"
    upload_to_server : bool, optional
        If True, upload the data to the SDC data bucket, by default False
    """
    # Store a list of rows in the repointing file
    with open(repointing_file) as f:
        repointings = list(csv.DictReader(f))
    logger.debug(
        f"Repointing file [{repointing_file}] contains [{len(repointings)}] rows"
    )

    apids = INSTRUMENT_APIDS[instrument]
    logger.info(f"Downloading data for instrument [{instrument}]")
    # Make a query to get the timestamps of the packets during this ERT
    # range. We can/will get packets outside of this range because of the way we are
    # only getting data after the fact and potentially backfilling data gaps.
    packet_times = sorted(
        [p for apid in apids for p in get_packet_times_ert(apid, start_time, end_time)]
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

    # Iterate over the packet dates to make a query for each individual "pointing"
    # A "pointing" is defined as the time between the end of one repointing maneuver
    # to the end of the next repointing maneuver.
    # NOTE: We iterate over the repointings rather than the packet times because it is
    #       assumed to be the shorter list (1/day vs 1000s of packets/day per apid)
    for i in range(len(repointings) - 1):
        pointing_start = datetime.datetime.strptime(
            repointings[i]["repoint_end_time_utc"], "%Y-%m-%dT%H:%M:%S.%f"
        )
        if repointings[i + 1]["repoint_end_time_utc"].lower() == "nan":
            # Missing repointing end time, so it isn't a complete "pointing" yet.
            continue
        if pointing_start > packet_times[-1]:
            # This pointing is after the last packet time, so skip it
            logger.debug(
                f"Pointing start {pointing_start} is after last packet time "
                f"{packet_times[-1]}, skipping"
            )
            continue
        # NOTE: All queries are <= / >= following this, so we need to make sure we
        #       are not double grabbing packets into the pointings.
        #       The times included are [repointing_start, repointing_end), exclusive
        #       on the right edge
        pointing_end = datetime.datetime.strptime(
            repointings[i + 1]["repoint_end_time_utc"], "%Y-%m-%dT%H:%M:%S.%f"
        ) - datetime.timedelta(seconds=1)
        if pointing_end < packet_times[0]:
            # This pointing is before the first packet time, so skip it
            logger.debug(
                f"Pointing end {pointing_end} is before first packet time "
                f"{packet_times[0]}, skipping"
            )
            continue
        if not any(pointing_start <= p_time <= pointing_end for p_time in packet_times):
            # This pointing didn't contain any packets within it
            logger.debug(
                f"Pointing start {pointing_start} and end {pointing_end} "
                f"didn't contain any packets, skipping"
            )
            continue

        logger.info(
            f"Found packets during pointing between {pointing_start} and {pointing_end}"
        )

        science_file = imap_data_access.ScienceFilePath.generate_from_inputs(
            instrument=instrument,
            data_level="l0",
            descriptor="raw",
            start_time=pointing_start.strftime("%Y%m%d"),
            repointing=int(repointings[i]["repoint_id"]),
            version=version,
        )
        path = science_file.construct_path()
        if path.exists():
            logger.info(f"Skipping {path} because it already exists.")
            continue

        # Iterate over all apids, downloading the content for this time period
        # concatenating all the binary returns into a single binary file
        pointing_packet_content = b"".join(
            [
                get_packet_binary_data_sctime(apid, pointing_start, pointing_end)
                for apid in apids
            ]
        )

        logger.info(
            f"Saving binary data of size {len(pointing_packet_content) // 1000} kB "
            f"to {path}"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pointing_packet_content)
        if upload_to_server:
            # Upload the data to the server
            imap_data_access.upload(path)
