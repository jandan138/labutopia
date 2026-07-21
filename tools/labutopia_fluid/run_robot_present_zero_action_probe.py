#!/usr/bin/env python3
"""Run the hash-pinned robot-present zero-action fluid diagnostic."""

from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import traceback
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import (  # noqa: E402
    run_contact_grasp_passive_stability_probe as passive,
)


DEFAULT_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_source_rest_offset_zero_600hz_step600_layout_v1.yaml"
)
EXPECTED_CONFIG_SHA256 = (
    "c0f9d636f8cde61add964ee99f11bda0ac117b8512fc2db185209c52888b08a8"
)
EXPECTED_ASSET_SHA256 = (
    "7c7667850dfc80a1d04c8649657cf9d9f5369b82e21f97b3d5c87c07ca218b02"
)
EXPECTED_SCENE_DEPENDENCY_CLOSURE_SHA256 = (
    "c62a6317d8c9076a0c136a359db505b5a3be0ff26193a15376c57a9afc9a60ce"
)
EXPECTED_ROBOT_SHA256 = (
    "312a326e338949fb40fd245886508cc52cc47e2bebd696e99c7dcdd3d3a7f90b"
)
EXPECTED_ASSET_RELATIVE_PATH = (
    "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
EXPECTED_FRANKA_DOF_NAMES = (
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
EXPECTED_BOOTSTRAP_RESET_LABELS = (
    "task_constructor_camera_reset",
    "explicit_task_reset",
)
MANIFEST_TYPE = "robot_present_zero_action_probe_v1"
PROVISIONAL_REPORT_BASENAME = "provisional_report.json"
FINAL_REPORT_BASENAME = "report.json"
SOURCE_TRACE_BASENAME = passive.SOURCE_TRACE_BASENAME
PARTICLE_TRACE_BASENAME = passive.PARTICLE_TRACE_BASENAME
PARTITION_NAMES = passive.PARTITION_NAMES
REQUIRED_POST_ORIGIN_APIS = frozenset(
    {
        "world.reset",
        "world.render",
        "task.reset",
        "task.step",
        "robot.apply_action",
        "robot.set_joint_positions",
        "robot.set_joint_velocities",
        "robot.set_joint_efforts",
        "articulation_controller.apply_action",
        "articulation_view.apply_action",
        "articulation_view.set_joint_position_targets",
        "articulation_view.set_joint_velocity_targets",
        "articulation_view.set_joint_positions",
        "articulation_view.set_joint_velocities",
        "articulation_view.set_joint_efforts",
        "gripper.set_joint_positions",
        "source_body.set_world_pose",
        "source_body.set_linear_velocity",
        "object_utils.set_object_position",
    }
)


def sha256_file(path: str | os.PathLike[str]) -> str:
    return passive._sha256_file(Path(path))


def _config_value(node: Any, name: str) -> Any:
    if isinstance(node, Mapping):
        return node[name]
    return getattr(node, name)


def validate_effective_particle_readback_settings(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(expected, Mapping) or not expected:
        raise ValueError("robot_present_particle_readback_invalid")
    if not isinstance(actual, Mapping) or set(actual) != set(expected):
        raise ValueError("robot_present_particle_readback_invalid")
    normalized: dict[str, bool] = {}
    for path, expected_value in expected.items():
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or type(expected_value) is not bool
            or type(actual.get(path)) is not bool
            or actual[path] is not expected_value
        ):
            raise ValueError("robot_present_particle_readback_invalid")
        normalized[path] = actual[path]
    return {"settings": normalized, "valid": True}


def validate_candidate_contract(
    config: Any,
    *,
    config_sha256: str,
    asset_sha256: str,
) -> dict[str, Any]:
    try:
        fluid = _config_value(config, "online_fluid")
        robot = _config_value(config, "robot")
        values = {
            "task_type": str(_config_value(config, "task_type")),
            "usd_path": str(_config_value(config, "usd_path")),
            "physics_dt": float(_config_value(fluid, "physics_dt")),
            "rendering_dt": float(_config_value(fluid, "rendering_dt")),
            "pre_roll_steps": int(_config_value(fluid, "dynamic_pre_roll_steps")),
            "hold_steps": int(_config_value(fluid, "filled_static_hold_steps")),
            "expected_particle_count": int(
                _config_value(fluid, "expected_particle_count")
            ),
            "source_path": str(_config_value(fluid, "source_actor_path")),
            "particle_path": str(_config_value(fluid, "particle_path")),
            "robot_type": str(_config_value(robot, "type")),
            "robot_usd_path": str(_config_value(robot, "usd_path")),
            "robot_camera_frequency": int(
                _config_value(robot, "camera_frequency")
            ),
            "robot_position": [
                float(value) for value in _config_value(robot, "position")
            ],
        }
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("robot_present_candidate_config_invalid") from exc

    valid = bool(
        config_sha256 == EXPECTED_CONFIG_SHA256
        and asset_sha256 == EXPECTED_ASSET_SHA256
        and values["task_type"] == "pickpour"
        and values["usd_path"] == EXPECTED_ASSET_RELATIVE_PATH
        and math.isclose(
            values["physics_dt"], 1.0 / 600.0, rel_tol=0.0, abs_tol=1.0e-15
        )
        and math.isclose(
            values["rendering_dt"], 1.0 / 30.0, rel_tol=0.0, abs_tol=1.0e-15
        )
        and values["pre_roll_steps"] == 600
        and values["hold_steps"] == 1800
        and values["expected_particle_count"] == 3600
        and values["source_path"] == "/World/beaker2"
        and values["particle_path"]
        == "/World/InternDataParityFluid/Particles"
        and values["robot_type"] == "franka"
        and values["robot_usd_path"] == "assets/robots/Franka.usd"
        and values["robot_camera_frequency"] == 30
        and np.array_equal(
            np.asarray(values["robot_position"], dtype=np.float64),
            np.asarray([-0.4, 0.0, 0.71], dtype=np.float64),
        )
        and math.isclose(
            values["physics_dt"] * values["pre_roll_steps"],
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
        and math.isclose(
            values["physics_dt"] * values["hold_steps"],
            3.0,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    )
    if not valid:
        raise ValueError("robot_present_candidate_config_invalid")
    record_count = 1 + values["pre_roll_steps"] + values["hold_steps"]
    return {
        **values,
        "config_sha256": config_sha256,
        "asset_sha256": asset_sha256,
        "record_count": record_count,
        "source_trace_shape": [record_count, 4, 4],
        "particle_trace_shape": [
            record_count,
            values["expected_particle_count"],
            3,
        ],
        "valid": True,
    }


def validate_bootstrap_reset_contract(
    reset_labels: Sequence[str],
) -> dict[str, Any]:
    labels = tuple(str(label) for label in reset_labels)
    if labels != EXPECTED_BOOTSTRAP_RESET_LABELS:
        raise RuntimeError("zero_action_bootstrap_reset_contract_invalid")
    return {
        "reset_count": len(labels),
        "reset_labels": list(labels),
        "prepended_world_reset_count": 0,
        "post_origin_reset_count": 0,
        "valid": True,
    }


class ZeroActionLedger:
    """Instrument the small set of command APIs relevant to this probe."""

    def __init__(self) -> None:
        self._authority_origin = False
        self._events: list[dict[str, Any]] = []
        self._instrumentation: list[dict[str, Any]] = []
        self._reset_labels: list[str] = []
        self._expected_reset_label: str | None = None

    def _record(self, api_name: str, *, reset_label: str | None = None) -> None:
        self._events.append(
            {
                "sequence": len(self._events),
                "phase": (
                    "post_origin" if self._authority_origin else "bootstrap"
                ),
                "api": api_name,
                "reset_label": reset_label,
            }
        )

    def instrument(
        self,
        target: Any,
        method_name: str,
        api_name: str,
        *,
        required: bool,
    ) -> bool:
        if any(
            record["target_id"] == id(target)
            and record["method_name"] == method_name
            for record in self._instrumentation
        ):
            raise RuntimeError(f"zero_action_duplicate_instrumentation:{api_name}")
        original = getattr(target, method_name, None)
        available = callable(original)
        record = {
            "target_type": type(target).__name__,
            "target_id": id(target),
            "method_name": method_name,
            "api": api_name,
            "required": required,
            "available": available,
            "installed": False,
        }
        self._instrumentation.append(record)
        if not available:
            if required:
                raise RuntimeError(f"zero_action_instrumentation_missing:{api_name}")
            return False

        @functools.wraps(original)
        def instrumented(*args: Any, **kwargs: Any) -> Any:
            if api_name == "world.reset":
                if self._authority_origin:
                    self._record(api_name)
                    raise RuntimeError(f"zero_action_post_origin_call:{api_name}")
                label = self._expected_reset_label
                if label is None:
                    self._record(api_name)
                    raise RuntimeError("zero_action_unexpected_bootstrap_reset")
                if label in self._reset_labels:
                    self._record(api_name, reset_label=label)
                    raise RuntimeError("zero_action_duplicate_bootstrap_reset")
                self._reset_labels.append(label)
                self._record(api_name, reset_label=label)
                return original(*args, **kwargs)

            self._record(api_name)
            if self._authority_origin:
                raise RuntimeError(f"zero_action_post_origin_call:{api_name}")
            return original(*args, **kwargs)

        try:
            setattr(target, method_name, instrumented)
        except (AttributeError, TypeError) as exc:
            record["available"] = False
            record["failure"] = type(exc).__name__
            if required:
                raise RuntimeError(
                    f"zero_action_instrumentation_failed:{api_name}"
                ) from exc
            return False
        record["installed"] = True
        return True

    @contextlib.contextmanager
    def expect_bootstrap_reset(self, label: str) -> Iterator[None]:
        if self._authority_origin or self._expected_reset_label is not None:
            raise RuntimeError("zero_action_reset_expectation_state_invalid")
        if label not in EXPECTED_BOOTSTRAP_RESET_LABELS:
            raise ValueError("zero_action_bootstrap_reset_label_invalid")
        before = len(self._reset_labels)
        self._expected_reset_label = label
        try:
            yield
        finally:
            self._expected_reset_label = None
        if len(self._reset_labels) != before + 1 or self._reset_labels[-1] != label:
            raise RuntimeError(f"zero_action_expected_reset_missing:{label}")

    def mark_authority_origin(self) -> dict[str, Any]:
        if self._authority_origin or self._expected_reset_label is not None:
            raise RuntimeError("zero_action_authority_origin_state_invalid")
        contract = validate_bootstrap_reset_contract(self._reset_labels)
        self._authority_origin = True
        return contract

    def assert_zero_post_origin(self) -> None:
        calls = [
            record for record in self._events if record["phase"] == "post_origin"
        ]
        if calls:
            raise RuntimeError(
                "zero_action_contract_violated:"
                + ",".join(record["api"] for record in calls)
            )

    def summary(self) -> dict[str, Any]:
        post_origin = [
            record for record in self._events if record["phase"] == "post_origin"
        ]
        counts: dict[str, int] = {}
        for record in post_origin:
            counts[record["api"]] = counts.get(record["api"], 0) + 1
        instrumentation = [
            {key: value for key, value in record.items() if key != "target_id"}
            for record in self._instrumentation
        ]
        return {
            "authority_origin_marked": self._authority_origin,
            "bootstrap_reset_labels": list(self._reset_labels),
            "post_origin_call_count": len(post_origin),
            "post_origin_api_counts": counts,
            "events": [dict(record) for record in self._events],
            "instrumentation": instrumentation,
            "valid": bool(self._authority_origin and not post_origin),
        }


def trace_sample_spec(
    local_step: int,
    *,
    pre_roll_steps: int,
    hold_steps: int,
) -> dict[str, Any]:
    if type(pre_roll_steps) is not int or pre_roll_steps <= 0:
        raise ValueError("robot_present_sample_pre_roll_steps_invalid")
    if type(hold_steps) is not int or hold_steps <= 0:
        raise ValueError("robot_present_sample_hold_steps_invalid")
    if type(local_step) is not int or not 0 <= local_step <= pre_roll_steps + hold_steps:
        raise ValueError("robot_present_sample_local_step_invalid")
    if local_step == 0:
        phase = "baseline"
        phase_step = 0
        reference = 0
    elif local_step <= pre_roll_steps:
        phase = "pre_roll"
        phase_step = local_step
        reference = 0
    else:
        phase = "hold"
        phase_step = local_step - pre_roll_steps
        reference = pre_roll_steps
    return {
        "local_step": local_step,
        "phase": phase,
        "phase_step": phase_step,
        "motion_reference_local_step": reference,
    }


def validate_live_state_contract(
    *,
    articulation_valid: bool,
    dof_names: Sequence[str],
    joint_positions: Any,
    robot_position_world_m: Any,
    expected_robot_position_world_m: Any,
    robot_orientation_wxyz: Any,
    task_robot_matches: bool,
    task_source_path: str,
    expected_source_path: str,
    task_frame_index: int,
    finger_body_paths: Sequence[str],
    bound_finger_colliders: Mapping[str, Sequence[str]],
    contact_material_path: str,
) -> dict[str, Any]:
    names = tuple(str(name) for name in dof_names)
    positions = np.asarray(joint_positions, dtype=np.float64)
    robot_position = np.asarray(robot_position_world_m, dtype=np.float64)
    expected_robot_position = np.asarray(
        expected_robot_position_world_m, dtype=np.float64
    )
    robot_orientation = np.asarray(robot_orientation_wxyz, dtype=np.float64)
    fingers = tuple(str(path) for path in finger_body_paths)
    try:
        bound = {
            str(path): [str(collider) for collider in colliders]
            for path, colliders in bound_finger_colliders.items()
        }
    except (AttributeError, TypeError) as exc:
        raise ValueError("robot_present_live_state_invalid") from exc
    valid = bool(
        type(articulation_valid) is bool
        and articulation_valid
        and names == EXPECTED_FRANKA_DOF_NAMES
        and positions.shape == (len(EXPECTED_FRANKA_DOF_NAMES),)
        and np.isfinite(positions).all()
        and robot_position.shape == (3,)
        and expected_robot_position.shape == (3,)
        and np.isfinite(robot_position).all()
        and np.isfinite(expected_robot_position).all()
        and np.allclose(
            robot_position,
            expected_robot_position,
            rtol=0.0,
            atol=1.0e-6,
        )
        and robot_orientation.shape == (4,)
        and np.isfinite(robot_orientation).all()
        and math.isclose(
            float(np.linalg.norm(robot_orientation)),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-5,
        )
        and type(task_robot_matches) is bool
        and task_robot_matches
        and task_source_path == expected_source_path == "/World/beaker2"
        and type(task_frame_index) is int
        and task_frame_index == 4
        and len(fingers) == 2
        and len(set(fingers)) == 2
        and set(bound) == set(fingers)
        and all(
            colliders
            and len(colliders) == len(set(colliders))
            and all(path.startswith(finger + "/") for path in colliders)
            for finger, colliders in bound.items()
        )
        and isinstance(contact_material_path, str)
        and contact_material_path == "/World/PhysicsMaterials/ContactGrasp"
    )
    if not valid:
        raise ValueError("robot_present_live_state_invalid")
    return {
        "articulation_valid": True,
        "dof_count": len(names),
        "dof_names": list(names),
        "joint_positions": positions.tolist(),
        "robot_position_world_m": robot_position.tolist(),
        "expected_robot_position_world_m": expected_robot_position.tolist(),
        "robot_orientation_wxyz": robot_orientation.tolist(),
        "task_robot_identity": True,
        "source_path": task_source_path,
        "task_frame_index": task_frame_index,
        "finger_body_paths": list(fingers),
        "finger_collider_paths": bound,
        "finger_collider_count": sum(len(paths) for paths in bound.values()),
        "contact_material_path": contact_material_path,
        "valid": True,
    }


def _source_pose_sha256(matrix: Any) -> str:
    values = np.asarray(matrix, dtype=np.float64)
    if values.shape != (4, 4) or not np.isfinite(values).all():
        raise ValueError("robot_present_source_matrix_invalid")
    return hashlib.sha256(
        np.ascontiguousarray(values, dtype="<f8").tobytes(order="C")
    ).hexdigest()


def _finite_vector(value: Any, shape: tuple[int, ...], *, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(name)
    return result


def _normalized_direction_at_matrix(local_direction: Any, matrix: Any) -> np.ndarray:
    direction = _finite_vector(
        local_direction,
        (3,),
        name="robot_present_source_frame_contract_invalid",
    )
    world = np.append(direction, 0.0) @ np.asarray(matrix, dtype=np.float64)
    norm = float(np.linalg.norm(world[:3]))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("robot_present_source_frame_contract_invalid")
    return np.ascontiguousarray(world[:3] / norm, dtype=np.float64)


def _validate_source_frame_contract(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, Mapping):
        raise ValueError("robot_present_source_frame_contract_invalid")
    origin = _finite_vector(
        contract.get("origin_parent_local_m"),
        (3,),
        name="robot_present_source_frame_contract_invalid",
    )
    axes = _finite_vector(
        contract.get("axes_parent_local"),
        (3, 3),
        name="robot_present_source_frame_contract_invalid",
    )
    norms = np.linalg.norm(axes, axis=1)
    if (
        not np.allclose(norms, 1.0, rtol=0.0, atol=1.0e-8)
        or not np.allclose(axes @ axes.T, np.eye(3), rtol=0.0, atol=1.0e-8)
    ):
        raise ValueError("robot_present_source_frame_contract_invalid")
    scalars: dict[str, float] = {}
    for name in (
        "interior_radius_m",
        "interior_floor_m",
        "rim_height_m",
        "epsilon_m",
    ):
        value = contract.get(name)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, np.number))
            or not math.isfinite(float(value))
        ):
            raise ValueError("robot_present_source_frame_contract_invalid")
        scalars[name] = float(value)
    if (
        scalars["interior_radius_m"] <= 0.0
        or scalars["epsilon_m"] < 0.0
        or scalars["rim_height_m"] <= scalars["interior_floor_m"]
    ):
        raise ValueError("robot_present_source_frame_contract_invalid")
    payload = {
        "origin_parent_local_m": origin.tolist(),
        "axes_parent_local": axes.tolist(),
        **scalars,
    }
    supplied_hash = contract.get("sha256")
    expected_hash = passive._canonical_json_sha256(payload)
    if supplied_hash is not None and supplied_hash != expected_hash:
        raise ValueError("robot_present_source_frame_contract_invalid")
    return {**payload, "sha256": expected_hash, "valid": True}


def build_source_frame_contract(frame: Any, parent_world_matrix: Any) -> dict[str, Any]:
    matrix = _finite_vector(
        parent_world_matrix,
        (4, 4),
        name="robot_present_source_frame_contract_invalid",
    )
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError as exc:
        raise ValueError("robot_present_source_frame_contract_invalid") from exc
    origin_world = _finite_vector(
        frame.origin_world,
        (3,),
        name="robot_present_source_frame_contract_invalid",
    )
    origin_local = (np.append(origin_world, 1.0) @ inverse)[:3]
    local_axes = []
    for attribute in ("x_axis_world", "y_axis_world", "z_axis_world"):
        world_axis = _finite_vector(
            getattr(frame, attribute),
            (3,),
            name="robot_present_source_frame_contract_invalid",
        )
        local_axis = (np.append(world_axis, 0.0) @ inverse)[:3]
        local_axis /= np.linalg.norm(local_axis)
        local_axes.append(local_axis)
    return _validate_source_frame_contract(
        {
            "origin_parent_local_m": origin_local,
            "axes_parent_local": local_axes,
            "interior_radius_m": float(frame.interior_radius),
            "interior_floor_m": float(frame.interior_floor),
            "rim_height_m": float(frame.rim_height),
            "epsilon_m": 0.00005,
        }
    )


def _source_frame_at_matrix(
    contract: Mapping[str, Any], matrix: Any
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(matrix, dtype=np.float64)
    origin = (
        np.append(contract["origin_parent_local_m"], 1.0) @ values
    )[:3]
    axes = np.asarray(
        [
            _normalized_direction_at_matrix(direction, values)
            for direction in contract["axes_parent_local"]
        ],
        dtype=np.float64,
    )
    return np.ascontiguousarray(origin), np.ascontiguousarray(axes)


def _source_containment_count(
    positions_world_m: Any,
    *,
    source_world_matrix: Any,
    source_frame_contract: Mapping[str, Any],
) -> int:
    positions = np.asarray(positions_world_m, dtype=np.float64)
    origin, axes = _source_frame_at_matrix(
        source_frame_contract, source_world_matrix
    )
    canonical = (positions - origin) @ axes.T
    radius = np.hypot(canonical[:, 0], canonical[:, 1])
    epsilon = float(source_frame_contract["epsilon_m"])
    inside = (
        (radius <= float(source_frame_contract["interior_radius_m"]) + epsilon)
        & (
            canonical[:, 2]
            >= float(source_frame_contract["interior_floor_m"]) - epsilon
        )
        & (
            canonical[:, 2]
            < float(source_frame_contract["rim_height_m"]) - epsilon
        )
    )
    return int(np.count_nonzero(inside))


def summarize_startup_motion_checkpoints(
    *,
    authored_source_world_matrix: Any,
    authored_source_center_world_m: Any,
    checkpoints: Sequence[Mapping[str, Any]],
    vessel_axis_object: Any,
    translation_limit_m: float,
    tilt_limit_degrees: float,
) -> dict[str, Any]:
    from utils.isaac_fluid_evaluation import evaluate_preclose_source_motion

    authored_matrix = np.asarray(authored_source_world_matrix, dtype=np.float64)
    authored_center = np.asarray(authored_source_center_world_m, dtype=np.float64)
    if (
        authored_matrix.shape != (4, 4)
        or authored_center.shape != (3,)
        or not np.isfinite(authored_matrix).all()
        or not np.isfinite(authored_center).all()
        or isinstance(checkpoints, (str, bytes))
        or not checkpoints
    ):
        raise ValueError("robot_present_startup_authority_invalid")
    try:
        geometry_center_parent_local = (
            np.append(authored_center, 1.0) @ np.linalg.inv(authored_matrix)
        )
    except np.linalg.LinAlgError as exc:
        raise ValueError("robot_present_startup_authority_invalid") from exc
    if (
        not np.isfinite(geometry_center_parent_local).all()
        or not math.isclose(
            float(geometry_center_parent_local[3]),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-10,
        )
    ):
        raise ValueError("robot_present_startup_authority_invalid")
    records = []
    seen_names: set[str] = set()
    maximum_translation = 0.0
    maximum_tilt = 0.0
    first_failure = None
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, Mapping):
            raise ValueError("robot_present_startup_checkpoint_invalid")
        name = checkpoint.get("name")
        matrix = np.asarray(checkpoint.get("source_world_matrix"), dtype=np.float64)
        center = np.asarray(checkpoint.get("source_center_world_m"), dtype=np.float64)
        if (
            not isinstance(name, str)
            or not name
            or name in seen_names
            or matrix.shape != (4, 4)
            or center.shape != (3,)
            or not np.isfinite(matrix).all()
            or not np.isfinite(center).all()
        ):
            raise ValueError("robot_present_startup_checkpoint_invalid")
        seen_names.add(name)
        derived_center = np.asarray(
            (geometry_center_parent_local @ matrix)[:3], dtype=np.float64
        )
        if not np.allclose(center, derived_center, rtol=0.0, atol=1.0e-12):
            raise ValueError("robot_present_startup_checkpoint_center_invalid")
        motion = evaluate_preclose_source_motion(
            reference_center_world_m=authored_center,
            reference_source_world_matrix=authored_matrix,
            current_center_world_m=derived_center,
            current_source_world_matrix=matrix,
            vessel_axis_object=vessel_axis_object,
            translation_limit_m=translation_limit_m,
            tilt_limit_degrees=tilt_limit_degrees,
        )
        maximum_translation = max(maximum_translation, motion["translation_m"])
        maximum_tilt = max(maximum_tilt, motion["tilt_degrees"])
        if not motion["passed"] and first_failure is None:
            first_failure = name
        records.append(
            {
                "name": name,
                "source_world_matrix": matrix.tolist(),
                "source_center_world_m": derived_center.tolist(),
                "source_pose_sha256": _source_pose_sha256(matrix),
                "translation_m": motion["translation_m"],
                "tilt_degrees": motion["tilt_degrees"],
                "translation_valid": motion["translation_valid"],
                "tilt_valid": motion["tilt_valid"],
                "passed": motion["passed"],
            }
        )
    return {
        "valid": True,
        "passed": first_failure is None,
        "reference": {
            "name": "authored_pre_world",
            "source_world_matrix": authored_matrix.tolist(),
            "source_center_world_m": authored_center.tolist(),
            "source_pose_sha256": _source_pose_sha256(authored_matrix),
        },
        "geometry_center_parent_local_m": geometry_center_parent_local[:3].tolist(),
        "checkpoint_count": len(records),
        "checkpoints": records,
        "maximum_translation_m": maximum_translation,
        "maximum_tilt_degrees": maximum_tilt,
        "first_failure_checkpoint": first_failure,
        "sampling_scope": "net_authored_to_checkpoint_motion",
        "unsampled_internal_reset_transients_claimed_absent": False,
    }


def _required_array(
    arrays: Mapping[str, Any],
    name: str,
    shape: tuple[int, ...],
    *,
    dtype: np.dtype[Any] | None = None,
    finite: bool = False,
) -> np.ndarray:
    if name not in arrays:
        raise ValueError(f"robot_present_trace_array_missing:{name}")
    value = np.asarray(arrays[name])
    if value.shape != shape or (dtype is not None and value.dtype != dtype):
        raise ValueError(f"robot_present_trace_array_invalid:{name}")
    if finite and not np.isfinite(value).all():
        raise ValueError(f"robot_present_trace_array_nonfinite:{name}")
    return value


def validate_trace_array_contract(
    source_arrays: Mapping[str, Any],
    particle_arrays: Mapping[str, Any],
    *,
    physics_dt: float,
    pre_roll_steps: int,
    hold_steps: int,
    expected_particle_count: int,
    trace_authority: Mapping[str, Any],
) -> dict[str, Any]:
    from utils.isaac_fluid_evaluation import evaluate_preclose_source_motion
    from utils.online_fluid_surface import canonical_position_sha256

    if not isinstance(trace_authority, Mapping):
        raise ValueError("robot_present_trace_authority_invalid")
    geometry_center_local = _finite_vector(
        trace_authority.get("geometry_center_parent_local_m"),
        (3,),
        name="robot_present_trace_authority_invalid",
    )
    vessel_axis_object = _finite_vector(
        trace_authority.get("vessel_axis_object"),
        (3,),
        name="robot_present_trace_authority_invalid",
    )
    translation_limit = trace_authority.get("translation_limit_m")
    tilt_limit = trace_authority.get("tilt_limit_degrees")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
        for value in (translation_limit, tilt_limit)
    ):
        raise ValueError("robot_present_trace_authority_invalid")
    source_frame_contract = _validate_source_frame_contract(
        trace_authority.get("source_frame_contract")
    )

    expected_records = 1 + pre_roll_steps + hold_steps
    matrices = _required_array(
        source_arrays,
        "source_world_matrix_m",
        (expected_records, 4, 4),
        dtype=np.dtype(np.float64),
        finite=True,
    )
    centers = _required_array(
        source_arrays,
        "source_geometry_center_world_m",
        (expected_records, 3),
        dtype=np.dtype(np.float64),
        finite=True,
    )
    axes = _required_array(
        source_arrays,
        "source_axis_world",
        (expected_records, 3),
        dtype=np.dtype(np.float64),
        finite=True,
    )
    for name in ("linear_velocity_m_s", "angular_velocity_rad_s"):
        _required_array(
            source_arrays,
            name,
            (expected_records, 3),
            dtype=np.dtype(np.float64),
            finite=True,
        )
    world_times = _required_array(
        source_arrays,
        "world_time_s",
        (expected_records,),
        dtype=np.dtype(np.float64),
        finite=True,
    )
    translations = _required_array(
        source_arrays,
        "translation_m",
        (expected_records,),
        dtype=np.dtype(np.float64),
        finite=True,
    )
    tilts = _required_array(
        source_arrays,
        "tilt_degrees",
        (expected_records,),
        dtype=np.dtype(np.float64),
        finite=True,
    )
    positions = _required_array(
        particle_arrays,
        "positions_world_m",
        (expected_records, expected_particle_count, 3),
        dtype=np.dtype(np.float64),
        finite=True,
    )
    one_dimensional_names = (
        "local_step",
        "phase",
        "phase_step",
        "motion_reference_local_step",
        "world_step",
        "translation_valid",
        "tilt_valid",
        "source_pose_sha256",
    )
    for name in one_dimensional_names:
        _required_array(source_arrays, name, (expected_records,))
    for name in (
        "position_sha256",
        "particle_count",
        "partition_complete",
        "source_frame_pose_sha256",
        *PARTITION_NAMES,
    ):
        _required_array(particle_arrays, name, (expected_records,))

    records: list[dict[str, Any]] = []
    for index in range(expected_records):
        spec = trace_sample_spec(
            index,
            pre_roll_steps=pre_roll_steps,
            hold_steps=hold_steps,
        )
        source_hash = str(source_arrays["source_pose_sha256"][index])
        frame_hash = str(particle_arrays["source_frame_pose_sha256"][index])
        if source_hash != _source_pose_sha256(matrices[index]):
            raise ValueError("robot_present_source_pose_hash_invalid")
        if source_hash != frame_hash:
            raise ValueError("robot_present_source_frame_hash_invalid")
        if str(particle_arrays["position_sha256"][index]) != canonical_position_sha256(
            positions[index]
        ):
            raise ValueError("robot_present_particle_position_hash_invalid")
        expected_center = (
            np.append(geometry_center_local, 1.0) @ matrices[index]
        )[:3]
        if not np.allclose(
            centers[index], expected_center, rtol=0.0, atol=1.0e-12
        ):
            raise ValueError("robot_present_source_geometry_center_invalid")
        reference_index = spec["motion_reference_local_step"]
        reference_center = (
            np.append(geometry_center_local, 1.0) @ matrices[reference_index]
        )[:3]
        motion = evaluate_preclose_source_motion(
            reference_center_world_m=reference_center,
            reference_source_world_matrix=matrices[reference_index],
            current_center_world_m=expected_center,
            current_source_world_matrix=matrices[index],
            vessel_axis_object=vessel_axis_object,
            translation_limit_m=float(translation_limit),
            tilt_limit_degrees=float(tilt_limit),
        )
        if (
            not math.isclose(
                float(translations[index]),
                motion["translation_m"],
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            or not math.isclose(
                float(tilts[index]),
                motion["tilt_degrees"],
                rel_tol=0.0,
                abs_tol=1.0e-10,
            )
            or bool(source_arrays["translation_valid"][index])
            is not motion["translation_valid"]
            or bool(source_arrays["tilt_valid"][index]) is not motion["tilt_valid"]
            or not np.allclose(
                axes[index],
                np.asarray(motion["current_axis_world"], dtype=np.float64),
                rtol=0.0,
                atol=1.0e-12,
            )
        ):
            raise ValueError("robot_present_source_motion_metrics_invalid")
        source_count = _source_containment_count(
            positions[index],
            source_world_matrix=matrices[index],
            source_frame_contract=source_frame_contract,
        )
        if int(particle_arrays["source"][index]) != source_count:
            raise ValueError("robot_present_source_containment_count_invalid")
        if int(source_arrays["motion_reference_local_step"][index]) != spec[
            "motion_reference_local_step"
        ]:
            raise ValueError("robot_present_motion_reference_invalid")
        record = {
            **spec,
            "world_step": int(source_arrays["world_step"][index]),
            "world_time_s": float(world_times[index]),
            "translation_m": motion["translation_m"],
            "tilt_degrees": motion["tilt_degrees"],
            "translation_valid": motion["translation_valid"],
            "tilt_valid": motion["tilt_valid"],
            "source_pose_sha256": source_hash,
            "source_frame_pose_sha256": frame_hash,
            "position_sha256": str(particle_arrays["position_sha256"][index]),
            "particle_count": int(particle_arrays["particle_count"][index]),
            "partition_complete": bool(
                particle_arrays["partition_complete"][index]
            ),
        }
        record.update(
            {
                name: int(particle_arrays[name][index])
                for name in PARTITION_NAMES
            }
        )
        if (
            int(source_arrays["local_step"][index]) != index
            or str(source_arrays["phase"][index]) != spec["phase"]
            or int(source_arrays["phase_step"][index]) != spec["phase_step"]
        ):
            raise ValueError("robot_present_trace_order_invalid")
        records.append(record)
    schedule = passive.validate_trace_schedule(
        records,
        physics_dt=physics_dt,
        pre_roll_steps=pre_roll_steps,
        hold_steps=hold_steps,
    )
    filled = passive.summarize_filled_trace(
        records,
        expected_particle_count=expected_particle_count,
    )
    return {
        "valid": True,
        "record_count": expected_records,
        "source_trace_shape": list(matrices.shape),
        "particle_trace_shape": list(positions.shape),
        "source_trace_dtype": matrices.dtype.str,
        "particle_trace_dtype": positions.dtype.str,
        "source_pose_hashes_valid": True,
        "position_hashes_valid": True,
        "source_frame_hashes_valid": True,
        "motion_metrics_recomputed": True,
        "source_containment_recomputed": True,
        "distinct_particle_position_hash_count": len(
            set(str(value) for value in particle_arrays["position_sha256"])
        ),
        "baseline_source_pose_sha256": str(
            source_arrays["source_pose_sha256"][0]
        ),
        "terminal_source_pose_sha256": str(
            source_arrays["source_pose_sha256"][-1]
        ),
        "baseline_particle_position_sha256": str(
            particle_arrays["position_sha256"][0]
        ),
        "schedule": schedule,
        "motion_summary": passive.summarize_motion_trace(records),
        "filled_summary": filled,
    }


def containment_summary_from_filled(
    filled_summary: Mapping[str, Any],
) -> dict[str, Any]:
    result = {
        key: value
        for key, value in filled_summary.items()
        if key
        not in {
            "motion_passed",
            "maximum_translation_m",
            "maximum_tilt_degrees",
            "first_translation_failure_local_step",
            "first_tilt_failure_local_step",
        }
    }
    result["passed"] = bool(filled_summary["containment_passed"])
    return result


def motion_summaries_match(left: Any, right: Any) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    numeric_names = {"maximum_translation_m", "maximum_tilt_degrees"}
    if set(left) != set(right):
        return False
    for name in left:
        if name in numeric_names:
            try:
                if not math.isclose(
                    float(left[name]),
                    float(right[name]),
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                ):
                    return False
            except (TypeError, ValueError):
                return False
        elif left[name] != right[name]:
            return False
    return True


def finalize_child_report(
    provisional_report: Mapping[str, Any],
    *,
    expected_run_nonce: str,
    expected_config_sha256: str,
    child_command: Sequence[str],
    child_returncode: int,
    timed_out: bool,
    termination: str | None,
) -> dict[str, Any]:
    if (
        provisional_report.get("manifest_type") != MANIFEST_TYPE
        or provisional_report.get("run_nonce") != expected_run_nonce
        or provisional_report.get("config_sha256") != expected_config_sha256
    ):
        raise ValueError("robot_present_provisional_identity_invalid")
    if type(child_returncode) is not int or type(timed_out) is not bool:
        raise ValueError("robot_present_child_status_invalid")
    final = json.loads(passive._canonical_json_bytes(provisional_report).decode("utf-8"))
    measurement_decision = str(
        final.get("measurement_decision", "PROBE_RUNTIME_ERROR")
    )
    clean = bool(
        not timed_out
        and child_returncode == 0
        and final.get("lifecycle_status")
        == "measurement_complete_pending_application_close"
        and measurement_decision
        in {
            "ROBOT_PRESENT_ZERO_ACTION_PASS",
            "ROBOT_PRESENT_ZERO_ACTION_FAIL",
        }
    )
    final["pre_shutdown_decision"] = measurement_decision
    final["finalized_at_utc"] = datetime.now(timezone.utc).isoformat()
    final["child_process"] = {
        "command": [str(value) for value in child_command],
        "returncode": child_returncode,
        "timed_out": timed_out,
        "termination": termination,
    }
    if clean:
        final["decision"] = measurement_decision
        final["lifecycle_status"] = "completed"
        final["shutdown_status"] = "child_exit_0"
    else:
        final["decision"] = "PROBE_RUNTIME_ERROR"
        final["lifecycle_status"] = "failed"
        final["shutdown_status"] = (
            "child_timeout"
            if timed_out
            else "child_exit_nonzero"
            if child_returncode != 0
            else "measurement_runtime_error"
        )
    return final


def _stage_source_world_matrix(stage: Any, source_path: str) -> np.ndarray:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(source_path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"robot_present_source_missing:{source_path}")
    values = np.asarray(
        UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()),
        dtype=np.float64,
    )
    if values.shape != (4, 4) or not np.isfinite(values).all():
        raise RuntimeError("robot_present_source_world_matrix_invalid")
    return values


def _checkpoint(
    *,
    name: str,
    source_world_matrix: Any,
    geometry_center_local: np.ndarray,
) -> dict[str, Any]:
    matrix = np.asarray(source_world_matrix, dtype=np.float64)
    center = np.asarray(geometry_center_local @ matrix, dtype=np.float64)[:3]
    return {
        "name": name,
        "source_world_matrix": matrix,
        "source_center_world_m": center,
    }


def _jsonable_usd_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.number)):
        number = float(value)
        return number if math.isfinite(number) else str(number)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_jsonable_usd_value(item) for item in value]
    try:
        return [_jsonable_usd_value(item) for item in value]
    except TypeError:
        return str(value)


def _authored_drive_snapshot(stage: Any, robot_path: str) -> dict[str, Any]:
    from pxr import Usd

    root = stage.GetPrimAtPath(robot_path)
    if not root or not root.IsValid():
        raise RuntimeError(f"robot_present_robot_prim_missing:{robot_path}")
    drives = []
    for prim in Usd.PrimRange(root):
        schemas = [
            str(schema)
            for schema in prim.GetAppliedSchemas()
            if str(schema).startswith("PhysicsDriveAPI:")
        ]
        for schema in schemas:
            instance = schema.split(":", 1)[1]
            prefix = f"drive:{instance}:"
            attributes = {
                str(attribute.GetName())[len(prefix) :]: _jsonable_usd_value(
                    attribute.Get()
                )
                for attribute in prim.GetAttributes()
                if str(attribute.GetName()).startswith(prefix)
            }
            stiffness = attributes.get("physics:stiffness", 0.0)
            damping = attributes.get("physics:damping", 0.0)
            active = any(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and float(value) > 0.0
                for value in (stiffness, damping)
            )
            drives.append(
                {
                    "joint_name": str(prim.GetName()),
                    "prim_path": str(prim.GetPath()),
                    "drive_instance": instance,
                    "attributes": attributes,
                    "active": active,
                }
            )
    drives.sort(key=lambda record: (record["joint_name"], record["drive_instance"]))
    joint_names = tuple(record["joint_name"] for record in drives)
    active_drive_count = sum(record["active"] for record in drives)
    if (
        len(drives) != len(EXPECTED_FRANKA_DOF_NAMES)
        or set(joint_names) != set(EXPECTED_FRANKA_DOF_NAMES)
        or len(set(joint_names)) != len(joint_names)
        or active_drive_count != 8
    ):
        raise RuntimeError(
            "robot_present_authored_drive_contract_invalid:"
            f"actual={joint_names}"
        )
    payload = {
        "robot_path": robot_path,
        "drive_count": len(drives),
        "joint_names": list(joint_names),
        "active_drive_count": active_drive_count,
        "drives": drives,
    }
    return {
        **payload,
        "sha256": passive._canonical_json_sha256(payload),
        "valid": True,
    }


def _articulation_validity(robot: Any) -> tuple[bool, str]:
    view = getattr(robot, "_articulation_view", None)
    for owner, authority in (
        (robot, "robot.is_physics_handle_valid"),
        (view, "articulation_view.is_physics_handle_valid"),
    ):
        method = getattr(owner, "is_physics_handle_valid", None)
        if callable(method):
            return bool(method()), authority
    return bool(view is not None and getattr(view, "_physics_view", None) is not None), (
        "articulation_view._physics_view"
    )


def _live_state(
    *,
    robot: Any,
    task: Any,
    fluid: Any,
    contact_scene: Mapping[str, Any],
    expected_robot_position_world_m: Any,
) -> dict[str, Any]:
    articulation_valid, authority = _articulation_validity(robot)
    robot_position, robot_orientation = robot.get_world_pose()
    result = validate_live_state_contract(
        articulation_valid=articulation_valid,
        dof_names=tuple(str(name) for name in robot.dof_names),
        joint_positions=robot.get_joint_positions(),
        robot_position_world_m=robot_position,
        expected_robot_position_world_m=expected_robot_position_world_m,
        robot_orientation_wxyz=robot_orientation,
        task_robot_matches=task.robot is robot,
        task_source_path=str(getattr(task, "current_obj_path", "")),
        expected_source_path=str(_config_value(fluid, "source_actor_path")),
        task_frame_index=getattr(task, "frame_idx", None),
        finger_body_paths=tuple(_config_value(fluid, "finger_body_paths")),
        bound_finger_colliders=contact_scene["finger_collider_paths"],
        contact_material_path=str(contact_scene["material_path"]),
    )
    result["articulation_validity_authority"] = authority
    return result


def _validate_contact_material_bindings(
    stage: Any,
    contact_scene: Mapping[str, Any],
) -> dict[str, Any]:
    from pxr import UsdShade

    material_path = str(contact_scene["material_path"])
    bindings: dict[str, str] = {}
    for collider_paths in contact_scene["finger_collider_paths"].values():
        for collider_path in collider_paths:
            prim = stage.GetPrimAtPath(str(collider_path))
            material, relationship = UsdShade.MaterialBindingAPI(
                prim
            ).ComputeBoundMaterial("physics")
            bound_path = str(material.GetPath()) if material else ""
            if not relationship or bound_path != material_path:
                raise RuntimeError(
                    f"robot_present_contact_material_binding_invalid:{collider_path}"
                )
            bindings[str(collider_path)] = bound_path
    if not bindings:
        raise RuntimeError("robot_present_contact_material_bindings_missing")
    return {
        **dict(contact_scene),
        "validated_material_bindings": bindings,
        "validated_material_binding_count": len(bindings),
        "valid": True,
    }


def _effective_particle_readback_settings(
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    import carb

    settings = carb.settings.get_settings()
    actual = {str(path): settings.get(str(path)) for path in expected}
    return validate_effective_particle_readback_settings(expected, actual)


def _camera_object_record(
    camera: Any,
    *,
    role: str,
    prim_path: str,
    name: str,
    frequency: int,
    resolution: Sequence[int],
) -> dict[str, Any]:
    render_product = None
    getter = getattr(camera, "get_render_product_path", None)
    if callable(getter):
        try:
            value = getter()
        except RuntimeError:
            value = None
        if value:
            render_product = str(value)
    for attribute_name in ("_render_product_path", "render_product_path"):
        if render_product is not None:
            break
        value = getattr(camera, attribute_name, None)
        if value:
            render_product = str(value)
            break
    return {
        "role": role,
        "object_type": type(camera).__name__,
        "name": name,
        "prim_path": prim_path,
        "frequency_hz": int(frequency),
        "resolution": [int(value) for value in resolution],
        "object_constructed": True,
        "render_product_path": render_product,
        "render_product_constructed": render_product is not None,
        "diagnostic_camera": False,
        "image_captured_by_probe": False,
    }


def _camera_disclosure(stage: Any, cfg: Any, robot: Any, task: Any) -> dict[str, Any]:
    from pxr import Usd, UsdGeom

    task_configs = tuple(_config_value(cfg, "cameras"))
    task_cameras = tuple(task.cameras)
    if len(task_configs) != 2 or len(task_cameras) != len(task_configs):
        raise RuntimeError("robot_present_task_camera_contract_invalid")
    records = []
    for camera, config in zip(task_cameras, task_configs):
        records.append(
            _camera_object_record(
                camera,
                role="task_model_camera",
                prim_path=str(_config_value(config, "prim_path")),
                name=str(_config_value(config, "name")),
                frequency=int(_config_value(config, "frequency")),
                resolution=_config_value(config, "resolution"),
            )
        )
    if not all(record["render_product_constructed"] for record in records):
        raise RuntimeError("robot_present_task_render_product_missing")
    robot_camera = getattr(robot, "camera", None)
    if robot_camera is None:
        raise RuntimeError("robot_present_franka_camera_missing")
    records.append(
        _camera_object_record(
            robot_camera,
            role="franka_arm_camera",
            prim_path="/World/Franka/panda_hand/arm_camera",
            name=str(getattr(robot_camera, "name", "franka_arm_camera")),
            frequency=int(_config_value(_config_value(cfg, "robot"), "camera_frequency")),
            resolution=(256, 256),
        )
    )
    stage_paths = sorted(
        str(prim.GetPath())
        for prim in Usd.PrimRange.Stage(stage)
        if prim.IsA(UsdGeom.Camera)
    )
    object_paths = {record["prim_path"] for record in records}
    if not object_paths.issubset(set(stage_paths)):
        raise RuntimeError("robot_present_camera_prim_missing")
    return {
        "camera_object_count": len(records),
        "camera_objects": records,
        "stage_camera_prim_paths": stage_paths,
        "render_product_paths": [
            record["render_product_path"]
            for record in records
            if record["render_product_path"] is not None
        ],
        "additional_diagnostic_camera_count": 0,
        "probe_image_read_count": 0,
        "production_render_product_frame_generation_claimed_absent": False,
        "valid": True,
    }


def _install_post_origin_instrumentation(
    *,
    ledger: ZeroActionLedger,
    world: Any,
    task: Any,
    robot: Any,
    source_body: Any,
    object_utils: Any,
) -> None:
    ledger.instrument(task, "step", "task.step", required=True)
    ledger.instrument(task, "reset", "task.reset", required=True)
    for method_name in (
        "apply_action",
        "set_joint_positions",
        "set_joint_velocities",
        "set_joint_efforts",
        "set_joint_position_targets",
        "set_joint_velocity_targets",
        "set_joint_effort_targets",
        "set_world_pose",
        "set_local_pose",
        "initialize",
        "post_reset",
    ):
        ledger.instrument(
            robot,
            method_name,
            f"robot.{method_name}",
            required=method_name
            in {
                "apply_action",
                "set_joint_positions",
                "set_joint_velocities",
                "set_joint_efforts",
            },
        )
    articulation_controller = robot.get_articulation_controller()
    ledger.instrument(
        articulation_controller,
        "apply_action",
        "articulation_controller.apply_action",
        required=True,
    )
    for method_name in (
        "set_gains",
        "switch_dof_control_mode",
        "set_effort_modes",
    ):
        ledger.instrument(
            articulation_controller,
            method_name,
            f"articulation_controller.{method_name}",
            required=False,
        )
    articulation_view = getattr(robot, "_articulation_view", None)
    if articulation_view is None:
        raise RuntimeError("zero_action_articulation_view_missing")
    for method_name in (
        "apply_action",
        "set_joint_position_targets",
        "set_joint_velocity_targets",
        "set_joint_positions",
        "set_joint_velocities",
        "set_joint_efforts",
        "set_gains",
        "switch_control_mode",
        "switch_dof_control_mode",
        "set_effort_modes",
        "set_world_poses",
        "set_local_poses",
    ):
        ledger.instrument(
            articulation_view,
            method_name,
            f"articulation_view.{method_name}",
            required=method_name
            in {
                "apply_action",
                "set_joint_position_targets",
                "set_joint_velocity_targets",
                "set_joint_positions",
                "set_joint_velocities",
                "set_joint_efforts",
            },
        )
    gripper = robot.gripper
    for method_name in (
        "open",
        "close",
        "forward",
        "apply_action",
        "set_joint_positions",
        "set_default_state",
        "post_reset",
    ):
        ledger.instrument(
            gripper,
            method_name,
            f"gripper.{method_name}",
            required=method_name == "set_joint_positions",
        )
    for method_name in (
        "set_world_pose",
        "set_local_pose",
        "set_linear_velocity",
        "set_angular_velocity",
        "set_default_state",
    ):
        ledger.instrument(
            source_body,
            method_name,
            f"source_body.{method_name}",
            required=method_name in {"set_world_pose", "set_linear_velocity"},
        )
    ledger.instrument(
        object_utils,
        "set_object_position",
        "object_utils.set_object_position",
        required=True,
    )
    ledger.instrument(world, "render", "world.render", required=True)
    ledger.instrument(task, "get_camera_data", "task.get_camera_data", required=True)
    cameras = [*task.cameras, robot.camera]
    for index, camera in enumerate(cameras):
        for method_name in ("get_rgb", "get_rgba", "get_current_frame"):
            ledger.instrument(
                camera,
                method_name,
                f"camera[{index}].{method_name}",
                required=False,
            )


def _runtime_error_report(
    exc: BaseException,
    *,
    run_nonce: str,
    config_sha256: str,
    phase: str,
    ledger: ZeroActionLedger | None = None,
) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "runtime_error_pending_application_close",
        "shutdown_status": "pending",
        "run_nonce": run_nonce,
        "config_sha256": config_sha256,
        "measurement_decision": "PROBE_RUNTIME_ERROR",
        "fatal_error": {
            "phase": phase,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
    }
    if ledger is not None:
        report["zero_action_ledger_at_error"] = ledger.summary()
    return report


def _measure_runtime(args: argparse.Namespace) -> dict[str, Any]:
    from isaacsim_compat import install_legacy_isaacsim_aliases

    install_legacy_isaacsim_aliases()
    import omni.physx
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.utils.stage import add_reference_to_stage, get_stage_units
    from omegaconf import OmegaConf

    from factories.robot_factory import create_robot
    from factories.task_factory import create_task
    from utils.isaac_fluid_evaluation import (
        AuthoredWrapperFrameReader,
        _single_rigid_world_matrix,
        _table_top_z,
        classify_transfer_positions,
        configure_contact_grasp_scene,
        configure_fluid_world_timing,
        configure_particle_usd_readback,
        construct_single_rigid_prim,
        evaluate_preclose_source_motion,
        validate_fluid_stage_contract,
    )
    from utils.object_utils import ObjectUtils
    from utils.online_fluid_surface import (
        canonical_position_sha256,
        read_strict_simulation_points,
    )

    cfg = OmegaConf.load(str(args.config))
    fluid = cfg.online_fluid
    config_sha256 = sha256_file(args.config)
    usd_path = (REPO_ROOT / str(cfg.usd_path)).resolve()
    if not usd_path.is_file():
        raise FileNotFoundError(f"robot_present_candidate_asset_missing:{usd_path}")
    candidate_contract = validate_candidate_contract(
        cfg,
        config_sha256=config_sha256,
        asset_sha256=sha256_file(usd_path),
    )
    dependency_closure = passive.build_usd_dependency_closure(usd_path)
    if (
        dependency_closure.get("sha256")
        != EXPECTED_SCENE_DEPENDENCY_CLOSURE_SHA256
        or dependency_closure.get("unresolved") != []
    ):
        raise RuntimeError("robot_present_scene_dependency_closure_invalid")

    readback_settings_pre_world = configure_particle_usd_readback()
    stage = omni.usd.get_context().get_stage()
    add_reference_to_stage(usd_path=str(usd_path), prim_path="/World")
    source_path = str(fluid.source_actor_path)
    authored_particle_positions = read_strict_simulation_points(
        stage,
        str(fluid.particle_path),
        expected_particle_count=int(fluid.expected_particle_count),
    )
    authored_particle_position_sha256 = canonical_position_sha256(
        authored_particle_positions
    )
    authored_source_world = _stage_source_world_matrix(stage, source_path)
    authored_source_center = passive._source_geometry_center(stage, source_path)
    geometry_center_local = np.append(authored_source_center, 1.0) @ np.linalg.inv(
        authored_source_world
    )
    if not math.isclose(
        float(geometry_center_local[3]),
        1.0,
        rel_tol=0.0,
        abs_tol=1.0e-10,
    ):
        raise RuntimeError("robot_present_source_geometry_center_invalid")
    geometry_center_local = np.ascontiguousarray(
        np.append(
            geometry_center_local[:3] / geometry_center_local[3],
            1.0,
        ),
        dtype=np.float64,
    )

    world = World(
        physics_dt=float(fluid.physics_dt),
        rendering_dt=float(fluid.rendering_dt),
        stage_units_in_meters=1.0,
        physics_prim_path=str(fluid.physics_scene_path),
        set_defaults=False,
        backend="numpy",
        device="cpu",
    )
    omni.physx.get_physx_interface().overwrite_gpu_setting(1)
    readback_settings_post_world = configure_particle_usd_readback()
    if readback_settings_post_world != readback_settings_pre_world:
        raise RuntimeError("robot_present_particle_readback_setting_paths_changed")
    ledger = ZeroActionLedger()
    ledger.instrument(world, "reset", "world.reset", required=True)

    robot_usd_path = (REPO_ROOT / str(cfg.robot.usd_path)).resolve()
    robot_sha256 = sha256_file(robot_usd_path)
    if robot_sha256 != EXPECTED_ROBOT_SHA256:
        raise RuntimeError("robot_present_robot_usd_hash_invalid")
    robot = create_robot(
        str(cfg.robot.type),
        position=np.asarray(cfg.robot.position, dtype=np.float64),
        usd_path=str(robot_usd_path),
        camera_frequency=int(cfg.robot.camera_frequency),
    )
    contact_scene = configure_contact_grasp_scene(stage, fluid)
    object_utils = ObjectUtils.get_instance(stage)

    with ledger.expect_bootstrap_reset("task_constructor_camera_reset"):
        task = create_task(
            str(cfg.task_type),
            cfg=cfg,
            world=world,
            stage=stage,
            robot=robot,
        )
    startup_checkpoints = [
        _checkpoint(
            name="task_constructor_camera_reset",
            source_world_matrix=_stage_source_world_matrix(stage, source_path),
            geometry_center_local=geometry_center_local,
        )
    ]
    with ledger.expect_bootstrap_reset("explicit_task_reset"):
        task.reset()
    startup_checkpoints.append(
        _checkpoint(
            name="explicit_task_reset",
            source_world_matrix=_stage_source_world_matrix(stage, source_path),
            geometry_center_local=geometry_center_local,
        )
    )

    configure_fluid_world_timing(
        world,
        physics_dt=float(fluid.physics_dt),
        rendering_dt=float(fluid.rendering_dt),
    )
    readback_settings_at_origin = _effective_particle_readback_settings(
        readback_settings_post_world
    )
    stage_contract = validate_fluid_stage_contract(stage, fluid)
    contact_scene = _validate_contact_material_bindings(stage, contact_scene)
    source_body = construct_single_rigid_prim(
        SingleRigidPrim,
        prim_path=source_path,
        name="robot_present_zero_action_source_vessel",
    )
    source_body.initialize()
    authority_source_world = _single_rigid_world_matrix(source_body)
    startup_checkpoints.append(
        _checkpoint(
            name="authority_origin",
            source_world_matrix=authority_source_world,
            geometry_center_local=geometry_center_local,
        )
    )
    startup_motion = summarize_startup_motion_checkpoints(
        authored_source_world_matrix=authored_source_world,
        authored_source_center_world_m=authored_source_center,
        checkpoints=startup_checkpoints,
        vessel_axis_object=fluid.grasp_height_axis_object,
        translation_limit_m=float(fluid.grasp_preclose_source_translation_limit_m),
        tilt_limit_degrees=float(fluid.grasp_preclose_source_tilt_limit_degrees),
    )
    origin_live_state = _live_state(
        robot=robot,
        task=task,
        fluid=fluid,
        contact_scene=contact_scene,
        expected_robot_position_world_m=cfg.robot.position,
    )
    camera_disclosure = _camera_disclosure(stage, cfg, robot, task)
    origin_drives = _authored_drive_snapshot(stage, "/World/Franka")

    _install_post_origin_instrumentation(
        ledger=ledger,
        world=world,
        task=task,
        robot=robot,
        source_body=source_body,
        object_utils=object_utils,
    )
    reset_contract = ledger.mark_authority_origin()

    particle_path = str(fluid.particle_path)
    source_visual_path = str(fluid.source_visual_mesh_path)
    expected_particle_count = int(fluid.expected_particle_count)
    physics_dt = float(fluid.physics_dt)
    pre_roll_steps = int(fluid.dynamic_pre_roll_steps)
    hold_steps = int(fluid.filled_static_hold_steps)
    vessel_axis_object = tuple(float(value) for value in fluid.grasp_height_axis_object)
    translation_limit = float(fluid.grasp_preclose_source_translation_limit_m)
    tilt_limit = float(fluid.grasp_preclose_source_tilt_limit_degrees)
    cached_source_world = authority_source_world.copy()
    source_frame = AuthoredWrapperFrameReader(
        stage,
        parent_path=source_path,
        visual_mesh_path=source_visual_path,
        parent_world_matrix=lambda: cached_source_world.copy(),
    )
    target_frame = AuthoredWrapperFrameReader(
        stage,
        parent_path=str(fluid.target_actor_path),
        visual_mesh_path=str(fluid.target_visual_mesh_path),
    )
    source_frame_contract = build_source_frame_contract(
        source_frame(), authority_source_world
    )
    trace_authority = {
        "geometry_center_parent_local_m": geometry_center_local[:3].tolist(),
        "vessel_axis_object": list(vessel_axis_object),
        "translation_limit_m": translation_limit,
        "tilt_limit_degrees": tilt_limit,
        "source_frame_contract": source_frame_contract,
    }
    table_z = _table_top_z(stage, str(fluid.table_path))

    records: list[dict[str, Any]] = []
    source_matrices: list[np.ndarray] = []
    source_centers: list[np.ndarray] = []
    source_axes: list[np.ndarray] = []
    linear_velocities: list[np.ndarray] = []
    angular_velocities: list[np.ndarray] = []
    particle_positions: list[np.ndarray] = []
    baseline_world: np.ndarray | None = None
    baseline_center: np.ndarray | None = None
    hold_world: np.ndarray | None = None
    hold_center: np.ndarray | None = None

    def capture(local_step: int) -> None:
        nonlocal cached_source_world, baseline_world, baseline_center
        nonlocal hold_world, hold_center
        spec = trace_sample_spec(
            local_step,
            pre_roll_steps=pre_roll_steps,
            hold_steps=hold_steps,
        )
        current_world = _single_rigid_world_matrix(source_body)
        cached_source_world = current_world.copy()
        current_center = np.ascontiguousarray(
            (geometry_center_local @ current_world)[:3], dtype=np.float64
        )
        linear_velocity = passive._rigid_velocity(
            source_body, "get_linear_velocity"
        )
        angular_velocity = passive._rigid_velocity(
            source_body, "get_angular_velocity"
        )
        if local_step == 0:
            baseline_world = current_world.copy()
            baseline_center = current_center.copy()
        if baseline_world is None or baseline_center is None:
            raise RuntimeError("robot_present_baseline_missing")
        if local_step <= pre_roll_steps:
            reference_world = baseline_world
            reference_center = baseline_center
        else:
            if hold_world is None or hold_center is None:
                raise RuntimeError("robot_present_hold_reference_missing")
            reference_world = hold_world
            reference_center = hold_center
        motion = evaluate_preclose_source_motion(
            reference_center_world_m=reference_center,
            reference_source_world_matrix=reference_world,
            current_center_world_m=current_center,
            current_source_world_matrix=current_world,
            vessel_axis_object=vessel_axis_object,
            translation_limit_m=translation_limit,
            tilt_limit_degrees=tilt_limit,
        )
        current_source_frame = source_frame()
        pose_hash = _source_pose_sha256(current_world)
        positions = read_strict_simulation_points(
            stage,
            particle_path,
            expected_particle_count=expected_particle_count,
        )
        classification = classify_transfer_positions(
            positions,
            source_frame=current_source_frame,
            target_frame=target_frame(),
            table_z=table_z,
            minimum_target_particles=int(fluid.minimum_target_particles),
            minimum_task_target_fraction=float(fluid.minimum_task_target_fraction),
            minimum_expert_target_fraction=float(
                fluid.minimum_expert_target_fraction
            ),
        )
        record: dict[str, Any] = {
            **spec,
            "world_step": passive._world_counter(
                world, "current_time_step_index", integer=True
            ),
            "world_time_s": passive._world_counter(
                world, "current_time", integer=False
            ),
            "translation_m": motion["translation_m"],
            "tilt_degrees": motion["tilt_degrees"],
            "translation_valid": motion["translation_valid"],
            "tilt_valid": motion["tilt_valid"],
            "source_pose_sha256": pose_hash,
            "source_frame_pose_sha256": pose_hash,
            "source_frame_origin_world_m": [
                float(value) for value in current_source_frame.origin_world
            ],
            "source_frame_axis_world": [
                float(value) for value in current_source_frame.z_axis_world
            ],
            "particle_count": int(classification["particle_count"]),
            "partition_complete": bool(classification["partition_complete"]),
            "position_sha256": canonical_position_sha256(positions),
        }
        record.update(
            {name: int(classification[name]) for name in PARTITION_NAMES}
        )
        records.append(record)
        source_matrices.append(current_world.copy())
        source_centers.append(current_center.copy())
        source_axes.append(
            np.asarray(motion["current_axis_world"], dtype=np.float64)
        )
        linear_velocities.append(linear_velocity)
        angular_velocities.append(angular_velocity)
        particle_positions.append(np.asarray(positions, dtype=np.float64).copy())
        if local_step == pre_roll_steps:
            hold_world = current_world.copy()
            hold_center = current_center.copy()

    capture(0)
    baseline_particle_position_sha256 = records[0]["position_sha256"]
    baseline_matches_authored = bool(
        baseline_particle_position_sha256 == authored_particle_position_sha256
    )
    authority_checkpoint = startup_motion["checkpoints"][-1]
    authority_origin_binding = {
        "checkpoint_name": authority_checkpoint["name"],
        "checkpoint_source_pose_sha256": authority_checkpoint[
            "source_pose_sha256"
        ],
        "baseline_source_pose_sha256": records[0]["source_pose_sha256"],
        "checkpoint_center_world_m": authority_checkpoint[
            "source_center_world_m"
        ],
        "baseline_center_world_m": source_centers[0].tolist(),
    }
    authority_origin_binding["valid"] = bool(
        authority_origin_binding["checkpoint_name"] == "authority_origin"
        and authority_origin_binding["checkpoint_source_pose_sha256"]
        == authority_origin_binding["baseline_source_pose_sha256"]
        and np.array_equal(
            np.asarray(
                authority_origin_binding["checkpoint_center_world_m"],
                dtype=np.float64,
            ),
            np.asarray(
                authority_origin_binding["baseline_center_world_m"],
                dtype=np.float64,
            ),
        )
    )
    if not authority_origin_binding["valid"]:
        raise RuntimeError("robot_present_authority_origin_binding_invalid")
    for local_step in range(1, pre_roll_steps + hold_steps + 1):
        before_step = passive._world_counter(
            world, "current_time_step_index", integer=True
        )
        before_time = passive._world_counter(world, "current_time", integer=False)
        world.step(render=False)
        ledger.assert_zero_post_origin()
        after_step = passive._world_counter(
            world, "current_time_step_index", integer=True
        )
        after_time = passive._world_counter(world, "current_time", integer=False)
        if after_step != before_step + 1:
            raise RuntimeError("robot_present_world_step_advance_invalid")
        if not math.isclose(
            after_time,
            before_time + physics_dt,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            raise RuntimeError("robot_present_world_time_advance_invalid")
        capture(local_step)

    ledger.assert_zero_post_origin()
    if not math.isclose(
        float(world.get_physics_dt()),
        physics_dt,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ) or not math.isclose(
        float(world.get_rendering_dt()),
        float(fluid.rendering_dt),
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise RuntimeError("robot_present_terminal_timing_invalid")
    schedule = passive.validate_trace_schedule(
        records,
        physics_dt=physics_dt,
        pre_roll_steps=pre_roll_steps,
        hold_steps=hold_steps,
    )
    motion_stability = passive.summarize_motion_trace(records)
    filled_summary = passive.summarize_filled_trace(
        records,
        expected_particle_count=expected_particle_count,
    )
    containment = containment_summary_from_filled(filled_summary)
    terminal_live_state = _live_state(
        robot=robot,
        task=task,
        fluid=fluid,
        contact_scene=contact_scene,
        expected_robot_position_world_m=cfg.robot.position,
    )
    readback_settings_at_terminal = _effective_particle_readback_settings(
        readback_settings_post_world
    )
    terminal_drives = _authored_drive_snapshot(stage, "/World/Franka")
    drives_unchanged = origin_drives["sha256"] == terminal_drives["sha256"]
    if not drives_unchanged:
        raise RuntimeError("robot_present_authored_drives_changed")
    ledger_summary = ledger.summary()
    if not ledger_summary["valid"]:
        raise RuntimeError("robot_present_zero_action_ledger_invalid")
    distinct_particle_hash_count = len(
        {record["position_sha256"] for record in records}
    )
    if distinct_particle_hash_count <= 1:
        raise RuntimeError("robot_present_particle_readback_not_fresh")

    artifacts = passive._write_trace_artifacts(
        output_dir=args.out_dir,
        records=records,
        source_matrices=source_matrices,
        source_centers=source_centers,
        source_axes=source_axes,
        linear_velocities=linear_velocities,
        angular_velocities=angular_velocities,
        particle_positions=particle_positions,
    )
    measurement_passed = bool(
        startup_motion["passed"]
        and motion_stability["passed"]
        and containment["passed"]
        and drives_unchanged
    )
    particle_readback_authority = {
        "pre_world_applied": readback_settings_pre_world,
        "post_world_reasserted": readback_settings_post_world,
        "authority_origin_effective": readback_settings_at_origin,
        "terminal_effective": readback_settings_at_terminal,
        "authored_position_sha256": authored_particle_position_sha256,
        "baseline_position_sha256": baseline_particle_position_sha256,
        "baseline_matches_authored": baseline_matches_authored,
        "baseline_comparison_scope": "pre_world_authored_vs_post_final_reset",
        "distinct_position_sha256_count": distinct_particle_hash_count,
        "dynamic_updates_observed": True,
        "valid": True,
    }
    runtime = passive._runtime_identity()
    no_action_contract = {
        **ledger_summary,
        "definition": "zero_post_origin_command_api_calls",
        "task_or_policy_controller_constructed_during_child": False,
        "intrinsic_robot_articulation_controller_present": True,
        "physics_step_call_count": pre_roll_steps + hold_steps,
        "physics_step_render_false_count": pre_roll_steps + hold_steps,
        "explicit_render_call_count": ledger_summary["post_origin_api_counts"].get(
            "world.render", 0
        ),
        "task_step_call_count": ledger_summary["post_origin_api_counts"].get(
            "task.step", 0
        ),
        "post_origin_reset_count": sum(
            count
            for api, count in ledger_summary["post_origin_api_counts"].items()
            if api.endswith(".reset")
        ),
        "source_pose_or_velocity_write_count": sum(
            count
            for api, count in ledger_summary["post_origin_api_counts"].items()
            if api.startswith("source_body.")
            or api == "object_utils.set_object_position"
        ),
        "robot_or_gripper_command_count": sum(
            count
            for api, count in ledger_summary["post_origin_api_counts"].items()
            if api.startswith("robot.")
            or api.startswith("gripper.")
            or api.startswith("articulation_controller.")
        ),
        "probe_issued_particle_mutation_count": 0,
        "particle_mutation_authority": "runner_control_flow_no_particle_setter",
        "authored_robot_drives_zeroed": False,
        "authored_robot_drives_present": True,
        "mechanical_attachment_count": 0,
        "collision_filter_edit_count": 0,
        "grasp_authorized": False,
        "raw_usd_attribute_setters_globally_intercepted": False,
    }
    bootstrap_ledger = [
        "simulation_app_started",
        "legacy_isaacsim_aliases_installed",
        "particle_usd_readback_configured_pre_world",
        "candidate_usd_referenced",
        "authored_source_authority_captured_pre_world",
        "world_constructed_without_prepended_reset",
        "particle_usd_readback_reasserted_post_world",
        "franka_constructed_from_explicit_config",
        "contact_grasp_material_configured",
        "object_utils_initialized",
        "pickpour_task_constructed_camera_reset_complete",
        "explicit_task_reset_complete",
        "fluid_world_timing_reasserted",
        "full_fluid_stage_contract_validated",
        "source_readback_initialized",
        "live_robot_task_state_validated",
        "production_cameras_disclosed",
        "zero_action_instrumentation_installed",
        "authority_origin_captured",
    ]
    return {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "run_nonce": args.run_nonce,
        "measurement_decision": (
            "ROBOT_PRESENT_ZERO_ACTION_PASS"
            if measurement_passed
            else "ROBOT_PRESENT_ZERO_ACTION_FAIL"
        ),
        "config_path": str(args.config),
        "config_sha256": config_sha256,
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "usd_path": str(usd_path),
        "candidate_contract": candidate_contract,
        "usd_dependency_closure": dependency_closure,
        "robot_usd": {
            "path": str(robot_usd_path),
            "sha256": robot_sha256,
        },
        "runtime": runtime,
        "particle_usd_readback": particle_readback_authority,
        "bootstrap_ledger": bootstrap_ledger,
        "reset_contract": reset_contract,
        "startup_motion": startup_motion,
        "authority_origin_binding": authority_origin_binding,
        "contact_grasp_scene": contact_scene,
        "stage_contract": stage_contract,
        "trace_authority": trace_authority,
        "live_state": {
            "authority_origin": origin_live_state,
            "terminal": terminal_live_state,
        },
        "production_cameras": camera_disclosure,
        "authored_robot_drives": {
            "authority_origin": origin_drives,
            "terminal": terminal_drives,
            "unchanged": drives_unchanged,
            "authored_drive_apis_remain_present": True,
        },
        "trace_schedule": schedule,
        "motion_stability": motion_stability,
        "containment": containment,
        "zero_action_contract": no_action_contract,
        "timing": {
            "physics_dt": physics_dt,
            "rendering_dt": float(fluid.rendering_dt),
            "physics_hz": 1.0 / physics_dt,
            "pre_roll_steps": pre_roll_steps,
            "hold_steps": hold_steps,
        },
        "artifacts": artifacts,
        "claim_limits": {
            "grasp_authorized": False,
            "causal_attribution_allowed": False,
            "repeatability_claim_allowed": False,
            "mass_or_force_claim_allowed": False,
            "production_claim_allowed": False,
        },
        "stage_units_in_meters": float(get_stage_units()),
        "gravity_world_m_s2": passive._gravity_vector(
            stage, str(fluid.physics_scene_path)
        ),
    }


def _validate_artifact_record(
    record: Mapping[str, Any],
    *,
    output_dir: Path,
) -> Path:
    relative = Path(str(record.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("robot_present_artifact_path_invalid")
    path = output_dir / relative
    if (
        not path.is_file()
        or type(record.get("byte_count")) is not int
        or path.stat().st_size != record["byte_count"]
        or record.get("sha256") != sha256_file(path)
    ):
        raise ValueError("robot_present_artifact_hash_invalid")
    return path


def _validate_report_drive_snapshot(snapshot: Any) -> None:
    if not isinstance(snapshot, Mapping):
        raise ValueError("robot_present_parent_drive_snapshot_invalid")
    payload = {
        key: snapshot.get(key)
        for key in (
            "robot_path",
            "drive_count",
            "joint_names",
            "active_drive_count",
            "drives",
        )
    }
    drive_records = payload["drives"]
    if (
        not isinstance(drive_records, list)
        or len(drive_records) != len(EXPECTED_FRANKA_DOF_NAMES)
        or any(not isinstance(record, Mapping) for record in drive_records)
    ):
        raise ValueError("robot_present_parent_drive_snapshot_invalid")
    derived_names = [str(record.get("joint_name")) for record in drive_records]
    derived_active_count = sum(record.get("active") is True for record in drive_records)
    if (
        snapshot.get("valid") is not True
        or payload["robot_path"] != "/World/Franka"
        or payload["drive_count"] != len(drive_records)
        or len(drive_records) != 9
        or payload["active_drive_count"] != derived_active_count
        or derived_active_count != 8
        or payload["joint_names"] != derived_names
        or set(derived_names) != set(EXPECTED_FRANKA_DOF_NAMES)
        or snapshot.get("sha256") != passive._canonical_json_sha256(payload)
    ):
        raise ValueError("robot_present_parent_drive_snapshot_invalid")


def _validate_dependency_closure_record(
    closure: Any,
    *,
    expected_sha256: str,
    expected_entry_path: Path,
) -> None:
    if not isinstance(closure, Mapping):
        raise ValueError("robot_present_dependency_closure_invalid")
    files = closure.get("files")
    payload = {
        "entry_path": closure.get("entry_path"),
        "files": files,
        "unresolved": closure.get("unresolved"),
    }
    if (
        payload["entry_path"] != str(expected_entry_path.resolve())
        or not isinstance(files, list)
        or not files
        or payload["unresolved"] != []
        or closure.get("sha256") != expected_sha256
        or passive._canonical_json_sha256(payload) != expected_sha256
    ):
        raise ValueError("robot_present_dependency_closure_invalid")
    seen: set[str] = set()
    for record in files:
        if not isinstance(record, Mapping):
            raise ValueError("robot_present_dependency_closure_invalid")
        path = Path(str(record.get("path", "")))
        if (
            not path.is_absolute()
            or str(path) in seen
            or not path.is_file()
            or type(record.get("byte_count")) is not int
            or path.stat().st_size != record["byte_count"]
            or record.get("sha256") != sha256_file(path)
        ):
            raise ValueError("robot_present_dependency_closure_invalid")
        seen.add(str(path))


def _validate_parent_report_contract(report: Mapping[str, Any]) -> None:
    candidate = report.get("candidate_contract")
    reset = report.get("reset_contract")
    startup = report.get("startup_motion")
    authority_binding = report.get("authority_origin_binding")
    contact_scene = report.get("contact_grasp_scene")
    live = report.get("live_state")
    cameras = report.get("production_cameras")
    drives = report.get("authored_robot_drives")
    zero_action = report.get("zero_action_contract")
    timing = report.get("timing")
    readback = report.get("particle_usd_readback")
    trace_authority = report.get("trace_authority")
    robot_usd = report.get("robot_usd")
    usd_path = Path(str(report.get("usd_path", "")))
    _validate_dependency_closure_record(
        report.get("usd_dependency_closure"),
        expected_sha256=EXPECTED_SCENE_DEPENDENCY_CLOSURE_SHA256,
        expected_entry_path=usd_path,
    )
    normalized_trace_frame = _validate_source_frame_contract(
        trace_authority.get("source_frame_contract")
        if isinstance(trace_authority, Mapping)
        else None
    )
    if isinstance(drives, Mapping):
        _validate_report_drive_snapshot(drives.get("authority_origin"))
        _validate_report_drive_snapshot(drives.get("terminal"))
    camera_objects = cameras.get("camera_objects", []) if isinstance(cameras, Mapping) else []
    installed_required = {
        record.get("api")
        for record in zero_action.get("instrumentation", [])
        if isinstance(record, Mapping)
        and record.get("required") is True
        and record.get("installed") is True
    } if isinstance(zero_action, Mapping) else set()
    if (
        not isinstance(candidate, Mapping)
        or report.get("runner_sha256") != sha256_file(Path(__file__).resolve())
        or candidate.get("valid") is not True
        or candidate.get("config_sha256") != EXPECTED_CONFIG_SHA256
        or candidate.get("asset_sha256") != EXPECTED_ASSET_SHA256
        or candidate.get("record_count") != 2401
        or candidate.get("particle_trace_shape") != [2401, 3600, 3]
        or not isinstance(robot_usd, Mapping)
        or robot_usd.get("path")
        != str((REPO_ROOT / "assets/robots/Franka.usd").resolve())
        or robot_usd.get("sha256") != EXPECTED_ROBOT_SHA256
        or sha256_file(robot_usd["path"]) != EXPECTED_ROBOT_SHA256
        or not isinstance(reset, Mapping)
        or reset.get("reset_labels") != list(EXPECTED_BOOTSTRAP_RESET_LABELS)
        or reset.get("reset_count") != 2
        or reset.get("prepended_world_reset_count") != 0
        or reset.get("post_origin_reset_count") != 0
        or not isinstance(startup, Mapping)
        or startup.get("valid") is not True
        or type(startup.get("passed")) is not bool
        or [
            checkpoint.get("name")
            for checkpoint in startup.get("checkpoints", [])
            if isinstance(checkpoint, Mapping)
        ]
        != [
            "task_constructor_camera_reset",
            "explicit_task_reset",
            "authority_origin",
        ]
        or not isinstance(authority_binding, Mapping)
        or authority_binding.get("valid") is not True
        or authority_binding.get("checkpoint_name") != "authority_origin"
        or authority_binding.get("checkpoint_source_pose_sha256")
        != authority_binding.get("baseline_source_pose_sha256")
        or not isinstance(contact_scene, Mapping)
        or contact_scene.get("valid") is not True
        or contact_scene.get("validated_material_binding_count") != 2
        or not isinstance(live, Mapping)
        or any(
            not isinstance(live.get(name), Mapping)
            or live[name].get("valid") is not True
            for name in ("authority_origin", "terminal")
        )
        or not isinstance(cameras, Mapping)
        or cameras.get("valid") is not True
        or cameras.get("camera_object_count") != 3
        or cameras.get("additional_diagnostic_camera_count") != 0
        or cameras.get("probe_image_read_count") != 0
        or len(camera_objects) != 3
        or sum(
            record.get("role") == "task_model_camera"
            and record.get("render_product_constructed") is True
            for record in camera_objects
            if isinstance(record, Mapping)
        )
        != 2
        or not isinstance(drives, Mapping)
        or drives.get("unchanged") is not True
        or drives.get("authored_drive_apis_remain_present") is not True
        or drives.get("authority_origin", {}).get("sha256")
        != drives.get("terminal", {}).get("sha256")
        or not isinstance(zero_action, Mapping)
        or zero_action.get("valid") is not True
        or zero_action.get("post_origin_call_count") != 0
        or zero_action.get("task_or_policy_controller_constructed_during_child")
        is not False
        or zero_action.get("intrinsic_robot_articulation_controller_present")
        is not True
        or zero_action.get("physics_step_call_count") != 2400
        or zero_action.get("physics_step_render_false_count") != 2400
        or zero_action.get("explicit_render_call_count") != 0
        or zero_action.get("task_step_call_count") != 0
        or zero_action.get("post_origin_reset_count") != 0
        or zero_action.get("source_pose_or_velocity_write_count") != 0
        or zero_action.get("robot_or_gripper_command_count") != 0
        or zero_action.get("probe_issued_particle_mutation_count") != 0
        or zero_action.get("particle_mutation_authority")
        != "runner_control_flow_no_particle_setter"
        or not REQUIRED_POST_ORIGIN_APIS.issubset(installed_required)
        or not isinstance(readback, Mapping)
        or readback.get("valid") is not True
        or type(readback.get("baseline_matches_authored")) is not bool
        or readback.get("dynamic_updates_observed") is not True
        or not isinstance(readback.get("distinct_position_sha256_count"), int)
        or readback["distinct_position_sha256_count"] <= 1
        or readback.get("baseline_matches_authored")
        is not (
            readback.get("authored_position_sha256")
            == readback.get("baseline_position_sha256")
        )
        or any(
            not isinstance(readback.get(name), Mapping)
            or readback[name].get("valid") is not True
            for name in ("authority_origin_effective", "terminal_effective")
        )
        or not isinstance(trace_authority, Mapping)
        or normalized_trace_frame.get("valid") is not True
        or trace_authority.get("source_frame_contract", {}).get("sha256")
        != normalized_trace_frame["sha256"]
        or not isinstance(timing, Mapping)
        or not math.isclose(
            float(timing.get("physics_dt", 0.0)),
            1.0 / 600.0,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        or timing.get("pre_roll_steps") != 600
        or timing.get("hold_steps") != 1800
    ):
        raise ValueError("robot_present_parent_report_contract_invalid")
    for snapshot_name in ("authority_origin_effective", "terminal_effective"):
        validate_effective_particle_readback_settings(
            readback["post_world_reasserted"],
            readback[snapshot_name]["settings"],
        )
    reference = startup["reference"]
    recomputed_startup = summarize_startup_motion_checkpoints(
        authored_source_world_matrix=reference["source_world_matrix"],
        authored_source_center_world_m=reference["source_center_world_m"],
        checkpoints=startup["checkpoints"],
        vessel_axis_object=[0.0, 1.0, 0.0],
        translation_limit_m=0.002,
        tilt_limit_degrees=1.0,
    )
    if passive._canonical_json_sha256(recomputed_startup) != passive._canonical_json_sha256(
        startup
    ):
        raise ValueError("robot_present_parent_startup_motion_mismatch")


def _validate_artifacts(
    report: Mapping[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    _validate_parent_report_contract(report)
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "source_trace",
        "particle_trace",
    }:
        raise ValueError("robot_present_artifact_set_invalid")
    source_path = _validate_artifact_record(
        artifacts["source_trace"], output_dir=output_dir
    )
    particle_path = _validate_artifact_record(
        artifacts["particle_trace"], output_dir=output_dir
    )
    with np.load(source_path, allow_pickle=False) as source, np.load(
        particle_path, allow_pickle=False
    ) as particles:
        validation = validate_trace_array_contract(
            source,
            particles,
            physics_dt=1.0 / 600.0,
            pre_roll_steps=600,
            hold_steps=1800,
            expected_particle_count=3600,
            trace_authority=report.get("trace_authority", {}),
        )
    if validation["schedule"] != report.get("trace_schedule"):
        raise ValueError("robot_present_parent_schedule_mismatch")
    if validation["baseline_source_pose_sha256"] != report.get(
        "authority_origin_binding", {}
    ).get("baseline_source_pose_sha256"):
        raise ValueError("robot_present_parent_origin_binding_mismatch")
    motion = report.get("motion_stability")
    containment = report.get("containment")
    filled = validation["filled_summary"]
    expected_containment = containment_summary_from_filled(filled)
    if (
        not isinstance(motion, Mapping)
        or not motion_summaries_match(motion, validation["motion_summary"])
        or not isinstance(containment, Mapping)
        or passive._canonical_json_sha256(containment)
        != passive._canonical_json_sha256(expected_containment)
    ):
        raise ValueError("robot_present_parent_summary_mismatch")
    readback = report["particle_usd_readback"]
    if (
        validation["baseline_source_pose_sha256"]
        != report["authority_origin_binding"]["baseline_source_pose_sha256"]
        or validation["distinct_particle_position_hash_count"]
        != readback["distinct_position_sha256_count"]
        or validation["baseline_particle_position_sha256"]
        != readback["baseline_position_sha256"]
    ):
        raise ValueError("robot_present_parent_readback_authority_mismatch")
    decision_passed = report.get("measurement_decision") == (
        "ROBOT_PRESENT_ZERO_ACTION_PASS"
    )
    expected_passed = bool(
        report["startup_motion"]["passed"]
        and filled["passed"]
        and report["authored_robot_drives"]["unchanged"]
    )
    if decision_passed is not expected_passed:
        raise ValueError("robot_present_parent_decision_mismatch")
    return validation


def _run_runtime_child(args: argparse.Namespace) -> int:
    provisional_path = args.out_dir / PROVISIONAL_REPORT_BASENAME
    app = None
    config_sha256 = sha256_file(args.config)
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "width": 64, "height": 64})
        try:
            report = _measure_runtime(args)
        except Exception as exc:
            report = _runtime_error_report(
                exc,
                run_nonce=args.run_nonce,
                config_sha256=config_sha256,
                phase="runtime_measurement",
            )
        passive.atomic_create_json(provisional_path, report)
    except Exception as exc:
        if not provisional_path.exists():
            passive.atomic_create_json(
                provisional_path,
                _runtime_error_report(
                    exc,
                    run_nonce=args.run_nonce,
                    config_sha256=config_sha256,
                    phase="application_bootstrap",
                ),
            )
        return 1
    finally:
        if app is not None:
            app.close()
    return 0


def _terminate_and_reap(process: subprocess.Popen[Any]) -> str:
    termination = "SIGTERM"
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30.0)
    except subprocess.TimeoutExpired:
        termination = "SIGKILL"
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            termination = "SIGKILL_UNREAPED"
    return termination


def _child_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--runtime-child",
        "--config",
        str(args.config),
        "--out-dir",
        str(args.out_dir),
        "--run-nonce",
        args.run_nonce,
    ]


def _run_parent(args: argparse.Namespace) -> int:
    try:
        args.out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(
            f"robot-present zero-action probe refused existing output: {args.out_dir}",
            file=sys.stderr,
            flush=True,
        )
        return 2
    command = _child_command(args)
    timed_out = False
    termination = None
    child_returncode = 127
    launch_error: OSError | None = None
    process: subprocess.Popen[Any] | None = None
    with (args.out_dir / "child.stdout.log").open("xb") as stdout, (
        args.out_dir / "child.stderr.log"
    ).open("xb") as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            try:
                child_returncode = int(
                    process.wait(timeout=args.timeout_seconds)
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                termination = _terminate_and_reap(process)
                child_returncode = (
                    int(process.returncode)
                    if process.returncode is not None
                    else -signal.SIGKILL
                )
        except OSError as exc:
            launch_error = exc
        except BaseException:
            if process is not None and process.poll() is None:
                _terminate_and_reap(process)
            raise

    provisional_path = args.out_dir / PROVISIONAL_REPORT_BASENAME
    try:
        provisional = passive._load_json_mapping(provisional_path)
        if (
            provisional.get("manifest_type") != MANIFEST_TYPE
            or provisional.get("run_nonce") != args.run_nonce
            or provisional.get("config_sha256") != EXPECTED_CONFIG_SHA256
        ):
            raise ValueError("robot_present_provisional_identity_invalid")
        if provisional.get("measurement_decision") != "PROBE_RUNTIME_ERROR":
            artifact_validation = _validate_artifacts(
                provisional, output_dir=args.out_dir
            )
            provisional = dict(provisional)
            provisional["parent_artifact_validation"] = artifact_validation
    except Exception as exc:
        provisional = _runtime_error_report(
            exc,
            run_nonce=args.run_nonce,
            config_sha256=EXPECTED_CONFIG_SHA256,
            phase="parent_artifact_validation",
        )
        if launch_error is not None:
            provisional["fatal_error"]["launch_error"] = str(launch_error)
    report = finalize_child_report(
        provisional,
        expected_run_nonce=args.run_nonce,
        expected_config_sha256=EXPECTED_CONFIG_SHA256,
        child_command=command,
        child_returncode=child_returncode,
        timed_out=timed_out,
        termination=termination,
    )
    final_path = args.out_dir / FINAL_REPORT_BASENAME
    passive.atomic_create_json(final_path, report)
    print(
        f"robot-present zero-action probe decision={report['decision']} "
        f"out={final_path}",
        flush=True,
    )
    return 0 if report["lifecycle_status"] == "completed" else 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--runtime-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-nonce", default="", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.config.is_file():
        parser.error(f"config not found: {args.config}")
    if sha256_file(args.config) != EXPECTED_CONFIG_SHA256:
        parser.error("config does not match the hash-pinned candidate")
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("timeout must be finite and positive")
    if args.runtime_child:
        if not args.run_nonce or not args.out_dir.is_dir():
            parser.error("runtime child requires reserved output and nonce")
    else:
        if args.run_nonce:
            parser.error("run nonce is parent-managed")
        args.run_nonce = secrets.token_hex(16)
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_runtime_child(args) if args.runtime_child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
