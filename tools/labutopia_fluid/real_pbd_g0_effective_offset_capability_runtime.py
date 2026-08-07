"""Sealed-child one-step OmniPVD capture for G0 offset capability only.

This module never supplies G0/Phase 3 authority. A PVD record is accepted only
when a one-collider source-owner manifest and one-shape PVD actor prove an
unambiguous diagnostic mapping for each un-authored target.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _has_symlink_component(path: Path, *, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    if current.is_symlink():
        return True
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            return True
    return False


def _regular_file(path: Path, *, root: Path) -> Path:
    if (
        _has_symlink_component(path, root=root)
        or not path.is_file()
        or path.stat().st_nlink != 1
    ):
        raise RuntimeError("g0_pvd_capability_artifact_not_regular")
    return path


def _artifact(path: Path, *, root: Path) -> dict[str, Any]:
    regular = _regular_file(path, root=root)
    return {
        "path": str(regular.relative_to(root)),
        "byte_count": regular.stat().st_size,
        "sha256": _sha256_file(regular),
    }


def _create_private_empty_directory(path: Path, *, out_dir: Path) -> None:
    if not path.is_relative_to(out_dir) or path.exists() or _has_symlink_component(path, root=out_dir):
        raise RuntimeError("g0_pvd_capability_output_directory_invalid")
    path.mkdir(mode=0o700)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError("g0_pvd_capability_output_directory_permissions_invalid")


def _require_runtime_artifacts(value: Any) -> dict[str, dict[str, str]]:
    from utils import real_pbd_g0_effective_offset_capability as capability

    if not isinstance(value, Mapping) or set(value) != set(capability.PVD_RUNTIME_ARTIFACT_NAMES):
        raise RuntimeError("g0_pvd_capability_runtime_artifacts_invalid")
    normalized = {}
    for name in capability.PVD_RUNTIME_ARTIFACT_NAMES:
        record = value[name]
        if (
            not isinstance(record, Mapping)
            or set(record) != {"path", "sha256"}
            or not isinstance(record.get("path"), str)
            or not isinstance(record.get("sha256"), str)
        ):
            raise RuntimeError("g0_pvd_capability_runtime_artifacts_invalid")
        path = Path(record["path"])
        if path.is_symlink() or not path.is_file() or _sha256_file(path) != record["sha256"]:
            raise RuntimeError("g0_pvd_capability_runtime_artifacts_invalid")
        normalized[name] = {"path": str(path.resolve()), "sha256": record["sha256"]}
    return normalized


def configure_pvd_recording_before_scene(
    *,
    recording_dir: Path,
    conversion_dir: Path,
    out_dir: Path,
    runtime_artifacts: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    """Create private output paths and enable PVD before ``World`` construction."""
    import carb
    from omni.physx.bindings._physx import (
        SETTING_OMNIPVD_ENABLED,
        SETTING_OMNIPVD_OVD_RECORDING_DIRECTORY,
    )

    artifacts = _require_runtime_artifacts(runtime_artifacts)
    _create_private_empty_directory(recording_dir, out_dir=out_dir)
    _create_private_empty_directory(conversion_dir, out_dir=out_dir)
    settings = carb.settings.get_settings()
    settings.set(SETTING_OMNIPVD_OVD_RECORDING_DIRECTORY, f"{recording_dir}/")
    settings.set(SETTING_OMNIPVD_ENABLED, True)
    if (
        settings.get(SETTING_OMNIPVD_OVD_RECORDING_DIRECTORY) != f"{recording_dir}/"
        or not settings.get_as_bool(SETTING_OMNIPVD_ENABLED)
    ):
        raise RuntimeError("g0_pvd_capability_settings_before_scene_invalid")
    return artifacts


def _regular_tree(root: Path, *, out_dir: Path) -> list[Path]:
    if _has_symlink_component(root, root=out_dir) or not root.is_dir():
        raise RuntimeError("g0_pvd_capability_artifact_tree_invalid")
    files = []
    for path in sorted(root.rglob("*")):
        if _has_symlink_component(path, root=out_dir):
            raise RuntimeError("g0_pvd_capability_artifact_symlink")
        if path.is_dir():
            continue
        files.append(_regular_file(path, root=out_dir))
    return files


def _finalized_ovd(recording_dir: Path, *, out_dir: Path) -> dict[str, Any]:
    files = _regular_tree(recording_dir, out_dir=out_dir)
    finalized = [path for path in files if path.suffix == ".ovd"]
    unexpected = [path for path in files if path not in finalized]
    if len(finalized) != 1 or unexpected:
        raise RuntimeError("g0_pvd_capability_finalized_ovd_invalid")
    return _artifact(finalized[0], root=out_dir)


def _converted_artifacts(conversion_dir: Path, *, out_dir: Path) -> list[dict[str, Any]]:
    files = _regular_tree(conversion_dir, out_dir=out_dir)
    expected = {
        conversion_dir / "stage.usda",
        conversion_dir / "scene.usda",
        conversion_dir / "shared.usda",
    }
    if set(files) != expected:
        raise RuntimeError("g0_pvd_capability_conversion_closure_invalid")
    return [_artifact(path, root=out_dir) for path in sorted(files)]


def _finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _time_zero_value(attribute: Any, time_code: Any) -> Any:
    if not attribute or not attribute.IsValid():
        return None
    try:
        samples = [float(sample) for sample in attribute.GetTimeSamples()]
    except (TypeError, ValueError):
        return None
    if not any(math.isclose(sample, 0.0, rel_tol=0.0, abs_tol=0.0) for sample in samples):
        return None
    return attribute.Get(time_code)


def _uniform_value(attribute: Any) -> Any:
    if not attribute or not attribute.IsValid():
        return None
    return attribute.Get()


def build_source_target_manifest(stage: Any, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Bind each desired PVD actor to exactly one enabled source collider."""
    from pxr import PhysxSchema, Usd, UsdPhysics

    from utils import real_pbd_g0_effective_offset_capability as capability

    normalized_plan = capability.validate_plan(plan)
    records = []
    for target in normalized_plan["targets"]:
        collider = stage.GetPrimAtPath(target["collider_path"])
        owner = stage.GetPrimAtPath(target["actor_name"])
        if (
            not collider
            or not collider.IsValid()
            or not owner
            or not owner.IsValid()
            or not collider.HasAPI(UsdPhysics.CollisionAPI)
        ):
            raise RuntimeError("g0_pvd_capability_target_source_missing")
        enabled = []
        for prim in Usd.PrimRange(owner):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                continue
            value = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
            if value is not False:
                enabled.append(str(prim.GetPath()))
        enabled = sorted(set(enabled))
        if enabled != [target["collider_path"]]:
            raise RuntimeError("g0_pvd_capability_target_source_cardinality_invalid")
        api = PhysxSchema.PhysxCollisionAPI(collider)
        contact = api.GetContactOffsetAttr()
        rest = api.GetRestOffsetAttr()
        records.append(
            {
                "id": target["id"],
                "collider_path": target["collider_path"],
                "actor_name": target["actor_name"],
                "source_owner_path": target["actor_name"],
                "source_enabled_collider_paths": enabled,
                "source_shape_count": 1,
                "source_prim_type": str(collider.GetTypeName()),
                "contact_offset_authored": bool(
                    contact and contact.HasAuthoredValueOpinion()
                ),
                "rest_offset_authored": bool(rest and rest.HasAuthoredValueOpinion()),
            }
        )
    payload = {
        "authority": capability.TARGET_MANIFEST_AUTHORITY,
        "targets": sorted(records, key=lambda item: item["id"]),
    }
    return {**payload, "sha256": capability.canonical_json_sha256(payload)}


def _stage_immutability_snapshot(stage: Any) -> dict[str, str]:
    from tools.labutopia_fluid import run_real_pbd_grasp_v2_g0_geometry as geometry

    return {
        "root_layer_sha256": hashlib.sha256(
            stage.GetRootLayer().ExportToString().encode("utf-8")
        ).hexdigest(),
        "session_layer_sha256": hashlib.sha256(
            stage.GetSessionLayer().ExportToString().encode("utf-8")
        ).hexdigest(),
        "collision_inventory_sha256": geometry._collision_inventory(stage)["sha256"],
    }


class _WorldOperationAudit:
    """Count the only permitted capture operations on this disposable world."""

    def __init__(self, world: Any, methods: Sequence[tuple[str, str]]) -> None:
        self._world = world
        self._originals: dict[str, tuple[Any, bool]] = {}
        self.counts = {counter: 0 for _, counter in methods}
        for method, counter in methods:
            original = getattr(world, method, None)
            if not callable(original):
                self.close()
                raise RuntimeError(f"g0_pvd_capability_world_operation_unavailable:{method}")
            instance_dict = getattr(world, "__dict__", None)
            had_instance_attribute = isinstance(instance_dict, dict) and method in instance_dict

            def counted(*args: Any, _original: Any = original, _counter: str = counter, **kwargs: Any) -> Any:
                self.counts[_counter] += 1
                return _original(*args, **kwargs)

            try:
                setattr(world, method, counted)
            except (AttributeError, TypeError) as exc:
                self.close()
                raise RuntimeError(f"g0_pvd_capability_world_operation_unpatchable:{method}") from exc
            self._originals[method] = (original, had_instance_attribute)

    def close(self) -> None:
        for method, (original, had_instance_attribute) in reversed(tuple(self._originals.items())):
            if had_instance_attribute:
                setattr(self._world, method, original)
            else:
                delattr(self._world, method)
        self._originals.clear()


def _pvd_extension_provenance(runtime_artifacts: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    import omni.kit.app
    import omni.physxpvd.bindings._physxPvd as binding
    import omni.physxpvd.scripts.extension as extension
    import omni.physxpvd.scripts.omniusd_to_physxusd.omniusd_to_physxusd as converter

    manager = omni.kit.app.get_app().get_extension_manager()
    extension_id = manager.get_extension_id_by_module("omni.physxpvd")
    if not isinstance(extension_id, str) or not extension_id:
        raise RuntimeError("g0_pvd_capability_extension_id_unavailable")
    metadata = manager.get_extension_dict(extension_id)
    package = metadata.get("package") if isinstance(metadata, Mapping) else None
    version = package.get("version") if isinstance(package, Mapping) else None
    extension_path = manager.get_extension_path(extension_id)
    origins = {
        "extension_python": str(Path(extension.__file__).resolve()),
        "converter_python": str(Path(converter.__file__).resolve()),
        "binding": str(Path(binding.__file__).resolve()),
    }
    if (
        not isinstance(version, str)
        or not isinstance(extension_path, str)
        or Path(extension_path).resolve()
        != Path(runtime_artifacts["extension_toml"]["path"]).parent.resolve()
        or any(origins[name] != runtime_artifacts[name]["path"] for name in origins)
    ):
        raise RuntimeError("g0_pvd_capability_extension_provenance_invalid")
    return {
        "extension_id": extension_id,
        "extension_version": version,
        "extension_path": str(Path(extension_path).resolve()),
        "module_origins": origins,
    }


def _pvd_scene(stage: Any, *, source_stage_meters_per_unit: float) -> dict[str, Any]:
    from pxr import Usd

    time_zero = Usd.TimeCode(0)
    scenes = []
    for prim in Usd.PrimRange.Stage(stage):
        if _uniform_value(prim.GetAttribute("omni:pvdi:class")) != "PxScene":
            continue
        scale = _time_zero_value(prim.GetAttribute("omni:pvd:tolerancesScale"), time_zero)
        try:
            scale_values = [float(item) for item in scale]
        except (TypeError, ValueError):
            continue
        if not scale_values or not math.isfinite(scale_values[0]) or scale_values[0] <= 0.0:
            continue
        scenes.append(
            {
                "pvd_scene_path": str(prim.GetPath()),
                "pvd_scene_class": "PxScene",
                "sample_time_code": 0,
                "pvd_length_units_per_meter": scale_values[0],
                "source_stage_meters_per_unit": source_stage_meters_per_unit,
            }
        )
    if len(scenes) != 1:
        raise RuntimeError("g0_pvd_capability_pvd_scene_invalid")
    return scenes[0]


def _pvd_actor_inventory(
    stage: Any,
    *,
    target_manifest: Mapping[str, Any],
    pvd_scene: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract only explicit time-zero records inside the unique PVD scene."""
    from pxr import Usd

    time_zero = Usd.TimeCode(0)
    scene_path = pvd_scene["pvd_scene_path"]
    manifest_targets = {target["id"]: target for target in target_manifest["targets"]}
    targets_by_actor = {}
    for target in manifest_targets.values():
        targets_by_actor.setdefault(target["actor_name"], []).append(target)
    actors = []
    target_records = []
    for prim in Usd.PrimRange.Stage(stage):
        prim_path = str(prim.GetPath())
        if not prim_path.startswith(f"{scene_path}/"):
            continue
        actor_name = _time_zero_value(prim.GetAttribute("omni:pvd:name"), time_zero)
        actor_type = _time_zero_value(prim.GetAttribute("omni:pvd:type"), time_zero)
        actor_class = _uniform_value(prim.GetAttribute("omni:pvdi:class"))
        if not isinstance(actor_name, str) or not actor_name or not isinstance(actor_type, str):
            continue
        if not isinstance(actor_class, str) or not actor_class:
            continue
        shapes = []
        for descendant in Usd.PrimRange(prim):
            if descendant == prim:
                continue
            shape_path = str(descendant.GetPath())
            if not shape_path.startswith(f"{prim_path}/"):
                continue
            if _uniform_value(descendant.GetAttribute("omni:pvdi:class")) != "PxShape":
                continue
            raw_flags = _time_zero_value(descendant.GetAttribute("omni:pvd:shapeFlags"), time_zero)
            flags = [str(item) for item in raw_flags] if raw_flags is not None else []
            geometry_classes = []
            for geometry in Usd.PrimRange(descendant):
                if geometry == descendant:
                    continue
                raw_class = _uniform_value(geometry.GetAttribute("omni:pvdi:class"))
                if isinstance(raw_class, str) and raw_class.startswith("PxGeom"):
                    geometry_classes.append(raw_class)
            shapes.append(
                {
                    "pvd_shape_path": shape_path,
                    "raw_contact_offset_pvd": _finite_float(
                        _time_zero_value(descendant.GetAttribute("omni:pvd:contactOffset"), time_zero)
                    ),
                    "raw_rest_offset_pvd": _finite_float(
                        _time_zero_value(descendant.GetAttribute("omni:pvd:restOffset"), time_zero)
                    ),
                    "shape_flags": sorted(flags),
                    "pvd_geometry_classes": sorted(set(geometry_classes)),
                }
            )
        shapes.sort(key=lambda item: item["pvd_shape_path"])
        actor = {
            "actor_name": actor_name,
            "actor_type": actor_type,
            "pvd_actor_class": actor_class,
            "pvd_scene_path": scene_path,
            "pvd_actor_path": prim_path,
            "shape_count": len(shapes),
            "shapes": shapes,
        }
        actors.append(actor)
        for target in targets_by_actor.get(actor_name, []):
            for shape in shapes:
                geometry_classes = shape["pvd_geometry_classes"]
                target_records.append(
                    {
                        "id": target["id"],
                        "collider_path": target["collider_path"],
                        "actor_name": actor_name,
                        "actor_type": actor_type,
                        "pvd_actor_class": actor_class,
                        "pvd_scene_path": scene_path,
                        "pvd_actor_path": prim_path,
                        "pvd_shape_path": shape["pvd_shape_path"],
                        "sample_time_code": 0,
                        "source_target_manifest_sha256": target_manifest["sha256"],
                        "source_owner_path": target["source_owner_path"],
                        "source_enabled_collider_paths": list(
                            target["source_enabled_collider_paths"]
                        ),
                        "source_shape_count": target["source_shape_count"],
                        "pvd_actor_shape_count": len(shapes),
                        "pvd_geometry_class": geometry_classes[0]
                        if len(geometry_classes) == 1
                        else "",
                        "raw_contact_offset_pvd": shape["raw_contact_offset_pvd"],
                        "raw_rest_offset_pvd": shape["raw_rest_offset_pvd"],
                        "pvd_length_units_per_meter": pvd_scene[
                            "pvd_length_units_per_meter"
                        ],
                        "contact_offset_m": (
                            shape["raw_contact_offset_pvd"]
                            / pvd_scene["pvd_length_units_per_meter"]
                            if shape["raw_contact_offset_pvd"] is not None
                            else None
                        ),
                        "rest_offset_m": (
                            shape["raw_rest_offset_pvd"]
                            / pvd_scene["pvd_length_units_per_meter"]
                            if shape["raw_rest_offset_pvd"] is not None
                            else None
                        ),
                        "shape_flags": shape["shape_flags"],
                    }
                )
    actors.sort(key=lambda item: (item["actor_name"], item["pvd_actor_path"]))
    target_records.sort(key=lambda item: (item["id"], item["pvd_actor_path"], item["pvd_shape_path"]))
    return actors, target_records


def _converted_stage_closure(stage: Any, *, conversion_dir: Path, out_dir: Path) -> None:
    expected = {
        conversion_dir / "stage.usda",
        conversion_dir / "scene.usda",
        conversion_dir / "shared.usda",
    }
    layers = set()
    for layer in stage.GetUsedLayers():
        if layer.anonymous:
            continue
        path = Path(layer.realPath)
        if not path.is_relative_to(conversion_dir):
            raise RuntimeError("g0_pvd_capability_converted_stage_external_dependency")
        layers.add(_regular_file(path, root=out_dir))
    if layers != expected:
        raise RuntimeError("g0_pvd_capability_converted_stage_closure_invalid")


def _native_pvd_artifacts_loaded(runtime_artifacts: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    expected_names = ("binding", "plugin", "runtime_library")
    expected_paths = {Path(runtime_artifacts[name]["path"]).resolve() for name in expected_names}
    mapped = set()
    try:
        lines = Path("/proc/self/maps").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError("g0_pvd_capability_proc_maps_unavailable") from exc
    for line in lines:
        fields = line.split()
        if len(fields) < 6 or not fields[-1].startswith("/"):
            continue
        try:
            path = Path(fields[-1]).resolve(strict=True)
        except OSError:
            continue
        if path in expected_paths:
            mapped.add(path)
    if mapped != expected_paths:
        raise RuntimeError("g0_pvd_capability_native_artifact_not_loaded")
    return {name: dict(runtime_artifacts[name]) for name in expected_names}


def run_pvd_offset_capability(
    *,
    app: Any,
    stage: Any,
    timeline: Any,
    plan: Mapping[str, Any],
    target_manifest: Mapping[str, Any],
    recording_dir: Path,
    conversion_dir: Path,
    out_dir: Path,
    runtime_artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    """Capture one explicit World step and parse its finalized PVD closure."""
    import carb
    import numpy as np
    import omni.physx
    import omni.timeline
    from omni.isaac.core import World
    from omni.isaac.core.prims import RigidPrimView
    from omni.physx.bindings._physx import (
        SETTING_OMNIPVD_ENABLED,
        SETTING_OMNIPVD_IS_RECORDING,
    )
    from omni.physxpvd.bindings import _physxPvd
    from pxr import Usd, UsdGeom

    from tools.labutopia_fluid import (
        real_pbd_g0_full_robot_fk_capability_runtime as fk_runtime,
    )
    from tools.labutopia_fluid import nonformal_controller_static_collision_screen_runtime as static_runtime
    from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as native
    from utils import real_pbd_g0_effective_offset_capability as capability

    normalized_plan = capability.validate_plan(plan)
    normalized_artifacts = _require_runtime_artifacts(runtime_artifacts)
    # The pure evaluator validates this manifest after it has been bound to PVD records.
    if not isinstance(target_manifest, Mapping):
        raise RuntimeError("g0_pvd_capability_target_manifest_invalid")
    settings = carb.settings.get_settings()
    world = None
    reset_audit = None
    operation_audit = None
    timeline_audit = None
    try:
        if not settings.get_as_bool(SETTING_OMNIPVD_ENABLED):
            raise RuntimeError("g0_pvd_capability_not_enabled_before_scene")
        stage_before = _stage_immutability_snapshot(stage)
        world = World(
            physics_dt=1.0 / 600.0,
            rendering_dt=1.0 / 600.0,
            stage_units_in_meters=1.0,
            physics_prim_path="/World/PhysicsScene",
            backend="numpy",
            set_defaults=False,
        )
        omni.physx.get_physx_interface().overwrite_gpu_setting(1)
        reset_audit = _WorldOperationAudit(world, (("reset", "world_reset"),))
        world.reset()
        reset_count = reset_audit.counts["world_reset"]
        reset_audit.close()
        reset_audit = None
        reset_runtime = static_runtime._runtime_receipt(world, timeline)
        source_reader = native.RuntimeReadOnlySourceAdapter(RigidPrimView, "/World/beaker2")
        source_reader.initialize()
        initialized_runtime = static_runtime._runtime_receipt(world, timeline)
        if initialized_runtime != reset_runtime:
            raise RuntimeError("g0_pvd_capability_source_reader_advanced")
        source_before = fk_runtime._source_state(np, source_reader, stage)
        operation_audit = _WorldOperationAudit(
            world,
            (("step", "world_step"), ("play", "world_play"), ("pause", "world_pause")),
        )
        timeline_audit = fk_runtime._TimelineEventAudit(
            timeline,
            {
                int(omni.timeline.TimelineEventType.PLAY): "timeline_play",
                int(omni.timeline.TimelineEventType.PAUSE): "timeline_pause",
                int(omni.timeline.TimelineEventType.STOP): "timeline_stop",
            },
        )
        world.play()
        if not timeline.is_playing():
            raise RuntimeError("g0_pvd_capability_timeline_not_playing")
        before_step = static_runtime._runtime_receipt(world, timeline)
        world.step(render=False)
        after_step = static_runtime._runtime_receipt(world, timeline)
        world.pause()
        if timeline.is_playing():
            raise RuntimeError("g0_pvd_capability_timeline_not_paused")
        settings.set(SETTING_OMNIPVD_ENABLED, False)
        finalization_before = static_runtime._runtime_receipt(world, timeline)
        finalization_updates = normalized_plan["capture"]["maximum_post_disable_finalization_updates"]
        for _ in range(finalization_updates):
            app.update()
            if static_runtime._runtime_receipt(world, timeline) != finalization_before:
                raise RuntimeError("g0_pvd_capability_finalization_advanced_physics")
        if settings.get_as_bool(SETTING_OMNIPVD_ENABLED) or settings.get_as_bool(
            SETTING_OMNIPVD_IS_RECORDING
        ):
            raise RuntimeError("g0_pvd_capability_recording_not_disabled")
        timeline_counts = timeline_audit.operation_counts()
        operation_counts = {
            "world_reset": reset_count,
            **operation_audit.counts,
            "app_update_finalization": finalization_updates,
        }
        finalized_ovd = _finalized_ovd(recording_dir, out_dir=out_dir)
        ovd_path = out_dir / finalized_ovd["path"]
        interface = _physxPvd.acquire_physx_pvd_interface()
        if interface is None:
            raise RuntimeError("g0_pvd_capability_interface_unavailable")
        try:
            if not interface.ovd_to_usd(str(ovd_path), f"{conversion_dir}/", 1, 1):
                raise RuntimeError("g0_pvd_capability_conversion_failed")
        finally:
            _physxPvd.release_physx_pvd_interface(interface)
        conversion_artifacts = _converted_artifacts(conversion_dir, out_dir=out_dir)
        converted_stage = Usd.Stage.Open(str(conversion_dir / "stage.usda"))
        if converted_stage is None:
            raise RuntimeError("g0_pvd_capability_converted_stage_open_failed")
        _converted_stage_closure(converted_stage, conversion_dir=conversion_dir, out_dir=out_dir)
        pvd_scene = _pvd_scene(
            converted_stage,
            source_stage_meters_per_unit=float(UsdGeom.GetStageMetersPerUnit(stage)),
        )
        actor_inventory, target_offsets = _pvd_actor_inventory(
            converted_stage,
            target_manifest=target_manifest,
            pvd_scene=pvd_scene,
        )
        source_after = fk_runtime._source_state(np, source_reader, stage)
        stage_after = _stage_immutability_snapshot(stage)
        stage_immutability = {
            "root_layer_sha256_before": stage_before["root_layer_sha256"],
            "root_layer_sha256_after": stage_after["root_layer_sha256"],
            "session_layer_sha256_before": stage_before["session_layer_sha256"],
            "session_layer_sha256_after": stage_after["session_layer_sha256"],
            "collision_inventory_sha256_before": stage_before["collision_inventory_sha256"],
            "collision_inventory_sha256_after": stage_after["collision_inventory_sha256"],
            "unchanged": stage_before == stage_after,
        }
        provenance = _pvd_extension_provenance(normalized_artifacts)
        observation_payload = {
            "authority": capability.OBSERVATION_AUTHORITY,
            "schema_version": 1,
            "classification": capability.CLASSIFICATION,
            "plan_sha256": normalized_plan["sha256"],
            "authorization": dict(normalized_plan["authorization"]),
            "pvd_runtime_artifacts": normalized_artifacts,
            "pvd_extension_provenance": provenance,
            "recording": {
                "capture_authority": "instrumented_world_and_timeline_v1",
                "pvd_enabled_before_scene": True,
                "bootstrap_world_reset_count": operation_counts["world_reset"],
                "explicit_world_step_count": operation_counts["world_step"],
                "timeline_play_count": operation_counts["world_play"],
                "timeline_pause_count": operation_counts["world_pause"],
                "world_index_before_step": before_step["world_index"],
                "world_index_after_step": after_step["world_index"],
                "pvd_enabled_after_capture": False,
                "pvd_is_recording_after_capture": False,
                "post_disable_finalization_updates": finalization_updates,
                "operation_counts": operation_counts,
                "timeline_event_counts": timeline_counts,
                "finalized_ovd": finalized_ovd,
                "conversion_artifacts": conversion_artifacts,
            },
            "pvd_scene": pvd_scene,
            "target_manifest": dict(target_manifest),
            "stage_immutability": stage_immutability,
            "target_offsets": target_offsets,
        }
        observation = {
            **observation_payload,
            "sha256": capability.canonical_json_sha256(observation_payload),
        }
        return {
            "authority": "real_pbd_g0_effective_offset_capability_runtime_v2",
            "status": "COMPLETE",
            "plan": normalized_plan,
            "observation": observation,
            "evaluation": capability.evaluate_observation(observation, plan=normalized_plan),
            "pvd_actor_inventory": {
                "authority": "real_pbd_g0_pvd_actor_inventory_v2",
                "pvd_scene": pvd_scene,
                "actors": actor_inventory,
                "sha256": _canonical_json_sha256(
                    {"pvd_scene": pvd_scene, "actors": actor_inventory}
                ),
            },
            "native_pvd_artifacts_loaded": _native_pvd_artifacts_loaded(normalized_artifacts),
            "capture_runtime": {
                "reset_runtime": reset_runtime,
                "before_step": before_step,
                "after_step": after_step,
                "finalization_runtime": finalization_before,
            },
            "source_state_before": source_before,
            "source_state_after": source_after,
            "source_reader": source_reader.contract(),
        }
    finally:
        settings.set(SETTING_OMNIPVD_ENABLED, False)
        if reset_audit is not None:
            reset_audit.close()
        if operation_audit is not None:
            operation_audit.close()
        if timeline_audit is not None:
            timeline_audit.close()
        if world is not None:
            clear_instance = getattr(World, "clear_instance", None)
            if callable(clear_instance):
                clear_instance()
