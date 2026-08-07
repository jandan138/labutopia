"""Sealed-child runtime implementation for the wrapper-to-Franka A/B probe.

This module is imported only after effective-runtime attestation. It performs
no controller actions, does not attach or lift the vessel, and writes no USD
asset. Each variant uses a new stage and an anonymous session layer.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import nonformal_collision_filter_proof as proof


HAND_BODY_PATH = "/World/Franka/panda_hand"
SOURCE_ROOT_PATH = "/World/beaker2"
SOURCE_MESH_PATH = "/World/beaker2/mesh"
WRAPPER_ROOT_PATH = "/World/beaker2/FluidSafeWrapperCanonical"
COLLISION_GROUP_ROOT = "/World/ContactGraspCollisionGroups"
ENVIRONMENT_GROUP_PATH = f"{COLLISION_GROUP_ROOT}/Environment"
INTERIOR_GROUP_PATH = f"{COLLISION_GROUP_ROOT}/SourceFluidInterior"
PROBE_GROUP_PATH = f"{COLLISION_GROUP_ROOT}/ABProbeFranka"
UNFILTERED_VARIANT = "scoped_unfiltered_qualification"
AUTHORED_VARIANT = "authored_filter_confirmation"
VARIANTS = (UNFILTERED_VARIANT, AUTHORED_VARIANT)

# The same source-mesh-center-to-hand-collider-center grid is replayed in both
# fresh stages. It deliberately probes a compact static neighborhood only.
GRID_XY_M = (-0.06, -0.03, 0.0, 0.03, 0.06)
GRID_Z_M = (-0.035, 0.0, 0.035)


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


def _finite_vector(np: Any, value: Any, *, field: str, length: int = 3) -> list[float]:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (length,) or not np.isfinite(array).all():
        raise RuntimeError(f"filter_proof_{field}_invalid")
    return [float(item) for item in array.tolist()]


def _enabled_colliders(Usd: Any, UsdPhysics: Any, stage: Any, root_path: str) -> list[str]:
    root = stage.GetPrimAtPath(root_path)
    if not root or not root.IsValid():
        raise RuntimeError(f"filter_proof_collider_root_missing:{root_path}")
    colliders = []
    for prim in Usd.PrimRange(root):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = prim.GetAttribute("physics:collisionEnabled")
        if enabled and enabled.Get() is False:
            continue
        colliders.append(str(prim.GetPath()))
    if not colliders:
        raise RuntimeError(f"filter_proof_colliders_missing:{root_path}")
    return sorted(set(colliders))


def _relationship_targets(prim: Any, name: str) -> list[str]:
    relationship = prim.GetRelationship(name)
    if not relationship:
        return []
    return sorted(str(target) for target in relationship.GetTargets())


def _world_bound_center(np: Any, Usd: Any, UsdGeom: Any, stage: Any, path: str) -> Any:
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"filter_proof_bound_prim_missing:{path}")
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[UsdGeom.Tokens.default_],
        useExtentsHint=True,
    )
    bounds = cache.ComputeWorldBound(prim).ComputeAlignedRange()
    minimum = np.asarray(bounds.GetMin(), dtype=np.float64)
    maximum = np.asarray(bounds.GetMax(), dtype=np.float64)
    if (
        minimum.shape != (3,)
        or maximum.shape != (3,)
        or not np.isfinite(minimum).all()
        or not np.isfinite(maximum).all()
        or np.any(maximum < minimum)
    ):
        raise RuntimeError(f"filter_proof_bound_invalid:{path}")
    return (minimum + maximum) / 2.0


def _event_name(value: Any) -> str:
    named = {
        "CONTACT_FOUND": "FOUND",
        "CONTACT_LOST": "LOST",
        "CONTACT_PERSIST": "PERSIST",
    }.get(getattr(value, "name", None))
    if named is not None:
        return named
    try:
        return {0: "FOUND", 1: "LOST", 2: "PERSIST"}[int(value)]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("filter_proof_contact_event_invalid") from exc


def _resolve_path(np: Any, PhysicsSchemaTools: Any, identifier: Any) -> str:
    if isinstance(identifier, bool) or not isinstance(identifier, (int, np.integer)):
        raise RuntimeError("filter_proof_contact_identifier_invalid")
    value = str(PhysicsSchemaTools.intToSdfPath(int(identifier)))
    if not value:
        raise RuntimeError("filter_proof_contact_identifier_unresolved")
    return value


def _install_contact_report_api(
    PhysxSchema: Any,
    stage: Any,
    body_paths: tuple[str, ...],
) -> list[str]:
    installed = []
    for path in body_paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise RuntimeError(f"filter_proof_contact_body_missing:{path}")
        api = PhysxSchema.PhysxContactReportAPI.Apply(prim)
        if not api:
            raise RuntimeError(f"filter_proof_contact_api_apply_failed:{path}")
        api.CreateThresholdAttr().Set(0.0)
        report_pairs = api.CreateReportPairsRel()
        report_pairs.ClearTargets(True)
        if api.GetThresholdAttr().Get() != 0.0 or report_pairs.GetTargets():
            raise RuntimeError(f"filter_proof_contact_api_invalid:{path}")
        installed.append(path)
    return installed


def _set_source_kinematic(UsdPhysics: Any, stage: Any) -> dict[str, Any]:
    source = stage.GetPrimAtPath(SOURCE_ROOT_PATH)
    if not source or not source.IsValid() or not source.HasAPI(UsdPhysics.RigidBodyAPI):
        raise RuntimeError("filter_proof_source_rigid_body_missing")
    api = UsdPhysics.RigidBodyAPI(source)
    attribute = api.CreateKinematicEnabledAttr()
    before = attribute.Get()
    attribute.Set(True)
    if attribute.Get() is not True:
        raise RuntimeError("filter_proof_source_kinematic_write_failed")
    return {"path": SOURCE_ROOT_PATH, "before": before, "after": True}


def _verify_authored_collision_groups(UsdPhysics: Any, stage: Any) -> dict[str, Any]:
    environment = stage.GetPrimAtPath(ENVIRONMENT_GROUP_PATH)
    interior = stage.GetPrimAtPath(INTERIOR_GROUP_PATH)
    if (
        not environment
        or not environment.IsValid()
        or not environment.IsA(UsdPhysics.CollisionGroup)
        or not interior
        or not interior.IsValid()
        or not interior.IsA(UsdPhysics.CollisionGroup)
    ):
        raise RuntimeError("filter_proof_authored_collision_group_missing")
    interior_filters = _relationship_targets(interior, "physics:filteredGroups")
    if interior_filters != [ENVIRONMENT_GROUP_PATH]:
        raise RuntimeError("filter_proof_authored_interior_filter_invalid")
    environment_includes = _relationship_targets(
        environment, "collection:colliders:includes"
    )
    if "/World" not in environment_includes:
        raise RuntimeError("filter_proof_authored_environment_include_invalid")
    return {
        "environment_group_path": ENVIRONMENT_GROUP_PATH,
        "environment_includes": environment_includes,
        "environment_excludes": _relationship_targets(
            environment, "collection:colliders:excludes"
        ),
        "interior_filtered_groups": interior_filters,
    }


def _apply_unfiltered_session_edit(
    Sdf: Any,
    Usd: Any,
    UsdPhysics: Any,
    stage: Any,
    selected_hand_collider: str,
) -> dict[str, Any]:
    environment = stage.GetPrimAtPath(ENVIRONMENT_GROUP_PATH)
    if not environment or not environment.IsValid():
        raise RuntimeError("filter_proof_environment_group_missing")
    collection = Usd.CollectionAPI(environment, "colliders")
    excludes = collection.GetExcludesRel()
    if not excludes:
        excludes = collection.CreateExcludesRel()
    before = sorted(str(target) for target in excludes.GetTargets())
    after = sorted(set(before) | {selected_hand_collider})
    excludes.SetTargets([Sdf.Path(path) for path in after])

    probe_group = UsdPhysics.CollisionGroup.Define(stage, PROBE_GROUP_PATH)
    if not probe_group or not probe_group.GetPrim().IsValid():
        raise RuntimeError("filter_proof_probe_group_create_failed")
    probe_collection = Usd.CollectionAPI.Apply(probe_group.GetPrim(), "colliders")
    includes = probe_collection.CreateIncludesRel()
    includes.SetTargets([Sdf.Path(selected_hand_collider)])
    filters = probe_group.GetPrim().GetRelationship("physics:filteredGroups")
    if filters and filters.GetTargets():
        raise RuntimeError("filter_proof_probe_group_filtered_unexpected")
    if _relationship_targets(environment, "collection:colliders:excludes") != after:
        raise RuntimeError("filter_proof_environment_exclude_write_failed")
    if _relationship_targets(probe_group.GetPrim(), "collection:colliders:includes") != [
        selected_hand_collider
    ]:
        raise RuntimeError("filter_proof_probe_group_include_write_failed")
    return {
        "environment_excludes_before": before,
        "environment_excludes_after": after,
        "probe_group_path": PROBE_GROUP_PATH,
        "probe_group_includes": [selected_hand_collider],
        "probe_group_filtered_groups": [],
    }


def _contact_report_sample(
    *,
    np: Any,
    PhysicsSchemaTools: Any,
    simulation: Any,
    expected_stage_id: int,
    pose_index: int,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    raw = simulation.get_full_contact_report()
    if not isinstance(raw, tuple) or len(raw) != 3:
        raise RuntimeError("filter_proof_contact_report_tuple_invalid")
    raw_headers, raw_points, raw_anchors = raw
    headers = []
    projected = []
    for header in raw_headers:
        normalized = {
            "type": _event_name(header.type),
            "stage_id": int(header.stage_id),
            "actor0": _resolve_path(np, PhysicsSchemaTools, header.actor0),
            "actor1": _resolve_path(np, PhysicsSchemaTools, header.actor1),
            "collider0": _resolve_path(np, PhysicsSchemaTools, header.collider0),
            "collider1": _resolve_path(np, PhysicsSchemaTools, header.collider1),
            "proto_index0": int(header.proto_index0),
            "proto_index1": int(header.proto_index1),
            "contact_data_offset": int(header.contact_data_offset),
            "num_contact_data": int(header.num_contact_data),
            "friction_anchors_offset": int(header.friction_anchors_offset),
            "num_friction_anchors_data": int(header.num_friction_anchors_data),
        }
        if normalized["stage_id"] != expected_stage_id:
            raise RuntimeError("filter_proof_contact_stage_id_mismatch")
        headers.append(normalized)
        projected.append(
            {
                "type": normalized["type"],
                "actor0": normalized["actor0"],
                "actor1": normalized["actor1"],
                "collider0": normalized["collider0"],
                "collider1": normalized["collider1"],
            }
        )
    points = []
    for point in raw_points:
        separation = float(point.separation)
        if not math.isfinite(separation):
            raise RuntimeError("filter_proof_contact_separation_invalid")
        points.append(
            {
                "position": _finite_vector(np, point.position, field="contact_position"),
                "normal": _finite_vector(np, point.normal, field="contact_normal"),
                "impulse": _finite_vector(np, point.impulse, field="contact_impulse"),
                "separation": separation,
                "face_index0": int(point.face_index0),
                "face_index1": int(point.face_index1),
            }
        )
    anchors = [
        {
            "position": _finite_vector(np, anchor.position, field="anchor_position"),
            "impulse": _finite_vector(np, anchor.impulse, field="anchor_impulse"),
        }
        for anchor in raw_anchors
    ]
    return (
        {
            "pose_index": pose_index,
            "headers": headers,
            "contact_data": points,
            "friction_anchors": anchors,
        },
        projected,
    )


def _transform_plan() -> dict[str, Any]:
    offsets = [
        [float(x), float(y), float(z)]
        for z in GRID_Z_M
        for x in GRID_XY_M
        for y in GRID_XY_M
    ]
    payload = {
        "authority": "wrapper_franka_filter_static_transform_plan_v1",
        "selected_hand_anchor": "world_bbox_center",
        "source_anchor": "source_mesh_world_bbox_center",
        "source_kinematic": True,
        "source_orientation": "reset_orientation_wxyz",
        "physics_steps_per_pose": 1,
        "offsets_m": offsets,
    }
    return {**payload, "sha256": proof.canonical_json_sha256(payload)}


def _new_stage(app: Any, omni_usd: Any, World: Any) -> Any:
    clear_instance = getattr(World, "clear_instance", None)
    if callable(clear_instance):
        clear_instance()
    context = omni_usd.get_context()
    context.new_stage()
    app.update()
    app.update()
    stage = context.get_stage()
    if stage is None:
        raise RuntimeError("filter_proof_new_stage_missing")
    return stage


def _run_variant(
    *,
    app: Any,
    out_dir: Path,
    variant: str,
    frozen_config: Mapping[str, Any],
    runtime_identity_sha256: str,
    build_variant_policy: Callable[[str, str], Mapping[str, Any]],
    modules: Mapping[str, Any],
) -> dict[str, Any]:
    np = modules["np"]
    omni_physx = modules["omni_physx"]
    omni_usd = modules["omni_usd"]
    World = modules["World"]
    SingleRigidPrim = modules["SingleRigidPrim"]
    add_reference_to_stage = modules["add_reference_to_stage"]
    get_physx_simulation_interface = modules["get_physx_simulation_interface"]
    PhysxSchema = modules["PhysxSchema"]
    PhysicsSchemaTools = modules["PhysicsSchemaTools"]
    Sdf = modules["Sdf"]
    Usd = modules["Usd"]
    UsdGeom = modules["UsdGeom"]
    UsdPhysics = modules["UsdPhysics"]
    UsdUtils = modules["UsdUtils"]
    create_robot = modules["create_robot"]
    native = modules["native"]

    config = frozen_config.get("config")
    diagnostic = config.get("diagnostic") if isinstance(config, Mapping) else None
    local_scene = frozen_config.get("local_scene")
    local_franka = frozen_config.get("local_franka")
    if (
        not isinstance(config, Mapping)
        or not isinstance(diagnostic, Mapping)
        or not isinstance(local_scene, Mapping)
        or not isinstance(local_franka, Mapping)
    ):
        raise RuntimeError("filter_proof_runtime_frozen_config_invalid")
    if diagnostic.get("source_body_path") != SOURCE_MESH_PATH:
        raise RuntimeError("filter_proof_runtime_source_mesh_path_invalid")
    if diagnostic.get("hand_body_path") != HAND_BODY_PATH:
        raise RuntimeError("filter_proof_runtime_hand_body_path_invalid")

    trace_path = out_dir / f"{variant}_full_contact_trace.jsonl.gz"
    trace_digest = hashlib.sha256()
    trace_count = 0
    trace_stream = None
    world = None
    try:
        stage = _new_stage(app, omni_usd, World)
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
            raise RuntimeError("filter_proof_session_layer_missing")
        overlay = diagnostic.get("hidden_cube_treatment")
        if not isinstance(overlay, Mapping):
            raise RuntimeError("filter_proof_hidden_cube_treatment_missing")
        overlay_path = Path(native.REPO_ROOT / str(overlay["usd_path"])).resolve()
        if native.sha256_file(overlay_path) != overlay.get("sha256"):
            raise RuntimeError("filter_proof_hidden_cube_hash_mismatch")
        if str(overlay_path) not in session.subLayerPaths:
            session.subLayerPaths.append(str(overlay_path))
        app.update()
        app.update()

        source_mesh_colliders = _enabled_colliders(
            Usd, UsdPhysics, stage, SOURCE_MESH_PATH
        )
        wrapper_colliders = _enabled_colliders(
            Usd, UsdPhysics, stage, WRAPPER_ROOT_PATH
        )
        hand_colliders = _enabled_colliders(Usd, UsdPhysics, stage, HAND_BODY_PATH)
        if source_mesh_colliders != [SOURCE_MESH_PATH]:
            raise RuntimeError("filter_proof_source_mesh_collider_inventory_invalid")
        if len(wrapper_colliders) != 145:
            raise RuntimeError("filter_proof_wrapper_collider_inventory_invalid")
        selected_hand_collider = hand_colliders[0]
        policy = dict(build_variant_policy(variant, selected_hand_collider))
        if policy.get("selected_hand_collider") != selected_hand_collider:
            raise RuntimeError("filter_proof_selected_hand_policy_mismatch")
        authored_groups = _verify_authored_collision_groups(UsdPhysics, stage)

        previous_target = stage.GetEditTarget()
        layer = Sdf.Layer.CreateAnonymous(f"filter_proof_{variant}.usda")
        if layer is None:
            raise RuntimeError("filter_proof_session_edit_layer_create_failed")
        session.subLayerPaths.insert(0, layer.identifier)
        try:
            stage.SetEditTarget(Usd.EditTarget(layer))
            kinematic_edit = _set_source_kinematic(UsdPhysics, stage)
            report_bodies = _install_contact_report_api(
                PhysxSchema, stage, (SOURCE_ROOT_PATH, HAND_BODY_PATH)
            )
            if variant == UNFILTERED_VARIANT:
                session_group_edit = _apply_unfiltered_session_edit(
                    Sdf, Usd, UsdPhysics, stage, selected_hand_collider
                )
            else:
                if stage.GetPrimAtPath(PROBE_GROUP_PATH).IsValid():
                    raise RuntimeError("filter_proof_authored_probe_group_unexpected")
                session_group_edit = None
        finally:
            stage.SetEditTarget(previous_target)
        simulation = get_physx_simulation_interface()
        simulation.flush_changes()
        session_layer_text = layer.ExportToString()
        session_layer_sha256 = hashlib.sha256(
            session_layer_text.encode("utf-8")
        ).hexdigest()

        world = World(
            physics_dt=float(diagnostic["physics_dt"]),
            stage_units_in_meters=float(diagnostic["stage_units_in_meters"]),
            physics_prim_path=str(diagnostic["physics_scene_path"]),
            backend="numpy",
            set_defaults=False,
        )
        omni_physx.get_physx_interface().overwrite_gpu_setting(1)
        world.reset()
        robot.initialize()
        source_body = SingleRigidPrim(
            prim_path=SOURCE_ROOT_PATH,
            name=f"filter_proof_source_{variant}",
        )
        source_body.initialize()
        kinematic = stage.GetPrimAtPath(SOURCE_ROOT_PATH).GetAttribute(
            "physics:kinematicEnabled"
        ).Get()
        if kinematic is not True:
            raise RuntimeError("filter_proof_runtime_source_not_kinematic")

        source_position, source_orientation = source_body.get_world_pose()
        source_position = np.asarray(source_position, dtype=np.float64)
        source_orientation = np.asarray(source_orientation, dtype=np.float64)
        if (
            source_position.shape != (3,)
            or source_orientation.shape != (4,)
            or not np.isfinite(source_position).all()
            or not np.isfinite(source_orientation).all()
        ):
            raise RuntimeError("filter_proof_source_reset_pose_invalid")
        mesh_center = _world_bound_center(
            np, Usd, UsdGeom, stage, SOURCE_MESH_PATH
        )
        hand_center = _world_bound_center(
            np, Usd, UsdGeom, stage, selected_hand_collider
        )
        source_mesh_center_offset = mesh_center - source_position
        plan = _transform_plan()
        reports: list[dict[str, str]] = []
        applied_poses = []
        trace_stream = gzip.open(trace_path, "xb")
        stage_id = int(UsdUtils.StageCache.Get().GetId(stage).ToLongInt())
        for pose_index, offset in enumerate(plan["offsets_m"]):
            offset_vector = np.asarray(offset, dtype=np.float64)
            target_position = hand_center - source_mesh_center_offset + offset_vector
            source_body.set_world_pose(
                position=target_position, orientation=source_orientation
            )
            world.step(render=False)
            record, projected = _contact_report_sample(
                np=np,
                PhysicsSchemaTools=PhysicsSchemaTools,
                simulation=simulation,
                expected_stage_id=stage_id,
                pose_index=pose_index,
            )
            record["source_root_position_m"] = _finite_vector(
                np, target_position, field="applied_source_position"
            )
            payload = _canonical_json_bytes(record)
            trace_stream.write(payload + b"\n")
            trace_digest.update(payload + b"\n")
            trace_count += 1
            reports.extend(projected)
            applied_poses.append(record["source_root_position_m"])
        trace_stream.close()
        trace_stream = None

        observation = {
            "variant": variant,
            "selected_hand_collider": selected_hand_collider,
            "source_mesh_colliders": source_mesh_colliders,
            "wrapper_colliders": wrapper_colliders,
            "transform_plan_sha256": plan["sha256"],
            "runtime_identity_sha256": runtime_identity_sha256,
            "reports": reports,
        }
        audit = proof.evaluate_variant_contacts(
            observation["variant"],
            observation["selected_hand_collider"],
            observation["source_mesh_colliders"],
            observation["wrapper_colliders"],
            observation["reports"],
        )
        return {
            "observation": observation,
            "audit": audit,
            "policy": policy,
            "authored_collision_groups": authored_groups,
            "common_session_edit": {
                "source_kinematic": kinematic_edit,
                "contact_report_bodies": report_bodies,
            },
            "variant_session_group_edit": session_group_edit,
            "session_layer_sha256": session_layer_sha256,
            "transform_plan": plan,
            "hand_anchor_world_m": _finite_vector(
                np, hand_center, field="hand_anchor"
            ),
            "source_mesh_center_offset_m": _finite_vector(
                np, source_mesh_center_offset, field="source_mesh_center_offset"
            ),
            "applied_source_root_positions_m": applied_poses,
            "full_contact_trace": {
                "path": trace_path.name,
                "sha256": _sha256_file(trace_path),
                "stream_sha256": trace_digest.hexdigest(),
                "record_count": trace_count,
            },
        }
    finally:
        if trace_stream is not None:
            trace_stream.close()
        clear_instance = getattr(World, "clear_instance", None)
        if callable(clear_instance):
            clear_instance()


def run_filter_proof(
    *,
    app: Any,
    out_dir: Path,
    frozen_config: Mapping[str, Any],
    contract: Mapping[str, Any],
    runtime: Mapping[str, Any],
    build_variant_policy: Callable[[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute the two fresh-stage variants and return diagnostic-only evidence."""
    validated_contract = proof.validate_filter_proof_contract(contract)
    runtime_identity = runtime.get("runtime_identity")
    if (
        not isinstance(runtime_identity, Mapping)
        or not isinstance(runtime_identity.get("sha256"), str)
        or len(runtime_identity["sha256"]) != 64
    ):
        raise RuntimeError("filter_proof_runtime_identity_missing")
    if not isinstance(frozen_config, Mapping) or not callable(build_variant_policy):
        raise RuntimeError("filter_proof_runtime_argument_invalid")

    from isaacsim_compat import install_legacy_isaacsim_aliases

    install_legacy_isaacsim_aliases()
    import numpy as np
    import omni.physx
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.utils.stage import add_reference_to_stage
    from omni.physx import get_physx_simulation_interface
    from pxr import PhysxSchema, PhysicsSchemaTools, Sdf, Usd, UsdGeom, UsdPhysics, UsdUtils

    from factories.robot_factory import create_robot
    from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as native

    modules = {
        "np": np,
        "omni_physx": omni.physx,
        "omni_usd": omni.usd,
        "World": World,
        "SingleRigidPrim": SingleRigidPrim,
        "add_reference_to_stage": add_reference_to_stage,
        "get_physx_simulation_interface": get_physx_simulation_interface,
        "PhysxSchema": PhysxSchema,
        "PhysicsSchemaTools": PhysicsSchemaTools,
        "Sdf": Sdf,
        "Usd": Usd,
        "UsdGeom": UsdGeom,
        "UsdPhysics": UsdPhysics,
        "UsdUtils": UsdUtils,
        "create_robot": create_robot,
        "native": native,
    }
    variants = {}
    for variant in VARIANTS:
        variants[variant] = _run_variant(
            app=app,
            out_dir=out_dir,
            variant=variant,
            frozen_config=frozen_config,
            runtime_identity_sha256=runtime_identity["sha256"],
            build_variant_policy=build_variant_policy,
            modules=modules,
        )
    unfiltered = variants[UNFILTERED_VARIANT]["observation"]
    authored = variants[AUTHORED_VARIANT]["observation"]
    result = proof.evaluate_ab_filter_proof(
        validated_contract, unfiltered, authored
    )
    decision = result["outcome"]
    return {
        "schema_version": 1,
        "manifest_type": "nonformal_wrapper_franka_filter_proof_child_v1",
        "authority": "nonformal_wrapper_franka_collision_filter_proof_v1",
        "classification": "NON_FORMAL_OBSERVATION_ONLY",
        "decision": decision,
        "contract": validated_contract,
        "runtime": dict(runtime),
        "scope": {
            "controller_started": False,
            "native_pick_or_lift_started": False,
            "g0_or_gate_evaluated": False,
            "persistent_usd_modified": False,
            "source_motion": "kinematic_session_layer_static_grid_only",
            "variant_stage_policy": "fresh_stage_per_variant",
        },
        "variants": variants,
        "comparison": result,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
