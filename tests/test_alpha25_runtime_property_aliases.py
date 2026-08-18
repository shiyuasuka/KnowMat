from knowmat.alpha25.runner_compat import property_name_without_unit_suffix


def test_unit_suffix_is_semantic_only_and_raw_property_name_is_retained():
    raw_name = "UTS (MPa)"

    assert property_name_without_unit_suffix(raw_name) == "UTS"
    assert raw_name == "UTS (MPa)"
