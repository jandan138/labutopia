#!/usr/bin/env python3
"""Render accepted experimental WCSPH frames in the sealed Isaac Sim 4.1 renderer.

This is a visual-only replay.  It never advances physics and never changes the
accepted particle trajectory.  The parent creates an effective-runtime v2
execution request; the child attests the exact Isaac 4.1 runtime before opening
the USD scene or consuming particle frames.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


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
    "context": "/World/InternDataParityCamera",
    "closeup": "/World/InternDataParityCloseupCamera",
}
SOURCE_BEAKER_PATH = "/World/beaker2"
LIQUID_PATH = "/World/WcsphAcceptedReplay"
RESIDUAL_LIQUID_PATH = "/World/WcsphAcceptedReplayResidual"
MATERIAL_PATH = "/World/Looks/WcsphAcceptedReplayWater"
LEGACY_LIQUID_PATHS = (
    "/World/InternDataParityFluid/Particles",
    "/World/InternDataParityFluid/VisualParticles",
    "/World/ParticleSet",
    "/World/fluid",
)


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def source_paths() -> tuple[Path, ...]:
    return (
        REPO_ROOT / "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        Path(__file__).resolve(),
        REPO_ROOT / "tools/labutopia_fluid/fluid_benchmark_contract.py",
        REPO_ROOT / "tools/labutopia_fluid/interndata_surface_reconstruction.py",
    )


def _pose_matrix_gf(Gf: Any, pose: Sequence[float]) -> Any:
    x, y, z, qx, qy, qz, qw = (float(value) for value in pose)
    matrix = Gf.Matrix4d(1.0)
    matrix.SetRotate(Gf.Quatd(qw, qx, qy, qz))
    matrix.SetTranslateOnly(Gf.Vec3d(x, y, z))
    return matrix


def _set_world_matrix(prim: Any, UsdGeom: Any, matrix: Any) -> None:
    xformable = UsdGeom.Xformable(prim)
    xformable.ClearXformOpOrder()
    xformable.AddTransformOp(
        precision=UsdGeom.XformOp.PrecisionDouble,
        opSuffix="wcsphReplay",
    ).Set(matrix)


def _encode_video(frame_dir: Path, output_path: Path, fps: int) -> dict[str, Any]:
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(fps), "-i", str(frame_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-preset", "slow", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path),
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
        "sha256": _sha256_file(output_path),
        "size_bytes": output_path.stat().st_size,
        "codec_name": stream.get("codec_name"),
        "pixel_format": stream.get("pix_fmt"),
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "frame_rate": stream.get("r_frame_rate"),
        "decoded_frame_count": int(stream.get("nb_read_frames", 0)),
    }


def _render(args: argparse.Namespace, *, application: Any, runtime: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np
    import omni.replicator.core as rep
    import omni.usd
    from PIL import Image
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    from tools.labutopia_fluid.fluid_benchmark_contract import load_packet
    from tools.labutopia_fluid.interndata_surface_reconstruction import reconstruct_surface_live

    if args.output_dir.exists():
        raise FileExistsError(f"output_dir_exists:{args.output_dir}")
    args.output_dir.mkdir(parents=True)
    with np.load(args.particle_frames, allow_pickle=False) as archive:
        if set(archive.files) != {"observation_indices", "particle_positions"}:
            raise ValueError("particle_frame_archive_fields_invalid")
        observation_indices = np.asarray(archive["observation_indices"], dtype=np.int32)
        frames = np.asarray(archive["particle_positions"], dtype=np.float32)
    with np.load(args.trajectory_npz, allow_pickle=False) as archive:
        if tuple(archive.files) != ("source_poses_xyzw",):
            raise ValueError("trajectory_archive_fields_invalid")
        source_poses = np.asarray(archive["source_poses_xyzw"], dtype=np.float64)
    if (
        frames.ndim != 3
        or frames.shape[0] != 953
        or frames.shape[2] != 3
        or observation_indices.tolist() != list(range(953))
        or source_poses.shape != (953, 7)
        or not np.isfinite(frames).all()
        or not np.isfinite(source_poses).all()
    ):
        raise ValueError("replay_input_shape_or_value_invalid")
    stop_frame = args.start_frame + args.max_frames
    frames = frames[args.start_frame : stop_frame]
    observation_indices = observation_indices[args.start_frame : stop_frame]
    packet = load_packet(args.packet)
    context = omni.usd.get_context()
    if not context.open_stage(str(args.scene)):
        raise RuntimeError("isaac_stage_open_failed")
    for _ in range(args.stage_warmup_updates):
        application.update()
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("isaac_stage_missing")
    source_prim = stage.GetPrimAtPath(SOURCE_BEAKER_PATH)
    if not source_prim or not source_prim.IsValid():
        raise RuntimeError("source_beaker_prim_missing")
    for path in CAMERAS.values():
        if not stage.GetPrimAtPath(path).IsValid():
            raise RuntimeError(f"camera_prim_missing:{path}")
    for path in LEGACY_LIQUID_PATHS:
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsValid() and prim.IsA(UsdGeom.Imageable):
            UsdGeom.Imageable(prim).CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)

    recorded = packet.array("source_poses_xyzw", (953, 7))
    initial_world = UsdGeom.XformCache().GetLocalToWorldTransform(source_prim)
    source_from_recorded_com = initial_world * _pose_matrix_gf(Gf, recorded[0]).GetInverse()

    products: dict[str, dict[str, Any]] = {}
    for camera_name, camera_path in CAMERAS.items():
        product = rep.create.render_product(camera_path, (args.width, args.height))
        annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        annotator.attach(product)
        products[camera_name] = {"product": product, "annotator": annotator}

    material = UsdShade.Material.Define(stage, MATERIAL_PATH)
    shader = UsdShade.Shader.Define(stage, f"{MATERIAL_PATH}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.05, 0.46, 0.72))
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.005, 0.025, 0.04))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.08)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(
        1.0 if args.representation == "particles" else 0.38
    )
    shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.333)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

    particle_instancer = None
    surface_mesh = None
    residual_instancer = None
    if args.representation == "particles":
        particle_instancer = UsdGeom.PointInstancer.Define(stage, LIQUID_PATH)
        UsdGeom.Scope.Define(stage, f"{LIQUID_PATH}/Prototypes")
        prototype_path = f"{LIQUID_PATH}/Prototypes/Sphere"
        prototype = UsdGeom.Sphere.Define(stage, prototype_path)
        prototype.CreateRadiusAttr().Set(float(args.particle_radius_m))
        particle_instancer.CreatePrototypesRel().SetTargets([Sdf.Path(prototype_path)])
        particle_instancer.CreateProtoIndicesAttr().Set(Vt.IntArray([0] * frames.shape[1]))
        UsdShade.MaterialBindingAPI.Apply(prototype.GetPrim()).Bind(material)
    else:
        surface_mesh = UsdGeom.Mesh.Define(stage, LIQUID_PATH)
        surface_mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        surface_mesh.CreateDoubleSidedAttr().Set(True)
        UsdShade.MaterialBindingAPI.Apply(surface_mesh.GetPrim()).Bind(material)
        residual_instancer = UsdGeom.PointInstancer.Define(stage, RESIDUAL_LIQUID_PATH)
        UsdGeom.Scope.Define(stage, f"{RESIDUAL_LIQUID_PATH}/Prototypes")
        residual_prototype_path = f"{RESIDUAL_LIQUID_PATH}/Prototypes/Sphere"
        residual_prototype = UsdGeom.Sphere.Define(stage, residual_prototype_path)
        residual_prototype.CreateRadiusAttr().Set(float(args.particle_radius_m))
        residual_instancer.CreatePrototypesRel().SetTargets(
            [Sdf.Path(residual_prototype_path)]
        )
        UsdShade.MaterialBindingAPI.Apply(residual_prototype.GetPrim()).Bind(material)

    def author_partitioned_surface(positions: Any) -> dict[str, Any]:
        """Mesh coherent liquid bodies and retain every small body as particles."""
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        from scipy.spatial import cKDTree

        values = np.ascontiguousarray(positions, dtype=np.float32)
        pairs = np.asarray(
            list(cKDTree(values).query_pairs(args.surface_connectivity_radius_m)),
            dtype=np.int32,
        )
        if pairs.size:
            pairs = pairs.reshape(-1, 2)
            graph = coo_matrix(
                (
                    np.ones(2 * len(pairs), dtype=np.uint8),
                    (
                        np.concatenate((pairs[:, 0], pairs[:, 1])),
                        np.concatenate((pairs[:, 1], pairs[:, 0])),
                    ),
                ),
                shape=(len(values), len(values)),
            )
            component_count, labels = connected_components(
                graph, directed=False, return_labels=True
            )
        else:
            component_count = len(values)
            labels = np.arange(len(values), dtype=np.int32)
        sizes = np.bincount(labels, minlength=component_count)
        mesh_labels = np.flatnonzero(sizes >= args.surface_min_mesh_particles)
        mesh_mask = np.isin(labels, mesh_labels)
        vertices_parts: list[Any] = []
        faces_parts: list[Any] = []
        normals_parts: list[Any] = []
        vertex_offset = 0
        for label in mesh_labels:
            reconstructed = reconstruct_surface_live(values[labels == label])
            vertices = np.ascontiguousarray(
                np.asarray(reconstructed["vertices"], dtype=np.float32)
                + np.asarray(reconstructed["origin_world_m"], dtype=np.float32),
                dtype=np.float32,
            )
            faces = np.ascontiguousarray(reconstructed["faces"], dtype=np.int32)
            normals = np.ascontiguousarray(reconstructed["normals"], dtype=np.float32)
            vertices_parts.append(vertices)
            faces_parts.append(faces + vertex_offset)
            normals_parts.append(normals)
            vertex_offset += len(vertices)
        if not vertices_parts:
            raise RuntimeError("surface_partition_has_no_meshable_component")
        vertices = np.concatenate(vertices_parts, axis=0)
        faces = np.concatenate(faces_parts, axis=0)
        normals = np.concatenate(normals_parts, axis=0)
        surface_mesh.CreatePointsAttr().Set(Vt.Vec3fArray.FromNumpy(vertices))
        surface_mesh.CreateFaceVertexCountsAttr().Set(Vt.IntArray([3] * len(faces)))
        surface_mesh.CreateFaceVertexIndicesAttr().Set(
            Vt.IntArray(faces.reshape(-1).tolist())
        )
        surface_mesh.CreateNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(normals))
        surface_mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        residual = np.ascontiguousarray(values[~mesh_mask], dtype=np.float32)
        residual_instancer.CreateProtoIndicesAttr().Set(Vt.IntArray([0] * len(residual)))
        residual_instancer.GetPositionsAttr().Set(Vt.Vec3fArray.FromNumpy(residual))
        if int(np.count_nonzero(mesh_mask)) + len(residual) != len(values):
            raise RuntimeError("surface_partition_particle_accounting_mismatch")
        return {
            "component_count": int(component_count),
            "meshed_component_count": int(len(mesh_labels)),
            "meshed_particle_count": int(np.count_nonzero(mesh_mask)),
            "residual_particle_count": int(len(residual)),
        }

    # Prime the actual render products after the replay geometry, material, and
    # first pose exist.  This excludes shader compilation from frame 0 without
    # advancing the timeline or invoking physics.
    warmup_observation_index = int(observation_indices[0])
    warmup_positions = frames[0]
    _set_world_matrix(
        source_prim,
        UsdGeom,
        source_from_recorded_com * _pose_matrix_gf(Gf, source_poses[warmup_observation_index]),
    )
    if particle_instancer is not None:
        particle_instancer.GetPositionsAttr().Set(
            Vt.Vec3fArray.FromNumpy(
                np.ascontiguousarray(warmup_positions, dtype=np.float32)
            )
        )
    else:
        author_partitioned_surface(warmup_positions)
    rep.orchestrator.step(
        rt_subframes=args.camera_warmup_subframes,
        pause_timeline=True,
        delta_time=0.0,
    )
    rep.orchestrator.wait_until_complete()

    render_times: list[float] = []
    reconstruction_times: list[float] = []
    surface_partition_diagnostics: list[dict[str, Any]] = []
    review_frames: list[dict[str, Any]] = []
    review_indices = {0, 300, 450, 580, 650, 750, 852, 952}
    try:
        for ordinal, (observation_index, positions) in enumerate(
            zip(observation_indices, frames, strict=True)
        ):
            _set_world_matrix(
                source_prim,
                UsdGeom,
                source_from_recorded_com * _pose_matrix_gf(Gf, source_poses[int(observation_index)]),
            )
            if particle_instancer is not None:
                particle_instancer.GetPositionsAttr().Set(
                    Vt.Vec3fArray.FromNumpy(np.ascontiguousarray(positions, dtype=np.float32))
                )
                reconstruction_times.append(0.0)
            else:
                reconstruction_started = time.perf_counter()
                surface_partition_diagnostics.append(
                    author_partitioned_surface(positions)
                )
                reconstruction_times.append((time.perf_counter() - reconstruction_started) * 1000.0)
            render_started = time.perf_counter()
            rep.orchestrator.step(
                rt_subframes=args.rt_subframes,
                pause_timeline=True,
                delta_time=0.0,
            )
            rep.orchestrator.wait_until_complete()
            render_times.append((time.perf_counter() - render_started) * 1000.0)
            for camera_name, resource in products.items():
                rgb = np.asarray(resource["annotator"].get_data())
                if rgb.shape[:2] != (args.height, args.width):
                    raise RuntimeError(f"rgb_shape_invalid:{camera_name}:{rgb.shape}")
                path = args.output_dir / "frames" / camera_name / f"frame_{ordinal:04d}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(np.ascontiguousarray(rgb[..., :3], dtype=np.uint8), mode="RGB").save(path)
                if int(observation_index) in review_indices:
                    review_frames.append(
                        {
                            "camera": camera_name,
                            "observation_index": int(observation_index),
                            "path": str(path),
                            "sha256": _sha256_file(path),
                        }
                    )
    finally:
        for resource in products.values():
            try:
                resource["annotator"].detach()
                resource["product"].destroy()
            except Exception:
                pass

    videos = {}
    for camera_name in CAMERAS:
        video_path = args.output_dir / f"isaac41_{args.representation}_{camera_name}_720p.mp4"
        videos[camera_name] = _encode_video(
            args.output_dir / "frames" / camera_name,
            video_path,
            args.video_fps,
        )
        if videos[camera_name]["decoded_frame_count"] != len(frames):
            raise RuntimeError("video_frame_count_mismatch")
    result = {
        "schema": "labutopia.isaac41_wcsph_visual_replay.v1",
        "status": "passed",
        "claim_boundary": (
            "formal_isaac41_runtime_visual_only_replay_of_experimental_isaac601_wcsph_positions;"
            "zero_physics_steps;not_isaac41_physics_evidence"
        ),
        "runtime": dict(runtime),
        "representation": args.representation,
        "headless": True,
        "physics_step_calls": 0,
        "render_warmup_excluded": True,
        "camera_warmup_subframes": args.camera_warmup_subframes,
        "frame_count": int(len(frames)),
        "observation_index_span": [
            int(observation_indices[0]),
            int(observation_indices[-1]),
        ],
        "particle_count": int(frames.shape[1]),
        "resolution": [args.width, args.height],
        "fps": args.video_fps,
        "inputs": {
            "particle_frames": {"path": str(args.particle_frames), "sha256": _sha256_file(args.particle_frames)},
            "trajectory": {"path": str(args.trajectory_npz), "sha256": _sha256_file(args.trajectory_npz)},
            "packet": {"path": str(args.packet), "sha256": _sha256_file(args.packet)},
            "scene": {"path": str(args.scene), "sha256": _sha256_file(args.scene)},
        },
        "timing": {
            "render_mean_ms": float(sum(render_times) / len(render_times)),
            "reconstruction_mean_ms": float(sum(reconstruction_times) / len(reconstruction_times)),
        },
        "surface_partition": (
            None
            if args.representation != "surface"
            else {
                "connectivity_radius_m": args.surface_connectivity_radius_m,
                "minimum_mesh_particles": args.surface_min_mesh_particles,
                "small_components_rendered_as_particles": True,
                "maximum_residual_particle_count": max(
                    item["residual_particle_count"]
                    for item in surface_partition_diagnostics
                ),
                "maximum_meshed_component_count": max(
                    item["meshed_component_count"]
                    for item in surface_partition_diagnostics
                ),
            }
        ),
        "videos": videos,
        "review_frames": review_frames,
    }
    result["content_sha256"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    _atomic_json(args.output_dir / "result.json", result)
    return result


def _child_command(args: argparse.Namespace, request_path: Path) -> list[str]:
    return [
        str(FORMAL_ISAAC41_PYTHON), "-I", "-B", str(Path(__file__).resolve()), "--child",
        "--particle-frames", str(args.particle_frames),
        "--trajectory-npz", str(args.trajectory_npz),
        "--packet", str(args.packet), "--scene", str(args.scene),
        "--output-dir", str(args.output_dir), "--evidence-dir", str(args.evidence_dir),
        "--execution-request", str(request_path), "--representation", args.representation,
        "--width", str(args.width), "--height", str(args.height),
        "--video-fps", str(args.video_fps), "--rt-subframes", str(args.rt_subframes),
        "--stage-warmup-updates", str(args.stage_warmup_updates),
        "--camera-warmup-subframes", str(args.camera_warmup_subframes),
        "--particle-radius-m", str(args.particle_radius_m),
        "--surface-connectivity-radius-m", str(args.surface_connectivity_radius_m),
        "--surface-min-mesh-particles", str(args.surface_min_mesh_particles),
        "--start-frame", str(args.start_frame),
        "--max-frames", str(args.max_frames),
    ]


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
            "hide_ui": True,
            "width": args.width,
            "height": args.height,
            "renderer": "RayTracedLighting",
            "extra_args": ["--/rtx/raytracing/fractionalCutoutOpacity=true"],
        }
    )
    sys.argv = parsed_argv
    try:
        receipt = attestation.attest_existing_application(
            application=application,
            pre_app_numpy_modules=pre_app_numpy_modules,
            execution_request=request,
            source_paths=source_paths(),
        )
        receipt_path = args.evidence_dir / "runtime_receipt.json"
        attestation.write_canonical_json(receipt_path, receipt)
        binding = attestation.execution_binding_for_request(request, child_pid=os.getpid())
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        progress_path = args.evidence_dir / "child_task_progress.json"
        _atomic_json(
            progress_path,
            {
                "schema": "labutopia.isaac41_wcsph_replay_child_progress.v1",
                "status": "render_started",
                "child_pid": os.getpid(),
            },
        )
        try:
            _render(
                args,
                application=application,
                runtime={
                    "receipt_path": str(receipt_path),
                    "receipt_sha256": attestation.canonical_json_sha256(receipt),
                    "execution_binding": binding,
                },
            )
        except BaseException as error:
            _atomic_json(
                args.evidence_dir / "child_task_failure.json",
                {
                    "schema": "labutopia.isaac41_wcsph_replay_child_failure.v1",
                    "status": "render_failed",
                    "child_pid": os.getpid(),
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            raise
        _atomic_json(
            progress_path,
            {
                "schema": "labutopia.isaac41_wcsph_replay_child_progress.v1",
                "status": "render_completed",
                "child_pid": os.getpid(),
            },
        )
        return 0
    finally:
        application.close()


def _run_parent(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    if args.evidence_dir.exists():
        raise FileExistsError(f"evidence_dir_exists:{args.evidence_dir}")
    args.evidence_dir.mkdir(parents=True)
    source_before = attestation.capture_source_identity(source_paths())
    request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    request_path = args.evidence_dir / "execution_request.json"
    attestation.write_canonical_json(request_path, request)
    command = _child_command(args, request_path)
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=attestation.sealed_child_environment(args.evidence_dir / "runtime"),
        check=False,
    )
    result_path = args.output_dir / "result.json"
    receipt_path = args.evidence_dir / "runtime_receipt.json"
    verification_error = None
    try:
        receipt = attestation._read_canonical_json(receipt_path)
        attestation.require_matched_runtime_receipt(receipt)
        if completed.returncode != 0 or not result_path.is_file():
            raise RuntimeError(f"isaac41_replay_child_exit:{completed.returncode}")
    except BaseException as error:
        verification_error = {"type": type(error).__name__, "message": str(error)}
    manifest = {
        "schema": "labutopia.isaac41_wcsph_replay_parent_manifest.v1",
        "status": "passed" if verification_error is None else "blocked_runtime",
        "command": command,
        "child_returncode": completed.returncode,
        "source_before": source_before,
        "source_after": attestation.capture_source_identity(source_paths()),
        "runtime_receipt_sha256": _sha256_file(receipt_path) if receipt_path.is_file() else None,
        "result_sha256": _sha256_file(result_path) if result_path.is_file() else None,
        "verification_error": verification_error,
    }
    attestation.write_canonical_json(args.evidence_dir / "run_manifest.json", manifest)
    return 0 if verification_error is None else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--particle-frames", type=Path, required=True)
    parser.add_argument("--trajectory-npz", type=Path, required=True)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--representation", choices=("particles", "surface"), required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--video-fps", type=int, default=30)
    parser.add_argument("--rt-subframes", type=int, default=1)
    parser.add_argument("--stage-warmup-updates", type=int, default=64)
    parser.add_argument("--camera-warmup-subframes", type=int, default=8)
    parser.add_argument("--particle-radius-m", type=float, default=0.0023811016)
    parser.add_argument("--surface-connectivity-radius-m", type=float, default=0.006)
    parser.add_argument("--surface-min-mesh-particles", type=int, default=32)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=953)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in (
        "particle_frames", "trajectory_npz", "packet", "scene", "output_dir",
        "evidence_dir", "execution_request",
    ):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve())
    if args.child:
        if args.execution_request is None:
            raise ValueError("child_execution_request_required")
        return _run_child(args)
    if args.start_frame < 0 or args.start_frame > 952:
        raise ValueError("start_frame_out_of_range")
    if args.max_frames < 1 or args.start_frame + args.max_frames > 953:
        raise ValueError("max_frames_out_of_range")
    if args.camera_warmup_subframes < 1:
        raise ValueError("camera_warmup_subframes_must_be_positive")
    if args.surface_connectivity_radius_m <= 0.0:
        raise ValueError("surface_connectivity_radius_m_must_be_positive")
    if args.surface_min_mesh_particles < 4:
        raise ValueError("surface_min_mesh_particles_too_small")
    if args.execution_request is not None:
        raise ValueError("execution_request_is_child_only")
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
