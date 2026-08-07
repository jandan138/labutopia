"""Pure v2 validation for an event-0 source-collider snapshot.

The v2 artifact extends the v1 precontact replay with a PhysX-rooted source
collider closure.  It remains a bounded diagnostic and never authorizes
contact, attachment, lift, a gate, or Phase 3.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from utils import formal_precontact_event0_replay as replay


AUTHORITY = "formal_precontact_event0_snapshot_replay_v2"
CLASSIFICATION = "FORMAL_PRECONTACT_EVENT0_SNAPSHOT_REPLAY_ONLY"
FIXED_MOUNT_AUTHORITY = "formal_precontact_event0_fixed_mount_snapshot_replay_v3"
FIXED_MOUNT_CLASSIFICATION = "FORMAL_PRECONTACT_EVENT0_FIXED_MOUNT_SNAPSHOT_REPLAY_ONLY"
FIXED_MOUNT_PROFILE_AUTHORITY = "formal_precontact_fixed_mount_profile_v1"
FIXED_MOUNT_RUNTIME_FILTER_AUTHORITY = "formal_precontact_fixed_mount_runtime_filter_v1"
SOURCE_CLOSURE_AUTHORITY = "formal_precontact_source_collider_closure_v1"
MATRIX_CONVENTION = "row_major_row_vector_meters_v1"
SOURCE_ROOT_PATH = "/World/beaker2"
SOURCE_MESH_PATH = "/World/beaker2/mesh"
SOURCE_WRAPPER_ROOT_PATH = "/World/beaker2/FluidSafeWrapperCanonical"
PASS = replay.PASS
NO_GO = replay.NO_GO
SAFETY_ABORT = replay.SAFETY_ABORT


def canonical_json_sha256(value: Any) -> str:
    return replay.canonical_json_sha256(value)


def _sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"precontact_snapshot_{field}_invalid")
    return value


def _vector(value: Any, *, field: str, length: int) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != length:
        raise ValueError(f"precontact_snapshot_{field}_invalid")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"precontact_snapshot_{field}_invalid")
        numeric = float(item)
        if not math.isfinite(numeric):
            raise ValueError(f"precontact_snapshot_{field}_invalid")
        result.append(numeric)
    return result


def _matrix(value: Any, *, field: str) -> list[float]:
    matrix = _vector(value, field=field, length=16)
    if (
        any(abs(matrix[index]) > 1.0e-12 for index in (3, 7, 11))
        or not math.isclose(matrix[15], 1.0, rel_tol=0.0, abs_tol=1.0e-12)
    ):
        raise ValueError("precontact_snapshot_closure_matrix_invalid")
    determinant = (
        matrix[0] * (matrix[5] * matrix[10] - matrix[6] * matrix[9])
        - matrix[1] * (matrix[4] * matrix[10] - matrix[6] * matrix[8])
        + matrix[2] * (matrix[4] * matrix[9] - matrix[5] * matrix[8])
    )
    if not math.isfinite(determinant) or abs(determinant) <= 1.0e-12:
        raise ValueError("precontact_snapshot_closure_matrix_invalid")
    return matrix


def _rigid_root_matrix(matrix: Sequence[float]) -> None:
    rows = [matrix[index : index + 3] for index in (0, 4, 8)]
    for row_index, row in enumerate(rows):
        for other_index, other in enumerate(rows):
            dot = sum(left * right for left, right in zip(row, other, strict=True))
            expected = 1.0 if row_index == other_index else 0.0
            if not math.isclose(dot, expected, rel_tol=0.0, abs_tol=1.0e-5):
                raise ValueError("precontact_snapshot_closure_root_not_rigid")
    determinant = (
        matrix[0] * (matrix[5] * matrix[10] - matrix[6] * matrix[9])
        - matrix[1] * (matrix[4] * matrix[10] - matrix[6] * matrix[8])
        + matrix[2] * (matrix[4] * matrix[9] - matrix[5] * matrix[8])
    )
    if not math.isclose(determinant, 1.0, rel_tol=0.0, abs_tol=1.0e-5):
        raise ValueError("precontact_snapshot_closure_root_not_rigid")


def _matmul(left: Sequence[float], right: Sequence[float]) -> list[float]:
    return [
        sum(left[4 * row + column] * right[4 * column + target] for column in range(4))
        for row in range(4)
        for target in range(4)
    ]


def _max_abs_difference(left: Sequence[float], right: Sequence[float]) -> float:
    return max(abs(first - second) for first, second in zip(left, right, strict=True))


def _source_snapshot_contract(value: Any) -> dict[str, Any]:
    expected = {
        "authority",
        "matrix_convention",
        "source_root_path",
        "source_mesh_path",
        "source_wrapper_root_path",
        "expected_external_shell_count",
        "expected_internal_wrapper_count",
        "usd_witness_matrix_atol",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("precontact_snapshot_contract_invalid")
    tolerance = value["usd_witness_matrix_atol"]
    if (
        value["authority"] != SOURCE_CLOSURE_AUTHORITY
        or value["matrix_convention"] != MATRIX_CONVENTION
        or value["source_root_path"] != SOURCE_ROOT_PATH
        or value["source_mesh_path"] != SOURCE_MESH_PATH
        or value["source_wrapper_root_path"] != SOURCE_WRAPPER_ROOT_PATH
        or value["expected_external_shell_count"] != 1
        or value["expected_internal_wrapper_count"] != 145
        or isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(float(tolerance))
        or not 0.0 < float(tolerance) <= 1.0e-3
    ):
        raise ValueError("precontact_snapshot_contract_invalid")
    return {**dict(value), "usd_witness_matrix_atol": float(tolerance)}


def _contract(value: Any) -> dict[str, Any]:
    expected = {
        "authority",
        "classification",
        "schema_version",
        "pre_roll_steps",
        "transition_count",
        "v7_config_sha256",
        "local_scene_sha256",
        "local_franka_sha256",
        "hidden_cube_overlay_sha256",
        "forbidden_operations",
        "source_snapshot",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("precontact_snapshot_contract_invalid")
    contract = dict(value)
    if (
        contract["authority"] != AUTHORITY
        or contract["classification"] != CLASSIFICATION
        or contract["schema_version"] != 2
        or type(contract["pre_roll_steps"]) is not int
        or contract["pre_roll_steps"] <= 0
        or contract["transition_count"] != 6
        or contract["forbidden_operations"]
        != ["close", "attachment", "lift", "contact_observer", "phase3", "gate"]
        or contract["sha256"]
        != canonical_json_sha256({key: item for key, item in contract.items() if key != "sha256"})
    ):
        raise ValueError("precontact_snapshot_contract_invalid")
    for field in (
        "v7_config_sha256",
        "local_scene_sha256",
        "local_franka_sha256",
        "hidden_cube_overlay_sha256",
        "sha256",
    ):
        _sha256(contract[field], field=field)
    contract["source_snapshot"] = _source_snapshot_contract(contract["source_snapshot"])
    return contract


def build_contract(
    *,
    pre_roll_steps: int,
    v7_config_sha256: str,
    local_scene_sha256: str,
    local_franka_sha256: str,
    hidden_cube_overlay_sha256: str,
    usd_witness_matrix_atol: float = 1.0e-4,
) -> dict[str, Any]:
    payload = {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 2,
        "pre_roll_steps": pre_roll_steps,
        "transition_count": 6,
        "v7_config_sha256": v7_config_sha256,
        "local_scene_sha256": local_scene_sha256,
        "local_franka_sha256": local_franka_sha256,
        "hidden_cube_overlay_sha256": hidden_cube_overlay_sha256,
        "forbidden_operations": [
            "close",
            "attachment",
            "lift",
            "contact_observer",
            "phase3",
            "gate",
        ],
        "source_snapshot": {
            "authority": SOURCE_CLOSURE_AUTHORITY,
            "matrix_convention": MATRIX_CONVENTION,
            "source_root_path": SOURCE_ROOT_PATH,
            "source_mesh_path": SOURCE_MESH_PATH,
            "source_wrapper_root_path": SOURCE_WRAPPER_ROOT_PATH,
            "expected_external_shell_count": 1,
            "expected_internal_wrapper_count": 145,
            "usd_witness_matrix_atol": usd_witness_matrix_atol,
        },
    }
    return _contract({**payload, "sha256": canonical_json_sha256(payload)})


def _absolute_path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value == "/"
        or value.endswith("/")
        or "//" in value
    ):
        raise ValueError("precontact_fixed_mount_profile_invalid")
    return value


def _relative_path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("precontact_fixed_mount_profile_invalid")
    return value


def _fixed_mount_profile(value: Any) -> dict[str, Any]:
    expected = {
        "authority",
        "schema_version",
        "profile_id",
        "profile_path",
        "profile_sha256",
        "robot_position_m",
        "filter",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("precontact_fixed_mount_profile_invalid")
    position = _vector(value["robot_position_m"], field="fixed_mount_position", length=3)
    filter_value = value["filter"]
    filter_expected = {
        "overlay_path",
        "overlay_sha256",
        "author_collider_path",
        "target_collider_path",
    }
    if (
        value["authority"] != FIXED_MOUNT_PROFILE_AUTHORITY
        or value["schema_version"] != 1
        or value["profile_id"] != "v7_link0_table_surface_mount_filter_v1"
        or _relative_path(value["profile_path"])
        != "config/formal_precontact_fixed_mount_filter_v1.json"
        or not math.isclose(position[0], -0.4, rel_tol=0.0, abs_tol=1.0e-12)
        or not math.isclose(position[1], 0.0, rel_tol=0.0, abs_tol=1.0e-12)
        or not math.isclose(position[2], 0.772761, rel_tol=0.0, abs_tol=1.0e-12)
        or not isinstance(filter_value, Mapping)
        or set(filter_value) != filter_expected
    ):
        raise ValueError("precontact_fixed_mount_profile_invalid")
    author = _absolute_path(filter_value["author_collider_path"])
    target = _absolute_path(filter_value["target_collider_path"])
    if (
        author != "/World/Franka/panda_link0/geometry/panda_link0"
        or target != "/World/table/surface/mesh"
        or _relative_path(filter_value["overlay_path"])
        != "assets/chemistry_lab/lab_001_fluid_eval/"
        "lab_001_v7_link0_table_fixed_mount_filter_v1.usda"
    ):
        raise ValueError("precontact_fixed_mount_profile_invalid")
    return {
        "authority": FIXED_MOUNT_PROFILE_AUTHORITY,
        "schema_version": 1,
        "profile_id": value["profile_id"],
        "profile_path": value["profile_path"],
        "profile_sha256": _sha256(value["profile_sha256"], field="fixed_mount_profile_sha256"),
        "robot_position_m": position,
        "filter": {
            "overlay_path": filter_value["overlay_path"],
            "overlay_sha256": _sha256(
                filter_value["overlay_sha256"], field="fixed_mount_overlay_sha256"
            ),
            "author_collider_path": author,
            "target_collider_path": target,
        },
    }


def validate_fixed_mount_profile(value: Any) -> dict[str, Any]:
    """Normalize the approved, formal-only link0/table filter profile."""
    return _fixed_mount_profile(value)


def _fixed_mount_contract(value: Any) -> dict[str, Any]:
    expected = {
        "authority",
        "classification",
        "schema_version",
        "pre_roll_steps",
        "transition_count",
        "v7_config_sha256",
        "local_scene_sha256",
        "local_franka_sha256",
        "hidden_cube_overlay_sha256",
        "forbidden_operations",
        "source_snapshot",
        "fixed_mount_profile",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("precontact_fixed_mount_contract_invalid")
    contract = dict(value)
    if (
        contract["authority"] != FIXED_MOUNT_AUTHORITY
        or contract["classification"] != FIXED_MOUNT_CLASSIFICATION
        or contract["schema_version"] != 3
        or type(contract["pre_roll_steps"]) is not int
        or contract["pre_roll_steps"] <= 0
        or contract["transition_count"] != 6
        or contract["forbidden_operations"]
        != ["close", "attachment", "lift", "contact_observer", "phase3", "gate"]
        or contract["sha256"]
        != canonical_json_sha256({key: item for key, item in contract.items() if key != "sha256"})
    ):
        raise ValueError("precontact_fixed_mount_contract_invalid")
    for field in (
        "v7_config_sha256",
        "local_scene_sha256",
        "local_franka_sha256",
        "hidden_cube_overlay_sha256",
        "sha256",
    ):
        _sha256(contract[field], field=field)
    return {
        **contract,
        "source_snapshot": _source_snapshot_contract(contract["source_snapshot"]),
        "fixed_mount_profile": _fixed_mount_profile(contract["fixed_mount_profile"]),
    }


def build_fixed_mount_contract(
    *,
    pre_roll_steps: int,
    v7_config_sha256: str,
    local_scene_sha256: str,
    local_franka_sha256: str,
    hidden_cube_overlay_sha256: str,
    fixed_mount_profile: Mapping[str, Any],
    usd_witness_matrix_atol: float = 1.0e-4,
) -> dict[str, Any]:
    profile = _fixed_mount_profile(fixed_mount_profile)
    payload = {
        "authority": FIXED_MOUNT_AUTHORITY,
        "classification": FIXED_MOUNT_CLASSIFICATION,
        "schema_version": 3,
        "pre_roll_steps": pre_roll_steps,
        "transition_count": 6,
        "v7_config_sha256": v7_config_sha256,
        "local_scene_sha256": local_scene_sha256,
        "local_franka_sha256": local_franka_sha256,
        "hidden_cube_overlay_sha256": hidden_cube_overlay_sha256,
        "forbidden_operations": [
            "close",
            "attachment",
            "lift",
            "contact_observer",
            "phase3",
            "gate",
        ],
        "source_snapshot": {
            "authority": SOURCE_CLOSURE_AUTHORITY,
            "matrix_convention": MATRIX_CONVENTION,
            "source_root_path": SOURCE_ROOT_PATH,
            "source_mesh_path": SOURCE_MESH_PATH,
            "source_wrapper_root_path": SOURCE_WRAPPER_ROOT_PATH,
            "expected_external_shell_count": 1,
            "expected_internal_wrapper_count": 145,
            "usd_witness_matrix_atol": usd_witness_matrix_atol,
        },
        "fixed_mount_profile": profile,
    }
    return _fixed_mount_contract({**payload, "sha256": canonical_json_sha256(payload)})


def _v1_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "authority": replay.AUTHORITY,
        "classification": "FORMAL_PRECONTACT_EVENT0_REPLAY_ONLY",
        "schema_version": 1,
        "pre_roll_steps": contract["pre_roll_steps"],
        "transition_count": contract["transition_count"],
        "v7_config_sha256": contract["v7_config_sha256"],
        "local_scene_sha256": contract["local_scene_sha256"],
        "local_franka_sha256": contract["local_franka_sha256"],
        "hidden_cube_overlay_sha256": contract["hidden_cube_overlay_sha256"],
        "forbidden_operations": contract["forbidden_operations"],
    }
    return {**payload, "sha256": replay.canonical_json_sha256(payload)}


def _v1_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    terminal = trace.get("terminal")
    if not isinstance(terminal, Mapping):
        raise ValueError("precontact_snapshot_trace_invalid")
    expected_terminal = {
        "world_index",
        "event0_action_applied",
        "event0_integrated",
        "close",
        "lift",
        "phase",
        "source_collider_closure",
    }
    if set(terminal) != expected_terminal:
        raise ValueError("precontact_snapshot_trace_invalid")
    return {
        "schema_version": 1,
        "authority": replay.AUTHORITY,
        "pre_roll": trace.get("pre_roll"),
        "transitions": trace.get("transitions"),
        "terminal": {
            key: terminal[key]
            for key in (
                "world_index",
                "event0_action_applied",
                "event0_integrated",
                "close",
                "lift",
                "phase",
            )
        },
    }


def _closure(
    value: Any,
    *,
    snapshot_contract: Mapping[str, Any],
    transition: Mapping[str, Any],
    event0_action_sha256: str,
    resolved_target_sha256: str,
) -> dict[str, Any]:
    expected = {
        "authority",
        "matrix_convention",
        "source_root_path",
        "capture",
        "source_root",
        "colliders",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("precontact_snapshot_closure_invalid")
    closure = dict(value)
    if closure["sha256"] != canonical_json_sha256(
        {key: item for key, item in closure.items() if key != "sha256"}
    ):
        raise ValueError("precontact_snapshot_closure_sha256_invalid")
    _sha256(closure["sha256"], field="closure_sha256")
    if (
        closure["authority"] != snapshot_contract["authority"]
        or closure["matrix_convention"] != snapshot_contract["matrix_convention"]
        or closure["source_root_path"] != snapshot_contract["source_root_path"]
    ):
        raise ValueError("precontact_snapshot_closure_invalid")
    capture = closure["capture"]
    if not isinstance(capture, Mapping) or set(capture) != {
        "transition_index",
        "world_index_after_transition",
        "task_frame_idx",
        "event0_raw_action_sha256",
        "event0_resolved_position_target_sha256",
        "event0_apply_count_at_capture",
        "world_index_after_capture",
    }:
        raise ValueError("precontact_snapshot_closure_capture_invalid")
    if (
        capture["transition_index"] != 5
        or capture["world_index_after_transition"] != transition.get("world_index_after")
        or capture["task_frame_idx"] != transition.get("task_frame_idx")
        or capture["event0_raw_action_sha256"] != event0_action_sha256
        or capture["event0_resolved_position_target_sha256"] != resolved_target_sha256
        or capture["event0_apply_count_at_capture"] != 0
        or capture["world_index_after_capture"] != capture["world_index_after_transition"]
    ):
        raise ValueError("precontact_snapshot_closure_capture_invalid")
    root = closure["source_root"]
    if not isinstance(root, Mapping) or set(root) != {
        "physx_world_matrix_row_major",
        "usd_world_matrix_row_major",
        "linear_velocity_m_s",
        "angular_velocity_rad_s",
    }:
        raise ValueError("precontact_snapshot_closure_root_invalid")
    physx_root = _matrix(root["physx_world_matrix_row_major"], field="physx_root_matrix")
    usd_root = _matrix(root["usd_world_matrix_row_major"], field="usd_root_matrix")
    _rigid_root_matrix(physx_root)
    _rigid_root_matrix(usd_root)
    _vector(root["linear_velocity_m_s"], field="linear_velocity", length=3)
    _vector(root["angular_velocity_rad_s"], field="angular_velocity", length=3)
    tolerance = snapshot_contract["usd_witness_matrix_atol"]
    if _max_abs_difference(physx_root, usd_root) > tolerance:
        raise ValueError("precontact_snapshot_closure_matrix_invalid")
    colliders = closure["colliders"]
    if not isinstance(colliders, list):
        raise ValueError("precontact_snapshot_closure_colliders_invalid")
    normalized = []
    paths = []
    external = 0
    internal = 0
    for collider in colliders:
        if not isinstance(collider, Mapping) or set(collider) != {
            "path",
            "role",
            "collision_enabled",
            "rigid_owner_path",
            "collider_to_source_root_row_major",
            "usd_world_matrix_row_major",
            "composed_world_matrix_row_major",
        }:
            raise ValueError("precontact_snapshot_closure_colliders_invalid")
        path = collider["path"]
        role = collider["role"]
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or collider["collision_enabled"] is not True
            or collider["rigid_owner_path"] != SOURCE_ROOT_PATH
        ):
            raise ValueError("precontact_snapshot_closure_colliders_invalid")
        if role == "external_shell" and path == snapshot_contract["source_mesh_path"]:
            external += 1
        elif (
            role == "internal_wrapper"
            and path.startswith(f"{snapshot_contract['source_wrapper_root_path']}/")
        ):
            internal += 1
        else:
            raise ValueError("precontact_snapshot_closure_colliders_invalid")
        relative = _matrix(
            collider["collider_to_source_root_row_major"], field="collider_relative_matrix"
        )
        usd_world = _matrix(collider["usd_world_matrix_row_major"], field="collider_usd_matrix")
        composed = _matrix(
            collider["composed_world_matrix_row_major"], field="collider_composed_matrix"
        )
        expected_composed = _matmul(relative, physx_root)
        if (
            _max_abs_difference(composed, expected_composed) > tolerance
            or _max_abs_difference(usd_world, composed) > tolerance
        ):
            raise ValueError("precontact_snapshot_closure_matrix_invalid")
        normalized.append(
            {
                "path": path,
                "role": role,
                "collision_enabled": True,
                "rigid_owner_path": SOURCE_ROOT_PATH,
                "collider_to_source_root_row_major": relative,
                "usd_world_matrix_row_major": usd_world,
                "composed_world_matrix_row_major": composed,
            }
        )
        paths.append(path)
    if (
        paths != sorted(paths)
        or len(paths) != len(set(paths))
        or external != snapshot_contract["expected_external_shell_count"]
        or internal != snapshot_contract["expected_internal_wrapper_count"]
    ):
        raise ValueError("precontact_snapshot_closure_colliders_invalid")
    return {
        "authority": closure["authority"],
        "matrix_convention": closure["matrix_convention"],
        "source_root_path": closure["source_root_path"],
        "capture": dict(capture),
        "source_root": {
            "physx_world_matrix_row_major": physx_root,
            "usd_world_matrix_row_major": usd_root,
            "linear_velocity_m_s": _vector(root["linear_velocity_m_s"], field="linear_velocity", length=3),
            "angular_velocity_rad_s": _vector(root["angular_velocity_rad_s"], field="angular_velocity", length=3),
        },
        "colliders": normalized,
        "sha256": closure["sha256"],
    }


def _evaluate(trace: Any, contract: Any) -> dict[str, Any]:
    normalized_contract = _contract(contract)
    if not isinstance(trace, Mapping) or set(trace) != {
        "schema_version",
        "authority",
        "pre_roll",
        "transitions",
        "terminal",
    }:
        raise ValueError("precontact_snapshot_trace_invalid")
    if trace["schema_version"] != 2 or trace["authority"] != AUTHORITY:
        raise ValueError("precontact_snapshot_trace_invalid")
    base_trace = _v1_trace(trace)
    base_evaluation = replay.evaluate_precontact_event0_replay(
        base_trace, _v1_contract(normalized_contract)
    )
    if base_evaluation["decision"] == SAFETY_ABORT:
        raise ValueError(base_evaluation["validation_error"])
    transitions = trace["transitions"]
    if not isinstance(transitions, list) or len(transitions) != 6:
        raise ValueError("precontact_snapshot_trace_invalid")
    event0 = transitions[5]
    if not isinstance(event0, Mapping) or not isinstance(event0.get("raw_action_sha256"), str):
        raise ValueError("precontact_snapshot_trace_invalid")
    closure = _closure(
        trace["terminal"]["source_collider_closure"],
        snapshot_contract=normalized_contract["source_snapshot"],
        transition=event0,
        event0_action_sha256=base_evaluation["event0_raw_action_sha256"],
        resolved_target_sha256=base_evaluation["event0_resolved_position_target_sha256"],
    )
    return {
        **base_evaluation,
        "source_collider_closure_sha256": closure["sha256"],
        "source_collider_count": len(closure["colliders"]),
        "source_matrix_convention": closure["matrix_convention"],
    }


def _fixed_mount_v2_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 2,
        "pre_roll_steps": contract["pre_roll_steps"],
        "transition_count": contract["transition_count"],
        "v7_config_sha256": contract["v7_config_sha256"],
        "local_scene_sha256": contract["local_scene_sha256"],
        "local_franka_sha256": contract["local_franka_sha256"],
        "hidden_cube_overlay_sha256": contract["hidden_cube_overlay_sha256"],
        "forbidden_operations": contract["forbidden_operations"],
        "source_snapshot": contract["source_snapshot"],
    }
    return _contract({**payload, "sha256": canonical_json_sha256(payload)})


def _fixed_mount_filter_record(value: Any, *, profile: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "authority",
        "profile_sha256",
        "author_collider_path",
        "target_collider_path",
        "filtered_pair",
        "authored_filtered_pair_paths",
        "robot_filtered_pair_paths",
        "collision_group_membership_paths",
    }
    filter_profile = profile["filter"]
    author = filter_profile["author_collider_path"]
    target = filter_profile["target_collider_path"]
    pair = sorted([author, target])
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value["authority"] != FIXED_MOUNT_RUNTIME_FILTER_AUTHORITY
        or value["profile_sha256"] != profile["profile_sha256"]
        or value["author_collider_path"] != author
        or value["target_collider_path"] != target
        or value["filtered_pair"] != pair
        or value["authored_filtered_pair_paths"] != [[author, target]]
        or value["robot_filtered_pair_paths"] != [[author, target]]
        or value["collision_group_membership_paths"] != []
    ):
        raise ValueError("precontact_fixed_mount_filter_invalid")
    return {
        "authority": FIXED_MOUNT_RUNTIME_FILTER_AUTHORITY,
        "profile_sha256": profile["profile_sha256"],
        "author_collider_path": author,
        "target_collider_path": target,
        "filtered_pair": pair,
        "authored_filtered_pair_paths": [[author, target]],
        "robot_filtered_pair_paths": [[author, target]],
        "collision_group_membership_paths": [],
    }


def validate_fixed_mount_filter_record(
    value: Any, *, fixed_mount_profile: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate the exact runtime relation approved by a fixed-mount profile."""
    return _fixed_mount_filter_record(
        value, profile=_fixed_mount_profile(fixed_mount_profile)
    )


def _evaluate_fixed_mount(trace: Any, contract: Any) -> dict[str, Any]:
    normalized_contract = _fixed_mount_contract(contract)
    expected_trace = {"schema_version", "authority", "pre_roll", "transitions", "terminal"}
    if (
        not isinstance(trace, Mapping)
        or set(trace) != expected_trace
        or trace["schema_version"] != 3
        or trace["authority"] != FIXED_MOUNT_AUTHORITY
        or not isinstance(trace["terminal"], Mapping)
    ):
        raise ValueError("precontact_fixed_mount_trace_invalid")
    expected_terminal = {
        "world_index",
        "event0_action_applied",
        "event0_integrated",
        "close",
        "lift",
        "phase",
        "source_collider_closure",
        "fixed_mount_filter",
    }
    if set(trace["terminal"]) != expected_terminal:
        raise ValueError("precontact_fixed_mount_trace_invalid")
    filter_record = _fixed_mount_filter_record(
        trace["terminal"]["fixed_mount_filter"],
        profile=normalized_contract["fixed_mount_profile"],
    )
    base_trace = {
        "schema_version": 2,
        "authority": AUTHORITY,
        "pre_roll": trace["pre_roll"],
        "transitions": trace["transitions"],
        "terminal": {
            key: trace["terminal"][key]
            for key in (
                "world_index",
                "event0_action_applied",
                "event0_integrated",
                "close",
                "lift",
                "phase",
                "source_collider_closure",
            )
        },
    }
    base_evaluation = _evaluate(base_trace, _fixed_mount_v2_contract(normalized_contract))
    return {
        **base_evaluation,
        "fixed_mount_profile_sha256": normalized_contract["fixed_mount_profile"]["profile_sha256"],
        "fixed_mount_filtered_pair": filter_record["filtered_pair"],
    }


def evaluate_precontact_event0_snapshot_replay(trace: Any, contract: Any) -> dict[str, Any]:
    try:
        if isinstance(contract, Mapping) and contract.get("authority") == FIXED_MOUNT_AUTHORITY:
            return _evaluate_fixed_mount(trace, contract)
        return _evaluate(trace, contract)
    except ValueError as exc:
        return {"decision": SAFETY_ABORT, "validation_error": str(exc)}


def validate_contract(value: Any) -> dict[str, Any]:
    """Normalize a v2 snapshot or v3 fixed-mount snapshot contract."""
    if isinstance(value, Mapping) and value.get("authority") == FIXED_MOUNT_AUTHORITY:
        return _fixed_mount_contract(value)
    return _contract(value)


def validate_source_collider_closure(
    value: Any,
    *,
    contract: Mapping[str, Any],
    transition_index: int,
    world_index_after_transition: int,
    task_frame_idx: int,
    event0_action_sha256: str,
    resolved_target_sha256: str,
) -> dict[str, Any]:
    """Validate a closure independently of the full six-transition trace."""
    normalized_contract = validate_contract(contract)
    return _closure(
        value,
        snapshot_contract=normalized_contract["source_snapshot"],
        transition={
            "world_index_after": world_index_after_transition,
            "task_frame_idx": task_frame_idx,
        },
        event0_action_sha256=event0_action_sha256,
        resolved_target_sha256=resolved_target_sha256,
    )
