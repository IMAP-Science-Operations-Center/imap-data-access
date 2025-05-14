import json
from datetime import datetime

import pytest

from imap_data_access import (
    AncillaryFilePath,
    ScienceFilePath,
    SPICEFilePath,
    processing_input,
)
from imap_data_access.processing_input import (
    AncillaryInput,
    ProcessingInputType,
    ScienceInput,
    SPICEInput,
    generate_imap_input,
)


def test_create_science_files():
    one_file = processing_input.ScienceInput("imap_mag_l1a_norm-magi_20240312_v000.cdf")
    two_files = processing_input.ScienceInput(
        "imap_mag_l1a_burst-magi_20240312_v000.cdf",
        "imap_mag_l1a_burst-magi_20240310_v000.cdf",
    )

    assert one_file.filename_list == ["imap_mag_l1a_norm-magi_20240312_v000.cdf"]
    assert len(one_file.imap_file_paths) == 1
    assert isinstance(one_file.imap_file_paths[0], ScienceFilePath)
    assert one_file.input_type == ProcessingInputType.SCIENCE_FILE
    assert one_file.source == "mag"
    assert one_file.descriptor == "norm-magi"
    assert one_file.data_type == "l1a"

    assert two_files.filename_list == [
        "imap_mag_l1a_burst-magi_20240312_v000.cdf",
        "imap_mag_l1a_burst-magi_20240310_v000.cdf",
    ]
    assert all([isinstance(obj, ScienceFilePath) for obj in two_files.imap_file_paths])
    assert len(two_files.imap_file_paths) == 2
    assert two_files.input_type == ProcessingInputType.SCIENCE_FILE
    assert two_files.source == "mag"
    assert two_files.descriptor == "burst-magi"
    assert two_files.data_type == "l1a"

    with pytest.raises(ValueError, match="same source"):
        processing_input.ScienceInput(
            "imap_mag_l1a_burst-magi_20240312_v000.cdf",
            "imap_mag_l1a_norm-magi_20240312_v000.cdf",
        )


def test_create_ancillary_files():
    one_file = processing_input.AncillaryInput("imap_mag_l1b-cal_20250101_v001.cdf")
    two_files = processing_input.AncillaryInput(
        "imap_mag_l1b-cal_20250101_v001.cdf",
        "imap_mag_l1b-cal_20250103_20250104_v002.cdf",
    )

    assert one_file.filename_list == ["imap_mag_l1b-cal_20250101_v001.cdf"]
    assert len(one_file.imap_file_paths) == 1
    assert isinstance(one_file.imap_file_paths[0], AncillaryFilePath)
    assert one_file.input_type == ProcessingInputType.ANCILLARY_FILE
    assert one_file.source == "mag"
    assert one_file.descriptor == "l1b-cal"
    assert one_file.data_type == "ancillary"

    assert two_files.filename_list == [
        "imap_mag_l1b-cal_20250101_v001.cdf",
        "imap_mag_l1b-cal_20250103_20250104_v002.cdf",
    ]
    assert len(two_files.imap_file_paths) == 2
    assert all(
        [isinstance(obj, AncillaryFilePath) for obj in two_files.imap_file_paths]
    )
    assert two_files.input_type == ProcessingInputType.ANCILLARY_FILE
    assert two_files.source == "mag"
    assert two_files.descriptor == "l1b-cal"
    assert two_files.data_type == "ancillary"

    with pytest.raises(ValueError, match="same source"):
        processing_input.AncillaryInput(
            "imap_mag_l1b-cal_20250101_v001.cdf",
            "imap_mag_l1b-cal_20250103_20250104_v002.cdf",
            "imap_mag_l1a-cal_20250105_v003.cdf",
        )


def test_spice_input():
    """Test SPICEInput class for different SPICE file types."""
    one_file = processing_input.SPICEInput("imap_1000_100_1000_100_01.ah.bc")

    assert one_file.filename_list == ["imap_1000_100_1000_100_01.ah.bc"]
    assert len(one_file.imap_file_paths) == 1
    assert isinstance(one_file.imap_file_paths[0], SPICEFilePath)
    assert one_file.input_type == ProcessingInputType.SPICE_FILE
    assert one_file.source == ["attitude_history"]
    assert one_file.descriptor == "historical"

    # Test with multiple SPICE files of the same type
    multiple_files = processing_input.SPICEInput(
        "imap_1000_100_1000_100_01.ah.bc",
        "imap_1000_100_1000_100_02.ap.bc",
    )

    assert multiple_files.filename_list == [
        "imap_1000_100_1000_100_01.ah.bc",
        "imap_1000_100_1000_100_02.ap.bc",
    ]
    assert len(multiple_files.imap_file_paths) == 2
    assert multiple_files.input_type == ProcessingInputType.SPICE_FILE
    assert multiple_files.source == ["attitude_history", "attitude_predict"]
    assert multiple_files.descriptor == "best"

    # Adding few more kernel types to test
    multiple_files = processing_input.SPICEInput(
        "naif0012.tls",
        "imap_sclk_0001.tsc",
        "pck00010.tpc",
        "imap_001.tf",
        "de440.bsp",
        "imap_90days_20260922_20261221_v01.bsp",
        "imap_1000_100_1000_100_01.ah.bc",
        "imap_1000_100_1000_100_02.ap.bc",
    )
    assert len(multiple_files.imap_file_paths) == 8
    assert multiple_files.input_type == ProcessingInputType.SPICE_FILE
    assert multiple_files.source == [
        "leapseconds",
        "spacecraft_clock",
        "planetary_constants",
        "frames",
        "planetary_ephemeris",
        "ephemeris_90days",
        "attitude_history",
        "attitude_predict",
    ]
    assert multiple_files.descriptor == "best"

    # Test historical ephemeris files
    ephemeris_file = processing_input.SPICEInput(
        "imap_recon_20260922_20261221_v01.bsp",
    )
    assert ephemeris_file.descriptor == "historical"

    # Test with multiple ephemeris files
    ephemeris_files = processing_input.SPICEInput(
        "imap_recon_20260922_20261221_v01.bsp",
        "imap_nom_20260922_20261221_v02.bsp",
        "imap_pred_20260922_20261221_v02.bsp",
    )
    assert ephemeris_files.descriptor == "best"

    # Test with a SPICE file containing "spin" in the source
    spin_file = processing_input.SpinInput("imap_1000_100_1000_100_01.spin.csv")

    assert spin_file.filename_list == ["imap_1000_100_1000_100_01.spin.csv"]
    assert len(spin_file.imap_file_paths) == 1
    assert spin_file.input_type == ProcessingInputType.SPICE_FILE
    assert spin_file.source == "spin"
    assert spin_file.descriptor == "historical"

    # Test with a SPICE file containing "repoint" in the source
    repoint_file = processing_input.RepointInput("imap_1000_100_01.repoint.csv")

    assert repoint_file.filename_list == ["imap_1000_100_01.repoint.csv"]
    assert len(repoint_file.imap_file_paths) == 1
    assert repoint_file.input_type == ProcessingInputType.SPICE_FILE
    assert repoint_file.source == "repoint"
    assert repoint_file.descriptor == "historical"

    # Test with invalid SPICE files (different sources)
    with pytest.raises(ValueError, match="SpinInput can only contain spin files."):
        processing_input.SpinInput(
            "imap_1000_100_1000_100_01.spin.csv",
            "imap_1000_001_02.repoint.csv",
        )

    # Test with multiple "repoint" files (should raise an error)
    with pytest.raises(
        ValueError, match="RepointInput can only contain one repoint file."
    ):
        processing_input.RepointInput(
            "imap_1000_001_02.repoint.csv",
            "imap_1000_001_03.repoint.csv",
        )
    # Try passing in spin or repoint files to the SPICEInput class
    with pytest.raises(
        ValueError, match="SPICEInput can only contain ephemeris or attitude file"
    ):
        processing_input.SPICEInput(
            "imap_1000_100_1000_100_01.spin.csv",
            "imap_1000_001_03.repoint.csv",
        )


def test_create_collection():
    ancillary = processing_input.AncillaryInput(
        "imap_mag_l1b-cal_20250101_v001.cdf",
        "imap_mag_l1b-cal_20250103_20250104_v002.cdf",
    )
    science = processing_input.ScienceInput(
        "imap_mag_l1a_norm-magi_20240312_v000.cdf",
        "imap_mag_l1a_norm-magi_20240312_v001.cdf",
    )
    input_collection = processing_input.ProcessingInputCollection(ancillary, science)

    assert len(input_collection.processing_input) == 2
    assert input_collection.processing_input[0].descriptor == "l1b-cal"
    assert input_collection.processing_input[1].descriptor == "norm-magi"
    deser = processing_input.ProcessingInputCollection()
    deser.deserialize(input_collection.serialize())

    assert len(deser.processing_input) == 2
    assert deser.processing_input[0].descriptor == "l1b-cal"
    assert deser.processing_input[1].descriptor == "norm-magi"
    assert deser.processing_input[0].input_type == ProcessingInputType.ANCILLARY_FILE
    assert deser.processing_input[1].input_type == ProcessingInputType.SCIENCE_FILE

    extra_files = processing_input.ProcessingInputCollection(
        processing_input.ScienceInput("imap_glows_l1a_hist_20250202_v001.cdf")
    )
    assert len(extra_files.processing_input) == 1
    deser.deserialize(extra_files.serialize())

    assert len(deser.processing_input) == 3
    assert deser.processing_input[2].descriptor == "hist"

    science_files = deser.get_science_inputs()
    assert len(science_files) == 2
    assert science_files[0].descriptor == "norm-magi"
    assert science_files[1].descriptor == "hist"
    assert len(science_files[0].imap_file_paths) == 2
    assert len(science_files[1].imap_file_paths) == 1

    glows_science_files = deser.get_science_inputs("glows")
    assert len(glows_science_files) == 1
    assert science_files[1].descriptor == "hist"
    assert len(science_files[1].imap_file_paths) == 1

    # Test collection with spice files
    spice_files = processing_input.SPICEInput(
        "naif0012.tls",
        "imap_sclk_0001.tsc",
        "pck00010.tpc",
        "imap_001.tf",
        "de440.bsp",
        "imap_90days_20260922_20261221_v01.bsp",
        "imap_1000_100_1000_100_01.ah.bc",
        "imap_1000_100_1000_100_02.ap.bc",
    )
    spin_files = processing_input.SpinInput(
        "imap_1000_100_1000_100_01.spin.csv",
        "imap_1000_100_1000_101_01.spin.csv",
    )
    repoint_files = processing_input.RepointInput(
        "imap_1000_001_03.repoint.csv",
    )
    spice_collection = processing_input.ProcessingInputCollection(
        spice_files, spin_files, repoint_files
    )
    assert len(spice_collection.processing_input) == 3
    expected_deserialized = [
        {
            "type": "spice",
            "files": [
                "naif0012.tls",
                "imap_sclk_0001.tsc",
                "pck00010.tpc",
                "imap_001.tf",
                "de440.bsp",
                "imap_90days_20260922_20261221_v01.bsp",
                "imap_1000_100_1000_100_01.ah.bc",
                "imap_1000_100_1000_100_02.ap.bc",
            ],
        },
        {
            "type": "spin",
            "files": [
                "imap_1000_100_1000_100_01.spin.csv",
                "imap_1000_100_1000_101_01.spin.csv",
            ],
        },
        {
            "type": "repoint",
            "files": [
                "imap_1000_001_03.repoint.csv",
            ],
        },
    ]
    assert spice_collection.serialize() == json.dumps(expected_deserialized)


def test_get_time_range():
    ancillary = processing_input.AncillaryInput(
        "imap_mag_l1b-cal_20250101_v001.cdf",
        "imap_mag_l1b-cal_20250103_20250104_v002.cdf",
    )

    start, end = ancillary.get_time_range()

    assert start == datetime.strptime("20250101", "%Y%m%d")
    assert end == datetime.strptime("20250104", "%Y%m%d")


def test_get_file_paths():
    # This example is fake example where we are processing HIT L2
    # and it has three dependencies, one primary dependent (HIT l1b)
    # and two ancillary dependents, MAG l1a and HIT ancillary.
    mag_sci_anc = ScienceInput(
        "imap_mag_l1a_norm-magi_20240312_v000.cdf",
        "imap_mag_l1a_norm-magi_20240312_v001.cdf",
    )
    hit_anc = AncillaryInput(
        "imap_hit_l1b-cal_20240312_v000.cdf",
    )
    hit_sci = ScienceInput(
        "imap_hit_l1b_sci_20240312_v000.cdf",
    )

    input_collection = processing_input.ProcessingInputCollection(
        mag_sci_anc, hit_anc, hit_sci
    )
    hit_sci_files = input_collection.get_file_paths("hit", "sci")
    assert len(hit_sci_files) == 1

    hit_anc_files = input_collection.get_file_paths("hit", "l1b-cal")
    assert len(hit_anc_files) == 1
    expected_path = AncillaryFilePath(
        "imap_hit_l1b-cal_20240312_v000.cdf"
    ).construct_path()
    assert hit_anc_files == [expected_path]

    mag_sci_files = input_collection.get_file_paths("mag", "norm-magi")
    assert len(mag_sci_files) == 2

    all_hit_files = input_collection.get_file_paths("hit")
    assert len(all_hit_files) == 2

    all_mag_files = input_collection.get_file_paths(descriptor="norm-magi")
    assert len(all_mag_files) == 2

    all_files = input_collection.get_file_paths()
    assert len(all_files) == 4


def test_get_file_paths_descriptor():
    # Example where we have 2 ultra 45 sensor files, 1 ultra 90 sensor file.
    # Also have an unrelated mag file and 1 hi 45, 1 hi 90 file.
    # Test that we can get all the ultra 45/90 files, hi 45/90 files, etc.
    # by filtering by sensor and/or instrument.
    ultra_sci_45sensor = ScienceInput(
        "imap_ultra_l1c_45sensor-pset_20240312_v000.cdf",
        "imap_ultra_l1c_45sensor-pset_20240313_v000.cdf",
    )
    ultra_sci_90sensor = ScienceInput(
        "imap_ultra_l1c_90sensor-pset_20240312_v000.cdf",
    )
    hi_sci_45sensor = ScienceInput(
        "imap_hi_l1c_45sensor-pset_20240312_v000.cdf",
    )
    hi_sci_90sensor = ScienceInput(
        "imap_hi_l1c_90sensor-pset_20240312_v000.cdf",
    )
    mag_sci_anc = ScienceInput(
        "imap_mag_l1a_norm-magi_20240312_v000.cdf",
    )
    spice_files = processing_input.SPICEInput(
        "imap_1000_100_1000_100_01.ah.bc",
        "imap_1000_100_1000_100_02.ap.bc",
    )
    spin_files = processing_input.SpinInput(
        "imap_1000_100_1000_100_01.spin.csv",
        "imap_1000_100_1000_101_01.spin.csv",
    )
    repoint_files = processing_input.RepointInput(
        "imap_1000_001_03.repoint.csv",
    )

    input_collection = processing_input.ProcessingInputCollection(
        ultra_sci_45sensor,
        ultra_sci_90sensor,
        hi_sci_45sensor,
        hi_sci_90sensor,
        mag_sci_anc,
        spice_files,
        spin_files,
        repoint_files,
    )

    all_ultra_files = input_collection.get_file_paths(
        source="ultra", descriptor="sensor-pset"
    )
    assert len(all_ultra_files) == 3

    all_ultra_files = input_collection.get_file_paths(descriptor="sensor-pset")
    assert len(all_ultra_files) == 5

    all_ultra45_files = input_collection.get_file_paths(
        source="ultra", descriptor="45se"
    )
    assert len(all_ultra45_files) == 2

    all_ultra90_files = input_collection.get_file_paths(
        source="ultra", descriptor="90sens"
    )
    assert len(all_ultra90_files) == 1

    all_hi_files = input_collection.get_file_paths(source="hi")
    assert len(all_hi_files) == 2

    all_hi45_files = input_collection.get_file_paths(source="hi", descriptor="45se")
    assert len(all_hi45_files) == 1

    all_hi90_files = input_collection.get_file_paths(source="hi", descriptor="90se")
    assert len(all_hi90_files) == 1

    all_files = input_collection.get_file_paths()
    assert len(all_files) == 11

    all_spice_files = input_collection.get_file_paths(data_type="spice")
    assert len(all_spice_files) == 2
    all_spin_files = input_collection.get_file_paths(data_type="spin")
    assert len(all_spin_files) == 2
    all_repoint_files = input_collection.get_file_paths(data_type="repoint")
    assert len(all_repoint_files) == 1


def test_download_all_files():
    # This example is fake example where we are processing HIT L2
    # and it has three dependencies, one primary dependent (HIT l1b)
    # and two ancillary dependents, MAG l1a and HIT ancillary.
    mag_sci_anc = ScienceInput(
        "imap_mag_l1a_norm-magi_20240312_v000.cdf",
        "imap_mag_l1a_norm-magi_20240312_v001.cdf",
    )
    hit_anc = AncillaryInput(
        "imap_hit_l1b-cal_20240312_v000.cdf",
    )
    hit_sci = ScienceInput(
        "imap_hit_l1b_sci_20240312_v000.cdf",
    )
    spice_files = processing_input.SPICEInput(
        "naif0012.tls", "imap_sclk_0001.tsc", "imap_1000_100_1000_100_01.ah.bc"
    )
    spin_files = processing_input.SpinInput(
        "imap_1000_100_1000_100_01.spin.csv",
    )
    repoint_files = processing_input.RepointInput(
        "imap_1000_001_03.repoint.csv",
    )

    input_collection = processing_input.ProcessingInputCollection(
        mag_sci_anc, hit_anc, hit_sci, spice_files, spin_files, repoint_files
    )
    input_collection.download_all_files()
    # Check that the files are downloaded
    for file in input_collection.get_file_paths():
        assert file.exists()


def test_get_valid_inputs_for_start_date():
    mag_sci_anc = ScienceInput(
        "imap_mag_l1a_norm-magi_20250101_v000.cdf",
        "imap_mag_l1a_norm-magi_20250102_v001.cdf",
    )
    hit_anc = AncillaryInput(
        "imap_hit_l1b-cal_20250101_v000.cdf",
        "imap_hit_l1b-cal_20240102_20260101_v000.cdf",
        "imap_hit_l1b-cal_20250103_v000.cdf",
    )
    hit_sci = ScienceInput(
        "imap_hit_l1b_sci_20250101_v000.cdf",
        "imap_hit_l1b_sci_20250102_v000.cdf",
    )
    input_collection = processing_input.ProcessingInputCollection(
        mag_sci_anc, hit_anc, hit_sci
    )
    date = datetime(2025, 1, 1)

    valid_collection_latest = input_collection.get_valid_inputs_for_start_date(
        date, return_latest_ancillary=True
    )
    valid_collection = input_collection.get_valid_inputs_for_start_date(date)
    for collection in [valid_collection, valid_collection_latest]:
        assert len(collection.processing_input) == 3
        assert collection.processing_input[0].descriptor == "norm-magi"
        assert len(collection.processing_input[0].imap_file_paths) == 1
        assert (
            datetime.strptime(
                collection.processing_input[0].imap_file_paths[0].start_date, "%Y%m%d"
            )
            == date
        )
        assert collection.processing_input[1].descriptor == "l1b-cal"
        assert (
            datetime.strptime(
                collection.processing_input[1].imap_file_paths[0].start_date, "%Y%m%d"
            )
            == date
        )
        assert collection.processing_input[2].descriptor == "sci"
        assert len(collection.processing_input[2].imap_file_paths) == 1
        assert (
            datetime.strptime(
                collection.processing_input[2].imap_file_paths[0].start_date, "%Y%m%d"
            )
            == date
        )

    assert len(valid_collection.processing_input[1].imap_file_paths) == 2
    assert len(valid_collection_latest.processing_input[1].imap_file_paths) == 1


def test_get_processing_inputs():
    ultra_sci_45sensor = ScienceInput(
        "imap_ultra_l1c_45sensor-pset_20240312_v000.cdf",
        "imap_ultra_l1c_45sensor-pset_20240313_v000.cdf",
    )
    ultra_sci_90sensor = ScienceInput(
        "imap_ultra_l1c_90sensor-pset_20240312_v000.cdf",
    )
    hi_sci_45sensor = ScienceInput(
        "imap_hi_l1c_45sensor-pset_20240312_v000.cdf",
    )
    hi_sci_90sensor = ScienceInput(
        "imap_hi_l1c_90sensor-pset_20240312_v000.cdf",
    )
    mag_sci_anc = ScienceInput(
        "imap_mag_l1a_norm-magi_20240312_v000.cdf",
    )
    hit_anc = AncillaryInput(
        "imap_hit_l1b-cal_20250101_v000.cdf",
    )

    input_collection = processing_input.ProcessingInputCollection(
        ultra_sci_45sensor,
        ultra_sci_90sensor,
        hi_sci_45sensor,
        hi_sci_90sensor,
        mag_sci_anc,
        hit_anc,
    )

    # Get all inputs
    all_inputs = input_collection.get_processing_inputs()
    assert len(all_inputs) == 6

    # Get all science inputs
    science_inputs = input_collection.get_processing_inputs(
        input_type=ProcessingInputType.SCIENCE_FILE
    )
    assert len(science_inputs) == 5

    # Get all ancillary inputs
    ancillary_inputs = input_collection.get_processing_inputs(
        input_type=ProcessingInputType.ANCILLARY_FILE
    )
    assert len(ancillary_inputs) == 1

    # Get all ultra inputs
    ultra_inputs = input_collection.get_processing_inputs(source="ultra")
    assert len(ultra_inputs) == 2

    # multiple filters
    hit_anc_inputs = input_collection.get_processing_inputs(
        source="hit", input_type=ProcessingInputType.ANCILLARY_FILE
    )
    assert len(hit_anc_inputs) == 1

    data_level_inputs = input_collection.get_processing_inputs(data_type="l1c")
    assert len(data_level_inputs) == 4


def test_generate_imap_input():
    """Test the generate_imap_input function for different file types."""

    # Test with a SPICE file
    spice_file = "imap_1000_100_1000_100_01.ah.bc"
    result = generate_imap_input(spice_file)
    assert isinstance(result, SPICEInput)
    assert result.source == ["attitude_history"]
    assert result.descriptor == "historical"
    assert result.data_type == "spice"

    # Test with a Science file
    science_file = "imap_mag_l1a_norm-magi_20250101_v000.cdf"
    result = generate_imap_input(science_file)
    assert isinstance(result, ScienceInput)
    assert result.source == "mag"
    assert result.descriptor == "norm-magi"
    assert result.data_type == "l1a"

    # Test with an Ancillary file
    ancillary_file = "imap_hit_l1b-cal_20250101_v000.cdf"
    result = generate_imap_input(ancillary_file)
    assert isinstance(result, AncillaryInput)
    assert result.source == "hit"
    assert result.descriptor == "l1b-cal"
    assert result.data_type == "ancillary"

    # Test with an invalid file type
    invalid_file = "invalid_file_type.txt"
    with pytest.raises(ValueError, match="Invalid input type"):
        generate_imap_input(invalid_file)
