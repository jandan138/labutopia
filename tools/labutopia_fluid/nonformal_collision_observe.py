"""Pure contracts for collision-observe-only trajectory diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


TRAJECTORY_MODE = "collision_observe_full_trajectory_v1"
COLLISION_POLICY = "record_and_continue"


def validate_current_trajectory_config(value: Any) -> dict[str, Any]:
    """Reject configs that could turn the diagnostic into a product run."""
    if not isinstance(value, Mapping):
        raise ValueError("collision_observe_config_invalid")
    fluid = value.get("online_fluid")
    if not isinstance(fluid, Mapping):
        raise ValueError("collision_observe_config_invalid")
    if (
        value.get("task_type") != "pickpour"
        or value.get("controller_type") != "pour"
        or value.get("mode") != "collect"
        or value.get("max_episodes") != 1
        or fluid.get("enabled") is not True
        or fluid.get("expert_control_profile") != "native_expert_v1"
        or fluid.get("source_ownership") != "contact_friction_dynamic_v1"
        or fluid.get("source_pose_authority")
        != "physx_dynamic_readback_v1"
        or fluid.get("diagnostic_trajectory_mode") != TRAJECTORY_MODE
        or fluid.get("collision_policy") != COLLISION_POLICY
        or not isinstance(fluid.get("source_actor_path"), str)
        or not fluid["source_actor_path"]
        or not isinstance(fluid.get("source_external_shell_path"), str)
        or not fluid["source_external_shell_path"]
        or any(
            key in fluid
            for key in (
                "attachment_matrix_policy",
                "expert_attachment",
                "gripper_frame_path",
                "synthetic_attachment_collision_filter_root_path",
            )
        )
    ):
        raise ValueError("collision_observe_config_invalid")
    return dict(value)


def classify_contact_header(
    header: Any,
    *,
    source_body_path: str,
    robot_body_paths: Sequence[str],
    left_finger_body_path: str,
    right_finger_body_path: str,
    hand_body_path: str,
) -> str:
    """Classify a direct PhysX header without assigning pass/fail semantics."""
    if not isinstance(header, Mapping):
        raise ValueError("collision_observe_contact_header_invalid")
    actors = (header.get("actor0"), header.get("actor1"))
    colliders = (header.get("collider0"), header.get("collider1"))
    if any(not isinstance(path, str) or not path for path in (*actors, *colliders)):
        raise ValueError("collision_observe_contact_header_invalid")
    if not isinstance(source_body_path, str) or not source_body_path:
        raise ValueError("collision_observe_source_body_invalid")
    robot = set(robot_body_paths)
    if not robot or any(not isinstance(path, str) or not path for path in robot):
        raise ValueError("collision_observe_robot_bodies_invalid")
    if source_body_path in actors:
        other = actors[1] if actors[0] == source_body_path else actors[0]
        if other == hand_body_path:
            return "SOURCE_HAND"
        if other == left_finger_body_path:
            return "SOURCE_LEFT_FINGER"
        if other == right_finger_body_path:
            return "SOURCE_RIGHT_FINGER"
        if other in robot:
            return "SOURCE_OTHER_ROBOT"
        return "SOURCE_ENVIRONMENT"
    robot_actors = [path for path in actors if path in robot]
    if len(robot_actors) == 2:
        return "ROBOT_SELF"
    if len(robot_actors) == 1:
        return "ROBOT_ENVIRONMENT"
    return "NONROBOT"


def collision_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Produce a stable summary from per-substep contact observations."""
    if isinstance(records, (str, bytes, bytearray)):
        raise ValueError("collision_observe_records_invalid")
    counts: dict[str, int] = {}
    first: dict[str, Any] | None = None
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("collision_observe_record_invalid")
        contact_class = record.get("contact_class")
        if not isinstance(contact_class, str) or not contact_class:
            raise ValueError("collision_observe_record_invalid")
        counts[contact_class] = counts.get(contact_class, 0) + 1
        if contact_class in {
            "SOURCE_HAND",
            "SOURCE_LEFT_FINGER",
            "SOURCE_RIGHT_FINGER",
            "SOURCE_OTHER_ROBOT",
            "ROBOT_ENVIRONMENT",
        } and first is None:
            first = dict(record)
    return {
        "contact_class_counts": dict(sorted(counts.items())),
        "first_robot_or_source_collision": first,
        "collision_record_count": sum(counts.values()),
    }
