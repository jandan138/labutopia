#!/usr/bin/env python3
"""Measure true asynchronous RTX-completed CUDA frames for liquid_0812.

This is deliberately a separate experimental protocol.  It does not weaken or
replace the synchronous, current-state artifact-ready contract implemented by
``run_isaac41_liquid0812_benchmark.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import statistics
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import run_isaac41_liquid0812_benchmark as baseline


FORMAL_ISAAC41_PYTHON = baseline.FORMAL_ISAAC41_PYTHON
DEFAULT_SCENE = baseline.DEFAULT_SCENE
DEFAULT_PACKET = baseline.DEFAULT_PACKET
CAMERA_PATH = baseline.CAMERA_PATH
BENCHMARK_CAMERA_PATH = "/World/LabUtopiaAsyncRtxCamera"
PHYSICS_HZ = baseline.PHYSICS_HZ
PHYSICS_DT = baseline.PHYSICS_DT
EXPECTED_OBSERVATIONS = baseline.EXPECTED_OBSERVATIONS
LANES = ("headless-product", "offscreen-viewport")
PROFILES = ("current", "fast-translucent", "fast-glass", "fast-opaque")
CAMERA_POLICIES = ("trajectory-follow", "trajectory-envelope", "benchmark", "scene")
TARGET_RENDER_HZ = 50
DEFAULT_WIDTH = 256
DEFAULT_HEIGHT = 256
SOURCE_SEMANTIC_LABEL = "labutopia_source_beaker"
SYNC_WINDOW_RADIUS = 4
MIN_SOURCE_MASK_PIXELS = 8
MAX_PROJECTED_CENTER_ERROR_PX = 8.0
MIN_TRAJECTORY_DIRECTION_COSINE = 0.8
MIN_TRAJECTORY_MAGNITUDE_RATIO = 0.7
MAX_TRAJECTORY_MAGNITUDE_RATIO = 1.3


def source_paths() -> tuple[Path, ...]:
    return tuple(dict.fromkeys((*baseline.source_paths(), Path(__file__).resolve())))


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _summarize_ms(values: Sequence[float]) -> dict[str, Any]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {"count": 0, "mean_ms": None, "median_ms": None, "p95_ms": None, "max_ms": None}
    ordered = sorted(finite)
    p95_index = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return {
        "count": len(ordered),
        "mean_ms": statistics.fmean(ordered),
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[p95_index],
        "max_ms": ordered[-1],
    }


def _target_render_count(observation_count: int) -> int:
    return math.ceil(observation_count * TARGET_RENDER_HZ / PHYSICS_HZ)


def _physics_index_for_render(render_index: int) -> int:
    return (render_index * PHYSICS_HZ) // TARGET_RENDER_HZ


def _sync_audit_physics_indices(source_poses_xyzw: Any) -> dict[str, list[int]]:
    import numpy as np

    poses = np.asarray(source_poses_xyzw, dtype=np.float64)
    if poses.ndim != 2 or poses.shape[1] != 7 or len(poses) < 9:
        raise ValueError("visible_sync_source_poses_invalid")
    first_tilt = baseline._first_tilt_observation(np, poses)
    translation_limit = max(2, min(first_tilt, len(poses)))
    translation_speeds = np.linalg.norm(np.diff(poses[:translation_limit, :3], axis=0), axis=1)
    translation_center = int(np.argmax(translation_speeds)) + 1
    initial_q = poses[0, 3:] / np.linalg.norm(poses[0, 3:])
    angular = []
    for quaternion in poses[:, 3:]:
        normalized = quaternion / np.linalg.norm(quaternion)
        cosine = min(1.0, max(-1.0, abs(float(np.dot(initial_q, normalized)))))
        angular.append(math.degrees(2.0 * math.acos(cosine)))
    half_max = max(angular) * 0.5
    tilt_center = min(range(len(angular)), key=lambda index: abs(angular[index] - half_max))

    def window(center: int) -> list[int]:
        start = min(max(0, center - SYNC_WINDOW_RADIUS), len(poses) - 9)
        return list(range(start, start + 9))

    return {
        "static": list(range(9)),
        "translation_lift": window(translation_center),
        "mid_tilt": window(tilt_center),
        "final_settle": list(range(len(poses) - 9, len(poses))),
    }


def _first_render_index_for_physics(physics_index: int, render_count: int) -> int:
    for render_index in range(render_count):
        if _physics_index_for_render(render_index) == physics_index:
            return render_index
    raise ValueError(f"physics_state_has_no_render:{physics_index}:{render_count}")


def _project_world_point(
    point: Any,
    *,
    eye: Any,
    target: Any,
    width: int,
    height: int,
    focal_length_mm: float,
    horizontal_aperture_mm: float,
    vertical_aperture_mm: float,
) -> tuple[float, float]:
    import numpy as np

    eye_value = np.asarray(eye, dtype=np.float64)
    forward = np.asarray(target, dtype=np.float64) - eye_value
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.asarray([0.0, 0.0, 1.0], dtype=np.float64))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    relative = np.asarray(point, dtype=np.float64) - eye_value
    depth = float(relative @ forward)
    if depth <= 0.0:
        raise ValueError("projected_point_behind_camera")
    tangent_x = horizontal_aperture_mm / (2.0 * focal_length_mm)
    tangent_y = vertical_aperture_mm / (2.0 * focal_length_mm)
    pixel_x = (0.5 + float(relative @ right) / (2.0 * depth * tangent_x)) * width
    pixel_y = (0.5 - float(relative @ up) / (2.0 * depth * tangent_y)) * height
    return pixel_x, pixel_y


def _source_instance_ids(info: dict[str, Any]) -> list[int]:
    semantics = info.get("idToSemantics", {})
    if isinstance(semantics, dict) and "idToSemantics" in semantics:
        semantics = semantics["idToSemantics"]
    result = []
    for raw_id, labels in semantics.items():
        if isinstance(labels, dict) and SOURCE_SEMANTIC_LABEL in str(labels.get("class", "")):
            result.append(int(raw_id))
    return sorted(result)


def _evaluate_visible_sync_records(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    import numpy as np

    checks = []
    for record in records:
        observed = np.asarray(record["mask_centroid_px"], dtype=np.float64)
        projected = np.asarray(record["projected_center_px"], dtype=np.float64)
        error = float(np.linalg.norm(observed - projected))
        checks.append(
            {
                **record,
                "projected_center_error_px": error,
                "passed": int(record["mask_pixel_count"]) >= MIN_SOURCE_MASK_PIXELS
                and error <= MAX_PROJECTED_CENTER_ERROR_PX,
            }
        )
    stage_centers = []
    for stage_name in ("static", "translation_lift", "mid_tilt", "final_settle"):
        stage_records = [item for item in checks if item["stage"] == stage_name]
        if not stage_records:
            continue
        stage_centers.append(
            {
                "stage": stage_name,
                "observed": np.mean([item["mask_centroid_px"] for item in stage_records], axis=0),
                "projected": np.mean([item["projected_center_px"] for item in stage_records], axis=0),
            }
        )
    displacement_checks = []
    for left, right in zip(stage_centers, stage_centers[1:]):
        observed = right["observed"] - left["observed"]
        projected = right["projected"] - left["projected"]
        observed_norm = float(np.linalg.norm(observed))
        projected_norm = float(np.linalg.norm(projected))
        if projected_norm <= 1.0e-9:
            cosine = 1.0 if observed_norm <= 1.0 else 0.0
            ratio = 1.0 if observed_norm <= 1.0 else float("inf")
        else:
            cosine = float(observed @ projected / max(1.0e-12, observed_norm * projected_norm))
            ratio = observed_norm / projected_norm
        displacement_checks.append(
            {
                "from": left["stage"],
                "to": right["stage"],
                "direction_cosine": cosine,
                "magnitude_ratio": ratio,
                "passed": cosine >= MIN_TRAJECTORY_DIRECTION_COSINE
                and MIN_TRAJECTORY_MAGNITUDE_RATIO <= ratio <= MAX_TRAJECTORY_MAGNITUDE_RATIO,
            }
        )
    expected_count = 4 * 9
    return {
        "passed": len(checks) == expected_count
        and all(item["passed"] for item in checks)
        and len(displacement_checks) == 3
        and all(item["passed"] for item in displacement_checks),
        "expected_record_count": expected_count,
        "actual_record_count": len(checks),
        "thresholds": {
            "minimum_mask_pixels": MIN_SOURCE_MASK_PIXELS,
            "maximum_projected_center_error_px": MAX_PROJECTED_CENTER_ERROR_PX,
            "minimum_direction_cosine": MIN_TRAJECTORY_DIRECTION_COSINE,
            "magnitude_ratio_range": [MIN_TRAJECTORY_MAGNITUDE_RATIO, MAX_TRAJECTORY_MAGNITUDE_RATIO],
        },
        "records": checks,
        "displacements": displacement_checks,
    }


def _configure_profile(stage: Any, profile: str) -> dict[str, Any]:
    import carb

    if profile not in PROFILES:
        raise ValueError(f"unknown_rtx_profile:{profile}")
    settings = carb.settings.get_settings()
    paths = (
        "/rtx/rendermode",
        "/rtx/post/aa/op",
        "/rtx/reflections/enabled",
        "/rtx/indirectDiffuse/enabled",
        "/rtx/post/motionblur/enabled",
        "/rtx/shadows/enabled",
        "/rtx/translucency/enabled",
        "/rtx/translucency/maxRefractionBounces",
        "/app/hydraEngine/waitIdle",
    )
    before = {path: settings.get(path) for path in paths}
    authored_material = None
    if profile != "current":
        settings.set_int("/rtx/post/aa/op", 0)
        settings.set_bool("/rtx/reflections/enabled", False)
        settings.set_bool("/rtx/indirectDiffuse/enabled", False)
        settings.set_bool("/rtx/post/motionblur/enabled", False)
        settings.set_bool("/rtx/shadows/enabled", False)
        settings.set_int("/rtx/translucency/maxRefractionBounces", 1)
        for suffix, value in (
            ("post/aa/op", 0),
            ("reflections/enabled", False),
            ("indirectDiffuse/enabled", False),
            ("post/motionblur/enabled", False),
            ("shadows/enabled", False),
        ):
            settings.set(f"/rtx-defaults/{suffix}", value)
    if profile == "fast-translucent":
        settings.set_bool("/rtx/translucency/enabled", True)
    elif profile == "fast-glass":
        # Preserve the complete glass-lighting path and remove only indirect
        # diffuse.  In this Isaac build AA op 3 is the fast DLSS path; op 0
        # renders native pixels and was both slower and not visibly better.
        settings.set_int("/rtx/post/aa/op", 3)
        settings.set("/rtx-defaults/post/aa/op", 3)
        settings.set_bool("/rtx/reflections/enabled", True)
        settings.set("/rtx-defaults/reflections/enabled", True)
        settings.set_bool("/rtx/shadows/enabled", True)
        settings.set("/rtx-defaults/shadows/enabled", True)
        settings.set_bool("/rtx/translucency/enabled", True)
        settings.set_int("/rtx/translucency/maxRefractionBounces", 2)
    elif profile == "fast-opaque":
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

        settings.set_bool("/rtx/translucency/enabled", False)
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            looks = "/World/Looks"
            if not stage.GetPrimAtPath(looks):
                UsdGeom.Scope.Define(stage, looks)
            material_path = f"{looks}/LabUtopiaAsyncFastOpaqueLiquid"
            material = UsdShade.Material.Define(stage, material_path)
            shader = UsdShade.Shader.Define(stage, f"{material_path}/PreviewSurface")
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(0.03, 0.62, 0.88)
            )
            shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
                Gf.Vec3f(0.01, 0.10, 0.16)
            )
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.25)
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
            shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            bound_paths = []
            for prim_path in (baseline.PARTICLE_SYSTEM_PATH, baseline.PARTICLE_SET_PATH):
                prim = stage.GetPrimAtPath(prim_path)
                if prim and prim.IsValid():
                    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
                    bound_paths.append(prim_path)
        authored_material = {
            "path": material_path,
            "shader": "UsdPreviewSurface",
            "bound_paths": bound_paths,
            "diffuse_color": [0.03, 0.62, 0.88],
            "opacity": 1.0,
            "authored_in_memory_only": True,
            "authoring_layer": "anonymous_session_layer",
        }
    settings.set_bool("/app/hydraEngine/waitIdle", False)
    after = {path: settings.get(path) for path in paths}
    return {"profile": profile, "before": before, "after": after, "material": authored_material}


def _author_source_semantics(stage: Any) -> dict[str, Any]:
    from pxr import Semantics, Usd

    prim = stage.GetPrimAtPath(baseline.SOURCE_PATH)
    if not prim or not prim.IsValid():
        raise RuntimeError("visible_sync_source_prim_missing")
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        semantic = Semantics.SemanticsAPI.Get(prim, "LabUtopiaVisibleSync")
        if not semantic:
            semantic = Semantics.SemanticsAPI.Apply(prim, "LabUtopiaVisibleSync")
        semantic.CreateSemanticTypeAttr().Set("class")
        semantic.CreateSemanticDataAttr().Set(SOURCE_SEMANTIC_LABEL)
    return {
        "prim_path": baseline.SOURCE_PATH,
        "type": "class",
        "label": SOURCE_SEMANTIC_LABEL,
        "authoring_layer": "anonymous_session_layer",
        "input_usd_mutated": False,
    }


def _trajectory_envelope_camera_contract(
    *,
    source_bounds: dict[str, Any],
    target_bounds: dict[str, Any],
    source_poses_xyzw: Any,
    table_z: float,
) -> dict[str, Any]:
    """Fit a fixed camera around the complete source trajectory and target.

    A sphere is deliberately used instead of fitting only the initial source
    and target bounds.  A sphere remains inside the camera frustum for every
    view direction when the distance is derived from the narrowest FOV.
    """
    import numpy as np

    poses = np.asarray(source_poses_xyzw, dtype=np.float64)
    if poses.ndim != 2 or poses.shape[1] != 7 or not np.isfinite(poses).all():
        raise ValueError("trajectory_camera_source_poses_invalid")
    source_extent = np.asarray(source_bounds["extent"], dtype=np.float64)
    source_radius = float(np.linalg.norm(source_extent) * 0.5)
    # The packet trajectory is aligned to the runtime rigid body later by the
    # benchmark.  Apply the same translation convention here so a localized
    # scene remains framed even when its absolute origin differs from packet
    # authoring space.
    source_centers = (
        np.asarray(source_bounds["center"], dtype=np.float64)
        + poses[:, :3]
        - poses[0, :3]
    )
    minimum = np.minimum(
        source_centers.min(axis=0) - source_radius,
        np.asarray(target_bounds["minimum"], dtype=np.float64),
    )
    maximum = np.maximum(
        source_centers.max(axis=0) + source_radius,
        np.asarray(target_bounds["maximum"], dtype=np.float64),
    )
    minimum[2] = min(float(minimum[2]), float(table_z) - 0.01)

    unpadded_extent = maximum - minimum
    padding = np.maximum(unpadded_extent * 0.08, np.asarray([0.015, 0.015, 0.015]))
    minimum -= padding
    maximum += padding
    center = (minimum + maximum) * 0.5
    radius = float(np.linalg.norm(maximum - minimum) * 0.5)

    focal_length_mm = 26.0
    horizontal_aperture_mm = 24.0
    vertical_aperture_mm = 16.0
    horizontal_fov = 2.0 * math.atan(horizontal_aperture_mm / (2.0 * focal_length_mm))
    vertical_fov = 2.0 * math.atan(vertical_aperture_mm / (2.0 * focal_length_mm))
    limiting_fov = min(horizontal_fov, vertical_fov)
    distance = radius / math.sin(limiting_fov * 0.5)
    side_y = 1.0 if poses[0, 1] >= float(target_bounds["center"][1]) else -1.0
    view_direction = np.asarray([0.55, side_y, 0.65], dtype=np.float64)
    view_direction /= np.linalg.norm(view_direction)
    eye = center + view_direction * distance

    return {
        "eye": eye.tolist(),
        "target": center.tolist(),
        "focal_length_mm": focal_length_mm,
        "horizontal_aperture_mm": horizontal_aperture_mm,
        "vertical_aperture_mm": vertical_aperture_mm,
        "envelope": {
            "minimum": minimum.tolist(),
            "maximum": maximum.tolist(),
            "center": center.tolist(),
            "radius_m": radius,
            "source_radius_m": source_radius,
            "padding_fraction": 0.08,
            "minimum_padding_m": 0.015,
            "source_pose_count": int(poses.shape[0]),
        },
        "framing_contract": {
            "method": "complete_trajectory_padded_bounding_sphere",
            "limiting_fov_degrees": math.degrees(limiting_fov),
            "camera_distance_m": distance,
            "sphere_angular_radius_degrees": math.degrees(math.asin(radius / distance)),
            "all_source_pose_centers_inside_envelope": bool(
                np.all(source_centers >= minimum) and np.all(source_centers <= maximum)
            ),
            "target_bounds_inside_envelope": bool(
                np.all(np.asarray(target_bounds["minimum"]) >= minimum)
                and np.all(np.asarray(target_bounds["maximum"]) <= maximum)
            ),
            "tabletop_inside_envelope": bool(minimum[2] <= table_z <= maximum[2]),
        },
    }


def _fit_follow_camera_pose(
    *,
    source_center: Any,
    source_radius: float,
    target_bounds: dict[str, Any],
    table_z: float,
) -> dict[str, Any]:
    """Fit one deterministic camera pose to the current source and target."""
    import numpy as np

    source_center = np.asarray(source_center, dtype=np.float64)
    target_minimum = np.asarray(target_bounds["minimum"], dtype=np.float64)
    target_maximum = np.asarray(target_bounds["maximum"], dtype=np.float64)
    source_minimum = source_center - float(source_radius)
    source_maximum = source_center + float(source_radius)
    minimum = np.minimum(source_minimum, target_minimum)
    maximum = np.maximum(source_maximum, target_maximum)
    minimum[2] = min(float(minimum[2]), float(table_z) - 0.005)
    unpadded_extent = maximum - minimum
    padding = np.maximum(unpadded_extent * 0.04, np.asarray([0.008, 0.008, 0.008]))
    minimum -= padding
    maximum += padding
    center = (minimum + maximum) * 0.5

    # The pour primarily travels in Y. Looking across X keeps that separation
    # on the wider horizontal sensor axis instead of the tighter vertical FOV.
    view_direction = np.asarray([1.0, 0.0, 0.55], dtype=np.float64)
    view_direction /= np.linalg.norm(view_direction)
    forward = -view_direction
    world_up = np.asarray([0.0, 0.0, 1.0], dtype=np.float64)
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    focal_length_mm = 26.0
    horizontal_aperture_mm = 24.0
    vertical_aperture_mm = 16.0
    tan_horizontal = horizontal_aperture_mm / (2.0 * focal_length_mm)
    tan_vertical = vertical_aperture_mm / (2.0 * focal_length_mm)
    corners = np.asarray(
        [
            [x, y, z]
            for x in (minimum[0], maximum[0])
            for y in (minimum[1], maximum[1])
            for z in (minimum[2], maximum[2])
        ],
        dtype=np.float64,
    )
    relative = corners - center
    required_distance = max(
        max(
            abs(float(point @ right)) / tan_horizontal - float(point @ forward),
            abs(float(point @ up)) / tan_vertical - float(point @ forward),
            -float(point @ forward) + 0.01,
        )
        for point in relative
    )
    distance = required_distance * 1.04
    eye = center + view_direction * distance
    return {
        "eye": eye.tolist(),
        "target": center.tolist(),
        "camera_distance_m": float(distance),
        "envelope_minimum": minimum.tolist(),
        "envelope_maximum": maximum.tolist(),
    }


def _source_follow_camera_contract(
    *,
    source_bounds: dict[str, Any],
    target_bounds: dict[str, Any],
    source_poses_xyzw: Any,
    table_z: float,
) -> dict[str, Any]:
    import numpy as np

    poses = np.asarray(source_poses_xyzw, dtype=np.float64)
    if poses.ndim != 2 or poses.shape[1] != 7 or not np.isfinite(poses).all():
        raise ValueError("follow_camera_source_poses_invalid")
    initial_center = np.asarray(source_bounds["center"], dtype=np.float64)
    source_centers = initial_center + poses[:, :3] - poses[0, :3]
    source_radius = float(
        np.linalg.norm(np.asarray(source_bounds["extent"], dtype=np.float64)) * 0.5
    )
    frame_poses = [
        _fit_follow_camera_pose(
            source_center=center,
            source_radius=source_radius,
            target_bounds=target_bounds,
            table_z=table_z,
        )
        for center in source_centers
    ]
    distances = [float(frame["camera_distance_m"]) for frame in frame_poses]
    return {
        "frame_poses": frame_poses,
        "source_pose_count": int(poses.shape[0]),
        "source_radius_m": source_radius,
        "minimum_camera_distance_m": min(distances),
        "maximum_camera_distance_m": max(distances),
        "same_physics_state_reuses_camera_pose": True,
        "physics_changes": False,
        "method": "per_physics_state_source_target_perspective_fit",
    }


def _author_camera_pose(stage: Any, camera_path: str, pose: dict[str, Any]) -> None:
    from pxr import Gf, UsdGeom

    camera = UsdGeom.Camera(stage.GetPrimAtPath(camera_path))
    if not camera:
        raise RuntimeError(f"follow_camera_missing:{camera_path}")
    transform = Gf.Matrix4d(1).SetLookAt(
        Gf.Vec3d(*pose["eye"]),
        Gf.Vec3d(*pose["target"]),
        Gf.Vec3d(0.0, 0.0, 1.0),
    ).GetInverse()
    ops = camera.GetOrderedXformOps()
    if len(ops) != 1:
        raise RuntimeError(f"follow_camera_transform_op_count:{len(ops)}")
    ops[0].Set(transform)


def _define_benchmark_camera(stage: Any, packet: Any, policy: str) -> dict[str, Any]:
    """Author a reproducible close lab camera in the anonymous session layer."""
    if policy == "scene":
        return {
            "camera_path": CAMERA_PATH,
            "policy": policy,
            "authored": False,
        }
    if policy not in {"benchmark", "trajectory-envelope", "trajectory-follow"}:
        raise ValueError(f"unknown_camera_policy:{policy}")

    from pxr import Gf, Usd, UsdGeom

    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
        useExtentsHint=True,
    )

    def bounds(path: str) -> dict[str, Any]:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise RuntimeError(f"benchmark_camera_prim_missing:{path}")
        aligned = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        minimum = tuple(float(value) for value in aligned.GetMin())
        maximum = tuple(float(value) for value in aligned.GetMax())
        if not all(math.isfinite(value) for value in (*minimum, *maximum)):
            raise RuntimeError(f"benchmark_camera_nonfinite_bounds:{path}")
        center = tuple((minimum[index] + maximum[index]) * 0.5 for index in range(3))
        extent = tuple(maximum[index] - minimum[index] for index in range(3))
        return {"path": path, "minimum": minimum, "maximum": maximum, "center": center, "extent": extent}

    source = bounds(baseline.SOURCE_PATH)
    target = bounds(baseline.TARGET_PATH)
    table_z = float(packet.manifest["frames"]["table_top_z_m"])
    trajectory_contract = None
    follow_contract = None
    if policy == "trajectory-follow":
        follow_contract = _source_follow_camera_contract(
            source_bounds=source,
            target_bounds=target,
            source_poses_xyzw=packet.array(
                "source_poses_xyzw", (EXPECTED_OBSERVATIONS, 7)
            ),
            table_z=table_z,
        )
        eye = tuple(follow_contract["frame_poses"][0]["eye"])
        look_at = tuple(follow_contract["frame_poses"][0]["target"])
        pair_span = max(source["extent"][0], target["extent"][0])
    elif policy == "trajectory-envelope":
        trajectory_contract = _trajectory_envelope_camera_contract(
            source_bounds=source,
            target_bounds=target,
            source_poses_xyzw=packet.array(
                "source_poses_xyzw", (EXPECTED_OBSERVATIONS, 7)
            ),
            table_z=table_z,
        )
        eye = tuple(trajectory_contract["eye"])
        look_at = tuple(trajectory_contract["target"])
        pair_span = max(
            trajectory_contract["envelope"]["maximum"][index]
            - trajectory_contract["envelope"]["minimum"][index]
            for index in range(2)
        )
    else:
        focus = tuple(
            source["center"][index] * 0.58 + target["center"][index] * 0.42
            for index in range(2)
        )
        pair_span = max(
            abs(source["center"][0] - target["center"][0])
            + source["extent"][0] * 0.5
            + target["extent"][0] * 0.5,
            abs(source["center"][1] - target["center"][1])
            + source["extent"][1] * 0.5
            + target["extent"][1] * 0.5,
        )
        side_y = 1.0 if source["center"][1] >= target["center"][1] else -1.0
        look_at = (focus[0], focus[1], table_z + 0.072)
        eye = (
            focus[0] + max(0.22, pair_span * 0.42),
            focus[1] + side_y * max(0.33, pair_span * 0.76),
            table_z + 0.27,
        )
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        camera = UsdGeom.Camera.Define(stage, BENCHMARK_CAMERA_PATH)
        transform = Gf.Matrix4d(1).SetLookAt(
            Gf.Vec3d(*eye), Gf.Vec3d(*look_at), Gf.Vec3d(0.0, 0.0, 1.0)
        ).GetInverse()
        camera.ClearXformOpOrder()
        camera.AddTransformOp().Set(transform)
        camera.CreateFocalLengthAttr(26.0)
        camera.CreateHorizontalApertureAttr(24.0)
        camera.CreateVerticalApertureAttr(16.0)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
    return {
        "camera_path": BENCHMARK_CAMERA_PATH,
        "policy": policy,
        "authored": True,
        "authoring_layer": "anonymous_session_layer",
        "eye": list(eye),
        "target": list(look_at),
        "focal_length_mm": 26.0,
        "horizontal_aperture_mm": 24.0,
        "vertical_aperture_mm": 16.0,
        "source_bounds": source,
        "target_bounds": target,
        "pair_span_m": pair_span,
        "trajectory_envelope": (
            trajectory_contract["envelope"] if trajectory_contract else None
        ),
        "framing_contract": (
            trajectory_contract["framing_contract"] if trajectory_contract else None
        ),
        "follow_contract": (
            {key: value for key, value in follow_contract.items() if key != "frame_poses"}
            if follow_contract
            else None
        ),
        "follow_frame_poses": follow_contract["frame_poses"] if follow_contract else None,
    }


def _create_render_target(
    args: argparse.Namespace, application: Any, camera_path: str
) -> dict[str, Any]:
    import omni.replicator.core as rep

    if args.lane == "headless-product":
        product = rep.create.render_product(camera_path, (args.width, args.height))
        return {
            "product_path": product.path,
            "product": product,
            "viewport": None,
            "window": None,
            "kind": "direct_headless_render_product",
        }
    if args.lane != "offscreen-viewport":
        raise ValueError(f"unknown_lane:{args.lane}")
    from omni.isaac.core.utils import extensions

    extensions.enable_extension("omni.kit.viewport.window")
    for _ in range(8):
        application.update()
    from omni.kit.viewport.utility import create_viewport_window

    window = create_viewport_window(
        "LabUtopia Async RTX Offscreen",
        width=args.width,
        height=args.height,
    )
    if window is None or window.viewport_api is None:
        raise RuntimeError("offscreen_viewport_create_failed")
    viewport = window.viewport_api
    viewport.camera_path = camera_path
    viewport.resolution = (args.width, args.height)
    viewport.resolution_scale = 1
    for _ in range(8):
        application.update()
    product_path = viewport.get_render_product_path()
    if not product_path:
        raise RuntimeError("offscreen_viewport_render_product_missing")
    return {
        "product_path": product_path,
        "product": None,
        "viewport": viewport,
        "window": window,
        "kind": "retained_offscreen_viewport_render_product",
    }


class _CudaFrameSink:
    """Own CUDA frames until a fake consumer has completed a real GPU read."""

    def __init__(
        self,
        *,
        torch: Any,
        width: int,
        height: int,
        review_indices: set[int],
        full_frame_count: int = 0,
    ):
        self.torch = torch
        self.width = width
        self.height = height
        self.ring = torch.empty((3, 3, height, width), dtype=torch.uint8, device="cuda:0")
        self.slot_events: list[Any | None] = [None, None, None]
        self.slot_sequences: list[int | None] = [None, None, None]
        self.checksums: list[Any] = []
        self.review_indices = review_indices
        self.review_order = sorted(review_indices)
        self.review_slot = {frame: index for index, frame in enumerate(self.review_order)}
        self.review = torch.empty(
            (len(self.review_order), 3, height, width), dtype=torch.uint8, device="cuda:0"
        )
        self.full_frame_count = int(full_frame_count)
        self.full = (
            torch.empty(
                (self.full_frame_count, 3, height, width),
                dtype=torch.uint8,
                device="cuda:0",
            )
            if self.full_frame_count
            else None
        )
        self.backpressure_wait_ms: list[float] = []
        self.consumed_sequences: list[int] = []

    def publish(self, image_hwc: Any, sequence: int) -> dict[str, Any]:
        torch = self.torch
        slot = sequence % 3
        previous = self.slot_events[slot]
        if previous is not None:
            started = time.perf_counter()
            previous.synchronize()
            waited = (time.perf_counter() - started) * 1000.0
            if waited > 1.0e-6:
                self.backpressure_wait_ms.append(waited)
            previous_sequence = self.slot_sequences[slot]
            if previous_sequence is not None:
                self.consumed_sequences.append(previous_sequence)
        rgb = image_hwc[..., :3].permute(2, 0, 1)
        self.ring[slot].copy_(rgb, non_blocking=True)
        if self.full is not None:
            self.full[sequence].copy_(self.ring[slot], non_blocking=True)
        if sequence in self.review_slot:
            self.review[self.review_slot[sequence]].copy_(self.ring[slot], non_blocking=True)
        checksum = torch.sum(self.ring[slot][:, ::64, ::64], dtype=torch.int64)
        event = torch.cuda.Event(enable_timing=False, blocking=False)
        event.record(torch.cuda.current_stream())
        self.slot_events[slot] = event
        self.slot_sequences[slot] = sequence
        self.checksums.append(checksum)
        return {"slot": slot, "shape": [3, self.height, self.width], "dtype": "torch.uint8"}

    def drain(self) -> None:
        for slot, event in enumerate(self.slot_events):
            if event is None:
                continue
            event.synchronize()
            sequence = self.slot_sequences[slot]
            if sequence is not None:
                self.consumed_sequences.append(sequence)
        self.consumed_sequences.sort()


def _save_review_artifacts(output_dir: Path, sink: _CudaFrameSink, *, fps: int = 15) -> dict[str, Any]:
    import numpy as np
    from PIL import Image

    if not sink.review_order:
        return {"frame_count": 0, "video": None, "frames": []}
    frames = sink.review.cpu().numpy().transpose(0, 2, 3, 1)
    review_dir = output_dir / "review_frames"
    review_dir.mkdir(parents=True, exist_ok=True)
    frame_records = []
    for index, (render_index, frame) in enumerate(zip(sink.review_order, frames)):
        path = review_dir / f"frame_{index:04d}_render_{render_index:04d}.png"
        Image.fromarray(np.ascontiguousarray(frame), mode="RGB").save(path)
        frame_records.append({"render_index": render_index, **baseline._file_record(path)})
    video_path = output_dir / "liquid0812_async_rtx_review.mp4"
    command = [
        "/usr/bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{sink.width}x{sink.height}", "-framerate", str(fps),
        "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast",
        "-crf", "20", "-pix_fmt", "yuv420p", str(video_path),
    ]
    encoded = subprocess.run(
        command,
        input=np.ascontiguousarray(frames).tobytes(),
        check=False,
        capture_output=True,
    )
    if encoded.returncode != 0:
        raise RuntimeError(f"review_video_encode_failed:{encoded.returncode}:{encoded.stderr[-500:]!r}")
    return {
        "frame_count": len(frame_records),
        "sample_policy": "uniform_over_timed_render_sequence;gpu_snapshots_timed;cpu_readback_and_encoding_untimed",
        "fps": fps,
        "frames": frame_records,
        "video": baseline._file_record(video_path),
    }


def _save_full_video_artifacts(
    output_dir: Path,
    sink: _CudaFrameSink,
    records: Sequence[dict[str, Any]],
    *,
    lane: str,
    fps: int = TARGET_RENDER_HZ,
) -> dict[str, Any]:
    """Read the retained CUDA sequence back after timing and encode every frame."""
    import numpy as np

    if sink.full is None:
        raise RuntimeError("full_video_cuda_store_missing")
    if sink.full_frame_count != len(records):
        raise RuntimeError(
            f"full_video_frame_count_mismatch:{sink.full_frame_count}:{len(records)}"
        )

    readback_started = time.perf_counter()
    frames_chw = sink.full.cpu().numpy()
    readback_s = time.perf_counter() - readback_started
    expected_shape = (len(records), 3, sink.height, sink.width)
    if frames_chw.shape != expected_shape or frames_chw.dtype != np.uint8:
        raise RuntimeError(f"full_video_array_invalid:{frames_chw.shape}:{frames_chw.dtype}")

    safe_lane = lane.replace("-", "_")
    video_path = output_dir / f"liquid0812_{safe_lane}_full_50fps.mp4"
    command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{sink.width}x{sink.height}",
        "-framerate",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(video_path),
    ]
    raw_rgb_sha256 = hashlib.sha256()
    frame_sha256s = []
    encode_started = time.perf_counter()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_chw in frames_chw:
            frame = np.ascontiguousarray(frame_chw.transpose(1, 2, 0))
            payload = frame.tobytes(order="C")
            frame_sha256s.append(hashlib.sha256(payload).hexdigest())
            raw_rgb_sha256.update(payload)
            process.stdin.write(payload)
        process.stdin.close()
        stderr = process.stderr.read() if process.stderr is not None else b""
        returncode = process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    encode_s = time.perf_counter() - encode_started
    if returncode != 0:
        raise RuntimeError(f"full_video_encode_failed:{returncode}:{stderr[-1000:]!r}")

    probe = subprocess.run(
        [
            "/usr/bin/ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,duration",
            "-of",
            "json",
            str(video_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise RuntimeError(f"full_video_ffprobe_failed:{probe.returncode}:{probe.stderr[-1000:]}")
    probe_document = json.loads(probe.stdout)
    streams = probe_document.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise RuntimeError("full_video_ffprobe_stream_invalid")
    stream = streams[0]
    expected_duration_s = len(records) / fps
    video_checks = {
        "codec_h264": stream.get("codec_name") == "h264",
        "resolution_matches": [stream.get("width"), stream.get("height")]
        == [sink.width, sink.height],
        "frame_rate_50": stream.get("avg_frame_rate") == f"{fps}/1",
        "frame_count_matches": int(stream.get("nb_frames", -1)) == len(records),
        "duration_matches": abs(float(stream.get("duration", -1.0)) - expected_duration_s)
        <= 1.0 / fps,
    }
    if not all(video_checks.values()):
        raise RuntimeError(f"full_video_probe_contract_failed:{video_checks}:{stream}")

    sequence = [
        {
            "render_index": int(record["render_index"]),
            "render_frame_number": int(record["render_frame_number"]),
            "physics_index": int(record["physics_index"]),
            "sim_time_s": int(record["physics_index"]) / PHYSICS_HZ,
            "render_complete_perf_s": float(record["render_complete_perf_s"]),
            "rgb_sha256": frame_sha256s[index],
        }
        for index, record in enumerate(records)
    ]
    sequence_sha256 = hashlib.sha256(
        json.dumps(sequence, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()
    manifest = {
        "schema": "labutopia.isaac41.liquid0812_full_50fps_video.v1",
        "status": "encoded_and_verified",
        "claim_boundary": (
            "all_rtx_frames_retained_on_cuda_during_timed_window;"
            "cpu_readback_and_h264_encoding_after_timed_window"
        ),
        "lane": lane,
        "frame_count": len(records),
        "encoded_fps": fps,
        "duration_s": expected_duration_s,
        "resolution": [sink.width, sink.height],
        "cuda_store_bytes": int(frames_chw.nbytes),
        "readback_after_timing_s": readback_s,
        "encoding_after_timing_s": encode_s,
        "raw_rgb_sha256": raw_rgb_sha256.hexdigest(),
        "sequence_sha256": sequence_sha256,
        "sequence": sequence,
        "ffprobe": stream,
        "checks": video_checks,
        "video": baseline._file_record(video_path),
    }
    manifest_path = output_dir / "full_video_manifest.json"
    _atomic_json(manifest_path, manifest)
    return {
        "manifest": baseline._file_record(manifest_path),
        "video": manifest["video"],
        "frame_count": len(records),
        "fps": fps,
        "duration_s": expected_duration_s,
        "raw_rgb_sha256": manifest["raw_rgb_sha256"],
        "sequence_sha256": sequence_sha256,
        "readback_after_timing_s": readback_s,
        "encoding_after_timing_s": encode_s,
        "checks": video_checks,
    }


def _visible_sync_sample(
    *,
    np: Any,
    stage: Any,
    camera_record: dict[str, Any],
    payload: dict[str, Any],
    rgb_payload: Any,
    stage_name: str,
    physics_index: int,
    output_dir: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    from PIL import Image

    data = np.asarray(payload.get("data"))
    info = payload.get("info", {})
    ids = _source_instance_ids(info)
    if data.shape != (height, width):
        raise RuntimeError(f"visible_sync_instance_shape:{data.shape}")
    mask = np.isin(data, ids) if ids else np.zeros(data.shape, dtype=bool)
    ys, xs = np.nonzero(mask)
    centroid = (
        [float(xs.mean()), float(ys.mean())]
        if len(xs)
        else [-1.0e9, -1.0e9]
    )
    bbox = (
        [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        if len(xs)
        else None
    )
    mesh_bounds = baseline._prim_world_bounds(stage, baseline.SOURCE_MESH_PATH)
    projected = _project_world_point(
        mesh_bounds["center"],
        eye=camera_record["eye"],
        target=camera_record["target"],
        width=width,
        height=height,
        focal_length_mm=camera_record["focal_length_mm"],
        horizontal_aperture_mm=camera_record["horizontal_aperture_mm"],
        vertical_aperture_mm=camera_record["vertical_aperture_mm"],
    )
    audit_dir = output_dir / "visible_sync_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{stage_name}_{physics_index:04d}"
    mask_path = audit_dir / f"{stem}_mask.png"
    rgb_path = audit_dir / f"{stem}_rgb.png"
    Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(mask_path)
    rgb = np.asarray(rgb_payload)
    if rgb.shape[:2] != (height, width) or rgb.shape[2] < 3:
        raise RuntimeError(f"visible_sync_rgb_shape:{rgb.shape}")
    Image.fromarray(np.ascontiguousarray(rgb[..., :3], dtype=np.uint8), mode="RGB").save(
        rgb_path
    )
    return {
        "stage": stage_name,
        "physics_index": physics_index,
        "instance_ids": ids,
        "mask_pixel_count": int(mask.sum()),
        "mask_bbox_px": bbox,
        "mask_centroid_px": centroid,
        "projected_center_px": list(projected),
        "mask": baseline._file_record(mask_path),
        "rgb": baseline._file_record(rgb_path),
    }


def _run_visible_sync_audit_measurement(
    args: argparse.Namespace,
    *,
    application: Any,
    runtime_record: dict[str, Any],
) -> dict[str, Any]:
    import numpy as np
    import omni.physx
    import omni.replicator.core as rep
    import omni.timeline

    from tools.labutopia_fluid.fluid_benchmark_contract import load_packet

    if args.max_observations != EXPECTED_OBSERVATIONS:
        raise ValueError("visible_sync_audit_requires_complete_trajectory")
    output_dir = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output_dir_not_empty:{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    packet = load_packet(args.packet)
    stage, stage_record = baseline._open_stage(args, application)
    profile_record = _configure_profile(stage, args.profile)
    camera_record = _define_benchmark_camera(stage, packet, args.camera_policy)
    target = _create_render_target(args, application, camera_record["camera_path"])
    product_path = str(target["product_path"])
    semantics = _author_source_semantics(stage)
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    instance = rep.AnnotatorRegistry.get_annotator("instance_segmentation_fast")
    rgb.attach([product_path])
    instance.attach([product_path])
    timeline = omni.timeline.get_timeline_interface()
    timeline.stop()
    for _ in range(args.render_warmup_frames):
        rep.orchestrator.step(rt_subframes=1, pause_timeline=True, delta_time=0.0)
        rep.orchestrator.wait_until_complete()

    stepper, _tensor_simulation, source_view, source_indices, initial_source_pose = (
        baseline._attach_stepper_and_source(stage, args)
    )
    source_poses = packet.array("source_poses_xyzw", (EXPECTED_OBSERVATIONS, 7))
    initial_usd_matrix, source_matrix_time_code, source_matrix_time_samples = (
        baseline._source_usd_matrix(stage)
    )
    alignment = baseline._source_motion_alignment(
        np,
        initial_rigid_pose=initial_source_pose,
        source_poses=source_poses,
        initial_usd_matrix=initial_usd_matrix,
    )
    initial_root_to_mesh_matrix = baseline._root_to_mesh_relation(np, stage)
    simulation = omni.physx.get_physx_simulation_interface()
    windows = _sync_audit_physics_indices(source_poses)
    selected = {
        index: stage_name for stage_name, indices in windows.items() for index in indices
    }
    action_records = []
    samples = []
    try:
        for physics_index in range(EXPECTED_OBSERVATIONS):
            previous_index = max(0, physics_index - 1)
            action = baseline._advance_source_interval(
                np=np,
                args=args,
                stage=stage,
                stepper=stepper,
                source_view=source_view,
                source_indices=source_indices,
                alignment=alignment,
                previous_packet_pose=source_poses[previous_index],
                current_packet_pose=source_poses[physics_index],
                source_matrix_time_code=source_matrix_time_code,
                simulation=simulation,
                initial_root_to_mesh_matrix=initial_root_to_mesh_matrix,
            )
            action_records.append(action)
            if physics_index in selected:
                before = float(timeline.get_current_time())
                rep.orchestrator.step(
                    rt_subframes=1, pause_timeline=True, delta_time=0.0
                )
                rep.orchestrator.wait_until_complete()
                after = float(timeline.get_current_time())
                if abs(after - before) > 1.0e-12:
                    raise RuntimeError("visible_sync_render_advanced_timeline")
                samples.append(
                    _visible_sync_sample(
                        np=np,
                        stage=stage,
                        camera_record=camera_record,
                        payload=instance.get_data(),
                        rgb_payload=rgb.get_data(),
                        stage_name=selected[physics_index],
                        physics_index=physics_index,
                        output_dir=output_dir,
                        width=args.width,
                        height=args.height,
                    )
                )
    finally:
        stepper.detach()
        for annotator in (rgb, instance):
            try:
                annotator.detach([product_path])
            except Exception:
                pass
        if target.get("product") is not None:
            target["product"].destroy()
        if target.get("window") is not None:
            target["window"].destroy()

    pose_acceptance = baseline._motion_acceptance(
        np,
        scores=[
            {
                "source": baseline.EXPECTED_PARTICLE_COUNT,
                "nonfinite": 0,
                "below_table": 0,
            }
            for _ in action_records
        ],
        action_records=action_records,
        source_poses=source_poses,
        source_driver=args.source_driver,
    )["source_pose_tracking"]
    pixel_audit = _evaluate_visible_sync_records(samples)
    result = {
        "schema": "labutopia.isaac41.visible_source_sync_audit.v1",
        "status": "passed" if pose_acceptance["passed"] and pixel_audit["passed"] else "failed",
        "runtime": runtime_record,
        "lane": args.lane,
        "scene": baseline._file_record(args.scene),
        "packet": baseline._file_record(args.packet),
        "stage": stage_record,
        "profile": profile_record,
        "configuration": {
            "camera": camera_record,
            "render_product_path": product_path,
            "resolution": [args.width, args.height],
            "source_driver": args.source_driver,
            "integration_hz": args.integration_hz,
            "physics_states": EXPECTED_OBSERVATIONS,
            "same_render_product_for_rgb_and_instance": True,
            "performance_claim": False,
        },
        "semantics": semantics,
        "windows": windows,
        "pose_sync": pose_acceptance,
        "pixel_sync": pixel_audit,
        "stepper": stepper.summary(requested_steps=EXPECTED_OBSERVATIONS),
        "initial_source_pose_xyzw": initial_source_pose.tolist(),
        "initial_source_usd_matrix": initial_usd_matrix.tolist(),
        "source_matrix_time_code": source_matrix_time_code,
        "source_matrix_time_samples": source_matrix_time_samples,
        "initial_root_to_mesh_relation": initial_root_to_mesh_matrix.tolist(),
    }
    result["content_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    ).hexdigest()
    _atomic_json(output_dir / "result.json", result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "lane": args.lane,
                "result": str(output_dir / "result.json"),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return result


def _run_measurement(
    args: argparse.Namespace,
    *,
    application: Any,
    runtime_record: dict[str, Any],
) -> dict[str, Any]:
    import carb
    import numpy as np
    import omni.physx
    import omni.replicator.core as rep
    import omni.syntheticdata._syntheticdata as syntheticdata
    import omni.timeline
    import omni.usd
    import torch
    import warp as wp

    from tools.labutopia_fluid.fluid_benchmark_contract import (
        evaluate_quality_gate,
        evaluate_stability_gate,
        interpolate_pose_xyzw,
        load_packet,
    )

    output_dir = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output_dir_not_empty:{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    packet = load_packet(args.packet)
    stage, stage_record = baseline._open_stage(args, application)
    profile_record = _configure_profile(stage, args.profile)
    camera_record = _define_benchmark_camera(stage, packet, args.camera_policy)
    target = _create_render_target(args, application, camera_record["camera_path"])
    product_path = str(target["product_path"])
    annotator = rep.AnnotatorRegistry.get_annotator(
        "LdrColor", device="cuda", do_array_copy=False
    )
    annotator.attach([product_path])
    sdg = syntheticdata.acquire_syntheticdata_interface()
    render_count = _target_render_count(args.max_observations)
    if render_count < 1:
        raise ValueError("render_count_must_be_positive")
    review_count = min(args.review_frames, render_count)
    review_indices = (
        {round(index * (render_count - 1) / max(1, review_count - 1)) for index in range(review_count)}
        if review_count
        else set()
    )
    sink = _CudaFrameSink(
        torch=torch,
        width=args.width,
        height=args.height,
        review_indices=review_indices,
        full_frame_count=render_count if args.save_full_video else 0,
    )
    phase = "warmup"
    armed = False
    requested_render_index = -1
    requested_physics_index = -1
    current_physics_timestamp = None
    last_camera_physics_index = None
    warmup_valid = 0
    records: list[dict[str, Any]] = []
    callback_errors: list[dict[str, str]] = []
    ignored_events = 0
    foreign_events = 0
    duplicate_frame_numbers = 0
    invalid_cuda_events = 0
    last_frame_number = None

    def on_new_frame(event: Any) -> None:
        nonlocal armed, warmup_valid, ignored_events, foreign_events
        nonlocal duplicate_frame_numbers, invalid_cuda_events, last_frame_number
        try:
            parsed = sdg.parse_rendered_simulation_event(
                event.payload["product_path_handle"], event.payload["results"]
            )
            if str(parsed[0]) != product_path:
                foreign_events += 1
                return
            frame_number = int(event.payload.get("frame_number", -1))
            if last_frame_number is not None and frame_number <= last_frame_number:
                duplicate_frame_numbers += 1
                return
            data = annotator.get_data()
            if isinstance(data, dict):
                data = data.get("data")
            if data is None or not hasattr(data, "shape") or len(data.shape) != 3:
                ignored_events += 1
                return
            try:
                image = wp.to_torch(data)
            except RuntimeError as error:
                if "pointer resides on host memory" in str(error):
                    invalid_cuda_events += 1
                    ignored_events += 1
                    return
                raise
            if tuple(image.shape[:2]) != (args.height, args.width) or image.shape[2] < 3:
                raise RuntimeError(f"cuda_ldr_shape:{tuple(image.shape)}")
            if image.device.type != "cuda":
                raise RuntimeError(f"cuda_ldr_wrong_device:{image.device}")
            last_frame_number = frame_number
            if phase == "warmup":
                warmup_valid += 1
                return
            if not armed:
                ignored_events += 1
                return
            event_wall = time.perf_counter()
            tensor_record = sink.publish(image, requested_render_index)
            state_age_ms = (
                (event_wall - current_physics_timestamp) * 1000.0
                if current_physics_timestamp is not None
                else None
            )
            records.append(
                {
                    "render_index": requested_render_index,
                    "render_frame_number": frame_number,
                    "product_path": product_path,
                    "physics_index": requested_physics_index,
                    "render_complete_perf_s": event_wall,
                    "state_age_ms": state_age_ms,
                    "tensor": tensor_record,
                }
            )
            armed = False
        except BaseException as error:
            callback_errors.append(
                {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
            )
            armed = False

    subscription = (
        omni.usd.get_context()
        .get_rendering_event_stream()
        .create_subscription_to_pop_by_type(
            int(omni.usd.StageRenderingEventType.NEW_FRAME),
            on_new_frame,
            name="labutopia_async_rtx_new_frame",
            order=1100,
        )
    )
    timeline = omni.timeline.get_timeline_interface()
    timeline.stop()
    timeline_time_before = float(timeline.get_current_time())
    scheduler_frame_budget = args.render_warmup_frames + render_count + 64
    capture_on_play_before = bool(
        carb.settings.get_settings().get("/omni/replicator/captureOnPlay")
    )
    carb.settings.get_settings().set("/omni/replicator/captureOnPlay", False)
    rep.orchestrator.run(num_frames=scheduler_frame_budget, start_timeline=False)
    stepper = None
    try:
        warmup_updates = 0
        while warmup_valid < args.render_warmup_frames:
            application.update()
            warmup_updates += 1
            if callback_errors:
                raise RuntimeError(f"render_callback_failed:{callback_errors[-1]}")
            if warmup_updates > args.max_updates_per_frame * max(1, args.render_warmup_frames):
                raise TimeoutError(f"render_warmup_timeout:{warmup_valid}:{warmup_updates}")

        stepper, _tensor_simulation, source_view, source_indices, initial_source_pose = (
            baseline._attach_stepper_and_source(stage, args)
        )
        source_poses = packet.array("source_poses_xyzw", (EXPECTED_OBSERVATIONS, 7))
        source_frame_local = packet.array("source_frame_local_matrix", (4, 4))
        initial_usd_matrix, source_matrix_time_code, source_matrix_time_samples = baseline._source_usd_matrix(stage)
        alignment = baseline._source_motion_alignment(
            np,
            initial_rigid_pose=initial_source_pose,
            source_poses=source_poses,
            initial_usd_matrix=initial_usd_matrix,
        )
        initial_root_to_mesh_matrix = baseline._root_to_mesh_relation(np, stage)
        simulation = omni.physx.get_physx_simulation_interface()
        physics_index = -1
        physics_ms: list[float] = []
        scores = []
        action_records = []
        phase = "timed"
        timed_started = time.perf_counter()
        for render_index in range(render_count):
            desired_physics_index = min(
                args.max_observations - 1, _physics_index_for_render(render_index)
            )
            while physics_index < desired_physics_index:
                physics_index += 1
                physics_started = time.perf_counter()
                previous_index = max(0, physics_index - 1)
                action = baseline._advance_source_interval(
                    np=np,
                    args=args,
                    stage=stage,
                    stepper=stepper,
                    source_view=source_view,
                    source_indices=source_indices,
                    alignment=alignment,
                    previous_packet_pose=source_poses[previous_index],
                    current_packet_pose=source_poses[physics_index],
                    source_matrix_time_code=source_matrix_time_code,
                    simulation=simulation,
                    initial_root_to_mesh_matrix=initial_root_to_mesh_matrix,
                )
                positions = baseline._read_positions(stage)
                physics_ms.append((time.perf_counter() - physics_started) * 1000.0)
                action_records.append(action)
                scores.append(
                    baseline._partition(
                        positions,
                        packet=packet,
                        source_frame_world=(
                            source_frame_local
                            @ baseline._pose_matrix_xyzw(
                                np, action["actual_packet_pose_xyzw"]
                            )
                        ),
                        observation_index=physics_index,
                    )
                )
                current_physics_timestamp = time.perf_counter()
            if args.camera_policy == "trajectory-follow":
                follow_poses = camera_record.get("follow_frame_poses") or []
                if physics_index < 0 or physics_index >= len(follow_poses):
                    raise RuntimeError(
                        f"follow_camera_physics_index:{physics_index}:{len(follow_poses)}"
                    )
                if physics_index != last_camera_physics_index:
                    _author_camera_pose(
                        stage,
                        camera_record["camera_path"],
                        follow_poses[physics_index],
                    )
                    last_camera_physics_index = physics_index
            requested_render_index = render_index
            requested_physics_index = physics_index
            armed = True
            record_count_before = len(records)
            for _ in range(args.max_updates_per_frame):
                application.update()
                if callback_errors:
                    raise RuntimeError(f"render_callback_failed:{callback_errors[-1]}")
                if len(records) > record_count_before:
                    break
            else:
                raise TimeoutError(f"render_frame_timeout:{render_index}:{product_path}")
        sink.drain()
        timed_finished = time.perf_counter()
        timeline_time_after = float(timeline.get_current_time())
        timeline_playing_after = bool(timeline.is_playing())
        if timeline_playing_after:
            raise RuntimeError("async_render_started_timeline")
    finally:
        phase = "closed"
        subscription = None
        if stepper is not None:
            stepper.detach()
        try:
            annotator.detach([product_path])
        except Exception:
            pass
        try:
            rep.orchestrator.stop()
            rep.orchestrator.wait_until_complete()
        except Exception:
            pass
        if target.get("product") is not None:
            try:
                target["product"].destroy()
            except Exception:
                pass
        if target.get("window") is not None:
            try:
                target["window"].destroy()
            except Exception:
                pass

    elapsed_s = timed_finished - timed_started
    if len(records) != render_count:
        raise RuntimeError(f"render_record_count:{len(records)}:{render_count}")
    render_indices = [int(record["render_index"]) for record in records]
    frame_numbers = [int(record["render_frame_number"]) for record in records]
    physics_indices = [int(record["physics_index"]) for record in records]
    completion_times = [float(record["render_complete_perf_s"]) for record in records]
    intervals_ms = [
        (completion_times[index] - completion_times[index - 1]) * 1000.0
        for index in range(1, len(completion_times))
    ]
    state_ages_ms = [float(record["state_age_ms"]) for record in records if record["state_age_ms"] is not None]
    quality = evaluate_quality_gate(scores, visual_liquid_passed=None)
    stability = evaluate_stability_gate(scores, expected_particle_count=baseline.EXPECTED_PARTICLE_COUNT)
    motion_acceptance = baseline._motion_acceptance(
        np,
        scores=scores,
        action_records=action_records,
        source_poses=source_poses,
        source_driver=args.source_driver,
    )
    review = _save_review_artifacts(output_dir, sink) if args.save_review else None
    full_video = (
        _save_full_video_artifacts(output_dir, sink, records, lane=args.lane)
        if args.save_full_video
        else None
    )
    events_path = output_dir / "render_events.jsonl"
    events_path.write_text(
        "".join(json.dumps(record, sort_keys=True, allow_nan=False) + "\n" for record in records),
        encoding="utf-8",
    )
    average_rtx_fps = len(records) / elapsed_s
    average_physics_fps = len(scores) / elapsed_s
    performance_acceptance = {
        "average_rtx_completed_fps_at_least_50": average_rtx_fps >= TARGET_RENDER_HZ,
        "average_physics_fps_at_least_30": average_physics_fps >= PHYSICS_HZ,
        "expected_render_count": len(records) == render_count,
        "expected_physics_count": len(scores) == args.max_observations,
        "contiguous_render_indices": render_indices == list(range(render_count)),
        "strictly_increasing_frame_numbers": all(
            frame_numbers[index] > frame_numbers[index - 1] for index in range(1, len(frame_numbers))
        ),
        "physics_indices_nondecreasing": all(
            physics_indices[index] >= physics_indices[index - 1] for index in range(1, len(physics_indices))
        ),
        "all_cuda_tensors_consumed": sink.consumed_sequences == list(range(render_count)),
        "no_callback_errors": not callback_errors,
        "no_duplicate_frame_numbers": duplicate_frame_numbers == 0,
        "no_cpu_rgb_readback_in_timed_path": True,
    }
    if args.save_full_video:
        performance_acceptance["full_video_encoded_and_verified"] = bool(
            full_video and all(full_video["checks"].values())
        )
    physics_acceptance = {
        "formal_kinematic_driver": args.source_driver == "physx-kinematic-target",
        "pre_tilt_retention": motion_acceptance["pre_tilt_retention"]["passed"],
        "source_pose_tracking": motion_acceptance["source_pose_tracking"]["passed"],
        "no_penetration_or_nonfinite": stability["passed"],
        "complete_pour_numeric_quality": quality["numeric_passed"],
    }
    performance_passed = all(performance_acceptance.values())
    physics_passed = all(physics_acceptance.values())
    result = {
        "schema": "labutopia.isaac41.liquid0812_async_rtx_result.v3",
        "status": (
            "passed_50fps_and_physics"
            if performance_passed and physics_passed
            else (
                "passed_50fps_quality_no_go"
                if performance_passed
                else "measured_no_go"
            )
        ),
        "claim_boundary": (
            "experimental_async_rtx_completed_gpu_ready_protocol;not_current_state_artifact_ready;"
            "single_camera;30hz_control;configurable_integration_hz;50hz_render_schedule;"
            "same_control_state_may_back_two_renders"
        ),
        "runtime": runtime_record,
        "lane": args.lane,
        "headless_simulation_app": True,
        "render_target_kind": target["kind"],
        "scene": baseline._file_record(args.scene),
        "packet": baseline._file_record(args.packet),
        "stage": stage_record,
        "profile": profile_record,
        "configuration": {
            "camera_path": camera_record["camera_path"],
            "camera": {
                key: value
                for key, value in camera_record.items()
                if key != "follow_frame_poses"
            },
            "render_product_path": product_path,
            "resolution": [args.width, args.height],
            "renderer": "RayTracedLighting",
            "control_hz": PHYSICS_HZ,
            "integration_hz": args.integration_hz,
            "substeps_per_control_observation": baseline._integration_substeps(
                args.integration_hz
            ),
            "source_driver": args.source_driver,
            "target_render_hz": TARGET_RENDER_HZ,
            "observation_count": args.max_observations,
            "render_count": render_count,
            "mapping": "physics_index=floor(render_index*30/50)",
            "cuda_tensor": {"shape": [3, args.height, args.width], "dtype": "uint8", "device": "cuda:0"},
            "consumer": "same_process_cuda_checksum_fake_consumer",
            "ring_size": 3,
            "full_cuda_video_store": {
                "enabled": args.save_full_video,
                "frame_count": render_count if args.save_full_video else 0,
                "bytes": (
                    render_count * 3 * args.width * args.height
                    if args.save_full_video
                    else 0
                ),
            },
            "warmup_frames_excluded": args.render_warmup_frames,
            "scheduler": "single_replicator_continuous_run_without_timeline;no_per_frame_step_or_wait",
            "scheduler_frame_budget": scheduler_frame_budget,
            "capture_on_play_before": capture_on_play_before,
            "capture_on_play_forced_false": True,
            "timeline": {
                "start_timeline_requested": False,
                "playing_after_timed_window": timeline_playing_after,
                "time_before_s": timeline_time_before,
                "time_after_s": timeline_time_after,
                "time_delta_s": timeline_time_after - timeline_time_before,
                "note": "Replicator may adjust its internal stopped-timeline sample; physics advances only through StrictPhysicsStepper.",
            },
        },
        "timing": {
            "elapsed_s_including_final_cuda_drain": elapsed_s,
            "average_rtx_completed_gpu_consumed_fps": average_rtx_fps,
            "average_physics_fps_on_same_elapsed_window": average_physics_fps,
            "render_intervals": _summarize_ms(intervals_ms),
            "physics_steps": _summarize_ms(physics_ms),
            "state_age": _summarize_ms(state_ages_ms),
            "ring_backpressure_wait": _summarize_ms(sink.backpressure_wait_ms),
        },
        "event_integrity": {
            "target_events": len(records),
            "foreign_events": foreign_events,
            "ignored_target_events": ignored_events,
            "duplicate_or_nonmonotonic_frame_numbers": duplicate_frame_numbers,
            "invalid_host_pointer_events_discarded": invalid_cuda_events,
            "callback_errors": callback_errors,
            "first_frame_number": frame_numbers[0],
            "last_frame_number": frame_numbers[-1],
        },
        "physics": {
            "initial_source_pose_xyzw": initial_source_pose.tolist(),
            "source_matrix_time_code": source_matrix_time_code,
            "source_matrix_time_samples": source_matrix_time_samples,
            "rigid_from_packet_relation": alignment["rigid_from_packet"].tolist(),
            "initial_root_to_mesh_relation": initial_root_to_mesh_matrix.tolist(),
            "motion_acceptance": motion_acceptance,
            "quality": quality,
            "stability": stability,
        },
        "acceptance": {
            "performance": performance_acceptance,
            "physics": physics_acceptance,
            "performance_passed": performance_passed,
            "physics_passed": physics_passed,
        },
        "artifacts": {
            "render_events": baseline._file_record(events_path),
            "review": review,
            "full_video": full_video,
        },
    }
    result["content_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    _atomic_json(output_dir / "result.json", result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "lane": args.lane,
                "profile": args.profile,
                "rtx_fps": average_rtx_fps,
                "physics_fps": average_physics_fps,
                "result": str(output_dir / "result.json"),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return result


def _run_child(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    request = attestation._read_canonical_json(args.execution_request)
    request = attestation.verify_execution_request(request, source_paths=source_paths())
    pre_app_numpy_modules = sorted(
        name for name in sys.modules if name == "numpy" or name.startswith("numpy.")
    )
    from isaacsim import SimulationApp

    parsed_argv = sys.argv
    sys.argv = [sys.argv[0]]
    application = SimulationApp(
        {
            "headless": True,
            "width": args.width,
            "height": args.height,
            "renderer": "RayTracedLighting",
        }
    )
    sys.argv = parsed_argv
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    try:
        receipt = attestation.attest_existing_application(
            application=application,
            pre_app_numpy_modules=pre_app_numpy_modules,
            execution_request=request,
            source_paths=source_paths(),
        )
        attestation.write_canonical_json(receipt_path, receipt)
        binding = attestation.execution_binding_for_request(request, child_pid=os.getpid())
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        baseline._configure_runtime_settings()
        runtime_record = {
            "lane": "formal_isaac41_liquid0812_async_rtx",
            "evidence_class": (
                "non_authoritative_busy_gpu_exploration"
                if args.allow_busy_gpu_exploratory
                else "formal_comparable"
            ),
            "receipt_path": str(receipt_path),
            "receipt_sha256": attestation.canonical_json_sha256(receipt),
            "execution_binding": binding,
        }
        if args.visible_sync_audit:
            _run_visible_sync_audit_measurement(
                args,
                application=application,
                runtime_record=runtime_record,
            )
        else:
            _run_measurement(
                args,
                application=application,
                runtime_record=runtime_record,
            )
    except BaseException as error:
        _atomic_json(
            args.evidence_dir / "child_failure.json",
            {
                "status": "blocked_runtime",
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        )
        # Preserve the formal nonzero outcome; failed children rely on normal
        # interpreter teardown instead of Kit close, which may force exit 0.
        return 2
    try:
        application.close()
    except SystemExit:
        pass
    return 0


def _child_command(args: argparse.Namespace, request_path: Path) -> list[str]:
    command = [
        str(FORMAL_ISAAC41_PYTHON), "-I", "-B", str(Path(__file__).resolve()),
        "--child", "--lane", args.lane, "--profile", args.profile,
        "--camera-policy", args.camera_policy,
        "--scene", str(args.scene), "--packet", str(args.packet),
        "--output-dir", str(args.output_dir), "--evidence-dir", str(args.evidence_dir),
        "--execution-request", str(request_path),
        "--max-observations", str(args.max_observations),
        "--width", str(args.width), "--height", str(args.height),
        "--stage-warmup-updates", str(args.stage_warmup_updates),
        "--render-warmup-frames", str(args.render_warmup_frames),
        "--max-updates-per-frame", str(args.max_updates_per_frame),
        "--review-frames", str(args.review_frames),
        "--source-driver", args.source_driver,
        "--integration-hz", str(args.integration_hz),
    ]
    if args.allow_busy_gpu_exploratory:
        command.append("--allow-busy-gpu-exploratory")
    if args.save_review:
        command.append("--save-review")
    if args.save_full_video:
        command.append("--save-full-video")
    if args.visible_sync_audit:
        command.append("--visible-sync-audit")
    return command


def _run_one_parent(args: argparse.Namespace, *, gpu_preflight: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    args.evidence_dir.mkdir(parents=True, exist_ok=False)
    closure = source_paths()
    source_before = attestation.capture_source_identity(closure)
    request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    request_path = args.evidence_dir / "execution_request.json"
    attestation.write_canonical_json(request_path, request)
    environment = attestation.sealed_child_environment(args.evidence_dir / "runtime")
    command = _child_command(args, request_path)
    started = time.time()
    completed = subprocess.run(command, cwd=REPO_ROOT, env=environment, check=False, capture_output=True)
    stdout_path = args.evidence_dir / "child.stdout.log"
    stderr_path = args.evidence_dir / "child.stderr.log"
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    result_path = args.output_dir / "result.json"
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    verification_error = None
    receipt_sha256 = None
    result = None
    try:
        receipt = attestation._read_canonical_json(receipt_path)
        attestation.require_matched_runtime_receipt(receipt)
        receipt_sha256 = attestation.canonical_json_sha256(receipt)
        if completed.returncode != 0 or not result_path.is_file():
            raise RuntimeError(f"async_rtx_child_exit:{completed.returncode}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except BaseException as error:
        verification_error = {"type": type(error).__name__, "message": str(error)}
    manifest = {
        "schema": "labutopia.isaac41.liquid0812_async_rtx_parent_manifest.v1",
        "status": "passed" if verification_error is None else "blocked_runtime",
        "command": command,
        "child_returncode": completed.returncode,
        "started_unix_s": started,
        "elapsed_wall_s": time.time() - started,
        "source_before": source_before,
        "source_after": attestation.capture_source_identity(closure),
        "scene": baseline._file_record(args.scene),
        "packet": baseline._file_record(args.packet),
        "gpu_preflight": gpu_preflight,
        "gpu_after": baseline._gpu_snapshot(),
        "runtime_receipt_sha256": receipt_sha256,
        "stdout": baseline._file_record(stdout_path),
        "stderr": baseline._file_record(stderr_path),
        "result_sha256": baseline._sha256_file(result_path) if result_path.is_file() else None,
        "verification_error": verification_error,
    }
    attestation.write_canonical_json(args.evidence_dir / "run_manifest.json", manifest)
    return (0 if verification_error is None else 2), result


def _run_matrix(args: argparse.Namespace) -> int:
    root = args.output_root
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"output_root_not_empty:{root}")
    root.mkdir(parents=True, exist_ok=True)
    run_records = []
    results_by_cell: dict[str, list[dict[str, Any]]] = {}
    failures = []
    for lane in args.lanes:
        for profile in args.profiles:
            cell = f"{lane}__{profile}"
            results_by_cell[cell] = []
            for repeat in range(args.repeats):
                gpu_attempts = []
                for gpu_attempt in range(5):
                    gpu = baseline._sample_gpu(args.gpu_sample_seconds)
                    gpu_attempts.append(gpu)
                    if gpu["idle_enough"]:
                        break
                    has_compute_process = any(
                        sample.get("compute_processes")
                        for sample in gpu.get("samples", [])
                    )
                    if has_compute_process:
                        break
                    # nvidia-smi utilization can retain the just-closed Isaac
                    # process for one sampling interval after memory/processes
                    # have returned to zero.  Re-sample that transient state.
                    time.sleep(2.0)
                if not gpu["idle_enough"]:
                    failures.append(
                        {
                            "cell": cell,
                            "repeat": repeat,
                            "reason": "gpu_busy",
                            "gpu": gpu,
                            "gpu_preflight_attempts": gpu_attempts,
                        }
                    )
                    break
                run_root = root / "runs" / cell / f"repeat-{repeat:02d}"
                child_args = argparse.Namespace(**vars(args))
                child_args.lane = lane
                child_args.profile = profile
                child_args.output_dir = run_root / "artifacts"
                child_args.evidence_dir = run_root / "evidence"
                child_args.save_review = args.save_review and repeat == 0
                child_args.visible_sync_audit = False
                print(json.dumps({"event": "run_start", "cell": cell, "repeat": repeat}, sort_keys=True), flush=True)
                code, result = _run_one_parent(child_args, gpu_preflight=gpu)
                run_records.append({"cell": cell, "repeat": repeat, "returncode": code, "root": str(run_root)})
                if result is None:
                    failures.append({"cell": cell, "repeat": repeat, "reason": "run_failed"})
                    break
                results_by_cell[cell].append(result)
                print(
                    json.dumps(
                        {
                            "event": "run_end", "cell": cell, "repeat": repeat,
                            "status": result["status"],
                            "rtx_fps": result["timing"]["average_rtx_completed_gpu_consumed_fps"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
    summaries = {}
    for cell, results in results_by_cell.items():
        if not results:
            summaries[cell] = None
            continue
        rtx = [float(item["timing"]["average_rtx_completed_gpu_consumed_fps"]) for item in results]
        physics = [float(item["timing"]["average_physics_fps_on_same_elapsed_window"]) for item in results]
        summaries[cell] = {
            "run_count": len(results),
            "rtx_fps": {"values": rtx, "mean": statistics.fmean(rtx), "median": statistics.median(rtx)},
            "physics_fps": {"values": physics, "mean": statistics.fmean(physics), "median": statistics.median(physics)},
            "all_runs_meet_50fps": len(results) == args.repeats and all(value >= TARGET_RENDER_HZ for value in rtx),
            "all_runs_meet_30hz_physics": len(results) == args.repeats and all(value >= PHYSICS_HZ for value in physics),
        }
    complete = not failures and all(
        summary is not None and summary["run_count"] == args.repeats for summary in summaries.values()
    )
    all_pass = complete and all(
        summary["all_runs_meet_50fps"] and summary["all_runs_meet_30hz_physics"]
        for summary in summaries.values() if summary is not None
    )
    matrix = {
        "schema": "labutopia.isaac41.liquid0812_async_rtx_matrix.v1",
        "status": "passed_50fps" if all_pass else ("measured_no_go" if complete else "incomplete"),
        "claim_boundary": "experimental_async_rtx_completed_gpu_ready;not_strict_artifact_ready",
        "configuration": {
            "lanes": list(args.lanes), "profiles": list(args.profiles), "repeats": args.repeats,
            "resolution": [args.width, args.height], "control_hz": PHYSICS_HZ,
            "integration_hz": args.integration_hz,
            "substeps_per_control_observation": baseline._integration_substeps(
                args.integration_hz
            ),
            "source_driver": args.source_driver,
            "target_render_hz": TARGET_RENDER_HZ, "observation_count": args.max_observations,
            "camera_policy": args.camera_policy,
        },
        "historical_context": {
            "gui_overlay_fps_range": [49.76, 54.16],
            "gui_overlay_is_not_rtx_completion_evidence": True,
            "strict_synchronous_256_probe_fps": 4.1405,
        },
        "runs": run_records,
        "summaries": summaries,
        "failures": failures,
    }
    matrix["content_sha256"] = hashlib.sha256(
        json.dumps(matrix, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    _atomic_json(root / "matrix.json", matrix)
    print(json.dumps({"status": matrix["status"], "matrix": str(root / "matrix.json")}, sort_keys=True), flush=True)
    return 0 if complete else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--lane", choices=LANES)
    parser.add_argument("--profile", choices=PROFILES, default="current")
    parser.add_argument(
        "--camera-policy", choices=CAMERA_POLICIES, default="trajectory-follow"
    )
    parser.add_argument("--lanes", nargs="+", choices=LANES, default=list(LANES))
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--gpu-sample-seconds", type=int, default=3)
    parser.add_argument("--max-observations", type=int, default=EXPECTED_OBSERVATIONS)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--stage-warmup-updates", type=int, default=32)
    parser.add_argument("--render-warmup-frames", type=int, default=16)
    parser.add_argument("--max-updates-per-frame", type=int, default=600)
    parser.add_argument("--review-frames", type=int, default=60)
    parser.add_argument(
        "--source-driver",
        choices=baseline.SOURCE_DRIVERS,
        default=baseline.DEFAULT_SOURCE_DRIVER,
    )
    parser.add_argument(
        "--integration-hz",
        type=int,
        choices=baseline.INTEGRATION_HZ_CHOICES,
        default=baseline.DEFAULT_INTEGRATION_HZ,
    )
    parser.add_argument("--save-review", action="store_true")
    parser.add_argument("--save-full-video", action="store_true")
    parser.add_argument("--visible-sync-audit", action="store_true")
    parser.add_argument("--allow-busy-gpu-exploratory", action="store_true")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.max_observations <= EXPECTED_OBSERVATIONS:
        raise ValueError("max_observations_out_of_range")
    if args.width < 1 or args.height < 1:
        raise ValueError("resolution_must_be_positive")
    if args.render_warmup_frames < 1 or args.max_updates_per_frame < 1:
        raise ValueError("warmup_and_update_limit_must_be_positive")
    if args.review_frames < 0:
        raise ValueError("review_frames_must_be_nonnegative")
    baseline._integration_substeps(args.integration_hz)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _validate_args(args)
    for name in ("scene", "packet"):
        setattr(args, name, getattr(args, name).resolve())
    for name in ("output_root", "output_dir", "evidence_dir", "execution_request"):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve())
    if args.child:
        if None in (args.lane, args.output_dir, args.evidence_dir, args.execution_request):
            raise ValueError("child_arguments_missing")
        return _run_child(args)
    if args.matrix:
        if args.output_root is None or args.repeats < 1:
            raise ValueError("matrix_arguments_missing")
        return _run_matrix(args)
    if None in (args.lane, args.output_dir, args.evidence_dir):
        raise ValueError("single_run_arguments_missing")
    gpu = baseline._sample_gpu(args.gpu_sample_seconds)
    if not gpu["idle_enough"] and not args.allow_busy_gpu_exploratory:
        print(
            json.dumps(
                {"status": "blocked_gpu_busy", "gpu_preflight": gpu},
                sort_keys=True,
            ),
            flush=True,
        )
        return 3
    if args.allow_busy_gpu_exploratory:
        gpu = {
            **gpu,
            "exception": {
                "approved_by": "user_message_2026-08-13",
                "scope": "visible synchronization and video exploration only",
                "rationale": "user accepted running alongside shared GPU workloads",
                "environment_difference": "GPU is shared; runtime tuple and sealed child are unchanged",
                "expiry": "this exploratory run only",
                "evidence_impact": "non-authoritative and non-comparable; FPS cannot be promoted",
            },
        }
    code, _result = _run_one_parent(args, gpu_preflight=gpu)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
