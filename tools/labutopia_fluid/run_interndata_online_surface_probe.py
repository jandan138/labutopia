#!/usr/bin/env python3
"""Run current-state liquid surface rendering inside the strict PhysX loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from tools.labutopia_fluid.run_interndata_pour_parity_probe import (
    INTEGRATION_DT,
    PARTICLE_SET_PATH,
    PARTICLE_SYSTEM_PATH,
    PHYSICS_SUBSTEPS_PER_FRAME,
    PUBLIC_PARTICLE_COUNT,
    PUBLIC_PHYSICS_DT,
    _frame_at_parent_matrix,
    _kinematic_parent_matrix,
    build_fixed_kinematic_schedule,
    classify_two_beaker_positions,
    kinematic_pose_error,
    matrix_to_physx_pose,
    physx_pose_to_matrix,
)
from utils.online_fluid_surface import (
    ObservationTransition,
    OnlineFluidSurfaceRuntime,
    SurfaceFrameToken,
    read_strict_simulation_points,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = (
    REPO_ROOT
    / "outputs/usd_asset_packages"
    / "lab_001_level1_pour_interndata_liquid_v1_20260714"
)
DEFAULT_INPUT_SCENE = PACKAGE_ROOT / "lab_001_level1_pour_interndata_liquid_v1.usda"
DEFAULT_RECONSTRUCTION_SITE_PACKAGES = (
    REPO_ROOT
    / "outputs/interndata_surface_replay_20260714/reconstruction_env"
    / "lib/python3.10/site-packages"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs/interndata_online_surface_probe_20260714"
INPUT_SCENE_SHA256 = "ab9f5eb1d3bc387e13ccb23655454d9357833b261f346fd93d974b86e1f83139"
SOURCE_ACTOR_PATH = "/World/beaker2"
TARGET_ACTOR_PATH = "/World/beaker1"
SURFACE_PATH = "/World/InternDataOnlineSurface"
MATERIAL_PATH = "/World/Looks/InternDataOnlineSurfaceWater"
VALIDATION_CAMERA_PATHS = {
    "context": "/World/InternDataParityCamera",
    "closeup": "/World/InternDataParityCloseupCamera",
}
MODEL_CAMERA_PATHS = {
    "camera_1": "/World/Camera1",
    "camera_2": "/World/Camera2",
}
CAMERA_PATHS = VALIDATION_CAMERA_PATHS
CAMERA_PROFILES = {
    "validation": VALIDATION_CAMERA_PATHS,
    "model": MODEL_CAMERA_PATHS,
}
HOLD_CHECKPOINT_STEP = 230
INITIAL_SET_RMS_TOLERANCE_M = 5.0e-4
INITIAL_SET_MAX_TOLERANCE_M = 3.0e-3
INITIAL_SET_CENTROID_TOLERANCE_M = 1.0e-4
INITIAL_SET_MINIMUM_UNIQUE_COVERAGE = 0.95
DYNAMIC_HOLD_MAX_POSITION_DRIFT_M = 0.01
DYNAMIC_HOLD_MAX_ROTATION_DRIFT_DEGREES = 2.0
IMPLEMENTATION_FILES = (
    "tools/labutopia_fluid/run_interndata_online_surface_probe.py",
    "tools/labutopia_fluid/interndata_surface_reconstruction.py",
    "tools/labutopia_fluid/run_interndata_pour_parity_probe.py",
    "tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py",
    "tools/labutopia_fluid/real_beaker.py",
    "utils/online_fluid_surface.py",
)


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def implementation_identity() -> dict[str, Any]:
    files = {
        relative: _sha256_file(REPO_ROOT / relative)
        for relative in IMPLEMENTATION_FILES
    }
    return {
        "files": files,
        "sha256": _canonical_json_sha256(files),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                _json_safe(value),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        )


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_initial_particle_snapshot(
    path: str | Path,
    positions: Any,
) -> dict[str, Any]:
    values = np.ascontiguousarray(positions, dtype=np.float32)
    if values.shape != (PUBLIC_PARTICLE_COUNT, 3) or not np.isfinite(values).all():
        raise ValueError("initial_particle_snapshot_invalid")
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    np.save(target, values, allow_pickle=False)
    return {
        "path": str(target),
        "sha256": _sha256_file(target),
        "shape": list(values.shape),
        "dtype": str(values.dtype),
    }


def _load_initial_particle_snapshot(metadata: Any) -> np.ndarray:
    if not isinstance(metadata, Mapping):
        raise ValueError("initial_particle_snapshot_metadata_missing")
    path = Path(metadata["path"]).resolve(strict=True)
    if _sha256_file(path) != metadata.get("sha256"):
        raise ValueError("initial_particle_snapshot_sha256_mismatch")
    values = np.load(path, allow_pickle=False)
    if (
        list(values.shape) != metadata.get("shape")
        or str(values.dtype) != metadata.get("dtype")
        or values.shape != (PUBLIC_PARTICLE_COUNT, 3)
        or not np.isfinite(values).all()
    ):
        raise ValueError("initial_particle_snapshot_invalid")
    return np.ascontiguousarray(values, dtype=np.float64)


def compare_initial_particle_snapshots(
    first: Any,
    second: Any,
) -> dict[str, Any]:
    try:
        first_points = _load_initial_particle_snapshot(first)
        second_points = _load_initial_particle_snapshot(second)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return {
            "status": "INVALID",
            "passed": False,
            "error": str(exc),
            "rms_error_m": None,
            "maximum_error_m": None,
        }
    from scipy.spatial import cKDTree

    first_to_second, first_indices = cKDTree(second_points).query(
        first_points, k=1
    )
    second_to_first, second_indices = cKDTree(first_points).query(
        second_points, k=1
    )
    squared_errors = np.concatenate(
        (np.square(first_to_second), np.square(second_to_first))
    )
    rms_error = float(np.sqrt(np.mean(squared_errors)))
    maximum_error = float(
        max(np.max(first_to_second), np.max(second_to_first))
    )
    centroid_error = float(
        np.linalg.norm(np.mean(first_points, axis=0) - np.mean(second_points, axis=0))
    )
    first_coverage = float(len(np.unique(first_indices)) / len(first_indices))
    second_coverage = float(len(np.unique(second_indices)) / len(second_indices))
    minimum_unique_coverage = min(first_coverage, second_coverage)
    passed = (
        rms_error <= INITIAL_SET_RMS_TOLERANCE_M
        and maximum_error <= INITIAL_SET_MAX_TOLERANCE_M
        and centroid_error <= INITIAL_SET_CENTROID_TOLERANCE_M
        and minimum_unique_coverage >= INITIAL_SET_MINIMUM_UNIQUE_COVERAGE
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "particle_count": int(first_points.shape[0]),
        "rms_error_m": rms_error,
        "maximum_error_m": maximum_error,
        "centroid_error_m": centroid_error,
        "minimum_unique_coverage": minimum_unique_coverage,
        "first_to_second_unique_coverage": first_coverage,
        "second_to_first_unique_coverage": second_coverage,
        "rms_tolerance_m": INITIAL_SET_RMS_TOLERANCE_M,
        "maximum_tolerance_m": INITIAL_SET_MAX_TOLERANCE_M,
        "centroid_tolerance_m": INITIAL_SET_CENTROID_TOLERANCE_M,
        "minimum_unique_coverage_required": (
            INITIAL_SET_MINIMUM_UNIQUE_COVERAGE
        ),
    }


def extract_liquid_semantic_mask(
    payload: Mapping[str, Any],
    *,
    expected_width: int,
    expected_height: int,
    expected_surface_token: str | None = None,
    allow_absent: bool = False,
) -> tuple[np.ndarray, dict[str, Any]]:
    if not isinstance(payload, Mapping):
        raise ValueError("semantic_segmentation_payload_invalid")
    data = np.asarray(payload.get("data"))
    if data.shape != (expected_height, expected_width) or data.dtype.kind not in "ui":
        raise ValueError("semantic_segmentation_data_invalid")
    info = payload.get("info")
    labels = info.get("idToLabels") if isinstance(info, Mapping) else None
    if not isinstance(labels, Mapping):
        raise ValueError("semantic_segmentation_labels_missing")

    semantic_ids = []
    token_matched = expected_surface_token is None
    liquid_label_found = False
    for raw_id, raw_labels in labels.items():
        if not isinstance(raw_labels, Mapping):
            continue
        class_value = raw_labels.get("class")
        if not isinstance(class_value, str):
            continue
        class_tokens = {token.strip() for token in class_value.split(",")}
        if "online_liquid" in class_tokens:
            liquid_label_found = True
            if expected_surface_token is not None:
                if expected_surface_token not in class_tokens:
                    continue
                token_matched = True
            try:
                semantic_ids.append(int(raw_id))
            except (TypeError, ValueError) as exc:
                raise ValueError("online_liquid_semantic_id_invalid") from exc
    semantic_ids = sorted(set(semantic_ids))
    if liquid_label_found and not token_matched:
        raise ValueError("online_liquid_surface_token_mismatch")
    if not semantic_ids:
        if not allow_absent:
            raise ValueError("online_liquid_semantic_id_missing")
        mask = np.zeros((expected_height, expected_width), dtype=np.bool_)
        return mask, {
            "semantic_ids": [],
            "visible_pixel_count": 0,
            "mask_sha256": _canonical_json_sha256(mask.tolist()),
            "surface_frame_token": None,
        }

    mask = np.isin(data, semantic_ids)
    visible_pixel_count = int(np.count_nonzero(mask))
    if visible_pixel_count == 0:
        if not allow_absent:
            raise ValueError("online_liquid_pixels_missing")
    mask = np.ascontiguousarray(mask, dtype=np.bool_)
    evidence = {
        "semantic_ids": semantic_ids,
        "visible_pixel_count": visible_pixel_count,
        "mask_sha256": _canonical_json_sha256(mask.tolist()),
    }
    if expected_surface_token is not None:
        evidence["surface_frame_token"] = expected_surface_token
    return mask, evidence


def default_probe_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "input_scene": str(DEFAULT_INPUT_SCENE),
        "input_scene_sha256": INPUT_SCENE_SHA256,
        "particle_path": PARTICLE_SET_PATH,
        "particle_system_path": PARTICLE_SYSTEM_PATH,
        "source_actor_path": SOURCE_ACTOR_PATH,
        "source_body_mode": "kinematic",
        "target_actor_path": TARGET_ACTOR_PATH,
        "surface_path": SURFACE_PATH,
        "expected_particle_count": PUBLIC_PARTICLE_COUNT,
        "logical_dt": PUBLIC_PHYSICS_DT,
        "integration_dt": INTEGRATION_DT,
        "substeps_per_observation": PHYSICS_SUBSTEPS_PER_FRAME,
        "camera_resolution": [256, 256],
        "camera_paths": dict(CAMERA_PATHS),
        "model_camera_paths": dict(MODEL_CAMERA_PATHS),
        "default_camera_profile": "validation",
        "surface_observation_stride": 1,
        "pre_episode_physx_initialization_steps": 1,
        "saved_frame_stride": 10,
        "hold_checkpoint_step": HOLD_CHECKPOINT_STEP,
        "renderer": "RayTracedLighting",
        "rt_subframes": 4,
        "reconstruction_site_packages": str(
            DEFAULT_RECONSTRUCTION_SITE_PACKAGES
        ),
    }


def source_body_mode_contract(mode: str, *, treatment: str) -> dict[str, Any]:
    if mode not in {"kinematic", "dynamic"}:
        raise ValueError(f"source_body_mode_invalid:{mode}")
    if mode == "dynamic" and treatment != "hold":
        raise ValueError("dynamic_source_requires_hold_treatment")
    return {
        "mode": mode,
        "kinematic_enabled": mode == "kinematic",
        "action_driver": (
            "RigidBodyView.set_kinematic_targets"
            if mode == "kinematic"
            else "none_dynamic_gravity"
        ),
        "activation_phase": (
            "pre_particle_initialization"
            if mode == "kinematic"
            else "post_particle_initialization"
        ),
    }


def apply_source_body_mode(
    source_prim: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    kinematic = source_prim.GetAttribute("physics:kinematicEnabled")
    rigid_body = source_prim.GetAttribute("physics:rigidBodyEnabled")
    if not kinematic or not rigid_body or not bool(rigid_body.Get()):
        raise ValueError("source_rigid_body_contract_invalid")
    before = bool(kinematic.Get())
    expected = bool(contract["kinematic_enabled"])
    authoring_warning = None
    try:
        kinematic.Set(expected)
    except Exception as exc:
        if "Proceeding to use existing" not in str(exc):
            raise
        authoring_warning = str(exc)
    after = bool(kinematic.Get())
    if after != expected:
        raise RuntimeError("source_body_mode_authoring_failed")
    result = {
        **dict(contract),
        "prim_path": str(source_prim.GetPath()),
        "kinematic_enabled_before": before,
        "kinematic_enabled_after": after,
        "rigid_body_enabled": True,
    }
    if authoring_warning is not None:
        result["authoring_warning"] = authoring_warning
    return result


def summarize_dynamic_hold_quality(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not records or any(
        record.get("source_body_mode") != "dynamic" for record in records
    ):
        raise ValueError("dynamic_hold_records_required")
    position_drift = [
        float(record["action"]["reference_pose_error"]["position_m"])
        for record in records
    ]
    rotation_drift = [
        float(record["action"]["reference_pose_error"]["rotation_degrees"])
        for record in records
    ]
    minimum_source = min(
        int(record["raw_particle_counts"]["source"]) for record in records
    )
    maximum_escape_counts = {
        field: max(
            int(record["raw_particle_counts"][field]) for record in records
        )
        for field in (
            "target",
            "transit",
            "tabletop_spill",
            "below_table",
            "nonfinite",
        )
    }
    maximum_position = max(position_drift)
    maximum_rotation = max(rotation_drift)
    passed = (
        maximum_position <= DYNAMIC_HOLD_MAX_POSITION_DRIFT_M
        and maximum_rotation <= DYNAMIC_HOLD_MAX_ROTATION_DRIFT_DEGREES
        and minimum_source == PUBLIC_PARTICLE_COUNT
        and all(value == 0 for value in maximum_escape_counts.values())
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "maximum_position_drift_m": maximum_position,
        "maximum_rotation_drift_degrees": maximum_rotation,
        "minimum_source_particle_count": minimum_source,
        "maximum_escape_counts": maximum_escape_counts,
        "position_drift_tolerance_m": DYNAMIC_HOLD_MAX_POSITION_DRIFT_M,
        "rotation_drift_tolerance_degrees": (
            DYNAMIC_HOLD_MAX_ROTATION_DRIFT_DEGREES
        ),
    }


def camera_paths_for_profile(profile: str) -> dict[str, str]:
    try:
        return dict(CAMERA_PROFILES[profile])
    except KeyError as exc:
        raise ValueError(f"camera_profile_invalid:{profile}") from exc


def format_camera_observation(
    camera_name: str,
    rgb: Any,
    *,
    camera_profile: str,
) -> tuple[str, np.ndarray]:
    values = np.asarray(rgb)
    if values.ndim != 3 or values.shape[2] != 3 or values.dtype != np.uint8:
        raise ValueError("camera_rgb_hwc_uint8_required")
    if camera_profile == "model":
        return f"{camera_name}_rgb", np.ascontiguousarray(
            np.transpose(values, (2, 0, 1))
        )
    if camera_profile == "validation":
        return camera_name, np.ascontiguousarray(values)
    raise ValueError(f"camera_profile_invalid:{camera_profile}")


def build_treatment_plan(treatment: str) -> list[dict[str, Any]]:
    if treatment not in {"pour", "hold"}:
        raise ValueError(f"treatment_invalid:{treatment}")
    states = [dict(state) for state in build_fixed_kinematic_schedule()["states"]]
    if treatment == "pour":
        return states
    result = []
    for state in states[: HOLD_CHECKPOINT_STEP + 1]:
        result.append(
            {
                **state,
                "phase": "hold_control",
                "translation_progress": 0.0,
                "tilt_degrees": 0.0,
            }
        )
    return result


def build_observation_transition(
    *,
    episode_id: str,
    observation_index: int,
    logical_step_before: int,
    logical_step_after: int,
    integration_step_before: int,
    integration_step_after: int,
    action_sha256: str | None = None,
) -> ObservationTransition:
    return ObservationTransition(
        episode_id=episode_id,
        observation_index=observation_index,
        caused_by_action_index=(
            None if observation_index == 0 else observation_index - 1
        ),
        logical_step_before=logical_step_before,
        logical_step_after=logical_step_after,
        integration_step_before=integration_step_before,
        integration_step_after=integration_step_after,
        simulation_time_before=integration_step_before * INTEGRATION_DT,
        simulation_time_after=integration_step_after * INTEGRATION_DT,
        action_sha256=action_sha256,
    )


def _records_by_step(records: Sequence[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    for record in records:
        step = int(record["observation_index"])
        if step in result:
            raise ValueError(f"duplicate_observation_record:{step}")
        result[step] = record
    return result


def _initial_counts_are_equivalent(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> bool:
    zero_fields = ("target", "transit", "tabletop_spill", "below_table", "nonfinite")
    try:
        first_source = int(first["source"])
        second_source = int(second["source"])
        zeroed = all(
            int(record[field]) == 0
            for record in (first, second)
            for field in zero_fields
        )
    except (KeyError, TypeError, ValueError):
        return False
    validity = all(
        bool(record.get(field, True))
        for record in (first, second)
        for field in ("valid", "partition_complete")
    )
    return first_source == second_source and first_source > 0 and zeroed and validity


def _counts_close(first: Any, second: Any, *, relative_tolerance: float = 0.01) -> bool:
    try:
        first_value = int(first)
        second_value = int(second)
    except (TypeError, ValueError):
        return False
    tolerance = max(2, math.ceil(relative_tolerance * max(first_value, second_value, 1)))
    return abs(first_value - second_value) <= tolerance


def _initial_surface_topology_is_equivalent(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> bool:
    return _counts_close(first.get("vertex_count"), second.get("vertex_count")) and _counts_close(
        first.get("face_count"), second.get("face_count")
    )


def _visible_liquid_counts(evidence: Mapping[str, Any]) -> dict[str, int] | None:
    cameras = evidence.get("cameras")
    if not isinstance(cameras, Sequence) or isinstance(cameras, (str, bytes)):
        return None
    result: dict[str, int] = {}
    for camera in cameras:
        if not isinstance(camera, Mapping):
            return None
        name = camera.get("camera")
        try:
            count = int(camera["visible_pixel_count"])
        except (KeyError, TypeError, ValueError):
            return None
        if not isinstance(name, str) or not name or name in result or count <= 0:
            return None
        result[name] = count
    return result or None


def _initial_liquid_visibility_is_equivalent(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> bool:
    first_counts = _visible_liquid_counts(first)
    second_counts = _visible_liquid_counts(second)
    if first_counts is None or second_counts is None or first_counts.keys() != second_counts.keys():
        return False
    return all(
        _counts_close(first_counts[name], second_counts[name]) for name in first_counts
    )


def _initial_conditions_are_physically_equivalent(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> bool:
    try:
        same_epoch = (
            int(first["logical_step_after"]) == int(second["logical_step_after"]) == 0
            and int(first["integration_step_after"])
            == int(second["integration_step_after"])
            == 0
            and math.isclose(
                float(first["simulation_time_after"]),
                float(second["simulation_time_after"]),
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
        )
        first_pose = np.asarray(first["action"]["target_pose_xyzw"], dtype=np.float64)
        second_pose = np.asarray(second["action"]["target_pose_xyzw"], dtype=np.float64)
        same_pose = (
            first_pose.shape == second_pose.shape == (7,)
            and np.isfinite(first_pose).all()
            and np.isfinite(second_pose).all()
            and np.allclose(first_pose, second_pose, rtol=0.0, atol=1.0e-12)
        )
        counts_match = _initial_counts_are_equivalent(
            first["raw_particle_counts"], second["raw_particle_counts"]
        )
        topology_match = _initial_surface_topology_is_equivalent(
            first["surface"], second["surface"]
        )
        visibility_match = _initial_liquid_visibility_is_equivalent(
            first["liquid_pixel_evidence"], second["liquid_pixel_evidence"]
        )
    except (KeyError, TypeError, ValueError):
        return False
    return bool(same_epoch and same_pose and counts_match and topology_match and visibility_match)


def compare_treatments(
    pour_records: Sequence[Mapping[str, Any]],
    hold_records: Sequence[Mapping[str, Any]],
    *,
    checkpoint_step: int = HOLD_CHECKPOINT_STEP,
) -> dict[str, Any]:
    pour = _records_by_step(pour_records)
    hold = _records_by_step(hold_records)
    if 0 not in pour or 0 not in hold:
        raise ValueError("initial_observation_missing")
    if checkpoint_step not in pour or checkpoint_step not in hold:
        raise ValueError(f"checkpoint_observation_missing:{checkpoint_step}")
    pour_initial = pour[0]
    hold_initial = hold[0]
    pour_checkpoint = pour[checkpoint_step]
    hold_checkpoint = hold[checkpoint_step]
    common_initial_exact = (
        pour_initial["position_sha256"] == hold_initial["position_sha256"]
        and pour_initial["surface"]["geometry_sha256"]
        == hold_initial["surface"]["geometry_sha256"]
        and pour_initial["liquid_evidence_sha256"]
        == hold_initial["liquid_evidence_sha256"]
    )
    initial_particle_comparison = compare_initial_particle_snapshots(
        pour_initial.get("initial_particle_snapshot"),
        hold_initial.get("initial_particle_snapshot"),
    )
    initial_conditions_equivalent = (
        common_initial_exact
        or (
            initial_particle_comparison["passed"]
            and _initial_conditions_are_physically_equivalent(
                pour_initial, hold_initial
            )
        )
    )
    matched_time = (
        pour_checkpoint["logical_step_after"]
        == hold_checkpoint["logical_step_after"]
        and pour_checkpoint["integration_step_after"]
        == hold_checkpoint["integration_step_after"]
        and math.isclose(
            float(pour_checkpoint["simulation_time_after"]),
            float(hold_checkpoint["simulation_time_after"]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    )
    pour_action_pose = np.asarray(
        pour_checkpoint["action"]["target_pose_xyzw"], dtype=np.float64
    )
    hold_action_pose = np.asarray(
        hold_checkpoint["action"]["target_pose_xyzw"], dtype=np.float64
    )
    action_diverged = (
        pour_action_pose.shape == hold_action_pose.shape == (7,)
        and np.isfinite(pour_action_pose).all()
        and np.isfinite(hold_action_pose).all()
        and not np.allclose(
            pour_action_pose, hold_action_pose, rtol=0.0, atol=1.0e-12
        )
    )
    position_diverged = (
        pour_checkpoint["position_sha256"]
        != hold_checkpoint["position_sha256"]
    )
    counts_diverged = (
        pour_checkpoint["raw_particle_counts"]
        != hold_checkpoint["raw_particle_counts"]
        and int(pour_checkpoint["raw_particle_counts"]["target"])
        > int(hold_checkpoint["raw_particle_counts"]["target"])
    )
    surface_diverged = (
        pour_checkpoint["surface"]["geometry_sha256"]
        != hold_checkpoint["surface"]["geometry_sha256"]
    )
    liquid_pixels_diverged = (
        pour_checkpoint["liquid_evidence_sha256"]
        != hold_checkpoint["liquid_evidence_sha256"]
    )
    raw_particles_diverged = position_diverged and counts_diverged
    passed = all(
        (
            initial_conditions_equivalent,
            matched_time,
            action_diverged,
            raw_particles_diverged,
            surface_diverged,
            liquid_pixels_diverged,
        )
    )
    return {
        "checkpoint_step": checkpoint_step,
        "common_initial_state_exact": common_initial_exact,
        "initial_conditions_equivalent": initial_conditions_equivalent,
        "common_initial_state": initial_conditions_equivalent,
        "initial_comparison_basis": (
            "byte_exact"
            if common_initial_exact
            else "bidirectional_particle_set_tolerance"
            if initial_conditions_equivalent
            else "mismatch"
        ),
        "initial_particle_comparison": initial_particle_comparison,
        "matched_simulation_time": matched_time,
        "action_diverged": action_diverged,
        "position_hash_diverged": position_diverged,
        "raw_particle_counts_diverged": counts_diverged,
        "raw_particles_diverged": raw_particles_diverged,
        "surface_diverged": surface_diverged,
        "liquid_pixels_diverged": liquid_pixels_diverged,
        "causality_gate_passed": passed,
    }


def _load_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path).resolve(strict=True)
    records = []
    for line_number, raw_line in enumerate(
        source.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        value = json.loads(raw_line)
        if not isinstance(value, Mapping):
            raise ValueError(f"observation_record_mapping_required:{line_number}")
        records.append(dict(value))
    if not records:
        raise ValueError("observation_records_empty")
    return records


_RUN_IDENTITY_FIELDS = (
    "runtime_contract_sha256",
    "implementation_sha256",
    "input_scene_sha256",
    "camera_profile",
    "source_body_mode",
)


def _validate_gate_record_sequence(
    records: Sequence[Mapping[str, Any]],
    *,
    treatment: str,
    checkpoint_step: int,
) -> dict[str, Any]:
    expected_steps = list(range(checkpoint_step + 1))
    actual_steps = [int(record["observation_index"]) for record in records]
    if actual_steps != expected_steps:
        raise ValueError(f"gate_records_incomplete:{treatment}")
    if any(record.get("treatment") != treatment for record in records):
        raise ValueError(f"gate_treatment_mismatch:{treatment}")
    episode_ids = {record.get("episode_id") for record in records}
    if len(episode_ids) != 1 or None in episode_ids:
        raise ValueError(f"gate_episode_identity_invalid:{treatment}")
    for step, record in enumerate(records):
        if (
            int(record["logical_step_after"]) != step
            or int(record["integration_step_after"]) != step * 4
            or not math.isclose(
                float(record["simulation_time_after"]),
                step / 30.0,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
        ):
            raise ValueError(f"gate_step_epoch_invalid:{treatment}:{step}")
    identity = {}
    for field in _RUN_IDENTITY_FIELDS:
        values = {record.get(field) for record in records}
        if len(values) != 1 or None in values:
            raise ValueError(f"gate_run_identity_invalid:{treatment}:{field}")
        identity[field] = next(iter(values))
    return identity


def _treatment_quality(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    maxima = {
        field: max(int(record["raw_particle_counts"][field]) for record in records)
        for field in ("tabletop_spill", "below_table", "nonfinite")
    }
    return {
        "maximum_counts": maxima,
        "strict_zero_spill_passed": all(value == 0 for value in maxima.values()),
    }


def write_treatment_causality_gate(
    pour_records_path: str | Path,
    hold_records_path: str | Path,
    output_path: str | Path,
    *,
    checkpoint_step: int = HOLD_CHECKPOINT_STEP,
) -> dict[str, Any]:
    pour_path = Path(pour_records_path).resolve(strict=True)
    hold_path = Path(hold_records_path).resolve(strict=True)
    pour_records = _load_jsonl_records(pour_path)
    hold_records = _load_jsonl_records(hold_path)
    pour_identity = _validate_gate_record_sequence(
        pour_records,
        treatment="pour",
        checkpoint_step=checkpoint_step,
    )
    hold_identity = _validate_gate_record_sequence(
        hold_records,
        treatment="hold",
        checkpoint_step=checkpoint_step,
    )
    if pour_identity != hold_identity:
        raise ValueError("gate_run_identity_mismatch")
    comparison = compare_treatments(
        pour_records,
        hold_records,
        checkpoint_step=checkpoint_step,
    )
    gate = {
        "schema_version": 1,
        "status": "PASS" if comparison["causality_gate_passed"] else "FAIL",
        "claim": "online_action_to_physics_to_surface_to_pixels_causality",
        "gate_implementation": implementation_identity(),
        "matched_run_identity": True,
        "run_identity": pour_identity,
        "pour_records": {
            "path": str(pour_path),
            "sha256": _sha256_file(pour_path),
            "count": len(pour_records),
        },
        "hold_records": {
            "path": str(hold_path),
            "sha256": _sha256_file(hold_path),
            "count": len(hold_records),
        },
        "comparison": comparison,
        "task_quality": {
            "pour": _treatment_quality(pour_records),
            "hold": _treatment_quality(hold_records),
        },
    }
    _write_json(Path(output_path), gate)
    return gate


def _load_live_reconstruction(site_packages: Path) -> tuple[Any, dict[str, Any]]:
    if not site_packages.is_dir():
        raise FileNotFoundError(f"reconstruction_site_packages_missing:{site_packages}")
    site_value = str(site_packages.resolve())
    if site_value not in sys.path:
        sys.path.append(site_value)
    from tools.labutopia_fluid.interndata_surface_reconstruction import (
        default_live_reconstruction_contract,
        reconstruct_surface_live,
        reconstruction_contract_sha256,
    )
    import scipy
    import skimage

    contract = default_live_reconstruction_contract()
    dependencies = {
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "scikit_image": skimage.__version__,
        "site_packages": site_value,
        "contract": contract,
        "contract_sha256": reconstruction_contract_sha256(contract),
    }
    return reconstruct_surface_live, dependencies


def _vt_vec3f_array(values: np.ndarray) -> Any:
    from pxr import Gf, Vt

    contiguous = np.ascontiguousarray(values, dtype=np.float32)
    converter = getattr(Vt.Vec3fArray, "FromNumpy", None)
    if converter is not None:
        return converter(contiguous)
    return Vt.Vec3fArray([Gf.Vec3f(*row) for row in contiguous.tolist()])


def _vt_int_array(values: np.ndarray) -> Any:
    from pxr import Vt

    contiguous = np.ascontiguousarray(values, dtype=np.int32).reshape(-1)
    converter = getattr(Vt.IntArray, "FromNumpy", None)
    if converter is not None:
        return converter(contiguous)
    return Vt.IntArray(contiguous.tolist())


def _set_surface_semantics(prim: Any, surface_token: str) -> dict[str, Any]:
    from pxr import Semantics

    api = Semantics.SemanticsAPI.Apply(prim, "OnlineLiquid")
    api.CreateSemanticTypeAttr().Set("class")
    data = f"online_liquid,{surface_token}"
    api.CreateSemanticDataAttr().Set(data)
    return {"type": "class", "data": data}


def update_live_surface_mesh(
    stage: Any,
    mesh_data: Mapping[str, Any],
    token: SurfaceFrameToken,
) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom, Vt

    vertices = np.ascontiguousarray(mesh_data["vertices"], dtype=np.float32)
    faces = np.ascontiguousarray(mesh_data["faces"], dtype=np.int32)
    normals = np.ascontiguousarray(mesh_data["normals"], dtype=np.float32)
    origin = np.asarray(mesh_data["origin_world_m"], dtype=np.float64)
    mesh = UsdGeom.Mesh.Define(stage, SURFACE_PATH)
    prim = mesh.GetPrim()
    translate = prim.CreateAttribute(
        "xformOp:translate", Sdf.ValueTypeNames.Double3, custom=False
    )
    translate.Set(Gf.Vec3d(*origin.tolist()))
    order = prim.CreateAttribute(
        "xformOpOrder", Sdf.ValueTypeNames.TokenArray, custom=False
    )
    order.Set(Vt.TokenArray(["xformOp:translate"]))
    mesh.CreatePointsAttr().Set(_vt_vec3f_array(vertices))
    mesh.CreateFaceVertexCountsAttr().Set(
        _vt_int_array(np.full(len(faces), 3, dtype=np.int32))
    )
    mesh.CreateFaceVertexIndicesAttr().Set(_vt_int_array(faces))
    mesh.CreateNormalsAttr().Set(_vt_vec3f_array(normals))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateExtentAttr().Set(
        _vt_vec3f_array(
            np.asarray([vertices.min(axis=0), vertices.max(axis=0)], dtype=np.float32)
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
    semantics = _set_surface_semantics(prim, token.identity)
    return {
        "path": SURFACE_PATH,
        "surface_token": token.identity,
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        "origin_world_m": origin.tolist(),
        "semantics": semantics,
    }


def invalidate_live_surface(stage: Any, reason: str) -> None:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(SURFACE_PATH)
    if prim and prim.IsValid() and prim.IsA(UsdGeom.Imageable):
        UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)


def author_live_surface_material(stage: Any) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    if not stage.GetPrimAtPath("/World/Looks"):
        UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, MATERIAL_PATH)
    shader = UsdShade.Shader.Define(stage, f"{MATERIAL_PATH}/PreviewSurface")
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
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    surface = stage.GetPrimAtPath(SURFACE_PATH)
    UsdShade.MaterialBindingAPI.Apply(surface).Bind(material)
    return {"material_path": MATERIAL_PATH, "shader": "UsdPreviewSurface"}


def configure_live_visual_authority(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    hidden = []
    for path in (
        PARTICLE_SET_PATH,
        "/World/InternDataParityFluid/VisualParticles",
        "/World/ParticleSet",
        "/World/fluid",
    ):
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsValid() and prim.IsA(UsdGeom.Imageable):
            UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            hidden.append(path)
    system = stage.GetPrimAtPath(PARTICLE_SYSTEM_PATH)
    if system and system.IsValid():
        attribute = system.GetAttribute("physxParticleIsosurface:isosurfaceEnabled")
        if attribute:
            attribute.Set(False)
    surface = stage.GetPrimAtPath(SURFACE_PATH)
    UsdGeom.Imageable(surface).CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)
    return {
        "visible_liquid_path": SURFACE_PATH,
        "hidden_liquid_paths": hidden,
        "native_isosurface_disabled": True,
    }


class _CaptureAdapter:
    def __init__(
        self,
        *,
        rep: Any,
        resources: Mapping[str, Mapping[str, Any]],
        output_dir: Path,
        width: int,
        height: int,
        saved_frame_stride: int,
        minimum_visible_cameras: int,
        camera_profile: str,
    ) -> None:
        self.rep = rep
        self.resources = resources
        self.output_dir = output_dir
        self.width = width
        self.height = height
        self.saved_frame_stride = saved_frame_stride
        self.minimum_visible_cameras = minimum_visible_cameras
        self.camera_profile = camera_profile
        self.last_liquid_evidence_sha256: str | None = None
        self.last_liquid_evidence: dict[str, Any] | None = None

    def __call__(
        self,
        token: SurfaceFrameToken,
        render_record: Mapping[str, Any],
    ) -> dict[str, np.ndarray]:
        from PIL import Image
        from tools.labutopia_fluid.run_interndata_pour_parity_probe import (
            normalize_rgb_frame,
        )

        arrays: dict[str, np.ndarray] = {}
        evidence_parts = []
        for name, resource in self.resources.items():
            rgb = normalize_rgb_frame(
                resource["rgb"].get_data(),
                expected_width=self.width,
                expected_height=self.height,
            ).copy()
            liquid_mask, liquid_evidence = extract_liquid_semantic_mask(
                resource["semantic"].get_data(),
                expected_width=self.width,
                expected_height=self.height,
                expected_surface_token=token.identity,
                allow_absent=True,
            )
            observation_name, observation = format_camera_observation(
                name,
                rgb,
                camera_profile=self.camera_profile,
            )
            arrays[observation_name] = observation
            evidence_parts.append(
                {
                    "camera": name,
                    **liquid_evidence,
                }
            )
            if (
                token.observation_index % self.saved_frame_stride == 0
                or token.observation_index in {190, 200, 230, 260, 690}
            ):
                path = (
                    self.output_dir
                    / "frames"
                    / name
                    / f"frame_{token.observation_index:04d}.png"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(rgb, mode="RGB").save(path)
                mask_path = (
                    self.output_dir
                    / "liquid_masks"
                    / name
                    / f"mask_{token.observation_index:04d}.png"
                )
                mask_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(liquid_mask.astype(np.uint8) * 255, mode="L").save(
                    mask_path
                )
        visible_cameras = sum(
            int(part["visible_pixel_count"] > 0) for part in evidence_parts
        )
        if visible_cameras < self.minimum_visible_cameras:
            raise ValueError(
                "online_liquid_visible_camera_count_insufficient:"
                f"required={self.minimum_visible_cameras}:actual={visible_cameras}"
            )
        self.last_liquid_evidence = {
            "source": "semantic_segmentation_online_liquid",
            "cameras": evidence_parts,
        }
        self.last_liquid_evidence_sha256 = _canonical_json_sha256(evidence_parts)
        return arrays


def _create_capture_resources(
    rep: Any,
    *,
    camera_paths: Mapping[str, str],
    width: int,
    height: int,
) -> dict[str, dict[str, Any]]:
    resources = {}
    for name, camera_path in camera_paths.items():
        product = rep.create.render_product(camera_path, (width, height))
        rgb = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb.attach(product)
        semantic = rep.AnnotatorRegistry.get_annotator(
            "semantic_segmentation",
            init_params={"colorize": False},
        )
        semantic.attach(product)
        resources[name] = {
            "render_product": product,
            "rgb": rgb,
            "semantic": semantic,
        }
    return resources


def _destroy_capture_resources(resources: Mapping[str, Mapping[str, Any]]) -> None:
    for resource in resources.values():
        resource["rgb"].detach()
        resource["semantic"].detach()
        resource["render_product"].destroy()


def _table_height(stage: Any) -> float:
    from pxr import Usd, UsdGeom

    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
        useExtentsHint=True,
    )
    box = cache.ComputeWorldBound(stage.GetPrimAtPath("/World/table")).ComputeAlignedBox()
    return float(box.GetMax()[2])


def _run_isaac(args: argparse.Namespace) -> dict[str, Any]:
    from isaacsim import SimulationApp

    app = SimulationApp(
        {
            "headless": bool(args.headless),
            "width": int(args.width),
            "height": int(args.height),
            "renderer": "RayTracedLighting",
            "extra_args": ["--/rtx/raytracing/fractionalCutoutOpacity=true"],
        }
    )
    resources: dict[str, dict[str, Any]] = {}
    stepper = None
    try:
        import carb
        import omni
        import omni.physics.tensors
        import omni.physx.bindings._physx as pb
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd
        from pxr import Gf, UsdGeom, UsdUtils
        from tools.labutopia_fluid.real_beaker import (
            derive_authored_fluid_wrapper_frame,
        )
        from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
            StrictPhysicsStepper,
            _configure_physics_scene_for_pbd,
        )
        from tools.labutopia_fluid.run_interndata_pour_parity_probe import (
            PHYSICS_SCENE_PATH,
            _replicator_render_barrier,
        )

        settings = carb.settings.get_settings()
        settings.set(pb.SETTING_UPDATE_TO_USD, True)
        settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
        settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
        settings.set(pb.SETTING_DISPLAY_PARTICLES, getattr(pb.VisualizerMode, "NONE", 0))
        settings.set_bool(pb.SETTING_SUPPRESS_READBACK, False)
        settings.set_bool("/physics/suppressReadback", False)
        input_scene = Path(args.input_scene).resolve(strict=True)
        if _sha256_file(input_scene) != INPUT_SCENE_SHA256:
            raise ValueError("input_scene_sha256_mismatch")
        context = omni.usd.get_context()
        if not context.open_stage(str(input_scene)):
            raise RuntimeError("input_stage_open_failed")
        for _ in range(20):
            app.update()
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("input_stage_missing_after_open")
        stage.SetEditTarget(stage.GetRootLayer())
        timeline = omni.timeline.get_timeline_interface()
        timeline.stop()
        physics_settings = _configure_physics_scene_for_pbd(
            stage,
            PHYSICS_SCENE_PATH,
            integration_dt=INTEGRATION_DT,
            strict_mode=True,
        )
        if not math.isclose(
            float(physics_settings["effective_physics_dt"]),
            INTEGRATION_DT,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise RuntimeError("physics_integration_dt_mismatch")

        reconstruct, reconstruction_info = _load_live_reconstruction(
            Path(args.reconstruction_site_packages)
        )
        source_frame = derive_authored_fluid_wrapper_frame(
            stage,
            parent_path=SOURCE_ACTOR_PATH,
            visual_mesh_path=f"{SOURCE_ACTOR_PATH}/mesh",
        )
        target_frame = derive_authored_fluid_wrapper_frame(
            stage,
            parent_path=TARGET_ACTOR_PATH,
            visual_mesh_path=f"{TARGET_ACTOR_PATH}/mesh",
        )
        source_parent = stage.GetPrimAtPath(SOURCE_ACTOR_PATH)
        requested_source_body = source_body_mode_contract(
            args.source_body_mode,
            treatment=args.treatment,
        )
        initialization_source_body = apply_source_body_mode(
            source_parent,
            source_body_mode_contract(
                "kinematic",
                treatment=args.treatment,
            ),
        )
        initial_parent = UsdGeom.Xformable(source_parent).GetLocalTransformation()
        table_z = _table_height(stage)
        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        stepper = StrictPhysicsStepper.attach(
            interface=omni.physx.get_physx_simulation_interface(),
            logical_dt=PUBLIC_PHYSICS_DT,
            integration_dt=INTEGRATION_DT,
            substeps_per_logical_step=PHYSICS_SUBSTEPS_PER_FRAME,
            stage_id=stage_id,
        )
        stepper.step()
        read_strict_simulation_points(
            stage,
            PARTICLE_SET_PATH,
            expected_particle_count=PUBLIC_PARTICLE_COUNT,
        )
        initialization_summary = stepper.summary(requested_steps=1)
        if not initialization_summary["exact_step_count_verified"]:
            raise RuntimeError("pre_episode_physx_initialization_failed")
        source_body = apply_source_body_mode(
            source_parent,
            requested_source_body,
        )
        activation_steps_before = (
            int(stepper.executed_logical_steps),
            int(stepper.executed_integration_steps),
        )
        app.update()
        activation_steps_after = (
            int(stepper.executed_logical_steps),
            int(stepper.executed_integration_steps),
        )
        if activation_steps_before != activation_steps_after:
            raise RuntimeError("source_body_activation_advanced_physics")
        source_body["activation_update_count"] = 1
        source_body["activation_advanced_physics"] = False
        source_body["initialization_mode"] = initialization_source_body
        read_strict_simulation_points(
            stage,
            PARTICLE_SET_PATH,
            expected_particle_count=PUBLIC_PARTICLE_COUNT,
        )
        episode_logical_step_origin = int(stepper.executed_logical_steps)
        episode_integration_step_origin = int(stepper.executed_integration_steps)
        tensor_simulation = omni.physics.tensors.create_simulation_view(
            "numpy", stage_id
        )
        source_view = tensor_simulation.create_rigid_body_view(SOURCE_ACTOR_PATH)
        if source_view.count != 1:
            raise RuntimeError(f"source_actor_view_count_invalid:{source_view.count}")
        source_indices = np.asarray([0], dtype=np.uint32)
        episode_reference_pose = (
            np.asarray(source_view.get_transforms(), dtype=np.float64)
            .reshape((-1, 7))[0]
            .tolist()
        )
        camera_paths = camera_paths_for_profile(args.camera_profile)
        missing_cameras = [
            path
            for path in camera_paths.values()
            if not stage.GetPrimAtPath(path).IsValid()
        ]
        if missing_cameras:
            raise RuntimeError(f"camera_prims_missing:{','.join(missing_cameras)}")
        active_contract = {
            **default_probe_contract(),
            "camera_profile": args.camera_profile,
            "active_camera_paths": camera_paths,
            "source_body": source_body,
            "reconstruction_contract_sha256": reconstruction_info[
                "contract_sha256"
            ],
        }
        runtime_contract_sha256 = _canonical_json_sha256(active_contract)
        implementation = implementation_identity()
        resources = _create_capture_resources(
            rep,
            camera_paths=camera_paths,
            width=args.width,
            height=args.height,
        )
        capture = _CaptureAdapter(
            rep=rep,
            resources=resources,
            output_dir=Path(args.out_dir),
            width=args.width,
            height=args.height,
            saved_frame_stride=args.saved_frame_stride,
            minimum_visible_cameras=(
                0 if args.camera_profile == "model" else len(camera_paths)
            ),
            camera_profile=args.camera_profile,
        )
        first_authoring = True
        authority: dict[str, Any] | None = None
        material: dict[str, Any] | None = None

        def author(mesh_data: Mapping[str, Any], token: SurfaceFrameToken):
            nonlocal first_authoring, authority, material
            record = update_live_surface_mesh(stage, mesh_data, token)
            if first_authoring:
                material = author_live_surface_material(stage)
                authority = configure_live_visual_authority(stage)
                first_authoring = False
            return record

        render_index = 0

        def render(token: SurfaceFrameToken):
            nonlocal render_index
            surface_prim = stage.GetPrimAtPath(SURFACE_PATH)
            surface_token_attr = surface_prim.GetAttribute(
                "labutopia:surfaceFrameToken"
            )
            surface_token_before = (
                surface_token_attr.Get() if surface_token_attr else None
            )
            barrier = _replicator_render_barrier(
                rep,
                timeline,
                rt_subframes=args.rt_subframes,
                stepper=stepper,
            )
            surface_token_after = (
                surface_token_attr.Get() if surface_token_attr else None
            )
            if surface_token_before != surface_token_after:
                raise RuntimeError("surface_token_changed_during_render")
            render_index += 1
            return {
                "render_token": hashlib.sha256(
                    f"{token.identity}:{render_index}".encode("ascii")
                ).hexdigest(),
                "surface_token": surface_token_after,
                "logical_steps_before": (
                    barrier["logical_steps_before"] - episode_logical_step_origin
                ),
                "logical_steps_after": (
                    barrier["logical_steps_after"] - episode_logical_step_origin
                ),
                "integration_steps_before": (
                    barrier["integration_steps_before"]
                    - episode_integration_step_origin
                ),
                "integration_steps_after": (
                    barrier["integration_steps_after"]
                    - episode_integration_step_origin
                ),
                "timeline_time_before": barrier["timeline_time_before"],
                "timeline_time_after": barrier["timeline_time_after"],
            }

        runtime = OnlineFluidSurfaceRuntime(
            expected_particle_count=PUBLIC_PARTICLE_COUNT,
            physics_substeps_per_observation=PHYSICS_SUBSTEPS_PER_FRAME,
            physics_substep_dt=INTEGRATION_DT,
            reconstruct=reconstruct,
            author_surface=author,
            invalidate_surface=lambda reason: invalidate_live_surface(stage, reason),
            render_surface=render,
            capture_cameras=capture,
        )
        episode_id = f"{args.treatment}-1"
        runtime.reset_episode(episode_id)
        output_dir = Path(args.out_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        records_path = output_dir / "online_observations.jsonl"
        records_path.write_text("", encoding="utf-8")
        records: list[dict[str, Any]] = []
        plan = build_treatment_plan(args.treatment)
        if args.max_steps is not None:
            plan = plan[: int(args.max_steps) + 1]
        started = time.monotonic()
        for state in plan:
            if time.monotonic() - started > args.runtime_timeout_seconds:
                raise TimeoutError("online_surface_probe_timeout")
            observation_index = int(state["step_index"])
            current_parent = (
                initial_parent
                if args.treatment == "hold"
                else _kinematic_parent_matrix(
                    state=state,
                    initial_parent=initial_parent,
                    source_frame=source_frame,
                    target_frame=target_frame,
                )
            )
            target_pose = matrix_to_physx_pose(current_parent)
            if args.source_body_mode == "kinematic":
                action_commitment = target_pose
            else:
                action_commitment = {
                    "command": "hold_no_external_command",
                    "source_body_mode": "dynamic",
                }
            action_sha256 = _canonical_json_sha256(action_commitment)
            logical_before = (
                int(stepper.executed_logical_steps) - episode_logical_step_origin
            )
            integration_before = (
                int(stepper.executed_integration_steps)
                - episode_integration_step_origin
            )
            if observation_index > 0:
                if args.source_body_mode == "kinematic":
                    source_view.set_kinematic_targets(
                        np.asarray([target_pose], dtype=np.float32),
                        source_indices,
                    )
                stepper.step()
            logical_after = (
                int(stepper.executed_logical_steps) - episode_logical_step_origin
            )
            integration_after = (
                int(stepper.executed_integration_steps)
                - episode_integration_step_origin
            )
            actual_pose = (
                np.asarray(source_view.get_transforms(), dtype=np.float64)
                .reshape((-1, 7))[0]
                .tolist()
            )
            pose_error = kinematic_pose_error(target_pose, actual_pose)
            reference_pose_error = kinematic_pose_error(
                episode_reference_pose,
                actual_pose,
            )
            actual_parent = physx_pose_to_matrix(actual_pose)
            current_source_frame = _frame_at_parent_matrix(
                source_frame,
                initial_parent,
                actual_parent,
            )
            positions = read_strict_simulation_points(
                stage,
                PARTICLE_SET_PATH,
                expected_particle_count=PUBLIC_PARTICLE_COUNT,
            )
            counts = classify_two_beaker_positions(
                positions,
                source_frame=current_source_frame,
                target_frame=target_frame,
                table_z=table_z,
            )
            transition = build_observation_transition(
                episode_id=episode_id,
                observation_index=observation_index,
                logical_step_before=logical_before,
                logical_step_after=logical_after,
                integration_step_before=integration_before,
                integration_step_after=integration_after,
                action_sha256=(
                    None
                    if observation_index == 0
                    else action_sha256
                ),
            )
            record = runtime.process_observation(transition, positions)
            record["treatment"] = args.treatment
            record["camera_profile"] = args.camera_profile
            record["source_body_mode"] = args.source_body_mode
            record["input_scene_sha256"] = INPUT_SCENE_SHA256
            record["runtime_contract_sha256"] = runtime_contract_sha256
            record["implementation_sha256"] = implementation["sha256"]
            record["phase"] = state["phase"]
            record["action"] = {
                "command_sha256": action_sha256,
                "actual_pose_xyzw": [float(value) for value in actual_pose],
                "reference_pose_xyzw": [
                    float(value) for value in episode_reference_pose
                ],
                "reference_pose_error": reference_pose_error,
                "driver": source_body["action_driver"],
            }
            if args.source_body_mode == "kinematic":
                record["action"].update(
                    {
                        "target_pose_xyzw": [
                            float(value) for value in target_pose
                        ],
                        "target_pose_sha256": action_sha256,
                        "pose_error": pose_error,
                    }
                )
            else:
                record["action"]["command"] = "hold_no_external_command"
            if observation_index > 0 and (
                record["action_sha256"] != record["action"]["command_sha256"]
            ):
                raise RuntimeError("action_commitment_mismatch")
            record["raw_particle_counts"] = counts
            if observation_index == 0:
                record["initial_particle_snapshot"] = (
                    write_initial_particle_snapshot(
                        output_dir / "initial_simulation_points.npy",
                        positions,
                    )
                )
            if (
                capture.last_liquid_evidence_sha256 is None
                or capture.last_liquid_evidence is None
            ):
                raise RuntimeError("liquid_evidence_hash_missing")
            record["liquid_evidence_sha256"] = (
                capture.last_liquid_evidence_sha256
            )
            record["liquid_pixel_evidence"] = capture.last_liquid_evidence
            records.append(record)
            _append_jsonl(records_path, record)

        latencies = [record["latency_seconds"]["total"] for record in records[1:]]
        visibility_by_camera: dict[str, list[int]] = {
            name: [] for name in camera_paths
        }
        for record in records:
            for camera in record["liquid_pixel_evidence"]["cameras"]:
                visibility_by_camera[camera["camera"]].append(
                    int(camera["visible_pixel_count"])
                )
        camera_visibility = {
            name: {
                "minimum_visible_pixel_count": min(counts),
                "maximum_visible_pixel_count": max(counts),
                "visible_observation_count": sum(count > 0 for count in counts),
                "observation_count": len(counts),
            }
            for name, counts in visibility_by_camera.items()
        }
        if args.camera_profile == "model" and not any(
            item["maximum_visible_pixel_count"] > 0
            for item in camera_visibility.values()
        ):
            raise RuntimeError("online_liquid_never_visible_in_model_cameras")
        summary = {
            "schema_version": 1,
            "status": "RUN_COMPLETE",
            "runtime_integrity": "PASS",
            "causality_gate": "NOT_EVALUATED_SINGLE_TREATMENT",
            "claim": "single_treatment_same_state_physics_driven_online_surface_rendering",
            "treatment": args.treatment,
            "source_body": source_body,
            "contract": active_contract,
            "runtime_contract_sha256": runtime_contract_sha256,
            "implementation": implementation,
            "input": {
                "path": str(input_scene),
                "sha256": _sha256_file(input_scene),
            },
            "reconstruction": reconstruction_info,
            "observation_count": len(records),
            "first_observation": records[0],
            "last_observation": records[-1],
            "initial_particle_snapshot": records[0][
                "initial_particle_snapshot"
            ],
            "dynamic_hold_quality": (
                summarize_dynamic_hold_quality(records)
                if args.source_body_mode == "dynamic"
                else None
            ),
            "latency_seconds": {
                "warm_count": len(latencies),
                "p50": float(np.percentile(latencies, 50)) if latencies else None,
                "p95": float(np.percentile(latencies, 95)) if latencies else None,
                "maximum": max(latencies, default=None),
            },
            "camera_liquid_visibility": camera_visibility,
            "visual_authority": authority,
            "material": material,
            "strict_physics": stepper.summary(requested_steps=len(records)),
            "pre_episode_physx_initialization": initialization_summary,
            "forbidden_runtime_inputs": {
                "offline_position_log": False,
                "reconstructed_archive": False,
                "prebuilt_surface_directory": False,
            },
            "records_path": str(records_path),
        }
        _write_json(output_dir / "online_surface_manifest.json", summary)
        return summary
    except BaseException as exc:
        failure = {
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }
        try:
            _write_json(Path(args.out_dir).resolve() / "fatal_error.json", failure)
        except Exception:
            pass
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr, flush=True)
        raise
    finally:
        if resources:
            try:
                _destroy_capture_resources(resources)
            except Exception:
                pass
        if stepper is not None:
            try:
                stepper.detach()
            except Exception:
                pass
        app.close()


def parse_args(contract: Mapping[str, Any] | None = None) -> argparse.Namespace:
    cfg = default_probe_contract() if contract is None else dict(contract)
    parser = argparse.ArgumentParser(
        description="Run online current-state surface reconstruction in strict PhysX"
    )
    parser.add_argument("--treatment", choices=("pour", "hold"), default="pour")
    parser.add_argument(
        "--source-body-mode",
        choices=("kinematic", "dynamic"),
        default=cfg["source_body_mode"],
    )
    parser.add_argument("--input-scene", default=cfg["input_scene"])
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--width", type=int, default=cfg["camera_resolution"][0])
    parser.add_argument("--height", type=int, default=cfg["camera_resolution"][1])
    parser.add_argument(
        "--camera-profile",
        choices=tuple(CAMERA_PROFILES),
        default=cfg["default_camera_profile"],
    )
    parser.add_argument(
        "--saved-frame-stride", type=int, default=cfg["saved_frame_stride"]
    )
    parser.add_argument("--rt-subframes", type=int, default=cfg["rt_subframes"])
    parser.add_argument(
        "--reconstruction-site-packages",
        default=cfg["reconstruction_site_packages"],
    )
    parser.add_argument("--runtime-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument(
        "--headless", action=argparse.BooleanOptionalAction, default=True
    )
    args = parser.parse_args()
    if args.width <= 0 or args.height <= 0:
        parser.error("width and height must be positive")
    if args.saved_frame_stride <= 0 or args.rt_subframes <= 0:
        parser.error("frame stride and rt subframes must be positive")
    if args.max_steps is not None and args.max_steps < 0:
        parser.error("max steps must be nonnegative")
    try:
        source_body_mode_contract(
            args.source_body_mode,
            treatment=args.treatment,
        )
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main() -> int:
    args = parse_args()
    summary = _run_isaac(args)
    print(json.dumps(_json_safe(summary), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
