#!/usr/bin/env python3
"""Measure real-contact grasp prerequisites without approaching or lifting."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CONFIG = REPO_ROOT / "config/level1_pour_online_fluid_contact_grasp_v1.yaml"


def _positive_number(value: Any, *, name: str, allow_zero: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
        or (float(value) < 0.0 if allow_zero else float(value) <= 0.0)
    ):
        raise ValueError(f"{name}_invalid")
    return float(value)


def summarize_pad_velocity_authority(
    samples: Sequence[Mapping[str, Any]],
    *,
    agreement_tolerance_m_s: float,
) -> dict[str, Any]:
    tolerance = _positive_number(
        agreement_tolerance_m_s,
        name="velocity_agreement_tolerance_m_s",
    )
    if not isinstance(samples, Sequence) or not samples:
        raise ValueError("velocity_samples_required")
    errors = []
    nonzero = 0
    maximum_api_speed = 0.0
    maximum_finite_difference_speed = 0.0
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise TypeError("velocity_sample_mapping_required")
        api = np.asarray(sample.get("api_pad_velocity_m_s"), dtype=np.float64)
        finite_difference = np.asarray(
            sample.get("finite_difference_pad_velocity_m_s"),
            dtype=np.float64,
        )
        if (
            api.shape != (2,)
            or finite_difference.shape != (2,)
            or not np.isfinite(api).all()
            or not np.isfinite(finite_difference).all()
        ):
            raise ValueError("velocity_sample_values_invalid")
        errors.extend(np.abs(api - finite_difference).tolist())
        maximum_api_speed = max(maximum_api_speed, float(np.max(np.abs(api))))
        maximum_finite_difference_speed = max(
            maximum_finite_difference_speed,
            float(np.max(np.abs(finite_difference))),
        )
        if max(float(np.max(np.abs(api))), float(np.max(np.abs(finite_difference)))) > 1.0e-5:
            nonzero += 1
    maximum_error = max(errors)
    return {
        "sample_count": len(samples),
        "nonzero_sample_count": nonzero,
        "agreement_tolerance_m_s": tolerance,
        "maximum_absolute_error_m_s": maximum_error,
        "maximum_api_speed_m_s": maximum_api_speed,
        "maximum_finite_difference_speed_m_s": (
            maximum_finite_difference_speed
        ),
        "passed": bool(nonzero > 0 and maximum_error <= tolerance),
    }


def derive_effective_payload_mass_from_support(
    *,
    support_impulses_n_s: Sequence[float],
    physics_dt: float,
    gravity_m_s2: float,
    minimum_samples: int,
) -> dict[str, Any]:
    dt = _positive_number(physics_dt, name="support_physics_dt")
    gravity = _positive_number(gravity_m_s2, name="support_gravity_m_s2")
    if type(minimum_samples) is not int or minimum_samples <= 0:
        raise ValueError("support_minimum_samples_invalid")
    impulses = np.asarray(support_impulses_n_s, dtype=np.float64)
    if impulses.ndim != 1 or not np.isfinite(impulses).all() or np.any(impulses <= 0.0):
        raise ValueError("support_impulse_samples_invalid")
    if len(impulses) < minimum_samples:
        raise ValueError("support_impulse_sample_count_insufficient")
    median = float(np.median(impulses))
    p05, p95 = np.percentile(impulses, [5.0, 95.0])
    relative_spread = float((p95 - p05) / median)
    mass = median / (gravity * dt)
    return {
        "sample_count": int(len(impulses)),
        "minimum_samples": minimum_samples,
        "median_support_impulse_n_s": median,
        "p05_support_impulse_n_s": float(p05),
        "p95_support_impulse_n_s": float(p95),
        "relative_p05_p95_spread": relative_spread,
        "physics_dt": dt,
        "gravity_m_s2": gravity,
        "effective_payload_mass_kg": mass,
        "passed": bool(mass > 0.0 and relative_spread <= 0.20),
    }


def evaluate_symmetric_open_clearance(
    *,
    open_inner_gap_m: float,
    source_width_m: float,
    source_contact_offset_m: float,
    finger_contact_offset_m: float,
    tracking_error_m: float,
    numerical_margin_m: float,
) -> dict[str, Any]:
    gap = _positive_number(open_inner_gap_m, name="clearance_open_inner_gap_m")
    width = _positive_number(source_width_m, name="clearance_source_width_m")
    source_offset = _positive_number(
        source_contact_offset_m,
        name="clearance_source_contact_offset_m",
        allow_zero=True,
    )
    finger_offset = _positive_number(
        finger_contact_offset_m,
        name="clearance_finger_contact_offset_m",
        allow_zero=True,
    )
    tracking_error = _positive_number(
        tracking_error_m,
        name="clearance_tracking_error_m",
        allow_zero=True,
    )
    margin = _positive_number(
        numerical_margin_m,
        name="clearance_numerical_margin_m",
    )
    per_side = (gap - width) / 2.0
    required = source_offset + finger_offset + tracking_error + margin
    return {
        "open_inner_gap_m": gap,
        "source_width_m": width,
        "per_side_open_clearance_m": per_side,
        "source_contact_offset_m": source_offset,
        "finger_contact_offset_m": finger_offset,
        "tracking_error_m": tracking_error,
        "numerical_margin_m": margin,
        "required_per_side_clearance_m": required,
        "passed": bool(per_side > required),
    }


def summarize_pre_sweep_clearance(
    *,
    open_inner_gap_m: float,
    source_widths_m: Sequence[float],
    source_contact_offset_m: float | None,
    finger_contact_offsets_m: Sequence[float | None],
    controller_tracking_error_m: float | None,
    numerical_margin_m: float,
) -> dict[str, Any]:
    widths = tuple(
        _positive_number(value, name="clearance_source_width_m")
        for value in source_widths_m
    )
    if not widths:
        raise ValueError("clearance_source_widths_required")
    if len(finger_contact_offsets_m) != 2:
        raise ValueError("clearance_finger_contact_offsets_required")

    unknown_terms = []
    if source_contact_offset_m is None:
        source_offset = 0.0
        unknown_terms.append("source_contact_offset_m")
    else:
        source_offset = _positive_number(
            source_contact_offset_m,
            name="clearance_source_contact_offset_m",
            allow_zero=True,
        )
    if any(value is None for value in finger_contact_offsets_m):
        finger_offset = 0.0
        unknown_terms.append("finger_contact_offset_m")
    else:
        finger_offset = max(
            _positive_number(
                value,
                name="clearance_finger_contact_offset_m",
                allow_zero=True,
            )
            for value in finger_contact_offsets_m
        )
    if controller_tracking_error_m is None:
        tracking_error = 0.0
        unknown_terms.append("controller_tracking_error_m")
    else:
        tracking_error = _positive_number(
            controller_tracking_error_m,
            name="clearance_tracking_error_m",
            allow_zero=True,
        )

    records = []
    for width in widths:
        record = evaluate_symmetric_open_clearance(
            open_inner_gap_m=open_inner_gap_m,
            source_width_m=width,
            source_contact_offset_m=source_offset,
            finger_contact_offset_m=finger_offset,
            tracking_error_m=tracking_error,
            numerical_margin_m=numerical_margin_m,
        )
        optimistic_passed = bool(record["passed"])
        record["optimistic_passed"] = optimistic_passed
        record["optimistic_remaining_margin_m"] = (
            record["per_side_open_clearance_m"]
            - record["required_per_side_clearance_m"]
        )
        record["passed"] = bool(not unknown_terms and optimistic_passed)
        records.append(record)
    margins = [record["optimistic_remaining_margin_m"] for record in records]
    return {
        "measurement_complete": not unknown_terms,
        "unknown_budget_terms": unknown_terms,
        "records": records,
        "minimum_optimistic_remaining_margin_m": min(margins),
        "maximum_optimistic_remaining_margin_m": max(margins),
        "passed": bool(not unknown_terms and any(record["passed"] for record in records)),
    }


def evaluate_probe_prerequisites(report: Mapping[str, Any]) -> dict[str, Any]:
    cooked = report.get("cooked_collider_probe", {})
    bodies = cooked.get("bodies", {}) if isinstance(cooked, Mapping) else {}
    checks = {
        "frame_probe": bool(report.get("frame_probe", {}).get("passed", False)),
        "velocity_probe": bool(
            report.get("velocity_probe", {}).get("passed", False)
        ),
        "support_load_probe": bool(
            report.get("support_load_probe", {}).get("passed", False)
        ),
    }
    for name in ("source", "left_finger", "right_finger", "hand", "table"):
        body = bodies.get(name, {}) if isinstance(bodies, Mapping) else {}
        checks[f"cooked_body_{name}"] = bool(
            isinstance(body, Mapping)
            and int(body.get("collider_count", 0)) > 0
            and body.get("colliders")
            and not body.get("rigid_body_error")
            and not body.get("collider_errors")
        )
    widths = (
        cooked.get("source_width_raycast", [])
        if isinstance(cooked, Mapping)
        else []
    )
    checks["source_width_raycast"] = bool(
        widths
        and any(
            isinstance(record, Mapping)
            and isinstance(record.get("source_width_y_m"), (int, float, np.number))
            and not isinstance(record.get("source_width_y_m"), bool)
            and math.isfinite(float(record["source_width_y_m"]))
            and float(record["source_width_y_m"]) > 0.0
            for record in widths
        )
    )
    checks["contact_offsets_resolved"] = bool(
        isinstance(cooked, Mapping)
        and cooked.get("unresolved_contact_offset_paths") == []
    )
    clearance = (
        cooked.get("pre_sweep_clearance", {})
        if isinstance(cooked, Mapping)
        else {}
    )
    checks["pre_sweep_clearance"] = bool(
        isinstance(clearance, Mapping)
        and clearance.get("measurement_complete") is True
        and clearance.get("passed") is True
    )
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return "Infinity" if value > 0.0 else "-Infinity" if value < 0.0 else "NaN"
    return value


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"probe_output_exists:{path}")
    payload = (
        json.dumps(
            _json_safe(value),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise FileExistsError(f"probe_output_exists:{path}")
        os.replace(temporary_path, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _runtime_error_report(exc: BaseException, *, phase: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "contact_grasp_feasibility_probe_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "runtime_error_pending_application_close",
        "shutdown_status": "pending",
        "measurement_decision": "PROBE_RUNTIME_ERROR",
        "fatal_error": {
            "phase": phase,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
    }


def _persist_provisional_before_shutdown(
    *,
    app: Any,
    output_path: Path,
    report: Mapping[str, Any],
) -> None:
    try:
        _atomic_write_json(output_path, report)
    finally:
        app.close()


def _finalize_child_report(
    provisional_report: Mapping[str, Any],
    *,
    child_returncode: int,
    child_command: Sequence[str],
) -> dict[str, Any]:
    final = dict(_json_safe(provisional_report))
    measurement_decision = str(
        final.get("measurement_decision", "PROBE_RUNTIME_ERROR")
    )
    final["pre_shutdown_decision"] = measurement_decision
    final["finalized_at_utc"] = datetime.now(timezone.utc).isoformat()
    final["child_process"] = {
        "command": list(child_command),
        "returncode": int(child_returncode),
    }
    if child_returncode == 0:
        final["shutdown_status"] = "child_exit_0"
        final["decision"] = measurement_decision
        final["lifecycle_status"] = (
            "failed"
            if measurement_decision == "PROBE_RUNTIME_ERROR"
            else "completed"
        )
        return final

    final["shutdown_status"] = "child_exit_nonzero"
    final["decision"] = "PROBE_RUNTIME_ERROR"
    final["lifecycle_status"] = "failed"
    final["shutdown_error"] = {
        "phase": "application_shutdown",
        "type": "ChildProcessExit",
        "message": f"probe_child_exit_{child_returncode}",
        "returncode": int(child_returncode),
    }
    return final


def _row_matrix(stage: Any, path: str) -> np.ndarray:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"probe_prim_missing:{path}")
    return np.asarray(
        UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()),
        dtype=np.float64,
    )


def row_world_matrix_from_lula_pose(
    *,
    position_world_m: Sequence[float],
    column_rotation_world: Sequence[Sequence[float]],
) -> np.ndarray:
    position = np.asarray(position_world_m, dtype=np.float64)
    rotation = np.asarray(column_rotation_world, dtype=np.float64)
    if (
        position.shape != (3,)
        or rotation.shape != (3, 3)
        or not np.isfinite(position).all()
        or not np.isfinite(rotation).all()
        or not np.allclose(
            rotation @ rotation.T,
            np.eye(3),
            rtol=0.0,
            atol=1.0e-8,
        )
        or not math.isclose(
            float(np.linalg.det(rotation)),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-8,
        )
    ):
        raise ValueError("probe_lula_world_pose_invalid")
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = rotation.T
    result[3, :3] = position
    return result


def derive_control_to_target_row_matrix(
    *,
    control_world_matrix: Sequence[Sequence[float]],
    target_world_matrix: Sequence[Sequence[float]],
) -> np.ndarray:
    control_world = np.asarray(control_world_matrix, dtype=np.float64)
    target_world = np.asarray(target_world_matrix, dtype=np.float64)
    if (
        control_world.shape != (4, 4)
        or target_world.shape != (4, 4)
        or not np.isfinite(control_world).all()
        or not np.isfinite(target_world).all()
    ):
        raise ValueError("probe_frame_world_matrix_invalid")
    return control_world @ np.linalg.inv(target_world)


def _configured_contact_offset(stage: Any, path: str) -> dict[str, Any]:
    from pxr import PhysxSchema

    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"probe_collider_missing:{path}")
    api = PhysxSchema.PhysxCollisionAPI(prim)
    contact = api.GetContactOffsetAttr().Get() if api else None
    rest = api.GetRestOffsetAttr().Get() if api else None
    contact_value = None
    if contact is not None and math.isfinite(float(contact)) and float(contact) >= 0.0:
        contact_value = float(contact)
    rest_value = None
    if rest is not None and math.isfinite(float(rest)):
        rest_value = float(rest)
    return {
        "path": path,
        "contact_offset_m": contact_value,
        "rest_offset_m": rest_value,
        "contact_offset_authority": (
            "authored" if contact_value is not None else "physx_autocomputed_unresolved"
        ),
    }


def _query_cooked_colliders(app: Any, stage: Any, body_path: str) -> dict[str, Any]:
    from omni.physx import get_physx_property_query_interface
    from omni.physx.bindings._physx import (
        PhysxPropertyQueryMode,
        PhysxPropertyQueryResult,
    )
    from pxr import PhysicsSchemaTools, UsdUtils

    body = stage.GetPrimAtPath(body_path)
    if not body or not body.IsValid():
        raise RuntimeError(f"probe_body_missing:{body_path}")
    result: dict[str, Any] = {"body_path": body_path, "colliders": []}
    finished = {"value": False}

    def rigid_body_callback(info):
        if info.result != PhysxPropertyQueryResult.VALID:
            result["rigid_body_error"] = str(info.result)
            return
        result.update(
            {
                "mass_kg": float(info.mass),
                "center_of_mass_local_m": list(info.center_of_mass),
                "diagonal_inertia_kg_m2": list(info.inertia),
            }
        )

    def collider_callback(info):
        if info.result != PhysxPropertyQueryResult.VALID:
            result.setdefault("collider_errors", []).append(str(info.result))
            return
        result["colliders"].append(
            {
                "path": str(PhysicsSchemaTools.intToSdfPath(info.path_id)),
                "aabb_local_min_m": list(info.aabb_local_min),
                "aabb_local_max_m": list(info.aabb_local_max),
                "volume_m3": float(info.volume),
            }
        )

    get_physx_property_query_interface().query_prim(
        stage_id=UsdUtils.StageCache.Get().Insert(stage).ToLongInt(),
        prim_id=PhysicsSchemaTools.sdfPathToInt(body.GetPath()),
        query_mode=PhysxPropertyQueryMode.QUERY_RIGID_BODY_WITH_COLLIDERS,
        rigid_body_fn=rigid_body_callback,
        collider_fn=collider_callback,
        finished_fn=lambda: finished.__setitem__("value", True),
        timeout_ms=60000,
    )
    for _ in range(600):
        if finished["value"]:
            break
        app.update()
    if not finished["value"]:
        raise RuntimeError(f"probe_property_query_timeout:{body_path}")
    result["colliders"].sort(key=lambda item: item["path"])
    result["collider_count"] = len(result["colliders"])
    return result


def _world_aabb_for_collider(stage: Any, collider: Mapping[str, Any]) -> dict[str, Any]:
    low = np.asarray(collider["aabb_local_min_m"], dtype=np.float64)
    high = np.asarray(collider["aabb_local_max_m"], dtype=np.float64)
    corners = np.asarray(
        [
            [x, y, z, 1.0]
            for x in (low[0], high[0])
            for y in (low[1], high[1])
            for z in (low[2], high[2])
        ],
        dtype=np.float64,
    )
    world = corners @ _row_matrix(stage, str(collider["path"]))
    return {
        "min_m": world[:, :3].min(axis=0).tolist(),
        "max_m": world[:, :3].max(axis=0).tolist(),
    }


def _finger_open_gap(
    stage: Any,
    left_query: Mapping[str, Any],
    right_query: Mapping[str, Any],
) -> dict[str, Any]:
    left_bounds = [
        _world_aabb_for_collider(stage, collider)
        for collider in left_query["colliders"]
    ]
    right_bounds = [
        _world_aabb_for_collider(stage, collider)
        for collider in right_query["colliders"]
    ]
    left_min = min(bound["min_m"][1] for bound in left_bounds)
    left_max = max(bound["max_m"][1] for bound in left_bounds)
    right_min = min(bound["min_m"][1] for bound in right_bounds)
    right_max = max(bound["max_m"][1] for bound in right_bounds)
    low_max, high_min = sorted((left_max, right_max))[0], sorted((left_min, right_min))[1]
    gap = max(0.0, high_min - low_max)
    return {
        "left_world_y_interval_m": [left_min, left_max],
        "right_world_y_interval_m": [right_min, right_max],
        "open_inner_gap_m": gap,
        "method": "cooked_collider_world_aabb",
    }


def _source_width_raycast(
    stage: Any,
    *,
    source_collider_path: str,
    center_world_m: Sequence[float],
    height_offsets_m: Sequence[float],
) -> list[dict[str, Any]]:
    import carb
    from omni.physx import get_physx_scene_query_interface

    center = np.asarray(center_world_m, dtype=np.float64)
    query = get_physx_scene_query_interface()
    records = []
    for offset in height_offsets_m:
        hits = []

        def report(hit):
            collision = str(hit.collision)
            if collision == source_collider_path:
                hits.append(
                    {
                        "position_m": [
                            float(hit.position.x),
                            float(hit.position.y),
                            float(hit.position.z),
                        ],
                        "normal": [
                            float(hit.normal.x),
                            float(hit.normal.y),
                            float(hit.normal.z),
                        ],
                        "collision": collision,
                        "rigid_body": str(hit.rigid_body),
                    }
                )
            return True

        z = float(center[2] + offset)
        for direction in (1.0, -1.0):
            origin_y = float(center[1] - direction * 0.15)
            query.raycast_all(
                carb.Float3(float(center[0]), origin_y, z),
                carb.Float3(0.0, direction, 0.0),
                0.30,
                report,
            )
        ys = sorted({round(hit["position_m"][1], 8) for hit in hits})
        records.append(
            {
                "height_offset_from_geometry_center_m": float(offset),
                "world_z_m": z,
                "source_hit_count": len(hits),
                "unique_world_y_hits_m": ys,
                "source_width_y_m": (max(ys) - min(ys) if len(ys) >= 2 else None),
                "hits": hits,
            }
        )
    return records


def _support_impulse_from_frame(
    contacts: Sequence[Mapping[str, Any]],
    *,
    source_root_path: str,
) -> tuple[float, list[tuple[str, str]]]:
    total = 0.0
    pairs = []
    for contact in contacts:
        body0 = str(contact.get("body0", ""))
        body1 = str(contact.get("body1", ""))
        if not body0 or not body1:
            continue
        source0 = body0 == source_root_path or body0.startswith(source_root_path + "/")
        source1 = body1 == source_root_path or body1.startswith(source_root_path + "/")
        if source0 == source1:
            continue
        other = body1 if source0 else body0
        if other.startswith("/World/InternDataParityFluid") or other.startswith("/World/Franka"):
            continue
        impulse = np.asarray(contact.get("impulse"), dtype=np.float64)
        if impulse.shape != (3,) or not np.isfinite(impulse).all():
            continue
        total += abs(float(impulse[2]))
        pairs.append(tuple(sorted((body0, body1))))
    return total, pairs


def _run_runtime(args: argparse.Namespace) -> dict[str, Any]:
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": bool(args.headless), "width": 64, "height": 64})
    report: dict[str, Any] = {}
    try:
        from isaacsim_compat import install_legacy_isaacsim_aliases

        install_legacy_isaacsim_aliases()
        import omni
        import omni.physx
        import omni.usd
        from isaacsim.core.api import World
        from isaacsim.core.utils.stage import add_reference_to_stage, get_stage_units
        from isaacsim.core.utils.types import ArticulationAction
        from isaacsim.sensors.physics import ContactSensor
        from omegaconf import OmegaConf

        from factories.robot_factory import create_robot
        from factories.task_factory import create_task
        from robots.franka.rmpflow_controller import RMPFlowController
        from utils.isaac_fluid_evaluation import (
            configure_contact_grasp_scene,
            configure_fluid_world_timing,
            configure_particle_usd_readback,
        )
        from utils.object_utils import ObjectUtils

        cfg = OmegaConf.load(str(args.config))
        fluid = cfg.online_fluid
        stage = omni.usd.get_context().get_stage()
        configure_particle_usd_readback()
        add_reference_to_stage(
            usd_path=str((REPO_ROOT / str(cfg.usd_path)).resolve()),
            prim_path="/World",
        )
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
        robot = create_robot(
            str(cfg.robot.type),
            position=np.asarray(cfg.robot.position, dtype=np.float64),
            usd_path=str((REPO_ROOT / str(cfg.robot.usd_path)).resolve()),
            camera_frequency=int(cfg.robot.camera_frequency),
        )
        scene_record = configure_contact_grasp_scene(stage, fluid)
        ObjectUtils.get_instance(stage)
        task = create_task(
            str(cfg.task_type),
            cfg=cfg,
            world=world,
            stage=stage,
            robot=robot,
        )
        task.reset()
        frame_controller = RMPFlowController(
            name="contact_grasp_feasibility_frame_controller",
            robot_articulation=robot,
            physics_dt=float(fluid.rendering_dt),
        )
        configure_fluid_world_timing(
            world,
            physics_dt=float(fluid.physics_dt),
            rendering_dt=float(fluid.rendering_dt),
        )
        source_sensor = ContactSensor(
            prim_path=str(fluid.source_external_shell_path) + "/feasibility_sensor",
            name="contact_grasp_feasibility_source_sensor",
            dt=float(fluid.physics_dt),
            min_threshold=0.0,
            max_threshold=10000000.0,
            radius=-1.0,
        )
        source_sensor.initialize()
        source_sensor.add_raw_contact_data_to_frame()

        support_impulses = []
        pair_counts: Counter[tuple[str, str]] = Counter()
        for step in range(args.pre_roll_steps):
            world.step(render=False)
            frame = source_sensor.get_current_frame()
            impulse, pairs = _support_impulse_from_frame(
                frame.get("contacts", []),
                source_root_path=str(fluid.source_actor_path),
            )
            if step >= args.pre_roll_steps - args.support_tail_steps and impulse > 0.0:
                support_impulses.append(impulse)
                pair_counts.update(pairs)

        source_center = task.object_utils.get_geometry_center(
            object_path=str(fluid.source_actor_path)
        )
        control_position, control_rotation = (
            frame_controller.get_end_effector_pose_world()
        )
        control_world = row_world_matrix_from_lula_pose(
            position_world_m=control_position,
            column_rotation_world=control_rotation,
        )
        grasp_world = _row_matrix(stage, str(fluid.grasp_frame_path))
        measured_control_to_grasp = derive_control_to_target_row_matrix(
            control_world_matrix=control_world,
            target_world_matrix=grasp_world,
        )
        configured_control_to_grasp = np.asarray(
            fluid.rmpflow_control_to_grasp_matrix_m,
            dtype=np.float64,
        )
        frame_translation_error = float(
            np.linalg.norm(
                measured_control_to_grasp[3, :3]
                - configured_control_to_grasp[3, :3]
            )
        )
        relative_rotation = (
            measured_control_to_grasp[:3, :3]
            @ configured_control_to_grasp[:3, :3].T
        )
        frame_rotation_error = math.degrees(
            math.acos(
                float(
                    np.clip((np.trace(relative_rotation) - 1.0) / 2.0, -1.0, 1.0)
                )
            )
        )

        body_paths = {
            "source": str(fluid.source_actor_path),
            "left_finger": str(fluid.finger_body_paths[0]),
            "right_finger": str(fluid.finger_body_paths[1]),
            "hand": "/World/Franka/panda_hand",
            "table": str(fluid.table_path),
        }
        cooked = {
            name: _query_cooked_colliders(app, stage, path)
            for name, path in body_paths.items()
        }
        open_gap = _finger_open_gap(
            stage,
            cooked["left_finger"],
            cooked["right_finger"],
        )
        source_widths = _source_width_raycast(
            stage,
            source_collider_path=str(fluid.source_external_shell_path),
            center_world_m=source_center,
            height_offsets_m=(-0.025, -0.015, -0.005, 0.005, 0.015, 0.025),
        )

        contact_offsets = {
            "source": _configured_contact_offset(
                stage, str(fluid.source_external_shell_path)
            ),
            "left_finger": [
                _configured_contact_offset(stage, path)
                for path in scene_record["finger_collider_paths"][body_paths["left_finger"]]
            ],
            "right_finger": [
                _configured_contact_offset(stage, path)
                for path in scene_record["finger_collider_paths"][body_paths["right_finger"]]
            ],
        }

        finger_indices = robot.validate_gripper_dof_contract(
            tuple(int(value) for value in fluid.finger_joint_indices)
        )
        stage_units = float(get_stage_units())
        velocity_samples = []
        for _ in range(args.velocity_control_steps):
            joints = np.asarray(robot.get_joint_positions(), dtype=np.float64)
            targets = [None] * len(joints)
            for index in finger_indices:
                targets[index] = max(
                    0.0,
                    float(joints[index])
                    - args.commanded_pad_speed_m_s
                    * float(fluid.rendering_dt)
                    / stage_units,
                )
            robot.get_articulation_controller().apply_action(
                ArticulationAction(joint_positions=targets)
            )
            for _ in range(int(fluid.physics_substeps_per_observation)):
                before = np.asarray(robot.get_joint_positions(), dtype=np.float64)[
                    list(finger_indices)
                ]
                world.step(render=False)
                after = np.asarray(robot.get_joint_positions(), dtype=np.float64)[
                    list(finger_indices)
                ]
                finite_difference = (
                    (after - before) * stage_units / float(fluid.physics_dt)
                )
                api = robot.get_gripper_pad_relative_velocities_m_s()
                velocity_samples.append(
                    {
                        "api_pad_velocity_m_s": api.tolist(),
                        "finite_difference_pad_velocity_m_s": (
                            finite_difference.tolist()
                        ),
                        "joint_position_before": before.tolist(),
                        "joint_position_after": after.tolist(),
                    }
                )
        velocity_authority = summarize_pad_velocity_authority(
            velocity_samples,
            agreement_tolerance_m_s=args.velocity_agreement_tolerance_m_s,
        )
        try:
            support_mass = derive_effective_payload_mass_from_support(
                support_impulses_n_s=support_impulses,
                physics_dt=float(fluid.physics_dt),
                gravity_m_s2=args.gravity_m_s2,
                minimum_samples=args.minimum_support_samples,
            )
        except ValueError as exc:
            support_mass = {
                "passed": False,
                "failure_reason": str(exc),
                "sample_count": len(support_impulses),
            }

        unresolved_offsets = [
            record["path"]
            for record in [
                contact_offsets["source"],
                *contact_offsets["left_finger"],
                *contact_offsets["right_finger"],
            ]
            if record["contact_offset_m"] is None
        ]
        finger_contact_offsets = []
        for side in ("left_finger", "right_finger"):
            values = [
                record["contact_offset_m"] for record in contact_offsets[side]
            ]
            finger_contact_offsets.append(
                max(float(value) for value in values)
                if values and all(value is not None for value in values)
                else None
            )
        pre_sweep_clearance = summarize_pre_sweep_clearance(
            open_inner_gap_m=float(open_gap["open_inner_gap_m"]),
            source_widths_m=[
                float(record["source_width_y_m"])
                for record in source_widths
                if record["source_width_y_m"] is not None
            ],
            source_contact_offset_m=contact_offsets["source"][
                "contact_offset_m"
            ],
            finger_contact_offsets_m=finger_contact_offsets,
            controller_tracking_error_m=None,
            numerical_margin_m=0.001,
        )
        report = {
            "schema_version": 1,
            "manifest_type": "contact_grasp_feasibility_probe_v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "config_path": str(args.config),
            "config_sha256": _sha256_file(args.config),
            "usd_path": str((REPO_ROOT / str(cfg.usd_path)).resolve()),
            "usd_sha256": _sha256_file((REPO_ROOT / str(cfg.usd_path)).resolve()),
            "physics_dt": float(fluid.physics_dt),
            "rendering_dt": float(fluid.rendering_dt),
            "pre_roll_steps": args.pre_roll_steps,
            "source_geometry_center_world_m": np.asarray(source_center).tolist(),
            "frame_probe": {
                "control_frame_name": str(fluid.rmpflow_control_frame_name),
                "control_frame_authority": "lula_rmpflow_forward_kinematics",
                "grasp_frame_path": str(fluid.grasp_frame_path),
                "control_world_matrix_m": control_world.tolist(),
                "grasp_world_matrix_m": grasp_world.tolist(),
                "measured_control_to_grasp_matrix_m": measured_control_to_grasp.tolist(),
                "configured_control_to_grasp_matrix_m": configured_control_to_grasp.tolist(),
                "translation_error_m": frame_translation_error,
                "rotation_error_degrees": frame_rotation_error,
                "passed": bool(
                    frame_translation_error <= 0.0005
                    and frame_rotation_error <= 0.5
                ),
            },
            "velocity_probe": {
                **velocity_authority,
                "commanded_pad_speed_m_s": args.commanded_pad_speed_m_s,
                "samples": velocity_samples,
            },
            "support_load_probe": {
                **support_mass,
                "support_impulses_n_s": support_impulses,
                "contact_pair_counts": {
                    " | ".join(pair): count
                    for pair, count in sorted(pair_counts.items())
                },
            },
            "cooked_collider_probe": {
                "bodies": cooked,
                "open_finger_gap": open_gap,
                "source_width_raycast": source_widths,
                "contact_offsets": contact_offsets,
                "unresolved_contact_offset_paths": unresolved_offsets,
                "pre_sweep_clearance": pre_sweep_clearance,
            },
            "motion_contract": {
                "arm_action_count": 0,
                "approach_action_count": 0,
                "contact_close_action_count": 0,
                "free_space_finger_velocity_command_count": (
                    args.velocity_control_steps
                ),
                "lift_action_count": 0,
                "pour_action_count": 0,
                "source_pose_write_count": 0,
            },
        }
        prerequisite_evaluation = evaluate_probe_prerequisites(report)
        report["prerequisite_evaluation"] = prerequisite_evaluation
        prerequisites_passed = bool(prerequisite_evaluation["passed"])
        report["prerequisites_passed"] = prerequisites_passed
        report["measurement_decision"] = (
            "BLOCKED_SIDE_POSE_SWEEP_REQUIRED"
            if prerequisites_passed
            else "NO_GO_PREREQUISITE_MEASUREMENT_FAILED"
        )
        report["lifecycle_status"] = (
            "measurement_complete_pending_application_close"
        )
        report["shutdown_status"] = "pending"
    except Exception as exc:
        report = _runtime_error_report(exc, phase="runtime_measurement")
    finally:
        _persist_provisional_before_shutdown(
            app=app,
            output_path=args.out,
            report=report,
        )
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--runtime-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pre-roll-steps", type=int, default=180)
    parser.add_argument("--support-tail-steps", type=int, default=60)
    parser.add_argument("--minimum-support-samples", type=int, default=30)
    parser.add_argument("--velocity-control-steps", type=int, default=12)
    parser.add_argument("--commanded-pad-speed-m-s", type=float, default=0.01)
    parser.add_argument(
        "--velocity-agreement-tolerance-m-s",
        type=float,
        default=0.002,
    )
    parser.add_argument("--gravity-m-s2", type=float, default=9.81)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out = args.out.resolve()
    if args.pre_roll_steps <= 0 or not 0 < args.support_tail_steps <= args.pre_roll_steps:
        parser.error("invalid pre-roll/support-tail step counts")
    return args


def _provisional_output_path(final_output_path: Path) -> Path:
    return final_output_path.with_name(
        f"{final_output_path.stem}.pre_shutdown{final_output_path.suffix}"
    )


def _child_command(args: argparse.Namespace, provisional_output: Path) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--runtime-child",
        "--config",
        str(args.config),
        "--out",
        str(provisional_output),
        "--pre-roll-steps",
        str(args.pre_roll_steps),
        "--support-tail-steps",
        str(args.support_tail_steps),
        "--minimum-support-samples",
        str(args.minimum_support_samples),
        "--velocity-control-steps",
        str(args.velocity_control_steps),
        "--commanded-pad-speed-m-s",
        str(args.commanded_pad_speed_m_s),
        "--velocity-agreement-tolerance-m-s",
        str(args.velocity_agreement_tolerance_m_s),
        "--gravity-m-s2",
        str(args.gravity_m_s2),
    ]
    if args.headless:
        command.append("--headless")
    return command


def _load_json_mapping(path: Path) -> dict[str, Any]:
    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"probe_json_nonfinite_constant:{value}")

    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream, parse_constant=reject_nonfinite)
    if not isinstance(value, dict):
        raise TypeError("probe_json_mapping_required")
    if value.get("manifest_type") != "contact_grasp_feasibility_probe_v1":
        raise ValueError("probe_manifest_type_invalid")
    if value.get("shutdown_status") != "pending":
        raise ValueError("probe_provisional_shutdown_status_invalid")
    return value


def _run_child(args: argparse.Namespace) -> int:
    try:
        report = _run_runtime(args)
    except Exception as exc:
        if args.out.exists():
            raise
        report = _runtime_error_report(exc, phase="application_bootstrap")
        _atomic_write_json(args.out, report)
    return 0


def _run_parent(args: argparse.Namespace) -> int:
    provisional_output = _provisional_output_path(args.out)
    existing = [path for path in (args.out, provisional_output) if path.exists()]
    if existing:
        print(
            "contact grasp feasibility probe refused existing output: "
            + ", ".join(str(path) for path in existing),
            file=sys.stderr,
            flush=True,
        )
        return 2

    command = _child_command(args, provisional_output)
    try:
        completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
        child_returncode = int(completed.returncode)
        provisional = _load_json_mapping(provisional_output)
    except Exception as exc:
        child_returncode = int(
            completed.returncode if "completed" in locals() else 127
        )
        provisional = _runtime_error_report(exc, phase="child_provisional_report")

    report = _finalize_child_report(
        provisional,
        child_returncode=child_returncode,
        child_command=command,
    )
    _atomic_write_json(args.out, report)
    print(
        f"contact grasp feasibility probe decision={report['decision']} out={args.out}",
        flush=True,
    )
    return 0 if report["decision"] == "BLOCKED_SIDE_POSE_SWEEP_REQUIRED" else 2


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_child(args) if args.runtime_child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
