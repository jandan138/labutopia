"""Sealed static USD composition observer for the finite-offset calibration treatment."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _layer_closure(stage: Any, *, composition: Any) -> dict[str, Any]:
    """Hash the composed non-anonymous USD inputs from inside the sealed child."""
    layers_by_path: dict[str, dict[str, str]] = {}
    for layer in stage.GetUsedLayers():
        if bool(getattr(layer, "anonymous", False)):
            continue
        raw_path = getattr(layer, "realPath", "")
        if not isinstance(raw_path, str) or not raw_path:
            raise RuntimeError("authored_offset_composition_layer_path_unavailable")
        raw_candidate = Path(raw_path)
        if raw_candidate.is_symlink() or not raw_candidate.is_file():
            raise RuntimeError("authored_offset_composition_layer_not_regular")
        path = raw_candidate.resolve()
        record = {
            "identifier": str(layer.identifier),
            "real_path": str(path),
            "sha256": _sha256_file(path),
        }
        existing = layers_by_path.get(record["real_path"])
        if existing is not None and existing != record:
            raise RuntimeError("authored_offset_composition_layer_identity_ambiguous")
        layers_by_path[record["real_path"]] = record
    layers = [layers_by_path[path] for path in sorted(layers_by_path)]
    if not layers:
        raise RuntimeError("authored_offset_composition_layer_closure_empty")
    payload = {"layers": layers}
    return {**payload, "sha256": composition.canonical_json_sha256(payload)}


def _layer_path(layer: Any) -> str:
    raw_path = getattr(layer, "realPath", "")
    if isinstance(raw_path, str) and raw_path:
        return str(Path(raw_path).resolve())
    identifier = getattr(layer, "identifier", "")
    return str(identifier) if identifier else ""


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _offset_record(attribute: Any, *, time_code: Any) -> dict[str, Any]:
    if not attribute or not attribute.IsValid():
        return {
            "authored": False,
            "composed_value_m": None,
            "property_stack_layer_paths": [],
            "strongest_property_stack_default_m": None,
        }
    stack = attribute.GetPropertyStack(time_code)
    layer_paths = [_layer_path(spec.layer) for spec in stack]
    strongest_default = _finite_float(stack[0].default) if stack else None
    return {
        "authored": bool(attribute.HasAuthoredValueOpinion()),
        "composed_value_m": _finite_float(attribute.Get()),
        "property_stack_layer_paths": layer_paths,
        "strongest_property_stack_default_m": strongest_default,
    }


def _target_record(
    *,
    stage: Any,
    target: Mapping[str, Any],
    Usd: Any,
    PhysxSchema: Any,
    UsdPhysics: Any,
) -> dict[str, Any]:
    prim = stage.GetPrimAtPath(target["collider_path"])
    if not prim or not prim.IsValid():
        return {
            "id": target["id"],
            "collider_path": target["collider_path"],
            "prim_type": "",
            "collision_enabled": False,
            "usd_collision_api_applied": False,
            "physx_collision_api_applied": False,
            "contact_offset": _offset_record(None, time_code=Usd.TimeCode.Default()),
            "rest_offset": _offset_record(None, time_code=Usd.TimeCode.Default()),
        }
    has_collision_api = bool(prim.HasAPI(UsdPhysics.CollisionAPI))
    collision = UsdPhysics.CollisionAPI(prim) if has_collision_api else None
    enabled_attribute = collision.GetCollisionEnabledAttr() if collision else None
    enabled = enabled_attribute.Get() if enabled_attribute and enabled_attribute.IsValid() else None
    api = PhysxSchema.PhysxCollisionAPI(prim)
    return {
        "id": target["id"],
        "collider_path": target["collider_path"],
        "prim_type": str(prim.GetTypeName()),
        "collision_enabled": enabled is True,
        "usd_collision_api_applied": has_collision_api,
        "physx_collision_api_applied": bool(prim.HasAPI(PhysxSchema.PhysxCollisionAPI)),
        "contact_offset": _offset_record(
            api.GetContactOffsetAttr(), time_code=Usd.TimeCode.Default()
        ),
        "rest_offset": _offset_record(api.GetRestOffsetAttr(), time_code=Usd.TimeCode.Default()),
    }


def _layer_export_sha256(layer: Any) -> str:
    return hashlib.sha256(layer.ExportToString().encode("utf-8")).hexdigest()


def compose_authored_offset_overlay(
    *,
    app: Any,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Compose the two approved session layers without constructing a physics world."""
    import omni.timeline
    import omni.usd
    from pxr import Gf, PhysxSchema, Usd, UsdGeom, UsdPhysics, UsdUtils

    from utils import nonformal_authored_offset_overlay_composition as composition
    from utils import nonformal_usd_dependency_resolution as dependency_resolution

    plan = composition.validate_plan(request["plan"])
    fixture = request["fixture"]
    kit_profile = request["kit_profile"]
    overlay_stack = fixture["overlay_profile"]["overlay_stack"]
    session_sublayers = [item["path"] for item in overlay_stack]
    calibration = next(
        item for item in overlay_stack if item["id"] == composition.OVERLAY_PROFILE_ID
    )
    calibration_path = Path(calibration["path"])
    if (
        calibration_path.is_symlink()
        or not calibration_path.is_file()
        or _sha256_file(calibration_path) != calibration["sha256"]
    ):
        raise RuntimeError("authored_offset_composition_calibration_overlay_changed")
    cube_only_stack = [
        item for item in overlay_stack if item["id"] == "hidden_cube_collision_disable"
    ]

    def dependency_entries(stack: list[Mapping[str, Any]]) -> list[dict[str, str]]:
        return [
            {"id": "fixture_asset", **fixture["asset"]},
            {"id": "robot_asset", **fixture["robot_asset"]},
            *(
                {"id": item["id"], "path": item["path"], "sha256": item["sha256"]}
                for item in stack
            ),
        ]

    dependency_closures_before = {
        "cube_only_baseline_v1": dependency_resolution.discover(
            dependency_entries(cube_only_stack),
            repo_root=Path(__file__).resolve().parents[2],
            UsdUtils=UsdUtils,
        ),
        "finite_target_offsets_calibration_v2": dependency_resolution.discover(
            dependency_entries(overlay_stack),
            repo_root=Path(__file__).resolve().parents[2],
            UsdUtils=UsdUtils,
        ),
    }
    timeline = omni.timeline.get_timeline_interface()
    timeline_before = {
        "is_playing": bool(timeline.is_playing()),
        "time_s": float(timeline.get_current_time()),
    }
    context = omni.usd.get_context()
    context.new_stage()
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("authored_offset_composition_stage_missing")
    root_layer = stage.GetRootLayer()
    session_layer = stage.GetSessionLayer()
    root_layer.Clear()
    session_layer.Clear()
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    world_root = stage.DefinePrim("/World", "Xform")
    world_root.GetReferences().AddReference(fixture["asset"]["path"])
    franka = stage.DefinePrim("/World/Franka", "Xform")
    franka.GetReferences().AddReference(fixture["robot_asset"]["path"])
    translate = franka.GetAttribute("xformOp:translate")
    if translate and translate.IsValid():
        translate.Set(Gf.Vec3d(-0.4, 0.0, 0.71))
    else:
        UsdGeom.Xformable(franka).AddTranslateOp().Set(Gf.Vec3d(-0.4, 0.0, 0.71))
    robot_reference_ready_before_treatment = bool(franka and franka.IsValid())
    if not robot_reference_ready_before_treatment:
        raise RuntimeError("authored_offset_composition_robot_reference_missing")
    for path in session_sublayers:
        session_layer.subLayerPaths.append(path)
    if list(session_layer.subLayerPaths) != session_sublayers:
        raise RuntimeError("authored_offset_composition_session_stack_mismatch")
    for _ in range(2):
        app.update()
    dependency_closures_after = {
        "cube_only_baseline_v1": dependency_resolution.discover(
            dependency_entries(cube_only_stack),
            repo_root=Path(__file__).resolve().parents[2],
            UsdUtils=UsdUtils,
        ),
        "finite_target_offsets_calibration_v2": dependency_resolution.discover(
            dependency_entries(overlay_stack),
            repo_root=Path(__file__).resolve().parents[2],
            UsdUtils=UsdUtils,
        ),
    }
    closure_before = _layer_closure(stage, composition=composition)
    root_before = _layer_export_sha256(root_layer)
    session_before = _layer_export_sha256(session_layer)
    cube = stage.GetPrimAtPath("/World/Cube")
    cube_attribute = cube.GetAttribute("physics:collisionEnabled") if cube and cube.IsValid() else None
    cube_collision_disabled = bool(
        cube_attribute and cube_attribute.IsValid() and cube_attribute.Get() is False
    )
    targets = [
        _target_record(
            stage=stage,
            target=target,
            Usd=Usd,
            PhysxSchema=PhysxSchema,
            UsdPhysics=UsdPhysics,
        )
        for target in plan["targets"]
    ]
    closure_after = _layer_closure(stage, composition=composition)
    root_after = _layer_export_sha256(root_layer)
    session_after = _layer_export_sha256(session_layer)
    timeline_after = {
        "is_playing": bool(timeline.is_playing()),
        "time_s": float(timeline.get_current_time()),
    }
    manager = app.app.get_extension_manager()
    pvd_extensions_enabled = bool(
        manager.get_enabled_extension_id("omni.physx.pvd")
        or manager.get_enabled_extension_id("omni.physxpvd")
    )
    overlay_text = calibration_path.read_text(encoding="ascii")
    payload = {
        "authority": composition.OBSERVATION_AUTHORITY,
        "schema_version": 1,
        "classification": composition.CLASSIFICATION,
        "plan_sha256": plan["sha256"],
        "authorization": dict(composition.AUTHORIZATION),
        "fixture": dict(fixture),
        "kit_profile": dict(kit_profile),
        "input_usd_dependency_closures": {
            "before": closure_before,
            "after": closure_after,
        },
        "resolved_usd_dependency_closures": {
            "cube_only_baseline_v1": {
                "before": dependency_closures_before["cube_only_baseline_v1"],
                "after": dependency_closures_after["cube_only_baseline_v1"],
            },
            "finite_target_offsets_calibration_v2": {
                "before": dependency_closures_before["finite_target_offsets_calibration_v2"],
                "after": dependency_closures_after["finite_target_offsets_calibration_v2"],
            },
        },
        "stage": {
            "meters_per_unit": float(UsdGeom.GetStageMetersPerUnit(stage)),
            "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
            "session_sublayer_paths": list(session_layer.subLayerPaths),
            "robot_reference_ready_before_treatment": robot_reference_ready_before_treatment,
            "cube_collision_disabled": cube_collision_disabled,
            "root_layer_sha256_before": root_before,
            "root_layer_sha256_after": root_after,
            "session_layer_sha256_before": session_before,
            "session_layer_sha256_after": session_after,
            "composition_unchanged": root_before == root_after and session_before == session_after,
        },
        "runtime_scope": {
            "world_constructed": False,
            "world_reset_count": 0,
            "world_step_count": 0,
            "timeline_play_count": 0,
            "timeline_before": timeline_before,
            "timeline_after": timeline_after,
            "timeline_unchanged": timeline_before == timeline_after,
            "pvd_recording_configured": False,
            "pvd_extensions_enabled": pvd_extensions_enabled,
        },
        "overlay_layer": {
            "path": str(calibration_path.resolve()),
            "sha256": calibration["sha256"],
            "exact_canonical_text": overlay_text == composition.expected_overlay_usda(),
            "api_schema_application_count": 3,
            "scalar_opinion_count": 6,
        },
        "targets": targets,
    }
    return {**payload, "sha256": composition.canonical_json_sha256(payload)}
