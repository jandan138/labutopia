"""Sealed-child runtime for the authorized v7-native event-0 prefix."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import formal_precontact_event0_replay as replay
from utils import formal_precontact_event0_snapshot_replay as snapshot_replay


SOURCE_ROOT_PATH = "/World/beaker2"
SOURCE_MESH_PATH = "/World/beaker2/mesh"
SOURCE_WRAPPER_ROOT_PATH = "/World/beaker2/FluidSafeWrapperCanonical"
TRACE_NAME = "precontact_trace.json"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_create_only(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical_bytes(dict(value))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _finite_vector(np: Any, value: Any, *, field: str, length: int) -> list[float]:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (length,) or not np.isfinite(array).all():
        raise RuntimeError(f"precontact_replay_{field}_invalid")
    return [float(item) for item in array.tolist()]


def _raw_action(np: Any, action: Any) -> dict[str, Any]:
    if action is None:
        raise RuntimeError("precontact_replay_action_missing")

    def channel(value: Any, *, sparse: bool) -> list[float | None] | None:
        if value is None:
            return None
        array = np.asarray(value, dtype=object)
        if array.ndim != 1:
            raise RuntimeError("precontact_replay_action_invalid")
        result: list[float | None] = []
        for item in array.tolist():
            if item is None and sparse:
                result.append(None)
                continue
            if (
                isinstance(item, bool)
                or not isinstance(item, (int, float, np.integer, np.floating))
                or not math.isfinite(float(item))
            ):
                raise RuntimeError("precontact_replay_action_invalid")
            result.append(float(item))
        return result

    raw_indices = getattr(action, "joint_indices", None)
    if raw_indices is None:
        indices = None
    else:
        values = np.asarray(raw_indices, dtype=object)
        if values.ndim != 1:
            raise RuntimeError("precontact_replay_action_invalid")
        indices = []
        for value in values.tolist():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.integer, np.floating))
                or not math.isfinite(float(value))
                or int(value) != float(value)
            ):
                raise RuntimeError("precontact_replay_action_invalid")
            indices.append(int(value))
    return {
        "joint_positions": channel(getattr(action, "joint_positions", None), sparse=True),
        "joint_velocities": channel(getattr(action, "joint_velocities", None), sparse=False),
        "joint_efforts": channel(getattr(action, "joint_efforts", None), sparse=False),
        "joint_indices": indices,
    }


def _world_index(world: Any) -> int:
    value = int(world.current_time_step_index)
    if value < 0:
        raise RuntimeError("precontact_replay_world_index_invalid")
    return value


def _pick_state(controller: Any) -> dict[str, Any]:
    pick = getattr(controller, "pick_controller", None)
    if pick is None:
        raise RuntimeError("precontact_replay_pick_controller_missing")
    return {
        "start": bool(pick._start),
        "event": int(pick._event),
        "last_emitted_event": pick._last_emitted_event,
        "close": bool(pick._close_command_emitted),
        "lift": bool(pick._lift_command_emitted),
    }


def _joint_limits(np: Any, robot: Any) -> tuple[list[float], list[float]]:
    properties = robot.dof_properties
    names = getattr(getattr(properties, "dtype", None), "names", None)
    if names is None or not {"lower", "upper"} <= set(names):
        raise RuntimeError("precontact_replay_joint_limits_missing")
    lower = _finite_vector(np, properties["lower"], field="joint_lower", length=9)
    upper = _finite_vector(np, properties["upper"], field="joint_upper", length=9)
    if any(left >= right for left, right in zip(lower, upper, strict=True)):
        raise RuntimeError("precontact_replay_joint_limits_invalid")
    return lower, upper


def _source_position(np: Any, task: Any) -> list[float]:
    center = task.object_utils.get_geometry_center(object_path=task.current_obj_path)
    return _finite_vector(np, center, field="source_position", length=3)


def _row_matrix_from_pose(np: Any, position: Any, orientation_wxyz: Any) -> list[float]:
    translation = np.asarray(position, dtype=np.float64)
    orientation = np.asarray(orientation_wxyz, dtype=np.float64)
    if (
        translation.shape != (3,)
        or orientation.shape != (4,)
        or not np.isfinite(translation).all()
        or not np.isfinite(orientation).all()
    ):
        raise RuntimeError("precontact_snapshot_physx_pose_invalid")
    norm = float(np.linalg.norm(orientation))
    if not math.isfinite(norm) or norm <= 1.0e-12:
        raise RuntimeError("precontact_snapshot_physx_pose_invalid")
    w, x, y, z = orientation / norm
    column_rotation = np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)],
            [2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)],
            [2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = column_rotation.T
    matrix[3, :3] = translation
    return [float(value) for value in matrix.reshape(-1).tolist()]


def _usd_world_matrix(np: Any, Usd: Any, UsdGeom: Any, stage: Any, path: str) -> list[float]:
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"precontact_snapshot_matrix_prim_missing:{path}")
    matrix = np.asarray(
        UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()),
        dtype=np.float64,
    )
    if (
        matrix.shape != (4, 4)
        or not np.isfinite(matrix).all()
        or not np.allclose(matrix[:, 3], [0.0, 0.0, 0.0, 1.0], rtol=0.0, atol=1.0e-12)
    ):
        raise RuntimeError(f"precontact_snapshot_matrix_invalid:{path}")
    return [float(value) for value in matrix.reshape(-1).tolist()]


def _collider_relative_matrix(
    np: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    *,
    collider_path: str,
) -> list[float]:
    collider = stage.GetPrimAtPath(collider_path)
    source = stage.GetPrimAtPath(SOURCE_ROOT_PATH)
    if not collider or not collider.IsValid() or not source or not source.IsValid():
        raise RuntimeError("precontact_snapshot_relative_prim_missing")
    relative, resets_xform_stack = UsdGeom.XformCache(
        Usd.TimeCode.Default()
    ).ComputeRelativeTransform(collider, source)
    matrix = np.asarray(relative, dtype=np.float64)
    if (
        resets_xform_stack
        or matrix.shape != (4, 4)
        or not np.isfinite(matrix).all()
        or not np.allclose(matrix[:, 3], [0.0, 0.0, 0.0, 1.0], rtol=0.0, atol=1.0e-12)
    ):
        raise RuntimeError("precontact_snapshot_relative_matrix_invalid")
    return [float(value) for value in matrix.reshape(-1).tolist()]


def _source_colliders(Usd: Any, UsdPhysics: Any, stage: Any) -> list[tuple[str, str]]:
    source_root = stage.GetPrimAtPath(SOURCE_ROOT_PATH)
    mesh = stage.GetPrimAtPath(SOURCE_MESH_PATH)
    wrapper = stage.GetPrimAtPath(SOURCE_WRAPPER_ROOT_PATH)
    if (
        not source_root
        or not source_root.IsValid()
        or not mesh
        or not mesh.IsValid()
        or not wrapper
        or not wrapper.IsValid()
    ):
        raise RuntimeError("precontact_snapshot_collider_root_missing")

    def enabled(root: Any) -> list[str]:
        paths = []
        for prim in Usd.PrimRange(root):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                continue
            attribute = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr()
            if attribute and attribute.Get() is False:
                continue
            paths.append(str(prim.GetPath()))
        return sorted(set(paths))

    mesh_paths = enabled(mesh)
    wrapper_paths = enabled(wrapper)
    root_paths = enabled(source_root)
    expected_paths = sorted([*mesh_paths, *wrapper_paths])
    if (
        mesh_paths != [SOURCE_MESH_PATH]
        or len(wrapper_paths) != 145
        or root_paths != expected_paths
    ):
        raise RuntimeError("precontact_snapshot_collider_inventory_invalid")
    return sorted(
        [(path, "external_shell") for path in mesh_paths]
        + [(path, "internal_wrapper") for path in wrapper_paths],
        key=lambda item: item[0],
    )


def _capture_source_collider_closure(
    *,
    np: Any,
    Usd: Any,
    UsdGeom: Any,
    UsdPhysics: Any,
    stage: Any,
    source_reader: Any,
    transition_index: int,
    world_index_after_transition: int,
    task_frame_idx: int,
    event0_raw_action_sha256: str,
    event0_resolved_position_target_sha256: str,
    world_index_reader: Any,
) -> dict[str, Any]:
    before = world_index_reader()
    if before != world_index_after_transition:
        raise RuntimeError("precontact_snapshot_capture_world_index_invalid")
    position, orientation = source_reader.get_world_pose()
    physx_matrix = _row_matrix_from_pose(np, position, orientation)
    usd_matrix = _usd_world_matrix(np, Usd, UsdGeom, stage, SOURCE_ROOT_PATH)
    physx_array = np.asarray(physx_matrix, dtype=np.float64).reshape(4, 4)
    colliders = []
    for path, role in _source_colliders(Usd, UsdPhysics, stage):
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise RuntimeError("precontact_snapshot_collider_missing")
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is False:
            raise RuntimeError("precontact_snapshot_collider_disabled")
        relative = _collider_relative_matrix(np, Usd, UsdGeom, stage, collider_path=path)
        composed = np.asarray(relative, dtype=np.float64).reshape(4, 4) @ physx_array
        colliders.append(
            {
                "path": path,
                "role": role,
                "collision_enabled": True,
                "rigid_owner_path": SOURCE_ROOT_PATH,
                "collider_to_source_root_row_major": relative,
                "usd_world_matrix_row_major": _usd_world_matrix(np, Usd, UsdGeom, stage, path),
                "composed_world_matrix_row_major": [
                    float(value) for value in composed.reshape(-1).tolist()
                ],
            }
        )
    after = world_index_reader()
    if after != before:
        raise RuntimeError("precontact_snapshot_capture_advanced_physics")
    payload = {
        "authority": snapshot_replay.SOURCE_CLOSURE_AUTHORITY,
        "matrix_convention": snapshot_replay.MATRIX_CONVENTION,
        "source_root_path": SOURCE_ROOT_PATH,
        "capture": {
            "transition_index": transition_index,
            "world_index_after_transition": world_index_after_transition,
            "task_frame_idx": task_frame_idx,
            "event0_raw_action_sha256": event0_raw_action_sha256,
            "event0_resolved_position_target_sha256": event0_resolved_position_target_sha256,
            "event0_apply_count_at_capture": 0,
            "world_index_after_capture": after,
        },
        "source_root": {
            "physx_world_matrix_row_major": physx_matrix,
            "usd_world_matrix_row_major": usd_matrix,
            "linear_velocity_m_s": _finite_vector(
                np, source_reader.get_linear_velocity(), field="source_linear_velocity", length=3
            ),
            "angular_velocity_rad_s": _finite_vector(
                np, source_reader.get_angular_velocity(), field="source_angular_velocity", length=3
            ),
        },
        "colliders": colliders,
    }
    return {**payload, "sha256": snapshot_replay.canonical_json_sha256(payload)}


def _scope(controller: Any, guard_counts: Mapping[str, int], *, event0_applied: bool) -> dict[str, Any]:
    pick = _pick_state(controller)
    phase = str(getattr(getattr(controller, "current_phase", None), "name", "UNKNOWN"))
    pour_count = int(getattr(controller, "_pour_forward_invocation_count", 0))
    if (
        pick["close"]
        or pick["lift"]
        or phase != "PICKING"
        or pour_count != 0
        or guard_counts.get("attachment", -1) != 0
        or guard_counts.get("contact_observer", -1) != 0
        or guard_counts.get("phase3_or_gate", -1) != 0
    ):
        raise RuntimeError("precontact_replay_forbidden_controller_state")
    return {
        "close_command_emitted": False,
        "lift_command_emitted": False,
        "attachment_invocation_count": guard_counts["attachment"],
        "contact_observer_invocation_count": guard_counts["contact_observer"],
        "phase3_or_gate_evaluated": False,
        "event0_integrated": False,
        "event0_action_applied": event0_applied,
    }


def _fixed_mount_filter_record(
    *,
    Usd: Any,
    UsdPhysics: Any,
    stage: Any,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the one approved collider-level relation after composition."""
    filter_profile = profile["filter"]
    author = filter_profile["author_collider_path"]
    target = filter_profile["target_collider_path"]
    author_prim = stage.GetPrimAtPath(author)
    target_prim = stage.GetPrimAtPath(target)
    if (
        not author_prim
        or not author_prim.IsValid()
        or not target_prim
        or not target_prim.IsValid()
        or not author_prim.HasAPI(UsdPhysics.CollisionAPI)
        or not target_prim.HasAPI(UsdPhysics.CollisionAPI)
        or UsdPhysics.CollisionAPI(author_prim).GetCollisionEnabledAttr().Get() is False
        or UsdPhysics.CollisionAPI(target_prim).GetCollisionEnabledAttr().Get() is False
        or not author_prim.HasAPI(UsdPhysics.FilteredPairsAPI)
    ):
        raise RuntimeError("precontact_fixed_mount_filter_missing")
    relation = UsdPhysics.FilteredPairsAPI(author_prim).GetFilteredPairsRel()
    if sorted(str(path) for path in relation.GetTargets()) != [target]:
        raise RuntimeError("precontact_fixed_mount_filter_targets_invalid")
    robot_filtered_pairs = []
    collision_group_memberships = []
    for prim in Usd.PrimRange.Stage(stage):
        if prim.HasAPI(UsdPhysics.FilteredPairsAPI):
            left = str(prim.GetPath())
            for relationship_target in UsdPhysics.FilteredPairsAPI(prim).GetFilteredPairsRel().GetTargets():
                right = str(relationship_target)
                if left.startswith("/World/Franka") or right.startswith("/World/Franka"):
                    robot_filtered_pairs.append([left, right])
        if prim.IsA(UsdPhysics.CollisionGroup):
            owner = str(prim.GetPath())
            for relationship in prim.GetRelationships():
                for relationship_target in relationship.GetTargets():
                    related = str(relationship_target)
                    if related.startswith("/World/Franka") or related.startswith("/World/table"):
                        collision_group_memberships.append(
                            [owner, str(relationship.GetName()), related]
                        )
    robot_filtered_pairs.sort()
    collision_group_memberships.sort()
    if (
        robot_filtered_pairs != [[author, target]]
        or collision_group_memberships
    ):
        raise RuntimeError("precontact_fixed_mount_filter_scope_invalid")
    return {
        "authority": snapshot_replay.FIXED_MOUNT_RUNTIME_FILTER_AUTHORITY,
        "profile_sha256": profile["profile_sha256"],
        "author_collider_path": author,
        "target_collider_path": target,
        "filtered_pair": sorted([author, target]),
        "authored_filtered_pair_paths": [[author, target]],
        "robot_filtered_pair_paths": robot_filtered_pairs,
        "collision_group_membership_paths": collision_group_memberships,
    }


def _preapply_action_allowed(
    raw_action: Mapping[str, Any], *, transition_index: int, lower: Sequence[float], upper: Sequence[float]
) -> bool:
    positions = raw_action["joint_positions"]
    if transition_index == 4:
        if (
            raw_action["joint_indices"] is not None
            or raw_action["joint_velocities"] is not None
            or raw_action["joint_efforts"] is not None
            or not isinstance(positions, list)
            or len(positions) != 9
            or any(value is not None for value in positions[:7])
            or any(value is None for value in positions[7:])
        ):
            raise RuntimeError("precontact_replay_opening_action_invalid")
        return all(
            lower[index] - 1.0e-8 <= float(value) <= upper[index] + 1.0e-8
            for index, value in enumerate(positions)
            if value is not None
        )
    if transition_index == 5:
        if (
            raw_action["joint_indices"] != list(range(7))
            or not isinstance(positions, list)
            or not isinstance(raw_action["joint_velocities"], list)
            or raw_action["joint_efforts"] is not None
            or len(positions) != 7
            or len(raw_action["joint_velocities"]) != 7
            or any(value is None for value in positions)
        ):
            raise RuntimeError("precontact_replay_event0_action_invalid")
        return all(
            lower[index] <= float(value) <= upper[index]
            for index, value in zip(raw_action["joint_indices"], positions, strict=True)
        )
    raise RuntimeError("precontact_replay_unexpected_action_transition")


def run_precontact_event0_replay(
    *,
    app: Any,
    out_dir: Path,
    frozen_config: Mapping[str, Any],
    contract: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    """Replay reset/pre-roll/open/event0 and stop before event0 can integrate."""
    snapshot_v2 = isinstance(contract, Mapping) and contract.get("authority") in {
        snapshot_replay.AUTHORITY,
        snapshot_replay.FIXED_MOUNT_AUTHORITY,
    }
    fixed_mount = (
        isinstance(contract, Mapping)
        and contract.get("authority") == snapshot_replay.FIXED_MOUNT_AUTHORITY
    )
    expected_authority = (
        snapshot_replay.FIXED_MOUNT_AUTHORITY
        if fixed_mount
        else snapshot_replay.AUTHORITY
        if snapshot_v2
        else replay.AUTHORITY
    )
    expected_classification = (
        snapshot_replay.FIXED_MOUNT_CLASSIFICATION
        if fixed_mount
        else snapshot_replay.CLASSIFICATION
        if snapshot_v2
        else "FORMAL_PRECONTACT_EVENT0_REPLAY_ONLY"
    )
    if (
        not isinstance(frozen_config, Mapping)
        or not isinstance(contract, Mapping)
        or not isinstance(runtime, Mapping)
        or contract.get("authority") != expected_authority
        or contract.get("classification") != expected_classification
    ):
        raise RuntimeError("precontact_replay_contract_invalid")
    from isaacsim_compat import install_legacy_isaacsim_aliases

    install_legacy_isaacsim_aliases()
    import numpy as np
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.utils.stage import add_reference_to_stage
    from factories.controller_factory import create_controller
    from factories.robot_factory import create_robot
    from factories.task_factory import create_task
    from omni.isaac.core.prims import RigidPrimView
    from omegaconf import OmegaConf
    from pxr import Usd, UsdGeom, UsdPhysics
    from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as native
    from utils.object_utils import ObjectUtils

    config = frozen_config.get("config")
    diagnostic = config.get("diagnostic") if isinstance(config, Mapping) else None
    local_scene = frozen_config.get("local_scene")
    local_franka = frozen_config.get("local_franka")
    if (
        not isinstance(config, Mapping)
        or not isinstance(diagnostic, Mapping)
        or not isinstance(local_scene, Mapping)
        or not isinstance(local_franka, Mapping)
        or frozen_config.get("sha256") != contract.get("v7_config_sha256")
        or local_scene.get("sha256") != contract.get("local_scene_sha256")
        or local_franka.get("sha256") != contract.get("local_franka_sha256")
        or native.g0_source_settle_pre_roll_steps(diagnostic) != contract.get("pre_roll_steps")
    ):
        raise RuntimeError("precontact_replay_frozen_binding_invalid")
    fixed_mount_profile = None
    runtime_config = config
    if fixed_mount:
        try:
            fixed_mount_profile = snapshot_replay.validate_fixed_mount_profile(
                contract.get("fixed_mount_profile")
            )
        except ValueError as exc:
            raise RuntimeError("precontact_fixed_mount_profile_invalid") from exc
        runtime_config = copy.deepcopy(dict(config))
        runtime_config["robot"]["position"] = list(fixed_mount_profile["robot_position_m"])
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("precontact_replay_stage_missing")
    world = World(
        stage_units_in_meters=float(diagnostic["stage_units_in_meters"]),
        physics_prim_path=str(diagnostic["physics_scene_path"]),
        backend="numpy",
        physics_dt=float(diagnostic["physics_dt"]),
    )
    robot = native.create_diagnostic_local_franka(
        create_robot, runtime_config, local_franka=local_franka
    )
    add_reference_to_stage(usd_path=str(local_scene["absolute_usd_path"]), prim_path="/World")
    overlay = diagnostic.get("hidden_cube_treatment")
    if not isinstance(overlay, Mapping):
        raise RuntimeError("precontact_replay_hidden_cube_missing")
    overlay_path = Path(native.REPO_ROOT / str(overlay.get("usd_path", ""))).resolve()
    if not overlay_path.is_file() or _sha256_file(overlay_path) != contract.get("hidden_cube_overlay_sha256"):
        raise RuntimeError("precontact_replay_hidden_cube_binding_invalid")
    session = stage.GetSessionLayer()
    if session is None:
        raise RuntimeError("precontact_replay_session_layer_missing")
    if str(overlay_path) not in session.subLayerPaths:
        session.subLayerPaths.append(str(overlay_path))
    fixed_mount_filter = None
    if fixed_mount:
        if fixed_mount_profile is None:
            raise RuntimeError("precontact_fixed_mount_profile_missing")
        filter_overlay_path = Path(
            native.REPO_ROOT / fixed_mount_profile["filter"]["overlay_path"]
        ).resolve()
        if (
            not filter_overlay_path.is_file()
            or _sha256_file(filter_overlay_path)
            != fixed_mount_profile["filter"]["overlay_sha256"]
        ):
            raise RuntimeError("precontact_fixed_mount_overlay_binding_invalid")
        if str(filter_overlay_path) not in session.subLayerPaths:
            session.subLayerPaths.append(str(filter_overlay_path))
        app.update()
    ObjectUtils.get_instance(stage)
    cfg = OmegaConf.create(native.apply_g0_layout_treatment(runtime_config))
    task = create_task(str(runtime_config["task_type"]), cfg=cfg, world=world, stage=stage, robot=robot)
    np.random.seed(int(diagnostic["numpy_seed"]))
    task.reset()
    controller = create_controller(str(runtime_config["controller_type"]), cfg=cfg, robot=robot)
    guard_counts = {"attachment": 0, "contact_observer": 0, "phase3_or_gate": 0}
    if (
        getattr(controller, "_use_contact_pick_controller", None) is not False
        or getattr(controller, "_contact_grasp_required", None) is not False
        or getattr(controller, "_contact_acquisition_probe", None) is not False
        or type(getattr(controller, "pick_controller", None)).__name__ != "PickController"
    ):
        raise RuntimeError("precontact_replay_contact_or_gate_path_enabled")
    gripper_control = getattr(controller, "gripper_control", None)
    add_object_to_gripper = getattr(gripper_control, "add_object_to_gripper", None)
    if callable(add_object_to_gripper):
        def _deny_attachment(*_args: Any, **_kwargs: Any) -> None:
            guard_counts["attachment"] += 1
            raise RuntimeError("precontact_replay_attachment_forbidden")

        gripper_control.add_object_to_gripper = _deny_attachment
    source_prim = stage.GetPrimAtPath(SOURCE_ROOT_PATH)
    if not source_prim or not source_prim.IsValid() or not source_prim.HasAPI(UsdPhysics.RigidBodyAPI):
        raise RuntimeError("precontact_replay_dynamic_source_missing")
    source_reader = None
    if snapshot_v2:
        source_reader = native.RuntimeReadOnlySourceAdapter(RigidPrimView, SOURCE_ROOT_PATH)
        source_reader.initialize()
    pre_roll_before = _world_index(world)
    pre_roll_world_step_call_count = 0
    for _ in range(contract["pre_roll_steps"]):
        world.step(render=False)
        pre_roll_world_step_call_count += 1
    pre_roll_after = _world_index(world)
    if pre_roll_world_step_call_count != contract["pre_roll_steps"] or pre_roll_after <= pre_roll_before:
        raise RuntimeError(
            "precontact_replay_pre_roll_cadence_invalid:"
            f"before={pre_roll_before}:after={pre_roll_after}:"
            f"calls={pre_roll_world_step_call_count}:"
            f"playing={world.is_playing()}:stopped={world.is_stopped()}"
        )
    transitions = []
    event0_applied = False
    source_collider_closure = None
    for transition_index in range(contract["transition_count"]):
        before = _world_index(world)
        world.step(render=True)
        after = _world_index(world)
        if after <= before:
            raise RuntimeError("precontact_replay_transition_cadence_invalid")
        state = task.step()
        action = None
        controller_called = state is not None
        if controller_called:
            result = controller.step(state)
            if not isinstance(result, tuple) or len(result) != 3:
                raise RuntimeError("precontact_replay_controller_result_invalid")
            action, done, success = result
            if done or success:
                raise RuntimeError("precontact_replay_early_terminal_invalid")
        positions = _finite_vector(np, robot.get_joint_positions(), field="joint_positions", length=9)
        velocities = _finite_vector(np, robot.get_joint_velocities(), field="joint_velocities", length=9)
        lower, upper = _joint_limits(np, robot)
        raw_action = _raw_action(np, action) if action is not None else None
        apply_count = 0
        if action is not None:
            allowed = _preapply_action_allowed(
                raw_action, transition_index=transition_index, lower=lower, upper=upper
            )
            if transition_index == 4 and not allowed:
                raise RuntimeError("precontact_replay_opening_target_out_of_limit")
            if snapshot_v2 and transition_index == 5:
                if source_reader is None or raw_action is None:
                    raise RuntimeError("precontact_snapshot_source_reader_missing")
                resolved_target = list(positions)
                for index, value in zip(
                    raw_action["joint_indices"], raw_action["joint_positions"], strict=True
                ):
                    if value is None:
                        raise RuntimeError("precontact_snapshot_event0_target_invalid")
                    resolved_target[index] = value
                source_collider_closure = _capture_source_collider_closure(
                    np=np,
                    Usd=Usd,
                    UsdGeom=UsdGeom,
                    UsdPhysics=UsdPhysics,
                    stage=stage,
                    source_reader=source_reader,
                    transition_index=transition_index,
                    world_index_after_transition=after,
                    task_frame_idx=int(task.frame_idx),
                    event0_raw_action_sha256=snapshot_replay.canonical_json_sha256(raw_action),
                    event0_resolved_position_target_sha256=snapshot_replay.canonical_json_sha256(
                        resolved_target
                    ),
                    world_index_reader=lambda: _world_index(world),
                )
            if transition_index == 5 and allowed:
                robot.get_articulation_controller().apply_action(action)
                apply_count = 1
                event0_applied = True
            elif transition_index == 4:
                robot.get_articulation_controller().apply_action(action)
                apply_count = 1
        pick = _pick_state(controller)
        transitions.append(
            {
                "transition_index": transition_index,
                "world_index_before": before,
                "world_index_after": after,
                "task_frame_idx": int(task.frame_idx),
                "controller_called": controller_called,
                "raw_action": raw_action,
                "raw_action_sha256": replay.canonical_json_sha256(raw_action) if raw_action is not None else None,
                "apply_count": apply_count,
                "pick": pick,
                "controller_phase": str(getattr(getattr(controller, "current_phase", None), "name", "UNKNOWN")),
                "pour_forward_invocation_count": int(getattr(controller, "_pour_forward_invocation_count", 0)),
                "joint_positions_before_action": positions,
                "joint_velocities_before_action": velocities,
                "joint_lower_limits": lower,
                "joint_upper_limits": upper,
                "source_position": _source_position(np, task),
            }
        )
        _scope(controller, guard_counts, event0_applied=event0_applied)
    if snapshot_v2 and source_collider_closure is None:
        raise RuntimeError("precontact_snapshot_closure_not_captured")
    if fixed_mount:
        if fixed_mount_profile is None:
            raise RuntimeError("precontact_fixed_mount_profile_missing")
        fixed_mount_filter = _fixed_mount_filter_record(
            Usd=Usd,
            UsdPhysics=UsdPhysics,
            stage=stage,
            profile=fixed_mount_profile,
        )
    terminal = {
        "world_index": _world_index(world),
        "event0_action_applied": event0_applied,
        "event0_integrated": False,
        "close": False,
        "lift": False,
        "phase": "PICKING",
    }
    if snapshot_v2:
        terminal["source_collider_closure"] = source_collider_closure
    if fixed_mount:
        if fixed_mount_filter is None:
            raise RuntimeError("precontact_fixed_mount_filter_missing")
        terminal["fixed_mount_filter"] = fixed_mount_filter
    trace = {
        "schema_version": 3 if fixed_mount else 2 if snapshot_v2 else 1,
        "authority": expected_authority,
        "pre_roll": {
            "requested_steps": contract["pre_roll_steps"],
            "world_step_call_count": pre_roll_world_step_call_count,
            "world_index_before": pre_roll_before,
            "world_index_after": pre_roll_after,
        },
        "transitions": transitions,
        "terminal": terminal,
    }
    evaluation = (
        snapshot_replay.evaluate_precontact_event0_snapshot_replay(trace, contract)
        if snapshot_v2
        else replay.evaluate_precontact_event0_replay(trace, contract)
    )
    trace_path = out_dir / TRACE_NAME
    _write_create_only(trace_path, trace)
    scope = _scope(controller, guard_counts, event0_applied=event0_applied)
    return {
        "schema_version": 3 if fixed_mount else 2 if snapshot_v2 else 1,
        "manifest_type": (
            "formal_precontact_event0_fixed_mount_snapshot_replay_v3_child"
            if fixed_mount
            else "formal_precontact_event0_snapshot_replay_v2_child"
            if snapshot_v2
            else "formal_precontact_event0_replay_v1_child"
        ),
        "authority": expected_authority,
        "classification": expected_classification,
        "decision": evaluation["decision"],
        "contract": dict(contract),
        "runtime": dict(runtime),
        "scope": scope,
        "trace": {"path": trace_path.name, "sha256": _sha256_file(trace_path)},
        "evaluation": evaluation,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
