"""Tests for the CLI options."""

import sys
from unittest import mock

import pytest

from imap_data_access import cli


def test_cli_works():
    """Smoke test for the CLI module making sure it is callable."""
    with mock.patch.object(sys, "argv", ["imap-data-access", "-h"]):
        # Should have a 0 SystemExit return code if successful
        with pytest.raises(SystemExit, match="0"):
            cli.main()
