#!/usr/bin/env python3
"""Formal Isaac Sim 4.1 benchmark for the colleague liquid_0812 fast USD."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import statistics
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
DEFAULT_SCENE = REPO_ROOT / "inputs/usd/scene/liquid_0812/test.usd"
DEFAULT_VIDEO_REFERENCE = (
    REPO_ROOT / "inputs/usd/scene/liquid_0812/20260812-154211.mp4"
)
DEFAULT_PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)
PARTICLE_SET_PATH = "/World/ParticleSet"
PARTICLE_SYSTEM_PATH = "/World/ParticleSystem"
PHYSICS_SCENE_PATH = "/World/PhysicsScene"
SOURCE_PATH = "/World/beaker2"
TARGET_PATH = "/World/beaker1"
CAMERA_PATH = "/OmniverseKit_Persp"
EXPECTED_PARTICLE_COUNT = 548
EXPECTED_OBSERVATIONS = 953
PHYSICS_HZ = 30
PHYSICS_DT = 1.0 / PHYSICS_HZ
STATIC_HOLD_SECONDS = 8
STATIC_HOLD_STEPS = PHYSICS_HZ * STATIC_HOLD_SECONDS
REVIEW_INDICES = frozenset({0, 300, 450, 580, 650, 750, 852, 952})


def source_paths() -> tuple[Path, ...]:
    return (
        REPO_ROOT / "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        Path(__file__).resolve(),
        REPO_ROOT / "tools/labutopia_fluid/fluid_benchmark_contract.py",
        REPO_ROOT
        / "tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py",
        REPO_ROOT / "tools/labutopia_fluid/run_interndata_online_surface_probe.py",
        REPO_ROOT / "utils/online_fluid_surface.py",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _pose_matrix_xyzw(np: Any, pose: Any) -> Any:
    from scipy.spatial.transform import Rotation

    value = np.asarray(pose, dtype=np.float64)
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = Rotation.from_quat(value[3:]).as_matrix().T
    matrix[3, :3] = value[:3]
    return matrix


def _matrix_pose_xyzw(np: Any, matrix: Any) -> Any:
    from scipy.spatial.transform import Rotation

    value = np.asarray(matrix, dtype=np.float64)
    pose = np.empty(7, dtype=np.float64)
    pose[:3] = value[3, :3]
    pose[3:] = Rotation.from_matrix(value[:3, :3].T).as_quat()
    return pose.astype(np.float32)


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _gpu_snapshot() -> dict[str, Any]:
    gpu = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=timestamp,index,name,driver_version,memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    processes = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    rows = []
    for line in gpu.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 7:
            continue
        rows.append(
            {
                "timestamp": parts[0],
                "index": int(parts[1]),
                "name": parts[2],
                "driver_version": parts[3],
                "memory_used_mib": float(parts[4]),
                "memory_total_mib": float(parts[5]),
                "utilization_percent": float(parts[6]),
            }
        )
    process_rows = []
    for line in processes.stdout.splitlines():
        parts = [part.strip() for part in line.split(",", 2)]
        if len(parts) != 3:
            continue
        process_rows.append(
            {"pid": int(parts[0]), "process_name": parts[1], "used_memory_mib": float(parts[2])}
        )
    return {
        "gpu_returncode": gpu.returncode,
        "process_returncode": processes.returncode,
        "gpus": rows,
        "compute_processes": process_rows,
    }


def _sample_gpu(seconds: int = 10) -> dict[str, Any]:
    samples = []
    for index in range(seconds):
        samples.append(_gpu_snapshot())
        if index + 1 < seconds:
            time.sleep(1.0)
    utilizations = [
        float(gpu["utilization_percent"])
        for sample in samples
        for gpu in sample.get("gpus", [])
    ]
    return {
        "duration_seconds": seconds,
        "samples": samples,
        "maximum_utilization_percent": max(utilizations) if utilizations else None,
        "mean_utilization_percent": statistics.fmean(utilizations) if utilizations else None,
        "idle_enough": bool(utilizations) and max(utilizations) <= 20.0,
    }


def _asset_configuration(stage: Any) -> dict[str, Any]:
    particle_set = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    particle_system = stage.GetPrimAtPath(PARTICLE_SYSTEM_PATH)
    physics_scene = stage.GetPrimAtPath(PHYSICS_SCENE_PATH)
    if not all(prim and prim.IsValid() for prim in (particle_set, particle_system, physics_scene)):
        raise RuntimeError("liquid0812_required_prim_missing")
    points = particle_set.GetAttribute("points").Get()
    records = {}
    for path in (f"{TARGET_PATH}/mesh", f"{SOURCE_PATH}/mesh"):
        prim = stage.GetPrimAtPath(path)
        records[path] = {
            "approximation": prim.GetAttribute("physics:approximation").Get(),
            "collision_enabled": bool(prim.GetAttribute("physics:collisionEnabled").Get()),
            "contact_offset_m": float(prim.GetAttribute("physxCollision:contactOffset").Get()),
            "rest_offset_m": float(prim.GetAttribute("physxCollision:restOffset").Get()),
            "decomposition_error_percentage": float(
                prim.GetAttribute("physxConvexDecompositionCollision:errorPercentage").Get()
            ),
        }
    return {
        "particle_set_path": PARTICLE_SET_PATH,
        "particle_system_path": PARTICLE_SYSTEM_PATH,
        "particle_count": len(points),
        "particle_contact_offset_m": float(
            particle_system.GetAttribute("particleContactOffset").Get()
        ),
        "non_particle_rest_offset_m": float(particle_system.GetAttribute("restOffset").Get()),
        "solver_position_iteration_count": int(
            particle_system.GetAttribute("solverPositionIterationCount").Get()
        ),
        "isosurface_enabled": bool(
            particle_system.GetAttribute("physxParticleIsosurface:isosurfaceEnabled").Get()
        ),
        "authored_physics_hz": int(
            physics_scene.GetAttribute("physxScene:timeStepsPerSecond").Get()
        ),
        "beaker_colliders": records,
        "invalid_decomposition_error_percentage": any(
            record["decomposition_error_percentage"] < 0.01
            or record["decomposition_error_percentage"] > 25.0
            for record in records.values()
        ),
    }


def _configure_runtime_settings() -> None:
    import carb
    import omni.physx.bindings._physx as pb

    settings = carb.settings.get_settings()
    settings.set(pb.SETTING_UPDATE_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
    settings.set_bool(pb.SETTING_SUPPRESS_READBACK, False)
    settings.set_bool("/physics/suppressReadback", False)


def _open_stage(args: argparse.Namespace, application: Any) -> tuple[Any, dict[str, Any]]:
    import omni.usd

    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
        _configure_physics_scene_for_pbd,
    )

    context = omni.usd.get_context()
    if not context.open_stage(str(args.scene)):
        raise RuntimeError("liquid0812_stage_open_failed")
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("liquid0812_stage_missing")
    stage.SetEditTarget(stage.GetRootLayer())
    physics_settings = _configure_physics_scene_for_pbd(
        stage,
        PHYSICS_SCENE_PATH,
        integration_dt=PHYSICS_DT,
        strict_mode=True,
    )
    source_prim = stage.GetPrimAtPath(SOURCE_PATH)
    source_body_contract = {
        "applied_schemas": list(source_prim.GetAppliedSchemas()),
        "rigid_body_enabled": source_prim.GetAttribute("physics:rigidBodyEnabled").Get(),
        "kinematic_enabled": source_prim.GetAttribute("physics:kinematicEnabled").Get(),
        "runtime_schema_edits": False,
        "motion_compatibility": "author_existing_xformOp_transform_then_flush_physx_changes",
    }
    for _ in range(args.stage_warmup_updates):
        application.update()
    return stage, {
        "physics_settings": physics_settings,
        "asset_configuration": _asset_configuration(stage),
        "source_body_contract": source_body_contract,
    }


def _attach_stepper_and_source(stage: Any) -> tuple[Any, Any, Any, Any]:
    import numpy as np
    import omni.physics.tensors
    import omni.physx
    from pxr import UsdUtils

    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
        StrictPhysicsStepper,
    )

    stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
    stepper = StrictPhysicsStepper.attach(
        interface=omni.physx.get_physx_simulation_interface(),
        logical_dt=PHYSICS_DT,
        integration_dt=PHYSICS_DT,
        substeps_per_logical_step=1,
        stage_id=stage_id,
    )
    tensor_simulation = omni.physics.tensors.create_simulation_view("numpy", stage_id)
    source_view = tensor_simulation.create_rigid_body_view(SOURCE_PATH)
    if source_view.count != 1:
        raise RuntimeError(f"liquid0812_source_view_count:{source_view.count}")
    source_indices = np.asarray([0], dtype=np.uint32)
    initial_pose = np.asarray(source_view.get_transforms(), dtype=np.float64).reshape((-1, 7))[0]
    return stepper, source_view, source_indices, initial_pose


def _source_usd_matrix(stage: Any) -> tuple[Any, float | None, list[float]]:
    import numpy as np
    from pxr import UsdGeom

    source = stage.GetPrimAtPath(SOURCE_PATH)
    attribute = source.GetAttribute("xformOp:transform")
    samples = [float(value) for value in attribute.GetTimeSamples()]
    time_code = samples[0] if samples else None
    value = attribute.Get(time_code) if time_code is not None else attribute.Get()
    if value is None:
        value = UsdGeom.Xformable(source).GetLocalTransformation()
    return (
        np.asarray([list(row) for row in value], dtype=np.float64),
        time_code,
        samples,
    )


def _set_source_usd_matrix(
    stage: Any,
    matrix_value: Any,
    time_code: float | None,
    simulation: Any,
) -> None:
    import numpy as np
    from pxr import Gf, Usd

    source = stage.GetPrimAtPath(SOURCE_PATH)
    matrix = source.GetAttribute("xformOp:transform")
    if matrix:
        value = Gf.Matrix4d(*matrix_value.reshape(-1).tolist())
        if time_code is None:
            matrix.Set(value)
        else:
            matrix.Set(value, Usd.TimeCode(time_code))
    else:
        translate = source.GetAttribute("xformOp:translate")
        orient = source.GetAttribute("xformOp:orient")
        if not translate or not orient:
            raise RuntimeError(
                "liquid0812_source_xform_ops_missing:"
                + ",".join(source.GetPropertyNames())
            )
        pose = _matrix_pose_xyzw(np, matrix_value)
        quaternion = (float(pose[6]), float(pose[3]), float(pose[4]), float(pose[5]))
        translation = Gf.Vec3d(*[float(value) for value in pose[:3]])
        rotation = (
            Gf.Quatf(*quaternion)
            if str(orient.GetTypeName()) == "quatf"
            else Gf.Quatd(*quaternion)
        )
        if time_code is None:
            translate.Set(translation)
            orient.Set(rotation)
        else:
            usd_time = Usd.TimeCode(time_code)
            translate.Set(translation, usd_time)
            orient.Set(rotation, usd_time)
    simulation.flush_changes()


def _read_positions(stage: Any) -> Any:
    import numpy as np

    prim = stage.GetPrimAtPath(PARTICLE_SET_PATH)
    for name in ("physxParticle:simulationPoints", "points"):
        attribute = prim.GetAttribute(name)
        value = attribute.Get() if attribute else None
        if value is None:
            continue
        positions = np.asarray(value, dtype=np.float32).reshape((-1, 3))
        if positions.shape != (EXPECTED_PARTICLE_COUNT, 3):
            raise RuntimeError(f"liquid0812_particle_shape:{name}:{positions.shape}")
        if not np.isfinite(positions).all():
            raise RuntimeError(f"liquid0812_particle_nonfinite:{name}")
        return positions.copy()
    raise RuntimeError(f"liquid0812_particle_positions_missing:{PARTICLE_SET_PATH}")


def _partition(
    positions: Any,
    *,
    packet: Any,
    source_frame_world: Any,
    observation_index: int,
) -> dict[str, Any]:
    from tools.labutopia_fluid.fluid_benchmark_contract import classify_positions

    source_frame = packet.manifest["frames"]["source"]
    target_frame = packet.manifest["frames"]["target"]
    score = classify_positions(
        positions,
        source_frame_world_matrix=source_frame_world,
        target_frame_world_matrix=packet.array("target_frame_world_matrix", (4, 4)),
        source_interior_radius_m=float(source_frame["interior_radius_m"]),
        target_interior_radius_m=float(target_frame["interior_radius_m"]),
        source_floor_m=float(source_frame["floor_m"]),
        source_rim_m=float(source_frame["rim_m"]),
        target_floor_m=float(target_frame["floor_m"]),
        target_rim_m=float(target_frame["rim_m"]),
        table_top_z_m=float(packet.manifest["frames"]["table_top_z_m"]),
    )
    score["observation_index"] = observation_index
    return score


def _run_static_hold(args: argparse.Namespace, application: Any, packet: Any) -> dict[str, Any]:
    import numpy as np

    stage, stage_record = _open_stage(args, application)
    stepper, source_view, source_indices, initial_pose = _attach_stepper_and_source(stage)
    source_frame_local = packet.array("source_frame_local_matrix", (4, 4))
    source_poses = packet.array("source_poses_xyzw", (EXPECTED_OBSERVATIONS, 7))
    initial_usd_matrix, source_matrix_time_code, source_matrix_time_samples = (
        _source_usd_matrix(stage)
    )
    timings = []
    scores = []
    try:
        for index in range(STATIC_HOLD_STEPS):
            started = time.perf_counter()
            stepper.step()
            positions = _read_positions(stage)
            timings.append((time.perf_counter() - started) * 1000.0)
            scores.append(
                _partition(
                    positions,
                    packet=packet,
                    source_frame_world=(
                        source_frame_local @ _pose_matrix_xyzw(np, source_poses[0])
                    ),
                    observation_index=index,
                )
            )
    finally:
        stepper.detach()
    initial = scores[0]
    final = scores[-1]
    maximum = {
        name: max(int(score[name]) for score in scores)
        for name in ("below_table", "nonfinite", "tabletop_spill", "transit")
    }
    minimum_source = min(int(score["source"]) for score in scores)
    passed = (
        maximum["below_table"] == 0
        and maximum["nonfinite"] == 0
        and minimum_source >= int(initial["source"])
        and all(int(score["particle_count"]) == EXPECTED_PARTICLE_COUNT for score in scores)
    )
    from tools.labutopia_fluid.fluid_benchmark_contract import summarize_milliseconds

    return {
        "status": "passed" if passed else "failed",
        "duration_s": STATIC_HOLD_SECONDS,
        "step_count": STATIC_HOLD_STEPS,
        "timing": summarize_milliseconds(timings[1:]),
        "initial_partition": initial,
        "final_partition": final,
        "minimum_source_count": minimum_source,
        "maximum_counts": maximum,
        "particle_count_conserved": all(
            int(score["particle_count"]) == EXPECTED_PARTICLE_COUNT for score in scores
        ),
        "source_pose_xyzw": initial_pose.tolist(),
        "source_usd_matrix": initial_usd_matrix.tolist(),
        "source_matrix_time_code": source_matrix_time_code,
        "source_matrix_time_samples": source_matrix_time_samples,
        "source_motion_driver": "none_static_hold",
        **stage_record,
    }


def _start_video(path: Path, width: int, height: int) -> subprocess.Popen[bytes]:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        "30",
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    return subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _run_pour(
    args: argparse.Namespace,
    application: Any,
    packet: Any,
    output_dir: Path,
) -> dict[str, Any]:
    import numpy as np
    import omni.physx

    from tools.labutopia_fluid.fluid_benchmark_contract import (
        evaluate_quality_gate,
        evaluate_stability_gate,
        interpolate_pose_xyzw,
        summarize_milliseconds,
    )

    stage, stage_record = _open_stage(args, application)
    stepper, source_view, source_indices, initial_source_pose = _attach_stepper_and_source(stage)
    source_poses = packet.array("source_poses_xyzw", (EXPECTED_OBSERVATIONS, 7))
    source_frame_local = packet.array("source_frame_local_matrix", (4, 4))
    initial_usd_matrix, source_matrix_time_code, source_matrix_time_samples = (
        _source_usd_matrix(stage)
    )
    usd_from_packet = initial_usd_matrix @ np.linalg.inv(
        _pose_matrix_xyzw(np, source_poses[0])
    )
    simulation = omni.physx.get_physx_simulation_interface()

    def usd_matrix_for_packet_pose(packet_pose: Any) -> Any:
        return usd_from_packet @ _pose_matrix_xyzw(np, packet_pose)

    rendered = args.mode == "headless-rendered"
    rep = None
    rgb = None
    product = None
    timeline = None
    if rendered:
        import omni.replicator.core as rep_module
        import omni.timeline

        if not stage.GetPrimAtPath(CAMERA_PATH).IsValid():
            raise RuntimeError(f"liquid0812_camera_missing:{CAMERA_PATH}")
        rep = rep_module
        timeline = omni.timeline.get_timeline_interface()
        timeline.stop()
        product = rep.create.render_product(CAMERA_PATH, (args.width, args.height))
        rgb = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb.attach(product)
        for _ in range(args.render_warmup_observations):
            rep.orchestrator.step(rt_subframes=1, pause_timeline=True, delta_time=0.0)
            rep.orchestrator.wait_until_complete()
            _ = np.asarray(rgb.get_data())

    video_path = output_dir / "liquid0812_headless_single_camera.mp4"
    video = _start_video(video_path, args.width, args.height) if rendered and args.save_video else None
    physics_ms = []
    score_ms = []
    render_ms = []
    capture_ms = []
    model_ready_ms = []
    scores = []
    frame_hashes = []
    records_path = output_dir / "observations.jsonl"
    records = records_path.open("xb")
    try:
        _set_source_usd_matrix(
            stage,
            usd_matrix_for_packet_pose(source_poses[0]),
            source_matrix_time_code,
            simulation,
        )
        stepper.step()
        initial_positions = _read_positions(stage)
        initial_position_hash = hashlib.sha256(
            np.ascontiguousarray(initial_positions, dtype="<f4").tobytes()
        ).hexdigest()
        for observation_index in range(args.max_observations):
            model_started = time.perf_counter()
            physics_started = time.perf_counter()
            previous_index = max(0, observation_index - 1)
            pose = interpolate_pose_xyzw(
                source_poses[previous_index], source_poses[observation_index], 1.0
            )
            actual_usd_matrix = usd_matrix_for_packet_pose(pose)
            _set_source_usd_matrix(
                stage,
                actual_usd_matrix,
                source_matrix_time_code,
                simulation,
            )
            stepper.step()
            positions = _read_positions(stage)
            physics_ms.append((time.perf_counter() - physics_started) * 1000.0)

            score_started = time.perf_counter()
            score = _partition(
                positions,
                packet=packet,
                source_frame_world=(
                    source_frame_local @ _pose_matrix_xyzw(np, source_poses[observation_index])
                ),
                observation_index=observation_index,
            )
            scores.append(score)
            score_ms.append((time.perf_counter() - score_started) * 1000.0)

            camera_hash = None
            frame = None
            if rendered:
                assert rep is not None and rgb is not None and timeline is not None
                render_started = time.perf_counter()
                before = float(timeline.get_current_time())
                rep.orchestrator.step(rt_subframes=1, pause_timeline=True, delta_time=0.0)
                rep.orchestrator.wait_until_complete()
                after = float(timeline.get_current_time())
                if abs(after - before) > 1.0e-12:
                    raise RuntimeError("liquid0812_render_advanced_timeline")
                render_ms.append((time.perf_counter() - render_started) * 1000.0)
                capture_started = time.perf_counter()
                raw = np.asarray(rgb.get_data())
                if raw.shape[:2] != (args.height, args.width):
                    raise RuntimeError(f"liquid0812_camera_shape:{raw.shape}")
                frame = np.ascontiguousarray(raw[..., :3], dtype=np.uint8)
                camera_hash = hashlib.sha256(frame.tobytes()).hexdigest()
                capture_ms.append((time.perf_counter() - capture_started) * 1000.0)
            model_ready_ms.append((time.perf_counter() - model_started) * 1000.0)

            if frame is not None:
                if video is not None:
                    assert video.stdin is not None
                    video.stdin.write(frame.tobytes())
                if observation_index in REVIEW_INDICES or observation_index + 1 == args.max_observations:
                    from PIL import Image

                    frame_path = output_dir / "review_frames" / f"frame_{observation_index:04d}.png"
                    frame_path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(frame, mode="RGB").save(frame_path)
                    frame_hashes.append(
                        {"observation_index": observation_index, **_file_record(frame_path)}
                    )
            records.write(
                (
                    json.dumps(
                        {"observation_index": observation_index, "score": score, "camera_sha256": camera_hash},
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n"
                ).encode("utf-8")
            )
    finally:
        records.close()
        stepper.detach()
        if video is not None:
            assert video.stdin is not None
            video.stdin.close()
            stderr = video.stderr.read().decode("utf-8", errors="replace") if video.stderr else ""
            returncode = video.wait()
            if returncode != 0:
                raise RuntimeError(f"liquid0812_ffmpeg_failed:{returncode}:{stderr[-1000:]}")
        if rgb is not None and product is not None:
            try:
                rgb.detach()
                product.destroy()
            except Exception:
                pass

    warm_slice = slice(1, None) if len(physics_ms) > 1 else slice(None)
    quality = evaluate_quality_gate(scores, visual_liquid_passed=None)
    stability = evaluate_stability_gate(scores, expected_particle_count=EXPECTED_PARTICLE_COUNT)
    timing = {
        "warmup_observations_excluded": 1 if len(physics_ms) > 1 else 0,
        "physics_per_observation": summarize_milliseconds(physics_ms[warm_slice]),
        "physics_only_fps": 1000.0 / statistics.fmean(physics_ms[warm_slice]),
        "score_per_observation": summarize_milliseconds(score_ms[warm_slice]),
        "rtx_render_per_observation": (
            summarize_milliseconds(render_ms[warm_slice]) if rendered else None
        ),
        "camera_capture_per_observation": (
            summarize_milliseconds(capture_ms[warm_slice]) if rendered else None
        ),
        "model_ready_per_observation": summarize_milliseconds(model_ready_ms[warm_slice]),
        "model_ready_fps": 1000.0 / statistics.fmean(model_ready_ms[warm_slice]),
    }
    final = scores[-1]
    separated_acceptance = {
        "penetration": {
            "passed": stability["checks"]["no_below_table_penetration"]
            and stability["checks"]["finite_positions"],
            "maximum_below_table_count": stability["maximum_below_table_count"],
            "maximum_nonfinite_count": stability["maximum_nonfinite_count"],
        },
        "tabletop_spill": {
            "passed": float(final["tabletop_spill_fraction"]) <= 0.02,
            "final_fraction": float(final["tabletop_spill_fraction"]),
            "threshold": 0.02,
        },
        "target_reception": {
            "passed": float(final["target_fraction"]) >= 0.90,
            "final_fraction": float(final["target_fraction"]),
            "threshold": 0.90,
        },
        "stable_tail": quality["checks"]["stable_tail"],
    }
    return {
        "status": "measured" if stability["passed"] else "failed_stability",
        "mode": args.mode,
        "particle_count": EXPECTED_PARTICLE_COUNT,
        "observation_count": args.max_observations,
        "physics_hz": PHYSICS_HZ,
        "physics_dt_s": PHYSICS_DT,
        "substeps_per_observation": 1,
        "trajectory": "fluid_benchmark_packet_v2_953_frame_pose_with_initial_rigid_alignment",
        "source_motion_driver": "USD_xformOp_transform_relative_trajectory_plus_PhysX_flush_changes",
        "initial_source_pose_xyzw": initial_source_pose.tolist(),
        "initial_source_usd_matrix": initial_usd_matrix.tolist(),
        "source_matrix_time_code": source_matrix_time_code,
        "source_matrix_time_samples": source_matrix_time_samples,
        "usd_from_packet_relation": usd_from_packet.tolist(),
        "initial_position_sha256": initial_position_hash,
        "timing": timing,
        "quality": quality,
        "stability": stability,
        "separated_acceptance": separated_acceptance,
        "stage": stage_record,
        "artifacts": {
            "observations": _file_record(records_path),
            "review_frames": frame_hashes,
            "video": _file_record(video_path) if video_path.is_file() else None,
        },
    }


def _run_benchmark(
    args: argparse.Namespace,
    *,
    application: Any,
    runtime_record: dict[str, Any],
) -> dict[str, Any]:
    from tools.labutopia_fluid.fluid_benchmark_contract import load_packet

    output_dir = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output_dir_not_empty:{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    packet = load_packet(args.packet)
    if args.max_observations < 1 or args.max_observations > EXPECTED_OBSERVATIONS:
        raise ValueError("max_observations_out_of_range")
    static_hold = _run_static_hold(args, application, packet) if args.mode == "physics-only" else None
    if static_hold is not None:
        import omni.usd

        omni.usd.get_context().close_stage()
        application.update()
    pour = _run_pour(args, application, packet, output_dir)
    result = {
        "schema": "labutopia.isaac41.liquid0812_fast_benchmark_result.v1",
        "claim_boundary": (
            "formal_isaac41_runtime;liquid0812_fast_usd_only;"
            "548_particles;30hz;single_native_isosurface_camera;not_full_product_scene"
        ),
        "runtime": runtime_record,
        "scene": _file_record(args.scene),
        "packet": _file_record(args.packet),
        "mode": args.mode,
        "headless": True,
        "static_hold": static_hold,
        "pour": pour,
    }
    result["content_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    _atomic_json(output_dir / "result.json", result)
    print(
        json.dumps(
            {
                "status": pour["status"],
                "mode": args.mode,
                "model_ready_fps": pour["timing"]["model_ready_fps"],
                "result": str(output_dir / "result.json"),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return result


def _run_child(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    request = attestation._read_canonical_json(args.execution_request)
    request = attestation.verify_execution_request(request, source_paths=source_paths())
    pre_app_numpy_modules = sorted(
        name for name in sys.modules if name == "numpy" or name.startswith("numpy.")
    )
    from isaacsim import SimulationApp

    parsed_argv = sys.argv
    sys.argv = [sys.argv[0]]
    application = SimulationApp(
        {
            "headless": True,
            "width": args.width,
            "height": args.height,
            "renderer": "RayTracedLighting",
        }
    )
    sys.argv = parsed_argv
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    try:
        receipt = attestation.attest_existing_application(
            application=application,
            pre_app_numpy_modules=pre_app_numpy_modules,
            execution_request=request,
            source_paths=source_paths(),
        )
        attestation.write_canonical_json(receipt_path, receipt)
        binding = attestation.execution_binding_for_request(request, child_pid=os.getpid())
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        _configure_runtime_settings()
        _run_benchmark(
            args,
            application=application,
            runtime_record={
                "lane": "formal_isaac41_liquid0812_fast_benchmark",
                "receipt_path": str(receipt_path),
                "receipt_sha256": attestation.canonical_json_sha256(receipt),
                "execution_binding": binding,
            },
        )
        return 0
    except BaseException as error:
        _atomic_json(
            args.evidence_dir / "child_failure.json",
            {
                "status": "blocked_runtime",
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        )
        return 2
    finally:
        application.close()


def _child_command(args: argparse.Namespace, request_path: Path, *, save_video: bool) -> list[str]:
    command = [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--mode",
        args.mode,
        "--scene",
        str(args.scene),
        "--packet",
        str(args.packet),
        "--output-dir",
        str(args.output_dir),
        "--evidence-dir",
        str(args.evidence_dir),
        "--execution-request",
        str(request_path),
        "--max-observations",
        str(args.max_observations),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--stage-warmup-updates",
        str(args.stage_warmup_updates),
        "--render-warmup-observations",
        str(args.render_warmup_observations),
    ]
    if save_video:
        command.append("--save-video")
    return command


def _run_one_parent(
    args: argparse.Namespace,
    *,
    gpu_preflight: dict[str, Any],
    save_video: bool,
) -> tuple[int, dict[str, Any] | None]:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    args.evidence_dir.mkdir(parents=True, exist_ok=False)
    closure = source_paths()
    source_before = attestation.capture_source_identity(closure)
    request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    request_path = args.evidence_dir / "execution_request.json"
    attestation.write_canonical_json(request_path, request)
    environment = attestation.sealed_child_environment(args.evidence_dir / "runtime")
    command = _child_command(args, request_path, save_video=save_video)
    started = time.time()
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
    )
    stdout_path = args.evidence_dir / "child.stdout.log"
    stderr_path = args.evidence_dir / "child.stderr.log"
    stdout_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    result_path = args.output_dir / "result.json"
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    verification_error = None
    receipt_sha256 = None
    result = None
    try:
        receipt = attestation._read_canonical_json(receipt_path)
        attestation.require_matched_runtime_receipt(receipt)
        receipt_sha256 = attestation.canonical_json_sha256(receipt)
        if completed.returncode != 0 or not result_path.is_file():
            raise RuntimeError(f"liquid0812_child_exit:{completed.returncode}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except BaseException as error:
        verification_error = {"type": type(error).__name__, "message": str(error)}
    combined_logs = completed.stdout + b"\n" + completed.stderr
    manifest = {
        "schema": "labutopia.isaac41.liquid0812_fast_parent_manifest.v1",
        "status": "passed" if verification_error is None else "blocked_runtime",
        "command": command,
        "child_returncode": completed.returncode,
        "started_unix_s": started,
        "elapsed_wall_s": time.time() - started,
        "source_before": source_before,
        "source_after": attestation.capture_source_identity(closure),
        "scene": _file_record(args.scene),
        "packet": _file_record(args.packet),
        "gpu_preflight": gpu_preflight,
        "gpu_after": _gpu_snapshot(),
        "runtime_receipt_sha256": receipt_sha256,
        "stdout": _file_record(stdout_path),
        "stderr": _file_record(stderr_path),
        "result_sha256": _sha256_file(result_path) if result_path.is_file() else None,
        "warnings": {
            "particle_sampling_recovery": b"target particle prim has a different point count" in combined_logs,
            "invalid_convex_error_percentage": b"Invalid volume error percentage" in combined_logs,
        },
        "verification_error": verification_error,
    }
    attestation.write_canonical_json(args.evidence_dir / "run_manifest.json", manifest)
    return (0 if verification_error is None else 2), result


def _coefficient_of_variation(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    return statistics.stdev(values) / mean if mean else math.inf


def _reference_video_record(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    command = [
        "/usr/bin/ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,duration",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return {
        **_file_record(path),
        "ffprobe_returncode": completed.returncode,
        "ffprobe": json.loads(completed.stdout) if completed.returncode == 0 else None,
        "manual_overlay_review": {
            "fps_range": [49.76, 54.16],
            "frame_time_ms_range": [18.46, 20.10],
            "provenance": "local_non_independent_visual_read_of_gui_overlay",
        },
    }


def _run_matrix(args: argparse.Namespace) -> int:
    root = args.output_root
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"output_root_not_empty:{root}")
    root.mkdir(parents=True, exist_ok=True)
    modes = ("physics-only", "headless-rendered")
    all_results: dict[str, list[dict[str, Any]]] = {mode: [] for mode in modes}
    run_records = []
    failures = []
    for mode in modes:
        repeat_target = args.repeats
        repeat = 0
        while repeat < repeat_target:
            print(
                json.dumps(
                    {"event": "gpu_preflight_start", "mode": mode, "repeat": repeat},
                    sort_keys=True,
                ),
                flush=True,
            )
            gpu_preflight = _sample_gpu(args.gpu_sample_seconds)
            if not gpu_preflight["idle_enough"]:
                retry_records = [gpu_preflight]
                for _ in range(2):
                    candidate = _sample_gpu(args.gpu_sample_seconds)
                    retry_records.append(candidate)
                    if candidate["idle_enough"]:
                        gpu_preflight = candidate
                        break
                else:
                    failures.append({"mode": mode, "repeat": repeat, "reason": "gpu_busy", "samples": retry_records})
                    break
            run_root = root / "runs" / mode / f"repeat-{repeat:02d}"
            child_args = argparse.Namespace(**vars(args))
            child_args.mode = mode
            child_args.output_dir = run_root / "artifacts"
            child_args.evidence_dir = run_root / "evidence"
            print(
                json.dumps(
                    {"event": "formal_run_start", "mode": mode, "repeat": repeat, "root": str(run_root)},
                    sort_keys=True,
                ),
                flush=True,
            )
            code, result = _run_one_parent(
                child_args,
                gpu_preflight=gpu_preflight,
                save_video=mode == "headless-rendered" and repeat == 0,
            )
            run_records.append(
                {"mode": mode, "repeat": repeat, "returncode": code, "root": str(run_root)}
            )
            print(
                json.dumps(
                    {
                        "event": "formal_run_end",
                        "mode": mode,
                        "repeat": repeat,
                        "returncode": code,
                        "model_ready_fps": (
                            result["pour"]["timing"]["model_ready_fps"] if result is not None else None
                        ),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            if result is None:
                failures.append({"mode": mode, "repeat": repeat, "reason": "run_failed"})
                break
            all_results[mode].append(result)
            repeat += 1
            if repeat == repeat_target and repeat_target == 3:
                fps_values = [
                    float(item["pour"]["timing"]["model_ready_fps"])
                    for item in all_results[mode]
                ]
                if _coefficient_of_variation(fps_values) > 0.05:
                    repeat_target = 5

    summaries = {}
    for mode, results in all_results.items():
        if not results:
            summaries[mode] = None
            continue
        fps = [float(item["pour"]["timing"]["model_ready_fps"]) for item in results]
        physics = [
            float(item["pour"]["timing"]["physics_per_observation"]["mean_ms"])
            for item in results
        ]
        initial_hashes = [item["pour"]["initial_position_sha256"] for item in results]
        summaries[mode] = {
            "run_count": len(results),
            "model_ready_fps": {
                "values": fps,
                "mean": statistics.fmean(fps),
                "median": statistics.median(fps),
                "coefficient_of_variation": _coefficient_of_variation(fps),
            },
            "physics_mean_ms": {
                "values": physics,
                "mean": statistics.fmean(physics),
                "median": statistics.median(physics),
            },
            "initial_position_hashes": initial_hashes,
            "initial_position_reproducible": len(set(initial_hashes)) == 1,
            "separated_acceptance": results[0]["pour"]["separated_acceptance"],
            "static_hold": results[0]["static_hold"],
        }
    matrix = {
        "schema": "labutopia.isaac41.liquid0812_fast_matrix.v1",
        "status": "passed" if not failures and all(summaries.values()) else "incomplete",
        "claim_boundary": (
            "liquid0812_fast_usd_only;not_full_lab;not_dual_product_camera;"
            "nonexclusive_gpu_if_compute_processes_recorded"
        ),
        "scene": _file_record(args.scene),
        "packet": _file_record(args.packet),
        "reference_video": _reference_video_record(args.video_reference),
        "configuration": {
            "particle_count": EXPECTED_PARTICLE_COUNT,
            "physics_hz": PHYSICS_HZ,
            "substeps_per_observation": 1,
            "solver_position_iterations": 16,
            "render_resolution": [args.width, args.height],
            "camera_path": CAMERA_PATH,
            "headless": True,
            "surface": "native_physx_isosurface",
        },
        "runs": run_records,
        "summaries": summaries,
        "failures": failures,
    }
    matrix["content_sha256"] = hashlib.sha256(
        json.dumps(matrix, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    _atomic_json(root / "matrix.json", matrix)
    print(json.dumps({"status": matrix["status"], "matrix": str(root / "matrix.json")}, sort_keys=True))
    return 0 if matrix["status"] == "passed" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--mode", choices=("physics-only", "headless-rendered"))
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--video-reference", type=Path, default=DEFAULT_VIDEO_REFERENCE)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--gpu-sample-seconds", type=int, default=10)
    parser.add_argument("--max-observations", type=int, default=EXPECTED_OBSERVATIONS)
    parser.add_argument("--width", type=int, default=1554)
    parser.add_argument("--height", type=int, default=1068)
    parser.add_argument("--stage-warmup-updates", type=int, default=32)
    parser.add_argument("--render-warmup-observations", type=int, default=16)
    parser.add_argument("--save-video", action="store_true")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in ("scene", "packet", "video_reference"):
        setattr(args, name, getattr(args, name).resolve())
    for name in ("output_root", "output_dir", "evidence_dir", "execution_request"):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve())
    if args.child:
        if args.execution_request is None or args.output_dir is None or args.evidence_dir is None or args.mode is None:
            raise ValueError("child_arguments_missing")
        return _run_child(args)
    if args.execution_request is not None:
        raise ValueError("execution_request_is_child_only")
    if args.matrix:
        if args.output_root is None:
            raise ValueError("matrix_output_root_required")
        if args.repeats < 3 or args.repeats > 5:
            raise ValueError("matrix_repeats_out_of_range")
        return _run_matrix(args)
    if args.mode is None or args.output_dir is None or args.evidence_dir is None:
        raise ValueError("single_run_arguments_missing")
    gpu_preflight = _sample_gpu(args.gpu_sample_seconds)
    code, _ = _run_one_parent(args, gpu_preflight=gpu_preflight, save_video=args.save_video)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
