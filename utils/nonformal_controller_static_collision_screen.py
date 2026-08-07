"""Pure contracts for a paused controller-configuration collision screen.

This diagnostic screen evaluates conservative pair results at controller-derived
joint configurations.  It is intentionally not a runtime contact proof and
cannot authorize a gate or a physical manipulation action.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


_BLOCKING = "BLOCKING"
_ALLOWED = "ALLOWED_SOURCE_SHELL_FINGER"
_CLEAR = "CLEAR"
_POTENTIAL = "POTENTIAL_OVERLAP_OR_MARGIN"
_EVENTS = frozenset((-1, 0, 1, 2, 3, 4))
_SEMANTICS_AUTHORITY = "native_pick_action_semantics_v1"
_SEMANTICS_DECISIONS = frozenset(
    (
        "NATIVE_TARGET_CONTRACT_INVALID",
        "DIRECT_STATIC_PROJECTION_UNSUPPORTED",
        "RAW_NATIVE_POSITION_TARGET_OUT_OF_LIMIT",
        "STATIC_PROJECTION_ELIGIBLE",
    )
)


def canonical_json_sha256(value: Any) -> str:
    """Return a deterministic JSON SHA-256 digest for diagnostic binding."""
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("controller_static_screen_json_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


def _finite_vector(value: Any, *, field: str) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise ValueError(f"controller_static_screen_{field}_invalid")
    normalized = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"controller_static_screen_{field}_invalid")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError(f"controller_static_screen_{field}_invalid")
        normalized.append(number)
    return normalized


def _absolute_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("/")
        and value != "/"
        and not value.endswith("/")
        and "//" not in value
    )


def _canonical_pair(value: Any, *, field: str) -> tuple[str, str]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(not _absolute_path(path) for path in value)
        or value[0] >= value[1]
    ):
        raise ValueError(f"controller_static_screen_{field}_invalid")
    return (value[0], value[1])


def _normalized_scope(scope: Any) -> dict[str, list[list[str]]]:
    if not isinstance(scope, Mapping) or set(scope) != {
        "blocking_pairs",
        "allowed_source_shell_pairs",
    }:
        raise ValueError("controller_static_screen_scope_invalid")

    normalized: dict[str, list[list[str]]] = {}
    seen: set[tuple[str, str]] = set()
    for field in ("blocking_pairs", "allowed_source_shell_pairs"):
        pairs = scope[field]
        if not isinstance(pairs, list) or not pairs:
            raise ValueError("controller_static_screen_scope_invalid")
        canonical = [_canonical_pair(pair, field=field) for pair in pairs]
        if len(canonical) != len(set(canonical)):
            raise ValueError("controller_static_screen_scope_invalid")
        if seen.intersection(canonical):
            raise ValueError("controller_static_screen_scope_invalid")
        seen.update(canonical)
        normalized[field] = [list(pair) for pair in sorted(canonical)]
    return normalized


def resolve_joint_configuration(current: Any, action: Any) -> dict[str, Any]:
    """Apply one explicit positional action to a complete joint vector.

    A position-less action is an explicit hold only when every controller
    channel is absent.  A positional action must name every changed index.
    """
    current_positions = _finite_vector(current, field="joint_action")
    if not isinstance(action, Mapping):
        raise ValueError("joint_action_invalid")
    required = {
        "joint_positions",
        "joint_indices",
        "joint_velocities",
        "joint_efforts",
    }
    if set(action) != required:
        raise ValueError("joint_action_invalid")
    if action["joint_velocities"] is not None or action["joint_efforts"] is not None:
        raise ValueError("joint_action_invalid")

    positions = action["joint_positions"]
    indices = action["joint_indices"]
    if positions is None:
        if indices is not None:
            raise ValueError("joint_action_invalid")
        return {
            "joint_positions": current_positions,
            "changed_joint_indices": [],
            "is_hold": True,
        }
    if isinstance(positions, (str, bytes)) or not isinstance(positions, Sequence):
        raise ValueError("joint_action_invalid")
    if isinstance(indices, (str, bytes)) or not isinstance(indices, Sequence):
        raise ValueError("joint_action_invalid")
    if len(positions) != len(indices) or not positions:
        raise ValueError("joint_action_invalid")

    resolved = list(current_positions)
    changed_indices: list[int] = []
    for position, index in zip(positions, indices, strict=True):
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or index >= len(resolved)
            or index in changed_indices
            or isinstance(position, bool)
            or not isinstance(position, (int, float))
            or not math.isfinite(float(position))
        ):
            raise ValueError("joint_action_invalid")
        resolved[index] = float(position)
        changed_indices.append(index)
    return {
        "joint_positions": resolved,
        "changed_joint_indices": changed_indices,
        "is_hold": False,
    }


def _semantics_vector(value: Any, *, field: str, length: int) -> list[float]:
    try:
        result = _finite_vector(value, field=field)
    except ValueError as exc:
        raise ValueError(f"native_pick_semantics_{field}_invalid") from exc
    if len(result) != length:
        raise ValueError(f"native_pick_semantics_{field}_invalid")
    return result


def _semantics_sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"native_pick_semantics_{field}_invalid")
    return value


def _semantics_raw_action(value: Any, *, field: str) -> dict[str, Any]:
    required = {"joint_positions", "joint_velocities", "joint_efforts", "joint_indices"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError(f"native_pick_semantics_{field}_invalid")

    def normalize_channel(
        channel: Any, *, allow_sparse: bool, numeric_only: bool
    ) -> list[float | None] | None:
        if channel is None:
            return None
        if isinstance(channel, (str, bytes)) or not isinstance(channel, Sequence):
            raise ValueError(f"native_pick_semantics_{field}_invalid")
        normalized: list[float | None] = []
        for item in channel:
            if item is None and allow_sparse:
                normalized.append(None)
                continue
            if (
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(float(item))
            ):
                raise ValueError(f"native_pick_semantics_{field}_invalid")
            normalized.append(float(item))
        if numeric_only and any(item is None for item in normalized):
            raise ValueError(f"native_pick_semantics_{field}_invalid")
        return normalized

    indices = value["joint_indices"]
    if indices is None:
        normalized_indices = None
    elif isinstance(indices, (str, bytes)) or not isinstance(indices, Sequence):
        raise ValueError(f"native_pick_semantics_{field}_invalid")
    else:
        normalized_indices = []
        for index in indices:
            if isinstance(index, bool) or not isinstance(index, int):
                raise ValueError(f"native_pick_semantics_{field}_invalid")
            normalized_indices.append(index)
    return {
        "joint_positions": normalize_channel(
            value["joint_positions"], allow_sparse=True, numeric_only=False
        ),
        "joint_velocities": normalize_channel(
            value["joint_velocities"], allow_sparse=False, numeric_only=True
        ),
        "joint_efforts": normalize_channel(
            value["joint_efforts"], allow_sparse=False, numeric_only=True
        ),
        "joint_indices": normalized_indices,
    }


def _semantics_receipt(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "world_index",
        "timeline_time_s",
        "is_playing",
        "is_stopped",
    }:
        raise ValueError(f"native_pick_semantics_{field}_invalid")
    world_index = value["world_index"]
    timeline_time_s = value["timeline_time_s"]
    if (
        type(world_index) is not int
        or world_index < 0
        or isinstance(timeline_time_s, bool)
        or not isinstance(timeline_time_s, (int, float))
        or not math.isfinite(float(timeline_time_s))
        or type(value["is_playing"]) is not bool
        or type(value["is_stopped"]) is not bool
    ):
        raise ValueError(f"native_pick_semantics_{field}_invalid")
    return {
        "world_index": world_index,
        "timeline_time_s": float(timeline_time_s),
        "is_playing": value["is_playing"],
        "is_stopped": value["is_stopped"],
    }


def _evaluate_native_pick_semantics(capture: Any) -> dict[str, Any]:
    required = {
        "schema_version",
        "authority",
        "baseline",
        "post_audit",
        "target",
        "rmp",
        "frame_observations",
        "source_world_matrix_row_major",
        "source_world_matrix_after_row_major",
        "opening",
        "event0",
        "timeline_before",
        "timeline_after",
    }
    if (
        not isinstance(capture, Mapping)
        or set(capture) != required
        or capture.get("schema_version") != 1
        or capture.get("authority") != _SEMANTICS_AUTHORITY
    ):
        raise ValueError("native_pick_semantics_capture_invalid")
    baseline = capture["baseline"]
    if not isinstance(baseline, Mapping) or set(baseline) != {
        "joint_positions",
        "joint_velocities",
        "joint_lower_limits",
        "joint_upper_limits",
        "dof_names",
        "stage_units_in_meters",
        "expected_stage_units_in_meters",
    }:
        raise ValueError("native_pick_semantics_baseline_invalid")
    positions = _semantics_vector(
        baseline["joint_positions"], field="joint_positions", length=9
    )
    _semantics_vector(baseline["joint_velocities"], field="joint_velocities", length=9)
    lower = _semantics_vector(
        baseline["joint_lower_limits"], field="joint_lower_limits", length=9
    )
    upper = _semantics_vector(
        baseline["joint_upper_limits"], field="joint_upper_limits", length=9
    )
    if any(lower_value >= upper_value for lower_value, upper_value in zip(lower, upper)):
        raise ValueError("native_pick_semantics_baseline_invalid")
    dof_names = baseline["dof_names"]
    stage_units = baseline["stage_units_in_meters"]
    expected_stage_units = baseline["expected_stage_units_in_meters"]
    if (
        not isinstance(dof_names, list)
        or len(dof_names) != 9
        or any(not isinstance(name, str) or not name for name in dof_names)
        or len(set(dof_names)) != len(dof_names)
        or isinstance(stage_units, bool)
        or not isinstance(stage_units, (int, float))
        or not math.isfinite(float(stage_units))
        or float(stage_units) <= 0.0
        or isinstance(expected_stage_units, bool)
        or not isinstance(expected_stage_units, (int, float))
        or not math.isfinite(float(expected_stage_units))
        or not math.isclose(
            float(stage_units), float(expected_stage_units), rel_tol=0.0, abs_tol=1.0e-12
        )
    ):
        raise ValueError("native_pick_semantics_baseline_invalid")
    stage_units = float(stage_units)
    post_audit = capture["post_audit"]
    if not isinstance(post_audit, Mapping) or set(post_audit) != {
        "joint_positions",
        "joint_velocities",
    }:
        raise ValueError("native_pick_semantics_post_audit_invalid")
    post_audit_positions = _semantics_vector(
        post_audit["joint_positions"], field="post_audit_joint_positions", length=9
    )
    post_audit_velocities = _semantics_vector(
        post_audit["joint_velocities"], field="post_audit_joint_velocities", length=9
    )
    baseline_velocities = _semantics_vector(
        baseline["joint_velocities"], field="joint_velocities", length=9
    )
    if not all(
        math.isclose(before, after, rel_tol=0.0, abs_tol=1.0e-8)
        for before, after in zip(post_audit_positions, positions)
    ) or not all(
        math.isclose(before, after, rel_tol=0.0, abs_tol=1.0e-8)
        for before, after in zip(post_audit_velocities, baseline_velocities)
    ):
        raise ValueError("native_pick_semantics_post_audit_invalid")

    target = capture["target"]
    if not isinstance(target, Mapping) or set(target) != {
        "source_center_stage",
        "source_size_stage",
        "approach_direction",
        "event0_target_position_stage",
        "event0_target_orientation_wxyz",
        "pre_offset_x_m",
        "pre_offset_z_m",
        "after_offset_z_m",
        "pick_z_offset_m",
        "pick_x_offset_m",
        "rmp_end_effector_frame_name",
        "pick_progress_frame_name",
        "rmp_forward_call_count",
    }:
        raise ValueError("native_pick_semantics_target_invalid")
    source_center = _semantics_vector(
        target["source_center_stage"], field="source_center", length=3
    )
    source_size = _semantics_vector(
        target["source_size_stage"], field="source_size", length=3
    )
    approach = _semantics_vector(
        target["approach_direction"], field="approach_direction", length=3
    )
    event0_target = _semantics_vector(
        target["event0_target_position_stage"], field="event0_target", length=3
    )
    orientation = _semantics_vector(
        target["event0_target_orientation_wxyz"], field="event0_orientation", length=4
    )
    scalar_offsets = {}
    for field in (
        "pre_offset_x_m",
        "pre_offset_z_m",
        "after_offset_z_m",
        "pick_z_offset_m",
        "pick_x_offset_m",
    ):
        value = target[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError("native_pick_semantics_target_invalid")
        scalar_offsets[field] = float(value)
    if (
        not 0.0 <= scalar_offsets["pick_z_offset_m"] <= 0.10
        or abs(scalar_offsets["pick_x_offset_m"]) > 0.10
        or scalar_offsets["pre_offset_x_m"] <= 0.0
        or scalar_offsets["pre_offset_z_m"] <= 0.0
        or scalar_offsets["after_offset_z_m"] <= 0.0
        or approach != [-1.0, 0.0, 0.0]
        or not math.isclose(sum(component * component for component in orientation), 1.0, abs_tol=1.0e-6)
        or target["rmp_end_effector_frame_name"] != "right_gripper"
        or target["pick_progress_frame_name"] != "tool_center"
        or target["rmp_forward_call_count"] != 1
    ):
        raise ValueError("native_pick_semantics_target_invalid")
    expected_event0_target = [
        source_center[index]
        + approach[index] * scalar_offsets["pre_offset_x_m"] / stage_units
        for index in range(3)
    ]
    expected_event0_target[2] += source_size[2] + scalar_offsets["pre_offset_z_m"]
    if not all(
        math.isclose(observed, expected, rel_tol=0.0, abs_tol=1.0e-9)
        for observed, expected in zip(event0_target, expected_event0_target)
    ):
        raise ValueError("native_pick_semantics_target_invalid")

    rmp = capture["rmp"]
    if not isinstance(rmp, Mapping) or set(rmp) != {
        "physics_dt_s",
        "active_joint_names",
        "active_joint_indices",
        "policy_config",
        "policy_file_hashes",
    }:
        raise ValueError("native_pick_semantics_rmp_invalid")
    physics_dt_s = rmp["physics_dt_s"]
    active_names = rmp["active_joint_names"]
    active_indices = rmp["active_joint_indices"]
    policy_config = rmp["policy_config"]
    policy_file_hashes = rmp["policy_file_hashes"]
    if (
        isinstance(physics_dt_s, bool)
        or not isinstance(physics_dt_s, (int, float))
        or not math.isfinite(float(physics_dt_s))
        or not math.isclose(float(physics_dt_s), 1.0 / 60.0, rel_tol=0.0, abs_tol=1.0e-12)
        or not isinstance(active_names, list)
        or not isinstance(active_indices, list)
        or len(active_names) != 7
        or len(active_indices) != 7
        or any(not isinstance(name, str) or not name for name in active_names)
        or any(type(index) is not int for index in active_indices)
        or len(set(active_indices)) != len(active_indices)
        or any(index < 0 or index >= len(dof_names) for index in active_indices)
        or any(dof_names[index] != name for index, name in zip(active_indices, active_names))
        or not isinstance(policy_config, Mapping)
        or policy_config.get("end_effector_frame_name")
        != target["rmp_end_effector_frame_name"]
        or policy_config.get("ignore_robot_state_updates") is not False
        or not isinstance(policy_file_hashes, Mapping)
        or set(policy_file_hashes)
        != {"robot_description_path", "urdf_path", "rmpflow_config_path"}
    ):
        raise ValueError("native_pick_semantics_mapping_invalid")
    for record in policy_file_hashes.values():
        if (
            not isinstance(record, Mapping)
            or set(record) != {"path", "sha256"}
            or not isinstance(record["path"], str)
            or not record["path"].startswith("/")
        ):
            raise ValueError("native_pick_semantics_rmp_invalid")
        _semantics_sha256(record["sha256"], field="policy_file_sha256")

    frame_observations = capture["frame_observations"]
    if not isinstance(frame_observations, Mapping) or set(frame_observations) != {
        "robot_base_position_world",
        "robot_base_orientation_wxyz",
        "rmp_policy_end_effector_position",
        "rmp_policy_end_effector_orientation_wxyz",
        "tool_center_position_world",
    }:
        raise ValueError("native_pick_semantics_frames_invalid")
    _semantics_vector(
        frame_observations["robot_base_position_world"], field="robot_base_position", length=3
    )
    robot_base_orientation = _semantics_vector(
        frame_observations["robot_base_orientation_wxyz"], field="robot_base_orientation", length=4
    )
    _semantics_vector(
        frame_observations["rmp_policy_end_effector_position"], field="rmp_position", length=3
    )
    rmp_orientation = _semantics_vector(
        frame_observations["rmp_policy_end_effector_orientation_wxyz"], field="rmp_orientation", length=4
    )
    _semantics_vector(
        frame_observations["tool_center_position_world"], field="tool_center_position", length=3
    )
    if not all(
        math.isclose(sum(component * component for component in quaternion), 1.0, abs_tol=1.0e-6)
        for quaternion in (robot_base_orientation, rmp_orientation)
    ):
        raise ValueError("native_pick_semantics_frames_invalid")
    source_matrix = _semantics_vector(
        capture["source_world_matrix_row_major"], field="source_matrix", length=16
    )
    source_matrix_after = _semantics_vector(
        capture["source_world_matrix_after_row_major"], field="source_matrix_after", length=16
    )
    if not all(
        math.isclose(before, after, rel_tol=0.0, abs_tol=1.0e-10)
        for before, after in zip(source_matrix, source_matrix_after)
    ):
        raise ValueError("native_pick_semantics_source_transform_invalid")
    timeline_before = _semantics_receipt(capture["timeline_before"], field="timeline_before")
    timeline_after = _semantics_receipt(capture["timeline_after"], field="timeline_after")
    if timeline_before != timeline_after or timeline_before["is_playing"] or timeline_before["is_stopped"]:
        raise ValueError("native_pick_semantics_timeline_invalid")

    opening = capture["opening"]
    event0 = capture["event0"]
    if (
        not isinstance(opening, Mapping)
        or set(opening) != {"event_before", "event_after", "last_emitted_event", "raw_action"}
        or opening.get("event_before") != 0
        or opening.get("event_after") != 0
        or opening.get("last_emitted_event") is not None
        or not isinstance(event0, Mapping)
        or set(event0) != {"event_before", "event_after", "last_emitted_event", "raw_action"}
        or event0.get("event_before") != 0
        or type(event0.get("event_after")) is not int
        or event0["event_after"] not in {0, 1}
        or event0.get("last_emitted_event") != 0
    ):
        raise ValueError("native_pick_semantics_action_invalid")
    opening_action = _semantics_raw_action(opening["raw_action"], field="opening_action")
    event0_action = _semantics_raw_action(event0["raw_action"], field="event0_action")
    if (
        opening_action["joint_positions"] is None
        or len(opening_action["joint_positions"]) != len(dof_names)
        or any(item is not None for item in opening_action["joint_positions"][:7])
        or any(item is None for item in opening_action["joint_positions"][7:])
        or opening_action["joint_indices"] is not None
        or opening_action["joint_velocities"] is not None
        or opening_action["joint_efforts"] is not None
        or event0_action["joint_positions"] is None
        or len(event0_action["joint_positions"]) != len(active_indices)
        or any(value is None for value in event0_action["joint_positions"])
        or event0_action["joint_indices"] != active_indices
        or (
            event0_action["joint_velocities"] is not None
            and len(event0_action["joint_velocities"]) != len(active_indices)
        )
        or (
            event0_action["joint_efforts"] is not None
            and len(event0_action["joint_efforts"]) != len(active_indices)
        )
    ):
        raise ValueError("native_pick_semantics_mapping_invalid")
    if any(
        value < lower[index] - 1.0e-8 or value > upper[index] + 1.0e-8
        for index, value in enumerate(opening_action["joint_positions"])
        if value is not None
    ):
        raise ValueError("native_pick_semantics_opening_action_invalid")
    resolved_positions = list(positions)
    for index, target_position in zip(
        active_indices, event0_action["joint_positions"], strict=True
    ):
        if target_position is None:
            raise ValueError("native_pick_semantics_mapping_invalid")
        resolved_positions[index] = target_position
    violations = [
        {
            "index": index,
            "target": resolved_positions[index],
            "lower": lower[index],
            "upper": upper[index],
        }
        for index in active_indices
        if resolved_positions[index] < lower[index] or resolved_positions[index] > upper[index]
    ]
    common = {
        "raw_event0_action_sha256": canonical_json_sha256(event0_action),
        "resolved_position_target": resolved_positions,
        "resolved_position_target_sha256": canonical_json_sha256(resolved_positions),
        "position_limit_violations": violations,
        "native_action_channels": {
            "joint_positions": True,
            "joint_velocities": event0_action["joint_velocities"] is not None,
            "joint_efforts": event0_action["joint_efforts"] is not None,
        },
        "static_projection_channel_treatment": {
            "joint_positions": "static_geometry_target",
            "joint_velocities": (
                "recorded_not_applied"
                if event0_action["joint_velocities"] is not None
                else "absent"
            ),
            "joint_efforts": (
                "unsupported"
                if event0_action["joint_efforts"] is not None
                else "absent"
            ),
        },
    }
    if violations:
        return {
            "decision": "RAW_NATIVE_POSITION_TARGET_OUT_OF_LIMIT",
            "static_projection_authorized": False,
            **common,
        }
    if event0_action["joint_efforts"] is not None:
        return {
            "decision": "DIRECT_STATIC_PROJECTION_UNSUPPORTED",
            "static_projection_authorized": False,
            **common,
        }
    return {
        "decision": "STATIC_PROJECTION_ELIGIBLE",
        "static_projection_authorized": True,
        **common,
    }


def evaluate_native_pick_semantics(capture: Any) -> dict[str, Any]:
    """Classify whether a native event-0 target admits static projection."""
    try:
        return _evaluate_native_pick_semantics(capture)
    except ValueError as exc:
        return {
            "decision": "NATIVE_TARGET_CONTRACT_INVALID",
            "static_projection_authorized": False,
            "validation_error": str(exc),
        }


def _counterfactual_vector(value: Any, *, field: str, length: int) -> list[float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != length:
        raise ValueError(f"rmp_qdot_counterfactual_{field}_invalid")
    normalized = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"rmp_qdot_counterfactual_{field}_invalid")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError(f"rmp_qdot_counterfactual_{field}_invalid")
        normalized.append(number)
    return normalized


def _max_abs_difference(left: Sequence[float], right: Sequence[float]) -> float:
    return max(abs(first - second) for first, second in zip(left, right, strict=True))


def _evaluate_rmp_qdot_counterfactual(capture: Any, replay: Any) -> dict[str, Any]:
    semantics = evaluate_native_pick_semantics(capture)
    if semantics.get("decision") != "RAW_NATIVE_POSITION_TARGET_OUT_OF_LIMIT":
        raise ValueError("rmp_qdot_counterfactual_semantics_not_eligible")
    if not isinstance(capture, Mapping):
        raise ValueError("rmp_qdot_counterfactual_capture_invalid")
    baseline = capture["baseline"]
    rmp = capture["rmp"]
    event0 = capture["event0"]
    if (
        not isinstance(baseline, Mapping)
        or not isinstance(rmp, Mapping)
        or not isinstance(event0, Mapping)
        or not isinstance(event0.get("raw_action"), Mapping)
        or not isinstance(replay, Mapping)
        or set(replay) != {
            "schema_version",
            "authority",
            "control_dt_s",
            "active_joint_positions",
            "active_joint_velocities",
            "watched_joint_names",
            "watched_joint_positions",
            "watched_joint_velocities",
            "actual_qdot_branch",
            "zero_qdot_branch",
        }
        or replay.get("schema_version") != 1
        or replay.get("authority") != "rmp_qdot_counterfactual_v1"
    ):
        raise ValueError("rmp_qdot_counterfactual_capture_invalid")
    active_indices = rmp.get("active_joint_indices")
    if (
        not isinstance(active_indices, list)
        or len(active_indices) != 7
        or any(type(index) is not int for index in active_indices)
    ):
        raise ValueError("rmp_qdot_counterfactual_mapping_invalid")
    all_positions = _semantics_vector(
        baseline.get("joint_positions"), field="joint_positions", length=9
    )
    all_velocities = _semantics_vector(
        baseline.get("joint_velocities"), field="joint_velocities", length=9
    )
    lower = _semantics_vector(
        baseline.get("joint_lower_limits"), field="joint_lower_limits", length=9
    )
    upper = _semantics_vector(
        baseline.get("joint_upper_limits"), field="joint_upper_limits", length=9
    )
    active_positions = [all_positions[index] for index in active_indices]
    active_velocities = [all_velocities[index] for index in active_indices]
    control_dt_s = replay["control_dt_s"]
    if (
        isinstance(control_dt_s, bool)
        or not isinstance(control_dt_s, (int, float))
        or not math.isfinite(float(control_dt_s))
        or not math.isclose(
            float(control_dt_s), float(rmp.get("physics_dt_s")), rel_tol=0.0, abs_tol=1.0e-12
        )
        or _counterfactual_vector(
            replay["active_joint_positions"], field="active_joint_positions", length=7
        )
        != active_positions
        or _counterfactual_vector(
            replay["active_joint_velocities"], field="active_joint_velocities", length=7
        )
        != active_velocities
        or replay["watched_joint_names"] != []
        or _counterfactual_vector(
            replay["watched_joint_positions"], field="watched_joint_positions", length=0
        )
        != []
        or _counterfactual_vector(
            replay["watched_joint_velocities"], field="watched_joint_velocities", length=0
        )
        != []
    ):
        raise ValueError("rmp_qdot_counterfactual_input_invalid")

    def branch(value: Any, *, name: str, expected_input: list[float]) -> tuple[list[float], list[float]]:
        if not isinstance(value, Mapping) or set(value) != {
            "input_joint_velocities",
            "position_targets",
            "velocity_targets",
        }:
            raise ValueError(f"rmp_qdot_counterfactual_{name}_invalid")
        input_velocities = _counterfactual_vector(
            value["input_joint_velocities"], field=f"{name}_input", length=7
        )
        if input_velocities != expected_input:
            raise ValueError(f"rmp_qdot_counterfactual_{name}_invalid")
        return (
            _counterfactual_vector(
                value["position_targets"], field=f"{name}_positions", length=7
            ),
            _counterfactual_vector(
                value["velocity_targets"], field=f"{name}_velocities", length=7
            ),
        )

    actual_positions, actual_velocities = branch(
        replay["actual_qdot_branch"], name="actual", expected_input=active_velocities
    )
    zero_positions, zero_velocities = branch(
        replay["zero_qdot_branch"], name="zero", expected_input=[0.0] * 7
    )
    raw_action = event0["raw_action"]
    raw_positions = _counterfactual_vector(
        raw_action.get("joint_positions"), field="raw_positions", length=7
    )
    raw_velocities = _counterfactual_vector(
        raw_action.get("joint_velocities"), field="raw_velocities", length=7
    )
    position_replay_error = _max_abs_difference(actual_positions, raw_positions)
    velocity_replay_error = _max_abs_difference(actual_velocities, raw_velocities)
    velocity_replay_equivalent = all(
        math.isclose(
            observed,
            expected,
            rel_tol=1.0e-6,
            abs_tol=1.0e-6,
        )
        for observed, expected in zip(actual_velocities, raw_velocities, strict=True)
    )
    replay_equivalent = position_replay_error <= 1.0e-6 and velocity_replay_equivalent
    zero_resolved = list(all_positions)
    for index, target in zip(active_indices, zero_positions, strict=True):
        zero_resolved[index] = target
    zero_violations = [
        {
            "index": index,
            "target": zero_resolved[index],
            "lower": lower[index],
            "upper": upper[index],
        }
        for index in active_indices
        if zero_resolved[index] < lower[index] or zero_resolved[index] > upper[index]
    ]
    zero_min_limit_margin = min(
        min(zero_resolved[index] - lower[index], upper[index] - zero_resolved[index])
        for index in active_indices
    )
    common = {
        "replay_equivalent": replay_equivalent,
        "actual_qdot_position_replay_max_abs_error": position_replay_error,
        "actual_qdot_velocity_replay_max_abs_error": velocity_replay_error,
        "actual_qdot_velocity_replay_equivalent": velocity_replay_equivalent,
        "actual_qdot_position_targets_sha256": canonical_json_sha256(actual_positions),
        "zero_qdot_position_targets_sha256": canonical_json_sha256(zero_positions),
        "zero_qdot_resolved_position_target": zero_resolved,
        "zero_qdot_resolved_position_target_sha256": canonical_json_sha256(zero_resolved),
        "zero_qdot_position_limit_violations": zero_violations,
        "zero_qdot_min_limit_margin": zero_min_limit_margin,
        "position_target_max_abs_difference": _max_abs_difference(
            actual_positions, zero_positions
        ),
        "velocity_target_max_abs_difference": _max_abs_difference(
            actual_velocities, zero_velocities
        ),
    }
    if not replay_equivalent:
        return {"decision": "REPLAY_NOT_EQUIVALENT", **common}
    if not zero_violations and zero_min_limit_margin > 1.0e-6:
        return {"decision": "QDOT_CAUSAL_LIMIT_CONTRIBUTOR", **common}
    if common["position_target_max_abs_difference"] > 1.0e-8:
        return {"decision": "QDOT_INFLUENTIAL_NOT_DISPOSITIVE", **common}
    return {"decision": "QDOT_NOT_CAUSAL_TARGET_OR_LIMIT", **common}


def evaluate_rmp_qdot_counterfactual(capture: Any, replay: Any) -> dict[str, Any]:
    """Evaluate a shadow-RMP qdot=0 counterfactual without authorizing control."""
    try:
        return _evaluate_rmp_qdot_counterfactual(capture, replay)
    except ValueError as exc:
        return {
            "decision": "COUNTERFACTUAL_CONTRACT_INVALID",
            "replay_equivalent": False,
            "validation_error": str(exc),
        }


def _validate_pair_result(
    value: Any,
    *,
    blocking_pairs: set[tuple[str, str]],
    allowed_pairs: set[tuple[str, str]],
) -> tuple[tuple[str, str], str]:
    if not isinstance(value, Mapping) or set(value) != {
        "pair",
        "classification",
        "status",
        "lower_bound_m",
    }:
        raise ValueError("pair_result_invalid")
    pair = _canonical_pair(value["pair"], field="pair_result")
    expected_classification = (
        _BLOCKING if pair in blocking_pairs else _ALLOWED if pair in allowed_pairs else None
    )
    if value["classification"] != expected_classification:
        raise ValueError("pair_result_invalid")
    status = value["status"]
    if status not in (_CLEAR, _POTENTIAL):
        raise ValueError("pair_result_invalid")
    lower_bound = value["lower_bound_m"]
    if (
        isinstance(lower_bound, bool)
        or not isinstance(lower_bound, (int, float))
        or not math.isfinite(float(lower_bound))
    ):
        raise ValueError("pair_result_invalid")
    return pair, status


def evaluate_configuration_trace(scope: Any, trace: Any) -> dict[str, Any]:
    """Evaluate all declared pairs at each pre-lift controller configuration."""
    normalized_scope = _normalized_scope(scope)
    if isinstance(trace, (str, bytes)) or not isinstance(trace, Iterable):
        raise ValueError("configuration_trace_invalid")
    blocking_pairs = {tuple(pair) for pair in normalized_scope["blocking_pairs"]}
    allowed_pairs = {tuple(pair) for pair in normalized_scope["allowed_source_shell_pairs"]}
    required_pairs = blocking_pairs | allowed_pairs
    forbidden_records: list[dict[str, Any]] = []
    early_allowed_records: list[dict[str, Any]] = []
    screened_pair_result_count = 0
    terminal_event: int | None = None

    configuration_count = 0
    for expected_index, record in enumerate(trace):
        configuration_count += 1
        if not isinstance(record, Mapping) or set(record) != {
            "sample_index",
            "controller_event",
            "joint_positions",
            "action_sha256",
            "pair_results",
        }:
            raise ValueError("configuration_trace_invalid")
        if record["sample_index"] != expected_index:
            raise ValueError("configuration_trace_invalid")
        event = record["controller_event"]
        if type(event) is not int or event not in _EVENTS:
            raise ValueError("controller_event_invalid")
        terminal_event = event
        _finite_vector(record["joint_positions"], field="trace_joint_positions")
        digest = record["action_sha256"]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("configuration_trace_invalid")
        results = record["pair_results"]
        if not isinstance(results, list):
            raise ValueError("pair_result_coverage_invalid")
        observed: dict[tuple[str, str], str] = {}
        for result in results:
            pair, status = _validate_pair_result(
                result,
                blocking_pairs=blocking_pairs,
                allowed_pairs=allowed_pairs,
            )
            if pair in observed:
                raise ValueError("pair_result_coverage_invalid")
            observed[pair] = status
        if set(observed) != required_pairs:
            raise ValueError("pair_result_coverage_invalid")
        screened_pair_result_count += len(observed)

        for pair in sorted(blocking_pairs):
            if observed[pair] != _CLEAR:
                forbidden_records.append(
                    {
                        "sample_index": expected_index,
                        "controller_event": event,
                        "pair": list(pair),
                        "status": observed[pair],
                    }
                )
        if event < 4:
            for pair in sorted(allowed_pairs):
                if observed[pair] != _CLEAR:
                    early_allowed_records.append(
                        {
                            "sample_index": expected_index,
                            "controller_event": event,
                            "pair": list(pair),
                            "status": observed[pair],
                        }
                    )

    if configuration_count == 0:
        raise ValueError("configuration_trace_invalid")
    if terminal_event != 4:
        raise ValueError("controller_event_invalid")
    return {
        "candidate_passed": not forbidden_records and not early_allowed_records,
        "configuration_count": configuration_count,
        "required_pair_count": len(required_pairs),
        "screened_pair_result_count": screened_pair_result_count,
        "forbidden_pair_result_count": len(forbidden_records),
        "early_allowed_pair_result_count": len(early_allowed_records),
        "first_forbidden_pair_result": (
            forbidden_records[0] if forbidden_records else None
        ),
        "first_early_allowed_pair_result": (
            early_allowed_records[0] if early_allowed_records else None
        ),
        "scope_sha256": canonical_json_sha256(normalized_scope),
    }


def select_candidate(candidates: Any) -> dict[str, Any]:
    """Select exactly one passing diagnostic candidate, never a gate result."""
    if not isinstance(candidates, list):
        raise ValueError("candidate_selection_invalid")
    candidate_ids: set[str] = set()
    passing_ids: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ValueError("candidate_selection_invalid")
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id or candidate_id in candidate_ids:
            raise ValueError("candidate_selection_invalid")
        candidate_ids.add(candidate_id)
        if candidate.get("candidate_passed") is True:
            passing_ids.append(candidate_id)
    passing_ids.sort()
    if len(passing_ids) == 1:
        return {
            "decision": "SCREEN_SELECTED_DIAGNOSTIC_ONLY",
            "selected_candidate_id": passing_ids[0],
            "passing_candidate_ids": passing_ids,
        }
    if passing_ids:
        return {
            "decision": "SCREEN_AMBIGUOUS_CANDIDATES",
            "selected_candidate_id": None,
            "passing_candidate_ids": passing_ids,
        }
    return {
        "decision": "SCREEN_NO_CANDIDATE",
        "selected_candidate_id": None,
        "passing_candidate_ids": [],
    }
