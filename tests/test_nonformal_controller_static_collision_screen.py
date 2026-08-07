from __future__ import annotations

import ast
from pathlib import Path

import pytest

from utils import nonformal_controller_static_collision_screen as screen


REPO_ROOT = Path(__file__).resolve().parents[1]
ARM = "/World/Franka/panda_link7/geometry/panda_link7"
LEFT = "/World/Franka/panda_leftfinger/geometry/panda_leftfinger"
RIGHT = "/World/Franka/panda_rightfinger/geometry/panda_rightfinger"
MESH = "/World/beaker2/mesh"
WRAPPER = "/World/beaker2/FluidSafeWrapperCanonical/Wall_r0_00"
TABLE = "/World/table/surface/mesh"


def _scope() -> dict:
    return {
        "blocking_pairs": [
            sorted([ARM, MESH]),
            sorted([ARM, WRAPPER]),
            sorted([LEFT, TABLE]),
            sorted([RIGHT, TABLE]),
        ],
        "allowed_source_shell_pairs": [
            sorted([LEFT, MESH]),
            sorted([RIGHT, MESH]),
        ],
    }


def _result(pair: list[str], classification: str, status: str, lower: float) -> dict:
    return {
        "pair": pair,
        "classification": classification,
        "status": status,
        "lower_bound_m": lower,
    }


def _record(index: int, event: int, *, early_finger_overlap: bool = False) -> dict:
    results = [
        _result(pair, "BLOCKING", "CLEAR", 0.01)
        for pair in _scope()["blocking_pairs"]
    ]
    allowed_status = "POTENTIAL_OVERLAP_OR_MARGIN" if early_finger_overlap else "CLEAR"
    results.extend(
        _result(pair, "ALLOWED_SOURCE_SHELL_FINGER", allowed_status, -0.001)
        for pair in _scope()["allowed_source_shell_pairs"]
    )
    return {
        "sample_index": index,
        "controller_event": event,
        "joint_positions": [0.01 * index] * 9,
        "action_sha256": "a" * 64,
        "pair_results": results,
    }


def _semantics_capture(
    *,
    event0_positions: list[float] | None = None,
    event0_velocities: list[float] | None = None,
    event0_efforts: list[float] | None = None,
) -> dict:
    positions = [0.1] * 7 if event0_positions is None else event0_positions
    return {
        "schema_version": 1,
        "authority": "native_pick_action_semantics_v1",
        "baseline": {
            "joint_positions": [0.0] * 9,
            "joint_velocities": [0.0] * 9,
            "joint_lower_limits": [-3.0] * 9,
            "joint_upper_limits": [3.0] * 9,
            "dof_names": [f"joint_{index}" for index in range(9)],
            "stage_units_in_meters": 1.0,
            "expected_stage_units_in_meters": 1.0,
        },
        "post_audit": {
            "joint_positions": [0.0] * 9,
            "joint_velocities": [0.0] * 9,
        },
        "target": {
            "source_center_stage": [1.0, 2.0, 3.0],
            "source_size_stage": [0.1, 0.1, 0.2],
            "approach_direction": [-1.0, 0.0, 0.0],
            "event0_target_position_stage": [0.95, 2.0, 3.25],
            "event0_target_orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
            "pre_offset_x_m": 0.05,
            "pre_offset_z_m": 0.05,
            "after_offset_z_m": 0.5,
            "pick_z_offset_m": 0.0139,
            "pick_x_offset_m": 0.0023,
            "rmp_end_effector_frame_name": "right_gripper",
            "pick_progress_frame_name": "tool_center",
            "rmp_forward_call_count": 1,
        },
        "rmp": {
            "physics_dt_s": 1.0 / 60.0,
            "active_joint_names": [f"joint_{index}" for index in range(7)],
            "active_joint_indices": list(range(7)),
            "policy_config": {
                "end_effector_frame_name": "right_gripper",
                "maximum_substep_size": 0.00334,
                "ignore_robot_state_updates": False,
            },
            "policy_file_hashes": {
                "robot_description_path": {
                    "path": "/formal/robot_descriptor.yaml",
                    "sha256": "a" * 64,
                },
                "urdf_path": {"path": "/formal/franka.urdf", "sha256": "b" * 64},
                "rmpflow_config_path": {
                    "path": "/formal/rmpflow.yaml",
                    "sha256": "c" * 64,
                },
            },
        },
        "frame_observations": {
            "robot_base_position_world": [0.0, 0.0, 0.0],
            "robot_base_orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
            "rmp_policy_end_effector_position": [0.0, 0.0, 0.0],
            "rmp_policy_end_effector_orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
            "tool_center_position_world": [0.0, 0.0, 0.0],
        },
        "source_world_matrix_row_major": [
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
        ],
        "source_world_matrix_after_row_major": [
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
        ],
        "opening": {
            "event_before": 0,
            "event_after": 0,
            "last_emitted_event": None,
            "raw_action": {
                "joint_positions": [None] * 7 + [0.04, 0.04],
                "joint_velocities": None,
                "joint_efforts": None,
                "joint_indices": None,
            },
        },
        "event0": {
            "event_before": 0,
            "event_after": 0,
            "last_emitted_event": 0,
            "raw_action": {
                "joint_positions": positions,
                "joint_velocities": event0_velocities,
                "joint_efforts": event0_efforts,
                "joint_indices": list(range(7)),
            },
        },
        "timeline_before": {
            "world_index": 2,
            "timeline_time_s": 1.0 / 60.0,
            "is_playing": False,
            "is_stopped": False,
        },
        "timeline_after": {
            "world_index": 2,
            "timeline_time_s": 1.0 / 60.0,
            "is_playing": False,
            "is_stopped": False,
        },
    }


def _qdot_counterfactual(capture: dict, *, zero_positions: list[float]) -> dict:
    active_positions = capture["baseline"]["joint_positions"][:7]
    active_velocities = capture["baseline"]["joint_velocities"][:7]
    raw_action = capture["event0"]["raw_action"]
    return {
        "schema_version": 1,
        "authority": "rmp_qdot_counterfactual_v1",
        "control_dt_s": 1.0 / 60.0,
        "active_joint_positions": active_positions,
        "active_joint_velocities": active_velocities,
        "watched_joint_names": [],
        "watched_joint_positions": [],
        "watched_joint_velocities": [],
        "actual_qdot_branch": {
            "input_joint_velocities": active_velocities,
            "position_targets": raw_action["joint_positions"],
            "velocity_targets": raw_action["joint_velocities"],
        },
        "zero_qdot_branch": {
            "input_joint_velocities": [0.0] * 7,
            "position_targets": zero_positions,
            "velocity_targets": [0.0] * 7,
        },
    }


def test_native_pick_semantics_prioritizes_raw_target_limit_violations():
    capture = _semantics_capture(
        event0_positions=[0.1, 0.1, 0.1, -4.0, 0.1, 4.0, 0.1],
        event0_velocities=[0.0] * 7,
    )

    evaluation = screen.evaluate_native_pick_semantics(capture)

    assert evaluation["decision"] == "RAW_NATIVE_POSITION_TARGET_OUT_OF_LIMIT"
    assert evaluation["static_projection_authorized"] is False
    assert evaluation["position_limit_violations"] == [
        {"index": 3, "target": -4.0, "lower": -3.0, "upper": 3.0},
        {"index": 5, "target": 4.0, "lower": -3.0, "upper": 3.0},
    ]


def test_qdot_counterfactual_identifies_a_sufficient_limit_contributor():
    capture = _semantics_capture(
        event0_positions=[0.1, 0.1, 0.1, -4.0, 0.1, 4.0, 0.1],
        event0_velocities=[200.0] * 7,
    )
    capture["baseline"]["joint_velocities"][:7] = [1.0] * 7
    capture["post_audit"]["joint_velocities"][:7] = [1.0] * 7
    replay = _qdot_counterfactual(capture, zero_positions=[0.1] * 7)
    replay["actual_qdot_branch"]["velocity_targets"][0] += 2.0e-5

    evaluation = screen.evaluate_rmp_qdot_counterfactual(capture, replay)

    assert evaluation["decision"] == "QDOT_CAUSAL_LIMIT_CONTRIBUTOR"
    assert evaluation["replay_equivalent"] is True
    assert evaluation["zero_qdot_position_limit_violations"] == []


def test_native_pick_semantics_records_velocity_without_treating_it_as_geometry():
    with_velocity = screen.evaluate_native_pick_semantics(
        _semantics_capture(event0_velocities=[0.0] * 7)
    )
    with_effort = screen.evaluate_native_pick_semantics(
        _semantics_capture(event0_efforts=[0.0] * 7)
    )

    assert with_velocity["decision"] == "STATIC_PROJECTION_ELIGIBLE"
    assert with_velocity["static_projection_authorized"] is True
    assert with_velocity["static_projection_channel_treatment"] == {
        "joint_positions": "static_geometry_target",
        "joint_velocities": "recorded_not_applied",
        "joint_efforts": "absent",
    }
    assert with_effort["decision"] == "DIRECT_STATIC_PROJECTION_UNSUPPORTED"
    assert with_effort["static_projection_authorized"] is False


def test_native_pick_semantics_tolerates_float_rounding_at_open_finger_limit():
    capture = _semantics_capture()
    capture["baseline"]["joint_upper_limits"][7:] = [0.03999999910593033] * 2

    evaluation = screen.evaluate_native_pick_semantics(capture)

    assert evaluation["decision"] == "STATIC_PROJECTION_ELIGIBLE"


def test_native_pick_semantics_rejects_mismatched_native_joint_mapping():
    capture = _semantics_capture()
    capture["event0"]["raw_action"]["joint_indices"] = [1, 2, 3, 4, 5, 6, 7]

    evaluation = screen.evaluate_native_pick_semantics(capture)

    assert evaluation == {
        "decision": "NATIVE_TARGET_CONTRACT_INVALID",
        "static_projection_authorized": False,
        "validation_error": "native_pick_semantics_mapping_invalid",
    }


def test_resolve_joint_configuration_completes_partial_controller_actions():
    current = [0.0] * 9
    action = {
        "joint_positions": [0.1] * 7,
        "joint_indices": list(range(7)),
        "joint_velocities": None,
        "joint_efforts": None,
    }

    resolved = screen.resolve_joint_configuration(current, action)

    assert resolved == {
        "joint_positions": [0.1] * 7 + [0.0, 0.0],
        "changed_joint_indices": list(range(7)),
        "is_hold": False,
    }


def test_resolve_joint_configuration_rejects_nonfinite_or_ambiguous_actions():
    with pytest.raises(ValueError, match="joint_action_invalid"):
        screen.resolve_joint_configuration(
            [0.0] * 9,
            {
                "joint_positions": [float("nan")] * 7,
                "joint_indices": list(range(7)),
                "joint_velocities": None,
                "joint_efforts": None,
            },
        )
    with pytest.raises(ValueError, match="joint_action_invalid"):
        screen.resolve_joint_configuration(
            [0.0] * 9,
            {
                "joint_positions": [0.1] * 7,
                "joint_indices": None,
                "joint_velocities": None,
                "joint_efforts": None,
            },
        )


def test_complete_trace_selects_one_candidate_only_after_first_close():
    trace = [_record(0, -1), _record(1, 0), _record(2, 4, early_finger_overlap=True)]

    evaluation = screen.evaluate_configuration_trace(_scope(), trace)
    decision = screen.select_candidate(
        [{"candidate_id": "v7-native", **evaluation}]
    )

    assert evaluation["candidate_passed"] is True
    assert evaluation["forbidden_pair_result_count"] == 0
    assert evaluation["early_allowed_pair_result_count"] == 0
    assert decision == {
        "decision": "SCREEN_SELECTED_DIAGNOSTIC_ONLY",
        "selected_candidate_id": "v7-native",
        "passing_candidate_ids": ["v7-native"],
    }


def test_trace_rejects_finger_mesh_overlap_before_close():
    trace = [_record(0, -1), _record(1, 3, early_finger_overlap=True), _record(2, 4)]

    evaluation = screen.evaluate_configuration_trace(_scope(), trace)

    assert evaluation["candidate_passed"] is False
    assert evaluation["early_allowed_pair_result_count"] == 2


def test_trace_rejects_missing_blocking_pair_or_lift_event():
    missing_pair = _record(0, 4)
    missing_pair["pair_results"].pop(0)
    with pytest.raises(ValueError, match="pair_result_coverage_invalid"):
        screen.evaluate_configuration_trace(_scope(), [missing_pair])

    with pytest.raises(ValueError, match="controller_event_invalid"):
        screen.evaluate_configuration_trace(_scope(), [_record(0, 5)])


def test_trace_requires_first_close_as_its_terminal_configuration():
    with pytest.raises(ValueError, match="controller_event_invalid"):
        screen.evaluate_configuration_trace(_scope(), [_record(0, -1), _record(1, 3)])


def test_candidate_selection_never_selects_zero_or_multiple_passes():
    failed = {
        "candidate_id": "failed",
        "candidate_passed": False,
        "forbidden_pair_result_count": 1,
        "early_allowed_pair_result_count": 0,
        "configuration_count": 1,
        "required_pair_count": 6,
        "screened_pair_result_count": 6,
    }
    passed = {**failed, "candidate_id": "passed", "candidate_passed": True, "forbidden_pair_result_count": 0}

    assert screen.select_candidate([failed])["decision"] == "SCREEN_NO_CANDIDATE"
    assert screen.select_candidate([passed, {**passed, "candidate_id": "other"}]) == {
        "decision": "SCREEN_AMBIGUOUS_CANDIDATES",
        "selected_candidate_id": None,
        "passing_candidate_ids": ["other", "passed"],
    }


def test_screen_module_is_ascii_and_has_no_simulator_imports():
    source_path = Path(screen.__file__)
    source = source_path.read_bytes()
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )

    assert source.isascii()
    assert not any(
        name == forbidden or name.startswith(f"{forbidden}.")
        for name in imports
        for forbidden in ("isaacsim", "omni", "pxr")
    )


def test_controller_semantics_audit_cannot_actuate_or_advance_physics():
    runtime_path = (
        REPO_ROOT
        / "tools/labutopia_fluid/nonformal_controller_static_collision_screen_runtime.py"
    )
    tree = ast.parse(runtime_path.read_text(encoding="utf-8"))
    audit = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_controller_semantics_audit"
    )
    counterfactual = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_rmp_qdot_counterfactual"
    )
    called_attributes = {
        node.func.attr
        for function in (audit, counterfactual)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not {
        "step",
        "apply_action",
        "set_joint_positions",
        "update_articulations_kinematic",
        "set_world_pose",
    }.intersection(called_attributes)
