"""Methods for managing and validating filenames and filepaths."""
# ruff: noqa: PLR0913

from __future__ import annotations

import re
import typing
import warnings
from abc import abstractmethod
from datetime import datetime
from pathlib import Path

import imap_data_access


def generate_imap_file_path(filename: str) -> ImapFilePath:
    """Generate an ImapFilePath object from a filename.

    This method determines if the filename is a SPICE, Science, Ancillary, or
    Quicklook file and returns the corresponding class.

    Parameters
    ----------
    filename : str
        The filename to generate a path for.

    Returns
    -------
    A FilePath object
    """
    for cls in (
        ScienceFilePath,
        AncillaryFilePath,
        SPICEFilePath,
        QuicklookFilePath,
        DependencyFilePath,
    ):
        try:
            return cls(filename)
        except ImapFilePath.InvalidImapFileError:
            continue
    raise ValueError(
        f"Invalid file type for {filename}. It does not matchany file formats."
    )


class ImapFilePath:
    """Base class for FilePaths.

    Includes shared static methods and provides correct typing for ScienceFilePath,
    AncillaryFilePath, and SPICEFilePath.
    """

    class InvalidImapFileError(Exception):
        """Indicates a bad file type."""

        pass

    @property
    def data_dir(self) -> Path:
        """Return the data directory for the file.

        .. NOTE::
            This is deprecated, use `imap_data_access.config["DATA_DIR"]` instead.
        """
        warnings.warn(
            "data_dir is deprecated. Use imap_data_access.config['DATA_DIR'] instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return imap_data_access.config["DATA_DIR"]

    @staticmethod
    def is_valid_date(input_date: str) -> bool:
        """Check input date string is in valid format and is correct date.

        Parameters
        ----------
        input_date : str
            Date in YYYYMMDD format.

        Returns
        -------
        bool
            Whether date input is valid or not
        """
        # Validate if it's a real date
        try:
            # This checks if date is in YYYYMMDD format.
            # Sometimes, date is correct but not in the format we want
            datetime.strptime(input_date, "%Y%m%d")
            return True
        except ValueError:
            return False

    @staticmethod
    def is_valid_version(input_version: str) -> bool:
        """Check input version string is in valid format 'vXXX' or 'latest'.

        Parameters
        ----------
        input_version : str
            Version to be checked.

        Returns
        -------
        bool
            Whether input version is valid or not.
        """
        return input_version == "latest" or re.fullmatch(r"v\d{3}", input_version)

    @abstractmethod
    def construct_path(self) -> Path:
        """Construct valid path from class variables and data_dir."""
        raise NotImplementedError

    @abstractmethod
    def is_valid_for_start_date(self, start_date):
        """Check if the file is valid for the given time."""
        pass


class ScienceFilePath(ImapFilePath):
    """Class for building and validating filepaths for science files."""

    FILENAME_CONVENTION = (
        "<mission>_<instrument>_<datalevel>_<descriptor>_"
        "<startdate>(-<repointing>)_<version>.<extension>"
    )
    VALID_EXTENSIONS: typing.ClassVar[set[str]] = {"cdf", "pkts"}
    _dir_prefix = "imap"

    class InvalidScienceFileError(ImapFilePath.InvalidImapFileError):
        """DEPRECATED: Use ImapFilePath.InvalidImapFileError instead."""

        pass

    def __init__(self, filename: str | Path):
        """Class to store filepath and file management methods for science files.

        If you have an instance of this class, you can be confident you have a valid
        science file and generate paths in the correct format. The parent of the file
        path is set by the "IMAP_DATA_DIR" environment variable, or defaults to "data/"

        Current filename convention:
        <mission>_<instrument>_<datalevel>_<descriptor>_<start_date>(-<repointing>)
        _<version>.<extension>

        NOTE: There are no optional parameters. All parameters are required.
        <mission>: imap
        <instrument>: codice, glows, hi, hit, idex, lo, mag, swapi, swe, ultra
        <data_level> : l1a, l1b, l1, l3a and etc.
        <descriptor>: descriptor stores information specific to instrument. This is
            decided by each instrument. For L0, "raw" is used.
        <start_date>: startdate is the earliest date in the data, format: YYYYMMDD
        <repointing>: This is an optional field. It is used to indicate which
            repointing the data is from, format: repointXXXXX
        <cr>: This is an optional field describing the Carrington rotation.
            format: crXXXXX.
        <version>: This stores the data version for this product, format: vXXX

        Parameters
        ----------
        filename : str | Path
            Science data filename or file path.
        """
        self.filename = Path(filename)

        try:
            split_filename = self.extract_filename_components(self.filename)
        except ValueError as err:
            raise self.InvalidImapFileError(
                f"Invalid filename. Expected file to match format: "
                f"{ScienceFilePath.FILENAME_CONVENTION}"
            ) from err

        self.mission = split_filename["mission"]
        self.instrument = split_filename["instrument"]
        self.data_level = split_filename["data_level"]
        self.descriptor = split_filename["descriptor"]
        self.start_date = split_filename["start_date"]
        self.repointing = split_filename["repointing"]
        self.cr = split_filename["cr"]
        self.version = split_filename["version"]
        self.extension = split_filename["extension"]

        self.error_message = self.validate_filename()
        if self.error_message:
            raise self.InvalidImapFileError(f"{self.error_message}")

    @classmethod
    def generate_from_inputs(
        cls,
        instrument: str,
        data_level: str,
        descriptor: str,
        start_time: str,
        version: str,
        extension: str = "cdf",
        repointing: int | str | None = None,
        cr: int | None = None,
    ) -> ScienceFilePath:
        """Generate a filename from given inputs and return a ScienceFilePath instance.

        This can be used instead of the __init__ method to make a new instance:
        ```
        science_file_path = ScienceFilePath.generate_from_inputs("mag", "l0", "test",
            "20240213", "v001")
        full_path = science_file_path.construct_path()
        ```

        Parameters
        ----------
        descriptor : str
            The descriptor for the filename
        instrument : str
            The instrument for the filename
        data_level : str
            The data level for the filename
        start_time: str
            The start time for the filename
        version : str
            The version of the data
        extension : str, optional
            The extension type of the file. Default is "cdf"
            For l0 files, the extension is always "pkts"
        repointing : int, optional
            The repointing number for this file, optional field that
            is not always present. Should be either a string like "repointXXXXX" or an
            integer like 12345.
        cr : int, optional
            The Carrington rotation number for the file. This is an optional field.
            Only one (or zero) of repoint or CR can be included.

        Returns
        -------
        str
            The generated filename
        """
        if data_level == "l0":
            extension = "pkts"
        time_field = start_time
        if repointing is not None:
            if ScienceFilePath.is_valid_repointing(repointing):
                time_field += f"-{repointing}"
            elif isinstance(repointing, int):
                time_field += f"-repoint{repointing:05d}"
            if cr:
                raise ImapFilePath.InvalidImapFileError(
                    "Only one of CR or repointing can be included."
                )
        if cr:
            time_field += f"-cr{cr:05d}"
        filename = (
            f"imap_{instrument}_{data_level}_{descriptor}_{time_field}_"
            f"{version}.{extension}"
        )
        return cls(filename)

    def validate_filename(self) -> str:
        """Validate the filename and populate the error message for wrong attributes.

        The error message will be an empty string if the filename is valid. Otherwise,
        all errors with the filename will be put into the error message.

        Returns
        -------
        error_message: str
            Error message for specific missing attribute, or "" if the file name is
            valid.
        """
        error_message = ""

        if any(
            attr is None or attr == ""
            for attr in [
                self.mission,
                self.instrument,
                self.data_level,
                self.descriptor,
                self.start_date,
                self.version,
                self.extension,
            ]
        ):
            error_message = (
                f"Invalid filename, missing attribute. Filename "
                f"convention is {ScienceFilePath.FILENAME_CONVENTION} \n"
            )
        if self.mission != "imap":
            error_message += f"Invalid mission {self.mission}. Please use imap \n"

        if self.instrument not in imap_data_access.VALID_INSTRUMENTS:
            error_message += (
                f"Invalid instrument {self.instrument}. Please choose "
                f"from "
                f"{imap_data_access.VALID_INSTRUMENTS} \n"
            )
        if self.data_level not in imap_data_access.VALID_DATALEVELS:
            error_message += (
                f"Invalid data level {self.data_level}. Please choose "
                f"from "
                f"{imap_data_access.VALID_DATALEVELS} \n"
            )
        if not self.is_valid_date(self.start_date):
            error_message += "Invalid start date format. Please use YYYYMMDD format. \n"
        if not bool(re.match(r"^v\d{3}$", self.version)):
            error_message += "Invalid version format. Please use vXXX format. \n"
        if self.repointing and not isinstance(self.repointing, int):
            error_message += "The repointing number should be an integer.\n"

        if self.extension not in self.VALID_EXTENSIONS:
            error_message += (
                f"Invalid extension. Extension should be one of "
                f"{self.VALID_EXTENSIONS}\n"
            )

        return error_message

    def construct_path(self) -> Path:
        """Construct valid path from class variables and data_dir.

        If data_dir is not None, it is prepended on the returned path.

        expected return:
        <data_dir>/mission/instrument/data_level/startdate_month/startdate_day/filename

        Returns
        -------
        Path
            Upload path
        """
        upload_path = Path(
            f"{self._dir_prefix}/{self.instrument}/{self.data_level}/"
            f"{self.start_date[:4]}/{self.start_date[4:6]}/{self.filename}"
        )

        return imap_data_access.config["DATA_DIR"] / upload_path

    @staticmethod
    def extract_filename_components(filename: str | Path) -> dict:
        """Extract all components from filename. Does not validate instrument or level.

        Will return a dictionary with the following keys:
        { instrument, datalevel, descriptor, startdate, enddate, version, extension, cr,
        repointing }

        If a match is not found, a ValueError will be raised.

        Generally, this method should not be used directly. Instead the class should
        be used to make a `ScienceFilepath` object.

        Parameters
        ----------
        filename : Path or str
            Path of dependency data.

        Returns
        -------
        components : dict
            Dictionary containing components.
        """
        pattern = (
            r"^(?P<mission>imap)_"
            r"(?P<instrument>[^_]+)_"
            r"(?P<data_level>[^_]+)_"
            r"(?P<descriptor>[^_]+)_"
            r"(?P<start_date>\d{8})"
            # Optional repointing/CR field
            r"(-(?P<interval_type>(?:repoint|cr))(?P<interval>\d{5}))?"
            r"_(?P<version>v\d{3})"
            r"\.(?P<extension>[^.]+)$"
        )
        if isinstance(filename, Path):
            filename = filename.name

        match = re.match(pattern, filename)
        if match is None:
            raise ScienceFilePath.InvalidImapFileError(
                f"Filename {filename} does not match expected pattern: "
                f"{ScienceFilePath.FILENAME_CONVENTION}"
            )

        components = match.groupdict()
        components["repointing"] = None
        components["cr"] = None

        # If the repointing field exists, we want to check if it's a repointing or
        # carrington rotation (cr) and set the field accordingly
        interval_number = components.pop("interval")
        if interval_number:
            interval_number = int(interval_number)
            # We want the repointing number as an integer
            if components["interval_type"] == "cr":
                components["cr"] = interval_number
            elif components["interval_type"] == "repoint":
                components["repointing"] = interval_number

        del components["interval_type"]

        return components

    @staticmethod
    def is_valid_repointing(input_repointing: str) -> bool:
        """Check input repointing string is in valid format 'repointingXXXXX'.

        Parameters
        ----------
        input_repointing : str
            Repointing to be checked.

        Returns
        -------
        bool
            Whether input repointing is valid or not.
        """
        return bool(re.fullmatch(r"repoint\d{5}", str(input_repointing)))

    def is_valid_for_start_date(self, start_date: datetime) -> bool:
        """Check if the file is valid for the given science file start_date.

        Parameters
        ----------
        start_date : datetime
            The science time to check in YYYYMMDD format.

        Returns
        -------
        bool
            True if the file start_date is equal to the given time, False otherwise.
        """
        if datetime.strptime(self.start_date, "%Y%m%d") == start_date:
            return True
        else:
            return False

    @staticmethod
    def is_valid_cr(input_cr: str) -> bool:
        """Check input carrington rotation string is in valid format 'crXXXXX'.

        Parameters
        ----------
        input_cr : str
            Carrington rotation to be checked.

        Returns
        -------
        bool
            Whether input carrington rotation is valid or not.
        """
        return re.fullmatch(r"cr\d{5}", str(input_cr))


# Transform the suffix to the directory structure we are using
# Commented out mappings are not being used on IMAP


_SPICE_TYPE_MAPPING = {
    "ah.bc": "attitude_history",
    "ap.bc": "attitude_predict",
    "spin.csv": "spin",
    "spin": "spin",
    "repoint.csv": "repoint",
    "repoint": "repoint",
    "recon": "ephemeris_reconstructed",
    "nom": "ephemeris_nominal",
    "pred": "ephemeris_predicted",
    "90days": "ephemeris_90days",
    "long": "ephemeris_long",
    "launch": "ephemeris_launch",
    "de": "planetary_ephemeris",
    "pck": "planetary_constants",
    "naif": "leapseconds",
    "imap_dps": "pointing_attitude",
    "imap_sclk_": "spacecraft_clock",
    "tf": "imap_frames",
    "imap_science": "science_frames",
    "mk": "metakernel",
    "tm": "metakernel",
    "sff": "thruster",
    "L1_de": "lagrange_point",
    "bpc": "earth_attitude",
}

_SPICE_DIR_MAPPING = {
    "attitude_history": "ck",
    "pointing_attitude": "ck",
    "attitude_predict": "ck",
    "spin": "spin",
    "repoint": "repoint",
    "ephemeris_reconstructed": "spk",
    "ephemeris_nominal": "spk",
    "ephemeris_predicted": "spk",
    "ephemeris_90days": "spk",
    "ephemeris_long": "spk",
    "ephemeris_launch": "spk",
    "planetary_ephemeris": "spk",
    "planetary_constants": "pck",
    "leapseconds": "lsk",
    "spacecraft_clock": "sclk",
    "imap_frames": "fk",
    "science_frames": "fk",
    "metakernel": "mk",
    "thruster": "activities",
    "lagrange_point": "spk",
    "earth_attitude": "pck",
}
"""These are the valid extensions for SPICE files according to NAIF
https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/kernel.html

.bc    binary CK
.bds   binary DSK
.bes   binary Sequence Component EK
.bpc   binary PCK
.bsp   binary SPK
.tf    text FK
.ti    text IK
.tls   text LSK
.tm    text meta-kernel (FURNSH kernel)
.tpc   text PCK
.tsc   text SCLK
"""


class SPICEFilePath(ImapFilePath):
    """Class for building and validating filepaths for SPICE files."""

    _dir_prefix = "imap/spice"

    # Covers:
    # Historical Attitude (type: ah.bc)
    # Predicted Attitude (type: ap.bc)
    # Spin Files (type: spin.csv)
    attitude_file_pattern = (
        r"(imap)_"
        r"(?P<start_year_doy>[\d]{4}_[\d]{3})_"
        r"(?P<end_year_doy>[\d]{4}_[\d]{3})_"
        r"(?P<version>[\d]+)\."
        r"(?P<type>ah.bc|ap.bc|spin.csv|spin)"
    )
    # Covers:
    # DPS kernel (type: ah.bc)
    dps_file_pattern = (
        r"(?P<type>imap_dps)_"
        r"(?P<start_year_doy>\d{4}_\d{3})_"
        r"(?P<end_year_doy>[\d]{4}_[\d]{3})_"
        r"(?P<version>\d+)\."
        r"(?P<extension>ah\.bc)"
    )
    # Covers:
    # Repoint Files (type: repoint.csv, or repoint)
    repoint_file_pattern = (
        r"(imap)_"
        r"(?P<end_year_doy>[\d]{4}_[\d]{3})_"
        r"(?P<version>[\d]+)\."
        r"(?P<type>repoint.csv|repoint)"
    )
    # Covers:
    # Reconstructed (type: recon)
    # Nominal (type: nom)
    # Predict (type: pred)
    # 90 Day Predict (type: 90days)
    # Long Term Predict (type: long)
    # Launch Predict (type: launch)
    spacecraft_ephemeris_file_pattern = (
        r"(imap)_"
        r"(?P<type>[a-zA-Z0-9\-]+)_"
        r"(?P<start_date>[\d]{8})_"
        r"(?P<end_date>[\d]{8})"
        r"(?:|_v(?P<version>[\d]*))\."
        r"(?P<extension>bsp)"
    )
    # Covers:
    # Planetary Ephemeris (type: "de")
    # Lagrange Point Ephemeris (type: "L1_de")
    # Planetary Constants (type: "pck")
    # Leapsecond kernel (type: "naif")
    # Spacecraft clock kernel (type: "imap_sclk_")
    spice_prod_ver_pattern = (
        r"(?P<type>L1_de|[a-zA-Z\-_]+)"
        r"(?P<version>[\d]+)\."
        r"(?P<extension>tls|tpc|bsp|tsc)"
    )

    # Covers:
    # Frame: (type: 'tf')
    imap_frame_pattern = r"(imap)_(?P<version>[\d]+)\.(?P<type>tf)"

    # Covers:
    # Science Frame: (type: 'imap_science')
    science_frame_pattern = r"(?P<type>imap_science)_(?P<version>[\d]+)\.tf"

    # Covers:
    # Thruster files (type: sff)
    sff_filename_pattern = (
        r"(imap)_"
        r"(?P<start_year_doy>[\d]{4}_[\d]{3})_"
        r"(?P<end_year_doy>[\d]{4}_[\d]{3})_"
        r"(?P<type>sff)_"
        r"([a-zA-Z0-9\-_]+)_"
        r"(?P<version>[\d]{2})\."
        r"(?P<extension>sff)"
    )

    # Covers:
    # SDC generated metakernels (type: 'tm')
    sdc_mk_filename_pattern = (
        r"(imap)_sdc_metakernel_"
        r"(?P<start_year>[\d]{4})_"
        r"v(?P<version>[\d]{3})\."
        r"(?P<type>tm)"
    )

    # Covers:
    # MOC metakernels (type: 'mk')
    attitude_mk_filename_pattern = (
        r"imap_"
        r"(?P<start_year_doy>\d{4}_\d{3})_"
        r"a(?P<version>\d{2})\.spice\."
        r"(?P<type>mk)"
    )
    ephemeris_mk_filename_pattern = (
        r"IMAP_"
        r"(?P<start_year_doy>\d{4}_\d{3})_"
        r"e(?P<version>\d{2})\."
        r"(?P<type>mk)"
    )
    earth_attitude_pattern = (
        r"earth_"
        r"(?P<start_date>\d{6})_"
        r"(?P<end_date>\d{6})_"
        r"(?P<prediction_start_date>\d{6})"
        r"\.(?P<type>bpc)"
    )

    valid_spice_regexes = (
        re.compile(attitude_file_pattern, re.IGNORECASE),
        re.compile(dps_file_pattern, re.IGNORECASE),
        re.compile(repoint_file_pattern, re.IGNORECASE),
        re.compile(spacecraft_ephemeris_file_pattern, re.IGNORECASE),
        re.compile(spice_prod_ver_pattern, re.IGNORECASE),
        re.compile(imap_frame_pattern, re.IGNORECASE),
        re.compile(sff_filename_pattern, re.IGNORECASE),
        re.compile(sdc_mk_filename_pattern),
        re.compile(attitude_mk_filename_pattern, re.IGNORECASE),
        re.compile(ephemeris_mk_filename_pattern, re.IGNORECASE),
        re.compile(science_frame_pattern, re.IGNORECASE),
        re.compile(earth_attitude_pattern, re.IGNORECASE),
    )

    class InvalidSPICEFileError(ImapFilePath.InvalidImapFileError):
        """DEPRECATED: Use ImapFilePath.InvalidImapFileError instead."""

        pass

    def __init__(self, filename: str | Path):
        """Class to store filepath and file management methods for SPICE files.

        If you have an instance of this class, you can be confident you have a valid
        SPICE file and generate paths in the correct format. The parent of the file
        path is set by the "IMAP_DATA_DIR" environment variable, or defaults to "data/"

        IMAP_DATA_DIR/spice/<subdir>/filename"

        Parameters
        ----------
        filename : str | Path
            SPICE data filename or file path.
        """
        self.filename = Path(filename)
        self.spice_metadata = SPICEFilePath.extract_filename_components(self.filename)

    def construct_path(self) -> Path:
        """Construct valid path from the class variables and data_dir.

        expected return:
        <data_dir>/imap/spice/<subdir>/filename

        Returns
        -------
        Path
            Upload path
        """
        spice_dir = imap_data_access.config["DATA_DIR"] / f"{self._dir_prefix}"
        subdir = _SPICE_DIR_MAPPING[self.spice_metadata["type"]]
        # Use the file suffix to determine the directory structure
        # IMAP_DATA_DIR/spice/<subdir>/filename
        return spice_dir / subdir / self.filename

    @staticmethod
    def _spice_parts_handler(components):  # noqa: PLR0912
        """Validate and transform SPICE file compents.

        Parameters
        ----------
        components : dict
            Dictionary containing components of the file.

        Returns
        -------
        components : dict | None
            Dictionary containing components, validated and transformed.
            If
        """
        if components["type"] not in _SPICE_TYPE_MAPPING:
            raise SPICEFilePath.InvalidImapFileError(
                f"Invalid SPICE file. Expected file to have one of the following "
                f"file types {list(_SPICE_DIR_MAPPING.keys())}. Please reference "
                f"the documentation to ensure the type,{components['type']},has "
                f"the proper naming convention."
            )

        components["type"] = _SPICE_TYPE_MAPPING[components["type"]]

        try:
            if "start_date" in components:  # Convert to datetime
                if len(components["start_date"]) == 8:
                    components["start_date"] = datetime.strptime(
                        components["start_date"], "%Y%m%d"
                    )
                else:
                    components["start_date"] = datetime.strptime(
                        components["start_date"], "%y%m%d"
                    )
            if "end_date" in components:
                if len(components["end_date"]) == 8:
                    components["end_date"] = datetime.strptime(
                        components["end_date"], "%Y%m%d"
                    )
                else:
                    components["end_date"] = datetime.strptime(
                        components["end_date"], "%y%m%d"
                    )
            if "start_year_doy" in components:
                components["start_date"] = datetime.strptime(
                    components.pop("start_year_doy"), "%Y_%j"
                )
            if "end_year_doy" in components:
                components["end_date"] = datetime.strptime(
                    components.pop("end_year_doy"), "%Y_%j"
                )
            if "start_year" in components:
                components["start_date"] = datetime(
                    int(components.pop("start_year")), 1, 1
                )
            if "prediction_start_date" in components:
                components["prediction_start_date"] = datetime.strptime(
                    components["prediction_start_date"], "%y%m%d"
                )
        except ValueError:
            raise SPICEFilePath.InvalidImapFileError(
                "Invalid date detect in product file name, ensure date exists"
            ) from None

        if "start_date" not in components:
            components["start_date"] = None
        if "end_date" not in components:
            components["end_date"] = None
        return components

    @staticmethod
    def extract_filename_components(filename: Path | str) -> dict | None:
        """Extract all components from filename.

        Will return a dictionary in the form:
            version - string
            type - string
            extension - string
            start_date - datetime or None
            end_date - datetime or None

        If a match is not found, InvalidImapFileError will be raised.

        Parameters
        ----------
        filename : Path | str
            The filename to parse

        Returns
        -------
        components : dict
            Dictionary containing components.
        """
        filename = Path(filename)
        for regex in SPICEFilePath.valid_spice_regexes:
            m = regex.match(filename.name)
            if m is not None:
                spice_metadata = SPICEFilePath._spice_parts_handler(m.groupdict())
                # Add the extension to the metadata
                spice_metadata["extension"] = filename.suffix[1:]
                return spice_metadata

        # Error if no match found to accepted types
        raise SPICEFilePath.InvalidImapFileError(
            f"Invalid SPICE file. Expected file to have one of the following "
            f"file types {list(_SPICE_DIR_MAPPING.keys())}. Please reference "
            f"the documentation to ensure the file, {filename}, has the "
            f"proper naming convention "
        )

    def is_valid_for_start_date(self, start_date: datetime) -> bool:
        """Check if the SPICE file is valid for the given science start_date.

        Parameters
        ----------
        start_date : datetime
            The science time to check in YYYYMMDD format.

        Returns
        -------
        bool
            True if the SPICE file date range covers the given time, False otherwise.
        """
        # TODO implement this
        return True


class AncillaryFilePath(ImapFilePath):
    """Class for building and validating filepaths for Ancillary files."""

    FILENAME_CONVENTION = (
        "<mission>_<instrument>_<description>_"
        "<start_date>(_<end_date>)_<version>.<extension>"
    )
    VALID_EXTENSIONS: typing.ClassVar[set[str]] = {
        "cdf",
        "csv",
        "dat",
        "json",
        "zip",
        "tsv",
        "pgm",
    }
    _dir_prefix = "imap/ancillary"

    class InvalidAncillaryFileError(ImapFilePath.InvalidImapFileError):
        """DEPRECATED: Use ImapFilePath.InvalidImapFileError instead."""

        pass

    def __init__(self, filename: str | Path):
        """Class to store filepath and file management methods for Ancillary files.

        If you have an instance of this class, you can be confident you have a valid
        ancillary file and generate paths in the correct format. The parent of the file
        path is set by the "IMAP_DATA_DIR" environment variable, or defaults to "data/"

        Current filename convention:
        "<mission>_<instrument>_<descriptor>_<start_date>(_<end_date>)_
        <version>.<extension>"

        <mission>: imap
        <instrument>: codice, glows, hi, hit, idex, lo, mag, swapi, swe, ultra
        <descriptor>: A descriptive name for the ancillary file which
                       distinguishes between other ancillary files used by the
                       instrument.
        <start_date>: startdate is the earliest date where the file is valid,
                     format: YYYYMMDD
        <end_date>: The end time of the validity of the ancillary file,
                    in the format “YYYYMMDD”. This is optional for files, with the
                    understanding that if end_date is not provided, the file is valid
                    until a file with a later start_date and no end_date.
        <version>: This stores the data version for this product, format: vXXX

        Parameters
        ----------
        filename : str | Path
            Ancillary data filename or file path.
        """
        self.filename = Path(filename)

        try:
            split_filename = self.extract_filename_components(self.filename)
        except ValueError as err:
            raise self.InvalidImapFileError(
                f"Invalid filename. Expected file to match format: "
                f"{AncillaryFilePath.FILENAME_CONVENTION}"
            ) from err

        self.mission = split_filename["mission"]
        self.instrument = split_filename["instrument"]
        self.descriptor = split_filename["descriptor"]
        self.start_date = split_filename["start_date"]
        self.end_date = split_filename["end_date"]
        self.version = split_filename["version"]
        self.extension = split_filename["extension"]

        self.error_message = self.validate_filename()
        if self.error_message:
            raise self.InvalidImapFileError(f"{self.error_message}")

    @classmethod
    def generate_from_inputs(
        cls,
        instrument: str,
        descriptor: str,
        version: str,
        extension: str,
        start_time: str,
        end_time: str | None = None,
    ) -> AncillaryFilePath:
        """Generate filename from given inputs and return a AncillaryFilePath instance.

        This can be used instead of the __init__ method to make a new instance:
        ```
        ancillary_file_path = AncillaryFilePath.generate_from_inputs("mag",
        "mag-rotation-matrices", "20240213", "v001")
        full_path = ancillary_file_path.construct_path()
        ```

        Parameters
        ----------
        instrument : str
            The instrument for the filename.
        descriptor : str
            The descriptor for the ancillary filename.
        version : str
            The version of the data.
        extension : str
            The extension type of the file.
        start_time: str
            The start time for the filename. An updated
            start time or the mission start time.
        end_time: str, optional
            The end time for the filename. If not provided,
            the file is valid until a file with a later
            start_date and no end_date.

        Returns
        -------
        str
            The generated filename
        """
        if end_time:
            filename = (
                f"imap_{instrument}_{descriptor}_{start_time}_{end_time}_"
                f"{version}.{extension}"
            )
        else:
            filename = (
                f"imap_{instrument}_{descriptor}_{start_time}_{version}.{extension}"
            )
        return cls(filename)

    def validate_filename(self) -> str:
        """Validate the filename and populate the error message for wrong attributes.

        The error message will be an empty string if the filename is valid. Otherwise,
        all errors with the filename will be put into the error message.

        Returns
        -------
        error_message: str
            Error message for specific missing attribute, or "" if the file name is
            valid.
        """
        error_message = ""

        if any(
            attr is None or attr == ""
            for attr in [
                self.mission,
                self.instrument,
                self.descriptor,
                self.version,
                self.extension,
            ]
        ):
            error_message = (
                f"Invalid filename, missing attribute. Filename "
                f"convention is {AncillaryFilePath.FILENAME_CONVENTION} \n"
            )
        if self.mission != "imap":
            error_message += f"Invalid mission {self.mission}. Please use imap \n"

        if self.instrument not in imap_data_access.VALID_INSTRUMENTS:
            error_message += (
                f"Invalid instrument {self.instrument}. Please choose from "
                f"{imap_data_access.VALID_INSTRUMENTS} \n"
            )

        if self.extension not in self.VALID_EXTENSIONS:
            error_message += (
                f"Invalid extension. Extension should be one of "
                f"{self.VALID_EXTENSIONS}.\n"
            )

        if not ScienceFilePath.is_valid_date(self.start_date):
            error_message += "Invalid start date format. Please use YYYYMMDD format. \n"

        if self.end_date:
            if not ScienceFilePath.is_valid_date(self.end_date):
                error_message += (
                    "Invalid end date format. Please use YYYYMMDD format. \n"
                )

        return error_message

    def construct_path(self) -> Path:
        """Construct valid path from class variables and data_dir.

        If data_dir is not None, it is prepended on the returned path.

        expected return:
        <data_dir>/mission/instrument/filename

        Returns
        -------
        Path
            Upload path
        """
        upload_path = Path(f"{self._dir_prefix}/{self.instrument}/{self.filename}")
        return imap_data_access.config["DATA_DIR"] / upload_path

    @staticmethod
    def extract_filename_components(filename: str | Path) -> dict:
        """Extract all components from filename. Does not validate instrument or level.

        Will return a dictionary with the following keys:
        { instrument, descriptor, start_date, end_date, version, extension }

        If a match is not found, a ValueError will be raised.

        Generally, this method should not be used directly. Instead the class should
        be used to make a `AncillaryFilepath` object.

        Parameters
        ----------
        filename : Path or str
            Path of dependency data.

        Returns
        -------
        components : dict
            Dictionary containing components.
        """
        # Pipe these together for optional matching in the regex below
        extension_regex = "|".join(
            AncillaryFilePath.VALID_EXTENSIONS.union(QuicklookFilePath.VALID_EXTENSIONS)
        )
        pattern = (
            r"^(?P<mission>imap)_"
            r"(?P<instrument>[^_]+)_"
            r"(?P<descriptor>[^_]+)_"
            r"(?P<start_date>\d{8})"
            r"(_(?P<end_date>\d{8}))?"  # Optional end_date
            r"_(?P<version>v\d{3})"
            rf"\.(?P<extension>{extension_regex})$"
        )
        if isinstance(filename, Path):
            filename = filename.name

        match = re.match(pattern, filename)
        if match is None:
            raise AncillaryFilePath.InvalidImapFileError(
                f"Filename {filename} does not match expected pattern: "
                f"{AncillaryFilePath.FILENAME_CONVENTION}"
            )

        components = match.groupdict()
        return components

    def is_valid_for_start_date(self, start_date: datetime) -> bool:
        """Check if the Ancillary file is valid for the given science start_date.

        Parameters
        ----------
        start_date : datetime
            The science time to check in YYYYMMDD format.

        Returns
        -------
        bool
            True if the Ancillary file date range covers the given time, False
            otherwise.
        """
        start_date_anc = datetime.strptime(self.start_date, "%Y%m%d")
        if self.end_date:
            # If end_date is set, check to see weather the time is between start and end
            end_date_anc = datetime.strptime(self.end_date, "%Y%m%d")
            if start_date_anc <= start_date <= end_date_anc:
                return True
        # If end_date is not set, check to see if the time is after start_date
        elif start_date_anc <= start_date:
            return True
        return False


class QuicklookFilePath(ScienceFilePath):
    """Class for building and validating filepaths for Quicklook files."""

    VALID_EXTENSIONS: typing.ClassVar[set[str]] = {"jpg", "pdf", "png"}
    _dir_prefix = "imap/quicklook"


class DependencyFilePath(ScienceFilePath):
    """Class for building and validating filepaths for dependency files.

    These files store the processing input for the data product they
    are associated with. This approach avoids hitting the character
    limit imposed by batch job commands and ensures the input format
    remains compatible with what ProcessingInputCollection expects.
    """

    VALID_EXTENSIONS: typing.ClassVar[set[str]] = {"json"}
    _dir_prefix = "imap/dependency"


class CadenceFilePath(DependencyFilePath):
    """DEPRECATED class for CadenceFile processing, use DependencyFilePath instead."""
