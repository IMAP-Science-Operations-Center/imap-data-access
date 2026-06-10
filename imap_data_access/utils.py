"""Utility classes and enums for IMAP Data Access."""

from enum import Enum


class ReleaseType(Enum):
    """Enum for release types."""

    RELEASE = "release"
    EARLY_RELEASE = "early-release"
    UNRELEASE = "unrelease"
    REPROCESS = "reprocess"
