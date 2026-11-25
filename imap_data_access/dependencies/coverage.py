"""The time span that a file nominally covers.

A file's nominal coverage is the time window it's meant to cover by
construction: the window of the processing run that makes it, rather than the
span of the data inside it. It's worked out from the file's name and, for a
file that a processing job makes, from that job's partition, so that it
matches the windows the SDC processing pipeline runs jobs over. A file that
covers a pointing gets the pointing's times from the SDC's repoint file.
"""

import csv
import datetime
import os
from functools import cache
from typing import NamedTuple

from imap_data_access.dependencies.config import (
    IDEX_10_DAY_RANGES_PATH,
    DependencyConfigReader,
)
from imap_data_access.dependencies.map_windows import (
    BaseENAMapPartition,
    Map1YrPartition,
    Map3MoPartition,
    Map6MoPartition,
)
from imap_data_access.dependencies.nodes import DependencyNode, ProcessingJobNode
from imap_data_access.file_validation import (
    AncillaryFilePath,
    DependencyFilePath,
    ImapFilePath,
    ReleaseFilePath,
    ScienceFilePath,
    generate_imap_file_path,
)
from imap_data_access.repoint import repoint_query

ONE_DAY = datetime.timedelta(days=1)

_MAP_PARTITIONS: dict[str, type[BaseENAMapPartition]] = {
    "3mo": Map3MoPartition,
    "6mo": Map6MoPartition,
    "1yr": Map1YrPartition,
}


class Coverage(NamedTuple):
    """The half-open time span ``[start, end)`` that a file nominally covers.

    Attributes
    ----------
    start : datetime.datetime
        The start of the span, in UTC.
    end : datetime.datetime or None
        The end of the span, in UTC. The span stops just before it. None means
        that the span has no stated end, which happens only for an ancillary
        file whose name has no end date.
    """

    start: datetime.datetime
    end: datetime.datetime | None


class CoverageError(ValueError):
    """A file's nominal coverage can't be worked out."""


class PointingNotFoundError(CoverageError):
    """The start or end of the pointing that a file covers isn't known yet."""


def nominal_coverage(
    file: str | os.PathLike | ImapFilePath,
    reader: DependencyConfigReader | None = None,
) -> Coverage:
    """Return the time span that a file nominally covers.

    The span depends on the kind of file:

    - **An ancillary file with a repointing in its name** covers that pointing.
    - **Any other ancillary file** covers the dates in its name, from the start
      of its start date up to the end of its end date. If its name has no end
      date, the span has no end.
    - **A science or quicklook file that a processing job makes** covers the
      job's partition window that the file belongs to:

      - ``daily``: the day of the file's start date.
      - ``repoint``: the pointing whose repointing number is in the file's name.
      - ``10d``: the IDEX 10-day window that starts on the file's start date,
        up to the start of the next window.
      - ``3mo``, ``6mo``, ``1yr``: the ENA map window that starts on the file's
        start date.

    - **A science or quicklook file that no job makes**, such as an L0 file or
      one that an instrument team uploads, covers the pointing in its name if it
      has one, and otherwise the day of its start date.

    Days start at midnight UTC. A pointing runs from the end of the repointing
    maneuver with the file's repointing number to the end of the next one, as
    in the SDC's pointing table and repoint partitions. Those times come from
    the SDC's newest repoint file, through
    :func:`imap_data_access.repoint_query`, so files that cover a pointing need
    access to the SDC. Other files don't.

    Parameters
    ----------
    file : str, os.PathLike or ImapFilePath
        The file, as its name, its path or a parsed file path.
    reader : DependencyConfigReader, optional
        The dependency configuration that says which job makes a file. Defaults
        to the configuration that ships with imap-data-access.

    Returns
    -------
    Coverage
        The ``[start, end)`` span, in UTC.

    Raises
    ------
    PointingNotFoundError
        If the file covers a pointing that the SDC's repoint files don't have
        yet, or that hasn't ended yet.
    IMAPDataAccessError
        If the file covers a pointing and the SDC can't be reached.
    CoverageError
        If the file has no nominal coverage, for example because it's a SPICE
        file or the job that makes it has no usable partition, or if its name
        doesn't match the partition, for example a map file whose start date
        doesn't start a map window.
    """
    path = _parse(file)
    name = str(path.filename)
    if isinstance(path, DependencyFilePath | ReleaseFilePath) or not isinstance(
        path, ScienceFilePath | AncillaryFilePath
    ):
        raise CoverageError(
            f"{name} isn't a science, quicklook or ancillary file, so it has no "
            "nominal coverage"
        )

    if isinstance(path, AncillaryFilePath):
        return _ancillary_coverage(path, name)

    reader = reader or DependencyConfigReader()
    product = DependencyNode(path.instrument, path.data_level, path.descriptor)
    try:
        job = reader.get_node_for_output(product)
    except ValueError:
        # No job makes this file, so the file's name decides.
        if path.repointing is not None:
            return _pointing_coverage(path.repointing, name)
        start = _day(path.start_date)
        return Coverage(start, start + ONE_DAY)
    return _partition_coverage(path, name, job)


def _ancillary_coverage(path: AncillaryFilePath, name: str) -> Coverage:
    """Return the pointing or the dates in an ancillary file's name."""
    if path.repointing is not None:
        return _pointing_coverage(path.repointing, name)
    start = _day(path.start_date)
    if path.end_date is None:
        return Coverage(start, None)
    end = _day(path.end_date) + ONE_DAY
    if end <= start:
        raise CoverageError(f"{name} has an end date before its start date")
    return Coverage(start, end)


def _partition_coverage(
    path: ScienceFilePath, name: str, job: ProcessingJobNode
) -> Coverage:
    """Return the window of the job's partition that a file belongs to."""
    start = _day(path.start_date)
    partition = job.partition
    job_name = f"({job.source}, {job.data_type}, {job.descriptor})"
    if partition == "daily":
        return Coverage(start, start + ONE_DAY)
    if partition == "repoint":
        if path.repointing is None:
            raise CoverageError(
                f"{name} is made by the repoint job {job_name}, but has no "
                "repointing in its name"
            )
        return _pointing_coverage(path.repointing, name)
    if partition == "10d":
        window = _idex_10_day_windows().get(start)
        if window is None:
            raise CoverageError(
                f"{name} is made by the 10-day job {job_name}, but no IDEX 10-day "
                f"window starts on {path.start_date}"
            )
        return window
    if partition in _MAP_PARTITIONS:
        cadence = _MAP_PARTITIONS[partition](start)
        for window in cadence.get_windows(start.year - 1) + cadence.get_windows(
            start.year
        ):
            if window.start == start:
                return Coverage(window.start, window.end)
        raise CoverageError(
            f"{name} is made by the {partition} map job {job_name}, but no "
            f"{partition} map window starts on {path.start_date}"
        )
    if partition == "pointing_attitude":
        raise CoverageError(
            f"{name} is made by {job_name}, which makes SPICE kernels; their "
            "coverage is measured from their contents instead"
        )
    raise CoverageError(
        f"{name} is made by {job_name}, whose partition {partition!r} has no "
        "known window"
    )


def _parse(file: str | os.PathLike | ImapFilePath) -> ImapFilePath:
    """Return the parsed file path for a file given in any supported form."""
    if isinstance(file, ImapFilePath):
        return file
    name = os.path.basename(os.fspath(file))
    try:
        return generate_imap_file_path(name)
    except ValueError as e:
        raise CoverageError(f"{name} isn't a valid IMAP file name: {e}") from e


def _day(date: str) -> datetime.datetime:
    """Return midnight UTC at the start of a ``YYYYMMDD`` date."""
    return datetime.datetime.strptime(date, "%Y%m%d").replace(
        tzinfo=datetime.timezone.utc
    )


def _pointing_coverage(repointing: int, name: str) -> Coverage:
    """Return the span of a pointing, from the SDC's repoint file."""
    repoint = repoint_query(repointing)
    if repoint is None or repoint.pointing_start is None:
        raise PointingNotFoundError(
            f"{name} covers repointing {repointing}, which the SDC's repoint "
            "files don't have yet"
        )
    if repoint.pointing_end is None:
        raise PointingNotFoundError(
            f"{name} covers repointing {repointing}, whose pointing hasn't ended yet"
        )
    start, end = repoint.pointing_start, repoint.pointing_end
    if end <= start:
        raise CoverageError(
            f"{name} covers repointing {repointing}, which ends before it starts"
        )
    return Coverage(start, end)


@cache
def _idex_10_day_windows() -> dict[datetime.datetime, Coverage]:
    """Return the IDEX 10-day windows, keyed by their start.

    As in the SDC's 10-day partitions, each window runs from its start date up
    to the start of the next window. The last one runs to its end date.
    """
    with open(IDEX_10_DAY_RANGES_PATH, newline="") as f:
        rows = sorted(
            (_day(row["start_date"]), _day(row["end_date"]))
            for row in csv.DictReader(f)
        )
    ends = [start for start, _ in rows[1:]] + [rows[-1][1]]
    return {
        start: Coverage(start, end) for (start, _), end in zip(rows, ends, strict=True)
    }
