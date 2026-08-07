#!/usr/bin/env python3
"""Run the LabUtopia pour trace with Newton's implicit MPM solver.

This entry point is intentionally USD-free.  It consumes the immutable scene
packet produced by ``build_fluid_benchmark_packet.py`` and can optionally
publish particle frames to an Isaac Sim renderer through shared memory.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_benchmark_bridge import (  # noqa: E402
    BRIDGE_SCHEMA,
    SharedFluidFrame,
    receive_message,
    send_message,
)
from tools.labutopia_fluid.fluid_benchmark_contract import (  # noqa: E402
    EXPECTED_OBSERVATION_COUNT,
    INTEGRATION_DT_S,
    LOGICAL_DT_S,
    RESULT_SCHEMA,
    SUBSTEPS_PER_OBSERVATION,
    NEWTON_POUR_RETARGET_BLEND,
    NEWTON_POUR_RETARGET_OFFSET_M,
    canonical_json_sha256,
    classify_positions,
    evaluate_quality_gate,
    interpolate_pose_xyzw,
    load_packet,
    row_transform_points,
    retarget_source_poses,
    sha256_file,
    summarize_milliseconds,
)


DEFAULT_PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)
EXPERIMENTAL_ENV = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-newton140-mpm-py312"
)
REVIEW_FRAME_INDICES = frozenset({0, 300, 450, 580, 650, 750, 852, 952})

PROFILES: dict[str, dict[str, Any]] = {
    "sparse_q1_gs_fast": {
        "grid_type": "sparse",
        "grid_padding": 0,
        "voxel_size": 0.012,
        "max_iterations": 12,
        "tolerance": 5.0e-4,
        "solver": "gs",
        "strain_basis": "P0",
        "velocity_basis": "Q1",
        "collider_basis": "S2",
        "collider_velocity_mode": "backward",
        "transfer_scheme": "apic",
        "warmstart_mode": "auto",
        "project_outside": True,
        "viscosity": 8.0,
        "graph": False,
    },
    "sparse_q1_gs_balanced": {
        "grid_type": "sparse",
        "grid_padding": 0,
        "voxel_size": 0.010,
        "max_iterations": 24,
        "tolerance": 1.0e-5,
        "solver": "gs",
        "strain_basis": "P0",
        "velocity_basis": "Q1",
        "collider_basis": "S2",
        "collider_velocity_mode": "backward",
        "transfer_scheme": "apic",
        "warmstart_mode": "auto",
        "project_outside": True,
        "viscosity": 20.0,
        "graph": False,
    },
    "sparse_q1_cg_fast": {
        "grid_type": "sparse",
        "grid_padding": 0,
        "voxel_size": 0.012,
        "max_iterations": 12,
        "tolerance": 5.0e-4,
        "solver": "cg",
        "strain_basis": "P0",
        "velocity_basis": "Q1",
        "collider_basis": "S2",
        "collider_velocity_mode": "backward",
        "transfer_scheme": "apic",
        "warmstart_mode": "auto",
        "project_outside": True,
        "viscosity": 8.0,
        "graph": False,
    },
    "sparse_q1_jacobi_fast": {
        "grid_type": "sparse",
        "grid_padding": 0,
        "voxel_size": 0.012,
        "max_iterations": 12,
        "tolerance": 5.0e-4,
        "solver": "jacobi",
        "strain_basis": "P0",
        "velocity_basis": "Q1",
        "collider_basis": "S2",
        "collider_velocity_mode": "backward",
        "transfer_scheme": "apic",
        "warmstart_mode": "auto",
        "project_outside": True,
        "viscosity": 8.0,
        "graph": False,
    },
    "fixed_q1_gs_graph": {
        "grid_type": "fixed",
        "grid_padding": 40,
        "voxel_size": 0.012,
        "max_iterations": 12,
        "tolerance": 5.0e-4,
        "solver": "gs",
        "strain_basis": "P0",
        "velocity_basis": "Q1",
        "collider_basis": "S2",
        "collider_velocity_mode": "backward",
        "transfer_scheme": "apic",
        "warmstart_mode": "none",
        "project_outside": True,
        "viscosity": 8.0,
        "graph": True,
    },
}

SOLVER_DIAGNOSTIC_PATTERN = re.compile(
    r"(?P<solver>.+?) terminated after (?P<iteration>\d+) iterations with "
    r"residuals (?P<l2>[-+0-9.eE]+), (?P<linf>[-+0-9.eE]+)"
)


def _pose_matrix_xyzw(pose: np.ndarray) -> np.ndarray:
    value = np.asarray(pose, dtype=np.float64)
    if value.shape != (7,) or not np.isfinite(value).all():
        raise ValueError("pose_xyzw_invalid")
    x, y, z, qx, qy, qz, qw = value
    norm = float(np.linalg.norm(value[3:]))
    if norm <= 0.0:
        raise ValueError("pose_quaternion_zero")
    qx, qy, qz, qw = (value[3:] / norm).tolist()
    column_rotation = np.asarray(
        [
            [
                1.0 - 2.0 * (qy * qy + qz * qz),
                2.0 * (qx * qy - qz * qw),
                2.0 * (qx * qz + qy * qw),
            ],
            [
                2.0 * (qx * qy + qz * qw),
                1.0 - 2.0 * (qx * qx + qz * qz),
                2.0 * (qy * qz - qx * qw),
            ],
            [
                2.0 * (qx * qz - qy * qw),
                2.0 * (qy * qz + qx * qw),
                1.0 - 2.0 * (qx * qx + qy * qy),
            ],
        ],
        dtype=np.float64,
    )
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = column_rotation.T
    result[3, :3] = (x, y, z)
    return result


def _warp_transform(wp: Any, pose: np.ndarray) -> Any:
    value = np.asarray(pose, dtype=np.float64)
    return wp.transform(
        wp.vec3(*(float(component) for component in value[:3])),
        wp.quat(*(float(component) for component in value[3:])),
    )


def _make_table_halfspace_kernel(wp: Any) -> Any:
    @wp.kernel
    def enforce_table_halfspace(
        positions: wp.array(dtype=wp.vec3),
        velocities: wp.array(dtype=wp.vec3),
        minimum_z: float,
        corrected: wp.array(dtype=wp.int32),
    ):
        index = wp.tid()
        position = positions[index]
        if position[2] < minimum_z:
            positions[index] = wp.vec3(position[0], position[1], minimum_z)
            velocity = velocities[index]
            velocities[index] = wp.vec3(
                velocity[0],
                velocity[1],
                wp.max(velocity[2], 0.0),
            )
            corrected[index] = 1

    return enforce_table_halfspace


def _make_source_pose_kernels(wp: Any) -> tuple[Any, Any]:
    @wp.kernel
    def set_pose_cursor(cursor: wp.array(dtype=wp.int32), value: int):
        if wp.tid() == 0:
            cursor[0] = value

    @wp.kernel
    def set_kinematic_source_pose(
        body_q: wp.array(dtype=wp.transform),
        body_qd: wp.array(dtype=wp.spatial_vector),
        poses: wp.array(dtype=wp.transform),
        cursor: wp.array(dtype=wp.int32),
        body_index: int,
    ):
        pose_index = cursor[0]
        body_q[body_index] = poses[pose_index]
        body_qd[body_index] = wp.spatial_vector(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        cursor[0] = pose_index + 1

    return set_pose_cursor, set_kinematic_source_pose


def precompute_substep_poses(
    source_poses: np.ndarray,
    *,
    observation_count: int,
    substeps: int,
) -> np.ndarray:
    """Build the exact per-substep SLERP trace consumed by the GPU kernel."""
    poses = np.asarray(source_poses, dtype=np.float64)
    if poses.ndim != 2 or poses.shape[1] != 7 or not np.isfinite(poses).all():
        raise ValueError("source_pose_trace_invalid")
    if observation_count <= 0 or observation_count > poses.shape[0]:
        raise ValueError("source_pose_observation_count_invalid")
    if substeps <= 0:
        raise ValueError("source_pose_substeps_invalid")
    result = np.empty((observation_count * substeps, 7), dtype=np.float32)
    for observation_index in range(observation_count):
        previous_index = max(0, observation_index - 1)
        for substep_index in range(substeps):
            alpha = float(substep_index + 1) / float(substeps)
            result[observation_index * substeps + substep_index] = (
                interpolate_pose_xyzw(
                    poses[previous_index],
                    poses[observation_index],
                    alpha,
                )
            )
    return result


def parse_solver_diagnostics(text: str) -> dict[str, Any]:
    records = []
    for match in SOLVER_DIAGNOSTIC_PATTERN.finditer(text):
        # Newton initializes its CUDA loop counter to one, while each loop body
        # performs five actual nonlinear iterations.  Report both values.
        reported_iteration = int(match.group("iteration"))
        actual_iteration = max(0, reported_iteration - 1)
        records.append(
            {
                "solver": match.group("solver").strip(),
                "reported_iteration_counter": reported_iteration,
                "actual_iterations": actual_iteration,
                "residual_l2": float(match.group("l2")),
                "residual_linf": float(match.group("linf")),
            }
        )
    histogram: dict[str, int] = {}
    for record in records:
        key = str(record["actual_iterations"])
        histogram[key] = histogram.get(key, 0) + 1
    return {
        "record_count": len(records),
        "actual_iteration_histogram": histogram,
        "maximum_actual_iterations": (
            max(record["actual_iterations"] for record in records)
            if records
            else None
        ),
        "final_residual_l2": records[-1]["residual_l2"] if records else None,
        "final_residual_linf": records[-1]["residual_linf"] if records else None,
        "records": records,
    }


def _regular_cylinder_positions(
    *,
    particle_count: int,
    points_per_layer: int,
    radius_m: float,
    floor_m: float,
    fill_height_m: float,
    frame_world_matrix: np.ndarray,
    jitter_fraction: float,
) -> np.ndarray:
    if particle_count % points_per_layer != 0:
        raise ValueError("regular_cylinder_particle_factorization_invalid")
    layer_count = particle_count // points_per_layer
    if layer_count < 2 or points_per_layer < 2:
        raise ValueError("regular_cylinder_resolution_invalid")
    disk_area_per_point = np.pi * radius_m**2 / points_per_layer
    spacing = float(np.sqrt(disk_area_per_point))
    lattice_range = int(np.ceil(2.0 * radius_m / spacing)) + 3
    candidates = []
    for row in range(-lattice_range, lattice_range + 1):
        y = row * spacing
        for column in range(-lattice_range, lattice_range + 1):
            x = column * spacing
            candidates.append((x * x + y * y, x, y))
    candidates.sort(key=lambda item: (item[0], item[2], item[1]))
    disk = np.asarray(
        [[item[1], item[2]] for item in candidates[:points_per_layer]],
        dtype=np.float64,
    )
    maximum_radius = float(np.hypot(disk[:, 0], disk[:, 1]).max())
    radial_margin = 0.55 * spacing
    disk *= max(0.0, radius_m - radial_margin) / maximum_radius
    z_values = np.linspace(
        floor_m + 0.5 * fill_height_m / layer_count,
        floor_m + fill_height_m - 0.5 * fill_height_m / layer_count,
        layer_count,
        dtype=np.float64,
    )
    local_layers = []
    for z_value in z_values:
        local_layers.append(
            np.column_stack(
                [disk, np.full(points_per_layer, z_value, dtype=np.float64)]
            )
        )
    local = np.concatenate(local_layers, axis=0)
    if jitter_fraction:
        if jitter_fraction < 0.0 or jitter_fraction > 0.25:
            raise ValueError("regular_cylinder_jitter_fraction_invalid")
        rng = np.random.default_rng(20260731)
        local += (
            rng.uniform(-1.0, 1.0, size=local.shape)
            * spacing
            * float(jitter_fraction)
        )
    world = row_transform_points(local, frame_world_matrix)
    if world.shape != (particle_count, 3) or not np.isfinite(world).all():
        raise ValueError("regular_cylinder_positions_invalid")
    return world.astype(np.float32)


def _resample_authored_particles(
    positions: np.ndarray,
    particle_count: int,
    *,
    base_radius_m: float,
) -> np.ndarray:
    authored = np.asarray(positions, dtype=np.float32)
    if authored.shape != (3600, 3):
        raise ValueError("authored_particle_shape_invalid")
    if particle_count not in {900, 1800, 3600, 7200}:
        raise ValueError("particle_count_not_in_benchmark_resolution_set")
    if particle_count <= 3600:
        result = authored[np.linspace(0, 3599, particle_count, dtype=np.int64)].copy()
    else:
        result = np.repeat(authored, 2, axis=0)
        sequence = np.arange(len(result), dtype=np.float32)
        direction = np.stack(
            [
                np.sin(sequence * 12.9898),
                np.sin(sequence * 78.233 + 0.7),
                np.sin(sequence * 37.719 + 1.4),
            ],
            axis=1,
        )
        direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1.0e-6)
        signs = np.where((np.arange(len(result)) % 2)[:, None] == 0, -1.0, 1.0)
        result += signs * direction * float(base_radius_m) * 0.2
    if result.shape != (particle_count, 3) or not np.isfinite(result).all():
        raise RuntimeError("resampled_particles_invalid")
    return result.astype(np.float32)


def _regular_box_positions(
    *,
    radius_m: float,
    floor_m: float,
    fill_height_m: float,
    frame_world_matrix: np.ndarray,
    radial_margin_m: float,
) -> tuple[np.ndarray, float]:
    dimensions = (12, 12, 25)
    radial_margin = max(0.0015, radial_margin_m)
    half_side = (radius_m - radial_margin) / np.sqrt(2.0)
    x_values = np.linspace(-half_side, half_side, dimensions[0])
    y_values = np.linspace(-half_side, half_side, dimensions[1])
    z_spacing = fill_height_m / dimensions[2]
    z_values = np.linspace(
        floor_m + 0.5 * z_spacing,
        floor_m + fill_height_m - 0.5 * z_spacing,
        dimensions[2],
    )
    local = np.stack(
        np.meshgrid(x_values, y_values, z_values, indexing="ij"),
        axis=-1,
    ).reshape((-1, 3))
    if local.shape != (3600, 3):
        raise ValueError("regular_box_particle_count_invalid")
    spacing_x = float(x_values[1] - x_values[0])
    spacing_y = float(y_values[1] - y_values[0])
    cell_volume = spacing_x * spacing_y * float(z_spacing)
    world = row_transform_points(local, frame_world_matrix)
    return world.astype(np.float32), cell_volume


def _cup_mesh_vertices_indices(
    *,
    interior_radius_m: float,
    rim_m: float,
    wall_thickness_m: float,
    bottom_thickness_m: float,
    segments: int,
) -> tuple[np.ndarray, np.ndarray]:
    if segments < 16:
        raise ValueError("cup_mesh_segments_too_small")
    theta = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    cosine = np.cos(theta)
    sine = np.sin(theta)

    def ring(radius: float, z: float) -> np.ndarray:
        return np.column_stack(
            [radius * cosine, radius * sine, np.full(segments, z)]
        )

    outer_radius = interior_radius_m + wall_thickness_m
    vertices = np.vstack(
        [
            ring(interior_radius_m, 0.0),
            ring(interior_radius_m, rim_m),
            ring(outer_radius, rim_m),
            ring(outer_radius, -bottom_thickness_m),
            np.asarray([[0.0, 0.0, 0.0]]),
            np.asarray([[0.0, 0.0, -bottom_thickness_m]]),
        ]
    ).astype(np.float32)
    inner_center = 4 * segments
    outer_center = inner_center + 1
    indices: list[int] = []
    for index in range(segments):
        next_index = (index + 1) % segments
        inner_bottom_i, inner_bottom_j = index, next_index
        inner_top_i, inner_top_j = index + segments, next_index + segments
        outer_top_i, outer_top_j = index + 2 * segments, next_index + 2 * segments
        outer_bottom_i, outer_bottom_j = (
            index + 3 * segments,
            next_index + 3 * segments,
        )
        indices.extend(
            [inner_bottom_i, inner_top_i, inner_bottom_j]
        )
        indices.extend(
            [inner_bottom_j, inner_top_i, inner_top_j]
        )
        indices.extend([outer_bottom_i, outer_bottom_j, outer_top_i])
        indices.extend([outer_top_i, outer_bottom_j, outer_top_j])
        indices.extend([inner_top_i, outer_top_i, inner_top_j])
        indices.extend([inner_top_j, outer_top_i, outer_top_j])
        indices.extend([inner_center, inner_bottom_i, inner_bottom_j])
        indices.extend([outer_center, outer_bottom_j, outer_bottom_i])
    return vertices, np.asarray(indices, dtype=np.int32)


def _git_identity() -> dict[str, Any]:
    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed.stdout.strip()

    try:
        revision = run("rev-parse", "HEAD")
        status = run("status", "--short")
    except (OSError, subprocess.CalledProcessError) as error:
        return {"error": f"{type(error).__name__}:{error}"}
    return {
        "revision": revision,
        "dirty": bool(status),
        "status_sha256": canonical_json_sha256(status),
    }


def _environment_identity(wp: Any, newton: Any, device: Any) -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    environment_keys = (
        "CUDA_VISIBLE_DEVICES",
        "LD_LIBRARY_PATH",
        "PATH",
        "PYTHONNOUSERSITE",
    )
    selected_environment = {
        key: os.environ[key] for key in environment_keys if key in os.environ
    }
    return {
        "claim_boundary": (
            "experimental_lane_not_formal_isaac41_evidence_and_not_cross_runtime_"
            "performance_comparable_until_matrix_controls_pass"
        ),
        "executable": str(executable),
        "prefix": str(Path(sys.prefix).resolve()),
        "expected_prefix": str(EXPERIMENTAL_ENV),
        "prefix_matches_expected": Path(sys.prefix).resolve() == EXPERIMENTAL_ENV,
        "python": platform.python_version(),
        "newton": str(getattr(newton, "__version__", "unknown")),
        "warp": str(getattr(wp, "__version__", "unknown")),
        "device": str(device),
        "device_is_cuda": bool(device.is_cuda),
        "platform": platform.platform(),
        "selected_environment": selected_environment,
        "selected_environment_sha256": canonical_json_sha256(selected_environment),
        "source": _git_identity(),
    }


def _runtime_identity(
    wp: Any,
    newton: Any,
    device: Any,
    runtime_receipt: Path | None,
) -> dict[str, Any]:
    identity = _environment_identity(wp, newton, device)
    if runtime_receipt is None:
        return {**identity, "attested_experimental_runtime": False}
    receipt_path = runtime_receipt.resolve(strict=True)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("schema") != "labutopia.newton_only_runtime_attestation.v1"
        or receipt.get("status") != "matched_experimental_runtime"
        or Path(receipt.get("executable", "")).resolve(strict=True)
        != Path(sys.executable).resolve(strict=True)
        or Path(receipt.get("prefix", "")).resolve(strict=True)
        != Path(sys.prefix).resolve(strict=True)
    ):
        raise RuntimeError("newton_runtime_receipt_mismatch")
    return {
        **identity,
        "claim_boundary": receipt["claim_boundary"],
        "attested_experimental_runtime": True,
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_content_sha256": receipt["content_sha256"],
    }


def _connect_bridge(socket_path: Path, timeout_s: float) -> socket.socket:
    deadline = time.monotonic() + timeout_s
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.connect(str(socket_path))
            connection.settimeout(timeout_s)
            return connection
        except OSError as error:
            last_error = error
            connection.close()
            time.sleep(0.05)
    raise TimeoutError(f"bridge_connect_timeout:{last_error}")


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _resolve_profile(args: argparse.Namespace) -> dict[str, Any]:
    profile = dict(PROFILES[args.profile])
    for name in (
        "grid_type",
        "grid_padding",
        "voxel_size",
        "max_iterations",
        "tolerance",
        "solver",
        "strain_basis",
        "velocity_basis",
        "collider_basis",
        "collider_velocity_mode",
        "transfer_scheme",
        "warmstart_mode",
        "viscosity",
    ):
        override = getattr(args, name)
        if override is not None:
            profile[name] = override
    if args.graph is not None:
        profile["graph"] = args.graph
    return profile


def run(args: argparse.Namespace) -> dict[str, Any]:
    import newton
    import warp as wp
    from newton.solvers import SolverImplicitMPM

    started_wall_s = time.time()
    setup_started = time.perf_counter()
    packet = load_packet(args.packet)
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output_dir_not_empty:{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    profile = _resolve_profile(args)
    if args.timing_breakdown and bool(profile["graph"]):
        raise ValueError("timing_breakdown_incompatible_with_outer_cuda_graph")
    requested_count = (
        EXPECTED_OBSERVATION_COUNT
        if args.max_observations is None
        else args.max_observations
    )
    if requested_count <= 0 or requested_count > EXPECTED_OBSERVATION_COUNT:
        raise ValueError("max_observations_out_of_range")

    wp.init()
    device = wp.get_device(args.device)
    if not device.is_cuda and not args.allow_cpu:
        raise RuntimeError("cuda_device_required")

    authored_positions = packet.array("initial_particle_positions", (3600, 3))
    recorded_source_poses = packet.array("source_poses_xyzw", (953, 7))
    if args.trajectory_npz is not None:
        from tools.labutopia_fluid.newton_only_contract import (
            validate_reoptimized_trajectory,
        )

        trajectory_path = args.trajectory_npz.resolve(strict=True)
        with np.load(trajectory_path, allow_pickle=False) as archive:
            if tuple(archive.files) != ("source_poses_xyzw",):
                raise ValueError("trajectory_archive_fields_invalid")
            source_poses = np.asarray(archive["source_poses_xyzw"], dtype=np.float64)
        validate_reoptimized_trajectory(source_poses, recorded_source_poses)
        if args.pour_retarget:
            raise ValueError("trajectory_npz_incompatible_with_pour_retarget")
    else:
        source_poses = (
            retarget_source_poses(
                recorded_source_poses,
                offset_m=args.pour_retarget_offset_m,
                blend_observations=args.pour_retarget_blend,
            )
            if args.pour_retarget
            else recorded_source_poses
        )
    source_box_poses = packet.array(
        "source_box_poses_xyzw",
        (int(packet.manifest["source_box_count"]), 7),
    )
    source_box_extents = packet.array(
        "source_box_half_extents",
        (int(packet.manifest["source_box_count"]), 3),
    )
    target_box_poses = packet.array(
        "target_box_poses_xyzw",
        (int(packet.manifest["target_box_count"]), 7),
    )
    target_box_extents = packet.array(
        "target_box_half_extents",
        (int(packet.manifest["target_box_count"]), 3),
    )
    source_frame_local = packet.array("source_frame_local_matrix", (4, 4))
    target_frame_world = packet.array("target_frame_world_matrix", (4, 4))
    initial_source_frame_world = source_frame_local @ _pose_matrix_xyzw(
        source_poses[0]
    )
    initial_fluid_min_z = float(
        packet.manifest["fluid"]["initial_fluid_min_canonical_z_m"]
    )
    initial_fluid_max_z = float(
        packet.manifest["fluid"]["initial_fluid_max_canonical_z_m"]
    )
    regular_layout_min_z = max(
        initial_fluid_min_z,
        float(args.collider_margin) + 0.002,
    )
    regular_layout_height = initial_fluid_max_z - regular_layout_min_z
    if regular_layout_height <= 0.0:
        raise ValueError("regular_layout_height_invalid")
    layout_cell_volume: float | None = None
    if args.initial_layout == "authored":
        positions = _resample_authored_particles(
            authored_positions,
            args.particle_count,
            base_radius_m=float(packet.manifest["fluid"]["particle_radius_m"]),
        )
    elif args.initial_layout == "regular_cylinder":
        positions = _regular_cylinder_positions(
            particle_count=args.particle_count,
            points_per_layer=args.points_per_layer,
            radius_m=float(
                packet.manifest["frames"]["source"]["interior_radius_m"]
            ),
            floor_m=regular_layout_min_z,
            fill_height_m=regular_layout_height,
            frame_world_matrix=initial_source_frame_world,
            jitter_fraction=args.initial_jitter_fraction,
        )
        layout_cell_volume = (
            float(packet.manifest["fluid"]["estimated_initial_volume_m3"])
            / args.particle_count
        )
    else:
        if args.particle_count != 3600:
            raise ValueError("regular_box_layout_only_supports_3600_particles")
        positions, layout_cell_volume = _regular_box_positions(
            radius_m=float(
                packet.manifest["frames"]["source"]["interior_radius_m"]
            ),
            floor_m=regular_layout_min_z,
            fill_height_m=regular_layout_height,
            frame_world_matrix=initial_source_frame_world,
            radial_margin_m=float(args.collider_margin) + 0.002,
        )

    builder = newton.ModelBuilder(up_axis=newton.Axis.Z)
    SolverImplicitMPM.register_custom_attributes(builder)
    source_body = -1
    if not args.omit_source_body:
        source_body = builder.add_body(
            xform=_warp_transform(wp, source_poses[0]),
            mass=0.0,
            label="synthetic_kinematic_source_beaker",
            is_kinematic=True,
        )
    vessel_shape_config = newton.ModelBuilder.ShapeConfig(
        density=0.0,
        mu=float(args.collider_friction),
        margin=float(args.collider_margin),
    )
    if not args.omit_vessel_colliders and args.collider_representation == "wrapper_boxes":
        if source_body < 0 and not args.static_source_colliders:
            raise ValueError("source_body_required_for_vessel_colliders")
        for index, (pose, extent) in enumerate(
            zip(source_box_poses, source_box_extents, strict=True)
        ):
            shape_body = source_body
            shape_transform = _warp_transform(wp, pose)
            if args.static_source_colliders:
                shape_body = -1
                shape_transform = wp.transform_multiply(
                    _warp_transform(wp, source_poses[0]),
                    shape_transform,
                )
            builder.add_shape_box(
                body=shape_body,
                xform=shape_transform,
                hx=float(extent[0]),
                hy=float(extent[1]),
                hz=float(extent[2]),
                cfg=vessel_shape_config,
                label=f"source_wrapper_{index:03d}",
            )
        for index, (pose, extent) in enumerate(
            zip(target_box_poses, target_box_extents, strict=True)
        ):
            builder.add_shape_box(
                body=-1,
                xform=_warp_transform(wp, pose),
                hx=float(extent[0]),
                hy=float(extent[1]),
                hz=float(extent[2]),
                cfg=vessel_shape_config,
                label=f"target_wrapper_{index:03d}",
            )
    elif not args.omit_vessel_colliders:
        source_vertices, source_indices = _cup_mesh_vertices_indices(
            interior_radius_m=float(
                packet.manifest["frames"]["source"]["interior_radius_m"]
            ),
            rim_m=float(packet.manifest["frames"]["source"]["rim_m"]),
            wall_thickness_m=args.mesh_wall_thickness,
            bottom_thickness_m=args.mesh_bottom_thickness,
            segments=args.mesh_segments,
        )
        source_vertices_body = row_transform_points(
            source_vertices,
            source_frame_local,
        ).astype(np.float32)
        source_mesh = newton.Mesh(
            source_vertices_body,
            source_indices,
            compute_inertia=False,
            is_solid=True,
        )
        builder.add_shape_mesh(
            body=source_body,
            mesh=source_mesh,
            cfg=vessel_shape_config,
            label="source_simplified_cup_mesh",
        )
        target_vertices, target_indices = _cup_mesh_vertices_indices(
            interior_radius_m=float(
                packet.manifest["frames"]["target"]["interior_radius_m"]
            ),
            rim_m=float(packet.manifest["frames"]["target"]["rim_m"]),
            wall_thickness_m=args.mesh_wall_thickness,
            bottom_thickness_m=args.mesh_bottom_thickness,
            segments=args.mesh_segments,
        )
        target_vertices_world = row_transform_points(
            target_vertices,
            target_frame_world,
        ).astype(np.float32)
        target_mesh = newton.Mesh(
            target_vertices_world,
            target_indices,
            compute_inertia=False,
            is_solid=True,
        )
        builder.add_shape_mesh(
            body=-1,
            mesh=target_mesh,
            cfg=vessel_shape_config,
            label="target_simplified_cup_mesh",
        )
        builder.add_shape_box(
            body=-1,
            xform=_warp_transform(wp, target_box_poses[0]),
            hx=float(target_box_extents[0, 0]),
            hy=float(target_box_extents[0, 1]),
            hz=float(target_box_extents[0, 2]),
            cfg=vessel_shape_config,
            label="target_authored_wrapper_bottom_seal",
        )

    table_top_z = float(packet.manifest["frames"]["table_top_z_m"])
    table_shape_config = newton.ModelBuilder.ShapeConfig(
        density=0.0,
        mu=float(args.table_friction),
        margin=0.0,
    )
    if not args.omit_table_collider:
        table_half_thickness = 2.0
        builder.add_shape_box(
            body=-1,
            xform=wp.transform(
                wp.vec3(0.0, 0.0, table_top_z - table_half_thickness),
                wp.quat_identity(),
            ),
            hx=2.0,
            hy=2.0,
            hz=table_half_thickness,
            cfg=table_shape_config,
            label="tabletop_deep_halfspace_proxy",
        )

    fluid = packet.manifest["fluid"]
    particle_count = int(args.particle_count)
    resolution_scale = (3600.0 / particle_count) ** (1.0 / 3.0)
    particle_radius = (
        (
            float(fluid["particle_radius_m"]) * resolution_scale
            if layout_cell_volume is None
            else 0.5 * layout_cell_volume ** (1.0 / 3.0)
        )
        if args.particle_radius is None
        else float(args.particle_radius)
    )
    particle_mass = (
        (
            float(fluid["particle_mass_kg"]) * 3600.0 / particle_count
            if layout_cell_volume is None
            else layout_cell_volume * 1000.0
        )
        if args.particle_density is None
        else 8.0 * particle_radius**3 * float(args.particle_density)
    )
    builder.add_particles(
        pos=positions.astype(np.float32).tolist(),
        vel=np.zeros_like(positions, dtype=np.float32).tolist(),
        mass=[particle_mass] * particle_count,
        radius=[particle_radius] * particle_count,
    )
    model = builder.finalize(device=device)
    model.set_gravity((0.0, 0.0, -9.81))
    model.mpm.viscosity.fill_(float(profile["viscosity"]))
    model.mpm.tensile_yield_ratio.fill_(1.0)
    model.mpm.friction.fill_(float(args.particle_friction))

    options = SolverImplicitMPM.Config()
    options.grid_type = str(profile["grid_type"])
    options.grid_padding = int(profile["grid_padding"])
    options.voxel_size = float(profile["voxel_size"])
    options.max_iterations = int(profile["max_iterations"])
    options.tolerance = float(profile["tolerance"])
    options.solver = str(profile["solver"])
    options.strain_basis = str(profile["strain_basis"])
    options.velocity_basis = str(profile["velocity_basis"])
    options.collider_basis = str(profile["collider_basis"])
    options.transfer_scheme = str(profile["transfer_scheme"])
    options.warmstart_mode = str(profile["warmstart_mode"])
    options.collider_velocity_mode = str(profile["collider_velocity_mode"])
    solver = SolverImplicitMPM(
        model,
        options,
        verbose=bool(args.solver_diagnostics),
        enable_timers=bool(args.solver_diagnostics),
    )
    state_0 = model.state()
    state_1 = model.state()
    table_guard_kernel = _make_table_halfspace_kernel(wp)
    table_guard_flags = wp.zeros(particle_count, dtype=wp.int32, device=device)

    def apply_table_guard(state: Any) -> None:
        if args.table_halfspace_guard:
            wp.launch(
                table_guard_kernel,
                dim=particle_count,
                inputs=[
                    state.particle_q,
                    state.particle_qd,
                    table_top_z + particle_radius,
                    table_guard_flags,
                ],
                device=device,
            )

    compile_warmup_times_ms: list[float] = []
    if args.warmup_observations:
        for _ in range(args.warmup_observations):
            wp.synchronize_device(device)
            warmup_started = time.perf_counter()
            for _ in range(args.debug_substeps):
                solver.step(
                    state_0,
                    state_1,
                    control=None,
                    contacts=None,
                    dt=args.debug_integration_dt,
                )
                if profile["project_outside"]:
                    solver.project_outside(
                        state_1,
                        state_1,
                        args.debug_integration_dt,
                    )
                apply_table_guard(state_1)
                state_0, state_1 = state_1, state_0
            wp.synchronize_device(device)
            compile_warmup_times_ms.append(
                (time.perf_counter() - warmup_started) * 1000.0
            )
        warmup_positions = state_0.particle_q.numpy()
        if not np.isfinite(warmup_positions).all():
            raise RuntimeError("mpm_warmup_created_nonfinite_positions")
        solver = SolverImplicitMPM(
            model,
            options,
            verbose=bool(args.solver_diagnostics),
            enable_timers=bool(args.solver_diagnostics),
        )
        state_0 = model.state()
        state_1 = model.state()
    wp.synchronize_device(device)
    setup_ms = (time.perf_counter() - setup_started) * 1000.0

    bridge_memory: SharedFluidFrame | None = None
    bridge_connection: socket.socket | None = None
    bridge_times_ms: list[float] = []
    transport_write_times_ms: list[float] = []
    socket_send_times_ms: list[float] = []
    renderer_roundtrip_wait_times_ms: list[float] = []
    if args.bridge_socket is not None or args.shared_memory_name is not None:
        if args.bridge_socket is None or args.shared_memory_name is None:
            raise ValueError("bridge_socket_and_shared_memory_name_required_together")
        bridge_memory = SharedFluidFrame.attach(args.shared_memory_name)
        bridge_connection = _connect_bridge(
            args.bridge_socket.resolve(),
            args.bridge_timeout_s,
        )
        send_message(
            bridge_connection,
            {
                "schema": BRIDGE_SCHEMA,
                "type": "hello",
                "particle_count": particle_count,
                "observation_count": requested_count,
                "packet_sha256": sha256_file(packet.manifest_path),
            },
        )
        hello_reply = receive_message(bridge_connection)
        if hello_reply.get("type") != "hello_ack":
            raise RuntimeError(f"bridge_hello_rejected:{hello_reply}")

    physics_times_ms: list[float] = []
    readback_times_ms: list[float] = []
    score_times_ms: list[float] = []
    score_history: list[dict[str, Any]] = []
    review_positions: list[np.ndarray] = []
    review_indices: list[int] = []

    substep_poses_host = precompute_substep_poses(
        source_poses,
        observation_count=requested_count,
        substeps=args.debug_substeps,
    )
    substep_poses_device = wp.array(
        substep_poses_host,
        dtype=wp.transform,
        device=device,
    )
    pose_cursor = wp.zeros(1, dtype=wp.int32, device=device)
    set_pose_cursor_kernel, set_source_pose_kernel = _make_source_pose_kernels(wp)
    breakdown_times_ms: dict[str, list[float]] = {
        "pose_update": [],
        "solver_step": [],
        "project_outside": [],
        "table_guard": [],
    }
    solver_diagnostic_stream = io.StringIO() if args.solver_diagnostics else None

    def time_gpu_section(name: str, operation: Any) -> None:
        if not args.timing_breakdown:
            operation()
            return
        wp.synchronize_device(device)
        started = time.perf_counter()
        operation()
        wp.synchronize_device(device)
        breakdown_times_ms[name].append((time.perf_counter() - started) * 1000.0)

    def set_pose_cursor(value: int) -> None:
        if source_body < 0:
            return
        wp.launch(
            set_pose_cursor_kernel,
            dim=1,
            inputs=[pose_cursor, int(value)],
            device=device,
        )

    def set_source_pose_from_cursor() -> None:
        if source_body < 0:
            return
        wp.launch(
            set_source_pose_kernel,
            dim=1,
            inputs=[
                state_0.body_q,
                state_0.body_qd,
                substep_poses_device,
                pose_cursor,
                source_body,
            ],
            device=device,
        )

    def solver_step() -> None:
        output_context = (
            contextlib.redirect_stdout(solver_diagnostic_stream)
            if solver_diagnostic_stream is not None
            else contextlib.nullcontext()
        )
        with output_context:
            solver.step(
                state_0,
                state_1,
                control=None,
                contacts=None,
                dt=args.debug_integration_dt,
            )

    def advance_substeps(
        observation_index: int | None = None,
        *,
        initialize_pose_cursor: bool = True,
    ) -> None:
        nonlocal state_0, state_1
        if observation_index is not None and initialize_pose_cursor:
            set_pose_cursor(observation_index * args.debug_substeps)
        for substep_index in range(args.debug_substeps):
            if observation_index is not None and source_body >= 0:
                time_gpu_section("pose_update", set_source_pose_from_cursor)
            time_gpu_section("solver_step", solver_step)
            if profile["project_outside"]:
                time_gpu_section(
                    "project_outside",
                    lambda: solver.project_outside(
                        state_1,
                        state_1,
                        args.debug_integration_dt,
                    ),
                )
            time_gpu_section("table_guard", lambda: apply_table_guard(state_1))
            state_0, state_1 = state_1, state_0

    graph = None
    if bool(profile["graph"]):
        if not device.is_cuda:
            raise RuntimeError("cuda_graph_requires_cuda")
        if profile["grid_type"] != "fixed":
            raise RuntimeError("cuda_graph_requires_fixed_grid")
        pristine_state_0 = model.state()
        pristine_state_1 = model.state()
        with wp.ScopedCapture(device=device) as capture:
            advance_substeps(0, initialize_pose_cursor=False)
        graph = capture.graph
        state_0.assign(pristine_state_0)
        state_1.assign(pristine_state_1)
        wp.synchronize_device(device)

    for observation_index in range(requested_count):
        wp.synchronize_device(device)
        physics_started = time.perf_counter()
        if graph is not None:
            set_pose_cursor(observation_index * args.debug_substeps)
            wp.capture_launch(graph)
        else:
            advance_substeps(observation_index)
        wp.synchronize_device(device)
        physics_times_ms.append((time.perf_counter() - physics_started) * 1000.0)

        readback_started = time.perf_counter()
        current_positions = state_0.particle_q.numpy()
        readback_times_ms.append((time.perf_counter() - readback_started) * 1000.0)
        score_started = time.perf_counter()
        source_frame_world = source_frame_local @ _pose_matrix_xyzw(
            source_poses[observation_index]
        )
        source_frame = packet.manifest["frames"]["source"]
        target_frame = packet.manifest["frames"]["target"]
        score = classify_positions(
            current_positions,
            source_frame_world_matrix=source_frame_world,
            target_frame_world_matrix=target_frame_world,
            source_interior_radius_m=float(source_frame["interior_radius_m"]),
            target_interior_radius_m=float(target_frame["interior_radius_m"]),
            source_floor_m=float(source_frame["floor_m"]),
            source_rim_m=float(source_frame["rim_m"]),
            target_floor_m=float(target_frame["floor_m"]),
            target_rim_m=float(target_frame["rim_m"]),
            table_top_z_m=table_top_z,
        )
        score["observation_index"] = observation_index
        score_history.append(score)
        score_times_ms.append((time.perf_counter() - score_started) * 1000.0)

        if (
            observation_index in REVIEW_FRAME_INDICES
            or observation_index == requested_count - 1
        ):
            review_indices.append(observation_index)
            review_positions.append(current_positions.astype(np.float32, copy=True))

        if bridge_memory is not None and bridge_connection is not None:
            bridge_started = time.perf_counter()
            transport_started = time.perf_counter()
            checksum = bridge_memory.write(
                current_positions,
                frame_index=observation_index,
                simulation_time_s=(observation_index + 1) * LOGICAL_DT_S,
            )
            transport_write_times_ms.append(
                (time.perf_counter() - transport_started) * 1000.0
            )
            socket_send_started = time.perf_counter()
            send_message(
                bridge_connection,
                {
                    "schema": BRIDGE_SCHEMA,
                    "type": "frame",
                    "frame_index": observation_index,
                    "checksum_crc32": checksum,
                },
            )
            socket_send_times_ms.append(
                (time.perf_counter() - socket_send_started) * 1000.0
            )
            renderer_wait_started = time.perf_counter()
            acknowledgement = receive_message(bridge_connection)
            renderer_roundtrip_wait_times_ms.append(
                (time.perf_counter() - renderer_wait_started) * 1000.0
            )
            if (
                acknowledgement.get("type") != "frame_ack"
                or acknowledgement.get("frame_index") != observation_index
            ):
                raise RuntimeError(
                    f"bridge_frame_ack_invalid:{acknowledgement}"
                )
            bridge_times_ms.append(
                (time.perf_counter() - bridge_started) * 1000.0
            )

    if bridge_connection is not None:
        send_message(
            bridge_connection,
            {
                "schema": BRIDGE_SCHEMA,
                "type": "complete",
                "observation_count": requested_count,
            },
        )
        completed_reply = receive_message(bridge_connection)
        if completed_reply.get("type") != "complete_ack":
            raise RuntimeError(f"bridge_complete_rejected:{completed_reply}")
        bridge_connection.close()
    if bridge_memory is not None:
        bridge_memory.close()

    review_path = output_dir / "review_particle_frames.npz"
    np.savez_compressed(
        review_path,
        observation_indices=np.asarray(review_indices, dtype=np.int32),
        particle_positions=np.stack(review_positions, axis=0),
    )
    score_path = output_dir / "score_history.jsonl"
    score_path.write_text(
        "".join(
            json.dumps(record, sort_keys=True, allow_nan=False) + "\n"
            for record in score_history
        ),
        encoding="utf-8",
    )

    visual_liquid_passed = (
        True
        if args.visual_liquid_passed
        else False
        if args.visual_liquid_failed
        else None
    )
    quality = evaluate_quality_gate(
        score_history,
        visual_liquid_passed=visual_liquid_passed,
    )
    if args.timing_warmup_observations < 0:
        raise ValueError("timing_warmup_observations_negative")
    if args.timing_warmup_observations >= len(physics_times_ms):
        raise ValueError("timing_warmup_observations_exhaust_measurements")
    timing_start = args.timing_warmup_observations
    measured_physics_times_ms = physics_times_ms[timing_start:]
    measured_readback_times_ms = readback_times_ms[timing_start:]
    physics_summary = summarize_milliseconds(measured_physics_times_ms)
    readback_summary = summarize_milliseconds(measured_readback_times_ms)
    physics_end_to_end_times_ms = [
        physics_ms + readback_ms
        for physics_ms, readback_ms in zip(
            measured_physics_times_ms,
            measured_readback_times_ms,
            strict=True,
        )
    ]
    physics_end_to_end_summary = summarize_milliseconds(
        physics_end_to_end_times_ms
    )
    score_summary = summarize_milliseconds(score_times_ms[timing_start:])
    bridge_summary = (
        summarize_milliseconds(bridge_times_ms[timing_start:])
        if bridge_times_ms
        else None
    )
    artifact_ready_mean_ms = (
        float(physics_end_to_end_summary["mean_ms"])
        + float(score_summary["mean_ms"])
        + (
            float(bridge_summary["mean_ms"])
            if bridge_summary is not None
            else 0.0
        )
    )
    diagnostic_path = None
    solver_diagnostics = None
    if solver_diagnostic_stream is not None:
        diagnostic_path = output_dir / "solver_diagnostics.log"
        diagnostic_text = solver_diagnostic_stream.getvalue()
        diagnostic_path.write_text(diagnostic_text, encoding="utf-8")
        solver_diagnostics = parse_solver_diagnostics(diagnostic_text)
        solver_diagnostics["log_path"] = str(diagnostic_path)
        solver_diagnostics["log_sha256"] = sha256_file(diagnostic_path)

    breakdown_summary = {
        name: summarize_milliseconds(values) if values else None
        for name, values in breakdown_times_ms.items()
    }
    result = {
        "schema": RESULT_SCHEMA,
        "status": "passed" if quality["passed"] else "failed_quality",
        "claim_boundary": (
            "experimental_newton140_mpm_candidate;"
            "not_formal_isaac41_evidence;"
            "solver_specific_controller_retarget;"
            "analytic_table_halfspace_guard;"
            "visual_review_not_independent"
        ),
        "profile_name": args.profile,
        "profile": profile,
        "initialization": {
            "layout": args.initial_layout,
            "points_per_layer": (
                args.points_per_layer
                if args.initial_layout == "regular_cylinder"
                else None
            ),
            "jitter_fraction": (
                args.initial_jitter_fraction
                if args.initial_layout == "regular_cylinder"
                else None
            ),
            "particle_radius_m": particle_radius,
            "particle_mass_kg": particle_mass,
            "effective_density_kg_m3": particle_mass
            / (8.0 * particle_radius**3),
            "collider_margin_m": args.collider_margin,
            "collider_representation": args.collider_representation,
            "mesh_segments": (
                args.mesh_segments
                if args.collider_representation == "simplified_mesh"
                else None
            ),
            "source_motion_policy": (
                "recorded_orientation_with_newton_pour_alignment_v1"
                if args.pour_retarget
                else "recorded_pose_exact"
            ),
            "pour_retarget_offset_m": (
                list(args.pour_retarget_offset_m)
                if args.pour_retarget
                else None
            ),
            "pour_retarget_blend_observations": (
                list(args.pour_retarget_blend)
                if args.pour_retarget
                else None
            ),
            "table_halfspace_guard": bool(args.table_halfspace_guard),
            "table_halfspace_minimum_z_m": (
                table_top_z + particle_radius
                if args.table_halfspace_guard
                else None
            ),
            "table_halfspace_corrected_unique_particles": (
                int(np.count_nonzero(table_guard_flags.numpy()))
                if args.table_halfspace_guard
                else 0
            ),
        },
        "particle_count": particle_count,
        "observation_count": requested_count,
        "requested_observation_count": requested_count,
        "integration_steps": requested_count * args.debug_substeps,
        "timing": {
            "schema": "labutopia.newton_mpm_timing.v2",
            "setup_ms": setup_ms,
            "synthetic_compile_warmup_observations": args.warmup_observations,
            "cold_first_synthetic_observation_ms": (
                compile_warmup_times_ms[0] if compile_warmup_times_ms else None
            ),
            "synthetic_compile_warmup_per_observation": (
                summarize_milliseconds(compile_warmup_times_ms)
                if compile_warmup_times_ms
                else None
            ),
            "trace_timing_warmup_observations_excluded": timing_start,
            "trace_observations_scored": requested_count,
            "trace_observations_timed": len(physics_times_ms) - timing_start,
            "solver_execution_per_observation": physics_summary,
            "solver_execution_fps": 1000.0 / float(physics_summary["mean_ms"]),
            "particle_readback_per_observation": readback_summary,
            "physics_per_observation": physics_end_to_end_summary,
            "physics_fps": 1000.0
            / float(physics_end_to_end_summary["mean_ms"]),
            "score_per_observation": score_summary,
            "bridge_transaction_per_observation": bridge_summary,
            "transport_write_per_observation": (
                summarize_milliseconds(transport_write_times_ms[timing_start:])
                if transport_write_times_ms
                else None
            ),
            "socket_send_per_observation": (
                summarize_milliseconds(socket_send_times_ms[timing_start:])
                if socket_send_times_ms
                else None
            ),
            "renderer_roundtrip_wait_per_observation": (
                summarize_milliseconds(
                    renderer_roundtrip_wait_times_ms[timing_start:]
                )
                if renderer_roundtrip_wait_times_ms
                else None
            ),
            "diagnostic_breakdown_enabled": bool(args.timing_breakdown),
            "diagnostic_breakdown_per_substep": breakdown_summary,
            "performance_comparable": not args.timing_breakdown,
            "artifact_ready_mean_ms": artifact_ready_mean_ms,
            "artifact_ready_fps": 1000.0 / artifact_ready_mean_ms,
            "logical_simulated_seconds": requested_count * LOGICAL_DT_S,
            "wall_started_unix_s": started_wall_s,
            "wall_finished_unix_s": time.time(),
        },
        "quality": quality,
        "packet": {
            "path": str(packet.manifest_path),
            "sha256": sha256_file(packet.manifest_path),
            "arrays_path": str(packet.arrays_path),
            "arrays_sha256": sha256_file(packet.arrays_path),
        },
        "runtime": _runtime_identity(wp, newton, device, args.runtime_receipt),
        "solver_diagnostics": solver_diagnostics,
        "artifacts": {
            "review_particle_frames": {
                "path": str(review_path),
                "sha256": sha256_file(review_path),
            },
            "score_history": {
                "path": str(score_path),
                "sha256": sha256_file(score_path),
            },
            "solver_diagnostics": (
                {
                    "path": str(diagnostic_path),
                    "sha256": sha256_file(diagnostic_path),
                }
                if diagnostic_path is not None
                else None
            ),
        },
    }
    result["content_sha256"] = canonical_json_sha256(result)
    result_path = output_dir / "result.json"
    _atomic_json(result_path, result)
    print(json.dumps({"result_path": str(result_path), **result}, sort_keys=True))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="sparse_q1_gs_fast")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--allow-cpu", action="store_true")
    parser.add_argument("--max-observations", type=int)
    parser.add_argument(
        "--particle-count",
        type=int,
        choices=(900, 1800, 3600, 7200),
        default=3600,
    )
    parser.add_argument("--trajectory-npz", type=Path)
    parser.add_argument("--runtime-receipt", type=Path)
    parser.add_argument("--warmup-observations", type=int, default=1)
    parser.add_argument(
        "--timing-warmup-observations",
        type=int,
        default=1,
        help="Exclude this many leading trace observations from timing only.",
    )
    parser.add_argument(
        "--timing-breakdown",
        action="store_true",
        help="Synchronizing diagnostic timing; output is not performance-comparable.",
    )
    parser.add_argument(
        "--solver-diagnostics",
        action="store_true",
        help="Capture Newton iteration/residual output and internal section timers.",
    )
    parser.add_argument(
        "--pour-retarget",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Blend the declared Newton-specific source alignment before the "
            "pour; use --no-pour-retarget for the exact recorded pose trace."
        ),
    )
    parser.add_argument(
        "--pour-retarget-offset-m",
        type=float,
        nargs=3,
        default=NEWTON_POUR_RETARGET_OFFSET_M,
    )
    parser.add_argument(
        "--pour-retarget-blend",
        type=int,
        nargs=2,
        default=NEWTON_POUR_RETARGET_BLEND,
    )
    parser.add_argument(
        "--debug-substeps",
        type=int,
        default=SUBSTEPS_PER_OBSERVATION,
        help="Diagnostic override; controlled matrix leaves this at four.",
    )
    parser.add_argument(
        "--debug-integration-dt",
        type=float,
        default=INTEGRATION_DT_S,
        help="Diagnostic override; controlled matrix leaves this at 1/120 s.",
    )
    parser.add_argument(
        "--initial-layout",
        choices=("authored", "regular_cylinder", "regular_box"),
        default="regular_box",
    )
    parser.add_argument("--points-per-layer", type=int, default=150)
    parser.add_argument("--initial-jitter-fraction", type=float, default=0.10)
    parser.add_argument("--grid-type", choices=("sparse", "dense", "fixed"))
    parser.add_argument("--grid-padding", type=int)
    parser.add_argument("--voxel-size", type=float)
    parser.add_argument("--max-iterations", type=int)
    parser.add_argument("--tolerance", type=float)
    parser.add_argument("--solver")
    parser.add_argument("--strain-basis")
    parser.add_argument("--velocity-basis")
    parser.add_argument("--collider-basis")
    parser.add_argument(
        "--collider-velocity-mode",
        choices=("forward", "backward"),
    )
    parser.add_argument("--transfer-scheme")
    parser.add_argument("--warmstart-mode")
    parser.add_argument("--viscosity", type=float)
    parser.add_argument("--particle-friction", type=float, default=0.0)
    parser.add_argument("--particle-radius", type=float)
    parser.add_argument("--particle-density", type=float)
    parser.add_argument("--collider-friction", type=float, default=0.05)
    parser.add_argument("--collider-margin", type=float, default=0.0025)
    parser.add_argument(
        "--collider-representation",
        choices=("simplified_mesh", "wrapper_boxes"),
        default="simplified_mesh",
    )
    parser.add_argument("--mesh-segments", type=int, default=64)
    parser.add_argument("--mesh-wall-thickness", type=float, default=0.006)
    parser.add_argument("--mesh-bottom-thickness", type=float, default=0.008)
    parser.add_argument("--table-friction", type=float, default=0.2)
    parser.add_argument(
        "--table-halfspace-guard",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--omit-vessel-colliders", action="store_true")
    parser.add_argument("--omit-table-collider", action="store_true")
    parser.add_argument("--omit-source-body", action="store_true")
    parser.add_argument("--static-source-colliders", action="store_true")
    parser.add_argument("--bridge-socket", type=Path)
    parser.add_argument("--shared-memory-name")
    parser.add_argument("--bridge-timeout-s", type=float, default=120.0)
    parser.add_argument("--visual-liquid-passed", action="store_true")
    parser.add_argument("--visual-liquid-failed", action="store_true")
    graph_group = parser.add_mutually_exclusive_group()
    graph_group.add_argument("--graph", action="store_true", dest="graph")
    graph_group.add_argument("--no-graph", action="store_false", dest="graph")
    parser.set_defaults(graph=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.visual_liquid_passed and args.visual_liquid_failed:
        raise ValueError("visual_liquid_flags_mutually_exclusive")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
