#!/usr/bin/env python3
"""Capture one material-only PreviewSurface treatment on the accepted beaker fill."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import (  # noqa: E402
    run_colleague_native_usd_completed_pbd_step_video as native,
)
from tools.labutopia_fluid import run_real_beaker_omniglass_replay as replay  # noqa: E402


AUTHORITY_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_008"
    / "matrix_decision_authority"
)
SOURCE_STAGE = (
    AUTHORITY_ROOT
    / "final_closure/aggregate/cells/A_0_AO0_RT4_CONTROL"
    / "OMNI_REF_DISPLAY_FILL/OMNI_REF_DISPLAY_FILL_static.usda"
)
DECISION_PATH = AUTHORITY_ROOT / "matrix_decision.json"
OUTPUT_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_preview_water_material_probe_20260713"
)

PRESENTATION_SURFACE_PATH = replay.PRESENTATION_SURFACE_PATH
TREATMENT_MATERIAL_PATH = native.LIQUID_PRESENTATION_MATERIAL_PATH
CAMERA_PATHS = {
    "source_beaker_closeup": "/World/Beaker2CloseupNativeMaterialCamera",
    "pair_context": "/World/BeakerPairContextCamera",
}
CAPTURE_RESOLUTION = (960, 540)
RT_SUBFRAMES = 4
WARMUP_UPDATES = 8
EXPECTED_PHYSICAL_FRAME = 600
EXPECTED_SOURCE_SHA256 = (
    "c05ec299524cb0d895412ee0c5a1efe7d45c93f7838e512ebd90b0b7bbcc511a"
)
EXPECTED_PROXY_GEOMETRY_SHA256 = (
    "8905803d5177e9d2a194720f942c7558847046dffce6b084bc8b66aa36f4a70d"
)
EXPECTED_MATRIX_DECISION_SHA256 = (
    "0a1ae1b0de8974710deee7561509a0794b6f84dc0fab6abcdae1e8051942ea43"
)
EXPECTED_TERMINAL_STATE = "FAIL_NO_RENDER_SETTING_RECOVERY"

CONTROL_IMAGE_PATHS = {
    "source_beaker_closeup": (
        AUTHORITY_ROOT
        / "final_closure/aggregate/cells/A_0_AO0_RT4_CONTROL"
        / "OMNI_REF_DISPLAY_FILL/source_beaker_closeup_frames/frame_0600.png"
    ),
    "pair_context": (
        AUTHORITY_ROOT
        / "final_closure/aggregate/cells/A_0_AO0_RT4_CONTROL"
        / "OMNI_REF_DISPLAY_FILL/context_frames/frame_0600.png"
    ),
}
CONTROL_IMAGE_SHA256 = {
    "source_beaker_closeup": (
        "6f127941887c7f3b3175f06cfd78eadfd58b8b932305e48e20b71a72d36c8dbd"
    ),
    "pair_context": (
        "43b9b88f7f75cfc7b726b838a5efcea81ab1ea62797e291ec8af25adcbb90dec"
    ),
}

PREVIEW_WATER_INPUTS = {
    "diffuseColor": [0.74, 0.94, 1.0],
    "emissiveColor": [0.0, 0.0, 0.0],
    "opacity": 0.34,
    "roughness": 0.02,
    "metallic": 0.0,
    "ior": 1.333,
}

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

EXPECTED_TREATMENT_SPEC_PATHS = (
    "/",
    "/World",
    "/World/CompletedPBD",
    "/World/CompletedPBD/PresentationSurface",
    "/World/CompletedPBD/PresentationSurface.material:binding",
    (
        "/World/CompletedPBD/PresentationSurface.material:binding"
        "[/World/Looks/LiquidPresentationWater]"
    ),
    "/World/Looks",
    "/World/Looks/LiquidPresentationWater",
    "/World/Looks/LiquidPresentationWater.outputs:surface",
    (
        "/World/Looks/LiquidPresentationWater.outputs:surface"
        "[/World/Looks/LiquidPresentationWater/PreviewSurface.outputs:surface]"
    ),
    "/World/Looks/LiquidPresentationWater/PreviewSurface",
    "/World/Looks/LiquidPresentationWater/PreviewSurface.info:id",
    "/World/Looks/LiquidPresentationWater/PreviewSurface.inputs:diffuseColor",
    "/World/Looks/LiquidPresentationWater/PreviewSurface.inputs:emissiveColor",
    "/World/Looks/LiquidPresentationWater/PreviewSurface.inputs:ior",
    "/World/Looks/LiquidPresentationWater/PreviewSurface.inputs:metallic",
    "/World/Looks/LiquidPresentationWater/PreviewSurface.inputs:opacity",
    "/World/Looks/LiquidPresentationWater/PreviewSurface.inputs:roughness",
    "/World/Looks/LiquidPresentationWater/PreviewSurface.outputs:surface",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_usd_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("nonfinite_usd_value")
        return value
    try:
        return [_canonical_usd_value(item) for item in value]
    except TypeError:
        return str(value)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def presentation_geometry_signature(stage: Any) -> dict[str, Any]:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH)
    if not prim.IsValid() or not prim.IsA(UsdGeom.Mesh):
        raise ValueError("presentation_surface_mesh_missing")
    mesh = UsdGeom.Mesh(prim)
    payload = {
        "points": _canonical_usd_value(mesh.GetPointsAttr().Get()),
        "face_vertex_counts": _canonical_usd_value(
            mesh.GetFaceVertexCountsAttr().Get()
        ),
        "face_vertex_indices": _canonical_usd_value(
            mesh.GetFaceVertexIndicesAttr().Get()
        ),
        "normals": _canonical_usd_value(mesh.GetNormalsAttr().Get()),
        "normals_interpolation": str(mesh.GetNormalsInterpolation()),
        "local_to_world": _canonical_usd_value(
            UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(prim)
        ),
    }
    return {
        "fingerprint_sha256": _canonical_sha256(payload),
        "point_count": len(payload["points"] or []),
        "face_count": len(payload["face_vertex_counts"] or []),
        "normal_count": len(payload["normals"] or []),
    }


def validate_stage_contract(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH)
    if not prim.IsValid() or not prim.IsA(UsdGeom.Mesh):
        raise ValueError("presentation_surface_mesh_missing")
    frame = prim.GetAttribute("labutopia:physicalTraceFrameIndex").Get()
    if frame != EXPECTED_PHYSICAL_FRAME:
        raise ValueError(
            f"physical_trace_frame_mismatch:{frame}!={EXPECTED_PHYSICAL_FRAME}"
        )
    geometry_sha256 = prim.GetAttribute("labutopia:proxyGeometrySha256").Get()
    if geometry_sha256 != EXPECTED_PROXY_GEOMETRY_SHA256:
        raise ValueError("proxy_geometry_sha256_mismatch")
    for role, path in CAMERA_PATHS.items():
        camera = stage.GetPrimAtPath(path)
        if not camera.IsValid() or not camera.IsA(UsdGeom.Camera):
            raise ValueError(f"probe_camera_missing:{role}:{path}")
    return {
        "physical_trace_frame_index": int(frame),
        "proxy_geometry_sha256": str(geometry_sha256),
        "camera_paths": dict(CAMERA_PATHS),
        "presentation_geometry": presentation_geometry_signature(stage),
    }


def _layer_spec_paths(layer: Any) -> tuple[str, ...]:
    from pxr import Sdf

    paths: list[str] = []
    layer.Traverse(Sdf.Path.absoluteRootPath, lambda path: paths.append(str(path)))
    return tuple(sorted(paths))


def _read_preview_water_inputs(stage: Any) -> dict[str, Any]:
    from pxr import Sdf, UsdShade

    shader = UsdShade.Shader(
        stage.GetPrimAtPath(f"{TREATMENT_MATERIAL_PATH}/PreviewSurface")
    )
    if not shader or shader.GetIdAttr().Get() != "UsdPreviewSurface":
        raise ValueError("preview_water_shader_missing")
    result: dict[str, Any] = {}
    for name, expected in PREVIEW_WATER_INPUTS.items():
        shader_input = shader.GetInput(name)
        actual = shader_input.Get() if shader_input else None
        if isinstance(expected, list):
            actual_values = [float(value) for value in actual or []]
            if len(actual_values) != len(expected) or any(
                not math.isclose(value, target, rel_tol=0.0, abs_tol=1e-6)
                for value, target in zip(actual_values, expected)
            ):
                raise ValueError(f"preview_water_input_mismatch:{name}")
        elif actual is None or not math.isclose(
            float(actual), float(expected), rel_tol=0.0, abs_tol=1e-6
        ):
            raise ValueError(f"preview_water_input_mismatch:{name}")
        result[name] = deepcopy(expected)
    surface_output = UsdShade.Material(
        stage.GetPrimAtPath(TREATMENT_MATERIAL_PATH)
    ).GetSurfaceOutput()
    if not surface_output or not surface_output.HasConnectedSource():
        raise ValueError("preview_water_surface_output_unconnected")
    return result


def validate_preview_water_treatment(stage: Any, layer: Any) -> dict[str, Any]:
    from pxr import UsdShade

    authored_paths = _layer_spec_paths(layer)
    if authored_paths != EXPECTED_TREATMENT_SPEC_PATHS:
        raise ValueError(
            "treatment_layer_specs_mismatch:"
            f"actual={authored_paths}:expected={EXPECTED_TREATMENT_SPEC_PATHS}"
        )
    surface = stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH)
    material, _ = UsdShade.MaterialBindingAPI(surface).ComputeBoundMaterial()
    material_path = str(material.GetPath()) if material else ""
    if material_path != TREATMENT_MATERIAL_PATH:
        raise ValueError(f"treatment_material_binding_mismatch:{material_path}")
    material_inputs = _read_preview_water_inputs(stage)
    return {
        "verified": True,
        "authored_spec_paths": authored_paths,
        "effective_material_path": material_path,
        "material_inputs": material_inputs,
    }


def apply_preview_water_treatment(stage: Any) -> dict[str, Any]:
    from pxr import Sdf, Usd, UsdShade

    geometry_before = presentation_geometry_signature(stage)
    layer = Sdf.Layer.CreateAnonymous("preview_water_treatment.usda")
    stage.GetSessionLayer().subLayerPaths.insert(0, layer.identifier)
    stage.SetEditTarget(Usd.EditTarget(layer))
    native._author_presentation_water_preview_surface(stage)
    surface = stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH)
    material = UsdShade.Material(stage.GetPrimAtPath(TREATMENT_MATERIAL_PATH))
    UsdShade.MaterialBindingAPI.Apply(surface).Bind(material)
    validated = validate_preview_water_treatment(stage, layer)
    geometry_after = presentation_geometry_signature(stage)
    if geometry_after != geometry_before:
        raise RuntimeError("preview_water_treatment_changed_geometry")
    return {"layer": layer, **validated}


def apply_and_validate_control_render_settings(
    settings: Any,
    *,
    update_barrier: Any | None = None,
) -> dict[str, Any]:
    for path, value in CONTROL_RENDER_SETTINGS.items():
        if type(value) is bool:
            settings.set_bool(path, value)
        elif type(value) is int:
            settings.set_int(path, value)
        elif type(value) is float:
            settings.set_float(path, value)
        else:
            raise TypeError(f"unsupported_render_setting_type:{path}")
    if update_barrier is not None:
        update_barrier()
    for path, expected in CONTROL_RENDER_SETTINGS.items():
        actual = settings.get(path)
        matches = (
            math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-6)
            if type(expected) is float and isinstance(actual, (int, float))
            else type(actual) is type(expected) and actual == expected
        )
        if not matches:
            raise RuntimeError(
                f"control_render_setting_readback_mismatch:{path}:"
                f"actual={actual!r}:expected={expected!r}"
            )
    return {
        "registry_values": deepcopy(CONTROL_RENDER_SETTINGS),
        "rt_subframes": RT_SUBFRAMES,
        "resolution": list(CAPTURE_RESOLUTION),
        "readback_verified": True,
    }


def verify_fixed_inputs(source_path: Path) -> dict[str, Any]:
    source_path = source_path.resolve(strict=True)
    source_sha256 = _sha256_file(source_path)
    if source_sha256 != EXPECTED_SOURCE_SHA256:
        raise ValueError("fixed_source_sha256_mismatch")
    decision = json.loads(DECISION_PATH.read_text(encoding="utf-8"))
    if decision.get("matrix_decision_sha256") != EXPECTED_MATRIX_DECISION_SHA256:
        raise ValueError("matrix_decision_sha256_mismatch")
    if decision.get("terminal_state", {}).get("code") != EXPECTED_TERMINAL_STATE:
        raise ValueError("matrix_decision_terminal_state_mismatch")
    control_images = {}
    for role, path in CONTROL_IMAGE_PATHS.items():
        actual = _sha256_file(path.resolve(strict=True))
        if actual != CONTROL_IMAGE_SHA256[role]:
            raise ValueError(f"control_image_sha256_mismatch:{role}")
        control_images[role] = {"path": str(path), "sha256": actual}
    return {
        "source_path": str(source_path),
        "source_sha256": source_sha256,
        "matrix_decision_path": str(DECISION_PATH),
        "matrix_decision_sha256": EXPECTED_MATRIX_DECISION_SHA256,
        "terminal_state": EXPECTED_TERMINAL_STATE,
        "control_images": control_images,
    }


def _control_render_startup_arguments() -> list[str]:
    arguments = []
    for path, value in CONTROL_RENDER_SETTINGS.items():
        encoded = (
            "true"
            if value is True
            else "false"
            if value is False
            else str(value)
        )
        arguments.append(f"--{path}={encoded}")
    return arguments


def _create_two_camera_resources(rep: Any) -> dict[str, dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    width, height = CAPTURE_RESOLUTION
    try:
        for role, camera_path in CAMERA_PATHS.items():
            render_product = rep.create.render_product(camera_path, (width, height))
            annotator = rep.AnnotatorRegistry.get_annotator("rgb")
            annotator.attach(render_product)
            resources[role] = {
                "render_product": render_product,
                "annotator": annotator,
                "annotator_attached": True,
                "annotator_detach_required": True,
            }
    except BaseException:
        replay.destroy_replicator_capture_resources(resources)
        raise
    return resources


def _kit_version() -> str:
    try:
        import omni.kit.app

        app = omni.kit.app.get_app()
        for method_name in ("get_build_version", "get_version"):
            method = getattr(app, method_name, None)
            if callable(method) and (value := method()):
                return str(value)
    except Exception:
        pass
    return "NOT_AVAILABLE"


def _write_manifest(path: Path, value: Mapping[str, Any]) -> None:
    encoded = json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded)


def _run_runtime(source_path: Path, out_root: Path) -> dict[str, Any]:
    fixed_inputs = verify_fixed_inputs(source_path)
    out_root.mkdir(parents=True, exist_ok=False)

    for argument in _control_render_startup_arguments():
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
    try:
        import carb
        import omni.replicator.core as rep
        import omni.timeline
        import omni.usd

        settings = carb.settings.get_settings()
        settings.set_bool("/app/player/playSimulations", False)
        settings.set_bool("/omni/replicator/captureOnPlay", False)
        rep.orchestrator.set_capture_on_play(False)
        render_contract = apply_and_validate_control_render_settings(
            settings,
            update_barrier=app.update,
        )

        timeline = omni.timeline.get_timeline_interface()
        timeline.stop()
        replay.require_stopped_timeline(timeline)
        stage = replay._open_exact_stage(
            context=omni.usd.get_context(),
            app=app,
            timeline=timeline,
            source_path=source_path,
            warmup_updates=WARMUP_UPDATES,
        )
        stage_contract = validate_stage_contract(stage)
        geometry_before = presentation_geometry_signature(stage)
        source_sha256_before = _sha256_file(source_path)
        root_layer_before = stage.GetRootLayer().ExportToString()

        treatment = apply_preview_water_treatment(stage)
        resources = _create_two_camera_resources(rep)
        annotators = {
            role: resource["annotator"] for role, resource in resources.items()
        }
        rep.orchestrator.preview()
        for _ in range(WARMUP_UPDATES):
            replay.require_stopped_timeline(timeline)
            app.update()

        with tempfile.TemporaryDirectory(prefix="warmup_", dir=out_root) as warmup_dir:
            warmup_paths = {
                role: Path(warmup_dir) / f"{role}.png" for role in CAMERA_PATHS
            }
            warmup_capture = replay.capture_static_replicator_rgbs(
                orchestrator=rep.orchestrator,
                timeline=timeline,
                annotators=annotators,
                output_paths=warmup_paths,
                width=CAPTURE_RESOLUTION[0],
                height=CAPTURE_RESOLUTION[1],
                rt_subframes=RT_SUBFRAMES,
                observed_default_time_usd_point_attributes_hash=lambda: (
                    replay.usd_observed_default_time_point_attributes_sha256(stage)
                ),
            )
            warmup_summary = {
                "discarded": True,
                "frame_sha256": {
                    role: record["sha256"]
                    for role, record in warmup_capture["frames"].items()
                },
            }

        output_paths = {
            "source_beaker_closeup": out_root
            / "treatment_source_beaker_closeup.png",
            "pair_context": out_root / "treatment_pair_context.png",
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
        cleanup = replay.destroy_replicator_capture_resources(resources)
        resources = {}
        replay.require_replicator_cleanup(cleanup)

        geometry_after = presentation_geometry_signature(stage)
        if geometry_after != geometry_before:
            raise RuntimeError("capture_changed_presentation_geometry")
        treatment_after = validate_preview_water_treatment(stage, treatment["layer"])
        if stage.GetRootLayer().ExportToString() != root_layer_before:
            raise RuntimeError("probe_changed_source_root_layer")
        source_sha256_after = _sha256_file(source_path)
        if source_sha256_after != source_sha256_before:
            raise RuntimeError("probe_changed_source_file")
        replay.require_stopped_timeline(timeline)

        manifest = {
            "schema_version": 1,
            "probe_id": "real_beaker_preview_water_material_probe_20260713",
            "status": "CAPTURED_PENDING_BLIND_VISUAL_REVIEW",
            "fixed_inputs": fixed_inputs,
            "stage_contract": stage_contract,
            "source_sha256_before": source_sha256_before,
            "source_sha256_after": source_sha256_after,
            "source_unchanged": True,
            "presentation_geometry_before": geometry_before,
            "presentation_geometry_after": geometry_after,
            "presentation_geometry_unchanged": True,
            "treatment": {
                key: value for key, value in treatment_after.items() if key != "layer"
            },
            "render_contract": render_contract,
            "renderer": "RayTracedLighting",
            "kit_version": _kit_version(),
            "camera_warmup_updates": WARMUP_UPDATES,
            "warmup_capture": warmup_summary,
            "capture": capture,
            "replicator_cleanup": cleanup,
            "timeline_stopped": True,
            "simulation_playback_enabled": False,
            "physics_step_count_instrumented": False,
            "physics_steps_executed": None,
            "claim_boundary": "material_presentation_probe_only",
        }
        _write_manifest(out_root / "probe_manifest.json", manifest)
        return manifest
    finally:
        if resources:
            replay.destroy_replicator_capture_resources(resources)
        app.close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_STAGE)
    parser.add_argument("--out-root", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = _run_runtime(args.source.resolve(), args.out_root.resolve())
    print(
        json.dumps(
            {
                "status": result["status"],
                "out_root": str(args.out_root.resolve()),
                "images": {
                    role: record["path"]
                    for role, record in result["capture"]["frames"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
