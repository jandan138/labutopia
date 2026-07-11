from tools.labutopia_fluid.presentation_look_profiles import (
    PRESENTATION_LOOK_NONE,
    REF_OMNIGLASS_GLASS_COLOR,
    REF_OMNIGLASS_REFLECTION_COLOR,
    is_weekly_omniglass_look,
    resolve_presentation_look_profile,
)


def test_none_preset_returns_official_clearwater_compatible_marker():
    profile = resolve_presentation_look_profile(None)
    assert profile["look_id"] == PRESENTATION_LOOK_NONE
    assert profile["official_visual_a_compatible"] is True
    assert profile["water_backend"] == "MDL_WATER"
    assert profile["water_sub_identifier"] == "OmniSurface_ClearWater"
    assert profile["postprocess"]["anisotropy_scale"] == 5.0


def test_empty_string_preset_is_none():
    profile = resolve_presentation_look_profile("")
    assert profile["look_id"] == PRESENTATION_LOOK_NONE


def test_weekly_b_uses_omniglass_water_and_lower_anisotropy():
    profile = resolve_presentation_look_profile("weekly_omniglass_B")
    assert profile["water_backend"] == "MDL_OMNIGLASS_WATER"
    assert profile["water_sub_identifier"] == "OmniGlass"
    assert profile["postprocess"]["anisotropy_scale"] == 2.0
    assert profile["postprocess"]["smoothing_strength"] == 0.65
    assert profile["postprocess"]["postprocess_hash"] == "anisotropy_2_1_2_smoothing_0_65_v1"
    assert profile["official_visual_a_compatible"] is False
    assert profile["beaker_override"]["target_mesh"] == "/World/beaker2/mesh"
    assert profile["lighting"]["lighting_contract_hash"] == "weekly_omniglass_intensity_v3"
    assert profile["camera"]["eye_z_above_table"] == 0.34
    assert profile["camera"]["focus_source_weight"] == 0.72
    assert profile["camera"]["main_hash"] == "weekly_omniglass_main_camera_v3"
    assert is_weekly_omniglass_look(profile["look_id"]) is True


def test_weekly_c_inherits_b_water_and_uses_exposure_lighting():
    profile = resolve_presentation_look_profile("weekly_omniglass_C")
    assert profile["water_backend"] == "MDL_OMNIGLASS_WATER"
    assert profile["glass_color"][0] == resolve_presentation_look_profile("weekly_omniglass_B")["glass_color"][0]
    assert profile["lighting"]["mode"] == "exposure_ct_ref_v1"
    assert profile["lighting"]["dome_exposure"] == 9.0
    assert profile["camera"]["capture_closeup"] is True
    assert profile["official_visual_a_compatible"] is False


def test_unknown_preset_raises():
    try:
        resolve_presentation_look_profile("nope")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unknown" in str(exc).lower() or "nope" in str(exc)


def test_resolve_returns_independent_copies():
    a = resolve_presentation_look_profile("weekly_omniglass_B")
    b = resolve_presentation_look_profile("weekly_omniglass_B")
    a["postprocess"]["anisotropy_scale"] = 99.0
    assert b["postprocess"]["anisotropy_scale"] == 2.0


def test_local_a18_reference_colors_are_pinned_in_profile_source_of_truth():
    profile = resolve_presentation_look_profile("weekly_omniglass_B")

    assert REF_OMNIGLASS_GLASS_COLOR == (
        0.73344165,
        0.9498069,
        0.94228774,
    )
    assert REF_OMNIGLASS_REFLECTION_COLOR == (
        0.6368421,
        0.9266409,
        0.88300306,
    )
    assert profile["glass_color"] == REF_OMNIGLASS_GLASS_COLOR
    assert profile["reflection_color"] == REF_OMNIGLASS_REFLECTION_COLOR
