"""Tests for the dependency configuration files that ship with imap-data-access."""

import csv
import re
from datetime import datetime

import pytest

import imap_data_access
from imap_data_access.dependencies import (
    DEPENDENCY_CONFIG_DIR,
    IDEX_10_DAY_RANGES_PATH,
    DependencyConfigReader,
    get_kickoff_jobs,
)

# The reader skips these instruments, and every other one needs a YAML file.
SKIPPED_INSTRUMENTS = {"ialirt", "l1const"}

# The format reference, and the YAML examples in it.
FORMAT_REFERENCE = DEPENDENCY_CONFIG_DIR / "README.md"
REFERENCE_EXAMPLES = re.findall(
    r"```yaml\n(.*?)```", FORMAT_REFERENCE.read_text(encoding="utf-8"), re.DOTALL
)


def test_one_yaml_file_per_instrument():
    assert {path.name for path in DEPENDENCY_CONFIG_DIR.glob("*.yaml")} == {
        f"imap_{instrument}_dependencies.yaml"
        for instrument in imap_data_access.VALID_INSTRUMENTS - SKIPPED_INSTRUMENTS
    }


def test_reader_defaults_to_packaged_yaml():
    """With no directory given, the reader loads every job in the packaged YAML."""
    reader = DependencyConfigReader()
    # One job per "(data_type, descriptor)" key across every instrument's file.
    expected = sum(
        len(re.findall(r"^\(", path.read_text(), re.MULTILINE))
        for path in DEPENDENCY_CONFIG_DIR.glob("*.yaml")
    )
    assert len(reader.config) == expected
    assert DependencyConfigReader(DEPENDENCY_CONFIG_DIR).config is reader.config


def test_get_kickoff_jobs_defaults_to_packaged_yaml():
    reader = DependencyConfigReader()
    assert get_kickoff_jobs() == get_kickoff_jobs(reader=reader)
    assert get_kickoff_jobs("swe") == [reader.config[("swe", "l1a", "all")]]


def test_idex_10_day_ranges():
    with open(IDEX_10_DAY_RANGES_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["start_date", "end_date", "doy"]
    for row in rows:
        datetime.strptime(row["start_date"], "%Y%m%d")
        datetime.strptime(row["end_date"], "%Y%m%d")
    # Each window's start date names its partition, so they must be unique.
    start_dates = [row["start_date"] for row in rows]
    assert len(set(start_dates)) == len(start_dates)


def test_yaml_files_point_to_the_format_reference():
    for path in DEPENDENCY_CONFIG_DIR.glob("*.yaml"):
        header = path.read_text(encoding="utf-8").split("\n\n", 1)[0]
        assert "documented in README.md, in the same folder" in header, path.name


def test_format_reference_has_examples():
    assert REFERENCE_EXAMPLES


@pytest.mark.parametrize(
    "example",
    REFERENCE_EXAMPLES,
    ids=[f"example{i}" for i in range(len(REFERENCE_EXAMPLES))],
)
def test_format_reference_examples_load(one_job_yaml_dir, example):
    """Every YAML example in the format reference loads with the reader."""
    instrument = re.search(r"outputs:\n +- source: (\w+)", example).group(1)
    (one_job_yaml_dir / f"imap_{instrument}_dependencies.yaml").write_text(example)
    reader = DependencyConfigReader(one_job_yaml_dir)
    jobs = re.findall(r"^\((\S+), (\S+)\):$", example, re.MULTILINE)
    assert jobs
    assert {(instrument, *job) for job in jobs} <= set(reader.config)
