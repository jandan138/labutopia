#!/usr/bin/env python3
"""Benchmark Newton particle/surface rendering without importing Isaac Sim.

The input is a retained particle-frame NPZ produced by a solver run.  Physics
time is deliberately not mixed with reconstruction, upload, render submission,
or RGB readback time.  ViewerRTX fails closed on the known incompatible driver
interval used by this DSW machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_benchmark_contract import (  # noqa: E402
    load_packet,
    sha256_file,
    summarize_milliseconds,
)
from tools.labutopia_fluid.newton_only_contract import (  # noqa: E402
    VISUAL_REVIEW_FRAME_INDICES,
)
from tools.labutopia_fluid.warp_surface_reconstruction import (  # noqa: E402
    WarpSurfaceReconstructor,
)


DEFAULT_PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)
BLOCKED_RTX_DRIVER_LOWER = (570, 0, 0)
BLOCKED_RTX_DRIVER_UPPER = (570, 158, 1)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _cold_and_steady(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        raise ValueError("render_timing_values_empty")
    return {
        "cold_first_ms": float(values[0]),
        "steady_after_first": (
            summarize_milliseconds(values[1:]) if len(values) > 1 else None
        ),
        "all_samples": summarize_milliseconds(values),
    }


def _driver_version() -> tuple[str, tuple[int, int, int]]:
    text = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=driver_version",
            "--format=csv,noheader",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.splitlines()[0].strip()
    values = tuple(int(value) for value in text.split("."))
    padded = (values + (0, 0, 0))[:3]
    return text, padded


def _encode_video(frame_dir: Path, output_path: Path, fps: int) -> dict[str, Any]:
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-i",
        str(frame_dir / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg_failed:{completed.stderr.strip()}")
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries", "stream=codec_name,pix_fmt,width,height,r_frame_rate,nb_read_frames",
            "-of", "json", str(output_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    return {
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "size_bytes": output_path.stat().st_size,
        "crf": 20,
        "codec_name": stream.get("codec_name"),
        "pixel_format": stream.get("pix_fmt"),
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "frame_rate": stream.get("r_frame_rate"),
        "decoded_frame_count": int(stream.get("nb_read_frames", 0)),
    }


def _runtime_record(args: argparse.Namespace) -> dict[str, Any]:
    if args.runtime_receipt is None:
        return {
            "authoritative": False,
            "executable": sys.executable,
            "prefix": sys.prefix,
            "reason": args.runtime_claim,
        }
    path = args.runtime_receipt.resolve(strict=True)
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("schema") != "labutopia.newton_only_runtime_attestation.v1"
        or value.get("status") != "matched_experimental_runtime"
        or value.get("executable") != sys.executable
        or Path(value.get("prefix", "")).resolve(strict=True)
        != Path(sys.prefix).resolve(strict=True)
    ):
        raise RuntimeError("newton_runtime_receipt_mismatch")
    return {
        "authoritative": True,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "receipt_path": str(path),
        "receipt_sha256": sha256_file(path),
        "receipt_content_sha256": value["content_sha256"],
    }


def _cpu_surface(
    positions: np.ndarray,
    *,
    lower: np.ndarray,
    upper: np.ndarray,
    voxel_size_m: float,
    support_radius_m: float,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    from scipy.ndimage import gaussian_filter
    from skimage.measure import marching_cubes

    shape = tuple(
        int(math.ceil(float(upper[axis] - lower[axis]) / voxel_size_m)) + 1
        for axis in range(3)
    )
    if any(value < 2 or value > 384 for value in shape):
        raise ValueError(f"cpu_surface_grid_shape_invalid:{shape}")
    started = time.perf_counter()
    grid = np.zeros(shape, dtype=np.float32)
    indices = np.rint((positions - lower) / voxel_size_m).astype(np.int64)
    valid = np.all((indices >= 0) & (indices < np.asarray(shape)), axis=1)
    np.add.at(grid, tuple(indices[valid].T), 1.0)
    sigma = max(0.5, support_radius_m / voxel_size_m / 2.0)
    field = gaussian_filter(grid, sigma=sigma, mode="constant")
    maximum = float(field.max(initial=0.0))
    if maximum <= 0.0:
        raise ValueError("cpu_surface_field_empty")
    level = maximum * 0.18
    vertices, faces, _, _ = marching_cubes(
        field,
        level=level,
        spacing=(voxel_size_m, voxel_size_m, voxel_size_m),
    )
    vertices = vertices.astype(np.float32, copy=False) + lower
    faces = faces.astype(np.int32, copy=False).reshape(-1)
    return vertices, faces, {
        "total_ms": (time.perf_counter() - started) * 1000.0,
        "grid_shape": list(shape),
        "threshold": level,
        "vertex_count": int(vertices.shape[0]),
        "triangle_count": int(faces.size // 3),
    }


def _camera_record(scene_pack: Mapping[str, Any] | None, camera_id: str) -> dict[str, Any]:
    if scene_pack is not None:
        camera = scene_pack.get("cameras", {}).get(camera_id)
        if not isinstance(camera, Mapping):
            raise ValueError(f"scene_pack_camera_missing:{camera_id}")
        matrix = np.asarray(camera["camera_to_world_row_matrix"], dtype=np.float64)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
            raise ValueError(f"scene_pack_camera_matrix_invalid:{camera_id}")
        position = matrix[3, :3]
        optical_axis = -matrix[2, :3]
        return {
            "camera_id": camera_id,
            "position": position.tolist(),
            "target": (position + optical_axis).tolist(),
            "source": "formal_scene_pack_usd_camera",
        }
    proxies = {
        "front": ([0.82, 0.34, 1.28], [0.28, -0.08, 0.92]),
        "wrist": ([0.05, 0.16, 1.18], [0.28, -0.08, 0.92]),
    }
    position, target = proxies[camera_id]
    return {
        "camera_id": camera_id,
        "position": position,
        "target": target,
        "source": "nonformal_deterministic_proxy_no_scene_pack",
    }


def _line_circle(
    center: np.ndarray, radius: float, z_offset: float, segments: int = 64
) -> tuple[np.ndarray, np.ndarray]:
    angles = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    points = np.column_stack(
        (
            center[0] + radius * np.cos(angles),
            center[1] + radius * np.sin(angles),
            np.full(segments, center[2] + z_offset),
        )
    ).astype(np.float32)
    return points, np.roll(points, -1, axis=0)


def _render_viewergl(args: argparse.Namespace) -> dict[str, Any]:
    os.environ.setdefault("PYGLET_HEADLESS", "1")
    import newton
    import warp as wp
    from PIL import Image

    packet = load_packet(args.packet)
    with np.load(args.particle_frames, allow_pickle=False) as archive:
        if set(archive.files) != {"observation_indices", "particle_positions"}:
            raise ValueError("particle_frame_archive_fields_invalid")
        observation_indices = np.asarray(archive["observation_indices"], dtype=np.int32)
        frames = np.asarray(archive["particle_positions"], dtype=np.float32)
    if (
        frames.ndim != 3
        or frames.shape[0] != observation_indices.size
        or frames.shape[2] != 3
        or not np.isfinite(frames).all()
    ):
        raise ValueError("particle_frame_archive_values_invalid")
    stop_frame = (
        len(frames)
        if args.max_frames is None
        else args.start_frame + args.max_frames
    )
    if args.start_frame >= len(frames) or stop_frame > len(frames):
        raise ValueError("requested_frame_span_out_of_range")
    frames = frames[args.start_frame:stop_frame]
    observation_indices = observation_indices[args.start_frame:stop_frame]

    scene_pack = (
        json.loads(args.scene_pack.read_text(encoding="utf-8"))
        if args.scene_pack is not None
        else None
    )
    camera = _camera_record(scene_pack, args.camera_id)
    lower = np.asarray(args.bounds_lower, dtype=np.float32)
    upper = np.asarray(args.bounds_upper, dtype=np.float32)
    reconstructor = (
        WarpSurfaceReconstructor(
            bounds_lower_m=lower,
            bounds_upper_m=upper,
            voxel_size_m=args.voxel_size_m,
            support_radius_m=args.support_radius_m,
            threshold=args.gpu_surface_threshold,
            device=args.device,
        )
        if args.representation == "surface_gpu"
        else None
    )

    setup_started = time.perf_counter()
    viewer = newton.viewer.ViewerGL(
        width=args.width,
        height=args.height,
        vsync=False,
        headless=True,
    )
    viewer.camera.pos = wp.vec3(*camera["position"])
    viewer.camera.look_at(wp.vec3(*camera["target"]))
    if hasattr(viewer.renderer, "exposure"):
        viewer.renderer.exposure = args.exposure
    setup_ms = (time.perf_counter() - setup_started) * 1000.0

    upload_times: list[float] = []
    reconstruction_times: list[float] = []
    render_times: list[float] = []
    readback_times: list[float] = []
    mesh_sizes: list[dict[str, int]] = []
    image_records: list[dict[str, Any]] = []
    residual_particle_counts: list[int] = []
    target_center = packet.array("target_frame_world_matrix", (4, 4))[3, :3]
    source_poses = packet.array("source_poses_xyzw", (953, 7))
    target_rim = float(packet.manifest["frames"]["target"]["rim_m"])
    target_radius = float(packet.manifest["frames"]["target"]["interior_radius_m"])
    image_dir = args.output_dir / "images"
    try:
        for frame_ordinal, (observation_index, positions) in enumerate(
            zip(observation_indices, frames, strict=True)
        ):
            upload_started = time.perf_counter()
            points = wp.array(positions, dtype=wp.vec3, device=args.device)
            wp.synchronize_device(args.device)
            upload_ms = (time.perf_counter() - upload_started) * 1000.0
            upload_times.append(upload_ms)

            mesh_vertices = None
            mesh_indices = None
            if args.representation == "surface_gpu":
                surface = reconstructor.reconstruct(points)
                mesh_vertices = surface.vertices
                mesh_indices = surface.indices
                reconstruction_times.append(surface.timing_ms["total_ms"])
                mesh_sizes.append(
                    {
                        "vertex_count": int(surface.vertices.shape[0]),
                        "triangle_count": int(surface.indices.shape[0] // 3),
                    }
                )
            elif args.representation == "surface_cpu":
                vertices, indices, reconstruction = _cpu_surface(
                    positions,
                    lower=lower,
                    upper=upper,
                    voxel_size_m=args.voxel_size_m,
                    support_radius_m=args.support_radius_m,
                )
                reconstruction_times.append(float(reconstruction["total_ms"]))
                mesh_sizes.append(
                    {
                        "vertex_count": int(reconstruction["vertex_count"]),
                        "triangle_count": int(reconstruction["triangle_count"]),
                    }
                )
                mesh_upload_started = time.perf_counter()
                mesh_vertices = wp.array(vertices, dtype=wp.vec3, device=args.device)
                mesh_indices = wp.array(indices, dtype=wp.int32, device=args.device)
                wp.synchronize_device(args.device)
                upload_times[-1] += (time.perf_counter() - mesh_upload_started) * 1000.0

            render_started = time.perf_counter()
            viewer.begin_frame(float(observation_index) / 30.0)
            if args.representation == "particles":
                viewer.log_points(
                    "/fluid/particles",
                    points,
                    radii=args.particle_radius_m,
                    colors=wp.array(
                        np.tile(
                            np.asarray((0.08, 0.55, 0.95), dtype=np.float32),
                            (positions.shape[0], 1),
                        ),
                        dtype=wp.vec3,
                        device=args.device,
                    ),
                )
            else:
                # ViewerGL's MeshGL has a fixed vertex/index capacity.  Fluid
                # marching-cubes topology changes every frame, so replace the
                # prior mesh object before logging the next topology.
                for object_name in tuple(viewer.objects):
                    if (
                        object_name.endswith("/fluid/surface")
                        or object_name == "/fluid/surface"
                        or object_name.endswith("/fluid/residual_particles")
                        or object_name == "/fluid/residual_particles"
                    ):
                        del viewer.objects[object_name]
                viewer.log_mesh(
                    "/fluid/surface",
                    mesh_vertices,
                    mesh_indices,
                    color=(0.08, 0.55, 0.95),
                    roughness=0.18,
                    metallic=0.0,
                    backface_culling=False,
                )
                residual_mask = np.any(
                    (positions < lower) | (positions > upper), axis=1
                )
                residual_positions = np.ascontiguousarray(
                    positions[residual_mask], dtype=np.float32
                )
                residual_particle_counts.append(int(len(residual_positions)))
                if len(residual_positions):
                    viewer.log_points(
                        "/fluid/residual_particles",
                        wp.array(residual_positions, dtype=wp.vec3, device=args.device),
                        radii=args.particle_radius_m,
                        colors=wp.array(
                            np.tile(
                                np.asarray((0.14, 0.78, 0.96), dtype=np.float32),
                                (len(residual_positions), 1),
                            ),
                            dtype=wp.vec3,
                            device=args.device,
                        ),
                    )
            source_center = source_poses[int(observation_index), :3]
            for name, center, radius, height, color in (
                (
                    "source",
                    source_center,
                    float(packet.manifest["frames"]["source"]["interior_radius_m"]),
                    float(packet.manifest["frames"]["source"]["rim_m"]),
                    (0.85, 0.72, 0.30),
                ),
                ("target", target_center, target_radius, target_rim, (0.30, 0.85, 0.58)),
            ):
                starts, ends = _line_circle(np.asarray(center), radius, height)
                viewer.log_lines(
                    f"/vessels/{name}_rim",
                    wp.array(starts, dtype=wp.vec3, device=args.device),
                    wp.array(ends, dtype=wp.vec3, device=args.device),
                    colors=wp.array(
                        np.tile(np.asarray(color, dtype=np.float32), (starts.shape[0], 1)),
                        dtype=wp.vec3,
                        device=args.device,
                    ),
                    width=0.003,
                )
            viewer.end_frame()
            wp.synchronize_device(args.device)
            render_times.append((time.perf_counter() - render_started) * 1000.0)

            readback_started = time.perf_counter()
            frame = viewer.get_frame(render_ui=False)
            rgb = frame.numpy() if hasattr(frame, "numpy") else np.asarray(frame)
            readback_times.append((time.perf_counter() - readback_started) * 1000.0)
            if rgb.shape[:2] != (args.height, args.width):
                raise RuntimeError(f"viewergl_frame_shape_invalid:{rgb.shape}")
            should_save = args.save_all_images or int(observation_index) in {
                *VISUAL_REVIEW_FRAME_INDICES,
                int(observation_indices[0]),
                int(observation_indices[-1]),
            }
            if should_save:
                image_dir.mkdir(parents=True, exist_ok=True)
                path = (
                    image_dir / f"frame_{frame_ordinal:04d}.png"
                    if args.save_all_images
                    else image_dir / f"{frame_ordinal:04d}_obs_{int(observation_index):04d}.png"
                )
                image = rgb[..., :3].astype(np.uint8, copy=False)
                Image.fromarray(image).save(path)
                image_records.append(
                    {
                        "observation_index": int(observation_index),
                        "path": str(path),
                        "sha256": sha256_file(path),
                    }
                )
    finally:
        viewer.close()

    total = [
        upload + reconstruction + render + readback
        for upload, reconstruction, render, readback in zip(
            upload_times,
            reconstruction_times or [0.0] * len(upload_times),
            render_times,
            readback_times,
            strict=True,
        )
    ]
    video = None
    if args.video_output is not None:
        if not args.save_all_images:
            raise ValueError("video_output_requires_save_all_images")
        args.video_output.parent.mkdir(parents=True, exist_ok=True)
        video = _encode_video(image_dir, args.video_output, args.video_fps)
        if video["decoded_frame_count"] != int(frames.shape[0]):
            raise RuntimeError("encoded_video_frame_count_mismatch")
    return {
        "status": "completed",
        "backend": "viewergl",
        "headless": True,
        "representation": args.representation,
        "camera": camera,
        "frame_count": int(frames.shape[0]),
        "observation_index_span": [
            int(observation_indices[0]),
            int(observation_indices[-1]),
        ],
        "particle_count": int(frames.shape[1]),
        "timing": {
            "sample_policy": (
                "first_frame_is_cold_and_reported_separately;"
                "steady_after_first_excludes_first_frame"
            ),
            "viewer_setup_ms": setup_ms,
            "particle_and_mesh_upload": _cold_and_steady(upload_times),
            "surface_reconstruction": (
                _cold_and_steady(reconstruction_times)
                if reconstruction_times
                else None
            ),
            "render_submit_and_gpu_complete": _cold_and_steady(render_times),
            "rgb_readback": _cold_and_steady(readback_times),
            "headless_rgb_artifact_ready": _cold_and_steady(total),
        },
        "mesh_sizes": mesh_sizes or None,
        "surface_residual_particles": (
            None
            if args.representation == "particles"
            else {
                "policy": "particles_outside_reconstruction_bounds_are_rendered_as_points",
                "maximum_count": max(residual_particle_counts, default=0),
            }
        ),
        "images": image_records,
        "video": video,
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.output_dir.exists():
        raise FileExistsError(f"output_dir_exists:{args.output_dir}")
    args.output_dir.mkdir(parents=True)
    driver_text, driver = _driver_version()
    common = {
        "schema": "labutopia.newton_only_render_benchmark.v1",
        "claim_boundary": (
            "experimental_newton_only_render_lane;physics_time_excluded;"
            "formal_scene_camera_required_for_comparable_visual_claim"
        ),
        "runtime": _runtime_record(args),
        "driver_version": driver_text,
        "input": {
            "particle_frames_path": str(args.particle_frames),
            "particle_frames_sha256": sha256_file(args.particle_frames),
            "packet_path": str(args.packet),
            "packet_sha256": sha256_file(args.packet),
            "scene_pack_path": str(args.scene_pack) if args.scene_pack else None,
            "scene_pack_sha256": sha256_file(args.scene_pack) if args.scene_pack else None,
        },
    }
    if args.backend == "viewerrtx" and BLOCKED_RTX_DRIVER_LOWER <= driver < BLOCKED_RTX_DRIVER_UPPER:
        result = {
            **common,
            "status": "blocked_infrastructure",
            "backend": "viewerrtx",
            "headless": True,
            "reason": "driver_in_reviewed_newton_viewerrtx_blocked_interval",
            "blocked_interval": {"lower_inclusive": "570.00", "upper_exclusive": "570.158.01"},
            "performance_claim_generated": False,
        }
        _atomic_json(args.output_dir / "result.json", result)
        return result, 2
    if args.backend == "viewerrtx":
        result = {
            **common,
            "status": "blocked_capability",
            "backend": "viewerrtx",
            "headless": True,
            "reason": "dedicated_locked_rtx_environment_not_available",
            "performance_claim_generated": False,
        }
        _atomic_json(args.output_dir / "result.json", result)
        return result, 2
    measured = _render_viewergl(args)
    result = {**common, **measured}
    result["content_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _atomic_json(args.output_dir / "result.json", result)
    return result, 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--particle-frames", type=Path, required=True)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--scene-pack", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--backend", choices=("viewergl", "viewerrtx"), required=True)
    parser.add_argument(
        "--representation",
        choices=("particles", "surface_cpu", "surface_gpu"),
        required=True,
    )
    parser.add_argument("--camera-id", choices=("front", "wrist"), default="front")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--particle-radius-m", type=float, default=0.0023811016)
    parser.add_argument("--voxel-size-m", type=float, default=0.006)
    parser.add_argument("--support-radius-m", type=float, default=0.012)
    parser.add_argument("--gpu-surface-threshold", type=float, default=0.45)
    parser.add_argument("--exposure", type=float, default=1.35)
    parser.add_argument("--bounds-lower", nargs=3, type=float, default=(0.15, -0.38, 0.76))
    parser.add_argument("--bounds-upper", nargs=3, type=float, default=(0.43, 0.18, 1.34))
    parser.add_argument("--save-all-images", action="store_true")
    parser.add_argument("--video-output", type=Path)
    parser.add_argument("--video-fps", type=int, default=30)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--runtime-receipt", type=Path)
    parser.add_argument("--runtime-claim", default="unattested_nonformal_render_smoke")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for name in (
        "particle_frames", "packet", "output_dir", "scene_pack", "runtime_receipt", "video_output"
    ):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve())
    if args.width < 32 or args.height < 32:
        parser.error("render resolution too small")
    if args.video_fps < 1:
        parser.error("video fps must be positive")
    if args.start_frame < 0:
        parser.error("start frame must be nonnegative")
    if args.max_frames is not None and args.max_frames < 1:
        parser.error("max frames must be positive")
    result, exit_code = run(args)
    print(
        json.dumps(
            {"status": result["status"], "result": str(args.output_dir / "result.json")},
            sort_keys=True,
        ),
        flush=True,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
