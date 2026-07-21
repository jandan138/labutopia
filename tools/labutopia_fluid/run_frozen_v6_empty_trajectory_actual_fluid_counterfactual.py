#!/usr/bin/env python3
"""Render a rejected real-PBD-liquid replay of the frozen v6 empty-beaker actions.

This runner is intentionally separate from ``main.py`` and does not construct a
task controller or finalize a collect episode. It replays the recorded raw joint
actions verbatim while the source vessel and liquid remain PhysX/PBD driven.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_frozen_v6_empty_trajectory_actual_fluid_v1.yaml"
)
EXPECTED_SOURCE_TRACE_RELATIVE_PATH = Path(
    "outputs/native_expert_empty_beaker_unbound_lift_20260720_005/"
    "instrumented/trace.jsonl"
)
EXPECTED_SOURCE_TRACE_SHA256 = (
    "36dfe27b8086fb21cf1f8c86ff27b6b5a2d63362ebde189b477d44adb7d73a04"
)
SOURCE_TRACE_MANIFEST_TYPE = "native_expert_empty_beaker_unbound_lift_trace_v1"
SOURCE_PROTOCOL_ID = "native_expert_empty_beaker_unbound_lift_v6"
SOURCE_CONFIG_SHA256 = (
    "fb86040b98e59b96b79c65871cb60277df67d09192d075119ebfe6fb87f9e28c"
)
MANIFEST_TYPE = "frozen_v6_empty_trajectory_actual_fluid_counterfactual_v1"
FORCED_STATUS = "REJECTED_UNSAFE_VISUAL_ONLY"
RUNTIME_INTEGRITY_FAILURE = "COUNTERFACTUAL_RUNTIME_INTEGRITY_FAILURE"
RUNTIME_ERROR = "COUNTERFACTUAL_RUNTIME_ERROR"
ACTION_CHANNELS = ("joint_positions", "joint_velocities", "joint_efforts")
VIDEO_BASENAME = "unsafe_visual_only_counterfactual.mp4"
VIDEO_MAP_BASENAME = "unsafe_visual_only_counterfactual_frame_map.json"
OBSERVATION_TRACE_BASENAME = "counterfactual_observations.jsonl"
PROVISIONAL_REPORT_BASENAME = "provisional_report.json"
FINAL_REPORT_BASENAME = "report.json"
LIVE_NORMAL_POLICY = (
    "area_weighted_face_with_oriented_density_zero_sum_fallback_v1"
)
LIVE_NORMAL_ZERO_SUM_EPSILON = 1.0e-15
LIVE_NORMAL_FALLBACK_MAX_FRACTION = 0.01
LIVE_NORMAL_FALLBACK_NEIGHBOR_ALIGNMENT_MIN_DOT = 0.5
FRANKA_DOF_NAMES = (
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
EXPECTED_ROBOT_USD_RELATIVE_PATH = Path("assets/robots/Franka.usd")
EXPECTED_ROBOT_USD_SHA256 = (
    "312a326e338949fb40fd245886508cc52cc47e2bebd696e99c7dcdd3d3a7f90b"
)
ROBOT_ROOT_PATH = "/World/Franka"
ACTION_REPRESENTATION_ADAPTER_SCHEMA = "frozen_v6_action_representation_adapter_v1"
VIDEO_SAMPLING_POLICY = "initial_t0_then_odd_source_transitions_cfr30"
HD_PRESENTATION_SCHEMA = "frozen_v6_counterfactual_hd_presentation_v1"
HD_PRESENTATION_CAPTURE_POLICY = "viewport_same_observation_no_physics_step_v1"
HD_PRESENTATION_RAW_DIRECTORY = "presentation_raw"
HD_PRESENTATION_FINAL_DIRECTORY = "presentation_hd"
HD_PRESENTATION_MANIFEST_BASENAME = "presentation_video_manifest.json"
HD_PRESENTATION_FRAMES_BASENAME = "presentation_video_frames.jsonl"
HD_PRESENTATION_FRAME_MAP_BASENAME = "presentation_frame_map.json"
HD_PRESENTATION_WIDTH = 1280
HD_PRESENTATION_HEIGHT = 720
HD_PRESENTATION_FPS = 30
HD_PRESENTATION_VIEWPORT_WINDOW_NAME = "FrozenV6CounterfactualPresentation"
HD_PRESENTATION_FONT_PATH = Path(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
)
HD_PRESENTATION_BANNER_HEIGHT = 72
HD_PRESENTATION_BANNER_COLOR = "0x8B0000"
HD_PRESENTATION_BANNER_LINES = (
    "REJECTED - UNSAFE VISUAL-ONLY",
    "DISTINCT PBD COUNTERFACTUAL - NOT GRASP, TRANSFER, OR SUCCESS EVIDENCE",
)
HD_PRESENTATION_CAMERA_SPECS = (
    ("camera_1", "/World/InternDataParityCamera"),
    ("camera_2", "/World/InternDataParityCloseupCamera"),
)
HD_PRESENTATION_ARTIFACT_KEYS = (
    "hd_presentation_manifest",
    "hd_presentation_frames",
    "hd_presentation_frame_map",
    "hd_presentation_camera_1_raw",
    "hd_presentation_camera_1",
    "hd_presentation_camera_2_raw",
    "hd_presentation_camera_2",
)
VELOCITY_MODE_TRANSITION = {
    "source_transition_index": 487,
    "dof_index": 6,
    "mode": "velocity",
}
FROZEN_V6_ACTION_LAYOUT_SPECS = {
    (7, 7, None): {
        "name": "arm_position_velocity_7",
        "joint_indices": tuple(range(7)),
        "count": 412,
    },
    (9, None, None): {
        "name": "full_position_9",
        "joint_indices": None,
        "count": 70,
    },
    (None, 9, None): {
        "name": "full_velocity_9",
        "joint_indices": None,
        "count": 376,
    },
}
EXPECTED_ACTION_REPRESENTATION_ADAPTER_CONFIG = {
    "schema": ACTION_REPRESENTATION_ADAPTER_SCHEMA,
    "source_trace_omits_joint_indices": True,
    "expected_robot_usd_path": str(EXPECTED_ROBOT_USD_RELATIVE_PATH),
    "expected_robot_usd_sha256": EXPECTED_ROBOT_USD_SHA256,
    "expected_robot_dof_names": list(FRANKA_DOF_NAMES),
    "expected_finger_joint_indices": [7, 8],
    "action_layouts": [
        {
            "name": "arm_position_velocity_7",
            "channel_lengths": {
                "joint_positions": 7,
                "joint_velocities": 7,
                "joint_efforts": None,
            },
            "joint_indices": list(range(7)),
            "count": 412,
        },
        {
            "name": "full_position_9",
            "channel_lengths": {
                "joint_positions": 9,
                "joint_velocities": None,
                "joint_efforts": None,
            },
            "joint_indices": None,
            "count": 70,
        },
        {
            "name": "full_velocity_9",
            "channel_lengths": {
                "joint_positions": None,
                "joint_velocities": 9,
                "joint_efforts": None,
            },
            "joint_indices": None,
            "count": 376,
        },
    ],
    "velocity_mode_transition": VELOCITY_MODE_TRANSITION,
}


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_native(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_native(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("counterfactual_json_nonfinite")
    return value


def _canonical_json_bytes(value: Any, *, indent: int | None = None) -> bytes:
    try:
        encoded = json.dumps(
            _json_native(value),
            allow_nan=False,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("counterfactual_json_invalid") from exc
    return (encoded + "\n").encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value).rstrip(b"\n")).hexdigest()


def _validate_live_normal_provenance(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("counterfactual_surface_normal_provenance_invalid")
    payload = dict(value)
    digest = payload.pop("sha256", None)
    indices = payload.get("fallback_vertex_indices")
    count = payload.get("fallback_vertex_count")
    signs = payload.get("component_orientation_signs")
    density_sha256 = payload.get("density_normals_sha256")
    alignment_dots = payload.get("fallback_neighbor_alignment_min_dots")
    component_count = payload.get("component_count")
    if (
        payload.get("policy") != LIVE_NORMAL_POLICY
        or not math.isclose(
            float(payload.get("normal_zero_sum_epsilon", math.nan)),
            LIVE_NORMAL_ZERO_SUM_EPSILON,
            rel_tol=0.0,
            abs_tol=1.0e-30,
        )
        or not math.isclose(
            float(payload.get("normal_fallback_max_fraction", math.nan)),
            LIVE_NORMAL_FALLBACK_MAX_FRACTION,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        or not math.isclose(
            float(
                payload.get(
                    "normal_fallback_neighbor_alignment_min_dot", math.nan
                )
            ),
            LIVE_NORMAL_FALLBACK_NEIGHBOR_ALIGNMENT_MIN_DOT,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        or type(count) is not int
        or count < 0
        or not isinstance(indices, list)
        or len(indices) != count
        or any(type(index) is not int or index < 0 for index in indices)
        or indices != sorted(set(indices))
        or payload.get("fallback_vertex_indices_sha256")
        != _canonical_json_sha256(indices)
        or not isinstance(signs, list)
        or type(component_count) is not int
        or component_count <= 0
        or len(signs) != component_count
        or not isinstance(alignment_dots, list)
        or len(alignment_dots) != count
        or any(
            not isinstance(dot, (int, float))
            or isinstance(dot, bool)
            or not math.isfinite(float(dot))
            or float(dot) < LIVE_NORMAL_FALLBACK_NEIGHBOR_ALIGNMENT_MIN_DOT
            or float(dot) > 1.0
            for dot in alignment_dots
        )
        or any(type(sign) is not int for sign in signs)
        or (
            count == 0
            and (
                density_sha256 is not None
                or any(sign != 0 for sign in signs)
                or alignment_dots != []
            )
        )
        or (
            count > 0
            and (
                not _is_sha256(density_sha256)
                or any(sign not in (-1, 1) for sign in signs)
            )
        )
        or digest != _canonical_json_sha256(payload)
    ):
        raise ValueError("counterfactual_surface_normal_provenance_invalid")
    return {**payload, "sha256": digest}


def _surface_normal_provenance_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    surface = record.get("surface")
    if not isinstance(surface, Mapping):
        raise ValueError("counterfactual_surface_normal_provenance_invalid")
    return _validate_live_normal_provenance(surface.get("normal_provenance"))


def _surface_geometry_sha256_from_record(record: Mapping[str, Any]) -> str:
    surface = record.get("surface")
    geometry_sha256 = surface.get("geometry_sha256") if isinstance(surface, Mapping) else None
    if not _is_sha256(geometry_sha256):
        raise ValueError("counterfactual_surface_geometry_invalid")
    return geometry_sha256


def _atomic_create_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical_json_bytes(value, indent=2)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError as exc:
            raise FileExistsError(
                f"counterfactual_output_exists:{path}"
            ) from exc
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary_path.unlink(missing_ok=True)


def _normalise_action(action: Any) -> dict[str, list[float | None] | None]:
    if not isinstance(action, Mapping) or set(action) != set(ACTION_CHANNELS):
        raise ValueError("counterfactual_source_action_invalid")
    result: dict[str, list[float | None] | None] = {}
    for name in ACTION_CHANNELS:
        values = action[name]
        if values is None:
            result[name] = None
            continue
        if isinstance(values, (str, bytes, bytearray)):
            raise ValueError("counterfactual_source_action_invalid")
        try:
            entries = list(values)
        except TypeError as exc:
            raise ValueError("counterfactual_source_action_invalid") from exc
        if not entries:
            raise ValueError("counterfactual_source_action_invalid")
        normalised: list[float | None] = []
        for value in entries:
            if value is None:
                normalised.append(None)
            elif (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.number))
                or not math.isfinite(float(value))
            ):
                raise ValueError("counterfactual_source_action_invalid")
            else:
                number = float(value)
                normalised.append(0.0 if number == 0.0 else number)
        result[name] = normalised
    return result


def canonicalize_action(action: Any) -> dict[str, Any]:
    """Use the v6 byte-level action representation for replay verification."""
    raw = _normalise_action(action)
    channels: dict[str, dict[str, Any]] = {}
    for name in ACTION_CHANNELS:
        values = raw[name]
        if values is None:
            channels[name] = {
                "present": False,
                "shape": None,
                "none_mask_hex": None,
                "float64_le_hex": None,
            }
            continue
        array = np.zeros(len(values), dtype=np.dtype("<f8"))
        mask = bytearray((len(values) + 7) // 8)
        for index, value in enumerate(values):
            if value is None:
                mask[index // 8] |= 1 << (index % 8)
            else:
                array[index] = value
        channels[name] = {
            "present": True,
            "shape": [len(values)],
            "none_mask_hex": bytes(mask).hex(),
            "float64_le_hex": array.tobytes(order="C").hex(),
        }
    payload = {"channel_order": list(ACTION_CHANNELS), "channels": channels}
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _frozen_v6_action_layout_from_raw(
    raw: Mapping[str, list[float | None] | None],
) -> dict[str, Any]:
    lengths = tuple(
        None if raw[channel] is None else len(raw[channel])
        for channel in ACTION_CHANNELS
    )
    specification = FROZEN_V6_ACTION_LAYOUT_SPECS.get(lengths)
    if specification is None:
        raise ValueError("counterfactual_action_layout_invalid")
    return {
        "name": specification["name"],
        "channel_lengths": dict(zip(ACTION_CHANNELS, lengths)),
        "joint_indices": (
            None
            if specification["joint_indices"] is None
            else list(specification["joint_indices"])
        ),
    }


def resolve_frozen_v6_action_layout(action: Any) -> dict[str, Any]:
    """Rehydrate only the index information omitted by the v6 trace schema."""
    return _frozen_v6_action_layout_from_raw(_normalise_action(action))


def _effective_action_receipt(transition: Mapping[str, Any]) -> dict[str, Any] | None:
    action = transition.get("action")
    if action is None:
        return None
    if type(transition.get("source_transition_index")) is not int:
        raise ValueError("counterfactual_effective_action_receipt_invalid")
    raw = _normalise_action(action)
    canonical = canonicalize_action(raw)
    if transition.get("action_sha256") != canonical["sha256"]:
        raise ValueError("counterfactual_effective_action_receipt_invalid")
    layout = _frozen_v6_action_layout_from_raw(raw)
    source_transition_index = int(transition["source_transition_index"])
    mode_transition = (
        dict(VELOCITY_MODE_TRANSITION)
        if source_transition_index == VELOCITY_MODE_TRANSITION["source_transition_index"]
        else None
    )
    if mode_transition is not None and layout["name"] != "full_velocity_9":
        raise ValueError("counterfactual_action_layout_invalid")
    payload = {
        "schema": ACTION_REPRESENTATION_ADAPTER_SCHEMA,
        "source_transition_index": source_transition_index,
        "source_action_sha256": canonical["sha256"],
        "layout": layout,
        "velocity_mode_transition": mode_transition,
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _velocity_mode_switch_receipt(
    effective_action_receipt: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if effective_action_receipt is None:
        return None
    transition = effective_action_receipt.get("velocity_mode_transition")
    if transition is None:
        return None
    if not isinstance(transition, Mapping):
        raise ValueError("counterfactual_velocity_mode_receipt_invalid")
    payload = {
        "schema": ACTION_REPRESENTATION_ADAPTER_SCHEMA,
        "source_transition_index": transition.get("source_transition_index"),
        "dof_index": transition.get("dof_index"),
        "mode": transition.get("mode"),
        "applied": True,
        "normal_return": True,
    }
    if payload != {
        "schema": ACTION_REPRESENTATION_ADAPTER_SCHEMA,
        **VELOCITY_MODE_TRANSITION,
        "applied": True,
        "normal_return": True,
    }:
        raise ValueError("counterfactual_velocity_mode_receipt_invalid")
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def build_frozen_v6_action_representation_contract(
    ledger: Mapping[str, Any],
) -> dict[str, Any]:
    """Pin the unambiguous adapter needed for v6's channel-only trace format."""
    actions = ledger.get("actions") if isinstance(ledger, Mapping) else None
    if not isinstance(actions, Sequence) or isinstance(actions, (str, bytes)):
        raise ValueError("counterfactual_action_layout_invalid")
    layout_counts = {
        specification["name"]: 0
        for specification in FROZEN_V6_ACTION_LAYOUT_SPECS.values()
    }
    effective_action_hashes = []
    expected_velocity_mode_switch_receipts = []
    velocity_transition_indices = []
    for action in actions:
        if not isinstance(action, Mapping):
            raise ValueError("counterfactual_action_layout_invalid")
        receipt = _effective_action_receipt(action)
        if receipt is None:
            raise ValueError("counterfactual_action_layout_invalid")
        layout = receipt["layout"]
        layout_counts[layout["name"]] += 1
        if layout["name"] == "full_velocity_9":
            velocities = action["action"]["joint_velocities"]
            if (
                not isinstance(velocities, list)
                or len(velocities) != len(FRANKA_DOF_NAMES)
                or velocities[VELOCITY_MODE_TRANSITION["dof_index"]]
                not in (-1.0, 0.0, 1.0)
                or any(
                    value is not None and index != VELOCITY_MODE_TRANSITION["dof_index"]
                    for index, value in enumerate(velocities)
                )
            ):
                raise ValueError("counterfactual_action_layout_invalid")
            velocity_transition_indices.append(action["source_transition_index"])
        mode_receipt = _velocity_mode_switch_receipt(receipt)
        if mode_receipt is not None:
            expected_velocity_mode_switch_receipts.append(mode_receipt)
        effective_action_hashes.append(receipt["sha256"])
    expected_counts = {
        specification["name"]: specification["count"]
        for specification in FROZEN_V6_ACTION_LAYOUT_SPECS.values()
    }
    expected_velocity_indices = list(
        range(
            VELOCITY_MODE_TRANSITION["source_transition_index"],
            VELOCITY_MODE_TRANSITION["source_transition_index"]
            + expected_counts["full_velocity_9"],
        )
    )
    if (
        layout_counts != expected_counts
        or velocity_transition_indices != expected_velocity_indices
        or len(effective_action_hashes) != 858
        or len(expected_velocity_mode_switch_receipts) != 1
    ):
        raise ValueError("counterfactual_action_layout_invalid")
    public = {
        "schema": ACTION_REPRESENTATION_ADAPTER_SCHEMA,
        "source_trace_omits_joint_indices": True,
        "layouts": EXPECTED_ACTION_REPRESENTATION_ADAPTER_CONFIG["action_layouts"],
        "layout_counts": layout_counts,
        "velocity_mode_transition": dict(VELOCITY_MODE_TRANSITION),
        "effective_action_count": len(effective_action_hashes),
        "effective_action_chain_sha256": _canonical_json_sha256(
            effective_action_hashes
        ),
    }
    return {
        "public": public,
        "effective_action_hashes": effective_action_hashes,
        "expected_velocity_mode_switch_receipts": (
            expected_velocity_mode_switch_receipts
        ),
    }


def validate_live_replay_robot_identity(
    *,
    dof_names: Sequence[str],
    joint_positions: Any,
    finger_joint_indices: Sequence[int],
    task_robot_matches: bool,
    robot_usd_path: str | os.PathLike[str],
    robot_usd_sha256: str,
) -> dict[str, Any]:
    try:
        names = tuple(str(name) for name in dof_names)
        positions = np.asarray(joint_positions, dtype=np.float64)
        finger_indices = tuple(int(index) for index in finger_joint_indices)
        usd_path = Path(robot_usd_path).resolve()
    except (TypeError, ValueError) as exc:
        raise ValueError("counterfactual_live_robot_identity_invalid") from exc
    if not (
        names == FRANKA_DOF_NAMES
        and positions.shape == (len(FRANKA_DOF_NAMES),)
        and np.isfinite(positions).all()
        and finger_indices == (7, 8)
        and task_robot_matches is True
        and usd_path == (REPO_ROOT / EXPECTED_ROBOT_USD_RELATIVE_PATH).resolve()
        and robot_usd_sha256 == EXPECTED_ROBOT_USD_SHA256
    ):
        raise ValueError("counterfactual_live_robot_identity_invalid")
    payload = {
        "dof_names": list(names),
        "dof_count": len(names),
        "joint_positions": positions.tolist(),
        "finger_joint_indices": list(finger_indices),
        "task_robot_identity": True,
        "robot_usd_path": str(usd_path),
        "robot_usd_sha256": robot_usd_sha256,
    }
    return {**payload, "sha256": _canonical_json_sha256(payload), "valid": True}


def build_live_replay_robot_stage_binding(stage: Any) -> dict[str, Any]:
    """Bind the live robot composition to the pinned local Franka root USD."""
    root = stage.GetPrimAtPath(ROBOT_ROOT_PATH)
    if not root or not root.IsValid():
        raise ValueError("counterfactual_live_robot_stage_binding_invalid")
    layers = []
    expected_path = (REPO_ROOT / EXPECTED_ROBOT_USD_RELATIVE_PATH).resolve()
    pinned_root_layer_found = False
    for specification in root.GetPrimStack():
        layer = specification.layer
        real_path = str(getattr(layer, "realPath", "") or "")
        record = {"real_path": real_path}
        if real_path:
            resolved = Path(real_path).resolve()
            record["real_path"] = str(resolved)
            if resolved.is_file():
                record["sha256"] = sha256_file(resolved)
                if (
                    resolved == expected_path
                    and record["sha256"] == EXPECTED_ROBOT_USD_SHA256
                ):
                    pinned_root_layer_found = True
        layers.append(record)
    if not pinned_root_layer_found:
        raise ValueError("counterfactual_live_robot_stage_binding_invalid")
    payload = {
        "robot_root_path": ROBOT_ROOT_PATH,
        "pinned_root_usd_path": str(expected_path),
        "pinned_root_usd_sha256": EXPECTED_ROBOT_USD_SHA256,
        "prim_stack_layers": layers,
        "pinned_root_layer_found": True,
    }
    return {**payload, "sha256": _canonical_json_sha256(payload), "valid": True}


def validate_live_replay_robot_stage_binding_evidence(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("counterfactual_live_robot_stage_binding_invalid")
    payload = dict(value)
    digest = payload.pop("sha256", None)
    valid = payload.pop("valid", None)
    expected_path = str((REPO_ROOT / EXPECTED_ROBOT_USD_RELATIVE_PATH).resolve())
    layers = payload.get("prim_stack_layers")
    if (
        valid is not True
        or payload.get("robot_root_path") != ROBOT_ROOT_PATH
        or payload.get("pinned_root_usd_path") != expected_path
        or payload.get("pinned_root_usd_sha256") != EXPECTED_ROBOT_USD_SHA256
        or payload.get("pinned_root_layer_found") is not True
        or not isinstance(layers, list)
        or not any(
            isinstance(layer, Mapping)
            and layer.get("real_path") == expected_path
            and layer.get("sha256") == EXPECTED_ROBOT_USD_SHA256
            for layer in layers
        )
        or digest != _canonical_json_sha256(payload)
    ):
        raise ValueError("counterfactual_live_robot_stage_binding_invalid")


def _gain_vector(value: Any) -> np.ndarray:
    try:
        gains = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("counterfactual_velocity_mode_readback_invalid") from exc
    if gains.shape != (len(FRANKA_DOF_NAMES),) or not np.isfinite(gains).all():
        raise ValueError("counterfactual_velocity_mode_readback_invalid")
    return gains


def build_velocity_mode_gain_readback(
    *,
    before_stiffness: Any,
    before_damping: Any,
    after_stiffness: Any,
    after_damping: Any,
) -> dict[str, Any]:
    before_kps = _gain_vector(before_stiffness)
    before_kds = _gain_vector(before_damping)
    after_kps = _gain_vector(after_stiffness)
    after_kds = _gain_vector(after_damping)
    dof_index = VELOCITY_MODE_TRANSITION["dof_index"]
    other_indices = [
        index for index in range(len(FRANKA_DOF_NAMES)) if index != dof_index
    ]
    other_before = {
        "stiffness": before_kps[other_indices].tolist(),
        "damping": before_kds[other_indices].tolist(),
    }
    other_after = {
        "stiffness": after_kps[other_indices].tolist(),
        "damping": after_kds[other_indices].tolist(),
    }
    other_unchanged = bool(
        np.array_equal(before_kps[other_indices], after_kps[other_indices])
        and np.array_equal(before_kds[other_indices], after_kds[other_indices])
    )
    payload = {
        "schema": ACTION_REPRESENTATION_ADAPTER_SCHEMA,
        **VELOCITY_MODE_TRANSITION,
        "dof_name": FRANKA_DOF_NAMES[dof_index],
        "readback_api": "articulation_controller.get_gains",
        "pre_switch_dof_stiffness": float(before_kps[dof_index]),
        "pre_switch_dof_damping": float(before_kds[dof_index]),
        "post_switch_dof_stiffness": float(after_kps[dof_index]),
        "post_switch_dof_damping": float(after_kds[dof_index]),
        "other_dof_gains_before_sha256": _canonical_json_sha256(other_before),
        "other_dof_gains_after_sha256": _canonical_json_sha256(other_after),
        "other_dof_gains_unchanged": other_unchanged,
    }
    if not (
        before_kps[dof_index] > 0.0
        and before_kds[dof_index] > 0.0
        and math.isclose(
            float(after_kps[dof_index]), 0.0, rel_tol=0.0, abs_tol=1.0e-8
        )
        and math.isclose(
            float(after_kds[dof_index]),
            float(before_kds[dof_index]),
            rel_tol=0.0,
            abs_tol=1.0e-8,
        )
        and other_unchanged
    ):
        raise ValueError("counterfactual_velocity_mode_readback_invalid")
    return {**payload, "sha256": _canonical_json_sha256(payload), "valid": True}


def validate_velocity_mode_gain_readback(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("counterfactual_velocity_mode_readback_invalid")
    payload = dict(value)
    digest = payload.pop("sha256", None)
    valid = payload.pop("valid", None)
    scalar_keys = (
        "pre_switch_dof_stiffness",
        "pre_switch_dof_damping",
        "post_switch_dof_stiffness",
        "post_switch_dof_damping",
    )
    scalars = [payload.get(key) for key in scalar_keys]
    if not (
        valid is True
        and payload.get("schema") == ACTION_REPRESENTATION_ADAPTER_SCHEMA
        and payload.get("source_transition_index")
        == VELOCITY_MODE_TRANSITION["source_transition_index"]
        and payload.get("dof_index") == VELOCITY_MODE_TRANSITION["dof_index"]
        and payload.get("mode") == VELOCITY_MODE_TRANSITION["mode"]
        and payload.get("dof_name") == FRANKA_DOF_NAMES[6]
        and payload.get("readback_api") == "articulation_controller.get_gains"
        and all(
            isinstance(scalar, (int, float))
            and not isinstance(scalar, bool)
            and math.isfinite(float(scalar))
            for scalar in scalars
        )
        and float(payload["pre_switch_dof_stiffness"]) > 0.0
        and float(payload["pre_switch_dof_damping"]) > 0.0
        and math.isclose(
            float(payload["post_switch_dof_stiffness"]),
            0.0,
            rel_tol=0.0,
            abs_tol=1.0e-8,
        )
        and math.isclose(
            float(payload["post_switch_dof_damping"]),
            float(payload["pre_switch_dof_damping"]),
            rel_tol=0.0,
            abs_tol=1.0e-8,
        )
        and _is_sha256(payload.get("other_dof_gains_before_sha256"))
        and payload.get("other_dof_gains_before_sha256")
        == payload.get("other_dof_gains_after_sha256")
        and payload.get("other_dof_gains_unchanged") is True
        and digest == _canonical_json_sha256(payload)
    ):
        raise ValueError("counterfactual_velocity_mode_readback_invalid")


def _velocity_mode_gain_readback_is_valid(value: Any) -> bool:
    try:
        validate_velocity_mode_gain_readback(value)
    except ValueError:
        return False
    return True


def _read_articulation_controller_gains(
    articulation_controller: Any,
) -> tuple[np.ndarray, np.ndarray]:
    getter = getattr(articulation_controller, "get_gains", None)
    if not callable(getter):
        raise RuntimeError("counterfactual_velocity_mode_readback_api_missing")
    values = getter()
    if not isinstance(values, tuple) or len(values) != 2:
        raise RuntimeError("counterfactual_velocity_mode_readback_invalid")
    try:
        return _gain_vector(values[0]), _gain_vector(values[1])
    except ValueError as exc:
        raise RuntimeError("counterfactual_velocity_mode_readback_invalid") from exc


def _required_event(value: Any, *, name: str, maximum: int) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"counterfactual_source_{name}_invalid")
    return value


def load_frozen_action_ledger(
    trace_path: str | os.PathLike[str],
    *,
    expected_sha256: str,
) -> dict[str, Any]:
    """Load only verified raw actions from the immutable v6 trace."""
    path = Path(trace_path)
    if not path.is_file() or not _is_sha256(expected_sha256):
        raise ValueError("counterfactual_source_trace_invalid")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError("counterfactual_source_trace_sha256_mismatch")

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("counterfactual_source_trace_invalid") from exc
    if not lines:
        raise ValueError("counterfactual_source_trace_invalid")
    try:
        records = [json.loads(line) for line in lines]
    except json.JSONDecodeError as exc:
        raise ValueError("counterfactual_source_trace_invalid") from exc
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError("counterfactual_source_trace_invalid")

    bootstrap = records[0]
    if (
        bootstrap.get("kind") != "bootstrap"
        or bootstrap.get("manifest_type") != SOURCE_TRACE_MANIFEST_TYPE
    ):
        raise ValueError("counterfactual_source_trace_identity_invalid")
    runtime = bootstrap.get("payload", {}).get("runtime_evidence")
    if not isinstance(runtime, Mapping):
        raise ValueError("counterfactual_source_trace_identity_invalid")
    protocol = runtime.get("protocol")
    static_identity = runtime.get("child_static_identity_post")
    if (
        not isinstance(protocol, Mapping)
        or protocol.get("protocol_id") != SOURCE_PROTOCOL_ID
        or not isinstance(static_identity, Mapping)
        or static_identity.get("config_sha256") != SOURCE_CONFIG_SHA256
    ):
        raise ValueError("counterfactual_source_trace_identity_invalid")

    transitions: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    expected_transition_index = 0
    expected_apply_index = 0
    terminal_seen = False
    for record in records[1:]:
        if record.get("kind") != "transition":
            continue
        if record.get("manifest_type") != SOURCE_TRACE_MANIFEST_TYPE:
            raise ValueError("counterfactual_source_trace_identity_invalid")
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("counterfactual_source_transition_invalid")
        transition_index = payload.get("transition_index")
        if transition_index != expected_transition_index:
            raise ValueError("counterfactual_source_transition_index_invalid")
        expected_transition_index += 1
        action = payload.get("action")
        apply_count = payload.get("apply_count")
        receipt = payload.get("action_receipt")
        canonical = payload.get("canonical_action")
        apply_index = payload.get("apply_index")
        integrating_transition_index = payload.get("integrating_transition_index")
        pick_event = _required_event(
            payload.get("pick_event"), name="pick_event", maximum=6
        )
        pour_event = _required_event(
            payload.get("pour_event"), name="pour_event", maximum=5
        )
        if action is None:
            if (
                apply_count != 0
                or receipt is not None
                or canonical is not None
                or apply_index is not None
                or integrating_transition_index is not None
            ):
                raise ValueError("counterfactual_source_action_receipt_invalid")
            normalised_action = None
            action_sha256 = None
        else:
            if terminal_seen:
                raise ValueError("counterfactual_source_post_terminal_action")
            normalised_action = _normalise_action(action)
            expected_canonical = canonicalize_action(normalised_action)
            if (
                canonical != expected_canonical
                or not isinstance(receipt, Mapping)
                or receipt.get("applied") is not True
                or receipt.get("normal_return") is not True
                or receipt.get("apply_count") != 1
                or receipt.get("action_sha256") != expected_canonical["sha256"]
                or apply_count != 1
                or apply_index != expected_apply_index
                or integrating_transition_index != transition_index + 1
            ):
                raise ValueError("counterfactual_source_action_receipt_invalid")
            action_sha256 = expected_canonical["sha256"]
            actions.append(
                {
                    "source_transition_index": transition_index,
                    "source_apply_index": expected_apply_index,
                    "action": normalised_action,
                    "action_sha256": action_sha256,
                    "pick_event": pick_event,
                    "pour_event": pour_event,
                }
            )
            expected_apply_index += 1
        transition = {
            "source_transition_index": transition_index,
            "source_apply_index": apply_index,
            "integrating_transition_index": integrating_transition_index,
            "action": normalised_action,
            "action_sha256": action_sha256,
            "pick_event": pick_event,
            "pour_event": pour_event,
            "source_terminal": payload.get("production_terminal") is True,
        }
        transitions.append(transition)
        terminal_seen = bool(terminal_seen or transition["source_terminal"])
    if not transitions or not actions:
        raise ValueError("counterfactual_source_actions_missing")
    if not any(action["pick_event"] == 4 for action in actions):
        raise ValueError("counterfactual_source_close_action_missing")
    if not any(action["pick_event"] == 5 for action in actions):
        raise ValueError("counterfactual_source_lift_action_missing")
    if not any(action["pour_event"] == 2 for action in actions):
        raise ValueError("counterfactual_source_pour_action_missing")
    if any(
        action["source_transition_index"] + 1 >= len(transitions)
        for action in actions
    ):
        raise ValueError("counterfactual_source_final_action_unintegrated")
    return {
        "source_trace_path": str(path.resolve()),
        "source_trace_sha256": actual_sha256,
        "source_protocol_id": SOURCE_PROTOCOL_ID,
        "source_config_sha256": SOURCE_CONFIG_SHA256,
        "transition_count": len(transitions),
        "action_count": len(actions),
        "transitions": transitions,
        "actions": actions,
    }


def build_replay_intervals(ledger: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Preserve v6's step-then-apply command timing exactly.

    A source action emitted at transition ``k`` is applied after that transition
    and therefore integrates during transition ``k + 1``. The first interval
    intentionally integrates no action.
    """
    transitions = ledger.get("transitions") if isinstance(ledger, Mapping) else None
    if not isinstance(transitions, Sequence) or isinstance(
        transitions, (str, bytes)
    ):
        raise ValueError("counterfactual_replay_schedule_invalid")
    result: list[dict[str, Any]] = []
    for index, source_transition in enumerate(transitions):
        if (
            not isinstance(source_transition, Mapping)
            or source_transition.get("source_transition_index") != index
        ):
            raise ValueError("counterfactual_replay_schedule_invalid")
        active = None if index == 0 else transitions[index - 1]
        if active is not None:
            if not isinstance(active, Mapping):
                raise ValueError("counterfactual_replay_schedule_invalid")
            action = active.get("action")
            if action is not None and active.get("integrating_transition_index") != index:
                raise ValueError("counterfactual_replay_schedule_invalid")
        result.append(
            {
                "source_transition": dict(source_transition),
                "integrated_source_transition": (
                    None if active is None else dict(active)
                ),
            }
        )
    if not result:
        raise ValueError("counterfactual_replay_schedule_invalid")
    return result


class FrozenReplayState:
    """Expose only source-ledger phase facts to the passive contact monitor."""

    def __init__(self) -> None:
        self._close_requested = False
        self._lift_requested = False
        self._pour_rotation_requested = False
        self._source_terminal_seen = False

    def advance(self, transition: Mapping[str, Any]) -> None:
        pick_event = transition.get("pick_event")
        pour_event = transition.get("pour_event")
        if pick_event == 4:
            self._close_requested = True
        if pick_event == 5:
            self._lift_requested = True
        if pour_event == 2:
            self._pour_rotation_requested = True
        self._source_terminal_seen = bool(
            self._source_terminal_seen or transition.get("source_terminal") is True
        )

    def online_fluid_grasp_attachment_requested(self) -> bool:
        return False

    def online_fluid_grasp_contact_requested(self) -> bool:
        return self._close_requested

    def online_fluid_grasp_lift_requested(self) -> bool:
        return self._lift_requested

    def pour_rotation_requested(self) -> bool:
        return self._pour_rotation_requested

    def snapshot(self) -> dict[str, Any]:
        return {
            "close_requested": self._close_requested,
            "lift_requested": self._lift_requested,
            "pour_rotation_requested": self._pour_rotation_requested,
            "source_terminal_seen": self._source_terminal_seen,
            "contact_grasp_claimed": False,
            "mechanical_attachment_requested": False,
        }


def _mapping_value(value: Any, key: str) -> Any:
    if not isinstance(value, Mapping):
        raise ValueError("counterfactual_config_invalid")
    return value.get(key)


def validate_counterfactual_config(
    config: Mapping[str, Any],
    *,
    config_path: str | os.PathLike[str],
) -> dict[str, Any]:
    """Fail closed on every setting that could turn this into a normal run."""
    if not isinstance(config, Mapping):
        raise ValueError("counterfactual_config_invalid")
    if config.get("controller_type") != "frozen_v6_counterfactual_replay":
        raise ValueError("counterfactual_controller_type_invalid")
    if config.get("mode") != "collect" or config.get("max_episodes") != 1:
        raise ValueError("counterfactual_episode_contract_invalid")
    fluid = config.get("online_fluid")
    counterfactual = config.get("counterfactual")
    if not isinstance(fluid, Mapping) or not isinstance(counterfactual, Mapping):
        raise ValueError("counterfactual_config_invalid")
    if (
        fluid.get("enabled") is not True
        or fluid.get("expert_control_profile") != "native_expert_v1"
        or fluid.get("execution_mode") != "production_pour_v1"
        or fluid.get("source_ownership") != "contact_friction_dynamic_v1"
        or fluid.get("source_pose_authority") != "physx_dynamic_readback_v1"
    ):
        raise ValueError("counterfactual_dynamic_source_contract_invalid")
    forbidden_attachment_keys = {
        "attachment_matrix_policy",
        "expert_attachment",
        "gripper_frame_path",
        "synthetic_attachment_collision_filter_root_path",
    }
    if forbidden_attachment_keys.intersection(fluid):
        raise ValueError("counterfactual_attachment_controls_forbidden")
    try:
        physics_dt = float(fluid["physics_dt"])
        rendering_dt = float(fluid["rendering_dt"])
        substeps = int(fluid["physics_substeps_per_observation"])
        particle_count = int(fluid["expected_particle_count"])
        attempts = int(fluid["max_attempts"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("counterfactual_timing_invalid") from exc
    if (
        not math.isclose(physics_dt, 1.0 / 600.0, rel_tol=0.0, abs_tol=1.0e-15)
        or not math.isclose(rendering_dt, 1.0 / 60.0, rel_tol=0.0, abs_tol=1.0e-15)
        or substeps != 10
        or not math.isclose(
            physics_dt * substeps,
            rendering_dt,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
    ):
        raise ValueError("counterfactual_action_cadence_invalid")
    if particle_count != 3600 or attempts != 1:
        raise ValueError("counterfactual_pbd_contract_invalid")
    if counterfactual.get("protocol_id") != MANIFEST_TYPE:
        raise ValueError("counterfactual_protocol_id_invalid")
    if counterfactual.get("forced_status") != FORCED_STATUS:
        raise ValueError("counterfactual_forced_status_invalid")
    if (
        counterfactual.get("trajectory_claim")
        != "exact_v6_serialized_action_channel_replay_with_pinned_representation_adapter"
        or counterfactual.get("scene_equivalence_claim_allowed") is not False
    ):
        raise ValueError("counterfactual_claim_boundary_invalid")
    if (
        counterfactual.get("action_representation_adapter")
        != EXPECTED_ACTION_REPRESENTATION_ADAPTER_CONFIG
    ):
        raise ValueError("counterfactual_action_adapter_config_invalid")
    if (
        counterfactual.get("source_protocol_id") != SOURCE_PROTOCOL_ID
        or counterfactual.get("source_config_sha256") != SOURCE_CONFIG_SHA256
        or counterfactual.get("source_trace_sha256")
        != EXPECTED_SOURCE_TRACE_SHA256
        or counterfactual.get("source_transition_count") != 864
        or counterfactual.get("source_action_count") != 858
    ):
        raise ValueError("counterfactual_source_trace_identity_invalid")
    if (
        counterfactual.get("command_frequency_hz") != 60
        or counterfactual.get("video_fps") != 30
        or counterfactual.get("video_sample_every_transitions") != 2
        or counterfactual.get("video_sampling_policy") != VIDEO_SAMPLING_POLICY
    ):
        raise ValueError("counterfactual_video_cadence_invalid")
    trace_value = counterfactual.get("source_trace")
    if not isinstance(trace_value, str):
        raise ValueError("counterfactual_source_trace_path_invalid")
    trace_relative = Path(trace_value)
    if trace_relative.is_absolute() or ".." in trace_relative.parts:
        raise ValueError("counterfactual_source_trace_path_invalid")
    if trace_relative != EXPECTED_SOURCE_TRACE_RELATIVE_PATH:
        raise ValueError("counterfactual_source_trace_path_invalid")
    trace_path = (REPO_ROOT / trace_relative).resolve()
    if not trace_path.is_file():
        raise ValueError("counterfactual_source_trace_missing")
    robot = config.get("robot")
    if (
        not isinstance(robot, Mapping)
        or robot.get("type") != "franka"
        or robot.get("usd_path") != str(EXPECTED_ROBOT_USD_RELATIVE_PATH)
    ):
        raise ValueError("counterfactual_robot_contract_invalid")
    if Path(config_path).resolve() != DEFAULT_CONFIG.resolve():
        raise ValueError("counterfactual_config_path_invalid")
    return {
        "valid": True,
        "config_path": str(Path(config_path).resolve()),
        "config_sha256": sha256_file(config_path),
        "source_trace_path": str(trace_path),
        "source_trace_sha256": EXPECTED_SOURCE_TRACE_SHA256,
        "physics_dt": physics_dt,
        "rendering_dt": rendering_dt,
        "physics_substeps_per_observation": substeps,
        "expected_particle_count": particle_count,
        "command_frequency_hz": 60,
        "video_fps": 30,
        "video_sample_every_transitions": 2,
        "action_representation_adapter_schema": ACTION_REPRESENTATION_ADAPTER_SCHEMA,
    }


def build_hd_presentation_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    """Pin the existing model-camera views used for an opt-in HD derivative."""
    cameras = config.get("cameras") if isinstance(config, Mapping) else None
    if not isinstance(cameras, list) or len(cameras) != len(
        HD_PRESENTATION_CAMERA_SPECS
    ):
        raise ValueError("counterfactual_hd_presentation_camera_contract_invalid")
    expected_names = [name for name, _ in HD_PRESENTATION_CAMERA_SPECS]
    expected_paths = dict(HD_PRESENTATION_CAMERA_SPECS)
    if [camera.get("name") if isinstance(camera, Mapping) else None for camera in cameras] != expected_names:
        raise ValueError("counterfactual_hd_presentation_camera_contract_invalid")
    for camera in cameras:
        if not isinstance(camera, Mapping):
            raise ValueError("counterfactual_hd_presentation_camera_contract_invalid")
        name = camera.get("name")
        if (
            camera.get("prim_path") != expected_paths.get(name)
            or camera.get("resolution") != [256, 256]
            or camera.get("focal_length") != 16
            or camera.get("frequency") != 60
            or camera.get("clipping_range") != [0.01, 100.0]
            or camera.get("image_type") != "rgb"
        ):
            raise ValueError("counterfactual_hd_presentation_camera_contract_invalid")
    return {
        "schema": HD_PRESENTATION_SCHEMA,
        "capture_policy": HD_PRESENTATION_CAPTURE_POLICY,
        "camera_names": expected_names,
        "source_prim_paths": expected_paths,
        "resolution": [HD_PRESENTATION_WIDTH, HD_PRESENTATION_HEIGHT],
        "fps": HD_PRESENTATION_FPS,
        "framing": "preserve_vertical_fov",
        "banner_lines": list(HD_PRESENTATION_BANNER_LINES),
        "raw_directory": HD_PRESENTATION_RAW_DIRECTORY,
        "final_directory": HD_PRESENTATION_FINAL_DIRECTORY,
    }


def _escape_ffmpeg_filter_text(value: str) -> str:
    return value.replace("\\", r"\\").replace(":", r"\:").replace(",", r"\,")


def build_hd_presentation_ffmpeg_command(
    *, raw_path: str | os.PathLike[str], output_path: str | os.PathLike[str]
) -> list[str]:
    """Create a deterministic, create-only browser-video command."""
    font_path = str(HD_PRESENTATION_FONT_PATH)
    first_line, second_line = (
        _escape_ffmpeg_filter_text(value) for value in HD_PRESENTATION_BANNER_LINES
    )
    video_filter = (
        "drawbox="
        f"x=0:y=0:w=iw:h={HD_PRESENTATION_BANNER_HEIGHT}:"
        f"color={HD_PRESENTATION_BANNER_COLOR}:t=fill,"
        "drawtext="
        f"fontfile={font_path}:text={first_line}:fontcolor=white:"
        "fontsize=28:x=24:y=8,"
        "drawtext="
        f"fontfile={font_path}:text={second_line}:fontcolor=white:"
        "fontsize=18:x=24:y=43"
    )
    return [
        "ffmpeg",
        "-n",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(raw_path),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(HD_PRESENTATION_FPS),
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _valid_velocity_mode_switch_receipt(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    payload = dict(value)
    digest = payload.pop("sha256", None)
    return bool(
        payload
        == {
            "schema": ACTION_REPRESENTATION_ADAPTER_SCHEMA,
            **VELOCITY_MODE_TRANSITION,
            "applied": True,
            "normal_return": True,
        }
        and digest == _canonical_json_sha256(payload)
    )


def build_terminal_contract(
    *,
    ledger: Mapping[str, Any],
    applied_action_hashes: Sequence[str],
    applied_effective_action_hashes: Sequence[str],
    expected_effective_action_hashes: Sequence[str],
    applied_velocity_mode_switch_receipts: Sequence[Mapping[str, Any]],
    expected_velocity_mode_switch_receipts: Sequence[Mapping[str, Any]],
    velocity_mode_gain_readbacks: Sequence[Mapping[str, Any]],
    attachment: Mapping[str, Any],
    particle_readback_observation_count: int,
) -> dict[str, Any]:
    """Make success impossible while still exposing runtime-integrity failures."""
    actions = ledger.get("actions") if isinstance(ledger, Mapping) else None
    if not isinstance(actions, Sequence) or isinstance(actions, (str, bytes)):
        raise ValueError("counterfactual_terminal_ledger_invalid")
    expected_hashes = [
        item.get("action_sha256") if isinstance(item, Mapping) else None
        for item in actions
    ]
    if not all(_is_sha256(value) for value in expected_hashes):
        raise ValueError("counterfactual_terminal_ledger_invalid")
    if not (
        all(_is_sha256(value) for value in applied_effective_action_hashes)
        and all(_is_sha256(value) for value in expected_effective_action_hashes)
        and all(
            _valid_velocity_mode_switch_receipt(value)
            for value in applied_velocity_mode_switch_receipts
        )
        and all(
            _valid_velocity_mode_switch_receipt(value)
            for value in expected_velocity_mode_switch_receipts
        )
        and all(
            _velocity_mode_gain_readback_is_valid(value)
            for value in velocity_mode_gain_readbacks
        )
    ):
        raise ValueError("counterfactual_terminal_effective_action_invalid")
    if not isinstance(attachment, Mapping):
        raise ValueError("counterfactual_terminal_attachment_invalid")
    writer_audit = attachment.get("source_writer_audit")
    writer_audit = writer_audit if isinstance(writer_audit, Mapping) else {}
    zero_write_values = (
        attachment.get("source_pose_write_count_after_play"),
        attachment.get("source_velocity_write_count_after_play"),
        attachment.get("object_utils_source_position_write_count_after_play"),
        attachment.get("kinematic_target_update_count"),
    )
    zero_source_writes = bool(
        all(type(value) is int and value == 0 for value in zero_write_values)
        and writer_audit.get("valid") is True
    )
    failure_reason = attachment.get("failure_reason")
    checks = {
        "all_source_actions_applied_exactly_once": list(applied_action_hashes)
        == expected_hashes,
        "all_effective_actions_applied_exactly_once": (
            list(applied_effective_action_hashes)
            == list(expected_effective_action_hashes)
        ),
        "velocity_mode_transition_applied_exactly_once": (
            list(applied_velocity_mode_switch_receipts)
            == list(expected_velocity_mode_switch_receipts)
        ),
        "velocity_mode_readback_verified": len(velocity_mode_gain_readbacks) == 1,
        "dynamic_source": (
            attachment.get("mode") == "contact_friction_dynamic_v1"
            and attachment.get("source_dynamic") is True
        ),
        "mechanical_attachment_unused": (
            attachment.get("mechanical_attachment_used") is False
        ),
        "zero_source_writes": zero_source_writes,
        "particle_readback_observed": (
            type(particle_readback_observation_count) is int
            and particle_readback_observation_count >= 2
        ),
        "first_latched_failure_captured": (
            isinstance(failure_reason, str) and bool(failure_reason)
        ),
    }
    integrity_valid = all(checks.values())
    return {
        "status": FORCED_STATUS if integrity_valid else RUNTIME_INTEGRITY_FAILURE,
        "success": False,
        "expert_episode_accepted": False,
        "collector_write_allowed": False,
        "ebench_finalize_allowed": False,
        "contact_grasp_claimed": False,
        "trajectory_repair_applied": False,
        "scene_equivalence_claim_allowed": False,
        "integrity_valid": integrity_valid,
        "integrity_checks": checks,
        "first_latched_failure_reason": failure_reason,
        "source_write_evidence_scope": (
            "zero calls across SourceBodyWriterAudit instrumented surfaces; "
            "raw USD attribute writes, plural prim-view setters, and replacement "
            "objects are outside scope"
        ),
        "source_action_count": len(expected_hashes),
        "applied_action_count": len(applied_action_hashes),
        "effective_action_count": len(expected_effective_action_hashes),
        "applied_effective_action_count": len(applied_effective_action_hashes),
    }


def _artifact_record(path: Path, *, output_dir: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(output_dir)),
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _write_trace_line(stream: Any, value: Mapping[str, Any]) -> None:
    stream.write(
        json.dumps(
            _json_native(value),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    stream.write("\n")
    stream.flush()


def _articulation_action_from_raw(action: Mapping[str, Any]) -> Any:
    from isaacsim.core.utils.types import ArticulationAction

    raw = _normalise_action(action)
    layout = _frozen_v6_action_layout_from_raw(raw)
    return ArticulationAction(
        joint_positions=raw["joint_positions"],
        joint_velocities=raw["joint_velocities"],
        joint_efforts=raw["joint_efforts"],
        joint_indices=(
            None
            if layout["joint_indices"] is None
            else np.asarray(layout["joint_indices"], dtype=np.int64)
        ),
    )


def _capture_counterfactual_frame(
    *,
    state: Mapping[str, Any],
    record: Mapping[str, Any],
    source_transition: Mapping[str, Any] | None,
    integrated_source_transition: Mapping[str, Any] | None,
    replay_state: FrozenReplayState,
    attachment: Mapping[str, Any],
    writer: Any,
    frame_map: list[dict[str, Any]],
    camera_keys: Sequence[str],
    camera_shape: Sequence[int],
    replay_elapsed_seconds: float,
) -> None:
    import cv2

    from utils.fluid_evaluation_loop import model_camera_video_rgb

    normal_provenance = _surface_normal_provenance_from_record(record)
    geometry_sha256 = _surface_geometry_sha256_from_record(record)
    render = record.get("render")
    if not isinstance(render, Mapping) or not _is_sha256(render.get("render_token")):
        raise ValueError("counterfactual_video_render_token_invalid")
    rgb = model_camera_video_rgb(
        state,
        camera_keys=tuple(camera_keys),
        expected_shape=tuple(camera_shape),
    )
    image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    cv2.rectangle(image, (0, 0), (image.shape[1], 34), (0, 0, 110), -1)
    cv2.putText(
        image,
        "UNSAFE VISUAL-ONLY COUNTERFACTUAL | NOT A SUCCESS",
        (6, 15),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    failure = attachment.get("failure_reason")
    failure_text = "monitor: " + (
        str(failure) if isinstance(failure, str) and failure else "no-latched-failure"
    )
    cv2.putText(
        image,
        failure_text[:95],
        (6, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.32,
        (210, 230, 255),
        1,
        cv2.LINE_AA,
    )
    writer.write(image)
    if not math.isfinite(replay_elapsed_seconds) or replay_elapsed_seconds < 0.0:
        raise ValueError("counterfactual_video_time_invalid")
    frame_map.append(
        {
            "frame_index": len(frame_map),
            "observation_index": int(record["observation_index"]),
            "frame_identity": str(record["frame_identity"]),
            "render_token": str(render["render_token"]),
            "integration_step_after": int(record["integration_step_after"]),
            "logical_step_after": int(record["logical_step_after"]),
            "particle_position_sha256": str(record["position_sha256"]),
            "source_transition_index": (
                None
                if source_transition is None
                else int(source_transition["source_transition_index"])
            ),
            "source_action_sha256": (
                None
                if source_transition is None
                else source_transition["action_sha256"]
            ),
            "source_transition_processed_after_observation": source_transition is not None,
            "integrated_source_transition_index": (
                None
                if integrated_source_transition is None
                else int(integrated_source_transition["source_transition_index"])
            ),
            "integrated_source_action_sha256": (
                None
                if integrated_source_transition is None
                else integrated_source_transition["action_sha256"]
            ),
            "replay_elapsed_seconds": float(replay_elapsed_seconds),
            "surface_normal_provenance": normal_provenance,
            "surface_geometry_sha256": geometry_sha256,
            "monitor_failure_reason": failure,
            "replay_state": replay_state.snapshot(),
        }
    )


def build_hd_presentation_binding_map(
    video_frame_map: Mapping[str, Any],
) -> dict[str, Any]:
    frames = video_frame_map.get("frames") if isinstance(video_frame_map, Mapping) else None
    if not isinstance(frames, list):
        raise ValueError("counterfactual_hd_presentation_binding_invalid")
    payload = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "forced_status": FORCED_STATUS,
        "capture_policy": HD_PRESENTATION_CAPTURE_POLICY,
        "frame_count": len(frames),
        "frames": [
            {
                "frame_index": frame.get("frame_index"),
                "source_transition_index": frame.get("source_transition_index"),
                "observation_index": frame.get("observation_index"),
                "frame_identity": frame.get("frame_identity"),
                "render_token": frame.get("render_token"),
                "integration_step_after": frame.get("integration_step_after"),
                "logical_step_after": frame.get("logical_step_after"),
                "camera_frame_ordinals": {
                    name: frame.get("frame_index")
                    for name, _ in HD_PRESENTATION_CAMERA_SPECS
                },
            }
            for frame in frames
            if isinstance(frame, Mapping)
        ],
    }
    validate_hd_presentation_binding_map(payload, video_frame_map=video_frame_map)
    return payload


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("counterfactual_hd_presentation_recorder_invalid") from exc
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError("counterfactual_hd_presentation_recorder_invalid")
    return [dict(record) for record in records]


def _probe_video(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-count_frames",
        "-show_entries",
        (
            "stream=codec_type,codec_name,pix_fmt,width,height,"
            "r_frame_rate,avg_frame_rate,nb_read_frames"
        ),
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"counterfactual_hd_ffprobe_failed:{completed.stderr.strip()}")
    try:
        streams = json.loads(completed.stdout).get("streams")
    except json.JSONDecodeError as exc:
        raise RuntimeError("counterfactual_hd_ffprobe_invalid") from exc
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], Mapping):
        raise RuntimeError("counterfactual_hd_ffprobe_invalid")
    stream = streams[0]
    frame_count = stream.get("nb_read_frames")
    try:
        decoded_frame_count = int(frame_count)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("counterfactual_hd_ffprobe_invalid") from exc
    return {
        "stream_count": len(streams),
        "codec_type": stream.get("codec_type"),
        "codec_name": stream.get("codec_name"),
        "pixel_format": stream.get("pix_fmt"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "frame_rate": stream.get("r_frame_rate"),
        "average_frame_rate": stream.get("avg_frame_rate"),
        "decoded_frame_count": decoded_frame_count,
    }


def _validate_hd_video_probe(
    value: Mapping[str, Any],
    *,
    final_h264: bool,
) -> None:
    if (
        value.get("stream_count") != 1
        or value.get("codec_type") != "video"
        or value.get("width") != HD_PRESENTATION_WIDTH
        or value.get("height") != HD_PRESENTATION_HEIGHT
        or value.get("frame_rate") != f"{HD_PRESENTATION_FPS}/1"
        or value.get("average_frame_rate") != f"{HD_PRESENTATION_FPS}/1"
        or value.get("decoded_frame_count") != 433
        or (final_h264 and value.get("codec_name") != "h264")
        or (final_h264 and value.get("pixel_format") != "yuv420p")
    ):
        raise ValueError("counterfactual_hd_presentation_video_invalid")


def _has_faststart_moov_before_mdat(path: Path) -> bool:
    try:
        total_size = path.stat().st_size
        with path.open("rb") as stream:
            offset = 0
            atom_order: list[bytes] = []
            while offset + 8 <= total_size and len(atom_order) < 64:
                stream.seek(offset)
                header = stream.read(8)
                if len(header) != 8:
                    return False
                atom_size = int.from_bytes(header[:4], "big")
                atom_type = header[4:]
                header_size = 8
                if atom_size == 1:
                    extended = stream.read(8)
                    if len(extended) != 8:
                        return False
                    atom_size = int.from_bytes(extended, "big")
                    header_size = 16
                elif atom_size == 0:
                    atom_size = total_size - offset
                if atom_size < header_size or offset + atom_size > total_size:
                    return False
                atom_order.append(atom_type)
                offset += atom_size
    except OSError:
        return False
    try:
        return atom_order.index(b"moov") < atom_order.index(b"mdat")
    except ValueError:
        return False


def _validate_hd_rejection_banner(path: Path) -> None:
    import cv2

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("counterfactual_hd_presentation_banner_invalid")
        ok, frame = capture.read()
    finally:
        capture.release()
    if (
        not ok
        or frame is None
        or frame.shape[:2] != (HD_PRESENTATION_HEIGHT, HD_PRESENTATION_WIDTH)
    ):
        raise ValueError("counterfactual_hd_presentation_banner_invalid")
    patch = frame[8:24, HD_PRESENTATION_WIDTH - 80 : HD_PRESENTATION_WIDTH - 16]
    if patch.size == 0:
        raise ValueError("counterfactual_hd_presentation_banner_invalid")
    blue, green, red = np.mean(patch, axis=(0, 1))
    if not (red > 50.0 and red > blue * 1.5 and red > green * 1.5):
        raise ValueError("counterfactual_hd_presentation_banner_invalid")


def _encode_hd_presentation_video(
    *, raw_path: Path, output_path: Path
) -> tuple[list[str], dict[str, Any]]:
    if (
        not HD_PRESENTATION_FONT_PATH.is_file()
        or output_path.exists()
        or output_path.is_symlink()
    ):
        raise RuntimeError("counterfactual_hd_presentation_encoder_precondition_invalid")
    command = build_hd_presentation_ffmpeg_command(
        raw_path=raw_path,
        output_path=output_path,
    )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"counterfactual_hd_presentation_ffmpeg_failed:{completed.stderr.strip()}"
        )
    probe = _probe_video(output_path)
    _validate_hd_video_probe(probe, final_h264=True)
    if not _has_faststart_moov_before_mdat(output_path):
        raise RuntimeError("counterfactual_hd_presentation_faststart_invalid")
    _validate_hd_rejection_banner(output_path)
    return command, probe


def _ffmpeg_version() -> str:
    completed = subprocess.run(
        ["ffmpeg", "-version"],
        check=False,
        capture_output=True,
        text=True,
    )
    first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
    if completed.returncode != 0 or not first_line.startswith("ffmpeg version "):
        raise RuntimeError("counterfactual_hd_presentation_ffmpeg_version_invalid")
    return first_line


def _finalize_hd_presentation_artifacts(
    *,
    output_dir: Path,
    video_frame_map: Mapping[str, Any],
    hd_contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Validate raw recorder outputs, then encode the only release media."""
    raw_directory = output_dir / HD_PRESENTATION_RAW_DIRECTORY
    final_directory = output_dir / HD_PRESENTATION_FINAL_DIRECTORY
    manifest_path = raw_directory / HD_PRESENTATION_MANIFEST_BASENAME
    frames_path = raw_directory / HD_PRESENTATION_FRAMES_BASENAME
    if (
        raw_directory.is_symlink()
        or not manifest_path.is_file()
        or not frames_path.is_file()
        or final_directory.exists()
        or not HD_PRESENTATION_FONT_PATH.is_file()
    ):
        raise RuntimeError("counterfactual_hd_presentation_raw_artifacts_missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("counterfactual_hd_presentation_manifest_invalid") from exc
    if not isinstance(manifest, Mapping):
        raise RuntimeError("counterfactual_hd_presentation_manifest_invalid")
    binding_map = build_hd_presentation_binding_map(video_frame_map)
    final_directory.mkdir()
    binding_map_path = final_directory / HD_PRESENTATION_FRAME_MAP_BASENAME
    _atomic_create_json(binding_map_path, binding_map)
    recorder_evidence = validate_hd_presentation_recorder_evidence(
        manifest,
        _read_jsonl_records(frames_path),
        binding_map=binding_map,
    )
    artifacts: dict[str, dict[str, Any]] = {
        "hd_presentation_manifest": _artifact_record(
            manifest_path,
            output_dir=output_dir,
        ),
        "hd_presentation_frames": _artifact_record(
            frames_path,
            output_dir=output_dir,
        ),
        "hd_presentation_frame_map": _artifact_record(
            binding_map_path,
            output_dir=output_dir,
        ),
    }
    videos = []
    for name, source_prim_path in HD_PRESENTATION_CAMERA_SPECS:
        raw_relative = recorder_evidence["raw_video_relative_paths"][name]
        raw_path = raw_directory / raw_relative
        raw_artifact_key = f"hd_presentation_{name}_raw"
        final_artifact_key = f"hd_presentation_{name}"
        if raw_path.is_symlink() or not raw_path.is_file():
            raise RuntimeError("counterfactual_hd_presentation_raw_video_missing")
        raw_probe = _probe_video(raw_path)
        _validate_hd_video_probe(raw_probe, final_h264=False)
        final_path = final_directory / (
            f"unsafe_visual_only_counterfactual_{name}_{HD_PRESENTATION_HEIGHT}p.mp4"
        )
        command, final_probe = _encode_hd_presentation_video(
            raw_path=raw_path,
            output_path=final_path,
        )
        artifacts[raw_artifact_key] = _artifact_record(
            raw_path,
            output_dir=output_dir,
        )
        artifacts[final_artifact_key] = _artifact_record(
            final_path,
            output_dir=output_dir,
        )
        videos.append(
            {
                "name": name,
                "source_prim_path": source_prim_path,
                "raw_artifact_key": raw_artifact_key,
                "final_artifact_key": final_artifact_key,
                "raw_probe": raw_probe,
                "final_probe": final_probe,
                "ffmpeg_command": command,
            }
        )
    if tuple(artifacts) != HD_PRESENTATION_ARTIFACT_KEYS:
        raise RuntimeError("counterfactual_hd_presentation_artifact_keys_invalid")
    return (
        {
            "schema": HD_PRESENTATION_SCHEMA,
            "contract": dict(hd_contract),
            "capture_status": "complete",
            "encoding_status": "complete",
            "evidence_valid": True,
            "attempt_id": recorder_evidence["attempt_id"],
            "episode_id": recorder_evidence["episode_id"],
            "frame_count": recorder_evidence["frame_count"],
            "banner_lines": list(HD_PRESENTATION_BANNER_LINES),
            "raw_media_release_allowed": False,
            "font": {
                "path": str(HD_PRESENTATION_FONT_PATH),
                "sha256": sha256_file(HD_PRESENTATION_FONT_PATH),
            },
            "ffmpeg_version": _ffmpeg_version(),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "artifact_keys": list(HD_PRESENTATION_ARTIFACT_KEYS),
            "videos": videos,
        },
        artifacts,
    )


def _measure_runtime(
    args: argparse.Namespace,
    *,
    presentation_viewport: Any | None = None,
) -> dict[str, Any]:
    """Run the action ledger against the real PBD scene in a child process."""
    from isaacsim_compat import install_legacy_isaacsim_aliases

    install_legacy_isaacsim_aliases()
    from isaacsim.core.api import World
    from isaacsim.core.utils.stage import add_reference_to_stage
    from omegaconf import OmegaConf
    import omni.physx
    import omni.usd

    from factories.robot_factory import create_robot
    from factories.task_factory import create_task
    from utils.isaac_fluid_evaluation import (
        build_isaac_fluid_evaluation_loop,
        configure_contact_grasp_scene,
        configure_particle_usd_readback,
    )
    from utils.object_utils import ObjectUtils

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    contract = validate_counterfactual_config(config, config_path=args.config)
    capture_hd_presentation = bool(
        getattr(args, "capture_hd_presentation", False)
    )
    hd_presentation_contract = (
        build_hd_presentation_contract(config)
        if capture_hd_presentation
        else None
    )
    if capture_hd_presentation and presentation_viewport is None:
        raise RuntimeError("counterfactual_hd_presentation_viewport_missing")
    ledger = load_frozen_action_ledger(
        contract["source_trace_path"],
        expected_sha256=contract["source_trace_sha256"],
    )
    action_representation_contract = build_frozen_v6_action_representation_contract(
        ledger
    )
    replay_intervals = build_replay_intervals(ledger)
    if (
        ledger["transition_count"] != 864
        or ledger["action_count"] != 858
    ):
        raise RuntimeError("counterfactual_source_ledger_cardinality_mismatch")

    cfg = OmegaConf.create(config)
    fluid = cfg.online_fluid
    counter = cfg.counterfactual
    configure_particle_usd_readback()
    stage = omni.usd.get_context().get_stage()
    add_reference_to_stage(usd_path=str((REPO_ROOT / cfg.usd_path).resolve()), prim_path="/World")
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
    configure_particle_usd_readback()
    np.random.seed(int(counter.numpy_seed))
    robot_kwargs = {"position": np.asarray(cfg.robot.position, dtype=np.float64)}
    if getattr(cfg.robot, "usd_path", None):
        robot_kwargs["usd_path"] = str((REPO_ROOT / cfg.robot.usd_path).resolve())
    if getattr(cfg.robot, "camera_frequency", None) is not None:
        robot_kwargs["camera_frequency"] = int(cfg.robot.camera_frequency)
    robot = create_robot(str(cfg.robot.type), **robot_kwargs)
    contact_scene = configure_contact_grasp_scene(stage, fluid)
    ObjectUtils.get_instance(stage)
    task = create_task(str(cfg.task_type), cfg=cfg, world=world, stage=stage, robot=robot)
    task.reset()
    fluid_loop = build_isaac_fluid_evaluation_loop(
        cfg=cfg,
        world=world,
        task=task,
        stage=stage,
    )
    fluid_loop.reset_episode("unsafe-visual-only-counterfactual-0000")
    robot_usd_path = (REPO_ROOT / str(cfg.robot.usd_path)).resolve()
    dof_names = robot.dof_names
    dof_names = dof_names() if callable(dof_names) else dof_names
    live_robot_identity = validate_live_replay_robot_identity(
        dof_names=dof_names,
        joint_positions=robot.get_joint_positions(),
        finger_joint_indices=robot.gripper.joint_dof_indicies,
        task_robot_matches=getattr(task, "robot", None) is robot,
        robot_usd_path=robot_usd_path,
        robot_usd_sha256=sha256_file(robot_usd_path),
    )
    live_robot_stage_binding = build_live_replay_robot_stage_binding(stage)
    articulation_controller = robot.get_articulation_controller()
    if not callable(
        getattr(articulation_controller, "switch_dof_control_mode", None)
    ):
        raise RuntimeError("counterfactual_velocity_mode_api_missing")
    _read_articulation_controller_gains(articulation_controller)

    output_dir = args.out_dir
    trace_path = output_dir / OBSERVATION_TRACE_BASENAME
    video_path = output_dir / VIDEO_BASENAME
    map_path = output_dir / VIDEO_MAP_BASENAME
    hd_raw_directory = output_dir / HD_PRESENTATION_RAW_DIRECTORY
    hd_final_directory = output_dir / HD_PRESENTATION_FINAL_DIRECTORY
    hd_binding_map_path = hd_final_directory / HD_PRESENTATION_FRAME_MAP_BASENAME
    replay_state = FrozenReplayState()
    applied_action_hashes: list[str] = []
    applied_effective_action_hashes: list[str] = []
    applied_velocity_mode_switch_receipts: list[dict[str, Any]] = []
    velocity_mode_gain_readbacks: list[dict[str, Any]] = []
    frame_map: list[dict[str, Any]] = []
    observation_count = 0
    video_writer = None
    presentation_recorder = None
    presentation_recorder_closed = False
    hd_presentation_report: dict[str, Any] | None = None
    latest_attachment: Mapping[str, Any] = {}

    if capture_hd_presentation:
        from utils.presentation_video import build_isaac_presentation_video_recorder

        presentation_recorder = build_isaac_presentation_video_recorder(
            model_camera_configs=tuple(cfg.cameras),
            world=world,
            presentation_config=hd_presentation_contract,
            output_dir=hd_raw_directory,
            viewport=presentation_viewport,
        )
        presentation_recorder.initialize()

    try:
        with trace_path.open("x", encoding="utf-8") as trace_stream:
            observation = fluid_loop.observe()
            observation_count += 1
            latest_attachment = dict(observation["attachment"])
            state = observation["state"]
            record = observation["record"]
            combined = None
            import cv2
            from utils.fluid_evaluation_loop import model_camera_video_rgb

            combined = model_camera_video_rgb(
                state,
                camera_keys=tuple(fluid.model_camera_keys),
                expected_shape=tuple(fluid.model_camera_shape),
            )
            height, width = combined.shape[:2]
            video_writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                float(counter.video_fps),
                (width, height),
            )
            if not video_writer.isOpened():
                raise RuntimeError("counterfactual_video_writer_open_failed")
            _capture_counterfactual_frame(
                state=state,
                record=record,
                source_transition=None,
                integrated_source_transition=None,
                replay_state=replay_state,
                attachment=latest_attachment,
                writer=video_writer,
                frame_map=frame_map,
                camera_keys=tuple(fluid.model_camera_keys),
                camera_shape=tuple(fluid.model_camera_shape),
                replay_elapsed_seconds=0.0,
            )
            if presentation_recorder is not None:
                presentation_recorder.capture(record)
            _write_trace_line(
                trace_stream,
                {
                    "kind": "initial_observation",
                    "observation_index": int(record["observation_index"]),
                    "frame_identity": str(record["frame_identity"]),
                    "render_token": str(record["render"]["render_token"]),
                    "integration_step_after": int(record["integration_step_after"]),
                    "logical_step_after": int(record["logical_step_after"]),
                    "particle_position_sha256": str(record["position_sha256"]),
                    "surface_normal_provenance": (
                        _surface_normal_provenance_from_record(record)
                    ),
                    "surface_geometry_sha256": (
                        _surface_geometry_sha256_from_record(record)
                    ),
                    "monitor": replay_state.snapshot(),
                    "attachment_failure_reason": latest_attachment.get("failure_reason"),
                },
            )

            for interval in replay_intervals:
                transition = interval["source_transition"]
                integrated_transition = interval["integrated_source_transition"]
                fluid_loop.maybe_attach(replay_state, state)
                active_action = (
                    None
                    if integrated_transition is None
                    else integrated_transition["action"]
                )
                fluid_loop.commit_action(active_action)
                observation = fluid_loop.observe()
                observation_count += 1
                state = observation["state"]
                record = observation["record"]
                latest_attachment = dict(observation["attachment"])
                replay_state.advance(transition)
                action = transition["action"]
                effective_action_receipt = _effective_action_receipt(transition)
                velocity_mode_switch_receipt = _velocity_mode_switch_receipt(
                    effective_action_receipt
                )
                velocity_mode_gain_readback = None
                if action is not None:
                    if velocity_mode_switch_receipt is not None:
                        before_stiffness, before_damping = (
                            _read_articulation_controller_gains(
                                articulation_controller
                            )
                        )
                        articulation_controller.switch_dof_control_mode(
                            dof_index=velocity_mode_switch_receipt["dof_index"],
                            mode=velocity_mode_switch_receipt["mode"],
                        )
                        after_stiffness, after_damping = (
                            _read_articulation_controller_gains(
                                articulation_controller
                            )
                        )
                        velocity_mode_gain_readback = (
                            build_velocity_mode_gain_readback(
                                before_stiffness=before_stiffness,
                                before_damping=before_damping,
                                after_stiffness=after_stiffness,
                                after_damping=after_damping,
                            )
                        )
                        applied_velocity_mode_switch_receipts.append(
                            velocity_mode_switch_receipt
                        )
                        velocity_mode_gain_readbacks.append(
                            velocity_mode_gain_readback
                        )
                    reconstructed = _articulation_action_from_raw(action)
                    articulation_controller.apply_action(reconstructed)
                    applied_action_hashes.append(transition["action_sha256"])
                    if effective_action_receipt is None:
                        raise RuntimeError("counterfactual_effective_action_missing")
                    applied_effective_action_hashes.append(
                        effective_action_receipt["sha256"]
                    )
                if transition["pour_event"] == 2:
                    fluid_loop.mark_pour_started()
                _write_trace_line(
                    trace_stream,
                    {
                        "kind": "replayed_transition",
                        "source_transition_index": transition[
                            "source_transition_index"
                        ],
                        "source_apply_index": transition["source_apply_index"],
                        "source_action_sha256": transition["action_sha256"],
                        "integrated_source_transition_index": (
                            None
                            if integrated_transition is None
                            else integrated_transition["source_transition_index"]
                        ),
                        "integrated_source_action_sha256": (
                            None
                            if integrated_transition is None
                            else integrated_transition["action_sha256"]
                        ),
                        "source_pick_event": transition["pick_event"],
                        "source_pour_event": transition["pour_event"],
                        "source_terminal": transition["source_terminal"],
                        "source_transition_processed_after_observation": True,
                        "effective_action_receipt": effective_action_receipt,
                        "velocity_mode_switch_receipt": velocity_mode_switch_receipt,
                        "velocity_mode_gain_readback": velocity_mode_gain_readback,
                        "observation_index": int(record["observation_index"]),
                        "frame_identity": str(record["frame_identity"]),
                        "render_token": str(record["render"]["render_token"]),
                        "integration_step_after": int(record["integration_step_after"]),
                        "logical_step_after": int(record["logical_step_after"]),
                        "particle_position_sha256": str(record["position_sha256"]),
                        "surface_normal_provenance": (
                            _surface_normal_provenance_from_record(record)
                        ),
                        "surface_geometry_sha256": (
                            _surface_geometry_sha256_from_record(record)
                        ),
                        "monitor": replay_state.snapshot(),
                        "attachment_failure_reason": latest_attachment.get(
                            "failure_reason"
                        ),
                    },
                )
                if (
                    int(transition["source_transition_index"])
                    % int(counter.video_sample_every_transitions)
                    == 1
                ):
                    _capture_counterfactual_frame(
                        state=state,
                        record=record,
                        source_transition=transition,
                        integrated_source_transition=integrated_transition,
                        replay_state=replay_state,
                        attachment=latest_attachment,
                        writer=video_writer,
                        frame_map=frame_map,
                        camera_keys=tuple(fluid.model_camera_keys),
                        camera_shape=tuple(fluid.model_camera_shape),
                        replay_elapsed_seconds=(
                            int(transition["source_transition_index"]) + 1
                        )
                        * float(fluid.rendering_dt),
                    )
                    if presentation_recorder is not None:
                        presentation_recorder.capture(record)
            _write_trace_line(
                trace_stream,
                {
                    "kind": "terminal_evidence",
                    "attachment": latest_attachment,
                    "observation_count": observation_count,
                    "applied_action_hashes": applied_action_hashes,
                    "applied_effective_action_hashes": (
                        applied_effective_action_hashes
                    ),
                    "applied_velocity_mode_switch_receipts": (
                        applied_velocity_mode_switch_receipts
                    ),
                    "velocity_mode_gain_readbacks": velocity_mode_gain_readbacks,
                },
            )
            if presentation_recorder is not None:
                presentation_recorder.close_attempt(status="rejected")
                presentation_recorder_closed = True
    finally:
        if presentation_recorder is not None and not presentation_recorder_closed:
            presentation_recorder.close()
        if video_writer is not None:
            video_writer.release()

    if not video_path.is_file() or not frame_map:
        raise RuntimeError("counterfactual_video_missing")
    map_payload = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "forced_status": FORCED_STATUS,
        "source_trace_sha256": ledger["source_trace_sha256"],
        "video": VIDEO_BASENAME,
        "fps": int(counter.video_fps),
        "sampling_policy": str(counter.video_sampling_policy),
        "frame_count": len(frame_map),
        "frames": frame_map,
    }
    _atomic_create_json(map_path, map_payload)
    terminal = build_terminal_contract(
        ledger=ledger,
        applied_action_hashes=applied_action_hashes,
        applied_effective_action_hashes=applied_effective_action_hashes,
        expected_effective_action_hashes=action_representation_contract[
            "effective_action_hashes"
        ],
        applied_velocity_mode_switch_receipts=(
            applied_velocity_mode_switch_receipts
        ),
        expected_velocity_mode_switch_receipts=(
            action_representation_contract["expected_velocity_mode_switch_receipts"]
        ),
        velocity_mode_gain_readbacks=velocity_mode_gain_readbacks,
        attachment=latest_attachment,
        particle_readback_observation_count=observation_count,
    )
    if capture_hd_presentation:
        if terminal["status"] != FORCED_STATUS or terminal["integrity_valid"] is not True:
            raise RuntimeError("counterfactual_hd_presentation_terminal_invalid")
        hd_presentation_report, hd_artifacts = _finalize_hd_presentation_artifacts(
            output_dir=output_dir,
            video_frame_map=map_payload,
            hd_contract=hd_presentation_contract,
        )
    sealed = fluid_loop.seal_attempt(
        status="failed",
        reason="unsafe_visual_only_counterfactual",
    )
    artifacts = {
        "observation_trace": _artifact_record(trace_path, output_dir=output_dir),
        "video": _artifact_record(video_path, output_dir=output_dir),
        "video_frame_map": _artifact_record(map_path, output_dir=output_dir),
    }
    if hd_presentation_report is not None:
        artifacts.update(hd_artifacts)
    report = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "measurement_decision": terminal["status"],
        "run_nonce": args.run_nonce,
        "config_path": str(args.config),
        "config_sha256": contract["config_sha256"],
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "source_trace": {
            key: ledger[key]
            for key in (
                "source_trace_path",
                "source_trace_sha256",
                "source_protocol_id",
                "source_config_sha256",
                "transition_count",
                "action_count",
            )
        },
        "counterfactual_contract": contract,
        "action_representation_adapter": {
            **action_representation_contract["public"],
            "runtime_robot_identity": live_robot_identity,
            "runtime_robot_stage_binding": live_robot_stage_binding,
            "applied_velocity_mode_switch_receipts": (
                applied_velocity_mode_switch_receipts
            ),
            "velocity_mode_gain_readbacks": velocity_mode_gain_readbacks,
            "valid": (
                live_robot_identity["valid"] is True
                and live_robot_stage_binding["valid"] is True
                and applied_velocity_mode_switch_receipts
                == action_representation_contract[
                    "expected_velocity_mode_switch_receipts"
                ]
                and len(velocity_mode_gain_readbacks) == 1
                and velocity_mode_gain_readbacks[0]["valid"] is True
            ),
        },
        "runtime": {
            "physics_dt": float(world.get_physics_dt()),
            "rendering_dt": float(world.get_rendering_dt()),
            "source_ownership": str(fluid.source_ownership),
            "source_pose_authority": str(fluid.source_pose_authority),
            "controller_constructed": False,
            "collector_constructed": False,
            "action_index_rehydration_applied": True,
            "source_trace_replay_complete": len(applied_action_hashes)
            == ledger["action_count"],
            "observation_count": observation_count,
            "contact_grasp_scene": _json_native(contact_scene),
            "hd_presentation_requested": capture_hd_presentation,
        },
        "terminal": terminal,
        "sealed_attempt": sealed,
        "artifacts": artifacts,
        "success": False,
        "expert_episode_accepted": False,
        "collector_write_allowed": False,
        "ebench_finalize_allowed": False,
        "claim_limits": {
            "success_claim_allowed": False,
            "stable_grasp_claim_allowed": False,
            "liquid_transfer_claim_allowed": False,
            "scene_equivalence_claim_allowed": False,
            "trajectory_repair_applied": False,
            "description": (
                "Exact v6 serialized action-channel replay with a pinned, "
                "disclosed representation adapter in a distinct PBD liquid scene. "
                "This is visual-only evidence."
            ),
        },
    }
    if hd_presentation_report is not None:
        report["hd_presentation"] = hd_presentation_report
    return report


def _runtime_error_report(
    error: BaseException,
    *,
    run_nonce: str,
    config_sha256: str | None,
    phase: str,
    hd_presentation_requested: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "failed",
        "shutdown_status": "pending",
        "measurement_decision": RUNTIME_ERROR,
        "run_nonce": run_nonce,
        "config_sha256": config_sha256,
        "fatal_error": {
            "phase": phase,
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        },
        "success": False,
        "expert_episode_accepted": False,
        "collector_write_allowed": False,
        "ebench_finalize_allowed": False,
        "hd_presentation": {
            "requested": bool(hd_presentation_requested),
            "capture_status": (
                "failed" if hd_presentation_requested else "not_requested"
            ),
            "encoding_status": "not_started",
            "evidence_valid": False,
        },
    }


def _validate_artifact(record: Mapping[str, Any], *, output_dir: Path) -> Path:
    relative = Path(str(record.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("counterfactual_artifact_path_invalid")
    path = output_dir / relative
    component = output_dir
    if component.is_symlink():
        raise ValueError("counterfactual_artifact_path_invalid")
    for name in relative.parts:
        component = component / name
        if component.is_symlink():
            raise ValueError("counterfactual_artifact_path_invalid")
    if (
        not path.is_file()
        or type(record.get("byte_count")) is not int
        or record["byte_count"] != path.stat().st_size
        or record.get("sha256") != sha256_file(path)
    ):
        raise ValueError("counterfactual_artifact_hash_invalid")
    return path


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def validate_hd_presentation_binding_map(
    value: Mapping[str, Any],
    *,
    video_frame_map: Mapping[str, Any],
) -> int:
    """Bind every HD frame ordinal to the same-run frozen video schedule."""
    expected_frames = (
        video_frame_map.get("frames")
        if isinstance(video_frame_map, Mapping)
        else None
    )
    frames = value.get("frames") if isinstance(value, Mapping) else None
    if (
        not isinstance(expected_frames, list)
        or len(expected_frames) != 433
        or value.get("schema_version") != 1
        or value.get("manifest_type") != MANIFEST_TYPE
        or value.get("forced_status") != FORCED_STATUS
        or value.get("capture_policy") != HD_PRESENTATION_CAPTURE_POLICY
        or value.get("frame_count") != len(expected_frames)
        or not isinstance(frames, list)
        or len(frames) != len(expected_frames)
    ):
        raise ValueError("counterfactual_hd_presentation_binding_invalid")
    for index, (frame, expected) in enumerate(zip(frames, expected_frames)):
        if not isinstance(frame, Mapping) or not isinstance(expected, Mapping):
            raise ValueError("counterfactual_hd_presentation_binding_invalid")
        expected_values = {
            "frame_index": index,
            "source_transition_index": expected.get("source_transition_index"),
            "observation_index": expected.get("observation_index"),
            "frame_identity": expected.get("frame_identity"),
            "render_token": expected.get("render_token"),
            "integration_step_after": expected.get("integration_step_after"),
            "logical_step_after": expected.get("logical_step_after"),
            "camera_frame_ordinals": {
                name: index for name, _ in HD_PRESENTATION_CAMERA_SPECS
            },
        }
        if (
            dict(frame) != expected_values
            or not _is_sha256(expected_values["frame_identity"])
            or not _is_sha256(expected_values["render_token"])
            or type(expected_values["observation_index"]) is not int
            or type(expected_values["integration_step_after"]) is not int
            or type(expected_values["logical_step_after"]) is not int
        ):
            raise ValueError("counterfactual_hd_presentation_binding_invalid")
    return len(frames)


def _validate_hd_presentation_sync_receipt(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("counterfactual_hd_presentation_recorder_invalid")
    if (
        value.get("physics_and_timeline_unchanged") is not True
        or value.get("world_physics_unchanged") is not True
        or not _is_finite_number(value.get("time_before"))
        or not _is_finite_number(value.get("time_after"))
        or float(value["time_before"]) != float(value["time_after"])
        or type(value.get("step_before")) is not int
        or value.get("step_after") != value.get("step_before")
        or not _is_finite_number(value.get("timeline_time_before"))
        or not _is_finite_number(value.get("timeline_time_after"))
        or float(value["timeline_time_before"])
        != float(value["timeline_time_after"])
        or type(value.get("timeline_playing_before")) is not bool
        or type(value.get("timeline_playing_after")) is not bool
        or value.get("timeline_playing_after")
        is not value.get("timeline_playing_before")
        or type(value.get("timeline_auto_update_before")) is not bool
        or type(value.get("timeline_auto_update_after")) is not bool
        or value.get("timeline_auto_update_after")
        is not value.get("timeline_auto_update_before")
        or type(value.get("timeline_auto_update_disabled_for_capture")) is not bool
        or value.get("timeline_auto_update_disabled_for_capture")
        is not value.get("timeline_auto_update_before")
        or type(value.get("omni_timeline_unchanged")) is not bool
        or value.get("omni_timeline_unchanged") is not True
        or type(value.get("render_count")) is not int
        or not 6 <= value.get("render_count") <= 20
    ):
        raise ValueError("counterfactual_hd_presentation_recorder_invalid")


def validate_hd_presentation_recorder_evidence(
    manifest: Mapping[str, Any],
    frame_records: Sequence[Mapping[str, Any]],
    *,
    binding_map: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the raw recorder's one rejected attempt before encoding."""
    binding_frames = binding_map.get("frames") if isinstance(binding_map, Mapping) else None
    attempts = manifest.get("attempts") if isinstance(manifest, Mapping) else None
    if (
        manifest.get("schema_version") != 1
        or manifest.get("capture_policy") != HD_PRESENTATION_CAPTURE_POLICY
        or not isinstance(binding_frames, list)
        or not isinstance(attempts, list)
        or len(attempts) != 1
        or not isinstance(attempts[0], Mapping)
        or len(frame_records) != len(binding_frames)
    ):
        raise ValueError("counterfactual_hd_presentation_recorder_invalid")
    attempt = attempts[0]
    attempt_id = "attempt-00000000"
    episode_id = "unsafe-visual-only-counterfactual-0000"
    if (
        attempt.get("attempt_id") != attempt_id
        or attempt.get("episode_id") != episode_id
        or attempt.get("status") != "rejected"
        or attempt.get("frame_count") != len(binding_frames)
        or attempt.get("observation_index_range")
        != [
            binding_frames[0].get("observation_index"),
            binding_frames[-1].get("observation_index"),
        ]
    ):
        raise ValueError("counterfactual_hd_presentation_recorder_invalid")
    videos = attempt.get("videos")
    if not isinstance(videos, list) or len(videos) != len(HD_PRESENTATION_CAMERA_SPECS):
        raise ValueError("counterfactual_hd_presentation_recorder_invalid")
    raw_video_relative_paths: dict[str, str] = {}
    for video, (name, source_prim_path) in zip(videos, HD_PRESENTATION_CAMERA_SPECS):
        expected_path = f"{attempt_id}_{episode_id}_{name}_{HD_PRESENTATION_HEIGHT}p.mp4"
        if (
            not isinstance(video, Mapping)
            or video.get("name") != name
            or video.get("source_prim_path") != source_prim_path
            or video.get("prim_path")
            != f"/World/LabUtopiaPresentationCameras/{name}"
            or video.get("resolution")
            != [HD_PRESENTATION_WIDTH, HD_PRESENTATION_HEIGHT]
            or not _is_finite_number(video.get("fps"))
            or not math.isclose(
                float(video["fps"]),
                float(HD_PRESENTATION_FPS),
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            or video.get("path") != expected_path
        ):
            raise ValueError("counterfactual_hd_presentation_recorder_invalid")
        raw_video_relative_paths[name] = expected_path
    if len(set(raw_video_relative_paths.values())) != len(raw_video_relative_paths):
        raise ValueError("counterfactual_hd_presentation_recorder_invalid")
    for index, (record, binding) in enumerate(zip(frame_records, binding_frames)):
        if not isinstance(record, Mapping) or not isinstance(binding, Mapping):
            raise ValueError("counterfactual_hd_presentation_recorder_invalid")
        if (
            record.get("attempt_id") != attempt_id
            or record.get("episode_id") != episode_id
            or record.get("observation_index") != binding.get("observation_index")
            or record.get("frame_identity") != binding.get("frame_identity")
            or record.get("render_token") != binding.get("render_token")
            or record.get("integration_step_after")
            != binding.get("integration_step_after")
            or record.get("logical_step_after")
            != binding.get("logical_step_after")
            or record.get("physics_and_timeline_unchanged") is not True
        ):
            raise ValueError("counterfactual_hd_presentation_recorder_invalid")
        _validate_hd_presentation_sync_receipt(record.get("presentation_render"))
        cameras = record.get("cameras")
        if not isinstance(cameras, Mapping) or set(cameras) != {
            name for name, _ in HD_PRESENTATION_CAMERA_SPECS
        }:
            raise ValueError("counterfactual_hd_presentation_recorder_invalid")
        ordinals = binding.get("camera_frame_ordinals")
        if not isinstance(ordinals, Mapping):
            raise ValueError("counterfactual_hd_presentation_recorder_invalid")
        for name, _ in HD_PRESENTATION_CAMERA_SPECS:
            camera = cameras.get(name)
            if (
                ordinals.get(name) != index
                or not isinstance(camera, Mapping)
                or type(camera.get("rendering_frame")) is not int
                or camera.get("rendering_frame") < 0
                or not _is_finite_number(camera.get("rendering_time"))
            ):
                raise ValueError("counterfactual_hd_presentation_recorder_invalid")
    return {
        "attempt_id": attempt_id,
        "episode_id": episode_id,
        "frame_count": len(binding_frames),
        "raw_video_relative_paths": raw_video_relative_paths,
    }


def _validate_video_frame_map(
    value: Mapping[str, Any],
    *,
    ledger: Mapping[str, Any],
) -> int:
    if (
        value.get("manifest_type") != MANIFEST_TYPE
        or value.get("forced_status") != FORCED_STATUS
        or value.get("source_trace_sha256") != EXPECTED_SOURCE_TRACE_SHA256
        or value.get("fps") != 30
        or value.get("sampling_policy") != VIDEO_SAMPLING_POLICY
    ):
        raise ValueError("counterfactual_video_map_invalid")
    frame_count = value.get("frame_count")
    frames = value.get("frames")
    transitions = ledger.get("transitions") if isinstance(ledger, Mapping) else None
    expected_source_indices = [None, *range(1, 864, 2)]
    if (
        type(frame_count) is not int
        or frame_count != len(expected_source_indices)
        or not isinstance(frames, list)
        or len(frames) != frame_count
        or not isinstance(transitions, Sequence)
        or len(transitions) != 864
    ):
        raise ValueError("counterfactual_video_map_invalid")
    for index, (frame, source_index) in enumerate(
        zip(frames, expected_source_indices)
    ):
        if (
            not isinstance(frame, Mapping)
            or frame.get("frame_index") != index
            or frame.get("source_transition_index") != source_index
            or frame.get("source_transition_processed_after_observation")
            is not (source_index is not None)
            or not _is_sha256(frame.get("frame_identity"))
            or not _is_sha256(frame.get("particle_position_sha256"))
            or not _is_sha256(frame.get("surface_geometry_sha256"))
            or isinstance(frame.get("replay_elapsed_seconds"), bool)
            or not isinstance(frame.get("replay_elapsed_seconds"), (int, float))
            or not math.isfinite(float(frame["replay_elapsed_seconds"]))
            or not math.isclose(
                float(frame["replay_elapsed_seconds"]),
                0.0 if source_index is None else (source_index + 1) / 60.0,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
        ):
            raise ValueError("counterfactual_video_map_invalid")
        try:
            _validate_live_normal_provenance(frame.get("surface_normal_provenance"))
        except ValueError as exc:
            raise ValueError("counterfactual_video_map_invalid") from exc
        integrated_index = frame.get("integrated_source_transition_index")
        if source_index is None:
            if (
                integrated_index is not None
                or frame.get("source_action_sha256") is not None
                or frame.get("integrated_source_action_sha256") is not None
            ):
                raise ValueError("counterfactual_video_map_invalid")
        else:
            source = transitions[source_index]
            integrated = None if source_index == 0 else transitions[source_index - 1]
            if (
                not isinstance(source, Mapping)
                or source.get("source_transition_index") != source_index
                or frame.get("source_action_sha256") != source.get("action_sha256")
                or integrated_index
                != (None if integrated is None else integrated.get("source_transition_index"))
                or frame.get("integrated_source_action_sha256")
                != (None if integrated is None else integrated.get("action_sha256"))
            ):
                raise ValueError("counterfactual_video_map_invalid")
    return frame_count


def _validate_observation_trace(
    path: Path,
    *,
    ledger: Mapping[str, Any],
    frame_map: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("counterfactual_observation_trace_invalid") from exc
    transitions = ledger.get("transitions") if isinstance(ledger, Mapping) else None
    if (
        not isinstance(transitions, Sequence)
        or len(records) != len(transitions) + 2
        or not isinstance(records[0], Mapping)
        or records[0].get("kind") != "initial_observation"
    ):
        raise ValueError("counterfactual_observation_trace_invalid")
    try:
        _validate_live_normal_provenance(
            records[0].get("surface_normal_provenance")
        )
        if not _is_sha256(records[0].get("surface_geometry_sha256")):
            raise ValueError("counterfactual_surface_geometry_invalid")
    except ValueError as exc:
        raise ValueError("counterfactual_observation_trace_invalid") from exc
    by_source_index: dict[int, Mapping[str, Any]] = {}
    for index, (record, source) in enumerate(zip(records[1:-1], transitions)):
        integrated = None if index == 0 else transitions[index - 1]
        expected_effective_action_receipt = _effective_action_receipt(source)
        expected_velocity_mode_switch_receipt = _velocity_mode_switch_receipt(
            expected_effective_action_receipt
        )
        if (
            not isinstance(record, Mapping)
            or not isinstance(source, Mapping)
            or record.get("kind") != "replayed_transition"
            or record.get("source_transition_index") != index
            or record.get("source_apply_index") != source.get("source_apply_index")
            or record.get("source_action_sha256") != source.get("action_sha256")
            or record.get("source_pick_event") != source.get("pick_event")
            or record.get("source_pour_event") != source.get("pour_event")
            or record.get("source_terminal") != source.get("source_terminal")
            or record.get("integrated_source_transition_index")
            != (None if integrated is None else integrated.get("source_transition_index"))
            or record.get("integrated_source_action_sha256")
            != (None if integrated is None else integrated.get("action_sha256"))
            or record.get("source_transition_processed_after_observation") is not True
            or record.get("effective_action_receipt")
            != expected_effective_action_receipt
            or record.get("velocity_mode_switch_receipt")
            != expected_velocity_mode_switch_receipt
            or (
                expected_velocity_mode_switch_receipt is None
                and record.get("velocity_mode_gain_readback") is not None
            )
            or (
                expected_velocity_mode_switch_receipt is not None
                and not _velocity_mode_gain_readback_is_valid(
                    record.get("velocity_mode_gain_readback")
                )
            )
            or not _is_sha256(record.get("frame_identity"))
            or not _is_sha256(record.get("particle_position_sha256"))
            or not _is_sha256(record.get("surface_geometry_sha256"))
        ):
            raise ValueError("counterfactual_observation_trace_invalid")
        try:
            _validate_live_normal_provenance(
                record.get("surface_normal_provenance")
            )
        except ValueError as exc:
            raise ValueError("counterfactual_observation_trace_invalid") from exc
        by_source_index[index] = record
    terminal_evidence = records[-1]
    action_contract = build_frozen_v6_action_representation_contract(ledger)
    expected_action_hashes = [
        action.get("action_sha256") if isinstance(action, Mapping) else None
        for action in ledger.get("actions", [])
    ]
    if (
        not isinstance(terminal_evidence, Mapping)
        or terminal_evidence.get("kind") != "terminal_evidence"
        or not isinstance(terminal_evidence.get("attachment"), Mapping)
        or terminal_evidence.get("observation_count") != len(transitions) + 1
        or terminal_evidence.get("applied_action_hashes") != expected_action_hashes
        or terminal_evidence.get("applied_effective_action_hashes")
        != action_contract["effective_action_hashes"]
        or terminal_evidence.get("applied_velocity_mode_switch_receipts")
        != action_contract["expected_velocity_mode_switch_receipts"]
        or not isinstance(terminal_evidence.get("velocity_mode_gain_readbacks"), list)
        or len(terminal_evidence["velocity_mode_gain_readbacks"]) != 1
        or not _velocity_mode_gain_readback_is_valid(
            terminal_evidence["velocity_mode_gain_readbacks"][0]
        )
    ):
        raise ValueError("counterfactual_observation_trace_invalid")
    frames = frame_map.get("frames") if isinstance(frame_map, Mapping) else None
    if not isinstance(frames, list):
        raise ValueError("counterfactual_observation_trace_invalid")
    if (
        not frames
        or not isinstance(frames[0], Mapping)
        or frames[0].get("observation_index") != records[0].get("observation_index")
        or frames[0].get("frame_identity") != records[0].get("frame_identity")
        or frames[0].get("particle_position_sha256")
        != records[0].get("particle_position_sha256")
        or frames[0].get("surface_normal_provenance")
        != records[0].get("surface_normal_provenance")
        or frames[0].get("surface_geometry_sha256")
        != records[0].get("surface_geometry_sha256")
    ):
        raise ValueError("counterfactual_observation_trace_invalid")
    extra_frame_fields = (
        "render_token",
        "integration_step_after",
        "logical_step_after",
    )
    if any(key in frames[0] for key in extra_frame_fields) and any(
        frames[0].get(key) != records[0].get(key) for key in extra_frame_fields
    ):
        raise ValueError("counterfactual_observation_trace_invalid")
    for frame in frames[1:]:
        if not isinstance(frame, Mapping):
            raise ValueError("counterfactual_observation_trace_invalid")
        source_index = frame.get("source_transition_index")
        trace = by_source_index.get(source_index)
        if (
            trace is None
            or frame.get("observation_index") != trace.get("observation_index")
            or frame.get("frame_identity") != trace.get("frame_identity")
            or frame.get("particle_position_sha256")
            != trace.get("particle_position_sha256")
            or frame.get("surface_normal_provenance")
            != trace.get("surface_normal_provenance")
            or frame.get("surface_geometry_sha256")
            != trace.get("surface_geometry_sha256")
        ):
            raise ValueError("counterfactual_observation_trace_invalid")
        if any(key in frame for key in extra_frame_fields) and any(
            frame.get(key) != trace.get(key) for key in extra_frame_fields
        ):
            raise ValueError("counterfactual_observation_trace_invalid")
    return dict(terminal_evidence)


def _validate_action_representation_adapter(
    value: Any,
    *,
    ledger: Mapping[str, Any],
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("counterfactual_action_adapter_report_invalid")
    contract = build_frozen_v6_action_representation_contract(ledger)
    public = contract["public"]
    if any(value.get(key) != expected for key, expected in public.items()):
        raise ValueError("counterfactual_action_adapter_report_invalid")
    identity = value.get("runtime_robot_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("counterfactual_action_adapter_report_invalid")
    try:
        expected_identity = validate_live_replay_robot_identity(
            dof_names=identity.get("dof_names"),
            joint_positions=identity.get("joint_positions"),
            finger_joint_indices=identity.get("finger_joint_indices"),
            task_robot_matches=identity.get("task_robot_identity"),
            robot_usd_path=identity.get("robot_usd_path"),
            robot_usd_sha256=identity.get("robot_usd_sha256"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("counterfactual_action_adapter_report_invalid") from exc
    receipts = value.get("applied_velocity_mode_switch_receipts")
    stage_binding = value.get("runtime_robot_stage_binding")
    gain_readbacks = value.get("velocity_mode_gain_readbacks")
    try:
        validate_live_replay_robot_stage_binding_evidence(stage_binding)
    except ValueError as exc:
        raise ValueError("counterfactual_action_adapter_report_invalid") from exc
    if (
        dict(identity) != expected_identity
        or not isinstance(receipts, list)
        or receipts != contract["expected_velocity_mode_switch_receipts"]
        or not isinstance(gain_readbacks, list)
        or len(gain_readbacks) != 1
        or not _velocity_mode_gain_readback_is_valid(gain_readbacks[0])
        or value.get("valid") is not True
    ):
        raise ValueError("counterfactual_action_adapter_report_invalid")


def _validate_video_decode(
    path: Path,
    *,
    expected_frame_count: int,
    expected_fps: int,
) -> None:
    import cv2

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError("counterfactual_video_decode_invalid")
    actual_fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not math.isfinite(actual_fps) or not math.isclose(
        actual_fps,
        float(expected_fps),
        rel_tol=0.0,
        abs_tol=1.0e-6,
    ):
        capture.release()
        raise ValueError("counterfactual_video_decode_invalid")
    frame_count = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame is None or frame.size == 0:
                raise ValueError("counterfactual_video_decode_invalid")
            frame_count += 1
    finally:
        capture.release()
    if frame_count != expected_frame_count:
        raise ValueError("counterfactual_video_decode_invalid")


def _validate_hd_presentation_report(
    value: Any,
    *,
    artifacts: Mapping[str, Any],
    output_dir: Path,
    video_frame_map: Mapping[str, Any],
    expected_contract: Mapping[str, Any],
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("counterfactual_hd_presentation_report_invalid")
    font = value.get("font")
    videos = value.get("videos")
    if (
        value.get("schema") != HD_PRESENTATION_SCHEMA
        or value.get("contract") != expected_contract
        or value.get("capture_status") != "complete"
        or value.get("encoding_status") != "complete"
        or value.get("evidence_valid") is not True
        or value.get("attempt_id") != "attempt-00000000"
        or value.get("episode_id") != "unsafe-visual-only-counterfactual-0000"
        or value.get("frame_count") != 433
        or value.get("banner_lines") != list(HD_PRESENTATION_BANNER_LINES)
        or value.get("raw_media_release_allowed") is not False
        or not isinstance(font, Mapping)
        or font.get("path") != str(HD_PRESENTATION_FONT_PATH)
        or font.get("sha256") != sha256_file(HD_PRESENTATION_FONT_PATH)
        or not isinstance(value.get("ffmpeg_version"), str)
        or not value["ffmpeg_version"].startswith("ffmpeg version ")
        or not (
            value.get("cuda_visible_devices") is None
            or isinstance(value.get("cuda_visible_devices"), str)
        )
        or value.get("artifact_keys") != list(HD_PRESENTATION_ARTIFACT_KEYS)
        or not isinstance(videos, list)
        or len(videos) != len(HD_PRESENTATION_CAMERA_SPECS)
    ):
        raise ValueError("counterfactual_hd_presentation_report_invalid")
    all_hd_artifacts = {
        key: artifacts.get(key) for key in HD_PRESENTATION_ARTIFACT_KEYS
    }
    if any(not isinstance(record, Mapping) for record in all_hd_artifacts.values()):
        raise ValueError("counterfactual_hd_presentation_report_invalid")
    paths = [str(record.get("path")) for record in all_hd_artifacts.values()]
    if len(set(paths)) != len(paths):
        raise ValueError("counterfactual_hd_presentation_report_invalid")
    resolved = {
        key: _validate_artifact(record, output_dir=output_dir)
        for key, record in all_hd_artifacts.items()
    }
    try:
        binding_map = json.loads(
            resolved["hd_presentation_frame_map"].read_text(encoding="utf-8")
        )
        manifest = json.loads(
            resolved["hd_presentation_manifest"].read_text(encoding="utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("counterfactual_hd_presentation_report_invalid") from exc
    if not isinstance(binding_map, Mapping) or not isinstance(manifest, Mapping):
        raise ValueError("counterfactual_hd_presentation_report_invalid")
    try:
        frame_count = validate_hd_presentation_binding_map(
            binding_map,
            video_frame_map=video_frame_map,
        )
        recorder_evidence = validate_hd_presentation_recorder_evidence(
            manifest,
            _read_jsonl_records(resolved["hd_presentation_frames"]),
            binding_map=binding_map,
        )
    except ValueError as exc:
        raise ValueError("counterfactual_hd_presentation_report_invalid") from exc
    if (
        frame_count != value.get("frame_count")
        or recorder_evidence["attempt_id"] != value.get("attempt_id")
        or recorder_evidence["episode_id"] != value.get("episode_id")
    ):
        raise ValueError("counterfactual_hd_presentation_report_invalid")
    for video, (name, source_prim_path) in zip(videos, HD_PRESENTATION_CAMERA_SPECS):
        raw_artifact_key = f"hd_presentation_{name}_raw"
        final_artifact_key = f"hd_presentation_{name}"
        if (
            not isinstance(video, Mapping)
            or video.get("name") != name
            or video.get("source_prim_path") != source_prim_path
            or video.get("raw_artifact_key") != raw_artifact_key
            or video.get("final_artifact_key") != final_artifact_key
        ):
            raise ValueError("counterfactual_hd_presentation_report_invalid")
        raw_path = resolved[raw_artifact_key]
        final_path = resolved[final_artifact_key]
        raw_probe = _probe_video(raw_path)
        final_probe = _probe_video(final_path)
        try:
            _validate_hd_video_probe(raw_probe, final_h264=False)
            _validate_hd_video_probe(final_probe, final_h264=True)
            _validate_hd_rejection_banner(final_path)
        except ValueError as exc:
            raise ValueError("counterfactual_hd_presentation_report_invalid") from exc
        if (
            video.get("raw_probe") != raw_probe
            or video.get("final_probe") != final_probe
            or video.get("ffmpeg_command")
            != build_hd_presentation_ffmpeg_command(
                raw_path=raw_path,
                output_path=final_path,
            )
            or not _has_faststart_moov_before_mdat(final_path)
        ):
            raise ValueError("counterfactual_hd_presentation_report_invalid")


def _validate_provisional_report(
    report: Mapping[str, Any],
    *,
    output_dir: Path,
    expected_nonce: str,
    expected_config_sha256: str,
    expected_contract: Mapping[str, Any],
    expected_ledger: Mapping[str, Any],
    expected_runner_sha256: str,
    expected_hd_presentation_contract: Mapping[str, Any] | None,
) -> None:
    expected_source_trace = {
        key: expected_ledger[key]
        for key in (
            "source_trace_path",
            "source_trace_sha256",
            "source_protocol_id",
            "source_config_sha256",
            "transition_count",
            "action_count",
        )
    }
    if (
        report.get("manifest_type") != MANIFEST_TYPE
        or report.get("run_nonce") != expected_nonce
        or report.get("config_sha256") != expected_config_sha256
        or report.get("runner_sha256") != expected_runner_sha256
        or report.get("source_trace") != expected_source_trace
        or report.get("counterfactual_contract") != expected_contract
        or report.get("measurement_decision") != FORCED_STATUS
        or report.get("lifecycle_status")
        != "measurement_complete_pending_application_close"
        or report.get("shutdown_status") != "pending"
    ):
        raise ValueError("counterfactual_provisional_identity_invalid")
    terminal = report.get("terminal")
    artifacts = report.get("artifacts")
    runtime = report.get("runtime")
    sealed_attempt = report.get("sealed_attempt")
    claim_limits = report.get("claim_limits")
    integrity_checks = (
        terminal.get("integrity_checks") if isinstance(terminal, Mapping) else None
    )
    expected_artifact_keys = {
        "observation_trace",
        "video",
        "video_frame_map",
    }
    if expected_hd_presentation_contract is not None:
        expected_artifact_keys.update(HD_PRESENTATION_ARTIFACT_KEYS)
    if (
        not isinstance(terminal, Mapping)
        or terminal.get("status") != FORCED_STATUS
        or terminal.get("success") is not False
        or terminal.get("expert_episode_accepted") is not False
        or terminal.get("collector_write_allowed") is not False
        or terminal.get("ebench_finalize_allowed") is not False
        or report.get("success") is not False
        or report.get("expert_episode_accepted") is not False
        or report.get("collector_write_allowed") is not False
        or report.get("ebench_finalize_allowed") is not False
        or terminal.get("contact_grasp_claimed") is not False
        or terminal.get("trajectory_repair_applied") is not False
        or terminal.get("scene_equivalence_claim_allowed") is not False
        or terminal.get("integrity_valid") is not True
        or not isinstance(integrity_checks, Mapping)
        or integrity_checks.get("all_source_actions_applied_exactly_once")
        is not True
        or integrity_checks.get("all_effective_actions_applied_exactly_once")
        is not True
        or integrity_checks.get("velocity_mode_transition_applied_exactly_once")
        is not True
        or integrity_checks.get("velocity_mode_readback_verified") is not True
        or not isinstance(runtime, Mapping)
        or not math.isclose(
            float(runtime.get("physics_dt", math.nan)),
            float(expected_contract["physics_dt"]),
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        or not math.isclose(
            float(runtime.get("rendering_dt", math.nan)),
            float(expected_contract["rendering_dt"]),
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        or runtime.get("controller_constructed") is not False
        or runtime.get("collector_constructed") is not False
        or runtime.get("action_index_rehydration_applied") is not True
        or runtime.get("source_trace_replay_complete") is not True
        or runtime.get("hd_presentation_requested")
        is not (expected_hd_presentation_contract is not None)
        or not isinstance(sealed_attempt, Mapping)
        or sealed_attempt.get("attempt_status") != "failed"
        or sealed_attempt.get("reason") != "unsafe_visual_only_counterfactual"
        or not isinstance(claim_limits, Mapping)
        or claim_limits.get("success_claim_allowed") is not False
        or claim_limits.get("stable_grasp_claim_allowed") is not False
        or claim_limits.get("liquid_transfer_claim_allowed") is not False
        or claim_limits.get("scene_equivalence_claim_allowed") is not False
        or claim_limits.get("trajectory_repair_applied") is not False
        or not isinstance(artifacts, Mapping)
        or set(artifacts) != expected_artifact_keys
    ):
        raise ValueError("counterfactual_provisional_contract_invalid")
    map_path = _validate_artifact(artifacts["video_frame_map"], output_dir=output_dir)
    video_path = _validate_artifact(artifacts["video"], output_dir=output_dir)
    observation_trace_path = _validate_artifact(
        artifacts["observation_trace"], output_dir=output_dir
    )
    frame_map = json.loads(map_path.read_text(encoding="utf-8"))
    _validate_action_representation_adapter(
        report.get("action_representation_adapter"),
        ledger=expected_ledger,
    )
    frame_count = _validate_video_frame_map(frame_map, ledger=expected_ledger)
    if expected_hd_presentation_contract is None:
        if "hd_presentation" in report:
            raise ValueError("counterfactual_provisional_contract_invalid")
    else:
        _validate_hd_presentation_report(
            report.get("hd_presentation"),
            artifacts=artifacts,
            output_dir=output_dir,
            video_frame_map=frame_map,
            expected_contract=expected_hd_presentation_contract,
        )
    terminal_evidence = _validate_observation_trace(
        observation_trace_path,
        ledger=expected_ledger,
        frame_map=frame_map,
    )
    adapter = report.get("action_representation_adapter")
    if (
        not isinstance(adapter, Mapping)
        or adapter.get("velocity_mode_gain_readbacks")
        != terminal_evidence["velocity_mode_gain_readbacks"]
    ):
        raise ValueError("counterfactual_provisional_contract_invalid")
    action_contract = build_frozen_v6_action_representation_contract(expected_ledger)
    recomputed_terminal = build_terminal_contract(
        ledger=expected_ledger,
        applied_action_hashes=terminal_evidence["applied_action_hashes"],
        applied_effective_action_hashes=terminal_evidence[
            "applied_effective_action_hashes"
        ],
        expected_effective_action_hashes=action_contract["effective_action_hashes"],
        applied_velocity_mode_switch_receipts=terminal_evidence[
            "applied_velocity_mode_switch_receipts"
        ],
        expected_velocity_mode_switch_receipts=action_contract[
            "expected_velocity_mode_switch_receipts"
        ],
        velocity_mode_gain_readbacks=terminal_evidence[
            "velocity_mode_gain_readbacks"
        ],
        attachment=terminal_evidence["attachment"],
        particle_readback_observation_count=terminal_evidence["observation_count"],
    )
    if dict(terminal) != recomputed_terminal:
        raise ValueError("counterfactual_provisional_contract_invalid")
    _validate_video_decode(
        video_path,
        expected_frame_count=frame_count,
        expected_fps=30,
    )


def _finalize_child_report(
    provisional: Mapping[str, Any],
    *,
    child_command: Sequence[str],
    child_returncode: int,
    timed_out: bool,
    termination: str | None,
) -> dict[str, Any]:
    report = dict(provisional)
    clean = bool(
        not timed_out
        and child_returncode == 0
        and report.get("measurement_decision") == FORCED_STATUS
        and report.get("lifecycle_status")
        == "measurement_complete_pending_application_close"
    )
    report["child_process"] = {
        "command": [str(value) for value in child_command],
        "returncode": int(child_returncode),
        "timed_out": bool(timed_out),
        "termination": termination,
    }
    report["finalized_at_utc"] = datetime.now(timezone.utc).isoformat()
    if clean:
        report["decision"] = FORCED_STATUS
        report["lifecycle_status"] = "completed"
        report["shutdown_status"] = "child_exit_0"
    else:
        report["decision"] = RUNTIME_ERROR
        report["lifecycle_status"] = "failed"
        report["shutdown_status"] = (
            "child_timeout"
            if timed_out
            else "child_exit_nonzero"
            if child_returncode != 0
            else "measurement_runtime_error"
        )
        report["success"] = False
        report["expert_episode_accepted"] = False
        report["collector_write_allowed"] = False
        report["ebench_finalize_allowed"] = False
    return report


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
        process.wait(timeout=30.0)
    return termination


def _provision_hd_presentation_viewport(app: Any) -> tuple[Any, Any]:
    """Create a retained, explicit viewport rather than relying on UI defaults."""
    from isaacsim.core.utils import extensions

    extensions.enable_extension("omni.kit.viewport.window")
    for _ in range(8):
        app.update()
    from omni.kit.viewport.utility import (
        create_viewport_window,
        get_active_viewport,
    )

    window = create_viewport_window(
        HD_PRESENTATION_VIEWPORT_WINDOW_NAME,
        width=HD_PRESENTATION_WIDTH,
        height=HD_PRESENTATION_HEIGHT,
    )
    if window is None:
        raise RuntimeError("counterfactual_hd_presentation_viewport_create_failed")
    for _ in range(8):
        app.update()
    active_viewport = get_active_viewport()
    viewport = window.viewport_api
    if active_viewport is None or viewport is None:
        try:
            window.destroy()
        finally:
            raise RuntimeError("counterfactual_hd_presentation_viewport_missing")
    return window, viewport


def _run_runtime_child(args: argparse.Namespace) -> int:
    provisional_path = args.out_dir / PROVISIONAL_REPORT_BASENAME
    app = None
    presentation_window = None
    config_sha256 = sha256_file(args.config)
    try:
        from isaacsim import SimulationApp

        app = SimulationApp(
            {
                "headless": True,
                "width": (
                    HD_PRESENTATION_WIDTH
                    if args.capture_hd_presentation
                    else 512
                ),
                "height": (
                    HD_PRESENTATION_HEIGHT
                    if args.capture_hd_presentation
                    else 256
                ),
            }
        )
        try:
            presentation_viewport = None
            if args.capture_hd_presentation:
                from isaacsim_compat import install_legacy_isaacsim_aliases

                install_legacy_isaacsim_aliases()
                presentation_window, presentation_viewport = (
                    _provision_hd_presentation_viewport(app)
                )
            report = _measure_runtime(
                args,
                presentation_viewport=presentation_viewport,
            )
        except Exception as exc:
            report = _runtime_error_report(
                exc,
                run_nonce=args.run_nonce,
                config_sha256=config_sha256,
                phase="runtime_measurement",
                hd_presentation_requested=args.capture_hd_presentation,
            )
        _atomic_create_json(provisional_path, report)
    except Exception as exc:
        if not provisional_path.exists():
            _atomic_create_json(
                provisional_path,
                _runtime_error_report(
                    exc,
                    run_nonce=args.run_nonce,
                    config_sha256=config_sha256,
                    phase="application_bootstrap",
                    hd_presentation_requested=args.capture_hd_presentation,
                ),
            )
        return 1
    finally:
        if presentation_window is not None:
            presentation_window.destroy()
        if app is not None:
            app.close()
    return 0


def _child_command(args: argparse.Namespace) -> list[str]:
    command = [
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
    if args.capture_hd_presentation:
        command.append("--capture-hd-presentation")
    return command


def _load_json_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("counterfactual_report_invalid")
    return dict(value)


def _run_parent(args: argparse.Namespace) -> int:
    # Freeze all identities before child launch so post-run validation has an
    # immutable parent-side authority rather than rereading mutable inputs.
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    expected_contract = validate_counterfactual_config(
        config,
        config_path=args.config,
    )
    expected_hd_presentation_contract = (
        build_hd_presentation_contract(config)
        if args.capture_hd_presentation
        else None
    )
    expected_ledger = load_frozen_action_ledger(
        expected_contract["source_trace_path"],
        expected_sha256=expected_contract["source_trace_sha256"],
    )
    expected_config_sha256 = expected_contract["config_sha256"]
    expected_runner_sha256 = sha256_file(Path(__file__).resolve())
    try:
        args.out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(
            f"counterfactual runner refused existing output: {args.out_dir}",
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
                child_returncode = int(process.wait(timeout=args.timeout_seconds))
            except subprocess.TimeoutExpired:
                timed_out = True
                termination = _terminate_and_reap(process)
                child_returncode = int(process.returncode or -signal.SIGKILL)
        except OSError as exc:
            launch_error = exc

    provisional_path = args.out_dir / PROVISIONAL_REPORT_BASENAME
    try:
        provisional = _load_json_mapping(provisional_path)
        if provisional.get("measurement_decision") == FORCED_STATUS:
            _validate_provisional_report(
                provisional,
                output_dir=args.out_dir,
                expected_nonce=args.run_nonce,
                expected_config_sha256=expected_config_sha256,
                expected_contract=expected_contract,
                expected_ledger=expected_ledger,
                expected_runner_sha256=expected_runner_sha256,
                expected_hd_presentation_contract=expected_hd_presentation_contract,
            )
    except Exception as exc:
        provisional = _runtime_error_report(
            exc,
            run_nonce=args.run_nonce,
            config_sha256=expected_config_sha256,
            phase="parent_artifact_validation",
            hd_presentation_requested=args.capture_hd_presentation,
        )
        if launch_error is not None:
            provisional["fatal_error"]["launch_error"] = str(launch_error)
    report = _finalize_child_report(
        provisional,
        child_command=command,
        child_returncode=child_returncode,
        timed_out=timed_out,
        termination=termination,
    )
    _atomic_create_json(args.out_dir / FINAL_REPORT_BASENAME, report)
    print(
        f"counterfactual decision={report['decision']} out={args.out_dir / FINAL_REPORT_BASENAME}",
        flush=True,
    )
    return 0 if report["lifecycle_status"] == "completed" else 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument(
        "--capture-hd-presentation",
        action="store_true",
        help=(
            "Write the separately audited 1280x720 rejected presentation videos"
        ),
    )
    parser.add_argument("--runtime-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-nonce", default="", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.config.is_file():
        parser.error(f"config not found: {args.config}")
    try:
        config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
        validate_counterfactual_config(config, config_path=args.config)
        if args.capture_hd_presentation:
            build_hd_presentation_contract(config)
        load_frozen_action_ledger(
            REPO_ROOT / EXPECTED_SOURCE_TRACE_RELATIVE_PATH,
            expected_sha256=EXPECTED_SOURCE_TRACE_SHA256,
        )
    except ValueError as exc:
        parser.error(str(exc))
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
