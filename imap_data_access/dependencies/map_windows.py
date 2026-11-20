"""ENA map windows: the date ranges that 3-month, 6-month and 1-year maps cover.

Every window starts and ends on the 25th of a month, and each year of windows
starts on December 25, so that maps line up with those from IBEX, IMAP's
predecessor mission.
"""

import datetime
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class MapWindow:
    """Represent an ENA map cadence window with explicit date range.

    Parameters
    ----------
    cadence: str
        cadence string, e.g. "3mo", "6mo", "1yr"
    start: datetime.datetime
        start datetime for the window, e.g. "2024-01-01T00:00:00"
    end: datetime.datetime
        end datetime for the window, e.g. "2024-04-01T00:00:00"
    """

    cadence: str
    start: datetime.datetime
    end: datetime.datetime

    def to_partition_name(self) -> str:
        """Convert this window to a partition key string."""
        start_str = self.start.strftime("%Y-%m-%dT%H:%M:%S")
        end_str = self.end.strftime("%Y-%m-%dT%H:%M:%S")
        return f"cadence-{self.cadence}_{start_str}_to_{end_str}"


@dataclass(frozen=True)
class WindowBoundary:
    """A (month, day) boundary point for a map window.

    Parameters
    ----------
    month: int
        Month of the boundary (1-12). Eg. 1 for January, etc.
    day: int
        Day of the month (1-31, depending on month)
    """

    month: int
    day: int

    def to_datetime(self, year: int) -> datetime.datetime:
        """Convert to a datetime for the given year."""
        return datetime.datetime(
            year, self.month, self.day, tzinfo=datetime.timezone.utc
        )


class BaseENAMapPartition:
    """Base class for defining ENA map partition windows.

    This class provides common utilities for map jobs to determine the
    current map window or retrieve all windows for a given cadence. Map
    windows are used to construct cadence-based partition names.

    It also provides methods to get all windows for a cadence or determine
    the active window based on the current time. These allow the
    orchestration code to dynamically determine which map
    partition name to use when starting a map job.
    """

    cadence: ClassVar[str]
    # Define the map windows for the cadence using WindowBoundary.
    boundaries: ClassVar[tuple[WindowBoundary, ...]]

    def __init__(self, current_time: datetime.datetime):
        """Initialize the cadence period with the current time."""
        self.current_time = current_time

    def get_windows(self, year: int | None = None) -> list[MapWindow]:
        """Build all configured windows for the cadence type.

        Based on the current time's year, generate cadence windows
        for the cadence. The windows start on Dec 25 of the given year
        and run through Dec 25 of the next year. Eg.
            - For 3mo cadence, it will generate 4 windows:
                - Dec 25 to Mar 25 of the next year
                - Mar 25 to Jun 25 of the next year
                - Jun 25 to Sept 25 of the next year
                - Sept 25 to Dec 25 of the next year
            - For 6mo cadence, it will generate 2 windows:
                - Dec 25 to Jun 25 of the next year
                - Jun 25 to Dec 25 of the next year
            - For 1yr cadence, it will generate 1 window:
                - Dec 25 to Dec 25 of the next year
        """
        windows: list[MapWindow] = []
        year = self.current_time.year if year is None else year

        for i in range(len(self.boundaries) - 1):
            start_boundary = self.boundaries[i]
            end_boundary = self.boundaries[i + 1]

            # Handle year rollover. A window rolls into the next year if the end
            # boundary falls at or before the start boundary within the calendar
            # year (e.g., Oct -> Jan). Equality (e.g., Dec 25 -> Dec 25 for the
            # 1yr cadence) also means "next year", since a window can never be
            # zero-length.
            start_point = (start_boundary.month, start_boundary.day)
            end_point = (end_boundary.month, end_boundary.day)
            end_year = year if end_point > start_point else year + 1

            windows.append(
                MapWindow(
                    cadence=self.cadence,
                    start=start_boundary.to_datetime(year),
                    end=end_boundary.to_datetime(end_year),
                )
            )
            # Update year to be end_year in the case of a year rollover.
            year = end_year
        return windows

    def get_windows_since(self, since_time: datetime.datetime) -> list[MapWindow]:
        """Return all windows since the given time through the current year."""
        windows: list[MapWindow] = []
        for year in range(since_time.year - 1, self.current_time.year + 1):
            windows.extend(self.get_windows(year))

        # Drop windows that ended at or before since_time.
        return [wind for wind in windows if wind.end > since_time]

    def get_current_window(self) -> MapWindow | None:
        """Return the active map window for current_time.

        Active window is defined relative to the current time.
        For example, if current time is June 1, 2025 and cadence
        is 3mo, the active window would be the one that starts
        on March 26, 2025 and ends on June 25, 2025. Similarly, for
        6mo or 1yr cadence.
        """
        # Get windows from the previous year in case of a rollover.
        previous_year_windows = self.get_windows(self.current_time.year - 1)
        for window in self.get_windows() + previous_year_windows:
            if window.start <= self.current_time < window.end:
                return window
        return None


class Map3MoPartition(BaseENAMapPartition):
    """3-month map partitions."""

    cadence: ClassVar[str] = "3mo"
    # These boundaries are used to construct the 3-month maps windows:
    #     First partition can be 91 days(or 92 days on leap year).
    #     "cadence_3mo_{year}-12-25T00:00:00_to_{year+1}-03-25T00:00:00",
    #     Next two partition are always 91 days.
    #     "cadence_3mo_{year+1}-03-25T00:00:00_to_{year+1}-06-25T00:00:00",
    #     "cadence_3mo_{year+1}-06-25T00:00:00_to_{year+1}-09-25T00:00:00",
    #     Last partition is always 92 days.
    #     "cadence_3mo_{year+1}-09-25T00:00:00_to_{year+1}-12-25T00:00:00"
    boundaries: ClassVar[tuple[WindowBoundary, ...]] = (
        WindowBoundary(12, 25),  # Dec 25
        WindowBoundary(3, 25),  # March 25 (next year)
        WindowBoundary(6, 25),  # June 25 (next year)
        WindowBoundary(9, 25),  # Sept 25 (next year)
        WindowBoundary(12, 25),  # Dec 25 (next year - marks end of last window)
    )


class Map6MoPartition(BaseENAMapPartition):
    """6-month map partitions."""

    cadence: ClassVar[str] = "6mo"
    # These boundaries are used to construct the 6-month maps windows:
    #     First partition can be 182 days(or 183 days on leap year).
    #     "cadence_6mo_{year}-12-25T00:00:00_to_{year+1}-06-25T00:00:00",
    #     Last partition is always 183 days.
    #     "cadence_6mo_{year+1}-06-25T00:00:00_to_{year+1}-12-25T00:00:00
    boundaries: ClassVar[tuple[WindowBoundary, ...]] = (
        WindowBoundary(12, 25),  # Dec 25
        WindowBoundary(6, 25),  # June 25 (next year)
        WindowBoundary(12, 25),  # Dec 25 (next year)
    )


class Map1YrPartition(BaseENAMapPartition):
    """1-year map partitions."""

    cadence: ClassVar[str] = "1yr"
    # This boundary is used to construct the 1-year map window:
    #     "cadence_1yr_{year}-12-25T00:00:00_to_{year+1}-12-25T00:00:00
    boundaries: ClassVar[tuple[WindowBoundary, ...]] = (
        WindowBoundary(12, 25),  # Dec 25
        WindowBoundary(12, 25),  # Dec 25 (next year)
    )
