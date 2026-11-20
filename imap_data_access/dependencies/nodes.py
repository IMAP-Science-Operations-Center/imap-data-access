"""Types describing data products and the dependencies between them.

A :class:`ProcessingJobNode` describes one processing job: the products it reads
(its inputs), the products it writes (its outputs) and how its runs are
partitioned. Each input and output is a :class:`DependencyNode`.
:class:`~imap_data_access.dependencies.config.DependencyConfigReader` builds these
from the dependency YAML files.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar

import imap_data_access

# Date range validation constants
NEAREST_OPTIONS = ("nd", "np")
DATE_RANGE_OPTIONS = ("p", "h", "d", "l", *NEAREST_OPTIONS)

# SPICE file types that can be a dependency source, in metakernel load order.
# Keep this in step with the kernel types the SDC metakernel builder supports;
# a test in sds-data-manager checks that the two lists match.
SPICE_SOURCES = (
    "leapseconds",
    "planetary_constants",
    "imap_frames",
    "science_frames",
    "spacecraft_clock",
    "earth_attitude",
    "planetary_ephemeris",
    "ephemeris_reconstructed",
    "ephemeris_predicted",
    "ephemeris_nominal",
    "ephemeris_90days",
    "attitude_history",
    "pointing_attitude",
    "lo_pivot_attitude",
    "spin",
    "thruster",
)


@dataclass
class DataSource:
    """Valid data sources for dependency tracking.

    Valid data sources include valid instruments names
    from imap_data_access and other data sources related to SPICE.
    """

    @property
    def valid_source(self) -> list[str]:
        """Add data sources.

        Returns
        -------
        list[str]
            list of valid data sources.
        """
        return [
            "spin",
            "repoint",
            "spice",
            *SPICE_SOURCES,
            *imap_data_access.VALID_INSTRUMENTS,
        ]


@dataclass
class DataType:
    """Valid data types for dependency tracking.

    Valid data types include valid data levels from imap_data_access
    and other data types related to SPICE and ancillary data.
    """

    SPICE: str = "spice"
    SPIN: str = "spin"
    REPOINT: str = "repoint"
    ANCILLARY: str = "ancillary"
    COLLECTION: str = "collection"

    @property
    def valid_type(self) -> list[str]:
        """Add data types.

        Returns
        -------
        list[str]
            list of valid data types.
        """
        return [
            self.SPICE,
            self.ANCILLARY,
            self.SPIN,
            self.REPOINT,
            self.COLLECTION,
            *imap_data_access.VALID_DATALEVELS,
        ]


@dataclass
class Node:
    """Node represents the key pieces of information about the processing starter.

    This contains all the information that is true starting from the input file
    all the way to the output processing job.

    source: Source should be one of DataSource. This represents the instrument or the
    area of responsibility (eg spin, repoint, etc)
    data_type: One of DataType. Represents the level or other more specific information.
    descriptor: String. Additional information which mostly is passed through without
    being used to the next processing step.
    """

    _data_source_validator: ClassVar[DataSource] = DataSource()
    _data_type_validator: ClassVar[DataType] = DataType()

    source: str
    data_type: str
    descriptor: str

    def __post_init__(self):
        """Validate all fields on construction."""
        self._validate_source(self.source)
        self._validate_data_type(self.data_type)
        self._validate_descriptor(self.descriptor)

    def _validate_source(self, source: str) -> None:
        """Validate source is valid."""
        if source not in self._data_source_validator.valid_source:
            raise ValueError(
                f"Invalid data source '{source}'. "
                f"Valid sources: {self._data_source_validator.valid_source}"
            )

    def _validate_data_type(self, data_type: str) -> None:
        """Validate data type is valid."""
        if data_type not in self._data_type_validator.valid_type:
            raise ValueError(
                f"Invalid data type '{data_type}'. "
                f"Valid types: {self._data_type_validator.valid_type}"
            )

    def _validate_descriptor(self, descriptor: str) -> None:
        """Validate descriptor is a non-empty string."""
        # TODO: validate descriptor once we finalize the descriptor list
        # for each instrument and data type.
        if not isinstance(descriptor, str) or not descriptor.strip():
            raise ValueError(
                f"Descriptor must be a non-empty string, got '{descriptor}'"
            )


@dataclass
class DependencyNode(Node):
    """Store dependency information for a given Node.

    This does not contain specific time span requirement, it is only relative time spans
    - i.e. rather than specifying that the dependencies cover June 1st to June 5th,
    it is instead 2 days before and 2 days after the processing time.

    A valid DependencyNode must have exactly 5 or 6 elements:
        [
            source,
            data_type,
            descriptor,
            required,
            trigger_job,
            Optional([past, future])
        ]
    If it includes past/future date ranges, it should follow the following format:
        - p - pointing
        - h - hourly
        - d - days
        - l - last_processed
        - nd - nearest day
        - np - nearest pointing

        past and future should end with one of these options. Eg.
            ["-3p", "3p"] means 3 pointing
            ["-3d", "5d"] means 5 days
            ["-2h", "2h"] means 2 hours
            ["-1l"] means last processed
            ["6np"] means nearest 6 pointing

    Validation is performed for each field.

    This information is retrieved from configuration files and used to assemble the
    ProcessingInputCollection for job starting.
    """

    required: bool = True
    trigger_job: bool = True
    dependency_query_time_range: list = field(default_factory=list)
    major_version: int = 1

    def __post_init__(self):
        """Validate all fields on construction."""
        super().__post_init__()
        self._validate_boolean_fields(self.required, self.trigger_job)
        self._validate_date_range(self.dependency_query_time_range)

    def serialize(self) -> dict[str, Any]:
        """Serialize dependency node to dictionary."""
        return asdict(self)

    @classmethod
    def deserialize(cls, json_object: dict[str, Any]):
        """Deserialize dictionary to dependency node."""
        return cls(**json_object)

    def _validate_boolean_fields(self, required: bool, trigger_job: bool) -> None:
        """Validate required and trigger_job are booleans."""
        if not isinstance(required, bool) or not isinstance(trigger_job, bool):
            raise ValueError("'required' and 'trigger_job' must be boolean values")

    def _validate_date_range(self, date_range) -> None:
        """Validate date range format if provided."""
        if not date_range:
            return

        if not isinstance(date_range, list) or not (1 <= len(date_range) <= 2):
            raise ValueError(
                "Date range must be a list of 1-2 elements [past] or [past, future], "
                f"got {date_range}"
            )

        # Handle both single-element and two-element lists
        past = date_range[0]
        future = date_range[1] if len(date_range) > 1 else None

        is_nearest = past.endswith(NEAREST_OPTIONS)

        # Nearest is only valid as a single-element list
        if is_nearest and future is not None:
            raise ValueError(
                "Nearest need to be in this format, [<int><option>, ]. "
                "Eg. ['6np',] or ['6nd',]"
            )

        # Validate past
        if is_nearest:
            past_option = "np" if past.endswith("np") else "nd"
            past_int = int(past[:-2])
        else:
            past_option = past[-1]
            past_int = int(past[:-1])

        # Validate past option and its integer value
        if (past_option not in DATE_RANGE_OPTIONS) or (
            past_option not in NEAREST_OPTIONS and past_int > 0
        ):
            raise ValueError(
                f"Invalid past '{past}'. Must end with "
                f"{DATE_RANGE_OPTIONS} and must be negative."
            )

        # Validate future if provided
        if future is None:
            return True
        elif future.endswith(NEAREST_OPTIONS):
            raise ValueError(
                "Nearest need to be in this format, [<int><option>, ]. "
                "Eg. ['6np',] or ['6nd',]"
            )
        else:
            future_option = future[-1]
            future_int = int(future[:-1])

        # Validate future option and integer value
        if (future_option not in DATE_RANGE_OPTIONS) or (future_int < 0):
            raise ValueError(
                f"Invalid future '{future}'. Must end with "
                f"{DATE_RANGE_OPTIONS} and be positive."
            )


@dataclass
class ProcessingJobNode(Node):
    """Representation of an expected processing job.

    This class contains information about the expected settings for a single processing
    job, including inputs, outputs, and the partition to use.
    """

    inputs: list[DependencyNode]
    outputs: list[DependencyNode]
    partition: str
    spice_types: list[str] = None
    triggering_deps: list[DependencyNode] = None  # Dependencies that trigger processing
    science_inputs: list[DependencyNode] = None
    ancillary_inputs: list[DependencyNode] = None
    spice_inputs: list[DependencyNode] = None
    spin_input: DependencyNode = None
    repoint_input: DependencyNode = None

    def __post_init__(self):
        """Consolidate and modify the inputs."""
        all_inputs = []
        triggering_deps = []
        spice_inputs = []
        ancillary_inputs = []
        science_inputs = []
        spice_types = []
        for dep in self.inputs:
            all_inputs.append(dep)
            if dep.source == "repoint":
                self.repoint_input = dep
            elif dep.data_type == "spice":
                spice_inputs.append(dep)
                spice_types.append(dep.source)
            elif dep.data_type == "spin":
                self.spin_input = dep
            elif dep.data_type == "ancillary":
                ancillary_inputs.append(dep)
            else:
                science_inputs.append(dep)
            if dep.trigger_job:
                triggering_deps.append(dep)

        self.inputs = all_inputs
        self.triggering_deps = triggering_deps
        self.spice_inputs = spice_inputs
        self.ancillary_inputs = ancillary_inputs
        self.science_inputs = science_inputs
        self.spice_types = spice_types
