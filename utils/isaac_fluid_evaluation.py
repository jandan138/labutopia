"""Isaac-specific adapters for the online fluid evaluation loop."""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Callable

import numpy as np

from utils.controlled_contact import (
    FullContactReportAccumulator,
    PostcontactSourceMotionAccumulator,
    PostcontactToolMotionAccumulator,
    canonical_json_sha256,
    evaluate_controlled_contact_report,
)
from utils.franka_gripper_contract import gripper_aperture_rate_m_s


STRICT_CONTAINMENT_EPSILON_M = 0.00005
TABLETOP_SPILL_BAND_M = 0.02
CONTACT_SENSOR_NAMES = ("left", "right", "hand")
CONTACT_SENSOR_MINIMUM_READY_STEPS = 20
CONTACT_REPORT_HAND_BODY_PATH = "/World/Franka/panda_hand"


class ImmediatePhysxContactReporter:
    """Read and normalize exactly one synchronous PhysX report per step."""

    _EVENT_NAMES = {
        "CONTACT_FOUND": "FOUND",
        "CONTACT_PERSIST": "PERSIST",
        "CONTACT_LOST": "LOST",
    }
    _EVENT_VALUES = {0: "FOUND", 1: "LOST", 2: "PERSIST"}

    def __init__(
        self,
        *,
        get_full_contact_report: Callable[[], Any],
        resolve_path: Callable[[int], Any],
        expected_stage_id: int,
        provisional_background_pairs: Sequence[Sequence[str]] = (),
    ) -> None:
        if not callable(get_full_contact_report) or not callable(resolve_path):
            raise TypeError("full_contact_report_callables_required")
        self._get_full_contact_report = get_full_contact_report
        self._resolve_path = resolve_path
        self._accumulator = FullContactReportAccumulator(
            expected_stage_id=expected_stage_id,
            provisional_background_pairs=provisional_background_pairs,
        )
        self._read_count = 0

    def reset(self) -> None:
        self._accumulator.reset()
        self._read_count = 0

    def _path(self, value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise ValueError("full_contact_report_path_id_invalid")
        try:
            path = str(self._resolve_path(int(value)))
        except Exception as exc:
            raise ValueError("full_contact_report_path_resolution_failed") from exc
        if not path:
            raise ValueError("full_contact_report_path_resolution_failed")
        return path

    @classmethod
    def _event_name(cls, value: Any) -> str:
        name = getattr(value, "name", None)
        if name in cls._EVENT_NAMES:
            return cls._EVENT_NAMES[name]
        try:
            integer = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("full_contact_report_event_type_invalid") from exc
        try:
            return cls._EVENT_VALUES[integer]
        except KeyError as exc:
            raise ValueError("full_contact_report_event_type_invalid") from exc

    @staticmethod
    def _vector(value: Any, *, field: str) -> list[float]:
        try:
            result = [float(item) for item in value]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"full_contact_report_{field}_invalid") from exc
        if len(result) != 3:
            raise ValueError(f"full_contact_report_{field}_invalid")
        return result

    def _header(self, value: Any) -> dict[str, Any]:
        try:
            return {
                "type": self._event_name(value.type),
                "stage_id": int(value.stage_id),
                "actor0": self._path(value.actor0),
                "actor1": self._path(value.actor1),
                "collider0": self._path(value.collider0),
                "collider1": self._path(value.collider1),
                "proto_index0": int(value.proto_index0),
                "proto_index1": int(value.proto_index1),
                "contact_data_offset": int(value.contact_data_offset),
                "num_contact_data": int(value.num_contact_data),
                "friction_anchors_offset": int(value.friction_anchors_offset),
                "num_friction_anchors_data": int(
                    value.num_friction_anchors_data
                ),
            }
        except AttributeError as exc:
            raise ValueError("full_contact_report_header_invalid") from exc

    def _contact(self, value: Any) -> dict[str, Any]:
        try:
            return {
                "position": self._vector(value.position, field="position"),
                "normal": self._vector(value.normal, field="normal"),
                "impulse": self._vector(value.impulse, field="impulse"),
                "separation": float(value.separation),
                "face_index0": int(value.face_index0),
                "face_index1": int(value.face_index1),
                "material0": self._path(value.material0),
                "material1": self._path(value.material1),
            }
        except AttributeError as exc:
            raise ValueError("full_contact_report_contact_invalid") from exc

    def _friction_anchor(self, value: Any) -> dict[str, Any]:
        try:
            return {
                "position": self._vector(
                    value.position, field="friction_position"
                ),
                "impulse": self._vector(
                    value.impulse, field="friction_impulse"
                ),
            }
        except AttributeError as exc:
            raise ValueError("full_contact_report_friction_invalid") from exc

    def sample(
        self,
        *,
        physics_index: int,
        allow_provisional_persist_bootstrap: bool = False,
    ) -> dict[str, Any]:
        report = self._get_full_contact_report()
        read_index = self._read_count
        self._read_count += 1
        if not isinstance(report, tuple) or len(report) != 3:
            raise RuntimeError("full_contact_report_tuple_invalid")
        raw_headers, raw_contacts, raw_friction = report
        try:
            headers = [self._header(value) for value in raw_headers]
            contacts = [self._contact(value) for value in raw_contacts]
            friction = [
                self._friction_anchor(value) for value in raw_friction
            ]
        except TypeError as exc:
            raise RuntimeError("full_contact_report_vectors_invalid") from exc
        result = self._accumulator.consume(
            physics_index=physics_index,
            headers=headers,
            contact_data=contacts,
            friction_anchors=friction,
            allow_provisional_persist_bootstrap=(
                allow_provisional_persist_bootstrap
            ),
        )
        return {
            **result,
            "authority": "physx_immediate_full_contact_report_v1",
            "immediate_read_index": read_index,
            "immediate_read_count": self._read_count,
            # Preserve the full immediate buffer so a downstream sealed route
            # can reconcile occurrence summaries against every raw header.
            "raw_headers": headers,
            "raw_contact_data": contacts,
            "raw_friction_anchors": friction,
        }


def construct_single_rigid_prim(
    single_rigid_prim_type: Any,
    *,
    prim_path: str,
    name: str,
) -> Any:
    kwargs = {"prim_path": prim_path, "name": name}
    if "reset_xform_properties" in inspect.signature(
        single_rigid_prim_type
    ).parameters:
        kwargs["reset_xform_properties"] = False
    return single_rigid_prim_type(**kwargs)


def configure_fluid_world_timing(
    world: Any,
    *,
    physics_dt: float,
    rendering_dt: float,
) -> None:
    world.set_simulation_dt(
        physics_dt=physics_dt,
        rendering_dt=rendering_dt,
    )
    actual_physics_dt = float(world.get_physics_dt())
    actual_rendering_dt = float(world.get_rendering_dt())
    if not math.isclose(actual_physics_dt, physics_dt, abs_tol=1.0e-12):
        raise RuntimeError(
            "fluid_world_physics_dt_mismatch:"
            f"expected={physics_dt}:actual={actual_physics_dt}"
        )
    if not math.isclose(actual_rendering_dt, rendering_dt, abs_tol=1.0e-12):
        raise RuntimeError(
            "fluid_world_rendering_dt_mismatch:"
            f"expected={rendering_dt}:actual={actual_rendering_dt}"
        )


def _inside_frame(point: np.ndarray, frame: Any, epsilon: float) -> bool:
    canonical = frame.world_to_canonical(point)
    return (
        math.hypot(float(canonical[0]), float(canonical[1]))
        <= float(frame.interior_radius) + epsilon
        and float(canonical[2]) >= float(frame.interior_floor) - epsilon
        and float(canonical[2]) < float(frame.rim_height) - epsilon
    )


def classify_transfer_positions(
    positions_world: Any,
    *,
    source_frame: Any,
    target_frame: Any,
    table_z: float,
    minimum_target_particles: int,
    minimum_task_target_fraction: float,
    minimum_expert_target_fraction: float,
    epsilon: float = STRICT_CONTAINMENT_EPSILON_M,
    tabletop_spill_band_m: float = TABLETOP_SPILL_BAND_M,
) -> dict[str, Any]:
    values = np.asarray(positions_world, dtype=np.float64)
    if values.ndim != 2 or values.shape[1:] != (3,):
        raise ValueError("transfer_positions_shape_invalid")
    if type(minimum_target_particles) is not int or minimum_target_particles <= 0:
        raise ValueError("minimum_target_particles_invalid")
    for name, fraction in (
        ("minimum_task_target_fraction", minimum_task_target_fraction),
        ("minimum_expert_target_fraction", minimum_expert_target_fraction),
    ):
        if (
            isinstance(fraction, bool)
            or not isinstance(fraction, (int, float, np.number))
            or not math.isfinite(float(fraction))
            or not 0.0 < float(fraction) <= 1.0
        ):
            raise ValueError(f"{name}_invalid")
    if minimum_expert_target_fraction < minimum_task_target_fraction:
        raise ValueError("minimum_expert_target_fraction_below_task")
    if not math.isfinite(table_z):
        raise ValueError("table_z_invalid")

    counts = {
        "source": 0,
        "target": 0,
        "below_table": 0,
        "tabletop_spill": 0,
        "transit": 0,
        "nonfinite": 0,
    }
    category_points = {
        name: []
        for name in ("source", "target", "below_table", "tabletop_spill", "transit")
    }
    for point in values:
        if not np.isfinite(point).all():
            counts["nonfinite"] += 1
            continue
        if _inside_frame(point, source_frame, epsilon):
            category = "source"
        elif _inside_frame(point, target_frame, epsilon):
            category = "target"
        elif point[2] < table_z - epsilon:
            category = "below_table"
        elif point[2] <= table_z + tabletop_spill_band_m:
            category = "tabletop_spill"
        else:
            category = "transit"
        counts[category] += 1
        category_points[category].append(point)

    category_bounds = {}
    for category, points in category_points.items():
        if not points:
            continue
        category_values = np.asarray(points, dtype=np.float64)
        category_bounds[category] = {
            "min": category_values.min(axis=0).tolist(),
            "max": category_values.max(axis=0).tolist(),
        }

    particle_count = int(len(values))
    finite_total = sum(counts[key] for key in counts if key != "nonfinite")
    partition_complete = finite_total + counts["nonfinite"] == particle_count
    valid = counts["nonfinite"] == 0 and partition_complete
    strict_transfer_passed = (
        valid
        and counts["target"] >= minimum_target_particles
        and counts["below_table"] == 0
        and counts["tabletop_spill"] == 0
        and counts["transit"] == 0
    )
    fractions = {
        f"{name}_fraction": float(count) / particle_count
        for name, count in counts.items()
    }
    fractions["spill_fraction"] = (
        float(counts["tabletop_spill"] + counts["below_table"])
        / particle_count
    )
    fractions["partition_fraction_total"] = sum(
        fractions[f"{name}_fraction"] for name in counts
    )
    task_transfer_passed = (
        valid
        and counts["target"] >= minimum_target_particles
        and fractions["target_fraction"]
        >= float(minimum_task_target_fraction)
    )
    expert_transfer_passed = (
        valid
        and counts["target"] >= minimum_target_particles
        and fractions["target_fraction"]
        >= float(minimum_expert_target_fraction)
    )
    return {
        **counts,
        **fractions,
        "particle_count": particle_count,
        "finite_partition_total": finite_total,
        "partition_complete": partition_complete,
        "valid": valid,
        "fluid_transfer_passed": strict_transfer_passed,
        "strict_zero_spill_transfer_passed": strict_transfer_passed,
        "task_transfer_passed": task_transfer_passed,
        "expert_transfer_passed": expert_transfer_passed,
        "minimum_target_particles": minimum_target_particles,
        "minimum_task_target_fraction": float(minimum_task_target_fraction),
        "minimum_expert_target_fraction": float(minimum_expert_target_fraction),
        "epsilon_m": float(epsilon),
        "tabletop_spill_band_m": float(tabletop_spill_band_m),
        "category_bounds_world_m": category_bounds,
        "assignment_priority": [
            "nonfinite",
            "source",
            "target",
            "below_table",
            "tabletop_spill",
            "transit",
        ],
    }


def scripted_grasp_is_closed(controller: Any) -> bool:
    phase = getattr(getattr(controller, "current_phase", None), "value", None)
    pick_controller = getattr(controller, "pick_controller", None)
    event = getattr(pick_controller, "_event", -1)
    return phase == "picking" and isinstance(event, int) and event >= 5


def scripted_pour_velocity_was_emitted(controller: Any) -> bool:
    phase = getattr(getattr(controller, "current_phase", None), "value", None)
    pour_controller = getattr(controller, "pour_controller", None)
    emitted_event = getattr(pour_controller, "_last_emitted_event", None)
    return phase == "pouring" and emitted_event == 2


def _controller_request(controller: Any, name: str) -> bool | None:
    request = getattr(controller, name, None)
    if not callable(request):
        return None
    result = request()
    if type(result) is not bool:
        raise TypeError(f"{name}_must_return_bool")
    return result


def fluid_grasp_attachment_requested(controller: Any) -> bool:
    requested = _controller_request(
        controller, "online_fluid_grasp_attachment_requested"
    )
    return scripted_grasp_is_closed(controller) if requested is None else requested


def fluid_grasp_contact_requested(controller: Any) -> bool:
    requested = _controller_request(
        controller, "online_fluid_grasp_contact_requested"
    )
    if requested is not None:
        return requested
    pick_controller = getattr(controller, "pick_controller", None)
    request = getattr(pick_controller, "grasp_contact_requested", None)
    if callable(request):
        result = request()
        if type(result) is not bool:
            raise TypeError("grasp_contact_requested_must_return_bool")
        return result
    event = getattr(pick_controller, "_event", -1)
    return isinstance(event, int) and event >= 5


def fluid_grasp_lift_requested(controller: Any) -> bool:
    requested = _controller_request(
        controller, "online_fluid_grasp_lift_requested"
    )
    if requested is not None:
        return requested
    pick_controller = getattr(controller, "pick_controller", None)
    request = getattr(pick_controller, "lift_command_emitted", None)
    if not callable(request):
        return False
    result = request()
    if type(result) is not bool:
        raise TypeError("lift_command_emitted_must_return_bool")
    return result


def fluid_rotation_handoff_requested(controller: Any) -> bool:
    requested = _controller_request(
        controller, "online_fluid_rotation_handoff_requested"
    )
    return (
        scripted_pour_velocity_was_emitted(controller)
        if requested is None
        else requested
    )


def _affine_matrix(value: Any, *, name: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(f"{name}_matrix_invalid")
    if not np.allclose(matrix[:, 3], [0.0, 0.0, 0.0, 1.0], atol=1.0e-10):
        raise ValueError(f"{name}_matrix_not_row_affine")
    return np.ascontiguousarray(matrix)


def _rigid_affine_matrix(value: Any, *, name: str) -> np.ndarray:
    matrix = _affine_matrix(value, name=name)
    rotation = matrix[:3, :3]
    if not np.allclose(
        rotation @ rotation.T,
        np.eye(3, dtype=np.float64),
        rtol=0.0,
        atol=1.0e-6,
    ):
        raise ValueError(f"{name}_matrix_not_rigid")
    determinant = float(np.linalg.det(rotation))
    if not math.isclose(determinant, 1.0, rel_tol=0.0, abs_tol=1.0e-6):
        raise ValueError(f"{name}_matrix_not_right_handed")
    return matrix


def _matrix_sha256(matrix: np.ndarray) -> str:
    encoded = json.dumps(
        matrix.tolist(),
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def evaluate_preclose_source_motion(
    *,
    reference_center_world_m: Any,
    reference_source_world_matrix: Any,
    current_center_world_m: Any,
    current_source_world_matrix: Any,
    vessel_axis_object: Any,
    translation_limit_m: Any,
    tilt_limit_degrees: Any,
) -> dict[str, Any]:
    """Evaluate source-center translation and configured-axis tilt."""

    def vector(value: Any, *, name: str) -> np.ndarray:
        result = np.asarray(value, dtype=np.float64)
        if result.shape != (3,) or not np.isfinite(result).all():
            raise ValueError(f"preclose_source_motion_{name}_invalid")
        return result

    def positive_number(value: Any, *, name: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, np.number))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
        ):
            raise ValueError(f"preclose_source_motion_{name}_invalid")
        return float(value)

    reference_center = vector(
        reference_center_world_m,
        name="reference_center_world_m",
    )
    current_center = vector(
        current_center_world_m,
        name="current_center_world_m",
    )
    try:
        reference_world = _rigid_affine_matrix(
            reference_source_world_matrix,
            name="preclose_source_motion_reference_source_world",
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "preclose_source_motion_reference_source_world_matrix_invalid"
        ) from exc
    try:
        current_world = _rigid_affine_matrix(
            current_source_world_matrix,
            name="preclose_source_motion_current_source_world",
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "preclose_source_motion_current_source_world_matrix_invalid"
        ) from exc
    axis_object = vector(vessel_axis_object, name="vessel_axis_object")
    axis_norm = float(np.linalg.norm(axis_object))
    if axis_norm <= 1.0e-12:
        raise ValueError("preclose_source_motion_vessel_axis_object_invalid")
    axis_object /= axis_norm
    translation_limit = positive_number(
        translation_limit_m,
        name="translation_limit_m",
    )
    tilt_limit = positive_number(
        tilt_limit_degrees,
        name="tilt_limit_degrees",
    )

    reference_axis = axis_object @ reference_world[:3, :3]
    current_axis = axis_object @ current_world[:3, :3]
    reference_axis /= np.linalg.norm(reference_axis)
    current_axis /= np.linalg.norm(current_axis)
    translation = float(np.linalg.norm(current_center - reference_center))
    cosine = float(np.clip(np.dot(reference_axis, current_axis), -1.0, 1.0))
    tilt = float(np.degrees(np.arccos(cosine)))
    translation_valid = bool(translation <= translation_limit + 1.0e-12)
    tilt_valid = bool(tilt <= tilt_limit + 1.0e-9)
    return {
        "translation_m": translation,
        "tilt_degrees": tilt,
        "translation_limit_m": translation_limit,
        "tilt_limit_degrees": tilt_limit,
        "translation_boundary_tolerance_m": 1.0e-12,
        "tilt_boundary_tolerance_degrees": 1.0e-9,
        "translation_valid": translation_valid,
        "tilt_valid": tilt_valid,
        "passed": bool(translation_valid and tilt_valid),
        "vessel_axis_object": axis_object.tolist(),
        "reference_axis_world": reference_axis.tolist(),
        "current_axis_world": current_axis.tolist(),
    }


def relative_source_to_gripper_matrix(
    source_world_matrix: Any,
    gripper_world_matrix: Any,
) -> np.ndarray:
    source = _affine_matrix(source_world_matrix, name="source_world")
    gripper = _affine_matrix(gripper_world_matrix, name="gripper_world")
    return np.ascontiguousarray(source @ np.linalg.inv(gripper))


def attached_source_world_matrix(
    source_to_gripper_matrix: Any,
    gripper_world_matrix: Any,
) -> np.ndarray:
    relative = _affine_matrix(source_to_gripper_matrix, name="source_to_gripper")
    gripper = _affine_matrix(gripper_world_matrix, name="gripper_world")
    return np.ascontiguousarray(relative @ gripper)


def _pose_jump(before: Any, after: Any) -> tuple[float, float]:
    source = _rigid_affine_matrix(before, name="pose_jump_before")
    target = _rigid_affine_matrix(after, name="pose_jump_after")
    translation = float(np.linalg.norm(target[3, :3] - source[3, :3]))
    relative_rotation = source[:3, :3] @ target[:3, :3].T
    cosine = float(np.clip((np.trace(relative_rotation) - 1.0) / 2.0, -1.0, 1.0))
    rotation_degrees = float(np.degrees(np.arccos(cosine)))
    return translation, rotation_degrees


def derive_minimum_per_finger_normal_impulse(
    *,
    effective_payload_mass_kg: float,
    effective_friction: float,
    physics_dt: float,
    gravity_m_s2: float,
) -> dict[str, Any]:
    """Derive the symmetric two-pad impulse needed to support the payload."""
    values = {
        "effective_payload_mass_kg": effective_payload_mass_kg,
        "effective_friction": effective_friction,
        "physics_dt": physics_dt,
        "gravity_m_s2": gravity_m_s2,
    }
    for name, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, np.number))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
        ):
            raise ValueError(f"contact_gate_{name}_invalid")
    safety_factor = 2.0
    supporting_finger_count = 2
    threshold = (
        safety_factor
        * float(effective_payload_mass_kg)
        * float(gravity_m_s2)
        * float(physics_dt)
        / (supporting_finger_count * float(effective_friction))
    )
    if not math.isfinite(threshold) or threshold <= 0.0:
        raise ValueError("contact_gate_derived_impulse_threshold_invalid")
    return {
        **{name: float(value) for name, value in values.items()},
        "safety_factor": safety_factor,
        "supporting_finger_count": supporting_finger_count,
        "minimum_per_finger_normal_impulse_n_s": threshold,
        "formula": (
            "safety_factor*effective_payload_mass_kg*gravity_m_s2*physics_dt/"
            "(supporting_finger_count*effective_friction)"
        ),
    }


class BilateralContactGraspGate:
    """Qualify fresh contacts using load and source-relative geometry."""

    def __init__(
        self,
        *,
        source_body_path: str,
        source_collider_path: str,
        left_finger_body_path: str,
        right_finger_body_path: str,
        minimum_normal_impulse_n_s: float,
        minimum_side_projection_m: float,
        required_consecutive_steps: int,
        grasp_height_axis_object: Any,
        grasp_height_band_m: Any,
        maximum_bilateral_height_difference_m: float,
        minimum_inward_normal_cosine: float,
        minimum_opposing_normal_cosine: float,
        maximum_finger_speed_m_s: float = 0.002,
    ) -> None:
        paths = (
            source_body_path,
            source_collider_path,
            left_finger_body_path,
            right_finger_body_path,
        )
        if any(not isinstance(path, str) or not path.startswith("/") for path in paths):
            raise ValueError("contact_gate_body_path_invalid")
        if len({source_body_path, left_finger_body_path, right_finger_body_path}) != 3:
            raise ValueError("contact_gate_body_paths_must_be_distinct")
        for name, value in (
            ("minimum_normal_impulse_n_s", minimum_normal_impulse_n_s),
            ("minimum_side_projection_m", minimum_side_projection_m),
            ("maximum_finger_speed_m_s", maximum_finger_speed_m_s),
            (
                "maximum_bilateral_height_difference_m",
                maximum_bilateral_height_difference_m,
            ),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"contact_gate_{name}_invalid")
        for name, value in (
            ("minimum_inward_normal_cosine", minimum_inward_normal_cosine),
            ("minimum_opposing_normal_cosine", minimum_opposing_normal_cosine),
        ):
            if not math.isfinite(value) or not 0.0 < value <= 1.0:
                raise ValueError(f"contact_gate_{name}_invalid")
        if type(required_consecutive_steps) is not int or required_consecutive_steps <= 0:
            raise ValueError("contact_gate_required_consecutive_steps_invalid")
        height_axis = self._finite_vector(
            grasp_height_axis_object,
            name="grasp_height_axis_object",
        )
        height_axis_norm = float(np.linalg.norm(height_axis))
        if height_axis_norm <= 1.0e-12:
            raise ValueError("contact_gate_grasp_height_axis_object_invalid")
        height_band = np.asarray(grasp_height_band_m, dtype=np.float64)
        if (
            height_band.shape != (2,)
            or not np.isfinite(height_band).all()
            or not height_band[0] < height_band[1]
        ):
            raise ValueError("contact_gate_grasp_height_band_m_invalid")

        self.source_body_path = source_body_path
        self.source_collider_path = source_collider_path
        self.left_finger_body_path = left_finger_body_path
        self.right_finger_body_path = right_finger_body_path
        self.minimum_normal_impulse_n_s = float(minimum_normal_impulse_n_s)
        self.minimum_side_projection_m = float(minimum_side_projection_m)
        self.required_consecutive_steps = required_consecutive_steps
        self.maximum_finger_speed_m_s = float(maximum_finger_speed_m_s)
        self.grasp_height_axis_object = height_axis / height_axis_norm
        self.grasp_height_band_m = height_band
        self.maximum_bilateral_height_difference_m = float(
            maximum_bilateral_height_difference_m
        )
        self.minimum_inward_normal_cosine = float(
            minimum_inward_normal_cosine
        )
        self.minimum_opposing_normal_cosine = float(
            minimum_opposing_normal_cosine
        )
        self.reset()

    def reset(self) -> None:
        self.consecutive_steps = 0
        self.qualified = False
        self.last_physics_step: int | None = None
        self.last_record: dict[str, Any] = {
            "qualified": False,
            "valid_this_step": False,
            "consecutive_steps": 0,
            "failure_reason": None,
        }

    @staticmethod
    def _finite_vector(value: Any, *, name: str) -> np.ndarray:
        vector = np.asarray(value, dtype=np.float64)
        if vector.shape != (3,) or not np.isfinite(vector).all():
            raise ValueError(f"contact_gate_{name}_invalid")
        return vector

    @staticmethod
    def _weighted_mean(values: list[np.ndarray], weights: list[float]) -> np.ndarray:
        weight_array = np.asarray(weights, dtype=np.float64)
        if float(np.sum(weight_array)) <= 1.0e-15:
            weight_array = np.ones(len(values), dtype=np.float64)
        return np.average(np.asarray(values), axis=0, weights=weight_array)

    def update(
        self,
        *,
        physics_step: int,
        contacts: Sequence[Mapping[str, Any]],
        source_center_world_m: Any,
        source_world_matrix: Any,
        finger_side_axis_world: Any,
        finger_speeds_m_s: Any | None = None,
    ) -> bool:
        if type(physics_step) is not int or physics_step < 0:
            raise ValueError("contact_gate_physics_step_invalid")
        if not isinstance(contacts, Sequence):
            raise TypeError("contact_gate_contacts_sequence_required")
        center = self._finite_vector(
            source_center_world_m, name="source_center_world_m"
        )
        source_world = _rigid_affine_matrix(
            source_world_matrix,
            name="contact_gate_source_world",
        )
        inverse_source_world = np.linalg.inv(source_world)
        center_object = np.concatenate([center, [1.0]]) @ inverse_source_world
        axis = self._finite_vector(
            finger_side_axis_world, name="finger_side_axis_world"
        )
        axis_norm = float(np.linalg.norm(axis))
        if axis_norm <= 1.0e-12:
            raise ValueError("contact_gate_finger_side_axis_world_invalid")
        axis /= axis_norm

        speed_valid = True
        speed_values = None
        if finger_speeds_m_s is not None:
            speeds = np.asarray(finger_speeds_m_s, dtype=np.float64).reshape(-1)
            if speeds.shape != (2,) or not np.isfinite(speeds).all():
                raise ValueError("contact_gate_finger_speeds_invalid")
            speed_valid = bool(
                np.max(np.abs(speeds)) <= self.maximum_finger_speed_m_s
            )
            speed_values = speeds.tolist()

        per_finger = {
            self.left_finger_body_path: {
                "impulse": 0.0,
                "positions": [],
                "normals": [],
                "heights": [],
                "inward_cosines": [],
                "weights": [],
                "source_colliders": [],
            },
            self.right_finger_body_path: {
                "impulse": 0.0,
                "positions": [],
                "normals": [],
                "heights": [],
                "inward_cosines": [],
                "weights": [],
                "source_colliders": [],
            },
        }
        stale = (
            self.last_physics_step is not None
            and physics_step != self.last_physics_step + 1
        )
        for contact in contacts:
            if not isinstance(contact, Mapping):
                raise TypeError("contact_gate_contact_mapping_required")
            contact_step = contact.get("physics_step")
            if contact_step != physics_step:
                stale = True
                continue
            body0 = contact.get("body0_path")
            body1 = contact.get("body1_path")
            finger_path = None
            source_collider = None
            source_normal_sign = 0.0
            if body0 == self.source_body_path and body1 in per_finger:
                finger_path = body1
                source_collider = contact.get("collider0_path")
                source_normal_sign = 1.0
            elif body1 == self.source_body_path and body0 in per_finger:
                finger_path = body0
                source_collider = contact.get("collider1_path")
                source_normal_sign = -1.0
            if finger_path is None:
                continue
            position = self._finite_vector(
                contact.get("position_world_m"), name="position_world_m"
            )
            normal = self._finite_vector(
                contact.get("normal_body1_to_body0_world"),
                name="normal_body1_to_body0_world",
            )
            normal_norm = float(np.linalg.norm(normal))
            if normal_norm <= 1.0e-12:
                raise ValueError("contact_gate_normal_body1_to_body0_world_invalid")
            normal_on_source = source_normal_sign * normal / normal_norm
            impulse = contact.get("normal_impulse_n_s")
            if (
                isinstance(impulse, bool)
                or not isinstance(impulse, (int, float, np.number))
                or not math.isfinite(float(impulse))
                or float(impulse) < 0.0
            ):
                raise ValueError("contact_gate_normal_impulse_invalid")
            position_object = (
                np.concatenate([position, [1.0]]) @ inverse_source_world
            )
            height = float(
                np.dot(
                    position_object[:3] - center_object[:3],
                    self.grasp_height_axis_object,
                )
            )
            inward = center - position
            inward_norm = float(np.linalg.norm(inward))
            inward_cosine = (
                -1.0
                if inward_norm <= 1.0e-12
                else float(np.dot(normal_on_source, inward / inward_norm))
            )
            values = per_finger[finger_path]
            values["impulse"] += float(impulse)
            values["positions"].append(position)
            values["normals"].append(normal_on_source)
            values["heights"].append(height)
            values["inward_cosines"].append(inward_cosine)
            values["weights"].append(float(impulse))
            values["source_colliders"].append(source_collider)

        self.last_physics_step = physics_step
        paths = (self.left_finger_body_path, self.right_finger_body_path)
        impulses = [per_finger[path]["impulse"] for path in paths]
        bilateral = all(per_finger[path]["positions"] for path in paths)
        side_projections: list[float] = []
        heights: list[float] = []
        representative_normals: list[np.ndarray] = []
        if bilateral:
            for path in paths:
                values = per_finger[path]
                mean_position = self._weighted_mean(
                    values["positions"], values["weights"]
                )
                mean_normal = self._weighted_mean(
                    values["normals"], values["weights"]
                )
                mean_normal_norm = float(np.linalg.norm(mean_normal))
                if mean_normal_norm <= 1.0e-12:
                    mean_normal = np.zeros(3, dtype=np.float64)
                else:
                    mean_normal /= mean_normal_norm
                side_projections.append(float(np.dot(mean_position - center, axis)))
                heights.append(
                    float(
                        np.average(
                            values["heights"],
                            weights=(
                                values["weights"]
                                if sum(values["weights"]) > 1.0e-15
                                else None
                            ),
                        )
                    )
                )
                representative_normals.append(mean_normal)

        named_opposite_sides = bool(
            bilateral
            and side_projections[0]
            <= -self.minimum_side_projection_m + 1.0e-7
            and side_projections[1]
            >= self.minimum_side_projection_m - 1.0e-7
        )
        source_collider_valid = bool(
            bilateral
            and all(
                collider == self.source_collider_path
                for path in paths
                for collider in per_finger[path]["source_colliders"]
            )
        )
        low_height, high_height = self.grasp_height_band_m
        height_band_valid = bool(
            bilateral
            and all(
                low_height - 1.0e-12 <= height <= high_height + 1.0e-12
                for path in paths
                for height in per_finger[path]["heights"]
            )
        )
        inward_normals_valid = bool(
            bilateral
            and all(
                cosine + 1.0e-12 >= self.minimum_inward_normal_cosine
                for path in paths
                for cosine in per_finger[path]["inward_cosines"]
            )
        )
        opposing_normal_cosine = (
            None
            if not bilateral
            else float(np.dot(representative_normals[0], representative_normals[1]))
        )
        opposing_normals_valid = bool(
            bilateral
            and opposing_normal_cosine
            <= -self.minimum_opposing_normal_cosine + 1.0e-12
        )
        bilateral_height_valid = bool(
            bilateral
            and abs(heights[0] - heights[1])
            <= self.maximum_bilateral_height_difference_m + 1.0e-12
        )
        impulses_valid = all(
            impulse + 1.0e-12 >= self.minimum_normal_impulse_n_s
            for impulse in impulses
        )
        checks = (
            (stale, "contact_physics_step_discontinuity"),
            (not bilateral, "contact_not_bilateral"),
            (not source_collider_valid, "contact_source_collider_not_external_shell"),
            (not named_opposite_sides, "contact_not_on_named_opposite_sides"),
            (not height_band_valid, "contact_outside_grasp_band"),
            (not inward_normals_valid, "contact_normal_not_inward"),
            (not opposing_normals_valid, "contact_normals_not_opposed"),
            (not bilateral_height_valid, "contact_bilateral_height_mismatch"),
            (not impulses_valid, "contact_load_below_threshold"),
            (not speed_valid, "contact_finger_speed_not_settled"),
        )
        failure_reason = next((reason for failed, reason in checks if failed), None)
        valid = failure_reason is None
        self.consecutive_steps = self.consecutive_steps + 1 if valid else 0
        self.qualified = self.consecutive_steps >= self.required_consecutive_steps
        self.last_record = {
            "qualified": self.qualified,
            "valid_this_step": valid,
            "physics_step": physics_step,
            "consecutive_steps": self.consecutive_steps,
            "required_consecutive_steps": self.required_consecutive_steps,
            "source_collider_path": self.source_collider_path,
            "source_collider_valid": source_collider_valid,
            "normal_impulse_n_s": {
                "left": impulses[0],
                "right": impulses[1],
            },
            "minimum_normal_impulse_n_s": self.minimum_normal_impulse_n_s,
            "side_projection_m": {
                "left": side_projections[0] if bilateral else None,
                "right": side_projections[1] if bilateral else None,
            },
            "height_m": {
                "left": heights[0] if bilateral else None,
                "right": heights[1] if bilateral else None,
            },
            "grasp_height_axis_object": self.grasp_height_axis_object.tolist(),
            "grasp_height_band_m": self.grasp_height_band_m.tolist(),
            "height_band_valid": height_band_valid,
            "maximum_bilateral_height_difference_m": (
                self.maximum_bilateral_height_difference_m
            ),
            "bilateral_height_valid": bilateral_height_valid,
            "inward_normal_cosine_min": {
                "left": (
                    min(per_finger[paths[0]]["inward_cosines"])
                    if bilateral
                    else None
                ),
                "right": (
                    min(per_finger[paths[1]]["inward_cosines"])
                    if bilateral
                    else None
                ),
            },
            "minimum_inward_normal_cosine": self.minimum_inward_normal_cosine,
            "inward_normals_valid": inward_normals_valid,
            "opposing_normal_cosine": opposing_normal_cosine,
            "minimum_opposing_normal_cosine": self.minimum_opposing_normal_cosine,
            "opposing_normals_valid": opposing_normals_valid,
            "stale": stale,
            "bilateral": bilateral,
            "opposite_sides": named_opposite_sides,
            "finger_speed_valid": speed_valid,
            "finger_speeds_m_s": speed_values,
            "finger_speed_semantics": "per_pad_relative_prismatic_speed_m_s",
            "aperture_rate_m_s": (
                None
                if speed_values is None
                else gripper_aperture_rate_m_s(speed_values)
            ),
            "failure_reason": failure_reason,
        }
        return self.qualified

    def record(self) -> dict[str, Any]:
        return dict(self.last_record)


def normalize_contact_sensor_frames(
    frames: Mapping[str, Mapping[str, Any]],
    *,
    expected_physics_step: int,
    resolve_body_path: Callable[[str], str] | None = None,
    expected_sensor_names: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Convert Isaac 4.1 raw contact frames into deterministic gate records."""
    if not isinstance(frames, Mapping) or not frames:
        raise TypeError("contact_sensor_frames_mapping_required")
    if type(expected_physics_step) is not int or expected_physics_step < 0:
        raise ValueError("contact_sensor_expected_physics_step_invalid")
    if resolve_body_path is not None and not callable(resolve_body_path):
        raise TypeError("contact_sensor_body_resolver_callable_required")
    if expected_sensor_names is not None:
        expected_names = tuple(str(name) for name in expected_sensor_names)
        if (
            not expected_names
            or len(set(expected_names)) != len(expected_names)
            or set(frames) != set(expected_names)
        ):
            raise ValueError(
                "contact_sensor_frame_set_mismatch:"
                f"expected={sorted(expected_names)}:actual={sorted(frames)}"
            )

    result: list[dict[str, Any]] = []
    seen: dict[tuple[Any, ...], tuple[tuple[Any, ...], int]] = {}
    for sensor_name in sorted(frames):
        frame = frames[sensor_name]
        if not isinstance(frame, Mapping):
            raise TypeError("contact_sensor_frame_mapping_required")
        raw_step = frame.get("physics_step")
        if (
            isinstance(raw_step, bool)
            or not isinstance(raw_step, (int, float, np.number))
            or not math.isfinite(float(raw_step))
            or not float(raw_step).is_integer()
            or int(raw_step) != expected_physics_step
        ):
            raise ValueError(
                "contact_sensor_frame_step_mismatch:"
                f"sensor={sensor_name}:expected={expected_physics_step}:"
                f"actual={raw_step}"
            )
        if "contacts" not in frame:
            raise ValueError(
                f"contact_sensor_raw_contacts_required:{sensor_name}"
            )
        raw_contacts = frame["contacts"]
        if not isinstance(raw_contacts, Sequence):
            raise TypeError("contact_sensor_contacts_sequence_required")
        for raw in raw_contacts:
            if not isinstance(raw, Mapping):
                raise TypeError("contact_sensor_contact_mapping_required")
            collider0 = raw.get("body0")
            collider1 = raw.get("body1")
            if any(
                not isinstance(path, str) or not path.startswith("/")
                for path in (collider0, collider1)
            ):
                raise ValueError("contact_sensor_body_path_invalid")
            body0 = collider0
            body1 = collider1
            if resolve_body_path is not None:
                body0 = resolve_body_path(body0)
                body1 = resolve_body_path(body1)
            position = np.asarray(raw.get("position"), dtype=np.float64)
            normal = np.asarray(raw.get("normal"), dtype=np.float64)
            impulse = np.asarray(raw.get("impulse"), dtype=np.float64)
            if any(
                vector.shape != (3,) or not np.isfinite(vector).all()
                for vector in (position, normal, impulse)
            ):
                raise ValueError("contact_sensor_vector_invalid")
            normal_norm = float(np.linalg.norm(normal))
            if normal_norm <= 1.0e-12:
                raise ValueError("contact_sensor_normal_invalid")
            normal /= normal_norm
            if (body1, collider1) < (body0, collider0):
                body0, body1 = body1, body0
                collider0, collider1 = collider1, collider0
                normal = -normal
                impulse = -impulse
            normal_impulse = abs(float(np.dot(impulse, normal)))
            key = (
                body0,
                body1,
                collider0,
                collider1,
                tuple(np.round(position, decimals=8).tolist()),
            )
            signature = (
                tuple(np.round(normal, decimals=8).tolist()),
                tuple(np.round(impulse, decimals=10).tolist()),
                round(normal_impulse, 10),
            )
            previous = seen.get(key)
            if previous is not None:
                previous_signature, result_index = previous
                if signature != previous_signature:
                    raise ValueError("contact_sensor_duplicate_conflict")
                result[result_index]["sensor_names"].append(sensor_name)
                continue
            seen[key] = (signature, len(result))
            result.append(
                {
                    "physics_step": expected_physics_step,
                    "body0_path": body0,
                    "body1_path": body1,
                    "collider0_path": collider0,
                    "collider1_path": collider1,
                    "position_world_m": tuple(position.tolist()),
                    "normal_body1_to_body0_world": tuple(normal.tolist()),
                    "impulse_body1_to_body0_world": tuple(impulse.tolist()),
                    "normal_convention": "body1_to_body0_world",
                    "normal_impulse_n_s": normal_impulse,
                    "sensor_names": [sensor_name],
                }
            )
    return result


class _PhysicsViewWriterAuditProxy:
    def __init__(self, target: Any, audit: Any, surface: str) -> None:
        self._target = target
        self._audit = audit
        self._surface = surface

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)

    def set_kinematic_targets(self, *args: Any, **kwargs: Any) -> Any:
        self._audit._record_call(self._surface)
        return self._target.set_kinematic_targets(*args, **kwargs)


class SourceBodyWriterAudit:
    """Observe known source-body command surfaces without blocking writes."""

    SOURCE_BODY_SURFACES = (
        "source_body.set_world_pose",
        "source_body.set_local_pose",
        "source_body.set_linear_velocity",
        "source_body.set_angular_velocity",
    )
    KINEMATIC_TARGET_SURFACE = "physics_view.set_kinematic_targets"
    OBJECT_UTILS_SURFACE = "object_utils.set_object_position"
    REQUIRED_SURFACES = (
        *SOURCE_BODY_SURFACES,
        KINEMATIC_TARGET_SURFACE,
        OBJECT_UTILS_SURFACE,
    )
    _OBJECT_UTILS_REGISTRY_ATTRIBUTE = (
        "_labutopia_source_body_writer_audit_registry"
    )

    def __init__(self, *, source_body_path: str) -> None:
        if not isinstance(source_body_path, str) or not source_body_path.startswith(
            "/"
        ):
            raise ValueError("source_writer_audit_body_path_invalid")
        self.source_body_path = source_body_path
        self._coverage: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._installed = False

    def _record_call(self, surface: str) -> None:
        self._events.append(
            {
                "sequence": len(self._events),
                "surface": surface,
                "source_body_path": self.source_body_path,
            }
        )

    def _instrument_method(
        self,
        target: Any,
        method_name: str,
        surface: str,
    ) -> bool:
        original = getattr(target, method_name, None)
        coverage = {
            "surface": surface,
            "target_type": type(target).__name__,
            "method_name": method_name,
            "available": callable(original),
            "installed": False,
            "installation_mode": None,
        }
        self._coverage[surface] = coverage
        if not callable(original):
            coverage["failure_reason"] = "callable_unavailable"
            return False

        @functools.wraps(original)
        def instrumented(*args: Any, **kwargs: Any) -> Any:
            self._record_call(surface)
            return original(*args, **kwargs)

        try:
            setattr(target, method_name, instrumented)
        except (AttributeError, TypeError) as exc:
            coverage["failure_reason"] = type(exc).__name__
            return False
        coverage["installed"] = True
        coverage["installation_mode"] = "instance_method_wrapper"
        return True

    def _instrument_physics_view(self, source_body: Any) -> None:
        surface = self.KINEMATIC_TARGET_SURFACE
        prim_view = getattr(source_body, "_prim_view", None)
        physics_view = getattr(prim_view, "_physics_view", None)
        if prim_view is None or physics_view is None:
            self._coverage[surface] = {
                "surface": surface,
                "target_type": None,
                "method_name": "set_kinematic_targets",
                "available": False,
                "installed": False,
                "installation_mode": None,
                "failure_reason": "physics_view_unavailable",
            }
            return
        if self._instrument_method(
            physics_view,
            "set_kinematic_targets",
            surface,
        ):
            return
        original = getattr(physics_view, "set_kinematic_targets", None)
        coverage = self._coverage[surface]
        if not callable(original):
            return
        try:
            prim_view._physics_view = _PhysicsViewWriterAuditProxy(
                physics_view,
                self,
                surface,
            )
        except (AttributeError, TypeError) as exc:
            coverage["failure_reason"] = (
                "physics_view_proxy_" + type(exc).__name__
            )
            return
        coverage.update(
            {
                "available": True,
                "installed": True,
                "installation_mode": "physics_view_proxy",
                "failure_reason": None,
            }
        )

    @staticmethod
    def _object_utils_call_path(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        if "object_path" in kwargs:
            return kwargs["object_path"]
        return args[0] if args else None

    def _instrument_object_utils(self, object_utils: Any) -> None:
        surface = self.OBJECT_UTILS_SURFACE
        original = getattr(object_utils, "set_object_position", None)
        coverage = {
            "surface": surface,
            "target_type": type(object_utils).__name__,
            "method_name": "set_object_position",
            "available": callable(original),
            "installed": False,
            "installation_mode": None,
        }
        self._coverage[surface] = coverage
        if not callable(original):
            coverage["failure_reason"] = "callable_unavailable"
            return

        registry = getattr(
            object_utils,
            self._OBJECT_UTILS_REGISTRY_ATTRIBUTE,
            None,
        )
        if registry is None:
            registry = {"audits": {}}

            @functools.wraps(original)
            def instrumented(*args: Any, **kwargs: Any) -> Any:
                path = self._object_utils_call_path(args, kwargs)
                path_string = None if path is None else str(path)
                audit = registry["audits"].get(path_string)
                if audit is not None:
                    audit._record_call(audit.OBJECT_UTILS_SURFACE)
                return original(*args, **kwargs)

            try:
                setattr(
                    object_utils,
                    self._OBJECT_UTILS_REGISTRY_ATTRIBUTE,
                    registry,
                )
                setattr(object_utils, "set_object_position", instrumented)
            except (AttributeError, TypeError) as exc:
                coverage["failure_reason"] = type(exc).__name__
                return
        elif not (
            isinstance(registry, dict)
            and isinstance(registry.get("audits"), dict)
        ):
            coverage["failure_reason"] = "registry_invalid"
            return
        registry["audits"][self.source_body_path] = self
        coverage["installed"] = True
        coverage["installation_mode"] = "source_path_registry_wrapper"

    def install(self, *, source_body: Any, object_utils: Any) -> dict[str, Any]:
        if self._installed:
            return self.record()
        for surface in self.SOURCE_BODY_SURFACES:
            self._instrument_method(
                source_body,
                surface.rsplit(".", 1)[1],
                surface,
            )
        self._instrument_physics_view(source_body)
        self._instrument_object_utils(object_utils)
        self._installed = True
        return self.record()

    def reset(self) -> None:
        self._events = []

    def record(self) -> dict[str, Any]:
        counts = {surface: 0 for surface in self.REQUIRED_SURFACES}
        for event in self._events:
            counts[event["surface"]] += 1
        covered = [
            surface
            for surface in self.REQUIRED_SURFACES
            if self._coverage.get(surface, {}).get("installed") is True
        ]
        missing = [
            surface for surface in self.REQUIRED_SURFACES if surface not in covered
        ]
        coverage_limits = [
            "raw_usd_attribute_writes_not_intercepted",
            "source_prim_view_plural_pose_velocity_setters_not_intercepted",
            "instrumented_object_replacement_not_intercepted",
            *[
                f"required_surface_not_intercepted:{surface}"
                for surface in missing
            ],
        ]
        source_write_count = sum(
            counts[surface]
            for surface in (*self.SOURCE_BODY_SURFACES, self.OBJECT_UTILS_SURFACE)
        )
        kinematic_count = counts[self.KINEMATIC_TARGET_SURFACE]
        call_count = source_write_count + kinematic_count
        coverage_complete = self._installed and not missing
        return {
            "source_body_path": self.source_body_path,
            "installed": self._installed,
            "required_surfaces": list(self.REQUIRED_SURFACES),
            "covered_surfaces": covered,
            "coverage": {
                surface: dict(self._coverage.get(surface, {}))
                for surface in self.REQUIRED_SURFACES
            },
            "coverage_complete": coverage_complete,
            "coverage_limits": coverage_limits,
            "calls": [dict(event) for event in self._events],
            "counts": counts,
            "call_count": call_count,
            "source_pose_write_count_after_play": source_write_count,
            "source_velocity_write_count_after_play": (
                counts["source_body.set_linear_velocity"]
                + counts["source_body.set_angular_velocity"]
            ),
            "object_utils_source_position_write_count_after_play": counts[
                self.OBJECT_UTILS_SURFACE
            ],
            "kinematic_target_update_count": kinematic_count,
            "valid": bool(coverage_complete and call_count == 0),
        }


class ContactFrictionDynamicVessel:
    """Monitor a PhysX-only beaker grasp without writing its pose."""

    def __init__(
        self,
        *,
        source_body_path: str,
        source_collider_path: str,
        left_finger_body_path: str,
        right_finger_body_path: str,
        read_source_world_matrix: Callable[[], Any],
        read_source_center_world: Callable[[], Any],
        read_gripper_world_matrix: Callable[[], Any],
        read_finger_world_matrices: Callable[[], Sequence[Any]],
        read_contact_sensor_frames: Callable[[], Mapping[str, Mapping[str, Any]]],
        read_physics_step: Callable[[], int],
        read_finger_joint_velocities: Callable[[], Any],
        physics_dt: float,
        minimum_normal_impulse_n_s: float,
        minimum_side_projection_m: float,
        required_consecutive_steps: int,
        maximum_finger_speed_m_s: float,
        grasp_height_axis_object: Any,
        grasp_height_band_m: Any,
        maximum_bilateral_height_difference_m: float,
        minimum_inward_normal_cosine: float,
        minimum_opposing_normal_cosine: float,
        contact_timeout_s: float,
        contact_loss_grace_steps: int,
        preclose_source_translation_limit_m: float,
        preclose_source_tilt_limit_degrees: float,
        minimum_normal_impulse_derivation: Mapping[str, Any] | None = None,
        resolve_body_path: Callable[[str], str] | None = None,
        source_writer_audit: Any | None = None,
        require_complete_writer_audit: bool = False,
        immediate_contact_reporter: Any | None = None,
        controlled_contact_classifier: Callable[..., Mapping[str, Any]] | None = None,
        read_controlled_body_states: Callable[[], Mapping[str, Any]] | None = None,
        controlled_contact_baseline_collider_pairs: Sequence[Sequence[str]] = (),
        controlled_settle_required_steps: int = 60,
        controlled_precontact_settle_required_steps: int = 60,
        controlled_close_required_steps: int | None = None,
        controlled_contact_settle_required_steps: int = 60,
        controlled_pregrasp_deadline_steps: int = 3000,
        controlled_align_deadline_steps: int = 9000,
        controlled_insert_deadline_steps: int = 7200,
        controlled_settle_deadline_steps: int = 600,
        controlled_precontact_settle_deadline_steps: int = 300,
        controlled_close_deadline_steps: int = 900,
        controlled_contact_settle_deadline_steps: int = 300,
        allow_preclose_contact: bool = False,
    ) -> None:
        readers = (
            read_source_world_matrix,
            read_source_center_world,
            read_gripper_world_matrix,
            read_finger_world_matrices,
            read_contact_sensor_frames,
            read_physics_step,
            read_finger_joint_velocities,
        )
        if not all(callable(reader) for reader in readers):
            raise TypeError("dynamic_contact_grasp_reader_required")
        if not math.isfinite(physics_dt) or physics_dt <= 0.0:
            raise ValueError("dynamic_contact_grasp_physics_dt_invalid")
        if not math.isfinite(contact_timeout_s) or contact_timeout_s <= 0.0:
            raise ValueError("dynamic_contact_grasp_timeout_invalid")
        if type(contact_loss_grace_steps) is not int or contact_loss_grace_steps < 0:
            raise ValueError("dynamic_contact_grasp_loss_grace_invalid")
        if type(require_complete_writer_audit) is not bool:
            raise TypeError("dynamic_contact_grasp_writer_audit_requirement_bool")
        if source_writer_audit is not None and not all(
            callable(getattr(source_writer_audit, name, None))
            for name in ("reset", "record")
        ):
            raise TypeError("dynamic_contact_grasp_writer_audit_invalid")
        if (immediate_contact_reporter is None) != (
            controlled_contact_classifier is None
        ):
            raise ValueError("dynamic_contact_immediate_monitor_pair_required")
        if immediate_contact_reporter is not None and not all(
            callable(getattr(immediate_contact_reporter, name, None))
            for name in ("reset", "sample")
        ):
            raise TypeError("dynamic_contact_immediate_reporter_invalid")
        if (
            controlled_contact_classifier is not None
            and not callable(controlled_contact_classifier)
        ):
            raise TypeError("dynamic_contact_classifier_invalid")
        if (immediate_contact_reporter is None) != (
            read_controlled_body_states is None
        ):
            raise ValueError("dynamic_contact_body_state_reader_pair_required")
        baseline_pairs = []
        for pair in controlled_contact_baseline_collider_pairs:
            if (
                not isinstance(pair, Sequence)
                or isinstance(pair, (str, bytes, bytearray))
                or len(pair) != 2
                or any(not isinstance(path, str) or not path for path in pair)
                or pair[0] == pair[1]
            ):
                raise ValueError("dynamic_contact_baseline_pair_invalid")
            baseline_pairs.append(tuple(sorted(pair)))
        if len(baseline_pairs) != len(set(baseline_pairs)):
            raise ValueError("dynamic_contact_baseline_pair_duplicate")
        if baseline_pairs and immediate_contact_reporter is None:
            raise ValueError("dynamic_contact_baseline_requires_immediate_report")
        if controlled_close_required_steps is None:
            controlled_close_required_steps = required_consecutive_steps
        certificate_requirements = {
            "SETTLE": controlled_settle_required_steps,
            "PRECONTACT_SETTLE": controlled_precontact_settle_required_steps,
            "CLOSE": controlled_close_required_steps,
            "CONTACT_SETTLE": controlled_contact_settle_required_steps,
        }
        if any(
            type(value) is not int or value <= 0
            for value in certificate_requirements.values()
        ):
            raise ValueError("dynamic_contact_certificate_steps_invalid")
        if controlled_close_required_steps != required_consecutive_steps:
            raise ValueError("dynamic_contact_close_certificate_mismatch")
        phase_deadlines = {
            "PREGRASP": controlled_pregrasp_deadline_steps,
            "ALIGN": controlled_align_deadline_steps,
            "INSERT": controlled_insert_deadline_steps,
            "SETTLE": controlled_settle_deadline_steps,
            "PRECONTACT_SETTLE": controlled_precontact_settle_deadline_steps,
            "CLOSE": controlled_close_deadline_steps,
            "CONTACT_SETTLE": controlled_contact_settle_deadline_steps,
        }
        if any(
            type(value) is not int or value <= 0
            for value in phase_deadlines.values()
        ):
            raise ValueError("dynamic_contact_phase_deadline_invalid")
        for name, value in (
            ("preclose_source_translation_limit_m", preclose_source_translation_limit_m),
            ("preclose_source_tilt_limit_degrees", preclose_source_tilt_limit_degrees),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"dynamic_contact_grasp_{name}_invalid")

        self._read_source_world = read_source_world_matrix
        self._read_source_center_world = read_source_center_world
        self._read_gripper_world = read_gripper_world_matrix
        self._read_finger_worlds = read_finger_world_matrices
        self._read_contact_frames = read_contact_sensor_frames
        self._read_physics_step = read_physics_step
        self._read_finger_velocities = read_finger_joint_velocities
        self._resolve_body_path = resolve_body_path
        self._source_writer_audit = source_writer_audit
        self._require_complete_writer_audit = require_complete_writer_audit
        self._immediate_contact_reporter = immediate_contact_reporter
        self._controlled_contact_classifier = controlled_contact_classifier
        self._read_controlled_body_states = read_controlled_body_states
        self._controlled_contact_baseline_pairs = tuple(sorted(baseline_pairs))
        self._controlled_certificate_requirements = certificate_requirements
        self._controlled_phase_deadlines = phase_deadlines
        self._timeout_steps = int(math.ceil(contact_timeout_s / physics_dt))
        self._loss_grace_steps = contact_loss_grace_steps
        self._allow_preclose_contact = allow_preclose_contact
        self._preclose_translation_limit_m = float(
            preclose_source_translation_limit_m
        )
        self._preclose_tilt_limit_degrees = float(
            preclose_source_tilt_limit_degrees
        )
        if allow_preclose_contact:
            self._preclose_translation_limit_m = 1.0e9
            self._preclose_tilt_limit_degrees = 1.0e9
        if minimum_normal_impulse_derivation is None:
            self._minimum_normal_impulse_derivation = None
        else:
            if not isinstance(minimum_normal_impulse_derivation, Mapping):
                raise TypeError("dynamic_contact_grasp_impulse_derivation_mapping_required")
            derived_threshold = minimum_normal_impulse_derivation.get(
                "minimum_per_finger_normal_impulse_n_s"
            )
            if (
                isinstance(derived_threshold, bool)
                or not isinstance(derived_threshold, (int, float, np.number))
                or not math.isclose(
                    float(derived_threshold),
                    float(minimum_normal_impulse_n_s),
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ):
                raise ValueError("dynamic_contact_grasp_impulse_derivation_mismatch")
            self._minimum_normal_impulse_derivation = dict(
                minimum_normal_impulse_derivation
            )
        self._gate = BilateralContactGraspGate(
            source_body_path=source_body_path,
            source_collider_path=source_collider_path,
            left_finger_body_path=left_finger_body_path,
            right_finger_body_path=right_finger_body_path,
            minimum_normal_impulse_n_s=minimum_normal_impulse_n_s,
            minimum_side_projection_m=minimum_side_projection_m,
            required_consecutive_steps=required_consecutive_steps,
            maximum_finger_speed_m_s=maximum_finger_speed_m_s,
            grasp_height_axis_object=grasp_height_axis_object,
            grasp_height_band_m=grasp_height_band_m,
            maximum_bilateral_height_difference_m=(
                maximum_bilateral_height_difference_m
            ),
            minimum_inward_normal_cosine=minimum_inward_normal_cosine,
            minimum_opposing_normal_cosine=minimum_opposing_normal_cosine,
        )
        self._grasp_height_axis_object = self._gate.grasp_height_axis_object.copy()
        self.reset()

    def reset(self) -> None:
        if self._source_writer_audit is not None:
            self._source_writer_audit.reset()
        self._gate.reset()
        if self._immediate_contact_reporter is not None:
            self._immediate_contact_reporter.reset()
        reset_classifier = getattr(
            self._controlled_contact_classifier, "reset", None
        )
        if callable(reset_classifier):
            reset_classifier()
        self._monitoring = False
        self._monitoring_steps = 0
        self._preclose_monitoring_steps = 0
        self._contact_acquisition_steps = 0
        self._monitoring_start_physics_step: int | None = None
        self._controller: Any | None = None
        self._preclose_source_center: np.ndarray | None = None
        self._preclose_source_world: np.ndarray | None = None
        reset_source_world = _rigid_affine_matrix(
            self._read_source_world(),
            name="dynamic_contact_grasp_reset_source_world",
        )
        reset_source_center = np.asarray(
            self._read_source_center_world(), dtype=np.float64
        )
        if (
            reset_source_center.shape != (3,)
            or not np.isfinite(reset_source_center).all()
        ):
            raise ValueError("dynamic_contact_grasp_reset_source_center_invalid")
        self._reset_source_world = reset_source_world.copy()
        self._reset_source_center = reset_source_center.copy()
        self._pre_roll_max_source_translation_m = 0.0
        self._pre_roll_max_source_tilt_degrees = 0.0
        self._preclose_max_source_translation_m = 0.0
        self._preclose_max_source_tilt_degrees = 0.0
        self._during_close_max_source_translation_m = 0.0
        self._during_close_max_source_tilt_degrees = 0.0
        self._monitoring_max_source_translation_m = 0.0
        self._monitoring_max_source_tilt_degrees = 0.0
        self._close_command_observed = False
        self._lift_command_observed = False
        self._first_unexpected_contact: dict[str, Any] | None = None
        self._first_failure_physics_step: int | None = None
        self._acquired = False
        self._loss_steps = 0
        self._failure_reason: str | None = None
        self._observed_relative: np.ndarray | None = None
        self._relative_translation_drift_m = 0.0
        self._relative_rotation_drift_degrees = 0.0
        self._last_sampled_physics_step: int | None = None
        self._contact_sensor_consecutive_current_steps = 0
        self._contact_sensor_last_validated_physics_step: int | None = None
        self._contact_sensor_last_sampled_physics_step: int | None = None
        self._contact_sensor_last_failure_reason: str | None = None
        self._last_raw_contact_counts: dict[str, int | None] = {
            name: None for name in CONTACT_SENSOR_NAMES
        }
        self._last_normalized_contact_count = 0
        self._last_qualifying_contact_count = 0
        self._immediate_report_sample_count = 0
        self._last_immediate_report: dict[str, Any] | None = None
        self._last_controlled_classification: dict[str, Any] | None = None
        self._controlled_pre_body_states: dict[str, Any] | None = None
        self._controlled_effective_phase: str | None = None
        self._controlled_certificate_streaks = {
            phase: 0 for phase in self._controlled_certificate_requirements
        }
        self._controlled_phase_elapsed_steps = {
            phase: 0 for phase in self._controlled_phase_deadlines
        }
        self._precontact_deadline_origin_latched = False
        self._controlled_contact_baseline_observed: list[list[str]] | None = None
        self._controlled_contact_baseline_validated: bool | None = None
        self._sensor_immediate_agreement_valid: bool | None = None
        self._last_sensor_immediate_missing_pairs: list[list[str]] = []

    def _controlled_step_decision(self, physics_step: int) -> dict[str, Any] | None:
        if self._immediate_contact_reporter is None:
            return None
        report = self._immediate_contact_reporter.sample(
            physics_index=physics_step,
            allow_provisional_persist_bootstrap=(
                self._immediate_report_sample_count == 0
            ),
        )
        self._immediate_report_sample_count += 1
        if not isinstance(report, Mapping):
            raise TypeError("dynamic_contact_immediate_report_mapping_required")
        self._last_immediate_report = dict(report)
        if not self._monitoring:
            phase = "PRE_ROLL"
            controller_phase = phase
        else:
            if self._controller is None:
                raise RuntimeError("dynamic_contact_controller_missing")
            context = self._controller.controlled_contact_action_context()
            if not isinstance(context, Mapping):
                raise TypeError("dynamic_contact_action_context_mapping_required")
            phase = self._controlled_effective_phase or context.get("phase")
            controller_phase = context.get("controller_phase", phase)
        if not isinstance(phase, str) or not phase:
            raise RuntimeError("dynamic_contact_action_phase_missing")
        if not isinstance(controller_phase, str) or not controller_phase:
            raise RuntimeError("dynamic_contact_controller_phase_missing")
        classification = self._controlled_contact_classifier(
            report=report,
            phase=phase,
            pre_body_states=self._controlled_pre_body_states,
            post_body_states=self._read_controlled_body_states(),
        )
        if not isinstance(classification, Mapping):
            raise TypeError("dynamic_contact_classification_mapping_required")
        classification = dict(classification)
        self._last_controlled_classification = classification
        self._update_controlled_classification_certificate(
            phase=phase,
            classification=classification,
        )
        if phase in self._controlled_phase_elapsed_steps:
            self._controlled_phase_elapsed_steps[phase] += 1
        terminal_kind = classification.get("terminal_kind")
        if terminal_kind is not None:
            if not isinstance(terminal_kind, str) or not terminal_kind:
                raise ValueError("dynamic_contact_terminal_kind_invalid")
            return {
                "kind": "TERMINAL",
                "terminal_kind": terminal_kind,
                "classification": classification,
            }
        latch = classification.get("precontact_latch")
        evidence_sha256 = None
        if latch is not None:
            if not isinstance(latch, Mapping):
                raise TypeError("dynamic_contact_precontact_latch_mapping_required")
            evidence_sha256 = classification.get("evidence_sha256")
            if not isinstance(evidence_sha256, str):
                raise ValueError("dynamic_contact_evidence_sha256_invalid")
        legal_successors = {
            "PREGRASP": {"ALIGN"},
            "ALIGN": {"INSERT"},
            "INSERT": {"SETTLE", "PRECONTACT_SETTLE"},
        }
        phase_exit_observed = bool(
            latch is not None
            or controller_phase in legal_successors.get(phase, set())
        )
        timeout = self._controlled_phase_timeout_decision(
            phase,
            phase_exit_observed=phase_exit_observed,
        )
        if timeout is not None:
            return timeout
        if latch is None:
            decision = {"kind": "CONTINUE"}
            elapsed = self._controlled_phase_elapsed_steps.get(phase)
            deadline = self._controlled_phase_deadlines.get(phase)
            if (
                phase_exit_observed
                and elapsed is not None
                and deadline is not None
                and elapsed == deadline
            ):
                decision["phase_deadline_exit_grace"] = {
                    "phase": phase,
                    "controller_phase": controller_phase,
                    "phase_elapsed_steps": elapsed,
                    "phase_deadline_steps": deadline,
                }
            return decision
        return {
            "kind": "INTENDED_PRECONTACT",
            "evidence": {
                "authority": "controlled_contact_complete_manifold_v1",
                "physics_step": latch.get("physics_step"),
                "sides": list(latch.get("sides", ())),
                "records": [dict(record) for record in latch.get("records", ())],
                "evidence_sha256": evidence_sha256,
            },
        }

    def set_controlled_effective_phase(self, phase: str) -> None:
        if phase not in {
            "PREGRASP",
            "ALIGN",
            "INSERT",
            "SETTLE",
            "PRECONTACT_SETTLE",
            "CLOSE",
            "CONTACT_SETTLE",
        }:
            raise ValueError("dynamic_contact_effective_phase_invalid")
        if phase != self._controlled_effective_phase:
            if phase in self._controlled_certificate_streaks:
                self._controlled_certificate_streaks[phase] = 0
            if phase == "PRECONTACT_SETTLE":
                self._precontact_deadline_origin_latched = False
        self._controlled_effective_phase = phase

    def _update_controlled_classification_certificate(
        self,
        *,
        phase: str,
        classification: Mapping[str, Any],
    ) -> None:
        if phase not in {"SETTLE", "PRECONTACT_SETTLE"}:
            return
        records = classification.get("records")
        if not isinstance(records, Sequence):
            self._controlled_certificate_streaks[phase] = 0
            return
        if phase == "SETTLE":
            valid = bool(
                classification.get("terminal_kind") is None
                and not any(
                    isinstance(record, Mapping)
                    and record.get("class")
                    in {"INTENDED_PRECONTACT", "INTENDED_CLOSE_CONTACT"}
                    for record in records
                )
            )
        else:
            valid = bool(
                classification.get("terminal_kind") is None
                and any(
                    isinstance(record, Mapping)
                    and record.get("class") == "INTENDED_PRECONTACT"
                    and record.get("current") is True
                    and record.get("transient") is not True
                    for record in records
                )
            )
        self._controlled_certificate_streaks[phase] = (
            self._controlled_certificate_streaks[phase] + 1 if valid else 0
        )

    def _update_controlled_gate_certificate(
        self,
        *,
        phase: str,
        valid_this_step: bool,
    ) -> None:
        if phase not in {"CLOSE", "CONTACT_SETTLE"}:
            return
        self._controlled_certificate_streaks[phase] = (
            self._controlled_certificate_streaks[phase] + 1
            if valid_this_step
            else 0
        )

    def _controlled_phase_certificates(self) -> dict[str, Any]:
        return {
            phase: {
                "consecutive_steps": self._controlled_certificate_streaks[phase],
                "required_steps": required,
                "ready": self._controlled_certificate_streaks[phase] >= required,
            }
            for phase, required in self._controlled_certificate_requirements.items()
        }

    def _controlled_phase_timeout_decision(
        self,
        phase: str,
        *,
        after_gate: bool = False,
        phase_exit_observed: bool = False,
        at_transaction_boundary: bool = False,
    ) -> dict[str, Any] | None:
        if phase not in self._controlled_phase_deadlines:
            return None
        if (
            phase in {"CLOSE", "CONTACT_SETTLE"}
            and not after_gate
            and not at_transaction_boundary
        ):
            return None
        elapsed = self._controlled_phase_elapsed_steps[phase]
        deadline = self._controlled_phase_deadlines[phase]
        certificate = self._controlled_phase_certificates().get(phase)
        if (
            elapsed < deadline
            or (
                not at_transaction_boundary
                and (
                    (phase_exit_observed and elapsed == deadline)
                    or (certificate is not None and certificate["ready"])
                )
            )
        ):
            return None
        return {
            "kind": "TERMINAL",
            "terminal_kind": "PHYSICAL_TIMEOUT",
            "failure_reason": f"{phase}_timeout",
            "phase_elapsed_steps": elapsed,
            "phase_deadline_steps": deadline,
            "certificate": certificate,
        }

    def validate_controlled_action_phase(self, phase: str) -> dict[str, Any]:
        if phase not in self._controlled_phase_deadlines:
            raise ValueError("dynamic_contact_action_phase_invalid")
        previous = self._controlled_effective_phase
        legal_successors = {
            "PREGRASP": {"ALIGN"},
            "ALIGN": {"INSERT"},
            "INSERT": {"SETTLE", "PRECONTACT_SETTLE"},
            "SETTLE": {"PRECONTACT_SETTLE", "CLOSE"},
            "PRECONTACT_SETTLE": {"CLOSE"},
            "CLOSE": {"CONTACT_SETTLE"},
            "CONTACT_SETTLE": set(),
        }
        if (
            previous is not None
            and phase != previous
            and phase not in legal_successors[previous]
        ):
            return {
                "kind": "TERMINAL",
                "terminal_kind": "PROTOCOL_FAILURE",
                "failure_reason": f"{previous}_to_{phase}_illegal",
                "previous_phase": previous,
                "proposed_phase": phase,
            }
        timeout = self._controlled_phase_timeout_decision(
            phase,
            after_gate=True,
            at_transaction_boundary=True,
        )
        return {"kind": "CONTINUE"} if timeout is None else timeout

    def latch_intended_precontact(self, evidence: Mapping[str, Any]) -> bool:
        if self._controller is None:
            raise RuntimeError("dynamic_contact_controller_missing")
        latch = getattr(self._controller, "latch_intended_precontact", None)
        if not callable(latch):
            raise RuntimeError("dynamic_contact_controller_latch_missing")
        result = latch(evidence)
        if type(result) is not bool:
            raise TypeError("dynamic_contact_controller_latch_bool_required")
        if result:
            self._controlled_phase_elapsed_steps["PRECONTACT_SETTLE"] = 1
            self._precontact_deadline_origin_latched = True
        return result

    def _validated_physics_step(self) -> int:
        physics_step = self._read_physics_step()
        if type(physics_step) is not int or physics_step < 0:
            raise ValueError("dynamic_contact_grasp_physics_step_invalid")
        return physics_step

    def _read_normalized_contact_sample(
        self,
        physics_step: int,
    ) -> list[dict[str, Any]]:
        frames = self._read_contact_frames()
        contacts = normalize_contact_sensor_frames(
            frames,
            expected_physics_step=physics_step,
            resolve_body_path=self._resolve_body_path,
            expected_sensor_names=CONTACT_SENSOR_NAMES,
        )
        self._last_raw_contact_counts = {
            name: len(frames[name]["contacts"]) for name in CONTACT_SENSOR_NAMES
        }
        self._last_normalized_contact_count = len(contacts)
        return contacts

    def _finger_role_contacts(
        self,
        contacts: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        expected_sensor_by_pair = {
            frozenset(
                (self._gate.source_body_path, self._gate.left_finger_body_path)
            ): "left",
            frozenset(
                (self._gate.source_body_path, self._gate.right_finger_body_path)
            ): "right",
        }
        qualifying = []
        for contact in contacts:
            pair = frozenset(
                (contact.get("body0_path"), contact.get("body1_path"))
            )
            expected_sensor = expected_sensor_by_pair.get(pair)
            sensor_names = contact.get("sensor_names", ())
            if expected_sensor is not None and expected_sensor in sensor_names:
                qualifying.append(dict(contact))
        self._last_qualifying_contact_count = len(qualifying)
        return qualifying

    def _sensor_immediate_agreement_failure(
        self,
        contacts: Sequence[Mapping[str, Any]],
        *,
        physics_step: int,
    ) -> str | None:
        if self._immediate_contact_reporter is None:
            return None
        report = self._last_immediate_report
        if (
            not isinstance(report, Mapping)
            or report.get("physics_index") != physics_step
        ):
            self._sensor_immediate_agreement_valid = False
            return "contact_sensor_immediate_authority_invalid"
        occurrences = report.get("occurrences")
        if not isinstance(occurrences, Sequence) or isinstance(
            occurrences, (str, bytes, bytearray)
        ):
            self._sensor_immediate_agreement_valid = False
            return "contact_sensor_immediate_authority_invalid"
        immediate_pairs = set()
        for occurrence in occurrences:
            if not isinstance(occurrence, Mapping):
                self._sensor_immediate_agreement_valid = False
                return "contact_sensor_immediate_authority_invalid"
            fragments = occurrence.get("fragments")
            if not isinstance(fragments, Sequence) or not fragments:
                self._sensor_immediate_agreement_valid = False
                return "contact_sensor_immediate_authority_invalid"
            for fragment in fragments:
                header = (
                    fragment.get("header")
                    if isinstance(fragment, Mapping)
                    else None
                )
                if not isinstance(header, Mapping):
                    self._sensor_immediate_agreement_valid = False
                    return "contact_sensor_immediate_authority_invalid"
                pair = (header.get("collider0"), header.get("collider1"))
                if any(not isinstance(path, str) or not path for path in pair):
                    self._sensor_immediate_agreement_valid = False
                    return "contact_sensor_immediate_authority_invalid"
                immediate_pairs.add(frozenset(pair))
        sensor_pairs = {
            frozenset(
                (contact.get("collider0_path"), contact.get("collider1_path"))
            )
            for contact in contacts
        }
        if any(
            len(pair) != 2
            or any(not isinstance(path, str) or not path for path in pair)
            for pair in sensor_pairs
        ):
            self._sensor_immediate_agreement_valid = False
            return "contact_sensor_immediate_authority_invalid"
        missing = sorted(
            tuple(sorted(pair)) for pair in sensor_pairs.difference(immediate_pairs)
        )
        self._last_sensor_immediate_missing_pairs = [
            list(pair) for pair in missing
        ]
        if missing:
            self._sensor_immediate_agreement_valid = False
            return "contact_sensor_immediate_disagreement"
        if self._sensor_immediate_agreement_valid is not False:
            self._sensor_immediate_agreement_valid = True
        return None

    def _record_valid_contact_sensor_step(self, physics_step: int) -> None:
        previous = self._contact_sensor_last_validated_physics_step
        if previous is None:
            self._contact_sensor_consecutive_current_steps = 1
            self._contact_sensor_last_failure_reason = None
        elif physics_step == previous:
            pass
        elif physics_step == previous + 1:
            self._contact_sensor_consecutive_current_steps += 1
            self._contact_sensor_last_failure_reason = None
        else:
            self._contact_sensor_consecutive_current_steps = 1
            self._contact_sensor_last_failure_reason = (
                "contact_sensor_readiness_step_discontinuity:"
                f"previous={previous}:current={physics_step}"
            )
        self._contact_sensor_last_validated_physics_step = physics_step

    def _read_sample(
        self,
    ) -> tuple[
        int,
        np.ndarray,
        np.ndarray,
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        physics_step = self._validated_physics_step()
        source_world = _rigid_affine_matrix(
            self._read_source_world(), name="dynamic_contact_grasp_source_world"
        )
        source_center = np.asarray(
            self._read_source_center_world(), dtype=np.float64
        )
        if source_center.shape != (3,) or not np.isfinite(source_center).all():
            raise ValueError("dynamic_contact_grasp_source_center_invalid")
        contacts = self._read_normalized_contact_sample(physics_step)
        qualifying_contacts = self._finger_role_contacts(contacts)
        self._contact_sensor_last_sampled_physics_step = physics_step
        self._record_valid_contact_sensor_step(physics_step)
        self._last_sampled_physics_step = physics_step
        return (
            physics_step,
            source_world,
            source_center,
            contacts,
            qualifying_contacts,
        )

    def _update_contact_sensor_readiness(self) -> None:
        try:
            physics_step = self._validated_physics_step()
            self._contact_sensor_last_sampled_physics_step = physics_step
            contacts = self._read_normalized_contact_sample(physics_step)
            self._finger_role_contacts(contacts)
            agreement_failure = self._sensor_immediate_agreement_failure(
                contacts,
                physics_step=physics_step,
            )
            if agreement_failure is not None:
                self._latch_failure(agreement_failure, physics_step)
                self._contact_sensor_last_failure_reason = agreement_failure
                self._contact_sensor_consecutive_current_steps = 0
                return
        except Exception as exc:
            self._contact_sensor_consecutive_current_steps = 0
            self._contact_sensor_last_failure_reason = (
                f"{type(exc).__name__}:{exc}"
            )
            self._last_raw_contact_counts = {
                name: None for name in CONTACT_SENSOR_NAMES
            }
            self._last_normalized_contact_count = 0
            self._last_qualifying_contact_count = 0
            return

        self._record_valid_contact_sensor_step(physics_step)

    def _contact_sensor_readiness_record(self) -> dict[str, Any]:
        try:
            current_physics_step = self._validated_physics_step()
        except (TypeError, ValueError, RuntimeError):
            current_physics_step = None
        current_step_matches = bool(
            current_physics_step is not None
            and self._contact_sensor_last_validated_physics_step
            == current_physics_step
        )
        streak_satisfied = bool(
            self._contact_sensor_consecutive_current_steps
            >= CONTACT_SENSOR_MINIMUM_READY_STEPS
        )
        return {
            "ready": bool(streak_satisfied and current_step_matches),
            "streak_satisfied": streak_satisfied,
            "current_step_matches": current_step_matches,
            "consecutive_current_steps": (
                self._contact_sensor_consecutive_current_steps
            ),
            "required_consecutive_current_steps": (
                CONTACT_SENSOR_MINIMUM_READY_STEPS
            ),
            "last_sampled_physics_step": (
                self._contact_sensor_last_sampled_physics_step
            ),
            "last_validated_physics_step": (
                self._contact_sensor_last_validated_physics_step
            ),
            "current_physics_step": current_physics_step,
            "expected_sensor_names": list(CONTACT_SENSOR_NAMES),
            "hand_role": "diagnostic_only",
            "last_failure_reason": self._contact_sensor_last_failure_reason,
        }

    def _source_writer_audit_record(self) -> dict[str, Any]:
        if self._source_writer_audit is None:
            counts = {
                surface: 0 for surface in SourceBodyWriterAudit.REQUIRED_SURFACES
            }
            return {
                "source_body_path": self._gate.source_body_path,
                "installed": False,
                "required_surfaces": list(
                    SourceBodyWriterAudit.REQUIRED_SURFACES
                ),
                "covered_surfaces": [],
                "coverage": {},
                "coverage_complete": False,
                "coverage_limits": ["source_writer_audit_not_installed"],
                "calls": [],
                "counts": counts,
                "call_count": 0,
                "source_pose_write_count_after_play": 0,
                "source_velocity_write_count_after_play": 0,
                "object_utils_source_position_write_count_after_play": 0,
                "kinematic_target_update_count": 0,
                "valid": False,
            }
        record = self._source_writer_audit.record()
        if not isinstance(record, Mapping):
            raise TypeError("dynamic_contact_grasp_writer_audit_record_mapping")
        return dict(record)

    def _source_writer_authority_failure(self) -> str | None:
        record = self._source_writer_audit_record()
        if (
            self._require_complete_writer_audit
            and record.get("coverage_complete") is not True
        ):
            return "source_writer_audit_coverage_incomplete"
        if record.get("call_count", 0) != 0:
            return "source_writer_observed"
        return None

    def _controlled_contact_baseline_failure(
        self, physics_step: int
    ) -> str | None:
        if not self._controlled_contact_baseline_pairs:
            return None
        report = self._last_immediate_report
        if (
            not isinstance(report, Mapping)
            or report.get("physics_index") != physics_step
        ):
            self._controlled_contact_baseline_validated = False
            return "contact_report_baseline_authority_invalid"
        current_pairs = report.get("current_pairs")
        if not isinstance(current_pairs, Sequence) or isinstance(
            current_pairs, (str, bytes, bytearray)
        ):
            self._controlled_contact_baseline_validated = False
            return "contact_report_baseline_authority_invalid"
        observed = []
        for pair in current_pairs:
            if (
                not isinstance(pair, Sequence)
                or isinstance(pair, (str, bytes, bytearray))
                or len(pair) != 2
            ):
                self._controlled_contact_baseline_validated = False
                return "contact_report_baseline_authority_invalid"
            paths = []
            for endpoint in pair:
                if not isinstance(endpoint, Mapping):
                    self._controlled_contact_baseline_validated = False
                    return "contact_report_baseline_authority_invalid"
                path = endpoint.get("collider_path")
                if not isinstance(path, str) or not path:
                    self._controlled_contact_baseline_validated = False
                    return "contact_report_baseline_authority_invalid"
                paths.append(path)
            if paths[0] == paths[1]:
                self._controlled_contact_baseline_validated = False
                return "contact_report_baseline_authority_invalid"
            observed.append(tuple(sorted(paths)))
        if len(observed) != len(set(observed)):
            self._controlled_contact_baseline_validated = False
            return "contact_report_baseline_authority_invalid"
        observed = sorted(observed)
        self._controlled_contact_baseline_observed = [list(pair) for pair in observed]
        self._controlled_contact_baseline_validated = bool(
            tuple(observed) == self._controlled_contact_baseline_pairs
        )
        return (
            None
            if self._controlled_contact_baseline_validated
            else "contact_report_baseline_pair_mismatch"
        )

    def validate_controlled_preaction_authority(self) -> dict[str, Any]:
        physics_step = self._validated_physics_step()
        readiness = self._contact_sensor_readiness_record()
        failure = None
        if readiness["ready"] is not True:
            failure = "contact_sensor_pre_roll_not_ready"
        if failure is None:
            failure = self._source_writer_authority_failure()
        if failure is None:
            failure = self._controlled_contact_baseline_failure(physics_step)
        if failure is None:
            failure = self._failure_reason
        if failure is None:
            return {"kind": "CONTINUE"}
        self._latch_failure(failure, physics_step)
        return {
            "kind": "TERMINAL",
            "terminal_kind": self._controlled_failure_terminal_kind(failure),
            "failure_reason": failure,
        }

    @staticmethod
    def _controlled_failure_terminal_kind(reason: str) -> str:
        if reason == "contact_timeout":
            return "PHYSICAL_TIMEOUT"
        if reason.startswith("source_translation_") or reason.startswith(
            "source_tilt_"
        ):
            return "PHYSICAL_MOTION_FAILURE"
        if reason in {
            "unexpected_contact_before_close",
            "unexpected_contact_outside_grasp_allowlist",
            "grasp_lost",
        }:
            return "PHYSICAL_CONTACT_FAILURE"
        return "PROTOCOL_FAILURE"

    def _latch_failure(
        self,
        reason: str,
        physics_step: int,
        *,
        unexpected_contact: Mapping[str, Any] | None = None,
    ) -> None:
        if self._failure_reason is not None:
            return
        self._failure_reason = reason
        self._first_failure_physics_step = physics_step
        if unexpected_contact is not None:
            self._first_unexpected_contact = dict(unexpected_contact)

    def maybe_attach(self, controller: Any, state: Mapping[str, Any]) -> bool:
        del state
        if self._monitoring or self._failure_reason is not None:
            return False
        readiness = self._contact_sensor_readiness_record()
        physics_step = readiness["current_physics_step"]
        if readiness["ready"] is not True:
            self._latch_failure(
                "contact_sensor_pre_roll_not_ready",
                0 if physics_step is None else physics_step,
            )
            return False
        writer_failure = self._source_writer_authority_failure()
        if writer_failure is not None:
            self._latch_failure(
                writer_failure,
                physics_step,
            )
            return False
        baseline_failure = self._controlled_contact_baseline_failure(physics_step)
        if baseline_failure is not None:
            self._latch_failure(baseline_failure, physics_step)
            return False
        (
            physics_step,
            source_world,
            source_center,
            contacts,
            _qualifying_contacts,
        ) = self._read_sample()
        self._controller = controller
        self._monitoring_start_physics_step = physics_step
        self._preclose_source_center = source_center.copy()
        self._preclose_source_world = source_world.copy()
        self._monitoring = True
        if contacts and not self._allow_preclose_contact:
            self._latch_failure(
                "unexpected_contact_before_close",
                physics_step,
                unexpected_contact=contacts[0],
            )
        return True

    def _source_height_axis_world(self, source_world: np.ndarray) -> np.ndarray:
        axis = self._grasp_height_axis_object @ source_world[:3, :3]
        norm = float(np.linalg.norm(axis))
        if norm <= 1.0e-12:
            raise ValueError("dynamic_contact_grasp_height_axis_world_invalid")
        return axis / norm

    def update_before_substep(self) -> None:
        if self._read_controlled_body_states is not None:
            value = self._read_controlled_body_states()
            if not isinstance(value, Mapping):
                raise TypeError("dynamic_contact_body_states_mapping_required")
            self._controlled_pre_body_states = dict(value)
        return None

    def _update_preclose_motion(
        self,
        *,
        physics_step: int,
        source_world: np.ndarray,
        source_center: np.ndarray,
        during_close: bool,
    ) -> None:
        if self._preclose_source_center is None or self._preclose_source_world is None:
            raise RuntimeError("dynamic_contact_grasp_motion_origin_missing")
        motion = evaluate_preclose_source_motion(
            reference_center_world_m=self._preclose_source_center,
            reference_source_world_matrix=self._preclose_source_world,
            current_center_world_m=source_center,
            current_source_world_matrix=source_world,
            vessel_axis_object=self._grasp_height_axis_object,
            translation_limit_m=self._preclose_translation_limit_m,
            tilt_limit_degrees=self._preclose_tilt_limit_degrees,
        )
        translation = float(motion["translation_m"])
        tilt = float(motion["tilt_degrees"])
        self._monitoring_max_source_translation_m = max(
            self._monitoring_max_source_translation_m,
            translation,
        )
        self._monitoring_max_source_tilt_degrees = max(
            self._monitoring_max_source_tilt_degrees,
            tilt,
        )
        if during_close:
            self._during_close_max_source_translation_m = max(
                self._during_close_max_source_translation_m,
                translation,
            )
            self._during_close_max_source_tilt_degrees = max(
                self._during_close_max_source_tilt_degrees,
                tilt,
            )
            failure_phase = "during_close"
        else:
            self._preclose_max_source_translation_m = max(
                self._preclose_max_source_translation_m,
                translation,
            )
            self._preclose_max_source_tilt_degrees = max(
                self._preclose_max_source_tilt_degrees,
                tilt,
            )
            failure_phase = "before_contact"
        if not motion["translation_valid"]:
            self._latch_failure(
                f"source_translation_exceeded_{failure_phase}",
                physics_step,
            )
        elif not motion["tilt_valid"]:
            self._latch_failure(
                f"source_tilt_exceeded_{failure_phase}",
                physics_step,
            )

    def _update_pre_roll_motion(self, *, physics_step: int) -> None:
        source_world = _rigid_affine_matrix(
            self._read_source_world(),
            name="dynamic_contact_grasp_pre_roll_source_world",
        )
        source_center = np.asarray(
            self._read_source_center_world(), dtype=np.float64
        )
        if source_center.shape != (3,) or not np.isfinite(source_center).all():
            raise ValueError("dynamic_contact_grasp_source_center_invalid")
        motion = evaluate_preclose_source_motion(
            reference_center_world_m=self._reset_source_center,
            reference_source_world_matrix=self._reset_source_world,
            current_center_world_m=source_center,
            current_source_world_matrix=source_world,
            vessel_axis_object=self._grasp_height_axis_object,
            translation_limit_m=self._preclose_translation_limit_m,
            tilt_limit_degrees=self._preclose_tilt_limit_degrees,
        )
        self._pre_roll_max_source_translation_m = max(
            self._pre_roll_max_source_translation_m,
            float(motion["translation_m"]),
        )
        self._pre_roll_max_source_tilt_degrees = max(
            self._pre_roll_max_source_tilt_degrees,
            float(motion["tilt_degrees"]),
        )
        if not motion["translation_valid"]:
            self._latch_failure(
                "source_translation_exceeded_pre_roll",
                physics_step,
            )
        elif not motion["tilt_valid"]:
            self._latch_failure(
                "source_tilt_exceeded_pre_roll",
                physics_step,
            )

    def update_after_substep(self) -> dict[str, Any] | None:
        physics_step = self._validated_physics_step()
        controlled_decision = self._controlled_step_decision(physics_step)

        def terminal(kind: str, reason: str | None) -> dict[str, Any] | None:
            if controlled_decision is None:
                return None
            if controlled_decision.get("kind") == "TERMINAL":
                return controlled_decision
            return {
                "kind": "TERMINAL",
                "terminal_kind": kind,
                "failure_reason": reason,
            }

        if not self._monitoring:
            if self._failure_reason is None:
                self._update_contact_sensor_readiness()
            if self._failure_reason is None:
                self._update_pre_roll_motion(physics_step=physics_step)
            if self._failure_reason is not None:
                return terminal(
                    self._controlled_failure_terminal_kind(
                        self._failure_reason
                    ),
                    self._failure_reason,
                )
            return controlled_decision
        if self._failure_reason is not None:
            return terminal(
                self._controlled_failure_terminal_kind(self._failure_reason),
                self._failure_reason,
            )
        writer_failure = self._source_writer_authority_failure()
        if writer_failure is not None:
            self._latch_failure(
                writer_failure,
                physics_step,
            )
            return terminal("PROTOCOL_FAILURE", writer_failure)
        (
            physics_step,
            source_world,
            source_center,
            contacts,
            qualifying_contacts,
        ) = self._read_sample()
        agreement_failure = self._sensor_immediate_agreement_failure(
            contacts,
            physics_step=physics_step,
        )
        if agreement_failure is not None:
            self._latch_failure(agreement_failure, physics_step)
            return terminal("PROTOCOL_FAILURE", agreement_failure)
        self._monitoring_steps += 1
        close_requested = fluid_grasp_contact_requested(self._controller)
        lift_requested = fluid_grasp_lift_requested(self._controller)
        self._lift_command_observed = bool(
            self._lift_command_observed or lift_requested
        )
        if not self._lift_command_observed:
            self._update_preclose_motion(
                physics_step=physics_step,
                source_world=source_world,
                source_center=source_center,
                during_close=close_requested,
            )
            if self._failure_reason is not None:
                return terminal(
                    "PHYSICAL_MOTION_FAILURE", self._failure_reason
                )
        if lift_requested and not self._acquired and not self._allow_preclose_contact:
            self._latch_failure(
                "lift_started_before_contact_acquisition",
                physics_step,
            )
            return terminal("PROTOCOL_FAILURE", self._failure_reason)
        if not close_requested:
            self._preclose_monitoring_steps += 1
            if (
                contacts
                and self._immediate_contact_reporter is None
                and not self._allow_preclose_contact
            ):
                self._latch_failure(
                    "unexpected_contact_before_close",
                    physics_step,
                    unexpected_contact=contacts[0],
                )
            return controlled_decision

        if not self._close_command_observed:
            self._close_command_observed = True
            self._gate.reset()
        allowed_pairs = {
            frozenset((self._gate.source_body_path, self._gate.left_finger_body_path)),
            frozenset((self._gate.source_body_path, self._gate.right_finger_body_path)),
        }
        unexpected = next(
            (
                contact
                for contact in contacts
                if frozenset(
                    (contact.get("body0_path"), contact.get("body1_path"))
                )
                not in allowed_pairs
            ),
            None,
        )
        if unexpected is not None and not self._allow_preclose_contact:
            self._latch_failure(
                "unexpected_contact_outside_grasp_allowlist",
                physics_step,
                unexpected_contact=unexpected,
            )
            return terminal(
                "PHYSICAL_CONTACT_FAILURE", self._failure_reason
            )

        finger_worlds = tuple(self._read_finger_worlds())
        if len(finger_worlds) != 2:
            raise ValueError("dynamic_contact_grasp_finger_worlds_invalid")
        left_world = _rigid_affine_matrix(
            finger_worlds[0], name="dynamic_contact_grasp_left_finger_world"
        )
        right_world = _rigid_affine_matrix(
            finger_worlds[1], name="dynamic_contact_grasp_right_finger_world"
        )
        side_axis = right_world[3, :3] - left_world[3, :3]
        self._contact_acquisition_steps += 1
        qualified = self._gate.update(
            physics_step=physics_step,
            contacts=qualifying_contacts,
            source_center_world_m=source_center,
            source_world_matrix=source_world,
            finger_side_axis_world=side_axis,
            finger_speeds_m_s=self._read_finger_velocities(),
        )
        gate_record = self._gate.record()
        valid_this_step = bool(gate_record.get("valid_this_step"))
        self._update_controlled_gate_certificate(
            phase=self._controlled_effective_phase or "CLOSE",
            valid_this_step=valid_this_step,
        )
        phase_timeout = self._controlled_phase_timeout_decision(
            self._controlled_effective_phase or "CLOSE",
            after_gate=True,
        )
        if phase_timeout is not None:
            return phase_timeout
        if not self._acquired and qualified:
            gripper = _rigid_affine_matrix(
                self._read_gripper_world(), name="dynamic_contact_grasp_gripper_world"
            )
            self._observed_relative = relative_source_to_gripper_matrix(
                source_world, gripper
            )
            self._acquired = True
            self._loss_steps = 0
        elif self._acquired:
            if valid_this_step:
                self._loss_steps = 0
            else:
                self._loss_steps += 1
                if self._loss_steps > self._loss_grace_steps:
                    self._latch_failure("grasp_lost", physics_step)

        if (
            not self._acquired
            and self._contact_acquisition_steps >= self._timeout_steps
        ):
            self._latch_failure("contact_timeout", physics_step)
        if self._failure_reason is not None:
            return terminal(
                self._controlled_failure_terminal_kind(self._failure_reason),
                self._failure_reason,
            )

        if self._acquired and self._observed_relative is not None:
            current_relative = relative_source_to_gripper_matrix(
                source_world, self._read_gripper_world()
            )
            translation, rotation = _pose_jump(
                self._observed_relative, current_relative
            )
            self._relative_translation_drift_m = max(
                self._relative_translation_drift_m, translation
            )
            self._relative_rotation_drift_degrees = max(
                self._relative_rotation_drift_degrees, rotation
            )
        return controlled_decision

    def probe_qualified_now(self) -> bool:
        gate = self._gate.record()
        try:
            current_physics_step = self._validated_physics_step()
        except (TypeError, ValueError, RuntimeError):
            return False
        return bool(
            self._acquired
            and self._failure_reason is None
            and self._loss_steps == 0
            and gate.get("valid_this_step") is True
            and gate.get("stale") is False
            and gate.get("physics_step") == current_physics_step
            and gate.get("consecutive_steps", 0)
            >= self._gate.required_consecutive_steps
            and self._source_writer_authority_failure() is None
        )

    def state_record(self) -> dict[str, Any]:
        readiness = self._contact_sensor_readiness_record()
        return {
            "qualified": self._acquired and self._failure_reason is None,
            "probe_qualified_now": self.probe_qualified_now(),
            "contact_sensor_ready": readiness["ready"],
            "contact_sensor_readiness": readiness,
            "failure_reason": self._failure_reason,
            "controlled_phase_certificates": (
                self._controlled_phase_certificates()
            ),
            "controlled_phase_elapsed_steps": dict(
                self._controlled_phase_elapsed_steps
            ),
            "controlled_phase_deadlines": dict(self._controlled_phase_deadlines),
        }

    def record(self) -> dict[str, Any]:
        readiness = self._contact_sensor_readiness_record()
        writer_audit = self._source_writer_audit_record()
        observed_writer_audit = {
            **writer_audit,
            "prohibited_writer_call_count": writer_audit["call_count"],
        }
        writer_authority_valid = self._source_writer_authority_failure() is None
        expert_grasp_valid = bool(
            self._acquired
            and self._failure_reason is None
            and writer_authority_valid
        )
        return {
            "mode": "contact_friction_dynamic_v1",
            "contact_grasp_claimed": True,
            "mechanical_attachment_used": False,
            "source_dynamic": True,
            "contact_sensor_scope": "left_finger_right_finger_and_panda_hand",
            "contact_sensor_ready": readiness["ready"],
            "contact_sensor_readiness": readiness,
            "contact_sensor_diagnostics": {
                "hand_qualifying_role": False,
                "raw_contact_count_by_sensor": dict(
                    self._last_raw_contact_counts
                ),
                "hand_raw_contact_count": self._last_raw_contact_counts["hand"],
                "normalized_contact_count": self._last_normalized_contact_count,
                "qualifying_contact_count": self._last_qualifying_contact_count,
            },
            "immediate_contact_report_enabled": (
                self._immediate_contact_reporter is not None
            ),
            "immediate_contact_report_sample_count": (
                self._immediate_report_sample_count
            ),
            "last_immediate_contact_report": (
                None
                if self._last_immediate_report is None
                else dict(self._last_immediate_report)
            ),
            "last_controlled_contact_classification": (
                None
                if self._last_controlled_classification is None
                else dict(self._last_controlled_classification)
            ),
            "sensor_immediate_agreement_valid": (
                self._sensor_immediate_agreement_valid
            ),
            "last_sensor_immediate_missing_pairs": [
                list(pair) for pair in self._last_sensor_immediate_missing_pairs
            ],
            "controlled_phase_certificates": (
                self._controlled_phase_certificates()
            ),
            "controlled_phase_elapsed_steps": dict(
                self._controlled_phase_elapsed_steps
            ),
            "controlled_phase_deadlines": dict(self._controlled_phase_deadlines),
            "controlled_contact_baseline_expected": [
                list(pair) for pair in self._controlled_contact_baseline_pairs
            ],
            "controlled_contact_baseline_observed": (
                None
                if self._controlled_contact_baseline_observed is None
                else [
                    list(pair)
                    for pair in self._controlled_contact_baseline_observed
                ]
            ),
            "controlled_contact_baseline_validated": (
                self._controlled_contact_baseline_validated
            ),
            "attached": self._acquired,
            "monitoring": self._monitoring,
            "monitoring_steps": self._monitoring_steps,
            "monitoring_start_physics_step": self._monitoring_start_physics_step,
            "preclose_monitoring_steps": self._preclose_monitoring_steps,
            "contact_acquisition_steps": self._contact_acquisition_steps,
            "close_command_observed": self._close_command_observed,
            "lift_command_observed": self._lift_command_observed,
            "preclose_max_source_translation_m": (
                self._preclose_max_source_translation_m
            ),
            "pre_roll_max_source_translation_m": (
                self._pre_roll_max_source_translation_m
            ),
            "pre_roll_max_source_tilt_degrees": (
                self._pre_roll_max_source_tilt_degrees
            ),
            "preclose_max_source_tilt_degrees": (
                self._preclose_max_source_tilt_degrees
            ),
            "during_close_max_source_translation_m": (
                self._during_close_max_source_translation_m
            ),
            "during_close_max_source_tilt_degrees": (
                self._during_close_max_source_tilt_degrees
            ),
            "monitoring_max_source_translation_m": (
                self._monitoring_max_source_translation_m
            ),
            "monitoring_max_source_tilt_degrees": (
                self._monitoring_max_source_tilt_degrees
            ),
            "source_motion_monitoring_policy": (
                "single_origin_until_lift_requested_v1"
            ),
            "source_motion_monitoring_active": bool(
                self._monitoring and not self._lift_command_observed
            ),
            "source_motion_origin_center_world_m": (
                None
                if self._preclose_source_center is None
                else self._preclose_source_center.tolist()
            ),
            "source_motion_origin_world_matrix_sha256": (
                None
                if self._preclose_source_world is None
                else _matrix_sha256(self._preclose_source_world)
            ),
            "preclose_source_translation_limit_m": (
                self._preclose_translation_limit_m
            ),
            "preclose_source_tilt_limit_degrees": (
                self._preclose_tilt_limit_degrees
            ),
            "first_unexpected_contact": self._first_unexpected_contact,
            "first_failure_physics_step": self._first_failure_physics_step,
            "qualified": self._acquired,
            "probe_qualified_now": self.probe_qualified_now(),
            "failure_reason": self._failure_reason,
            "loss_steps": self._loss_steps,
            "source_pose_write_count_after_play": writer_audit[
                "source_pose_write_count_after_play"
            ],
            "source_velocity_write_count_after_play": writer_audit[
                "source_velocity_write_count_after_play"
            ],
            "object_utils_source_position_write_count_after_play": writer_audit[
                "object_utils_source_position_write_count_after_play"
            ],
            "kinematic_target_update_count": writer_audit[
                "kinematic_target_update_count"
            ],
            "source_writer_call_count_after_play": writer_audit["call_count"],
            "source_writer_audit_required": self._require_complete_writer_audit,
            "source_writer_authority_valid": writer_authority_valid,
            "source_writer_audit": writer_audit,
            "observed_writer_audit": observed_writer_audit,
            "expert_grasp_valid": expert_grasp_valid,
            "minimum_normal_impulse_derivation": (
                None
                if self._minimum_normal_impulse_derivation is None
                else dict(self._minimum_normal_impulse_derivation)
            ),
            "gate": self._gate.record(),
            "relative_translation_drift_m": self._relative_translation_drift_m,
            "relative_rotation_drift_degrees": (
                self._relative_rotation_drift_degrees
            ),
            "observed_source_to_gripper_matrix": (
                None
                if self._observed_relative is None
                else self._observed_relative.tolist()
            ),
            "observed_matrix_sha256": (
                None
                if self._observed_relative is None
                else _matrix_sha256(self._observed_relative)
            ),
        }


class GripperAttachedKinematicVessel:
    """Transport upright, then follow the gripper rigidly for scripted pouring."""

    def __init__(
        self,
        *,
        read_source_world_matrix: Callable[[], Any],
        read_gripper_world_matrix: Callable[[], Any],
        write_source_world_matrix: Callable[[np.ndarray], None],
    ) -> None:
        self._read_source = read_source_world_matrix
        self._read_gripper = read_gripper_world_matrix
        self._write_source = write_source_world_matrix
        self._initial_source = _affine_matrix(
            read_source_world_matrix(), name="initial_source_world"
        ).copy()
        self._attach_source: np.ndarray | None = None
        self._attach_gripper: np.ndarray | None = None
        self._observed_relative: np.ndarray | None = None
        self._active_relative: np.ndarray | None = None
        self._pre_attach_source: np.ndarray | None = None
        self._first_attachment_target: np.ndarray | None = None
        self._pre_pour_handoff_source: np.ndarray | None = None
        self._first_pour_handoff_target: np.ndarray | None = None
        self._attachment_translation_jump_m: float | None = None
        self._attachment_rotation_jump_degrees: float | None = None
        self._pour_handoff_translation_jump_m: float | None = None
        self._pour_handoff_rotation_jump_degrees: float | None = None
        self._attachment_count = 0
        self._rotation_handoff_count = 0
        self._target_update_count = 0

    def reset(self) -> None:
        self._attach_source = None
        self._attach_gripper = None
        self._observed_relative = None
        self._active_relative = None
        self._pre_attach_source = None
        self._first_attachment_target = None
        self._pre_pour_handoff_source = None
        self._first_pour_handoff_target = None
        self._attachment_translation_jump_m = None
        self._attachment_rotation_jump_degrees = None
        self._pour_handoff_translation_jump_m = None
        self._pour_handoff_rotation_jump_degrees = None
        self._attachment_count = 0
        self._rotation_handoff_count = 0
        self._target_update_count = 0
        self._write_source(self._initial_source.copy())

    def _upright_transport_target(self, gripper: Any) -> np.ndarray:
        if self._attach_source is None or self._attach_gripper is None:
            raise RuntimeError("upright_transport_requires_attachment")
        current_gripper = _rigid_affine_matrix(
            gripper, name="upright_transport_gripper_world"
        )
        target = self._attach_source.copy()
        target[3, :3] += (
            current_gripper[3, :3] - self._attach_gripper[3, :3]
        )
        return _rigid_affine_matrix(target, name="upright_transport_target_world")

    def maybe_attach(self, controller: Any, state: Mapping[str, Any]) -> bool:
        del state
        if self._attach_source is None:
            if not fluid_grasp_attachment_requested(controller):
                return False
            source = _rigid_affine_matrix(
                self._read_source(), name="attach_source_world"
            )
            gripper = _rigid_affine_matrix(
                self._read_gripper(), name="attach_gripper_world"
            )
            self._attach_source = source.copy()
            self._attach_gripper = gripper.copy()
            self._observed_relative = relative_source_to_gripper_matrix(
                source, gripper
            )
            self._pre_attach_source = source.copy()
            self._first_attachment_target = self._upright_transport_target(gripper)
            (
                self._attachment_translation_jump_m,
                self._attachment_rotation_jump_degrees,
            ) = _pose_jump(source, self._first_attachment_target)
            self._attachment_count += 1
            return True

        if (
            self._active_relative is None
            and fluid_rotation_handoff_requested(controller)
        ):
            source = _rigid_affine_matrix(
                self._read_source(), name="pour_handoff_source_world"
            )
            gripper = _rigid_affine_matrix(
                self._read_gripper(), name="pour_handoff_gripper_world"
            )
            relative = relative_source_to_gripper_matrix(source, gripper)
            target = attached_source_world_matrix(relative, gripper)
            self._pre_pour_handoff_source = source.copy()
            self._first_pour_handoff_target = target.copy()
            (
                self._pour_handoff_translation_jump_m,
                self._pour_handoff_rotation_jump_degrees,
            ) = _pose_jump(source, target)
            self._active_relative = relative.copy()
            self._rotation_handoff_count += 1
            return True
        return False

    def update_before_substep(self) -> None:
        if self._attach_source is None:
            return
        gripper = self._read_gripper()
        if self._active_relative is None:
            target = self._upright_transport_target(gripper)
        else:
            target = attached_source_world_matrix(self._active_relative, gripper)
        self._write_source(target)
        self._target_update_count += 1

    def record(self) -> dict[str, Any]:
        attached = self._attach_source is not None
        handoff_complete = self._active_relative is not None
        jump_values = (
            self._attachment_translation_jump_m,
            self._attachment_rotation_jump_degrees,
            self._pour_handoff_translation_jump_m,
            self._pour_handoff_rotation_jump_degrees,
        )
        expert_attachment_valid = (
            attached
            and self._attachment_count == 1
            and handoff_complete
            and self._rotation_handoff_count == 1
            and self._observed_relative is not None
            and all(value is not None for value in jump_values)
            and self._attachment_translation_jump_m <= 1.0e-9
            and self._attachment_rotation_jump_degrees <= 1.0e-5
            and self._pour_handoff_translation_jump_m <= 1.0e-9
            and self._pour_handoff_rotation_jump_degrees <= 1.0e-5
        )
        return {
            "mode": "gripper_attached_kinematic_vessel",
            "contact_grasp_claimed": False,
            "attached": attached,
            "attachment_count": self._attachment_count,
            "rotation_handoff_count": self._rotation_handoff_count,
            "attachment_stage": (
                "unattached"
                if not attached
                else "full_rigid_pour"
                if handoff_complete
                else "upright_translation"
            ),
            "kinematic_target_update_count": self._target_update_count,
            "attachment_matrix_policy": (
                "captured_translation_then_recaptured_full_at_scripted_pour"
            ),
            "expert_attachment_valid": expert_attachment_valid,
            "observed_source_to_gripper_matrix": (
                None
                if self._observed_relative is None
                else self._observed_relative.tolist()
            ),
            "observed_matrix_sha256": (
                None
                if self._observed_relative is None
                else _matrix_sha256(self._observed_relative)
            ),
            "applied_source_to_gripper_matrix": (
                None
                if self._active_relative is None
                else self._active_relative.tolist()
            ),
            "applied_matrix_sha256": (
                None
                if self._active_relative is None
                else _matrix_sha256(self._active_relative)
            ),
            "pre_attach_source_world_matrix": (
                None
                if self._pre_attach_source is None
                else self._pre_attach_source.tolist()
            ),
            "first_attachment_target_world_matrix": (
                None
                if self._first_attachment_target is None
                else self._first_attachment_target.tolist()
            ),
            "attachment_translation_jump_m": self._attachment_translation_jump_m,
            "attachment_rotation_jump_degrees": (
                self._attachment_rotation_jump_degrees
            ),
            "pour_handoff_source_to_gripper_matrix": (
                None
                if self._active_relative is None
                else self._active_relative.tolist()
            ),
            "pour_handoff_matrix_sha256": (
                None
                if self._active_relative is None
                else _matrix_sha256(self._active_relative)
            ),
            "pre_pour_handoff_source_world_matrix": (
                None
                if self._pre_pour_handoff_source is None
                else self._pre_pour_handoff_source.tolist()
            ),
            "first_pour_handoff_target_world_matrix": (
                None
                if self._first_pour_handoff_target is None
                else self._first_pour_handoff_target.tolist()
            ),
            "pour_handoff_translation_jump_m": (
                self._pour_handoff_translation_jump_m
            ),
            "pour_handoff_rotation_jump_degrees": (
                self._pour_handoff_rotation_jump_degrees
            ),
            "pour_handoff_trigger_event": 2 if handoff_complete else None,
            "source_to_gripper_matrix": (
                None
                if self._active_relative is None
                else self._active_relative.tolist()
            ),
        }


def _vt_vec3f_array(values: Any) -> Any:
    from pxr import Gf, Vt

    contiguous = np.ascontiguousarray(values, dtype=np.float32)
    converter = getattr(Vt.Vec3fArray, "FromNumpy", None)
    if converter is not None:
        return converter(contiguous)
    return Vt.Vec3fArray([Gf.Vec3f(*row) for row in contiguous.tolist()])


def _vt_int_array(values: Any) -> Any:
    from pxr import Vt

    contiguous = np.ascontiguousarray(values, dtype=np.int32).reshape(-1)
    converter = getattr(Vt.IntArray, "FromNumpy", None)
    if converter is not None:
        return converter(contiguous)
    return Vt.IntArray(contiguous.tolist())


class IsaacFluidSurfaceAuthor:
    """Author the sole visible liquid mesh for the current particle token."""

    def __init__(
        self,
        *,
        stage: Any,
        surface_path: str,
        material_path: str,
        hidden_liquid_paths: Sequence[str],
        particle_system_path: str,
    ) -> None:
        for name, path in (
            ("surface", surface_path),
            ("material", material_path),
            ("particle_system", particle_system_path),
        ):
            if not isinstance(path, str) or not path.startswith("/"):
                raise ValueError(f"{name}_path_invalid")
        self.stage = stage
        self.surface_path = surface_path
        self.material_path = material_path
        self.hidden_liquid_paths = tuple(hidden_liquid_paths)
        self.particle_system_path = particle_system_path
        self._configured = False

    def _configure_visual_authority(self, surface_prim: Any) -> dict[str, Any]:
        from pxr import UsdGeom

        hidden = []
        for path in self.hidden_liquid_paths:
            prim = self.stage.GetPrimAtPath(path)
            if prim and prim.IsValid() and prim.IsA(UsdGeom.Imageable):
                UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(
                    UsdGeom.Tokens.invisible
                )
                hidden.append(path)
        system = self.stage.GetPrimAtPath(self.particle_system_path)
        native_isosurface_disabled = False
        if system and system.IsValid():
            attribute = system.GetAttribute(
                "physxParticleIsosurface:isosurfaceEnabled"
            )
            if attribute:
                attribute.Set(False)
                native_isosurface_disabled = True
        UsdGeom.Imageable(surface_prim).CreateVisibilityAttr().Set(
            UsdGeom.Tokens.inherited
        )
        return {
            "visible_liquid_path": self.surface_path,
            "hidden_liquid_paths": hidden,
            "native_isosurface_disabled": native_isosurface_disabled,
        }

    def _bind_material(self, surface_prim: Any) -> dict[str, Any]:
        from pxr import Gf, Sdf, UsdGeom, UsdShade

        parent_path = self.material_path.rsplit("/", 1)[0]
        if not self.stage.GetPrimAtPath(parent_path).IsValid():
            UsdGeom.Scope.Define(self.stage, parent_path)
        material = UsdShade.Material.Define(self.stage, self.material_path)
        shader = UsdShade.Shader.Define(
            self.stage, f"{self.material_path}/PreviewSurface"
        )
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(0.46, 0.82, 0.96)
        )
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(0.01, 0.025, 0.035)
        )
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.06)
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.06)
        shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.333)
        material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(), "surface"
        )
        UsdShade.MaterialBindingAPI.Apply(surface_prim).Bind(material)
        return {
            "material_path": self.material_path,
            "shader": "UsdPreviewSurface",
        }

    def __call__(self, mesh_data: Mapping[str, Any], token: Any) -> dict[str, Any]:
        from pxr import Gf, Sdf, UsdGeom, Vt

        vertices = np.ascontiguousarray(mesh_data["vertices"], dtype=np.float32)
        faces = np.ascontiguousarray(mesh_data["faces"], dtype=np.int32)
        normals = np.ascontiguousarray(mesh_data["normals"], dtype=np.float32)
        origin = np.asarray(mesh_data["origin_world_m"], dtype=np.float64)
        if (
            vertices.ndim != 2
            or vertices.shape[1:] != (3,)
            or faces.ndim != 2
            or faces.shape[1:] != (3,)
            or normals.shape != vertices.shape
            or origin.shape != (3,)
        ):
            raise ValueError("surface_author_mesh_shape_invalid")

        mesh = UsdGeom.Mesh.Define(self.stage, self.surface_path)
        prim = mesh.GetPrim()
        prim.CreateAttribute(
            "xformOp:translate", Sdf.ValueTypeNames.Double3, custom=False
        ).Set(Gf.Vec3d(*origin.tolist()))
        prim.CreateAttribute(
            "xformOpOrder", Sdf.ValueTypeNames.TokenArray, custom=False
        ).Set(Vt.TokenArray(["xformOp:translate"]))
        mesh.CreatePointsAttr().Set(_vt_vec3f_array(vertices))
        mesh.CreateFaceVertexCountsAttr().Set(
            _vt_int_array(np.full(len(faces), 3, dtype=np.int32))
        )
        mesh.CreateFaceVertexIndicesAttr().Set(_vt_int_array(faces))
        mesh.CreateNormalsAttr().Set(_vt_vec3f_array(normals))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateExtentAttr().Set(
            _vt_vec3f_array(
                np.asarray(
                    [vertices.min(axis=0), vertices.max(axis=0)], dtype=np.float32
                )
            )
        )
        mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        mesh.CreateOrientationAttr().Set(UsdGeom.Tokens.rightHanded)
        mesh.CreateDoubleSidedAttr().Set(False)
        mesh.CreatePurposeAttr().Set(UsdGeom.Tokens.render)
        mesh.CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)
        prim.CreateAttribute(
            "labutopia:surfaceFrameToken", Sdf.ValueTypeNames.String, custom=True
        ).Set(token.identity)

        authority = None
        material = None
        if not self._configured:
            material = self._bind_material(prim)
            authority = self._configure_visual_authority(prim)
            self._configured = True
        return {
            "path": self.surface_path,
            "surface_token": token.identity,
            "vertex_count": int(len(vertices)),
            "face_count": int(len(faces)),
            "origin_world_m": origin.tolist(),
            "visual_authority": authority,
            "material": material,
        }

    def invalidate(self, reason: str) -> None:
        from pxr import Sdf, UsdGeom

        prim = self.stage.GetPrimAtPath(self.surface_path)
        if prim and prim.IsValid() and prim.IsA(UsdGeom.Imageable):
            UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(
                UsdGeom.Tokens.invisible
            )
            prim.CreateAttribute(
                "labutopia:surfaceInvalidationReason",
                Sdf.ValueTypeNames.String,
                custom=True,
            ).Set(str(reason))


def _config_value(node: Any, name: str) -> Any:
    if isinstance(node, Mapping):
        return node[name]
    return getattr(node, name)


def _config_contains(node: Any, name: str) -> bool:
    if isinstance(node, Mapping):
        return name in node
    return hasattr(node, name)


def controlled_contact_interlock_requested(fluid_cfg: Any) -> bool:
    return bool(
        str(_optional_config_value(fluid_cfg, "source_ownership", ""))
        == "contact_friction_dynamic_v1"
        and str(_optional_config_value(fluid_cfg, "execution_mode", ""))
        == "contact_acquisition_probe_v1"
        and str(_optional_config_value(fluid_cfg, "expert_control_profile", ""))
        == "contact_pick_v1"
    )


def dynamic_contact_grasp_parameters(fluid_cfg: Any) -> dict[str, Any]:
    payload_authority = str(
        _config_value(fluid_cfg, "grasp_payload_mass_authority")
    )
    if not payload_authority:
        raise ValueError("grasp_payload_mass_authority_required")
    derivation = derive_minimum_per_finger_normal_impulse(
        effective_payload_mass_kg=float(
            _config_value(fluid_cfg, "grasp_effective_payload_mass_kg")
        ),
        effective_friction=float(
            _config_value(fluid_cfg, "grasp_effective_friction")
        ),
        physics_dt=float(_config_value(fluid_cfg, "physics_dt")),
        gravity_m_s2=float(_config_value(fluid_cfg, "grasp_gravity_m_s2")),
    )
    derivation = {**derivation, "payload_mass_authority": payload_authority}
    return {
        "source_collider_path": str(
            _config_value(fluid_cfg, "source_external_shell_path")
        ),
        "grasp_height_axis_object": tuple(
            float(value)
            for value in _config_value(fluid_cfg, "grasp_height_axis_object")
        ),
        "grasp_height_band_m": tuple(
            float(value)
            for value in _config_value(fluid_cfg, "grasp_height_band_m")
        ),
        "maximum_bilateral_height_difference_m": float(
            _config_value(
                fluid_cfg,
                "grasp_contact_max_bilateral_height_difference_m",
            )
        ),
        "minimum_inward_normal_cosine": float(
            _config_value(
                fluid_cfg,
                "grasp_contact_min_inward_normal_cosine",
            )
        ),
        "minimum_opposing_normal_cosine": float(
            _config_value(
                fluid_cfg,
                "grasp_contact_min_opposing_normal_cosine",
            )
        ),
        "minimum_normal_impulse_n_s": float(
            derivation["minimum_per_finger_normal_impulse_n_s"]
        ),
        "minimum_normal_impulse_derivation": derivation,
    }


def configure_particle_usd_readback() -> dict[str, Any]:
    """Enable current GPU particle state readback before World initialization."""
    import carb
    import omni.physx.bindings._physx as pb

    settings = carb.settings.get_settings()
    settings.set_bool("/physics/suppressReadback", False)
    applied = {"/physics/suppressReadback": False}
    for constant_name in (
        "SETTING_UPDATE_TO_USD",
        "SETTING_UPDATE_PARTICLES_TO_USD",
        "SETTING_UPDATE_VELOCITIES_TO_USD",
    ):
        path = getattr(pb, constant_name, None)
        if path:
            settings.set(path, True)
            applied[str(path)] = True
    return applied


def author_synthetic_attachment_collision_filter(
    stage: Any,
    *,
    source_body_path: str,
    robot_root_path: str,
) -> dict[str, Any]:
    """Keep a synthetic kinematic grasp from colliding with its carrier."""
    from pxr import Sdf, Usd, UsdPhysics

    source = stage.GetPrimAtPath(source_body_path)
    if not source or not source.IsValid():
        raise RuntimeError(f"synthetic_attachment_source_missing:{source_body_path}")
    if not source.HasAPI(UsdPhysics.RigidBodyAPI):
        raise RuntimeError("synthetic_attachment_source_rigid_body_required")
    kinematic = source.GetAttribute("physics:kinematicEnabled")
    if not kinematic or kinematic.Get() is not True:
        raise RuntimeError("synthetic_attachment_source_kinematic_required")

    robot_root = stage.GetPrimAtPath(robot_root_path)
    if not robot_root or not robot_root.IsValid():
        raise RuntimeError(f"synthetic_attachment_robot_missing:{robot_root_path}")
    robot_body_paths = []
    for prim in Usd.PrimRange(robot_root):
        if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
            continue
        enabled = prim.GetAttribute("physics:rigidBodyEnabled")
        if enabled and enabled.Get() is False:
            continue
        robot_body_paths.append(str(prim.GetPath()))
    robot_body_paths.sort()
    if not robot_body_paths:
        raise RuntimeError("synthetic_attachment_robot_rigid_bodies_missing")

    filtered_pairs = UsdPhysics.FilteredPairsAPI.Apply(source)
    relationship = filtered_pairs.CreateFilteredPairsRel()
    targets = {str(path) for path in relationship.GetTargets()}
    targets.update(robot_body_paths)
    relationship.SetTargets([Sdf.Path(path) for path in sorted(targets)])
    return {
        "source_body_path": source_body_path,
        "robot_root_path": robot_root_path,
        "robot_rigid_body_paths": robot_body_paths,
    }


def configure_contact_grasp_scene(stage: Any, fluid_cfg: Any) -> dict[str, Any]:
    """Bind the real-grasp friction material to the two finger colliders."""
    from pxr import PhysxSchema, Usd, UsdPhysics, UsdShade

    material_path = str(_config_value(fluid_cfg, "contact_material_path"))
    material_prim = stage.GetPrimAtPath(material_path)
    if not material_prim or not material_prim.IsValid():
        raise RuntimeError(f"contact_grasp_material_missing:{material_path}")
    material = UsdShade.Material(material_prim)
    if not material:
        raise RuntimeError(f"contact_grasp_material_invalid:{material_path}")

    finger_paths = tuple(
        str(path) for path in _config_value(fluid_cfg, "finger_body_paths")
    )
    if len(finger_paths) != 2 or len(set(finger_paths)) != 2:
        raise ValueError("contact_grasp_finger_body_paths_invalid")
    finger_prims = {}
    for path in finger_paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise RuntimeError(f"contact_grasp_finger_missing:{path}")
        if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
            raise RuntimeError(f"contact_grasp_finger_rigid_body_required:{path}")
        finger_prims[path] = prim

    controlled_contact = bool(
        str(
            _optional_config_value(
                fluid_cfg,
                "execution_mode",
                "production_pour_v1",
            )
        )
        == "contact_acquisition_probe_v1"
        or str(
            _optional_config_value(
                fluid_cfg,
                "execution_mode",
                "production_pour_v1",
            )
        )
        == "close_contact_allowed_v1"
    )
    if controlled_contact:
        robot_root_path = CONTACT_REPORT_HAND_BODY_PATH.rsplit("/", 1)[0]
        robot_root = stage.GetPrimAtPath(robot_root_path)
        if not robot_root or not robot_root.IsValid():
            raise RuntimeError(
                f"contact_grasp_robot_root_missing:{robot_root_path}"
            )
        robot_report_paths = []
        for prim in Usd.PrimRange(robot_root):
            if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
                continue
            enabled = prim.GetAttribute("physics:rigidBodyEnabled")
            if enabled and enabled.Get() is False:
                continue
            robot_report_paths.append(str(prim.GetPath()))
        source_path = str(_config_value(fluid_cfg, "source_actor_path"))
        contact_report_paths = tuple(sorted((*robot_report_paths, source_path)))
    else:
        contact_report_paths = (*finger_paths, CONTACT_REPORT_HAND_BODY_PATH)
    if len(contact_report_paths) != len(set(contact_report_paths)):
        raise ValueError("contact_grasp_contact_report_body_paths_invalid")
    if not contact_report_paths:
        raise ValueError("contact_grasp_contact_report_body_paths_invalid")
    for path in contact_report_paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise RuntimeError(
                f"contact_grasp_contact_report_body_missing:{path}"
            )
        if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
            raise RuntimeError(
                f"contact_grasp_contact_report_rigid_body_required:{path}"
            )
        enabled = prim.GetAttribute("physics:rigidBodyEnabled")
        if enabled and enabled.Get() is False:
            raise RuntimeError(
                f"contact_grasp_contact_report_body_disabled:{path}"
            )
        contact_report_type = PhysxSchema.PhysxContactReportAPI

        def has_contact_report_api() -> bool:
            try:
                return bool(prim.HasAPI(contact_report_type))
            except (TypeError, RuntimeError):
                return bool(contact_report_type(prim))

        report_api = contact_report_type(prim)
        if not has_contact_report_api():
            report_api = contact_report_type.Apply(prim)
        if not has_contact_report_api():
            raise RuntimeError(
                f"contact_grasp_contact_report_api_invalid:{path}"
            )
        if controlled_contact:
            threshold = report_api.CreateThresholdAttr()
            if threshold.Set(0.0) is False:
                raise RuntimeError(
                    f"contact_grasp_contact_report_threshold_write_failed:{path}"
                )
            observed_threshold = report_api.GetThresholdAttr().Get()
            if (
                isinstance(observed_threshold, bool)
                or not isinstance(observed_threshold, (int, float))
                or float(observed_threshold) != 0.0
            ):
                raise RuntimeError(
                    f"contact_grasp_contact_report_threshold_invalid:{path}"
                )
            report_pairs = report_api.GetReportPairsRel()
            if not report_pairs:
                create_report_pairs = getattr(
                    report_api, "CreateReportPairsRel", None
                )
                if not callable(create_report_pairs):
                    raise RuntimeError(
                        f"contact_grasp_contact_report_pairs_missing:{path}"
                    )
                report_pairs = create_report_pairs()
            if report_pairs.ClearTargets(True) is False:
                raise RuntimeError(
                    f"contact_grasp_contact_report_pairs_clear_failed:{path}"
                )
            if report_pairs.GetTargets():
                raise RuntimeError(
                    f"contact_grasp_contact_report_pairs_not_empty:{path}"
                )

    bound: dict[str, list[str]] = {}
    for path, prim in finger_prims.items():
        colliders = []
        for candidate in Usd.PrimRange(prim):
            if not candidate.HasAPI(UsdPhysics.CollisionAPI):
                continue
            enabled = candidate.GetAttribute("physics:collisionEnabled")
            if enabled and enabled.Get() is False:
                continue
            UsdShade.MaterialBindingAPI.Apply(candidate).Bind(
                material,
                bindingStrength=UsdShade.Tokens.weakerThanDescendants,
                materialPurpose="physics",
            )
            colliders.append(str(candidate.GetPath()))
        if not colliders:
            raise RuntimeError(f"contact_grasp_finger_collision_required:{path}")
        bound[path] = colliders
    return {
        "material_path": material_path,
        "finger_collider_paths": bound,
        "contact_report_body_paths": list(contact_report_paths),
        "contact_report_api_body_paths": list(contact_report_paths),
        "physx_contact_report_api_paths": list(contact_report_paths),
        "contact_report_api_preauthorized": True,
        "contact_report_runtime_auto_add_required": False,
        "external_shell_to_finger_collision_filtered": False,
        "contact_report_threshold_n_s": 0.0 if controlled_contact else None,
        "contact_report_pairs_empty": controlled_contact,
    }


def resolve_enabled_rigid_body_path(stage: Any, prim_path: str) -> str:
    """Resolve a raw PhysX collider name to its owning enabled rigid body."""
    from pxr import UsdPhysics

    prim = stage.GetPrimAtPath(prim_path)
    while prim and prim.IsValid():
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            enabled = prim.GetAttribute("physics:rigidBodyEnabled")
            if not enabled or enabled.Get() is not False:
                return str(prim.GetPath())
        prim = prim.GetParent()
    raise RuntimeError(f"contact_rigid_body_owner_missing:{prim_path}")


def validate_dynamic_source_stage_contract(
    stage: Any,
    fluid_cfg: Any,
    *,
    additional_required_paths: Sequence[str] = (),
) -> dict[str, Any]:
    """Validate the production dynamic vessel without requiring a robot."""
    from pxr import Usd, UsdPhysics

    physics_scene_path = str(_config_value(fluid_cfg, "physics_scene_path"))
    scenes = [
        str(prim.GetPath())
        for prim in Usd.PrimRange.Stage(stage)
        if prim.IsA(UsdPhysics.Scene)
    ]
    if scenes != [physics_scene_path]:
        raise RuntimeError(
            f"fluid_physics_scene_contract_invalid:expected={physics_scene_path}:"
            f"actual={scenes}"
        )
    source_ownership = str(_config_value(fluid_cfg, "source_ownership"))
    if source_ownership != "contact_friction_dynamic_v1":
        raise ValueError(f"fluid_source_ownership_unsupported:{source_ownership}")
    if isinstance(additional_required_paths, (str, bytes)):
        raise TypeError("dynamic_source_additional_required_paths_invalid")
    additional_paths = tuple(str(path) for path in additional_required_paths)
    if any(not path.startswith("/") for path in additional_paths):
        raise ValueError("dynamic_source_additional_required_paths_invalid")
    required_paths = [
        str(_config_value(fluid_cfg, "particle_path")),
        str(_config_value(fluid_cfg, "particle_system_path")),
        str(_config_value(fluid_cfg, "source_actor_path")),
        str(_config_value(fluid_cfg, "target_actor_path")),
        str(_config_value(fluid_cfg, "source_external_shell_path")),
        str(_config_value(fluid_cfg, "source_internal_wrapper_path")),
        *additional_paths,
    ]
    required_paths = tuple(dict.fromkeys(required_paths))
    missing = [path for path in required_paths if not stage.GetPrimAtPath(path).IsValid()]
    if missing:
        raise RuntimeError(f"fluid_stage_required_prims_missing:{missing}")
    source_path = str(_config_value(fluid_cfg, "source_actor_path"))
    source = stage.GetPrimAtPath(source_path)
    kinematic = source.GetAttribute("physics:kinematicEnabled")

    legacy_keys = (
        "attachment_matrix_policy",
        "expert_attachment",
        "gripper_frame_path",
        "synthetic_attachment_collision_filter_root_path",
    )
    present_legacy = [
        key for key in legacy_keys if _config_contains(fluid_cfg, key)
    ]
    if present_legacy:
        raise RuntimeError(f"dynamic_source_legacy_controls_present:{present_legacy}")
    if not source.HasAPI(UsdPhysics.RigidBodyAPI):
        raise RuntimeError("dynamic_source_rigid_body_required")
    if not source.HasAPI(UsdPhysics.MassAPI):
        raise RuntimeError("dynamic_source_root_mass_required")
    if kinematic and kinematic.Get() is not False:
        raise RuntimeError("dynamic_source_kinematic_forbidden")

    enabled_rigid_bodies = []
    descendant_mass_owners = []
    joints = []
    for prim in Usd.PrimRange(source):
        path = str(prim.GetPath())
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            enabled = prim.GetAttribute("physics:rigidBodyEnabled")
            if not enabled or enabled.Get() is not False:
                enabled_rigid_bodies.append(path)
        if path != source_path and prim.HasAPI(UsdPhysics.MassAPI):
            descendant_mass_owners.append(path)
        if prim.IsA(UsdPhysics.Joint):
            joints.append(path)
    if enabled_rigid_bodies != [source_path]:
        raise RuntimeError(
            "dynamic_source_rigid_body_ownership_invalid:"
            f"{enabled_rigid_bodies}"
        )
    if descendant_mass_owners:
        raise RuntimeError(
            f"dynamic_source_descendant_mass_forbidden:{descendant_mass_owners}"
        )
    if joints:
        raise RuntimeError(f"dynamic_source_joint_forbidden:{joints}")

    external_path = str(_config_value(fluid_cfg, "source_external_shell_path"))
    external = stage.GetPrimAtPath(external_path)
    collision_enabled = external.GetAttribute("physics:collisionEnabled")
    approximation = external.GetAttribute("physics:approximation")
    if (
        not external.HasAPI(UsdPhysics.CollisionAPI)
        or not collision_enabled
        or collision_enabled.Get() is not True
        or not approximation
        or approximation.Get() != "convexDecomposition"
    ):
        raise RuntimeError("dynamic_source_external_shell_collision_invalid")

    wrapper_path = str(_config_value(fluid_cfg, "source_internal_wrapper_path"))
    wrapper = stage.GetPrimAtPath(wrapper_path)
    wrapper_colliders = []
    for prim in Usd.PrimRange(wrapper):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = prim.GetAttribute("physics:collisionEnabled")
        if not enabled or enabled.Get() is not False:
            wrapper_colliders.append(str(prim.GetPath()))
    if len(wrapper_colliders) != 145:
        raise RuntimeError(
            "dynamic_source_internal_wrapper_collider_count_invalid:"
            f"expected=145:actual={len(wrapper_colliders)}"
        )

    group_root = "/World/ContactGraspCollisionGroups"
    group_paths = {
        "fluid": f"{group_root}/FluidParticles",
        "external": f"{group_root}/SourceExternalShell",
        "interior": f"{group_root}/SourceFluidInterior",
        "environment": f"{group_root}/Environment",
    }
    for path in group_paths.values():
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid() or not prim.IsA(UsdPhysics.CollisionGroup):
            raise RuntimeError(f"dynamic_source_collision_group_invalid:{path}")

    def relationship_targets(path: str, name: str) -> set[str]:
        relationship = stage.GetPrimAtPath(path).GetRelationship(name)
        return {str(target) for target in relationship.GetTargets()}

    particle_system_path = str(_config_value(fluid_cfg, "particle_system_path"))
    expected_members = {
        "fluid": {particle_system_path},
        "external": {external_path},
        "interior": {wrapper_path},
    }
    for name, expected in expected_members.items():
        actual = relationship_targets(
            group_paths[name], "collection:colliders:includes"
        )
        if actual != expected:
            raise RuntimeError(
                f"dynamic_source_collision_group_members_invalid:{name}:"
                f"expected={sorted(expected)}:actual={sorted(actual)}"
            )
    if relationship_targets(group_paths["fluid"], "physics:filteredGroups") != {
        group_paths["external"]
    }:
        raise RuntimeError("dynamic_source_fluid_external_filter_invalid")
    if relationship_targets(
        group_paths["interior"], "physics:filteredGroups"
    ) != {group_paths["environment"]}:
        raise RuntimeError("dynamic_source_interior_environment_filter_invalid")
    external_filters = relationship_targets(
        group_paths["external"], "physics:filteredGroups"
    )
    if group_paths["environment"] in external_filters:
        raise RuntimeError("dynamic_source_external_finger_filter_forbidden")

    return {
        "physics_scene_paths": scenes,
        "required_prim_paths": list(required_paths),
        "source_ownership": source_ownership,
        "source_kinematic": False,
        "enabled_source_rigid_body_paths": enabled_rigid_bodies,
        "source_internal_wrapper_collider_count": len(wrapper_colliders),
        "collision_group_paths": group_paths,
    }


def validate_fluid_stage_contract(stage: Any, fluid_cfg: Any) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    source_ownership = str(_config_value(fluid_cfg, "source_ownership"))
    if source_ownership == "contact_friction_dynamic_v1":
        return validate_dynamic_source_stage_contract(
            stage,
            fluid_cfg,
            additional_required_paths=(
                str(_config_value(fluid_cfg, "grasp_frame_path")),
                str(_config_value(fluid_cfg, "contact_material_path")),
                *[
                    str(path)
                    for path in _config_value(fluid_cfg, "finger_body_paths")
                ],
            ),
        )
    if source_ownership != "gripper_attached_kinematic_vessel":
        raise ValueError(f"fluid_source_ownership_unsupported:{source_ownership}")

    physics_scene_path = str(_config_value(fluid_cfg, "physics_scene_path"))
    scenes = [
        str(prim.GetPath())
        for prim in Usd.PrimRange.Stage(stage)
        if prim.IsA(UsdPhysics.Scene)
    ]
    if scenes != [physics_scene_path]:
        raise RuntimeError(
            f"fluid_physics_scene_contract_invalid:expected={physics_scene_path}:"
            f"actual={scenes}"
        )
    required_paths = (
        str(_config_value(fluid_cfg, "particle_path")),
        str(_config_value(fluid_cfg, "particle_system_path")),
        str(_config_value(fluid_cfg, "source_actor_path")),
        str(_config_value(fluid_cfg, "target_actor_path")),
        str(_config_value(fluid_cfg, "gripper_frame_path")),
    )
    missing = [path for path in required_paths if not stage.GetPrimAtPath(path).IsValid()]
    if missing:
        raise RuntimeError(f"fluid_stage_required_prims_missing:{missing}")
    source = stage.GetPrimAtPath(
        str(_config_value(fluid_cfg, "source_actor_path"))
    )
    kinematic = source.GetAttribute("physics:kinematicEnabled")
    if not kinematic or kinematic.Get() is not True:
        raise RuntimeError("fluid_source_must_be_kinematic")
    return {
        "physics_scene_paths": scenes,
        "required_prim_paths": list(required_paths),
        "source_ownership": source_ownership,
        "source_kinematic": True,
    }


def _prim_world_matrix(stage: Any, prim_path: str) -> np.ndarray:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"world_matrix_prim_missing:{prim_path}")
    matrix = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(prim)
    values = np.asarray(
        [[float(matrix[row][column]) for column in range(4)] for row in range(4)],
        dtype=np.float64,
    )
    return _affine_matrix(values, name="prim_world")


def _optional_config_value(node: Any, name: str, default: Any = None) -> Any:
    if isinstance(node, Mapping):
        return node.get(name, default)
    return getattr(node, name, default)


def resolve_camera_contract_record(
    stage: Any,
    *,
    contract_id: str,
    camera_configs: Sequence[Any],
    compatibility: str,
    rendering_dt: float,
) -> dict[str, Any]:
    from pxr import UsdGeom

    if not isinstance(contract_id, str) or not contract_id:
        raise ValueError("camera_contract_id_invalid")
    if not isinstance(compatibility, str) or not compatibility:
        raise ValueError("camera_contract_compatibility_invalid")
    if not math.isfinite(rendering_dt) or rendering_dt <= 0.0:
        raise ValueError("camera_contract_rendering_dt_invalid")
    configs = tuple(camera_configs)
    if not configs:
        raise ValueError("camera_configs_required")

    cameras = []
    for config in configs:
        prim_path = str(_config_value(config, "prim_path"))
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid() or not prim.IsA(UsdGeom.Camera):
            raise RuntimeError(f"camera_prim_invalid:{prim_path}")
        camera = UsdGeom.Camera(prim)
        focal_length = float(camera.GetFocalLengthAttr().Get())
        horizontal_aperture = float(camera.GetHorizontalApertureAttr().Get())
        vertical_aperture = float(camera.GetVerticalApertureAttr().Get())
        clipping_range = [
            float(value) for value in camera.GetClippingRangeAttr().Get()
        ]

        expected_focal_length = float(_config_value(config, "focal_length"))
        if not math.isclose(
            focal_length, expected_focal_length, rel_tol=0.0, abs_tol=1.0e-6
        ):
            raise ValueError(
                f"camera_focal_length_mismatch:{prim_path}:"
                f"expected={expected_focal_length}:actual={focal_length}"
            )
        expected_clipping = _optional_config_value(config, "clipping_range")
        if expected_clipping is not None and not np.allclose(
            clipping_range,
            np.asarray(expected_clipping, dtype=np.float64),
            rtol=0.0,
            atol=1.0e-6,
        ):
            raise ValueError(
                f"camera_clipping_range_mismatch:{prim_path}:"
                f"expected={list(expected_clipping)}:actual={clipping_range}"
            )
        frequency = _optional_config_value(config, "frequency", 60)
        if type(frequency) is not int or frequency <= 0:
            raise ValueError(f"camera_frequency_invalid:{prim_path}")

        cameras.append(
            {
                "name": str(_config_value(config, "name")),
                "prim_path": prim_path,
                "resolution": [
                    int(value) for value in _config_value(config, "resolution")
                ],
                "image_type": str(_config_value(config, "image_type")),
                "frequency": frequency,
                "focal_length": focal_length,
                "horizontal_aperture": horizontal_aperture,
                "vertical_aperture": vertical_aperture,
                "clipping_range": clipping_range,
                "world_transform": _prim_world_matrix(stage, prim_path).tolist(),
            }
        )

    payload = {
        "schema_version": 2,
        "id": contract_id,
        "compatibility": compatibility,
        "rendering_dt": float(rendering_dt),
        "cameras": cameras,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {**payload, "sha256": hashlib.sha256(encoded).hexdigest()}


def require_camera_contract_sha256(
    record: Mapping[str, Any],
    *,
    expected_sha256: str,
) -> Mapping[str, Any]:
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValueError("camera_contract_expected_sha256_invalid")
    if record.get("sha256") != expected_sha256:
        raise ValueError(
            "camera_contract_sha256_mismatch:"
            f"expected={expected_sha256}:actual={record.get('sha256')}"
        )
    return record


def _matrix_to_world_pose(matrix: Any) -> tuple[np.ndarray, np.ndarray]:
    from pxr import Gf

    values = _affine_matrix(matrix, name="world_pose")
    gf_matrix = Gf.Matrix4d(*values.reshape(-1).tolist())
    quaternion = gf_matrix.ExtractRotationQuat()
    imaginary = quaternion.GetImaginary()
    orientation_wxyz = np.asarray(
        [
            float(quaternion.GetReal()),
            float(imaginary[0]),
            float(imaginary[1]),
            float(imaginary[2]),
        ],
        dtype=np.float64,
    )
    return values[3, :3].copy(), orientation_wxyz


def _world_pose_to_matrix(
    position: Any,
    orientation_wxyz: Any,
) -> np.ndarray:
    """Convert an Isaac scalar-first pose to the row-affine matrix used by Gf."""
    translation = np.asarray(position, dtype=np.float64)
    orientation = np.asarray(orientation_wxyz, dtype=np.float64)
    if translation.shape != (3,) or not np.isfinite(translation).all():
        raise ValueError("world_pose_position_invalid")
    if orientation.shape != (4,) or not np.isfinite(orientation).all():
        raise ValueError("world_pose_orientation_invalid")
    norm = float(np.linalg.norm(orientation))
    if norm <= 0.0:
        raise ValueError("world_pose_orientation_invalid")
    w, x, y, z = orientation / norm
    column_rotation = np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)],
            [2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)],
            [2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = column_rotation.T
    result[3, :3] = translation
    return _affine_matrix(result, name="world_pose")


def _single_rigid_world_matrix(single_rigid_prim: Any) -> np.ndarray:
    getter = getattr(single_rigid_prim, "get_world_pose", None)
    if not callable(getter):
        raise TypeError("single_rigid_world_pose_reader_required")
    position, orientation_wxyz = getter()
    return _world_pose_to_matrix(position, orientation_wxyz)


def read_rigid_body_com_state(
    rigid_body: Any,
    *,
    body_path: str,
) -> dict[str, list[float]]:
    if not isinstance(body_path, str) or not body_path:
        raise ValueError("controlled_contact_body_path_invalid")
    for method_name in (
        "get_world_pose",
        "get_com",
        "get_linear_velocity",
        "get_angular_velocity",
    ):
        if not callable(getattr(rigid_body, method_name, None)):
            raise TypeError(
                f"controlled_contact_body_reader_required:{body_path}:{method_name}"
            )
    position, orientation = rigid_body.get_world_pose()
    world_matrix = _world_pose_to_matrix(position, orientation)
    orientation = np.asarray(orientation, dtype=np.float64)
    orientation = orientation / np.linalg.norm(orientation)
    first_nonzero = next(
        (float(value) for value in orientation if value != 0.0),
        0.0,
    )
    if first_nonzero < 0.0:
        orientation = -orientation
    orientation[orientation == 0.0] = 0.0
    com = rigid_body.get_com()
    if not isinstance(com, tuple) or len(com) != 2:
        raise RuntimeError(f"controlled_contact_com_unavailable:{body_path}")
    local_com = np.asarray(com[0], dtype=np.float64)
    if local_com.shape != (3,) or not np.isfinite(local_com).all():
        raise RuntimeError(f"controlled_contact_com_invalid:{body_path}")
    world_com = (np.concatenate((local_com, [1.0])) @ world_matrix)[:3]
    linear = np.asarray(rigid_body.get_linear_velocity(), dtype=np.float64)
    angular = np.asarray(rigid_body.get_angular_velocity(), dtype=np.float64)
    if (
        linear.shape != (3,)
        or angular.shape != (3,)
        or not np.isfinite(linear).all()
        or not np.isfinite(angular).all()
    ):
        raise RuntimeError(f"controlled_contact_velocity_invalid:{body_path}")
    return {
        "com_position_m": world_com.tolist(),
        "orientation_wxyz": orientation.tolist(),
        "linear_velocity_m_s": linear.tolist(),
        "angular_velocity_rad_s": angular.tolist(),
    }


def _tracked_child_world_matrix(
    *,
    child_authored_world: Any,
    parent_authored_world: Any,
    parent_current_world: Any,
) -> np.ndarray:
    child = _affine_matrix(child_authored_world, name="child_authored_world")
    authored_parent = _affine_matrix(
        parent_authored_world, name="parent_authored_world"
    )
    current_parent = _affine_matrix(
        parent_current_world, name="parent_current_world"
    )
    child_to_parent = child @ np.linalg.inv(authored_parent)
    return _affine_matrix(child_to_parent @ current_parent, name="child_current_world")


class SourceVisualMeshSynchronizer:
    """Align a collision-free source display mesh with the live PhysX body."""

    def __init__(
        self,
        *,
        source_authored_world_matrix: Any,
        read_source_world_matrix: Callable[[], Any],
        read_visual_mesh_world_matrix: Callable[[], Any],
        write_visual_mesh_parent_delta: Callable[[np.ndarray], None],
        translation_tolerance_m: float = 1.0e-5,
        linear_tolerance: float = 1.0e-5,
    ) -> None:
        if not callable(read_source_world_matrix):
            raise TypeError("source_visual_sync_source_reader_required")
        if not callable(read_visual_mesh_world_matrix):
            raise TypeError("source_visual_sync_mesh_reader_required")
        if not callable(write_visual_mesh_parent_delta):
            raise TypeError("source_visual_sync_mesh_writer_required")
        if (
            not math.isfinite(translation_tolerance_m)
            or translation_tolerance_m < 0.0
        ):
            raise ValueError("source_visual_sync_translation_tolerance_invalid")
        if not math.isfinite(linear_tolerance) or linear_tolerance < 0.0:
            raise ValueError("source_visual_sync_linear_tolerance_invalid")
        self._source_authored_world = _rigid_affine_matrix(
            source_authored_world_matrix,
            name="source_visual_sync_source_authored_world",
        ).copy()
        self._read_source_world = read_source_world_matrix
        self._read_visual_mesh_world = read_visual_mesh_world_matrix
        self._write_visual_mesh_parent_delta = write_visual_mesh_parent_delta
        self._translation_tolerance_m = float(translation_tolerance_m)
        self._linear_tolerance = float(linear_tolerance)
        self._write_visual_mesh_parent_delta(np.eye(4, dtype=np.float64))
        self._visual_mesh_authored_world = _affine_matrix(
            self._read_visual_mesh_world(),
            name="source_visual_sync_mesh_authored_world",
        ).copy()

    def sync(self) -> dict[str, Any]:
        source_world = _rigid_affine_matrix(
            self._read_source_world(), name="source_visual_sync_source_world"
        )
        parent_delta = _rigid_affine_matrix(
            source_world @ np.linalg.inv(self._source_authored_world),
            name="source_visual_sync_parent_delta",
        )
        self._write_visual_mesh_parent_delta(parent_delta)
        expected_mesh_world = _tracked_child_world_matrix(
            child_authored_world=self._visual_mesh_authored_world,
            parent_authored_world=self._source_authored_world,
            parent_current_world=source_world,
        )
        actual_mesh_world = _affine_matrix(
            self._read_visual_mesh_world(),
            name="source_visual_sync_mesh_world",
        )
        translation_error_m = float(
            np.linalg.norm(
                actual_mesh_world[3, :3] - expected_mesh_world[3, :3]
            )
        )
        linear_error_max_abs = float(
            np.max(
                np.abs(
                    actual_mesh_world[:3, :3] - expected_mesh_world[:3, :3]
                )
            )
        )
        valid = (
            translation_error_m <= self._translation_tolerance_m
            and linear_error_max_abs <= self._linear_tolerance
        )
        return {
            "policy": "visual_mesh_parent_delta_v1",
            "valid": valid,
            "translation_error_m": translation_error_m,
            "linear_error_max_abs": linear_error_max_abs,
            "source_physics_world_matrix_sha256": _matrix_sha256(source_world),
            "visual_mesh_parent_delta_sha256": _matrix_sha256(parent_delta),
            "expected_visual_mesh_world_matrix_sha256": _matrix_sha256(
                expected_mesh_world
            ),
            "actual_visual_mesh_world_matrix_sha256": _matrix_sha256(
                actual_mesh_world
            ),
        }


class ReadOnlySourceVisualMeshValidator:
    """Verify that a dynamic source child follows PhysX through inheritance."""

    def __init__(
        self,
        *,
        source_authored_world_matrix: Any,
        visual_mesh_authored_world_matrix: Any,
        read_source_world_matrix: Callable[[], Any],
        read_visual_mesh_world_matrix: Callable[[], Any],
        translation_tolerance_m: float = 1.0e-5,
        linear_tolerance: float = 1.0e-5,
    ) -> None:
        if not callable(read_source_world_matrix) or not callable(
            read_visual_mesh_world_matrix
        ):
            raise TypeError("source_visual_validator_reader_required")
        if (
            not math.isfinite(translation_tolerance_m)
            or translation_tolerance_m < 0.0
            or not math.isfinite(linear_tolerance)
            or linear_tolerance < 0.0
        ):
            raise ValueError("source_visual_validator_tolerance_invalid")
        self._source_authored_world = _rigid_affine_matrix(
            source_authored_world_matrix,
            name="source_visual_validator_source_authored_world",
        ).copy()
        self._visual_authored_world = _affine_matrix(
            visual_mesh_authored_world_matrix,
            name="source_visual_validator_mesh_authored_world",
        ).copy()
        self._read_source_world = read_source_world_matrix
        self._read_visual_world = read_visual_mesh_world_matrix
        self._translation_tolerance_m = float(translation_tolerance_m)
        self._linear_tolerance = float(linear_tolerance)

    def validate(self) -> dict[str, Any]:
        source_world = _rigid_affine_matrix(
            self._read_source_world(), name="source_visual_validator_source_world"
        )
        expected = _tracked_child_world_matrix(
            child_authored_world=self._visual_authored_world,
            parent_authored_world=self._source_authored_world,
            parent_current_world=source_world,
        )
        actual = _affine_matrix(
            self._read_visual_world(), name="source_visual_validator_mesh_world"
        )
        translation_error = float(
            np.linalg.norm(actual[3, :3] - expected[3, :3])
        )
        linear_error = float(
            np.max(np.abs(actual[:3, :3] - expected[:3, :3]))
        )
        return {
            "policy": "inherited_dynamic_child_readback_v1",
            "valid": (
                translation_error <= self._translation_tolerance_m
                and linear_error <= self._linear_tolerance
            ),
            "translation_error_m": translation_error,
            "linear_error_max_abs": linear_error,
            "source_or_visual_pose_write_count": 0,
            "source_physics_world_matrix_sha256": _matrix_sha256(source_world),
            "expected_visual_mesh_world_matrix_sha256": _matrix_sha256(expected),
            "actual_visual_mesh_world_matrix_sha256": _matrix_sha256(actual),
        }


def _source_visual_mesh_parent_delta_writer(
    stage: Any,
    *,
    visual_mesh_path: str,
) -> Callable[[np.ndarray], None]:
    """Author a display-only parent delta before a mesh's existing local ops."""
    from pxr import Gf, UsdGeom

    mesh = stage.GetPrimAtPath(visual_mesh_path)
    if not mesh or not mesh.IsValid() or not mesh.IsA(UsdGeom.Mesh):
        raise RuntimeError(f"source_visual_mesh_invalid:{visual_mesh_path}")
    for attribute_name in ("physics:collisionEnabled", "physics:rigidBodyEnabled"):
        attribute = mesh.GetAttribute(attribute_name)
        if attribute and attribute.Get() is True:
            raise RuntimeError(
                f"source_visual_mesh_must_not_drive_physics:{visual_mesh_path}:"
                f"{attribute_name}"
            )

    xformable = UsdGeom.Xformable(mesh)
    existing_ops = list(xformable.GetOrderedXformOps())
    sync_op_name = "xformOp:transform:labutopiaVisualSync"
    sync_op = next(
        (op for op in existing_ops if str(op.GetOpName()) == sync_op_name), None
    )
    if sync_op is None:
        sync_op = xformable.AddTransformOp(
            UsdGeom.XformOp.PrecisionDouble,
            "labutopiaVisualSync",
        )
    elif sync_op.GetOpType() != UsdGeom.XformOp.TypeTransform:
        raise RuntimeError(f"source_visual_sync_op_type_invalid:{visual_mesh_path}")
    ordered_ops = [
        sync_op
    ] + [op for op in existing_ops if str(op.GetOpName()) != sync_op_name]
    xformable.SetXformOpOrder(ordered_ops)

    def write(parent_delta: np.ndarray) -> None:
        values = _rigid_affine_matrix(
            parent_delta, name="source_visual_mesh_parent_delta"
        )
        sync_op.Set(Gf.Matrix4d(*values.reshape(-1).tolist()))

    return write


def _frame_at_world_matrix(template: Any, world_matrix: Any) -> Any:
    world = _affine_matrix(world_matrix, name="frame_world")

    def unit(values: np.ndarray) -> tuple[float, float, float]:
        norm = float(np.linalg.norm(values))
        if not math.isfinite(norm) or norm <= 0.0:
            raise RuntimeError("wrapper_axis_invalid")
        return tuple((values / norm).tolist())

    return replace(
        template,
        origin_world=tuple(world[3, :3].tolist()),
        x_axis_world=unit(world[0, :3]),
        y_axis_world=unit(world[1, :3]),
        z_axis_world=unit(world[2, :3]),
    )


class PhysicsSourceStateAdapter:
    """Replace stale USD task pose fields with one current PhysX pose snapshot."""

    def __init__(
        self,
        *,
        read_source_world_pose: Callable[[], tuple[Any, Any]],
        initial_geometry_center_world: Any,
        use_captured_pose: bool = False,
        read_grasp_state: Callable[[], Mapping[str, Any]] | None = None,
    ) -> None:
        if not callable(read_source_world_pose):
            raise TypeError("source_world_pose_reader_required")
        center = np.asarray(initial_geometry_center_world, dtype=np.float64)
        if center.shape != (3,) or not np.isfinite(center).all():
            raise ValueError("initial_geometry_center_world_invalid")
        self._read_pose = read_source_world_pose
        if type(use_captured_pose) is not bool:
            raise TypeError("use_captured_pose_bool_required")
        if read_grasp_state is not None and not callable(read_grasp_state):
            raise TypeError("grasp_state_reader_callable_required")
        self._use_captured_pose = use_captured_pose
        self._read_grasp_state = read_grasp_state
        initial_position, initial_orientation = self._read_pose()
        initial_world = _world_pose_to_matrix(initial_position, initial_orientation)
        center_homogeneous = np.concatenate([center, [1.0]])
        self._center_local = np.ascontiguousarray(
            center_homogeneous @ np.linalg.inv(initial_world), dtype=np.float64
        )
        self._position = np.asarray(initial_position, dtype=np.float64).copy()
        self._orientation_wxyz = np.asarray(
            initial_orientation, dtype=np.float64
        ).copy()
        self._world = initial_world.copy()

    def capture(self) -> np.ndarray:
        position, orientation = self._read_pose()
        self._position = np.asarray(position, dtype=np.float64).copy()
        self._orientation_wxyz = np.asarray(orientation, dtype=np.float64).copy()
        self._world = _world_pose_to_matrix(
            self._position, self._orientation_wxyz
        )
        return self._world.copy()

    def world_matrix(self) -> np.ndarray:
        return self._world.copy()

    def center_world(self) -> np.ndarray:
        return np.ascontiguousarray((self._center_local @ self._world)[:3])

    def __call__(self, state: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(state, Mapping):
            raise TypeError("physics_source_state_mapping_required")
        if not self._use_captured_pose:
            self.capture()
        orientation = self._orientation_wxyz.copy()
        orientation /= np.linalg.norm(orientation)
        center_world = self._center_local @ self._world
        adapted = dict(state)
        adapted["object_position"] = np.ascontiguousarray(
            center_world[:3], dtype=np.float64
        )
        adapted["object_quaternion"] = np.ascontiguousarray(
            orientation[[1, 2, 3, 0]], dtype=np.float64
        )
        if self._read_grasp_state is not None:
            grasp_state = self._read_grasp_state()
            if not isinstance(grasp_state, Mapping):
                raise TypeError("online_fluid_grasp_state_mapping_required")
            adapted["online_fluid_grasp"] = dict(grasp_state)
        return adapted


def set_single_rigid_kinematic_target(
    single_rigid_prim: Any,
    *,
    position: Any,
    orientation_wxyz: Any,
) -> None:
    """Set an actual PhysX kinematic target instead of teleporting the body."""
    position_values = np.asarray(position, dtype=np.float32)
    orientation_values = np.asarray(orientation_wxyz, dtype=np.float32)
    if position_values.shape != (3,) or not np.isfinite(position_values).all():
        raise ValueError("kinematic_target_position_invalid")
    if (
        orientation_values.shape != (4,)
        or not np.isfinite(orientation_values).all()
        or float(np.linalg.norm(orientation_values)) <= 0.0
    ):
        raise ValueError("kinematic_target_orientation_invalid")
    orientation_values = orientation_values / np.linalg.norm(orientation_values)
    prim_view = getattr(single_rigid_prim, "_prim_view", None)
    physics_view = getattr(prim_view, "_physics_view", None)
    if physics_view is None or not hasattr(physics_view, "set_kinematic_targets"):
        raise RuntimeError("physx_kinematic_target_view_unavailable")
    target_xyzw = np.concatenate(
        [position_values, orientation_values[1:], orientation_values[:1]]
    ).reshape(1, 7)
    physics_view.set_kinematic_targets(
        np.ascontiguousarray(target_xyzw, dtype=np.float32),
        np.asarray([0], dtype=np.int32),
    )


class AuthoredWrapperFrameReader:
    def __init__(
        self,
        stage: Any,
        *,
        parent_path: str,
        visual_mesh_path: str,
        parent_world_matrix: Callable[[], Any] | None = None,
    ):
        from tools.labutopia_fluid.real_beaker import (
            derive_authored_fluid_wrapper_frame,
        )

        self.stage = stage
        self.parent_path = parent_path
        self.wrapper_path = f"{parent_path.rstrip('/')}/FluidSafeWrapperCanonical"
        self.template = derive_authored_fluid_wrapper_frame(
            stage,
            parent_path=parent_path,
            visual_mesh_path=visual_mesh_path,
        )
        self._authored_parent_world = _prim_world_matrix(stage, parent_path)
        self._authored_wrapper_world = _prim_world_matrix(stage, self.wrapper_path)
        self._read_parent_world = parent_world_matrix or (
            lambda: _prim_world_matrix(stage, parent_path)
        )

    def __call__(self) -> Any:
        world = _tracked_child_world_matrix(
            child_authored_world=self._authored_wrapper_world,
            parent_authored_world=self._authored_parent_world,
            parent_current_world=self._read_parent_world(),
        )
        return _frame_at_world_matrix(self.template, world)


def _table_top_z(stage: Any, table_path: str) -> float:
    from pxr import Usd, UsdGeom

    table = stage.GetPrimAtPath(table_path)
    if not table or not table.IsValid():
        raise RuntimeError(f"fluid_table_prim_missing:{table_path}")
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
        useExtentsHint=True,
    )
    return float(cache.ComputeWorldBound(table).ComputeAlignedBox().GetMax()[2])


class FluidTransferScorer:
    def __init__(
        self,
        *,
        source_frame: Callable[[], Any],
        target_frame: Callable[[], Any],
        table_z: float,
        minimum_target_particles: int,
        minimum_task_target_fraction: float,
        minimum_expert_target_fraction: float,
    ) -> None:
        self.source_frame = source_frame
        self.target_frame = target_frame
        self.table_z = float(table_z)
        self.minimum_target_particles = int(minimum_target_particles)
        self.minimum_task_target_fraction = float(minimum_task_target_fraction)
        self.minimum_expert_target_fraction = float(
            minimum_expert_target_fraction
        )

    def __call__(self, positions: np.ndarray) -> dict[str, Any]:
        source = self.source_frame()
        target = self.target_frame()
        result = classify_transfer_positions(
            positions,
            source_frame=source,
            target_frame=target,
            table_z=self.table_z,
            minimum_target_particles=self.minimum_target_particles,
            minimum_task_target_fraction=self.minimum_task_target_fraction,
            minimum_expert_target_fraction=self.minimum_expert_target_fraction,
        )
        result.update(
            {
                "source_frame_origin_world": [
                    float(value) for value in source.origin_world
                ],
                "source_frame_z_axis_world": [
                    float(value) for value in source.z_axis_world
                ],
                "target_frame_origin_world": [
                    float(value) for value in target.origin_world
                ],
            }
        )
        return result


def make_substep_containment_sampler(
    *,
    read_particles: Callable[[], Any],
    score_particles: Callable[[Any], Mapping[str, Any]],
    capture_source_state: Callable[[], Any] | None = None,
) -> Callable[[], Mapping[str, Any]]:
    if not callable(read_particles) or not callable(score_particles):
        raise TypeError("substep_containment_reader_and_scorer_required")
    if capture_source_state is not None and not callable(capture_source_state):
        raise TypeError("substep_containment_source_capture_callable_required")

    def sample() -> Mapping[str, Any]:
        if capture_source_state is not None:
            capture_source_state()
        return score_particles(read_particles())

    return sample


def build_isaac_fluid_evaluation_loop(
    *,
    cfg: Any,
    world: Any,
    task: Any,
    stage: Any,
) -> Any:
    """Build the production 5.1 adapter after the task's first fixed reset."""
    from isaacsim.core.prims import SingleRigidPrim

    from tools.labutopia_fluid.interndata_surface_reconstruction import (
        reconstruct_surface_live,
    )
    from utils.fluid_evaluation_loop import FluidEvaluationLoop
    from utils.online_fluid_surface import read_strict_simulation_points

    fluid = _config_value(cfg, "online_fluid")
    configure_fluid_world_timing(
        world,
        physics_dt=float(_config_value(fluid, "physics_dt")),
        rendering_dt=float(_config_value(fluid, "rendering_dt")),
    )
    validate_fluid_stage_contract(stage, fluid)
    source_ownership = str(_config_value(fluid, "source_ownership"))
    controlled_contact_interlock = controlled_contact_interlock_requested(fluid)
    source_path = str(_config_value(fluid, "source_actor_path"))
    gripper_path = str(
        _config_value(
            fluid,
            "grasp_frame_path"
            if source_ownership == "contact_friction_dynamic_v1"
            else "gripper_frame_path",
        )
    )
    source_visual_mesh_path = str(
        _config_value(fluid, "source_visual_mesh_path")
    )
    source_authored_world = _prim_world_matrix(stage, source_path)
    source_visual_authored_world = _prim_world_matrix(
        stage, source_visual_mesh_path
    )
    source_body = construct_single_rigid_prim(
        SingleRigidPrim,
        prim_path=source_path,
        name="online_fluid_source_vessel",
    )
    source_body.initialize()

    def read_source_pose() -> tuple[Any, Any]:
        return source_body.get_world_pose()

    def read_source_world() -> np.ndarray:
        position, orientation = read_source_pose()
        return _world_pose_to_matrix(position, orientation)
    initial_geometry_center = task.object_utils.get_geometry_center(
        object_path=source_path
    )

    if source_ownership == "gripper_attached_kinematic_vessel":
        attachment_policy = str(
            _config_value(fluid, "attachment_matrix_policy")
        )
        if attachment_policy != (
            "captured_translation_then_recaptured_full_at_scripted_pour"
        ):
            raise ValueError(
                f"attachment_matrix_policy_unsupported:{attachment_policy}"
            )

        def write_source(matrix: np.ndarray) -> None:
            position, orientation = _matrix_to_world_pose(matrix)
            set_single_rigid_kinematic_target(
                source_body,
                position=position,
                orientation_wxyz=orientation,
            )

        source_visual_sync = SourceVisualMeshSynchronizer(
            source_authored_world_matrix=source_authored_world,
            read_source_world_matrix=read_source_world,
            read_visual_mesh_world_matrix=lambda: _prim_world_matrix(
                stage, source_visual_mesh_path
            ),
            write_visual_mesh_parent_delta=(
                _source_visual_mesh_parent_delta_writer(
                    stage,
                    visual_mesh_path=source_visual_mesh_path,
                )
            ),
        )
        attachment = GripperAttachedKinematicVessel(
            read_source_world_matrix=read_source_world,
            read_gripper_world_matrix=lambda: _prim_world_matrix(
                stage, gripper_path
            ),
            write_source_world_matrix=write_source,
        )
        source_state = PhysicsSourceStateAdapter(
            read_source_world_pose=read_source_pose,
            initial_geometry_center_world=initial_geometry_center,
        )
        source_parent_world = read_source_world
        sync_source_visual_state = source_visual_sync.sync
        reset_pre_roll_substeps = 0
    elif source_ownership == "contact_friction_dynamic_v1":
        robot = task.robot
        for method_name in (
            "initialize_contact_sensors",
            "read_contact_sensor_frames",
            "get_gripper_pad_relative_velocities_m_s",
            "validate_gripper_dof_contract",
        ):
            if not callable(getattr(robot, method_name, None)):
                raise RuntimeError(
                    f"contact_grasp_robot_method_required:{method_name}"
                )
        physics_dt = float(_config_value(fluid, "physics_dt"))
        robot.initialize_contact_sensors(physics_dt)
        robot.validate_gripper_dof_contract(
            tuple(_config_value(fluid, "finger_joint_indices"))
        )
        source_writer_audit = SourceBodyWriterAudit(
            source_body_path=source_path
        )
        source_writer_audit.install(
            source_body=source_body,
            object_utils=task.object_utils,
        )
        require_complete_writer_audit = bool(
            str(
                _optional_config_value(
                    fluid,
                    "execution_mode",
                    "production_pour_v1",
                )
            )
        == "contact_acquisition_probe_v1"
        or str(
            _optional_config_value(
                fluid,
                "execution_mode",
                "production_pour_v1",
            )
        )
        == "close_contact_allowed_v1"
        )
        finger_paths = tuple(
            str(path) for path in _config_value(fluid, "finger_body_paths")
        )
        initial_center_homogeneous = np.concatenate(
            [np.asarray(initial_geometry_center, dtype=np.float64), [1.0]]
        )
        center_local = initial_center_homogeneous @ np.linalg.inv(
            read_source_world()
        )

        def read_source_center_world() -> np.ndarray:
            return np.ascontiguousarray(
                (center_local @ read_source_world())[:3], dtype=np.float64
            )

        def read_physics_step() -> int:
            value = getattr(world, "current_time_step_index", None)
            value = value() if callable(value) else value
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise RuntimeError("contact_grasp_world_step_unavailable")
            return int(value)

        immediate_reporter = None
        controlled_classifier = None
        read_controlled_body_states = None
        if controlled_contact_interlock:
            from omni.physx import get_physx_simulation_interface
            from omni.physx.scripts.physicsUtils import PhysicsSchemaTools
            from pxr import Usd, UsdPhysics, UsdUtils

            cache = UsdUtils.StageCache.Get()
            stage_id = cache.GetId(stage).ToLongInt()
            baseline_pairs = tuple(
                tuple(str(path) for path in pair)
                for pair in _config_value(
                    fluid, "controlled_contact_baseline_collider_pairs"
                )
            )
            if any(len(pair) != 2 for pair in baseline_pairs):
                raise ValueError("controlled_contact_baseline_pairs_invalid")
            immediate_reporter = ImmediatePhysxContactReporter(
                get_full_contact_report=(
                    get_physx_simulation_interface().get_full_contact_report
                ),
                resolve_path=PhysicsSchemaTools.intToSdfPath,
                expected_stage_id=int(stage_id),
                provisional_background_pairs=baseline_pairs,
            )

            robot_root = stage.GetPrimAtPath(
                CONTACT_REPORT_HAND_BODY_PATH.rsplit("/", 1)[0]
            )
            robot_body_paths = tuple(
                sorted(
                    str(prim.GetPath())
                    for prim in Usd.PrimRange(robot_root)
                    if prim.HasAPI(UsdPhysics.RigidBodyAPI)
                    and (
                        not prim.GetAttribute("physics:rigidBodyEnabled")
                        or prim.GetAttribute("physics:rigidBodyEnabled").Get()
                        is not False
                    )
                )
            )
            known_body_paths = {
                str(prim.GetPath()) for prim in Usd.PrimRange.Stage(stage)
            }
            known_collider_paths = set()
            for prim in Usd.PrimRange.Stage(stage):
                if not prim.HasAPI(UsdPhysics.CollisionAPI):
                    continue
                enabled = prim.GetAttribute("physics:collisionEnabled")
                if enabled and enabled.Get() is False:
                    continue
                path = str(prim.GetPath())
                known_collider_paths.add(path)
                try:
                    known_body_paths.add(
                        resolve_enabled_rigid_body_path(stage, path)
                    )
                except RuntimeError:
                    known_body_paths.add(path)

            finger_colliders = {}
            rigid_bodies = {source_path: source_body}
            for side, path in zip(("left", "right"), finger_paths):
                prim = stage.GetPrimAtPath(path)
                colliders = tuple(
                    sorted(
                        str(candidate.GetPath())
                        for candidate in Usd.PrimRange(prim)
                        if candidate.HasAPI(UsdPhysics.CollisionAPI)
                        and (
                            not candidate.GetAttribute("physics:collisionEnabled")
                            or candidate.GetAttribute("physics:collisionEnabled").Get()
                            is not False
                        )
                    )
                )
                if not colliders:
                    raise RuntimeError(
                        f"controlled_contact_finger_colliders_missing:{path}"
                    )
                finger_colliders[side] = {
                    "body_path": path,
                    "collider_paths": colliders,
                }
                body = construct_single_rigid_prim(
                    SingleRigidPrim,
                    prim_path=path,
                    name=f"controlled_contact_{side}_finger",
                )
                body.initialize()
                rigid_bodies[path] = body
            hand_body = construct_single_rigid_prim(
                SingleRigidPrim,
                prim_path=CONTACT_REPORT_HAND_BODY_PATH,
                name="controlled_contact_hand",
            )
            hand_body.initialize()
            rigid_bodies[CONTACT_REPORT_HAND_BODY_PATH] = hand_body

            def read_body_states() -> dict[str, Any]:
                states = {
                    path: read_rigid_body_com_state(body, body_path=path)
                    for path, body in rigid_bodies.items()
                }
                tool_position = _prim_world_matrix(stage, gripper_path)[3, :3]
                hand_state = states[CONTACT_REPORT_HAND_BODY_PATH]
                tool_velocity = np.asarray(
                    hand_state["linear_velocity_m_s"], dtype=np.float64
                ) + np.cross(
                    np.asarray(
                        hand_state["angular_velocity_rad_s"],
                        dtype=np.float64,
                    ),
                    tool_position
                    - np.asarray(hand_state["com_position_m"], dtype=np.float64),
                )
                states[gripper_path] = {
                    "position_m": tool_position.tolist(),
                    "linear_velocity_m_s": tool_velocity.tolist(),
                }
                return states

            episode_impulses = {"normal": 0.0, "total": 0.0}
            postcontact_source_motion = PostcontactSourceMotionAccumulator(
                maximum_path_m=float(
                    _config_value(
                        fluid,
                        "controlled_contact_maximum_postcontact_source_path_m",
                    )
                ),
                maximum_angular_variation_degrees=float(
                    _config_value(
                        fluid,
                        "controlled_contact_maximum_postcontact_angular_variation_degrees",
                    )
                ),
            )
            postcontact_tool_motion = PostcontactToolMotionAccumulator(
                physics_dt=physics_dt,
                approach_direction_world=_config_value(
                    fluid, "expert_pick_approach_direction_world"
                ),
                maximum_downward_coast_m=float(
                    _config_value(
                        fluid,
                        "controlled_contact_maximum_downward_coast_m",
                    )
                ),
                maximum_contact_step_speed_m_s=float(
                    _config_value(
                        fluid,
                        "controlled_contact_maximum_precontact_relative_speed_m_s",
                    )
                ),
                maximum_settled_speed_m_s=float(
                    _config_value(
                        fluid,
                        "controlled_contact_maximum_settled_tool_speed_m_s",
                    )
                ),
            )
            grasp_axis_object = np.asarray(
                _config_value(fluid, "grasp_height_axis_object"),
                dtype=np.float64,
            )

            def classify_immediate_report(
                *,
                report: Mapping[str, Any],
                phase: str,
                pre_body_states: Mapping[str, Any],
                post_body_states: Mapping[str, Any],
            ) -> dict[str, Any]:
                source_world = read_source_world()
                source_axis_world = grasp_axis_object @ source_world[:3, :3]
                source_axis_world = source_axis_world / np.linalg.norm(
                    source_axis_world
                )
                result = evaluate_controlled_contact_report(
                    report=report,
                    phase=phase,
                    source_body_path=source_path,
                    source_external_collider_paths=(
                        str(_config_value(fluid, "source_external_shell_path")),
                    ),
                    finger_pairs=finger_colliders,
                    robot_body_paths=robot_body_paths,
                    known_body_paths=tuple(sorted(known_body_paths)),
                    known_collider_paths=tuple(sorted(known_collider_paths)),
                    baseline_collider_pairs=baseline_pairs,
                    source_center_world_m=read_source_center_world(),
                    source_axis_world=source_axis_world,
                    grasp_height_band_m=tuple(
                        _config_value(fluid, "grasp_height_band_m")
                    ),
                    pre_body_states=pre_body_states,
                    post_body_states=post_body_states,
                    normal_convention=str(
                        _config_value(
                            fluid, "controlled_contact_normal_convention"
                        )
                    ),
                    minimum_inward_normal_cosine=float(
                        _config_value(
                            fluid, "grasp_contact_min_inward_normal_cosine"
                        )
                    ),
                    maximum_penetration_m=float(
                        _config_value(
                            fluid, "controlled_contact_maximum_penetration_m"
                        )
                    ),
                    maximum_precontact_relative_speed_m_s=float(
                        _config_value(
                            fluid,
                            "controlled_contact_maximum_precontact_relative_speed_m_s",
                        )
                    ),
                    maximum_close_relative_speed_m_s=float(
                        _config_value(
                            fluid,
                            "controlled_contact_maximum_close_relative_speed_m_s",
                        )
                    ),
                    maximum_step_normal_impulse_n_s=float(
                        _config_value(
                            fluid,
                            "controlled_contact_maximum_step_normal_impulse_n_s",
                        )
                    ),
                    maximum_step_total_impulse_n_s=float(
                        _config_value(
                            fluid,
                            "controlled_contact_maximum_step_total_impulse_n_s",
                        )
                    ),
                    episode_normal_impulse_before_n_s=episode_impulses["normal"],
                    episode_total_impulse_before_n_s=episode_impulses["total"],
                    maximum_episode_normal_impulse_n_s=float(
                        _config_value(
                            fluid,
                            "controlled_contact_maximum_episode_normal_impulse_n_s",
                        )
                    ),
                    maximum_episode_total_impulse_n_s=float(
                        _config_value(
                            fluid,
                            "controlled_contact_maximum_episode_total_impulse_n_s",
                        )
                    ),
                    maximum_source_linear_speed_m_s=float(
                        _config_value(
                            fluid,
                            "controlled_contact_maximum_source_linear_speed_m_s",
                        )
                    ),
                    maximum_source_angular_speed_rad_s=math.radians(
                        float(
                            _config_value(
                                fluid,
                                "controlled_contact_maximum_source_angular_speed_degrees_s",
                            )
                        )
                    ),
                    physics_dt=physics_dt,
                )
                intended_contact_occurring = any(
                    record.get("class")
                    in {"INTENDED_PRECONTACT", "INTENDED_CLOSE_CONTACT"}
                    for record in result["records"]
                )
                source_motion = postcontact_source_motion.update(
                    pre_source_state=pre_body_states[source_path],
                    post_source_state=post_body_states[source_path],
                    intended_contact_occurring=intended_contact_occurring,
                )
                tool_motion = postcontact_tool_motion.update(
                    pre_tool_state=pre_body_states[gripper_path],
                    post_tool_state=post_body_states[gripper_path],
                    intended_contact_occurring=intended_contact_occurring,
                )
                payload = dict(result)
                payload.pop("evidence_sha256", None)
                payload["postcontact_source_motion"] = source_motion
                payload["postcontact_tool_motion"] = tool_motion
                if not source_motion["valid"] or not tool_motion["valid"]:
                    if payload["terminal_kind"] is None:
                        payload["terminal_kind"] = "PHYSICAL_MOTION_FAILURE"
                    payload["precontact_latch"] = None
                result = {
                    **payload,
                    "evidence_sha256": canonical_json_sha256(payload),
                }
                episode_impulses["normal"] = result[
                    "episode_normal_impulse_n_s"
                ]
                episode_impulses["total"] = result[
                    "episode_total_impulse_n_s"
                ]
                return result

            def reset_immediate_classifier() -> None:
                episode_impulses.update(normal=0.0, total=0.0)
                postcontact_source_motion.reset()
                postcontact_tool_motion.reset()

            classify_immediate_report.reset = reset_immediate_classifier

            controlled_classifier = classify_immediate_report
            read_controlled_body_states = read_body_states

        attachment = ContactFrictionDynamicVessel(
            source_body_path=source_path,
            **dynamic_contact_grasp_parameters(fluid),
            left_finger_body_path=finger_paths[0],
            right_finger_body_path=finger_paths[1],
            read_source_world_matrix=read_source_world,
            read_source_center_world=read_source_center_world,
            read_gripper_world_matrix=lambda: _prim_world_matrix(
                stage, gripper_path
            ),
            read_finger_world_matrices=lambda: tuple(
                _prim_world_matrix(stage, path) for path in finger_paths
            ),
            read_contact_sensor_frames=robot.read_contact_sensor_frames,
            read_physics_step=read_physics_step,
            read_finger_joint_velocities=(
                robot.get_gripper_pad_relative_velocities_m_s
            ),
            physics_dt=physics_dt,
            allow_preclose_contact=bool(
                str(
                    _optional_config_value(
                        fluid, "execution_mode", "production_pour_v1"
                    )
                )
                in {"close_contact_allowed_v1", "production_pour_v1"}
            ),
            minimum_side_projection_m=float(
                _config_value(fluid, "grasp_contact_min_side_projection_m")
            ),
            required_consecutive_steps=int(
                _config_value(fluid, "grasp_contact_min_consecutive_steps")
            ),
            maximum_finger_speed_m_s=float(
                _config_value(
                    fluid,
                    "grasp_contact_max_pad_relative_speed_mps",
                )
            ),
            contact_timeout_s=float(
                _config_value(fluid, "grasp_contact_timeout_s")
            ),
            contact_loss_grace_steps=int(
                _config_value(fluid, "grasp_contact_loss_grace_steps")
            ),
            preclose_source_translation_limit_m=float(
                _config_value(
                    fluid,
                    "grasp_preclose_source_translation_limit_m",
                )
            ),
            preclose_source_tilt_limit_degrees=float(
                _config_value(
                    fluid,
                    "grasp_preclose_source_tilt_limit_degrees",
                )
            ),
            resolve_body_path=lambda path: resolve_enabled_rigid_body_path(
                stage, path
            ),
            source_writer_audit=source_writer_audit,
            require_complete_writer_audit=require_complete_writer_audit,
            immediate_contact_reporter=immediate_reporter,
            controlled_contact_classifier=controlled_classifier,
            read_controlled_body_states=read_controlled_body_states,
            controlled_contact_baseline_collider_pairs=(
                baseline_pairs if controlled_contact_interlock else ()
            ),
            controlled_settle_required_steps=int(
                _config_value(fluid, "controlled_contact_settle_required_steps")
            ) if controlled_contact_interlock else 60,
            controlled_precontact_settle_required_steps=int(
                _config_value(
                    fluid,
                    "controlled_contact_precontact_settle_required_steps",
                )
            ) if controlled_contact_interlock else 60,
            controlled_close_required_steps=int(
                _config_value(fluid, "controlled_contact_close_required_steps")
            ) if controlled_contact_interlock else None,
            controlled_contact_settle_required_steps=int(
                _config_value(
                    fluid,
                    "controlled_contact_contact_settle_required_steps",
                )
            ) if controlled_contact_interlock else 60,
            controlled_pregrasp_deadline_steps=int(
                _config_value(
                    fluid, "controlled_contact_pregrasp_deadline_steps"
                )
            ) if controlled_contact_interlock else 3000,
            controlled_align_deadline_steps=int(
                _config_value(fluid, "controlled_contact_align_deadline_steps")
            ) if controlled_contact_interlock else 9000,
            controlled_insert_deadline_steps=int(
                _config_value(fluid, "controlled_contact_insert_deadline_steps")
            ) if controlled_contact_interlock else 7200,
            controlled_settle_deadline_steps=int(
                _config_value(fluid, "controlled_contact_settle_deadline_steps")
            ) if controlled_contact_interlock else 600,
            controlled_precontact_settle_deadline_steps=int(
                _config_value(
                    fluid,
                    "controlled_contact_precontact_settle_deadline_steps",
                )
            ) if controlled_contact_interlock else 300,
            controlled_close_deadline_steps=int(
                _config_value(fluid, "controlled_contact_close_deadline_steps")
            ) if controlled_contact_interlock else 900,
            controlled_contact_settle_deadline_steps=int(
                _config_value(
                    fluid,
                    "controlled_contact_contact_settle_deadline_steps",
                )
            ) if controlled_contact_interlock else 300,
        )
        source_state = PhysicsSourceStateAdapter(
            read_source_world_pose=read_source_pose,
            initial_geometry_center_world=initial_geometry_center,
            use_captured_pose=True,
            read_grasp_state=attachment.state_record,
        )
        source_visual_validator = ReadOnlySourceVisualMeshValidator(
            source_authored_world_matrix=source_authored_world,
            visual_mesh_authored_world_matrix=source_visual_authored_world,
            read_source_world_matrix=source_state.world_matrix,
            read_visual_mesh_world_matrix=lambda: _prim_world_matrix(
                stage, source_visual_mesh_path
            ),
        )

        def capture_and_validate_source_visual() -> dict[str, Any]:
            source_state.capture()
            return source_visual_validator.validate()

        source_parent_world = source_state.world_matrix
        sync_source_visual_state = capture_and_validate_source_visual
        reset_pre_roll_substeps = int(
            _config_value(fluid, "dynamic_pre_roll_steps")
        )
    else:
        raise ValueError(f"fluid_source_ownership_unsupported:{source_ownership}")

    source_frame = AuthoredWrapperFrameReader(
        stage,
        parent_path=source_path,
        visual_mesh_path=source_visual_mesh_path,
        parent_world_matrix=source_parent_world,
    )
    target_frame = AuthoredWrapperFrameReader(
        stage,
        parent_path=str(_config_value(fluid, "target_actor_path")),
        visual_mesh_path=str(_config_value(fluid, "target_visual_mesh_path")),
    )
    scorer = FluidTransferScorer(
        source_frame=source_frame,
        target_frame=target_frame,
        table_z=_table_top_z(stage, str(_config_value(fluid, "table_path"))),
        minimum_target_particles=int(
            _config_value(fluid, "minimum_target_particles")
        ),
        minimum_task_target_fraction=float(
            _config_value(fluid, "minimum_task_target_fraction")
        ),
        minimum_expert_target_fraction=float(
            _config_value(fluid, "minimum_expert_target_fraction")
        ),
    )
    surface = IsaacFluidSurfaceAuthor(
        stage=stage,
        surface_path=str(_config_value(fluid, "surface_path")),
        material_path=str(_config_value(fluid, "surface_material_path")),
        hidden_liquid_paths=tuple(_config_value(fluid, "hidden_liquid_paths")),
        particle_system_path=str(_config_value(fluid, "particle_system_path")),
    )
    particle_path = str(_config_value(fluid, "particle_path"))
    expected_count = int(_config_value(fluid, "expected_particle_count"))

    def read_particles() -> Any:
        return read_strict_simulation_points(
            stage,
            particle_path,
            expected_particle_count=expected_count,
        )

    sample_containment_after_substep = make_substep_containment_sampler(
        read_particles=read_particles,
        score_particles=scorer,
        capture_source_state=(
            source_state.capture
            if source_ownership == "contact_friction_dynamic_v1"
            else None
        ),
    )
    camera_contract_id = str(_config_value(fluid, "camera_contract"))
    camera_contract = resolve_camera_contract_record(
        stage,
        contract_id=camera_contract_id,
        camera_configs=tuple(_config_value(cfg, "cameras")),
        compatibility=str(
            _optional_config_value(
                fluid,
                "camera_contract_compatibility",
                f"requires_{camera_contract_id}",
            )
        ),
        rendering_dt=float(_config_value(fluid, "rendering_dt")),
    )
    expected_camera_contract_sha256 = _optional_config_value(
        fluid, "camera_contract_sha256"
    )
    if expected_camera_contract_sha256 is not None:
        require_camera_contract_sha256(
            camera_contract,
            expected_sha256=str(expected_camera_contract_sha256),
        )
    initial_render_warmup_updates = (
        fluid.get("initial_render_warmup_updates", 0)
        if isinstance(fluid, Mapping)
        else getattr(fluid, "initial_render_warmup_updates", 0)
    )
    return FluidEvaluationLoop(
        world=world,
        task=task,
        expected_particle_count=expected_count,
        physics_substeps_per_observation=int(
            _config_value(fluid, "physics_substeps_per_observation")
        ),
        physics_substep_dt=float(_config_value(fluid, "physics_dt")),
        read_particles=read_particles,
        score_particles=scorer,
        reconstruct=reconstruct_surface_live,
        author_surface=surface,
        invalidate_surface=surface.invalidate,
        attachment=attachment,
        adapt_state=source_state,
        sync_source_visual_state=sync_source_visual_state,
        expected_camera_keys=tuple(_config_value(fluid, "model_camera_keys")),
        expected_camera_shape=tuple(_config_value(fluid, "model_camera_shape")),
        camera_contract=camera_contract,
        initial_render_warmup_updates=initial_render_warmup_updates,
        reset_pre_roll_substeps=reset_pre_roll_substeps,
        sample_containment_after_substep=sample_containment_after_substep,
        expected_source_ownership=source_ownership,
        controlled_contact_interlock=controlled_contact_interlock,
    )
