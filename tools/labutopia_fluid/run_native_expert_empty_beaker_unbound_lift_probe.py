#!/usr/bin/env python3
"""Validate a native empty-beaker pick, lift, and pour without artificial coupling."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
from importlib import metadata as importlib_metadata
import json
import math
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from collections import deque
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v1.yaml"
)
PRODUCTION_CONFIG = REPO_ROOT / "config/level1_pour.yaml"
TREATMENTS = ("control", "instrumented")
DECISIONS = (
    "PROBE_RUNTIME_ERROR",
    "NATIVE_EXPERT_UNBOUND_AUDIT_NO_GO",
    "NATIVE_EXPERT_UNBOUND_LIFT_FAIL",
    "NATIVE_EXPERT_UNBOUND_LIFT_PASS",
)
SOURCE_ROOT_PATH = "/World/beaker2"
SOURCE_BODY_PATH = "/World/beaker2/mesh"
SUPPORT_PATH = "/World/Cube"
TABLE_SUPPORT_PATH = "/World/table/surface/mesh"
ROBOT_ROOT_PATH = "/World/Franka"
LEFT_FINGER_BODY_PATH = "/World/Franka/panda_leftfinger"
RIGHT_FINGER_BODY_PATH = "/World/Franka/panda_rightfinger"
HAND_BODY_PATH = "/World/Franka/panda_hand"
LOCAL_FRANKA_USD_PATH = "assets/robots/Franka.usd"
LOCAL_FRANKA_SHA256 = "312a326e338949fb40fd245886508cc52cc47e2bebd696e99c7dcdd3d3a7f90b"
ISAACSIM41_FRANKA_RUNTIME_OMNIPBR_PATH = (
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/"
    "site-packages/omni/mdl/core/Base/OmniPBR.mdl"
)
ISAACSIM41_FRANKA_RUNTIME_OMNIPBR_SHA256 = (
    "e0591cdda9f21eb61360a39919a82bbff8b8a872344d89c67e6b245dae974c3b"
)
LOCAL_SCENE_USD_PATH = (
    "assets/chemistry_lab/lab_001_fluid_eval/dependencies/"
    "lab_001_localized_20260707/lab_001.usd"
)
LOCAL_SCENE_SHA256 = "b3861b5a17945abe401062a04125969c3a63b0f8a0a5ce0026a461dbdfc935f2"
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
REPORT_BODY_PATHS = (
    SOURCE_BODY_PATH,
    LEFT_FINGER_BODY_PATH,
    RIGHT_FINGER_BODY_PATH,
    HAND_BODY_PATH,
)
ACTION_CHANNELS = ("joint_positions", "joint_velocities", "joint_efforts")
PROJECTION_ONLY_FIELDS = ("diagnostic", "name", "max_episodes", "hydra", "multi_run")
FROZEN_CONFIG_BASENAME = "frozen_config.json"
TRACE_BASENAME = "trace.jsonl"
PROVISIONAL_REPORT_BASENAME = "provisional_report.json"
CLEANUP_BASENAME = "cleanup.json"
FINAL_REPORT_BASENAME = "report.json"
VIDEO_BASENAME = "instrumented_composite.mp4"
VIDEO_MAP_BASENAME = "instrumented_video_frame_map.json"
V1_PROTOCOL_ID = "native_expert_empty_beaker_unbound_lift_v1"
V2_PROTOCOL_ID = "native_expert_empty_beaker_unbound_lift_v2"
V3_PROTOCOL_ID = "native_expert_empty_beaker_unbound_lift_v3"
V4_PROTOCOL_ID = "native_expert_empty_beaker_unbound_lift_v4"
V5_PROTOCOL_ID = "native_expert_empty_beaker_unbound_lift_v5"
V6_PROTOCOL_ID = "native_expert_empty_beaker_unbound_lift_v6"
TRACE_MANIFEST_TYPE = "native_expert_empty_beaker_unbound_lift_trace_v1"
CHILD_MANIFEST_TYPE = "native_expert_empty_beaker_unbound_lift_child_v1"
MANIFEST_TYPE = "native_expert_empty_beaker_unbound_lift_probe_v1"
ZERO_SHA256 = "0" * 64
PROTO_NONE = 0xFFFFFFFF
CONTACT_MATERIAL_IDENTIFIER_ZERO = "__physx_material_identifier_zero__"
STATIC_USD_NONFINITE_FLOAT_TAG = "__native_unbound_static_usd_nonfinite_float__"
RUNTIME_DIAGNOSTICS_ENV = "LABUTOPIA_NATIVE_UNBOUND_RUNTIME_DIAGNOSTICS"
RUNTIME_DIAGNOSTIC_PREFIX = "native_unbound_runtime_diagnostic"
RUNTIME_DIAGNOSTIC_STACK_READY_FRAGMENT = (
    b"native_unbound_runtime_diagnostic phase=runtime "
    b"event=stack_dump_handler_ready "
)
RUNTIME_DIAGNOSTIC_STACK_DUMP_GRACE_SECONDS = 0.25

REQUIRED_WRITER_AUDIT_SURFACES = (
    "source_adapter_read_only",
    "plural_prim_view_pose_velocity",
    "plural_prim_view_world_poses",
    "plural_prim_view_local_poses",
    "plural_prim_view_velocities",
    "plural_prim_view_linear_velocities",
    "plural_prim_view_angular_velocities",
    "physics_view_kinematic_targets",
    "physics_view_dynamic_targets",
    "physics_view_transforms_velocities",
    "physics_view_transforms",
    "physics_view_velocities",
    "physics_view_forces_torques_impulses",
    "physics_view_forces",
    "physics_view_torques",
    "physics_view_impulses",
    "physics_view_force_at_position",
    "object_utils_set_object_position",
    "gripper_add_object_to_gripper",
    "gripper_update_grasped_object_position",
    "gripper_release_object",
    "usd_mutation_notice",
)
WRITER_AUDIT_COUNT_FIELDS = (
    "root_body_pose_velocity",
    "plural_pose_velocity",
    "plural_world_poses",
    "plural_local_poses",
    "plural_velocities",
    "plural_linear_velocities",
    "plural_angular_velocities",
    "kinematic_targets",
    "dynamic_targets",
    "transforms_velocities",
    "transforms",
    "physics_velocities",
    "forces_torques_impulses",
    "forces",
    "torques",
    "impulses",
    "force_at_position",
    "software_gripper_calls",
    "raw_property_changes",
)
PINNED_DIAGNOSTIC_V1 = {
    "schema_version": 1,
    "protocol_id": V1_PROTOCOL_ID,
    "treatments": list(TREATMENTS),
    "numpy_seed": 20260718,
    "physics_dt": 1.0 / 60.0,
    "gravity_world_m_s2": [0.0, 0.0, -9.81],
    "stage_units_in_meters": 1.0,
    "physics_scene_path": "/physicsScene",
    "isaac_sim_version": "4.1.0.0",
    "maximum_production_steps": 1500,
    "child_timeout_seconds": 900,
    "retention_steps": 60,
    "rise_threshold_m": 0.12,
    "stable_supported_steps": 10,
    "stable_linear_speed_m_s": 0.001,
    "stable_angular_speed_degrees_s": 0.1,
    "stable_origin_displacement_m": 0.0001,
    "post_pour_rotation_degrees": 50.0,
    "source_reset_root_path": SOURCE_ROOT_PATH,
    "source_body_path": SOURCE_BODY_PATH,
    "source_collider_path": SOURCE_BODY_PATH,
    "support_collider_path": SUPPORT_PATH,
    "left_finger_body_path": LEFT_FINGER_BODY_PATH,
    "right_finger_body_path": RIGHT_FINGER_BODY_PATH,
    "hand_body_path": HAND_BODY_PATH,
    "local_franka": {
        "usd_path": LOCAL_FRANKA_USD_PATH,
        "sha256": LOCAL_FRANKA_SHA256,
    },
    "local_scene": {
        "usd_path": LOCAL_SCENE_USD_PATH,
        "sha256": LOCAL_SCENE_SHA256,
    },
    "report_body_paths": list(REPORT_BODY_PATHS),
    "topology": {
        "normalized_height_range": [0.20, 0.80],
        "pad_edge_margin_m": 0.001,
        "maximum_vertical_normal_cosine": 0.25,
        "minimum_inward_face_cosine": 0.8,
    },
    "comparison_tolerances": {
        "origin_m": 0.0001,
        "orientation_degrees": 0.1,
        "linear_velocity_m_s": 0.001,
        "angular_velocity_degrees_s": 0.1,
    },
    "video": {
        "sample_every_transitions": 2,
        "fps": 30.0,
        "camera_names": ["camera_1", "camera_2"],
    },
    "required_implementation_files": [
        "factories/robot_factory.py",
        "factories/task_factory.py",
        "factories/controller_factory.py",
        "tasks/base_task.py",
        "tasks/pickpour_task.py",
        "controllers/base_controller.py",
        "controllers/pour_controller.py",
        "controllers/atomic_actions/pick_controller.py",
        "controllers/atomic_actions/pour_controller.py",
        "controllers/robot_controllers/grapper_manager.py",
        "robots/franka/franka.py",
        "utils/object_utils.py",
        "data_collectors/data_collector.py",
    ],
}
PINNED_DIAGNOSTIC_V2 = copy.deepcopy(PINNED_DIAGNOSTIC_V1)
PINNED_DIAGNOSTIC_V2.update(
    {
        "schema_version": 2,
        "protocol_id": V2_PROTOCOL_ID,
        "initial_support_activation_max_absent_reports": 10,
    }
)
PINNED_DIAGNOSTIC_V3 = copy.deepcopy(PINNED_DIAGNOSTIC_V2)
PINNED_DIAGNOSTIC_V3.pop("support_collider_path")
PINNED_DIAGNOSTIC_V3.update(
    {
        "schema_version": 3,
        "protocol_id": V3_PROTOCOL_ID,
        "support_collider_paths": [SUPPORT_PATH, TABLE_SUPPORT_PATH],
    }
)
PINNED_DIAGNOSTIC_V4 = copy.deepcopy(PINNED_DIAGNOSTIC_V3)
PINNED_DIAGNOSTIC_V4.update(
    {
        "schema_version": 4,
        "protocol_id": V4_PROTOCOL_ID,
        "allow_active_support_pair_omission": True,
    }
)
PINNED_DIAGNOSTIC_V5 = copy.deepcopy(PINNED_DIAGNOSTIC_V4)
PINNED_DIAGNOSTIC_V5.update(
    {
        "schema_version": 5,
        "protocol_id": V5_PROTOCOL_ID,
        "topology_required_from_close_to_rise": True,
    }
)
PINNED_DIAGNOSTIC_V6 = copy.deepcopy(PINNED_DIAGNOSTIC_V5)
PINNED_DIAGNOSTIC_V6.update(
    {
        "schema_version": 6,
        "protocol_id": V6_PROTOCOL_ID,
        "topology_world_metric_distances": True,
        "contact_load_bearing_authority": True,
        "minimum_noncontact_clearance_m": 0.005,
        "topology": {
            **PINNED_DIAGNOSTIC_V5["topology"],
            "inward_face_distance_tolerance_m": 0.005,
        },
    }
)
PINNED_DIAGNOSTICS = {
    (1, V1_PROTOCOL_ID): PINNED_DIAGNOSTIC_V1,
    (2, V2_PROTOCOL_ID): PINNED_DIAGNOSTIC_V2,
    (3, V3_PROTOCOL_ID): PINNED_DIAGNOSTIC_V3,
    (4, V4_PROTOCOL_ID): PINNED_DIAGNOSTIC_V4,
    (5, V5_PROTOCOL_ID): PINNED_DIAGNOSTIC_V5,
    (6, V6_PROTOCOL_ID): PINNED_DIAGNOSTIC_V6,
}
PROTOCOL_SPECS = {
    (1, V1_PROTOCOL_ID): {
        "schema_version": 1,
        "protocol_id": V1_PROTOCOL_ID,
        "initial_support_activation_max_absent_reports": 0,
        "allow_late_initial_support_persist": False,
        "require_current_support_contact_points": False,
    },
    (2, V2_PROTOCOL_ID): {
        "schema_version": 2,
        "protocol_id": V2_PROTOCOL_ID,
        "initial_support_activation_max_absent_reports": 10,
        "allow_late_initial_support_persist": True,
        "require_current_support_contact_points": True,
    },
    (3, V3_PROTOCOL_ID): {
        "schema_version": 3,
        "protocol_id": V3_PROTOCOL_ID,
        "initial_support_activation_max_absent_reports": 10,
        "allow_late_initial_support_persist": True,
        "require_current_support_contact_points": True,
        "composite_support": True,
        "support_collider_paths": [SUPPORT_PATH, TABLE_SUPPORT_PATH],
    },
    (4, V4_PROTOCOL_ID): {
        "schema_version": 4,
        "protocol_id": V4_PROTOCOL_ID,
        "initial_support_activation_max_absent_reports": 10,
        "allow_late_initial_support_persist": True,
        "require_current_support_contact_points": True,
        "composite_support": True,
        "support_collider_paths": [SUPPORT_PATH, TABLE_SUPPORT_PATH],
        "allow_active_support_pair_omission": True,
    },
    (5, V5_PROTOCOL_ID): {
        "schema_version": 5,
        "protocol_id": V5_PROTOCOL_ID,
        "initial_support_activation_max_absent_reports": 10,
        "allow_late_initial_support_persist": True,
        "require_current_support_contact_points": True,
        "composite_support": True,
        "support_collider_paths": [SUPPORT_PATH, TABLE_SUPPORT_PATH],
        "allow_active_support_pair_omission": True,
        "topology_required_from_close_to_rise": True,
    },
    (6, V6_PROTOCOL_ID): {
        "schema_version": 6,
        "protocol_id": V6_PROTOCOL_ID,
        "initial_support_activation_max_absent_reports": 10,
        "allow_late_initial_support_persist": True,
        "require_current_support_contact_points": True,
        "composite_support": True,
        "support_collider_paths": [SUPPORT_PATH, TABLE_SUPPORT_PATH],
        "allow_active_support_pair_omission": True,
        "topology_required_from_close_to_rise": True,
        "topology_world_metric_distances": True,
        "contact_load_bearing_authority": True,
        "minimum_noncontact_clearance_m": 0.005,
    },
}
PINNED_DIAGNOSTIC = PINNED_DIAGNOSTIC_V1
CHILD_LIFECYCLE_BY_RUNTIME_STATUS = {
    "ok": "measurement_complete_pending_application_close",
    "audit_no_go": "audit_no_go_pending_application_close",
    "runtime_error": "runtime_error_pending_application_close",
}
DYNAMIC_SOURCE_ATTRIBUTE_NAMES = frozenset(
    {"physics:velocity", "physics:angularVelocity"}
)
MUTATION_PHASES = frozenset(
    {
        "pre_reset",
        "world_step",
        "task",
        "controller",
        "action",
        "close",
    }
)
BOUNDARY_RELATION_FINGERPRINT_SCHEMA = "native_unbound_relation_fingerprint_v1"
STATIC_SUPPORT_BOUNDARY_FINGERPRINT_SCHEMA = "native_unbound_static_support_fingerprint_v1"
_RELATION_INVENTORY_PAYLOAD_FIELDS = frozenset(
    {
        "relations",
        "relationship_topology",
        "applied_schemas",
        "applied_schema_resolution_complete",
    }
)
_PRODUCTION_BOUNDARY_PHASES = (
    ("after_world", "world_step"),
    ("after_task", "task"),
    ("after_controller", "controller"),
    ("after_action", "action"),
)
_CONTINUATION_BOUNDARY_PHASES = (("continuation", "world_step"),)
_DYNAMIC_MUTATION_ATTRIBUTE_NAMES = frozenset(
    {
        "physics:velocity",
        "physics:angularVelocity",
        "physxRigidBody:linearVelocity",
        "physxRigidBody:angularVelocity",
    }
)
_TENSOR_WRITER_SURFACES = frozenset(
    {
        "plural_prim_view_world_poses",
        "plural_prim_view_local_poses",
        "plural_prim_view_velocities",
        "plural_prim_view_linear_velocities",
        "plural_prim_view_angular_velocities",
        "physics_view_kinematic_targets",
        "physics_view_dynamic_targets",
        "physics_view_transforms",
        "physics_view_velocities",
        "physics_view_forces",
        "physics_view_torques",
        "physics_view_impulses",
        "physics_view_force_at_position",
    }
)
_GRIPPER_AUDIT_SURFACES = frozenset(
    {
        "gripper_add_object_to_gripper",
        "gripper_update_grasped_object_position",
        "gripper_release_object",
    }
)


class AuditNoGo(RuntimeError):
    """A missing or changed audit authority rather than a process failure."""

    def __init__(self, code: str, detail: str, *, evidence: Any = None) -> None:
        if not isinstance(code, str) or not code:
            raise ValueError("native_unbound_audit_code_invalid")
        if not isinstance(detail, str) or not detail:
            raise ValueError("native_unbound_audit_detail_invalid")
        super().__init__(f"{code}:{detail}")
        self.code = code
        self.detail = detail
        self.evidence = evidence


class ContactAuditError(ValueError):
    """A malformed or unresolved full-contact-report authority."""


def _is_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_native(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_native(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, np.ndarray):
        return _json_native(value.tolist())
    if isinstance(value, np.generic):
        return _json_native(value.item())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_native(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("native_unbound_json_nonfinite")
    return value


def _static_usd_native(value: Any) -> Any:
    """Canonicalize authored USD values without weakening live-runtime JSON checks."""

    if isinstance(value, Mapping):
        return {
            str(key): _static_usd_native(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, np.ndarray):
        return _static_usd_native(value.tolist())
    if isinstance(value, np.generic):
        return _static_usd_native(value.item())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_static_usd_native(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return {
            STATIC_USD_NONFINITE_FLOAT_TAG: (
                "nan" if math.isnan(value) else "+inf" if value > 0.0 else "-inf"
            )
        }
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    try:
        return [_static_usd_native(item) for item in value]
    except TypeError:
        return str(value)


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
        if "native_unbound_json_nonfinite" in str(exc):
            raise
        raise ValueError("native_unbound_json_invalid") from exc
    return (encoded + "\n").encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value).rstrip(b"\n"))


def runtime_diagnostics_enabled(environ: Mapping[str, str] | None = None) -> bool:
    environment = os.environ if environ is None else environ
    return environment.get(RUNTIME_DIAGNOSTICS_ENV) == "1"


class _RuntimeDiagnosticEmitter:
    """Emit opt-in stderr checkpoints without changing runtime evidence."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        stream: Any | None = None,
        pid: int | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        self.enabled = runtime_diagnostics_enabled() if enabled is None else bool(enabled)
        self.stream = sys.stderr if stream is None else stream
        self.pid = os.getpid() if pid is None else int(pid)
        self.clock = clock

    def emit(self, phase: str, event: str) -> None:
        if not self.enabled:
            return
        print(
            f"{RUNTIME_DIAGNOSTIC_PREFIX} phase={phase} event={event} "
            f"pid={self.pid} monotonic_s={float(self.clock()):.6f}",
            file=self.stream,
            flush=True,
        )

    @contextmanager
    def phase(self, name: str):
        self.emit(name, "begin")
        try:
            yield
        except BaseException as exc:
            self.emit(name, f"error:{type(exc).__name__}")
            raise
        else:
            self.emit(name, "end")


def install_runtime_diagnostic_stack_dump(
    diagnostics: _RuntimeDiagnosticEmitter,
    *,
    faulthandler_module: Any | None = None,
) -> bool:
    """Allow the parent to request a Python stack only in diagnostic runs."""

    if not diagnostics.enabled or not hasattr(signal, "SIGUSR1"):
        return False
    try:
        if faulthandler_module is None:
            import faulthandler as faulthandler_module

        faulthandler_module.register(
            signal.SIGUSR1,
            file=diagnostics.stream,
            all_threads=True,
            chain=False,
        )
    except (ImportError, OSError, RuntimeError, ValueError):
        diagnostics.emit("runtime", "stack_dump_handler_unavailable")
        return False
    diagnostics.emit("runtime", "stack_dump_handler_ready")
    return True


def _runtime_diagnostic_stack_handler_ready(stderr_path: Path) -> bool:
    try:
        return RUNTIME_DIAGNOSTIC_STACK_READY_FRAGMENT in stderr_path.read_bytes()
    except OSError:
        return False


def request_runtime_diagnostic_stack_dump(
    process: subprocess.Popen[Any],
    *,
    diagnostics_enabled: bool,
    stderr_path: Path,
    grace_seconds: float = RUNTIME_DIAGNOSTIC_STACK_DUMP_GRACE_SECONDS,
    sleep: Any = time.sleep,
) -> bool:
    """Request one stack dump from a child that confirmed its SIGUSR1 handler."""

    if (
        not diagnostics_enabled
        or not _runtime_diagnostic_stack_handler_ready(stderr_path)
        or process.poll() is not None
    ):
        return False
    try:
        os.kill(int(process.pid), signal.SIGUSR1)
    except OSError:
        return False
    sleep(float(grace_seconds))
    return True


def _publish_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            raise FileExistsError(f"native_unbound_output_exists:{path}") from exc
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_create_json(path: str | os.PathLike[str], value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise TypeError("native_unbound_json_mapping_required")
    _publish_create_only(Path(path), _canonical_json_bytes(value, indent=2))


def atomic_create_jsonl(
    path: str | os.PathLike[str], records: Sequence[Mapping[str, Any]]
) -> None:
    if isinstance(records, (str, bytes, bytearray)) or not isinstance(records, Sequence):
        raise TypeError("native_unbound_jsonl_sequence_required")
    payload = b"".join(_canonical_json_bytes(record) for record in records)
    if not payload:
        raise ValueError("native_unbound_jsonl_records_required")
    _publish_create_only(Path(path), payload)


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_key:{key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"nonfinite_constant:{value}")


def _validate_finite_json_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_finite_json_tree(item)
    elif isinstance(value, list):
        for item in value:
            _validate_finite_json_tree(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite_number")


def _decode_strict_json_line(line: bytes) -> dict[str, Any]:
    try:
        decoded = line.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(value, dict):
            raise TypeError("mapping_required")
        _validate_finite_json_tree(value)
        return value
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("native_unbound_strict_json_invalid") from exc


def load_strict_json_object(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError("native_unbound_strict_json_invalid") from exc
    if (
        not payload
        or not payload.endswith(b"\n")
        or b"\r" in payload
        or payload.endswith(b"\n\n")
    ):
        raise ValueError("native_unbound_strict_json_invalid")
    return _decode_strict_json_line(payload[:-1])


def load_strict_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise ValueError("native_unbound_strict_jsonl_invalid") from exc
    if not payload or not payload.endswith(b"\n") or b"\r" in payload:
        raise ValueError("native_unbound_strict_jsonl_invalid")
    lines = payload[:-1].split(b"\n")
    if not lines or any(not line.strip() for line in lines):
        raise ValueError("native_unbound_strict_jsonl_invalid")
    try:
        return [_decode_strict_json_line(line) for line in lines]
    except ValueError as exc:
        raise ValueError("native_unbound_strict_jsonl_invalid") from exc


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_yaml_mapping(loader: Any, node: Any, deep: bool = False) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"native_unbound_yaml_duplicate_key:{key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_yaml_mapping,
)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"native_unbound_config_parse_invalid:{path}") from exc
    if not isinstance(value, dict):
        raise ValueError("native_unbound_config_mapping_required")
    _validate_finite_json_tree(value)
    return value


def resolve_local_franka_asset(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the diagnostic-only local Franka root without consulting robot config."""

    if not isinstance(diagnostic, Mapping):
        raise ValueError("native_unbound_local_franka_metadata_invalid")
    local_franka = diagnostic.get("local_franka")
    if not isinstance(local_franka, Mapping) or set(local_franka) != {
        "usd_path",
        "sha256",
    }:
        raise ValueError("native_unbound_local_franka_metadata_invalid")
    usd_path = local_franka.get("usd_path")
    expected_sha256 = local_franka.get("sha256")
    if (
        usd_path != LOCAL_FRANKA_USD_PATH
        or expected_sha256 != LOCAL_FRANKA_SHA256
        or not _is_sha256(expected_sha256)
    ):
        raise ValueError("native_unbound_local_franka_metadata_invalid")
    relative_path = Path(usd_path)
    if relative_path.is_absolute() or ".." in relative_path.parts or relative_path == Path("."):
        raise ValueError("native_unbound_local_franka_path_invalid")
    repo_root = REPO_ROOT.resolve()
    resolved = (repo_root / relative_path).resolve()
    try:
        contained_path = resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("native_unbound_local_franka_path_invalid") from exc
    if contained_path.as_posix() != LOCAL_FRANKA_USD_PATH or not resolved.is_file():
        raise ValueError("native_unbound_local_franka_path_invalid")
    actual_sha256 = sha256_file(resolved)
    if actual_sha256 != expected_sha256:
        raise ValueError("native_unbound_local_franka_hash_mismatch")
    return {
        "usd_path": LOCAL_FRANKA_USD_PATH,
        "absolute_usd_path": str(resolved),
        "sha256": actual_sha256,
    }


def resolve_local_scene_asset(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the diagnostic-only local scene root without consulting usd_path."""

    if not isinstance(diagnostic, Mapping):
        raise ValueError("native_unbound_local_scene_metadata_invalid")
    local_scene = diagnostic.get("local_scene")
    if not isinstance(local_scene, Mapping) or set(local_scene) != {"usd_path", "sha256"}:
        raise ValueError("native_unbound_local_scene_metadata_invalid")
    usd_path = local_scene.get("usd_path")
    expected_sha256 = local_scene.get("sha256")
    if (
        usd_path != LOCAL_SCENE_USD_PATH
        or expected_sha256 != LOCAL_SCENE_SHA256
        or not _is_sha256(expected_sha256)
    ):
        raise ValueError("native_unbound_local_scene_metadata_invalid")
    relative_path = Path(usd_path)
    if relative_path.is_absolute() or ".." in relative_path.parts or relative_path == Path("."):
        raise ValueError("native_unbound_local_scene_path_invalid")
    repo_root = REPO_ROOT.resolve()
    resolved = (repo_root / relative_path).resolve()
    try:
        contained_path = resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("native_unbound_local_scene_path_invalid") from exc
    if contained_path.as_posix() != LOCAL_SCENE_USD_PATH or not resolved.is_file():
        raise ValueError("native_unbound_local_scene_path_invalid")
    actual_sha256 = sha256_file(resolved)
    if actual_sha256 != expected_sha256:
        raise ValueError("native_unbound_local_scene_hash_mismatch")
    return {
        "usd_path": LOCAL_SCENE_USD_PATH,
        "absolute_usd_path": str(resolved),
        "sha256": actual_sha256,
    }


def create_diagnostic_local_franka(
    create_robot: Any,
    config: Mapping[str, Any],
    *,
    local_franka: Mapping[str, Any],
) -> Any:
    """Construct the diagnostic robot from its sealed local asset metadata."""

    if not callable(create_robot) or not isinstance(config, Mapping):
        raise ValueError("native_unbound_local_franka_create_contract_invalid")
    expected_local_franka = resolve_local_franka_asset(config.get("diagnostic", {}))
    if dict(local_franka) != expected_local_franka:
        raise ValueError("native_unbound_local_franka_create_contract_invalid")
    robot = config.get("robot")
    if not isinstance(robot, Mapping) or not isinstance(robot.get("type"), str):
        raise ValueError("native_unbound_local_franka_create_contract_invalid")
    try:
        position = np.asarray(robot["position"], dtype=np.float64)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("native_unbound_local_franka_create_contract_invalid") from exc
    if position.shape != (3,) or not np.isfinite(position).all():
        raise ValueError("native_unbound_local_franka_create_contract_invalid")
    return create_robot(
        str(robot["type"]),
        position=position,
        usd_path=expected_local_franka["absolute_usd_path"],
    )


def _protocol_key(value: Mapping[str, Any]) -> tuple[int, str]:
    schema_version = value.get("schema_version")
    protocol_id = value.get("protocol_id")
    if type(schema_version) is not int or not isinstance(protocol_id, str) or not protocol_id:
        raise ValueError("native_unbound_pinned_contract_mismatch")
    return schema_version, protocol_id


def _require_protocol_spec(protocol: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(protocol, Mapping):
        raise ValueError("native_unbound_protocol_spec_invalid")
    key = _protocol_key(protocol)
    expected = PROTOCOL_SPECS.get(key)
    if (
        expected is None
        or _canonical_json_bytes(dict(protocol)) != _canonical_json_bytes(expected)
    ):
        raise ValueError("native_unbound_protocol_spec_invalid")
    return copy.deepcopy(expected)


def _protocol_spec_for_diagnostic(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    key = _protocol_key(diagnostic)
    expected = PINNED_DIAGNOSTICS.get(key)
    if (
        expected is None
        or _canonical_json_bytes(dict(diagnostic)) != _canonical_json_bytes(expected)
    ):
        raise ValueError("native_unbound_pinned_contract_mismatch")
    return copy.deepcopy(PROTOCOL_SPECS[key])


def _diagnostic_support_collider_paths(diagnostic: Mapping[str, Any]) -> list[str]:
    spec = _protocol_spec_for_diagnostic(diagnostic)
    if spec.get("composite_support") is True:
        paths = diagnostic.get("support_collider_paths")
        if (
            not isinstance(paths, list)
            or paths != spec["support_collider_paths"]
            or len(set(paths)) != len(paths)
        ):
            raise ValueError("native_unbound_support_collider_paths_invalid")
        return copy.deepcopy(paths)
    path = diagnostic.get("support_collider_path")
    if not isinstance(path, str) or not path:
        raise ValueError("native_unbound_support_collider_path_invalid")
    return [path]


def _require_pinned_diagnostic(config: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        raise ValueError("native_unbound_config_mapping_required")
    diagnostic = config.get("diagnostic")
    if not isinstance(diagnostic, Mapping):
        raise ValueError("native_unbound_diagnostic_missing")
    value = dict(diagnostic)
    resolve_local_franka_asset(value)
    resolve_local_scene_asset(value)
    _protocol_spec_for_diagnostic(value)
    return value


def resolve_protocol_spec(config: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the exact frozen protocol selected by a diagnostic config."""

    return _protocol_spec_for_diagnostic(_require_pinned_diagnostic(config))


def production_visible_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        raise TypeError("native_unbound_config_mapping_required")
    projected = copy.deepcopy(dict(config))
    for field in PROJECTION_ONLY_FIELDS:
        projected.pop(field, None)
    return json.loads(_canonical_json_bytes(projected).decode("utf-8"))


def _validate_relative_output_route(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("native_unbound_output_route_invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise ValueError("native_unbound_output_route_invalid")
    return value


def freeze_diagnostic_config(
    config_path: str | os.PathLike[str],
    *,
    production_config_path: str | os.PathLike[str] = PRODUCTION_CONFIG,
) -> dict[str, Any]:
    path = Path(config_path).resolve()
    production_path = Path(production_config_path).resolve()
    config = _load_yaml_mapping(path)
    production = _load_yaml_mapping(production_path)
    diagnostic = _require_pinned_diagnostic(config)
    local_franka = resolve_local_franka_asset(diagnostic)
    local_scene = resolve_local_scene_asset(diagnostic)
    if (
        config.get("max_episodes") != 1
        or config.get("usd_path") != "assets/chemistry_lab/lab_001/lab_001.usd"
        or not isinstance(config.get("robot"), Mapping)
    ):
        raise ValueError("native_unbound_pinned_contract_mismatch")
    hydra = config.get("hydra")
    multi_run = config.get("multi_run")
    if not isinstance(hydra, Mapping) or not isinstance(multi_run, Mapping):
        raise ValueError("native_unbound_output_route_invalid")
    run = hydra.get("run")
    if not isinstance(run, Mapping):
        raise ValueError("native_unbound_output_route_invalid")
    if (
        _validate_relative_output_route(run.get("dir")) != "hydra"
        or _validate_relative_output_route(multi_run.get("run_dir")) != "collector"
    ):
        raise ValueError("native_unbound_output_route_invalid")
    if production_visible_projection(config) != production_visible_projection(production):
        raise ValueError("native_unbound_production_projection_mismatch")
    canonical = _canonical_json_bytes(config)
    return {
        "config": config,
        "canonical_bytes": canonical,
        "sha256": _sha256_bytes(canonical),
        "source_path": str(path),
        "source_sha256": sha256_file(path),
        "production_path": str(production_path),
        "production_sha256": sha256_file(production_path),
        "production_projection_sha256": _canonical_json_sha256(
            production_visible_projection(production)
        ),
        "local_franka": local_franka,
        "local_scene": local_scene,
    }


def write_frozen_config(
    canonical_bytes: bytes, treatment_dir: str | os.PathLike[str]
) -> Path:
    if not isinstance(canonical_bytes, bytes) or not canonical_bytes.endswith(b"\n"):
        raise ValueError("native_unbound_frozen_config_bytes_invalid")
    config = _decode_strict_json_line(canonical_bytes[:-1])
    if _canonical_json_bytes(config) != canonical_bytes:
        raise ValueError("native_unbound_frozen_config_not_canonical")
    directory = Path(treatment_dir).resolve()
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(directory, 0o700)
    path = directory / FROZEN_CONFIG_BASENAME
    _publish_create_only(path, canonical_bytes)
    os.chmod(path, 0o600)
    return path


def build_child_command(
    *,
    treatment: str,
    frozen_config_path: str | os.PathLike[str],
    treatment_dir: str | os.PathLike[str],
    run_nonce: str,
    parent_pid: int,
    expected_config_sha256: str,
    python_executable: str | os.PathLike[str] = sys.executable,
) -> list[str]:
    if treatment not in TREATMENTS:
        raise ValueError("native_unbound_treatment_invalid")
    if not isinstance(run_nonce, str) or not run_nonce:
        raise ValueError("native_unbound_run_nonce_invalid")
    if type(parent_pid) is not int or parent_pid <= 0:
        raise ValueError("native_unbound_parent_pid_invalid")
    if not _is_sha256(expected_config_sha256):
        raise ValueError("native_unbound_config_sha256_invalid")
    return [
        str(Path(python_executable).resolve()),
        str(Path(__file__).resolve()),
        "--runtime-child",
        "--headless",
        "--treatment",
        treatment,
        "--frozen-config",
        str(Path(frozen_config_path).resolve()),
        "--out-dir",
        str(Path(treatment_dir).resolve()),
        "--run-nonce",
        run_nonce,
        "--parent-pid",
        str(parent_pid),
        "--expected-config-sha256",
        expected_config_sha256,
    ]


def select_decision(components: Mapping[str, Any]) -> str:
    expected = {"runtime_error", "audit_no_go", "physical_passed"}
    if (
        not isinstance(components, Mapping)
        or set(components) != expected
        or any(type(components[name]) is not bool for name in expected)
    ):
        raise ValueError("native_unbound_decision_components_invalid")
    if components["runtime_error"]:
        return DECISIONS[0]
    if components["audit_no_go"]:
        return DECISIONS[1]
    if not components["physical_passed"]:
        return DECISIONS[2]
    return DECISIONS[3]


def classify_parent_result(
    *, runtime_error: bool, audit_no_go: bool, physical_passed: bool
) -> dict[str, Any]:
    components = {
        "runtime_error": runtime_error,
        "audit_no_go": audit_no_go,
        "physical_passed": physical_passed,
    }
    decision = select_decision(components)
    return {
        "decision": decision,
        "lifecycle_status": "failed"
        if decision == "PROBE_RUNTIME_ERROR"
        else "completed",
        "clean_physical_failure": decision == "NATIVE_EXPERT_UNBOUND_LIFT_FAIL",
    }


def _finite_scalar(value: Any, *, field: str, nonnegative: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
        or (nonnegative and float(value) < 0.0)
    ):
        raise ValueError(f"native_unbound_{field}_invalid")
    return float(value)


def _finite_vector(value: Any, *, field: str, length: int = 3, unit: bool = False) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"native_unbound_{field}_invalid") from exc
    if result.shape != (length,) or not np.isfinite(result).all():
        raise ValueError(f"native_unbound_{field}_invalid")
    if unit:
        norm = float(np.linalg.norm(result))
        if norm <= 1.0e-12:
            raise ValueError(f"native_unbound_{field}_invalid")
        result = result / norm
    result[result == 0.0] = 0.0
    return result


def _matrix4(value: Any, *, field: str) -> np.ndarray:
    try:
        matrix = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"native_unbound_{field}_invalid") from exc
    if (
        matrix.shape != (4, 4)
        or not np.isfinite(matrix).all()
        or abs(float(np.linalg.det(matrix))) <= 1.0e-15
    ):
        raise ValueError(f"native_unbound_{field}_invalid")
    return matrix


def _quaternion_angle_degrees(first: Any, second: Any) -> float:
    one = _finite_vector(first, field="quaternion", length=4)
    two = _finite_vector(second, field="quaternion", length=4)
    first_norm = float(np.linalg.norm(one))
    second_norm = float(np.linalg.norm(two))
    if first_norm <= 1.0e-12 or second_norm <= 1.0e-12:
        raise ValueError("native_unbound_quaternion_invalid")
    cosine = float(np.clip(abs((one / first_norm) @ (two / second_norm)), 0.0, 1.0))
    return math.degrees(2.0 * math.acos(cosine))


def evaluate_dynamic_source_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    audit_failures: list[str] = []
    physical_failures: list[str] = []
    try:
        if not isinstance(contract, Mapping):
            raise ValueError("contract_mapping_required")
        required = {
            "source_body_path": SOURCE_BODY_PATH,
            "source_collider_path": SOURCE_BODY_PATH,
        }
        for name, expected in required.items():
            if contract.get(name) != expected:
                audit_failures.append("source_identity_or_scene_owner_invalid")
        owner = contract.get("scene_owner")
        owners = contract.get("simulation_owner_targets")
        active_scene = contract.get("active_scene_contract")
        membership = contract.get("live_physics_membership")
        active_scene_valid = bool(
            isinstance(active_scene, Mapping)
            and active_scene.get("valid") is True
            and active_scene.get("physics_context_path") == "/physicsScene"
            and isinstance(active_scene.get("physics_scene_paths"), list)
            and "/physicsScene" in active_scene["physics_scene_paths"]
        )
        required_membership_readbacks = {
            "world_pose",
            "linear_velocity",
            "angular_velocity",
            "physx_is_sleeping",
        }
        membership_valid = bool(
            isinstance(membership, Mapping)
            and membership.get("source_body_path") == SOURCE_BODY_PATH
            and membership.get("adapter_initialized") is True
            and membership.get("valid") is True
            and isinstance(membership.get("readbacks"), Mapping)
            and set(membership["readbacks"]) == required_membership_readbacks
            and all(membership["readbacks"].get(name) is True for name in required_membership_readbacks)
        )
        if membership_valid:
            try:
                _state_authority(membership.get("state"))
            except (TypeError, ValueError):
                membership_valid = False
        explicit_owner_valid = owner == "/physicsScene" and owners == ["/physicsScene"]
        default_owner_valid = owner is None and owners == [] and active_scene_valid and membership_valid
        if not explicit_owner_valid and not default_owner_valid:
            audit_failures.append("source_identity_or_scene_owner_invalid")
        if type(contract.get("stage_id")) is not int:
            audit_failures.append("stage_identity_missing")
        readbacks = contract.get("motion_readbacks")
        required_readbacks = {
            "world_pose",
            "linear_velocity",
            "angular_velocity",
            "physx_is_sleeping",
        }
        if (
            not isinstance(readbacks, Mapping)
            or set(readbacks) != required_readbacks
            or any(readbacks[name] is not True for name in required_readbacks)
        ):
            audit_failures.append("motion_authority_missing")
        for name in (
            "rigid_body_enabled",
            "collision_enabled",
            "gravity_enabled",
            "kinematic_enabled",
            "awake",
        ):
            if type(contract.get(name)) is not bool:
                audit_failures.append("dynamic_source_property_authority_missing")
                break
        if contract.get("rigid_body_enabled") is not True:
            physical_failures.append("source_not_rigid")
        if contract.get("collision_enabled") is not True:
            physical_failures.append("source_collision_disabled")
        if contract.get("gravity_enabled") is not True:
            physical_failures.append("source_gravity_disabled")
        if contract.get("kinematic_enabled") is not False:
            physical_failures.append("source_kinematic")
        if contract.get("awake") is not True:
            physical_failures.append("source_not_awake")
        metric = contract.get("body_origin_metric")
        if (
            not isinstance(metric, Mapping)
            or metric.get("metric") != "rigid_body_origin"
            or metric.get("valid") is not True
            or not isinstance(metric.get("authored_center_of_mass_overrides"), list)
            or metric.get("authored_center_of_mass_overrides")
        ):
            audit_failures.append("source_center_of_mass_authority_invalid")
        local_com = contract.get("source_local_com_authority")
        if local_com is None:
            audit_failures.append("source_local_com_authority_missing")
        elif (
            not isinstance(local_com, Mapping)
            or local_com.get("kind") != "physx_cooked_rigid_body_properties"
            or local_com.get("source_body_path") != SOURCE_BODY_PATH
            or local_com.get("stage_id") != contract.get("stage_id")
            or local_com.get("query_complete") is not True
            or local_com.get("query_timing") != "pre_task_reset_nonplaying"
            or type(local_com.get("world_counter_before")) is not int
            or local_com.get("world_counter_before") != local_com.get("world_counter_after")
            or not _is_sha256(local_com.get("sealed_sha256"))
        ):
            audit_failures.append("source_local_com_authority_invalid")
        else:
            try:
                if _finite_scalar(
                    local_com.get("mass_kg"), field="source_cooked_mass", nonnegative=True
                ) <= 0.0:
                    audit_failures.append("source_local_com_authority_invalid")
                _finite_vector(
                    local_com.get("center_of_mass_local_m"), field="source_local_com"
                )
                inertia = _finite_vector(
                    local_com.get("diagonal_inertia_kg_m2"), field="source_cooked_inertia"
                )
                if np.any(inertia < 0.0):
                    audit_failures.append("source_local_com_authority_invalid")
            except ValueError:
                audit_failures.append("source_local_com_authority_invalid")
        adapter = contract.get("read_only_adapter")
        if (
            not isinstance(adapter, Mapping)
            or adapter.get("kind") != "omni.isaac.core.prims.RigidPrimView"
            or adapter.get("source_body_path") != SOURCE_BODY_PATH
            or adapter.get("count") != 1
            or adapter.get("initialized") is not True
            or adapter.get("reset_xform_properties") is not False
            or adapter.get("prepare_contact_sensors") is not False
            or adapter.get("read_only") is not True
            or adapter.get("readbacks")
            != {
                "world_pose": True,
                "linear_velocity": True,
                "angular_velocity": True,
            }
        ):
            audit_failures.append("source_read_adapter_authority_missing")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    physical_failures = sorted(set(physical_failures))
    return {
        "audit_valid": not audit_failures,
        "physical_valid": bool(not audit_failures and not physical_failures),
        "audit_failures": audit_failures,
        "physical_failures": physical_failures,
    }


def _path_partition(path: str, *, support_paths: Sequence[str] = (SUPPORT_PATH,)) -> str:
    if path == SOURCE_ROOT_PATH or path.startswith(
        (SOURCE_ROOT_PATH + "/", SOURCE_ROOT_PATH + ".")
    ):
        return "source"
    if path == ROBOT_ROOT_PATH or path.startswith(
        (ROBOT_ROOT_PATH + "/", ROBOT_ROOT_PATH + ".")
    ):
        return "robot"
    for support_path in support_paths:
        if path == support_path or path.startswith(
            (support_path + "/", support_path + ".")
        ):
            return "support"
    return "other"


def _endpoint_partitions(path: str) -> set[str]:
    """Resolve direct and broad relationship endpoints against protected roots."""

    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("relation_endpoint_path_invalid")
    partitions = {_path_partition(path)}
    ancestor = path.rstrip("/") or "/"
    for partition, root in (
        ("source", SOURCE_ROOT_PATH),
        ("robot", ROBOT_ROOT_PATH),
        ("support", SUPPORT_PATH),
    ):
        if ancestor == "/" or root == ancestor or root.startswith(ancestor + "/"):
            partitions.add(partition)
    return partitions


def _is_semantic_relation_mutation(event: Mapping[str, Any]) -> bool:
    path = event.get("path")
    kind = event.get("kind")
    fields = event.get("fields")
    if (
        not isinstance(path, str)
        or not path
        or kind not in {"info", "resync"}
        or not isinstance(fields, Sequence)
        or isinstance(fields, (str, bytes, bytearray))
        or any(not isinstance(field, str) for field in fields)
    ):
        raise ValueError("coupling_mutation_event_invalid")
    if kind == "resync":
        # A resync does not expose a field-level delta. During the sealed epoch
        # it could have created and removed a relation before boundary inventory.
        return True
    leaf = path.rsplit("/", 1)[-1]
    property_name = leaf.rsplit(".", 1)[-1] if "." in leaf else ""
    text = " ".join((*fields, property_name)).lower()
    return any(
        token in text
        for token in (
            "relationship",
            "targetpath",
            "apischemas",
            "schema",
            "typename",
            "specifier",
            "collection",
            "collisiongroup",
            "filtered",
            "filter",
            "mask",
            "merge",
            "joint",
            "constraint",
            "attachment",
            "gripper",
            "force",
        )
    )


def evaluate_coupling_inventory(inventory: Mapping[str, Any]) -> dict[str, Any]:
    audit_failures: list[str] = []
    try:
        if not isinstance(inventory, Mapping):
            raise ValueError("coupling_inventory_mapping_required")
        raw_relations = inventory.get("relations")
        if (
            not isinstance(raw_relations, Sequence)
            or isinstance(raw_relations, (str, bytes, bytearray))
        ):
            raise ValueError("coupling_relations_missing")
        allowed_kinds = {
            "joint",
            "constraint",
            "attachment",
            "surface_gripper",
            "d6",
            "fixed",
            "filtered_pairs",
            "filter",
            "collision_group",
            "collection",
            "mask",
            "merge_group",
            "force_field_membership",
            "external_constraint",
            "ordinary_static_support",
            "generic",
        }
        collision_treatment_kinds = {
            "filtered_pairs",
            "filter",
            "collision_group",
            "collection",
            "mask",
            "merge_group",
        }
        graph: dict[str, set[str]] = {}
        direct = False
        source_external = False
        relation_keys: set[tuple[str, str]] = set()
        for relation in raw_relations:
            if not isinstance(relation, Mapping):
                raise ValueError("coupling_relation_invalid")
            kind = relation.get("kind")
            endpoints = relation.get("endpoints")
            if kind not in allowed_kinds:
                audit_failures.append("unsupported_relation_kind")
                continue
            if (
                not isinstance(endpoints, Sequence)
                or isinstance(endpoints, (str, bytes, bytearray))
                or len(endpoints) < 2
                or any(not isinstance(path, str) or not path for path in endpoints)
            ):
                audit_failures.append("unsupported_relation_endpoint")
                continue
            paths = list(dict.fromkeys(endpoints))
            if len(paths) < 2 or relation.get("identity_valid", True) is not True:
                audit_failures.append("unsupported_relation_endpoint")
                continue
            owner = relation.get("owner_path")
            relationship = relation.get("relationship")
            if owner is not None and (not isinstance(owner, str) or not owner):
                audit_failures.append("unsupported_relation_endpoint")
                continue
            if relationship is not None and (not isinstance(relationship, str) or not relationship):
                audit_failures.append("unsupported_relation_endpoint")
                continue
            if owner is not None and relationship is not None:
                relation_keys.add((owner, relationship))
            endpoint_partitions = {
                path: sorted(_endpoint_partitions(path)) for path in paths
            }
            recorded_partitions = relation.get("endpoint_partitions")
            if recorded_partitions is not None and recorded_partitions != endpoint_partitions:
                audit_failures.append("relation_endpoint_partition_invalid")
            kinds = {
                partition
                for partitions in endpoint_partitions.values()
                for partition in partitions
            }
            if kind == "ordinary_static_support":
                if kinds != {"source", "support"}:
                    audit_failures.append("invalid_static_support_relation")
                    continue
            else:
                if "source" in kinds:
                    audit_failures.append("source_relation_not_explicit_static_support")
                if "source" in kinds and "robot" in kinds:
                    direct = True
                elif "source" in kinds and ("other" in kinds or "support" in kinds):
                    source_external = True
                if kind in collision_treatment_kinds and len(kinds) > 1:
                    audit_failures.append("unknown_cross_root_collision_treatment")
                    if relation.get("schema_resolution_complete") is not True:
                        audit_failures.append("unresolved_cross_root_collision_treatment")
            for index, first in enumerate(paths):
                graph.setdefault(first, set()).update(
                    path for path in paths[index + 1 :] if path != first
                )
                for second in paths[index + 1 :]:
                    graph.setdefault(second, set()).add(first)
        topology = inventory.get("relationship_topology")
        if topology is not None:
            if (
                not isinstance(topology, Sequence)
                or isinstance(topology, (str, bytes, bytearray))
            ):
                raise ValueError("relationship_topology_invalid")
            for record in topology:
                if not isinstance(record, Mapping):
                    raise ValueError("relationship_topology_invalid")
                owner = record.get("owner_path")
                name = record.get("relationship")
                targets = record.get("targets")
                if (
                    not isinstance(owner, str)
                    or not owner
                    or not isinstance(name, str)
                    or not name
                    or not isinstance(targets, Sequence)
                    or isinstance(targets, (str, bytes, bytearray))
                    or any(not isinstance(target, str) or not target for target in targets)
                ):
                    raise ValueError("relationship_topology_invalid")
                if (
                    targets
                    and not name.startswith("material:binding")
                    and name != "physics:simulationOwner"
                    and (owner, name) not in relation_keys
                ):
                    audit_failures.append("relationship_topology_unresolved")
        if direct:
            audit_failures.append("direct_source_robot_coupling")
        if source_external:
            audit_failures.append("source_external_driving_relation")
        source_nodes = [path for path in graph if _path_partition(path) == "source"]
        reachable = set(source_nodes)
        queue = deque(source_nodes)
        while queue:
            current = queue.popleft()
            for target in graph.get(current, ()):
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
        if not direct and any(_path_partition(path) == "robot" for path in reachable):
            audit_failures.append("transitive_source_robot_coupling")
        if inventory.get("mutation_create_remove_detected") is True:
            audit_failures.append("coupling_create_remove_detected")
        applied_schemas = inventory.get("applied_schemas", [])
        if (
            not isinstance(applied_schemas, Sequence)
            or isinstance(applied_schemas, (str, bytes, bytearray))
        ):
            raise ValueError("coupling_applied_schemas_invalid")
        for record in applied_schemas:
            if not isinstance(record, Mapping):
                raise ValueError("coupling_applied_schema_invalid")
            path = record.get("path")
            schemas = record.get("schemas")
            if (
                not isinstance(path, str)
                or not path
                or not isinstance(schemas, Sequence)
                or isinstance(schemas, (str, bytes, bytearray))
                or any(not isinstance(schema, str) or not schema for schema in schemas)
                or len(set(schemas)) != len(schemas)
            ):
                raise ValueError("coupling_applied_schema_invalid")
            normalized = " ".join(schemas).lower()
            if "source" in _endpoint_partitions(path) and any(
                token in normalized
                for token in (
                    "force",
                    "attachment",
                    "joint",
                    "constraint",
                    "drive",
                    "gripper",
                    "collisiongroup",
                    "collection",
                    "filter",
                    "mask",
                    "merge",
                )
            ):
                audit_failures.append("source_relevant_applied_schema")
        mutation_events = inventory.get("mutation_events", [])
        if (
            not isinstance(mutation_events, Sequence)
            or isinstance(mutation_events, (str, bytes, bytearray))
        ):
            raise ValueError("coupling_mutation_events_invalid")
        for event in mutation_events:
            if not isinstance(event, Mapping):
                raise ValueError("coupling_mutation_event_invalid")
            if _is_semantic_relation_mutation(event):
                # A semantic relationship can be owned by an external collection or
                # collision group, so its owner path cannot be ignored.
                audit_failures.append("external_relation_mutation_detected")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {
        "audit_valid": not audit_failures,
        "audit_failures": audit_failures,
    }


def evaluate_reset_coupling_inventories(
    before_reset: Mapping[str, Any], after_reset: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate both task-initialization endpoints without requiring global equality."""

    before = evaluate_coupling_inventory(before_reset)
    after = evaluate_coupling_inventory(after_reset)
    audit_failures = sorted(set([*before["audit_failures"], *after["audit_failures"]]))
    return {
        "audit_valid": not audit_failures,
        "audit_failures": audit_failures,
        "before_reset": before,
        "after_reset": after,
    }


def _validate_snapshot(snapshot: Any, *, required: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(snapshot, Mapping) or not required <= set(snapshot):
        raise ValueError(f"{field}_invalid")
    _canonical_json_bytes(snapshot)
    return snapshot


def evaluate_cube_immutability(
    baseline: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    mutation_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    audit_failures: list[str] = []
    try:
        required = {
            "world_matrix",
            "rigid_body_enabled",
            "kinematic_enabled",
            "velocities",
            "force_constraint_membership",
            "collision_properties",
            "material_bindings",
            "group_filter_relationships",
            "descendant_physics_state",
            "support_contract",
        }
        initial = _validate_snapshot(
            baseline, required=required, field="cube_baseline_snapshot"
        )
        def static_support_contract(snapshot: Mapping[str, Any]) -> bool:
            contract = snapshot.get("support_contract")
            state = snapshot.get("descendant_physics_state")
            velocities = snapshot.get("velocities")
            if (
                not isinstance(contract, Mapping)
                or contract.get("static") is not True
                or contract.get("nonkinematic") is not True
                or contract.get("nonmoving") is not True
                or not isinstance(contract.get("dynamic_descendant_paths"), list)
                or contract["dynamic_descendant_paths"]
                or snapshot.get("rigid_body_enabled") is True
                or snapshot.get("kinematic_enabled") is True
                or not isinstance(velocities, Mapping)
                or not isinstance(state, Mapping)
                or not {
                    "colliders",
                    "material_bindings",
                    "relationships",
                    "applied_schemas",
                    "body_state",
                    "motion_state",
                } <= set(state)
                or not isinstance(state.get("colliders"), Mapping)
                or not isinstance(state.get("relationships"), (Mapping, list))
                or not isinstance(state.get("applied_schemas"), list)
                or not isinstance(state.get("body_state"), Mapping)
                or not isinstance(state.get("motion_state"), Mapping)
            ):
                return False

            def zero_or_absent(value: Any) -> bool:
                if value is None:
                    return True
                try:
                    vector = _finite_vector(value, field="cube_snapshot_velocity")
                except ValueError:
                    return False
                return bool(np.allclose(vector, np.zeros(3), rtol=0.0, atol=1.0e-12))

            if not all(
                zero_or_absent(velocities.get(name)) for name in ("linear", "angular")
            ):
                return False
            for motion in state["motion_state"].values():
                if not isinstance(motion, Mapping) or not all(
                    zero_or_absent(motion.get(name)) for name in ("linear", "angular")
                ):
                    return False
            dynamic_paths = []
            any_kinematic = False
            for path, body in state["body_state"].items():
                if not isinstance(path, str) or not isinstance(body, Mapping):
                    return False
                has_body = body.get("rigid_body_api")
                enabled = body.get("rigid_body_enabled")
                kinematic = body.get("kinematic_enabled")
                if type(has_body) is not bool:
                    return False
                if not has_body:
                    if enabled is not None or kinematic is not None:
                        return False
                    continue
                if type(enabled) is not bool or type(kinematic) is not bool:
                    return False
                if enabled:
                    dynamic_paths.append(path)
                if kinematic:
                    any_kinematic = True
            if (
                sorted(dynamic_paths) != contract.get("dynamic_descendant_paths")
                or contract.get("static") is not (not dynamic_paths)
                or contract.get("nonkinematic") is not (not any_kinematic)
            ):
                return False
            return True

        if not static_support_contract(initial):
            audit_failures.append("cube_support_contract_invalid")
        if (
            not isinstance(snapshots, Sequence)
            or isinstance(snapshots, (str, bytes, bytearray))
            or not snapshots
        ):
            raise ValueError("cube_boundary_snapshots_missing")
        initial_bytes = _canonical_json_bytes(initial)
        for snapshot in snapshots:
            current = _validate_snapshot(
                snapshot, required=required, field="cube_boundary_snapshot"
            )
            if _canonical_json_bytes(current) != initial_bytes:
                audit_failures.append("cube_snapshot_changed")
            if not static_support_contract(current):
                audit_failures.append("cube_support_contract_invalid")
        if (
            not isinstance(mutation_events, Sequence)
            or isinstance(mutation_events, (str, bytes, bytearray))
        ):
            raise ValueError("cube_mutation_events_invalid")
        for event in mutation_events:
            if not isinstance(event, Mapping) or not isinstance(event.get("path"), str):
                raise ValueError("cube_mutation_events_invalid")
            path = event["path"]
            if _path_partition(path) == "support":
                audit_failures.append("cube_mutation_notice")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {"audit_valid": not audit_failures, "audit_failures": audit_failures}


def evaluate_static_support_immutability(
    baseline: Mapping[str, Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Mapping[str, Any]]],
    mutation_events: Sequence[Mapping[str, Any]],
    *,
    support_paths: Sequence[str],
) -> dict[str, Any]:
    """Validate the exact v3 support set without changing the v1/v2 Cube audit."""

    audit_failures: list[str] = []
    try:
        if (
            not isinstance(support_paths, Sequence)
            or isinstance(support_paths, (str, bytes, bytearray))
            or list(support_paths) != [SUPPORT_PATH, TABLE_SUPPORT_PATH]
            or not isinstance(baseline, Mapping)
            or set(baseline) != set(support_paths)
        ):
            raise ValueError("static_support_paths_invalid")

        required = {
            "support_path",
            "world_matrix",
            "rigid_body_enabled",
            "kinematic_enabled",
            "velocities",
            "force_constraint_membership",
            "collision_properties",
            "material_bindings",
            "group_filter_relationships",
            "descendant_physics_state",
            "support_contract",
            "ancestor_body_state",
        }

        def valid_body_state(value: Any) -> bool:
            if not isinstance(value, Mapping):
                return False
            for path, body in value.items():
                if not isinstance(path, str) or not isinstance(body, Mapping):
                    return False
                has_body = body.get("rigid_body_api")
                enabled = body.get("rigid_body_enabled")
                kinematic = body.get("kinematic_enabled")
                if type(has_body) is not bool:
                    return False
                if not has_body:
                    if enabled is not None or kinematic is not None:
                        return False
                elif (
                    type(enabled) is not bool
                    or type(kinematic) is not bool
                    or enabled
                    or kinematic
                ):
                    return False
            return True

        def valid_snapshot(path: str, snapshot: Any, *, field: str) -> Mapping[str, Any]:
            value = _validate_snapshot(snapshot, required=required, field=field)
            collision = value.get("collision_properties")
            if (
                value.get("support_path") != path
                or not isinstance(collision, Mapping)
                or collision.get("enabled") is not True
                or not valid_body_state(value.get("ancestor_body_state"))
            ):
                raise ValueError("static_support_contract_invalid")
            # The existing evaluator validates the static descendant and motion contract.
            if not evaluate_cube_immutability(value, [value], [])["audit_valid"]:
                raise ValueError("static_support_contract_invalid")
            return value

        initial = {
            path: valid_snapshot(path, baseline[path], field="static_support_baseline")
            for path in support_paths
        }
        if (
            not isinstance(snapshots, Sequence)
            or isinstance(snapshots, (str, bytes, bytearray))
            or not snapshots
        ):
            raise ValueError("static_support_boundary_snapshots_missing")
        initial_bytes = {
            path: _canonical_json_bytes(snapshot) for path, snapshot in initial.items()
        }
        for snapshot_map in snapshots:
            if not isinstance(snapshot_map, Mapping) or set(snapshot_map) != set(support_paths):
                raise ValueError("static_support_boundary_snapshot_invalid")
            for path in support_paths:
                current = valid_snapshot(
                    path,
                    snapshot_map[path],
                    field="static_support_boundary",
                )
                if _canonical_json_bytes(current) != initial_bytes[path]:
                    audit_failures.append("static_support_snapshot_changed")
        if (
            not isinstance(mutation_events, Sequence)
            or isinstance(mutation_events, (str, bytes, bytearray))
        ):
            raise ValueError("static_support_mutation_events_invalid")
        for event in mutation_events:
            path, _kind, _fields = _mutation_event_parts(event)
            if any(
                path == support
                or path.startswith((support + "/", support + "."))
                or support.startswith(path.rstrip("/") + "/")
                for support in support_paths
            ):
                audit_failures.append("static_support_mutation_notice")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {"audit_valid": not audit_failures, "audit_failures": audit_failures}


def _static_support_boundary_fingerprint(snapshot: Mapping[str, Any]) -> dict[str, str]:
    path = snapshot.get("support_path") if isinstance(snapshot, Mapping) else None
    if not isinstance(path, str) or not path:
        raise ValueError("static_support_boundary_fingerprint_invalid")
    return {
        "schema": STATIC_SUPPORT_BOUNDARY_FINGERPRINT_SCHEMA,
        "support_path": path,
        "sha256": _canonical_json_sha256(snapshot),
    }


def evaluate_static_support_boundary_fingerprints(
    baseline: Mapping[str, Mapping[str, Any]],
    fingerprints: Sequence[Mapping[str, Mapping[str, str]]],
    *,
    support_paths: Sequence[str],
) -> dict[str, Any]:
    audit_failures: list[str] = []
    try:
        baseline_check = evaluate_static_support_immutability(
            baseline,
            [baseline],
            [],
            support_paths=support_paths,
        )
        if not baseline_check["audit_valid"]:
            audit_failures.extend(baseline_check["audit_failures"])
            raise ValueError("static_support_baseline_invalid")
        expected = {
            path: _static_support_boundary_fingerprint(baseline[path])
            for path in support_paths
        }
        if (
            not isinstance(fingerprints, Sequence)
            or isinstance(fingerprints, (str, bytes, bytearray))
        ):
            raise ValueError("static_support_boundary_fingerprints_invalid")
        for fingerprint_map in fingerprints:
            if not isinstance(fingerprint_map, Mapping) or set(fingerprint_map) != set(support_paths):
                raise ValueError("static_support_boundary_fingerprint_invalid")
            for path in support_paths:
                fingerprint = fingerprint_map[path]
                if (
                    not isinstance(fingerprint, Mapping)
                    or fingerprint != expected[path]
                ):
                    audit_failures.append("static_support_boundary_changed")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {"audit_valid": not audit_failures, "audit_failures": audit_failures}


def evaluate_source_robot_property_mutations(
    baseline: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    mutation_events: Sequence[Mapping[str, Any]],
    *,
    pre_reset_mutation_events: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    audit_failures: list[str] = []
    try:
        required = {"source", "left_finger", "right_finger", "hand"}
        initial = _validate_snapshot(
            baseline, required=required, field="source_robot_property_baseline"
        )
        if (
            not isinstance(snapshots, Sequence)
            or isinstance(snapshots, (str, bytes, bytearray))
            or not snapshots
        ):
            raise ValueError("source_robot_property_snapshots_missing")
        initial_bytes = _canonical_json_bytes(_without_report_metadata(initial))
        for snapshot in snapshots:
            current = _validate_snapshot(
                snapshot, required=required, field="source_robot_property_snapshot"
            )
            if _canonical_json_bytes(_without_report_metadata(current)) != initial_bytes:
                audit_failures.append("source_robot_physical_properties_changed")
        if (
            not isinstance(pre_reset_mutation_events, Sequence)
            or isinstance(pre_reset_mutation_events, (str, bytes, bytearray))
        ):
            raise ValueError("pre_reset_source_robot_mutation_events_invalid")

        for event in pre_reset_mutation_events:
            if not isinstance(event, Mapping) or not isinstance(event.get("path"), str):
                raise ValueError("pre_reset_source_robot_mutation_events_invalid")
            if event.get("phase") not in {None, "pre_reset"}:
                audit_failures.append("pre_reset_source_robot_mutation_notice")
                continue
            path = event["path"]
            if (
                _path_partition(path) in {"source", "robot"}
                and not _is_allowed_pre_reset_setup_event(event)
            ):
                audit_failures.append("pre_reset_source_robot_mutation_notice")
        if (
            not isinstance(mutation_events, Sequence)
            or isinstance(mutation_events, (str, bytes, bytearray))
        ):
            raise ValueError("source_robot_mutation_events_invalid")
        for event in mutation_events:
            if not isinstance(event, Mapping) or not isinstance(event.get("path"), str):
                raise ValueError("source_robot_mutation_events_invalid")
            path = event["path"]
            if _path_partition(path) in {"source", "robot"}:
                audit_failures.append("source_robot_mutation_notice")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {"audit_valid": not audit_failures, "audit_failures": audit_failures}


def _without_report_metadata(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only the exact, instrumentation-only contact-report metadata."""

    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, Mapping):
            return copy.deepcopy(value)
        result = {
            key: visit(item)
            for key, item in value.items()
            if key != "sha256"
        }
        schemas = result.get("applied_schemas")
        if isinstance(schemas, list):
            normalized_schemas = []
            for record in schemas:
                if not isinstance(record, Mapping):
                    normalized_schemas.append(record)
                    continue
                path = record.get("path")
                values = record.get("schemas")
                if (
                    path in REPORT_BODY_PATHS
                    and isinstance(values, list)
                    and all(isinstance(schema, str) for schema in values)
                    and "PhysxContactReportAPI" in values
                ):
                    record = dict(record)
                    record["schemas"] = [
                        schema for schema in values if schema != "PhysxContactReportAPI"
                    ]
                normalized_schemas.append(record)
            result["applied_schemas"] = normalized_schemas
        attributes = result.get("attributes")
        if isinstance(attributes, list):
            result["attributes"] = [
                record
                for record in attributes
                if not (
                    isinstance(record, Mapping)
                    and record.get("path") in REPORT_BODY_PATHS
                    and record.get("name") == "physxContactReport:threshold"
                    and record.get("value") == 0.0
                )
            ]
        relationships = result.get("relationships")
        if isinstance(relationships, list):
            result["relationships"] = [
                record
                for record in relationships
                if not (
                    isinstance(record, Mapping)
                    and record.get("path") in REPORT_BODY_PATHS
                    and record.get("name") == "physxContactReport:reportPairs"
                    and record.get("targets") == []
                )
            ]
        return result

    return visit(snapshot)


def evaluate_writer_target_force_gripper_audit(audit: Mapping[str, Any]) -> dict[str, Any]:
    audit_failures: list[str] = []
    try:
        if not isinstance(audit, Mapping):
            raise ValueError("writer_audit_mapping_required")
        coverage = audit.get("coverage")
        counts = audit.get("counts")
        if (
            not isinstance(coverage, Mapping)
            or set(coverage) != set(REQUIRED_WRITER_AUDIT_SURFACES)
            or any(type(coverage[name]) is not bool for name in REQUIRED_WRITER_AUDIT_SURFACES)
        ):
            audit_failures.append("writer_audit_coverage_incomplete")
        surfaces = audit.get("surfaces")
        if (
            not isinstance(surfaces, Mapping)
            or set(surfaces) != set(REQUIRED_WRITER_AUDIT_SURFACES)
        ):
            audit_failures.append("writer_audit_surface_status_invalid")
        else:
            for name in REQUIRED_WRITER_AUDIT_SURFACES:
                surface = surfaces[name]
                if not isinstance(surface, Mapping):
                    audit_failures.append("writer_audit_surface_status_invalid")
                    continue
                reachable = surface.get("reachable")
                available = surface.get("available")
                audited = surface.get("audited")
                status = surface.get("status")
                if (
                    type(reachable) is not bool
                    or type(available) is not bool
                    or type(audited) is not bool
                    or not isinstance(status, str)
                    or (audited and not available)
                ):
                    audit_failures.append("writer_audit_surface_status_invalid")
                    continue
                if coverage.get(name) is not audited:
                    audit_failures.append("writer_audit_surface_status_invalid")
                    if coverage.get(name) is False and audited is True:
                        audit_failures.append("writer_audit_coverage_incomplete")
                    continue
                if reachable and (not available or not audited):
                    audit_failures.append("writer_audit_reachable_surface_unaudited")
                elif available and not audited and reachable:
                    audit_failures.append("writer_audit_available_surface_unaudited")
                elif not available and status != "not_applicable":
                    audit_failures.append("writer_audit_surface_status_invalid")
                elif audited and status != "audited":
                    audit_failures.append("writer_audit_surface_status_invalid")
        closure = audit.get("static_production_closure")
        if (
            not isinstance(closure, Mapping)
            or closure.get("audit_valid") is not True
            or not isinstance(closure.get("forbidden_calls"), list)
            or closure.get("forbidden_calls")
            or not isinstance(closure.get("required_runtime_surfaces"), list)
            or not isinstance(closure.get("not_applicable_runtime_surfaces"), list)
            or any(
                not isinstance(name, str) or name not in REQUIRED_WRITER_AUDIT_SURFACES
                for name in closure.get("required_runtime_surfaces", [])
            )
            or any(
                not isinstance(name, str) or name not in REQUIRED_WRITER_AUDIT_SURFACES
                for name in closure.get("not_applicable_runtime_surfaces", [])
            )
            or len(set(closure.get("required_runtime_surfaces", [])))
            != len(closure.get("required_runtime_surfaces", []))
            or len(set(closure.get("not_applicable_runtime_surfaces", [])))
            != len(closure.get("not_applicable_runtime_surfaces", []))
            or set(closure.get("required_runtime_surfaces", []))
            & set(closure.get("not_applicable_runtime_surfaces", []))
        ):
            audit_failures.append("static_production_closure_audit_invalid")
        elif isinstance(surfaces, Mapping):
            for name in closure["required_runtime_surfaces"]:
                surface = surfaces.get(name)
                if not isinstance(surface, Mapping) or surface.get("reachable") is not True:
                    audit_failures.append("writer_audit_reachable_surface_unaudited")
            for name, surface in surfaces.items():
                if (
                    isinstance(surface, Mapping)
                    and surface.get("available") is False
                    and (
                        surface.get("status") != "not_applicable"
                        or surface.get("reachable") is not False
                        or surface.get("audited") is not False
                        or name not in closure["not_applicable_runtime_surfaces"]
                    )
                ):
                    audit_failures.append("writer_audit_surface_status_invalid")
        if (
            not isinstance(counts, Mapping)
            or set(counts) != set(WRITER_AUDIT_COUNT_FIELDS)
            or any(type(counts[name]) is not int or counts[name] < 0 for name in counts)
        ):
            audit_failures.append("writer_audit_counts_invalid")
        elif any(counts[name] != 0 for name in WRITER_AUDIT_COUNT_FIELDS):
            audit_failures.append("post_reset_source_writer_detected")
        if audit.get("reset_root_write_count") != 1:
            audit_failures.append("reset_root_write_contract_invalid")
        if audit.get("zero_write_epoch_opened") is not True:
            audit_failures.append("zero_write_epoch_missing")
        if audit.get("mutation_notice_active") is not True:
            audit_failures.append("mutation_notice_missing")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {"audit_valid": not audit_failures, "audit_failures": audit_failures}


def validate_report_only_layer_catalog(catalog: Mapping[str, Any]) -> dict[str, Any]:
    audit_failures: list[str] = []
    try:
        if not isinstance(catalog, Mapping):
            raise ValueError("report_layer_catalog_mapping_required")
        records = catalog.get("records")
        if (
            not isinstance(records, Sequence)
            or isinstance(records, (str, bytes, bytearray))
            or not _is_sha256(catalog.get("sha256"))
        ):
            raise ValueError("report_layer_catalog_records_invalid")
        payload = {
            "records": sorted(
                copy.deepcopy(list(records)),
                key=lambda record: record.get("path", "")
                if isinstance(record, Mapping)
                else "",
            )
        }
        if catalog.get("sha256") != _canonical_json_sha256(payload):
            audit_failures.append("report_layer_catalog_sha256_invalid")
        expected = set(REPORT_BODY_PATHS)
        observed = set()
        all_paths = set()
        allowed_ancestors = {"/", "/World", SOURCE_ROOT_PATH, ROBOT_ROOT_PATH}
        for record in records:
            if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
                raise ValueError("report_layer_catalog_record_invalid")
            path = record["path"]
            if path in all_paths:
                audit_failures.append("report_layer_duplicate_or_ancestor_invalid")
                continue
            all_paths.add(path)
            properties = record.get("properties")
            schemas = record.get("api_schemas")
            metadata = record.get("metadata")
            if not isinstance(properties, Sequence) or isinstance(
                properties, (str, bytes, bytearray)
            ):
                raise ValueError("report_layer_catalog_record_invalid")
            if path not in expected:
                if path not in allowed_ancestors or properties or schemas or metadata:
                    audit_failures.append("report_layer_unexpected_prim")
                continue
            observed.add(path)
            if schemas != ["PhysxContactReportAPI"] or metadata != {}:
                audit_failures.append("report_layer_schema_or_metadata_invalid")
            by_name = {
                item.get("name"): item
                for item in properties
                if isinstance(item, Mapping) and isinstance(item.get("name"), str)
            }
            if len(by_name) != len(properties) or set(by_name) != {
                "physxContactReport:threshold",
                "physxContactReport:reportPairs",
            }:
                audit_failures.append("report_layer_unexpected_property")
                continue
            if by_name["physxContactReport:threshold"].get("value") != 0.0:
                audit_failures.append("report_layer_threshold_invalid")
            pairs = by_name["physxContactReport:reportPairs"]
            if pairs.get("targets") != [] or pairs.get("list_op") != "explicit":
                audit_failures.append("report_layer_report_pairs_invalid")
        if observed != expected:
            audit_failures.append("report_layer_report_body_set_invalid")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {"audit_valid": not audit_failures, "audit_failures": audit_failures}


def _bound_corners(bound: Mapping[str, Any]) -> np.ndarray:
    low = _finite_vector(bound.get("local_min_m"), field="bound_min")
    high = _finite_vector(bound.get("local_max_m"), field="bound_max")
    if np.any(high <= low):
        raise ValueError("native_unbound_bound_degenerate")
    matrix = _matrix4(bound.get("world_from_local"), field="bound_transform")
    local = np.asarray(
        [[x, y, z, 1.0] for x in low for y in low[1:2] for z in low[2:3]],
        dtype=np.float64,
    )
    local = np.asarray(
        [
            [x, y, z, 1.0]
            for x in (low[0], high[0])
            for y in (low[1], high[1])
            for z in (low[2], high[2])
        ],
        dtype=np.float64,
    )
    world = local @ matrix
    if not np.allclose(world[:, 3], 1.0, rtol=0.0, atol=1.0e-10):
        raise ValueError("native_unbound_bound_transform_invalid")
    return world[:, :3]


def _world_normal_from_local(local: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    normal = local @ np.linalg.inv(matrix[:3, :3]).T
    magnitude = float(np.linalg.norm(normal))
    if magnitude <= 1.0e-12 or not math.isfinite(magnitude):
        raise ValueError("native_unbound_normal_transform_invalid")
    return normal / magnitude


def _source_local_up(geometry: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    gravity = _finite_vector(geometry.get("gravity_world_m_s2"), field="gravity")
    magnitude = float(np.linalg.norm(gravity))
    if magnitude <= 1.0e-12:
        raise ValueError("native_unbound_gravity_invalid")
    reset = _matrix4(
        geometry.get("source_reset_world_from_local"), field="source_reset_transform"
    )
    anti_gravity = -gravity / magnitude
    candidates: list[tuple[float, np.ndarray]] = []
    for axis in range(3):
        for sign in (-1.0, 1.0):
            local = np.zeros(3, dtype=np.float64)
            local[axis] = sign
            world = _world_normal_from_local(local, reset)
            candidates.append((float(world @ anti_gravity), local))
    cosine, local_up = max(candidates, key=lambda item: item[0])
    if cosine < 0.95:
        raise ValueError("native_unbound_source_up_alignment_invalid")
    source = geometry.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("native_unbound_source_bound_invalid")
    live = _matrix4(source.get("world_from_local"), field="source_live_transform")
    return local_up, _world_normal_from_local(local_up, live)


def _raw_local_point(point_world: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    point = np.append(point_world, 1.0) @ np.linalg.inv(matrix)
    if not np.isfinite(point).all() or not math.isclose(
        float(point[3]), 1.0, rel_tol=0.0, abs_tol=1.0e-10
    ):
        raise ValueError("native_unbound_point_transform_invalid")
    return point[:3]


def _classify_pair(pair: tuple[str, str], identities: Mapping[str, Any]) -> str:
    source = set(identities["source_colliders"])
    support = set(identities["support_colliders"])
    left = set(identities["left_colliders"])
    right = set(identities["right_colliders"])
    hand = set(identities["hand_colliders"])
    values = set(pair)
    if values & source:
        other = next(iter(values - source), None)
        if other in left:
            return "LEFT_SOURCE"
        if other in right:
            return "RIGHT_SOURCE"
        if other in support:
            return "SOURCE_SUPPORT"
        return "SOURCE_OTHER"
    robot = left | right | hand
    if values & robot and values - robot:
        return "ROBOT_ENVIRONMENT"
    return "OTHER"


def _contact_load_bearing_policy(protocol: Mapping[str, Any] | None) -> bool:
    return bool(
        protocol is not None
        and _require_protocol_spec(protocol).get("contact_load_bearing_authority") is True
    )


def _point_is_load_bearing(point: Mapping[str, Any]) -> bool:
    if not isinstance(point, Mapping):
        raise ValueError("contact_load_bearing_point_invalid")
    separation = _finite_scalar(point.get("separation"), field="contact_separation")
    impulse = _finite_vector(point.get("impulse"), field="contact_impulse")
    return bool(separation <= 0.0 or float(np.linalg.norm(impulse)) > 1.0e-12)


def _contact_physical_evidence(
    sample: Mapping[str, Any], *, protocol: Mapping[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(sample, Mapping):
        raise ValueError("contact_physical_evidence_sample_invalid")
    classifications = sample.get("classifications")
    if (
        not isinstance(classifications, list)
        or any(not isinstance(value, str) for value in classifications)
    ):
        raise ValueError("contact_physical_evidence_classifications_invalid")
    if not _contact_load_bearing_policy(protocol):
        return {
            "physical_classifications": copy.deepcopy(classifications),
            "noncontact_clearance_m": {},
        }
    pairs = sample.get("pairs")
    if not isinstance(pairs, list):
        raise ValueError("contact_physical_evidence_pairs_invalid")
    physical_classifications: set[str] = set()
    clearances: dict[str, float] = {}
    for pair in pairs:
        if not isinstance(pair, Mapping):
            raise ValueError("contact_physical_evidence_pair_invalid")
        classification = pair.get("classification")
        current = pair.get("current")
        transient = pair.get("transient")
        points = pair.get("points")
        if (
            not isinstance(classification, str)
            or type(current) is not bool
            or type(transient) is not bool
            or not isinstance(points, list)
        ):
            raise ValueError("contact_physical_evidence_pair_invalid")
        if not current and not transient:
            continue
        if not points:
            if classification in {"SOURCE_OTHER", "ROBOT_ENVIRONMENT"}:
                raise ValueError("contact_noncontact_clearance_missing")
            continue
        if any(not isinstance(point, Mapping) for point in points):
            raise ValueError("contact_load_bearing_point_invalid")
        if any(_point_is_load_bearing(point) for point in points):
            physical_classifications.add(classification)
            continue
        if classification in {"SOURCE_OTHER", "ROBOT_ENVIRONMENT"}:
            separation = min(
                _finite_scalar(point.get("separation"), field="contact_separation")
                for point in points
                if isinstance(point, Mapping)
            )
            if separation <= 0.0:
                raise ValueError("contact_noncontact_clearance_invalid")
            prior = clearances.get(classification)
            clearances[classification] = (
                separation if prior is None else min(prior, separation)
            )
    return {
        "physical_classifications": sorted(physical_classifications),
        "noncontact_clearance_m": clearances,
    }


def _apply_contact_physical_evidence(
    sample: dict[str, Any], *, protocol: Mapping[str, Any] | None
) -> None:
    evidence = _contact_physical_evidence(sample, protocol=protocol)
    physical_classifications = set(evidence["physical_classifications"])
    sample["forbidden_source_contact"] = "SOURCE_OTHER" in physical_classifications
    sample["robot_environment_contact"] = "ROBOT_ENVIRONMENT" in physical_classifications
    if _contact_load_bearing_policy(protocol):
        sample.update(evidence)


class ContactLifecycleAccumulator:
    """Validate complete raw contact reports and preserve pair state per physics step."""

    _events = frozenset({"FOUND", "PERSIST", "LOST"})

    def __init__(
        self,
        identities: Mapping[str, Any],
        *,
        protocol: Mapping[str, Any] | None = None,
    ) -> None:
        self.protocol = _require_protocol_spec(
            PROTOCOL_SPECS[(1, V1_PROTOCOL_ID)] if protocol is None else protocol
        )
        self.identities = self._validate_identities(identities)
        self._composite_support = self.protocol.get("composite_support") is True
        self._allow_active_support_pair_omission = (
            self.protocol.get("allow_active_support_pair_omission") is True
        )
        if self._composite_support and self.identities["support_colliders"] != self.protocol[
            "support_collider_paths"
        ]:
            raise ContactAuditError("contact_support_identity_mismatch")
        self.active: set[tuple[str, str]] = set()
        self.previous_index: int | None = None
        self._support_seen = False
        self.recent_samples: deque[dict[str, Any]] = deque(maxlen=32)

    @staticmethod
    def _validate_identities(identities: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(identities, Mapping) or type(identities.get("stage_id")) is not int:
            raise ContactAuditError("contact_identity_stage_invalid")
        required = (
            "source_colliders",
            "support_colliders",
            "left_colliders",
            "right_colliders",
            "hand_colliders",
            "other_colliders",
        )
        result = {"stage_id": identities["stage_id"]}
        known: set[str] = set()
        for name in required:
            values = identities.get(name)
            if (
                not isinstance(values, Sequence)
                or isinstance(values, (str, bytes, bytearray))
                or (not values and name not in {"hand_colliders", "other_colliders"})
                or any(not isinstance(path, str) or not path for path in values)
                or len(set(values)) != len(values)
            ):
                raise ContactAuditError("contact_identity_colliders_invalid")
            result[name] = list(values)
            known.update(values)
        owners = identities.get("collider_owners")
        if (
            not isinstance(owners, Mapping)
            or set(owners) != known
            or any(not isinstance(value, str) or not value for value in owners.values())
        ):
            raise ContactAuditError("contact_identity_owners_invalid")
        result["collider_owners"] = dict(owners)
        return result

    @staticmethod
    def _range(
        header: Mapping[str, Any],
        *,
        offset_name: str,
        count_name: str,
        used: list[bool],
    ) -> range:
        offset = header.get(offset_name)
        count = header.get(count_name)
        if (
            isinstance(offset, bool)
            or not isinstance(offset, (int, np.integer))
            or isinstance(count, bool)
            or not isinstance(count, (int, np.integer))
            or int(offset) < 0
            or int(count) < 0
            or int(offset) + int(count) > len(used)
        ):
            raise ContactAuditError("contact_range_invalid")
        result = range(int(offset), int(offset) + int(count))
        if any(used[index] for index in result):
            raise ContactAuditError("contact_range_invalid")
        for index in result:
            used[index] = True
        return result

    @staticmethod
    def _point(value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ContactAuditError("contact_point_invalid")
        try:
            return {
                "position": _finite_vector(value.get("position"), field="contact_position").tolist(),
                "normal": _finite_vector(
                    value.get("normal"), field="contact_normal", unit=True
                ).tolist(),
                "impulse": _finite_vector(value.get("impulse"), field="contact_impulse").tolist(),
                "separation": _finite_scalar(value.get("separation"), field="contact_separation"),
                "face_index0": int(value.get("face_index0")),
                "face_index1": int(value.get("face_index1")),
                "material0": str(value.get("material0")),
                "material1": str(value.get("material1")),
            }
        except (TypeError, ValueError) as exc:
            raise ContactAuditError("contact_point_invalid") from exc

    @staticmethod
    def _anchor(value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ContactAuditError("contact_anchor_invalid")
        try:
            return {
                "position": _finite_vector(
                    value.get("position"), field="contact_anchor_position"
                ).tolist(),
                "impulse": _finite_vector(
                    value.get("impulse"), field="contact_anchor_impulse"
                ).tolist(),
            }
        except ValueError as exc:
            raise ContactAuditError("contact_anchor_invalid") from exc

    def _composite_support_summary(
        self,
        pairs: Sequence[Mapping[str, Any]],
        support_pairs: Sequence[tuple[str, str]],
        unreported_active_pairs: Sequence[tuple[str, str]] = (),
    ) -> dict[str, Any]:
        by_pair = {
            tuple(item["pair"]): item
            for item in pairs
            if tuple(item["pair"]) in set(support_pairs)
        }
        members = []
        for pair in support_pairs:
            item = by_pair.get(pair)
            if item is None:
                continue
            members.append(
                {
                    "pair": copy.deepcopy(item["pair"]),
                    "events": copy.deepcopy(item["events"]),
                    "current": item["current"],
                    "header_count": len(item["headers"]),
                    "contact_count": len(item["points"]),
                    "friction_anchor_count": len(item["anchors"]),
                    "lost_header_count": item["lost_header_count"],
                    "observer_activation": item["observer_activation"],
                    "bootstrap": item["bootstrap"],
                    "transient": item["transient"],
                }
            )
        summary = {
            "present": bool(members),
            "events": sorted({event for member in members for event in member["events"]}),
            "current": any(member["current"] for member in members),
            "header_count": sum(member["header_count"] for member in members),
            "contact_count": sum(member["contact_count"] for member in members),
            "friction_anchor_count": sum(
                member["friction_anchor_count"] for member in members
            ),
            "lost_header_count": sum(member["lost_header_count"] for member in members),
            "observer_activation": any(
                member["observer_activation"] for member in members
            ),
            "pairs": members,
        }
        if self._allow_active_support_pair_omission:
            summary["support_observation_gap"] = bool(unreported_active_pairs)
            summary["unreported_active_pairs"] = [
                list(pair) for pair in unreported_active_pairs
            ]
        return summary

    def consume(self, *, physics_index: int, raw: Mapping[str, Any]) -> dict[str, Any]:
        if type(physics_index) is not int or physics_index < 0:
            raise ContactAuditError("contact_physics_index_invalid")
        if self.previous_index is not None and physics_index != self.previous_index + 1:
            raise ContactAuditError("contact_physics_index_discontinuous")
        if not isinstance(raw, Mapping):
            raise ContactAuditError("contact_report_mapping_invalid")
        headers = raw.get("headers")
        raw_points = raw.get("contact_data")
        raw_anchors = raw.get("friction_anchors")
        if any(
            not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray))
            for value in (headers, raw_points, raw_anchors)
        ):
            raise ContactAuditError("contact_report_vectors_invalid")
        points = [self._point(value) for value in raw_points]
        anchors = [self._anchor(value) for value in raw_anchors]
        point_used = [False] * len(points)
        anchor_used = [False] * len(anchors)
        known = set(self.identities["collider_owners"])
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for raw_header in headers:
            if not isinstance(raw_header, Mapping):
                raise ContactAuditError("contact_header_invalid")
            header = dict(raw_header)
            stage_id = header.get("stage_id")
            if (
                header.get("type") not in self._events
                or isinstance(stage_id, bool)
                or not isinstance(stage_id, (int, np.integer))
                or int(stage_id) != self.identities["stage_id"]
            ):
                raise ContactAuditError("contact_header_semantics_invalid")
            collider0, collider1 = header.get("collider0"), header.get("collider1")
            actor0, actor1 = header.get("actor0"), header.get("actor1")
            if (
                not isinstance(collider0, str)
                or not isinstance(collider1, str)
                or collider0 == collider1
                or collider0 not in known
                or collider1 not in known
                or actor0 != self.identities["collider_owners"].get(collider0)
                or actor1 != self.identities["collider_owners"].get(collider1)
            ):
                raise ContactAuditError("unresolved_contact_identity")
            for name in ("proto_index0", "proto_index1"):
                value = header.get(name)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, np.integer))
                    or not 0 <= int(value) <= PROTO_NONE
                ):
                    raise ContactAuditError("contact_prototype_identity_invalid")
            point_range = self._range(
                header,
                offset_name="contact_data_offset",
                count_name="num_contact_data",
                used=point_used,
            )
            anchor_range = self._range(
                header,
                offset_name="friction_anchors_offset",
                count_name="num_friction_anchors_data",
                used=anchor_used,
            )
            pair = tuple(sorted((collider0, collider1)))
            group = groups.setdefault(
                pair,
                {"headers": [], "events": [], "points": [], "anchors": []},
            )
            group["headers"].append(header)
            if not group["events"] or group["events"][-1] != header["type"]:
                group["events"].append(header["type"])
            group["points"].extend(copy.deepcopy(points[index]) for index in point_range)
            group["anchors"].extend(copy.deepcopy(anchors[index]) for index in anchor_range)
        if not all(point_used) or not all(anchor_used):
            raise ContactAuditError("contact_range_invalid")
        support_pairs = tuple(
            tuple(sorted((source, support)))
            for source in self.identities["source_colliders"]
            for support in self.identities["support_colliders"]
        )
        missing = self.active.difference(groups)
        unreported_active_pairs: tuple[tuple[str, str], ...] = ()
        if missing:
            if (
                not self._allow_active_support_pair_omission
                or not missing <= set(support_pairs)
            ):
                raise ContactAuditError("contact_active_pair_missing")
            unreported_active_pairs = tuple(
                pair for pair in support_pairs if pair in missing
            )
        support_pair = support_pairs[0]
        next_active = set(self.active)
        pairs = []
        first_observation = physics_index == 0 and self.previous_index is None
        for pair in sorted(groups):
            group = groups[pair]
            events = tuple(group["events"])
            prior_active = pair in self.active
            bootstrap = bool(
                first_observation
                and not prior_active
                and events in {("PERSIST",), ("LOST",), ("PERSIST", "LOST")}
            )
            observer_activation = bool(
                pair in support_pairs
                and not self._support_seen
                and physics_index > 0
                and physics_index
                <= self.protocol["initial_support_activation_max_absent_reports"]
                and self.protocol["allow_late_initial_support_persist"] is True
                and events == ("PERSIST",)
            )
            if bootstrap:
                current = events == ("PERSIST",)
                transient = events == ("PERSIST", "LOST")
            elif observer_activation:
                current, transient = True, False
            elif not prior_active and events == ("FOUND",):
                current, transient = True, False
            elif prior_active and events == ("PERSIST",):
                current, transient = True, False
            elif prior_active and events == ("LOST",):
                current, transient = False, False
            elif not prior_active and events == ("FOUND", "LOST"):
                current, transient = False, True
            elif prior_active and events == ("PERSIST", "LOST"):
                current, transient = False, True
            else:
                raise ContactAuditError("contact_lifecycle_invalid")
            lost_headers = [header for header in group["headers"] if header["type"] == "LOST"]
            if lost_headers and any(
                header["num_contact_data"] != 0
                or header["num_friction_anchors_data"] != 0
                for header in lost_headers
            ):
                raise ContactAuditError("contact_lost_nonzero_data")
            if current:
                next_active.add(pair)
            else:
                next_active.discard(pair)
            pairs.append(
                {
                    "pair": list(pair),
                    "classification": _classify_pair(pair, self.identities),
                    "events": list(events),
                    "current": current,
                    "transient": transient,
                    "bootstrap": bootstrap,
                    "observer_activation": observer_activation,
                    "headers": group["headers"],
                    "points": group["points"],
                    "anchors": group["anchors"],
                    "lost_header_count": len(lost_headers),
                }
            )
        self.active = next_active
        self.previous_index = physics_index
        if self._composite_support:
            support = self._composite_support_summary(
                pairs,
                support_pairs,
                unreported_active_pairs,
            )
            if support["current"]:
                self._support_seen = True
        else:
            support = next((item for item in pairs if tuple(item["pair"]) == support_pair), None)
            if support is not None:
                self._support_seen = True
        result = {
            "physics_index": physics_index,
            "identity_valid": True,
            "classifications": sorted({item["classification"] for item in pairs}),
            "pairs": pairs,
            "support": (
                support
                if self._composite_support
                else {
                    "present": support is not None,
                    "events": [] if support is None else support["events"],
                    "current": False if support is None else support["current"],
                    "header_count": 0 if support is None else len(support["headers"]),
                    "contact_count": 0 if support is None else len(support["points"]),
                    "friction_anchor_count": 0 if support is None else len(support["anchors"]),
                    "lost_header_count": 0 if support is None else support["lost_header_count"],
                    "observer_activation": (
                        False if support is None else support["observer_activation"]
                    ),
                }
            ),
            **(
                {
                    "support_observation_gap": bool(unreported_active_pairs),
                    "unreported_active_pairs": [
                        list(pair) for pair in unreported_active_pairs
                    ]
                }
                if self._allow_active_support_pair_omission
                else {}
            ),
        }
        self.recent_samples.append(
            {
                "physics_index": physics_index,
                "pairs": [
                    {
                        "pair": copy.deepcopy(pair["pair"]),
                        "classification": pair["classification"],
                        "events": copy.deepcopy(pair["events"]),
                        "current": pair["current"],
                        "transient": pair["transient"],
                        "bootstrap": pair["bootstrap"],
                        "observer_activation": pair["observer_activation"],
                        "header_count": len(pair["headers"]),
                        "contact_count": len(pair["points"]),
                        "friction_anchor_count": len(pair["anchors"]),
                    }
                    for pair in result["pairs"]
                ],
                "support": copy.deepcopy(result["support"]),
                **(
                    {
                        "support_observation_gap": result["support_observation_gap"],
                        "unreported_active_pairs": copy.deepcopy(
                            result["unreported_active_pairs"]
                        )
                    }
                    if self._allow_active_support_pair_omission
                    else {}
                ),
            }
        )
        return result


class SupportObserverAccumulator:
    """Apply the pinned support-observer policy to parsed contact samples."""

    def __init__(self, *, protocol: Mapping[str, Any]) -> None:
        self.protocol = _require_protocol_spec(protocol)
        self._composite_support = self.protocol.get("composite_support") is True
        self._allow_active_support_pair_omission = (
            self.protocol.get("allow_active_support_pair_omission") is True
        )
        self.state = "UNKNOWN"
        self.absent_reports = 0
        self._previous_index: int | None = None
        self._close_action_seen = False
        self._prefix_physical_failures: set[str] = set()
        self._support_membership_closed = False
        self._support_pair_states: dict[tuple[str, str], dict[str, Any]] = {}
        self._support_pair_physical_failures: set[str] = set()
        self._observation_gap_pairs: tuple[tuple[str, str], ...] = ()

    @staticmethod
    def _support(sample: Mapping[str, Any]) -> Mapping[str, Any] | None:
        support = sample.get("support")
        if not isinstance(support, Mapping):
            return None
        present = support.get("present")
        current = support.get("current")
        events = support.get("events")
        counts = (
            support.get("header_count"),
            support.get("contact_count"),
            support.get("friction_anchor_count"),
            support.get("lost_header_count"),
        )
        if (
            type(present) is not bool
            or type(current) is not bool
            or not isinstance(events, list)
            or any(not isinstance(event, str) for event in events)
            or any(type(count) is not int or count < 0 for count in counts)
        ):
            return None
        return support

    @staticmethod
    def _source_awake(source_state: Mapping[str, Any]) -> bool | None:
        if not isinstance(source_state, Mapping):
            return None
        awake = source_state.get("awake")
        return awake if type(awake) is bool else None

    def _prefix_failures(self, sample: Mapping[str, Any]) -> None:
        values = set(
            _contact_physical_evidence(sample, protocol=self.protocol)[
                "physical_classifications"
            ]
        )
        if values & {"LEFT_SOURCE", "RIGHT_SOURCE"}:
            self._prefix_physical_failures.add("initial_observer_source_finger_contact")
        if "SOURCE_OTHER" in values:
            self._prefix_physical_failures.add("initial_observer_forbidden_source_contact")
        if "ROBOT_ENVIRONMENT" in values:
            self._prefix_physical_failures.add("initial_observer_robot_environment_contact")

    def _decision(
        self,
        *,
        state_before: str,
        absent_reports_before: int,
        activation_event: str | None,
        audit_no_go_code: str | None,
    ) -> dict[str, Any]:
        return {
            "state_before": state_before,
            "state": self.state,
            "absent_reports_before": absent_reports_before,
            "absent_reports": self.absent_reports,
            "activation_event": activation_event,
            "audit_no_go_code": audit_no_go_code,
            "prefix_physical_failures": sorted(self._prefix_physical_failures),
        }

    @property
    def prefix_physical_failures(self) -> list[str]:
        return sorted(self._prefix_physical_failures)

    @property
    def support_pair_physical_failures(self) -> list[str]:
        return sorted(self._support_pair_physical_failures)

    def _composite_pair_order(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            tuple(sorted((SOURCE_BODY_PATH, support)))
            for support in self.protocol["support_collider_paths"]
        )

    def _composite_decision(
        self,
        *,
        state_before: str,
        absent_reports_before: int,
        activation_event: str | None,
        audit_no_go_code: str | None,
    ) -> dict[str, Any]:
        states = []
        for pair in self._composite_pair_order():
            pair_state = self._support_pair_states.get(pair)
            if pair_state is not None:
                states.append(copy.deepcopy(pair_state))
        decision = {
            **self._decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=activation_event,
                audit_no_go_code=audit_no_go_code,
            ),
            "support_pairs": states,
            "support_pair_physical_failures": self.support_pair_physical_failures,
        }
        if self._allow_active_support_pair_omission:
            decision["support_observation_gap"] = bool(self._observation_gap_pairs)
            decision["unreported_active_pairs"] = [
                list(pair) for pair in self._observation_gap_pairs
            ]
        return decision

    def _composite_members(
        self, sample: Mapping[str, Any]
    ) -> dict[tuple[str, str], Mapping[str, Any]] | None:
        support = self._support(sample)
        if support is None:
            return None
        members = support.get("pairs")
        if not isinstance(members, list):
            return None
        expected = set(self._composite_pair_order())
        result: dict[tuple[str, str], Mapping[str, Any]] = {}
        required = {
            "pair",
            "events",
            "current",
            "header_count",
            "contact_count",
            "friction_anchor_count",
            "lost_header_count",
            "observer_activation",
            "bootstrap",
            "transient",
        }
        for member in members:
            if not isinstance(member, Mapping) or not required <= set(member):
                return None
            paths = member.get("pair")
            events = member.get("events")
            counts = (
                member.get("header_count"),
                member.get("contact_count"),
                member.get("friction_anchor_count"),
                member.get("lost_header_count"),
            )
            if (
                not isinstance(paths, list)
                or len(paths) != 2
                or any(not isinstance(path, str) or not path for path in paths)
                or tuple(paths) != tuple(sorted(paths))
                or tuple(paths) not in expected
                or tuple(paths) in result
                or not isinstance(events, list)
                or any(event not in {"FOUND", "PERSIST", "LOST"} for event in events)
                or type(member.get("current")) is not bool
                or any(type(count) is not int or count < 0 for count in counts)
                or any(
                    type(member.get(field)) is not bool
                    for field in ("observer_activation", "bootstrap", "transient")
                )
            ):
                return None
            result[tuple(paths)] = member
        if (
            support.get("present") is not bool(members)
            or support.get("current")
            is not any(member["current"] for member in members)
            or support.get("header_count")
            != sum(member["header_count"] for member in members)
            or support.get("contact_count")
            != sum(member["contact_count"] for member in members)
            or support.get("friction_anchor_count")
            != sum(member["friction_anchor_count"] for member in members)
            or support.get("lost_header_count")
            != sum(member["lost_header_count"] for member in members)
        ):
            return None
        return result

    def _composite_unreported_pairs(
        self, sample: Mapping[str, Any]
    ) -> tuple[tuple[str, str], ...] | None:
        if not self._allow_active_support_pair_omission:
            return ()
        support = self._support(sample)
        if support is None:
            return None
        raw_pairs = sample.get("unreported_active_pairs")
        support_pairs = support.get("unreported_active_pairs")
        gap = sample.get("support_observation_gap")
        support_gap = support.get("support_observation_gap")
        if (
            raw_pairs != support_pairs
            or type(gap) is not bool
            or support_gap is not gap
            or not isinstance(raw_pairs, list)
        ):
            return None
        expected = self._composite_pair_order()
        result = []
        for index, paths in enumerate(raw_pairs):
            if (
                not isinstance(paths, list)
                or len(paths) != 2
                or any(not isinstance(path, str) or not path for path in paths)
                or tuple(paths) != tuple(sorted(paths))
                or tuple(paths) not in expected
                or tuple(paths) in result
            ):
                return None
            result.append(tuple(paths))
        if result != [pair for pair in expected if pair in result]:
            return None
        if gap is not bool(result):
            return None
        for pair in result:
            state = self._support_pair_states.get(pair)
            if state is None or state["current"] is not True:
                return None
        return tuple(result)

    def _mark_observation_gaps(
        self, pairs: Sequence[tuple[str, str]]
    ) -> None:
        for pair in pairs:
            state = self._support_pair_states[pair]
            state["current_contact_count"] = 0
            state["current_friction_anchor_count"] = 0
            if self._allow_active_support_pair_omission:
                state["observed_current"] = False

    def _composite_exact_absent(self, sample: Mapping[str, Any]) -> bool:
        support = self._support(sample)
        return bool(
            isinstance(support, Mapping)
            and support.get("present") is False
            and support.get("current") is False
            and support.get("events") == []
            and support.get("header_count") == 0
            and support.get("contact_count") == 0
            and support.get("friction_anchor_count") == 0
            and support.get("lost_header_count") == 0
            and support.get("pairs") == []
        )

    def _update_composite_pairs(
        self,
        members: Mapping[tuple[str, str], Mapping[str, Any]],
        *,
        awake: bool,
    ) -> str | None:
        for pair, member in members.items():
            events = member["events"]
            current = member["current"]
            pair_state = self._support_pair_states.setdefault(
                pair,
                {
                    "pair": list(pair),
                    "ever_current": False,
                    "current": False,
                    "terminal_lost": False,
                    "last_events": [],
                    "current_contact_count": 0,
                    "current_friction_anchor_count": 0,
                    **(
                        {"observed_current": False}
                        if self._allow_active_support_pair_omission
                        else {}
                    ),
                },
            )
            pair_state["last_events"] = copy.deepcopy(events)
            if current:
                if (
                    self.protocol["require_current_support_contact_points"] is True
                    and member["contact_count"] == 0
                ):
                    return "support_current_contact_missing"
                if not pair_state["ever_current"] and self._support_membership_closed:
                    self._support_pair_physical_failures.add("late_support_pair_after_close")
                pair_state["ever_current"] = True
                pair_state["current"] = True
                pair_state["terminal_lost"] = False
                pair_state["current_contact_count"] = member["contact_count"]
                pair_state["current_friction_anchor_count"] = member[
                    "friction_anchor_count"
                ]
                if self._allow_active_support_pair_omission:
                    pair_state["observed_current"] = True
            elif events and events[-1] == "LOST":
                pair_state["current"] = False
                pair_state["current_contact_count"] = 0
                pair_state["current_friction_anchor_count"] = 0
                if self._allow_active_support_pair_omission:
                    pair_state["observed_current"] = False
                if pair_state["ever_current"]:
                    if member["lost_header_count"] != 1 or not awake:
                        return "support_lost_contract_invalid"
                    pair_state["terminal_lost"] = True
        return None

    def _consume_composite(
        self,
        sample: Mapping[str, Any],
        *,
        source_state: Mapping[str, Any],
        transition_index: int,
    ) -> dict[str, Any]:
        self._observation_gap_pairs = ()
        state_before = self.state
        absent_reports_before = self.absent_reports
        if (
            type(transition_index) is not int
            or transition_index < 0
            or (
                self._previous_index is not None
                and transition_index != self._previous_index + 1
            )
        ):
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="support_observer_transition_index_invalid",
            )
        self._previous_index = transition_index
        if not isinstance(sample, Mapping):
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="support_contact_authority_missing",
            )
        classifications = sample.get("classifications")
        if (
            not isinstance(classifications, Sequence)
            or isinstance(classifications, (str, bytes, bytearray))
            or any(not isinstance(value, str) for value in classifications)
        ):
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="contact_classification_authority_missing",
            )
        awake = self._source_awake(source_state)
        members = self._composite_members(sample)
        if members is None:
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="support_contact_authority_missing",
            )
        gap_pairs = self._composite_unreported_pairs(sample)
        if gap_pairs is None:
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="support_observation_gap_authority_missing",
            )
        self._observation_gap_pairs = gap_pairs
        if awake is None:
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="support_awake_authority_missing",
            )
        if state_before in {"UNKNOWN", "UNOBSERVED"}:
            self._prefix_failures(sample)
            if self._composite_exact_absent(sample):
                maximum = self.protocol["initial_support_activation_max_absent_reports"]
                if self.absent_reports >= maximum:
                    return self._composite_decision(
                        state_before=state_before,
                        absent_reports_before=absent_reports_before,
                        activation_event=None,
                        audit_no_go_code="support_initial_activation_timeout",
                    )
                self.state = "UNOBSERVED"
                self.absent_reports += 1
                return self._composite_decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code=None,
                )
            update_error = self._update_composite_pairs(members, awake=awake)
            if update_error is not None:
                return self._composite_decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code=update_error,
                )
            current_members = [member for member in members.values() if member["current"]]
            if not current_members:
                return self._composite_decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code="support_initial_state_unknown",
                )
            if any(
                transition_index > 0
                and member["events"] == ["PERSIST"]
                and member["observer_activation"] is not True
                for member in current_members
            ):
                return self._composite_decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code="support_initial_state_unknown",
                )
            self.state = "CURRENT"
            activation_event = (
                "FOUND"
                if any(member["events"] == ["FOUND"] for member in current_members)
                else "PERSIST"
            )
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=activation_event,
                audit_no_go_code=None,
            )
        update_error = self._update_composite_pairs(members, awake=awake)
        if update_error is not None:
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code=update_error,
            )
        self._mark_observation_gaps(gap_pairs)
        if state_before == "CURRENT":
            states = list(self._support_pair_states.values())
            if states and all(
                state["ever_current"] and state["terminal_lost"] and not state["current"]
                for state in states
            ):
                self.state = "LOST"
            elif not any(state["current"] for state in states):
                return self._composite_decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code="support_lost_contract_invalid",
                )
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code=None,
            )
        if state_before == "LOST":
            if members:
                self._support_pair_physical_failures.add("support_recontact")
            return self._composite_decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code=None,
            )
        return self._composite_decision(
            state_before=state_before,
            absent_reports_before=absent_reports_before,
            activation_event=None,
            audit_no_go_code="support_state_invalid",
        )

    def consume(
        self,
        sample: Mapping[str, Any],
        *,
        source_state: Mapping[str, Any],
        transition_index: int,
    ) -> dict[str, Any]:
        if self._composite_support:
            return self._consume_composite(
                sample,
                source_state=source_state,
                transition_index=transition_index,
            )
        state_before = self.state
        absent_reports_before = self.absent_reports
        if (
            type(transition_index) is not int
            or transition_index < 0
            or (
                self._previous_index is not None
                and transition_index != self._previous_index + 1
            )
        ):
            return self._decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="support_observer_transition_index_invalid",
            )
        self._previous_index = transition_index
        if not isinstance(sample, Mapping):
            return self._decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="support_contact_authority_missing",
            )
        classifications = sample.get("classifications")
        if (
            not isinstance(classifications, Sequence)
            or isinstance(classifications, (str, bytes, bytearray))
            or any(not isinstance(value, str) for value in classifications)
        ):
            return self._decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="contact_classification_authority_missing",
            )
        support = self._support(sample)
        awake = self._source_awake(source_state)
        if support is None:
            return self._decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="support_contact_authority_missing",
            )
        if awake is None:
            return self._decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code="support_awake_authority_missing",
            )
        if state_before in {"UNKNOWN", "UNOBSERVED"}:
            if self.protocol["initial_support_activation_max_absent_reports"] > 0:
                self._prefix_failures(sample)
            exact_absent = (
                support["present"] is False
                and support["current"] is False
                and support["events"] == []
                and support["header_count"] == 0
                and support["contact_count"] == 0
                and support["friction_anchor_count"] == 0
                and support["lost_header_count"] == 0
            )
            if exact_absent:
                maximum = self.protocol["initial_support_activation_max_absent_reports"]
                if maximum == 0:
                    return self._decision(
                        state_before=state_before,
                        absent_reports_before=absent_reports_before,
                        activation_event=None,
                        audit_no_go_code="support_initial_state_unknown",
                    )
                if self.absent_reports >= maximum:
                    return self._decision(
                        state_before=state_before,
                        absent_reports_before=absent_reports_before,
                        activation_event=None,
                        audit_no_go_code="support_initial_activation_timeout",
                    )
                self.state = "UNOBSERVED"
                self.absent_reports += 1
                return self._decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code=None,
                )
            events = support["events"]
            if (
                support["present"] is not True
                or support["current"] is not True
                or events not in (["FOUND"], ["PERSIST"])
            ):
                return self._decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code="support_initial_state_unknown",
                )
            if (
                self.protocol["require_current_support_contact_points"] is True
                and support["contact_count"] == 0
            ):
                return self._decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code="support_current_contact_missing",
                )
            if (
                transition_index > 0
                and events == ["PERSIST"]
                and support.get("observer_activation") is not True
            ):
                return self._decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code="support_initial_state_unknown",
                )
            self.state = "CURRENT"
            return self._decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=events[0],
                audit_no_go_code=None,
            )
        if state_before == "CURRENT":
            if support["present"] is not True:
                return self._decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code="support_state_became_unknown",
                )
            events = support["events"]
            if events and events[-1] == "LOST":
                if (
                    support["current"] is True
                    or support["lost_header_count"] != 1
                    or support["contact_count"] != 0
                    or support["friction_anchor_count"] != 0
                    or awake is not True
                ):
                    return self._decision(
                        state_before=state_before,
                        absent_reports_before=absent_reports_before,
                        activation_event=None,
                        audit_no_go_code="support_lost_contract_invalid",
                    )
                self.state = "LOST"
                return self._decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code=None,
                )
            if (
                support["current"] is not True
                or events != ["PERSIST"]
                or (
                    self.protocol["require_current_support_contact_points"] is True
                    and support["contact_count"] == 0
                )
            ):
                return self._decision(
                    state_before=state_before,
                    absent_reports_before=absent_reports_before,
                    activation_event=None,
                    audit_no_go_code=(
                        "support_current_contact_missing"
                        if support["current"] is True
                        and events == ["PERSIST"]
                        and support["contact_count"] == 0
                        else "support_current_contract_invalid"
                    ),
                )
            return self._decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code=None,
            )
        if state_before == "LOST":
            return self._decision(
                state_before=state_before,
                absent_reports_before=absent_reports_before,
                activation_event=None,
                audit_no_go_code=None,
            )
        return self._decision(
            state_before=state_before,
            absent_reports_before=absent_reports_before,
            activation_event=None,
            audit_no_go_code="support_state_invalid",
        )

    def observe_action(
        self,
        *,
        pick_event: int | None,
        action: Any,
        apply_count: int,
        action_receipt: Mapping[str, Any] | None,
        classifications: Sequence[str] | None = None,
        sample: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if pick_event != 4:
            return {"audit_no_go_code": None}
        valid_action = bool(
            action is not None
            and apply_count == 1
            and isinstance(action_receipt, Mapping)
            and action_receipt.get("applied") is True
            and action_receipt.get("normal_return") is True
            and action_receipt.get("apply_count") == 1
        )
        if not valid_action:
            return {"audit_no_go_code": "support_activation_close_action_invalid"}
        if self._close_action_seen:
            return {"audit_no_go_code": None}
        self._close_action_seen = True
        if self._composite_support:
            self._support_membership_closed = True
        if (
            self.protocol["initial_support_activation_max_absent_reports"] > 0
            and classifications is not None
        ):
            if sample is not None:
                self._prefix_failures(sample)
            elif not _contact_load_bearing_policy(self.protocol):
                self._prefix_failures({"classifications": list(classifications)})
            elif classifications:
                return {"audit_no_go_code": "contact_load_bearing_authority_missing"}
        if self.state != "CURRENT":
            return {"audit_no_go_code": "support_activation_before_close_missing"}
        return {"audit_no_go_code": None}


INITIAL_SUPPORT_FAILURE_EVIDENCE_SCHEMA = "native_unbound_initial_support_failure_evidence_v1"


def build_initial_support_failure_evidence(
    *,
    protocol: Mapping[str, Any],
    code: str,
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    spec = _require_protocol_spec(protocol)
    if not isinstance(code, str) or not code or not isinstance(observations, Sequence):
        raise ValueError("initial_support_failure_evidence_invalid")
    return {
        "schema": INITIAL_SUPPORT_FAILURE_EVIDENCE_SCHEMA,
        "protocol": {
            "schema_version": spec["schema_version"],
            "protocol_id": spec["protocol_id"],
        },
        "code": code,
        "observations": copy.deepcopy(list(observations)),
    }


def validate_initial_support_failure_evidence(
    evidence: Mapping[str, Any],
    *,
    identities: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    audit_failures: list[str] = []
    failure_code = None
    try:
        spec = _require_protocol_spec(protocol)
        expected_protocol = {
            "schema_version": spec["schema_version"],
            "protocol_id": spec["protocol_id"],
        }
        if (
            not isinstance(evidence, Mapping)
            or evidence.get("schema") != INITIAL_SUPPORT_FAILURE_EVIDENCE_SCHEMA
            or evidence.get("protocol") != expected_protocol
            or not isinstance(evidence.get("code"), str)
            or not evidence["code"]
            or not isinstance(evidence.get("observations"), list)
            or not evidence["observations"]
        ):
            raise ValueError("initial_support_failure_evidence_invalid")
        failure_code = evidence["code"]
        parser = ContactLifecycleAccumulator(identities, protocol=spec)
        observer = SupportObserverAccumulator(protocol=spec)
        previous_world = None
        final_code = None
        for index, observation in enumerate(evidence["observations"]):
            if not isinstance(observation, Mapping):
                raise ValueError("initial_support_failure_observation_invalid")
            if observation.get("transition_index") != index:
                raise ValueError("initial_support_failure_transition_index_invalid")
            world_index = observation.get("world_index")
            if type(world_index) is not int or (
                previous_world is not None and world_index != previous_world + 1
            ):
                raise ValueError("initial_support_failure_world_index_invalid")
            previous_world = world_index
            _state_authority(observation.get("pre"))
            _state_authority(observation.get("post"))
            raw_report = observation.get("raw_report")
            if not isinstance(raw_report, Mapping):
                raise ValueError("initial_support_failure_raw_report_missing")
            sample = parser.consume(physics_index=index, raw=raw_report)
            if _canonical_json_bytes(sample) != _canonical_json_bytes(observation.get("sample")):
                audit_failures.append("initial_support_failure_sample_mismatch")
            decision = observer.consume(
                sample,
                source_state=observation["post"],
                transition_index=index,
            )
            action_context = observation.get("action_context")
            if (
                not isinstance(action_context, Mapping)
                or set(action_context)
                != {"pick_event", "action", "apply_count", "action_receipt", "close_gate"}
                or type(action_context.get("apply_count")) is not int
                or action_context.get("pick_event") is not None
                and type(action_context.get("pick_event")) is not int
                or action_context.get("action_receipt") is not None
                and not isinstance(action_context.get("action_receipt"), Mapping)
            ):
                raise ValueError("initial_support_failure_action_context_invalid")
            gate = observer.observe_action(
                pick_event=action_context["pick_event"],
                action=action_context["action"],
                apply_count=action_context["apply_count"],
                action_receipt=action_context["action_receipt"],
                classifications=sample.get("classifications"),
                sample=sample,
            )
            decision["prefix_physical_failures"] = observer.prefix_physical_failures
            if _canonical_json_bytes(decision) != _canonical_json_bytes(
                observation.get("observer")
            ):
                audit_failures.append("initial_support_failure_observer_mismatch")
            if gate != action_context["close_gate"]:
                audit_failures.append("initial_support_failure_action_gate_mismatch")
            final_code = gate["audit_no_go_code"] or decision["audit_no_go_code"]
        if final_code != failure_code:
            audit_failures.append("initial_support_failure_code_mismatch")
    except (ContactAuditError, TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    return {
        "audit_valid": not audit_failures,
        "audit_failures": sorted(set(audit_failures)),
        "failure_code": failure_code,
    }


def evaluate_sidewall_topology(
    sample: Mapping[str, Any],
    *,
    geometry: Mapping[str, Any],
    identities: Mapping[str, Any],
    protocol: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    audit_failures: list[str] = []
    physical_failures: list[str] = []
    try:
        if not isinstance(sample, Mapping) or not isinstance(geometry, Mapping):
            raise ValueError("topology_mapping_required")
        protocol_spec = None if protocol is None else _require_protocol_spec(protocol)
        defer_unilateral_preclose = bool(
            protocol_spec is not None
            and protocol_spec.get("topology_required_from_close_to_rise") is True
        )
        world_metric_distances = bool(
            protocol_spec is not None
            and protocol_spec.get("topology_world_metric_distances") is True
        )
        if world_metric_distances and "inward_face_distance_tolerance_m" not in geometry:
            raise ValueError("topology_inward_face_distance_tolerance_missing")
        inward_face_distance_tolerance_m = _finite_scalar(
            geometry.get("inward_face_distance_tolerance_m", 0.005),
            field="topology_inward_face_distance_tolerance",
            nonnegative=True,
        )
        if inward_face_distance_tolerance_m <= 0.0:
            raise ValueError("topology_inward_face_distance_tolerance_invalid")
        load_bearing_contacts = _contact_load_bearing_policy(protocol)
        source_bound = geometry.get("source")
        finger_bounds = geometry.get("finger_colliders")
        if not isinstance(source_bound, Mapping) or not isinstance(finger_bounds, Mapping):
            raise ValueError("topology_geometry_missing")
        normalized_height_range = _finite_vector(
            geometry.get("normalized_height_range"),
            field="topology_normalized_height_range",
            length=2,
        )
        if not 0.0 <= normalized_height_range[0] < normalized_height_range[1] <= 1.0:
            raise ValueError("topology_normalized_height_range_invalid")
        maximum_vertical_normal_cosine = _finite_scalar(
            geometry.get("maximum_vertical_normal_cosine"),
            field="topology_maximum_vertical_normal_cosine",
            nonnegative=True,
        )
        if maximum_vertical_normal_cosine > 1.0:
            raise ValueError("topology_maximum_vertical_normal_cosine_invalid")
        minimum_inward_face_cosine = _finite_scalar(
            geometry.get("minimum_inward_face_cosine"),
            field="topology_minimum_inward_face_cosine",
            nonnegative=True,
        )
        if minimum_inward_face_cosine > 1.0:
            raise ValueError("topology_minimum_inward_face_cosine_invalid")
        source_min = _finite_vector(source_bound.get("local_min_m"), field="source_bound_min")
        source_max = _finite_vector(source_bound.get("local_max_m"), field="source_bound_max")
        if np.any(source_max <= source_min):
            raise ValueError("source_bound_degenerate")
        source_matrix = _matrix4(
            source_bound.get("world_from_local"), field="source_live_transform"
        )
        local_up, source_up = _source_local_up(geometry)
        source_corners = _bound_corners(source_bound)
        source_center = np.mean(source_corners, axis=0)
        left_paths = set(identities["left_colliders"])
        right_paths = set(identities["right_colliders"])
        if not left_paths <= set(finger_bounds) or not right_paths <= set(finger_bounds):
            raise ValueError("topology_finger_bounds_missing")
        raw_pairs = sample.get("pairs")
        if (
            not isinstance(raw_pairs, Sequence)
            or isinstance(raw_pairs, (str, bytes, bytearray))
        ):
            raise ValueError("topology_pairs_invalid")
        finger_geometry = {}
        for side, paths in (("left", left_paths), ("right", right_paths)):
            for path in sorted(paths):
                bound = finger_bounds[path]
                if not isinstance(bound, Mapping):
                    raise ValueError("topology_finger_bound_invalid")
                local_min = _finite_vector(bound.get("local_min_m"), field="finger_bound_min")
                local_max = _finite_vector(bound.get("local_max_m"), field="finger_bound_max")
                if np.any(local_max <= local_min):
                    raise ValueError("topology_finger_bound_degenerate")
                matrix = _matrix4(bound.get("world_from_local"), field="finger_live_transform")
                bound_corners = _bound_corners(bound)
                finger_geometry[path] = {
                    "local_min": local_min,
                    "local_max": local_max,
                    "matrix": matrix,
                    "corners": bound_corners,
                    "center": np.mean(bound_corners, axis=0),
                }
        target_pairs = [
            pair
            for pair in raw_pairs
            if isinstance(pair, Mapping)
            and pair.get("classification") in {"LEFT_SOURCE", "RIGHT_SOURCE"}
            and pair.get("current") is True
        ]
        by_side: dict[str, list[Mapping[str, Any]]] = {"left": [], "right": []}
        for pair in target_pairs:
            paths = pair.get("pair")
            if not isinstance(paths, Sequence) or len(paths) != 2:
                raise ValueError("topology_pair_invalid")
            finger = next((path for path in paths if path in left_paths | right_paths), None)
            if finger is None:
                raise ValueError("topology_pair_invalid")
            side = "left" if finger in left_paths else "right"
            points = pair.get("points")
            if not isinstance(points, Sequence) or not points:
                raise ValueError("topology_current_pair_without_points")
            usable_points = (
                [point for point in points if _point_is_load_bearing(point)]
                if load_bearing_contacts
                else list(points)
            )
            if usable_points:
                by_side[side].append({"finger": finger, "points": usable_points})
        for side in ("left", "right"):
            if not by_side[side]:
                physical_failures.append(f"{side}_sidewall_contact_missing")
        face_for_path: dict[str, tuple[int, int, np.ndarray, np.ndarray, np.ndarray]] = {}
        bilateral = bool(by_side["left"] and by_side["right"])
        if bilateral or not defer_unilateral_preclose:
            for occurrences in by_side.values():
                for occurrence in occurrences:
                    finger = occurrence["finger"]
                    if finger in face_for_path:
                        continue
                    values = finger_geometry[finger]
                    inward = source_center - values["center"]
                    inward -= source_up * float(inward @ source_up)
                    magnitude = float(np.linalg.norm(inward))
                    if magnitude <= 1.0e-12:
                        raise ValueError("topology_inward_direction_degenerate")
                    inward /= magnitude
                    candidates = []
                    for axis in range(3):
                        for sign in (-1, 1):
                            local_normal = np.zeros(3, dtype=np.float64)
                            local_normal[axis] = sign
                            world_normal = _world_normal_from_local(local_normal, values["matrix"])
                            candidates.append((float(world_normal @ inward), axis, sign))
                    candidates.sort(reverse=True)
                    if math.isclose(
                        candidates[0][0], candidates[1][0], rel_tol=0.0, abs_tol=1.0e-12
                    ):
                        raise ValueError("topology_inward_face_ambiguous")
                    if candidates[0][0] < minimum_inward_face_cosine:
                        if not defer_unilateral_preclose:
                            raise ValueError("topology_inward_face_ambiguous")
                        physical_failures.append("finger_inward_face_alignment_below_threshold")
                    face_for_path[finger] = (
                        candidates[0][1],
                        candidates[0][2],
                        values["local_min"],
                        values["local_max"],
                        values["matrix"],
                    )
        if bilateral:
            side_centers = {}
            for side, paths in (("left", left_paths), ("right", right_paths)):
                corners = [finger_geometry[path]["corners"] for path in sorted(paths)]
                concatenated = np.concatenate(corners, axis=0)
                side_centers[side] = (
                    concatenated.min(axis=0) + concatenated.max(axis=0)
                ) / 2.0
            closing = side_centers["right"] - side_centers["left"]
            closing -= source_up * float(closing @ source_up)
            closing_norm = float(np.linalg.norm(closing))
            if closing_norm <= 1.0e-12:
                raise ValueError("topology_closing_axis_degenerate")
            closing /= closing_norm
            source_coordinate = float(source_center @ closing)
            edge_margin = _finite_scalar(
                geometry.get("pad_edge_margin_m"), field="pad_edge_margin", nonnegative=True
            )
            for side, occurrences in by_side.items():
                for occurrence in occurrences:
                    finger = occurrence["finger"]
                    face_axis, face_sign, low, high, finger_matrix = face_for_path[finger]
                    tangent = [axis for axis in range(3) if axis != face_axis]
                    face_value = high[face_axis] if face_sign > 0 else low[face_axis]
                    for point_record in occurrence["points"]:
                        point = _finite_vector(point_record.get("position"), field="topology_point")
                        normal = _finite_vector(
                            point_record.get("normal"), field="topology_normal", unit=True
                        )
                        source_local = _raw_local_point(point, source_matrix)
                        finger_local = _raw_local_point(point, finger_matrix)
                        height_axis = int(np.argmax(np.abs(local_up)))
                        extent = source_max[height_axis] - source_min[height_axis]
                        coordinate = source_local[height_axis]
                        normalized_height = (
                            (coordinate - source_min[height_axis]) / extent
                            if local_up[height_axis] > 0.0
                            else (source_max[height_axis] - coordinate) / extent
                        )
                        if not normalized_height_range[0] <= normalized_height <= normalized_height_range[1]:
                            physical_failures.append("outside_middle_sidewall")
                        if abs(float(point @ closing) - source_coordinate) <= 1.0e-12:
                            physical_failures.append("source_side_ambiguous")
                        elif side == "left" and float(point @ closing) >= source_coordinate:
                            physical_failures.append("source_sides_not_opposed")
                        elif side == "right" and float(point @ closing) <= source_coordinate:
                            physical_failures.append("source_sides_not_opposed")
                        if abs(float(normal @ source_up)) > maximum_vertical_normal_cosine:
                            physical_failures.append("rim_or_underside_normal")
                        if world_metric_distances:
                            face_local = finger_local.copy()
                            face_local[face_axis] = face_value
                            face_world = np.append(face_local, 1.0) @ finger_matrix
                            if not math.isclose(
                                float(face_world[3]), 1.0, rel_tol=0.0, abs_tol=1.0e-10
                            ):
                                raise ValueError("topology_finger_transform_invalid")
                            face_normal = np.zeros(3, dtype=np.float64)
                            face_normal[face_axis] = face_sign
                            face_normal = _world_normal_from_local(face_normal, finger_matrix)
                            face_distance = abs(
                                float((point - face_world[:3]) @ face_normal)
                            )
                        else:
                            face_distance = abs(float(finger_local[face_axis] - face_value))
                        if face_distance > inward_face_distance_tolerance_m:
                            physical_failures.append("finger_inward_face_missing")
                        for axis in tangent:
                            if world_metric_distances:
                                low_local = finger_local.copy()
                                high_local = finger_local.copy()
                                low_local[axis] = low[axis]
                                high_local[axis] = high[axis]
                                low_world = np.append(low_local, 1.0) @ finger_matrix
                                high_world = np.append(high_local, 1.0) @ finger_matrix
                                if not math.isclose(
                                    float(low_world[3]), 1.0, rel_tol=0.0, abs_tol=1.0e-10
                                ) or not math.isclose(
                                    float(high_world[3]), 1.0, rel_tol=0.0, abs_tol=1.0e-10
                                ):
                                    raise ValueError("topology_finger_transform_invalid")
                                low_normal = np.zeros(3, dtype=np.float64)
                                low_normal[axis] = 1.0
                                high_normal = np.zeros(3, dtype=np.float64)
                                high_normal[axis] = -1.0
                                low_clearance = float(
                                    (point - low_world[:3])
                                    @ _world_normal_from_local(low_normal, finger_matrix)
                                )
                                high_clearance = float(
                                    (point - high_world[:3])
                                    @ _world_normal_from_local(high_normal, finger_matrix)
                                )
                                outside_pad = min(low_clearance, high_clearance) < edge_margin
                            else:
                                outside_pad = bool(
                                    finger_local[axis] < low[axis] + edge_margin
                                    or finger_local[axis] > high[axis] - edge_margin
                                )
                            if outside_pad:
                                physical_failures.append("finger_pad_edge_contact")
    except (TypeError, ValueError, np.linalg.LinAlgError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    physical_failures = sorted(set(physical_failures))
    return {
        "audit_valid": not audit_failures,
        "qualified": bool(not audit_failures and not physical_failures),
        "audit_failures": audit_failures,
        "failure_reasons": physical_failures,
    }


def evaluate_contact_trace(
    reports: Sequence[Mapping[str, Any]],
    *,
    identities: Mapping[str, Any],
    geometry: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    require_immediate_read: bool = False,
    protocol: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    audit_failures: list[str] = []
    samples: list[dict[str, Any]] = []
    try:
        if (
            not isinstance(reports, Sequence)
            or isinstance(reports, (str, bytes, bytearray))
            or not reports
        ):
            raise ContactAuditError("contact_reports_missing")
        geometry_sequence = None
        if isinstance(geometry, Sequence) and not isinstance(geometry, (str, bytes, bytearray)):
            if len(geometry) != len(reports):
                raise ContactAuditError("contact_geometry_schedule_invalid")
            geometry_sequence = geometry
        elif not isinstance(geometry, Mapping):
            raise ContactAuditError("contact_geometry_invalid")
        accumulator = ContactLifecycleAccumulator(identities, protocol=protocol)
        for index, report in enumerate(reports):
            if require_immediate_read and (
                report.get("physics_index") != index
                or report.get("immediate_read_index") != index
                or report.get("immediate_read_count") != index + 1
            ):
                raise ContactAuditError("contact_immediate_read_contract_invalid")
            sample = accumulator.consume(physics_index=index, raw=report)
            active_geometry = geometry if geometry_sequence is None else geometry_sequence[index]
            topology = evaluate_sidewall_topology(
                sample,
                geometry=active_geometry,
                identities=identities,
                protocol=protocol,
            )
            if not topology["audit_valid"]:
                raise ContactAuditError("contact_topology_authority_invalid")
            sample["topology"] = topology
            _apply_contact_physical_evidence(sample, protocol=protocol)
            sample["contact_read_once"] = True
            samples.append(sample)
    except ContactAuditError as exc:
        audit_failures.append(str(exc))
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {
        "audit_valid": not audit_failures,
        "audit_failures": audit_failures,
        "samples": samples,
    }


def evaluate_support_lifecycle(
    samples: Sequence[Mapping[str, Any]],
    states: Sequence[Mapping[str, Any]],
    *,
    protocol: Mapping[str, Any] | None = None,
    action_contexts: Sequence[Mapping[str, Any] | None] | None = None,
) -> dict[str, Any]:
    audit_failures: list[str] = []
    physical_failures: list[str] = []
    states_out: list[str] = []
    decisions: list[dict[str, Any]] = []
    action_gates: list[dict[str, Any]] = []
    loss_index = None
    try:
        if (
            not isinstance(samples, Sequence)
            or not isinstance(states, Sequence)
            or isinstance(samples, (str, bytes, bytearray))
            or isinstance(states, (str, bytes, bytearray))
            or len(samples) != len(states)
            or not samples
        ):
            raise ValueError("support_lifecycle_schedule_invalid")
        if action_contexts is None:
            action_contexts = [None] * len(samples)
        elif (
            not isinstance(action_contexts, Sequence)
            or isinstance(action_contexts, (str, bytes, bytearray))
            or len(action_contexts) != len(samples)
        ):
            raise ValueError("support_lifecycle_action_schedule_invalid")
        observer = SupportObserverAccumulator(
            protocol=(PROTOCOL_SPECS[(1, V1_PROTOCOL_ID)] if protocol is None else protocol)
        )
        for index, (sample, source_state) in enumerate(zip(samples, states)):
            if not isinstance(sample, Mapping) or not isinstance(source_state, Mapping):
                raise ValueError("support_lifecycle_record_invalid")
            decision = observer.consume(
                sample,
                source_state=source_state,
                transition_index=index,
            )
            decisions.append(decision)
            states_out.append(decision["state"])
            if decision["audit_no_go_code"] is not None:
                audit_failures.append(decision["audit_no_go_code"])
            physical_failures.extend(decision["prefix_physical_failures"])
            if observer.protocol.get("composite_support") is True:
                physical_failures.extend(decision["support_pair_physical_failures"])
            support = sample.get("support")
            if (
                decision["state_before"] == "LOST"
                and isinstance(support, Mapping)
                and support.get("present") is True
            ):
                physical_failures.append("support_recontact")
            if (
                loss_index is None
                and decision["state_before"] == "CURRENT"
                and decision["state"] == "LOST"
            ):
                loss_index = index
            context = action_contexts[index]
            if context is None:
                action_gates.append({"audit_no_go_code": None})
                continue
            if (
                not isinstance(context, Mapping)
                or context.get("pick_event") is not None
                and type(context.get("pick_event")) is not int
                or type(context.get("apply_count")) is not int
                or context.get("action_receipt") is not None
                and not isinstance(context.get("action_receipt"), Mapping)
            ):
                raise ValueError("support_lifecycle_action_context_invalid")
            gate = observer.observe_action(
                pick_event=context.get("pick_event"),
                action=context.get("action"),
                apply_count=context["apply_count"],
                action_receipt=context.get("action_receipt"),
                classifications=sample.get("classifications"),
                sample=sample,
            )
            decision["prefix_physical_failures"] = observer.prefix_physical_failures
            physical_failures.extend(decision["prefix_physical_failures"])
            if observer.protocol.get("composite_support") is True:
                decision["support_pair_physical_failures"] = (
                    observer.support_pair_physical_failures
                )
                physical_failures.extend(decision["support_pair_physical_failures"])
            action_gates.append(gate)
            if gate["audit_no_go_code"] is not None:
                audit_failures.append(gate["audit_no_go_code"])
        if loss_index is None:
            physical_failures.append("support_lost_missing")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    physical_failures = sorted(set(physical_failures))
    return {
        "audit_valid": not audit_failures,
        "support_valid": bool(not audit_failures and not physical_failures),
        "audit_failures": audit_failures,
        "physical_failures": physical_failures,
        "states": states_out,
        "decisions": decisions,
        "action_gates": action_gates,
        "loss_index": loss_index,
    }


def _action_channel_value(action: Any, name: str) -> Any:
    return action.get(name) if isinstance(action, Mapping) else getattr(action, name, None)


def raw_action_channels(action: Any) -> dict[str, Any]:
    if action is None:
        raise ValueError("native_unbound_action_required")
    result = {}
    for name in ACTION_CHANNELS:
        value = _action_channel_value(action, name)
        if value is None:
            result[name] = None
            continue
        if isinstance(value, (str, bytes, bytearray)):
            raise ValueError("native_unbound_action_value_invalid")
        try:
            entries = list(value)
        except TypeError as exc:
            raise ValueError("native_unbound_action_value_invalid") from exc
        normalized = []
        for entry in entries:
            if entry is None:
                normalized.append(None)
            elif (
                isinstance(entry, bool)
                or not isinstance(entry, (int, float, np.number))
                or not math.isfinite(float(entry))
            ):
                raise ValueError("native_unbound_action_value_invalid")
            else:
                value_float = float(entry)
                normalized.append(0.0 if value_float == 0.0 else value_float)
        result[name] = normalized
    return result


def canonicalize_action(action: Any) -> dict[str, Any]:
    raw = raw_action_channels(action)
    channels = {}
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


def _action_velocity_joint_six(action: Mapping[str, Any]) -> float | None:
    values = action.get("joint_velocities")
    if not isinstance(values, list) or len(values) <= 6:
        return None
    value = values[6]
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
    ):
        return None
    return float(value)


def evaluate_action_ledger(
    records: Sequence[Mapping[str, Any]],
    *,
    maximum_production_steps: int,
    retention_steps: int = 60,
) -> dict[str, Any]:
    audit_failures: list[str] = []
    physical_failures: list[str] = []
    close_action_index = lift_action_index = pour_action_index = None
    try:
        if (
            type(maximum_production_steps) is not int
            or maximum_production_steps <= 0
            or type(retention_steps) is not int
            or retention_steps <= 0
            or not isinstance(records, Sequence)
            or isinstance(records, (str, bytes, bytearray))
            or not records
            or len(records) > maximum_production_steps + retention_steps
        ):
            raise ValueError("action_ledger_records_invalid")
        expected_apply_index = 0
        expected_continuation = 0
        entered_pouring = False
        terminal_seen = False
        for index, record in enumerate(records):
            if not isinstance(record, Mapping) or record.get("transition_index") != index:
                raise ValueError("action_ledger_transition_index_invalid")
            state_present = record.get("state_present")
            calls = record.get("controller_call_count")
            continuation = record.get("continuation_index")
            action = record.get("action")
            canonical = record.get("canonical_action")
            apply_count = record.get("apply_count")
            receipt = record.get("action_receipt")
            if type(state_present) is not bool or type(calls) is not int:
                raise ValueError("action_ledger_state_authority_invalid")
            if continuation is not None:
                if continuation != expected_continuation or state_present or calls != 0:
                    raise ValueError("action_ledger_continuation_invalid")
                expected_continuation += 1
            elif not state_present and calls != 0:
                raise ValueError("action_ledger_controller_called_without_state")
            elif state_present and calls != 1:
                raise ValueError("action_ledger_controller_call_count_invalid")
            if terminal_seen and continuation is None:
                audit_failures.append("post_terminal_production_step_forbidden")
            if continuation is not None and action is not None:
                audit_failures.append(
                    "continuation_action_forbidden"
                )
            elif terminal_seen and action is not None:
                audit_failures.append("post_terminal_action_forbidden")
            if record.get("phase_before") == "POURING" or record.get("phase_after") == "POURING":
                entered_pouring = True
            if action is None:
                if canonical is not None or apply_count != 0 or receipt is not None or record.get(
                    "integrating_transition_index"
                ) is not None:
                    audit_failures.append("action_apply_contract_invalid")
                if record.get("apply_index") is not None:
                    audit_failures.append(
                        "continuation_action_forbidden"
                        if continuation is not None
                        else "post_terminal_action_forbidden"
                        if terminal_seen
                        else "action_apply_contract_invalid"
                    )
            else:
                try:
                    raw = raw_action_channels(action)
                    expected_canonical = canonicalize_action(raw)
                except ValueError:
                    audit_failures.append("action_authority_invalid")
                    continue
                if (
                    canonical != expected_canonical
                    or apply_count != 1
                    or record.get("integrating_transition_index") != index + 1
                    or not isinstance(receipt, Mapping)
                    or receipt.get("applied") is not True
                    or receipt.get("normal_return") is not True
                    or receipt.get("apply_count") != 1
                    or receipt.get("action_sha256") != expected_canonical["sha256"]
                ):
                    audit_failures.append("action_apply_contract_invalid")
                if record.get("apply_index") is not None and record.get("apply_index") != expected_apply_index:
                    audit_failures.append("action_apply_index_invalid")
                expected_apply_index += 1
            pick_event = record.get("pick_event")
            pour_event = record.get("pour_event")
            if pick_event is not None and (type(pick_event) is not int or not 0 <= pick_event <= 6):
                audit_failures.append("pick_event_authority_invalid")
            if pour_event is not None and (type(pour_event) is not int or not 0 <= pour_event <= 5):
                audit_failures.append("pour_event_authority_invalid")
            if continuation is not None and (pick_event is not None or pour_event is not None):
                audit_failures.append("continuation_action_forbidden")
            if pour_event == 2 and (
                record.get("phase_before") != "POURING"
                or record.get("phase_after") != "POURING"
            ):
                audit_failures.append("pour_event_two_phase_invalid")
            if pick_event == 4 and action is not None and close_action_index is None:
                close_action_index = index
            if pick_event == 5 and action is not None and lift_action_index is None:
                lift_action_index = index
            if pour_event == 2 and action is not None:
                velocity = _action_velocity_joint_six(action)
                if velocity is not None and velocity != 0.0 and pour_action_index is None:
                    pour_action_index = index
            terminal = record.get("production_terminal")
            if terminal is True:
                terminal_seen = True
        if close_action_index is None:
            physical_failures.append("native_close_action_missing")
        if lift_action_index is None:
            physical_failures.append("native_lift_action_missing")
        elif close_action_index is None or lift_action_index <= close_action_index:
            physical_failures.append("native_close_lift_order_invalid")
        if not entered_pouring:
            physical_failures.append("controller_never_entered_pouring")
        if pour_action_index is None:
            physical_failures.append("pour_event_two_nonzero_joint_six_velocity_missing")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    physical_failures = sorted(set(physical_failures))
    return {
        "audit_valid": not audit_failures,
        "native_sequence_valid": bool(not audit_failures and not physical_failures),
        "audit_failures": audit_failures,
        "physical_failures": physical_failures,
        "close_action_index": close_action_index,
        "lift_action_index": lift_action_index,
        "k_lift": None if lift_action_index is None else lift_action_index + 1,
        "pour_action_index": pour_action_index,
        "k_pour": None if pour_action_index is None else pour_action_index + 1,
    }


def validate_runtime_transition_ledger(
    transitions: Sequence[Mapping[str, Any]],
    *,
    maximum_production_steps: int,
    retention_steps: int = 60,
) -> dict[str, Any]:
    audit_failures: list[str] = []
    try:
        action_ledger = evaluate_action_ledger(
            transitions,
            maximum_production_steps=maximum_production_steps,
            retention_steps=retention_steps,
        )
        audit_failures.extend(action_ledger["audit_failures"])
        prior_world = None
        prior_post = None
        terminal_indices = []
        for index, transition in enumerate(transitions):
            if not isinstance(transition, Mapping) or transition.get("transition_index") != index:
                raise ValueError("runtime_ledger_transition_index_invalid")
            world_index = transition.get("world_index")
            if type(world_index) is not int or (
                prior_world is not None and world_index != prior_world + 1
            ):
                audit_failures.append("runtime_ledger_world_index_discontinuous")
            pre = transition.get("pre")
            post = transition.get("post")
            _state_authority(pre)
            _state_authority(post)
            if prior_post is not None and _canonical_json_bytes(pre) != _canonical_json_bytes(prior_post):
                audit_failures.append("runtime_ledger_state_discontinuous")
            if transition.get("production_terminal") is True:
                if type(transition.get("terminal_success")) is not bool:
                    audit_failures.append("runtime_ledger_terminal_authority_invalid")
                terminal_indices.append(index)
            elif (
                transition.get("production_terminal") is not False
                or transition.get("terminal_success") is not None
            ):
                audit_failures.append("runtime_ledger_terminal_authority_invalid")
            prior_world = world_index
            prior_post = post
        if len(terminal_indices) > 1:
            audit_failures.append("runtime_ledger_multiple_terminals")
        if terminal_indices:
            terminal = terminal_indices[0]
            for transition in transitions[terminal + 1 :]:
                if transition.get("continuation_index") is None:
                    audit_failures.append("runtime_ledger_post_terminal_production_step")
                    break
                if (
                    transition.get("action") is not None
                    or transition.get("canonical_action") is not None
                    or transition.get("apply_count") != 0
                    or transition.get("action_receipt") is not None
                    or transition.get("pick_event") is not None
                    or transition.get("pour_event") is not None
                ):
                    audit_failures.append("runtime_ledger_post_terminal_action")
                    break
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {
        "audit_valid": not audit_failures,
        "audit_failures": audit_failures,
        "terminal_index": None if not terminal_indices else terminal_indices[0],
        "normal_terminal": bool(
            len(terminal_indices) == 1
            and transitions[terminal_indices[0]].get("terminal_outcome") == "FINISHED"
            and transitions[terminal_indices[0]].get("terminal_success") is True
        ),
    }


def _state_authority(state: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, bool]:
    if not isinstance(state, Mapping):
        raise ValueError("state_mapping_required")
    origin = _finite_vector(state.get("origin_m"), field="state_origin")
    orientation = _finite_vector(state.get("orientation_wxyz"), field="state_orientation", length=4)
    if float(np.linalg.norm(orientation)) <= 1.0e-12:
        raise ValueError("state_orientation_invalid")
    linear = _finite_vector(state.get("linear_velocity_m_s"), field="state_linear_velocity")
    angular = _finite_vector(state.get("angular_velocity_rad_s"), field="state_angular_velocity")
    awake = state.get("awake")
    if type(awake) is not bool:
        raise ValueError("state_awake_authority_missing")
    return origin, orientation, linear, angular, awake


def evaluate_native_lift_pour_trace(
    transitions: Sequence[Mapping[str, Any]],
    *,
    retention_steps: int,
    rise_threshold_m: float,
    maximum_production_steps: int = 1500,
    stable_supported_steps: int = 10,
    stable_linear_speed_m_s: float = 0.001,
    stable_angular_speed_degrees_s: float = 0.1,
    stable_origin_displacement_m: float = 0.0001,
    post_pour_rotation_degrees: float = 50.0,
    initial_support_activation_max_absent_reports: int = 0,
    protocol: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    audit_failures: list[str] = []
    physical_failures: list[str] = []
    k_lift = k_loss = k_rise = None
    rotation_degrees = None
    retention_count = 0
    try:
        protocol_spec = (
            None if protocol is None else _require_protocol_spec(protocol)
        )
        composite_support = bool(
            protocol_spec is not None and protocol_spec.get("composite_support") is True
        )
        observation_gap_policy = bool(
            protocol_spec is not None
            and protocol_spec.get("allow_active_support_pair_omission") is True
        )
        topology_required_from_close_to_rise = bool(
            protocol_spec is not None
            and protocol_spec.get("topology_required_from_close_to_rise") is True
        )
        contact_load_bearing_authority = _contact_load_bearing_policy(protocol)
        minimum_noncontact_clearance_m = (
            None
            if not contact_load_bearing_authority
            else _finite_scalar(
                protocol_spec.get("minimum_noncontact_clearance_m"),
                field="minimum_noncontact_clearance_m",
                nonnegative=True,
            )
        )
        if (
            minimum_noncontact_clearance_m is not None
            and minimum_noncontact_clearance_m <= 0.0
        ):
            raise ValueError("minimum_noncontact_clearance_m_invalid")
        if (
            type(retention_steps) is not int
            or retention_steps <= 0
            or type(maximum_production_steps) is not int
            or maximum_production_steps <= 0
            or type(stable_supported_steps) is not int
            or stable_supported_steps <= 0
            or type(initial_support_activation_max_absent_reports) is not int
            or initial_support_activation_max_absent_reports < 0
            or isinstance(rise_threshold_m, bool)
            or not isinstance(rise_threshold_m, (int, float, np.number))
            or not math.isfinite(float(rise_threshold_m))
            or float(rise_threshold_m) <= 0.0
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.number))
                or not math.isfinite(float(value))
                or float(value) < 0.0
                for value in (
                    stable_linear_speed_m_s,
                    stable_angular_speed_degrees_s,
                    stable_origin_displacement_m,
                )
            )
            or isinstance(post_pour_rotation_degrees, bool)
            or not isinstance(post_pour_rotation_degrees, (int, float, np.number))
            or not math.isfinite(float(post_pour_rotation_degrees))
            or float(post_pour_rotation_degrees) <= 0.0
            or not isinstance(transitions, Sequence)
            or isinstance(transitions, (str, bytes, bytearray))
            or not transitions
        ):
            raise ValueError("native_trace_limits_invalid")

        def composite_pair_loss_complete(contact: Mapping[str, Any]) -> bool:
            pairs = contact.get("support_pairs")
            if not isinstance(pairs, list) or not pairs:
                return False
            seen = set()
            for pair in pairs:
                if (
                    not isinstance(pair, Mapping)
                    or not isinstance(pair.get("pair"), list)
                    or len(pair["pair"]) != 2
                    or tuple(pair["pair"]) in seen
                    or type(pair.get("ever_current")) is not bool
                    or type(pair.get("current")) is not bool
                    or type(pair.get("terminal_lost")) is not bool
                ):
                    return False
                seen.add(tuple(pair["pair"]))
                if not pair["ever_current"] or pair["current"] or not pair["terminal_lost"]:
                    return False
            return True

        def observation_gap(contact: Mapping[str, Any]) -> bool | None:
            if not observation_gap_policy:
                return False
            gap = contact.get("support_observation_gap")
            pairs = contact.get("unreported_active_pairs")
            expected = [
                list(sorted((SOURCE_BODY_PATH, support)))
                for support in protocol_spec["support_collider_paths"]
            ]
            if type(gap) is not bool or not isinstance(pairs, list):
                return None
            seen = []
            for paths in pairs:
                if (
                    not isinstance(paths, list)
                    or len(paths) != 2
                    or any(not isinstance(path, str) or not path for path in paths)
                    or paths != sorted(paths)
                    or paths not in expected
                    or paths in seen
                ):
                    return None
                seen.append(paths)
            if seen != [paths for paths in expected if paths in seen] or gap is not bool(seen):
                return None
            return gap

        ledger = evaluate_action_ledger(
            transitions,
            maximum_production_steps=maximum_production_steps,
            retention_steps=retention_steps,
        )
        audit_failures.extend(ledger["audit_failures"])
        physical_failures.extend(ledger["physical_failures"])
        if not ledger["audit_valid"]:
            raise ValueError("action_ledger_authority_invalid")
        k_lift = ledger["k_lift"]
        if k_lift is None or k_lift >= len(transitions):
            physical_failures.append("lift_integration_transition_missing")
            raise StopIteration
        close_integration = ledger["close_action_index"]
        close_integration = None if close_integration is None else close_integration + 1
        initial_pending_reports = 0
        support_activated = False
        observation_gap_indices: set[int] = set()
        physical_classifications_by_index: dict[int, set[str]] = {}
        for index, transition in enumerate(transitions):
            if not isinstance(transition, Mapping) or transition.get("transition_index") != index:
                raise ValueError("native_trace_index_invalid")
            _state_authority(transition.get("pre"))
            _state_authority(transition.get("post"))
            contact = transition.get("contact")
            if not isinstance(contact, Mapping):
                raise ValueError("contact_authority_missing")
            if contact.get("contact_read_once") is not True or contact.get("identity_valid") is not True:
                audit_failures.append("contact_authority_missing")
            gap = observation_gap(contact)
            if gap is None:
                audit_failures.append("support_observation_gap_authority_missing")
            elif gap:
                observation_gap_indices.add(index)
            if composite_support:
                pair_failures = contact.get("support_pair_physical_failures")
                if (
                    not isinstance(pair_failures, Sequence)
                    or isinstance(pair_failures, (str, bytes, bytearray))
                    or any(not isinstance(value, str) for value in pair_failures)
                ):
                    audit_failures.append("support_pair_authority_missing")
                else:
                    physical_failures.extend(pair_failures)
            support_state = contact.get("support_state")
            if support_state not in {"CURRENT", "LOST"}:
                if (
                    initial_support_activation_max_absent_reports > 0
                    and support_state == "UNOBSERVED"
                    and not support_activated
                    and contact.get("support_header_count") == 0
                    and contact.get("support_contact_count") == 0
                    and contact.get("support_friction_anchor_count") == 0
                ):
                    initial_pending_reports += 1
                    if (
                        initial_pending_reports
                        > initial_support_activation_max_absent_reports
                        or contact.get("initial_support_absent_reports")
                        != initial_pending_reports
                    ):
                        audit_failures.append("support_initial_activation_authority_invalid")
                    prefix_failures = contact.get("initial_support_prefix_physical_failures")
                    if (
                        not isinstance(prefix_failures, Sequence)
                        or isinstance(prefix_failures, (str, bytes, bytearray))
                        or any(not isinstance(value, str) for value in prefix_failures)
                    ):
                        audit_failures.append("support_initial_activation_authority_invalid")
                    else:
                        physical_failures.extend(prefix_failures)
                else:
                    audit_failures.append("support_state_authority_missing")
            else:
                activating = support_state == "CURRENT" and not support_activated
                support_activated = support_activated or support_state == "CURRENT"
                if activating and initial_support_activation_max_absent_reports > 0:
                    prefix_failures = contact.get("initial_support_prefix_physical_failures")
                    if (
                        not isinstance(prefix_failures, Sequence)
                        or isinstance(prefix_failures, (str, bytes, bytearray))
                        or any(not isinstance(value, str) for value in prefix_failures)
                    ):
                        audit_failures.append("support_initial_activation_authority_invalid")
                    else:
                        physical_failures.extend(prefix_failures)
            if type(contact.get("source_awake")) is not bool:
                audit_failures.append("source_awake_authority_missing")
            classifications = contact.get("classifications", [])
            if (
                not isinstance(classifications, Sequence)
                or isinstance(classifications, (str, bytes, bytearray))
                or any(not isinstance(value, str) for value in classifications)
            ):
                audit_failures.append("contact_classification_authority_missing")
                classifications = []
            physical_classifications = set(classifications)
            if contact_load_bearing_authority:
                reported_physical = contact.get("physical_classifications")
                clearances = contact.get("noncontact_clearance_m")
                if (
                    not isinstance(reported_physical, list)
                    or any(not isinstance(value, str) for value in reported_physical)
                    or reported_physical != sorted(set(reported_physical))
                    or not isinstance(clearances, Mapping)
                    or set(clearances) - {"SOURCE_OTHER", "ROBOT_ENVIRONMENT"}
                    or any(
                        not isinstance(value, (int, float, np.number))
                        or isinstance(value, bool)
                        or not math.isfinite(float(value))
                        or float(value) <= 0.0
                        for value in clearances.values()
                    )
                ):
                    audit_failures.append("contact_load_bearing_authority_missing")
                else:
                    physical_classifications = set(reported_physical)
                    for classification, clearance in clearances.items():
                        if float(clearance) < float(minimum_noncontact_clearance_m):
                            physical_failures.append(
                                "forbidden_source_proximity_clearance"
                                if classification == "SOURCE_OTHER"
                                else "robot_environment_proximity_clearance"
                            )
                    if "SOURCE_OTHER" in physical_classifications:
                        physical_failures.append("forbidden_source_contact")
                    if "ROBOT_ENVIRONMENT" in physical_classifications:
                        physical_failures.append("robot_environment_contact")
            physical_classifications_by_index[index] = physical_classifications
            if index == 0:
                initial_classifications = physical_classifications
                if initial_classifications & {"LEFT_SOURCE", "RIGHT_SOURCE"}:
                    physical_failures.append("first_observation_source_finger_contact")
                if "SOURCE_OTHER" in initial_classifications:
                    physical_failures.append("first_observation_forbidden_source_contact")
                if "ROBOT_ENVIRONMENT" in initial_classifications:
                    physical_failures.append("first_observation_robot_environment_contact")
            terminal = transition.get("production_terminal")
            if terminal is True:
                if type(transition.get("terminal_success")) is not bool:
                    audit_failures.append("terminal_success_authority_missing")
            elif terminal is not False or transition.get("terminal_success") is not None:
                audit_failures.append("terminal_success_authority_missing")
        if audit_failures:
            raise ValueError("native_trace_contact_authority_invalid")
        terminal_indices = [
            index
            for index, transition in enumerate(transitions)
            if transition.get("production_terminal") is True
        ]
        if not terminal_indices:
            physical_failures.append("normal_production_terminal_missing")
        elif (
            len(terminal_indices) != 1
            or transitions[terminal_indices[0]].get("terminal_outcome") != "FINISHED"
            or transitions[terminal_indices[0]].get("terminal_success") is not True
        ):
            physical_failures.append("normal_production_terminal_missing")
        stable_start = k_lift - stable_supported_steps
        if stable_start < 0:
            physical_failures.append("stable_supported_window_missing")
        else:
            for index in range(stable_start, k_lift):
                transition = transitions[index]
                post_origin, _orientation, linear, angular, awake = _state_authority(
                    transition["post"]
                )
                pre_origin, *_unused = _state_authority(transition["pre"])
                contact = transition["contact"]
                if (
                    contact.get("support_state") != "CURRENT"
                    or index in observation_gap_indices
                    or awake is not True
                    or float(np.linalg.norm(linear)) > float(stable_linear_speed_m_s)
                    or math.degrees(float(np.linalg.norm(angular)))
                    > float(stable_angular_speed_degrees_s)
                    or float(np.linalg.norm(post_origin - pre_origin))
                    > float(stable_origin_displacement_m)
                ):
                    physical_failures.append("stable_supported_window_missing")
                    break
        baseline_origin, *_unused = _state_authority(transitions[k_lift]["pre"])
        baseline_z = float(baseline_origin[2])
        if contact_load_bearing_authority and close_integration is not None:
            for index in range(close_integration):
                if physical_classifications_by_index[index] & {"LEFT_SOURCE", "RIGHT_SOURCE"}:
                    physical_failures.append("preclose_force_bearing_source_finger_contact")
                    break
        for index in range(k_lift, len(transitions)):
            transition = transitions[index]
            post_origin, _orientation, _linear, _angular, awake = _state_authority(
                transition["post"]
            )
            contact = transition["contact"]
            if k_loss is None and contact.get("support_state") == "LOST":
                if composite_support:
                    if not composite_pair_loss_complete(contact) or awake is not True:
                        physical_failures.append("support_pairs_loss_incomplete")
                elif (
                    contact.get("support_event") != "LOST"
                    or contact.get("support_header_count") != 1
                    or contact.get("support_contact_count") != 0
                    or contact.get("support_friction_anchor_count") != 0
                    or awake is not True
                ):
                    audit_failures.append("support_lost_contract_invalid")
                k_loss = index
            if k_loss is not None and index > k_loss and contact.get("support_state") == "CURRENT":
                physical_failures.append("support_recontact")
            if k_loss is not None and k_rise is None and index > k_loss:
                if float(post_origin[2] - baseline_z) >= float(rise_threshold_m):
                    k_rise = index
        if close_integration is not None:
            topology_start = (
                close_integration
                if topology_required_from_close_to_rise
                else max(k_lift, close_integration)
            )
            topology_end = len(transitions) - 1 if k_rise is None else k_rise
            for index in range(topology_start, topology_end + 1):
                contact = transitions[index]["contact"]
                topology = contact.get("topology")
                if not isinstance(topology, Mapping) or topology.get("qualified") is not True:
                    physical_failures.append("bilateral_middle_sidewall_topology_missing")
                if contact.get("forbidden_source_contact") is not False:
                    physical_failures.append("forbidden_source_contact")
                if contact.get("robot_environment_contact") is not False:
                    physical_failures.append("robot_environment_contact")
        if k_loss is None:
            physical_failures.append("support_lost_missing")
        elif any(k_lift <= index <= k_loss for index in observation_gap_indices):
            physical_failures.append("support_observation_gap_before_loss")
        if k_rise is None:
            physical_failures.append("rise_threshold_not_crossed")
        if k_loss is not None and k_rise is not None and k_loss >= k_rise:
            physical_failures.append("support_loss_not_before_rise")
        if k_rise is not None:
            end = k_rise + retention_steps
            if end > len(transitions):
                physical_failures.append("retention_window_incomplete")
            else:
                retention_count = retention_steps
                for index in range(k_rise, end):
                    transition = transitions[index]
                    post_origin, *_state_tail = _state_authority(transition["post"])
                    contact = transition["contact"]
                    if index in observation_gap_indices:
                        physical_failures.append("support_observation_gap_in_retention")
                    if float(post_origin[2] - baseline_z) < float(rise_threshold_m):
                        physical_failures.append("retention_height_lost")
                    if (
                        contact.get("support_state") == "CURRENT"
                        or contact.get("source_support_recontact") is not False
                        or contact.get("support_header_count") != 0
                    ):
                        physical_failures.append("retention_support_recontact")
        k_pour = ledger["k_pour"]
        if k_pour is None or k_pour >= len(transitions):
            physical_failures.append("pour_integration_transition_missing")
        else:
            pour_pre_origin, pour_baseline, *_unused = _state_authority(
                transitions[k_pour]["pre"]
            )
            if k_rise is None:
                physical_failures.append("post_pour_rotation_threshold_not_reached")
            else:
                if float(pour_pre_origin[2] - baseline_z) < float(rise_threshold_m):
                    physical_failures.append("pour_integration_below_lift_threshold")
                if k_pour > 0:
                    integration_start_contact = transitions[k_pour - 1].get("contact")
                    if not isinstance(integration_start_contact, Mapping):
                        raise ValueError("contact_authority_missing")
                    if integration_start_contact.get("forbidden_source_contact") is not False:
                        physical_failures.append(
                            "pour_integration_start_forbidden_source_contact"
                        )
                    if integration_start_contact.get("robot_environment_contact") is not False:
                        physical_failures.append(
                            "pour_integration_start_robot_environment_contact"
                        )
                    if (
                        integration_start_contact.get("source_support_recontact") is not False
                        or integration_start_contact.get("support_state") == "CURRENT"
                        or integration_start_contact.get("support_header_count") != 0
                    ):
                        physical_failures.append("pour_integration_start_support_recontact")
                    if k_pour - 1 in observation_gap_indices:
                        physical_failures.append("support_observation_gap_during_pour")
                rotation_accepted = False
                for index in range(k_pour, len(transitions)):
                    post_origin, orientation, *_unused = _state_authority(
                        transitions[index]["post"]
                    )
                    contact = transitions[index]["contact"]
                    if index in observation_gap_indices:
                        physical_failures.append("support_observation_gap_during_pour")
                    angle = _quaternion_angle_degrees(pour_baseline, orientation)
                    rotation_degrees = max(rotation_degrees or 0.0, angle)
                    if float(post_origin[2] - baseline_z) < float(rise_threshold_m):
                        physical_failures.append("pour_rotation_height_retention_lost")
                    if contact.get("forbidden_source_contact") is not False:
                        physical_failures.append("pour_rotation_forbidden_source_contact")
                    if contact.get("robot_environment_contact") is not False:
                        physical_failures.append("pour_rotation_robot_environment_contact")
                    if (
                        contact.get("source_support_recontact") is not False
                        or contact.get("support_state") == "CURRENT"
                        or contact.get("support_header_count") != 0
                    ):
                        physical_failures.append("pour_rotation_support_recontact")
                    if angle >= float(post_pour_rotation_degrees):
                        rotation_accepted = True
                        break
                if not rotation_accepted:
                    physical_failures.append("post_pour_rotation_threshold_not_reached")
    except StopIteration:
        pass
    except (TypeError, ValueError, IndexError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    physical_failures = sorted(set(physical_failures))
    return {
        "audit_valid": not audit_failures,
        "physical_passed": bool(not audit_failures and not physical_failures),
        "audit_failures": audit_failures,
        "physical_failures": physical_failures,
        "k_lift": k_lift,
        "k_loss": k_loss,
        "k_rise": k_rise,
        "retention_count": retention_count,
        "rotation_degrees": rotation_degrees,
    }


def make_trace_record(
    prior_records: Sequence[Mapping[str, Any]],
    *,
    treatment: str,
    run_nonce: str,
    parent_pid: int,
    child_pid: int,
    run_id: str,
    kind: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        treatment not in TREATMENTS
        or kind
        not in {
            "bootstrap",
            "transition",
            "observation_gap",
            "audit_no_go",
            "runtime_error",
            "terminal",
        }
        or not isinstance(run_nonce, str)
        or not run_nonce
        or type(parent_pid) is not int
        or parent_pid <= 0
        or type(child_pid) is not int
        or child_pid <= 0
        or not isinstance(run_id, str)
        or not run_id
        or not isinstance(payload, Mapping)
    ):
        raise ValueError("native_unbound_trace_identity_invalid")
    previous = prior_records[-1].get("record_sha256") if prior_records else ZERO_SHA256
    if not _is_sha256(previous):
        raise ValueError("native_unbound_trace_previous_hash_invalid")
    record = {
        "schema_version": 1,
        "manifest_type": TRACE_MANIFEST_TYPE,
        "record_index": len(prior_records),
        "treatment": treatment,
        "run_nonce": run_nonce,
        "parent_pid": parent_pid,
        "child_pid": child_pid,
        "run_id": run_id,
        "kind": kind,
        "previous_sha256": previous,
        "payload": copy.deepcopy(dict(payload)),
    }
    return {**record, "record_sha256": _canonical_json_sha256(record)}


def _bind_trace_bootstrap_runtime_evidence(
    records: Sequence[Mapping[str, Any]],
    *,
    treatment: str,
    run_nonce: str,
    parent_pid: int,
    child_pid: int,
    run_id: str,
    runtime_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Rechain retained events under one final, report-identical bootstrap payload."""

    events = []
    for record in records:
        if not isinstance(record, Mapping):
            raise RuntimeError("trace_rebind_record_invalid")
        kind = record.get("kind")
        payload = record.get("payload")
        if kind == "bootstrap":
            continue
        if kind not in {
            "transition",
            "observation_gap",
            "audit_no_go",
            "runtime_error",
        } or not isinstance(payload, Mapping):
            raise RuntimeError("trace_rebind_record_invalid")
        events.append((kind, copy.deepcopy(dict(payload))))
    rebound: list[dict[str, Any]] = [
        make_trace_record(
            [],
            treatment=treatment,
            run_nonce=run_nonce,
            parent_pid=parent_pid,
            child_pid=child_pid,
            run_id=run_id,
            kind="bootstrap",
            payload={"runtime_evidence": copy.deepcopy(dict(runtime_evidence))},
        )
    ]
    for kind, payload in events:
        rebound.append(
            make_trace_record(
                rebound,
                treatment=treatment,
                run_nonce=run_nonce,
                parent_pid=parent_pid,
                child_pid=child_pid,
                run_id=run_id,
                kind=kind,
                payload=payload,
            )
        )
    return rebound


def validate_trace_records(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_treatment: str,
    expected_nonce: str,
    expected_parent_pid: int,
    expected_child_pid: int,
    expected_run_id: str,
    expected_runtime_status: str | None = None,
    expected_lifecycle_status: str | None = None,
) -> dict[str, Any]:
    if (
        expected_treatment not in TREATMENTS
        or not isinstance(records, Sequence)
        or isinstance(records, (str, bytes, bytearray))
        or not records
    ):
        raise ValueError("native_unbound_trace_records_invalid")
    previous = ZERO_SHA256
    terminal_index = None
    terminal_record = None
    failure_kind = None
    bootstrap_count = 0
    bootstrap_runtime_evidence_sha256 = None
    for index, value in enumerate(records):
        if terminal_index is not None:
            raise ValueError("native_unbound_trace_after_terminal")
        if not isinstance(value, Mapping):
            raise ValueError("native_unbound_trace_record_invalid")
        record = dict(value)
        digest = record.pop("record_sha256", None)
        if (
            record.get("schema_version") != 1
            or record.get("manifest_type") != TRACE_MANIFEST_TYPE
            or record.get("record_index") != index
            or record.get("treatment") != expected_treatment
            or record.get("run_nonce") != expected_nonce
            or record.get("parent_pid") != expected_parent_pid
            or record.get("child_pid") != expected_child_pid
            or record.get("run_id") != expected_run_id
            or record.get("previous_sha256") != previous
            or record.get("kind")
            not in {
                "bootstrap",
                "transition",
                "observation_gap",
                "audit_no_go",
                "runtime_error",
                "terminal",
            }
            or not isinstance(record.get("payload"), Mapping)
            or digest != _canonical_json_sha256(record)
        ):
            raise ValueError("native_unbound_trace_record_invalid")
        previous = digest
        if record["kind"] == "bootstrap":
            bootstrap_count += 1
            payload = record["payload"]
            if index != 0 or set(payload) != {"runtime_evidence"} or not isinstance(
                payload.get("runtime_evidence"), Mapping
            ):
                raise ValueError("native_unbound_trace_bootstrap_invalid")
            bootstrap_runtime_evidence_sha256 = _canonical_json_sha256(
                payload["runtime_evidence"]
            )
        elif index == 0:
            raise ValueError("native_unbound_trace_bootstrap_invalid")
        if record["kind"] in {"audit_no_go", "runtime_error"}:
            if failure_kind is not None or terminal_index is not None:
                raise ValueError("native_unbound_trace_status_contradiction")
            failure_kind = record["kind"]
        elif failure_kind is not None and record["kind"] in {"transition", "observation_gap"}:
            raise ValueError("native_unbound_trace_status_contradiction")
        if record["kind"] == "terminal":
            terminal_index = index
            terminal_record = copy.deepcopy(dict(value))
    if terminal_index is None:
        raise ValueError("native_unbound_trace_terminal_missing")
    if bootstrap_count != 1 or bootstrap_runtime_evidence_sha256 is None:
        raise ValueError("native_unbound_trace_bootstrap_invalid")
    inferred_status = (
        "runtime_error"
        if failure_kind == "runtime_error"
        else "audit_no_go"
        if failure_kind == "audit_no_go"
        else "ok"
    )
    inferred_lifecycle = CHILD_LIFECYCLE_BY_RUNTIME_STATUS[inferred_status]
    terminal_payload = terminal_record.get("payload") if isinstance(terminal_record, Mapping) else None
    if (
        terminal_payload
        != {
            "runtime_status": inferred_status,
            "lifecycle_status": inferred_lifecycle,
        }
        or (
            expected_runtime_status is None
            and expected_lifecycle_status is not None
        )
        or (
            expected_runtime_status is not None
            and (
                expected_runtime_status != inferred_status
                or expected_lifecycle_status != inferred_lifecycle
            )
        )
    ):
        raise ValueError("native_unbound_trace_status_contradiction")
    return {
        "valid": True,
        "record_count": len(records),
        "terminal_index": terminal_index,
        "terminal_record": terminal_record,
        "chain_sha256": previous,
        "runtime_status": inferred_status,
        "lifecycle_status": inferred_lifecycle,
        "bootstrap_runtime_evidence_sha256": bootstrap_runtime_evidence_sha256,
    }


def _internal_module_path(module: str) -> Path | None:
    if not module or module.split(".", 1)[0] not in {
        "factories",
        "tasks",
        "controllers",
        "robots",
        "utils",
        "data_collectors",
        "isaacsim_compat",
    }:
        return None
    base = REPO_ROOT.joinpath(*module.split("."))
    candidate = base.with_suffix(".py")
    if candidate.is_file():
        return candidate
    package = base / "__init__.py"
    return package if package.is_file() else None


def _python_import_closure(seed_files: Sequence[str]) -> dict[str, Any]:
    queue: deque[Path] = deque()
    visited: set[Path] = set()
    unresolved: list[str] = []
    for relative in seed_files:
        if not isinstance(relative, str):
            raise ValueError("native_unbound_identity_seed_invalid")
        path = (REPO_ROOT / relative).resolve()
        try:
            path.relative_to(REPO_ROOT)
        except ValueError as exc:
            raise ValueError("native_unbound_identity_seed_escape") from exc
        if not path.is_file():
            raise ValueError(f"native_unbound_identity_seed_missing:{relative}")
        queue.append(path)
    while queue:
        path = queue.popleft()
        if path in visited:
            continue
        visited.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            raise ValueError(f"native_unbound_identity_parse_invalid:{path}") from exc
        package = path.relative_to(REPO_ROOT).with_suffix("").parts[:-1]
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    prefix = package[: max(0, len(package) - node.level + 1)]
                    suffix = tuple(node.module.split(".")) if node.module else ()
                    modules.append(".".join((*prefix, *suffix)))
                elif node.module:
                    modules.append(node.module)
            for module in modules:
                candidate = _internal_module_path(module)
                if candidate is not None:
                    queue.append(candidate.resolve())
    records = {
        path.relative_to(REPO_ROOT).as_posix(): sha256_file(path)
        for path in sorted(visited, key=lambda item: item.as_posix())
    }
    payload = {"files": records, "unresolved": sorted(set(unresolved))}
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _static_call_method(call: ast.Call) -> str | None:
    function = call.func
    if isinstance(function, ast.Attribute):
        return function.attr
    if isinstance(function, ast.Name):
        return function.id
    return None


def _static_string_literals(node: ast.AST) -> list[str]:
    return [
        value.value
        for value in ast.walk(node)
        if isinstance(value, ast.Constant) and isinstance(value.value, str)
    ]


def _static_production_closure_audit(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    """Identify source-control calls before runtime adapters are selected.

    The closure check deliberately does not infer that an unavailable tensor method is
    reachable. A direct source-targeted writer is forbidden statically; generic
    ObjectUtils/gripper routes remain runtime-audited because their target is data-driven.
    """

    audit_failures: list[str] = []
    calls: list[dict[str, Any]] = []
    forbidden_calls: list[dict[str, Any]] = []
    required_runtime_surfaces: set[str] = set()
    try:
        if not isinstance(diagnostic, Mapping):
            raise ValueError("static_production_closure_diagnostic_invalid")
        _protocol_spec_for_diagnostic(diagnostic)
        closure = _python_import_closure(diagnostic["required_implementation_files"])
        surface_by_method = {
            "set_object_position": "object_utils_set_object_position",
            "add_object_to_gripper": "gripper_add_object_to_gripper",
            "update_grasped_object_position": "gripper_update_grasped_object_position",
            "release_object": "gripper_release_object",
            "set_world_poses": "plural_prim_view_world_poses",
            "set_local_poses": "plural_prim_view_local_poses",
            "set_velocities": "plural_prim_view_velocities",
            "set_linear_velocities": "plural_prim_view_linear_velocities",
            "set_angular_velocities": "plural_prim_view_angular_velocities",
            "set_kinematic_targets": "physics_view_kinematic_targets",
            "set_dynamic_targets": "physics_view_dynamic_targets",
            "set_transforms": "physics_view_transforms",
            "apply_forces": "physics_view_forces",
            "apply_torques": "physics_view_torques",
            "apply_impulses": "physics_view_impulses",
            "apply_forces_and_torques": "physics_view_forces_torques_impulses",
            "apply_forces_and_torques_at_pos": "physics_view_force_at_position",
            "apply_forces_and_torques_at_position": "physics_view_force_at_position",
        }
        generic_mutators = {
            "Set",
            "SetTargets",
            "AddTarget",
            "RemoveTarget",
            "AddRelationshipTarget",
            "RemoveRelationshipTarget",
        }
        for relative in sorted(closure["files"]):
            path = REPO_ROOT / relative
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                method = _static_call_method(node)
                if method not in surface_by_method and method not in generic_mutators:
                    continue
                literals = _static_string_literals(node)
                source_literals = sorted(
                    value for value in literals if _path_partition(value) == "source"
                )
                surface = surface_by_method.get(method)
                record = {
                    "file": relative,
                    "line": node.lineno,
                    "method": method,
                    "surface": surface,
                    "source_literals": source_literals,
                }
                calls.append(record)
                if surface == "object_utils_set_object_position":
                    required_runtime_surfaces.add(surface)
                    continue
                if surface in _GRIPPER_AUDIT_SURFACES:
                    # The gripper keeps its target in object state, so a single
                    # reachable gripper call requires all of its mutating routes.
                    required_runtime_surfaces.update(_GRIPPER_AUDIT_SURFACES)
                    if source_literals:
                        forbidden_calls.append(record)
                    continue
                if surface in _TENSOR_WRITER_SURFACES:
                    if source_literals:
                        forbidden_calls.append(record)
                    elif not literals:
                        required_runtime_surfaces.add(surface)
                    continue
                if method in generic_mutators and source_literals:
                    forbidden_calls.append(record)
        if forbidden_calls:
            audit_failures.append("static_forbidden_source_control_call")
    except (OSError, SyntaxError, TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
        closure = {"files": {}, "unresolved": [], "sha256": None}
    payload = {
        "audit_valid": not audit_failures,
        "audit_failures": sorted(set(audit_failures)),
        "closure_sha256": closure.get("sha256"),
        "closure_files": closure.get("files"),
        "calls": sorted(calls, key=lambda item: (item["file"], item["line"], item["method"])),
        "forbidden_calls": sorted(
            forbidden_calls, key=lambda item: (item["file"], item["line"], item["method"])
        ),
        "required_runtime_surfaces": sorted(required_runtime_surfaces),
        "not_applicable_runtime_surfaces": sorted(
            (set(REQUIRED_WRITER_AUDIT_SURFACES) - {
                "source_adapter_read_only",
                "usd_mutation_notice",
            })
            - required_runtime_surfaces
        ),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _asset_dependency_closure(entry_path: Path) -> dict[str, Any]:
    entry = entry_path.resolve()
    if not entry.is_file():
        raise ValueError(f"native_unbound_asset_missing:{entry}")
    queue: deque[Path] = deque([entry])
    visited: set[Path] = set()
    unresolved: list[str] = []
    pattern = re.compile(r"@([^@]+)@")
    while queue:
        path = queue.popleft()
        if path in visited:
            continue
        visited.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for reference in pattern.findall(text):
            if "://" in reference or reference.startswith("${"):
                unresolved.append(reference)
                continue
            target = (path.parent / reference).resolve()
            if target.is_file():
                queue.append(target)
            else:
                unresolved.append(reference)
    files = [
        {
            "path": path.relative_to(REPO_ROOT).as_posix()
            if path.is_relative_to(REPO_ROOT)
            else str(path),
            "sha256": sha256_file(path),
            "byte_count": path.stat().st_size,
        }
        for path in sorted(visited, key=lambda item: str(item))
    ]
    payload = {
        "entry_path": str(entry),
        "entry_sha256": sha256_file(entry),
        "files": files,
        "unresolved": sorted(set(unresolved)),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def build_parent_identity(config: Mapping[str, Any]) -> dict[str, Any]:
    diagnostic = _require_pinned_diagnostic(config)
    local_franka = resolve_local_franka_asset(diagnostic)
    local_scene = resolve_local_scene_asset(diagnostic)
    seeds = diagnostic["required_implementation_files"]
    if (
        not isinstance(seeds, Sequence)
        or isinstance(seeds, (str, bytes, bytearray))
        or not seeds
    ):
        raise ValueError("native_unbound_identity_implementation_missing")
    implementation = _python_import_closure([str(value) for value in seeds])
    asset = _asset_dependency_closure(Path(local_scene["absolute_usd_path"]))
    payload = {
        "python_executable": str(Path(sys.executable).resolve()),
        "config_sha256": _sha256_bytes(_canonical_json_bytes(config)),
        "runner": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "implementation": implementation,
        "asset_dependency_closure": asset,
        "local_franka": local_franka,
        "local_scene": local_scene,
    }
    return {**payload, "identity_sha256": _canonical_json_sha256(payload)}


def _extract_transitions(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for record in records:
        if record.get("kind") == "transition":
            payload = record.get("payload")
            if not isinstance(payload, Mapping):
                raise ValueError("native_unbound_transition_payload_missing")
            result.append(copy.deepcopy(dict(payload)))
    if not result:
        raise ValueError("native_unbound_transitions_missing")
    return result


def _extract_observation_gap_journals(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for record in records:
        if record.get("kind") == "observation_gap":
            payload = record.get("payload")
            if not isinstance(payload, Mapping):
                raise ValueError("native_unbound_observation_gap_payload_missing")
            result.append(copy.deepcopy(dict(payload)))
    return result


def evaluate_control_instrumented_nonperturbation(
    control: Sequence[Mapping[str, Any]],
    instrumented: Sequence[Mapping[str, Any]],
    *,
    comparison_tolerances: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    audit_failures: list[str] = []
    try:
        tolerances = (
            PINNED_DIAGNOSTIC["comparison_tolerances"]
            if comparison_tolerances is None
            else comparison_tolerances
        )
        expected_tolerances = {
            "origin_m",
            "orientation_degrees",
            "linear_velocity_m_s",
            "angular_velocity_degrees_s",
        }
        if (
            not isinstance(tolerances, Mapping)
            or set(tolerances) != expected_tolerances
        ):
            raise ValueError("nonperturbation_tolerances_invalid")
        tolerance_values = {
            name: _finite_scalar(
                tolerances[name], field=f"nonperturbation_{name}", nonnegative=True
            )
            for name in expected_tolerances
        }
        if (
            not isinstance(control, Sequence)
            or not isinstance(instrumented, Sequence)
            or isinstance(control, (str, bytes, bytearray))
            or isinstance(instrumented, (str, bytes, bytearray))
            or len(control) != len(instrumented)
            or not control
        ):
            raise ValueError("nonperturbation_schedule_invalid")
        for index, (first, second) in enumerate(zip(control, instrumented)):
            if not isinstance(first, Mapping) or not isinstance(second, Mapping):
                raise ValueError("nonperturbation_record_invalid")
            if (
                first.get("transition_index") != index
                or second.get("transition_index") != index
                or first.get("world_index") != second.get("world_index")
            ):
                audit_failures.append("nonperturbation_world_index_mismatch")
                continue
            for name in (
                "phase_before",
                "phase_after",
                "pick_event",
                "pour_event",
                "continuation_index",
            ):
                if first.get(name) != second.get(name):
                    audit_failures.append("nonperturbation_action_phase_mismatch")
                    break
            for name in ("state_present", "controller_call_count"):
                if first.get(name) != second.get(name):
                    audit_failures.append("nonperturbation_controller_mismatch")
                    break
            for name in (
                "action",
                "canonical_action",
                "apply_count",
                "integrating_transition_index",
                "apply_index",
            ):
                if first.get(name) != second.get(name):
                    audit_failures.append("nonperturbation_action_identity_mismatch")
                    break
            if first.get("action_receipt") != second.get("action_receipt"):
                audit_failures.append("nonperturbation_action_receipt_mismatch")
            if (
                first.get("production_terminal") != second.get("production_terminal")
                or first.get("terminal_outcome") != second.get("terminal_outcome")
                or first.get("terminal_success") != second.get("terminal_success")
            ):
                audit_failures.append("nonperturbation_terminal_mismatch")
            for state_name in ("pre", "post"):
                one = first.get(state_name)
                two = second.get(state_name)
                one_origin, one_orientation, one_linear, one_angular, one_awake = _state_authority(one)
                two_origin, two_orientation, two_linear, two_angular, two_awake = _state_authority(two)
                if float(np.linalg.norm(one_origin - two_origin)) > tolerance_values["origin_m"]:
                    audit_failures.append("nonperturbation_origin_mismatch")
                if (
                    _quaternion_angle_degrees(one_orientation, two_orientation)
                    > tolerance_values["orientation_degrees"]
                ):
                    audit_failures.append("nonperturbation_orientation_mismatch")
                if (
                    float(np.linalg.norm(one_linear - two_linear))
                    > tolerance_values["linear_velocity_m_s"]
                ):
                    audit_failures.append("nonperturbation_linear_velocity_mismatch")
                if (
                    math.degrees(float(np.linalg.norm(one_angular - two_angular)))
                    > tolerance_values["angular_velocity_degrees_s"]
                ):
                    audit_failures.append("nonperturbation_angular_velocity_mismatch")
                if one_awake is not two_awake:
                    audit_failures.append("nonperturbation_awake_mismatch")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {
        "audit_valid": not audit_failures,
        "perturbation_detected": bool(audit_failures),
        "audit_failures": audit_failures,
    }


def _run_runtime_child(args: argparse.Namespace) -> int:
    from isaacsim import SimulationApp

    diagnostics = _RuntimeDiagnosticEmitter()
    app = SimulationApp({"headless": bool(args.headless), "width": 64, "height": 64})
    try:
        install_runtime_diagnostic_stack_dump(diagnostics)
        from isaacsim_compat import install_legacy_isaacsim_aliases

        install_legacy_isaacsim_aliases()
        import isaacsim
        import omni.kit.app
        import omni.usd
        from omni.isaac.core.prims import RigidPrimView
        from isaacsim.core.api import World
        from isaacsim.core.utils.stage import add_reference_to_stage, get_stage_units
        from omegaconf import OmegaConf
        from omni.physx import get_physx_simulation_interface
        from pxr import PhysicsSchemaTools, UsdUtils

        from factories.robot_factory import create_robot
        from factories.task_factory import create_task
        from factories.controller_factory import create_controller
        from utils.object_utils import ObjectUtils

        return _runtime_child_execute(
            args,
            app=app,
            isaacsim_module=isaacsim,
            omni_usd=omni.usd,
            world_type=World,
            kit_app=omni.kit.app.get_app(),
            rigid_prim_view_type=RigidPrimView,
            add_reference_to_stage=add_reference_to_stage,
            get_stage_units=get_stage_units,
            omega_conf=OmegaConf,
            get_simulation_interface=get_physx_simulation_interface,
            resolve_path=PhysicsSchemaTools.intToSdfPath,
            sdf_path_to_int=PhysicsSchemaTools.sdfPathToInt,
            stage_cache=UsdUtils.StageCache.Get(),
            create_robot=create_robot,
            create_task=create_task,
            create_controller=create_controller,
            object_utils_type=ObjectUtils,
            diagnostics=diagnostics,
        )
    finally:
        # The child writes its cleanup receipt before the application is closed.
        try:
            with diagnostics.phase("application.close"):
                app.close()
        except BaseException:
            return 1


def _runtime_world_counter(world: Any) -> int:
    value = getattr(world, "current_time_step_index", None)
    value = value() if callable(value) else value
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise AuditNoGo("world_counter_authority_missing", type(value).__name__)
    return int(value)


def _runtime_world_is_playing(world: Any) -> bool:
    reader = getattr(world, "is_playing", None)
    if not callable(reader):
        raise AuditNoGo("world_playback_authority_missing", type(world).__name__)
    try:
        value = reader()
    except BaseException as exc:
        raise AuditNoGo("world_playback_authority_missing", type(exc).__name__) from exc
    if type(value) is not bool:
        raise AuditNoGo("world_playback_authority_missing", type(value).__name__)
    return value


def _runtime_native(value: Any) -> Any:
    if value is None or isinstance(
        value, (str, bool, int, float, np.ndarray, np.generic)
    ):
        return _json_native(value)
    if isinstance(value, Mapping):
        return {str(key): _runtime_native(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_runtime_native(item) for item in value]
    try:
        return [_runtime_native(item) for item in value]
    except TypeError:
        return str(value)


def _runtime_row_matrix(stage: Any, path: str) -> np.ndarray:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise AuditNoGo("runtime_prim_missing", path)
    matrix = np.asarray(
        UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()),
        dtype=np.float64,
    )
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise AuditNoGo("runtime_world_matrix_invalid", path)
    return matrix


def _runtime_enabled_colliders(stage: Any, body_path: str, *, require_nonempty: bool) -> list[str]:
    from pxr import Usd, UsdPhysics

    root = stage.GetPrimAtPath(body_path)
    if not root or not root.IsValid():
        raise AuditNoGo("runtime_body_missing", body_path)
    colliders = []
    for prim in Usd.PrimRange(root):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is not False:
            colliders.append(str(prim.GetPath()))
    if require_nonempty and not colliders:
        raise AuditNoGo("runtime_enabled_colliders_missing", body_path)
    return sorted(set(colliders))


def _runtime_bound(stage: Any, path: str) -> dict[str, Any]:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise AuditNoGo("runtime_bound_prim_missing", path)
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[
            UsdGeom.Tokens.default_,
            UsdGeom.Tokens.proxy,
            UsdGeom.Tokens.render,
        ],
        useExtentsHint=False,
        ignoreVisibility=True,
    )
    local_bound = cache.ComputeLocalBound(prim)
    extent = local_bound.GetRange()
    low = [float(value) for value in extent.GetMin()]
    high = [float(value) for value in extent.GetMax()]
    local_matrix = np.asarray(local_bound.GetMatrix(), dtype=np.float64)
    parent = prim.GetParent()
    parent_matrix = np.asarray(
        UsdGeom.Xformable(parent).ComputeLocalToWorldTransform(Usd.TimeCode.Default()),
        dtype=np.float64,
    )
    record = {
        "local_min_m": low,
        "local_max_m": high,
        "world_from_local": (local_matrix @ parent_matrix).tolist(),
    }
    _bound_corners(record)
    return record


def _runtime_rigid_owner(stage: Any, collider_path: str) -> str:
    from pxr import UsdPhysics

    prim = stage.GetPrimAtPath(collider_path)
    while prim and prim.IsValid():
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            return str(prim.GetPath())
        prim = prim.GetParent()
    raise AuditNoGo("runtime_collider_owner_unresolved", collider_path)


def _runtime_all_enabled_colliders(stage: Any) -> list[str]:
    from pxr import Usd, UsdPhysics

    result = []
    for prim in Usd.PrimRange.Stage(stage):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is not False:
            result.append(str(prim.GetPath()))
    return sorted(set(result))


def _runtime_actor_owner(stage: Any, collider_path: str) -> str:
    try:
        return _runtime_rigid_owner(stage, collider_path)
    except AuditNoGo:
        return collider_path


def _runtime_contact_identities(
    stage: Any, *, diagnostic: Mapping[str, Any]
) -> dict[str, Any]:
    source = _runtime_enabled_colliders(stage, SOURCE_BODY_PATH, require_nonempty=True)
    support_paths = _diagnostic_support_collider_paths(diagnostic)
    support = []
    for path in support_paths:
        resolved = _runtime_enabled_colliders(stage, path, require_nonempty=True)
        if resolved != [path]:
            raise AuditNoGo("support_collider_identity_ambiguous", json.dumps(resolved))
        support.extend(resolved)
    left = _runtime_enabled_colliders(stage, LEFT_FINGER_BODY_PATH, require_nonempty=True)
    right = _runtime_enabled_colliders(stage, RIGHT_FINGER_BODY_PATH, require_nonempty=True)
    hand = _runtime_enabled_colliders(stage, HAND_BODY_PATH, require_nonempty=False)
    if source != [SOURCE_BODY_PATH]:
        raise AuditNoGo("source_collider_identity_invalid", json.dumps(source))
    if support != support_paths:
        raise AuditNoGo("support_collider_identity_ambiguous", json.dumps(support))
    all_colliders = [*source, *support, *left, *right, *hand]
    if len(set(all_colliders)) != len(all_colliders):
        raise AuditNoGo("collider_identity_overlap", json.dumps(all_colliders))
    other = sorted(set(_runtime_all_enabled_colliders(stage)) - set(all_colliders))
    all_sealed = [*all_colliders, *other]
    return {
        "source_colliders": source,
        "support_colliders": support,
        "left_colliders": left,
        "right_colliders": right,
        "hand_colliders": hand,
        "other_colliders": other,
        "collider_owners": {
            path: _runtime_actor_owner(stage, path) for path in all_sealed
        },
    }


def _runtime_dynamic_body_paths(stage: Any) -> list[str]:
    from pxr import Usd, UsdPhysics

    result = []
    for root_path in (SOURCE_ROOT_PATH, ROBOT_ROOT_PATH):
        root = stage.GetPrimAtPath(root_path)
        if not root or not root.IsValid():
            raise AuditNoGo("dynamic_body_root_missing", root_path)
        for prim in Usd.PrimRange(root):
            if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
                continue
            body = UsdPhysics.RigidBodyAPI(prim)
            enabled = body.GetRigidBodyEnabledAttr().Get()
            kinematic = body.GetKinematicEnabledAttr().Get()
            if enabled is not False and kinematic is not True:
                result.append(str(prim.GetPath()))
    result = sorted(set(result))
    if SOURCE_BODY_PATH not in result:
        raise AuditNoGo("source_dynamic_body_missing", json.dumps(result))
    return result


def _runtime_live_geometry(stage: Any, sealed: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(sealed, Mapping):
        raise AuditNoGo("geometry_seal_missing", "not a mapping")
    source = sealed.get("source")
    fingers = sealed.get("finger_colliders")
    if not isinstance(source, Mapping) or not isinstance(fingers, Mapping):
        raise AuditNoGo("geometry_seal_missing", "source or fingers")
    live_source = copy.deepcopy(dict(source))
    live_source["world_from_local"] = _runtime_bound(stage, SOURCE_BODY_PATH)[
        "world_from_local"
    ]
    live_fingers = {}
    for path, bound in fingers.items():
        if not isinstance(bound, Mapping):
            raise AuditNoGo("geometry_seal_invalid", str(path))
        live = copy.deepcopy(dict(bound))
        live["world_from_local"] = _runtime_bound(stage, str(path))["world_from_local"]
        live_fingers[str(path)] = live
    return {
        "gravity_world_m_s2": copy.deepcopy(sealed["gravity_world_m_s2"]),
        "source": live_source,
        "source_reset_world_from_local": copy.deepcopy(
            sealed["source_reset_world_from_local"]
        ),
        "finger_colliders": live_fingers,
        "normalized_height_range": copy.deepcopy(sealed["normalized_height_range"]),
        "pad_edge_margin_m": sealed["pad_edge_margin_m"],
        "inward_face_distance_tolerance_m": sealed.get(
            "inward_face_distance_tolerance_m", 0.005
        ),
        "maximum_vertical_normal_cosine": sealed["maximum_vertical_normal_cosine"],
        "minimum_inward_face_cosine": sealed["minimum_inward_face_cosine"],
    }


def _runtime_is_sleeping(
    simulation_interface: Any,
    *,
    stage_id: int,
    source_path: str,
    sdf_path_to_int: Any,
) -> bool:
    method = getattr(simulation_interface, "is_sleeping", None)
    if not callable(method):
        raise AuditNoGo("physx_is_sleeping_unavailable", "method missing")
    path_id = sdf_path_to_int(source_path)
    attempts = ((stage_id, path_id), (stage_id, source_path), (path_id,), (source_path,))
    errors = []
    for arguments in attempts:
        try:
            value = method(*arguments)
        except BaseException as exc:
            errors.append(f"{len(arguments)}:{type(exc).__name__}")
            continue
        if isinstance(value, np.ndarray):
            value = bool(value.reshape(-1)[0]) if value.size == 1 else None
        if type(value) is bool:
            return value
        errors.append(f"{len(arguments)}:result={type(value).__name__}")
    raise AuditNoGo("physx_is_sleeping_unavailable", ",".join(errors))


class RuntimeReadOnlySourceAdapter:
    """Read one rigid body through Isaac 4.1's legacy high-level RigidPrimView."""

    def __init__(self, rigid_prim_view_type: Any, source_body_path: str) -> None:
        if source_body_path != SOURCE_BODY_PATH:
            raise AuditNoGo("source_read_adapter_path_invalid", str(source_body_path))
        if not callable(rigid_prim_view_type):
            raise AuditNoGo("source_read_adapter_view_unavailable", "RigidPrimView")
        try:
            view = rigid_prim_view_type(
                prim_paths_expr=source_body_path,
                name="native_unbound_source_reader",
                reset_xform_properties=False,
                prepare_contact_sensors=False,
            )
        except BaseException as exc:
            raise AuditNoGo(
                "source_read_adapter_view_unavailable", type(exc).__name__
            ) from exc
        self._source_body_path = source_body_path
        self._view = view
        self._initialized = False
        self._readbacks: set[str] = set()

    def initialize(self) -> None:
        initializer = getattr(self._view, "initialize", None)
        if not callable(initializer):
            raise AuditNoGo("source_read_adapter_initialize_unavailable", type(self._view).__name__)
        try:
            initializer()
        except BaseException as exc:
            raise AuditNoGo(
                "source_read_adapter_initialize_failed", type(exc).__name__
            ) from exc
        count = getattr(self._view, "count", None)
        if isinstance(count, bool) or not isinstance(count, (int, np.integer)) or int(count) != 1:
            raise AuditNoGo("source_read_adapter_count_invalid", str(count))
        paths = getattr(self._view, "prim_paths", None)
        if (
            not isinstance(paths, Sequence)
            or isinstance(paths, (str, bytes, bytearray))
            or [str(path) for path in paths] != [self._source_body_path]
        ):
            raise AuditNoGo("source_read_adapter_identity_invalid", str(paths))
        if not all(
            callable(getattr(self._view, method, None))
            for method in (
                "get_world_poses",
                "get_linear_velocities",
                "get_angular_velocities",
            )
        ):
            raise AuditNoGo(
                "source_read_adapter_readback_unavailable", type(self._view).__name__
            )
        self._initialized = True

    @staticmethod
    def _row(value: Any, *, width: int, field: str) -> np.ndarray:
        try:
            array = np.asarray(value, dtype=np.float64).reshape((-1, width))
        except (TypeError, ValueError) as exc:
            raise AuditNoGo("source_read_adapter_readback_invalid", field) from exc
        if array.shape != (1, width) or not np.isfinite(array).all():
            raise AuditNoGo("source_read_adapter_readback_invalid", field)
        return array[0]

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise AuditNoGo("source_read_adapter_not_initialized", self._source_body_path)

    def get_world_pose(self) -> tuple[list[float], list[float]]:
        self._require_initialized()
        try:
            positions, orientations = self._view.get_world_poses()
        except BaseException as exc:
            raise AuditNoGo("source_read_adapter_readback_invalid", "world_poses") from exc
        position = self._row(positions, width=3, field="world_positions")
        orientation = self._row(orientations, width=4, field="world_orientations")
        self._readbacks.add("world_pose")
        return position.tolist(), orientation.tolist()

    def get_linear_velocity(self) -> list[float]:
        self._require_initialized()
        try:
            velocity = self._view.get_linear_velocities()
        except BaseException as exc:
            raise AuditNoGo("source_read_adapter_readback_invalid", "linear_velocities") from exc
        self._readbacks.add("linear_velocity")
        return self._row(velocity, width=3, field="linear_velocities").tolist()

    def get_angular_velocity(self) -> list[float]:
        self._require_initialized()
        try:
            velocity = self._view.get_angular_velocities()
        except BaseException as exc:
            raise AuditNoGo("source_read_adapter_readback_invalid", "angular_velocities") from exc
        self._readbacks.add("angular_velocity")
        return self._row(velocity, width=3, field="angular_velocities").tolist()

    def contract(self) -> dict[str, Any]:
        return {
            "kind": "omni.isaac.core.prims.RigidPrimView",
            "source_body_path": self._source_body_path,
            "count": getattr(self._view, "count", None),
            "initialized": self._initialized,
            "reset_xform_properties": False,
            "prepare_contact_sensors": False,
            "read_only": True,
            "readbacks": {
                "world_pose": "world_pose" in self._readbacks,
                "linear_velocity": "linear_velocity" in self._readbacks,
                "angular_velocity": "angular_velocity" in self._readbacks,
            },
        }


def _runtime_source_state(
    source_body: Any,
    *,
    simulation_interface: Any,
    stage_id: int,
    sdf_path_to_int: Any,
) -> dict[str, Any]:
    position, orientation = source_body.get_world_pose()
    origin = _finite_vector(position, field="source_origin")
    quaternion = _finite_vector(orientation, field="source_orientation", length=4)
    if float(np.linalg.norm(quaternion)) <= 1.0e-12:
        raise AuditNoGo("source_orientation_invalid", str(orientation))
    linear = _finite_vector(
        source_body.get_linear_velocity(), field="source_linear_velocity"
    )
    angular = _finite_vector(
        source_body.get_angular_velocity(), field="source_angular_velocity"
    )
    sleeping = _runtime_is_sleeping(
        simulation_interface,
        stage_id=stage_id,
        source_path=SOURCE_BODY_PATH,
        sdf_path_to_int=sdf_path_to_int,
    )
    return {
        "origin_m": origin.tolist(),
        "orientation_wxyz": quaternion.tolist(),
        "linear_velocity_m_s": linear.tolist(),
        "angular_velocity_rad_s": angular.tolist(),
        "awake": not sleeping,
    }


def _runtime_material_binding(stage: Any, path: str) -> dict[str, Any]:
    from pxr import UsdShade

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise AuditNoGo("material_binding_target_missing", path)
    authored_physics_relationships = []
    for relationship in prim.GetRelationships():
        name = relationship.GetName()
        namespace = name.split(":") if isinstance(name, str) else []
        if namespace[:2] != ["material", "binding"] or "physics" not in namespace[2:]:
            continue
        metadata = getattr(relationship, "GetMetadata", None)
        authored_physics_relationships.append(
            {
                "owner_path": str(prim.GetPath()),
                "name": name,
                "targets": sorted(str(value) for value in relationship.GetTargets()),
                "bind_material_as": (
                    None
                    if not callable(metadata)
                    else _static_usd_native(metadata("bindMaterialAs"))
                ),
            }
        )
    binding = UsdShade.MaterialBindingAPI(prim)
    try:
        result = binding.ComputeBoundMaterial("physics")
    except TypeError:
        result = binding.ComputeBoundMaterial(materialPurpose="physics")
    material = result[0] if isinstance(result, tuple) else result
    relationship = result[1] if isinstance(result, tuple) and len(result) > 1 else None
    material_prim = material.GetPrim() if material else None
    if not material_prim or not material_prim.IsValid():
        if any(item["targets"] for item in authored_physics_relationships):
            raise AuditNoGo("material_binding_unresolved", path)
        return {
            "material_path": None,
            "relationship_name": None,
            "relationship_owner": None,
            "targets": [],
            "physics_binding_state": (
                "authored_empty_default"
                if authored_physics_relationships
                else "no_authored_physics_default"
            ),
            "authored_physics_relationships": authored_physics_relationships,
        }
    return {
        "material_path": str(material_prim.GetPath()),
        "relationship_name": None if relationship is None else relationship.GetName(),
        "relationship_owner": (
            None if relationship is None else str(relationship.GetPrim().GetPath())
        ),
        "targets": (
            [] if relationship is None else sorted(str(value) for value in relationship.GetTargets())
        ),
        "physics_binding_state": "resolved",
        "authored_physics_relationships": authored_physics_relationships,
    }


def _is_static_physics_attribute(name: Any) -> bool:
    normalized = name.lower() if isinstance(name, str) else ""
    return (
        isinstance(name, str)
        and name.startswith(("physics:", "physx:", "physxRigidBody:", "physxCollision:"))
        and name not in DYNAMIC_SOURCE_ATTRIBUTE_NAMES
        and normalized
        not in {
            "physxrigidbody:linearvelocity",
            "physxrigidbody:angularvelocity",
        }
    )


def _runtime_physics_properties(
    stage: Any,
    root_path: str,
    *,
    require_root_binding: bool = False,
    include_xforms: bool = False,
) -> dict[str, Any]:
    from pxr import Usd

    root = stage.GetPrimAtPath(root_path)
    if not root or not root.IsValid():
        raise AuditNoGo("physics_property_root_missing", root_path)
    if include_xforms:
        raise AuditNoGo("static_snapshot_xform_authority_forbidden", root_path)
    attributes = []
    relationships = []
    bindings = []
    applied_schemas = []
    for prim in Usd.PrimRange(root):
        path = str(prim.GetPath())
        schemas = sorted(str(value) for value in prim.GetAppliedSchemas())
        applied_schemas.append({"path": path, "schemas": schemas})
        for attribute in prim.GetAttributes():
            name = attribute.GetName()
            if _is_static_physics_attribute(name):
                attributes.append(
                    {
                        "path": path,
                        "name": name,
                        "value": _static_usd_native(attribute.Get()),
                    }
                )
        for relationship in prim.GetRelationships():
            name = relationship.GetName()
            lower = name.lower()
            if (
                "material:binding" in name
                or "filtered" in lower
                or "filter" in lower
                or "collision" in lower
                or "group" in lower
                or "collection" in lower
                or "mask" in lower
                or "merge" in lower
                or "constraint" in lower
                or "joint" in lower
                or "attachment" in lower
                or "gripper" in lower
                or "body" in lower
                or "owner" in lower
                or "force" in lower
            ):
                relationships.append(
                    {
                        "path": path,
                        "name": name,
                        "targets": sorted(str(value) for value in relationship.GetTargets()),
                    }
                )
        try:
            bindings.append({"path": path, **_runtime_material_binding(stage, path)})
        except AuditNoGo:
            if path == root_path and require_root_binding:
                raise
            bindings.append({"path": path, "material_path": None, "unresolved": True})
    payload = {
        "attributes": sorted(attributes, key=lambda item: (item["path"], item["name"])),
        "relationships": sorted(
            relationships, key=lambda item: (item["path"], item["name"])
        ),
        "material_bindings": sorted(bindings, key=lambda item: item["path"]),
        "applied_schemas": sorted(applied_schemas, key=lambda item: item["path"]),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _runtime_source_robot_property_snapshot(
    stage: Any, identities: Mapping[str, Any]
) -> dict[str, Any]:
    def body_and_colliders(path: str, colliders: Sequence[str]) -> dict[str, Any]:
        return {
            "body": _runtime_physics_properties(
                stage, path, include_xforms=False
            ),
            "colliders": {
                collider: _runtime_physics_properties(
                    stage,
                    collider,
                    require_root_binding=True,
                    include_xforms=False,
                )
                for collider in sorted(colliders)
            },
        }

    return {
        "source": {
            "reset_root": _runtime_physics_properties(
                stage, SOURCE_ROOT_PATH, include_xforms=False
            ),
            **body_and_colliders(
                SOURCE_BODY_PATH,
                identities["source_colliders"],
            ),
        },
        "left_finger": body_and_colliders(
            LEFT_FINGER_BODY_PATH, identities["left_colliders"]
        ),
        "right_finger": body_and_colliders(
            RIGHT_FINGER_BODY_PATH, identities["right_colliders"]
        ),
        "hand": body_and_colliders(
            HAND_BODY_PATH, identities["hand_colliders"]
        ),
    }


def _runtime_cube_snapshot(stage: Any) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    cube = stage.GetPrimAtPath(SUPPORT_PATH)
    if not cube or not cube.IsValid():
        raise AuditNoGo("cube_missing", SUPPORT_PATH)
    has_rigid = cube.HasAPI(UsdPhysics.RigidBodyAPI)
    has_collision = cube.HasAPI(UsdPhysics.CollisionAPI)
    rigid = UsdPhysics.RigidBodyAPI(cube) if has_rigid else None
    collision = UsdPhysics.CollisionAPI(cube) if has_collision else None
    descendants = _runtime_physics_properties(stage, SUPPORT_PATH)
    collider_state = {
        path: _runtime_physics_properties(
            stage, path, require_root_binding=True, include_xforms=False
        )
        for path in _runtime_enabled_colliders(stage, SUPPORT_PATH, require_nonempty=True)
    }
    relationships = descendants["relationships"]
    motion_state = {}
    body_state = {}
    dynamic_descendants = []
    for prim in Usd.PrimRange(cube):
        path = str(prim.GetPath())
        linear = prim.GetAttribute("physics:velocity")
        angular = prim.GetAttribute("physics:angularVelocity")
        linear_value = None if not linear else _runtime_native(linear.Get())
        angular_value = None if not angular else _runtime_native(angular.Get())
        motion_state[path] = {"linear": linear_value, "angular": angular_value}
        has_body = prim.HasAPI(UsdPhysics.RigidBodyAPI)
        body_state[path] = {
            "rigid_body_api": has_body,
            "rigid_body_enabled": None,
            "kinematic_enabled": None,
        }
        if has_body:
            body = UsdPhysics.RigidBodyAPI(prim)
            enabled = body.GetRigidBodyEnabledAttr().Get()
            kinematic = body.GetKinematicEnabledAttr().Get()
            body_state[path] = {
                "rigid_body_api": True,
                "rigid_body_enabled": _runtime_native(enabled),
                "kinematic_enabled": _runtime_native(kinematic),
            }
            if enabled is not False:
                dynamic_descendants.append(path)

    def zero_or_absent(value: Any) -> bool:
        if value is None:
            return True
        try:
            vector = _finite_vector(value, field="cube_velocity")
        except ValueError:
            return False
        return bool(np.allclose(vector, np.zeros(3), rtol=0.0, atol=1.0e-12))

    rigid_enabled = None if rigid is None else _runtime_native(rigid.GetRigidBodyEnabledAttr().Get())
    kinematic_enabled = (
        None if rigid is None else _runtime_native(rigid.GetKinematicEnabledAttr().Get())
    )
    root_linear = None if not cube.GetAttribute("physics:velocity") else _runtime_native(
        cube.GetAttribute("physics:velocity").Get()
    )
    root_angular = None if not cube.GetAttribute("physics:angularVelocity") else _runtime_native(
        cube.GetAttribute("physics:angularVelocity").Get()
    )
    return {
        "world_matrix": _runtime_row_matrix(stage, SUPPORT_PATH).tolist(),
        "rigid_body_enabled": rigid_enabled,
        "kinematic_enabled": kinematic_enabled,
        "velocities": {
            "linear": root_linear,
            "angular": root_angular,
        },
        "force_constraint_membership": {
            f"{item['path']}:{item['name']}": item["targets"]
            for item in relationships
            if any(token in item["name"].lower() for token in ("force", "joint", "constraint"))
        },
        "collision_properties": {
            "enabled": (
                None if collision is None else _runtime_native(collision.GetCollisionEnabledAttr().Get())
            ),
            "attributes": descendants["attributes"],
        },
        "material_bindings": descendants["material_bindings"],
        "group_filter_relationships": {
            f"{item['path']}:{item['name']}": item["targets"]
            for item in relationships
            if any(
                token in item["name"].lower()
                for token in ("group", "filter", "collision", "collection", "mask", "merge")
            )
        },
        "descendant_physics_state": {
            "colliders": collider_state,
            "material_bindings": descendants["material_bindings"],
            "relationships": relationships,
            "applied_schemas": descendants["applied_schemas"],
            "body_state": body_state,
            "motion_state": motion_state,
        },
        "support_contract": {
            "static": not dynamic_descendants,
            "nonkinematic": kinematic_enabled is not True,
            "nonmoving": all(
                zero_or_absent(values[axis])
                for values in motion_state.values()
                for axis in ("linear", "angular")
            ),
            "dynamic_descendant_paths": sorted(dynamic_descendants),
        },
    }


def _runtime_static_support_snapshot(stage: Any, support_path: str) -> dict[str, Any]:
    """Capture the exact leaf collider and its ancestor-body chain for v3."""

    from pxr import Usd, UsdPhysics

    root = stage.GetPrimAtPath(support_path)
    if not root or not root.IsValid():
        raise AuditNoGo("support_collider_missing", support_path)
    collision = (
        UsdPhysics.CollisionAPI(root) if root.HasAPI(UsdPhysics.CollisionAPI) else None
    )
    if collision is None:
        raise AuditNoGo("support_collider_collision_missing", support_path)
    properties = _runtime_physics_properties(
        stage, support_path, require_root_binding=True, include_xforms=False
    )
    has_rigid = root.HasAPI(UsdPhysics.RigidBodyAPI)
    rigid = UsdPhysics.RigidBodyAPI(root) if has_rigid else None
    rigid_enabled = None if rigid is None else _runtime_native(rigid.GetRigidBodyEnabledAttr().Get())
    kinematic_enabled = (
        None if rigid is None else _runtime_native(rigid.GetKinematicEnabledAttr().Get())
    )
    root_linear = None if not root.GetAttribute("physics:velocity") else _runtime_native(
        root.GetAttribute("physics:velocity").Get()
    )
    root_angular = None if not root.GetAttribute("physics:angularVelocity") else _runtime_native(
        root.GetAttribute("physics:angularVelocity").Get()
    )
    body_state = {
        support_path: {
            "rigid_body_api": has_rigid,
            "rigid_body_enabled": rigid_enabled,
            "kinematic_enabled": kinematic_enabled,
        }
    }
    ancestor_body_state = {}
    ancestor = root.GetParent()
    while ancestor and ancestor.IsValid():
        path = str(ancestor.GetPath())
        has_body = ancestor.HasAPI(UsdPhysics.RigidBodyAPI)
        body = UsdPhysics.RigidBodyAPI(ancestor) if has_body else None
        ancestor_body_state[path] = {
            "rigid_body_api": has_body,
            "rigid_body_enabled": (
                None if body is None else _runtime_native(body.GetRigidBodyEnabledAttr().Get())
            ),
            "kinematic_enabled": (
                None if body is None else _runtime_native(body.GetKinematicEnabledAttr().Get())
            ),
        }
        ancestor = ancestor.GetParent()

    def zero_or_absent(value: Any) -> bool:
        if value is None:
            return True
        try:
            vector = _finite_vector(value, field="static_support_velocity")
        except ValueError:
            return False
        return bool(np.allclose(vector, np.zeros(3), rtol=0.0, atol=1.0e-12))

    relationships = properties["relationships"]
    return {
        "support_path": support_path,
        "world_matrix": _runtime_row_matrix(stage, support_path).tolist(),
        "rigid_body_enabled": rigid_enabled,
        "kinematic_enabled": kinematic_enabled,
        "velocities": {"linear": root_linear, "angular": root_angular},
        "force_constraint_membership": {
            f"{item['path']}:{item['name']}": item["targets"]
            for item in relationships
            if any(token in item["name"].lower() for token in ("force", "joint", "constraint"))
        },
        "collision_properties": {
            "enabled": _runtime_native(collision.GetCollisionEnabledAttr().Get()),
            "attributes": properties["attributes"],
        },
        "material_bindings": properties["material_bindings"],
        "group_filter_relationships": {
            f"{item['path']}:{item['name']}": item["targets"]
            for item in relationships
            if any(
                token in item["name"].lower()
                for token in ("group", "filter", "collision", "collection", "mask", "merge")
            )
        },
        "descendant_physics_state": {
            "colliders": {
                support_path: _runtime_physics_properties(
                    stage,
                    support_path,
                    require_root_binding=True,
                    include_xforms=False,
                )
            },
            "material_bindings": properties["material_bindings"],
            "relationships": relationships,
            "applied_schemas": properties["applied_schemas"],
            "body_state": body_state,
            "motion_state": {
                support_path: {"linear": root_linear, "angular": root_angular}
            },
        },
        "support_contract": {
            "static": rigid_enabled is not True,
            "nonkinematic": kinematic_enabled is not True,
            "nonmoving": zero_or_absent(root_linear) and zero_or_absent(root_angular),
            "dynamic_descendant_paths": [] if rigid_enabled is not True else [support_path],
        },
        "ancestor_body_state": ancestor_body_state,
    }


def _runtime_static_support_snapshots(
    stage: Any, support_paths: Sequence[str]
) -> dict[str, dict[str, Any]]:
    if list(support_paths) != [SUPPORT_PATH, TABLE_SUPPORT_PATH]:
        raise AuditNoGo("static_support_paths_invalid", json.dumps(list(support_paths)))
    return {
        path: _runtime_static_support_snapshot(stage, path)
        for path in support_paths
    }


def _runtime_relation_inventory(stage: Any) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    relations = []
    relationship_topology = []
    applied_schemas = []
    for prim in Usd.PrimRange.Stage(stage):
        path = str(prim.GetPath())
        is_joint = prim.IsA(UsdPhysics.Joint)
        is_group = prim.IsA(UsdPhysics.CollisionGroup)
        schemas = sorted(str(value) for value in prim.GetAppliedSchemas())
        applied_schemas.append({"path": path, "schemas": schemas})
        for relationship in prim.GetRelationships():
            name = relationship.GetName()
            lower = name.lower()
            targets = sorted(str(value) for value in relationship.GetTargets())
            relationship_topology.append(
                {
                    "owner_path": path,
                    "relationship": name,
                    "targets": targets,
                    "applied_schemas": schemas,
                }
            )
            if name.startswith("material:binding") or name == "physics:simulationOwner":
                continue
            # USD joints use empty proxy/body slots for normal articulation
            # topology, including Franka's world-anchored root joint. Keep the
            # slots in relationship_topology, but do not invent graph edges.
            if is_joint and not targets and name in {
                "proxyPrim",
                "physics:body0",
                "physics:body1",
            }:
                continue
            candidate = is_joint or is_group or bool(targets)
            if not candidate:
                continue
            endpoints = [path, *targets]
            if "filtered" in lower:
                kind = "filtered_pairs"
            elif "filter" in lower:
                kind = "filter"
            elif "mask" in lower:
                kind = "mask"
            elif "merge" in lower:
                kind = "merge_group"
            elif "collection" in lower:
                kind = "collection"
            elif is_group or "group" in lower:
                kind = "collision_group"
            elif "force" in lower:
                kind = "force_field_membership"
            elif "attachment" in lower or "gripper" in lower:
                kind = "attachment"
            elif "d6" in prim.GetTypeName().lower():
                kind = "d6"
            elif "fixed" in prim.GetTypeName().lower():
                kind = "fixed"
            elif is_joint:
                kind = "joint"
            else:
                kind = "generic"
            relations.append(
                {
                    "kind": kind,
                    "owner_path": path,
                    "relationship": name,
                    "endpoints": endpoints,
                    "identity_valid": bool(targets),
                }
            )
    schema_by_path = {record["path"]: record["schemas"] for record in applied_schemas}
    resolved_relations = []
    for relation in relations:
        endpoints = relation["endpoints"]
        owner = relation["owner_path"]
        endpoint_schemas = {
            endpoint: schema_by_path.get(endpoint) for endpoint in endpoints
        }
        resolved_relations.append(
            {
                **relation,
                "endpoint_partitions": {
                    endpoint: sorted(_endpoint_partitions(endpoint)) for endpoint in endpoints
                },
                "owner_applied_schemas": schema_by_path.get(owner),
                "endpoint_applied_schemas": endpoint_schemas,
                "schema_resolution_complete": bool(
                    schema_by_path.get(owner) is not None
                    and all(value is not None for value in endpoint_schemas.values())
                ),
            }
        )
    payload = {
        "relations": sorted(
            resolved_relations, key=lambda item: (item["owner_path"], item["relationship"])
        ),
        "relationship_topology": sorted(
            relationship_topology,
            key=lambda item: (item["owner_path"], item["relationship"]),
        ),
        "applied_schemas": sorted(applied_schemas, key=lambda item: item["path"]),
        "applied_schema_resolution_complete": all(
            relation["schema_resolution_complete"] for relation in resolved_relations
        ),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _relation_inventory_sha256(inventory: Any) -> str:
    if not isinstance(inventory, Mapping) or set(inventory) != (
        _RELATION_INVENTORY_PAYLOAD_FIELDS | {"sha256"}
    ):
        raise ValueError("relation_inventory_fingerprint_invalid")
    payload = {name: inventory[name] for name in _RELATION_INVENTORY_PAYLOAD_FIELDS}
    digest = _canonical_json_sha256(payload)
    if not _is_sha256(inventory.get("sha256")) or inventory["sha256"] != digest:
        raise ValueError("relation_inventory_fingerprint_invalid")
    return digest


def _relation_boundary_fingerprint(inventory: Mapping[str, Any]) -> dict[str, str]:
    return {
        "schema": BOUNDARY_RELATION_FINGERPRINT_SCHEMA,
        "sha256": _relation_inventory_sha256(inventory),
    }


def _relation_boundary_fingerprint_sha256(fingerprint: Any) -> str:
    if (
        not isinstance(fingerprint, Mapping)
        or set(fingerprint) != {"schema", "sha256"}
        or fingerprint.get("schema") != BOUNDARY_RELATION_FINGERPRINT_SCHEMA
        or not _is_sha256(fingerprint.get("sha256"))
    ):
        raise ValueError("relation_boundary_fingerprint_invalid")
    return str(fingerprint["sha256"])


def evaluate_relation_boundary_fingerprints(
    baseline_inventory: Any,
    fingerprints: Sequence[Any],
) -> dict[str, Any]:
    audit_failures: list[str] = []
    expected_sha256 = None
    try:
        expected_sha256 = _relation_inventory_sha256(baseline_inventory)
    except ValueError:
        audit_failures.append("relation_baseline_fingerprint_invalid")
    if (
        not isinstance(fingerprints, Sequence)
        or isinstance(fingerprints, (str, bytes, bytearray))
    ):
        audit_failures.append("relation_boundary_fingerprint_invalid")
        fingerprints = []
    for fingerprint in fingerprints:
        try:
            digest = _relation_boundary_fingerprint_sha256(fingerprint)
        except ValueError:
            audit_failures.append("relation_boundary_fingerprint_invalid")
            continue
        if expected_sha256 is not None and digest != expected_sha256:
            audit_failures.append("relation_inventory_changed")
    audit_failures = sorted(set(audit_failures))
    return {
        "audit_valid": not audit_failures,
        "audit_failures": audit_failures,
        "expected_sha256": expected_sha256,
    }


def _mutation_event_parts(event: Any) -> tuple[str, str, list[str]]:
    if not isinstance(event, Mapping):
        raise ValueError("mutation_ledger_event_invalid")
    path = event.get("path")
    kind = event.get("kind")
    fields = event.get("fields")
    if (
        not isinstance(path, str)
        or not path
        or kind not in {"info", "resync"}
        or not isinstance(fields, Sequence)
        or isinstance(fields, (str, bytes, bytearray))
        or any(not isinstance(field, str) or not field for field in fields)
    ):
        raise ValueError("mutation_ledger_event_invalid")
    return path, kind, list(fields)


def _initial_root_placement_event(event: Mapping[str, Any]) -> bool:
    try:
        path, kind, fields = _mutation_event_parts(event)
    except ValueError:
        return False
    if kind != "info":
        return False
    if path == SOURCE_ROOT_PATH:
        return all(field.startswith("xformOp:") or field == "xformOpOrder" for field in fields)
    if path.startswith(SOURCE_ROOT_PATH + ".xformOp:"):
        return fields == ["default"]
    return False


def _is_report_metadata_setup_event(event: Mapping[str, Any]) -> bool:
    try:
        path, kind, fields = _mutation_event_parts(event)
    except ValueError:
        return False
    if path in REPORT_BODY_PATHS:
        return kind == "info" and fields == ["apiSchemas"]
    for body_path in REPORT_BODY_PATHS:
        threshold = f"{body_path}.physxContactReport:threshold"
        report_pairs = f"{body_path}.physxContactReport:reportPairs"
        if path == threshold:
            return (kind == "resync" and not fields) or (
                kind == "info" and fields == ["default"]
            )
        if path == report_pairs:
            return (kind == "resync" and not fields) or (
                kind == "info" and fields == ["targetPaths"]
            )
    return False


def _is_pre_reset_dynamic_state_event(event: Mapping[str, Any]) -> bool:
    try:
        path, kind, fields = _mutation_event_parts(event)
    except ValueError:
        return False
    if kind != "info" or _path_partition(path) not in {"source", "robot"}:
        return False
    values = fields
    if "." in path.rsplit("/", 1)[-1]:
        owner, property_name = path.rsplit(".", 1)
        if fields != ["default"]:
            return False
        path = owner
        values = [property_name]
    return bool(values) and all(
        value.startswith("xformOp:") or value in _DYNAMIC_MUTATION_ATTRIBUTE_NAMES
        for value in values
    )


def _is_allowed_pre_reset_setup_event(event: Mapping[str, Any]) -> bool:
    try:
        path, kind, fields = _mutation_event_parts(event)
    except ValueError:
        return False
    if _initial_root_placement_event(event) or _is_report_metadata_setup_event(event):
        return True
    if _is_pre_reset_dynamic_state_event(event):
        return True
    if _path_partition(path) in {"source", "robot"} and not fields:
        return kind in {"info", "resync"}
    if (
        kind == "resync"
        and not fields
        and (
            path == SOURCE_ROOT_PATH
            or path.startswith(SOURCE_ROOT_PATH + ".xformOp:")
        )
    ):
        return True
    return "camera" in path.lower()


def _mutation_dynamic_owner(path: str, body_paths: Sequence[str]) -> str | None:
    for body_path in sorted(body_paths, key=len, reverse=True):
        if path == body_path or path.startswith(body_path + "/") or path.startswith(body_path + "."):
            return body_path
    return None


def _is_dynamic_world_step_mutation(
    event: Mapping[str, Any], *, known_dynamic_body_paths: Sequence[str]
) -> bool:
    path, kind, fields = _mutation_event_parts(event)
    if kind != "info":
        return False
    owner = _mutation_dynamic_owner(path, known_dynamic_body_paths)
    if owner is None:
        return False
    properties = list(fields)
    if path.startswith(owner + "."):
        property_name = path[len(owner) + 1 :]
        if fields != ["default"]:
            return False
        properties = [property_name]
    return bool(properties) and all(
        value.startswith("xformOp:") or value in _DYNAMIC_MUTATION_ATTRIBUTE_NAMES
        for value in properties
    )


def evaluate_runtime_mutation_ledger(
    segments: Sequence[Mapping[str, Any]],
    *,
    known_dynamic_body_paths: Sequence[str],
    support_paths: Sequence[str] = (SUPPORT_PATH,),
) -> dict[str, Any]:
    """Validate every observed USD notice without mistaking PhysX writeback for authoring."""

    audit_failures: list[str] = []
    normalized_segments: list[dict[str, Any]] = []
    forbidden_event_count = 0
    try:
        if (
            not isinstance(segments, Sequence)
            or isinstance(segments, (str, bytes, bytearray))
            or not isinstance(known_dynamic_body_paths, Sequence)
            or isinstance(known_dynamic_body_paths, (str, bytes, bytearray))
            or not known_dynamic_body_paths
            or any(
                not isinstance(path, str) or not path
                for path in known_dynamic_body_paths
            )
            or len(set(known_dynamic_body_paths)) != len(known_dynamic_body_paths)
            or SOURCE_BODY_PATH not in known_dynamic_body_paths
            or not isinstance(support_paths, Sequence)
            or isinstance(support_paths, (str, bytes, bytearray))
            or not support_paths
            or any(not isinstance(path, str) or not path for path in support_paths)
            or len(set(support_paths)) != len(support_paths)
        ):
            raise ValueError("mutation_ledger_authority_invalid")
        for segment in segments:
            if not isinstance(segment, Mapping):
                raise ValueError("mutation_ledger_segment_invalid")
            phase = segment.get("phase")
            events = segment.get("events")
            if (
                phase not in MUTATION_PHASES
                or not isinstance(events, Sequence)
                or isinstance(events, (str, bytes, bytearray))
            ):
                raise ValueError("mutation_ledger_segment_invalid")
            normalized_events = []
            for event in events:
                path, kind, fields = _mutation_event_parts(event)
                normalized_events.append(
                    {
                        "path": path,
                        "kind": kind,
                        "fields": fields,
                        **(
                            {"notice_index": event["notice_index"]}
                            if type(event.get("notice_index")) is int
                            else {}
                        ),
                    }
                )
                event_forbidden = False
                partition = _path_partition(path, support_paths=support_paths)
                if phase == "pre_reset":
                    # The zero-mutation epoch begins after task.reset(); the
                    # sealed before/after snapshots bind its setup outcome.
                    continue
                if _is_semantic_relation_mutation(
                    {"path": path, "kind": kind, "fields": fields}
                ):
                    audit_failures.append("external_relation_mutation_detected")
                    event_forbidden = True
                if phase == "pre_reset":
                    if partition == "source" and not _initial_root_placement_event(
                        {"path": path, "kind": kind, "fields": fields}
                    ):
                        audit_failures.append("pre_reset_source_robot_mutation_notice")
                        event_forbidden = True
                    elif partition in {"robot", "support"}:
                        audit_failures.append("pre_reset_source_robot_mutation_notice")
                        event_forbidden = True
                elif phase == "world_step":
                    if partition == "support":
                        audit_failures.append("cube_mutation_notice")
                        event_forbidden = True
                    elif partition in {"source", "robot"}:
                        if _mutation_dynamic_owner(path, known_dynamic_body_paths) is None:
                            audit_failures.append("world_step_dynamic_body_unknown")
                            event_forbidden = True
                        elif not _is_dynamic_world_step_mutation(
                            {"path": path, "kind": kind, "fields": fields},
                            known_dynamic_body_paths=known_dynamic_body_paths,
                        ):
                            audit_failures.append("world_step_static_or_semantic_mutation")
                            event_forbidden = True
                elif partition == "support":
                    audit_failures.append("cube_mutation_notice")
                    event_forbidden = True
                elif partition in {"source", "robot"}:
                    audit_failures.append("source_robot_mutation_outside_world_step")
                    event_forbidden = True
                if event_forbidden:
                    forbidden_event_count += 1
            normalized_segments.append({"phase": phase, "events": normalized_events})
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {
        "audit_valid": not audit_failures,
        "audit_failures": audit_failures,
        "segments": normalized_segments,
        "forbidden_event_count": forbidden_event_count,
    }


class _RuntimeMutationNotice:
    def __init__(self, stage: Any) -> None:
        from pxr import Tf, Usd

        self._stage = stage
        self._events: list[dict[str, Any]] = []
        self._segments: list[dict[str, Any]] = []
        self._error: str | None = None
        self._listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_notice, stage)

    def _on_notice(self, notice: Any, _sender: Any) -> None:
        try:
            paths = []
            for path in notice.GetResyncedPaths():
                paths.append((str(path), "resync", []))
            for path in notice.GetChangedInfoOnlyPaths():
                paths.append(
                    (
                        str(path),
                        "info",
                        sorted(str(field) for field in notice.GetChangedFields(path)),
                    )
                )
            for path, kind, fields in paths:
                self._events.append(
                    {
                        "notice_index": len(self._events),
                        "path": path,
                        "kind": kind,
                        "fields": fields,
                    }
                )
        except BaseException as exc:
            self._error = f"{type(exc).__name__}:{exc}"

    def mark(self) -> int:
        return len(self._events)

    def events_since(self, marker: int) -> list[dict[str, Any]]:
        if type(marker) is not int or marker < 0 or marker > len(self._events):
            raise AuditNoGo("mutation_notice_marker_invalid", str(marker))
        if self._error is not None:
            raise AuditNoGo("mutation_notice_error", self._error)
        return copy.deepcopy(self._events[marker:])

    def all_events(self) -> list[dict[str, Any]]:
        return self.events_since(0)

    def capture_since(self, marker: int, *, phase: str) -> dict[str, Any]:
        if phase not in MUTATION_PHASES:
            raise AuditNoGo("mutation_notice_phase_invalid", str(phase))
        segment = {"phase": phase, "events": self.events_since(marker)}
        self._segments.append(copy.deepcopy(segment))
        return segment

    def ledger(self) -> list[dict[str, Any]]:
        if self._error is not None:
            raise AuditNoGo("mutation_notice_error", self._error)
        return copy.deepcopy(self._segments)

    def close(self) -> None:
        listener = self._listener
        self._listener = None
        if listener is not None:
            listener.Revoke()


class _RuntimeWriteAudit:
    def __init__(self) -> None:
        self.coverage = {name: False for name in REQUIRED_WRITER_AUDIT_SURFACES}
        self.surfaces = {
            name: {
                "reachable": False,
                "available": False,
                "audited": False,
                "status": "unobserved",
                "detail": None,
            }
            for name in REQUIRED_WRITER_AUDIT_SURFACES
        }
        self.counts = {name: 0 for name in WRITER_AUDIT_COUNT_FIELDS}
        self.reset_root_write_count = 0
        self.zero_write_epoch_opened = False
        self._patches: list[tuple[Any, str, Any]] = []
        self._static_production_closure: dict[str, Any] = {
            "audit_valid": False,
            "forbidden_calls": [],
            "required_runtime_surfaces": [],
            "not_applicable_runtime_surfaces": [],
        }

    @staticmethod
    def _call_path(args: Sequence[Any], kwargs: Mapping[str, Any]) -> str | None:
        for name in ("object_path", "prim_path", "path"):
            value = kwargs.get(name)
            if isinstance(value, str):
                return value
        for value in args:
            if isinstance(value, str) and value.startswith("/"):
                return value
        return None

    def set_static_production_closure(self, value: Mapping[str, Any]) -> None:
        if not isinstance(value, Mapping):
            raise ValueError("native_unbound_static_closure_mapping_required")
        self._static_production_closure = copy.deepcopy(dict(value))

    def _set_surface(
        self,
        surface: str,
        *,
        reachable: bool,
        available: bool,
        audited: bool,
        status: str,
        detail: str | None = None,
    ) -> None:
        if surface not in self.surfaces:
            raise ValueError("native_unbound_writer_patch_contract_invalid")
        self.surfaces[surface] = {
            "reachable": reachable,
            "available": available,
            "audited": audited,
            "status": status,
            "detail": detail,
        }
        self.coverage[surface] = audited

    def audit_callable(
        self,
        obj: Any,
        method_name: str,
        *,
        surface: str,
        count: str | Sequence[str],
        source_scoped: bool,
        required: bool,
        source_path_resolver: Any = None,
    ) -> bool:
        count_names = (count,) if isinstance(count, str) else tuple(count)
        if (
            surface not in self.surfaces
            or not count_names
            or any(name not in self.counts for name in count_names)
        ):
            raise ValueError("native_unbound_writer_patch_contract_invalid")
        method = getattr(obj, method_name, None) if obj is not None else None
        if not callable(method):
            self._set_surface(
                surface,
                reachable=required,
                available=False,
                audited=False,
                status="unavailable" if required else "not_applicable",
                detail=(
                    f"{type(obj).__name__ if obj is not None else 'None'}.{method_name}"
                    if required
                    else "static_production_closure_proves_unreachable:"
                    f"{type(obj).__name__ if obj is not None else 'None'}.{method_name}"
                ),
            )
            return False

        def audited(*args: Any, **kwargs: Any) -> Any:
            path = (
                source_path_resolver(args, kwargs)
                if callable(source_path_resolver)
                else self._call_path(args, kwargs)
            )
            relevant = not source_scoped or (
                isinstance(path, str) and _path_partition(path) == "source"
            )
            if relevant:
                if self.zero_write_epoch_opened:
                    for name in count_names:
                        self.counts[name] += 1
                elif path == SOURCE_ROOT_PATH:
                    self.reset_root_write_count += 1
            return method(*args, **kwargs)

        try:
            setattr(obj, method_name, audited)
        except BaseException as exc:
            self._set_surface(
                surface,
                reachable=required,
                available=True,
                audited=False,
                status="unpatchable",
                detail=f"{type(obj).__name__}.{method_name}:{type(exc).__name__}",
            )
            return False
        self._patches.append((obj, method_name, method))
        self._set_surface(
            surface,
            reachable=required,
            available=True,
            audited=True,
            status="audited",
        )
        return True

    def patch_required(
        self,
        obj: Any,
        method_name: str,
        *,
        surface: str,
        count: str | Sequence[str],
        source_scoped: bool,
    ) -> None:
        if not self.audit_callable(
            obj,
            method_name,
            surface=surface,
            count=count,
            source_scoped=source_scoped,
            required=True,
        ):
            raise AuditNoGo(
                "writer_audit_surface_unavailable",
                f"{type(obj).__name__ if obj is not None else 'None'}.{method_name}",
            )

    def mark_covered(self, surface: str, *, reachable: bool = True) -> None:
        if surface not in self.surfaces:
            raise ValueError("native_unbound_writer_patch_contract_invalid")
        self._set_surface(
            surface,
            reachable=reachable,
            available=True,
            audited=True,
            status="audited",
        )

    def summarize_surface(self, surface: str, components: Sequence[str]) -> None:
        if surface not in self.surfaces or not components:
            raise ValueError("native_unbound_writer_patch_contract_invalid")
        values = [self.surfaces[name] for name in components]
        direct = self.surfaces[surface]
        direct_values = [] if direct["status"] == "unobserved" else [direct]
        summarized = [*direct_values, *values]
        reachable = direct["reachable"] or any(value["reachable"] for value in values)
        available_values = [value for value in summarized if value["available"]]
        available = bool(available_values)
        audited = bool(available_values) and all(
            value["audited"] for value in available_values
        )
        self._set_surface(
            surface,
            reachable=reachable,
            available=available,
            audited=audited,
            status=(
                "audited"
                if audited
                else "not_applicable"
                if not available
                and all(value["status"] == "not_applicable" for value in summarized)
                else "unavailable"
                if not available
                else "unpatchable"
            ),
        )

    def activate_mutation_notice(self) -> None:
        self.mark_covered("usd_mutation_notice")

    def open_epoch(self) -> None:
        self.zero_write_epoch_opened = True

    def close(self) -> None:
        for obj, method_name, original in reversed(self._patches):
            try:
                setattr(obj, method_name, original)
            except BaseException:
                pass
        self._patches.clear()

    def report(
        self,
        *,
        mutation_notice_active: bool,
        mutation_events: Sequence[Mapping[str, Any]] = (),
        snapshot_phase: str = "measurement",
    ) -> dict[str, Any]:
        if snapshot_phase not in {"measurement", "after_controller_close"}:
            raise AuditNoGo("writer_audit_snapshot_phase_invalid", str(snapshot_phase))
        counts = dict(self.counts)
        if (
            not isinstance(mutation_events, Sequence)
            or isinstance(mutation_events, (str, bytes, bytearray))
        ):
            raise AuditNoGo("writer_audit_mutation_events_invalid", type(mutation_events).__name__)
        for event in mutation_events:
            if not isinstance(event, Mapping) or not isinstance(event.get("path"), str):
                raise AuditNoGo("writer_audit_mutation_events_invalid", str(event))
        return {
            "coverage": dict(self.coverage),
            "surfaces": copy.deepcopy(self.surfaces),
            "static_production_closure": copy.deepcopy(self._static_production_closure),
            "counts": counts,
            "reset_root_write_count": self.reset_root_write_count,
            "zero_write_epoch_opened": self.zero_write_epoch_opened,
            "mutation_notice_active": mutation_notice_active,
            "writer_audit_snapshot_phase": snapshot_phase,
        }


def _sdf_list_op_items(value: Any) -> tuple[list[str], str]:
    if value is None:
        return [], "explicit"
    for name, label in (
        ("explicitItems", "explicit"),
        ("prependedItems", "prepended"),
        ("appendedItems", "appended"),
        ("addedItems", "added"),
        ("deletedItems", "deleted"),
    ):
        items = getattr(value, name, None)
        if items:
            return [str(item) for item in items], label
    return [], "explicit"


def _runtime_layer_catalog(layer: Any) -> dict[str, Any]:
    records = []

    def visit(prim_spec: Any) -> None:
        schemas, _schema_op = _sdf_list_op_items(prim_spec.GetInfo("apiSchemas"))
        metadata = {}
        for key in prim_spec.ListInfoKeys():
            name = str(key)
            if name in {"apiSchemas", "specifier", "typeName"}:
                continue
            metadata[name] = _static_usd_native(prim_spec.GetInfo(key))
        properties = []
        for property_spec in prim_spec.properties:
            name = property_spec.name
            if name == "physxContactReport:threshold":
                properties.append(
                    {
                        "name": name,
                        "value": _finite_scalar(
                            property_spec.GetInfo("default"), field="report_threshold"
                        ),
                    }
                )
            elif name == "physxContactReport:reportPairs":
                targets, list_op = _sdf_list_op_items(
                    property_spec.GetInfo("targetPaths")
                )
                properties.append(
                    {"name": name, "targets": targets, "list_op": list_op}
                )
            else:
                properties.append(
                    {
                        "name": name,
                        "value": _static_usd_native(property_spec.GetInfo("default")),
                    }
                )
        records.append(
            {
                "path": str(prim_spec.path),
                "api_schemas": sorted(schemas),
                "properties": sorted(properties, key=lambda item: item["name"]),
                "metadata": metadata,
            }
        )
        for child in prim_spec.nameChildren:
            visit(child)

    for root in layer.rootPrims:
        visit(root)
    payload = {"records": sorted(records, key=lambda item: item["path"])}
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _runtime_install_report_layer(
    stage: Any,
    *,
    simulation_interface: Any,
    world: Any,
) -> dict[str, Any]:
    from pxr import PhysxSchema, Sdf, Usd

    session = stage.GetSessionLayer()
    if session is None:
        raise AuditNoGo("report_session_layer_unavailable", "stage session layer missing")
    before_counter = _runtime_world_counter(world)
    previous_target = stage.GetEditTarget()
    previous_identifier = previous_target.GetLayer().identifier
    previous_sublayers = list(session.subLayerPaths)
    layer = Sdf.Layer.CreateAnonymous("native_expert_empty_beaker_report.usda")
    if layer is None:
        raise AuditNoGo("report_session_sublayer_unavailable", "CreateAnonymous returned None")
    try:
        session.subLayerPaths.insert(0, layer.identifier)
        stage.SetEditTarget(Usd.EditTarget(layer))
        for path in REPORT_BODY_PATHS:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                raise AuditNoGo("report_body_missing", path)
            api = PhysxSchema.PhysxContactReportAPI.Apply(prim)
            api.CreateThresholdAttr().Set(0.0)
            api.CreateReportPairsRel().SetTargets([])
            threshold = api.GetThresholdAttr().Get()
            pairs = list(api.GetReportPairsRel().GetTargets())
            if threshold != 0.0 or pairs:
                raise AuditNoGo("report_api_readback_mismatch", path)
    finally:
        stage.SetEditTarget(previous_target)
    if stage.GetEditTarget().GetLayer().identifier != previous_identifier:
        raise AuditNoGo("report_edit_target_restore_failed", previous_identifier)
    if list(session.subLayerPaths) != [layer.identifier, *previous_sublayers]:
        raise AuditNoGo("report_sublayer_order_invalid", layer.identifier)
    flush = getattr(simulation_interface, "flush_changes", None)
    if not callable(flush):
        raise AuditNoGo("report_flush_authority_missing", "flush_changes missing")
    flush()
    after_counter = _runtime_world_counter(world)
    if after_counter != before_counter:
        raise AuditNoGo(
            "report_observer_advanced_physics",
            f"before={before_counter}:after={after_counter}",
        )
    catalog = _runtime_layer_catalog(layer)
    validation = validate_report_only_layer_catalog(catalog)
    if not validation["audit_valid"]:
        raise AuditNoGo(
            "report_layer_catalog_invalid",
            json.dumps(validation["audit_failures"], sort_keys=True),
            evidence=catalog,
        )
    return {
        "layer": layer,
        "layer_identifier": layer.identifier,
        "catalog": catalog,
        "validation": validation,
        "before_world_index": before_counter,
        "after_world_index": after_counter,
    }


class _RuntimeFullContactReporter:
    _event_names = {
        "CONTACT_FOUND": "FOUND",
        "CONTACT_PERSIST": "PERSIST",
        "CONTACT_LOST": "LOST",
    }
    _event_values = {0: "FOUND", 1: "LOST", 2: "PERSIST"}

    def __init__(self, *, simulation_interface: Any, resolve_path: Any) -> None:
        reader = getattr(simulation_interface, "get_full_contact_report", None)
        if not callable(reader):
            raise AuditNoGo("full_contact_report_unavailable", "method missing")
        if not callable(resolve_path):
            raise AuditNoGo("contact_path_resolver_unavailable", "resolver missing")
        self._reader = reader
        self._resolve_path = resolve_path
        self._read_count = 0

    def _path(self, value: Any, *, field: str) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise AuditNoGo(
                "contact_path_identifier_invalid",
                f"{field}:{value}",
                evidence={"field": field, "identifier": str(value)},
            )
        identifier = int(value)
        try:
            path = str(self._resolve_path(identifier))
        except BaseException as exc:
            raise AuditNoGo(
                "contact_path_resolution_failed",
                f"{field}:{identifier}",
                evidence={"field": field, "identifier": identifier},
            ) from exc
        if not path:
            raise AuditNoGo(
                "contact_path_resolution_failed",
                f"{field}:{identifier}",
                evidence={"field": field, "identifier": identifier},
            )
        return path

    def _material_path(self, value: Any, *, field: str) -> str:
        if (
            not isinstance(value, bool)
            and isinstance(value, (int, np.integer))
            and int(value) == 0
        ):
            return CONTACT_MATERIAL_IDENTIFIER_ZERO
        return self._path(value, field=field)

    @classmethod
    def _event(cls, value: Any) -> str:
        name = getattr(value, "name", None)
        if name in cls._event_names:
            return cls._event_names[name]
        try:
            return cls._event_values[int(value)]
        except (KeyError, TypeError, ValueError) as exc:
            raise AuditNoGo("contact_event_semantics_unsupported", str(value)) from exc

    @staticmethod
    def _vector(value: Any, field: str) -> list[float]:
        try:
            result = [float(item) for item in value]
        except (TypeError, ValueError) as exc:
            raise AuditNoGo("contact_vector_invalid", field) from exc
        if len(result) != 3 or not all(math.isfinite(item) for item in result):
            raise AuditNoGo("contact_vector_invalid", field)
        return result

    def sample(self, *, physics_index: int) -> dict[str, Any]:
        raw = self._reader()
        read_index = self._read_count
        self._read_count += 1
        if not isinstance(raw, tuple) or len(raw) != 3:
            raise AuditNoGo("full_contact_report_tuple_invalid", type(raw).__name__)
        raw_headers, raw_points, raw_anchors = raw
        headers = []
        points = []
        anchors = []
        try:
            for value in raw_headers:
                headers.append(
                    {
                        "type": self._event(value.type),
                        "stage_id": int(value.stage_id),
                        "actor0": self._path(value.actor0, field="actor0"),
                        "actor1": self._path(value.actor1, field="actor1"),
                        "collider0": self._path(value.collider0, field="collider0"),
                        "collider1": self._path(value.collider1, field="collider1"),
                        "proto_index0": int(value.proto_index0),
                        "proto_index1": int(value.proto_index1),
                        "contact_data_offset": int(value.contact_data_offset),
                        "num_contact_data": int(value.num_contact_data),
                        "friction_anchors_offset": int(value.friction_anchors_offset),
                        "num_friction_anchors_data": int(value.num_friction_anchors_data),
                    }
                )
            for value in raw_points:
                points.append(
                    {
                        "position": self._vector(value.position, "position"),
                        "normal": self._vector(value.normal, "normal"),
                        "impulse": self._vector(value.impulse, "impulse"),
                        "separation": float(value.separation),
                        "face_index0": int(value.face_index0),
                        "face_index1": int(value.face_index1),
                        "material0": self._material_path(value.material0, field="material0"),
                        "material1": self._material_path(value.material1, field="material1"),
                    }
                )
            for value in raw_anchors:
                anchors.append(
                    {
                        "position": self._vector(value.position, "friction_position"),
                        "impulse": self._vector(value.impulse, "friction_impulse"),
                    }
                )
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise AuditNoGo("contact_record_semantics_unsupported", str(exc)) from exc
        return {
            "headers": headers,
            "contact_data": points,
            "friction_anchors": anchors,
            "immediate_read_index": read_index,
            "immediate_read_count": self._read_count,
            "physics_index": physics_index,
        }


class _CompositeVideoRecorder:
    def __init__(
        self,
        *,
        output_path: Path,
        frame_map_path: Path,
        fps: float,
        camera_names: Sequence[str],
        treatment: str,
        run_nonce: str,
        parent_pid: int,
        child_pid: int,
        run_id: str,
    ) -> None:
        self.output_path = output_path
        self.frame_map_path = frame_map_path
        self.fps = _finite_scalar(fps, field="video_fps")
        if self.fps <= 0.0:
            raise AuditNoGo("video_fps_invalid", str(fps))
        if (
            not isinstance(camera_names, Sequence)
            or isinstance(camera_names, (str, bytes, bytearray))
            or len(camera_names) != 2
            or any(not isinstance(name, str) or not name for name in camera_names)
            or len(set(camera_names)) != 2
        ):
            raise AuditNoGo("video_camera_names_invalid", str(camera_names))
        self.camera_names = tuple(camera_names)
        self._writer = None
        self._cv2 = None
        self._frames: list[dict[str, int]] = []
        self._identity = {
            "treatment": treatment,
            "run_nonce": run_nonce,
            "parent_pid": parent_pid,
            "child_pid": child_pid,
            "run_id": run_id,
        }

    @staticmethod
    def _rgb(frame: Any) -> np.ndarray:
        value = np.asarray(frame)
        if value.ndim != 3:
            raise RuntimeError("composite_video_frame_rank_invalid")
        if value.shape[0] in {3, 4} and value.shape[-1] not in {3, 4}:
            value = value.transpose(1, 2, 0)
        if value.shape[-1] not in {3, 4}:
            raise RuntimeError("composite_video_frame_channels_invalid")
        value = value[:, :, :3]
        if value.dtype != np.uint8:
            if not np.isfinite(value).all():
                raise RuntimeError("composite_video_frame_nonfinite")
            value = np.clip(value, 0, 255).astype(np.uint8)
        return np.ascontiguousarray(value)

    def capture(self, displays: Mapping[str, Any], *, transition_index: int, world_index: int) -> None:
        if not isinstance(displays, Mapping):
            raise RuntimeError("composite_video_displays_missing")
        try:
            first = self._rgb(displays[self.camera_names[0]])
            second = self._rgb(displays[self.camera_names[1]])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("composite_video_camera_frame_missing") from exc
        import cv2

        if first.shape[0] != second.shape[0]:
            second = cv2.resize(second, (second.shape[1], first.shape[0]))
        composite = np.concatenate((first, second), axis=1)
        if self._writer is None:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(
                str(self.output_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                self.fps,
                (int(composite.shape[1]), int(composite.shape[0])),
            )
            if not writer.isOpened():
                writer.release()
                raise RuntimeError("composite_video_open_failed")
            self._writer = writer
            self._cv2 = cv2
        self._writer.write(self._cv2.cvtColor(composite, self._cv2.COLOR_RGB2BGR))
        self._frames.append(
            {
                "video_frame_index": len(self._frames),
                "transition_index": int(transition_index),
                "world_index": int(world_index),
            }
        )

    def close(self) -> dict[str, Any]:
        if self._writer is None or not self._frames:
            raise RuntimeError("composite_video_no_frames_encoded")
        self._writer.release()
        self._writer = None
        if not self.output_path.is_file() or self.output_path.stat().st_size <= 0:
            raise RuntimeError("composite_video_encode_failed")
        payload = {"schema_version": 1, **self._identity, "frames": self._frames}
        atomic_create_json(self.frame_map_path, payload)
        return {
            "video": _artifact_record(self.output_path, relative_to=self.output_path.parent),
            "frame_map": _artifact_record(self.frame_map_path, relative_to=self.frame_map_path.parent),
            "frame_count": len(self._frames),
        }

    def abort(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None


def _runtime_scene_identity(
    stage: Any, world: Any, *, diagnostic: Mapping[str, Any]
) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    scene_paths = [
        str(prim.GetPath())
        for prim in Usd.PrimRange.Stage(stage)
        if prim.IsA(UsdPhysics.Scene)
    ]
    context = world.get_physics_context()
    context_path = getattr(context, "prim_path", None)
    context_path = context_path() if callable(context_path) else context_path
    context_path = str(context_path)
    scene = UsdPhysics.Scene(stage.GetPrimAtPath(context_path))
    direction = _finite_vector(
        scene.GetGravityDirectionAttr().Get(), field="scene_gravity_direction"
    )
    magnitude = _finite_scalar(
        scene.GetGravityMagnitudeAttr().Get(), field="scene_gravity_magnitude", nonnegative=True
    )
    gravity = direction * magnitude
    physics_dt = _finite_scalar(world.get_physics_dt(), field="physics_dt")
    payload = {
        "physics_scene_paths": scene_paths,
        "physics_context_path": context_path,
        "physics_dt": physics_dt,
        "gravity_world_m_s2": gravity.tolist(),
        "stage_units_in_meters": float(diagnostic["stage_units_in_meters"]),
    }
    payload["valid"] = bool(
        str(diagnostic["physics_scene_path"]) in scene_paths
        and context_path == str(diagnostic["physics_scene_path"])
        and math.isclose(
            physics_dt,
            float(diagnostic["physics_dt"]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
        and np.allclose(
            gravity,
            diagnostic["gravity_world_m_s2"],
            rtol=0.0,
            atol=1.0e-6,
        )
    )
    return payload


def _runtime_body_origin_metric(stage: Any) -> dict[str, Any]:
    from pxr import Usd

    source = stage.GetPrimAtPath(SOURCE_BODY_PATH)
    root = stage.GetPrimAtPath(SOURCE_ROOT_PATH)
    if not source or not source.IsValid() or not root or not root.IsValid():
        raise AuditNoGo("source_body_missing", SOURCE_BODY_PATH)
    overrides = []
    for prim in Usd.PrimRange(root):
        for attribute in prim.GetAttributes():
            name = attribute.GetName()
            normalized = name.lower().replace("_", "")
            if "centerofmass" not in normalized:
                continue
            if attribute.HasAuthoredValueOpinion():
                overrides.append(
                    {
                        "path": str(prim.GetPath()),
                        "name": name,
                        "value": _static_usd_native(attribute.Get()),
                    }
                )
    return {
        "metric": "rigid_body_origin",
        "authored_center_of_mass_overrides": overrides,
        "valid": not overrides,
    }


def _runtime_source_local_com_authority(
    app: Any,
    stage: Any,
    *,
    stage_id: int,
    world: Any,
    query_interface: Any = None,
    query_mode: Any = None,
    valid_query_result: Any = None,
    sdf_path_to_int: Any = None,
) -> dict[str, Any]:
    """Read the cooked PhysX COM in the rigid body's local frame and seal it."""

    if (
        query_interface is None
        or query_mode is None
        or valid_query_result is None
        or sdf_path_to_int is None
    ):
        from omni.physx import get_physx_property_query_interface
        from omni.physx.bindings._physx import (
            PhysxPropertyQueryMode,
            PhysxPropertyQueryResult,
        )
        from pxr import PhysicsSchemaTools

        query_interface = get_physx_property_query_interface()
        query_mode = PhysxPropertyQueryMode.QUERY_RIGID_BODY_WITH_COLLIDERS
        valid_query_result = PhysxPropertyQueryResult.VALID
        sdf_path_to_int = PhysicsSchemaTools.sdfPathToInt

    source = stage.GetPrimAtPath(SOURCE_BODY_PATH)
    is_valid = getattr(source, "IsValid", None)
    if source is None or (callable(is_valid) and not is_valid()):
        raise AuditNoGo("source_cooked_com_prim_missing", SOURCE_BODY_PATH)
    world_before = _runtime_world_counter(world)
    if world_before != 0:
        raise AuditNoGo("source_cooked_com_query_unsafe", "world_counter_not_pre_reset")
    if _runtime_world_is_playing(world):
        raise AuditNoGo("source_cooked_com_query_unsafe", "world_playing")
    if not callable(sdf_path_to_int):
        raise AuditNoGo("source_cooked_com_query_unsafe", "sdf_path_to_int_missing")
    query = getattr(query_interface, "query_prim", None)
    if not callable(query):
        raise AuditNoGo("source_cooked_com_query_unsafe", "query_prim_missing")
    completed = {"value": False}
    result: dict[str, Any] = {}

    def rigid_body_callback(info: Any) -> None:
        if getattr(info, "result", None) != valid_query_result:
            result["error"] = str(getattr(info, "result", None))
            return
        try:
            result.update(
                {
                    "mass_kg": float(info.mass),
                    "center_of_mass_local_m": [float(value) for value in info.center_of_mass],
                    "diagonal_inertia_kg_m2": [float(value) for value in info.inertia],
                }
            )
        except (TypeError, ValueError) as exc:
            result["error"] = f"callback:{type(exc).__name__}"

    try:
        prim_id = sdf_path_to_int(source.GetPath())
        query(
            stage_id=stage_id,
            prim_id=prim_id,
            query_mode=query_mode,
            rigid_body_fn=rigid_body_callback,
            finished_fn=lambda *_args: completed.__setitem__("value", True),
            timeout_ms=60000,
        )
    except BaseException as exc:
        raise AuditNoGo("source_cooked_com_unavailable", type(exc).__name__) from exc
    if _runtime_world_counter(world) != world_before or _runtime_world_is_playing(world):
        raise AuditNoGo("source_cooked_com_query_unsafe", "query_advanced_or_started_world")
    for _ in range(600):
        if completed["value"]:
            break
        if _runtime_world_counter(world) != world_before or _runtime_world_is_playing(world):
            raise AuditNoGo("source_cooked_com_query_unsafe", "pre_update_world_changed")
        try:
            app.update()
        except BaseException as exc:
            raise AuditNoGo("source_cooked_com_unavailable", type(exc).__name__) from exc
        if _runtime_world_counter(world) != world_before or _runtime_world_is_playing(world):
            raise AuditNoGo("source_cooked_com_query_unsafe", "update_advanced_or_started_world")
    world_after = _runtime_world_counter(world)
    if (
        not completed["value"]
        or "error" in result
        or set(result)
        != {"mass_kg", "center_of_mass_local_m", "diagonal_inertia_kg_m2"}
    ):
        raise AuditNoGo("source_cooked_com_unavailable", json.dumps(result, sort_keys=True))
    try:
        mass = _finite_scalar(result["mass_kg"], field="source_cooked_mass", nonnegative=True)
        com = _finite_vector(result["center_of_mass_local_m"], field="source_local_com")
        inertia = _finite_vector(
            result["diagonal_inertia_kg_m2"], field="source_cooked_inertia"
        )
    except ValueError as exc:
        raise AuditNoGo("source_cooked_com_invalid", str(exc)) from exc
    if mass <= 0.0 or np.any(inertia < 0.0):
        raise AuditNoGo("source_cooked_com_invalid", json.dumps(result, sort_keys=True))
    payload = {
        "kind": "physx_cooked_rigid_body_properties",
        "source_body_path": SOURCE_BODY_PATH,
        "stage_id": stage_id,
        "query_complete": True,
        "query_timing": "pre_task_reset_nonplaying",
        "world_counter_before": world_before,
        "world_counter_after": world_after,
        "mass_kg": mass,
        "center_of_mass_local_m": com.tolist(),
        "diagonal_inertia_kg_m2": inertia.tolist(),
    }
    return {**payload, "sealed_sha256": _canonical_json_sha256(payload)}


def _runtime_source_contract(
    stage: Any,
    source_state: Mapping[str, Any],
    *,
    stage_id: int,
    source_adapter: RuntimeReadOnlySourceAdapter,
    source_local_com_authority: Mapping[str, Any],
    active_scene: Mapping[str, Any],
) -> dict[str, Any]:
    from pxr import UsdPhysics

    source = stage.GetPrimAtPath(SOURCE_BODY_PATH)
    if not source or not source.IsValid():
        raise AuditNoGo("source_body_missing", SOURCE_BODY_PATH)
    rigid = UsdPhysics.RigidBodyAPI(source)
    collision = UsdPhysics.CollisionAPI(source)
    owner = source.GetRelationship("physics:simulationOwner")
    owners = [] if not owner else [str(value) for value in owner.GetTargets()]
    if len(owners) != 1:
        owner_path = None
    else:
        owner_path = owners[0]
    disable_gravity_attribute = source.GetAttribute("physxRigidBody:disableGravity")
    disable_gravity = (
        None if not disable_gravity_attribute else disable_gravity_attribute.Get()
    )
    adapter_contract = source_adapter.contract()
    membership_readbacks = {
        **copy.deepcopy(adapter_contract.get("readbacks", {})),
        "physx_is_sleeping": True,
    }
    membership_valid = bool(
        adapter_contract.get("kind") == "omni.isaac.core.prims.RigidPrimView"
        and adapter_contract.get("source_body_path") == SOURCE_BODY_PATH
        and adapter_contract.get("count") == 1
        and adapter_contract.get("initialized") is True
        and adapter_contract.get("read_only") is True
        and membership_readbacks
        == {
            "world_pose": True,
            "linear_velocity": True,
            "angular_velocity": True,
            "physx_is_sleeping": True,
        }
    )
    contract = {
        "source_body_path": SOURCE_BODY_PATH,
        "source_collider_path": SOURCE_BODY_PATH,
        "rigid_body_enabled": None if not rigid else rigid.GetRigidBodyEnabledAttr().Get(),
        "collision_enabled": None if not collision else collision.GetCollisionEnabledAttr().Get(),
        "gravity_enabled": disable_gravity is not True,
        "kinematic_enabled": None if not rigid else rigid.GetKinematicEnabledAttr().Get(),
        "awake": source_state.get("awake"),
        "scene_owner": owner_path,
        "stage_id": stage_id,
        "motion_readbacks": {
            "world_pose": True,
            "linear_velocity": True,
            "angular_velocity": True,
            "physx_is_sleeping": True,
        },
        "simulation_owner_targets": owners,
        "active_scene_contract": {
            "valid": active_scene.get("valid"),
            "physics_context_path": active_scene.get("physics_context_path"),
            "physics_scene_paths": copy.deepcopy(active_scene.get("physics_scene_paths")),
        },
        "live_physics_membership": {
            "source_body_path": SOURCE_BODY_PATH,
            "adapter_initialized": adapter_contract.get("initialized"),
            "readbacks": membership_readbacks,
            "state": copy.deepcopy(dict(source_state)),
            "valid": membership_valid,
        },
        "body_origin_metric": _runtime_body_origin_metric(stage),
        "source_local_com_authority": copy.deepcopy(dict(source_local_com_authority)),
        "read_only_adapter": adapter_contract,
    }
    return contract


def _runtime_dependency_closure(entry_path: Path) -> dict[str, Any]:
    from pxr import UsdUtils

    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(str(entry_path))
    paths = {entry_path.resolve()}
    unresolved_values = [str(value) for value in unresolved]
    for value in (*layers, *assets):
        raw = str(
            getattr(value, "realPath", "")
            or getattr(value, "resolvedPath", "")
            or getattr(value, "path", "")
            or getattr(value, "identifier", "")
            or value
        )
        if not raw or raw.startswith("anon:") or "://" in raw:
            unresolved_values.append(raw)
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = entry_path.parent / path
        path = path.resolve()
        if path.is_file():
            paths.add(path)
        else:
            unresolved_values.append(str(path))
    records = [
        {
            "path": str(path),
            "byte_count": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(paths, key=str)
    ]
    payload = {
        "entry_path": str(entry_path.resolve()),
        "entry_sha256": sha256_file(entry_path),
        "files": records,
        "unresolved": sorted(set(unresolved_values)),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _is_remote_dependency(value: Any) -> bool:
    return isinstance(value, str) and "://" in value


def _local_franka_identity_failures(
    identity: Any, *, local_franka: Mapping[str, Any]
) -> list[str]:
    failures: list[str] = []
    try:
        expected_root = Path(str(local_franka["absolute_usd_path"])).resolve()
        expected_relative_path = str(local_franka["usd_path"])
        expected_sha256 = str(local_franka["sha256"])
    except (KeyError, TypeError, ValueError):
        return ["local_franka_parent_asset_invalid"]
    if not isinstance(identity, Mapping):
        return ["local_franka_identity_missing"]
    payload = dict(identity)
    recorded_sha256 = payload.pop("sha256", None)
    try:
        if not _is_sha256(recorded_sha256) or recorded_sha256 != _canonical_json_sha256(payload):
            failures.append("local_franka_identity_hash_invalid")
    except (TypeError, ValueError):
        failures.append("local_franka_identity_hash_invalid")
    if (
        identity.get("root_path") != ROBOT_ROOT_PATH
        or identity.get("root_usd_path") != expected_relative_path
        or identity.get("root_absolute_usd_path") != str(expected_root)
        or identity.get("root_sha256") != expected_sha256
    ):
        failures.append("local_franka_root_binding_invalid")

    closure = identity.get("dependency_closure")
    if not isinstance(closure, Mapping):
        failures.append("local_franka_dependency_closure_invalid")
    else:
        closure_payload = dict(closure)
        closure_sha256 = closure_payload.pop("sha256", None)
        try:
            if (
                not _is_sha256(closure_sha256)
                or closure_sha256 != _canonical_json_sha256(closure_payload)
            ):
                failures.append("local_franka_dependency_closure_hash_invalid")
        except (TypeError, ValueError):
            failures.append("local_franka_dependency_closure_hash_invalid")
        if (
            closure.get("entry_path") != str(expected_root)
            or closure.get("entry_sha256") != expected_sha256
        ):
            failures.append("local_franka_dependency_root_binding_invalid")
        unresolved = closure.get("unresolved")
        if not isinstance(unresolved, list):
            failures.append("local_franka_dependency_closure_invalid")
        elif unresolved:
            failures.append("local_franka_dependency_unresolved")
            if any(_is_remote_dependency(value) for value in unresolved):
                failures.append("local_franka_remote_dependency")
        files = closure.get("files")
        if not isinstance(files, list) or not files:
            failures.append("local_franka_dependency_closure_invalid")
        else:
            root_records = 0
            runtime_mdl = Path(ISAACSIM41_FRANKA_RUNTIME_OMNIPBR_PATH).resolve()
            for record in files:
                if not isinstance(record, Mapping):
                    failures.append("local_franka_dependency_closure_invalid")
                    continue
                path_text = record.get("path")
                if _is_remote_dependency(path_text):
                    failures.append("local_franka_remote_dependency")
                    continue
                if not isinstance(path_text, str) or not path_text:
                    failures.append("local_franka_dependency_closure_invalid")
                    continue
                path = Path(path_text)
                if not path.is_absolute():
                    failures.append("local_franka_dependency_path_invalid")
                    continue
                resolved = path.resolve()
                pinned_runtime_mdl = (
                    path_text == ISAACSIM41_FRANKA_RUNTIME_OMNIPBR_PATH
                    and resolved == runtime_mdl
                )
                try:
                    resolved.relative_to(REPO_ROOT.resolve())
                except ValueError:
                    if not pinned_runtime_mdl:
                        failures.append("local_franka_dependency_path_invalid")
                        continue
                if not resolved.is_file():
                    failures.append("local_franka_dependency_path_invalid")
                    continue
                if pinned_runtime_mdl and (
                    record.get("sha256") != ISAACSIM41_FRANKA_RUNTIME_OMNIPBR_SHA256
                    or sha256_file(resolved) != ISAACSIM41_FRANKA_RUNTIME_OMNIPBR_SHA256
                ):
                    failures.append("local_franka_runtime_mdl_drift")
                if (
                    type(record.get("byte_count")) is not int
                    or record.get("byte_count") != resolved.stat().st_size
                    or not _is_sha256(record.get("sha256"))
                    or record.get("sha256") != sha256_file(resolved)
                ):
                    failures.append("local_franka_dependency_file_drift")
                if resolved == expected_root:
                    root_records += 1
                    if record.get("sha256") != expected_sha256:
                        failures.append("local_franka_dependency_root_binding_invalid")
            if root_records != 1:
                failures.append("local_franka_dependency_root_binding_invalid")

    layers = identity.get("prim_stack_layers")
    if not isinstance(layers, list) or not layers:
        failures.append("local_franka_prim_stack_invalid")
    else:
        pinned_root_found = False
        for layer in layers:
            if not isinstance(layer, Mapping):
                failures.append("local_franka_prim_stack_invalid")
                continue
            identifier = layer.get("identifier")
            real_path = layer.get("real_path")
            if not isinstance(identifier, str) or not isinstance(real_path, str):
                failures.append("local_franka_prim_stack_invalid")
                continue
            if _is_remote_dependency(identifier) or _is_remote_dependency(real_path):
                failures.append("local_franka_remote_dependency")
                continue
            if not real_path:
                continue
            resolved = Path(real_path).resolve()
            if not resolved.is_file():
                failures.append("local_franka_prim_stack_invalid")
                continue
            try:
                resolved.relative_to(REPO_ROOT.resolve())
            except ValueError:
                failures.append("local_franka_prim_stack_invalid")
                continue
            if resolved == expected_root:
                if layer.get("sha256") != expected_sha256:
                    failures.append("local_franka_prim_stack_binding_invalid")
                else:
                    pinned_root_found = True
        if not pinned_root_found:
            failures.append("local_franka_prim_stack_binding_invalid")

    if (
        identity.get("dof_names") != list(FRANKA_DOF_NAMES)
        or identity.get("dof_count") != len(FRANKA_DOF_NAMES)
    ):
        failures.append("local_franka_dof_identity_invalid")
    if (
        identity.get("left_finger_body_path") != LEFT_FINGER_BODY_PATH
        or identity.get("right_finger_body_path") != RIGHT_FINGER_BODY_PATH
        or identity.get("hand_body_path") != HAND_BODY_PATH
    ):
        failures.append("local_franka_body_identity_invalid")
    return sorted(set(failures))


def evaluate_local_franka_evidence(
    pre: Any,
    post: Any,
    *,
    diagnostic: Mapping[str, Any],
) -> dict[str, Any]:
    audit_failures: list[str] = []
    try:
        local_franka = resolve_local_franka_asset(diagnostic)
        audit_failures.extend(
            _local_franka_identity_failures(pre, local_franka=local_franka)
        )
        audit_failures.extend(
            _local_franka_identity_failures(post, local_franka=local_franka)
        )
        if _canonical_json_bytes(pre) != _canonical_json_bytes(post):
            audit_failures.append("local_franka_pre_post_mismatch")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {"audit_valid": not audit_failures, "audit_failures": audit_failures}


def _runtime_local_franka_identity(
    stage: Any,
    robot: Any,
    *,
    local_franka: Mapping[str, Any],
    dependency_closure: Mapping[str, Any],
) -> dict[str, Any]:
    root = stage.GetPrimAtPath(ROBOT_ROOT_PATH)
    if not root or not root.IsValid():
        raise AuditNoGo("local_franka_root_missing", ROBOT_ROOT_PATH)
    body_paths = {
        "left_finger_body_path": LEFT_FINGER_BODY_PATH,
        "right_finger_body_path": RIGHT_FINGER_BODY_PATH,
        "hand_body_path": HAND_BODY_PATH,
    }
    for path in body_paths.values():
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise AuditNoGo("local_franka_body_missing", path)
    dof_names = getattr(robot, "dof_names", None)
    dof_names = dof_names() if callable(dof_names) else dof_names
    if isinstance(dof_names, (str, bytes, bytearray)):
        raise AuditNoGo("local_franka_dof_authority_missing", type(dof_names).__name__)
    try:
        dof_names = [str(name) for name in dof_names]
    except TypeError as exc:
        raise AuditNoGo(
            "local_franka_dof_authority_missing", type(dof_names).__name__
        ) from exc
    layers = []
    for spec in root.GetPrimStack():
        layer = spec.layer
        real_path = str(layer.realPath or "")
        record = {"identifier": str(layer.identifier), "real_path": real_path}
        if real_path and Path(real_path).is_file():
            record["sha256"] = sha256_file(real_path)
        layers.append(record)
    payload = {
        "root_path": ROBOT_ROOT_PATH,
        "root_usd_path": local_franka["usd_path"],
        "root_absolute_usd_path": local_franka["absolute_usd_path"],
        "root_sha256": local_franka["sha256"],
        "dependency_closure": copy.deepcopy(dict(dependency_closure)),
        "prim_stack_layers": layers,
        "dof_names": dof_names,
        "dof_count": len(dof_names),
        **body_paths,
    }
    identity = {**payload, "sha256": _canonical_json_sha256(payload)}
    failures = _local_franka_identity_failures(identity, local_franka=local_franka)
    if failures:
        raise AuditNoGo(
            "local_franka_identity_invalid",
            json.dumps(failures, sort_keys=True),
            evidence=identity,
        )
    return identity


def _canonical_isaac_version(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?", value.strip())
    if match is None:
        return None
    major, minor, patch, build = match.groups()
    return ".".join((major, minor, patch, build or "0"))


def _runtime_version_identity(
    isaacsim_module: Any,
    *,
    kit_app: Any = None,
    expected_version: str = "4.1.0.0",
) -> dict[str, Any]:
    del isaacsim_module  # Isaac 4.1's namespace module has no reliable __version__.
    expected = _canonical_isaac_version(expected_version)
    if expected is None:
        raise AuditNoGo("isaac_runtime_version_contract_invalid", str(expected_version))
    sources: dict[str, str] = {}
    for distribution in ("isaacsim", "omni.isaac.sim"):
        try:
            version = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError:
            continue
        except BaseException as exc:
            raise AuditNoGo(
                "isaac_runtime_version_metadata_error",
                f"{distribution}:{type(exc).__name__}",
            ) from exc
        if not isinstance(version, str) or not version.strip():
            raise AuditNoGo("isaac_runtime_version_unavailable", distribution)
        sources[f"distribution:{distribution}"] = version.strip()
    if not sources and kit_app is not None:
        getter = getattr(kit_app, "get_app_version", None)
        if not callable(getter):
            raise AuditNoGo("isaac_runtime_version_unavailable", "kit get_app_version missing")
        version = getter()
        if not isinstance(version, str) or not version.strip():
            raise AuditNoGo("isaac_runtime_version_unavailable", "kit app version invalid")
        sources["kit_app"] = version.strip()
    if not sources:
        raise AuditNoGo("isaac_runtime_version_unavailable", "metadata and kit unavailable")
    normalized = {name: _canonical_isaac_version(value) for name, value in sources.items()}
    if any(value != expected for value in normalized.values()):
        raise AuditNoGo(
            "isaac_runtime_version_mismatch",
            json.dumps({"expected": expected, "sources": sources}, sort_keys=True),
            evidence={"expected": expected, "version_sources": sources},
        )
    payload = {
        "isaac_sim_version": expected,
        "version_sources": sources,
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version.split()[0],
        "numpy_version": np.__version__,
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _install_runtime_write_audit(
    audit: _RuntimeWriteAudit,
    *,
    source_adapter: RuntimeReadOnlySourceAdapter,
    controller: Any,
    object_utils: Any,
    static_production_closure: Mapping[str, Any],
) -> None:
    if (
        not isinstance(static_production_closure, Mapping)
        or static_production_closure.get("audit_valid") is not True
        or not isinstance(static_production_closure.get("required_runtime_surfaces"), list)
        or not isinstance(static_production_closure.get("not_applicable_runtime_surfaces"), list)
    ):
        raise AuditNoGo("static_production_closure_audit_invalid", "runtime controls unknown")
    required = set(static_production_closure["required_runtime_surfaces"])
    if not required <= set(REQUIRED_WRITER_AUDIT_SURFACES):
        raise AuditNoGo("static_production_closure_audit_invalid", "runtime surface unknown")
    audit.set_static_production_closure(static_production_closure)
    adapter_contract = source_adapter.contract()
    if adapter_contract.get("read_only") is not True or any(
        name.startswith("set_") for name in vars(type(source_adapter))
    ):
        raise AuditNoGo("source_read_adapter_writer_surface_invalid", str(adapter_contract))
    audit.mark_covered("source_adapter_read_only")
    rigid_view = source_adapter._view
    physics_view = getattr(rigid_view, "_physics_view", None)
    force_at_position_method = (
        "apply_forces_and_torques_at_pos"
        if callable(getattr(rigid_view, "apply_forces_and_torques_at_pos", None))
        else "apply_forces_and_torques_at_position"
    )
    high_level_specs = (
        (
            rigid_view,
            "set_world_poses",
            "plural_prim_view_world_poses",
            ("plural_pose_velocity", "plural_world_poses"),
        ),
        (
            rigid_view,
            "set_local_poses",
            "plural_prim_view_local_poses",
            ("plural_pose_velocity", "plural_local_poses"),
        ),
        (
            rigid_view,
            "set_velocities",
            "plural_prim_view_velocities",
            ("plural_pose_velocity", "plural_velocities"),
        ),
        (
            rigid_view,
            "set_linear_velocities",
            "plural_prim_view_linear_velocities",
            ("plural_pose_velocity", "plural_linear_velocities"),
        ),
        (
            rigid_view,
            "set_angular_velocities",
            "plural_prim_view_angular_velocities",
            ("plural_pose_velocity", "plural_angular_velocities"),
        ),
        (
            rigid_view,
            "apply_forces",
            "physics_view_forces",
            ("forces_torques_impulses", "forces"),
        ),
        (
            rigid_view,
            "apply_torques",
            "physics_view_torques",
            ("forces_torques_impulses", "torques"),
        ),
        (
            rigid_view,
            "apply_impulses",
            "physics_view_impulses",
            ("forces_torques_impulses", "impulses"),
        ),
        (
            rigid_view,
            "apply_forces_and_torques",
            "physics_view_forces_torques_impulses",
            ("forces_torques_impulses", "forces", "torques"),
        ),
        (
            rigid_view,
            force_at_position_method,
            "physics_view_force_at_position",
            "force_at_position",
        ),
    )
    physics_specs = (
        (physics_view, "set_kinematic_targets", "physics_view_kinematic_targets", "kinematic_targets"),
        (physics_view, "set_dynamic_targets", "physics_view_dynamic_targets", "dynamic_targets"),
        (
            physics_view,
            "set_transforms",
            "physics_view_transforms",
            ("transforms_velocities", "transforms"),
        ),
        (
            physics_view,
            "set_velocities",
            "physics_view_velocities",
            ("transforms_velocities", "physics_velocities"),
        ),
    )
    for obj, method, surface, count in (*high_level_specs, *physics_specs):
        audit.audit_callable(
            obj,
            method,
            surface=surface,
            count=count,
            source_scoped=False,
            required=surface in required,
        )
    audit.summarize_surface(
        "plural_prim_view_pose_velocity",
        (
            "plural_prim_view_world_poses",
            "plural_prim_view_local_poses",
            "plural_prim_view_velocities",
            "plural_prim_view_linear_velocities",
            "plural_prim_view_angular_velocities",
        ),
    )
    audit.summarize_surface(
        "physics_view_transforms_velocities",
        ("physics_view_transforms", "physics_view_velocities"),
    )
    audit.summarize_surface(
        "physics_view_forces_torques_impulses",
        (
            "physics_view_forces",
            "physics_view_torques",
            "physics_view_impulses",
            "physics_view_force_at_position",
        ),
    )
    if not audit.surfaces["object_utils_set_object_position"]["audited"]:
        audit.audit_callable(
            object_utils,
            "set_object_position",
            surface="object_utils_set_object_position",
            count="root_body_pose_velocity",
            source_scoped=True,
            required="object_utils_set_object_position" in required,
        )
    gripper = getattr(controller, "gripper_control", None)
    def gripper_source_path(args: Sequence[Any], kwargs: Mapping[str, Any]) -> str | None:
        explicit = audit._call_path(args, kwargs)
        return explicit if explicit is not None else getattr(gripper, "grasped_object_path", None)

    for method, surface in (
        ("add_object_to_gripper", "gripper_add_object_to_gripper"),
        ("update_grasped_object_position", "gripper_update_grasped_object_position"),
        ("release_object", "gripper_release_object"),
    ):
        audit.audit_callable(
            gripper,
            method,
            surface=surface,
            count="software_gripper_calls",
            source_scoped=True,
            required=surface in required,
            source_path_resolver=gripper_source_path,
        )


def _runtime_contact_summary(
    sample: Mapping[str, Any],
    *,
    source_awake: bool,
    observer_decision: Mapping[str, Any],
    protocol: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    support = sample.get("support")
    if not isinstance(support, Mapping):
        raise AuditNoGo("contact_support_authority_missing", "missing support record")
    events = support.get("events")
    if not isinstance(events, list):
        raise AuditNoGo("contact_support_authority_missing", "events missing")
    summary = {
        "contact_read_once": True,
        "identity_valid": sample.get("identity_valid") is True,
        "classifications": copy.deepcopy(sample.get("classifications", [])),
        "bootstrap_classifications": sorted(
            {
                str(pair["classification"])
                for pair in sample.get("pairs", [])
                if isinstance(pair, Mapping)
                and pair.get("bootstrap") is True
                and isinstance(pair.get("classification"), str)
            }
        ),
        "support_state": observer_decision["state"],
        "support_event": events[-1] if events else None,
        "support_header_count": support.get("header_count"),
        "support_contact_count": support.get("contact_count"),
        "support_friction_anchor_count": support.get("friction_anchor_count"),
        "source_awake": source_awake,
        "topology": copy.deepcopy(sample.get("topology")),
        "forbidden_source_contact": sample.get("forbidden_source_contact") is True,
        "robot_environment_contact": sample.get("robot_environment_contact") is True,
        "source_support_recontact": False,
        "support_observer": copy.deepcopy(dict(observer_decision)),
        "initial_support_absent_reports": observer_decision["absent_reports"],
        "initial_support_prefix_physical_failures": copy.deepcopy(
            observer_decision["prefix_physical_failures"]
        ),
    }
    if "support_pairs" in observer_decision:
        summary["support_pairs"] = copy.deepcopy(observer_decision["support_pairs"])
        summary["support_pair_physical_failures"] = copy.deepcopy(
            observer_decision["support_pair_physical_failures"]
        )
    if "support_observation_gap" in observer_decision:
        summary["support_observation_gap"] = observer_decision["support_observation_gap"]
        summary["unreported_active_pairs"] = copy.deepcopy(
            observer_decision["unreported_active_pairs"]
        )
    if _contact_load_bearing_policy(protocol):
        physical_classifications = sample.get("physical_classifications")
        noncontact_clearance_m = sample.get("noncontact_clearance_m")
        if (
            not isinstance(physical_classifications, list)
            or any(not isinstance(value, str) for value in physical_classifications)
            or not isinstance(noncontact_clearance_m, Mapping)
            or any(
                not isinstance(name, str)
                or not isinstance(value, (int, float, np.number))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or float(value) <= 0.0
                for name, value in noncontact_clearance_m.items()
            )
        ):
            raise AuditNoGo("contact_load_bearing_authority_missing", "contact summary")
        summary["physical_classifications"] = copy.deepcopy(physical_classifications)
        summary["noncontact_clearance_m"] = {
            name: float(value) for name, value in noncontact_clearance_m.items()
        }
    return summary


_V4_OBSERVATION_GAP_SAMPLE_FIELDS = (
    "physics_index",
    "identity_valid",
    "classifications",
    "pairs",
    "support",
    "support_observation_gap",
    "unreported_active_pairs",
)


def _v4_observation_gap_pairs_valid(
    pairs: Any,
    *,
    protocol: Mapping[str, Any],
    gap: bool,
) -> bool:
    expected = [
        list(sorted((SOURCE_BODY_PATH, support)))
        for support in protocol["support_collider_paths"]
    ]
    if not isinstance(pairs, list) or gap is not bool(pairs):
        return False
    seen = []
    for pair in pairs:
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or any(not isinstance(path, str) or not path for path in pair)
            or pair != sorted(pair)
            or pair not in expected
            or pair in seen
        ):
            return False
        seen.append(pair)
    return seen == [pair for pair in expected if pair in seen]


def _v4_observation_gap_sample_projection(
    sample: Mapping[str, Any], *, protocol: Mapping[str, Any]
) -> dict[str, Any]:
    spec = _require_protocol_spec(protocol)
    if spec.get("allow_active_support_pair_omission") is not True:
        raise ValueError("instrumented_v4_observation_gap_protocol_invalid")
    if not isinstance(sample, Mapping) or any(
        field not in sample for field in _V4_OBSERVATION_GAP_SAMPLE_FIELDS
    ):
        raise ValueError("instrumented_v4_observation_gap_sample_missing")
    result = {
        field: copy.deepcopy(sample[field]) for field in _V4_OBSERVATION_GAP_SAMPLE_FIELDS
    }
    gap = result["support_observation_gap"]
    pairs = result["unreported_active_pairs"]
    support = result["support"]
    if (
        type(result["physics_index"]) is not int
        or result["physics_index"] < 0
        or result["identity_valid"] is not True
        or not isinstance(result["classifications"], list)
        or any(not isinstance(value, str) for value in result["classifications"])
        or not isinstance(result["pairs"], list)
        or type(gap) is not bool
        or not _v4_observation_gap_pairs_valid(pairs, protocol=spec, gap=gap)
        or not isinstance(support, Mapping)
        or support.get("support_observation_gap") is not gap
        or support.get("unreported_active_pairs") != pairs
    ):
        raise ValueError("instrumented_v4_observation_gap_sample_invalid")
    return result


def _runtime_observation_gap_journal(
    *,
    transition_index: int,
    raw_report: Mapping[str, Any],
    sample: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Preserve a parser-accepted v4 gap before topology or control can fail."""

    projection = _v4_observation_gap_sample_projection(sample, protocol=protocol)
    if projection["support_observation_gap"] is not True:
        return None
    if (
        type(transition_index) is not int
        or transition_index < 0
        or not isinstance(raw_report, Mapping)
    ):
        raise AuditNoGo("observation_gap_journal_invalid", "parser observation gap")
    return {
        "transition_index": transition_index,
        "raw_report": copy.deepcopy(dict(raw_report)),
        "parser_sample": projection,
    }


_CONTACT_OBSERVER_PROJECTION_FIELDS = (
    "contact_read_once",
    "identity_valid",
    "classifications",
    "bootstrap_classifications",
    "support_state",
    "support_event",
    "support_header_count",
    "support_contact_count",
    "support_friction_anchor_count",
    "source_awake",
    "topology",
    "forbidden_source_contact",
    "robot_environment_contact",
    "source_support_recontact",
    "support_observer",
    "initial_support_absent_reports",
    "initial_support_prefix_physical_failures",
)


def _contact_observer_projection(
    contact: Mapping[str, Any], *, protocol: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    if not isinstance(contact, Mapping) or any(
        field not in contact for field in _CONTACT_OBSERVER_PROJECTION_FIELDS
    ):
        raise ValueError("instrumented_contact_projection_missing")
    projection = {
        field: copy.deepcopy(contact[field]) for field in _CONTACT_OBSERVER_PROJECTION_FIELDS
    }
    required_v4_fields = ()
    required_v6_fields = ()
    if protocol is not None and _require_protocol_spec(protocol).get(
        "allow_active_support_pair_omission"
    ) is True:
        required_v4_fields = ("support_observation_gap", "unreported_active_pairs")
        if any(field not in contact for field in required_v4_fields):
            raise ValueError("instrumented_v4_observation_gap_projection_missing")
    if _contact_load_bearing_policy(protocol):
        required_v6_fields = ("physical_classifications", "noncontact_clearance_m")
        if any(field not in contact for field in required_v6_fields):
            raise ValueError("instrumented_v6_contact_load_projection_missing")
    for field in (
        "support_pairs",
        "support_pair_physical_failures",
        *required_v4_fields,
        *required_v6_fields,
    ):
        if field in contact:
            projection[field] = copy.deepcopy(contact[field])
    return projection


def _runtime_transition_boundary(
    stage: Any,
    *,
    identities: Mapping[str, Any],
    mutation_segment: Mapping[str, Any],
    expected_relation_sha256: str,
    protocol: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(mutation_segment, Mapping)
        or mutation_segment.get("phase") not in MUTATION_PHASES
        or not isinstance(mutation_segment.get("events"), list)
        or not _is_sha256(expected_relation_sha256)
    ):
        raise AuditNoGo("mutation_boundary_segment_invalid", str(mutation_segment))
    relation_inventory = _runtime_relation_inventory(stage)
    relation_fingerprint = _relation_boundary_fingerprint(relation_inventory)
    if relation_fingerprint["sha256"] != expected_relation_sha256:
        raise AuditNoGo(
            "relation_inventory_changed",
            "runtime transition boundary",
            evidence=relation_inventory,
        )
    result = {
        "source_robot_properties": _runtime_source_robot_property_snapshot(stage, identities),
        "relation_fingerprint": relation_fingerprint,
        "mutation_segment": copy.deepcopy(dict(mutation_segment)),
        "mutation_events": copy.deepcopy(mutation_segment["events"]),
    }
    spec = (
        PROTOCOL_SPECS[(1, V1_PROTOCOL_ID)]
        if protocol is None
        else _require_protocol_spec(protocol)
    )
    if spec.get("composite_support") is True:
        static_supports = _runtime_static_support_snapshots(
            stage, identities["support_colliders"]
        )
        result["static_support_fingerprints"] = {
            path: _static_support_boundary_fingerprint(snapshot)
            for path, snapshot in static_supports.items()
        }
    else:
        result["cube"] = _runtime_cube_snapshot(stage)
    return result


def _runtime_support_transition(
    prior: str,
    sample: Mapping[str, Any],
    *,
    source_state: Mapping[str, Any],
    transition_index: int,
    observer: SupportObserverAccumulator,
) -> tuple[dict[str, Any], bool]:
    if observer.state != prior:
        raise AuditNoGo("support_observer_state_contradiction", f"{prior}:{observer.state}")
    decision = observer.consume(
        sample,
        source_state=source_state,
        transition_index=transition_index,
    )
    support = sample.get("support")
    recontact = bool(
        decision["state_before"] == "LOST"
        and isinstance(support, Mapping)
        and support.get("present") is True
    )
    return decision, recontact


def _runtime_pick_event(controller: Any, phase_before: str) -> int | None:
    if phase_before != "PICKING":
        return None
    pick = getattr(controller, "pick_controller", None)
    event = getattr(pick, "_last_emitted_event", None)
    if event is None:
        return None
    if type(event) is not int or not 0 <= event <= 6:
        raise AuditNoGo("native_pick_event_invalid", str(event))
    return event


def _runtime_pour_event(controller: Any, phase_before: str, phase_after: str) -> int | None:
    if phase_before != "POURING" and phase_after != "POURING":
        return None
    pour = getattr(controller, "pour_controller", None)
    event = getattr(pour, "_last_emitted_event", None)
    if event is None:
        return None
    if type(event) is not int or not 0 <= event <= 5:
        raise AuditNoGo("native_pour_event_invalid", str(event))
    return event


def _runtime_action_fields(action: Any, *, apply_index: int, robot: Any) -> dict[str, Any]:
    if action is None:
        return {
            "action": None,
            "canonical_action": None,
            "apply_count": 0,
            "action_receipt": None,
            "integrating_transition_index": None,
            "apply_index": None,
        }
    raw = raw_action_channels(action)
    canonical = canonicalize_action(raw)
    robot.get_articulation_controller().apply_action(action)
    return {
        "action": raw,
        "canonical_action": canonical,
        "apply_count": 1,
        "action_receipt": {
            "applied": True,
            "normal_return": True,
            "apply_count": 1,
            "action_sha256": canonical["sha256"],
        },
        "integrating_transition_index": None,
        "apply_index": apply_index,
    }


def _runtime_production_transition(
    *,
    transition_index: int,
    world: Any,
    task: Any,
    controller: Any,
    robot: Any,
    source_body: Any,
    simulation_interface: Any,
    stage_id: int,
    sdf_path_to_int: Any,
    reporter: _RuntimeFullContactReporter | None,
    contact_accumulator: ContactLifecycleAccumulator | None,
    support_observer: SupportObserverAccumulator | None,
    support_state: str,
    initial_support_observations: list[dict[str, Any]] | None,
    protocol: Mapping[str, Any] | None,
    stage: Any,
    sealed_geometry: Mapping[str, Any] | None,
    identities: Mapping[str, Any] | None,
    mutation_notice: _RuntimeMutationNotice,
    mutation_marker: int,
    relation_baseline_sha256: str,
    apply_index: int,
    video: _CompositeVideoRecorder | None,
    video_sample_every_transitions: int,
    observation_gap_sink: Any | None = None,
) -> tuple[dict[str, Any], str, int, bool]:
    before_world = _runtime_world_counter(world)
    pre = _runtime_source_state(
        source_body,
        simulation_interface=simulation_interface,
        stage_id=stage_id,
        sdf_path_to_int=sdf_path_to_int,
    )
    world_marker = mutation_notice.mark()
    world.step(render=True)
    after_world = _runtime_world_counter(world)
    if after_world != before_world + 1:
        raise RuntimeError(
            f"world_step_advance_invalid:before={before_world}:after={after_world}"
        )
    world_segment = mutation_notice.capture_since(world_marker, phase="world_step")
    contact = None
    raw_sample = None
    parsed_sample = None
    geometry = None
    raw_report = None
    post = None
    post = None
    initial_support_observation = None
    if reporter is not None:
        if (
            contact_accumulator is None
            or support_observer is None
            or initial_support_observations is None
            or protocol is None
            or sealed_geometry is None
            or identities is None
        ):
            raise AuditNoGo("instrumented_contact_setup_missing", "reporter dependencies missing")
        raw_report = reporter.sample(physics_index=transition_index)
        try:
            raw_sample = contact_accumulator.consume(
                physics_index=transition_index,
                raw=raw_report,
            )
            parsed_sample = copy.deepcopy(raw_sample)
        except ContactAuditError as exc:
            raise AuditNoGo(
                "contact_lifecycle_invalid",
                str(exc),
                evidence={
                    "raw_report": raw_report,
                    "active_pairs_before_report": [
                        list(pair) for pair in sorted(contact_accumulator.active)
                    ],
                    "recent_contact_samples": list(contact_accumulator.recent_samples),
                    "physics_index": transition_index,
                },
            ) from exc
        observation_gap = _runtime_observation_gap_journal(
            transition_index=transition_index,
            raw_report=raw_report,
            sample=raw_sample,
            protocol=protocol,
        )
        if observation_gap is not None and observation_gap_sink is not None:
            observation_gap_sink(observation_gap)
        geometry = _runtime_live_geometry(stage, sealed_geometry)
        post = _runtime_source_state(
            source_body,
            simulation_interface=simulation_interface,
            stage_id=stage_id,
            sdf_path_to_int=sdf_path_to_int,
        )
        topology = evaluate_sidewall_topology(
            raw_sample,
            geometry=geometry,
            identities=identities,
            protocol=protocol,
        )
        if not topology["audit_valid"]:
            raise AuditNoGo(
                "contact_topology_authority_invalid",
                json.dumps(topology["audit_failures"], sort_keys=True),
                evidence={
                    "raw_report": raw_report,
                    "parser_sample": parsed_sample,
                    "geometry": geometry,
                    "post": post,
                    "topology": topology,
                    "observation_gap_journal": observation_gap,
                },
            )
        raw_sample["topology"] = topology
        try:
            _apply_contact_physical_evidence(raw_sample, protocol=protocol)
        except (TypeError, ValueError) as exc:
            raise AuditNoGo(
                "contact_load_bearing_authority_missing"
                if _contact_load_bearing_policy(protocol)
                else "contact_physical_evidence_invalid",
                str(exc),
                evidence={
                    "raw_report": raw_report,
                    "parser_sample": parsed_sample,
                    "geometry": geometry,
                    "topology": topology,
                    "observation_gap_journal": observation_gap,
                },
            ) from exc
    if post is None:
        post = _runtime_source_state(
            source_body,
            simulation_interface=simulation_interface,
            stage_id=stage_id,
            sdf_path_to_int=sdf_path_to_int,
        )
    if raw_sample is not None:
        observer_decision, recontact = _runtime_support_transition(
            support_state,
            raw_sample,
            source_state=post,
            transition_index=transition_index,
            observer=support_observer,
        )
        support_state = observer_decision["state"]
        if observer_decision["state_before"] in {"UNKNOWN", "UNOBSERVED"}:
            initial_support_observation = {
                "transition_index": transition_index,
                "world_index": after_world,
                "pre": copy.deepcopy(pre),
                "post": copy.deepcopy(post),
                "raw_report": copy.deepcopy(raw_report),
                "sample": parsed_sample,
                "observer": copy.deepcopy(observer_decision),
                "action_context": {
                    "pick_event": None,
                    "action": None,
                    "apply_count": 0,
                    "action_receipt": None,
                    "close_gate": {"audit_no_go_code": None},
                },
            }
            initial_support_observations.append(initial_support_observation)
        if observer_decision["audit_no_go_code"] is not None:
            failure_evidence = (
                build_initial_support_failure_evidence(
                    protocol=protocol,
                    code=observer_decision["audit_no_go_code"],
                    observations=initial_support_observations,
                )
                if initial_support_observation is not None
                else {"raw_report": raw_report, "sample": raw_sample}
            )
            raise AuditNoGo(
                observer_decision["audit_no_go_code"],
                json.dumps(observer_decision, sort_keys=True),
                evidence=failure_evidence,
            )
        contact = {
            "raw_report": raw_report,
            "geometry": geometry,
            **_runtime_contact_summary(
                raw_sample,
                source_awake=post["awake"],
                observer_decision=observer_decision,
                protocol=protocol,
            ),
            "source_support_recontact": recontact,
        }
    boundary_after_world = _runtime_transition_boundary(
        stage,
        identities=identities,
        mutation_segment=world_segment,
        expected_relation_sha256=relation_baseline_sha256,
        protocol=protocol,
    )
    phase_before = str(getattr(getattr(controller, "current_phase", None), "name", "UNKNOWN"))
    task_marker = mutation_notice.mark()
    state = task.step()
    task_segment = mutation_notice.capture_since(task_marker, phase="task")
    boundary_after_task = _runtime_transition_boundary(
        stage,
        identities=identities,
        mutation_segment=task_segment,
        expected_relation_sha256=relation_baseline_sha256,
        protocol=protocol,
    )
    action = None
    done = False
    success = False
    controller_calls = 0
    controller_marker = mutation_notice.mark()
    if state is not None:
        result = controller.step(state)
        controller_calls = 1
        if not isinstance(result, tuple) or len(result) != 3:
            raise RuntimeError("controller_return_contract_invalid")
        action, done, success = result
        if type(done) is not bool or type(success) is not bool:
            raise RuntimeError("controller_return_flags_invalid")
    controller_segment = mutation_notice.capture_since(
        controller_marker, phase="controller"
    )
    phase_after = str(getattr(getattr(controller, "current_phase", None), "name", "UNKNOWN"))
    pick_event = _runtime_pick_event(controller, phase_before) if state is not None else None
    pour_event = _runtime_pour_event(controller, phase_before, phase_after) if state is not None else None
    boundary_after_controller = _runtime_transition_boundary(
        stage,
        identities=identities,
        mutation_segment=controller_segment,
        expected_relation_sha256=relation_baseline_sha256,
        protocol=protocol,
    )
    action_marker = mutation_notice.mark()
    action_fields = _runtime_action_fields(action, apply_index=apply_index, robot=robot)
    if action is not None:
        action_fields["integrating_transition_index"] = transition_index + 1
        apply_index += 1
    action_segment = mutation_notice.capture_since(action_marker, phase="action")
    boundary_after_action = _runtime_transition_boundary(
        stage,
        identities=identities,
        mutation_segment=action_segment,
        expected_relation_sha256=relation_baseline_sha256,
        protocol=protocol,
    )
    if (
        support_observer is not None
        and protocol is not None
        and protocol["initial_support_activation_max_absent_reports"] > 0
    ):
        close_gate = support_observer.observe_action(
            pick_event=pick_event,
            action=action_fields["action"],
            apply_count=action_fields["apply_count"],
            action_receipt=action_fields["action_receipt"],
            classifications=raw_sample.get("classifications") if raw_sample is not None else None,
            sample=raw_sample,
        )
        if raw_sample is not None:
            observer_decision["prefix_physical_failures"] = (
                support_observer.prefix_physical_failures
            )
            if contact is not None:
                contact["support_observer"] = copy.deepcopy(observer_decision)
                contact["initial_support_prefix_physical_failures"] = copy.deepcopy(
                    observer_decision["prefix_physical_failures"]
                )
        if initial_support_observation is not None:
            initial_support_observation["observer"] = copy.deepcopy(observer_decision)
            initial_support_observation["action_context"] = {
                "pick_event": pick_event,
                "action": copy.deepcopy(action_fields["action"]),
                "apply_count": action_fields["apply_count"],
                "action_receipt": copy.deepcopy(action_fields["action_receipt"]),
                "close_gate": copy.deepcopy(close_gate),
            }
        if close_gate["audit_no_go_code"] is not None:
            if initial_support_observations is None:
                raise AuditNoGo("instrumented_contact_setup_missing", "support observations missing")
            raise AuditNoGo(
                close_gate["audit_no_go_code"],
                json.dumps(close_gate, sort_keys=True),
                evidence=build_initial_support_failure_evidence(
                    protocol=protocol,
                    code=close_gate["audit_no_go_code"],
                    observations=initial_support_observations,
                ),
            )
    if (
        video is not None
        and transition_index % video_sample_every_transitions == 0
        and isinstance(state, Mapping)
    ):
        video.capture(
            state.get("camera_display", {}),
            transition_index=transition_index,
            world_index=after_world,
        )
    if not done and (
        world.is_stopped() or task.need_reset() or controller.need_reset()
    ):
        raise RuntimeError(
            "unexpected_reset_or_world_stop:"
            f"stopped={world.is_stopped()}:task={task.need_reset()}:controller={controller.need_reset()}"
        )
    record = {
        "transition_index": transition_index,
        "world_index": after_world,
        "pre": pre,
        "post": post,
        "state_present": state is not None,
        "controller_call_count": controller_calls,
        "phase_before": phase_before,
        "phase_after": phase_after,
        "pick_event": pick_event,
        "pour_event": pour_event,
        "continuation_index": None,
        "production_terminal": bool(done),
        "terminal_outcome": phase_after if done else None,
        "terminal_success": success if done else None,
        "contact": contact,
        "boundaries": {
            "after_world": boundary_after_world,
            "after_task": boundary_after_task,
            "after_controller": boundary_after_controller,
            "after_action": boundary_after_action,
        },
        **action_fields,
    }
    return record, support_state, apply_index, bool(done)


def _runtime_continuation_transition(
    *,
    transition_index: int,
    continuation_index: int,
    world: Any,
    source_body: Any,
    simulation_interface: Any,
    stage_id: int,
    sdf_path_to_int: Any,
    reporter: _RuntimeFullContactReporter | None,
    contact_accumulator: ContactLifecycleAccumulator | None,
    support_observer: SupportObserverAccumulator | None,
    support_state: str,
    initial_support_observations: list[dict[str, Any]] | None,
    protocol: Mapping[str, Any] | None,
    stage: Any,
    sealed_geometry: Mapping[str, Any] | None,
    identities: Mapping[str, Any] | None,
    mutation_notice: _RuntimeMutationNotice,
    mutation_marker: int,
    relation_baseline_sha256: str,
    terminal_phase: str,
    observation_gap_sink: Any | None = None,
) -> tuple[dict[str, Any], str]:
    before_world = _runtime_world_counter(world)
    pre = _runtime_source_state(
        source_body,
        simulation_interface=simulation_interface,
        stage_id=stage_id,
        sdf_path_to_int=sdf_path_to_int,
    )
    world_marker = mutation_notice.mark()
    world.step(render=True)
    after_world = _runtime_world_counter(world)
    if after_world != before_world + 1:
        raise RuntimeError("continuation_world_step_invalid")
    world_segment = mutation_notice.capture_since(world_marker, phase="world_step")
    contact = None
    raw_sample = None
    parsed_sample = None
    geometry = None
    raw_report = None
    if reporter is not None:
        if (
            contact_accumulator is None
            or support_observer is None
            or initial_support_observations is None
            or protocol is None
            or sealed_geometry is None
            or identities is None
        ):
            raise AuditNoGo("instrumented_contact_setup_missing", "continuation dependencies")
        raw_report = reporter.sample(physics_index=transition_index)
        try:
            raw_sample = contact_accumulator.consume(
                physics_index=transition_index,
                raw=raw_report,
            )
            parsed_sample = copy.deepcopy(raw_sample)
        except ContactAuditError as exc:
            raise AuditNoGo(
                "contact_lifecycle_invalid",
                str(exc),
                evidence={
                    "raw_report": raw_report,
                    "active_pairs_before_report": [
                        list(pair) for pair in sorted(contact_accumulator.active)
                    ],
                    "recent_contact_samples": list(contact_accumulator.recent_samples),
                    "physics_index": transition_index,
                },
            ) from exc
        observation_gap = _runtime_observation_gap_journal(
            transition_index=transition_index,
            raw_report=raw_report,
            sample=raw_sample,
            protocol=protocol,
        )
        if observation_gap is not None and observation_gap_sink is not None:
            observation_gap_sink(observation_gap)
        geometry = _runtime_live_geometry(stage, sealed_geometry)
        post = _runtime_source_state(
            source_body,
            simulation_interface=simulation_interface,
            stage_id=stage_id,
            sdf_path_to_int=sdf_path_to_int,
        )
        topology = evaluate_sidewall_topology(
            raw_sample,
            geometry=geometry,
            identities=identities,
            protocol=protocol,
        )
        if not topology["audit_valid"]:
            raise AuditNoGo(
                "contact_topology_authority_invalid",
                "continuation",
                evidence={
                    "raw_report": raw_report,
                    "parser_sample": parsed_sample,
                    "geometry": geometry,
                    "post": post,
                    "topology": topology,
                    "observation_gap_journal": observation_gap,
                },
            )
        raw_sample["topology"] = topology
        try:
            _apply_contact_physical_evidence(raw_sample, protocol=protocol)
        except (TypeError, ValueError) as exc:
            raise AuditNoGo(
                "contact_load_bearing_authority_missing"
                if _contact_load_bearing_policy(protocol)
                else "contact_physical_evidence_invalid",
                str(exc),
                evidence={
                    "raw_report": raw_report,
                    "parser_sample": parsed_sample,
                    "geometry": geometry,
                    "topology": topology,
                    "observation_gap_journal": observation_gap,
                },
            ) from exc
    if post is None:
        post = _runtime_source_state(
            source_body,
            simulation_interface=simulation_interface,
            stage_id=stage_id,
            sdf_path_to_int=sdf_path_to_int,
        )
    if raw_sample is not None:
        observer_decision, recontact = _runtime_support_transition(
            support_state,
            raw_sample,
            source_state=post,
            transition_index=transition_index,
            observer=support_observer,
        )
        support_state = observer_decision["state"]
        if observer_decision["state_before"] in {"UNKNOWN", "UNOBSERVED"}:
            initial_support_observations.append(
                {
                    "transition_index": transition_index,
                    "world_index": after_world,
                    "pre": copy.deepcopy(pre),
                    "post": copy.deepcopy(post),
                    "raw_report": copy.deepcopy(raw_report),
                    "sample": parsed_sample,
                    "observer": copy.deepcopy(observer_decision),
                    "action_context": {
                        "pick_event": None,
                        "action": None,
                        "apply_count": 0,
                        "action_receipt": None,
                        "close_gate": {"audit_no_go_code": None},
                    },
                }
            )
        if observer_decision["audit_no_go_code"] is not None:
            failure_evidence = (
                build_initial_support_failure_evidence(
                    protocol=protocol,
                    code=observer_decision["audit_no_go_code"],
                    observations=initial_support_observations,
                )
                if observer_decision["state_before"] in {"UNKNOWN", "UNOBSERVED"}
                else {"raw_report": raw_report, "sample": raw_sample}
            )
            raise AuditNoGo(
                observer_decision["audit_no_go_code"],
                json.dumps(observer_decision, sort_keys=True),
                evidence=failure_evidence,
            )
        contact = {
            "raw_report": raw_report,
            "geometry": geometry,
            **_runtime_contact_summary(
                raw_sample,
                source_awake=post["awake"],
                observer_decision=observer_decision,
                protocol=protocol,
            ),
            "source_support_recontact": recontact,
        }
    boundary = _runtime_transition_boundary(
        stage,
        identities=identities,
        mutation_segment=world_segment,
        expected_relation_sha256=relation_baseline_sha256,
        protocol=protocol,
    )
    return (
        {
            "transition_index": transition_index,
            "world_index": after_world,
            "pre": pre,
            "post": post,
            "state_present": False,
            "controller_call_count": 0,
            "phase_before": terminal_phase,
            "phase_after": terminal_phase,
            "pick_event": None,
            "pour_event": None,
            "action": None,
            "canonical_action": None,
            "apply_count": 0,
            "action_receipt": None,
            "integrating_transition_index": None,
            "apply_index": None,
            "continuation_index": continuation_index,
            "production_terminal": False,
            "terminal_outcome": None,
            "terminal_success": None,
            "contact": contact,
            "boundaries": {"continuation": boundary},
        },
        support_state,
    )


def _runtime_execute_trajectory(
    *,
    world: Any,
    task: Any,
    controller: Any,
    robot: Any,
    source_body: Any,
    simulation_interface: Any,
    stage_id: int,
    sdf_path_to_int: Any,
    reporter: _RuntimeFullContactReporter | None,
    contact_accumulator: ContactLifecycleAccumulator | None,
    support_observer: SupportObserverAccumulator | None,
    protocol: Mapping[str, Any] | None,
    stage: Any,
    sealed_geometry: Mapping[str, Any] | None,
    identities: Mapping[str, Any],
    mutation_notice: _RuntimeMutationNotice,
    mutation_marker: int,
    relation_baseline_sha256: str,
    maximum_steps: int,
    retention_steps: int,
    rise_threshold_m: float,
    video: _CompositeVideoRecorder | None,
    video_sample_every_transitions: int,
    transition_sink: Any | None = None,
    observation_gap_sink: Any | None = None,
) -> dict[str, Any]:
    if transition_sink is not None and not callable(transition_sink):
        raise ValueError("runtime_transition_sink_invalid")
    if observation_gap_sink is not None and not callable(observation_gap_sink):
        raise ValueError("runtime_observation_gap_sink_invalid")
    transitions = []
    support_state = "UNKNOWN"
    apply_index = 0
    terminal = False
    terminal_phase = "UNKNOWN"
    terminal_success = None
    lift_action_index = None
    lift_baseline_z = None
    rise_index = None
    initial_support_observations: list[dict[str, Any]] = []
    for transition_index in range(maximum_steps):
        record, support_state, apply_index, done = _runtime_production_transition(
            transition_index=transition_index,
            world=world,
            task=task,
            controller=controller,
            robot=robot,
            source_body=source_body,
            simulation_interface=simulation_interface,
            stage_id=stage_id,
            sdf_path_to_int=sdf_path_to_int,
            reporter=reporter,
            contact_accumulator=contact_accumulator,
            support_observer=support_observer,
            support_state=support_state,
            initial_support_observations=initial_support_observations,
            protocol=protocol,
            stage=stage,
            sealed_geometry=sealed_geometry,
            identities=identities,
            mutation_notice=mutation_notice,
            mutation_marker=mutation_marker,
            relation_baseline_sha256=relation_baseline_sha256,
            apply_index=apply_index,
            video=video,
            video_sample_every_transitions=video_sample_every_transitions,
            observation_gap_sink=observation_gap_sink,
        )
        transitions.append(record)
        if transition_sink is not None:
            transition_sink(record)
        if record["pick_event"] == 5 and record["action"] is not None and lift_action_index is None:
            lift_action_index = transition_index
        if lift_action_index is not None and transition_index == lift_action_index + 1:
            lift_baseline_z = float(record["pre"]["origin_m"][2])
        if (
            lift_baseline_z is not None
            and rise_index is None
            and float(record["post"]["origin_m"][2] - lift_baseline_z)
            >= rise_threshold_m
        ):
            rise_index = transition_index
        if done:
            terminal = True
            terminal_phase = record["phase_after"]
            terminal_success = record["terminal_success"]
            break
    if terminal and rise_index is not None:
        continuation_index = 0
        while len(transitions) < rise_index + retention_steps:
            record, support_state = _runtime_continuation_transition(
                transition_index=len(transitions),
                continuation_index=continuation_index,
                world=world,
                source_body=source_body,
                simulation_interface=simulation_interface,
                stage_id=stage_id,
                sdf_path_to_int=sdf_path_to_int,
                reporter=reporter,
                contact_accumulator=contact_accumulator,
                support_observer=support_observer,
                support_state=support_state,
                initial_support_observations=initial_support_observations,
                protocol=protocol,
                stage=stage,
                sealed_geometry=sealed_geometry,
                identities=identities,
                mutation_notice=mutation_notice,
                mutation_marker=mutation_marker,
                relation_baseline_sha256=relation_baseline_sha256,
                terminal_phase=terminal_phase,
                observation_gap_sink=observation_gap_sink,
            )
            transitions.append(record)
            if transition_sink is not None:
                transition_sink(record)
            continuation_index += 1
    return {
        "transitions": transitions,
        "terminal": terminal,
        "terminal_phase": terminal_phase if terminal else None,
        "terminal_success": terminal_success if terminal else None,
        "maximum_transitions_reached": not terminal,
        "lift_action_index": lift_action_index,
        "rise_index": rise_index,
    }


def _artifact_record(path: Path, *, relative_to: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve().relative_to(relative_to.resolve())),
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _runtime_identity(
    *,
    config_sha256: str,
    static_identity: Mapping[str, Any],
    scene: Mapping[str, Any],
    dependency_closure: Mapping[str, Any],
    local_franka: Mapping[str, Any],
    runtime_version: Mapping[str, Any],
    report_layer: Mapping[str, Any] | None,
) -> dict[str, Any]:
    local_franka_closure = local_franka.get("dependency_closure")
    payload = {
        "config_sha256": config_sha256,
        "parent_static_identity_sha256": static_identity.get("identity_sha256"),
        "scene": copy.deepcopy(dict(scene)),
        "dependency_closure_sha256": dependency_closure.get("sha256"),
        "dependency_entry_sha256": dependency_closure.get("entry_sha256"),
        "local_franka_root_usd_path": local_franka.get("root_usd_path"),
        "local_franka_root_sha256": local_franka.get("root_sha256"),
        "local_franka_dependency_closure_sha256": (
            local_franka_closure.get("sha256")
            if isinstance(local_franka_closure, Mapping)
            else None
        ),
        "local_franka_sha256": local_franka.get("sha256"),
        "runtime_version_sha256": runtime_version.get("sha256"),
        "report_layer_catalog_sha256": (
            None if report_layer is None else report_layer.get("catalog", {}).get("sha256")
        ),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _runtime_child_execute(
    args: argparse.Namespace,
    *,
    app: Any,
    isaacsim_module: Any,
    omni_usd: Any,
    world_type: Any,
    kit_app: Any,
    rigid_prim_view_type: Any,
    add_reference_to_stage: Any,
    get_stage_units: Any,
    omega_conf: Any,
    get_simulation_interface: Any,
    resolve_path: Any,
    sdf_path_to_int: Any,
    stage_cache: Any,
    create_robot: Any,
    create_task: Any,
    create_controller: Any,
    object_utils_type: Any,
    diagnostics: _RuntimeDiagnosticEmitter | None = None,
) -> int:
    diagnostics = diagnostics or _RuntimeDiagnosticEmitter()
    child_pid = os.getpid()
    run_id = secrets.token_hex(16)
    trace_records: list[dict[str, Any]] = []
    runtime_evidence: dict[str, Any] = {}
    controller = None
    world = None
    audit = None
    mutation_notice = None
    video = None
    report_layer = None
    mutation_marker: int | None = None
    measurement_writer_audit: dict[str, Any] | None = None
    report_written = False
    cleanup_written = False
    exit_code = 1
    report: dict[str, Any]
    try:
        if Path.cwd().resolve() != args.out_dir.resolve():
            raise RuntimeError("child_working_directory_mismatch")
        if os.getppid() != args.parent_pid:
            raise RuntimeError(
                f"child_parent_pid_mismatch:actual={os.getppid()}:expected={args.parent_pid}"
            )
        frozen_bytes = args.frozen_config.read_bytes()
        if _sha256_bytes(frozen_bytes) != args.expected_config_sha256:
            raise RuntimeError("child_frozen_config_sha256_mismatch")
        if not frozen_bytes.endswith(b"\n") or b"\r" in frozen_bytes:
            raise RuntimeError("child_frozen_config_format_invalid")
        config = _decode_strict_json_line(frozen_bytes[:-1])
        if _canonical_json_bytes(config) != frozen_bytes:
            raise RuntimeError("child_frozen_config_not_canonical")
        diagnostic = _require_pinned_diagnostic(config)
        protocol = _protocol_spec_for_diagnostic(diagnostic)
        local_franka_asset = resolve_local_franka_asset(diagnostic)
        local_scene_asset = resolve_local_scene_asset(diagnostic)
        if config.get("max_episodes") != 1 or not isinstance(config.get("robot"), Mapping):
            raise RuntimeError("child_frozen_config_contract_mismatch")
        child_static_identity_pre = build_parent_identity(config)
        if child_static_identity_pre.get("config_sha256") != args.expected_config_sha256:
            raise AuditNoGo("child_static_identity_config_mismatch", "frozen config hash")
        runtime_version = _runtime_version_identity(
            isaacsim_module,
            kit_app=kit_app,
            expected_version=str(diagnostic["isaac_sim_version"]),
        )
        stage = omni_usd.get_context().get_stage()
        world = world_type(
            stage_units_in_meters=float(diagnostic["stage_units_in_meters"]),
            physics_prim_path=str(diagnostic["physics_scene_path"]),
            backend="numpy",
        )
        simulation_interface = get_simulation_interface()
        if not math.isclose(
            float(world.get_physics_dt()),
            float(diagnostic["physics_dt"]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise AuditNoGo("physics_dt_mismatch", str(world.get_physics_dt()))
        if not math.isclose(
            float(get_stage_units()),
            float(diagnostic["stage_units_in_meters"]),
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise AuditNoGo("stage_units_mismatch", str(get_stage_units()))
        robot = create_diagnostic_local_franka(
            create_robot,
            config,
            local_franka=local_franka_asset,
        )
        asset_path = Path(local_scene_asset["absolute_usd_path"])
        add_reference_to_stage(usd_path=str(asset_path), prim_path="/World")
        object_utils = object_utils_type.get_instance(stage)
        if args.treatment == "instrumented":
            report_layer = _runtime_install_report_layer(
                stage,
                simulation_interface=simulation_interface,
                world=world,
            )
        stage_id = int(stage_cache.Insert(stage).ToLongInt())
        source_local_com_authority = _runtime_source_local_com_authority(
            app,
            stage,
            stage_id=stage_id,
            world=world,
        )
        mutation_notice = _RuntimeMutationNotice(stage)
        static_production_closure = _static_production_closure_audit(diagnostic)
        if not static_production_closure["audit_valid"]:
            raise AuditNoGo(
                "static_production_closure_audit_invalid",
                json.dumps(static_production_closure["audit_failures"], sort_keys=True),
                evidence=static_production_closure,
            )
        audit = _RuntimeWriteAudit()
        audit.set_static_production_closure(static_production_closure)
        audit.activate_mutation_notice()
        audit.audit_callable(
            object_utils,
            "set_object_position",
            surface="object_utils_set_object_position",
            count="root_body_pose_velocity",
            source_scoped=True,
            required="object_utils_set_object_position"
            in static_production_closure["required_runtime_surfaces"],
        )
        identities = {
            "stage_id": stage_id,
            **_runtime_contact_identities(stage, diagnostic=diagnostic),
        }
        source_properties_before_reset = _runtime_source_robot_property_snapshot(
            stage, identities
        )
        cube_before_reset = _runtime_cube_snapshot(stage)
        static_supports_before_reset = (
            _runtime_static_support_snapshots(stage, identities["support_colliders"])
            if protocol.get("composite_support") is True
            else None
        )
        relation_before_reset = _runtime_relation_inventory(stage)
        relation_before_evaluation = evaluate_coupling_inventory(relation_before_reset)
        if not relation_before_evaluation["audit_valid"]:
            raise AuditNoGo(
                "pre_reset_coupling_inventory_invalid",
                json.dumps(relation_before_evaluation["audit_failures"], sort_keys=True),
                evidence=relation_before_reset,
            )
        pre_reset_marker = mutation_notice.mark()
        cfg = omega_conf.create(config)
        task = create_task(
            str(config["task_type"]),
            cfg=cfg,
            world=world,
            stage=stage,
            robot=robot,
        )
        np.random.seed(int(diagnostic["numpy_seed"]))
        task.reset()
        controller = create_controller(str(config["controller_type"]), cfg=cfg, robot=robot)
        pre_reset_segment = mutation_notice.capture_since(
            pre_reset_marker, phase="pre_reset"
        )
        if audit.reset_root_write_count != 1:
            raise AuditNoGo(
                "reset_root_write_count_invalid", str(audit.reset_root_write_count)
            )
        source_body = RuntimeReadOnlySourceAdapter(rigid_prim_view_type, SOURCE_BODY_PATH)
        source_body.initialize()
        initial_source_state = _runtime_source_state(
            source_body,
            simulation_interface=simulation_interface,
            stage_id=stage_id,
            sdf_path_to_int=sdf_path_to_int,
        )
        scene = _runtime_scene_identity(stage, world, diagnostic=diagnostic)
        if not scene["valid"]:
            raise AuditNoGo("scene_contract_mismatch", json.dumps(scene, sort_keys=True))
        source_contract = _runtime_source_contract(
            stage,
            initial_source_state,
            stage_id=stage_id,
            source_adapter=source_body,
            source_local_com_authority=source_local_com_authority,
            active_scene=scene,
        )
        source_contract_evaluation = evaluate_dynamic_source_contract(source_contract)
        if not source_contract_evaluation["audit_valid"]:
            raise AuditNoGo(
                "source_contract_invalid",
                json.dumps(source_contract_evaluation["audit_failures"], sort_keys=True),
                evidence=source_contract,
        )
        dynamic_body_paths = _runtime_dynamic_body_paths(stage)
        left_bounds = {
            path: _runtime_bound(stage, path) for path in identities["left_colliders"]
        }
        right_bounds = {
            path: _runtime_bound(stage, path) for path in identities["right_colliders"]
        }
        sealed_geometry = {
            "gravity_world_m_s2": copy.deepcopy(diagnostic["gravity_world_m_s2"]),
            "source": _runtime_bound(stage, SOURCE_BODY_PATH),
            "source_reset_world_from_local": _runtime_bound(stage, SOURCE_BODY_PATH)[
                "world_from_local"
            ],
            "finger_colliders": {**left_bounds, **right_bounds},
            "normalized_height_range": copy.deepcopy(
                diagnostic["topology"]["normalized_height_range"]
            ),
            "pad_edge_margin_m": float(diagnostic["topology"]["pad_edge_margin_m"]),
            "inward_face_distance_tolerance_m": float(
                diagnostic["topology"].get("inward_face_distance_tolerance_m", 0.005)
            ),
            "maximum_vertical_normal_cosine": float(
                diagnostic["topology"]["maximum_vertical_normal_cosine"]
            ),
            "minimum_inward_face_cosine": float(
                diagnostic["topology"]["minimum_inward_face_cosine"]
            ),
        }
        _source_local_up(sealed_geometry)
        dependency_closure = _runtime_dependency_closure(asset_path)
        if dependency_closure["unresolved"]:
            raise AuditNoGo(
                "usd_dependency_closure_unresolved",
                json.dumps(dependency_closure["unresolved"], sort_keys=True),
            )
        if (
            dependency_closure.get("entry_sha256")
            != child_static_identity_pre.get("asset_dependency_closure", {}).get("entry_sha256")
        ):
            raise AuditNoGo("runtime_asset_entry_hash_mismatch", "preflight")
        if child_static_identity_pre.get("local_franka") != local_franka_asset:
            raise AuditNoGo("local_franka_parent_binding_invalid", "preflight")
        if child_static_identity_pre.get("local_scene") != local_scene_asset:
            raise AuditNoGo("local_scene_parent_binding_invalid", "preflight")
        franka_dependency_closure = _runtime_dependency_closure(
            Path(local_franka_asset["absolute_usd_path"])
        )
        franka_identity = _runtime_local_franka_identity(
            stage,
            robot,
            local_franka=local_franka_asset,
            dependency_closure=franka_dependency_closure,
        )
        source_properties_after_reset = _runtime_source_robot_property_snapshot(stage, identities)
        cube_after_reset = _runtime_cube_snapshot(stage)
        static_supports_after_reset = (
            _runtime_static_support_snapshots(stage, identities["support_colliders"])
            if protocol.get("composite_support") is True
            else None
        )
        relation_after_reset = _runtime_relation_inventory(stage)
        relation_after_reset_sha256 = _relation_inventory_sha256(relation_after_reset)
        reset_relation_evaluation = evaluate_reset_coupling_inventories(
            relation_before_reset, relation_after_reset
        )
        if not reset_relation_evaluation["audit_valid"]:
            raise AuditNoGo(
                "post_reset_coupling_inventory_invalid",
                json.dumps(reset_relation_evaluation["audit_failures"], sort_keys=True),
                evidence={
                    "before_reset": relation_before_reset,
                    "after_reset": relation_after_reset,
                },
            )
        _install_runtime_write_audit(
            audit,
            source_adapter=source_body,
            controller=controller,
            object_utils=object_utils,
            static_production_closure=static_production_closure,
        )
        mutation_marker = mutation_notice.mark()
        audit.open_epoch()
        reporter = None
        accumulator = None
        support_observer = None
        if args.treatment == "instrumented":
            reporter = _RuntimeFullContactReporter(
                simulation_interface=simulation_interface,
                resolve_path=resolve_path,
            )
            accumulator = ContactLifecycleAccumulator(identities, protocol=protocol)
            support_observer = SupportObserverAccumulator(protocol=protocol)
            video = _CompositeVideoRecorder(
                output_path=args.out_dir / VIDEO_BASENAME,
                frame_map_path=args.out_dir / VIDEO_MAP_BASENAME,
                fps=float(diagnostic["video"]["fps"]),
                camera_names=diagnostic["video"]["camera_names"],
                treatment=args.treatment,
                run_nonce=args.run_nonce,
                parent_pid=args.parent_pid,
                child_pid=child_pid,
                run_id=run_id,
            )
        runtime_identity_pre = _runtime_identity(
            config_sha256=args.expected_config_sha256,
            static_identity=child_static_identity_pre,
            scene=scene,
            dependency_closure=dependency_closure,
            local_franka=franka_identity,
            runtime_version=runtime_version,
            report_layer=report_layer,
        )
        runtime_evidence.update(
            {
                "protocol": protocol,
                "child_static_identity_pre": child_static_identity_pre,
                "runtime_version": runtime_version,
                "scene": scene,
                "source_contract": source_contract,
                "source_contract_evaluation": source_contract_evaluation,
                "source_local_com_authority": source_local_com_authority,
                "contact_identities": identities,
                "known_dynamic_body_paths": dynamic_body_paths,
                "sealed_geometry": sealed_geometry,
                "dependency_closure": dependency_closure,
                "local_scene": local_scene_asset,
                "local_franka": franka_identity,
                "report_layer": (
                    None
                    if report_layer is None
                    else {
                        key: value
                        for key, value in report_layer.items()
                        if key != "layer"
                    }
                ),
                "source_properties_before_reset": source_properties_before_reset,
                "source_properties_after_reset": source_properties_after_reset,
                "cube_baseline": cube_before_reset,
                "cube_after_reset": cube_after_reset,
                "relation_before_reset": relation_before_reset,
                "relation_after_reset": relation_after_reset,
                "pre_reset_mutation_events": copy.deepcopy(pre_reset_segment["events"]),
                "static_production_closure": static_production_closure,
                "runtime_identity_pre": runtime_identity_pre,
                **(
                    {
                        "static_supports_baseline": static_supports_before_reset,
                        "static_supports_after_reset": static_supports_after_reset,
                    }
                    if static_supports_before_reset is not None
                    else {}
                ),
            }
        )
        trace_records.append(
            make_trace_record(
                trace_records,
                treatment=args.treatment,
                run_nonce=args.run_nonce,
                parent_pid=args.parent_pid,
                child_pid=child_pid,
                run_id=run_id,
                kind="bootstrap",
                payload={"runtime_evidence": runtime_evidence},
            )
        )

        def append_transition(transition: Mapping[str, Any]) -> None:
            trace_records.append(
                make_trace_record(
                    trace_records,
                    treatment=args.treatment,
                    run_nonce=args.run_nonce,
                    parent_pid=args.parent_pid,
                    child_pid=child_pid,
                    run_id=run_id,
                    kind="transition",
                    payload=transition,
                )
            )

        def append_observation_gap(observation_gap: Mapping[str, Any]) -> None:
            trace_records.append(
                make_trace_record(
                    trace_records,
                    treatment=args.treatment,
                    run_nonce=args.run_nonce,
                    parent_pid=args.parent_pid,
                    child_pid=child_pid,
                    run_id=run_id,
                    kind="observation_gap",
                    payload=observation_gap,
                )
            )

        with diagnostics.phase("trajectory.execute"):
            trajectory = _runtime_execute_trajectory(
                world=world,
                task=task,
                controller=controller,
                robot=robot,
                source_body=source_body,
                simulation_interface=simulation_interface,
                stage_id=stage_id,
                sdf_path_to_int=sdf_path_to_int,
                reporter=reporter,
                contact_accumulator=accumulator,
                support_observer=support_observer,
                protocol=protocol,
                stage=stage,
                sealed_geometry=sealed_geometry if reporter is not None else None,
                identities=identities,
                mutation_notice=mutation_notice,
                mutation_marker=mutation_marker,
                relation_baseline_sha256=relation_after_reset_sha256,
                maximum_steps=int(diagnostic["maximum_production_steps"]),
                retention_steps=int(diagnostic["retention_steps"]),
                rise_threshold_m=float(diagnostic["rise_threshold_m"]),
                video=video,
                video_sample_every_transitions=int(
                    diagnostic["video"]["sample_every_transitions"]
                ),
                transition_sink=append_transition,
                observation_gap_sink=append_observation_gap,
            )
        video_artifacts = None
        with diagnostics.phase("finalization.video.close"):
            if video is not None:
                video_artifacts = video.close()
        with diagnostics.phase("finalization.report_layer.audit"):
            if report_layer is not None:
                post_catalog = _runtime_layer_catalog(report_layer["layer"])
                post_validation = validate_report_only_layer_catalog(post_catalog)
                if not post_validation["audit_valid"] or post_catalog != report_layer["catalog"]:
                    raise AuditNoGo(
                        "report_layer_changed_during_run",
                        json.dumps(post_validation["audit_failures"], sort_keys=True),
                        evidence=post_catalog,
                    )
                report_layer["post_catalog"] = post_catalog
                runtime_evidence["report_layer"]["post_catalog"] = post_catalog
        with diagnostics.phase("finalization.postflight.identity"):
            post_scene = _runtime_scene_identity(stage, world, diagnostic=diagnostic)
            post_dependency = _runtime_dependency_closure(asset_path)
            post_franka_dependency_closure = _runtime_dependency_closure(
                Path(local_franka_asset["absolute_usd_path"])
            )
            post_franka = _runtime_local_franka_identity(
                stage,
                robot,
                local_franka=local_franka_asset,
                dependency_closure=post_franka_dependency_closure,
            )
            child_static_identity_post = build_parent_identity(config)
            if child_static_identity_post != child_static_identity_pre:
                raise AuditNoGo("child_static_identity_changed", "runner or implementation changed")
            if (
                post_dependency.get("entry_sha256")
                != child_static_identity_post.get("asset_dependency_closure", {}).get("entry_sha256")
            ):
                raise AuditNoGo("runtime_asset_entry_hash_mismatch", "postflight")
            runtime_identity_post = _runtime_identity(
                config_sha256=args.expected_config_sha256,
                static_identity=child_static_identity_post,
                scene=post_scene,
                dependency_closure=post_dependency,
                local_franka=post_franka,
                runtime_version=runtime_version,
                report_layer=report_layer,
            )
            if runtime_identity_post != runtime_identity_pre:
                raise AuditNoGo("runtime_identity_changed", "pre/post runtime identity differs")
        with diagnostics.phase("finalization.writer.audit"):
            mutation_ledger = mutation_notice.ledger()
            zero_epoch_mutation_events = [
                event
                for segment in mutation_ledger
                if segment["phase"] != "pre_reset"
                for event in segment["events"]
            ]
            measurement_writer_audit = audit.report(
                mutation_notice_active=True,
                mutation_events=[],
            )
            writer_evaluation = evaluate_writer_target_force_gripper_audit(
                measurement_writer_audit
            )
            if not writer_evaluation["audit_valid"]:
                raise AuditNoGo(
                    "writer_audit_invalid",
                    json.dumps(writer_evaluation["audit_failures"], sort_keys=True),
                    evidence=measurement_writer_audit,
                )
        with diagnostics.phase("finalization.report.assemble"):
            runtime_evidence.update(
                {
                    "runtime_identity_post": runtime_identity_post,
                    "post_scene": post_scene,
                    "post_dependency_closure": post_dependency,
                    "post_local_franka": post_franka,
                    "child_static_identity_post": child_static_identity_post,
                    "mutation_ledger": mutation_ledger,
                    "zero_epoch_mutation_events": zero_epoch_mutation_events,
                    "writer_audit": measurement_writer_audit,
                    "trajectory": {
                        key: value for key, value in trajectory.items() if key != "transitions"
                    },
                    "video_artifacts": video_artifacts,
                    "video_sample_every_transitions": int(
                        diagnostic["video"]["sample_every_transitions"]
                    ),
                }
            )
            report = {
                "schema_version": 1,
                "manifest_type": CHILD_MANIFEST_TYPE,
                "lifecycle_status": CHILD_LIFECYCLE_BY_RUNTIME_STATUS["ok"],
                "runtime_status": "ok",
                "treatment": args.treatment,
                "run_nonce": args.run_nonce,
                "parent_pid": args.parent_pid,
                "child_pid": child_pid,
                "run_id": run_id,
                "config_sha256": args.expected_config_sha256,
                "runtime_evidence": runtime_evidence,
            }
        exit_code = 0
    except AuditNoGo as exc:
        if not trace_records:
            trace_records.append(
                make_trace_record(
                    trace_records,
                    treatment=args.treatment,
                    run_nonce=args.run_nonce,
                    parent_pid=args.parent_pid,
                    child_pid=child_pid,
                    run_id=run_id,
                    kind="bootstrap",
                    payload={"runtime_evidence": runtime_evidence},
                )
            )
        trace_records.append(
            make_trace_record(
                trace_records,
                treatment=args.treatment,
                run_nonce=args.run_nonce,
                parent_pid=args.parent_pid,
                child_pid=child_pid,
                run_id=run_id,
                kind="audit_no_go",
                payload={"code": exc.code, "detail": exc.detail, "evidence": exc.evidence},
            )
        )
        report = {
            "schema_version": 1,
            "manifest_type": CHILD_MANIFEST_TYPE,
            "lifecycle_status": CHILD_LIFECYCLE_BY_RUNTIME_STATUS["audit_no_go"],
            "runtime_status": "audit_no_go",
            "treatment": args.treatment,
            "run_nonce": args.run_nonce,
            "parent_pid": args.parent_pid,
            "child_pid": child_pid,
            "run_id": run_id,
            "config_sha256": args.expected_config_sha256,
            "audit_no_go": {"code": exc.code, "detail": exc.detail, "evidence": exc.evidence},
            "runtime_evidence": runtime_evidence,
        }
        exit_code = 0
    except BaseException as exc:
        if not trace_records:
            trace_records.append(
                make_trace_record(
                    trace_records,
                    treatment=args.treatment,
                    run_nonce=args.run_nonce,
                    parent_pid=args.parent_pid,
                    child_pid=child_pid,
                    run_id=run_id,
                    kind="bootstrap",
                    payload={"runtime_evidence": runtime_evidence},
                )
            )
        trace_records.append(
            make_trace_record(
                trace_records,
                treatment=args.treatment,
                run_nonce=args.run_nonce,
                parent_pid=args.parent_pid,
                child_pid=child_pid,
                run_id=run_id,
                kind="runtime_error",
                payload={"type": type(exc).__name__, "message": str(exc)},
            )
        )
        report = {
            "schema_version": 1,
            "manifest_type": CHILD_MANIFEST_TYPE,
            "lifecycle_status": CHILD_LIFECYCLE_BY_RUNTIME_STATUS["runtime_error"],
            "runtime_status": "runtime_error",
            "treatment": args.treatment,
            "run_nonce": args.run_nonce,
            "parent_pid": args.parent_pid,
            "child_pid": child_pid,
            "run_id": run_id,
            "config_sha256": args.expected_config_sha256,
            "runtime_error": {"type": type(exc).__name__, "message": str(exc)},
            "runtime_evidence": runtime_evidence,
        }
        exit_code = 1
    try:
        with diagnostics.phase("finalization.trace.rechain"):
            trace_records = _bind_trace_bootstrap_runtime_evidence(
                trace_records,
                treatment=args.treatment,
                run_nonce=args.run_nonce,
                parent_pid=args.parent_pid,
                child_pid=child_pid,
                run_id=run_id,
                runtime_evidence=runtime_evidence,
            )
            trace_records.append(
                make_trace_record(
                    trace_records,
                    treatment=args.treatment,
                    run_nonce=args.run_nonce,
                    parent_pid=args.parent_pid,
                    child_pid=child_pid,
                    run_id=run_id,
                    kind="terminal",
                    payload={
                        "runtime_status": report["runtime_status"],
                        "lifecycle_status": report["lifecycle_status"],
                    },
                )
            )
        with diagnostics.phase("finalization.trace.publish"):
            trace_path = args.out_dir / TRACE_BASENAME
            atomic_create_jsonl(trace_path, trace_records)
            report["trace_chain_sha256"] = trace_records[-1]["record_sha256"]
            report["artifacts"] = {
                "frozen_config": _artifact_record(args.frozen_config, relative_to=args.out_dir),
                "trace": _artifact_record(trace_path, relative_to=args.out_dir),
            }
            if isinstance(runtime_evidence.get("video_artifacts"), Mapping):
                report["artifacts"]["video"] = runtime_evidence["video_artifacts"].get(
                    "video"
                )
                report["artifacts"]["video_frame_map"] = runtime_evidence[
                    "video_artifacts"
                ].get("frame_map")
        with diagnostics.phase("finalization.provisional.publish"):
            provisional_path = args.out_dir / PROVISIONAL_REPORT_BASENAME
            atomic_create_json(provisional_path, report)
            report_written = True
        if video is not None:
            video.abort()
        close_marker = None if mutation_notice is None else mutation_notice.mark()
        world_before_close = _runtime_world_counter(world) if world is not None else None
        collector_closed = controller is None
        with diagnostics.phase("finalization.controller.close"):
            if controller is not None:
                controller.close()
                collector_closed = True
            world_after_close = _runtime_world_counter(world) if world is not None else None
            if world_before_close != world_after_close:
                raise RuntimeError("controller_close_advanced_world")
        with diagnostics.phase("finalization.cleanup.audit"):
            post_close_mutation_events = []
            if mutation_notice is not None and close_marker is not None:
                post_close_mutation_events = mutation_notice.capture_since(
                    close_marker, phase="close"
                )["events"]
            writer_audit = (
                audit.report(
                    mutation_notice_active=True,
                    mutation_events=(
                        []
                        if mutation_notice is None or mutation_marker is None
                        else mutation_notice.events_since(mutation_marker)
                    ),
                    snapshot_phase="after_controller_close",
                )
                if audit is not None
                else {
                    "coverage": {name: False for name in REQUIRED_WRITER_AUDIT_SURFACES},
                    "surfaces": {},
                    "static_production_closure": {},
                    "counts": {name: 0 for name in WRITER_AUDIT_COUNT_FIELDS},
                    "reset_root_write_count": 0,
                    "zero_write_epoch_opened": False,
                    "mutation_notice_active": False,
                    "writer_audit_snapshot_phase": "after_controller_close",
                }
            )
            if audit is not None:
                audit.close()
            if mutation_notice is not None:
                mutation_notice.close()
        with diagnostics.phase("finalization.cleanup.publish"):
            cleanup = {
                "schema_version": 1,
                "manifest_type": "native_expert_empty_beaker_unbound_lift_cleanup_v1",
                "treatment": args.treatment,
                "run_nonce": args.run_nonce,
                "parent_pid": args.parent_pid,
                "child_pid": child_pid,
                "run_id": run_id,
                "trace_chain_sha256": trace_records[-1]["record_sha256"],
                "controller_closed": collector_closed,
                "collector_closed": collector_closed,
                "world_counter_before_controller_close": world_before_close,
                "world_counter_after_controller_close": world_after_close,
                "writer_audit_snapshot_phase": writer_audit.get(
                    "writer_audit_snapshot_phase"
                ),
                "writer_audit": writer_audit,
                "post_close_mutation_events": post_close_mutation_events,
                "runtime_status": report["runtime_status"],
                "lifecycle_status": report["lifecycle_status"],
            }
            atomic_create_json(args.out_dir / CLEANUP_BASENAME, cleanup)
            cleanup_written = True
    except BaseException:
        exit_code = 1
    return exit_code if report_written and cleanup_written else 1


def terminate_process_group(
    process: subprocess.Popen[Any],
    *,
    term_grace_seconds: float = 30.0,
    kill_grace_seconds: float = 10.0,
) -> str:
    if process.poll() is not None:
        process.wait(timeout=kill_grace_seconds)
        try:
            if _process_group_members(process.pid):
                os.killpg(process.pid, signal.SIGTERM)
                deadline = time.monotonic() + term_grace_seconds
                while _process_group_members(process.pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
                if _process_group_members(process.pid):
                    os.killpg(process.pid, signal.SIGKILL)
                    deadline = time.monotonic() + kill_grace_seconds
                    while _process_group_members(process.pid) and time.monotonic() < deadline:
                        time.sleep(0.05)
                    return "POSTEXIT_SIGKILL"
                return "POSTEXIT_SIGTERM"
        except ProcessLookupError:
            pass
        return "ALREADY_EXITED"
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=term_grace_seconds)
        if not _process_group_members(process.pid):
            return "SIGTERM"
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return "SIGTERM"
        deadline = time.monotonic() + kill_grace_seconds
        while _process_group_members(process.pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        if _process_group_members(process.pid):
            return "SIGTERM_POSTEXIT_SIGKILL_UNREAPED"
        return "SIGTERM_POSTEXIT_SIGKILL"
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=kill_grace_seconds)
            return "SIGKILL"
        except subprocess.TimeoutExpired:
            return "SIGKILL_UNREAPED"


def _process_group_members(process_group_id: int) -> list[int]:
    members = []
    proc = Path("/proc")
    if not proc.is_dir():
        raise RuntimeError("native_unbound_procfs_unavailable")
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="utf-8").split()
            if len(fields) >= 5 and int(fields[4]) == process_group_id:
                members.append(int(entry.name))
        except (OSError, ValueError):
            continue
    return sorted(members)


def validate_process_quiescence(
    process: subprocess.Popen[Any], *, collector_closed: bool | None
) -> dict[str, Any]:
    if process.poll() is None:
        raise RuntimeError("native_unbound_child_not_reaped")
    if collector_closed is not None and collector_closed is not True:
        raise RuntimeError("native_unbound_collector_not_closed")
    members = _process_group_members(process.pid)
    if members:
        raise RuntimeError(f"native_unbound_process_group_not_quiescent:{members}")
    return {"quiescent": True, "process_group_members": []}


def cleanup_process_group_after_validation_error(
    process: subprocess.Popen[Any],
) -> dict[str, Any]:
    """Reap an exited child and any descendants before another treatment starts."""

    termination = terminate_process_group(process)
    quiescence = validate_process_quiescence(process, collector_closed=None)
    return {"termination": termination, "quiescent": quiescence["quiescent"]}


def _validate_cleanup_receipt(
    cleanup: Mapping[str, Any],
    *,
    treatment: str,
    run_nonce: str,
    parent_pid: int,
    child_pid: int,
    run_id: str,
    trace_chain_sha256: str,
    runtime_status: str,
    lifecycle_status: str,
) -> dict[str, Any]:
    before_close = cleanup.get("world_counter_before_controller_close") if isinstance(cleanup, Mapping) else None
    after_close = cleanup.get("world_counter_after_controller_close") if isinstance(cleanup, Mapping) else None
    ok_close_counters = (
        type(before_close) is int
        and type(after_close) is int
        and before_close == after_close
    )
    if (
        not isinstance(cleanup, Mapping)
        or cleanup.get("schema_version") != 1
        or cleanup.get("manifest_type")
        != "native_expert_empty_beaker_unbound_lift_cleanup_v1"
        or cleanup.get("treatment") != treatment
        or cleanup.get("run_nonce") != run_nonce
        or cleanup.get("parent_pid") != parent_pid
        or cleanup.get("child_pid") != child_pid
        or cleanup.get("run_id") != run_id
        or cleanup.get("trace_chain_sha256") != trace_chain_sha256
        or cleanup.get("runtime_status") != runtime_status
        or cleanup.get("lifecycle_status") != lifecycle_status
        or cleanup.get("controller_closed") is not True
        or cleanup.get("collector_closed") is not True
        or (
            runtime_status == "ok"
            and (
                not ok_close_counters
                or cleanup.get("writer_audit_snapshot_phase") != "after_controller_close"
            )
        )
        or (
            runtime_status != "ok"
            and before_close is not None
            and after_close is not None
            and before_close != after_close
        )
        or not isinstance(cleanup.get("writer_audit"), Mapping)
        or not isinstance(cleanup.get("post_close_mutation_events"), list)
    ):
        raise ValueError("native_unbound_cleanup_receipt_invalid")
    return {**dict(cleanup), "valid": True}


def _validate_artifact_manifest_record(
    treatment_dir: Path,
    record: Any,
    *,
    expected_path: str,
) -> dict[str, Any]:
    if (
        not isinstance(record, Mapping)
        or record.get("path") != expected_path
        or type(record.get("byte_count")) is not int
        or record["byte_count"] < 0
        or not _is_sha256(record.get("sha256"))
    ):
        raise ValueError("native_unbound_child_artifact_manifest_invalid")
    path = treatment_dir / expected_path
    if (
        not path.is_file()
        or path.stat().st_size != record["byte_count"]
        or sha256_file(path) != record["sha256"]
    ):
        raise ValueError("native_unbound_child_artifact_manifest_invalid")
    return dict(record)


def _validate_child_status_binding(
    provisional: Mapping[str, Any], trace_validation: Mapping[str, Any]
) -> None:
    status = provisional.get("runtime_status")
    expected_lifecycle = CHILD_LIFECYCLE_BY_RUNTIME_STATUS.get(status)
    terminal = trace_validation.get("terminal_record")
    if (
        expected_lifecycle is None
        or provisional.get("lifecycle_status") != expected_lifecycle
        or trace_validation.get("runtime_status") != status
        or trace_validation.get("lifecycle_status") != expected_lifecycle
        or not isinstance(terminal, Mapping)
        or terminal.get("payload")
        != {"runtime_status": status, "lifecycle_status": expected_lifecycle}
    ):
        raise ValueError("native_unbound_child_status_contradiction")


def _validate_treatment_tree(root: Path) -> dict[str, Any]:
    root = root.resolve()
    paths = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item)):
        if path.is_symlink():
            raise ValueError(f"native_unbound_output_symlink_forbidden:{path}")
        resolved = path.resolve()
        try:
            paths.append(resolved.relative_to(root).as_posix())
        except ValueError as exc:
            raise ValueError(f"native_unbound_output_path_escape:{path}") from exc
    return {"valid": True, "paths": paths, "path_count": len(paths)}


def _validate_child_artifacts(
    *,
    treatment_dir: Path,
    treatment: str,
    run_nonce: str,
    parent_pid: int,
    child_pid: int,
    config_sha256: str,
) -> dict[str, Any]:
    provisional = load_strict_json_object(treatment_dir / PROVISIONAL_REPORT_BASENAME)
    required = {
        "schema_version",
        "manifest_type",
        "lifecycle_status",
        "runtime_status",
        "treatment",
        "run_nonce",
        "parent_pid",
        "child_pid",
        "run_id",
        "config_sha256",
        "runtime_evidence",
        "trace_chain_sha256",
        "artifacts",
    }
    if (
        not required <= set(provisional)
        or provisional.get("schema_version") != 1
        or provisional.get("manifest_type") != CHILD_MANIFEST_TYPE
        or provisional.get("runtime_status") not in {"ok", "audit_no_go", "runtime_error"}
        or provisional.get("treatment") != treatment
        or provisional.get("run_nonce") != run_nonce
        or provisional.get("parent_pid") != parent_pid
        or provisional.get("child_pid") != child_pid
        or provisional.get("config_sha256") != config_sha256
        or not isinstance(provisional.get("run_id"), str)
        or not provisional["run_id"]
        or not isinstance(provisional.get("runtime_evidence"), Mapping)
        or not isinstance(provisional.get("artifacts"), Mapping)
    ):
        raise ValueError("native_unbound_provisional_identity_invalid")
    trace = load_strict_jsonl(treatment_dir / TRACE_BASENAME)
    try:
        trace_validation = validate_trace_records(
            trace,
            expected_treatment=treatment,
            expected_nonce=run_nonce,
            expected_parent_pid=parent_pid,
            expected_child_pid=child_pid,
            expected_run_id=provisional["run_id"],
            expected_runtime_status=provisional["runtime_status"],
            expected_lifecycle_status=provisional["lifecycle_status"],
        )
    except ValueError as exc:
        if str(exc) == "native_unbound_trace_status_contradiction":
            raise ValueError("native_unbound_child_status_contradiction") from exc
        raise
    if provisional.get("trace_chain_sha256") != trace_validation["chain_sha256"]:
        raise ValueError("native_unbound_trace_summary_contradiction")
    if trace_validation.get("bootstrap_runtime_evidence_sha256") != _canonical_json_sha256(
        provisional["runtime_evidence"]
    ):
        raise ValueError("native_unbound_trace_runtime_evidence_mismatch")
    _validate_child_status_binding(provisional, trace_validation)
    artifacts = provisional["artifacts"]
    frozen_artifact = _validate_artifact_manifest_record(
        treatment_dir,
        artifacts.get("frozen_config"),
        expected_path=FROZEN_CONFIG_BASENAME,
    )
    trace_artifact = _validate_artifact_manifest_record(
        treatment_dir,
        artifacts.get("trace"),
        expected_path=TRACE_BASENAME,
    )
    if frozen_artifact.get("sha256") != config_sha256:
        raise ValueError("native_unbound_child_artifact_manifest_invalid")
    cleanup = load_strict_json_object(treatment_dir / CLEANUP_BASENAME)
    cleanup_validation = _validate_cleanup_receipt(
        cleanup,
        treatment=treatment,
        run_nonce=run_nonce,
        parent_pid=parent_pid,
        child_pid=child_pid,
        run_id=provisional["run_id"],
        trace_chain_sha256=trace_validation["chain_sha256"],
        runtime_status=provisional["runtime_status"],
        lifecycle_status=provisional["lifecycle_status"],
    )
    return {
        "provisional": provisional,
        "trace": trace,
        "trace_validation": trace_validation,
        "cleanup": cleanup_validation,
    }


def _boundary_records(transitions: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    boundaries = []
    for transition in transitions:
        values = transition.get("boundaries")
        if not isinstance(values, Mapping) or not values:
            raise ValueError("native_unbound_boundary_snapshots_missing")
        if set(values) == {name for name, _phase in _PRODUCTION_BOUNDARY_PHASES}:
            expected_boundaries = _PRODUCTION_BOUNDARY_PHASES
        elif set(values) == {name for name, _phase in _CONTINUATION_BOUNDARY_PHASES}:
            expected_boundaries = _CONTINUATION_BOUNDARY_PHASES
        else:
            raise ValueError("native_unbound_boundary_snapshot_invalid")
        for name, expected_phase in expected_boundaries:
            boundary = values[name]
            if not isinstance(boundary, Mapping):
                raise ValueError("native_unbound_boundary_snapshot_invalid")
            segment = boundary.get("mutation_segment")
            if (
                not isinstance(segment, Mapping)
                or segment.get("phase") != expected_phase
                or not isinstance(segment.get("events"), list)
                or boundary.get("mutation_events") != segment.get("events")
            ):
                raise ValueError("native_unbound_boundary_mutation_segment_invalid")
            _relation_boundary_fingerprint_sha256(boundary.get("relation_fingerprint"))
            boundaries.append(boundary)
    return boundaries


def _evaluate_local_runtime_audits(
    evidence: Mapping[str, Any],
    transitions: Sequence[Mapping[str, Any]],
    *,
    diagnostic: Mapping[str, Any],
    close_mutation_events: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    audit_failures: list[str] = []
    evaluations: dict[str, Any] = {}
    try:
        if not isinstance(evidence, Mapping):
            raise ValueError("runtime_evidence_missing")
        protocol = _protocol_spec_for_diagnostic(diagnostic)
        if protocol.get("composite_support") is True:
            if evidence.get("protocol") != protocol:
                audit_failures.append("runtime_protocol_binding_mismatch")
            identities = evidence.get("contact_identities")
            if (
                not isinstance(identities, Mapping)
                or identities.get("support_colliders") != protocol["support_collider_paths"]
            ):
                audit_failures.append("runtime_support_identity_binding_mismatch")
        ledger = validate_runtime_transition_ledger(
            transitions,
            maximum_production_steps=int(diagnostic["maximum_production_steps"]),
            retention_steps=int(diagnostic["retention_steps"]),
        )
        evaluations["transition_ledger"] = ledger
        if not ledger["audit_valid"]:
            audit_failures.extend(ledger["audit_failures"])
        source = evaluate_dynamic_source_contract(evidence.get("source_contract"))
        evaluations["source_contract"] = source
        if not source["audit_valid"]:
            audit_failures.extend(source["audit_failures"])
        if evidence.get("source_contract_evaluation") != source:
            audit_failures.append("source_contract_evaluation_contradiction")
        source_contract_payload = evidence.get("source_contract")
        if (
            not isinstance(source_contract_payload, Mapping)
            or evidence.get("source_local_com_authority")
            != source_contract_payload.get("source_local_com_authority")
        ):
            audit_failures.append("source_local_com_authority_contradiction")
        scene = evidence.get("scene")
        if not isinstance(scene, Mapping) or scene.get("valid") is not True:
            audit_failures.append("scene_contract_authority_missing")
        version = evidence.get("runtime_version")
        if not isinstance(version, Mapping) or version.get("isaac_sim_version") != "4.1.0.0":
            audit_failures.append("runtime_version_authority_missing")
        pre_identity = evidence.get("runtime_identity_pre")
        post_identity = evidence.get("runtime_identity_post")
        if not isinstance(pre_identity, Mapping) or pre_identity != post_identity:
            audit_failures.append("runtime_identity_pre_post_mismatch")
        report_layer = evidence.get("report_layer")
        expected_report_catalog_sha256 = None
        if report_layer is not None:
            if not isinstance(report_layer, Mapping) or not isinstance(
                report_layer.get("catalog"), Mapping
            ):
                audit_failures.append("report_layer_runtime_identity_binding_missing")
            else:
                expected_report_catalog_sha256 = report_layer["catalog"].get("sha256")
        for identity in (pre_identity, post_identity):
            if (
                not isinstance(identity, Mapping)
                or identity.get("report_layer_catalog_sha256")
                != expected_report_catalog_sha256
            ):
                audit_failures.append("report_layer_runtime_identity_binding_missing")
        local_franka = evaluate_local_franka_evidence(
            evidence.get("local_franka"),
            evidence.get("post_local_franka"),
            diagnostic=diagnostic,
        )
        evaluations["local_franka"] = local_franka
        if not local_franka["audit_valid"]:
            audit_failures.extend(local_franka["audit_failures"])
        for runtime_name, local_name in (
            ("runtime_identity_pre", "local_franka"),
            ("runtime_identity_post", "post_local_franka"),
        ):
            runtime_identity = evidence.get(runtime_name)
            local_identity = evidence.get(local_name)
            local_closure = (
                local_identity.get("dependency_closure")
                if isinstance(local_identity, Mapping)
                else None
            )
            if (
                not isinstance(runtime_identity, Mapping)
                or not isinstance(local_identity, Mapping)
                or not isinstance(local_closure, Mapping)
                or runtime_identity.get("local_franka_root_usd_path")
                != local_identity.get("root_usd_path")
                or runtime_identity.get("local_franka_root_sha256")
                != local_identity.get("root_sha256")
                or runtime_identity.get("local_franka_dependency_closure_sha256")
                != local_closure.get("sha256")
                or runtime_identity.get("local_franka_sha256")
                != local_identity.get("sha256")
            ):
                audit_failures.append("runtime_local_franka_identity_mismatch")
        if evidence.get("child_static_identity_pre") != evidence.get(
            "child_static_identity_post"
        ):
            audit_failures.append("child_static_identity_pre_post_mismatch")
        boundaries = _boundary_records(transitions)
        mutation_ledger = evidence.get("mutation_ledger")
        known_dynamic_body_paths = evidence.get("known_dynamic_body_paths")
        if (
            not isinstance(mutation_ledger, list)
            or not isinstance(close_mutation_events, Sequence)
            or isinstance(close_mutation_events, (str, bytes, bytearray))
        ):
            raise ValueError("mutation_evidence_missing")
        pre_reset_mutations = evidence.get("pre_reset_mutation_events")
        if not isinstance(pre_reset_mutations, list):
            raise ValueError("mutation_evidence_missing")
        expected_measurement_ledger = [
            {"phase": "pre_reset", "events": pre_reset_mutations},
            *[
                copy.deepcopy(dict(boundary["mutation_segment"]))
                for boundary in boundaries
            ],
        ]
        if _canonical_json_bytes(mutation_ledger) != _canonical_json_bytes(
            expected_measurement_ledger
        ):
            audit_failures.append("mutation_ledger_boundary_contradiction")
        full_mutation_ledger = [*copy.deepcopy(mutation_ledger)]
        full_mutation_ledger.append(
            {"phase": "close", "events": copy.deepcopy(list(close_mutation_events))}
        )
        mutation = evaluate_runtime_mutation_ledger(
            full_mutation_ledger,
            known_dynamic_body_paths=known_dynamic_body_paths,
            support_paths=(
                protocol["support_collider_paths"]
                if protocol.get("composite_support") is True
                else [SUPPORT_PATH]
            ),
        )
        evaluations["mutation_ledger"] = mutation
        if not mutation["audit_valid"]:
            audit_failures.extend(mutation["audit_failures"])
        source_baseline = evidence.get("source_properties_before_reset")
        source_snapshots = [evidence.get("source_properties_after_reset"), *[
            boundary.get("source_robot_properties") for boundary in boundaries
        ]]
        properties = evaluate_source_robot_property_mutations(
            source_baseline,
            source_snapshots,
            [],
            pre_reset_mutation_events=pre_reset_mutations,
        )
        evaluations["source_robot_properties"] = properties
        if not properties["audit_valid"]:
            audit_failures.extend(properties["audit_failures"])
        execution_mutation_events = [
            event
            for segment in full_mutation_ledger
            if segment["phase"] != "pre_reset"
            for event in segment["events"]
        ]
        if protocol.get("composite_support") is True:
            static_supports = evaluate_static_support_immutability(
                evidence.get("static_supports_baseline"),
                [evidence.get("static_supports_after_reset")],
                execution_mutation_events,
                support_paths=protocol["support_collider_paths"],
            )
            evaluations["static_supports"] = static_supports
            if not static_supports["audit_valid"]:
                audit_failures.extend(static_supports["audit_failures"])
            static_support_boundaries = evaluate_static_support_boundary_fingerprints(
                evidence.get("static_supports_baseline"),
                [
                    boundary.get("static_support_fingerprints")
                    for boundary in boundaries
                ],
                support_paths=protocol["support_collider_paths"],
            )
            evaluations["static_support_boundaries"] = static_support_boundaries
            if not static_support_boundaries["audit_valid"]:
                audit_failures.extend(static_support_boundaries["audit_failures"])
        else:
            cube_baseline = evidence.get("cube_baseline")
            cube_snapshots = [evidence.get("cube_after_reset"), *[
                boundary.get("cube") for boundary in boundaries
            ]]
            cube = evaluate_cube_immutability(
                cube_baseline,
                cube_snapshots,
                execution_mutation_events,
            )
            evaluations["cube"] = cube
            if not cube["audit_valid"]:
                audit_failures.extend(cube["audit_failures"])
        relation_before_reset = evidence.get("relation_before_reset")
        if not isinstance(relation_before_reset, Mapping):
            raise ValueError("relation_before_reset_missing")
        relation_after_reset = evidence.get("relation_after_reset")
        if not isinstance(relation_after_reset, Mapping):
            raise ValueError("relation_after_reset_missing")
        try:
            _relation_inventory_sha256(relation_before_reset)
        except ValueError:
            audit_failures.append("relation_before_reset_fingerprint_invalid")
        relation_fingerprints = evaluate_relation_boundary_fingerprints(
            relation_after_reset,
            [boundary.get("relation_fingerprint") for boundary in boundaries],
        )
        evaluations["relation_fingerprints"] = relation_fingerprints
        if not relation_fingerprints["audit_valid"]:
            audit_failures.extend(relation_fingerprints["audit_failures"])
        relation_evaluations = [
            evaluate_coupling_inventory(
                {
                    **dict(relation_before_reset),
                    "mutation_events": execution_mutation_events,
                }
            ),
            evaluate_coupling_inventory(
                {
                    **dict(relation_after_reset),
                    "mutation_events": execution_mutation_events,
                }
            ),
        ]
        evaluations["relations"] = relation_evaluations
        for relation in relation_evaluations:
            if not relation["audit_valid"]:
                audit_failures.extend(relation["audit_failures"])
        writer = evaluate_writer_target_force_gripper_audit(evidence.get("writer_audit"))
        evaluations["writer_audit"] = writer
        if not writer["audit_valid"]:
            audit_failures.extend(writer["audit_failures"])
        writer_payload = evidence.get("writer_audit")
        if (
            not isinstance(writer_payload, Mapping)
            or evidence.get("static_production_closure")
            != writer_payload.get("static_production_closure")
        ):
            audit_failures.append("static_production_closure_contradiction")
        trajectory = evidence.get("trajectory")
        terminal_index = ledger["terminal_index"]
        if (
            not isinstance(trajectory, Mapping)
            or type(trajectory.get("terminal")) is not bool
            or type(trajectory.get("maximum_transitions_reached")) is not bool
            or trajectory.get("terminal") is not (terminal_index is not None)
            or trajectory.get("maximum_transitions_reached") is not (terminal_index is None)
            or trajectory.get("terminal_phase")
            != (None if terminal_index is None else transitions[terminal_index].get("terminal_outcome"))
            or trajectory.get("terminal_success")
            != (None if terminal_index is None else transitions[terminal_index].get("terminal_success"))
        ):
            audit_failures.append("trajectory_terminal_contradiction")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {
        "audit_valid": not audit_failures,
        "audit_failures": audit_failures,
        "evaluations": evaluations,
    }


def _v4_observation_gap_contact_valid(
    contact: Mapping[str, Any], *, protocol: Mapping[str, Any]
) -> bool:
    if not isinstance(contact, Mapping) or contact.get("support_observation_gap") is not True:
        return False
    pairs = contact.get("unreported_active_pairs")
    if not _v4_observation_gap_pairs_valid(pairs, protocol=protocol, gap=True):
        return False
    try:
        _contact_observer_projection(contact, protocol=protocol)
    except ValueError:
        return False
    return isinstance(contact.get("raw_report"), Mapping) and isinstance(
        contact.get("geometry"), Mapping
    )


def _replay_v4_observation_gap_samples(
    reports: Sequence[Mapping[str, Any]],
    *,
    identities: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    samples = []
    try:
        if not reports:
            raise ValueError("instrumented_v4_observation_gap_reports_missing")
        accumulator = ContactLifecycleAccumulator(identities, protocol=protocol)
        for index, report in enumerate(reports):
            if (
                not isinstance(report, Mapping)
                or report.get("physics_index") != index
                or report.get("immediate_read_index") != index
                or report.get("immediate_read_count") != index + 1
            ):
                raise ValueError("instrumented_v4_observation_gap_report_invalid")
            samples.append(accumulator.consume(physics_index=index, raw=report))
    except (ContactAuditError, TypeError, ValueError) as exc:
        return {
            "audit_valid": False,
            "audit_failures": [str(exc)],
            "samples": [],
        }
    return {"audit_valid": True, "audit_failures": [], "samples": samples}


def _parent_recompute_v4_observation_gap_prefix(
    transitions: Sequence[Mapping[str, Any]],
    journals: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay parser-authoritative v4 gap journals across an audit-failure prefix."""

    failures: list[str] = []
    contact_replay: dict[str, Any] | None = None
    parser_replay: dict[str, Any] | None = None
    try:
        spec = _require_protocol_spec(protocol)
        if spec.get("allow_active_support_pair_omission") is not True:
            raise ValueError("instrumented_v4_observation_gap_protocol_invalid")
        if (
            not isinstance(transitions, Sequence)
            or isinstance(transitions, (str, bytes, bytearray))
            or not isinstance(journals, Sequence)
            or isinstance(journals, (str, bytes, bytearray))
            or not isinstance(evidence, Mapping)
        ):
            raise ValueError("instrumented_v4_observation_gap_journal_invalid")
        completed = [copy.deepcopy(dict(transition)) for transition in transitions]
        completed_gap_indices: set[int] = set()
        reports = []
        for index, transition in enumerate(completed):
            if (
                not isinstance(transition, Mapping)
                or transition.get("transition_index") != index
                or not isinstance(transition.get("contact"), Mapping)
            ):
                raise ValueError("instrumented_v4_observation_gap_journal_invalid")
            raw = transition["contact"].get("raw_report")
            if not isinstance(raw, Mapping):
                raise ValueError("instrumented_v4_observation_gap_journal_invalid")
            reports.append(raw)
            if transition["contact"].get("support_observation_gap") is True:
                if not _v4_observation_gap_contact_valid(
                    transition["contact"], protocol=spec
                ):
                    raise ValueError("instrumented_v4_observation_gap_journal_invalid")
                completed_gap_indices.add(index)

        journal_indices: set[int] = set()
        previous_index = -1
        trailing = None
        for journal in journals:
            if not isinstance(journal, Mapping):
                raise ValueError("instrumented_v4_observation_gap_journal_invalid")
            index = journal.get("transition_index")
            parser_sample = journal.get("parser_sample")
            raw_report = journal.get("raw_report")
            if (
                set(journal)
                != {"transition_index", "raw_report", "parser_sample"}
                or type(index) is not int
                or index < 0
                or index <= previous_index
                or index > len(completed)
                or index in journal_indices
                or not isinstance(raw_report, Mapping)
            ):
                raise ValueError("instrumented_v4_observation_gap_journal_invalid")
            if (
                not isinstance(parser_sample, Mapping)
                or set(parser_sample) != set(_V4_OBSERVATION_GAP_SAMPLE_FIELDS)
                or _v4_observation_gap_sample_projection(parser_sample, protocol=spec)[
                    "support_observation_gap"
                ]
                is not True
            ):
                raise ValueError("instrumented_v4_observation_gap_journal_invalid")
            previous_index = index
            journal_indices.add(index)
            if index < len(completed):
                completed_contact = completed[index]["contact"]
                if (
                    index not in completed_gap_indices
                    or _canonical_json_bytes(raw_report)
                    != _canonical_json_bytes(completed_contact.get("raw_report"))
                    or parser_sample["unreported_active_pairs"]
                    != completed_contact.get("unreported_active_pairs")
                ):
                    raise ValueError("instrumented_v4_observation_gap_journal_invalid")
            else:
                trailing = copy.deepcopy(dict(journal))
        if completed_gap_indices - journal_indices:
            failures.append("instrumented_v4_observation_gap_journal_missing")
        if completed:
            contact_replay = _parent_recompute_instrumented_contacts(
                completed, evidence, protocol=spec
            )
            if not contact_replay["audit_valid"]:
                failures.extend(contact_replay["audit_failures"])
        if trailing is not None:
            reports.append(trailing["raw_report"])
        if journals:
            identities = evidence.get("contact_identities")
            parser_replay = _replay_v4_observation_gap_samples(
                reports,
                identities=identities,
                protocol=spec,
            )
            if not parser_replay["audit_valid"]:
                failures.extend(parser_replay["audit_failures"])
            else:
                for journal in journals:
                    index = journal["transition_index"]
                    derived = _v4_observation_gap_sample_projection(
                        parser_replay["samples"][index], protocol=spec
                    )
                    if _canonical_json_bytes(journal["parser_sample"]) != _canonical_json_bytes(
                        derived
                    ):
                        failures.append("instrumented_v4_observation_gap_journal_invalid")
    except (ContactAuditError, KeyError, TypeError, ValueError) as exc:
        failures.extend(
            ["instrumented_v4_observation_gap_journal_invalid", str(exc)]
        )
    failures = sorted(set(failures))
    return {
        "audit_valid": not failures,
        "audit_failures": failures,
        "journal_count": len(journals) if isinstance(journals, Sequence) else None,
        "contact_replay": contact_replay,
        "parser_replay": (
            None
            if parser_replay is None
            else {
                "audit_valid": parser_replay["audit_valid"],
                "audit_failures": parser_replay["audit_failures"],
                "journal_indices": [journal["transition_index"] for journal in journals],
            }
        ),
    }


def _parent_recompute_instrumented_contacts(
    transitions: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected_protocol = _require_protocol_spec(
        evidence.get("protocol", PROTOCOL_SPECS[(1, V1_PROTOCOL_ID)])
        if protocol is None
        else protocol
    )
    if protocol is not None and evidence.get("protocol") != expected_protocol:
        return {
            "audit_valid": False,
            "audit_failures": ["instrumented_protocol_binding_mismatch"],
        }
    protocol = expected_protocol
    identities = evidence.get("contact_identities")
    reports = []
    geometries = []
    for transition in transitions:
        contact = transition.get("contact")
        if not isinstance(contact, Mapping):
            raise ValueError("instrumented_contact_payload_missing")
        raw = contact.get("raw_report")
        geometry = contact.get("geometry")
        if not isinstance(raw, Mapping) or not isinstance(geometry, Mapping):
            raise ValueError("instrumented_raw_contact_authority_missing")
        reports.append(raw)
        geometries.append(geometry)
    contacts = evaluate_contact_trace(
        reports,
        identities=identities,
        geometry=geometries,
        require_immediate_read=True,
        protocol=protocol,
    )
    if not contacts["audit_valid"]:
        return {"audit_valid": False, "audit_failures": contacts["audit_failures"]}
    source_states = [transition["post"] for transition in transitions]
    action_contexts = (
        [
            {
                "pick_event": transition.get("pick_event"),
                "action": transition.get("action"),
                "apply_count": transition.get("apply_count"),
                "action_receipt": transition.get("action_receipt"),
            }
            for transition in transitions
        ]
        if protocol["initial_support_activation_max_absent_reports"] > 0
        else None
    )
    lifecycle = evaluate_support_lifecycle(
        contacts["samples"],
        source_states,
        protocol=protocol,
        action_contexts=action_contexts,
    )
    if not lifecycle["audit_valid"]:
        return {
            "audit_valid": False,
            "audit_failures": lifecycle["audit_failures"],
            "contact_trace": contacts,
            "support_lifecycle": lifecycle,
        }
    augmented = copy.deepcopy(list(transitions))
    loss_index = lifecycle["loss_index"]
    replay_failures: list[str] = []
    for index, (transition, sample, decision) in enumerate(
        zip(augmented, contacts["samples"], lifecycle["decisions"])
    ):
        support = sample["support"]
        derived = _runtime_contact_summary(
            sample,
            source_awake=transition["post"]["awake"],
            observer_decision=decision,
            protocol=protocol,
        )
        derived["source_support_recontact"] = bool(
            loss_index is not None and index > loss_index and support["present"]
        )
        try:
            child_projection = _contact_observer_projection(
                transitions[index]["contact"], protocol=protocol
            )
            derived_projection = _contact_observer_projection(derived, protocol=protocol)
        except ValueError:
            replay_failures.append("instrumented_contact_replay_mismatch")
            continue
        if _canonical_json_bytes(child_projection) != _canonical_json_bytes(derived_projection):
            replay_failures.append("instrumented_contact_replay_mismatch")
        transition["contact"] = derived
    if replay_failures:
        return {
            "audit_valid": False,
            "audit_failures": sorted(set(replay_failures)),
            "contact_trace": contacts,
            "support_lifecycle": lifecycle,
        }
    return {
        "audit_valid": True,
        "audit_failures": [],
        "contact_trace": contacts,
        "support_lifecycle": lifecycle,
        "transitions": augmented,
    }


def _comparable_runtime_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(identity, Mapping):
        raise ValueError("runtime_identity_missing")
    value = dict(identity)
    value.pop("sha256", None)
    value.pop("report_layer_catalog_sha256", None)
    value.pop("local_franka_sha256", None)
    return value


def evaluate_parent_child_identity_binding(
    evidence: Mapping[str, Any],
    *,
    parent_identity: Mapping[str, Any],
    expected_config_sha256: str,
) -> dict[str, Any]:
    """Bind child static/runtime identities to the parent-frozen implementation and asset."""

    audit_failures: list[str] = []
    try:
        if (
            not isinstance(evidence, Mapping)
            or not isinstance(parent_identity, Mapping)
            or not _is_sha256(expected_config_sha256)
            or not _is_sha256(parent_identity.get("identity_sha256"))
            or parent_identity.get("config_sha256") != expected_config_sha256
            or not isinstance(parent_identity.get("asset_dependency_closure"), Mapping)
            or not _is_sha256(parent_identity["asset_dependency_closure"].get("entry_sha256"))
        ):
            raise ValueError("parent_identity_binding_authority_invalid")
        parent_entry_sha256 = parent_identity["asset_dependency_closure"]["entry_sha256"]
        parent_local_franka = parent_identity.get("local_franka")
        expected_local_franka_path = (REPO_ROOT / LOCAL_FRANKA_USD_PATH).resolve()
        if (
            not isinstance(parent_local_franka, Mapping)
            or parent_local_franka.get("usd_path") != LOCAL_FRANKA_USD_PATH
            or parent_local_franka.get("absolute_usd_path") != str(expected_local_franka_path)
            or parent_local_franka.get("sha256") != LOCAL_FRANKA_SHA256
        ):
            raise ValueError("parent_identity_binding_authority_invalid")
        for name in ("child_static_identity_pre", "child_static_identity_post"):
            identity = evidence.get(name)
            if not isinstance(identity, Mapping) or not _is_sha256(identity.get("identity_sha256")):
                audit_failures.append("child_static_identity_parent_mismatch")
                continue
            payload = {key: value for key, value in identity.items() if key != "identity_sha256"}
            if identity.get("identity_sha256") != _canonical_json_sha256(payload):
                audit_failures.append("child_static_identity_hash_invalid")
            if identity != parent_identity:
                audit_failures.append("child_static_identity_parent_mismatch")
            if identity.get("config_sha256") != expected_config_sha256:
                audit_failures.append("child_static_identity_config_mismatch")
        for name in ("runtime_identity_pre", "runtime_identity_post"):
            identity = evidence.get(name)
            if not isinstance(identity, Mapping) or not _is_sha256(identity.get("sha256")):
                audit_failures.append("runtime_identity_parent_binding_missing")
                continue
            payload = {key: value for key, value in identity.items() if key != "sha256"}
            if identity.get("sha256") != _canonical_json_sha256(payload):
                audit_failures.append("runtime_identity_hash_invalid")
            if identity.get("parent_static_identity_sha256") != parent_identity["identity_sha256"]:
                audit_failures.append("runtime_identity_parent_binding_missing")
            if identity.get("config_sha256") != expected_config_sha256:
                audit_failures.append("runtime_identity_config_binding_mismatch")
            if identity.get("dependency_entry_sha256") != parent_entry_sha256:
                audit_failures.append("runtime_asset_entry_hash_mismatch")
            if (
                identity.get("local_franka_root_usd_path")
                != parent_local_franka["usd_path"]
                or identity.get("local_franka_root_sha256")
                != parent_local_franka["sha256"]
                or not _is_sha256(identity.get("local_franka_dependency_closure_sha256"))
                or not _is_sha256(identity.get("local_franka_sha256"))
            ):
                audit_failures.append("local_franka_runtime_binding_mismatch")
        for name in ("dependency_closure", "post_dependency_closure"):
            closure = evidence.get(name)
            if not isinstance(closure, Mapping) or closure.get("entry_sha256") != parent_entry_sha256:
                audit_failures.append("runtime_asset_entry_hash_mismatch")
        for name in ("local_franka", "post_local_franka"):
            identity = evidence.get(name)
            closure = identity.get("dependency_closure") if isinstance(identity, Mapping) else None
            if (
                not isinstance(identity, Mapping)
                or identity.get("root_usd_path") != parent_local_franka["usd_path"]
                or identity.get("root_absolute_usd_path")
                != parent_local_franka["absolute_usd_path"]
                or identity.get("root_sha256") != parent_local_franka["sha256"]
                or not isinstance(closure, Mapping)
                or closure.get("entry_path") != parent_local_franka["absolute_usd_path"]
                or closure.get("entry_sha256") != parent_local_franka["sha256"]
            ):
                audit_failures.append("local_franka_parent_binding_mismatch")
        for runtime_name, local_name in (
            ("runtime_identity_pre", "local_franka"),
            ("runtime_identity_post", "post_local_franka"),
        ):
            runtime_identity = evidence.get(runtime_name)
            local_identity = evidence.get(local_name)
            local_closure = (
                local_identity.get("dependency_closure")
                if isinstance(local_identity, Mapping)
                else None
            )
            if (
                not isinstance(runtime_identity, Mapping)
                or not isinstance(local_identity, Mapping)
                or not isinstance(local_closure, Mapping)
                or runtime_identity.get("local_franka_root_usd_path")
                != local_identity.get("root_usd_path")
                or runtime_identity.get("local_franka_root_sha256")
                != local_identity.get("root_sha256")
                or runtime_identity.get("local_franka_dependency_closure_sha256")
                != local_closure.get("sha256")
                or runtime_identity.get("local_franka_sha256")
                != local_identity.get("sha256")
            ):
                audit_failures.append("local_franka_runtime_binding_mismatch")
    except (TypeError, ValueError) as exc:
        audit_failures.append(str(exc))
    audit_failures = sorted(set(audit_failures))
    return {"audit_valid": not audit_failures, "audit_failures": audit_failures}


def recompute_parent_evidence(
    child_results: Mapping[str, Mapping[str, Any]],
    *,
    config: Mapping[str, Any],
    parent_identity: Mapping[str, Any] | None = None,
    expected_config_sha256: str | None = None,
) -> dict[str, Any]:
    evaluations: dict[str, Any] = {}
    runtime_error = False
    audit_no_go = False
    physical_passed = False
    try:
        diagnostic = _require_pinned_diagnostic(config)
        protocol = _protocol_spec_for_diagnostic(diagnostic)
        if set(child_results) != set(TREATMENTS):
            raise RuntimeError("child_treatment_set_invalid")
        parsed: dict[str, dict[str, Any]] = {}
        for treatment in TREATMENTS:
            result = child_results[treatment]
            if not isinstance(result, Mapping) or result.get("process_runtime_error") is True:
                runtime_error = True
                continue
            provisional = result.get("provisional")
            if not isinstance(provisional, Mapping):
                runtime_error = True
                continue
            status = provisional.get("runtime_status")
            if status == "runtime_error":
                runtime_error = True
                continue
            if status == "audit_no_go":
                audit_no_go = True
                child_audit = provisional.get("audit_no_go")
                evaluation = {"child_audit_no_go": child_audit}
                initial_codes = {
                    "support_initial_state_unknown",
                    "support_initial_activation_timeout",
                    "support_current_contact_missing",
                    "support_activation_before_close_missing",
                    "support_activation_close_action_invalid",
                }
                if (
                    protocol["initial_support_activation_max_absent_reports"] > 0
                    and isinstance(child_audit, Mapping)
                    and child_audit.get("code") in initial_codes
                ):
                    runtime_evidence = provisional.get("runtime_evidence")
                    identities = (
                        runtime_evidence.get("contact_identities")
                        if isinstance(runtime_evidence, Mapping)
                        else None
                    )
                    validation = validate_initial_support_failure_evidence(
                        child_audit.get("evidence"),
                        identities=identities,
                        protocol=protocol,
                    )
                    failure_payloads = [
                        record.get("payload")
                        for record in result.get("trace", [])
                        if isinstance(record, Mapping) and record.get("kind") == "audit_no_go"
                    ]
                    trace_matches = (
                        len(failure_payloads) == 1
                        and _canonical_json_bytes(failure_payloads[0])
                        == _canonical_json_bytes(child_audit)
                    )
                    evaluation["initial_support_failure"] = {
                        **validation,
                        "trace_matches_provisional": trace_matches,
                    }
                if (
                    protocol.get("allow_active_support_pair_omission") is True
                    and treatment == "instrumented"
                ):
                    runtime_evidence = provisional.get("runtime_evidence")
                    try:
                        transitions = _extract_transitions(result.get("trace", []))
                        journals = _extract_observation_gap_journals(result.get("trace", []))
                        replay = _parent_recompute_v4_observation_gap_prefix(
                            transitions,
                            journals,
                            runtime_evidence,
                            protocol=protocol,
                        )
                    except (TypeError, ValueError) as exc:
                        replay = {
                            "audit_valid": False,
                            "audit_failures": [
                                "instrumented_v4_observation_gap_prefix_unreplayable",
                                str(exc),
                            ],
                        }
                    evaluation["observation_gap_prefix"] = replay
                evaluations[treatment] = evaluation
                continue
            if status != "ok":
                runtime_error = True
                continue
            transitions = _extract_transitions(result.get("trace", []))
            observation_gap_journals = _extract_observation_gap_journals(
                result.get("trace", [])
            )
            evidence = provisional.get("runtime_evidence")
            cleanup = result.get("cleanup")
            close_mutation_events = (
                cleanup.get("post_close_mutation_events", [])
                if isinstance(cleanup, Mapping)
                else []
            )
            local = _evaluate_local_runtime_audits(
                evidence,
                transitions,
                diagnostic=diagnostic,
                close_mutation_events=close_mutation_events,
            )
            if not local["audit_valid"]:
                audit_no_go = True
            if (
                protocol.get("allow_active_support_pair_omission") is True
                and treatment == "instrumented"
            ):
                observation_gap_replay = _parent_recompute_v4_observation_gap_prefix(
                    transitions,
                    observation_gap_journals,
                    evidence,
                    protocol=protocol,
                )
                local["observation_gap_journal"] = observation_gap_replay
                if not observation_gap_replay["audit_valid"]:
                    audit_no_go = True
            if parent_identity is not None or expected_config_sha256 is not None:
                if parent_identity is None or expected_config_sha256 is None:
                    raise ValueError("parent_identity_binding_authority_invalid")
                identity_binding = evaluate_parent_child_identity_binding(
                    evidence,
                    parent_identity=parent_identity,
                    expected_config_sha256=expected_config_sha256,
                )
                local["parent_identity_binding"] = identity_binding
                if not identity_binding["audit_valid"]:
                    audit_no_go = True
            if (
                not isinstance(cleanup, Mapping)
                or not isinstance(evidence, Mapping)
                or not isinstance(cleanup.get("post_close_mutation_events"), list)
            ):
                audit_no_go = True
                local.setdefault("audit_failures", []).append(
                    "cleanup_writer_audit_contradiction"
                )
            else:
                close_writer_payload = cleanup.get("writer_audit")
                close_writer = evaluate_writer_target_force_gripper_audit(
                    close_writer_payload
                )
                local["close_writer_audit"] = close_writer
                if not close_writer["audit_valid"]:
                    audit_no_go = True
                    local.setdefault("audit_failures", []).extend(
                        close_writer["audit_failures"]
                    )
                if (
                    cleanup.get("writer_audit_snapshot_phase") != "after_controller_close"
                    or not isinstance(close_writer_payload, Mapping)
                    or close_writer_payload.get("writer_audit_snapshot_phase")
                    != "after_controller_close"
                ):
                    audit_no_go = True
                    local.setdefault("audit_failures", []).append(
                        "cleanup_writer_audit_contradiction"
                    )
            report_layer = evidence.get("report_layer") if isinstance(evidence, Mapping) else None
            if treatment == "control":
                if report_layer is not None:
                    audit_no_go = True
                    local.setdefault("audit_failures", []).append("control_report_layer_present")
            else:
                if not isinstance(report_layer, Mapping):
                    audit_no_go = True
                    local.setdefault("audit_failures", []).append("instrumented_report_layer_missing")
                else:
                    layer_validation = validate_report_only_layer_catalog(
                        report_layer.get("catalog", {})
                    )
                    local["report_layer"] = layer_validation
                    if not layer_validation["audit_valid"]:
                        audit_no_go = True
                    post_catalog = report_layer.get("post_catalog")
                    if (
                        not isinstance(post_catalog, Mapping)
                        or post_catalog != report_layer.get("catalog")
                    ):
                        audit_no_go = True
                        local.setdefault("audit_failures", []).append(
                            "instrumented_report_layer_postrun_mismatch"
                        )
            parsed[treatment] = {
                "transitions": transitions,
                "evidence": evidence,
                "local": local,
                "provisional": provisional,
            }
            evaluations[treatment] = local
        if runtime_error:
            return {
                "components": {
                    "runtime_error": True,
                    "audit_no_go": audit_no_go,
                    "physical_passed": False,
                },
                "decision": "PROBE_RUNTIME_ERROR",
                "evaluations": evaluations,
            }
        if set(parsed) != set(TREATMENTS):
            audit_no_go = True
        if set(parsed) == set(TREATMENTS):
            control_identity = _comparable_runtime_identity(
                parsed["control"]["evidence"].get("runtime_identity_pre")
            )
            instrumented_identity = _comparable_runtime_identity(
                parsed["instrumented"]["evidence"].get("runtime_identity_pre")
            )
            if control_identity != instrumented_identity:
                audit_no_go = True
                evaluations["cross_treatment_identity"] = {"audit_valid": False}
            parity = evaluate_control_instrumented_nonperturbation(
                parsed["control"]["transitions"],
                parsed["instrumented"]["transitions"],
                comparison_tolerances=diagnostic["comparison_tolerances"],
            )
            evaluations["control_instrumented_nonperturbation"] = parity
            if not parity["audit_valid"]:
                audit_no_go = True
            contacts = _parent_recompute_instrumented_contacts(
                parsed["instrumented"]["transitions"],
                parsed["instrumented"]["evidence"],
                protocol=protocol,
            )
            evaluations["instrumented_contacts"] = contacts
            if not contacts["audit_valid"]:
                audit_no_go = True
            else:
                physical = evaluate_native_lift_pour_trace(
                    contacts["transitions"],
                    retention_steps=int(diagnostic["retention_steps"]),
                    rise_threshold_m=float(diagnostic["rise_threshold_m"]),
                    maximum_production_steps=int(diagnostic["maximum_production_steps"]),
                    stable_supported_steps=int(diagnostic["stable_supported_steps"]),
                    stable_linear_speed_m_s=float(diagnostic["stable_linear_speed_m_s"]),
                    stable_angular_speed_degrees_s=float(
                        diagnostic["stable_angular_speed_degrees_s"]
                    ),
                    stable_origin_displacement_m=float(
                        diagnostic["stable_origin_displacement_m"]
                    ),
                    post_pour_rotation_degrees=float(
                        diagnostic["post_pour_rotation_degrees"]
                    ),
                    initial_support_activation_max_absent_reports=int(
                        protocol["initial_support_activation_max_absent_reports"]
                    ),
                    protocol=protocol,
                )
                evaluations["instrumented_physical"] = physical
                control_source = evaluations["control"].get("evaluations", {}).get(
                    "source_contract", {}
                )
                instrumented_source = evaluations["instrumented"].get("evaluations", {}).get(
                    "source_contract", {}
                )
                physical_passed = bool(
                    isinstance(control_source, Mapping)
                    and control_source.get("physical_valid") is True
                    and isinstance(instrumented_source, Mapping)
                    and instrumented_source.get("physical_valid") is True
                    and contacts["support_lifecycle"].get("support_valid") is True
                    and physical["physical_passed"] is True
                )
                if not physical["audit_valid"]:
                    audit_no_go = True
    except RuntimeError:
        runtime_error = True
    except (KeyError, TypeError, ValueError) as exc:
        audit_no_go = True
        evaluations["parent_recalculation_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    components = {
        "runtime_error": runtime_error,
        "audit_no_go": audit_no_go,
        "physical_passed": physical_passed,
    }
    return {
        "components": components,
        "decision": select_decision(components),
        "evaluations": evaluations,
    }


def _decoded_video_frame_count(video_path: Path) -> int:
    try:
        import cv2
    except BaseException as exc:
        raise ValueError("native_unbound_video_decode_unavailable") from exc
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise ValueError("native_unbound_video_decode_failed")
        count = 0
        while True:
            decoded, frame = capture.read()
            if not decoded:
                break
            if frame is None:
                raise ValueError("native_unbound_video_decode_failed")
            count += 1
        return count
    finally:
        capture.release()


def _validate_video_artifacts(
    treatment_dir: Path,
    provisional: Mapping[str, Any],
    *,
    sample_every_transitions: int | None = None,
    trace_records: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    evidence = provisional.get("runtime_evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("native_unbound_video_evidence_missing")
    artifacts = evidence.get("video_artifacts")
    map_path = treatment_dir / VIDEO_MAP_BASENAME
    cadence = (
        evidence.get("video_sample_every_transitions")
        if sample_every_transitions is None
        else sample_every_transitions
    )
    if (
        not isinstance(artifacts, Mapping)
        or type(cadence) is not int
        or cadence <= 0
    ):
        raise ValueError("native_unbound_video_artifact_missing")
    if (
        provisional.get("artifacts", {}).get("video") != artifacts.get("video")
        or provisional.get("artifacts", {}).get("video_frame_map")
        != artifacts.get("frame_map")
    ):
        raise ValueError("native_unbound_video_manifest_invalid")
    try:
        video_artifact = _validate_artifact_manifest_record(
            treatment_dir,
            artifacts.get("video"),
            expected_path=VIDEO_BASENAME,
        )
        map_artifact = _validate_artifact_manifest_record(
            treatment_dir,
            artifacts.get("frame_map"),
            expected_path=VIDEO_MAP_BASENAME,
        )
    except ValueError as exc:
        raise ValueError("native_unbound_video_artifact_manifest_invalid") from exc
    if video_artifact["byte_count"] <= 0:
        raise ValueError("native_unbound_video_artifact_manifest_invalid")
    frame_map = load_strict_json_object(map_path)
    frames = frame_map.get("frames") if isinstance(frame_map, Mapping) else None
    if (
        frame_map.get("schema_version") != 1
        or not isinstance(frames, list)
        or not frames
        or frame_map.get("treatment") != provisional.get("treatment")
        or frame_map.get("run_nonce") != provisional.get("run_nonce")
        or frame_map.get("parent_pid") != provisional.get("parent_pid")
        or frame_map.get("child_pid") != provisional.get("child_pid")
        or frame_map.get("run_id") != provisional.get("run_id")
        or artifacts.get("frame_count") != len(frames)
        or video_artifact != provisional.get("artifacts", {}).get("video")
        or map_artifact != provisional.get("artifacts", {}).get("video_frame_map")
    ):
        raise ValueError("native_unbound_video_map_invalid")
    for index, frame in enumerate(frames):
        if (
            not isinstance(frame, Mapping)
            or frame.get("video_frame_index") != index
            or type(frame.get("transition_index")) is not int
            or frame["transition_index"] < 0
            or frame["transition_index"] % cadence != 0
            or type(frame.get("world_index")) is not int
        ):
            raise ValueError("native_unbound_video_map_invalid")
    if (
        trace_records is None
        or not isinstance(trace_records, Sequence)
        or isinstance(trace_records, (str, bytes, bytearray))
    ):
        raise ValueError("native_unbound_video_map_trace_missing")
    transitions = _extract_transitions(trace_records)
    expected_frames = []
    for index, transition in enumerate(transitions):
        if (
            not isinstance(transition, Mapping)
            or transition.get("transition_index") != index
            or type(transition.get("world_index")) is not int
            or type(transition.get("state_present")) is not bool
        ):
            raise ValueError("native_unbound_video_map_trace_mismatch")
        if transition["state_present"] and index % cadence == 0:
            expected_frames.append(
                {
                    "video_frame_index": len(expected_frames),
                    "transition_index": index,
                    "world_index": transition["world_index"],
                }
            )
    if frames != expected_frames:
        raise ValueError("native_unbound_video_map_trace_mismatch")
    if _decoded_video_frame_count(treatment_dir / VIDEO_BASENAME) != len(frames):
        raise ValueError("native_unbound_video_decoded_frame_count_mismatch")


def _run_parent(args: argparse.Namespace) -> int:
    parent_pid = os.getpid()
    diagnostics_enabled = runtime_diagnostics_enabled()
    try:
        args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        os.chmod(args.out_dir, 0o700)
    except FileExistsError:
        print(
            f"native unbound lift probe refused existing output: {args.out_dir}",
            file=sys.stderr,
            flush=True,
        )
        return 2
    child_results: dict[str, dict[str, Any]] = {}
    parent_artifacts: dict[str, Any] = {}
    parent_error = None
    frozen = None
    parent_identity = None
    try:
        frozen = freeze_diagnostic_config(
            args.config, production_config_path=PRODUCTION_CONFIG
        )
        child_timeout_seconds = float(
            frozen["config"]["diagnostic"]["child_timeout_seconds"]
        )
        if args.timeout_seconds is not None and not math.isclose(
            args.timeout_seconds,
            child_timeout_seconds,
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise ValueError("native_unbound_timeout_contract_mismatch")
        parent_identity = build_parent_identity(frozen["config"])
        run_nonce = secrets.token_hex(16)
        launch_allowed = True
        for treatment in TREATMENTS:
            treatment_dir = args.out_dir / treatment
            frozen_path = write_frozen_config(frozen["canonical_bytes"], treatment_dir)
            command = build_child_command(
                treatment=treatment,
                frozen_config_path=frozen_path,
                treatment_dir=treatment_dir,
                run_nonce=run_nonce,
                parent_pid=parent_pid,
                expected_config_sha256=frozen["sha256"],
            )
            stdout_path = treatment_dir / "child.stdout.log"
            stderr_path = treatment_dir / "child.stderr.log"
            result: dict[str, Any] = {
                "command": command,
                "process_runtime_error": False,
                "provisional": None,
                "trace": [],
                "cleanup": None,
                "process": {},
            }
            if not launch_allowed:
                result["process_runtime_error"] = True
                result["process"] = {"status": "previous_child_not_quiescent"}
                child_results[treatment] = result
                continue
            process = None
            timed_out = False
            termination = None
            diagnostic_stack_dump_requested = False
            returncode = 127
            try:
                if build_parent_identity(frozen["config"]) != parent_identity:
                    raise RuntimeError("parent_identity_changed_before_child")
                with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
                    process = subprocess.Popen(
                        command,
                        cwd=str(treatment_dir),
                        env={
                            **os.environ,
                            "PYTHONUNBUFFERED": "1",
                            "PYTHONPATH": os.pathsep.join(
                                filter(
                                    None,
                                    (str(REPO_ROOT), os.environ.get("PYTHONPATH", "")),
                                )
                            ),
                        },
                        stdout=stdout,
                        stderr=stderr,
                        start_new_session=True,
                    )
                    child_pid = int(process.pid)
                    try:
                        returncode = int(process.wait(timeout=child_timeout_seconds))
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        diagnostic_stack_dump_requested = request_runtime_diagnostic_stack_dump(
                            process,
                            diagnostics_enabled=diagnostics_enabled,
                            stderr_path=stderr_path,
                        )
                        termination = terminate_process_group(process)
                        returncode = (
                            int(process.returncode)
                            if process.returncode is not None
                            else -signal.SIGKILL
                        )
                if build_parent_identity(frozen["config"]) != parent_identity:
                    raise RuntimeError("parent_identity_changed_during_child")
                if timed_out or returncode != 0:
                    raise RuntimeError("child_process_failed")
                validate_process_quiescence(process, collector_closed=None)
                artifacts = _validate_child_artifacts(
                    treatment_dir=treatment_dir,
                    treatment=treatment,
                    run_nonce=run_nonce,
                    parent_pid=parent_pid,
                    child_pid=child_pid,
                    config_sha256=frozen["sha256"],
                )
                if treatment == "instrumented" and artifacts["provisional"].get("runtime_status") == "ok":
                    _validate_video_artifacts(
                        treatment_dir,
                        artifacts["provisional"],
                        sample_every_transitions=int(
                            frozen["config"]["diagnostic"]["video"][
                                "sample_every_transitions"
                            ]
                        ),
                        trace_records=artifacts["trace"],
                    )
                quiescence = validate_process_quiescence(
                    process, collector_closed=artifacts["cleanup"]["collector_closed"]
                )
                result.update(artifacts)
                result["process"] = {
                    "returncode": returncode,
                    "timed_out": timed_out,
                    "timeout_seconds": child_timeout_seconds,
                    "termination": termination,
                    "diagnostic_stack_dump_requested": diagnostic_stack_dump_requested,
                    "quiescence": quiescence,
                    "child_pid": child_pid,
                }
            except BaseException as exc:
                if process is not None:
                    try:
                        cleanup_result = cleanup_process_group_after_validation_error(process)
                        termination = cleanup_result["termination"]
                    except BaseException as cleanup_exc:
                        termination = f"cleanup_error:{type(cleanup_exc).__name__}"
                if process is not None and process.returncode is not None:
                    returncode = int(process.returncode)
                result["process_runtime_error"] = True
                result["process"] = {
                    "returncode": returncode,
                    "timed_out": timed_out,
                    "timeout_seconds": (
                        child_timeout_seconds if "child_timeout_seconds" in locals() else None
                    ),
                    "termination": termination,
                    "diagnostic_stack_dump_requested": diagnostic_stack_dump_requested,
                    "error": f"{type(exc).__name__}:{exc}",
                    "child_pid": None if process is None else int(process.pid),
                }
                launch_allowed = False
            result["treatment_tree"] = _validate_treatment_tree(treatment_dir)
            result["parent_identity"] = parent_identity
            child_results[treatment] = result
            parent_artifacts[treatment] = {
                "frozen_config": _artifact_record(frozen_path, relative_to=args.out_dir),
                "child_stdout": _artifact_record(stdout_path, relative_to=args.out_dir)
                if stdout_path.is_file()
                else None,
                "child_stderr": _artifact_record(stderr_path, relative_to=args.out_dir)
                if stderr_path.is_file()
                else None,
            }
        recalculated = recompute_parent_evidence(
            child_results,
            config=frozen["config"],
            parent_identity=parent_identity,
            expected_config_sha256=frozen["sha256"],
        )
    except BaseException as exc:
        parent_error = f"{type(exc).__name__}:{exc}"
        components = {"runtime_error": True, "audit_no_go": False, "physical_passed": False}
        recalculated = {
            "components": components,
            "decision": select_decision(components),
            "evaluations": {},
        }
    report = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "finalized_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": recalculated["decision"],
        "components": recalculated["components"],
        "parent_recalculation": recalculated["evaluations"],
        "parent_pid": parent_pid,
        "parent_error": parent_error,
        "parent_identity": parent_identity,
        "frozen_config": (
            None
            if frozen is None
            else {
                key: value
                for key, value in frozen.items()
                if key not in {"config", "canonical_bytes"}
            }
        ),
        "child_results": child_results,
        "artifacts": parent_artifacts,
        "runtime_launched": bool(child_results),
        "gpu_launched": False,
    }
    atomic_create_json(args.out_dir / FINAL_REPORT_BASENAME, report)
    print(
        f"native unbound lift probe decision={report['decision']} out={args.out_dir / FINAL_REPORT_BASENAME}",
        flush=True,
    )
    return 0 if report["decision"] != "PROBE_RUNTIME_ERROR" else 2


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--runtime-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--treatment", choices=TREATMENTS, help=argparse.SUPPRESS)
    parser.add_argument("--frozen-config", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--run-nonce", default="", help=argparse.SUPPRESS)
    parser.add_argument("--parent-pid", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--expected-config-sha256", default="", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if args.timeout_seconds is not None and (
        not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0
    ):
        parser.error("timeout must be finite and positive")
    if args.runtime_child:
        if (
            args.treatment not in TREATMENTS
            or args.frozen_config is None
            or not args.run_nonce
            or args.parent_pid <= 0
            or not _is_sha256(args.expected_config_sha256)
            or not args.out_dir.is_dir()
        ):
            parser.error("runtime child identity arguments are incomplete")
        args.frozen_config = args.frozen_config.resolve()
        if not args.frozen_config.is_file():
            parser.error("runtime child frozen config is missing")
    else:
        if not args.config.is_file():
            parser.error(f"config not found: {args.config}")
        if any(
            (
                args.treatment is not None,
                args.frozen_config is not None,
                bool(args.run_nonce),
                args.parent_pid != 0,
                bool(args.expected_config_sha256),
            )
        ):
            parser.error("runtime child arguments are parent-managed")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_runtime_child(args) if args.runtime_child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
