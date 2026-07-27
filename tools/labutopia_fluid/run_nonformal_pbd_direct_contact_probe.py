#!/usr/bin/env python3
"""Observe a close-only dynamic PBD contact attempt with direct PhysX reports.

This tool is diagnostic only. It never emits a formal grasp, lift, pour, or
acceptance result and terminates before an arm-lift action can be applied.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
FORMAL_ISAAC41_PREFIX = FORMAL_ISAAC41_PYTHON.parents[1]
APPROVED_LIBRARY_PATHS = (
    FORMAL_ISAAC41_PREFIX
    / "lib/python3.10/site-packages/isaacsim/extscache/omni.cuda.libs/bin",
    FORMAL_ISAAC41_PREFIX
    / "lib/python3.10/site-packages/isaacsim/extscache/omni.gpu_foundation/bin/deps",
    FORMAL_ISAAC41_PREFIX / "lib/python3.10/site-packages/torch/lib",
)
APPROVED_LD_LIBRARY_PATH = ":".join(str(path) for path in APPROVED_LIBRARY_PATHS)
DEFAULT_CONFIG = REPO_ROOT / "config/level1_pour_online_fluid_contact_grasp_v1.yaml"
REQUIRED_ENVIRONMENT = {
    "PYTHONNOUSERSITE": "1",
    "ACCEPT_EULA": "Y",
    "OMNI_KIT_ACCEPT_EULA": "YES",
}
FORBIDDEN_ENVIRONMENT = (
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONUSERBASE",
    "CARB_APP_PATH",
    "EXP_PATH",
    "ISAAC_PATH",
    "OMNI_SERVER",
    "LD_PRELOAD",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_unchanged_input_hashes(
    *,
    config_path: Path,
    config_sha256: str,
    asset_path: Path,
    asset_sha256: str,
) -> None:
    if (
        _sha256_file(config_path) != config_sha256
        or _sha256_file(asset_path) != asset_sha256
    ):
        raise RuntimeError("nonformal_probe_input_changed_during_run")


def _json_native(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(item) for item in value]
    if hasattr(value, "tolist"):
        return _json_native(value.tolist())
    if hasattr(value, "item"):
        return _json_native(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite_json_value")
    return value


def _write_create_only(path: Path, value: dict[str, Any]) -> None:
    payload = json.dumps(
        _json_native(value),
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if os.path.exists(path):
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)


def _runtime_preflight(receipt_path: Path) -> dict[str, Any]:
    if Path(sys.executable).resolve() != FORMAL_ISAAC41_PYTHON.resolve():
        raise RuntimeError("nonformal_probe_interpreter_mismatch")
    for name, expected in REQUIRED_ENVIRONMENT.items():
        if os.environ.get(name) != expected:
            raise RuntimeError(f"nonformal_probe_environment_missing:{name}")
    present = [name for name in FORBIDDEN_ENVIRONMENT if os.environ.get(name)]
    if present:
        raise RuntimeError(
            "nonformal_probe_environment_forbidden:" + ",".join(sorted(present))
        )
    if os.environ.get("LD_LIBRARY_PATH") != APPROVED_LD_LIBRARY_PATH:
        raise RuntimeError("nonformal_probe_library_path_invalid")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    try:
        attestation.require_matched_runtime_receipt(receipt)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("nonformal_probe_runtime_receipt_invalid") from exc
    return {
        "executable": str(FORMAL_ISAAC41_PYTHON),
        "receipt_path": str(receipt_path),
        "receipt_sha256": _sha256_file(receipt_path),
        "receipt_binding": "separate_nonformal_preflight_only",
        "library_path": APPROVED_LD_LIBRARY_PATH,
        "library_path_sha256": hashlib.sha256(
            APPROVED_LD_LIBRARY_PATH.encode("utf-8")
        ).hexdigest(),
        "environment": {
            name: os.environ[name]
            for name in (*REQUIRED_ENVIRONMENT, "HOME", "TMPDIR", "XDG_CACHE_HOME")
            if name in os.environ
        },
    }


def _finite_vector(value: Any, *, name: str) -> list[float]:
    try:
        result = [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"direct_report_{name}_invalid") from exc
    if len(result) != 3 or not all(math.isfinite(item) for item in result):
        raise RuntimeError(f"direct_report_{name}_invalid")
    return result


def _event_name(value: Any) -> str:
    names = {
        "CONTACT_FOUND": "FOUND",
        "CONTACT_PERSIST": "PERSIST",
        "CONTACT_LOST": "LOST",
    }
    values = {0: "FOUND", 1: "LOST", 2: "PERSIST"}
    name = getattr(value, "name", None)
    if name in names:
        return names[name]
    try:
        return values[int(value)]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("direct_report_event_invalid") from exc


def _runtime_probe(args: argparse.Namespace, runtime: dict[str, Any]) -> dict[str, Any]:
    # Keep all Isaac imports after SimulationApp has bootstrapped Kit.
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True, "width": 64, "height": 64})
    trace_path = args.out_dir / "direct_physx_reports.jsonl.gz"
    trace_stream = None
    trace_digest = hashlib.sha256()
    trace_records = 0
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from isaacsim_compat import install_legacy_isaacsim_aliases

        install_legacy_isaacsim_aliases()
        import numpy as np
        import omni.physx
        import omni.usd
        from isaacsim.core.api import World
        from isaacsim.core.prims import SingleRigidPrim
        from isaacsim.core.utils.stage import add_reference_to_stage
        from omegaconf import OmegaConf
        from omni.physx import get_physx_simulation_interface
        from pxr import PhysxSchema, PhysicsSchemaTools, Sdf, Usd, UsdPhysics, UsdShade, UsdUtils

        from controllers.atomic_actions.contact_pick_controller import (
            ContactPickController,
            ContactPickEvent,
        )
        from factories.robot_factory import create_robot
        from factories.task_factory import create_task
        from robots.franka.rmpflow_controller import RMPFlowController
        from tools.labutopia_fluid import nonformal_direct_contact
        from utils.fluid_evaluation_loop import fluid_control_dt
        from utils.isaac_fluid_evaluation import (
            PhysicsSourceStateAdapter,
            SourceBodyWriterAudit,
            configure_contact_grasp_scene,
            construct_single_rigid_prim,
            configure_fluid_world_timing,
            configure_particle_usd_readback,
            validate_fluid_stage_contract,
        )
        from utils.object_utils import ObjectUtils
        from utils.controlled_contact import FullContactReportAccumulator

        cfg = OmegaConf.load(str(args.config))
        fluid = cfg.online_fluid
        if (
            fluid.enabled is not True
            or str(fluid.source_ownership) != "contact_friction_dynamic_v1"
            or str(fluid.expert_control_profile) != "contact_pick_v1"
            or str(cfg.task_type) != "pickpour"
        ):
            raise RuntimeError("nonformal_probe_config_contract_invalid")
        asset_path = (REPO_ROOT / str(cfg.usd_path)).resolve()
        if not asset_path.is_file():
            raise FileNotFoundError(f"nonformal_probe_asset_missing:{asset_path}")
        config_sha256_before = _sha256_file(args.config)
        asset_sha256_before = _sha256_file(asset_path)

        configure_particle_usd_readback()
        stage = omni.usd.get_context().get_stage()
        add_reference_to_stage(usd_path=str(asset_path), prim_path="/World")
        if (
            not stage.GetPrimAtPath(str(fluid.particle_path)).IsValid()
            or not stage.GetPrimAtPath(str(fluid.particle_system_path)).IsValid()
        ):
            raise RuntimeError("nonformal_probe_pbd_prims_missing")
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
            usd_path=str((REPO_ROOT / str(cfg.robot.usd_path)).resolve()),
            camera_frequency=int(cfg.robot.camera_frequency),
        )

        session = stage.GetSessionLayer()
        if session is None:
            raise RuntimeError("nonformal_probe_session_layer_missing")
        initial_world_index = int(world.current_time_step_index)
        previous_target = stage.GetEditTarget()
        layer = Sdf.Layer.CreateAnonymous("nonformal_pbd_direct_contact.usda")
        if layer is None:
            raise RuntimeError("nonformal_probe_session_layer_create_failed")
        session.subLayerPaths.insert(0, layer.identifier)
        try:
            stage.SetEditTarget(Usd.EditTarget(layer))
            # This is the declared physical treatment: finger friction binding.
            configure_contact_grasp_scene(stage, fluid)
            report_paths = (
                str(fluid.source_actor_path),
                *tuple(str(path) for path in fluid.finger_body_paths),
                "/World/Franka/panda_hand",
            )
            for path in report_paths:
                prim = stage.GetPrimAtPath(path)
                if not prim or not prim.IsValid():
                    raise RuntimeError(f"nonformal_probe_report_body_missing:{path}")
                api = PhysxSchema.PhysxContactReportAPI.Apply(prim)
                api.CreateThresholdAttr().Set(0.0)
                api.CreateReportPairsRel().ClearTargets(True)
                if api.GetThresholdAttr().Get() != 0.0 or api.GetReportPairsRel().GetTargets():
                    raise RuntimeError(f"nonformal_probe_report_api_invalid:{path}")
        finally:
            stage.SetEditTarget(previous_target)
        simulation.flush_changes()
        if int(world.current_time_step_index) != initial_world_index:
            raise RuntimeError("nonformal_probe_setup_advanced_physics")
        report_layer_usda = layer.ExportToString()
        report_layer_sha256 = hashlib.sha256(
            report_layer_usda.encode("utf-8")
        ).hexdigest()

        ObjectUtils.get_instance(stage)
        task = create_task(str(cfg.task_type), cfg=cfg, world=world, stage=stage, robot=robot)
        task.reset()

        def controller_state() -> dict[str, Any] | None:
            # This direct-contact diagnostic has no perception consumer. Avoid
            # camera readback while stepping physics without rendering.
            task.frame_idx += 1
            if not task.check_frame_limits():
                return None
            joint_positions = robot.get_joint_positions()
            gripper_position = robot.get_gripper_position()
            if joint_positions is None or gripper_position is None:
                return None
            return {
                "joint_positions": joint_positions,
                "gripper_position": gripper_position,
            }

        source_root = str(fluid.source_actor_path)
        source_collider = str(fluid.source_external_shell_path)
        source_stage_contract = validate_fluid_stage_contract(stage, fluid)
        source_prim = stage.GetPrimAtPath(source_root)
        source_mesh = stage.GetPrimAtPath(source_collider)
        source_body = construct_single_rigid_prim(
            SingleRigidPrim,
            prim_path=source_root,
            name="nonformal_pbd_direct_contact_source_reader",
        )
        source_body.initialize()

        def source_contract() -> dict[str, Any]:
            rigid_enabled = source_prim.GetAttribute("physics:rigidBodyEnabled").Get()
            kinematic = source_prim.GetAttribute("physics:kinematicEnabled").Get()
            collision_enabled = source_mesh.GetAttribute("physics:collisionEnabled").Get()
            position, orientation = source_body.get_world_pose()
            linear = source_body.get_linear_velocity()
            angular = source_body.get_angular_velocity()
            vectors = (position, orientation, linear, angular)
            values_valid = all(np.isfinite(np.asarray(value, dtype=np.float64)).all() for value in vectors)
            return {
                "rigid_body_enabled": rigid_enabled is not False,
                "kinematic_enabled": kinematic is True,
                "collision_enabled": collision_enabled is True,
                "state_finite": bool(values_valid),
                "position_m": np.asarray(position, dtype=np.float64).tolist(),
                "orientation_wxyz": np.asarray(orientation, dtype=np.float64).tolist(),
                "linear_velocity_m_s": np.asarray(linear, dtype=np.float64).tolist(),
                "angular_velocity_rad_s": np.asarray(angular, dtype=np.float64).tolist(),
            }

        initial_source_contract = source_contract()
        if not (
            initial_source_contract["rigid_body_enabled"]
            and not initial_source_contract["kinematic_enabled"]
            and initial_source_contract["collision_enabled"]
            and initial_source_contract["state_finite"]
        ):
            raise RuntimeError("nonformal_probe_source_dynamic_contract_invalid")
        source_state = PhysicsSourceStateAdapter(
            read_source_world_pose=source_body.get_world_pose,
            initial_geometry_center_world=task.object_utils.get_geometry_center(
                object_path=source_root
            ),
        )
        source_writer_audit = SourceBodyWriterAudit(source_body_path=source_root)
        source_writer_audit.install(source_body=source_body, object_utils=task.object_utils)
        source_writer_audit.reset()

        def enabled_colliders(root_path: str) -> list[str]:
            root = stage.GetPrimAtPath(root_path)
            if not root or not root.IsValid():
                raise RuntimeError(f"nonformal_probe_collider_root_missing:{root_path}")
            paths = []
            for prim in Usd.PrimRange(root):
                if not prim.HasAPI(UsdPhysics.CollisionAPI):
                    continue
                enabled = prim.GetAttribute("physics:collisionEnabled")
                if enabled and enabled.Get() is False:
                    continue
                paths.append(str(prim.GetPath()))
            return sorted(set(paths))

        def owner(collider_path: str) -> str:
            prim = stage.GetPrimAtPath(collider_path)
            while prim and prim.IsValid():
                if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                    return str(prim.GetPath())
                prim = prim.GetParent()
            return collider_path

        # Only the external source shell can substantiate a finger grasp. A
        # finger reaching the interior PBD wrapper is classified as unexpected.
        source_colliders = enabled_colliders(source_collider)
        left_colliders = enabled_colliders(str(fluid.finger_body_paths[0]))
        right_colliders = enabled_colliders(str(fluid.finger_body_paths[1]))
        hand_colliders = enabled_colliders("/World/Franka/panda_hand")
        support_colliders = set(enabled_colliders(str(fluid.table_path)))
        cube = stage.GetPrimAtPath("/World/Cube")
        if cube and cube.IsValid():
            support_colliders.update(enabled_colliders("/World/Cube"))
        all_colliders = enabled_colliders("/World")
        named = set(source_colliders + left_colliders + right_colliders + hand_colliders)
        support_colliders.difference_update(named)
        other_colliders = sorted(set(all_colliders) - named - support_colliders)
        known = set(source_colliders + left_colliders + right_colliders + hand_colliders)
        known.update(support_colliders)
        known.update(other_colliders)
        identities = {
            "source_colliders": source_colliders,
            "left_colliders": left_colliders,
            "right_colliders": right_colliders,
            "hand_colliders": hand_colliders,
            "support_colliders": sorted(support_colliders),
            "other_colliders": other_colliders,
            "collider_owners": {path: owner(path) for path in sorted(known)},
        }
        if not source_colliders or not left_colliders or not right_colliders:
            raise RuntimeError("nonformal_probe_required_colliders_missing")

        stage_cache_id = UsdUtils.StageCache.Get().GetId(stage)
        stage_id = int(stage_cache_id.ToLongInt())
        accumulator = FullContactReportAccumulator(
            expected_stage_id=stage_id,
            provisional_background_pairs=[
                (source, support)
                for source in source_colliders
                for support in sorted(support_colliders)
            ],
        )
        event_values = {0: "FOUND", 1: "LOST", 2: "PERSIST"}
        reads = 0
        trace_stream = gzip.open(trace_path, "xb")

        def resolve(identifier: Any) -> str:
            if isinstance(identifier, bool) or not isinstance(identifier, (int, np.integer)):
                raise RuntimeError("direct_report_identifier_invalid")
            path = str(PhysicsSchemaTools.intToSdfPath(int(identifier)))
            if not path:
                raise RuntimeError("direct_report_path_unresolved")
            return path

        def report_sample(physics_index: int, *, bootstrap: bool) -> dict[str, Any]:
            nonlocal reads
            raw = simulation.get_full_contact_report()
            if not isinstance(raw, tuple) or len(raw) != 3:
                raise RuntimeError("direct_report_tuple_invalid")
            raw_headers, raw_points, raw_anchors = raw
            headers = []
            points = []
            anchors = []
            for header in raw_headers:
                name = getattr(header.type, "name", None)
                event = name and {
                    "CONTACT_FOUND": "FOUND",
                    "CONTACT_PERSIST": "PERSIST",
                    "CONTACT_LOST": "LOST",
                }.get(name)
                if event is None:
                    try:
                        event = event_values[int(header.type)]
                    except (KeyError, TypeError, ValueError) as exc:
                        raise RuntimeError("direct_report_event_invalid") from exc
                headers.append(
                    {
                        "type": event,
                        "stage_id": int(header.stage_id),
                        "actor0": resolve(header.actor0),
                        "actor1": resolve(header.actor1),
                        "collider0": resolve(header.collider0),
                        "collider1": resolve(header.collider1),
                        "proto_index0": int(header.proto_index0),
                        "proto_index1": int(header.proto_index1),
                        "contact_data_offset": int(header.contact_data_offset),
                        "num_contact_data": int(header.num_contact_data),
                        "friction_anchors_offset": int(header.friction_anchors_offset),
                        "num_friction_anchors_data": int(header.num_friction_anchors_data),
                    }
                )
            for point in raw_points:
                separation = float(point.separation)
                if not math.isfinite(separation):
                    raise RuntimeError("direct_report_separation_invalid")
                points.append(
                    {
                        "position": _finite_vector(point.position, name="position"),
                        "normal": _finite_vector(point.normal, name="normal"),
                        "impulse": _finite_vector(point.impulse, name="impulse"),
                        "separation": separation,
                        "face_index0": int(point.face_index0),
                        "face_index1": int(point.face_index1),
                        "material0": resolve(point.material0) if int(point.material0) else "__zero__",
                        "material1": resolve(point.material1) if int(point.material1) else "__zero__",
                    }
                )
            for anchor in raw_anchors:
                anchors.append(
                    {
                        "position": _finite_vector(anchor.position, name="anchor_position"),
                        "impulse": _finite_vector(anchor.impulse, name="anchor_impulse"),
                    }
                )
            reads += 1
            return accumulator.consume(
                physics_index=physics_index,
                headers=headers,
                contact_data=points,
                friction_anchors=anchors,
                allow_provisional_persist_bootstrap=bootstrap,
            )

        def record_direct_report(report: dict[str, Any]) -> dict[str, Any]:
            nonlocal trace_records
            if trace_stream is None:
                raise RuntimeError("nonformal_probe_direct_trace_closed")
            payload = json.dumps(
                _json_native(report),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            trace_stream.write(payload + b"\n")
            trace_digest.update(payload + b"\n")
            trace_records += 1
            return {
                "line": trace_records,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }

        control_dt = fluid_control_dt(
            physics_dt=float(fluid.physics_dt),
            physics_substeps_per_observation=int(fluid.physics_substeps_per_observation),
            rendering_dt=float(fluid.rendering_dt),
        )
        rmp = RMPFlowController(
            name="nonformal_pbd_direct_contact_rmp",
            robot_articulation=robot,
            physics_dt=control_dt,
        )
        pick = ContactPickController(
            name="nonformal_pbd_direct_contact_pick",
            cspace_controller=rmp,
            control_dt=control_dt,
            position_threshold=float(getattr(fluid, "expert_pick_position_threshold_m", 0.005)),
            open_position=float(getattr(fluid, "expert_pick_open_position_m", 0.040)),
            open_position_tolerance=float(
                getattr(fluid, "expert_pick_open_position_tolerance_m", 0.0002)
            ),
            pregrasp_distance=float(getattr(fluid, "expert_pick_pregrasp_distance_m", 0.10)),
            insert_distance=float(getattr(fluid, "expert_pick_insert_distance_m", 0.03)),
            approach_speed=float(getattr(fluid, "expert_pick_approach_speed_m_s", 0.03)),
            close_speed=float(getattr(fluid, "expert_pick_close_speed_m_s", 0.01)),
            lift_speed=float(getattr(fluid, "expert_pick_lift_speed_m_s", 0.05)),
            orientation_threshold_degrees=float(
                getattr(fluid, "expert_pick_orientation_threshold_degrees", 5.0)
            ),
            contact_timeout=float(fluid.grasp_contact_timeout_s),
            control_to_end_effector_matrix_m=np.asarray(
                fluid.rmpflow_control_to_grasp_matrix_m, dtype=np.float64
            ),
            end_effector_frame=str(fluid.grasp_target_frame_name),
            control_frame=str(fluid.rmpflow_control_frame_name),
            finger_joint_indices=tuple(int(index) for index in fluid.finger_joint_indices),
            source_translation_limit=float(fluid.grasp_preclose_source_translation_limit_m),
            source_tilt_limit_degrees=float(fluid.grasp_preclose_source_tilt_limit_degrees),
            terminate_after_contact_settle=True,
            require_external_phase_certificates=False,
        )

        physics_index = 0
        history: list[dict[str, Any]] = []
        action_ledger: list[dict[str, Any]] = []
        latest: dict[str, Any] | None = None
        observed = False
        terminal: str | None = None
        terminal_reason: str | None = None

        def source_snapshot() -> dict[str, Any]:
            source_state.capture()
            contract = source_contract()
            center = source_state.center_world()
            center_values = np.asarray(center, dtype=np.float64)
            if center_values.shape != (3,) or not np.isfinite(center_values).all():
                raise RuntimeError("nonformal_probe_source_center_invalid")
            contract["geometry_center_world_m"] = center_values.tolist()
            return contract

        def source_contract_valid(contract: dict[str, Any]) -> bool:
            return bool(
                contract["rigid_body_enabled"]
                and not contract["kinematic_enabled"]
                and contract["collision_enabled"]
                and contract["state_finite"]
            )

        def action_record(action: Any) -> dict[str, Any]:
            record: dict[str, Any] = {}
            for name in (
                "joint_positions",
                "joint_velocities",
                "joint_efforts",
                "joint_indices",
            ):
                value = getattr(action, name, None)
                if value is None:
                    record[name] = None
                    continue
                try:
                    array = np.asarray(value, dtype=np.float64)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(f"nonformal_probe_action_{name}_invalid") from exc
                if array.ndim != 1 or np.isinf(array).any():
                    raise RuntimeError(f"nonformal_probe_action_{name}_invalid")
                if name == "joint_indices":
                    if np.isnan(array).any() or not np.equal(array, np.floor(array)).all():
                        raise RuntimeError(f"nonformal_probe_action_{name}_invalid")
                    record[name] = array.astype(np.int64).tolist()
                    continue
                # Isaac encodes intentionally unspecified sparse joints as NaN.
                record[name] = [
                    None if np.isnan(item) else float(item) for item in array.tolist()
                ]
                record[f"{name}_specified_indices"] = np.flatnonzero(
                    ~np.isnan(array)
                ).astype(np.int64).tolist()
            return record

        def writer_summary(writer: dict[str, Any]) -> dict[str, Any]:
            return {
                "valid": writer["valid"],
                "coverage_complete": writer["coverage_complete"],
                "call_count": writer["call_count"],
                "source_pose_write_count_after_play": writer[
                    "source_pose_write_count_after_play"
                ],
                "source_velocity_write_count_after_play": writer[
                    "source_velocity_write_count_after_play"
                ],
                "object_utils_source_position_write_count_after_play": writer[
                    "object_utils_source_position_write_count_after_play"
                ],
                "kinematic_target_update_count": writer[
                    "kinematic_target_update_count"
                ],
            }

        def step_and_observe(*, phase: str, control_index: int, substep: int) -> dict[str, Any]:
            nonlocal physics_index, latest, observed, terminal, terminal_reason
            pre_source = source_snapshot()
            world.step(render=False)
            report = report_sample(physics_index, bootstrap=physics_index == 0)
            trace_record = record_direct_report(report)
            physics_index += 1
            post_source = source_snapshot()
            writer = source_writer_audit.record()
            latest = nonformal_direct_contact.evaluate_full_report_bilateral_contact(
                report,
                identities=identities,
            )
            if latest["decision"] == "OBSERVED":
                observed = True
            if not source_contract_valid(post_source):
                terminal = "AUDIT_NO_GO"
                terminal_reason = "source_dynamic_contract_invalid_after_play"
            elif writer["valid"] is not True:
                terminal = "AUDIT_NO_GO"
                terminal_reason = "source_writer_audit_invalid"
            elif latest["decision"] == "AUDIT_NO_GO":
                terminal = "AUDIT_NO_GO"
                terminal_reason = "direct_report_audit_no_go"
            elif any(
                failure in latest["failures"]
                for failure in (
                    "hand_source_contact",
                    "unexpected_source_contact",
                    "robot_environment_contact",
                )
            ):
                terminal = "PHYSICAL_FAIL"
                terminal_reason = next(
                    failure
                    for failure in latest["failures"]
                    if failure
                    in {
                        "hand_source_contact",
                        "unexpected_source_contact",
                        "robot_environment_contact",
                    }
                )
            history.append(
                {
                    "phase": phase,
                    "control_index": control_index,
                    "substep": substep,
                    "physics_index": physics_index - 1,
                    "source_pre_step": pre_source,
                    "source_post_step": post_source,
                    "source_writer_audit": writer_summary(writer),
                    "direct": latest,
                    "direct_report_trace": trace_record,
                    "full_report_counts": {
                        "headers": report["header_count"],
                        "points": report["contact_data_count"],
                        "anchors": report["friction_anchor_count"],
                        "occurrences": report["occurrence_count"],
                    },
                }
            )
            return latest

        for pre_roll_index in range(int(fluid.dynamic_pre_roll_steps)):
            step_and_observe(
                phase="PRE_ROLL", control_index=-1, substep=pre_roll_index
            )
            if terminal is not None:
                break

        control_index = 0
        while terminal is None and control_index < args.max_control_steps:
            state = controller_state()
            if not isinstance(state, dict):
                terminal = "AUDIT_NO_GO"
                terminal_reason = "task_state_invalid"
                break
            state = source_state(state)
            if pick.current_event == ContactPickEvent.LIFT or pick.lift_command_emitted():
                terminal = "AUDIT_NO_GO"
                terminal_reason = "lift_phase_reached_before_action"
                break
            action = pick.forward(
                source_position=state["object_position"],
                source_orientation_xyzw=state["object_quaternion"],
                current_joint_positions=state["joint_positions"],
                gripper_position=state["gripper_position"],
                end_effector_orientation=np.asarray(
                    fluid.expert_pick_target_orientation_wxyz, dtype=np.float64
                ),
                current_end_effector_orientation=rmp.get_end_effector_orientation_wxyz(),
                approach_direction=np.asarray(
                    getattr(fluid, "expert_pick_approach_direction_world", [0.0, 0.0, -1.0]),
                    dtype=np.float64,
                ),
                grasp_offset=np.asarray(
                    fluid.expert_pick_gripper_offset_object_m, dtype=np.float64
                ),
                lift_height=float(fluid.expert_pick_lift_height_m),
                gripper_distance=float(fluid.grasp_finger_joint_target_m),
                contact_qualified=bool(latest and latest["decision"] == "OBSERVED"),
            )
            evidence = pick.control_evidence()
            if evidence["lift_command_emitted"] or evidence["phase"] == "LIFT":
                terminal = "AUDIT_NO_GO"
                terminal_reason = "lift_action_attempted"
                action_ledger.append(
                    {
                        "control_index": control_index,
                        "evidence": evidence,
                        "action": action_record(action),
                        "applied": False,
                        "denial_reason": terminal_reason,
                    }
                )
                break
            action_ledger.append(
                {
                    "control_index": control_index,
                    "evidence": evidence,
                    "action": action_record(action),
                    "applied": True,
                }
            )
            robot.get_articulation_controller().apply_action(action)
            for substep in range(int(fluid.physics_substeps_per_observation)):
                step_and_observe(
                    phase=str(evidence["phase"]),
                    control_index=control_index,
                    substep=substep,
                )
                if terminal is not None:
                    break
            if terminal is None and pick.terminal_failure_reason is not None:
                terminal = "PHYSICAL_FAIL"
                terminal_reason = str(pick.terminal_failure_reason)
            elif terminal is None and pick.is_done():
                terminal = "OBSERVED" if observed else "PHYSICAL_FAIL"
                terminal_reason = (
                    "close_only_direct_contact_observed"
                    if observed
                    else "close_only_direct_contact_not_observed"
                )
            control_index += 1

        if terminal is None:
            terminal = "PHYSICAL_FAIL"
            terminal_reason = "max_control_steps_exhausted"
        final_source = source_snapshot()
        final_writer_audit = source_writer_audit.record()
        if terminal == "OBSERVED" and (
            not source_contract_valid(final_source) or final_writer_audit["valid"] is not True
        ):
            terminal = "AUDIT_NO_GO"
            terminal_reason = "final_source_audit_invalid"
        _require_unchanged_input_hashes(
            config_path=args.config,
            config_sha256=config_sha256_before,
            asset_path=asset_path,
            asset_sha256=asset_sha256_before,
        )
        if trace_stream is None:
            raise RuntimeError("nonformal_probe_direct_trace_missing")
        trace_stream.close()
        trace_stream = None
        direct_report_trace = {
            "path": str(trace_path),
            "compression": "gzip",
            "encoding": "utf-8",
            "record_format": "one_canonical_full_contact_report_step_v1_per_line",
            "record_count": trace_records,
            "uncompressed_sha256": trace_digest.hexdigest(),
            "compressed_sha256": _sha256_file(trace_path),
            "complete": True,
        }
        report = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_direct_contact_probe_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": terminal,
            "runtime": runtime,
            "config": {
                "path": str(args.config),
                "sha256": config_sha256_before,
                "asset_path": str(asset_path),
                "asset_sha256": asset_sha256_before,
            },
            "treatment": {
                "source_ownership": str(fluid.source_ownership),
                "source_dynamic": True,
                "finger_friction_binding": "session_layer_intentional_treatment",
                "report_layer_identifier": layer.identifier,
                "report_layer_usda": report_layer_usda,
                "report_layer_sha256": report_layer_sha256,
                "source_stage_contract": source_stage_contract,
                "no_source_pose_write_claim": "instrumented_known_surfaces_only",
                "camera_observation": "not_requested_by_contact_only_diagnostic",
                "lift_action_applied": any(
                    item["applied"] and item["evidence"]["lift_command_emitted"]
                    for item in action_ledger
                ),
            },
            "result": {
                "observed_bilateral_direct_contact": observed,
                "terminal_reason": terminal_reason,
                "final_pick_evidence": pick.control_evidence(),
                "final_direct": latest,
                "direct_report_read_count": reads,
                "direct_report_trace": direct_report_trace,
                "control_steps": control_index,
                "physics_steps": physics_index,
                "source_initial_contract": initial_source_contract,
                "source_final_state": final_source,
                "source_writer_audit": final_writer_audit,
            },
            "action_ledger": action_ledger,
            "history": history,
        }
        report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_create_only(args.out_dir / "report.json", report)
        return report
    except BaseException as exc:
        if trace_stream is not None:
            trace_stream.close()
            trace_stream = None
        report = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_direct_contact_probe_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": "RUNTIME_BLOCKED",
            "runtime": runtime,
            "fatal_error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            "direct_report_trace": {
                "path": str(trace_path),
                "compression": "gzip",
                "record_count": trace_records,
                "uncompressed_sha256": trace_digest.hexdigest(),
                "compressed_sha256": (
                    _sha256_file(trace_path) if trace_path.is_file() else None
                ),
                "complete": False,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_create_only(args.out_dir / "report.json", report)
        return report
    finally:
        app.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-control-steps", type=int, default=600)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.runtime_receipt = args.runtime_receipt.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.config.is_file() or not args.runtime_receipt.is_file():
        parser.error("config and runtime receipt must exist")
    if args.out_dir.exists():
        parser.error("out-dir must not exist")
    if args.max_control_steps <= 0:
        parser.error("max-control-steps must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.out_dir.mkdir(parents=True, mode=0o700)
    runtime = None
    try:
        runtime = _runtime_preflight(args.runtime_receipt)
        report = _runtime_probe(args, runtime)
        code = 2 if report["decision"] == "RUNTIME_BLOCKED" else 0
    except BaseException as exc:
        report = {
            "schema_version": 1,
            "manifest_type": "nonformal_pbd_direct_contact_probe_v1",
            "classification": "NON_FORMAL_DIAGNOSTIC_ONLY",
            "decision": "RUNTIME_BLOCKED",
            "runtime": runtime,
            "fatal_error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        }
        code = 2
    report_path = args.out_dir / "report.json"
    if not report_path.exists():
        report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_create_only(report_path, report)
    print(
        f"nonformal pbd direct contact decision={report['decision']} out={report_path}",
        flush=True,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
