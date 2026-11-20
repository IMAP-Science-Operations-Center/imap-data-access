"""Dependency configuration for IMAP SDC processing jobs.

This subpackage describes what each processing job reads and writes:

- :mod:`~imap_data_access.dependencies.nodes`: the node types for products,
  their dependencies and processing jobs, and how their fields are validated.
- :mod:`~imap_data_access.dependencies.map_windows`: the date ranges that ENA
  maps cover.
- :mod:`~imap_data_access.dependencies.config`: the reader that loads the
  dependency YAML files into those node types.
"""

from imap_data_access.dependencies.config import (
    DependencyConfigReader,
    clear_config_cache,
    get_kickoff_jobs,
)
from imap_data_access.dependencies.map_windows import (
    BaseENAMapPartition,
    Map1YrPartition,
    Map3MoPartition,
    Map6MoPartition,
    MapWindow,
    WindowBoundary,
)
from imap_data_access.dependencies.nodes import (
    DATE_RANGE_OPTIONS,
    NEAREST_OPTIONS,
    SPICE_SOURCES,
    DataSource,
    DataType,
    DependencyNode,
    Node,
    ProcessingJobNode,
)

__all__ = [
    "DATE_RANGE_OPTIONS",
    "NEAREST_OPTIONS",
    "SPICE_SOURCES",
    "BaseENAMapPartition",
    "DataSource",
    "DataType",
    "DependencyConfigReader",
    "DependencyNode",
    "Map1YrPartition",
    "Map3MoPartition",
    "Map6MoPartition",
    "MapWindow",
    "Node",
    "ProcessingJobNode",
    "WindowBoundary",
    "clear_config_cache",
    "get_kickoff_jobs",
]
