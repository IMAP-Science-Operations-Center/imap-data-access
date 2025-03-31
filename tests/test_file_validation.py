"""Tests for the ``file_validataion`` module."""

from datetime import datetime
from pathlib import Path

import pytest

import imap_data_access
from imap_data_access.file_validation import (
    AncillaryFilePath,
    ScienceFilePath,
    SPICEFilePath,
)


def test_extract_filename_components():
    """Tests the ``extract_filename_components`` function."""
    valid_filename = "imap_mag_l1a_burst_20210101_v001.pkts"

    expected_output = {
        "mission": "imap",
        "instrument": "mag",
        "data_level": "l1a",
        "descriptor": "burst",
        "start_date": "20210101",
        "repointing": None,
        "version": "v001",
        "extension": "pkts",
    }

    assert (
        ScienceFilePath.extract_filename_components(valid_filename) == expected_output
    )
    # Add a repointing value
    valid_filename = "imap_mag_l1a_burst_20210101-repoint00001_v001.pkts"
    assert ScienceFilePath.extract_filename_components(
        valid_filename
    ) == expected_output | {"repointing": 1}

    # Add a multi-part hyphen descriptor
    valid_filename = "imap_mag_l1a_burst-1min_20210101_v001.pkts"
    assert ScienceFilePath.extract_filename_components(
        valid_filename
    ) == expected_output | {"descriptor": "burst-1min"}

    # Descriptor is required
    invalid_filename = "imap_mag_l1a_20210101_v001.cdf"

    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath.extract_filename_components(invalid_filename)

    # start and end time are required
    invalid_filename = "imap_mag_l1a_20210101_v001"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath.extract_filename_components(invalid_filename)

    valid_filepath = Path("/test/imap_mag_l1a_burst_20210101_v001.cdf")
    expected_output["extension"] = "cdf"
    assert (
        ScienceFilePath.extract_filename_components(valid_filepath) == expected_output
    )

    invalid_ext = "imap_mag_l1a_burst_20210101_v001.txt"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath.extract_filename_components(invalid_ext)


def test_construct_sciencefilepathmanager():
    """Tests that the ``ScienceFilePath`` class constructs a valid filename."""
    valid_filename = "imap_mag_l1a_burst_20210101_v001.cdf"
    sfm = ScienceFilePath(valid_filename)
    assert sfm.mission == "imap"
    assert sfm.instrument == "mag"
    assert sfm.data_level == "l1a"
    assert sfm.descriptor == "burst"
    assert sfm.start_date == "20210101"
    assert sfm.repointing is None
    assert sfm.version == "v001"
    assert sfm.extension == "cdf"

    # no extension
    invalid_filename = "imap_mag_l1a_burst_20210101_v001"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath(invalid_filename)

    # invalid extension
    invalid_filename = "imap_mag_l1a_burst_20210101_v001.pkts"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath(invalid_filename)

    # invalid instrument
    invalid_filename = "imap_sdc_l1a_burst_20210101_v001.cdf"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath(invalid_filename)

    # Bad repointing, not 5 digits
    invalid_filename = "imap_mag_l1a_burst_20210101-repoint0001_v001.cdf"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath(invalid_filename)

    # good path with an extra "test" directory
    valid_filepath = Path("/test/imap_mag_l1a_burst_20210101_v001.cdf")
    sfm = ScienceFilePath(valid_filepath)

    assert sfm.instrument == "mag"
    assert sfm.data_level == "l1a"
    assert sfm.descriptor == "burst"
    assert sfm.start_date == "20210101"
    assert sfm.repointing is None
    assert sfm.version == "v001"
    assert sfm.extension == "cdf"


def test_is_valid_date():
    """Tests the ``is_valid_date`` method."""
    valid_date = "20210101"
    assert ScienceFilePath.is_valid_date(valid_date)

    invalid_date = "2021-01-01"
    assert not ScienceFilePath.is_valid_date(invalid_date)

    invalid_date = "20210132"
    assert not ScienceFilePath.is_valid_date(invalid_date)

    invalid_date = "2021010"
    assert not ScienceFilePath.is_valid_date(invalid_date)


def test_construct_upload_path():
    """Tests the ``construct_path`` method."""
    valid_filename = "imap_mag_l1a_burst_20210101_v001.cdf"
    sfm = ScienceFilePath(valid_filename)
    expected_output = imap_data_access.config["DATA_DIR"] / Path(
        "imap/mag/l1a/2021/01/imap_mag_l1a_burst_20210101_v001.cdf"
    )

    assert sfm.construct_path() == expected_output


def test_generate_from_inputs():
    """Tests the ``generate_from_inputs`` method."""
    sfm = ScienceFilePath.generate_from_inputs(
        "mag", "l1a", "burst", "20210101", "v001"
    )
    expected_output = imap_data_access.config["DATA_DIR"] / Path(
        "imap/mag/l1a/2021/01/imap_mag_l1a_burst_20210101_v001.cdf"
    )

    assert sfm.construct_path() == expected_output
    assert sfm.instrument == "mag"
    assert sfm.data_level == "l1a"
    assert sfm.descriptor == "burst"
    assert sfm.start_date == "20210101"
    assert sfm.repointing is None
    assert sfm.version == "v001"
    assert sfm.extension == "cdf"

    sfm = ScienceFilePath.generate_from_inputs("mag", "l0", "raw", "20210101", "v001")
    expected_output = imap_data_access.config["DATA_DIR"] / Path(
        "imap/mag/l0/2021/01/imap_mag_l0_raw_20210101_v001.pkts"
    )

    assert sfm.construct_path() == expected_output

    sfm = ScienceFilePath.generate_from_inputs(
        "mag",
        "l0",
        "raw",
        "20210101",
        "v001",
        repointing=1,
    )
    expected_output = imap_data_access.config["DATA_DIR"] / Path(
        "imap/mag/l0/2021/01/imap_mag_l0_raw_20210101-repoint00001_v001.pkts"
    )
    assert sfm.construct_path() == expected_output


def test_spice_file_path():
    """Tests the ``SPICEFilePath`` class."""
    file_path = SPICEFilePath("imap_1000_100_1000_100_01.ap.bc")
    assert file_path.construct_path() == imap_data_access.config["DATA_DIR"] / Path(
        "spice/ck/imap_1000_100_1000_100_01.ap.bc"
    )

    # Test a bad file extension too
    with pytest.raises(SPICEFilePath.InvalidSPICEFileError):
        SPICEFilePath("test.txt")

    # Test that spin and repoint goes into their own directories
    spin_file_path = SPICEFilePath("imap_2025_122_2025_122_01.spin.csv")
    assert spin_file_path.construct_path() == imap_data_access.config[
        "DATA_DIR"
    ] / Path("spice/spin/imap_2025_122_2025_122_01.spin.csv")

    repoint_file_path = SPICEFilePath("imap_2025_122_01.repoint.csv")
    assert repoint_file_path.construct_path() == imap_data_access.config[
        "DATA_DIR"
    ] / Path("spice/repoint/imap_2025_122_01.repoint.csv")

    metakernel_file = SPICEFilePath("imap_1000_v000.tm")
    assert metakernel_file.construct_path() == imap_data_access.config[
        "DATA_DIR"
    ] / Path("spice/mk/imap_1000_v000.tm")

    thruster_file = SPICEFilePath("imap_0001_001_hist_00.sff")
    assert thruster_file.construct_path() == imap_data_access.config["DATA_DIR"] / Path(
        "spice/activities/imap_0001_001_hist_00.sff"
    )


def test_spice_extract_spin_parts():
    # Test spin
    file_path = SPICEFilePath("imap_2025_122_2025_122_01.spin.csv")
    assert file_path.spice_metadata["version"] == "01"
    assert file_path.spice_metadata["type"] == "spin"
    assert file_path.spice_metadata["start_date"] == datetime.strptime(
        "2025_122", "%Y_%j"
    )
    assert file_path.spice_metadata["end_date"] == datetime.strptime(
        "2025_122", "%Y_%j"
    )
    assert len(file_path.spice_metadata) == 5


def test_spice_extract_metakernel_parts():
    file_path = SPICEFilePath("imap_2025_v100.tm")
    assert file_path.spice_metadata["version"] == "100"
    assert file_path.spice_metadata["type"] == "metakernel"
    assert file_path.spice_metadata["start_date"] == datetime(2025, 1, 1)
    assert len(file_path.spice_metadata) == 5


def test_spice_extract_attitude_parts():
    file_path = SPICEFilePath("imap_2025_032_2025_034_003.ah.bc")
    assert file_path.spice_metadata["version"] == "003"
    assert file_path.spice_metadata["type"] == "attitude_history"
    assert file_path.spice_metadata["start_date"] == datetime.strptime(
        "2025_032", "%Y_%j"
    )
    assert file_path.spice_metadata["end_date"] == datetime.strptime(
        "2025_034", "%Y_%j"
    )
    assert len(file_path.spice_metadata) == 5


def test_spice_extract_leapsecond_parts():
    file_path = SPICEFilePath("naif0012.tls")
    assert file_path.spice_metadata["version"] == "0012"
    assert file_path.spice_metadata["type"] == "leapseconds"
    assert file_path.spice_metadata["extension"] == "tls"
    assert file_path.spice_metadata["start_date"] is None
    assert file_path.spice_metadata["end_date"] is None
    assert len(file_path.spice_metadata) == 5


def test_spice_extract_clock_parts():
    file_path = SPICEFilePath("imapsclk_0012.tsc")
    assert file_path.spice_metadata["version"] == "0012"
    assert file_path.spice_metadata["type"] == "spacecraft_clock"
    assert file_path.spice_metadata["extension"] == "tsc"
    assert file_path.spice_metadata["start_date"] is None
    assert file_path.spice_metadata["end_date"] is None
    assert len(file_path.spice_metadata) == 5


def test_spice_extract_planetary_ephemeris_parts():
    file_path = SPICEFilePath("de440.bsp")
    assert file_path.spice_metadata["version"] == "440"
    assert file_path.spice_metadata["type"] == "planetary_ephemeris"
    assert file_path.spice_metadata["extension"] == "bsp"
    assert file_path.spice_metadata["start_date"] is None
    assert file_path.spice_metadata["end_date"] is None
    assert len(file_path.spice_metadata) == 5


def test_spice_extract_pck_parts():
    file_path = SPICEFilePath("pck00010.tpc")
    assert file_path.spice_metadata["version"] == "00010"
    assert file_path.spice_metadata["type"] == "planetary_constants"
    assert file_path.spice_metadata["extension"] == "tpc"
    assert file_path.spice_metadata["start_date"] is None
    assert file_path.spice_metadata["end_date"] is None
    assert len(file_path.spice_metadata) == 5


def test_spice_extract_ephemeris_parts():
    file_path = SPICEFilePath("imap_90days_20251120_20260220_v01.bsp")
    assert file_path.spice_metadata["version"] == "01"
    assert file_path.spice_metadata["type"] == "ephemeris_90days"
    assert file_path.spice_metadata["start_date"] == datetime.strptime(
        "20251120", "%Y%m%d"
    )
    assert file_path.spice_metadata["end_date"] == datetime.strptime(
        "20260220", "%Y%m%d"
    )
    assert file_path.spice_metadata["extension"] == "bsp"
    assert len(file_path.spice_metadata) == 5


def test_spice_extract_repoint_parts():
    file_path = SPICEFilePath("imap_2025_230_01.repoint.csv")
    assert file_path.spice_metadata["version"] == "01"
    assert file_path.spice_metadata["type"] == "repoint"
    assert file_path.spice_metadata["extension"] == "csv"
    assert file_path.spice_metadata["start_date"] is None
    assert file_path.spice_metadata["end_date"] == datetime.strptime(
        "2025_230", "%Y_%j"
    )
    assert len(file_path.spice_metadata) == 5


def test_spice_invalid_dates():
    # Ensure the DOY is valid (DOY 410??)
    with pytest.raises(SPICEFilePath.InvalidSPICEFileError):
        SPICEFilePath("imap_2025_032_2025_410_003.ah.bc")

    # Ensure dates are valid (Month 13??)
    with pytest.raises(SPICEFilePath.InvalidSPICEFileError):
        SPICEFilePath("imap_90days_20251320_20260220_v01.bsp")

    # Ensure valid ephemeris type (type taco??)
    with pytest.raises(SPICEFilePath.InvalidSPICEFileError):
        SPICEFilePath("imap_taco_20251320_20260220_v01.bsp")


def test_spice_extract_parts_static_method():
    # Making sure the function works without an instance
    file_parts = SPICEFilePath.extract_filename_components(
        "imap_2025_122_2025_122_01.spin.csv"
    )
    assert file_parts["version"] == "01"
    file_parts = SPICEFilePath.extract_filename_components(
        "imap_2025_032_2025_034_003.ah.bc",
    )
    assert file_parts["version"] == "003"
    assert file_parts["type"] == "attitude_history"


def test_ancillary_file_path():
    """Tests the ``AncillaryFilePath`` class for different scenarios."""

    # Test for an invalid ancillary file (incorrect instrument type)
    with pytest.raises(AncillaryFilePath.InvalidAncillaryFileError):
        AncillaryFilePath.generate_from_inputs(
            instrument="invalid_instrument",  # Invalid instrument
            descriptor="test",
            start_time="20210101",
            version="v001",
            extension="cdf",
        )

    # Test with start_time and end_time
    ancillary_file_all_params = AncillaryFilePath.generate_from_inputs(
        instrument="mag",
        descriptor="test",
        start_time="20210101",
        end_time="20210102",
        version="v001",
        extension="cdf",
    )
    expected_output = imap_data_access.config["DATA_DIR"] / Path(
        "imap/ancillary/mag/imap_mag_test_20210101_20210102_v001.cdf"
    )
    assert ancillary_file_all_params.construct_path() == expected_output

    # Test with different extension (json)
    ancillary_file_json = AncillaryFilePath.generate_from_inputs(
        instrument="mag",
        descriptor="test",
        start_time="20210101",
        version="v001",
        extension="json",
    )
    expected_output_json = imap_data_access.config["DATA_DIR"] / Path(
        "imap/ancillary/mag/imap_mag_test_20210101_v001.json"
    )
    assert ancillary_file_json.construct_path() == expected_output_json

    # Test with different extension (csv)
    ancillary_file_csv = AncillaryFilePath.generate_from_inputs(
        instrument="mag",
        descriptor="test",
        start_time="20210101",
        version="v001",
        extension="csv",
    )
    expected_output_csv = imap_data_access.config["DATA_DIR"] / Path(
        "imap/ancillary/mag/imap_mag_test_20210101_v001.csv"
    )
    assert ancillary_file_csv.construct_path() == expected_output_csv

    # Test with no end date
    ancillary_file_no_end_date = AncillaryFilePath.generate_from_inputs(
        instrument="mag",
        descriptor="test",
        start_time="20210101",
        version="v001",
        extension="cdf",
    )
    expected_output_no_end_date = imap_data_access.config["DATA_DIR"] / Path(
        "imap/ancillary/mag/imap_mag_test_20210101_v001.cdf"
    )
    assert ancillary_file_no_end_date.construct_path() == expected_output_no_end_date

    # Test by passing the file
    anc_file = "imap_mag_test_20210101_20210102_v001.csv"
    ancillary_file = AncillaryFilePath(anc_file)
    assert ancillary_file.instrument == "mag"
    assert ancillary_file.end_date == "20210102"
