"""Utility classes and enums for IMAP Data Access."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path


class ReleaseType(Enum):
    """Enum for release types."""

    RELEASE = "release"
    EARLY_RELEASE = "early-release"
    UNRELEASE = "unrelease"


class ImapProductCatalog:
    """Provides structured lookups into the IMAP product hierarchy JSON.

    The hierarchy JSON has two top-level sections:

    ``science``
        Maps  instrument -> data_level -> [descriptor, ...]

    ``ancillary``
        Maps  instrument -> [descriptor, ...]

    Examples
    --------
    >>> pc = ImapProductCatalog()
    >>> pc.data_levels()                            # all unique levels
    >>> pc.data_levels("mag")                       # levels for mag
    >>> pc.science_descriptors("mag", "l2")         # science descriptors for mag l2
    >>> pc.ancillary_descriptors("hit")             # ancillary descriptors for hit
    """

    def __init__(
        self,
    ) -> None:
        """Load and format dictionary for easier lookup."""
        config_file = Path(__file__).parent / "imap_products_hierarchy.json"
        with open(config_file, encoding="utf-8") as fp:
            hierarchy = json.load(fp)
        science_raw: dict[str, dict[str, list[str]]] = dict(
            hierarchy.get("science", {})
        )

        # science: instrument -> data_level -> frozenset of descriptors
        self._science: dict[str, dict[str, frozenset[str]]] = {
            instrument: {
                level: frozenset(descriptors) for level, descriptors in levels.items()
            }
            for instrument, levels in science_raw.items()
        }

        # ancillary: instrument -> frozenset of descriptors
        self._ancillary: dict[str, frozenset[str]] = {
            instrument: frozenset(descriptors)
            for instrument, descriptors in hierarchy.get("ancillary", {}).items()
        }

        # pre-build the mission-wide level set (immutable)
        self._all_levels: frozenset[str] = frozenset(
            level for levels in self._science.values() for level in levels
        )

    def data_levels(self, instrument: str | None = None) -> tuple[str, ...]:
        """Return sorted unique data levels for the mission or one instrument.

        Parameters
        ----------
        instrument : str, optional
            When omitted, returns all unique levels across every instrument.
        """
        if instrument is None:
            return tuple(sorted(self._all_levels))
        return tuple(sorted(self._science.get(instrument, {})))

    def science_descriptors(
        self,
        instrument: str,
        data_level: str | None = None,
    ) -> tuple[str, ...]:
        """Return sorted descriptors for an instrument, optionally filtered by level.

        Parameters
        ----------
        instrument : str
            Instrument name (e.g. ``"mag"``).
        data_level : str, optional
            When omitted, returns all descriptors across every level for the instrument.
        """
        instrument_levels = self._science.get(instrument, {})
        if data_level is None:
            return tuple(
                sorted(
                    {
                        d
                        for descriptors in instrument_levels.values()
                        for d in descriptors
                    }
                )
            )
        return tuple(sorted(instrument_levels.get(data_level, frozenset())))

    def ancillary_descriptors(self, instrument: str) -> tuple[str, ...]:
        """Return sorted ancillary descriptor names for an instrument.

        Parameters
        ----------
        instrument : str
            Instrument name (e.g. ``"hit"``).
        """
        return tuple(sorted(self._ancillary.get(instrument, frozenset())))
