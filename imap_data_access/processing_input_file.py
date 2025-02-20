import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from imap_data_access import ScienceFilePath, AncillaryFilePath, SPICEFilePath


class ProcessingInputType(Enum):
    SCIENCE_FILE = "science"
    ANCILLARY_FILE = "ancillary"
    SPICE_FILE = "spice"


class InputTypePathMapper(Enum):
    SCIENCE_FILE = ScienceFilePath
    ANCILLARY_FILE = AncillaryFilePath
    SPICE_FILE = SPICEFilePath


class InputFileDescription:
    filepath: str
    type: ProcessingInputType

    # TODO: keep filepath?
    def __init__(self, filepath: str, type: ProcessingInputType):
        self.filepath = filepath
        self.type = type

    def construct_json_output(self):
        pass

@dataclass
class ProcessingInput(ABC):
    """ Interface for input files.

     Mostly used for typehints and to enforce a common interface for input files.
     """
    filepath_list: list[str] = None
    input_type: ProcessingInputType = None
    # Following three are retrieved from dependency check.
    # But they can also come from the filename.
    source: str = field(init=False)
    data_type: str = field(init=False)  # should be data level or "ancillary" or "spice"
    descriptor: str = field(init=False)
    time_range: tuple = field(init=False)

    def __init__(self, *args):
        """

        Parameters
        ----------
        args
            InputFileDescriptions
        """
        self.filepath_list = []
        for filename in args:
            if not isinstance(filename, str):
                raise ValueError("All arguments must be strings")
            self.filepath_list.append(filename)
        self._set_attributes_from_filenames()
        self.time_range = self.get_time_range()
        self.description = []
        if len(args) < 1:
            raise ValueError("At least one file must be provided.")

        for filepath in args:
            self.description.append(InputFileDescription(filepath=filepath,
                                                         type=ProcessingInputType.SCIENCE_FILE))

    @abstractmethod
    def get_time_range(self):
        raise NotImplementedError

    def _set_attributes_from_filenames(self):
        source = set()
        data_type = set()
        descriptor = set()
        science_file_paths = []
        for file in self.filepath_list:
            path_validator = InputTypePathMapper[self.input_type.name].value(file)
            print(path_validator)
            # science_file_path = ScienceFilePath(file)

            source.add(path_validator.instrument)
            data_type.add(path_validator.data_level)
            descriptor.add(path_validator.descriptor)
            science_file_paths.append(path_validator)

        if len(source) != 1 or len(data_type) != 1 or len(descriptor) != 1:
            raise ValueError(
                "All files must have the same source, data type, and descriptor.")

        self.source = source.pop()
        self.data_type = data_type.pop()
        self.descriptor = descriptor.pop()
        self.science_file_paths = science_file_paths

    @abstractmethod
    def construct_json_output(self):
        raise NotImplementedError


class ScienceInput(ProcessingInput):
    """
    Science

    The class can contain multiple files, but they must have the same source, data type,
     and descriptor.


    """
    science_file_paths: list[ScienceFilePath] = None

    def __init__(self, *args):
        self.input_type = ProcessingInputType.SCIENCE_FILE
        super().__init__(*args)

    def get_time_range(self) -> tuple:
        pass

    def construct_json_output(self) -> dict:
        return {"type": self.input_type.value, "path": self.filepath_list}


class AncillaryInput(ProcessingInput):
    # Can contain multiple ancillary files - should have the same descriptor
    def _set_attributes_from_filenames(self):
        pass

    def get_time_range(self):
        # I think we will want the time range of all the filenames here.
        pass


class SpiceInput(ProcessingInput):
    def _set_attributes_from_filenames(self):
        pass


    def get_time_range(self):
        pass


@dataclass
class ProcessingInputCollection:
    # I am not sure if the collection class makes sense.
    # It might be better to just use lists of ProcessingInput objects.
    # But, there may be some shared methods and it is nice to ensure the collection.

    # TODO: take in an unordered list of filenames, return organized info.

    # NOT necessarily one file (eg ancillary files)
    files: list[ProcessingInput]

    def __init__(self, processing_inputs: Optional[list[ProcessingInput]] = None):
        if processing_inputs is None:
            self.files = []
        else:
            self.files = processing_inputs

    def serialize(self) -> str:
        json_out = []
        for file in self.files:
            json_out.append(file.construct_json_output())

        return json.dumps(json_out)

    def add_file(self, file: ProcessingInput):
        self.files.append(file)

    def deserialize(self, json_input: str):
        """
        Returns a list of InputFile objects.

        Parameters
        ----------
        json_input

        Returns
        -------

        """
        full_input = json.loads(json_input)
        print("in deserialize")
        print(full_input)
        self.files = []

        for file_creator in full_input:
            if file_creator["type"] == ProcessingInputType.SCIENCE_FILE.value:
                print(type(file_creator["path"]))
                print(type(file_creator["path"][0]))
                self.files.append(ScienceInput(*file_creator["path"]))
            elif file_creator["type"] == ProcessingInputType.ANCILLARY_FILE.value:
                self.files.append(AncillaryInput(*file_creator["path"]))
            elif file_creator["type"] == ProcessingInputType.SPICE_FILE.value:
                self.files.append(SpiceInput(*file_creator["path"]))


