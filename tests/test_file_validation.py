from pathlib import Path

import pytest

import imap_data_access
from imap_data_access.file_validation import ScienceFilePath


def test_extract_filename_components():
    valid_filename = "imap_mag_l1a_burst_20210101_20210102_v01-01.pkts"

    expected_output = {
        "mission": "imap",
        "instrument": "mag",
        "data_level": "l1a",
        "descriptor": "burst",
        "start_date": "20210101",
        "end_date": "20210102",
        "version": "v01-01",
        "extension": "pkts",
    }

    assert (
        ScienceFilePath.extract_filename_components(valid_filename) == expected_output
    )

    # Descriptor is required
    invalid_filename = "imap_mag_l1a_20210101_20210102_v01-01.cdf"

    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath.extract_filename_components(invalid_filename)

    # start and end time are required
    invalid_filename = "imap_mag_l1a_20210101_v01-01"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath.extract_filename_components(invalid_filename)

    valid_filepath = Path("/test/imap_mag_l1a_burst_20210101_20210102_v01-01.cdf")
    expected_output["extension"] = "cdf"
    assert (
        ScienceFilePath.extract_filename_components(valid_filepath) == expected_output
    )

    invalid_ext = "imap_mag_l1a_burst_20210101_20210102_v01-01.txt"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath.extract_filename_components(invalid_ext)


def test_construct_sciencefilepathmanager():
    valid_filename = "imap_mag_l1a_burst_20210101_20210102_v01-01.cdf"
    sfm = ScienceFilePath(valid_filename)
    assert sfm.mission == "imap"
    assert sfm.instrument == "mag"
    assert sfm.data_level == "l1a"
    assert sfm.descriptor == "burst"
    assert sfm.start_date == "20210101"
    assert sfm.end_date == "20210102"
    assert sfm.version == "v01-01"
    assert sfm.extension == "cdf"

    invalid_filename = "imap_mag_l1a_burst_20210101_20210102_v01-01"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath(invalid_filename)

    invalid_filename = "imap_mag_l1a_burst_20210101_20210102_v01-01.pkts"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath(invalid_filename)

    invalid_filename = "imap_sdc_l1a_burst_20210101_20210102_v01-01.cdf"
    with pytest.raises(ScienceFilePath.InvalidScienceFileError):
        ScienceFilePath(invalid_filename)

    valid_filepath = Path("/test/imap_mag_l1a_burst_20210101_20210102_v01-01.cdf")
    sfm = ScienceFilePath(valid_filepath)

    assert sfm.instrument == "mag"
    assert sfm.data_level == "l1a"
    assert sfm.descriptor == "burst"
    assert sfm.start_date == "20210101"
    assert sfm.end_date == "20210102"
    assert sfm.version == "v01-01"
    assert sfm.extension == "cdf"


def test_is_valid_date():
    valid_date = "20210101"
    assert ScienceFilePath.is_valid_date(valid_date)

    invalid_date = "2021-01-01"
    assert not ScienceFilePath.is_valid_date(invalid_date)

    invalid_date = "20210132"
    assert not ScienceFilePath.is_valid_date(invalid_date)

    invalid_date = "2021010"
    assert not ScienceFilePath.is_valid_date(invalid_date)


def test_construct_upload_path():
    valid_filename = "imap_mag_l1a_burst_20210101_20210102_v01-01.cdf"
    sfm = ScienceFilePath(valid_filename)
    expected_output = imap_data_access.config["DATA_DIR"] / Path(
        "imap/mag/l1a/2021/01/imap_mag_l1a_burst_20210101_20210102_v01-01.cdf"
    )

    assert sfm.construct_path() == expected_output


def test_generate_from_inputs():
    sfm = ScienceFilePath.generate_from_inputs(
        "mag", "l1a", "burst", "20210101", "20210102", "v01-01"
    )
    expected_output = imap_data_access.config["DATA_DIR"] / Path(
        "imap/mag/l1a/2021/01/imap_mag_l1a_burst_20210101_20210102_v01-01.cdf"
    )

    assert sfm.construct_path() == expected_output
    assert sfm.instrument == "mag"
    assert sfm.data_level == "l1a"
    assert sfm.descriptor == "burst"
    assert sfm.start_date == "20210101"
    assert sfm.end_date == "20210102"
    assert sfm.version == "v01-01"
    assert sfm.extension == "cdf"

    sfm = ScienceFilePath.generate_from_inputs(
        "mag", "l0", "raw", "20210101", "20210102", "v01-01"
    )
    expected_output = imap_data_access.config["DATA_DIR"] / Path(
        "imap/mag/l0/2021/01/imap_mag_l0_raw_20210101_20210102_v01-01.pkts"
    )

    assert sfm.construct_path() == expected_output
