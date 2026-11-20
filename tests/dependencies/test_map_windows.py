"""Tests for the ENA map windows."""

from datetime import datetime, timezone

import pytest

from imap_data_access.dependencies import (
    Map1YrPartition,
    Map3MoPartition,
    Map6MoPartition,
    MapWindow,
)

_CADENCE_TYPES = {
    "3mo": Map3MoPartition,
    "6mo": Map6MoPartition,
    "1yr": Map1YrPartition,
}

FIRST_MAP_START_DATE = datetime(2024, 12, 25, tzinfo=timezone.utc)


def _utc(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)


#### Test for BaseENAMapPartition class #####


@pytest.mark.parametrize("cadence_str", ["3mo", "6mo", "1yr"])
def test_get_current_windows(cadence_str):
    """Test that the get_current_windows method returns the correct window."""
    cadence_type = _CADENCE_TYPES.get(cadence_str)
    current_time = datetime(2026, 1, 10, tzinfo=timezone.utc)
    window = cadence_type(current_time).get_current_window()
    assert isinstance(window, MapWindow)
    assert window.cadence == cadence_str
    # The current_time is between a year rollover
    # Ensure that the start year is 2025 and the end year is 2026
    assert window.start.year == 2025
    assert window.end.year == 2026
    assert window.start < current_time <= window.end


@pytest.mark.parametrize("cadence_str", ["3mo", "6mo", "1yr"])
def test_get_windows_since(cadence_str):
    """Test that the get_windows_since method returns the correct windows."""
    cadence_type = _CADENCE_TYPES.get(cadence_str)
    current_time = datetime(2026, 1, 10, tzinfo=timezone.utc)
    # get all the windows since the first map through the current time
    windows = cadence_type(current_time).get_windows_since(FIRST_MAP_START_DATE)
    # The first window should always start on dec 25th 2024
    assert windows[0].start == datetime(2024, 12, 25, tzinfo=timezone.utc)

    # The last window should be through the next year
    assert windows[-1].end.year == 2027

    for window in windows:
        assert window.cadence == cadence_str
        # The start and end should always fall on the 25th of whatever month
        assert window.start.day == 25
        assert window.end.day == 25


@pytest.mark.parametrize(
    ("cadence_type", "boundaries"),
    [
        (
            Map3MoPartition,
            [
                _utc(2024, 12, 25),
                _utc(2025, 3, 25),
                _utc(2025, 6, 25),
                _utc(2025, 9, 25),
                _utc(2025, 12, 25),
            ],
        ),
        (Map6MoPartition, [_utc(2024, 12, 25), _utc(2025, 6, 25), _utc(2025, 12, 25)]),
        (Map1YrPartition, [_utc(2024, 12, 25), _utc(2025, 12, 25)]),
    ],
)
def test_get_windows(cadence_type, boundaries):
    """A year of windows runs from Dec 25 to the next Dec 25, without gaps."""
    windows = cadence_type(_utc(2025, 1, 1)).get_windows(2024)
    assert [(window.start, window.end) for window in windows] == list(
        zip(boundaries[:-1], boundaries[1:])
    )


def test_to_partition_name():
    window = MapWindow("3mo", _utc(2024, 12, 25), _utc(2025, 3, 25))
    assert (
        window.to_partition_name()
        == "cadence-3mo_2024-12-25T00:00:00_to_2025-03-25T00:00:00"
    )
