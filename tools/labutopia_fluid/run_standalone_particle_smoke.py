#!/usr/bin/env python3
"""Run S1 standalone PhysX/PBD particle smoke in Isaac Sim 4.1."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001"
)
DEFAULT_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_s1_standalone_particle_smoke_20260707.json"
)
DEFAULT_SCENE_PATH = "assets/chemistry_lab/lab_001_fluid_spike/standalone_particle_smoke.usda"


@dataclass(frozen=True)
class SmokeConfig:
    particle_count: int = 256
    grid_dims: tuple[int, int, int] = (8, 8, 4)
    particle_spacing: float = 0.005
    particle_width: float = 0.004
    particle_contact_offset: float = 0.005
    lower: tuple[float, float, float] = (-0.0175, -0.0175, 0.16)
    steps: int = 120
    physics_dt: float = 1.0 / 60.0
    render_width: int = 512
    render_height: int = 512


def build_particle_grid(
    count: int,
    dims: tuple[int, int, int],
    lower: tuple[float, float, float],
    spacing: float,
) -> list[tuple[float, float, float]]:
    """Build a deterministic particle grid in x/y/z order."""
    positions: list[tuple[float, float, float]] = []
    for ix in range(dims[0]):
        for iy in range(dims[1]):
            for iz in range(dims[2]):
                positions.append(
                    (
                        lower[0] + ix * spacing,
                        lower[1] + iy * spacing,
                        lower[2] + iz * spacing,
                    )
                )
                if len(positions) == count:
                    return positions
    raise ValueError(f"particle_count_exceeds_grid_capacity:{count}>{dims[0] * dims[1] * dims[2]}")


def _finite_positions(positions: Sequence[Sequence[float]]) -> list[tuple[float, float, float]]:
    finite: list[tuple[float, float, float]] = []
    for pos in positions:
        values = (float(pos[0]), float(pos[1]), float(pos[2]))
        if all(math.isfinite(v) for v in values):
            finite.append(values)
    return finite


def _nan_count(positions: Sequence[Sequence[float]]) -> int:
    count = 0
    for pos in positions:
        values = (float(pos[0]), float(pos[1]), float(pos[2]))
        if not all(math.isfinite(v) for v in values):
            count += 1
    return count


def _aabb(positions: Sequence[Sequence[float]]) -> dict[str, list[float] | None]:
    finite = _finite_positions(positions)
    if not finite:
        return {"min": None, "max": None}
    return {
        "min": [min(pos[i] for pos in finite) for i in range(3)],
        "max": [max(pos[i] for pos in finite) for i in range(3)],
    }


def _centroid(positions: Sequence[Sequence[float]]) -> list[float] | None:
    finite = _finite_positions(positions)
    if not finite:
        return None
    return [sum(pos[i] for pos in finite) / len(finite) for i in range(3)]


def _max_displacement(initial: Sequence[Sequence[float]], final: Sequence[Sequence[float]]) -> float:
    max_dist = 0.0
    for before, after in zip(initial, final):
        before_v = (float(before[0]), float(before[1]), float(before[2]))
        after_v = (float(after[0]), float(after[1]), float(after[2]))
        if all(math.isfinite(v) for v in before_v + after_v):
            dist = math.sqrt(sum((after_v[i] - before_v[i]) ** 2 for i in range(3)))
            max_dist = max(max_dist, dist)
    return max_dist


def summarize_particle_readback(
    initial_positions: Sequence[Sequence[float]],
    final_positions: Sequence[Sequence[float]],
) -> dict[str, Any]:
    initial_count = len(initial_positions)
    final_count = len(final_positions)
    paired_delta_y: list[float] = []
    paired_delta_z: list[float] = []
    for before, after in zip(initial_positions, final_positions):
        before_v = (float(before[0]), float(before[1]), float(before[2]))
        after_v = (float(after[0]), float(after[1]), float(after[2]))
        if all(math.isfinite(v) for v in before_v + after_v):
            paired_delta_y.append(after_v[1] - before_v[1])
            paired_delta_z.append(after_v[2] - before_v[2])
    return {
        "particle_count_initial": initial_count,
        "particle_count_final": final_count,
        "particle_count_final_fraction": final_count / initial_count if initial_count else 0.0,
        "nan_count": _nan_count(initial_positions) + _nan_count(final_positions),
        "initial_aabb": _aabb(initial_positions),
        "final_aabb": _aabb(final_positions),
        "initial_centroid": _centroid(initial_positions),
        "final_centroid": _centroid(final_positions),
        "mean_delta_y": sum(paired_delta_y) / len(paired_delta_y) if paired_delta_y else None,
        "mean_delta_z": sum(paired_delta_z) / len(paired_delta_z) if paired_delta_z else None,
        "max_displacement": _max_displacement(initial_positions, final_positions),
        "particle_motion_observed": _max_displacement(initial_positions, final_positions) > 1e-5,
    }


def classify_smoke(
    *,
    config: SmokeConfig,
    readback_summary: dict[str, Any] | None,
    gpu_dynamics_enabled: bool,
    readback_available: bool,
    fatal_error: dict[str, Any] | None,
    particle_schema_supported: bool,
) -> dict[str, Any]:
    if fatal_error is not None:
        failure_class = "RUNTIME_CRASH"
    elif not particle_schema_supported:
        failure_class = "PARTICLE_SCHEMA_UNSUPPORTED"
    elif not gpu_dynamics_enabled:
        failure_class = "GPU_DYNAMICS_DISABLED"
    elif not readback_available or readback_summary is None:
        failure_class = "READBACK_UNAVAILABLE"
    elif readback_summary.get("particle_count_initial", 0) <= 0:
        failure_class = "READBACK_UNAVAILABLE"
    elif readback_summary.get("particle_count_final_fraction", 0.0) < 0.95:
        failure_class = "READBACK_UNAVAILABLE"
    elif readback_summary.get("nan_count", 0) != 0:
        failure_class = "READBACK_UNAVAILABLE"
    elif not readback_summary.get("particle_motion_observed", True):
        failure_class = "READBACK_UNAVAILABLE"
    else:
        failure_class = None

    status = "GO_NEXT" if failure_class is None else "STOP_WITH_EVIDENCE"
    return {
        "status": status,
        "failure_class": failure_class,
        "stop_reason": failure_class,
        "s1_particle_runtime_passed": failure_class is None,
        "true_fluid_runtime_claim_allowed": failure_class is None,
        "s2_collider_matrix_released": failure_class is None,
        "pass_criteria": {
            "gpu_dynamics_enabled": bool(gpu_dynamics_enabled),
            "particle_count_initial_gt_zero": bool(
                readback_summary and readback_summary.get("particle_count_initial", 0) > 0
            ),
            "particle_count_final_fraction_ge_0_95": bool(
                readback_summary and readback_summary.get("particle_count_final_fraction", 0.0) >= 0.95
            ),
            "nan_count_eq_zero": bool(readback_summary and readback_summary.get("nan_count", 1) == 0),
            "readback_available": bool(readback_available),
            "particle_motion_observed": bool(readback_summary and readback_summary.get("particle_motion_observed")),
        },
        "expected_particle_count": config.particle_count,
    }


def _json_ready_positions(positions: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[float(pos[0]), float(pos[1]), float(pos[2])] for pos in positions]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_trace_line(trace_path: Path, payload: dict[str, Any]) -> None:
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _write_projection_png(path: Path, positions: Sequence[Sequence[float]], title: str) -> str:
    """Write a deterministic side-view particle diagnostic image."""
    from PIL import Image, ImageDraw

    width, height = 512, 512
    image = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(203, 213, 225))
    draw.line((30, 430, 482, 430), fill=(100, 116, 139), width=2)
    draw.text((28, 20), title, fill=(15, 23, 42))
    draw.text((28, 42), "diagnostic x-z projection from particle readback", fill=(71, 85, 105))

    finite = _finite_positions(positions)
    if finite:
        xs = [p[0] for p in finite]
        zs = [p[2] for p in finite]
        min_x, max_x = min(xs), max(xs)
        min_z, max_z = min(zs), max(zs)
        span_x = max(max_x - min_x, 1e-6)
        span_z = max(max_z - min_z, 0.22)
        for x, _, z in finite:
            px = 80 + int((x - min_x) / span_x * 352)
            py = 430 - int((z - min(0.0, min_z)) / span_z * 330)
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=(37, 99, 235), outline=(30, 64, 175))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return "diagnostic_projection"


def _try_write_camera_png(camera: Any, path: Path) -> str | None:
    try:
        from PIL import Image
        import numpy as np

        data = camera.get_rgb()
        array = np.asarray(data)
        if array.size == 0:
            return None
        if array.dtype != np.uint8:
            array = array.astype(np.uint8)
        if array.ndim != 3 or array.shape[2] < 3:
            return None
        rgb = array[:, :, :3]
        # Headless cameras can return technically valid but visually useless
        # near-black frames when the camera is not fully warmed up or framed.
        if float(rgb.mean()) < 5.0 or float(rgb.std()) < 2.0:
            return None
        Image.fromarray(rgb).save(path)
        return "camera_rgb"
    except Exception:
        return None


def _read_points(stage: Any, path: str = "/World/ParticleSet") -> list[list[float]]:
    from pxr import UsdGeom

    points = UsdGeom.Points(stage.GetPrimAtPath(path))
    values = points.GetPointsAttr().Get()
    if values is None:
        return []
    return _json_ready_positions(values)


def _make_visual_and_pbd_material(stage: Any, material_path: Any) -> None:
    from pxr import Gf, Sdf, UsdShade
    from omni.physx.scripts import particleUtils

    particleUtils.add_pbd_particle_material(
        stage=stage,
        path=material_path,
        cohesion=0.01,
        damping=0.0,
        friction=0.1,
        surface_tension=0.0074,
        viscosity=0.0000017,
        vorticity_confinement=0.0,
        density=1000.0,
    )
    material = UsdShade.Material(stage.GetPrimAtPath(material_path))
    shader = UsdShade.Shader.Define(stage, material_path.AppendChild("PreviewSurface"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.08, 0.32, 1.0))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.55)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.25)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")


def _build_stage(config: SmokeConfig, scene_path: Path) -> dict[str, Any]:
    import carb
    import omni
    import omni.physx.bindings._physx as pb
    from omni.isaac.core import World
    from omni.isaac.core.utils import stage as stage_utils
    from omni.physx.scripts import particleUtils, physicsUtils
    from pxr import Gf, PhysxSchema, Sdf, UsdGeom, UsdLux, UsdPhysics, UsdShade

    World.clear_instance()
    stage_utils.create_new_stage()
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
        physics_dt=config.physics_dt,
        rendering_dt=config.physics_dt,
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

    physics_scene = UsdPhysics.Scene.Get(stage, physics_context.prim_path)
    physx_scene_api = PhysxSchema.PhysxSceneAPI.Apply(physics_scene.GetPrim())
    physx_scene_api.CreateEnableGPUDynamicsAttr().Set(True)
    physx_scene_api.CreateBroadphaseTypeAttr().Set("GPU")
    physx_scene_api.CreateGpuMaxParticleContactsAttr().Set(1_048_576)

    looks_path = Sdf.Path("/World/Looks")
    UsdGeom.Scope.Define(stage, looks_path)
    material_path = looks_path.AppendChild("Blue_Glass")
    _make_visual_and_pbd_material(stage, material_path)

    particle_system_path = Sdf.Path("/World/ParticleSystem")
    particle_system = particleUtils.add_physx_particle_system(
        stage=stage,
        particle_system_path=particle_system_path,
        particle_system_enabled=True,
        simulation_owner=Sdf.Path(physics_context.prim_path),
        contact_offset=config.particle_contact_offset * 1.2,
        rest_offset=0.0,
        particle_contact_offset=config.particle_contact_offset,
        solid_rest_offset=config.particle_contact_offset * 0.6,
        fluid_rest_offset=config.particle_contact_offset * 0.6,
        solver_position_iterations=4,
        max_velocity=5.0,
        max_neighborhood=96,
        global_self_collision_enabled=True,
        non_particle_collision_enabled=True,
    )
    particleUtils.add_physx_particle_isosurface(stage, particle_system_path, enabled=False)
    physicsUtils.add_physics_material_to_prim(stage, particle_system.GetPrim(), material_path)
    UsdShade.MaterialBindingAPI.Apply(particle_system.GetPrim()).Bind(
        UsdShade.Material(stage.GetPrimAtPath(material_path))
    )

    positions = build_particle_grid(
        count=config.particle_count,
        dims=config.grid_dims,
        lower=config.lower,
        spacing=config.particle_spacing,
    )
    velocities = [Gf.Vec3f(0.0, 0.0, 0.0)] * len(positions)
    widths = [config.particle_width] * len(positions)
    particle_set = particleUtils.add_physx_particleset_points(
        stage,
        Sdf.Path("/World/ParticleSet"),
        [Gf.Vec3f(*pos) for pos in positions],
        velocities,
        widths,
        particle_system_path,
        True,
        True,
        0,
        0.001,
        1000.0,
    )
    UsdShade.MaterialBindingAPI.Apply(particle_set.GetPrim()).Bind(UsdShade.Material(stage.GetPrimAtPath(material_path)))
    particle_set.GetDisplayColorAttr().Set([Gf.Vec3f(0.08, 0.32, 1.0)])

    physicsUtils.add_ground_plane(stage, "/World/GroundPlane", "Z", 1.0, Gf.Vec3f(0.0, 0.0, 0.0), Gf.Vec3f(0.5))
    light = UsdLux.DistantLight.Define(stage, "/World/DistantLight")
    light.CreateIntensityAttr(650.0)
    light.AddRotateXYZOp().Set(Gf.Vec3f(55.0, 0.0, 35.0))
    camera = UsdGeom.Camera.Define(stage, "/World/ReviewCamera")
    camera.AddTranslateOp().Set(Gf.Vec3d(0.32, -0.42, 0.26))
    camera.AddRotateXYZOp().Set(Gf.Vec3f(62.0, 0.0, 38.0))
    camera.CreateFocalLengthAttr(28.0)

    scene_path.parent.mkdir(parents=True, exist_ok=True)
    stage.GetRootLayer().Export(str(scene_path))

    return {
        "world": world,
        "stage": stage,
        "physics_context": physics_context,
        "particle_system_path": str(particle_system_path),
        "particle_set_path": "/World/ParticleSet",
        "physics_scene_path": physics_context.prim_path,
        "material_path": str(material_path),
    }


def _make_camera_sensor(config: SmokeConfig) -> Any | None:
    try:
        import numpy as np
        from omni.isaac.core.utils.rotations import euler_angles_to_quat
        from omni.isaac.sensor import Camera

        camera = Camera(
            prim_path="/World/ReviewCamera",
            name="s1_review_camera",
            position=np.array([0.32, -0.42, 0.26]),
            orientation=euler_angles_to_quat([62.0, 0.0, 38.0], degrees=True),
            resolution=(config.render_width, config.render_height),
        )
        camera.initialize()
        return camera
    except Exception:
        return None


def _run_smoke(config: SmokeConfig, artifact_dir: Path, scene_path: Path) -> dict[str, Any]:
    import carb
    import omni.kit.app
    import omni.physx.bindings._physx as pb

    artifact_dir.mkdir(parents=True, exist_ok=True)
    trace_path = artifact_dir / "particle_readback_trace.jsonl"
    trace_path.write_text("", encoding="utf-8")

    built = _build_stage(config, scene_path)
    world = built["world"]
    stage = built["stage"]
    physics_context = built["physics_context"]

    camera = None
    frame_sources: dict[str, str] = {}
    frames = {
        0: "initial_frame.png",
        max(1, config.steps // 2): "mid_frame.png",
        config.steps: "terminal_frame.png",
    }

    physics_settings = {
        "physics_scene_path": built["physics_scene_path"],
        "gpu_dynamics_enabled": bool(physics_context.is_gpu_dynamics_enabled()),
        "broadphase_type": physics_context.get_broadphase_type(),
        "solver_type": physics_context.get_solver_type(),
        "physics_dt": physics_context.get_physics_dt(),
        "particle_system_path": built["particle_system_path"],
        "particle_set_path": built["particle_set_path"],
        "particle_contact_offset": config.particle_contact_offset,
        "isosurface_enabled": False,
        "material_path": built["material_path"],
        "update_to_usd_setting": carb.settings.get_settings().get(pb.SETTING_UPDATE_TO_USD),
        "update_particles_to_usd_setting": carb.settings.get_settings().get(pb.SETTING_UPDATE_PARTICLES_TO_USD),
        "update_velocities_to_usd_setting": carb.settings.get_settings().get(pb.SETTING_UPDATE_VELOCITIES_TO_USD),
        "suppress_readback_setting": carb.settings.get_settings().get("/physics/suppressReadback"),
    }

    world.reset(soft=False)
    world.play()
    for _ in range(3):
        omni.kit.app.get_app().update()
    camera = _make_camera_sensor(config)

    initial_positions: list[list[float]] | None = None
    final_positions: list[list[float]] | None = None
    trace_records: list[dict[str, Any]] = []

    for step_index in range(config.steps + 1):
        positions = _read_points(stage)
        if step_index == 0:
            initial_positions = positions
        if step_index == config.steps:
            final_positions = positions
        if step_index in frames:
            frame_path = artifact_dir / frames[step_index]
            frame_source = _try_write_camera_png(camera, frame_path) if camera is not None else None
            if frame_source is None:
                frame_source = _write_projection_png(frame_path, positions, f"S1 particle smoke step {step_index}")
            frame_sources[frames[step_index]] = frame_source
        if step_index in frames or step_index % 30 == 0:
            trace_record = {
                "step_index": step_index,
                "particle_count": len(positions),
                "aabb": _aabb(positions),
                "centroid": _centroid(positions),
                "nan_count": _nan_count(positions),
                "positions": positions,
            }
            trace_records.append(trace_record)
            _write_trace_line(trace_path, trace_record)
        if step_index < config.steps:
            world.step(render=True)

    readback_available = initial_positions is not None and final_positions is not None and len(final_positions) > 0
    readback_summary = (
        summarize_particle_readback(initial_positions or [], final_positions or []) if readback_available else None
    )
    classification = classify_smoke(
        config=config,
        readback_summary=readback_summary,
        gpu_dynamics_enabled=bool(physics_context.is_gpu_dynamics_enabled()),
        readback_available=readback_available,
        fatal_error=None,
        particle_schema_supported=True,
    )

    summary = {
        "schema_version": 1,
        "manifest_type": "true_physx_pbd_fluid_spike_runtime_smoke_summary",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": asdict(config),
        "scene_path": str(scene_path),
        "artifact_dir": str(artifact_dir),
        "runtime_step_executed": True,
        "readback_available": readback_available,
        "readback_summary": readback_summary,
        "classification": classification,
        "frame_sources": frame_sources,
        "trace_record_count": len(trace_records),
    }
    _write_json(artifact_dir / "runtime_smoke_summary.json", summary)
    _write_json(artifact_dir / "physics_scene_settings.json", physics_settings)
    return summary


def _gpu_probe() -> dict[str, Any]:
    try:
        import torch

        return {
            "torch_cuda_available": bool(torch.cuda.is_available()),
            "torch_cuda_device_count": int(torch.cuda.device_count()),
            "torch_cuda_device_0": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
    except Exception as exc:
        return {"error_type": type(exc).__name__, "error": str(exc)}


def _build_manifest(
    *,
    config: SmokeConfig,
    artifact_dir: Path,
    scene_path: Path,
    summary: dict[str, Any] | None,
    fatal_error: dict[str, Any] | None,
    command: str,
) -> dict[str, Any]:
    readback_summary = summary.get("readback_summary") if summary else None
    classification = (
        summary.get("classification")
        if summary
        else classify_smoke(
            config=config,
            readback_summary=None,
            gpu_dynamics_enabled=False,
            readback_available=False,
            fatal_error=fatal_error,
            particle_schema_supported=fatal_error is None,
        )
    )
    status = classification["status"]
    passed = status == "GO_NEXT"
    return {
        "schema_version": 1,
        "manifest_type": "true_physx_pbd_fluid_spike_evidence",
        "run_id": "fluid_spike_isaacsim41_ebench_s1_standalone_particle_smoke_20260707_001",
        "stage": "S1_PARTICLE_SMOKE",
        "status": status,
        "failure_class": classification.get("failure_class"),
        "stop_reason": classification.get("stop_reason"),
        "live_evidence": True,
        "runtime_step_executed": bool(summary and summary.get("runtime_step_executed")),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "commands": [command],
        "target_runtime": {
            "python": sys.executable,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "accept_eula": os.environ.get("ACCEPT_EULA"),
            "omni_kit_accept_eula": os.environ.get("OMNI_KIT_ACCEPT_EULA"),
            "gpu_probe": _gpu_probe(),
        },
        "scene_path": str(scene_path),
        "artifact_dir": str(artifact_dir),
        "evidence_files": {
            "runtime_smoke_summary": str(artifact_dir / "runtime_smoke_summary.json"),
            "particle_readback_trace": str(artifact_dir / "particle_readback_trace.jsonl"),
            "physics_scene_settings": str(artifact_dir / "physics_scene_settings.json"),
            "initial_frame": str(artifact_dir / "initial_frame.png"),
            "mid_frame": str(artifact_dir / "mid_frame.png"),
            "terminal_frame": str(artifact_dir / "terminal_frame.png"),
            "server_stdout": str(artifact_dir / "server.stdout.txt"),
            "server_stderr": str(artifact_dir / "server.stderr.txt"),
        },
        "smoke_config": asdict(config),
        "gpu_dynamics_enabled": bool(
            summary and summary.get("classification", {}).get("pass_criteria", {}).get("gpu_dynamics_enabled")
        ),
        "particle_count_initial": readback_summary.get("particle_count_initial") if readback_summary else 0,
        "particle_count_final": readback_summary.get("particle_count_final") if readback_summary else 0,
        "particle_count_final_fraction": readback_summary.get("particle_count_final_fraction")
        if readback_summary
        else 0.0,
        "nan_count": readback_summary.get("nan_count") if readback_summary else None,
        "readback_available": bool(summary and summary.get("readback_available")),
        "particle_motion_observed": bool(readback_summary and readback_summary.get("particle_motion_observed")),
        "readback_summary": readback_summary,
        "frame_sources": summary.get("frame_sources") if summary else {},
        "classification": classification,
        "fluid_spike_claim_allowed": True,
        "true_fluid_claim_allowed": False,
        "true_fluid_runtime_claim_allowed": bool(passed),
        "expert_oracle_score_claim_allowed": False,
        "canonical_score_claim_allowed": False,
        "score_claim_allowed": False,
        "policy_score_claim_allowed": False,
        "official_leaderboard_claim_allowed": False,
        "visual_only_liquid_claim_allowed": False,
        "allowed_claims": [
            "S1 standalone PBD particle runtime smoke passed in the selected IsaacSim41 runtime.",
            "GPU dynamics was enabled for the standalone PhysicsScene.",
            "Particle positions stepped and were read back from USD.",
            "S2 beaker collider matrix may proceed.",
        ]
        if passed
        else [
            "S1 standalone particle smoke produced failure evidence.",
            f"S1 stop class is {classification.get('failure_class')}.",
        ],
        "blocked_claims": [
            "level1_pour has true fluid today",
            "particles have stepped in EBench",
            "beaker collider is fluid-compatible",
            "fluid is EBench-scoreable",
            "Expert Oracle Score includes fluid",
            "policy score claim",
            "official leaderboard claim",
            "visual-only liquid equals true fluid",
        ],
        "next_stage": {
            "id": "S2_BEAKER_COLLIDER_SMOKE" if passed else "S1_FAILURE_FOLLOW_UP",
            "goal": "Run the required beaker collider matrix." if passed else "Debug the S1 stop class before S2.",
        },
        "fatal_error": fatal_error,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--scene-path", default=DEFAULT_SCENE_PATH)
    parser.add_argument("--manifest-path", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--particle-count", type=int, default=SmokeConfig.particle_count)
    parser.add_argument("--steps", type=int, default=SmokeConfig.steps)
    parser.add_argument("--width", type=int, default=SmokeConfig.render_width)
    parser.add_argument("--height", type=int, default=SmokeConfig.render_height)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config = SmokeConfig(
        particle_count=args.particle_count,
        steps=args.steps,
        render_width=args.width,
        render_height=args.height,
    )
    artifact_dir = Path(args.artifact_dir).resolve()
    scene_path = Path(args.scene_path).resolve()
    manifest_path = Path(args.manifest_path).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    command = " ".join([sys.executable, Path(__file__).as_posix(), *argv])

    app = None
    summary: dict[str, Any] | None = None
    fatal_error: dict[str, Any] | None = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": bool(args.headless), "width": args.width, "height": args.height})
        summary = _run_smoke(config=config, artifact_dir=artifact_dir, scene_path=scene_path)
    except Exception as exc:
        fatal_error = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback_tail": traceback.format_exc()[-6000:],
        }
        _write_json(
            artifact_dir / "runtime_smoke_summary.json",
            {
                "schema_version": 1,
                "manifest_type": "true_physx_pbd_fluid_spike_runtime_smoke_summary",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "config": asdict(config),
                "scene_path": str(scene_path),
                "artifact_dir": str(artifact_dir),
                "runtime_step_executed": False,
                "readback_available": False,
                "fatal_error": fatal_error,
            },
        )

    manifest = _build_manifest(
        config=config,
        artifact_dir=artifact_dir,
        scene_path=scene_path,
        summary=summary,
        fatal_error=fatal_error,
        command=command,
    )
    _write_json(manifest_path, manifest)
    print(
        "S1 standalone particle smoke "
        f"status={manifest['status']} failure_class={manifest.get('failure_class')} "
        f"manifest={manifest_path}",
        flush=True,
    )
    if app is not None:
        app.close()
    return 0 if manifest["status"] == "GO_NEXT" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
