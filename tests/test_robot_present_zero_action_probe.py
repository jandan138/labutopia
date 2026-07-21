from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import yaml

from tools.labutopia_fluid import run_robot_present_zero_action_probe as probe
from utils.online_fluid_surface import canonical_position_sha256


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_source_rest_offset_zero_600hz_step600_layout_v1.yaml"
)
ASSET_PATH = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)


class _ResetTarget:
    def __init__(self) -> None:
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1


def _source_pose_hash(matrix: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(matrix, dtype="<f8").tobytes(order="C")
    ).hexdigest()


def _small_trace_arrays() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    matrices = np.repeat(np.eye(4, dtype=np.float64)[None, :, :], 3, axis=0)
    matrices[1, 3, 0] = 0.001
    matrices[2, 3, 0] = 0.0015
    positions = np.asarray(
        [
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.1]],
            [[0.0, 0.0, 0.01], [0.0, 0.0, 0.11]],
            [[0.0, 0.0, 0.02], [0.0, 0.0, 0.12]],
        ],
        dtype=np.float64,
    )
    pose_hashes = np.asarray([_source_pose_hash(matrix) for matrix in matrices])
    position_hashes = np.asarray(
        [canonical_position_sha256(record) for record in positions]
    )
    source = {
        "local_step": np.asarray([0, 1, 2], dtype=np.int64),
        "phase": np.asarray(["baseline", "pre_roll", "hold"]),
        "phase_step": np.asarray([0, 1, 1], dtype=np.int64),
        "motion_reference_local_step": np.asarray([0, 0, 1], dtype=np.int64),
        "world_step": np.asarray([20, 21, 22], dtype=np.int64),
        "world_time_s": np.asarray([1.0, 1.5, 2.0], dtype=np.float64),
        "source_world_matrix_m": matrices,
        "source_geometry_center_world_m": matrices[:, 3, :3].copy(),
        "source_axis_world": np.repeat(
            np.asarray([[0.0, 1.0, 0.0]], dtype=np.float64), 3, axis=0
        ),
        "linear_velocity_m_s": np.zeros((3, 3), dtype=np.float64),
        "angular_velocity_rad_s": np.zeros((3, 3), dtype=np.float64),
        "translation_m": np.asarray([0.0, 0.001, 0.0005], dtype=np.float64),
        "tilt_degrees": np.zeros(3, dtype=np.float64),
        "translation_valid": np.ones(3, dtype=np.bool_),
        "tilt_valid": np.ones(3, dtype=np.bool_),
        "source_pose_sha256": pose_hashes,
    }
    particles = {
        "positions_world_m": positions,
        "position_sha256": position_hashes,
        "particle_count": np.asarray([2, 2, 2], dtype=np.int64),
        "partition_complete": np.ones(3, dtype=np.bool_),
        "source_frame_pose_sha256": pose_hashes.copy(),
        "source": np.asarray([2, 2, 2], dtype=np.int64),
        "target": np.zeros(3, dtype=np.int64),
        "transit": np.zeros(3, dtype=np.int64),
        "tabletop_spill": np.zeros(3, dtype=np.int64),
        "below_table": np.zeros(3, dtype=np.int64),
        "nonfinite": np.zeros(3, dtype=np.int64),
    }
    return source, particles


def _small_trace_authority() -> dict:
    return {
        "geometry_center_parent_local_m": [0.0, 0.0, 0.0],
        "vessel_axis_object": [0.0, 1.0, 0.0],
        "translation_limit_m": 0.002,
        "tilt_limit_degrees": 1.0,
        "source_frame_contract": {
            "origin_parent_local_m": [0.0, 0.0, 0.0],
            "axes_parent_local": np.eye(3, dtype=np.float64).tolist(),
            "interior_radius_m": 0.5,
            "interior_floor_m": -0.1,
            "rim_height_m": 0.5,
            "epsilon_m": 0.00005,
        },
    }


def test_default_candidate_and_runtime_dimensions_are_hash_pinned():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    result = probe.validate_candidate_contract(
        config,
        config_sha256=probe.sha256_file(CONFIG_PATH),
        asset_sha256=probe.sha256_file(ASSET_PATH),
    )

    assert probe.DEFAULT_CONFIG == CONFIG_PATH
    assert result["config_sha256"] == probe.EXPECTED_CONFIG_SHA256
    assert result["asset_sha256"] == probe.EXPECTED_ASSET_SHA256
    assert result["physics_dt"] == pytest.approx(1 / 600)
    assert result["pre_roll_steps"] == 600
    assert result["hold_steps"] == 1800
    assert result["record_count"] == 2401
    assert result["particle_trace_shape"] == [2401, 3600, 3]
    assert (
        probe.EXPECTED_SCENE_DEPENDENCY_CLOSURE_SHA256
        == "c62a6317d8c9076a0c136a359db505b5a3be0ff26193a15376c57a9afc9a60ce"
    )
    assert probe.sha256_file(REPO_ROOT / "assets/robots/Franka.usd") == (
        probe.EXPECTED_ROBOT_SHA256
    )


def test_zero_action_ledger_requires_only_the_two_named_bootstrap_resets():
    target = _ResetTarget()
    ledger = probe.ZeroActionLedger()
    ledger.instrument(target, "reset", "world.reset", required=True)

    with ledger.expect_bootstrap_reset("task_constructor_camera_reset"):
        target.reset()
    with ledger.expect_bootstrap_reset("explicit_task_reset"):
        target.reset()

    reset_contract = ledger.mark_authority_origin()
    ledger.assert_zero_post_origin()

    assert target.reset_count == 2
    assert reset_contract["reset_count"] == 2
    assert reset_contract["reset_labels"] == [
        "task_constructor_camera_reset",
        "explicit_task_reset",
    ]
    assert ledger.summary()["post_origin_call_count"] == 0


def test_zero_action_ledger_fails_closed_on_missing_extra_or_post_origin_reset():
    missing = probe.ZeroActionLedger()
    missing_target = _ResetTarget()
    missing.instrument(missing_target, "reset", "world.reset", required=True)
    with missing.expect_bootstrap_reset("task_constructor_camera_reset"):
        missing_target.reset()
    with pytest.raises(RuntimeError, match="zero_action_bootstrap_reset_contract_invalid"):
        missing.mark_authority_origin()

    extra = probe.ZeroActionLedger()
    extra_target = _ResetTarget()
    extra.instrument(extra_target, "reset", "world.reset", required=True)
    with pytest.raises(RuntimeError, match="zero_action_unexpected_bootstrap_reset"):
        extra_target.reset()
    assert extra_target.reset_count == 0

    complete = probe.ZeroActionLedger()
    complete_target = _ResetTarget()
    complete.instrument(complete_target, "reset", "world.reset", required=True)
    for label in probe.EXPECTED_BOOTSTRAP_RESET_LABELS:
        with complete.expect_bootstrap_reset(label):
            complete_target.reset()
    complete.mark_authority_origin()
    with pytest.raises(RuntimeError, match="zero_action_post_origin_call:world.reset"):
        complete_target.reset()
    assert complete_target.reset_count == 2
    assert complete.summary()["post_origin_call_count"] == 1


def test_live_robot_task_contract_requires_initialized_nine_dof_franka():
    finger_paths = (
        "/World/Franka/panda_leftfinger",
        "/World/Franka/panda_rightfinger",
    )
    result = probe.validate_live_state_contract(
        articulation_valid=True,
        dof_names=probe.EXPECTED_FRANKA_DOF_NAMES,
        joint_positions=np.zeros(9, dtype=np.float64),
        robot_position_world_m=[-0.4, 0.0, 0.71],
        expected_robot_position_world_m=[-0.4, 0.0, 0.71],
        robot_orientation_wxyz=[1.0, 0.0, 0.0, 0.0],
        task_robot_matches=True,
        task_source_path="/World/beaker2",
        expected_source_path="/World/beaker2",
        task_frame_index=4,
        finger_body_paths=finger_paths,
        bound_finger_colliders={
            finger_paths[0]: [finger_paths[0] + "/collider"],
            finger_paths[1]: [finger_paths[1] + "/collider"],
        },
        contact_material_path="/World/PhysicsMaterials/ContactGrasp",
    )

    assert result["valid"] is True
    assert result["dof_count"] == 9
    assert result["task_frame_index"] == 4
    assert result["source_path"] == "/World/beaker2"
    assert result["finger_collider_count"] == 2


@pytest.mark.parametrize(
    "replacement",
    [
        {"articulation_valid": False},
        {"joint_positions": [0.0] * 8},
        {"joint_positions": [0.0] * 8 + [np.nan]},
        {"task_robot_matches": False},
        {"task_source_path": "/World/beaker1"},
        {"task_frame_index": 0},
        {
            "bound_finger_colliders": {
                "/World/Franka/panda_leftfinger": ["/left/collider"]
            }
        },
    ],
)
def test_live_robot_task_contract_rejects_incomplete_state(replacement):
    finger_paths = (
        "/World/Franka/panda_leftfinger",
        "/World/Franka/panda_rightfinger",
    )
    values = {
        "articulation_valid": True,
        "dof_names": probe.EXPECTED_FRANKA_DOF_NAMES,
        "joint_positions": np.zeros(9),
        "robot_position_world_m": [-0.4, 0.0, 0.71],
        "expected_robot_position_world_m": [-0.4, 0.0, 0.71],
        "robot_orientation_wxyz": [1.0, 0.0, 0.0, 0.0],
        "task_robot_matches": True,
        "task_source_path": "/World/beaker2",
        "expected_source_path": "/World/beaker2",
        "task_frame_index": 4,
        "finger_body_paths": finger_paths,
        "bound_finger_colliders": {
            finger_paths[0]: [finger_paths[0] + "/collider"],
            finger_paths[1]: [finger_paths[1] + "/collider"],
        },
        "contact_material_path": "/World/PhysicsMaterials/ContactGrasp",
    }
    values.update(replacement)

    with pytest.raises(ValueError, match="robot_present_live_state_invalid"):
        probe.validate_live_state_contract(**values)


def test_sampling_spec_is_baseline_plus_600_preroll_plus_1800_hold():
    specs = [
        probe.trace_sample_spec(
            local_step,
            pre_roll_steps=600,
            hold_steps=1800,
        )
        for local_step in range(2401)
    ]

    assert specs[0] == {
        "local_step": 0,
        "phase": "baseline",
        "phase_step": 0,
        "motion_reference_local_step": 0,
    }
    assert specs[600]["phase"] == "pre_roll"
    assert specs[600]["phase_step"] == 600
    assert specs[601]["phase"] == "hold"
    assert specs[601]["phase_step"] == 1
    assert specs[601]["motion_reference_local_step"] == 600
    assert specs[-1]["local_step"] == 2400
    assert specs[-1]["phase_step"] == 1800

    with pytest.raises(ValueError, match="robot_present_sample_local_step_invalid"):
        probe.trace_sample_spec(2401, pre_roll_steps=600, hold_steps=1800)


def test_startup_motion_gate_uses_authored_pose_for_every_checkpoint():
    authored = np.eye(4, dtype=np.float64)
    camera_reset = authored.copy()
    camera_reset[3, 0] = 0.001
    explicit_reset = authored.copy()
    explicit_reset[3, 0] = 0.0015

    passed = probe.summarize_startup_motion_checkpoints(
        authored_source_world_matrix=authored,
        authored_source_center_world_m=[0.0, 0.0, 0.0],
        checkpoints=[
            {
                "name": "task_constructor_camera_reset",
                "source_world_matrix": camera_reset,
                "source_center_world_m": camera_reset[3, :3],
            },
            {
                "name": "explicit_task_reset",
                "source_world_matrix": explicit_reset,
                "source_center_world_m": explicit_reset[3, :3],
            },
        ],
        vessel_axis_object=[0.0, 1.0, 0.0],
        translation_limit_m=0.002,
        tilt_limit_degrees=1.0,
    )
    assert passed["valid"] is True
    assert passed["passed"] is True
    assert passed["checkpoint_count"] == 2
    assert passed["maximum_translation_m"] == pytest.approx(0.0015)

    failed_reset = explicit_reset.copy()
    failed_reset[3, 0] = 0.0021
    failed = probe.summarize_startup_motion_checkpoints(
        authored_source_world_matrix=authored,
        authored_source_center_world_m=[0.0, 0.0, 0.0],
        checkpoints=[
            {
                "name": "explicit_task_reset",
                "source_world_matrix": failed_reset,
                "source_center_world_m": failed_reset[3, :3],
            }
        ],
        vessel_axis_object=[0.0, 1.0, 0.0],
        translation_limit_m=0.002,
        tilt_limit_degrees=1.0,
    )
    assert failed["passed"] is False
    assert failed["first_failure_checkpoint"] == "explicit_task_reset"

    inconsistent_center = failed_reset[3, :3].copy()
    inconsistent_center[1] += 0.01
    with pytest.raises(
        ValueError, match="robot_present_startup_checkpoint_center_invalid"
    ):
        probe.summarize_startup_motion_checkpoints(
            authored_source_world_matrix=authored,
            authored_source_center_world_m=[0.0, 0.0, 0.0],
            checkpoints=[
                {
                    "name": "explicit_task_reset",
                    "source_world_matrix": failed_reset,
                    "source_center_world_m": inconsistent_center,
                }
            ],
            vessel_axis_object=[0.0, 1.0, 0.0],
            translation_limit_m=0.002,
            tilt_limit_degrees=1.0,
        )


def test_parent_semantically_validates_source_and_particle_trace_arrays():
    source, particles = _small_trace_arrays()

    result = probe.validate_trace_array_contract(
        source,
        particles,
        physics_dt=0.5,
        pre_roll_steps=1,
        hold_steps=1,
        expected_particle_count=2,
        trace_authority=_small_trace_authority(),
    )

    assert result["valid"] is True
    assert result["record_count"] == 3
    assert result["source_trace_shape"] == [3, 4, 4]
    assert result["particle_trace_shape"] == [3, 2, 3]
    assert result["position_hashes_valid"] is True
    assert result["source_pose_hashes_valid"] is True

    particles["position_sha256"] = particles["position_sha256"].copy()
    particles["position_sha256"][1] = "f" * 64
    with pytest.raises(ValueError, match="robot_present_particle_position_hash_invalid"):
        probe.validate_trace_array_contract(
            source,
            particles,
            physics_dt=0.5,
            pre_roll_steps=1,
            hold_steps=1,
            expected_particle_count=2,
            trace_authority=_small_trace_authority(),
        )


def test_parent_recomputes_motion_from_matrices_and_containment_from_positions():
    source, particles = _small_trace_arrays()
    source["source_world_matrix_m"] = source["source_world_matrix_m"].copy()
    source["source_world_matrix_m"][1, 3, 0] = 0.01
    source["source_pose_sha256"] = source["source_pose_sha256"].copy()
    source["source_pose_sha256"][1] = _source_pose_hash(
        source["source_world_matrix_m"][1]
    )
    particles["source_frame_pose_sha256"] = (
        particles["source_frame_pose_sha256"].copy()
    )
    particles["source_frame_pose_sha256"][1] = source[
        "source_pose_sha256"
    ][1]

    with pytest.raises(
        ValueError, match="robot_present_source_geometry_center_invalid"
    ):
        probe.validate_trace_array_contract(
            source,
            particles,
            physics_dt=0.5,
            pre_roll_steps=1,
            hold_steps=1,
            expected_particle_count=2,
            trace_authority=_small_trace_authority(),
        )

    source, particles = _small_trace_arrays()
    particles["positions_world_m"] = particles["positions_world_m"].copy()
    particles["positions_world_m"][1, :, 0] = 1.0
    particles["position_sha256"] = particles["position_sha256"].copy()
    particles["position_sha256"][1] = canonical_position_sha256(
        particles["positions_world_m"][1]
    )
    with pytest.raises(
        ValueError, match="robot_present_source_containment_count_invalid"
    ):
        probe.validate_trace_array_contract(
            source,
            particles,
            physics_dt=0.5,
            pre_roll_steps=1,
            hold_steps=1,
            expected_particle_count=2,
            trace_authority=_small_trace_authority(),
        )


def test_effective_particle_readback_settings_must_match_every_applied_setting():
    expected = {
        "/physics/suppressReadback": False,
        "/physics/updateToUsd": True,
        "/physics/updateParticlesToUsd": True,
    }

    assert probe.validate_effective_particle_readback_settings(
        expected, dict(expected)
    )["valid"] is True

    stale = dict(expected)
    stale["/physics/updateParticlesToUsd"] = False
    with pytest.raises(ValueError, match="robot_present_particle_readback_invalid"):
        probe.validate_effective_particle_readback_settings(expected, stale)


def test_required_command_coverage_includes_direct_gripper_joint_write():
    assert "gripper.set_joint_positions" in probe.REQUIRED_POST_ORIGIN_APIS


def test_parent_validates_drive_snapshot_without_dependency_closure_state():
    drives = [
        {"joint_name": name, "active": index < 8}
        for index, name in enumerate(probe.EXPECTED_FRANKA_DOF_NAMES)
    ]
    payload = {
        "robot_path": "/World/Franka",
        "drive_count": 9,
        "joint_names": list(probe.EXPECTED_FRANKA_DOF_NAMES),
        "active_drive_count": 8,
        "drives": drives,
    }
    snapshot = {
        **payload,
        "sha256": probe.passive._canonical_json_sha256(payload),
        "valid": True,
    }

    probe._validate_report_drive_snapshot(snapshot)
    snapshot["sha256"] = "f" * 64
    with pytest.raises(
        ValueError, match="robot_present_parent_drive_snapshot_invalid"
    ):
        probe._validate_report_drive_snapshot(snapshot)


def test_parent_motion_summary_comparison_allows_only_float_roundoff():
    reported = {
        "status": "MEASURED",
        "valid": True,
        "passed": True,
        "record_count": 2401,
        "maximum_translation_m": 1.585829803601833e-05,
        "maximum_tilt_degrees": 0.0001743517834610463,
        "first_translation_failure_local_step": None,
        "first_tilt_failure_local_step": None,
    }
    recomputed = dict(reported)
    recomputed["maximum_tilt_degrees"] = 0.00017435178346104634

    assert probe.motion_summaries_match(reported, recomputed) is True
    recomputed["maximum_tilt_degrees"] = reported["maximum_tilt_degrees"] + 1e-8
    assert probe.motion_summaries_match(reported, recomputed) is False


def test_robot_present_finalizer_requires_clean_child_and_matching_identity():
    provisional = {
        "schema_version": 1,
        "manifest_type": probe.MANIFEST_TYPE,
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "run_nonce": "nonce-1",
        "config_sha256": probe.EXPECTED_CONFIG_SHA256,
        "measurement_decision": "ROBOT_PRESENT_ZERO_ACTION_PASS",
    }

    clean = probe.finalize_child_report(
        provisional,
        expected_run_nonce="nonce-1",
        expected_config_sha256=probe.EXPECTED_CONFIG_SHA256,
        child_command=["python", "probe.py"],
        child_returncode=0,
        timed_out=False,
        termination=None,
    )
    assert clean["decision"] == "ROBOT_PRESENT_ZERO_ACTION_PASS"
    assert clean["lifecycle_status"] == "completed"
    assert clean["shutdown_status"] == "child_exit_0"

    timed_out = probe.finalize_child_report(
        provisional,
        expected_run_nonce="nonce-1",
        expected_config_sha256=probe.EXPECTED_CONFIG_SHA256,
        child_command=["python", "probe.py"],
        child_returncode=-9,
        timed_out=True,
        termination="SIGKILL",
    )
    assert timed_out["decision"] == "PROBE_RUNTIME_ERROR"
    assert timed_out["lifecycle_status"] == "failed"

    with pytest.raises(ValueError, match="robot_present_provisional_identity_invalid"):
        probe.finalize_child_report(
            provisional,
            expected_run_nonce="different",
            expected_config_sha256=probe.EXPECTED_CONFIG_SHA256,
            child_command=["python", "probe.py"],
            child_returncode=0,
            timed_out=False,
            termination=None,
        )


def test_runner_source_does_not_construct_controller_or_fluid_loop():
    source = Path(probe.__file__).read_text(encoding="utf-8")

    assert "create_controller" not in source
    assert "FluidEvaluationLoop" not in source
    assert "RMPFlowController" not in source
    assert "robot_present_baseline_particle_layout_invalid" not in source
