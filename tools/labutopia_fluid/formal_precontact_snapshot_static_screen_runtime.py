"""Sealed no-step static projection of a formal v2 precontact snapshot."""

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

from utils import formal_precontact_snapshot_static_screen as static_screen
from utils import formal_precontact_event0_snapshot_replay as snapshot_replay


AUTHORITY = "formal_precontact_snapshot_static_screen_v1"
CLASSIFICATION = "FORMAL_PRECONTACT_SNAPSHOT_STATIC_SCREEN_ONLY"
PROJECTION_NAME = "event0_snapshot_projection.json"


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


def _screen_pair_results(
    *,
    np: Any,
    legacy: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    catalog: Mapping[str, Mapping[str, Any]],
    scope: Mapping[str, Sequence[Sequence[str]]],
    numerical_margin_m: float,
    robot_world_matrices: Mapping[str, Any],
    source_world_matrices: Mapping[str, Any],
) -> list[dict[str, Any]]:
    paths = {
        path
        for field in ("blocking_pairs", "allowed_source_shell_pairs")
        for pair in scope[field]
        for path in pair
    }
    if paths != set(catalog) or set(robot_world_matrices).intersection(source_world_matrices):
        raise RuntimeError("formal_snapshot_static_projection_scope_invalid")
    overrides = {**dict(robot_world_matrices), **dict(source_world_matrices)}
    boxes = {
        path: legacy._cooked_world_box(
            np=np,
            Usd=Usd,
            UsdGeom=UsdGeom,
            stage=stage,
            collider=catalog[path],
            world_matrix=overrides.get(path),
            tensor_transform=path in robot_world_matrices,
        )
        for path in sorted(paths)
    }
    results = []
    for classification, field in (
        ("BLOCKING", "blocking_pairs"),
        ("ALLOWED_SOURCE_SHELL_FINGER", "allowed_source_shell_pairs"),
    ):
        for pair in scope[field]:
            separation = legacy._aabb_separation(np, boxes[pair[0]], boxes[pair[1]])
            results.append(
                {
                    "pair": list(pair),
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


def _link0_table_pair_result(
    *,
    np: Any,
    legacy: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    catalog: Mapping[str, Mapping[str, Any]],
    robot_world_matrices: Mapping[str, Any],
    numerical_margin_m: float,
) -> tuple[dict[str, Any], list[float], list[float]]:
    link0_path = static_screen.LINK0_COLLIDER_PATH
    table_path = static_screen.TABLE_COLLIDER_PATH
    if link0_path not in catalog or table_path not in catalog or link0_path not in robot_world_matrices:
        raise RuntimeError("formal_snapshot_static_link0_table_coverage_invalid")
    link0_matrix = np.asarray(robot_world_matrices[link0_path], dtype=np.float64)
    link0_box = legacy._cooked_world_box(
        np=np,
        Usd=Usd,
        UsdGeom=UsdGeom,
        stage=stage,
        collider=catalog[link0_path],
        world_matrix=link0_matrix,
        tensor_transform=True,
    )
    table_box = legacy._cooked_world_box(
        np=np,
        Usd=Usd,
        UsdGeom=UsdGeom,
        stage=stage,
        collider=catalog[table_path],
    )
    separation = legacy._aabb_separation(np, link0_box, table_box)
    axis_signed_separation = np.maximum(
        link0_box["world_min_m"] - table_box["world_max_m"],
        table_box["world_min_m"] - link0_box["world_max_m"],
    )
    positive_norm = float(np.linalg.norm(np.maximum(axis_signed_separation, 0.0)))
    if not math.isclose(separation, positive_norm, rel_tol=0.0, abs_tol=1.0e-12):
        raise RuntimeError("formal_snapshot_static_link0_table_separation_invalid")
    return (
        {
            "pair": sorted([link0_path, table_path]),
            "lower_bound_m": separation,
            "status": (
                "CLEAR"
                if separation > numerical_margin_m
                else "POTENTIAL_OVERLAP_OR_MARGIN"
            ),
        },
        [float(value) for value in link0_matrix.reshape(-1).tolist()],
        [float(value) for value in axis_signed_separation.tolist()],
    )


def _path_covers(candidate: str, path: str) -> bool:
    return candidate == path or path.startswith(f"{candidate}/")


def _link0_table_geometry_audit(
    *,
    np: Any,
    legacy: Any,
    Usd: Any,
    UsdGeom: Any,
    UsdPhysics: Any,
    stage: Any,
    catalog: Mapping[str, Mapping[str, Any]],
    robot_world_matrices: Mapping[str, Any],
) -> dict[str, Any]:
    """Record the authored/cooked metadata without inferring a shape overlap."""
    link0_path = static_screen.LINK0_COLLIDER_PATH
    table_path = static_screen.TABLE_COLLIDER_PATH
    expected_paths = sorted((link0_path, table_path))
    if (
        link0_path not in catalog
        or table_path not in catalog
        or link0_path not in robot_world_matrices
    ):
        raise RuntimeError("formal_snapshot_static_geometry_audit_coverage_invalid")

    def collider_record(path: str) -> dict[str, Any]:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            raise RuntimeError("formal_snapshot_static_geometry_audit_prim_missing")
        collision = UsdPhysics.CollisionAPI(prim)
        if not collision or collision.GetCollisionEnabledAttr().Get() is False:
            raise RuntimeError("formal_snapshot_static_geometry_audit_collision_invalid")
        mesh = UsdGeom.Mesh(prim)
        if prim.GetTypeName() == "Mesh":
            points = mesh.GetPointsAttr().Get()
            face_counts = mesh.GetFaceVertexCountsAttr().Get()
            if points is None or face_counts is None:
                raise RuntimeError("formal_snapshot_static_geometry_audit_mesh_topology_missing")
            point_count = len(points)
            triangle_count = sum(max(0, int(count) - 2) for count in face_counts)
        else:
            point_count = 0
            triangle_count = 0
        approximation_attr = prim.GetAttribute("physics:approximation")
        approximation_value = (
            approximation_attr.Get()
            if approximation_attr and approximation_attr.IsValid()
            else None
        )
        approximation = None if approximation_value is None else str(approximation_value)
        collider = catalog[path]
        local_min = np.asarray(collider["aabb_local_min_m"], dtype=np.float64)
        local_max = np.asarray(collider["aabb_local_max_m"], dtype=np.float64)
        if local_min.shape != (3,) or local_max.shape != (3,) or np.any(local_max < local_min):
            raise RuntimeError("formal_snapshot_static_geometry_audit_cooked_aabb_invalid")
        world_box = legacy._cooked_world_box(
            np=np,
            Usd=Usd,
            UsdGeom=UsdGeom,
            stage=stage,
            collider=collider,
            world_matrix=(robot_world_matrices[path] if path == link0_path else None),
            tensor_transform=path == link0_path,
        )
        return {
            "path": path,
            "type_name": str(prim.GetTypeName()),
            "collision_enabled": True,
            "mesh_collision_api_applied": prim.HasAPI(UsdPhysics.MeshCollisionAPI),
            "physics_approximation": approximation,
            "mesh_point_count": int(point_count),
            "mesh_triangle_count": int(triangle_count),
            "cooked_aabb_local_min_m": [float(value) for value in local_min.tolist()],
            "cooked_aabb_local_max_m": [float(value) for value in local_max.tolist()],
            "cooked_volume_m3": float(collider["volume_m3"]),
            "cooked_aabb_volume_m3": float(np.prod(local_max - local_min)),
            "world_aabb_min_m": [float(value) for value in world_box["world_min_m"].tolist()],
            "world_aabb_max_m": [float(value) for value in world_box["world_max_m"].tolist()],
        }

    filtered_pairs = set()
    for prim in Usd.PrimRange.Stage(stage):
        if not prim.HasAPI(UsdPhysics.FilteredPairsAPI):
            continue
        left = str(prim.GetPath())
        relation = UsdPhysics.FilteredPairsAPI(prim).GetFilteredPairsRel()
        for target in relation.GetTargets():
            right = str(target)
            if (
                (_path_covers(left, link0_path) and _path_covers(right, table_path))
                or (_path_covers(left, table_path) and _path_covers(right, link0_path))
            ):
                filtered_pairs.add(tuple(sorted((left, right))))
    return {
        "schema_version": 1,
        "authority": static_screen.LINK0_TABLE_GEOMETRY_AUDIT_AUTHORITY,
        "pair": expected_paths,
        "authored_filtered_pair_paths": [list(pair) for pair in sorted(filtered_pairs)],
        "colliders": [collider_record(path) for path in expected_paths],
    }


def _mesh_world_vertices_and_triangles(
    *,
    np: Any,
    UsdGeom: Any,
    stage: Any,
    path: str,
    world_matrix: Any,
) -> tuple[Any, Any]:
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid() or prim.GetTypeName() != "Mesh":
        raise RuntimeError("formal_snapshot_static_mounting_mesh_invalid")
    mesh = UsdGeom.Mesh(prim)
    points = mesh.GetPointsAttr().Get()
    face_counts = mesh.GetFaceVertexCountsAttr().Get()
    face_indices = mesh.GetFaceVertexIndicesAttr().Get()
    if points is None or face_counts is None or face_indices is None:
        raise RuntimeError("formal_snapshot_static_mounting_mesh_topology_missing")
    local_points = np.asarray(
        [[float(point[0]), float(point[1]), float(point[2]), 1.0] for point in points],
        dtype=np.float64,
    )
    matrix = np.asarray(world_matrix, dtype=np.float64)
    if (
        local_points.ndim != 2
        or local_points.shape[0] == 0
        or local_points.shape[1] != 4
        or matrix.shape != (4, 4)
        or not np.isfinite(local_points).all()
        or not np.isfinite(matrix).all()
    ):
        raise RuntimeError("formal_snapshot_static_mounting_mesh_points_invalid")
    indices = [int(index) for index in face_indices]
    counts = [int(count) for count in face_counts]
    if (
        not counts
        or any(count < 3 for count in counts)
        or sum(counts) != len(indices)
        or any(index < 0 or index >= local_points.shape[0] for index in indices)
    ):
        raise RuntimeError("formal_snapshot_static_mounting_mesh_topology_invalid")
    triangles = []
    offset = 0
    for count in counts:
        face = indices[offset : offset + count]
        triangles.extend((face[0], face[index], face[index + 1]) for index in range(1, count - 1))
        offset += count
    triangle_indices = np.asarray(triangles, dtype=np.int64)
    if triangle_indices.ndim != 2 or triangle_indices.shape[0] == 0 or triangle_indices.shape[1] != 3:
        raise RuntimeError("formal_snapshot_static_mounting_mesh_triangles_invalid")
    world_points = (local_points @ matrix)[:, :3]
    if not np.isfinite(world_points).all():
        raise RuntimeError("formal_snapshot_static_mounting_mesh_transform_invalid")
    return world_points, triangle_indices


def _vertical_table_top_z(
    *,
    np: Any,
    table_world_points: Any,
    table_triangles: Any,
    xy: Any,
) -> float:
    triangles = table_world_points[table_triangles]
    first = triangles[:, 0, :]
    second = triangles[:, 1, :]
    third = triangles[:, 2, :]
    edge_first = second[:, :2] - first[:, :2]
    edge_second = third[:, :2] - first[:, :2]
    determinant = edge_first[:, 0] * edge_second[:, 1] - edge_first[:, 1] * edge_second[:, 0]
    nonvertical = np.abs(determinant) > 1.0e-12
    relative = np.asarray(xy, dtype=np.float64) - first[:, :2]
    first_weight = (
        relative[:, 0] * edge_second[:, 1] - relative[:, 1] * edge_second[:, 0]
    ) / np.where(nonvertical, determinant, 1.0)
    second_weight = (
        edge_first[:, 0] * relative[:, 1] - edge_first[:, 1] * relative[:, 0]
    ) / np.where(nonvertical, determinant, 1.0)
    third_weight = 1.0 - first_weight - second_weight
    inside = (
        nonvertical
        & (first_weight >= -1.0e-9)
        & (second_weight >= -1.0e-9)
        & (third_weight >= -1.0e-9)
    )
    top_values = (
        first[:, 2] * third_weight
        + second[:, 2] * first_weight
        + third[:, 2] * second_weight
    )[inside]
    if top_values.size == 0 or not np.isfinite(top_values).all():
        raise RuntimeError("formal_snapshot_static_mounting_support_surface_missing")
    return float(np.max(top_values))


def _link0_table_mounting_alignment(
    *,
    np: Any,
    legacy: Any,
    Usd: Any,
    UsdGeom: Any,
    stage: Any,
    config: Mapping[str, Any],
    robot_world_matrices: Mapping[str, Any],
) -> dict[str, Any]:
    link0_path = static_screen.LINK0_COLLIDER_PATH
    table_path = static_screen.TABLE_COLLIDER_PATH
    diagnostic = config.get("diagnostic")
    robot_config = config.get("robot")
    if (
        not isinstance(diagnostic, Mapping)
        or not isinstance(robot_config, Mapping)
        or link0_path not in robot_world_matrices
    ):
        raise RuntimeError("formal_snapshot_static_mounting_config_invalid")
    configured_position = np.asarray(robot_config.get("position"), dtype=np.float64)
    clearance = diagnostic.get("minimum_noncontact_clearance_m")
    if (
        configured_position.shape != (3,)
        or not np.isfinite(configured_position).all()
        or isinstance(clearance, bool)
        or not isinstance(clearance, (int, float))
        or not math.isfinite(float(clearance))
        or float(clearance) < 0.0
    ):
        raise RuntimeError("formal_snapshot_static_mounting_config_invalid")
    link0_matrix = np.asarray(robot_world_matrices[link0_path], dtype=np.float64)
    if (
        link0_matrix.shape != (4, 4)
        or not np.isfinite(link0_matrix).all()
        or not np.allclose(link0_matrix[:, 3], [0.0, 0.0, 0.0, 1.0], rtol=0.0, atol=1.0e-12)
    ):
        raise RuntimeError("formal_snapshot_static_mounting_link0_matrix_invalid")
    link0_points, _link0_triangles = _mesh_world_vertices_and_triangles(
        np=np,
        UsdGeom=UsdGeom,
        stage=stage,
        path=link0_path,
        world_matrix=link0_matrix,
    )
    table_points, table_triangles = _mesh_world_vertices_and_triangles(
        np=np,
        UsdGeom=UsdGeom,
        stage=stage,
        path=table_path,
        world_matrix=legacy._world_matrix(np, Usd, UsdGeom, stage, table_path),
    )
    low_xy = link0_points[:, :2].min(axis=0)
    high_xy = link0_points[:, :2].max(axis=0)
    if np.any(high_xy <= low_xy):
        raise RuntimeError("formal_snapshot_static_mounting_link0_footprint_invalid")
    samples = []
    for x in np.linspace(low_xy[0], high_xy[0], 5):
        for y in np.linspace(low_xy[1], high_xy[1], 5):
            xy = [float(x), float(y)]
            samples.append(
                {"xy_m": xy, "top_z_m": _vertical_table_top_z(
                    np=np,
                    table_world_points=table_points,
                    table_triangles=table_triangles,
                    xy=xy,
                )}
            )
    return {
        "schema_version": 1,
        "authority": static_screen.LINK0_TABLE_MOUNTING_ALIGNMENT_AUTHORITY,
        "pair": sorted([link0_path, table_path]),
        "configured_robot_position_m": [float(value) for value in configured_position.tolist()],
        "observed_link0_collider_origin_m": [float(value) for value in link0_matrix[3, :3].tolist()],
        "link0_authored_mesh_world_bottom_z_m": float(link0_points[:, 2].min()),
        "link0_authored_mesh_world_xy_bounds_m": [
            float(low_xy[0]),
            float(low_xy[1]),
            float(high_xy[0]),
            float(high_xy[1]),
        ],
        "link0_mesh_point_count": int(link0_points.shape[0]),
        "table_mesh_triangle_count": int(table_triangles.shape[0]),
        "table_support_samples": samples,
        "required_clearance_m": float(clearance),
    }


def _validate_source_closure_against_fresh_stage(
    *,
    np: Any,
    legacy: Any,
    Usd: Any,
    UsdGeom: Any,
    UsdPhysics: Any,
    stage: Any,
    handoff: Mapping[str, Any],
    source_mesh: Sequence[str],
    source_wrapper: Sequence[str],
) -> dict[str, Any]:
    closure = handoff["source_collider_closure"]
    colliders = closure["colliders"]
    expected_paths = sorted([*source_mesh, *source_wrapper])
    root_paths = legacy._enabled_colliders(
        Usd, UsdPhysics, stage, legacy.SOURCE_ROOT_PATH
    )
    records = {record["path"]: record for record in colliders}
    if (
        len(records) != len(colliders)
        or sorted(records) != expected_paths
        or root_paths != expected_paths
        or closure["source_root_path"] != legacy.SOURCE_ROOT_PATH
    ):
        raise RuntimeError("formal_snapshot_static_source_inventory_invalid")
    source_world_matrices = {}
    for path in expected_paths:
        record = records[path]
        prim = stage.GetPrimAtPath(path)
        enabled = (
            UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
            if prim and prim.IsValid()
            else False
        )
        if enabled is False or legacy._nearest_rigid_owner(UsdPhysics, stage, path) != legacy.SOURCE_ROOT_PATH:
            raise RuntimeError("formal_snapshot_static_source_owner_invalid")
        fresh_relative = legacy._relative_matrix(
            np,
            Usd,
            UsdGeom,
            stage,
            child_path=path,
            owner_path=legacy.SOURCE_ROOT_PATH,
        )
        recorded_relative = np.asarray(
            record["collider_to_source_root_row_major"], dtype=np.float64
        ).reshape(4, 4)
        matrix = np.asarray(record["composed_world_matrix_row_major"], dtype=np.float64).reshape(4, 4)
        if (
            matrix.shape != (4, 4)
            or not np.isfinite(matrix).all()
            or not np.allclose(
                fresh_relative, recorded_relative, rtol=0.0, atol=1.0e-10
            )
        ):
            raise RuntimeError("formal_snapshot_static_source_relative_drift")
        source_world_matrices[path] = matrix
    return source_world_matrices


def run_formal_precontact_snapshot_static_screen(
    *,
    app: Any,
    out_dir: Path,
    frozen_config: Mapping[str, Any],
    contract: Mapping[str, Any],
    runtime: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    """Project one sealed event-0 target without post-reset simulator advancement."""
    if (
        not isinstance(frozen_config, Mapping)
        or not isinstance(contract, Mapping)
        or not isinstance(runtime, Mapping)
        or contract.get("authority") != AUTHORITY
        or contract.get("classification") != CLASSIFICATION
        or contract.get("post_reset_physics_steps_allowed") != 0
        or contract.get("g0_or_gate_authorized") is not False
    ):
        raise RuntimeError("formal_snapshot_static_runtime_contract_invalid")
    normalized_handoff = static_screen.normalize_static_handoff(handoff)
    if normalized_handoff["sha256"] != contract.get("handoff_sha256"):
        raise RuntimeError("formal_snapshot_static_handoff_binding_invalid")
    formal_contract = normalized_handoff["formal_contract"]
    fixed_mount = formal_contract.get("authority") == snapshot_replay.FIXED_MOUNT_AUTHORITY
    fixed_mount_profile = None
    if fixed_mount:
        try:
            fixed_mount_profile = snapshot_replay.validate_fixed_mount_profile(
                formal_contract.get("fixed_mount_profile")
            )
        except ValueError as exc:
            raise RuntimeError("formal_snapshot_static_fixed_mount_profile_invalid") from exc
        if (
            contract.get("fixed_mount_profile_sha256")
            != fixed_mount_profile["profile_sha256"]
            or "fixed_mount_filter" not in normalized_handoff
        ):
            raise RuntimeError("formal_snapshot_static_fixed_mount_binding_invalid")
    elif "fixed_mount_profile_sha256" in contract:
        raise RuntimeError("formal_snapshot_static_fixed_mount_binding_invalid")
    for field in (
        "v7_config_sha256",
        "local_scene_sha256",
        "local_franka_sha256",
        "hidden_cube_overlay_sha256",
    ):
        if formal_contract.get(field) != contract.get(field):
            raise RuntimeError("formal_snapshot_static_fixture_binding_invalid")

    from isaacsim_compat import install_legacy_isaacsim_aliases

    install_legacy_isaacsim_aliases()
    import numpy as np
    import omni.physx
    import omni.timeline
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.utils.stage import add_reference_to_stage
    from pxr import Sdf, Usd, UsdGeom, UsdPhysics
    from scipy.spatial.transform import Rotation

    from factories.robot_factory import create_robot
    from tools.labutopia_fluid import formal_precontact_event0_replay_runtime as formal_runtime
    from tools.labutopia_fluid import nonformal_controller_static_collision_screen_runtime as legacy
    from tools.labutopia_fluid import run_native_expert_empty_beaker_unbound_lift_probe as native
    from tools.labutopia_fluid import run_real_pbd_grasp_v2_g0_geometry as g0_geometry

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
        raise RuntimeError("formal_snapshot_static_frozen_binding_invalid")
    runtime_config = config
    if fixed_mount:
        if fixed_mount_profile is None:
            raise RuntimeError("formal_snapshot_static_fixed_mount_profile_missing")
        runtime_config = copy.deepcopy(dict(config))
        runtime_config["robot"]["position"] = list(fixed_mount_profile["robot_position_m"])
    overlay = diagnostic.get("hidden_cube_treatment")
    if not isinstance(overlay, Mapping):
        raise RuntimeError("formal_snapshot_static_hidden_cube_missing")
    overlay_path = Path(native.REPO_ROOT / str(overlay.get("usd_path", ""))).resolve()
    if (
        not overlay_path.is_file()
        or _sha256_file(overlay_path) != contract.get("hidden_cube_overlay_sha256")
    ):
        raise RuntimeError("formal_snapshot_static_hidden_cube_binding_invalid")

    world = None
    try:
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("formal_snapshot_static_stage_missing")
        add_reference_to_stage(usd_path=str(local_scene["absolute_usd_path"]), prim_path="/World")
        robot = native.create_diagnostic_local_franka(
            create_robot, runtime_config, local_franka=local_franka
        )
        app.update()
        app.update()
        session = stage.GetSessionLayer()
        if session is None:
            raise RuntimeError("formal_snapshot_static_session_layer_missing")
        if str(overlay_path) not in session.subLayerPaths:
            session.subLayerPaths.append(str(overlay_path))
        fresh_fixed_mount_filter = None
        if fixed_mount:
            if fixed_mount_profile is None:
                raise RuntimeError("formal_snapshot_static_fixed_mount_profile_missing")
            filter_overlay_path = Path(
                native.REPO_ROOT / fixed_mount_profile["filter"]["overlay_path"]
            ).resolve()
            if (
                not filter_overlay_path.is_file()
                or _sha256_file(filter_overlay_path)
                != fixed_mount_profile["filter"]["overlay_sha256"]
            ):
                raise RuntimeError("formal_snapshot_static_fixed_mount_overlay_binding_invalid")
            if str(filter_overlay_path) not in session.subLayerPaths:
                session.subLayerPaths.append(str(filter_overlay_path))
        app.update()
        app.update()
        if fixed_mount:
            if fixed_mount_profile is None:
                raise RuntimeError("formal_snapshot_static_fixed_mount_profile_missing")
            fresh_fixed_mount_filter = formal_runtime._fixed_mount_filter_record(
                Usd=Usd,
                UsdPhysics=UsdPhysics,
                stage=stage,
                profile=fixed_mount_profile,
            )
            if fresh_fixed_mount_filter != normalized_handoff["fixed_mount_filter"]:
                raise RuntimeError("formal_snapshot_static_fixed_mount_filter_drift")
        timeline = omni.timeline.get_timeline_interface()
        pre_reset = legacy._stopped_receipt(timeline)
        if pre_reset["is_playing"] or not pre_reset["is_stopped"]:
            raise RuntimeError("formal_snapshot_static_pre_reset_timeline_invalid")
        source_mesh = legacy._enabled_colliders(Usd, UsdPhysics, stage, legacy.SOURCE_MESH_PATH)
        source_wrapper = legacy._enabled_colliders(Usd, UsdPhysics, stage, legacy.WRAPPER_ROOT_PATH)
        table = legacy._enabled_colliders(Usd, UsdPhysics, stage, legacy.TABLE_PATH)
        beaker1 = legacy._enabled_colliders(Usd, UsdPhysics, stage, legacy.BEAKER1_PATH)
        robot_colliders = legacy._enabled_colliders(Usd, UsdPhysics, stage, legacy.ROBOT_ROOT_PATH)
        left_fingers = legacy._enabled_colliders(
            Usd, UsdPhysics, stage, "/World/Franka/panda_leftfinger"
        )
        right_fingers = legacy._enabled_colliders(
            Usd, UsdPhysics, stage, "/World/Franka/panda_rightfinger"
        )
        inventory = {
            "source_mesh": len(source_mesh),
            "source_wrapper": len(source_wrapper),
            "table": len(table),
            "beaker1": len(beaker1),
            "full_robot": len(robot_colliders),
        }
        if (
            inventory != contract.get("expected_collider_inventory")
            or source_mesh != [legacy.SOURCE_MESH_PATH]
            or table != [legacy.TABLE_PATH]
            or len(left_fingers) != 1
            or len(right_fingers) != 1
        ):
            raise RuntimeError("formal_snapshot_static_collider_inventory_invalid")
        source_world_matrices = _validate_source_closure_against_fresh_stage(
            np=np,
            legacy=legacy,
            Usd=Usd,
            UsdGeom=UsdGeom,
            UsdPhysics=UsdPhysics,
            stage=stage,
            handoff=normalized_handoff,
            source_mesh=source_mesh,
            source_wrapper=source_wrapper,
        )
        role_paths = {
            "source_external_shell_paths": source_mesh,
            "source_internal_wrapper_paths": source_wrapper,
            "support_collider_paths": table,
            "beaker1_collider_paths": beaker1,
            "full_robot_collider_paths": robot_colliders,
            "hand_collider_paths": legacy._enabled_colliders(
                Usd, UsdPhysics, stage, "/World/Franka/panda_hand"
            ),
            "finger_pad_collider_paths": {"left": left_fingers, "right": right_fingers},
        }
        full_scope = g0_geometry.build_full_robot_static_collision_scope(role_paths)
        if (
            len(full_scope["blocking_pairs"]) != 3210
            or len(full_scope["allowed_source_shell_pairs"]) != 2
        ):
            raise RuntimeError("formal_snapshot_static_collision_scope_invalid")
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
        catalog = legacy._collect_cooked_catalog(
            app=app,
            np=np,
            Sdf=Sdf,
            Usd=Usd,
            UsdPhysics=UsdPhysics,
            stage=stage,
            timeline=timeline,
            world=None,
            baseline=pre_reset,
            required_paths=required_paths,
        )
        legacy._require_query_timeline_unchanged(
            None, timeline, pre_reset, context="formal_snapshot_static_catalog_complete"
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
        reset_before = legacy._runtime_receipt(world, timeline)
        world.reset()
        reset_after = legacy._runtime_receipt(world, timeline)
        physics_view = world.physics_sim_view
        if physics_view is None:
            raise RuntimeError("formal_snapshot_static_tensor_view_missing")
        robot.initialize(physics_sim_view=physics_view)
        initialized = legacy._runtime_receipt(world, timeline)
        if (
            initialized["world_index"] != reset_after["world_index"]
            or initialized["timeline_time_s"] != reset_after["timeline_time_s"]
        ):
            raise RuntimeError("formal_snapshot_static_robot_initialization_advanced")
        baseline = legacy._pause_after_reset(
            app, world, timeline, post_reset_receipt=initialized
        )
        robot_kinematics = legacy._robot_kinematic_model(
            np=np,
            Rotation=Rotation,
            Usd=Usd,
            UsdGeom=UsdGeom,
            UsdPhysics=UsdPhysics,
            stage=stage,
            robot=robot,
            expected_simulation_view=physics_view,
            collider_paths=full_scope["full_robot_collider_paths"],
        )
        lower, upper = legacy._joint_position_limits(np, robot)
        margin = contract.get("aabb_numerical_margin_m")
        if (
            isinstance(margin, bool)
            or not isinstance(margin, (int, float))
            or not math.isfinite(float(margin))
            or float(margin) < 0.0
        ):
            raise RuntimeError("formal_snapshot_static_margin_invalid")
        baseline_robot_world_matrices = legacy._robot_collider_world_matrices(
            np, Rotation, robot_kinematics
        )
        baseline_link0_pair, baseline_link0_matrix, baseline_axis_signed_separation = _link0_table_pair_result(
            np=np,
            legacy=legacy,
            Usd=Usd,
            UsdGeom=UsdGeom,
            stage=stage,
            catalog=catalog,
            robot_world_matrices=baseline_robot_world_matrices,
            numerical_margin_m=float(margin),
        )
        geometry_audit = _link0_table_geometry_audit(
            np=np,
            legacy=legacy,
            Usd=Usd,
            UsdGeom=UsdGeom,
            UsdPhysics=UsdPhysics,
            stage=stage,
            catalog=catalog,
            robot_world_matrices=baseline_robot_world_matrices,
        )
        geometry_evaluation = static_screen.evaluate_link0_table_geometry_audit(geometry_audit)
        if geometry_evaluation["decision"] == static_screen.SAFETY_ABORT:
            raise RuntimeError(
                "formal_snapshot_static_geometry_audit_invalid:"
                f"{geometry_evaluation['validation_error']}"
            )
        mounting_alignment = _link0_table_mounting_alignment(
            np=np,
            legacy=legacy,
            Usd=Usd,
            UsdGeom=UsdGeom,
            stage=stage,
            config=runtime_config,
            robot_world_matrices=baseline_robot_world_matrices,
        )
        mounting_evaluation = static_screen.evaluate_link0_table_mounting_alignment(
            mounting_alignment
        )
        if mounting_evaluation["decision"] == static_screen.SAFETY_ABORT:
            raise RuntimeError(
                "formal_snapshot_static_mounting_alignment_invalid:"
                f"{mounting_evaluation['validation_error']}"
            )
        if fixed_mount and (
            mounting_evaluation["decision"]
            != static_screen.LINK0_TABLE_MOUNTING_SURFACE_TOUCH
            or mounting_evaluation["table_support_top_z_spread_m"] > 1.0e-6
        ):
            raise RuntimeError("formal_snapshot_static_fixed_mount_alignment_invalid")
        source_matrix_before = legacy._world_matrix(
            np, Usd, UsdGeom, stage, legacy.SOURCE_ROOT_PATH
        )
        event0 = normalized_handoff["event0"]
        joint_readback, _source_matrix_after, robot_world_matrices = legacy._materialize_configuration(
            np=np,
            Rotation=Rotation,
            Usd=Usd,
            UsdGeom=UsdGeom,
            stage=stage,
            robot=robot,
            robot_kinematics=robot_kinematics,
            source_matrix_before=source_matrix_before,
            world=world,
            timeline=timeline,
            baseline=baseline,
            target_positions=event0["resolved_position_target"],
            joint_lower_limits=lower,
            joint_upper_limits=upper,
            is_hold=False,
        )
        event0_link0_pair, event0_link0_matrix, event0_axis_signed_separation = _link0_table_pair_result(
            np=np,
            legacy=legacy,
            Usd=Usd,
            UsdGeom=UsdGeom,
            stage=stage,
            catalog=catalog,
            robot_world_matrices=robot_world_matrices,
            numerical_margin_m=float(margin),
        )
        baseline_comparison = {
            "schema_version": 1,
            "authority": static_screen.BASELINE_COMPARISON_AUTHORITY,
            "pair": baseline_link0_pair["pair"],
            "aabb_numerical_margin_m": float(margin),
            "baseline_lower_bound_m": baseline_link0_pair["lower_bound_m"],
            "event0_lower_bound_m": event0_link0_pair["lower_bound_m"],
            "axis_signed_separation_m": baseline_axis_signed_separation,
            "baseline_link0_collider_world_matrix": baseline_link0_matrix,
            "event0_link0_collider_world_matrix": event0_link0_matrix,
        }
        baseline_evaluation = static_screen.evaluate_fixed_mount_baseline_comparison(
            baseline_comparison
        )
        if not np.allclose(
            np.asarray(baseline_axis_signed_separation, dtype=np.float64),
            np.asarray(event0_axis_signed_separation, dtype=np.float64),
            rtol=0.0,
            atol=1.0e-10,
        ):
            raise RuntimeError("formal_snapshot_static_link0_table_axis_drift")
        if baseline_evaluation["decision"] == static_screen.SAFETY_ABORT:
            raise RuntimeError(
                "formal_snapshot_static_baseline_comparison_invalid:"
                f"{baseline_evaluation['validation_error']}"
            )
        full_screen_scope = {
            "blocking_pairs": full_scope["blocking_pairs"],
            "allowed_source_shell_pairs": full_scope["allowed_source_shell_pairs"],
        }
        active_screen_scope = None
        if fixed_mount:
            if fixed_mount_profile is None or fresh_fixed_mount_filter is None:
                raise RuntimeError("formal_snapshot_static_fixed_mount_filter_missing")
            active_screen_scope = static_screen.build_fixed_mount_filtered_screen_scope(
                full_screen_scope,
                fixed_mount_profile=fixed_mount_profile,
                fixed_mount_filter=fresh_fixed_mount_filter,
            )
            scope = {
                "blocking_pairs": active_screen_scope["blocking_pairs"],
                "allowed_source_shell_pairs": active_screen_scope[
                    "allowed_source_shell_pairs"
                ],
            }
        else:
            scope = full_screen_scope
        projection = {
            "schema_version": 1,
            "authority": static_screen.PROJECTION_AUTHORITY,
            "controller_event": 0,
            "resolved_position_target": joint_readback,
            "resolved_position_target_sha256": static_screen.canonical_json_sha256(joint_readback),
            "source_collider_closure_sha256": normalized_handoff["source_collider_closure"]["sha256"],
            "aabb_numerical_margin_m": float(margin),
            "pair_results": _screen_pair_results(
                np=np,
                legacy=legacy,
                Usd=Usd,
                UsdGeom=UsdGeom,
                stage=stage,
                catalog=catalog,
                scope=scope,
                numerical_margin_m=float(margin),
                robot_world_matrices=robot_world_matrices,
                source_world_matrices=source_world_matrices,
            ),
        }
        if (
            projection["resolved_position_target_sha256"]
            != event0["resolved_position_target_sha256"]
        ):
            raise RuntimeError("formal_snapshot_static_joint_target_drift")
        projection_link0 = next(
            (
                result
                for result in projection["pair_results"]
                if result["pair"] == event0_link0_pair["pair"]
            ),
            None,
        )
        if fixed_mount:
            if projection_link0 is not None:
                raise RuntimeError("formal_snapshot_static_fixed_mount_pair_not_excluded")
        elif (
            projection_link0 != {
                "pair": event0_link0_pair["pair"],
                "classification": "BLOCKING",
                "status": event0_link0_pair["status"],
                "lower_bound_m": event0_link0_pair["lower_bound_m"],
            }
        ):
            raise RuntimeError("formal_snapshot_static_link0_table_projection_drift")
        evaluation = static_screen.evaluate_event0_static_projection(scope, projection)
        if evaluation["decision"] == static_screen.SAFETY_ABORT:
            raise RuntimeError(f"formal_snapshot_static_projection_invalid:{evaluation['validation_error']}")
        projection_path = out_dir / PROJECTION_NAME
        _write_create_only(projection_path, projection)
        final = legacy._require_paused_unchanged(
            world, timeline, baseline, context="formal_snapshot_static_complete"
        )
        return {
            "schema_version": 1,
            "manifest_type": "formal_precontact_snapshot_static_screen_child_v1",
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "decision": evaluation["decision"],
            "contract": dict(contract),
            "runtime": dict(runtime),
            "scope": {
                "event0_only": True,
                "controller_forwarded": False,
                "event0_action_applied_in_static": False,
                "robot_pose_injection": "paused_direct_joint_positions_with_readback",
                "event0_integrated": False,
                "source_pose_materialized": False,
                "source_collider_matrices": "formal_v2_analytic_override_only",
                "link0_table_baseline_comparison": baseline_evaluation["decision"],
                "link0_table_geometry_audit": geometry_evaluation["decision"],
                "link0_table_mounting_alignment": mounting_evaluation["decision"],
                "fixed_mount_filter_applied": fixed_mount,
                "attachment": False,
                "close": False,
                "lift": False,
                "contact_observer": False,
                "g0_or_gate_evaluated": False,
                "post_reset_physics_steps_allowed": 0,
                "post_reset_physics_advance": {
                    "world_index_delta": final["world_index"] - initialized["world_index"],
                    "timeline_time_delta_s": final["timeline_time_s"] - initialized["timeline_time_s"],
                    "verified_zero": final == baseline,
                },
            },
            "timeline": {
                "pre_reset_cooked_query": pre_reset,
                "before_reset": reset_before,
                "after_reset": reset_after,
                "after_robot_initialization": initialized,
                "baseline": baseline,
                "final": final,
                "unchanged": final == baseline,
            },
            "handoff": {
                "sha256": normalized_handoff["sha256"],
                "formal_contract_sha256": normalized_handoff["formal_contract_sha256"],
                "formal_provenance": normalized_handoff["formal_provenance"],
                "event0_resolved_position_target_sha256": event0[
                    "resolved_position_target_sha256"
                ],
                "source_collider_closure_sha256": normalized_handoff[
                    "source_collider_closure"
                ]["sha256"],
                "fixed_mount_filter": (
                    normalized_handoff.get("fixed_mount_filter") if fixed_mount else None
                ),
            },
            "collision_scope": full_scope,
            "active_screen_scope": active_screen_scope,
            "fixed_mount_filter": fresh_fixed_mount_filter,
            "projection": {
                "path": projection_path.name,
                "sha256": _sha256_file(projection_path),
                "evaluation": evaluation,
            },
            "baseline_comparison": {
                "record": baseline_comparison,
                "evaluation": baseline_evaluation,
            },
            "geometry_audit": {
                "record": geometry_audit,
                "evaluation": geometry_evaluation,
            },
            "mounting_alignment": {
                "record": mounting_alignment,
                "evaluation": mounting_evaluation,
            },
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        clear_instance = getattr(World, "clear_instance", None)
        if callable(clear_instance):
            clear_instance()
