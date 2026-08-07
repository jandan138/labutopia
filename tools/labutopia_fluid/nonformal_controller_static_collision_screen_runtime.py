"""Attested-child implementation of the v7 paused static collision screen.

All simulator interaction occurs only after runtime attestation.  One World
reset is permitted for initialization; after its paused baseline, controller
outputs are materialized through direct articulation joint positions without
an explicit world step.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import nonformal_controller_static_collision_screen as screen


SOURCE_ROOT_PATH = "/World/beaker2"
SOURCE_MESH_PATH = "/World/beaker2/mesh"
WRAPPER_ROOT_PATH = "/World/beaker2/FluidSafeWrapperCanonical"
BEAKER1_PATH = "/World/beaker1"
BEAKER1_WRAPPER_ROOT_PATH = "/World/beaker1/FluidSafeWrapperCanonical"
ROBOT_ROOT_PATH = "/World/Franka"
TABLE_ROOT_PATH = "/World/table"
TABLE_PATH = "/World/table/surface/mesh"
DEFAULT_CONTROL_DT_S = 1.0 / 60.0
JOINT_READBACK_ATOL = 1.0e-8
MATRIX_CHANGE_ATOL = 1.0e-10
SOURCE_STABILITY_ATOL = 1.0e-10
SEMANTICS_ARTIFACT_NAME = "controller_semantics.json"


class _JointLimitViolation(RuntimeError):
    def __init__(self, violations: list[dict[str, float | int]]) -> None:
        super().__init__("controller_static_screen_joint_limit_violation")
        self.violations = violations


def _canonical_json_bytes(value: Any) -> bytes:
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


def _finite_vector(np: Any, value: Any, *, field: str, length: int | None = None) -> list[float]:
    array = np.asarray(value, dtype=np.float64)
    if (
        array.ndim != 1
        or (length is not None and array.shape != (length,))
        or not np.isfinite(array).all()
    ):
        raise RuntimeError(f"controller_static_screen_{field}_invalid")
    return [float(item) for item in array.tolist()]


def _enabled_colliders(Usd: Any, UsdPhysics: Any, stage: Any, root_path: str) -> list[str]:
    root = stage.GetPrimAtPath(root_path)
    if not root or not root.IsValid():
        raise RuntimeError(f"controller_static_screen_collider_root_missing:{root_path}")
    colliders = []
    for prim in Usd.PrimRange(root):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = prim.GetAttribute("physics:collisionEnabled")
        if enabled and enabled.Get() is False:
            continue
        colliders.append(str(prim.GetPath()))
    if not colliders:
        raise RuntimeError(f"controller_static_screen_colliders_missing:{root_path}")
    return sorted(set(colliders))


def _runtime_receipt(world: Any, timeline: Any) -> dict[str, Any]:
    try:
        world_index = int(world.current_time_step_index)
        timeline_time_s = float(timeline.get_current_time())
        is_playing = bool(timeline.is_playing())
        is_stopped = bool(timeline.is_stopped())
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError("controller_static_screen_runtime_counter_unavailable") from exc
    if not math.isfinite(timeline_time_s) or world_index < 0:
        raise RuntimeError("controller_static_screen_runtime_counter_invalid")
    return {
        "world_index": world_index,
        "timeline_time_s": timeline_time_s,
        "is_playing": is_playing,
        "is_stopped": is_stopped,
    }


def _require_paused_unchanged(
    world: Any,
    timeline: Any,
    baseline: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    observed = _runtime_receipt(world, timeline)
    if (
        observed != dict(baseline)
        or observed["is_playing"]
        or observed["is_stopped"]
    ):
        raise RuntimeError(f"controller_static_screen_paused_state_changed:{context}")
    return observed


def _stopped_receipt(timeline: Any) -> dict[str, Any]:
    try:
        receipt = {
            "timeline_time_s": float(timeline.get_current_time()),
            "is_playing": bool(timeline.is_playing()),
            "is_stopped": bool(timeline.is_stopped()),
        }
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError("controller_static_screen_timeline_counter_unavailable") from exc
    if not math.isfinite(receipt["timeline_time_s"]):
        raise RuntimeError("controller_static_screen_timeline_counter_invalid")
    return receipt


def _require_query_timeline_unchanged(
    world: Any | None,
    timeline: Any,
    baseline: Mapping[str, Any],
    *,
    context: str,
) -> None:
    if world is None:
        observed = _stopped_receipt(timeline)
        if (
            observed != dict(baseline)
            or observed["is_playing"]
            or not observed["is_stopped"]
        ):
            raise RuntimeError(
                f"controller_static_screen_stopped_query_state_changed:{context}"
            )
        return
    _require_paused_unchanged(world, timeline, baseline, context=context)


def _pause_after_reset(
    app: Any,
    world: Any,
    timeline: Any,
    *,
    post_reset_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    timeline.pause()
    app.update()
    receipt = _runtime_receipt(world, timeline)
    if (
        receipt["is_playing"]
        or receipt["is_stopped"]
        or receipt["world_index"] != post_reset_receipt["world_index"]
        or receipt["timeline_time_s"] != post_reset_receipt["timeline_time_s"]
    ):
        raise RuntimeError("controller_static_screen_timeline_not_paused")
    return receipt


def _world_matrix(np: Any, Usd: Any, UsdGeom: Any, stage: Any, path: str) -> Any:
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"controller_static_screen_matrix_prim_missing:{path}")
    matrix = np.asarray(
        UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()),
        dtype=np.float64,
    )
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise RuntimeError(f"controller_static_screen_matrix_invalid:{path}")
    return matrix


def _relative_matrix(
    np: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    *,
    child_path: str,
    owner_path: str,
) -> Any:
    child = stage.GetPrimAtPath(child_path)
    owner = stage.GetPrimAtPath(owner_path)
    if (
        not child
        or not child.IsValid()
        or not owner
        or not owner.IsValid()
    ):
        raise RuntimeError("controller_static_screen_relative_prim_missing")
    relative, resets_xform_stack = UsdGeom.XformCache(
        Usd.TimeCode.Default()
    ).ComputeRelativeTransform(child, owner)
    matrix = np.asarray(relative, dtype=np.float64)
    if (
        resets_xform_stack
        or matrix.shape != (4, 4)
        or not np.isfinite(matrix).all()
        or not np.allclose(matrix[:, 3], [0.0, 0.0, 0.0, 1.0], rtol=0.0, atol=1.0e-12)
    ):
        raise RuntimeError("controller_static_screen_relative_transform_invalid")
    return matrix


def _link_transform_array(np: Any, physics_view: Any, *, expected_links: int) -> Any:
    raw = physics_view.get_link_transforms()
    if hasattr(raw, "detach"):
        raw = raw.detach().cpu().numpy()
    elif hasattr(raw, "numpy"):
        raw = raw.numpy()
    transforms = np.asarray(raw, dtype=np.float64).copy()
    if (
        transforms.shape != (1, expected_links, 7)
        or not np.isfinite(transforms).all()
    ):
        raise RuntimeError("controller_static_screen_link_transform_tensor_invalid")
    return transforms


def _row_matrix_from_link_transform(np: Any, Rotation: Any, value: Any) -> Any:
    transform = np.asarray(value, dtype=np.float64)
    if transform.shape != (7,) or not np.isfinite(transform).all():
        raise RuntimeError("controller_static_screen_link_transform_invalid")
    position = transform[:3]
    quaternion_xyzw = transform[3:]
    norm = float(np.linalg.norm(quaternion_xyzw))
    if not math.isfinite(norm) or abs(norm - 1.0) > 1.0e-3:
        raise RuntimeError("controller_static_screen_link_quaternion_invalid")
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = Rotation.from_quat(quaternion_xyzw / norm).as_matrix().T
    matrix[3, :3] = position
    return matrix


def _robot_kinematic_model(
    *,
    np: Any,
    Rotation: Any,
    Usd: Any,
    UsdGeom: Any,
    UsdPhysics: Any,
    stage: Any,
    robot: Any,
    expected_simulation_view: Any,
    collider_paths: Sequence[str],
) -> dict[str, Any]:
    articulation_view = getattr(robot, "_articulation_view", None)
    physics_view = getattr(articulation_view, "_physics_view", None)
    simulation_view = getattr(articulation_view, "_physics_sim_view", None)
    body_names = list(getattr(articulation_view, "body_names", ()) or ())
    if (
        physics_view is None
        or simulation_view is not expected_simulation_view
        or len(body_names) != 12
        or len(body_names) != len(set(body_names))
    ):
        raise RuntimeError("controller_static_screen_articulation_tensor_view_invalid")
    owner_indices = {
        f"{ROBOT_ROOT_PATH}/{name}": index
        for index, name in enumerate(body_names)
    }
    for owner_path in owner_indices:
        owner = stage.GetPrimAtPath(owner_path)
        if not owner or not owner.IsValid() or not owner.HasAPI(UsdPhysics.RigidBodyAPI):
            raise RuntimeError("controller_static_screen_link_owner_invalid")
    owner_by_collider = {}
    relative_by_collider = {}
    for collider_path in collider_paths:
        owner_path = _nearest_rigid_owner(UsdPhysics, stage, collider_path)
        if owner_path not in owner_indices:
            raise RuntimeError("controller_static_screen_collider_owner_invalid")
        owner_by_collider[collider_path] = owner_path
        relative_by_collider[collider_path] = _relative_matrix(
            np,
            Usd,
            UsdGeom,
            stage,
            child_path=collider_path,
            owner_path=owner_path,
        )
    tool_center_path = f"{ROBOT_ROOT_PATH}/panda_hand/tool_center"
    hand_path = f"{ROBOT_ROOT_PATH}/panda_hand"
    if hand_path not in owner_indices:
        raise RuntimeError("controller_static_screen_hand_link_missing")
    tool_center_relative = _relative_matrix(
        np,
        Usd,
        UsdGeom,
        stage,
        child_path=tool_center_path,
        owner_path=hand_path,
    )
    model = {
        "body_names": body_names,
        "owner_indices": owner_indices,
        "owner_by_collider": owner_by_collider,
        "relative_by_collider": relative_by_collider,
        "tool_center_relative": tool_center_relative,
        "physics_view": physics_view,
        "simulation_view": simulation_view,
    }
    owner_matrices = _robot_owner_world_matrices(np, Rotation, model)
    for owner_path in owner_indices:
        authored = _world_matrix(np, Usd, UsdGeom, stage, owner_path)
        if not np.allclose(
            owner_matrices[owner_path], authored, rtol=0.0, atol=5.0e-4
        ):
            raise RuntimeError("controller_static_screen_link_tensor_usd_baseline_mismatch")
    return model


def _robot_owner_world_matrices(np: Any, Rotation: Any, model: Mapping[str, Any]) -> dict[str, Any]:
    owner_indices = model.get("owner_indices")
    physics_view = model.get("physics_view")
    if not isinstance(owner_indices, Mapping) or physics_view is None:
        raise RuntimeError("controller_static_screen_articulation_tensor_view_invalid")
    transforms = _link_transform_array(
        np, physics_view, expected_links=len(owner_indices)
    )
    return {
        owner_path: _row_matrix_from_link_transform(
            np, Rotation, transforms[0, index]
        )
        for owner_path, index in owner_indices.items()
    }


def _robot_collider_world_matrices(
    np: Any, Rotation: Any, model: Mapping[str, Any]
) -> dict[str, Any]:
    owner_matrices = _robot_owner_world_matrices(np, Rotation, model)
    owner_by_collider = model.get("owner_by_collider")
    relative_by_collider = model.get("relative_by_collider")
    if not isinstance(owner_by_collider, Mapping) or not isinstance(
        relative_by_collider, Mapping
    ):
        raise RuntimeError("controller_static_screen_collider_owner_invalid")
    result = {}
    for collider_path, owner_path in owner_by_collider.items():
        matrix = np.asarray(relative_by_collider.get(collider_path), dtype=np.float64)
        owner_world = owner_matrices.get(owner_path)
        if (
            matrix.shape != (4, 4)
            or owner_world is None
            or not np.isfinite(matrix).all()
        ):
            raise RuntimeError("controller_static_screen_collider_transform_invalid")
        result[collider_path] = matrix @ owner_world
    return result


def _robot_tool_center_position(np: Any, Rotation: Any, model: Mapping[str, Any]) -> Any:
    owner_matrices = _robot_owner_world_matrices(np, Rotation, model)
    hand_world = owner_matrices.get(f"{ROBOT_ROOT_PATH}/panda_hand")
    relative = np.asarray(model.get("tool_center_relative"), dtype=np.float64)
    if (
        hand_world is None
        or relative.shape != (4, 4)
        or not np.isfinite(relative).all()
    ):
        raise RuntimeError("controller_static_screen_tool_center_transform_invalid")
    matrix = relative @ hand_world
    position = matrix[3, :3]
    if not np.isfinite(position).all():
        raise RuntimeError("controller_static_screen_tool_center_transform_invalid")
    return position


def _nearest_rigid_owner(UsdPhysics: Any, stage: Any, collider_path: str) -> str | None:
    prim = stage.GetPrimAtPath(collider_path)
    while prim and prim.IsValid():
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            return str(prim.GetPath())
        prim = prim.GetParent()
    return None


def _query_cooked_rigid_body(
    *,
    app: Any,
    np: Any,
    stage: Any,
    timeline: Any,
    world: Any,
    baseline: Mapping[str, Any],
    body_path: str,
) -> dict[str, Any]:
    from omni.physx import get_physx_property_query_interface
    from omni.physx.bindings._physx import PhysxPropertyQueryMode, PhysxPropertyQueryResult
    from pxr import PhysicsSchemaTools, UsdPhysics, UsdUtils

    body = stage.GetPrimAtPath(body_path)
    if not body or not body.IsValid() or not body.HasAPI(UsdPhysics.RigidBodyAPI):
        raise RuntimeError(f"controller_static_screen_query_body_invalid:{body_path}")
    result: dict[str, Any] = {
        "body_path": body_path,
        "colliders": [],
        "callback_errors": [],
        "finished_callback_count": 0,
    }
    finished = {"value": False}

    def collider_callback(info: Any) -> None:
        if info.result != PhysxPropertyQueryResult.VALID:
            result["callback_errors"].append(f"collider:{info.result}")
            return
        path = str(PhysicsSchemaTools.intToSdfPath(info.path_id))
        local_min = _finite_vector(
            np, info.aabb_local_min, field="cooked_aabb_min", length=3
        )
        local_max = _finite_vector(
            np, info.aabb_local_max, field="cooked_aabb_max", length=3
        )
        if any(high < low for low, high in zip(local_min, local_max, strict=True)):
            result["callback_errors"].append(f"collider_aabb_order:{path}")
            return
        result["colliders"].append(
            {
                "path": path,
                "aabb_local_min_m": local_min,
                "aabb_local_max_m": local_max,
                "volume_m3": float(info.volume),
            }
        )

    def finished_callback() -> None:
        result["finished_callback_count"] += 1
        finished["value"] = True

    get_physx_property_query_interface().query_prim(
        stage_id=UsdUtils.StageCache.Get().Insert(stage).ToLongInt(),
        prim_id=PhysicsSchemaTools.sdfPathToInt(body.GetPath()),
        query_mode=PhysxPropertyQueryMode.QUERY_RIGID_BODY_WITH_COLLIDERS,
        rigid_body_fn=lambda _info: None,
        collider_fn=collider_callback,
        finished_fn=finished_callback,
        timeout_ms=60_000,
    )
    deadline = time.monotonic() + 60.0
    while not finished["value"] and time.monotonic() < deadline:
        _require_query_timeline_unchanged(
            world, timeline, baseline, context="cooked_query_before_update"
        )
        app.update()
        _require_query_timeline_unchanged(
            world, timeline, baseline, context="cooked_query_after_update"
        )
    if not finished["value"]:
        raise RuntimeError(f"controller_static_screen_cooked_query_timeout:{body_path}")
    _require_query_timeline_unchanged(
        world, timeline, baseline, context="cooked_query_complete"
    )
    colliders = result["colliders"]
    if (
        result["callback_errors"]
        or result["finished_callback_count"] != 1
        or not colliders
        or len({item["path"] for item in colliders}) != len(colliders)
    ):
        raise RuntimeError(f"controller_static_screen_cooked_query_invalid:{body_path}")
    result["colliders"] = sorted(colliders, key=lambda item: item["path"])
    return result


def _static_collision_paths(Usd: Any, UsdPhysics: Any, stage: Any, body_path: str) -> list[str]:
    body = stage.GetPrimAtPath(body_path)
    if not body or not body.IsValid() or body.HasAPI(UsdPhysics.RigidBodyAPI):
        raise RuntimeError(f"controller_static_screen_static_body_invalid:{body_path}")
    paths = []
    nested_rigid_bodies = []
    for prim in Usd.PrimRange(body):
        path = str(prim.GetPath())
        if path != body_path and prim.HasAPI(UsdPhysics.RigidBodyAPI):
            nested_rigid_bodies.append(path)
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
            if enabled is not False:
                paths.append(path)
    if nested_rigid_bodies or not paths:
        raise RuntimeError(f"controller_static_screen_static_inventory_invalid:{body_path}")
    return sorted(set(paths))


def _query_static_cooked_body(
    *,
    app: Any,
    np: Any,
    Sdf: Any,
    Usd: Any,
    UsdPhysics: Any,
    stage: Any,
    timeline: Any,
    world: Any,
    baseline: Mapping[str, Any],
    body_path: str,
) -> dict[str, Any]:
    collision_paths = _static_collision_paths(Usd, UsdPhysics, stage, body_path)
    session = stage.GetSessionLayer()
    if session is None:
        raise RuntimeError("controller_static_screen_static_query_session_missing")
    previous_target = stage.GetEditTarget()
    previous_sublayers = list(session.subLayerPaths)
    layer = Sdf.Layer.CreateAnonymous("controller_static_screen_static_query.usda")
    if layer is None:
        raise RuntimeError("controller_static_screen_static_query_layer_create_failed")
    raw = None
    try:
        session.subLayerPaths.insert(0, layer.identifier)
        stage.SetEditTarget(Usd.EditTarget(layer))
        body = stage.GetPrimAtPath(body_path)
        rigid = UsdPhysics.RigidBodyAPI.Apply(body)
        rigid.CreateRigidBodyEnabledAttr(False)
        app.update()
        _require_query_timeline_unchanged(
            world, timeline, baseline, context="static_query_activation"
        )
        raw = _query_cooked_rigid_body(
            app=app,
            np=np,
            stage=stage,
            timeline=timeline,
            world=world,
            baseline=baseline,
            body_path=body_path,
        )
    finally:
        stage.SetEditTarget(previous_target)
        session.subLayerPaths = previous_sublayers
        app.update()
    _require_query_timeline_unchanged(
        world, timeline, baseline, context="static_query_cleanup"
    )
    if (
        not isinstance(raw, Mapping)
        or _static_collision_paths(Usd, UsdPhysics, stage, body_path) != collision_paths
        or sorted(item["path"] for item in raw["colliders"]) != collision_paths
    ):
        raise RuntimeError(f"controller_static_screen_static_query_invalid:{body_path}")
    return dict(raw)


def _collect_cooked_catalog(
    *,
    app: Any,
    np: Any,
    Sdf: Any,
    Usd: Any,
    UsdPhysics: Any,
    stage: Any,
    timeline: Any,
    world: Any,
    baseline: Mapping[str, Any],
    required_paths: Sequence[str],
) -> dict[str, dict[str, Any]]:
    required = set(required_paths)
    owners: dict[str, list[str]] = {}
    static_paths = []
    for path in sorted(required):
        owner = _nearest_rigid_owner(UsdPhysics, stage, path)
        if owner is None:
            static_paths.append(path)
        else:
            owners.setdefault(owner, []).append(path)
    catalog: dict[str, dict[str, Any]] = {}
    for owner in sorted(owners):
        query = _query_cooked_rigid_body(
            app=app,
            np=np,
            stage=stage,
            timeline=timeline,
            world=world,
            baseline=baseline,
            body_path=owner,
        )
        for collider in query["colliders"]:
            path = collider["path"]
            if path in required:
                if path in catalog:
                    raise RuntimeError(f"controller_static_screen_collider_duplicate:{path}")
                catalog[path] = dict(collider)
    static_roots: dict[str, list[str]] = {}
    for path in static_paths:
        if path == TABLE_PATH:
            root = TABLE_ROOT_PATH
        elif path.startswith(f"{BEAKER1_WRAPPER_ROOT_PATH}/"):
            root = BEAKER1_WRAPPER_ROOT_PATH
        else:
            raise RuntimeError(
                f"controller_static_screen_unexpected_static_collider:{path}"
            )
        static_roots.setdefault(root, []).append(path)
    for body_path in sorted(static_roots):
        query = _query_static_cooked_body(
            app=app,
            np=np,
            Sdf=Sdf,
            Usd=Usd,
            UsdPhysics=UsdPhysics,
            stage=stage,
            timeline=timeline,
            world=world,
            baseline=baseline,
            body_path=body_path,
        )
        for collider in query["colliders"]:
            path = collider["path"]
            if path in required:
                if path in catalog:
                    raise RuntimeError(f"controller_static_screen_collider_duplicate:{path}")
                catalog[path] = dict(collider)
    if set(catalog) != required:
        missing = sorted(required - set(catalog))
        extra = sorted(set(catalog) - required)
        raise RuntimeError(
            f"controller_static_screen_cooked_catalog_coverage_invalid:{missing}:{extra}"
        )
    return {path: catalog[path] for path in sorted(catalog)}


def _cooked_world_box(
    *,
    np: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    collider: Mapping[str, Any],
    world_matrix: Any | None = None,
    tensor_transform: bool = False,
) -> dict[str, Any]:
    low = np.asarray(collider["aabb_local_min_m"], dtype=np.float64)
    high = np.asarray(collider["aabb_local_max_m"], dtype=np.float64)
    if (
        low.shape != (3,)
        or high.shape != (3,)
        or not np.isfinite(low).all()
        or not np.isfinite(high).all()
        or np.any(high < low)
    ):
        raise RuntimeError("controller_static_screen_cooked_aabb_invalid")
    corners = np.asarray(
        [[x, y, z, 1.0] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])],
        dtype=np.float64,
    )
    matrix = (
        _world_matrix(np, Usd, UsdGeom, stage, collider["path"])
        if world_matrix is None
        else np.asarray(world_matrix, dtype=np.float64)
    )
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise RuntimeError("controller_static_screen_world_transform_invalid")
    points = (corners @ matrix)[:, :3]
    world_min = points.min(axis=0)
    world_max = points.max(axis=0)
    if not np.isfinite(world_min).all() or not np.isfinite(world_max).all():
        raise RuntimeError("controller_static_screen_world_aabb_invalid")
    local_max = max(1.0, float(np.max(np.abs(low))), float(np.max(np.abs(high))))
    linear_norm = max(1.0, float(np.linalg.norm(matrix[:3, :3], ord=2)))
    local_error = 8.0 * float(np.finfo(np.float32).eps) * local_max
    transform_error = 128.0 * float(np.finfo(np.float64).eps) * max(
        1.0,
        float(np.max(np.abs(points))),
        float(np.max(np.abs(matrix))),
    )
    tensor_pose_error = (
        8.0
        * float(np.finfo(np.float32).eps)
        * max(1.0, float(np.max(np.abs(matrix))))
        * (1.0 + math.sqrt(3.0) * local_max)
        if tensor_transform
        else 0.0
    )
    outward_error = math.nextafter(
        math.sqrt(3.0) * local_error * linear_norm
        + transform_error
        + tensor_pose_error,
        math.inf,
    )
    return {
        "world_min_m": world_min - outward_error,
        "world_max_m": world_max + outward_error,
        "outward_error_m": outward_error,
    }


def _aabb_separation(
    np: Any, first: Mapping[str, Any], second: Mapping[str, Any]
) -> float:
    first_min = first["world_min_m"]
    first_max = first["world_max_m"]
    second_min = second["world_min_m"]
    second_max = second["world_max_m"]
    separation = np.maximum(
        np.maximum(first_min - second_max, second_min - first_max), 0.0
    )
    value = float(np.linalg.norm(separation))
    if not math.isfinite(value) or value < 0.0:
        raise RuntimeError("controller_static_screen_aabb_separation_invalid")
    return value


def _screen_pair_results(
    *,
    np: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    catalog: Mapping[str, Mapping[str, Any]],
    screen_scope: Mapping[str, Sequence[Sequence[str]]],
    numerical_margin_m: float,
    robot_collider_world_matrices: Mapping[str, Any],
) -> list[dict[str, Any]]:
    paths = {
        path
        for field in ("blocking_pairs", "allowed_source_shell_pairs")
        for pair in screen_scope[field]
        for path in pair
    }
    if paths != set(catalog):
        raise RuntimeError("controller_static_screen_catalog_scope_mismatch")
    boxes = {
        path: _cooked_world_box(
            np=np,
            Usd=Usd,
            UsdGeom=UsdGeom,
            stage=stage,
            collider=catalog[path],
            world_matrix=robot_collider_world_matrices.get(path),
            tensor_transform=path in robot_collider_world_matrices,
        )
        for path in sorted(paths)
    }
    results = []
    for classification, field in (
        ("BLOCKING", "blocking_pairs"),
        ("ALLOWED_SOURCE_SHELL_FINGER", "allowed_source_shell_pairs"),
    ):
        for raw_pair in screen_scope[field]:
            pair = list(raw_pair)
            separation = _aabb_separation(np, boxes[pair[0]], boxes[pair[1]])
            results.append(
                {
                    "pair": pair,
                    "classification": classification,
                    "status": (
                        "CLEAR"
                        if separation > numerical_margin_m
                        else "POTENTIAL_OVERLAP_OR_MARGIN"
                    ),
                    "lower_bound_m": separation,
                }
            )
    return results


def _action_values(np: Any, value: Any, *, field: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        raise RuntimeError(f"controller_static_screen_action_{field}_invalid")
    array = np.asarray(value, dtype=object)
    if array.ndim != 1:
        raise RuntimeError(f"controller_static_screen_action_{field}_invalid")
    return array.tolist()


def _explicit_position_action(
    np: Any, action: Any, *, dof_count: int
) -> tuple[dict[str, Any], list[float] | None]:
    """Project native RMP output to the position-only static-screen command."""
    if action is None:
        raise RuntimeError("controller_static_screen_action_missing")
    if getattr(action, "joint_efforts", None) is not None:
        raise RuntimeError("controller_static_screen_nonposition_action")
    positions = _action_values(
        np, getattr(action, "joint_positions", None), field="positions"
    )
    raw_velocity = getattr(action, "joint_velocities", None)
    discarded_velocity = None
    if raw_velocity is not None:
        values = _action_values(np, raw_velocity, field="velocities")
        if len(values) not in {7, dof_count}:
            raise RuntimeError("controller_static_screen_action_velocity_invalid")
        discarded_velocity = []
        for value in values:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.integer, np.floating))
                or not math.isfinite(float(value))
            ):
                raise RuntimeError("controller_static_screen_action_velocity_invalid")
            discarded_velocity.append(float(value))
    raw_indices = getattr(action, "joint_indices", None)
    if not positions:
        if raw_indices is not None or discarded_velocity is not None:
            raise RuntimeError("controller_static_screen_hold_indices_invalid")
        return (
            {
                "joint_positions": None,
                "joint_indices": None,
                "joint_velocities": None,
                "joint_efforts": None,
            },
            None,
        )
    if raw_indices is None:
        if len(positions) == dof_count:
            indices = list(range(dof_count))
        elif len(positions) == 7 and dof_count == 9:
            indices = list(range(7))
        else:
            raise RuntimeError("controller_static_screen_action_indices_ambiguous")
    else:
        raw = _action_values(np, raw_indices, field="indices")
        if len(raw) != len(positions):
            raise RuntimeError("controller_static_screen_action_indices_invalid")
        indices = []
        for value in raw:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float, np.integer, np.floating))
                or not math.isfinite(float(value))
                or int(value) != float(value)
            ):
                raise RuntimeError("controller_static_screen_action_indices_invalid")
            indices.append(int(value))

    explicit_positions = []
    explicit_indices = []
    allow_sparse_full_width = len(positions) == dof_count and raw_indices is None
    for position, index in zip(positions, indices, strict=True):
        if position is None:
            if allow_sparse_full_width:
                continue
            raise RuntimeError("controller_static_screen_action_position_invalid")
        if isinstance(position, bool) or not isinstance(
            position, (int, float, np.integer, np.floating)
        ):
            raise RuntimeError("controller_static_screen_action_position_invalid")
        numeric = float(position)
        if math.isinf(numeric):
            raise RuntimeError("controller_static_screen_action_position_invalid")
        if math.isnan(numeric):
            if allow_sparse_full_width:
                continue
            raise RuntimeError("controller_static_screen_action_position_invalid")
        explicit_positions.append(numeric)
        explicit_indices.append(index)
    if not explicit_positions:
        return (
            {
                "joint_positions": None,
                "joint_indices": None,
                "joint_velocities": None,
                "joint_efforts": None,
            },
            discarded_velocity,
        )
    return (
        {
            "joint_positions": explicit_positions,
            "joint_indices": explicit_indices,
            "joint_velocities": None,
            "joint_efforts": None,
        },
        discarded_velocity,
    )


def _read_joint_positions(np: Any, robot: Any) -> list[float]:
    positions = _finite_vector(
        np, robot.get_joint_positions(), field="joint_readback"
    )
    if len(positions) != 9:
        raise RuntimeError("controller_static_screen_joint_dof_count_invalid")
    return positions


def _joint_position_limits(np: Any, robot: Any) -> tuple[Any, Any]:
    properties = robot.dof_properties
    names = getattr(getattr(properties, "dtype", None), "names", None)
    if names is None or not {"lower", "upper"} <= set(names):
        raise RuntimeError("controller_static_screen_joint_limits_unavailable")
    lower = np.asarray(properties["lower"], dtype=np.float64)
    upper = np.asarray(properties["upper"], dtype=np.float64)
    if (
        lower.shape != (9,)
        or upper.shape != (9,)
        or not np.isfinite(lower).all()
        or not np.isfinite(upper).all()
        or np.any(lower >= upper)
    ):
        raise RuntimeError("controller_static_screen_joint_limits_invalid")
    return lower, upper


def _joint_limit_violations(
    np: Any, target: Any, lower: Any, upper: Any
) -> list[dict[str, float | int]]:
    invalid_indices = np.flatnonzero(
        (target < lower - JOINT_READBACK_ATOL) | (target > upper + JOINT_READBACK_ATOL)
    )
    return [
        {
            "index": int(index),
            "target": float(target[index]),
            "lower": float(lower[index]),
            "upper": float(upper[index]),
        }
        for index in invalid_indices.tolist()
    ]


def _materialize_configuration(
    *,
    np: Any,
    Rotation: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    robot: Any,
    robot_kinematics: Mapping[str, Any],
    source_matrix_before: Any,
    world: Any,
    timeline: Any,
    baseline: Mapping[str, Any],
    target_positions: Sequence[float],
    joint_lower_limits: Any,
    joint_upper_limits: Any,
    is_hold: bool,
    joint_readback_atol: float = JOINT_READBACK_ATOL,
) -> tuple[list[float], Any, dict[str, Any]]:
    if (
        isinstance(joint_readback_atol, bool)
        or not isinstance(joint_readback_atol, (int, float))
        or not math.isfinite(float(joint_readback_atol))
        or not 0.0 < float(joint_readback_atol) <= 1.0e-5
    ):
        raise RuntimeError("controller_static_screen_joint_readback_atol_invalid")
    before = _read_joint_positions(np, robot)
    before_matrices = _robot_collider_world_matrices(np, Rotation, robot_kinematics)
    if not is_hold:
        target = np.asarray(target_positions, dtype=np.float64)
        if target.shape != (9,):
            raise RuntimeError("controller_static_screen_joint_target_shape_invalid")
        violations = _joint_limit_violations(
            np, target, joint_lower_limits, joint_upper_limits
        )
        if violations:
            raise _JointLimitViolation(violations)
        robot.set_joint_positions(target)
        simulation_view = getattr(world, "physics_sim_view", None)
        if simulation_view is not robot_kinematics.get("simulation_view"):
            raise RuntimeError("controller_static_screen_kinematic_view_mismatch")
        update_kinematic = getattr(
            simulation_view, "update_articulations_kinematic", None
        )
        if not callable(update_kinematic):
            raise RuntimeError("controller_static_screen_kinematic_update_unavailable")
        update_kinematic()
        _require_paused_unchanged(
            world,
            timeline,
            baseline,
            context="joint_materialization_kinematic_update",
        )
    readback = _read_joint_positions(np, robot)
    expected = np.asarray(target_positions if not is_hold else before, dtype=np.float64)
    if not np.allclose(
        np.asarray(readback, dtype=np.float64),
        expected,
        rtol=0.0,
        atol=float(joint_readback_atol),
    ):
        raise RuntimeError("controller_static_screen_joint_readback_mismatch")
    _require_paused_unchanged(world, timeline, baseline, context="joint_materialization")
    source_matrix_after = _world_matrix(np, Usd, UsdGeom, stage, SOURCE_ROOT_PATH)
    if not np.allclose(
        source_matrix_after,
        source_matrix_before,
        rtol=0.0,
        atol=SOURCE_STABILITY_ATOL,
    ):
        raise RuntimeError("controller_static_screen_source_transform_changed")
    changed_joint = not np.allclose(
        np.asarray(before, dtype=np.float64), expected, rtol=0.0, atol=JOINT_READBACK_ATOL
    )
    if changed_joint:
        after_matrices = _robot_collider_world_matrices(np, Rotation, robot_kinematics)
        if not any(
            not np.allclose(
                before_matrices[path],
                after_matrices[path],
                rtol=0.0,
                atol=MATRIX_CHANGE_ATOL,
            )
            for path in before_matrices
        ):
            raise RuntimeError("controller_static_screen_kinematic_refresh_unobserved")
    else:
        after_matrices = before_matrices
    return readback, source_matrix_after, after_matrices


def _native_pick_treatment(
    contract: Mapping[str, Any], np: Any
) -> tuple[list[float], Any, float, float, dict[str, float]]:
    treatment = contract.get("native_pick_treatment")
    if not isinstance(treatment, Mapping):
        raise RuntimeError("controller_static_screen_pick_treatment_missing")
    event_durations = treatment.get("settle_events_dt")
    orientation = np.asarray(treatment.get("target_orientation_wxyz"), dtype=np.float64)
    z_offset = treatment.get("pick_z_offset_m")
    x_offset = treatment.get("pick_x_offset_m")
    forward_parameters = contract.get("native_pick_forward_parameters")
    if (
        not isinstance(event_durations, list)
        or len(event_durations) != 7
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
            for value in event_durations
        )
        or orientation.shape != (4,)
        or not np.isfinite(orientation).all()
        or float(np.linalg.norm(orientation)) <= 1.0e-12
        or isinstance(z_offset, bool)
        or not isinstance(z_offset, (int, float))
        or not math.isfinite(float(z_offset))
        or not 0.0 <= float(z_offset) <= 0.10
        or isinstance(x_offset, bool)
        or not isinstance(x_offset, (int, float))
        or not math.isfinite(float(x_offset))
        or abs(float(x_offset)) > 0.10
        or not isinstance(forward_parameters, Mapping)
        or set(forward_parameters) != {"pre_offset_x", "pre_offset_z", "after_offset_z"}
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
            for value in forward_parameters.values()
        )
    ):
        raise RuntimeError("controller_static_screen_pick_treatment_invalid")
    return (
        [float(value) for value in event_durations],
        orientation / float(np.linalg.norm(orientation)),
        float(z_offset),
        float(x_offset),
        {name: float(forward_parameters[name]) for name in sorted(forward_parameters)},
    )


def _iter_trace(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rb") as stream:
        for line in stream:
            if not line.endswith(b"\n") or b"\r" in line:
                raise RuntimeError("controller_static_screen_trace_encoding_invalid")
            try:
                value = json.loads(line[:-1].decode("ascii"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("controller_static_screen_trace_encoding_invalid") from exc
            if not isinstance(value, Mapping) or _canonical_json_bytes(value) != line[:-1]:
                raise RuntimeError("controller_static_screen_trace_canonical_invalid")
            yield dict(value)


def _write_jsonl_record(stream: Any, digest: Any, value: Mapping[str, Any]) -> None:
    payload = _canonical_json_bytes(dict(value))
    stream.write(payload + b"\n")
    digest.update(payload + b"\n")


def _write_canonical_create_only(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical_json_bytes(dict(value))
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _json_safe_value(np: Any, value: Any, *, field: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, bool
    ):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise RuntimeError(f"controller_static_screen_{field}_invalid")
        return int(value) if isinstance(value, (int, np.integer)) else numeric
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise RuntimeError(f"controller_static_screen_{field}_invalid")
        return {
            key: _json_safe_value(np, value[key], field=field)
            for key in sorted(value)
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(np, item, field=field) for item in value]
    raise RuntimeError(f"controller_static_screen_{field}_invalid")


def _raw_action_payload(np: Any, action: Any, *, field: str) -> dict[str, Any]:
    if action is None:
        raise RuntimeError(f"controller_static_screen_{field}_missing")

    def channel(value: Any, *, allow_sparse: bool) -> list[float | None] | None:
        if value is None:
            return None
        normalized = []
        for item in _action_values(np, value, field=field):
            if item is None and allow_sparse:
                normalized.append(None)
                continue
            if (
                isinstance(item, bool)
                or not isinstance(item, (int, float, np.integer, np.floating))
                or not math.isfinite(float(item))
            ):
                raise RuntimeError(f"controller_static_screen_{field}_invalid")
            normalized.append(float(item))
        return normalized

    raw_indices = getattr(action, "joint_indices", None)
    if raw_indices is None:
        indices = None
    else:
        indices = []
        for item in _action_values(np, raw_indices, field=f"{field}_indices"):
            if (
                isinstance(item, bool)
                or not isinstance(item, (int, float, np.integer, np.floating))
                or not math.isfinite(float(item))
                or int(item) != float(item)
            ):
                raise RuntimeError(f"controller_static_screen_{field}_invalid")
            indices.append(int(item))
    return {
        "joint_positions": channel(
            getattr(action, "joint_positions", None), allow_sparse=True
        ),
        "joint_velocities": channel(
            getattr(action, "joint_velocities", None), allow_sparse=False
        ),
        "joint_efforts": channel(
            getattr(action, "joint_efforts", None), allow_sparse=False
        ),
        "joint_indices": indices,
    }


def _native_pick_object_geometry(np: Any, ObjectUtils: Any, stage: Any) -> tuple[Any, Any]:
    object_utils = ObjectUtils.get_instance(stage)
    object_position = np.asarray(
        object_utils.get_geometry_center(object_path=SOURCE_ROOT_PATH), dtype=np.float64
    )
    object_size = np.asarray(
        object_utils.get_object_size(object_path=SOURCE_ROOT_PATH), dtype=np.float64
    )
    if (
        object_position.shape != (3,)
        or object_size.shape != (3,)
        or not np.isfinite(object_position).all()
        or not np.isfinite(object_size).all()
    ):
        raise RuntimeError("controller_static_screen_object_geometry_invalid")
    return object_position, object_size


def _rmp_policy_file_hashes(config: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    records = {}
    for field in ("robot_description_path", "urdf_path", "rmpflow_config_path"):
        value = config.get(field)
        if not isinstance(value, str):
            raise RuntimeError("controller_static_screen_rmp_policy_path_invalid")
        path = Path(value).resolve()
        if not path.is_file():
            raise RuntimeError("controller_static_screen_rmp_policy_path_invalid")
        records[field] = {"path": str(path), "sha256": _sha256_file(path)}
    return records


def _active_rmp_joint_metadata(
    np: Any, rmp: Any, dof_names: Sequence[str]
) -> tuple[list[str], list[int]]:
    subset = rmp.articulation_rmp.get_active_joints_subset()
    names = list(getattr(subset, "joint_names", ()) or ())
    raw_indices = getattr(subset, "joint_indices", None)
    if raw_indices is None:
        raise RuntimeError("controller_static_screen_rmp_active_joint_mapping_invalid")
    indices = _action_values(np, raw_indices, field="rmp_active_joint_indices")
    if (
        len(names) != 7
        or len(indices) != len(names)
        or any(not isinstance(name, str) or not name for name in names)
    ):
        raise RuntimeError("controller_static_screen_rmp_active_joint_mapping_invalid")
    normalized_indices = []
    for value in indices:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float, np.integer, np.floating))
            or not math.isfinite(float(value))
            or int(value) != float(value)
        ):
            raise RuntimeError("controller_static_screen_rmp_active_joint_mapping_invalid")
        normalized_indices.append(int(value))
    if (
        len(set(normalized_indices)) != len(normalized_indices)
        or any(index < 0 or index >= len(dof_names) for index in normalized_indices)
        or any(
            dof_names[index] != name
            for index, name in zip(normalized_indices, names, strict=True)
        )
    ):
        raise RuntimeError("controller_static_screen_rmp_active_joint_mapping_invalid")
    return names, normalized_indices


class _RecordingCspaceController:
    def __init__(self, np: Any, controller: Any) -> None:
        self._np = np
        self._controller = controller
        self.forward_calls: list[dict[str, Any]] = []

    def forward(self, **kwargs: Any) -> Any:
        expected = {"target_end_effector_position", "target_end_effector_orientation"}
        if set(kwargs) != expected:
            raise RuntimeError("controller_static_screen_rmp_forward_arguments_invalid")
        self.forward_calls.append(
            {
                "target_end_effector_position": self._np.asarray(
                    kwargs["target_end_effector_position"], dtype=self._np.float64
                ).copy(),
                "target_end_effector_orientation": self._np.asarray(
                    kwargs["target_end_effector_orientation"], dtype=self._np.float64
                ).copy(),
            }
        )
        return self._controller.forward(**kwargs)

    def reset(self) -> None:
        self._controller.reset()


def _shadow_rmp_targets(
    *,
    np: Any,
    RmpFlow: Any,
    policy_config: Mapping[str, Any],
    robot_base_position: Any,
    robot_base_orientation: Any,
    target_position: Any,
    target_orientation: Any,
    active_positions: Sequence[float],
    active_velocities: Sequence[float],
    watched_positions: Sequence[float],
    watched_velocities: Sequence[float],
    control_dt_s: float,
) -> tuple[list[float], list[float]]:
    shadow = RmpFlow(**dict(policy_config))
    shadow.set_ignore_state_updates(False)
    shadow.set_robot_base_pose(
        np.asarray(robot_base_position, dtype=np.float64).copy(),
        np.asarray(robot_base_orientation, dtype=np.float64).copy(),
    )
    shadow.set_end_effector_target(
        np.asarray(target_position, dtype=np.float64).copy(),
        np.asarray(target_orientation, dtype=np.float64).copy(),
    )
    shadow.update_world()
    position_targets, velocity_targets = shadow.compute_joint_targets(
        np.asarray(active_positions, dtype=np.float64).copy(),
        np.asarray(active_velocities, dtype=np.float64).copy(),
        np.asarray(watched_positions, dtype=np.float64).copy(),
        np.asarray(watched_velocities, dtype=np.float64).copy(),
        control_dt_s,
    )
    return (
        _finite_vector(
            np, position_targets, field="shadow_rmp_position_targets", length=7
        ),
        _finite_vector(
            np, velocity_targets, field="shadow_rmp_velocity_targets", length=7
        ),
    )


def _rmp_qdot_counterfactual(
    *,
    np: Any,
    RmpFlow: Any,
    rmp: Any,
    policy_config: Mapping[str, Any],
    baseline_positions: Sequence[float],
    baseline_velocities: Sequence[float],
    active_joint_indices: Sequence[int],
    robot_base_position: Any,
    robot_base_orientation: Any,
    target_position: Any,
    target_orientation: Any,
    capture: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    watched_subset = rmp.articulation_rmp.get_watched_joints_subset()
    watched_joint_names = list(getattr(watched_subset, "joint_names", ()) or ())
    if watched_joint_names:
        watched_positions = _finite_vector(
            np,
            watched_subset.get_joint_positions(),
            field="watched_joint_positions",
            length=len(watched_joint_names),
        )
        watched_velocities = _finite_vector(
            np,
            watched_subset.get_joint_velocities(),
            field="watched_joint_velocities",
            length=len(watched_joint_names),
        )
    else:
        watched_positions = []
        watched_velocities = []
    active_positions = [baseline_positions[index] for index in active_joint_indices]
    active_velocities = [baseline_velocities[index] for index in active_joint_indices]
    actual_positions, actual_velocities = _shadow_rmp_targets(
        np=np,
        RmpFlow=RmpFlow,
        policy_config=policy_config,
        robot_base_position=robot_base_position,
        robot_base_orientation=robot_base_orientation,
        target_position=target_position,
        target_orientation=target_orientation,
        active_positions=active_positions,
        active_velocities=active_velocities,
        watched_positions=watched_positions,
        watched_velocities=watched_velocities,
        control_dt_s=DEFAULT_CONTROL_DT_S,
    )
    zero_positions, zero_velocities = _shadow_rmp_targets(
        np=np,
        RmpFlow=RmpFlow,
        policy_config=policy_config,
        robot_base_position=robot_base_position,
        robot_base_orientation=robot_base_orientation,
        target_position=target_position,
        target_orientation=target_orientation,
        active_positions=active_positions,
        active_velocities=[0.0] * len(active_positions),
        watched_positions=watched_positions,
        watched_velocities=watched_velocities,
        control_dt_s=DEFAULT_CONTROL_DT_S,
    )
    replay = {
        "schema_version": 1,
        "authority": "rmp_qdot_counterfactual_v1",
        "control_dt_s": DEFAULT_CONTROL_DT_S,
        "active_joint_positions": active_positions,
        "active_joint_velocities": active_velocities,
        "watched_joint_names": watched_joint_names,
        "watched_joint_positions": watched_positions,
        "watched_joint_velocities": watched_velocities,
        "actual_qdot_branch": {
            "input_joint_velocities": active_velocities,
            "position_targets": actual_positions,
            "velocity_targets": actual_velocities,
        },
        "zero_qdot_branch": {
            "input_joint_velocities": [0.0] * len(active_positions),
            "position_targets": zero_positions,
            "velocity_targets": zero_velocities,
        },
    }
    return replay, screen.evaluate_rmp_qdot_counterfactual(capture, replay)


def _controller_semantics_audit(
    *,
    np: Any,
    Rotation: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    world: Any,
    timeline: Any,
    baseline: Mapping[str, Any],
    robot: Any,
    robot_kinematics: Mapping[str, Any],
    joint_lower_limits: Any,
    joint_upper_limits: Any,
    PickController: Any,
    RMPFlowController: Any,
    RmpFlow: Any,
    ObjectUtils: Any,
    get_stage_units: Any,
    expected_stage_units_in_meters: float,
    contract: Mapping[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    """Capture opening and event-0 native actions without applying either action."""
    event_durations, orientation, z_offset, x_offset, forward_parameters = _native_pick_treatment(
        contract, np
    )
    object_position, object_size = _native_pick_object_geometry(np, ObjectUtils, stage)
    stage_units = float(get_stage_units())
    if (
        not math.isfinite(stage_units)
        or stage_units <= 0.0
        or not math.isclose(
            stage_units,
            expected_stage_units_in_meters,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    ):
        raise RuntimeError("controller_static_screen_stage_units_invalid")
    source_matrix_before = _world_matrix(np, Usd, UsdGeom, stage, SOURCE_ROOT_PATH)
    timeline_before = _require_paused_unchanged(
        world, timeline, baseline, context="controller_semantics_before"
    )
    baseline_positions = _read_joint_positions(np, robot)
    baseline_velocities = _finite_vector(
        np, robot.get_joint_velocities(), field="joint_velocity_readback", length=9
    )
    dof_names = list(getattr(robot, "dof_names", ()) or ())
    if (
        len(dof_names) != 9
        or len(dof_names) != len(set(dof_names))
        or any(not isinstance(name, str) or not name for name in dof_names)
    ):
        raise RuntimeError("controller_static_screen_dof_names_invalid")
    rmp = RMPFlowController(
        name="controller_semantics_native_rmp",
        robot_articulation=robot,
        physics_dt=DEFAULT_CONTROL_DT_S,
    )
    recording_rmp = _RecordingCspaceController(np, rmp)
    pick = PickController(
        name="controller_semantics_native_pick",
        cspace_controller=recording_rmp,
        events_dt=event_durations,
    )
    pick.reset()
    active_joint_names, active_joint_indices = _active_rmp_joint_metadata(
        np, rmp, dof_names
    )
    policy_config = _json_safe_value(
        np, rmp.rmp_flow_config, field="rmp_policy_config"
    )
    if not isinstance(policy_config, Mapping):
        raise RuntimeError("controller_static_screen_rmp_policy_config_invalid")
    policy_file_hashes = _rmp_policy_file_hashes(policy_config)
    robot_base_position, robot_base_orientation = robot.get_world_pose()
    rmp_policy_position, _ = rmp.get_end_effector_pose_world()
    rmp_policy_orientation = rmp.get_end_effector_orientation_wxyz()
    tool_center_position = _robot_tool_center_position(np, Rotation, robot_kinematics)
    forward_kwargs = {
        "picking_position": object_position.copy(),
        "current_joint_positions": np.asarray(baseline_positions, dtype=np.float64),
        "object_name": "beaker2",
        "object_size": object_size.copy(),
        "gripper_control": type(
            "NoAttachmentGripper",
            (),
            {"add_object_to_gripper": staticmethod(lambda *_args, **_kwargs: None)},
        )(),
        "gripper_position": tool_center_position.copy(),
        "end_effector_orientation": orientation.copy(),
        "pre_offset_x": forward_parameters["pre_offset_x"],
        "pre_offset_z": forward_parameters["pre_offset_z"],
        "after_offset_z": forward_parameters["after_offset_z"],
        "pick_z_offset_m": z_offset,
        "pick_x_offset_m": x_offset,
    }
    opening_event_before = int(pick._event)
    opening_action = pick.forward(**forward_kwargs)
    opening = {
        "event_before": opening_event_before,
        "event_after": int(pick._event),
        "last_emitted_event": pick._last_emitted_event,
        "raw_action": _raw_action_payload(np, opening_action, field="opening_action"),
    }
    event0_before = int(pick._event)
    event0_action = pick.forward(**forward_kwargs)
    event0 = {
        "event_before": event0_before,
        "event_after": int(pick._event),
        "last_emitted_event": pick._last_emitted_event,
        "raw_action": _raw_action_payload(np, event0_action, field="event0_action"),
    }
    if len(recording_rmp.forward_calls) != 1:
        raise RuntimeError("controller_static_screen_rmp_forward_count_invalid")
    target_call = recording_rmp.forward_calls[0]
    source_matrix_after = _world_matrix(np, Usd, UsdGeom, stage, SOURCE_ROOT_PATH)
    timeline_after = _require_paused_unchanged(
        world, timeline, baseline, context="controller_semantics_after"
    )
    post_audit_positions = _read_joint_positions(np, robot)
    post_audit_velocities = _finite_vector(
        np, robot.get_joint_velocities(), field="post_audit_joint_velocities", length=9
    )
    if (
        not np.allclose(
            np.asarray(post_audit_positions, dtype=np.float64),
            np.asarray(baseline_positions, dtype=np.float64),
            rtol=0.0,
            atol=JOINT_READBACK_ATOL,
        )
        or not np.allclose(
            np.asarray(post_audit_velocities, dtype=np.float64),
            np.asarray(baseline_velocities, dtype=np.float64),
            rtol=0.0,
            atol=JOINT_READBACK_ATOL,
        )
    ):
        raise RuntimeError("controller_static_screen_semantics_robot_state_changed")
    capture = {
        "schema_version": 1,
        "authority": "native_pick_action_semantics_v1",
        "baseline": {
            "joint_positions": baseline_positions,
            "joint_velocities": baseline_velocities,
            "joint_lower_limits": _finite_vector(
                np, joint_lower_limits, field="joint_lower_limits", length=9
            ),
            "joint_upper_limits": _finite_vector(
                np, joint_upper_limits, field="joint_upper_limits", length=9
            ),
            "dof_names": dof_names,
            "stage_units_in_meters": stage_units,
            "expected_stage_units_in_meters": expected_stage_units_in_meters,
        },
        "post_audit": {
            "joint_positions": post_audit_positions,
            "joint_velocities": post_audit_velocities,
        },
        "target": {
            "source_center_stage": _finite_vector(
                np, object_position, field="object_position", length=3
            ),
            "source_size_stage": _finite_vector(
                np, object_size, field="object_size", length=3
            ),
            "approach_direction": _finite_vector(
                np,
                pick._calculate_approach_direction(object_position.copy()),
                field="approach_direction",
                length=3,
            ),
            "event0_target_position_stage": _finite_vector(
                np,
                target_call["target_end_effector_position"],
                field="event0_target_position",
                length=3,
            ),
            "event0_target_orientation_wxyz": _finite_vector(
                np,
                target_call["target_end_effector_orientation"],
                field="event0_target_orientation",
                length=4,
            ),
            "pre_offset_x_m": forward_parameters["pre_offset_x"],
            "pre_offset_z_m": forward_parameters["pre_offset_z"],
            "after_offset_z_m": forward_parameters["after_offset_z"],
            "pick_z_offset_m": z_offset,
            "pick_x_offset_m": x_offset,
            "rmp_end_effector_frame_name": policy_config.get(
                "end_effector_frame_name"
            ),
            "pick_progress_frame_name": "tool_center",
            "rmp_forward_call_count": len(recording_rmp.forward_calls),
        },
        "rmp": {
            "physics_dt_s": rmp.physics_dt,
            "active_joint_names": active_joint_names,
            "active_joint_indices": active_joint_indices,
            "policy_config": policy_config,
            "policy_file_hashes": policy_file_hashes,
        },
        "frame_observations": {
            "robot_base_position_world": _finite_vector(
                np, robot_base_position, field="robot_base_position", length=3
            ),
            "robot_base_orientation_wxyz": _finite_vector(
                np, robot_base_orientation, field="robot_base_orientation", length=4
            ),
            "rmp_policy_end_effector_position": _finite_vector(
                np, rmp_policy_position, field="rmp_policy_position", length=3
            ),
            "rmp_policy_end_effector_orientation_wxyz": _finite_vector(
                np, rmp_policy_orientation, field="rmp_policy_orientation", length=4
            ),
            "tool_center_position_world": _finite_vector(
                np, tool_center_position, field="tool_center_position", length=3
            ),
        },
        "source_world_matrix_row_major": _finite_vector(
            np, source_matrix_before.reshape(-1), field="source_matrix", length=16
        ),
        "source_world_matrix_after_row_major": _finite_vector(
            np, source_matrix_after.reshape(-1), field="source_matrix_after", length=16
        ),
        "opening": opening,
        "event0": event0,
        "timeline_before": timeline_before,
        "timeline_after": timeline_after,
    }
    evaluation = screen.evaluate_native_pick_semantics(capture)
    qdot_counterfactual = None
    qdot_counterfactual_evaluation = None
    if evaluation.get("decision") == "RAW_NATIVE_POSITION_TARGET_OUT_OF_LIMIT":
        qdot_counterfactual, _ = _rmp_qdot_counterfactual(
            np=np,
            RmpFlow=RmpFlow,
            rmp=rmp,
            policy_config=policy_config,
            baseline_positions=baseline_positions,
            baseline_velocities=baseline_velocities,
            active_joint_indices=active_joint_indices,
            robot_base_position=robot_base_position,
            robot_base_orientation=robot_base_orientation,
            target_position=target_call["target_end_effector_position"],
            target_orientation=target_call["target_end_effector_orientation"],
            capture=capture,
        )
        if _rmp_policy_file_hashes(policy_config) != policy_file_hashes:
            raise RuntimeError("controller_static_screen_rmp_policy_changed_during_audit")
        final_source_matrix = _world_matrix(np, Usd, UsdGeom, stage, SOURCE_ROOT_PATH)
        final_timeline = _require_paused_unchanged(
            world, timeline, baseline, context="rmp_qdot_counterfactual_after"
        )
        final_positions = _read_joint_positions(np, robot)
        final_velocities = _finite_vector(
            np, robot.get_joint_velocities(), field="final_joint_velocities", length=9
        )
        if (
            not np.allclose(
                np.asarray(final_positions, dtype=np.float64),
                np.asarray(baseline_positions, dtype=np.float64),
                rtol=0.0,
                atol=JOINT_READBACK_ATOL,
            )
            or not np.allclose(
                np.asarray(final_velocities, dtype=np.float64),
                np.asarray(baseline_velocities, dtype=np.float64),
                rtol=0.0,
                atol=JOINT_READBACK_ATOL,
            )
        ):
            raise RuntimeError("controller_static_screen_counterfactual_robot_state_changed")
        capture["post_audit"] = {
            "joint_positions": final_positions,
            "joint_velocities": final_velocities,
        }
        capture["source_world_matrix_after_row_major"] = _finite_vector(
            np,
            final_source_matrix.reshape(-1),
            field="final_source_matrix",
            length=16,
        )
        capture["timeline_after"] = final_timeline
        evaluation = screen.evaluate_native_pick_semantics(capture)
        qdot_counterfactual_evaluation = screen.evaluate_rmp_qdot_counterfactual(
            capture, qdot_counterfactual
        )
    artifact_path = out_dir / SEMANTICS_ARTIFACT_NAME
    artifact = {
        "schema_version": 1,
        "manifest_type": "nonformal_native_pick_controller_semantics_v1",
        "capture": capture,
        "evaluation": evaluation,
    }
    if qdot_counterfactual is not None:
        artifact["schema_version"] = 2
        artifact["manifest_type"] = "nonformal_native_pick_controller_semantics_v2"
        artifact["qdot_counterfactual"] = qdot_counterfactual
        artifact["qdot_counterfactual_evaluation"] = qdot_counterfactual_evaluation
    _write_canonical_create_only(
        artifact_path,
        artifact,
    )
    return {
        "artifact": {"path": artifact_path.name, "sha256": _sha256_file(artifact_path)},
        "evaluation": evaluation,
        "capture": capture,
        "qdot_counterfactual_evaluation": qdot_counterfactual_evaluation,
    }


def _require_semantics_prefix_match(
    *,
    np: Any,
    capture: Mapping[str, Any],
    action_ordinal: int,
    event_before: int,
    event_after: int,
    last_emitted_event: int | None,
    action: Any,
    rmp_forward_calls: Sequence[Mapping[str, Any]],
) -> None:
    slot = "opening" if action_ordinal == 0 else "event0" if action_ordinal == 1 else None
    if slot is None:
        return
    expected = capture.get(slot)
    if (
        not isinstance(expected, Mapping)
        or expected.get("event_before") != event_before
        or expected.get("event_after") != event_after
        or expected.get("last_emitted_event") != last_emitted_event
        or expected.get("raw_action") != _raw_action_payload(np, action, field="screen_action")
    ):
        raise RuntimeError("controller_static_screen_semantics_action_drift")
    if action_ordinal != 1:
        return
    target = capture.get("target")
    if (
        not isinstance(target, Mapping)
        or len(rmp_forward_calls) != 1
        or not np.allclose(
            np.asarray(
                rmp_forward_calls[0].get("target_end_effector_position"),
                dtype=np.float64,
            ),
            np.asarray(target.get("event0_target_position_stage"), dtype=np.float64),
            rtol=0.0,
            atol=1.0e-12,
        )
        or not np.allclose(
            np.asarray(
                rmp_forward_calls[0].get("target_end_effector_orientation"),
                dtype=np.float64,
            ),
            np.asarray(target.get("event0_target_orientation_wxyz"), dtype=np.float64),
            rtol=0.0,
            atol=1.0e-12,
        )
    ):
        raise RuntimeError("controller_static_screen_semantics_target_drift")


def _controller_screen(
    *,
    np: Any,
    Rotation: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    world: Any,
    timeline: Any,
    baseline: Mapping[str, Any],
    robot: Any,
    robot_kinematics: Mapping[str, Any],
    joint_lower_limits: Any,
    joint_upper_limits: Any,
    PickController: Any,
    RMPFlowController: Any,
    ObjectUtils: Any,
    catalog: Mapping[str, Mapping[str, Any]],
    full_scope: Mapping[str, Any],
    contract: Mapping[str, Any],
    semantics_capture: Mapping[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    event_durations, orientation, z_offset, x_offset, forward_parameters = _native_pick_treatment(
        contract, np
    )
    object_utils = ObjectUtils.get_instance(stage)
    object_position = np.asarray(
        object_utils.get_geometry_center(object_path=SOURCE_ROOT_PATH), dtype=np.float64
    )
    object_size = np.asarray(
        object_utils.get_object_size(object_path=SOURCE_ROOT_PATH), dtype=np.float64
    )
    if (
        object_position.shape != (3,)
        or object_size.shape != (3,)
        or not np.isfinite(object_position).all()
        or not np.isfinite(object_size).all()
    ):
        raise RuntimeError("controller_static_screen_object_geometry_invalid")
    rmp = RMPFlowController(
        name="controller_static_screen_native_rmp",
        robot_articulation=robot,
        physics_dt=DEFAULT_CONTROL_DT_S,
    )
    recording_rmp = _RecordingCspaceController(np, rmp)
    pick = PickController(
        name="controller_static_screen_native_pick",
        cspace_controller=recording_rmp,
        events_dt=event_durations,
    )
    pick.reset()
    screen_scope = {
        "blocking_pairs": full_scope["blocking_pairs"],
        "allowed_source_shell_pairs": full_scope["allowed_source_shell_pairs"],
    }
    margin = contract.get("aabb_numerical_margin_m")
    if (
        isinstance(margin, bool)
        or not isinstance(margin, (int, float))
        or not math.isfinite(float(margin))
        or float(margin) < 0.0
    ):
        raise RuntimeError("controller_static_screen_margin_invalid")
    trace_path = out_dir / "configuration_pair_trace.jsonl.gz"
    action_path = out_dir / "controller_action_ledger.jsonl.gz"
    trace_digest = hashlib.sha256()
    action_digest = hashlib.sha256()
    trace_count = 0
    action_count = 0
    source_matrix = _world_matrix(np, Usd, UsdGeom, stage, SOURCE_ROOT_PATH)
    configuration_sample_indices: dict[tuple[int, tuple[float, ...], str], int] = {}
    events = []
    close_emitted = False
    invalid_controller_action: dict[str, Any] | None = None
    trace_stream = gzip.open(trace_path, "xb")
    action_stream = gzip.open(action_path, "xb")
    try:
        max_commands = 2 + sum(math.ceil(1.0 / duration) + 2 for duration in event_durations[:4])
        for action_ordinal in range(max_commands):
            joint_before = _read_joint_positions(np, robot)
            event_before = int(pick._event)
            if event_before > 4:
                raise RuntimeError("controller_static_screen_lift_event_reached")
            action = pick.forward(
                picking_position=object_position.copy(),
                current_joint_positions=np.asarray(joint_before, dtype=np.float64),
                object_name="beaker2",
                object_size=object_size.copy(),
                gripper_control=type(
                    "NoAttachmentGripper",
                    (),
                    {"add_object_to_gripper": staticmethod(lambda *_args, **_kwargs: None)},
                )(),
                gripper_position=_robot_tool_center_position(
                    np, Rotation, robot_kinematics
                ).copy(),
                end_effector_orientation=orientation.copy(),
                pre_offset_x=forward_parameters["pre_offset_x"],
                pre_offset_z=forward_parameters["pre_offset_z"],
                after_offset_z=forward_parameters["after_offset_z"],
                pick_z_offset_m=z_offset,
                pick_x_offset_m=x_offset,
            )
            emitted_event = pick._last_emitted_event
            event = -1 if emitted_event is None else emitted_event
            if type(event) is not int or event < -1 or event > 4:
                raise RuntimeError("controller_static_screen_controller_event_invalid")
            _require_semantics_prefix_match(
                np=np,
                capture=semantics_capture,
                action_ordinal=action_ordinal,
                event_before=event_before,
                event_after=int(pick._event),
                last_emitted_event=emitted_event,
                action=action,
                rmp_forward_calls=recording_rmp.forward_calls,
            )
            explicit_action, discarded_velocity = _explicit_position_action(
                np, action, dof_count=len(joint_before)
            )
            resolved = screen.resolve_joint_configuration(joint_before, explicit_action)
            action_sha256 = screen.canonical_json_sha256(explicit_action)
            try:
                joint_after, source_matrix, robot_world_matrices = _materialize_configuration(
                    np=np,
                    Rotation=Rotation,
                    Usd=Usd,
                    UsdGeom=UsdGeom,
                    stage=stage,
                    robot=robot,
                    robot_kinematics=robot_kinematics,
                    source_matrix_before=source_matrix,
                    world=world,
                    timeline=timeline,
                    baseline=baseline,
                    target_positions=resolved["joint_positions"],
                    joint_lower_limits=joint_lower_limits,
                    joint_upper_limits=joint_upper_limits,
                    is_hold=resolved["is_hold"],
                )
            except _JointLimitViolation as exc:
                invalid_controller_action = {
                    "action_ordinal": action_ordinal,
                    "controller_event_before": event_before,
                    "controller_event": event,
                    "action": explicit_action,
                    "discarded_joint_velocities": discarded_velocity,
                    "action_sha256": action_sha256,
                    "joint_positions_before": joint_before,
                    "resolved_joint_positions": resolved["joint_positions"],
                    "changed_joint_indices": resolved["changed_joint_indices"],
                    "is_hold": resolved["is_hold"],
                    "joint_limit_violations": exc.violations,
                    "outcome": "JOINT_LIMIT_REJECTED",
                }
                _write_jsonl_record(
                    action_stream, action_digest, invalid_controller_action
                )
                action_count += 1
                events.append(event)
                break
            key = (event, tuple(joint_after), action_sha256)
            if key not in configuration_sample_indices:
                sample_index = trace_count
                configuration_sample_indices[key] = sample_index
                record = {
                    "sample_index": sample_index,
                    "controller_event": event,
                    "joint_positions": joint_after,
                    "action_sha256": action_sha256,
                    "pair_results": _screen_pair_results(
                        np=np,
                        Usd=Usd,
                        UsdGeom=UsdGeom,
                        stage=stage,
                        catalog=catalog,
                        screen_scope=screen_scope,
                        numerical_margin_m=float(margin),
                        robot_collider_world_matrices=robot_world_matrices,
                    ),
                }
                _write_jsonl_record(trace_stream, trace_digest, record)
                trace_count += 1
            else:
                sample_index = configuration_sample_indices[key]
            action_record = {
                "action_ordinal": action_ordinal,
                "controller_event_before": event_before,
                "controller_event": event,
                "action": explicit_action,
                "discarded_joint_velocities": discarded_velocity,
                "action_sha256": action_sha256,
                "joint_positions_before": joint_before,
                "joint_positions_after": joint_after,
                "changed_joint_indices": resolved["changed_joint_indices"],
                "is_hold": resolved["is_hold"],
                "screen_sample_index": sample_index,
            }
            _write_jsonl_record(action_stream, action_digest, action_record)
            action_count += 1
            events.append(event)
            if event == 4:
                close_emitted = True
                break
        if invalid_controller_action is None and (
            not close_emitted
            or pick._close_command_emitted is not True
            or pick._lift_command_emitted
        ):
            raise RuntimeError("controller_static_screen_first_close_not_reached")
    finally:
        trace_stream.close()
        action_stream.close()
    controller_report = {
        "controller_class": "PickController",
        "rmp_controller_class": "RMPFlowController",
        "control_dt_s": DEFAULT_CONTROL_DT_S,
        "events_dt": event_durations,
        "target_orientation_wxyz": _finite_vector(
            np, orientation, field="target_orientation", length=4
        ),
        "pick_z_offset_m": z_offset,
        "pick_x_offset_m": x_offset,
        "native_pick_forward_parameters": forward_parameters,
        "event_sequence": events,
        "first_close_emitted": close_emitted,
        "lift_command_emitted": bool(pick._lift_command_emitted),
        "robot_transform_authority": "physx_tensor_link_transforms_v1",
        "robot_link_names": list(robot_kinematics["body_names"]),
        "joint_lower_limits": _finite_vector(
            np, joint_lower_limits, field="joint_lower_limits", length=9
        ),
        "joint_upper_limits": _finite_vector(
            np, joint_upper_limits, field="joint_upper_limits", length=9
        ),
        "audited_event0_raw_action_sha256": screen.canonical_json_sha256(
            semantics_capture["event0"]["raw_action"]
        ),
    }
    object_geometry = {
        "source_root_path": SOURCE_ROOT_PATH,
        "object_position_m": _finite_vector(
            np, object_position, field="object_position", length=3
        ),
        "object_size_m": _finite_vector(
            np, object_size, field="object_size", length=3
        ),
    }
    trace_artifact = {
        "path": trace_path.name,
        "sha256": _sha256_file(trace_path),
        "stream_sha256": trace_digest.hexdigest(),
        "record_count": trace_count,
    }
    action_artifact = {
        "path": action_path.name,
        "sha256": _sha256_file(action_path),
        "stream_sha256": action_digest.hexdigest(),
        "record_count": action_count,
    }
    if invalid_controller_action is not None:
        _require_paused_unchanged(
            world,
            timeline,
            baseline,
            context="controller_configuration_invalid",
        )
        return {
            "candidate_id": "v7-native-pick-prefix-to-first-close",
            "controller": controller_report,
            "object_geometry": object_geometry,
            "invalid_controller_action": invalid_controller_action,
            "selection": {
                "decision": "SCREEN_CONTROLLER_CONFIGURATION_INVALID",
                "selected_candidate_id": None,
                "passing_candidate_ids": [],
            },
            "configuration_pair_trace": trace_artifact,
            "controller_action_ledger": action_artifact,
        }
    evaluation = screen.evaluate_configuration_trace(screen_scope, _iter_trace(trace_path))
    if evaluation["configuration_count"] != trace_count:
        raise RuntimeError("controller_static_screen_trace_count_mismatch")
    selection = screen.select_candidate(
        [{"candidate_id": "v7-native-pick-prefix-to-first-close", **evaluation}]
    )
    _require_paused_unchanged(world, timeline, baseline, context="screen_complete")
    return {
        "candidate_id": "v7-native-pick-prefix-to-first-close",
        "controller": controller_report,
        "object_geometry": object_geometry,
        "evaluation": evaluation,
        "selection": selection,
        "configuration_pair_trace": trace_artifact,
        "controller_action_ledger": action_artifact,
    }


def run_static_screen(
    *,
    app: Any,
    out_dir: Path,
    frozen_config: Mapping[str, Any],
    contract: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    """Run the nonformal static screen after effective-runtime attestation."""
    if (
        not isinstance(frozen_config, Mapping)
        or not isinstance(contract, Mapping)
        or not isinstance(runtime, Mapping)
        or contract.get("authority") != "nonformal_controller_static_collision_screen_v1"
        or contract.get("classification") != "NON_FORMAL_STATIC_SCREEN_ONLY"
        or contract.get("g0_or_gate_authorized") is not False
        or contract.get("post_reset_physics_steps_allowed") != 0
    ):
        raise RuntimeError("controller_static_screen_runtime_contract_invalid")
    runtime_identity = runtime.get("runtime_identity")
    if not isinstance(runtime_identity, Mapping) or not isinstance(
        runtime_identity.get("sha256"), str
    ):
        raise RuntimeError("controller_static_screen_runtime_identity_missing")

    from isaacsim_compat import install_legacy_isaacsim_aliases

    install_legacy_isaacsim_aliases()
    import numpy as np
    import omni.physx
    import omni.timeline
    import omni.usd
    import isaacsim.robot_motion.motion_generation as mg
    from isaacsim.core.api import World
    from isaacsim.core.utils.stage import add_reference_to_stage, get_stage_units
    from pxr import Sdf, Usd, UsdGeom, UsdPhysics
    from scipy.spatial.transform import Rotation

    from controllers.atomic_actions.pick_controller import PickController
    from factories.robot_factory import create_robot
    from robots.franka.rmpflow_controller import RMPFlowController
    from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as native
    from tools.labutopia_fluid import run_real_pbd_grasp_v2_g0_geometry as g0_geometry
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
    ):
        raise RuntimeError("controller_static_screen_frozen_binding_invalid")
    overlay = diagnostic.get("hidden_cube_treatment")
    if not isinstance(overlay, Mapping):
        raise RuntimeError("controller_static_screen_hidden_cube_treatment_missing")
    overlay_path = Path(native.REPO_ROOT / str(overlay.get("usd_path", ""))).resolve()
    if (
        not overlay_path.is_file()
        or _sha256_file(overlay_path) != contract.get("hidden_cube_overlay_sha256")
    ):
        raise RuntimeError("controller_static_screen_hidden_cube_binding_invalid")

    world = None
    try:
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("controller_static_screen_stage_missing")
        add_reference_to_stage(
            usd_path=str(local_scene["absolute_usd_path"]), prim_path="/World"
        )
        robot = native.create_diagnostic_local_franka(
            create_robot, config, local_franka=local_franka
        )
        app.update()
        app.update()
        session = stage.GetSessionLayer()
        if session is None:
            raise RuntimeError("controller_static_screen_session_layer_missing")
        if str(overlay_path) not in session.subLayerPaths:
            session.subLayerPaths.append(str(overlay_path))
        app.update()
        app.update()

        timeline = omni.timeline.get_timeline_interface()
        pre_reset_query_baseline = _stopped_receipt(timeline)
        if (
            pre_reset_query_baseline["is_playing"]
            or not pre_reset_query_baseline["is_stopped"]
        ):
            raise RuntimeError("controller_static_screen_pre_reset_timeline_not_stopped")
        source_mesh = _enabled_colliders(Usd, UsdPhysics, stage, SOURCE_MESH_PATH)
        wrapper = _enabled_colliders(Usd, UsdPhysics, stage, WRAPPER_ROOT_PATH)
        table = _enabled_colliders(Usd, UsdPhysics, stage, TABLE_PATH)
        beaker1 = _enabled_colliders(Usd, UsdPhysics, stage, BEAKER1_PATH)
        robot_colliders = _enabled_colliders(Usd, UsdPhysics, stage, ROBOT_ROOT_PATH)
        left_fingers = _enabled_colliders(
            Usd, UsdPhysics, stage, "/World/Franka/panda_leftfinger"
        )
        right_fingers = _enabled_colliders(
            Usd, UsdPhysics, stage, "/World/Franka/panda_rightfinger"
        )
        inventories = {
            "source_mesh": len(source_mesh),
            "source_wrapper": len(wrapper),
            "table": len(table),
            "beaker1": len(beaker1),
            "full_robot": len(robot_colliders),
        }
        if (
            inventories != contract.get("expected_collider_inventory")
            or source_mesh != [SOURCE_MESH_PATH]
            or table != [TABLE_PATH]
            or len(left_fingers) != 1
            or len(right_fingers) != 1
        ):
            raise RuntimeError(
                "controller_static_screen_collider_inventory_invalid:"
                f"inventories={inventories}:source_mesh={source_mesh}:table={table}:"
                f"left_fingers={left_fingers}:right_fingers={right_fingers}"
            )
        role_paths = {
            "source_external_shell_paths": source_mesh,
            "source_internal_wrapper_paths": wrapper,
            "support_collider_paths": table,
            "beaker1_collider_paths": beaker1,
            "full_robot_collider_paths": robot_colliders,
            "hand_collider_paths": _enabled_colliders(
                Usd, UsdPhysics, stage, "/World/Franka/panda_hand"
            ),
            "finger_pad_collider_paths": {
                "left": left_fingers,
                "right": right_fingers,
            },
        }
        full_scope = g0_geometry.build_full_robot_static_collision_scope(role_paths)
        if (
            len(full_scope["allowed_source_shell_pairs"]) != 2
            or len(full_scope["blocking_pairs"]) != 3210
        ):
            raise RuntimeError("controller_static_screen_collision_scope_invalid")
        required_paths = sorted(
            {
                path
                for pair in [
                    *full_scope["blocking_pairs"],
                    *full_scope["allowed_source_shell_pairs"],
                ]
                for path in pair
            }
        )
        catalog = _collect_cooked_catalog(
            app=app,
            np=np,
            Sdf=Sdf,
            Usd=Usd,
            UsdPhysics=UsdPhysics,
            stage=stage,
            timeline=timeline,
            world=None,
            baseline=pre_reset_query_baseline,
            required_paths=required_paths,
        )
        _require_query_timeline_unchanged(
            None,
            timeline,
            pre_reset_query_baseline,
            context="catalog_complete",
        )

        world = World(
            physics_dt=float(diagnostic["physics_dt"]),
            rendering_dt=float(diagnostic["physics_dt"]),
            stage_units_in_meters=float(diagnostic["stage_units_in_meters"]),
            physics_prim_path=str(diagnostic["physics_scene_path"]),
            backend="numpy",
            set_defaults=False,
        )
        omni.physx.get_physx_interface().overwrite_gpu_setting(1)
        reset_before = _runtime_receipt(world, timeline)
        world.reset()
        reset_after = _runtime_receipt(world, timeline)
        physics_simulation_view = world.physics_sim_view
        if physics_simulation_view is None:
            raise RuntimeError("controller_static_screen_world_tensor_view_missing")
        robot.initialize(physics_sim_view=physics_simulation_view)
        post_initialization = _runtime_receipt(world, timeline)
        if (
            post_initialization["world_index"] != reset_after["world_index"]
            or post_initialization["timeline_time_s"] != reset_after["timeline_time_s"]
        ):
            raise RuntimeError("controller_static_screen_robot_initialization_advanced")
        baseline = _pause_after_reset(
            app,
            world,
            timeline,
            post_reset_receipt=post_initialization,
        )
        robot_kinematics = _robot_kinematic_model(
            np=np,
            Rotation=Rotation,
            Usd=Usd,
            UsdGeom=UsdGeom,
            UsdPhysics=UsdPhysics,
            stage=stage,
            robot=robot,
            expected_simulation_view=physics_simulation_view,
            collider_paths=full_scope["full_robot_collider_paths"],
        )
        joint_lower_limits, joint_upper_limits = _joint_position_limits(np, robot)
        expected_stage_units = diagnostic.get("stage_units_in_meters")
        if (
            isinstance(expected_stage_units, bool)
            or not isinstance(expected_stage_units, (int, float))
            or not math.isfinite(float(expected_stage_units))
            or float(expected_stage_units) <= 0.0
        ):
            raise RuntimeError("controller_static_screen_stage_units_invalid")
        controller_semantics = _controller_semantics_audit(
            np=np,
            Rotation=Rotation,
            Usd=Usd,
            UsdGeom=UsdGeom,
            stage=stage,
            world=world,
            timeline=timeline,
            baseline=baseline,
            robot=robot,
            robot_kinematics=robot_kinematics,
            joint_lower_limits=joint_lower_limits,
            joint_upper_limits=joint_upper_limits,
            PickController=PickController,
            RMPFlowController=RMPFlowController,
            RmpFlow=mg.lula.motion_policies.RmpFlow,
            ObjectUtils=ObjectUtils,
            get_stage_units=get_stage_units,
            expected_stage_units_in_meters=float(expected_stage_units),
            contract=contract,
            out_dir=out_dir,
        )
        semantics_evaluation = controller_semantics["evaluation"]
        semantics_capture = controller_semantics["capture"]
        controller_semantics_report = {
            "artifact": controller_semantics["artifact"],
            "evaluation": semantics_evaluation,
        }
        if controller_semantics["qdot_counterfactual_evaluation"] is not None:
            controller_semantics_report["qdot_counterfactual_evaluation"] = (
                controller_semantics["qdot_counterfactual_evaluation"]
            )
        if (
            semantics_evaluation.get("decision") == "STATIC_PROJECTION_ELIGIBLE"
            and semantics_evaluation.get("static_projection_authorized") is True
        ):
            result = _controller_screen(
                np=np,
                Rotation=Rotation,
                Usd=Usd,
                UsdGeom=UsdGeom,
                stage=stage,
                world=world,
                timeline=timeline,
                baseline=baseline,
                robot=robot,
                robot_kinematics=robot_kinematics,
                joint_lower_limits=joint_lower_limits,
                joint_upper_limits=joint_upper_limits,
                PickController=PickController,
                RMPFlowController=RMPFlowController,
                ObjectUtils=ObjectUtils,
                catalog=catalog,
                full_scope=full_scope,
                contract=contract,
                semantics_capture=semantics_capture,
                out_dir=out_dir,
            )
            decision = result["selection"]["decision"]
        else:
            result = None
            decision = semantics_evaluation.get("decision")
            if not isinstance(decision, str):
                raise RuntimeError("controller_static_screen_semantics_decision_invalid")
        final_receipt = _require_paused_unchanged(
            world, timeline, baseline, context="runtime_complete"
        )
        return {
            "schema_version": 1,
            "manifest_type": "nonformal_controller_static_collision_screen_child_v1",
            "authority": "nonformal_controller_static_collision_screen_v1",
            "classification": "NON_FORMAL_STATIC_SCREEN_ONLY",
            "decision": decision,
            "contract": dict(contract),
            "runtime": dict(runtime),
            "scope": {
                "controller_prefix": "v7_native_pick_reset_to_first_close_only",
                "reset_bootstrap_permitted": True,
                "reset_bootstrap_advance": {
                    "world_index_delta": reset_after["world_index"] - reset_before["world_index"],
                    "timeline_time_delta_s": (
                        reset_after["timeline_time_s"] - reset_before["timeline_time_s"]
                    ),
                },
                "post_reset_physics_steps_allowed": 0,
                "post_reset_physics_advance": {
                    "world_index_delta": (
                        final_receipt["world_index"]
                        - post_initialization["world_index"]
                    ),
                    "timeline_time_delta_s": (
                        final_receipt["timeline_time_s"]
                        - post_initialization["timeline_time_s"]
                    ),
                    "verified_zero": (
                        final_receipt["world_index"]
                        == post_initialization["world_index"]
                        and final_receipt["timeline_time_s"]
                        == post_initialization["timeline_time_s"]
                    ),
                },
                "controller_semantics_gate": semantics_evaluation["decision"],
                "controller_action_projection": "native_raw_action_captured_before_static_projection",
                "source_attachment_or_lift": False,
                "runtime_contact_observer": False,
                "g0_or_gate_evaluated": False,
                "persistent_usd_modified": False,
                "pose_materialization": (
                    "paused_direct_joint_positions_with_readback"
                    if result is not None
                    else "not_reached_controller_semantics_not_eligible"
                ),
                "cooked_catalog_acquisition": "pre_reset_stopped_property_query",
            },
            "timeline": {
                "pre_reset_cooked_query": pre_reset_query_baseline,
                "before_reset": reset_before,
                "after_reset": reset_after,
                "after_robot_initialization": post_initialization,
                "baseline": baseline,
                "final": final_receipt,
                "unchanged": final_receipt == baseline,
            },
            "fixture": {
                "local_scene_sha256": local_scene["sha256"],
                "local_franka_sha256": local_franka["sha256"],
                "hidden_cube_overlay_sha256": contract["hidden_cube_overlay_sha256"],
                "runtime_identity_sha256": runtime_identity["sha256"],
            },
            "collision_scope": full_scope,
            "cooked_collider_catalog": {
                "authority": "runtime_stopped_cooked_aabb_plus_tensor_link_pose_v1",
                "colliders": [catalog[path] for path in sorted(catalog)],
                "sha256": screen.canonical_json_sha256(
                    {"colliders": [catalog[path] for path in sorted(catalog)]}
                ),
            },
            "controller_semantics": controller_semantics_report,
            "screen": result,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        clear_instance = getattr(World, "clear_instance", None)
        if callable(clear_instance):
            clear_instance()
