"""Pure records shared by controlled-contact controllers and physics loops."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import numpy as np


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field}_invalid")
    return value


def _index(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{field}_invalid")
    result = int(value)
    if result < 0:
        raise ValueError(f"{field}_invalid")
    return result


def _canonical_array(value: Any, *, shape: tuple[int, ...]) -> tuple[np.ndarray, dict]:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("controlled_target_array_invalid") from exc
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError("controlled_target_array_invalid")
    array = np.ascontiguousarray(array, dtype=np.dtype("<f8"))
    raw = array.tobytes(order="C")
    return array, {
        "dtype": "<f8",
        "shape": list(shape),
        "bytes_hex": raw.hex(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _canonical_quaternion(value: Any) -> tuple[np.ndarray, dict]:
    array, _ = _canonical_array(value, shape=(4,))
    norm = float(np.linalg.norm(array))
    if not math.isfinite(norm) or norm <= 1.0e-12:
        raise ValueError("controlled_target_quaternion_invalid")
    array = array / norm
    first_nonzero = next((float(item) for item in array if item != 0.0), 0.0)
    if first_nonzero < 0.0:
        array = -array
    array[array == 0.0] = 0.0
    return _canonical_array(array, shape=(4,))


def _target_token(payload: dict[str, Any]) -> dict[str, Any]:
    token = deepcopy(payload)
    token["sha256"] = canonical_json_sha256(token)
    return token


def build_arm_target_token(
    *,
    tool_position_stage_units: Any,
    tool_orientation_wxyz: Any,
    control_position_stage_units: Any,
    control_orientation_wxyz: Any,
    tool_frame: str,
    control_frame: str,
    stage_units_m: float,
) -> dict[str, Any]:
    if not isinstance(tool_frame, str) or not tool_frame:
        raise ValueError("controlled_target_tool_frame_invalid")
    if not isinstance(control_frame, str) or not control_frame:
        raise ValueError("controlled_target_control_frame_invalid")
    if (
        isinstance(stage_units_m, bool)
        or not isinstance(stage_units_m, (int, float, np.number))
        or not math.isfinite(float(stage_units_m))
        or float(stage_units_m) <= 0.0
    ):
        raise ValueError("controlled_target_stage_units_invalid")

    _, tool_position = _canonical_array(tool_position_stage_units, shape=(3,))
    _, tool_orientation = _canonical_quaternion(tool_orientation_wxyz)
    _, control_position = _canonical_array(control_position_stage_units, shape=(3,))
    _, control_orientation = _canonical_quaternion(control_orientation_wxyz)
    return _target_token(
        {
            "authority": "controlled_target_token_v1",
            "kind": "arm_pose",
            "tool_frame": tool_frame,
            "control_frame": control_frame,
            "stage_units_m": float(stage_units_m),
            "arrays": {
                "tool_position_stage_units": tool_position,
                "tool_orientation_wxyz": tool_orientation,
                "control_position_stage_units": control_position,
                "control_orientation_wxyz": control_orientation,
            },
        }
    )


def build_finger_target_token(
    *,
    joint_indices: Sequence[int],
    joint_targets: Any,
) -> dict[str, Any]:
    if (
        not isinstance(joint_indices, Sequence)
        or isinstance(joint_indices, (str, bytes, bytearray))
        or len(joint_indices) != 2
        or len(set(joint_indices)) != 2
        or any(type(index) is not int or index < 0 for index in joint_indices)
    ):
        raise ValueError("controlled_target_finger_indices_invalid")
    _, targets = _canonical_array(joint_targets, shape=(2,))
    return _target_token(
        {
            "authority": "controlled_target_token_v1",
            "kind": "finger_joints",
            "joint_indices": list(joint_indices),
            "arrays": {"joint_targets": targets},
        }
    )


def validate_target_token(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("controlled_target_token_invalid")
    token = deepcopy(dict(value))
    digest = token.pop("sha256", None)
    _sha256(digest, field="controlled_target_token_sha256")
    if token.get("authority") != "controlled_target_token_v1":
        raise ValueError("controlled_target_token_invalid")
    if token.get("kind") not in {"arm_pose", "finger_joints"}:
        raise ValueError("controlled_target_token_invalid")
    try:
        recomputed = canonical_json_sha256(token)
    except (TypeError, ValueError) as exc:
        raise ValueError("controlled_target_token_invalid") from exc
    if digest != recomputed:
        raise ValueError("controlled_target_token_sha256_mismatch")
    return {**token, "sha256": digest}


class PostcontactSourceMotionAccumulator:
    """Accumulate non-cancelling source COM path and angular variation."""

    def __init__(
        self,
        *,
        maximum_path_m: float,
        maximum_angular_variation_degrees: float,
    ) -> None:
        for name, value in (
            ("path", maximum_path_m),
            ("angular_variation", maximum_angular_variation_degrees),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.number))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(f"postcontact_source_{name}_limit_invalid")
        self.maximum_path_m = float(maximum_path_m)
        self.maximum_angular_variation_degrees = float(
            maximum_angular_variation_degrees
        )
        self.reset()

    def reset(self) -> None:
        self._active = False
        self._path_m = 0.0
        self._angular_variation_degrees = 0.0
        self._previous_post_position: np.ndarray | None = None
        self._previous_post_orientation: np.ndarray | None = None

    @staticmethod
    def _position(state: Mapping[str, Any]) -> np.ndarray:
        if not isinstance(state, Mapping):
            raise ValueError("postcontact_source_state_invalid")
        value = np.asarray(state.get("com_position_m"), dtype=np.float64)
        if value.shape != (3,) or not np.isfinite(value).all():
            raise ValueError("postcontact_source_state_invalid")
        return value

    @staticmethod
    def _orientation(state: Mapping[str, Any]) -> np.ndarray:
        if not isinstance(state, Mapping):
            raise ValueError("postcontact_source_state_invalid")
        value = np.asarray(state.get("orientation_wxyz"), dtype=np.float64)
        if value.shape != (4,) or not np.isfinite(value).all():
            raise ValueError("postcontact_source_state_invalid")
        norm = float(np.linalg.norm(value))
        if norm <= 1.0e-12:
            raise ValueError("postcontact_source_state_invalid")
        return value / norm

    @staticmethod
    def _angle_degrees(first: np.ndarray, second: np.ndarray) -> float:
        dot = float(np.clip(abs(first @ second), 0.0, 1.0))
        return math.degrees(2.0 * math.acos(dot))

    def update(
        self,
        *,
        pre_source_state: Mapping[str, Any],
        post_source_state: Mapping[str, Any],
        intended_contact_occurring: bool,
    ) -> dict[str, Any]:
        if type(intended_contact_occurring) is not bool:
            raise TypeError("postcontact_source_contact_bool_required")
        pre_position = self._position(pre_source_state)
        post_position = self._position(post_source_state)
        pre_orientation = self._orientation(pre_source_state)
        post_orientation = self._orientation(post_source_state)
        if intended_contact_occurring:
            self._active = True
        if self._active:
            if self._previous_post_position is not None:
                self._path_m += float(
                    np.linalg.norm(pre_position - self._previous_post_position)
                )
                self._angular_variation_degrees += self._angle_degrees(
                    self._previous_post_orientation,
                    pre_orientation,
                )
            self._path_m += float(np.linalg.norm(post_position - pre_position))
            self._angular_variation_degrees += self._angle_degrees(
                pre_orientation,
                post_orientation,
            )
            self._previous_post_position = post_position.copy()
            self._previous_post_orientation = post_orientation.copy()
        valid = bool(
            self._path_m <= self.maximum_path_m
            and self._angular_variation_degrees
            <= self.maximum_angular_variation_degrees
        )
        return {
            "active": self._active,
            "path_m": self._path_m,
            "angular_variation_degrees": self._angular_variation_degrees,
            "maximum_path_m": self.maximum_path_m,
            "maximum_angular_variation_degrees": (
                self.maximum_angular_variation_degrees
            ),
            "valid": valid,
        }


class PostcontactToolMotionAccumulator:
    """Measure physical postcontact coast and conservative tool-center speed."""

    def __init__(
        self,
        *,
        physics_dt: float,
        approach_direction_world: Any,
        maximum_downward_coast_m: float,
        maximum_contact_step_speed_m_s: float,
        maximum_settled_speed_m_s: float,
    ) -> None:
        for name, value in (
            ("physics_dt", physics_dt),
            ("downward_coast", maximum_downward_coast_m),
            ("contact_step_speed", maximum_contact_step_speed_m_s),
            ("settled_speed", maximum_settled_speed_m_s),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.number))
                or not math.isfinite(float(value))
                or float(value) <= 0.0
            ):
                raise ValueError(f"postcontact_tool_{name}_invalid")
        direction = np.asarray(approach_direction_world, dtype=np.float64)
        if direction.shape != (3,) or not np.isfinite(direction).all():
            raise ValueError("postcontact_tool_approach_direction_invalid")
        norm = float(np.linalg.norm(direction))
        if norm <= 1.0e-12:
            raise ValueError("postcontact_tool_approach_direction_invalid")
        self.physics_dt = float(physics_dt)
        self.approach_direction_world = direction / norm
        self.maximum_downward_coast_m = float(maximum_downward_coast_m)
        self.maximum_contact_step_speed_m_s = float(
            maximum_contact_step_speed_m_s
        )
        self.maximum_settled_speed_m_s = float(maximum_settled_speed_m_s)
        self.reset()

    def reset(self) -> None:
        self._active = False
        self._baseline_position: np.ndarray | None = None
        self._maximum_downward_coast_m = 0.0
        self._maximum_speed_m_s = 0.0

    @staticmethod
    def _state(state: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
        if not isinstance(state, Mapping):
            raise ValueError("postcontact_tool_state_invalid")
        position = np.asarray(state.get("position_m"), dtype=np.float64)
        velocity = np.asarray(
            state.get("linear_velocity_m_s"), dtype=np.float64
        )
        if (
            position.shape != (3,)
            or velocity.shape != (3,)
            or not np.isfinite(position).all()
            or not np.isfinite(velocity).all()
        ):
            raise ValueError("postcontact_tool_state_invalid")
        return position, velocity

    def update(
        self,
        *,
        pre_tool_state: Mapping[str, Any],
        post_tool_state: Mapping[str, Any],
        intended_contact_occurring: bool,
    ) -> dict[str, Any]:
        if type(intended_contact_occurring) is not bool:
            raise TypeError("postcontact_tool_contact_bool_required")
        pre_position, pre_velocity = self._state(pre_tool_state)
        post_position, post_velocity = self._state(post_tool_state)
        first_contact_step = bool(intended_contact_occurring and not self._active)
        if first_contact_step:
            self._active = True
            self._baseline_position = pre_position.copy()
        displacement_speed = float(
            np.linalg.norm(post_position - pre_position) / self.physics_dt
        )
        step_speed = max(
            float(np.linalg.norm(pre_velocity)),
            float(np.linalg.norm(post_velocity)),
            displacement_speed,
        )
        self._maximum_speed_m_s = max(self._maximum_speed_m_s, step_speed)
        if self._active:
            for position in (pre_position, post_position):
                coast = float(
                    (position - self._baseline_position)
                    @ self.approach_direction_world
                )
                self._maximum_downward_coast_m = max(
                    self._maximum_downward_coast_m,
                    coast,
                )
        speed_limit = (
            self.maximum_contact_step_speed_m_s
            if first_contact_step
            else self.maximum_settled_speed_m_s
        )
        speed_valid = bool(not self._active or step_speed <= speed_limit)
        coast_valid = bool(
            self._maximum_downward_coast_m <= self.maximum_downward_coast_m
        )
        return {
            "active": self._active,
            "first_contact_step": first_contact_step,
            "step_speed_m_s": step_speed,
            "maximum_speed_m_s": self._maximum_speed_m_s,
            "speed_limit_m_s": speed_limit,
            "speed_valid": speed_valid,
            "maximum_downward_coast_m": self._maximum_downward_coast_m,
            "downward_coast_limit_m": self.maximum_downward_coast_m,
            "coast_valid": coast_valid,
            "valid": bool(speed_valid and coast_valid),
        }


class FullContactReportAccumulator:
    """Validate one-step contact vectors and maintain exact pair lifecycle."""

    _EVENTS = frozenset({"FOUND", "PERSIST", "LOST"})
    _PROTO_NONE = 0xFFFFFFFF

    def __init__(
        self,
        *,
        expected_stage_id: int,
        provisional_background_pairs: Sequence[Sequence[str]] = (),
    ) -> None:
        self._expected_stage_id = _index(
            expected_stage_id, field="contact_report_stage_id"
        )
        provisional = set()
        for pair in provisional_background_pairs:
            if (
                not isinstance(pair, Sequence)
                or isinstance(pair, (str, bytes, bytearray))
                or len(pair) != 2
                or any(not isinstance(path, str) or not path for path in pair)
                or pair[0] == pair[1]
            ):
                raise ValueError("contact_report_provisional_pair_invalid")
            provisional.add(
                self._canonical_pair(
                    pair[0], self._PROTO_NONE, pair[1], self._PROTO_NONE
                )
            )
        self._provisional_pairs = frozenset(provisional)
        self.reset()

    def reset(self) -> None:
        self._active_pairs: set[tuple[tuple[str, int], tuple[str, int]]] = set()
        self._last_physics_index: int | None = None

    @staticmethod
    def _canonical_pair(
        path0: str,
        proto0: int,
        path1: str,
        proto1: int,
    ) -> tuple[tuple[str, int], tuple[str, int]]:
        return tuple(sorted(((path0, proto0), (path1, proto1))))

    @staticmethod
    def _pair_record(
        pair: tuple[tuple[str, int], tuple[str, int]],
    ) -> list[dict[str, Any]]:
        return [
            {"collider_path": path, "proto_index": proto}
            for path, proto in pair
        ]

    @staticmethod
    def _signed_index(value: Any, *, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{field}_invalid")
        return int(value)

    @classmethod
    def _header_pair(
        cls,
        header: Mapping[str, Any],
    ) -> tuple[tuple[str, int], tuple[str, int]]:
        for field in ("actor0", "actor1", "collider0", "collider1"):
            value = header.get(field)
            if not isinstance(value, str) or not value:
                raise ValueError("contact_report_path_invalid")
        collider0 = header["collider0"]
        collider1 = header["collider1"]
        if collider0 == collider1:
            raise ValueError("contact_report_pair_invalid")
        protos = []
        for field in ("proto_index0", "proto_index1"):
            value = header.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, np.integer))
                or not 0 <= int(value) <= cls._PROTO_NONE
            ):
                raise ValueError("contact_report_proto_index_invalid")
            protos.append(int(value))
        return cls._canonical_pair(collider0, protos[0], collider1, protos[1])

    @staticmethod
    def _claim_range(
        header: Mapping[str, Any],
        *,
        offset_field: str,
        count_field: str,
        used: list[bool],
        error: str,
    ) -> range:
        offset = header.get(offset_field)
        count = header.get(count_field)
        if (
            isinstance(offset, bool)
            or not isinstance(offset, (int, np.integer))
            or isinstance(count, bool)
            or not isinstance(count, (int, np.integer))
        ):
            raise ValueError(error)
        offset = int(offset)
        count = int(count)
        if offset < 0 or count < 0 or offset + count > len(used):
            raise ValueError(error)
        result = range(offset, offset + count)
        if any(used[index] for index in result):
            raise ValueError(error)
        for index in result:
            used[index] = True
        return result

    def consume(
        self,
        *,
        physics_index: int,
        headers: Sequence[Mapping[str, Any]],
        contact_data: Sequence[Mapping[str, Any]],
        friction_anchors: Sequence[Mapping[str, Any]],
        allow_provisional_persist_bootstrap: bool = False,
    ) -> dict[str, Any]:
        index = self._signed_index(
            physics_index, field="contact_report_physics_index"
        )
        if (
            self._last_physics_index is not None
            and index != self._last_physics_index + 1
        ):
            raise ValueError("contact_report_physics_index_discontinuous")
        if type(allow_provisional_persist_bootstrap) is not bool:
            raise TypeError("contact_report_bootstrap_bool_required")
        for name, value in (
            ("headers", headers),
            ("contact_data", contact_data),
            ("friction_anchors", friction_anchors),
        ):
            if not isinstance(value, Sequence) or isinstance(
                value, (str, bytes, bytearray)
            ):
                raise TypeError(f"contact_report_{name}_sequence_required")

        normalized_headers = []
        contact_used = [False] * len(contact_data)
        friction_used = [False] * len(friction_anchors)
        grouped: dict[
            tuple[tuple[str, int], tuple[str, int]], dict[str, Any]
        ] = {}
        for raw_header in headers:
            if not isinstance(raw_header, Mapping):
                raise TypeError("contact_report_header_mapping_required")
            header = deepcopy(dict(raw_header))
            event_type = header.get("type")
            if event_type not in self._EVENTS:
                raise ValueError("contact_report_event_type_invalid")
            if header.get("stage_id") != self._expected_stage_id:
                raise ValueError("contact_report_stage_id_mismatch")
            pair = self._header_pair(header)
            contact_range = self._claim_range(
                header,
                offset_field="contact_data_offset",
                count_field="num_contact_data",
                used=contact_used,
                error="contact_report_contact_range_invalid",
            )
            friction_range = self._claim_range(
                header,
                offset_field="friction_anchors_offset",
                count_field="num_friction_anchors_data",
                used=friction_used,
                error="contact_report_friction_range_invalid",
            )
            normalized_headers.append(header)
            group = grouped.setdefault(
                pair,
                {
                    "pair": pair,
                    "headers": [],
                    "event_types": [],
                    "contact_data": [],
                    "friction_anchors": [],
                    "fragments": [],
                },
            )
            group["headers"].append(header)
            if not group["event_types"] or group["event_types"][-1] != event_type:
                group["event_types"].append(event_type)
            group["contact_data"].extend(
                deepcopy(contact_data[item]) for item in contact_range
            )
            group["friction_anchors"].extend(
                deepcopy(friction_anchors[item]) for item in friction_range
            )
            group["fragments"].append(
                {
                    "header": deepcopy(header),
                    "contact_data": [
                        deepcopy(contact_data[item]) for item in contact_range
                    ],
                    "friction_anchors": [
                        deepcopy(friction_anchors[item]) for item in friction_range
                    ],
                }
            )

        if not all(contact_used):
            raise ValueError("contact_report_contact_range_invalid")
        if not all(friction_used):
            raise ValueError("contact_report_friction_range_invalid")

        missing_active = self._active_pairs.difference(grouped)
        if missing_active:
            raise ValueError("contact_report_active_pair_missing")

        next_active = set(self._active_pairs)
        occurrences = []
        event_sequences = []
        bootstrap_count = 0
        for pair in sorted(grouped):
            group = grouped[pair]
            events = tuple(group["event_types"])
            prior_active = pair in self._active_pairs
            bootstrap = bool(
                not prior_active
                and events == ("PERSIST",)
                and allow_provisional_persist_bootstrap
                and pair in self._provisional_pairs
            )
            if bootstrap:
                bootstrap_count += 1
                occurrence = True
                current = True
                transient = False
            elif not prior_active and events == ("FOUND",):
                occurrence = True
                current = True
                transient = False
            elif prior_active and events == ("PERSIST",):
                occurrence = True
                current = True
                transient = False
            elif prior_active and events == ("LOST",):
                occurrence = False
                current = False
                transient = False
            elif not prior_active and events == ("FOUND", "LOST"):
                occurrence = True
                current = False
                transient = True
            elif prior_active and events == ("PERSIST", "LOST"):
                occurrence = True
                current = False
                transient = True
            else:
                raise ValueError("contact_report_lifecycle_invalid")

            if current:
                next_active.add(pair)
            else:
                next_active.discard(pair)
            sequence = ",".join(events)
            event_sequences.append(sequence)
            if occurrence:
                occurrences.append(
                    {
                        "canonical_pair": self._pair_record(pair),
                        "event_sequence": sequence,
                        "current": current,
                        "transient": transient,
                        "bootstrap": bootstrap,
                        "headers": deepcopy(group["headers"]),
                        "contact_data": deepcopy(group["contact_data"]),
                        "friction_anchors": deepcopy(
                            group["friction_anchors"]
                        ),
                        "fragments": deepcopy(group["fragments"]),
                    }
                )

        self._active_pairs = next_active
        self._last_physics_index = index
        return {
            "authority": "full_contact_report_step_v1",
            "physics_index": index,
            "header_count": len(normalized_headers),
            "contact_data_count": len(contact_data),
            "friction_anchor_count": len(friction_anchors),
            "range_partition_valid": True,
            "event_sequences": event_sequences,
            "occurrence_count": len(occurrences),
            "occurrences": occurrences,
            "current_pair_count": len(next_active),
            "current_pairs": [
                self._pair_record(pair) for pair in sorted(next_active)
            ],
            "bootstrap_pair_count": bootstrap_count,
        }


def evaluate_controlled_contact_report(
    *,
    report: Mapping[str, Any],
    phase: str,
    source_body_path: str,
    source_external_collider_paths: Sequence[str],
    finger_pairs: Mapping[str, Mapping[str, Any]],
    robot_body_paths: Sequence[str],
    known_body_paths: Sequence[str],
    known_collider_paths: Sequence[str],
    baseline_collider_pairs: Sequence[Sequence[str]],
    source_center_world_m: Any,
    source_axis_world: Any,
    grasp_height_band_m: Any,
    pre_body_states: Mapping[str, Mapping[str, Any]],
    post_body_states: Mapping[str, Mapping[str, Any]],
    normal_convention: str,
    minimum_inward_normal_cosine: float,
    maximum_penetration_m: float,
    maximum_precontact_relative_speed_m_s: float,
    maximum_close_relative_speed_m_s: float,
    maximum_step_normal_impulse_n_s: float,
    maximum_step_total_impulse_n_s: float,
    episode_normal_impulse_before_n_s: float,
    episode_total_impulse_before_n_s: float,
    maximum_episode_normal_impulse_n_s: float,
    maximum_episode_total_impulse_n_s: float,
    maximum_source_linear_speed_m_s: float | None = None,
    maximum_source_angular_speed_rad_s: float | None = None,
    physics_dt: float | None = None,
) -> dict[str, Any]:
    """Classify a complete immediate report with non-cancelling safety gates."""

    precontact_phases = frozenset({"INSERT", "SETTLE", "PRECONTACT_SETTLE"})
    close_phases = frozenset({"CLOSE", "CONTACT_SETTLE"})
    allowed_phases = precontact_phases | close_phases | frozenset(
        {"PRE_ROLL", "PREGRASP", "ALIGN"}
    )

    def finite_number(value: Any, *, nonnegative: bool = False) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, np.number))
            or not math.isfinite(float(value))
            or (nonnegative and float(value) < 0.0)
        ):
            raise ValueError("controlled_contact_number_invalid")
        return float(value)

    def vector(value: Any, *, unit: bool = False) -> np.ndarray:
        try:
            result = np.asarray(value, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError("controlled_contact_vector_invalid") from exc
        if result.shape != (3,) or not np.isfinite(result).all():
            raise ValueError("controlled_contact_vector_invalid")
        if unit:
            norm = float(np.linalg.norm(result))
            if norm <= 1.0e-12:
                raise ValueError("controlled_contact_vector_invalid")
            result = result / norm
        return result

    def path_set(value: Any, *, field: str) -> set[str]:
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes, bytearray))
            or any(not isinstance(item, str) or not item for item in value)
            or len(value) != len(set(value))
        ):
            raise ValueError(f"controlled_contact_{field}_invalid")
        return set(value)

    def body_state(
        states: Mapping[str, Mapping[str, Any]], body_path: str
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        value = states.get(body_path)
        if not isinstance(value, Mapping):
            raise ValueError("controlled_contact_body_state_missing")
        return (
            vector(value.get("com_position_m")),
            vector(value.get("linear_velocity_m_s")),
            vector(value.get("angular_velocity_rad_s")),
        )

    def point_velocity(
        state: tuple[np.ndarray, np.ndarray, np.ndarray], point: np.ndarray
    ) -> np.ndarray:
        com, linear, angular = state
        return linear + np.cross(angular, point - com)

    if not isinstance(report, Mapping):
        raise TypeError("controlled_contact_report_mapping_required")
    physics_step = report.get("physics_index")
    if isinstance(physics_step, bool) or not isinstance(
        physics_step, (int, np.integer)
    ):
        raise ValueError("controlled_contact_physics_step_invalid")
    physics_step = int(physics_step)
    if phase not in allowed_phases:
        raise ValueError("controlled_contact_phase_invalid")
    if normal_convention not in {
        "actor0_to_actor1",
        "actor1_to_actor0",
    }:
        raise ValueError("controlled_contact_normal_convention_invalid")
    known_bodies = path_set(known_body_paths, field="known_body_paths")
    known_colliders = path_set(
        known_collider_paths, field="known_collider_paths"
    )
    robot_bodies = path_set(robot_body_paths, field="robot_body_paths")
    if not robot_bodies <= known_bodies or source_body_path not in known_bodies:
        raise ValueError("controlled_contact_body_partition_invalid")
    source_colliders = path_set(
        source_external_collider_paths,
        field="source_external_collider_paths",
    )
    if not source_colliders <= known_colliders:
        raise ValueError("controlled_contact_source_colliders_invalid")
    center = vector(source_center_world_m)
    axis = vector(source_axis_world, unit=True)
    try:
        height_band = np.asarray(grasp_height_band_m, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("controlled_contact_height_band_invalid") from exc
    if (
        height_band.shape != (2,)
        or not np.isfinite(height_band).all()
        or height_band[0] > height_band[1]
    ):
        raise ValueError("controlled_contact_height_band_invalid")

    limits = {
        "minimum_cosine": finite_number(minimum_inward_normal_cosine),
        "penetration": finite_number(maximum_penetration_m, nonnegative=True),
        "precontact_speed": finite_number(
            maximum_precontact_relative_speed_m_s, nonnegative=True
        ),
        "close_speed": finite_number(
            maximum_close_relative_speed_m_s, nonnegative=True
        ),
        "step_normal_impulse": finite_number(
            maximum_step_normal_impulse_n_s, nonnegative=True
        ),
        "step_total_impulse": finite_number(
            maximum_step_total_impulse_n_s, nonnegative=True
        ),
        "episode_normal_impulse": finite_number(
            maximum_episode_normal_impulse_n_s, nonnegative=True
        ),
        "episode_total_impulse": finite_number(
            maximum_episode_total_impulse_n_s, nonnegative=True
        ),
    }
    if not -1.0 <= limits["minimum_cosine"] <= 1.0:
        raise ValueError("controlled_contact_minimum_cosine_invalid")
    episode_normal_before = finite_number(
        episode_normal_impulse_before_n_s, nonnegative=True
    )
    episode_total_before = finite_number(
        episode_total_impulse_before_n_s, nonnegative=True
    )
    if not isinstance(pre_body_states, Mapping) or not isinstance(
        post_body_states, Mapping
    ):
        raise TypeError("controlled_contact_body_states_mapping_required")
    if (maximum_source_linear_speed_m_s is None) != (
        maximum_source_angular_speed_rad_s is None
    ):
        raise ValueError("controlled_contact_source_speed_limits_pair_required")
    source_linear_speed = None
    source_angular_speed = None
    source_motion_authority_failure = False
    source_motion_failure = False
    source_linear_finite_difference_speed = None
    source_angular_finite_difference_speed = None
    if maximum_source_linear_speed_m_s is not None:
        source_linear_limit = finite_number(
            maximum_source_linear_speed_m_s,
            nonnegative=True,
        )
        source_angular_limit = finite_number(
            maximum_source_angular_speed_rad_s,
            nonnegative=True,
        )
        try:
            source_pre = body_state(pre_body_states, source_body_path)
            source_post = body_state(post_body_states, source_body_path)
            source_linear_speed = max(
                float(np.linalg.norm(source_pre[1])),
                float(np.linalg.norm(source_post[1])),
            )
            source_angular_speed = max(
                float(np.linalg.norm(source_pre[2])),
                float(np.linalg.norm(source_post[2])),
            )
            if physics_dt is not None:
                dt = finite_number(physics_dt)
                if dt <= 0.0:
                    raise ValueError("controlled_contact_physics_dt_invalid")
                source_linear_finite_difference_speed = float(
                    np.linalg.norm(source_post[0] - source_pre[0]) / dt
                )
                pre_orientation = np.asarray(
                    pre_body_states[source_body_path].get("orientation_wxyz"),
                    dtype=np.float64,
                )
                post_orientation = np.asarray(
                    post_body_states[source_body_path].get("orientation_wxyz"),
                    dtype=np.float64,
                )
                if (
                    pre_orientation.shape != (4,)
                    or post_orientation.shape != (4,)
                    or not np.isfinite(pre_orientation).all()
                    or not np.isfinite(post_orientation).all()
                ):
                    raise ValueError("controlled_contact_source_orientation_invalid")
                pre_norm = float(np.linalg.norm(pre_orientation))
                post_norm = float(np.linalg.norm(post_orientation))
                if pre_norm <= 1.0e-12 or post_norm <= 1.0e-12:
                    raise ValueError("controlled_contact_source_orientation_invalid")
                dot = float(
                    np.clip(
                        abs(
                            (pre_orientation / pre_norm)
                            @ (post_orientation / post_norm)
                        ),
                        0.0,
                        1.0,
                    )
                )
                source_angular_finite_difference_speed = (
                    2.0 * math.acos(dot) / dt
                )
                source_linear_speed = max(
                    source_linear_speed,
                    source_linear_finite_difference_speed,
                )
                source_angular_speed = max(
                    source_angular_speed,
                    source_angular_finite_difference_speed,
                )
            source_motion_failure = bool(
                source_linear_speed > source_linear_limit
                or source_angular_speed > source_angular_limit
            )
        except (TypeError, ValueError):
            source_motion_authority_failure = True

    intended_by_pair: dict[frozenset[str], dict[str, Any]] = {}
    if not isinstance(finger_pairs, Mapping) or set(finger_pairs) != {
        "left",
        "right",
    }:
        raise ValueError("controlled_contact_finger_pairs_invalid")
    for side in ("left", "right"):
        spec = finger_pairs[side]
        if not isinstance(spec, Mapping):
            raise ValueError("controlled_contact_finger_pairs_invalid")
        body = spec.get("body_path")
        colliders = path_set(
            spec.get("collider_paths"), field=f"{side}_finger_colliders"
        )
        if body not in robot_bodies or not colliders <= known_colliders:
            raise ValueError("controlled_contact_finger_pairs_invalid")
        for collider in colliders:
            key = frozenset((collider, *source_colliders))
            # One source collider is expected in the current treatment. Keeping
            # this explicit avoids accepting an unintended shell by set overlap.
            for source_collider in source_colliders:
                pair = frozenset((collider, source_collider))
                if pair in intended_by_pair:
                    raise ValueError("controlled_contact_finger_pair_duplicate")
                intended_by_pair[pair] = {
                    "side": side,
                    "finger_body": body,
                    "finger_collider": collider,
                    "source_collider": source_collider,
                }

    baseline_pairs = set()
    for pair in baseline_collider_pairs:
        if (
            not isinstance(pair, Sequence)
            or isinstance(pair, (str, bytes, bytearray))
            or len(pair) != 2
            or any(path not in known_colliders for path in pair)
        ):
            raise ValueError("controlled_contact_baseline_pair_invalid")
        baseline_pairs.add(frozenset(pair))

    occurrences = report.get("occurrences")
    if not isinstance(occurrences, Sequence) or isinstance(
        occurrences, (str, bytes, bytearray)
    ):
        raise ValueError("controlled_contact_occurrences_invalid")
    records = []
    step_normal_impulse = 0.0
    step_total_impulse = 0.0
    intended_record_indices = []
    for occurrence in occurrences:
        if not isinstance(occurrence, Mapping):
            records.append(
                {
                    "class": "UNKNOWN_CONTACT",
                    "side": None,
                    "pair": None,
                    "manifold_points": [],
                    "gate_failures": ["occurrence_not_mapping"],
                }
            )
            continue
        fragments = occurrence.get("fragments")
        if not isinstance(fragments, Sequence) or not fragments:
            records.append(
                {
                    "class": "UNKNOWN_CONTACT",
                    "side": None,
                    "pair": occurrence.get("canonical_pair"),
                    "manifold_points": [],
                    "gate_failures": ["fragment_authority"],
                }
            )
            continue
        first_header = fragments[0].get("header") if isinstance(
            fragments[0], Mapping
        ) else None
        if not isinstance(first_header, Mapping):
            actor_paths = set()
            collider_paths = set()
        else:
            actor_paths = {first_header.get("actor0"), first_header.get("actor1")}
            collider_paths = {
                first_header.get("collider0"),
                first_header.get("collider1"),
            }
        paths_known = bool(
            len(actor_paths) == 2
            and len(collider_paths) == 2
            and actor_paths <= known_bodies
            and collider_paths <= known_colliders
        )
        intended = intended_by_pair.get(frozenset(collider_paths))
        pair_record = {
            "body_paths": sorted(actor_paths) if paths_known else None,
            "collider_paths": sorted(collider_paths) if paths_known else None,
        }
        if not paths_known:
            records.append(
                {
                    "class": "UNKNOWN_CONTACT",
                    "side": None,
                    "pair": pair_record,
                    "manifold_points": [],
                    "gate_failures": ["unknown_path"],
                }
            )
            continue
        if intended is None:
            if actor_paths & robot_bodies:
                contact_class = "PROHIBITED_CONTACT"
                failures = ["robot_pair_not_allowed"]
            elif frozenset(collider_paths) in baseline_pairs:
                contact_class = "BACKGROUND"
                failures = []
            else:
                contact_class = "PROHIBITED_CONTACT"
                failures = ["new_source_or_nonrobot_pair"]
            records.append(
                {
                    "class": contact_class,
                    "side": None,
                    "pair": pair_record,
                    "manifold_points": [],
                    "gate_failures": failures,
                }
            )
            continue

        side = intended["side"]
        finger_body = intended["finger_body"]
        manifold_points = []
        failures = []
        manifold_authority = True
        speed_limit = (
            limits["precontact_speed"]
            if phase in {"INSERT", "SETTLE"}
            else limits["close_speed"]
        )
        if phase not in precontact_phases | close_phases:
            failures.append("phase")
        try:
            finger_pre = body_state(pre_body_states, finger_body)
            source_pre = body_state(pre_body_states, source_body_path)
            finger_post = body_state(post_body_states, finger_body)
            source_post = body_state(post_body_states, source_body_path)
            for fragment in fragments:
                if not isinstance(fragment, Mapping) or not isinstance(
                    fragment.get("header"), Mapping
                ):
                    raise ValueError("fragment")
                header = fragment["header"]
                fragment_actors = {header.get("actor0"), header.get("actor1")}
                fragment_colliders = {
                    header.get("collider0"),
                    header.get("collider1"),
                }
                if (
                    fragment_actors != actor_paths
                    or fragment_colliders != collider_paths
                    or finger_body not in fragment_actors
                    or source_body_path not in fragment_actors
                ):
                    raise ValueError("fragment")
                finger_is_actor0 = header.get("actor0") == finger_body
                orientation_sign = 1.0 if finger_is_actor0 else -1.0
                if normal_convention == "actor1_to_actor0":
                    orientation_sign *= -1.0
                raw_points = fragment.get("contact_data")
                raw_friction = fragment.get("friction_anchors")
                if (
                    not isinstance(raw_points, Sequence)
                    or not raw_points
                    or not isinstance(raw_friction, Sequence)
                ):
                    raise ValueError("fragment")
                for point_record in raw_points:
                    if not isinstance(point_record, Mapping):
                        raise ValueError("point")
                    point = vector(point_record.get("position"))
                    normal = (
                        vector(point_record.get("normal"), unit=True)
                        * orientation_sign
                    )
                    impulse = vector(point_record.get("impulse")) * orientation_sign
                    separation = finite_number(point_record.get("separation"))
                    radial = center - point
                    inward = radial - axis * float(radial @ axis)
                    inward_norm = float(np.linalg.norm(inward))
                    if inward_norm <= 1.0e-12:
                        raise ValueError("inward")
                    inward = inward / inward_norm
                    height = float((point - center) @ axis)
                    cosine = float(normal @ inward)
                    penetration = max(0.0, -separation)
                    relative_speed = max(
                        float(
                            np.linalg.norm(
                                point_velocity(finger_pre, point)
                                - point_velocity(source_pre, point)
                            )
                        ),
                        float(
                            np.linalg.norm(
                                point_velocity(finger_post, point)
                                - point_velocity(source_post, point)
                            )
                        ),
                    )
                    normal_impulse = float(impulse @ inward)
                    total_impulse = float(np.linalg.norm(impulse))
                    point_failures = []
                    if not height_band[0] <= height <= height_band[1]:
                        point_failures.append("height")
                    if cosine < limits["minimum_cosine"]:
                        point_failures.append("normal")
                    if penetration > limits["penetration"]:
                        point_failures.append("penetration")
                    if relative_speed > speed_limit:
                        point_failures.append("relative_speed")
                    if normal_impulse < 0.0:
                        point_failures.append("normal_impulse_direction")
                    failures.extend(point_failures)
                    step_normal_impulse += max(0.0, normal_impulse)
                    step_total_impulse += total_impulse
                    manifold_points.append(
                        {
                            "position_m": point.tolist(),
                            "normal_finger_to_source_world": normal.tolist(),
                            "separation_m": separation,
                            "penetration_m": penetration,
                            "relative_speed_m_s": relative_speed,
                            "normal_impulse_n_s": normal_impulse,
                            "total_impulse_n_s": total_impulse,
                            "source_height_m": height,
                            "inward_normal_cosine": cosine,
                            "gate_failures": sorted(set(point_failures)),
                        }
                    )
                for anchor in raw_friction:
                    if not isinstance(anchor, Mapping):
                        raise ValueError("friction")
                    vector(anchor.get("position"))
                    step_total_impulse += float(
                        np.linalg.norm(vector(anchor.get("impulse")))
                    )
        except (KeyError, TypeError, ValueError):
            manifold_authority = False
            failures.append("manifold_authority")

        contact_class = (
            "UNKNOWN_CONTACT"
            if not manifold_authority
            else "PROHIBITED_CONTACT"
            if failures
            else "INTENDED_PRECONTACT"
            if phase in precontact_phases
            else "INTENDED_CLOSE_CONTACT"
        )
        records.append(
            {
                "class": contact_class,
                "side": side,
                "pair": pair_record,
                "current": occurrence.get("current") is True,
                "transient": occurrence.get("transient") is True,
                "manifold_points": manifold_points,
                "gate_failures": sorted(set(failures)),
            }
        )
        intended_record_indices.append(len(records) - 1)

    episode_normal = episode_normal_before + step_normal_impulse
    episode_total = episode_total_before + step_total_impulse
    global_failures = []
    if step_normal_impulse > limits["step_normal_impulse"]:
        global_failures.append("step_normal_impulse")
    if step_total_impulse > limits["step_total_impulse"]:
        global_failures.append("step_total_impulse")
    if episode_normal > limits["episode_normal_impulse"]:
        global_failures.append("episode_normal_impulse")
    if episode_total > limits["episode_total_impulse"]:
        global_failures.append("episode_total_impulse")
    if global_failures:
        for index in intended_record_indices:
            if records[index]["class"] != "UNKNOWN_CONTACT":
                records[index]["class"] = "PROHIBITED_CONTACT"
                records[index]["gate_failures"] = sorted(
                    set(records[index]["gate_failures"] + global_failures)
                )

    records.sort(key=canonical_json_sha256)
    class_counts = dict(
        sorted(Counter(record["class"] for record in records).items())
    )
    if source_motion_authority_failure or class_counts.get("UNKNOWN_CONTACT", 0):
        terminal_kind = "PROTOCOL_FAILURE"
    elif source_motion_failure:
        terminal_kind = "PHYSICAL_MOTION_FAILURE"
    elif class_counts.get("PROHIBITED_CONTACT", 0):
        terminal_kind = "PHYSICAL_CONTACT_FAILURE"
    else:
        terminal_kind = None
    latch_records = [
        record for record in records if record["class"] == "INTENDED_PRECONTACT"
    ]
    precontact_latch = (
        {
            "physics_step": physics_step,
            "sides": sorted({record["side"] for record in latch_records}),
            "records": latch_records,
        }
        if terminal_kind is None
        and phase in {"INSERT", "SETTLE"}
        and latch_records
        else None
    )
    payload = {
        "authority": "controlled_contact_complete_immediate_report_v1",
        "physics_step": physics_step,
        "phase": phase,
        "records": records,
        "class_counts": class_counts,
        "terminal_kind": terminal_kind,
        "precontact_latch": precontact_latch,
        "step_normal_impulse_n_s": step_normal_impulse,
        "step_total_impulse_n_s": step_total_impulse,
        "episode_normal_impulse_n_s": episode_normal,
        "episode_total_impulse_n_s": episode_total,
        "source_linear_speed_m_s": source_linear_speed,
        "source_angular_speed_rad_s": source_angular_speed,
        "source_linear_finite_difference_speed_m_s": (
            source_linear_finite_difference_speed
        ),
        "source_angular_finite_difference_speed_rad_s": (
            source_angular_finite_difference_speed
        ),
        "source_motion_authority_valid": not source_motion_authority_failure,
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def build_precontact_continuation_lease(
    *,
    applied_receipt: Mapping[str, Any],
    contact_physics_index: int,
    contact_substep_slot: int,
    substeps_per_interval: int,
    contact_evidence_sha256: str,
) -> dict[str, Any]:
    if not isinstance(applied_receipt, Mapping):
        raise ValueError("precontact_applied_receipt_invalid")
    receipt = deepcopy(dict(applied_receipt))
    if receipt.get("authority") != "controlled_action_applied_receipt_v1":
        raise ValueError("precontact_applied_receipt_invalid")
    phase = receipt.get("phase")
    expected_kind = {"INSERT": "ARM_INSERT", "SETTLE": "ARM_SETTLE"}.get(phase)
    if expected_kind is None or receipt.get("semantic_action_kind") != expected_kind:
        raise ValueError("precontact_receipt_phase_invalid")
    if receipt.get("channel") != "arm" or receipt.get("applied") is not True:
        raise ValueError("precontact_applied_receipt_invalid")
    _sha256(receipt.get("action_sha256"), field="precontact_action_sha256")
    token = validate_target_token(receipt.get("target_token"))
    if receipt.get("target_token_sha256") != token["sha256"]:
        raise ValueError("precontact_receipt_target_mismatch")
    for field in ("control_index", "action_index", "apply_index", "interval_index"):
        _index(receipt.get(field), field=f"precontact_{field}")

    physics_index = _index(
        contact_physics_index, field="precontact_contact_physics_index"
    )
    slot = _index(contact_substep_slot, field="precontact_contact_substep_slot")
    total = _index(substeps_per_interval, field="precontact_substeps_per_interval")
    if total <= 0 or slot <= 0 or slot > total:
        raise ValueError("precontact_substep_slot_invalid")
    evidence_sha256 = _sha256(
        contact_evidence_sha256, field="precontact_evidence_sha256"
    )
    payload = {
        "authority": "precontact_continuation_lease_v1",
        "command_phase": phase,
        "effective_phase": "PRECONTACT_SETTLE",
        "contact_physics_index": physics_index,
        "contact_substep_slot": slot,
        "remaining_substep_slots": list(range(slot + 1, total + 1)),
        "substeps_per_interval": total,
        "contact_evidence_sha256": evidence_sha256,
        "applied_receipt_sha256": canonical_json_sha256(receipt),
        "target_token_sha256": token["sha256"],
        "action_index": receipt["action_index"],
        "interval_index": receipt["interval_index"],
        "articulation_mutation_count": 0,
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}
