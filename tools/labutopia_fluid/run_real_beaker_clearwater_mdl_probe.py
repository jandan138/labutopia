#!/usr/bin/env python3
"""Capture one fixed ClearWater MDL treatment on the accepted beaker fill."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AUTHORITY_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_ao_rt_matrix_v3_20260712_008"
    / "matrix_decision_authority"
)
CELL_ROOT = (
    AUTHORITY_ROOT
    / "final_closure/aggregate/cells/A_0_AO0_RT4_CONTROL"
)
SOURCE_STAGE = (
    CELL_ROOT
    / "OMNI_REF_DISPLAY_FILL/OMNI_REF_DISPLAY_FILL_static.usda"
)
MATERIAL_CLOSURE_ROOT = CELL_ROOT / "material_closure_isaacsim41_conda_core"
MDL_SOURCE_ASSET = MATERIAL_CLOSURE_ROOT / "Base/OmniSurfacePresets.mdl"
OUTPUT_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "real_beaker_clearwater_mdl_material_probe_20260713"
)

PRESENTATION_SURFACE_PATH = "/World/CompletedPBD/PresentationSurface"
TREATMENT_MATERIAL_PATH = "/World/Looks/LiquidPresentationWater"
MDL_SUB_IDENTIFIER = "OmniSurface_ClearWater"
EXPECTED_MDL_SOURCE_SHA256 = (
    "5c86c8545a1e215ec4b99e60eb66f9112ca5952cc66ca13ec0c26687dcfcb930"
)
EXPECTED_SOURCE_SHA256 = (
    "c05ec299524cb0d895412ee0c5a1efe7d45c93f7838e512ebd90b0b7bbcc511a"
)
EXPECTED_PHYSICAL_FRAME = 600
EXPECTED_PROXY_GEOMETRY_SHA256 = (
    "8905803d5177e9d2a194720f942c7558847046dffce6b084bc8b66aa36f4a70d"
)
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
    "/World/Looks/LiquidPresentationWater.outputs:mdl:displacement",
    (
        "/World/Looks/LiquidPresentationWater.outputs:mdl:displacement"
        "[/World/Looks/LiquidPresentationWater/Shader.outputs:out]"
    ),
    "/World/Looks/LiquidPresentationWater.outputs:mdl:surface",
    (
        "/World/Looks/LiquidPresentationWater.outputs:mdl:surface"
        "[/World/Looks/LiquidPresentationWater/Shader.outputs:out]"
    ),
    "/World/Looks/LiquidPresentationWater.outputs:mdl:volume",
    (
        "/World/Looks/LiquidPresentationWater.outputs:mdl:volume"
        "[/World/Looks/LiquidPresentationWater/Shader.outputs:out]"
    ),
    "/World/Looks/LiquidPresentationWater/Shader",
    "/World/Looks/LiquidPresentationWater/Shader.info:implementationSource",
    "/World/Looks/LiquidPresentationWater/Shader.info:mdl:sourceAsset",
    "/World/Looks/LiquidPresentationWater/Shader.info:mdl:sourceAsset:subIdentifier",
    "/World/Looks/LiquidPresentationWater/Shader.outputs:out",
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
    payload = json.dumps(
        value,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def _layer_spec_paths(layer: Any) -> tuple[str, ...]:
    from pxr import Sdf

    paths: list[str] = []
    layer.Traverse(Sdf.Path.absoluteRootPath, lambda path: paths.append(str(path)))
    return tuple(sorted(paths))


def verify_clearwater_mdl_input(
    source_asset: Path = MDL_SOURCE_ASSET,
) -> dict[str, str]:
    source = source_asset.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"clearwater_mdl_source_missing:{source}")
    if source != MDL_SOURCE_ASSET.resolve():
        raise ValueError(f"clearwater_mdl_source_not_pinned:{source}")
    source_sha256 = _sha256_file(source)
    if source_sha256 != EXPECTED_MDL_SOURCE_SHA256:
        raise ValueError("clearwater_mdl_source_sha256_mismatch")
    return {
        "source_asset": str(source),
        "source_asset_sha256": source_sha256,
        "sub_identifier": MDL_SUB_IDENTIFIER,
    }


def build_mdl_search_contract() -> dict[str, Any]:
    paths = [
        str((MATERIAL_CLOSURE_ROOT / "mdl").resolve(strict=True)),
        str((MATERIAL_CLOSURE_ROOT / "Base").resolve(strict=True)),
    ]
    encoded = json.dumps(paths, separators=(",", ":"))
    return {
        "search_paths": paths,
        "source_asset": str(MDL_SOURCE_ASSET.resolve(strict=True)),
        "startup_arguments": [
            f"--/app/mdl/additionalUserPaths={encoded}",
            f"--/materialConfig/searchPaths/custom={encoded}",
            f"--/renderer/mdl/searchPaths/custom={';'.join(paths)}",
        ],
    }


def validate_mdl_search_readback(
    settings: Any,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    expected = list(contract["search_paths"])
    additional = list(settings.get("/app/mdl/additionalUserPaths") or [])
    material = list(settings.get("/materialConfig/searchPaths/custom") or [])
    renderer_raw = settings.get("/renderer/mdl/searchPaths/custom")
    renderer = (
        renderer_raw.split(";")
        if isinstance(renderer_raw, str)
        else list(renderer_raw or [])
    )
    if (
        additional[: len(expected)] != expected
        or material[: len(expected)] != expected
        or renderer[: len(expected)] != expected
    ):
        raise RuntimeError("clearwater_mdl_search_readback_mismatch")
    return {
        **deepcopy(dict(contract)),
        "additional_user_paths_readback": additional,
        "material_custom_paths_readback": material,
        "renderer_custom_paths_readback": renderer,
        "readback_verified": True,
    }


def validate_clearwater_treatment(stage: Any, layer: Any) -> dict[str, Any]:
    from pxr import UsdShade

    authored_paths = _layer_spec_paths(layer)
    if authored_paths != EXPECTED_TREATMENT_SPEC_PATHS:
        raise ValueError(
            "clearwater_treatment_layer_specs_mismatch:"
            f"actual={authored_paths}:expected={EXPECTED_TREATMENT_SPEC_PATHS}"
        )
    if stage.GetPrimAtPath(f"{TREATMENT_MATERIAL_PATH}/PreviewSurface"):
        raise ValueError("clearwater_preview_fallback_present")
    shader = UsdShade.Shader(
        stage.GetPrimAtPath(f"{TREATMENT_MATERIAL_PATH}/Shader")
    )
    if not shader or shader.GetImplementationSourceAttr().Get() != "sourceAsset":
        raise ValueError("clearwater_mdl_shader_invalid")
    asset = shader.GetSourceAsset("mdl")
    source_path = str(asset.path) if asset else ""
    resolved_path = str(asset.resolvedPath) if asset else ""
    if source_path != str(MDL_SOURCE_ASSET.resolve()):
        raise ValueError("clearwater_mdl_source_asset_path_mismatch")
    if resolved_path != str(MDL_SOURCE_ASSET.resolve()):
        raise ValueError("clearwater_mdl_source_asset_resolved_path_mismatch")
    sub_identifier = shader.GetSourceAssetSubIdentifier("mdl")
    if sub_identifier != MDL_SUB_IDENTIFIER:
        raise ValueError("clearwater_mdl_sub_identifier_mismatch")
    material = UsdShade.Material(stage.GetPrimAtPath(TREATMENT_MATERIAL_PATH))
    for output_name in ("surface", "displacement", "volume"):
        output = getattr(material, f"Get{output_name.capitalize()}Output")("mdl")
        if not output or not output.HasConnectedSource():
            raise ValueError(f"clearwater_mdl_{output_name}_unconnected")
    surface = stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH)
    bound, _ = UsdShade.MaterialBindingAPI(surface).ComputeBoundMaterial()
    bound_path = str(bound.GetPath()) if bound else ""
    if bound_path != TREATMENT_MATERIAL_PATH:
        raise ValueError("clearwater_effective_material_binding_mismatch")
    return {
        "verified": True,
        "authored_spec_paths": authored_paths,
        "source_asset_path": source_path,
        "source_asset_resolved_path": resolved_path,
        "source_asset_sha256": EXPECTED_MDL_SOURCE_SHA256,
        "sub_identifier": str(sub_identifier),
        "effective_material_path": bound_path,
        "preview_fallback_present": False,
    }


def apply_clearwater_treatment(
    stage: Any,
    *,
    source_asset: Path = MDL_SOURCE_ASSET,
) -> dict[str, Any]:
    from pxr import Sdf, Usd, UsdShade
    from tools.labutopia_fluid import (
        run_colleague_native_usd_completed_pbd_step_video as native,
    )

    verified_input = verify_clearwater_mdl_input(source_asset)
    geometry_before = presentation_geometry_signature(stage)
    layer = Sdf.Layer.CreateAnonymous("clearwater_mdl_treatment.usda")
    stage.GetSessionLayer().subLayerPaths.insert(0, layer.identifier)
    stage.SetEditTarget(Usd.EditTarget(layer))
    native._author_presentation_water_mdl_shader(
        stage,
        Path(verified_input["source_asset"]),
    )
    surface = stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH)
    material = UsdShade.Material(stage.GetPrimAtPath(TREATMENT_MATERIAL_PATH))
    UsdShade.MaterialBindingAPI.Apply(surface).Bind(material)
    validated = validate_clearwater_treatment(stage, layer)
    if presentation_geometry_signature(stage) != geometry_before:
        raise RuntimeError("clearwater_treatment_changed_geometry")
    return {"layer": layer, **validated}


def validate_clearwater_log_segment(segment: Mapping[str, Any]) -> dict[str, Any]:
    from tools.labutopia_fluid import (
        run_colleague_native_usd_completed_pbd_step_video as native,
    )

    log_text = segment.get("log_text")
    if (
        segment.get("cursor_captured") is not True
        or segment.get("diagnostic_scan_complete") is not True
        or type(segment.get("segment_byte_count")) is not int
        or segment["segment_byte_count"] <= 0
        or not isinstance(log_text, str)
        or not log_text.strip()
    ):
        raise ValueError("clearwater_log_segment_invalid")
    scan = native.scan_presentation_water_mdl_compile_errors(log_text)
    if scan.get("mdl_compile_status") != native.MDL_COMPILE_STATUS_PASS:
        raise RuntimeError(
            "clearwater_mdl_compile_failed:"
            + json.dumps(scan.get("errors") or [], separators=(",", ":"))
        )
    return {
        "diagnostic_scan_complete": True,
        "segment_byte_count": int(segment["segment_byte_count"]),
        "segment_sha256": segment.get("segment_sha256"),
        **scan,
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


def _apply_control_render_settings(settings: Any, update_barrier: Any) -> dict[str, Any]:
    for path, value in CONTROL_RENDER_SETTINGS.items():
        if type(value) is bool:
            settings.set_bool(path, value)
        elif type(value) is int:
            settings.set_int(path, value)
        else:
            settings.set_float(path, value)
    update_barrier()
    for path, expected in CONTROL_RENDER_SETTINGS.items():
        actual = settings.get(path)
        matches = (
            math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-6)
            if type(expected) is float and isinstance(actual, (int, float))
            else type(actual) is type(expected) and actual == expected
        )
        if not matches:
            raise RuntimeError(f"control_render_setting_readback_mismatch:{path}")
    return {
        "registry_values": deepcopy(CONTROL_RENDER_SETTINGS),
        "rt_subframes": RT_SUBFRAMES,
        "resolution": list(CAPTURE_RESOLUTION),
        "readback_verified": True,
    }


def _validate_stage_contract(stage: Any) -> dict[str, Any]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(PRESENTATION_SURFACE_PATH)
    if not prim.IsValid() or not prim.IsA(UsdGeom.Mesh):
        raise ValueError("presentation_surface_mesh_missing")
    frame = prim.GetAttribute("labutopia:physicalTraceFrameIndex").Get()
    geometry_hash = prim.GetAttribute("labutopia:proxyGeometrySha256").Get()
    if frame != EXPECTED_PHYSICAL_FRAME:
        raise ValueError("physical_trace_frame_mismatch")
    if geometry_hash != EXPECTED_PROXY_GEOMETRY_SHA256:
        raise ValueError("proxy_geometry_sha256_mismatch")
    for role, path in CAMERA_PATHS.items():
        camera = stage.GetPrimAtPath(path)
        if not camera.IsValid() or not camera.IsA(UsdGeom.Camera):
            raise ValueError(f"probe_camera_missing:{role}:{path}")
    return {
        "physical_trace_frame_index": int(frame),
        "proxy_geometry_sha256": str(geometry_hash),
        "camera_paths": dict(CAMERA_PATHS),
        "presentation_geometry": presentation_geometry_signature(stage),
    }


def _create_two_camera_resources(rep: Any, replay: Any) -> dict[str, dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    try:
        for role, camera_path in CAMERA_PATHS.items():
            product = rep.create.render_product(camera_path, CAPTURE_RESOLUTION)
            annotator = rep.AnnotatorRegistry.get_annotator("rgb")
            annotator.attach(product)
            resources[role] = {
                "render_product": product,
                "annotator": annotator,
                "annotator_attached": True,
                "annotator_detach_required": True,
            }
    except BaseException:
        replay.destroy_replicator_capture_resources(resources)
        raise
    return resources


def _kit_version() -> str:
    import omni.kit.app

    app = omni.kit.app.get_app()
    for method_name in ("get_build_version", "get_version"):
        method = getattr(app, method_name, None)
        if callable(method) and (value := method()):
            return str(value)
    return "NOT_AVAILABLE"


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, allow_nan=False, indent=2, sort_keys=True)
        stream.write("\n")


def _run_runtime(source_path: Path, out_root: Path) -> dict[str, Any]:
    mdl_input = verify_clearwater_mdl_input()
    search_contract = build_mdl_search_contract()
    source_path = source_path.resolve(strict=True)
    if _sha256_file(source_path) != EXPECTED_SOURCE_SHA256:
        raise ValueError("fixed_source_sha256_mismatch")
    out_root.mkdir(parents=True, exist_ok=False)
    for argument in (
        search_contract["startup_arguments"] + _control_render_startup_arguments()
    ):
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
        from tools.labutopia_fluid import (
            run_colleague_native_usd_completed_pbd_step_video as native,
        )
        from tools.labutopia_fluid import (
            run_real_beaker_omniglass_replay as replay,
        )

        settings = carb.settings.get_settings()
        settings.set_bool("/app/player/playSimulations", False)
        settings.set_bool("/omni/replicator/captureOnPlay", False)
        rep.orchestrator.set_capture_on_play(False)
        mdl_search = validate_mdl_search_readback(settings, search_contract)
        render_contract = _apply_control_render_settings(settings, app.update)

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
        stage_contract = _validate_stage_contract(stage)
        geometry_before = presentation_geometry_signature(stage)
        source_sha256_before = _sha256_file(source_path)
        root_before = stage.GetRootLayer().ExportToString()

        log_cursor = native._capture_kit_log_cursor()
        if log_cursor.get("cursor_captured") is not True:
            raise RuntimeError("clearwater_kit_log_cursor_unavailable")
        treatment = apply_clearwater_treatment(stage)
        resources = _create_two_camera_resources(rep, replay)
        annotators = {
            role: resource["annotator"] for role, resource in resources.items()
        }
        rep.orchestrator.preview()
        for _ in range(WARMUP_UPDATES):
            replay.require_stopped_timeline(timeline)
            app.update()
        treatment_after_warmup = validate_clearwater_treatment(
            stage,
            treatment["layer"],
        )

        with tempfile.TemporaryDirectory(prefix="warmup_", dir=out_root) as warmup_dir:
            warmup = replay.capture_static_replicator_rgbs(
                orchestrator=rep.orchestrator,
                timeline=timeline,
                annotators=annotators,
                output_paths={
                    role: Path(warmup_dir) / f"{role}.png" for role in CAMERA_PATHS
                },
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
                    for role, record in warmup["frames"].items()
                },
            }

        capture = replay.capture_static_replicator_rgbs(
            orchestrator=rep.orchestrator,
            timeline=timeline,
            annotators=annotators,
            output_paths={
                "source_beaker_closeup": out_root
                / "clearwater_source_beaker_closeup.png",
                "pair_context": out_root / "clearwater_pair_context.png",
            },
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
        app.update()

        log_segment = native._read_kit_log_segment(log_cursor)
        log_validation = validate_clearwater_log_segment(log_segment)
        log_path = out_root / "kit_log_segment.txt"
        with log_path.open("x", encoding="utf-8") as stream:
            stream.write(str(log_segment["log_text"]))
        log_artifact = {
            "path": str(log_path),
            "sha256": _sha256_file(log_path),
            **log_validation,
        }

        geometry_after = presentation_geometry_signature(stage)
        if geometry_after != geometry_before:
            raise RuntimeError("capture_changed_presentation_geometry")
        treatment_after = validate_clearwater_treatment(stage, treatment["layer"])
        if treatment_after != treatment_after_warmup:
            raise RuntimeError("clearwater_treatment_changed_after_warmup")
        if stage.GetRootLayer().ExportToString() != root_before:
            raise RuntimeError("probe_changed_source_root_layer")
        source_sha256_after = _sha256_file(source_path)
        if source_sha256_after != source_sha256_before:
            raise RuntimeError("probe_changed_source_file")
        replay.require_stopped_timeline(timeline)

        manifest = {
            "schema_version": 1,
            "probe_id": "real_beaker_clearwater_mdl_material_probe_20260713",
            "status": "CAPTURED_TECHNICALLY_VALID_PENDING_BLIND_VISUAL_REVIEW",
            "source_path": str(source_path),
            "source_sha256_before": source_sha256_before,
            "source_sha256_after": source_sha256_after,
            "source_unchanged": True,
            "stage_contract": stage_contract,
            "presentation_geometry_before": geometry_before,
            "presentation_geometry_after": geometry_after,
            "presentation_geometry_unchanged": True,
            "mdl_input": mdl_input,
            "mdl_search_contract": mdl_search,
            "treatment": treatment_after,
            "render_contract": render_contract,
            "renderer": "RayTracedLighting",
            "kit_version": _kit_version(),
            "camera_warmup_updates": WARMUP_UPDATES,
            "warmup_capture": warmup_summary,
            "capture": capture,
            "kit_log_segment": log_artifact,
            "replicator_cleanup": cleanup,
            "timeline_stopped": True,
            "simulation_playback_enabled": False,
            "physics_step_count_instrumented": False,
            "physics_steps_executed": None,
            "preview_fallback_used": False,
            "claim_boundary": "material_presentation_probe_only",
        }
        _write_json(out_root / "probe_manifest.json", manifest)
        return manifest
    finally:
        if resources:
            from tools.labutopia_fluid import (
                run_real_beaker_omniglass_replay as replay,
            )

            replay.destroy_replicator_capture_resources(resources)
        app.close()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_STAGE)
    parser.add_argument("--out-root", type=Path, default=OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = _run_runtime(args.source, args.out_root.resolve())
    print(
        json.dumps(
            {
                "status": result["status"],
                "out_root": str(args.out_root.resolve()),
                "images": {
                    role: frame["path"]
                    for role, frame in result["capture"]["frames"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
