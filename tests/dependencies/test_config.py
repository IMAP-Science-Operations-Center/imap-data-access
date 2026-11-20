"""Tests for the dependency YAML reader."""

import logging
import re

import pytest

import imap_data_access
from imap_data_access.dependencies import (
    DependencyConfigReader,
    DependencyNode,
    ProcessingJobNode,
    clear_config_cache,
    get_kickoff_jobs,
)

# The reader skips these instruments and raises if any other one has no file.
SKIPPED_INSTRUMENTS = {"ialirt", "l1const"}
INSTRUMENTS = sorted(imap_data_access.VALID_INSTRUMENTS - SKIPPED_INSTRUMENTS)


def _kickoff_job(instrument):
    """Return the YAML for a pipeline with one job, which reads the L0 data."""
    return f"""
(l1a, all):
  partition: daily
  inputs:
    - source: {instrument}
      data_type: l0
      descriptor: raw
  outputs:
    - source: {instrument}
      data_type: l1a
      descriptor: sci
      major_version: 1
"""


# Anchor groups, including one nested in another, and a date range.
HI_YAML = """
# Comments at the top, as in the real files.

spice_basic: &spice_basic
  - source: leapseconds
    data_type: spice
    descriptor: historical
    trigger_job: false
  - source: spacecraft_clock
    data_type: spice
    descriptor: historical
    trigger_job: false

spice_l1b: &spice_l1b
  - *spice_basic
  - source: imap_frames
    data_type: spice
    descriptor: historical
    trigger_job: false

(l1a, all):
  partition: repoint
  inputs:
    - source: hi
      data_type: l0
      descriptor: raw
    - *spice_basic
  outputs:
    - source: hi
      data_type: l1a
      descriptor: 45sensor-de
      major_version: 1

(l1b, 45sensor-de):
  partition: repoint
  inputs:
    - *spice_l1b
    - source: hi
      data_type: l1a
      descriptor: 45sensor-de
  outputs:
    - source: hi
      data_type: l1b
      descriptor: 45sensor-de
      major_version: 1

(l1b, 45sensor-goodtimes):
  partition: repoint
  inputs:
    - *spice_l1b
    - source: hi
      data_type: l1b
      descriptor: 45sensor-de
      date_range: ["8np",]
  outputs:
    - source: hi
      data_type: l1b
      descriptor: 45sensor-goodtimes
      major_version: 1
"""

IDEX_YAML = """
(l1a, all):
  partition: 10d
  inputs:
    - source: idex
      data_type: l0
      descriptor: raw
  outputs:
    - source: idex
      data_type: l1a
      descriptor: sci-10days
      major_version: 1
    - source: idex
      data_type: l1a
      descriptor: msg-10days
      major_version: 1

(l1b, sci-10days):
  partition: 10d
  inputs:
    - source: idex
      data_type: l1a
      descriptor: sci-10days
  outputs:
    - source: idex
      data_type: l1b
      descriptor: sci-10days
      major_version: 1
"""

# Two jobs read the L0 data, as in the real SWAPI file.
SWAPI_YAML = """
(l1a, hk):
  partition: daily
  inputs:
    - source: swapi
      data_type: l0
      descriptor: raw
  outputs:
    - source: swapi
      data_type: l1a
      descriptor: hk
      major_version: 1

(l1, sci):
  partition: daily
  inputs:
    - source: swapi
      data_type: l0
      descriptor: raw
  outputs:
    - source: swapi
      data_type: l1
      descriptor: sci
      major_version: 1
"""

# Every kind of input, and fields left out so that they take their defaults.
SWE_YAML = """
(l1a, all):
  partition: daily
  inputs:
    - source: swe
      data_type: l0
      descriptor: raw
  outputs:
    - source: swe
      data_type: l1a
      descriptor: sci
      major_version: 1

(l1b, sci):
  partition: daily
  inputs:
    - source: swe
      data_type: l1a
      descriptor: sci
    - source: swe
      data_type: ancillary
      descriptor: esa-lut
      required: false
    - source: leapseconds
      data_type: spice
      descriptor: historical
      trigger_job: false
    - source: spin
      data_type: spin
      descriptor: historical
    - source: repoint
      data_type: repoint
      descriptor: historical
  outputs:
    - source: swe
      data_type: l1b
      descriptor: sci
      major_version: 2
    - source: swe
      data_type: l1b
      descriptor: hk
"""

# One product that several jobs read.
ULTRA_YAML = """
(l1a, all):
  partition: daily
  inputs:
    - source: ultra
      data_type: l0
      descriptor: raw
  outputs:
    - source: ultra
      data_type: l1a
      descriptor: 45sensor-de
      major_version: 1

(l1c, 45sensor-spacecraftpset):
  partition: repoint
  inputs:
    - source: ultra
      data_type: l1a
      descriptor: 45sensor-de
  outputs:
    - source: ultra
      data_type: l1c
      descriptor: 45sensor-spacecraftpset
      major_version: 1
""" + "".join(
    f"""
(l2, u45-ena-h-sf-nsp-full-hae-4deg-{cadence}):
  partition: {cadence}
  inputs:
    - source: ultra
      data_type: l1c
      descriptor: 45sensor-spacecraftpset
  outputs:
    - source: ultra
      data_type: l2
      descriptor: u45-ena-h-sf-nsp-full-hae-4deg-{cadence}
      major_version: 1
"""
    for cadence in ("3mo", "6mo", "1yr")
)

FIXTURE_YAML = {instrument: _kickoff_job(instrument) for instrument in INSTRUMENTS}
FIXTURE_YAML.update(
    hi=HI_YAML, idex=IDEX_YAML, swapi=SWAPI_YAML, swe=SWE_YAML, ultra=ULTRA_YAML
)


def write_yaml_files(directory, **overrides):
    """Write a dependency YAML file for every instrument the reader loads.

    Each keyword names an instrument and gives the YAML to write for it instead
    of the fixture's, or None to leave its file out.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for instrument, content in {**FIXTURE_YAML, **overrides}.items():
        if content is not None:
            (directory / f"imap_{instrument}_dependencies.yaml").write_text(content)
    return directory


def _key(node):
    return (node.source, node.data_type, node.descriptor)


@pytest.fixture
def yaml_dir(tmp_path):
    """Directory holding the fixture's dependency YAML files."""
    return write_yaml_files(tmp_path / "dependencies")


def test_reads_every_job(yaml_dir):
    """Every job in every file is keyed by its instrument, data type and descriptor."""
    reader = DependencyConfigReader(yaml_dir)
    expected = {
        (instrument, data_type, descriptor)
        for instrument, content in FIXTURE_YAML.items()
        for data_type, descriptor in re.findall(
            r"^\((\S+), (\S+)\):$", content, re.MULTILINE
        )
    }
    assert set(reader.config) == expected
    for key, job in reader.config.items():
        assert isinstance(job, ProcessingJobNode)
        assert _key(job) == key


def test_skips_ialirt_and_l1const(yaml_dir):
    """The ialirt and l1const files are never read, even when they exist."""
    for instrument in SKIPPED_INSTRUMENTS:
        (yaml_dir / f"imap_{instrument}_dependencies.yaml").write_text("not: [yaml")
    reader = DependencyConfigReader(yaml_dir)
    assert not {source for source, _, _ in reader.config} & SKIPPED_INSTRUMENTS


def test_get_node_for_output(yaml_dir):
    """Test get_node_for_output."""
    reader = DependencyConfigReader(yaml_dir)
    node = reader.get_node_for_output(DependencyNode("idex", "l1a", "sci-10days"))
    # Check that the correct processingJobNode was returned.
    assert node.source == "idex"
    assert node.data_type == "l1a"
    assert node.descriptor == "all"


def test_get_node_for_output_invalid(yaml_dir):
    """Test get_node_for_output with non-existent dependency node."""
    reader = DependencyConfigReader(yaml_dir)
    # This DependencyNode does not exist in the dependency configuration,
    # so it should raise an error.
    with pytest.raises(ValueError, match="No job found that produces output"):
        reader.get_node_for_output(DependencyNode("idex", "l1a", "sci"))


def test_get_node_for_input(yaml_dir):
    """Test get_node_for_input."""
    reader = DependencyConfigReader(yaml_dir)
    nodes = reader.get_nodes_for_input(DependencyNode("idex", "l1a", "sci-10days"))
    # There should be only one node
    assert len(nodes) == 1
    # Check that the correct processingJobNode was returned.
    assert nodes[0].source == "idex"
    assert nodes[0].data_type == "l1b"
    assert nodes[0].descriptor == "sci-10days"


def test_get_node_for_input_invalid(yaml_dir):
    """Test get_node_for_input with non-existent dependency node."""
    reader = DependencyConfigReader(yaml_dir)
    # This DependencyNode does not exist in the dependency configuration,
    # so it should return an empty list
    node = reader.get_nodes_for_input(DependencyNode("idex", "l1a", "sci"))
    assert node == []


def test_get_nodes_for_input_many(yaml_dir):
    """Test get_node_for_input when there are multiple nodes."""
    reader = DependencyConfigReader(yaml_dir)
    # Ultra l1c spacecraft psets are the inputs to multiple jobs
    nodes = reader.get_nodes_for_input(
        DependencyNode("ultra", "l1c", "45sensor-spacecraftpset")
    )
    # There should be 3 nodes
    assert len(nodes) == 3


def test_input_and_output_defaults(yaml_dir):
    """Fields the YAML leaves out take the reader's defaults."""
    reader = DependencyConfigReader(yaml_dir)
    job = reader.config[("swe", "l1b", "sci")]
    science, ancillary, leapseconds, spin, repoint = job.inputs

    # Inputs are required and trigger the job unless the YAML says otherwise.
    assert (science.required, science.trigger_job) == (True, True)
    assert (ancillary.required, ancillary.trigger_job) == (False, True)
    assert (leapseconds.required, leapseconds.trigger_job) == (True, False)
    # With no date_range, the time range is empty.
    assert science.dependency_query_time_range == []
    # With no major_version, it's None rather than the class default of 1.
    assert science.major_version is None

    sci, hk = job.outputs
    # Outputs aren't required unless the YAML says so, and they trigger jobs.
    assert (sci.required, sci.trigger_job, sci.major_version) == (False, True, 2)
    assert (hk.required, hk.trigger_job, hk.major_version) == (False, True, None)

    # The job sorts its inputs by kind.
    assert job.science_inputs == [science]
    assert job.ancillary_inputs == [ancillary]
    assert job.spice_inputs == [leapseconds]
    assert job.spin_input is spin
    assert job.repoint_input is repoint
    assert reader.partition(("swe", "l1b", "sci")) == "daily"


def test_date_range_becomes_query_time_range(yaml_dir):
    reader = DependencyConfigReader(yaml_dir)
    de_input = reader.inputs(("hi", "l1b", "45sensor-goodtimes"))[-1]
    assert _key(de_input) == ("hi", "l1b", "45sensor-de")
    assert de_input.dependency_query_time_range == ["8np"]


def test_yaml_anchors_and_nested_lists(yaml_dir):
    """Anchor groups aren't jobs, and anchors nested in lists are flattened."""
    reader = DependencyConfigReader(yaml_dir)
    assert {key for key in reader.config if key[0] == "hi"} == {
        ("hi", "l1a", "all"),
        ("hi", "l1b", "45sensor-de"),
        ("hi", "l1b", "45sensor-goodtimes"),
    }
    assert [_key(node) for node in reader.inputs(("hi", "l1a", "all"))] == [
        ("hi", "l0", "raw"),
        ("leapseconds", "spice", "historical"),
        ("spacecraft_clock", "spice", "historical"),
    ]
    assert [
        _key(node) for node in reader.inputs(("hi", "l1b", "45sensor-goodtimes"))
    ] == [
        ("leapseconds", "spice", "historical"),
        ("spacecraft_clock", "spice", "historical"),
        ("imap_frames", "spice", "historical"),
        ("hi", "l1b", "45sensor-de"),
    ]


def test_recursive_flatten_list(yaml_dir):
    reader = DependencyConfigReader(yaml_dir)
    a, b, c, d = ({"source": name} for name in "abcd")
    assert reader.recursive_flatten_list([a, [b, [c, [d]]], []]) == [a, b, c, d]


@pytest.mark.parametrize("outputs", ["", "  outputs:\n"], ids=["absent", "empty"])
def test_job_without_partition_or_outputs(tmp_path, outputs):
    glows_yaml = """
(l1a, all):
  inputs:
    - source: glows
      data_type: l0
      descriptor: raw
"""
    reader = DependencyConfigReader(
        write_yaml_files(tmp_path, glows=glows_yaml + outputs)
    )
    assert reader.partition(("glows", "l1a", "all")) is None
    assert reader.outputs(("glows", "l1a", "all")) == []


def test_missing_file(tmp_path):
    yaml_dir = write_yaml_files(tmp_path, swe=None)
    with pytest.raises(FileNotFoundError, match="not found for 'swe'"):
        DependencyConfigReader(yaml_dir)


@pytest.mark.parametrize("content", ["", "# Only a comment\n"])
def test_empty_file(tmp_path, content):
    yaml_dir = write_yaml_files(tmp_path, swe=content)
    with pytest.raises(ValueError, match="Dependency content is empty for 'swe'"):
        DependencyConfigReader(yaml_dir)


@pytest.mark.parametrize("key", ["(l1b)", "(l1b, )", "(l9z, sci)"])
def test_malformed_key(tmp_path, key):
    yaml_dir = write_yaml_files(tmp_path, swe=SWE_YAML.replace("(l1b, sci)", key))
    with pytest.raises(ValueError, match=re.escape(f"Non-product key error: '{key}'")):
        DependencyConfigReader(yaml_dir)


def test_invalid_input_names_its_job(tmp_path):
    swe_yaml = SWE_YAML.replace("source: spin", "source: not-a-source")
    yaml_dir = write_yaml_files(tmp_path, swe=swe_yaml)
    with pytest.raises(
        ValueError,
        match=r"Non-product key error: '\(l1b, sci\)'.*'not-a-source'",
    ):
        DependencyConfigReader(yaml_dir)


def test_cache_is_per_directory(tmp_path):
    key = ("swe", "l1b", "sci")
    first_dir = write_yaml_files(tmp_path / "first")
    second_dir = write_yaml_files(
        tmp_path / "second",
        swe=SWE_YAML.replace("major_version: 2", "major_version: 3"),
    )

    first = DependencyConfigReader(first_dir)
    # A second reader for the same directory reuses the loaded configuration.
    assert DependencyConfigReader(first_dir).config is first.config
    # Another directory is loaded and cached separately.
    second = DependencyConfigReader(second_dir)
    assert second.config is not first.config
    assert second.outputs(key)[0].major_version == 3
    assert DependencyConfigReader(first_dir).outputs(key)[0].major_version == 2


def test_cache_ignores_file_changes_until_cleared(yaml_dir):
    key = ("swe", "l1b", "sci")
    first = DependencyConfigReader(yaml_dir)
    (yaml_dir / "imap_swe_dependencies.yaml").write_text(
        SWE_YAML.replace("major_version: 2", "major_version: 3")
    )
    # The directory is already cached, so the change isn't seen...
    assert DependencyConfigReader(yaml_dir).config is first.config
    assert DependencyConfigReader(yaml_dir).outputs(key)[0].major_version == 2
    # ...until the cache is cleared.
    clear_config_cache()
    assert DependencyConfigReader(yaml_dir).outputs(key)[0].major_version == 3


def test_get_kickoff_jobs(yaml_dir):
    """A kickoff job is any job that reads an instrument's L0 raw data."""
    reader = DependencyConfigReader(yaml_dir)
    jobs = get_kickoff_jobs(reader=reader)
    expected = {(instrument, "l1a", "all") for instrument in INSTRUMENTS}
    expected = (expected - {("swapi", "l1a", "all")}) | {
        ("swapi", "l1a", "hk"),
        ("swapi", "l1", "sci"),
    }
    assert sorted(_key(job) for job in jobs) == sorted(expected)


def test_get_kickoff_jobs_for_instrument(yaml_dir):
    reader = DependencyConfigReader(yaml_dir)
    assert get_kickoff_jobs("swe", reader) == [reader.config[("swe", "l1a", "all")]]


def test_get_kickoff_jobs_returns_first_job_only(yaml_dir):
    """For an instrument with two kickoff jobs, only the first in its file."""
    reader = DependencyConfigReader(yaml_dir)
    assert get_kickoff_jobs("swapi", reader) == [reader.config[("swapi", "l1a", "hk")]]


def test_get_kickoff_jobs_instrument_without_any(yaml_dir):
    """An instrument with no kickoff job gets every instrument's kickoff jobs.

    This pins current behavior rather than endorsing it: a caller can't tell
    this result apart from a match.
    """
    reader = DependencyConfigReader(yaml_dir)
    assert get_kickoff_jobs("ialirt", reader) == get_kickoff_jobs(reader=reader)


def test_get_kickoff_jobs_none_found(tmp_path, caplog):
    no_l0_inputs = {
        instrument: _kickoff_job(instrument).replace("l0", "l1a")
        for instrument in INSTRUMENTS
    }
    reader = DependencyConfigReader(write_yaml_files(tmp_path, **no_l0_inputs))
    with caplog.at_level(logging.INFO, logger="imap_data_access.dependencies"):
        assert get_kickoff_jobs(reader=reader) == []
    assert "No kickoff jobs found" in caplog.text
