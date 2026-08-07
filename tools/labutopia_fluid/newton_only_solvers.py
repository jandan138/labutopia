#!/usr/bin/env python3
"""Runtime adapters for the Newton-only LabUtopia fluid solver matrix.

Imports of Newton and Warp are deliberately lazy.  The parent orchestrator can
inspect the registry without importing a simulator runtime; only the sealed
runtime child constructs an adapter.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

import numpy as np

from tools.labutopia_fluid.fluid_benchmark_contract import LOGICAL_DT_S, interpolate_pose_xyzw
from tools.labutopia_fluid.newton_only_contract import adaptive_cfl_step, solver_spec


class SolverCapabilityError(RuntimeError):
    """The solver exists, but this benchmark scene cannot be represented faithfully."""


@dataclass
class StepDiagnostics:
    substeps: int
    dt_s: float
    maximum_speed_m_s: float
    actual_iterations: list[int] = field(default_factory=list)
    final_residuals: list[float] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class WcsphFrameInput:
    """One observation-frame input shared by Isaac and Newton adapters."""

    frame_index: int
    source_pose_xyzw: np.ndarray
    next_source_pose_xyzw: np.ndarray
    observation_dt_s: float = LOGICAL_DT_S


@dataclass(frozen=True)
class WcsphFrameOutput:
    """Device-resident WCSPH output; readback remains an explicit caller choice."""

    frame_index: int
    particle_positions_device: Any
    diagnostics: StepDiagnostics
    boundary_kind: str
    boundary_impulse_supported: bool


class FluidSolverAdapter(Protocol):
    solver_id: str
    particle_count: int
    particle_radius_m: float

    def logical_step(self, source_pose_xyzw: np.ndarray, next_source_pose_xyzw: np.ndarray) -> StepDiagnostics: ...

    def particle_positions(self) -> Any: ...

    def close(self) -> None: ...


def _quat_multiply_xyzw(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return np.asarray(
        [
            lw * rx + lx * rw + ly * rz - lz * ry,
            lw * ry - lx * rz + ly * rw + lz * rx,
            lw * rz + lx * ry - ly * rx + lz * rw,
            lw * rw - lx * rx - ly * ry - lz * rz,
        ],
        dtype=np.float64,
    )


def _source_velocity(start: np.ndarray, end: np.ndarray, dt_s: float) -> tuple[np.ndarray, np.ndarray]:
    linear = (end[:3] - start[:3]) / dt_s
    left_inverse = np.asarray([-start[3], -start[4], -start[5], start[6]], dtype=np.float64)
    delta = _quat_multiply_xyzw(end[3:], left_inverse)
    if delta[3] < 0.0:
        delta = -delta
    sine = float(np.linalg.norm(delta[:3]))
    if sine < 1.0e-12:
        angular = np.zeros(3, dtype=np.float64)
    else:
        angle = 2.0 * math.atan2(sine, float(np.clip(delta[3], -1.0, 1.0)))
        angular = delta[:3] / sine * angle / dt_s
    return linear.astype(np.float32), angular.astype(np.float32)


def _wp_transform(wp: Any, pose_xyzw: np.ndarray) -> Any:
    pose = np.asarray(pose_xyzw, dtype=np.float32)
    return wp.transform(wp.vec3(pose[:3]), wp.quat(pose[3], pose[4], pose[5], pose[6]))


def _rotation_matrix_xyzw(quaternion_xyzw: np.ndarray) -> np.ndarray:
    x, y, z, w = np.asarray(quaternion_xyzw, dtype=np.float64)
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm <= 0.0:
        raise ValueError("wrapper_quaternion_invalid")
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _wrapper_aabb(poses_xyzw: np.ndarray, half_extents: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    poses = np.asarray(poses_xyzw, dtype=np.float64)
    extents = np.asarray(half_extents, dtype=np.float64)
    if poses.ndim != 2 or poses.shape[1] != 7 or extents.shape != (len(poses), 3):
        raise ValueError("wrapper_aabb_inputs_invalid")
    world_extents = np.stack(
        [np.abs(_rotation_matrix_xyzw(pose[3:])) @ extent for pose, extent in zip(poses, extents, strict=True)]
    )
    return np.min(poses[:, :3] - world_extents, axis=0), np.max(
        poses[:, :3] + world_extents, axis=0
    )


_WARP_KERNELS: dict[str, Any] = {}


def _warp_kernels(wp: Any) -> Mapping[str, Any]:
    if _WARP_KERNELS:
        return _WARP_KERNELS

    @wp.func
    def poly6_weight(distance_sq: float, support_radius: float):
        h2 = support_radius * support_radius
        value = wp.max(h2 - distance_sq, 0.0)
        h3 = h2 * support_radius
        h9 = h3 * h3 * h3
        return 315.0 / (64.0 * 3.141592653589793 * h9) * value * value * value

    @wp.func
    def spiky_gradient(delta: wp.vec3, support_radius: float):
        distance = wp.length(delta)
        if distance > 1.0e-7 and distance < support_radius:
            h2 = support_radius * support_radius
            h6 = h2 * h2 * h2
            coefficient = -45.0 / (3.141592653589793 * h6)
            value = support_radius - distance
            return coefficient * value * value * delta / distance
        return wp.vec3(0.0, 0.0, 0.0)

    @wp.kernel
    def compute_density(
        hash_grid: wp.uint64,
        positions: wp.array(dtype=wp.vec3),
        densities: wp.array(dtype=wp.float32),
        particle_mass: float,
        support_radius: float,
    ):
        tid = wp.tid()
        particle_index = wp.hash_grid_point_id(hash_grid, tid)
        position = positions[particle_index]
        density = float(0.0)
        query = wp.hash_grid_query(hash_grid, position, support_radius)
        for neighbor in query:
            delta = position - positions[neighbor]
            density = density + particle_mass * poly6_weight(wp.dot(delta, delta), support_radius)
        densities[particle_index] = wp.max(density, 1.0e-6)

    @wp.kernel
    def compute_wcsph_acceleration(
        hash_grid: wp.uint64,
        positions: wp.array(dtype=wp.vec3),
        velocities: wp.array(dtype=wp.vec3),
        densities: wp.array(dtype=wp.float32),
        accelerations: wp.array(dtype=wp.vec3),
        particle_mass: float,
        support_radius: float,
        rest_density: float,
        sound_speed: float,
        viscosity: float,
        eos_gamma: float,
        pressure_floor_ratio: float,
        density_diffusion: float,
        xsph_coefficient: float,
        surface_tension: float,
        velocity_corrections: wp.array(dtype=wp.vec3),
        gravity_z: float,
    ):
        tid = wp.tid()
        particle_index = wp.hash_grid_point_id(hash_grid, tid)
        position = positions[particle_index]
        velocity = velocities[particle_index]
        density = densities[particle_index]
        effective_density = density + density_diffusion * (rest_density - density)
        pressure_scale = rest_density * sound_speed * sound_speed / eos_gamma
        pressure = pressure_scale * (wp.pow(effective_density / rest_density, eos_gamma) - 1.0)
        pressure = wp.max(pressure, -pressure_floor_ratio * pressure_scale)
        pressure_accel = wp.vec3(0.0, 0.0, 0.0)
        viscosity_accel = wp.vec3(0.0, 0.0, 0.0)
        surface_accel = wp.vec3(0.0, 0.0, 0.0)
        xsph_delta = wp.vec3(0.0, 0.0, 0.0)
        h2 = support_radius * support_radius
        h6 = h2 * h2 * h2
        viscosity_normalization = 45.0 / (3.141592653589793 * h6)
        query = wp.hash_grid_query(hash_grid, position, support_radius)
        for neighbor in query:
            if neighbor != particle_index:
                delta = position - positions[neighbor]
                distance = wp.length(delta)
                if distance < support_radius and distance > 1.0e-7:
                    neighbor_density = densities[neighbor]
                    neighbor_effective_density = neighbor_density + density_diffusion * (
                        rest_density - neighbor_density
                    )
                    neighbor_pressure = pressure_scale * (
                        wp.pow(neighbor_effective_density / rest_density, eos_gamma) - 1.0
                    )
                    neighbor_pressure = wp.max(
                        neighbor_pressure, -pressure_floor_ratio * pressure_scale
                    )
                    pressure_accel = pressure_accel - particle_mass * (
                        pressure / (density * density)
                        + neighbor_pressure / (neighbor_density * neighbor_density)
                    ) * spiky_gradient(delta, support_radius)
                    laplacian = viscosity_normalization * (support_radius - distance)
                    viscosity_accel = viscosity_accel + (
                        viscosity
                        * particle_mass
                        * (velocities[neighbor] - velocity)
                        / neighbor_density
                        * laplacian
                    )
                    weight = poly6_weight(wp.dot(delta, delta), support_radius)
                    xsph_delta = xsph_delta + (
                        particle_mass / neighbor_density * (velocities[neighbor] - velocity) * weight
                    )
                    surface_accel = surface_accel - (
                        surface_tension
                        * particle_mass
                        / neighbor_density
                        * weight
                        * delta
                    )
        velocity_corrections[particle_index] = xsph_coefficient * xsph_delta
        accelerations[particle_index] = (
            pressure_accel
            + viscosity_accel
            + surface_accel
            + wp.vec3(0.0, 0.0, gravity_z)
        )

    @wp.kernel
    def apply_xsph_velocity(
        velocities: wp.array(dtype=wp.vec3),
        velocity_corrections: wp.array(dtype=wp.vec3),
    ):
        particle_index = wp.tid()
        velocities[particle_index] = velocities[particle_index] + velocity_corrections[particle_index]

    @wp.kernel
    def copy_positions(
        positions: wp.array(dtype=wp.vec3),
        previous_positions: wp.array(dtype=wp.vec3),
    ):
        particle_index = wp.tid()
        previous_positions[particle_index] = positions[particle_index]

    @wp.kernel
    def integrate_velocity_position(
        positions: wp.array(dtype=wp.vec3),
        velocities: wp.array(dtype=wp.vec3),
        accelerations: wp.array(dtype=wp.vec3),
        dt_s: float,
    ):
        particle_index = wp.tid()
        velocity = velocities[particle_index] + accelerations[particle_index] * dt_s
        velocities[particle_index] = velocity
        positions[particle_index] = positions[particle_index] + velocity * dt_s

    @wp.kernel
    def predict_positions(
        positions: wp.array(dtype=wp.vec3),
        velocities: wp.array(dtype=wp.vec3),
        predicted: wp.array(dtype=wp.vec3),
        gravity_z: float,
        dt_s: float,
    ):
        particle_index = wp.tid()
        velocity = velocities[particle_index] + wp.vec3(0.0, 0.0, gravity_z) * dt_s
        velocities[particle_index] = velocity
        predicted[particle_index] = positions[particle_index] + velocity * dt_s

    @wp.kernel
    def pbf_lambdas(
        hash_grid: wp.uint64,
        predicted: wp.array(dtype=wp.vec3),
        densities: wp.array(dtype=wp.float32),
        lambdas: wp.array(dtype=wp.float32),
        maximum_residual: wp.array(dtype=wp.float32),
        particle_mass: float,
        support_radius: float,
        rest_density: float,
        relaxation: float,
    ):
        tid = wp.tid()
        particle_index = wp.hash_grid_point_id(hash_grid, tid)
        position = predicted[particle_index]
        density = float(0.0)
        gradient_i = wp.vec3(0.0, 0.0, 0.0)
        gradient_sum = float(0.0)
        query = wp.hash_grid_query(hash_grid, position, support_radius)
        for neighbor in query:
            delta = position - predicted[neighbor]
            density = density + particle_mass * poly6_weight(wp.dot(delta, delta), support_radius)
            if neighbor != particle_index:
                gradient_j = -particle_mass / rest_density * spiky_gradient(delta, support_radius)
                gradient_sum = gradient_sum + wp.dot(gradient_j, gradient_j)
                gradient_i = gradient_i - gradient_j
        constraint = density / rest_density - 1.0
        gradient_sum = gradient_sum + wp.dot(gradient_i, gradient_i)
        densities[particle_index] = density
        lambdas[particle_index] = -constraint / (gradient_sum + relaxation)
        wp.atomic_max(maximum_residual, 0, wp.abs(constraint))

    @wp.kernel
    def pbf_corrections(
        hash_grid: wp.uint64,
        predicted: wp.array(dtype=wp.vec3),
        lambdas: wp.array(dtype=wp.float32),
        corrections: wp.array(dtype=wp.vec3),
        particle_mass: float,
        support_radius: float,
        rest_density: float,
    ):
        tid = wp.tid()
        particle_index = wp.hash_grid_point_id(hash_grid, tid)
        position = predicted[particle_index]
        correction = wp.vec3(0.0, 0.0, 0.0)
        query = wp.hash_grid_query(hash_grid, position, support_radius)
        for neighbor in query:
            if neighbor != particle_index:
                delta = position - predicted[neighbor]
                correction = correction + (
                    lambdas[particle_index] + lambdas[neighbor]
                ) * particle_mass / rest_density * spiky_gradient(delta, support_radius)
        corrections[particle_index] = correction

    @wp.kernel
    def apply_corrections(
        predicted: wp.array(dtype=wp.vec3),
        corrections: wp.array(dtype=wp.vec3),
    ):
        particle_index = wp.tid()
        predicted[particle_index] = predicted[particle_index] + corrections[particle_index]

    @wp.kernel
    def apply_gravity(
        velocities: wp.array(dtype=wp.vec3),
        gravity_z: float,
        dt_s: float,
    ):
        particle_index = wp.tid()
        velocities[particle_index] = velocities[particle_index] + wp.vec3(
            0.0, 0.0, gravity_z
        ) * dt_s

    @wp.kernel
    def dfsph_factor(
        hash_grid: wp.uint64,
        positions: wp.array(dtype=wp.vec3),
        factors: wp.array(dtype=wp.float32),
        particle_mass: float,
        support_radius: float,
        rest_density: float,
        relaxation: float,
    ):
        tid = wp.tid()
        particle_index = wp.hash_grid_point_id(hash_grid, tid)
        position = positions[particle_index]
        gradient_i = wp.vec3(0.0, 0.0, 0.0)
        gradient_sum = float(0.0)
        query = wp.hash_grid_query(hash_grid, position, support_radius)
        for neighbor in query:
            if neighbor != particle_index:
                delta = position - positions[neighbor]
                gradient_j = -particle_mass / rest_density * spiky_gradient(
                    delta, support_radius
                )
                gradient_sum = gradient_sum + wp.dot(gradient_j, gradient_j)
                gradient_i = gradient_i - gradient_j
        factors[particle_index] = -1.0 / (
            gradient_sum + wp.dot(gradient_i, gradient_i) + relaxation
        )

    @wp.kernel
    def dfsph_divergence_kappa(
        hash_grid: wp.uint64,
        positions: wp.array(dtype=wp.vec3),
        velocities: wp.array(dtype=wp.vec3),
        factors: wp.array(dtype=wp.float32),
        kappas: wp.array(dtype=wp.float32),
        maximum_residual: wp.array(dtype=wp.float32),
        particle_mass: float,
        support_radius: float,
        rest_density: float,
    ):
        tid = wp.tid()
        particle_index = wp.hash_grid_point_id(hash_grid, tid)
        position = positions[particle_index]
        velocity = velocities[particle_index]
        density_rate = float(0.0)
        query = wp.hash_grid_query(hash_grid, position, support_radius)
        for neighbor in query:
            if neighbor != particle_index:
                delta = position - positions[neighbor]
                density_rate = density_rate + particle_mass * wp.dot(
                    velocity - velocities[neighbor],
                    spiky_gradient(delta, support_radius),
                )
        residual = wp.max(density_rate / rest_density, 0.0)
        kappas[particle_index] = factors[particle_index] * residual
        wp.atomic_max(maximum_residual, 0, residual)

    @wp.kernel
    def dfsph_density_kappa(
        hash_grid: wp.uint64,
        positions: wp.array(dtype=wp.vec3),
        velocities: wp.array(dtype=wp.vec3),
        densities: wp.array(dtype=wp.float32),
        factors: wp.array(dtype=wp.float32),
        kappas: wp.array(dtype=wp.float32),
        maximum_residual: wp.array(dtype=wp.float32),
        particle_mass: float,
        support_radius: float,
        rest_density: float,
        dt_s: float,
    ):
        tid = wp.tid()
        particle_index = wp.hash_grid_point_id(hash_grid, tid)
        position = positions[particle_index]
        velocity = velocities[particle_index]
        density_rate = float(0.0)
        query = wp.hash_grid_query(hash_grid, position, support_radius)
        for neighbor in query:
            if neighbor != particle_index:
                delta = position - positions[neighbor]
                density_rate = density_rate + particle_mass * wp.dot(
                    velocity - velocities[neighbor],
                    spiky_gradient(delta, support_radius),
                )
        predicted_density = densities[particle_index] + dt_s * density_rate
        residual = wp.max(predicted_density / rest_density - 1.0, 0.0) / dt_s
        kappas[particle_index] = factors[particle_index] * residual
        wp.atomic_max(maximum_residual, 0, residual)

    @wp.kernel
    def dfsph_velocity_correction(
        hash_grid: wp.uint64,
        positions: wp.array(dtype=wp.vec3),
        kappas: wp.array(dtype=wp.float32),
        velocity_delta: wp.array(dtype=wp.vec3),
        particle_mass: float,
        support_radius: float,
        rest_density: float,
    ):
        tid = wp.tid()
        particle_index = wp.hash_grid_point_id(hash_grid, tid)
        position = positions[particle_index]
        correction = wp.vec3(0.0, 0.0, 0.0)
        query = wp.hash_grid_query(hash_grid, position, support_radius)
        for neighbor in query:
            if neighbor != particle_index:
                delta = position - positions[neighbor]
                correction = correction + (
                    kappas[particle_index] + kappas[neighbor]
                ) * particle_mass / rest_density * spiky_gradient(
                    delta, support_radius
                )
        velocity_delta[particle_index] = correction

    @wp.kernel
    def apply_velocity_delta(
        velocities: wp.array(dtype=wp.vec3),
        velocity_delta: wp.array(dtype=wp.vec3),
        relaxation: float,
    ):
        particle_index = wp.tid()
        velocities[particle_index] = velocities[particle_index] + relaxation * velocity_delta[
            particle_index
        ]

    @wp.func
    def segment_aabb_overlap(
        start: wp.vec3,
        end: wp.vec3,
        lower: wp.vec3,
        upper: wp.vec3,
        margin: float,
    ):
        segment_lower = wp.vec3(
            wp.min(start[0], end[0]),
            wp.min(start[1], end[1]),
            wp.min(start[2], end[2]),
        )
        segment_upper = wp.vec3(
            wp.max(start[0], end[0]),
            wp.max(start[1], end[1]),
            wp.max(start[2], end[2]),
        )
        return (
            segment_upper[0] >= lower[0] - margin
            and segment_lower[0] <= upper[0] + margin
            and segment_upper[1] >= lower[1] - margin
            and segment_lower[1] <= upper[1] + margin
            and segment_upper[2] >= lower[2] - margin
            and segment_lower[2] <= upper[2] + margin
        )

    @wp.func
    def project_box_swept(
        previous_position: wp.vec3,
        position: wp.vec3,
        velocity: wp.vec3,
        previous_box_transform: wp.transform,
        box_transform: wp.transform,
        half_extents: wp.vec3,
        collision_margin: float,
        collider_velocity: wp.vec3,
        restitution: float,
        friction: float,
    ):
        previous_inverse = wp.transform_inverse(previous_box_transform)
        inverse = wp.transform_inverse(box_transform)
        previous_local = wp.transform_point(previous_inverse, previous_position)
        local = wp.transform_point(inverse, position)
        expanded = half_extents + wp.vec3(
            collision_margin, collision_margin, collision_margin
        )
        previous_inside = (
            wp.abs(previous_local[0]) < expanded[0]
            and wp.abs(previous_local[1]) < expanded[1]
            and wp.abs(previous_local[2]) < expanded[2]
        )
        delta = local - previous_local
        t_enter = float(0.0)
        t_exit = float(1.0)
        enter_axis = int(-1)
        enter_sign = float(0.0)
        intersects = bool(True)
        for axis in range(3):
            if wp.abs(delta[axis]) < 1.0e-8:
                if previous_local[axis] < -expanded[axis] or previous_local[axis] > expanded[axis]:
                    intersects = False
            else:
                inverse_direction = 1.0 / delta[axis]
                near = (-expanded[axis] - previous_local[axis]) * inverse_direction
                far = (expanded[axis] - previous_local[axis]) * inverse_direction
                normal_sign = -1.0
                if near > far:
                    temporary = near
                    near = far
                    far = temporary
                    normal_sign = 1.0
                if near > t_enter:
                    t_enter = near
                    enter_axis = axis
                    enter_sign = normal_sign
                t_exit = wp.min(t_exit, far)
                if t_enter > t_exit:
                    intersects = False
        swept_hit = (
            intersects
            and not previous_inside
            and enter_axis >= 0
            and t_exit >= 0.0
            and t_enter >= 0.0
            and t_enter <= 1.0
        )
        overlap_recovery = bool(False)
        normal_local = wp.vec3(0.0, 0.0, 0.0)
        if swept_hit:
            contact_t = wp.max(0.0, t_enter - 1.0e-4)
            local = previous_local + delta * contact_t
            normal_local[enter_axis] = enter_sign
            local = local + normal_local * 1.0e-6
            position = wp.transform_point(box_transform, local)
        # The simplified wrapper boxes intentionally overlap slightly.  A particle
        # that starts inside one proxy is not a new wall crossing, so repeatedly
        # projecting it would manufacture energy and eject the fluid.  Only an
        # outside-to-inside swept crossing is corrected here.
        if swept_hit or overlap_recovery:
            normal = wp.normalize(wp.transform_vector(box_transform, normal_local))
            relative = velocity - collider_velocity
            normal_speed = wp.dot(relative, normal)
            if normal_speed < 0.0:
                normal_component = normal_speed * normal
                tangent = relative - normal_component
                relative = -restitution * normal_component + (1.0 - friction) * tangent
                velocity = collider_velocity + relative
        return position, velocity, int(swept_hit), int(overlap_recovery)

    @wp.kernel
    def collide_scene_swept(
        previous_positions: wp.array(dtype=wp.vec3),
        positions: wp.array(dtype=wp.vec3),
        velocities: wp.array(dtype=wp.vec3),
        previous_source_pose: wp.transform,
        source_pose: wp.transform,
        source_linear_velocity: wp.vec3,
        source_angular_velocity: wp.vec3,
        source_box_local_poses: wp.array(dtype=wp.transform),
        source_box_half_extents: wp.array(dtype=wp.vec3),
        target_box_world_poses: wp.array(dtype=wp.transform),
        target_box_half_extents: wp.array(dtype=wp.vec3),
        source_bounds_lower: wp.vec3,
        source_bounds_upper: wp.vec3,
        target_bounds_lower: wp.vec3,
        target_bounds_upper: wp.vec3,
        table_top_z: float,
        collision_margin: float,
        restitution: float,
        friction: float,
        maximum_hits: int,
        counters: wp.array(dtype=wp.int32),
    ):
        particle_index = wp.tid()
        previous_position = previous_positions[particle_index]
        position = positions[particle_index]
        velocity = velocities[particle_index]
        source_origin = wp.transform_get_translation(source_pose)
        previous_source_local = wp.transform_point(
            wp.transform_inverse(previous_source_pose), previous_position
        )
        source_local = wp.transform_point(wp.transform_inverse(source_pose), position)
        hits = int(0)
        if segment_aabb_overlap(
            previous_source_local,
            source_local,
            source_bounds_lower,
            source_bounds_upper,
            collision_margin,
        ):
            wp.atomic_add(counters, 0, 1)
            for box_index in range(source_box_local_poses.shape[0]):
                if hits < maximum_hits:
                    previous_box = wp.transform_multiply(
                        previous_source_pose, source_box_local_poses[box_index]
                    )
                    box = wp.transform_multiply(
                        source_pose, source_box_local_poses[box_index]
                    )
                    box_center = wp.transform_get_translation(box)
                    collider_velocity = source_linear_velocity + wp.cross(
                        source_angular_velocity, box_center - source_origin
                    )
                    position, velocity, swept, overlap = project_box_swept(
                        previous_position,
                        position,
                        velocity,
                        previous_box,
                        box,
                        source_box_half_extents[box_index],
                        collision_margin,
                        collider_velocity,
                        restitution,
                        friction,
                    )
                    hits = hits + swept + overlap
                    if swept > 0:
                        wp.atomic_add(counters, 2, 1)
                    if overlap > 0:
                        wp.atomic_add(counters, 3, 1)
        if segment_aabb_overlap(
            previous_position,
            position,
            target_bounds_lower,
            target_bounds_upper,
            collision_margin,
        ):
            wp.atomic_add(counters, 1, 1)
            for box_index in range(target_box_world_poses.shape[0]):
                if hits < maximum_hits:
                    box = target_box_world_poses[box_index]
                    position, velocity, swept, overlap = project_box_swept(
                        previous_position,
                        position,
                        velocity,
                        box,
                        box,
                        target_box_half_extents[box_index],
                        collision_margin,
                        wp.vec3(0.0, 0.0, 0.0),
                        restitution,
                        friction,
                    )
                    hits = hits + swept + overlap
                    if swept > 0:
                        wp.atomic_add(counters, 2, 1)
                    if overlap > 0:
                        wp.atomic_add(counters, 3, 1)
        floor = table_top_z + collision_margin
        if position[2] < floor:
            position[2] = floor
            if velocity[2] < 0.0:
                velocity[2] = -restitution * velocity[2]
            velocity[0] = velocity[0] * (1.0 - friction)
            velocity[1] = velocity[1] * (1.0 - friction)
            wp.atomic_add(counters, 4, 1)
        positions[particle_index] = position
        velocities[particle_index] = velocity

    @wp.func
    def project_box(
        position: wp.vec3,
        velocity: wp.vec3,
        box_transform: wp.transform,
        half_extents: wp.vec3,
        particle_radius: float,
        collider_velocity: wp.vec3,
        restitution: float,
        friction: float,
    ):
        inverse = wp.transform_inverse(box_transform)
        local = wp.transform_point(inverse, position)
        expanded = half_extents + wp.vec3(particle_radius, particle_radius, particle_radius)
        distance = expanded - wp.vec3(
            wp.abs(local[0]),
            wp.abs(local[1]),
            wp.abs(local[2]),
        )
        if distance[0] > 0.0 and distance[1] > 0.0 and distance[2] > 0.0:
            axis = int(0)
            penetration = distance[0]
            if distance[1] < penetration:
                axis = 1
                penetration = distance[1]
            if distance[2] < penetration:
                axis = 2
            normal_local = wp.vec3(0.0, 0.0, 0.0)
            sign = wp.where(local[axis] >= 0.0, 1.0, -1.0)
            normal_local[axis] = sign
            local[axis] = sign * expanded[axis]
            position = wp.transform_point(box_transform, local)
            normal = wp.normalize(wp.transform_vector(box_transform, normal_local))
            relative = velocity - collider_velocity
            normal_speed = wp.dot(relative, normal)
            if normal_speed < 0.0:
                normal_component = normal_speed * normal
                tangent = relative - normal_component
                relative = -restitution * normal_component + (1.0 - friction) * tangent
                velocity = collider_velocity + relative
        return position, velocity

    @wp.kernel
    def collide_scene(
        positions: wp.array(dtype=wp.vec3),
        velocities: wp.array(dtype=wp.vec3),
        source_pose: wp.transform,
        source_linear_velocity: wp.vec3,
        source_angular_velocity: wp.vec3,
        source_box_local_poses: wp.array(dtype=wp.transform),
        source_box_half_extents: wp.array(dtype=wp.vec3),
        target_box_world_poses: wp.array(dtype=wp.transform),
        target_box_half_extents: wp.array(dtype=wp.vec3),
        table_top_z: float,
        particle_radius: float,
        restitution: float,
        friction: float,
    ):
        particle_index = wp.tid()
        position = positions[particle_index]
        velocity = velocities[particle_index]
        source_origin = wp.transform_get_translation(source_pose)
        for box_index in range(source_box_local_poses.shape[0]):
            box_transform = wp.transform_multiply(source_pose, source_box_local_poses[box_index])
            box_center = wp.transform_get_translation(box_transform)
            collider_velocity = source_linear_velocity + wp.cross(source_angular_velocity, box_center - source_origin)
            position, velocity = project_box(
                position,
                velocity,
                box_transform,
                source_box_half_extents[box_index],
                particle_radius,
                collider_velocity,
                restitution,
                friction,
            )
        for box_index in range(target_box_world_poses.shape[0]):
            position, velocity = project_box(
                position,
                velocity,
                target_box_world_poses[box_index],
                target_box_half_extents[box_index],
                particle_radius,
                wp.vec3(0.0, 0.0, 0.0),
                restitution,
                friction,
            )
        floor = table_top_z + particle_radius
        if position[2] < floor:
            position[2] = floor
            if velocity[2] < 0.0:
                velocity[2] = -restitution * velocity[2]
            velocity[0] = velocity[0] * (1.0 - friction)
            velocity[1] = velocity[1] * (1.0 - friction)
        positions[particle_index] = position
        velocities[particle_index] = velocity

    @wp.kernel
    def finalize_predicted(
        positions: wp.array(dtype=wp.vec3),
        predicted: wp.array(dtype=wp.vec3),
        velocities: wp.array(dtype=wp.vec3),
        inverse_dt: float,
    ):
        particle_index = wp.tid()
        velocity = (predicted[particle_index] - positions[particle_index]) * inverse_dt
        positions[particle_index] = predicted[particle_index]
        velocities[particle_index] = velocity

    @wp.kernel
    def maximum_speed(
        velocities: wp.array(dtype=wp.vec3),
        result: wp.array(dtype=wp.float32),
    ):
        particle_index = wp.tid()
        wp.atomic_max(result, 0, wp.length(velocities[particle_index]))

    @wp.kernel
    def set_kinematic_body_pose(
        body_q: wp.array(dtype=wp.transform),
        body_qd: wp.array(dtype=wp.spatial_vector),
        body_index: int,
        pose: wp.transform,
        angular_velocity: wp.vec3,
        linear_velocity: wp.vec3,
    ):
        body_q[body_index] = pose
        body_qd[body_index] = wp.spatial_vector(
            angular_velocity[0],
            angular_velocity[1],
            angular_velocity[2],
            linear_velocity[0],
            linear_velocity[1],
            linear_velocity[2],
        )

    _WARP_KERNELS.update(
        compute_density=compute_density,
        compute_wcsph_acceleration=compute_wcsph_acceleration,
        apply_xsph_velocity=apply_xsph_velocity,
        copy_positions=copy_positions,
        integrate_velocity_position=integrate_velocity_position,
        predict_positions=predict_positions,
        pbf_lambdas=pbf_lambdas,
        pbf_corrections=pbf_corrections,
        apply_corrections=apply_corrections,
        apply_gravity=apply_gravity,
        dfsph_factor=dfsph_factor,
        dfsph_divergence_kappa=dfsph_divergence_kappa,
        dfsph_density_kappa=dfsph_density_kappa,
        dfsph_velocity_correction=dfsph_velocity_correction,
        apply_velocity_delta=apply_velocity_delta,
        collide_scene=collide_scene,
        collide_scene_swept=collide_scene_swept,
        finalize_predicted=finalize_predicted,
        maximum_speed=maximum_speed,
        set_kinematic_body_pose=set_kinematic_body_pose,
    )
    return _WARP_KERNELS


class WarpHashFluidAdapter:
    """WCSPH or PBF implementation with common moving-wrapper collisions."""

    def __init__(
        self,
        *,
        solver_id: str,
        initial_positions: np.ndarray,
        particle_radius_m: float,
        particle_mass_kg: float,
        source_box_poses_xyzw: np.ndarray,
        source_box_half_extents: np.ndarray,
        target_box_poses_xyzw: np.ndarray,
        target_box_half_extents: np.ndarray,
        table_top_z_m: float,
        parameters: Mapping[str, Any],
        device: str = "cuda:0",
    ) -> None:
        import warp as wp

        spec = solver_spec(solver_id)
        if solver_id not in {
            "labutopia_wcsph",
            "warp_example_sph",
            "splishsplash_pbf_port",
            "warp_example_apic",
            "labutopia_dfsph",
            "splishsplash_dfsph_port",
        }:
            raise ValueError(f"warp_hash_adapter_solver_invalid:{solver_id}")
        positions = np.asarray(initial_positions, dtype=np.float32)
        if positions.ndim != 2 or positions.shape[1] != 3 or not np.isfinite(positions).all():
            raise ValueError("initial_positions_invalid")
        self.wp = wp
        self.kernels = _warp_kernels(wp)
        self.device = wp.get_device(device)
        self.solver_id = spec.solver_id
        self.algorithm = (
            "pbf"
            if solver_id == "splishsplash_pbf_port"
            else "apic"
            if solver_id == "warp_example_apic"
            else "wcsph"
        )
        self.particle_count = int(positions.shape[0])
        self.particle_radius_m = float(particle_radius_m)
        self.particle_mass_kg = float(particle_mass_kg)
        self.support_radius_m = float(parameters.get("support_radius_m", particle_radius_m * 4.0))
        self.rest_density = float(parameters.get("rest_density_kg_m3", 1000.0))
        self.sound_speed = float(parameters.get("sound_speed_m_s", 12.0))
        self.viscosity = float(parameters.get("viscosity", 0.002))
        self.eos_gamma = float(parameters.get("eos_gamma", 1.0))
        self.pressure_floor_ratio = float(parameters.get("pressure_floor_ratio", 0.0))
        self.density_diffusion = float(parameters.get("density_diffusion", 0.0))
        self.xsph_coefficient = float(parameters.get("xsph_coefficient", 0.0))
        self.surface_tension = float(parameters.get("surface_tension", 0.0))
        self.maximum_iterations = int(parameters.get("maximum_iterations", 6))
        self.minimum_iterations = int(parameters.get("minimum_iterations", 2))
        self.tolerance = float(parameters.get("tolerance", 0.01))
        self.relaxation = float(parameters.get("relaxation", 1.0e-6))
        self.cfl = float(parameters.get("cfl", 0.4))
        self.minimum_dt_s = float(parameters.get("minimum_dt_s", 1.0 / 3840.0))
        self.maximum_dt_s = float(parameters.get("maximum_dt_s", 1.0 / 120.0))
        self.restitution = float(parameters.get("restitution", 0.0))
        self.friction = float(parameters.get("friction", 0.05))
        self.boundary_kind = str(parameters.get("boundary_kind", "boxes"))
        if self.boundary_kind != "boxes":
            raise SolverCapabilityError(
                f"boundary_kind_not_implemented:{self.boundary_kind}"
            )
        self.collision_mode = str(parameters.get("collision_mode", "discrete_v1"))
        if self.collision_mode not in {"discrete_v1", "swept_v2"}:
            raise ValueError("collision_mode_invalid")
        self.collision_skin_ratio = float(parameters.get("collision_skin_ratio", 0.25))
        self.collision_max_hits = int(parameters.get("collision_max_hits", 4))
        if (
            self.eos_gamma <= 0.0
            or not 0.0 <= self.pressure_floor_ratio <= 1.0
            or not 0.0 <= self.density_diffusion <= 1.0
            or not 0.0 <= self.xsph_coefficient <= 1.0
            or self.surface_tension < 0.0
            or not 0.0 <= self.collision_skin_ratio <= 1.0
            or self.collision_max_hits < 1
            or self.collision_max_hits > 8
        ):
            raise ValueError("wcsph_quality_parameters_invalid")
        self.profile_stages = bool(parameters.get("profile_stages", False))
        self.positions = wp.array(positions, dtype=wp.vec3, device=self.device)
        self.previous_positions = wp.array(positions, dtype=wp.vec3, device=self.device)
        self.velocities = wp.zeros(self.particle_count, dtype=wp.vec3, device=self.device)
        self.velocity_corrections = wp.zeros_like(self.velocities)
        self.accelerations = wp.zeros_like(self.velocities)
        self.predicted = wp.zeros_like(self.positions)
        self.corrections = wp.zeros_like(self.positions)
        self.densities = wp.zeros(self.particle_count, dtype=wp.float32, device=self.device)
        self.lambdas = wp.zeros(self.particle_count, dtype=wp.float32, device=self.device)
        self.maximum_value = wp.zeros(1, dtype=wp.float32, device=self.device)
        self.collision_counters = wp.zeros(5, dtype=wp.int32, device=self.device)
        bounds = np.ptp(positions, axis=0) + 0.5
        dimensions = tuple(max(8, int(math.ceil(float(value) / self.support_radius_m))) for value in bounds)
        self.hash_grid = wp.HashGrid(*dimensions, device=self.device)
        self.source_boxes = wp.array(
            [_wp_transform(wp, pose) for pose in np.asarray(source_box_poses_xyzw)],
            dtype=wp.transform,
            device=self.device,
        )
        self.source_extents = wp.array(
            np.asarray(source_box_half_extents, dtype=np.float32), dtype=wp.vec3, device=self.device
        )
        self.target_boxes = wp.array(
            [_wp_transform(wp, pose) for pose in np.asarray(target_box_poses_xyzw)],
            dtype=wp.transform,
            device=self.device,
        )
        self.target_extents = wp.array(
            np.asarray(target_box_half_extents, dtype=np.float32), dtype=wp.vec3, device=self.device
        )
        source_lower, source_upper = _wrapper_aabb(
            np.asarray(source_box_poses_xyzw), np.asarray(source_box_half_extents)
        )
        target_lower, target_upper = _wrapper_aabb(
            np.asarray(target_box_poses_xyzw), np.asarray(target_box_half_extents)
        )
        self.source_bounds_lower = wp.vec3(source_lower.astype(np.float32))
        self.source_bounds_upper = wp.vec3(source_upper.astype(np.float32))
        self.target_bounds_lower = wp.vec3(target_lower.astype(np.float32))
        self.target_bounds_upper = wp.vec3(target_upper.astype(np.float32))
        self.table_top_z_m = float(table_top_z_m)

    def _maximum_speed(self) -> float:
        self.maximum_value.zero_()
        self.wp.launch(
            self.kernels["maximum_speed"],
            dim=self.particle_count,
            inputs=(self.velocities, self.maximum_value),
            device=self.device,
        )
        return float(self.maximum_value.numpy()[0])

    def _collide(
        self,
        source_pose: np.ndarray,
        source_linear_velocity: np.ndarray,
        source_angular_velocity: np.ndarray,
        *,
        positions: Any | None = None,
    ) -> None:
        selected_positions = self.positions if positions is None else positions
        self.wp.launch(
            self.kernels["collide_scene"],
            dim=self.particle_count,
            inputs=(
                selected_positions,
                self.velocities,
                _wp_transform(self.wp, source_pose),
                self.wp.vec3(source_linear_velocity),
                self.wp.vec3(source_angular_velocity),
                self.source_boxes,
                self.source_extents,
                self.target_boxes,
                self.target_extents,
                self.table_top_z_m,
                self.particle_radius_m,
                self.restitution,
                self.friction,
            ),
            device=self.device,
        )

    def _collide_swept(
        self,
        previous_source_pose: np.ndarray,
        source_pose: np.ndarray,
        source_linear_velocity: np.ndarray,
        source_angular_velocity: np.ndarray,
    ) -> None:
        self.wp.launch(
            self.kernels["collide_scene_swept"],
            dim=self.particle_count,
            inputs=(
                self.previous_positions,
                self.positions,
                self.velocities,
                _wp_transform(self.wp, previous_source_pose),
                _wp_transform(self.wp, source_pose),
                self.wp.vec3(source_linear_velocity),
                self.wp.vec3(source_angular_velocity),
                self.source_boxes,
                self.source_extents,
                self.target_boxes,
                self.target_extents,
                self.source_bounds_lower,
                self.source_bounds_upper,
                self.target_bounds_lower,
                self.target_bounds_upper,
                self.table_top_z_m,
                self.particle_radius_m * (1.0 + self.collision_skin_ratio),
                self.restitution,
                self.friction,
                self.collision_max_hits,
                self.collision_counters,
            ),
            device=self.device,
        )

    def _profiled_stage(self, function: Any) -> float:
        started = time.perf_counter()
        function()
        self.wp.synchronize_device(self.device)
        return (time.perf_counter() - started) * 1000.0

    def _wcsph_substep(
        self,
        dt_s: float,
        previous_source_pose: np.ndarray,
        source_pose: np.ndarray,
        linear: np.ndarray,
        angular: np.ndarray,
    ) -> dict[str, float]:
        if self.profile_stages:
            return {
                "hash_grid_ms": self._profiled_stage(
                    lambda: self.hash_grid.build(self.positions, self.support_radius_m)
                ),
                "density_ms": self._profiled_stage(
                    lambda: self.wp.launch(
                        self.kernels["compute_density"],
                        dim=self.particle_count,
                        inputs=(
                            self.hash_grid.id,
                            self.positions,
                            self.densities,
                            self.particle_mass_kg,
                            self.support_radius_m,
                        ),
                        device=self.device,
                    )
                ),
                "force_ms": self._profiled_stage(
                    lambda: self.wp.launch(
                        self.kernels["compute_wcsph_acceleration"],
                        dim=self.particle_count,
                        inputs=(
                            self.hash_grid.id,
                            self.positions,
                            self.velocities,
                            self.densities,
                            self.accelerations,
                            self.particle_mass_kg,
                            self.support_radius_m,
                            self.rest_density,
                            self.sound_speed,
                            self.viscosity,
                            self.eos_gamma,
                            self.pressure_floor_ratio,
                            self.density_diffusion,
                            self.xsph_coefficient,
                            self.surface_tension,
                            self.velocity_corrections,
                            -9.81,
                        ),
                        device=self.device,
                    )
                ),
                "integration_ms": self._profiled_stage(
                    lambda: self._integrate_wcsph(dt_s)
                ),
                "collision_ms": self._profiled_stage(
                    lambda: self._collide_swept(
                        previous_source_pose, source_pose, linear, angular
                    )
                    if self.collision_mode == "swept_v2"
                    else self._collide(source_pose, linear, angular)
                ),
            }
        self.hash_grid.build(self.positions, self.support_radius_m)
        self.wp.launch(
            self.kernels["compute_density"],
            dim=self.particle_count,
            inputs=(self.hash_grid.id, self.positions, self.densities, self.particle_mass_kg, self.support_radius_m),
            device=self.device,
        )
        self.wp.launch(
            self.kernels["compute_wcsph_acceleration"],
            dim=self.particle_count,
            inputs=(
                self.hash_grid.id,
                self.positions,
                self.velocities,
                self.densities,
                self.accelerations,
                self.particle_mass_kg,
                self.support_radius_m,
                self.rest_density,
                self.sound_speed,
                self.viscosity,
                self.eos_gamma,
                self.pressure_floor_ratio,
                self.density_diffusion,
                self.xsph_coefficient,
                self.surface_tension,
                self.velocity_corrections,
                -9.81,
            ),
            device=self.device,
        )
        self._integrate_wcsph(dt_s)
        if self.collision_mode == "swept_v2":
            self._collide_swept(previous_source_pose, source_pose, linear, angular)
        else:
            self._collide(source_pose, linear, angular)
        return {}

    def _integrate_wcsph(self, dt_s: float) -> None:
        self.wp.launch(
            self.kernels["copy_positions"],
            dim=self.particle_count,
            inputs=(self.positions, self.previous_positions),
            device=self.device,
        )
        if self.xsph_coefficient > 0.0:
            self.wp.launch(
                self.kernels["apply_xsph_velocity"],
                dim=self.particle_count,
                inputs=(self.velocities, self.velocity_corrections),
                device=self.device,
            )
        self.wp.launch(
            self.kernels["integrate_velocity_position"],
            dim=self.particle_count,
            inputs=(self.positions, self.velocities, self.accelerations, dt_s),
            device=self.device,
        )

    def _pbf_substep(
        self, dt_s: float, source_pose: np.ndarray, linear: np.ndarray, angular: np.ndarray
    ) -> tuple[int, float]:
        wp = self.wp
        wp.launch(
            self.kernels["predict_positions"],
            dim=self.particle_count,
            inputs=(self.positions, self.velocities, self.predicted, -9.81, dt_s),
            device=self.device,
        )
        actual_iterations = self.maximum_iterations
        final_residual = math.inf
        for iteration in range(1, self.maximum_iterations + 1):
            self.hash_grid.build(self.predicted, self.support_radius_m)
            self.maximum_value.zero_()
            wp.launch(
                self.kernels["pbf_lambdas"],
                dim=self.particle_count,
                inputs=(
                    self.hash_grid.id,
                    self.predicted,
                    self.densities,
                    self.lambdas,
                    self.maximum_value,
                    self.particle_mass_kg,
                    self.support_radius_m,
                    self.rest_density,
                    self.relaxation,
                ),
                device=self.device,
            )
            wp.launch(
                self.kernels["pbf_corrections"],
                dim=self.particle_count,
                inputs=(
                    self.hash_grid.id,
                    self.predicted,
                    self.lambdas,
                    self.corrections,
                    self.particle_mass_kg,
                    self.support_radius_m,
                    self.rest_density,
                ),
                device=self.device,
            )
            wp.launch(
                self.kernels["apply_corrections"],
                dim=self.particle_count,
                inputs=(self.predicted, self.corrections),
                device=self.device,
            )
            final_residual = float(self.maximum_value.numpy()[0])
            if iteration >= self.minimum_iterations and final_residual <= self.tolerance:
                actual_iterations = iteration
                break
        wp.launch(
            self.kernels["finalize_predicted"],
            dim=self.particle_count,
            inputs=(self.positions, self.predicted, self.velocities, 1.0 / dt_s),
            device=self.device,
        )
        self._collide(source_pose, linear, angular)
        return actual_iterations, final_residual

    def logical_step(self, source_pose_xyzw: np.ndarray, next_source_pose_xyzw: np.ndarray) -> StepDiagnostics:
        cfl_started = time.perf_counter()
        maximum_speed = self._maximum_speed()
        cfl_readback_ms = (time.perf_counter() - cfl_started) * 1000.0
        cfl = adaptive_cfl_step(
            maximum_speed_m_s=maximum_speed,
            support_radius_m=self.support_radius_m,
            sound_speed_m_s=self.sound_speed if self.algorithm == "wcsph" else 0.0,
            cfl=self.cfl,
            minimum_dt_s=self.minimum_dt_s,
            maximum_dt_s=self.maximum_dt_s,
        )
        substeps = int(cfl["substeps"])
        dt_s = float(cfl["dt_s"])
        linear, angular = _source_velocity(source_pose_xyzw, next_source_pose_xyzw, substeps * dt_s)
        actual_iterations: list[int] = []
        final_residuals: list[float] = []
        stage_timings: dict[str, float] = {}
        if self.collision_mode == "swept_v2":
            self.collision_counters.zero_()
        started = time.perf_counter()
        for substep in range(substeps):
            previous_pose = interpolate_pose_xyzw(
                source_pose_xyzw, next_source_pose_xyzw, substep / substeps
            )
            pose = interpolate_pose_xyzw(source_pose_xyzw, next_source_pose_xyzw, (substep + 1) / substeps)
            if self.algorithm == "wcsph":
                for name, value in self._wcsph_substep(
                    dt_s, previous_pose, pose, linear, angular
                ).items():
                    stage_timings[name] = stage_timings.get(name, 0.0) + value
            else:
                actual, residual = self._pbf_substep(dt_s, pose, linear, angular)
                actual_iterations.append(actual)
                final_residuals.append(residual)
        self.wp.synchronize_device(self.device)
        physics_ms = (time.perf_counter() - started) * 1000.0
        timings = {"physics_ms": physics_ms, "cfl_readback_ms": cfl_readback_ms}
        if stage_timings:
            timings.update(stage_timings)
        counters = {}
        if self.collision_mode == "swept_v2":
            values = self.collision_counters.numpy().astype(np.int64)
            counters = {
                "source_broadphase_particles": int(values[0]),
                "target_broadphase_particles": int(values[1]),
                "swept_contacts": int(values[2]),
                "overlap_recoveries": int(values[3]),
                "table_contacts": int(values[4]),
            }
        return StepDiagnostics(
            substeps=substeps,
            dt_s=dt_s,
            maximum_speed_m_s=maximum_speed,
            actual_iterations=actual_iterations,
            final_residuals=final_residuals,
            timings_ms=timings,
            counters=counters,
        )

    def step_frame(self, frame: WcsphFrameInput) -> WcsphFrameOutput:
        if self.solver_id != "labutopia_wcsph":
            raise ValueError("step_frame_requires_labutopia_wcsph")
        if frame.frame_index < 0:
            raise ValueError("frame_index_invalid")
        if not math.isclose(
            float(frame.observation_dt_s), LOGICAL_DT_S, rel_tol=0.0, abs_tol=1.0e-12
        ):
            raise ValueError("observation_dt_mismatch")
        diagnostics = self.logical_step(
            frame.source_pose_xyzw,
            frame.next_source_pose_xyzw,
        )
        return WcsphFrameOutput(
            frame_index=frame.frame_index,
            particle_positions_device=self.positions,
            diagnostics=diagnostics,
            boundary_kind=self.boundary_kind,
            boundary_impulse_supported=False,
        )

    def particle_positions(self) -> Any:
        return self.positions

    def close(self) -> None:
        return None


class WarpDfsphFluidAdapter(WarpHashFluidAdapter):
    """LabUtopia DFSPH density/divergence velocity projection on Warp."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.solver_id not in {"labutopia_dfsph", "splishsplash_dfsph_port"}:
            raise ValueError("warp_dfsph_adapter_solver_invalid")
        parameters = kwargs["parameters"]
        self.divergence_maximum_iterations = int(
            parameters.get("divergence_maximum_iterations", 4)
        )
        self.density_maximum_iterations = int(
            parameters.get("density_maximum_iterations", 6)
        )
        self.minimum_iterations = int(parameters.get("minimum_iterations", 2))
        self.divergence_tolerance = float(
            parameters.get("divergence_tolerance_s_inv", 0.1)
        )
        self.density_tolerance = float(
            parameters.get("density_tolerance_s_inv", 0.1)
        )
        self.projection_relaxation = float(
            parameters.get("projection_relaxation", 0.5)
        )
        if (
            self.minimum_iterations < 1
            or self.divergence_maximum_iterations < self.minimum_iterations
            or self.density_maximum_iterations < self.minimum_iterations
            or self.divergence_tolerance <= 0.0
            or self.density_tolerance <= 0.0
            or not 0.0 < self.projection_relaxation <= 1.0
        ):
            raise ValueError("dfsph_parameters_invalid")
        self.factors = self.wp.zeros(
            self.particle_count, dtype=self.wp.float32, device=self.device
        )
        self.velocity_delta = self.wp.zeros_like(self.velocities)

    def _projection_iteration(
        self,
        *,
        density_projection: bool,
        dt_s: float,
    ) -> float:
        self.maximum_value.zero_()
        kernel = (
            self.kernels["dfsph_density_kappa"]
            if density_projection
            else self.kernels["dfsph_divergence_kappa"]
        )
        if density_projection:
            inputs = (
                self.hash_grid.id,
                self.positions,
                self.velocities,
                self.densities,
                self.factors,
                self.lambdas,
                self.maximum_value,
                self.particle_mass_kg,
                self.support_radius_m,
                self.rest_density,
                dt_s,
            )
        else:
            inputs = (
                self.hash_grid.id,
                self.positions,
                self.velocities,
                self.factors,
                self.lambdas,
                self.maximum_value,
                self.particle_mass_kg,
                self.support_radius_m,
                self.rest_density,
            )
        self.wp.launch(kernel, dim=self.particle_count, inputs=inputs, device=self.device)
        self.wp.launch(
            self.kernels["dfsph_velocity_correction"],
            dim=self.particle_count,
            inputs=(
                self.hash_grid.id,
                self.positions,
                self.lambdas,
                self.velocity_delta,
                self.particle_mass_kg,
                self.support_radius_m,
                self.rest_density,
            ),
            device=self.device,
        )
        self.wp.launch(
            self.kernels["apply_velocity_delta"],
            dim=self.particle_count,
            inputs=(self.velocities, self.velocity_delta, self.projection_relaxation),
            device=self.device,
        )
        return float(self.maximum_value.numpy()[0])

    def _dfsph_substep(
        self,
        dt_s: float,
        source_pose: np.ndarray,
        linear: np.ndarray,
        angular: np.ndarray,
    ) -> tuple[list[int], list[float]]:
        wp = self.wp
        self.hash_grid.build(self.positions, self.support_radius_m)
        wp.launch(
            self.kernels["compute_density"],
            dim=self.particle_count,
            inputs=(
                self.hash_grid.id,
                self.positions,
                self.densities,
                self.particle_mass_kg,
                self.support_radius_m,
            ),
            device=self.device,
        )
        wp.launch(
            self.kernels["dfsph_factor"],
            dim=self.particle_count,
            inputs=(
                self.hash_grid.id,
                self.positions,
                self.factors,
                self.particle_mass_kg,
                self.support_radius_m,
                self.rest_density,
                self.relaxation,
            ),
            device=self.device,
        )
        wp.launch(
            self.kernels["apply_gravity"],
            dim=self.particle_count,
            inputs=(self.velocities, -9.81, dt_s),
            device=self.device,
        )
        counts = []
        residuals = []
        for density_projection, maximum, tolerance in (
            (False, self.divergence_maximum_iterations, self.divergence_tolerance),
            (True, self.density_maximum_iterations, self.density_tolerance),
        ):
            residual = math.inf
            actual = maximum
            for iteration in range(1, maximum + 1):
                residual = self._projection_iteration(
                    density_projection=density_projection,
                    dt_s=dt_s,
                )
                if iteration >= self.minimum_iterations and residual <= tolerance:
                    actual = iteration
                    break
            counts.append(actual)
            residuals.append(residual)
        # Gravity and pressure have already modified velocity; clear the
        # shared acceleration scratch before advancing positions.
        self.accelerations.zero_()
        wp.launch(
            self.kernels["integrate_velocity_position"],
            dim=self.particle_count,
            inputs=(self.positions, self.velocities, self.accelerations, dt_s),
            device=self.device,
        )
        self._collide(source_pose, linear, angular)
        return counts, residuals

    def logical_step(
        self, source_pose_xyzw: np.ndarray, next_source_pose_xyzw: np.ndarray
    ) -> StepDiagnostics:
        maximum_speed = self._maximum_speed()
        cfl = adaptive_cfl_step(
            maximum_speed_m_s=maximum_speed,
            support_radius_m=self.support_radius_m,
            cfl=self.cfl,
            minimum_dt_s=self.minimum_dt_s,
            maximum_dt_s=self.maximum_dt_s,
        )
        substeps = int(cfl["substeps"])
        dt_s = float(cfl["dt_s"])
        linear, angular = _source_velocity(
            source_pose_xyzw, next_source_pose_xyzw, substeps * dt_s
        )
        counts = []
        residuals = []
        started = time.perf_counter()
        for substep in range(substeps):
            pose = interpolate_pose_xyzw(
                source_pose_xyzw,
                next_source_pose_xyzw,
                (substep + 1) / substeps,
            )
            substep_counts, substep_residuals = self._dfsph_substep(
                dt_s, pose, linear, angular
            )
            counts.extend(substep_counts)
            residuals.extend(substep_residuals)
        self.wp.synchronize_device(self.device)
        return StepDiagnostics(
            substeps=substeps,
            dt_s=dt_s,
            maximum_speed_m_s=maximum_speed,
            actual_iterations=counts,
            final_residuals=residuals,
            timings_ms={"physics_ms": (time.perf_counter() - started) * 1000.0},
        )


class WarpApicFluidAdapter(WarpHashFluidAdapter):
    """Adapt Warp's installed official FEM APIC example to LabUtopia.

    The particle/grid transfers and Schur-complement pressure projection are
    the official Warp example path.  LabUtopia's moving concave beaker,
    receiver, and table projection is applied after each APIC advection step;
    this boundary adaptation is deliberately reported as experimental rather
    than algorithm-equivalent to a native cut-cell APIC boundary.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.solver_id != "warp_example_apic":
            raise ValueError("warp_apic_adapter_solver_invalid")
        import warp.fem as fem

        self.fem = fem
        self.voxel_size_m = float(
            kwargs["parameters"].get("voxel_size_m", self.particle_radius_m * 4.0)
        )
        self.maximum_iterations = int(kwargs["parameters"].get("maximum_iterations", 80))
        self.tolerance = float(kwargs["parameters"].get("tolerance", 1.0e-5))
        if self.voxel_size_m <= 0.0 or self.maximum_iterations < 1 or self.tolerance <= 0.0:
            raise ValueError("warp_apic_parameters_invalid")
        particle_volume = self.particle_mass_kg / self.rest_density
        self.particle_volumes = self.wp.full(
            self.particle_count,
            particle_volume,
            dtype=self.wp.float32,
            device=self.device,
        )
        self.velocity_gradients = self.wp.zeros(
            self.particle_count, dtype=self.wp.mat33, device=self.device
        )
        self.next_positions = self.wp.empty_like(self.positions)
        self.next_velocities = self.wp.empty_like(self.velocities)
        self.next_velocity_gradients = self.wp.empty_like(self.velocity_gradients)
        self.temporary_store = fem.TemporaryStore()

    def _apic_substep(
        self,
        dt_s: float,
        source_pose: np.ndarray,
        linear: np.ndarray,
        angular: np.ndarray,
    ) -> tuple[int, float]:
        wp = self.wp
        fem = self.fem
        from warp.examples.fem import example_apic_fluid as official
        import warp.examples.fem.utils as fem_example_utils
        from warp.sparse import bsr_mm, bsr_mv, bsr_transposed

        fem.set_default_temporary_store(self.temporary_store)
        try:
            volume = wp.Volume.allocate_by_voxels(
                voxel_points=self.positions,
                voxel_size=self.voxel_size_m,
            )
            grid = fem.Nanogrid(volume)
            linear_basis = fem.make_polynomial_basis_space(grid, degree=1)
            velocity_space = fem.make_collocated_function_space(linear_basis, dtype=wp.vec3)
            fraction_space = fem.make_collocated_function_space(linear_basis, dtype=float)
            pressure_space = fem.make_polynomial_space(
                grid, dtype=float, degree=0, discontinuous=True
            )
            pressure_field = pressure_space.make_field()
            velocity_field = velocity_space.make_field()
            domain = fem.Cells(grid)
            velocity_test = fem.make_test(velocity_space, domain=domain)
            velocity_trial = fem.make_trial(velocity_space, domain=domain)
            fraction_test = fem.make_test(fraction_space, domain=domain)
            pressure_test = fem.make_test(pressure_space, domain=domain)
            # The official example's half-ball boundary is inactive for this
            # meter-scale scene, yielding a zero projector.  LabUtopia's exact
            # wrapper-box boundary is projected after advection below.
            velocity_projector = fem.integrate(
                official.velocity_boundary_projector_form,
                fields={"u": velocity_trial, "v": velocity_test},
                assembly="nodal",
                output_dtype=float,
            )
            fem.normalize_dirichlet_projector(velocity_projector)
            pic = fem.PicQuadrature(
                domain=domain,
                positions=self.positions,
                measures=self.particle_volumes,
            )
            inverse_volume = fem.integrate(
                official.integrate_fraction,
                quadrature=pic,
                fields={"phi": fraction_test},
                output_dtype=float,
            )
            wp.launch(
                official.invert_volume_kernel,
                dim=inverse_volume.shape,
                inputs=[inverse_volume],
                device=self.device,
            )
            velocity_integral = fem.integrate(
                official.integrate_velocity,
                quadrature=pic,
                fields={"u": velocity_test},
                values={
                    "velocities": self.velocities,
                    "velocity_gradients": self.velocity_gradients,
                    "dt": dt_s,
                    "gravity": wp.vec3(0.0, 0.0, -9.81),
                },
                output_dtype=wp.vec3,
            )
            wp.launch(
                official.scalar_vector_multiply,
                dim=inverse_volume.shape[0],
                inputs=[inverse_volume, velocity_integral, velocity_field.dof_values],
                device=self.device,
            )
            bsr_mv(
                A=velocity_projector,
                x=velocity_field.dof_values,
                y=velocity_field.dof_values,
                alpha=-1.0,
                beta=1.0,
            )
            divergence = fem.integrate(
                official.divergence_form,
                quadrature=pic,
                fields={"u": velocity_trial, "psi": pressure_test},
                output_dtype=float,
            )
            rhs = wp.empty_like(pressure_field.dof_values)
            bsr_mv(A=divergence, x=velocity_field.dof_values, y=rhs, alpha=-1.0)
            bsr_mm(
                alpha=-1.0,
                x=divergence,
                y=velocity_projector,
                z=divergence,
                beta=1.0,
            )
            transposed = bsr_transposed(divergence)
            wp.launch(
                official.scale_transposed_divergence_mat,
                dim=inverse_volume.shape[0],
                inputs=[transposed.offsets, transposed.values, inverse_volume],
                device=self.device,
            )
            schur = bsr_mm(divergence, transposed)
            residual, iterations = fem_example_utils.bsr_cg(
                schur,
                b=rhs,
                x=pressure_field.dof_values,
                quiet=True,
                tol=self.tolerance,
                method="cr",
                max_iters=self.maximum_iterations,
            )
            bsr_mv(
                A=transposed,
                x=pressure_field.dof_values,
                y=velocity_field.dof_values,
                alpha=1.0,
                beta=1.0,
            )
            fem.interpolate(
                official.update_particles,
                at=pic,
                values={
                    "pos": self.next_positions,
                    "pos_prev": self.positions,
                    "vel": self.next_velocities,
                    "vel_grad": self.next_velocity_gradients,
                    "dt": dt_s,
                },
                fields={"grid_vel": velocity_field},
            )
            self.positions, self.next_positions = self.next_positions, self.positions
            self.velocities, self.next_velocities = self.next_velocities, self.velocities
            self.velocity_gradients, self.next_velocity_gradients = (
                self.next_velocity_gradients,
                self.velocity_gradients,
            )
            self._collide(source_pose, linear, angular)
            return int(iterations), float(residual)
        finally:
            fem.set_default_temporary_store(None)

    def logical_step(
        self, source_pose_xyzw: np.ndarray, next_source_pose_xyzw: np.ndarray
    ) -> StepDiagnostics:
        maximum_speed = self._maximum_speed()
        cfl = adaptive_cfl_step(
            maximum_speed_m_s=maximum_speed,
            support_radius_m=self.voxel_size_m,
            cfl=self.cfl,
            minimum_dt_s=self.minimum_dt_s,
            maximum_dt_s=self.maximum_dt_s,
        )
        substeps = int(cfl["substeps"])
        dt_s = float(cfl["dt_s"])
        linear, angular = _source_velocity(
            source_pose_xyzw, next_source_pose_xyzw, substeps * dt_s
        )
        actual_iterations = []
        final_residuals = []
        started = time.perf_counter()
        for substep in range(substeps):
            pose = interpolate_pose_xyzw(
                source_pose_xyzw,
                next_source_pose_xyzw,
                (substep + 1) / substeps,
            )
            iterations, residual = self._apic_substep(dt_s, pose, linear, angular)
            actual_iterations.append(iterations)
            final_residuals.append(residual)
        self.wp.synchronize_device(self.device)
        return StepDiagnostics(
            substeps=substeps,
            dt_s=dt_s,
            maximum_speed_m_s=maximum_speed,
            actual_iterations=actual_iterations,
            final_residuals=final_residuals,
            timings_ms={"physics_ms": (time.perf_counter() - started) * 1000.0},
        )


class NewtonNativeParticleAdapter:
    """Newton XPBD/VBD/SemiImplicit candidate lane using native contacts."""

    def __init__(
        self,
        *,
        solver_id: str,
        initial_positions: np.ndarray,
        particle_radius_m: float,
        particle_mass_kg: float,
        source_box_poses_xyzw: np.ndarray,
        source_box_half_extents: np.ndarray,
        target_box_poses_xyzw: np.ndarray,
        target_box_half_extents: np.ndarray,
        table_top_z_m: float,
        initial_source_pose_xyzw: np.ndarray,
        parameters: Mapping[str, Any],
        device: str = "cuda:0",
    ) -> None:
        import newton
        import warp as wp

        if solver_id not in {
            "newton_xpbd_cohesion",
            "newton_vbd_self_contact",
            "newton_semiimplicit_particles",
        }:
            raise ValueError(f"native_particle_solver_invalid:{solver_id}")
        positions = np.asarray(initial_positions, dtype=np.float32)
        self.wp = wp
        self.newton = newton
        self.device = wp.get_device(device)
        self.solver_id = solver_id
        self.particle_count = int(len(positions))
        self.particle_radius_m = float(particle_radius_m)
        builder = newton.ModelBuilder(up_axis=newton.Axis.Z)
        self.source_body = builder.add_body(
            xform=_wp_transform(wp, initial_source_pose_xyzw),
            mass=0.0,
            label="kinematic_source_beaker",
            is_kinematic=True,
        )
        cfg = newton.ModelBuilder.ShapeConfig(
            density=0.0,
            mu=float(parameters.get("collider_friction", 0.05)),
            margin=float(parameters.get("collider_margin_m", 0.0005)),
        )
        for index, (pose, extent) in enumerate(
            zip(source_box_poses_xyzw, source_box_half_extents, strict=True)
        ):
            builder.add_shape_box(
                body=self.source_body,
                xform=_wp_transform(wp, pose),
                hx=float(extent[0]),
                hy=float(extent[1]),
                hz=float(extent[2]),
                cfg=cfg,
                label=f"source_wrapper_{index:03d}",
            )
        for index, (pose, extent) in enumerate(
            zip(target_box_poses_xyzw, target_box_half_extents, strict=True)
        ):
            builder.add_shape_box(
                body=-1,
                xform=_wp_transform(wp, pose),
                hx=float(extent[0]),
                hy=float(extent[1]),
                hz=float(extent[2]),
                cfg=cfg,
                label=f"target_wrapper_{index:03d}",
            )
        table_half_thickness = 2.0
        builder.add_shape_box(
            body=-1,
            xform=wp.transform(
                wp.vec3(0.0, 0.0, table_top_z_m - table_half_thickness),
                wp.quat_identity(),
            ),
            hx=2.0,
            hy=2.0,
            hz=table_half_thickness,
            cfg=cfg,
            label="table_halfspace_proxy",
        )
        builder.add_particles(
            pos=positions.tolist(),
            vel=np.zeros_like(positions).tolist(),
            mass=[float(particle_mass_kg)] * self.particle_count,
            radius=[self.particle_radius_m] * self.particle_count,
        )
        if solver_id == "newton_vbd_self_contact":
            builder.color()
        self.model = builder.finalize(device=self.device)
        self.model.set_gravity((0.0, 0.0, -9.81))
        self.model.particle_mu = float(parameters.get("particle_friction", 0.02))
        self.model.particle_cohesion = float(parameters.get("cohesion", 0.002))
        self.model.particle_adhesion = float(parameters.get("adhesion", 0.0))
        iterations = int(parameters.get("iterations", 4))
        if solver_id == "newton_xpbd_cohesion":
            self.solver = newton.solvers.SolverXPBD(self.model, iterations=iterations)
        elif solver_id == "newton_vbd_self_contact":
            self.solver = newton.solvers.SolverVBD(
                self.model,
                iterations=iterations,
                particle_enable_self_contact=True,
                particle_self_contact_radius=self.particle_radius_m,
                particle_self_contact_margin=self.particle_radius_m * 1.5,
            )
        else:
            self.solver = newton.solvers.SolverSemiImplicit(self.model)
        self.state_0 = self.model.state()
        self.state_1 = self.model.state()
        self.contacts = self.model.contacts()
        self.control = self.model.control()
        self.maximum_value = wp.zeros(1, dtype=wp.float32, device=self.device)
        self.maximum_speed_kernel = _warp_kernels(wp)["maximum_speed"]
        self.set_source_pose_kernel = _warp_kernels(wp)["set_kinematic_body_pose"]
        self.maximum_dt_s = float(parameters.get("maximum_dt_s", 1.0 / 120.0))
        self.minimum_dt_s = float(parameters.get("minimum_dt_s", 1.0 / 3840.0))
        self.cfl = float(parameters.get("cfl", 0.4))

    def _set_source_pose(self, pose_xyzw: np.ndarray, linear: np.ndarray, angular: np.ndarray) -> None:
        self.wp.launch(
            self.set_source_pose_kernel,
            dim=1,
            inputs=(
                self.state_0.body_q,
                self.state_0.body_qd,
                self.source_body,
                _wp_transform(self.wp, pose_xyzw),
                self.wp.vec3(angular),
                self.wp.vec3(linear),
            ),
            device=self.device,
        )

    def _maximum_speed(self) -> float:
        self.maximum_value.zero_()
        self.wp.launch(
            self.maximum_speed_kernel,
            dim=self.particle_count,
            inputs=(self.state_0.particle_qd, self.maximum_value),
            device=self.device,
        )
        return float(self.maximum_value.numpy()[0])

    def logical_step(self, source_pose_xyzw: np.ndarray, next_source_pose_xyzw: np.ndarray) -> StepDiagnostics:
        maximum_speed = self._maximum_speed()
        cfl = adaptive_cfl_step(
            maximum_speed_m_s=maximum_speed,
            support_radius_m=self.particle_radius_m * 2.0,
            cfl=self.cfl,
            minimum_dt_s=self.minimum_dt_s,
            maximum_dt_s=self.maximum_dt_s,
        )
        substeps = int(cfl["substeps"])
        dt_s = float(cfl["dt_s"])
        linear, angular = _source_velocity(source_pose_xyzw, next_source_pose_xyzw, substeps * dt_s)
        started = time.perf_counter()
        for substep in range(substeps):
            pose = interpolate_pose_xyzw(source_pose_xyzw, next_source_pose_xyzw, (substep + 1) / substeps)
            self._set_source_pose(pose, linear, angular)
            self.model.collide(self.state_0, self.contacts)
            self.solver.step(self.state_0, self.state_1, self.control, self.contacts, dt_s)
            self.state_0, self.state_1 = self.state_1, self.state_0
        self.wp.synchronize_device(self.device)
        return StepDiagnostics(
            substeps=substeps,
            dt_s=dt_s,
            maximum_speed_m_s=maximum_speed,
            timings_ms={"physics_ms": (time.perf_counter() - started) * 1000.0},
        )

    def particle_positions(self) -> Any:
        return self.state_0.particle_q

    def close(self) -> None:
        return None


def create_solver_adapter(**kwargs: Any) -> FluidSolverAdapter:
    solver_id = str(kwargs.get("solver_id"))
    solver_spec(solver_id)
    if solver_id in {
        "labutopia_wcsph",
        "warp_example_sph",
        "splishsplash_pbf_port",
    }:
        selected = dict(kwargs)
        selected.pop("initial_source_pose_xyzw", None)
        return WarpHashFluidAdapter(**selected)
    if solver_id == "warp_example_apic":
        selected = dict(kwargs)
        selected.pop("initial_source_pose_xyzw", None)
        return WarpApicFluidAdapter(**selected)
    if solver_id in {"labutopia_dfsph", "splishsplash_dfsph_port"}:
        selected = dict(kwargs)
        selected.pop("initial_source_pose_xyzw", None)
        return WarpDfsphFluidAdapter(**selected)
    if solver_id in {
        "newton_xpbd_cohesion",
        "newton_semiimplicit_particles",
    }:
        return NewtonNativeParticleAdapter(**kwargs)
    if solver_id == "newton_vbd_self_contact":
        raise SolverCapabilityError(
            "newton_vbd_requires_triangle_tet_or_elastic_particle_energy_topology;"
            "the_labutopia_liquid_is_an_unconnected_point_cloud;"
            "self_contact_alone_is_not_a_liquid_incompressibility_model"
        )
    if solver_id == "newton_implicit_mpm":
        raise SolverCapabilityError(
            "newton_implicit_mpm_uses_run_newton140_mpm_benchmark_subprocess_adapter"
        )
    raise AssertionError(f"unhandled_solver:{solver_id}")
