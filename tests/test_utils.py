from imap_data_access.utils import ImapProductCatalog


def test_mission_data_levels():
    """Test that we return expected data levels"""
    product_catalog = ImapProductCatalog()
    valid_datalevels = {
        "l0",
        "l1",
        "l1a",
        "l1b",
        "l1c",
        "l1d",
        "l2",
        "l2a",
        "l2b",
        "l3",
        "l3a",
        "l3b",
        "l3c",
        "l3d",
        "l3e",
    }
    assert set(product_catalog.data_levels()) == valid_datalevels


def test_instrument_data_levels():
    """Test that we return expected data levels for an instrument"""
    product_catalog = ImapProductCatalog()
    print(product_catalog.data_levels("mag"))
    assert set(product_catalog.data_levels("mag")) == {
        "l0",
        "l1a",
        "l1b",
        "l1c",
        "l1d",
        "l2",
    }


def test_science_descriptors():
    """Test that we return expected science descriptors for an instrument and level"""
    product_catalog = ImapProductCatalog()
    print(product_catalog.science_descriptors("swe", "l2"))
    assert set(product_catalog.science_descriptors("swe", "l2")) == {"sci"}


def test_ancillary_descriptors():
    """Test that we return expected ancillary descriptors for an instrument"""
    product_catalog = ImapProductCatalog()
    print(product_catalog.ancillary_descriptors("hi"))
    hi_ancillary_expected = {
        "45sensor-cal-prod",
        "45sensor-esa-energies",
        "45sensor-esa-eta-fit-factors",
        "90sensor-cal-prod",
        "90sensor-esa-energies",
        "90sensor-esa-eta-fit-factors",
        "45sensor-backgrounds",
        "90sensor-backgrounds",
    }
    assert set(product_catalog.ancillary_descriptors("hi")) == hi_ancillary_expected
