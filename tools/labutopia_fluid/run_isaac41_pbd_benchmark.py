#!/usr/bin/env python3
"""Matched Isaac Sim 4.1 PhysX PBD benchmark for the fluid packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
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
DEFAULT_PACKET = (
    REPO_ROOT
    / "outputs/fluid_benchmark_isaac601_newton140/packet_v2"
    / "fluid_benchmark_packet_v2.json"
)
DEFAULT_SCENE = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval"
    / "lab_001_level1_pour_interndata_liquid_v1.usda"
)
CAMERAS = {
    "camera_1": "/World/InternDataParityCamera",
    "camera_2": "/World/InternDataParityCloseupCamera",
}
SURFACE_PATH = "/World/InternDataOnlineSurface"
REVIEW_FRAME_INDICES = frozenset({0, 300, 450, 580, 650, 750, 852, 952})


def source_paths() -> tuple[Path, ...]:
    return (
        REPO_ROOT / "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        Path(__file__).resolve(),
        REPO_ROOT / "tools/labutopia_fluid/fluid_benchmark_contract.py",
        REPO_ROOT / "tools/labutopia_fluid/interndata_surface_reconstruction.py",
        REPO_ROOT / "tools/labutopia_fluid/run_interndata_online_surface_probe.py",
        REPO_ROOT / "tools/labutopia_fluid/run_interndata_pour_parity_probe.py",
        REPO_ROOT
        / "tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py",
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


def _numeric_pass(quality: dict[str, Any]) -> bool:
    return bool(quality.get("numeric_passed"))


def _run_benchmark(
    args: argparse.Namespace,
    *,
    application: Any,
    runtime_record: dict[str, Any],
) -> dict[str, Any]:
    import carb
    import numpy as np
    import omni.physics.tensors
    import omni.physx
    import omni.physx.bindings._physx as pb
    import omni.timeline
    import omni.usd
    from pxr import UsdUtils

    from tools.labutopia_fluid.fluid_benchmark_contract import (
        EXPECTED_OBSERVATION_COUNT,
        EXPECTED_PARTICLE_COUNT,
        INTEGRATION_DT_S,
        classify_positions,
        evaluate_quality_gate,
        evaluate_stability_gate,
        interpolate_pose_xyzw,
        load_packet,
        sha256_file,
        summarize_milliseconds,
    )
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
        StrictPhysicsStepper,
        _configure_physics_scene_for_pbd,
    )
    from tools.labutopia_fluid.run_interndata_online_surface_probe import (
        apply_source_body_mode,
        author_live_surface_material,
        configure_live_visual_authority,
        read_strict_simulation_points,
        source_body_mode_contract,
        update_live_surface_mesh,
    )
    from tools.labutopia_fluid.run_interndata_pour_parity_probe import (
        PARTICLE_SET_PATH,
        PHYSICS_SCENE_PATH,
    )

    output_dir = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output_dir_not_empty:{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    packet = load_packet(args.packet)
    count = args.max_observations or EXPECTED_OBSERVATION_COUNT
    if count <= 0 or count > EXPECTED_OBSERVATION_COUNT:
        raise ValueError("max_observations_out_of_range")
    source_poses = packet.array("source_poses_xyzw", (953, 7))
    source_frame_local = packet.array("source_frame_local_matrix", (4, 4))
    target_frame_world = packet.array("target_frame_world_matrix", (4, 4))

    settings = carb.settings.get_settings()
    settings.set(pb.SETTING_UPDATE_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
    settings.set(pb.SETTING_DISPLAY_PARTICLES, getattr(pb.VisualizerMode, "NONE", 0))
    settings.set_bool(pb.SETTING_SUPPRESS_READBACK, False)
    settings.set_bool("/physics/suppressReadback", False)

    context = omni.usd.get_context()
    if not context.open_stage(str(args.scene)):
        raise RuntimeError("isaac41_pbd_stage_open_failed")
    for _ in range(args.stage_warmup_updates):
        application.update()
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("isaac41_pbd_stage_missing")
    stage.SetEditTarget(stage.GetRootLayer())
    physics_settings = _configure_physics_scene_for_pbd(
        stage,
        PHYSICS_SCENE_PATH,
        integration_dt=INTEGRATION_DT_S,
        strict_mode=True,
    )
    source_path = str(packet.manifest["paths"]["source"])
    source_prim = stage.GetPrimAtPath(source_path)
    if not source_prim or not source_prim.IsValid():
        raise RuntimeError("isaac41_pbd_source_missing")
    apply_source_body_mode(
        source_prim,
        source_body_mode_contract("kinematic", treatment="benchmark"),
    )
    application.update()
    stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
    stepper = StrictPhysicsStepper.attach(
        interface=omni.physx.get_physx_simulation_interface(),
        logical_dt=INTEGRATION_DT_S,
        integration_dt=INTEGRATION_DT_S,
        substeps_per_logical_step=1,
        stage_id=stage_id,
    )
    tensor_simulation = omni.physics.tensors.create_simulation_view("numpy", stage_id)
    source_view = tensor_simulation.create_rigid_body_view(source_path)
    if source_view.count != 1:
        raise RuntimeError(f"isaac41_pbd_source_view_count:{source_view.count}")
    source_indices = np.asarray([0], dtype=np.uint32)
    initial_source_view_pose = (
        np.asarray(source_view.get_transforms(), dtype=np.float64)
        .reshape((-1, 7))[0]
    )
    rigid_from_packet_relation = (
        _pose_matrix_xyzw(np, initial_source_view_pose)
        @ np.linalg.inv(_pose_matrix_xyzw(np, source_poses[0]))
    )

    def rigid_target_for_packet_pose(packet_pose: Any) -> Any:
        return _matrix_pose_xyzw(
            np,
            rigid_from_packet_relation @ _pose_matrix_xyzw(np, packet_pose),
        )
    _atomic_json(
        output_dir / "source_pose_diagnostic.json",
        {
            "rigid_view_initial_pose_xyzw": initial_source_view_pose.tolist(),
            "packet_initial_pose_xyzw": source_poses[0].tolist(),
            "rigid_from_packet_relation": rigid_from_packet_relation.tolist(),
        },
    )
    source_view.set_kinematic_targets(
        np.asarray([rigid_target_for_packet_pose(source_poses[0])], dtype=np.float32),
        source_indices,
    )
    stepper.step()
    initial_positions = read_strict_simulation_points(
        stage, PARTICLE_SET_PATH, expected_particle_count=EXPECTED_PARTICLE_COUNT
    )
    initial_position_sha256 = hashlib.sha256(
        np.ascontiguousarray(initial_positions, dtype="<f4").tobytes()
    ).hexdigest()

    rendered = args.mode == "rendered"
    resources: dict[str, dict[str, Any]] = {}
    rep = None
    timeline = None
    material_record = None
    authority_record = None
    reconstruct_surface_live = None
    update_surface = None
    SurfaceFrameToken = None
    if rendered:
        import omni.replicator.core as rep_module
        from tools.labutopia_fluid.interndata_surface_reconstruction import (
            reconstruct_surface_live as reconstruct,
        )
        from utils.online_fluid_surface import SurfaceFrameToken as Token

        rep = rep_module
        timeline = omni.timeline.get_timeline_interface()
        timeline.stop()
        reconstruct_surface_live = reconstruct
        update_surface = update_live_surface_mesh
        SurfaceFrameToken = Token
        for name, camera_path in CAMERAS.items():
            if not stage.GetPrimAtPath(camera_path).IsValid():
                raise RuntimeError(f"isaac41_pbd_camera_missing:{camera_path}")
            product = rep.create.render_product(camera_path, (args.width, args.height))
            rgb = rep.AnnotatorRegistry.get_annotator("rgb")
            rgb.attach(product)
            resources[name] = {"render_product": product, "rgb": rgb}

    physics_ms: list[float] = []
    score_ms: list[float] = []
    reconstruction_ms: list[float] = []
    authoring_ms: list[float] = []
    render_ms: list[float] = []
    capture_ms: list[float] = []
    model_ready_ms: list[float] = []
    score_history: list[dict[str, Any]] = []
    review_positions: list[Any] = []
    review_indices: list[int] = []
    saved_frames: list[dict[str, Any]] = []
    records_path = output_dir / "observations.jsonl"
    records_stream = records_path.open("xb")
    try:
        for observation_index in range(count):
            model_started = time.perf_counter()
            physics_started = time.perf_counter()
            previous_index = max(0, observation_index - 1)
            for substep_index in range(4):
                pose = interpolate_pose_xyzw(
                    source_poses[previous_index],
                    source_poses[observation_index],
                    float(substep_index + 1) / 4.0,
                )
                source_view.set_kinematic_targets(
                    np.asarray([rigid_target_for_packet_pose(pose)], dtype=np.float32),
                    source_indices,
                )
                stepper.step()
            positions = read_strict_simulation_points(
                stage,
                PARTICLE_SET_PATH,
                expected_particle_count=EXPECTED_PARTICLE_COUNT,
            )
            physics_ms.append((time.perf_counter() - physics_started) * 1000.0)

            score_started = time.perf_counter()
            source_frame = packet.manifest["frames"]["source"]
            target_frame = packet.manifest["frames"]["target"]
            score = classify_positions(
                positions,
                source_frame_world_matrix=(
                    source_frame_local @ _pose_matrix_xyzw(np, source_poses[observation_index])
                ),
                target_frame_world_matrix=target_frame_world,
                source_interior_radius_m=float(source_frame["interior_radius_m"]),
                target_interior_radius_m=float(target_frame["interior_radius_m"]),
                source_floor_m=float(source_frame["floor_m"]),
                source_rim_m=float(source_frame["rim_m"]),
                target_floor_m=float(target_frame["floor_m"]),
                target_rim_m=float(target_frame["rim_m"]),
                table_top_z_m=float(packet.manifest["frames"]["table_top_z_m"]),
            )
            score["observation_index"] = observation_index
            score_history.append(score)
            score_ms.append((time.perf_counter() - score_started) * 1000.0)
            camera_hashes = None

            if rendered:
                assert reconstruct_surface_live is not None
                assert update_surface is not None
                assert SurfaceFrameToken is not None
                reconstruction_started = time.perf_counter()
                surface = reconstruct_surface_live(positions)
                reconstruction_ms.append(
                    (time.perf_counter() - reconstruction_started) * 1000.0
                )
                position_sha256 = hashlib.sha256(
                    np.ascontiguousarray(positions, dtype="<f4").tobytes()
                ).hexdigest()
                identity = hashlib.sha256(
                    f"pbd:{observation_index}:{position_sha256}:{surface['geometry_sha256']}".encode("ascii")
                ).hexdigest()
                token = SurfaceFrameToken(
                    episode_id="isaac41_pbd_packet_benchmark",
                    observation_index=observation_index,
                    caused_by_action_index=(None if observation_index == 0 else observation_index - 1),
                    logical_step_before=observation_index * 4,
                    logical_step_after=(observation_index + 1) * 4,
                    integration_step_before=observation_index * 4,
                    integration_step_after=(observation_index + 1) * 4,
                    simulation_time_before=observation_index / 30.0,
                    simulation_time_after=(observation_index + 1) / 30.0,
                    action_sha256=None,
                    particle_count=EXPECTED_PARTICLE_COUNT,
                    position_sha256=position_sha256,
                    surface_geometry_sha256=surface["geometry_sha256"],
                    identity=identity,
                    positions=positions,
                )
                authoring_started = time.perf_counter()
                authored = update_surface(stage, surface, token)
                if material_record is None:
                    material_record = author_live_surface_material(stage)
                    authority_record = configure_live_visual_authority(stage)
                authoring_ms.append(
                    (time.perf_counter() - authoring_started) * 1000.0
                )
                render_started = time.perf_counter()
                before = float(timeline.get_current_time())
                rep.orchestrator.step(
                    rt_subframes=args.rt_subframes,
                    pause_timeline=True,
                    delta_time=0.0,
                )
                rep.orchestrator.wait_until_complete()
                after = float(timeline.get_current_time())
                if abs(after - before) > 1.0e-12:
                    raise RuntimeError("isaac41_pbd_render_advanced_timeline")
                render_ms.append((time.perf_counter() - render_started) * 1000.0)
                capture_started = time.perf_counter()
                camera_hashes = {}
                for name, resource in resources.items():
                    raw = np.asarray(resource["rgb"].get_data())
                    if raw.shape[:2] != (args.height, args.width):
                        raise RuntimeError(f"isaac41_pbd_camera_shape:{name}:{raw.shape}")
                    rgb = np.ascontiguousarray(raw[..., :3], dtype=np.uint8)
                    camera_hashes[name] = hashlib.sha256(rgb.tobytes()).hexdigest()
                    if observation_index in REVIEW_FRAME_INDICES or observation_index == count - 1:
                        from PIL import Image

                        frame_path = output_dir / "review_frames" / name / f"frame_{observation_index:04d}.png"
                        frame_path.parent.mkdir(parents=True, exist_ok=True)
                        Image.fromarray(rgb, mode="RGB").save(frame_path)
                        saved_frames.append(
                            {"camera": name, "observation_index": observation_index, "path": str(frame_path), "sha256": _sha256_file(frame_path)}
                        )
                capture_ms.append((time.perf_counter() - capture_started) * 1000.0)
                _ = authored

            model_ready_ms.append((time.perf_counter() - model_started) * 1000.0)
            record = {
                "observation_index": observation_index,
                "score": score,
                "camera_sha256": camera_hashes,
            }
            records_stream.write(
                (json.dumps(record, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
            )
            if observation_index in REVIEW_FRAME_INDICES or observation_index == count - 1:
                review_indices.append(observation_index)
                review_positions.append(positions.astype(np.float32, copy=True))
    finally:
        records_stream.close()
        for resource in resources.values():
            try:
                resource["rgb"].detach()
                resource["render_product"].destroy()
            except Exception:
                pass

    np.savez_compressed(
        output_dir / "review_particle_frames.npz",
        observation_indices=np.asarray(review_indices, dtype=np.int32),
        particle_positions=np.stack(review_positions, axis=0),
    )
    quality = evaluate_quality_gate(score_history, visual_liquid_passed=None)
    stability = evaluate_stability_gate(
        score_history,
        expected_particle_count=EXPECTED_PARTICLE_COUNT,
    )
    warm_physics = physics_ms[1:] if len(physics_ms) > 1 else physics_ms
    warm_model = model_ready_ms[1:] if len(model_ready_ms) > 1 else model_ready_ms
    timing = {
        "warmup_observations_excluded": 1 if len(physics_ms) > 1 else 0,
        "physics_per_observation": summarize_milliseconds(warm_physics),
        "physics_only_fps": 1000.0 / float(sum(warm_physics) / len(warm_physics)),
        "score_per_observation": summarize_milliseconds(score_ms[1:] if len(score_ms) > 1 else score_ms),
        "model_ready_per_observation": summarize_milliseconds(warm_model),
        "model_ready_fps": 1000.0 / float(sum(warm_model) / len(warm_model)),
        "reconstruction": summarize_milliseconds(reconstruction_ms[1:] if len(reconstruction_ms) > 1 else reconstruction_ms) if reconstruction_ms else None,
        "usd_authoring": summarize_milliseconds(authoring_ms[1:] if len(authoring_ms) > 1 else authoring_ms) if authoring_ms else None,
        "rtx_render": summarize_milliseconds(render_ms[1:] if len(render_ms) > 1 else render_ms) if render_ms else None,
        "camera_capture": summarize_milliseconds(capture_ms[1:] if len(capture_ms) > 1 else capture_ms) if capture_ms else None,
    }
    result = {
        "schema": runtime_record.get(
            "result_schema",
            "labutopia.isaac41_pbd_packet_benchmark_result.v1",
        ),
        "status": "numeric_pass" if _numeric_pass(quality) else "failed_quality",
        "claim_boundary": runtime_record.get(
            "claim_boundary",
            "matched_packet_performance_lane;formal_isaac41_runtime;visual_review_pending",
        ),
        "mode": args.mode,
        "runtime": runtime_record,
        "particle_count": EXPECTED_PARTICLE_COUNT,
        "observation_count": count,
        "integration_dt_s": INTEGRATION_DT_S,
        "substeps_per_observation": 4,
        "source_motion": "recorded_pose_with_four_substep_slerp",
        "source_pose_diagnostic": {
            "rigid_view_initial_pose_xyzw": initial_source_view_pose.tolist(),
            "packet_initial_pose_xyzw": source_poses[0].tolist(),
            "rigid_from_packet_relation": rigid_from_packet_relation.tolist(),
        },
        "initial_position_sha256": initial_position_sha256,
        "physics_settings": physics_settings,
        "timing": timing,
        "quality": quality,
        "stability": stability,
        "packet": {"path": str(packet.manifest_path), "sha256": sha256_file(packet.manifest_path)},
        "scene": {"path": str(args.scene), "sha256": _sha256_file(args.scene)},
        "strict_physics": stepper.summary(requested_steps=count * 4 + 1),
        "pre_episode_initialization_substeps": 1,
        "artifacts": {
            "observations": {"path": str(records_path), "sha256": _sha256_file(records_path)},
            "saved_review_frames": saved_frames,
        },
    }
    result["content_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    _atomic_json(output_dir / "result.json", result)
    print(json.dumps({"status": result["status"], "result": str(output_dir / "result.json")}, sort_keys=True), flush=True)
    return result


def _run_child(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    closure = source_paths()
    request = attestation._read_canonical_json(args.execution_request)
    request = attestation.verify_execution_request(request, source_paths=closure)
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
            "extra_args": ["--/rtx/raytracing/fractionalCutoutOpacity=true"],
        }
    )
    sys.argv = parsed_argv
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    try:
        receipt = attestation.attest_existing_application(
            application=application,
            pre_app_numpy_modules=pre_app_numpy_modules,
            execution_request=request,
            source_paths=closure,
        )
        attestation.write_canonical_json(receipt_path, receipt)
        binding = attestation.execution_binding_for_request(request, child_pid=os.getpid())
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        _run_benchmark(
            args,
            application=application,
            runtime_record={
                "lane": "formal_isaac41_pbd_packet_benchmark",
                "receipt_path": str(receipt_path),
                "receipt_sha256": attestation.canonical_json_sha256(receipt),
                "execution_binding": binding,
            },
        )
        return 0
    except BaseException as error:
        _atomic_json(
            args.evidence_dir / "child_failure.json",
            {"status": "blocked_runtime", "type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()},
        )
        return 2
    finally:
        application.close()


def _child_command(args: argparse.Namespace, request_path: Path) -> list[str]:
    command = [
        str(FORMAL_ISAAC41_PYTHON), "-I", "-B", str(Path(__file__).resolve()),
        "--child", "--mode", args.mode, "--packet", str(args.packet),
        "--scene", str(args.scene), "--output-dir", str(args.output_dir),
        "--evidence-dir", str(args.evidence_dir), "--execution-request", str(request_path),
        "--width", str(args.width), "--height", str(args.height),
        "--rt-subframes", str(args.rt_subframes),
        "--stage-warmup-updates", str(args.stage_warmup_updates),
    ]
    if args.max_observations is not None:
        command.extend(["--max-observations", str(args.max_observations)])
    return command


def _run_parent(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    if args.evidence_dir.exists():
        raise FileExistsError(f"evidence_dir_exists:{args.evidence_dir}")
    args.evidence_dir.mkdir(parents=True)
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
    command = _child_command(args, request_path)
    completed = subprocess.run(command, cwd=REPO_ROOT, env=environment, check=False)
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    verification_error = None
    receipt_sha256 = None
    try:
        receipt = attestation._read_canonical_json(receipt_path)
        attestation.require_matched_runtime_receipt(receipt)
        receipt_sha256 = attestation.canonical_json_sha256(receipt)
        if completed.returncode != 0 or not (args.output_dir / "result.json").is_file():
            raise RuntimeError(f"isaac41_pbd_child_exit:{completed.returncode}")
    except BaseException as error:
        verification_error = {"type": type(error).__name__, "message": str(error)}
    manifest = {
        "schema": "labutopia.isaac41_pbd_packet_parent_manifest.v1",
        "status": "passed" if verification_error is None else "blocked_runtime",
        "command": command,
        "child_returncode": completed.returncode,
        "source_before": source_before,
        "source_after": attestation.capture_source_identity(closure),
        "runtime_receipt_sha256": receipt_sha256,
        "result_sha256": _sha256_file(args.output_dir / "result.json") if (args.output_dir / "result.json").is_file() else None,
        "verification_error": verification_error,
    }
    attestation.write_canonical_json(args.evidence_dir / "run_manifest.json", manifest)
    return 0 if verification_error is None else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("physics-only", "rendered"), required=True)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--max-observations", type=int)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--rt-subframes", type=int, default=1)
    parser.add_argument("--stage-warmup-updates", type=int, default=32)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in ("packet", "scene", "output_dir", "evidence_dir"):
        setattr(args, name, getattr(args, name).resolve())
    if args.child:
        if args.execution_request is None:
            raise ValueError("child_execution_request_required")
        args.execution_request = args.execution_request.resolve()
        return _run_child(args)
    if args.execution_request is not None:
        raise ValueError("execution_request_is_child_only")
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
