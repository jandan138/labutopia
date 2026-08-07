#!/usr/bin/env python3
"""Build the immutable v1 scene packet used by fluid performance runs.

Run this script with a Python environment that owns its USD/pxr stack.  It
extracts authored particle positions and collision proxies once; per-frame
benchmarks consume the resulting NPZ and do not use USD as a state bridge.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_benchmark_contract import (  # noqa: E402
    EXPECTED_OBSERVATION_COUNT,
    EXPECTED_PARTICLE_COUNT,
    INTEGRATION_DT_S,
    LOGICAL_DT_S,
    PACKET_SCHEMA,
    SUBSTEPS_PER_OBSERVATION,
    canonical_json_sha256,
    row_transform_points,
    sha256_file,
)


DEFAULT_SCENE = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval"
    / "lab_001_level1_pour_interndata_liquid_v1.usda"
)
DEFAULT_OBSERVATIONS = (
    REPO_ROOT
    / "outputs/collect/2026.07.15/20.15.27_Level1_pour_online_fluid_v2"
    / "online_fluid_evidence/observations.jsonl"
)
DEFAULT_CONFIG = REPO_ROOT / "config/level1_pour_online_fluid_v2.yaml"
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
)
PARTICLE_PATH = "/World/InternDataParityFluid/Particles"
SOURCE_PATH = "/World/beaker2"
TARGET_PATH = "/World/beaker1"
WRAPPER_NAME = "FluidSafeWrapperCanonical"
TABLE_PATH = "/World/table"


def _require_attr(prim: Any, name: str) -> Any:
    attribute = prim.GetAttribute(name)
    if not attribute or not attribute.HasAuthoredValueOpinion():
        raise ValueError(f"usd_attribute_missing:{prim.GetPath()}:{name}")
    value = attribute.Get()
    if value is None:
        raise ValueError(f"usd_attribute_empty:{prim.GetPath()}:{name}")
    return value


def _matrix_array(matrix: Any) -> np.ndarray:
    value = np.asarray([[float(item) for item in row] for row in matrix], dtype=np.float64)
    if value.shape != (4, 4) or not np.isfinite(value).all():
        raise ValueError("usd_matrix_invalid")
    return value


def _pose_scale_xyzw(matrix: Any, Gf: Any) -> tuple[np.ndarray, np.ndarray]:
    transform = Gf.Transform(matrix)
    translation = transform.GetTranslation()
    rotation = transform.GetRotation().GetQuat()
    imaginary = rotation.GetImaginary()
    scale = transform.GetScale()
    pose = np.asarray(
        [
            float(translation[0]),
            float(translation[1]),
            float(translation[2]),
            float(imaginary[0]),
            float(imaginary[1]),
            float(imaginary[2]),
            float(rotation.GetReal()),
        ],
        dtype=np.float64,
    )
    scale_array = np.abs(
        np.asarray([float(scale[0]), float(scale[1]), float(scale[2])], dtype=np.float64)
    )
    if not np.isfinite(pose).all() or not np.isfinite(scale_array).all():
        raise ValueError("usd_transform_components_nonfinite")
    quaternion_norm = float(np.linalg.norm(pose[3:]))
    if not math.isclose(quaternion_norm, 1.0, abs_tol=1.0e-5):
        raise ValueError(f"usd_quaternion_not_unit:{quaternion_norm}")
    return pose, scale_array


def _pose_matrix_xyzw_gf(pose: np.ndarray, Gf: Any) -> Any:
    value = np.asarray(pose, dtype=np.float64)
    if value.shape != (7,) or not np.isfinite(value).all():
        raise ValueError("pose_matrix_xyzw_invalid")
    quaternion = Gf.Quatd(
        float(value[6]),
        float(value[3]),
        float(value[4]),
        float(value[5]),
    )
    matrix = Gf.Matrix4d(1.0)
    matrix.SetRotate(quaternion)
    matrix.SetTranslateOnly(
        Gf.Vec3d(float(value[0]), float(value[1]), float(value[2]))
    )
    return matrix


def _load_source_poses(path: Path) -> tuple[np.ndarray, list[dict[str, Any]]]:
    poses: list[list[float]] = []
    provenance: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            document = json.loads(line)
            record = document.get("record")
            if not isinstance(record, dict):
                raise ValueError(f"observation_record_missing:{line_number}")
            index = record.get("observation_index")
            if index != len(poses):
                raise ValueError(
                    "observation_index_not_contiguous:"
                    f"expected={len(poses)}:actual={index}"
                )
            model_pose = record.get("model_state_pose")
            if not isinstance(model_pose, dict):
                raise ValueError(f"model_state_pose_missing:{index}")
            position = model_pose.get("object_position")
            quaternion = model_pose.get("object_quaternion_xyzw")
            pose = np.asarray([*(position or []), *(quaternion or [])], dtype=np.float64)
            if pose.shape != (7,) or not np.isfinite(pose).all():
                raise ValueError(f"model_state_pose_invalid:{index}")
            if not math.isclose(float(np.linalg.norm(pose[3:])), 1.0, abs_tol=1.0e-5):
                raise ValueError(f"model_state_quaternion_invalid:{index}")
            poses.append(pose.tolist())
            provenance.append(
                {
                    "observation_index": int(index),
                    "position_sha256": record.get("position_sha256"),
                    "frame_identity": record.get("frame_identity"),
                }
            )
    result = np.asarray(poses, dtype=np.float64)
    if result.shape != (EXPECTED_OBSERVATION_COUNT, 7):
        raise ValueError(
            "observation_pose_count_mismatch:"
            f"expected={EXPECTED_OBSERVATION_COUNT}:actual={result.shape}"
        )
    return result, provenance


def _extract_wrapper(
    stage: Any,
    xform_cache: Any,
    *,
    body_path: str,
    Usd: Any,
    UsdGeom: Any,
    Gf: Any,
    source_actor_world: Any | None = None,
) -> dict[str, Any]:
    body = stage.GetPrimAtPath(body_path)
    wrapper = stage.GetPrimAtPath(f"{body_path}/{WRAPPER_NAME}")
    if not body or not wrapper:
        raise ValueError(f"wrapper_missing:{body_path}")
    prim_world = xform_cache.GetLocalToWorldTransform(body)
    body_world = (
        source_actor_world
        if body_path == SOURCE_PATH and source_actor_world is not None
        else prim_world
    )
    body_world_inverse = body_world.GetInverse()
    wrapper_world = xform_cache.GetLocalToWorldTransform(wrapper)
    wrapper_relative = wrapper_world * body_world_inverse

    box_poses: list[np.ndarray] = []
    box_half_extents: list[np.ndarray] = []
    box_paths: list[str] = []
    for prim in Usd.PrimRange(wrapper):
        if not prim.IsA(UsdGeom.Cube):
            continue
        fluid_safe = prim.GetAttribute("labutopia:fluidSafeWrapper")
        collision_enabled = prim.GetAttribute("physics:collisionEnabled")
        if (
            not fluid_safe
            or fluid_safe.Get() is not True
            or not collision_enabled
            or collision_enabled.Get() is not True
        ):
            continue
        world = xform_cache.GetLocalToWorldTransform(prim)
        selected = world * body_world_inverse if body_path == SOURCE_PATH else world
        pose, scale = _pose_scale_xyzw(selected, Gf)
        size = float(UsdGeom.Cube(prim).GetSizeAttr().Get())
        half_extents = 0.5 * size * scale
        if np.any(half_extents <= 0.0):
            raise ValueError(f"wrapper_box_extent_invalid:{prim.GetPath()}")
        box_poses.append(pose)
        box_half_extents.append(half_extents)
        box_paths.append(str(prim.GetPath()))

    expected_count = int(_require_attr(wrapper, "labutopia:colliderCount"))
    if len(box_poses) != expected_count:
        raise ValueError(
            "wrapper_collider_count_mismatch:"
            f"path={body_path}:expected={expected_count}:actual={len(box_poses)}"
        )
    frame_matrix = (
        _matrix_array(wrapper_relative)
        if body_path == SOURCE_PATH
        else _matrix_array(wrapper_world)
    )
    return {
        "box_poses": np.asarray(box_poses, dtype=np.float64),
        "box_half_extents": np.asarray(box_half_extents, dtype=np.float64),
        "box_paths": box_paths,
        "frame_matrix": frame_matrix,
        "interior_radius_m": float(_require_attr(wrapper, "labutopia:panelInnerRadius")),
        "floor_m": float(_require_attr(wrapper, "labutopia:wallFloorCanonicalZ")),
        "rim_m": float(_require_attr(wrapper, "labutopia:wallRimCanonicalZ")),
        "body_world_matrix": _matrix_array(body_world),
    }


def _table_top_z(stage: Any, xform_cache: Any, Usd: Any, UsdGeom: Any) -> float:
    table = stage.GetPrimAtPath(TABLE_PATH)
    if not table:
        raise ValueError("table_prim_missing")
    purposes = [
        UsdGeom.Tokens.default_,
        UsdGeom.Tokens.render,
        UsdGeom.Tokens.proxy,
    ]
    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), purposes)
    aligned = bbox_cache.ComputeWorldBound(table).ComputeAlignedRange()
    result = float(aligned.GetMax()[2])
    if not math.isfinite(result):
        raise ValueError("table_top_z_nonfinite")
    return result


def _layer_closure(stage: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for layer in stage.GetUsedLayers():
        real_path = str(layer.realPath or "")
        if not real_path:
            continue
        path = Path(real_path).resolve(strict=True)
        records.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    records.sort(key=lambda record: record["path"])
    if not records:
        raise ValueError("usd_layer_closure_empty")
    return records


def build_packet(
    *,
    scene_path: Path,
    observations_path: Path,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    from pxr import Gf, Usd, UsdGeom

    scene_path = scene_path.resolve(strict=True)
    observations_path = observations_path.resolve(strict=True)
    config_path = config_path.resolve(strict=True)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"packet_output_not_empty:{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    stage = Usd.Stage.Open(str(scene_path))
    if stage is None:
        raise RuntimeError("usd_stage_open_failed")
    xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())

    particle_prim = stage.GetPrimAtPath(PARTICLE_PATH)
    if not particle_prim or not particle_prim.IsA(UsdGeom.Points):
        raise ValueError("authored_particle_prim_missing")
    initial_positions = np.asarray(
        UsdGeom.Points(particle_prim).GetPointsAttr().Get(),
        dtype=np.float64,
    )
    if initial_positions.shape != (EXPECTED_PARTICLE_COUNT, 3):
        raise ValueError(
            "authored_particle_count_mismatch:"
            f"expected={EXPECTED_PARTICLE_COUNT}:actual={initial_positions.shape}"
        )
    if not np.isfinite(initial_positions).all():
        raise ValueError("authored_particle_positions_nonfinite")

    source_poses, observation_provenance = _load_source_poses(observations_path)
    source_actor_world = _pose_matrix_xyzw_gf(source_poses[0], Gf)
    source = _extract_wrapper(
        stage,
        xform_cache,
        body_path=SOURCE_PATH,
        Usd=Usd,
        UsdGeom=UsdGeom,
        Gf=Gf,
        source_actor_world=source_actor_world,
    )
    target = _extract_wrapper(
        stage,
        xform_cache,
        body_path=TARGET_PATH,
        Usd=Usd,
        UsdGeom=UsdGeom,
        Gf=Gf,
    )
    initial_source_local = row_transform_points(
        initial_positions,
        np.linalg.inv(source["frame_matrix"] @ source["body_world_matrix"]),
    )
    initial_fluid_min_z = float(initial_source_local[:, 2].min())
    initial_fluid_max_z = float(initial_source_local[:, 2].max())
    fill_height = max(0.001, initial_fluid_max_z - initial_fluid_min_z)
    estimated_volume = (
        math.pi
        * float(source["interior_radius_m"]) ** 2
        * fill_height
    )
    particle_mass_kg = 1000.0 * estimated_volume / EXPECTED_PARTICLE_COUNT

    arrays_path = output_dir / "fluid_benchmark_packet_v2.npz"
    arrays_tmp = output_dir / ".fluid_benchmark_packet_v2.npz.tmp"
    with arrays_tmp.open("wb") as stream:
        np.savez_compressed(
            stream,
            initial_particle_positions=initial_positions.astype(np.float32),
            source_poses_xyzw=source_poses.astype(np.float64),
            source_box_poses_xyzw=source["box_poses"].astype(np.float64),
            source_box_half_extents=source["box_half_extents"].astype(np.float64),
            target_box_poses_xyzw=target["box_poses"].astype(np.float64),
            target_box_half_extents=target["box_half_extents"].astype(np.float64),
            source_frame_local_matrix=source["frame_matrix"].astype(np.float64),
            target_frame_world_matrix=target["frame_matrix"].astype(np.float64),
        )
    os.replace(arrays_tmp, arrays_path)

    inputs = {
        "scene": {
            "path": str(scene_path),
            "sha256": sha256_file(scene_path),
        },
        "observations": {
            "path": str(observations_path),
            "sha256": sha256_file(observations_path),
        },
        "config": {
            "path": str(config_path),
            "sha256": sha256_file(config_path),
        },
        "usd_layer_closure": _layer_closure(stage),
    }
    manifest: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "claim_boundary": (
            "experimental_cross_runtime_scene_packet_for_controlled_performance;"
            "synthetic_kinematic_source_vessel_only"
        ),
        "particle_count": EXPECTED_PARTICLE_COUNT,
        "observation_count": EXPECTED_OBSERVATION_COUNT,
        "source_box_count": int(source["box_poses"].shape[0]),
        "target_box_count": int(target["box_poses"].shape[0]),
        "timing": {
            "logical_dt_s": LOGICAL_DT_S,
            "integration_dt_s": INTEGRATION_DT_S,
            "substeps_per_observation": SUBSTEPS_PER_OBSERVATION,
            "source_pose_policy": (
                "observation_i_pose_applied_before_four_integration_substeps"
            ),
        },
        "fluid": {
            "density_kg_m3": 1000.0,
            "estimated_initial_volume_m3": estimated_volume,
            "estimated_fill_height_m": fill_height,
            "initial_fluid_min_canonical_z_m": initial_fluid_min_z,
            "initial_fluid_max_canonical_z_m": initial_fluid_max_z,
            "particle_mass_kg": particle_mass_kg,
            "particle_radius_m": 0.0015,
        },
        "frames": {
            "source": {
                "interior_radius_m": source["interior_radius_m"],
                "floor_m": source["floor_m"],
                "rim_m": source["rim_m"],
            },
            "target": {
                "interior_radius_m": target["interior_radius_m"],
                "floor_m": target["floor_m"],
                "rim_m": target["rim_m"],
            },
            "table_top_z_m": _table_top_z(stage, xform_cache, Usd, UsdGeom),
        },
        "paths": {
            "particle": PARTICLE_PATH,
            "source": SOURCE_PATH,
            "target": TARGET_PATH,
            "table": TABLE_PATH,
        },
        "arrays": {
            "path": arrays_path.name,
            "sha256": sha256_file(arrays_path),
            "dtype_policy": "positions_float32_transforms_float64",
        },
        "inputs": inputs,
        "source_box_paths": source["box_paths"],
        "target_box_paths": target["box_paths"],
        "observation_provenance_sha256": canonical_json_sha256(
            observation_provenance
        ),
    }
    manifest["content_sha256"] = canonical_json_sha256(manifest)
    manifest_path = output_dir / "fluid_benchmark_packet_v2.json"
    manifest_tmp = output_dir / ".fluid_benchmark_packet_v2.json.tmp"
    manifest_tmp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(manifest_tmp, manifest_path)
    return {
        "manifest_path": str(manifest_path),
        "arrays_path": str(arrays_path),
        "manifest_sha256": sha256_file(manifest_path),
        "arrays_sha256": sha256_file(arrays_path),
        "particle_count": EXPECTED_PARTICLE_COUNT,
        "observation_count": EXPECTED_OBSERVATION_COUNT,
        "source_box_count": manifest["source_box_count"],
        "target_box_count": manifest["target_box_count"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument(
        "--observations",
        type=Path,
        default=DEFAULT_OBSERVATIONS,
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_packet(
        scene_path=args.scene,
        observations_path=args.observations,
        config_path=args.config,
        output_dir=args.output_dir,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
