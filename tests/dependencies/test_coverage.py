"""Tests for the nominal coverage of files."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from imap_data_access import Repoint
from imap_data_access.dependencies import (
    Coverage,
    CoverageError,
    DependencyConfigReader,
    PointingNotFoundError,
    nominal_coverage,
)
from imap_data_access.dependencies import coverage as coverage_module
from imap_data_access.file_validation import ScienceFilePath

UTC = timezone.utc


def utc(*args):
    return datetime(*args, tzinfo=UTC)


# One SWE job for each partition, plus one with no partition and one with a
# partition the SDC doesn't know.
SWE_JOBS = [
    ("l1a", "day", "daily"),
    ("l1b", "pointing", "repoint"),
    ("l1c", "tenday", "10d"),
    ("l2", "map-3mo", "3mo"),
    ("l2", "map-6mo", "6mo"),
    ("l2", "map-1yr", "1yr"),
    ("l3", "attitude", "pointing_attitude"),
    ("l3a", "unpartitioned", None),
    ("l3b", "weekly", "weekly"),
]


def _job(data_type, descriptor, partition):
    partition_line = f"  partition: {partition}\n" if partition else ""
    return f"""
({data_type}, {descriptor}):
{partition_line}  inputs:
    - source: swe
      data_type: l0
      descriptor: raw
  outputs:
    - source: swe
      data_type: {data_type}
      descriptor: {descriptor}
      major_version: 1
"""


def _repoint(repoint_id, pointing_start, pointing_end):
    return Repoint(repoint_id, None, pointing_start, pointing_start, pointing_end)


# Repointing 123's pointing is complete, 124's hasn't ended, 125's ends before
# it starts, and 126's maneuver has no end time.
REPOINTS = {
    123: _repoint(123, utc(2025, 4, 15, 3, 0, 5, 250000), utc(2025, 4, 16, 2, 45)),
    124: _repoint(124, utc(2025, 4, 16, 3), None),
    125: _repoint(125, utc(2025, 4, 17), utc(2025, 4, 16)),
    126: _repoint(126, None, utc(2025, 4, 18)),
}


@pytest.fixture(autouse=True)
def repoints(monkeypatch):
    """Stand in for the SDC's repoint file, and record the lookups."""
    lookups = []

    def query_repoint(repoint_id):
        lookups.append(repoint_id)
        return REPOINTS.get(repoint_id)

    monkeypatch.setattr(coverage_module, "query_repoint", query_repoint)
    return lookups


@pytest.fixture
def reader(one_job_yaml_dir):
    """A configuration where SWE has one job for each partition."""
    (one_job_yaml_dir / "imap_swe_dependencies.yaml").write_text(
        "".join(_job(*job) for job in SWE_JOBS)
    )
    return DependencyConfigReader(one_job_yaml_dir)


def test_daily(reader):
    coverage = nominal_coverage("imap_swe_l1a_day_20250101_v001.cdf", reader=reader)
    assert coverage == Coverage(utc(2025, 1, 1), utc(2025, 1, 2))


def test_coverage_unpacks_to_start_and_end(reader):
    start, end = nominal_coverage("imap_swe_l1a_day_20250101_v001.cdf", reader=reader)
    assert end - start == timedelta(days=1)


def test_repoint(reader, repoints):
    """A repoint file covers the pointing named by the number in its name."""
    coverage = nominal_coverage(
        "imap_swe_l1b_pointing_20250415-repoint00123_v001.cdf", reader=reader
    )
    # The pointing's times are kept to full precision.
    assert coverage == Coverage(
        utc(2025, 4, 15, 3, 0, 5, 250000), utc(2025, 4, 16, 2, 45)
    )
    assert repoints == [123]


@pytest.mark.parametrize(
    ("repointing", "message"),
    [
        pytest.param(999, "don't have yet", id="no repoint row"),
        pytest.param(126, "don't have yet", id="no pointing start"),
        pytest.param(124, "hasn't ended yet", id="pointing not ended"),
    ],
)
def test_repoint_pointing_not_found(reader, repointing, message):
    name = f"imap_swe_l1b_pointing_20250415-repoint{repointing:05d}_v001.cdf"
    with pytest.raises(
        PointingNotFoundError, match=f"repointing {repointing}.*{message}"
    ):
        nominal_coverage(name, reader=reader)


def test_repoint_pointing_ends_before_it_starts(reader):
    with pytest.raises(CoverageError, match="ends before it starts"):
        nominal_coverage(
            "imap_swe_l1b_pointing_20250417-repoint00125_v001.cdf", reader=reader
        )


def test_repoint_file_without_a_repointing(reader, repoints):
    with pytest.raises(CoverageError, match="no repointing in its name") as error:
        nominal_coverage("imap_swe_l1b_pointing_20250415_v001.cdf", reader=reader)
    assert not isinstance(error.value, PointingNotFoundError)
    assert repoints == []


def test_only_pointing_files_look_up_repoints(reader, repoints):
    """Other files need no access to the SDC."""
    nominal_coverage("imap_swe_l1a_day_20250101_v001.cdf", reader=reader)
    nominal_coverage("imap_swe_l2_map-3mo_20250325_v001.cdf", reader=reader)
    nominal_coverage("imap_swe_esa-lut_20250101_v001.csv")
    assert repoints == []


def test_10_day(reader):
    """A 10-day window runs up to the start of the next one."""
    coverage = nominal_coverage("imap_swe_l1c_tenday_20250110_v001.cdf", reader=reader)
    assert coverage == Coverage(utc(2025, 1, 10), utc(2025, 1, 20))


def test_10_day_last_window_runs_to_its_end_date(reader):
    coverage = nominal_coverage("imap_swe_l1c_tenday_20361225_v001.cdf", reader=reader)
    assert coverage == Coverage(utc(2036, 12, 25), utc(2037, 1, 1))


def test_10_day_file_not_on_a_window_start(reader):
    with pytest.raises(CoverageError, match="no IDEX 10-day window starts on"):
        nominal_coverage("imap_swe_l1c_tenday_20250111_v001.cdf", reader=reader)


@pytest.mark.parametrize(
    ("descriptor", "start", "end"),
    [
        ("map-3mo", utc(2024, 12, 25), utc(2025, 3, 25)),
        ("map-3mo", utc(2025, 9, 25), utc(2025, 12, 25)),
        ("map-6mo", utc(2025, 6, 25), utc(2025, 12, 25)),
        ("map-1yr", utc(2024, 12, 25), utc(2025, 12, 25)),
    ],
)
def test_map(reader, descriptor, start, end):
    name = f"imap_swe_l2_{descriptor}_{start:%Y%m%d}_v001.cdf"
    assert nominal_coverage(name, reader=reader) == Coverage(start, end)


@pytest.mark.parametrize(
    "name",
    [
        "imap_swe_l2_map-3mo_20250101_v001.cdf",
        # March 25 starts a 3-month window, but not a 6-month or 1-year one.
        "imap_swe_l2_map-6mo_20250325_v001.cdf",
        "imap_swe_l2_map-1yr_20250625_v001.cdf",
    ],
)
def test_map_file_not_on_a_window_start(reader, name):
    with pytest.raises(CoverageError, match="map window starts on"):
        nominal_coverage(name, reader=reader)


def test_pointing_attitude_has_no_coverage(reader):
    with pytest.raises(CoverageError, match="makes SPICE kernels"):
        nominal_coverage("imap_swe_l3_attitude_20250101_v001.cdf", reader=reader)


@pytest.mark.parametrize(
    ("name", "partition"),
    [
        ("imap_swe_l3a_unpartitioned_20250101_v001.cdf", "None"),
        ("imap_swe_l3b_weekly_20250101_v001.cdf", "'weekly'"),
    ],
)
def test_unknown_partition(reader, name, partition):
    with pytest.raises(CoverageError, match=f"partition {partition} has no known"):
        nominal_coverage(name, reader=reader)


def test_no_job_makes_the_file(reader):
    """A file no job makes, such as an L0 file, covers the day of its start date."""
    coverage = nominal_coverage("imap_swe_l0_raw_20250101_v001.pkts", reader=reader)
    assert coverage == Coverage(utc(2025, 1, 1), utc(2025, 1, 2))


def test_no_job_makes_the_file_with_a_repointing(reader):
    """With a repointing in its name, such a file covers that pointing."""
    coverage = nominal_coverage(
        "imap_swe_l0_raw_20250415-repoint00123_v001.pkts", reader=reader
    )
    assert coverage == Coverage(
        utc(2025, 4, 15, 3, 0, 5, 250000), utc(2025, 4, 16, 2, 45)
    )
    with pytest.raises(PointingNotFoundError):
        nominal_coverage(
            "imap_swe_l0_raw_20250416-repoint00124_v001.pkts", reader=reader
        )


def test_quicklook(reader):
    coverage = nominal_coverage("imap_swe_l1a_day_20250101_v001.png", reader=reader)
    assert coverage == Coverage(utc(2025, 1, 1), utc(2025, 1, 2))


def test_ancillary_with_an_end_date():
    """An ancillary file covers its dates, up to the end of its end date."""
    coverage = nominal_coverage("imap_swe_esa-lut_20250101_20250110_v001.csv")
    assert coverage == Coverage(utc(2025, 1, 1), utc(2025, 1, 11))


def test_ancillary_without_an_end_date():
    """Without an end date, an ancillary file's coverage has no end."""
    coverage = nominal_coverage("imap_swe_esa-lut_20250101_v001.csv")
    assert coverage == Coverage(utc(2025, 1, 1), None)


def test_ancillary_ending_before_it_starts():
    with pytest.raises(CoverageError, match="end date before its start date"):
        nominal_coverage("imap_swe_esa-lut_20250110_20250101_v001.csv")


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("naif0012.tls", id="SPICE"),
        pytest.param("imap_swe_l1a_sci_20250101_v001.json", id="dependency file"),
    ],
)
def test_files_without_coverage(name):
    with pytest.raises(CoverageError, match="has no nominal coverage"):
        nominal_coverage(name)


def test_invalid_file_name():
    with pytest.raises(CoverageError, match="isn't a valid IMAP file name"):
        nominal_coverage("not_an_imap_file.txt")


def test_errors_are_value_errors():
    assert issubclass(PointingNotFoundError, CoverageError)
    assert issubclass(CoverageError, ValueError)


@pytest.mark.parametrize(
    "file",
    [
        Path("imap/swe/l1a/2025/01/imap_swe_l1a_day_20250101_v001.cdf"),
        "imap/swe/l1a/2025/01/imap_swe_l1a_day_20250101_v001.cdf",
        ScienceFilePath("imap_swe_l1a_day_20250101_v001.cdf"),
    ],
    ids=["Path", "str path", "ScienceFilePath"],
)
def test_file_forms(reader, file):
    assert nominal_coverage(file, reader=reader) == Coverage(
        utc(2025, 1, 1), utc(2025, 1, 2)
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "imap_swe_l1a_sci_20250101_v001.cdf",
            Coverage(utc(2025, 1, 1), utc(2025, 1, 2)),
        ),
        (
            "imap_idex_l1a_sci-10days_20250110_v001.cdf",
            Coverage(utc(2025, 1, 10), utc(2025, 1, 20)),
        ),
        (
            "imap_ultra_l2_u45-ena-h-hf-nsp-full-hae-2deg-3mo_20250325_v001.cdf",
            Coverage(utc(2025, 3, 25), utc(2025, 6, 25)),
        ),
    ],
)
def test_packaged_configuration(name, expected):
    """By default, the job that makes a file comes from the packaged YAML."""
    assert nominal_coverage(name) == expected
