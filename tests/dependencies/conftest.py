"""Shared fixtures for the dependency configuration tests."""

import pytest

import imap_data_access
from imap_data_access.dependencies import clear_config_cache


@pytest.fixture(autouse=True)
def _clear_dependency_cache():
    """Start and end every test with an empty configuration cache."""
    clear_config_cache()
    yield
    clear_config_cache()


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
def one_job_yaml_dir(tmp_path):
    """A one-job dependency YAML file for every instrument, for a test to replace.

    The reader needs a file for every instrument, so a test that's about one
    instrument can start from these and overwrite that instrument's file.
    """
    for instrument in imap_data_access.VALID_INSTRUMENTS - {"ialirt", "l1const"}:
        (tmp_path / f"imap_{instrument}_dependencies.yaml").write_text(
            _one_job(instrument)
        )
    return tmp_path
