"""Class for abstracting and organizing collections of input files."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from imap_data_access import AncillaryFilePath, ScienceFilePath, SPICEFilePath


class ProcessingInputType(Enum):
    """Enum matching types of ProcessingInputs to output strings describing them."""

    SCIENCE_FILE = "science"
    ANCILLARY_FILE = "ancillary"
    SPICE_FILE = "spice"


class InputTypePathMapper(Enum):
    """Enum matching ProcessingInput names to classes."""

    SCIENCE_FILE = ScienceFilePath
    ANCILLARY_FILE = AncillaryFilePath
    SPICE_FILE = SPICEFilePath


@dataclass
class ProcessingInput(ABC):
    """Interface for input file management and serialization.

    ProcessingInput is an abstract class that is used to manage input files for
    processing. Any kind of input file can create an Input class which inherits from
    this abstract class. Then, they can be used in ProcessingInputCollection, which
    describes a set of files to be used in processing.

    Each instance of the Input class can contain multiple files that have the same
    source, data type, and descriptor, but which may cover a wide time range.

    Attributes
    ----------
    filepath_list : list[str]
        A list of filepaths.
    input_type : ProcessingInputType
        The type of input file.
    source : str
        The source of the file, for example, instrument name, "sc_attitude", or
        "ancillary".
    data_type : str
        The type of data, for example, "l1a" or "l1b" or "predict".
    descriptor : str
        A descriptor for the file, for example, "burst" or "cal".
    """

    filename_list: list[str] = None
    input_type: ProcessingInputType = None
    # Following three are retrieved from dependency check.
    # But they can also come from the filename.
    source: str = field(init=False)
    data_type: str = field(init=False)  # should be data level or "ancillary" or "spice"
    descriptor: str = field(init=False)

    def __init__(self, *args):
        """Initialize using a list of filepaths and sets the attributes of the class.

        This method works for ScienceFilePaths and AncillaryFilePaths. Subclasses
        should set self.input_type to the appropriate ProcessingInputType before
        calling this method.

        Parameters
        ----------
        args: str
            Filenames (not paths), as strings.
        """
        self.filename_list = []
        for filename in args:
            if not isinstance(filename, str):
                raise ValueError("All arguments must be strings")
            self.filename_list.append(filename)
        self._set_attributes_from_filenames()
        if len(args) < 1:
            raise ValueError("At least one file must be provided.")

    @abstractmethod
    def get_time_range(self):
        """Describe the time range covered by the files.

        Should return a tuple with (start_date, end_date).
         All datapoints in the file should fall within the range,
        inclusive (so ranging from midnight on start_date to midnight on end_date+1).

        Abstract method that is overridden for each file type.

        Returns
        -------
        (start_time, end_time): tuple[datetime, datetime]
            A tuple with the earliest and latest times covered by the files.
        """
        raise NotImplementedError

    def _set_attributes_from_filenames(self):
        """Set the source, data type, and descriptor attributes based on the filenames.

        This method is called by the constructor and can be overridden by subclasses.
        It works for ScienceFilePaths and AncillaryFilePaths, but not SPICEFilePaths.

        This sets source, datatype, descriptor, and file_path_list attributes.
        """
        # For science and ancillary files
        source = set()
        data_type = set()
        descriptor = set()
        file_path_list = []
        for file in self.filename_list:
            path_validator = InputTypePathMapper[self.input_type.name].value(file)

            source.add(path_validator.instrument)
            if self.input_type == ProcessingInputType.SCIENCE_FILE:
                data_type.add(path_validator.data_level)
            else:
                data_type.add(self.input_type.value)
            descriptor.add(path_validator.descriptor)
            file_path_list.append(path_validator)

        if len(source) != 1 or len(data_type) != 1 or len(descriptor) != 1:
            raise ValueError(
                "All files must have the same source, data type, and descriptor."
            )

        self.source = source.pop()
        self.data_type = data_type.pop()
        self.descriptor = descriptor.pop()
        self.file_path_list = file_path_list

    def construct_json_output(self):
        """Construct a JSON output.

        This contains the minimum information needed to construct an identical
        ProcessingInput instance (input_type and filename)
        """
        return {"type": self.input_type.value, "files": self.filename_list}


class ScienceInput(ProcessingInput):
    """Science file subclass for ProcessingInput.

    The class can contain multiple files, but they must have the same source, data type,
     and descriptor.

    Attributes
    ----------
    science_file_paths : list[ScienceFilePath]
        A list of ScienceFilePath objects.
    """

    science_file_paths: list[ScienceFilePath] = None

    def __init__(self, *args):
        """Set the processing type to ScienceFile and then calls super().

        Parameters
        ----------
        args : str
            Filenames for initialization.
        """
        self.input_type = ProcessingInputType.SCIENCE_FILE
        super().__init__(*args)

    def get_time_range(self):
        """Retrieve the time range covered by the files.

        Files are assumed to cover exactly 24 hours. The range returned is (earliest,
        latest) where latest is inclusive.

        Returns
        -------
        (earlist, latest) : tuple[datetime]
        Tuple of datetimes describing the range of the files.
        """
        # TODO: Add repointing time calculation here
        # files are currently assumed to cover exactly 24 hours.
        earliest = None
        latest = None
        for file in self.filename_list:
            filepath = ScienceFilePath(file)
            date = datetime.strptime(filepath.start_date, "%Y%m%d")
            if earliest is None or date < earliest:
                earliest = date
            if latest is None or date > latest:
                latest = date
        return earliest, latest


class AncillaryInput(ProcessingInput):
    """Ancillary file subclass for ProcessingInput.

    The class can contain multiple files, but they must have the same source, data type,
    and descriptor.
    """

    # Can contain multiple ancillary files - should have the same descriptor
    def __init__(self, *args):
        """Set the processing type to AncillaryFile and then calls super().

        Parameters
        ----------
        args : str
            Filenames for initialization.

        """
        self.input_type = ProcessingInputType.ANCILLARY_FILE
        super().__init__(*args)

    def get_time_range(self):
        """Return the time range covered by the ancillary files.

        The return is a tuple (earliest, latest) where latest is inclusive.
        For example, a single file with a time range of 20250101-20250105 would return
        (20250101, 20250105).

        Returns
        -------
        (earlist, latest) : tuple[datetime]
            A tuple of earliest, latest describing the time range across all files.
        """
        earliest = None
        latest = None
        for file in self.filename_list:
            filepath = AncillaryFilePath(file)
            startdate = datetime.strptime(filepath.start_date, "%Y%m%d")
            if filepath.end_date is not None:
                enddate = datetime.strptime(filepath.end_date, "%Y%m%d")
            else:
                enddate = startdate

            if earliest is None or startdate < earliest:
                earliest = startdate
            if latest is None or enddate > latest:
                latest = enddate

        return earliest, latest

    def get_file_for_time(self, day):
        """Given a single time or day, return the files that are required for coverage.

        This will take all the files that are valid for that timestamp, and select only
        the highest version of the file.

        Parameters
        ----------
        day: datetime
            Input day to retrieve files for

        Returns
        -------
        list[str]
            List of filenames that are required for the given day.
        """
        # todo: complete this
        return NotImplementedError


class SpiceInput(ProcessingInput):
    """SPICE file subclass for ProcessingInput."""

    def __init__(self, *args) -> None:
        """Initialize the attributes from the SPICE file name.

        Not completed.

        Parameters
        ----------
        args : str
            Input SPICE filenames.
        """
        self.input_type = ProcessingInputType.SPICE_FILE
        # Not yet completed
        raise NotImplementedError

    def _set_attributes_from_filenames(self) -> None:
        """Set the source, data type, and descriptor attributes based on filename."""
        # TODO: update SPICEFilePath to retrieve data_type and descriptor from
        # file name. Do we have an expected filename format?

        # just using examples for now
        self.source = "sc_attitude"
        self.data_type = ProcessingInputType.SPICE_FILE.value
        self.descriptor = "predict"

    def get_time_range(self):
        """Not yet complete."""
        pass


@dataclass
class ProcessingInputCollection:
    """Describe a collection of ProcessingInput objects.

    This can be used to organize a set of ProcessingInput objects, which can then fully
    describe all the required inputs to a processing step.

    This also serializes and deserializes the ProcessingInput classes to and from JSON
    so they can be passed between processes.

    Attributes
    ----------
    processing_input : list[ProcessingInput]
        A list of ProcessingInput objects.
    """

    processing_input: list[ProcessingInput]

    def __init__(self, processing_inputs: list[ProcessingInput] | None = None) -> None:
        """Initialize the collection with the inputs.

        Parameters
        ----------
        processing_inputs : Optional[list]
            A list of ProcessingInput objects to add to the collection.
        """
        if processing_inputs is None:
            self.processing_input = []
        else:
            self.processing_input = processing_inputs

    def add(self, processing_inputs: list | ProcessingInput) -> None:
        """Add a ProcessingInput or list of processing inputs to the collection.

        Parameters
        ----------
        processing_inputs : list | ProcessingInput
            Either a list of ProcessingInputs or a single ProcessingInput instance.
        """
        if isinstance(processing_inputs, list):
            self.processing_input.extend(processing_inputs)
        else:
            self.processing_input.append(processing_inputs)

    def serialize(self) -> str:
        """Convert the collection to a JSON string.

        Returns
        -------
        str
            A string of JSON-formatted serialized output.
        """
        json_out = []
        for file in self.processing_input:
            json_out.append(file.construct_json_output())

        return json.dumps(json_out)

    def deserialize(self, json_input: str) -> None:
        """Deserialize JSON into the collection of ProcessingInput instances.

        Parameters
        ----------
        json_input : str
            JSON input matching the output of ProcessingInputCollection.serialize()
        """
        full_input = json.loads(json_input)
        self.processing_input = []

        for file_creator in full_input:
            if file_creator["type"] == ProcessingInputType.SCIENCE_FILE.value:
                self.processing_input.append(ScienceInput(*file_creator["path"]))
            elif file_creator["type"] == ProcessingInputType.ANCILLARY_FILE.value:
                self.processing_input.append(AncillaryInput(*file_creator["path"]))
            elif file_creator["type"] == ProcessingInputType.SPICE_FILE.value:
                self.processing_input.append(SpiceInput(*file_creator["path"]))

    def get_science_files(self) -> list[ProcessingInput]:
        """Return just the science files from the collection.

        Returns
        -------
        out : list[ScienceInput]
            list of ScienceInput files contained in the collection.
        """
        out = []
        for file in self.processing_input:
            if file.input_type == ProcessingInputType.SCIENCE_FILE:
                out.append(file)

        return out
