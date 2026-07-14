#!/usr/bin/env python3
"""Capture one presentation-only top water film in the accepted real beaker."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import traceback
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AUTHORITY_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_008"
    / "matrix_decision_authority/final_closure/aggregate/cells"
    / "A_0_AO0_RT4_CONTROL/OMNI_REF_DISPLAY_FILL"
)
SOURCE_STAGE = AUTHORITY_ROOT / "OMNI_REF_DISPLAY_FILL_static.usda"
OUTPUT_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_derived_water_film_probe_20260713"
)

PROBE_ID = "real_beaker_derived_water_film_probe_20260713"
SUCCESS_STATUS = "CAPTURED_DERIVED_WATER_FILM_PENDING_VISUAL_REVIEW"
FAILURE_STATUS = "INVALID_DERIVED_WATER_FILM_PROBE"

SOURCE_SURFACE_PATH = "/World/CompletedPBD/PresentationSurface"
FILM_PATH = "/World/CompletedPBD/DerivedWaterFilm"
FILM_MATERIAL_PATH = "/World/Looks/DerivedWaterFilmMaterial"
FILM_SHADER_PATH = f"{FILM_MATERIAL_PATH}/PreviewSurface"

EXPECTED_SOURCE_SHA256 = (
    "c05ec299524cb0d895412ee0c5a1efe7d45c93f7838e512ebd90b0b7bbcc511a"
)
EXPECTED_PROXY_GEOMETRY_SHA256 = (
    "8905803d5177e9d2a194720f942c7558847046dffce6b084bc8b66aa36f4a70d"
)
EXPECTED_PHYSICAL_FRAME = 600
EXPECTED_SOURCE_POINT_COUNT = 386
EXPECTED_SOURCE_FACE_COUNT = 480
TOP_RING_START = 289
TOP_RING_COUNT = 96
TOP_CENTER_INDEX = 385

FILM_MATERIAL_INPUTS = {
    "diffuseColor": [0.16, 0.52, 0.62],
    "emissiveColor": [0.0, 0.0, 0.0],
    "opacity": 0.72,
    "roughness": 0.06,
    "metallic": 0.0,
    "ior": 1.333,
}

CAMERA_PATHS = {
    "source_beaker_closeup": "/World/Beaker2CloseupNativeMaterialCamera",
    "pair_context": "/World/BeakerPairContextCamera",
}
CAPTURE_RESOLUTION = (960, 540)
RT_SUBFRAMES = 4
WARMUP_UPDATES = 8

CONTROL_RENDER_SETTINGS = {
    "/rtx/ambientOcclusion/enabled": False,
    "/rtx/ambientOcclusion/rayLength": 5.0,
    "/rtx/ambientOcclusion/minSamples": 8,
    "/rtx/ambientOcclusion/maxSamples": 16,
    "/rtx/ambientOcclusion/denoiserMode": 2,
    "/rtx/shadows/enabled": True,
    "/rtx/shadows/sampleCount": 4,
    "/rtx/translucency/maxRefractionBounces": 12,
}

ZERO_STEP_CHECKPOINT_NAMES = (
    "before_treatment",
    "after_treatment",
    "after_warmup",
    "after_discarded_capture",
    "after_final_capture",
    "after_cleanup",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _point(value: Sequence[float], *, label: str) -> list[float]:
    if len(value) != 3:
        raise ValueError(f"{label}_shape_invalid")
    result = [float(component) for component in value]
    if not all(math.isfinite(component) for component in result):
        raise ValueError(f"{label}_nonfinite")
    return result


def _cross(left: Sequence[float], right: Sequence[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _subtract(left: Sequence[float], right: Sequence[float]) -> list[float]:
    return [left[index] - right[index] for index in range(3)]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return math.fsum(left[index] * right[index] for index in range(3))


def extract_top_film_geometry(
    *,
    points: Sequence[Sequence[float]],
    normals: Sequence[Sequence[float]],
    face_counts: Sequence[int],
    face_indices: Sequence[int],
) -> dict[str, Any]:
    if len(points) != EXPECTED_SOURCE_POINT_COUNT or len(normals) != len(points):
        raise ValueError("source_topology_mismatch:point_count")
    if len(face_counts) != EXPECTED_SOURCE_FACE_COUNT:
        raise ValueError("source_topology_mismatch:face_count")

    source_ring_indices = list(
        range(TOP_RING_START, TOP_RING_START + TOP_RING_COUNT)
    )
    expected_top_indices: list[int] = []
    for offset in range(TOP_RING_COUNT):
        expected_top_indices.extend(
            (
                TOP_CENTER_INDEX,
                source_ring_indices[offset],
                source_ring_indices[(offset + 1) % TOP_RING_COUNT],
            )
        )
    top_face_offset = sum(int(count) for count in face_counts[:-TOP_RING_COUNT])
    actual_top_counts = [int(value) for value in face_counts[-TOP_RING_COUNT:]]
    actual_top_indices = [int(value) for value in face_indices[top_face_offset:]]
    if (
        actual_top_counts != [3] * TOP_RING_COUNT
        or actual_top_indices != expected_top_indices
    ):
        raise ValueError("source_topology_mismatch:top_cap")

    source_points = [_point(value, label=f"source_point_{index}") for index, value in enumerate(points)]
    source_normals = [_point(value, label=f"source_normal_{index}") for index, value in enumerate(normals)]
    film_points = [source_points[index] for index in source_ring_indices]
    film_points.append(source_points[TOP_CENTER_INDEX])
    film_normals = [source_normals[index] for index in source_ring_indices]
    film_normals.append(source_normals[TOP_CENTER_INDEX])
    center_local_index = TOP_RING_COUNT
    film_face_indices: list[int] = []
    total_area = 0.0
    non_degenerate = True
    upward_wound = True
    reference_normal = film_normals[center_local_index]
    for index in range(TOP_RING_COUNT):
        following = (index + 1) % TOP_RING_COUNT
        film_face_indices.extend((center_local_index, index, following))
        first = _subtract(film_points[index], film_points[center_local_index])
        second = _subtract(
            film_points[following], film_points[center_local_index]
        )
        cross = _cross(first, second)
        magnitude = math.sqrt(_dot(cross, cross))
        area = 0.5 * magnitude
        total_area += area
        non_degenerate = non_degenerate and area > 1e-12
        upward_wound = upward_wound and _dot(cross, reference_normal) > 0.0
    if not non_degenerate:
        raise ValueError("film_triangle_degenerate")
    if not upward_wound:
        raise ValueError("film_triangle_winding_invalid")

    geometry_payload = {
        "points": film_points,
        "normals": film_normals,
        "face_vertex_counts": [3] * TOP_RING_COUNT,
        "face_vertex_indices": film_face_indices,
    }
    geometry_sha256 = _canonical_sha256(geometry_payload)
    return {
        "source_ring_indices": source_ring_indices,
        "source_center_index": TOP_CENTER_INDEX,
        "presentation_kind": "surface_mesh",
        "vertex_count": len(film_points),
        "face_count": TOP_RING_COUNT,
        "positions_world": film_points,
        "normals_world": film_normals,
        "face_vertex_counts": geometry_payload["face_vertex_counts"],
        "face_vertex_indices": geometry_payload["face_vertex_indices"],
        "all_triangles_non_degenerate": True,
        "all_triangles_upward_wound": True,
        "total_area_m2": total_area,
        "geometry_sha256": geometry_sha256,
        "canonical_mesh_sha256": geometry_sha256,
        "presentation_only": True,
        "physics_schema_allowed": False,
        "physical_volume_parity_claim_allowed": False,
        "free_surface_shape_claim_allowed": False,
        "fluid_dynamics_claim_allowed": False,
    }


def _source_stage_contract(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(SOURCE_SURFACE_PATH)
    mesh = UsdGeom.Mesh(prim)
    if not prim or not mesh:
        raise ValueError("source_presentation_surface_missing")
    geometry_sha256 = prim.GetAttribute("labutopia:proxyGeometrySha256").Get()
    physical_frame = prim.GetAttribute("labutopia:physicalTraceFrameIndex").Get()
    points = mesh.GetPointsAttr().Get() or []
    face_counts = mesh.GetFaceVertexCountsAttr().Get() or []
    if (
        geometry_sha256 != EXPECTED_PROXY_GEOMETRY_SHA256
        or physical_frame != EXPECTED_PHYSICAL_FRAME
        or len(points) != EXPECTED_SOURCE_POINT_COUNT
        or len(face_counts) != EXPECTED_SOURCE_FACE_COUNT
    ):
        raise ValueError("fixed_source_surface_contract_mismatch")
    for role, path in CAMERA_PATHS.items():
        camera = stage.GetPrimAtPath(path)
        if not camera or not camera.IsA(UsdGeom.Camera):
            raise ValueError(f"fixed_camera_missing:{role}:{path}")
    return {
        "proxy_geometry_sha256": str(geometry_sha256),
        "physical_trace_frame_index": int(physical_frame),
        "source_point_count": len(points),
        "source_face_count": len(face_counts),
        "camera_paths": dict(CAMERA_PATHS),
    }


def verify_fixed_inputs(source_path: Path = SOURCE_STAGE) -> dict[str, Any]:
    from pxr import Usd

    source = source_path.resolve(strict=True)
    source_sha256 = _sha256_file(source)
    if source_sha256 != EXPECTED_SOURCE_SHA256:
        raise ValueError("fixed_source_sha256_mismatch")
    stage = Usd.Stage.Open(str(source), Usd.Stage.LoadNone)
    if not stage:
        raise RuntimeError("fixed_source_open_failed")
    return {
        "source_path": str(source),
        "source_sha256": source_sha256,
        **_source_stage_contract(stage),
    }


def _layer_spec_paths(layer: Any) -> tuple[str, ...]:
    from pxr import Sdf

    paths: list[str] = []
    layer.Traverse(Sdf.Path.absoluteRootPath, lambda path: paths.append(str(path)))
    return tuple(sorted(paths))


def film_geometry_signature(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(FILM_PATH)
    mesh = UsdGeom.Mesh(prim)
    if not prim or not mesh:
        raise ValueError("derived_water_film_missing")
    payload = {
        "points": [[float(value) for value in point] for point in (mesh.GetPointsAttr().Get() or [])],
        "normals": [[float(value) for value in normal] for normal in (mesh.GetNormalsAttr().Get() or [])],
        "face_vertex_counts": [int(value) for value in (mesh.GetFaceVertexCountsAttr().Get() or [])],
        "face_vertex_indices": [int(value) for value in (mesh.GetFaceVertexIndicesAttr().Get() or [])],
    }
    return {
        "vertex_count": len(payload["points"]),
        "face_count": len(payload["face_vertex_counts"]),
        "geometry_sha256": _canonical_sha256(payload),
    }


def apply_derived_water_film_treatment(stage: Any) -> dict[str, Any]:
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade
    from tools.labutopia_fluid import omniglass_reference

    source_contract = _source_stage_contract(stage)
    source_prim = stage.GetPrimAtPath(SOURCE_SURFACE_PATH)
    source_mesh = UsdGeom.Mesh(source_prim)
    geometry = extract_top_film_geometry(
        points=source_mesh.GetPointsAttr().Get() or [],
        normals=source_mesh.GetNormalsAttr().Get() or [],
        face_counts=source_mesh.GetFaceVertexCountsAttr().Get() or [],
        face_indices=source_mesh.GetFaceVertexIndicesAttr().Get() or [],
    )
    if stage.GetPrimAtPath(FILM_PATH):
        raise ValueError("derived_water_film_path_already_exists")

    layer = Sdf.Layer.CreateAnonymous("derived_water_film_treatment.usda")
    stage.GetSessionLayer().subLayerPaths.insert(0, layer.identifier)
    stage.SetEditTarget(Usd.EditTarget(layer))
    UsdGeom.Imageable(source_prim).MakeInvisible()

    if not stage.GetPrimAtPath("/World/Looks"):
        UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, FILM_MATERIAL_PATH)
    shader = UsdShade.Shader.Define(stage, FILM_SHADER_PATH)
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*FILM_MATERIAL_INPUTS["diffuseColor"])
    )
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*FILM_MATERIAL_INPUTS["emissiveColor"])
    )
    for name in ("opacity", "roughness", "metallic", "ior"):
        shader.CreateInput(name, Sdf.ValueTypeNames.Float).Set(
            FILM_MATERIAL_INPUTS[name]
        )
    material.CreateSurfaceOutput().ConnectToSource(
        shader.ConnectableAPI(), "surface"
    )
    film_prim = omniglass_reference.author_presentation_surface(
        stage,
        path=FILM_PATH,
        surface_frame=geometry,
        material_path=FILM_MATERIAL_PATH,
    )
    film_prim.CreateAttribute(
        "labutopia:sourceProxyGeometrySha256",
        Sdf.ValueTypeNames.String,
        custom=True,
    ).Set(EXPECTED_PROXY_GEOMETRY_SHA256)
    film_prim.CreateAttribute(
        "labutopia:derivedFilmGeometrySha256",
        Sdf.ValueTypeNames.String,
        custom=True,
    ).Set(geometry["geometry_sha256"])

    authored_paths = _layer_spec_paths(layer)
    layer_adds_physx_specs = any("physx" in path.lower() for path in authored_paths)
    material_readback, _ = UsdShade.MaterialBindingAPI(
        film_prim
    ).ComputeBoundMaterial()
    valid = bool(
        not layer_adds_physx_specs
        and str(material_readback.GetPath()) == FILM_MATERIAL_PATH
        and not any("physx" in token.lower() for token in film_prim.GetAppliedSchemas())
        and not any(
            relationship.GetName().lower().startswith("physx")
            for relationship in film_prim.GetRelationships()
        )
        and UsdGeom.Imageable(source_prim).ComputeVisibility()
        == UsdGeom.Tokens.invisible
        and film_geometry_signature(stage)["geometry_sha256"]
        == geometry["geometry_sha256"]
    )
    if not valid:
        raise RuntimeError("derived_water_film_treatment_invalid")
    return {
        "layer": layer,
        "verified": True,
        "source_contract": source_contract,
        "geometry": geometry,
        "authored_spec_paths": list(authored_paths),
        "layer_adds_physx_specs": False,
        "material_path": FILM_MATERIAL_PATH,
        "material_inputs": dict(FILM_MATERIAL_INPUTS),
        "old_proxy_hidden": True,
    }


def validate_zero_step_checkpoints(
    checkpoints: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    valid = tuple(checkpoints) == ZERO_STEP_CHECKPOINT_NAMES and all(
        isinstance(checkpoints[name], Mapping)
        and checkpoints[name].get("physics_step_events") == 0
        and checkpoints[name].get("timeline_stopped") is True
        for name in ZERO_STEP_CHECKPOINT_NAMES
    )
    if not valid:
        raise RuntimeError("zero_step_checkpoint_invalid")
    return {
        "verified": True,
        "physics_steps_executed": 0,
        "checkpoints": {name: dict(checkpoints[name]) for name in checkpoints},
    }


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def validate_capture_contract(capture: Mapping[str, Any]) -> dict[str, Any]:
    frames = capture.get("frames")
    valid = isinstance(frames, Mapping) and tuple(frames) == tuple(CAMERA_PATHS)
    if valid:
        for role in CAMERA_PATHS:
            frame = frames[role]
            shape = frame.get("shape") if isinstance(frame, Mapping) else None
            valid = bool(
                isinstance(shape, list)
                and shape[:2] == [CAPTURE_RESOLUTION[1], CAPTURE_RESOLUTION[0]]
                and len(shape) == 3
                and shape[2] >= 3
                and frame.get("dtype") == "uint8"
                and isinstance(frame.get("mean"), (int, float))
                and float(frame["mean"]) >= 5.0
                and isinstance(frame.get("std"), (int, float))
                and float(frame["std"]) >= 2.0
                and isinstance(frame.get("path"), str)
                and frame["path"]
                and _valid_sha256(frame.get("sha256"))
            )
            if not valid:
                break
    if not valid:
        raise ValueError("capture_contract_invalid")
    return {
        "verified": True,
        "camera_roles": list(CAMERA_PATHS),
        "resolution": list(CAPTURE_RESOLUTION),
        "frames": {role: dict(frames[role]) for role in CAMERA_PATHS},
    }


def record_replicator_cleanup(
    runtime_context: dict[str, Any],
    cleanup: Mapping[str, Any],
) -> dict[str, Any]:
    contract = dict(cleanup)
    runtime_context["replicator_cleanup"] = contract
    if contract.get("cleanup_complete") is not True or contract.get(
        "cleanup_failures"
    ):
        raise RuntimeError(
            "replicator_resource_cleanup_failed:"
            + json.dumps(contract, sort_keys=True, separators=(",", ":"))
        )
    return contract


def build_failure_manifest(exc: BaseException) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "probe_id": PROBE_ID,
        "status": FAILURE_STATUS,
        "technically_valid": False,
        "fatal_error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(limit=30),
        },
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(path)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, allow_nan=False, indent=2, sort_keys=True)
            stream.write("\n")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _render_startup_arguments() -> list[str]:
    arguments = []
    for path, value in CONTROL_RENDER_SETTINGS.items():
        encoded = "true" if value is True else "false" if value is False else str(value)
        arguments.append(f"--{path}={encoded}")
    return arguments


def _create_wrapper(source: Path, wrapper: Path) -> dict[str, Any]:
    from pxr import Sdf

    layer = Sdf.Layer.CreateNew(str(wrapper))
    if layer is None:
        raise RuntimeError("wrapper_create_failed")
    layer.subLayerPaths = [str(source)]
    if not layer.Save():
        raise RuntimeError("wrapper_save_failed")
    return {
        "path": str(wrapper),
        "sha256": _sha256_file(wrapper),
        "source_sublayer": str(source),
    }


def _run_runtime(source_path: Path, out_root: Path) -> dict[str, Any]:
    source = source_path.resolve(strict=True)
    if _sha256_file(source) != EXPECTED_SOURCE_SHA256:
        raise ValueError("fixed_source_sha256_mismatch")
    out_root.mkdir(parents=True, exist_ok=False)
    for argument in _render_startup_arguments():
        if argument not in sys.argv:
            sys.argv.append(argument)

    from isaacsim import SimulationApp

    app = SimulationApp(
        {
            "headless": True,
            "width": CAPTURE_RESOLUTION[0],
            "height": CAPTURE_RESOLUTION[1],
            "renderer": "RayTracedLighting",
        }
    )
    resources: dict[str, dict[str, Any]] = {}
    step_subscription: Any = None
    runtime_context: dict[str, Any] = {}
    try:
        import carb
        import omni.physx
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd
        from tools.labutopia_fluid import run_real_beaker_omniglass_replay as replay
        from tools.labutopia_fluid import run_real_beaker_preview_water_probe as preview

        settings = carb.settings.get_settings()
        settings.set_bool("/app/player/playSimulations", False)
        settings.set_bool("/omni/replicator/captureOnPlay", False)
        rep.orchestrator.set_capture_on_play(False)
        render_contract = preview.apply_and_validate_control_render_settings(
            settings,
            update_barrier=app.update,
        )

        wrapper_path = out_root / "derived_water_film_wrapper.usda"
        wrapper_contract = _create_wrapper(source, wrapper_path)
        wrapper_sha256_before = _sha256_file(wrapper_path)
        source_sha256_before = _sha256_file(source)
        timeline = omni.timeline.get_timeline_interface()
        timeline.stop()
        replay.require_stopped_timeline(timeline)
        stage = replay._open_exact_stage(
            context=omni.usd.get_context(),
            app=app,
            timeline=timeline,
            source_path=wrapper_path,
            warmup_updates=2,
        )
        fixed_inputs = {"source_path": str(source), "source_sha256": source_sha256_before, **_source_stage_contract(stage)}
        root_layer_before = stage.GetRootLayer().ExportToString()

        physics_step_count = 0

        def on_physics_step(_dt: float) -> None:
            nonlocal physics_step_count
            physics_step_count += 1

        checkpoints: dict[str, dict[str, Any]] = {}
        runtime_context["zero_step_checkpoints"] = checkpoints

        def checkpoint(name: str) -> None:
            replay.require_stopped_timeline(timeline)
            if physics_step_count != 0:
                raise RuntimeError(
                    f"zero_step_checkpoint_invalid:{name}:{physics_step_count}"
                )
            checkpoints[name] = {
                "physics_step_events": 0,
                "timeline_stopped": True,
            }

        step_subscription = omni.physx.get_physx_interface().subscribe_physics_step_events(
            on_physics_step
        )
        checkpoint("before_treatment")
        treatment = apply_derived_water_film_treatment(stage)
        treatment_layer = treatment.pop("layer")
        checkpoint("after_treatment")
        geometry_before = film_geometry_signature(stage)

        resources = preview._create_two_camera_resources(rep)
        annotators = {
            role: resource["annotator"] for role, resource in resources.items()
        }
        rep.orchestrator.preview()
        for _ in range(WARMUP_UPDATES):
            replay.require_stopped_timeline(timeline)
            app.update()
        checkpoint("after_warmup")

        with tempfile.TemporaryDirectory(
            prefix="discarded_water_film_", dir=out_root
        ) as discarded_dir:
            discarded_capture = replay.capture_static_replicator_rgbs(
                orchestrator=rep.orchestrator,
                timeline=timeline,
                annotators=annotators,
                output_paths={
                    role: Path(discarded_dir) / f"{role}.png"
                    for role in CAMERA_PATHS
                },
                width=CAPTURE_RESOLUTION[0],
                height=CAPTURE_RESOLUTION[1],
                rt_subframes=RT_SUBFRAMES,
                observed_default_time_usd_point_attributes_hash=lambda: (
                    replay.usd_observed_default_time_point_attributes_sha256(stage)
                ),
            )
            discarded_validation = validate_capture_contract(discarded_capture)
        checkpoint("after_discarded_capture")

        output_paths = {
            "source_beaker_closeup": out_root
            / "derived_water_film_source_beaker_closeup.png",
            "pair_context": out_root / "derived_water_film_pair_context.png",
        }
        capture = replay.capture_static_replicator_rgbs(
            orchestrator=rep.orchestrator,
            timeline=timeline,
            annotators=annotators,
            output_paths=output_paths,
            width=CAPTURE_RESOLUTION[0],
            height=CAPTURE_RESOLUTION[1],
            rt_subframes=RT_SUBFRAMES,
            observed_default_time_usd_point_attributes_hash=lambda: (
                replay.usd_observed_default_time_point_attributes_sha256(stage)
            ),
        )
        checkpoint("after_final_capture")
        capture_validation = validate_capture_contract(capture)

        cleanup = replay.destroy_replicator_capture_resources(resources)
        resources = {}
        cleanup = record_replicator_cleanup(runtime_context, cleanup)
        checkpoint("after_cleanup")
        zero_step_validation = validate_zero_step_checkpoints(checkpoints)
        geometry_after = film_geometry_signature(stage)
        if geometry_after != geometry_before:
            raise RuntimeError("capture_changed_film_geometry")
        source_sha256_after = _sha256_file(source)
        wrapper_sha256_after = _sha256_file(wrapper_path)
        if source_sha256_after != source_sha256_before:
            raise RuntimeError("capture_changed_source_file")
        if wrapper_sha256_after != wrapper_sha256_before:
            raise RuntimeError("capture_changed_wrapper_file")
        if stage.GetRootLayer().ExportToString() != root_layer_before:
            raise RuntimeError("capture_changed_wrapper_root_layer")

        treatment_export = out_root / "derived_water_film_treatment.usda"
        if not treatment_layer.Export(str(treatment_export)):
            raise RuntimeError("treatment_layer_export_failed")
        manifest = {
            "schema_version": 1,
            "probe_id": PROBE_ID,
            "status": SUCCESS_STATUS,
            "technically_valid": True,
            "fixed_inputs": fixed_inputs,
            "wrapper_contract": wrapper_contract,
            "treatment": treatment,
            "treatment_layer_export": {
                "path": str(treatment_export),
                "sha256": _sha256_file(treatment_export),
            },
            "film_geometry_before_capture": geometry_before,
            "film_geometry_after_capture": geometry_after,
            "render_contract": render_contract,
            "discarded_capture": {
                "discarded": True,
                "verified": discarded_validation["verified"],
                "frame_sha256": {
                    role: record["sha256"]
                    for role, record in discarded_validation["frames"].items()
                },
            },
            "capture": capture_validation,
            "replicator_cleanup": cleanup,
            "zero_step_validation": zero_step_validation,
            "source_sha256_before": source_sha256_before,
            "source_sha256_after": source_sha256_after,
            "source_unchanged": True,
            "wrapper_unchanged": True,
            "no_retry": True,
            "shutdown_contract": {
                "manifest_persisted_before_simulation_app_close": True,
                "process_exit_code_authoritative": False,
                "manifest_status_is_authoritative": True,
            },
            "claim_boundary": (
                "presentation_only_no_physical_volume_or_free_surface_claim;"
                "accepted_frame_600_particles_remain_physics_authority"
            ),
        }
        _write_json(out_root / "probe_manifest.json", manifest)
        step_subscription = None
        return manifest
    except BaseException as exc:
        if resources:
            from tools.labutopia_fluid import run_real_beaker_omniglass_replay as replay

            runtime_context["replicator_cleanup"] = (
                replay.destroy_replicator_capture_resources(resources)
            )
            resources = {}
        failure = build_failure_manifest(exc)
        if runtime_context:
            failure["runtime_context"] = runtime_context
        manifest_path = out_root / "probe_manifest.json"
        if not manifest_path.exists():
            _write_json(manifest_path, failure)
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        sys.stderr.flush()
        raise
    finally:
        step_subscription = None
        app.close()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_STAGE)
    parser.add_argument("--out-root", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = _run_runtime(args.source, args.out_root.resolve())
    except Exception:
        return 1
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
