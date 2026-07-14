#!/usr/bin/env python3
"""Render a verified derived-surface cache in Isaac Sim without physics steps."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "interndata_kinematic_pour_probe_final_inset_20260714"
)
DEFAULT_SCENE_PATH = RUN_ROOT / "authored_scene.usda"
DEFAULT_CACHE_DIR = REPO_ROOT / "outputs/interndata_surface_replay_20260714/mesh_cache"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs/interndata_surface_replay_20260714/render"

SURFACE_PATH = "/World/InternDataSurfaceReplay"
SOURCE_BEAKER_PATH = "/World/beaker2"
PARTICLE_SYSTEM_PATH = "/World/InternDataParityFluid/ParticleSystem"
LEGACY_LIQUID_PATHS = [
    "/World/InternDataParityFluid/Particles",
    "/World/InternDataParityFluid/VisualParticles",
    "/World/ParticleSet",
    "/World/fluid",
]
CAMERA_PATHS = {
    "context": "/World/InternDataParityCamera",
    "closeup": "/World/InternDataParityCloseupCamera",
}
MATERIAL_PATH = "/World/Looks/InternDataDerivedSurfaceWater"
EXPECTED_SCENE_SHA256 = "e0c020fe44536406253a9bb14a89f0d2d2b6d415abd369e780e03ef0d1db347d"
EXPECTED_TRACE_SHA256 = "0321dee981f3ca82e62018352ef66ca12772f75dda35f20330ef2124b552dfb7"
EXPECTED_RUNTIME_SUMMARY_SHA256 = (
    "91e2c65dfcd96841e018975d772b4c2ace081d802fc4789d28b5251d7f2a1333"
)


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
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


def build_replay_contract() -> dict[str, Any]:
    selected_steps = list(range(0, 691, 10))
    return {
        "schema_version": 1,
        "surface_path": SURFACE_PATH,
        "source_beaker_path": SOURCE_BEAKER_PATH,
        "particle_system_path": PARTICLE_SYSTEM_PATH,
        "camera_paths": dict(CAMERA_PATHS),
        "legacy_liquid_paths": list(LEGACY_LIQUID_PATHS),
        "selected_steps": selected_steps,
        "frame_count": len(selected_steps),
        "width": 960,
        "height": 540,
        "video_fps": 15,
        "physics_trace_hz": 30,
        "frame_stride": 10,
        "playback_speed_multiplier": 5.0,
        "physics_step_calls": 0,
        "dynamic_authority": "mesh_cache_plus_replay_runner",
        "usd_delivery": "static_final_state_snapshot",
    }


def build_surface_material_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "material_path": MATERIAL_PATH,
        "shader_backend": "UsdPreviewSurface",
        "diffuse_color": [0.46, 0.82, 0.96],
        "emissive_color": [0.01, 0.025, 0.035],
        "metallic": 0.0,
        "roughness": 0.06,
        "opacity": 0.06,
        "ior": 1.333,
        "fallback_allowed": False,
        "reference": "accepted_interndata_point_video_material",
    }


def build_closeup_camera_contract() -> dict[str, Any]:
    return {
        "path": CAMERA_PATHS["closeup"],
        "eye": [0.1645, -0.6469, 1.0200],
        "target": [0.2785233518810611, -0.22147663301350906, 0.8899941121566101],
        "up": [0.0, 0.0, 1.0],
        "focal_length": 22.0,
        "horizontal_aperture": 24.0,
        "vertical_aperture": 16.0,
        "critical_rim_projection_margin_px": 31.7,
        "reference": "target_local_azimuth_minus_150_degrees",
    }


def build_render_settings_contract() -> dict[str, Any]:
    return {
        "renderer": "RayTracedLighting",
        "width": 960,
        "height": 540,
        "warmup_rt_subframes": 8,
        "capture_rt_subframes": 8,
        "settings": {
            "/rtx/ambientOcclusion/enabled": False,
            "/rtx/shadows/enabled": True,
            "/rtx/shadows/sampleCount": 4,
            "/rtx/translucency/maxRefractionBounces": 12,
        },
        "lighting": {
            "distant_intensity": 950.0,
            "distant_rotation_xyz": [55.0, 0.0, 35.0],
            "dome_intensity": 400.0,
        },
    }


def configure_presentation_closeup_camera(stage: Any) -> dict[str, Any]:
    from pxr import Gf, UsdGeom

    contract = build_closeup_camera_contract()
    camera = UsdGeom.Camera.Define(stage, contract["path"])
    transform = Gf.Matrix4d(1).SetLookAt(
        Gf.Vec3d(*contract["eye"]),
        Gf.Vec3d(*contract["target"]),
        Gf.Vec3d(*contract["up"]),
    ).GetInverse()
    xformable = UsdGeom.Xformable(camera.GetPrim())
    xformable.ClearXformOpOrder()
    xformable.AddTransformOp().Set(transform)
    camera.CreateFocalLengthAttr().Set(contract["focal_length"])
    camera.CreateHorizontalApertureAttr().Set(contract["horizontal_aperture"])
    camera.CreateVerticalApertureAttr().Set(contract["vertical_aperture"])
    camera.CreateClippingRangeAttr().Set(Gf.Vec2f(0.01, 100.0))
    actual = xformable.GetLocalTransformation()
    matches = actual == transform and math.isclose(
        float(camera.GetFocalLengthAttr().Get()), contract["focal_length"], abs_tol=1e-6
    )
    if not matches:
        raise RuntimeError("closeup_camera_readback_mismatch")
    return {**contract, "readback_matches_contract": True}


def _matrix4d(value: Sequence[Sequence[float]]) -> Any:
    from pxr import Gf

    array = np.asarray(value, dtype=np.float64)
    if array.shape != (4, 4) or not np.isfinite(array).all():
        raise ValueError("source_parent_matrix_invalid")
    return Gf.Matrix4d(*array.tolist())


def _matrix_to_numpy(value: Any) -> np.ndarray:
    return np.asarray(
        [[float(value[row][column]) for column in range(4)] for row in range(4)],
        dtype=np.float64,
    )


def update_surface_mesh(
    stage: Any,
    vertices: np.ndarray,
    faces: np.ndarray,
    normals: np.ndarray,
) -> dict[str, Any]:
    from pxr import Gf, UsdGeom, Vt

    vertices = np.ascontiguousarray(vertices, dtype=np.float32)
    faces = np.ascontiguousarray(faces, dtype=np.int32)
    normals = np.ascontiguousarray(normals, dtype=np.float32)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) == 0:
        raise ValueError("surface_vertices_shape_invalid")
    if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
        raise ValueError("surface_faces_shape_invalid")
    if normals.shape != vertices.shape:
        raise ValueError("surface_normals_shape_invalid")
    if not np.isfinite(vertices).all() or not np.isfinite(normals).all():
        raise ValueError("surface_arrays_nonfinite")
    if np.any(faces < 0) or np.any(faces >= len(vertices)):
        raise ValueError("surface_faces_out_of_range")

    mesh = UsdGeom.Mesh.Define(stage, SURFACE_PATH)
    xformable = UsdGeom.Xformable(mesh.GetPrim())
    xformable.ClearXformOpOrder()
    mesh.CreatePointsAttr().Set(
        Vt.Vec3fArray([Gf.Vec3f(*point) for point in vertices.tolist()])
    )
    mesh.CreateFaceVertexCountsAttr().Set(Vt.IntArray([3] * len(faces)))
    mesh.CreateFaceVertexIndicesAttr().Set(Vt.IntArray(faces.reshape(-1).tolist()))
    mesh.CreateNormalsAttr().Set(
        Vt.Vec3fArray([Gf.Vec3f(*normal) for normal in normals.tolist()])
    )
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    mesh.CreateExtentAttr().Set(
        Vt.Vec3fArray(
            [
                Gf.Vec3f(*[float(value) for value in minimum]),
                Gf.Vec3f(*[float(value) for value in maximum]),
            ]
        )
    )
    mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
    mesh.CreateOrientationAttr().Set(UsdGeom.Tokens.rightHanded)
    mesh.CreateDoubleSidedAttr().Set(False)
    mesh.CreatePurposeAttr().Set(UsdGeom.Tokens.render)
    mesh.CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)
    local = xformable.GetLocalTransformation()
    identity = _matrix_to_numpy(local)
    identity_ok = bool(np.allclose(identity, np.eye(4), atol=1e-12, rtol=0.0))
    if not identity_ok:
        raise RuntimeError("surface_mesh_transform_not_identity")
    return {
        "path": SURFACE_PATH,
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        "bounds_min_world_m": minimum.astype(float).tolist(),
        "bounds_max_world_m": maximum.astype(float).tolist(),
        "world_space_vertices": True,
        "identity_transform": True,
        "topology_updated": True,
        "normals_interpolation": "vertex",
        "subdivision_scheme": "none",
    }


def _visibility(stage: Any, path: str) -> str | None:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid() or not prim.IsA(UsdGeom.Imageable):
        return None
    return str(UsdGeom.Imageable(prim).ComputeVisibility())


def configure_surface_visual_authority(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    hidden_paths: list[str] = []
    for path in LEGACY_LIQUID_PATHS:
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsValid() and prim.IsA(UsdGeom.Imageable):
            UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            hidden_paths.append(path)
    system = stage.GetPrimAtPath(PARTICLE_SYSTEM_PATH)
    isosurface_disabled = False
    if system and system.IsValid():
        attribute = system.GetAttribute("physxParticleIsosurface:isosurfaceEnabled")
        if attribute:
            attribute.Set(False)
            isosurface_disabled = attribute.Get() is False
    generated_paths: list[str] = []
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if path == SURFACE_PATH or "isosurface" not in path.lower():
            continue
        if prim.IsA(UsdGeom.Imageable):
            UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
            generated_paths.append(path)
    surface = stage.GetPrimAtPath(SURFACE_PATH)
    if not surface or not surface.IsValid() or not surface.IsA(UsdGeom.Mesh):
        raise ValueError("derived_surface_mesh_missing")
    UsdGeom.Imageable(surface).CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)
    candidate_paths = [SURFACE_PATH, *LEGACY_LIQUID_PATHS, *generated_paths]
    visible = sorted(
        path for path in set(candidate_paths) if _visibility(stage, path) == "inherited"
    )
    sole = visible == [SURFACE_PATH]
    if not sole:
        raise RuntimeError(f"multiple_visible_liquid_representations:{visible}")
    return {
        "hidden_legacy_paths": sorted(hidden_paths),
        "hidden_generated_isosurface_paths": sorted(set(generated_paths)),
        "particle_isosurface_disabled": isosurface_disabled,
        "visible_liquid_paths": visible,
        "sole_visible_liquid_representation": True,
    }


def author_surface_material(stage: Any) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    contract = build_surface_material_contract()
    if not stage.GetPrimAtPath("/World/Looks"):
        UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, MATERIAL_PATH)
    shader = UsdShade.Shader.Define(stage, f"{MATERIAL_PATH}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*contract["diffuse_color"])
    )
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*contract["emissive_color"])
    )
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(contract["metallic"])
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(contract["roughness"])
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(contract["opacity"])
    shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(contract["ior"])
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    surface = stage.GetPrimAtPath(SURFACE_PATH)
    if not surface or not surface.IsValid():
        raise ValueError("surface_missing_before_material_binding")
    UsdShade.MaterialBindingAPI.Apply(surface).Bind(material)
    readback = {
        "shader_backend": str(shader.GetIdAttr().Get()),
        "diffuse_color": [float(value) for value in shader.GetInput("diffuseColor").Get()],
        "emissive_color": [float(value) for value in shader.GetInput("emissiveColor").Get()],
        "metallic": float(shader.GetInput("metallic").Get()),
        "roughness": float(shader.GetInput("roughness").Get()),
        "opacity": float(shader.GetInput("opacity").Get()),
        "ior": float(shader.GetInput("ior").Get()),
        "material_path": str(
            UsdShade.MaterialBindingAPI(surface).GetDirectBinding().GetMaterialPath()
        ),
    }
    matches = (
        readback["shader_backend"] == contract["shader_backend"]
        and np.allclose(readback["diffuse_color"], contract["diffuse_color"])
        and np.allclose(readback["emissive_color"], contract["emissive_color"])
        and math.isclose(
            readback["metallic"], contract["metallic"], abs_tol=1e-6
        )
        and math.isclose(
            readback["roughness"], contract["roughness"], abs_tol=1e-6
        )
        and math.isclose(
            readback["opacity"], contract["opacity"], abs_tol=1e-6
        )
        and math.isclose(readback["ior"], contract["ior"], abs_tol=1e-6)
        and readback["material_path"] == MATERIAL_PATH
    )
    if not matches:
        raise RuntimeError(f"surface_material_readback_mismatch:{readback}")
    return {
        **contract,
        "readback": readback,
        "readback_matches_contract": True,
        "fallback_used": False,
        "material_contract_sha256": _json_sha256(contract),
    }


def apply_source_parent_matrix(
    stage: Any, matrix: Sequence[Sequence[float]]
) -> dict[str, Any]:
    from pxr import UsdGeom

    expected = _matrix4d(matrix)
    prim = stage.GetPrimAtPath(SOURCE_BEAKER_PATH)
    if not prim or not prim.IsValid():
        raise ValueError(f"source_beaker_missing:{SOURCE_BEAKER_PATH}")
    xformable = UsdGeom.Xformable(prim)
    operations = xformable.GetOrderedXformOps()
    transform_op = next(
        (
            operation
            for operation in operations
            if operation.GetOpType() == UsdGeom.XformOp.TypeTransform
        ),
        None,
    )
    if transform_op is None:
        xformable.ClearXformOpOrder()
        transform_op = xformable.AddTransformOp()
    transform_op.Set(expected)
    actual = xformable.GetLocalTransformation()
    error = float(
        np.max(np.abs(_matrix_to_numpy(actual) - _matrix_to_numpy(expected)))
    )
    if error > 1e-12:
        raise RuntimeError(f"source_parent_matrix_readback_mismatch:{error}")
    return {
        "path": SOURCE_BEAKER_PATH,
        "max_abs_error": error,
        "readback_matches_trace": True,
    }


def validate_capture_mapping(
    mappings: Sequence[Mapping[str, Any]],
    *,
    expected_steps: Sequence[int] | None = None,
) -> dict[str, Any]:
    expected = list(
        build_replay_contract()["selected_steps"]
        if expected_steps is None
        else expected_steps
    )
    if len(mappings) != len(expected):
        raise ValueError(
            f"capture_frame_count_mismatch:expected={len(expected)}:actual={len(mappings)}"
        )
    frame_indices = [int(item["frame_index"]) for item in mappings]
    steps = [int(item["step_index"]) for item in mappings]
    if frame_indices != list(range(len(expected))) or steps != expected:
        raise ValueError("capture_step_mapping_mismatch")
    for key in ("context_path", "closeup_path"):
        paths = [str(item[key]) for item in mappings]
        if len(set(paths)) != len(paths):
            raise ValueError(f"capture_paths_not_unique:{key}")
    geometry_hashes = [str(item["cache_geometry_sha256"]) for item in mappings]
    if any(len(value) != 64 for value in geometry_hashes):
        raise ValueError("capture_geometry_hash_invalid")
    return {
        "valid": True,
        "frame_count": len(mappings),
        "selected_steps": steps,
        "warmup_excluded": True,
        "paths_unique": True,
    }


def build_ffmpeg_command(
    *, frame_pattern: str | Path, output_path: str | Path, fps: int
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(int(fps)),
        "-i",
        str(frame_pattern),
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _canonical_mesh_sha256(
    vertices: np.ndarray, faces: np.ndarray, normals: np.ndarray
) -> str:
    digest = hashlib.sha256()
    arrays = (
        ("vertices", np.ascontiguousarray(vertices, dtype=np.dtype("<f4"))),
        ("faces", np.ascontiguousarray(faces, dtype=np.dtype("<i4"))),
        ("normals", np.ascontiguousarray(normals, dtype=np.dtype("<f4"))),
    )
    for name, array in arrays:
        digest.update(name.encode("ascii") + b"\0")
        digest.update(array.dtype.str.encode("ascii") + b"\0")
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
        digest.update(b"\0")
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _load_mesh_archive(cache_dir: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    relative = Path(str(entry["mesh_path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("cache_mesh_path_not_relative")
    path = (cache_dir / relative).resolve(strict=True)
    if cache_dir.resolve() not in path.parents:
        raise ValueError("cache_mesh_path_outside_cache")
    actual_file_hash = _sha256_file(path)
    if actual_file_hash != entry["mesh_file_sha256"]:
        raise ValueError(f"cache_mesh_file_hash_mismatch:{entry['step_index']}")
    with np.load(path, allow_pickle=False) as archive:
        if set(archive.files) != {"vertices", "faces", "normals"}:
            raise ValueError("cache_mesh_members_invalid")
        vertices = np.ascontiguousarray(archive["vertices"], dtype=np.float32)
        faces = np.ascontiguousarray(archive["faces"], dtype=np.int32)
        normals = np.ascontiguousarray(archive["normals"], dtype=np.float32)
    geometry_hash = _canonical_mesh_sha256(vertices, faces, normals)
    if geometry_hash != entry["geometry_sha256"]:
        raise ValueError(f"cache_geometry_hash_mismatch:{entry['step_index']}")
    return {
        "vertices": vertices,
        "faces": faces,
        "normals": normals,
        "path": str(path),
        "file_sha256": actual_file_hash,
        "geometry_sha256": geometry_hash,
    }


def load_cache_manifest(cache_dir: str | Path) -> dict[str, Any]:
    root = Path(cache_dir).resolve(strict=True)
    path = root / "mesh_cache_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != "interndata_derived_surface_mesh_cache":
        raise ValueError("cache_manifest_type_invalid")
    expected_inputs = {
        "trace": EXPECTED_TRACE_SHA256,
        "scene": EXPECTED_SCENE_SHA256,
        "runtime_summary": EXPECTED_RUNTIME_SUMMARY_SHA256,
    }
    for name, expected_hash in expected_inputs.items():
        if manifest.get("inputs", {}).get(name, {}).get("sha256") != expected_hash:
            raise ValueError(f"cache_input_hash_mismatch:{name}")
    frames = manifest.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("cache_frames_missing")
    steps = [int(entry["step_index"]) for entry in frames]
    if steps != sorted(set(steps)) or any(step % 10 != 0 for step in steps):
        raise ValueError("cache_selected_steps_invalid")
    if manifest.get("selected_steps") != steps or manifest.get("frame_count") != len(frames):
        raise ValueError("cache_frame_manifest_mismatch")
    if manifest.get("component_filter") != "none":
        raise ValueError("cache_component_filter_not_none")
    for entry in frames:
        _load_mesh_archive(root, entry)
    return {
        **manifest,
        "cache_dir": str(root),
        "manifest_path": str(path),
        "manifest_sha256": _sha256_file(path),
    }


def _normalize_rgb_frame(data: Any, *, width: int, height: int) -> np.ndarray:
    array = np.asarray(data)
    if array.ndim != 3 or array.shape[0] != height or array.shape[1] != width or array.shape[2] < 3:
        raise ValueError(f"rgb_capture_shape_invalid:{list(array.shape)}")
    if array.dtype != np.uint8:
        array = np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=255.0, neginf=0.0)
        if array.size and float(array.max()) <= 1.0:
            array *= 255.0
        array = np.clip(array, 0.0, 255.0).astype(np.uint8)
    return array[:, :, :3]


def _render_barrier(rep: Any, timeline: Any, *, rt_subframes: int) -> dict[str, Any]:
    before = float(timeline.get_current_time())
    rep.orchestrator.step(
        rt_subframes=int(rt_subframes),
        pause_timeline=True,
        delta_time=0.0,
    )
    rep.orchestrator.wait_until_complete()
    after = float(timeline.get_current_time())
    if not math.isclose(before, after, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("render_barrier_advanced_timeline")
    return {
        "timeline_before": before,
        "timeline_after": after,
        "timeline_unchanged": True,
        "physics_step_calls": 0,
        "rt_subframes": int(rt_subframes),
    }


def _encode_video(frame_dir: Path, output_path: Path, fps: int) -> dict[str, Any]:
    command = build_ffmpeg_command(
        frame_pattern=frame_dir / "frame_%04d.png",
        output_path=output_path,
        fps=fps,
    )
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg_failed:{completed.stderr.strip()}")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames",
            "-of",
            "json",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    return {
        "path": str(output_path),
        "sha256": _sha256_file(output_path),
        "size_bytes": output_path.stat().st_size,
        "codec_name": stream.get("codec_name"),
        "pixel_format": stream.get("pix_fmt"),
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "frame_rate": stream.get("r_frame_rate"),
        "decoded_frame_count": int(stream.get("nb_read_frames", 0)),
    }


def _prepare_overlay(source_scene: Path, overlay_path: Path) -> None:
    from pxr import Sdf

    layer = Sdf.Layer.CreateNew(str(overlay_path))
    if layer is None:
        raise RuntimeError(f"overlay_create_failed:{overlay_path}")
    layer.subLayerPaths = [str(source_scene)]
    layer.Save()


def _run_isaac(args: argparse.Namespace) -> dict[str, Any]:
    from isaacsim import SimulationApp

    source_scene = Path(args.usd).resolve(strict=True)
    if _sha256_file(source_scene) != EXPECTED_SCENE_SHA256:
        raise ValueError("source_scene_sha256_mismatch")
    cache = load_cache_manifest(args.cache_dir)
    cache_root = Path(cache["cache_dir"])
    output_dir = Path(args.out_dir).resolve()
    if output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"render_output_exists:{output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    overlay_path = output_dir / "surface_replay_final.usda"

    app = SimulationApp(
        {
            "headless": bool(args.headless),
            "width": int(args.width),
            "height": int(args.height),
            "renderer": "RayTracedLighting",
        }
    )
    resources: dict[str, dict[str, Any]] = {}
    summary: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "interndata_derived_surface_replay",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "technical_valid": False,
        "visual_verdict": None,
        "physics_rerun": False,
        "physics_step_calls": 0,
    }
    try:
        import carb
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd
        from PIL import Image
        from pxr import UsdGeom

        _prepare_overlay(source_scene, overlay_path)
        context = omni.usd.get_context()
        opened = bool(context.open_stage(str(overlay_path)))
        stage = context.get_stage()
        updates = 0
        while stage is None and updates < 60:
            app.update()
            stage = context.get_stage()
            updates += 1
        if not opened or stage is None:
            raise RuntimeError("surface_replay_stage_open_failed")
        stage.SetEditTarget(stage.GetRootLayer())
        timeline = omni.timeline.get_timeline_interface()
        timeline.stop()
        render_settings_contract = build_render_settings_contract()
        settings = carb.settings.get_settings()
        for path, value in render_settings_contract["settings"].items():
            settings.set(path, value)
        closeup_camera = configure_presentation_closeup_camera(stage)
        for name, path in CAMERA_PATHS.items():
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid() or not prim.IsA(UsdGeom.Camera):
                raise ValueError(f"replay_camera_missing:{name}:{path}")
            product = rep.create.render_product(path, (int(args.width), int(args.height)))
            annotator = rep.AnnotatorRegistry.get_annotator("rgb")
            annotator.attach(product)
            resources[name] = {"render_product": product, "annotator": annotator}

        mappings: list[dict[str, Any]] = []
        frame_diagnostics: list[dict[str, Any]] = []
        material_info: dict[str, Any] | None = None
        authority_info: dict[str, Any] | None = None
        for frame_index, entry in enumerate(cache["frames"]):
            mesh = _load_mesh_archive(cache_root, entry)
            pose = apply_source_parent_matrix(stage, entry["source_parent_matrix"])
            topology = update_surface_mesh(
                stage, mesh["vertices"], mesh["faces"], mesh["normals"]
            )
            if material_info is None:
                material_info = author_surface_material(stage)
            authority_info = configure_surface_visual_authority(stage)
            warmup = None
            if frame_index == 0:
                warmup = _render_barrier(
                    rep,
                    timeline,
                    rt_subframes=max(1, int(args.camera_warmup_subframes)),
                )
            barrier = _render_barrier(
                rep, timeline, rt_subframes=max(1, int(args.rt_subframes))
            )
            mapping = {
                "frame_index": frame_index,
                "step_index": int(entry["step_index"]),
                "cache_geometry_sha256": mesh["geometry_sha256"],
            }
            camera_diagnostics: dict[str, Any] = {}
            for name, resource in resources.items():
                rgb = _normalize_rgb_frame(
                    resource["annotator"].get_data(),
                    width=int(args.width),
                    height=int(args.height),
                )
                mean = float(rgb.mean())
                std = float(rgb.std())
                if mean < 5.0 or std < 2.0:
                    raise RuntimeError(
                        f"rgb_capture_near_black_or_flat:{name}:mean={mean}:std={std}"
                    )
                relative = Path("frames") / name / f"frame_{frame_index:04d}.png"
                destination = output_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(rgb, mode="RGB").save(destination)
                mapping[f"{name}_path"] = relative.as_posix()
                camera_diagnostics[name] = {
                    "path": str(destination),
                    "sha256": _sha256_file(destination),
                    "mean": mean,
                    "std": std,
                    "shape": list(rgb.shape),
                }
            mappings.append(mapping)
            frame_diagnostics.append(
                {
                    "frame_index": frame_index,
                    "step_index": int(entry["step_index"]),
                    "source_pose": pose,
                    "surface_topology": topology,
                    "visual_authority": authority_info,
                    "warmup": warmup,
                    "render_barrier": barrier,
                    "cameras": camera_diagnostics,
                }
            )
        capture_mapping = validate_capture_mapping(
            mappings, expected_steps=cache["selected_steps"]
        )
        stage.GetRootLayer().Save()
        videos = {
            name: _encode_video(
                output_dir / "frames" / name,
                output_dir / f"{name}.mp4",
                int(args.video_fps),
            )
            for name in CAMERA_PATHS
        }
        for name, video in videos.items():
            if (
                video["codec_name"] != "h264"
                or video["pixel_format"] != "yuv420p"
                or video["width"] != int(args.width)
                or video["height"] != int(args.height)
                or video["decoded_frame_count"] != len(cache["frames"])
            ):
                raise RuntimeError(f"encoded_video_contract_invalid:{name}:{video}")
        summary.update(
            {
                "technical_valid": True,
                "replay_contract": {
                    **build_replay_contract(),
                    "selected_steps": cache["selected_steps"],
                    "frame_count": len(cache["frames"]),
                    "width": int(args.width),
                    "height": int(args.height),
                    "video_fps": int(args.video_fps),
                },
                "source_scene": {
                    "path": str(source_scene),
                    "sha256": _sha256_file(source_scene),
                },
                "cache": {
                    "path": cache["cache_dir"],
                    "manifest_path": cache["manifest_path"],
                    "manifest_sha256": cache["manifest_sha256"],
                    "reconstruction_contract_sha256": cache[
                        "reconstruction_contract_sha256"
                    ],
                    "frame_count": cache["frame_count"],
                },
                "material": material_info,
                "closeup_camera": closeup_camera,
                "render_settings": render_settings_contract,
                "visual_authority": authority_info,
                "capture_mapping": capture_mapping,
                "frames": frame_diagnostics,
                "videos": videos,
                "final_snapshot": {
                    "path": str(overlay_path),
                    "sha256": _sha256_file(overlay_path),
                    "dynamic_animation": False,
                },
                "playback_disclosure": "stride_10_of_30hz_trace_at_15fps_equals_5x_speed",
            }
        )
        return summary
    except Exception as exc:
        summary["error"] = repr(exc)
        raise
    finally:
        cleanup_failures: dict[str, str] = {}
        for name, resource in resources.items():
            try:
                resource["annotator"].detach()
            except Exception as exc:
                cleanup_failures[f"{name}:detach"] = repr(exc)
            try:
                resource["render_product"].destroy()
            except Exception as exc:
                cleanup_failures[f"{name}:destroy"] = repr(exc)
        summary["replicator_cleanup_failures"] = cleanup_failures
        output_dir = Path(args.out_dir).resolve()
        if output_dir.exists():
            summary_path = output_dir / "surface_replay_manifest.json"
            summary_path.write_text(
                json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
        app.close()


def build_arg_parser() -> argparse.ArgumentParser:
    contract = build_replay_contract()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", default=str(DEFAULT_SCENE_PATH))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--width", type=int, default=contract["width"])
    parser.add_argument("--height", type=int, default=contract["height"])
    parser.add_argument("--video-fps", type=int, default=contract["video_fps"])
    parser.add_argument("--rt-subframes", type=int, default=8)
    parser.add_argument("--camera-warmup-subframes", type=int, default=8)
    parser.add_argument(
        "--headless", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = _run_isaac(args)
    print(
        json.dumps(
            {
                "technical_valid": summary["technical_valid"],
                "output_dir": str(Path(args.out_dir).resolve()),
                "frame_count": summary["capture_mapping"]["frame_count"],
                "videos": summary["videos"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
