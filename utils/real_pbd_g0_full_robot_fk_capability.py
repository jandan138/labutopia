"""Pure contracts for the no-step full-robot FK capability diagnostic."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any


PLAN_AUTHORITY = "real_pbd_g0_full_robot_fk_capability_plan_v1"
OBSERVATION_AUTHORITY = "real_pbd_g0_full_robot_fk_capability_observation_v4"
EVALUATION_AUTHORITY = "real_pbd_g0_full_robot_fk_capability_evaluation_v4"
PASS = "G0_FULL_ROBOT_FK_CAPABILITY_PASS"
NO_GO = "G0_FULL_ROBOT_FK_CAPABILITY_NO_GO"
DOF_NAMES = (
    "panda_joint1",
    "panda_joint2",
    "panda_joint3",
    "panda_joint4",
    "panda_joint5",
    "panda_joint6",
    "panda_joint7",
    "panda_finger_joint1",
    "panda_finger_joint2",
)
PARTICLE_PATH = "/World/InternDataParityFluid/Particles"
SIMULATION_POINTS_ATTRIBUTE = "physxParticle:simulationPoints"
# Isaac's tensor articulation readback is float32 even when the target is
# represented as Python float64. This remains far below the 0.5/1.0 mrad probes.
_JOINT_READBACK_ATOL = 2.0e-7
_MATRIX_CHANGE_ATOL = 1.0e-10

PROHIBITED_OPERATION_COUNTERS = (
    "world_step",
    "world_reset",
    "simulation_view_step",
    "timeline_play",
    "timeline_pause",
    "timeline_stop",
    "timeline_time_set",
    "apply_action",
    "robot_nonposition_writer",
    "source_pose_writer",
    "source_velocity_writer",
    "source_force_writer",
    "particle_writer",
    "collision_filter_write",
    "raw_usd_mutation",
)
ALLOWED_OPERATION_COUNTERS = (
    "direct_joint_position_materialization",
    "tensor_kinematic_refresh",
)
OPERATION_GUARD_COVERAGE_FIELDS = (
    *PROHIBITED_OPERATION_COUNTERS,
    *ALLOWED_OPERATION_COUNTERS,
)
PARTICLE_USD_READBACK_SETTINGS = {
    "/physics/suppressReadback": False,
    "/physics/updateToUsd": True,
    "/physics/updateParticlesToUsd": True,
    "/physics/updateVelocitiesToUsd": True,
}


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    return value


def _finite_vector(value: Any, *, field: str, length: int) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != length:
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
        numeric = float(item)
        if not math.isfinite(numeric):
            raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
        result.append(numeric)
    return result


def _nonnegative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    return value


def _runtime_receipt(value: Any, *, field: str) -> dict[str, Any]:
    expected = {"world_index", "timeline_time_s", "is_playing", "is_stopped"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    time_s = value["timeline_time_s"]
    if (
        isinstance(time_s, bool)
        or not isinstance(time_s, (int, float))
        or not math.isfinite(float(time_s))
        or type(value["is_playing"]) is not bool
        or type(value["is_stopped"]) is not bool
    ):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    return {
        "world_index": _nonnegative_int(value["world_index"], field=f"{field}_world_index"),
        "timeline_time_s": float(time_s),
        "is_playing": value["is_playing"],
        "is_stopped": value["is_stopped"],
    }


def _particle_snapshot(value: Any, *, field: str) -> tuple[dict[str, Any], bool]:
    expected = {
        "prim_path",
        "type_name",
        "point_count",
        "attributes",
        "complete",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    if (
        value["prim_path"] != PARTICLE_PATH
        or not isinstance(value["type_name"], str)
        or not value["type_name"]
        or type(value["complete"]) is not bool
    ):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    point_count = _nonnegative_int(value["point_count"], field=f"{field}_point_count")
    attributes = value["attributes"]
    if (
        not isinstance(attributes, Mapping)
        or any(not isinstance(name, str) or not name for name in attributes)
    ):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    normalized_attributes = {}
    for name in sorted(attributes):
        record = attributes[name]
        if not isinstance(record, Mapping) or set(record) != {"shape", "sha256"}:
            raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
        shape = record["shape"]
        if (
            not isinstance(shape, list)
            or not shape
            or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in shape)
        ):
            raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
        normalized_attributes[name] = {
            "shape": list(shape),
            "sha256": _sha256(record["sha256"], field=f"{field}_{name}"),
        }
    simulation_points = normalized_attributes.get(SIMULATION_POINTS_ATTRIBUTE)
    simulation_points_present = (
        simulation_points is not None
        and simulation_points["shape"] == [point_count, 3]
        and point_count > 0
    )
    payload = {
        "prim_path": PARTICLE_PATH,
        "type_name": value["type_name"],
        "point_count": point_count,
        "attributes": normalized_attributes,
        "complete": value["complete"],
    }
    if value["sha256"] != canonical_json_sha256(payload):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    return {**payload, "sha256": _sha256(value["sha256"], field=f"{field}_sha256")}, simulation_points_present


def _state_snapshot(value: Any, *, field: str) -> dict[str, Any]:
    expected = {
        "source",
        "particle_usd_snapshot",
        "source_state_sha256",
        "particle_usd_snapshot_sha256",
        "particle_usd_snapshot_complete",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    source = value["source"]
    expected_source = {
        "position_m",
        "orientation_xyzw",
        "linear_velocity_m_s",
        "angular_velocity_rad_s",
    }
    if not isinstance(source, Mapping) or set(source) != expected_source:
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    normalized_source = {
        "position_m": _finite_vector(source["position_m"], field=f"{field}_position", length=3),
        "orientation_xyzw": _finite_vector(
            source["orientation_xyzw"], field=f"{field}_orientation", length=4
        ),
        "linear_velocity_m_s": _finite_vector(
            source["linear_velocity_m_s"], field=f"{field}_linear_velocity", length=3
        ),
        "angular_velocity_rad_s": _finite_vector(
            source["angular_velocity_rad_s"], field=f"{field}_angular_velocity", length=3
        ),
    }
    orientation_norm = math.sqrt(
        sum(component * component for component in normalized_source["orientation_xyzw"])
    )
    if not math.isclose(orientation_norm, 1.0, rel_tol=0.0, abs_tol=1.0e-6):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    particle_snapshot, simulation_points_present = _particle_snapshot(
        value["particle_usd_snapshot"], field=f"{field}_particles"
    )
    if (
        value["source_state_sha256"] != canonical_json_sha256(normalized_source)
        or value["particle_usd_snapshot_sha256"] != particle_snapshot["sha256"]
        or type(value["particle_usd_snapshot_complete"]) is not bool
        or value["particle_usd_snapshot_complete"] != particle_snapshot["complete"]
    ):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    return {
        "source": normalized_source,
        "particle_usd_snapshot": particle_snapshot,
        "source_state_sha256": _sha256(
            value["source_state_sha256"], field=f"{field}_source_sha256"
        ),
        "particle_usd_snapshot_sha256": _sha256(
            value["particle_usd_snapshot_sha256"], field=f"{field}_particle_sha256"
        ),
        "particle_usd_snapshot_complete": value["particle_usd_snapshot_complete"],
        "simulation_points_present": simulation_points_present,
    }


def _collider_paths(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    if any(not isinstance(path, str) or not path.startswith("/World/Franka/") for path in value):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    if value != sorted(value) or len(value) != len(set(value)):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    return list(value)


def _matrix(value: Any, *, field: str) -> list[list[float]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 4:
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    rows = [_finite_vector(row, field=field, length=4) for row in value]
    if (
        not math.isclose(rows[0][3], 0.0, rel_tol=0.0, abs_tol=1.0e-12)
        or not math.isclose(rows[1][3], 0.0, rel_tol=0.0, abs_tol=1.0e-12)
        or not math.isclose(rows[2][3], 0.0, rel_tol=0.0, abs_tol=1.0e-12)
        or not math.isclose(rows[3][3], 1.0, rel_tol=0.0, abs_tol=1.0e-12)
    ):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    return rows


def _collider_matrices(
    value: Any,
    *,
    collider_paths: Sequence[str],
    field: str,
) -> dict[str, list[list[float]]]:
    if not isinstance(value, Mapping) or set(value) != set(collider_paths):
        raise ValueError(f"real_pbd_g0_fk_capability_{field}_invalid")
    return {
        path: _matrix(value[path], field=f"{field}_{index}")
        for index, path in enumerate(collider_paths)
    }


def _matrix_equal(first: Sequence[Sequence[float]], second: Sequence[Sequence[float]]) -> bool:
    return all(
        math.isclose(left, right, rel_tol=0.0, abs_tol=_MATRIX_CHANGE_ATOL)
        for first_row, second_row in zip(first, second, strict=True)
        for left, right in zip(first_row, second_row, strict=True)
    )


def _particle_usd_readback(value: Any) -> dict[str, bool]:
    if (
        not isinstance(value, Mapping)
        or set(value) != set(PARTICLE_USD_READBACK_SETTINGS)
        or any(type(item) is not bool for item in value.values())
    ):
        raise ValueError("real_pbd_g0_fk_capability_particle_usd_readback_invalid")
    return {name: value[name] for name in sorted(value)}


def _plan(value: Any) -> dict[str, Any]:
    expected = {"authority", "schema_version", "dof_names", "probes", "sha256"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("real_pbd_g0_fk_capability_plan_invalid")
    payload = {key: item for key, item in value.items() if key != "sha256"}
    if (
        value["authority"] != PLAN_AUTHORITY
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["dof_names"] != list(DOF_NAMES)
        or value["sha256"] != canonical_json_sha256(payload)
        or not isinstance(value["probes"], list)
        or len(value["probes"]) != len(DOF_NAMES)
    ):
        raise ValueError("real_pbd_g0_fk_capability_plan_invalid")
    probes = []
    for expected_index, raw in enumerate(value["probes"]):
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"dof_index", "positive_delta", "negative_delta"}
            or type(raw["dof_index"]) is not int
            or raw["dof_index"] != expected_index
        ):
            raise ValueError("real_pbd_g0_fk_capability_plan_invalid")
        positive = raw["positive_delta"]
        negative = raw["negative_delta"]
        maximum = 0.001 if expected_index < 7 else 0.0005
        if (
            isinstance(positive, bool)
            or isinstance(negative, bool)
            or not isinstance(positive, (int, float))
            or not isinstance(negative, (int, float))
            or not math.isfinite(float(positive))
            or not math.isfinite(float(negative))
            or not 0.0 < float(positive) <= maximum
            or not 0.0 < float(negative) <= maximum
        ):
            raise ValueError("real_pbd_g0_fk_capability_plan_invalid")
        probes.append(
            {
                "dof_index": expected_index,
                "positive_delta": float(positive),
                "negative_delta": float(negative),
            }
        )
    return {
        "authority": PLAN_AUTHORITY,
        "schema_version": 1,
        "dof_names": list(DOF_NAMES),
        "probes": probes,
        "sha256": _sha256(value["sha256"], field="plan_sha256"),
    }


def build_plan(*, probes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    payload = {
        "authority": PLAN_AUTHORITY,
        "schema_version": 1,
        "dof_names": list(DOF_NAMES),
        "probes": [dict(item) for item in probes],
    }
    return _plan({**payload, "sha256": canonical_json_sha256(payload)})


def validate_plan(value: Any) -> dict[str, Any]:
    return _plan(value)


def _parse_observation(value: Any, *, plan: Mapping[str, Any]) -> dict[str, Any]:
    normalized_plan = _plan(plan)
    expected = {
        "authority",
        "schema_version",
        "plan_sha256",
        "dof_names",
        "baseline_joint_positions",
        "baseline_runtime",
        "final_runtime",
        "baseline_state",
        "final_state",
        "restored_joint_positions",
        "full_robot_collider_paths",
        "baseline_collider_world_matrices",
        "restored_collider_world_matrices",
        "particle_usd_readback",
        "bootstrap_world_reset_count",
        "post_reset_physics_advance",
        "operation_counts",
        "operation_guard_coverage",
        "samples",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
    payload = {key: item for key, item in value.items() if key != "sha256"}
    if (
        value["authority"] != OBSERVATION_AUTHORITY
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 4
        or value["plan_sha256"] != normalized_plan["sha256"]
        or value["dof_names"] != list(DOF_NAMES)
        or value["sha256"] != canonical_json_sha256(payload)
        or not isinstance(value["samples"], list)
        or len(value["samples"]) != len(DOF_NAMES)
    ):
        raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
    baseline = _finite_vector(value["baseline_joint_positions"], field="baseline_joints", length=9)
    restored = _finite_vector(value["restored_joint_positions"], field="restored_joints", length=9)
    baseline_runtime = _runtime_receipt(value["baseline_runtime"], field="baseline_runtime")
    final_runtime = _runtime_receipt(value["final_runtime"], field="final_runtime")
    baseline_state = _state_snapshot(value["baseline_state"], field="baseline_state")
    final_state = _state_snapshot(value["final_state"], field="final_state")
    collider_paths = _collider_paths(
        value["full_robot_collider_paths"], field="full_robot_collider_paths"
    )
    baseline_matrices = _collider_matrices(
        value["baseline_collider_world_matrices"],
        collider_paths=collider_paths,
        field="baseline_collider_world_matrices",
    )
    restored_matrices = _collider_matrices(
        value["restored_collider_world_matrices"],
        collider_paths=collider_paths,
        field="restored_collider_world_matrices",
    )
    particle_usd_readback = _particle_usd_readback(value["particle_usd_readback"])
    bootstrap_reset_count = _nonnegative_int(
        value["bootstrap_world_reset_count"], field="bootstrap_world_reset_count"
    )
    advance = value["post_reset_physics_advance"]
    if (
        not isinstance(advance, Mapping)
        or set(advance) != {"world_index_delta", "timeline_time_delta_s", "verified_zero"}
        or isinstance(advance["timeline_time_delta_s"], bool)
        or not isinstance(advance["timeline_time_delta_s"], (int, float))
        or not math.isfinite(float(advance["timeline_time_delta_s"]))
        or type(advance["verified_zero"]) is not bool
    ):
        raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
    operation_counts = value["operation_counts"]
    if (
        not isinstance(operation_counts, Mapping)
        or set(operation_counts)
        != set((*PROHIBITED_OPERATION_COUNTERS, *ALLOWED_OPERATION_COUNTERS))
    ):
        raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
    normalized_counts = {
        name: _nonnegative_int(count, field=f"operation_{name}")
        for name, count in operation_counts.items()
    }
    coverage = value["operation_guard_coverage"]
    if (
        not isinstance(coverage, Mapping)
        or set(coverage) != set(OPERATION_GUARD_COVERAGE_FIELDS)
        or any(type(item) is not bool for item in coverage.values())
    ):
        raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
    normalized_coverage = {name: coverage[name] for name in OPERATION_GUARD_COVERAGE_FIELDS}
    samples = []
    for expected_index, raw in enumerate(value["samples"]):
        expected_probe = normalized_plan["probes"][expected_index]
        if (
            not isinstance(raw, Mapping)
            or set(raw)
            != {
                "dof_index",
                "selected_direction",
                "selected_delta",
                "joint_positions",
                "changed_collider_paths",
                "collider_world_matrices",
                "state",
            }
            or type(raw["dof_index"]) is not int
            or raw["dof_index"] != expected_index
            or type(raw["selected_direction"]) is not int
            or raw["selected_direction"] not in {-1, 1}
        ):
            raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
        selected_delta = raw["selected_delta"]
        expected_delta = expected_probe[
            "positive_delta" if raw["selected_direction"] == 1 else "negative_delta"
        ]
        if (
            isinstance(selected_delta, bool)
            or not isinstance(selected_delta, (int, float))
            or not math.isfinite(float(selected_delta))
            or not math.isclose(
                float(selected_delta), expected_delta, rel_tol=0.0, abs_tol=1.0e-15
            )
        ):
            raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
        joints = _finite_vector(raw["joint_positions"], field="sample_joints", length=9)
        expected_joints = list(baseline)
        expected_joints[expected_index] += int(raw["selected_direction"]) * expected_delta
        if any(
            not math.isclose(actual, target, rel_tol=0.0, abs_tol=_JOINT_READBACK_ATOL)
            for actual, target in zip(joints, expected_joints, strict=True)
        ):
            raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
        changed_paths = raw["changed_collider_paths"]
        if (
            not isinstance(changed_paths, list)
            or not changed_paths
            or any(not isinstance(path, str) for path in changed_paths)
            or changed_paths != sorted(changed_paths)
            or len(changed_paths) != len(set(changed_paths))
            or not set(changed_paths) <= set(collider_paths)
        ):
            raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
        matrices = _collider_matrices(
            raw["collider_world_matrices"],
            collider_paths=collider_paths,
            field="sample_collider_world_matrices",
        )
        recomputed_changed_paths = [
            path
            for path in collider_paths
            if not _matrix_equal(baseline_matrices[path], matrices[path])
        ]
        if changed_paths != recomputed_changed_paths:
            raise ValueError("real_pbd_g0_fk_capability_observation_invalid")
        state = _state_snapshot(raw["state"], field="sample_state")
        samples.append(
            {
                "dof_index": expected_index,
                "selected_direction": int(raw["selected_direction"]),
                "selected_delta": float(selected_delta),
                "joint_positions": joints,
                "changed_collider_paths": list(changed_paths),
                "collider_world_matrices": matrices,
                "state": state,
            }
        )
    return {
        "authority": OBSERVATION_AUTHORITY,
        "schema_version": 4,
        "plan_sha256": normalized_plan["sha256"],
        "dof_names": list(DOF_NAMES),
        "baseline_joint_positions": baseline,
        "baseline_runtime": baseline_runtime,
        "final_runtime": final_runtime,
        "baseline_state": baseline_state,
        "final_state": final_state,
        "restored_joint_positions": restored,
        "full_robot_collider_paths": collider_paths,
        "baseline_collider_world_matrices": baseline_matrices,
        "restored_collider_world_matrices": restored_matrices,
        "particle_usd_readback": particle_usd_readback,
        "bootstrap_world_reset_count": bootstrap_reset_count,
        "post_reset_physics_advance": {
            "world_index_delta": _nonnegative_int(
                advance["world_index_delta"], field="world_index_delta"
            ),
            "timeline_time_delta_s": float(advance["timeline_time_delta_s"]),
            "verified_zero": advance["verified_zero"],
        },
        "operation_counts": normalized_counts,
        "operation_guard_coverage": normalized_coverage,
        "samples": samples,
        "sha256": _sha256(value["sha256"], field="observation_sha256"),
    }


def _observation(value: Any, *, plan: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return _parse_observation(value, plan=plan)
    except ValueError as exc:
        if str(exc) == "real_pbd_g0_fk_capability_observation_invalid":
            raise
        raise ValueError("real_pbd_g0_fk_capability_observation_invalid") from exc


def _expected_collider_paths(value: Sequence[str] | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("real_pbd_g0_fk_capability_expected_collider_paths_invalid")
    return _collider_paths(list(value), field="expected_collider_paths")


def evaluate_observation(
    value: Any,
    *,
    plan: Mapping[str, Any],
    expected_collider_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    observation = _observation(value, plan=plan)
    expected_scope = _expected_collider_paths(expected_collider_paths)
    checks = {
        "declared_full_robot_scope_matches_expected": (
            expected_scope is not None
            and observation["full_robot_collider_paths"] == expected_scope
        ),
        "paused_baseline_preserved": (
            observation["baseline_runtime"] == observation["final_runtime"]
            and observation["baseline_runtime"]["is_playing"] is False
            and observation["baseline_runtime"]["is_stopped"] is False
        ),
        "exactly_one_bootstrap_reset": observation["bootstrap_world_reset_count"] == 1,
        "post_reset_physics_advance_zero": (
            observation["post_reset_physics_advance"]["world_index_delta"] == 0
            and math.isclose(
                observation["post_reset_physics_advance"]["timeline_time_delta_s"],
                0.0,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            and observation["post_reset_physics_advance"]["verified_zero"] is True
        ),
        "baseline_joint_positions_restored": all(
            math.isclose(first, second, rel_tol=0.0, abs_tol=_JOINT_READBACK_ATOL)
            for first, second in zip(
                observation["baseline_joint_positions"],
                observation["restored_joint_positions"],
                strict=True,
            )
        ),
        "baseline_collider_matrices_restored": all(
            _matrix_equal(
                observation["baseline_collider_world_matrices"][path],
                observation["restored_collider_world_matrices"][path],
            )
            for path in observation["full_robot_collider_paths"]
        ),
        "all_dof_fk_refreshes_observed": (
            len(observation["samples"]) == len(DOF_NAMES)
            and all(sample["changed_collider_paths"] for sample in observation["samples"])
        ),
        "matrix_witnesses_cover_declared_scope": all(
            set(sample["collider_world_matrices"])
            == set(observation["full_robot_collider_paths"])
            for sample in observation["samples"]
        ),
        "source_and_particle_usd_snapshot_unchanged": (
            all(sample["state"] == observation["baseline_state"] for sample in observation["samples"])
            and observation["final_state"] == observation["baseline_state"]
        ),
        "particle_solver_state_witnessed": (
            observation["baseline_state"]["particle_usd_snapshot_complete"] is True
            and observation["baseline_state"]["simulation_points_present"] is True
            and observation["final_state"]["simulation_points_present"] is True
            and all(sample["state"]["simulation_points_present"] for sample in observation["samples"])
        ),
        "particle_usd_readback_enabled": (
            observation["particle_usd_readback"] == PARTICLE_USD_READBACK_SETTINGS
        ),
        "operation_guard_coverage_complete": all(
            observation["operation_guard_coverage"][name] is True
            for name in OPERATION_GUARD_COVERAGE_FIELDS
        ),
        "no_prohibited_operations": all(
            observation["operation_counts"][name] == 0
            for name in PROHIBITED_OPERATION_COUNTERS
        ),
        "expected_direct_joint_materializations": (
            observation["operation_counts"]["direct_joint_position_materialization"]
            == len(DOF_NAMES) * 2
        ),
        "expected_tensor_kinematic_refreshes": (
            observation["operation_counts"]["tensor_kinematic_refresh"]
            == len(DOF_NAMES) * 2
        ),
    }
    expected_scope_sha256 = (
        canonical_json_sha256({"full_robot_collider_paths": expected_scope})
        if expected_scope is not None
        else None
    )
    payload = {
        "authority": EVALUATION_AUTHORITY,
        "decision": PASS if all(checks.values()) else NO_GO,
        "checks": checks,
        "plan_sha256": observation["plan_sha256"],
        "observation_sha256": observation["sha256"],
        "expected_full_robot_collider_scope_sha256": expected_scope_sha256,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}
