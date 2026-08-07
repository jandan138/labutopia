from __future__ import annotations

import ast
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as native
from tools.labutopia_fluid import run_nonformal_controller_static_collision_screen as runner
from tools.labutopia_fluid import nonformal_controller_static_collision_screen_runtime as runtime
from utils import nonformal_controller_static_collision_screen as screen


REPO_ROOT = Path(__file__).resolve().parents[1]
V7_CONFIG = REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v7.yaml"


def test_static_screen_defaults_to_the_pinned_v7_config(tmp_path):
    args = runner.parse_args(["--out-dir", str(tmp_path / "screen")])

    assert args.config == V7_CONFIG.resolve()
    assert args.timeout_seconds == pytest.approx(900.0)
    assert args.child is False
    assert args.child_report_path == args.out_dir / "child_report.json"
    assert args.runtime_receipt_path == args.out_dir / "runtime_receipt.json"


def test_parent_manifest_binds_the_final_report_hash(tmp_path):
    report_path = tmp_path / "report.json"
    manifest_path = tmp_path / "run_manifest.json"
    report = {"decision": "SCREEN_NO_CANDIDATE"}
    manifest = {"manifest_type": "test"}
    written = {}

    def write_manifest(path, payload):
        written["payload"] = dict(payload)
        runner._write_create_only(path, payload)

    runner._write_bound_report_and_manifest(
        report_path=report_path,
        report=report,
        manifest_path=manifest_path,
        manifest=manifest,
        manifest_writer=write_manifest,
    )

    assert written["payload"]["report_sha256"] == runner.sha256_file(report_path)
    assert runner._read_canonical_line(manifest_path) == written["payload"]


def test_static_screen_contract_binds_v7_pick_treatment_and_assets():
    frozen = native.freeze_diagnostic_config(V7_CONFIG)

    contract = runner.build_static_screen_contract(frozen)

    assert contract["v7_config_sha256"] == frozen["sha256"]
    assert contract["local_scene_sha256"] == frozen["local_scene"]["sha256"]
    assert contract["local_franka_sha256"] == frozen["local_franka"]["sha256"]
    assert contract["candidate_ids"] == ["v7-native-pick-prefix-to-first-close"]
    assert contract["g0_or_gate_authorized"] is False
    assert contract["post_reset_physics_steps_allowed"] == 0
    assert contract["native_pick_treatment"] == frozen["config"]["diagnostic"][
        "g0_native_pick_treatment"
    ]
    assert contract["native_pick_forward_parameters"] == {
        "pre_offset_x": 0.05,
        "pre_offset_z": 0.05,
        "after_offset_z": 0.5,
    }


def test_static_screen_source_closure_binds_runtime_and_pure_contract():
    frozen = native.freeze_diagnostic_config(V7_CONFIG)
    paths = set(runner.source_paths(frozen))

    assert Path(runner.__file__).resolve() in paths
    assert runner.RUNTIME_IMPLEMENTATION_MODULE in paths
    assert runner.SCREEN_CONTRACT_MODULE in paths
    assert REPO_ROOT / "controllers/atomic_actions/pick_controller.py" in paths
    assert REPO_ROOT / "robots/franka/rmpflow_controller.py" in paths


def test_static_screen_parent_has_no_top_level_simulator_imports():
    source = Path(runner.__file__).read_bytes()
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


def test_static_runtime_cannot_step_or_apply_controller_actions():
    runtime_path = (
        REPO_ROOT
        / "tools/labutopia_fluid/nonformal_controller_static_collision_screen_runtime.py"
    )
    source = runtime_path.read_bytes()
    tree = ast.parse(source)
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert source.isascii()
    assert "step" not in called_attributes
    assert "apply_action" not in called_attributes
    assert "set_world_pose" not in called_attributes


def test_rmp_position_and_velocity_output_is_projected_to_static_positions_only():
    action = type(
        "Action",
        (),
        {
            "joint_positions": np.asarray([0.1] * 7, dtype=np.float64),
            "joint_indices": None,
            "joint_velocities": np.asarray([0.2] * 7, dtype=np.float64),
            "joint_efforts": None,
        },
    )()

    projected, discarded_velocity = runtime._explicit_position_action(
        np, action, dof_count=9
    )

    assert projected == {
        "joint_positions": [0.1] * 7,
        "joint_indices": list(range(7)),
        "joint_velocities": None,
        "joint_efforts": None,
    }
    assert discarded_velocity == [0.2] * 7


def test_static_screen_reports_joint_limit_violations_before_materialization():
    violations = runtime._joint_limit_violations(
        np,
        np.asarray([0.0, 0.0, 0.0, -4.0, 0.0, 4.0, 0.0, 0.0, 0.0]),
        np.asarray([-3.0] * 9),
        np.asarray([3.0] * 9),
    )

    assert violations == [
        {"index": 3, "target": -4.0, "lower": -3.0, "upper": 3.0},
        {"index": 5, "target": 4.0, "lower": -3.0, "upper": 3.0},
    ]


def _write_gzip_records(path: Path, records: list[dict]) -> dict[str, object]:
    digest = hashlib.sha256()
    with gzip.open(path, "xb") as stream:
        for record in records:
            payload = runner._canonical_json_bytes(record)
            stream.write(payload)
            digest.update(payload)
    return {
        "path": path.name,
        "sha256": runner.sha256_file(path),
        "stream_sha256": digest.hexdigest(),
        "record_count": len(records),
    }


def _semantics_capture_for_runner() -> dict:
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
        "source_world_matrix_row_major": [1.0, 0.0, 0.0, 0.0] * 4,
        "source_world_matrix_after_row_major": [1.0, 0.0, 0.0, 0.0] * 4,
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
                "joint_positions": [0.1, 0.1, 0.1, -4.0, 0.1, 4.0, 0.1],
                "joint_velocities": [0.0] * 7,
                "joint_efforts": None,
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


def _qdot_counterfactual_for_runner(capture: dict) -> dict:
    raw_action = capture["event0"]["raw_action"]
    return {
        "schema_version": 1,
        "authority": "rmp_qdot_counterfactual_v1",
        "control_dt_s": 1.0 / 60.0,
        "active_joint_positions": capture["baseline"]["joint_positions"][:7],
        "active_joint_velocities": capture["baseline"]["joint_velocities"][:7],
        "watched_joint_names": [],
        "watched_joint_positions": [],
        "watched_joint_velocities": [],
        "actual_qdot_branch": {
            "input_joint_velocities": capture["baseline"]["joint_velocities"][:7],
            "position_targets": raw_action["joint_positions"],
            "velocity_targets": raw_action["joint_velocities"],
        },
        "zero_qdot_branch": {
            "input_joint_velocities": [0.0] * 7,
            "position_targets": raw_action["joint_positions"],
            "velocity_targets": [0.0] * 7,
        },
    }


def test_parent_recomputes_controller_semantics_artifact(tmp_path):
    capture = _semantics_capture_for_runner()
    evaluation = screen.evaluate_native_pick_semantics(capture)
    qdot_counterfactual = _qdot_counterfactual_for_runner(capture)
    qdot_counterfactual_evaluation = screen.evaluate_rmp_qdot_counterfactual(
        capture, qdot_counterfactual
    )
    artifact_payload = {
        "schema_version": 2,
        "manifest_type": "nonformal_native_pick_controller_semantics_v2",
        "capture": capture,
        "evaluation": evaluation,
        "qdot_counterfactual": qdot_counterfactual,
        "qdot_counterfactual_evaluation": qdot_counterfactual_evaluation,
    }
    artifact_path = tmp_path / "controller_semantics.json"
    artifact_path.write_bytes(
        json.dumps(
            artifact_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    )

    verification = runner._verify_controller_semantics_artifact(
        {
            "artifact": {
                "path": artifact_path.name,
                "sha256": runner.sha256_file(artifact_path),
            },
            "evaluation": evaluation,
            "qdot_counterfactual_evaluation": qdot_counterfactual_evaluation,
        },
        root=tmp_path,
    )

    assert verification["decision"] == "RAW_NATIVE_POSITION_TARGET_OUT_OF_LIMIT"
    assert verification["joint_limit_violation_count"] == 2
    assert verification["qdot_counterfactual_decision"] == "QDOT_NOT_CAUSAL_TARGET_OR_LIMIT"


def test_static_screen_rejects_action_drift_from_audited_native_prefix():
    capture = _semantics_capture_for_runner()
    opening = type(
        "Action",
        (),
        {
            "joint_positions": [None] * 7 + [0.04, 0.04],
            "joint_velocities": None,
            "joint_efforts": None,
            "joint_indices": None,
        },
    )()

    runtime._require_semantics_prefix_match(
        np=np,
        capture=capture,
        action_ordinal=0,
        event_before=0,
        event_after=0,
        last_emitted_event=None,
        action=opening,
        rmp_forward_calls=[],
    )
    opening.joint_positions[7] = 0.03

    with pytest.raises(RuntimeError, match="controller_static_screen_semantics_action_drift"):
        runtime._require_semantics_prefix_match(
            np=np,
            capture=capture,
            action_ordinal=0,
            event_before=0,
            event_after=0,
            last_emitted_event=None,
            action=opening,
            rmp_forward_calls=[],
        )


def test_parent_verifies_controller_configuration_invalid_artifacts(tmp_path):
    collision_scope = {
        "blocking_pairs": [["/World/a", "/World/b"]],
        "allowed_source_shell_pairs": [["/World/c", "/World/d"]],
    }
    hold_action = {
        "joint_positions": None,
        "joint_indices": None,
        "joint_velocities": None,
        "joint_efforts": None,
    }
    hold_sha256 = screen.canonical_json_sha256(hold_action)
    initial_positions = [0.0] * 9
    trace = {
        "sample_index": 0,
        "controller_event": -1,
        "joint_positions": initial_positions,
        "action_sha256": hold_sha256,
        "pair_results": [
            {
                "pair": ["/World/a", "/World/b"],
                "classification": "BLOCKING",
                "status": "CLEAR",
                "lower_bound_m": 1.0,
            },
            {
                "pair": ["/World/c", "/World/d"],
                "classification": "ALLOWED_SOURCE_SHELL_FINGER",
                "status": "CLEAR",
                "lower_bound_m": 1.0,
            },
        ],
    }
    normal_action = {
        "action_ordinal": 0,
        "controller_event_before": 0,
        "controller_event": -1,
        "action": hold_action,
        "discarded_joint_velocities": None,
        "action_sha256": hold_sha256,
        "joint_positions_before": initial_positions,
        "joint_positions_after": initial_positions,
        "changed_joint_indices": [],
        "is_hold": True,
        "screen_sample_index": 0,
    }
    rejected_action = {
        "action_ordinal": 1,
        "controller_event_before": 0,
        "controller_event": 0,
        "action": {
            "joint_positions": [-4.0],
            "joint_indices": [3],
            "joint_velocities": None,
            "joint_efforts": None,
        },
        "discarded_joint_velocities": None,
        "joint_positions_before": initial_positions,
        "resolved_joint_positions": [0.0, 0.0, 0.0, -4.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "changed_joint_indices": [3],
        "is_hold": False,
        "joint_limit_violations": [
            {"index": 3, "target": -4.0, "lower": -3.0, "upper": 3.0}
        ],
        "outcome": "JOINT_LIMIT_REJECTED",
    }
    rejected_action["action_sha256"] = screen.canonical_json_sha256(
        rejected_action["action"]
    )
    trace_artifact = _write_gzip_records(
        tmp_path / "configuration_pair_trace.jsonl.gz", [trace]
    )
    action_artifact = _write_gzip_records(
        tmp_path / "controller_action_ledger.jsonl.gz", [normal_action, rejected_action]
    )
    screen_report = {
        "candidate_id": runner.CANDIDATE_ID,
        "controller": {
            "event_sequence": [-1, 0],
            "first_close_emitted": False,
            "lift_command_emitted": False,
            "joint_lower_limits": [-3.0] * 9,
            "joint_upper_limits": [3.0] * 9,
        },
        "object_geometry": {},
        "invalid_controller_action": rejected_action,
        "selection": {
            "decision": runner.CONTROLLER_CONFIGURATION_INVALID,
            "selected_candidate_id": None,
            "passing_candidate_ids": [],
        },
        "configuration_pair_trace": trace_artifact,
        "controller_action_ledger": action_artifact,
    }

    verification = runner._verify_controller_configuration_invalid_artifacts(
        screen_report,
        collision_scope=collision_scope,
        numerical_margin_m=1.0e-6,
        root=tmp_path,
    )

    assert verification["selection"] == screen_report["selection"]
    assert verification["invalid_action_ordinal"] == 1
    assert verification["joint_limit_violation_count"] == 1


def test_kit_gpu_identity_binds_visible_gpu_driver_and_child_log(tmp_path):
    stdout = tmp_path / "child.stdout.log"
    stdout.write_text(
        "| Driver Version: 570.153.02    | Graphics API: Vulkan\n"
        "| 0   | NVIDIA GeForce RTX 4090          | Yes: 0 |\n",
        encoding="utf-8",
    )

    identity = runner._kit_gpu_identity(
        stdout,
        {"NVIDIA_VISIBLE_DEVICES": "4"},
    )

    assert identity["nvidia_visible_devices"] == "4"
    assert identity["kit_logical_gpu_index"] == 0
    assert identity["name"] == "NVIDIA GeForce RTX 4090"
    assert identity["driver_version"] == "570.153.02"
