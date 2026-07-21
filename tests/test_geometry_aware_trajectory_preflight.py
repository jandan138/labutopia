from __future__ import annotations

import copy
import hashlib
import json
import math
import signal
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest
import yaml

from tools.labutopia_fluid import run_geometry_aware_trajectory_preflight as probe


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLED_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_geometry_aware_trajectory_preflight_600hz_step600_layout_v1.yaml"
)
SOURCE_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_close_only_600hz_step600_layout_v1.yaml"
)
REQUESTED_OPEN_TARGET_M = 0.040
MEASURED_OPEN_TARGET_M = 0.0399998
MEASURED_OPEN_TOLERANCE_M = 2.0e-7
COOKED_AABB_PRECISION = {
    "value_type": "float32",
    "authority": "physx_property_query_float32_local_aabb_v1",
}


def test_controlled_contact_runtime_limits_are_explicit_and_frozen():
    fluid = yaml.safe_load(CONTROLLED_CONFIG.read_text(encoding="utf-8"))[
        "online_fluid"
    ]

    assert fluid["controlled_contact_baseline_collider_pairs"] == [
        ["/World/beaker2/mesh", "/World/table/surface/mesh"]
    ]
    assert fluid["controlled_contact_normal_convention"] == "actor0_to_actor1"
    assert fluid["controlled_contact_maximum_penetration_m"] == 0.001
    assert (
        fluid["controlled_contact_maximum_precontact_relative_speed_m_s"]
        == 0.008
    )
    assert fluid["controlled_contact_maximum_close_relative_speed_m_s"] == 0.002
    assert fluid["controlled_contact_maximum_step_normal_impulse_n_s"] == 0.001
    assert fluid["controlled_contact_maximum_step_total_impulse_n_s"] == 0.001
    assert fluid["controlled_contact_maximum_episode_normal_impulse_n_s"] == 1.5
    assert fluid["controlled_contact_maximum_episode_total_impulse_n_s"] == 1.5
    assert fluid["grasp_preclose_source_translation_limit_m"] == 0.001
    assert fluid["grasp_preclose_source_tilt_limit_degrees"] == 0.5
    assert fluid["controlled_contact_maximum_source_linear_speed_m_s"] == 0.002
    assert fluid["controlled_contact_maximum_source_angular_speed_degrees_s"] == 1.0
    assert fluid["controlled_contact_maximum_postcontact_source_path_m"] == 0.005
    assert (
        fluid["controlled_contact_maximum_postcontact_angular_variation_degrees"]
        == 2.5
    )
    assert fluid["controlled_contact_settle_required_steps"] == 60
    assert fluid["controlled_contact_precontact_settle_required_steps"] == 60
    assert fluid["controlled_contact_close_required_steps"] == 5
    assert fluid["controlled_contact_contact_settle_required_steps"] == 60
    assert fluid["expert_pick_position_threshold_m"] == 0.0005
    assert fluid["expert_pick_orientation_threshold_degrees"] == 0.5
    assert fluid["controlled_contact_pregrasp_deadline_steps"] == 3000
    assert fluid["controlled_contact_align_deadline_steps"] == 9000
    assert fluid["controlled_contact_insert_deadline_steps"] == 7200
    assert fluid["controlled_contact_settle_deadline_steps"] == 600
    assert fluid["controlled_contact_precontact_settle_deadline_steps"] == 300
    assert fluid["controlled_contact_close_deadline_steps"] == 900
    assert fluid["controlled_contact_contact_settle_deadline_steps"] == 300
    assert fluid["controlled_contact_maximum_downward_coast_m"] == 0.001
    assert fluid["controlled_contact_maximum_settled_tool_speed_m_s"] == 0.002


def _controlled_contact_contract():
    return {
        "known_body_paths": [
            "/World/Franka/panda_hand",
            "/World/Franka/panda_leftfinger",
            "/World/Franka/panda_rightfinger",
            "/World/beaker1",
            "/World/beaker2",
            "/World/table",
        ],
        "known_collider_paths": [
            "/World/Franka/panda_hand/collider",
            "/World/Franka/panda_leftfinger/pad",
            "/World/Franka/panda_leftfinger/knuckle",
            "/World/Franka/panda_rightfinger/pad",
            "/World/beaker1/mesh",
            "/World/beaker2/mesh",
            "/World/table/surface/mesh",
        ],
        "robot_body_paths": [
            "/World/Franka/panda_hand",
            "/World/Franka/panda_leftfinger",
            "/World/Franka/panda_rightfinger",
        ],
        "intended_pairs": [
            {
                "side": "left",
                "finger_body_path": "/World/Franka/panda_leftfinger",
                "finger_collider_path": "/World/Franka/panda_leftfinger/pad",
                "source_body_path": "/World/beaker2",
                "source_collider_path": "/World/beaker2/mesh",
                "expected_inward_normal_world": [0.0, 1.0, 0.0],
            },
            {
                "side": "right",
                "finger_body_path": "/World/Franka/panda_rightfinger",
                "finger_collider_path": "/World/Franka/panda_rightfinger/pad",
                "source_body_path": "/World/beaker2",
                "source_collider_path": "/World/beaker2/mesh",
                "expected_inward_normal_world": [0.0, -1.0, 0.0],
            },
        ],
        "baseline_nonrobot_pairs": [
            {
                "body_paths": ["/World/beaker2", "/World/table"],
                "collider_paths": [
                    "/World/beaker2/mesh",
                    "/World/table/surface/mesh",
                ],
            }
        ],
        "source_center_world_m": [0.0, 0.0, 1.0],
        "source_axis_world": [0.0, 0.0, 1.0],
        "grasp_height_band_m": [-0.02, 0.02],
        "minimum_inward_normal_cosine": 0.8,
        "maximum_penetration_m": 0.001,
        "maximum_precontact_relative_speed_m_s": 0.008,
        "maximum_close_relative_speed_m_s": 0.002,
        "maximum_manifold_normal_impulse_n_s": 0.001,
    }


def _controlled_contact(
    *,
    body0="/World/Franka/panda_leftfinger",
    collider0="/World/Franka/panda_leftfinger/pad",
    body1="/World/beaker2",
    collider1="/World/beaker2/mesh",
    normal=(0.0, 1.0, 0.0),
    relative_speed_m_s=0.001,
    separation_m=-0.0001,
    impulses=(0.0004, 0.0005),
):
    return {
        "body0_path": body0,
        "collider0_path": collider0,
        "body1_path": body1,
        "collider1_path": collider1,
        "manifold_points": [
            {
                "position_m": [0.0, 0.0, 1.0],
                "normal_body0_to_body1_world": list(normal),
                "separation_m": separation_m,
                "relative_speed_m_s": relative_speed_m_s,
                "normal_impulse_n_s": impulse,
            }
            for impulse in impulses
        ],
    }


def _classify_controlled_contacts(phase, contacts):
    return probe.evaluate_controlled_contact_sample(
        physics_step=120,
        phase=phase,
        contacts=contacts,
        **_controlled_contact_contract(),
    )


def test_controlled_contact_classifier_covers_background_and_allowed_phases():
    background = _controlled_contact(
        body0="/World/beaker2",
        collider0="/World/beaker2/mesh",
        body1="/World/table",
        collider1="/World/table/surface/mesh",
        impulses=(),
    )
    result = _classify_controlled_contacts("INSERT", [background])
    assert result["class_counts"] == {"BACKGROUND": 1}
    assert result["terminal_kind"] is None
    assert result["precontact_latch"] is None

    for phase in ("INSERT", "SETTLE", "PRECONTACT_SETTLE"):
        result = _classify_controlled_contacts(phase, [_controlled_contact()])
        assert result["class_counts"] == {"INTENDED_PRECONTACT": 1}
        assert result["precontact_latch"]["physics_step"] == 120
        assert result["precontact_latch"]["sides"] == ["left"]
        assert result["terminal_kind"] is None

    for phase in ("CLOSE", "CONTACT_SETTLE"):
        result = _classify_controlled_contacts(phase, [_controlled_contact()])
        assert result["class_counts"] == {"INTENDED_CLOSE_CONTACT": 1}
        assert result["precontact_latch"] is None
        assert result["terminal_kind"] is None


def test_controlled_contact_classifier_is_total_and_checks_complete_manifold():
    finite_breaches = []
    too_high = _controlled_contact()
    too_high["manifold_points"][1]["position_m"][2] = 1.021
    finite_breaches.append(too_high)
    finite_breaches.append(_controlled_contact(relative_speed_m_s=0.008001))
    finite_breaches.append(_controlled_contact(separation_m=-0.001001))
    finite_breaches.append(_controlled_contact(impulses=(0.0006, 0.0005)))
    wrong_normal = _controlled_contact()
    wrong_normal["manifold_points"][0]["normal_body0_to_body1_world"] = [0, -1, 0]
    finite_breaches.append(wrong_normal)

    for contact in finite_breaches:
        result = _classify_controlled_contacts("INSERT", [contact])
        assert result["class_counts"] == {"PROHIBITED_CONTACT": 1}
        assert result["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"

    close_too_fast = _classify_controlled_contacts(
        "CLOSE", [_controlled_contact(relative_speed_m_s=0.002001)]
    )
    assert close_too_fast["class_counts"] == {"PROHIBITED_CONTACT": 1}

    missing = _controlled_contact()
    del missing["manifold_points"][0]["relative_speed_m_s"]
    result = _classify_controlled_contacts("INSERT", [missing])
    assert result["class_counts"] == {"UNKNOWN_CONTACT": 1}
    assert result["terminal_kind"] == "PROTOCOL_FAILURE"


def test_controlled_contact_classifier_rejects_nonpad_new_background_and_unknown():
    nonpad = _controlled_contact(
        collider0="/World/Franka/panda_leftfinger/knuckle"
    )
    assert _classify_controlled_contacts("INSERT", [nonpad])["terminal_kind"] == (
        "PHYSICAL_CONTACT_FAILURE"
    )

    new_background = _controlled_contact(
        body0="/World/beaker2",
        collider0="/World/beaker2/mesh",
        body1="/World/beaker1",
        collider1="/World/beaker1/mesh",
        impulses=(),
    )
    assert _classify_controlled_contacts("INSERT", [new_background])[
        "terminal_kind"
    ] == "PHYSICAL_CONTACT_FAILURE"

    unknown = _controlled_contact(body1="/World/unknown")
    assert _classify_controlled_contacts("INSERT", [unknown])["terminal_kind"] == (
        "PROTOCOL_FAILURE"
    )


def test_controlled_contact_classifier_canonicalizes_and_applies_precedence():
    reversed_contact = _controlled_contact(
        body0="/World/beaker2",
        collider0="/World/beaker2/mesh",
        body1="/World/Franka/panda_leftfinger",
        collider1="/World/Franka/panda_leftfinger/pad",
        normal=(0.0, -1.0, 0.0),
    )
    forward = _classify_controlled_contacts("INSERT", [_controlled_contact()])
    reverse = _classify_controlled_contacts("INSERT", [reversed_contact])
    assert reverse["records"] == forward["records"]
    assert reverse["evidence_sha256"] == forward["evidence_sha256"]

    right = _controlled_contact(
        body0="/World/Franka/panda_rightfinger",
        collider0="/World/Franka/panda_rightfinger/pad",
        normal=(0.0, -1.0, 0.0),
    )
    bilateral = _classify_controlled_contacts(
        "INSERT", [_controlled_contact(), right]
    )
    assert bilateral["precontact_latch"]["sides"] == ["left", "right"]

    prohibited = _controlled_contact(body0="/World/Franka/panda_hand")
    mixed = _classify_controlled_contacts(
        "INSERT", [_controlled_contact(), prohibited]
    )
    assert mixed["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"
    assert mixed["precontact_latch"] is None

    unknown = _controlled_contact(body1="/World/unknown")
    highest = _classify_controlled_contacts("INSERT", [prohibited, unknown])
    assert highest["terminal_kind"] == "PROTOCOL_FAILURE"


def _postcontact_samples(*, coast_m=0.0008, numeric_error_m=0.0):
    samples = [
        {
            "physics_step": 100,
            "tool_position_m": [0.0, 0.0, 1.0],
            "tool_linear_speed_m_s": 0.008,
            "source_translation_m": 0.0002,
            "source_tilt_degrees": 0.1,
            "source_linear_speed_m_s": 0.001,
            "source_angular_speed_degrees_s": 0.5,
            "position_error_m": 0.0002,
            "orientation_error_degrees": 0.2,
            "numeric_error_m": numeric_error_m,
        }
    ]
    for index in range(1, 61):
        progress = coast_m * index / 60.0
        samples.append(
            {
                "physics_step": 100 + index,
                "tool_position_m": [0.0, 0.0, 1.0 - progress],
                "tool_linear_speed_m_s": 0.001,
                "source_translation_m": 0.0005,
                "source_tilt_degrees": 0.2,
                "source_linear_speed_m_s": 0.001,
                "source_angular_speed_degrees_s": 0.5,
                "position_error_m": 0.0002,
                "orientation_error_degrees": 0.2,
                "numeric_error_m": numeric_error_m,
            }
        )
    return samples


def test_postcontact_settle_measures_physical_coast_not_command_increment():
    result = probe.evaluate_postcontact_settle(
        samples=_postcontact_samples(),
        first_contact_physics_step=100,
        approach_direction_world=[0.0, 0.0, -1.0],
        maximum_downward_coast_m=0.001,
        required_settled_steps=60,
        maximum_tool_speed_m_s=0.002,
        maximum_source_translation_m=0.001,
        maximum_source_tilt_degrees=0.5,
        maximum_source_linear_speed_m_s=0.002,
        maximum_source_angular_speed_degrees_s=1.0,
        maximum_position_error_m=0.0005,
        maximum_orientation_error_degrees=0.5,
    )
    assert result["maximum_downward_coast_m"] == pytest.approx(0.0008)
    assert result["maximum_downward_coast_m"] > 0.0002
    assert result["settled_step_count"] == 60
    assert result["passed"] is True


def test_postcontact_settle_fails_closed_on_overshoot_gap_and_outward_error():
    overshoot = probe.evaluate_postcontact_settle(
        samples=_postcontact_samples(coast_m=0.001001),
        first_contact_physics_step=100,
        approach_direction_world=[0.0, 0.0, -1.0],
        maximum_downward_coast_m=0.001,
        required_settled_steps=60,
        maximum_tool_speed_m_s=0.002,
        maximum_source_translation_m=0.001,
        maximum_source_tilt_degrees=0.5,
        maximum_source_linear_speed_m_s=0.002,
        maximum_source_angular_speed_degrees_s=1.0,
        maximum_position_error_m=0.0005,
        maximum_orientation_error_degrees=0.5,
    )
    assert overshoot["terminal_kind"] == "PHYSICAL_MOTION_FAILURE"
    assert overshoot["passed"] is False

    gapped_samples = _postcontact_samples()
    gapped_samples[12]["physics_step"] += 1
    gapped = probe.evaluate_postcontact_settle(
        samples=gapped_samples,
        first_contact_physics_step=100,
        approach_direction_world=[0.0, 0.0, -1.0],
        maximum_downward_coast_m=0.001,
        required_settled_steps=60,
        maximum_tool_speed_m_s=0.002,
        maximum_source_translation_m=0.001,
        maximum_source_tilt_degrees=0.5,
        maximum_source_linear_speed_m_s=0.002,
        maximum_source_angular_speed_degrees_s=1.0,
        maximum_position_error_m=0.0005,
        maximum_orientation_error_degrees=0.5,
    )
    assert gapped["terminal_kind"] == "PROTOCOL_FAILURE"

    outward = probe.evaluate_postcontact_settle(
        samples=_postcontact_samples(coast_m=0.001, numeric_error_m=1.0e-9),
        first_contact_physics_step=100,
        approach_direction_world=[0.0, 0.0, -1.0],
        maximum_downward_coast_m=0.001,
        required_settled_steps=60,
        maximum_tool_speed_m_s=0.002,
        maximum_source_translation_m=0.001,
        maximum_source_tilt_degrees=0.5,
        maximum_source_linear_speed_m_s=0.002,
        maximum_source_angular_speed_degrees_s=1.0,
        maximum_position_error_m=0.0005,
        maximum_orientation_error_degrees=0.5,
    )
    assert outward["terminal_kind"] == "PHYSICAL_MOTION_FAILURE"


def test_controlled_authorization_ledger_key_is_one_per_go_and_bundle(tmp_path):
    go_report = probe._canonical_json_bytes(
        {
            "schema_version": 1,
            "decision": "GEOMETRY_AWARE_CONTROLLED_CONTACT_PREFLIGHT_GO",
            "run_identity_sha256": "a" * 64,
        },
        indent=2,
    )
    bundle = {
        "schema_version": 1,
        "filled_config_sha256": "b" * 64,
        "treatment_sha256": "c" * 64,
    }
    first = probe.build_controlled_authorization_record(
        go_report_bytes=go_report,
        filled_bundle=bundle,
        authorization_id="1" * 64,
        attempt_path=tmp_path / "attempt-1",
    )
    second = probe.build_controlled_authorization_record(
        go_report_bytes=go_report,
        filled_bundle=bundle,
        authorization_id="2" * 64,
        attempt_path=tmp_path / "attempt-2",
    )
    assert first["ledger_key_sha256"] == second["ledger_key_sha256"]
    assert first["authorization_id"] != second["authorization_id"]
    assert first["attempt_path"] != second["attempt_path"]

    with pytest.raises(ValueError, match="controlled_authorization_bundle_invalid"):
        probe.build_controlled_authorization_record(
            go_report_bytes=go_report,
            filled_bundle={**bundle, "authorization_id": "3" * 64},
            authorization_id="3" * 64,
            attempt_path=tmp_path / "attempt-3",
        )

    no_go = probe._canonical_json_bytes(
        {
            "schema_version": 1,
            "decision": "GEOMETRY_AWARE_CONTROLLED_CONTACT_PREFLIGHT_NO_GO",
            "run_identity_sha256": "a" * 64,
        },
        indent=2,
    )
    with pytest.raises(ValueError, match="controlled_authorization_go_invalid"):
        probe.build_controlled_authorization_record(
            go_report_bytes=no_go,
            filled_bundle=bundle,
            authorization_id="4" * 64,
            attempt_path=tmp_path / "attempt-4",
        )


def _settle_samples(target_m: float, *, first_step: int) -> list[dict]:
    return [
        {
            "physics_step": first_step + index,
            "joint_positions_m": [target_m, target_m],
            "api_pad_velocity_m_s": [0.0, 0.0],
            "finite_difference_pad_velocity_m_s": [0.0, 0.0],
        }
        for index in range(60)
    ]


def _aperture_points() -> list[dict]:
    return [
        {
            "target_m": 0.040,
            "commanded_target_m": MEASURED_OPEN_TARGET_M,
            "joint_positions_m": [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M],
            "cooked_inner_gap_m": 0.0774,
            "lower_limits_m": [0.0, 0.0],
            "upper_limits_m": [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M],
            "settled_duration_s": 0.10,
            "measured_settling_time_s": 0.05,
            "settled_api_velocity_m_s": [0.0, 0.0],
            "settled_finite_difference_velocity_m_s": [0.0, 0.0],
            "settle_samples": _settle_samples(MEASURED_OPEN_TARGET_M, first_step=100),
        },
        {
            "target_m": 0.039,
            "commanded_target_m": 0.039,
            "joint_positions_m": [0.0390, 0.0389],
            "cooked_inner_gap_m": 0.0753,
            "lower_limits_m": [0.0, 0.0],
            "upper_limits_m": [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M],
            "settled_duration_s": 0.10,
            "measured_settling_time_s": 0.05,
            "settled_api_velocity_m_s": [0.0, 0.0],
            "settled_finite_difference_velocity_m_s": [0.0, 0.0],
            "settle_samples": _settle_samples(0.039, first_step=200),
        },
        {
            "target_m": 0.038,
            "commanded_target_m": 0.038,
            "joint_positions_m": [0.0380, 0.0379],
            "cooked_inner_gap_m": 0.0733,
            "lower_limits_m": [0.0, 0.0],
            "upper_limits_m": [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M],
            "settled_duration_s": 0.10,
            "measured_settling_time_s": 0.05,
            "settled_api_velocity_m_s": [0.0, 0.0],
            "settled_finite_difference_velocity_m_s": [0.0, 0.0],
            "settle_samples": _settle_samples(0.038, first_step=300),
        },
        {
            "target_m": 0.037,
            "commanded_target_m": 0.037,
            "joint_positions_m": [0.0370, 0.0369],
            "cooked_inner_gap_m": 0.0713,
            "lower_limits_m": [0.0, 0.0],
            "upper_limits_m": [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M],
            "settled_duration_s": 0.10,
            "measured_settling_time_s": 0.05,
            "settled_api_velocity_m_s": [0.0, 0.0],
            "settled_finite_difference_velocity_m_s": [0.0, 0.0],
            "settle_samples": _settle_samples(0.037, first_step=400),
        },
    ]


def _velocity_samples() -> list[dict]:
    return [
        {
            "api_pad_velocity_m_s": [-0.0030, -0.0029],
            "finite_difference_pad_velocity_m_s": [-0.0031, -0.0028],
        },
        {
            "api_pad_velocity_m_s": [-0.0012, -0.0011],
            "finite_difference_pad_velocity_m_s": [-0.0011, -0.0012],
        },
    ]


def _evaluate_aperture(points=None, velocities=None):
    return probe.evaluate_aperture_calibration(
        points=_aperture_points() if points is None else points,
        velocity_samples=_velocity_samples() if velocities is None else velocities,
        expected_targets_m=[0.040, 0.039, 0.038, 0.037],
        requested_open_target_m=REQUESTED_OPEN_TARGET_M,
        required_settle_duration_s=0.10,
        maximum_asymmetry_m=0.0005,
        velocity_agreement_tolerance_m_s=0.002,
        physics_dt=1.0 / 600.0,
    )


def test_effective_contact_offset_bounds_are_conservative_and_per_finger():
    result = probe.derive_effective_contact_offset_bounds(
        calibration_body_width_m=0.070,
        calibration_body_contact_offset_m=0.0001,
        contact_onset_brackets=_contact_onset_brackets(),
        finger_collider_catalogs=_finger_catalogs(),
    )

    assert result["bounds_m"]["left"] == 0.0011
    assert result["bounds_m"]["right"] > 0.0013
    assert result["contact_onset_bounds_m"]["left"] > 0.0010
    assert result["method"] == (
        "max_outward_contact_onset_upper_bound_and_resolved_per_collider_contact_offset"
    )
    assert result["measurement_complete"] is True
    assert result["passed"] is True


def test_effective_contact_offset_bounds_fail_closed_on_unknown_or_impossible_onset():
    unknown_brackets = _contact_onset_brackets()
    unknown_brackets["left"] = None
    unknown = probe.derive_effective_contact_offset_bounds(
        calibration_body_width_m=0.070,
        calibration_body_contact_offset_m=0.0001,
        contact_onset_brackets=unknown_brackets,
        finger_collider_catalogs=_finger_catalogs(),
    )
    assert unknown["bounds_m"]["left"] is None
    assert unknown["bounds_m"]["right"] > 0.0013
    assert unknown["unknown_sides"] == ["left"]
    assert unknown["passed"] is False

    impossible_brackets = _contact_onset_brackets()
    impossible_brackets["left"]["previous_no_contact"]["inner_gap_m"] = 0.069
    impossible_brackets["left"]["first_contact"]["inner_gap_m"] = 0.068
    impossible = probe.derive_effective_contact_offset_bounds(
        calibration_body_width_m=0.070,
        calibration_body_contact_offset_m=0.0001,
        contact_onset_brackets=impossible_brackets,
        finger_collider_catalogs=_finger_catalogs(),
    )
    assert impossible["invalid_sides"] == ["left"]
    assert impossible["bounds_m"]["left"] is None
    assert impossible["passed"] is False

    stale_brackets = _contact_onset_brackets()
    stale_brackets["left"]["previous_no_contact"]["physics_step"] = 898
    stale = probe.derive_effective_contact_offset_bounds(
        calibration_body_width_m=0.070,
        calibration_body_contact_offset_m=0.0001,
        contact_onset_brackets=stale_brackets,
        finger_collider_catalogs=_finger_catalogs(),
    )
    assert stale["invalid_sides"] == ["left"]
    assert stale["passed"] is False

    contacted = _contact_onset_brackets()
    evidence = contacted["left"]["previous_no_contact"]["normalized_contact_evidence"]
    evidence["normalized_contacts"] = [{"physics_step": 899}]
    contacted["left"]["previous_no_contact"]["normalized_contact_evidence_sha256"] = (
        probe.canonical_json_sha256(evidence)
    )
    assert probe.derive_effective_contact_offset_bounds(
        calibration_body_width_m=0.070,
        calibration_body_contact_offset_m=0.0001,
        contact_onset_brackets=contacted,
        finger_collider_catalogs=_finger_catalogs(),
    )["passed"] is False


def test_effective_contact_offset_uses_max_onset_and_all_resolved_colliders():
    result = probe.derive_effective_contact_offset_bounds(
        calibration_body_width_m=0.070,
        calibration_body_contact_offset_m=0.0001,
        contact_onset_brackets=_contact_onset_brackets(),
        finger_collider_catalogs=_finger_catalogs(),
    )
    assert result["resolved_collider_offset_bounds_m"] == {
        "left": 0.0011,
        "right": 0.0008,
    }
    assert result["bounds_m"]["left"] == 0.0011
    assert result["bounds_m"]["right"] == result["contact_onset_bounds_m"][
        "right"
    ]

    unresolved = _finger_catalogs()
    unresolved["left"]["colliders"][1]["contact_offset"] = {
        "contact_offset_m": None,
        "authority": "unresolved",
    }
    failed = probe.derive_effective_contact_offset_bounds(
        calibration_body_width_m=0.070,
        calibration_body_contact_offset_m=0.0001,
        contact_onset_brackets=_contact_onset_brackets(),
        finger_collider_catalogs=unresolved,
    )
    assert failed["resolved_collider_offset_bounds_m"]["left"] is None
    assert failed["passed"] is False


def test_aperture_contract_covers_monotonicity_asymmetry_limits_open_and_velocity():
    result = _evaluate_aperture()

    assert result["checks"] == {
        "target_sequence_exact": True,
        "joint_aperture_monotonic": True,
        "cooked_gap_monotonic": True,
        "bilateral_motion_observed": True,
        "asymmetry_within_limit": True,
        "limit_saturation_valid": True,
        "full_open_confirmed": True,
        "measured_open_authority": True,
        "settled_at_every_point": True,
        "continuous_settle_window": True,
        "velocity_agreement": True,
    }
    assert result["maximum_left_right_asymmetry_m"] == pytest.approx(0.0001)
    assert result["maximum_velocity_disagreement_m_s"] == pytest.approx(0.0001)
    assert result["open_contract"]["requested_open_target_m"] == 0.040
    assert result["open_contract"]["canonical_open_target_m"] == pytest.approx(
        MEASURED_OPEN_TARGET_M
    )
    assert result["open_contract"]["open_position_tolerance_m"] > 0.0
    assert result["open_contract"]["authority"] == (
        "measured_dof_upper_limits_settled_position_velocity_repeatability_v2"
    )
    assert result["passed"] is True


def test_aperture_contract_rejects_each_independent_failure_mode():
    nonmonotonic_gap = _aperture_points()
    nonmonotonic_gap[2]["cooked_inner_gap_m"] = 0.076
    assert _evaluate_aperture(nonmonotonic_gap)["checks"][
        "cooked_gap_monotonic"
    ] is False

    asymmetric = _aperture_points()
    asymmetric[2]["joint_positions_m"][1] = 0.036
    assert _evaluate_aperture(asymmetric)["checks"][
        "asymmetry_within_limit"
    ] is False

    saturated = _aperture_points()
    saturated[2]["joint_positions_m"] = [0.0, 0.0]
    assert _evaluate_aperture(saturated)["checks"][
        "limit_saturation_valid"
    ] is False

    not_open = _aperture_points()
    not_open[0]["joint_positions_m"] = [0.0399, MEASURED_OPEN_TARGET_M]
    assert _evaluate_aperture(not_open)["checks"]["full_open_confirmed"] is False

    disagreement = _velocity_samples()
    disagreement[1]["finite_difference_pad_velocity_m_s"][1] = 0.01
    assert _evaluate_aperture(velocities=disagreement)["checks"][
        "velocity_agreement"
    ] is False

    transient = _aperture_points()
    transient[1]["settle_samples"][30]["api_pad_velocity_m_s"][0] = 0.01
    assert _evaluate_aperture(transient)["checks"][
        "continuous_settle_window"
    ] is False

    position_excursion = _aperture_points()
    position_excursion[2]["settle_samples"][12]["joint_positions_m"][1] = 0.0377
    assert _evaluate_aperture(position_excursion)["checks"][
        "continuous_settle_window"
    ] is False


def test_measured_dof_upper_limits_drive_open_target_and_repeatability_tolerance():
    authority = probe.derive_measured_open_contract(
        points=_aperture_points(),
        velocity_samples=_velocity_samples(),
        requested_open_target_m=REQUESTED_OPEN_TARGET_M,
        physics_dt=1.0 / 600.0,
    )
    assert authority["canonical_open_target_m"] == pytest.approx(
        MEASURED_OPEN_TARGET_M
    )
    assert authority["measured_upper_limits_m"] == pytest.approx(
        [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M]
    )
    assert authority["requested_open_target_m"] == REQUESTED_OPEN_TARGET_M
    assert authority["open_position_tolerance_m"] > 0.0
    assert authority["velocity_repeatability_bound_m"] > 0.0

    asymmetric = _aperture_points()
    for point in asymmetric:
        point["upper_limits_m"][1] = 0.039
    with pytest.raises(ValueError, match="trajectory_preflight_open_authority_invalid"):
        probe.derive_measured_open_contract(
            points=asymmetric,
            velocity_samples=_velocity_samples(),
            requested_open_target_m=REQUESTED_OPEN_TARGET_M,
            physics_dt=1.0 / 600.0,
        )

    requested_mismatch = _aperture_points()
    requested_mismatch[0]["target_m"] = 0.0399
    with pytest.raises(ValueError, match="trajectory_preflight_open_authority_invalid"):
        probe.derive_measured_open_contract(
            points=requested_mismatch,
            velocity_samples=_velocity_samples(),
            requested_open_target_m=REQUESTED_OPEN_TARGET_M,
            physics_dt=1.0 / 600.0,
            )


def test_measured_open_tolerance_includes_settled_hard_stop_deficit():
    points = _aperture_points()
    for point in points:
        point["upper_limits_m"] = [0.04, 0.04]
    points[0]["commanded_target_m"] = 0.04
    points[0]["joint_positions_m"] = [0.039995551109313965, 0.03999556228518486]
    for sample in points[0]["settle_samples"]:
        sample["joint_positions_m"] = list(points[0]["joint_positions_m"])

    authority = probe.derive_measured_open_contract(
        points=points,
        velocity_samples=_velocity_samples(),
        requested_open_target_m=0.04,
        physics_dt=1.0 / 600.0,
    )

    assert authority["canonical_open_target_m"] == pytest.approx(0.04)
    assert authority["settled_position_deficit_bound_m"] == pytest.approx(
        0.04 - 0.039995551109313965
    )
    assert authority["open_position_tolerance_m"] >= authority[
        "settled_position_deficit_bound_m"
    ]
    assert authority["authority"] == (
        "measured_dof_upper_limits_settled_position_velocity_repeatability_v2"
    )


def test_finger_drive_finishes_when_exact_target_command_is_issued(monkeypatch):
    target = 0.04

    class Controller:
        def __init__(self):
            self.actions = []

        def apply_action(self, action):
            self.actions.append(action)

    class Robot:
        def __init__(self):
            self.positions = np.zeros(9, dtype=np.float64)
            self.positions[[7, 8]] = target - 5.0e-6
            self.controller = Controller()

        def get_joint_positions(self):
            return self.positions.copy()

        def get_articulation_controller(self):
            return self.controller

        def get_gripper_pad_relative_velocities_m_s(self):
            return np.zeros(2, dtype=np.float64)

    class World:
        current_time_step_index = 0

        def step(self, *, render):
            assert render is False
            self.current_time_step_index += 1

    robot = Robot()
    world = World()
    monkeypatch.setattr(
        probe,
        "_finger_action",
        lambda _robot, _indices, targets, _units: list(targets),
    )

    result = probe._drive_fingers(
        world=world,
        robot=robot,
        finger_indices=(7, 8),
        target_m=target,
        speed_m_s=0.003,
        physics_dt=1.0 / 600.0,
        control_dt=1.0 / 30.0,
        substeps=20,
        stage_units=1.0,
        velocity_samples=[],
    )

    assert result["control_count"] == 1
    assert result["physics_step_count"] == 20
    assert robot.controller.actions == [[target, target]]


def test_orientation_edge_displacement_uses_chord_bound_per_side():
    result = probe.orientation_edge_displacement_bounds(
        edge_radii_m={"left": 0.020, "right": 0.030},
        maximum_orientation_error_degrees=2.0,
    )

    assert result["left"] == pytest.approx(2.0 * 0.020 * 0.0174524064)
    assert result["right"] == pytest.approx(2.0 * 0.030 * 0.0174524064)


def _clearance_budget(**updates):
    values = {
        "geometric_clearance_m": {"left": 0.006, "right": 0.007},
        "source_contact_offset_m": 0.002,
        "finger_contact_offset_bounds_m": {"left": 0.001, "right": 0.0012},
        "trajectory_uncertainty_m": {"left": 0.0002, "right": 0.0003},
        "numerical_margin_m": 0.001,
        "environment_pairwise_budget": {
            "hand_to_source": {"remaining_clearance_m": 0.010, "passed": True},
            "swept_bodies_to_table": {"remaining_clearance_m": 0.020, "passed": True},
            "source_to_unrelated_robot_links": {
                "remaining_clearance_m": 0.030,
                "passed": True,
            },
        },
    }
    values.update(updates)
    return probe.evaluate_swept_clearance_budget(**values)


def test_swept_clearance_budget_is_strict_positive_and_independent_per_side():
    result = _clearance_budget()

    assert result["per_side"]["left"]["remaining_clearance_m"] == pytest.approx(0.0018)
    assert result["per_side"]["right"]["remaining_clearance_m"] == pytest.approx(0.0025)
    assert result["budget_method"] == (
        "realized_geometry_plus_offset_bounds_plus_measured_repeatability_quantization_uncertainty"
    )
    assert result["passed"] is True

    zero = _clearance_budget(geometric_clearance_m={"left": 0.0042, "right": 0.007})
    assert zero["per_side"]["left"]["remaining_clearance_m"] == pytest.approx(0.0)
    assert zero["per_side"]["left"]["passed"] is False
    assert zero["per_side"]["right"]["passed"] is True
    assert zero["passed"] is False

    negative = _clearance_budget(
        geometric_clearance_m={"left": 0.006, "right": 0.0044}
    )
    assert negative["per_side"]["left"]["passed"] is True
    assert negative["per_side"]["right"]["passed"] is False
    assert negative["passed"] is False


def test_swept_clearance_budget_rejects_unknown_nonfinite_and_environment_terms():
    unknown = _clearance_budget(
        finger_contact_offset_bounds_m={"left": None, "right": 0.0012},
    )
    assert unknown["unknown_budget_terms"] == [
        "left.finger_contact_offset_bound_m",
    ]
    assert unknown["per_side"]["left"]["passed"] is False
    assert unknown["per_side"]["right"]["passed"] is True
    assert unknown["passed"] is False

    for name, value in (
        ("hand_to_source", 0.0),
        ("swept_bodies_to_table", -0.001),
        ("source_to_unrelated_robot_links", None),
    ):
        environment = {
            "hand_to_source": {"remaining_clearance_m": 0.010, "passed": True},
            "swept_bodies_to_table": {"remaining_clearance_m": 0.020, "passed": True},
            "source_to_unrelated_robot_links": {
                "remaining_clearance_m": 0.030,
                "passed": True,
            },
        }
        environment[name] = {"remaining_clearance_m": value, "passed": False}
        result = _clearance_budget(environment_pairwise_budget=environment)
        assert result["environment_checks"][name] is False
        assert result["passed"] is False

    uncertainty_unknown = _clearance_budget(
        trajectory_uncertainty_m={"left": None, "right": 0.0003}
    )
    assert "left.trajectory_uncertainty_m" in uncertainty_unknown[
        "unknown_budget_terms"
    ]
    assert uncertainty_unknown["passed"] is False


def _matrix(x=0.0, y=0.0, z=0.0):
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [x, y, z, 1.0],
    ]


def _catalog(
    body_path,
    collider_path,
    low,
    high,
    *,
    contact_offset_m=0.0001,
    contact_offset_authority="authored",
):
    return {
        "body_path": body_path,
        "cooked_aabb_precision": copy.deepcopy(COOKED_AABB_PRECISION),
        "colliders": [
            {
                "path": collider_path,
                "aabb_local_min_m": list(low),
                "aabb_local_max_m": list(high),
                "volume_m3": 0.001,
                "contact_offset": {
                    "contact_offset_m": contact_offset_m,
                    "authority": contact_offset_authority,
                },
            }
        ],
        "collider_count": 1,
    }


def _add_collider(
    catalog,
    collider_path,
    low,
    high,
    *,
    contact_offset_m,
    contact_offset_authority="authored",
):
    catalog["colliders"].append(
        {
            "path": collider_path,
            "aabb_local_min_m": list(low),
            "aabb_local_max_m": list(high),
            "volume_m3": 0.0005,
            "contact_offset": {
                "contact_offset_m": contact_offset_m,
                "authority": contact_offset_authority,
            },
        }
    )
    catalog["collider_count"] = len(catalog["colliders"])
    return catalog


def _geometry_catalogs():
    left = _add_collider(
        _catalog(
            "/World/Franka/panda_leftfinger",
            "/left/collider",
            [-0.01, -0.005, -0.02],
            [0.01, 0.005, 0.02],
        ),
        "/left/tip_collider",
        [-0.006, -0.005, -0.008],
        [0.006, 0.005, 0.008],
        contact_offset_m=0.0011,
    )
    right = _add_collider(
        _catalog(
            "/World/Franka/panda_rightfinger",
            "/right/collider",
            [-0.01, -0.005, -0.02],
            [0.01, 0.005, 0.02],
        ),
        "/right/tip_collider",
        [-0.006, -0.005, -0.008],
        [0.006, 0.005, 0.008],
        contact_offset_m=0.0008,
    )
    table = _catalog(
        "/World/table",
        "/World/table/collider",
        [-1.0, -1.0, -0.01],
        [1.0, 1.0, 0.0],
    )
    table["query_authority"] = probe.build_static_cooked_query_authority(
        body_path="/World/table",
        collision_paths=["/World/table/collider"],
    )
    catalogs = {
        "source": _catalog(
            "/World/beaker2",
            "/source/collider",
            [-0.02, -0.035, -0.04],
            [0.02, 0.035, 0.04],
            contact_offset_m=0.002,
            contact_offset_authority="effective",
        ),
        "table": table,
        "robot_bodies": {
            "/World/Franka/panda_leftfinger": left,
            "/World/Franka/panda_rightfinger": right,
            "/World/Franka/panda_hand": _catalog(
                "/World/Franka/panda_hand",
                "/hand/collider",
                [-0.02, -0.02, -0.02],
                [0.02, 0.02, 0.02],
            ),
            "/World/Franka/panda_link7": _catalog(
                "/World/Franka/panda_link7",
                "/arm/collider",
                [-0.01, -0.01, -0.01],
                [0.01, 0.01, 0.01],
            ),
        },
        "robot_rigid_body_paths": [
            "/World/Franka/panda_hand",
            "/World/Franka/panda_leftfinger",
            "/World/Franka/panda_link7",
            "/World/Franka/panda_rightfinger",
        ],
    }
    colliderless_path = "/World/Franka/panda_link8"
    catalogs["colliderless_robot_bodies"] = {
        colliderless_path: probe.build_colliderless_rigid_body_evidence(
            {
                "body_path": colliderless_path,
                "colliders": [],
                "collider_count": 0,
            },
            expected_body_path=colliderless_path,
        )
    }
    catalogs["all_robot_rigid_body_paths"] = sorted(
        [*catalogs["robot_rigid_body_paths"], colliderless_path]
    )
    inventory = {
        path: [collider["path"] for collider in catalog["colliders"]]
        for path, catalog in catalogs["robot_bodies"].items()
    }
    inventory_payload = {
        "robot_rigid_body_paths": catalogs["robot_rigid_body_paths"],
        "colliderless_robot_bodies": catalogs["colliderless_robot_bodies"],
        "all_robot_rigid_body_paths": catalogs["all_robot_rigid_body_paths"],
        "robot_collider_inventory": inventory,
    }
    catalogs["robot_collider_inventory"] = inventory
    catalogs["inventory_sha256"] = probe.canonical_json_sha256(inventory_payload)
    return catalogs


def _geometry_world_matrices():
    return {
        "/World/beaker2": [{"path": "/source/collider", "matrix": _matrix(z=1.0)}],
        "/World/table": [
            {"path": "/World/table/collider", "matrix": _matrix(z=0.7)}
        ],
        "/World/Franka/panda_leftfinger": [
            {"path": "/left/collider", "matrix": _matrix(y=-0.05, z=1.0)},
            {
                "path": "/left/tip_collider",
                "matrix": _matrix(y=-0.05, z=1.0),
            },
        ],
        "/World/Franka/panda_rightfinger": [
            {"path": "/right/collider", "matrix": _matrix(y=0.05, z=1.0)},
            {
                "path": "/right/tip_collider",
                "matrix": _matrix(y=0.05, z=1.0),
            },
        ],
        "/World/Franka/panda_hand": [
            {"path": "/hand/collider", "matrix": _matrix(z=1.1)}
        ],
        "/World/Franka/panda_link7": [
            {"path": "/arm/collider", "matrix": _matrix(x=0.2, z=1.0)}
        ],
    }


def _finger_catalogs():
    robot = _geometry_catalogs()["robot_bodies"]
    return {
        side: copy.deepcopy(robot[probe.EXPECTED_FINGER_BODY_PATHS[side]])
        for side in probe.SIDES
    }


def _finger_world_matrices():
    matrices = _geometry_world_matrices()
    return {
        side: copy.deepcopy(matrices[probe.EXPECTED_FINGER_BODY_PATHS[side]])
        for side in probe.SIDES
    }


def _gap_error_bound():
    return probe.derive_cooked_gap_error_bound(
        finger_collider_catalogs=_finger_catalogs(),
        finger_collider_world_matrices=_finger_world_matrices(),
    )


def test_tool_frame_axis_drives_projected_cooked_geometry_and_body_hash():
    tool_world = [
        [0.0, 1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.3, 0.1, 1.0, 1.0],
    ]
    axis = probe.derive_opening_axis_world(tool_world)
    assert axis == pytest.approx([-1.0, 0.0, 0.0])

    catalog = _catalog("/finger", "/finger/collider", [-0.01, -0.02, -0.03], [0.01, 0.02, 0.03])
    interval = probe.project_cooked_catalog_interval(
        catalog=catalog,
        collider_world_matrices=[{"path": "/finger/collider", "matrix": tool_world}],
        axis_world=axis,
    )
    assert interval == pytest.approx([-0.32, -0.28])

    translated_world = probe.compose_calibration_body_world_matrix(
        reset_tool_world_matrix=tool_world,
        translation_tool_m=[0.009, 0.0, 0.006],
    )
    expected_translation = np.eye(4, dtype=np.float64)
    expected_translation[3, :3] = [0.009, 0.0, 0.006]
    assert np.allclose(
        translated_world,
        expected_translation @ np.asarray(tool_world),
        rtol=0.0,
        atol=0.0,
    )

    spec = probe.calibration_body_spec(
        reset_tool_world_matrix=tool_world,
        translation_tool_m=[0.009, 0.0, 0.006],
        opening_axis_world=axis,
        size_m=[0.002, 0.070, 0.002],
        contact_offset_m=0.0001,
    )
    changed = copy.deepcopy(spec)
    changed["opening_axis_world"][0] = 1.0
    assert spec["reset_tool_world_matrix"] == tool_world
    assert spec["translation_tool_m"] == [0.009, 0.0, 0.006]
    assert np.allclose(spec["world_matrix"], translated_world, rtol=0.0, atol=0.0)
    assert spec["non_width_dimensions_m"] == [0.002, 0.002]
    assert spec["opening_axis_world"] == pytest.approx(axis)
    assert probe.canonical_json_sha256(spec) != probe.canonical_json_sha256(changed)


def _support_projection_intervals():
    return {
        "left": {
            "/left/pad": {
                "tool_x": [0.0, 0.020],
                "tool_y": [-0.050, -0.038],
                "tool_z": [-0.005, 0.015],
            }
        },
        "right": {
            "/right/pad": {
                "tool_x": [0.0, 0.020],
                "tool_y": [0.038, 0.050],
                "tool_z": [-0.005, 0.015],
            }
        },
    }


def _translated_calibration_spec():
    reset = _matrix()
    return probe.calibration_body_spec(
        reset_tool_world_matrix=reset,
        translation_tool_m=[0.009, 0.0, 0.006],
        opening_axis_world=probe.derive_opening_axis_world(reset),
        size_m=[0.002, 0.070, 0.002],
        contact_offset_m=0.0001,
    )


def test_calibration_support_requires_one_collider_to_cover_the_complete_face():
    placement = probe.evaluate_calibration_support_placement(
        calibration_spec=_translated_calibration_spec(),
        finger_collider_projection_intervals_m=_support_projection_intervals(),
        cooked_projection_error_bound_m=1.0e-6,
    )
    assert placement["selected_collider_paths"] == {
        "left": "/left/pad",
        "right": "/right/pad",
    }
    assert placement["opening_order"] == ["left", "right"]
    assert placement["passed"] is True

    mixed = _support_projection_intervals()
    mixed["left"] = {
        "/left/x_only": {
            "tool_x": [0.0, 0.020],
            "tool_y": [-0.050, -0.038],
            "tool_z": [0.007, 0.008],
        },
        "/left/z_only": {
            "tool_x": [0.009, 0.010],
            "tool_y": [-0.050, -0.038],
            "tool_z": [-0.005, 0.015],
        },
    }
    assert probe.evaluate_calibration_support_placement(
        calibration_spec=_translated_calibration_spec(),
        finger_collider_projection_intervals_m=mixed,
        cooked_projection_error_bound_m=1.0e-6,
    )["passed"] is False

    boundary = _support_projection_intervals()
    boundary["right"]["/right/pad"]["tool_x"][1] = 0.010001
    assert probe.evaluate_calibration_support_placement(
        calibration_spec=_translated_calibration_spec(),
        finger_collider_projection_intervals_m=boundary,
        cooked_projection_error_bound_m=1.0e-6,
    )["passed"] is False


def _support_ray_hits():
    sample_ids = [
        "center",
        "x_low_z_low",
        "x_low_z_high",
        "x_high_z_low",
        "x_high_z_high",
    ]
    return {
        side: [
            {
                "sample_id": sample_id,
                "collision_path": f"/{side}/pad",
                "position_m": [
                    0.009,
                    -0.038 if side == "left" else 0.038,
                    0.006,
                ],
                "normal_world": [
                    0.0,
                    1.0 if side == "left" else -1.0,
                    0.0,
                ],
                "distance_m": 0.003,
            }
            for sample_id in sample_ids
        ]
        for side in probe.SIDES
    }


def test_calibration_support_rays_bind_all_face_samples_to_selected_colliders():
    placement = probe.evaluate_calibration_support_placement(
        calibration_spec=_translated_calibration_spec(),
        finger_collider_projection_intervals_m=_support_projection_intervals(),
        cooked_projection_error_bound_m=1.0e-6,
    )
    result = probe.evaluate_calibration_support_rays(
        placement_evidence=placement,
        ray_hits_by_side=_support_ray_hits(),
        opening_axis_world=[0.0, 1.0, 0.0],
        cooked_projection_error_bound_m=1.0e-6,
    )
    assert result["passed"] is True

    wrong = _support_ray_hits()
    wrong["left"][2]["collision_path"] = "/left/edge"
    assert probe.evaluate_calibration_support_rays(
        placement_evidence=placement,
        ray_hits_by_side=wrong,
        opening_axis_world=[0.0, 1.0, 0.0],
        cooked_projection_error_bound_m=1.0e-6,
    )["passed"] is False


def test_calibration_axis_and_literal_commanded_shadow_axis_are_independent():
    angle = math.radians(49.0)
    remote_tool_world = [
        [math.cos(angle), -math.sin(angle), 0.0, 0.0],
        [math.sin(angle), math.cos(angle), 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 1.5, 1.0],
    ]
    calibration_axis = probe.derive_opening_axis_world(remote_tool_world)
    shadow_axis = probe.derive_opening_axis_from_orientation_wxyz(
        [0.0, 0.0, 1.0, 0.0]
    )

    assert calibration_axis == pytest.approx(
        [math.sin(angle), math.cos(angle), 0.0]
    )
    assert shadow_axis == pytest.approx([0.0, 1.0, 0.0])
    mismatch = math.degrees(
        math.acos(float(sum(a * b for a, b in zip(calibration_axis, shadow_axis))))
    )
    assert mismatch == pytest.approx(49.0)
    assert calibration_axis != pytest.approx(shadow_axis)


def test_cooked_catalog_validation_rejects_query_errors_and_empty_catalogs():
    valid = _catalog("/body", "/body/collider", [-1, -1, -1], [1, 1, 1])
    assert probe.validate_cooked_catalog(valid)["collider_count"] == 1

    for invalid in (
        {"body_path": "/body", "colliders": [], "collider_count": 0},
        {**valid, "rigid_body_error": "INVALID"},
        {**valid, "collider_errors": ["INVALID"]},
        {**valid, "collider_count": 2},
    ):
        with pytest.raises(ValueError, match="trajectory_preflight_cooked_catalog_invalid"):
            probe.validate_cooked_catalog(invalid)

    unresolved = _catalog(
        "/body",
        "/body/collider",
        [-1, -1, -1],
        [1, 1, 1],
        contact_offset_m=None,
        contact_offset_authority="unresolved",
    )
    assert probe.validate_cooked_catalog(unresolved)["colliders"][0][
        "contact_offset"
    ]["authority"] == "unresolved"


def test_isaac41_static_table_query_requires_temporary_disabled_rigid_body_adapter():
    direct_query = {
        "body_path": "/World/table",
        "cooked_aabb_precision": copy.deepcopy(COOKED_AABB_PRECISION),
        "colliders": [],
        "collider_count": 0,
        "rigid_body_error": "PhysxPropertyQueryResult.ERROR_PARSING",
        "collider_errors": ["PhysxPropertyQueryResult.ERROR_PARSING"],
    }

    assert probe.cooked_catalog_validation_failures(direct_query) == [
        "colliders_empty",
        "rigid_body_error",
        "collider_errors",
    ]
    with pytest.raises(
        ValueError,
        match=(
            "trajectory_preflight_cooked_catalog_invalid:"
            "colliders_empty,rigid_body_error,collider_errors"
        ),
    ):
        probe.validate_cooked_catalog(direct_query)

    adapted = _catalog(
        "/World/table",
        "/World/table/surface/mesh",
        [-129.63404846191406, -174.998779296875, -193.1901397705078],
        [130.9152069091797, 177.62924194335938, -172.69337463378906],
        contact_offset_m=None,
        contact_offset_authority="unresolved",
    )
    adapted["query_authority"] = probe.build_static_cooked_query_authority(
        body_path="/World/table",
        collision_paths=["/World/table/surface/mesh"],
    )

    assert probe.validate_static_cooked_catalog(
        adapted, expected_body_path="/World/table"
    ) == adapted

    for field, value in (
        ("rigid_body_enabled_during_query", True),
        ("temporary_layer_discarded", False),
        ("stage_composition_restored", False),
        ("collision_paths", ["/World/table/wrong"]),
    ):
        tampered = copy.deepcopy(adapted)
        tampered["query_authority"][field] = value
        with pytest.raises(
            ValueError, match="trajectory_preflight_static_cooked_catalog_invalid"
        ):
            probe.validate_static_cooked_catalog(
                tampered, expected_body_path="/World/table"
            )


def test_clean_colliderless_franka_link8_is_explicit_inventory_evidence():
    raw = {
        "body_path": "/World/Franka/panda_link8",
        "colliders": [],
        "collider_count": 0,
        "mass_kg": 0.0,
        "center_of_mass_local_m": [0.0, 0.0, 0.0],
        "diagonal_inertia_kg_m2": [0.0, 0.0, 0.0],
    }
    expected = {
        "authority": "physx_property_query_clean_zero_collider_v1",
        "body_path": "/World/Franka/panda_link8",
        "collider_count": 0,
        "rigid_body_error": None,
        "collider_errors": [],
    }

    assert probe.build_colliderless_rigid_body_evidence(
        raw, expected_body_path="/World/Franka/panda_link8"
    ) == expected

    for update in (
        {"body_path": "/World/Franka/panda_link7"},
        {"collider_count": 1},
        {"rigid_body_error": "PhysxPropertyQueryResult.ERROR_PARSING"},
        {"collider_errors": ["PhysxPropertyQueryResult.ERROR_PARSING"]},
        {
            "colliders": [
                {
                    "path": "/World/Franka/panda_link8/collider",
                }
            ]
        },
    ):
        invalid = {**raw, **update}
        with pytest.raises(
            ValueError, match="trajectory_preflight_colliderless_body_invalid"
        ):
            probe.build_colliderless_rigid_body_evidence(
                invalid, expected_body_path="/World/Franka/panda_link8"
            )

    with pytest.raises(
        ValueError,
        match=(
            "trajectory_preflight_cooked_catalog_invalid:colliders_empty:"
            "body_path=/World/Franka/panda_link8"
        ),
    ):
        probe._catalog_with_contact_offset_authority(
            None,
            raw,
            read_offset=lambda *_args: pytest.fail(
                "an empty catalog must fail before offset reads"
            ),
        )


def _collision_role_records():
    return [
        {
            "path": "/World/Franka/panda_leftfinger/pad",
            "collision_enabled": True,
            "rigid_body_owners_nearest_first": [
                {
                    "path": "/World/Franka/panda_leftfinger",
                    "rigid_body_enabled": True,
                    "kinematic_enabled": False,
                }
            ],
        },
        {
            "path": "/World/Franka/panda_rightfinger/pad",
            "collision_enabled": True,
            "rigid_body_owners_nearest_first": [
                {
                    "path": "/World/Franka/panda_rightfinger",
                    "rigid_body_enabled": True,
                    "kinematic_enabled": False,
                }
            ],
        },
        {
            "path": "/World/Franka/panda_hand/collider",
            "collision_enabled": True,
            "rigid_body_owners_nearest_first": [
                {
                    "path": "/World/Franka/panda_hand",
                    "rigid_body_enabled": True,
                    "kinematic_enabled": False,
                }
            ],
        },
        {
            "path": "/World/beaker1/wrapper",
            "collision_enabled": True,
            "rigid_body_owners_nearest_first": [],
        },
        {
            "path": "/World/beaker1/mesh",
            "collision_enabled": False,
            "rigid_body_owners_nearest_first": [
                {
                    "path": "/World/beaker1/mesh",
                    "rigid_body_enabled": True,
                    "kinematic_enabled": True,
                }
            ],
        },
        {
            "path": "/World/disabled_parent/collider",
            "collision_enabled": True,
            "rigid_body_owners_nearest_first": [
                {
                    "path": "/World/disabled_parent",
                    "rigid_body_enabled": False,
                    "kinematic_enabled": False,
                },
                {
                    "path": "/World",
                    "rigid_body_enabled": True,
                    "kinematic_enabled": False,
                },
            ],
        },
    ]


def test_collision_inventory_uses_nearest_owner_and_partitions_every_collider():
    result = probe.evaluate_calibration_collision_inventory(
        collider_records=_collision_role_records(),
        intended_finger_collider_paths={
            "left": ["/World/Franka/panda_leftfinger/pad"],
            "right": ["/World/Franka/panda_rightfinger/pad"],
        },
        colliderless_body_paths=["/World/Franka/panda_link8"],
    )
    assert result["roles_by_collider"] == {
        "/World/Franka/panda_leftfinger/pad": "dynamic",
        "/World/Franka/panda_rightfinger/pad": "dynamic",
        "/World/Franka/panda_hand/collider": "dynamic",
        "/World/beaker1/wrapper": "static",
        "/World/beaker1/mesh": "disabled_collider",
        "/World/disabled_parent/collider": "disabled_rigid_body",
    }
    assert result["intended_finger_colliders"] == sorted(
        [
            "/World/Franka/panda_leftfinger/pad",
            "/World/Franka/panda_rightfinger/pad",
        ]
    )
    assert result["compatible_obstacle_colliders"] == [
        "/World/Franka/panda_hand/collider"
    ]
    assert result["static_obstacle_colliders"] == ["/World/beaker1/wrapper"]
    assert result["passed"] is True

    duplicate = [*_collision_role_records(), copy.deepcopy(_collision_role_records()[0])]
    assert probe.evaluate_calibration_collision_inventory(
        collider_records=duplicate,
        intended_finger_collider_paths={
            "left": ["/World/Franka/panda_leftfinger/pad"],
            "right": ["/World/Franka/panda_rightfinger/pad"],
        },
        colliderless_body_paths=["/World/Franka/panda_link8"],
    )["passed"] is False

    leaked_link8 = _collision_role_records()
    leaked_link8.append(
        {
            "path": "/World/Franka/panda_link8/collider",
            "collision_enabled": True,
            "rigid_body_owners_nearest_first": [
                {
                    "path": "/World/Franka/panda_link8",
                    "rigid_body_enabled": True,
                    "kinematic_enabled": False,
                }
            ],
        }
    )
    assert probe.evaluate_calibration_collision_inventory(
        collider_records=leaked_link8,
        intended_finger_collider_paths={
            "left": ["/World/Franka/panda_leftfinger/pad"],
            "right": ["/World/Franka/panda_rightfinger/pad"],
        },
        colliderless_body_paths=["/World/Franka/panda_link8"],
    )["passed"] is False


def test_cooked_gap_error_bound_uses_float32_magnitudes_floor_and_authority():
    result = _gap_error_bound()
    assert result["authority"] == (
        "physx_property_query_float32_aabb_outward_8ulp_plus_float64_transform_v1"
    )
    assert result["property_query_value_type"] == "float32"
    assert result["bound_m"] >= probe.COOKED_GAP_ERROR_FLOOR_M
    assert result["passed"] is True

    large = _finger_catalogs()
    for catalog in large.values():
        for collider in catalog["colliders"]:
            collider["aabb_local_min_m"] = [-100.0, -100.0, -100.0]
            collider["aabb_local_max_m"] = [100.0, 100.0, 100.0]
    large_result = probe.derive_cooked_gap_error_bound(
        finger_collider_catalogs=large,
        finger_collider_world_matrices=_finger_world_matrices(),
    )
    assert large_result["bound_m"] > result["bound_m"]

    unknown = _finger_catalogs()
    unknown["left"]["cooked_aabb_precision"]["value_type"] = "unknown"
    failed = probe.derive_cooked_gap_error_bound(
        finger_collider_catalogs=unknown,
        finger_collider_world_matrices=_finger_world_matrices(),
    )
    assert failed["bound_m"] is None
    assert failed["passed"] is False


def _pose(position):
    return {
        "position_m": list(position),
        "orientation_wxyz": [0.0, 0.0, 1.0, 0.0],
    }


def _valid_trace(*, complete_insert: bool = True) -> list[dict]:
    actions = [
        ("GRIPPER_OPEN", "PREGRASP", [0.0, 0.0, 1.1200]),
        ("GRIPPER_OPEN", "PREGRASP", [0.0, 0.0, 1.1200]),
        ("ARM_PREGRASP", "PREGRASP", [0.0, 0.0, 1.1200]),
        ("ARM_ALIGN", "ALIGN", [0.0, 0.0, 1.0600]),
    ]
    insert_count = 300 if complete_insert else 3
    actions.extend(
        (
            "ARM_INSERT",
            "INSERT",
            [0.0, 0.0, 1.0600 - 0.0002 * (index + 1)],
        )
        for index in range(insert_count)
    )
    if complete_insert:
        actions.extend(
            ("ARM_SETTLE", "SETTLE", [0.0, 0.0, 1.0]) for _ in range(3)
        )
    trace = []
    for control_index, (kind, phase, command_position) in enumerate(actions):
        if kind == "GRIPPER_OPEN":
            payload = {
                "joint_positions": [None] * 7
                + [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M],
                "joint_velocities": None,
                "joint_efforts": None,
            }
        else:
            payload = {
                "joint_positions": [0.01 * (control_index + 1)] * 7,
                "joint_velocities": None,
                "joint_efforts": None,
                "joint_indices": list(range(7)),
            }
        action_hash = probe.canonical_action_hash(payload)
        commanded_tool_pose = _pose(command_position)
        commanded_control_pose = probe.map_tool_target_to_control_pose(
            tool_pose=commanded_tool_pose,
            control_to_tool_matrix_m=[
                [-1.0, 0.0, 0.0, 0.0],
                [0.0, -1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, -0.0034, 1.0],
            ],
        )
        for substep_index in range(20):
            trace_index = len(trace)
            fingers = (
                MEASURED_OPEN_TARGET_M - MEASURED_OPEN_TOLERANCE_M
                if trace_index == 0
                else MEASURED_OPEN_TARGET_M
            )
            physics_step = 1000 + trace_index
            trace.append(
                {
                    "trace_index": trace_index,
                    "timestamp_s": (physics_step - 1000) * (1.0 / 600.0),
                    "world_time_s": 10.0 + trace_index / 600.0,
                    "physics_step": physics_step,
                    "control_index": control_index,
                    "controller_invocation_index": control_index + 1,
                    "substep_index": substep_index,
                    "phase": phase,
                    "action_kind": kind,
                    "action_payload": payload,
                    "action_sha256": action_hash,
                    "commanded_tool_pose": commanded_tool_pose,
                    "measured_tool_pose": _pose(command_position),
                    "commanded_control_pose": commanded_control_pose,
                    "measured_control_pose": commanded_control_pose,
                    "rmpflow_control_pose": commanded_control_pose,
                    "joint_positions_m": [0.0] * 7 + [fingers, fingers],
                    "joint_velocities_m_s": [0.0] * 9,
                    "stage_units_in_meters": 1.0,
                    "joint_position_units": ["rad"] * 7 + ["m", "m"],
                    "joint_velocity_units": ["rad_s"] * 7 + ["m_s", "m_s"],
                    "collider_world_matrices": {
                        "left_finger": [
                            {
                                "path": "/left/collider",
                                "matrix": _matrix(y=-0.05, z=1.0),
                            },
                            {
                                "path": "/left/tip_collider",
                                "matrix": _matrix(y=-0.05, z=1.0),
                            },
                        ],
                        "right_finger": [
                            {
                                "path": "/right/collider",
                                "matrix": _matrix(y=0.05, z=1.0),
                            },
                            {
                                "path": "/right/tip_collider",
                                "matrix": _matrix(y=0.05, z=1.0),
                            },
                        ],
                        "hand": [
                            {"path": "/hand/collider", "matrix": _matrix(z=1.1)}
                        ],
                    },
                    "geometry_world_matrices": _geometry_world_matrices(),
                    "source_center_world_m": [0.0, 0.0, 1.0],
                    "source_world_matrix": _matrix(z=1.0),
                    "contacts": [],
                    "geometric_clearance_m": {"left": 0.010, "right": 0.010},
                    "environment_clearance_m": {
                        "hand_to_source": 0.040,
                        "swept_bodies_to_table": 0.280,
                        "source_to_unrelated_robot_links": 0.170,
                    },
                }
            )
    return trace


def test_trace_contract_requires_contiguous_600hz_exact_substeps_and_action_sequence():
    trace = _valid_trace()
    result = probe.validate_shadow_trace(
        trace,
        physics_dt=1.0 / 600.0,
        substeps_per_action=20,
        insertion_step_m=0.0002,
        insert_distance_m=0.060,
        settle_duration_s=0.10,
        frozen_source_position_m=[0.0, 0.0, 1.0],
        expected_tool_orientation_wxyz=[0.0, 0.0, 1.0, 0.0],
        requested_open_target_m=REQUESTED_OPEN_TARGET_M,
        canonical_open_target_m=MEASURED_OPEN_TARGET_M,
        open_position_tolerance_m=MEASURED_OPEN_TOLERANCE_M,
        stage_units_in_meters=1.0,
    )

    assert result["checks"] == {
        "nonempty": True,
        "contiguous_trace_indices": True,
        "integer_step_timestamps": True,
        "contiguous_physics_steps": True,
        "exact_substeps_per_action": True,
        "action_hashes_valid": True,
        "exact_action_channel_shape": True,
        "action_kind_sequence_valid": True,
        "global_control_order_valid": True,
        "controller_indices_cross_bound": True,
        "world_z_insert_only": True,
        "exact_insert_progression": True,
        "exact_settle_window": True,
        "frozen_waypoint_commands": True,
        "stage_and_dof_units": True,
        "per_step_pose_and_collider_evidence": True,
        "full_open_after_command_before_arm": True,
    }
    assert result["action_kind_counts"] == {
        "GRIPPER_OPEN": 2,
        "ARM_PREGRASP": 1,
        "ARM_ALIGN": 1,
        "ARM_INSERT": 300,
        "ARM_SETTLE": 3,
    }
    assert result["passed"] is True


def test_trace_contract_rejects_gaps_time_step_hash_substep_and_insert_drift():
    mutations = []

    missing = _valid_trace()
    del missing[20]
    mutations.append(missing)

    timestamp = _valid_trace()
    timestamp[7]["timestamp_s"] += 0.001
    mutations.append(timestamp)

    physics_step = _valid_trace()
    physics_step[8]["physics_step"] += 1
    mutations.append(physics_step)

    action_hash = _valid_trace()
    action_hash[20]["action_sha256"] = "0" * 64
    mutations.append(action_hash)

    wrong_kind = _valid_trace()
    for record in wrong_kind:
        if record["control_index"] == 2:
            record["action_kind"] = "ARM_INSERT"
            record["phase"] = "INSERT"
    mutations.append(wrong_kind)

    insert_drift = _valid_trace()
    first_insert = next(
        record for record in insert_drift if record["action_kind"] == "ARM_INSERT"
    )
    first_insert["commanded_tool_pose"]["position_m"][0] = 0.0001
    mutations.append(insert_drift)

    for trace in mutations:
        assert probe.validate_shadow_trace(
            trace,
            physics_dt=1.0 / 600.0,
            substeps_per_action=20,
            insertion_step_m=0.0002,
            insert_distance_m=0.060,
            settle_duration_s=0.10,
            frozen_source_position_m=[0.0, 0.0, 1.0],
            expected_tool_orientation_wxyz=[0.0, 0.0, 1.0, 0.0],
            requested_open_target_m=REQUESTED_OPEN_TARGET_M,
            canonical_open_target_m=MEASURED_OPEN_TARGET_M,
            open_position_tolerance_m=MEASURED_OPEN_TOLERANCE_M,
            stage_units_in_meters=1.0,
        )["passed"] is False


def _trace_result(trace):
    return probe.validate_shadow_trace(
        trace,
        physics_dt=1.0 / 600.0,
        substeps_per_action=20,
        insertion_step_m=0.0002,
        insert_distance_m=0.060,
        settle_duration_s=0.10,
        frozen_source_position_m=[0.0, 0.0, 1.0],
        expected_tool_orientation_wxyz=[0.0, 0.0, 1.0, 0.0],
        requested_open_target_m=REQUESTED_OPEN_TARGET_M,
        canonical_open_target_m=MEASURED_OPEN_TARGET_M,
        open_position_tolerance_m=MEASURED_OPEN_TOLERANCE_M,
        stage_units_in_meters=1.0,
    )


def test_trace_rejects_action_channels_global_reordering_and_counter_mismatch():
    velocity = _valid_trace()
    arm_group = next(
        record["control_index"]
        for record in velocity
        if record["action_kind"] == "ARM_PREGRASP"
    )
    for record in velocity:
        if record["control_index"] == arm_group:
            record["action_payload"]["joint_velocities"] = [0.0] * 9
            record["action_sha256"] = probe.canonical_action_hash(record["action_payload"])
    assert _trace_result(velocity)["checks"]["action_hashes_valid"] is False

    reordered = _valid_trace()
    for record in reordered[:40]:
        replacement = 1 - record["control_index"]
        record["control_index"] = replacement
        record["controller_invocation_index"] = replacement + 1
    assert _trace_result(reordered)["checks"]["global_control_order_valid"] is False

    counter = _valid_trace()
    counter[100]["controller_invocation_index"] += 1
    assert _trace_result(counter)["checks"]["controller_indices_cross_bound"] is False


def test_trace_requires_exact_300_insert_steps_and_three_exact_settle_targets():
    incomplete = _valid_trace(complete_insert=False)
    assert _trace_result(incomplete)["checks"]["exact_insert_progression"] is False

    wrong_settle = _valid_trace()
    settle_control = next(
        record["control_index"]
        for record in wrong_settle
        if record["action_kind"] == "ARM_SETTLE"
    )
    for record in wrong_settle:
        if record["control_index"] == settle_control:
            record["commanded_tool_pose"] = _pose([0.0, 0.0, 1.0001])
            record["commanded_control_pose"] = probe.map_tool_target_to_control_pose(
                tool_pose=record["commanded_tool_pose"],
                control_to_tool_matrix_m=[
                    [-1.0, 0.0, 0.0, 0.0],
                    [0.0, -1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, -0.0034, 1.0],
                ],
            )
    assert _trace_result(wrong_settle)["checks"]["exact_settle_window"] is False


def test_trace_binds_integer_time_units_frozen_waypoints_and_exact_arm_channels():
    world_time_noise = _valid_trace()
    world_time_noise[7]["world_time_s"] += 42.0
    assert _trace_result(world_time_noise)["checks"]["integer_step_timestamps"] is True

    units = _valid_trace()
    units[100]["joint_velocity_units"][0] = "m_s"
    assert _trace_result(units)["checks"]["stage_and_dof_units"] is False

    pregrasp = _valid_trace()
    pregrasp_control = next(
        record["control_index"]
        for record in pregrasp
        if record["action_kind"] == "ARM_PREGRASP"
    )
    for record in pregrasp:
        if record["control_index"] == pregrasp_control:
            record["commanded_tool_pose"] = _pose([0.001, 0.0, 1.120])
            record["commanded_control_pose"] = probe.map_tool_target_to_control_pose(
                tool_pose=record["commanded_tool_pose"],
                control_to_tool_matrix_m=[
                    [-1.0, 0.0, 0.0, 0.0],
                    [0.0, -1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, -0.0034, 1.0],
                ],
            )
    assert _trace_result(pregrasp)["checks"]["frozen_waypoint_commands"] is False

    permissive_arm = _valid_trace()
    arm_control = next(
        record["control_index"]
        for record in permissive_arm
        if record["action_kind"] == "ARM_ALIGN"
    )
    arm_records = [
        record
        for record in permissive_arm
        if record["control_index"] == arm_control
    ]
    payload = arm_records[0]["action_payload"]
    payload["joint_positions"] = payload["joint_positions"] + [None, None]
    payload.pop("joint_indices")
    for record in arm_records:
        record["action_sha256"] = probe.canonical_action_hash(payload)
    assert _trace_result(permissive_arm)["checks"]["exact_action_channel_shape"] is False


def test_trajectory_uncertainty_includes_absolute_error_without_double_counting():
    baseline = probe.derive_trajectory_uncertainty(
        trace=_valid_trace(),
        edge_radii_m={"left": 0.020, "right": 0.030},
    )
    assert baseline["formula"] == (
        "collider_projection_quantization + pose_quantization + max_absolute_or_repeatable_cross_track_error + max_absolute_or_repeatable_orientation_error_edge_chord"
    )
    assert baseline["passed"] is True
    assert all(value > 0.0 for value in baseline["per_side_m"].values())

    constant_lag = _valid_trace()
    for record in constant_lag:
        if record["action_kind"] in {"ARM_INSERT", "ARM_SETTLE"}:
            record["measured_tool_pose"]["position_m"][0] += 0.0004
    lag_result = probe.derive_trajectory_uncertainty(
        trace=constant_lag,
        edge_radii_m={"left": 0.020, "right": 0.030},
    )
    assert lag_result["cross_track_repeatability_m"] == pytest.approx(0.0)
    assert lag_result["maximum_absolute_cross_track_error_m"] >= 0.0004
    assert lag_result["cross_track_envelope_m"] >= 0.0004
    assert lag_result["per_side_m"]["left"] > baseline["per_side_m"]["left"]

    jitter = copy.deepcopy(constant_lag)
    tracked = [
        record
        for record in jitter
        if record["action_kind"] in {"ARM_INSERT", "ARM_SETTLE"}
    ]
    tracked[len(tracked) // 2]["measured_tool_pose"]["position_m"][0] += 0.0001
    jitter_result = probe.derive_trajectory_uncertainty(
        trace=jitter,
        edge_radii_m={"left": 0.020, "right": 0.030},
    )
    assert jitter_result["cross_track_repeatability_m"] >= 0.0001
    assert jitter_result["per_side_m"]["left"] > lag_result["per_side_m"]["left"]

    orientation = _valid_trace()
    angle = math.radians(1.0) / 2.0
    for record in orientation:
        if record["action_kind"] in {"ARM_INSERT", "ARM_SETTLE"}:
            record["measured_tool_pose"]["orientation_wxyz"] = [
                math.sin(angle),
                0.0,
                math.cos(angle),
                0.0,
            ]
    orientation_result = probe.derive_trajectory_uncertainty(
        trace=orientation,
        edge_radii_m={"left": 0.020, "right": 0.030},
    )
    assert orientation_result["maximum_absolute_orientation_error_degrees"] == (
        pytest.approx(1.0)
    )
    assert orientation_result["orientation_edge_displacement_m"]["left"] > 0.0


def test_parent_recomputes_geometry_from_local_bounds_and_world_transforms():
    trace = _valid_trace()[:1]
    result = probe.recompute_trace_geometry(
        trace=trace,
        geometry_catalogs=_geometry_catalogs(),
        opening_axis_world=[0.0, 1.0, 0.0],
        trajectory_uncertainty_m={"left": 0.0002, "right": 0.0003},
        numerical_margin_m=0.001,
    )

    assert result["parent_geometry_recomputed"] is True
    assert result["reported_values_match"] is True
    assert result["geometric_clearance_minima_m"] == pytest.approx(
        {"left": 0.010, "right": 0.010}
    )
    assert result["environment_clearance_minima_m"] == pytest.approx(
        {
            "hand_to_source": 0.040,
            "swept_bodies_to_table": 0.280,
            "source_to_unrelated_robot_links": 0.170,
        }
    )
    assert result["environment_pairwise_budget"]["hand_to_source"][
        "remaining_clearance_m"
    ] == pytest.approx(0.0366)
    assert result["environment_pairwise_budget"]["swept_bodies_to_table"][
        "remaining_clearance_m"
    ] == pytest.approx(0.2775)
    assert result["environment_pairwise_budget"][
        "source_to_unrelated_robot_links"
    ]["remaining_clearance_m"] == pytest.approx(0.1666)
    assert result["unknown_environment_offset_pairs"] == []
    assert result["passed"] is True

    missing = copy.deepcopy(trace)
    del missing[0]["geometry_world_matrices"]["/World/Franka/panda_link7"]
    assert probe.recompute_trace_geometry(
        trace=missing,
        geometry_catalogs=_geometry_catalogs(),
        opening_axis_world=[0.0, 1.0, 0.0],
        trajectory_uncertainty_m={"left": 0.0002, "right": 0.0003},
        numerical_margin_m=0.001,
    )["parent_geometry_recomputed"] is False

    unresolved = _geometry_catalogs()
    unresolved["robot_bodies"]["/World/Franka/panda_link7"]["colliders"][0][
        "contact_offset"
    ] = {"contact_offset_m": None, "authority": "unresolved"}
    unresolved_result = probe.recompute_trace_geometry(
        trace=trace,
        geometry_catalogs=unresolved,
        opening_axis_world=[0.0, 1.0, 0.0],
        trajectory_uncertainty_m={"left": 0.0002, "right": 0.0003},
        numerical_margin_m=0.001,
    )
    assert unresolved_result["parent_geometry_recomputed"] is True
    assert unresolved_result["unknown_environment_offset_pairs"]
    assert unresolved_result["passed"] is False


def _zero_writer_audit() -> dict:
    return {
        "coverage_complete": True,
        "calls": [],
        "source_pose_write_count_after_play": 0,
        "kinematic_target_update_count": 0,
    }


def test_prohibited_activity_counts_are_recomputed_and_all_zero():
    result = probe.evaluate_prohibited_activity(
        trace=_valid_trace(),
        source_writer_audit=_zero_writer_audit(),
        attachment_events=[],
    )

    assert result["counts"] == {
        "near_source_contact": 0,
        "unexpected_robot_contact": 0,
        "close": 0,
        "lift": 0,
        "hold": 0,
        "pour": 0,
        "attachment": 0,
        "source_write": 0,
        "kinematic_target": 0,
    }
    assert result["passed"] is True

    for kind in ("NEAR_SOURCE_CLOSE", "LIFT", "HOLD", "POUR"):
        trace = _valid_trace()
        trace[-1]["action_kind"] = kind
        result = probe.evaluate_prohibited_activity(
            trace=trace,
            source_writer_audit=_zero_writer_audit(),
            attachment_events=[],
        )
        assert result["passed"] is False

    writer = _zero_writer_audit()
    writer["calls"] = [{"surface": "source_body.set_world_pose"}]
    writer["source_pose_write_count_after_play"] = 1
    assert probe.evaluate_prohibited_activity(
        trace=_valid_trace(), source_writer_audit=writer, attachment_events=[]
    )["passed"] is False

    contact_trace = _valid_trace()
    contact_trace[-1]["contacts"] = [
        {
            "physics_step": contact_trace[-1]["physics_step"],
            "body0_path": "/World/Franka/panda_hand",
            "body1_path": "/World/table",
            "collider0_path": "/hand/collider",
            "collider1_path": "/World/table/collider",
            "sensor_names": ["hand"],
        }
    ]
    contact = probe.evaluate_prohibited_activity(
        trace=contact_trace,
        source_writer_audit=_zero_writer_audit(),
        attachment_events=[],
    )
    assert contact["counts"]["unexpected_robot_contact"] == 1
    assert contact["passed"] is False


def _first_contacts() -> dict:
    return {
        "left": {
            "physics_step": 900,
            "finger_body_path": "/World/Franka/panda_leftfinger",
            "finger_collider_path": "/left/collider",
            "calibration_collider_path": "/World/TrajectoryPreflight/CalibrationBody",
            "sensor_names": ["left"],
            "resolved_contact_count": 1,
        },
        "right": {
            "physics_step": 902,
            "finger_body_path": "/World/Franka/panda_rightfinger",
            "finger_collider_path": "/right/collider",
            "calibration_collider_path": "/World/TrajectoryPreflight/CalibrationBody",
            "sensor_names": ["right"],
            "resolved_contact_count": 1,
        },
    }


def _contact_onset_brackets() -> dict:
    def previous(physics_step, inner_gap_m):
        evidence = {"physics_step": physics_step, "normalized_contacts": []}
        return {
            "physics_step": physics_step,
            "inner_gap_m": inner_gap_m,
            "finger_collider_world_matrices": _finger_world_matrices(),
            "gap_error_bound": _gap_error_bound(),
            "normalized_contact_evidence": evidence,
            "normalized_contact_evidence_sha256": probe.canonical_json_sha256(
                evidence
            ),
        }

    return {
        "left": {
            "previous_no_contact": previous(899, 0.0711),
            "first_contact": {
                "physics_step": 900,
                "inner_gap_m": 0.0709,
                "finger_collider_world_matrices": _finger_world_matrices(),
                "gap_error_bound": _gap_error_bound(),
            },
        },
        "right": {
            "previous_no_contact": previous(901, 0.0714),
            "first_contact": {
                "physics_step": 902,
                "inner_gap_m": 0.0712,
                "finger_collider_world_matrices": _finger_world_matrices(),
                "gap_error_bound": _gap_error_bound(),
            },
        },
    }


def test_contact_records_require_current_step_and_resolved_body_paths():
    frames = {
        name: {"physics_step": 12.0, "contacts": []}
        for name in ("left", "right", "hand")
    }
    frames["left"]["contacts"] = [
        {
            "body0": "/left/collider",
            "body1": "/World/TrajectoryPreflight/CalibrationBody",
            "position": [0.0, -0.03, 1.0],
            "normal": [0.0, 1.0, 0.0],
            "impulse": [0.0, 0.001, 0.0],
        }
    ]
    records = probe.normalize_current_contacts(
        frames,
        physics_step=12,
        resolve_body_path=lambda path: {
            "/left/collider": "/World/Franka/panda_leftfinger",
            "/World/TrajectoryPreflight/CalibrationBody": (
                "/World/TrajectoryPreflight/CalibrationBody"
            ),
        }[path],
    )
    assert records[0]["physics_step"] == 12
    assert records[0]["body0_path"] == "/World/Franka/panda_leftfinger"

    frames["right"]["physics_step"] = 11.0
    with pytest.raises(ValueError, match="contact_sensor_frame_step_mismatch"):
        probe.normalize_current_contacts(
            frames,
            physics_step=12,
            resolve_body_path=lambda path: path,
        )


def _calibration_clearance_budget(**updates):
    values = {
        "calibration_body_world_bounds_m": {
            "min_m": [-0.002, -0.035, 1.498],
            "max_m": [0.002, 0.035, 1.502],
        },
        "obstacle_world_bounds_m": {
            "/World/Franka/panda_hand": {
                "min_m": [-0.02, -0.02, 1.60],
                "max_m": [0.02, 0.02, 1.64],
            },
            "/World/Franka/panda_link7": {
                "min_m": [0.18, -0.01, 1.49],
                "max_m": [0.20, 0.01, 1.51],
            },
            "/World/beaker2": {
                "min_m": [0.20, -0.035, 0.96],
                "max_m": [0.24, 0.035, 1.04],
            },
            "/World/table": {
                "min_m": [-1.0, -1.0, 0.69],
                "max_m": [1.0, 1.0, 0.70],
            },
        },
        "obstacle_contact_offset_bounds_m": {
            "/World/Franka/panda_hand": 0.0001,
            "/World/Franka/panda_link7": 0.0001,
            "/World/beaker2": 0.002,
            "/World/table": None,
        },
        "obstacle_roles": {
            "/World/Franka/panda_hand": "dynamic",
            "/World/Franka/panda_link7": "dynamic",
            "/World/beaker2": "kinematic",
            "/World/table": "static",
        },
        "calibration_body_role": "static",
        "required_obstacle_paths": sorted(
            [
                "/World/Franka/panda_hand",
                "/World/Franka/panda_link7",
                "/World/beaker2",
                "/World/table",
            ]
        ),
        "calibration_body_projection_interval_m": [-0.035, 0.035],
        "finger_inner_projection_interval_m": [-0.0387, 0.0387],
        "calibration_body_contact_offset_m": 0.0001,
        "numerical_margin_m": 0.001,
    }
    values.update(updates)
    return probe.evaluate_remote_calibration_clearance_budget(**values)


def test_remote_calibration_budget_covers_every_obstacle_offset_and_placement():
    result = _calibration_clearance_budget()
    assert set(result["per_obstacle"]) == {
        "/World/Franka/panda_hand",
        "/World/Franka/panda_link7",
        "/World/beaker2",
        "/World/table",
    }
    assert result["placement_between_finger_pads"] is True
    assert result["per_obstacle"]["/World/table"]["interaction_mode"] == (
        "static_static_no_contact_pair"
    )
    assert result["per_obstacle"]["/World/table"][
        "obstacle_contact_offset_bound_m"
    ] is None
    assert result["per_obstacle"]["/World/table"]["required_clearance_m"] == (
        pytest.approx(0.001)
    )
    assert all(record["passed"] for record in result["per_obstacle"].values())
    assert result["passed"] is True

    unknown = _calibration_clearance_budget(
        obstacle_contact_offset_bounds_m={
            **{
                path: value
                for path, value in _calibration_clearance_budget()[
                    "obstacle_contact_offset_bounds_m"
                ].items()
            },
            "/World/Franka/panda_link7": None,
        }
    )
    assert unknown["per_obstacle"]["/World/Franka/panda_link7"]["passed"] is False
    assert unknown["passed"] is False

    role_drift = _calibration_clearance_budget(
        obstacle_roles={
            **_calibration_clearance_budget()["obstacle_roles"],
            "/World/table": "kinematic",
        }
    )
    assert role_drift["per_obstacle"]["/World/table"]["passed"] is False
    assert role_drift["passed"] is False


def _source_isolation_snapshot(checkpoint):
    return probe.evaluate_source_isolation_snapshot(
        checkpoint=checkpoint,
        source_body_path="/World/beaker2",
        source_kinematic_enabled=True,
        filtered_pair_targets=_geometry_catalogs()["all_robot_rigid_body_paths"],
        expected_robot_rigid_body_paths=_geometry_catalogs()[
            "all_robot_rigid_body_paths"
        ],
        contact_report_api_applied=False,
        contact_report_threshold=float(np.finfo(np.float32).max),
        source_world_matrix=_matrix(z=1.0),
        expected_source_world_matrix=_matrix(z=1.0),
    )


def _source_isolation_snapshots():
    return [
        _source_isolation_snapshot(checkpoint)
        for checkpoint in (
            "post_task_reset_1",
            "post_task_reset_2",
            "pre_world_play",
            "pre_roll",
            "pre_first_shadow_action",
        )
    ]


def test_source_isolation_accepts_only_bounded_float32_matrix_recomposition():
    expected = [
        [0.7071065879183049, 0.7071069744547183, 1.6390571111468688e-07, 0.0],
        [-3.0335758399724355e-07, 7.155980197293133e-08, 0.9999999999999514, 0.0],
        [0.7071069744546722, -0.7071065879183203, 2.6510667083812223e-07, 0.0],
        [0.29499998688697815, 0.07499922066926956, 0.8233382105827332, 1.0],
    ]
    recomposed = [
        [0.7071067477931495, 0.7071068145788306, -1.2547808955210016e-06, 0.0],
        [5.363951570691583e-07, 1.2381329699273635e-06, 0.9999999999990898, 0.0],
        [0.7071068145797406, -0.707106747793179, 4.962035068389881e-07, 0.0],
        [0.29500001668930054, 0.07499980926513672, 0.8233382105827332, 1.0],
    ]
    result = probe.evaluate_source_isolation_snapshot(
        checkpoint="post_task_reset_1",
        source_body_path="/World/beaker2",
        source_kinematic_enabled=True,
        filtered_pair_targets=["/World/Franka/panda_hand"],
        expected_robot_rigid_body_paths=["/World/Franka/panda_hand"],
        contact_report_api_applied=False,
        contact_report_threshold=float(np.finfo(np.float32).max),
        source_world_matrix=recomposed,
        expected_source_world_matrix=expected,
    )

    assert result["checks"]["fixed_source_pose"] is True
    assert result["source_pose_error"]["authority"] == (
        "float32_world_matrix_recomposition_16ulp_v1"
    )
    assert result["source_pose_error"]["translation_error_m"] == pytest.approx(
        5.89349873380813e-07
    )
    assert result["source_pose_error"]["orientation_error_degrees"] == pytest.approx(
        8.336434052848328e-05
    )
    assert result["source_pose_error"]["translation_error_m"] < result[
        "source_pose_error"
    ]["translation_tolerance_m"]
    assert result["source_pose_error"]["orientation_error_degrees"] < result[
        "source_pose_error"
    ]["orientation_tolerance_degrees"]
    assert result["passed"] is True

    moved = copy.deepcopy(recomposed)
    moved[3][0] += 1.0e-4
    moved_result = probe.evaluate_source_isolation_snapshot(
        checkpoint="post_task_reset_1",
        source_body_path="/World/beaker2",
        source_kinematic_enabled=True,
        filtered_pair_targets=["/World/Franka/panda_hand"],
        expected_robot_rigid_body_paths=["/World/Franka/panda_hand"],
        contact_report_api_applied=False,
        contact_report_threshold=float(np.finfo(np.float32).max),
        source_world_matrix=moved,
        expected_source_world_matrix=expected,
    )
    assert moved_result["checks"]["fixed_source_pose"] is False
    assert moved_result["passed"] is False

    with pytest.raises(probe.MeasurementNoGo) as stopped:
        probe.require_source_isolation_snapshot(moved_result)
    assert stopped.value.reason == (
        "trajectory_preflight_source_isolation_failed:post_task_reset_1"
    )
    assert stopped.value.evidence == moved_result
    report = probe._measurement_no_go_report(
        stopped.value,
        run_id="run-1",
        run_identity_sha256="a" * 64,
    )
    assert report["measurement_abort"]["evidence"] == moved_result
    assert report["measurement_abort"]["interaction_prevented"] is True
    assert report["measurement_decision"] == probe.NO_GO_DECISION


def test_source_isolation_requires_exact_targets_suppression_pose_and_checkpoints():
    snapshots = _source_isolation_snapshots()
    assert all(snapshot["passed"] for snapshot in snapshots)

    wrong_targets = probe.evaluate_source_isolation_snapshot(
        checkpoint="pre_roll",
        source_body_path="/World/beaker2",
        source_kinematic_enabled=True,
        filtered_pair_targets=["/World/Franka/panda_hand"],
        expected_robot_rigid_body_paths=_geometry_catalogs()[
            "all_robot_rigid_body_paths"
        ],
        contact_report_api_applied=False,
        contact_report_threshold=float(np.finfo(np.float32).max),
        source_world_matrix=_matrix(z=1.0),
        expected_source_world_matrix=_matrix(z=1.0),
    )
    assert wrong_targets["checks"]["exact_filtered_pair_targets"] is False
    assert wrong_targets["passed"] is False

    moved = probe.evaluate_source_isolation_snapshot(
        checkpoint="pre_roll",
        source_body_path="/World/beaker2",
        source_kinematic_enabled=True,
        filtered_pair_targets=_geometry_catalogs()["all_robot_rigid_body_paths"],
        expected_robot_rigid_body_paths=_geometry_catalogs()[
            "all_robot_rigid_body_paths"
        ],
        contact_report_api_applied=False,
        contact_report_threshold=float(np.finfo(np.float32).max),
        source_world_matrix=_matrix(x=0.001, z=1.0),
        expected_source_world_matrix=_matrix(z=1.0),
    )
    assert moved["checks"]["fixed_source_pose"] is False
    assert moved["passed"] is False


def test_collision_enable_interlock_has_no_hidden_step_and_observes_first_step():
    events = []

    class World:
        current_time_step_index = 50

        def is_playing(self):
            return True

        def pause(self):
            events.append("pause")

        def play(self):
            events.append("play")

        def step(self, *, render):
            assert render is False
            events.append("step")
            self.current_time_step_index += 1

    class App:
        def update(self):
            events.append("update")

    class Attribute:
        value = False

        def Set(self, value):
            events.append(f"set:{value}")
            self.value = value

        def Get(self):
            return self.value

    def read_open_state():
        events.append("open")
        return {
            "joint_positions_m": [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M],
            "upper_limits_m": [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M],
            "position_tolerance_m": MEASURED_OPEN_TOLERANCE_M,
        }

    def observe_first_step(physics_step):
        events.append(f"observe:{physics_step}")
        return []

    def read_post_enable_budget():
        events.append("clearance_post")
        return _calibration_clearance_budget()

    evidence = probe._set_calibration_collision(
        app=App(),
        world=World(),
        collision_attribute=Attribute(),
        enabled=True,
        read_open_state=read_open_state,
        observe_first_enabled_step=observe_first_step,
        pre_enable_clearance_budget=_calibration_clearance_budget(),
        read_post_enable_clearance_budget=read_post_enable_budget,
    )

    assert events == [
        "pause",
        "update",
        "open",
        "set:True",
        "update",
        "clearance_post",
        "play",
        "step",
        "observe:51",
    ]
    assert evidence["physics_step_before_pause"] == 50
    assert evidence["physics_step_after_enable_update"] == 50
    assert evidence["first_enabled_physics_step"] == 51
    assert evidence["first_enabled_step_contacts"] == []
    assert evidence["pre_enable_clearance_budget"]["passed"] is True
    assert evidence["post_enable_clearance_budget"]["passed"] is True
    assert evidence["passed"] is True


def test_collision_enable_never_called_when_pre_enable_budget_fails():
    events = []

    class World:
        current_time_step_index = 50

        def is_playing(self):
            return True

        def pause(self):
            events.append("pause")

        def play(self):
            events.append("play")

        def step(self, *, render):
            events.append("step")

    class Attribute:
        def Set(self, value):
            events.append(f"set:{value}")

        def Get(self):
            return False

    bad_bounds = copy.deepcopy(
        _calibration_clearance_budget()["obstacle_world_bounds_m"]
    )
    bad_bounds["/World/Franka/panda_hand"] = {
        "min_m": [-0.002, -0.035, 1.498],
        "max_m": [0.002, 0.035, 1.502],
    }
    failed_budget = _calibration_clearance_budget(
        obstacle_world_bounds_m=bad_bounds
    )
    result = probe._set_calibration_collision(
        app=object(),
        world=World(),
        collision_attribute=Attribute(),
        enabled=True,
        read_open_state=lambda: (_ for _ in ()).throw(
            AssertionError("open state must not be read")
        ),
        observe_first_enabled_step=lambda _: (_ for _ in ()).throw(
            AssertionError("physics step must not be observed")
        ),
        pre_enable_clearance_budget=failed_budget,
        read_post_enable_clearance_budget=lambda: (_ for _ in ()).throw(
            AssertionError("post-enable budget must not be read")
        ),
    )
    assert result["failure_reason"] == (
        "pre_enable_calibration_clearance_budget_failed"
    )
    assert result["passed"] is False
    assert events == []


def test_collision_enable_interlock_rejects_not_physically_open():
    class World:
        current_time_step_index = 5

        def is_playing(self):
            return True

        def pause(self):
            pass

        def play(self):
            pass

        def step(self, *, render):
            self.current_time_step_index += 1

    class App:
        def update(self):
            pass

    class Attribute:
        def Set(self, value):
            raise AssertionError("collision must not be enabled")

        def Get(self):
            return False

    with pytest.raises(RuntimeError, match="calibration_body_not_physically_open"):
        probe._set_calibration_collision(
            app=App(),
            world=World(),
            collision_attribute=Attribute(),
            enabled=True,
            read_open_state=lambda: {
                "joint_positions_m": [0.039, MEASURED_OPEN_TARGET_M],
                "upper_limits_m": [
                    MEASURED_OPEN_TARGET_M,
                    MEASURED_OPEN_TARGET_M,
                ],
                "position_tolerance_m": MEASURED_OPEN_TOLERANCE_M,
            },
            observe_first_enabled_step=lambda _: [],
            pre_enable_clearance_budget=_calibration_clearance_budget(),
            read_post_enable_clearance_budget=_calibration_clearance_budget,
        )


def test_calibration_layer_cleanup_requires_no_step_and_physx_absence():
    evidence = probe.evaluate_calibration_layer_cleanup(
        previous_session_sublayers=["base-a", "base-b"],
        inserted_session_sublayers=["calibration-layer", "base-a", "base-b"],
        restored_session_sublayers=["base-a", "base-b"],
        calibration_layer_identifier="calibration-layer",
        authoring_edit_target="calibration-layer",
        enable_edit_target="calibration-layer",
        disable_edit_target="calibration-layer",
        previous_edit_target="root-layer",
        restored_edit_target="root-layer",
        physics_step_before_cleanup=120,
        physics_step_after_cleanup=120,
        calibration_body_valid_after_cleanup=False,
        calibration_scope_valid_after_cleanup=False,
        overlap_hit_paths_after_cleanup=[
            "/World/Franka/panda_leftfinger/geometry/pad"
        ],
        calibration_body_path=probe.CALIBRATION_BODY_PATH,
    )
    assert evidence["passed"] is True

    stepped = probe.evaluate_calibration_layer_cleanup(
        previous_session_sublayers=["base-a", "base-b"],
        inserted_session_sublayers=["calibration-layer", "base-a", "base-b"],
        restored_session_sublayers=["base-a", "base-b"],
        calibration_layer_identifier="calibration-layer",
        authoring_edit_target="calibration-layer",
        enable_edit_target="calibration-layer",
        disable_edit_target="calibration-layer",
        previous_edit_target="root-layer",
        restored_edit_target="root-layer",
        physics_step_before_cleanup=120,
        physics_step_after_cleanup=121,
        calibration_body_valid_after_cleanup=False,
        calibration_scope_valid_after_cleanup=False,
        overlap_hit_paths_after_cleanup=[],
        calibration_body_path=probe.CALIBRATION_BODY_PATH,
    )
    assert stepped["passed"] is False

    stale_shape = copy.deepcopy(evidence)
    stale_shape = probe.evaluate_calibration_layer_cleanup(
        previous_session_sublayers=stale_shape["previous_session_sublayers"],
        inserted_session_sublayers=stale_shape["inserted_session_sublayers"],
        restored_session_sublayers=stale_shape["restored_session_sublayers"],
        calibration_layer_identifier=stale_shape["calibration_layer_identifier"],
        authoring_edit_target=stale_shape["authoring_edit_target"],
        enable_edit_target=stale_shape["enable_edit_target"],
        disable_edit_target=stale_shape["disable_edit_target"],
        previous_edit_target=stale_shape["previous_edit_target"],
        restored_edit_target=stale_shape["restored_edit_target"],
        physics_step_before_cleanup=120,
        physics_step_after_cleanup=120,
        calibration_body_valid_after_cleanup=False,
        calibration_scope_valid_after_cleanup=False,
        overlap_hit_paths_after_cleanup=[probe.CALIBRATION_BODY_PATH],
        calibration_body_path=probe.CALIBRATION_BODY_PATH,
    )
    assert stale_shape["passed"] is False


def _stage_inventory() -> dict:
    payload = {
        "joint_paths": ["/World/Franka/panda_joint1"],
        "constraint_paths": ["/World/Franka/panda_joint1"],
        "fixed_attachment_paths": [],
        "constraint_records": [
            {
                "path": "/World/Franka/panda_joint1",
                "schema_type": "PhysicsRevoluteJoint",
                "body0_targets": ["/World/Franka/panda_link0"],
                "body1_targets": ["/World/Franka/panda_link1"],
            }
        ],
    }
    return {**payload, "inventory_sha256": probe.canonical_json_sha256(payload)}


def _source_attached_stage_inventory():
    attached = _stage_inventory()
    record = {
        "path": "/World/UnexpectedSourceAttachment",
        "schema_type": "PhysicsFixedJoint",
        "body0_targets": ["/World/beaker2"],
        "body1_targets": ["/World/Franka/panda_hand"],
    }
    attached["joint_paths"].append(record["path"])
    attached["constraint_paths"].append(record["path"])
    attached["fixed_attachment_paths"].append(record["path"])
    attached["constraint_records"].append(record)
    for key in ("joint_paths", "constraint_paths", "fixed_attachment_paths"):
        attached[key].sort()
    attached["constraint_records"].sort(key=lambda item: item["path"])
    payload = {key: value for key, value in attached.items() if key != "inventory_sha256"}
    attached["inventory_sha256"] = probe.canonical_json_sha256(payload)
    return attached, record


def test_attachment_inventory_rejects_unchanged_preexisting_source_robot_joint():
    attached, record = _source_attached_stage_inventory()

    result = probe.evaluate_attachment_inventory(
        pre_inventory=attached,
        post_inventory=copy.deepcopy(attached),
        source_body_path="/World/beaker2",
        robot_rigid_body_paths=_geometry_catalogs()["all_robot_rigid_body_paths"],
    )
    assert result["checks"]["inventories_unchanged"] is True
    assert result["checks"]["source_robot_attachment_absent"] is False
    assert result["source_robot_constraint_paths"] == [record["path"]]
    assert result["passed"] is False


def _authoritative_reset_record() -> dict:
    payload = {
        "authority": "post_task_reset_pre_session_mutation_v1",
        "joint_positions": [0.0] * 7
        + [MEASURED_OPEN_TARGET_M, MEASURED_OPEN_TARGET_M],
        "joint_position_units": ["rad"] * 7 + ["m", "m"],
    }
    return {**payload, "record_sha256": probe.canonical_json_sha256(payload)}


def _remote_tool_matrix_49_degrees():
    angle = math.radians(49.0)
    return [
        [math.cos(angle), -math.sin(angle), 0.0, 0.0],
        [math.sin(angle), math.cos(angle), 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 1.5, 1.0],
    ]


def _valid_runtime_report() -> dict:
    calibration_axis = probe.derive_opening_axis_world(
        _remote_tool_matrix_49_degrees()
    )
    body_spec = probe.calibration_body_spec(
        reset_tool_world_matrix=_remote_tool_matrix_49_degrees(),
        translation_tool_m=[0.009, 0.0, 0.006],
        opening_axis_world=calibration_axis,
        size_m=[0.002, 0.070, 0.002],
        contact_offset_m=0.0001,
    )
    session_text = "# geometry-aware trajectory preflight session\n"
    open_tolerance = MEASURED_OPEN_TOLERANCE_M
    geometry_catalogs = _geometry_catalogs()
    rigid_body_paths = geometry_catalogs["robot_rigid_body_paths"]
    all_rigid_body_paths = geometry_catalogs["all_robot_rigid_body_paths"]
    reset_record = _authoritative_reset_record()
    stage_inventory = _stage_inventory()
    return {
        "schema_version": 1,
        "manifest_type": probe.MANIFEST_TYPE,
        "lifecycle_status": "measurement_complete_application_closed",
        "shutdown_status": "application_closed",
        "measurement_decision": probe.GO_DECISION,
        "runtime_identity": {
            "pid": 2468,
            "run_id": "run-1",
            "run_identity_sha256": "a" * 64,
        },
        "config_path": str(probe.DEFAULT_CONFIG.resolve()),
        "config_sha256": probe.EXPECTED_CONFIG_SHA256,
        "asset_path": str(probe.ASSET_PATH.resolve()),
        "asset_sha256": probe.EXPECTED_ASSET_SHA256,
        "robot_path": str(probe.ROBOT_PATH.resolve()),
        "robot_sha256": probe.EXPECTED_ROBOT_SHA256,
        "runtime_contract": {
            "producer_schema": "geometry_aware_trajectory_preflight_runtime_v2",
            "profile": "geometry_aware_trajectory_preflight_v1",
            "physics_dt": 1.0 / 600.0,
            "control_dt": 1.0 / 30.0,
            "physics_substeps_per_action": 20,
            "pre_roll_steps": 600,
            "particle_count": 0,
            "stage_units_in_meters": 1.0,
            "joint_position_units": ["rad"] * 7 + ["m", "m"],
            "joint_velocity_units": ["rad_s"] * 7 + ["m_s", "m_s"],
            "robot_rigid_body_paths": rigid_body_paths,
            "colliderless_robot_bodies": geometry_catalogs[
                "colliderless_robot_bodies"
            ],
            "all_robot_rigid_body_paths": all_rigid_body_paths,
            "robot_collider_inventory": geometry_catalogs[
                "robot_collider_inventory"
            ],
            "robot_inventory_sha256": geometry_catalogs["inventory_sha256"],
            "pre_measurement_stage_inventory": stage_inventory,
            "post_measurement_stage_inventory": copy.deepcopy(stage_inventory),
            "rmpflow_runtime_data": {
                path: digest
                for path, digest in probe.PINNED_RUNTIME_DATA_SHA256.items()
            },
            "source_isolation_snapshots": _source_isolation_snapshots(),
            "particles_disabled": True,
            "source_robot_collision_filtered": True,
            "source_contact_reporting_disabled": True,
            "source_pose_fixed": True,
            "diagnostic_session_layer_text": session_text,
            "diagnostic_session_layer_sha256": hashlib.sha256(
                session_text.encode("utf-8")
            ).hexdigest(),
            "diagnostic_session_mutations": [
                {
                    "operation": "set_active",
                    "path": "/World/InternDataParityFluid/Particles",
                    "value": False,
                },
                {
                    "operation": "set_kinematic_enabled",
                    "path": "/World/beaker2",
                    "value": True,
                },
                {
                    "operation": "filter_collision_pairs",
                    "path": "/World/beaker2",
                    "targets": all_rigid_body_paths,
                },
                {
                    "operation": "disable_contact_reporting",
                    "path": "/World/beaker2",
                },
                {
                    "operation": "define_static_calibration_body",
                    "spec_sha256": probe.canonical_json_sha256(body_spec),
                },
            ],
            "authoritative_reset_record": reset_record,
            "reset_joint_positions_after": list(reset_record["joint_positions"]),
            "trajectory_inputs": {
                "tool_orientation_wxyz": [0.0, 0.0, 1.0, 0.0],
                "grasp_offset_object_m": [0.0, 0.0, 0.0],
                "approach_direction_world": [0.0, 0.0, -1.0],
                "control_to_tool_center_matrix_m": [
                    [-1.0, 0.0, 0.0, 0.0],
                    [0.0, -1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, -0.0034, 1.0],
                ],
                "pregrasp_distance_m": 0.120,
                "insert_distance_m": 0.060,
                "insertion_speed_m_s": 0.006,
                "remote_close_speed_m_s": 0.003,
                "settle_duration_s": 0.10,
                "contact_settle_duration_s": 0.10,
                "numerical_margin_m": 0.001,
                "requested_open_target_m": REQUESTED_OPEN_TARGET_M,
                "canonical_open_target_m": MEASURED_OPEN_TARGET_M,
                "physical_open_upper_limits_m": [
                    MEASURED_OPEN_TARGET_M,
                    MEASURED_OPEN_TARGET_M,
                ],
                "open_position_tolerance_m": open_tolerance,
                "position_threshold_m": 0.0005,
                "orientation_threshold_degrees": 0.5,
            },
        },
        "calibration": {
            "body_spec": body_spec,
            "body_spec_sha256": probe.canonical_json_sha256(body_spec),
            "aperture_points": _aperture_points(),
            "velocity_samples": _velocity_samples(),
            "contact_onset_brackets": _contact_onset_brackets(),
            "first_contacts": _first_contacts(),
            "contact_attribution_ambiguous": False,
            "finger_collider_paths": {
                "left": ["/left/collider", "/left/tip_collider"],
                "right": ["/right/collider", "/right/tip_collider"],
            },
            "remote_clearance_m": {
                "calibration_body_to_source": 0.20,
                "calibration_body_to_table": 0.10,
                "calibration_body_to_unrelated_robot_links": 0.02,
            },
            "remote_unexpected_contacts": [],
            "pre_enable_clearance_budget": _calibration_clearance_budget(),
            "collision_interlock": {
                "timeline_was_playing": True,
                "physics_step_before_pause": 850,
                "physics_step_after_pause_update": 850,
                "physics_step_after_enable_update": 850,
                "physics_step_after_resume": 850,
                "first_enabled_physics_step": 851,
                "collision_enabled_before": False,
                "collision_enabled_after": True,
                "physical_open_state": {
                    "joint_positions_m": [
                        MEASURED_OPEN_TARGET_M,
                        MEASURED_OPEN_TARGET_M,
                    ],
                    "upper_limits_m": [
                        MEASURED_OPEN_TARGET_M,
                        MEASURED_OPEN_TARGET_M,
                    ],
                    "position_tolerance_m": open_tolerance,
                },
                "pre_enable_clearance_budget": _calibration_clearance_budget(),
                "post_enable_clearance_budget": _calibration_clearance_budget(),
                "first_enabled_step_contacts": [],
                "passed": True,
            },
        },
        "shadow_sweep": {
            "trace": _valid_trace(complete_insert=True),
            "geometry_catalogs": geometry_catalogs,
            "opening_axis_world": [0.0, 1.0, 0.0],
            "opening_axis_authority": "literal_commanded_tool_orientation_v1",
            "opening_axis_tool_orientation_wxyz": [0.0, 0.0, 1.0, 0.0],
            "source_contact_offset_m": 0.002,
            "finger_edge_radii_m": {"left": 0.020, "right": 0.020},
            "source_writer_audit": _zero_writer_audit(),
            "attachment_events": [],
            "controller_evidence": {
                "phase": "CLOSE",
                "phase_index": 4,
                "phase_history": ["PREGRASP", "ALIGN", "INSERT", "SETTLE", "CLOSE"],
                "open_command_emitted": True,
                "open_command_count": 2,
                "close_command_emitted": False,
                "close_action_control_index": None,
                "probe_completed": False,
                "open_position_m": MEASURED_OPEN_TARGET_M,
                "open_position_tolerance_m": open_tolerance,
                "open_position_ready": True,
                "open_confirmed_control_index": 2,
                "first_arm_command_control_index": 3,
                "arm_before_open_violation": False,
                "control_invocation_count": 307,
                "arm_action_count": 305,
                "finger_action_count": 2,
                "noop_action_count": 0,
                "last_emitted_phase": "SETTLE",
                "last_emitted_action_kind": "arm",
                "lift_command_emitted": False,
                "latched_source_position": [0.0, 0.0, 1.0],
                "latched_end_effector_orientation_wxyz": [0.0, 0.0, 1.0, 0.0],
                "grasp_position": [0.0, 0.0, 1.0],
                "pregrasp_position": [0.0, 0.0, 1.120],
                "align_position": [0.0, 0.0, 1.060],
                "approach_direction": [0.0, 0.0, -1.0],
                "grasp_offset": [0.0, 0.0, 0.0],
                "control_to_end_effector_matrix_m": [
                    [-1.0, 0.0, 0.0, 0.0],
                    [0.0, -1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, -0.0034, 1.0],
                ],
                "approach_speed_m_s": 0.006,
                "close_speed_m_s": 0.003,
                "pregrasp_distance_m": 0.120,
                "insert_distance_m": 0.060,
                "position_threshold_m": 0.0005,
                "orientation_threshold_degrees": 0.5,
            },
        },
    }


def test_parent_independently_recomputes_every_go_conjunct():
    result = probe.evaluate_runtime_measurements(_valid_runtime_report())

    assert result["decision"] == probe.GO_DECISION
    assert result["failed_checks"] == []
    assert all(result["checks"].values())
    assert result["derived"]["clearance_budget"]["passed"] is True
    assert result["derived"]["trajectory_uncertainty"]["passed"] is True
    assert result["derived"]["trajectory_uncertainty"]["per_side_m"]["left"] > 0.0


def test_parent_requires_exact_colliderless_robot_partition_and_filter_coverage():
    runtime_tampered = _valid_runtime_report()
    runtime_tampered["runtime_contract"]["colliderless_robot_bodies"] = {}
    runtime_result = probe.evaluate_runtime_measurements(runtime_tampered)
    assert runtime_result["checks"]["environment_inventory"] is False
    assert runtime_result["decision"] == probe.NO_GO_DECISION

    geometry_tampered = _valid_runtime_report()
    geometry_tampered["shadow_sweep"]["geometry_catalogs"][
        "colliderless_robot_bodies"
    ] = {}
    geometry_result = probe.evaluate_runtime_measurements(geometry_tampered)
    assert geometry_result["checks"]["parent_geometry_recomputed"] is False
    assert geometry_result["decision"] == probe.NO_GO_DECISION

    filter_tampered = _valid_runtime_report()
    filter_tampered["runtime_contract"]["diagnostic_session_mutations"][2][
        "targets"
    ] = [
        path
        for path in filter_tampered["runtime_contract"][
            "all_robot_rigid_body_paths"
        ]
        if path != "/World/Franka/panda_link8"
    ]
    filter_result = probe.evaluate_runtime_measurements(filter_tampered)
    assert filter_result["checks"]["environment_inventory"] is False
    assert filter_result["checks"]["source_isolation"] is True
    assert filter_result["decision"] == probe.NO_GO_DECISION


def test_tracking_thresholds_cover_only_insert_and_settle_without_double_budgeting():
    pregrasp = _valid_runtime_report()
    pregrasp_record = next(
        record
        for record in pregrasp["shadow_sweep"]["trace"]
        if record["action_kind"] == "ARM_PREGRASP"
    )
    pregrasp_record["measured_tool_pose"]["position_m"][0] = 0.1
    assert probe.evaluate_runtime_measurements(pregrasp)["decision"] == probe.GO_DECISION

    insert = _valid_runtime_report()
    insert_record = next(
        record
        for record in insert["shadow_sweep"]["trace"]
        if record["action_kind"] == "ARM_INSERT"
    )
    insert_record["measured_tool_pose"]["position_m"][0] = 0.0006
    result = probe.evaluate_runtime_measurements(insert)
    assert result["checks"]["tracking_within_configured_thresholds"] is False
    assert result["decision"] == probe.NO_GO_DECISION
    assert result["derived"]["clearance_budget"]["per_side"]["left"][
        "required_clearance_m"
    ] > 0.004


def test_constant_lateral_error_consumes_reported_positive_clearance_and_cannot_go():
    baseline_report = _valid_runtime_report()
    baseline = probe.evaluate_runtime_measurements(baseline_report)
    base_required = (
        baseline_report["shadow_sweep"]["source_contact_offset_m"]
        + baseline["derived"]["effective_contact_offsets"]["bounds_m"]["left"]
        + baseline["derived"]["trajectory_uncertainty"]["per_side_m"]["left"]
        + baseline_report["runtime_contract"]["trajectory_inputs"][
            "numerical_margin_m"
        ]
    )
    reported_remaining_before_absolute_error = 0.0002999
    geometric_clearance = base_required + reported_remaining_before_absolute_error
    left_center_y = -0.035 - geometric_clearance - 0.005

    report = _valid_runtime_report()
    for record in report["shadow_sweep"]["trace"]:
        if record["action_kind"] in {"ARM_INSERT", "ARM_SETTLE"}:
            record["measured_tool_pose"]["position_m"][0] += 0.0004
        for collider in record["geometry_world_matrices"][
            "/World/Franka/panda_leftfinger"
        ]:
            collider["matrix"][3][1] = left_center_y
        for collider in record["collider_world_matrices"]["left_finger"]:
            collider["matrix"][3][1] = left_center_y
        record["geometric_clearance_m"]["left"] = geometric_clearance

    result = probe.evaluate_runtime_measurements(report)
    assert reported_remaining_before_absolute_error > 0.0
    assert result["derived"]["trajectory_uncertainty"][
        "maximum_absolute_cross_track_error_m"
    ] >= 0.0004
    assert result["checks"]["tracking_within_configured_thresholds"] is True
    assert result["checks"]["swept_clearance"] is False
    assert result["derived"]["clearance_budget"]["per_side"]["left"][
        "remaining_clearance_m"
    ] < 0.0
    assert result["decision"] == probe.NO_GO_DECISION


def test_parent_rejects_calibration_budget_isolation_and_preexisting_attachment():
    bad_budget_report = _valid_runtime_report()
    overlapping = copy.deepcopy(
        _calibration_clearance_budget()["obstacle_world_bounds_m"]
    )
    overlapping["/World/Franka/panda_hand"] = {
        "min_m": [-0.002, -0.035, 1.498],
        "max_m": [0.002, 0.035, 1.502],
    }
    failed_budget = _calibration_clearance_budget(
        obstacle_world_bounds_m=overlapping
    )
    bad_budget_report["calibration"]["pre_enable_clearance_budget"] = failed_budget
    bad_budget_report["calibration"]["collision_interlock"][
        "pre_enable_clearance_budget"
    ] = copy.deepcopy(failed_budget)
    budget_result = probe.evaluate_runtime_measurements(bad_budget_report)
    assert budget_result["checks"]["calibration_clearance"] is False
    assert budget_result["decision"] == probe.NO_GO_DECISION

    isolation_report = _valid_runtime_report()
    isolation_report["runtime_contract"]["source_isolation_snapshots"][3][
        "passed"
    ] = False
    isolation_result = probe.evaluate_runtime_measurements(isolation_report)
    assert isolation_result["checks"]["source_isolation"] is False
    assert isolation_result["decision"] == probe.NO_GO_DECISION

    attachment_report = _valid_runtime_report()
    attached, _ = _source_attached_stage_inventory()
    attachment_report["runtime_contract"]["pre_measurement_stage_inventory"] = (
        attached
    )
    attachment_report["runtime_contract"]["post_measurement_stage_inventory"] = (
        copy.deepcopy(attached)
    )
    attachment_result = probe.evaluate_runtime_measurements(attachment_report)
    assert attachment_result["checks"]["source_robot_attachment_absent"] is False
    assert attachment_result["decision"] == probe.NO_GO_DECISION


@pytest.mark.parametrize(
    ("mutate", "failed_check"),
    [
        (
            lambda report: report["calibration"]["contact_onset_brackets"].update(left=None),
            "effective_contact_offsets",
        ),
        (
            lambda report: report["calibration"]["aperture_points"][2].update(
                cooked_inner_gap_m=0.076
            ),
            "aperture_calibration",
        ),
        (
            lambda report: report["shadow_sweep"]["trace"][0][
                "environment_clearance_m"
            ].update(hand_to_source=0.0),
            "swept_clearance",
        ),
        (
            lambda report: report["shadow_sweep"]["trace"].pop(),
            "shadow_trace",
        ),
        (
            lambda report: report["shadow_sweep"]["trace"][0].update(
                geometry_world_matrices={}
            ),
            "parent_geometry_recomputed",
        ),
        (
            lambda report: report["shadow_sweep"].update(
                attachment_events=[{"kind": "fixed_joint"}]
            ),
            "prohibited_activity",
        ),
        (
            lambda report: report["shadow_sweep"].update(
                opening_axis_world=report["calibration"]["body_spec"][
                    "opening_axis_world"
                ]
            ),
            "shadow_opening_axis",
        ),
        (
            lambda report: report["runtime_contract"][
                "post_measurement_stage_inventory"
            ].update(fixed_attachment_paths=["/World/UnexpectedFixedJoint"]),
            "stage_inventory_unchanged",
        ),
        (
            lambda report: report["runtime_contract"][
                "authoritative_reset_record"
            ].update(record_sha256="0" * 64),
            "authoritative_reset",
        ),
        (
            lambda report: report["runtime_contract"][
                "diagnostic_session_mutations"
            ][2].update(targets=["/World/Franka/panda_hand"]),
            "environment_inventory",
        ),
        (
            lambda report: report["shadow_sweep"]["geometry_catalogs"][
                "robot_bodies"
            ]["/World/Franka/panda_link7"]["colliders"][0].update(
                contact_offset={
                    "contact_offset_m": None,
                    "authority": "unresolved",
                }
            ),
            "swept_clearance",
        ),
    ],
)
def test_child_go_claim_cannot_override_parent_recomputed_no_go(mutate, failed_check):
    report = _valid_runtime_report()
    mutate(report)

    result = probe.evaluate_runtime_measurements(report)

    assert report["measurement_decision"] == probe.GO_DECISION
    assert result["decision"] == probe.NO_GO_DECISION
    assert failed_check in result["failed_checks"]


def _producer_exact_runtime_report() -> dict:
    report = _valid_runtime_report()
    parent = probe.evaluate_runtime_measurements(report)
    report["child_evaluation"] = copy.deepcopy(parent)
    report["measurement_decision"] = parent["decision"]
    return report


def _producer_provisional_runtime_report() -> dict:
    report = _producer_exact_runtime_report()
    report["lifecycle_status"] = "measurement_complete_pending_application_close"
    report["shutdown_status"] = "pending"
    return report


def test_producer_exact_fixture_requires_matching_child_and_parent_go():
    report = _producer_exact_runtime_report()
    parent = probe.evaluate_bound_runtime_report(report)
    assert report["runtime_contract"]["producer_schema"] == (
        "geometry_aware_trajectory_preflight_runtime_v2"
    )
    assert report["child_evaluation"]["decision"] == probe.GO_DECISION
    assert parent["decision"] == probe.GO_DECISION

    mismatch = copy.deepcopy(report)
    mismatch["child_evaluation"]["decision"] = probe.NO_GO_DECISION
    with pytest.raises(ValueError, match="trajectory_preflight_runtime_agreement_invalid"):
        probe.evaluate_bound_runtime_report(mismatch)


def test_strict_json_rejects_missing_malformed_duplicate_and_nonfinite(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="trajectory_preflight_runtime_report_invalid"):
        probe.load_runtime_report(missing)

    path = tmp_path / "runtime.json"
    for payload in (
        b"",
        b"{}",
        b"{}\n{}\n",
        b'{"duplicate":1,"duplicate":2}\n',
        b'{"value":NaN}\n',
        b"[]\n",
        b"\xff\n",
    ):
        path.write_bytes(payload)
        with pytest.raises(ValueError, match="trajectory_preflight_runtime_report_invalid"):
            probe.load_runtime_report(path)


def test_runtime_report_hash_and_validation_use_one_immutable_byte_buffer(tmp_path):
    report = {
        "schema_version": 1,
        "manifest_type": probe.MANIFEST_TYPE,
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
    }
    payload = probe._canonical_json_bytes(report, indent=2)
    path = tmp_path / "runtime.json"
    path.write_bytes(payload)
    immutable = path.read_bytes()
    path.write_bytes(b'{"tampered":true}\n')

    assert probe.load_runtime_report_bytes(
        immutable, source_name=str(path)
    ) == report
    artifact = probe.runtime_report_artifact_from_bytes(
        immutable, relative_path=probe.RUNTIME_REPORT_BASENAME
    )
    assert artifact == {
        "path": probe.RUNTIME_REPORT_BASENAME,
        "byte_count": len(immutable),
        "sha256": hashlib.sha256(immutable).hexdigest(),
        "authority": "single_post_quiescence_byte_buffer_v1",
    }


def test_create_only_json_is_finite_and_never_replaces_existing_output(tmp_path):
    path = tmp_path / "report.json"
    probe.atomic_create_json(path, {"decision": probe.GO_DECISION})

    with pytest.raises(FileExistsError, match="trajectory_preflight_output_exists"):
        probe.atomic_create_json(path, {"decision": probe.NO_GO_DECISION})
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "decision": probe.GO_DECISION
    }

    with pytest.raises(ValueError, match="trajectory_preflight_json_nonfinite"):
        probe.atomic_create_json(tmp_path / "nan.json", {"value": float("nan")})


def test_child_binding_requires_exact_owner_pid_run_and_runtime_identity():
    report = _valid_runtime_report()
    owner = {
        "pid": 2468,
        "run_id": "run-1",
        "run_identity_sha256": "a" * 64,
    }

    assert probe.validate_child_binding(
        owner,
        report,
        expected_child_pid=2468,
        expected_run_id="run-1",
        expected_run_identity_sha256="a" * 64,
    ) == {
        "pid": 2468,
        "run_id": "run-1",
        "run_identity_sha256": "a" * 64,
        "valid": True,
    }

    for changed_owner, changed_report, expected_pid, identity_hash in (
        ({**owner, "pid": 9999}, report, 2468, "a" * 64),
        ({**owner, "run_id": "stale"}, report, 2468, "a" * 64),
        ({**owner, "pid": True}, report, 2468, "a" * 64),
        (
            owner,
            {**report, "runtime_identity": {**report["runtime_identity"], "pid": 9}},
            2468,
            "a" * 64,
        ),
        (owner, report, 9999, "a" * 64),
        (owner, report, 2468, "b" * 64),
        (owner, {**report, "config_sha256": "b" * 64}, 2468, "a" * 64),
    ):
        with pytest.raises(ValueError, match="trajectory_preflight_child_identity_invalid"):
            probe.validate_child_binding(
                changed_owner,
                changed_report,
                expected_child_pid=expected_pid,
                expected_run_id="run-1",
                expected_run_identity_sha256=identity_hash,
            )


def test_child_parent_decision_and_closed_lifecycle_must_agree():
    report = _valid_runtime_report()
    parent = probe.evaluate_runtime_measurements(report)
    report["child_evaluation"] = copy.deepcopy(parent)
    assert probe.validate_runtime_report_agreement(report, parent) == parent["decision"]

    report["child_evaluation"]["decision"] = probe.NO_GO_DECISION
    with pytest.raises(ValueError, match="trajectory_preflight_runtime_agreement_invalid"):
        probe.validate_runtime_report_agreement(report, parent)

    report = _valid_runtime_report()
    report["child_evaluation"] = copy.deepcopy(parent)
    report["lifecycle_status"] = "measurement_complete_pending_application_close"
    with pytest.raises(ValueError, match="trajectory_preflight_runtime_agreement_invalid"):
        probe.validate_runtime_report_agreement(report, parent)


def test_parent_accepts_only_pending_child_report_after_process_quiescence():
    report = _producer_provisional_runtime_report()

    parent = probe.evaluate_bound_provisional_runtime_report(report)

    assert parent["decision"] == probe.GO_DECISION
    closed = copy.deepcopy(report)
    closed["lifecycle_status"] = "measurement_complete_application_closed"
    closed["shutdown_status"] = "application_closed"
    with pytest.raises(
        ValueError, match="trajectory_preflight_provisional_runtime_agreement_invalid"
    ):
        probe.evaluate_bound_provisional_runtime_report(closed)


def _fake_child_args(tmp_path, *, identity_sha256="a" * 64):
    return types.SimpleNamespace(
        owner=tmp_path / probe.OWNER_BASENAME,
        runtime_report=tmp_path / probe.RUNTIME_REPORT_BASENAME,
        run_id="attempt-003",
        run_identity_sha256=identity_sha256,
        config=probe.DEFAULT_CONFIG,
        headless=True,
    )


def _install_fake_isaacsim(monkeypatch, simulation_app):
    module = types.ModuleType("isaacsim")
    module.SimulationApp = simulation_app
    monkeypatch.setitem(sys.modules, "isaacsim", module)


def test_child_creates_owner_then_app_then_validates_full_identity_then_measures(
    tmp_path, monkeypatch
):
    args = _fake_child_args(tmp_path)
    events = []
    writes = {}

    class App:
        def close(self):
            events.append("app_close")

    def simulation_app(settings):
        assert settings == {"headless": True, "width": 64, "height": 64}
        events.append("app_construct")
        return App()

    def atomic_create(path, value):
        label = "owner_write" if Path(path) == args.owner else "provisional_write"
        events.append(label)
        writes[Path(path)] = copy.deepcopy(value)

    def build_identity(config):
        assert config == probe.DEFAULT_CONFIG
        events.append("full_identity")
        return {"identity_sha256": args.run_identity_sha256}

    def measure(app, observed_args):
        assert isinstance(app, App)
        assert observed_args is args
        events.append("measure")
        return _producer_provisional_runtime_report()

    _install_fake_isaacsim(monkeypatch, simulation_app)
    monkeypatch.setattr(probe, "atomic_create_json", atomic_create)
    monkeypatch.setattr(probe, "build_run_identity", build_identity)
    monkeypatch.setattr(probe, "_measure_isaac_runtime", measure)

    assert probe._run_child(args) == 0
    assert events == [
        "owner_write",
        "app_construct",
        "full_identity",
        "measure",
        "provisional_write",
        "app_close",
    ]
    assert writes[args.runtime_report]["lifecycle_status"] == (
        "measurement_complete_pending_application_close"
    )
    assert writes[args.runtime_report]["shutdown_status"] == "pending"


def test_child_identity_mismatch_after_app_stops_before_scene_measurement(
    tmp_path, monkeypatch
):
    args = _fake_child_args(tmp_path)
    events = []
    writes = {}

    class App:
        def close(self):
            events.append("app_close")

    def simulation_app(_settings):
        events.append("app_construct")
        return App()

    def atomic_create(path, value):
        label = "owner_write" if Path(path) == args.owner else "provisional_write"
        events.append(label)
        writes[Path(path)] = copy.deepcopy(value)

    def build_identity(_config):
        events.append("full_identity")
        return {"identity_sha256": "b" * 64}

    _install_fake_isaacsim(monkeypatch, simulation_app)
    monkeypatch.setattr(probe, "atomic_create_json", atomic_create)
    monkeypatch.setattr(probe, "build_run_identity", build_identity)
    monkeypatch.setattr(
        probe,
        "_measure_isaac_runtime",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("identity mismatch must stop before scene measurement")
        ),
    )

    assert probe._run_child(args) == 0
    assert events == [
        "owner_write",
        "app_construct",
        "full_identity",
        "provisional_write",
        "app_close",
    ]
    report = writes[args.runtime_report]
    assert report["measurement_decision"] == probe.RUNTIME_ERROR_DECISION
    assert report["fatal_error"]["phase"] == (
        "post_simulation_app_identity_validation"
    )
    assert report["fatal_error"]["message"] == (
        "trajectory_preflight_child_run_identity_mismatch"
    )


def test_child_persists_pending_report_before_close_can_terminate(
    tmp_path, monkeypatch
):
    args = _fake_child_args(tmp_path)
    events = []
    writes = {}

    class App:
        def close(self):
            events.append("app_close_terminates")
            raise SystemExit(0)

    def atomic_create(path, value):
        label = "owner_write" if Path(path) == args.owner else "provisional_write"
        events.append(label)
        writes[Path(path)] = copy.deepcopy(value)

    _install_fake_isaacsim(monkeypatch, lambda _settings: App())
    monkeypatch.setattr(probe, "atomic_create_json", atomic_create)
    monkeypatch.setattr(
        probe,
        "build_run_identity",
        lambda _config: {"identity_sha256": args.run_identity_sha256},
    )
    monkeypatch.setattr(
        probe,
        "_measure_isaac_runtime",
        lambda _app, _args: _producer_provisional_runtime_report(),
    )

    with pytest.raises(SystemExit) as terminated:
        probe._run_child(args)

    assert terminated.value.code == 0
    assert events == [
        "owner_write",
        "provisional_write",
        "app_close_terminates",
    ]
    assert writes[args.runtime_report]["shutdown_status"] == "pending"


def test_python_contract_requires_host_pxr_and_keeps_pinned_child_python(tmp_path):
    assert probe.PARENT_HOST_PYTHON_REQUIRES_PXR is True
    assert "host Python with pxr" in probe.PARENT_HOST_PYTHON_REQUIREMENT
    assert probe.CHILD_BOOTSTRAP_ORDER == (
        "owner_create",
        "simulation_app_create",
        "full_identity_recompute",
        "runtime_measurement",
    )
    command = probe.build_child_command(
        config_path=probe.DEFAULT_CONFIG,
        run_id="attempt-003",
        owner_path=tmp_path / "owner.json",
        runtime_report_path=tmp_path / "provisional.json",
        run_identity_sha256="a" * 64,
    )
    assert Path(command[0]) == probe.DEFAULT_ISAAC_PYTHON.resolve()


def test_run_identity_pins_inputs_and_observes_launcher_without_embedded_self_hash():
    identity = probe.build_run_identity(probe.DEFAULT_CONFIG)

    assert identity["config"]["sha256"] == probe.EXPECTED_CONFIG_SHA256
    assert identity["asset"]["sha256"] == probe.EXPECTED_ASSET_SHA256
    assert identity["robot"]["sha256"] == probe.EXPECTED_ROBOT_SHA256
    files = identity["implementation"]["files"]
    assert probe.SELF_RELATIVE_PATH in files
    assert files[probe.SELF_RELATIVE_PATH] == probe.sha256_file(probe.__file__)
    assert probe.SELF_RELATIVE_PATH not in probe.PINNED_IMPLEMENTATION_SHA256
    assert set(probe.DIRECT_PROJECT_IMPORT_PATHS).issubset(files)
    assert identity["workspace_drift_seal"] == {
        "authority": "workspace_pre_post_drift_seal_v1",
        "description": "Workspace pre/post-run drift seal; not an external trust root.",
        "external_trust_root": False,
    }
    assert identity["interpreter"] == {
        "requested_path": str(probe.DEFAULT_ISAAC_PYTHON),
        "resolved_path": str(probe.DEFAULT_ISAAC_PYTHON.resolve()),
        "sha256": probe.EXPECTED_ISAAC_PYTHON_SHA256,
    }
    assert identity["usd_composition_closure"]["files"] == (
        probe.PINNED_USD_COMPOSITION_SHA256
    )
    assert identity["runtime_data"]["files"] == probe.PINNED_RUNTIME_DATA_SHA256
    assert probe.resolve_usd_composition_closure(
        [probe.ASSET_PATH, probe.ROBOT_PATH]
    ) == probe.PINNED_USD_COMPOSITION_SHA256
    assert probe.validate_run_identity(identity) == identity

    tampered = copy.deepcopy(identity)
    tampered["implementation"]["files"][probe.SELF_RELATIVE_PATH] = "0" * 64
    with pytest.raises(ValueError, match="trajectory_preflight_run_identity_invalid"):
        probe.validate_run_identity(tampered)


@pytest.mark.parametrize(
    ("kwargs", "shutdown_status"),
    [
        (
            {
                "child_returncode": -signal.SIGKILL,
                "timed_out": True,
                "termination": "SIGKILL",
                "runtime_error": "child_timeout",
            },
            "child_timeout",
        ),
        (
            {
                "child_returncode": 7,
                "runtime_error": "child_exit_nonzero:7",
            },
            "child_exit_nonzero",
        ),
        (
            {
                "runtime_error": "runtime_report_invalid:malformed",
            },
            "evidence_validation_failed",
        ),
        (
            {
                "runtime_error": "runtime_report_missing:/tmp/report.json",
            },
            "evidence_validation_failed",
        ),
    ],
)
def test_finalizer_turns_timeout_nonzero_malformed_and_missing_report_into_runtime_error(
    kwargs, shutdown_status
):
    values = {
        "runtime_evaluation": {"decision": probe.GO_DECISION},
        "pre_run_identity": {"identity_sha256": "a" * 64},
        "post_run_identity": {"identity_sha256": "a" * 64},
        "child_command": ["isaac-python", "probe.py", "--runtime-child"],
        "child_pid": 2468,
        "child_returncode": 0,
        "timed_out": False,
        "termination": None,
        "runtime_error": None,
        "child_reaped": True,
        "process_group_empty": True,
    }
    values.update(kwargs)

    report = probe.finalize_parent_report(**values)

    assert report["decision"] == probe.RUNTIME_ERROR_DECISION
    assert report["lifecycle_status"] == "failed"
    assert report["shutdown_status"] == shutdown_status


def test_finalizer_rejects_identity_drift_and_accepts_clean_go_or_no_go():
    common = {
        "pre_run_identity": {"identity_sha256": "a" * 64},
        "child_command": ["isaac-python", "probe.py", "--runtime-child"],
        "child_pid": 2468,
        "child_returncode": 0,
        "timed_out": False,
        "termination": None,
        "runtime_error": None,
        "child_reaped": True,
        "process_group_empty": True,
    }
    drift = probe.finalize_parent_report(
        runtime_evaluation={"decision": probe.GO_DECISION},
        post_run_identity={"identity_sha256": "b" * 64},
        **common,
    )
    assert drift["decision"] == probe.RUNTIME_ERROR_DECISION
    assert drift["shutdown_status"] == "identity_validation_failed"

    for decision in (probe.GO_DECISION, probe.NO_GO_DECISION):
        clean = probe.finalize_parent_report(
            runtime_evaluation={"decision": decision},
            post_run_identity=copy.deepcopy(common["pre_run_identity"]),
            **common,
        )
        assert clean["decision"] == decision
        assert clean["lifecycle_status"] == "completed"
        assert clean["shutdown_status"] == "child_exit_0"
        assert clean["identity_authority"] == "workspace_pre_post_drift_seal_v1"
        assert clean["external_trust_root"] is False
        assert clean["process_authority"] == {
            "authority": "leader_wait_then_process_group_quiescence_v1",
            "process_group_coverage": True,
            "detached_child_cgroup_coverage": False,
            "limitation": (
                "No dedicated cgroup; detached descendants outside the child process group are not covered."
            ),
        }

    for field in ("child_reaped", "process_group_empty"):
        unsafe = probe.finalize_parent_report(
            runtime_evaluation={"decision": probe.GO_DECISION},
            post_run_identity=copy.deepcopy(common["pre_run_identity"]),
            **{**common, field: False},
        )
        assert unsafe["decision"] == probe.RUNTIME_ERROR_DECISION
        assert unsafe["shutdown_status"] == "process_cleanup_failed"


def test_timeout_cleanup_escalates_process_group_and_reaps(monkeypatch):
    class Process:
        pid = 9876
        returncode = None

        def __init__(self):
            self.wait_calls = 0

        def poll(self):
            return None

        def wait(self, timeout):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(["python"], timeout)
            self.returncode = -signal.SIGKILL
            return self.returncode

    process = Process()
    signals = []
    monkeypatch.setattr(
        probe.os,
        "killpg",
        lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )

    assert probe.terminate_process_group(
        process,
        term_grace_seconds=0.01,
        kill_grace_seconds=0.01,
    ) == "SIGKILL"
    assert signals == [
        (9876, signal.SIGTERM),
        (9876, signal.SIGKILL),
    ]
    assert process.wait_calls == 2


def test_process_group_empty_probe_is_fail_closed(monkeypatch):
    monkeypatch.setattr(
        probe.os,
        "killpg",
        lambda _pid, _signal: (_ for _ in ()).throw(ProcessLookupError()),
    )
    assert probe.process_group_is_empty(1234) is True

    monkeypatch.setattr(probe.os, "killpg", lambda _pid, _signal: None)
    assert probe.process_group_is_empty(1234) is False


def test_parent_postflight_identity_runs_from_finally_after_launch_error(tmp_path, monkeypatch):
    identity = {
        "identity_sha256": "a" * 64,
        "workspace_drift_seal": {
            "authority": "workspace_pre_post_drift_seal_v1",
            "description": "Workspace pre/post-run drift seal; not an external trust root.",
            "external_trust_root": False,
        },
    }
    calls = []

    def build_identity(_config):
        calls.append("identity")
        return copy.deepcopy(identity)

    monkeypatch.setattr(probe, "build_run_identity", build_identity)
    monkeypatch.setattr(
        probe.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("launch failed")),
    )

    out_dir = tmp_path / "attempt"
    assert probe.main(
        [
            "--config",
            str(probe.DEFAULT_CONFIG),
            "--out-dir",
            str(out_dir),
            "--timeout-seconds",
            "1",
        ]
    ) == 2
    assert calls == ["identity", "identity"]
    report = json.loads((out_dir / probe.FINAL_REPORT_BASENAME).read_text())
    assert report["post_run_identity"] == identity
    assert report["shutdown_status"] == "child_launch_error"


def test_fake_clean_child_parent_seals_quiescent_runtime_buffer_end_to_end(
    tmp_path, monkeypatch
):
    identity = {
        "identity_sha256": "a" * 64,
        "workspace_drift_seal": {
            "authority": "workspace_pre_post_drift_seal_v1",
            "description": "Workspace pre/post-run drift seal; not an external trust root.",
            "external_trust_root": False,
        },
    }
    events = []
    identity_calls = 0

    def build_identity(_config):
        nonlocal identity_calls
        identity_calls += 1
        events.append("identity_pre" if identity_calls == 1 else "identity_post")
        return copy.deepcopy(identity)

    class Process:
        pid = 2468
        returncode = None

        def wait(self, timeout):
            events.append("leader_wait")
            self.returncode = 0
            return 0

        def poll(self):
            return self.returncode

    runtime_payload = {"value": None}

    def popen(command, **_kwargs):
        events.append("child_launch")
        run_id = command[command.index("--run-id") + 1]
        owner_path = Path(command[command.index("--owner") + 1])
        runtime_path = Path(command[command.index("--runtime-report") + 1])
        report = _producer_provisional_runtime_report()
        report["runtime_identity"] = {
            "pid": 2468,
            "run_id": run_id,
            "run_identity_sha256": "a" * 64,
        }
        owner_path.write_bytes(
            probe._canonical_json_bytes(
                {
                    "pid": 2468,
                    "run_id": run_id,
                    "run_identity_sha256": "a" * 64,
                },
                indent=2,
            )
        )
        runtime_payload["value"] = probe._canonical_json_bytes(report, indent=2)
        runtime_path.write_bytes(runtime_payload["value"])
        return Process()

    original_loader = probe.load_runtime_report_bytes

    def load_buffer(payload, *, source_name):
        events.append("runtime_buffer_validate")
        return original_loader(payload, source_name=source_name)

    monkeypatch.setattr(probe, "build_run_identity", build_identity)
    monkeypatch.setattr(probe.subprocess, "Popen", popen)
    monkeypatch.setattr(
        probe,
        "process_group_is_empty",
        lambda _pid: events.append("process_group_quiescent") or True,
    )
    monkeypatch.setattr(probe, "load_runtime_report_bytes", load_buffer)

    out_dir = tmp_path / "clean-attempt"
    assert probe.main(
        [
            "--config",
            str(probe.DEFAULT_CONFIG),
            "--out-dir",
            str(out_dir),
            "--timeout-seconds",
            "1",
        ]
    ) == 0
    assert events.index("identity_pre") < events.index("child_launch")
    assert events.index("leader_wait") < events.index("process_group_quiescent")
    assert events.index("process_group_quiescent") < events.index(
        "runtime_buffer_validate"
    )
    assert events.index("runtime_buffer_validate") < events.index("identity_post")

    final = json.loads((out_dir / probe.FINAL_REPORT_BASENAME).read_text())
    artifact = final["artifacts"]["runtime_report"]
    assert artifact["sha256"] == hashlib.sha256(runtime_payload["value"]).hexdigest()
    assert artifact["byte_count"] == len(runtime_payload["value"])
    assert artifact["authority"] == "single_post_quiescence_byte_buffer_v1"
    assert final["decision"] == probe.GO_DECISION


def test_parent_refuses_existing_output_without_modifying_it(tmp_path):
    marker = tmp_path / "marker.txt"
    marker.write_text("existing\n", encoding="utf-8")

    assert probe.main(
        [
            "--config",
            str(probe.DEFAULT_CONFIG),
            "--out-dir",
            str(tmp_path),
            "--timeout-seconds",
            "1",
        ]
    ) == 2
    assert marker.read_text(encoding="utf-8") == "existing\n"
    assert not (tmp_path / probe.FINAL_REPORT_BASENAME).exists()


def _deep_diff(source, candidate, path=()):
    if isinstance(source, dict) and isinstance(candidate, dict):
        differences = {}
        for key in sorted(set(source) | set(candidate), key=str):
            key_path = (*path, str(key))
            if key not in source:
                differences[key_path] = (None, candidate[key])
            elif key not in candidate:
                differences[key_path] = (source[key], None)
            else:
                differences.update(_deep_diff(source[key], candidate[key], key_path))
        return differences
    return {} if source == candidate else {path: (source, candidate)}


def test_preflight_config_is_hash_pinned_clone_with_only_reviewed_fields():
    source = yaml.safe_load(SOURCE_CONFIG.read_text(encoding="utf-8"))
    candidate = yaml.safe_load(probe.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    differences = _deep_diff(source, candidate)
    allowed_exact = {
        ("name",),
        ("online_fluid", "expert_control_profile"),
        ("online_fluid", "grasp_finger_joint_target_m"),
        ("online_fluid", "performance_label"),
    }
    allowed_added = {
        "trajectory_preflight_profile",
        "grasp_target_frame_name",
        "rmpflow_control_frame_name",
        "rmpflow_control_to_grasp_matrix_m",
        "expert_pick_gripper_offset_object_m",
        "expert_pick_target_orientation_wxyz",
        "expert_pick_approach_direction_world",
        "expert_pick_pregrasp_distance_m",
        "expert_pick_insert_distance_m",
        "expert_pick_approach_speed_m_s",
        "expert_pick_close_speed_m_s",
        "expert_pick_settle_duration_s",
        "expert_pick_contact_settle_duration_s",
        "trajectory_preflight_requested_open_target_m",
        "trajectory_preflight_position_threshold_m",
        "trajectory_preflight_orientation_threshold_degrees",
        "trajectory_preflight_calibration_points_m",
        "trajectory_preflight_remote_close_speed_m_s",
        "trajectory_preflight_calibration_settle_duration_s",
        "trajectory_preflight_calibration_body_size_m",
        "trajectory_preflight_calibration_body_translation_tool_m",
        "trajectory_preflight_calibration_body_contact_offset_m",
        "trajectory_preflight_velocity_agreement_tolerance_m_s",
        "trajectory_preflight_numerical_margin_m",
    }
    assert set(differences).issubset(
        allowed_exact | {("online_fluid", name) for name in allowed_added}
    )
    for path in set(differences) - allowed_exact:
        assert differences[path][0] is None

    fluid = candidate["online_fluid"]
    assert candidate["name"] == (
        "Diagnostic_level1_pour_geometry_aware_trajectory_preflight_600hz_step600_layout_v1"
    )
    assert fluid["trajectory_preflight_profile"] == (
        "geometry_aware_trajectory_preflight_v1"
    )
    assert fluid["expert_control_profile"] == "contact_pick_v1"
    assert fluid["expert_pick_target_orientation_wxyz"] == [0.0, 0.0, 1.0, 0.0]
    assert fluid["expert_pick_gripper_offset_object_m"] == [0.0, 0.0, 0.0]
    assert fluid["expert_pick_approach_direction_world"] == [0.0, 0.0, -1.0]
    assert fluid["rmpflow_control_to_grasp_matrix_m"] == [
        [-1.0, 0.0, 0.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, -0.0034, 1.0],
    ]
    assert fluid["expert_pick_pregrasp_distance_m"] == 0.120
    assert fluid["expert_pick_insert_distance_m"] == 0.060
    assert fluid["expert_pick_approach_speed_m_s"] == 0.006
    assert fluid["expert_pick_close_speed_m_s"] == 0.003
    assert fluid["trajectory_preflight_requested_open_target_m"] == 0.040
    assert "trajectory_preflight_open_position_tolerance_m" not in fluid
    assert fluid["trajectory_preflight_position_threshold_m"] == 0.0005
    assert fluid["trajectory_preflight_orientation_threshold_degrees"] == 0.5
    assert fluid["trajectory_preflight_remote_close_speed_m_s"] == 0.003
    assert fluid["trajectory_preflight_calibration_body_size_m"] == [
        0.002,
        0.070,
        0.002,
    ]
    assert fluid["trajectory_preflight_calibration_body_translation_tool_m"] == [
        0.009,
        0.0,
        0.006,
    ]
    assert fluid["expert_pick_settle_duration_s"] == 0.10
    assert fluid["expert_pick_contact_settle_duration_s"] == 0.10
    assert fluid["trajectory_preflight_calibration_settle_duration_s"] == 0.10
    assert probe.sha256_file(probe.DEFAULT_CONFIG) == probe.EXPECTED_CONFIG_SHA256
    assert probe.sha256_file(probe.ASSET_PATH) == probe.EXPECTED_ASSET_SHA256
    assert probe.sha256_file(probe.ROBOT_PATH) == probe.EXPECTED_ROBOT_SHA256
