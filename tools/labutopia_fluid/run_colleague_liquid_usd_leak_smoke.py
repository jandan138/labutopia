#!/usr/bin/env python3
"""Run a bounded leak-evidence smoke for the colleague-provided lab_001 liquid USD."""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
import traceback
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.run_beaker_collider_smoke import (
    ColliderConfig,
    VariantSpec,
    _add_native_beaker_isolation,
    _add_target_marker,
    classify_collider_hold,
    compute_region_counts,
)
from tools.labutopia_fluid.run_standalone_particle_smoke import (
    _aabb,
    _centroid,
    _finite_positions,
    _nan_count,
    _write_json,
    _write_trace_line,
    build_particle_grid,
)


DEFAULT_USD = (
    "outputs/usd_asset_packages/lab_001_localized_20260707/"
    "lab_001_level1_pour_tabletop_with_liquid.usd"
)
DEFAULT_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_colleague_liquid_usd_leak_smoke_20260708_001"
)
DEFAULT_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_colleague_liquid_usd_leak_smoke_20260708.json"
)
DEFAULT_NATIVE_USD = "outputs/usd_asset_packages/lab_001_localized_20260707/lab_001.usd"
EVIDENCE_PARTICLE_SYSTEM_PATH = "/World/ParticleSystem"
EVIDENCE_PARTICLE_SET_PATH = "/World/ParticleSet"
COLLIDER_MODES = ("native-convex", "native-proxy-wrapper", "none")
POSITION_MODES = ("colleague-sampled", "source-grid")


@dataclass(frozen=True)
class BBox:
    min: tuple[float, float, float]
    max: tuple[float, float, float]

    @property
    def center(self) -> tuple[float, float, float]:
        return tuple((self.min[i] + self.max[i]) / 2.0 for i in range(3))  # type: ignore[return-value]

    @property
    def size(self) -> tuple[float, float, float]:
        return tuple(self.max[i] - self.min[i] for i in range(3))  # type: ignore[return-value]


def select_particle_subset(
    points: Sequence[Sequence[float]],
    *,
    limit: int | None,
) -> list[tuple[float, float, float]]:
    """Select a deterministic, evenly spaced subset while preserving endpoints."""
    normalized = [(float(p[0]), float(p[1]), float(p[2])) for p in points]
    if limit is None or limit <= 0 or len(normalized) <= limit:
        return normalized
    if limit == 1:
        return [normalized[0]]
    last = len(normalized) - 1
    indices = [round(i * last / (limit - 1)) for i in range(limit)]
    return [normalized[i] for i in indices]


def build_particle_scope_summary(
    *,
    original_particle_count: int,
    selected_particle_count: int,
    particle_limit: int | None,
) -> dict[str, Any]:
    full_original = original_particle_count > 0 and selected_particle_count == original_particle_count
    limit_requests_all = particle_limit is None or particle_limit <= 0 or particle_limit >= original_particle_count
    full_original = full_original and limit_requests_all
    return {
        "particle_scope": "full_original_50k" if full_original else "sampled_subset",
        "full_original_50k_completed_pbd_overlay": bool(full_original and original_particle_count == 50000),
        "sampled_overlay": not full_original,
        "original_particle_count": int(original_particle_count),
        "selected_particle_count": int(selected_particle_count),
        "particle_limit": particle_limit,
    }


def build_review_camera_summary(frame_sources: dict[str, str]) -> dict[str, Any]:
    real_rgb_count = sum(1 for source in frame_sources.values() if source == "camera_rgb")
    projection_count = sum(1 for source in frame_sources.values() if source == "diagnostic_projection")
    return {
        "real_rgb_camera_frame_count": real_rgb_count,
        "diagnostic_projection_frame_count": projection_count,
        "d3_real_isaacsim41_rgb_camera_passed": real_rgb_count > 0,
        "frame_sources": dict(sorted(frame_sources.items())),
    }


def build_review_marker_summary(*, marker_limit: int, marker_width: float) -> dict[str, Any]:
    enabled = marker_limit != 0 and marker_width > 0.0
    return {
        "d3_review_markers_enabled": enabled,
        "d3_review_marker_limit": int(marker_limit),
        "d3_review_marker_width": float(marker_width),
        "d3_review_markers_are_physics": False,
        "d3_review_marker_source": "particle_readback_positions",
    }


def _normalize3(value: Sequence[float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(float(v) * float(v) for v in value))
    if length <= 1e-12:
        raise ValueError("zero_length_vector")
    return tuple(float(v) / length for v in value)  # type: ignore[return-value]


def _cross3(left: Sequence[float], right: Sequence[float]) -> tuple[float, float, float]:
    return (
        float(left[1]) * float(right[2]) - float(left[2]) * float(right[1]),
        float(left[2]) * float(right[0]) - float(left[0]) * float(right[2]),
        float(left[0]) * float(right[1]) - float(left[1]) * float(right[0]),
    )


def _dot3(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(left[i]) * float(right[i]) for i in range(3))


def _quat_from_rotation_matrix(matrix: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    m00, m01, m02 = (float(v) for v in matrix[0])
    m10, m11, m12 = (float(v) for v in matrix[1])
    m20, m21, m22 = (float(v) for v in matrix[2])
    trace = m00 + m11 + m22
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        return (
            0.25 * scale,
            (m21 - m12) / scale,
            (m02 - m20) / scale,
            (m10 - m01) / scale,
        )
    if m00 > m11 and m00 > m22:
        scale = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        return (
            (m21 - m12) / scale,
            0.25 * scale,
            (m01 + m10) / scale,
            (m02 + m20) / scale,
        )
    if m11 > m22:
        scale = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        return (
            (m02 - m20) / scale,
            (m01 + m10) / scale,
            0.25 * scale,
            (m12 + m21) / scale,
        )
    scale = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
    return (
        (m10 - m01) / scale,
        (m02 + m20) / scale,
        (m12 + m21) / scale,
        0.25 * scale,
    )


def _normalize4(value: Sequence[float]) -> tuple[float, float, float, float]:
    length = math.sqrt(sum(float(v) * float(v) for v in value))
    if length <= 1e-12:
        raise ValueError("zero_length_quaternion")
    return tuple(float(v) / length for v in value)  # type: ignore[return-value]


def world_camera_quat_look_at(
    *,
    eye: Sequence[float],
    target: Sequence[float],
    up: Sequence[float] = (0.0, 0.0, 1.0),
) -> tuple[float, float, float, float]:
    forward = _normalize3([float(target[i]) - float(eye[i]) for i in range(3)])
    up_hint = _normalize3(up)
    up_projected = [up_hint[i] - _dot3(up_hint, forward) * forward[i] for i in range(3)]
    camera_z = _normalize3(up_projected)
    camera_y = _normalize3(_cross3(camera_z, forward))
    matrix = (
        (forward[0], camera_y[0], camera_z[0]),
        (forward[1], camera_y[1], camera_z[1]),
        (forward[2], camera_y[2], camera_z[2]),
    )
    quat = _quat_from_rotation_matrix(matrix)
    return _normalize4(quat)


def build_source_grid_positions(*, config: ColliderConfig, count: int) -> list[tuple[float, float, float]]:
    grid_x = (config.grid_dims[0] - 1) * config.particle_spacing
    grid_y = (config.grid_dims[1] - 1) * config.particle_spacing
    lower = (
        config.source_center[0] - grid_x / 2.0,
        config.source_center[1] - grid_y / 2.0,
        config.table_z + 0.06,
    )
    return build_particle_grid(count=count, dims=config.grid_dims, lower=lower, spacing=config.particle_spacing)


def build_tabletop_region_config(
    *,
    source_bbox: BBox,
    target_bbox: BBox,
    table_top_z: float,
) -> ColliderConfig:
    """Map the packaged LabUtopia tabletop coordinates onto S2 source/target regions."""
    source_center_raw = source_bbox.center
    target_center_raw = target_bbox.center
    source_size = source_bbox.size
    target_size = target_bbox.size
    return ColliderConfig(
        particle_count=0,
        source_center=(round(source_center_raw[0], 6), round(source_center_raw[1], 6), table_top_z),
        target_center=(round(target_center_raw[0], 6), round(target_center_raw[1], 6), table_top_z),
        source_radius=round(max(source_size[0], source_size[1]) / 2.0 + 0.005, 6),
        target_radius=round(max(target_size[0], target_size[1]) / 2.0 + 0.005, 6),
        source_height=round(max(source_bbox.max[2] - table_top_z + 0.02, source_size[2] + 0.02), 6),
        target_height=round(max(target_bbox.max[2] - table_top_z + 0.02, target_size[2] + 0.02), 6),
        table_z=table_top_z,
        steps=0,
        trace_interval=1,
        tail_window_steps=1,
    )


def resolve_particle_runtime_offsets(
    *,
    authored_width: float,
    particle_width_override: float | None,
    particle_contact_offset_override: float | None,
) -> dict[str, float]:
    width = float(particle_width_override) if particle_width_override is not None else float(authored_width)
    particle_contact_offset = (
        float(particle_contact_offset_override)
        if particle_contact_offset_override is not None
        else max(width * 0.9, 0.0005)
    )
    return {
        "particle_width": width,
        "particle_contact_offset": particle_contact_offset,
        "particle_system_contact_offset": particle_contact_offset * 1.2,
        "solid_rest_offset": particle_contact_offset * 0.6,
        "fluid_rest_offset": particle_contact_offset * 0.6,
    }


def build_colleague_variant_spec(collider_mode: str) -> VariantSpec:
    if collider_mode not in COLLIDER_MODES:
        raise ValueError(f"unsupported_collider_mode:{collider_mode}")
    route = "render_mesh_plus_proxy_collision" if collider_mode == "native-proxy-wrapper" else "convexDecomposition"
    proxy_enabled = collider_mode == "native-proxy-wrapper"
    native_collision_enabled = collider_mode == "native-convex"
    return VariantSpec(
        variant_id=f"COLLEAGUE_{collider_mode.upper().replace('-', '_')}",
        name=f"colleague_{collider_mode}",
        description="Native beaker2 visual/collider mode with colleague-authored initial particle positions.",
        setup="colleague_liquid_usd_minimal_native_slice",
        collider_count=25 if proxy_enabled else (1 if collider_mode == "native-convex" else 0),
        collision_approximation=route if collider_mode != "none" else "none",
        source_kind="native_mesh_reference" if collider_mode != "none" else "none",
        native_source_path="/World/beaker2",
        native_mesh_source_path="/World/beaker2/mesh",
        native_reference_scope="parent_scope",
        native_material_binding_strategy="local_blue_glass_override",
        native_material_binding_scope_closed=True,
        native_pose_alignment="bbox_recenter_to_source_region",
        native_collision_route=route,
        native_mesh_collision_enabled=native_collision_enabled,
        proxy_collision_enabled=proxy_enabled,
        panel_count=24 if proxy_enabled else None,
    )


def _max_displacement(initial: Sequence[Sequence[float]], final: Sequence[Sequence[float]]) -> float:
    max_dist = 0.0
    for before, after in zip(initial, final):
        before_v = (float(before[0]), float(before[1]), float(before[2]))
        after_v = (float(after[0]), float(after[1]), float(after[2]))
        if all(math.isfinite(v) for v in before_v + after_v):
            max_dist = max(max_dist, math.sqrt(sum((after_v[i] - before_v[i]) ** 2 for i in range(3))))
    return max_dist


def _position_hash(positions: Sequence[Sequence[float]]) -> str:
    import hashlib

    payload = json.dumps(_jsonable_positions(positions), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tail_leak_rate(records: Sequence[dict[str, Any]], config: ColliderConfig, initial_count: int) -> float:
    if len(records) < 2 or initial_count <= 0:
        return 0.0
    first = records[max(0, len(records) - 3)]
    last = records[-1]
    first_counts = compute_region_counts(first.get("positions", []), config)
    last_counts = compute_region_counts(last.get("positions", []), config)
    first_outside = max(0, int(first_counts["finite_count"]) - int(first_counts["source_count"]))
    last_outside = max(0, int(last_counts["finite_count"]) - int(last_counts["source_count"]))
    step_delta = max(1, int(last["step_index"]) - int(first["step_index"]))
    seconds = step_delta * config.physics_dt
    return max(0.0, (last_outside - first_outside) / initial_count / seconds)


def classify_colleague_trace(records: Sequence[dict[str, Any]], config: ColliderConfig) -> dict[str, Any]:
    if not records:
        return classify_collider_hold(
            variant_id="COLLEAGUE_USD_BOUNDED",
            config=config,
            initial_count=0,
            final_count=0,
            source_count=0,
            target_count=0,
            spill_count=0,
            below_table_count=0,
            nan_count=0,
            tail_leak_rate_fraction_per_second=0.0,
            cpu_collision_fallback_detected=False,
            gpu_collider_unsupported=False,
            fatal_error={"type": "NO_RECORDS", "message": "no particle readback records"},
            particle_motion_observed=False,
        )
    initial_positions = records[0].get("positions", [])
    final_positions = records[-1].get("positions", [])
    counts = compute_region_counts(final_positions, config)
    particle_motion_observed = _max_displacement(initial_positions, final_positions) > 1e-6
    return classify_collider_hold(
        variant_id="COLLEAGUE_USD_BOUNDED",
        config=config,
        initial_count=len(initial_positions),
        final_count=int(counts["finite_count"]),
        source_count=int(counts["source_count"]),
        target_count=int(counts["target_count"]),
        spill_count=int(counts["spill_count"]),
        below_table_count=int(counts["below_table_count"]),
        nan_count=sum(_nan_count(record.get("positions", [])) for record in records),
        tail_leak_rate_fraction_per_second=_tail_leak_rate(records, config, len(initial_positions)),
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        fatal_error=None,
        particle_motion_observed=particle_motion_observed,
    )


def _jsonable_positions(positions: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[float(p[0]), float(p[1]), float(p[2])] for p in positions]


def _write_red_projection_frame(
    *,
    path: Path,
    positions: Sequence[Sequence[float]],
    config: ColliderConfig,
    step_index: int,
    total_steps: int,
) -> None:
    from PIL import Image, ImageDraw

    width, height = 960, 540
    image = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(image)
    finite = _finite_positions(positions)
    counts = compute_region_counts(finite, config)
    title = f"colleague USD liquid leak smoke | step {step_index}/{total_steps}"
    draw.text((24, 18), title, fill=(15, 23, 42))
    draw.text(
        (24, 42),
        (
            f"source={counts['source_count']} spill={counts['spill_count']} "
            f"below_table={counts['below_table_count']} total={counts['finite_count']}"
        ),
        fill=(71, 85, 105),
    )
    draw.text((24, 66), "red points = sampled colleague particles; blue outline = source beaker region", fill=(185, 28, 28))

    sx = config.source_center[0]
    z_values = [p[2] for p in finite]
    z_min = min(z_values + [config.table_z - 0.03])
    z_max = max(z_values + [config.table_z + config.source_height])
    if z_max - z_min < 1e-6:
        z_max = z_min + 0.1

    left, right = 80, 900
    top, bottom = 94, 500
    scale_x = 1800.0
    center_x = 490
    scale_z = (bottom - top) / (z_max - z_min)
    table_y = bottom - int((config.table_z - z_min) * scale_z)
    draw.line((left, table_y, right, table_y), fill=(100, 116, 139), width=3)

    cup_left = center_x - int(config.source_radius * scale_x)
    cup_right = center_x + int(config.source_radius * scale_x)
    cup_top = table_y - int(config.source_height * scale_z)
    draw.rectangle((cup_left, cup_top, cup_right, table_y), outline=(30, 64, 175), width=3)

    stride = max(1, len(finite) // 2500)
    for x, _, z in finite[::stride]:
        px = center_x + int((x - sx) * scale_x)
        py = bottom - int((z - z_min) * scale_z)
        radius = 2 if z >= config.table_z else 4
        color = (220, 38, 38) if z < config.table_z else (239, 68, 68)
        draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=color, outline=color)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _write_mp4_from_frames(frame_paths: Sequence[Path], video_path: Path, *, fps: float) -> bool:
    if not frame_paths:
        return False
    import cv2

    first = cv2.imread(str(frame_paths[0]))
    if first is None:
        return False
    height, width = first.shape[:2]
    video_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    try:
        for frame_path in frame_paths:
            frame = cv2.imread(str(frame_path))
            if frame is None:
                continue
            writer.write(frame)
    finally:
        writer.release()
    return video_path.exists() and video_path.stat().st_size > 0


def _review_camera_pose(config: ColliderConfig) -> dict[str, tuple[float, float, float]]:
    target = (
        config.source_center[0],
        config.source_center[1],
        config.table_z + min(max(config.source_height * 0.15, 0.02), 0.06),
    )
    eye = (
        config.source_center[0] + 0.32,
        config.source_center[1] - 0.58,
        config.table_z + 0.24,
    )
    return {"eye": eye, "target": target, "up": (0.0, 0.0, 1.0)}


def _define_review_camera(stage: Any, config: ColliderConfig) -> dict[str, Any]:
    from pxr import Gf, UsdGeom

    pose = _review_camera_pose(config)
    camera = UsdGeom.Camera.Define(stage, "/World/ReviewCamera")
    eye = Gf.Vec3d(*pose["eye"])
    target = Gf.Vec3d(*pose["target"])
    up = Gf.Vec3d(*pose["up"])
    transform = Gf.Matrix4d(1).SetLookAt(eye, target, up).GetInverse()
    camera.AddTransformOp().Set(transform)
    camera.CreateFocalLengthAttr(20.0)
    camera.CreateHorizontalApertureAttr(22.0)
    camera.CreateVerticalApertureAttr(16.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
    return {
        "camera_path": "/World/ReviewCamera",
        "eye": list(pose["eye"]),
        "target": list(pose["target"]),
        "up": list(pose["up"]),
    }


def _make_review_camera_sensor(config: ColliderConfig, camera_info: dict[str, Any]) -> Any | None:
    try:
        import numpy as np
        from omni.isaac.sensor import Camera

        camera = Camera(
            prim_path="/World/ReviewCamera",
            name="colleague_50k_static_leak_review_camera",
            resolution=(config.render_width, config.render_height),
        )
        camera.initialize()
        orientation = world_camera_quat_look_at(
            eye=camera_info["eye"],
            target=camera_info["target"],
            up=camera_info["up"],
        )
        camera.set_world_pose(
            position=np.array(camera_info["eye"], dtype=float),
            orientation=np.array(orientation, dtype=float),
            camera_axes="world",
        )
        return camera
    except Exception:
        return None


def _try_write_camera_png_with_diagnostics(camera: Any, path: Path) -> tuple[str | None, dict[str, Any]]:
    if camera is None:
        return None, {"status": "camera_none"}
    try:
        from PIL import Image
        import numpy as np

        data = camera.get_rgb()
        array = np.asarray(data)
        diagnostics: dict[str, Any] = {
            "status": "captured",
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "size": int(array.size),
        }
        if array.size == 0:
            diagnostics["status"] = "empty_array"
            return None, diagnostics
        if array.dtype != np.uint8:
            array = array.astype(np.uint8)
        if array.ndim != 3 or array.shape[2] < 3:
            diagnostics["status"] = "invalid_shape"
            return None, diagnostics
        rgb = array[:, :, :3]
        diagnostics["mean"] = float(rgb.mean())
        diagnostics["std"] = float(rgb.std())
        if float(rgb.mean()) < 5.0 or float(rgb.std()) < 2.0:
            diagnostics["status"] = "near_black_or_flat"
            return None, diagnostics
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgb).save(path)
        diagnostics["status"] = "saved_camera_rgb"
        diagnostics["path"] = str(path)
        return "camera_rgb", diagnostics
    except Exception as exc:
        return None, {"status": "exception", "type": type(exc).__name__, "message": str(exc)}


def _bbox_from_stage(stage: Any, prim_path: str) -> BBox:
    from pxr import UsdGeom

    cache = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_, UsdGeom.Tokens.render], useExtentsHint=True)
    box = cache.ComputeWorldBound(stage.GetPrimAtPath(prim_path)).ComputeAlignedBox()
    return BBox(
        min=tuple(float(v) for v in box.GetMin()),
        max=tuple(float(v) for v in box.GetMax()),
    )


def _inspect_colleague_usd(usd_path: Path) -> dict[str, Any]:
    from pxr import Usd

    stage = Usd.Stage.Open(str(usd_path), Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError(f"stage_open_failed:{usd_path}")
    source_bbox = _bbox_from_stage(stage, "/World/beaker2")
    target_bbox = _bbox_from_stage(stage, "/World/beaker1")
    table_bbox = _bbox_from_stage(stage, "/World/table")
    original_positions = _read_points(stage, "/World/ParticleSet")
    width = _read_width(stage, "/World/ParticleSet")
    return {
        "source_bbox": source_bbox,
        "target_bbox": target_bbox,
        "table_bbox": table_bbox,
        "original_positions": original_positions,
        "particle_width": width,
    }


def _read_points(stage: Any, path: str) -> list[tuple[float, float, float]]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim:
        return []
    values = UsdGeom.Points(prim).GetPointsAttr().Get()
    if values is None:
        return []
    return [(float(p[0]), float(p[1]), float(p[2])) for p in values]


def _read_width(stage: Any, path: str, fallback: float = 0.000594) -> float:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim:
        return fallback
    widths = UsdGeom.Points(prim).GetWidthsAttr().Get()
    if widths is None or len(widths) == 0:
        return fallback
    return float(widths[0])


def _author_red_runtime_particles(
    *,
    stage: Any,
    positions: Sequence[Sequence[float]],
    offsets: dict[str, float],
    physics_scene_path: str,
) -> dict[str, str]:
    from omni.physx.scripts import particleUtils, physicsUtils
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    stage.SetEditTarget(stage.GetRootLayer())
    for path in ("/World/ParticleSet", "/World/ParticleSystem", "/World/fluid"):
        prim = stage.GetPrimAtPath(path)
        if prim:
            prim.SetActive(False)

    looks_path = Sdf.Path("/World/Looks")
    if not stage.GetPrimAtPath(looks_path):
        UsdGeom.Scope.Define(stage, looks_path)
    material_path = looks_path.AppendChild("LeakEvidenceRedPBD")
    particleUtils.add_pbd_particle_material(
        stage=stage,
        path=material_path,
        cohesion=0.01,
        damping=0.0,
        friction=0.1,
        surface_tension=0.0074,
        viscosity=0.0000017,
        density=1000.0,
    )
    material = UsdShade.Material(stage.GetPrimAtPath(material_path))
    shader = UsdShade.Shader.Define(stage, material_path.AppendChild("PreviewSurface"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1.0, 0.02, 0.02))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.9)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.35)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

    particle_system = particleUtils.add_physx_particle_system(
        stage=stage,
        particle_system_path=Sdf.Path(EVIDENCE_PARTICLE_SYSTEM_PATH),
        particle_system_enabled=True,
        simulation_owner=Sdf.Path(physics_scene_path),
        contact_offset=offsets["particle_system_contact_offset"],
        rest_offset=0.0,
        particle_contact_offset=offsets["particle_contact_offset"],
        solid_rest_offset=offsets["solid_rest_offset"],
        fluid_rest_offset=offsets["fluid_rest_offset"],
        solver_position_iterations=4,
        max_velocity=5.0,
        max_neighborhood=96,
        global_self_collision_enabled=True,
        non_particle_collision_enabled=True,
    )
    particleUtils.add_physx_particle_isosurface(stage, Sdf.Path(EVIDENCE_PARTICLE_SYSTEM_PATH), enabled=False)
    physicsUtils.add_physics_material_to_prim(stage, particle_system.GetPrim(), material_path)
    UsdShade.MaterialBindingAPI.Apply(particle_system.GetPrim()).Bind(material)

    velocities = [Gf.Vec3f(0.0, 0.0, 0.0)] * len(positions)
    widths = [offsets["particle_width"]] * len(positions)
    points = [Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in positions]
    particle_set = particleUtils.add_physx_particleset_points(
        stage,
        Sdf.Path(EVIDENCE_PARTICLE_SET_PATH),
        points,
        velocities,
        widths,
        Sdf.Path(EVIDENCE_PARTICLE_SYSTEM_PATH),
        True,
        True,
        0,
        0.001,
        1000.0,
    )
    UsdShade.MaterialBindingAPI.Apply(particle_set.GetPrim()).Bind(material)
    particle_set.GetDisplayColorAttr().Set([Gf.Vec3f(1.0, 0.0, 0.0)])
    return {"particle_system_path": EVIDENCE_PARTICLE_SYSTEM_PATH, "particle_set_path": EVIDENCE_PARTICLE_SET_PATH}


def _update_review_markers(
    *,
    stage: Any,
    positions: Sequence[Sequence[float]],
    marker_limit: int,
    marker_width: float,
) -> dict[str, Any]:
    if marker_limit == 0 or marker_width <= 0.0:
        return {"enabled": False, "marker_count": 0, "path": None}
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    marker_positions = select_particle_subset(positions, limit=marker_limit)
    marker_root = Sdf.Path("/World/D3ReviewLeakMarkers")
    marker_path = marker_root.AppendChild("Instancer")
    prototype_path = marker_root.AppendChild("PrototypeSphere")
    UsdGeom.Xform.Define(stage, marker_root)
    prototype = UsdGeom.Sphere.Define(stage, prototype_path)
    prototype.CreateRadiusAttr(float(marker_width))
    prototype.CreateDisplayColorAttr([Gf.Vec3f(1.0, 0.0, 0.0)])
    looks_path = Sdf.Path("/World/Looks")
    if not stage.GetPrimAtPath(looks_path):
        UsdGeom.Scope.Define(stage, looks_path)
    material_path = looks_path.AppendChild("D3ReviewMarkerRed")
    material = UsdShade.Material.Define(stage, material_path)
    shader = UsdShade.Shader.Define(stage, material_path.AppendChild("PreviewSurface"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(1.0, 0.0, 0.0))
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.4, 0.0, 0.0))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.25)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(prototype.GetPrim()).Bind(material)
    instancer = UsdGeom.PointInstancer.Define(stage, marker_path)
    instancer.CreatePrototypesRel().SetTargets([prototype_path])
    instancer.CreateProtoIndicesAttr().Set(Vt.IntArray([0] * len(marker_positions)))
    instancer.CreatePositionsAttr().Set(
        Vt.Vec3fArray([Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in marker_positions])
    )
    return {
        "enabled": True,
        "marker_count": len(marker_positions),
        "path": str(marker_path),
        "prototype_path": str(prototype_path),
    }


def _run_minimal_native_slice(args: argparse.Namespace) -> dict[str, Any]:
    import carb
    import omni.kit.app
    import omni.physx.bindings._physx as pb
    from omni.isaac.core import World
    from omni.isaac.core.utils import stage as stage_utils
    from omni.physx.scripts import physicsUtils
    from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdLux, UsdPhysics

    usd_path = Path(args.usd).resolve()
    native_usd = Path(args.native_usd).resolve()
    artifact_dir = Path(args.out_dir).resolve()
    frames_dir = artifact_dir / "projection_frames"
    rgb_frames_dir = artifact_dir / "rgb_camera_frames"
    trace_path = artifact_dir / "particle_readback_trace.jsonl"
    scene_path = artifact_dir / "minimal_native_beaker_slice.usda"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("", encoding="utf-8")

    inspected = _inspect_colleague_usd(usd_path)
    source_bbox: BBox = inspected["source_bbox"]
    target_bbox: BBox = inspected["target_bbox"]
    table_bbox: BBox = inspected["table_bbox"]
    config = build_tabletop_region_config(
        source_bbox=source_bbox,
        target_bbox=target_bbox,
        table_top_z=float(table_bbox.max[2]),
    )
    if args.position_mode == "source-grid":
        selected_positions = build_source_grid_positions(config=config, count=args.particle_limit)
    else:
        selected_positions = select_particle_subset(inspected["original_positions"], limit=args.particle_limit)
    authored_width = float(inspected["particle_width"])
    offsets = resolve_particle_runtime_offsets(
        authored_width=authored_width,
        particle_width_override=args.particle_width_override,
        particle_contact_offset_override=args.particle_contact_offset_override,
    )
    config = replace(
        config,
        particle_count=len(selected_positions),
        particle_width=offsets["particle_width"],
        particle_contact_offset=offsets["particle_contact_offset"],
        spawn_particle_contact_offset=offsets["particle_contact_offset"],
        particle_system_contact_offset=offsets["particle_system_contact_offset"],
        solid_rest_offset=offsets["solid_rest_offset"],
        fluid_rest_offset=offsets["fluid_rest_offset"],
        steps=args.steps,
        trace_interval=args.trace_interval,
        tail_window_steps=min(args.steps, max(1, args.trace_interval * 3)),
        render_width=args.width,
        render_height=args.height,
    )
    particle_scope = build_particle_scope_summary(
        original_particle_count=len(inspected["original_positions"]),
        selected_particle_count=len(selected_positions),
        particle_limit=args.particle_limit,
    )

    World.clear_instance()
    stage_utils.create_new_stage()
    import omni.usd

    stage = omni.usd.get_context().get_stage()
    world_prim = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world_prim.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    settings = carb.settings.get_settings()
    settings.set(pb.SETTING_UPDATE_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
    settings.set(pb.SETTING_DISPLAY_PARTICLES, pb.VisualizerMode.ALL)
    settings.set_bool("/physics/suppressReadback", False)

    world = World(
        physics_dt=args.physics_dt,
        rendering_dt=args.physics_dt,
        stage_units_in_meters=1.0,
        physics_prim_path="/World/PhysicsScene",
        backend="torch",
        device="cuda:0",
    )
    physics_context = world.get_physics_context()
    settings.set_bool("/physics/suppressReadback", False)
    settings.set(pb.SETTING_UPDATE_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
    physics_context.enable_gpu_dynamics(True)
    physics_context.set_broadphase_type("GPU")
    physics_context.set_solver_type("TGS")
    physics_scene = UsdPhysics.Scene.Get(stage, "/World/PhysicsScene")
    physx_scene_api = PhysxSchema.PhysxSceneAPI.Apply(physics_scene.GetPrim())
    physx_scene_api.CreateEnableGPUDynamicsAttr().Set(True)
    physx_scene_api.CreateBroadphaseTypeAttr().Set("GPU")
    physx_scene_api.CreateGpuMaxParticleContactsAttr().Set(1_048_576)

    UsdGeom.Scope.Define(stage, "/World/Looks")
    spec = build_colleague_variant_spec(args.collider_mode)
    collider_paths = []
    if args.collider_mode != "none":
        collider_paths = _add_native_beaker_isolation(stage, config, native_usd, spec)
    if args.collider_mode != "none":
        _add_target_marker(stage, config)
    physicsUtils.add_ground_plane(
        stage,
        "/World/LeakCatcherGroundPlane",
        "Z",
        0.8,
        Gf.Vec3f(config.source_center[0], config.source_center[1], config.table_z - 0.05),
        Gf.Vec3f(0.32),
    )
    light = UsdLux.DistantLight.Define(stage, "/World/DistantLight")
    light.CreateIntensityAttr(700.0)
    light.AddRotateXYZOp().Set(Gf.Vec3f(55.0, 0.0, 35.0))
    camera_info = _define_review_camera(stage, config)
    authored = _author_red_runtime_particles(
        stage=stage,
        positions=selected_positions,
        offsets=offsets,
        physics_scene_path="/World/PhysicsScene",
    )
    stage.GetRootLayer().Export(str(scene_path))

    world.reset(soft=False)
    world.play()
    for _ in range(3):
        omni.kit.app.get_app().update()
    settings.set_bool("/physics/suppressReadback", False)
    settings.set(pb.SETTING_UPDATE_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
    physics_settings = {
        "physics_scene_path": physics_context.prim_path,
        "gpu_dynamics_enabled": bool(physics_context.is_gpu_dynamics_enabled()),
        "broadphase_type": physics_context.get_broadphase_type(),
        "solver_type": physics_context.get_solver_type(),
        "physics_dt": physics_context.get_physics_dt(),
        "update_to_usd_setting": settings.get(pb.SETTING_UPDATE_TO_USD),
        "update_particles_to_usd_setting": settings.get(pb.SETTING_UPDATE_PARTICLES_TO_USD),
        "update_velocities_to_usd_setting": settings.get(pb.SETTING_UPDATE_VELOCITIES_TO_USD),
        "suppress_readback_setting": settings.get("/physics/suppressReadback"),
    }

    records: list[dict[str, Any]] = []
    frame_paths: list[Path] = []
    rgb_frame_paths: list[Path] = []
    frame_sources: dict[str, str] = {}
    camera_capture_diagnostics: dict[str, dict[str, Any]] = {}
    review_marker_updates: dict[str, dict[str, Any]] = {}
    camera = _make_review_camera_sensor(config, camera_info)
    for _ in range(args.camera_warmup_updates):
        omni.kit.app.get_app().update()
    start = time.monotonic()
    for step_index in range(args.steps + 1):
        positions = _read_points(stage, EVIDENCE_PARTICLE_SET_PATH)
        if step_index % args.trace_interval == 0 or step_index in (0, args.steps):
            record = {
                "step_index": step_index,
                "particle_count": len(positions),
                "aabb": _aabb(positions),
                "centroid": _centroid(positions),
                "region_counts": compute_region_counts(positions, config),
                "nan_count": _nan_count(positions),
                "positions": _jsonable_positions(positions),
            }
            records.append(record)
            _write_trace_line(trace_path, record)
        if step_index % args.video_stride == 0 or step_index in (0, args.steps):
            frame_path = frames_dir / f"frame_{step_index:04d}.png"
            _write_red_projection_frame(
                path=frame_path,
                positions=positions,
                config=config,
                step_index=step_index,
                total_steps=args.steps,
            )
            frame_paths.append(frame_path)
            frame_sources[str(frame_path.relative_to(artifact_dir))] = "diagnostic_projection"
            marker_update = _update_review_markers(
                stage=stage,
                positions=positions,
                marker_limit=args.rgb_review_marker_limit,
                marker_width=args.rgb_review_marker_width,
            )
            review_marker_updates[f"step_{step_index:04d}"] = marker_update
            omni.kit.app.get_app().update()
            rgb_frame_path = rgb_frames_dir / f"frame_{step_index:04d}.png"
            rgb_source, rgb_diagnostics = _try_write_camera_png_with_diagnostics(camera, rgb_frame_path)
            camera_capture_diagnostics[str(rgb_frame_path.relative_to(artifact_dir))] = rgb_diagnostics
            if rgb_source is not None:
                rgb_frame_paths.append(rgb_frame_path)
                frame_sources[str(rgb_frame_path.relative_to(artifact_dir))] = rgb_source
        if step_index < args.steps:
            world.step(render=True)

    classification = classify_colleague_trace(records, config)
    initial_positions = records[0].get("positions", []) if records else []
    final_positions = records[-1].get("positions", []) if records else []
    readback_diagnostics = {
        "initial_position_hash": _position_hash(initial_positions),
        "final_position_hash": _position_hash(final_positions),
        "max_displacement": _max_displacement(initial_positions, final_positions),
        "readback_position_changed": _position_hash(initial_positions) != _position_hash(final_positions),
    }
    video_path = artifact_dir / "colleague_liquid_leak_red_side_projection.mp4"
    video_written = _write_mp4_from_frames(frame_paths, video_path, fps=args.video_fps)
    rgb_video_path = artifact_dir / "colleague_liquid_static_leak_rgb_camera.mp4"
    rgb_video_written = _write_mp4_from_frames(rgb_frame_paths, rgb_video_path, fps=args.video_fps)
    review_camera_summary = build_review_camera_summary(frame_sources)
    summary = {
        "schema_version": 1,
        "manifest_type": "fluid_spike_colleague_liquid_usd_leak_smoke",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "usd_path": str(usd_path),
        "native_usd": str(native_usd),
        "artifact_dir": str(artifact_dir),
        "runtime": "isaacsim41",
        "mode": f"minimal_native_beaker_slice_colleague_positions:{args.collider_mode}",
        "collider_mode": args.collider_mode,
        "runtime_step_executed": True,
        "d1_pbd_completion_overlay_executed": True,
        "d2_static_hold_leak_evidence_executed": True,
        "original_particle_count": len(inspected["original_positions"]),
        "sampled_particle_count": len(selected_positions),
        "particle_scope": particle_scope,
        "position_mode": args.position_mode,
        "authored_particle_width": authored_width,
        "runtime_particle_offsets": offsets,
        "physics_settings": physics_settings,
        "particle_width": offsets["particle_width"],
        "diagnostic_particle_size_override_used": (
            args.particle_width_override is not None or args.particle_contact_offset_override is not None
        ),
        "steps": args.steps,
        "physics_dt": args.physics_dt,
        "region_config": asdict(config),
        "readback_diagnostics": readback_diagnostics,
        "source_bbox": asdict(source_bbox),
        "target_bbox": asdict(target_bbox),
        "table_bbox": asdict(table_bbox),
        "collider_paths": collider_paths,
        "variant_spec": asdict(spec),
        "authored_runtime_paths": authored,
        "classification": classification,
        "trace_path": str(trace_path),
        "video_path": str(video_path) if video_written else None,
        "rgb_camera_video_path": str(rgb_video_path) if rgb_video_written else None,
        "rgb_camera_frame_count": len(rgb_frame_paths),
        "review_camera": {
            **camera_info,
            **review_camera_summary,
            "camera_sensor_created": camera is not None,
            "capture_diagnostics": camera_capture_diagnostics,
            **build_review_marker_summary(
                marker_limit=args.rgb_review_marker_limit,
                marker_width=args.rgb_review_marker_width,
            ),
            "d3_review_marker_updates": review_marker_updates,
            "require_camera_rgb": bool(args.require_camera_rgb),
            "rgb_camera_video_written": rgb_video_written,
        },
        "scene_path": str(scene_path),
        "projection_frame_count": len(frame_paths),
        "elapsed_seconds": time.monotonic() - start,
        "claim_boundary": {
            "allowed": [
                "This run tests colleague liquid initial positions after completing an IsaacSim41 PBD runtime overlay.",
                "If particle_scope.full_original_50k_completed_pbd_overlay is true, this run may be reported as a full original 50k static leak diagnostic.",
                "Leak status may be reported from particle readback region counts for this static hold run.",
                "D3 real IsaacSim41 RGB camera evidence may be reported only when review_camera.d3_real_isaacsim41_rgb_camera_passed is true.",
            ],
            "blocked": [
                "Do not claim the raw original colleague USD direct-stepped without completion overlay.",
                "Do not claim benchmark readiness, visual material parity, S3/S4 pouring, EBench score, or policy success.",
            ],
        },
    }
    _write_json(artifact_dir / "runtime_smoke_summary.json", summary)
    _write_json(Path(args.manifest), summary)
    world.stop()
    return summary


def _run_runtime(args: argparse.Namespace) -> dict[str, Any]:
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": bool(args.headless), "width": args.width, "height": args.height})
    try:
        return _run_minimal_native_slice(args)
    except Exception as exc:  # pragma: no cover - runtime-only path.
        fatal_error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc(limit=30)}
        summary = {
            "schema_version": 1,
            "manifest_type": "fluid_spike_colleague_liquid_usd_leak_smoke",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "runtime": "isaacsim41",
            "runtime_step_executed": False,
            "fatal_error": fatal_error,
        }
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_json(out_dir / "runtime_smoke_summary.json", summary)
        _write_json(Path(args.manifest), summary)
        return summary
    finally:
        app.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", default=DEFAULT_USD)
    parser.add_argument("--native-usd", default=DEFAULT_NATIVE_USD)
    parser.add_argument("--out-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--collider-mode", choices=COLLIDER_MODES, default="native-proxy-wrapper")
    parser.add_argument("--position-mode", choices=POSITION_MODES, default="colleague-sampled")
    parser.add_argument("--particle-limit", type=int, default=1024)
    parser.add_argument("--particle-width-override", type=float, default=None)
    parser.add_argument("--particle-contact-offset-override", type=float, default=None)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--physics-dt", type=float, default=1.0 / 60.0)
    parser.add_argument("--trace-interval", type=int, default=10)
    parser.add_argument("--video-stride", type=int, default=2)
    parser.add_argument("--video-fps", type=float, default=15.0)
    parser.add_argument("--require-camera-rgb", action="store_true")
    parser.add_argument("--camera-warmup-updates", type=int, default=8)
    parser.add_argument("--rgb-review-marker-limit", type=int, default=2500)
    parser.add_argument("--rgb-review-marker-width", type=float, default=0.006)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--headless", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = _run_runtime(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary.get("runtime_step_executed"):
        return 1
    if args.require_camera_rgb and not summary.get("review_camera", {}).get("d3_real_isaacsim41_rgb_camera_passed"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
