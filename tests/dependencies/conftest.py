"""Shared fixtures for the dependency configuration tests."""

import pytest

from imap_data_access.dependencies import clear_config_cache


@pytest.fixture(autouse=True)
def _clear_dependency_cache():
    """Start and end every test with an empty configuration cache."""
    clear_config_cache()
    yield
    clear_config_cache()
