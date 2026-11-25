"""Dependency configuration for IMAP SDC processing jobs.

This subpackage describes what each processing job reads and writes:

- :mod:`~imap_data_access.dependencies.nodes`: the node types for products,
  their dependencies and processing jobs, and how their fields are validated.
- :mod:`~imap_data_access.dependencies.map_windows`: the date ranges that ENA
  maps cover.
- :mod:`~imap_data_access.dependencies.config`: the reader that loads the
  dependency YAML files into those node types.
- :mod:`~imap_data_access.dependencies.validation`: checks that the major
  versions in the dependency YAML files are consistent.

The dependency YAML files, one per instrument, ship with this package in
:data:`DEPENDENCY_CONFIG_DIR`, together with the IDEX 10-day window CSV.
"""

from imap_data_access.dependencies.config import (
    DEPENDENCY_CONFIG_DIR,
    IDEX_10_DAY_RANGES_PATH,
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
    "DEPENDENCY_CONFIG_DIR",
    "IDEX_10_DAY_RANGES_PATH",
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
