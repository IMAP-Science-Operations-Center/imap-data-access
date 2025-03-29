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


@pytest.mark.xfail(reason="SPICE not completed")
def test_create_spice_files():
    one_file = processing_input.SPICEInput("imap_1000_100_1000_100_01.ap.bc")

    assert one_file.filename_list == ["imap_1000_100_1000_100_01.ap.bc"]
    assert len(one_file.imap_file_paths) == 1
    assert isinstance(one_file.imap_file_paths[0], SPICEFilePath)
    assert one_file.input_type == ProcessingInputType.SPICE_FILE
    assert one_file.source == "spice"


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


# Add a test for download()
def test_download_all_files(mock_urlopen):
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
    input_collection.download_all_files()
    # Check that the files are downloaded
    for file in input_collection.get_file_paths():
        assert file.exists()
