from __future__ import annotations

import copy
import json
from pathlib import Path

from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation
from tools.labutopia_fluid import run_real_pbd_g0_full_robot_fk_capability as runner
from utils import real_pbd_g0_full_robot_fk_capability as capability


REPO_ROOT = Path(__file__).resolve().parents[1]


def _plan() -> dict:
    return capability.build_plan(
        probes=[
            {
                "dof_index": index,
                "positive_delta": 0.001 if index < 7 else 0.0005,
                "negative_delta": 0.001 if index < 7 else 0.0005,
            }
            for index in range(9)
        ]
    )


def _state(*, simulation_points_sha256: str = "b" * 64) -> dict:
    source = {
        "position_m": [0.1, 0.2, 0.3],
        "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "linear_velocity_m_s": [0.0, 0.0, 0.0],
        "angular_velocity_rad_s": [0.0, 0.0, 0.0],
    }
    particle_payload = {
        "prim_path": "/World/InternDataParityFluid/Particles",
        "type_name": "Points",
        "point_count": 2,
        "attributes": {
            "physxParticle:simulationPoints": {
                "shape": [2, 3],
                "sha256": simulation_points_sha256,
            }
        },
        "complete": True,
    }
    particle_snapshot = {
        **particle_payload,
        "sha256": capability.canonical_json_sha256(particle_payload),
    }
    return {
        "source": source,
        "particle_usd_snapshot": particle_snapshot,
        "source_state_sha256": capability.canonical_json_sha256(source),
        "particle_usd_snapshot_sha256": particle_snapshot["sha256"],
        "particle_usd_snapshot_complete": True,
    }


def _runtime() -> dict:
    return {
        "world_index": 7,
        "timeline_time_s": 0.0,
        "is_playing": False,
        "is_stopped": False,
    }


def _rehash(observation: dict) -> dict:
    payload = {key: value for key, value in observation.items() if key != "sha256"}
    observation["sha256"] = capability.canonical_json_sha256(payload)
    return observation


def _observation(plan: dict) -> dict:
    baseline = [0.0] * 9
    state = _state()
    collider_paths = sorted(
        [f"/World/Franka/panda_link{index}/collider" for index in range(9)]
        + [
            "/World/Franka/panda_hand/collider",
            "/World/Franka/panda_leftfinger/collider",
        ]
    )
    baseline_matrices = {
        path: [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        for path in collider_paths
    }
    samples = []
    for probe in plan["probes"]:
        index = probe["dof_index"]
        joints = list(baseline)
        joints[index] = probe["positive_delta"]
        matrices = {
            path: [list(row) for row in matrix]
            for path, matrix in baseline_matrices.items()
        }
        matrices[collider_paths[index]][3][0] = float(index + 1) * 1.0e-4
        samples.append(
            {
                "dof_index": index,
                "selected_direction": 1,
                "selected_delta": probe["positive_delta"],
                "joint_positions": joints,
                "changed_collider_paths": [collider_paths[index]],
                "collider_world_matrices": matrices,
                "state": copy.deepcopy(state),
            }
        )
    payload = {
        "authority": capability.OBSERVATION_AUTHORITY,
        "schema_version": 4,
        "plan_sha256": plan["sha256"],
        "dof_names": list(capability.DOF_NAMES),
        "baseline_joint_positions": baseline,
        "baseline_runtime": _runtime(),
        "final_runtime": _runtime(),
        "baseline_state": state,
        "final_state": copy.deepcopy(state),
        "restored_joint_positions": baseline,
        "full_robot_collider_paths": collider_paths,
        "baseline_collider_world_matrices": baseline_matrices,
        "restored_collider_world_matrices": copy.deepcopy(baseline_matrices),
        "particle_usd_readback": {
            "/physics/suppressReadback": False,
            "/physics/updateToUsd": True,
            "/physics/updateParticlesToUsd": True,
            "/physics/updateVelocitiesToUsd": True,
        },
        "bootstrap_world_reset_count": 1,
        "post_reset_physics_advance": {
            "world_index_delta": 0,
            "timeline_time_delta_s": 0.0,
            "verified_zero": True,
        },
        "operation_counts": {
            **{name: 0 for name in capability.PROHIBITED_OPERATION_COUNTERS},
            "direct_joint_position_materialization": 18,
            "tensor_kinematic_refresh": 18,
        },
        "operation_guard_coverage": {
            name: True for name in capability.OPERATION_GUARD_COVERAGE_FIELDS
        },
        "samples": samples,
    }
    return {**payload, "sha256": capability.canonical_json_sha256(payload)}


def test_fk_capability_observation_passes_only_for_no_step_full_dof_readback():
    plan = _plan()

    observation = _observation(plan)
    evaluation = capability.evaluate_observation(
        observation,
        plan=plan,
        expected_collider_paths=observation["full_robot_collider_paths"],
    )

    assert evaluation["decision"] == capability.PASS
    assert all(evaluation["checks"].values())


def test_fk_capability_observation_rejects_particle_drift_and_nonzero_action_count():
    plan = _plan()
    observation = _observation(plan)
    observation["samples"][4]["state"] = _state(simulation_points_sha256="c" * 64)
    observation["operation_counts"]["apply_action"] = 1
    _rehash(observation)

    evaluation = capability.evaluate_observation(
        observation,
        plan=plan,
        expected_collider_paths=observation["full_robot_collider_paths"],
    )

    assert evaluation["decision"] == capability.NO_GO
    assert evaluation["checks"]["source_and_particle_usd_snapshot_unchanged"] is False
    assert evaluation["checks"]["no_prohibited_operations"] is False


def test_fk_capability_observation_rejects_final_state_drift_and_stopped_timeline():
    plan = _plan()
    observation = _observation(plan)
    observation["final_state"] = _state(simulation_points_sha256="c" * 64)
    observation["baseline_runtime"]["is_stopped"] = True
    _rehash(observation)

    evaluation = capability.evaluate_observation(
        observation,
        plan=plan,
        expected_collider_paths=observation["full_robot_collider_paths"],
    )

    assert evaluation["decision"] == capability.NO_GO
    assert evaluation["checks"]["paused_baseline_preserved"] is False
    assert evaluation["checks"]["source_and_particle_usd_snapshot_unchanged"] is False


def test_fk_capability_observation_rejects_matrix_witness_outside_declared_scope():
    plan = _plan()
    observation = _observation(plan)
    observation["samples"][0]["changed_collider_paths"] = ["/World/Franka/not-in-scope"]
    _rehash(observation)

    try:
        capability.evaluate_observation(
            observation,
            plan=plan,
            expected_collider_paths=observation["full_robot_collider_paths"],
        )
    except ValueError as exc:
        assert str(exc) == "real_pbd_g0_fk_capability_observation_invalid"
    else:
        raise AssertionError("out-of-scope matrix witness unexpectedly accepted")


def test_fk_capability_requires_the_parent_declared_full_robot_scope():
    plan = _plan()
    observation = _observation(plan)

    evaluation = capability.evaluate_observation(
        observation,
        plan=plan,
        expected_collider_paths=observation["full_robot_collider_paths"][:-1],
    )

    assert evaluation["decision"] == capability.NO_GO
    assert evaluation["checks"]["declared_full_robot_scope_matches_expected"] is False


def test_fk_capability_rejects_unrestored_fk_and_incomplete_guards():
    plan = _plan()
    observation = _observation(plan)
    changed_path = observation["full_robot_collider_paths"][0]
    observation["restored_collider_world_matrices"][changed_path][3][1] = 0.01
    observation["bootstrap_world_reset_count"] = 2
    observation["operation_guard_coverage"]["world_reset"] = False
    _rehash(observation)

    evaluation = capability.evaluate_observation(
        observation,
        plan=plan,
        expected_collider_paths=observation["full_robot_collider_paths"],
    )

    assert evaluation["decision"] == capability.NO_GO
    assert evaluation["checks"]["baseline_collider_matrices_restored"] is False
    assert evaluation["checks"]["exactly_one_bootstrap_reset"] is False
    assert evaluation["checks"]["operation_guard_coverage_complete"] is False


def test_fk_capability_requires_particle_usd_readback_binding():
    plan = _plan()
    observation = _observation(plan)
    observation["particle_usd_readback"]["/physics/updateParticlesToUsd"] = False
    _rehash(observation)

    evaluation = capability.evaluate_observation(
        observation,
        plan=plan,
        expected_collider_paths=observation["full_robot_collider_paths"],
    )

    assert evaluation["decision"] == capability.NO_GO
    assert evaluation["checks"]["particle_usd_readback_enabled"] is False


def test_fk_capability_accepts_float32_joint_readback_rounding_only():
    plan = _plan()
    observation = _observation(plan)
    observation["samples"][3]["joint_positions"][3] -= 1.3e-8
    _rehash(observation)

    evaluation = capability.evaluate_observation(
        observation,
        plan=plan,
        expected_collider_paths=observation["full_robot_collider_paths"],
    )

    assert evaluation["decision"] == capability.PASS


def test_fk_capability_rejects_tampered_state_digest_and_non_affine_matrix():
    plan = _plan()
    observation = _observation(plan)
    observation["baseline_state"]["source"]["position_m"][0] = 0.4
    _rehash(observation)

    try:
        capability.evaluate_observation(
            observation,
            plan=plan,
            expected_collider_paths=observation["full_robot_collider_paths"],
        )
    except ValueError as exc:
        assert str(exc) == "real_pbd_g0_fk_capability_observation_invalid"
    else:
        raise AssertionError("tampered state digest unexpectedly accepted")

    observation = _observation(plan)
    observation["baseline_collider_world_matrices"][
        observation["full_robot_collider_paths"][0]
    ][0][3] = 0.1
    _rehash(observation)
    try:
        capability.evaluate_observation(
            observation,
            plan=plan,
            expected_collider_paths=observation["full_robot_collider_paths"],
        )
    except ValueError as exc:
        assert str(exc) == "real_pbd_g0_fk_capability_observation_invalid"
    else:
        raise AssertionError("non-affine matrix unexpectedly accepted")


def test_fk_capability_plan_rejects_a_noncanonical_dof_probe_set():
    plan = _plan()
    plan["probes"][7]["dof_index"] = 6
    payload = {key: value for key, value in plan.items() if key != "sha256"}
    plan["sha256"] = capability.canonical_json_sha256(payload)

    try:
        capability.validate_plan(plan)
    except ValueError as exc:
        assert str(exc) == "real_pbd_g0_fk_capability_plan_invalid"
    else:
        raise AssertionError("duplicate capability DOF probe unexpectedly accepted")


def test_fk_capability_plan_rejects_boolean_schema_version():
    plan = _plan()
    plan["schema_version"] = True
    payload = {key: value for key, value in plan.items() if key != "sha256"}
    plan["sha256"] = capability.canonical_json_sha256(payload)

    try:
        capability.validate_plan(plan)
    except ValueError as exc:
        assert str(exc) == "real_pbd_g0_fk_capability_plan_invalid"
    else:
        raise AssertionError("boolean schema version unexpectedly accepted")


def test_checked_in_fk_plan_and_profile_are_bound_to_diagnostic_only_runner():
    raw_plan = json.loads(runner.FK_CAPABILITY_PLAN_PATH.read_text(encoding="ascii"))
    plan = capability.validate_plan(raw_plan)
    request = runner.build_capability_request()
    closure = set(runner.source_paths())

    assert plan["sha256"] == raw_plan["sha256"]
    assert request["plan"] == plan
    assert request["authorization"] == {
        "clearance_certificate_authorized": False,
        "g0_go_authorized": False,
        "phase3_authorized": False,
    }
    assert runner.FK_CAPABILITY_PLAN_PATH.resolve() in closure
    assert runner.FK_CAPABILITY_PROFILE_PATH.resolve() in closure
    assert (
        REPO_ROOT / "utils/nonformal_controller_static_collision_screen.py"
    ).resolve() in closure
    assert runner.expected_child_returncode(runner.CAPABILITY_PASS) == 0
    assert runner.expected_child_returncode(runner.CAPABILITY_NO_GO) == 0
    assert runner.expected_child_returncode(runner.RUNTIME_BLOCKED) == 2


def test_runner_uses_attestation_canonical_hashes_for_runtime_receipts():
    receipt = {"authority": "example", "schema_version": 1}

    assert runner._attestation_json_sha256(receipt) == attestation.canonical_json_sha256(
        receipt
    )
    assert runner._attestation_json_sha256(receipt) != capability.canonical_json_sha256(
        receipt
    )
