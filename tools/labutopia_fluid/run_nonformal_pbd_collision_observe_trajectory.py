#!/usr/bin/env python3
"""Run the native pick-and-pour command path while recording collisions only.

This is a diagnostic-only runner. It never attaches the source vessel, never
writes its pose, and never treats command completion as a grasp or task pass.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import traceback
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import nonformal_collision_observe as observe
from tools.labutopia_fluid import run_nonformal_pbd_direct_contact_probe as probe


FORMAL_ISAAC41_PYTHON = probe.FORMAL_ISAAC41_PYTHON
DEFAULT_CONFIG = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_collision_observe_full_pbd_v1.yaml"
)
HAND_BODY_PATH = "/World/Franka/panda_hand"


def _source_paths(attester_path: Path) -> tuple[Path, ...]:
    return (
        Path(attester_path),
        Path(__file__),
        REPO_ROOT / "tools/labutopia_fluid/nonformal_collision_observe.py",
        REPO_ROOT / "tools/labutopia_fluid/run_nonformal_pbd_direct_contact_probe.py",
        REPO_ROOT / "controllers/atomic_actions/pick_controller.py",
        REPO_ROOT / "controllers/atomic_actions/pour_controller.py",
        REPO_ROOT / "robots/franka/rmpflow_controller.py",
        REPO_ROOT / "utils/isaac_fluid_evaluation.py",
    )


def _attestation_module() -> Any:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime

    return attest_isaac41_effective_runtime


def _write_trace(
    stream: Any,
    digest: Any,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    payload = json.dumps(
        probe._json_native(dict(record)),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    stream.write(payload + b"\n")
    digest.update(payload + b"\n")
    return {"sha256": hashlib.sha256(payload).hexdigest()}


def _enabled_colliders(stage: Any, root_path: str) -> list[str]:
    from pxr import Usd, UsdPhysics

    root = stage.GetPrimAtPath(root_path)
    if not root or not root.IsValid():
        raise RuntimeError(f"collision_observe_collider_root_missing:{root_path}")
    paths = []
    for prim in Usd.PrimRange(root):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = prim.GetAttribute("physics:collisionEnabled")
        if enabled and enabled.Get() is False:
            continue
        paths.append(str(prim.GetPath()))
    if not paths:
        raise RuntimeError(f"collision_observe_colliders_missing:{root_path}")
    return sorted(set(paths))


def _record_action(action: Any, np: Any) -> dict[str, Any] | None:
    if action is None:
        return None
    result: dict[str, Any] = {}
    for name in (
        "joint_positions",
        "joint_velocities",
        "joint_efforts",
        "joint_indices",
    ):
        value = getattr(action, name, None)
        if value is None:
            result[name] = None
            continue
        array = np.asarray(value, dtype=np.float64)
        if array.ndim != 1 or np.isinf(array).any():
            raise RuntimeError(f"collision_observe_action_invalid:{name}")
        if name == "joint_indices":
            if np.isnan(array).any() or not np.equal(array, np.floor(array)).all():
                raise RuntimeError(f"collision_observe_action_invalid:{name}")
            result[name] = array.astype(np.int64).tolist()
        else:
            result[name] = [
                None if np.isnan(value) else float(value) for value in array.tolist()
            ]
    return result


def _artifact(path: Path, *, root: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return {
        "path": str(path.relative_to(root)),
        "byte_count": path.stat().st_size,
        "sha256": probe._sha256_file(path),
    }


def _runtime_trajectory(
    args: argparse.Namespace,
    runtime: Mapping[str, Any],
    *,
    app: Any,
) -> dict[str, Any]:
    trace_path = args.out_dir / "direct_physx_reports.jsonl.gz"
    action_path = args.out_dir / "action_ledger.jsonl"
    video_dir = args.out_dir / "video"
    trace_stream = None
    action_stream = None
    video_writer = None
    trace_digest = hashlib.sha256()
    action_digest = hashlib.sha256()
    trace_count = 0
    action_count = 0
    try:
        from isaacsim_compat import install_legacy_isaacsim_aliases

        install_legacy_isaacsim_aliases()
        import cv2
        import numpy as np
        import omni.physx
        import omni.usd
        from isaacsim.core.api import World
        from isaacsim.core.prims import SingleRigidPrim
        from isaacsim.core.utils.stage import add_reference_to_stage
        from omni.physx import get_physx_simulation_interface
        from pxr import PhysxSchema, PhysicsSchemaTools, Sdf, Usd, UsdUtils, UsdPhysics
        from scipy.spatial.transform import Rotation

        from controllers.atomic_actions.pick_controller import PickController
        from controllers.atomic_actions.pour_controller import PourController
        from factories.robot_factory import create_robot
        from factories.task_factory import create_task
        from robots.franka.rmpflow_controller import RMPFlowController
        from utils.fluid_evaluation_loop import fluid_control_dt, model_camera_video_rgb
        from utils.isaac_fluid_evaluation import (
            PhysicsSourceStateAdapter,
            SourceBodyWriterAudit,
            configure_contact_grasp_scene,
            configure_fluid_world_timing,
            configure_particle_usd_readback,
            construct_single_rigid_prim,
            validate_fluid_stage_contract,
        )
        from utils.object_utils import ObjectUtils

        cfg, config_closure = probe.load_composed_config(args.config)
        from omegaconf import OmegaConf

        # The task contract does not consume Hydra's output-dir interpolation.
        # Resolving it here would fail before any diagnostic physics can start.
        config_value = OmegaConf.to_container(cfg, resolve=False)
        observe.validate_current_trajectory_config(config_value)
        fluid = cfg.online_fluid
        asset_path = (REPO_ROOT / str(cfg.usd_path)).resolve()
        robot_asset_path = (REPO_ROOT / str(cfg.robot.usd_path)).resolve()
        if not asset_path.is_file() or not robot_asset_path.is_file():
            raise FileNotFoundError("collision_observe_input_asset_missing")
        input_closure = dict(
            sorted(
                {
                    **config_closure,
                    str(asset_path): probe._stable_file_bytes(asset_path)[1],
                    str(robot_asset_path): probe._stable_file_bytes(robot_asset_path)[1],
                }.items()
            )
        )

        configure_particle_usd_readback()
        stage = omni.usd.get_context().get_stage()
        add_reference_to_stage(usd_path=str(asset_path), prim_path="/World")
        world = World(
            physics_dt=float(fluid.physics_dt),
            rendering_dt=float(fluid.rendering_dt),
            stage_units_in_meters=1.0,
            physics_prim_path=str(fluid.physics_scene_path),
            set_defaults=False,
            backend="numpy",
            device="cpu",
        )
        omni.physx.get_physx_interface().overwrite_gpu_setting(1)
        configure_particle_usd_readback()
        configure_fluid_world_timing(
            world,
            physics_dt=float(fluid.physics_dt),
            rendering_dt=float(fluid.rendering_dt),
        )
        simulation = get_physx_simulation_interface()
        robot = create_robot(
            str(cfg.robot.type),
            position=np.asarray(cfg.robot.position, dtype=np.float64),
            usd_path=str(robot_asset_path),
            camera_frequency=int(cfg.robot.camera_frequency),
        )

        session = stage.GetSessionLayer()
        if session is None:
            raise RuntimeError("collision_observe_session_layer_missing")
        layer = Sdf.Layer.CreateAnonymous("collision_observe_trajectory.usda")
        if layer is None:
            raise RuntimeError("collision_observe_session_layer_create_failed")
        session.subLayerPaths.insert(0, layer.identifier)
        previous_target = stage.GetEditTarget()
        try:
            stage.SetEditTarget(Usd.EditTarget(layer))
            configure_contact_grasp_scene(stage, fluid)
            source_path = str(fluid.source_actor_path)
            robot_root = stage.GetPrimAtPath("/World/Franka")
            if not robot_root or not robot_root.IsValid():
                raise RuntimeError("collision_observe_robot_root_missing")
            robot_body_paths = tuple(
                sorted(
                    str(prim.GetPath())
                    for prim in Usd.PrimRange(robot_root)
                    if prim.HasAPI(UsdPhysics.RigidBodyAPI)
                    and (
                        not prim.GetAttribute("physics:rigidBodyEnabled")
                        or prim.GetAttribute("physics:rigidBodyEnabled").Get()
                        is not False
                    )
                )
            )
            for path in (source_path, *robot_body_paths):
                prim = stage.GetPrimAtPath(path)
                if not prim or not prim.IsValid():
                    raise RuntimeError(f"collision_observe_report_body_missing:{path}")
                api = PhysxSchema.PhysxContactReportAPI.Apply(prim)
                api.CreateThresholdAttr().Set(0.0)
                api.CreateReportPairsRel().ClearTargets(True)
        finally:
            stage.SetEditTarget(previous_target)
        simulation.flush_changes()

        ObjectUtils.get_instance(stage)
        task = create_task(
            str(cfg.task_type), cfg=cfg, world=world, stage=stage, robot=robot
        )
        task.reset()
        source_path = str(fluid.source_actor_path)
        source_body = construct_single_rigid_prim(
            SingleRigidPrim,
            prim_path=source_path,
            name="collision_observe_source_reader",
        )
        source_body.initialize()
        source_state = PhysicsSourceStateAdapter(
            read_source_world_pose=source_body.get_world_pose,
            initial_geometry_center_world=task.object_utils.get_geometry_center(
                object_path=source_path
            ),
        )
        writer_audit = SourceBodyWriterAudit(source_body_path=source_path)
        writer_audit.install(source_body=source_body, object_utils=task.object_utils)
        writer_audit.reset()
        source_stage_contract = validate_fluid_stage_contract(stage, fluid)
        source_mesh_path = str(fluid.source_external_shell_path)
        source_mesh = stage.GetPrimAtPath(source_mesh_path)
        if not source_mesh or not source_mesh.IsValid():
            raise RuntimeError("collision_observe_source_collider_missing")
        finger_paths = tuple(str(path) for path in fluid.finger_body_paths)
        if len(finger_paths) != 2:
            raise RuntimeError("collision_observe_finger_paths_invalid")
        left_finger, right_finger = finger_paths
        stage_id = int(UsdUtils.StageCache.Get().GetId(stage).ToLongInt())
        robot_colliders = _enabled_colliders(stage, "/World/Franka")
        source_colliders = _enabled_colliders(stage, source_mesh_path)

        def source_snapshot() -> dict[str, Any]:
            source_state.capture()
            position, orientation = source_body.get_world_pose()
            linear = source_body.get_linear_velocity()
            angular = source_body.get_angular_velocity()
            values = (position, orientation, linear, angular)
            if not all(
                np.isfinite(np.asarray(value, dtype=np.float64)).all()
                for value in values
            ):
                raise RuntimeError("collision_observe_source_state_nonfinite")
            return {
                "position_m": np.asarray(position, dtype=np.float64).tolist(),
                "orientation_wxyz": np.asarray(orientation, dtype=np.float64).tolist(),
                "linear_velocity_m_s": np.asarray(linear, dtype=np.float64).tolist(),
                "angular_velocity_rad_s": np.asarray(angular, dtype=np.float64).tolist(),
                "geometry_center_world_m": source_state.center_world().tolist(),
            }

        def path(identifier: Any) -> str:
            if isinstance(identifier, bool) or not isinstance(identifier, (int, np.integer)):
                raise RuntimeError("collision_observe_report_identifier_invalid")
            result = str(PhysicsSchemaTools.intToSdfPath(int(identifier)))
            if not result:
                raise RuntimeError("collision_observe_report_path_unresolved")
            return result

        event_names = {0: "FOUND", 1: "LOST", 2: "PERSIST"}

        def event_name(value: Any) -> str:
            name = getattr(value, "name", None)
            mapped = {
                "CONTACT_FOUND": "FOUND",
                "CONTACT_LOST": "LOST",
                "CONTACT_PERSIST": "PERSIST",
            }.get(name)
            if mapped is not None:
                return mapped
            try:
                return event_names[int(value)]
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("collision_observe_report_event_invalid") from exc

        collision_records: list[dict[str, Any]] = []
        trace_stream = gzip.open(trace_path, "xb")

        def report_step(physics_step: int) -> None:
            nonlocal trace_count
            raw = simulation.get_full_contact_report()
            if not isinstance(raw, tuple) or len(raw) != 3:
                raise RuntimeError("collision_observe_report_tuple_invalid")
            raw_headers, raw_points, raw_anchors = raw
            headers = []
            for header in raw_headers:
                headers.append(
                    {
                        "type": event_name(header.type),
                        "stage_id": int(header.stage_id),
                        "actor0": path(header.actor0),
                        "actor1": path(header.actor1),
                        "collider0": path(header.collider0),
                        "collider1": path(header.collider1),
                        "contact_data_offset": int(header.contact_data_offset),
                        "num_contact_data": int(header.num_contact_data),
                        "friction_anchors_offset": int(header.friction_anchors_offset),
                        "num_friction_anchors_data": int(
                            header.num_friction_anchors_data
                        ),
                    }
                )
            points = []
            for point in raw_points:
                separation = float(point.separation)
                if not math.isfinite(separation):
                    raise RuntimeError("collision_observe_contact_separation_invalid")
                points.append(
                    {
                        "position": probe._finite_vector(point.position, name="position"),
                        "normal": probe._finite_vector(point.normal, name="normal"),
                        "impulse": probe._finite_vector(point.impulse, name="impulse"),
                        "separation": separation,
                    }
                )
            anchors = [
                {
                    "position": probe._finite_vector(anchor.position, name="anchor_position"),
                    "impulse": probe._finite_vector(anchor.impulse, name="anchor_impulse"),
                }
                for anchor in raw_anchors
            ]
            classified = []
            for header in headers:
                if header["stage_id"] != stage_id:
                    raise RuntimeError("collision_observe_report_stage_mismatch")
                contact_class = observe.classify_contact_header(
                    header,
                    source_body_path=source_path,
                    robot_body_paths=robot_body_paths,
                    left_finger_body_path=left_finger,
                    right_finger_body_path=right_finger,
                    hand_body_path=HAND_BODY_PATH,
                )
                record = {
                    "physics_step": physics_step,
                    "contact_class": contact_class,
                    **header,
                }
                classified.append(record)
                collision_records.append(record)
            record = {
                "physics_step": physics_step,
                "headers": headers,
                "contact_data": points,
                "friction_anchors": anchors,
                "classified_headers": classified,
            }
            _write_trace(trace_stream, trace_digest, record)
            trace_count += 1

        control_dt = fluid_control_dt(
            physics_dt=float(fluid.physics_dt),
            physics_substeps_per_observation=int(fluid.physics_substeps_per_observation),
            rendering_dt=float(fluid.rendering_dt),
        )
        rmp = RMPFlowController(
            name="collision_observe_native_rmp",
            robot_articulation=robot,
            physics_dt=control_dt,
        )
        pick = PickController(
            name="collision_observe_native_pick",
            cspace_controller=rmp,
            events_dt=[0.002, 0.002, 0.005, 0.05, 0.05, 0.01, 0.05],
        )
        pour = PourController(
            name="collision_observe_native_pour",
            cspace_controller=rmp,
            events_dt=[0.05, 0.05, 0.05, 0.05, 0.05, 0.05],
            fixed_height_offsets=tuple(float(value) for value in fluid.expert_pour_height_offsets_m),
            target_position_offset=tuple(float(value) for value in fluid.expert_pour_target_offset_m),
            direct_control_frame_targets=True,
        )
        pick_orientation = Rotation.from_euler("xyz", np.radians([0, 90, 30])).as_quat()
        physics_step = int(world.current_time_step_index)
        for _ in range(int(fluid.initial_render_warmup_updates)):
            world.render()
        for _ in range(int(fluid.dynamic_pre_roll_steps)):
            world.step(render=False)
            physics_step = int(world.current_time_step_index)
            report_step(physics_step)
            if writer_audit.record()["valid"] is not True:
                raise RuntimeError("collision_observe_source_writer_audit_invalid")

        video_dir.mkdir(mode=0o700)
        video_path = video_dir / "trajectory.mp4"

        def capture_video(state: Mapping[str, Any]) -> None:
            nonlocal video_writer
            try:
                rgb = model_camera_video_rgb(
                    state,
                    camera_keys=tuple(fluid.model_camera_keys),
                    expected_shape=tuple(fluid.model_camera_shape),
                )
            except (TypeError, ValueError):
                return
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            if video_writer is None:
                height, width = bgr.shape[:2]
                video_writer = cv2.VideoWriter(
                    str(video_path),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    30.0,
                    (width, height),
                )
                if not video_writer.isOpened():
                    raise RuntimeError("collision_observe_video_open_failed")
            video_writer.write(bgr)

        action_stream = action_path.open("xb")
        phase = "PICKING"
        initial_size = None
        command_sequence_completed = False
        for control_index in range(args.max_control_steps):
            state = task.step()
            if state is None:
                raise RuntimeError("collision_observe_task_state_missing")
            source_state.capture()
            state = source_state(state)
            capture_video(state)
            if initial_size is None:
                initial_size = np.asarray(state["object_size"], dtype=np.float64).copy()
            if phase == "PICKING" and pick.is_done():
                phase = "POURING"
            if phase == "PICKING":
                action = pick.forward(
                    picking_position=np.asarray(state["object_position"], dtype=np.float64).copy(),
                    current_joint_positions=state["joint_positions"],
                    object_size=state["object_size"],
                    object_name=state["object_name"],
                    gripper_control=type("NoAttachmentGripper", (), {"add_object_to_gripper": staticmethod(lambda *_args, **_kwargs: None)})(),
                    gripper_position=state["gripper_position"],
                    end_effector_orientation=pick_orientation,
                    pre_offset_x=0.05,
                    pre_offset_z=0.05,
                    after_offset_z=0.5,
                )
                atomic_event = pick._last_emitted_event
            else:
                if pour.is_done():
                    command_sequence_completed = True
                    break
                action = pour.forward(
                    articulation_controller=robot.get_articulation_controller(),
                    source_size=initial_size,
                    target_position=state["target_position"],
                    current_joint_velocities=robot.get_joint_velocities(),
                    gripper_position=state["gripper_position"],
                    source_name=state["object_name"],
                    pour_speed=float(fluid.expert_pour_speed_rad_s),
                )
                atomic_event = pour._last_emitted_event
            action_record = {
                "control_index": control_index,
                "phase": phase,
                "atomic_event": atomic_event,
                "pick_event": pick._event,
                "pour_event": pour._event,
                "source_before": source_snapshot(),
                "gripper_position_before_m": np.asarray(
                    state["gripper_position"], dtype=np.float64
                ).tolist(),
                "action": _record_action(action, np),
            }
            robot.get_articulation_controller().apply_action(action)
            for substep in range(int(fluid.physics_substeps_per_observation)):
                world.step(
                    render=substep
                    == int(fluid.physics_substeps_per_observation) - 1
                )
                physics_step = int(world.current_time_step_index)
                report_step(physics_step)
                writer = writer_audit.record()
                if writer["valid"] is not True:
                    raise RuntimeError("collision_observe_source_writer_audit_invalid")
            action_record["source_after"] = source_snapshot()
            action_record["gripper_position_after_m"] = np.asarray(
                robot.get_gripper_position(), dtype=np.float64
            ).tolist()
            action_record["source_writer_audit"] = {
                key: writer[key]
                for key in (
                    "valid",
                    "coverage_complete",
                    "call_count",
                    "source_pose_write_count_after_play",
                    "source_velocity_write_count_after_play",
                    "kinematic_target_update_count",
                )
            }
            payload = json.dumps(
                probe._json_native(action_record),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            action_stream.write(payload + b"\n")
            action_digest.update(payload + b"\n")
            action_count += 1
        else:
            command_sequence_completed = False

        if video_writer is not None:
            video_writer.release()
            video_writer = None
        trace_stream.close()
        trace_stream = None
        action_stream.close()
        action_stream = None
        probe._require_unchanged_input_hashes(input_closure=input_closure)
        writer = writer_audit.record()
        result = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_collision_observe_trajectory_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": (
                "COMMAND_TRAJECTORY_COMPLETED"
                if command_sequence_completed
                else "COMMAND_TRAJECTORY_INCOMPLETE"
            ),
            "runtime": dict(runtime),
            "config": {
                "path": str(args.config),
                "input_closure": input_closure,
                "input_closure_sha256": probe._canonical_json_sha256(input_closure),
            },
            "treatment": {
                "controller_source": "current_native_atomic_pick_and_pour_v1",
                "collision_policy": observe.COLLISION_POLICY,
                "source_dynamic": True,
                "mechanical_attachment_used": False,
                "source_pose_authority": "physx_dynamic_readback_v1",
                "source_stage_contract": source_stage_contract,
                "source_colliders": source_colliders,
                "robot_colliders": robot_colliders,
                "report_layer_sha256": hashlib.sha256(
                    layer.ExportToString().encode("utf-8")
                ).hexdigest(),
            },
            "result": {
                "command_sequence_completed": command_sequence_completed,
                "final_pick_evidence": pick.control_evidence(),
                "final_pour_event": pour._event,
                "final_source": source_snapshot(),
                "source_writer_audit": writer,
                "collision_summary": observe.collision_summary(collision_records),
                "direct_report_trace": {
                    "path": str(trace_path),
                    "compression": "gzip",
                    "record_count": trace_count,
                    "uncompressed_sha256": trace_digest.hexdigest(),
                    "compressed_sha256": probe._sha256_file(trace_path),
                },
                "action_ledger": {
                    "path": str(action_path),
                    "record_count": action_count,
                    "sha256": probe._sha256_file(action_path),
                    "uncompressed_sha256": action_digest.hexdigest(),
                },
                "video": _artifact(video_path, root=args.out_dir),
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        probe._write_create_only(args.child_report_path, result)
        return result
    except BaseException as exc:
        result = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_collision_observe_trajectory_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": "RUNTIME_BLOCKED",
            "runtime": dict(runtime),
            "fatal_error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        if not args.child_report_path.exists():
            probe._write_create_only(args.child_report_path, result)
        return result
    finally:
        if video_writer is not None:
            video_writer.release()
        if trace_stream is not None:
            trace_stream.close()
        if action_stream is not None:
            action_stream.close()


def _run_child(args: argparse.Namespace) -> int:
    app = None
    runtime = None
    try:
        attestation = _attestation_module()
        request = attestation._read_canonical_json(args.execution_request)
        paths = _source_paths(Path(attestation.__file__))
        request = attestation.verify_execution_request(request, source_paths=paths)
        runtime = probe.runtime_process_preflight(request)
        receipt, app = attestation.bootstrap_effective_runtime(
            execution_request=request,
            source_paths=paths,
        )
        attestation.write_canonical_json(args.runtime_receipt_path, receipt)
        binding = attestation.execution_binding_for_request(
            request, child_pid=os.getpid()
        )
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=binding
        )
        runtime.update(
            {
                "receipt_sha256": attestation.canonical_json_sha256(receipt),
                "execution_binding": binding,
            }
        )
        report = _runtime_trajectory(args, runtime, app=app)
    except BaseException as exc:
        report = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_collision_observe_trajectory_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": "RUNTIME_BLOCKED",
            "runtime": runtime,
            "fatal_error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        }
    finally:
        if app is not None:
            app.close()
    if not args.child_report_path.exists():
        probe._write_create_only(args.child_report_path, report)
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def _run_parent(args: argparse.Namespace) -> int:
    args.out_dir.mkdir(parents=True, mode=0o700)
    child_report_path = args.out_dir / "child_report.json"
    runtime_receipt_path = args.out_dir / "runtime_receipt.json"
    attestation = _attestation_module()
    paths = _source_paths(Path(attestation.__file__))
    source_before = attestation.capture_source_identity(paths)
    request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    request_path = args.out_dir / "execution_request.json"
    attestation.write_canonical_json(request_path, request)
    environment = attestation.sealed_child_environment(args.out_dir / "runtime")
    command = [
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--config",
        str(args.config),
        "--out-dir",
        str(args.out_dir),
        "--max-control-steps",
        str(args.max_control_steps),
        "--execution-request",
        str(request_path),
    ]
    stdout_path = args.out_dir / "child.stdout.log"
    stderr_path = args.out_dir / "child.stderr.log"
    child_pid = None
    child_returncode = None
    receipt = None
    verification_failure = None
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            child_pid = process.pid
            try:
                child_returncode = process.wait(timeout=args.timeout_s)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                child_returncode = process.wait()
                raise RuntimeError("collision_observe_child_timeout")
        child_report = json.loads(child_report_path.read_text(encoding="utf-8"))
        if not isinstance(child_report, Mapping):
            raise RuntimeError("collision_observe_child_report_invalid")
        receipt = attestation._read_canonical_json(runtime_receipt_path)
        binding = attestation.execution_binding_for_request(
            request, child_pid=child_pid
        )
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=binding
        )
        if (
            child_report.get("runtime", {}).get("receipt_sha256")
            != attestation.canonical_json_sha256(receipt)
            or child_returncode
            != (2 if child_report.get("decision") == "RUNTIME_BLOCKED" else 0)
        ):
            raise RuntimeError("collision_observe_child_verification_invalid")
        report = dict(child_report)
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        report = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_collision_observe_trajectory_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": "RUNTIME_BLOCKED",
            "fatal_error": verification_failure,
        }
    finally:
        manifest = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_collision_observe_parent_manifest_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "command": command,
            "source_before": source_before,
            "source_after": attestation.capture_source_identity(paths),
            "execution_request_sha256": attestation.canonical_json_sha256(request),
            "runtime_receipt_sha256": (
                None
                if receipt is None
                else attestation.canonical_json_sha256(receipt)
            ),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "stdout": _artifact(stdout_path, root=args.out_dir),
            "stderr": _artifact(stderr_path, root=args.out_dir),
            "verification_failure": verification_failure,
        }
        attestation.write_canonical_json(args.out_dir / "run_manifest.json", manifest)
    probe._write_create_only(args.out_dir / "report.json", report)
    print(
        f"collision-observe trajectory decision={report['decision']} out={args.out_dir / 'report.json'}",
        flush=True,
    )
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-control-steps", type=int, default=1200)
    parser.add_argument("--timeout-s", type=float, default=3600.0)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.config.is_file() or args.max_control_steps <= 0:
        parser.error("config must exist and max-control-steps must be positive")
    if not math.isfinite(args.timeout_s) or args.timeout_s <= 0.0:
        parser.error("timeout-s must be positive")
    if args.child:
        if args.execution_request is None:
            parser.error("--child requires --execution-request")
        args.execution_request = args.execution_request.resolve()
        if not args.out_dir.is_dir() or not args.execution_request.is_file():
            parser.error("child inputs must exist")
        args.child_report_path = args.out_dir / "child_report.json"
        args.runtime_receipt_path = args.out_dir / "runtime_receipt.json"
    elif args.execution_request is not None or args.out_dir.exists():
        parser.error("parent out-dir must not exist")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_child(args) if args.child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
