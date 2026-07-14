#!/usr/bin/env python3
"""Build a deterministic support-aligned level1_pour source entry."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import uuid
from typing import Any, Mapping, Sequence

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "level1_pour.yaml"
DEFAULT_SOURCE_PATH = (
    REPO_ROOT
    / "outputs"
    / "usd_asset_packages"
    / "lab_001_localized_20260707"
    / "lab_001_level1_pour_tabletop_with_liquid.usd"
)
EXPECTED_CONFIG_SHA256 = (
    "ec745b14e13c63c5b906ea2b76d08b5d64ef473dfe0567e6deef9252f17950c1"
)
EXPECTED_SOURCE_SHA256 = (
    "77607b6bdf3b6cba419e1bc17943bdb3e220b497a77e98d7665e98f779406211"
)
LAYOUT_VERSION = "level1_pour_config_midpoint_support_aligned_v1"
LAYOUT_SEMANTICS = "config_range_midpoint_support_aligned"
SUPPORT_PRIM_PATH = "/World/Cube"
PARTICLE_SET_PATH = "/World/ParticleSet"
PARTICLE_SET_OWNER_PATH = "/World/beaker2"
LEGACY_FLUID_ROOT_PATH = "/World/fluid"
LEGACY_SAMPLER_PATH = "/World/fluid/Cylinder"
LEGACY_PARTICLE_SYSTEM_PATH = "/World/ParticleSystem"
PARTICLE_SAMPLING_API_SCHEMA = "PhysxParticleSamplingAPI"
SUPPORT_CLEARANCE_M = 0.0
CONTACT_TOLERANCE_M = 1e-6
ENTRY_BASENAME = "lab_001_level1_pour_support_aligned_v1.usda"
OVERLAY_BASENAME = "level1_pour_support_aligned_overlay_v1.usda"
MANIFEST_BASENAME = "support_aligned_manifest.json"
BEAKER_PATHS = {
    "beaker1": ("/World/beaker1", "/World/beaker1/mesh"),
    "beaker2": ("/World/beaker2", "/World/beaker2/mesh"),
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: str | os.PathLike[str]) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _require_sha256(name: str, value: Any) -> str:
    text = str(value)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{name}_invalid")
    return text


def _validate_json_finite(value: Any) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical_json_non_finite")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("canonical_json_key_must_be_string")
            _validate_json_finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_json_finite(item)


def canonical_json_sha256_v1(value: Any) -> str:
    _validate_json_finite(value)
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        if "range" in str(exc).lower() or "nan" in str(exc).lower():
            raise ValueError("canonical_json_non_finite") from exc
        raise
    return _sha256_bytes(payload)


def _plain_finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}_invalid")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name}_invalid")
    return result


def _interval(name: str, value: Any) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"config_interval_invalid:{name}")
    try:
        low = _plain_finite_number("config_numeric_value", value[0])
        high = _plain_finite_number("config_numeric_value", value[1])
    except ValueError as exc:
        raise ValueError("config_numeric_value_invalid") from exc
    if low > high:
        raise ValueError(f"config_interval_reversed:{name}")
    return [low, high]


def _position_range(name: str, value: Any) -> tuple[dict[str, list[float]], list[float]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"config_position_range_invalid:{name}")
    ranges = {axis: _interval(f"{name}.{axis}", value.get(axis)) for axis in "xyz"}
    midpoint = [sum(ranges[axis]) / 2.0 for axis in "xyz"]
    return ranges, midpoint


def load_config_midpoint_contract(
    path: str | os.PathLike[str],
    *,
    expected_sha256: str = EXPECTED_CONFIG_SHA256,
) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise FileNotFoundError(f"config_missing:{target}")
    actual_sha = _sha256_file(target)
    expected_sha = _require_sha256("expected_config_sha256", expected_sha256)
    if actual_sha != expected_sha:
        raise ValueError(f"config_sha256_mismatch:{actual_sha}!={expected_sha}")
    payload = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("config_root_invalid")
    if payload.get("usd_path") != "assets/chemistry_lab/lab_001/lab_001.usd":
        raise ValueError("config_usd_path_changed")
    if payload.get("target_path") != "/World/beaker1":
        raise ValueError("config_target_path_changed")
    task = payload.get("task")
    if not isinstance(task, Mapping):
        raise ValueError("config_task_missing")
    target_ranges, target_midpoint = _position_range("beaker1", task.get("left_pos"))
    source_items = task.get("obj_paths")
    if not isinstance(source_items, list):
        raise ValueError("config_obj_paths_invalid")
    source_matches = [
        item
        for item in source_items
        if isinstance(item, Mapping) and item.get("path") == "/World/beaker2"
    ]
    if len(source_matches) != 1:
        raise ValueError("config_source_beaker_entry_invalid")
    source_ranges, source_midpoint = _position_range(
        "beaker2", source_matches[0].get("position_range")
    )
    for midpoint in (target_midpoint, source_midpoint):
        if not math.isclose(midpoint[2], 0.87, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("config_reset_z_changed")
    contract: dict[str, Any] = {
        "schema_version": 1,
        "contract_version": "config_layout_contract_v1",
        "config_path_relative": str(target.relative_to(REPO_ROOT)),
        "config_sha256": actual_sha,
        "layout_semantics": LAYOUT_SEMANTICS,
        "exact_expert_episode_layout": False,
        "expert_episode_id": None,
        "reset_z_from_config_m": 0.87,
        "beakers": {
            "beaker1": {
                "parent_path": "/World/beaker1",
                "mesh_path": "/World/beaker1/mesh",
                "position_ranges": target_ranges,
                "midpoint_xyz": target_midpoint,
            },
            "beaker2": {
                "parent_path": "/World/beaker2",
                "mesh_path": "/World/beaker2/mesh",
                "position_ranges": source_ranges,
                "midpoint_xyz": source_midpoint,
            },
        },
    }
    contract["config_layout_contract_sha256"] = canonical_json_sha256_v1(contract)
    return contract


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return {
                "__usd_non_finite_float__": (
                    "NaN"
                    if math.isnan(value)
                    else ("Infinity" if value > 0.0 else "-Infinity")
                )
            }
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "path") and type(value).__name__ == "AssetPath":
        return str(value.path)
    try:
        return [_jsonable(item) for item in value]
    except TypeError:
        return str(value)


def _attr_value(attr: Any) -> Any:
    try:
        value = attr.Get()
    except Exception as exc:
        return {"read_error": f"{type(exc).__name__}:{exc}"}
    try:
        value_count = len(value)
    except TypeError:
        value_count = None
    converted = _jsonable(value)
    if value_count is not None and value_count > 1024:
        return {
            "value_count": int(value_count),
            "value_sha256": canonical_json_sha256_v1(converted),
            "usd_type_name": str(attr.GetTypeName()),
        }
    return converted


def world_bbox(stage: Any, prim_path: str) -> dict[str, list[float]]:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        raise ValueError(f"required_prim_missing:{prim_path}")
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy],
        useExtentsHint=False,
    )
    box = cache.ComputeWorldBound(prim).ComputeAlignedBox()
    if box.IsEmpty():
        raise ValueError(f"required_prim_empty_bbox:{prim_path}")
    minimum = [float(value) for value in box.GetMin()]
    maximum = [float(value) for value in box.GetMax()]
    return {
        "min": minimum,
        "max": maximum,
        "center": [(minimum[index] + maximum[index]) / 2.0 for index in range(3)],
        "size": [maximum[index] - minimum[index] for index in range(3)],
    }


def _ordered_xform_ops(prim: Any) -> list[dict[str, Any]]:
    from pxr import UsdGeom

    result = []
    for op in UsdGeom.Xformable(prim).GetOrderedXformOps():
        result.append(
            {
                "name": op.GetOpName(),
                "type": str(op.GetOpType()),
                "precision": str(op.GetPrecision()),
                "value": _jsonable(op.Get()),
            }
        )
    return result


def _translate_op(prim: Any) -> Any:
    from pxr import UsdGeom

    matches = [
        op
        for op in UsdGeom.Xformable(prim).GetOrderedXformOps()
        if op.GetOpName() == "xformOp:translate"
    ]
    if len(matches) != 1:
        raise ValueError(f"parent_translate_op_invalid:{prim.GetPath()}")
    return matches[0]


def _mesh_geometry_signature(stage: Any, path: str) -> dict[str, Any]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim.IsValid() or not prim.IsA(UsdGeom.Mesh):
        raise ValueError(f"required_mesh_invalid:{path}")
    mesh = UsdGeom.Mesh(prim)
    payload = {
        "prim_path": path,
        "points": _jsonable(mesh.GetPointsAttr().Get()),
        "face_vertex_counts": _jsonable(mesh.GetFaceVertexCountsAttr().Get()),
        "face_vertex_indices": _jsonable(mesh.GetFaceVertexIndicesAttr().Get()),
        "normals": _jsonable(mesh.GetNormalsAttr().Get()),
        "normals_interpolation": str(mesh.GetNormalsInterpolation()),
        "subdivision_scheme": str(mesh.GetSubdivisionSchemeAttr().Get()),
        "double_sided": bool(mesh.GetDoubleSidedAttr().Get()),
    }
    return {
        "prim_path": path,
        "points_sha256": canonical_json_sha256_v1(payload["points"]),
        "topology_sha256": canonical_json_sha256_v1(
            {
                "counts": payload["face_vertex_counts"],
                "indices": payload["face_vertex_indices"],
            }
        ),
        "normals_sha256": canonical_json_sha256_v1(payload["normals"]),
        "normals_interpolation": payload["normals_interpolation"],
        "subdivision_scheme": payload["subdivision_scheme"],
        "double_sided": payload["double_sided"],
        "geometry_sha256": canonical_json_sha256_v1(payload),
    }


def _material_binding(stage: Any, path: str) -> str | None:
    from pxr import UsdShade

    material, _relationship = UsdShade.MaterialBindingAPI(
        stage.GetPrimAtPath(path)
    ).ComputeBoundMaterial()
    return str(material.GetPath()) if material else None


def _physics_prim_contract(prim: Any) -> dict[str, Any]:
    attrs = {}
    for attr in prim.GetAttributes():
        name = attr.GetName()
        lowered = name.lower()
        if lowered.startswith("physics:") or lowered.startswith("physx"):
            attrs[name] = _attr_value(attr)
    relationships = {}
    for relationship in prim.GetRelationships():
        name = relationship.GetName()
        lowered = name.lower()
        if lowered.startswith("physics:") or lowered.startswith("physx"):
            relationships[name] = [str(value) for value in relationship.GetTargets()]
    return {
        "path": str(prim.GetPath()),
        "applied_schemas": sorted(str(value) for value in prim.GetAppliedSchemas()),
        "attributes": attrs,
        "relationships": relationships,
    }


def _particle_points_sha256(stage: Any) -> str:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    if not prim.IsValid() or not prim.IsA(UsdGeom.Points):
        raise ValueError(f"required_points_invalid:{PARTICLE_SET_PATH}")
    return canonical_json_sha256_v1(_jsonable(UsdGeom.Points(prim).GetPointsAttr().Get()))


def _bounds(points: Sequence[Any]) -> dict[str, list[float]]:
    if not points:
        raise ValueError("particle_set_points_missing")
    axes = [[float(point[index]) for point in points] for index in range(3)]
    return {
        "min": [min(axis) for axis in axes],
        "max": [max(axis) for axis in axes],
    }


def particle_set_bounds(stage: Any) -> dict[str, dict[str, list[float]]]:
    from pxr import Gf, Usd, UsdGeom

    prim = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    if not prim.IsValid() or not prim.IsA(UsdGeom.Points):
        raise ValueError(f"required_points_invalid:{PARTICLE_SET_PATH}")
    points = UsdGeom.Points(prim).GetPointsAttr().Get()
    if not points:
        raise ValueError("particle_set_points_missing")
    matrix = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(prim)
    world_points = [matrix.Transform(Gf.Vec3d(*point)) for point in points]
    return {
        "local": _bounds(points),
        "world": _bounds(world_points),
    }


def _relationship_targets(prim: Any, name: str) -> list[str]:
    relationship = prim.GetRelationship(name)
    if not relationship:
        return []
    return [str(path) for path in relationship.GetTargets()]


def _api_schema_tokens(prim: Any) -> list[str]:
    metadata = prim.GetMetadata("apiSchemas")
    if metadata is None:
        return []
    try:
        return sorted(str(value) for value in metadata.GetAppliedItems())
    except AttributeError:
        return sorted(str(value) for value in metadata)


def _legacy_particle_graph_snapshot(stage: Any) -> dict[str, Any]:
    required = (
        LEGACY_FLUID_ROOT_PATH,
        LEGACY_SAMPLER_PATH,
        PARTICLE_SET_PATH,
        LEGACY_PARTICLE_SYSTEM_PATH,
    )
    prims = {path: stage.GetPrimAtPath(path) for path in required}
    for path, prim in prims.items():
        if not prim.IsValid():
            raise ValueError(f"required_prim_missing:{path}")
    sampler = prims[LEGACY_SAMPLER_PATH]
    particle_set = prims[PARTICLE_SET_PATH]
    particle_system = prims[LEGACY_PARTICLE_SYSTEM_PATH]

    def attr_value(prim: Any, name: str) -> Any:
        attr = prim.GetAttribute(name)
        return attr.Get() if attr else None

    return {
        "sampler_path": LEGACY_SAMPLER_PATH,
        "particle_set_path": PARTICLE_SET_PATH,
        "particle_system_path": LEGACY_PARTICLE_SYSTEM_PATH,
        "source_sampler_targets": _relationship_targets(
            sampler, "physxParticleSampling:particles"
        ),
        "source_particle_system_targets": _relationship_targets(
            particle_set, "physxParticle:particleSystem"
        ),
        "source_sampler_volume": attr_value(
            sampler, "physxParticleSampling:volume"
        ),
        "source_particle_set_self_collision": attr_value(
            particle_set, "physxParticle:selfCollision"
        ),
        "source_particle_set_fluid": attr_value(
            particle_set, "physxParticle:fluid"
        ),
        "source_particle_system_enabled": attr_value(
            particle_system, "particleSystemEnabled"
        ),
        "source_sampling_api_metadata_tokens": _api_schema_tokens(sampler),
        "source_particle_set_bounds": particle_set_bounds(stage),
        "overlay_must_be_stronger_than_source": True,
        "retained_as_inert_calibration_data": True,
        "expected_composed_sampler_targets": [],
        "expected_composed_particle_system_targets": [],
        "expected_composed_flags": {
            "sampler_volume": False,
            "particle_set_self_collision": False,
            "particle_set_fluid": False,
            "particle_system_enabled": False,
        },
        "expected_sampling_api_present": False,
        "expected_all_legacy_prims_active": True,
        "expected_all_legacy_prims_hidden": True,
    }


def particle_set_owner_canonical_sha256(stage: Any) -> str:
    from pxr import Gf, Usd, UsdGeom

    particle_prim = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    owner_prim = stage.GetPrimAtPath(PARTICLE_SET_OWNER_PATH)
    if not particle_prim.IsValid() or not owner_prim.IsValid():
        raise ValueError("particle_set_owner_prim_missing")
    points = UsdGeom.Points(particle_prim).GetPointsAttr().Get()
    if not points:
        raise ValueError("particle_set_points_missing")
    cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    particle_world = cache.GetLocalToWorldTransform(particle_prim)
    owner_inverse = cache.GetLocalToWorldTransform(owner_prim).GetInverse()
    canonical = []
    for point in points:
        world = particle_world.Transform(Gf.Vec3d(*point))
        local = owner_inverse.Transform(world)
        canonical.append([round(float(value), 12) for value in local])
    return canonical_json_sha256_v1(canonical)


def snapshot_scene_authority(stage: Any) -> dict[str, Any]:
    mesh_paths = [value[1] for value in BEAKER_PATHS.values()]
    particle_prim = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    return {
        "schema_version": 1,
        "mesh_geometry": {
            path: _mesh_geometry_signature(stage, path) for path in mesh_paths
        },
        "mesh_material_bindings": {
            path: _material_binding(stage, path) for path in mesh_paths
        },
        "physics_contract": {
            path: _physics_prim_contract(stage.GetPrimAtPath(path))
            for path in [*mesh_paths, SUPPORT_PRIM_PATH, PARTICLE_SET_PATH]
        },
        "particle_points_sha256": _particle_points_sha256(stage),
        "particle_owner_canonical_sha256": particle_set_owner_canonical_sha256(
            stage
        ),
        "parent_transforms": {
            parent_path: _ordered_xform_ops(stage.GetPrimAtPath(parent_path))
            for parent_path, _mesh_path in BEAKER_PATHS.values()
        },
    }


def _support_signature(stage: Any) -> dict[str, Any]:
    prim = stage.GetPrimAtPath(SUPPORT_PRIM_PATH)
    if not prim.IsValid():
        raise ValueError(f"required_prim_missing:{SUPPORT_PRIM_PATH}")
    geometry_attrs = {}
    for name in ("size", "points", "faceVertexCounts", "faceVertexIndices"):
        attr = prim.GetAttribute(name)
        if attr:
            geometry_attrs[name] = _attr_value(attr)
    payload = {
        "prim_path": SUPPORT_PRIM_PATH,
        "type_name": prim.GetTypeName(),
        "bbox": world_bbox(stage, SUPPORT_PRIM_PATH),
        "geometry_attributes": geometry_attrs,
        "xform_ops": _ordered_xform_ops(prim),
        "physics": _physics_prim_contract(prim),
    }
    return {
        **payload,
        "bbox_max_z": float(payload["bbox"]["max"][2]),
        "support_signature_sha256": canonical_json_sha256_v1(payload),
    }


def _validate_config_contract(contract: Mapping[str, Any]) -> None:
    expected_hash = contract.get("config_layout_contract_sha256")
    payload = dict(contract)
    payload.pop("config_layout_contract_sha256", None)
    if expected_hash != canonical_json_sha256_v1(payload):
        raise ValueError("config_layout_contract_sha256_mismatch")
    if contract.get("layout_semantics") != LAYOUT_SEMANTICS:
        raise ValueError("layout_semantics_invalid")
    if contract.get("exact_expert_episode_layout") is not False:
        raise ValueError("exact_expert_episode_claim_forbidden")


def build_support_alignment_contract(
    stage: Any,
    *,
    config_contract: Mapping[str, Any],
    source_usd_sha256: str,
    expected_source_usd_sha256: str = EXPECTED_SOURCE_SHA256,
) -> dict[str, Any]:
    _validate_config_contract(config_contract)
    actual_source = _require_sha256("source_usd_sha256", source_usd_sha256)
    expected_source = _require_sha256(
        "expected_source_usd_sha256", expected_source_usd_sha256
    )
    if actual_source != expected_source:
        raise ValueError(
            f"source_usd_sha256_mismatch:{actual_source}!={expected_source}"
        )
    required_paths = [
        "/World",
        "/World/beaker1",
        "/World/beaker1/mesh",
        "/World/beaker2",
        "/World/beaker2/mesh",
        PARTICLE_SET_PATH,
        SUPPORT_PRIM_PATH,
        LEGACY_FLUID_ROOT_PATH,
        LEGACY_SAMPLER_PATH,
        LEGACY_PARTICLE_SYSTEM_PATH,
    ]
    for path in required_paths:
        if not stage.GetPrimAtPath(path).IsValid():
            raise ValueError(f"required_prim_missing:{path}")
    authority = snapshot_scene_authority(stage)
    legacy_graph = _legacy_particle_graph_snapshot(stage)
    if legacy_graph["source_sampler_targets"] != [PARTICLE_SET_PATH]:
        raise ValueError("legacy_sampler_source_relationship_invalid")
    if legacy_graph["source_particle_system_targets"] != [
        LEGACY_PARTICLE_SYSTEM_PATH
    ]:
        raise ValueError("legacy_particle_set_source_relationship_invalid")
    support = _support_signature(stage)
    support_top = float(support["bbox"]["max"][2])
    target_bottom = support_top + SUPPORT_CLEARANCE_M
    beakers = {}
    for name, (parent_path, mesh_path) in BEAKER_PATHS.items():
        parent = stage.GetPrimAtPath(parent_path)
        midpoint = [
            float(value)
            for value in config_contract["beakers"][name]["midpoint_xyz"]
        ]
        translate_op = _translate_op(parent)
        initial_parent = [float(value) for value in translate_op.Get()]
        if any(
            not math.isclose(initial_parent[index], midpoint[index], abs_tol=1e-12)
            for index in range(3)
        ):
            raise ValueError(f"config_midpoint_parent_mismatch:{parent_path}")
        initial_bbox = world_bbox(stage, parent_path)
        initial_bottom = float(initial_bbox["min"][2])
        delta_z = target_bottom - initial_bottom
        if not math.isfinite(delta_z) or delta_z >= -CONTACT_TOLERANCE_M:
            raise ValueError(f"support_alignment_requires_downward_move:{parent_path}")
        beakers[name] = {
            "parent_path": parent_path,
            "mesh_path": mesh_path,
            "initial_parent_xyz": initial_parent,
            "initial_parent_xform_ops": _ordered_xform_ops(parent),
            "initial_bbox": initial_bbox,
            "initial_bbox_bottom_z": initial_bottom,
            "target_bbox_bottom_z": target_bottom,
            "delta_z": delta_z,
            "final_parent_xyz": [initial_parent[0], initial_parent[1], initial_parent[2] + delta_z],
            "support_collision_top_z": support_top,
            "support_clearance_m": SUPPORT_CLEARANCE_M,
            "contact_tolerance_m": CONTACT_TOLERANCE_M,
        }
    particle_delta = float(beakers["beaker2"]["delta_z"])
    contract: dict[str, Any] = {
        "schema_version": 1,
        "contract_version": LAYOUT_VERSION,
        "layout_semantics": LAYOUT_SEMANTICS,
        "exact_expert_episode_layout": False,
        "expert_episode_id": None,
        "reset_z_from_config_m": 0.87,
        "support_alignment_is_static_authoring": True,
        "old_physics_authority_applies_to_support_aligned_stage": False,
        "source_usd_sha256": actual_source,
        "config_sha256": config_contract["config_sha256"],
        "config_layout_contract_sha256": config_contract[
            "config_layout_contract_sha256"
        ],
        "builder_script_sha256": _sha256_file(__file__),
        "support_clearance_m": SUPPORT_CLEARANCE_M,
        "contact_tolerance_m": CONTACT_TOLERANCE_M,
        "support": support,
        "beakers": beakers,
        "particle_set": {
            "prim_path": PARTICLE_SET_PATH,
            "owner_beaker_path": PARTICLE_SET_OWNER_PATH,
            "ownership_semantics": "legacy_calibration_and_particle_set_for_source_beaker2",
            "delta_source": PARTICLE_SET_OWNER_PATH,
            "delta_z": particle_delta,
            "point_array_sha256": authority["particle_points_sha256"],
            "owner_canonical_sha256_before": authority[
                "particle_owner_canonical_sha256"
            ],
            "owner_canonical_quantization_decimals": 12,
        },
        "legacy_particle_graph": legacy_graph,
        "source_authority_snapshot": authority,
        "claim_boundary": {
            "physical_volume_parity_claim_allowed": False,
            "free_surface_shape_claim_allowed": False,
            "fluid_dynamics_claim_allowed": False,
            "pour_success_claim_allowed": False,
        },
    }
    contract["support_aligned_source_contract_sha256"] = canonical_json_sha256_v1(
        contract
    )
    return contract


def begin_support_alignment_layer(stage: Any, path: str | os.PathLike[str]) -> Any:
    from pxr import Sdf, Usd

    session = stage.GetSessionLayer()
    if session is None:
        raise RuntimeError("support_alignment_session_layer_missing")
    if session.subLayerPaths or session.rootPrims:
        raise RuntimeError("support_alignment_session_layer_not_empty")
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError(f"support_alignment_layer_exists:{target}")
    layer = Sdf.Layer.CreateNew(str(target))
    if layer is None:
        raise RuntimeError("support_alignment_layer_create_failed")
    session.subLayerPaths.insert(0, layer.identifier)
    stage.SetEditTarget(Usd.EditTarget(layer))
    if stage.GetEditTarget().GetLayer().identifier != layer.identifier:
        raise RuntimeError("support_alignment_edit_target_failed")
    return layer


def _validate_contract_hash(contract: Mapping[str, Any]) -> None:
    expected = contract.get("support_aligned_source_contract_sha256")
    payload = dict(contract)
    payload.pop("support_aligned_source_contract_sha256", None)
    if expected != canonical_json_sha256_v1(payload):
        raise ValueError("support_aligned_source_contract_sha256_mismatch")


def _set_world_contract_attributes(world_prim: Any, contract: Mapping[str, Any]) -> None:
    from pxr import Sdf

    values = {
        "labutopia:supportAlignedLayoutVersion": (
            Sdf.ValueTypeNames.String,
            contract["contract_version"],
        ),
        "labutopia:layoutSemantics": (
            Sdf.ValueTypeNames.String,
            contract["layout_semantics"],
        ),
        "labutopia:exactExpertEpisodeLayout": (
            Sdf.ValueTypeNames.Bool,
            False,
        ),
        "labutopia:supportAlignedSourceContractSha256": (
            Sdf.ValueTypeNames.String,
            contract["support_aligned_source_contract_sha256"],
        ),
        "labutopia:configLayoutContractSha256": (
            Sdf.ValueTypeNames.String,
            contract["config_layout_contract_sha256"],
        ),
        "labutopia:sourceUsdSha256": (
            Sdf.ValueTypeNames.String,
            contract["source_usd_sha256"],
        ),
        "labutopia:particleSetOwnerBeakerPath": (
            Sdf.ValueTypeNames.String,
            PARTICLE_SET_OWNER_PATH,
        ),
        "labutopia:supportClearanceM": (
            Sdf.ValueTypeNames.Double,
            SUPPORT_CLEARANCE_M,
        ),
    }
    for name, (type_name, value) in values.items():
        world_prim.CreateAttribute(name, type_name, custom=True).Set(value)


def _author_legacy_particle_graph_isolation(stage: Any, overlay_layer: Any) -> None:
    from pxr import Sdf, UsdGeom

    sampler = stage.GetPrimAtPath(LEGACY_SAMPLER_PATH)
    particle_set = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    particle_system = stage.GetPrimAtPath(LEGACY_PARTICLE_SYSTEM_PATH)
    for path, prim in (
        (LEGACY_FLUID_ROOT_PATH, stage.GetPrimAtPath(LEGACY_FLUID_ROOT_PATH)),
        (LEGACY_SAMPLER_PATH, sampler),
        (PARTICLE_SET_PATH, particle_set),
        (LEGACY_PARTICLE_SYSTEM_PATH, particle_system),
    ):
        if not prim.IsValid() or not prim.IsActive():
            raise RuntimeError(f"legacy_particle_graph_prim_inactive:{path}")
        prim.CreateAttribute("visibility", Sdf.ValueTypeNames.Token).Set(
            UsdGeom.Tokens.invisible
        )

    sampler.SetMetadata(
        "apiSchemas",
        Sdf.TokenListOp.Create(deletedItems=[PARTICLE_SAMPLING_API_SCHEMA]),
    )
    sampler.CreateRelationship("physxParticleSampling:particles").SetTargets([])
    sampler.CreateAttribute(
        "physxParticleSampling:volume", Sdf.ValueTypeNames.Bool
    ).Set(False)
    particle_set.CreateRelationship("physxParticle:particleSystem").SetTargets([])
    particle_set.CreateAttribute(
        "physxParticle:selfCollision", Sdf.ValueTypeNames.Bool
    ).Set(False)
    particle_set.CreateAttribute("physxParticle:fluid", Sdf.ValueTypeNames.Bool).Set(
        False
    )
    particle_system.CreateAttribute(
        "particleSystemEnabled", Sdf.ValueTypeNames.Bool
    ).Set(False)

    sampler_spec = overlay_layer.GetPrimAtPath(LEGACY_SAMPLER_PATH)
    if sampler_spec is None:
        raise RuntimeError("legacy_particle_graph_overlay_sampler_spec_missing")
    api_op = sampler_spec.GetInfo("apiSchemas")
    if (
        api_op is None
        or PARTICLE_SAMPLING_API_SCHEMA
        not in [str(value) for value in api_op.deletedItems]
    ):
        raise RuntimeError("legacy_particle_sampling_api_delete_op_missing")


def _legacy_particle_graph_isolation(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    fluid_root = stage.GetPrimAtPath(LEGACY_FLUID_ROOT_PATH)
    sampler = stage.GetPrimAtPath(LEGACY_SAMPLER_PATH)
    particle_set = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    particle_system = stage.GetPrimAtPath(LEGACY_PARTICLE_SYSTEM_PATH)
    prims = (fluid_root, sampler, particle_set, particle_system)
    all_active = all(prim.IsValid() and prim.IsActive() for prim in prims)
    all_hidden = all(
        prim.IsValid()
        and UsdGeom.Imageable(prim).GetVisibilityAttr().Get()
        == UsdGeom.Tokens.invisible
        for prim in prims
    )
    sampler_targets = _relationship_targets(
        sampler, "physxParticleSampling:particles"
    )
    particle_system_targets = _relationship_targets(
        particle_set, "physxParticle:particleSystem"
    )
    sampler_volume = sampler.GetAttribute("physxParticleSampling:volume").Get()
    particle_set_self_collision = particle_set.GetAttribute(
        "physxParticle:selfCollision"
    ).Get()
    particle_set_fluid = particle_set.GetAttribute("physxParticle:fluid").Get()
    particle_system_enabled = particle_system.GetAttribute(
        "particleSystemEnabled"
    ).Get()
    sampling_api_present = PARTICLE_SAMPLING_API_SCHEMA in set(
        [*_api_schema_tokens(sampler), *sampler.GetAppliedSchemas()]
    )
    result = {
        "sampler_targets": sampler_targets,
        "particle_system_targets": particle_system_targets,
        "sampler_volume": sampler_volume,
        "particle_set_self_collision": particle_set_self_collision,
        "particle_set_fluid": particle_set_fluid,
        "particle_system_enabled": particle_system_enabled,
        "sampling_api_present": sampling_api_present,
        "all_legacy_prims_active": all_active,
        "all_legacy_prims_hidden": all_hidden,
    }
    result["verified"] = (
        not sampler_targets
        and not particle_system_targets
        and sampler_volume is False
        and particle_set_self_collision is False
        and particle_set_fluid is False
        and particle_system_enabled is False
        and not sampling_api_present
        and all_active
        and all_hidden
    )
    if result["verified"] is not True:
        raise RuntimeError(
            "legacy_particle_graph_isolation_failed:"
            + json.dumps(result, sort_keys=True, ensure_ascii=True)
        )
    return result


def _normalized_particle_set_physics_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": value["path"],
        "applied_schemas": value["applied_schemas"],
        "attributes": {
            name: item
            for name, item in value["attributes"].items()
            if name not in ("physxParticle:selfCollision", "physxParticle:fluid")
        },
        "relationships": {
            name: item
            for name, item in value["relationships"].items()
            if name != "physxParticle:particleSystem"
        },
    }


def _verify_shifted_particle_bounds(
    current: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    delta_z: float,
) -> None:
    if current["local"] != source["local"]:
        raise RuntimeError("particle_set_local_bounds_changed")
    for bound_name in ("min", "max"):
        expected = [
            float(source["world"][bound_name][0]),
            float(source["world"][bound_name][1]),
            float(source["world"][bound_name][2]) + float(delta_z),
        ]
        actual = [float(value) for value in current["world"][bound_name]]
        if any(
            not math.isclose(actual[index], expected[index], abs_tol=1e-12)
            for index in range(3)
        ):
            raise RuntimeError("particle_set_world_bounds_shift_mismatch")


def author_support_aligned_scene(
    stage: Any,
    *,
    contract: Mapping[str, Any],
    overlay_layer: Any,
) -> dict[str, Any]:
    from pxr import Gf, UsdGeom

    _validate_contract_hash(contract)
    if stage.GetEditTarget().GetLayer().identifier != overlay_layer.identifier:
        raise RuntimeError("support_alignment_edit_target_mismatch")
    root_layer = stage.GetRootLayer()
    root_before = root_layer.ExportToString()
    relation_before = particle_set_owner_canonical_sha256(stage)
    for name, details in contract["beakers"].items():
        parent = stage.GetPrimAtPath(details["parent_path"])
        op = _translate_op(parent)
        op.Set(Gf.Vec3d(*[float(value) for value in details["final_parent_xyz"]]))
    particle_prim = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    particle_xform = UsdGeom.Xformable(particle_prim)
    if particle_xform.GetOrderedXformOps():
        raise RuntimeError("particle_set_existing_xform_ops_not_supported")
    particle_op = particle_xform.AddTranslateOp(
        UsdGeom.XformOp.PrecisionDouble, "supportAligned"
    )
    particle_op.Set(
        Gf.Vec3d(0.0, 0.0, float(contract["particle_set"]["delta_z"]))
    )
    _author_legacy_particle_graph_isolation(stage, overlay_layer)
    _set_world_contract_attributes(stage.GetPrimAtPath("/World"), contract)
    if root_layer.ExportToString() != root_before:
        raise RuntimeError("support_alignment_source_root_mutated")
    verified = verify_support_aligned_scene(stage, contract=contract)
    if verified["particle_set_owner_canonical_sha256"] != relation_before:
        raise RuntimeError("particle_set_owner_relation_changed")
    return {
        **verified,
        "overlay_layer_identifier": overlay_layer.identifier,
        "particle_set_owner_beaker_path": PARTICLE_SET_OWNER_PATH,
        "particle_set_delta_z": float(contract["particle_set"]["delta_z"]),
    }


def verify_support_aligned_scene(
    stage: Any,
    *,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    from pxr import UsdGeom

    _validate_contract_hash(contract)
    support = _support_signature(stage)
    if support["support_signature_sha256"] != contract["support"][
        "support_signature_sha256"
    ]:
        raise RuntimeError("support_signature_changed")
    beaker_results = {}
    for name, details in contract["beakers"].items():
        parent = stage.GetPrimAtPath(details["parent_path"])
        translation = [float(value) for value in _translate_op(parent).Get()]
        expected_translation = [float(value) for value in details["final_parent_xyz"]]
        if any(
            not math.isclose(
                translation[index], expected_translation[index], abs_tol=1e-12
            )
            for index in range(3)
        ):
            raise RuntimeError(f"support_aligned_parent_transform_mismatch:{name}")
        bbox = world_bbox(stage, details["parent_path"])
        contact_gap = float(bbox["min"][2]) - float(
            contract["support"]["bbox"]["max"][2]
        )
        expected_gap = float(contract["support_clearance_m"])
        if not math.isclose(
            contact_gap,
            expected_gap,
            rel_tol=0.0,
            abs_tol=float(contract["contact_tolerance_m"]),
        ):
            raise RuntimeError(f"support_aligned_contact_gap_mismatch:{name}")
        beaker_results[name] = {
            "parent_path": details["parent_path"],
            "mesh_path": details["mesh_path"],
            "parent_xyz": translation,
            "bbox": bbox,
            "contact_gap_m": contact_gap,
            "contact_verified": True,
        }
    particle_prim = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    ops = UsdGeom.Xformable(particle_prim).GetOrderedXformOps()
    if len(ops) != 1 or ops[0].GetOpName() != "xformOp:translate:supportAligned":
        raise RuntimeError("particle_set_support_aligned_xform_invalid")
    particle_delta = [float(value) for value in ops[0].Get()]
    expected_delta = float(contract["beakers"]["beaker2"]["delta_z"])
    if (
        not math.isclose(particle_delta[0], 0.0, abs_tol=1e-12)
        or not math.isclose(particle_delta[1], 0.0, abs_tol=1e-12)
        or not math.isclose(particle_delta[2], expected_delta, abs_tol=1e-12)
    ):
        raise RuntimeError("particle_set_owner_relation_changed:delta_mismatch")
    if _particle_points_sha256(stage) != contract["particle_set"][
        "point_array_sha256"
    ]:
        raise RuntimeError("particle_set_point_array_changed")
    relation = particle_set_owner_canonical_sha256(stage)
    if relation != contract["particle_set"]["owner_canonical_sha256_before"]:
        raise RuntimeError("particle_set_owner_relation_changed")
    authority = snapshot_scene_authority(stage)
    source_authority = contract["source_authority_snapshot"]
    for key in (
        "mesh_geometry",
        "mesh_material_bindings",
        "particle_points_sha256",
    ):
        if authority[key] != source_authority[key]:
            raise RuntimeError(f"support_aligned_authority_changed:{key}")
    for path in ("/World/beaker1/mesh", "/World/beaker2/mesh", SUPPORT_PRIM_PATH):
        if authority["physics_contract"][path] != source_authority[
            "physics_contract"
        ][path]:
            raise RuntimeError(f"support_aligned_authority_changed:physics:{path}")
    if _normalized_particle_set_physics_contract(
        authority["physics_contract"][PARTICLE_SET_PATH]
    ) != _normalized_particle_set_physics_contract(
        source_authority["physics_contract"][PARTICLE_SET_PATH]
    ):
        raise RuntimeError("support_aligned_authority_changed:particle_set_physics")
    _verify_shifted_particle_bounds(
        particle_set_bounds(stage),
        contract["legacy_particle_graph"]["source_particle_set_bounds"],
        delta_z=expected_delta,
    )
    legacy_isolation = _legacy_particle_graph_isolation(stage)
    world = stage.GetPrimAtPath("/World")
    expected_attrs = {
        "labutopia:supportAlignedLayoutVersion": contract["contract_version"],
        "labutopia:layoutSemantics": contract["layout_semantics"],
        "labutopia:exactExpertEpisodeLayout": False,
        "labutopia:supportAlignedSourceContractSha256": contract[
            "support_aligned_source_contract_sha256"
        ],
        "labutopia:particleSetOwnerBeakerPath": PARTICLE_SET_OWNER_PATH,
    }
    for name, expected in expected_attrs.items():
        attr = world.GetAttribute(name)
        if not attr or attr.Get() != expected:
            raise RuntimeError(f"support_aligned_metadata_mismatch:{name}")
    return {
        "support_alignment_verified": True,
        "layout_semantics": LAYOUT_SEMANTICS,
        "exact_expert_episode_layout": False,
        "beakers": beaker_results,
        "particle_set_owner_beaker_path": PARTICLE_SET_OWNER_PATH,
        "particle_set_delta_z": particle_delta[2],
        "particle_set_owner_canonical_sha256": relation,
        "legacy_particle_graph_isolation": legacy_isolation,
        "support_aligned_source_contract_sha256": contract[
            "support_aligned_source_contract_sha256"
        ],
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def verify_support_entry_layer_order(
    entry_layer: Any,
    *,
    overlay_basename: str = OVERLAY_BASENAME,
) -> dict[str, Any]:
    paths = [str(path) for path in entry_layer.subLayerPaths]
    if (
        len(paths) != 2
        or paths[0] != overlay_basename
        or paths.count(overlay_basename) != 1
    ):
        raise RuntimeError("support_overlay_layer_order_invalid")
    return {
        "verified": True,
        "support_overlay_sublayer_index": 0,
        "support_overlay_sublayer": paths[0],
        "localized_source_sublayer": paths[1],
    }


def build_support_aligned_entry(
    *,
    source_path: str | os.PathLike[str],
    config_path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
) -> dict[str, Any]:
    from pxr import Sdf, Usd

    source = Path(source_path).expanduser().resolve()
    config = Path(config_path).expanduser().resolve()
    output = Path(out_dir).expanduser().resolve()
    if output.exists():
        raise ValueError(f"output_directory_already_exists:{output}")
    if not source.is_file():
        raise FileNotFoundError(f"source_usd_missing:{source}")
    source_sha = _sha256_file(source)
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            f"source_usd_sha256_mismatch:{source_sha}!={EXPECTED_SOURCE_SHA256}"
        )
    config_contract = load_config_midpoint_contract(config)
    stage = Usd.Stage.Open(str(source), Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError("source_stage_open_failed")
    source_root = stage.GetRootLayer()
    source_root_before = source_root.ExportToString()
    contract = build_support_alignment_contract(
        stage,
        config_contract=config_contract,
        source_usd_sha256=source_sha,
    )
    temp = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temp.mkdir(parents=True, exist_ok=False)
    try:
        overlay_path = temp / OVERLAY_BASENAME
        entry_path = temp / ENTRY_BASENAME
        manifest_path = temp / MANIFEST_BASENAME
        overlay = begin_support_alignment_layer(stage, overlay_path)
        authored = author_support_aligned_scene(
            stage, contract=contract, overlay_layer=overlay
        )
        if not overlay.Save():
            raise RuntimeError("support_alignment_overlay_save_failed")
        if source_root.ExportToString() != source_root_before or source_root.dirty:
            raise RuntimeError("support_alignment_source_root_changed")
        entry_layer = Sdf.Layer.CreateNew(str(entry_path))
        if entry_layer is None:
            raise RuntimeError("support_alignment_entry_create_failed")
        entry_layer.defaultPrim = "World"
        entry_layer.subLayerPaths = [
            OVERLAY_BASENAME,
            os.path.relpath(source, temp).replace(os.sep, "/"),
        ]
        entry_layer_order = verify_support_entry_layer_order(entry_layer)
        if not entry_layer.Save():
            raise RuntimeError("support_alignment_entry_save_failed")
        reopened = Usd.Stage.Open(str(entry_path), Usd.Stage.LoadAll)
        if reopened is None:
            raise RuntimeError("support_alignment_entry_reopen_failed")
        reopened_verification = verify_support_aligned_scene(
            reopened, contract=contract
        )
        final_entry = output / ENTRY_BASENAME
        final_overlay = output / OVERLAY_BASENAME
        final_manifest = output / MANIFEST_BASENAME
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "manifest_type": "level1_pour_support_aligned_source",
            "layout_semantics": LAYOUT_SEMANTICS,
            "exact_expert_episode_layout": False,
            "expert_episode_id": None,
            "reset_z_from_config_m": 0.87,
            "support_alignment_is_static_authoring": True,
            "old_physics_authority_applies_to_support_aligned_stage": False,
            "source_usd_path": str(source),
            "source_usd_sha256": source_sha,
            "localized_source_usd_path": str(source),
            "localized_source_usd_sha256": source_sha,
            "config_path": str(config),
            "config_sha256": config_contract["config_sha256"],
            "builder_script_path": str(Path(__file__).resolve()),
            "builder_script_sha256": _sha256_file(__file__),
            "entry_usd_path": str(final_entry),
            "entry_usd_sha256": _sha256_file(entry_path),
            "support_entry_root_usd_path": str(final_entry),
            "support_entry_root_usd_sha256": _sha256_file(entry_path),
            "overlay_usd_path": str(final_overlay),
            "overlay_usd_sha256": _sha256_file(overlay_path),
            "support_overlay_usd_path": str(final_overlay),
            "support_overlay_usd_sha256": _sha256_file(overlay_path),
            "manifest_path": str(final_manifest),
            "support_alignment_contract": contract,
            "support_alignment_verified": True,
            "authoring_verification": authored,
            "plain_reopen_verification": reopened_verification,
            "entry_layer_order_verification": entry_layer_order,
            "claim_boundary": contract["claim_boundary"],
        }
        manifest["manifest_payload_sha256"] = canonical_json_sha256_v1(manifest)
        _write_json(manifest_path, manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        os.rename(temp, output)
        final_reopened = Usd.Stage.Open(str(final_entry), Usd.Stage.LoadAll)
        if final_reopened is None:
            raise RuntimeError("support_alignment_final_entry_reopen_failed")
        verify_support_aligned_scene(final_reopened, contract=contract)
        return manifest
    except BaseException:
        if temp.exists():
            shutil.rmtree(temp)
        raise


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE_PATH))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--out-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = build_support_aligned_entry(
        source_path=args.source,
        config_path=args.config,
        out_dir=args.out_dir,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
