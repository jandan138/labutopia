#!/usr/bin/env python3
"""One-runtime-child benchmark for Newton-only fluid solver candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_benchmark_contract import (  # noqa: E402
    EXPECTED_OBSERVATION_COUNT,
    classify_positions,
    evaluate_quality_gate,
    evaluate_stability_gate,
    load_packet,
    row_transform_points,
    sha256_file,
    summarize_milliseconds,
)
from tools.labutopia_fluid.newton_only_contract import (  # noqa: E402
    ROBOT_LANES,
    RUN_RESULT_SCHEMA,
    VISUAL_REVIEW_FRAME_INDICES,
    solver_spec,
    validate_reoptimized_trajectory,
)
from tools.labutopia_fluid.newton_only_solvers import (  # noqa: E402
    SolverCapabilityError,
    create_solver_adapter,
)


DEFAULT_PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)


DEFAULT_PARAMETERS: dict[str, dict[str, Any]] = {
    "newton_xpbd_cohesion": {"iterations": 2, "cohesion": 0.002},
    "newton_vbd_self_contact": {"iterations": 2},
    "newton_semiimplicit_particles": {},
    "labutopia_wcsph": {"sound_speed_m_s": 6.0, "viscosity": 0.002},
    "warp_example_sph": {"sound_speed_m_s": 4.0, "viscosity": 0.025},
    "splishsplash_pbf_port": {
        "maximum_iterations": 6,
        "minimum_iterations": 2,
        "tolerance": 0.02,
    },
    "warp_example_apic": {
        "maximum_iterations": 80,
        "tolerance": 1.0e-5,
    },
    "labutopia_dfsph": {
        "divergence_maximum_iterations": 4,
        "density_maximum_iterations": 6,
        "minimum_iterations": 2,
        "divergence_tolerance_s_inv": 0.1,
        "density_tolerance_s_inv": 0.1,
    },
    "splishsplash_dfsph_port": {
        "divergence_maximum_iterations": 4,
        "density_maximum_iterations": 6,
        "minimum_iterations": 2,
        "divergence_tolerance_s_inv": 0.1,
        "density_tolerance_s_inv": 0.1,
    },
}


ALGORITHM_CONFORMANCE: dict[str, dict[str, Any]] = {
    "newton_xpbd_cohesion": {
        "status": "upstream_native",
        "ranking_eligible": True,
    },
    "newton_vbd_self_contact": {
        "status": "upstream_native",
        "ranking_eligible": True,
    },
    "newton_semiimplicit_particles": {
        "status": "upstream_native",
        "ranking_eligible": True,
    },
    "labutopia_wcsph": {
        "status": "labutopia_implementation",
        "ranking_eligible": True,
    },
    "warp_example_sph": {
        "status": "warp_apache_example_equations_adapted_to_z_up_and_scene_colliders",
        "ranking_eligible": True,
    },
    "splishsplash_pbf_port": {
        "status": "pbf_kernel_smoke_only_splishsplash_source_equivalence_not_yet_reviewed",
        "ranking_eligible": False,
    },
    "warp_example_apic": {
        "status": (
            "installed_warp_official_fem_apic_particle_grid_and_pressure_path;"
            "labutopia_post_advection_moving_wrapper_boundary_adaptation"
        ),
        "ranking_eligible": True,
    },
    "labutopia_dfsph": {
        "status": "labutopia_warp_density_and_divergence_velocity_projection",
        "ranking_eligible": True,
    },
    "splishsplash_dfsph_port": {
        "status": (
            "dfsph_kernel_port_smoke_only;"
            "splishsplash_source_equivalence_not_yet_reviewed"
        ),
        "ranking_eligible": False,
    },
}


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _summarize_values(values: Sequence[float | int]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or len(array) == 0 or not np.isfinite(array).all():
        raise ValueError("numeric_summary_values_invalid")
    return {
        "count": int(len(array)),
        "minimum": float(np.min(array)),
        "mean": float(np.mean(array)),
        "p50": float(np.percentile(array, 50)),
        "p95": float(np.percentile(array, 95)),
        "maximum": float(np.max(array)),
    }


def _resample_particles(
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
        indices = np.linspace(0, 3599, particle_count, dtype=np.int64)
        result = authored[indices].copy()
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
        norms = np.linalg.norm(direction, axis=1, keepdims=True)
        direction /= np.maximum(norms, 1.0e-6)
        signs = np.where((np.arange(len(result)) % 2)[:, None] == 0, -1.0, 1.0)
        result += signs * direction * float(base_radius_m) * 0.2
    if result.shape != (particle_count, 3) or not np.isfinite(result).all():
        raise RuntimeError("resampled_particles_invalid")
    return result.astype(np.float32)


def _source_frame_world(packet: Any, pose_xyzw: np.ndarray) -> np.ndarray:
    from tools.labutopia_fluid.run_newton140_mpm_benchmark import _pose_matrix_xyzw

    return packet.array("source_frame_local_matrix", (4, 4)) @ _pose_matrix_xyzw(pose_xyzw)


def _merged_parameters(solver_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
    parameters = dict(DEFAULT_PARAMETERS.get(solver_id, {}))
    parameters.update(value)
    return parameters


def _runtime_record(args: argparse.Namespace) -> dict[str, Any]:
    if args.runtime_receipt is None:
        return {
            "executable": sys.executable,
            "prefix": sys.prefix,
            "authoritative": False,
            "reason": args.runtime_claim,
        }
    receipt_path = args.runtime_receipt.resolve(strict=True)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    newton_receipt = (
        receipt.get("schema") == "labutopia.newton_only_runtime_attestation.v1"
        and receipt.get("status") == "matched_experimental_runtime"
    )
    isaac_receipt = (
        receipt.get("schema") == "labutopia.experimental_fluid_runtime_attestation.v1"
        and receipt.get("status") == "passed"
        and ((receipt.get("capabilities") or {}).get("physics") or {}).get("status")
        == "passed"
    )
    if (
        not (newton_receipt or isaac_receipt)
        or receipt.get("executable") != sys.executable
        or Path(receipt.get("prefix", "")).resolve(strict=True)
        != Path(sys.prefix).resolve(strict=True)
    ):
        raise RuntimeError("newton_runtime_receipt_mismatch")
    return {
        "executable": sys.executable,
        "prefix": sys.prefix,
        "authoritative": True,
        "claim_boundary": receipt["claim_boundary"],
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_content_sha256": receipt["content_sha256"],
        "lane": receipt.get("lane"),
        "capabilities": receipt.get("capabilities"),
    }


def _adapter_arguments(
    *,
    args: argparse.Namespace,
    packet: Any,
    parameters: Mapping[str, Any],
    source_poses: np.ndarray,
) -> dict[str, Any]:
    fluid = packet.manifest["fluid"]
    base_positions = packet.array("initial_particle_positions", (3600, 3))
    base_radius = float(fluid["particle_radius_m"])
    scale = (3600.0 / args.particle_count) ** (1.0 / 3.0)
    selected_parameters = dict(parameters)
    selected_parameters.setdefault("support_radius_m", base_radius * scale * 4.0)
    return {
        "solver_id": args.solver_id,
        "initial_positions": _resample_particles(
            base_positions,
            args.particle_count,
            base_radius_m=base_radius,
        ),
        "particle_radius_m": base_radius * scale,
        "particle_mass_kg": float(fluid["particle_mass_kg"]) * 3600.0 / args.particle_count,
        "source_box_poses_xyzw": packet.array(
            "source_box_poses_xyzw", (int(packet.manifest["source_box_count"]), 7)
        ),
        "source_box_half_extents": packet.array(
            "source_box_half_extents", (int(packet.manifest["source_box_count"]), 3)
        ),
        "target_box_poses_xyzw": packet.array(
            "target_box_poses_xyzw", (int(packet.manifest["target_box_count"]), 7)
        ),
        "target_box_half_extents": packet.array(
            "target_box_half_extents", (int(packet.manifest["target_box_count"]), 3)
        ),
        "table_top_z_m": float(packet.manifest["frames"]["table_top_z_m"]),
        "initial_source_pose_xyzw": source_poses[0],
        "parameters": selected_parameters,
        "device": args.device,
    }


def _score_positions(packet: Any, positions: np.ndarray, pose_xyzw: np.ndarray) -> dict[str, Any]:
    source = packet.manifest["frames"]["source"]
    target = packet.manifest["frames"]["target"]
    return classify_positions(
        positions,
        source_frame_world_matrix=_source_frame_world(packet, pose_xyzw),
        target_frame_world_matrix=packet.array("target_frame_world_matrix", (4, 4)),
        source_interior_radius_m=float(source["interior_radius_m"]),
        target_interior_radius_m=float(target["interior_radius_m"]),
        source_floor_m=float(source["floor_m"]),
        source_rim_m=float(source["rim_m"]),
        target_floor_m=float(target["floor_m"]),
        target_rim_m=float(target["rim_m"]),
        table_top_z_m=float(packet.manifest["frames"]["table_top_z_m"]),
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    started_wall_s = time.time()
    if args.output_dir.exists():
        raise FileExistsError(f"output_dir_exists:{args.output_dir}")
    args.output_dir.mkdir(parents=True)
    packet = load_packet(args.packet)
    spec = solver_spec(args.solver_id)
    if args.robot_lane != "kinematic_replay":
        raise SolverCapabilityError(
            "newton_dynamics_fixed_grasp_requires_attested_franka_scene_pack"
        )
    if args.solver_id == "newton_implicit_mpm":
        raise SolverCapabilityError(
            "solver_route_is_owned_by_dedicated_adapter_or_pending_algorithm_validation"
        )
    parameters = _merged_parameters(args.solver_id, args.parameters)
    reference_source_poses = packet.array(
        "source_poses_xyzw", (EXPECTED_OBSERVATION_COUNT, 7)
    )
    if args.trajectory_npz is None:
        source_poses = reference_source_poses
        trajectory_record = {
            "kind": "exact_packet_trace",
            "path": None,
            "sha256": None,
            "validation": validate_reoptimized_trajectory(
                source_poses, reference_source_poses
            ),
        }
    else:
        trajectory_path = args.trajectory_npz.resolve(strict=True)
        with np.load(trajectory_path, allow_pickle=False) as archive:
            if tuple(archive.files) != ("source_poses_xyzw",):
                raise ValueError("trajectory_archive_fields_invalid")
            source_poses = np.asarray(archive["source_poses_xyzw"], dtype=np.float64)
        trajectory_record = {
            "kind": "solver_reoptimized_candidate",
            "path": str(trajectory_path),
            "sha256": sha256_file(trajectory_path),
            "validation": validate_reoptimized_trajectory(
                source_poses, reference_source_poses
            ),
        }
    adapter_kwargs = _adapter_arguments(
        args=args,
        packet=packet,
        parameters=parameters,
        source_poses=source_poses,
    )
    host_update = None
    host_points_attr = None
    host_vt = None
    host_bridge_record: dict[str, Any] | None = None
    render_memory = None
    render_connection: socket.socket | None = None
    render_reconstructor = None
    render_lower = np.asarray(args.render_bounds_lower, dtype=np.float32)
    render_upper = np.asarray(args.render_bounds_upper, dtype=np.float32)
    if args.host_runtime_update in {"isaac_kit", "isaac_kit_particles"}:
        import omni.kit.app

        host_update = omni.kit.app.get_app().update
    if args.host_runtime_update == "isaac_kit_particles":
        import omni.usd
        from pxr import Gf, UsdGeom, Vt

        context = omni.usd.get_context()
        context.new_stage()
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("isaac_usd_stage_missing_after_new_stage")
        points = UsdGeom.Points.Define(stage, "/World/LiquidParticles")
        points.CreateWidthsAttr().Set(
            Vt.FloatArray(
                [float(adapter_kwargs["particle_radius_m"]) * 2.0]
                * args.particle_count
            )
        )
        points.CreateDisplayColorAttr().Set(Vt.Vec3fArray([Gf.Vec3f(0.05, 0.65, 0.82)]))
        host_points_attr = points.CreatePointsAttr()
        host_vt = Vt
        host_update()
        host_bridge_record = {
            "kind": "isaac_usd_points_particle_display",
            "prim_path": "/World/LiquidParticles",
            "surface_reconstruction": False,
            "particle_count": args.particle_count,
        }
    if args.render_bridge_socket is not None:
        from tools.labutopia_fluid.fluid_benchmark_bridge import (
            RENDER_BRIDGE_SCHEMA,
            SharedFluidRenderFrame,
            receive_message,
            send_message,
        )

        if args.render_shared_memory_name is None or args.render_representation is None:
            raise ValueError("render_bridge_requires_memory_and_representation")
        if args.particle_count != 3600:
            raise ValueError("render_bridge_requires_3600_particles")
        render_memory = SharedFluidRenderFrame.attach(args.render_shared_memory_name)
        render_connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        render_connection.settimeout(args.render_bridge_timeout_s)
        render_connection.connect(str(args.render_bridge_socket))
        send_message(
            render_connection,
            {
                "schema": RENDER_BRIDGE_SCHEMA,
                "type": "hello",
                "particle_count": args.particle_count,
                "observation_count": args.max_observations,
                "representation": args.render_representation,
            },
        )
        hello_ack = receive_message(render_connection)
        if hello_ack != {"schema": RENDER_BRIDGE_SCHEMA, "type": "hello_ack"}:
            raise RuntimeError(f"render_bridge_hello_ack_invalid:{hello_ack}")
        if args.render_representation == "surface_gpu":
            from tools.labutopia_fluid.warp_surface_reconstruction import (
                WarpSurfaceReconstructor,
            )

            render_reconstructor = WarpSurfaceReconstructor(
                bounds_lower_m=render_lower,
                bounds_upper_m=render_upper,
                voxel_size_m=args.render_voxel_size_m,
                support_radius_m=args.render_support_radius_m,
                threshold=args.render_surface_threshold,
                device=args.device,
            )

    cold_started = time.perf_counter()
    cold_adapter = create_solver_adapter(**adapter_kwargs)
    cold_setup_ms = (time.perf_counter() - cold_started) * 1000.0
    cold_step_started = time.perf_counter()
    cold_diagnostics = cold_adapter.logical_step(source_poses[0], source_poses[0])
    cold_step_ms = (time.perf_counter() - cold_step_started) * 1000.0
    cold_adapter.close()

    warm_started = time.perf_counter()
    adapter = create_solver_adapter(**adapter_kwargs)
    steady_setup_ms = (time.perf_counter() - warm_started) * 1000.0
    for warmup_index in range(args.warmup_observations):
        index = min(warmup_index, EXPECTED_OBSERVATION_COUNT - 1)
        previous = source_poses[max(0, index - 1)]
        adapter.logical_step(previous, source_poses[index])
    adapter.close()
    adapter = create_solver_adapter(**adapter_kwargs)

    physics_times_ms: list[float] = []
    readback_times_ms: list[float] = []
    score_times_ms: list[float] = []
    host_update_times_ms: list[float] = []
    host_usd_authoring_times_ms: list[float] = []
    simulation_chain_times_ms: list[float] = []
    actual_iterations: list[int] = []
    residuals: list[float] = []
    substeps: list[int] = []
    score_history: list[dict[str, Any]] = []
    maximum_speeds_m_s: list[float] = []
    internal_timing_history: dict[str, list[float]] = {}
    diagnostic_counter_history: dict[str, list[int]] = {}
    review_indices: list[int] = []
    review_positions: list[np.ndarray] = []
    all_positions: list[np.ndarray] | None = [] if args.capture_all_particle_frames else None
    render_artifact_ready_times_ms: list[float] = []
    render_surface_reconstruction_times_ms: list[float] = []
    render_surface_readback_times_ms: list[float] = []
    render_handoff_to_rgb_ack_times_ms: list[float] = []
    render_mesh_sizes: list[dict[str, int]] = []
    for observation_index in range(args.max_observations):
        previous_pose = source_poses[max(0, observation_index - 1)]
        current_pose = source_poses[observation_index]
        step_started = time.perf_counter()
        diagnostics = adapter.logical_step(previous_pose, current_pose)
        physics_ms = (time.perf_counter() - step_started) * 1000.0
        physics_times_ms.append(physics_ms)
        positions = None
        readback_ms = None
        host_ms = 0.0
        if host_points_attr is not None:
            host_started = time.perf_counter()
            readback_started = time.perf_counter()
            positions = adapter.particle_positions().numpy()
            readback_ms = (time.perf_counter() - readback_started) * 1000.0
            author_started = time.perf_counter()
            host_points_attr.Set(
                host_vt.Vec3fArray.FromNumpy(
                    np.asarray(positions, dtype=np.float32)
                )
            )
            host_usd_authoring_times_ms.append(
                (time.perf_counter() - author_started) * 1000.0
            )
            host_update()
            host_ms = (time.perf_counter() - host_started) * 1000.0
            host_update_times_ms.append(host_ms)
        elif host_update is not None:
            host_started = time.perf_counter()
            host_update()
            host_ms = (time.perf_counter() - host_started) * 1000.0
            host_update_times_ms.append(host_ms)
        simulation_chain_times_ms.append(physics_ms + host_ms)
        substeps.append(diagnostics.substeps)
        maximum_speeds_m_s.append(diagnostics.maximum_speed_m_s)
        actual_iterations.extend(diagnostics.actual_iterations)
        residuals.extend(diagnostics.final_residuals)
        for name, value in diagnostics.timings_ms.items():
            internal_timing_history.setdefault(name, []).append(float(value))
        for name, value in diagnostics.counters.items():
            diagnostic_counter_history.setdefault(name, []).append(int(value))

        if positions is None:
            readback_started = time.perf_counter()
            positions = adapter.particle_positions().numpy()
            readback_ms = (time.perf_counter() - readback_started) * 1000.0
        readback_times_ms.append(float(readback_ms))
        if not np.isfinite(positions).all():
            raise RuntimeError(f"nonfinite_particle_positions:{observation_index}")
        if render_connection is not None and render_memory is not None:
            handoff_started = time.perf_counter()
            if args.render_representation == "particles":
                checksum = render_memory.write_particles(
                    positions,
                    frame_index=observation_index,
                    simulation_time_s=observation_index / 30.0,
                )
            else:
                surface = render_reconstructor.reconstruct(positions)
                render_surface_reconstruction_times_ms.append(
                    float(surface.timing_ms["total_ms"])
                )
                surface_readback_started = time.perf_counter()
                vertices = np.ascontiguousarray(surface.vertices.numpy(), dtype=np.float32)
                indices = np.ascontiguousarray(surface.indices.numpy(), dtype=np.int32).reshape(-1)
                render_surface_readback_times_ms.append(
                    (time.perf_counter() - surface_readback_started) * 1000.0
                )
                if len(vertices) < 3 or len(indices) < 3:
                    raise RuntimeError(f"render_surface_empty:{observation_index}")
                residual_mask = np.any(
                    (positions < render_lower) | (positions > render_upper), axis=1
                )
                residual_positions = np.ascontiguousarray(
                    positions[residual_mask], dtype=np.float32
                )
                checksum = render_memory.write_surface(
                    vertices,
                    indices,
                    residual_positions,
                    frame_index=observation_index,
                    simulation_time_s=observation_index / 30.0,
                )
                render_mesh_sizes.append(
                    {
                        "vertex_count": int(len(vertices)),
                        "triangle_count": int(len(indices) // 3),
                        "residual_particle_count": int(len(residual_positions)),
                    }
                )
            send_message(
                render_connection,
                {
                    "schema": RENDER_BRIDGE_SCHEMA,
                    "type": "frame",
                    "frame_index": observation_index,
                    "checksum_crc32": checksum,
                },
            )
            acknowledgement = receive_message(render_connection)
            if acknowledgement != {
                "schema": RENDER_BRIDGE_SCHEMA,
                "type": "frame_ack",
                "frame_index": observation_index,
            }:
                raise RuntimeError(
                    f"render_bridge_frame_ack_invalid:{acknowledgement}"
                )
            render_handoff_to_rgb_ack_times_ms.append(
                (time.perf_counter() - handoff_started) * 1000.0
            )
            render_artifact_ready_times_ms.append(
                (time.perf_counter() - step_started) * 1000.0
            )
        score_started = time.perf_counter()
        score = _score_positions(packet, positions, current_pose)
        score["observation_index"] = observation_index
        score_history.append(score)
        score_times_ms.append((time.perf_counter() - score_started) * 1000.0)
        if observation_index in VISUAL_REVIEW_FRAME_INDICES or observation_index == args.max_observations - 1:
            review_indices.append(observation_index)
            review_positions.append(positions.astype(np.float32, copy=True))
        if all_positions is not None:
            all_positions.append(positions.astype(np.float32, copy=True))
    if render_connection is not None:
        send_message(
            render_connection,
            {
                "schema": RENDER_BRIDGE_SCHEMA,
                "type": "complete",
                "observation_count": args.max_observations,
            },
        )
        complete_ack = receive_message(render_connection)
        if complete_ack != {"schema": RENDER_BRIDGE_SCHEMA, "type": "complete_ack"}:
            raise RuntimeError(f"render_bridge_complete_ack_invalid:{complete_ack}")
        render_connection.close()
        render_connection = None
    if render_memory is not None:
        render_memory.close()
        render_memory = None
    adapter.close()

    review_path = args.output_dir / "review_particle_frames.npz"
    np.savez_compressed(
        review_path,
        observation_indices=np.asarray(review_indices, dtype=np.int32),
        particle_positions=np.stack(review_positions, axis=0),
    )
    score_path = args.output_dir / "score_history.jsonl"
    score_path.write_text(
        "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in score_history),
        encoding="utf-8",
    )
    all_frames_path = None
    if all_positions is not None:
        all_frames_path = args.output_dir / "all_particle_frames.npz"
        np.savez_compressed(
            all_frames_path,
            observation_indices=np.arange(args.max_observations, dtype=np.int32),
            particle_positions=np.stack(all_positions, axis=0),
        )
    render_timing_path = None
    if render_artifact_ready_times_ms:
        render_timing_path = args.output_dir / "render_bridge_timings.npz"
        np.savez_compressed(
            render_timing_path,
            artifact_ready_ms=np.asarray(
                render_artifact_ready_times_ms, dtype=np.float64
            ),
            handoff_to_rgb_ack_ms=np.asarray(
                render_handoff_to_rgb_ack_times_ms, dtype=np.float64
            ),
            surface_reconstruction_ms=np.asarray(
                render_surface_reconstruction_times_ms, dtype=np.float64
            ),
            surface_mesh_readback_ms=np.asarray(
                render_surface_readback_times_ms, dtype=np.float64
            ),
        )
    quality = evaluate_quality_gate(score_history, visual_liquid_passed=None)
    spill_values = np.asarray(
        [row["tabletop_spill_fraction"] for row in score_history], dtype=np.float64
    )
    target_values = np.asarray(
        [row["target_fraction"] for row in score_history], dtype=np.float64
    )
    quality_diagnostics = {
        "peak_tabletop_spill_fraction": float(np.max(spill_values)),
        "peak_tabletop_spill_observation_index": int(np.argmax(spill_values)),
        "peak_target_fraction": float(np.max(target_values)),
        "peak_target_observation_index": int(np.argmax(target_values)),
    }
    stability = evaluate_stability_gate(
        score_history,
        expected_particle_count=args.particle_count,
    )
    conformance = ALGORITHM_CONFORMANCE[args.solver_id]
    status = (
        "excluded_algorithm_conformance"
        if not conformance["ranking_eligible"]
        else "failed_numeric_stability"
        if not stability["passed"]
        else "performance_valid_quality_candidate"
        if bool(quality["numeric_passed"])
        else "performance_valid_quality_unqualified"
    )
    result: dict[str, Any] = {
        "schema": RUN_RESULT_SCHEMA,
        "status": status,
        "claim_boundary": (
            "experimental_newton_only_lane;not_formal_isaac41_evidence;"
            "visual_review_required_before_ranking"
        ),
        "solver": {
            "solver_id": spec.solver_id,
            "display_name": spec.display_name,
            "family": spec.family,
            "implementation": spec.implementation,
            "origin": spec.origin,
            "algorithm_conformance": conformance,
        },
        "robot_lane": args.robot_lane,
        "particle_count": args.particle_count,
        "particle_radius_m": float(adapter_kwargs["particle_radius_m"]),
        "observation_count": args.max_observations,
        "parameters": parameters,
        "trajectory": trajectory_record,
        "timing": {
            "cold_setup_ms": cold_setup_ms,
            "cold_first_logical_step_ms": cold_step_ms,
            "cold_first_step_internal": cold_diagnostics.timings_ms,
            "steady_setup_ms": steady_setup_ms,
            "physics_logical_frame": summarize_milliseconds(physics_times_ms),
            "particle_readback": summarize_milliseconds(readback_times_ms),
            "quality_scoring": summarize_milliseconds(score_times_ms),
            "host_runtime_update": (
                summarize_milliseconds(host_update_times_ms)
                if host_update_times_ms
                else None
            ),
            "host_usd_particle_authoring": (
                summarize_milliseconds(host_usd_authoring_times_ms)
                if host_usd_authoring_times_ms
                else None
            ),
            "simulation_chain_frame": summarize_milliseconds(
                simulation_chain_times_ms
            ),
            "render_bridge": (
                {
                    "sample_policy": "observation_0_cold_excluded_from_official_fps",
                    "artifact_ready_all": summarize_milliseconds(
                        render_artifact_ready_times_ms
                    ),
                    "artifact_ready_steady": summarize_milliseconds(
                        render_artifact_ready_times_ms[1:]
                        if len(render_artifact_ready_times_ms) > 1
                        else render_artifact_ready_times_ms
                    ),
                    "artifact_ready_fps": 1000.0
                    / float(
                        np.mean(
                            render_artifact_ready_times_ms[1:]
                            if len(render_artifact_ready_times_ms) > 1
                            else render_artifact_ready_times_ms
                        )
                    ),
                    "surface_reconstruction": (
                        summarize_milliseconds(render_surface_reconstruction_times_ms[1:])
                        if len(render_surface_reconstruction_times_ms) > 1
                        else summarize_milliseconds(render_surface_reconstruction_times_ms)
                        if render_surface_reconstruction_times_ms
                        else None
                    ),
                    "surface_mesh_readback": (
                        summarize_milliseconds(render_surface_readback_times_ms[1:])
                        if len(render_surface_readback_times_ms) > 1
                        else summarize_milliseconds(render_surface_readback_times_ms)
                        if render_surface_readback_times_ms
                        else None
                    ),
                    "handoff_to_rgb_ack": summarize_milliseconds(
                        render_handoff_to_rgb_ack_times_ms[1:]
                        if len(render_handoff_to_rgb_ack_times_ms) > 1
                        else render_handoff_to_rgb_ack_times_ms
                    ),
                }
                if render_artifact_ready_times_ms
                else None
            ),
            "internal_stage_profile": {
                name: summarize_milliseconds(values)
                for name, values in sorted(internal_timing_history.items())
            },
        },
        "diagnostic_counters": {
            name: {
                "count": len(values),
                "total": int(sum(values)),
                "maximum_per_frame": int(max(values, default=0)),
                "mean_per_frame": float(np.mean(values)) if values else 0.0,
            }
            for name, values in sorted(diagnostic_counter_history.items())
        },
        "adaptive_integration": {
            "minimum_substeps": min(substeps),
            "maximum_substeps": max(substeps),
            "mean_substeps": float(np.mean(substeps)),
            "maximum_speed_m_s": _summarize_values(maximum_speeds_m_s),
            "actual_iteration_count": _summarize_values(actual_iterations)
            if actual_iterations
            else None,
            "final_residual": _summarize_values(residuals) if residuals else None,
        },
        "stability": stability,
        "quality": quality,
        "quality_diagnostics": quality_diagnostics,
        "host_runtime_update": args.host_runtime_update,
        "host_particle_bridge": host_bridge_record,
        "render_bridge": (
            {
                "schema": RENDER_BRIDGE_SCHEMA,
                "representation": args.render_representation,
                "camera_rgb_ack_required": True,
                "surface_parameters": (
                    {
                        "bounds_lower_m": render_lower.tolist(),
                        "bounds_upper_m": render_upper.tolist(),
                        "voxel_size_m": args.render_voxel_size_m,
                        "support_radius_m": args.render_support_radius_m,
                        "threshold": args.render_surface_threshold,
                    }
                    if args.render_representation == "surface_gpu"
                    else None
                ),
                "mesh_sizes": render_mesh_sizes or None,
            }
            if args.render_bridge_socket is not None
            else None
        ),
        "packet": {
            "path": str(packet.manifest_path),
            "sha256": sha256_file(packet.manifest_path),
        },
        "runtime": _runtime_record(args),
        "artifacts": {
            "review_particle_frames": {
                "path": str(review_path),
                "sha256": sha256_file(review_path),
            },
            "score_history": {
                "path": str(score_path),
                "sha256": sha256_file(score_path),
            },
            "all_particle_frames": (
                {
                    "path": str(all_frames_path),
                    "sha256": sha256_file(all_frames_path),
                }
                if all_frames_path is not None
                else None
            ),
            "render_bridge_timings": (
                {
                    "path": str(render_timing_path),
                    "sha256": sha256_file(render_timing_path),
                }
                if render_timing_path is not None
                else None
            ),
        },
        "started_wall_s": started_wall_s,
        "finished_wall_s": time.time(),
    }
    result["content_sha256"] = _sha256_json(result)
    _atomic_json(args.output_dir / "result.json", result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver-id", required=True)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--particle-count", type=int, choices=(900, 1800, 3600, 7200), default=3600)
    parser.add_argument("--max-observations", type=int, default=EXPECTED_OBSERVATION_COUNT)
    parser.add_argument("--warmup-observations", type=int, default=2)
    parser.add_argument("--robot-lane", choices=ROBOT_LANES, default="kinematic_replay")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--parameters-json", default="{}")
    parser.add_argument("--trajectory-npz", type=Path)
    parser.add_argument(
        "--runtime-claim",
        default="unattested_runtime_forbidden_for_published_performance",
    )
    parser.add_argument("--runtime-receipt", type=Path)
    parser.add_argument("--capture-all-particle-frames", action="store_true")
    parser.add_argument(
        "--host-runtime-update",
        choices=("none", "isaac_kit", "isaac_kit_particles"),
        default="none",
        help="Optional same-process Kit update, with or without timed USD Points authoring.",
    )
    parser.add_argument("--render-bridge-socket", type=Path)
    parser.add_argument("--render-shared-memory-name")
    parser.add_argument(
        "--render-representation", choices=("particles", "surface_gpu")
    )
    parser.add_argument("--render-bridge-timeout-s", type=float, default=300.0)
    parser.add_argument("--render-voxel-size-m", type=float, default=0.003)
    parser.add_argument("--render-support-radius-m", type=float, default=0.006)
    parser.add_argument("--render-surface-threshold", type=float, default=0.45)
    parser.add_argument(
        "--render-bounds-lower", nargs=3, type=float, default=(0.15, -0.38, 0.76)
    )
    parser.add_argument(
        "--render-bounds-upper", nargs=3, type=float, default=(0.43, 0.18, 1.34)
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.packet = args.packet.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.render_bridge_socket is not None:
        args.render_bridge_socket = args.render_bridge_socket.resolve()
    if (args.render_bridge_socket is None) != (
        args.render_shared_memory_name is None
    ):
        parser.error("render bridge socket and shared-memory name must be provided together")
    if args.max_observations < 1 or args.max_observations > EXPECTED_OBSERVATION_COUNT:
        parser.error("--max-observations out of range")
    try:
        parsed_parameters = json.loads(args.parameters_json)
        if not isinstance(parsed_parameters, Mapping):
            raise ValueError("parameters_not_object")
        args.parameters = dict(parsed_parameters)
    except (json.JSONDecodeError, ValueError) as error:
        parser.error(f"invalid --parameters-json: {error}")
    try:
        result = run(args)
    except SolverCapabilityError as error:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "schema": RUN_RESULT_SCHEMA,
            "status": "failed_capability",
            "solver_id": args.solver_id,
            "robot_lane": args.robot_lane,
            "message": str(error),
            "runtime": {"executable": sys.executable, "prefix": sys.prefix},
        }
        _atomic_json(args.output_dir / "result.json", failure)
        print(json.dumps(failure, sort_keys=True), flush=True)
        return 3
    except BaseException as error:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "schema": RUN_RESULT_SCHEMA,
            "status": "failed_runtime",
            "solver_id": args.solver_id,
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "runtime": {"executable": sys.executable, "prefix": sys.prefix},
        }
        _atomic_json(args.output_dir / "result.json", failure)
        print(json.dumps({key: value for key, value in failure.items() if key != "traceback"}, sort_keys=True), flush=True)
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "result": str(args.output_dir / "result.json"),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
