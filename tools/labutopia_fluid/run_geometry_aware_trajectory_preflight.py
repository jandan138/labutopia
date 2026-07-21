#!/usr/bin/env python3
"""Measure the frozen geometry-aware trajectory without source interaction."""

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
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ISAAC_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
PARENT_HOST_PYTHON_REQUIRES_PXR = True
PARENT_HOST_PYTHON_REQUIREMENT = (
    "The parent identity preflight must run under a host Python with pxr; "
    "the runtime child remains pinned to DEFAULT_ISAAC_PYTHON and constructs "
    "SimulationApp before recomputing the full identity."
)
CHILD_BOOTSTRAP_ORDER = (
    "owner_create",
    "simulation_app_create",
    "full_identity_recompute",
    "runtime_measurement",
)
DEFAULT_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_geometry_aware_trajectory_preflight_600hz_step600_layout_v1.yaml"
)
ASSET_PATH = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
ROBOT_PATH = REPO_ROOT / "assets/robots/Franka.usd"

EXPECTED_CONFIG_SHA256 = (
    "0f0f37df41fe1eb2eb3ed09a72314f78304f1ac20a7ebbccabae80ee1f46cd31"
)
EXPECTED_ASSET_SHA256 = (
    "7c7667850dfc80a1d04c8649657cf9d9f5369b82e21f97b3d5c87c07ca218b02"
)
EXPECTED_ROBOT_SHA256 = (
    "312a326e338949fb40fd245886508cc52cc47e2bebd696e99c7dcdd3d3a7f90b"
)
EXPECTED_ISAAC_PYTHON_SHA256 = (
    "5004a4e785f05dd493882e18bfd70c73a3683fc37d680c65d389fb1d49d82e58"
)
PINNED_RUNTIME_DATA_SHA256 = {
    "robots/franka/lula_franka_gen.urdf": (
        "e9024642e7952cbcaec0ae14425bf1cd19d674d3c98eeef3793913f63a8101b6"
    ),
    "robots/franka/rmpflow/franka_rmpflow_common.yaml": (
        "bc9953bda98f89d5a0193e711bbf872466a77e0a426eede4a824b06e6b7f8083"
    ),
    "robots/franka/rmpflow/robot_descriptor.yaml": (
        "f91201b9270bea28fe72ae5466365ba410b373e0e46de7ec3fe36c0af9d2dc59"
    ),
}
PINNED_USD_COMPOSITION_SHA256 = {
    "assets/chemistry_lab/lab_001_fluid_eval/dependencies/lab_001_level1_pour_support_aligned_v1_20260712/lab_001_level1_pour_support_aligned_v1.usda": "3cd4f73913a600f2ac19c490080ac17ffcd395072a1e54101960803e8fa9939b",
    "assets/chemistry_lab/lab_001_fluid_eval/dependencies/lab_001_level1_pour_support_aligned_v1_20260712/level1_pour_support_aligned_overlay_v1.usda": "b56ae419d3adeb1c49972e6b699e5369c837deb4785279f71068b633041b5094",
    "assets/chemistry_lab/lab_001_fluid_eval/dependencies/lab_001_localized_20260707/0/sektion_cabinet_collisions.usd": "02358840d0491aef8c1a529ec90fa4a129f80f96014339aef09a9ce700caf2ed",
    "assets/chemistry_lab/lab_001_fluid_eval/dependencies/lab_001_localized_20260707/0/sektion_cabinet_instanceable.usd": "5f6a5646f8e51b5ffce1df2cca84763c621a68efea2ac4f629990a93e69a04b4",
    "assets/chemistry_lab/lab_001_fluid_eval/dependencies/lab_001_localized_20260707/0/sektion_cabinet_visuals.usd": "c1aacb0fb999e9d8c6e17ac003abf9ae55aefd26008a9e6e45f8d2852849c7dd",
    "assets/chemistry_lab/lab_001_fluid_eval/dependencies/lab_001_localized_20260707/lab_001.usd": "b3861b5a17945abe401062a04125969c3a63b0f8a0a5ce0026a461dbdfc935f2",
    "assets/chemistry_lab/lab_001_fluid_eval/dependencies/lab_001_localized_20260707/lab_001_level1_pour_tabletop_with_liquid.usd": "77607b6bdf3b6cba419e1bc17943bdb3e220b497a77e98d7665e98f779406211",
    "assets/chemistry_lab/lab_001_fluid_eval/lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda": EXPECTED_ASSET_SHA256,
    "assets/chemistry_lab/lab_001_fluid_eval/lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_v1.usda": "d2090f9688764e819b6ea3d2f9f9c4e98b9c78495af6cbba36a05983228d9386",
    "assets/chemistry_lab/lab_001_fluid_eval/lab_001_level1_pour_interndata_contact_grasp_v1.usda": "a84822c76b4a544d6ba6ecb9f9cb25b5bef4e654c813089b704cb937a733267b",
    "assets/chemistry_lab/lab_001_fluid_eval/lab_001_level1_pour_interndata_liquid_v1.usda": "9ad95cc881c5899ff8258c3a1ccf4be52e3cc6a9d41f73042c943840c5d5de23",
    "assets/robots/Franka.usd": EXPECTED_ROBOT_SHA256,
}
PINNED_IMPLEMENTATION_SHA256 = {
    "controllers/atomic_actions/contact_pick_controller.py": (
        "7dd7a60ce67ffbbd799a6e9c89ccb16970d72d91ae2fb0f26320123426770594"
    ),
    "factories/robot_factory.py": (
        "0d6996013ee3a1e5e17966c657dd4020cae3b916fe08edfb8a26eb60774ea09d"
    ),
    "factories/task_factory.py": (
        "15293413067f6609aef10f80f0c7e2c10ea980d6c338a0e15fcc801acccf15aa"
    ),
    "isaacsim_compat.py": (
        "e6a25eac39cdd84fe3a328a659b033ec4d55279a38a2bfbc807ea15a4c944dd1"
    ),
    "robots/franka/franka.py": (
        "c406af2432eeb9bcefd4b4f0c0745f08afb54b635702878ae6c94f81a168f7a0"
    ),
    "robots/franka/rmpflow_controller.py": (
        "12464bf5294a39c8393332d6acc3dc38bb97b463f79a13406475a0ece1be9d7d"
    ),
    "tasks/base_task.py": (
        "bcdbefcb975d1d2e13cc9b24d08ccceb3281bcdabd4f949443cd7bcb584f8933"
    ),
    "tasks/pickpour_task.py": (
        "c5fe9242bf2c9bec28034fa168e1473131512ddbc6d71e1c42e6010f64475a53"
    ),
    "tools/labutopia_fluid/run_contact_grasp_feasibility_probe.py": (
        "5c5f224a48061cc2978377a1061ecef669dbcabed18af834af7eacfa4dd95cb4"
    ),
    "utils/fixed_frame_pose.py": (
        "40283137517b3e89c4723e62a65b31952a5e0367a5e1779ec695d50a8aa21b43"
    ),
    "utils/franka_gripper_contract.py": (
        "ceafc4cae73b1fb3dfef53551c33928a3e33337ca4b782e8d338b0ac61df9148"
    ),
    "utils/isaac_fluid_evaluation.py": (
        "bd7d3c3eea8c680bf443aac4bf3560df5a8bc327d26afb2366594f782ebd899a"
    ),
    "utils/object_utils.py": (
        "6d45e2531949dc35e10c1d1bbab6c686cb3c5ad7507267484c12ebff5397d2d0"
    ),
}
SELF_RELATIVE_PATH = "tools/labutopia_fluid/run_geometry_aware_trajectory_preflight.py"
DIRECT_PROJECT_IMPORT_PATHS = (
    "controllers/atomic_actions/contact_pick_controller.py",
    "factories/robot_factory.py",
    "factories/task_factory.py",
    "isaacsim_compat.py",
    "robots/franka/rmpflow_controller.py",
    "tools/labutopia_fluid/run_contact_grasp_feasibility_probe.py",
    "utils/isaac_fluid_evaluation.py",
    "utils/object_utils.py",
)
WORKSPACE_DRIFT_SEAL = {
    "authority": "workspace_pre_post_drift_seal_v1",
    "description": "Workspace pre/post-run drift seal; not an external trust root.",
    "external_trust_root": False,
}

MANIFEST_TYPE = "geometry_aware_trajectory_preflight_v1"
PROFILE = "geometry_aware_trajectory_preflight_v1"
GO_DECISION = "GEOMETRY_AWARE_TRAJECTORY_PREFLIGHT_GO"
NO_GO_DECISION = "GEOMETRY_AWARE_TRAJECTORY_PREFLIGHT_NO_GO"
RUNTIME_ERROR_DECISION = "PROBE_RUNTIME_ERROR"
CONTROLLED_PREFLIGHT_GO_DECISION = (
    "GEOMETRY_AWARE_CONTROLLED_CONTACT_PREFLIGHT_GO"
)
CONTROLLED_PREFLIGHT_NO_GO_DECISION = (
    "GEOMETRY_AWARE_CONTROLLED_CONTACT_PREFLIGHT_NO_GO"
)
FINAL_REPORT_BASENAME = "report.json"
RUNTIME_REPORT_BASENAME = "runtime_report.json"
OWNER_BASENAME = ".trajectory-preflight-owner.json"
STDOUT_BASENAME = "child.stdout.log"
STDERR_BASENAME = "child.stderr.log"

SIDES = ("left", "right")
ENVIRONMENT_CLEARANCE_NAMES = (
    "hand_to_source",
    "swept_bodies_to_table",
    "source_to_unrelated_robot_links",
)
EXPECTED_TOOL_ORIENTATION_WXYZ = [0.0, 0.0, 1.0, 0.0]
EXPECTED_GRASP_OFFSET_OBJECT_M = [0.0, 0.0, 0.0]
EXPECTED_APPROACH_DIRECTION_WORLD = [0.0, 0.0, -1.0]
EXPECTED_CONTROL_TO_TOOL_MATRIX_M = [
    [-1.0, 0.0, 0.0, 0.0],
    [0.0, -1.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, -0.0034, 1.0],
]
EXPECTED_CALIBRATION_TARGETS_M = [0.040, 0.039, 0.038, 0.037]
EXPECTED_CALIBRATION_BODY_SIZE_M = [0.002, 0.070, 0.002]
EXPECTED_CALIBRATION_BODY_TRANSLATION_TOOL_M = [0.009, 0.0, 0.006]
EXPECTED_FINGER_BODY_PATHS = {
    "left": "/World/Franka/panda_leftfinger",
    "right": "/World/Franka/panda_rightfinger",
}
EXPECTED_TABLE_BODY_PATH = "/World/table"
EXPECTED_COLLIDERLESS_ROBOT_BODY_PATHS = ("/World/Franka/panda_link8",)
CALIBRATION_BODY_PATH = "/World/TrajectoryPreflight/CalibrationBody"
CALIBRATION_SCOPE_PATH = "/World/TrajectoryPreflight"
CALIBRATION_FACE_SAMPLE_IDS = (
    "center",
    "x_low_z_low",
    "x_low_z_high",
    "x_high_z_low",
    "x_high_z_high",
)
TRACKED_ACTION_KINDS = {"ARM_INSERT", "ARM_SETTLE"}
COOKED_GAP_ERROR_FLOOR_M = 1.0e-6
COOKED_AABB_PRECISION = {
    "value_type": "float32",
    "authority": "physx_property_query_float32_local_aabb_v1",
}
STATIC_COOKED_QUERY_AUTHORITY = (
    "physx_property_query_transient_disabled_rigid_body_v1"
)
SOURCE_ISOLATION_CHECKPOINTS = (
    "post_task_reset_1",
    "post_task_reset_2",
    "pre_world_play",
    "pre_roll",
    "pre_first_shadow_action",
)


class MeasurementNoGo(RuntimeError):
    def __init__(self, reason: str, evidence: Mapping[str, Any]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.evidence = dict(evidence)


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
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_json_native(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_native(value.tolist())
    if isinstance(value, np.generic):
        return _json_native(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("trajectory_preflight_json_nonfinite")
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
        if "nonfinite" in str(exc).lower() or "nan" in str(exc).lower():
            raise ValueError("trajectory_preflight_json_nonfinite") from exc
        raise
    return (encoded + "\n").encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value).rstrip(b"\n")).hexdigest()


def atomic_create_json(path: str | os.PathLike[str], value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise TypeError("trajectory_preflight_json_mapping_required")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json_bytes(value, indent=2)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise FileExistsError(
                f"trajectory_preflight_output_exists:{output}"
            ) from exc
        directory_descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _strict_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_key:{key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"nonfinite_constant:{value}")


def _validate_json_tree(value: Any) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_json_tree(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_tree(item)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite_number")


def _load_strict_json_object_bytes(
    payload: bytes, *, source_name: str, error_code: str
) -> dict[str, Any]:
    try:
        if not payload or not payload.endswith(b"\n") or b"\r" in payload:
            raise ValueError("line_contract")
        decoded = payload.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_strict_object_pairs,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(value, dict):
            raise TypeError("mapping_required")
        _validate_json_tree(value)
        return value
    except (TypeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{error_code}:{source_name}") from exc


def _load_strict_json_object(path: Path, *, error_code: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{error_code}:{path}") from exc
    return _load_strict_json_object_bytes(
        payload, source_name=str(path), error_code=error_code
    )


def load_runtime_report_bytes(
    payload: bytes, *, source_name: str
) -> dict[str, Any]:
    if not isinstance(payload, bytes) or not isinstance(source_name, str):
        raise ValueError(f"trajectory_preflight_runtime_report_invalid:{source_name}")
    report = _load_strict_json_object_bytes(
        payload,
        source_name=source_name,
        error_code="trajectory_preflight_runtime_report_invalid",
    )
    if (
        report.get("manifest_type") != MANIFEST_TYPE
        or report.get("schema_version") != 1
        or (
            report.get("lifecycle_status"), report.get("shutdown_status")
        )
        not in {
            ("measurement_complete_pending_application_close", "pending"),
            ("runtime_error_pending_application_close", "pending"),
            ("measurement_complete_application_closed", "application_closed"),
            ("runtime_error_application_closed", "application_closed"),
            ("runtime_error_application_unavailable", "application_not_created"),
            ("runtime_error_application_close_failed", "application_close_failed"),
        }
    ):
        raise ValueError(f"trajectory_preflight_runtime_report_invalid:{source_name}")
    return report


def load_runtime_report(path: str | os.PathLike[str]) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise ValueError(
            f"trajectory_preflight_runtime_report_invalid:{source}"
        ) from exc
    return load_runtime_report_bytes(payload, source_name=str(source))


def runtime_report_artifact_from_bytes(
    payload: bytes, *, relative_path: str
) -> dict[str, Any]:
    if not isinstance(payload, bytes) or not isinstance(relative_path, str):
        raise TypeError("trajectory_preflight_runtime_artifact_invalid")
    return {
        "path": relative_path,
        "byte_count": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "authority": "single_post_quiescence_byte_buffer_v1",
    }


def load_owner(path: str | os.PathLike[str]) -> dict[str, Any]:
    owner = _load_strict_json_object(
        Path(path), error_code="trajectory_preflight_owner_invalid"
    )
    if set(owner) != {"pid", "run_id", "run_identity_sha256"}:
        raise ValueError(f"trajectory_preflight_owner_invalid:{path}")
    return owner


def _finite_number(value: Any, *, positive: bool = False, nonnegative: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
    ):
        raise ValueError("finite_number_required")
    result = float(value)
    if positive and result <= 0.0:
        raise ValueError("positive_number_required")
    if nonnegative and result < 0.0:
        raise ValueError("nonnegative_number_required")
    return result


def _optional_nonnegative(value: Any) -> float | None:
    try:
        return _finite_number(value, nonnegative=True)
    except ValueError:
        return None


def _finite_array(value: Any, shape: tuple[int, ...]) -> np.ndarray | None:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if result.shape != shape or not np.isfinite(result).all():
        return None
    return result


def derive_opening_axis_world(
    tool_world_matrix: Sequence[Sequence[float]],
    tool_axis: Sequence[float] = (0.0, 1.0, 0.0),
) -> list[float]:
    matrix = _finite_array(tool_world_matrix, (4, 4))
    axis = _finite_array(tool_axis, (3,))
    if (
        matrix is None
        or axis is None
        or not np.allclose(
            matrix[:, 3], [0.0, 0.0, 0.0, 1.0], rtol=0.0, atol=1.0e-12
        )
    ):
        raise ValueError("trajectory_preflight_opening_axis_invalid")
    axis_norm = float(np.linalg.norm(axis))
    if axis_norm <= 1.0e-12:
        raise ValueError("trajectory_preflight_opening_axis_invalid")
    world = (axis / axis_norm) @ matrix[:3, :3]
    world_norm = float(np.linalg.norm(world))
    if world_norm <= 1.0e-12 or not math.isfinite(world_norm):
        raise ValueError("trajectory_preflight_opening_axis_invalid")
    return (world / world_norm).tolist()


def derive_opening_axis_from_orientation_wxyz(
    orientation_wxyz: Sequence[float],
    tool_axis: Sequence[float] = (0.0, 1.0, 0.0),
) -> list[float]:
    from scipy.spatial.transform import Rotation

    quaternion = _finite_array(orientation_wxyz, (4,))
    axis = _finite_array(tool_axis, (3,))
    if quaternion is None or axis is None:
        raise ValueError("trajectory_preflight_opening_axis_invalid")
    quaternion_norm = float(np.linalg.norm(quaternion))
    axis_norm = float(np.linalg.norm(axis))
    if quaternion_norm <= 1.0e-12 or axis_norm <= 1.0e-12:
        raise ValueError("trajectory_preflight_opening_axis_invalid")
    rotation = Rotation.from_quat(
        (quaternion / quaternion_norm)[[1, 2, 3, 0]]
    ).as_matrix()
    world = (axis / axis_norm) @ rotation.T
    return (world / np.linalg.norm(world)).tolist()


def cooked_catalog_validation_failures(catalog: Any) -> list[str]:
    if not isinstance(catalog, Mapping):
        return ["catalog_not_mapping"]
    failures = []
    body_path = catalog.get("body_path")
    colliders = catalog.get("colliders")
    count = catalog.get("collider_count")
    precision = catalog.get("cooked_aabb_precision")
    colliders_are_sequence = isinstance(colliders, Sequence) and not isinstance(
        colliders, (str, bytes)
    )
    if not isinstance(body_path, str) or not body_path.startswith("/"):
        failures.append("body_path")
    if not colliders_are_sequence:
        failures.append("colliders_not_sequence")
    elif not colliders:
        failures.append("colliders_empty")
    if type(count) is not int or (
        colliders_are_sequence and count != len(colliders)
    ):
        failures.append("collider_count")
    if precision != COOKED_AABB_PRECISION:
        failures.append("cooked_aabb_precision")
    if catalog.get("rigid_body_error") is not None:
        failures.append("rigid_body_error")
    if bool(catalog.get("collider_errors")):
        failures.append("collider_errors")
    known_error_keys = {"rigid_body_error", "collider_errors"}
    if any(
        key not in known_error_keys
        and "error" in str(key).lower()
        and value not in (None, [], {})
        for key, value in catalog.items()
    ):
        failures.append("unexpected_error_field")

    paths = []
    for index, collider in enumerate(colliders if colliders_are_sequence else []):
        if not isinstance(collider, Mapping):
            failures.append(f"collider_{index}_not_mapping")
            continue
        path = collider.get("path")
        low = _finite_array(collider.get("aabb_local_min_m"), (3,))
        high = _finite_array(collider.get("aabb_local_max_m"), (3,))
        volume = _optional_nonnegative(collider.get("volume_m3"))
        offset_record = collider.get("contact_offset")
        offset_authority_valid = bool(
            isinstance(offset_record, Mapping)
            and set(offset_record) == {"contact_offset_m", "authority"}
            and offset_record.get("authority")
            in {"authored", "effective", "unresolved"}
            and (
                _optional_nonnegative(offset_record.get("contact_offset_m"))
                is not None
                or (
                    offset_record.get("contact_offset_m") is None
                    and offset_record.get("authority") == "unresolved"
                )
            )
        )
        if not isinstance(path, str) or not path.startswith("/"):
            failures.append(f"collider_{index}_path")
        else:
            paths.append(path)
        if low is None or high is None:
            failures.append(f"collider_{index}_aabb")
        elif np.any(high < low):
            failures.append(f"collider_{index}_aabb_order")
        if volume is None:
            failures.append(f"collider_{index}_volume")
        if not offset_authority_valid:
            failures.append(f"collider_{index}_contact_offset")
    if len(set(paths)) != len(paths):
        failures.append("duplicate_collider_paths")
    return failures


def validate_cooked_catalog(catalog: Mapping[str, Any]) -> dict[str, Any]:
    failures = cooked_catalog_validation_failures(catalog)
    if failures:
        raise ValueError(
            "trajectory_preflight_cooked_catalog_invalid:" + ",".join(failures)
        )
    return dict(catalog)


def build_static_cooked_query_authority(
    *, body_path: str, collision_paths: Sequence[str]
) -> dict[str, Any]:
    if (
        not isinstance(body_path, str)
        or not body_path.startswith("/")
        or not isinstance(collision_paths, Sequence)
        or isinstance(collision_paths, (str, bytes))
        or not collision_paths
        or any(
            not isinstance(path, str)
            or not path.startswith("/")
            or (path != body_path and not path.startswith(body_path + "/"))
            for path in collision_paths
        )
        or len(set(collision_paths)) != len(collision_paths)
    ):
        raise ValueError("trajectory_preflight_static_cooked_query_invalid")
    return {
        "authority": STATIC_COOKED_QUERY_AUTHORITY,
        "body_path": body_path,
        "collision_paths": sorted(collision_paths),
        "rigid_body_enabled_during_query": False,
        "temporary_layer_discarded": True,
        "stage_composition_restored": True,
    }


def validate_static_cooked_catalog(
    catalog: Mapping[str, Any], *, expected_body_path: str
) -> dict[str, Any]:
    error = "trajectory_preflight_static_cooked_catalog_invalid"
    try:
        validated = validate_cooked_catalog(catalog)
        authority = validated.get("query_authority")
        if not isinstance(authority, Mapping):
            raise ValueError(error)
        expected = build_static_cooked_query_authority(
            body_path=expected_body_path,
            collision_paths=[str(collider["path"]) for collider in validated["colliders"]],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(error) from exc
    if validated.get("body_path") != expected_body_path or dict(authority) != expected:
        raise ValueError(error)
    return validated


def _colliderless_rigid_body_evidence_record(body_path: str) -> dict[str, Any]:
    return {
        "authority": "physx_property_query_clean_zero_collider_v1",
        "body_path": body_path,
        "collider_count": 0,
        "rigid_body_error": None,
        "collider_errors": [],
    }


def build_colliderless_rigid_body_evidence(
    catalog: Mapping[str, Any], *, expected_body_path: str
) -> dict[str, Any]:
    error = "trajectory_preflight_colliderless_body_invalid"
    if not isinstance(catalog, Mapping):
        raise ValueError(error)
    colliders = catalog.get("colliders")
    if (
        not isinstance(expected_body_path, str)
        or not expected_body_path.startswith("/")
        or catalog.get("body_path") != expected_body_path
        or not isinstance(colliders, Sequence)
        or isinstance(colliders, (str, bytes))
        or len(colliders) != 0
        or type(catalog.get("collider_count")) is not int
        or catalog.get("collider_count") != 0
        or catalog.get("rigid_body_error") is not None
        or catalog.get("collider_errors") not in (None, [])
        or any(
            key not in {"rigid_body_error", "collider_errors"}
            and "error" in str(key).lower()
            and value not in (None, [], {})
            for key, value in catalog.items()
        )
    ):
        raise ValueError(error)
    return _colliderless_rigid_body_evidence_record(expected_body_path)


def evaluate_calibration_collision_inventory(
    *,
    collider_records: Sequence[Mapping[str, Any]],
    intended_finger_collider_paths: Mapping[str, Sequence[str]],
    colliderless_body_paths: Sequence[str],
) -> dict[str, Any]:
    failures = []
    normalized_records = []
    roles = {}
    seen_paths = set()
    colliderless = (
        sorted(colliderless_body_paths)
        if isinstance(colliderless_body_paths, Sequence)
        and not isinstance(colliderless_body_paths, (str, bytes))
        else []
    )
    if (
        len(colliderless) != len(set(colliderless))
        or any(not isinstance(path, str) or not path.startswith("/") for path in colliderless)
    ):
        failures.append("colliderless_body_paths")
    intended = []
    if (
        not isinstance(intended_finger_collider_paths, Mapping)
        or set(intended_finger_collider_paths) != set(SIDES)
    ):
        failures.append("intended_finger_collider_paths")
    else:
        for side in SIDES:
            paths = intended_finger_collider_paths.get(side)
            if (
                not isinstance(paths, Sequence)
                or isinstance(paths, (str, bytes))
                or not paths
                or any(
                    not isinstance(path, str) or not path.startswith("/")
                    for path in paths
                )
            ):
                failures.append(f"intended_finger_collider_paths.{side}")
                continue
            intended.extend(paths)
    if len(intended) != len(set(intended)):
        failures.append("duplicate_intended_finger_colliders")

    records_valid = isinstance(collider_records, Sequence) and not isinstance(
        collider_records, (str, bytes)
    )
    if not records_valid:
        failures.append("collider_records")
        collider_records = []
    for index, raw in enumerate(collider_records):
        if not isinstance(raw, Mapping):
            failures.append(f"collider_{index}")
            continue
        path = raw.get("path")
        enabled = raw.get("collision_enabled")
        owners = raw.get("rigid_body_owners_nearest_first")
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or type(enabled) is not bool
            or not isinstance(owners, Sequence)
            or isinstance(owners, (str, bytes))
        ):
            failures.append(f"collider_{index}_structure")
            continue
        if path in seen_paths:
            failures.append(f"collider_{index}_duplicate")
            continue
        seen_paths.add(path)
        normalized_owners = []
        owner_valid = True
        previous_path = path
        for owner_index, owner in enumerate(owners):
            if not isinstance(owner, Mapping):
                owner_valid = False
                break
            owner_path = owner.get("path")
            rigid_enabled = owner.get("rigid_body_enabled")
            kinematic_enabled = owner.get("kinematic_enabled")
            if (
                not isinstance(owner_path, str)
                or not owner_path.startswith("/")
                or not (
                    previous_path == owner_path
                    or previous_path.startswith(owner_path + "/")
                )
                or type(rigid_enabled) is not bool
                or type(kinematic_enabled) is not bool
            ):
                owner_valid = False
                break
            normalized_owners.append(
                {
                    "path": owner_path,
                    "rigid_body_enabled": rigid_enabled,
                    "kinematic_enabled": kinematic_enabled,
                }
            )
            previous_path = owner_path
        if not owner_valid:
            failures.append(f"collider_{index}_owners")
            continue
        nearest = normalized_owners[0] if normalized_owners else None
        if not enabled:
            role = "disabled_collider"
        elif nearest is None:
            role = "static"
        elif not nearest["rigid_body_enabled"]:
            role = "disabled_rigid_body"
        elif nearest["kinematic_enabled"]:
            role = "kinematic"
        else:
            role = "dynamic"
        if any(
            path == body_path or path.startswith(body_path + "/")
            for body_path in colliderless
        ):
            failures.append(f"collider_{index}_colliderless_body_conflict")
        roles[path] = role
        normalized_records.append(
            {
                "path": path,
                "collision_enabled": enabled,
                "rigid_body_owners_nearest_first": normalized_owners,
                "role": role,
            }
        )
    if set(intended) - set(roles):
        failures.append("intended_finger_colliders_missing")
    if any(roles.get(path) not in {"dynamic", "kinematic"} for path in intended):
        failures.append("intended_finger_colliders_not_compatible")
    payload = {
        "authority": "complete_nearest_rigid_body_owner_collider_partition_v1",
        "collider_records": sorted(normalized_records, key=lambda item: item["path"]),
        "roles_by_collider": dict(sorted(roles.items())),
        "intended_finger_colliders": sorted(intended),
        "compatible_obstacle_colliders": sorted(
            path
            for path, role in roles.items()
            if role in {"dynamic", "kinematic"} and path not in intended
        ),
        "static_obstacle_colliders": sorted(
            path for path, role in roles.items() if role == "static"
        ),
        "disabled_colliders": sorted(
            path
            for path, role in roles.items()
            if role in {"disabled_collider", "disabled_rigid_body"}
        ),
        "colliderless_body_paths": colliderless,
        "failures": failures,
        "passed": not failures,
    }
    return {**payload, "inventory_sha256": canonical_json_sha256(payload)}


def evaluate_controlled_contact_sample(
    *,
    physics_step: int,
    phase: str,
    contacts: Sequence[Mapping[str, Any]],
    known_body_paths: Sequence[str],
    known_collider_paths: Sequence[str],
    robot_body_paths: Sequence[str],
    intended_pairs: Sequence[Mapping[str, Any]],
    baseline_nonrobot_pairs: Sequence[Mapping[str, Any]],
    source_center_world_m: Sequence[float],
    source_axis_world: Sequence[float],
    grasp_height_band_m: Sequence[float],
    minimum_inward_normal_cosine: Any,
    maximum_penetration_m: Any,
    maximum_precontact_relative_speed_m_s: Any,
    maximum_close_relative_speed_m_s: Any,
    maximum_manifold_normal_impulse_n_s: Any,
) -> dict[str, Any]:
    authority = "controlled_contact_complete_manifold_v1"
    precontact_phases = {"INSERT", "SETTLE", "PRECONTACT_SETTLE"}
    close_phases = {"CLOSE", "CONTACT_SETTLE"}
    known_phases = {
        "PREGRASP",
        "ALIGN",
        *precontact_phases,
        *close_phases,
    }

    def path_set(value: Any) -> set[str] | None:
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes))
            or any(not isinstance(item, str) or not item.startswith("/") for item in value)
            or len(value) != len(set(value))
        ):
            return None
        return set(value)

    def canonical_endpoints(
        body0: str, collider0: str, body1: str, collider1: str
    ) -> tuple[tuple[str, str], tuple[str, str]]:
        return tuple(sorted(((body0, collider0), (body1, collider1))))

    bodies = path_set(known_body_paths)
    colliders = path_set(known_collider_paths)
    robot_bodies = path_set(robot_body_paths)
    center = _finite_array(source_center_world_m, (3,))
    axis = _finite_array(source_axis_world, (3,))
    height_band = _finite_array(grasp_height_band_m, (2,))
    minimum_cosine = _finite_number(minimum_inward_normal_cosine)
    penetration_limit = _finite_number(maximum_penetration_m, nonnegative=True)
    precontact_speed_limit = _finite_number(
        maximum_precontact_relative_speed_m_s, nonnegative=True
    )
    close_speed_limit = _finite_number(
        maximum_close_relative_speed_m_s, nonnegative=True
    )
    impulse_limit = _finite_number(
        maximum_manifold_normal_impulse_n_s, nonnegative=True
    )
    structure_valid = bool(
        type(physics_step) is int
        and physics_step >= 0
        and isinstance(phase, str)
        and phase in known_phases
        and bodies is not None
        and colliders is not None
        and robot_bodies is not None
        and robot_bodies <= bodies
        and center is not None
        and axis is not None
        and height_band is not None
        and height_band[0] <= height_band[1]
        and math.isclose(
            float(np.linalg.norm(axis)), 1.0, rel_tol=0.0, abs_tol=1.0e-9
        )
        and -1.0 <= minimum_cosine <= 1.0
        and isinstance(contacts, Sequence)
        and not isinstance(contacts, (str, bytes))
    )

    intended_by_pair: dict[
        tuple[tuple[str, str], tuple[str, str]], dict[str, Any]
    ] = {}
    if isinstance(intended_pairs, Sequence) and not isinstance(
        intended_pairs, (str, bytes)
    ):
        for raw in intended_pairs:
            if not isinstance(raw, Mapping):
                structure_valid = False
                continue
            side = raw.get("side")
            finger_body = raw.get("finger_body_path")
            finger_collider = raw.get("finger_collider_path")
            source_body = raw.get("source_body_path")
            source_collider = raw.get("source_collider_path")
            expected_normal = _finite_array(
                raw.get("expected_inward_normal_world"), (3,)
            )
            if (
                side not in SIDES
                or finger_body not in (robot_bodies or set())
                or source_body not in (bodies or set())
                or source_body in (robot_bodies or set())
                or finger_collider not in (colliders or set())
                or source_collider not in (colliders or set())
                or expected_normal is None
                or float(np.linalg.norm(expected_normal)) <= 1.0e-12
            ):
                structure_valid = False
                continue
            expected_normal = expected_normal / np.linalg.norm(expected_normal)
            key = canonical_endpoints(
                finger_body, finger_collider, source_body, source_collider
            )
            if key in intended_by_pair:
                structure_valid = False
                continue
            intended_by_pair[key] = {
                "side": side,
                "finger_endpoint": (finger_body, finger_collider),
                "source_endpoint": (source_body, source_collider),
                "expected_inward_normal_world": expected_normal,
            }
    else:
        structure_valid = False
    if set(record["side"] for record in intended_by_pair.values()) != set(SIDES):
        structure_valid = False

    baseline_pairs: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    if isinstance(baseline_nonrobot_pairs, Sequence) and not isinstance(
        baseline_nonrobot_pairs, (str, bytes)
    ):
        for raw in baseline_nonrobot_pairs:
            body_values = raw.get("body_paths") if isinstance(raw, Mapping) else None
            collider_values = (
                raw.get("collider_paths") if isinstance(raw, Mapping) else None
            )
            if (
                not isinstance(body_values, Sequence)
                or isinstance(body_values, (str, bytes))
                or len(body_values) != 2
                or not isinstance(collider_values, Sequence)
                or isinstance(collider_values, (str, bytes))
                or len(collider_values) != 2
                or any(body not in (bodies or set()) for body in body_values)
                or any(body in (robot_bodies or set()) for body in body_values)
                or any(
                    collider not in (colliders or set())
                    for collider in collider_values
                )
            ):
                structure_valid = False
                continue
            key = canonical_endpoints(
                str(body_values[0]),
                str(collider_values[0]),
                str(body_values[1]),
                str(collider_values[1]),
            )
            if key in baseline_pairs:
                structure_valid = False
            baseline_pairs.add(key)
    else:
        structure_valid = False

    normalized_records: list[dict[str, Any]] = []
    for raw in contacts if isinstance(contacts, Sequence) else []:
        if not isinstance(raw, Mapping):
            normalized_records.append(
                {
                    "pair": None,
                    "class": "UNKNOWN_CONTACT",
                    "side": None,
                    "manifold_points": [],
                    "aggregate_normal_impulse_n_s": None,
                    "gate_failures": ["contact_not_mapping"],
                }
            )
            continue
        body0 = raw.get("body0_path")
        body1 = raw.get("body1_path")
        collider0 = raw.get("collider0_path")
        collider1 = raw.get("collider1_path")
        paths_known = bool(
            body0 in (bodies or set())
            and body1 in (bodies or set())
            and collider0 in (colliders or set())
            and collider1 in (colliders or set())
        )
        pair = (
            canonical_endpoints(body0, collider0, body1, collider1)
            if all(
                isinstance(value, str)
                for value in (body0, collider0, body1, collider1)
            )
            else None
        )
        pair_record = (
            {
                "body_paths": [endpoint[0] for endpoint in pair],
                "collider_paths": [endpoint[1] for endpoint in pair],
            }
            if pair is not None
            else None
        )
        contact_class = "UNKNOWN_CONTACT"
        side = None
        normalized_points: list[dict[str, Any]] = []
        aggregate_impulse: float | None = None
        gate_failures: list[str] = []
        intended = intended_by_pair.get(pair) if pair is not None else None

        if not paths_known:
            gate_failures.append("unknown_path")
        elif intended is not None:
            points = raw.get("manifold_points")
            manifold_valid = bool(
                isinstance(points, Sequence)
                and not isinstance(points, (str, bytes))
                and len(points) > 0
            )
            finger_first = (body0, collider0) == intended["finger_endpoint"]
            if not finger_first and (body1, collider1) != intended["finger_endpoint"]:
                manifold_valid = False
            for point in points if manifold_valid else []:
                if not isinstance(point, Mapping):
                    manifold_valid = False
                    break
                position = _finite_array(point.get("position_m"), (3,))
                normal = _finite_array(
                    point.get("normal_body0_to_body1_world"), (3,)
                )
                try:
                    separation = _finite_number(point.get("separation_m"))
                    relative_speed = _finite_number(
                        point.get("relative_speed_m_s"), nonnegative=True
                    )
                    impulse = _finite_number(
                        point.get("normal_impulse_n_s"), nonnegative=True
                    )
                except ValueError:
                    manifold_valid = False
                    break
                if position is None or normal is None or np.linalg.norm(normal) <= 1.0e-12:
                    manifold_valid = False
                    break
                normal = normal / np.linalg.norm(normal)
                if not finger_first:
                    normal = -normal
                normal[normal == 0.0] = 0.0
                height = float((position - center) @ axis)
                normal_cosine = float(
                    normal @ intended["expected_inward_normal_world"]
                )
                penetration = max(0.0, -separation)
                normalized_points.append(
                    {
                        "position_m": position.tolist(),
                        "normal_finger_to_source_world": normal.tolist(),
                        "separation_m": separation,
                        "penetration_m": penetration,
                        "relative_speed_m_s": relative_speed,
                        "normal_impulse_n_s": impulse,
                        "source_height_m": height,
                        "inward_normal_cosine": normal_cosine,
                    }
                )
            if not manifold_valid:
                gate_failures.append("manifold_authority")
            else:
                normalized_points.sort(key=canonical_json_sha256)
                aggregate_impulse = float(
                    sum(point["normal_impulse_n_s"] for point in normalized_points)
                )
                speed_limit = (
                    precontact_speed_limit
                    if phase in precontact_phases
                    else close_speed_limit
                )
                if phase not in precontact_phases | close_phases:
                    gate_failures.append("phase")
                if any(
                    not (height_band[0] <= point["source_height_m"] <= height_band[1])
                    for point in normalized_points
                ):
                    gate_failures.append("height")
                if any(
                    point["inward_normal_cosine"] < minimum_cosine
                    for point in normalized_points
                ):
                    gate_failures.append("normal")
                if any(
                    point["penetration_m"] > penetration_limit
                    for point in normalized_points
                ):
                    gate_failures.append("penetration")
                if any(
                    point["relative_speed_m_s"] > speed_limit
                    for point in normalized_points
                ):
                    gate_failures.append("relative_speed")
                if aggregate_impulse > impulse_limit:
                    gate_failures.append("aggregate_impulse")
            side = intended["side"]
            if "manifold_authority" in gate_failures:
                contact_class = "UNKNOWN_CONTACT"
            elif gate_failures:
                contact_class = "PROHIBITED_CONTACT"
            elif phase in precontact_phases:
                contact_class = "INTENDED_PRECONTACT"
            else:
                contact_class = "INTENDED_CLOSE_CONTACT"
        elif body0 in (robot_bodies or set()) or body1 in (robot_bodies or set()):
            contact_class = "PROHIBITED_CONTACT"
            gate_failures.append("robot_pair_not_allowed")
        elif pair in baseline_pairs:
            contact_class = "BACKGROUND"
        else:
            contact_class = "PROHIBITED_CONTACT"
            gate_failures.append("new_nonrobot_pair")

        normalized_records.append(
            {
                "pair": pair_record,
                "class": contact_class,
                "side": side,
                "manifold_points": normalized_points,
                "aggregate_normal_impulse_n_s": aggregate_impulse,
                "gate_failures": sorted(set(gate_failures)),
            }
        )

    normalized_records.sort(key=canonical_json_sha256)
    class_counts = dict(
        sorted(Counter(record["class"] for record in normalized_records).items())
    )
    if not structure_valid or class_counts.get("UNKNOWN_CONTACT", 0):
        terminal_kind = "PROTOCOL_FAILURE"
    elif class_counts.get("PROHIBITED_CONTACT", 0):
        terminal_kind = "PHYSICAL_CONTACT_FAILURE"
    else:
        terminal_kind = None
    latch_records = [
        record
        for record in normalized_records
        if record["class"] == "INTENDED_PRECONTACT"
    ]
    precontact_latch = (
        {
            "physics_step": physics_step,
            "sides": sorted({record["side"] for record in latch_records}),
            "records": latch_records,
        }
        if terminal_kind is None and latch_records
        else None
    )
    payload = {
        "authority": authority,
        "physics_step": physics_step,
        "phase": phase,
        "records": normalized_records,
        "class_counts": class_counts,
        "terminal_kind": terminal_kind,
        "precontact_latch": precontact_latch,
        "structure_valid": structure_valid,
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def evaluate_postcontact_settle(
    *,
    samples: Sequence[Mapping[str, Any]],
    first_contact_physics_step: int,
    approach_direction_world: Sequence[float],
    maximum_downward_coast_m: Any,
    required_settled_steps: int,
    maximum_tool_speed_m_s: Any,
    maximum_source_translation_m: Any,
    maximum_source_tilt_degrees: Any,
    maximum_source_linear_speed_m_s: Any,
    maximum_source_angular_speed_degrees_s: Any,
    maximum_position_error_m: Any,
    maximum_orientation_error_degrees: Any,
) -> dict[str, Any]:
    authority = "first_contact_physical_coast_and_settle_v1"
    direction = _finite_array(approach_direction_world, (3,))
    limits = {}
    try:
        limits = {
            "coast_m": _finite_number(maximum_downward_coast_m, nonnegative=True),
            "tool_speed_m_s": _finite_number(
                maximum_tool_speed_m_s, nonnegative=True
            ),
            "source_translation_m": _finite_number(
                maximum_source_translation_m, nonnegative=True
            ),
            "source_tilt_degrees": _finite_number(
                maximum_source_tilt_degrees, nonnegative=True
            ),
            "source_linear_speed_m_s": _finite_number(
                maximum_source_linear_speed_m_s, nonnegative=True
            ),
            "source_angular_speed_degrees_s": _finite_number(
                maximum_source_angular_speed_degrees_s, nonnegative=True
            ),
            "position_error_m": _finite_number(
                maximum_position_error_m, nonnegative=True
            ),
            "orientation_error_degrees": _finite_number(
                maximum_orientation_error_degrees, nonnegative=True
            ),
        }
    except ValueError:
        limits = {}
    structure_valid = bool(
        type(first_contact_physics_step) is int
        and first_contact_physics_step >= 0
        and type(required_settled_steps) is int
        and required_settled_steps > 0
        and direction is not None
        and math.isclose(
            float(np.linalg.norm(direction)), 1.0, rel_tol=0.0, abs_tol=1.0e-9
        )
        and len(limits) == 8
        and isinstance(samples, Sequence)
        and not isinstance(samples, (str, bytes))
        and len(samples) > 0
    )
    normalized_samples = []
    if structure_valid:
        for index, raw in enumerate(samples):
            if not isinstance(raw, Mapping):
                structure_valid = False
                break
            position = _finite_array(raw.get("tool_position_m"), (3,))
            try:
                record = {
                    "physics_step": raw.get("physics_step"),
                    "tool_position_m": position.tolist() if position is not None else None,
                    "tool_linear_speed_m_s": _finite_number(
                        raw.get("tool_linear_speed_m_s"), nonnegative=True
                    ),
                    "source_translation_m": _finite_number(
                        raw.get("source_translation_m"), nonnegative=True
                    ),
                    "source_tilt_degrees": _finite_number(
                        raw.get("source_tilt_degrees"), nonnegative=True
                    ),
                    "source_linear_speed_m_s": _finite_number(
                        raw.get("source_linear_speed_m_s"), nonnegative=True
                    ),
                    "source_angular_speed_degrees_s": _finite_number(
                        raw.get("source_angular_speed_degrees_s"), nonnegative=True
                    ),
                    "position_error_m": _finite_number(
                        raw.get("position_error_m"), nonnegative=True
                    ),
                    "orientation_error_degrees": _finite_number(
                        raw.get("orientation_error_degrees"), nonnegative=True
                    ),
                    "numeric_error_m": _finite_number(
                        raw.get("numeric_error_m", 0.0), nonnegative=True
                    ),
                }
            except ValueError:
                structure_valid = False
                break
            if (
                type(record["physics_step"]) is not int
                or position is None
                or record["physics_step"] != first_contact_physics_step + index
            ):
                structure_valid = False
                break
            normalized_samples.append(record)
    if (
        structure_valid
        and normalized_samples[0]["physics_step"] != first_contact_physics_step
    ):
        structure_valid = False

    maximum_coast = None
    maximum_coast_upper = None
    settled_streak = 0
    physical_failures = []
    if structure_valid:
        first_position = np.asarray(
            normalized_samples[0]["tool_position_m"], dtype=np.float64
        )
        maximum_coast = 0.0
        maximum_coast_upper = 0.0
        for index, sample in enumerate(normalized_samples):
            position = np.asarray(sample["tool_position_m"], dtype=np.float64)
            coast = max(0.0, float((position - first_position) @ direction))
            coast_upper = math.nextafter(
                coast + sample["numeric_error_m"], math.inf
            )
            sample["downward_coast_m"] = coast
            sample["downward_coast_upper_m"] = coast_upper
            maximum_coast = max(maximum_coast, coast)
            maximum_coast_upper = max(maximum_coast_upper, coast_upper)
            if coast_upper > limits["coast_m"]:
                physical_failures.append(f"sample_{index}.downward_coast")
            for field, limit_key in (
                ("source_translation_m", "source_translation_m"),
                ("source_tilt_degrees", "source_tilt_degrees"),
                ("position_error_m", "position_error_m"),
                ("orientation_error_degrees", "orientation_error_degrees"),
            ):
                if sample[field] > limits[limit_key]:
                    physical_failures.append(f"sample_{index}.{field}")
            settled_now = bool(
                index > 0
                and coast_upper <= limits["coast_m"]
                and sample["tool_linear_speed_m_s"] <= limits["tool_speed_m_s"]
                and sample["source_translation_m"] <= limits["source_translation_m"]
                and sample["source_tilt_degrees"] <= limits["source_tilt_degrees"]
                and sample["source_linear_speed_m_s"]
                <= limits["source_linear_speed_m_s"]
                and sample["source_angular_speed_degrees_s"]
                <= limits["source_angular_speed_degrees_s"]
                and sample["position_error_m"] <= limits["position_error_m"]
                and sample["orientation_error_degrees"]
                <= limits["orientation_error_degrees"]
            )
            settled_streak = settled_streak + 1 if settled_now else 0
        if settled_streak < required_settled_steps:
            physical_failures.append("settled_window")

    terminal_kind = (
        "PROTOCOL_FAILURE"
        if not structure_valid
        else "PHYSICAL_MOTION_FAILURE"
        if physical_failures
        else None
    )
    payload = {
        "authority": authority,
        "first_contact_physics_step": first_contact_physics_step,
        "approach_direction_world": (
            direction.tolist() if direction is not None else None
        ),
        "limits": limits,
        "required_settled_steps": required_settled_steps,
        "samples": normalized_samples,
        "maximum_downward_coast_m": maximum_coast,
        "maximum_downward_coast_upper_m": maximum_coast_upper,
        "settled_step_count": settled_streak,
        "physical_failures": sorted(set(physical_failures)),
        "terminal_kind": terminal_kind,
        "structure_valid": structure_valid,
        "passed": terminal_kind is None,
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def build_controlled_authorization_record(
    *,
    go_report_bytes: bytes,
    filled_bundle: Mapping[str, Any],
    authorization_id: str,
    attempt_path: str | os.PathLike[str],
) -> dict[str, Any]:
    if not isinstance(go_report_bytes, bytes):
        raise ValueError("controlled_authorization_go_invalid")
    try:
        report = _load_strict_json_object_bytes(
            go_report_bytes,
            source_name="controlled_preflight_report",
            error_code="controlled_authorization_go_invalid",
        )
    except ValueError as exc:
        raise ValueError("controlled_authorization_go_invalid") from exc
    if (
        report.get("schema_version") != 1
        or report.get("decision") != CONTROLLED_PREFLIGHT_GO_DECISION
        or not isinstance(report.get("run_identity_sha256"), str)
        or len(report["run_identity_sha256"]) != 64
    ):
        raise ValueError("controlled_authorization_go_invalid")
    if (
        not isinstance(filled_bundle, Mapping)
        or not filled_bundle
        or any(
            key in filled_bundle
            for key in ("authorization_id", "attempt_path", "ledger_key_sha256")
        )
    ):
        raise ValueError("controlled_authorization_bundle_invalid")
    bundle = _json_native(filled_bundle)
    if not isinstance(bundle, dict):
        raise ValueError("controlled_authorization_bundle_invalid")
    if (
        not isinstance(authorization_id, str)
        or len(authorization_id) != 64
        or any(character not in "0123456789abcdef" for character in authorization_id)
    ):
        raise ValueError("controlled_authorization_id_invalid")
    attempt = Path(attempt_path)
    if not attempt.is_absolute():
        raise ValueError("controlled_authorization_attempt_path_invalid")
    bundle_sha256 = canonical_json_sha256(bundle)
    ledger_key = hashlib.sha256(
        go_report_bytes + b"\0" + bundle_sha256.encode("ascii")
    ).hexdigest()
    payload = {
        "schema_version": 1,
        "authority": "go_report_and_filled_bundle_single_local_claim_v1",
        "go_report_sha256": hashlib.sha256(go_report_bytes).hexdigest(),
        "filled_bundle": bundle,
        "filled_bundle_sha256": bundle_sha256,
        "ledger_key_sha256": ledger_key,
        "authorization_id": authorization_id,
        "attempt_path": str(attempt),
    }
    return {**payload, "record_sha256": canonical_json_sha256(payload)}


def _catalog_world_points(
    catalog: Mapping[str, Any],
    collider_world_matrices: Sequence[Mapping[str, Any]],
) -> np.ndarray:
    validated = validate_cooked_catalog(catalog)
    if (
        not isinstance(collider_world_matrices, Sequence)
        or isinstance(collider_world_matrices, (str, bytes))
    ):
        raise ValueError("trajectory_preflight_collider_matrices_invalid")
    matrices: dict[str, np.ndarray] = {}
    for record in collider_world_matrices:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise ValueError("trajectory_preflight_collider_matrices_invalid")
        matrix = _finite_array(record.get("matrix"), (4, 4))
        path = record["path"]
        if matrix is None or path in matrices:
            raise ValueError("trajectory_preflight_collider_matrices_invalid")
        matrices[path] = matrix
    expected_paths = {str(collider["path"]) for collider in validated["colliders"]}
    if set(matrices) != expected_paths:
        raise ValueError("trajectory_preflight_collider_matrices_invalid")
    points = []
    for collider in validated["colliders"]:
        low = np.asarray(collider["aabb_local_min_m"], dtype=np.float64)
        high = np.asarray(collider["aabb_local_max_m"], dtype=np.float64)
        corners = np.asarray(
            [
                [x, y, z, 1.0]
                for x in (low[0], high[0])
                for y in (low[1], high[1])
                for z in (low[2], high[2])
            ],
            dtype=np.float64,
        )
        points.append(corners @ matrices[str(collider["path"])])
    return np.concatenate(points, axis=0)[:, :3]


def project_cooked_catalog_interval(
    *,
    catalog: Mapping[str, Any],
    collider_world_matrices: Sequence[Mapping[str, Any]],
    axis_world: Sequence[float],
) -> list[float]:
    axis = _finite_array(axis_world, (3,))
    if axis is None or not math.isclose(
        float(np.linalg.norm(axis)), 1.0, rel_tol=0.0, abs_tol=1.0e-9
    ):
        raise ValueError("trajectory_preflight_projection_axis_invalid")
    projection = _catalog_world_points(catalog, collider_world_matrices) @ axis
    return [float(np.min(projection)), float(np.max(projection))]


def derive_cooked_gap_error_bound(
    *,
    finger_collider_catalogs: Mapping[str, Any],
    finger_collider_world_matrices: Mapping[str, Any],
) -> dict[str, Any]:
    authority = (
        "physx_property_query_float32_aabb_outward_8ulp_plus_"
        "float64_transform_v1"
    )
    invalid = {
        "authority": authority,
        "property_query_value_type": None,
        "local_aabb_max_abs_m": None,
        "world_transform_max_abs": None,
        "float32_aabb_error_bound_m": None,
        "float64_transform_error_bound_m": None,
        "conservative_floor_m": COOKED_GAP_ERROR_FLOOR_M,
        "bound_m": None,
        "evidence_sha256": None,
        "passed": False,
    }
    if (
        not isinstance(finger_collider_catalogs, Mapping)
        or set(finger_collider_catalogs) != set(SIDES)
        or not isinstance(finger_collider_world_matrices, Mapping)
        or set(finger_collider_world_matrices) != set(SIDES)
    ):
        return invalid
    try:
        local_max = 0.0
        transform_max = 0.0
        linear_norm = 0.0
        world_max = 0.0
        for side in SIDES:
            catalog = validate_cooked_catalog(
                finger_collider_catalogs[side]
            )
            if catalog.get("cooked_aabb_precision") != COOKED_AABB_PRECISION:
                return invalid
            records = finger_collider_world_matrices[side]
            points = _catalog_world_points(catalog, records)
            world_max = max(world_max, float(np.max(np.abs(points))))
            matrices = {
                record["path"]: _finite_array(record.get("matrix"), (4, 4))
                for record in records
                if isinstance(record, Mapping)
                and isinstance(record.get("path"), str)
            }
            if any(matrix is None for matrix in matrices.values()):
                return invalid
            for collider in catalog["colliders"]:
                low = _finite_array(collider.get("aabb_local_min_m"), (3,))
                high = _finite_array(collider.get("aabb_local_max_m"), (3,))
                matrix = matrices.get(collider["path"])
                if low is None or high is None or matrix is None:
                    return invalid
                local_max = max(
                    local_max,
                    float(np.max(np.abs(low))),
                    float(np.max(np.abs(high))),
                )
                transform_max = max(
                    transform_max, float(np.max(np.abs(matrix)))
                )
                linear_norm = max(
                    linear_norm,
                    float(np.linalg.norm(matrix[:3, :3], ord=2)),
                )
        float32_bound = (
            2.0
            * math.sqrt(3.0)
            * 8.0
            * float(np.finfo(np.float32).eps)
            * max(1.0, local_max)
            * max(1.0, linear_norm)
        )
        transform_bound = (
            128.0
            * float(np.finfo(np.float64).eps)
            * max(1.0, world_max, transform_max)
        )
        bound = math.nextafter(
            max(COOKED_GAP_ERROR_FLOOR_M, float32_bound + transform_bound),
            math.inf,
        )
    except (KeyError, TypeError, ValueError):
        return invalid
    payload = {
        "authority": authority,
        "property_query_value_type": "float32",
        "local_aabb_max_abs_m": local_max,
        "world_transform_max_abs": transform_max,
        "float32_aabb_error_bound_m": float32_bound,
        "float64_transform_error_bound_m": transform_bound,
        "conservative_floor_m": COOKED_GAP_ERROR_FLOOR_M,
        "bound_m": bound,
        "passed": True,
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def compose_calibration_body_world_matrix(
    *,
    reset_tool_world_matrix: Sequence[Sequence[float]],
    translation_tool_m: Sequence[float],
) -> list[list[float]]:
    matrix = _finite_array(reset_tool_world_matrix, (4, 4))
    translation = _finite_array(translation_tool_m, (3,))
    if (
        matrix is None
        or translation is None
        or not np.array_equal(matrix[:, 3], [0.0, 0.0, 0.0, 1.0])
        or not np.allclose(
            matrix[:3, :3] @ matrix[:3, :3].T,
            np.eye(3),
            rtol=0.0,
            atol=1.0e-8,
        )
        or not math.isclose(
            float(np.linalg.det(matrix[:3, :3])),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-8,
        )
    ):
        raise ValueError("trajectory_preflight_calibration_transform_invalid")
    local_translation = np.eye(4, dtype=np.float64)
    local_translation[3, :3] = translation
    return (local_translation @ matrix).tolist()


def calibration_body_spec(
    *,
    reset_tool_world_matrix: Sequence[Sequence[float]],
    translation_tool_m: Sequence[float],
    opening_axis_world: Sequence[float],
    size_m: Sequence[float],
    contact_offset_m: float,
) -> dict[str, Any]:
    reset_matrix = _finite_array(reset_tool_world_matrix, (4, 4))
    translation = _finite_array(translation_tool_m, (3,))
    matrix = _finite_array(
        compose_calibration_body_world_matrix(
            reset_tool_world_matrix=reset_tool_world_matrix,
            translation_tool_m=translation_tool_m,
        ),
        (4, 4),
    )
    axis = _finite_array(opening_axis_world, (3,))
    size = _finite_array(size_m, (3,))
    offset = _finite_number(contact_offset_m, nonnegative=True)
    if (
        reset_matrix is None
        or translation is None
        or matrix is None
        or axis is None
        or size is None
        or np.any(size <= 0.0)
        or not math.isclose(
            float(np.linalg.norm(axis)), 1.0, rel_tol=0.0, abs_tol=1.0e-9
        )
        or not np.allclose(
            axis,
            np.asarray(derive_opening_axis_world(matrix), dtype=np.float64),
            rtol=0.0,
            atol=1.0e-9,
        )
    ):
        raise ValueError("trajectory_preflight_calibration_body_spec_invalid")
    return {
        "path": CALIBRATION_BODY_PATH,
        "shape": "box",
        "size_m": size.tolist(),
        "width_m": float(size[1]),
        "reset_tool_world_matrix": reset_matrix.tolist(),
        "translation_tool_m": translation.tolist(),
        "world_matrix": matrix.tolist(),
        "opening_axis_tool": [0.0, 1.0, 0.0],
        "opening_axis_world": axis.tolist(),
        "placement_authority": (
            "row_tool_translation_from_reset_between_open_finger_pads_v2"
        ),
        "non_width_dimensions_m": [float(size[0]), float(size[2])],
        "contact_offset_m": offset,
        "rest_offset_m": 0.0,
        "rigid_body": False,
    }


def evaluate_calibration_support_placement(
    *,
    calibration_spec: Mapping[str, Any],
    finger_collider_projection_intervals_m: Mapping[str, Any],
    cooked_projection_error_bound_m: Any,
) -> dict[str, Any]:
    error_bound = _optional_nonnegative(cooked_projection_error_bound_m)
    reset = _finite_array(calibration_spec.get("reset_tool_world_matrix"), (4, 4))
    try:
        body_points = _box_world_points(
            size_m=calibration_spec.get("size_m", []),
            world_matrix=calibration_spec.get("world_matrix", []),
        )
    except (TypeError, ValueError):
        body_points = None
    axes = {
        "tool_x": reset[0, :3] if reset is not None else None,
        "tool_y": reset[1, :3] if reset is not None else None,
        "tool_z": reset[2, :3] if reset is not None else None,
    }
    body_intervals = {}
    if body_points is not None and all(axis is not None for axis in axes.values()):
        body_intervals = {
            name: [
                float(np.min(body_points @ axis)),
                float(np.max(body_points @ axis)),
            ]
            for name, axis in axes.items()
        }

    selected: dict[str, str] = {}
    selected_intervals: dict[str, dict[str, list[float]]] = {}
    tangent_margins: dict[str, Any] = {}
    structure_valid = bool(
        error_bound is not None
        and error_bound > 0.0
        and set(body_intervals) == set(axes)
        and isinstance(finger_collider_projection_intervals_m, Mapping)
        and set(finger_collider_projection_intervals_m) == set(SIDES)
    )
    strict_error_bound = (
        error_bound + 16.0 * float(np.finfo(np.float64).eps)
        if error_bound is not None
        else None
    )
    if structure_valid:
        for side in SIDES:
            raw_colliders = finger_collider_projection_intervals_m.get(side)
            candidates = []
            if isinstance(raw_colliders, Mapping):
                for path, raw_intervals in sorted(raw_colliders.items()):
                    if not isinstance(path, str) or not path.startswith("/"):
                        continue
                    intervals = {}
                    if isinstance(raw_intervals, Mapping):
                        for name in axes:
                            interval = _finite_array(raw_intervals.get(name), (2,))
                            if interval is not None and interval[0] <= interval[1]:
                                intervals[name] = interval
                    if set(intervals) != set(axes):
                        continue
                    margins = {}
                    for name in ("tool_x", "tool_z"):
                        body_low, body_high = body_intervals[name]
                        support_low, support_high = intervals[name]
                        margins[name] = [
                            float(body_low - support_low),
                            float(support_high - body_high),
                        ]
                    if all(
                        value > strict_error_bound
                        for values in margins.values()
                        for value in values
                    ):
                        candidates.append((path, intervals, margins))
            if len(candidates) == 1:
                path, intervals, margins = candidates[0]
                selected[side] = path
                selected_intervals[side] = {
                    name: interval.tolist() for name, interval in intervals.items()
                }
                tangent_margins[side] = margins

    opening_order: list[str] = []
    finger_inner = None
    opening_margins = None
    opening_valid = False
    if len(selected) == len(SIDES):
        opening_order = sorted(
            SIDES,
            key=lambda side: float(
                np.sum(selected_intervals[side]["tool_y"])
            ),
        )
        lower = selected_intervals[opening_order[0]]["tool_y"]
        upper = selected_intervals[opening_order[1]]["tool_y"]
        finger_inner = [float(lower[1]), float(upper[0])]
        body_low, body_high = body_intervals["tool_y"]
        opening_margins = [
            float(body_low - finger_inner[0]),
            float(finger_inner[1] - body_high),
        ]
        opening_valid = bool(
            finger_inner[0] < finger_inner[1]
            and all(value > strict_error_bound for value in opening_margins)
        )
    payload = {
        "authority": "single_cooked_pad_collider_full_face_projection_v1",
        "body_projection_intervals_m": body_intervals,
        "finger_collider_projection_intervals_m": _json_native(
            finger_collider_projection_intervals_m
        ),
        "selected_collider_paths": selected,
        "selected_collider_projection_intervals_m": selected_intervals,
        "tangent_containment_margins_m": tangent_margins,
        "opening_order": opening_order,
        "finger_inner_projection_interval_m": finger_inner,
        "opening_containment_margins_m": opening_margins,
        "cooked_projection_error_bound_m": error_bound,
        "passed": bool(
            structure_valid
            and len(selected) == len(SIDES)
            and opening_valid
        ),
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def evaluate_calibration_support_rays(
    *,
    placement_evidence: Mapping[str, Any],
    ray_hits_by_side: Mapping[str, Any],
    opening_axis_world: Sequence[float],
    cooked_projection_error_bound_m: Any,
) -> dict[str, Any]:
    axis = _finite_array(opening_axis_world, (3,))
    error_bound = _optional_nonnegative(cooked_projection_error_bound_m)
    selected = placement_evidence.get("selected_collider_paths")
    intervals = placement_evidence.get("selected_collider_projection_intervals_m")
    order = placement_evidence.get("opening_order")
    expected_ids = list(CALIBRATION_FACE_SAMPLE_IDS)
    normalized = {}
    checks = {}
    structure_valid = bool(
        placement_evidence.get("passed") is True
        and axis is not None
        and math.isclose(float(np.linalg.norm(axis)), 1.0, rel_tol=0.0, abs_tol=1.0e-9)
        and error_bound is not None
        and error_bound > 0.0
        and isinstance(selected, Mapping)
        and isinstance(intervals, Mapping)
        and order in (["left", "right"], ["right", "left"])
        and isinstance(ray_hits_by_side, Mapping)
        and set(ray_hits_by_side) == set(SIDES)
    )
    if structure_valid:
        for side in SIDES:
            side_hits = ray_hits_by_side.get(side)
            valid_hits = []
            if isinstance(side_hits, Sequence) and not isinstance(
                side_hits, (str, bytes)
            ):
                boundary_index = 1 if side == order[0] else 0
                boundary = intervals[side]["tool_y"][boundary_index]
                expected_normal = axis if side == order[0] else -axis
                for hit in side_hits:
                    if not isinstance(hit, Mapping):
                        continue
                    position = _finite_array(hit.get("position_m"), (3,))
                    normal = _finite_array(hit.get("normal_world"), (3,))
                    distance = _finite_number(hit.get("distance_m"), positive=True)
                    if position is None or normal is None or distance is None:
                        continue
                    norm = float(np.linalg.norm(normal))
                    if norm <= 0.0:
                        continue
                    normal = normal / norm
                    valid_hits.append(
                        {
                            **dict(hit),
                            "position_m": position.tolist(),
                            "normal_world": normal.tolist(),
                            "distance_m": distance,
                            "boundary_error_m": abs(float(position @ axis) - boundary),
                            "inward_normal_cosine": float(normal @ expected_normal),
                        }
                    )
            ids = [hit.get("sample_id") for hit in valid_hits]
            side_passed = bool(
                ids == expected_ids
                and all(
                    hit.get("collision_path") == selected.get(side)
                    and hit["boundary_error_m"] <= error_bound
                    and hit["inward_normal_cosine"] > 0.8
                    for hit in valid_hits
                )
            )
            normalized[side] = valid_hits
            checks[side] = side_passed
    payload = {
        "authority": "five_ray_same_cooked_pad_support_witness_v1",
        "placement_evidence_sha256": placement_evidence.get("evidence_sha256"),
        "ray_hits_by_side": normalized,
        "opening_axis_world": axis.tolist() if axis is not None else None,
        "cooked_projection_error_bound_m": error_bound,
        "checks": checks,
        "passed": bool(
            structure_valid
            and set(checks) == set(SIDES)
            and all(checks.values())
        ),
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def validate_physical_open_authority(
    *, upper_limits_m: Any, requested_open_target_m: Any
) -> dict[str, Any]:
    limits = _finite_array(upper_limits_m, (2,))
    requested = _optional_nonnegative(requested_open_target_m)
    if (
        limits is None
        or requested is None
        or requested <= 0.0
        or np.any(limits <= 0.0)
        or not np.allclose(limits, limits[0], rtol=0.0, atol=1.0e-12)
        or float(limits[0]) > requested + 1.0e-12
    ):
        raise ValueError("trajectory_preflight_open_authority_invalid")
    return {
        "upper_limits_m": limits.tolist(),
        "requested_open_target_m": requested,
        "canonical_open_target_m": float(limits[0]),
        "authority": "physical_dof_upper_limits",
        "passed": True,
    }


def derive_measured_open_contract(
    *,
    points: Sequence[Mapping[str, Any]],
    velocity_samples: Sequence[Mapping[str, Any]],
    requested_open_target_m: Any,
    physics_dt: Any,
) -> dict[str, Any]:
    error = "trajectory_preflight_open_authority_invalid"
    requested = _finite_number(requested_open_target_m, positive=True)
    dt = _finite_number(physics_dt, positive=True)
    if (
        not isinstance(points, Sequence)
        or isinstance(points, (str, bytes))
        or not points
        or not all(isinstance(point, Mapping) for point in points)
        or not isinstance(velocity_samples, Sequence)
        or isinstance(velocity_samples, (str, bytes))
    ):
        raise ValueError(error)
    first_target = _optional_nonnegative(points[0].get("target_m"))
    if first_target is None or not math.isclose(
        first_target, requested, rel_tol=0.0, abs_tol=1.0e-12
    ):
        raise ValueError(error)
    upper_limits = [_finite_array(point.get("upper_limits_m"), (2,)) for point in points]
    if any(limits is None for limits in upper_limits):
        raise ValueError(error)
    upper = np.asarray(upper_limits, dtype=np.float64)
    canonical = float(upper[0, 0])
    if (
        canonical <= 0.0
        or canonical > requested + 1.0e-12
        or not np.allclose(upper, canonical, rtol=0.0, atol=1.0e-12)
    ):
        raise ValueError(error)
    commanded = _optional_nonnegative(points[0].get("commanded_target_m"))
    positions = _finite_array(points[0].get("joint_positions_m"), (2,))
    if (
        commanded is None
        or not math.isclose(commanded, canonical, rel_tol=0.0, abs_tol=1.0e-12)
        or positions is None
    ):
        raise ValueError(error)
    settle_samples = points[0].get("settle_samples")
    if (
        not isinstance(settle_samples, Sequence)
        or isinstance(settle_samples, (str, bytes))
        or not settle_samples
    ):
        raise ValueError(error)
    settled_positions = []
    for sample in settle_samples:
        sample_positions = (
            _finite_array(sample.get("joint_positions_m"), (2,))
            if isinstance(sample, Mapping)
            else None
        )
        if sample_positions is None:
            raise ValueError(error)
        settled_positions.append(sample_positions)
    maximum_velocity_disagreement = 0.0
    for sample in velocity_samples:
        if not isinstance(sample, Mapping):
            raise ValueError(error)
        api = _finite_array(sample.get("api_pad_velocity_m_s"), (2,))
        finite_difference = _finite_array(
            sample.get("finite_difference_pad_velocity_m_s"), (2,)
        )
        if api is None or finite_difference is None:
            raise ValueError(error)
        maximum_velocity_disagreement = max(
            maximum_velocity_disagreement,
            float(np.max(np.abs(api - finite_difference))),
        )
    storage_bound = max(
        float(np.finfo(np.float64).eps), abs(requested - canonical)
    )
    settled_position_deficit = max(
        float(np.max(np.abs(sample - canonical))) for sample in settled_positions
    )
    velocity_bound = max(
        float(np.finfo(np.float64).eps), maximum_velocity_disagreement * dt
    )
    tolerance = max(storage_bound, settled_position_deficit, velocity_bound)
    return {
        "requested_open_target_m": requested,
        "canonical_open_target_m": canonical,
        "measured_upper_limits_m": upper[0].tolist(),
        "storage_quantization_bound_m": storage_bound,
        "settled_position_deficit_bound_m": settled_position_deficit,
        "velocity_repeatability_bound_m": velocity_bound,
        "open_position_tolerance_m": tolerance,
        "authority": (
            "measured_dof_upper_limits_settled_position_velocity_repeatability_v2"
        ),
        "passed": True,
    }


def validate_collision_interlock_evidence(evidence: Any) -> bool:
    if not isinstance(evidence, Mapping):
        return False
    before = evidence.get("physics_step_before_pause")
    first_enabled = evidence.get("first_enabled_physics_step")
    open_state = evidence.get("physical_open_state")
    pre_budget = evidence.get("pre_enable_clearance_budget")
    post_budget = evidence.get("post_enable_clearance_budget")
    if (
        evidence.get("timeline_was_playing") is not True
        or type(before) is not int
        or before < 0
        or evidence.get("physics_step_after_pause_update") != before
        or evidence.get("physics_step_after_enable_update") != before
        or evidence.get("physics_step_after_resume") != before
        or first_enabled != before + 1
        or evidence.get("collision_enabled_before") is not False
        or evidence.get("collision_enabled_after") is not True
        or evidence.get("first_enabled_step_contacts") != []
        or evidence.get("failure_reason") is not None
        or not validate_remote_calibration_clearance_budget(pre_budget)
        or not validate_remote_calibration_clearance_budget(post_budget)
        or pre_budget != post_budget
        or not isinstance(open_state, Mapping)
    ):
        return False
    positions = _finite_array(open_state.get("joint_positions_m"), (2,))
    upper = _finite_array(open_state.get("upper_limits_m"), (2,))
    tolerance = _optional_nonnegative(open_state.get("position_tolerance_m"))
    return bool(
        positions is not None
        and upper is not None
        and tolerance is not None
        and tolerance > 0.0
        and np.all(np.abs(positions - upper) <= tolerance + 1.0e-12)
    )


def derive_effective_contact_offset_bounds(
    *,
    calibration_body_width_m: float,
    calibration_body_contact_offset_m: float,
    contact_onset_brackets: Mapping[str, Any],
    finger_collider_catalogs: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine onset calibration with every resolved finger collider offset."""
    width = _finite_number(calibration_body_width_m, positive=True)
    body_offset = _finite_number(
        calibration_body_contact_offset_m, nonnegative=True
    )
    if (
        not isinstance(contact_onset_brackets, Mapping)
        or set(contact_onset_brackets) != set(SIDES)
        or not isinstance(finger_collider_catalogs, Mapping)
        or set(finger_collider_catalogs) != set(SIDES)
    ):
        raise ValueError("trajectory_preflight_contact_onset_sides_invalid")
    onset_bounds: dict[str, float | None] = {}
    collider_bounds: dict[str, float | None] = {}
    effective_bounds: dict[str, float | None] = {}
    unknown = []
    invalid = []
    records = {}
    for side in SIDES:
        try:
            catalog = validate_cooked_catalog(finger_collider_catalogs[side])
        except (TypeError, ValueError):
            catalog = None
        resolved_offsets = []
        if isinstance(catalog, Mapping):
            for collider in catalog["colliders"]:
                offset = collider.get("contact_offset")
                value = _optional_nonnegative(
                    offset.get("contact_offset_m")
                    if isinstance(offset, Mapping)
                    and offset.get("authority") != "unresolved"
                    else None
                )
                if value is None:
                    resolved_offsets = []
                    break
                resolved_offsets.append(value)
        collider_bound = max(resolved_offsets) if resolved_offsets else None
        collider_bounds[side] = collider_bound
        bracket = contact_onset_brackets.get(side)
        if bracket is None:
            onset_bounds[side] = None
            effective_bounds[side] = None
            unknown.append(side)
            records[side] = {
                "previous_no_contact": None,
                "first_contact": None,
                "contact_onset_bound_m": None,
                "resolved_collider_offset_bound_m": collider_bound,
                "effective_bound_m": None,
            }
            continue
        previous = bracket.get("previous_no_contact") if isinstance(bracket, Mapping) else None
        first = bracket.get("first_contact") if isinstance(bracket, Mapping) else None
        previous_step = previous.get("physics_step") if isinstance(previous, Mapping) else None
        first_step = first.get("physics_step") if isinstance(first, Mapping) else None
        previous_gap = _optional_nonnegative(
            previous.get("inner_gap_m") if isinstance(previous, Mapping) else None
        )
        first_gap = _optional_nonnegative(
            first.get("inner_gap_m") if isinstance(first, Mapping) else None
        )
        previous_error = derive_cooked_gap_error_bound(
            finger_collider_catalogs=finger_collider_catalogs,
            finger_collider_world_matrices=(
                previous.get("finger_collider_world_matrices", {})
                if isinstance(previous, Mapping)
                else {}
            ),
        )
        first_error = derive_cooked_gap_error_bound(
            finger_collider_catalogs=finger_collider_catalogs,
            finger_collider_world_matrices=(
                first.get("finger_collider_world_matrices", {})
                if isinstance(first, Mapping)
                else {}
            ),
        )
        previous_resolution = _optional_nonnegative(previous_error.get("bound_m"))
        first_resolution = _optional_nonnegative(first_error.get("bound_m"))
        zero_contact_evidence = (
            previous.get("normalized_contact_evidence")
            if isinstance(previous, Mapping)
            else None
        )
        evidence_valid = bool(
            isinstance(zero_contact_evidence, Mapping)
            and zero_contact_evidence.get("physics_step") == previous_step
            and zero_contact_evidence.get("normalized_contacts") == []
            and previous.get("normalized_contact_evidence_sha256")
            == canonical_json_sha256(zero_contact_evidence)
        )
        valid_bracket = bool(
            type(previous_step) is int
            and type(first_step) is int
            and previous_step >= 0
            and first_step == previous_step + 1
            and previous_gap is not None
            and first_gap is not None
            and previous_resolution is not None
            and previous_resolution > 0.0
            and first_resolution is not None
            and first_resolution > 0.0
            and previous.get("gap_error_bound") == previous_error
            and first.get("gap_error_bound") == first_error
            and math.isclose(
                previous_resolution,
                first_resolution,
                rel_tol=0.0,
                abs_tol=1.0e-15,
            )
            and first_gap <= previous_gap + 1.0e-12
            and evidence_valid
            and collider_bound is not None
        )
        onset_bound = (
            None
            if previous_gap is None or previous_resolution is None
            else math.nextafter(
                previous_gap + previous_resolution - width - body_offset,
                math.inf,
            )
        )
        if not valid_bracket or onset_bound is None or onset_bound < 0.0:
            onset_bounds[side] = None
            effective_bounds[side] = None
            invalid.append(side)
            records[side] = {
                "previous_no_contact": dict(previous) if isinstance(previous, Mapping) else None,
                "first_contact": dict(first) if isinstance(first, Mapping) else None,
                "contact_onset_bound_m": None,
                "resolved_collider_offset_bound_m": collider_bound,
                "effective_bound_m": None,
            }
            continue
        effective_bound = max(onset_bound, collider_bound)
        onset_bounds[side] = onset_bound
        effective_bounds[side] = effective_bound
        records[side] = {
            "previous_no_contact": dict(previous),
            "first_contact": dict(first),
            "contact_onset_bound_m": onset_bound,
            "resolved_collider_offset_bound_m": collider_bound,
            "effective_bound_m": effective_bound,
        }
    return {
        "calibration_body_width_m": width,
        "calibration_body_contact_offset_m": body_offset,
        "method": "max_outward_contact_onset_upper_bound_and_resolved_per_collider_contact_offset",
        "records": records,
        "contact_onset_bounds_m": onset_bounds,
        "resolved_collider_offset_bounds_m": collider_bounds,
        "bounds_m": effective_bounds,
        "unknown_sides": unknown,
        "invalid_sides": invalid,
        "measurement_complete": not unknown and not invalid,
        "passed": not unknown and not invalid,
    }


def evaluate_continuous_settle_window(
    *,
    samples: Sequence[Mapping[str, Any]],
    target_positions_m: Sequence[float],
    physics_dt: float,
    required_duration_s: float,
    position_tolerance_m: float,
    velocity_tolerance_m_s: float,
) -> dict[str, Any]:
    dt = _finite_number(physics_dt, positive=True)
    duration = _finite_number(required_duration_s, positive=True)
    position_tolerance = _finite_number(position_tolerance_m, positive=True)
    velocity_tolerance = _finite_number(velocity_tolerance_m_s, positive=True)
    targets = _finite_array(target_positions_m, (2,))
    expected_count = int(math.ceil(duration / dt - 1.0e-12))
    parsed = []
    valid = bool(
        targets is not None
        and isinstance(samples, Sequence)
        and not isinstance(samples, (str, bytes))
        and len(samples) == expected_count
    )
    if valid:
        for sample in samples:
            if not isinstance(sample, Mapping):
                valid = False
                break
            step = sample.get("physics_step")
            positions = _finite_array(sample.get("joint_positions_m"), (2,))
            api = _finite_array(sample.get("api_pad_velocity_m_s"), (2,))
            finite_difference = _finite_array(
                sample.get("finite_difference_pad_velocity_m_s"), (2,)
            )
            if (
                type(step) is not int
                or step < 0
                or positions is None
                or api is None
                or finite_difference is None
            ):
                valid = False
                break
            parsed.append((step, positions, api, finite_difference))
    contiguous = bool(
        valid
        and [item[0] for item in parsed]
        == list(range(parsed[0][0], parsed[0][0] + expected_count))
    )
    positions_valid = bool(
        contiguous
        and all(
            np.max(np.abs(positions - targets)) <= position_tolerance + 1.0e-12
            for _, positions, _, _ in parsed
        )
    )
    api_valid = bool(
        contiguous
        and all(
            np.max(np.abs(api)) <= velocity_tolerance + 1.0e-12
            for _, _, api, _ in parsed
        )
    )
    finite_difference_valid = bool(
        contiguous
        and all(
            np.max(np.abs(finite_difference)) <= velocity_tolerance + 1.0e-12
            for _, _, _, finite_difference in parsed
        )
    )
    checks = {
        "exact_sample_count": valid,
        "contiguous_physics_steps": contiguous,
        "position_within_tolerance": positions_valid,
        "api_velocity_within_tolerance": api_valid,
        "finite_difference_velocity_within_tolerance": finite_difference_valid,
    }
    return {
        "expected_sample_count": expected_count,
        "sample_count": len(samples) if isinstance(samples, Sequence) else 0,
        "checks": checks,
        "passed": all(checks.values()),
    }


def evaluate_aperture_calibration(
    *,
    points: Sequence[Mapping[str, Any]],
    velocity_samples: Sequence[Mapping[str, Any]],
    expected_targets_m: Sequence[float],
    requested_open_target_m: float,
    required_settle_duration_s: float,
    maximum_asymmetry_m: float,
    velocity_agreement_tolerance_m_s: float,
    physics_dt: float,
) -> dict[str, Any]:
    expected = np.asarray(expected_targets_m, dtype=np.float64)
    if (
        expected.ndim != 1
        or len(expected) < 2
        or not np.isfinite(expected).all()
        or np.any(expected <= 0.0)
        or not np.all(np.diff(expected) < 0.0)
    ):
        raise ValueError("trajectory_preflight_aperture_targets_invalid")
    settle_duration = _finite_number(required_settle_duration_s, positive=True)
    asymmetry_limit = _finite_number(maximum_asymmetry_m, positive=True)
    velocity_tolerance = _finite_number(
        velocity_agreement_tolerance_m_s, positive=True
    )
    dt = _finite_number(physics_dt, positive=True)
    open_contract = derive_measured_open_contract(
        points=points,
        velocity_samples=velocity_samples,
        requested_open_target_m=requested_open_target_m,
        physics_dt=dt,
    )
    open_target = float(open_contract["canonical_open_target_m"])
    position_tolerance = float(open_contract["open_position_tolerance_m"])

    parsed_points = []
    points_valid = isinstance(points, Sequence) and len(points) == len(expected)
    if points_valid:
        for point in points:
            if not isinstance(point, Mapping):
                points_valid = False
                break
            try:
                target = _finite_number(point.get("target_m"), positive=True)
                commanded_target = _finite_number(
                    point.get("commanded_target_m"), positive=True
                )
                gap = _finite_number(point.get("cooked_inner_gap_m"), positive=True)
                duration = _finite_number(
                    point.get("settled_duration_s"), nonnegative=True
                )
                measured_settling_time = _finite_number(
                    point.get("measured_settling_time_s"), nonnegative=True
                )
            except ValueError:
                points_valid = False
                break
            positions = _finite_array(point.get("joint_positions_m"), (2,))
            lower = _finite_array(point.get("lower_limits_m"), (2,))
            upper = _finite_array(point.get("upper_limits_m"), (2,))
            api = _finite_array(point.get("settled_api_velocity_m_s"), (2,))
            finite_difference = _finite_array(
                point.get("settled_finite_difference_velocity_m_s"), (2,)
            )
            if any(
                value is None
                for value in (positions, lower, upper, api, finite_difference)
            ):
                points_valid = False
                break
            settle_window = evaluate_continuous_settle_window(
                samples=point.get("settle_samples", []),
                target_positions_m=[commanded_target, commanded_target],
                physics_dt=dt,
                required_duration_s=settle_duration,
                position_tolerance_m=position_tolerance,
                velocity_tolerance_m_s=velocity_tolerance,
            )
            parsed_points.append(
                {
                    "target": target,
                    "commanded_target": commanded_target,
                    "gap": gap,
                    "duration": duration,
                    "measured_settling_time": measured_settling_time,
                    "positions": positions,
                    "lower": lower,
                    "upper": upper,
                    "api": api,
                    "finite_difference": finite_difference,
                    "settle_window": settle_window,
                }
            )

    target_sequence_exact = bool(
        points_valid
        and np.array_equal(
            np.asarray([point["target"] for point in parsed_points]), expected
        )
    )
    joint_monotonic = False
    gap_monotonic = False
    bilateral_motion = False
    maximum_asymmetry = None
    asymmetry_valid = False
    limit_saturation_valid = False
    full_open_confirmed = False
    settled_everywhere = False
    continuous_settle = False
    if points_valid:
        positions = np.asarray(
            [point["positions"] for point in parsed_points], dtype=np.float64
        )
        gaps = np.asarray([point["gap"] for point in parsed_points], dtype=np.float64)
        joint_monotonic = bool(np.all(np.diff(positions, axis=0) <= 1.0e-12))
        gap_monotonic = bool(
            np.all(np.diff(gaps) <= 1.0e-12) and gaps[-1] < gaps[0]
        )
        bilateral_motion = bool(np.all(positions[-1] < positions[0] - 1.0e-9))
        maximum_asymmetry = float(np.max(np.abs(positions[:, 0] - positions[:, 1])))
        asymmetry_valid = bool(maximum_asymmetry <= asymmetry_limit)
        first = parsed_points[0]
        full_open_confirmed = bool(
            math.isclose(
                first["target"],
                float(open_contract["requested_open_target_m"]),
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            and math.isclose(
                first["commanded_target"],
                open_target,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            and np.allclose(first["upper"], open_target, rtol=0.0, atol=1.0e-12)
            and np.all(
                np.abs(first["positions"] - first["upper"])
                <= position_tolerance + 1.0e-12
            )
        )
        later_inside_limits = all(
            bool(
                np.all(point["positions"] > point["lower"] + 1.0e-9)
                and np.all(point["positions"] < point["upper"] - 1.0e-9)
            )
            for point in parsed_points[1:]
        )
        limit_saturation_valid = bool(full_open_confirmed and later_inside_limits)
        settled_everywhere = all(
            point["duration"] + 1.0e-12 >= settle_duration
            and point["measured_settling_time"] <= settle_duration + 1.0e-12
            and np.max(np.abs(point["api"])) <= velocity_tolerance
            and np.max(np.abs(point["finite_difference"])) <= velocity_tolerance
            for point in parsed_points
        )
        continuous_settle = all(
            point["settle_window"]["passed"] for point in parsed_points
        )

    maximum_velocity_error = None
    moving_samples = 0
    velocity_valid = isinstance(velocity_samples, Sequence) and bool(velocity_samples)
    velocity_errors = []
    if velocity_valid:
        for sample in velocity_samples:
            if not isinstance(sample, Mapping):
                velocity_valid = False
                break
            api = _finite_array(sample.get("api_pad_velocity_m_s"), (2,))
            finite_difference = _finite_array(
                sample.get("finite_difference_pad_velocity_m_s"), (2,)
            )
            if api is None or finite_difference is None:
                velocity_valid = False
                break
            velocity_errors.extend(np.abs(api - finite_difference).tolist())
            if max(np.max(np.abs(api)), np.max(np.abs(finite_difference))) > 1.0e-5:
                moving_samples += 1
    if velocity_valid and velocity_errors:
        maximum_velocity_error = float(max(velocity_errors))
    velocity_agreement = bool(
        velocity_valid
        and moving_samples > 0
        and maximum_velocity_error is not None
        and maximum_velocity_error <= velocity_tolerance
    )
    checks = {
        "target_sequence_exact": target_sequence_exact,
        "joint_aperture_monotonic": joint_monotonic,
        "cooked_gap_monotonic": gap_monotonic,
        "bilateral_motion_observed": bilateral_motion,
        "asymmetry_within_limit": asymmetry_valid,
        "limit_saturation_valid": limit_saturation_valid,
        "full_open_confirmed": full_open_confirmed,
        "measured_open_authority": bool(open_contract.get("passed")),
        "settled_at_every_point": settled_everywhere,
        "continuous_settle_window": continuous_settle,
        "velocity_agreement": velocity_agreement,
    }
    return {
        "checks": checks,
        "maximum_left_right_asymmetry_m": maximum_asymmetry,
        "maximum_allowed_asymmetry_m": asymmetry_limit,
        "maximum_velocity_disagreement_m_s": maximum_velocity_error,
        "velocity_agreement_tolerance_m_s": velocity_tolerance,
        "moving_velocity_sample_count": moving_samples,
        "open_contract": open_contract,
        "passed": all(checks.values()),
    }


def orientation_edge_displacement_bounds(
    *,
    edge_radii_m: Mapping[str, Any],
    maximum_orientation_error_degrees: Any,
) -> dict[str, float | None]:
    if not isinstance(edge_radii_m, Mapping) or set(edge_radii_m) != set(SIDES):
        raise ValueError("trajectory_preflight_edge_radii_invalid")
    angle = _optional_nonnegative(maximum_orientation_error_degrees)
    result: dict[str, float | None] = {}
    for side in SIDES:
        radius = _optional_nonnegative(edge_radii_m.get(side))
        result[side] = (
            None
            if radius is None or angle is None
            else 2.0 * radius * math.sin(math.radians(angle) / 2.0)
        )
    return result


def evaluate_swept_clearance_budget(
    *,
    geometric_clearance_m: Mapping[str, Any],
    source_contact_offset_m: Any,
    finger_contact_offset_bounds_m: Mapping[str, Any],
    trajectory_uncertainty_m: Mapping[str, Any],
    numerical_margin_m: Any,
    environment_pairwise_budget: Mapping[str, Any],
) -> dict[str, Any]:
    side_mappings = {
        "geometric_clearance_m": geometric_clearance_m,
        "finger_contact_offset_bound_m": finger_contact_offset_bounds_m,
        "trajectory_uncertainty_m": trajectory_uncertainty_m,
    }
    if any(
        not isinstance(value, Mapping) or set(value) != set(SIDES)
        for value in side_mappings.values()
    ):
        raise ValueError("trajectory_preflight_clearance_sides_invalid")
    source_offset = _optional_nonnegative(source_contact_offset_m)
    margin = _optional_nonnegative(numerical_margin_m)
    unknown = []
    per_side = {}
    for side in SIDES:
        values = {
            name: _optional_nonnegative(mapping.get(side))
            for name, mapping in side_mappings.items()
        }
        if source_offset is None:
            unknown.append(f"{side}.source_contact_offset_m")
        for name in (
            "geometric_clearance_m",
            "finger_contact_offset_bound_m",
            "trajectory_uncertainty_m",
        ):
            if values[name] is None:
                unknown.append(f"{side}.{name}")
        if margin is None:
            unknown.append(f"{side}.numerical_margin_m")
        complete = bool(
            source_offset is not None
            and margin is not None
            and all(value is not None for value in values.values())
        )
        required = None
        remaining = None
        if complete:
            required = float(
                source_offset
                + values["finger_contact_offset_bound_m"]
                + values["trajectory_uncertainty_m"]
                + margin
            )
            remaining = float(values["geometric_clearance_m"] - required)
        per_side[side] = {
            **values,
            "source_contact_offset_m": source_offset,
            "numerical_margin_m": margin,
            "required_clearance_m": required,
            "remaining_clearance_m": remaining,
            "passed": bool(complete and remaining is not None and remaining > 0.0),
        }

    environment_checks = {}
    normalized_environment = {}
    if not isinstance(environment_pairwise_budget, Mapping):
        environment_pairwise_budget = {}
    for name in ENVIRONMENT_CLEARANCE_NAMES:
        record = environment_pairwise_budget.get(name)
        value = _optional_nonnegative(
            record.get("remaining_clearance_m")
            if isinstance(record, Mapping)
            else None
        )
        valid = bool(
            isinstance(record, Mapping)
            and record.get("passed") is True
            and value is not None
            and value > 0.0
        )
        environment_checks[name] = valid
        normalized_environment[name] = dict(record) if isinstance(record, Mapping) else None
        if value is None:
            unknown.append(f"environment.{name}")
    return {
        "budget_method": (
            "realized_geometry_plus_offset_bounds_plus_measured_repeatability_"
            "quantization_uncertainty"
        ),
        "per_side": per_side,
        "environment_pairwise_budget": normalized_environment,
        "environment_checks": environment_checks,
        "unknown_budget_terms": unknown,
        "measurement_complete": not unknown,
        "passed": bool(
            not unknown
            and all(record["passed"] for record in per_side.values())
            and all(environment_checks.values())
        ),
    }


def _world_bounds(value: Any) -> tuple[np.ndarray, np.ndarray] | None:
    if not isinstance(value, Mapping) or set(value) != {"min_m", "max_m"}:
        return None
    low = _finite_array(value.get("min_m"), (3,))
    high = _finite_array(value.get("max_m"), (3,))
    if low is None or high is None or np.any(high < low):
        return None
    return low, high


def evaluate_remote_calibration_clearance_budget(
    *,
    calibration_body_world_bounds_m: Mapping[str, Any],
    obstacle_world_bounds_m: Mapping[str, Any],
    obstacle_contact_offset_bounds_m: Mapping[str, Any],
    obstacle_roles: Mapping[str, Any],
    calibration_body_role: str,
    required_obstacle_paths: Sequence[str],
    calibration_body_projection_interval_m: Sequence[float],
    finger_inner_projection_interval_m: Sequence[float],
    calibration_body_contact_offset_m: Any,
    numerical_margin_m: Any,
) -> dict[str, Any]:
    authority = "pre_enable_remote_calibration_clearance_budget_v1"
    required_paths = (
        list(required_obstacle_paths)
        if isinstance(required_obstacle_paths, Sequence)
        and not isinstance(required_obstacle_paths, (str, bytes))
        else []
    )
    body_bounds = _world_bounds(calibration_body_world_bounds_m)
    body_projection = _finite_array(
        calibration_body_projection_interval_m, (2,)
    )
    finger_projection = _finite_array(
        finger_inner_projection_interval_m, (2,)
    )
    body_offset = _optional_nonnegative(calibration_body_contact_offset_m)
    margin = _optional_nonnegative(numerical_margin_m)
    structure_valid = bool(
        required_paths
        and all(isinstance(path, str) and path.startswith("/") for path in required_paths)
        and required_paths == sorted(required_paths)
        and len(set(required_paths)) == len(required_paths)
        and isinstance(obstacle_world_bounds_m, Mapping)
        and set(obstacle_world_bounds_m) == set(required_paths)
        and isinstance(obstacle_contact_offset_bounds_m, Mapping)
        and set(obstacle_contact_offset_bounds_m) == set(required_paths)
        and isinstance(obstacle_roles, Mapping)
        and set(obstacle_roles) == set(required_paths)
        and calibration_body_role == "static"
        and all(
            obstacle_roles.get(path) in {"static", "kinematic", "dynamic"}
            for path in required_paths
        )
        and body_bounds is not None
        and body_projection is not None
        and finger_projection is not None
        and body_projection[0] <= body_projection[1]
        and finger_projection[0] <= finger_projection[1]
        and body_offset is not None
        and body_offset > 0.0
        and margin is not None
        and margin > 0.0
    )
    placement_valid = bool(
        structure_valid
        and finger_projection[0] < body_projection[0]
        and body_projection[1] < finger_projection[1]
    )
    per_obstacle: dict[str, Any] = {}
    for path in required_paths:
        obstacle_bounds = _world_bounds(
            obstacle_world_bounds_m.get(path)
            if isinstance(obstacle_world_bounds_m, Mapping)
            else None
        )
        obstacle_offset = _optional_nonnegative(
            obstacle_contact_offset_bounds_m.get(path)
            if isinstance(obstacle_contact_offset_bounds_m, Mapping)
            else None
        )
        obstacle_role = (
            obstacle_roles.get(path) if isinstance(obstacle_roles, Mapping) else None
        )
        interaction_mode = (
            "static_static_no_contact_pair"
            if calibration_body_role == "static" and obstacle_role == "static"
            else "contact_offset_budget"
        )
        geometric = None
        if body_bounds is not None and obstacle_bounds is not None:
            body_low, body_high = body_bounds
            obstacle_low, obstacle_high = obstacle_bounds
            separation = np.maximum(
                np.maximum(body_low - obstacle_high, obstacle_low - body_high),
                0.0,
            )
            geometric = float(np.linalg.norm(separation))
        complete = bool(
            structure_valid
            and geometric is not None
            and geometric > 0.0
            and (
                interaction_mode == "static_static_no_contact_pair"
                or obstacle_offset is not None
            )
        )
        required = (
            (
                float(margin)
                if interaction_mode == "static_static_no_contact_pair"
                else float(body_offset + obstacle_offset + margin)
            )
            if complete else None
        )
        remaining = (
            float(geometric - required) if required is not None else None
        )
        per_obstacle[path] = {
            "geometric_clearance_m": geometric,
            "calibration_body_contact_offset_m": body_offset,
            "obstacle_contact_offset_bound_m": obstacle_offset,
            "calibration_body_role": calibration_body_role,
            "obstacle_role": obstacle_role,
            "interaction_mode": interaction_mode,
            "numerical_margin_m": margin,
            "required_clearance_m": required,
            "remaining_clearance_m": remaining,
            "passed": bool(
                complete
                and remaining is not None
                and remaining > 0.0
                and placement_valid
            ),
        }
    payload = {
        "authority": authority,
        "calibration_body_world_bounds_m": _json_native(
            calibration_body_world_bounds_m
        ),
        "obstacle_world_bounds_m": _json_native(obstacle_world_bounds_m),
        "obstacle_contact_offset_bounds_m": _json_native(
            obstacle_contact_offset_bounds_m
        ),
        "obstacle_roles": _json_native(obstacle_roles),
        "calibration_body_role": calibration_body_role,
        "required_obstacle_paths": required_paths,
        "calibration_body_projection_interval_m": _json_native(
            calibration_body_projection_interval_m
        ),
        "finger_inner_projection_interval_m": _json_native(
            finger_inner_projection_interval_m
        ),
        "calibration_body_contact_offset_m": body_offset,
        "numerical_margin_m": margin,
        "placement_between_finger_pads": placement_valid,
        "per_obstacle": per_obstacle,
        "passed": bool(
            structure_valid
            and placement_valid
            and len(per_obstacle) == len(required_paths)
            and all(record["passed"] for record in per_obstacle.values())
        ),
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def validate_remote_calibration_clearance_budget(
    evidence: Any,
    *,
    expected_obstacle_paths: Sequence[str] | None = None,
    expected_obstacle_offsets_m: Mapping[str, Any] | None = None,
) -> bool:
    if not isinstance(evidence, Mapping):
        return False
    try:
        recomputed = evaluate_remote_calibration_clearance_budget(
            calibration_body_world_bounds_m=evidence.get(
                "calibration_body_world_bounds_m", {}
            ),
            obstacle_world_bounds_m=evidence.get("obstacle_world_bounds_m", {}),
            obstacle_contact_offset_bounds_m=evidence.get(
                "obstacle_contact_offset_bounds_m", {}
            ),
            obstacle_roles=evidence.get("obstacle_roles", {}),
            calibration_body_role=evidence.get("calibration_body_role"),
            required_obstacle_paths=evidence.get("required_obstacle_paths", []),
            calibration_body_projection_interval_m=evidence.get(
                "calibration_body_projection_interval_m", []
            ),
            finger_inner_projection_interval_m=evidence.get(
                "finger_inner_projection_interval_m", []
            ),
            calibration_body_contact_offset_m=evidence.get(
                "calibration_body_contact_offset_m"
            ),
            numerical_margin_m=evidence.get("numerical_margin_m"),
        )
    except (TypeError, ValueError):
        return False
    return bool(
        dict(evidence) == recomputed
        and recomputed.get("passed") is True
        and (
            expected_obstacle_paths is None
            or recomputed.get("required_obstacle_paths")
            == list(expected_obstacle_paths)
        )
        and (
            expected_obstacle_offsets_m is None
            or recomputed.get("obstacle_contact_offset_bounds_m")
            == dict(expected_obstacle_offsets_m)
        )
    )


def evaluate_calibration_layer_cleanup(
    *,
    previous_session_sublayers: Sequence[str],
    inserted_session_sublayers: Sequence[str],
    restored_session_sublayers: Sequence[str],
    calibration_layer_identifier: str,
    authoring_edit_target: str,
    enable_edit_target: str,
    disable_edit_target: str,
    previous_edit_target: str,
    restored_edit_target: str,
    physics_step_before_cleanup: int,
    physics_step_after_cleanup: int,
    calibration_body_valid_after_cleanup: bool,
    calibration_scope_valid_after_cleanup: bool,
    overlap_hit_paths_after_cleanup: Sequence[str],
    calibration_body_path: str,
) -> dict[str, Any]:
    lists_valid = all(
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and all(isinstance(item, str) and item for item in value)
        for value in (
            previous_session_sublayers,
            inserted_session_sublayers,
            restored_session_sublayers,
            overlap_hit_paths_after_cleanup,
        )
    )
    previous = list(previous_session_sublayers) if lists_valid else []
    inserted = list(inserted_session_sublayers) if lists_valid else []
    restored = list(restored_session_sublayers) if lists_valid else []
    overlap_paths = list(overlap_hit_paths_after_cleanup) if lists_valid else []
    structure_valid = bool(
        lists_valid
        and isinstance(calibration_layer_identifier, str)
        and calibration_layer_identifier
        and all(
            isinstance(value, str) and value
            for value in (
                authoring_edit_target,
                enable_edit_target,
                disable_edit_target,
                previous_edit_target,
                restored_edit_target,
                calibration_body_path,
            )
        )
        and type(physics_step_before_cleanup) is int
        and type(physics_step_after_cleanup) is int
        and type(calibration_body_valid_after_cleanup) is bool
        and type(calibration_scope_valid_after_cleanup) is bool
    )
    checks = {
        "inserted_once_at_front": bool(
            structure_valid
            and inserted == [calibration_layer_identifier, *previous]
        ),
        "session_sublayers_restored": bool(structure_valid and restored == previous),
        "all_body_edits_target_calibration_layer": bool(
            structure_valid
            and authoring_edit_target == calibration_layer_identifier
            and enable_edit_target == calibration_layer_identifier
            and disable_edit_target == calibration_layer_identifier
        ),
        "edit_target_restored": bool(
            structure_valid and restored_edit_target == previous_edit_target
        ),
        "cleanup_did_not_step_physics": bool(
            structure_valid
            and physics_step_after_cleanup == physics_step_before_cleanup
        ),
        "usd_body_and_scope_absent": bool(
            structure_valid
            and not calibration_body_valid_after_cleanup
            and not calibration_scope_valid_after_cleanup
        ),
        "physx_shape_absent": bool(
            structure_valid
            and all(
                path != calibration_body_path
                and not path.startswith(calibration_body_path + "/")
                for path in overlap_paths
            )
        ),
    }
    payload = {
        "authority": "anonymous_calibration_layer_no_step_physx_cleanup_v1",
        "previous_session_sublayers": previous,
        "inserted_session_sublayers": inserted,
        "restored_session_sublayers": restored,
        "calibration_layer_identifier": calibration_layer_identifier,
        "authoring_edit_target": authoring_edit_target,
        "enable_edit_target": enable_edit_target,
        "disable_edit_target": disable_edit_target,
        "previous_edit_target": previous_edit_target,
        "restored_edit_target": restored_edit_target,
        "physics_step_before_cleanup": physics_step_before_cleanup,
        "physics_step_after_cleanup": physics_step_after_cleanup,
        "calibration_body_valid_after_cleanup": calibration_body_valid_after_cleanup,
        "calibration_scope_valid_after_cleanup": calibration_scope_valid_after_cleanup,
        "overlap_hit_paths_after_cleanup": overlap_paths,
        "calibration_body_path": calibration_body_path,
        "checks": checks,
        "passed": bool(structure_valid and all(checks.values())),
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def evaluate_source_isolation_snapshot(
    *,
    checkpoint: str,
    source_body_path: str,
    source_kinematic_enabled: Any,
    filtered_pair_targets: Sequence[str],
    expected_robot_rigid_body_paths: Sequence[str],
    contact_report_api_applied: Any,
    contact_report_threshold: Any,
    source_world_matrix: Sequence[Sequence[float]],
    expected_source_world_matrix: Sequence[Sequence[float]],
) -> dict[str, Any]:
    targets = list(filtered_pair_targets) if isinstance(filtered_pair_targets, Sequence) and not isinstance(filtered_pair_targets, (str, bytes)) else []
    expected_targets = list(expected_robot_rigid_body_paths) if isinstance(expected_robot_rigid_body_paths, Sequence) and not isinstance(expected_robot_rigid_body_paths, (str, bytes)) else []
    matrix = _finite_array(source_world_matrix, (4, 4))
    expected_matrix = _finite_array(expected_source_world_matrix, (4, 4))
    threshold = _optional_nonnegative(contact_report_threshold)
    source_pose_error = {
        "authority": "float32_world_matrix_recomposition_16ulp_v1",
        "maximum_matrix_element_error": None,
        "matrix_element_tolerance": None,
        "translation_error_m": None,
        "translation_tolerance_m": None,
        "orientation_error_degrees": None,
        "orientation_tolerance_degrees": None,
    }
    fixed_source_pose = False
    if (
        matrix is not None
        and expected_matrix is not None
        and np.array_equal(matrix[:, 3], [0.0, 0.0, 0.0, 1.0])
        and np.array_equal(expected_matrix[:, 3], [0.0, 0.0, 0.0, 1.0])
    ):
        scale = max(
            1.0,
            float(np.max(np.abs(matrix))),
            float(np.max(np.abs(expected_matrix))),
        )
        element_tolerance = math.nextafter(
            16.0 * float(np.finfo(np.float32).eps) * scale, math.inf
        )
        translation_tolerance = math.sqrt(3.0) * element_tolerance
        orientation_tolerance = math.degrees(
            2.0
            * math.asin(
                min(1.0, 3.0 * element_tolerance / (2.0 * math.sqrt(2.0)))
            )
        )
        maximum_element_error = float(np.max(np.abs(matrix - expected_matrix)))
        translation_error = float(
            np.linalg.norm(matrix[3, :3] - expected_matrix[3, :3])
        )
        relative_rotation = matrix[:3, :3] @ expected_matrix[:3, :3].T
        orientation_error = math.degrees(
            math.acos(
                float(np.clip((float(np.trace(relative_rotation)) - 1.0) / 2.0, -1.0, 1.0))
            )
        )
        source_pose_error = {
            "authority": "float32_world_matrix_recomposition_16ulp_v1",
            "maximum_matrix_element_error": maximum_element_error,
            "matrix_element_tolerance": element_tolerance,
            "translation_error_m": translation_error,
            "translation_tolerance_m": translation_tolerance,
            "orientation_error_degrees": orientation_error,
            "orientation_tolerance_degrees": orientation_tolerance,
        }
        fixed_source_pose = bool(
            maximum_element_error <= element_tolerance
            and translation_error <= translation_tolerance
            and orientation_error <= orientation_tolerance
        )
    checks = {
        "checkpoint_valid": isinstance(checkpoint, str) and bool(checkpoint),
        "source_path_valid": isinstance(source_body_path, str)
        and source_body_path.startswith("/"),
        "source_kinematic": source_kinematic_enabled is True,
        "exact_filtered_pair_targets": bool(
            expected_targets
            and all(isinstance(path, str) for path in expected_targets)
            and expected_targets == sorted(expected_targets)
            and targets == expected_targets
        ),
        "contact_report_suppressed": bool(
            contact_report_api_applied is False
            and threshold is not None
            and threshold == float(np.finfo(np.float32).max)
        ),
        "fixed_source_pose": fixed_source_pose,
    }
    payload = {
        "authority": "source_isolation_snapshot_v1",
        "checkpoint": checkpoint,
        "source_body_path": source_body_path,
        "source_kinematic_enabled": source_kinematic_enabled,
        "filtered_pair_targets": targets,
        "expected_robot_rigid_body_paths": expected_targets,
        "contact_report_api_applied": contact_report_api_applied,
        "contact_report_threshold": threshold,
        "source_world_matrix": _json_native(source_world_matrix),
        "expected_source_world_matrix": _json_native(
            expected_source_world_matrix
        ),
        "source_pose_error": source_pose_error,
        "checks": checks,
        "passed": all(checks.values()),
    }
    return {**payload, "evidence_sha256": canonical_json_sha256(payload)}


def require_source_isolation_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if (
        not isinstance(snapshot, Mapping)
        or not isinstance(snapshot.get("checkpoint"), str)
        or not snapshot.get("checkpoint")
        or not isinstance(snapshot.get("checks"), Mapping)
    ):
        raise RuntimeError("trajectory_preflight_source_isolation_evidence_invalid")
    if snapshot.get("passed") is not True:
        raise MeasurementNoGo(
            f"trajectory_preflight_source_isolation_failed:{snapshot['checkpoint']}",
            snapshot,
        )
    return dict(snapshot)


def _stage_inventory_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "joint_paths",
        "constraint_paths",
        "fixed_attachment_paths",
        "constraint_records",
        "inventory_sha256",
    }:
        return False
    path_fields = (
        "joint_paths",
        "constraint_paths",
        "fixed_attachment_paths",
    )
    for field in path_fields:
        paths = value.get(field)
        if (
            not isinstance(paths, Sequence)
            or isinstance(paths, (str, bytes))
            or any(not isinstance(path, str) or not path.startswith("/") for path in paths)
            or list(paths) != sorted(paths)
            or len(set(paths)) != len(paths)
        ):
            return False
    records = value.get("constraint_records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        return False
    record_paths = []
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "schema_type",
            "body0_targets",
            "body1_targets",
        }:
            return False
        path = record.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            return False
        for field in ("body0_targets", "body1_targets"):
            targets = record.get(field)
            if (
                not isinstance(targets, Sequence)
                or isinstance(targets, (str, bytes))
                or any(
                    not isinstance(target, str) or not target.startswith("/")
                    for target in targets
                )
                or list(targets) != sorted(targets)
                or len(set(targets)) != len(targets)
            ):
                return False
        record_paths.append(path)
    payload = {key: value[key] for key in value if key != "inventory_sha256"}
    return bool(
        record_paths == sorted(record_paths)
        and len(set(record_paths)) == len(record_paths)
        and list(value["constraint_paths"]) == record_paths
        and set(value["joint_paths"]).issubset(record_paths)
        and value.get("inventory_sha256") == canonical_json_sha256(payload)
    )


def evaluate_attachment_inventory(
    *,
    pre_inventory: Mapping[str, Any],
    post_inventory: Mapping[str, Any],
    source_body_path: str,
    robot_rigid_body_paths: Sequence[str],
) -> dict[str, Any]:
    robot_paths = list(robot_rigid_body_paths) if isinstance(robot_rigid_body_paths, Sequence) and not isinstance(robot_rigid_body_paths, (str, bytes)) else []

    def belongs(path: str, roots: Sequence[str]) -> bool:
        return any(path == root or path.startswith(root + "/") for root in roots)

    source_robot_paths = set()
    for inventory in (pre_inventory, post_inventory):
        if not isinstance(inventory, Mapping):
            continue
        for record in inventory.get("constraint_records", []):
            if not isinstance(record, Mapping):
                continue
            body0 = record.get("body0_targets", [])
            body1 = record.get("body1_targets", [])
            for first in body0:
                for second in body1:
                    if (
                        belongs(first, [source_body_path])
                        and belongs(second, robot_paths)
                    ) or (
                        belongs(second, [source_body_path])
                        and belongs(first, robot_paths)
                    ):
                        source_robot_paths.add(str(record.get("path")))
    checks = {
        "pre_inventory_valid": _stage_inventory_valid(pre_inventory),
        "post_inventory_valid": _stage_inventory_valid(post_inventory),
        "inventories_unchanged": pre_inventory == post_inventory,
        "source_robot_attachment_absent": not source_robot_paths,
    }
    return {
        "authority": "endpoint_aware_stage_constraint_inventory_v1",
        "checks": checks,
        "source_robot_constraint_paths": sorted(source_robot_paths),
        "passed": all(checks.values()),
    }


def recompute_trace_geometry(
    *,
    trace: Sequence[Mapping[str, Any]],
    geometry_catalogs: Mapping[str, Any],
    opening_axis_world: Sequence[float],
    trajectory_uncertainty_m: Mapping[str, Any],
    numerical_margin_m: Any,
) -> dict[str, Any]:
    geometric_values = {side: [] for side in SIDES}
    environment_values = {name: [] for name in ENVIRONMENT_CLEARANCE_NAMES}
    reported_values_match = True
    recomputed = False
    error = None
    environment_pairwise_budget: dict[str, Any] = {}
    unknown_environment_offset_pairs: list[str] = []
    try:
        if (
            not isinstance(trace, Sequence)
            or isinstance(trace, (str, bytes))
            or not trace
            or not isinstance(geometry_catalogs, Mapping)
            or set(geometry_catalogs)
            != {
                "source",
                "table",
                "robot_bodies",
                "robot_rigid_body_paths",
                "colliderless_robot_bodies",
                "all_robot_rigid_body_paths",
                "robot_collider_inventory",
                "inventory_sha256",
            }
        ):
            raise ValueError("trajectory_preflight_parent_geometry_inputs_invalid")
        axis = _finite_array(opening_axis_world, (3,))
        if axis is None or not math.isclose(
            float(np.linalg.norm(axis)), 1.0, rel_tol=0.0, abs_tol=1.0e-9
        ):
            raise ValueError("trajectory_preflight_parent_geometry_axis_invalid")
        source = validate_cooked_catalog(geometry_catalogs["source"])
        table = validate_static_cooked_catalog(
            geometry_catalogs["table"], expected_body_path=EXPECTED_TABLE_BODY_PATH
        )
        robot_bodies = geometry_catalogs["robot_bodies"]
        moving_paths = geometry_catalogs["robot_rigid_body_paths"]
        colliderless_robot_bodies = geometry_catalogs["colliderless_robot_bodies"]
        all_robot_paths = geometry_catalogs["all_robot_rigid_body_paths"]
        collider_inventory = geometry_catalogs["robot_collider_inventory"]
        expected_colliderless_robot_bodies = {
            path: _colliderless_rigid_body_evidence_record(path)
            for path in EXPECTED_COLLIDERLESS_ROBOT_BODY_PATHS
        }
        if (
            not isinstance(robot_bodies, Mapping)
            or not robot_bodies
            or not isinstance(moving_paths, Sequence)
            or isinstance(moving_paths, (str, bytes))
            or not moving_paths
            or any(not isinstance(path, str) for path in moving_paths)
            or len(set(moving_paths)) != len(moving_paths)
            or set(moving_paths) != set(robot_bodies)
            or list(moving_paths) != sorted(moving_paths)
            or not isinstance(colliderless_robot_bodies, Mapping)
            or dict(colliderless_robot_bodies) != expected_colliderless_robot_bodies
            or not isinstance(all_robot_paths, Sequence)
            or isinstance(all_robot_paths, (str, bytes))
            or list(all_robot_paths) != sorted(all_robot_paths)
            or len(set(all_robot_paths)) != len(all_robot_paths)
            or list(all_robot_paths)
            != sorted([*moving_paths, *colliderless_robot_bodies])
            or not isinstance(collider_inventory, Mapping)
        ):
            raise ValueError("trajectory_preflight_moving_robot_catalogs_invalid")
        validated_robot = {
            path: validate_cooked_catalog(catalog)
            for path, catalog in robot_bodies.items()
        }
        if any(catalog.get("body_path") != path for path, catalog in validated_robot.items()):
            raise ValueError("trajectory_preflight_moving_robot_catalogs_invalid")
        expected_inventory = {
            path: [str(collider["path"]) for collider in catalog["colliders"]]
            for path, catalog in validated_robot.items()
        }
        inventory_payload = {
            "robot_rigid_body_paths": list(moving_paths),
            "colliderless_robot_bodies": dict(colliderless_robot_bodies),
            "all_robot_rigid_body_paths": list(all_robot_paths),
            "robot_collider_inventory": expected_inventory,
        }
        if (
            dict(collider_inventory) != expected_inventory
            or geometry_catalogs.get("inventory_sha256")
            != canonical_json_sha256(inventory_payload)
        ):
            raise ValueError("trajectory_preflight_robot_inventory_invalid")
        required_robot = {
            EXPECTED_FINGER_BODY_PATHS["left"],
            EXPECTED_FINGER_BODY_PATHS["right"],
            "/World/Franka/panda_hand",
        }
        if not required_robot.issubset(validated_robot):
            raise ValueError("trajectory_preflight_moving_robot_catalogs_invalid")
        unrelated_paths = sorted(set(validated_robot) - required_robot)
        if not unrelated_paths:
            raise ValueError("trajectory_preflight_unrelated_robot_catalogs_missing")
        expected_matrix_paths = {
            str(source["body_path"]),
            str(table["body_path"]),
            *validated_robot,
        }

        def contact_offset(catalog: Mapping[str, Any]) -> float | None:
            values = []
            for collider in catalog["colliders"]:
                offset = collider.get("contact_offset")
                value = _optional_nonnegative(
                    offset.get("contact_offset_m")
                    if isinstance(offset, Mapping)
                    else None
                )
                if value is None:
                    return None
                values.append(value)
            return max(values) if values else None

        source_offset = contact_offset(source)
        table_offset = contact_offset(table)
        robot_offsets = {
            path: contact_offset(catalog) for path, catalog in validated_robot.items()
        }

        def bounds(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            return points.min(axis=0), points.max(axis=0)

        def distance(
            first: tuple[np.ndarray, np.ndarray],
            second: tuple[np.ndarray, np.ndarray],
        ) -> float:
            first_low, first_high = first
            second_low, second_high = second
            separation = np.maximum(
                np.maximum(first_low - second_high, second_low - first_high), 0.0
            )
            return float(np.linalg.norm(separation))

        for record in trace:
            if not isinstance(record, Mapping):
                raise ValueError("trajectory_preflight_parent_geometry_record_invalid")
            matrices = record.get("geometry_world_matrices")
            if not isinstance(matrices, Mapping) or set(matrices) != expected_matrix_paths:
                raise ValueError("trajectory_preflight_parent_geometry_matrices_invalid")
            source_points = _catalog_world_points(
                source, matrices[str(source["body_path"])]
            )
            table_bounds = bounds(
                _catalog_world_points(table, matrices[str(table["body_path"])])
            )
            source_bounds = bounds(source_points)
            source_projection = source_points @ axis
            source_interval = (
                float(np.min(source_projection)), float(np.max(source_projection))
            )
            robot_bounds = {}
            computed_geometric = {}
            for side in SIDES:
                path = EXPECTED_FINGER_BODY_PATHS[side]
                points = _catalog_world_points(validated_robot[path], matrices[path])
                robot_bounds[path] = bounds(points)
                projection = points @ axis
                interval = (float(np.min(projection)), float(np.max(projection)))
                if sum(interval) / 2.0 <= sum(source_interval) / 2.0:
                    clearance = source_interval[0] - interval[1]
                else:
                    clearance = interval[0] - source_interval[1]
                computed_geometric[side] = max(0.0, float(clearance))
            for path, catalog in validated_robot.items():
                if path not in robot_bounds:
                    robot_bounds[path] = bounds(
                        _catalog_world_points(catalog, matrices[path])
                    )
            hand_path = "/World/Franka/panda_hand"
            computed_environment = {
                "hand_to_source": distance(robot_bounds[hand_path], source_bounds),
                "swept_bodies_to_table": min(
                    distance(robot_bounds[path], table_bounds) for path in moving_paths
                ),
                "source_to_unrelated_robot_links": min(
                    distance(source_bounds, robot_bounds[path])
                    for path in unrelated_paths
                ),
            }
            reported_geometric = record.get("geometric_clearance_m")
            reported_environment = record.get("environment_clearance_m")
            if not isinstance(reported_geometric, Mapping) or not isinstance(
                reported_environment, Mapping
            ):
                reported_values_match = False
            for side, value in computed_geometric.items():
                geometric_values[side].append(value)
                reported = (
                    _optional_nonnegative(reported_geometric.get(side))
                    if isinstance(reported_geometric, Mapping)
                    else None
                )
                if reported is None or not math.isclose(
                    reported, value, rel_tol=0.0, abs_tol=1.0e-12
                ):
                    reported_values_match = False
            for name, value in computed_environment.items():
                environment_values[name].append(value)
                reported = (
                    _optional_nonnegative(reported_environment.get(name))
                    if isinstance(reported_environment, Mapping)
                    else None
                )
                if reported is None or not math.isclose(
                    reported, value, rel_tol=0.0, abs_tol=1.0e-12
                ):
                    reported_values_match = False
        recomputed = all(
            len(values) == len(trace)
            for values in (*geometric_values.values(), *environment_values.values())
        )

        uncertainty_values = (
            {
                side: _optional_nonnegative(trajectory_uncertainty_m.get(side))
                for side in SIDES
            }
            if isinstance(trajectory_uncertainty_m, Mapping)
            and set(trajectory_uncertainty_m) == set(SIDES)
            else {side: None for side in SIDES}
        )
        maximum_uncertainty = (
            max(float(value) for value in uncertainty_values.values())
            if all(value is not None for value in uncertainty_values.values())
            else None
        )
        margin = _optional_nonnegative(numerical_margin_m)
        pair_offsets = {
            "hand_to_source": (
                source_offset,
                robot_offsets.get("/World/Franka/panda_hand"),
            ),
            "swept_bodies_to_table": (
                table_offset,
                None
                if any(robot_offsets.get(path) is None for path in moving_paths)
                else max(float(robot_offsets[path]) for path in moving_paths),
            ),
            "source_to_unrelated_robot_links": (
                source_offset,
                None
                if any(robot_offsets.get(path) is None for path in unrelated_paths)
                else max(float(robot_offsets[path]) for path in unrelated_paths),
            ),
        }
        for name in ENVIRONMENT_CLEARANCE_NAMES:
            first_offset, second_offset = pair_offsets[name]
            geometric = (
                min(environment_values[name])
                if recomputed and environment_values[name]
                else None
            )
            complete = bool(
                geometric is not None
                and first_offset is not None
                and second_offset is not None
                and maximum_uncertainty is not None
                and margin is not None
            )
            if not complete:
                unknown_environment_offset_pairs.append(name)
            required = (
                None
                if not complete
                else float(
                    first_offset + second_offset + maximum_uncertainty + margin
                )
            )
            remaining = (
                None if required is None else float(geometric - required)
            )
            environment_pairwise_budget[name] = {
                "geometric_clearance_m": geometric,
                "first_collider_contact_offset_bound_m": first_offset,
                "second_collider_contact_offset_bound_m": second_offset,
                "trajectory_uncertainty_m": maximum_uncertainty,
                "numerical_margin_m": margin,
                "required_clearance_m": required,
                "remaining_clearance_m": remaining,
                "passed": bool(complete and remaining is not None and remaining > 0.0),
            }
    except (KeyError, TypeError, ValueError) as exc:
        error = f"{type(exc).__name__}:{exc}"

    geometric_minima = {
        side: min(values) if recomputed and values else None
        for side, values in geometric_values.items()
    }
    environment_minima = {
        name: min(values) if recomputed and values else None
        for name, values in environment_values.items()
    }
    return {
        "parent_geometry_recomputed": recomputed,
        "reported_values_match": bool(recomputed and reported_values_match),
        "geometric_clearance_minima_m": geometric_minima,
        "environment_clearance_minima_m": environment_minima,
        "environment_pairwise_budget": environment_pairwise_budget,
        "unknown_environment_offset_pairs": unknown_environment_offset_pairs,
        "error": error,
        "passed": bool(
            recomputed
            and reported_values_match
            and not unknown_environment_offset_pairs
            and all(
                record.get("passed") is True
                for record in environment_pairwise_budget.values()
            )
        ),
    }


def canonical_action_hash(action_payload: Mapping[str, Any]) -> str:
    if not isinstance(action_payload, Mapping):
        raise TypeError("trajectory_preflight_action_mapping_required")
    return canonical_json_sha256(action_payload)


def map_tool_target_to_control_pose(
    *,
    tool_pose: Mapping[str, Any],
    control_to_tool_matrix_m: Sequence[Sequence[float]],
    meters_per_stage_unit: float = 1.0,
) -> dict[str, Any]:
    from scipy.spatial.transform import Rotation

    if not _pose_valid(tool_pose):
        raise ValueError("trajectory_preflight_tool_target_pose_invalid")
    matrix = _finite_array(control_to_tool_matrix_m, (4, 4))
    units = _finite_number(meters_per_stage_unit, positive=True)
    if matrix is None or not np.allclose(
        matrix[:, 3], [0.0, 0.0, 0.0, 1.0], rtol=0.0, atol=1.0e-12
    ):
        raise ValueError("trajectory_preflight_control_to_tool_matrix_invalid")
    quaternion = np.asarray(tool_pose["orientation_wxyz"], dtype=np.float64)
    quaternion /= np.linalg.norm(quaternion)
    tool_world = np.eye(4, dtype=np.float64)
    tool_world[:3, :3] = Rotation.from_quat(
        quaternion[[1, 2, 3, 0]]
    ).as_matrix().T
    tool_world[3, :3] = np.asarray(tool_pose["position_m"], dtype=np.float64)
    scaled = matrix.copy()
    scaled[3, :3] /= units
    control_world = scaled @ tool_world
    control_xyzw = Rotation.from_matrix(control_world[:3, :3].T).as_quat()
    return {
        "position_m": control_world[3, :3].tolist(),
        "orientation_wxyz": control_xyzw[[3, 0, 1, 2]].tolist(),
    }


def derive_trajectory_uncertainty(
    *, trace: Sequence[Mapping[str, Any]], edge_radii_m: Mapping[str, Any]
) -> dict[str, Any]:
    formula = (
        "collider_projection_quantization + pose_quantization + "
        "max_absolute_or_repeatable_cross_track_error + "
        "max_absolute_or_repeatable_orientation_error_edge_chord"
    )
    invalid = {
        "formula": formula,
        "collider_projection_quantization_m": None,
        "pose_quantization_m": None,
        "cross_track_repeatability_m": None,
        "maximum_absolute_cross_track_error_m": None,
        "cross_track_envelope_m": None,
        "orientation_residual_repeatability_degrees": None,
        "maximum_absolute_orientation_error_degrees": None,
        "orientation_error_envelope_degrees": None,
        "orientation_edge_displacement_m": {side: None for side in SIDES},
        "per_side_m": {side: None for side in SIDES},
        "passed": False,
    }
    if (
        not isinstance(trace, Sequence)
        or isinstance(trace, (str, bytes))
        or not isinstance(edge_radii_m, Mapping)
        or set(edge_radii_m) != set(SIDES)
    ):
        return invalid
    radii = {side: _optional_nonnegative(edge_radii_m.get(side)) for side in SIDES}
    if any(value is None for value in radii.values()):
        return invalid
    residuals = []
    orientation_residuals = []
    pose_scale = 1.0
    collider_scale = 1.0
    for record in trace:
        if not isinstance(record, Mapping) or record.get("action_kind") not in TRACKED_ACTION_KINDS:
            continue
        commanded = _finite_array(
            record.get("commanded_tool_pose", {}).get("position_m"), (3,)
        )
        measured = _finite_array(
            record.get("measured_tool_pose", {}).get("position_m"), (3,)
        )
        orientation_error = _quaternion_error_degrees(
            record.get("commanded_tool_pose", {}).get("orientation_wxyz"),
            record.get("measured_tool_pose", {}).get("orientation_wxyz"),
        )
        if commanded is None or measured is None or orientation_error is None:
            return invalid
        colliders = record.get("collider_world_matrices")
        if not isinstance(colliders, Mapping):
            return invalid
        for collider_records in colliders.values():
            if not isinstance(collider_records, Sequence):
                return invalid
            for collider_record in collider_records:
                matrix = (
                    _finite_array(collider_record.get("matrix"), (4, 4))
                    if isinstance(collider_record, Mapping)
                    else None
                )
                if matrix is None:
                    return invalid
                collider_scale = max(
                    collider_scale, float(np.max(np.abs(matrix)))
                )
        pose_scale = max(
            pose_scale,
            float(np.max(np.abs(commanded))),
            float(np.max(np.abs(measured))),
        )
        error = measured - commanded
        residuals.append(error[:2])
        orientation_residuals.append(orientation_error)
    if not residuals:
        return invalid
    cross_track_repeatability = max(
        (
            float(np.linalg.norm(current - previous))
            for previous, current in zip(residuals, residuals[1:])
        ),
        default=0.0,
    )
    if cross_track_repeatability > 0.0:
        cross_track_repeatability = math.nextafter(
            cross_track_repeatability, math.inf
        )
    maximum_absolute_cross_track = max(
        float(np.linalg.norm(residual)) for residual in residuals
    )
    if maximum_absolute_cross_track > 0.0:
        maximum_absolute_cross_track = math.nextafter(
            maximum_absolute_cross_track, math.inf
        )
    orientation_repeatability = max(
        (
            abs(current - previous)
            for previous, current in zip(
                orientation_residuals, orientation_residuals[1:]
            )
        ),
        default=0.0,
    )
    maximum_absolute_orientation = max(orientation_residuals)
    cross_track_envelope = max(
        maximum_absolute_cross_track, cross_track_repeatability
    )
    orientation_envelope = max(
        maximum_absolute_orientation, orientation_repeatability
    )
    collider_quantization = math.nextafter(
        64.0 * float(np.finfo(np.float64).eps) * collider_scale, math.inf
    )
    pose_quantization = math.nextafter(
        64.0 * float(np.finfo(np.float64).eps) * pose_scale, math.inf
    )
    orientation_edges = {
        side: 2.0
        * float(radii[side])
        * math.sin(math.radians(orientation_envelope) / 2.0)
        for side in SIDES
    }
    per_side = {
        side: float(
            collider_quantization
            + pose_quantization
            + cross_track_envelope
            + orientation_edges[side]
        )
        for side in SIDES
    }
    return {
        "formula": formula,
        "collider_projection_quantization_m": collider_quantization,
        "pose_quantization_m": pose_quantization,
        "cross_track_repeatability_m": cross_track_repeatability,
        "maximum_absolute_cross_track_error_m": maximum_absolute_cross_track,
        "cross_track_envelope_m": cross_track_envelope,
        "orientation_residual_repeatability_degrees": orientation_repeatability,
        "maximum_absolute_orientation_error_degrees": (
            maximum_absolute_orientation
        ),
        "orientation_error_envelope_degrees": orientation_envelope,
        "orientation_edge_displacement_m": orientation_edges,
        "per_side_m": per_side,
        "passed": True,
    }


def _action_payload_matches_kind(
    payload: Any, kind: Any, *, canonical_open_target_m: float
) -> bool:
    if not isinstance(payload, Mapping) or not isinstance(kind, str):
        return False
    if (
        not {"joint_positions", "joint_velocities", "joint_efforts"}.issubset(payload)
        or not set(payload).issubset(
            {"joint_positions", "joint_velocities", "joint_efforts", "joint_indices"}
        )
        or payload.get("joint_velocities") is not None
        or payload.get("joint_efforts") is not None
    ):
        return False
    positions = payload.get("joint_positions")
    if not isinstance(positions, Sequence) or isinstance(positions, (str, bytes)):
        return False
    indices = payload.get("joint_indices")
    if indices is None:
        resolved_indices = list(range(len(positions)))
    elif (
        isinstance(indices, Sequence)
        and not isinstance(indices, (str, bytes))
        and len(indices) == len(positions)
        and all(type(index) is int and index >= 0 for index in indices)
    ):
        resolved_indices = list(indices)
    else:
        return False
    active = {}
    for index, value in zip(resolved_indices, positions):
        if value is None:
            continue
        number = _optional_nonnegative(value) if index in (7, 8) else None
        if index in (7, 8) and number is None:
            return False
        if index not in (7, 8):
            try:
                number = _finite_number(value)
            except ValueError:
                return False
        active[index] = number
    if kind == "GRIPPER_OPEN":
        return bool(
            len(positions) == 9
            and indices is None
            and set(active) == {7, 8}
            and all(
                math.isclose(
                    value,
                    canonical_open_target_m,
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
                for value in active.values()
            )
        )
    if kind in {"ARM_PREGRASP", "ARM_ALIGN", "ARM_INSERT", "ARM_SETTLE"}:
        return bool(
            len(positions) == 7
            and indices == list(range(7))
            and set(active) == set(range(7))
        )
    return False


def _pose_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    position = _finite_array(value.get("position_m"), (3,))
    orientation = _finite_array(value.get("orientation_wxyz"), (4,))
    return bool(
        position is not None
        and orientation is not None
        and float(np.linalg.norm(orientation)) > 1.0e-12
    )


def _collider_evidence_valid(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "left_finger",
        "right_finger",
        "hand",
    }:
        return False
    for records in value.values():
        if not isinstance(records, Sequence) or not records:
            return False
        for record in records:
            if (
                not isinstance(record, Mapping)
                or not isinstance(record.get("path"), str)
                or not record["path"].startswith("/")
                or _finite_array(record.get("matrix"), (4, 4)) is None
            ):
                return False
    return True


def validate_shadow_trace(
    trace: Sequence[Mapping[str, Any]],
    *,
    physics_dt: float,
    substeps_per_action: int,
    insertion_step_m: float,
    insert_distance_m: float,
    settle_duration_s: float,
    frozen_source_position_m: Sequence[float],
    expected_tool_orientation_wxyz: Sequence[float],
    requested_open_target_m: float,
    canonical_open_target_m: float,
    open_position_tolerance_m: float,
    stage_units_in_meters: float,
) -> dict[str, Any]:
    dt = _finite_number(physics_dt, positive=True)
    step_limit = _finite_number(insertion_step_m, positive=True)
    insert_distance = _finite_number(insert_distance_m, positive=True)
    settle_duration = _finite_number(settle_duration_s, positive=True)
    frozen_source = _finite_array(frozen_source_position_m, (3,))
    expected_orientation = _finite_array(expected_tool_orientation_wxyz, (4,))
    requested_open = _finite_number(requested_open_target_m, positive=True)
    canonical_open = _finite_number(canonical_open_target_m, positive=True)
    open_tolerance = _finite_number(open_position_tolerance_m, positive=True)
    stage_units = _finite_number(stage_units_in_meters, positive=True)
    if (
        frozen_source is None
        or expected_orientation is None
        or canonical_open > requested_open + 1.0e-12
    ):
        raise ValueError("trajectory_preflight_trace_authority_invalid")
    if type(substeps_per_action) is not int or substeps_per_action <= 0:
        raise ValueError("trajectory_preflight_substeps_invalid")
    expected_insert_controls_float = insert_distance / step_limit
    expected_insert_controls = int(round(expected_insert_controls_float))
    if not math.isclose(
        expected_insert_controls_float,
        expected_insert_controls,
        rel_tol=0.0,
        abs_tol=1.0e-9,
    ):
        raise ValueError("trajectory_preflight_insert_progression_invalid")
    control_dt = dt * substeps_per_action
    expected_settle_controls = int(
        math.ceil(settle_duration / control_dt - 1.0e-12)
    )
    nonempty = isinstance(trace, Sequence) and bool(trace)
    records = list(trace) if nonempty else []
    mappings = bool(nonempty and all(isinstance(record, Mapping) for record in records))

    indices = [record.get("trace_index") for record in records] if mappings else []
    timestamps = [record.get("timestamp_s") for record in records] if mappings else []
    physics_steps = [record.get("physics_step") for record in records] if mappings else []
    contiguous_indices = bool(
        mappings
        and all(type(value) is int for value in indices)
        and indices == list(range(len(records)))
    )
    integer_step_timestamps = bool(
        mappings
        and all(_optional_nonnegative(value) is not None for value in timestamps)
        and physics_steps
        and all(type(value) is int and value >= 0 for value in physics_steps)
        and all(
            math.isclose(
                float(timestamp),
                (int(physics_step) - int(physics_steps[0])) * dt,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            for timestamp, physics_step in zip(timestamps, physics_steps)
        )
    )
    contiguous_physics = bool(
        mappings
        and physics_steps
        and all(type(value) is int and value >= 0 for value in physics_steps)
        and physics_steps
        == list(range(physics_steps[0], physics_steps[0] + len(physics_steps)))
    )

    groups: dict[int, list[Mapping[str, Any]]] = {}
    group_indices_valid = mappings
    if mappings:
        for record in records:
            control_index = record.get("control_index")
            if type(control_index) is not int or control_index < 0:
                group_indices_valid = False
                break
            groups.setdefault(control_index, []).append(record)
    ordered_controls = sorted(groups)
    global_control_order = bool(
        mappings
        and all(
            record.get("control_index") == trace_index // substeps_per_action
            and record.get("substep_index") == trace_index % substeps_per_action
            for trace_index, record in enumerate(records)
        )
    )
    controller_indices_cross_bound = bool(
        mappings
        and all(
            type(record.get("controller_invocation_index")) is int
            and record["controller_invocation_index"]
            == record.get("control_index", -2) + 1
            for record in records
        )
    )
    exact_substeps = bool(
        group_indices_valid
        and ordered_controls == list(range(len(ordered_controls)))
        and all(len(groups[index]) == substeps_per_action for index in ordered_controls)
        and all(
            [record.get("substep_index") for record in groups[index]]
            == list(range(substeps_per_action))
            for index in ordered_controls
        )
    )

    action_hashes_valid = bool(groups)
    exact_action_channel_shape = bool(groups)
    kinds = []
    phases = []
    command_positions = []
    for index in ordered_controls:
        group = groups[index]
        first = group[0]
        kind = first.get("action_kind")
        phase = first.get("phase")
        kinds.append(kind)
        phases.append(phase)
        if not _pose_valid(first.get("commanded_tool_pose")):
            command_positions.append(None)
        else:
            command_positions.append(
                np.asarray(first["commanded_tool_pose"]["position_m"], dtype=np.float64)
            )
        try:
            expected_hash = canonical_action_hash(first.get("action_payload"))
        except (TypeError, ValueError):
            action_hashes_valid = False
            exact_action_channel_shape = False
            continue
        payload_shape_valid = _action_payload_matches_kind(
            first.get("action_payload"),
            kind,
            canonical_open_target_m=canonical_open,
        )
        if (
            not isinstance(kind, str)
            or not isinstance(phase, str)
            or any(record.get("action_kind") != kind for record in group)
            or any(record.get("phase") != phase for record in group)
            or any(record.get("action_payload") != first.get("action_payload") for record in group)
            or any(record.get("action_sha256") != expected_hash for record in group)
            or not payload_shape_valid
            or any(
                record.get("commanded_tool_pose") != first.get("commanded_tool_pose")
                for record in group
            )
        ):
            action_hashes_valid = False
        if not payload_shape_valid:
            exact_action_channel_shape = False

    sequence_valid = False
    if kinds:
        cursor = 0
        sequence_valid = True
        open_start = cursor
        while cursor < len(kinds) and kinds[cursor] == "GRIPPER_OPEN":
            if phases[cursor] != "PREGRASP":
                sequence_valid = False
            cursor += 1
        if cursor - open_start != 2:
            sequence_valid = False
        for expected_kind, expected_phase in (
            ("ARM_PREGRASP", "PREGRASP"),
            ("ARM_ALIGN", "ALIGN"),
            ("ARM_INSERT", "INSERT"),
            ("ARM_SETTLE", "SETTLE"),
        ):
            start = cursor
            while cursor < len(kinds) and kinds[cursor] == expected_kind:
                if phases[cursor] != expected_phase:
                    sequence_valid = False
                cursor += 1
            if cursor == start:
                sequence_valid = False
        sequence_valid = bool(sequence_valid and cursor == len(kinds))
        sequence_valid = bool(
            sequence_valid
            and Counter(kinds)
            == {
                "GRIPPER_OPEN": 2,
                "ARM_PREGRASP": 1,
                "ARM_ALIGN": 1,
                "ARM_INSERT": expected_insert_controls,
                "ARM_SETTLE": expected_settle_controls,
            }
        )

    insert_indices = [index for index, kind in enumerate(kinds) if kind == "ARM_INSERT"]
    settle_indices = [index for index, kind in enumerate(kinds) if kind == "ARM_SETTLE"]
    world_z_insert_only = bool(insert_indices)
    exact_insert_progression = bool(len(insert_indices) == expected_insert_controls)
    if insert_indices:
        previous_index = insert_indices[0] - 1
        previous = (
            command_positions[previous_index]
            if previous_index >= 0
            else command_positions[insert_indices[0]]
        )
        reference_xy = command_positions[insert_indices[0]]
        if previous is None or reference_xy is None:
            world_z_insert_only = False
        else:
            reference_xy = reference_xy[:2]
            for index in insert_indices:
                current = command_positions[index]
                if current is None:
                    world_z_insert_only = False
                    break
                delta_z = float(previous[2] - current[2])
                if (
                    not np.array_equal(current[:2], reference_xy)
                    or delta_z <= 0.0
                    or delta_z > step_limit + 1.0e-12
                ):
                    world_z_insert_only = False
                    break
                if not math.isclose(
                    delta_z, step_limit, rel_tol=0.0, abs_tol=1.0e-12
                ):
                    exact_insert_progression = False
                previous = current
            if exact_insert_progression:
                first_previous = command_positions[insert_indices[0] - 1]
                final = command_positions[insert_indices[-1]]
                exact_insert_progression = bool(
                    first_previous is not None
                    and final is not None
                    and math.isclose(
                        float(first_previous[2] - final[2]),
                        insert_distance,
                        rel_tol=0.0,
                        abs_tol=1.0e-10,
                    )
                )

    final_insert_position = (
        command_positions[insert_indices[-1]] if insert_indices else None
    )
    exact_settle_window = bool(
        final_insert_position is not None
        and len(settle_indices) == expected_settle_controls
        and all(
            command_positions[index] is not None
            and np.array_equal(command_positions[index], final_insert_position)
            for index in settle_indices
        )
    )

    pregrasp_expected = frozen_source - np.asarray(
        EXPECTED_APPROACH_DIRECTION_WORLD, dtype=np.float64
    ) * 0.120
    align_expected = frozen_source - np.asarray(
        EXPECTED_APPROACH_DIRECTION_WORLD, dtype=np.float64
    ) * 0.060
    insert_ordinals = {
        control_index: ordinal
        for ordinal, control_index in enumerate(insert_indices, start=1)
    }
    frozen_waypoints = bool(command_positions)
    for index, kind in enumerate(kinds):
        position = command_positions[index]
        expected_position = (
            pregrasp_expected
            if kind in {"GRIPPER_OPEN", "ARM_PREGRASP"}
            else align_expected
            if kind == "ARM_ALIGN"
            else align_expected
            + np.asarray(EXPECTED_APPROACH_DIRECTION_WORLD, dtype=np.float64)
            * step_limit
            * insert_ordinals[index]
            if kind == "ARM_INSERT"
            else None
        )
        if expected_position is not None and (
            position is None
            or not np.allclose(
                position, expected_position, rtol=0.0, atol=1.0e-12
            )
        ):
            frozen_waypoints = False
            break
        if kind == "ARM_SETTLE" and (
            position is None
            or not np.allclose(position, frozen_source, rtol=0.0, atol=1.0e-10)
        ):
            frozen_waypoints = False
            break
        if not all(
            _exact_vector(
                record.get("commanded_tool_pose", {}).get("orientation_wxyz"),
                expected_orientation,
            )
            for record in groups.get(index, [])
        ):
            frozen_waypoints = False
            break

    per_step_evidence = bool(records)
    stage_and_dof_units = bool(records)
    for record in records:
        if (
            not _pose_valid(record.get("commanded_tool_pose"))
            or not _pose_valid(record.get("measured_tool_pose"))
            or not _pose_valid(record.get("commanded_control_pose"))
            or not _pose_valid(record.get("measured_control_pose"))
            or not _pose_valid(record.get("rmpflow_control_pose"))
            or _finite_array(record.get("joint_positions_m"), (9,)) is None
            or _finite_array(record.get("joint_velocities_m_s"), (9,)) is None
            or not _collider_evidence_valid(record.get("collider_world_matrices"))
            or _finite_array(record.get("source_center_world_m"), (3,)) is None
            or _finite_array(record.get("source_world_matrix"), (4, 4)) is None
            or not isinstance(record.get("contacts"), Sequence)
            or not isinstance(record.get("geometry_world_matrices"), Mapping)
            or not isinstance(record.get("geometric_clearance_m"), Mapping)
            or not isinstance(record.get("environment_clearance_m"), Mapping)
            or any(
                not isinstance(contact, Mapping)
                or contact.get("physics_step") != record.get("physics_step")
                for contact in record.get("contacts", [])
            )
        ):
            per_step_evidence = False
            break
        if (
            record.get("stage_units_in_meters") != stage_units
            or record.get("joint_position_units") != ["rad"] * 7 + ["m", "m"]
            or record.get("joint_velocity_units")
            != ["rad_s"] * 7 + ["m_s", "m_s"]
        ):
            stage_and_dof_units = False

    first_arm_trace_index = min(
        (
            record.get("trace_index")
            for record in records
            if isinstance(record.get("action_kind"), str)
            and record["action_kind"].startswith("ARM_")
            and type(record.get("trace_index")) is int
        ),
        default=None,
    )
    open_confirmation_indices = []
    for record in records:
        if record.get("action_kind") != "GRIPPER_OPEN":
            continue
        joints = _finite_array(record.get("joint_positions_m"), (9,))
        if (
            joints is not None
            and np.all(
                np.abs(joints[[7, 8]] - canonical_open)
                <= open_tolerance + 1.0e-12
            )
            and type(record.get("trace_index")) is int
            and record["trace_index"] > 0
        ):
            open_confirmation_indices.append(record["trace_index"])
    full_open_ordered = bool(
        first_arm_trace_index is not None
        and open_confirmation_indices
        and min(open_confirmation_indices) < first_arm_trace_index
        and kinds.count("GRIPPER_OPEN") >= 2
    )
    checks = {
        "nonempty": nonempty,
        "contiguous_trace_indices": contiguous_indices,
        "integer_step_timestamps": integer_step_timestamps,
        "contiguous_physics_steps": contiguous_physics,
        "exact_substeps_per_action": exact_substeps,
        "action_hashes_valid": action_hashes_valid,
        "exact_action_channel_shape": exact_action_channel_shape,
        "action_kind_sequence_valid": sequence_valid,
        "global_control_order_valid": global_control_order,
        "controller_indices_cross_bound": controller_indices_cross_bound,
        "world_z_insert_only": world_z_insert_only,
        "exact_insert_progression": exact_insert_progression,
        "exact_settle_window": exact_settle_window,
        "frozen_waypoint_commands": frozen_waypoints,
        "stage_and_dof_units": stage_and_dof_units,
        "per_step_pose_and_collider_evidence": per_step_evidence,
        "full_open_after_command_before_arm": full_open_ordered,
    }
    return {
        "checks": checks,
        "action_count": len(ordered_controls),
        "physics_step_count": len(records),
        "action_kind_sequence": kinds,
        "action_kind_counts": dict(Counter(kinds)),
        "open_confirmation_trace_index": (
            min(open_confirmation_indices) if open_confirmation_indices else None
        ),
        "first_arm_trace_index": first_arm_trace_index,
        "passed": all(checks.values()),
    }


def evaluate_prohibited_activity(
    *,
    trace: Sequence[Mapping[str, Any]],
    source_writer_audit: Mapping[str, Any],
    attachment_events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    forbidden_kinds = {
        "close": {"CLOSE", "NEAR_SOURCE_CLOSE", "CONTACT_SETTLE"},
        "lift": {"LIFT"},
        "hold": {"HOLD"},
        "pour": {"POUR", "POURING"},
    }
    unique_actions = {
        (record.get("control_index"), record.get("action_kind"))
        for record in trace
        if isinstance(record, Mapping)
    }
    counts = {
        name: sum(kind in kinds for _, kind in unique_actions)
        for name, kinds in forbidden_kinds.items()
    }
    near_source_contacts = 0
    unexpected_robot_contacts = 0
    for record in trace:
        if not isinstance(record, Mapping):
            continue
        for contact in record.get("contacts", []):
            unexpected_robot_contacts += 1
            if not isinstance(contact, Mapping):
                near_source_contacts += 1
                continue
            paths = [
                str(contact.get(name, ""))
                for name in (
                    "body0_path",
                    "body1_path",
                    "collider0_path",
                    "collider1_path",
                )
            ]
            if contact.get("near_source") is True or any(
                path == "/World/beaker2" or path.startswith("/World/beaker2/")
                for path in paths
            ):
                near_source_contacts += 1
    calls = (
        source_writer_audit.get("calls", [])
        if isinstance(source_writer_audit, Mapping)
        else []
    )
    source_calls = 0
    kinematic_calls = 0
    if isinstance(calls, Sequence):
        for call in calls:
            surface = call.get("surface") if isinstance(call, Mapping) else None
            if surface == "physics_view.set_kinematic_targets":
                kinematic_calls += 1
            else:
                source_calls += 1
    else:
        source_calls = 1
    explicit_source = (
        source_writer_audit.get("source_pose_write_count_after_play")
        if isinstance(source_writer_audit, Mapping)
        else None
    )
    explicit_kinematic = (
        source_writer_audit.get("kinematic_target_update_count")
        if isinstance(source_writer_audit, Mapping)
        else None
    )
    audit_consistent = bool(
        type(explicit_source) is int
        and type(explicit_kinematic) is int
        and explicit_source == source_calls
        and explicit_kinematic == kinematic_calls
        and source_writer_audit.get("coverage_complete") is True
    )
    counts.update(
        {
            "near_source_contact": near_source_contacts,
            "attachment": len(attachment_events)
            if isinstance(attachment_events, Sequence)
            else 1,
            "source_write": source_calls,
            "kinematic_target": kinematic_calls,
        }
    )
    ordered_counts = {
        "near_source_contact": counts["near_source_contact"],
        "unexpected_robot_contact": unexpected_robot_contacts,
        "close": counts["close"],
        "lift": counts["lift"],
        "hold": counts["hold"],
        "pour": counts["pour"],
        "attachment": counts["attachment"],
        "source_write": counts["source_write"],
        "kinematic_target": counts["kinematic_target"],
    }
    return {
        "counts": ordered_counts,
        "source_writer_audit_consistent": audit_consistent,
        "passed": bool(audit_consistent and all(value == 0 for value in ordered_counts.values())),
    }


def _quaternion_error_degrees(first: Any, second: Any) -> float | None:
    first_q = _finite_array(first, (4,))
    second_q = _finite_array(second, (4,))
    if first_q is None or second_q is None:
        return None
    first_norm = float(np.linalg.norm(first_q))
    second_norm = float(np.linalg.norm(second_q))
    if first_norm <= 1.0e-12 or second_norm <= 1.0e-12:
        return None
    dot = float(abs(np.dot(first_q / first_norm, second_q / second_norm)))
    return math.degrees(2.0 * math.acos(float(np.clip(dot, -1.0, 1.0))))


def _exact_vector(value: Any, expected: Sequence[float]) -> bool:
    actual = _finite_array(value, (len(expected),))
    return bool(actual is not None and np.array_equal(actual, np.asarray(expected)))


def normalize_current_contacts(
    frames: Mapping[str, Mapping[str, Any]],
    *,
    physics_step: int,
    resolve_body_path: Any,
) -> list[dict[str, Any]]:
    from utils.isaac_fluid_evaluation import normalize_contact_sensor_frames

    return normalize_contact_sensor_frames(
        frames,
        expected_physics_step=physics_step,
        resolve_body_path=resolve_body_path,
        expected_sensor_names=("left", "right", "hand"),
    )


def _contact_attribution_valid(calibration: Mapping[str, Any]) -> bool:
    contacts = calibration.get("first_contacts")
    collider_paths = calibration.get("finger_collider_paths")
    brackets = calibration.get("contact_onset_brackets")
    if (
        not isinstance(contacts, Mapping)
        or set(contacts) != set(SIDES)
        or not isinstance(collider_paths, Mapping)
        or set(collider_paths) != set(SIDES)
        or not isinstance(brackets, Mapping)
        or set(brackets) != set(SIDES)
    ):
        return False
    steps = []
    for side in SIDES:
        record = contacts.get(side)
        expected_colliders = collider_paths.get(side)
        bracket = brackets.get(side)
        first_bracket = (
            bracket.get("first_contact") if isinstance(bracket, Mapping) else None
        )
        if (
            not isinstance(record, Mapping)
            or not isinstance(expected_colliders, Sequence)
            or isinstance(expected_colliders, (str, bytes))
            or not expected_colliders
            or record.get("finger_body_path") != EXPECTED_FINGER_BODY_PATHS[side]
            or record.get("finger_collider_path") not in expected_colliders
            or record.get("calibration_collider_path") != CALIBRATION_BODY_PATH
            or record.get("sensor_names") != [side]
            or record.get("resolved_contact_count") != 1
            or type(record.get("physics_step")) is not int
            or record["physics_step"] < 0
            or not isinstance(first_bracket, Mapping)
            or first_bracket.get("physics_step") != record["physics_step"]
        ):
            return False
        steps.append(record["physics_step"])
    return len(steps) == 2


def evaluate_runtime_measurements(report: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        raise TypeError("trajectory_preflight_runtime_mapping_required")
    measurement_abort = report.get("measurement_abort")
    if measurement_abort is not None:
        if not isinstance(measurement_abort, Mapping):
            raise ValueError("trajectory_preflight_measurement_abort_invalid")
        payload = {
            key: value
            for key, value in measurement_abort.items()
            if key != "evidence_sha256"
        }
        evidence = measurement_abort.get("evidence")
        reason = measurement_abort.get("reason")
        calibration_abort_valid = bool(
            reason
            in {
                "pre_enable_calibration_clearance_budget_failed",
                "post_enable_calibration_clearance_budget_failed",
            }
            and isinstance(evidence, Mapping)
            and evidence.get("passed") is False
            and evidence.get("first_enabled_physics_step") is None
        )
        source_isolation_abort_valid = False
        if isinstance(evidence, Mapping):
            checkpoint = evidence.get("checkpoint")
            allowed_checkpoints = {
                *SOURCE_ISOLATION_CHECKPOINTS,
                "pre_calibration_enable",
            }
            if (
                checkpoint in allowed_checkpoints
                and reason
                == f"trajectory_preflight_source_isolation_failed:{checkpoint}"
            ):
                try:
                    recomputed_isolation = evaluate_source_isolation_snapshot(
                        checkpoint=evidence.get("checkpoint"),
                        source_body_path=evidence.get("source_body_path"),
                        source_kinematic_enabled=evidence.get(
                            "source_kinematic_enabled"
                        ),
                        filtered_pair_targets=evidence.get(
                            "filtered_pair_targets", []
                        ),
                        expected_robot_rigid_body_paths=evidence.get(
                            "expected_robot_rigid_body_paths", []
                        ),
                        contact_report_api_applied=evidence.get(
                            "contact_report_api_applied"
                        ),
                        contact_report_threshold=evidence.get(
                            "contact_report_threshold"
                        ),
                        source_world_matrix=evidence.get("source_world_matrix", []),
                        expected_source_world_matrix=evidence.get(
                            "expected_source_world_matrix", []
                        ),
                    )
                    source_isolation_abort_valid = bool(
                        dict(evidence) == recomputed_isolation
                        and recomputed_isolation.get("passed") is False
                    )
                except (TypeError, ValueError):
                    source_isolation_abort_valid = False
        if (
            set(measurement_abort)
            != {
                "authority",
                "reason",
                "interaction_prevented",
                "collision_enabled_physics_step_count",
                "evidence",
                "evidence_sha256",
            }
            or measurement_abort.get("authority")
            != "preinteraction_measurement_abort_v1"
            or not (calibration_abort_valid or source_isolation_abort_valid)
            or measurement_abort.get("interaction_prevented") is not True
            or measurement_abort.get("collision_enabled_physics_step_count") != 0
            or measurement_abort.get("evidence_sha256")
            != canonical_json_sha256(payload)
        ):
            raise ValueError("trajectory_preflight_measurement_abort_invalid")
        return {
            "decision": NO_GO_DECISION,
            "checks": {
                "interaction_prevented": True,
                "measurement_completed": False,
            },
            "failed_checks": ["measurement_completed"],
            "derived": {"measurement_abort": dict(measurement_abort)},
        }
    runtime = report.get("runtime_contract")
    calibration = report.get("calibration")
    shadow = report.get("shadow_sweep")
    if not all(isinstance(value, Mapping) for value in (runtime, calibration, shadow)):
        raise ValueError("trajectory_preflight_runtime_measurements_invalid")

    trajectory = runtime.get("trajectory_inputs")
    runtime_contract = bool(
        runtime.get("producer_schema")
        == "geometry_aware_trajectory_preflight_runtime_v2"
        and runtime.get("profile") == PROFILE
        and math.isclose(
            _optional_nonnegative(runtime.get("physics_dt")) or -1.0,
            1.0 / 600.0,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        and math.isclose(
            _optional_nonnegative(runtime.get("control_dt")) or -1.0,
            1.0 / 30.0,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        and runtime.get("physics_substeps_per_action") == 20
        and runtime.get("pre_roll_steps") == 600
        and runtime.get("particle_count") == 0
        and runtime.get("stage_units_in_meters") == 1.0
        and runtime.get("joint_position_units")
        == ["rad"] * 7 + ["m", "m"]
        and runtime.get("joint_velocity_units")
        == ["rad_s"] * 7 + ["m_s", "m_s"]
        and runtime.get("rmpflow_runtime_data") == PINNED_RUNTIME_DATA_SHA256
    )
    session_text = runtime.get("diagnostic_session_layer_text")
    session_mutations = runtime.get("diagnostic_session_mutations")
    operations = (
        {record.get("operation") for record in session_mutations}
        if isinstance(session_mutations, Sequence)
        and all(isinstance(record, Mapping) for record in session_mutations)
        else set()
    )
    mutation_by_operation = (
        {record["operation"]: record for record in session_mutations}
        if len(operations) == len(session_mutations or [])
        else {}
    )
    particle_mutation = mutation_by_operation.get("set_active", {})
    kinematic_mutation = mutation_by_operation.get("set_kinematic_enabled", {})
    filter_mutation = mutation_by_operation.get("filter_collision_pairs", {})
    report_mutation = mutation_by_operation.get("disable_contact_reporting", {})
    body_mutation = mutation_by_operation.get("define_static_calibration_body", {})
    diagnostic_session = bool(
        runtime.get("particles_disabled") is True
        and runtime.get("source_robot_collision_filtered") is True
        and runtime.get("source_contact_reporting_disabled") is True
        and runtime.get("source_pose_fixed") is True
        and isinstance(session_text, str)
        and bool(session_text)
        and isinstance(runtime.get("diagnostic_session_layer_sha256"), str)
        and len(runtime["diagnostic_session_layer_sha256"]) == 64
        and runtime["diagnostic_session_layer_sha256"]
        == hashlib.sha256(session_text.encode("utf-8")).hexdigest()
        and operations
        == {
            "set_active",
            "set_kinematic_enabled",
            "filter_collision_pairs",
            "disable_contact_reporting",
            "define_static_calibration_body",
        }
        and particle_mutation.get("path")
        == "/World/InternDataParityFluid/Particles"
        and particle_mutation.get("value") is False
        and kinematic_mutation.get("path") == "/World/beaker2"
        and kinematic_mutation.get("value") is True
        and filter_mutation.get("path") == "/World/beaker2"
        and isinstance(filter_mutation.get("targets"), Sequence)
        and bool(filter_mutation["targets"])
        and all(
            isinstance(path, str) and path.startswith("/World/Franka")
            for path in filter_mutation["targets"]
        )
        and report_mutation.get("path") == "/World/beaker2"
        and isinstance(body_mutation.get("spec_sha256"), str)
        and len(body_mutation["spec_sha256"]) == 64
    )
    geometry_catalogs = shadow.get("geometry_catalogs")
    rigid_body_paths = runtime.get("robot_rigid_body_paths")
    colliderless_robot_bodies = runtime.get("colliderless_robot_bodies")
    all_robot_rigid_body_paths = runtime.get("all_robot_rigid_body_paths")
    collider_inventory = runtime.get("robot_collider_inventory")
    expected_colliderless_robot_bodies = {
        path: _colliderless_rigid_body_evidence_record(path)
        for path in EXPECTED_COLLIDERLESS_ROBOT_BODY_PATHS
    }
    inventory_payload = {
        "robot_rigid_body_paths": rigid_body_paths,
        "colliderless_robot_bodies": colliderless_robot_bodies,
        "all_robot_rigid_body_paths": all_robot_rigid_body_paths,
        "robot_collider_inventory": collider_inventory,
    }
    environment_inventory = bool(
        isinstance(geometry_catalogs, Mapping)
        and isinstance(rigid_body_paths, Sequence)
        and not isinstance(rigid_body_paths, (str, bytes))
        and all(isinstance(path, str) for path in rigid_body_paths)
        and list(rigid_body_paths) == sorted(rigid_body_paths)
        and len(set(rigid_body_paths)) == len(rigid_body_paths)
        and isinstance(colliderless_robot_bodies, Mapping)
        and dict(colliderless_robot_bodies) == expected_colliderless_robot_bodies
        and isinstance(all_robot_rigid_body_paths, Sequence)
        and not isinstance(all_robot_rigid_body_paths, (str, bytes))
        and all(isinstance(path, str) for path in all_robot_rigid_body_paths)
        and list(all_robot_rigid_body_paths) == sorted(all_robot_rigid_body_paths)
        and len(set(all_robot_rigid_body_paths)) == len(all_robot_rigid_body_paths)
        and list(all_robot_rigid_body_paths)
        == sorted([*rigid_body_paths, *colliderless_robot_bodies])
        and isinstance(collider_inventory, Mapping)
        and geometry_catalogs.get("robot_rigid_body_paths") == rigid_body_paths
        and geometry_catalogs.get("colliderless_robot_bodies")
        == colliderless_robot_bodies
        and geometry_catalogs.get("all_robot_rigid_body_paths")
        == all_robot_rigid_body_paths
        and geometry_catalogs.get("robot_collider_inventory")
        == collider_inventory
        and geometry_catalogs.get("inventory_sha256")
        == runtime.get("robot_inventory_sha256")
        == canonical_json_sha256(inventory_payload)
        and filter_mutation.get("targets") == all_robot_rigid_body_paths
    )
    derived_source_contact_offset = None
    source_catalog = None
    try:
        source_catalog = validate_cooked_catalog(geometry_catalogs["source"])
        source_offsets = [
            _optional_nonnegative(
                collider["contact_offset"].get("contact_offset_m")
            )
            for collider in source_catalog["colliders"]
        ]
        if all(value is not None for value in source_offsets):
            derived_source_contact_offset = max(
                float(value) for value in source_offsets
            )
        expected_finger_inventory = {
            side: collider_inventory[EXPECTED_FINGER_BODY_PATHS[side]]
            for side in SIDES
        }
    except (KeyError, TypeError, ValueError):
        expected_finger_inventory = None
    reported_source_contact_offset = _optional_nonnegative(
        shadow.get("source_contact_offset_m")
    )
    environment_inventory = bool(
        environment_inventory
        and expected_finger_inventory is not None
        and calibration.get("finger_collider_paths")
        == expected_finger_inventory
        and derived_source_contact_offset is not None
        and reported_source_contact_offset is not None
        and math.isclose(
            reported_source_contact_offset,
            derived_source_contact_offset,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
    )
    snapshots = runtime.get("source_isolation_snapshots")
    source_isolation = bool(
        isinstance(snapshots, Sequence)
        and not isinstance(snapshots, (str, bytes))
        and len(snapshots) == len(SOURCE_ISOLATION_CHECKPOINTS)
    )
    if source_isolation:
        for checkpoint, snapshot in zip(SOURCE_ISOLATION_CHECKPOINTS, snapshots):
            if not isinstance(snapshot, Mapping):
                source_isolation = False
                break
            recomputed_snapshot = evaluate_source_isolation_snapshot(
                checkpoint=snapshot.get("checkpoint"),
                source_body_path=snapshot.get("source_body_path"),
                source_kinematic_enabled=snapshot.get(
                    "source_kinematic_enabled"
                ),
                filtered_pair_targets=snapshot.get("filtered_pair_targets", []),
                expected_robot_rigid_body_paths=snapshot.get(
                    "expected_robot_rigid_body_paths", []
                ),
                contact_report_api_applied=snapshot.get(
                    "contact_report_api_applied"
                ),
                contact_report_threshold=snapshot.get(
                    "contact_report_threshold"
                ),
                source_world_matrix=snapshot.get("source_world_matrix", []),
                expected_source_world_matrix=snapshot.get(
                    "expected_source_world_matrix", []
                ),
            )
            if (
                dict(snapshot) != recomputed_snapshot
                or snapshot.get("checkpoint") != checkpoint
                or snapshot.get("source_body_path") != "/World/beaker2"
                or snapshot.get("expected_robot_rigid_body_paths")
                != all_robot_rigid_body_paths
                or snapshot.get("filtered_pair_targets")
                != all_robot_rigid_body_paths
                or snapshot.get("passed") is not True
            ):
                source_isolation = False
                break
    pre_stage_inventory = runtime.get("pre_measurement_stage_inventory")
    post_stage_inventory = runtime.get("post_measurement_stage_inventory")
    attachment_inventory = evaluate_attachment_inventory(
        pre_inventory=pre_stage_inventory,
        post_inventory=post_stage_inventory,
        source_body_path="/World/beaker2",
        robot_rigid_body_paths=(
            all_robot_rigid_body_paths
            if isinstance(all_robot_rigid_body_paths, Sequence)
            else []
        ),
    )
    stage_inventory_unchanged = bool(
        attachment_inventory["checks"]["pre_inventory_valid"]
        and attachment_inventory["checks"]["post_inventory_valid"]
        and attachment_inventory["checks"]["inventories_unchanged"]
    )
    source_robot_attachment_absent = bool(
        attachment_inventory["checks"]["source_robot_attachment_absent"]
    )

    reset_record = runtime.get("authoritative_reset_record")
    after_reset = _finite_array(runtime.get("reset_joint_positions_after"), (9,))
    reset_positions = (
        _finite_array(reset_record.get("joint_positions"), (9,))
        if isinstance(reset_record, Mapping)
        else None
    )
    reset_payload = (
        {key: value for key, value in reset_record.items() if key != "record_sha256"}
        if isinstance(reset_record, Mapping)
        else {}
    )
    authoritative_reset = bool(
        isinstance(reset_record, Mapping)
        and set(reset_record)
        == {"authority", "joint_positions", "joint_position_units", "record_sha256"}
        and reset_record.get("authority")
        == "post_task_reset_pre_session_mutation_v1"
        and reset_record.get("joint_position_units")
        == ["rad"] * 7 + ["m", "m"]
        and reset_record.get("record_sha256")
        == canonical_json_sha256(reset_payload)
        and reset_positions is not None
        and after_reset is not None
        and np.array_equal(reset_positions, after_reset)
    )

    try:
        open_authority = derive_measured_open_contract(
            points=calibration.get("aperture_points", []),
            velocity_samples=calibration.get("velocity_samples", []),
            requested_open_target_m=(trajectory or {}).get(
                "requested_open_target_m"
            ),
            physics_dt=1.0 / 600.0,
        )
    except (TypeError, ValueError):
        open_authority = {"passed": False}
    exact_inputs = bool(
        isinstance(trajectory, Mapping)
        and _exact_vector(
            trajectory.get("tool_orientation_wxyz"), EXPECTED_TOOL_ORIENTATION_WXYZ
        )
        and _exact_vector(
            trajectory.get("grasp_offset_object_m"), EXPECTED_GRASP_OFFSET_OBJECT_M
        )
        and _exact_vector(
            trajectory.get("approach_direction_world"),
            EXPECTED_APPROACH_DIRECTION_WORLD,
        )
        and np.array_equal(
            _finite_array(trajectory.get("control_to_tool_center_matrix_m"), (4, 4)),
            np.asarray(EXPECTED_CONTROL_TO_TOOL_MATRIX_M),
        )
        and trajectory.get("pregrasp_distance_m") == 0.120
        and trajectory.get("insert_distance_m") == 0.060
        and trajectory.get("insertion_speed_m_s") == 0.006
        and trajectory.get("remote_close_speed_m_s") == 0.003
        and trajectory.get("settle_duration_s") == 0.10
        and trajectory.get("contact_settle_duration_s") == 0.10
        and trajectory.get("numerical_margin_m") == 0.001
        and trajectory.get("requested_open_target_m") == 0.040
        and math.isclose(
            _optional_nonnegative(trajectory.get("canonical_open_target_m"))
            or -1.0,
            float(open_authority.get("canonical_open_target_m", -2.0)),
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        and np.array_equal(
            _finite_array(trajectory.get("physical_open_upper_limits_m"), (2,)),
            _finite_array(open_authority.get("measured_upper_limits_m"), (2,)),
        )
        and math.isclose(
            _optional_nonnegative(trajectory.get("open_position_tolerance_m"))
            or -1.0,
            float(open_authority.get("open_position_tolerance_m", -2.0)),
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        and trajectory.get("position_threshold_m") == 0.0005
        and trajectory.get("orientation_threshold_degrees") == 0.5
        and open_authority.get("passed") is True
    )

    body_spec = calibration.get("body_spec")
    expected_body_spec = None
    if isinstance(body_spec, Mapping):
        try:
            expected_body_spec = calibration_body_spec(
                reset_tool_world_matrix=body_spec.get("reset_tool_world_matrix"),
                translation_tool_m=EXPECTED_CALIBRATION_BODY_TRANSLATION_TOOL_M,
                opening_axis_world=body_spec.get("opening_axis_world"),
                size_m=EXPECTED_CALIBRATION_BODY_SIZE_M,
                contact_offset_m=0.0001,
            )
        except (TypeError, ValueError):
            expected_body_spec = None
    calibration_body = bool(
        isinstance(body_spec, Mapping)
        and expected_body_spec is not None
        and dict(body_spec) == expected_body_spec
        and calibration.get("body_spec_sha256") == canonical_json_sha256(body_spec)
        and body_mutation.get("spec_sha256")
        == calibration.get("body_spec_sha256")
    )
    remote = calibration.get("remote_clearance_m")
    remote_clearance = bool(
        isinstance(remote, Mapping)
        and set(remote)
        == {
            "calibration_body_to_source",
            "calibration_body_to_table",
            "calibration_body_to_unrelated_robot_links",
        }
        and all(
            _optional_nonnegative(value) is not None and float(value) > 0.0
            for value in remote.values()
        )
        and calibration.get("remote_unexpected_contacts") == []
    )
    attribution = bool(
        calibration.get("contact_attribution_ambiguous") is False
        and _contact_attribution_valid(calibration)
    )
    expected_calibration_obstacle_paths: list[str] = []
    expected_calibration_offsets: dict[str, float | None] = {}
    finger_catalogs: dict[str, Any] = {}
    try:
        table_catalog = validate_static_cooked_catalog(
            geometry_catalogs["table"], expected_body_path=EXPECTED_TABLE_BODY_PATH
        )
        robot_catalogs = {
            path: validate_cooked_catalog(catalog)
            for path, catalog in geometry_catalogs["robot_bodies"].items()
        }
        finger_catalogs = {
            side: robot_catalogs[EXPECTED_FINGER_BODY_PATHS[side]]
            for side in SIDES
        }

        def maximum_catalog_offset(catalog: Mapping[str, Any]) -> float | None:
            values = [
                _optional_nonnegative(
                    collider["contact_offset"].get("contact_offset_m")
                    if collider["contact_offset"].get("authority")
                    != "unresolved"
                    else None
                )
                for collider in catalog["colliders"]
            ]
            return (
                max(float(value) for value in values)
                if values and all(value is not None for value in values)
                else None
            )

        unrelated_paths = sorted(
            set(robot_catalogs)
            - {
                *EXPECTED_FINGER_BODY_PATHS.values(),
                "/World/Franka/panda_hand",
            }
        )
        expected_calibration_obstacle_paths = sorted(
            [
                str(source_catalog["body_path"]),
                str(table_catalog["body_path"]),
                "/World/Franka/panda_hand",
                *unrelated_paths,
            ]
        )
        expected_calibration_offsets = {
            str(source_catalog["body_path"]): maximum_catalog_offset(
                source_catalog
            ),
            str(table_catalog["body_path"]): maximum_catalog_offset(
                table_catalog
            ),
            "/World/Franka/panda_hand": maximum_catalog_offset(
                robot_catalogs["/World/Franka/panda_hand"]
            ),
            **{
                path: maximum_catalog_offset(robot_catalogs[path])
                for path in unrelated_paths
            },
        }
    except (KeyError, TypeError, ValueError):
        expected_calibration_obstacle_paths = []
        expected_calibration_offsets = {}
        finger_catalogs = {}
    pre_enable_budget = calibration.get("pre_enable_clearance_budget")
    calibration_clearance = validate_remote_calibration_clearance_budget(
        pre_enable_budget,
        expected_obstacle_paths=expected_calibration_obstacle_paths,
        expected_obstacle_offsets_m=expected_calibration_offsets,
    )
    collision_evidence = calibration.get("collision_interlock")
    collision_open_state = (
        collision_evidence.get("physical_open_state")
        if isinstance(collision_evidence, Mapping)
        else None
    )
    collision_interlock = bool(
        validate_collision_interlock_evidence(collision_evidence)
        and collision_evidence.get("pre_enable_clearance_budget")
        == pre_enable_budget
        and collision_evidence.get("post_enable_clearance_budget")
        == pre_enable_budget
        and isinstance(collision_open_state, Mapping)
        and np.array_equal(
            _finite_array(collision_open_state.get("upper_limits_m"), (2,)),
            _finite_array((trajectory or {}).get("physical_open_upper_limits_m"), (2,)),
        )
        and collision_open_state.get("position_tolerance_m")
        == (trajectory or {}).get("open_position_tolerance_m")
    )
    width = body_spec.get("width_m") if isinstance(body_spec, Mapping) else None
    body_offset = (
        body_spec.get("contact_offset_m") if isinstance(body_spec, Mapping) else None
    )
    try:
        offset_bounds = derive_effective_contact_offset_bounds(
            calibration_body_width_m=width,
            calibration_body_contact_offset_m=body_offset,
            contact_onset_brackets=calibration.get("contact_onset_brackets", {}),
            finger_collider_catalogs=finger_catalogs,
        )
    except (TypeError, ValueError):
        offset_bounds = {
            "bounds_m": {"left": None, "right": None},
            "passed": False,
        }
    try:
        aperture = evaluate_aperture_calibration(
            points=calibration.get("aperture_points", []),
            velocity_samples=calibration.get("velocity_samples", []),
            expected_targets_m=EXPECTED_CALIBRATION_TARGETS_M,
            requested_open_target_m=0.040,
            required_settle_duration_s=0.10,
            maximum_asymmetry_m=0.0005,
            velocity_agreement_tolerance_m_s=0.002,
            physics_dt=1.0 / 600.0,
        )
    except (TypeError, ValueError):
        aperture = {"passed": False, "checks": {}}
    measured_open_tolerance = _optional_nonnegative(
        (trajectory or {}).get("open_position_tolerance_m")
    )

    trace = shadow.get("trace", [])
    try:
        trace_validation = validate_shadow_trace(
            trace,
            physics_dt=1.0 / 600.0,
            substeps_per_action=20,
            insertion_step_m=0.0002,
            insert_distance_m=0.060,
            settle_duration_s=0.10,
            frozen_source_position_m=(shadow.get("controller_evidence") or {}).get(
                "latched_source_position", []
            ),
            expected_tool_orientation_wxyz=EXPECTED_TOOL_ORIENTATION_WXYZ,
            requested_open_target_m=(trajectory or {}).get(
                "requested_open_target_m"
            ),
            canonical_open_target_m=(trajectory or {}).get(
                "canonical_open_target_m"
            ),
            open_position_tolerance_m=(trajectory or {}).get(
                "open_position_tolerance_m"
            ),
            stage_units_in_meters=runtime.get("stage_units_in_meters"),
        )
    except (TypeError, ValueError):
        trace_validation = {"passed": False, "action_kind_counts": {}}

    controller = shadow.get("controller_evidence")
    source_center = None
    frozen_trajectory = False
    if isinstance(controller, Mapping) and isinstance(trace, Sequence) and trace:
        source_center = _finite_array(controller.get("latched_source_position"), (3,))
        grasp = _finite_array(controller.get("grasp_position"), (3,))
        pregrasp = _finite_array(controller.get("pregrasp_position"), (3,))
        align = _finite_array(controller.get("align_position"), (3,))
        expected_pregrasp = (
            None if source_center is None else source_center + [0.0, 0.0, 0.120]
        )
        expected_align = (
            None if source_center is None else source_center + [0.0, 0.0, 0.060]
        )
        insert_records = [
            record for record in trace if record.get("action_kind") == "ARM_INSERT"
        ]
        action_counts = trace_validation.get("action_kind_counts", {})
        traced_arm_action_count = sum(
            int(action_counts.get(name, 0))
            for name in ("ARM_PREGRASP", "ARM_ALIGN", "ARM_INSERT", "ARM_SETTLE")
        )
        traced_finger_action_count = int(action_counts.get("GRIPPER_OPEN", 0))
        final_insert = (
            _finite_array(
                insert_records[-1].get("commanded_tool_pose", {}).get("position_m"),
                (3,),
            )
            if insert_records
            else None
        )
        all_orientations_exact = all(
            _exact_vector(
                record.get("commanded_tool_pose", {}).get("orientation_wxyz"),
                EXPECTED_TOOL_ORIENTATION_WXYZ,
            )
            for record in trace
        )
        control_pose_commands_valid = True
        for record in trace:
            try:
                expected_control_pose = map_tool_target_to_control_pose(
                    tool_pose=record.get("commanded_tool_pose", {}),
                    control_to_tool_matrix_m=EXPECTED_CONTROL_TO_TOOL_MATRIX_M,
                )
            except (TypeError, ValueError):
                control_pose_commands_valid = False
                break
            actual_control_pose = record.get("commanded_control_pose", {})
            if (
                not _pose_valid(actual_control_pose)
                or not np.allclose(
                    actual_control_pose["position_m"],
                    expected_control_pose["position_m"],
                    rtol=0.0,
                    atol=1.0e-12,
                )
                or not np.allclose(
                    actual_control_pose["orientation_wxyz"],
                    expected_control_pose["orientation_wxyz"],
                    rtol=0.0,
                    atol=1.0e-12,
                )
            ):
                control_pose_commands_valid = False
                break
        first_source_matrix = trace[0].get("source_world_matrix")
        first_source_center = trace[0].get("source_center_world_m")
        first_source_center_array = _finite_array(first_source_center, (3,))
        source_fixed = bool(
            first_source_center_array is not None
            and all(
                record.get("source_world_matrix") == first_source_matrix
                and record.get("source_center_world_m") == first_source_center
                for record in trace
            )
        )
        frozen_trajectory = bool(
            exact_inputs
            and source_center is not None
            and grasp is not None
            and pregrasp is not None
            and align is not None
            and np.allclose(grasp, source_center, rtol=0.0, atol=1.0e-12)
            and np.allclose(pregrasp, expected_pregrasp, rtol=0.0, atol=1.0e-12)
            and np.allclose(align, expected_align, rtol=0.0, atol=1.0e-12)
            and len(insert_records) == 300 * 20
            and final_insert is not None
            and np.allclose(final_insert, source_center, rtol=0.0, atol=1.0e-10)
            and controller.get("phase") == "CLOSE"
            and controller.get("phase_history")
            == ["PREGRASP", "ALIGN", "INSERT", "SETTLE", "CLOSE"]
            and controller.get("close_command_emitted") is False
            and controller.get("close_action_control_index") is None
            and controller.get("probe_completed") is False
            and controller.get("lift_command_emitted") is False
            and controller.get("control_invocation_count")
            == trace_validation.get("action_count")
            and controller.get("arm_action_count") == traced_arm_action_count
            and controller.get("finger_action_count") == traced_finger_action_count
            and controller.get("noop_action_count") == 0
            and controller.get("last_emitted_phase") == "SETTLE"
            and controller.get("last_emitted_action_kind") == "arm"
            and _exact_vector(
                controller.get("latched_end_effector_orientation_wxyz"),
                EXPECTED_TOOL_ORIENTATION_WXYZ,
            )
            and _exact_vector(
                controller.get("approach_direction"),
                EXPECTED_APPROACH_DIRECTION_WORLD,
            )
            and _exact_vector(
                controller.get("grasp_offset"), EXPECTED_GRASP_OFFSET_OBJECT_M
            )
            and np.array_equal(
                _finite_array(
                    controller.get("control_to_end_effector_matrix_m"), (4, 4)
                ),
                np.asarray(EXPECTED_CONTROL_TO_TOOL_MATRIX_M),
            )
            and controller.get("approach_speed_m_s") == 0.006
            and controller.get("close_speed_m_s") == 0.003
            and controller.get("pregrasp_distance_m") == 0.120
            and controller.get("insert_distance_m") == 0.060
            and all_orientations_exact
            and control_pose_commands_valid
            and source_fixed
            and np.allclose(
                first_source_center_array,
                source_center,
                rtol=0.0,
                atol=1.0e-12,
            )
        )

    maximum_tracking = None
    maximum_position_error = None
    maximum_orientation = None
    maximum_longitudinal_lag = None
    maximum_longitudinal_overshoot = None
    maximum_control_position_error = None
    maximum_control_orientation_error = None
    tracked_record_count = 0
    if isinstance(trace, Sequence) and trace:
        tracking_values = []
        position_error_values = []
        orientation_values = []
        longitudinal_lag_values = []
        longitudinal_overshoot_values = []
        control_position_errors = []
        control_orientation_errors = []
        for record in trace:
            if record.get("action_kind") not in TRACKED_ACTION_KINDS:
                continue
            tracked_record_count += 1
            commanded = _finite_array(
                record.get("commanded_tool_pose", {}).get("position_m"), (3,)
            )
            measured = _finite_array(
                record.get("measured_tool_pose", {}).get("position_m"), (3,)
            )
            angle = _quaternion_error_degrees(
                record.get("commanded_tool_pose", {}).get("orientation_wxyz"),
                record.get("measured_tool_pose", {}).get("orientation_wxyz"),
            )
            commanded_control = _finite_array(
                record.get("commanded_control_pose", {}).get("position_m"), (3,)
            )
            measured_control = _finite_array(
                record.get("measured_control_pose", {}).get("position_m"), (3,)
            )
            control_angle = _quaternion_error_degrees(
                record.get("commanded_control_pose", {}).get("orientation_wxyz"),
                record.get("measured_control_pose", {}).get("orientation_wxyz"),
            )
            if commanded is not None and measured is not None:
                error = measured - commanded
                tracking_values.append(float(np.linalg.norm(error[:2])))
                position_error_values.append(float(np.linalg.norm(error)))
                signed_progress_error = float(
                    np.dot(error, np.asarray(EXPECTED_APPROACH_DIRECTION_WORLD))
                )
                longitudinal_lag_values.append(max(0.0, -signed_progress_error))
                longitudinal_overshoot_values.append(max(0.0, signed_progress_error))
            if angle is not None:
                orientation_values.append(angle)
            if commanded_control is not None and measured_control is not None:
                control_position_errors.append(
                    float(np.linalg.norm(measured_control - commanded_control))
                )
            if control_angle is not None:
                control_orientation_errors.append(control_angle)
        if tracked_record_count and len(tracking_values) == tracked_record_count:
            maximum_tracking = max(tracking_values)
            maximum_position_error = max(position_error_values)
        if tracked_record_count and len(orientation_values) == tracked_record_count:
            maximum_orientation = max(orientation_values)
        if tracked_record_count and len(longitudinal_lag_values) == tracked_record_count:
            maximum_longitudinal_lag = max(longitudinal_lag_values)
            maximum_longitudinal_overshoot = max(longitudinal_overshoot_values)
        if tracked_record_count and len(control_position_errors) == tracked_record_count:
            maximum_control_position_error = max(control_position_errors)
        if tracked_record_count and len(control_orientation_errors) == tracked_record_count:
            maximum_control_orientation_error = max(control_orientation_errors)

    trajectory_uncertainty = derive_trajectory_uncertainty(
        trace=trace if isinstance(trace, Sequence) else [],
        edge_radii_m=shadow.get(
            "finger_edge_radii_m", {"left": None, "right": None}
        ),
    )
    try:
        derived_shadow_axis = derive_opening_axis_from_orientation_wxyz(
            shadow.get("opening_axis_tool_orientation_wxyz", [])
        )
    except (TypeError, ValueError):
        derived_shadow_axis = None
    reported_shadow_axis = _finite_array(shadow.get("opening_axis_world"), (3,))
    shadow_opening_axis = bool(
        derived_shadow_axis is not None
        and reported_shadow_axis is not None
        and shadow.get("opening_axis_authority")
        == "literal_commanded_tool_orientation_v1"
        and _exact_vector(
            shadow.get("opening_axis_tool_orientation_wxyz"),
            EXPECTED_TOOL_ORIENTATION_WXYZ,
        )
        and np.allclose(
            reported_shadow_axis,
            derived_shadow_axis,
            rtol=0.0,
            atol=1.0e-12,
        )
    )
    parent_geometry = recompute_trace_geometry(
        trace=trace if isinstance(trace, Sequence) else [],
        geometry_catalogs=shadow.get("geometry_catalogs", {}),
        opening_axis_world=shadow.get("opening_axis_world", []),
        trajectory_uncertainty_m=trajectory_uncertainty.get(
            "per_side_m", {"left": None, "right": None}
        ),
        numerical_margin_m=(trajectory or {}).get("numerical_margin_m"),
    )
    geometric_minima = parent_geometry["geometric_clearance_minima_m"]

    edge_displacements = orientation_edge_displacement_bounds(
        edge_radii_m=shadow.get(
            "finger_edge_radii_m", {"left": None, "right": None}
        ),
        maximum_orientation_error_degrees=maximum_orientation,
    )
    clearance = evaluate_swept_clearance_budget(
        geometric_clearance_m=geometric_minima,
        source_contact_offset_m=derived_source_contact_offset,
        finger_contact_offset_bounds_m=offset_bounds.get(
            "bounds_m", {"left": None, "right": None}
        ),
        trajectory_uncertainty_m=trajectory_uncertainty.get(
            "per_side_m", {"left": None, "right": None}
        ),
        numerical_margin_m=(trajectory or {}).get("numerical_margin_m"),
        environment_pairwise_budget=parent_geometry.get(
            "environment_pairwise_budget", {}
        ),
    )
    prohibited = evaluate_prohibited_activity(
        trace=trace if isinstance(trace, Sequence) else [],
        source_writer_audit=shadow.get("source_writer_audit", {}),
        attachment_events=shadow.get("attachment_events", []),
    )
    controller_open_tolerance = _optional_nonnegative(
        controller.get("open_position_tolerance_m")
        if isinstance(controller, Mapping)
        else None
    )
    action_sequence = trace_validation.get("action_kind_sequence", [])
    open_index = (
        controller.get("open_confirmed_control_index")
        if isinstance(controller, Mapping)
        else None
    )
    first_arm_index = (
        controller.get("first_arm_command_control_index")
        if isinstance(controller, Mapping)
        else None
    )
    indices_cross_bound = bool(
        type(open_index) is int
        and type(first_arm_index) is int
        and 1 <= open_index <= len(action_sequence)
        and 1 <= first_arm_index <= len(action_sequence)
        and action_sequence[open_index - 1] == "GRIPPER_OPEN"
        and action_sequence[first_arm_index - 1].startswith("ARM_")
    )
    full_open_controller_lifecycle = bool(
        isinstance(controller, Mapping)
        and measured_open_tolerance is not None
        and controller_open_tolerance is not None
        and math.isclose(
            controller_open_tolerance,
            measured_open_tolerance,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        and controller.get("open_position_m")
        == open_authority.get("canonical_open_target_m")
        and controller.get("open_command_count")
        == trace_validation.get("action_kind_counts", {}).get("GRIPPER_OPEN")
        and controller.get("open_command_count") == 2
        and controller.get("open_position_ready") is True
        and indices_cross_bound
        and open_index < first_arm_index
        and controller.get("arm_before_open_violation") is False
        and controller.get("position_threshold_m")
        == (trajectory or {}).get("position_threshold_m")
        and controller.get("orientation_threshold_degrees")
        == (trajectory or {}).get("orientation_threshold_degrees")
    )
    stopped_before_close = bool(
        isinstance(controller, Mapping)
        and controller.get("phase") == "CLOSE"
        and controller.get("phase_history")
        == ["PREGRASP", "ALIGN", "INSERT", "SETTLE", "CLOSE"]
        and controller.get("close_command_emitted") is False
        and controller.get("close_action_control_index") is None
        and prohibited["counts"]["close"] == 0
        and trace_validation.get("checks", {}).get("exact_settle_window") is True
    )
    tracking_metrics_complete = bool(
        tracked_record_count == (300 + 3) * 20
        and maximum_tracking is not None
        and maximum_position_error is not None
        and maximum_orientation is not None
        and maximum_longitudinal_lag is not None
        and maximum_longitudinal_overshoot is not None
        and maximum_control_position_error is not None
        and maximum_control_orientation_error is not None
    )
    tracking_within_thresholds = bool(
        tracking_metrics_complete
        and maximum_position_error <= 0.0005 + 1.0e-12
        and maximum_orientation <= 0.5 + 1.0e-9
        and maximum_control_position_error <= 0.0005 + 1.0e-12
        and maximum_control_orientation_error <= 0.5 + 1.0e-9
    )
    parent_geometry_bound = bool(
        parent_geometry.get("parent_geometry_recomputed")
        and parent_geometry.get("reported_values_match")
    )
    checks = {
        "runtime_contract": runtime_contract,
        "diagnostic_session": diagnostic_session,
        "authoritative_reset": authoritative_reset,
        "source_isolation": source_isolation,
        "stage_inventory_unchanged": stage_inventory_unchanged,
        "source_robot_attachment_absent": source_robot_attachment_absent,
        "environment_inventory": environment_inventory,
        "calibration_body": calibration_body,
        "calibration_clearance": calibration_clearance,
        "calibration_collision_interlock": collision_interlock,
        "physical_open_authority": bool(open_authority.get("passed")),
        "remote_clearance": remote_clearance,
        "contact_attribution": attribution,
        "effective_contact_offsets": bool(offset_bounds.get("passed")),
        "aperture_calibration": bool(aperture.get("passed")),
        "full_open_controller_lifecycle": full_open_controller_lifecycle,
        "shadow_opening_axis": shadow_opening_axis,
        "shadow_trace": bool(trace_validation.get("passed")),
        "tracking_metrics_complete": tracking_metrics_complete,
        "tracking_within_configured_thresholds": tracking_within_thresholds,
        "frozen_trajectory": frozen_trajectory,
        "trajectory_uncertainty": bool(trajectory_uncertainty.get("passed")),
        "parent_geometry_recomputed": parent_geometry_bound,
        "swept_clearance": bool(
            parent_geometry_bound
            and parent_geometry.get("passed")
            and clearance.get("passed")
        ),
        "prohibited_activity": bool(prohibited.get("passed")),
        "stopped_before_close": stopped_before_close,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "decision": GO_DECISION if not failed else NO_GO_DECISION,
        "checks": checks,
        "failed_checks": failed,
        "derived": {
            "effective_contact_offsets": offset_bounds,
            "aperture_calibration": aperture,
            "physical_open_authority": open_authority,
            "source_isolation_snapshots": snapshots,
            "attachment_inventory": attachment_inventory,
            "calibration_clearance": pre_enable_budget,
            "measured_open_position_tolerance_m": measured_open_tolerance,
            "shadow_trace": trace_validation,
            "parent_geometry": parent_geometry,
            "trajectory_uncertainty": trajectory_uncertainty,
            "tracked_action_kinds": sorted(TRACKED_ACTION_KINDS),
            "tracked_record_count": tracked_record_count,
            "maximum_lateral_tracking_envelope_m": maximum_tracking,
            "maximum_position_error_m": maximum_position_error,
            "maximum_orientation_error_degrees": maximum_orientation,
            "maximum_longitudinal_lag_m": maximum_longitudinal_lag,
            "maximum_longitudinal_overshoot_m": maximum_longitudinal_overshoot,
            "maximum_control_position_error_m": maximum_control_position_error,
            "maximum_control_orientation_error_degrees": (
                maximum_control_orientation_error
            ),
            "orientation_edge_displacement_m": edge_displacements,
            "clearance_budget": clearance,
            "prohibited_activity": prohibited,
        },
    }


def validate_child_binding(
    owner: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    expected_child_pid: int,
    expected_run_id: str,
    expected_run_identity_sha256: str,
) -> dict[str, Any]:
    runtime_identity = report.get("runtime_identity")
    if (
        not isinstance(owner, Mapping)
        or set(owner) != {"pid", "run_id", "run_identity_sha256"}
        or type(expected_child_pid) is not int
        or expected_child_pid <= 0
        or not isinstance(expected_run_id, str)
        or not expected_run_id
        or not isinstance(expected_run_identity_sha256, str)
        or len(expected_run_identity_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_run_identity_sha256)
        or type(owner.get("pid")) is not int
        or owner.get("pid") != expected_child_pid
        or not isinstance(owner.get("run_id"), str)
        or owner.get("run_id") != expected_run_id
        or owner.get("run_identity_sha256") != expected_run_identity_sha256
        or not isinstance(runtime_identity, Mapping)
        or set(runtime_identity) != {"pid", "run_id", "run_identity_sha256"}
        or type(runtime_identity.get("pid")) is not int
        or runtime_identity.get("pid") != expected_child_pid
        or not isinstance(runtime_identity.get("run_id"), str)
        or runtime_identity.get("run_id") != expected_run_id
        or runtime_identity.get("run_identity_sha256")
        != expected_run_identity_sha256
        or Path(str(report.get("config_path"))).resolve() != DEFAULT_CONFIG.resolve()
        or report.get("config_sha256") != EXPECTED_CONFIG_SHA256
        or Path(str(report.get("asset_path"))).resolve() != ASSET_PATH.resolve()
        or report.get("asset_sha256") != EXPECTED_ASSET_SHA256
        or Path(str(report.get("robot_path"))).resolve() != ROBOT_PATH.resolve()
        or report.get("robot_sha256") != EXPECTED_ROBOT_SHA256
    ):
        raise ValueError("trajectory_preflight_child_identity_invalid")
    return {
        "pid": expected_child_pid,
        "run_id": expected_run_id,
        "run_identity_sha256": expected_run_identity_sha256,
        "valid": True,
    }


def validate_runtime_report_agreement(
    report: Mapping[str, Any], parent_evaluation: Mapping[str, Any]
) -> str:
    child_evaluation = report.get("child_evaluation")
    measurement_decision = report.get("measurement_decision")
    child_decision = (
        child_evaluation.get("decision")
        if isinstance(child_evaluation, Mapping)
        else None
    )
    parent_decision = (
        parent_evaluation.get("decision")
        if isinstance(parent_evaluation, Mapping)
        else None
    )
    if (
        report.get("lifecycle_status") != "measurement_complete_application_closed"
        or report.get("shutdown_status") != "application_closed"
        or measurement_decision not in {GO_DECISION, NO_GO_DECISION}
        or child_decision != measurement_decision
        or parent_decision != measurement_decision
    ):
        raise ValueError("trajectory_preflight_runtime_agreement_invalid")
    return str(measurement_decision)


def evaluate_bound_runtime_report(report: Mapping[str, Any]) -> dict[str, Any]:
    parent_evaluation = evaluate_runtime_measurements(report)
    validate_runtime_report_agreement(report, parent_evaluation)
    return parent_evaluation


def validate_provisional_runtime_report_agreement(
    report: Mapping[str, Any], parent_evaluation: Mapping[str, Any]
) -> str:
    child_evaluation = report.get("child_evaluation")
    measurement_decision = report.get("measurement_decision")
    child_decision = (
        child_evaluation.get("decision")
        if isinstance(child_evaluation, Mapping)
        else None
    )
    parent_decision = (
        parent_evaluation.get("decision")
        if isinstance(parent_evaluation, Mapping)
        else None
    )
    if (
        report.get("lifecycle_status")
        != "measurement_complete_pending_application_close"
        or report.get("shutdown_status") != "pending"
        or measurement_decision not in {GO_DECISION, NO_GO_DECISION}
        or child_decision != measurement_decision
        or parent_decision != measurement_decision
    ):
        raise ValueError(
            "trajectory_preflight_provisional_runtime_agreement_invalid"
        )
    return str(measurement_decision)


def evaluate_bound_provisional_runtime_report(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    parent_evaluation = evaluate_runtime_measurements(report)
    validate_provisional_runtime_report_agreement(report, parent_evaluation)
    return parent_evaluation


def resolve_usd_composition_closure(
    roots: Sequence[str | os.PathLike[str]],
) -> dict[str, str]:
    from pxr import Sdf

    if not isinstance(roots, Sequence) or isinstance(roots, (str, bytes)) or not roots:
        raise ValueError("trajectory_preflight_usd_composition_invalid")
    pending = [Path(root).resolve() for root in roots]
    observed: dict[str, str] = {}
    while pending:
        path = pending.pop(0).resolve()
        try:
            relative = path.relative_to(REPO_ROOT).as_posix()
        except ValueError as exc:
            raise ValueError("trajectory_preflight_usd_composition_outside_repo") from exc
        if relative in observed:
            continue
        if not path.is_file():
            raise ValueError(f"trajectory_preflight_usd_composition_missing:{relative}")
        try:
            layer = Sdf.Layer.FindOrOpen(str(path))
        except Exception as exc:
            raise ValueError(
                f"trajectory_preflight_usd_composition_invalid:{relative}"
            ) from exc
        if layer is None:
            raise ValueError(f"trajectory_preflight_usd_composition_invalid:{relative}")
        observed[relative] = sha256_file(path)
        for dependency in layer.GetCompositionAssetDependencies():
            if not dependency:
                continue
            dependency_path = Path(dependency)
            if not dependency_path.is_absolute():
                dependency_path = path.parent / dependency_path
            pending.append(dependency_path.resolve())
    return dict(sorted(observed.items()))


def validate_run_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    error = "trajectory_preflight_run_identity_invalid"
    if not isinstance(identity, Mapping) or set(identity) != {
        "schema_version",
        "interpreter",
        "config",
        "asset",
        "robot",
        "implementation",
        "usd_composition_closure",
        "runtime_data",
        "workspace_drift_seal",
        "identity_sha256",
    }:
        raise ValueError(error)
    if identity.get("schema_version") != 1:
        raise ValueError(error)
    if identity.get("workspace_drift_seal") != WORKSPACE_DRIFT_SEAL:
        raise ValueError(error)
    interpreter = identity.get("interpreter")
    if (
        not isinstance(interpreter, Mapping)
        or dict(interpreter)
        != {
            "requested_path": str(DEFAULT_ISAAC_PYTHON),
            "resolved_path": str(DEFAULT_ISAAC_PYTHON.resolve()),
            "sha256": EXPECTED_ISAAC_PYTHON_SHA256,
        }
    ):
        raise ValueError(error)
    expected_records = {
        "config": (DEFAULT_CONFIG.resolve(), EXPECTED_CONFIG_SHA256),
        "asset": (ASSET_PATH.resolve(), EXPECTED_ASSET_SHA256),
        "robot": (ROBOT_PATH.resolve(), EXPECTED_ROBOT_SHA256),
    }
    for name, (path, expected_hash) in expected_records.items():
        record = identity.get(name)
        if (
            not isinstance(record, Mapping)
            or set(record) != {"path", "sha256"}
            or Path(str(record.get("path"))).resolve() != path
            or record.get("sha256") != expected_hash
        ):
            raise ValueError(error)
    implementation = identity.get("implementation")
    if not isinstance(implementation, Mapping) or set(implementation) != {
        "files",
        "closure_sha256",
    }:
        raise ValueError(error)
    files = implementation.get("files")
    if not isinstance(files, Mapping) or set(files) != {
        *PINNED_IMPLEMENTATION_SHA256,
        SELF_RELATIVE_PATH,
    }:
        raise ValueError(error)
    if not set(DIRECT_PROJECT_IMPORT_PATHS).issubset(files):
        raise ValueError(error)
    if any(files.get(path) != digest for path, digest in PINNED_IMPLEMENTATION_SHA256.items()):
        raise ValueError(error)
    if files.get(SELF_RELATIVE_PATH) != sha256_file(REPO_ROOT / SELF_RELATIVE_PATH):
        raise ValueError(error)
    if implementation.get("closure_sha256") != canonical_json_sha256(files):
        raise ValueError(error)
    for name, expected_files in (
        ("usd_composition_closure", PINNED_USD_COMPOSITION_SHA256),
        ("runtime_data", PINNED_RUNTIME_DATA_SHA256),
    ):
        closure = identity.get(name)
        if (
            not isinstance(closure, Mapping)
            or set(closure) != {"files", "closure_sha256"}
            or closure.get("files") != expected_files
            or closure.get("closure_sha256")
            != canonical_json_sha256(expected_files)
        ):
            raise ValueError(error)
    payload = {key: value for key, value in identity.items() if key != "identity_sha256"}
    if identity.get("identity_sha256") != canonical_json_sha256(payload):
        raise ValueError(error)
    return dict(identity)


def build_run_identity(
    config_path: str | os.PathLike[str] = DEFAULT_CONFIG,
) -> dict[str, Any]:
    config = Path(config_path).resolve()
    observed_inputs = {
        "config": sha256_file(config),
        "asset": sha256_file(ASSET_PATH),
        "robot": sha256_file(ROBOT_PATH),
    }
    implementation = {
        relative: sha256_file(REPO_ROOT / relative)
        for relative in (*PINNED_IMPLEMENTATION_SHA256, SELF_RELATIVE_PATH)
    }
    runtime_data = {
        relative: sha256_file(REPO_ROOT / relative)
        for relative in PINNED_RUNTIME_DATA_SHA256
    }
    usd_composition = resolve_usd_composition_closure([ASSET_PATH, ROBOT_PATH])
    interpreter_hash = sha256_file(DEFAULT_ISAAC_PYTHON.resolve())
    if (
        config != DEFAULT_CONFIG.resolve()
        or observed_inputs
        != {
            "config": EXPECTED_CONFIG_SHA256,
            "asset": EXPECTED_ASSET_SHA256,
            "robot": EXPECTED_ROBOT_SHA256,
        }
        or any(
            implementation.get(path) != digest
            for path, digest in PINNED_IMPLEMENTATION_SHA256.items()
        )
        or runtime_data != PINNED_RUNTIME_DATA_SHA256
        or usd_composition != PINNED_USD_COMPOSITION_SHA256
        or interpreter_hash != EXPECTED_ISAAC_PYTHON_SHA256
    ):
        raise ValueError("trajectory_preflight_run_identity_hash_mismatch")
    payload = {
        "schema_version": 1,
        "interpreter": {
            "requested_path": str(DEFAULT_ISAAC_PYTHON),
            "resolved_path": str(DEFAULT_ISAAC_PYTHON.resolve()),
            "sha256": interpreter_hash,
        },
        "config": {"path": str(config), "sha256": observed_inputs["config"]},
        "asset": {
            "path": str(ASSET_PATH.resolve()),
            "sha256": observed_inputs["asset"],
        },
        "robot": {
            "path": str(ROBOT_PATH.resolve()),
            "sha256": observed_inputs["robot"],
        },
        "implementation": {
            "files": implementation,
            "closure_sha256": canonical_json_sha256(implementation),
        },
        "usd_composition_closure": {
            "files": usd_composition,
            "closure_sha256": canonical_json_sha256(usd_composition),
        },
        "runtime_data": {
            "files": runtime_data,
            "closure_sha256": canonical_json_sha256(runtime_data),
        },
        "workspace_drift_seal": dict(WORKSPACE_DRIFT_SEAL),
    }
    return validate_run_identity(
        {**payload, "identity_sha256": canonical_json_sha256(payload)}
    )


def process_group_is_empty(process_group_id: int) -> bool:
    if type(process_group_id) is not int or process_group_id <= 0:
        raise ValueError("trajectory_preflight_process_group_id_invalid")
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def terminate_process_group(
    process: subprocess.Popen[Any],
    *,
    term_grace_seconds: float = 30.0,
    kill_grace_seconds: float = 10.0,
) -> str:
    if process.poll() is not None:
        process.wait(timeout=kill_grace_seconds)
        if process_group_is_empty(process.pid):
            return "ALREADY_EXITED"
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return "ALREADY_EXITED"
        if process_group_is_empty(process.pid):
            return "SIGTERM_DESCENDANTS"
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return "SIGTERM_DESCENDANTS"
        return (
            "SIGKILL_DESCENDANTS"
            if process_group_is_empty(process.pid)
            else "SIGKILL_UNREAPED"
        )
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=term_grace_seconds)
        return "SIGTERM"
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


def finalize_parent_report(
    *,
    runtime_evaluation: Mapping[str, Any] | None,
    pre_run_identity: Mapping[str, Any],
    post_run_identity: Mapping[str, Any] | None,
    child_command: Sequence[str],
    child_pid: int | None,
    child_returncode: int,
    timed_out: bool,
    termination: str | None,
    runtime_error: str | None,
    child_reaped: bool,
    process_group_empty: bool,
) -> dict[str, Any]:
    identity_drift = bool(
        post_run_identity is None or dict(post_run_identity) != dict(pre_run_identity)
    )
    computed = (
        runtime_evaluation.get("decision")
        if isinstance(runtime_evaluation, Mapping)
        else RUNTIME_ERROR_DECISION
    )
    if computed not in {GO_DECISION, NO_GO_DECISION}:
        computed = RUNTIME_ERROR_DECISION
    clean = bool(
        not timed_out
        and child_returncode == 0
        and runtime_error is None
        and child_reaped
        and process_group_empty
        and not identity_drift
        and isinstance(runtime_evaluation, Mapping)
        and computed in {GO_DECISION, NO_GO_DECISION}
    )
    report = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "finalized_at_utc": datetime.now(timezone.utc).isoformat(),
        "pre_shutdown_decision": computed,
        "run_identity": dict(pre_run_identity),
        "post_run_identity": (
            dict(post_run_identity)
            if isinstance(post_run_identity, Mapping)
            else None
        ),
        "runtime_evaluation": (
            dict(runtime_evaluation)
            if isinstance(runtime_evaluation, Mapping)
            else None
        ),
        "child_process": {
            "command": [str(value) for value in child_command],
            "pid": child_pid,
            "returncode": child_returncode,
            "timed_out": timed_out,
            "termination": termination,
            "reaped": child_reaped,
            "process_group_empty": process_group_empty,
        },
        "runtime_error": runtime_error,
        "identity_authority": "workspace_pre_post_drift_seal_v1",
        "external_trust_root": False,
        "process_authority": {
            "authority": "leader_wait_then_process_group_quiescence_v1",
            "process_group_coverage": True,
            "detached_child_cgroup_coverage": False,
            "limitation": (
                "No dedicated cgroup; detached descendants outside the child "
                "process group are not covered."
            ),
        },
    }
    if clean:
        report.update(
            {
                "decision": computed,
                "lifecycle_status": "completed",
                "shutdown_status": "child_exit_0",
            }
        )
        return report
    if timed_out:
        shutdown = "child_timeout"
    elif runtime_error is not None and runtime_error.startswith("child_launch_error"):
        shutdown = "child_launch_error"
    elif identity_drift or (
        runtime_error is not None and runtime_error.startswith("identity_")
    ):
        shutdown = "identity_validation_failed"
    elif not child_reaped or not process_group_empty:
        shutdown = "process_cleanup_failed"
    elif child_returncode != 0:
        shutdown = "child_exit_nonzero"
    elif runtime_error is not None:
        shutdown = "evidence_validation_failed"
    else:
        shutdown = "measurement_runtime_error"
    report.update(
        {
            "decision": RUNTIME_ERROR_DECISION,
            "lifecycle_status": "failed",
            "shutdown_status": shutdown,
        }
    )
    return report


def _artifact_record(path: Path, *, relative_to: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(relative_to)),
        "byte_count": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build_child_command(
    *,
    config_path: Path,
    run_id: str,
    owner_path: Path,
    runtime_report_path: Path,
    run_identity_sha256: str,
) -> list[str]:
    return [
        str(DEFAULT_ISAAC_PYTHON.resolve()),
        str(Path(__file__).resolve()),
        "--runtime-child",
        "--headless",
        "--config",
        str(config_path.resolve()),
        "--run-id",
        run_id,
        "--owner",
        str(owner_path.resolve()),
        "--runtime-report",
        str(runtime_report_path.resolve()),
        "--run-identity-sha256",
        run_identity_sha256,
    ]


def _run_parent(args: argparse.Namespace) -> int:
    try:
        args.out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(
            f"geometry-aware trajectory preflight refused existing output: {args.out_dir}",
            file=sys.stderr,
            flush=True,
        )
        return 2

    stdout_path = args.out_dir / STDOUT_BASENAME
    stderr_path = args.out_dir / STDERR_BASENAME
    owner_path = args.out_dir / OWNER_BASENAME
    runtime_path = args.out_dir / RUNTIME_REPORT_BASENAME
    run_id = "trajectory-preflight-" + secrets.token_hex(16)
    command: list[str] = []
    pre_identity: Mapping[str, Any] = {"status": "unavailable"}
    post_identity: Mapping[str, Any] | None = None
    runtime_evaluation: Mapping[str, Any] | None = None
    runtime_error = None
    child_pid = None
    child_returncode = 127
    timed_out = False
    termination = None
    process: subprocess.Popen[Any] | None = None
    child_reaped = True
    group_empty = True
    runtime_report_payload: bytes | None = None
    phase = "identity_preflight"

    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        try:
            pre_identity = build_run_identity(args.config)
            command = build_child_command(
                config_path=args.config,
                run_id=run_id,
                owner_path=owner_path,
                runtime_report_path=runtime_path,
                run_identity_sha256=str(pre_identity["identity_sha256"]),
            )
            phase = "child_launch"
            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            child_pid = int(process.pid)
            child_reaped = False
            group_empty = False
            phase = "child_wait"
            try:
                child_returncode = int(process.wait(timeout=args.timeout_seconds))
            except subprocess.TimeoutExpired:
                timed_out = True
                runtime_error = "child_timeout"
                termination = terminate_process_group(process)
                child_returncode = (
                    int(process.returncode)
                    if process.returncode is not None
                    else -signal.SIGKILL
                )
            if not timed_out and child_returncode != 0:
                runtime_error = f"child_exit_nonzero:{child_returncode}"
        except BaseException as exc:
            runtime_error = f"{phase}_error:{type(exc).__name__}:{exc}"
        finally:
            if process is not None and process.poll() is None:
                try:
                    termination = terminate_process_group(process)
                except BaseException as cleanup_exc:
                    termination = f"CLEANUP_ERROR:{type(cleanup_exc).__name__}"
            if process is not None and process.returncode is not None:
                child_returncode = int(process.returncode)
            child_reaped = bool(process is None or process.poll() is not None)
            if process is not None:
                try:
                    group_empty = process_group_is_empty(process.pid)
                    if not group_empty:
                        if runtime_error is None:
                            runtime_error = "process_group_nonempty_after_child_exit"
                        try:
                            termination = terminate_process_group(process)
                        except BaseException as cleanup_exc:
                            termination = (
                                f"CLEANUP_ERROR:{type(cleanup_exc).__name__}"
                            )
                        group_empty = process_group_is_empty(process.pid)
                except BaseException as cleanup_exc:
                    group_empty = False
                    if runtime_error is None:
                        runtime_error = (
                            "process_group_validation_error:"
                            f"{type(cleanup_exc).__name__}:{cleanup_exc}"
                        )
            if runtime_error is None and child_reaped and group_empty:
                phase = "runtime_report"
                try:
                    owner = load_owner(owner_path)
                    runtime_report_payload = runtime_path.read_bytes()
                    runtime_report = load_runtime_report_bytes(
                        runtime_report_payload, source_name=str(runtime_path)
                    )
                    validate_child_binding(
                        owner,
                        runtime_report,
                        expected_child_pid=child_pid,
                        expected_run_id=run_id,
                        expected_run_identity_sha256=str(
                            pre_identity["identity_sha256"]
                        ),
                    )
                    if (
                        runtime_report.get("measurement_decision")
                        == RUNTIME_ERROR_DECISION
                    ):
                        raise RuntimeError(
                            "child_measurement_runtime_error:"
                            + str(runtime_report.get("fatal_error"))
                        )
                    runtime_evaluation = evaluate_bound_provisional_runtime_report(
                        runtime_report
                    )
                except BaseException as exc:
                    runtime_error = f"{phase}_error:{type(exc).__name__}:{exc}"
            phase = "identity_postflight"
            try:
                post_identity = build_run_identity(args.config)
                if post_identity != pre_identity:
                    raise ValueError("identity_changed_during_run")
            except BaseException as exc:
                identity_error = f"{phase}_error:{type(exc).__name__}:{exc}"
                runtime_error = (
                    identity_error
                    if runtime_error is None
                    else f"{runtime_error};{identity_error}"
                )

    report = finalize_parent_report(
        runtime_evaluation=runtime_evaluation,
        pre_run_identity=pre_identity,
        post_run_identity=post_identity,
        child_command=command,
        child_pid=child_pid,
        child_returncode=child_returncode,
        timed_out=timed_out,
        termination=termination,
        runtime_error=runtime_error,
        child_reaped=child_reaped,
        process_group_empty=group_empty,
    )
    artifacts = {
        "child_stdout": _artifact_record(stdout_path, relative_to=args.out_dir),
        "child_stderr": _artifact_record(stderr_path, relative_to=args.out_dir),
    }
    if owner_path.is_file():
        artifacts["owner"] = _artifact_record(owner_path, relative_to=args.out_dir)
    if runtime_report_payload is not None:
        artifacts["runtime_report"] = runtime_report_artifact_from_bytes(
            runtime_report_payload, relative_path=RUNTIME_REPORT_BASENAME
        )
    elif runtime_path.is_file():
        artifacts["runtime_report"] = _artifact_record(
            runtime_path, relative_to=args.out_dir
        )
    report["artifacts"] = artifacts
    final_path = args.out_dir / FINAL_REPORT_BASENAME
    atomic_create_json(final_path, report)
    print(
        f"geometry-aware trajectory preflight decision={report['decision']} out={final_path}",
        flush=True,
    )
    return 0 if report["decision"] == GO_DECISION else 2


def _row_matrix(stage: Any, path: str) -> np.ndarray:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"trajectory_preflight_prim_missing:{path}")
    matrix = np.asarray(
        UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()),
        dtype=np.float64,
    )
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise RuntimeError(f"trajectory_preflight_world_matrix_invalid:{path}")
    return matrix


def _matrix_pose_wxyz(matrix: np.ndarray) -> dict[str, Any]:
    from scipy.spatial.transform import Rotation

    row_matrix = np.asarray(matrix, dtype=np.float64)
    if row_matrix.shape != (4, 4) or not np.isfinite(row_matrix).all():
        raise ValueError("trajectory_preflight_pose_matrix_invalid")
    quaternion_xyzw = Rotation.from_matrix(row_matrix[:3, :3].T).as_quat()
    return {
        "position_m": row_matrix[3, :3].tolist(),
        "orientation_wxyz": quaternion_xyzw[[3, 0, 1, 2]].tolist(),
    }


def _rmpflow_pose_wxyz(controller: Any) -> dict[str, Any]:
    from scipy.spatial.transform import Rotation

    position, column_rotation = controller.get_end_effector_pose_world()
    position = np.asarray(position, dtype=np.float64)
    rotation = np.asarray(column_rotation, dtype=np.float64)
    if (
        position.shape != (3,)
        or rotation.shape != (3, 3)
        or not np.isfinite(position).all()
        or not np.isfinite(rotation).all()
    ):
        raise RuntimeError("trajectory_preflight_rmpflow_pose_invalid")
    quaternion_xyzw = Rotation.from_matrix(rotation).as_quat()
    return {
        "position_m": position.tolist(),
        "orientation_wxyz": quaternion_xyzw[[3, 0, 1, 2]].tolist(),
    }


def _collider_corners_world(stage: Any, collider: Mapping[str, Any]) -> np.ndarray:
    low = np.asarray(collider.get("aabb_local_min_m"), dtype=np.float64)
    high = np.asarray(collider.get("aabb_local_max_m"), dtype=np.float64)
    if (
        low.shape != (3,)
        or high.shape != (3,)
        or not np.isfinite(low).all()
        or not np.isfinite(high).all()
        or np.any(high < low)
    ):
        raise RuntimeError("trajectory_preflight_collider_local_bounds_invalid")
    corners = np.asarray(
        [
            [x, y, z, 1.0]
            for x in (low[0], high[0])
            for y in (low[1], high[1])
            for z in (low[2], high[2])
        ],
        dtype=np.float64,
    )
    return corners @ _row_matrix(stage, str(collider["path"]))


def _catalog_bounds(stage: Any, catalog: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    try:
        validated = validate_cooked_catalog(catalog)
    except ValueError as exc:
        raise RuntimeError("trajectory_preflight_collider_catalog_invalid") from exc
    colliders = validated["colliders"]
    corners = np.concatenate(
        [_collider_corners_world(stage, collider) for collider in colliders], axis=0
    )[:, :3]
    return corners.min(axis=0), corners.max(axis=0)


def _catalog_with_contact_offset_authority(
    stage: Any, catalog: Mapping[str, Any], *, read_offset: Any
) -> dict[str, Any]:
    enriched = {
        key: value for key, value in catalog.items() if key != "colliders"
    }
    enriched["cooked_aabb_precision"] = dict(COOKED_AABB_PRECISION)
    colliders = []
    for collider in catalog.get("colliders", []):
        if not isinstance(collider, Mapping) or not isinstance(
            collider.get("path"), str
        ):
            raise RuntimeError("trajectory_preflight_collider_catalog_invalid")
        observed = read_offset(stage, collider["path"])
        value = _optional_nonnegative(observed.get("contact_offset_m"))
        authority = (
            "authored"
            if value is not None
            and observed.get("contact_offset_authority") == "authored"
            else "unresolved"
        )
        colliders.append(
            {
                **dict(collider),
                "contact_offset": {
                    "contact_offset_m": value,
                    "authority": authority,
                },
            }
        )
    enriched["colliders"] = colliders
    try:
        return validate_cooked_catalog(enriched)
    except ValueError as exc:
        raise ValueError(f"{exc}:body_path={enriched.get('body_path')}") from exc


def _static_collision_paths(stage: Any, body_path: str) -> list[str]:
    from pxr import Usd, UsdPhysics

    body = stage.GetPrimAtPath(body_path)
    if not body or not body.IsValid() or body.HasAPI(UsdPhysics.RigidBodyAPI):
        raise RuntimeError("trajectory_preflight_static_query_body_invalid")
    collision_paths = []
    nested_rigid_bodies = []
    for prim in Usd.PrimRange(body):
        path = str(prim.GetPath())
        if path != body_path and prim.HasAPI(UsdPhysics.RigidBodyAPI):
            nested_rigid_bodies.append(path)
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is not False:
            collision_paths.append(path)
    if nested_rigid_bodies or not collision_paths:
        raise RuntimeError("trajectory_preflight_static_query_hierarchy_invalid")
    return sorted(collision_paths)


def _query_static_cooked_colliders(
    app: Any,
    stage: Any,
    body_path: str,
    *,
    query_colliders: Any,
) -> dict[str, Any]:
    from pxr import Sdf, Usd, UsdPhysics

    collision_paths = _static_collision_paths(stage, body_path)
    session = stage.GetSessionLayer()
    if session is None:
        raise RuntimeError("trajectory_preflight_static_query_session_missing")
    previous_target = stage.GetEditTarget()
    previous_sublayers = list(session.subLayerPaths)
    temporary_layer = Sdf.Layer.CreateAnonymous(
        "trajectory_preflight_static_cooked_query.usda"
    )
    if temporary_layer is None:
        raise RuntimeError("trajectory_preflight_static_query_layer_create_failed")
    raw: Mapping[str, Any] | None = None
    try:
        session.subLayerPaths.insert(0, temporary_layer.identifier)
        stage.SetEditTarget(Usd.EditTarget(temporary_layer))
        body = stage.GetPrimAtPath(body_path)
        rigid_body = UsdPhysics.RigidBodyAPI.Apply(body)
        rigid_body.CreateRigidBodyEnabledAttr(False)
        app.update()
        app.update()
        raw = query_colliders(app, stage, body_path)
    finally:
        stage.SetEditTarget(previous_target)
        session.subLayerPaths = previous_sublayers
        app.update()
        app.update()

    restored_paths = _static_collision_paths(stage, body_path)
    if restored_paths != collision_paths or not isinstance(raw, Mapping):
        raise RuntimeError("trajectory_preflight_static_query_cleanup_invalid")
    colliders = raw.get("colliders")
    if (
        raw.get("body_path") != body_path
        or not isinstance(colliders, Sequence)
        or isinstance(colliders, (str, bytes))
        or any(not isinstance(collider, Mapping) for collider in colliders)
        or sorted(str(collider.get("path")) for collider in colliders)
        != collision_paths
    ):
        raise RuntimeError("trajectory_preflight_static_query_result_invalid")
    return {
        **dict(raw),
        "query_authority": build_static_cooked_query_authority(
            body_path=body_path,
            collision_paths=collision_paths,
        ),
    }


def _stage_constraint_inventory(stage: Any) -> dict[str, Any]:
    from pxr import UsdPhysics

    joint_paths = []
    fixed_attachment_paths = []
    records = []
    for prim in stage.Traverse():
        is_joint = prim.IsA(UsdPhysics.Joint)
        body0 = prim.GetRelationship("physics:body0")
        body1 = prim.GetRelationship("physics:body1")
        if not is_joint and not body0 and not body1:
            continue
        path = str(prim.GetPath())
        if is_joint:
            joint_paths.append(path)
        if prim.IsA(UsdPhysics.FixedJoint):
            fixed_attachment_paths.append(path)
        records.append(
            {
                "path": path,
                "schema_type": str(prim.GetTypeName()),
                "body0_targets": sorted(
                    str(target) for target in body0.GetTargets()
                )
                if body0
                else [],
                "body1_targets": sorted(
                    str(target) for target in body1.GetTargets()
                )
                if body1
                else [],
            }
        )
    joint_paths.sort()
    fixed_attachment_paths.sort()
    records.sort(key=lambda record: record["path"])
    payload = {
        "joint_paths": joint_paths,
        "constraint_paths": [record["path"] for record in records],
        "fixed_attachment_paths": fixed_attachment_paths,
        "constraint_records": records,
    }
    return {**payload, "inventory_sha256": canonical_json_sha256(payload)}


def _author_source_isolation(
    stage: Any, *, source_body_path: str, robot_rigid_body_paths: Sequence[str]
) -> None:
    from pxr import PhysxSchema, Sdf, UsdPhysics

    source = stage.GetPrimAtPath(source_body_path)
    if not source or not source.IsValid():
        raise RuntimeError("trajectory_preflight_source_missing")
    rigid = UsdPhysics.RigidBodyAPI(source)
    if not rigid:
        raise RuntimeError("trajectory_preflight_source_rigid_body_required")
    rigid.CreateKinematicEnabledAttr().Set(True)
    filtered = UsdPhysics.FilteredPairsAPI.Apply(source)
    filtered.CreateFilteredPairsRel().SetTargets(
        [Sdf.Path(path) for path in robot_rigid_body_paths]
    )
    if source.HasAPI(PhysxSchema.PhysxContactReportAPI):
        source.RemoveAPI(PhysxSchema.PhysxContactReportAPI)
    threshold = source.GetAttribute("physxContactReport:threshold")
    if not threshold:
        threshold = source.CreateAttribute(
            "physxContactReport:threshold", Sdf.ValueTypeNames.Float, custom=False
        )
    threshold.Set(float(np.finfo(np.float32).max))


def _read_source_isolation_snapshot(
    stage: Any,
    *,
    checkpoint: str,
    source_body_path: str,
    robot_rigid_body_paths: Sequence[str],
    expected_source_world_matrix: Sequence[Sequence[float]],
) -> dict[str, Any]:
    from pxr import PhysxSchema, UsdPhysics

    source = stage.GetPrimAtPath(source_body_path)
    if not source or not source.IsValid():
        raise RuntimeError("trajectory_preflight_source_missing")
    rigid = UsdPhysics.RigidBodyAPI(source)
    filtered = UsdPhysics.FilteredPairsAPI(source)
    threshold = source.GetAttribute("physxContactReport:threshold")
    return evaluate_source_isolation_snapshot(
        checkpoint=checkpoint,
        source_body_path=source_body_path,
        source_kinematic_enabled=(
            bool(rigid.GetKinematicEnabledAttr().Get()) if rigid else False
        ),
        filtered_pair_targets=(
            sorted(str(path) for path in filtered.GetFilteredPairsRel().GetTargets())
            if filtered
            else []
        ),
        expected_robot_rigid_body_paths=robot_rigid_body_paths,
        contact_report_api_applied=source.HasAPI(
            PhysxSchema.PhysxContactReportAPI
        ),
        contact_report_threshold=(threshold.Get() if threshold else None),
        source_world_matrix=_row_matrix(stage, source_body_path).tolist(),
        expected_source_world_matrix=expected_source_world_matrix,
    )


def _resolved_catalog_contact_offset(catalog: Mapping[str, Any]) -> float | None:
    try:
        validated = validate_cooked_catalog(catalog)
    except (TypeError, ValueError):
        return None
    values = []
    for collider in validated["colliders"]:
        record = collider.get("contact_offset")
        value = _optional_nonnegative(
            record.get("contact_offset_m")
            if isinstance(record, Mapping)
            and record.get("authority") != "unresolved"
            else None
        )
        if value is None:
            return None
        values.append(value)
    return max(values) if values else None


def _aabb_distance(
    first: tuple[np.ndarray, np.ndarray],
    second: tuple[np.ndarray, np.ndarray],
) -> float:
    first_low, first_high = first
    second_low, second_high = second
    separation = np.maximum(
        np.maximum(first_low - second_high, second_low - first_high), 0.0
    )
    return float(np.linalg.norm(separation))


def _minimum_catalog_distance(
    stage: Any,
    source: Mapping[str, Any],
    others: Sequence[Mapping[str, Any]],
) -> float | None:
    if not others:
        return None
    source_bounds = _catalog_bounds(stage, source)
    return min(_aabb_distance(source_bounds, _catalog_bounds(stage, item)) for item in others)


def _directional_finger_clearances(
    stage: Any,
    *,
    source: Mapping[str, Any],
    fingers: Mapping[str, Mapping[str, Any]],
    opening_axis_world: Sequence[float],
) -> dict[str, float]:
    source_matrices = _collider_transform_evidence(stage, source)
    source_interval = project_cooked_catalog_interval(
        catalog=source,
        collider_world_matrices=source_matrices,
        axis_world=opening_axis_world,
    )
    source_center = float(sum(source_interval) / 2.0)
    result = {}
    for side in SIDES:
        interval = project_cooked_catalog_interval(
            catalog=fingers[side],
            collider_world_matrices=_collider_transform_evidence(
                stage, fingers[side]
            ),
            axis_world=opening_axis_world,
        )
        finger_center = float(sum(interval) / 2.0)
        if finger_center <= source_center:
            clearance = float(source_interval[0] - interval[1])
        else:
            clearance = float(interval[0] - source_interval[1])
        result[side] = max(0.0, clearance)
    return result


def _projected_finger_gap(
    stage: Any,
    *,
    fingers: Mapping[str, Mapping[str, Any]],
    opening_axis_world: Sequence[float],
) -> dict[str, Any]:
    matrices = {
        side: _collider_transform_evidence(stage, fingers[side])
        for side in SIDES
    }
    intervals = {
        side: project_cooked_catalog_interval(
            catalog=fingers[side],
            collider_world_matrices=matrices[side],
            axis_world=opening_axis_world,
        )
        for side in SIDES
    }
    ordered = sorted(intervals.values(), key=lambda interval: sum(interval) / 2.0)
    gap_error_bound = derive_cooked_gap_error_bound(
        finger_collider_catalogs=fingers,
        finger_collider_world_matrices=matrices,
    )
    if not gap_error_bound.get("passed"):
        raise RuntimeError("trajectory_preflight_gap_precision_unresolved")
    return {
        "projected_intervals_m": intervals,
        "open_inner_gap_m": max(0.0, float(ordered[1][0] - ordered[0][1])),
        "finger_collider_world_matrices": matrices,
        "gap_error_bound": gap_error_bound,
        "opening_axis_world": list(opening_axis_world),
        "method": "cooked_collider_projection_on_tool_opening_axis",
    }


def _collider_transform_evidence(
    stage: Any, catalog: Mapping[str, Any]
) -> list[dict[str, Any]]:
    records = []
    for collider in catalog["colliders"]:
        path = str(collider["path"])
        records.append({"path": path, "matrix": _row_matrix(stage, path).tolist()})
    if not records:
        raise RuntimeError("trajectory_preflight_collider_transform_evidence_empty")
    return records


def _catalog_edge_radius(
    stage: Any,
    catalog: Mapping[str, Any],
    tool_position_m: Sequence[float],
) -> float:
    tool = np.asarray(tool_position_m, dtype=np.float64)
    if tool.shape != (3,) or not np.isfinite(tool).all():
        raise RuntimeError("trajectory_preflight_tool_position_invalid")
    return max(
        float(np.max(np.linalg.norm(_collider_corners_world(stage, collider)[:, :3] - tool, axis=1)))
        for collider in catalog["colliders"]
    )


def _box_world_bounds(
    *, size_m: Sequence[float], world_matrix: Sequence[Sequence[float]]
) -> tuple[np.ndarray, np.ndarray]:
    points = _box_world_points(size_m=size_m, world_matrix=world_matrix)
    return points.min(axis=0), points.max(axis=0)


def _box_world_points(
    *, size_m: Sequence[float], world_matrix: Sequence[Sequence[float]]
) -> np.ndarray:
    size = np.asarray(size_m, dtype=np.float64)
    matrix = np.asarray(world_matrix, dtype=np.float64)
    if (
        size.shape != (3,)
        or np.any(size <= 0.0)
        or not np.isfinite(size).all()
        or matrix.shape != (4, 4)
        or not np.isfinite(matrix).all()
    ):
        raise ValueError("trajectory_preflight_calibration_box_invalid")
    half = size / 2.0
    corners = np.asarray(
        [
            [x, y, z, 1.0]
            for x in (-half[0], half[0])
            for y in (-half[1], half[1])
            for z in (-half[2], half[2])
        ],
        dtype=np.float64,
    ) @ matrix
    return corners[:, :3]


def _remote_calibration_clearance_budget(
    stage: Any,
    *,
    calibration_spec: Mapping[str, Any],
    obstacle_catalogs: Mapping[str, Mapping[str, Any]],
    finger_gap_evidence: Mapping[str, Any],
    numerical_margin_m: float,
) -> dict[str, Any]:
    body_points = _box_world_points(
        size_m=calibration_spec.get("size_m", []),
        world_matrix=calibration_spec.get("world_matrix", []),
    )
    body_bounds = {
        "min_m": body_points.min(axis=0).tolist(),
        "max_m": body_points.max(axis=0).tolist(),
    }
    axis = _finite_array(calibration_spec.get("opening_axis_world"), (3,))
    intervals = finger_gap_evidence.get("projected_intervals_m")
    if axis is None or not isinstance(intervals, Mapping):
        raise RuntimeError("trajectory_preflight_calibration_placement_invalid")
    ordered = sorted(
        [_finite_array(intervals.get(side), (2,)) for side in SIDES],
        key=lambda interval: float(np.sum(interval)) if interval is not None else math.inf,
    )
    if any(interval is None for interval in ordered):
        raise RuntimeError("trajectory_preflight_calibration_placement_invalid")
    body_projection = body_points @ axis
    obstacle_bounds = {}
    obstacle_offsets = {}
    for path, catalog in sorted(obstacle_catalogs.items()):
        low, high = _catalog_bounds(stage, catalog)
        obstacle_bounds[path] = {"min_m": low.tolist(), "max_m": high.tolist()}
        obstacle_offsets[path] = _resolved_catalog_contact_offset(catalog)
    return evaluate_remote_calibration_clearance_budget(
        calibration_body_world_bounds_m=body_bounds,
        obstacle_world_bounds_m=obstacle_bounds,
        obstacle_contact_offset_bounds_m=obstacle_offsets,
        required_obstacle_paths=sorted(obstacle_catalogs),
        calibration_body_projection_interval_m=[
            float(np.min(body_projection)),
            float(np.max(body_projection)),
        ],
        finger_inner_projection_interval_m=[
            float(ordered[0][1]),
            float(ordered[1][0]),
        ],
        calibration_body_contact_offset_m=calibration_spec.get(
            "contact_offset_m"
        ),
        numerical_margin_m=numerical_margin_m,
    )


def _action_payload(action: Any) -> dict[str, Any]:
    def optional_values(name: str) -> Any:
        value = getattr(action, name, None)
        if value is None:
            return None
        if hasattr(value, "detach"):
            value = value.detach().cpu().numpy()
        array = np.asarray(value, dtype=object).reshape(-1)
        result = []
        for item in array:
            if item is None:
                result.append(None)
            else:
                number = float(item)
                if not math.isfinite(number):
                    raise RuntimeError("trajectory_preflight_action_nonfinite")
                result.append(number)
        return result

    payload = {
        "joint_positions": optional_values("joint_positions"),
        "joint_velocities": optional_values("joint_velocities"),
        "joint_efforts": optional_values("joint_efforts"),
    }
    indices = getattr(action, "joint_indices", None)
    if indices is not None:
        if hasattr(indices, "detach"):
            indices = indices.detach().cpu().numpy()
        payload["joint_indices"] = [int(value) for value in np.asarray(indices).reshape(-1)]
    return payload


def _exact_indexed_arm_action(action: Any) -> tuple[Any, dict[str, Any]]:
    from isaacsim.core.utils.types import ArticulationAction

    payload = _action_payload(action)
    positions = payload.get("joint_positions")
    if (
        not isinstance(positions, list)
        or len(positions) != 7
        or any(value is None for value in positions)
        or payload.get("joint_velocities") is not None
        or payload.get("joint_efforts") is not None
        or payload.get("joint_indices") not in (None, list(range(7)))
    ):
        raise RuntimeError("trajectory_preflight_arm_action_shape_invalid")
    exact = ArticulationAction(
        joint_positions=np.asarray(positions, dtype=np.float64),
        joint_indices=np.arange(7, dtype=np.int64),
    )
    exact_payload = _action_payload(exact)
    if not _action_payload_matches_kind(
        exact_payload, "ARM_INSERT", canonical_open_target_m=1.0
    ):
        raise RuntimeError("trajectory_preflight_arm_action_shape_invalid")
    return exact, exact_payload


def _finger_action(robot: Any, finger_indices: tuple[int, int], targets_m: Sequence[float], stage_units: float) -> Any:
    from isaacsim.core.utils.types import ArticulationAction

    joints = np.asarray(robot.get_joint_positions(), dtype=np.float64)
    targets = np.asarray(targets_m, dtype=np.float64)
    if (
        joints.ndim != 1
        or len(joints) <= max(finger_indices)
        or targets.shape != (2,)
        or not np.isfinite(joints).all()
        or not np.isfinite(targets).all()
    ):
        raise RuntimeError("trajectory_preflight_finger_action_invalid")
    positions: list[float | None] = [None] * len(joints)
    for index, value in zip(finger_indices, targets):
        positions[index] = float(value / stage_units)
    return ArticulationAction(joint_positions=positions)


def _joint_limits_m(robot: Any, finger_indices: tuple[int, int], stage_units: float) -> tuple[np.ndarray, np.ndarray]:
    view = getattr(robot, "_articulation_view", None)
    getter = getattr(view, "get_dof_limits", None)
    if not callable(getter):
        raise RuntimeError("trajectory_preflight_dof_limit_api_unavailable")
    limits = getter()
    if hasattr(limits, "detach"):
        limits = limits.detach().cpu().numpy()
    limits = np.asarray(limits, dtype=np.float64)
    if limits.ndim == 3 and limits.shape[0] == 1:
        limits = limits[0]
    if (
        limits.ndim != 2
        or limits.shape[1] != 2
        or limits.shape[0] <= max(finger_indices)
        or not np.isfinite(limits).all()
    ):
        raise RuntimeError("trajectory_preflight_dof_limits_invalid")
    selected = limits[list(finger_indices)] * stage_units
    return selected[:, 0], selected[:, 1]


def _drive_fingers(
    *,
    world: Any,
    robot: Any,
    finger_indices: tuple[int, int],
    target_m: float,
    speed_m_s: float,
    physics_dt: float,
    control_dt: float,
    substeps: int,
    stage_units: float,
    velocity_samples: list[dict[str, Any]] | None,
    physics_callback: Any | None = None,
    settle_duration_s: float = 0.0,
) -> dict[str, Any]:
    maximum_step = speed_m_s * control_dt
    if maximum_step <= 0.0:
        raise ValueError("trajectory_preflight_finger_speed_invalid")
    maximum_controls = 1000
    controls = 0
    physics_steps = 0
    final_command_start_step = None
    settled_step = None
    while True:
        current = np.asarray(robot.get_joint_positions(), dtype=np.float64)[
            list(finger_indices)
        ] * stage_units
        delta = np.full(2, target_m, dtype=np.float64) - current
        if np.max(np.abs(delta)) <= maximum_step:
            commanded = np.full(2, target_m, dtype=np.float64)
            final_control = True
        else:
            commanded = current + np.clip(delta, -maximum_step, maximum_step)
            final_control = False
        action = _finger_action(robot, finger_indices, commanded, stage_units)
        robot.get_articulation_controller().apply_action(action)
        if final_control and final_command_start_step is None:
            final_command_start_step = physics_steps
        for _ in range(substeps):
            before = np.asarray(robot.get_joint_positions(), dtype=np.float64)[
                list(finger_indices)
            ] * stage_units
            world.step(render=False)
            after = np.asarray(robot.get_joint_positions(), dtype=np.float64)[
                list(finger_indices)
            ] * stage_units
            finite_difference = (after - before) / physics_dt
            api = np.asarray(
                robot.get_gripper_pad_relative_velocities_m_s(), dtype=np.float64
            )
            if api.shape != (2,) or not np.isfinite(api).all() or not np.isfinite(finite_difference).all():
                raise RuntimeError("trajectory_preflight_pad_velocity_unavailable")
            physics_steps += 1
            if (
                final_command_start_step is not None
                and settled_step is None
                and np.max(np.abs(api)) <= 0.002
                and np.max(np.abs(finite_difference)) <= 0.002
            ):
                settled_step = physics_steps
            if velocity_samples is not None and not final_control:
                velocity_samples.append(
                    {
                        "api_pad_velocity_m_s": api.tolist(),
                        "finite_difference_pad_velocity_m_s": finite_difference.tolist(),
                    }
                )
            if physics_callback is not None:
                physics_callback()
        controls += 1
        if final_control:
            break
        if controls >= maximum_controls:
            raise RuntimeError("trajectory_preflight_finger_drive_timeout")

    settle_controls = int(math.ceil(settle_duration_s / control_dt - 1.0e-12))
    settle_samples = []
    for _ in range(settle_controls):
        action = _finger_action(
            robot, finger_indices, [target_m, target_m], stage_units
        )
        robot.get_articulation_controller().apply_action(action)
        for _ in range(substeps):
            before = np.asarray(robot.get_joint_positions(), dtype=np.float64)[
                list(finger_indices)
            ] * stage_units
            world.step(render=False)
            after = np.asarray(robot.get_joint_positions(), dtype=np.float64)[
                list(finger_indices)
            ] * stage_units
            finite_difference = (after - before) / physics_dt
            api = np.asarray(
                robot.get_gripper_pad_relative_velocities_m_s(), dtype=np.float64
            )
            if (
                api.shape != (2,)
                or not np.isfinite(api).all()
                or not np.isfinite(finite_difference).all()
            ):
                raise RuntimeError("trajectory_preflight_pad_velocity_unavailable")
            physics_steps += 1
            if (
                final_command_start_step is not None
                and settled_step is None
                and api.shape == (2,)
                and np.isfinite(api).all()
                and np.isfinite(finite_difference).all()
                and np.max(np.abs(api)) <= 0.002
                and np.max(np.abs(finite_difference)) <= 0.002
            ):
                settled_step = physics_steps
            if physics_callback is not None:
                physics_callback()
            settle_samples.append(
                {
                    "physics_step": int(world.current_time_step_index),
                    "joint_positions_m": after.tolist(),
                    "api_pad_velocity_m_s": api.tolist(),
                    "finite_difference_pad_velocity_m_s": finite_difference.tolist(),
                }
            )
    measured_settling_time = (
        None
        if final_command_start_step is None or settled_step is None
        else (settled_step - final_command_start_step) * physics_dt
    )
    return {
        "physics_step_count": physics_steps,
        "control_count": controls + settle_controls,
        "measured_settling_time_s": measured_settling_time,
        "settle_samples": settle_samples,
    }


def _raw_contact_records(
    frames: Mapping[str, Any],
    *,
    physics_step: int,
    resolve_body_path: Any,
) -> list[dict[str, Any]]:
    try:
        records = normalize_current_contacts(
            frames,
            physics_step=physics_step,
            resolve_body_path=resolve_body_path,
        )
    except (TypeError, ValueError, RuntimeError) as exc:
        raise RuntimeError("trajectory_preflight_raw_contacts_invalid") from exc
    for record in records:
        record["near_source"] = any(
            path == "/World/beaker2" or path.startswith("/World/beaker2/")
            for path in (record["body0_path"], record["body1_path"])
        )
    return records


def _author_calibration_body(
    stage: Any,
    *,
    world_matrix: np.ndarray,
    opening_axis_world: Sequence[float],
    size_m: Sequence[float],
    contact_offset_m: float,
) -> tuple[dict[str, Any], Any]:
    from pxr import Gf, PhysxSchema, UsdGeom, UsdPhysics

    UsdGeom.Xform.Define(stage, "/World/TrajectoryPreflight")
    cube = UsdGeom.Cube.Define(stage, CALIBRATION_BODY_PATH)
    cube.CreateSizeAttr(1.0)
    xform = UsdGeom.Xformable(cube.GetPrim())
    xform.ClearXformOpOrder()
    xform.AddTransformOp(UsdGeom.XformOp.PrecisionDouble).Set(
        Gf.Matrix4d(world_matrix.tolist())
    )
    xform.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(
        Gf.Vec3d(*[float(value) for value in size_m])
    )
    collision = UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
    collision.CreateCollisionEnabledAttr().Set(False)
    physx = PhysxSchema.PhysxCollisionAPI.Apply(cube.GetPrim())
    physx.CreateContactOffsetAttr().Set(float(contact_offset_m))
    physx.CreateRestOffsetAttr().Set(0.0)
    spec = calibration_body_spec(
        world_matrix=world_matrix,
        opening_axis_world=opening_axis_world,
        size_m=size_m,
        contact_offset_m=contact_offset_m,
    )
    return spec, collision.GetCollisionEnabledAttr()


def _set_calibration_collision(
    *,
    app: Any,
    world: Any,
    collision_attribute: Any,
    enabled: bool,
    read_open_state: Any | None = None,
    observe_first_enabled_step: Any | None = None,
    pre_enable_clearance_budget: Mapping[str, Any] | None = None,
    read_post_enable_clearance_budget: Any | None = None,
) -> dict[str, Any]:
    if enabled and not validate_remote_calibration_clearance_budget(
        pre_enable_clearance_budget
    ):
        return {
            "pre_enable_clearance_budget": (
                dict(pre_enable_clearance_budget)
                if isinstance(pre_enable_clearance_budget, Mapping)
                else None
            ),
            "post_enable_clearance_budget": None,
            "first_enabled_physics_step": None,
            "first_enabled_step_contacts": None,
            "failure_reason": (
                "pre_enable_calibration_clearance_budget_failed"
            ),
            "passed": False,
        }
    pause = getattr(world, "pause", None)
    play = getattr(world, "play", None)
    is_playing = getattr(world, "is_playing", None)
    if not callable(pause) or not callable(play) or not callable(is_playing):
        raise RuntimeError("trajectory_preflight_world_timeline_api_unavailable")
    timeline_was_playing = bool(is_playing())
    if not timeline_was_playing:
        raise RuntimeError("trajectory_preflight_timeline_not_playing")
    before = int(world.current_time_step_index)
    collision_before = bool(collision_attribute.Get())
    pause()
    app.update()
    after_pause_update = int(world.current_time_step_index)
    if after_pause_update != before:
        raise RuntimeError("trajectory_preflight_pause_update_advanced_physics")
    physical_open_state = None
    post_enable_budget = None
    if enabled:
        if (
            not callable(read_open_state)
            or not callable(observe_first_enabled_step)
            or not callable(read_post_enable_clearance_budget)
        ):
            raise RuntimeError("trajectory_preflight_collision_interlock_callbacks_missing")
        physical_open_state = read_open_state()
        if not isinstance(physical_open_state, Mapping):
            raise RuntimeError("trajectory_preflight_calibration_body_not_physically_open")
        positions = _finite_array(
            physical_open_state.get("joint_positions_m"), (2,)
        )
        upper = _finite_array(physical_open_state.get("upper_limits_m"), (2,))
        tolerance = _optional_nonnegative(
            physical_open_state.get("position_tolerance_m")
        )
        if (
            positions is None
            or upper is None
            or tolerance is None
            or tolerance <= 0.0
            or np.any(np.abs(positions - upper) > tolerance + 1.0e-12)
        ):
            raise RuntimeError("trajectory_preflight_calibration_body_not_physically_open")
    collision_attribute.Set(bool(enabled))
    app.update()
    after_toggle_update = int(world.current_time_step_index)
    if after_toggle_update != before:
        raise RuntimeError("trajectory_preflight_collision_update_advanced_physics")
    collision_after = bool(collision_attribute.Get())
    if collision_after != bool(enabled):
        raise RuntimeError("trajectory_preflight_calibration_collision_toggle_failed")
    if enabled:
        post_enable_budget = read_post_enable_clearance_budget()
        if (
            not validate_remote_calibration_clearance_budget(post_enable_budget)
            or post_enable_budget != pre_enable_clearance_budget
        ):
            collision_attribute.Set(False)
            app.update()
            if int(world.current_time_step_index) != before:
                raise RuntimeError(
                    "trajectory_preflight_failed_budget_disable_advanced_physics"
                )
            play()
            return {
                "timeline_was_playing": timeline_was_playing,
                "physics_step_before_pause": before,
                "physics_step_after_pause_update": after_pause_update,
                "physics_step_after_enable_update": after_toggle_update,
                "physics_step_after_resume": int(world.current_time_step_index),
                "first_enabled_physics_step": None,
                "collision_enabled_before": collision_before,
                "collision_enabled_after": False,
                "physical_open_state": physical_open_state,
                "pre_enable_clearance_budget": dict(
                    pre_enable_clearance_budget
                ),
                "post_enable_clearance_budget": (
                    dict(post_enable_budget)
                    if isinstance(post_enable_budget, Mapping)
                    else None
                ),
                "first_enabled_step_contacts": None,
                "failure_reason": (
                    "post_enable_calibration_clearance_budget_failed"
                ),
                "passed": False,
            }
    play()
    after_resume = int(world.current_time_step_index)
    if after_resume != before:
        raise RuntimeError("trajectory_preflight_collision_resume_advanced_physics")
    first_enabled_step = None
    first_enabled_contacts = None
    if enabled:
        world.step(render=False)
        first_enabled_step = int(world.current_time_step_index)
        if first_enabled_step != before + 1:
            raise RuntimeError("trajectory_preflight_first_enabled_step_invalid")
        first_enabled_contacts = observe_first_enabled_step(first_enabled_step)
        if not isinstance(first_enabled_contacts, Sequence):
            raise RuntimeError("trajectory_preflight_first_enabled_contacts_invalid")
    evidence = {
        "timeline_was_playing": timeline_was_playing,
        "physics_step_before_pause": before,
        "physics_step_after_pause_update": after_pause_update,
        "physics_step_after_enable_update": after_toggle_update,
        "physics_step_after_resume": after_resume,
        "first_enabled_physics_step": first_enabled_step,
        "collision_enabled_before": collision_before,
        "collision_enabled_after": collision_after,
        "physical_open_state": physical_open_state,
        "pre_enable_clearance_budget": (
            dict(pre_enable_clearance_budget) if enabled else None
        ),
        "post_enable_clearance_budget": post_enable_budget,
        "first_enabled_step_contacts": first_enabled_contacts,
        "failure_reason": None,
    }
    evidence["passed"] = (
        validate_collision_interlock_evidence(evidence) if enabled else True
    )
    if enabled and not evidence["passed"]:
        raise RuntimeError("trajectory_preflight_calibration_collision_interlock_invalid")
    return evidence


def _session_sha256(stage: Any) -> str:
    session = stage.GetSessionLayer()
    text = session.ExportToString()
    if not isinstance(text, str) or not text:
        raise RuntimeError("trajectory_preflight_session_layer_unavailable")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _runtime_error_report(
    exc: BaseException,
    *,
    run_id: str,
    run_identity_sha256: str,
    phase: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "runtime_error_pending_application_close",
        "shutdown_status": "pending",
        "measurement_decision": RUNTIME_ERROR_DECISION,
        "runtime_identity": {
            "pid": os.getpid(),
            "run_id": run_id,
            "run_identity_sha256": run_identity_sha256,
        },
        "config_path": str(DEFAULT_CONFIG.resolve()),
        "config_sha256": EXPECTED_CONFIG_SHA256,
        "asset_path": str(ASSET_PATH.resolve()),
        "asset_sha256": EXPECTED_ASSET_SHA256,
        "robot_path": str(ROBOT_PATH.resolve()),
        "robot_sha256": EXPECTED_ROBOT_SHA256,
        "fatal_error": {
            "phase": phase,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
    }


def _measurement_no_go_report(
    exc: MeasurementNoGo,
    *,
    run_id: str,
    run_identity_sha256: str,
) -> dict[str, Any]:
    abort_payload = {
        "authority": "preinteraction_measurement_abort_v1",
        "reason": exc.reason,
        "interaction_prevented": True,
        "collision_enabled_physics_step_count": 0,
        "evidence": exc.evidence,
    }
    measurement_abort = {
        **abort_payload,
        "evidence_sha256": canonical_json_sha256(abort_payload),
    }
    report = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "measurement_decision": NO_GO_DECISION,
        "runtime_identity": {
            "pid": os.getpid(),
            "run_id": run_id,
            "run_identity_sha256": run_identity_sha256,
        },
        "config_path": str(DEFAULT_CONFIG.resolve()),
        "config_sha256": EXPECTED_CONFIG_SHA256,
        "asset_path": str(ASSET_PATH.resolve()),
        "asset_sha256": EXPECTED_ASSET_SHA256,
        "robot_path": str(ROBOT_PATH.resolve()),
        "robot_sha256": EXPECTED_ROBOT_SHA256,
        "measurement_abort": measurement_abort,
    }
    report["child_evaluation"] = evaluate_runtime_measurements(report)
    return report


def _persist_provisional_before_shutdown(
    *, app: Any, output_path: Path, report: Mapping[str, Any]
) -> None:
    try:
        atomic_create_json(output_path, report)
    finally:
        if app is not None:
            app.close()


def _measure_isaac_runtime(app: Any, args: argparse.Namespace) -> dict[str, Any]:
    import yaml

    from isaacsim_compat import install_legacy_isaacsim_aliases

    install_legacy_isaacsim_aliases()
    import omni.physx
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.utils.stage import add_reference_to_stage, get_stage_units
    from omegaconf import OmegaConf
    from pxr import PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics

    from controllers.atomic_actions.contact_pick_controller import (
        ContactPickController,
    )
    from factories.robot_factory import create_robot
    from factories.task_factory import create_task
    from robots.franka.rmpflow_controller import RMPFlowController
    from tools.labutopia_fluid import run_contact_grasp_feasibility_probe as feasibility
    from utils.isaac_fluid_evaluation import (
        SourceBodyWriterAudit,
        configure_contact_grasp_scene,
        configure_fluid_world_timing,
        configure_particle_usd_readback,
        construct_single_rigid_prim,
        resolve_enabled_rigid_body_path,
    )
    from utils.object_utils import ObjectUtils

    phase = "config_load"
    config_data = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if not isinstance(config_data, Mapping) or not isinstance(
        config_data.get("online_fluid"), Mapping
    ):
        raise ValueError("trajectory_preflight_config_invalid")
    cfg = OmegaConf.create(config_data)
    fluid = cfg.online_fluid
    if sha256_file(args.config) != EXPECTED_CONFIG_SHA256:
        raise ValueError("trajectory_preflight_runtime_config_hash_mismatch")

    phase = "stage_setup"
    configure_particle_usd_readback()
    stage = omni.usd.get_context().get_stage()
    add_reference_to_stage(usd_path=str(ASSET_PATH), prim_path="/World")
    previous_target = stage.GetEditTarget()
    session = stage.GetSessionLayer()
    stage.SetEditTarget(session)
    mutation_ledger = []
    try:
        particle_path = str(fluid.particle_path)
        particle = stage.GetPrimAtPath(particle_path)
        if not particle or not particle.IsValid():
            raise RuntimeError(f"trajectory_preflight_particle_missing:{particle_path}")
        particle.SetActive(False)
        mutation_ledger.append(
            {"phase": "pre_world", "operation": "set_active", "path": particle_path, "value": False}
        )
    finally:
        stage.SetEditTarget(previous_target)

    physics_dt = float(fluid.physics_dt)
    control_dt = float(fluid.rendering_dt)
    substeps = int(fluid.physics_substeps_per_observation)
    if (
        not math.isclose(physics_dt, 1.0 / 600.0, rel_tol=0.0, abs_tol=1.0e-15)
        or not math.isclose(control_dt, 1.0 / 30.0, rel_tol=0.0, abs_tol=1.0e-15)
        or substeps != 20
    ):
        raise ValueError("trajectory_preflight_cadence_invalid")

    phase = "world_setup"
    world = World(
        physics_dt=physics_dt,
        rendering_dt=control_dt,
        stage_units_in_meters=1.0,
        physics_prim_path=str(fluid.physics_scene_path),
        set_defaults=False,
        backend="numpy",
        device="cpu",
    )
    omni.physx.get_physx_interface().overwrite_gpu_setting(1)
    robot = create_robot(
        str(cfg.robot.type),
        position=np.asarray(cfg.robot.position, dtype=np.float64),
        usd_path=str(ROBOT_PATH),
        camera_frequency=int(cfg.robot.camera_frequency),
    )
    previous_target = stage.GetEditTarget()
    stage.SetEditTarget(session)
    try:
        scene_record = configure_contact_grasp_scene(stage, fluid)
    finally:
        stage.SetEditTarget(previous_target)
    object_utils = ObjectUtils.get_instance(stage)
    task = create_task(
        str(cfg.task_type), cfg=cfg, world=world, stage=stage, robot=robot
    )
    task.reset()
    configure_fluid_world_timing(
        world, physics_dt=physics_dt, rendering_dt=control_dt
    )
    stage_units = float(get_stage_units())
    if not math.isfinite(stage_units) or stage_units <= 0.0:
        raise RuntimeError("trajectory_preflight_stage_units_invalid")
    finger_indices = robot.validate_gripper_dof_contract(
        tuple(int(value) for value in fluid.finger_joint_indices)
    )
    reset_positions = np.asarray(robot.get_joint_positions(), dtype=np.float64)
    if reset_positions.shape != (9,) or not np.isfinite(reset_positions).all():
        raise RuntimeError("trajectory_preflight_reset_pose_invalid")
    reset_positions = reset_positions.copy()
    reset_positions[list(finger_indices)] *= stage_units
    reset_payload = {
        "authority": "post_task_reset_pre_session_mutation_v1",
        "joint_positions": reset_positions.tolist(),
        "joint_position_units": ["rad"] * 7 + ["m", "m"],
    }
    authoritative_reset_record = {
        **reset_payload,
        "record_sha256": canonical_json_sha256(reset_payload),
    }
    pre_measurement_stage_inventory = _stage_constraint_inventory(stage)

    phase = "cooked_geometry_query"
    source_catalog = _catalog_with_contact_offset_authority(
        stage,
        feasibility._query_cooked_colliders(
            app, stage, str(fluid.source_actor_path)
        ),
        read_offset=feasibility._configured_contact_offset,
    )
    finger_catalogs = {
        side: _catalog_with_contact_offset_authority(
            stage,
            feasibility._query_cooked_colliders(
                app, stage, EXPECTED_FINGER_BODY_PATHS[side]
            ),
            read_offset=feasibility._configured_contact_offset,
        )
        for side in SIDES
    }
    hand_catalog = _catalog_with_contact_offset_authority(
        stage,
        feasibility._query_cooked_colliders(
            app, stage, "/World/Franka/panda_hand"
        ),
        read_offset=feasibility._configured_contact_offset,
    )
    table_path = str(fluid.table_path)
    if table_path != EXPECTED_TABLE_BODY_PATH:
        raise RuntimeError("trajectory_preflight_table_path_invalid")
    table_catalog = validate_static_cooked_catalog(
        _catalog_with_contact_offset_authority(
            stage,
            _query_static_cooked_colliders(
                app,
                stage,
                table_path,
                query_colliders=feasibility._query_cooked_colliders,
            ),
            read_offset=feasibility._configured_contact_offset,
        ),
        expected_body_path=table_path,
    )
    excluded_robot_bodies = {
        *EXPECTED_FINGER_BODY_PATHS.values(),
        "/World/Franka/panda_hand",
    }
    robot_catalogs = {
        EXPECTED_FINGER_BODY_PATHS["left"]: finger_catalogs["left"],
        EXPECTED_FINGER_BODY_PATHS["right"]: finger_catalogs["right"],
        "/World/Franka/panda_hand": hand_catalog,
    }
    robot_root = stage.GetPrimAtPath("/World/Franka")
    if not robot_root or not robot_root.IsValid():
        raise RuntimeError("trajectory_preflight_robot_root_missing")
    all_robot_rigid_body_paths = sorted(
        str(prim.GetPath())
        for prim in Usd.PrimRange(robot_root)
        if prim.HasAPI(UsdPhysics.RigidBodyAPI)
    )
    colliderless_robot_bodies = {}
    for path in all_robot_rigid_body_paths:
        if path in excluded_robot_bodies:
            continue
        raw_catalog = feasibility._query_cooked_colliders(app, stage, path)
        raw_colliders = raw_catalog.get("colliders")
        if (
            isinstance(raw_colliders, Sequence)
            and not isinstance(raw_colliders, (str, bytes))
            and len(raw_colliders) == 0
        ):
            colliderless_robot_bodies[path] = build_colliderless_rigid_body_evidence(
                raw_catalog, expected_body_path=path
            )
            continue
        robot_catalogs[path] = _catalog_with_contact_offset_authority(
            stage,
            raw_catalog,
            read_offset=feasibility._configured_contact_offset,
        )
    if tuple(sorted(colliderless_robot_bodies)) != EXPECTED_COLLIDERLESS_ROBOT_BODY_PATHS:
        raise RuntimeError("trajectory_preflight_colliderless_robot_inventory_invalid")
    robot_rigid_body_paths = sorted(robot_catalogs)
    if sorted([*robot_rigid_body_paths, *colliderless_robot_bodies]) != all_robot_rigid_body_paths:
        raise RuntimeError("trajectory_preflight_robot_inventory_partition_invalid")
    robot_collider_inventory = {
        path: [str(collider["path"]) for collider in catalog["colliders"]]
        for path, catalog in sorted(robot_catalogs.items())
    }
    robot_inventory_payload = {
        "robot_rigid_body_paths": robot_rigid_body_paths,
        "colliderless_robot_bodies": colliderless_robot_bodies,
        "all_robot_rigid_body_paths": all_robot_rigid_body_paths,
        "robot_collider_inventory": robot_collider_inventory,
    }
    robot_inventory_sha256 = canonical_json_sha256(robot_inventory_payload)
    unrelated_robot_paths = sorted(
        set(robot_rigid_body_paths)
        - {
            *EXPECTED_FINGER_BODY_PATHS.values(),
            "/World/Franka/panda_hand",
        }
    )
    if not unrelated_robot_paths:
        raise RuntimeError("trajectory_preflight_unrelated_robot_catalogs_missing")
    unrelated_catalogs = [robot_catalogs[path] for path in unrelated_robot_paths]
    source_offset_values = [
        collider["contact_offset"]["contact_offset_m"]
        for collider in source_catalog["colliders"]
    ]
    source_contact_offset = (
        max(float(value) for value in source_offset_values)
        if all(value is not None for value in source_offset_values)
        else None
    )
    source_path = str(fluid.source_actor_path)
    fixed_source_world_matrix = _row_matrix(stage, source_path).tolist()
    source_isolation_snapshots: list[dict[str, Any]] = []

    def record_source_isolation(checkpoint: str) -> dict[str, Any]:
        snapshot = require_source_isolation_snapshot(
            _read_source_isolation_snapshot(
                stage,
                checkpoint=checkpoint,
                source_body_path=source_path,
                robot_rigid_body_paths=all_robot_rigid_body_paths,
                expected_source_world_matrix=fixed_source_world_matrix,
            )
        )
        source_isolation_snapshots.append(snapshot)
        return snapshot

    pre_attachment = evaluate_attachment_inventory(
        pre_inventory=pre_measurement_stage_inventory,
        post_inventory=pre_measurement_stage_inventory,
        source_body_path=source_path,
        robot_rigid_body_paths=all_robot_rigid_body_paths,
    )
    if not pre_attachment["passed"]:
        raise RuntimeError("trajectory_preflight_preexisting_attachment_invalid")

    phase = "diagnostic_session_authoring"
    world.stop()
    previous_target = stage.GetEditTarget()
    stage.SetEditTarget(session)
    calibration_spec = None
    calibration_collision = None
    source_filter_verified = False
    source_contact_reporting_disabled = False
    source_kinematic_verified = False
    try:
        source_prim = stage.GetPrimAtPath(source_path)
        if not source_prim or not source_prim.IsValid():
            raise RuntimeError("trajectory_preflight_source_missing")
        rigid = UsdPhysics.RigidBodyAPI(source_prim)
        if not rigid:
            raise RuntimeError("trajectory_preflight_source_rigid_body_required")
        rigid.CreateKinematicEnabledAttr().Set(True)
        mutation_ledger.append(
            {
                "phase": "pre_measurement",
                "operation": "set_kinematic_enabled",
                "path": source_path,
                "value": True,
                "purpose": "fixed_noninteracting_shadow_source",
            }
        )
        filtered = UsdPhysics.FilteredPairsAPI.Apply(source_prim)
        observed_robot_body_paths = sorted(
            str(prim.GetPath())
            for prim in Usd.PrimRange(robot_root)
            if prim.HasAPI(UsdPhysics.RigidBodyAPI)
        )
        if observed_robot_body_paths != all_robot_rigid_body_paths:
            raise RuntimeError("trajectory_preflight_robot_inventory_mismatch")
        filtered_relationship = filtered.CreateFilteredPairsRel()
        filtered_relationship.SetTargets(
            [Sdf.Path(path) for path in all_robot_rigid_body_paths]
        )
        source_filter_verified = [
            str(path) for path in filtered_relationship.GetTargets()
        ] == all_robot_rigid_body_paths
        mutation_ledger.append(
            {
                "phase": "pre_measurement",
                "operation": "filter_collision_pairs",
                "path": str(fluid.source_actor_path),
                "targets": all_robot_rigid_body_paths,
                "purpose": "disable_source_robot_collision_response",
            }
        )
        try:
            if source_prim.HasAPI(PhysxSchema.PhysxContactReportAPI):
                source_prim.RemoveAPI(PhysxSchema.PhysxContactReportAPI)
        except (TypeError, RuntimeError):
            pass
        threshold = source_prim.GetAttribute("physxContactReport:threshold")
        if not threshold:
            threshold = source_prim.CreateAttribute(
                "physxContactReport:threshold", Sdf.ValueTypeNames.Float, custom=False
            )
        threshold.Set(float(np.finfo(np.float32).max))
        source_contact_reporting_disabled = bool(
            float(threshold.Get()) == float(np.finfo(np.float32).max)
        )
        source_kinematic_verified = bool(rigid.GetKinematicEnabledAttr().Get())
        mutation_ledger.append(
            {
                "phase": "pre_measurement",
                "operation": "disable_contact_reporting",
                "path": str(fluid.source_actor_path),
                "threshold": float(np.finfo(np.float32).max),
            }
        )
        tool_reset_matrix = _row_matrix(stage, str(fluid.grasp_frame_path))
        calibration_opening_axis_world = derive_opening_axis_world(
            tool_reset_matrix
        )
        body_size = [
            float(value)
            for value in fluid.trajectory_preflight_calibration_body_size_m
        ]
        body_contact_offset = float(
            fluid.trajectory_preflight_calibration_body_contact_offset_m
        )
        calibration_spec, calibration_collision = _author_calibration_body(
            stage,
            world_matrix=tool_reset_matrix,
            opening_axis_world=calibration_opening_axis_world,
            size_m=body_size,
            contact_offset_m=body_contact_offset,
        )
        mutation_ledger.append(
            {
                "phase": "pre_measurement",
                "operation": "define_static_calibration_body",
                "spec_sha256": canonical_json_sha256(calibration_spec),
                "initial_collision_enabled": False,
            }
        )
    finally:
        stage.SetEditTarget(previous_target)
    if calibration_spec is None or calibration_collision is None:
        raise RuntimeError("trajectory_preflight_calibration_body_authoring_failed")
    record_source_isolation("post_task_reset_1")
    task.reset()
    configure_fluid_world_timing(
        world, physics_dt=physics_dt, rendering_dt=control_dt
    )
    previous_target = stage.GetEditTarget()
    stage.SetEditTarget(session)
    try:
        _author_source_isolation(
            stage,
            source_body_path=source_path,
            robot_rigid_body_paths=all_robot_rigid_body_paths,
        )
    finally:
        stage.SetEditTarget(previous_target)
    record_source_isolation("post_task_reset_2")
    reset_after = np.asarray(robot.get_joint_positions(), dtype=np.float64)
    if reset_after.shape != (9,) or not np.isfinite(reset_after).all():
        raise RuntimeError("trajectory_preflight_post_override_reset_pose_invalid")
    reset_after = reset_after.copy()
    reset_after[list(finger_indices)] *= stage_units
    if not np.array_equal(reset_after, reset_positions):
        raise RuntimeError("trajectory_preflight_authoritative_reset_drift")
    robot.initialize_contact_sensors(physics_dt)

    source_body = construct_single_rigid_prim(
        SingleRigidPrim,
        prim_path=str(fluid.source_actor_path),
        name="trajectory_preflight_source",
    )
    source_body.initialize()
    writer_audit = SourceBodyWriterAudit(
        source_body_path=str(fluid.source_actor_path)
    )
    writer_audit.install(source_body=source_body, object_utils=object_utils)
    writer_audit.reset()
    record_source_isolation("pre_world_play")
    world.play()
    app.update()

    phase = "remote_clearance"
    calibration_bounds = _box_world_bounds(
        size_m=calibration_spec["size_m"], world_matrix=tool_reset_matrix
    )
    remote_clearance = {
        "calibration_body_to_source": _aabb_distance(
            calibration_bounds, _catalog_bounds(stage, source_catalog)
        ),
        "calibration_body_to_table": _aabb_distance(
            calibration_bounds, _catalog_bounds(stage, table_catalog)
        ),
        "calibration_body_to_unrelated_robot_links": min(
            _aabb_distance(calibration_bounds, _catalog_bounds(stage, catalog))
            for catalog in [hand_catalog, *unrelated_catalogs]
        ),
    }

    phase = "pre_roll"
    record_source_isolation("pre_roll")
    for _ in range(int(fluid.dynamic_pre_roll_steps)):
        world.step(render=False)

    phase = "free_aperture_calibration"
    velocity_samples: list[dict[str, Any]] = []
    aperture_points = []
    remote_unexpected_contacts: list[dict[str, Any]] = []
    remote_contact_keys = set()
    calibration_finger_colliders = {
        path
        for body_path in EXPECTED_FINGER_BODY_PATHS.values()
        for path in scene_record["finger_collider_paths"][body_path]
    }

    def resolve_contact_body(path: str) -> str:
        if path == CALIBRATION_BODY_PATH or path.startswith(
            CALIBRATION_BODY_PATH + "/"
        ):
            return CALIBRATION_BODY_PATH
        return resolve_enabled_rigid_body_path(stage, path)

    def observe_remote_contacts(*, allow_calibration_body: bool) -> list[dict[str, Any]]:
        frames = robot.read_contact_sensor_frames()
        physics_step = int(world.current_time_step_index)
        contacts = _raw_contact_records(
            frames,
            physics_step=physics_step,
            resolve_body_path=resolve_contact_body,
        )
        for contact in contacts:
            body_pair = {contact["body0_path"], contact["body1_path"]}
            collider_pair = {
                contact["collider0_path"], contact["collider1_path"]
            }
            valid_calibration = bool(
                allow_calibration_body
                and CALIBRATION_BODY_PATH in body_pair
                and CALIBRATION_BODY_PATH in collider_pair
                and len(body_pair - {CALIBRATION_BODY_PATH}) == 1
                and next(iter(body_pair - {CALIBRATION_BODY_PATH}))
                in EXPECTED_FINGER_BODY_PATHS.values()
                and len(collider_pair - {CALIBRATION_BODY_PATH}) == 1
                and next(iter(collider_pair - {CALIBRATION_BODY_PATH}))
                in calibration_finger_colliders
            )
            if valid_calibration:
                continue
            key = canonical_json_sha256(contact)
            if key in remote_contact_keys:
                continue
            remote_contact_keys.add(key)
            remote_unexpected_contacts.append(dict(contact))
        return contacts

    lower_limits, upper_limits = _joint_limits_m(
        robot, finger_indices, stage_units
    )
    requested_open_target = float(
        fluid.trajectory_preflight_requested_open_target_m
    )
    preliminary_open_authority = validate_physical_open_authority(
        upper_limits_m=upper_limits,
        requested_open_target_m=requested_open_target,
    )
    open_target = float(
        preliminary_open_authority["canonical_open_target_m"]
    )
    close_speed = float(fluid.trajectory_preflight_remote_close_speed_m_s)
    settle_duration = float(
        fluid.trajectory_preflight_calibration_settle_duration_s
    )
    requested_targets = [
        float(value) for value in fluid.trajectory_preflight_calibration_points_m
    ]
    for target_index, requested_target in enumerate(requested_targets):
        commanded_target = open_target if target_index == 0 else requested_target
        drive_measurement = _drive_fingers(
            world=world,
            robot=robot,
            finger_indices=finger_indices,
            target_m=commanded_target,
            speed_m_s=close_speed,
            physics_dt=physics_dt,
            control_dt=control_dt,
            substeps=substeps,
            stage_units=stage_units,
            velocity_samples=velocity_samples,
            physics_callback=lambda: observe_remote_contacts(
                allow_calibration_body=False
            ),
            settle_duration_s=settle_duration,
        )
        settle_samples = drive_measurement["settle_samples"]
        if not settle_samples:
            raise RuntimeError("trajectory_preflight_settle_samples_missing")
        final_sample = settle_samples[-1]
        gap = _projected_finger_gap(
            stage,
            fingers=finger_catalogs,
            opening_axis_world=calibration_opening_axis_world,
        )
        aperture_points.append(
            {
                "target_m": requested_target,
                "commanded_target_m": commanded_target,
                "joint_positions_m": list(final_sample["joint_positions_m"]),
                "cooked_inner_gap_m": float(gap["open_inner_gap_m"]),
                "lower_limits_m": lower_limits.tolist(),
                "upper_limits_m": upper_limits.tolist(),
                "settled_duration_s": settle_duration,
                "measured_settling_time_s": drive_measurement[
                    "measured_settling_time_s"
                ],
                "drive_physics_step_count": drive_measurement[
                    "physics_step_count"
                ],
                "settled_api_velocity_m_s": list(
                    final_sample["api_pad_velocity_m_s"]
                ),
                "settled_finite_difference_velocity_m_s": list(
                    final_sample["finite_difference_pad_velocity_m_s"]
                ),
                "settle_samples": settle_samples,
            }
        )
    open_authority = derive_measured_open_contract(
        points=aperture_points,
        velocity_samples=velocity_samples,
        requested_open_target_m=requested_open_target,
        physics_dt=physics_dt,
    )
    open_position_tolerance = float(
        open_authority["open_position_tolerance_m"]
    )
    _drive_fingers(
        world=world,
        robot=robot,
        finger_indices=finger_indices,
        target_m=open_target,
        speed_m_s=close_speed,
        physics_dt=physics_dt,
        control_dt=control_dt,
        substeps=substeps,
        stage_units=stage_units,
        velocity_samples=None,
        physics_callback=lambda: observe_remote_contacts(
            allow_calibration_body=False
        ),
        settle_duration_s=settle_duration,
    )
    pre_enable_source_isolation = require_source_isolation_snapshot(
        _read_source_isolation_snapshot(
            stage,
            checkpoint="pre_calibration_enable",
            source_body_path=source_path,
            robot_rigid_body_paths=all_robot_rigid_body_paths,
            expected_source_world_matrix=fixed_source_world_matrix,
        )
    )
    calibration_obstacle_catalogs = {
        str(source_catalog["body_path"]): source_catalog,
        str(table_catalog["body_path"]): table_catalog,
        "/World/Franka/panda_hand": hand_catalog,
        **{path: robot_catalogs[path] for path in unrelated_robot_paths},
    }

    def read_calibration_budget() -> dict[str, Any]:
        return _remote_calibration_clearance_budget(
            stage,
            calibration_spec=calibration_spec,
            obstacle_catalogs=calibration_obstacle_catalogs,
            finger_gap_evidence=_projected_finger_gap(
                stage,
                fingers=finger_catalogs,
                opening_axis_world=calibration_opening_axis_world,
            ),
            numerical_margin_m=float(
                fluid.trajectory_preflight_numerical_margin_m
            ),
        )

    pre_enable_clearance_budget = read_calibration_budget()

    phase = "contact_onset_calibration"
    first_contacts: dict[str, Any] = {"left": None, "right": None}
    contact_onset_brackets: dict[str, Any] = {"left": None, "right": None}
    previous_no_contact: dict[str, Any] = {"left": None, "right": None}
    attribution_ambiguous = False

    def observe_calibration_contacts(
        expected_physics_step: int | None = None,
    ) -> list[dict[str, Any]]:
        nonlocal attribution_ambiguous
        physics_step = int(world.current_time_step_index)
        if expected_physics_step is not None and physics_step != expected_physics_step:
            raise RuntimeError("trajectory_preflight_calibration_step_binding_invalid")
        contacts = observe_remote_contacts(allow_calibration_body=True)
        gap = _projected_finger_gap(
            stage,
            fingers=finger_catalogs,
            opening_axis_world=calibration_opening_axis_world,
        )
        for side in SIDES:
            if first_contacts[side] is not None:
                continue
            candidates = []
            normalized_side_contacts = []
            for contact in contacts:
                body_pair = {contact["body0_path"], contact["body1_path"]}
                collider_pair = {
                    contact["collider0_path"], contact["collider1_path"]
                }
                if body_pair != {
                    CALIBRATION_BODY_PATH,
                    EXPECTED_FINGER_BODY_PATHS[side],
                }:
                    continue
                normalized_side_contacts.append(dict(contact))
                finger_paths = collider_pair.intersection(
                    set(
                        scene_record["finger_collider_paths"][
                            EXPECTED_FINGER_BODY_PATHS[side]
                        ]
                    )
                )
                if (
                    CALIBRATION_BODY_PATH not in collider_pair
                    or len(finger_paths) != 1
                    or contact.get("sensor_names") != [side]
                ):
                    attribution_ambiguous = True
                    continue
                candidates.append(next(iter(finger_paths)))
            if len(candidates) > 1:
                attribution_ambiguous = True
            elif len(candidates) == 1:
                previous = previous_no_contact[side]
                if (
                    not isinstance(previous, Mapping)
                    or previous.get("physics_step") != physics_step - 1
                ):
                    attribution_ambiguous = True
                    continue
                first_contacts[side] = {
                    "physics_step": physics_step,
                    "finger_body_path": EXPECTED_FINGER_BODY_PATHS[side],
                    "finger_collider_path": candidates[0],
                    "calibration_collider_path": CALIBRATION_BODY_PATH,
                    "sensor_names": [side],
                    "resolved_contact_count": 1,
                }
                contact_onset_brackets[side] = {
                    "previous_no_contact": dict(previous),
                    "first_contact": {
                        "physics_step": physics_step,
                        "inner_gap_m": float(gap["open_inner_gap_m"]),
                        "finger_collider_world_matrices": gap[
                            "finger_collider_world_matrices"
                        ],
                        "gap_error_bound": gap["gap_error_bound"],
                    },
                }
            else:
                zero_contact_evidence = {
                    "physics_step": physics_step,
                    "normalized_contacts": normalized_side_contacts,
                }
                previous_no_contact[side] = {
                    "physics_step": physics_step,
                    "inner_gap_m": float(gap["open_inner_gap_m"]),
                    "finger_collider_world_matrices": gap[
                        "finger_collider_world_matrices"
                    ],
                    "gap_error_bound": gap["gap_error_bound"],
                    "normalized_contact_evidence": zero_contact_evidence,
                    "normalized_contact_evidence_sha256": canonical_json_sha256(
                        zero_contact_evidence
                    ),
                }
        return contacts

    collision_interlock = _set_calibration_collision(
        app=app,
        world=world,
        collision_attribute=calibration_collision,
        enabled=True,
        read_open_state=lambda: {
            "joint_positions_m": (
                np.asarray(robot.get_joint_positions(), dtype=np.float64)[
                    list(finger_indices)
                ]
                * stage_units
            ).tolist(),
            "upper_limits_m": upper_limits.tolist(),
            "position_tolerance_m": open_position_tolerance,
        },
        observe_first_enabled_step=observe_calibration_contacts,
        pre_enable_clearance_budget=pre_enable_clearance_budget,
        read_post_enable_clearance_budget=read_calibration_budget,
    )
    if not collision_interlock.get("passed"):
        raise MeasurementNoGo(
            str(collision_interlock.get("failure_reason")),
            collision_interlock,
        )

    _drive_fingers(
        world=world,
        robot=robot,
        finger_indices=finger_indices,
        target_m=requested_targets[-1],
        speed_m_s=close_speed,
        physics_dt=physics_dt,
        control_dt=control_dt,
        substeps=substeps,
        stage_units=stage_units,
        velocity_samples=None,
        physics_callback=observe_calibration_contacts,
        settle_duration_s=settle_duration,
    )
    _drive_fingers(
        world=world,
        robot=robot,
        finger_indices=finger_indices,
        target_m=open_target,
        speed_m_s=close_speed,
        physics_dt=physics_dt,
        control_dt=control_dt,
        substeps=substeps,
        stage_units=stage_units,
        velocity_samples=None,
        physics_callback=lambda: observe_remote_contacts(
            allow_calibration_body=True
        ),
        settle_duration_s=settle_duration,
    )
    _set_calibration_collision(
        app=app, world=world, collision_attribute=calibration_collision, enabled=False
    )

    phase = "shadow_controller_setup"
    rmpflow = RMPFlowController(
        name="geometry_aware_trajectory_preflight_rmpflow",
        robot_articulation=robot,
        physics_dt=control_dt,
        use_default_config=False,
    )
    controller = ContactPickController(
        name="geometry_aware_trajectory_preflight_contact_pick",
        cspace_controller=rmpflow,
        control_dt=control_dt,
        position_threshold=float(fluid.trajectory_preflight_position_threshold_m),
        open_position=open_target,
        open_position_tolerance=open_position_tolerance,
        pregrasp_distance=float(fluid.expert_pick_pregrasp_distance_m),
        insert_distance=float(fluid.expert_pick_insert_distance_m),
        approach_speed=float(fluid.expert_pick_approach_speed_m_s),
        close_speed=float(fluid.expert_pick_close_speed_m_s),
        settle_duration=float(fluid.expert_pick_settle_duration_s),
        contact_settle_duration=float(fluid.expert_pick_contact_settle_duration_s),
        orientation_threshold_degrees=float(
            fluid.trajectory_preflight_orientation_threshold_degrees
        ),
        control_to_end_effector_matrix_m=np.asarray(
            fluid.rmpflow_control_to_grasp_matrix_m, dtype=np.float64
        ),
        end_effector_frame=str(fluid.grasp_target_frame_name),
        control_frame=str(fluid.rmpflow_control_frame_name),
        finger_joint_indices=finger_indices,
        terminate_after_contact_settle=True,
    )
    source_center = np.asarray(
        task.object_utils.get_geometry_center(object_path=str(fluid.source_actor_path)),
        dtype=np.float64,
    )
    source_orientation_xyzw = np.asarray(
        task.object_utils.get_world_transform_quat(
            object_path=str(fluid.source_actor_path)
        ),
        dtype=np.float64,
    )
    if (
        source_center.shape != (3,)
        or source_orientation_xyzw.shape != (4,)
        or not np.isfinite(source_center).all()
        or not np.isfinite(source_orientation_xyzw).all()
    ):
        raise RuntimeError("trajectory_preflight_frozen_source_frame_invalid")
    record_source_isolation("pre_first_shadow_action")

    phase = "shadow_sweep"
    shadow_opening_axis_world = derive_opening_axis_from_orientation_wxyz(
        [float(value) for value in fluid.expert_pick_target_orientation_wxyz]
    )
    trace: list[dict[str, Any]] = []
    trace_physics_step_origin = None
    finger_edge_radii = {"left": 0.0, "right": 0.0}
    maximum_control_actions = 1000
    shadow_control_timeout = False
    for control_index in range(maximum_control_actions):
        event_name = controller.current_event.name
        if event_name == "CLOSE":
            break
        if event_name in {"CONTACT_SETTLE", "LIFT", "HOLD"}:
            raise RuntimeError(f"trajectory_preflight_prohibited_controller_phase:{event_name}")
        joints = np.asarray(robot.get_joint_positions(), dtype=np.float64)
        tool_matrix = _row_matrix(stage, str(fluid.grasp_frame_path))
        tool_pose = _matrix_pose_wxyz(tool_matrix)
        action = controller.forward(
            source_position=source_center,
            source_orientation_xyzw=source_orientation_xyzw,
            current_joint_positions=joints,
            gripper_position=np.asarray(tool_pose["position_m"], dtype=np.float64),
            end_effector_orientation=np.asarray(
                fluid.expert_pick_target_orientation_wxyz, dtype=np.float64
            ),
            current_end_effector_orientation=rmpflow.get_end_effector_orientation_wxyz(),
            approach_direction=np.asarray(
                fluid.expert_pick_approach_direction_world, dtype=np.float64
            ),
            grasp_offset=np.asarray(
                fluid.expert_pick_gripper_offset_object_m, dtype=np.float64
            ),
            lift_height=float(fluid.expert_pick_lift_height_m),
            gripper_distance=float(fluid.grasp_finger_joint_target_m),
            contact_qualified=False,
            contact_failure_reason=None,
        )
        action_evidence = controller.control_evidence()
        emitted_action_kind = action_evidence.get("last_emitted_action_kind")
        controller_invocation_index = action_evidence.get(
            "control_invocation_count"
        )
        if controller_invocation_index != control_index + 1:
            raise RuntimeError("trajectory_preflight_controller_index_mismatch")
        if event_name == "PREGRASP" and emitted_action_kind == "finger":
            action_kind = "GRIPPER_OPEN"
            commanded_position = np.asarray(
                controller._pregrasp_position, dtype=np.float64
            )
        elif event_name == "PREGRASP" and emitted_action_kind == "arm":
            action_kind = "ARM_PREGRASP"
            commanded_position = np.asarray(controller._pregrasp_position, dtype=np.float64)
        elif event_name == "ALIGN":
            action_kind = "ARM_ALIGN"
            commanded_position = np.asarray(controller._align_position, dtype=np.float64)
        elif event_name == "INSERT":
            action_kind = "ARM_INSERT"
            commanded_position = np.asarray(controller._insert_waypoint, dtype=np.float64)
        elif event_name == "SETTLE":
            action_kind = "ARM_SETTLE"
            commanded_position = np.asarray(controller._insert_target, dtype=np.float64)
        else:
            raise RuntimeError(f"trajectory_preflight_action_phase_unknown:{event_name}")
        if action_kind.startswith("ARM_"):
            action, payload = _exact_indexed_arm_action(action)
        else:
            payload = _action_payload(action)
            if not _action_payload_matches_kind(
                payload,
                action_kind,
                canonical_open_target_m=open_target,
            ):
                raise RuntimeError(
                    "trajectory_preflight_gripper_action_shape_invalid"
                )
        action_hash = canonical_action_hash(payload)
        robot.get_articulation_controller().apply_action(action)
        commanded_pose = {
            "position_m": commanded_position.tolist(),
            "orientation_wxyz": [
                float(value) for value in fluid.expert_pick_target_orientation_wxyz
            ],
        }
        commanded_control_pose = map_tool_target_to_control_pose(
            tool_pose=commanded_pose,
            control_to_tool_matrix_m=fluid.rmpflow_control_to_grasp_matrix_m,
            meters_per_stage_unit=stage_units,
        )
        for substep_index in range(substeps):
            world.step(render=False)
            trace_index = len(trace)
            current_world_time_s = float(world.current_time)
            if not math.isfinite(current_world_time_s):
                raise RuntimeError("trajectory_preflight_world_time_nonfinite")
            current_physics_step = int(world.current_time_step_index)
            if trace_physics_step_origin is None:
                trace_physics_step_origin = current_physics_step
            measured_tool_matrix = _row_matrix(stage, str(fluid.grasp_frame_path))
            measured_tool_pose = _matrix_pose_wxyz(measured_tool_matrix)
            rmpflow_pose = _rmpflow_pose_wxyz(rmpflow)
            collider_matrices = {
                "left_finger": _collider_transform_evidence(
                    stage, finger_catalogs["left"]
                ),
                "right_finger": _collider_transform_evidence(
                    stage, finger_catalogs["right"]
                ),
                "hand": _collider_transform_evidence(stage, hand_catalog),
            }
            geometry_world_matrices = {
                str(source_catalog["body_path"]): _collider_transform_evidence(
                    stage, source_catalog
                ),
                str(table_catalog["body_path"]): _collider_transform_evidence(
                    stage, table_catalog
                ),
                **{
                    path: _collider_transform_evidence(stage, catalog)
                    for path, catalog in robot_catalogs.items()
                },
            }
            for side in SIDES:
                finger_edge_radii[side] = max(
                    finger_edge_radii[side],
                    _catalog_edge_radius(
                        stage,
                        finger_catalogs[side],
                        measured_tool_pose["position_m"],
                    ),
                )
            geometric_clearance = _directional_finger_clearances(
                stage,
                source=source_catalog,
                fingers=finger_catalogs,
                opening_axis_world=shadow_opening_axis_world,
            )
            moving_catalogs = [
                robot_catalogs[path] for path in robot_rigid_body_paths
            ]
            environment_clearance = {
                "hand_to_source": _aabb_distance(
                    _catalog_bounds(stage, hand_catalog),
                    _catalog_bounds(stage, source_catalog),
                ),
                "swept_bodies_to_table": min(
                    _aabb_distance(
                        _catalog_bounds(stage, catalog),
                        _catalog_bounds(stage, table_catalog),
                    )
                    for catalog in moving_catalogs
                ),
                "source_to_unrelated_robot_links": _minimum_catalog_distance(
                    stage, source_catalog, unrelated_catalogs
                ),
            }
            current_joints = np.asarray(robot.get_joint_positions(), dtype=np.float64)
            current_velocities = np.asarray(robot.get_joint_velocities(), dtype=np.float64)
            current_source_center = np.asarray(
                task.object_utils.get_geometry_center(
                    object_path=str(fluid.source_actor_path)
                ),
                dtype=np.float64,
            )
            if (
                current_joints.shape != (9,)
                or current_velocities.shape != (9,)
                or current_source_center.shape != (3,)
                or not np.isfinite(current_joints).all()
                or not np.isfinite(current_velocities).all()
                or not np.isfinite(current_source_center).all()
            ):
                raise RuntimeError("trajectory_preflight_state_readback_invalid")
            joint_positions = current_joints.copy()
            joint_positions[list(finger_indices)] *= stage_units
            joint_velocities = current_velocities.copy()
            joint_velocities[list(finger_indices)] *= stage_units
            trace.append(
                {
                    "trace_index": trace_index,
                    "timestamp_s": (
                        current_physics_step - trace_physics_step_origin
                    )
                    * physics_dt,
                    "world_time_s": current_world_time_s,
                    "physics_step": current_physics_step,
                    "control_index": control_index,
                    "controller_invocation_index": controller_invocation_index,
                    "substep_index": substep_index,
                    "phase": event_name,
                    "action_kind": action_kind,
                    "action_payload": payload,
                    "action_sha256": action_hash,
                    "commanded_tool_pose": commanded_pose,
                    "measured_tool_pose": measured_tool_pose,
                    "commanded_control_pose": commanded_control_pose,
                    "measured_control_pose": rmpflow_pose,
                    "rmpflow_control_pose": rmpflow_pose,
                    "joint_positions_m": joint_positions.tolist(),
                    "joint_velocities_m_s": joint_velocities.tolist(),
                    "stage_units_in_meters": stage_units,
                    "joint_position_units": ["rad"] * 7 + ["m", "m"],
                    "joint_velocity_units": ["rad_s"] * 7
                    + ["m_s", "m_s"],
                    "collider_world_matrices": collider_matrices,
                    "geometry_world_matrices": geometry_world_matrices,
                    "source_center_world_m": current_source_center.tolist(),
                    "source_world_matrix": _row_matrix(
                        stage, str(fluid.source_actor_path)
                    ).tolist(),
                    "contacts": _raw_contact_records(
                        robot.read_contact_sensor_frames(),
                        physics_step=int(world.current_time_step_index),
                        resolve_body_path=resolve_contact_body,
                    ),
                    "geometric_clearance_m": geometric_clearance,
                    "environment_clearance_m": environment_clearance,
                }
            )
    else:
        shadow_control_timeout = True

    controller_evidence = controller.control_evidence()
    controller_evidence["align_position"] = (
        None
        if controller._align_position is None
        else controller._align_position.tolist()
    )
    controller_evidence["insert_waypoint"] = (
        None
        if controller._insert_waypoint is None
        else controller._insert_waypoint.tolist()
    )
    controller_evidence["shadow_control_timeout"] = shadow_control_timeout
    source_pose_fixed = bool(
        trace
        and all(
            record["source_center_world_m"] == trace[0]["source_center_world_m"]
            and record["source_world_matrix"] == trace[0]["source_world_matrix"]
            for record in trace
        )
    )
    post_measurement_stage_inventory = _stage_constraint_inventory(stage)
    attachment_events = []
    if post_measurement_stage_inventory != pre_measurement_stage_inventory:
        attachment_events.append(
            {
                "kind": "stage_constraint_inventory_changed",
                "pre_inventory_sha256": pre_measurement_stage_inventory[
                    "inventory_sha256"
                ],
                "post_inventory_sha256": post_measurement_stage_inventory[
                    "inventory_sha256"
                ],
            }
        )
    session_text = stage.GetSessionLayer().ExportToString()
    session_hash = _session_sha256(stage)
    runtime_contract = {
        "producer_schema": "geometry_aware_trajectory_preflight_runtime_v2",
        "profile": PROFILE,
        "physics_dt": physics_dt,
        "control_dt": control_dt,
        "physics_substeps_per_action": substeps,
        "pre_roll_steps": int(fluid.dynamic_pre_roll_steps),
        "particle_count": 0,
        "stage_units_in_meters": stage_units,
        "joint_position_units": ["rad"] * 7 + ["m", "m"],
        "joint_velocity_units": ["rad_s"] * 7 + ["m_s", "m_s"],
        "robot_rigid_body_paths": robot_rigid_body_paths,
        "colliderless_robot_bodies": colliderless_robot_bodies,
        "all_robot_rigid_body_paths": all_robot_rigid_body_paths,
        "robot_collider_inventory": robot_collider_inventory,
        "robot_inventory_sha256": robot_inventory_sha256,
        "pre_measurement_stage_inventory": pre_measurement_stage_inventory,
        "post_measurement_stage_inventory": post_measurement_stage_inventory,
        "rmpflow_runtime_data": dict(PINNED_RUNTIME_DATA_SHA256),
        "source_isolation_snapshots": source_isolation_snapshots,
        "particles_disabled": bool(
            not stage.GetPrimAtPath(str(fluid.particle_path)).IsActive()
        ),
        "source_robot_collision_filtered": source_filter_verified,
        "source_contact_reporting_disabled": source_contact_reporting_disabled,
        "source_pose_fixed": bool(source_kinematic_verified and source_pose_fixed),
        "diagnostic_session_layer_text": session_text,
        "diagnostic_session_layer_sha256": session_hash,
        "diagnostic_session_mutations": mutation_ledger,
        "authoritative_reset_record": authoritative_reset_record,
        "reset_joint_positions_after": reset_after.tolist(),
        "trajectory_inputs": {
            "tool_orientation_wxyz": [
                float(value) for value in fluid.expert_pick_target_orientation_wxyz
            ],
            "grasp_offset_object_m": [
                float(value) for value in fluid.expert_pick_gripper_offset_object_m
            ],
            "approach_direction_world": [
                float(value) for value in fluid.expert_pick_approach_direction_world
            ],
            "control_to_tool_center_matrix_m": [
                [float(value) for value in row]
                for row in fluid.rmpflow_control_to_grasp_matrix_m
            ],
            "pregrasp_distance_m": float(fluid.expert_pick_pregrasp_distance_m),
            "insert_distance_m": float(fluid.expert_pick_insert_distance_m),
            "insertion_speed_m_s": float(fluid.expert_pick_approach_speed_m_s),
            "remote_close_speed_m_s": close_speed,
            "settle_duration_s": float(fluid.expert_pick_settle_duration_s),
            "contact_settle_duration_s": float(
                fluid.expert_pick_contact_settle_duration_s
            ),
            "numerical_margin_m": float(
                fluid.trajectory_preflight_numerical_margin_m
            ),
            "requested_open_target_m": requested_open_target,
            "canonical_open_target_m": open_target,
            "physical_open_upper_limits_m": upper_limits.tolist(),
            "open_position_tolerance_m": open_position_tolerance,
            "position_threshold_m": float(
                fluid.trajectory_preflight_position_threshold_m
            ),
            "orientation_threshold_degrees": float(
                fluid.trajectory_preflight_orientation_threshold_degrees
            ),
        },
    }
    report = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "measurement_decision": NO_GO_DECISION,
        "runtime_identity": {
            "pid": os.getpid(),
            "run_id": args.run_id,
            "run_identity_sha256": args.run_identity_sha256,
        },
        "config_path": str(args.config),
        "config_sha256": sha256_file(args.config),
        "asset_path": str(ASSET_PATH),
        "asset_sha256": sha256_file(ASSET_PATH),
        "robot_path": str(ROBOT_PATH),
        "robot_sha256": sha256_file(ROBOT_PATH),
        "runtime_contract": runtime_contract,
        "calibration": {
            "body_spec": calibration_spec,
            "body_spec_sha256": canonical_json_sha256(calibration_spec),
            "aperture_points": aperture_points,
            "velocity_samples": velocity_samples,
            "contact_onset_brackets": contact_onset_brackets,
            "first_contacts": first_contacts,
            "finger_collider_paths": {
                side: list(
                    scene_record["finger_collider_paths"][
                        EXPECTED_FINGER_BODY_PATHS[side]
                    ]
                )
                for side in SIDES
            },
            "contact_attribution_ambiguous": attribution_ambiguous,
            "remote_clearance_m": remote_clearance,
            "remote_unexpected_contacts": remote_unexpected_contacts,
            "pre_enable_clearance_budget": pre_enable_clearance_budget,
            "post_enable_clearance_budget": collision_interlock.get(
                "post_enable_clearance_budget"
            ),
            "collision_interlock": collision_interlock,
        },
        "shadow_sweep": {
            "trace": trace,
            "geometry_catalogs": {
                "source": source_catalog,
                "table": table_catalog,
                "robot_bodies": robot_catalogs,
                "robot_rigid_body_paths": robot_rigid_body_paths,
                "colliderless_robot_bodies": colliderless_robot_bodies,
                "all_robot_rigid_body_paths": all_robot_rigid_body_paths,
                "robot_collider_inventory": robot_collider_inventory,
                "inventory_sha256": robot_inventory_sha256,
            },
            "opening_axis_world": shadow_opening_axis_world,
            "opening_axis_authority": (
                "literal_commanded_tool_orientation_v1"
            ),
            "opening_axis_tool_orientation_wxyz": [
                float(value)
                for value in fluid.expert_pick_target_orientation_wxyz
            ],
            "source_contact_offset_m": (
                None
                if source_contact_offset is None
                else float(source_contact_offset)
            ),
            "source_contact_offset_authority": {
                "authority": "per_collider_cooked_catalog_v1",
                "colliders": {
                    collider["path"]: collider["contact_offset"]
                    for collider in source_catalog["colliders"]
                },
            },
            "finger_edge_radii_m": finger_edge_radii,
            "finger_edge_radius_method": "cooked_local_aabb_corners_from_measured_tool_center",
            "source_writer_audit": writer_audit.record(),
            "attachment_events": attachment_events,
            "controller_evidence": controller_evidence,
        },
    }
    evaluation = evaluate_runtime_measurements(report)
    if attribution_ambiguous:
        evaluation["checks"]["contact_attribution"] = False
        if "contact_attribution" not in evaluation["failed_checks"]:
            evaluation["failed_checks"].append("contact_attribution")
        evaluation["decision"] = NO_GO_DECISION
    report["child_evaluation"] = evaluation
    report["measurement_decision"] = evaluation["decision"]
    return report


def _run_child(args: argparse.Namespace) -> int:
    atomic_create_json(
        args.owner,
        {
            "pid": os.getpid(),
            "run_id": args.run_id,
            "run_identity_sha256": args.run_identity_sha256,
        },
    )
    report: dict[str, Any]
    app = None
    phase = "application_bootstrap"
    try:
        from isaacsim import SimulationApp

        app = SimulationApp(
            {"headless": bool(args.headless), "width": 64, "height": 64}
        )
        phase = "post_simulation_app_identity_validation"
        child_identity = build_run_identity(args.config)
        if child_identity.get("identity_sha256") != args.run_identity_sha256:
            raise ValueError("trajectory_preflight_child_run_identity_mismatch")
        phase = "runtime_measurement"
        report = _measure_isaac_runtime(app, args)
    except MeasurementNoGo as exc:
        report = _measurement_no_go_report(
            exc,
            run_id=args.run_id,
            run_identity_sha256=args.run_identity_sha256,
        )
    except BaseException as exc:
        report = _runtime_error_report(
            exc,
            run_id=args.run_id,
            run_identity_sha256=args.run_identity_sha256,
            phase=phase,
        )
    try:
        _canonical_json_bytes(report)
    except (TypeError, ValueError) as exc:
        report = _runtime_error_report(
            exc,
            run_id=args.run_id,
            run_identity_sha256=args.run_identity_sha256,
            phase="strict_json_serialization",
        )
    _persist_provisional_before_shutdown(
        app=app,
        output_path=args.runtime_report,
        report=report,
    )
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--runtime-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--run-id", help=argparse.SUPPRESS)
    parser.add_argument("--owner", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--runtime-report", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--run-identity-sha256", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    if not args.config.is_file():
        parser.error(f"config not found: {args.config}")
    if args.runtime_child:
        if (
            not isinstance(args.run_id, str)
            or not args.run_id
            or args.owner is None
            or args.runtime_report is None
            or not isinstance(args.run_identity_sha256, str)
            or len(args.run_identity_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in args.run_identity_sha256
            )
            or args.out_dir is not None
        ):
            parser.error("runtime child requires run-id, owner, and runtime-report only")
        args.owner = args.owner.resolve()
        args.runtime_report = args.runtime_report.resolve()
        if args.owner.exists() or args.runtime_report.exists():
            parser.error("runtime child output already exists")
    else:
        if args.out_dir is None or any(
            value is not None
            for value in (
                args.run_id,
                args.owner,
                args.runtime_report,
                args.run_identity_sha256,
            )
        ):
            parser.error("parent requires out-dir and forbids child identity arguments")
        args.out_dir = args.out_dir.resolve()
        if (
            not math.isfinite(args.timeout_seconds)
            or args.timeout_seconds <= 0.0
        ):
            parser.error("timeout must be finite and positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_child(args) if args.runtime_child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
