#!/usr/bin/env python3
"""GPU particle-to-surface reconstruction using Warp 1.15 marching cubes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


@dataclass(frozen=True)
class WarpSurface:
    vertices: Any
    indices: Any
    field: Any
    timing_ms: dict[str, float]
    bounds_lower_m: tuple[float, float, float]
    bounds_upper_m: tuple[float, float, float]
    grid_shape: tuple[int, int, int]
    threshold: float


_DENSITY_KERNEL: Any | None = None


def _density_kernel(wp: Any) -> Any:
    global _DENSITY_KERNEL
    if _DENSITY_KERNEL is not None:
        return _DENSITY_KERNEL

    @wp.kernel
    def sample_particle_field(
        hash_grid: wp.uint64,
        particle_positions: wp.array(dtype=wp.vec3),
        field: wp.array3d(dtype=wp.float32),
        lower: wp.vec3,
        spacing: wp.vec3,
        support_radius: float,
    ):
        i, j, k = wp.tid()
        sample = lower + wp.cw_mul(wp.vec3(float(i), float(j), float(k)), spacing)
        support_sq = support_radius * support_radius
        density = float(0.0)
        query = wp.hash_grid_query(hash_grid, sample, support_radius)
        for particle_index in query:
            delta = sample - particle_positions[particle_index]
            distance_sq = wp.dot(delta, delta)
            if distance_sq < support_sq:
                weight = 1.0 - distance_sq / support_sq
                density = density + weight * weight * weight
        field[i, j, k] = density

    _DENSITY_KERNEL = sample_particle_field
    return _DENSITY_KERNEL


class WarpSurfaceReconstructor:
    """Reusable GPU density grid and GPU marching-cubes extractor.

    Both scalar-field construction and topology extraction stay on the selected
    Warp device. Readback is optional and belongs to the caller's evidence lane.
    """

    def __init__(
        self,
        *,
        bounds_lower_m: Sequence[float],
        bounds_upper_m: Sequence[float],
        voxel_size_m: float = 0.006,
        support_radius_m: float = 0.012,
        threshold: float = 0.45,
        device: str = "cuda:0",
    ) -> None:
        import warp as wp

        lower = np.asarray(bounds_lower_m, dtype=np.float32)
        upper = np.asarray(bounds_upper_m, dtype=np.float32)
        if lower.shape != (3,) or upper.shape != (3,) or not np.isfinite([lower, upper]).all():
            raise ValueError("surface_bounds_invalid")
        if np.any(upper <= lower):
            raise ValueError("surface_bounds_not_increasing")
        if voxel_size_m <= 0.0 or support_radius_m <= 0.0 or threshold <= 0.0:
            raise ValueError("surface_parameters_invalid")
        shape = tuple(int(np.ceil((upper[axis] - lower[axis]) / voxel_size_m)) + 1 for axis in range(3))
        if any(dimension < 2 or dimension > 384 for dimension in shape):
            raise ValueError(f"surface_grid_shape_invalid:{shape}")
        spacing = (upper - lower) / (np.asarray(shape, dtype=np.float32) - 1.0)
        self.wp = wp
        self.device = wp.get_device(device)
        self.lower = lower
        self.upper = upper
        self.spacing = spacing
        self.shape = shape
        self.voxel_size_m = float(voxel_size_m)
        self.support_radius_m = float(support_radius_m)
        self.threshold = float(threshold)
        self.field = wp.zeros(shape, dtype=wp.float32, device=self.device)
        grid_dims = tuple(max(1, int(np.ceil((upper[i] - lower[i]) / support_radius_m))) for i in range(3))
        self.hash_grid = wp.HashGrid(*grid_dims, device=self.device)

    def reconstruct(self, particle_positions: Any) -> WarpSurface:
        wp = self.wp
        if isinstance(particle_positions, np.ndarray):
            values = np.asarray(particle_positions, dtype=np.float32)
            if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
                raise ValueError("surface_particle_positions_invalid")
            particles = wp.array(values, dtype=wp.vec3, device=self.device)
        else:
            particles = particle_positions
            if particles.dtype != wp.vec3 or len(particles.shape) != 1:
                raise ValueError("surface_particle_array_invalid")
            if particles.device != self.device:
                particles = particles.to(self.device)

        build_start = time.perf_counter()
        self.hash_grid.build(particles, self.support_radius_m)
        wp.launch(
            _density_kernel(wp),
            dim=self.shape,
            inputs=(
                self.hash_grid.id,
                particles,
                self.field,
                wp.vec3(self.lower),
                wp.vec3(self.spacing),
                self.support_radius_m,
            ),
            device=self.device,
        )
        wp.synchronize_device(self.device)
        field_ms = (time.perf_counter() - build_start) * 1000.0

        marching_start = time.perf_counter()
        vertices, indices = wp.MarchingCubes.extract_surface_marching_cubes(
            self.field,
            self.threshold,
            domain_bounds_lower_corner=wp.vec3(self.lower),
            domain_bounds_upper_corner=wp.vec3(self.upper),
        )
        wp.synchronize_device(self.device)
        marching_ms = (time.perf_counter() - marching_start) * 1000.0
        return WarpSurface(
            vertices=vertices,
            indices=indices,
            field=self.field,
            timing_ms={
                "field_ms": field_ms,
                "marching_cubes_ms": marching_ms,
                "total_ms": field_ms + marching_ms,
            },
            bounds_lower_m=tuple(float(value) for value in self.lower),
            bounds_upper_m=tuple(float(value) for value in self.upper),
            grid_shape=self.shape,
            threshold=self.threshold,
        )
