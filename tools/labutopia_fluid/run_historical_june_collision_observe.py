#!/usr/bin/env python3
"""Execute the 2026-06-09 controller snapshot with external contact tracing.

The historical source tree is detached and never modified. This runner only
installs Isaac 4.1 import aliases and runtime instrumentation around it.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import runpy
import secrets
import signal
import subprocess
import sys
import traceback
import types
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import nonformal_collision_observe as observe
from tools.labutopia_fluid import run_nonformal_pbd_direct_contact_probe as probe


HISTORICAL_COMMIT = "22a263e54c545faebb9eb2e6d5f04566885e8c40"
DEFAULT_HISTORICAL_ROOT = (
    REPO_ROOT / ".worktrees/historical-pick-20260609"
)
FORMAL_ISAAC41_PYTHON = probe.FORMAL_ISAAC41_PYTHON
HISTORICAL_SCENE_RELATIVE_PATH = Path(
    "assets/chemistry_lab/lab_001/lab_001.usd"
)
HISTORICAL_ROBOT_RELATIVE_PATH = Path("assets/robots/Franka.usd")
LOCALIZED_ASSET_PACKAGE_ROOT = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/dependencies/"
    "lab_001_localized_20260707"
)
LOCALIZED_SCENE_PATH = LOCALIZED_ASSET_PACKAGE_ROOT / "lab_001.usd"
LOCALIZED_LIQUID_SCENE_PATH = (
    LOCALIZED_ASSET_PACKAGE_ROOT / "lab_001_level1_pour_tabletop_with_liquid.usd"
)
LOCALIZED_ASSET_SOURCES = {
    "localized": LOCALIZED_SCENE_PATH,
    "localized_liquid": LOCALIZED_LIQUID_SCENE_PATH,
}
PRESENTATION_LIQUID_OVERLAY_FRAME_PARENT_PATH = "/World/beaker2"
PRESENTATION_LIQUID_OVERLAY_PARENT_PATH = "/World/beaker2/mesh"
PRESENTATION_LIQUID_OVERLAY_PATH = (
    f"{PRESENTATION_LIQUID_OVERLAY_PARENT_PATH}/HistoricalPresentationLiquid"
)
PRESENTATION_LIQUID_OVERLAY_MATERIAL_PATH = "/World/Looks/LiquidPresentationWater"
PRESENTATION_LIQUID_OVERLAY_POINT_COUNT = 2376
PRESENTATION_WATER_PREVIEW_DIFFUSE_COLOR = (0.74, 0.94, 1.0)
PRESENTATION_WATER_PREVIEW_EMISSIVE_COLOR = (0.0, 0.0, 0.0)
PRESENTATION_WATER_PREVIEW_OPACITY = 0.34
PRESENTATION_WATER_PREVIEW_ROUGHNESS = 0.02
PRESENTATION_WATER_PREVIEW_IOR = 1.333
PHYSICAL_PBD_DEFAULT_PARTICLE_COUNT = 4096
PHYSICAL_PBD_DEFAULT_PARTICLE_SEED = 0
PHYSICAL_PBD_RUNTIME_PATH = "/World/CompletedPBD"
PHYSICAL_PBD_RUNTIME_PARTICLE_SET_PATH = f"{PHYSICAL_PBD_RUNTIME_PATH}/ParticleSet"
HISTORICAL_PICK_DONE_EVENT = 7
HISTORICAL_POUR_DONE_EVENT = 6
HISTORICAL_SOURCE_FILES = (
    "main.py",
    "config/level1_pour.yaml",
    "controllers/pour_controller.py",
    "controllers/atomic_actions/pick_controller.py",
    "controllers/atomic_actions/pour_controller.py",
    "controllers/base_controller.py",
    "factories/controller_factory.py",
    "factories/task_factory.py",
    "tasks/base_task.py",
    "tasks/pickpour_task.py",
    "robots/franka/franka.py",
    "robots/franka/rmpflow_controller.py",
    "utils/object_utils.py",
)


def _attestation_module() -> Any:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime

    return attest_isaac41_effective_runtime


def _sha256_file(path: Path) -> str:
    return probe._sha256_file(path)


def historical_identity(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not (root / ".git").exists():
        raise ValueError("historical_root_not_git_worktree")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if revision != HISTORICAL_COMMIT or status:
        raise ValueError("historical_source_identity_invalid")
    files = {}
    for relative in HISTORICAL_SOURCE_FILES:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"historical_source_file_missing:{relative}")
        files[relative] = _sha256_file(path)
    return {
        "root": str(root),
        "revision": revision,
        "clean": True,
        "files": files,
    }


def localized_asset_package_paths() -> tuple[Path, ...]:
    if not LOCALIZED_ASSET_PACKAGE_ROOT.is_dir():
        raise FileNotFoundError(
            f"historical_localized_asset_package_missing:{LOCALIZED_ASSET_PACKAGE_ROOT}"
        )
    paths = tuple(
        sorted(
            path
            for path in LOCALIZED_ASSET_PACKAGE_ROOT.rglob("*")
            if path.is_file()
        )
    )
    for scene_path in LOCALIZED_ASSET_SOURCES.values():
        if scene_path not in paths:
            raise FileNotFoundError(
                f"historical_localized_scene_missing:{scene_path}"
            )
    return paths


def _source_paths(
    attester_path: Path,
    historical_root: Path,
    asset_source: str,
    *,
    physical_pbd: bool = False,
) -> tuple[Path, ...]:
    paths = [
        Path(attester_path),
        Path(__file__),
        REPO_ROOT / "isaacsim_compat.py",
        REPO_ROOT / "tools/labutopia_fluid/nonformal_collision_observe.py",
        REPO_ROOT / "tools/labutopia_fluid/run_nonformal_pbd_direct_contact_probe.py",
        *(historical_root / relative for relative in HISTORICAL_SOURCE_FILES),
    ]
    if asset_source in LOCALIZED_ASSET_SOURCES:
        paths.extend(localized_asset_package_paths())
        if asset_source == "localized_liquid":
            paths.extend(
                REPO_ROOT / relative
                for relative in (
                    Path("tools/labutopia_fluid/omniglass_reference.py"),
                    Path("tools/labutopia_fluid/presentation_look_profiles.py"),
                    Path("tools/labutopia_fluid/real_beaker.py"),
                )
            )
            if physical_pbd:
                paths.extend(
                    REPO_ROOT / relative
                    for relative in (
                        Path("tools/labutopia_fluid/fluid_recipe.py"),
                        Path("tools/labutopia_fluid/full_scene_spawn_frame.py"),
                        Path("tools/labutopia_fluid/run_beaker_collider_followup_sweep.py"),
                        Path("tools/labutopia_fluid/run_beaker_collider_smoke.py"),
                        Path("tools/labutopia_fluid/run_colleague_liquid_usd_leak_smoke.py"),
                        Path("tools/labutopia_fluid/run_standalone_particle_smoke.py"),
                        Path("tools/labutopia_fluid/run_interndata_pour_parity_probe.py"),
                        Path("tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py"),
                    )
                )
    elif asset_source != "historical_raw":
        raise ValueError(f"historical_asset_source_invalid:{asset_source}")
    return tuple(paths)


def historical_asset_paths(root: Path, *, asset_source: str) -> dict[str, Path]:
    root = root.resolve()
    if asset_source in LOCALIZED_ASSET_SOURCES:
        scene_path = LOCALIZED_ASSET_SOURCES[asset_source]
    elif asset_source == "historical_raw":
        scene_path = root / HISTORICAL_SCENE_RELATIVE_PATH
    else:
        raise ValueError(f"historical_asset_source_invalid:{asset_source}")
    paths = {
        "scene": scene_path,
        "robot": root / HISTORICAL_ROBOT_RELATIVE_PATH,
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "historical_asset_missing:" + ",".join(sorted(missing))
        )
    return paths


def historical_input_closure(root: Path, *, asset_source: str) -> dict[str, str]:
    paths = historical_asset_paths(root, asset_source=asset_source)
    if asset_source in LOCALIZED_ASSET_SOURCES:
        paths = {
            **{
                f"package:{path}": path
                for path in localized_asset_package_paths()
            },
            "historical_robot": paths["robot"],
        }
    return dict(
        sorted(
            (str(path.resolve()), probe._stable_file_bytes(path)[1])
            for path in paths.values()
        )
    )


def presentation_liquid_overlay_enabled(asset_source: str) -> bool:
    """The localized liquid scene gets a visual-only water treatment."""
    return asset_source == "localized_liquid"


def _stage_input_closure(stage: Any) -> dict[str, Any]:
    files: dict[str, str] = {}
    unresolved_layers: list[dict[str, str]] = []
    for layer in stage.GetUsedLayers():
        if bool(getattr(layer, "anonymous", False)):
            continue
        real_path = getattr(layer, "realPath", None)
        if not real_path:
            unresolved_layers.append(
                {
                    "identifier": str(layer.identifier),
                    "reason": "remote_or_virtual_layer",
                }
            )
            continue
        path = Path(real_path).resolve()
        if not path.is_file():
            unresolved_layers.append(
                {
                    "identifier": str(layer.identifier),
                    "reason": "local_layer_missing",
                }
            )
            continue
        files[str(path)] = probe._stable_file_bytes(path)[1]
    return {
        "complete": not unresolved_layers,
        "files": dict(sorted(files.items())),
        "unresolved_layers": sorted(
            unresolved_layers,
            key=lambda item: (item["identifier"], item["reason"]),
        ),
    }


def command_sequence_completed(records: Sequence[Mapping[str, Any]]) -> bool:
    pick_events = [
        item.get("pick_current_event")
        for item in records
        if isinstance(item.get("pick_current_event"), int)
    ]
    pour_events = [
        item.get("pour_current_event")
        for item in records
        if isinstance(item.get("pour_current_event"), int)
    ]
    return bool(
        pick_events
        and pour_events
        and max(pick_events) >= HISTORICAL_PICK_DONE_EVENT
        and max(pour_events) >= HISTORICAL_POUR_DONE_EVENT
    )


def historical_task_terminated(records: Sequence[Mapping[str, Any]]) -> bool:
    """Detect the historical task controller's own terminal return."""
    return any(
        item.get("phase_after") == "FINISHED"
        and item.get("done") is True
        and item.get("success") is True
        for item in records
        if isinstance(item, Mapping)
    )


class _HistoricalSourceWriterAudit:
    """Observe known source mutation APIs after historical episode startup."""

    _SOURCE_METHODS = (
        "set_world_pose",
        "set_local_pose",
        "set_linear_velocity",
        "set_angular_velocity",
    )
    _OBJECT_UTILS_METHOD = "set_object_position"

    def __init__(self, source_actor_path: str) -> None:
        self.source_actor_path = source_actor_path
        self._events: list[dict[str, Any]] = []
        self._coverage: dict[str, dict[str, Any]] = {}
        self._restores: list[tuple[Any, str, Any]] = []
        self._installed = False

    def _record(self, surface: str) -> None:
        self._events.append(
            {"sequence": len(self._events), "surface": surface}
        )

    def _instrument(self, target: Any, method_name: str, surface: str) -> None:
        original = getattr(target, method_name, None)
        coverage = {
            "surface": surface,
            "target_type": type(target).__name__,
            "method_name": method_name,
            "available": callable(original),
            "installed": False,
        }
        self._coverage[surface] = coverage
        if not callable(original):
            coverage["failure_reason"] = "callable_unavailable"
            return

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            self._record(surface)
            return original(*args, **kwargs)

        try:
            setattr(target, method_name, wrapped)
        except (AttributeError, TypeError) as exc:
            coverage["failure_reason"] = type(exc).__name__
            return
        self._restores.append((target, method_name, original))
        coverage["installed"] = True

    @staticmethod
    def _object_utils_path(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> str | None:
        value = kwargs.get("object_path", args[0] if args else None)
        return str(value) if value is not None else None

    def _instrument_object_utils(self, object_utils: Any) -> None:
        surface = f"object_utils.{self._OBJECT_UTILS_METHOD}"
        original = getattr(object_utils, self._OBJECT_UTILS_METHOD, None)
        coverage = {
            "surface": surface,
            "target_type": type(object_utils).__name__,
            "method_name": self._OBJECT_UTILS_METHOD,
            "available": callable(original),
            "installed": False,
        }
        self._coverage[surface] = coverage
        if not callable(original):
            coverage["failure_reason"] = "callable_unavailable"
            return

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if self._object_utils_path(args, kwargs) == self.source_actor_path:
                self._record(surface)
            return original(*args, **kwargs)

        try:
            setattr(object_utils, self._OBJECT_UTILS_METHOD, wrapped)
        except (AttributeError, TypeError) as exc:
            coverage["failure_reason"] = type(exc).__name__
            return
        self._restores.append((object_utils, self._OBJECT_UTILS_METHOD, original))
        coverage["installed"] = True

    def install(self, *, source_body: Any, object_utils: Any) -> None:
        if self._installed:
            return
        for method_name in self._SOURCE_METHODS:
            self._instrument(
                source_body,
                method_name,
                f"source_body.{method_name}",
            )
        self._instrument_object_utils(object_utils)
        self._installed = True

    def reset(self) -> None:
        self._events = []

    def record(self) -> dict[str, Any]:
        surfaces = [
            *(f"source_body.{name}" for name in self._SOURCE_METHODS),
            f"object_utils.{self._OBJECT_UTILS_METHOD}",
        ]
        counts = {surface: 0 for surface in surfaces}
        for event in self._events:
            counts[event["surface"]] += 1
        coverage_complete = self._installed and all(
            self._coverage.get(surface, {}).get("installed") is True
            for surface in surfaces
        )
        source_pose_writes = sum(
            counts[f"source_body.{name}"]
            for name in ("set_world_pose", "set_local_pose")
        ) + counts[f"object_utils.{self._OBJECT_UTILS_METHOD}"]
        source_velocity_writes = sum(
            counts[f"source_body.{name}"]
            for name in ("set_linear_velocity", "set_angular_velocity")
        )
        return {
            "source_actor_path": self.source_actor_path,
            "installed": self._installed,
            "coverage_complete": coverage_complete,
            "coverage": {
                surface: dict(self._coverage.get(surface, {}))
                for surface in surfaces
            },
            "calls": [dict(event) for event in self._events],
            "counts": counts,
            "source_pose_write_count_after_play": source_pose_writes,
            "source_velocity_write_count_after_play": source_velocity_writes,
            "valid": bool(
                coverage_complete
                and source_pose_writes == 0
                and source_velocity_writes == 0
            ),
            "coverage_limits": [
                "raw_usd_attribute_writes_not_intercepted",
                "source_prim_view_plural_pose_velocity_setters_not_intercepted",
                "instrumented_object_replacement_not_intercepted",
            ],
        }

    def close(self) -> None:
        while self._restores:
            target, method_name, original = self._restores.pop()
            setattr(target, method_name, original)


class _HistoricalPresentationLiquidOverlay:
    """Author a render-only water surface that follows the historical beaker."""

    def __init__(self, *, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self._summary: dict[str, Any] = {
            "enabled": self.enabled,
            "applied": False,
            "mode": "presentation_only_display_fill",
            "path": PRESENTATION_LIQUID_OVERLAY_PATH,
            "parent_path": PRESENTATION_LIQUID_OVERLAY_PARENT_PATH,
            "physics_schema_allowed": False,
            "follows_parent_transform": True,
        }

    @staticmethod
    def _world_points(stage: Any, path: str) -> list[tuple[float, float, float]]:
        from pxr import Gf, Usd, UsdGeom

        if not path:
            return []
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid() or not prim.IsA(UsdGeom.Points):
            return []
        points = UsdGeom.Points(prim).GetPointsAttr().Get(Usd.TimeCode.Default()) or []
        transform = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(
            prim
        )
        return [
            tuple(float(value) for value in transform.Transform(Gf.Vec3d(*point)))
            for point in points
        ]

    @staticmethod
    def _inside_frame(point: Sequence[float], frame: Any) -> bool:
        canonical = frame.world_to_canonical(point)
        return bool(
            frame.interior_floor <= canonical[2] < frame.rim_height
            and math.hypot(canonical[0], canonical[1])
            <= frame.interior_radius
        )

    @staticmethod
    def _fallback_points(frame: Any) -> tuple[tuple[float, float, float], ...]:
        """Seed the proxy deterministically if the scene has no readable points."""
        points = []
        radial_limit = frame.interior_radius * 0.82
        axial_span = frame.rim_height - frame.interior_floor
        golden_angle = math.pi * (3.0 - math.sqrt(5.0))
        for index in range(PRESENTATION_LIQUID_OVERLAY_POINT_COUNT):
            fraction = (index + 0.5) / PRESENTATION_LIQUID_OVERLAY_POINT_COUNT
            radius = radial_limit * math.sqrt(fraction)
            angle = golden_angle * index
            axial_fraction = 0.18 + 0.48 * ((index % 29) / 28.0)
            points.append(
                frame.canonical_to_world(
                    (
                        radius * math.cos(angle),
                        radius * math.sin(angle),
                        frame.interior_floor + axial_span * axial_fraction,
                    )
                )
            )
        return tuple(points)

    @staticmethod
    def _sample_points(
        points: Sequence[Sequence[float]],
    ) -> tuple[tuple[float, float, float], ...]:
        normalized = tuple(sorted(tuple(float(value) for value in point) for point in points))
        if len(normalized) <= PRESENTATION_LIQUID_OVERLAY_POINT_COUNT:
            return normalized
        stride = len(normalized) / PRESENTATION_LIQUID_OVERLAY_POINT_COUNT
        return tuple(
            normalized[min(int(index * stride), len(normalized) - 1)]
            for index in range(PRESENTATION_LIQUID_OVERLAY_POINT_COUNT)
        )

    @staticmethod
    def _to_parent_local(
        stage: Any,
        *,
        surface_frame: Mapping[str, Any],
        parent_path: str,
    ) -> dict[str, Any]:
        from pxr import Gf, Usd, UsdGeom

        parent = stage.GetPrimAtPath(parent_path)
        if not parent or not parent.IsValid():
            raise ValueError(f"presentation_liquid_parent_missing:{parent_path}")
        parent_world = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(
            parent
        )
        parent_inverse = parent_world.GetInverse()

        def point_local(point: Sequence[float]) -> tuple[float, float, float]:
            return tuple(
                float(value)
                for value in parent_inverse.Transform(Gf.Vec3d(*point))
            )

        def normal_local(normal: Sequence[float]) -> tuple[float, float, float]:
            vector = parent_inverse.TransformDir(Gf.Vec3d(*normal))
            length = math.sqrt(sum(float(vector[index]) ** 2 for index in range(3)))
            if not math.isfinite(length) or length <= 0.0:
                raise ValueError("presentation_liquid_normal_transform_invalid")
            return tuple(float(vector[index]) / length for index in range(3))

        local_frame = dict(surface_frame)
        local_frame["positions_world"] = [
            point_local(point) for point in surface_frame["positions_world"]
        ]
        local_frame["normals_world"] = [
            normal_local(normal) for normal in surface_frame["normals_world"]
        ]
        return local_frame

    @staticmethod
    def _layer_spec_paths(layer: Any) -> tuple[str, ...]:
        from pxr import Sdf

        paths: list[str] = []
        layer.Traverse(Sdf.Path.absoluteRootPath, lambda path: paths.append(str(path)))
        return tuple(sorted(paths))

    @staticmethod
    def _author_preview_water_material(stage: Any) -> None:
        from pxr import Gf, Sdf, UsdShade

        from pxr import UsdGeom

        looks_path = Sdf.Path("/World/Looks")
        if not stage.GetPrimAtPath(looks_path):
            UsdGeom.Scope.Define(stage, looks_path)
        material_path = Sdf.Path(PRESENTATION_LIQUID_OVERLAY_MATERIAL_PATH)
        material = UsdShade.Material.Define(stage, material_path)
        preview_path = material_path.AppendChild("PreviewSurface")
        shader_path = material_path.AppendChild("Shader")
        if stage.GetPrimAtPath(shader_path):
            stage.RemovePrim(shader_path)
        shader = UsdShade.Shader.Define(stage, preview_path)
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*PRESENTATION_WATER_PREVIEW_DIFFUSE_COLOR)
        )
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(*PRESENTATION_WATER_PREVIEW_EMISSIVE_COLOR)
        )
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(
            PRESENTATION_WATER_PREVIEW_OPACITY
        )
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(
            PRESENTATION_WATER_PREVIEW_ROUGHNESS
        )
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(
            PRESENTATION_WATER_PREVIEW_IOR
        )
        material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(), "surface"
        )

    def apply(self, stage: Any) -> dict[str, Any]:
        if not self.enabled:
            return dict(self._summary)
        from pxr import Sdf, Usd, UsdGeom, UsdShade

        from tools.labutopia_fluid import omniglass_reference, real_beaker

        frame_parent_path = PRESENTATION_LIQUID_OVERLAY_FRAME_PARENT_PATH
        attachment_parent_path = PRESENTATION_LIQUID_OVERLAY_PARENT_PATH
        visual_mesh_path = attachment_parent_path
        calibration_path = "/World/ParticleSet"
        calibration_prim = stage.GetPrimAtPath(calibration_path)
        if not calibration_prim or not calibration_prim.IsValid():
            calibration_path = None
        try:
            frame = real_beaker.derive_cup_interior_frame(
                stage,
                parent_path=frame_parent_path,
                visual_mesh_path=visual_mesh_path,
                calibration_points_path=calibration_path,
            )
        except ValueError:
            if calibration_path is None:
                raise
            frame = real_beaker.derive_cup_interior_frame(
                stage,
                parent_path=frame_parent_path,
                visual_mesh_path=visual_mesh_path,
                calibration_points_path=None,
            )
            calibration_path = None

        source_points = [
            point
            for point in self._world_points(stage, calibration_path or "")
            if self._inside_frame(point, frame)
        ]
        source_points = list(self._sample_points(source_points))
        source_basis = "localized_particle_points"
        if len(source_points) < 256:
            source_points = list(self._fallback_points(frame))
            source_basis = "deterministic_presentation_seed"

        candidate = omniglass_reference.build_reference_candidates(
            2.0 * frame.interior_radius
        )["OMNI_REF_DISPLAY_FILL"]
        surface_frame = omniglass_reference.build_display_fill_surface_frame(
            source_points,
            frame=frame,
            candidate=candidate,
            nominal_physical_particle_width=float(candidate["display_width"]),
        )

        layer = Sdf.Layer.CreateAnonymous(
            "historical_liquid_presentation_overlay.usda"
        )
        session = stage.GetSessionLayer()
        if layer is None or session is None:
            raise RuntimeError("historical_liquid_presentation_session_layer_missing")
        session.subLayerPaths.insert(0, layer.identifier)
        old_target = stage.GetEditTarget()
        sampler_targets_before: list[str] = []
        particle_targets_before: list[str] = []
        try:
            stage.SetEditTarget(Usd.EditTarget(layer))
            hidden_source_liquid_paths = []
            for source_path in (
                "/World/fluid",
                "/World/ParticleSet",
                "/World/ParticleSystem",
            ):
                source_prim = stage.GetPrimAtPath(source_path)
                if source_prim and source_prim.IsValid():
                    UsdGeom.Imageable(source_prim).MakeInvisible()
                    hidden_source_liquid_paths.append(source_path)
            self._author_preview_water_material(stage)
            local_surface_frame = self._to_parent_local(
                stage,
                surface_frame=surface_frame,
                parent_path=attachment_parent_path,
            )
            prim = omniglass_reference.author_presentation_surface(
                stage,
                path=PRESENTATION_LIQUID_OVERLAY_PATH,
                surface_frame=local_surface_frame,
                material_path=PRESENTATION_LIQUID_OVERLAY_MATERIAL_PATH,
            )
            UsdGeom.Imageable(prim).CreatePurposeAttr().Set(UsdGeom.Tokens.render)
            prim.CreateAttribute(
                "labutopia:historicalPresentationLiquidOverlay",
                Sdf.ValueTypeNames.Bool,
                custom=True,
            ).Set(True)
            prim.CreateAttribute(
                "labutopia:followsParentTransform",
                Sdf.ValueTypeNames.Bool,
                custom=True,
            ).Set(True)
        finally:
            stage.SetEditTarget(old_target)

        authored_paths = self._layer_spec_paths(layer)
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        schema_violations = [
            token
            for token in prim.GetAppliedSchemas()
            if "physx" in str(token).lower()
        ]
        relationship_violations = [
            relationship.GetName()
            for relationship in prim.GetRelationships()
            if relationship.GetName().lower().startswith("physx")
        ]
        layer_physx_specs = [
            path for path in authored_paths if "physx" in path.lower()
        ]
        if (
            schema_violations
            or relationship_violations
            or layer_physx_specs
            or str(material.GetPath()) != PRESENTATION_LIQUID_OVERLAY_MATERIAL_PATH
        ):
            raise RuntimeError("historical_liquid_presentation_overlay_invalid")

        self._summary = {
            **self._summary,
            "applied": True,
            "layer_identifier": str(layer.identifier),
            "layer_sha256": hashlib.sha256(
                layer.ExportToString().encode("utf-8")
            ).hexdigest(),
            "material_path": PRESENTATION_LIQUID_OVERLAY_MATERIAL_PATH,
            "hidden_source_liquid_paths": hidden_source_liquid_paths,
            "calibration_points_path": calibration_path,
            "source_basis": source_basis,
            "source_points_available": len(
                self._world_points(stage, calibration_path or "")
            ),
            "source_points_used": len(source_points),
            "authored_spec_paths": list(authored_paths),
            "layer_adds_physx_specs": False,
            "physx_schema_violations": schema_violations,
            "physx_relationship_violations": relationship_violations,
            "frame": frame.as_dict(),
            "surface": {
                "candidate_id": surface_frame["candidate_id"],
                "surface_model_version": surface_frame["surface_model_version"],
                "display_fill_height_m": surface_frame["display_fill_height_m"],
                "display_fill_low_z_m": surface_frame["display_fill_low_z_m"],
                "display_fill_high_z_m": surface_frame["display_fill_high_z_m"],
                "canonical_mesh_sha256": surface_frame["canonical_mesh_sha256"],
                "surface_geometry_contract_sha256": surface_frame[
                    "surface_geometry_contract_sha256"
                ],
                "presentation_only": surface_frame["presentation_only"],
                "physics_schema_allowed": surface_frame["physics_schema_allowed"],
                "fluid_dynamics_claim_allowed": surface_frame[
                    "fluid_dynamics_claim_allowed"
                ],
            },
        }
        return dict(self._summary)


class _HistoricalPhysicalPbdRuntime:
    """Reuse the reviewed PBD authoring chain under the historical controller."""

    def __init__(
        self,
        out_dir: Path,
        *,
        scene_path: Path,
        max_task_steps: int,
        particle_count: int,
        particle_seed: int,
    ) -> None:
        if particle_count <= 0:
            raise ValueError("historical_physical_pbd_particle_count_invalid")
        self.out_dir = out_dir
        self.scene_path = scene_path
        self.max_task_steps = max_task_steps
        self.particle_count = particle_count
        self.particle_seed = particle_seed
        self.trace_path = out_dir / "physical_pbd_particle_readback.jsonl"
        self._stream = None
        self._digest = hashlib.sha256()
        self._records: list[dict[str, Any]] = []
        self._last_physics_step: int | None = None
        self._prepared = False
        self._activated = False
        self._setup_error: str | None = None
        self._native = None
        self._real_beaker = None
        self._frame = None
        self._initial_frame = None
        self._classification_frames: list[Any] = []
        self._wrapper_parent_path = "/World/beaker2"
        self._classification_config = None
        self._log_cursor: dict[str, Any] | None = None
        self._physics_settings: dict[str, Any] | None = None
        self._wrapper_summary: dict[str, Any] | None = None
        self._authored_summary: dict[str, Any] | None = None
        self._material_summary: dict[str, Any] | None = None
        self._lighting_summary: dict[str, Any] | None = None
        self._visible_spawn_summary: dict[str, Any] | None = None
        self._controlled_spawn_plan: dict[str, Any] | None = None
        self._offsets: dict[str, float] | None = None
        self._selected_positions: list[tuple[float, float, float]] = []
        self._post_activation_reset_count = 0
        self._records_ignored_after_reset = 0

    def prepare(self, stage: Any) -> None:
        if self._prepared:
            return
        try:
            from pxr import Usd

            from tools.labutopia_fluid import real_beaker
            from tools.labutopia_fluid import (
                run_colleague_native_usd_completed_pbd_step_video as native,
            )
            from tools.labutopia_fluid.run_interndata_pour_parity_probe import (
                author_inner_wall_collision_proxy,
            )

            if not stage.GetPrimAtPath("/World/beaker2/mesh").IsValid():
                raise RuntimeError("historical_physical_pbd_source_mesh_missing")
            source_bbox = native._bbox_from_stage(stage, "/World/beaker2")
            target_bbox = native._bbox_from_stage(stage, "/World/beaker1")
            table_bbox = native._bbox_from_stage(stage, "/World/table")
            self._controlled_spawn_plan = native.build_controlled_spawn_plan(
                self.particle_count,
                particle_seed=self.particle_seed,
            )
            spawn_frame = native.build_full_scene_spawn_frame(
                source_bbox=source_bbox,
                target_bbox=target_bbox,
                table_top_z=float(table_bbox.max[2]),
                particle_count=self.particle_count,
            )
            spawn_config = native.build_controlled_spawn_collider_config(
                source_bbox=source_bbox,
                target_bbox=target_bbox,
                table_top_z=float(table_bbox.max[2]),
                plan=self._controlled_spawn_plan,
                steps=self.max_task_steps,
                trace_interval=1,
                tail_window_steps=min(self.max_task_steps, 30),
                render_width=256,
                render_height=256,
                physics_dt=1.0 / 60.0,
            )
            self._classification_config = native.build_classification_collider_config(
                spawn_config,
                classification_table_z=float(spawn_frame["classification_table_z"]),
            )
            offsets = {
                "particle_width": float(spawn_config.particle_width),
                "particle_contact_offset": float(spawn_config.particle_contact_offset),
                "particle_system_contact_offset": float(
                    spawn_config.particle_system_contact_offset
                ),
                "solid_rest_offset": float(spawn_config.solid_rest_offset),
                "fluid_rest_offset": float(spawn_config.fluid_rest_offset),
            }
            self._frame = real_beaker.derive_cup_interior_frame(
                stage,
                parent_path="/World/beaker2",
                visual_mesh_path="/World/beaker2/mesh",
                calibration_points_path="/World/ParticleSet",
            )
            self._initial_frame = self._frame
            visible_spawn = real_beaker.build_visible_beaker_spawn(
                self._frame,
                self._controlled_spawn_plan,
                physics_particle_width=offsets["particle_width"],
                particle_contact_offset=offsets["particle_contact_offset"],
                fluid_rest_offset=offsets["fluid_rest_offset"],
            )
            initial_counts = real_beaker.classify_visible_beaker_positions(
                visible_spawn.positions_world,
                self._frame,
                legacy_region_config=asdict(self._classification_config),
            )
            if (
                len(visible_spawn.positions_world) != self.particle_count
                or initial_counts["strict_violating_point_count"] != 0
            ):
                raise RuntimeError("historical_physical_pbd_spawn_validation_failed")

            self._log_cursor = native._capture_kit_log_cursor()
            self._wrapper_summary = author_inner_wall_collision_proxy(
                stage,
                frame=self._frame,
                parent_path=self._wrapper_parent_path,
                visual_mesh_path="/World/beaker2/mesh",
                dynamic_actor=True,
            )
            if (
                self._wrapper_summary.get("actor_path") != self._wrapper_parent_path
                or self._wrapper_summary.get("dynamic_actor_enabled") is not True
                or self._wrapper_summary.get("kinematic_actor_enabled") is not False
                or self._wrapper_summary.get("native_mesh_collision_enabled") is not False
            ):
                raise RuntimeError("historical_physical_pbd_wrapper_contract_failed")

            self._physics_settings = native._configure_physics_scene_for_pbd(
                stage,
                "/physicsScene",
                integration_dt=1.0 / 600.0,
                strict_mode=True,
            )
            self._material_summary = native._author_liquid_presentation_water_material(
                stage,
                attempt_mdl=False,
            )
            self._lighting_summary = native._author_liquid_presentation_lighting(stage)
            self._visible_spawn_summary = {
                "particle_count": visible_spawn.particle_count,
                "particle_seed": visible_spawn.particle_seed,
                "positions_sha256": visible_spawn.positions_sha256,
                "physics_particle_width": visible_spawn.physics_particle_width,
                "particle_contact_offset": visible_spawn.particle_contact_offset,
                "physics_offsets": dict(visible_spawn.physics_offsets),
                "canonical_bounds": dict(visible_spawn.canonical_bounds),
                "initial_visible_counts": initial_counts,
                "spawn_frame": native.spawn_frame_summary(spawn_frame),
            }
            self._selected_positions = [
                tuple(float(value) for value in point)
                for point in visible_spawn.positions_world
            ]
            self._native = native
            self._real_beaker = real_beaker
            self._offsets = offsets
            self._prepared = True
            self._setup_error = None
        except BaseException as exc:
            self._setup_error = f"{type(exc).__name__}:{exc}"
            raise

    @staticmethod
    def _isolate_legacy_particle_graph(stage: Any) -> dict[str, Any]:
        """Override referenced legacy particle relationships in a session layer."""
        from pxr import Sdf, Usd, UsdGeom

        session = stage.GetSessionLayer()
        layer = Sdf.Layer.CreateAnonymous("historical_pbd_legacy_isolation.usda")
        if session is None or layer is None:
            raise RuntimeError("historical_pbd_legacy_isolation_layer_missing")
        session.subLayerPaths.insert(0, layer.identifier)
        old_target = stage.GetEditTarget()
        try:
            stage.SetEditTarget(Usd.EditTarget(layer))
            sampler_path = "/World/fluid/Cylinder"
            sampler = stage.GetPrimAtPath(sampler_path)
            if sampler and sampler.IsValid():
                sampler = stage.OverridePrim(sampler_path)
                UsdGeom.Imageable(sampler).MakeInvisible()
                relation = sampler.GetRelationship("physxParticleSampling:particles")
                sampler_targets_before = (
                    [str(path) for path in relation.GetTargets()] if relation else []
                )
                if relation:
                    # Author an explicit empty target list so the referenced target
                    # is blocked instead of removing the override and revealing it.
                    relation.SetTargets([])
                volume = sampler.GetAttribute("physxParticleSampling:volume")
                if not volume:
                    volume = sampler.CreateAttribute(
                        "physxParticleSampling:volume", Sdf.ValueTypeNames.Bool
                    )
                volume.Set(False)

            particle_set_path = "/World/ParticleSet"
            particle_set = stage.GetPrimAtPath(particle_set_path)
            if particle_set and particle_set.IsValid():
                particle_set = stage.OverridePrim(particle_set_path)
                UsdGeom.Imageable(particle_set).MakeInvisible()
                relation = particle_set.GetRelationship("physxParticle:particleSystem")
                particle_targets_before = (
                    [str(path) for path in relation.GetTargets()] if relation else []
                )
                if relation:
                    relation.SetTargets([])
                for name in ("physxParticle:selfCollision", "physxParticle:fluid"):
                    attr = particle_set.GetAttribute(name)
                    if not attr:
                        attr = particle_set.CreateAttribute(name, Sdf.ValueTypeNames.Bool)
                    attr.Set(False)

            particle_system_path = "/World/ParticleSystem"
            particle_system = stage.GetPrimAtPath(particle_system_path)
            if particle_system and particle_system.IsValid():
                particle_system = stage.OverridePrim(particle_system_path)
                UsdGeom.Imageable(particle_system).MakeInvisible()
                attr = particle_system.GetAttribute("particleSystemEnabled")
                if not attr:
                    attr = particle_system.CreateAttribute(
                        "particleSystemEnabled", Sdf.ValueTypeNames.Bool
                    )
                attr.Set(False)

            fluid_path = "/World/fluid"
            fluid = stage.GetPrimAtPath(fluid_path)
            if fluid and fluid.IsValid():
                fluid = stage.OverridePrim(fluid_path)
                UsdGeom.Imageable(fluid).MakeInvisible()
        finally:
            stage.SetEditTarget(old_target)

        sampler = stage.GetPrimAtPath("/World/fluid/Cylinder")
        particle_set = stage.GetPrimAtPath("/World/ParticleSet")
        sampler_relation = (
            sampler.GetRelationship("physxParticleSampling:particles")
            if sampler and sampler.IsValid()
            else None
        )
        particle_relation = (
            particle_set.GetRelationship("physxParticle:particleSystem")
            if particle_set and particle_set.IsValid()
            else None
        )
        sampler_targets_after = (
            [str(path) for path in sampler_relation.GetTargets()]
            if sampler_relation
            else []
        )
        particle_targets_after = (
            [str(path) for path in particle_relation.GetTargets()]
            if particle_relation
            else []
        )
        summary = {
            "session_layer_identifier": str(layer.identifier),
            "session_layer_sha256": hashlib.sha256(
                layer.ExportToString().encode("utf-8")
            ).hexdigest(),
            "sampler_path": "/World/fluid/Cylinder",
            "sampler_targets_before": sampler_targets_before,
            "sampler_targets_after": sampler_targets_after,
            "particle_set_targets_before": particle_targets_before,
            "particle_set_targets_after": particle_targets_after,
            "synchronization_required": bool(
                sampler_targets_before or particle_targets_before
            ),
        }
        summary["verified"] = not sampler_targets_after and not particle_targets_after
        if not summary["verified"]:
            raise RuntimeError(
                "historical_pbd_legacy_session_override_failed:"
                + json.dumps(probe._json_native(summary), sort_keys=True)
            )
        summary["ownership_isolation"] = {
            "sampler_path": summary["sampler_path"],
            "sampler_targets_after": list(summary["sampler_targets_after"]),
            "particle_set_targets_after": list(summary["particle_set_targets_after"]),
            "synchronization_required": summary["synchronization_required"],
            "verified": summary["verified"],
        }
        return summary

    def activate(self, stage: Any) -> None:
        """Create the runtime particle buffer after historical World.reset()."""
        if not self._prepared or self._activated:
            return
        if self._native is None or self._offsets is None or self._controlled_spawn_plan is None:
            raise RuntimeError("historical_physical_pbd_activation_state_missing")
        try:
            import carb
            import omni.kit.app
            import omni.physx
            import omni.timeline

            isolation_summary = self._isolate_legacy_particle_graph(stage)
            ownership = isolation_summary.get("ownership_isolation")
            if not isinstance(ownership, Mapping) or ownership.get("verified") is not True:
                raise RuntimeError(
                    "historical_physical_pbd_legacy_isolation_invalid:"
                    + json.dumps(probe._json_native(isolation_summary), sort_keys=True)
                )
            synchronization = self._native.synchronize_legacy_particle_graph(
                app=omni.kit.app.get_app(),
                timeline=omni.timeline.get_timeline_interface(),
                settings=carb.settings.get_settings(),
                isolation_summary=isolation_summary,
                warmup_updates=1,
                strict_mode=True,
            )
            self._authored_summary = self._native._author_completed_pbd_runtime_particles(
                stage=stage,
                positions=self._selected_positions,
                widths=self._offsets,
                physics_scene_path="/physicsScene",
                visual_material_path=self._native.LIQUID_PRESENTATION_MATERIAL_PATH,
                presentation_isosurface_video=True,
                presentation_visual_material_path=self._native.LIQUID_PRESENTATION_MATERIAL_PATH,
                presentation_postprocess_overrides=None,
                display_particle_width=self._offsets["particle_width"],
                non_particle_rest_offset=self._offsets["solid_rest_offset"],
            )
            self._authored_summary["legacy_graph_isolation"] = isolation_summary
            self._authored_summary["legacy_graph_synchronization"] = synchronization
            omni.physx.get_physx_simulation_interface().flush_changes()
            self._last_physics_step = None
            if self._stream is None:
                self._stream = self.trace_path.open("xb")
            self._activated = True
        except BaseException as exc:
            self._setup_error = f"{type(exc).__name__}:{exc}"
            raise

    def note_world_reset(self) -> None:
        if self._activated:
            self._post_activation_reset_count += 1

    def record(self, stage: Any, physics_step: int) -> None:
        if not self._activated or self._stream is None:
            return
        if self._post_activation_reset_count:
            self._records_ignored_after_reset += 1
            return
        if self._last_physics_step == physics_step:
            return
        positions = self._native._read_points(
            stage, self._native.RUNTIME_PARTICLE_SET_PATH
        )
        self._frame = self._real_beaker.derive_authored_fluid_wrapper_frame(
            stage,
            parent_path=self._wrapper_parent_path,
            visual_mesh_path="/World/beaker2/mesh",
        )
        self._classification_frames.append(self._frame)
        visible_counts = self._real_beaker.classify_visible_beaker_positions(
            positions,
            self._frame,
            legacy_region_config=asdict(self._classification_config),
        )
        record = {
            "step_index": len(self._records),
            "physics_step": int(physics_step),
            "particle_count": len(positions),
            "positions": self._native._jsonable_positions(positions),
            "region_counts": self._native.compute_region_counts(
                positions, self._classification_config
            ),
            "visible_beaker_counts": visible_counts,
            "finite_count": visible_counts["finite_count"],
            "nonfinite_count": visible_counts["nonfinite_count"],
        }
        payload = json.dumps(
            probe._json_native(record),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self._stream.write(payload + b"\n")
        self._digest.update(payload + b"\n")
        self._records.append(record)
        self._last_physics_step = physics_step

    def close(self) -> dict[str, Any]:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        if not self._activated or self._native is None or self._real_beaker is None:
            return {
                "enabled": True,
                "prepared": False,
                "activated": self._activated,
                "setup_error": self._setup_error,
                "physical_observation_complete": False,
            }

        log_segment = self._native._read_kit_log_segment(self._log_cursor)
        diagnostic_scan_complete = bool(log_segment.get("diagnostic_scan_complete"))
        cpu_fallback, gpu_unsupported = self._real_beaker._scan_run_diagnostics(
            log_segment.get("log_text")
        )
        visible_classification = None
        if self._records:
            visible_classification = self._real_beaker.classify_visible_beaker_trace(
                self._records,
                self._frame,
                frame_sequence=self._classification_frames,
                requested_count=self.particle_count,
                steps=len(self._records) - 1,
                cadence=1,
                tail_window_steps=min(max(len(self._records) - 1, 0), 30),
                source_usd_sha256=_sha256_file(self.scene_path),
                particle_seed=self.particle_seed,
                legacy_region_config=asdict(self._classification_config),
                diagnostic_log_text=log_segment.get("log_text"),
                diagnostic_scan_complete=diagnostic_scan_complete,
                readback_available=True,
            )
        initial = self._records[0] if self._records else None
        final = self._records[-1] if self._records else None
        initial_hash = (
            self._native._position_hash(initial["positions"]) if initial else None
        )
        final_hash = (
            self._native._position_hash(final["positions"]) if final else None
        )
        readback_available = bool(initial and final)
        physical_simulation_executed = bool(
            len(self._records) > 1 and initial_hash != final_hash
        )
        trace_sha256 = _sha256_file(self.trace_path) if self.trace_path.is_file() else None
        observation_complete = bool(
            readback_available
            and physical_simulation_executed
            and diagnostic_scan_complete
            and not cpu_fallback
            and not gpu_unsupported
        )
        return {
            "enabled": True,
            "prepared": True,
            "setup_error": self._setup_error,
            "mode": "historical_controller_gpu_pbd",
            "particle_count": self.particle_count,
            "particle_seed": self.particle_seed,
            "physics_scene_path": "/physicsScene",
            "physics_settings": self._physics_settings,
            "visible_beaker_frame": (
                self._initial_frame.as_dict()
                if self._initial_frame is not None
                else self._frame.as_dict()
            ),
            "final_visible_beaker_frame": self._frame.as_dict(),
            "classification_frame_mode": "current_authored_wrapper_world_transform",
            "controlled_spawn_plan": self._controlled_spawn_plan,
            "visible_beaker_spawn": self._visible_spawn_summary,
            "canonical_inner_wall": self._wrapper_summary,
            "material": self._material_summary,
            "lighting": self._lighting_summary,
            "authored_runtime": self._authored_summary,
            "trace": {
                "path": str(self.trace_path),
                "record_count": len(self._records),
                "uncompressed_sha256": self._digest.hexdigest(),
                "compressed_sha256": None,
                "initial_position_hash": initial_hash,
                "final_position_hash": final_hash,
            },
            "post_activation_world_reset_count": self._post_activation_reset_count,
            "records_ignored_after_reset": self._records_ignored_after_reset,
            "readback": {
                "available": readback_available,
                "position_changed": physical_simulation_executed,
                "initial_particle_count": initial["particle_count"] if initial else None,
                "final_particle_count": final["particle_count"] if final else None,
            },
            "visible_beaker_classification": visible_classification,
            "diagnostics": self._native._kit_log_segment_summary(log_segment),
            "cpu_collision_fallback_detected": cpu_fallback,
            "gpu_collider_unsupported": gpu_unsupported,
            "physical_simulation_executed": physical_simulation_executed,
            "physical_observation_complete": observation_complete,
            "claim_boundary": {
                "allowed": [
                    "historical_controller_reused_with_gpu_pbd_runtime=true",
                    "controlled_4096_particle_readback_recorded=true",
                    "canonical_inner_wall_authored_as_dynamic_source_body_compound=true",
                    "physical_particle_motion_observed=true"
                    if physical_simulation_executed
                    else "physical_particle_motion_observed=false",
                ],
                "blocked": [
                    "historical_controller_terminal_equals_fluid_success=true",
                    "pour_trajectory_equals_zero_leak=true",
                    "presentation_video_equals_physics_success=true",
                    "controlled_4096_equals_raw_50k=true",
                ],
            },
        }


class _HistoricalContactRecorder:
    """Instrument World reset/step without changing historical controller behavior."""

    def __init__(
        self,
        out_dir: Path,
        *,
        presentation_liquid_overlay: bool,
        physical_pbd: bool,
        physical_pbd_scene_path: Path,
        physical_pbd_max_task_steps: int,
        physical_pbd_particle_count: int,
        physical_pbd_particle_seed: int,
    ) -> None:
        self.out_dir = out_dir
        self.trace_path = out_dir / "direct_physx_reports.jsonl.gz"
        self._stream = None
        self._digest = hashlib.sha256()
        self._record_count = 0
        self._collision_records: list[dict[str, Any]] = []
        self._original_step = None
        self._original_reset = None
        self._installed = False
        self._report_configured = False
        self._setup_error: str | None = None
        self._stage_id = None
        self._source_body_paths: tuple[str, ...] = ()
        self._robot_body_paths: tuple[str, ...] = ()
        self._source_reader = None
        self._source_writer_audit: _HistoricalSourceWriterAudit | None = None
        self._play_started = False
        self._report_layer_sha256: str | None = None
        self._stage_input_closure: dict[str, Any] | None = None
        self._presentation_liquid_overlay = _HistoricalPresentationLiquidOverlay(
            enabled=presentation_liquid_overlay
        )
        self._presentation_liquid_overlay_summary = (
            self._presentation_liquid_overlay.apply(None)
            if not presentation_liquid_overlay
            else None
        )
        self._physical_pbd_runtime = (
            _HistoricalPhysicalPbdRuntime(
                out_dir,
                scene_path=physical_pbd_scene_path,
                max_task_steps=physical_pbd_max_task_steps,
                particle_count=physical_pbd_particle_count,
                particle_seed=physical_pbd_particle_seed,
            )
            if physical_pbd
            else None
        )
        self._physical_pbd_summary: dict[str, Any] | None = None
        self._physical_timing_configured = False
        self._physical_substeps = 10 if physical_pbd else 1
        self._physical_timing: dict[str, Any] | None = None
        self._physical_reset_count = 0
        self._task_class = None
        self._original_task_reset = None

    def install_hook(self) -> None:
        from isaacsim.core.api import World

        self._original_step = World.step
        self._original_reset = World.reset

        def wrapped_step(world: Any, *args: Any, **kwargs: Any) -> Any:
            return self._step(world, *args, **kwargs)

        def wrapped_reset(world: Any, *args: Any, **kwargs: Any) -> Any:
            return self._reset(world, *args, **kwargs)

        World.step = wrapped_step
        World.reset = wrapped_reset
        self._world_class = World

    def restore_hook(self) -> None:
        if self._original_step is not None:
            self._world_class.step = self._original_step
            self._original_step = None
        if self._original_reset is not None:
            self._world_class.reset = self._original_reset
            self._original_reset = None
        if self._task_class is not None and self._original_task_reset is not None:
            self._task_class.reset = self._original_task_reset
            self._task_class = None
            self._original_task_reset = None

    def install_task_activation_hook(self) -> None:
        if self._physical_pbd_runtime is None:
            return
        from tasks.pickpour_task import PickPourTask

        self._task_class = PickPourTask
        self._original_task_reset = PickPourTask.reset

        def wrapped_reset(task: Any, *args: Any, **kwargs: Any) -> Any:
            result = self._original_task_reset(task, *args, **kwargs)
            if self._physical_pbd_runtime is not None:
                import omni.usd

                stage = omni.usd.get_context().get_stage()
                if stage is not None:
                    was_activated = self._physical_pbd_runtime._activated
                    self._physical_pbd_runtime.prepare(stage)
                    self._physical_pbd_runtime.activate(stage)
                    if not was_activated:
                        task.world.play()
                        self._original_step(task.world, render=False)
                        task.robot.initialize()
            return result

        PickPourTask.reset = wrapped_reset

    def _configure_report(self, world: Any) -> None:
        if self._report_configured:
            return
        try:
            import omni.usd
            from omni.physx import get_physx_simulation_interface
            from pxr import PhysxSchema, PhysicsSchemaTools, Sdf, Usd, UsdPhysics, UsdUtils

            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return
            source_root = stage.GetPrimAtPath("/World/beaker2")
            robot_root = stage.GetPrimAtPath("/World/Franka")
            if not source_root or not source_root.IsValid() or not robot_root or not robot_root.IsValid():
                return
            source_bodies = tuple(
                sorted(
                    str(prim.GetPath())
                    for prim in Usd.PrimRange(source_root)
                    if prim.HasAPI(UsdPhysics.RigidBodyAPI)
                )
            )
            robot_bodies = tuple(
                sorted(
                    str(prim.GetPath())
                    for prim in Usd.PrimRange(robot_root)
                    if prim.HasAPI(UsdPhysics.RigidBodyAPI)
                    and (
                        not prim.GetAttribute("physics:rigidBodyEnabled")
                        or prim.GetAttribute("physics:rigidBodyEnabled").Get()
                        is not False
                    )
                )
            )
            if not source_bodies or not robot_bodies:
                raise RuntimeError("historical_contact_bodies_missing")
            session = stage.GetSessionLayer()
            layer = Sdf.Layer.CreateAnonymous("historical_june_collision_observe.usda")
            if session is None or layer is None:
                raise RuntimeError("historical_contact_session_layer_missing")
            session.subLayerPaths.insert(0, layer.identifier)
            old_target = stage.GetEditTarget()
            try:
                stage.SetEditTarget(Usd.EditTarget(layer))
                for path in (*source_bodies, *robot_bodies):
                    prim = stage.GetPrimAtPath(path)
                    api = PhysxSchema.PhysxContactReportAPI.Apply(prim)
                    api.CreateThresholdAttr().Set(0.0)
                    api.CreateReportPairsRel().ClearTargets(True)
            finally:
                stage.SetEditTarget(old_target)
            get_physx_simulation_interface().flush_changes()
            if self._presentation_liquid_overlay.enabled:
                self._presentation_liquid_overlay_summary = (
                    self._presentation_liquid_overlay.apply(stage)
                )
            self._resolve_path = PhysicsSchemaTools.intToSdfPath
            self._simulation = get_physx_simulation_interface()
            self._stage_id = int(UsdUtils.StageCache.Get().GetId(stage).ToLongInt())
            self._source_body_paths = source_bodies
            self._robot_body_paths = robot_bodies
            self._report_layer_sha256 = hashlib.sha256(
                layer.ExportToString().encode("utf-8")
            ).hexdigest()
            self._stage_input_closure = _stage_input_closure(stage)
            self._report_configured = True
            self._setup_error = None
        except BaseException as exc:
            self._setup_error = f"{type(exc).__name__}:{exc}"

    def _initialize_source_reader(self) -> None:
        if not self._report_configured or self._installed:
            return
        try:
            from isaacsim.core.prims import SingleRigidPrim
            from utils.object_utils import ObjectUtils

            source_reader = SingleRigidPrim(
                prim_path=self._source_body_paths[0],
                name="historical_collision_source_reader",
            )
            source_reader.initialize()
            writer_audit = _HistoricalSourceWriterAudit("/World/beaker2")
            writer_audit.install(
                source_body=source_reader,
                object_utils=ObjectUtils.get_instance(),
            )
            self._stream = gzip.open(self.trace_path, "xb")
            self._source_reader = source_reader
            self._source_writer_audit = writer_audit
            self._installed = True
            self._setup_error = None
        except BaseException as exc:
            self._setup_error = f"{type(exc).__name__}:{exc}"

    def _ensure_installed(self, world: Any) -> None:
        self._configure_report(world)
        self._initialize_source_reader()

    @staticmethod
    def _event_name(value: Any) -> str:
        mapping = {"CONTACT_FOUND": "FOUND", "CONTACT_LOST": "LOST", "CONTACT_PERSIST": "PERSIST"}
        name = getattr(value, "name", None)
        if name in mapping:
            return mapping[name]
        numeric = {0: "FOUND", 1: "LOST", 2: "PERSIST"}
        try:
            return numeric[int(value)]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("historical_contact_event_invalid") from exc

    def _path(self, value: Any) -> str:
        path = str(self._resolve_path(int(value)))
        if not path:
            raise RuntimeError("historical_contact_path_unresolved")
        return path

    def _classify(self, header: Mapping[str, Any]) -> str:
        actors = (header["actor0"], header["actor1"])
        source = set(self._source_body_paths)
        robot = set(self._robot_body_paths)
        if set(actors) & source:
            other = actors[1] if actors[0] in source else actors[0]
            if other == "/World/Franka/panda_hand":
                return "SOURCE_HAND"
            if other == "/World/Franka/panda_leftfinger":
                return "SOURCE_LEFT_FINGER"
            if other == "/World/Franka/panda_rightfinger":
                return "SOURCE_RIGHT_FINGER"
            if other in robot:
                return "SOURCE_OTHER_ROBOT"
            return "SOURCE_ENVIRONMENT"
        robot_actors = [path for path in actors if path in robot]
        if len(robot_actors) == 2:
            return "ROBOT_SELF"
        if len(robot_actors) == 1:
            return "ROBOT_ENVIRONMENT"
        return "NONROBOT"

    def _capture(self, world: Any) -> None:
        if not self._installed or self._stream is None:
            return
        try:
            stage = None
            if self._physical_pbd_runtime is not None:
                import omni.usd

                stage = omni.usd.get_context().get_stage()
            raw = self._simulation.get_full_contact_report()
            if not isinstance(raw, tuple) or len(raw) != 3:
                raise RuntimeError("historical_contact_report_tuple_invalid")
            headers_raw, points_raw, anchors_raw = raw
            headers = []
            for value in headers_raw:
                header = {
                    "type": self._event_name(value.type),
                    "stage_id": int(value.stage_id),
                    "actor0": self._path(value.actor0),
                    "actor1": self._path(value.actor1),
                    "collider0": self._path(value.collider0),
                    "collider1": self._path(value.collider1),
                    "contact_data_offset": int(value.contact_data_offset),
                    "num_contact_data": int(value.num_contact_data),
                    "friction_anchors_offset": int(value.friction_anchors_offset),
                    "num_friction_anchors_data": int(value.num_friction_anchors_data),
                }
                if header["stage_id"] != self._stage_id:
                    raise RuntimeError("historical_contact_stage_mismatch")
                headers.append(header)
            points = [
                {
                    "position": probe._finite_vector(value.position, name="position"),
                    "normal": probe._finite_vector(value.normal, name="normal"),
                    "impulse": probe._finite_vector(value.impulse, name="impulse"),
                    "separation": float(value.separation),
                }
                for value in points_raw
            ]
            anchors = [
                {
                    "position": probe._finite_vector(value.position, name="anchor_position"),
                    "impulse": probe._finite_vector(value.impulse, name="anchor_impulse"),
                }
                for value in anchors_raw
            ]
            physics_step = int(world.current_time_step_index)
            classified = []
            for header in headers:
                record = {
                    "physics_step": physics_step,
                    "contact_class": self._classify(header),
                    **header,
                }
                classified.append(record)
                self._collision_records.append(record)
            source_state = None
            if self._source_reader is not None:
                position, orientation = self._source_reader.get_world_pose()
                source_state = {
                    "position_m": [float(item) for item in position],
                    "orientation_wxyz": [float(item) for item in orientation],
                }
            record = {
                "physics_step": physics_step,
                "headers": headers,
                "contact_data": points,
                "friction_anchors": anchors,
                "classified_headers": classified,
                "source_state": source_state,
            }
            payload = json.dumps(
                probe._json_native(record), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            self._stream.write(payload + b"\n")
            self._digest.update(payload + b"\n")
            self._record_count += 1
            if self._physical_pbd_runtime is not None and stage is not None:
                self._physical_pbd_runtime.record(stage, physics_step)
        except BaseException as exc:
            self._setup_error = f"{type(exc).__name__}:{exc}"

    def _step(self, world: Any, *args: Any, **kwargs: Any) -> Any:
        self._ensure_installed(world)
        if not self._play_started and self._source_writer_audit is not None:
            self._source_writer_audit.reset()
            self._play_started = True
        if self._physical_pbd_runtime is not None:
            self._configure_physical_timing(world)
            if not world.is_playing():
                world.play()
            substep_kwargs = dict(kwargs)
            substep_kwargs["render"] = False
            result = None
            for _ in range(self._physical_substeps):
                result = self._original_step(world, *args, **substep_kwargs)
            if kwargs.get("render", True):
                world.render()
        else:
            result = self._original_step(world, *args, **kwargs)
        self._ensure_installed(world)
        self._capture(world)
        return result

    def _configure_physical_timing(self, world: Any) -> None:
        if self._physical_pbd_runtime is None or self._physical_timing_configured:
            return
        world.set_simulation_dt(
            physics_dt=1.0 / 600.0,
            rendering_dt=1.0 / 60.0,
        )
        actual_physics_dt = float(world.get_physics_dt())
        actual_rendering_dt = float(world.get_rendering_dt())
        if not math.isclose(actual_physics_dt, 1.0 / 600.0, abs_tol=1.0e-12):
            raise RuntimeError("historical_physical_pbd_physics_dt_mismatch")
        if not math.isclose(actual_rendering_dt, 1.0 / 60.0, abs_tol=1.0e-12):
            raise RuntimeError("historical_physical_pbd_rendering_dt_mismatch")
        self._physical_timing = {
            "logical_dt": 1.0 / 60.0,
            "integration_dt": 1.0 / 600.0,
            "substeps_per_controller_step": self._physical_substeps,
            "physics_dt": actual_physics_dt,
            "rendering_dt": actual_rendering_dt,
            "step_owner": "isaacsim_world_explicit_substeps",
            "action_order": "physics_group_then_render_then_controller_action",
        }
        self._physical_timing_configured = True

    def _reset(self, world: Any, *args: Any, **kwargs: Any) -> Any:
        # Configure reporting before the reset that initializes physics bodies.
        self._configure_report(world)
        if self._physical_pbd_runtime is not None:
            self._physical_reset_count += 1
            self._physical_pbd_runtime.note_world_reset()
        result = self._original_reset(world, *args, **kwargs)
        if self._physical_pbd_runtime is not None:
            self._configure_physical_timing(world)
            import omni.timeline

            omni.timeline.get_timeline_interface().stop()

        self._ensure_installed(world)
        self._capture(world)
        return result

    def close(self) -> dict[str, Any]:
        if self._physical_pbd_runtime is not None:
            self._physical_pbd_summary = self._physical_pbd_runtime.close()
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        writer_audit = (
            self._source_writer_audit.record()
            if self._source_writer_audit is not None
            else None
        )
        if self._source_writer_audit is not None:
            self._source_writer_audit.close()
        return {
            "installed": self._installed,
            "report_configured": self._report_configured,
            "setup_error": self._setup_error,
            "play_started": self._play_started,
            "source_body_paths": list(self._source_body_paths),
            "robot_body_paths": list(self._robot_body_paths),
            "report_layer_sha256": self._report_layer_sha256,
            "stage_input_closure": self._stage_input_closure,
            "stage_input_closure_sha256": (
                probe._canonical_json_sha256(self._stage_input_closure)
                if self._stage_input_closure is not None
                else None
            ),
            "presentation_liquid_overlay": (
                self._presentation_liquid_overlay_summary
                if self._presentation_liquid_overlay_summary is not None
                else None
            ),
            "physical_pbd": self._physical_pbd_summary,
            "physical_pbd_reset_count": self._physical_reset_count,
            "physical_pbd_timing": self._physical_timing,
            "source_writer_audit": writer_audit,
            "collision_summary": observe.collision_summary(self._collision_records),
            "trace": {
                "path": str(self.trace_path),
                "record_count": self._record_count,
                "uncompressed_sha256": self._digest.hexdigest(),
                "compressed_sha256": (
                    _sha256_file(self.trace_path) if self.trace_path.is_file() else None
                ),
            },
        }


class _HistoricalControllerRecorder:
    def __init__(self, out_dir: Path, *, single_attempt_bound: bool = False) -> None:
        self.path = out_dir / "controller_ledger.jsonl"
        self._stream = None
        self._digest = hashlib.sha256()
        self.records: list[dict[str, Any]] = []
        self._original = None
        self._original_reset = None
        self._controller_class = None
        self._single_attempt_bound = bool(single_attempt_bound)
        self._reset_count = 0
        self._forced_episode_bound_applied = False

    def install(self) -> None:
        from controllers.pour_controller import PourTaskController

        self._stream = self.path.open("xb")
        self._original = PourTaskController.step
        self._original_reset = PourTaskController.reset

        def wrapped(controller: Any, state: Any) -> Any:
            phase_before = getattr(getattr(controller, "current_phase", None), "name", None)
            result = self._original(controller, state)
            action, done, success = result
            pick = getattr(controller, "pick_controller", None)
            pour = getattr(controller, "pour_controller", None)
            record = {
                "phase_before": phase_before,
                "phase_after": getattr(getattr(controller, "current_phase", None), "name", None),
                "pick_event": getattr(pick, "_last_emitted_event", None),
                "pick_current_event": getattr(pick, "_event", None),
                "pour_event": getattr(pour, "_last_emitted_event", None),
                "pour_current_event": getattr(pour, "_event", None),
                "action_present": action is not None,
                "done": bool(done),
                "success": bool(success),
            }
            payload = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self._stream.write(payload + b"\n")
            self._digest.update(payload + b"\n")
            self.records.append(record)
            return result

        PourTaskController.step = wrapped
        if self._single_attempt_bound:
            def reset_wrapped(controller: Any, *args: Any, **kwargs: Any) -> Any:
                result = self._original_reset(controller, *args, **kwargs)
                self._reset_count += 1
                if self._reset_count >= 2:
                    collector = getattr(controller, "data_collector", None)
                    if collector is not None and hasattr(collector, "episode_count"):
                        max_episodes = int(getattr(controller.cfg, "max_episodes", 1))
                        collector.episode_count = max(
                            int(collector.episode_count), max_episodes
                        )
                        self._forced_episode_bound_applied = True
                return result

            PourTaskController.reset = reset_wrapped
        self._controller_class = PourTaskController

    def close(self) -> dict[str, Any]:
        if self._original is not None:
            self._controller_class.step = self._original
            self._original = None
        if self._original_reset is not None:
            self._controller_class.reset = self._original_reset
            self._original_reset = None
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        return {
            "path": str(self.path),
            "record_count": len(self.records),
            "sha256": _sha256_file(self.path) if self.path.is_file() else None,
            "uncompressed_sha256": self._digest.hexdigest(),
            "command_sequence_completed": command_sequence_completed(self.records),
            "historical_task_terminated": historical_task_terminated(self.records),
            "single_attempt_bound": self._single_attempt_bound,
            "forced_episode_bound_applied": self._forced_episode_bound_applied,
            "controller_reset_count": self._reset_count,
        }


class _HistoricalRobotAssetResolver:
    """Inject the historical local Franka asset without changing controller code."""

    def __init__(self, asset_path: Path) -> None:
        self.asset_path = asset_path
        self.calls: list[dict[str, Any]] = []
        self._factory = None
        self._original = None

    def install(self) -> None:
        import factories.robot_factory as robot_factory

        self._factory = robot_factory
        self._original = robot_factory.create_robot

        def wrapped(robot_type: str, *args: Any, **kwargs: Any) -> Any:
            if robot_type != "franka":
                return self._original(robot_type, *args, **kwargs)
            requested_asset = kwargs.get("usd_path")
            if requested_asset not in (None, ""):
                raise RuntimeError("historical_robot_asset_override_unexpected")
            amended = dict(kwargs)
            amended["usd_path"] = str(self.asset_path)
            self.calls.append(
                {
                    "robot_type": robot_type,
                    "asset_path": str(self.asset_path),
                }
            )
            return self._original(robot_type, *args, **amended)

        robot_factory.create_robot = wrapped

    def close(self) -> None:
        if self._factory is not None and self._original is not None:
            self._factory.create_robot = self._original
            self._original = None

    def record(self) -> dict[str, Any]:
        return {
            "asset_path": str(self.asset_path),
            "asset_sha256": _sha256_file(self.asset_path),
            "calls": [dict(call) for call in self.calls],
            "resolved_locally": bool(self.calls),
        }


class _HistoricalAttachmentRecorder:
    """Record historical attachment requests without suppressing them."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self._gripper_class = None
        self._original = None

    def install(self) -> None:
        from controllers.robot_controllers.grapper_manager import Gripper

        self._gripper_class = Gripper
        self._original = Gripper.add_object_to_gripper

        def wrapped(gripper: Any, object_path: Any, gripper_frame_path: Any) -> Any:
            self.calls.append(
                {
                    "object_path": str(object_path),
                    "gripper_frame_path": str(gripper_frame_path),
                }
            )
            return self._original(gripper, object_path, gripper_frame_path)

        Gripper.add_object_to_gripper = wrapped

    def close(self) -> None:
        if self._gripper_class is not None and self._original is not None:
            self._gripper_class.add_object_to_gripper = self._original
            self._original = None

    def record(self) -> dict[str, Any]:
        return {
            "calls": [dict(call) for call in self.calls],
            "mechanical_attachment_used": bool(self.calls),
        }


class _HistoricalCollectModeInferenceShim:
    """Avoid an unavailable infer-only dependency in historical collect mode."""

    _PACKAGE_NAME = "controllers.inference_engines"
    _FACTORY_NAME = _PACKAGE_NAME + ".inference_engine_factory"

    def __init__(
        self,
        *,
        module_table: MutableMapping[str, Any] | None = None,
    ) -> None:
        self._modules = sys.modules if module_table is None else module_table
        self._previous: dict[str, Any] = {}
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        sentinel = object()
        self._previous = {
            name: self._modules.get(name, sentinel)
            for name in (self._PACKAGE_NAME, self._FACTORY_NAME)
        }

        class InferenceEngineFactory:
            @staticmethod
            def create_inference_engine(*_args: Any, **_kwargs: Any) -> Any:
                raise RuntimeError("historical_collect_mode_inference_unsupported")

        package = types.ModuleType(self._PACKAGE_NAME)
        package.__path__ = []
        factory = types.ModuleType(self._FACTORY_NAME)
        factory.InferenceEngineFactory = InferenceEngineFactory
        package.InferenceEngineFactory = InferenceEngineFactory
        self._modules[self._PACKAGE_NAME] = package
        self._modules[self._FACTORY_NAME] = factory
        self._sentinel = sentinel
        self._installed = True

    def close(self) -> None:
        if not self._installed:
            return
        for name, previous in self._previous.items():
            if previous is self._sentinel:
                self._modules.pop(name, None)
            else:
                self._modules[name] = previous
        self._previous = {}
        self._installed = False

    def record(self) -> dict[str, Any]:
        return {
            "installed": self._installed,
            "reason": "sealed_baseline_missing_zarr_for_historical_infer_only_import",
            "scope": "historical_collect_mode_only",
            "factory_behavior": "raises_if_inference_is_invoked",
        }


class _HistoricalApplicationProxy:
    """Let historical main return so the sealed child can write its evidence."""

    def __init__(self, application: Any) -> None:
        self._application = application
        self.close_request_count = 0

    def close(self) -> None:
        self.close_request_count += 1

    def __getattr__(self, name: str) -> Any:
        return getattr(self._application, name)


def historical_observation_complete(
    contact: Mapping[str, Any],
    *,
    attachment: Mapping[str, Any],
) -> bool:
    writer_audit = contact.get("source_writer_audit")
    trace = contact.get("trace")
    return bool(
        contact.get("installed") is True
        and contact.get("report_configured") is True
        and contact.get("setup_error") is None
        and contact.get("play_started") is True
        and isinstance(trace, Mapping)
        and trace.get("record_count", 0) > 0
        and isinstance(writer_audit, Mapping)
        and writer_audit.get("valid") is True
        and attachment.get("mechanical_attachment_used") is False
    )


def child_returncode_matches_decision(decision: Any, returncode: Any) -> bool:
    """Kit may terminate with zero after the child persisted a blocked report."""
    if not isinstance(decision, str) or isinstance(returncode, bool):
        return False
    if decision == "RUNTIME_BLOCKED":
        return returncode in (0, 2)
    return returncode == 0


def apply_historical_diagnostic_bounds(
    cfg: Any,
    *,
    max_task_steps: int,
    out_dir: Path,
    scene_path: Path | None = None,
) -> Any:
    """Apply bounded-run and explicitly selected asset overlays."""
    from omegaconf import open_dict

    with open_dict(cfg):
        cfg.max_episodes = 1
        cfg.task.max_steps = max_task_steps
        cfg.multi_run.run_dir = str(out_dir / "historical_controller_output")
        if scene_path is not None:
            cfg.usd_path = str(scene_path.resolve())
    return cfg


def _clear_project_modules() -> None:
    prefixes = ("controllers", "factories", "tasks", "robots", "utils", "data_collectors")
    for name in list(sys.modules):
        if name in prefixes or name.startswith(tuple(f"{item}." for item in prefixes)):
            del sys.modules[name]


def _run_historical_main(args: argparse.Namespace, *, app: Any) -> dict[str, Any]:
    historical_root = args.historical_root
    identity = historical_identity(historical_root)
    assets = historical_asset_paths(
        historical_root,
        asset_source=args.asset_source,
    )
    input_closure = historical_input_closure(
        historical_root,
        asset_source=args.asset_source,
    )
    recorder = _HistoricalContactRecorder(
        args.out_dir,
        presentation_liquid_overlay=presentation_liquid_overlay_enabled(
            args.asset_source
        ) and not args.physical_pbd,
        physical_pbd=args.physical_pbd,
        physical_pbd_scene_path=assets["scene"],
        physical_pbd_max_task_steps=args.max_task_steps,
        physical_pbd_particle_count=args.controlled_particle_count,
        physical_pbd_particle_seed=args.controlled_particle_seed,
    )
    controller_recorder = None
    robot_asset_resolver = None
    attachment_recorder = None
    inference_shim = None
    original_cwd = Path.cwd()
    original_argv = list(sys.argv)
    original_path = list(sys.path)
    original_compose = None
    original_simulation_app = None
    app_requests: list[dict[str, Any]] = []
    historical_application = _HistoricalApplicationProxy(app)
    try:
        from isaacsim_compat import install_legacy_isaacsim_aliases

        install_legacy_isaacsim_aliases()
        _clear_project_modules()
        sys.path[:] = [str(historical_root)] + [
            value for value in sys.path if Path(value or ".").resolve() != REPO_ROOT
        ]
        os.chdir(historical_root)
        inference_shim = _HistoricalCollectModeInferenceShim()
        inference_shim.install()
        import hydra
        import isaacsim
        import numpy as np

        np.random.seed(args.seed)
        original_compose = hydra.compose

        def compose_with_diagnostic_bounds(*compose_args: Any, **compose_kwargs: Any) -> Any:
            cfg = original_compose(*compose_args, **compose_kwargs)
            return apply_historical_diagnostic_bounds(
                cfg,
                max_task_steps=args.max_task_steps,
                out_dir=args.out_dir,
                scene_path=(
                    assets["scene"]
                    if args.asset_source in LOCALIZED_ASSET_SOURCES
                    else None
                ),
            )

        hydra.compose = compose_with_diagnostic_bounds
        original_simulation_app = isaacsim.SimulationApp

        def reuse_attested_application(
            application_config: Any, *app_args: Any, **app_kwargs: Any
        ) -> Any:
            if app_args or app_kwargs or not isinstance(application_config, Mapping):
                raise RuntimeError("historical_simulation_app_request_invalid")
            app_requests.append(probe._json_native(dict(application_config)))
            return historical_application

        isaacsim.SimulationApp = reuse_attested_application
        robot_asset_resolver = _HistoricalRobotAssetResolver(
            assets["robot"]
        )
        robot_asset_resolver.install()
        attachment_recorder = _HistoricalAttachmentRecorder()
        attachment_recorder.install()
        recorder.install_hook()
        recorder.install_task_activation_hook()
        controller_recorder = _HistoricalControllerRecorder(
            args.out_dir,
            single_attempt_bound=args.physical_pbd,
        )
        controller_recorder.install()
        sys.argv = [
            str(historical_root / "main.py"),
            "--backend",
            "gpu" if args.physical_pbd else "numpy",
            "--headless",
            "--config-name",
            "level1_pour",
            "--config-dir",
            "config",
            "--video-dir",
            str(args.out_dir / "video"),
        ]
        runpy.run_path(str(historical_root / "main.py"), run_name="__main__")
        controller = controller_recorder.close()
        controller_recorder = None
        attachment = attachment_recorder.record()
        robot_asset = robot_asset_resolver.record()
        inference_compatibility = inference_shim.record()
        contact = recorder.close()
        recorder.restore_hook()
        inference_shim.close()
        inference_shim = None
        attachment_recorder.close()
        attachment_recorder = None
        robot_asset_resolver.close()
        robot_asset_resolver = None
        expected_app_request = {
            "headless": True,
            "extra_args": ["--/rtx/raytracing/fractionalCutoutOpacity=true"],
        }
        if app_requests != [expected_app_request]:
            raise RuntimeError("historical_simulation_app_request_unexpected")
        if historical_application.close_request_count != 1:
            raise RuntimeError("historical_simulation_app_close_count_invalid")
        stage_input_closure = contact.get("stage_input_closure")
        stage_input_files = (
            stage_input_closure.get("files", {})
            if isinstance(stage_input_closure, Mapping)
            else {}
        )
        if not isinstance(stage_input_files, Mapping):
            raise RuntimeError("historical_stage_input_closure_invalid")
        input_closure = dict(
            sorted(
                {
                    **input_closure,
                    **stage_input_files,
                }.items()
            )
        )
        probe._require_unchanged_input_hashes(input_closure=input_closure)
        input_closure_complete = bool(
            isinstance(stage_input_closure, Mapping)
            and stage_input_closure.get("complete") is True
        )
        video_paths = sorted((args.out_dir / "video").glob("episode_*.mp4"))
        video_artifacts = [
            _artifact(path, root=args.out_dir) for path in video_paths
        ]
        observation_complete = historical_observation_complete(
            contact,
            attachment=attachment,
        )
        physical_pbd = contact.get("physical_pbd")
        physical_pbd_complete = bool(
            not args.physical_pbd
            or (
                isinstance(physical_pbd, Mapping)
                and physical_pbd.get("physical_observation_complete") is True
            )
        )
        if args.physical_pbd:
            if not observation_complete:
                decision = "HISTORICAL_PBD_OBSERVATION_INCOMPLETE"
            elif not physical_pbd_complete:
                decision = "HISTORICAL_PBD_READBACK_INCOMPLETE"
            elif not input_closure_complete:
                decision = "HISTORICAL_INPUT_CLOSURE_INCOMPLETE"
            elif not controller["historical_task_terminated"]:
                decision = "HISTORICAL_TASK_CONTROLLER_INCOMPLETE"
            else:
                decision = "HISTORICAL_PBD_CONTROLLER_TERMINATED"
        else:
            decision = (
                "HISTORICAL_TASK_CONTROLLER_TERMINATED"
                if (
                    observation_complete
                    and input_closure_complete
                    and controller["historical_task_terminated"]
                )
                else (
                    "HISTORICAL_OBSERVATION_INCOMPLETE"
                    if not observation_complete
                    else (
                        "HISTORICAL_INPUT_CLOSURE_INCOMPLETE"
                        if not input_closure_complete
                        else "HISTORICAL_TASK_CONTROLLER_INCOMPLETE"
                    )
                )
            )
        return {
            "schema_version": 1,
            "manifest_type": "historical_june_collision_observe_v1",
            "classification": "NON_FORMAL_HISTORICAL_REFERENCE",
            "decision": decision,
            "physics_mode": "gpu_pbd" if args.physical_pbd else "rigid_contact_observe",
            "historical_source": identity,
            "diagnostic_overlay": {
                "seed": args.seed,
                "max_episodes": 1,
                "max_task_steps": args.max_task_steps,
                "collision_policy": observe.COLLISION_POLICY,
                "source_mutation_audit": "known_source_writer_apis_after_first_world_step",
                "simulation_app": {
                    "attested_bootstrap": {"headless": True},
                    "historical_main_request": app_requests[0],
                    "historical_visual_extra_args_applied": False,
                    "historical_main_close_request_count": historical_application.close_request_count,
                },
                "robot_asset_resolution": robot_asset,
                "asset_source": args.asset_source,
                "scene_path": str(assets["scene"]),
                "collect_mode_inference_compatibility": inference_compatibility,
                "input_closure": input_closure,
                "input_closure_sha256": probe._canonical_json_sha256(input_closure),
                "input_closure_complete": input_closure_complete,
                "physics_mode": "gpu_pbd" if args.physical_pbd else "rigid_contact_observe",
                "controlled_particle_count": (
                    args.controlled_particle_count if args.physical_pbd else None
                ),
                "controlled_particle_seed": (
                    args.controlled_particle_seed if args.physical_pbd else None
                ),
                "presentation_liquid_overlay": contact.get(
                    "presentation_liquid_overlay"
                ),
            },
            "result": {
                "controller": controller,
                "contact": contact,
                "attachment": attachment,
                "observation_complete": observation_complete,
                "physical_pbd": physical_pbd,
                "physical_pbd_complete": physical_pbd_complete,
                "input_closure_complete": input_closure_complete,
                "video": video_artifacts,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if controller_recorder is not None:
            controller_recorder.close()
        if attachment_recorder is not None:
            attachment_recorder.close()
        if robot_asset_resolver is not None:
            robot_asset_resolver.close()
        if inference_shim is not None:
            inference_shim.close()
        recorder.close()
        recorder.restore_hook()
        if original_compose is not None:
            import hydra

            hydra.compose = original_compose
        if original_simulation_app is not None:
            import isaacsim

            isaacsim.SimulationApp = original_simulation_app
        sys.argv = original_argv
        sys.path[:] = original_path
        os.chdir(original_cwd)


def _run_child(args: argparse.Namespace) -> int:
    app = None
    runtime = None
    try:
        attestation = _attestation_module()
        identity = historical_identity(args.historical_root)
        paths = _source_paths(
            Path(attestation.__file__),
            args.historical_root,
            args.asset_source,
            physical_pbd=args.physical_pbd,
        )
        request = attestation._read_canonical_json(args.execution_request)
        request = attestation.verify_execution_request(request, source_paths=paths)
        runtime = probe.runtime_process_preflight(request)
        receipt, app = attestation.bootstrap_effective_runtime(
            execution_request=request,
            source_paths=paths,
        )
        attestation.write_canonical_json(args.runtime_receipt_path, receipt)
        binding = attestation.execution_binding_for_request(request, child_pid=os.getpid())
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        runtime.update(
            {
                "receipt_sha256": attestation.canonical_json_sha256(receipt),
                "execution_binding": binding,
                "historical_revision": identity["revision"],
            }
        )
        report = _run_historical_main(args, app=app)
        report["runtime"] = runtime
    except BaseException as exc:
        report = {
            "schema_version": 1,
            "manifest_type": "historical_june_collision_observe_v1",
            "classification": "NON_FORMAL_HISTORICAL_REFERENCE",
            "decision": "RUNTIME_BLOCKED",
            "runtime": runtime,
            "fatal_error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if not args.child_report_path.exists():
            probe._write_create_only(args.child_report_path, report)
        if app is not None:
            app.close()
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def _run_parent(args: argparse.Namespace) -> int:
    args.out_dir.mkdir(parents=True, mode=0o700)
    historical = historical_identity(args.historical_root)
    attestation = _attestation_module()
    paths = _source_paths(
        Path(attestation.__file__),
        args.historical_root,
        args.asset_source,
        physical_pbd=args.physical_pbd,
    )
    source_before = attestation.capture_source_identity(paths)
    request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    request_path = args.out_dir / "execution_request.json"
    receipt_path = args.out_dir / "runtime_receipt.json"
    child_report_path = args.out_dir / "child_report.json"
    attestation.write_canonical_json(request_path, request)
    environment = attestation.sealed_child_environment(args.out_dir / "runtime")
    command = [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--historical-root",
        str(args.historical_root),
        "--out-dir",
        str(args.out_dir),
        "--seed",
        str(args.seed),
        "--max-task-steps",
        str(args.max_task_steps),
        "--asset-source",
        args.asset_source,
        *(["--physical-pbd"] if args.physical_pbd else []),
        *(
            [
                "--controlled-particle-count",
                str(args.controlled_particle_count),
                "--controlled-particle-seed",
                str(args.controlled_particle_seed),
            ]
            if args.physical_pbd
            else []
        ),
        "--execution-request",
        str(request_path),
    ]
    stdout_path = args.out_dir / "child.stdout.log"
    stderr_path = args.out_dir / "child.stderr.log"
    child_pid = None
    child_returncode = None
    receipt = None
    verification_failure = None
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            child_pid = process.pid
            try:
                child_returncode = process.wait(timeout=args.timeout_s)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                child_returncode = process.wait()
                raise RuntimeError("historical_collision_observe_child_timeout")
        report = json.loads(child_report_path.read_text(encoding="utf-8"))
        if not isinstance(report, Mapping):
            raise RuntimeError("historical_collision_observe_child_report_invalid")
        receipt = attestation._read_canonical_json(receipt_path)
        binding = attestation.execution_binding_for_request(request, child_pid=child_pid)
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        if (
            report.get("runtime", {}).get("receipt_sha256")
            != attestation.canonical_json_sha256(receipt)
            or not child_returncode_matches_decision(
                report.get("decision"), child_returncode
            )
        ):
            raise RuntimeError("historical_collision_observe_child_verification_invalid")
        report = dict(report)
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        report = {
            "schema_version": 1,
            "manifest_type": "historical_june_collision_observe_v1",
            "classification": "NON_FORMAL_HISTORICAL_REFERENCE",
            "decision": "RUNTIME_BLOCKED",
            "fatal_error": verification_failure,
        }
    finally:
        manifest = {
            "schema_version": 1,
            "manifest_type": "historical_june_collision_observe_parent_manifest_v1",
            "classification": "NON_FORMAL_HISTORICAL_REFERENCE",
            "historical_source": historical,
            "asset_source": args.asset_source,
            "command": command,
            "source_before": source_before,
            "source_after": attestation.capture_source_identity(paths),
            "execution_request_sha256": attestation.canonical_json_sha256(request),
            "runtime_receipt_sha256": (
                attestation.canonical_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None
            ),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "child_returncode_compatible": child_returncode_matches_decision(
                report.get("decision"), child_returncode
            ),
            "sanitized_environment_sha256": attestation.canonical_json_sha256(
                dict(sorted(environment.items()))
            ),
            "runtime_receipt": _artifact(receipt_path, root=args.out_dir),
            "child_report": _artifact(child_report_path, root=args.out_dir),
            "stdout": _artifact(stdout_path, root=args.out_dir),
            "stderr": _artifact(stderr_path, root=args.out_dir),
            "verification_failure": verification_failure,
        }
        attestation.write_canonical_json(args.out_dir / "run_manifest.json", manifest)
    probe._write_create_only(args.out_dir / "report.json", report)
    print(
        f"historical collision-observe decision={report['decision']} out={args.out_dir / 'report.json'}",
        flush=True,
    )
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def _artifact(path: Path, *, root: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return {
        "path": str(path.relative_to(root)),
        "byte_count": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-root", type=Path, default=DEFAULT_HISTORICAL_ROOT)
    parser.add_argument(
        "--asset-source",
        choices=("localized", "localized_liquid", "historical_raw"),
        default="localized",
        help=(
            "Use the localized empty scene, localized liquid scene, "
            "or raw historical scene."
        ),
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260609)
    parser.add_argument("--max-task-steps", type=int, default=1500)
    parser.add_argument("--timeout-s", type=float, default=3600.0)
    parser.add_argument(
        "--physical-pbd",
        action="store_true",
        help=(
            "Reuse the reviewed GPU PBD runtime and canonical inner-wall wrapper "
            "under the historical controller. Requires localized_liquid."
        ),
    )
    parser.add_argument(
        "--controlled-particle-count",
        type=int,
        default=PHYSICAL_PBD_DEFAULT_PARTICLE_COUNT,
    )
    parser.add_argument(
        "--controlled-particle-seed",
        type=int,
        default=PHYSICAL_PBD_DEFAULT_PARTICLE_SEED,
    )
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.historical_root = args.historical_root.resolve()
    args.out_dir = args.out_dir.resolve()
    if args.max_task_steps <= 0 or args.seed < 0:
        parser.error("seed and max-task-steps must be nonnegative/positive")
    if not math.isfinite(args.timeout_s) or args.timeout_s <= 0.0:
        parser.error("timeout-s must be positive")
    if args.physical_pbd and args.asset_source != "localized_liquid":
        parser.error("--physical-pbd requires --asset-source localized_liquid")
    if args.physical_pbd and args.controlled_particle_count <= 0:
        parser.error("controlled-particle-count must be positive")
    if args.physical_pbd and args.controlled_particle_seed < 0:
        parser.error("controlled-particle-seed must be nonnegative")
    historical_identity(args.historical_root)
    historical_asset_paths(
        args.historical_root,
        asset_source=args.asset_source,
    )
    if args.child:
        if args.execution_request is None:
            parser.error("--child requires --execution-request")
        args.execution_request = args.execution_request.resolve()
        if not args.out_dir.is_dir() or not args.execution_request.is_file():
            parser.error("child inputs must exist")
        args.child_report_path = args.out_dir / "child_report.json"
        args.runtime_receipt_path = args.out_dir / "runtime_receipt.json"
    elif args.execution_request is not None or args.out_dir.exists():
        parser.error("parent out-dir must not exist")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_child(args) if args.child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
