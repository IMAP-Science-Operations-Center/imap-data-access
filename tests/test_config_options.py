"""Tests for the various configs that a user can set."""
# ruff: noqa: S603
# subprocess call: check for execution of untrusted input

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("config_var", "default", "expected"),
    [
        ("DATA_DIR", Path.cwd() / "data", str(Path("/test/path"))),
        ("DATA_ACCESS_URL", "https://api.dev.imap-mission.com", "https://test.url"),
        ("API_KEY", None, "test-api-key"),
    ],
)
def test_configuration_updates(config_var, default, expected):
    """Test that the configurations get applied correctly.

    testing the default first, and then setting the environment
    variable explicitly.
    """
    command = [
        sys.executable,
        "-c",
        f"import imap_data_access; print(imap_data_access.config['{config_var}'])",
    ]
    # Default case
    proc = subprocess.run(
        command,
        capture_output=True,
        check=True,
        text=True,
    )
    assert proc.stdout.strip() == str(default)

    # Setting the environment variable should change the default
    # environment variables are preprended with IMAP_
    proc = subprocess.run(
        command,
        env={**os.environ, f"IMAP_{config_var}": expected},
        capture_output=True,
        check=True,
        text=True,
    )
    assert proc.stdout.strip() == expected
