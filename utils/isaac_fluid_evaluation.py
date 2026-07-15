"""Isaac-specific adapters for the online fluid evaluation loop."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any, Callable

import numpy as np


STRICT_CONTAINMENT_EPSILON_M = 0.00005
TABLETOP_SPILL_BAND_M = 0.02


def construct_single_rigid_prim(
    single_rigid_prim_type: Any,
    *,
    prim_path: str,
    name: str,
) -> Any:
    kwargs = {"prim_path": prim_path, "name": name}
    if "reset_xform_properties" in inspect.signature(
        single_rigid_prim_type
    ).parameters:
        kwargs["reset_xform_properties"] = False
    return single_rigid_prim_type(**kwargs)


def configure_fluid_world_timing(
    world: Any,
    *,
    physics_dt: float,
    rendering_dt: float,
) -> None:
    world.set_simulation_dt(
        physics_dt=physics_dt,
        rendering_dt=rendering_dt,
    )
    actual_physics_dt = float(world.get_physics_dt())
    actual_rendering_dt = float(world.get_rendering_dt())
    if not math.isclose(actual_physics_dt, physics_dt, abs_tol=1.0e-12):
        raise RuntimeError(
            "fluid_world_physics_dt_mismatch:"
            f"expected={physics_dt}:actual={actual_physics_dt}"
        )
    if not math.isclose(actual_rendering_dt, rendering_dt, abs_tol=1.0e-12):
        raise RuntimeError(
            "fluid_world_rendering_dt_mismatch:"
            f"expected={rendering_dt}:actual={actual_rendering_dt}"
        )


def _inside_frame(point: np.ndarray, frame: Any, epsilon: float) -> bool:
    canonical = frame.world_to_canonical(point)
    return (
        math.hypot(float(canonical[0]), float(canonical[1]))
        <= float(frame.interior_radius) + epsilon
        and float(canonical[2]) >= float(frame.interior_floor) - epsilon
        and float(canonical[2]) < float(frame.rim_height) - epsilon
    )


def classify_transfer_positions(
    positions_world: Any,
    *,
    source_frame: Any,
    target_frame: Any,
    table_z: float,
    minimum_target_particles: int,
    minimum_task_target_fraction: float,
    minimum_expert_target_fraction: float,
    epsilon: float = STRICT_CONTAINMENT_EPSILON_M,
    tabletop_spill_band_m: float = TABLETOP_SPILL_BAND_M,
) -> dict[str, Any]:
    values = np.asarray(positions_world, dtype=np.float64)
    if values.ndim != 2 or values.shape[1:] != (3,):
        raise ValueError("transfer_positions_shape_invalid")
    if type(minimum_target_particles) is not int or minimum_target_particles <= 0:
        raise ValueError("minimum_target_particles_invalid")
    for name, fraction in (
        ("minimum_task_target_fraction", minimum_task_target_fraction),
        ("minimum_expert_target_fraction", minimum_expert_target_fraction),
    ):
        if (
            isinstance(fraction, bool)
            or not isinstance(fraction, (int, float, np.number))
            or not math.isfinite(float(fraction))
            or not 0.0 < float(fraction) <= 1.0
        ):
            raise ValueError(f"{name}_invalid")
    if minimum_expert_target_fraction < minimum_task_target_fraction:
        raise ValueError("minimum_expert_target_fraction_below_task")
    if not math.isfinite(table_z):
        raise ValueError("table_z_invalid")

    counts = {
        "source": 0,
        "target": 0,
        "below_table": 0,
        "tabletop_spill": 0,
        "transit": 0,
        "nonfinite": 0,
    }
    category_points = {
        name: []
        for name in ("source", "target", "below_table", "tabletop_spill", "transit")
    }
    for point in values:
        if not np.isfinite(point).all():
            counts["nonfinite"] += 1
            continue
        if _inside_frame(point, source_frame, epsilon):
            category = "source"
        elif _inside_frame(point, target_frame, epsilon):
            category = "target"
        elif point[2] < table_z - epsilon:
            category = "below_table"
        elif point[2] <= table_z + tabletop_spill_band_m:
            category = "tabletop_spill"
        else:
            category = "transit"
        counts[category] += 1
        category_points[category].append(point)

    category_bounds = {}
    for category, points in category_points.items():
        if not points:
            continue
        category_values = np.asarray(points, dtype=np.float64)
        category_bounds[category] = {
            "min": category_values.min(axis=0).tolist(),
            "max": category_values.max(axis=0).tolist(),
        }

    particle_count = int(len(values))
    finite_total = sum(counts[key] for key in counts if key != "nonfinite")
    partition_complete = finite_total + counts["nonfinite"] == particle_count
    valid = counts["nonfinite"] == 0 and partition_complete
    strict_transfer_passed = (
        valid
        and counts["target"] >= minimum_target_particles
        and counts["below_table"] == 0
        and counts["tabletop_spill"] == 0
        and counts["transit"] == 0
    )
    fractions = {
        f"{name}_fraction": float(count) / particle_count
        for name, count in counts.items()
    }
    fractions["spill_fraction"] = (
        float(counts["tabletop_spill"] + counts["below_table"])
        / particle_count
    )
    fractions["partition_fraction_total"] = sum(
        fractions[f"{name}_fraction"] for name in counts
    )
    task_transfer_passed = (
        valid
        and counts["target"] >= minimum_target_particles
        and fractions["target_fraction"]
        >= float(minimum_task_target_fraction)
    )
    expert_transfer_passed = (
        valid
        and counts["target"] >= minimum_target_particles
        and fractions["target_fraction"]
        >= float(minimum_expert_target_fraction)
    )
    return {
        **counts,
        **fractions,
        "particle_count": particle_count,
        "finite_partition_total": finite_total,
        "partition_complete": partition_complete,
        "valid": valid,
        "fluid_transfer_passed": strict_transfer_passed,
        "strict_zero_spill_transfer_passed": strict_transfer_passed,
        "task_transfer_passed": task_transfer_passed,
        "expert_transfer_passed": expert_transfer_passed,
        "minimum_target_particles": minimum_target_particles,
        "minimum_task_target_fraction": float(minimum_task_target_fraction),
        "minimum_expert_target_fraction": float(minimum_expert_target_fraction),
        "epsilon_m": float(epsilon),
        "tabletop_spill_band_m": float(tabletop_spill_band_m),
        "category_bounds_world_m": category_bounds,
        "assignment_priority": [
            "nonfinite",
            "source",
            "target",
            "below_table",
            "tabletop_spill",
            "transit",
        ],
    }


def scripted_grasp_is_closed(controller: Any) -> bool:
    phase = getattr(getattr(controller, "current_phase", None), "value", None)
    pick_controller = getattr(controller, "pick_controller", None)
    event = getattr(pick_controller, "_event", -1)
    return phase == "picking" and isinstance(event, int) and event >= 5


def scripted_pour_velocity_was_emitted(controller: Any) -> bool:
    phase = getattr(getattr(controller, "current_phase", None), "value", None)
    pour_controller = getattr(controller, "pour_controller", None)
    emitted_event = getattr(pour_controller, "_last_emitted_event", None)
    return phase == "pouring" and emitted_event == 2


def _controller_request(controller: Any, name: str) -> bool | None:
    request = getattr(controller, name, None)
    if not callable(request):
        return None
    result = request()
    if type(result) is not bool:
        raise TypeError(f"{name}_must_return_bool")
    return result


def fluid_grasp_attachment_requested(controller: Any) -> bool:
    requested = _controller_request(
        controller, "online_fluid_grasp_attachment_requested"
    )
    return scripted_grasp_is_closed(controller) if requested is None else requested


def fluid_rotation_handoff_requested(controller: Any) -> bool:
    requested = _controller_request(
        controller, "online_fluid_rotation_handoff_requested"
    )
    return (
        scripted_pour_velocity_was_emitted(controller)
        if requested is None
        else requested
    )


def _affine_matrix(value: Any, *, name: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(f"{name}_matrix_invalid")
    if not np.allclose(matrix[:, 3], [0.0, 0.0, 0.0, 1.0], atol=1.0e-10):
        raise ValueError(f"{name}_matrix_not_row_affine")
    return np.ascontiguousarray(matrix)


def _rigid_affine_matrix(value: Any, *, name: str) -> np.ndarray:
    matrix = _affine_matrix(value, name=name)
    rotation = matrix[:3, :3]
    if not np.allclose(
        rotation @ rotation.T,
        np.eye(3, dtype=np.float64),
        rtol=0.0,
        atol=1.0e-6,
    ):
        raise ValueError(f"{name}_matrix_not_rigid")
    determinant = float(np.linalg.det(rotation))
    if not math.isclose(determinant, 1.0, rel_tol=0.0, abs_tol=1.0e-6):
        raise ValueError(f"{name}_matrix_not_right_handed")
    return matrix


def _matrix_sha256(matrix: np.ndarray) -> str:
    encoded = json.dumps(
        matrix.tolist(),
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def relative_source_to_gripper_matrix(
    source_world_matrix: Any,
    gripper_world_matrix: Any,
) -> np.ndarray:
    source = _affine_matrix(source_world_matrix, name="source_world")
    gripper = _affine_matrix(gripper_world_matrix, name="gripper_world")
    return np.ascontiguousarray(source @ np.linalg.inv(gripper))


def attached_source_world_matrix(
    source_to_gripper_matrix: Any,
    gripper_world_matrix: Any,
) -> np.ndarray:
    relative = _affine_matrix(source_to_gripper_matrix, name="source_to_gripper")
    gripper = _affine_matrix(gripper_world_matrix, name="gripper_world")
    return np.ascontiguousarray(relative @ gripper)


def _pose_jump(before: Any, after: Any) -> tuple[float, float]:
    source = _rigid_affine_matrix(before, name="pose_jump_before")
    target = _rigid_affine_matrix(after, name="pose_jump_after")
    translation = float(np.linalg.norm(target[3, :3] - source[3, :3]))
    relative_rotation = source[:3, :3] @ target[:3, :3].T
    cosine = float(np.clip((np.trace(relative_rotation) - 1.0) / 2.0, -1.0, 1.0))
    rotation_degrees = float(np.degrees(np.arccos(cosine)))
    return translation, rotation_degrees


class GripperAttachedKinematicVessel:
    """Transport upright, then follow the gripper rigidly for scripted pouring."""

    def __init__(
        self,
        *,
        read_source_world_matrix: Callable[[], Any],
        read_gripper_world_matrix: Callable[[], Any],
        write_source_world_matrix: Callable[[np.ndarray], None],
    ) -> None:
        self._read_source = read_source_world_matrix
        self._read_gripper = read_gripper_world_matrix
        self._write_source = write_source_world_matrix
        self._initial_source = _affine_matrix(
            read_source_world_matrix(), name="initial_source_world"
        ).copy()
        self._attach_source: np.ndarray | None = None
        self._attach_gripper: np.ndarray | None = None
        self._observed_relative: np.ndarray | None = None
        self._active_relative: np.ndarray | None = None
        self._pre_attach_source: np.ndarray | None = None
        self._first_attachment_target: np.ndarray | None = None
        self._pre_pour_handoff_source: np.ndarray | None = None
        self._first_pour_handoff_target: np.ndarray | None = None
        self._attachment_translation_jump_m: float | None = None
        self._attachment_rotation_jump_degrees: float | None = None
        self._pour_handoff_translation_jump_m: float | None = None
        self._pour_handoff_rotation_jump_degrees: float | None = None
        self._attachment_count = 0
        self._rotation_handoff_count = 0
        self._target_update_count = 0

    def reset(self) -> None:
        self._attach_source = None
        self._attach_gripper = None
        self._observed_relative = None
        self._active_relative = None
        self._pre_attach_source = None
        self._first_attachment_target = None
        self._pre_pour_handoff_source = None
        self._first_pour_handoff_target = None
        self._attachment_translation_jump_m = None
        self._attachment_rotation_jump_degrees = None
        self._pour_handoff_translation_jump_m = None
        self._pour_handoff_rotation_jump_degrees = None
        self._attachment_count = 0
        self._rotation_handoff_count = 0
        self._target_update_count = 0
        self._write_source(self._initial_source.copy())

    def _upright_transport_target(self, gripper: Any) -> np.ndarray:
        if self._attach_source is None or self._attach_gripper is None:
            raise RuntimeError("upright_transport_requires_attachment")
        current_gripper = _rigid_affine_matrix(
            gripper, name="upright_transport_gripper_world"
        )
        target = self._attach_source.copy()
        target[3, :3] += (
            current_gripper[3, :3] - self._attach_gripper[3, :3]
        )
        return _rigid_affine_matrix(target, name="upright_transport_target_world")

    def maybe_attach(self, controller: Any, state: Mapping[str, Any]) -> bool:
        del state
        if self._attach_source is None:
            if not fluid_grasp_attachment_requested(controller):
                return False
            source = _rigid_affine_matrix(
                self._read_source(), name="attach_source_world"
            )
            gripper = _rigid_affine_matrix(
                self._read_gripper(), name="attach_gripper_world"
            )
            self._attach_source = source.copy()
            self._attach_gripper = gripper.copy()
            self._observed_relative = relative_source_to_gripper_matrix(
                source, gripper
            )
            self._pre_attach_source = source.copy()
            self._first_attachment_target = self._upright_transport_target(gripper)
            (
                self._attachment_translation_jump_m,
                self._attachment_rotation_jump_degrees,
            ) = _pose_jump(source, self._first_attachment_target)
            self._attachment_count += 1
            return True

        if (
            self._active_relative is None
            and fluid_rotation_handoff_requested(controller)
        ):
            source = _rigid_affine_matrix(
                self._read_source(), name="pour_handoff_source_world"
            )
            gripper = _rigid_affine_matrix(
                self._read_gripper(), name="pour_handoff_gripper_world"
            )
            relative = relative_source_to_gripper_matrix(source, gripper)
            target = attached_source_world_matrix(relative, gripper)
            self._pre_pour_handoff_source = source.copy()
            self._first_pour_handoff_target = target.copy()
            (
                self._pour_handoff_translation_jump_m,
                self._pour_handoff_rotation_jump_degrees,
            ) = _pose_jump(source, target)
            self._active_relative = relative.copy()
            self._rotation_handoff_count += 1
            return True
        return False

    def update_before_substep(self) -> None:
        if self._attach_source is None:
            return
        gripper = self._read_gripper()
        if self._active_relative is None:
            target = self._upright_transport_target(gripper)
        else:
            target = attached_source_world_matrix(self._active_relative, gripper)
        self._write_source(target)
        self._target_update_count += 1

    def record(self) -> dict[str, Any]:
        attached = self._attach_source is not None
        handoff_complete = self._active_relative is not None
        jump_values = (
            self._attachment_translation_jump_m,
            self._attachment_rotation_jump_degrees,
            self._pour_handoff_translation_jump_m,
            self._pour_handoff_rotation_jump_degrees,
        )
        expert_attachment_valid = (
            attached
            and self._attachment_count == 1
            and handoff_complete
            and self._rotation_handoff_count == 1
            and self._observed_relative is not None
            and all(value is not None for value in jump_values)
            and self._attachment_translation_jump_m <= 1.0e-9
            and self._attachment_rotation_jump_degrees <= 1.0e-5
            and self._pour_handoff_translation_jump_m <= 1.0e-9
            and self._pour_handoff_rotation_jump_degrees <= 1.0e-5
        )
        return {
            "mode": "gripper_attached_kinematic_vessel",
            "contact_grasp_claimed": False,
            "attached": attached,
            "attachment_count": self._attachment_count,
            "rotation_handoff_count": self._rotation_handoff_count,
            "attachment_stage": (
                "unattached"
                if not attached
                else "full_rigid_pour"
                if handoff_complete
                else "upright_translation"
            ),
            "kinematic_target_update_count": self._target_update_count,
            "attachment_matrix_policy": (
                "captured_translation_then_recaptured_full_at_scripted_pour"
            ),
            "expert_attachment_valid": expert_attachment_valid,
            "observed_source_to_gripper_matrix": (
                None
                if self._observed_relative is None
                else self._observed_relative.tolist()
            ),
            "observed_matrix_sha256": (
                None
                if self._observed_relative is None
                else _matrix_sha256(self._observed_relative)
            ),
            "applied_source_to_gripper_matrix": (
                None
                if self._active_relative is None
                else self._active_relative.tolist()
            ),
            "applied_matrix_sha256": (
                None
                if self._active_relative is None
                else _matrix_sha256(self._active_relative)
            ),
            "pre_attach_source_world_matrix": (
                None
                if self._pre_attach_source is None
                else self._pre_attach_source.tolist()
            ),
            "first_attachment_target_world_matrix": (
                None
                if self._first_attachment_target is None
                else self._first_attachment_target.tolist()
            ),
            "attachment_translation_jump_m": self._attachment_translation_jump_m,
            "attachment_rotation_jump_degrees": (
                self._attachment_rotation_jump_degrees
            ),
            "pour_handoff_source_to_gripper_matrix": (
                None
                if self._active_relative is None
                else self._active_relative.tolist()
            ),
            "pour_handoff_matrix_sha256": (
                None
                if self._active_relative is None
                else _matrix_sha256(self._active_relative)
            ),
            "pre_pour_handoff_source_world_matrix": (
                None
                if self._pre_pour_handoff_source is None
                else self._pre_pour_handoff_source.tolist()
            ),
            "first_pour_handoff_target_world_matrix": (
                None
                if self._first_pour_handoff_target is None
                else self._first_pour_handoff_target.tolist()
            ),
            "pour_handoff_translation_jump_m": (
                self._pour_handoff_translation_jump_m
            ),
            "pour_handoff_rotation_jump_degrees": (
                self._pour_handoff_rotation_jump_degrees
            ),
            "pour_handoff_trigger_event": 2 if handoff_complete else None,
            "source_to_gripper_matrix": (
                None
                if self._active_relative is None
                else self._active_relative.tolist()
            ),
        }


def _vt_vec3f_array(values: Any) -> Any:
    from pxr import Gf, Vt

    contiguous = np.ascontiguousarray(values, dtype=np.float32)
    converter = getattr(Vt.Vec3fArray, "FromNumpy", None)
    if converter is not None:
        return converter(contiguous)
    return Vt.Vec3fArray([Gf.Vec3f(*row) for row in contiguous.tolist()])


def _vt_int_array(values: Any) -> Any:
    from pxr import Vt

    contiguous = np.ascontiguousarray(values, dtype=np.int32).reshape(-1)
    converter = getattr(Vt.IntArray, "FromNumpy", None)
    if converter is not None:
        return converter(contiguous)
    return Vt.IntArray(contiguous.tolist())


class IsaacFluidSurfaceAuthor:
    """Author the sole visible liquid mesh for the current particle token."""

    def __init__(
        self,
        *,
        stage: Any,
        surface_path: str,
        material_path: str,
        hidden_liquid_paths: Sequence[str],
        particle_system_path: str,
    ) -> None:
        for name, path in (
            ("surface", surface_path),
            ("material", material_path),
            ("particle_system", particle_system_path),
        ):
            if not isinstance(path, str) or not path.startswith("/"):
                raise ValueError(f"{name}_path_invalid")
        self.stage = stage
        self.surface_path = surface_path
        self.material_path = material_path
        self.hidden_liquid_paths = tuple(hidden_liquid_paths)
        self.particle_system_path = particle_system_path
        self._configured = False

    def _configure_visual_authority(self, surface_prim: Any) -> dict[str, Any]:
        from pxr import UsdGeom

        hidden = []
        for path in self.hidden_liquid_paths:
            prim = self.stage.GetPrimAtPath(path)
            if prim and prim.IsValid() and prim.IsA(UsdGeom.Imageable):
                UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(
                    UsdGeom.Tokens.invisible
                )
                hidden.append(path)
        system = self.stage.GetPrimAtPath(self.particle_system_path)
        native_isosurface_disabled = False
        if system and system.IsValid():
            attribute = system.GetAttribute(
                "physxParticleIsosurface:isosurfaceEnabled"
            )
            if attribute:
                attribute.Set(False)
                native_isosurface_disabled = True
        UsdGeom.Imageable(surface_prim).CreateVisibilityAttr().Set(
            UsdGeom.Tokens.inherited
        )
        return {
            "visible_liquid_path": self.surface_path,
            "hidden_liquid_paths": hidden,
            "native_isosurface_disabled": native_isosurface_disabled,
        }

    def _bind_material(self, surface_prim: Any) -> dict[str, Any]:
        from pxr import Gf, Sdf, UsdGeom, UsdShade

        parent_path = self.material_path.rsplit("/", 1)[0]
        if not self.stage.GetPrimAtPath(parent_path).IsValid():
            UsdGeom.Scope.Define(self.stage, parent_path)
        material = UsdShade.Material.Define(self.stage, self.material_path)
        shader = UsdShade.Shader.Define(
            self.stage, f"{self.material_path}/PreviewSurface"
        )
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(0.46, 0.82, 0.96)
        )
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
            Gf.Vec3f(0.01, 0.025, 0.035)
        )
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.06)
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.06)
        shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.333)
        material.CreateSurfaceOutput().ConnectToSource(
            shader.ConnectableAPI(), "surface"
        )
        UsdShade.MaterialBindingAPI.Apply(surface_prim).Bind(material)
        return {
            "material_path": self.material_path,
            "shader": "UsdPreviewSurface",
        }

    def __call__(self, mesh_data: Mapping[str, Any], token: Any) -> dict[str, Any]:
        from pxr import Gf, Sdf, UsdGeom, Vt

        vertices = np.ascontiguousarray(mesh_data["vertices"], dtype=np.float32)
        faces = np.ascontiguousarray(mesh_data["faces"], dtype=np.int32)
        normals = np.ascontiguousarray(mesh_data["normals"], dtype=np.float32)
        origin = np.asarray(mesh_data["origin_world_m"], dtype=np.float64)
        if (
            vertices.ndim != 2
            or vertices.shape[1:] != (3,)
            or faces.ndim != 2
            or faces.shape[1:] != (3,)
            or normals.shape != vertices.shape
            or origin.shape != (3,)
        ):
            raise ValueError("surface_author_mesh_shape_invalid")

        mesh = UsdGeom.Mesh.Define(self.stage, self.surface_path)
        prim = mesh.GetPrim()
        prim.CreateAttribute(
            "xformOp:translate", Sdf.ValueTypeNames.Double3, custom=False
        ).Set(Gf.Vec3d(*origin.tolist()))
        prim.CreateAttribute(
            "xformOpOrder", Sdf.ValueTypeNames.TokenArray, custom=False
        ).Set(Vt.TokenArray(["xformOp:translate"]))
        mesh.CreatePointsAttr().Set(_vt_vec3f_array(vertices))
        mesh.CreateFaceVertexCountsAttr().Set(
            _vt_int_array(np.full(len(faces), 3, dtype=np.int32))
        )
        mesh.CreateFaceVertexIndicesAttr().Set(_vt_int_array(faces))
        mesh.CreateNormalsAttr().Set(_vt_vec3f_array(normals))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateExtentAttr().Set(
            _vt_vec3f_array(
                np.asarray(
                    [vertices.min(axis=0), vertices.max(axis=0)], dtype=np.float32
                )
            )
        )
        mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        mesh.CreateOrientationAttr().Set(UsdGeom.Tokens.rightHanded)
        mesh.CreateDoubleSidedAttr().Set(False)
        mesh.CreatePurposeAttr().Set(UsdGeom.Tokens.render)
        mesh.CreateVisibilityAttr().Set(UsdGeom.Tokens.inherited)
        prim.CreateAttribute(
            "labutopia:surfaceFrameToken", Sdf.ValueTypeNames.String, custom=True
        ).Set(token.identity)

        authority = None
        material = None
        if not self._configured:
            material = self._bind_material(prim)
            authority = self._configure_visual_authority(prim)
            self._configured = True
        return {
            "path": self.surface_path,
            "surface_token": token.identity,
            "vertex_count": int(len(vertices)),
            "face_count": int(len(faces)),
            "origin_world_m": origin.tolist(),
            "visual_authority": authority,
            "material": material,
        }

    def invalidate(self, reason: str) -> None:
        from pxr import Sdf, UsdGeom

        prim = self.stage.GetPrimAtPath(self.surface_path)
        if prim and prim.IsValid() and prim.IsA(UsdGeom.Imageable):
            UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(
                UsdGeom.Tokens.invisible
            )
            prim.CreateAttribute(
                "labutopia:surfaceInvalidationReason",
                Sdf.ValueTypeNames.String,
                custom=True,
            ).Set(str(reason))


def _config_value(node: Any, name: str) -> Any:
    if isinstance(node, Mapping):
        return node[name]
    return getattr(node, name)


def configure_particle_usd_readback() -> dict[str, Any]:
    """Enable current GPU particle state readback before World initialization."""
    import carb
    import omni.physx.bindings._physx as pb

    settings = carb.settings.get_settings()
    settings.set_bool("/physics/suppressReadback", False)
    applied = {"/physics/suppressReadback": False}
    for constant_name in (
        "SETTING_UPDATE_TO_USD",
        "SETTING_UPDATE_PARTICLES_TO_USD",
        "SETTING_UPDATE_VELOCITIES_TO_USD",
    ):
        path = getattr(pb, constant_name, None)
        if path:
            settings.set(path, True)
            applied[str(path)] = True
    return applied


def author_synthetic_attachment_collision_filter(
    stage: Any,
    *,
    source_body_path: str,
    robot_root_path: str,
) -> dict[str, Any]:
    """Keep a synthetic kinematic grasp from colliding with its carrier."""
    from pxr import Sdf, Usd, UsdPhysics

    source = stage.GetPrimAtPath(source_body_path)
    if not source or not source.IsValid():
        raise RuntimeError(f"synthetic_attachment_source_missing:{source_body_path}")
    if not source.HasAPI(UsdPhysics.RigidBodyAPI):
        raise RuntimeError("synthetic_attachment_source_rigid_body_required")
    kinematic = source.GetAttribute("physics:kinematicEnabled")
    if not kinematic or kinematic.Get() is not True:
        raise RuntimeError("synthetic_attachment_source_kinematic_required")

    robot_root = stage.GetPrimAtPath(robot_root_path)
    if not robot_root or not robot_root.IsValid():
        raise RuntimeError(f"synthetic_attachment_robot_missing:{robot_root_path}")
    robot_body_paths = []
    for prim in Usd.PrimRange(robot_root):
        if not prim.HasAPI(UsdPhysics.RigidBodyAPI):
            continue
        enabled = prim.GetAttribute("physics:rigidBodyEnabled")
        if enabled and enabled.Get() is False:
            continue
        robot_body_paths.append(str(prim.GetPath()))
    robot_body_paths.sort()
    if not robot_body_paths:
        raise RuntimeError("synthetic_attachment_robot_rigid_bodies_missing")

    filtered_pairs = UsdPhysics.FilteredPairsAPI.Apply(source)
    relationship = filtered_pairs.CreateFilteredPairsRel()
    targets = {str(path) for path in relationship.GetTargets()}
    targets.update(robot_body_paths)
    relationship.SetTargets([Sdf.Path(path) for path in sorted(targets)])
    return {
        "source_body_path": source_body_path,
        "robot_root_path": robot_root_path,
        "robot_rigid_body_paths": robot_body_paths,
    }


def validate_fluid_stage_contract(stage: Any, fluid_cfg: Any) -> dict[str, Any]:
    from pxr import Usd, UsdPhysics

    physics_scene_path = str(_config_value(fluid_cfg, "physics_scene_path"))
    scenes = [
        str(prim.GetPath())
        for prim in Usd.PrimRange.Stage(stage)
        if prim.IsA(UsdPhysics.Scene)
    ]
    if scenes != [physics_scene_path]:
        raise RuntimeError(
            f"fluid_physics_scene_contract_invalid:expected={physics_scene_path}:"
            f"actual={scenes}"
        )
    required_paths = (
        str(_config_value(fluid_cfg, "particle_path")),
        str(_config_value(fluid_cfg, "particle_system_path")),
        str(_config_value(fluid_cfg, "source_actor_path")),
        str(_config_value(fluid_cfg, "target_actor_path")),
        str(_config_value(fluid_cfg, "gripper_frame_path")),
    )
    missing = [path for path in required_paths if not stage.GetPrimAtPath(path).IsValid()]
    if missing:
        raise RuntimeError(f"fluid_stage_required_prims_missing:{missing}")
    source = stage.GetPrimAtPath(str(_config_value(fluid_cfg, "source_actor_path")))
    kinematic = source.GetAttribute("physics:kinematicEnabled")
    if not kinematic or kinematic.Get() is not True:
        raise RuntimeError("fluid_source_must_be_kinematic")
    return {
        "physics_scene_paths": scenes,
        "required_prim_paths": list(required_paths),
        "source_kinematic": True,
    }


def _prim_world_matrix(stage: Any, prim_path: str) -> np.ndarray:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"world_matrix_prim_missing:{prim_path}")
    matrix = UsdGeom.XformCache(Usd.TimeCode.Default()).GetLocalToWorldTransform(prim)
    values = np.asarray(
        [[float(matrix[row][column]) for column in range(4)] for row in range(4)],
        dtype=np.float64,
    )
    return _affine_matrix(values, name="prim_world")


def _optional_config_value(node: Any, name: str, default: Any = None) -> Any:
    if isinstance(node, Mapping):
        return node.get(name, default)
    return getattr(node, name, default)


def resolve_camera_contract_record(
    stage: Any,
    *,
    contract_id: str,
    camera_configs: Sequence[Any],
    compatibility: str,
    rendering_dt: float,
) -> dict[str, Any]:
    from pxr import UsdGeom

    if not isinstance(contract_id, str) or not contract_id:
        raise ValueError("camera_contract_id_invalid")
    if not isinstance(compatibility, str) or not compatibility:
        raise ValueError("camera_contract_compatibility_invalid")
    if not math.isfinite(rendering_dt) or rendering_dt <= 0.0:
        raise ValueError("camera_contract_rendering_dt_invalid")
    configs = tuple(camera_configs)
    if not configs:
        raise ValueError("camera_configs_required")

    cameras = []
    for config in configs:
        prim_path = str(_config_value(config, "prim_path"))
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid() or not prim.IsA(UsdGeom.Camera):
            raise RuntimeError(f"camera_prim_invalid:{prim_path}")
        camera = UsdGeom.Camera(prim)
        focal_length = float(camera.GetFocalLengthAttr().Get())
        horizontal_aperture = float(camera.GetHorizontalApertureAttr().Get())
        vertical_aperture = float(camera.GetVerticalApertureAttr().Get())
        clipping_range = [
            float(value) for value in camera.GetClippingRangeAttr().Get()
        ]

        expected_focal_length = float(_config_value(config, "focal_length"))
        if not math.isclose(
            focal_length, expected_focal_length, rel_tol=0.0, abs_tol=1.0e-6
        ):
            raise ValueError(
                f"camera_focal_length_mismatch:{prim_path}:"
                f"expected={expected_focal_length}:actual={focal_length}"
            )
        expected_clipping = _optional_config_value(config, "clipping_range")
        if expected_clipping is not None and not np.allclose(
            clipping_range,
            np.asarray(expected_clipping, dtype=np.float64),
            rtol=0.0,
            atol=1.0e-6,
        ):
            raise ValueError(
                f"camera_clipping_range_mismatch:{prim_path}:"
                f"expected={list(expected_clipping)}:actual={clipping_range}"
            )
        frequency = _optional_config_value(config, "frequency", 60)
        if type(frequency) is not int or frequency <= 0:
            raise ValueError(f"camera_frequency_invalid:{prim_path}")

        cameras.append(
            {
                "name": str(_config_value(config, "name")),
                "prim_path": prim_path,
                "resolution": [
                    int(value) for value in _config_value(config, "resolution")
                ],
                "image_type": str(_config_value(config, "image_type")),
                "frequency": frequency,
                "focal_length": focal_length,
                "horizontal_aperture": horizontal_aperture,
                "vertical_aperture": vertical_aperture,
                "clipping_range": clipping_range,
                "world_transform": _prim_world_matrix(stage, prim_path).tolist(),
            }
        )

    payload = {
        "schema_version": 2,
        "id": contract_id,
        "compatibility": compatibility,
        "rendering_dt": float(rendering_dt),
        "cameras": cameras,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {**payload, "sha256": hashlib.sha256(encoded).hexdigest()}


def require_camera_contract_sha256(
    record: Mapping[str, Any],
    *,
    expected_sha256: str,
) -> Mapping[str, Any]:
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValueError("camera_contract_expected_sha256_invalid")
    if record.get("sha256") != expected_sha256:
        raise ValueError(
            "camera_contract_sha256_mismatch:"
            f"expected={expected_sha256}:actual={record.get('sha256')}"
        )
    return record


def _matrix_to_world_pose(matrix: Any) -> tuple[np.ndarray, np.ndarray]:
    from pxr import Gf

    values = _affine_matrix(matrix, name="world_pose")
    gf_matrix = Gf.Matrix4d(*values.reshape(-1).tolist())
    quaternion = gf_matrix.ExtractRotationQuat()
    imaginary = quaternion.GetImaginary()
    orientation_wxyz = np.asarray(
        [
            float(quaternion.GetReal()),
            float(imaginary[0]),
            float(imaginary[1]),
            float(imaginary[2]),
        ],
        dtype=np.float64,
    )
    return values[3, :3].copy(), orientation_wxyz


def _world_pose_to_matrix(
    position: Any,
    orientation_wxyz: Any,
) -> np.ndarray:
    """Convert an Isaac scalar-first pose to the row-affine matrix used by Gf."""
    translation = np.asarray(position, dtype=np.float64)
    orientation = np.asarray(orientation_wxyz, dtype=np.float64)
    if translation.shape != (3,) or not np.isfinite(translation).all():
        raise ValueError("world_pose_position_invalid")
    if orientation.shape != (4,) or not np.isfinite(orientation).all():
        raise ValueError("world_pose_orientation_invalid")
    norm = float(np.linalg.norm(orientation))
    if norm <= 0.0:
        raise ValueError("world_pose_orientation_invalid")
    w, x, y, z = orientation / norm
    column_rotation = np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)],
            [2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)],
            [2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = column_rotation.T
    result[3, :3] = translation
    return _affine_matrix(result, name="world_pose")


def _single_rigid_world_matrix(single_rigid_prim: Any) -> np.ndarray:
    getter = getattr(single_rigid_prim, "get_world_pose", None)
    if not callable(getter):
        raise TypeError("single_rigid_world_pose_reader_required")
    position, orientation_wxyz = getter()
    return _world_pose_to_matrix(position, orientation_wxyz)


def _tracked_child_world_matrix(
    *,
    child_authored_world: Any,
    parent_authored_world: Any,
    parent_current_world: Any,
) -> np.ndarray:
    child = _affine_matrix(child_authored_world, name="child_authored_world")
    authored_parent = _affine_matrix(
        parent_authored_world, name="parent_authored_world"
    )
    current_parent = _affine_matrix(
        parent_current_world, name="parent_current_world"
    )
    child_to_parent = child @ np.linalg.inv(authored_parent)
    return _affine_matrix(child_to_parent @ current_parent, name="child_current_world")


class SourceVisualMeshSynchronizer:
    """Align a collision-free source display mesh with the live PhysX body."""

    def __init__(
        self,
        *,
        source_authored_world_matrix: Any,
        read_source_world_matrix: Callable[[], Any],
        read_visual_mesh_world_matrix: Callable[[], Any],
        write_visual_mesh_parent_delta: Callable[[np.ndarray], None],
        translation_tolerance_m: float = 1.0e-5,
        linear_tolerance: float = 1.0e-5,
    ) -> None:
        if not callable(read_source_world_matrix):
            raise TypeError("source_visual_sync_source_reader_required")
        if not callable(read_visual_mesh_world_matrix):
            raise TypeError("source_visual_sync_mesh_reader_required")
        if not callable(write_visual_mesh_parent_delta):
            raise TypeError("source_visual_sync_mesh_writer_required")
        if (
            not math.isfinite(translation_tolerance_m)
            or translation_tolerance_m < 0.0
        ):
            raise ValueError("source_visual_sync_translation_tolerance_invalid")
        if not math.isfinite(linear_tolerance) or linear_tolerance < 0.0:
            raise ValueError("source_visual_sync_linear_tolerance_invalid")
        self._source_authored_world = _rigid_affine_matrix(
            source_authored_world_matrix,
            name="source_visual_sync_source_authored_world",
        ).copy()
        self._read_source_world = read_source_world_matrix
        self._read_visual_mesh_world = read_visual_mesh_world_matrix
        self._write_visual_mesh_parent_delta = write_visual_mesh_parent_delta
        self._translation_tolerance_m = float(translation_tolerance_m)
        self._linear_tolerance = float(linear_tolerance)
        self._write_visual_mesh_parent_delta(np.eye(4, dtype=np.float64))
        self._visual_mesh_authored_world = _affine_matrix(
            self._read_visual_mesh_world(),
            name="source_visual_sync_mesh_authored_world",
        ).copy()

    def sync(self) -> dict[str, Any]:
        source_world = _rigid_affine_matrix(
            self._read_source_world(), name="source_visual_sync_source_world"
        )
        parent_delta = _rigid_affine_matrix(
            source_world @ np.linalg.inv(self._source_authored_world),
            name="source_visual_sync_parent_delta",
        )
        self._write_visual_mesh_parent_delta(parent_delta)
        expected_mesh_world = _tracked_child_world_matrix(
            child_authored_world=self._visual_mesh_authored_world,
            parent_authored_world=self._source_authored_world,
            parent_current_world=source_world,
        )
        actual_mesh_world = _affine_matrix(
            self._read_visual_mesh_world(),
            name="source_visual_sync_mesh_world",
        )
        translation_error_m = float(
            np.linalg.norm(
                actual_mesh_world[3, :3] - expected_mesh_world[3, :3]
            )
        )
        linear_error_max_abs = float(
            np.max(
                np.abs(
                    actual_mesh_world[:3, :3] - expected_mesh_world[:3, :3]
                )
            )
        )
        valid = (
            translation_error_m <= self._translation_tolerance_m
            and linear_error_max_abs <= self._linear_tolerance
        )
        return {
            "policy": "visual_mesh_parent_delta_v1",
            "valid": valid,
            "translation_error_m": translation_error_m,
            "linear_error_max_abs": linear_error_max_abs,
            "source_physics_world_matrix_sha256": _matrix_sha256(source_world),
            "visual_mesh_parent_delta_sha256": _matrix_sha256(parent_delta),
            "expected_visual_mesh_world_matrix_sha256": _matrix_sha256(
                expected_mesh_world
            ),
            "actual_visual_mesh_world_matrix_sha256": _matrix_sha256(
                actual_mesh_world
            ),
        }


def _source_visual_mesh_parent_delta_writer(
    stage: Any,
    *,
    visual_mesh_path: str,
) -> Callable[[np.ndarray], None]:
    """Author a display-only parent delta before a mesh's existing local ops."""
    from pxr import Gf, UsdGeom

    mesh = stage.GetPrimAtPath(visual_mesh_path)
    if not mesh or not mesh.IsValid() or not mesh.IsA(UsdGeom.Mesh):
        raise RuntimeError(f"source_visual_mesh_invalid:{visual_mesh_path}")
    for attribute_name in ("physics:collisionEnabled", "physics:rigidBodyEnabled"):
        attribute = mesh.GetAttribute(attribute_name)
        if attribute and attribute.Get() is True:
            raise RuntimeError(
                f"source_visual_mesh_must_not_drive_physics:{visual_mesh_path}:"
                f"{attribute_name}"
            )

    xformable = UsdGeom.Xformable(mesh)
    existing_ops = list(xformable.GetOrderedXformOps())
    sync_op_name = "xformOp:transform:labutopiaVisualSync"
    sync_op = next(
        (op for op in existing_ops if str(op.GetOpName()) == sync_op_name), None
    )
    if sync_op is None:
        sync_op = xformable.AddTransformOp(
            UsdGeom.XformOp.PrecisionDouble,
            "labutopiaVisualSync",
        )
    elif sync_op.GetOpType() != UsdGeom.XformOp.TypeTransform:
        raise RuntimeError(f"source_visual_sync_op_type_invalid:{visual_mesh_path}")
    ordered_ops = [
        sync_op
    ] + [op for op in existing_ops if str(op.GetOpName()) != sync_op_name]
    xformable.SetXformOpOrder(ordered_ops)

    def write(parent_delta: np.ndarray) -> None:
        values = _rigid_affine_matrix(
            parent_delta, name="source_visual_mesh_parent_delta"
        )
        sync_op.Set(Gf.Matrix4d(*values.reshape(-1).tolist()))

    return write


def _frame_at_world_matrix(template: Any, world_matrix: Any) -> Any:
    world = _affine_matrix(world_matrix, name="frame_world")

    def unit(values: np.ndarray) -> tuple[float, float, float]:
        norm = float(np.linalg.norm(values))
        if not math.isfinite(norm) or norm <= 0.0:
            raise RuntimeError("wrapper_axis_invalid")
        return tuple((values / norm).tolist())

    return replace(
        template,
        origin_world=tuple(world[3, :3].tolist()),
        x_axis_world=unit(world[0, :3]),
        y_axis_world=unit(world[1, :3]),
        z_axis_world=unit(world[2, :3]),
    )


class PhysicsSourceStateAdapter:
    """Replace stale USD task pose fields with one current PhysX pose snapshot."""

    def __init__(
        self,
        *,
        read_source_world_pose: Callable[[], tuple[Any, Any]],
        initial_geometry_center_world: Any,
    ) -> None:
        if not callable(read_source_world_pose):
            raise TypeError("source_world_pose_reader_required")
        center = np.asarray(initial_geometry_center_world, dtype=np.float64)
        if center.shape != (3,) or not np.isfinite(center).all():
            raise ValueError("initial_geometry_center_world_invalid")
        self._read_pose = read_source_world_pose
        initial_position, initial_orientation = self._read_pose()
        initial_world = _world_pose_to_matrix(initial_position, initial_orientation)
        center_homogeneous = np.concatenate([center, [1.0]])
        self._center_local = np.ascontiguousarray(
            center_homogeneous @ np.linalg.inv(initial_world), dtype=np.float64
        )

    def __call__(self, state: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(state, Mapping):
            raise TypeError("physics_source_state_mapping_required")
        position, orientation_wxyz = self._read_pose()
        current_world = _world_pose_to_matrix(position, orientation_wxyz)
        orientation = np.asarray(orientation_wxyz, dtype=np.float64)
        orientation /= np.linalg.norm(orientation)
        center_world = self._center_local @ current_world
        adapted = dict(state)
        adapted["object_position"] = np.ascontiguousarray(
            center_world[:3], dtype=np.float64
        )
        adapted["object_quaternion"] = np.ascontiguousarray(
            orientation[[1, 2, 3, 0]], dtype=np.float64
        )
        return adapted


def set_single_rigid_kinematic_target(
    single_rigid_prim: Any,
    *,
    position: Any,
    orientation_wxyz: Any,
) -> None:
    """Set an actual PhysX kinematic target instead of teleporting the body."""
    position_values = np.asarray(position, dtype=np.float32)
    orientation_values = np.asarray(orientation_wxyz, dtype=np.float32)
    if position_values.shape != (3,) or not np.isfinite(position_values).all():
        raise ValueError("kinematic_target_position_invalid")
    if (
        orientation_values.shape != (4,)
        or not np.isfinite(orientation_values).all()
        or float(np.linalg.norm(orientation_values)) <= 0.0
    ):
        raise ValueError("kinematic_target_orientation_invalid")
    orientation_values = orientation_values / np.linalg.norm(orientation_values)
    prim_view = getattr(single_rigid_prim, "_prim_view", None)
    physics_view = getattr(prim_view, "_physics_view", None)
    if physics_view is None or not hasattr(physics_view, "set_kinematic_targets"):
        raise RuntimeError("physx_kinematic_target_view_unavailable")
    target_xyzw = np.concatenate(
        [position_values, orientation_values[1:], orientation_values[:1]]
    ).reshape(1, 7)
    physics_view.set_kinematic_targets(
        np.ascontiguousarray(target_xyzw, dtype=np.float32),
        np.asarray([0], dtype=np.int32),
    )


class AuthoredWrapperFrameReader:
    def __init__(
        self,
        stage: Any,
        *,
        parent_path: str,
        visual_mesh_path: str,
        parent_world_matrix: Callable[[], Any] | None = None,
    ):
        from tools.labutopia_fluid.real_beaker import (
            derive_authored_fluid_wrapper_frame,
        )

        self.stage = stage
        self.parent_path = parent_path
        self.wrapper_path = f"{parent_path.rstrip('/')}/FluidSafeWrapperCanonical"
        self.template = derive_authored_fluid_wrapper_frame(
            stage,
            parent_path=parent_path,
            visual_mesh_path=visual_mesh_path,
        )
        self._authored_parent_world = _prim_world_matrix(stage, parent_path)
        self._authored_wrapper_world = _prim_world_matrix(stage, self.wrapper_path)
        self._read_parent_world = parent_world_matrix or (
            lambda: _prim_world_matrix(stage, parent_path)
        )

    def __call__(self) -> Any:
        world = _tracked_child_world_matrix(
            child_authored_world=self._authored_wrapper_world,
            parent_authored_world=self._authored_parent_world,
            parent_current_world=self._read_parent_world(),
        )
        return _frame_at_world_matrix(self.template, world)


def _table_top_z(stage: Any, table_path: str) -> float:
    from pxr import Usd, UsdGeom

    table = stage.GetPrimAtPath(table_path)
    if not table or not table.IsValid():
        raise RuntimeError(f"fluid_table_prim_missing:{table_path}")
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
        useExtentsHint=True,
    )
    return float(cache.ComputeWorldBound(table).ComputeAlignedBox().GetMax()[2])


class FluidTransferScorer:
    def __init__(
        self,
        *,
        source_frame: Callable[[], Any],
        target_frame: Callable[[], Any],
        table_z: float,
        minimum_target_particles: int,
        minimum_task_target_fraction: float,
        minimum_expert_target_fraction: float,
    ) -> None:
        self.source_frame = source_frame
        self.target_frame = target_frame
        self.table_z = float(table_z)
        self.minimum_target_particles = int(minimum_target_particles)
        self.minimum_task_target_fraction = float(minimum_task_target_fraction)
        self.minimum_expert_target_fraction = float(
            minimum_expert_target_fraction
        )

    def __call__(self, positions: np.ndarray) -> dict[str, Any]:
        source = self.source_frame()
        target = self.target_frame()
        result = classify_transfer_positions(
            positions,
            source_frame=source,
            target_frame=target,
            table_z=self.table_z,
            minimum_target_particles=self.minimum_target_particles,
            minimum_task_target_fraction=self.minimum_task_target_fraction,
            minimum_expert_target_fraction=self.minimum_expert_target_fraction,
        )
        result.update(
            {
                "source_frame_origin_world": [
                    float(value) for value in source.origin_world
                ],
                "source_frame_z_axis_world": [
                    float(value) for value in source.z_axis_world
                ],
                "target_frame_origin_world": [
                    float(value) for value in target.origin_world
                ],
            }
        )
        return result


def build_isaac_fluid_evaluation_loop(
    *,
    cfg: Any,
    world: Any,
    task: Any,
    stage: Any,
) -> Any:
    """Build the production 5.1 adapter after the task's first fixed reset."""
    from isaacsim.core.prims import SingleRigidPrim

    from tools.labutopia_fluid.interndata_surface_reconstruction import (
        reconstruct_surface_live,
    )
    from utils.fluid_evaluation_loop import FluidEvaluationLoop
    from utils.online_fluid_surface import read_strict_simulation_points

    fluid = _config_value(cfg, "online_fluid")
    configure_fluid_world_timing(
        world,
        physics_dt=float(_config_value(fluid, "physics_dt")),
        rendering_dt=float(_config_value(fluid, "rendering_dt")),
    )
    validate_fluid_stage_contract(stage, fluid)
    attachment_policy = str(
        _config_value(fluid, "attachment_matrix_policy")
    )
    if attachment_policy != (
        "captured_translation_then_recaptured_full_at_scripted_pour"
    ):
        raise ValueError(f"attachment_matrix_policy_unsupported:{attachment_policy}")
    source_path = str(_config_value(fluid, "source_actor_path"))
    gripper_path = str(_config_value(fluid, "gripper_frame_path"))
    source_visual_mesh_path = str(
        _config_value(fluid, "source_visual_mesh_path")
    )
    source_authored_world = _prim_world_matrix(stage, source_path)
    source_body = construct_single_rigid_prim(
        SingleRigidPrim,
        prim_path=source_path,
        name="online_fluid_source_vessel",
    )
    source_body.initialize()

    def read_source_pose() -> tuple[Any, Any]:
        return source_body.get_world_pose()

    def read_source_world() -> np.ndarray:
        position, orientation = read_source_pose()
        return _world_pose_to_matrix(position, orientation)

    def write_source(matrix: np.ndarray) -> None:
        position, orientation = _matrix_to_world_pose(matrix)
        set_single_rigid_kinematic_target(
            source_body,
            position=position,
            orientation_wxyz=orientation,
        )

    source_visual_sync = SourceVisualMeshSynchronizer(
        source_authored_world_matrix=source_authored_world,
        read_source_world_matrix=read_source_world,
        read_visual_mesh_world_matrix=lambda: _prim_world_matrix(
            stage, source_visual_mesh_path
        ),
        write_visual_mesh_parent_delta=_source_visual_mesh_parent_delta_writer(
            stage,
            visual_mesh_path=source_visual_mesh_path,
        ),
    )

    attachment = GripperAttachedKinematicVessel(
        read_source_world_matrix=read_source_world,
        read_gripper_world_matrix=lambda: _prim_world_matrix(stage, gripper_path),
        write_source_world_matrix=write_source,
    )
    source_frame = AuthoredWrapperFrameReader(
        stage,
        parent_path=source_path,
        visual_mesh_path=source_visual_mesh_path,
        parent_world_matrix=read_source_world,
    )
    target_frame = AuthoredWrapperFrameReader(
        stage,
        parent_path=str(_config_value(fluid, "target_actor_path")),
        visual_mesh_path=str(_config_value(fluid, "target_visual_mesh_path")),
    )
    scorer = FluidTransferScorer(
        source_frame=source_frame,
        target_frame=target_frame,
        table_z=_table_top_z(stage, str(_config_value(fluid, "table_path"))),
        minimum_target_particles=int(
            _config_value(fluid, "minimum_target_particles")
        ),
        minimum_task_target_fraction=float(
            _config_value(fluid, "minimum_task_target_fraction")
        ),
        minimum_expert_target_fraction=float(
            _config_value(fluid, "minimum_expert_target_fraction")
        ),
    )
    source_state = PhysicsSourceStateAdapter(
        read_source_world_pose=read_source_pose,
        initial_geometry_center_world=task.object_utils.get_geometry_center(
            object_path=source_path
        ),
    )
    surface = IsaacFluidSurfaceAuthor(
        stage=stage,
        surface_path=str(_config_value(fluid, "surface_path")),
        material_path=str(_config_value(fluid, "surface_material_path")),
        hidden_liquid_paths=tuple(_config_value(fluid, "hidden_liquid_paths")),
        particle_system_path=str(_config_value(fluid, "particle_system_path")),
    )
    particle_path = str(_config_value(fluid, "particle_path"))
    expected_count = int(_config_value(fluid, "expected_particle_count"))
    camera_contract_id = str(_config_value(fluid, "camera_contract"))
    camera_contract = resolve_camera_contract_record(
        stage,
        contract_id=camera_contract_id,
        camera_configs=tuple(_config_value(cfg, "cameras")),
        compatibility=str(
            _optional_config_value(
                fluid,
                "camera_contract_compatibility",
                f"requires_{camera_contract_id}",
            )
        ),
        rendering_dt=float(_config_value(fluid, "rendering_dt")),
    )
    expected_camera_contract_sha256 = _optional_config_value(
        fluid, "camera_contract_sha256"
    )
    if expected_camera_contract_sha256 is not None:
        require_camera_contract_sha256(
            camera_contract,
            expected_sha256=str(expected_camera_contract_sha256),
        )
    initial_render_warmup_updates = (
        fluid.get("initial_render_warmup_updates", 0)
        if isinstance(fluid, Mapping)
        else getattr(fluid, "initial_render_warmup_updates", 0)
    )
    return FluidEvaluationLoop(
        world=world,
        task=task,
        expected_particle_count=expected_count,
        physics_substeps_per_observation=int(
            _config_value(fluid, "physics_substeps_per_observation")
        ),
        physics_substep_dt=float(_config_value(fluid, "physics_dt")),
        read_particles=lambda: read_strict_simulation_points(
            stage,
            particle_path,
            expected_particle_count=expected_count,
        ),
        score_particles=scorer,
        reconstruct=reconstruct_surface_live,
        author_surface=surface,
        invalidate_surface=surface.invalidate,
        attachment=attachment,
        adapt_state=source_state,
        sync_source_visual_state=source_visual_sync.sync,
        expected_camera_keys=tuple(_config_value(fluid, "model_camera_keys")),
        expected_camera_shape=tuple(_config_value(fluid, "model_camera_shape")),
        camera_contract=camera_contract,
        initial_render_warmup_updates=initial_render_warmup_updates,
    )
