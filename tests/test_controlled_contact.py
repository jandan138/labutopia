from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from utils.controlled_contact import (
    FullContactReportAccumulator,
    PostcontactSourceMotionAccumulator,
    PostcontactToolMotionAccumulator,
    build_arm_target_token,
    build_finger_target_token,
    build_precontact_continuation_lease,
    evaluate_controlled_contact_report,
)


def _header(
    event_type: str,
    *,
    collider0: str = "/World/source",
    collider1: str = "/World/table",
    contact_offset: int = 0,
    contact_count: int = 0,
    friction_offset: int = 0,
    friction_count: int = 0,
    actor0: str | None = None,
    actor1: str | None = None,
) -> dict:
    return {
        "type": event_type,
        "stage_id": 7,
        "actor0": collider0 if actor0 is None else actor0,
        "actor1": collider1 if actor1 is None else actor1,
        "collider0": collider0,
        "collider1": collider1,
        "proto_index0": 0xFFFFFFFF,
        "proto_index1": 0xFFFFFFFF,
        "contact_data_offset": contact_offset,
        "num_contact_data": contact_count,
        "friction_anchors_offset": friction_offset,
        "num_friction_anchors_data": friction_count,
    }


def _contact(position: float) -> dict:
    return {
        "position": [position, 0.0, 0.0],
        "normal": [1.0, 0.0, 0.0],
        "impulse": [0.0001, 0.0, 0.0],
        "separation": -0.0001,
        "face_index0": 0,
        "face_index1": 0,
        "material0": "/World/material0",
        "material1": "/World/material1",
    }


def _friction(position: float) -> dict:
    return {
        "position": [position, 0.0, 0.0],
        "impulse": [0.0, 0.00001, 0.0],
    }


def _arm_token(*, z: float = 0.2, quaternion_sign: float = 1.0) -> dict:
    return build_arm_target_token(
        tool_position_stage_units=np.asarray([0.1, -0.1, z]),
        tool_orientation_wxyz=np.asarray(
            [quaternion_sign, 0.0, 0.0, 0.0]
        ),
        control_position_stage_units=np.asarray([0.1, -0.1, z - 0.0034]),
        control_orientation_wxyz=np.asarray(
            [quaternion_sign, 0.0, 0.0, 0.0]
        ),
        tool_frame="tool_center",
        control_frame="right_gripper",
        stage_units_m=1.0,
    )


def _applied_receipt(token: dict) -> dict:
    return {
        "authority": "controlled_action_applied_receipt_v1",
        "phase": "INSERT",
        "semantic_action_kind": "ARM_INSERT",
        "channel": "arm",
        "action_sha256": "a" * 64,
        "target_token": deepcopy(token),
        "target_token_sha256": token["sha256"],
        "control_index": 3,
        "action_index": 3,
        "apply_index": 3,
        "interval_index": 3,
        "applied": True,
    }


def test_arm_target_token_is_canonical_and_binds_raw_float64_bytes():
    positive = _arm_token(quaternion_sign=1.0)
    negative = _arm_token(quaternion_sign=-1.0)

    assert positive == negative
    assert positive["authority"] == "controlled_target_token_v1"
    assert positive["kind"] == "arm_pose"
    assert positive["arrays"]["tool_position_stage_units"]["dtype"] == "<f8"
    assert positive["arrays"]["tool_position_stage_units"]["shape"] == [3]
    assert len(positive["arrays"]["tool_position_stage_units"]["bytes_hex"]) == 48
    assert len(positive["sha256"]) == 64

    changed = _arm_token(z=0.20000000000000004)
    assert changed["sha256"] != positive["sha256"]


def test_target_tokens_reject_nonfinite_values_and_bind_finger_indices():
    with pytest.raises(ValueError, match="controlled_target_array_invalid"):
        _arm_token(z=float("nan"))

    token = build_finger_target_token(
        joint_indices=(7, 8),
        joint_targets=np.asarray([0.037, 0.037], dtype=np.float32),
    )
    assert token["kind"] == "finger_joints"
    assert token["joint_indices"] == [7, 8]
    assert token["arrays"]["joint_targets"]["dtype"] == "<f8"


def test_precontact_continuation_lease_binds_receipt_target_and_slots():
    token = _arm_token()
    receipt = _applied_receipt(token)

    lease = build_precontact_continuation_lease(
        applied_receipt=receipt,
        contact_physics_index=120,
        contact_substep_slot=7,
        substeps_per_interval=20,
        contact_evidence_sha256="d" * 64,
    )

    assert lease["authority"] == "precontact_continuation_lease_v1"
    assert lease["command_phase"] == "INSERT"
    assert lease["effective_phase"] == "PRECONTACT_SETTLE"
    assert lease["contact_substep_slot"] == 7
    assert lease["remaining_substep_slots"] == list(range(8, 21))
    assert lease["target_token_sha256"] == token["sha256"]
    assert lease["articulation_mutation_count"] == 0

    wrong_phase = _applied_receipt(token)
    wrong_phase["phase"] = "CLOSE"
    wrong_phase["semantic_action_kind"] = "GRIPPER_CLOSE"
    with pytest.raises(ValueError, match="precontact_receipt_phase_invalid"):
        build_precontact_continuation_lease(
            applied_receipt=wrong_phase,
            contact_physics_index=120,
            contact_substep_slot=7,
            substeps_per_interval=20,
            contact_evidence_sha256="d" * 64,
        )

    corrupt = _applied_receipt(token)
    corrupt["target_token_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="precontact_receipt_target_mismatch"):
        build_precontact_continuation_lease(
            applied_receipt=corrupt,
            contact_physics_index=120,
            contact_substep_slot=7,
            substeps_per_interval=20,
            contact_evidence_sha256="d" * 64,
        )


def test_full_contact_report_lifecycle_found_persist_lost_and_empty():
    reports = FullContactReportAccumulator(expected_stage_id=7)

    found = reports.consume(
        physics_index=10,
        headers=[_header("FOUND", contact_count=1)],
        contact_data=[_contact(0.0)],
        friction_anchors=[],
    )
    assert found["event_sequences"] == ["FOUND"]
    assert found["occurrence_count"] == 1
    assert found["current_pair_count"] == 1
    assert found["occurrences"][0]["contact_data"] == [_contact(0.0)]

    persisted = reports.consume(
        physics_index=11,
        headers=[_header("PERSIST", contact_count=1)],
        contact_data=[_contact(0.1)],
        friction_anchors=[],
    )
    assert persisted["event_sequences"] == ["PERSIST"]
    assert persisted["current_pair_count"] == 1

    lost = reports.consume(
        physics_index=12,
        headers=[_header("LOST")],
        contact_data=[],
        friction_anchors=[],
    )
    assert lost["occurrence_count"] == 0
    assert lost["current_pair_count"] == 0

    empty = reports.consume(
        physics_index=13,
        headers=[],
        contact_data=[],
        friction_anchors=[],
    )
    assert empty["header_count"] == 0
    assert empty["range_partition_valid"] is True


def test_full_contact_report_aggregates_disjoint_fragments_once():
    reports = FullContactReportAccumulator(expected_stage_id=7)
    value = reports.consume(
        physics_index=0,
        headers=[
            _header(
                "FOUND",
                contact_offset=0,
                contact_count=1,
                friction_offset=0,
                friction_count=1,
            ),
            _header(
                "FOUND",
                contact_offset=1,
                contact_count=1,
                friction_offset=1,
                friction_count=1,
            ),
        ],
        contact_data=[_contact(0.0), _contact(0.1)],
        friction_anchors=[_friction(0.0), _friction(0.1)],
    )

    assert value["header_count"] == 2
    assert value["occurrence_count"] == 1
    assert value["event_sequences"] == ["FOUND"]
    assert len(value["occurrences"][0]["contact_data"]) == 2
    assert len(value["occurrences"][0]["friction_anchors"]) == 2


def test_full_contact_report_rejects_bad_ranges_and_missing_active_pair():
    reports = FullContactReportAccumulator(expected_stage_id=7)
    with pytest.raises(ValueError, match="contact_report_contact_range_invalid"):
        reports.consume(
            physics_index=0,
            headers=[
                _header("FOUND", contact_offset=0, contact_count=1),
                _header("FOUND", contact_offset=0, contact_count=1),
            ],
            contact_data=[_contact(0.0)],
            friction_anchors=[],
        )

    reports = FullContactReportAccumulator(expected_stage_id=7)
    reports.consume(
        physics_index=0,
        headers=[_header("FOUND", contact_count=1)],
        contact_data=[_contact(0.0)],
        friction_anchors=[],
    )
    with pytest.raises(ValueError, match="contact_report_active_pair_missing"):
        reports.consume(
            physics_index=1,
            headers=[],
            contact_data=[],
            friction_anchors=[],
        )


def test_full_contact_report_bootstraps_only_provisional_persist_and_transient():
    pair = ("/World/source", "/World/table")
    reports = FullContactReportAccumulator(
        expected_stage_id=7,
        provisional_background_pairs=(pair,),
    )
    bootstrap = reports.consume(
        physics_index=-2,
        headers=[_header("PERSIST", contact_count=1)],
        contact_data=[_contact(0.0)],
        friction_anchors=[],
        allow_provisional_persist_bootstrap=True,
    )
    assert bootstrap["bootstrap_pair_count"] == 1
    assert bootstrap["current_pair_count"] == 1

    reports.consume(
        physics_index=-1,
        headers=[_header("LOST")],
        contact_data=[],
        friction_anchors=[],
    )
    transient = reports.consume(
        physics_index=0,
        headers=[
            _header("FOUND", contact_offset=0, contact_count=1),
            _header("LOST", contact_offset=1, contact_count=0),
        ],
        contact_data=[_contact(0.0)],
        friction_anchors=[],
    )
    assert transient["event_sequences"] == ["FOUND,LOST"]
    assert transient["occurrences"][0]["transient"] is True
    assert transient["current_pair_count"] == 0

    invalid = FullContactReportAccumulator(expected_stage_id=7)
    with pytest.raises(ValueError, match="contact_report_lifecycle_invalid"):
        invalid.consume(
            physics_index=0,
            headers=[_header("PERSIST", contact_count=1)],
            contact_data=[_contact(0.0)],
            friction_anchors=[],
        )


def _rigid_state(*, linear=(0.0, 0.0, 0.0)) -> dict:
    return {
        "com_position_m": [0.0, 0.0, 0.0],
        "orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
        "linear_velocity_m_s": list(linear),
        "angular_velocity_rad_s": [0.0, 0.0, 0.0],
    }


def _intended_immediate_report(*, finger_speed=0.0, friction_impulse=0.0):
    accumulator = FullContactReportAccumulator(expected_stage_id=7)
    contact = _contact(0.07)
    contact["normal"] = [-1.0, 0.0, 0.0]
    contact["impulse"] = [-0.0002, 0.0, 0.0]
    return (
        accumulator.consume(
            physics_index=20,
            headers=[
                _header(
                    "FOUND",
                    actor0="/World/Franka/panda_leftfinger",
                    actor1="/World/beaker2",
                    collider0="/World/Franka/panda_leftfinger/collision",
                    collider1="/World/beaker2/mesh",
                    contact_count=1,
                    friction_count=1 if friction_impulse else 0,
                )
            ],
            contact_data=[contact],
            friction_anchors=(
                [
                    {
                        "position": [0.07, 0.0, 0.0],
                        "impulse": [0.0, friction_impulse, 0.0],
                    }
                ]
                if friction_impulse
                else []
            ),
        ),
        {
            "/World/Franka/panda_leftfinger": _rigid_state(
                linear=(finger_speed, 0.0, 0.0)
            ),
            "/World/beaker2": _rigid_state(),
        },
    )


def _classify_immediate(
    report,
    pre_states,
    *,
    phase="INSERT",
    maximum_source_linear_speed_m_s=None,
    maximum_source_angular_speed_rad_s=None,
    physics_dt=None,
    post_states=None,
):
    return evaluate_controlled_contact_report(
        report=report,
        phase=phase,
        source_body_path="/World/beaker2",
        source_external_collider_paths=("/World/beaker2/mesh",),
        finger_pairs={
            "left": {
                "body_path": "/World/Franka/panda_leftfinger",
                "collider_paths": (
                    "/World/Franka/panda_leftfinger/collision",
                ),
            },
            "right": {
                "body_path": "/World/Franka/panda_rightfinger",
                "collider_paths": (
                    "/World/Franka/panda_rightfinger/collision",
                ),
            },
        },
        robot_body_paths=(
            "/World/Franka/panda_leftfinger",
            "/World/Franka/panda_rightfinger",
            "/World/Franka/panda_hand",
        ),
        known_body_paths=(
            "/World/Franka/panda_leftfinger",
            "/World/Franka/panda_rightfinger",
            "/World/Franka/panda_hand",
            "/World/beaker2",
            "/World/table/surface/mesh",
        ),
        known_collider_paths=(
            "/World/Franka/panda_leftfinger/collision",
            "/World/Franka/panda_rightfinger/collision",
            "/World/beaker2/mesh",
            "/World/table/surface/mesh",
        ),
        baseline_collider_pairs=(
            ("/World/beaker2/mesh", "/World/table/surface/mesh"),
        ),
        source_center_world_m=(0.0, 0.0, 0.0),
        source_axis_world=(0.0, 0.0, 1.0),
        grasp_height_band_m=(-0.02, 0.02),
        pre_body_states=pre_states,
        post_body_states=(
            {path: deepcopy(state) for path, state in pre_states.items()}
            if post_states is None
            else post_states
        ),
        normal_convention="actor0_to_actor1",
        minimum_inward_normal_cosine=0.8,
        maximum_penetration_m=0.001,
        maximum_precontact_relative_speed_m_s=0.008,
        maximum_close_relative_speed_m_s=0.002,
        maximum_step_normal_impulse_n_s=0.001,
        maximum_step_total_impulse_n_s=0.001,
        episode_normal_impulse_before_n_s=0.0,
        episode_total_impulse_before_n_s=0.0,
        maximum_episode_normal_impulse_n_s=1.5,
        maximum_episode_total_impulse_n_s=1.5,
        maximum_source_linear_speed_m_s=maximum_source_linear_speed_m_s,
        maximum_source_angular_speed_rad_s=maximum_source_angular_speed_rad_s,
        physics_dt=physics_dt,
    )


def test_immediate_contact_classifier_uses_all_points_twists_and_friction():
    report, states = _intended_immediate_report()
    passed = _classify_immediate(report, states)
    assert passed["terminal_kind"] is None
    assert passed["class_counts"] == {"INTENDED_PRECONTACT": 1}
    assert passed["precontact_latch"]["sides"] == ["left"]
    point = passed["records"][0]["manifold_points"][0]
    assert point["inward_normal_cosine"] == pytest.approx(1.0)
    assert point["relative_speed_m_s"] == pytest.approx(0.0)
    assert passed["step_total_impulse_n_s"] == pytest.approx(0.0002)

    fast_report, fast_states = _intended_immediate_report(finger_speed=0.009)
    fast = _classify_immediate(fast_report, fast_states)
    assert fast["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"
    assert "relative_speed" in fast["records"][0]["gate_failures"]

    friction_report, friction_states = _intended_immediate_report(
        friction_impulse=0.0011
    )
    friction = _classify_immediate(friction_report, friction_states)
    assert friction["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"
    assert friction["step_total_impulse_n_s"] == pytest.approx(0.0013)


def test_precontact_settle_uses_settled_speed_and_does_not_relatch():
    report, states = _intended_immediate_report()
    settled = _classify_immediate(
        report,
        states,
        phase="PRECONTACT_SETTLE",
    )
    assert settled["terminal_kind"] is None
    assert settled["class_counts"] == {"INTENDED_PRECONTACT": 1}
    assert settled["precontact_latch"] is None

    fast_report, fast_states = _intended_immediate_report(finger_speed=0.003)
    fast = _classify_immediate(
        fast_report,
        fast_states,
        phase="PRECONTACT_SETTLE",
    )
    assert fast["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"
    assert "relative_speed" in fast["records"][0]["gate_failures"]


def test_pre_roll_finger_source_contact_is_prohibited():
    report, states = _intended_immediate_report()

    result = _classify_immediate(report, states, phase="PRE_ROLL")

    assert result["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"
    assert result["class_counts"] == {"PROHIBITED_CONTACT": 1}
    assert result["precontact_latch"] is None


def test_source_direct_speed_limits_apply_even_without_contact():
    report = {
        "physics_index": 20,
        "occurrences": [],
    }
    states = {
        "/World/beaker2": _rigid_state(linear=(0.00201, 0.0, 0.0)),
    }

    result = _classify_immediate(
        report,
        states,
        maximum_source_linear_speed_m_s=0.002,
        maximum_source_angular_speed_rad_s=np.radians(1.0),
    )

    assert result["terminal_kind"] == "PHYSICAL_MOTION_FAILURE"
    assert result["precontact_latch"] is None
    assert result["source_linear_speed_m_s"] == pytest.approx(0.00201)


def test_source_speed_uses_com_and_orientation_finite_difference():
    report = {"physics_index": 20, "occurrences": []}
    pre = {"/World/beaker2": _rigid_state()}
    post = {"/World/beaker2": _rigid_state()}
    post["/World/beaker2"]["com_position_m"] = [0.000004, 0.0, 0.0]

    result = _classify_immediate(
        report,
        pre,
        post_states=post,
        maximum_source_linear_speed_m_s=0.002,
        maximum_source_angular_speed_rad_s=np.radians(1.0),
        physics_dt=1.0 / 600.0,
    )

    assert result["source_linear_speed_m_s"] == pytest.approx(0.0024)
    assert result["terminal_kind"] == "PHYSICAL_MOTION_FAILURE"


def test_postcontact_source_motion_accumulates_non_cancelling_path_and_angle():
    accumulator = PostcontactSourceMotionAccumulator(
        maximum_path_m=0.005,
        maximum_angular_variation_degrees=2.5,
    )

    def state(x, degrees):
        radians = np.radians(degrees) / 2.0
        return {
            "com_position_m": [x, 0.0, 0.0],
            "orientation_wxyz": [np.cos(radians), 0.0, 0.0, np.sin(radians)],
        }

    before_contact = accumulator.update(
        pre_source_state=state(0.0, 0.0),
        post_source_state=state(0.004, 1.0),
        intended_contact_occurring=False,
    )
    assert before_contact["active"] is False
    assert before_contact["path_m"] == 0.0

    first = accumulator.update(
        pre_source_state=state(0.004, 1.0),
        post_source_state=state(0.005, 2.0),
        intended_contact_occurring=True,
    )
    assert first["active"] is True
    assert first["path_m"] == pytest.approx(0.001)
    assert first["angular_variation_degrees"] == pytest.approx(1.0)
    assert first["valid"] is True

    exceeded = accumulator.update(
        pre_source_state=state(0.005, 2.0),
        post_source_state=state(-0.0001, 3.0),
        intended_contact_occurring=False,
    )
    assert exceeded["path_m"] == pytest.approx(0.0061)
    assert exceeded["angular_variation_degrees"] == pytest.approx(2.0)
    assert exceeded["valid"] is False


def test_postcontact_tool_motion_measures_contact_step_coast_and_settled_speed():
    accumulator = PostcontactToolMotionAccumulator(
        physics_dt=1.0 / 600.0,
        approach_direction_world=(0.0, 0.0, -1.0),
        maximum_downward_coast_m=0.001,
        maximum_contact_step_speed_m_s=0.008,
        maximum_settled_speed_m_s=0.002,
    )

    def state(z, speed):
        return {
            "position_m": [0.0, 0.0, z],
            "linear_velocity_m_s": [0.0, 0.0, -speed],
        }

    first = accumulator.update(
        pre_tool_state=state(1.0, 0.006),
        post_tool_state=state(0.99999, 0.006),
        intended_contact_occurring=True,
    )
    assert first["maximum_downward_coast_m"] == pytest.approx(0.00001)
    assert first["maximum_speed_m_s"] == pytest.approx(0.006)
    assert first["valid"] is True

    too_fast = accumulator.update(
        pre_tool_state=state(0.99999, 0.00201),
        post_tool_state=state(0.99999, 0.00201),
        intended_contact_occurring=False,
    )
    assert too_fast["valid"] is False
    assert too_fast["speed_valid"] is False
