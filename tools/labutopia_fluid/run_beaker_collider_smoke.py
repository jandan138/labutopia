#!/usr/bin/env python3
"""Run S2 beaker collider matrix for PhysX/PBD particle fluid in Isaac Sim 4.1."""

from __future__ import annotations

import argparse
import json
import math
import os
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

from tools.labutopia_fluid.run_standalone_particle_smoke import (
    _aabb,
    _centroid,
    _finite_positions,
    _json_ready_positions,
    _nan_count,
    _read_points,
    _try_write_camera_png,
    _write_json,
    _write_trace_line,
    build_particle_grid,
)


BEAKER_COLLIDER_VARIANT_IDS = ("C0", "C1", "C2", "C3", "C4", "C5")
CLASSIFICATION_CONTRACT_VERSION = "s2_no_outside_source_v2"
DIAGNOSTIC_PROJECTION_VERSION = "v2_dynamic_z_shows_below_table_leaks"
HOLD_CLASSIFICATIONS = {
    "PASS_SOURCE_HOLD",
    "FAIL_CONTAINER_SEALED",
    "FAIL_CONTAINER_LEAK",
    "FAIL_NATIVE_CONVEX_INTERIOR_NOT_USABLE",
    "FAIL_GPU_COLLIDER_UNSUPPORTED",
    "FAIL_CPU_COLLISION_FALLBACK",
    "FAIL_PARTICLE_EXPLOSION",
    "FAIL_READBACK_UNAVAILABLE",
    "FAIL_PERF_BUDGET_EXCEEDED",
}
DEFAULT_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_s2_beaker_collider_matrix_20260707_001"
)
DEFAULT_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"
)
DEFAULT_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders"
DEFAULT_NATIVE_USD = "assets/chemistry_lab/lab_001/lab_001.usd"


@dataclass(frozen=True)
class ColliderConfig:
    particle_count: int = 256
    grid_dims: tuple[int, int, int] = (8, 8, 4)
    particle_spacing: float = 0.0045
    particle_width: float = 0.0035
    particle_contact_offset: float = 0.0045
    source_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    target_center: tuple[float, float, float] = (0.22, 0.0, 0.0)
    source_radius: float = 0.055
    target_radius: float = 0.055
    source_height: float = 0.13
    target_height: float = 0.13
    wall_height: float = 0.12
    wall_thickness: float = 0.01
    bottom_thickness: float = 0.008
    table_z: float = 0.0
    steps: int = 240
    physics_dt: float = 1.0 / 60.0
    trace_interval: int = 30
    tail_window_steps: int = 60
    render_width: int = 512
    render_height: int = 512
    perf_budget_seconds_per_variant: float = 240.0
    initial_radial_velocity: float = 0.08


@dataclass(frozen=True)
class VariantSpec:
    variant_id: str
    name: str
    description: str
    setup: str
    collider_count: int
    collision_approximation: str
    source_kind: str
    negative_control: bool = False
    native_source_path: str | None = None
    sdf_resolution: int | None = None
    panel_count: int | None = None


def variant_specs() -> dict[str, VariantSpec]:
    return {
        "C0": VariantSpec(
            variant_id="C0",
            name="segmented_box_wall_proxy",
            description="Floor plus 12 thin static box panels, no top cap.",
            setup="positive_control_static_panel_cup",
            collider_count=13,
            collision_approximation="box",
            source_kind="procedural_proxy",
            panel_count=12,
        ),
        "C1": VariantSpec(
            variant_id="C1",
            name="simplified_thick_wall_open_cup_proxy",
            description="Thicker open cup proxy with explicit bottom and 16 static wall panels.",
            setup="thick_static_panel_cup",
            collider_count=17,
            collision_approximation="box",
            source_kind="procedural_proxy",
            panel_count=16,
        ),
        "C2": VariantSpec(
            variant_id="C2",
            name="segmented_convex_wall_pieces",
            description="Curved wall approximated by 24 convex static panels, avoiding one sealing hull.",
            setup="convex_segment_wall_cup",
            collider_count=25,
            collision_approximation="convex_panel_boxes",
            source_kind="procedural_proxy",
            panel_count=24,
        ),
        "C3": VariantSpec(
            variant_id="C3",
            name="sdf_trimesh_open_beaker",
            description="Open concave tri-mesh beaker with PhysX SDF mesh collision attrs.",
            setup="sdf_open_concave_mesh",
            collider_count=1,
            collision_approximation="sdf",
            source_kind="procedural_mesh",
            sdf_resolution=64,
        ),
        "C4": VariantSpec(
            variant_id="C4",
            name="native_beaker2_mesh_convex_decomposition",
            description="Native /World/beaker2/mesh referenced from lab_001 with convexDecomposition.",
            setup="native_beaker2_mesh_reference",
            collider_count=1,
            collision_approximation="convexDecomposition",
            source_kind="native_mesh_reference",
            native_source_path="/World/beaker2/mesh",
        ),
        "C5": VariantSpec(
            variant_id="C5",
            name="custom_cylinder_analytic_negative_control",
            description="Closed analytic cylinder negative control; never promoted to S3.",
            setup="analytic_cylinder_negative_control",
            collider_count=1,
            collision_approximation="analytic_cylinder",
            source_kind="procedural_analytic",
            negative_control=True,
        ),
    }


def source_particle_lower(config: ColliderConfig) -> tuple[float, float, float]:
    grid_x = (config.grid_dims[0] - 1) * config.particle_spacing
    grid_y = (config.grid_dims[1] - 1) * config.particle_spacing
    return (
        config.source_center[0] - grid_x / 2.0,
        config.source_center[1] - grid_y / 2.0,
        config.table_z + config.bottom_thickness + config.particle_contact_offset * 3.0,
    )


def region_definitions(config: ColliderConfig) -> dict[str, Any]:
    return {
        "source_region": (
            "cylindrical region around source container interior; "
            f"center_xy={config.source_center[:2]} radius={config.source_radius} "
            f"z=[{config.table_z}, {config.table_z + config.source_height}]"
        ),
        "target_region": (
            "cylindrical region around target container interior; "
            f"center_xy={config.target_center[:2]} radius={config.target_radius} "
            f"z=[{config.table_z}, {config.table_z + config.target_height}]"
        ),
        "spill_region": "finite particles outside source and target regions with z >= table_z",
        "below_table_region": f"finite particles with z < {config.table_z}",
    }


def _inside_cylinder(
    pos: Sequence[float],
    *,
    center: tuple[float, float, float],
    radius: float,
    z_min: float,
    z_max: float,
) -> bool:
    x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
    return (x - center[0]) ** 2 + (y - center[1]) ** 2 <= radius**2 and z_min <= z <= z_max


def compute_region_counts(positions: Sequence[Sequence[float]], config: ColliderConfig) -> dict[str, int]:
    finite = _finite_positions(positions)
    source_count = 0
    target_count = 0
    spill_count = 0
    below_table_count = 0
    for pos in finite:
        if pos[2] < config.table_z:
            below_table_count += 1
        elif _inside_cylinder(
            pos,
            center=config.source_center,
            radius=config.source_radius,
            z_min=config.table_z,
            z_max=config.table_z + config.source_height,
        ):
            source_count += 1
        elif _inside_cylinder(
            pos,
            center=config.target_center,
            radius=config.target_radius,
            z_min=config.table_z,
            z_max=config.table_z + config.target_height,
        ):
            target_count += 1
        else:
            spill_count += 1
    return {
        "total_count": len(positions),
        "finite_count": len(finite),
        "source_count": source_count,
        "target_count": target_count,
        "spill_count": spill_count,
        "below_table_count": below_table_count,
    }


def _fraction(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def classify_collider_hold(
    *,
    variant_id: str,
    config: ColliderConfig,
    initial_count: int,
    final_count: int,
    source_count: int,
    target_count: int,
    spill_count: int,
    below_table_count: int,
    nan_count: int,
    tail_leak_rate_fraction_per_second: float,
    cpu_collision_fallback_detected: bool,
    gpu_collider_unsupported: bool,
    fatal_error: dict[str, Any] | None,
    particle_motion_observed: bool = True,
    container_sealed_detected: bool = False,
    particle_explosion_detected: bool = False,
    perf_budget_exceeded: bool = False,
) -> dict[str, Any]:
    final_fraction = _fraction(final_count, initial_count)
    source_retention_fraction = _fraction(source_count, initial_count)
    outside_source_count = max(0, final_count - source_count)

    if fatal_error is not None:
        classification = "FAIL_READBACK_UNAVAILABLE"
    elif gpu_collider_unsupported:
        classification = "FAIL_GPU_COLLIDER_UNSUPPORTED"
    elif cpu_collision_fallback_detected:
        classification = "FAIL_CPU_COLLISION_FALLBACK"
    elif perf_budget_exceeded:
        classification = "FAIL_PERF_BUDGET_EXCEEDED"
    elif nan_count != 0 or particle_explosion_detected:
        classification = "FAIL_PARTICLE_EXPLOSION"
    elif initial_count <= 0 or final_count <= 0:
        classification = "FAIL_READBACK_UNAVAILABLE"
    elif not particle_motion_observed:
        classification = "FAIL_READBACK_UNAVAILABLE"
    elif container_sealed_detected:
        classification = "FAIL_CONTAINER_SEALED"
    elif (
        source_retention_fraction < 0.95
        or final_fraction < 0.95
        or outside_source_count != 0
        or target_count != 0
        or spill_count != 0
        or below_table_count != 0
        or tail_leak_rate_fraction_per_second >= 0.02
    ):
        classification = "FAIL_NATIVE_CONVEX_INTERIOR_NOT_USABLE" if variant_id == "C4" else "FAIL_CONTAINER_LEAK"
    else:
        classification = "PASS_SOURCE_HOLD"

    assert classification in HOLD_CLASSIFICATIONS
    return {
        "variant_id": variant_id,
        "classification": classification,
        "source_retention_fraction": source_retention_fraction,
        "particle_count_final_fraction": final_fraction,
        "target_count": target_count,
        "spill_count": spill_count,
        "outside_source_count": outside_source_count,
        "below_table_count": below_table_count,
        "nan_count": nan_count,
        "tail_leak_rate_fraction_per_second": tail_leak_rate_fraction_per_second,
        "cpu_collision_fallback_detected": bool(cpu_collision_fallback_detected),
        "gpu_collider_unsupported": bool(gpu_collider_unsupported),
        "pass_criteria": {
            "source_retention_fraction_ge_0_95": source_retention_fraction >= 0.95,
            "particle_count_final_fraction_ge_0_95": final_fraction >= 0.95,
            "outside_source_count_eq_zero": outside_source_count == 0,
            "target_count_eq_zero": target_count == 0,
            "spill_count_eq_zero": spill_count == 0,
            "below_table_count_eq_zero": below_table_count == 0,
            "tail_leak_rate_lt_0_02": tail_leak_rate_fraction_per_second < 0.02,
            "cpu_collision_fallback_detected_false": not cpu_collision_fallback_detected,
            "nan_count_eq_zero": nan_count == 0,
            "particle_motion_observed": bool(particle_motion_observed),
        },
        "fatal_error": fatal_error,
    }


def rank_collider_variants(variant_results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    passed = [
        result
        for result in variant_results
        if result.get("classification") == "PASS_SOURCE_HOLD" and result.get("variant_id") != "C5"
    ]
    passed = sorted(
        passed,
        key=lambda result: (
            -float(result.get("source_retention_fraction", 0.0)),
            float(result.get("tail_leak_rate_fraction_per_second", 999.0)),
            str(result.get("variant_id")),
        ),
    )
    best_for_s3 = [str(result["variant_id"]) for result in passed]
    by_id = {str(result.get("variant_id")): result for result in variant_results}
    s2_status = "GO_NEXT" if best_for_s3 else "STOP_WITH_EVIDENCE"
    return {
        "best_for_s3": best_for_s3,
        "native_beaker_status": by_id.get("C4", {}).get("classification", "NOT_RUN"),
        "negative_control_status": by_id.get("C5", {}).get("classification", "NOT_RUN"),
        "s2_status": s2_status,
        "reason": "at_least_one_non_negative_control_variant_passed"
        if best_for_s3
        else "no_non_negative_control_variant_passed",
    }


def _particle_positions(config: ColliderConfig) -> list[tuple[float, float, float]]:
    return build_source_particle_positions(config)


def build_source_particle_positions(config: ColliderConfig) -> list[tuple[float, float, float]]:
    """Build deterministic source particles that exercise the beaker wall."""
    positions: list[tuple[float, float, float]] = []
    usable_radius = config.source_radius - config.particle_contact_offset * 1.2
    lower_z = source_particle_lower(config)[2]
    samples_per_axis = int(math.ceil((usable_radius * 2.0) / config.particle_spacing)) + 1
    start = -usable_radius
    candidates: list[tuple[float, float, float, float]] = []
    for iz in range(config.grid_dims[2]):
        z = lower_z + iz * config.particle_spacing
        for ix in range(samples_per_axis):
            x = start + ix * config.particle_spacing
            for iy in range(samples_per_axis):
                y = start + iy * config.particle_spacing
                radius = math.sqrt(x * x + y * y)
                if radius <= usable_radius:
                    angle = math.atan2(y, x)
                    candidates.append(
                        (
                            config.source_center[0] + x,
                            config.source_center[1] + y,
                            z,
                            radius + angle * 1e-6,
                        )
                    )
    candidates.sort(key=lambda item: (-item[3], item[2], item[0], item[1]))
    if len(candidates) < config.particle_count:
        raise ValueError(f"particle_count_exceeds_source_capacity:{config.particle_count}>{len(candidates)}")
    for x, y, z, _ in candidates[: config.particle_count]:
        positions.append((x, y, z))
    return positions


def build_source_particle_initial_velocities(
    positions: Sequence[Sequence[float]],
    config: ColliderConfig,
) -> list[tuple[float, float, float]]:
    velocities: list[tuple[float, float, float]] = []
    for pos in positions:
        dx = float(pos[0]) - config.source_center[0]
        dy = float(pos[1]) - config.source_center[1]
        radius = math.sqrt(dx * dx + dy * dy)
        if radius <= 1e-9:
            velocities.append((0.0, 0.0, 0.0))
        else:
            scale = config.initial_radial_velocity / radius
            velocities.append((dx * scale, dy * scale, 0.0))
    return velocities


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
        density=1000.0,
    )
    material = UsdShade.Material(stage.GetPrimAtPath(material_path))
    shader = UsdShade.Shader.Define(stage, material_path.AppendChild("PreviewSurface"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.08, 0.32, 1.0))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.55)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.25)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")


def _rotation_quat_z(theta: float) -> Any:
    from pxr import Gf

    return Gf.Quatf(math.cos(theta / 2.0), Gf.Vec3f(0.0, 0.0, math.sin(theta / 2.0)))


def _apply_static_collision(
    prim: Any,
    *,
    approximation: str | None = None,
    contact_offset: float = 0.003,
    rest_offset: float = 0.0,
    sdf_resolution: int | None = None,
) -> None:
    from pxr import PhysxSchema, UsdPhysics

    collision_api = UsdPhysics.CollisionAPI.Apply(prim)
    collision_api.CreateCollisionEnabledAttr().Set(True)
    physx_collision = PhysxSchema.PhysxCollisionAPI.Apply(prim)
    physx_collision.CreateContactOffsetAttr().Set(contact_offset)
    physx_collision.CreateRestOffsetAttr().Set(rest_offset)
    if approximation is not None:
        mesh_collision = UsdPhysics.MeshCollisionAPI.Apply(prim)
        mesh_collision.CreateApproximationAttr().Set(approximation)
    if sdf_resolution is not None and hasattr(PhysxSchema, "PhysxSDFMeshCollisionAPI"):
        sdf_api = PhysxSchema.PhysxSDFMeshCollisionAPI.Apply(prim)
        sdf_api.CreateSdfResolutionAttr().Set(int(sdf_resolution))
        sdf_api.CreateSdfSubgridResolutionAttr().Set(4)
        sdf_api.CreateSdfMarginAttr().Set(0.002)


def _add_static_box(
    stage: Any,
    path: str,
    *,
    size: tuple[float, float, float],
    position: tuple[float, float, float],
    angle_z: float = 0.0,
    color: tuple[float, float, float] = (0.72, 0.78, 0.86),
) -> Any:
    from omni.physx.scripts import physicsUtils
    from pxr import Gf

    prim = physicsUtils.add_cube(
        stage,
        path,
        size=Gf.Vec3f(*size),
        position=Gf.Vec3f(*position),
        orientation=_rotation_quat_z(angle_z),
        color=Gf.Vec3f(*color),
    )
    _apply_static_collision(prim)
    return prim


def _add_segmented_cup(stage: Any, config: ColliderConfig, *, panel_count: int, wall_thickness: float) -> list[str]:
    collider_paths: list[str] = []
    radius = config.source_radius
    bottom_size = (radius * 2.2, radius * 2.2, config.bottom_thickness)
    bottom_z = config.table_z + config.bottom_thickness / 2.0
    bottom = _add_static_box(
        stage,
        "/World/SourceContainer/Bottom",
        size=bottom_size,
        position=(config.source_center[0], config.source_center[1], bottom_z),
        color=(0.56, 0.64, 0.76),
    )
    collider_paths.append(str(bottom.GetPath()))

    panel_width = 2.0 * math.pi * radius / panel_count * 1.08
    wall_center_z = config.table_z + config.bottom_thickness + config.wall_height / 2.0
    for index in range(panel_count):
        theta = 2.0 * math.pi * index / panel_count
        center_radius = radius + wall_thickness / 2.0
        x = config.source_center[0] + center_radius * math.cos(theta)
        y = config.source_center[1] + center_radius * math.sin(theta)
        panel = _add_static_box(
            stage,
            f"/World/SourceContainer/Wall_{index:02d}",
            size=(panel_width, wall_thickness, config.wall_height),
            position=(x, y, wall_center_z),
            angle_z=theta + math.pi / 2.0,
            color=(0.62, 0.72, 0.88),
        )
        collider_paths.append(str(panel.GetPath()))
    return collider_paths


def _build_open_beaker_mesh_points(config: ColliderConfig, *, segments: int = 32) -> tuple[list[Any], list[int], list[int]]:
    from pxr import Gf

    points: list[Any] = []
    indices: list[int] = []
    counts: list[int] = []
    outer_r = config.source_radius + config.wall_thickness
    inner_r = config.source_radius
    z0 = config.table_z
    z1 = config.table_z + config.wall_height
    for z in (z0, z1):
        for radius in (outer_r, inner_r):
            for index in range(segments):
                theta = 2.0 * math.pi * index / segments
                points.append(
                    Gf.Vec3f(
                        config.source_center[0] + radius * math.cos(theta),
                        config.source_center[1] + radius * math.sin(theta),
                        z,
                    )
                )

    outer_bottom = 0
    inner_bottom = segments
    outer_top = 2 * segments
    inner_top = 3 * segments
    bottom_center = len(points)
    points.append(Gf.Vec3f(config.source_center[0], config.source_center[1], z0))
    for index in range(segments):
        nxt = (index + 1) % segments
        counts.append(4)
        indices.extend([outer_bottom + index, outer_bottom + nxt, outer_top + nxt, outer_top + index])
        counts.append(4)
        indices.extend([inner_bottom + nxt, inner_bottom + index, inner_top + index, inner_top + nxt])
        counts.append(4)
        indices.extend([outer_bottom + nxt, outer_bottom + index, inner_bottom + index, inner_bottom + nxt])
        counts.append(3)
        indices.extend([bottom_center, inner_bottom + index, inner_bottom + nxt])
    return points, counts, indices


def _add_sdf_open_beaker(stage: Any, config: ColliderConfig, spec: VariantSpec) -> list[str]:
    from pxr import Sdf, UsdGeom

    points, counts, indices = _build_open_beaker_mesh_points(config)
    mesh = UsdGeom.Mesh.Define(stage, "/World/SourceContainer/SDFOpenBeaker")
    mesh.CreatePointsAttr().Set(points)
    mesh.CreateFaceVertexCountsAttr().Set(counts)
    mesh.CreateFaceVertexIndicesAttr().Set(indices)
    mesh.CreateDoubleSidedAttr().Set(True)
    mesh.CreateDisplayColorAttr().Set([(0.52, 0.7, 0.92)])
    _apply_static_collision(
        mesh.GetPrim(),
        approximation="sdf",
        contact_offset=0.003,
        rest_offset=0.0,
        sdf_resolution=spec.sdf_resolution or 64,
    )
    mesh.GetPrim().CreateAttribute("labutopia:s2SdfResolution", Sdf.ValueTypeNames.Int).Set(spec.sdf_resolution or 64)
    return [str(mesh.GetPath())]


def _add_native_beaker_reference(stage: Any, config: ColliderConfig, native_usd: Path, spec: VariantSpec) -> list[str]:
    from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics

    parent = UsdGeom.Xform.Define(stage, "/World/SourceContainer/NativeBeaker2")
    translate_op = parent.AddTranslateOp()
    parent.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 45.0))
    translate_op.Set(Gf.Vec3d(0.0, 0.0, 0.0))

    mesh_prim = stage.DefinePrim("/World/SourceContainer/NativeBeaker2/mesh", "Mesh")
    mesh_prim.GetReferences().AddReference(str(native_usd), spec.native_source_path or "/World/beaker2/mesh")

    # Reference only /World/beaker2/mesh, then supply the missing native parent
    # orientation and recenter the resulting world-space bound around S2 source.
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "proxy"], useExtentsHint=True)
    bound = cache.ComputeWorldBound(mesh_prim).ComputeAlignedBox()
    midpoint = bound.GetMidpoint()
    min_z = bound.GetMin()[2]
    translate_op.Set(
        Gf.Vec3d(
            config.source_center[0] - midpoint[0],
            config.source_center[1] - midpoint[1],
            config.table_z - min_z,
        )
    )

    if mesh_prim.HasAPI(UsdPhysics.RigidBodyAPI):
        rigid_body = UsdPhysics.RigidBodyAPI.Apply(mesh_prim)
        rigid_body.CreateRigidBodyEnabledAttr().Set(False)
        rigid_body.CreateKinematicEnabledAttr().Set(False)
    _apply_static_collision(mesh_prim, approximation="convexDecomposition", contact_offset=0.002, rest_offset=-0.001)
    if hasattr(PhysxSchema, "PhysxConvexDecompositionCollisionAPI"):
        convex_api = PhysxSchema.PhysxConvexDecompositionCollisionAPI.Apply(mesh_prim)
        if hasattr(convex_api, "CreateVoxelResolutionAttr"):
            convex_api.CreateVoxelResolutionAttr().Set(500000)
        if hasattr(convex_api, "CreateMinThicknessAttr"):
            convex_api.CreateMinThicknessAttr().Set(0.001)
    mesh_prim.CreateAttribute("labutopia:nativeSourceUsd", Sdf.ValueTypeNames.String).Set(str(native_usd))
    mesh_prim.CreateAttribute("labutopia:nativeSourcePrim", Sdf.ValueTypeNames.String).Set(
        spec.native_source_path or "/World/beaker2/mesh"
    )
    return [str(mesh_prim.GetPath())]


def _add_analytic_cylinder(stage: Any, config: ColliderConfig) -> list[str]:
    from pxr import UsdGeom

    cylinder = UsdGeom.Cylinder.Define(stage, "/World/SourceContainer/ClosedCylinderNegativeControl")
    cylinder.CreateRadiusAttr().Set(config.source_radius)
    cylinder.CreateHeightAttr().Set(config.wall_height)
    cylinder.CreateAxisAttr().Set("Z")
    cylinder.AddTranslateOp().Set(
        (config.source_center[0], config.source_center[1], config.table_z + config.wall_height / 2.0)
    )
    cylinder.CreateDisplayColorAttr().Set([(0.88, 0.62, 0.56)])
    _apply_static_collision(cylinder.GetPrim(), contact_offset=0.003, rest_offset=0.0)
    return [str(cylinder.GetPath())]


def _add_target_marker(stage: Any, config: ColliderConfig) -> None:
    # The target cup is diagnostic only in S2 static hold; no collider is needed yet.
    _add_static_box(
        stage,
        "/World/TargetRegionMarker",
        size=(config.target_radius * 2.0, config.target_radius * 2.0, 0.001),
        position=(config.target_center[0], config.target_center[1], config.table_z - 0.025),
        color=(0.78, 0.86, 0.62),
    )


def _add_colliders(stage: Any, config: ColliderConfig, spec: VariantSpec, native_usd: Path) -> list[str]:
    from pxr import UsdGeom

    UsdGeom.Xform.Define(stage, "/World/SourceContainer")
    if spec.variant_id == "C0":
        return _add_segmented_cup(stage, config, panel_count=12, wall_thickness=config.wall_thickness)
    if spec.variant_id == "C1":
        return _add_segmented_cup(stage, replace(config, wall_thickness=0.014), panel_count=16, wall_thickness=0.014)
    if spec.variant_id == "C2":
        return _add_segmented_cup(stage, replace(config, wall_thickness=0.008), panel_count=24, wall_thickness=0.008)
    if spec.variant_id == "C3":
        return _add_sdf_open_beaker(stage, config, spec)
    if spec.variant_id == "C4":
        return _add_native_beaker_reference(stage, config, native_usd, spec)
    if spec.variant_id == "C5":
        return _add_analytic_cylinder(stage, config)
    raise ValueError(f"unknown_variant:{spec.variant_id}")


def _write_diagnostic_png(
    path: Path,
    positions: Sequence[Sequence[float]],
    config: ColliderConfig,
    *,
    title: str,
    view: str,
) -> str:
    from PIL import Image, ImageDraw

    width, height = 512, 512
    image = Image.new("RGB", (width, height), (248, 250, 252))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(203, 213, 225))
    draw.text((24, 18), title, fill=(15, 23, 42))
    draw.text((24, 40), f"diagnostic {view} projection from particle readback", fill=(71, 85, 105))
    finite = _finite_positions(positions)

    if view == "top":
        scale = 1500.0
        ox, oy = 180, 256
        sx, sy = config.source_center[0], config.source_center[1]
        tx, ty = config.target_center[0], config.target_center[1]
        for cx, cy, radius, outline in (
            (sx, sy, config.source_radius, (30, 64, 175)),
            (tx, ty, config.target_radius, (77, 124, 15)),
        ):
            px = ox + int((cx - sx) * scale)
            py = oy - int((cy - sy) * scale)
            rr = int(radius * scale)
            draw.ellipse((px - rr, py - rr, px + rr, py + rr), outline=outline, width=2)
        for x, y, z in finite:
            px = ox + int((x - sx) * scale)
            py = oy - int((y - sy) * scale)
            color = (37, 99, 235) if z >= config.table_z else (220, 38, 38)
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=color, outline=color)
    else:
        scale_x = 1500.0
        ox = 160
        sx = config.source_center[0]
        finite_z = [pos[2] for pos in finite]
        z_min = min(finite_z + [config.table_z - 0.02])
        z_max = max(finite_z + [config.table_z + config.source_height])
        if z_max - z_min < 1e-6:
            z_max = z_min + 0.1
        top_y = 92
        bottom_y = 470
        scale_z = (bottom_y - top_y) / (z_max - z_min)
        ground_y = bottom_y - int((config.table_z - z_min) * scale_z)
        draw.line((28, ground_y, 484, ground_y), fill=(100, 116, 139), width=2)
        cup_left = ox - int(config.source_radius * scale_x)
        cup_right = ox + int(config.source_radius * scale_x)
        cup_top = ground_y - int(config.source_height * scale_z)
        draw.rectangle((cup_left, cup_top, cup_right, ground_y), outline=(30, 64, 175), width=2)
        for x, _, z in finite:
            px = ox + int((x - sx) * scale_x)
            py = bottom_y - int((z - z_min) * scale_z)
            color = (37, 99, 235) if z >= config.table_z else (220, 38, 38)
            draw.ellipse((px - 3, py - 3, px + 3, py + 3), fill=color, outline=color)
        draw.text((28, 64), "red = below table / leak", fill=(185, 28, 28))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    if view == "side":
        return "diagnostic_side_projection_v2_dynamic_z"
    return f"diagnostic_{view}_projection"


def _build_variant_stage(
    *,
    config: ColliderConfig,
    spec: VariantSpec,
    scene_path: Path,
    native_usd: Path,
) -> dict[str, Any]:
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
    settings.set_bool("/physics/suppressReadback", False)
    physics_context.enable_gpu_dynamics(True)
    physics_context.set_broadphase_type("GPU")
    physics_context.set_solver_type("TGS")

    physics_scene = UsdPhysics.Scene.Get(stage, physics_context.prim_path)
    physx_scene_api = PhysxSchema.PhysxSceneAPI.Apply(physics_scene.GetPrim())
    physx_scene_api.CreateEnableGPUDynamicsAttr().Set(True)
    physx_scene_api.CreateBroadphaseTypeAttr().Set("GPU")
    physx_scene_api.CreateGpuMaxParticleContactsAttr().Set(1_048_576)

    UsdGeom.Scope.Define(stage, "/World/Looks")
    material_path = Sdf.Path("/World/Looks/Blue_Glass")
    _make_visual_and_pbd_material(stage, material_path)

    collider_paths = _add_colliders(stage, config, spec, native_usd)
    _add_target_marker(stage, config)
    physicsUtils.add_ground_plane(
        stage,
        "/World/LeakCatcherGroundPlane",
        "Z",
        0.8,
        Gf.Vec3f(config.source_center[0], config.source_center[1], config.table_z - 0.05),
        Gf.Vec3f(0.32),
    )

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
        solver_position_iterations=5,
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

    positions = _particle_positions(config)
    initial_velocities = build_source_particle_initial_velocities(positions, config)
    velocities = [Gf.Vec3f(*velocity) for velocity in initial_velocities]
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

    light = UsdLux.DistantLight.Define(stage, "/World/DistantLight")
    light.CreateIntensityAttr(700.0)
    light.AddRotateXYZOp().Set(Gf.Vec3f(55.0, 0.0, 35.0))
    camera = UsdGeom.Camera.Define(stage, "/World/ReviewCamera")
    camera.AddTranslateOp().Set(Gf.Vec3d(0.28, -0.34, 0.22))
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
        "collider_paths": collider_paths,
    }


def _make_camera_sensor(config: ColliderConfig) -> Any | None:
    try:
        import numpy as np
        from omni.isaac.core.utils.rotations import euler_angles_to_quat
        from omni.isaac.sensor import Camera

        camera = Camera(
            prim_path="/World/ReviewCamera",
            name="s2_review_camera",
            position=np.array([0.28, -0.34, 0.22]),
            orientation=euler_angles_to_quat([62.0, 0.0, 38.0], degrees=True),
            resolution=(config.render_width, config.render_height),
        )
        camera.initialize()
        return camera
    except Exception:
        return None


def _trace_tail_leak_rate(records: Sequence[dict[str, Any]], config: ColliderConfig, initial_count: int) -> float:
    if not records or initial_count <= 0:
        return 999.0
    tail_start_step = max(0, config.steps - config.tail_window_steps)
    tail_records = [record for record in records if int(record["step_index"]) >= tail_start_step]
    if len(tail_records) < 2:
        return 0.0
    first = tail_records[0]
    last = tail_records[-1]
    lost_fraction = max(0.0, float(first["region_counts"]["source_count"] - last["region_counts"]["source_count"]))
    lost_fraction /= initial_count
    elapsed = max((int(last["step_index"]) - int(first["step_index"])) * config.physics_dt, config.physics_dt)
    return lost_fraction / elapsed


def _max_displacement(initial: Sequence[Sequence[float]], final: Sequence[Sequence[float]]) -> float:
    max_dist = 0.0
    for before, after in zip(initial, final):
        before_v = (float(before[0]), float(before[1]), float(before[2]))
        after_v = (float(after[0]), float(after[1]), float(after[2]))
        if all(math.isfinite(v) for v in before_v + after_v):
            max_dist = max(max_dist, math.dist(before_v, after_v))
    return max_dist


def _explosion_detected(positions: Sequence[Sequence[float]], config: ColliderConfig) -> bool:
    finite = _finite_positions(positions)
    if not finite:
        return False
    return any(abs(value) > 20.0 for pos in finite for value in pos) or any(
        pos[2] > config.table_z + 2.0 for pos in finite
    )


def _run_variant(
    *,
    config: ColliderConfig,
    spec: VariantSpec,
    artifact_dir: Path,
    scene_path: Path,
    native_usd: Path,
) -> dict[str, Any]:
    import carb
    import omni.kit.app
    import omni.physx.bindings._physx as pb

    started = time.monotonic()
    variant_dir = artifact_dir / spec.variant_id
    variant_dir.mkdir(parents=True, exist_ok=True)
    trace_path = variant_dir / "particle_readback_trace.jsonl"
    trace_path.write_text("", encoding="utf-8")

    built = _build_variant_stage(config=config, spec=spec, scene_path=scene_path, native_usd=native_usd)
    world = built["world"]
    stage = built["stage"]
    physics_context = built["physics_context"]

    physics_settings = {
        "physics_scene_path": built["physics_scene_path"],
        "gpu_dynamics_enabled": bool(physics_context.is_gpu_dynamics_enabled()),
        "broadphase_type": physics_context.get_broadphase_type(),
        "solver_type": physics_context.get_solver_type(),
        "physics_dt": physics_context.get_physics_dt(),
        "particle_system_path": built["particle_system_path"],
        "particle_set_path": built["particle_set_path"],
        "particle_contact_offset": config.particle_contact_offset,
        "variant": asdict(spec),
        "collider_paths": built["collider_paths"],
        "region_definitions": region_definitions(config),
        "update_to_usd_setting": carb.settings.get_settings().get(pb.SETTING_UPDATE_TO_USD),
        "update_particles_to_usd_setting": carb.settings.get_settings().get(pb.SETTING_UPDATE_PARTICLES_TO_USD),
        "update_velocities_to_usd_setting": carb.settings.get_settings().get(pb.SETTING_UPDATE_VELOCITIES_TO_USD),
        "suppress_readback_setting": carb.settings.get_settings().get("/physics/suppressReadback"),
    }

    frames = {
        0: "initial_frame.png",
        max(1, config.steps // 2): "mid_frame.png",
        config.steps: "terminal_frame.png",
    }
    frame_sources: dict[str, str] = {}
    camera = None
    initial_positions: list[list[float]] | None = None
    final_positions: list[list[float]] | None = None
    records: list[dict[str, Any]] = []

    world.reset(soft=False)
    world.play()
    camera = _make_camera_sensor(config)

    for step_index in range(config.steps + 1):
        if step_index > 0:
            world.step(render=True)
        positions = _read_points(stage)
        if step_index == 0:
            initial_positions = positions
        if step_index == config.steps:
            final_positions = positions
        if step_index in frames:
            frame_path = variant_dir / frames[step_index]
            source = _try_write_camera_png(camera, frame_path) if camera is not None else None
            if source is None:
                source = _write_diagnostic_png(
                    frame_path,
                    positions,
                    config,
                    title=f"S2 {spec.variant_id} {spec.name} step {step_index}",
                    view="side",
                )
            frame_sources[frames[step_index]] = source
        if step_index % config.trace_interval == 0 or step_index in frames:
            record = {
                "step_index": step_index,
                "particle_count": len(positions),
                "aabb": _aabb(positions),
                "centroid": _centroid(positions),
                "nan_count": _nan_count(positions),
                "region_counts": compute_region_counts(positions, config),
                "positions": positions,
            }
            records.append(record)
            _write_trace_line(trace_path, record)

    final_positions = final_positions or []
    initial_positions = initial_positions or []
    final_region_counts = compute_region_counts(final_positions, config)
    tail_leak_rate = _trace_tail_leak_rate(records, config, len(initial_positions))
    max_displacement = _max_displacement(initial_positions, final_positions)
    elapsed_seconds = time.monotonic() - started
    fatal_error = None
    classification = classify_collider_hold(
        variant_id=spec.variant_id,
        config=config,
        initial_count=len(initial_positions),
        final_count=len(final_positions),
        source_count=final_region_counts["source_count"],
        target_count=final_region_counts["target_count"],
        spill_count=final_region_counts["spill_count"],
        below_table_count=final_region_counts["below_table_count"],
        nan_count=_nan_count(initial_positions) + _nan_count(final_positions),
        tail_leak_rate_fraction_per_second=tail_leak_rate,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        fatal_error=fatal_error,
        particle_motion_observed=max_displacement > 1e-5,
        container_sealed_detected=False,
        particle_explosion_detected=_explosion_detected(final_positions, config),
        perf_budget_exceeded=elapsed_seconds > config.perf_budget_seconds_per_variant,
    )

    _write_diagnostic_png(
        variant_dir / "top_collision_overlay.png",
        final_positions,
        config,
        title=f"S2 {spec.variant_id} final top overlay",
        view="top",
    )
    _write_diagnostic_png(
        variant_dir / "side_collision_overlay.png",
        final_positions,
        config,
        title=f"S2 {spec.variant_id} final side overlay",
        view="side",
    )
    frame_sources["top_collision_overlay.png"] = "diagnostic_top_projection"
    frame_sources["side_collision_overlay.png"] = "diagnostic_side_projection"

    summary = {
        "schema_version": 1,
        "manifest_type": "true_physx_pbd_fluid_spike_s2_variant_summary",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "S2_BEAKER_COLLIDER_SMOKE",
        "variant": asdict(spec),
        "config": asdict(config),
        "classification_contract_version": CLASSIFICATION_CONTRACT_VERSION,
        "scene_path": str(scene_path),
        "artifact_dir": str(variant_dir),
        "runtime_step_executed": True,
        "readback_available": bool(initial_positions and final_positions),
        "initial_count": len(initial_positions),
        "final_count": len(final_positions),
        "initial_region_counts": compute_region_counts(initial_positions, config),
        "final_region_counts": final_region_counts,
        "initial_aabb": _aabb(initial_positions),
        "final_aabb": _aabb(final_positions),
        "initial_centroid": _centroid(initial_positions),
        "final_centroid": _centroid(final_positions),
        "tail_leak_rate_fraction_per_second": tail_leak_rate,
        "max_displacement": max_displacement,
        "particle_motion_observed": max_displacement > 1e-5,
        "elapsed_seconds": elapsed_seconds,
        "classification": classification["classification"],
        "classification_detail": classification,
        "diagnostic_projection_version": DIAGNOSTIC_PROJECTION_VERSION,
        "runtime_warning_evidence_mode": (
            "variant-level flags are initialized during simulation; "
            "artifact-level stdout/stderr warning scan is authoritative for release"
        ),
        "frame_sources": frame_sources,
        "trace_record_count": len(records),
        "evidence_files": {
            "particle_readback_trace": str(trace_path),
            "physics_scene_settings": str(variant_dir / "physics_scene_settings.json"),
            "initial_frame": str(variant_dir / "initial_frame.png"),
            "mid_frame": str(variant_dir / "mid_frame.png"),
            "terminal_frame": str(variant_dir / "terminal_frame.png"),
            "top_collision_overlay": str(variant_dir / "top_collision_overlay.png"),
            "side_collision_overlay": str(variant_dir / "side_collision_overlay.png"),
        },
    }
    _write_json(variant_dir / "variant_summary.json", summary)
    _write_json(variant_dir / "physics_scene_settings.json", physics_settings)
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


def _variant_result_for_ranking(summary: dict[str, Any]) -> dict[str, Any]:
    detail = summary["classification_detail"]
    return {
        "variant_id": summary["variant"]["variant_id"],
        "classification": summary["classification"],
        "source_retention_fraction": detail["source_retention_fraction"],
        "particle_count_final_fraction": detail["particle_count_final_fraction"],
        "target_count": detail["target_count"],
        "spill_count": detail["spill_count"],
        "outside_source_count": detail["outside_source_count"],
        "below_table_count": detail["below_table_count"],
        "nan_count": detail["nan_count"],
        "tail_leak_rate_fraction_per_second": detail["tail_leak_rate_fraction_per_second"],
        "cpu_collision_fallback_detected": detail["cpu_collision_fallback_detected"],
        "gpu_collider_unsupported": detail["gpu_collider_unsupported"],
        "negative_control": bool(summary["variant"].get("negative_control")),
        "artifact_dir": summary["artifact_dir"],
        "scene_path": summary["scene_path"],
    }


def _run_matrix(
    *,
    config: ColliderConfig,
    artifact_dir: Path,
    scene_dir: Path,
    native_usd: Path,
    selected_variants: Sequence[str],
) -> dict[str, Any]:
    specs = variant_specs()
    summaries: list[dict[str, Any]] = []
    for variant_id in selected_variants:
        spec = specs[variant_id]
        scene_path = scene_dir / f"{variant_id.lower()}_{spec.name}.usda"
        try:
            summary = _run_variant(
                config=config,
                spec=spec,
                artifact_dir=artifact_dir,
                scene_path=scene_path,
                native_usd=native_usd,
            )
        except Exception as exc:
            fatal_error = {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback_tail": traceback.format_exc()[-6000:],
            }
            classification = classify_collider_hold(
                variant_id=variant_id,
                config=config,
                initial_count=0,
                final_count=0,
                source_count=0,
                target_count=0,
                spill_count=0,
                below_table_count=0,
                nan_count=0,
                tail_leak_rate_fraction_per_second=999.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                fatal_error=fatal_error,
            )
            variant_dir = artifact_dir / variant_id
            variant_dir.mkdir(parents=True, exist_ok=True)
            summary = {
                "schema_version": 1,
                "manifest_type": "true_physx_pbd_fluid_spike_s2_variant_summary",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "stage": "S2_BEAKER_COLLIDER_SMOKE",
                "variant": asdict(spec),
                "config": asdict(config),
                "classification_contract_version": CLASSIFICATION_CONTRACT_VERSION,
                "scene_path": str(scene_path),
                "artifact_dir": str(variant_dir),
                "runtime_step_executed": False,
                "readback_available": False,
                "initial_count": 0,
                "final_count": 0,
                "classification": classification["classification"],
                "classification_detail": classification,
                "diagnostic_projection_version": DIAGNOSTIC_PROJECTION_VERSION,
                "runtime_warning_evidence_mode": (
                    "variant-level flags are initialized during simulation; "
                    "artifact-level stdout/stderr warning scan is authoritative for release"
                ),
                "fatal_error": fatal_error,
            }
            _write_json(variant_dir / "variant_summary.json", summary)
        summaries.append(summary)
    ranking = rank_collider_variants([_variant_result_for_ranking(summary) for summary in summaries])
    return {
        "selected_variant_ids": list(selected_variants),
        "full_matrix_executed": tuple(selected_variants) == BEAKER_COLLIDER_VARIANT_IDS,
        "variant_summaries": summaries,
        "variant_results": [_variant_result_for_ranking(summary) for summary in summaries],
        "ranking": ranking,
    }


def _build_manifest(
    *,
    config: ColliderConfig,
    artifact_dir: Path,
    scene_dir: Path,
    native_usd: Path,
    matrix: dict[str, Any] | None,
    command: str,
    fatal_error: dict[str, Any] | None,
) -> dict[str, Any]:
    ranking = matrix["ranking"] if matrix else {
        "best_for_s3": [],
        "native_beaker_status": "NOT_RUN",
        "negative_control_status": "NOT_RUN",
        "s2_status": "STOP_WITH_EVIDENCE",
        "reason": "matrix_runtime_failed",
    }
    s2_status = ranking["s2_status"]
    selected_variant_ids = list(matrix["selected_variant_ids"]) if matrix else []
    full_matrix_executed = bool(matrix and matrix.get("full_matrix_executed"))
    allowed_claims = [
        "S2 tested the required beaker collider matrix in standalone IsaacSim41."
        if full_matrix_executed
        else "S2 tested a selected beaker collider subset in standalone IsaacSim41.",
        "At least one non-negative-control collider may proceed to S3 kinematic pour."
        if ranking["best_for_s3"]
        else "S2 produced stop evidence for beaker collider hold.",
    ]
    return {
        "schema_version": 1,
        "manifest_type": "true_physx_pbd_fluid_spike_evidence",
        "run_id": "fluid_spike_isaacsim41_ebench_s2_beaker_collider_matrix_20260707_001",
        "stage": "S2_BEAKER_COLLIDER_SMOKE",
        "classification_contract_version": CLASSIFICATION_CONTRACT_VERSION,
        "status": s2_status,
        "s2_status": s2_status,
        "reason": ranking["reason"],
        "live_evidence": True,
        "runtime_step_executed": bool(matrix),
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
        "config": asdict(config),
        "variant_ids": list(BEAKER_COLLIDER_VARIANT_IDS),
        "selected_variant_ids": selected_variant_ids,
        "full_matrix_executed": full_matrix_executed,
        "variant_specs": {variant_id: asdict(spec) for variant_id, spec in variant_specs().items()},
        "region_definitions": region_definitions(config),
        "native_usd": str(native_usd),
        "scene_dir": str(scene_dir),
        "artifact_dir": str(artifact_dir),
        "best_for_s3": ranking["best_for_s3"],
        "native_beaker_status": ranking["native_beaker_status"],
        "negative_control_status": ranking["negative_control_status"],
        "variant_results": matrix["variant_results"] if matrix else [],
        "variant_summary_files": {
            summary["variant"]["variant_id"]: str(Path(summary["artifact_dir"]) / "variant_summary.json")
            for summary in (matrix["variant_summaries"] if matrix else [])
        },
        "evidence_files": {
            "server_stdout": str(artifact_dir / "server.stdout.txt"),
            "server_stderr": str(artifact_dir / "server.stderr.txt"),
            "runtime_warning_scan": str(
                artifact_dir.parent / "fluid_spike_s2_runtime_warning_scan_20260707.json"
            ),
        },
        "pass_criteria": {
            "at_least_one_non_negative_control_variant_passed": bool(ranking["best_for_s3"]),
            "required_source_retention_fraction": 0.95,
            "required_particle_count_final_fraction": 0.95,
            "required_outside_source_count": 0,
            "required_target_count": 0,
            "required_spill_count": 0,
            "required_below_table_count": 0,
            "required_tail_leak_rate_fraction_per_second_lt": 0.02,
            "required_cpu_collision_fallback_detected": False,
            "required_nan_count": 0,
            "required_runtime_warning_scan_blocking": False,
        },
        "runtime_warning_evidence_mode": (
            "artifact-level stdout/stderr warning scan is authoritative for S3 release; "
            "variant-level runtime flags alone are not sufficient"
        ),
        "fluid_spike_claim_allowed": True,
        "true_fluid_claim_allowed": False,
        "expert_oracle_score_claim_allowed": False,
        "canonical_score_claim_allowed": False,
        "score_claim_allowed": False,
        "policy_score_claim_allowed": False,
        "official_leaderboard_claim_allowed": False,
        "visual_only_liquid_claim_allowed": False,
        "allowed_claims": allowed_claims,
        "blocked_claims": [
            "level1_pour has true fluid today",
            "S2 standalone collider hold equals robot pouring",
            "particles have stepped in EBench consumer",
            "fluid is EBench-scoreable",
            "Expert Oracle Score includes fluid",
            "policy score claim",
            "official leaderboard claim",
            "diagnostic overlays equal product-quality render",
        ],
        "next_stage": {
            "id": "S3_KINEMATIC_POUR_RIG" if ranking["best_for_s3"] else "S2_COLLIDER_FOLLOW_UP",
            "goal": "Run kinematic pour rig on best_for_s3 variants."
            if ranking["best_for_s3"]
            else "Use S2 failure matrix to narrow collider/cooking follow-up.",
            "variants": ranking["best_for_s3"],
        },
        "fatal_error": fatal_error,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--scene-dir", default=DEFAULT_SCENE_DIR)
    parser.add_argument("--manifest-path", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--native-usd", default=DEFAULT_NATIVE_USD)
    parser.add_argument("--particle-count", type=int, default=ColliderConfig.particle_count)
    parser.add_argument("--steps", type=int, default=ColliderConfig.steps)
    parser.add_argument("--width", type=int, default=ColliderConfig.render_width)
    parser.add_argument("--height", type=int, default=ColliderConfig.render_height)
    parser.add_argument(
        "--variants",
        default=",".join(BEAKER_COLLIDER_VARIANT_IDS),
        help="Comma-separated variant IDs. Default runs C0-C5.",
    )
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    selected_variants = tuple(value.strip() for value in args.variants.split(",") if value.strip())
    unknown = [value for value in selected_variants if value not in BEAKER_COLLIDER_VARIANT_IDS]
    if unknown:
        raise SystemExit(f"unknown variants: {unknown}")

    config = ColliderConfig(
        particle_count=args.particle_count,
        steps=args.steps,
        render_width=args.width,
        render_height=args.height,
    )
    artifact_dir = Path(args.artifact_dir).resolve()
    scene_dir = Path(args.scene_dir).resolve()
    manifest_path = Path(args.manifest_path).resolve()
    native_usd = Path(args.native_usd).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    scene_dir.mkdir(parents=True, exist_ok=True)
    command = " ".join([sys.executable, Path(__file__).as_posix(), *argv])

    app = None
    matrix: dict[str, Any] | None = None
    fatal_error: dict[str, Any] | None = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": bool(args.headless), "width": args.width, "height": args.height})
        matrix = _run_matrix(
            config=config,
            artifact_dir=artifact_dir,
            scene_dir=scene_dir,
            native_usd=native_usd,
            selected_variants=selected_variants,
        )
    except Exception as exc:
        fatal_error = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback_tail": traceback.format_exc()[-6000:],
        }
    manifest = _build_manifest(
        config=config,
        artifact_dir=artifact_dir,
        scene_dir=scene_dir,
        native_usd=native_usd,
        matrix=matrix,
        command=command,
        fatal_error=fatal_error,
    )
    _write_json(manifest_path, manifest)
    print(
        "S2 beaker collider matrix "
        f"status={manifest['status']} best_for_s3={manifest['best_for_s3']} "
        f"manifest={manifest_path}",
        flush=True,
    )
    if app is not None:
        app.close()
    return 0 if manifest["status"] == "GO_NEXT" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
