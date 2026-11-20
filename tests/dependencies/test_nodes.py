"""Tests for the dependency node types."""

import re

import pytest

import imap_data_access
from imap_data_access.dependencies import (
    SPICE_SOURCES,
    DataSource,
    DataType,
    DependencyNode,
    Node,
    ProcessingJobNode,
)


def test_valid_sources():
    """Sources are spin, repoint, spice, the SPICE file types and the instruments."""
    assert set(DataSource().valid_source) == {
        "spin",
        "repoint",
        "spice",
        *SPICE_SOURCES,
        *imap_data_access.VALID_INSTRUMENTS,
    }


def test_valid_types():
    """Types are the data levels plus spice, ancillary, spin, repoint, collection."""
    assert set(DataType().valid_type) == {
        "spice",
        "ancillary",
        "spin",
        "repoint",
        "collection",
        *imap_data_access.VALID_DATALEVELS,
    }


@pytest.mark.parametrize("source", ["swe", "leapseconds", "spice", "spin", "repoint"])
def test_node_accepts_source(source):
    assert Node(source, "l1a", "sci").source == source


def test_node_rejects_unknown_source():
    with pytest.raises(ValueError, match="Invalid data source 'not-a-source'"):
        Node("not-a-source", "l1a", "sci")


@pytest.mark.parametrize(
    "source",
    [
        "attitude_predict",
        "ephemeris_launch",
        "ephemeris_long",
        "lagrange_point",
        "metakernel",
    ],
)
def test_node_rejects_spice_types_outside_spice_sources(source):
    """File validation knows these SPICE types, but they aren't dependency sources."""
    with pytest.raises(ValueError, match=f"Invalid data source '{source}'"):
        Node(source, "spice", "historical")


def test_node_rejects_unknown_data_type():
    with pytest.raises(ValueError, match="Invalid data type 'l9'"):
        Node("swe", "l9", "sci")


@pytest.mark.parametrize("descriptor", ["", "   ", None])
def test_node_rejects_empty_descriptor(descriptor):
    with pytest.raises(ValueError, match="Descriptor must be a non-empty string"):
        Node("swe", "l1a", descriptor)


def test_dependency_node_validates_node_fields():
    with pytest.raises(ValueError, match="Invalid data source 'not-a-source'"):
        DependencyNode("not-a-source", "l1a", "sci")


def test_dependency_node_defaults():
    node = DependencyNode("swe", "l1a", "sci")
    assert node.required is True
    assert node.trigger_job is True
    assert node.dependency_query_time_range == []
    assert node.major_version == 1


@pytest.mark.parametrize(
    "date_range",
    [[], ["-3d", "5d"], ["-2h", "2h"], ["-3p", "3p"], ["-1l"], ["6np"], ["6nd"]],
)
def test_accepted_date_ranges(date_range):
    node = DependencyNode("swe", "l1a", "sci", dependency_query_time_range=date_range)
    assert node.dependency_query_time_range == date_range


@pytest.mark.parametrize(
    ("date_range", "message"),
    [
        pytest.param(["3d", "5d"], "Invalid past '3d'", id="positive past"),
        pytest.param(["-3d", "-5d"], "Invalid future '-5d'", id="negative future"),
        pytest.param(
            ["6np", "3d"],
            "Nearest need to be in this format",
            id="nearest with a future",
        ),
        pytest.param(
            ["-3d", "6nd"],
            "Nearest need to be in this format",
            id="nearest as the future",
        ),
        pytest.param(
            ["-3d", "3d", "1d"],
            "Date range must be a list of 1-2 elements",
            id="three elements",
        ),
        pytest.param(
            ("-3d", "3d"), "Date range must be a list of 1-2 elements", id="tuple"
        ),
        pytest.param(["-3w"], "Invalid past '-3w'", id="unknown past unit"),
        pytest.param(["-3d", "3w"], "Invalid future '3w'", id="unknown future unit"),
    ],
)
def test_rejected_date_ranges(date_range, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        DependencyNode("swe", "l1a", "sci", dependency_query_time_range=date_range)


@pytest.mark.parametrize(
    ("field", "value"),
    [("required", "yes"), ("required", None), ("trigger_job", 1)],
)
def test_required_and_trigger_job_must_be_booleans(field, value):
    with pytest.raises(
        ValueError, match="'required' and 'trigger_job' must be boolean values"
    ):
        DependencyNode("swe", "l1a", "sci", **{field: value})


def test_serialize_round_trip():
    node = DependencyNode(
        "hi",
        "l1b",
        "45sensor-de",
        required=False,
        trigger_job=False,
        dependency_query_time_range=["8np"],
        major_version=2,
    )
    serialized = node.serialize()
    assert serialized == {
        "source": "hi",
        "data_type": "l1b",
        "descriptor": "45sensor-de",
        "required": False,
        "trigger_job": False,
        "dependency_query_time_range": ["8np"],
        "major_version": 2,
    }
    assert DependencyNode.deserialize(serialized) == node


def test_processing_job_node_sorts_inputs():
    science = DependencyNode("swe", "l1a", "sci")
    ancillary = DependencyNode("swe", "ancillary", "esa-lut", trigger_job=False)
    leapseconds = DependencyNode(
        "leapseconds", "spice", "historical", trigger_job=False
    )
    attitude = DependencyNode("attitude_history", "spice", "historical")
    spin = DependencyNode("spin", "spin", "historical")
    repoint = DependencyNode("repoint", "repoint", "historical", trigger_job=False)
    inputs = [science, ancillary, leapseconds, attitude, spin, repoint]

    job = ProcessingJobNode(
        "swe", "l1b", "sci", inputs=inputs, outputs=[], partition="daily"
    )

    assert job.inputs == inputs
    assert job.science_inputs == [science]
    assert job.ancillary_inputs == [ancillary]
    assert job.spice_inputs == [leapseconds, attitude]
    assert job.spice_types == ["leapseconds", "attitude_history"]
    assert job.spin_input is spin
    assert job.repoint_input is repoint
    # Any kind of input can trigger the job.
    assert job.triggering_deps == [science, attitude, spin]


def test_processing_job_node_repoint_source_comes_first():
    """An input from the repoint source is the repoint input, whatever its type."""
    repoint = DependencyNode("repoint", "spice", "historical")
    job = ProcessingJobNode(
        "swe", "l1b", "sci", inputs=[repoint], outputs=[], partition="daily"
    )
    assert job.repoint_input is repoint
    assert job.spice_inputs == []


def test_processing_job_node_without_spin_or_repoint():
    job = ProcessingJobNode(
        "swe",
        "l1a",
        "all",
        inputs=[DependencyNode("swe", "l0", "raw")],
        outputs=[],
        partition="daily",
    )
    assert job.spin_input is None
    assert job.repoint_input is None
    assert job.spice_types == []


def test_processing_job_node_skips_node_validation():
    """ProcessingJobNode doesn't validate its own source, type or descriptor.

    The reader validates each job's key with a DependencyNode instead. This test
    pins that, so that adding validation here is a deliberate change.
    """
    job = ProcessingJobNode(
        "not-a-source", "not-a-type", "", inputs=[], outputs=[], partition="daily"
    )
    assert job.source == "not-a-source"
