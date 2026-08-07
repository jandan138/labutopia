"""Pure contracts for a no-step static projection of a formal event-0 snapshot."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from utils import formal_precontact_event0_replay as replay
from utils import formal_precontact_event0_snapshot_replay as snapshot
from utils import formal_precontact_usd_dependency_closure as dependency_closure


HANDOFF_AUTHORITY = "formal_precontact_snapshot_static_handoff_v1"
PROJECTION_AUTHORITY = "formal_precontact_event0_static_projection_v1"
BASELINE_COMPARISON_AUTHORITY = "formal_precontact_fixed_mount_baseline_comparison_v1"
CLEAR = "FORMAL_EVENT0_STATIC_CLEAR_DIAGNOSTIC_ONLY"
NO_GO = "FORMAL_EVENT0_STATIC_POTENTIAL_COLLISION_NO_GO"
SAFETY_ABORT = "FORMAL_EVENT0_STATIC_PROJECTION_INVALID"
BASELINE_FIXED_MOUNT = "FORMAL_EVENT0_STATIC_BASELINE_FIXED_MOUNT_POTENTIAL_OVERLAP"
BASELINE_FIXED_MOUNT_SURFACE_TOUCH = "FORMAL_EVENT0_STATIC_BASELINE_FIXED_MOUNT_SURFACE_TOUCH"
BASELINE_FIXED_MOUNT_VOLUMETRIC_OVERLAP = "FORMAL_EVENT0_STATIC_BASELINE_FIXED_MOUNT_VOLUMETRIC_OVERLAP"
BASELINE_FIXED_MOUNT_AMBIGUOUS = "FORMAL_EVENT0_STATIC_BASELINE_FIXED_MOUNT_AMBIGUOUS"
BASELINE_TARGET_DEPENDENT = "FORMAL_EVENT0_STATIC_TARGET_DEPENDENT_POTENTIAL_OVERLAP"
BASELINE_CLEAR = "FORMAL_EVENT0_STATIC_BASELINE_CLEAR"
FIXED_MOUNT_FILTERED_SCOPE_AUTHORITY = "formal_precontact_fixed_mount_filtered_scope_v1"
LINK0_TABLE_GEOMETRY_AUDIT_AUTHORITY = "formal_precontact_link0_table_geometry_audit_v1"
LINK0_TABLE_GEOMETRY_UNRESOLVED = "FORMAL_EVENT0_STATIC_LINK0_TABLE_GEOMETRY_UNRESOLVED"
LINK0_TABLE_MOUNTING_ALIGNMENT_AUTHORITY = "formal_precontact_link0_table_mounting_alignment_v1"
LINK0_TABLE_MOUNTING_EMBEDDED = "FORMAL_EVENT0_STATIC_LINK0_TABLE_AUTHORED_MESH_EMBEDDED"
LINK0_TABLE_MOUNTING_SURFACE_TOUCH = "FORMAL_EVENT0_STATIC_LINK0_TABLE_AUTHORED_MESH_SURFACE_TOUCH"
LINK0_TABLE_MOUNTING_INSUFFICIENT_CLEARANCE = "FORMAL_EVENT0_STATIC_LINK0_TABLE_AUTHORED_MESH_INSUFFICIENT_CLEARANCE"
LINK0_TABLE_MOUNTING_CLEAR = "FORMAL_EVENT0_STATIC_LINK0_TABLE_AUTHORED_MESH_CLEAR"
LINK0_COLLIDER_PATH = "/World/Franka/panda_link0/geometry/panda_link0"
TABLE_COLLIDER_PATH = "/World/table/surface/mesh"


def canonical_json_sha256(value: Any) -> str:
    return replay.canonical_json_sha256(value)


def _sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"formal_snapshot_static_{field}_invalid")
    return value


def _vector(value: Any, *, field: str, length: int) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != length:
        raise ValueError(f"formal_snapshot_static_{field}_invalid")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"formal_snapshot_static_{field}_invalid")
        numeric = float(item)
        if not math.isfinite(numeric):
            raise ValueError(f"formal_snapshot_static_{field}_invalid")
        result.append(numeric)
    return result


def _absolute_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("/")
        and value != "/"
        and not value.endswith("/")
        and "//" not in value
    )


def _pair(value: Any, *, field: str) -> tuple[str, str]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(not _absolute_path(path) for path in value)
        or value[0] >= value[1]
    ):
        raise ValueError(f"formal_snapshot_static_{field}_invalid")
    return value[0], value[1]


def _scope(value: Any) -> dict[str, list[list[str]]]:
    if not isinstance(value, Mapping) or set(value) != {
        "blocking_pairs",
        "allowed_source_shell_pairs",
    }:
        raise ValueError("formal_snapshot_static_scope_invalid")
    result: dict[str, list[list[str]]] = {}
    observed: set[tuple[str, str]] = set()
    for field in ("blocking_pairs", "allowed_source_shell_pairs"):
        pairs = value[field]
        if not isinstance(pairs, list) or not pairs:
            raise ValueError("formal_snapshot_static_scope_invalid")
        normalized = [_pair(pair, field=field) for pair in pairs]
        if len(normalized) != len(set(normalized)) or observed.intersection(normalized):
            raise ValueError("formal_snapshot_static_scope_invalid")
        observed.update(normalized)
        result[field] = [list(pair) for pair in sorted(normalized)]
    return result


def build_fixed_mount_filtered_screen_scope(
    full_scope: Any,
    *,
    fixed_mount_profile: Mapping[str, Any],
    fixed_mount_filter: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve the full matrix while excluding only the approved mounted pair."""
    normalized_scope = _scope(full_scope)
    profile = snapshot.validate_fixed_mount_profile(fixed_mount_profile)
    filter_record = snapshot.validate_fixed_mount_filter_record(
        fixed_mount_filter, fixed_mount_profile=profile
    )
    excluded_pair = tuple(filter_record["filtered_pair"])
    blocking = [tuple(pair) for pair in normalized_scope["blocking_pairs"]]
    if excluded_pair not in blocking:
        raise ValueError("formal_snapshot_static_fixed_mount_pair_not_blocking")
    active_blocking = [list(pair) for pair in blocking if pair != excluded_pair]
    payload = {
        "schema_version": 1,
        "authority": FIXED_MOUNT_FILTERED_SCOPE_AUTHORITY,
        "full_scope_sha256": canonical_json_sha256(normalized_scope),
        "fixed_mount_profile_sha256": profile["profile_sha256"],
        "fixed_mount_filter_record_sha256": canonical_json_sha256(filter_record),
        "excluded_blocking_pairs": [list(excluded_pair)],
        "full_blocking_pair_count": len(blocking),
        "active_blocking_pair_count": len(active_blocking),
        "blocking_pairs": active_blocking,
        "allowed_source_shell_pairs": normalized_scope["allowed_source_shell_pairs"],
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def _event0_action(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "joint_positions",
        "joint_velocities",
        "joint_efforts",
        "joint_indices",
    }:
        raise ValueError("formal_snapshot_static_event0_action_invalid")
    positions = _vector(value["joint_positions"], field="event0_positions", length=7)
    velocities = _vector(value["joint_velocities"], field="event0_velocities", length=7)
    if value["joint_efforts"] is not None or value["joint_indices"] != list(range(7)):
        raise ValueError("formal_snapshot_static_event0_action_invalid")
    return {
        "joint_positions": positions,
        "joint_velocities": velocities,
        "joint_efforts": None,
        "joint_indices": list(range(7)),
    }


def _formal_provenance(
    value: Any,
    *,
    trace: Mapping[str, Any] | None = None,
    fixed_mount: bool = False,
) -> dict[str, Any]:
    expected = {
        "formal_decision",
        "report_sha256",
        "manifest_sha256",
        "child_report_sha256",
        "runtime_receipt_sha256",
        "execution_request_sha256",
        "trace_sha256",
        "source_sha256",
    }
    if fixed_mount:
        expected.add("usd_dependency_preflight")
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("formal_snapshot_static_provenance_invalid")
    if value["formal_decision"] != snapshot.PASS:
        raise ValueError("formal_snapshot_static_provenance_invalid")
    result = dict(value)
    for field in expected - {"formal_decision", "usd_dependency_preflight"}:
        _sha256(result[field], field=field)
    if fixed_mount:
        result["usd_dependency_preflight"] = dependency_closure.validate_preflight_binding(
            result["usd_dependency_preflight"]
        )
    if trace is not None and result["trace_sha256"] != canonical_json_sha256(trace):
        raise ValueError("formal_snapshot_static_provenance_invalid")
    return result


def _event0_handoff(value: Any, *, closure: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "transition_index",
        "world_index_after_transition",
        "task_frame_idx",
        "raw_action",
        "raw_action_sha256",
        "joint_positions_before_action",
        "joint_velocities_before_action",
        "joint_lower_limits",
        "joint_upper_limits",
        "resolved_position_target",
        "resolved_position_target_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("formal_snapshot_static_event0_invalid")
    action = _event0_action(value["raw_action"])
    if (
        value["transition_index"] != 5
        or type(value["world_index_after_transition"]) is not int
        or value["world_index_after_transition"] < 0
        or value["task_frame_idx"] != 6
        or value["raw_action_sha256"] != canonical_json_sha256(action)
    ):
        raise ValueError("formal_snapshot_static_event0_invalid")
    before = _vector(value["joint_positions_before_action"], field="joint_positions_before", length=9)
    velocities = _vector(value["joint_velocities_before_action"], field="joint_velocities_before", length=9)
    lower = _vector(value["joint_lower_limits"], field="joint_lower", length=9)
    upper = _vector(value["joint_upper_limits"], field="joint_upper", length=9)
    target = _vector(value["resolved_position_target"], field="resolved_target", length=9)
    if any(left >= right for left, right in zip(lower, upper, strict=True)):
        raise ValueError("formal_snapshot_static_event0_invalid")
    expected_target = list(before)
    for index, position in zip(action["joint_indices"], action["joint_positions"], strict=True):
        expected_target[index] = position
    if (
        any(
            not math.isclose(observed, expected, rel_tol=0.0, abs_tol=1.0e-12)
            for observed, expected in zip(target, expected_target, strict=True)
        )
        or value["resolved_position_target_sha256"] != canonical_json_sha256(target)
        or any(position < low or position > high for position, low, high in zip(target, lower, upper, strict=True))
        or closure["capture"]["transition_index"] != value["transition_index"]
        or closure["capture"]["world_index_after_transition"]
        != value["world_index_after_transition"]
        or closure["capture"]["task_frame_idx"] != value["task_frame_idx"]
        or closure["capture"]["event0_raw_action_sha256"] != value["raw_action_sha256"]
        or closure["capture"]["event0_resolved_position_target_sha256"]
        != value["resolved_position_target_sha256"]
    ):
        raise ValueError("formal_snapshot_static_event0_invalid")
    return {
        "transition_index": 5,
        "world_index_after_transition": value["world_index_after_transition"],
        "task_frame_idx": 6,
        "raw_action": action,
        "raw_action_sha256": value["raw_action_sha256"],
        "joint_positions_before_action": before,
        "joint_velocities_before_action": velocities,
        "joint_lower_limits": lower,
        "joint_upper_limits": upper,
        "resolved_position_target": target,
        "resolved_position_target_sha256": value["resolved_position_target_sha256"],
    }


def normalize_static_handoff(value: Any) -> dict[str, Any]:
    base_expected = {
        "authority",
        "schema_version",
        "formal_contract",
        "formal_contract_sha256",
        "formal_provenance",
        "event0",
        "source_collider_closure",
        "sha256",
    }
    if (
        not isinstance(value, Mapping)
        or not isinstance(value.get("formal_contract"), Mapping)
    ):
        raise ValueError("formal_snapshot_static_handoff_invalid")
    handoff = dict(value)
    contract = snapshot.validate_contract(handoff["formal_contract"])
    fixed_mount = contract["authority"] == snapshot.FIXED_MOUNT_AUTHORITY
    expected = set(base_expected)
    if fixed_mount:
        expected.add("fixed_mount_filter")
    if set(handoff) != expected:
        raise ValueError("formal_snapshot_static_handoff_invalid")
    if (
        handoff["authority"] != HANDOFF_AUTHORITY
        or handoff["schema_version"] != 1
        or handoff["sha256"]
        != canonical_json_sha256({key: item for key, item in handoff.items() if key != "sha256"})
    ):
        raise ValueError("formal_snapshot_static_handoff_invalid")
    _sha256(handoff["sha256"], field="handoff_sha256")
    if handoff["formal_contract_sha256"] != contract["sha256"]:
        raise ValueError("formal_snapshot_static_handoff_invalid")
    provenance = _formal_provenance(
        handoff["formal_provenance"], fixed_mount=fixed_mount
    )
    provisional_event = handoff["event0"]
    if not isinstance(provisional_event, Mapping):
        raise ValueError("formal_snapshot_static_event0_invalid")
    closure = snapshot.validate_source_collider_closure(
        handoff["source_collider_closure"],
        contract=contract,
        transition_index=provisional_event.get("transition_index"),
        world_index_after_transition=provisional_event.get("world_index_after_transition"),
        task_frame_idx=provisional_event.get("task_frame_idx"),
        event0_action_sha256=provisional_event.get("raw_action_sha256"),
        resolved_target_sha256=provisional_event.get("resolved_position_target_sha256"),
    )
    event0 = _event0_handoff(provisional_event, closure=closure)
    normalized = {
        "authority": HANDOFF_AUTHORITY,
        "schema_version": 1,
        "formal_contract": contract,
        "formal_contract_sha256": contract["sha256"],
        "formal_provenance": provenance,
        "event0": event0,
        "source_collider_closure": closure,
        "sha256": handoff["sha256"],
    }
    if fixed_mount:
        normalized["fixed_mount_filter"] = snapshot.validate_fixed_mount_filter_record(
            handoff["fixed_mount_filter"],
            fixed_mount_profile=contract["fixed_mount_profile"],
        )
    return normalized


def build_static_handoff(
    *,
    formal_contract: Mapping[str, Any],
    formal_trace: Mapping[str, Any],
    formal_evaluation: Mapping[str, Any],
    formal_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    contract = snapshot.validate_contract(formal_contract)
    evaluation = snapshot.evaluate_precontact_event0_snapshot_replay(
        formal_trace, formal_contract
    )
    if evaluation != dict(formal_evaluation) or evaluation.get("decision") != snapshot.PASS:
        raise ValueError("formal_snapshot_static_formal_evidence_invalid")
    if not isinstance(formal_trace.get("transitions"), list) or len(formal_trace["transitions"]) != 6:
        raise ValueError("formal_snapshot_static_formal_evidence_invalid")
    event0 = formal_trace["transitions"][5]
    if not isinstance(event0, Mapping):
        raise ValueError("formal_snapshot_static_formal_evidence_invalid")
    provenance = _formal_provenance(
        formal_provenance,
        trace=formal_trace,
        fixed_mount=contract["authority"] == snapshot.FIXED_MOUNT_AUTHORITY,
    )
    payload = {
        "authority": HANDOFF_AUTHORITY,
        "schema_version": 1,
        "formal_contract": contract,
        "formal_contract_sha256": contract.get("sha256"),
        "formal_provenance": provenance,
        "event0": {
            "transition_index": event0.get("transition_index"),
            "world_index_after_transition": event0.get("world_index_after"),
            "task_frame_idx": event0.get("task_frame_idx"),
            "raw_action": event0.get("raw_action"),
            "raw_action_sha256": event0.get("raw_action_sha256"),
            "joint_positions_before_action": event0.get("joint_positions_before_action"),
            "joint_velocities_before_action": event0.get("joint_velocities_before_action"),
            "joint_lower_limits": event0.get("joint_lower_limits"),
            "joint_upper_limits": event0.get("joint_upper_limits"),
            "resolved_position_target": evaluation.get("event0_resolved_position_target"),
            "resolved_position_target_sha256": evaluation.get(
                "event0_resolved_position_target_sha256"
            ),
        },
        "source_collider_closure": formal_trace["terminal"].get("source_collider_closure"),
    }
    if contract["authority"] == snapshot.FIXED_MOUNT_AUTHORITY:
        payload["fixed_mount_filter"] = snapshot.validate_fixed_mount_filter_record(
            formal_trace["terminal"].get("fixed_mount_filter"),
            fixed_mount_profile=contract["fixed_mount_profile"],
        )
    return normalize_static_handoff(
        {**payload, "sha256": canonical_json_sha256(payload)}
    )


def _pair_result(
    value: Any,
    *,
    blocking: set[tuple[str, str]],
    allowed: set[tuple[str, str]],
) -> tuple[tuple[str, str], str, float]:
    if not isinstance(value, Mapping) or set(value) != {
        "pair",
        "classification",
        "status",
        "lower_bound_m",
    }:
        raise ValueError("formal_snapshot_static_pair_result_invalid")
    pair = _pair(value["pair"], field="pair_result")
    expected_classification = (
        "BLOCKING" if pair in blocking else "ALLOWED_SOURCE_SHELL_FINGER" if pair in allowed else None
    )
    lower = value["lower_bound_m"]
    if (
        value["classification"] != expected_classification
        or value["status"] not in {"CLEAR", "POTENTIAL_OVERLAP_OR_MARGIN"}
        or isinstance(lower, bool)
        or not isinstance(lower, (int, float))
        or not math.isfinite(float(lower))
        or float(lower) < 0.0
    ):
        raise ValueError("formal_snapshot_static_pair_result_invalid")
    return pair, value["status"], float(lower)


def _evaluate_projection(scope: Any, projection: Any) -> dict[str, Any]:
    normalized_scope = _scope(scope)
    expected = {
        "schema_version",
        "authority",
        "controller_event",
        "resolved_position_target",
        "resolved_position_target_sha256",
        "source_collider_closure_sha256",
        "aabb_numerical_margin_m",
        "pair_results",
    }
    if not isinstance(projection, Mapping) or set(projection) != expected:
        raise ValueError("formal_snapshot_static_projection_invalid")
    target = _vector(projection["resolved_position_target"], field="projection_target", length=9)
    margin = projection["aabb_numerical_margin_m"]
    if (
        projection["schema_version"] != 1
        or projection["authority"] != PROJECTION_AUTHORITY
        or projection["controller_event"] != 0
        or projection["resolved_position_target_sha256"] != canonical_json_sha256(target)
        or isinstance(margin, bool)
        or not isinstance(margin, (int, float))
        or not math.isfinite(float(margin))
        or float(margin) < 0.0
    ):
        raise ValueError("formal_snapshot_static_projection_invalid")
    _sha256(projection["source_collider_closure_sha256"], field="projection_closure_sha256")
    blocking = {tuple(pair) for pair in normalized_scope["blocking_pairs"]}
    allowed = {tuple(pair) for pair in normalized_scope["allowed_source_shell_pairs"]}
    required = blocking | allowed
    pairs = projection["pair_results"]
    if not isinstance(pairs, list):
        raise ValueError("formal_snapshot_static_projection_invalid")
    observed: dict[tuple[str, str], tuple[str, float]] = {}
    for value in pairs:
        pair, status, lower = _pair_result(value, blocking=blocking, allowed=allowed)
        if pair in observed:
            raise ValueError("formal_snapshot_static_projection_invalid")
        observed[pair] = status, lower
    if set(observed) != required:
        raise ValueError("formal_snapshot_static_projection_invalid")
    for status, lower in observed.values():
        expected_status = "CLEAR" if lower > float(margin) else "POTENTIAL_OVERLAP_OR_MARGIN"
        if status != expected_status:
            raise ValueError("formal_snapshot_static_projection_invalid")
    potential = [
        {
            "pair": list(pair),
            "classification": "BLOCKING" if pair in blocking else "ALLOWED_SOURCE_SHELL_FINGER",
            "status": status,
            "lower_bound_m": lower,
        }
        for pair, (status, lower) in sorted(observed.items())
        if status != "CLEAR"
    ]
    return {
        "decision": CLEAR if not potential else NO_GO,
        "required_pair_count": len(required),
        "screened_pair_result_count": len(observed),
        "potential_pair_result_count": len(potential),
        "first_potential_pair_result": potential[0] if potential else None,
        "resolved_position_target_sha256": projection["resolved_position_target_sha256"],
        "source_collider_closure_sha256": projection["source_collider_closure_sha256"],
        "aabb_numerical_margin_m": float(margin),
        "scope_sha256": canonical_json_sha256(normalized_scope),
    }


def evaluate_event0_static_projection(scope: Any, projection: Any) -> dict[str, Any]:
    try:
        return _evaluate_projection(scope, projection)
    except ValueError as exc:
        return {"decision": SAFETY_ABORT, "validation_error": str(exc)}


def _affine_matrix(value: Any, *, field: str) -> list[float]:
    matrix = _vector(value, field=field, length=16)
    if (
        any(abs(matrix[index]) > 1.0e-12 for index in (3, 7, 11))
        or not math.isclose(matrix[15], 1.0, rel_tol=0.0, abs_tol=1.0e-12)
    ):
        raise ValueError("formal_snapshot_static_baseline_matrix_invalid")
    return matrix


def _evaluate_fixed_mount_baseline_comparison(value: Any) -> dict[str, Any]:
    expected = {
        "schema_version",
        "authority",
        "pair",
        "aabb_numerical_margin_m",
        "baseline_lower_bound_m",
        "event0_lower_bound_m",
        "axis_signed_separation_m",
        "baseline_link0_collider_world_matrix",
        "event0_link0_collider_world_matrix",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("formal_snapshot_static_baseline_invalid")
    margin = value["aabb_numerical_margin_m"]
    baseline_lower = value["baseline_lower_bound_m"]
    event0_lower = value["event0_lower_bound_m"]
    expected_pair = tuple(sorted((LINK0_COLLIDER_PATH, TABLE_COLLIDER_PATH)))
    if (
        value["schema_version"] != 1
        or value["authority"] != BASELINE_COMPARISON_AUTHORITY
        or _pair(value["pair"], field="baseline_pair") != expected_pair
        or isinstance(margin, bool)
        or not isinstance(margin, (int, float))
        or not math.isfinite(float(margin))
        or float(margin) < 0.0
        or isinstance(baseline_lower, bool)
        or not isinstance(baseline_lower, (int, float))
        or not math.isfinite(float(baseline_lower))
        or float(baseline_lower) < 0.0
        or isinstance(event0_lower, bool)
        or not isinstance(event0_lower, (int, float))
        or not math.isfinite(float(event0_lower))
        or float(event0_lower) < 0.0
    ):
        raise ValueError("formal_snapshot_static_baseline_invalid")
    baseline_matrix = _affine_matrix(
        value["baseline_link0_collider_world_matrix"], field="baseline_link0_matrix"
    )
    event0_matrix = _affine_matrix(
        value["event0_link0_collider_world_matrix"], field="event0_link0_matrix"
    )
    max_difference = max(
        abs(first - second)
        for first, second in zip(baseline_matrix, event0_matrix, strict=True)
    )
    baseline_potential = float(baseline_lower) <= float(margin)
    event0_potential = float(event0_lower) <= float(margin)
    axis_signed_separation = _vector(
        value["axis_signed_separation_m"], field="axis_signed_separation", length=3
    )
    positive_norm = math.sqrt(
        sum(max(0.0, gap) * max(0.0, gap) for gap in axis_signed_separation)
    )
    if not math.isclose(
        positive_norm, float(baseline_lower), rel_tol=0.0, abs_tol=1.0e-10
    ):
        raise ValueError("formal_snapshot_static_baseline_invalid")
    if baseline_potential and event0_potential and max_difference <= 1.0e-10:
        touching_axes = [
            index
            for index, gap in enumerate(axis_signed_separation)
            if abs(gap) <= float(margin)
        ]
        penetrating_axes = [
            index
            for index, gap in enumerate(axis_signed_separation)
            if gap < -float(margin)
        ]
        if len(touching_axes) == 1 and len(penetrating_axes) == 2:
            decision = BASELINE_FIXED_MOUNT_SURFACE_TOUCH
        elif len(penetrating_axes) == 3:
            decision = BASELINE_FIXED_MOUNT_VOLUMETRIC_OVERLAP
        else:
            decision = BASELINE_FIXED_MOUNT_AMBIGUOUS
    elif not baseline_potential and event0_potential:
        decision = BASELINE_TARGET_DEPENDENT
    elif not baseline_potential and not event0_potential:
        decision = BASELINE_CLEAR
    else:
        decision = BASELINE_TARGET_DEPENDENT
    return {
        "decision": decision,
        "pair": list(expected_pair),
        "aabb_numerical_margin_m": float(margin),
        "baseline_lower_bound_m": float(baseline_lower),
        "event0_lower_bound_m": float(event0_lower),
        "axis_signed_separation_m": axis_signed_separation,
        "link0_matrix_max_abs_difference": max_difference,
        "baseline_status": (
            "POTENTIAL_OVERLAP_OR_MARGIN" if baseline_potential else "CLEAR"
        ),
        "event0_status": "POTENTIAL_OVERLAP_OR_MARGIN" if event0_potential else "CLEAR",
    }


def evaluate_fixed_mount_baseline_comparison(value: Any) -> dict[str, Any]:
    try:
        return _evaluate_fixed_mount_baseline_comparison(value)
    except ValueError as exc:
        return {"decision": SAFETY_ABORT, "validation_error": str(exc)}


def _nonnegative_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"formal_snapshot_static_{field}_invalid")
    return value


def _nonnegative_float(value: Any, *, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"formal_snapshot_static_{field}_invalid")
    return float(value)


def _geometry_audit_collider(value: Any, *, expected_path: str) -> dict[str, Any]:
    expected = {
        "path",
        "type_name",
        "collision_enabled",
        "mesh_collision_api_applied",
        "physics_approximation",
        "mesh_point_count",
        "mesh_triangle_count",
        "cooked_aabb_local_min_m",
        "cooked_aabb_local_max_m",
        "cooked_volume_m3",
        "cooked_aabb_volume_m3",
        "world_aabb_min_m",
        "world_aabb_max_m",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("formal_snapshot_static_geometry_audit_collider_invalid")
    type_name = value["type_name"]
    approximation = value["physics_approximation"]
    if (
        value["path"] != expected_path
        or not isinstance(type_name, str)
        or not type_name
        or value["collision_enabled"] is not True
        or not isinstance(value["mesh_collision_api_applied"], bool)
        or (approximation is not None and (not isinstance(approximation, str) or not approximation))
    ):
        raise ValueError("formal_snapshot_static_geometry_audit_collider_invalid")
    local_min = _vector(value["cooked_aabb_local_min_m"], field="geometry_audit_local_min", length=3)
    local_max = _vector(value["cooked_aabb_local_max_m"], field="geometry_audit_local_max", length=3)
    world_min = _vector(value["world_aabb_min_m"], field="geometry_audit_world_min", length=3)
    world_max = _vector(value["world_aabb_max_m"], field="geometry_audit_world_max", length=3)
    if any(high < low for low, high in zip(local_min, local_max, strict=True)) or any(
        high < low for low, high in zip(world_min, world_max, strict=True)
    ):
        raise ValueError("formal_snapshot_static_geometry_audit_collider_invalid")
    volume = _nonnegative_float(value["cooked_volume_m3"], field="geometry_audit_volume")
    aabb_volume = _nonnegative_float(
        value["cooked_aabb_volume_m3"], field="geometry_audit_aabb_volume"
    )
    expected_aabb_volume = math.prod(high - low for low, high in zip(local_min, local_max, strict=True))
    if not math.isclose(aabb_volume, expected_aabb_volume, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("formal_snapshot_static_geometry_audit_collider_invalid")
    return {
        "path": expected_path,
        "type_name": type_name,
        "collision_enabled": True,
        "mesh_collision_api_applied": value["mesh_collision_api_applied"],
        "physics_approximation": approximation,
        "mesh_point_count": _nonnegative_integer(
            value["mesh_point_count"], field="geometry_audit_mesh_points"
        ),
        "mesh_triangle_count": _nonnegative_integer(
            value["mesh_triangle_count"], field="geometry_audit_mesh_triangles"
        ),
        "cooked_aabb_local_min_m": local_min,
        "cooked_aabb_local_max_m": local_max,
        "cooked_volume_m3": volume,
        "cooked_aabb_volume_m3": aabb_volume,
        "world_aabb_min_m": world_min,
        "world_aabb_max_m": world_max,
    }


def _evaluate_link0_table_geometry_audit(value: Any) -> dict[str, Any]:
    expected = {
        "schema_version",
        "authority",
        "pair",
        "authored_filtered_pair_paths",
        "colliders",
    }
    expected_pair = tuple(sorted((LINK0_COLLIDER_PATH, TABLE_COLLIDER_PATH)))
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value["schema_version"] != 1
        or value["authority"] != LINK0_TABLE_GEOMETRY_AUDIT_AUTHORITY
        or _pair(value["pair"], field="geometry_audit_pair") != expected_pair
        or not isinstance(value["colliders"], list)
        or len(value["colliders"]) != len(expected_pair)
        or not isinstance(value["authored_filtered_pair_paths"], list)
    ):
        raise ValueError("formal_snapshot_static_geometry_audit_invalid")
    colliders = [
        _geometry_audit_collider(collider, expected_path=path)
        for collider, path in zip(value["colliders"], expected_pair, strict=True)
    ]
    filtered_pairs = [
        _pair(pair, field="geometry_audit_filtered_pair")
        for pair in value["authored_filtered_pair_paths"]
    ]
    if filtered_pairs != sorted(filtered_pairs) or len(filtered_pairs) != len(set(filtered_pairs)):
        raise ValueError("formal_snapshot_static_geometry_audit_invalid")
    if [collider["path"] for collider in colliders] != list(expected_pair):
        raise ValueError("formal_snapshot_static_geometry_audit_invalid")
    return {
        "decision": LINK0_TABLE_GEOMETRY_UNRESOLVED,
        "pair": list(expected_pair),
        "authored_filtered_pair_count": len(filtered_pairs),
        "reason": "cooked_shape_representation_not_exported",
    }


def evaluate_link0_table_geometry_audit(value: Any) -> dict[str, Any]:
    """Validate metadata while refusing to infer cooked-shape overlap from it."""
    try:
        return _evaluate_link0_table_geometry_audit(value)
    except ValueError as exc:
        return {"decision": SAFETY_ABORT, "validation_error": str(exc)}


def _finite_float(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"formal_snapshot_static_{field}_invalid")
    return float(value)


def _evaluate_link0_table_mounting_alignment(value: Any) -> dict[str, Any]:
    expected = {
        "schema_version",
        "authority",
        "pair",
        "configured_robot_position_m",
        "observed_link0_collider_origin_m",
        "link0_authored_mesh_world_bottom_z_m",
        "link0_authored_mesh_world_xy_bounds_m",
        "link0_mesh_point_count",
        "table_mesh_triangle_count",
        "table_support_samples",
        "required_clearance_m",
    }
    expected_pair = tuple(sorted((LINK0_COLLIDER_PATH, TABLE_COLLIDER_PATH)))
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value["schema_version"] != 1
        or value["authority"] != LINK0_TABLE_MOUNTING_ALIGNMENT_AUTHORITY
        or _pair(value["pair"], field="mounting_pair") != expected_pair
        or not isinstance(value["table_support_samples"], list)
        or len(value["table_support_samples"]) != 25
    ):
        raise ValueError("formal_snapshot_static_mounting_alignment_invalid")
    configured = _vector(value["configured_robot_position_m"], field="mounting_configured_position", length=3)
    observed = _vector(value["observed_link0_collider_origin_m"], field="mounting_observed_origin", length=3)
    if max(abs(expected - actual) for expected, actual in zip(configured, observed, strict=True)) > 1.0e-5:
        raise ValueError("formal_snapshot_static_mounting_alignment_invalid")
    bounds = _vector(value["link0_authored_mesh_world_xy_bounds_m"], field="mounting_xy_bounds", length=4)
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise ValueError("formal_snapshot_static_mounting_alignment_invalid")
    samples = []
    for sample in value["table_support_samples"]:
        if not isinstance(sample, Mapping) or set(sample) != {"xy_m", "top_z_m"}:
            raise ValueError("formal_snapshot_static_mounting_alignment_invalid")
        xy = _vector(sample["xy_m"], field="mounting_sample_xy", length=2)
        top_z = _finite_float(sample["top_z_m"], field="mounting_sample_top_z")
        if not (bounds[0] <= xy[0] <= bounds[2] and bounds[1] <= xy[1] <= bounds[3]):
            raise ValueError("formal_snapshot_static_mounting_alignment_invalid")
        samples.append((xy, top_z))
    sample_keys = [(xy[0], xy[1]) for xy, _top_z in samples]
    if sample_keys != sorted(sample_keys) or len(sample_keys) != len(set(sample_keys)):
        raise ValueError("formal_snapshot_static_mounting_alignment_invalid")
    bottom_z = _finite_float(
        value["link0_authored_mesh_world_bottom_z_m"], field="mounting_link0_bottom_z"
    )
    clearance = _nonnegative_float(value["required_clearance_m"], field="mounting_clearance")
    link0_point_count = _nonnegative_integer(
        value["link0_mesh_point_count"], field="mounting_link0_points"
    )
    table_triangle_count = _nonnegative_integer(
        value["table_mesh_triangle_count"], field="mounting_table_triangles"
    )
    if link0_point_count == 0 or table_triangle_count == 0:
        raise ValueError("formal_snapshot_static_mounting_alignment_invalid")
    top_values = [top_z for _xy, top_z in samples]
    support_top_min = min(top_values)
    support_top_max = max(top_values)
    penetration = support_top_max - bottom_z
    if penetration > 1.0e-6:
        decision = LINK0_TABLE_MOUNTING_EMBEDDED
    elif penetration <= -clearance:
        decision = LINK0_TABLE_MOUNTING_CLEAR
    elif penetration < -1.0e-6:
        decision = LINK0_TABLE_MOUNTING_INSUFFICIENT_CLEARANCE
    else:
        decision = LINK0_TABLE_MOUNTING_SURFACE_TOUCH
    surface_contact_position_z = configured[2] + penetration
    return {
        "decision": decision,
        "pair": list(expected_pair),
        "configured_robot_position_m": configured,
        "observed_link0_collider_origin_m": observed,
        "link0_authored_mesh_world_bottom_z_m": bottom_z,
        "table_support_sample_count": len(samples),
        "table_support_top_z_min_m": support_top_min,
        "table_support_top_z_max_m": support_top_max,
        "table_support_top_z_spread_m": support_top_max - support_top_min,
        "current_authored_mesh_penetration_m": penetration,
        "surface_contact_robot_position_z_m": surface_contact_position_z,
        "static_clearance_robot_position_z_m": surface_contact_position_z + clearance,
        "required_clearance_m": clearance,
        "link0_collider_origin_config_max_abs_difference_m": max(
            abs(expected - actual) for expected, actual in zip(configured, observed, strict=True)
        ),
    }


def evaluate_link0_table_mounting_alignment(value: Any) -> dict[str, Any]:
    """Evaluate authored support geometry without treating it as a cooked contact result."""
    try:
        return _evaluate_link0_table_mounting_alignment(value)
    except ValueError as exc:
        return {"decision": SAFETY_ABORT, "validation_error": str(exc)}
