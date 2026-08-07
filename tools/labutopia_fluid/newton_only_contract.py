#!/usr/bin/env python3
"""Pure-data contract for the Newton-only LabUtopia fluid benchmark.

This module intentionally imports neither Isaac Sim nor Newton/Warp.  Parent
orchestrators, sealed exporters, runtime children, tests, and report builders
can therefore agree on one benchmark definition without crossing runtime
boundaries.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from tools.labutopia_fluid.fluid_benchmark_contract import (
    EXPECTED_OBSERVATION_COUNT,
    LOGICAL_DT_S,
)


SCENE_PACK_SCHEMA = "labutopia.newton_fluid_scene_pack.v1"
RUN_CONFIG_SCHEMA = "labutopia.newton_fluid_run_config.v1"
RUN_RESULT_SCHEMA = "labutopia.newton_fluid_run_result.v1"
VISUAL_REVIEW_SCHEMA = "labutopia.newton_fluid_visual_review.v1"

RESOLUTIONS = (900, 1800, 3600, 7200)
FAIR_PARTICLE_COUNT = 3600
SEARCH_EXPLORATION_PARTICLE_COUNT = 900
SEARCH_EXPLORATION_COUNT = 24
SEARCH_REFINEMENT_COUNT = 8
SEARCH_CONFIGURATION_COUNT = SEARCH_EXPLORATION_COUNT + SEARCH_REFINEMENT_COUNT
MEASURED_OBSERVATIONS = EXPECTED_OBSERVATION_COUNT
MEASURED_DURATION_S = MEASURED_OBSERVATIONS * LOGICAL_DT_S
VISUAL_REVIEW_FRAME_INDICES = (0, 136, 272, 408, 544, 680, 816, 952)
VISUAL_REVIEW_CAMERA_IDS = ("front", "wrist")
ROBOT_LANES = ("kinematic_replay", "newton_dynamics_fixed_grasp")
RENDER_LANES = (
    "physics_only",
    "viewergl_particles",
    "viewergl_surface_cpu",
    "viewergl_surface_gpu",
    "viewerrtx_particles",
    "viewerrtx_surface_cpu",
    "viewerrtx_surface_gpu",
)


@dataclass(frozen=True)
class SolverSpec:
    solver_id: str
    display_name: str
    family: str
    implementation: str
    origin: str
    iterative: bool
    native_newton: bool
    liquid_model: str


SOLVER_CATALOG: tuple[SolverSpec, ...] = (
    SolverSpec(
        "newton_implicit_mpm",
        "Newton Implicit MPM",
        "mpm",
        "newton.solvers.SolverImplicitMPM",
        "Newton 1.4.0",
        True,
        True,
        "continuum",
    ),
    SolverSpec(
        "newton_xpbd_cohesion",
        "Newton XPBD cohesion",
        "position_based",
        "newton.solvers.SolverXPBD",
        "Newton 1.4.0",
        True,
        True,
        "particle_cohesion",
    ),
    SolverSpec(
        "newton_vbd_self_contact",
        "Newton VBD particle self-contact",
        "variational",
        "newton.solvers.SolverVBD",
        "Newton 1.4.0",
        True,
        True,
        "particle_self_contact",
    ),
    SolverSpec(
        "newton_semiimplicit_particles",
        "Newton SemiImplicit particles",
        "force_based",
        "newton.solvers.SolverSemiImplicit",
        "Newton 1.4.0",
        False,
        True,
        "particle_contact",
    ),
    SolverSpec(
        "labutopia_wcsph",
        "LabUtopia minimal WCSPH",
        "sph",
        "LabUtopia Warp kernels",
        "LabUtopia",
        False,
        False,
        "weakly_compressible",
    ),
    SolverSpec(
        "warp_example_sph",
        "Warp official SPH adaptation",
        "sph",
        "warp.examples.core.example_sph adaptation",
        "Warp 1.15.0 Apache-2.0 example",
        False,
        False,
        "weakly_compressible",
    ),
    SolverSpec(
        "labutopia_dfsph",
        "LabUtopia minimal DFSPH",
        "sph",
        "LabUtopia Warp kernels",
        "LabUtopia",
        True,
        False,
        "divergence_free",
    ),
    SolverSpec(
        "splishsplash_dfsph_port",
        "SPlisHSPlasH DFSPH Warp port",
        "sph",
        "SPlisHSPlasH equations ported to Warp",
        "SPlisHSPlasH MIT",
        True,
        False,
        "divergence_free",
    ),
    SolverSpec(
        "splishsplash_pbf_port",
        "SPlisHSPlasH PBF Warp port",
        "position_based",
        "SPlisHSPlasH equations ported to Warp",
        "SPlisHSPlasH MIT",
        True,
        False,
        "density_constraint",
    ),
    SolverSpec(
        "warp_example_apic",
        "Warp official APIC adaptation",
        "pic_grid",
        "warp.examples.fem.example_apic_fluid adaptation",
        "Warp 1.15.0 Apache-2.0 example",
        True,
        False,
        "incompressible_projection",
    ),
)

SOLVERS_BY_ID = {solver.solver_id: solver for solver in SOLVER_CATALOG}
if len(SOLVERS_BY_ID) != len(SOLVER_CATALOG):  # pragma: no cover - import invariant
    raise RuntimeError("duplicate_newton_fluid_solver_id")


def solver_spec(solver_id: str) -> SolverSpec:
    try:
        return SOLVERS_BY_ID[solver_id]
    except KeyError as error:
        raise ValueError(f"unknown_solver:{solver_id}") from error


def _positive_finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{label}_must_be_numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label}_must_be_positive_finite")
    return result


def adaptive_cfl_step(
    *,
    maximum_speed_m_s: float,
    support_radius_m: float,
    sound_speed_m_s: float = 0.0,
    cfl: float = 0.4,
    logical_dt_s: float = LOGICAL_DT_S,
    minimum_dt_s: float = 1.0 / 3840.0,
    maximum_dt_s: float = 1.0 / 120.0,
) -> dict[str, float | int]:
    """Choose an exact logical-frame subdivision from a continuous CFL bound."""
    speed = max(0.0, float(maximum_speed_m_s))
    sound_speed = max(0.0, float(sound_speed_m_s))
    radius = _positive_finite(support_radius_m, "support_radius_m")
    frame_dt = _positive_finite(logical_dt_s, "logical_dt_s")
    min_dt = _positive_finite(minimum_dt_s, "minimum_dt_s")
    max_dt = _positive_finite(maximum_dt_s, "maximum_dt_s")
    cfl_value = _positive_finite(cfl, "cfl")
    if min_dt > max_dt or max_dt > frame_dt:
        raise ValueError("cfl_dt_bounds_invalid")
    characteristic_speed = speed + sound_speed
    unconstrained = max_dt if characteristic_speed == 0.0 else cfl_value * radius / characteristic_speed
    bounded = min(max(unconstrained, min_dt), max_dt)
    substeps = max(1, int(math.ceil(frame_dt / bounded)))
    dt = frame_dt / substeps
    if dt + 1.0e-15 < min_dt:
        raise ValueError("cfl_requires_dt_below_minimum")
    return {
        "substeps": substeps,
        "dt_s": dt,
        "unconstrained_dt_s": unconstrained,
        "characteristic_speed_m_s": characteristic_speed,
        "cfl": cfl_value,
    }


def residual_stop(
    residuals: Sequence[float],
    *,
    tolerance: float,
    maximum_iterations: int,
    minimum_iterations: int = 1,
) -> dict[str, Any]:
    """Apply the benchmark's common residual early-stop rule."""
    tol = _positive_finite(tolerance, "tolerance")
    if maximum_iterations < 1 or minimum_iterations < 1 or minimum_iterations > maximum_iterations:
        raise ValueError("iteration_bounds_invalid")
    values = [float(value) for value in residuals]
    if not values or any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("residuals_invalid")
    observed = min(len(values), maximum_iterations)
    actual = observed
    converged = False
    for index, value in enumerate(values[:observed], start=1):
        if index >= minimum_iterations and value <= tol:
            actual = index
            converged = True
            break
    return {
        "actual_iterations": actual,
        "maximum_iterations": maximum_iterations,
        "minimum_iterations": minimum_iterations,
        "tolerance": tol,
        "final_residual": values[actual - 1],
        "converged": converged,
    }


def _quaternion_angle_xyzw(left: np.ndarray, right: np.ndarray) -> float:
    dot = abs(float(np.dot(left, right)))
    return 2.0 * math.acos(float(np.clip(dot, -1.0, 1.0)))


def trajectory_motion_limits(poses_xyzw: Any, *, dt_s: float = LOGICAL_DT_S) -> dict[str, float]:
    poses = np.asarray(poses_xyzw, dtype=np.float64)
    if poses.shape != (EXPECTED_OBSERVATION_COUNT, 7) or not np.isfinite(poses).all():
        raise ValueError("trajectory_shape_invalid")
    dt = _positive_finite(dt_s, "dt_s")
    norms = np.linalg.norm(poses[:, 3:], axis=1)
    if not np.allclose(norms, 1.0, atol=1.0e-4, rtol=0.0):
        raise ValueError("trajectory_quaternion_not_unit")
    linear_velocity = np.diff(poses[:, :3], axis=0) / dt
    linear_speed = np.linalg.norm(linear_velocity, axis=1)
    linear_acceleration = np.diff(linear_velocity, axis=0) / dt
    linear_accel_norm = np.linalg.norm(linear_acceleration, axis=1)
    angular_speed = np.asarray(
        [_quaternion_angle_xyzw(poses[i, 3:], poses[i + 1, 3:]) / dt for i in range(len(poses) - 1)]
    )
    angular_acceleration = np.diff(angular_speed) / dt
    return {
        "maximum_linear_speed_m_s": float(np.max(linear_speed, initial=0.0)),
        "maximum_linear_acceleration_m_s2": float(np.max(linear_accel_norm, initial=0.0)),
        "maximum_angular_speed_rad_s": float(np.max(angular_speed, initial=0.0)),
        "maximum_angular_acceleration_rad_s2": float(np.max(np.abs(angular_acceleration), initial=0.0)),
    }


def validate_reoptimized_trajectory(
    candidate_poses_xyzw: Any,
    reference_poses_xyzw: Any,
    *,
    endpoint_atol: float = 1.0e-6,
    limit_rtol: float = 1.0e-4,
) -> dict[str, Any]:
    """Enforce fixed endpoints and reference speed/acceleration envelopes."""
    candidate = np.asarray(candidate_poses_xyzw, dtype=np.float64)
    reference = np.asarray(reference_poses_xyzw, dtype=np.float64)
    candidate_limits = trajectory_motion_limits(candidate)
    reference_limits = trajectory_motion_limits(reference)
    if not np.allclose(candidate[0], reference[0], atol=endpoint_atol, rtol=0.0):
        raise ValueError("trajectory_start_changed")
    if not np.allclose(candidate[-1], reference[-1], atol=endpoint_atol, rtol=0.0):
        raise ValueError("trajectory_end_changed")
    violations: list[str] = []
    for name, reference_limit in reference_limits.items():
        allowed = reference_limit * (1.0 + limit_rtol) + 1.0e-9
        if candidate_limits[name] > allowed:
            violations.append(name)
    if violations:
        raise ValueError("trajectory_motion_limit_exceeded:" + ",".join(violations))
    return {
        "passed": True,
        "candidate": candidate_limits,
        "reference": reference_limits,
        "fixed_start": True,
        "fixed_end": True,
        "continuous": True,
    }


def build_search_schedule(solver_id: str) -> list[dict[str, Any]]:
    """Return the deterministic 24+8 search budget for one solver route."""
    spec = solver_spec(solver_id)
    schedule: list[dict[str, Any]] = []
    for index in range(SEARCH_EXPLORATION_COUNT):
        schedule.append(
            {
                "configuration_id": f"{solver_id}.explore.{index:02d}",
                "phase": "explore_900",
                "particle_count": SEARCH_EXPLORATION_PARTICLE_COUNT,
                "trajectory_candidate": index,
                "substep_tier": (1, 2, 4, 8)[index % 4],
                "iteration_tier": (1, 2, 4)[(index // 4) % 3] if spec.iterative else 1,
                "material_tier": (index // 12),
            }
        )
    for index, particle_count in enumerate((900, 1800, 3600, 7200) * 2):
        schedule.append(
            {
                "configuration_id": f"{solver_id}.refine.{index:02d}",
                "phase": "resolution_refine",
                "particle_count": particle_count,
                "refinement_rank": index // 4,
                "trajectory_candidate": "best_from_explore",
                "substep_tier": "best_from_explore",
                "iteration_tier": "best_from_explore",
                "material_tier": "best_from_explore",
            }
        )
    if len(schedule) != SEARCH_CONFIGURATION_COUNT:
        raise RuntimeError("search_schedule_size_internal_error")
    return schedule


def validate_visual_review(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema") != VISUAL_REVIEW_SCHEMA:
        raise ValueError("visual_review_schema_mismatch")
    if tuple(value.get("frame_indices", ())) != VISUAL_REVIEW_FRAME_INDICES:
        raise ValueError("visual_review_frames_mismatch")
    if tuple(value.get("camera_ids", ())) != VISUAL_REVIEW_CAMERA_IDS:
        raise ValueError("visual_review_cameras_mismatch")
    checks = value.get("checks")
    required = (
        "no_explosion_or_nonfinite",
        "no_obvious_cup_or_table_penetration",
        "no_sustained_scattering_outside_region",
        "meaningful_fluid_in_target_at_end",
    )
    if not isinstance(checks, Mapping) or any(type(checks.get(name)) is not bool for name in required):
        raise ValueError("visual_review_checks_invalid")
    passed = all(bool(checks[name]) for name in required)
    if value.get("passed") is not passed:
        raise ValueError("visual_review_pass_inconsistent")
    return {"passed": passed, "required_checks": required}


def validate_scene_pack_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema") != SCENE_PACK_SCHEMA:
        raise ValueError("scene_pack_schema_mismatch")
    if value.get("observation_count") != EXPECTED_OBSERVATION_COUNT:
        raise ValueError("scene_pack_observation_count_mismatch")
    cameras = value.get("cameras")
    if not isinstance(cameras, Mapping) or tuple(sorted(cameras)) != tuple(sorted(VISUAL_REVIEW_CAMERA_IDS)):
        raise ValueError("scene_pack_cameras_mismatch")
    for camera_id, camera in cameras.items():
        if not isinstance(camera, Mapping):
            raise ValueError(f"scene_pack_camera_invalid:{camera_id}")
        for name in ("fx", "fy", "cx", "cy"):
            _positive_finite(camera.get(name), f"camera_{camera_id}_{name}")
        resolution = camera.get("resolution")
        if (
            not isinstance(resolution, Sequence)
            or len(resolution) != 2
            or any(type(item) is not int or item <= 0 for item in resolution)
        ):
            raise ValueError(f"scene_pack_camera_resolution_invalid:{camera_id}")
    fixed_grasp = value.get("fixed_grasp")
    if not isinstance(fixed_grasp, Mapping):
        raise ValueError("scene_pack_fixed_grasp_missing")
    if fixed_grasp.get("semantics") != (
        "row_matrix_source_world_equals_source_to_gripper_times_gripper_world"
    ):
        raise ValueError("scene_pack_fixed_grasp_semantics_invalid")
    attachment_index = fixed_grasp.get("fixed_grasp_start_observation_index")
    if (
        type(attachment_index) is not int
        or attachment_index < 0
        or attachment_index >= EXPECTED_OBSERVATION_COUNT
    ):
        raise ValueError("scene_pack_fixed_grasp_index_invalid")
    matrix = np.asarray(fixed_grasp.get("source_to_gripper_row_matrix"), dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError("scene_pack_fixed_grasp_matrix_invalid")
    if not np.allclose(matrix[:, 3], [0.0, 0.0, 0.0, 1.0], atol=1.0e-9, rtol=0.0):
        raise ValueError("scene_pack_fixed_grasp_matrix_invalid")
    return {
        "observation_count": EXPECTED_OBSERVATION_COUNT,
        "camera_ids": tuple(sorted(cameras)),
        "robot_lanes": ROBOT_LANES,
        "fixed_grasp_start_observation_index": attachment_index,
    }
