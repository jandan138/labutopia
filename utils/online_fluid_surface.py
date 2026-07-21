"""Current-state liquid surface coordination for model-facing observations."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import numpy as np


def _canonical_sha256(array: np.ndarray) -> str:
    values = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(values.dtype.str.encode("ascii"))
    digest.update(b"\0")
    digest.update(json.dumps(list(values.shape), separators=(",", ":")).encode("ascii"))
    digest.update(b"\0")
    digest.update(values.tobytes(order="C"))
    return digest.hexdigest()


def canonical_position_sha256(positions: Any) -> str:
    values = np.ascontiguousarray(np.asarray(positions, dtype="<f8"))
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("simulation_points_shape_invalid")
    if not np.isfinite(values).all():
        raise ValueError("simulation_points_nonfinite")
    return _canonical_sha256(values)


def validate_simulation_points(
    positions: Any,
    *,
    expected_particle_count: int,
) -> np.ndarray:
    if type(expected_particle_count) is not int or expected_particle_count <= 0:
        raise ValueError("expected_particle_count_invalid")
    values = np.asarray(positions, dtype=np.float64)
    if values.ndim != 2 or values.shape[1:] != (3,):
        raise ValueError("simulation_points_shape_invalid")
    if len(values) != expected_particle_count:
        raise ValueError(
            "particle_count_mismatch:"
            f"expected={expected_particle_count}:actual={len(values)}"
        )
    if not np.isfinite(values).all():
        raise ValueError("simulation_points_nonfinite")
    result = np.ascontiguousarray(values, dtype=np.float64)
    result.setflags(write=False)
    return result


def read_strict_simulation_points(
    stage: Any,
    particle_path: str,
    *,
    expected_particle_count: int,
) -> np.ndarray:
    if not isinstance(particle_path, str) or not particle_path.startswith("/"):
        raise ValueError("particle_path_invalid")
    prim = stage.GetPrimAtPath(particle_path)
    if not prim or not prim.IsValid():
        raise ValueError(f"particle_prim_missing:{particle_path}")
    attribute = prim.GetAttribute("physxParticle:simulationPoints")
    values = attribute.Get() if attribute else None
    if values is None:
        raise ValueError(f"simulation_points_missing:{particle_path}")
    return validate_simulation_points(
        values,
        expected_particle_count=expected_particle_count,
    )


@dataclass(frozen=True)
class ObservationTransition:
    episode_id: str
    observation_index: int
    caused_by_action_index: int | None
    logical_step_before: int
    logical_step_after: int
    integration_step_before: int
    integration_step_after: int
    simulation_time_before: float
    simulation_time_after: float
    action_sha256: str | None = None


@dataclass(frozen=True)
class SurfaceFrameToken:
    episode_id: str
    observation_index: int
    caused_by_action_index: int | None
    logical_step_before: int
    logical_step_after: int
    integration_step_before: int
    integration_step_after: int
    simulation_time_before: float
    simulation_time_after: float
    action_sha256: str | None
    particle_count: int
    position_sha256: str
    surface_geometry_sha256: str
    identity: str
    positions: np.ndarray


def _frame_identity(
    transition: ObservationTransition,
    *,
    particle_count: int,
    position_sha256: str,
    surface_geometry_sha256: str,
) -> str:
    payload = {
        "episode_id": transition.episode_id,
        "observation_index": transition.observation_index,
        "caused_by_action_index": transition.caused_by_action_index,
        "logical_step_before": transition.logical_step_before,
        "logical_step_after": transition.logical_step_after,
        "integration_step_before": transition.integration_step_before,
        "integration_step_after": transition.integration_step_after,
        "simulation_time_before": transition.simulation_time_before,
        "simulation_time_after": transition.simulation_time_after,
        "action_sha256": transition.action_sha256,
        "particle_count": particle_count,
        "position_sha256": position_sha256,
        "surface_geometry_sha256": surface_geometry_sha256,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class OnlineFluidSurfaceRuntime:
    def __init__(
        self,
        *,
        expected_particle_count: int,
        physics_substeps_per_observation: int,
        physics_substep_dt: float,
        reconstruct: Callable[[np.ndarray], Mapping[str, Any]],
        author_surface: Callable[[Mapping[str, Any], SurfaceFrameToken], Mapping[str, Any]],
        invalidate_surface: Callable[[str], None],
        render_surface: Callable[[SurfaceFrameToken], Mapping[str, Any]],
        capture_cameras: Callable[
            [SurfaceFrameToken, Mapping[str, Any]], Mapping[str, Any]
        ],
    ) -> None:
        if type(expected_particle_count) is not int or expected_particle_count <= 0:
            raise ValueError("expected_particle_count_invalid")
        if (
            type(physics_substeps_per_observation) is not int
            or physics_substeps_per_observation <= 0
        ):
            raise ValueError("physics_substeps_per_observation_invalid")
        if not math.isfinite(physics_substep_dt) or physics_substep_dt <= 0.0:
            raise ValueError("physics_substep_dt_invalid")
        self.expected_particle_count = expected_particle_count
        self.physics_substeps_per_observation = physics_substeps_per_observation
        self.physics_substep_dt = float(physics_substep_dt)
        self.reconstruct = reconstruct
        self.author_surface = author_surface
        self.invalidate_surface = invalidate_surface
        self.render_surface = render_surface
        self.capture_cameras = capture_cameras
        self._episode_id: str | None = None
        self._next_observation_index = 0
        self._previous_transition: ObservationTransition | None = None
        self._failed = False

    def reset_episode(self, episode_id: str) -> None:
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError("episode_id_invalid")
        self.invalidate_surface("episode_reset")
        self._episode_id = episode_id
        self._next_observation_index = 0
        self._previous_transition = None
        self._failed = False

    def _validate_transition(self, transition: ObservationTransition) -> None:
        if not isinstance(transition, ObservationTransition):
            raise TypeError("observation_transition_required")
        if self._episode_id is None:
            raise RuntimeError("episode_not_reset")
        if transition.episode_id != self._episode_id:
            raise ValueError("transition_episode_mismatch")
        if transition.observation_index != self._next_observation_index:
            raise ValueError(
                "observation_index_out_of_sequence:"
                f"expected={self._next_observation_index}:"
                f"actual={transition.observation_index}"
            )
        integer_fields = (
            transition.observation_index,
            transition.logical_step_before,
            transition.logical_step_after,
            transition.integration_step_before,
            transition.integration_step_after,
        )
        if any(type(value) is not int or value < 0 for value in integer_fields):
            raise ValueError("transition_step_counter_invalid")
        times = (transition.simulation_time_before, transition.simulation_time_after)
        if any(not math.isfinite(value) or value < 0.0 for value in times):
            raise ValueError("transition_simulation_time_invalid")

        if transition.observation_index == 0:
            if transition.caused_by_action_index is not None:
                raise ValueError("reset_observation_must_not_have_action")
            if transition.action_sha256 is not None:
                raise ValueError("reset_observation_must_not_have_action_hash")
            if (
                transition.logical_step_before != transition.logical_step_after
                or transition.integration_step_before
                != transition.integration_step_after
                or not math.isclose(
                    transition.simulation_time_before,
                    transition.simulation_time_after,
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ):
                raise ValueError("reset_observation_advanced_physics")
            return

        if transition.caused_by_action_index != transition.observation_index - 1:
            raise ValueError("caused_by_action_index_invalid")
        action_sha256 = transition.action_sha256
        if (
            not isinstance(action_sha256, str)
            or len(action_sha256) != 64
            or any(character not in "0123456789abcdef" for character in action_sha256)
        ):
            raise ValueError("action_sha256_invalid")
        previous = self._previous_transition
        if previous is None:
            raise ValueError("transition_counter_discontinuity")
        if (
            transition.logical_step_before != previous.logical_step_after
            or transition.integration_step_before != previous.integration_step_after
            or not math.isclose(
                transition.simulation_time_before,
                previous.simulation_time_after,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
        ):
            raise ValueError("transition_counter_discontinuity")
        if transition.logical_step_after - transition.logical_step_before != 1:
            raise ValueError("logical_step_delta_invalid")
        if (
            transition.integration_step_after - transition.integration_step_before
            != self.physics_substeps_per_observation
        ):
            raise ValueError("integration_step_delta_invalid")
        expected_delta = (
            self.physics_substeps_per_observation * self.physics_substep_dt
        )
        actual_delta = (
            transition.simulation_time_after - transition.simulation_time_before
        )
        if not math.isclose(
            actual_delta,
            expected_delta,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            raise ValueError("simulation_time_delta_invalid")

    @staticmethod
    def _validate_mesh(mesh: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
        if not isinstance(mesh, Mapping):
            raise ValueError("surface_mesh_mapping_required")
        vertices = np.ascontiguousarray(mesh.get("vertices"), dtype=np.float32)
        faces = np.ascontiguousarray(mesh.get("faces"), dtype=np.int32)
        normals = np.ascontiguousarray(mesh.get("normals"), dtype=np.float32)
        if vertices.ndim != 2 or vertices.shape[1:] != (3,) or len(vertices) == 0:
            raise ValueError("surface_vertices_shape_invalid")
        if faces.ndim != 2 or faces.shape[1:] != (3,) or len(faces) == 0:
            raise ValueError("surface_faces_shape_invalid")
        if normals.shape != vertices.shape:
            raise ValueError("surface_normals_shape_invalid")
        if not np.isfinite(vertices).all() or not np.isfinite(normals).all():
            raise ValueError("surface_arrays_nonfinite")
        if np.any(faces < 0) or np.any(faces >= len(vertices)):
            raise ValueError("surface_faces_out_of_range")
        geometry_hash = mesh.get("geometry_sha256")
        if (
            not isinstance(geometry_hash, str)
            or len(geometry_hash) != 64
            or any(character not in "0123456789abcdef" for character in geometry_hash)
        ):
            raise ValueError("surface_geometry_sha256_invalid")
        return vertices, faces, normals, geometry_hash

    @staticmethod
    def _validate_authoring(
        authoring: Mapping[str, Any],
        token: SurfaceFrameToken,
        *,
        vertex_count: int,
        face_count: int,
    ) -> dict[str, Any]:
        if not isinstance(authoring, Mapping):
            raise ValueError("surface_authoring_record_required")
        if authoring.get("surface_token") != token.identity:
            raise RuntimeError("surface_authoring_token_mismatch")
        if int(authoring.get("vertex_count", -1)) != vertex_count:
            raise RuntimeError("surface_authoring_vertex_count_mismatch")
        if int(authoring.get("face_count", -1)) != face_count:
            raise RuntimeError("surface_authoring_face_count_mismatch")
        return dict(authoring)

    @staticmethod
    def _validate_render(
        render: Mapping[str, Any], token: SurfaceFrameToken
    ) -> dict[str, Any]:
        if not isinstance(render, Mapping):
            raise ValueError("render_record_mapping_required")
        required = (
            "render_token",
            "surface_token",
            "logical_steps_before",
            "logical_steps_after",
            "integration_steps_before",
            "integration_steps_after",
            "timeline_time_before",
            "timeline_time_after",
        )
        if any(key not in render for key in required):
            raise ValueError("render_record_incomplete")
        timeline_before = float(render["timeline_time_before"])
        timeline_after = float(render["timeline_time_after"])
        unchanged = (
            render["logical_steps_before"] == token.logical_step_after
            and render["logical_steps_after"] == token.logical_step_after
            and render["integration_steps_before"] == token.integration_step_after
            and render["integration_steps_after"] == token.integration_step_after
            and math.isfinite(timeline_before)
            and math.isfinite(timeline_after)
            and math.isclose(
                timeline_before,
                timeline_after,
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
        )
        if not unchanged:
            raise RuntimeError("render_advanced_physics_or_timeline")
        if render["surface_token"] != token.identity:
            raise RuntimeError("render_surface_token_mismatch")
        render_token = render["render_token"]
        if not isinstance(render_token, str) or not render_token:
            raise ValueError("render_token_invalid")
        return {**dict(render), "physics_and_timeline_unchanged": True}

    @staticmethod
    def _camera_records(cameras: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        if not isinstance(cameras, Mapping) or not cameras:
            raise ValueError("camera_arrays_missing")
        records: dict[str, dict[str, Any]] = {}
        for name, data in cameras.items():
            if not isinstance(name, str) or not name:
                raise ValueError("camera_name_invalid")
            array = np.asarray(data)
            if array.ndim < 2 or array.size == 0:
                raise ValueError(f"camera_array_shape_invalid:{name}")
            if np.issubdtype(array.dtype, np.number) and not np.isfinite(array).all():
                raise ValueError(f"camera_array_nonfinite:{name}")
            canonical = np.ascontiguousarray(array)
            records[name] = {
                "shape": [int(value) for value in canonical.shape],
                "dtype": str(canonical.dtype),
                "sha256": _canonical_sha256(canonical),
            }
        return records

    def process_observation(
        self,
        transition: ObservationTransition,
        positions: Any,
    ) -> dict[str, Any]:
        if self._failed:
            raise RuntimeError("episode_runtime_failed_requires_reset")
        total_start = time.perf_counter()
        try:
            self._validate_transition(transition)
            current_positions = validate_simulation_points(
                positions,
                expected_particle_count=self.expected_particle_count,
            )
            position_hash = canonical_position_sha256(current_positions)
            position_summary = {
                "min": current_positions.min(axis=0).tolist(),
                "max": current_positions.max(axis=0).tolist(),
                "centroid": current_positions.mean(axis=0).tolist(),
            }

            stage_start = time.perf_counter()
            mesh = self.reconstruct(current_positions)
            reconstruction_seconds = time.perf_counter() - stage_start
            vertices, faces, _normals, geometry_hash = self._validate_mesh(mesh)
            diagnostics = mesh.get("diagnostics")
            normal_provenance = (
                diagnostics.get("normal_provenance")
                if isinstance(diagnostics, Mapping)
                else None
            )
            if normal_provenance is not None and not isinstance(
                normal_provenance, Mapping
            ):
                raise ValueError("surface_normal_provenance_invalid")
            identity = _frame_identity(
                transition,
                particle_count=len(current_positions),
                position_sha256=position_hash,
                surface_geometry_sha256=geometry_hash,
            )
            token = SurfaceFrameToken(
                **transition.__dict__,
                particle_count=len(current_positions),
                position_sha256=position_hash,
                surface_geometry_sha256=geometry_hash,
                identity=identity,
                positions=current_positions,
            )

            stage_start = time.perf_counter()
            authoring = self._validate_authoring(
                self.author_surface(mesh, token),
                token,
                vertex_count=len(vertices),
                face_count=len(faces),
            )
            authoring_seconds = time.perf_counter() - stage_start

            stage_start = time.perf_counter()
            render = self._validate_render(self.render_surface(token), token)
            render_seconds = time.perf_counter() - stage_start

            stage_start = time.perf_counter()
            cameras = self._camera_records(self.capture_cameras(token, render))
            camera_seconds = time.perf_counter() - stage_start

            total_seconds = time.perf_counter() - total_start
            self._next_observation_index += 1
            self._previous_transition = transition
            return {
                "episode_id": transition.episode_id,
                "observation_index": transition.observation_index,
                "caused_by_action_index": transition.caused_by_action_index,
                "logical_step_before": transition.logical_step_before,
                "logical_step_after": transition.logical_step_after,
                "integration_step_before": transition.integration_step_before,
                "integration_step_after": transition.integration_step_after,
                "simulation_time_before": transition.simulation_time_before,
                "simulation_time_after": transition.simulation_time_after,
                "action_sha256": transition.action_sha256,
                "particle_count": len(current_positions),
                "position_sha256": position_hash,
                "position_summary_world_m": position_summary,
                "frame_identity": identity,
                "surface": {
                    "geometry_sha256": geometry_hash,
                    "vertex_count": int(len(vertices)),
                    "face_count": int(len(faces)),
                    "normal_provenance": (
                        None
                        if normal_provenance is None
                        else dict(normal_provenance)
                    ),
                    "authoring": authoring,
                },
                "render": render,
                "cameras": cameras,
                "latency_seconds": {
                    "reconstruction": reconstruction_seconds,
                    "usd_authoring": authoring_seconds,
                    "render": render_seconds,
                    "camera_read": camera_seconds,
                    "total": total_seconds,
                },
            }
        except Exception as exc:
            self._failed = True
            try:
                self.invalidate_surface(
                    f"observation_failed:{type(exc).__name__}"
                )
            except Exception:
                pass
            raise
