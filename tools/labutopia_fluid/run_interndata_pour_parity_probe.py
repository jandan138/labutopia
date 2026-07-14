#!/usr/bin/env python3
"""Run the fixed InternData-style fluid hold and deterministic pour probes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SOURCE_SCENE = (
    REPO_ROOT
    / "outputs/usd_asset_packages/lab_001_level1_pour_support_aligned_v1_20260712"
    / "lab_001_level1_pour_support_aligned_v1.usda"
)
DEFAULT_STATIC_OUTPUT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "interndata_source_hold_probe_20260714"
)
DEFAULT_KINEMATIC_OUTPUT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "interndata_kinematic_pour_probe_20260714"
)
DEFAULT_STATIC_MANIFEST = DEFAULT_STATIC_OUTPUT / "runtime_summary.json"

PUBLIC_SOURCE_COMMIT = "2a0a21f2c836df97c925729084e13d68950b4deb"
PUBLIC_GRID_DIMS = (12, 12, 25)
PUBLIC_PARTICLE_COUNT = math.prod(PUBLIC_GRID_DIMS)
PUBLIC_PARTICLE_CONTACT_OFFSET = 0.003
PUBLIC_PARTICLE_SPACING = 0.003
PUBLIC_POINT_WIDTH = 0.003
PUBLIC_PHYSICS_DT = 1.0 / 30.0
PHYSICS_SUBSTEPS_PER_FRAME = 4
INTEGRATION_DT = PUBLIC_PHYSICS_DT / PHYSICS_SUBSTEPS_PER_FRAME
INITIAL_GRID_VERTICAL_BIAS_M = -0.0005
PUBLIC_SETUP_STEPS = 1
PUBLIC_PRE_FLUID_STEPS = 20
PUBLIC_POST_FLUID_STEPS = 150
PUBLIC_TRANSFER_FLOOR = 150

PARTICLE_SCOPE_PATH = "/World/InternDataParityFluid"
PARTICLE_SYSTEM_PATH = f"{PARTICLE_SCOPE_PATH}/ParticleSystem"
PARTICLE_SET_PATH = f"{PARTICLE_SCOPE_PATH}/Particles"
VISUAL_PARTICLE_SET_PATH = f"{PARTICLE_SCOPE_PATH}/VisualParticles"
PBD_MATERIAL_PATH = f"{PARTICLE_SCOPE_PATH}/PbdMaterial"
VISUAL_MATERIAL_PATH = "/World/Looks/LiquidPresentationWater"
VISUAL_PARTICLE_MATERIAL_PATH = "/World/Looks/InternDataParticleWater"
COLLIDER_MATERIAL_PATH = "/World/PhysicsMaterials/InternDataCollider"
CAMERA_PATH = "/World/InternDataParityCamera"
CLOSEUP_CAMERA_PATH = "/World/InternDataParityCloseupCamera"
PHYSICS_SCENE_PATH = "/World/PhysicsScene"
TABLETOP_SPILL_BAND_M = 0.02
STRICT_CONTAINMENT_EPSILON_M = 0.00005
INNER_WALL_PANEL_COUNT = 72
INNER_WALL_PANEL_RING_COUNT = 2
INNER_WALL_THICKNESS_M = 0.026
INNER_WALL_BOTTOM_THICKNESS_M = 0.012
INNER_WALL_BOTTOM_OVERLAP_M = 0.018
INNER_WALL_CENTER_INSET_M = PUBLIC_POINT_WIDTH / 2.0

KINEMATIC_SEGMENT_STEPS = {
    "approach": 120,
    "tilt": 120,
    "hold": 120,
    "untilt": 120,
    "return": 60,
    "settle": 150,
}
KINEMATIC_TILT_DEGREES = 100.0
KINEMATIC_MOUTH_CLEARANCE_M = 0.005
KINEMATIC_MAX_POSITION_ERROR_M = 0.001
KINEMATIC_MAX_ROTATION_ERROR_DEGREES = 1.0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(_json_safe(value), sort_keys=True) + "\n")


def read_physics_particle_points(stage: Any, path: str) -> list[tuple[float, float, float]]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise ValueError(f"particle_points_prim_missing:{path}")
    simulation_attr = prim.GetAttribute("physxParticle:simulationPoints")
    values = simulation_attr.Get() if simulation_attr else None
    if values is None:
        if prim.IsA(UsdGeom.Points):
            values = UsdGeom.Points(prim).GetPointsAttr().Get()
        elif prim.IsA(UsdGeom.PointInstancer):
            values = UsdGeom.PointInstancer(prim).GetPositionsAttr().Get()
    if values is None:
        raise ValueError(f"particle_points_missing:{path}")
    return [tuple(float(value) for value in point) for point in values]


def author_initial_simulation_points(
    prim: Any, positions: Sequence[Sequence[float]]
) -> dict[str, Any]:
    from pxr import Gf, Sdf, Vt

    values = Vt.Vec3fArray([Gf.Vec3f(*position) for position in positions])
    simulation_points = prim.CreateAttribute(
        "physxParticle:simulationPoints",
        Sdf.ValueTypeNames.Point3fArray,
        custom=False,
    )
    authored = bool(simulation_points.Set(values))
    readback = simulation_points.Get()
    return {
        "authored": authored and readback is not None,
        "particle_count": len(readback) if readback is not None else 0,
    }


def author_replay_particle_positions(
    stage: Any,
    path: str,
    positions: Sequence[Sequence[float]],
) -> dict[str, Any]:
    from pxr import Gf, UsdGeom, Vt

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise ValueError(f"particle_points_prim_missing:{path}")
    simulation = author_initial_simulation_points(prim, positions)
    values = Vt.Vec3fArray([Gf.Vec3f(*position) for position in positions])
    if prim.IsA(UsdGeom.Points):
        display_authored = bool(UsdGeom.Points(prim).CreatePointsAttr().Set(values))
    elif prim.IsA(UsdGeom.PointInstancer):
        display_authored = bool(
            UsdGeom.PointInstancer(prim).CreatePositionsAttr().Set(values)
        )
        legacy_points = prim.GetAttribute("points")
        if legacy_points:
            display_authored = bool(legacy_points.Set(values)) and display_authored
    else:
        raise ValueError(f"particle_display_schema_unsupported:{prim.GetTypeName()}")
    return {
        "particle_count": int(simulation["particle_count"]),
        "display_and_simulation_points_match": bool(
            simulation["authored"] and display_authored
        ),
    }


def build_public_fluid_recipe() -> dict[str, Any]:
    isosurface = build_isosurface_contract(
        particle_contact_offset=PUBLIC_PARTICLE_CONTACT_OFFSET,
        particle_count=PUBLIC_PARTICLE_COUNT,
    )
    return {
        "evidence_label": "public_fluid_recipe",
        "source_repository": "InternRobotics/InternDataEngine",
        "source_commit": PUBLIC_SOURCE_COMMIT,
        "grid_dims": list(PUBLIC_GRID_DIMS),
        "particle_count": PUBLIC_PARTICLE_COUNT,
        "particle_contact_offset": PUBLIC_PARTICLE_CONTACT_OFFSET,
        "particle_spacing": PUBLIC_PARTICLE_SPACING,
        "point_width": PUBLIC_POINT_WIDTH,
        "physics_dt": PUBLIC_PHYSICS_DT,
        "physics_substeps_per_frame": PHYSICS_SUBSTEPS_PER_FRAME,
        "integration_dt": INTEGRATION_DT,
        "setup_steps": PUBLIC_SETUP_STEPS,
        "pre_fluid_steps": PUBLIC_PRE_FLUID_STEPS,
        "post_fluid_steps": PUBLIC_POST_FLUID_STEPS,
        "enable_ccd": True,
        "solver_position_iterations": 16,
        "max_neighborhood": 96,
        "neighborhood_scale": 1.01,
        "max_velocity": 0.8,
        "global_self_collision_enabled": True,
        "simulation_owner": PHYSICS_SCENE_PATH,
        "isosurface": isosurface,
        "smoothing": {"enabled": True, "strength": 50.0},
        "runtime_smoothing_strength": 50.0,
        "anisotropy": {
            "enabled": True,
            "scale": 5.0,
            "minimum": 1.0,
            "maximum": 2.0,
        },
        "pbd_material": {
            "cohesion": 0.01,
            "drag": 0.0,
            "lift": 0.0,
            "damping": 0.0,
            "friction": 0.1,
            "surface_tension": 0.0074,
            "viscosity": 0.0000017,
            "vorticity_confinement": 0.0,
        },
        "visual_material": {
            "diffuse_color": [1.0, 1.0, 1.0],
            "emissive_color": [0.0, 0.0, 0.0],
            "metallic": 0.0,
            "roughness": 0.4,
            "opacity": 0.05,
        },
        "runtime_visual_material_path": VISUAL_MATERIAL_PATH,
        "runtime_visual_strategy": "offline_physx_readback_points_replay",
        "delivery_visual_strategy": "physical_particle_prim",
    }


def build_isosurface_contract(
    *,
    particle_contact_offset: float,
    particle_count: int,
) -> dict[str, Any]:
    del particle_count
    reference_fluid_rest_offset = float(particle_contact_offset) * 0.5
    return {
        "enabled": True,
        "reference_fluid_rest_offset": reference_fluid_rest_offset,
        "grid_spacing": reference_fluid_rest_offset * 0.9,
        "surface_distance": reference_fluid_rest_offset * 0.95,
        "grid_filtering_passes": "GS",
        "grid_smoothing_radius": reference_fluid_rest_offset,
        "num_mesh_smoothing_passes": 4,
        "num_mesh_normal_smoothing_passes": 4,
        "max_vertices": 1024 * 1024,
        "max_triangles": 2 * 1024 * 1024,
        "max_subgrids": 4 * 1024,
        "parameter_reference": "isaacsim41_cup_demo",
        "affects_particle_physics": False,
    }


def build_visual_particle_proxy_contract(*, physical_width: float) -> dict[str, Any]:
    display_to_physical_ratio = 1.0
    return {
        "path": VISUAL_PARTICLE_SET_PATH,
        "material_path": VISUAL_PARTICLE_MATERIAL_PATH,
        "physical_width": float(physical_width),
        "display_width": float(physical_width) * display_to_physical_ratio,
        "display_to_physical_ratio": display_to_physical_ratio,
        "position_source": "strict_physx_readback",
        "physics_coupled": False,
        "reference": "local_liquid_usd_points_style",
    }


def _author_visual_particle_material(stage: Any, material_path: str) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    if not stage.GetPrimAtPath("/World/Looks"):
        UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, material_path)
    shader = UsdShade.Shader.Define(stage, f"{material_path}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(0.46, 0.82, 0.96)
    )
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(0.01, 0.025, 0.035)
    )
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.06)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.06)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.333)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return {
        "path": material_path,
        "shader_path": str(shader.GetPath()),
        "backend": "USD_PREVIEW_SMALL_PARTICLE_WATER",
        "reference_material": "OmniGlass.mdl:OmniGlass",
        "adaptation_reason": "avoid_multi_layer_refraction_blackening_in_small_beaker",
        "diffuse_color": [0.46, 0.82, 0.96],
        "opacity": 0.06,
        "roughness": 0.06,
        "ior": 1.333,
    }


def author_visual_particle_proxy(
    stage: Any,
    positions: Sequence[Sequence[float]],
    *,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    from pxr import Gf, UsdGeom, UsdShade, Vt

    material_info = _author_visual_particle_material(
        stage,
        str(contract["material_path"]),
    )
    points = UsdGeom.Points.Define(stage, str(contract["path"]))
    values = Vt.Vec3fArray([Gf.Vec3f(*position) for position in positions])
    widths = Vt.FloatArray([float(contract["display_width"])] * len(values))
    points.CreatePointsAttr().Set(values)
    points.CreateWidthsAttr().Set(widths)
    points.CreatePurposeAttr().Set(UsdGeom.Tokens.render)
    points.CreateDisplayColorPrimvar(UsdGeom.Tokens.constant).Set(
        Vt.Vec3fArray([Gf.Vec3f(0.73344165, 0.9498069, 0.94228774)])
    )
    points.CreateDisplayOpacityPrimvar(UsdGeom.Tokens.constant).Set(
        Vt.FloatArray([0.06])
    )
    material = UsdShade.Material(stage.GetPrimAtPath(str(contract["material_path"])))
    UsdShade.MaterialBindingAPI.Apply(points.GetPrim()).Bind(material)
    return {
        **dict(contract),
        "particle_count": len(values),
        "material": material_info,
        "purpose": str(points.GetPurposeAttr().Get()),
        "physics_schemas": [
            schema
            for schema in points.GetPrim().GetAppliedSchemas()
            if "Physx" in schema or "Physics" in schema
        ],
    }


def normalize_delivery_particle_prim_to_points(stage: Any) -> dict[str, Any]:
    from pxr import Gf, UsdGeom, Vt

    prim = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    if not prim or not prim.IsValid():
        raise ValueError(f"delivery_particle_prim_missing:{PARTICLE_SET_PATH}")
    if not (prim.IsA(UsdGeom.Points) or prim.IsA(UsdGeom.PointInstancer)):
        raise ValueError(f"delivery_particle_schema_unsupported:{prim.GetTypeName()}")

    positions = read_physics_particle_points(stage, PARTICLE_SET_PATH)
    normalized_from_point_instancer = prim.IsA(UsdGeom.PointInstancer)
    removed_prototypes: list[str] = []
    if normalized_from_point_instancer:
        instancer = UsdGeom.PointInstancer(prim)
        prototype_paths = list(instancer.GetPrototypesRel().GetTargets())
        points = UsdGeom.Points.Define(stage, PARTICLE_SET_PATH)
        prim = points.GetPrim()
        for name in (
            "positions",
            "protoIndices",
            "orientations",
            "orientationsf",
            "scales",
            "angularVelocities",
            "invisibleIds",
        ):
            prim.RemoveProperty(name)
        prim.RemoveProperty("prototypes")
        for path in prototype_paths:
            if str(path).startswith(PARTICLE_SET_PATH + "/") and stage.RemovePrim(path):
                removed_prototypes.append(str(path))
    else:
        points = UsdGeom.Points(prim)

    values = Vt.Vec3fArray([Gf.Vec3f(*position) for position in positions])
    widths = Vt.FloatArray([PUBLIC_POINT_WIDTH] * len(values))
    points.CreatePointsAttr().Set(values)
    points.CreateWidthsAttr().Set(widths)
    points.SetWidthsInterpolation(UsdGeom.Tokens.vertex)
    return {
        "normalized_from_point_instancer": normalized_from_point_instancer,
        "particle_count": len(values),
        "removed_prototype_paths": removed_prototypes,
        "delivery_prim_type": points.GetPrim().GetTypeName(),
    }


def configure_delivery_particle_visual_authority(stage: Any) -> dict[str, Any]:
    from pxr import Sdf, UsdGeom, UsdShade

    stage.SetEditTarget(stage.GetRootLayer())
    normalization = normalize_delivery_particle_prim_to_points(stage)
    physical = stage.GetPrimAtPath(PARTICLE_SET_PATH)

    material_prim = stage.GetPrimAtPath(VISUAL_PARTICLE_MATERIAL_PATH)
    if not material_prim or not material_prim.IsA(UsdShade.Material):
        _author_visual_particle_material(stage, VISUAL_PARTICLE_MATERIAL_PATH)
        material_prim = stage.GetPrimAtPath(VISUAL_PARTICLE_MATERIAL_PATH)
    material = UsdShade.Material(material_prim)
    UsdShade.MaterialBindingAPI.Apply(physical).Bind(material)
    UsdGeom.Imageable(physical).CreatePurposeAttr().Set(UsdGeom.Tokens.render)
    UsdGeom.Imageable(physical).CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)

    if physical.IsA(UsdGeom.PointInstancer):
        instancer = UsdGeom.PointInstancer(physical)
        for prototype_path in instancer.GetPrototypesRel().GetTargets():
            prototype = stage.GetPrimAtPath(prototype_path)
            if prototype and prototype.IsValid():
                UsdShade.MaterialBindingAPI.Apply(prototype).Bind(material)

    proxy = stage.GetPrimAtPath(VISUAL_PARTICLE_SET_PATH)
    proxy_removed = not proxy or not proxy.IsValid() or bool(
        stage.RemovePrim(VISUAL_PARTICLE_SET_PATH)
    )
    system = stage.GetPrimAtPath(PARTICLE_SYSTEM_PATH)
    isosurface = system.GetAttribute(
        "physxParticleIsosurface:isosurfaceEnabled"
    ) if system else None
    isosurface_disabled = bool(isosurface and isosurface.Set(False))

    scope = stage.GetPrimAtPath(PARTICLE_SCOPE_PATH)
    authority_attr = scope.GetAttribute("labutopia:deliveryVisualAuthority")
    if not authority_attr:
        authority_attr = scope.CreateAttribute(
            "labutopia:deliveryVisualAuthority",
            Sdf.ValueTypeNames.String,
            custom=True,
        )
    authority_attr.Set("physical_particle_prim")
    delivery_metadata = {
        "labutopia:deliverySnapshotOnly": (Sdf.ValueTypeNames.Bool, True),
        "labutopia:containsPrescribedPourAnimation": (
            Sdf.ValueTypeNames.Bool,
            False,
        ),
        "labutopia:externalControllerRequired": (Sdf.ValueTypeNames.Bool, True),
        "labutopia:sourceActorPath": (
            Sdf.ValueTypeNames.String,
            "/World/beaker2",
        ),
    }
    for name, (type_name, value) in delivery_metadata.items():
        attribute = scope.GetAttribute(name)
        if not attribute:
            attribute = scope.CreateAttribute(name, type_name, custom=True)
        attribute.Set(value)
    world = stage.GetPrimAtPath("/World")
    if world and world.IsValid():
        stage.SetDefaultPrim(world)
    return {
        **normalization,
        "authority": "physical_particle_prim",
        "physical_prim_path": PARTICLE_SET_PATH,
        "physical_prim_type": physical.GetTypeName(),
        "material_path": VISUAL_PARTICLE_MATERIAL_PATH,
        "offline_proxy_removed": proxy_removed,
        "isosurface_disabled": isosurface_disabled,
        "live_position_attribute": "points",
    }


def remove_dangling_material_bindings(stage: Any) -> dict[str, Any]:
    removed = []
    for prim in stage.Traverse():
        for relationship in prim.GetRelationships():
            if not relationship.GetName().startswith("material:binding"):
                continue
            targets = list(relationship.GetTargets())
            valid_targets = [
                target
                for target in targets
                if stage.GetPrimAtPath(target).IsValid()
            ]
            missing_targets = [
                str(target) for target in targets if target not in valid_targets
            ]
            if not missing_targets:
                continue
            relationship.SetTargets(valid_targets)
            removed.append(
                {
                    "prim_path": str(prim.GetPath()),
                    "relationship": relationship.GetName(),
                    "missing_targets": missing_targets,
                }
            )
    return {
        "removed_count": len(removed),
        "removed": removed,
    }


def export_delivery_snapshot(source_path: Path, destination_path: Path) -> dict[str, Any]:
    from pxr import Sdf, Usd

    source = Path(source_path).resolve(strict=True)
    destination = Path(destination_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    layer = Sdf.Layer.FindOrOpen(str(source))
    if layer is None or not layer.Export(str(destination)):
        raise RuntimeError(f"delivery_layer_export_failed:{source}:{destination}")
    stage = Usd.Stage.Open(str(destination), Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError(f"delivery_stage_open_failed:{destination}")
    visual_authority = configure_delivery_particle_visual_authority(stage)
    dangling = remove_dangling_material_bindings(stage)
    stage.GetRootLayer().Save()
    return {
        "path": str(destination),
        "sha256": _sha256_file(destination),
        "visual_authority": visual_authority,
        "dangling_material_bindings_removed": dangling["removed_count"],
        "dangling_material_binding_details": dangling["removed"],
        "snapshot_only": True,
        "contains_prescribed_pour_animation": False,
    }


def export_particle_state_layer(
    source_stage: Any,
    destination_path: Path,
    positions: Sequence[Sequence[float]],
) -> dict[str, Any]:
    from pxr import Usd

    destination = Path(destination_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_before = _json_sha256(
        read_physics_particle_points(source_stage, PARTICLE_SET_PATH)
    )
    if not source_stage.GetRootLayer().Export(str(destination)):
        raise RuntimeError(f"particle_state_layer_export_failed:{destination}")
    snapshot = Usd.Stage.Open(str(destination), Usd.Stage.LoadAll)
    if snapshot is None:
        raise RuntimeError(f"particle_state_stage_open_failed:{destination}")
    authored = author_replay_particle_positions(
        snapshot,
        PARTICLE_SET_PATH,
        positions,
    )
    snapshot.GetRootLayer().Save()
    source_after = _json_sha256(
        read_physics_particle_points(source_stage, PARTICLE_SET_PATH)
    )
    return {
        **authored,
        "path": str(destination),
        "sha256": _sha256_file(destination),
        "position_sha256": _json_sha256(positions),
        "source_stage_unchanged": source_before == source_after,
    }


def build_static_sampling_plan() -> list[dict[str, Any]]:
    return [
        {
            "state_index": state_index,
            "advance_physics_before_read": state_index > 0,
            "readback_source": (
                "authored_usd_points" if state_index == 0 else "physx"
            ),
        }
        for state_index in range(PUBLIC_POST_FLUID_STEPS + 1)
    ]


def select_capture_records(
    mode: str,
    records: Sequence[Mapping[str, Any]],
    *,
    frame_stride: int,
) -> list[Mapping[str, Any]]:
    if not records:
        raise ValueError("capture_records_empty")
    if frame_stride <= 0:
        raise ValueError("frame_stride_must_be_positive")
    if mode == "static":
        return [records[-1]]
    if mode != "kinematic":
        raise ValueError(f"unknown_mode:{mode}")
    return [
        record
        for record in records
        if int(record["step_index"]) % frame_stride == 0
        or record is records[-1]
    ]


def build_inferred_collider_contract() -> dict[str, Any]:
    return {
        "evidence_label": "inferred_collider_hypothesis",
        "approximation": "convexDecomposition",
        "max_convex_hulls": 64,
        "hull_vertex_limit": 64,
        "min_thickness": 0.001,
        "shrink_wrap": True,
        "error_percentage": 0.1,
        "static_friction": 1.0,
        "dynamic_friction": 1.0,
        "overlay_existing_prim": True,
        "second_collider_allowed": False,
    }


def _grid_values(count: int, spacing: float) -> list[float]:
    lower = -0.5 * (count - 1) * spacing
    return [lower + index * spacing for index in range(count)]


def build_centered_public_grid(frame: Any) -> dict[str, Any]:
    recipe = build_public_fluid_recipe()
    nx, ny, nz = PUBLIC_GRID_DIMS
    xs = _grid_values(nx, PUBLIC_PARTICLE_SPACING)
    ys = _grid_values(ny, PUBLIC_PARTICLE_SPACING)
    z_mid = (
        0.5 * (float(frame.interior_floor) + float(frame.rim_height))
        + INITIAL_GRID_VERTICAL_BIAS_M
    )
    zs = [z_mid + value for value in _grid_values(nz, PUBLIC_PARTICLE_SPACING)]
    canonical = [(x, y, z) for x in xs for y in ys for z in zs]
    world = [tuple(float(value) for value in frame.canonical_to_world(point)) for point in canonical]

    max_center_radius = max(math.hypot(point[0], point[1]) for point in canonical)
    min_z = min(point[2] for point in canonical)
    max_z = max(point[2] for point in canonical)
    contact_clearance = float(recipe["particle_contact_offset"])
    radial_margin = float(frame.interior_radius) - (max_center_radius + contact_clearance)
    floor_margin = min_z - contact_clearance - float(frame.interior_floor)
    rim_margin = float(frame.rim_height) - (max_z + contact_clearance)
    fit = {
        "max_center_radius_m": max_center_radius,
        "contact_clearance_m": contact_clearance,
        "radial_margin_m": radial_margin,
        "floor_margin_m": floor_margin,
        "rim_margin_m": rim_margin,
        "fits": radial_margin > 0.0 and floor_margin > 0.0 and rim_margin > 0.0,
    }
    if not fit["fits"]:
        raise ValueError(f"public_grid_contact_envelope_does_not_fit:{fit}")
    center_span = [
        (nx - 1) * PUBLIC_PARTICLE_SPACING,
        (ny - 1) * PUBLIC_PARTICLE_SPACING,
        (nz - 1) * PUBLIC_PARTICLE_SPACING,
    ]
    positions_payload = [[float(value) for value in point] for point in world]
    return {
        "grid_dims": list(PUBLIC_GRID_DIMS),
        "particle_count": len(world),
        "vertical_bias_m": INITIAL_GRID_VERTICAL_BIAS_M,
        "positions_canonical": canonical,
        "positions_world": world,
        "center_span_m": center_span,
        "point_width_envelope_m": [value + PUBLIC_POINT_WIDTH for value in center_span],
        "contact_clearance_envelope_m": [
            value + 2.0 * contact_clearance for value in center_span
        ],
        "fit": fit,
        "positions_sha256": _json_sha256(positions_payload),
    }


def _enabled_collision_paths(stage: Any, parent_path: str) -> list[str]:
    result = []
    parent = stage.GetPrimAtPath(parent_path)
    if not parent or not parent.IsValid():
        return result
    for prim in [parent, *list(stage.Traverse())]:
        path = str(prim.GetPath())
        if path != parent_path and not path.startswith(parent_path + "/"):
            continue
        attr = prim.GetAttribute("physics:collisionEnabled")
        if attr and attr.Get() is True:
            result.append(path)
    return sorted(set(result))


def _set_bool_attribute(prim: Any, name: str, value: bool) -> None:
    from pxr import Sdf

    attribute = prim.GetAttribute(name)
    if not attribute:
        attribute = prim.CreateAttribute(name, Sdf.ValueTypeNames.Bool, custom=False)
    attribute.Set(bool(value))


def author_inferred_collider_overlay(
    stage: Any,
    *,
    mesh_path: str,
    material_path: str = COLLIDER_MATERIAL_PATH,
) -> dict[str, Any]:
    from pxr import Sdf, UsdGeom, UsdPhysics, UsdShade

    try:
        from pxr import PhysxSchema
    except ImportError:
        PhysxSchema = None

    contract = build_inferred_collider_contract()
    prim = stage.GetPrimAtPath(mesh_path)
    if not prim or not prim.IsValid():
        raise ValueError(f"collider_mesh_missing:{mesh_path}")
    collision = UsdPhysics.CollisionAPI.Apply(prim)
    collision.CreateCollisionEnabledAttr().Set(True)
    mesh_collision = UsdPhysics.MeshCollisionAPI.Apply(prim)
    mesh_collision.CreateApproximationAttr().Set(contract["approximation"])
    if PhysxSchema is not None:
        PhysxSchema.PhysxCollisionAPI.Apply(prim)

    attribute_values = (
        (
            "physxConvexDecompositionCollision:maxConvexHulls",
            Sdf.ValueTypeNames.UInt,
            contract["max_convex_hulls"],
        ),
        (
            "physxConvexDecompositionCollision:hullVertexLimit",
            Sdf.ValueTypeNames.UInt,
            contract["hull_vertex_limit"],
        ),
        (
            "physxConvexDecompositionCollision:minThickness",
            Sdf.ValueTypeNames.Float,
            contract["min_thickness"],
        ),
        (
            "physxConvexDecompositionCollision:shrinkWrap",
            Sdf.ValueTypeNames.Bool,
            contract["shrink_wrap"],
        ),
        (
            "physxConvexDecompositionCollision:errorPercentage",
            Sdf.ValueTypeNames.Float,
            contract["error_percentage"],
        ),
    )
    for name, type_name, value in attribute_values:
        attr = prim.GetAttribute(name)
        if not attr:
            attr = prim.CreateAttribute(name, type_name, custom=False)
        attr.Set(value)

    material_parent = str(Path(material_path).parent)
    if material_parent != "/" and not stage.GetPrimAtPath(material_parent):
        UsdGeom.Scope.Define(stage, material_parent)
    material = UsdShade.Material.Define(stage, material_path)
    material_api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    material_api.CreateStaticFrictionAttr().Set(contract["static_friction"])
    material_api.CreateDynamicFrictionAttr().Set(contract["dynamic_friction"])
    physics_binding = prim.CreateRelationship("material:binding:physics", custom=False)
    physics_binding.SetTargets([material.GetPath()])

    parent_path = str(Path(mesh_path).parent)
    enabled_paths = _enabled_collision_paths(stage, parent_path)
    if enabled_paths != [mesh_path]:
        raise ValueError(f"collider_route_not_unique:{enabled_paths}")
    return {
        "mesh_path": mesh_path,
        "material_path": material_path,
        "contract": contract,
        "enabled_collision_prim_paths": enabled_paths,
        "authored_attributes": {name: value for name, _, value in attribute_values},
        "physics_material_binding_targets": [str(path) for path in physics_binding.GetTargets()],
    }


def build_inner_wall_contract() -> dict[str, Any]:
    return {
        "evidence_label": "explicit_open_inner_wall_proxy",
        "shape": "gpu_native_boxes",
        "panel_count": INNER_WALL_PANEL_COUNT,
        "panel_ring_count": INNER_WALL_PANEL_RING_COUNT,
        "wall_thickness": INNER_WALL_THICKNESS_M,
        "bottom_thickness": INNER_WALL_BOTTOM_THICKNESS_M,
        "bottom_overlap": INNER_WALL_BOTTOM_OVERLAP_M,
        "center_inset": INNER_WALL_CENTER_INSET_M,
        "contact_offset": 0.004,
        "rest_offset": 0.0,
        "open_top": True,
        "visual_world_geometry_preserved": True,
    }


def bake_uniform_mesh_scale(stage: Any, *, mesh_path: str) -> dict[str, Any]:
    from pxr import Gf, UsdGeom, Vt

    prim = stage.GetPrimAtPath(mesh_path)
    if not prim or not prim.IsA(UsdGeom.Mesh):
        raise ValueError(f"mesh_scale_bake_target_invalid:{mesh_path}")
    mesh = UsdGeom.Mesh(prim)
    scale_ops = [
        op
        for op in UsdGeom.Xformable(prim).GetOrderedXformOps()
        if op.GetOpType() == UsdGeom.XformOp.TypeScale
    ]
    if len(scale_ops) != 1:
        raise ValueError(f"mesh_scale_bake_requires_one_scale_op:{mesh_path}")
    scale_value = scale_ops[0].Get()
    components = [float(scale_value[index]) for index in range(3)]
    if min(components) <= 0.0 or not all(
        math.isclose(value, components[0], rel_tol=0.0, abs_tol=1e-9)
        for value in components[1:]
    ):
        raise ValueError(f"mesh_scale_bake_requires_positive_uniform_scale:{components}")
    uniform_scale = components[0]
    points = mesh.GetPointsAttr().Get()
    if not points:
        raise ValueError(f"mesh_scale_bake_points_missing:{mesh_path}")
    before_matrix = UsdGeom.XformCache().GetLocalToWorldTransform(prim)
    before_world = [
        tuple(float(value) for value in before_matrix.Transform(Gf.Vec3d(*point)))
        for point in points
    ]
    scaled_points = Vt.Vec3fArray(
        [Gf.Vec3f(*(float(value) * uniform_scale for value in point)) for point in points]
    )
    mesh.GetPointsAttr().Set(scaled_points)
    extent = mesh.GetExtentAttr().Get()
    if extent:
        mesh.GetExtentAttr().Set(
            Vt.Vec3fArray(
                [
                    Gf.Vec3f(*(float(value) * uniform_scale for value in point))
                    for point in extent
                ]
            )
        )
    scale_ops[0].Set(Gf.Vec3f(1.0, 1.0, 1.0))
    after_matrix = UsdGeom.XformCache().GetLocalToWorldTransform(prim)
    after_world = [
        tuple(float(value) for value in after_matrix.Transform(Gf.Vec3d(*point)))
        for point in scaled_points
    ]
    maximum_error = max(
        math.dist(before, after) for before, after in zip(before_world, after_world)
    )
    if maximum_error > 1e-6:
        raise ValueError(f"mesh_scale_bake_changed_world_geometry:{maximum_error}")
    return {
        "mesh_path": mesh_path,
        "scale_baked": not math.isclose(uniform_scale, 1.0),
        "uniform_scale": uniform_scale,
        "point_count": len(points),
        "maximum_world_point_error_m": maximum_error,
        "before_world_points_sha256": _json_sha256(before_world),
        "after_world_points_sha256": _json_sha256(after_world),
    }


def author_inner_wall_collision_proxy(
    stage: Any,
    *,
    frame: Any,
    parent_path: str,
    visual_mesh_path: str,
    material_path: str = COLLIDER_MATERIAL_PATH,
    kinematic_actor: bool = False,
) -> dict[str, Any]:
    from pxr import UsdGeom, UsdPhysics, UsdShade
    from tools.labutopia_fluid.real_beaker import author_canonical_fluid_wrapper

    contract = build_inner_wall_contract()
    proxy_radius = float(frame.interior_radius) - float(contract["center_inset"])
    if proxy_radius <= 0.0:
        raise ValueError("inner_wall_center_inset_exhausts_interior_radius")
    proxy_frame = replace(frame, interior_radius=proxy_radius)
    authored = author_canonical_fluid_wrapper(
        stage,
        frame=proxy_frame,
        parent_path=parent_path,
        visual_mesh_path=visual_mesh_path,
        panel_count=contract["panel_count"],
        panel_ring_count=contract["panel_ring_count"],
        wall_thickness=contract["wall_thickness"],
        bottom_thickness=contract["bottom_thickness"],
        bottom_overlap=contract["bottom_overlap"],
    )

    mesh_prim = stage.GetPrimAtPath(visual_mesh_path)
    actor_path = None
    actor_paths: list[str] = []
    actor_initial_matrices: list[list[list[float]]] = []
    actor_strategy = "static_canonical_compound_shapes"
    visual_actor_path = visual_mesh_path
    if kinematic_actor:
        if mesh_prim.HasAPI(UsdPhysics.RigidBodyAPI):
            mesh_prim.RemoveAPI(UsdPhysics.RigidBodyAPI)
        parent_prim = stage.GetPrimAtPath(parent_path)
        parent_rigid = UsdPhysics.RigidBodyAPI.Apply(parent_prim)
        parent_rigid.CreateRigidBodyEnabledAttr().Set(True)
        parent_rigid.CreateKinematicEnabledAttr().Set(True)
        actor_path = parent_path
        actor_paths = [parent_path]
        actor_world = UsdGeom.XformCache().GetLocalToWorldTransform(parent_prim)
        actor_initial_matrices = [
            [
                [float(actor_world[row][column]) for column in range(4)]
                for row in range(4)
            ]
        ]
        actor_strategy = "parent_compound_kinematic_actor"
        visual_actor_path = parent_path
    elif mesh_prim.HasAPI(UsdPhysics.RigidBodyAPI):
        mesh_rigid = UsdPhysics.RigidBodyAPI(mesh_prim)
        mesh_rigid.CreateRigidBodyEnabledAttr().Set(True)
        mesh_rigid.CreateKinematicEnabledAttr().Set(True)

    collider_paths = list(authored["collider_paths"])

    material_parent = str(Path(material_path).parent)
    if material_parent != "/" and not stage.GetPrimAtPath(material_parent):
        UsdGeom.Scope.Define(stage, material_parent)
    material = UsdShade.Material.Define(stage, material_path)
    material_api = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    material_api.CreateStaticFrictionAttr().Set(1.0)
    material_api.CreateDynamicFrictionAttr().Set(1.0)
    for path in collider_paths:
        collider = stage.GetPrimAtPath(path)
        relation = collider.CreateRelationship("material:binding:physics", custom=False)
        relation.SetTargets([material.GetPath()])

    enabled_paths = _enabled_collision_paths(stage, parent_path)
    expected_paths = sorted(collider_paths)
    if enabled_paths != expected_paths:
        raise ValueError(
            f"inner_wall_collider_routes_mismatch:{enabled_paths}:{expected_paths}"
        )
    return {
        **authored,
        **contract,
        "visual_interior_radius": float(frame.interior_radius),
        "collider_count": len(expected_paths),
        "collider_paths": expected_paths,
        "enabled_collision_prim_paths": enabled_paths,
        "material_path": material_path,
        "actor_path": actor_path,
        "actor_paths": actor_paths,
        "actor_root_path": None,
        "actor_initial_matrices": actor_initial_matrices,
        "actor_strategy": actor_strategy,
        "kinematic_actor_enabled": bool(kinematic_actor),
        "visual_actor_path": visual_actor_path,
        "visual_mesh_path": visual_mesh_path,
    }


def _ensure_scope(stage: Any, path: str) -> None:
    from pxr import UsdGeom

    if not stage.GetPrimAtPath(path):
        UsdGeom.Scope.Define(stage, path)


def _define_visual_material(stage: Any, path: str) -> Any:
    from pxr import Gf, Sdf, UsdShade

    values = build_public_fluid_recipe()["visual_material"]
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*values["diffuse_color"])
    )
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*values["emissive_color"])
    )
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(values["metallic"])
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(values["roughness"])
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(values["opacity"])
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def author_public_material_binding_sequence(
    stage: Any,
    *,
    prim: Any,
    pbd_material_path: str = PBD_MATERIAL_PATH,
    visual_material_path: str = VISUAL_MATERIAL_PATH,
) -> dict[str, Any]:
    from pxr import UsdGeom, UsdShade

    for parent in {str(Path(pbd_material_path).parent), str(Path(visual_material_path).parent)}:
        if parent != "/" and not stage.GetPrimAtPath(parent):
            UsdGeom.Scope.Define(stage, parent)
    pbd_material = UsdShade.Material.Define(stage, pbd_material_path)
    visual_prim = stage.GetPrimAtPath(visual_material_path)
    if visual_prim and visual_prim.IsA(UsdShade.Material):
        visual_material = UsdShade.Material(visual_prim)
        visual_source = "existing_stage_material"
    else:
        visual_material = _define_visual_material(stage, visual_material_path)
        visual_source = "fallback_preview_surface"
    binding = UsdShade.MaterialBindingAPI.Apply(prim)
    binding.Bind(pbd_material, materialPurpose="physics")
    binding.Bind(visual_material)
    relationship = prim.GetRelationship("material:binding")
    targets = [str(path) for path in relationship.GetTargets()] if relationship else []
    physics_relationship = prim.GetRelationship("material:binding:physics")
    physics_targets = (
        [str(path) for path in physics_relationship.GetTargets()]
        if physics_relationship
        else []
    )
    return {
        "binding_order": [pbd_material_path, visual_material_path],
        "effective_default_binding_targets": targets,
        "effective_physics_binding_targets": physics_targets,
        "pbd_effective_physics_binding": physics_targets == [pbd_material_path],
        "visual_material_source": visual_source,
    }


def _point_inside_frame(point: Sequence[float], frame: Any, epsilon: float) -> bool:
    canonical = frame.world_to_canonical(point)
    return (
        math.hypot(canonical[0], canonical[1]) <= float(frame.interior_radius) + epsilon
        and canonical[2] >= float(frame.interior_floor) - epsilon
        and canonical[2] < float(frame.rim_height) - epsilon
    )


def classify_two_beaker_positions(
    positions_world: Iterable[Sequence[float]],
    *,
    source_frame: Any,
    target_frame: Any,
    table_z: float,
    epsilon: float = STRICT_CONTAINMENT_EPSILON_M,
    tabletop_spill_band_m: float = TABLETOP_SPILL_BAND_M,
) -> dict[str, Any]:
    counts = {
        "source": 0,
        "target": 0,
        "below_table": 0,
        "tabletop_spill": 0,
        "transit": 0,
        "nonfinite": 0,
    }
    total = 0
    for point in positions_world:
        total += 1
        values = tuple(float(value) for value in point)
        if len(values) != 3 or not all(math.isfinite(value) for value in values):
            counts["nonfinite"] += 1
        elif _point_inside_frame(values, source_frame, epsilon):
            counts["source"] += 1
        elif _point_inside_frame(values, target_frame, epsilon):
            counts["target"] += 1
        elif values[2] < float(table_z) - epsilon:
            counts["below_table"] += 1
        elif values[2] <= float(table_z) + float(tabletop_spill_band_m):
            counts["tabletop_spill"] += 1
        else:
            counts["transit"] += 1
    finite_partition = sum(counts[key] for key in counts if key != "nonfinite")
    partition_complete = finite_partition + counts["nonfinite"] == total
    return {
        **counts,
        "particle_count": total,
        "finite_partition_total": finite_partition,
        "partition_complete": partition_complete,
        "valid": counts["nonfinite"] == 0 and partition_complete,
        "epsilon_m": epsilon,
        "tabletop_spill_band_m": tabletop_spill_band_m,
        "assignment_priority": [
            "nonfinite",
            "source",
            "target",
            "below_table",
            "tabletop_spill",
            "transit",
        ],
    }


def classify_source_hold_positions(
    positions_world: Iterable[Sequence[float]],
    frame: Any,
) -> dict[str, Any]:
    from tools.labutopia_fluid.real_beaker import classify_visible_beaker_positions

    tolerant_frame = replace(
        frame,
        interior_radius=float(frame.interior_radius)
        + STRICT_CONTAINMENT_EPSILON_M,
        interior_floor=float(frame.interior_floor)
        - STRICT_CONTAINMENT_EPSILON_M,
        rim_height=float(frame.rim_height) + STRICT_CONTAINMENT_EPSILON_M,
    )
    return {
        **classify_visible_beaker_positions(positions_world, tolerant_frame),
        "classification_epsilon_m": STRICT_CONTAINMENT_EPSILON_M,
    }


def classify_static_hold_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    first_failing_step = None
    expected_steps = list(range(PUBLIC_POST_FLUID_STEPS + 1))
    actual_steps = [int(record.get("step_index", -1)) for record in records]
    if actual_steps != expected_steps:
        reasons.append("state_indices_not_0_through_150")
    runtime_position_hashes = {
        str(record.get("position_sha256"))
        for record in records
        if int(record.get("step_index", -1)) > 0
        and record.get("position_sha256")
    }
    if len(runtime_position_hashes) < 2:
        reasons.append("particle_dynamics_not_observed")
    for record in records:
        step = int(record.get("step_index", -1))
        strict = record.get("strict_counts") or {}
        ok = (
            int(record.get("particle_count", -1)) == PUBLIC_PARTICLE_COUNT
            and int(strict.get("inside_visible_interior_count", -1)) == PUBLIC_PARTICLE_COUNT
            and int(strict.get("strict_violating_point_count", -1)) == 0
            and int(strict.get("nonfinite_count", -1)) == 0
        )
        if not ok:
            if first_failing_step is None:
                first_failing_step = step
            reasons.append(f"strict_containment_failed_at_{step}")
    return {
        "physics_pass": not reasons,
        "first_failing_step": first_failing_step,
        "failure_reasons": reasons,
        "state_count": len(records),
        "expected_state_count": PUBLIC_POST_FLUID_STEPS + 1,
        "runtime_unique_position_hash_count": len(runtime_position_hashes),
        "strict_zero_leak_required": True,
    }


def _smoothstep(value: float) -> float:
    value = min(max(float(value), 0.0), 1.0)
    return value * value * (3.0 - 2.0 * value)


def build_fixed_kinematic_schedule() -> dict[str, Any]:
    states: list[dict[str, Any]] = [
        {
            "step_index": 0,
            "phase": "initial",
            "translation_progress": 0.0,
            "tilt_degrees": 0.0,
        }
    ]

    def append_phase(name: str, count: int, state_fn: Any) -> None:
        for index in range(1, count + 1):
            progress = _smoothstep(index / count)
            state = state_fn(progress)
            states.append(
                {
                    "step_index": len(states),
                    "phase": name,
                    "translation_progress": float(state[0]),
                    "tilt_degrees": float(state[1]),
                }
            )

    append_phase("approach", KINEMATIC_SEGMENT_STEPS["approach"], lambda p: (p, 0.0))
    append_phase(
        "tilt",
        KINEMATIC_SEGMENT_STEPS["tilt"],
        lambda p: (1.0, KINEMATIC_TILT_DEGREES * p),
    )
    append_phase(
        "hold",
        KINEMATIC_SEGMENT_STEPS["hold"],
        lambda _p: (1.0, KINEMATIC_TILT_DEGREES),
    )
    append_phase(
        "untilt",
        KINEMATIC_SEGMENT_STEPS["untilt"],
        lambda p: (1.0, KINEMATIC_TILT_DEGREES * (1.0 - p)),
    )
    append_phase("return", KINEMATIC_SEGMENT_STEPS["return"], lambda p: (1.0 - p, 0.0))
    append_phase("settle", KINEMATIC_SEGMENT_STEPS["settle"], lambda _p: (0.0, 0.0))
    payload = {
        "segment_steps": dict(KINEMATIC_SEGMENT_STEPS),
        "physics_steps": sum(KINEMATIC_SEGMENT_STEPS.values()),
        "tilt_degrees": KINEMATIC_TILT_DEGREES,
        "states": states,
    }
    payload["trace_sha256"] = _json_sha256(states)
    return payload


def classify_kinematic_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    schedule = build_fixed_kinematic_schedule()
    expected_steps = list(range(schedule["physics_steps"] + 1))
    actual_steps = [int(record.get("step_index", -1)) for record in records]
    if actual_steps != expected_steps:
        reasons.append("kinematic_state_indices_mismatch")
    for record in records:
        step = int(record.get("step_index", -1))
        counts = record.get("counts") or {}
        pose_error = record.get("kinematic_pose_error") or {}
        if not bool(pose_error.get("within_tolerance", False)):
            reasons.append(f"kinematic_pose_readback_failed_at_{step}")
        finite_total = sum(int(counts.get(key, 0)) for key in ("source", "target", "below_table", "tabletop_spill", "transit"))
        if int(counts.get("nonfinite", 0)) != 0:
            reasons.append(f"nonfinite_at_{step}")
        if int(counts.get("below_table", 0)) != 0:
            reasons.append(f"below_table_at_{step}")
        if int(counts.get("tabletop_spill", 0)) != 0:
            reasons.append(f"tabletop_spill_at_{step}")
        if finite_total != PUBLIC_PARTICLE_COUNT or not bool(counts.get("partition_complete", False)):
            reasons.append(f"partition_failed_at_{step}")
    if records:
        final = records[-1].get("counts") or {}
        if int(final.get("transit", -1)) != 0:
            reasons.append("final_transit_nonzero")
        if int(final.get("target", 0)) < PUBLIC_TRANSFER_FLOOR:
            reasons.append("target_transfer_below_150")
        if int(final.get("source", 0)) + int(final.get("target", 0)) != PUBLIC_PARTICLE_COUNT:
            reasons.append("final_source_target_total_mismatch")
    else:
        reasons.append("no_kinematic_records")
    count_keys = (
        "source",
        "target",
        "below_table",
        "tabletop_spill",
        "transit",
        "nonfinite",
    )
    final_counts = {
        key: int((records[-1].get("counts") or {}).get(key, 0))
        for key in count_keys
    } if records else {}
    return {
        "physics_pass": not reasons,
        "failure_reasons": sorted(set(reasons)),
        "state_count": len(records),
        "expected_state_count": schedule["physics_steps"] + 1,
        "target_transfer_floor": PUBLIC_TRANSFER_FLOOR,
        "max_position_error_m": KINEMATIC_MAX_POSITION_ERROR_M,
        "max_rotation_error_degrees": KINEMATIC_MAX_ROTATION_ERROR_DEGREES,
        "final_counts": final_counts,
        "transit_particle_state_count": sum(
            int((record.get("counts") or {}).get("transit", 0))
            for record in records
        ),
        "maximum_transit_count": max(
            (
                int((record.get("counts") or {}).get("transit", 0))
                for record in records
            ),
            default=0,
        ),
        "intermediate_transit_semantics": "airborne_pour_stream_allowed",
    }


def classify_runtime_validity(
    *,
    step_summary: Mapping[str, Any],
    stage_contract: Mapping[str, Any],
    collider_log: Mapping[str, Any],
    record_count: int,
    required_video_valid: bool,
) -> dict[str, Any]:
    physics_reasons = []
    if not bool(step_summary.get("exact_step_count_verified")):
        physics_reasons.append("exact_step_count_not_verified")
    if not bool(step_summary.get("ordered_lifecycle_verified")):
        physics_reasons.append("ordered_lifecycle_not_verified")
    if not bool(stage_contract.get("valid")):
        physics_reasons.append("stage_contract_invalid")
    if bool(collider_log.get("failure_detected")):
        physics_reasons.append("collider_cooking_failure")
    if int(record_count) <= 0:
        physics_reasons.append("no_physics_records")
    visual_reasons = [] if required_video_valid else ["required_video_capture_missing"]
    physics_valid = not physics_reasons
    return {
        "technical_valid": physics_valid,
        "physics_evidence_valid": physics_valid,
        "physics_evidence_failure_reasons": physics_reasons,
        "visual_capture_valid": bool(required_video_valid),
        "visual_capture_failure_reasons": visual_reasons,
    }


def combine_strict_phase_summaries(
    phases: Mapping[str, Mapping[str, Any]],
    *,
    requested_logical_steps: int,
) -> dict[str, Any]:
    phase_values = list(phases.values())
    executed_logical = sum(
        int(phase.get("executed_logical_steps", 0)) for phase in phase_values
    )
    requested_integration = sum(
        int(phase.get("requested_integration_steps", 0)) for phase in phase_values
    )
    executed_integration = sum(
        int(phase.get("executed_integration_steps", 0)) for phase in phase_values
    )
    exact_logical = (
        executed_logical == int(requested_logical_steps)
        and all(bool(phase.get("exact_step_count_verified")) for phase in phase_values)
    )
    exact_integration = requested_integration == executed_integration and all(
        bool(phase.get("exact_step_count_verified")) for phase in phase_values
    )
    return {
        "requested_logical_steps": int(requested_logical_steps),
        "executed_logical_steps": executed_logical,
        "requested_integration_steps": requested_integration,
        "executed_integration_steps": executed_integration,
        "logical_dt": PUBLIC_PHYSICS_DT,
        "integration_dt": INTEGRATION_DT,
        "substeps_per_logical_step": PHYSICS_SUBSTEPS_PER_FRAME,
        "simulated_seconds": sum(
            float(phase.get("simulated_seconds", 0.0)) for phase in phase_values
        ),
        "exact_logical_step_count_verified": exact_logical,
        "exact_integration_step_count_verified": exact_integration,
        "exact_step_count_verified": exact_logical and exact_integration,
        "simulate_fetch_pair_count": sum(
            int(phase.get("simulate_fetch_pair_count", 0)) for phase in phase_values
        ),
        "ordered_lifecycle_verified": all(
            bool(phase.get("ordered_lifecycle_verified")) for phase in phase_values
        ),
        "attach_verified": all(
            bool(phase.get("attach_verified")) for phase in phase_values
        ),
        "detach_verified": all(
            bool(phase.get("detach_verified")) for phase in phase_values
        ),
        "render_updates_advance_physics": any(
            bool(phase.get("render_updates_advance_physics"))
            for phase in phase_values
        ),
        "render_invariance_checks": sum(
            int(phase.get("render_invariance_checks", 0)) for phase in phase_values
        ),
        "phases": dict(phases),
    }


def combine_terminal_verdict(
    *,
    mode: str,
    technical_valid: bool,
    physics_pass: bool,
    visual_pass: bool,
) -> str:
    if mode == "static":
        if not technical_valid:
            return "INVALID_STATIC_SOURCE_HOLD"
        if not physics_pass:
            return "STATIC_PHYSICS_FAIL"
        if not visual_pass:
            return "STATIC_VISUAL_FAIL"
        return "STATIC_ELIGIBLE_FOR_KINEMATIC"
    if mode == "kinematic":
        if not technical_valid:
            return "INVALID_KINEMATIC_POUR"
        if not physics_pass or not visual_pass:
            return "KINEMATIC_POUR_FAIL"
        return "KINEMATIC_POUR_PASS"
    raise ValueError(f"unknown_mode:{mode}")


def _consolidate_parent_transform(stage: Any, parent_path: str) -> dict[str, Any]:
    from pxr import Gf, UsdGeom, UsdPhysics

    parent_prim = stage.GetPrimAtPath(parent_path)
    mesh_prim = stage.GetPrimAtPath(f"{parent_path}/mesh")
    if not parent_prim or not mesh_prim:
        raise ValueError(f"beaker_prim_missing:{parent_path}")
    matrix = UsdGeom.XformCache().GetLocalToWorldTransform(parent_prim)
    xform = UsdGeom.Xformable(parent_prim)
    xform.ClearXformOpOrder()
    transform_op = xform.AddTransformOp(UsdGeom.XformOp.PrecisionDouble)
    transform_op.Set(Gf.Matrix4d(matrix))
    rigid = UsdPhysics.RigidBodyAPI.Apply(mesh_prim)
    rigid.CreateRigidBodyEnabledAttr().Set(True)
    rigid.CreateKinematicEnabledAttr().Set(True)
    return {
        "parent_path": parent_path,
        "mesh_path": f"{parent_path}/mesh",
        "transform_op_name": transform_op.GetOpName(),
        "initial_matrix": [[float(matrix[row][column]) for column in range(4)] for row in range(4)],
        "kinematic_enabled": True,
    }


def _consolidate_parent_actor_transform(stage: Any, parent_path: str) -> dict[str, Any]:
    from pxr import Gf, UsdGeom, UsdPhysics

    parent_prim = stage.GetPrimAtPath(parent_path)
    mesh_prim = stage.GetPrimAtPath(f"{parent_path}/mesh")
    if not parent_prim or not mesh_prim:
        raise ValueError(f"beaker_prim_missing:{parent_path}")
    matrix = UsdGeom.XformCache().GetLocalToWorldTransform(parent_prim)
    xform = UsdGeom.Xformable(parent_prim)
    xform.ClearXformOpOrder()
    transform_op = xform.AddTransformOp(UsdGeom.XformOp.PrecisionDouble)
    transform_op.Set(Gf.Matrix4d(matrix))
    parent_rigid = UsdPhysics.RigidBodyAPI.Apply(parent_prim)
    parent_rigid.CreateRigidBodyEnabledAttr().Set(True)
    parent_rigid.CreateKinematicEnabledAttr().Set(True)
    if mesh_prim.HasAPI(UsdPhysics.RigidBodyAPI):
        mesh_prim.RemoveAPI(UsdPhysics.RigidBodyAPI)
    _set_bool_attribute(mesh_prim, "physics:rigidBodyEnabled", False)
    _set_bool_attribute(mesh_prim, "physics:kinematicEnabled", False)
    return {
        "parent_path": parent_path,
        "actor_path": parent_path,
        "mesh_path": f"{parent_path}/mesh",
        "transform_op_name": transform_op.GetOpName(),
        "initial_matrix": [
            [float(matrix[row][column]) for column in range(4)] for row in range(4)
        ],
        "kinematic_enabled": True,
        "compound_child_colliders": True,
    }


def _prepare_overlay(
    *,
    source_scene: Path,
    overlay_path: Path,
    mode: str,
    collider_mode: str,
) -> dict[str, Any]:
    from pxr import Sdf, Usd, UsdGeom, UsdPhysics
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    source = source_scene.resolve(strict=True)
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    if overlay_path.exists():
        overlay_path.unlink()
    layer = Sdf.Layer.CreateNew(str(overlay_path))
    if layer is None:
        raise RuntimeError("overlay_layer_create_failed")
    layer.subLayerPaths = [str(source)]
    if not layer.Save():
        raise RuntimeError("overlay_layer_initial_save_failed")
    stage = Usd.Stage.Open(str(overlay_path), Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError("overlay_stage_open_failed")
    stage.SetEditTarget(stage.GetRootLayer())
    beaker_paths = ["/World/beaker2"]
    if mode == "kinematic" or collider_mode == "inner-wall":
        beaker_paths.append("/World/beaker1")
    collider_results = []
    transform_results = []
    for parent_path in beaker_paths:
        mesh_path = f"{parent_path}/mesh"
        is_source_actor = mode == "kinematic" and parent_path == "/World/beaker2"
        if collider_mode == "native":
            collider_results.append(
                author_inferred_collider_overlay(
                    stage,
                    mesh_path=mesh_path,
                    material_path=COLLIDER_MATERIAL_PATH,
                )
            )
            transform_results.append(_consolidate_parent_transform(stage, parent_path))
        elif collider_mode == "inner-wall":
            frame = derive_cup_interior_frame(
                stage,
                parent_path=parent_path,
                visual_mesh_path=mesh_path,
                calibration_points_path=(
                    "/World/ParticleSet" if parent_path == "/World/beaker2" else None
                ),
            )
            collider_results.append(
                author_inner_wall_collision_proxy(
                    stage,
                    frame=frame,
                    parent_path=parent_path,
                    visual_mesh_path=mesh_path,
                    material_path=COLLIDER_MATERIAL_PATH,
                    kinematic_actor=is_source_actor,
                )
            )
            transform_results.append(
                _consolidate_parent_actor_transform(stage, parent_path)
                if is_source_actor
                else _consolidate_parent_transform(stage, parent_path)
            )
        else:
            raise ValueError(f"unknown_collider_mode:{collider_mode}")

    if mode == "static":
        target_mesh = stage.GetPrimAtPath("/World/beaker1/mesh")
        if target_mesh and target_mesh.IsValid():
            rigid = UsdPhysics.RigidBodyAPI.Apply(target_mesh)
            rigid.CreateRigidBodyEnabledAttr().Set(True)
            rigid.CreateKinematicEnabledAttr().Set(True)
    for path in ("/World/ParticleSet", "/World/ParticleSystem", "/World/fluid"):
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsValid():
            prim.SetActive(False)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    stage.GetRootLayer().Save()
    return {
        "source_scene": str(source),
        "source_sha256": _sha256_file(source),
        "overlay_path": str(overlay_path),
        "overlay_sha256": _sha256_file(overlay_path),
        "colliders": collider_results,
        "transforms": transform_results,
        "mode": mode,
        "collider_mode": collider_mode,
    }


def runtime_kinematic_rigid_paths(*, mode: str, collider_mode: str) -> tuple[str, ...]:
    if mode == "kinematic" and collider_mode == "inner-wall":
        return ("/World/beaker2",)
    return ("/World/beaker1/mesh", "/World/beaker2/mesh")


def _read_matrix(payload: Sequence[Sequence[float]]) -> Any:
    from pxr import Gf

    return Gf.Matrix4d(
        *[float(payload[row][column]) for row in range(4) for column in range(4)]
    )


def matrix_to_physx_pose(matrix: Any) -> list[float]:
    from pxr import Gf

    translation = matrix.ExtractTranslation()
    quaternion = Gf.Transform(matrix).GetRotation().GetQuat()
    imaginary = quaternion.GetImaginary()
    return [
        float(translation[0]),
        float(translation[1]),
        float(translation[2]),
        float(imaginary[0]),
        float(imaginary[1]),
        float(imaginary[2]),
        float(quaternion.GetReal()),
    ]


def physx_pose_to_matrix(pose: Sequence[float]) -> Any:
    from pxr import Gf

    if len(pose) != 7:
        raise ValueError("physx_pose_requires_xyz_xyzw")
    matrix = Gf.Matrix4d(1.0)
    quaternion = Gf.Quatd(
        float(pose[6]),
        Gf.Vec3d(float(pose[3]), float(pose[4]), float(pose[5])),
    )
    matrix.SetRotate(Gf.Rotation(quaternion))
    matrix.SetTranslateOnly(Gf.Vec3d(*[float(value) for value in pose[:3]]))
    return matrix


def kinematic_pose_error(
    target_pose: Sequence[float],
    actual_pose: Sequence[float],
) -> dict[str, Any]:
    if len(target_pose) != 7 or len(actual_pose) != 7:
        raise ValueError("kinematic_pose_error_requires_xyz_xyzw")
    target = [float(value) for value in target_pose]
    actual = [float(value) for value in actual_pose]
    position_error = math.dist(target[:3], actual[:3])
    target_quaternion = target[3:]
    actual_quaternion = actual[3:]
    target_norm = math.sqrt(sum(value * value for value in target_quaternion))
    actual_norm = math.sqrt(sum(value * value for value in actual_quaternion))
    if target_norm == 0.0 or actual_norm == 0.0:
        rotation_error = math.inf
    else:
        dot = abs(
            sum(
                left * right
                for left, right in zip(target_quaternion, actual_quaternion)
            )
            / (target_norm * actual_norm)
        )
        rotation_error = math.degrees(2.0 * math.acos(min(1.0, max(-1.0, dot))))
    return {
        "position_m": position_error,
        "rotation_degrees": rotation_error,
        "position_tolerance_m": KINEMATIC_MAX_POSITION_ERROR_M,
        "rotation_tolerance_degrees": KINEMATIC_MAX_ROTATION_ERROR_DEGREES,
        "within_tolerance": (
            position_error <= KINEMATIC_MAX_POSITION_ERROR_M
            and rotation_error <= KINEMATIC_MAX_ROTATION_ERROR_DEGREES
        ),
    }


def replay_kinematic_actor_pose(
    *,
    view: Any,
    pose_xyzw: Sequence[float],
    indices: Any,
    np_module: Any,
) -> dict[str, Any]:
    target_pose = [float(value) for value in pose_xyzw]
    view.set_transforms(
        np_module.asarray([target_pose], dtype=np_module.float32),
        indices,
    )
    actual_pose = (
        np_module.asarray(view.get_transforms(), dtype=np_module.float64)
        .reshape((-1, 7))[0]
        .tolist()
    )
    error = kinematic_pose_error(target_pose, actual_pose)
    if not error["within_tolerance"]:
        raise RuntimeError(f"kinematic_capture_replay_pose_mismatch:{error}")
    return {
        "target_pose_xyzw": target_pose,
        "actual_pose_xyzw": actual_pose,
        "pose_error": error,
        "driver": "omni.physics.tensors.RigidBodyView.set_transforms",
    }


def _frame_at_parent_matrix(frame: Any, initial_parent: Any, current_parent: Any) -> Any:
    from pxr import Gf

    inverse_initial = initial_parent.GetInverse()

    def transform_point(point: Sequence[float]) -> tuple[float, float, float]:
        local = inverse_initial.Transform(Gf.Vec3d(*point))
        return tuple(float(value) for value in current_parent.Transform(local))

    def transform_direction(direction: Sequence[float]) -> tuple[float, float, float]:
        local = inverse_initial.TransformDir(Gf.Vec3d(*direction))
        world = current_parent.TransformDir(local)
        length = math.sqrt(sum(float(value) ** 2 for value in world))
        return tuple(float(value) / length for value in world)

    return replace(
        frame,
        origin_world=transform_point(frame.origin_world),
        x_axis_world=transform_direction(frame.x_axis_world),
        y_axis_world=transform_direction(frame.y_axis_world),
        z_axis_world=transform_direction(frame.z_axis_world),
    )


def _kinematic_approach_floor(source_frame: Any, target_frame: Any) -> tuple[float, float, float]:
    from pxr import Gf

    tilt_radians = math.radians(KINEMATIC_TILT_DEGREES)
    horizontal_offset = float(source_frame.rim_height) * math.sin(tilt_radians)
    opening_vertical = math.cos(tilt_radians)
    rim_vertical_extent = float(source_frame.outer_radius) * math.sin(tilt_radians)
    floor_height = (
        float(target_frame.rim_height)
        + KINEMATIC_MOUTH_CLEARANCE_M
        - float(source_frame.rim_height) * opening_vertical
        + rim_vertical_extent
    )
    floor = (
        Gf.Vec3d(*target_frame.origin_world)
        + Gf.Vec3d(*source_frame.x_axis_world) * horizontal_offset
        + Gf.Vec3d(*target_frame.z_axis_world) * floor_height
    )
    return tuple(float(value) for value in floor)


def _kinematic_parent_matrix(
    *,
    state: Mapping[str, Any],
    initial_parent: Any,
    source_frame: Any,
    target_frame: Any,
) -> Any:
    from pxr import Gf

    initial_rotation = Gf.Transform(initial_parent).GetRotation()
    source_floor = Gf.Vec3d(*source_frame.origin_world)
    approach_floor = Gf.Vec3d(*_kinematic_approach_floor(source_frame, target_frame))
    progress = float(state["translation_progress"])
    desired_floor = source_floor * (1.0 - progress) + approach_floor * progress
    tilt = Gf.Rotation(Gf.Vec3d(*source_frame.y_axis_world), -float(state["tilt_degrees"]))
    rotation = initial_rotation * tilt
    result = Gf.Matrix4d(1.0)
    result.SetRotate(rotation)
    local_floor = initial_parent.GetInverse().Transform(source_floor)
    rotated_floor = result.Transform(local_floor)
    translation = desired_floor - rotated_floor
    result.SetTranslateOnly(translation)
    return result


def _author_public_fluid(stage: Any, positions: Sequence[Sequence[float]]) -> dict[str, Any]:
    from omni.physx.scripts import particleUtils
    from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdShade, Vt
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
        _author_liquid_presentation_water_material,
    )

    recipe = build_public_fluid_recipe()
    stage.SetEditTarget(stage.GetRootLayer())
    if not stage.GetPrimAtPath(PARTICLE_SCOPE_PATH):
        UsdGeom.Xform.Define(stage, PARTICLE_SCOPE_PATH)
    system_path = Sdf.Path(PARTICLE_SYSTEM_PATH)
    system = particleUtils.add_physx_particle_system(
        stage=stage,
        particle_system_path=system_path,
        particle_system_enabled=True,
        simulation_owner=Sdf.Path(recipe["simulation_owner"]),
        particle_contact_offset=recipe["particle_contact_offset"],
        enable_ccd=recipe["enable_ccd"],
        solver_position_iterations=recipe["solver_position_iterations"],
        max_neighborhood=recipe["max_neighborhood"],
        neighborhood_scale=recipe["neighborhood_scale"],
        max_velocity=recipe["max_velocity"],
        global_self_collision_enabled=recipe["global_self_collision_enabled"],
        non_particle_collision_enabled=True,
    )
    isosurface = recipe["isosurface"]
    particleUtils.add_physx_particle_isosurface(
        stage,
        system_path,
        enabled=isosurface["enabled"],
        max_vertices=isosurface["max_vertices"],
        max_triangles=isosurface["max_triangles"],
        max_subgrids=isosurface["max_subgrids"],
        grid_spacing=isosurface["grid_spacing"],
        surface_distance=isosurface["surface_distance"],
        grid_filtering_passes=isosurface["grid_filtering_passes"],
        grid_smoothing_radius=isosurface["grid_smoothing_radius"],
        num_mesh_smoothing_passes=isosurface["num_mesh_smoothing_passes"],
        num_mesh_normal_smoothing_passes=isosurface[
            "num_mesh_normal_smoothing_passes"
        ],
    )
    smoothing = PhysxSchema.PhysxParticleSmoothingAPI.Apply(system.GetPrim())
    smoothing.CreateParticleSmoothingEnabledAttr().Set(True)
    smoothing.CreateStrengthAttr().Set(recipe["runtime_smoothing_strength"])
    anisotropy_values = recipe["anisotropy"]
    anisotropy = PhysxSchema.PhysxParticleAnisotropyAPI.Apply(system.GetPrim())
    anisotropy.CreateParticleAnisotropyEnabledAttr().Set(
        anisotropy_values["enabled"]
    )
    anisotropy.CreateScaleAttr().Set(anisotropy_values["scale"])
    anisotropy.CreateMinAttr().Set(anisotropy_values["minimum"])
    anisotropy.CreateMaxAttr().Set(anisotropy_values["maximum"])

    points = Vt.Vec3fArray([Gf.Vec3f(*point) for point in positions])
    velocities = Vt.Vec3fArray([Gf.Vec3f(0.0, 0.0, 0.0)] * len(points))
    widths = Vt.FloatArray([recipe["point_width"]] * len(points))
    particle_set = particleUtils.add_physx_particleset_points(
        stage=stage,
        path=Sdf.Path(PARTICLE_SET_PATH),
        positions_list=points,
        velocities_list=velocities,
        widths_list=widths,
        particle_system_path=system_path,
        self_collision=True,
        fluid=True,
        particle_group=0,
        particle_mass=0.0,
        density=0.0,
    )
    stage.SetInterpolationType(Usd.InterpolationTypeLinear)
    UsdGeom.Imageable(particle_set.GetPrim()).CreatePurposeAttr().Set(UsdGeom.Tokens.proxy)

    pbd = recipe["pbd_material"]
    particleUtils.add_pbd_particle_material(
        stage=stage,
        path=Sdf.Path(PBD_MATERIAL_PATH),
        cohesion=pbd["cohesion"],
        drag=pbd["drag"],
        lift=pbd["lift"],
        damping=pbd["damping"],
        friction=pbd["friction"],
        surface_tension=pbd["surface_tension"],
        viscosity=pbd["viscosity"],
        vorticity_confinement=pbd["vorticity_confinement"],
    )
    visual_material = _author_liquid_presentation_water_material(
        stage,
        attempt_mdl=False,
        prefer_kit_bind=False,
    )
    material_binding = author_public_material_binding_sequence(
        stage,
        prim=system.GetPrim(),
        pbd_material_path=PBD_MATERIAL_PATH,
        visual_material_path=VISUAL_MATERIAL_PATH,
    )
    visual_particle_proxy = author_visual_particle_proxy(
        stage,
        positions,
        contract=build_visual_particle_proxy_contract(
            physical_width=recipe["point_width"]
        ),
    )
    system_attrs = {}
    for name in (
        "physxParticleSystem:particleContactOffset",
        "physxParticleSystem:enableCCD",
        "physxParticleSystem:solverPositionIterationCount",
        "physxParticleSystem:maxNeighborhood",
        "physxParticleSystem:neighborhoodScale",
        "physxParticleSystem:maxVelocity",
        "physxParticleSystem:globalSelfCollisionEnabled",
        "physxParticleIsosurface:isosurfaceEnabled",
        "physxParticleIsosurface:gridSpacing",
        "physxParticleIsosurface:surfaceDistance",
        "physxParticleIsosurface:gridFilteringPasses",
        "physxParticleIsosurface:gridSmoothingRadius",
        "physxParticleIsosurface:numMeshSmoothingPasses",
        "physxParticleIsosurface:numMeshNormalSmoothingPasses",
        "physxParticleIsosurface:maxVertices",
        "physxParticleIsosurface:maxTriangles",
        "physxParticleIsosurface:maxSubgrids",
        "physxParticleSmoothing:particleSmoothingEnabled",
        "physxParticleSmoothing:strength",
        "physxParticleAnisotropy:particleAnisotropyEnabled",
        "physxParticleAnisotropy:scale",
        "physxParticleAnisotropy:min",
        "physxParticleAnisotropy:max",
    ):
        attr = system.GetPrim().GetAttribute(name)
        system_attrs[name] = attr.Get() if attr else None
    return {
        "particle_system_path": PARTICLE_SYSTEM_PATH,
        "particle_set_path": PARTICLE_SET_PATH,
        "particle_count": len(points),
        "initial_authored_points_count": len(points),
        "recipe": recipe,
        "material_binding": material_binding,
        "visual_material": visual_material,
        "visual_particle_proxy": visual_particle_proxy,
        "system_attribute_readback": system_attrs,
        "point_width": float(widths[0]),
        "purpose": str(UsdGeom.Imageable(particle_set.GetPrim()).GetPurposeAttr().Get()),
    }


def _camera_specs(source_frame: Any, target_frame: Any) -> dict[str, dict[str, list[float]]]:
    sx, sy, _ = source_frame.origin_world
    tx, ty, _ = target_frame.origin_world
    table_z = min(source_frame.origin_world[2], target_frame.origin_world[2])
    midpoint = ((sx + tx) / 2.0, (sy + ty) / 2.0, table_z + 0.08)
    return {
        "context": {
            "path": CAMERA_PATH,
            "eye": [midpoint[0] + 0.52, midpoint[1] - 0.62, table_z + 0.42],
            "target": list(midpoint),
            "up": [0.0, 0.0, 1.0],
        },
        "closeup": {
            "path": CLOSEUP_CAMERA_PATH,
            "eye": [tx + 0.28, ty - 0.34, table_z + 0.24],
            "target": [tx, ty, table_z + 0.11],
            "up": [0.0, 0.0, 1.0],
        },
    }


def _define_camera(stage: Any, spec: Mapping[str, Any]) -> None:
    from pxr import Gf, UsdGeom

    camera = UsdGeom.Camera.Define(stage, spec["path"])
    transform = Gf.Matrix4d(1).SetLookAt(
        Gf.Vec3d(*spec["eye"]),
        Gf.Vec3d(*spec["target"]),
        Gf.Vec3d(*spec["up"]),
    ).GetInverse()
    xformable = UsdGeom.Xformable(camera.GetPrim())
    xformable.ClearXformOpOrder()
    xformable.AddTransformOp().Set(transform)
    camera.CreateFocalLengthAttr(22.0)
    camera.CreateHorizontalApertureAttr(24.0)
    camera.CreateVerticalApertureAttr(16.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))


def _validate_stage_contract(stage: Any, physics_settings: Mapping[str, Any]) -> dict[str, Any]:
    from pxr import UsdGeom

    meters = float(UsdGeom.GetStageMetersPerUnit(stage))
    up = str(UsdGeom.GetStageUpAxis(stage)).upper()
    valid = (
        math.isclose(meters, 1.0)
        and up == "Z"
        and math.isclose(float(physics_settings["effective_physics_dt"]), INTEGRATION_DT)
        and physics_settings["gravity_direction"] == [0.0, 0.0, -1.0]
        and math.isclose(float(physics_settings["gravity_magnitude"]), 9.81)
    )
    return {
        "meters_per_unit": meters,
        "up_axis": up,
        "physics_dt": physics_settings["effective_physics_dt"],
        "gravity_direction": physics_settings["gravity_direction"],
        "gravity_magnitude": physics_settings["gravity_magnitude"],
        "valid": valid,
    }


def _scoped_log_has_collider_failure(log_text: str) -> dict[str, Any]:
    lowered = log_text.lower()
    needles = (
        "convex decomposition failed",
        "failed to cook",
        "gpu collision fallback",
        "unsupported gpu collision",
    )
    matches = [needle for needle in needles if needle in lowered]
    return {"failure_detected": bool(matches), "matches": matches}


def _resolve_output(args: argparse.Namespace) -> Path:
    if args.out_dir:
        return Path(args.out_dir).resolve()
    return (DEFAULT_STATIC_OUTPUT if args.mode == "static" else DEFAULT_KINEMATIC_OUTPUT).resolve()


def normalize_rgb_frame(
    data: Any,
    *,
    expected_width: int,
    expected_height: int,
) -> Any:
    import numpy as np

    array = np.asarray(data)
    if (
        array.ndim != 3
        or array.shape[0] != expected_height
        or array.shape[1] != expected_width
        or array.shape[2] < 3
    ):
        raise ValueError(f"rgb_capture_shape_mismatch:{list(array.shape)}")
    if array.dtype == np.uint8:
        converted = array
    else:
        converted = np.nan_to_num(
            array.astype(np.float32), nan=0.0, posinf=255.0, neginf=0.0
        )
        if converted.size and float(converted.max()) <= 1.0:
            converted *= 255.0
        converted = np.clip(converted, 0.0, 255.0).astype(np.uint8)
    return converted[:, :, :3]


def _create_replicator_capture_resources(
    rep: Any,
    *,
    camera_specs: Mapping[str, Mapping[str, Any]],
    width: int,
    height: int,
) -> dict[str, dict[str, Any]]:
    resources = {}
    for name, spec in camera_specs.items():
        render_product = rep.create.render_product(spec["path"], (width, height))
        annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        annotator.attach(render_product)
        resources[name] = {
            "render_product": render_product,
            "annotator": annotator,
        }
    return resources


def _destroy_replicator_capture_resources(
    resources: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    detached = []
    destroyed = []
    failures = {}
    annotator_groups: dict[int, dict[str, Any]] = {}
    for name, resource in resources.items():
        group = annotator_groups.setdefault(
            id(resource["annotator"]),
            {"annotator": resource["annotator"], "names": []},
        )
        group["names"].append(name)
    for group in annotator_groups.values():
        try:
            group["annotator"].detach()
            detached.extend(group["names"])
        except Exception as exc:
            for name in group["names"]:
                failures[f"{name}:detach"] = repr(exc)
    for name, resource in resources.items():
        try:
            resource["render_product"].destroy()
            destroyed.append(name)
        except Exception as exc:
            failures[f"{name}:destroy"] = repr(exc)
    return {
        "detached": sorted(detached),
        "destroyed": sorted(destroyed),
        "failures": failures,
        "complete": not failures,
    }


def _replicator_render_barrier(
    rep: Any,
    timeline: Any,
    *,
    rt_subframes: int,
    stepper: Any | None = None,
) -> dict[str, Any]:
    time_before = float(timeline.get_current_time())
    logical_steps_before = (
        int(stepper.executed_logical_steps) if stepper is not None else None
    )
    integration_steps_before = (
        int(stepper.executed_integration_steps) if stepper is not None else None
    )
    rep.orchestrator.step(
        rt_subframes=int(rt_subframes),
        pause_timeline=True,
        delta_time=0.0,
    )
    rep.orchestrator.wait_until_complete()
    time_after = float(timeline.get_current_time())
    if not math.isclose(time_before, time_after, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("replicator_render_advanced_timeline")
    logical_steps_after = (
        int(stepper.executed_logical_steps) if stepper is not None else None
    )
    integration_steps_after = (
        int(stepper.executed_integration_steps) if stepper is not None else None
    )
    strict_step_counts_unchanged = (
        stepper is None
        or (
            logical_steps_before == logical_steps_after
            and integration_steps_before == integration_steps_after
        )
    )
    if not strict_step_counts_unchanged:
        raise RuntimeError("replicator_render_advanced_physics")
    return {
        "timeline_time_before": time_before,
        "timeline_time_after": time_after,
        "timeline_unchanged": True,
        "logical_steps_before": logical_steps_before,
        "logical_steps_after": logical_steps_after,
        "integration_steps_before": integration_steps_before,
        "integration_steps_after": integration_steps_after,
        "strict_step_counts_unchanged": strict_step_counts_unchanged,
        "rt_subframes": int(rt_subframes),
    }


def _capture_frame(
    *,
    rep: Any,
    timeline: Any,
    physical_positions: Sequence[Sequence[float]],
    stepper: Any,
    resources: Mapping[str, Mapping[str, Any]],
    output_dir: Path,
    state_index: int,
    width: int,
    height: int,
) -> tuple[dict[str, str], dict[str, Any]]:
    from PIL import Image
    from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import (
        _position_hash,
    )

    before_hash = _position_hash(physical_positions)
    barrier = _replicator_render_barrier(
        rep,
        timeline,
        rt_subframes=1,
        stepper=stepper,
    )
    paths: dict[str, str] = {}
    diagnostics: dict[str, Any] = {}
    for name, resource in resources.items():
        path = output_dir / "frames" / name / f"frame_{state_index:04d}.png"
        rgb = normalize_rgb_frame(
            resource["annotator"].get_data(),
            expected_width=width,
            expected_height=height,
        )
        mean = float(rgb.mean())
        std = float(rgb.std())
        if mean < 5.0 or std < 2.0:
            raise RuntimeError(
                f"rgb_capture_near_black_or_flat:{name}:mean={mean}:std={std}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgb, mode="RGB").save(path)
        paths[name] = str(path)
        diagnostics[name] = {
            "status": "saved_replicator_rgb",
            "shape": list(rgb.shape),
            "dtype": str(rgb.dtype),
            "mean": mean,
            "std": std,
            "path": str(path),
            "sha256": _sha256_file(path),
        }
    return paths, {
        "position_hash_before": before_hash,
        "post_render_usd_particle_readback": "visual_proxy_positions_are_explicit_usd",
        "render_barrier": barrier,
        "cameras": diagnostics,
    }


def _run_isaac(args: argparse.Namespace) -> dict[str, Any]:
    from isaacsim import SimulationApp

    output_dir = _resolve_output(args)
    if output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"output_exists:{output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    overlay_path = output_dir / "interndata_parity_overlay.usda"
    source_path = Path(args.usd).resolve(strict=True)

    app = SimulationApp(
        {
            "headless": bool(args.headless),
            "width": int(args.width),
            "height": int(args.height),
            "renderer": "RayTracedLighting",
        }
    )
    summary: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "interndata_pour_parity_probe",
        "mode": args.mode,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "technical_valid": False,
        "physics_pass": False,
        "visual_pass": None,
        "final_verdict": None,
        "output_dir": str(output_dir),
    }
    stepper = None
    prefluid_step_summary = None
    kinematic_execution: dict[str, Any] | None = None
    capture_resources: dict[str, dict[str, Any]] = {}
    capture_cleanup: dict[str, Any] | None = None
    try:
        import carb
        import omni.kit.app
        import omni.physics.tensors
        import omni.physx
        import omni.physx.bindings._physx as pb
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd
        import numpy as np
        from pxr import Gf, Usd, UsdGeom, UsdPhysics, UsdUtils
        from tools.labutopia_fluid.real_beaker import (
            classify_visible_beaker_positions,
            derive_cup_interior_frame,
        )
        from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import (
            _position_hash,
            _write_mp4_from_frames,
        )
        from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
            StrictPhysicsStepper,
            _author_liquid_presentation_lighting,
            _capture_kit_log_cursor,
            _configure_physics_scene_for_pbd,
            _read_kit_log_segment,
        )

        log_cursor = _capture_kit_log_cursor()
        overlay = _prepare_overlay(
            source_scene=source_path,
            overlay_path=overlay_path,
            mode=args.mode,
            collider_mode=args.collider_mode,
        )
        settings = carb.settings.get_settings()
        settings.set(pb.SETTING_UPDATE_TO_USD, True)
        settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
        settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
        settings.set(pb.SETTING_DISPLAY_PARTICLES, getattr(pb.VisualizerMode, "NONE", 0))
        settings.set_bool(pb.SETTING_SUPPRESS_READBACK, False)
        settings.set_bool("/physics/suppressReadback", False)

        context = omni.usd.get_context()
        opened = bool(context.open_stage(str(overlay_path)))
        stage = context.get_stage()
        updates = 0
        while stage is None and updates < 30:
            app.update()
            stage = context.get_stage()
            updates += 1
        if not opened or stage is None:
            raise RuntimeError("runtime_overlay_open_failed")
        stage.SetEditTarget(stage.GetRootLayer())
        timeline = omni.timeline.get_timeline_interface()
        timeline.stop()
        physics_settings = _configure_physics_scene_for_pbd(
            stage,
            PHYSICS_SCENE_PATH,
            integration_dt=INTEGRATION_DT,
            strict_mode=True,
        )
        stage_contract = _validate_stage_contract(stage, physics_settings)
        if not stage_contract["valid"]:
            raise RuntimeError(f"stage_contract_invalid:{stage_contract}")

        rigid_paths = runtime_kinematic_rigid_paths(
            mode=args.mode,
            collider_mode=args.collider_mode,
        )
        for path in rigid_paths:
            prim = stage.GetPrimAtPath(path)
            if prim and prim.IsValid():
                rigid = UsdPhysics.RigidBodyAPI.Apply(prim)
                rigid.CreateKinematicEnabledAttr().Set(True)

        source_frame = derive_cup_interior_frame(
            stage,
            parent_path="/World/beaker2",
            visual_mesh_path="/World/beaker2/mesh",
            calibration_points_path="/World/ParticleSet",
        )
        target_frame = derive_cup_interior_frame(
            stage,
            parent_path="/World/beaker1",
            visual_mesh_path="/World/beaker1/mesh",
            calibration_points_path=None,
        )
        table_bbox_cache = UsdGeom.BBoxCache(
            0,
            [UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
            useExtentsHint=True,
        )
        table_box = table_bbox_cache.ComputeWorldBound(
            stage.GetPrimAtPath("/World/table")
        ).ComputeAlignedBox()
        table_z = float(table_box.GetMax()[2])

        stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
        stepper = StrictPhysicsStepper.attach(
            interface=omni.physx.get_physx_simulation_interface(),
            logical_dt=PUBLIC_PHYSICS_DT,
            integration_dt=INTEGRATION_DT,
            substeps_per_logical_step=PHYSICS_SUBSTEPS_PER_FRAME,
            stage_id=stage_id,
        )
        for _ in range(PUBLIC_SETUP_STEPS + PUBLIC_PRE_FLUID_STEPS):
            stepper.step()
        stepper.detach()
        prefluid_step_summary = stepper.summary(
            requested_steps=PUBLIC_SETUP_STEPS + PUBLIC_PRE_FLUID_STEPS
        )
        stepper = None

        source_frame = derive_cup_interior_frame(
            stage,
            parent_path="/World/beaker2",
            visual_mesh_path="/World/beaker2/mesh",
            calibration_points_path="/World/ParticleSet",
        )
        target_frame = derive_cup_interior_frame(
            stage,
            parent_path="/World/beaker1",
            visual_mesh_path="/World/beaker1/mesh",
            calibration_points_path=None,
        )
        grid = build_centered_public_grid(source_frame)
        authored = _author_public_fluid(stage, grid["positions_world"])
        presentation_lighting = _author_liquid_presentation_lighting(stage)
        particle_authoring_initialization = {
            "strategy": "complete_usd_points_authored_while_physx_detached",
            "paused_kit_update_count_before_physics": 0,
            "particle_count": authored["initial_authored_points_count"],
            "authored": authored["initial_authored_points_count"]
            == PUBLIC_PARTICLE_COUNT,
        }
        cameras_info = _camera_specs(source_frame, target_frame)
        for spec in cameras_info.values():
            _define_camera(stage, spec)
        authored_scene_path = output_dir / "authored_scene.usda"
        stage.GetRootLayer().Export(str(authored_scene_path))

        stepper = StrictPhysicsStepper.attach(
            interface=omni.physx.get_physx_simulation_interface(),
            logical_dt=PUBLIC_PHYSICS_DT,
            integration_dt=INTEGRATION_DT,
            substeps_per_logical_step=PHYSICS_SUBSTEPS_PER_FRAME,
            stage_id=stage_id,
        )

        static_records: list[dict[str, Any]] = []
        static_trace = output_dir / "static_hold_trace.jsonl"
        static_trace.write_text("", encoding="utf-8")
        frame_paths: dict[str, list[Path]] = {
            name: [] for name in cameras_info
        }
        capture_diagnostics: dict[str, Any] = {}
        start_time = time.monotonic()
        static_sampling_plan = build_static_sampling_plan()
        for sample in static_sampling_plan:
            state_index = int(sample["state_index"])
            if sample["advance_physics_before_read"]:
                if time.monotonic() - start_time > args.runtime_timeout_seconds:
                    raise TimeoutError("static_hold_timeout")
                stepper.step()
            if sample["readback_source"] == "authored_usd_points":
                positions = list(grid["positions_world"])
            else:
                positions = read_physics_particle_points(stage, PARTICLE_SET_PATH)
            strict_counts = classify_source_hold_positions(positions, source_frame)
            record = {
                "step_index": state_index,
                "global_physics_step_index": PUBLIC_SETUP_STEPS + PUBLIC_PRE_FLUID_STEPS + state_index,
                "readback_source": sample["readback_source"],
                "particle_count": len(positions),
                "position_sha256": _position_hash(positions),
                "strict_counts": strict_counts,
                "positions": positions,
            }
            static_records.append(record)
            _append_jsonl(static_trace, record)

        static_classification = classify_static_hold_records(static_records)
        if args.mode == "static":
            physics_classification = static_classification
            mode_records: list[dict[str, Any]] = static_records
            schedule = None
        else:
            if not static_classification["physics_pass"]:
                raise RuntimeError("kinematic_pre_hold_failed")
            schedule = build_fixed_kinematic_schedule()
            source_parent = stage.GetPrimAtPath("/World/beaker2")
            transform_op = UsdGeom.Xformable(source_parent).GetOrderedXformOps()[0]
            overlay_transform = next(
                item for item in overlay["transforms"] if item["parent_path"] == "/World/beaker2"
            )
            initial_parent = _read_matrix(overlay_transform["initial_matrix"])
            source_actor_path = str(
                overlay_transform.get("actor_path")
                or overlay_transform.get("mesh_path")
            )
            tensor_simulation = omni.physics.tensors.create_simulation_view(
                "numpy", stage_id
            )
            source_actor_view = tensor_simulation.create_rigid_body_view(
                source_actor_path
            )
            if source_actor_view.count != 1:
                raise RuntimeError(
                    f"source_kinematic_actor_view_count_invalid:{source_actor_path}:"
                    f"{source_actor_view.count}"
                )
            source_actor_indices = np.asarray([0], dtype=np.uint32)
            kinematic_records: list[dict[str, Any]] = []
            kinematic_trace = output_dir / "kinematic_trace.jsonl"
            kinematic_trace.write_text("", encoding="utf-8")
            for state in schedule["states"]:
                state_index = int(state["step_index"])
                current_parent = _kinematic_parent_matrix(
                    state=state,
                    initial_parent=initial_parent,
                    source_frame=source_frame,
                    target_frame=target_frame,
                )
                target_pose = matrix_to_physx_pose(current_parent)
                if state_index > 0:
                    source_actor_view.set_kinematic_targets(
                        np.asarray([target_pose], dtype=np.float32),
                        source_actor_indices,
                    )
                    stepper.step()
                actual_pose = (
                    np.asarray(source_actor_view.get_transforms(), dtype=np.float64)
                    .reshape((-1, 7))[0]
                    .tolist()
                )
                pose_error = kinematic_pose_error(target_pose, actual_pose)
                actual_parent = physx_pose_to_matrix(actual_pose)
                current_source_frame = _frame_at_parent_matrix(
                    source_frame,
                    initial_parent,
                    actual_parent,
                )
                positions = (
                    list(static_records[-1]["positions"])
                    if state_index == 0
                    else read_physics_particle_points(stage, PARTICLE_SET_PATH)
                )
                counts = classify_two_beaker_positions(
                    positions,
                    source_frame=current_source_frame,
                    target_frame=target_frame,
                    table_z=table_z,
                )
                record = {
                    "step_index": state_index,
                    "global_physics_step_index": (
                        PUBLIC_SETUP_STEPS
                        + PUBLIC_PRE_FLUID_STEPS
                        + PUBLIC_POST_FLUID_STEPS
                        + state_index
                    ),
                    "phase": state["phase"],
                    "translation_progress": state["translation_progress"],
                    "tilt_degrees": state["tilt_degrees"],
                    "kinematic_target_pose_xyzw": target_pose,
                    "kinematic_readback_pose_xyzw": actual_pose,
                    "kinematic_pose_error": pose_error,
                    "kinematic_actor_path": source_actor_path,
                    "particle_count": len(positions),
                    "position_sha256": _position_hash(positions),
                    "source_frame": current_source_frame.as_dict(),
                    "source_parent_matrix": [
                        [float(actual_parent[row][column]) for column in range(4)]
                        for row in range(4)
                    ],
                    "target_parent_matrix": [
                        [float(current_parent[row][column]) for column in range(4)]
                        for row in range(4)
                    ],
                    "counts": counts,
                    "positions": positions,
                }
                kinematic_records.append(record)
                _append_jsonl(kinematic_trace, record)
            kinematic_execution = {
                "driver": "omni.physics.tensors.RigidBodyView.set_kinematic_targets",
                "frontend": "numpy",
                "actor_path": source_actor_path,
                "actor_count": int(source_actor_view.count),
                "actor_prim_paths": [
                    str(path) for path in source_actor_view.prim_paths
                ],
                "target_quaternion_order": "xyzw",
                "readback_required_for_classification": True,
                "state_count": len(kinematic_records),
                "max_position_error_m": max(
                    record["kinematic_pose_error"]["position_m"]
                    for record in kinematic_records
                ),
                "max_rotation_error_degrees": max(
                    record["kinematic_pose_error"]["rotation_degrees"]
                    for record in kinematic_records
                ),
                "all_pose_readbacks_within_tolerance": all(
                    record["kinematic_pose_error"]["within_tolerance"]
                    for record in kinematic_records
                ),
            }
            physics_classification = classify_kinematic_records(kinematic_records)
            mode_records = kinematic_records

        capture_resources = _create_replicator_capture_resources(
            rep,
            camera_specs=cameras_info,
            width=args.width,
            height=args.height,
        )
        replay_records = select_capture_records(
            args.mode,
            mode_records,
            frame_stride=args.frame_stride,
        )
        for replay_index, record in enumerate(replay_records):
            state_index = int(record["step_index"])
            actor_replay = None
            if args.mode == "kinematic":
                actor_replay = replay_kinematic_actor_pose(
                    view=source_actor_view,
                    pose_xyzw=record["kinematic_readback_pose_xyzw"],
                    indices=source_actor_indices,
                    np_module=np,
                )
                transform_op.Set(
                    physx_pose_to_matrix(actor_replay["actual_pose_xyzw"])
                )
                replay_authoring = author_replay_particle_positions(
                    stage,
                    PARTICLE_SET_PATH,
                    record["positions"],
                )
                if not replay_authoring["display_and_simulation_points_match"]:
                    raise RuntimeError(
                        f"capture_replay_position_authoring_failed:{state_index}"
                    )
            proxy_authoring = author_visual_particle_proxy(
                stage,
                record["positions"],
                contract=build_visual_particle_proxy_contract(
                    physical_width=PUBLIC_POINT_WIDTH
                ),
            )
            if replay_index == 0:
                warmup = _replicator_render_barrier(
                    rep,
                    timeline,
                    rt_subframes=max(1, args.camera_warmup_updates),
                    stepper=stepper,
                )
                stepper.record_render_invariance_check()
                capture_diagnostics["offline_replay_camera_warmup"] = {
                    "state_index": state_index,
                    "render_barrier": warmup,
                    "visual_particle_proxy": proxy_authoring,
                }
                if args.mode == "kinematic":
                    author_replay_particle_positions(
                        stage,
                        PARTICLE_SET_PATH,
                        record["positions"],
                    )
            paths, diagnostics = _capture_frame(
                rep=rep,
                timeline=timeline,
                physical_positions=record["positions"],
                stepper=stepper,
                resources=capture_resources,
                output_dir=output_dir,
                state_index=state_index,
                width=args.width,
                height=args.height,
            )
            capture_diagnostics[
                f"offline_replay_{args.mode}_{state_index:04d}"
            ] = diagnostics
            if actor_replay is not None:
                capture_diagnostics[
                    f"offline_replay_{args.mode}_{state_index:04d}"
                ]["kinematic_actor_replay"] = actor_replay
            for name, path in paths.items():
                frame_paths[name].append(Path(path))
            stepper.record_render_invariance_check()

        final_record = mode_records[-1]
        if args.mode == "kinematic":
            final_actor_replay = replay_kinematic_actor_pose(
                view=source_actor_view,
                pose_xyzw=final_record["kinematic_readback_pose_xyzw"],
                indices=source_actor_indices,
                np_module=np,
            )
            transform_op.Set(
                physx_pose_to_matrix(final_actor_replay["actual_pose_xyzw"])
            )
        author_replay_particle_positions(
            stage,
            PARTICLE_SET_PATH,
            final_record["positions"],
        )
        author_visual_particle_proxy(
            stage,
            final_record["positions"],
            contract=build_visual_particle_proxy_contract(
                physical_width=PUBLIC_POINT_WIDTH
            ),
        )

        videos = {}
        for name, paths in frame_paths.items():
            video_path = output_dir / f"{name}.mp4"
            written = _write_mp4_from_frames(paths, video_path, fps=args.video_fps)
            videos[name] = {
                "path": str(video_path) if written else None,
                "frame_count": len(paths),
                "written": written,
            }
        required_video_valid = bool(videos.get("context", {}).get("written")) and bool(
            videos.get("closeup", {}).get("written")
        )
        capture_cleanup = _destroy_replicator_capture_resources(capture_resources)
        capture_resources = {}
        log_segment = _read_kit_log_segment(log_cursor)
        collider_log = _scoped_log_has_collider_failure(log_segment.get("log_text", ""))

        fluid_requested_steps = (
            PUBLIC_POST_FLUID_STEPS
            + (build_fixed_kinematic_schedule()["physics_steps"] if args.mode == "kinematic" else 0)
        )
        stepper.detach()
        fluid_step_summary = stepper.summary(requested_steps=fluid_requested_steps)
        if prefluid_step_summary is None:
            raise RuntimeError("prefluid_step_summary_missing")
        step_summary = combine_strict_phase_summaries(
            {
                "prefluid_scene_setup": prefluid_step_summary,
                "fluid_runtime": fluid_step_summary,
            },
            requested_logical_steps=(
                PUBLIC_SETUP_STEPS
                + PUBLIC_PRE_FLUID_STEPS
                + fluid_requested_steps
            ),
        )
        runtime_validity = classify_runtime_validity(
            step_summary=step_summary,
            stage_contract=stage_contract,
            collider_log=collider_log,
            record_count=len(mode_records),
            required_video_valid=required_video_valid,
        )
        technical_valid = runtime_validity["technical_valid"]
        physics_pass = bool(physics_classification["physics_pass"])
        if not technical_valid:
            preliminary_verdict = (
                "INVALID_STATIC_SOURCE_HOLD"
                if args.mode == "static"
                else "INVALID_KINEMATIC_POUR"
            )
        elif not physics_pass:
            preliminary_verdict = (
                "STATIC_PHYSICS_FAIL"
                if args.mode == "static"
                else "KINEMATIC_POUR_FAIL"
            )
        elif not required_video_valid:
            preliminary_verdict = f"{args.mode.upper()}_VISUAL_CAPTURE_FAIL"
        else:
            preliminary_verdict = (
                f"{args.mode.upper()}_PHYSICS_PASS_PENDING_VISUAL_REVIEW"
            )
        allowed_claims = [
            "public_fluid_recipe_authored",
            "strict_particle_readback_recorded",
        ]
        if args.collider_mode == "native":
            allowed_claims.append("inferred_collider_hypothesis_tested")
        else:
            allowed_claims.append("explicit_open_inner_wall_proxy_tested")
        if required_video_valid:
            allowed_claims.append(
                "offline_physx_readback_visualization_video_recorded"
            )
        summary.update(
            {
                "technical_valid": technical_valid,
                "physics_pass": physics_pass,
                "visual_pass": None,
                "final_verdict": preliminary_verdict,
                "source": overlay,
                "public_fluid_recipe": build_public_fluid_recipe(),
                "inferred_collider_contract": build_inferred_collider_contract(),
                "inner_wall_contract": build_inner_wall_contract(),
                "stage_contract": stage_contract,
                "physics_settings": physics_settings,
                "source_frame": source_frame.as_dict(),
                "target_frame": target_frame.as_dict(),
                "table_z": table_z,
                "grid": {key: value for key, value in grid.items() if key not in {"positions_world", "positions_canonical"}},
                "authored": authored,
                "particle_authoring_initialization": particle_authoring_initialization,
                "presentation_lighting": presentation_lighting,
                "static_classification": static_classification,
                "static_sampling_plan": static_sampling_plan,
                "physics_classification": physics_classification,
                "kinematic_schedule": schedule,
                "kinematic_execution": kinematic_execution,
                "strict_physics_execution": step_summary,
                "runtime_validity": runtime_validity,
                "videos": videos,
                "capture_diagnostics": capture_diagnostics,
                "capture_cleanup": capture_cleanup,
                "collider_log_scan": collider_log,
                "scoped_log": {
                    "path": str(output_dir / "run_scoped_kit_log.log"),
                    "diagnostic_scan_complete": log_segment.get("diagnostic_scan_complete"),
                },
                "claim_boundary": {
                    "allowed": allowed_claims,
                    "blocked": [
                        "exact_internvla_asset_collider_parity",
                        "expert_robot_replay",
                        "policy_or_benchmark_success",
                        "visual_pass_before_independent_review",
                    ],
                },
            }
        )
        (output_dir / "run_scoped_kit_log.log").write_text(
            log_segment.get("log_text", ""), encoding="utf-8"
        )
        final_runtime_path = output_dir / "final_runtime_scene.usda"
        stage.GetRootLayer().Export(str(final_runtime_path))
        stabilized_source_path = output_dir / "stabilized_source_scene.usda"
        authored_stage = Usd.Stage.Open(str(authored_scene_path), Usd.Stage.LoadAll)
        if authored_stage is None:
            raise RuntimeError(f"authored_stage_reopen_failed:{authored_scene_path}")
        summary["stabilized_source_snapshot"] = export_particle_state_layer(
            authored_stage,
            stabilized_source_path,
            static_records[-1]["positions"],
        )
        summary["delivery_snapshots"] = {
            "initial": export_delivery_snapshot(
                stabilized_source_path,
                output_dir / "delivery_initial_scene.usda",
            ),
            "result": export_delivery_snapshot(
                final_runtime_path,
                output_dir / "delivery_result_scene.usda",
            ),
        }
    except Exception as exc:
        summary.update(
            {
                "technical_valid": False,
                "physics_pass": False,
                "final_verdict": (
                    "INVALID_STATIC_SOURCE_HOLD"
                    if args.mode == "static"
                    else "INVALID_KINEMATIC_POUR"
                ),
                "fatal_error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(limit=40),
                },
            }
        )
        if stepper is not None:
            try:
                if not stepper.detach_verified:
                    stepper.detach()
            except Exception as cleanup_exc:
                summary["cleanup_error"] = {
                    "type": type(cleanup_exc).__name__,
                    "message": str(cleanup_exc),
                }
    finally:
        if capture_resources:
            capture_cleanup = _destroy_replicator_capture_resources(capture_resources)
            summary["capture_cleanup"] = capture_cleanup
            capture_resources = {}
        _write_json(output_dir / "runtime_summary.json", summary)
        if not args.skip_app_close:
            app.close()
    return summary


def finalize_visual_review(
    *,
    manifest_path: Path,
    verdict: str,
    notes: str,
    image_paths: Sequence[str],
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(strict=True)
    summary = json.loads(manifest_path.read_text(encoding="utf-8"))
    if verdict not in {"pass", "fail"}:
        raise ValueError("visual_verdict_must_be_pass_or_fail")
    visual_pass = verdict == "pass"
    final = combine_terminal_verdict(
        mode=summary["mode"],
        technical_valid=bool(summary.get("technical_valid")),
        physics_pass=bool(summary.get("physics_pass")),
        visual_pass=visual_pass,
    )
    review = {
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict.upper(),
        "visual_pass": visual_pass,
        "notes": notes,
        "image_paths": list(image_paths),
        "independent_visual_review_required": True,
    }
    summary["visual_pass"] = visual_pass
    summary["visual_review"] = review
    summary["final_verdict"] = final
    _write_json(manifest_path.parent / "visual_review.json", review)
    _write_json(manifest_path, summary)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("static", "kinematic"), default="static")
    parser.add_argument(
        "--collider-mode",
        choices=("inner-wall", "native"),
        default="inner-wall",
    )
    parser.add_argument("--usd", default=str(DEFAULT_SOURCE_SCENE))
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--static-manifest", default=str(DEFAULT_STATIC_MANIFEST))
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--frame-stride", type=int, default=10)
    parser.add_argument("--video-fps", type=float, default=15.0)
    parser.add_argument("--camera-warmup-updates", type=int, default=8)
    parser.add_argument("--runtime-timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--show-ui", action="store_false", dest="headless")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-app-close", action="store_true")
    parser.add_argument("--hard-exit-after-run", action="store_true")
    parser.add_argument("--finalize-manifest", default=None)
    parser.add_argument("--visual-verdict", choices=("pass", "fail"), default=None)
    parser.add_argument("--visual-notes", default="")
    parser.add_argument("--review-image", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.finalize_manifest:
        if args.visual_verdict is None:
            raise ValueError("finalize_manifest_requires_visual_verdict")
        summary = finalize_visual_review(
            manifest_path=Path(args.finalize_manifest),
            verdict=args.visual_verdict,
            notes=args.visual_notes,
            image_paths=args.review_image,
        )
    else:
        if args.mode == "kinematic":
            static_path = Path(args.static_manifest)
            if not static_path.is_file():
                raise FileNotFoundError(f"static_manifest_missing:{static_path}")
            static = json.loads(static_path.read_text(encoding="utf-8"))
            if static.get("final_verdict") != "STATIC_ELIGIBLE_FOR_KINEMATIC":
                raise RuntimeError("static_manifest_not_eligible_for_kinematic")
        summary = _run_isaac(args)
    print(json.dumps(_json_safe(summary), indent=2, sort_keys=True))
    success = bool(summary.get("technical_valid", True)) and not str(
        summary.get("final_verdict", "")
    ).startswith("INVALID")
    exit_code = 0 if success else 1
    if args.hard_exit_after_run:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
