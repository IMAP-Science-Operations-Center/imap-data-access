"""Tests for validating the major versions in the dependency YAML files."""

import pytest

import imap_data_access
from imap_data_access.dependencies import DependencyConfigReader, get_kickoff_jobs
from imap_data_access.dependencies.validation import (
    validate_dependency_yaml_versions,
    validate_dependency_yamls,
)

# Idex l1b sci-10days (downstream) has a major_version greater than or equal to
# its upstream input, idex l1a sci-10days. This is valid.
IDEX_VALID_YAML = """
(l1a, all):
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
      descriptor: catlst-10days
      major_version: 1
    - source: idex
      data_type: l1b
      descriptor: catlst-10days
      major_version: 1
    - source: idex
      data_type: l1a
      descriptor: msg-10days
      major_version: 1

(l1b, sci-10days):
  inputs:
    - source: idex
      data_type: l1a
      descriptor: sci-10days
  outputs:
    - source: idex
      data_type: l1b
      descriptor: sci-10days
      major_version: 2
    - source: idex
      data_type: l1b
      descriptor: msg-10days
      major_version: 1

"""

# Idex l1a sci-10days now has a greater major version than idex l1b
# sci-10 days (downstream) this is invalid.
IDEX_INVALID_YAML = IDEX_VALID_YAML.replace(
    "data_type: l1b\n      descriptor: sci-10days\n      major_version: 2",
    "data_type: l1b\n      descriptor: sci-10days\n      major_version: 0",
)

# Idex l1a catlst-10days now has a greater major version than idex l1b catlst. Since
# they have the same descriptor, the major_versions are required to match
IDEX_INVALID_CATLST_YAML = IDEX_VALID_YAML.replace(
    "data_type: l1b\n      descriptor: catlst-10days\n      major_version: 1",
    "data_type: l1b\n      descriptor: catlst-10days\n      major_version: 2",
)
# A minimal mag chain (l1a -> l2), starting at major_version 1. The
# cross-instrument dependent lives in SWAPI_VALID_YAML below - a job's source
# always comes from the file it's defined in (see
# DependencyConfigReader._load_all_dependencies), never from its
# "outputs.source", so it can't live here.
_MAG_VALID_YAML = """
(l1a, all):
  inputs:
    - source: mag
      data_type: l0
      descriptor: raw
  outputs:
    - source: mag
      data_type: l1a
      descriptor: norm-magi
      major_version: 1

(l2, norm-srf):
  inputs:
    - source: mag
      data_type: l1a
      descriptor: norm-magi
  outputs:
    - source: mag
      data_type: l2
      descriptor: norm-rtn
      major_version: 1

"""

# Bump mag l2 norm-rtn ahead of swapi l3a alpha-sw (still major_version 1 in
# SWAPI_VALID_YAML below), to check that a cross-instrument dependent doesn't
# get validated against it.
MAG_VALID_YAML_L2_BUMP = _MAG_VALID_YAML.replace(
    "data_type: l2\n      descriptor: norm-rtn\n      major_version: 1",
    "data_type: l2\n      descriptor: norm-rtn\n      major_version: 2",
)

# swapi l3a alpha-sw depends on mag l2 norm-rtn - a real cross-instrument
# dependency (see imap_swapi_dependencies.yaml).
SWAPI_VALID_YAML = """

(l3a, alpha-sw):
  inputs:
    - source: mag
      data_type: l2
      descriptor: norm-rtn
  outputs:
    - source: swapi
      data_type: l3a
      descriptor: alpha-sw
      major_version: 1

"""
# This YAML is now invalid because the job node data_level is l3a and the output is
# l3b. It is required that at least one output product shares a data_level with the
# job node.
SWAPI_INVALID_YAML = SWAPI_VALID_YAML.replace(
    "data_type: l3a\n      descriptor: alpha-sw",
    "data_type: l3b\n      descriptor: alpha-sw",
)
# A minimal, static swe chain (l1a -> l1b -> l2 -> l3), all starting at
# major_version 1.
_SWE_VALID_YAML = """
(l1a, all):
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
  inputs:
    - source: swe
      data_type: l1a
      descriptor: sci
  outputs:
    - source: swe
      data_type: l1b
      descriptor: sci
      major_version: 1

(l2, sci):
  inputs:
    - source: swe
      data_type: l1b
      descriptor: sci
  outputs:
    - source: swe
      data_type: l2
      descriptor: sci
      major_version: 1

(l3, sci):
  inputs:
    - source: swe
      data_type: l2
      descriptor: sci
  outputs:
    - source: swe
      data_type: l3
      descriptor: sci
      major_version: 1

"""

# Bump each level's major_version by a different, increasing amount to exercise
# a real multi-hop monotonic chain.
SWE_VALID_YAML_BUMPED = (
    _SWE_VALID_YAML.replace(
        "data_type: l1b\n      descriptor: sci\n      major_version: 1",
        "data_type: l1b\n      descriptor: sci\n      major_version: 5",
    )
    .replace(
        "data_type: l2\n      descriptor: sci\n      major_version: 1",
        "data_type: l2\n      descriptor: sci\n      major_version: 7",
    )
    .replace(
        "data_type: l3\n      descriptor: sci\n      major_version: 1",
        "data_type: l3\n      descriptor: sci\n      major_version: 10",
    )
)


def _one_job(instrument):
    """Return the YAML for a pipeline with one job, which reads the L0 data."""
    return f"""
(l1a, all):
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


@pytest.fixture
def yaml_dir(tmp_path):
    """A one-job YAML file for every instrument, for a test to replace.

    The reader needs a file for every instrument, but validation only follows
    one instrument's pipeline at a time, so the other files can be minimal.
    """
    for instrument in imap_data_access.VALID_INSTRUMENTS - {"ialirt", "l1const"}:
        (tmp_path / f"imap_{instrument}_dependencies.yaml").write_text(
            _one_job(instrument)
        )
    return tmp_path


def reader_with(yaml_dir, **instrument_yaml):
    """Return a reader for yaml_dir, with the given instruments' YAML replaced."""
    for instrument, content in instrument_yaml.items():
        (yaml_dir / f"imap_{instrument}_dependencies.yaml").write_text(content)
    return DependencyConfigReader(yaml_dir)


def test_validate_dependency_yaml_versions_invalid(yaml_dir, caplog):
    """Yaml with one invalid downstream major_version should log a warning."""
    reader = reader_with(yaml_dir, idex=IDEX_INVALID_YAML)
    kickoff_job = reader.config[("idex", "l1a", "all")]

    validate_dependency_yaml_versions(reader, kickoff_job)
    assert (
        "Output (idex, l1b, sci-10days) has major_version 0. "
        "It should be greater than or equal to 1"
    ) in caplog.text


def test_validate_dependency_yaml_versions_valid(yaml_dir):
    """Idex yaml content should pass."""
    reader = reader_with(yaml_dir, idex=IDEX_VALID_YAML)
    kickoff_job = reader.config[("idex", "l1a", "all")]

    # Should not raise.
    validate_dependency_yaml_versions(reader, kickoff_job)


def test_validate_dependency_yaml_versions_mag_l2(yaml_dir):
    """Bumping mag l2 norm-rtn should pass, even though swapi depends on it.

    validate_dependency_yaml_versions only walks downstream jobs within the same
    source (see the `processing_node.source != node.source` check), so swapi's
    l3a alpha-sw job - a real cross-instrument dependent of mag l2 norm-rtn -
    should never be checked or cause this to raise.
    """
    reader = reader_with(yaml_dir, mag=MAG_VALID_YAML_L2_BUMP, swapi=SWAPI_VALID_YAML)
    kickoff_job = reader.config[("mag", "l1a", "all")]

    # Should not raise, per the docstring above.
    validate_dependency_yaml_versions(reader, kickoff_job)


def test_validate_dependency_yaml_versions_swe(yaml_dir):
    """A static swe chain, with a monotonic version bump per level, should pass."""
    reader = reader_with(yaml_dir, swe=SWE_VALID_YAML_BUMPED)
    kickoff_job = reader.config[("swe", "l1a", "all")]

    # Should not raise.
    validate_dependency_yaml_versions(reader, kickoff_job)


def test_validate_dependency_yaml_invalid_idex_catlst_products(yaml_dir):
    """Check that outputs sharing a descriptor with different major versions raise."""
    reader = reader_with(yaml_dir, idex=IDEX_INVALID_CATLST_YAML)
    kickoff_job = reader.config[("idex", "l1a", "all")]

    # IDEX_INVALID_CATLST_YAML is invalid; outputs sharing a descriptor must
    # share the same major_version.
    error_msg = (
        "All outputs with identical descriptors should have the same major versions"
    )
    with pytest.raises(ValueError, match=error_msg):
        validate_dependency_yaml_versions(reader, kickoff_job)


def test_validate_dependency_yaml_invalid_data_levels(yaml_dir):
    """Check that an error is thrown when no output shares the job node's data level."""
    reader = reader_with(yaml_dir, swapi=SWAPI_INVALID_YAML)
    kickoff_job = reader.config[("swapi", "l3a", "alpha-sw")]

    error_msg = "At least one output must have the same data level as the job node"
    with pytest.raises(ValueError, match=error_msg):
        validate_dependency_yaml_versions(reader, kickoff_job)


def test_validate_dependency_yaml_versions_without_a_node():
    assert validate_dependency_yaml_versions(None, None) is None


def test_packaged_yaml_is_valid(capsys):
    """The dependency YAML files that ship with imap-data-access are valid."""
    validate_dependency_yamls()
    assert capsys.readouterr().out.splitlines() == [
        f"Validated the {job.source} dependency YAML file" for job in get_kickoff_jobs()
    ]


def test_validate_dependency_yamls_invalid(yaml_dir, capsys):
    reader = reader_with(yaml_dir, idex=IDEX_INVALID_CATLST_YAML)
    with pytest.raises(ValueError, match="identical descriptors"):
        validate_dependency_yamls(reader)
    assert "Invalid dependency file for idex." in capsys.readouterr().out
