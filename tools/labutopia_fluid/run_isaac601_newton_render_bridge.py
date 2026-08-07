#!/usr/bin/env python3
"""Isaac Sim 6.0.1 headless renderer for Newton MPM particle frames.

The process owns USD, RTX, surface reconstruction, surface authoring, and the
two 256x256 camera products.  Newton sends only float32 particle positions
through shared memory, so USD is never used as per-frame IPC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
NEWTON_POUR_RETARGET_OFFSET_M = (0.0187, -0.1310, 0.0)
NEWTON_POUR_RETARGET_BLEND = (500, 550)
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
REVIEW_FRAME_INDICES = frozenset({0, 300, 450, 580, 650, 750, 852, 952})
SURFACE_PATH = "/World/InternDataOnlineSurface"
RTX_DRIVER_VERIFY_DISABLE_ARG = "--/rtx/verifyDriverVersion/enabled=false"


RENDER_PROFILES = {
    "strict": {
        "renderer": "RealTimePathTracing",
        "capture_device": "cpu",
        "minimal_shading_mode": 0,
    },
    "cuda_rgb": {
        "renderer": "RealTimePathTracing",
        "capture_device": "cuda",
        "minimal_shading_mode": 0,
    },
    "minimal_textured": {
        "renderer": "MinimalRendering",
        "capture_device": "cuda",
        "minimal_shading_mode": 2,
    },
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _pose_matrix_gf(Gf: Any, pose: Any) -> Any:
    x, y, z, qx, qy, qz, qw = (float(value) for value in pose)
    quaternion = Gf.Quatd(qw, qx, qy, qz)
    matrix = Gf.Matrix4d(1.0)
    matrix.SetRotate(quaternion)
    matrix.SetTranslateOnly(Gf.Vec3d(x, y, z))
    return matrix


def _set_world_matrix(prim: Any, UsdGeom: Any, matrix: Any) -> None:
    xformable = UsdGeom.Xformable(prim)
    matrix_op = None
    for operation in xformable.GetOrderedXformOps():
        if operation.GetOpType() == UsdGeom.XformOp.TypeTransform:
            matrix_op = operation
            break
    if matrix_op is None:
        matrix_op = xformable.AddTransformOp(
            precision=UsdGeom.XformOp.PrecisionDouble,
            opSuffix="newtonBridge",
        )
    xformable.SetXformOpOrder([matrix_op], resetXformStack=True)
    matrix_op.Set(matrix)


def _apply_render_profile(args: argparse.Namespace) -> None:
    if args.render_profile is None:
        return
    profile = RENDER_PROFILES[args.render_profile]
    args.renderer = profile["renderer"]
    args.capture_device = profile["capture_device"]
    args.minimal_shading_mode = profile["minimal_shading_mode"]


def _simulation_launch_config(args: argparse.Namespace) -> dict[str, Any]:
    expected = _expected_effective_render_settings(args)
    extra_args = [f"--/rtx/rendermode={expected['render_mode']}"]
    if expected["minimal_shading_mode"] is not None:
        extra_args.append(
            "--/rtx/minimal/mode="
            f"{expected['minimal_shading_mode']}"
        )
    if args.allow_unvalidated_driver:
        extra_args.append(RTX_DRIVER_VERIFY_DISABLE_ARG)
    return {
        "headless": True,
        "hide_ui": True,
        "width": int(args.width),
        "height": int(args.height),
        "renderer": args.renderer,
        "minimal_shading_mode": int(args.minimal_shading_mode),
        "extra_args": extra_args,
    }


def _expected_effective_render_settings(
    args: argparse.Namespace,
) -> dict[str, Any]:
    renderer = str(args.renderer).lower()
    if renderer == "raytracedlighting":
        render_mode = "RaytracedLighting"
    elif renderer == "pathtracing":
        render_mode = "PathTracing"
    elif renderer == "realtimepathtracing":
        render_mode = "RealTimePathTracing"
    elif renderer in {"minimal", "minimalrendering"}:
        render_mode = "MinimalRendering"
    else:
        render_mode = str(args.renderer)
    return {
        "render_mode": render_mode,
        "minimal_shading_mode": (
            int(args.minimal_shading_mode)
            if render_mode == "MinimalRendering"
            else None
        ),
    }


def run(
    args: argparse.Namespace,
    *,
    application: Any | None = None,
    runtime_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if os.environ.get("ACCEPT_EULA") != "Y":
        raise RuntimeError("accept_eula_missing")
    if os.environ.get("OMNI_KIT_ACCEPT_EULA") != "YES":
        raise RuntimeError("omni_kit_accept_eula_missing")
    owns_application = application is None
    if application is None:
        from isaacsim import SimulationApp

        application = SimulationApp(_simulation_launch_config(args))
    server: socket.socket | None = None
    connection: socket.socket | None = None
    memory: Any = None
    resources: dict[str, dict[str, Any]] = {}
    try:
        import carb
        import numpy as np
        import omni.replicator.core as rep
        import omni.usd
        import warp as wp
        from PIL import Image
        from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from tools.labutopia_fluid.fluid_benchmark_bridge import (
            BRIDGE_SCHEMA,
            RENDER_BRIDGE_SCHEMA,
            SharedFluidFrame,
            SharedFluidRenderFrame,
            receive_message,
            send_message,
        )
        from tools.labutopia_fluid.fluid_benchmark_contract import (
            EXPECTED_PARTICLE_COUNT,
            load_packet,
            retarget_source_poses,
            summarize_milliseconds,
        )
        from tools.labutopia_fluid.interndata_surface_reconstruction import (
            reconstruct_surface_live,
        )
        from tools.labutopia_fluid.run_interndata_online_surface_probe import (
            author_live_surface_material,
            configure_live_visual_authority,
            update_live_surface_mesh,
        )
        from utils.online_fluid_surface import SurfaceFrameToken

        output_dir = args.output_dir.resolve()
        if output_dir.exists() and any(output_dir.iterdir()):
            raise FileExistsError(f"output_dir_not_empty:{output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        packet = load_packet(args.packet)
        recorded_source_poses = packet.array("source_poses_xyzw", (953, 7))
        if args.trajectory_npz is not None:
            with np.load(args.trajectory_npz.resolve(strict=True), allow_pickle=False) as archive:
                if tuple(archive.files) != ("source_poses_xyzw",):
                    raise ValueError("trajectory_archive_fields_invalid")
                source_poses = np.asarray(
                    archive["source_poses_xyzw"], dtype=np.float64
                )
            if source_poses.shape != recorded_source_poses.shape or not np.isfinite(source_poses).all():
                raise ValueError("trajectory_archive_values_invalid")
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

        context = omni.usd.get_context()
        if not context.open_stage(str(args.scene.resolve(strict=True))):
            raise RuntimeError("isaac_stage_open_failed")
        application.reset_render_settings()
        for _ in range(args.stage_warmup_updates):
            application.update()
        stage = context.get_stage()
        if stage is None:
            raise RuntimeError("isaac_stage_missing")
        source_prim = stage.GetPrimAtPath("/World/beaker2")
        if not source_prim or not source_prim.IsValid():
            raise RuntimeError("source_beaker_prim_missing")
        missing_cameras = [
            path
            for path in CAMERAS.values()
            if not stage.GetPrimAtPath(path).IsValid()
        ]
        if missing_cameras:
            raise RuntimeError(f"camera_prims_missing:{missing_cameras}")
        source_prim_initial_world = UsdGeom.XformCache().GetLocalToWorldTransform(
            source_prim
        )
        source_prim_from_recorded_com = (
            source_prim_initial_world
            * _pose_matrix_gf(Gf, source_poses[0]).GetInverse()
        )

        def bind_minimal_beaker_material(
            root_path: str,
            material_name: str,
            color: tuple[float, float, float],
        ) -> dict[str, Any]:
            material_path = f"/World/Looks/{material_name}"
            material = UsdShade.Material.Define(stage, material_path)
            shader = UsdShade.Shader.Define(
                stage, f"{material_path}/PreviewSurface"
            )
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput(
                "diffuseColor", Sdf.ValueTypeNames.Color3f
            ).Set(Gf.Vec3f(*color))
            shader.CreateInput(
                "emissiveColor", Sdf.ValueTypeNames.Color3f
            ).Set(Gf.Vec3f(*(component * 0.45 for component in color)))
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.28)
            shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
            material.CreateSurfaceOutput().ConnectToSource(
                shader.ConnectableAPI(), "surface"
            )
            root = stage.GetPrimAtPath(root_path)
            if not root or not root.IsValid():
                raise RuntimeError(f"minimal_visual_root_missing:{root_path}")
            bound_paths = []
            for prim in Usd.PrimRange(root):
                if not prim.IsA(UsdGeom.Gprim):
                    continue
                path = str(prim.GetPath())
                if "FluidSafeWrapperCanonical" in path:
                    continue
                UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
                bound_paths.append(path)
            if not bound_paths:
                raise RuntimeError(f"minimal_visual_gprims_missing:{root_path}")
            return {
                "root_path": root_path,
                "material_path": material_path,
                "color": list(color),
                "bound_gprims": bound_paths,
            }

        minimal_visual_aids = None
        if args.render_profile == "minimal_textured":
            minimal_visual_aids = {
                "policy": "minimal_mode_high_contrast_beakers_and_emissive_liquid_v1",
                "source_beaker": bind_minimal_beaker_material(
                    "/World/beaker2",
                    "MinimalSourceBeaker",
                    (0.95, 0.32, 0.08),
                ),
                "target_beaker": bind_minimal_beaker_material(
                    "/World/beaker1",
                    "MinimalTargetBeaker",
                    (0.08, 0.88, 0.34),
                ),
            }

        selected_cameras = dict(list(CAMERAS.items())[: int(args.camera_count)])
        for name, camera_path in selected_cameras.items():
            product = rep.create.render_product(
                camera_path,
                (int(args.width), int(args.height)),
            )
            rgb = rep.AnnotatorRegistry.get_annotator(
                "rgb", device=args.capture_device
            )
            rgb.attach(product)
            resources[name] = {"render_product": product, "rgb": rgb}

        expected_render_settings = _expected_effective_render_settings(args)
        render_setting_trace: list[dict[str, Any]] = []
        carb_settings = carb.settings.get_settings()

        def enforce_render_settings(phase: str, *, update: bool = False) -> None:
            # Render-product setup may overwrite Kit's launch-time mode. Reassert
            # the benchmark mode at the last boundary and fail closed if Kit does
            # not retain the requested setting.
            application.set_setting(
                "/rtx/rendermode",
                expected_render_settings["render_mode"],
            )
            if expected_render_settings["minimal_shading_mode"] is not None:
                application.set_setting(
                    "/rtx/minimal/mode",
                    expected_render_settings["minimal_shading_mode"],
                )
            if update:
                application.update()
            observed = {
                "phase": phase,
                "render_mode": carb_settings.get("/rtx/rendermode"),
                "minimal_shading_mode": carb_settings.get(
                    "/rtx/minimal/mode"
                ),
            }
            render_setting_trace.append(observed)
            if observed["render_mode"] != expected_render_settings["render_mode"]:
                raise RuntimeError(
                    "effective_renderer_mismatch:"
                    f"phase={phase}:expected={expected_render_settings['render_mode']}:"
                    f"actual={observed['render_mode']}"
                )
            if (
                expected_render_settings["minimal_shading_mode"] is not None
                and observed["minimal_shading_mode"]
                != expected_render_settings["minimal_shading_mode"]
            ):
                raise RuntimeError(
                    "effective_minimal_shading_mode_mismatch:"
                    f"phase={phase}:"
                    f"expected={expected_render_settings['minimal_shading_mode']}:"
                    f"actual={observed['minimal_shading_mode']}"
                )

        enforce_render_settings("after_render_product_setup", update=True)

        socket_path = args.bridge_socket.resolve()
        if socket_path.exists():
            raise FileExistsError(f"bridge_socket_exists:{socket_path}")
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(socket_path))
        server.listen(1)
        server.settimeout(args.bridge_timeout_s)
        ready_path = output_dir / "bridge_ready.json"
        _atomic_json(
            ready_path,
            {
                "schema": (
                    RENDER_BRIDGE_SCHEMA
                    if args.bridge_payload == "render-v2"
                    else BRIDGE_SCHEMA
                ),
                "socket": str(socket_path),
                "shared_memory_name": args.shared_memory_name,
                "particle_count": EXPECTED_PARTICLE_COUNT,
                "camera_paths": selected_cameras,
                "resolution": [args.width, args.height],
                "headless": True,
                "render_profile": args.render_profile,
                "capture_device": args.capture_device,
                "allow_unvalidated_driver": bool(
                    args.allow_unvalidated_driver
                ),
            },
        )
        print(
            json.dumps(
                {"status": "ready", "ready_path": str(ready_path)},
                sort_keys=True,
            ),
            flush=True,
        )

        memory = (
            SharedFluidRenderFrame.attach(args.shared_memory_name)
            if args.bridge_payload == "render-v2"
            else SharedFluidFrame.attach(args.shared_memory_name)
        )
        connection, _ = server.accept()
        connection.settimeout(args.bridge_timeout_s)
        hello = receive_message(connection)
        if (
            hello.get("schema")
            != (
                RENDER_BRIDGE_SCHEMA
                if args.bridge_payload == "render-v2"
                else BRIDGE_SCHEMA
            )
            or hello.get("type") != "hello"
            or hello.get("particle_count") != EXPECTED_PARTICLE_COUNT
        ):
            raise RuntimeError(f"bridge_hello_invalid:{hello}")
        requested_count = int(hello["observation_count"])
        if requested_count <= 0 or requested_count > 953:
            raise RuntimeError("bridge_observation_count_invalid")
        if args.bridge_payload == "render-v2":
            expected_representation = (
                "particles" if args.surface_mode == "particles" else "surface_gpu"
            )
            if hello.get("representation") != expected_representation:
                raise RuntimeError(
                    "bridge_representation_mismatch:"
                    f"expected={expected_representation}:actual={hello.get('representation')}"
                )
        send_message(
            connection,
            {
                "schema": (
                    RENDER_BRIDGE_SCHEMA
                    if args.bridge_payload == "render-v2"
                    else BRIDGE_SCHEMA
                ),
                "type": "hello_ack",
            },
        )

        reconstruction_times_ms: list[float] = []
        authoring_times_ms: list[float] = []
        render_times_ms: list[float] = []
        capture_times_ms: list[float] = []
        gpu_ready_times_ms: list[float] = []
        gpu_to_cpu_times_ms: list[float] = []
        frame_processing_times_ms: list[float] = []
        frame_records: list[dict[str, Any]] = []
        saved_frames: list[dict[str, Any]] = []
        deferred_review_frames: list[tuple[str, int, Any]] = []
        material_record = None
        authority_record = None
        static_surface = None
        static_authored = None
        particle_instancer = None
        residual_instancer = None

        def update_particle_instancer(positions: Any, token: Any) -> dict[str, Any]:
            nonlocal particle_instancer, material_record, authority_record
            if particle_instancer is None:
                particle_instancer = UsdGeom.PointInstancer.Define(
                    stage, SURFACE_PATH
                )
                prototype_scope = UsdGeom.Scope.Define(
                    stage, f"{SURFACE_PATH}/Prototypes"
                )
                del prototype_scope
                prototype_path = f"{SURFACE_PATH}/Prototypes/Sphere"
                prototype = UsdGeom.Sphere.Define(stage, prototype_path)
                prototype.CreateRadiusAttr().Set(
                    float(packet.manifest["fluid"]["particle_radius_m"])
                )
                particle_instancer.CreatePrototypesRel().SetTargets(
                    [Sdf.Path(prototype_path)]
                )
                particle_instancer.CreateProtoIndicesAttr().Set(
                    Vt.IntArray([0] * EXPECTED_PARTICLE_COUNT)
                )
                material_record = author_live_surface_material(stage)
                particle_material = UsdShade.Material.Get(
                    stage, material_record["material_path"]
                )
                UsdShade.MaterialBindingAPI.Apply(prototype.GetPrim()).Bind(
                    particle_material
                )
                particle_shader = UsdShade.Shader.Get(
                    stage,
                    f"{material_record['material_path']}/PreviewSurface",
                )
                particle_shader.GetInput("diffuseColor").Set(
                    Gf.Vec3f(0.08, 0.72, 0.95)
                )
                particle_shader.GetInput("emissiveColor").Set(
                    Gf.Vec3f(
                        0.08 if args.render_profile == "minimal_textured" else 0.01,
                        0.72 if args.render_profile == "minimal_textured" else 0.08,
                        0.95 if args.render_profile == "minimal_textured" else 0.12,
                    )
                )
                particle_shader.GetInput("opacity").Set(1.0)
                particle_shader.GetInput("roughness").Set(0.12)
                material_record["particle_display_opacity"] = 1.0
                material_record["bound_directly_to_prototype"] = True
                authority_record = configure_live_visual_authority(stage)
            contiguous = np.ascontiguousarray(positions, dtype=np.float32)
            converter = getattr(Vt.Vec3fArray, "FromNumpy", None)
            values = (
                converter(contiguous)
                if converter is not None
                else Vt.Vec3fArray(
                    [Gf.Vec3f(*row) for row in contiguous.tolist()]
                )
            )
            particle_instancer.CreatePositionsAttr().Set(values)
            particle_instancer.GetPrim().CreateAttribute(
                "labutopia:surfaceFrameToken",
                Sdf.ValueTypeNames.String,
                custom=True,
            ).Set(token.identity)
            return {
                "path": SURFACE_PATH,
                "surface_token": token.identity,
                "vertex_count": EXPECTED_PARTICLE_COUNT,
                "face_count": 0,
                "particle_radius_m": float(
                    packet.manifest["fluid"]["particle_radius_m"]
                ),
                "representation": "UsdGeomPointInstancerSpherePrototype",
            }

        def surface_mesh_data(vertices: Any, indices: Any) -> dict[str, Any]:
            authored_vertices = np.ascontiguousarray(vertices, dtype=np.float32)
            faces = np.ascontiguousarray(indices, dtype=np.int32).reshape((-1, 3))
            if len(authored_vertices) < 3 or len(faces) < 1:
                raise ValueError("bridge_surface_mesh_empty")
            triangles = authored_vertices[faces]
            face_normals = np.cross(
                triangles[:, 1] - triangles[:, 0],
                triangles[:, 2] - triangles[:, 0],
            )
            normals = np.zeros_like(authored_vertices)
            for corner in range(3):
                np.add.at(normals, faces[:, corner], face_normals)
            lengths = np.linalg.norm(normals, axis=1)
            valid = lengths > 1.0e-12
            normals[valid] /= lengths[valid, None]
            normals[~valid] = np.asarray((0.0, 0.0, 1.0), dtype=np.float32)
            geometry_hash = hashlib.sha256()
            geometry_hash.update(authored_vertices.astype("<f4", copy=False).tobytes())
            geometry_hash.update(faces.astype("<i4", copy=False).tobytes())
            return {
                "vertices": authored_vertices,
                "faces": faces,
                "normals": normals,
                "origin_world_m": [0.0, 0.0, 0.0],
                "geometry_sha256": geometry_hash.hexdigest(),
            }

        def tune_minimal_liquid_material() -> None:
            if args.render_profile != "minimal_textured":
                return
            shader = UsdShade.Shader.Get(
                stage,
                f"{material_record['material_path']}/PreviewSurface",
            )
            shader.GetInput("diffuseColor").Set(Gf.Vec3f(0.08, 0.72, 0.95))
            shader.GetInput("emissiveColor").Set(Gf.Vec3f(0.08, 0.72, 0.95))
            shader.GetInput("opacity").Set(1.0)
            shader.GetInput("roughness").Set(0.22)
            material_record["minimal_high_contrast_emissive"] = True

        def update_residual_instancer(positions: Any, token: Any) -> dict[str, Any]:
            nonlocal residual_instancer
            residual_path = f"{SURFACE_PATH}Residuals"
            if residual_instancer is None:
                residual_instancer = UsdGeom.PointInstancer.Define(stage, residual_path)
                UsdGeom.Scope.Define(stage, f"{residual_path}/Prototypes")
                prototype_path = f"{residual_path}/Prototypes/Sphere"
                prototype = UsdGeom.Sphere.Define(stage, prototype_path)
                prototype.CreateRadiusAttr().Set(
                    float(packet.manifest["fluid"]["particle_radius_m"])
                )
                residual_instancer.CreatePrototypesRel().SetTargets(
                    [Sdf.Path(prototype_path)]
                )
                particle_material = UsdShade.Material.Get(
                    stage, material_record["material_path"]
                )
                UsdShade.MaterialBindingAPI.Apply(prototype.GetPrim()).Bind(
                    particle_material
                )
            contiguous = np.ascontiguousarray(positions, dtype=np.float32)
            converter = getattr(Vt.Vec3fArray, "FromNumpy", None)
            values = (
                converter(contiguous)
                if converter is not None
                else Vt.Vec3fArray([Gf.Vec3f(*row) for row in contiguous.tolist()])
            )
            residual_instancer.CreatePositionsAttr().Set(values)
            residual_instancer.CreateProtoIndicesAttr().Set(
                Vt.IntArray([0] * len(contiguous))
            )
            residual_instancer.GetPrim().CreateAttribute(
                "labutopia:surfaceFrameToken",
                Sdf.ValueTypeNames.String,
                custom=True,
            ).Set(token.identity)
            return {"path": residual_path, "particle_count": int(len(contiguous))}

        while True:
            message = receive_message(connection)
            message_type = message.get("type")
            if message_type == "complete":
                if message.get("observation_count") != requested_count:
                    raise RuntimeError("bridge_complete_count_mismatch")
                send_message(
                    connection,
                    {
                        "schema": (
                            RENDER_BRIDGE_SCHEMA
                            if args.bridge_payload == "render-v2"
                            else BRIDGE_SCHEMA
                        ),
                        "type": "complete_ack",
                    },
                )
                break
            if message_type != "frame":
                raise RuntimeError(f"bridge_message_type_invalid:{message_type}")
            observation_index = int(message["frame_index"])
            frame_processing_started = time.perf_counter()
            if observation_index != len(frame_records):
                raise RuntimeError(
                    "bridge_frame_not_contiguous:"
                    f"expected={len(frame_records)}:actual={observation_index}"
                )
            frame_payload, shared_record = memory.read(
                expected_frame_index=observation_index
            )
            if (
                int(message["checksum_crc32"])
                != shared_record["checksum_crc32"]
            ):
                raise RuntimeError("bridge_message_checksum_mismatch")
            _set_world_matrix(
                source_prim,
                UsdGeom,
                source_prim_from_recorded_com
                * _pose_matrix_gf(Gf, source_poses[observation_index]),
            )

            if args.bridge_payload == "render-v2":
                if shared_record["representation"] == "particles":
                    positions = frame_payload["positions"]
                    residual_positions = np.empty((0, 3), dtype=np.float32)
                else:
                    positions = None
                    residual_positions = frame_payload["residual_positions"]
            else:
                positions = frame_payload
                residual_positions = np.empty((0, 3), dtype=np.float32)

            if positions is not None:
                position_hash = hashlib.sha256(
                    np.ascontiguousarray(positions, dtype="<f4").tobytes()
                ).hexdigest()
            else:
                position_digest = hashlib.sha256()
                position_digest.update(
                    np.ascontiguousarray(frame_payload["vertices"], dtype="<f4").tobytes()
                )
                position_digest.update(
                    np.ascontiguousarray(frame_payload["indices"], dtype="<i4").tobytes()
                )
                position_digest.update(
                    np.ascontiguousarray(residual_positions, dtype="<f4").tobytes()
                )
                position_hash = position_digest.hexdigest()

            reconstruct_this_frame = args.surface_mode in {"dynamic", "static-first"} and (
                args.surface_mode == "dynamic" or static_surface is None
            )
            if args.surface_mode == "particles":
                surface = {
                    "geometry_sha256": hashlib.sha256(
                        f"particle-instancer-v1:{position_hash}".encode("ascii")
                    ).hexdigest()
                }
                reconstruction_times_ms.append(0.0)
            elif args.surface_mode == "surface-shm":
                surface = surface_mesh_data(
                    frame_payload["vertices"], frame_payload["indices"]
                )
                reconstruction_times_ms.append(0.0)
            elif reconstruct_this_frame:
                reconstruction_started = time.perf_counter()
                surface = reconstruct_surface_live(positions)
                reconstruction_times_ms.append(
                    (time.perf_counter() - reconstruction_started) * 1000.0
                )
                if args.surface_mode == "static-first":
                    static_surface = surface
            else:
                surface = static_surface
                reconstruction_times_ms.append(0.0)

            identity = _canonical_sha256(
                {
                    "episode_id": "newton140_mpm_bridge",
                    "observation_index": observation_index,
                    "position_sha256": position_hash,
                    "surface_geometry_sha256": surface["geometry_sha256"],
                }
            )
            token = SurfaceFrameToken(
                episode_id="newton140_mpm_bridge",
                observation_index=observation_index,
                caused_by_action_index=(
                    None if observation_index == 0 else observation_index - 1
                ),
                logical_step_before=observation_index * 4,
                logical_step_after=(observation_index + 1) * 4,
                integration_step_before=observation_index * 4,
                integration_step_after=(observation_index + 1) * 4,
                simulation_time_before=observation_index / 30.0,
                simulation_time_after=(observation_index + 1) / 30.0,
                action_sha256=None,
                particle_count=EXPECTED_PARTICLE_COUNT,
                position_sha256=position_hash,
                surface_geometry_sha256=surface["geometry_sha256"],
                identity=identity,
                positions=(positions if positions is not None else residual_positions),
            )
            if args.surface_mode == "particles":
                authoring_started = time.perf_counter()
                authored = update_particle_instancer(positions, token)
                authoring_times_ms.append(
                    (time.perf_counter() - authoring_started) * 1000.0
                )
            elif args.surface_mode == "surface-shm":
                authoring_started = time.perf_counter()
                authored = update_live_surface_mesh(stage, surface, token)
                if material_record is None:
                    material_record = author_live_surface_material(stage)
                    tune_minimal_liquid_material()
                    authority_record = configure_live_visual_authority(stage)
                residual_authored = update_residual_instancer(
                    residual_positions, token
                )
                authored["residual_particles"] = residual_authored
                authoring_times_ms.append(
                    (time.perf_counter() - authoring_started) * 1000.0
                )
            elif reconstruct_this_frame:
                authoring_started = time.perf_counter()
                authored = update_live_surface_mesh(stage, surface, token)
                if material_record is None:
                    material_record = author_live_surface_material(stage)
                    tune_minimal_liquid_material()
                    authority_record = configure_live_visual_authority(stage)
                authoring_times_ms.append(
                    (time.perf_counter() - authoring_started) * 1000.0
                )
                if args.surface_mode == "static-first":
                    static_authored = authored
            else:
                authored = static_authored
                authoring_times_ms.append(0.0)

            enforce_render_settings(
                f"before_frame_{observation_index:04d}", update=False
            )
            render_started = time.perf_counter()
            rep.orchestrator.step(
                rt_subframes=int(args.rt_subframes),
                pause_timeline=True,
                delta_time=0.0,
            )
            rep.orchestrator.wait_until_complete()
            render_times_ms.append(
                (time.perf_counter() - render_started) * 1000.0
            )
            enforce_render_settings(
                f"after_frame_{observation_index:04d}", update=False
            )

            capture_started = time.perf_counter()
            raw_frames: dict[str, Any] = {}
            for name, resource in resources.items():
                raw = resource["rgb"].get_data(device=args.capture_device)
                raw_shape = tuple(int(value) for value in raw.shape)
                if raw_shape[:2] != (args.height, args.width):
                    raise RuntimeError(
                        f"camera_frame_shape_invalid:{name}:{raw_shape}"
                    )
                raw_frames[name] = raw
            if args.capture_device == "cuda":
                wp.synchronize()
                gpu_ready_finished = time.perf_counter()
                gpu_ready_times_ms.append(
                    (gpu_ready_finished - capture_started) * 1000.0
                )
                copy_started = gpu_ready_finished
                host_frames = {
                    name: np.asarray(raw.numpy())
                    for name, raw in raw_frames.items()
                }
                gpu_to_cpu_times_ms.append(
                    (time.perf_counter() - copy_started) * 1000.0
                )
            else:
                host_frames = {
                    name: np.asarray(raw) for name, raw in raw_frames.items()
                }
            captured: dict[str, Any] = {}
            for name, raw in host_frames.items():
                rgb = np.ascontiguousarray(raw[..., :3], dtype=np.uint8)
                captured[name] = {
                    "sha256": hashlib.sha256(rgb.tobytes()).hexdigest(),
                    "mean_rgb": rgb.reshape((-1, 3)).mean(axis=0).tolist(),
                }
                if args.save_all_rgb:
                    sequence_path = (
                        output_dir
                        / "rgb_sequences"
                        / name
                        / f"frame_{observation_index:04d}.png"
                    )
                    sequence_path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(rgb, mode="RGB").save(
                        sequence_path,
                        compress_level=1,
                    )
                if (
                    observation_index in REVIEW_FRAME_INDICES
                    or observation_index == requested_count - 1
                ):
                    deferred_review_frames.append(
                        (name, observation_index, rgb.copy())
                    )
            capture_times_ms.append(
                (time.perf_counter() - capture_started) * 1000.0
            )
            frame_records.append(
                {
                    "observation_index": observation_index,
                    "shared_memory": shared_record,
                    "surface": {
                        "geometry_sha256": surface["geometry_sha256"],
                        "vertex_count": authored["vertex_count"],
                        "face_count": authored["face_count"],
                        "identity": identity,
                        "mode": args.surface_mode,
                        "reused": (
                            args.surface_mode == "static-first"
                            and not reconstruct_this_frame
                        ),
                    },
                    "cameras": captured,
                }
            )
            send_message(
                connection,
                {
                    "schema": (
                        RENDER_BRIDGE_SCHEMA
                        if args.bridge_payload == "render-v2"
                        else BRIDGE_SCHEMA
                    ),
                    "type": "frame_ack",
                    "frame_index": observation_index,
                },
            )
            frame_processing_times_ms.append(
                (time.perf_counter() - frame_processing_started) * 1000.0
            )

        if len(frame_records) != requested_count:
            raise RuntimeError(
                "rendered_frame_count_mismatch:"
                f"expected={requested_count}:actual={len(frame_records)}"
            )
        for name, observation_index, rgb in deferred_review_frames:
            image_path = (
                output_dir
                / "review_frames"
                / name
                / f"frame_{observation_index:04d}.png"
            )
            image_path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(rgb, mode="RGB").save(image_path)
            saved_frames.append(
                {
                    "camera": name,
                    "observation_index": observation_index,
                    "path": str(image_path),
                    "sha256": _sha256_file(image_path),
                }
            )
        records_path = output_dir / "render_frames.jsonl"
        records_path.write_text(
            "".join(
                json.dumps(record, sort_keys=True, allow_nan=False) + "\n"
                for record in frame_records
            ),
            encoding="utf-8",
        )
        timing_arrays_path = output_dir / "render_timing_arrays.npz"
        np.savez_compressed(
            timing_arrays_path,
            reconstruction_ms=np.asarray(
                reconstruction_times_ms, dtype=np.float64
            ),
            usd_authoring_ms=np.asarray(authoring_times_ms, dtype=np.float64),
            rtx_render_ms=np.asarray(render_times_ms, dtype=np.float64),
            camera_host_ready_ms=np.asarray(
                capture_times_ms, dtype=np.float64
            ),
            camera_gpu_ready_ms=np.asarray(
                gpu_ready_times_ms, dtype=np.float64
            ),
            camera_gpu_to_cpu_ms=np.asarray(
                gpu_to_cpu_times_ms, dtype=np.float64
            ),
            frame_processing_ms=np.asarray(
                frame_processing_times_ms, dtype=np.float64
            ),
        )
        result = {
            "schema": (
                "labutopia.isaac41_newton_render_bridge_result.v1"
                if args.runtime_label == "isaac41"
                else "labutopia.isaac601_newton_render_bridge_result.v1"
            ),
            "status": "passed",
            "claim_boundary": (
                f"experimental_{args.runtime_label}_headless_render_lane;"
                "hybrid_newton140_particle_source;"
                "visual_review_not_independent"
            ),
            "runtime": runtime_record,
            "headless": True,
            "renderer": args.renderer,
            "render_profile": args.render_profile,
            "render_profile_semantics": (
                "isaac601_native_rtx_realtime_2_not_renderer_identical_to_isaac41"
                if args.render_profile in {"strict", "cuda_rgb"}
                else "isaac601_minimal_textured_mode_2"
                if args.render_profile == "minimal_textured"
                else "custom"
            ),
            "capture_device": args.capture_device,
            "minimal_shading_mode": int(args.minimal_shading_mode),
            "driver_override": {
                "requested": bool(args.allow_unvalidated_driver),
                "setting": (
                    RTX_DRIVER_VERIFY_DISABLE_ARG
                    if args.allow_unvalidated_driver
                    else None
                ),
                "effective_verify_driver_version_enabled": (
                    carb.settings.get_settings().get(
                        "/rtx/verifyDriverVersion/enabled"
                    )
                ),
            },
            "effective_renderer": {
                "expected": expected_render_settings,
                "render_mode": carb_settings.get("/rtx/rendermode"),
                "minimal_shading_mode": carb_settings.get("/rtx/minimal/mode"),
                "setting_trace": render_setting_trace,
            },
            "camera_paths": selected_cameras,
            "camera_count": int(args.camera_count),
            "camera_resolution": [args.width, args.height],
            "surface_mode": args.surface_mode,
            "bridge_payload": args.bridge_payload,
            "particle_count": EXPECTED_PARTICLE_COUNT,
            "observation_count": requested_count,
            "media_generation": {
                "save_all_rgb": bool(args.save_all_rgb),
                "performance_evidence_eligible": not bool(args.save_all_rgb),
                "png_encoding_in_timed_frame_loop": bool(args.save_all_rgb),
            },
            "rt_subframes": args.rt_subframes,
            "source_motion_policy": (
                "validated_trajectory_archive"
                if args.trajectory_npz is not None
                else "recorded_orientation_with_newton_pour_alignment_v1"
                if args.pour_retarget
                else "recorded_pose_exact"
            ),
            "trajectory": (
                {
                    "path": str(args.trajectory_npz),
                    "sha256": _sha256_file(args.trajectory_npz),
                }
                if args.trajectory_npz is not None
                else None
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
            "timing": {
                "schema": "labutopia.newton_render_timing.v2",
                "warmup_observations_excluded": (
                    1 if len(frame_processing_times_ms) > 1 else 0
                ),
                "reconstruction": summarize_milliseconds(
                    reconstruction_times_ms[1:]
                    if len(reconstruction_times_ms) > 1
                    else reconstruction_times_ms
                ),
                "usd_authoring": summarize_milliseconds(
                    authoring_times_ms[1:]
                    if len(authoring_times_ms) > 1
                    else authoring_times_ms
                ),
                "rtx_render": summarize_milliseconds(
                    render_times_ms[1:]
                    if len(render_times_ms) > 1
                    else render_times_ms
                ),
                "camera_capture": summarize_milliseconds(
                    capture_times_ms[1:]
                    if len(capture_times_ms) > 1
                    else capture_times_ms
                ),
                "camera_gpu_ready": (
                    summarize_milliseconds(
                        gpu_ready_times_ms[1:]
                        if len(gpu_ready_times_ms) > 1
                        else gpu_ready_times_ms
                    )
                    if gpu_ready_times_ms
                    else None
                ),
                "camera_gpu_to_cpu": (
                    summarize_milliseconds(
                        gpu_to_cpu_times_ms[1:]
                        if len(gpu_to_cpu_times_ms) > 1
                        else gpu_to_cpu_times_ms
                    )
                    if gpu_to_cpu_times_ms
                    else None
                ),
                "frame_processing": summarize_milliseconds(
                    frame_processing_times_ms[1:]
                    if len(frame_processing_times_ms) > 1
                    else frame_processing_times_ms
                ),
            },
            "material": material_record,
            "visual_authority": authority_record,
            "minimal_visual_aids": minimal_visual_aids,
            "packet": {
                "path": str(packet.manifest_path),
                "sha256": _sha256_file(packet.manifest_path),
            },
            "scene": {
                "path": str(args.scene.resolve(strict=True)),
                "sha256": _sha256_file(args.scene.resolve(strict=True)),
            },
            "artifacts": {
                "render_frames": {
                    "path": str(records_path),
                    "sha256": _sha256_file(records_path),
                },
                "render_timing_arrays": {
                    "path": str(timing_arrays_path),
                    "sha256": _sha256_file(timing_arrays_path),
                },
                "saved_review_frames": saved_frames,
                "rgb_sequences": (
                    {
                        name: {
                            "directory": str(
                                output_dir / "rgb_sequences" / name
                            ),
                            "frame_count": requested_count,
                            "filename_pattern": "frame_%04d.png",
                        }
                        for name in selected_cameras
                    }
                    if args.save_all_rgb
                    else None
                ),
            },
        }
        result["content_sha256"] = _canonical_sha256(result)
        result_path = output_dir / "result.json"
        _atomic_json(result_path, result)
        print(
            json.dumps(
                {"status": "passed", "result_path": str(result_path)},
                sort_keys=True,
            ),
            flush=True,
        )
        return result
    finally:
        for resource in resources.values():
            try:
                resource["rgb"].detach()
                resource["render_product"].destroy()
            except Exception:
                pass
        if connection is not None:
            connection.close()
        if memory is not None:
            memory.close()
        if server is not None:
            server.close()
        if args.bridge_socket.exists():
            args.bridge_socket.unlink()
        if owns_application:
            application.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--scene", type=Path, default=DEFAULT_SCENE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bridge-socket", type=Path, required=True)
    parser.add_argument("--shared-memory-name", required=True)
    parser.add_argument(
        "--bridge-payload",
        choices=("positions-v1", "render-v2"),
        default="positions-v1",
    )
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--renderer", default="RayTracedLighting")
    parser.add_argument(
        "--render-profile", choices=tuple(RENDER_PROFILES), default=None
    )
    parser.add_argument(
        "--capture-device", choices=("cpu", "cuda"), default="cpu"
    )
    parser.add_argument("--minimal-shading-mode", type=int, default=0)
    parser.add_argument("--allow-unvalidated-driver", action="store_true")
    parser.add_argument("--save-all-rgb", action="store_true")
    parser.add_argument("--rt-subframes", type=int, default=1)
    parser.add_argument("--camera-count", type=int, choices=(1, 2), default=2)
    parser.add_argument(
        "--surface-mode",
        choices=("dynamic", "static-first", "particles", "surface-shm"),
        default="dynamic",
    )
    parser.add_argument("--trajectory-npz", type=Path)
    parser.add_argument(
        "--runtime-label",
        choices=("isaac601", "isaac41"),
        default="isaac601",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--pour-retarget",
        action=argparse.BooleanOptionalAction,
        default=True,
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
    parser.add_argument("--stage-warmup-updates", type=int, default=64)
    parser.add_argument("--bridge-timeout-s", type=float, default=120.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _apply_render_profile(args)
    if args.bridge_payload == "render-v2" and args.surface_mode not in {
        "particles",
        "surface-shm",
    }:
        parser.error("render-v2 requires particles or surface-shm mode")
    if args.bridge_payload == "positions-v1" and args.surface_mode == "surface-shm":
        parser.error("surface-shm requires render-v2 payload")
    if args.trajectory_npz is not None:
        args.trajectory_npz = args.trajectory_npz.resolve()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
