#!/usr/bin/env python3
"""Audit whether the colleague liquid USD can direct-step as authored in IsaacSim41.

D0 is intentionally stricter than the bounded B0 smoke:
- it does not re-author particles;
- it does not add a PBD material;
- it does not add a proxy collider;
- it does not replace the source USD with red diagnostic particles.

The only runtime settings this audit changes are USD/readback visibility settings
so the authored particles can be observed if the raw runtime contract is valid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_USD = (
    "outputs/usd_asset_packages/lab_001_localized_20260707/"
    "lab_001_level1_pour_tabletop_with_liquid.usd"
)
DEFAULT_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_colleague_raw_usd_direct_step_audit_20260708_001"
)
DEFAULT_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_colleague_raw_usd_direct_step_audit_20260708.json"
)
RAW_PARTICLE_SET_PATH = "/World/ParticleSet"
RAW_PARTICLE_SYSTEM_PATH = "/World/ParticleSystem"
RAW_PHYSICS_SCENE_PATH = "/World/PhysicsScene"


def is_finite_nonzero_gravity(direction: Sequence[float] | None, magnitude: float | None) -> bool:
    if direction is None or magnitude is None:
        return False
    values = [float(v) for v in direction] + [float(magnitude)]
    if not all(math.isfinite(v) for v in values):
        return False
    return math.sqrt(sum(float(v) * float(v) for v in direction)) > 1e-8 and abs(float(magnitude)) > 1e-8


def summarize_numeric_sequence(values: Iterable[float]) -> dict[str, Any]:
    normalized = [float(value) for value in values]
    finite = [value for value in normalized if math.isfinite(value)]
    unique_preview = sorted(set(round(value, 12) for value in finite))[:8]
    return {
        "count": len(normalized),
        "finite_count": len(finite),
        "min": min(finite) if finite else None,
        "max": max(finite) if finite else None,
        "unique_preview": unique_preview,
    }


def classify_raw_direct_step_audit(
    *,
    raw_runtime_contract_complete: bool,
    readback_available: bool,
    readback_position_changed: bool,
    particle_count_initial: int,
    particle_count_final: int,
    nan_count: int,
    fatal_error: dict[str, Any] | None,
    perf_budget_exceeded: bool,
) -> dict[str, Any]:
    final_fraction = particle_count_final / particle_count_initial if particle_count_initial else 0.0
    if fatal_error is not None:
        classification = "STOP_RUNTIME_ERROR"
    elif perf_budget_exceeded:
        classification = "STOP_PERF_OR_OOM"
    elif not raw_runtime_contract_complete:
        classification = "STOP_RAW_RUNTIME_INCOMPLETE"
    elif not readback_available or not readback_position_changed:
        classification = "STOP_READBACK_UNAVAILABLE"
    elif particle_count_initial <= 0 or final_fraction < 0.95 or nan_count != 0:
        classification = "STOP_READBACK_UNAVAILABLE"
    else:
        classification = "PASS_RAW_DIRECT_STEP_RUNTIME"
    status = "GO_NEXT" if classification == "PASS_RAW_DIRECT_STEP_RUNTIME" else "STOP_WITH_EVIDENCE"
    return {
        "status": status,
        "classification": classification,
        "direct_original_50k_runtime_claim_allowed": classification == "PASS_RAW_DIRECT_STEP_RUNTIME",
        "pass_criteria": {
            "raw_runtime_contract_complete": bool(raw_runtime_contract_complete),
            "readback_available": bool(readback_available),
            "readback_position_changed": bool(readback_position_changed),
            "particle_count_initial_gt_zero": particle_count_initial > 0,
            "particle_count_final_fraction_ge_0_95": final_fraction >= 0.95,
            "nan_count_eq_zero": nan_count == 0,
            "fatal_error_absent": fatal_error is None,
            "perf_budget_not_exceeded": not perf_budget_exceeded,
        },
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), allow_nan=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_trace_line(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_safe(payload), allow_nan=False, sort_keys=True) + "\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable_positions(positions: Sequence[Sequence[float]], *, limit: int = 64) -> list[list[float]]:
    return [[float(p[0]), float(p[1]), float(p[2])] for p in positions[:limit]]


def _position_hash(positions: Sequence[Sequence[float]]) -> str:
    payload = json.dumps([[float(p[0]), float(p[1]), float(p[2])] for p in positions], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finite_positions(positions: Sequence[Sequence[float]]) -> list[tuple[float, float, float]]:
    finite: list[tuple[float, float, float]] = []
    for pos in positions:
        values = (float(pos[0]), float(pos[1]), float(pos[2]))
        if all(math.isfinite(v) for v in values):
            finite.append(values)
    return finite


def _nan_count(positions: Sequence[Sequence[float]]) -> int:
    return len(positions) - len(_finite_positions(positions))


def _aabb(positions: Sequence[Sequence[float]]) -> dict[str, list[float] | None]:
    finite = _finite_positions(positions)
    if not finite:
        return {"min": None, "max": None}
    return {
        "min": [min(pos[i] for pos in finite) for i in range(3)],
        "max": [max(pos[i] for pos in finite) for i in range(3)],
    }


def _centroid(positions: Sequence[Sequence[float]]) -> list[float] | None:
    finite = _finite_positions(positions)
    if not finite:
        return None
    return [sum(pos[i] for pos in finite) / len(finite) for i in range(3)]


def _max_displacement(initial: Sequence[Sequence[float]], final: Sequence[Sequence[float]]) -> float:
    max_dist = 0.0
    for before, after in zip(initial, final):
        before_v = (float(before[0]), float(before[1]), float(before[2]))
        after_v = (float(after[0]), float(after[1]), float(after[2]))
        if all(math.isfinite(v) for v in before_v + after_v):
            max_dist = max(max_dist, math.sqrt(sum((after_v[i] - before_v[i]) ** 2 for i in range(3))))
    return max_dist


def _relationships(prim: Any, names: Sequence[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for name in names:
        rel = prim.GetRelationship(name) if prim else None
        if rel:
            result[name] = [str(target) for target in rel.GetTargets()]
    return result


def _material_targets(prim: Any) -> list[str]:
    targets: list[str] = []
    for name in ("material:binding", "material:binding:full", "material:binding:preview"):
        rel = prim.GetRelationship(name) if prim else None
        if rel:
            targets.extend(str(target) for target in rel.GetTargets())
    return sorted(set(targets))


def _attr_value(prim: Any, *names: str) -> Any:
    if not prim:
        return None
    for name in names:
        attr = prim.GetAttribute(name)
        if attr:
            try:
                value = attr.Get()
            except Exception:
                value = None
            if value is not None:
                return value
    return None


def _vec3_to_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except Exception:
        return None


def _read_points(stage: Any, path: str) -> list[tuple[float, float, float]]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim:
        return []
    values = UsdGeom.Points(prim).GetPointsAttr().Get()
    if values is None:
        return []
    return [(float(p[0]), float(p[1]), float(p[2])) for p in values]


def _read_widths(stage: Any, path: str) -> list[float]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim:
        return []
    values = UsdGeom.Points(prim).GetWidthsAttr().Get()
    if values is None:
        return []
    return [float(value) for value in values]


def _read_velocities(stage: Any, path: str) -> list[tuple[float, float, float]]:
    from pxr import UsdGeom

    prim = stage.GetPrimAtPath(path)
    if not prim:
        return []
    values = UsdGeom.Points(prim).GetVelocitiesAttr().Get()
    if values is None:
        return []
    return [(float(p[0]), float(p[1]), float(p[2])) for p in values]


def _has_api(prim: Any, api_name: str) -> bool:
    return bool(prim) and api_name in [str(schema) for schema in prim.GetAppliedSchemas()]


def _has_pbd_material_api(stage: Any, paths: Sequence[str]) -> bool:
    for prim in stage.TraverseAll():
        if "PhysxPBDMaterialAPI" in [str(schema) for schema in prim.GetAppliedSchemas()]:
            return True
    for path in paths:
        prim = stage.GetPrimAtPath(path)
        if prim and "PhysxPBDMaterialAPI" in [str(schema) for schema in prim.GetAppliedSchemas()]:
            return True
    return False


def _audit_raw_contract(stage: Any) -> dict[str, Any]:
    from pxr import PhysxSchema, UsdPhysics

    particle_set_prim = stage.GetPrimAtPath(RAW_PARTICLE_SET_PATH)
    particle_system_prim = stage.GetPrimAtPath(RAW_PARTICLE_SYSTEM_PATH)
    physics_scene_prim = stage.GetPrimAtPath(RAW_PHYSICS_SCENE_PATH)
    physics_scene = UsdPhysics.Scene(physics_scene_prim) if physics_scene_prim else None
    physx_scene_api = PhysxSchema.PhysxSceneAPI(physics_scene_prim) if physics_scene_prim else None

    particle_system_targets = _relationships(particle_set_prim, ("physxParticle:particleSystem",))
    material_targets = sorted(set(_material_targets(particle_set_prim) + _material_targets(particle_system_prim)))
    gravity_direction = _vec3_to_list(
        _attr_value(
            physics_scene_prim,
            "physics:gravityDirection",
            "physxScene:gravityDirection",
        )
    )
    gravity_magnitude_raw = _attr_value(
        physics_scene_prim,
        "physics:gravityMagnitude",
        "physxScene:gravityMagnitude",
    )
    gravity_magnitude = float(gravity_magnitude_raw) if gravity_magnitude_raw is not None else None
    gpu_dynamics_raw = _attr_value(physics_scene_prim, "physxScene:enableGPUDynamics")
    broadphase_type = _attr_value(physics_scene_prim, "physxScene:broadphaseType")
    solver_type = _attr_value(physics_scene_prim, "physxScene:solverType")
    widths = _read_widths(stage, RAW_PARTICLE_SET_PATH)
    velocities = _read_velocities(stage, RAW_PARTICLE_SET_PATH)
    positions = _read_points(stage, RAW_PARTICLE_SET_PATH)

    has_particle_set = bool(particle_set_prim)
    has_particle_system = bool(particle_system_prim) and bool(PhysxSchema.PhysxParticleSystem(particle_system_prim))
    has_particle_set_api = _has_api(particle_set_prim, "PhysxParticleSetAPI")
    has_pbd_material_api = _has_pbd_material_api(stage, material_targets)
    particle_system_relationship_closed = RAW_PARTICLE_SYSTEM_PATH in particle_system_targets.get(
        "physxParticle:particleSystem", []
    )
    gravity_ok = is_finite_nonzero_gravity(gravity_direction, gravity_magnitude)
    gravity_invalid_reasons: list[str] = []
    if gravity_direction is None:
        gravity_invalid_reasons.append("missing_gravity_direction")
    elif not all(math.isfinite(float(value)) for value in gravity_direction):
        gravity_invalid_reasons.append("nonfinite_gravity_direction")
    elif math.sqrt(sum(float(value) * float(value) for value in gravity_direction)) <= 1e-8:
        gravity_invalid_reasons.append("zero_gravity_direction")
    if gravity_magnitude is None:
        gravity_invalid_reasons.append("missing_gravity_magnitude")
    elif not math.isfinite(float(gravity_magnitude)):
        gravity_invalid_reasons.append("nonfinite_gravity_magnitude")
    elif abs(float(gravity_magnitude)) <= 1e-8:
        gravity_invalid_reasons.append("zero_gravity_magnitude")
    gpu_dynamics_authored_true = gpu_dynamics_raw is True
    raw_runtime_contract_complete = all(
        [
            has_particle_set,
            has_particle_system,
            has_particle_set_api,
            has_pbd_material_api,
            particle_system_relationship_closed,
            gravity_ok,
            gpu_dynamics_authored_true,
            len(positions) > 0,
            len(widths) in (0, len(positions), 1),
        ]
    )
    reasons = []
    if not has_particle_set:
        reasons.append("missing_/World/ParticleSet")
    if not has_particle_system:
        reasons.append("missing_or_invalid_/World/ParticleSystem")
    if not has_particle_set_api:
        reasons.append("missing_PhysxParticleSetAPI")
    if not has_pbd_material_api:
        reasons.append("missing_PhysxPBDMaterialAPI")
    if not particle_system_relationship_closed:
        reasons.append("particle_system_relationship_not_closed")
    if not gravity_ok:
        reasons.append("invalid_or_zero_gravity")
    if not gpu_dynamics_authored_true:
        reasons.append("gpu_dynamics_not_authored_true")
    if len(positions) <= 0:
        reasons.append("particle_points_missing")
    if len(widths) not in (0, len(positions), 1):
        reasons.append("width_count_mismatch")
    return {
        "raw_runtime_contract_complete": raw_runtime_contract_complete,
        "raw_runtime_contract_missing_reasons": reasons,
        "has_particle_set": has_particle_set,
        "has_particle_system": has_particle_system,
        "has_particle_set_api": has_particle_set_api,
        "has_pbd_material_api": has_pbd_material_api,
        "particle_system_relationships": particle_system_targets,
        "particle_system_relationship_closed": particle_system_relationship_closed,
        "material_binding_targets": material_targets,
        "gravity_direction": gravity_direction,
        "gravity_magnitude": gravity_magnitude,
        "gravity_finite_nonzero": gravity_ok,
        "gravity_invalid_reasons": gravity_invalid_reasons,
        "gpu_dynamics_authored": gpu_dynamics_raw,
        "gpu_dynamics_authored_true": gpu_dynamics_authored_true,
        "broadphase_type": str(broadphase_type) if broadphase_type is not None else None,
        "solver_type": str(solver_type) if solver_type is not None else None,
        "particle_count": len(positions),
        "particle_widths_summary": summarize_numeric_sequence(widths),
        "particle_velocities_count": len(velocities),
        "particle_aabb": _aabb(positions),
        "particle_centroid": _centroid(positions),
        "physics_scene_is_valid": bool(physics_scene),
        "physx_scene_api_is_valid": bool(physx_scene_api),
    }


def _runtime_audit(args: argparse.Namespace) -> dict[str, Any]:
    import carb
    import omni.physx.bindings._physx as pb
    from pxr import Usd

    usd_path = Path(args.usd).resolve()
    artifact_dir = Path(args.out_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    trace_path = artifact_dir / "raw_particle_readback_trace.jsonl"
    trace_path.write_text("", encoding="utf-8")
    fatal_error = None
    start = time.monotonic()

    settings = carb.settings.get_settings()
    settings.set(pb.SETTING_UPDATE_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
    settings.set_bool(pb.SETTING_SUPPRESS_READBACK, False)

    audit_mode = "force_timeline_step" if args.force_step else "static_raw_contract_audit"
    if args.force_step:
        import omni.kit.app
        import omni.timeline
        import omni.usd

        context = omni.usd.get_context()
        opened = bool(context.open_stage(str(usd_path)))
        for _ in range(args.warmup_updates):
            omni.kit.app.get_app().update()
        stage = context.get_stage()
        if not opened or stage is None:
            raise RuntimeError(f"open_stage_failed:{usd_path}")
    else:
        stage = Usd.Stage.Open(str(usd_path), Usd.Stage.LoadAll)
        if stage is None:
            raise RuntimeError(f"usd_stage_open_failed:{usd_path}")

    raw_contract = _audit_raw_contract(stage)
    initial_positions = _read_points(stage, RAW_PARTICLE_SET_PATH)
    initial_record = {
        "step_index": 0,
        "particle_count": len(initial_positions),
        "aabb": _aabb(initial_positions),
        "centroid": _centroid(initial_positions),
        "nan_count": _nan_count(initial_positions),
        "positions_preview": _jsonable_positions(initial_positions),
        "position_hash": _position_hash(initial_positions) if initial_positions else None,
    }
    _write_trace_line(trace_path, initial_record)

    runtime_step_executed = False
    step_skipped_reason = None
    if not args.force_step:
        if not raw_contract["raw_runtime_contract_complete"]:
            step_skipped_reason = "raw_runtime_contract_incomplete"
        else:
            step_skipped_reason = "static_contract_complete_force_step_required_for_runtime_claim"
        final_positions = initial_positions
        _write_trace_line(
            trace_path,
            {
                "step_index": 0,
                "event": "step_skipped",
                "reason": step_skipped_reason,
                "raw_runtime_contract_missing_reasons": raw_contract["raw_runtime_contract_missing_reasons"],
                "particle_count": len(final_positions),
                "position_hash": _position_hash(final_positions) if final_positions else None,
            },
        )
    else:
        import omni.kit.app
        import omni.timeline

        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        try:
            for step_index in range(1, args.steps + 1):
                omni.kit.app.get_app().update()
                runtime_step_executed = True
                if step_index % args.trace_interval == 0 or step_index == args.steps:
                    positions = _read_points(stage, RAW_PARTICLE_SET_PATH)
                    _write_trace_line(
                        trace_path,
                        {
                            "step_index": step_index,
                            "particle_count": len(positions),
                            "aabb": _aabb(positions),
                            "centroid": _centroid(positions),
                            "nan_count": _nan_count(positions),
                            "positions_preview": _jsonable_positions(positions),
                            "position_hash": _position_hash(positions) if positions else None,
                        },
                    )
        finally:
            timeline.stop()
            for _ in range(2):
                omni.kit.app.get_app().update()
        final_positions = _read_points(stage, RAW_PARTICLE_SET_PATH)
    readback_position_changed = (
        bool(initial_positions)
        and bool(final_positions)
        and _position_hash(initial_positions) != _position_hash(final_positions)
    )
    readback_available = bool(initial_positions) and bool(final_positions)
    nan_count = _nan_count(initial_positions) + _nan_count(final_positions)
    max_displacement = _max_displacement(initial_positions, final_positions)
    final_fraction = len(final_positions) / len(initial_positions) if initial_positions else 0.0
    perf_budget_exceeded = (time.monotonic() - start) > float(args.perf_budget_seconds)
    classification = classify_raw_direct_step_audit(
        raw_runtime_contract_complete=bool(raw_contract["raw_runtime_contract_complete"]),
        readback_available=readback_available,
        readback_position_changed=readback_position_changed,
        particle_count_initial=len(initial_positions),
        particle_count_final=len(final_positions),
        nan_count=nan_count,
        fatal_error=fatal_error,
        perf_budget_exceeded=perf_budget_exceeded,
    )
    summary = {
        "schema_version": 1,
        "manifest_type": "fluid_spike_colleague_raw_usd_direct_step_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": "isaacsim41",
        "mode": "raw_usd_direct_step_audit",
        "audit_mode": audit_mode,
        "usd_path": str(usd_path),
        "raw_usd_sha256": _sha256_file(usd_path),
        "artifact_dir": str(artifact_dir),
        "trace_path": str(trace_path),
        "raw_particle_set_path": RAW_PARTICLE_SET_PATH,
        "raw_particle_system_path": RAW_PARTICLE_SYSTEM_PATH,
        "raw_physics_scene_path": RAW_PHYSICS_SCENE_PATH,
        "steps": args.steps,
        "runtime_step_executed": runtime_step_executed,
        "force_step": bool(args.force_step),
        "step_skipped_reason": step_skipped_reason,
        "raw_contract": raw_contract,
        "readback_diagnostics": {
            "readback_available": readback_available,
            "readback_position_changed": readback_position_changed,
            "initial_position_hash": _position_hash(initial_positions) if initial_positions else None,
            "final_position_hash": _position_hash(final_positions) if final_positions else None,
            "particle_count_initial": len(initial_positions),
            "particle_count_final": len(final_positions),
            "particle_count_final_fraction": final_fraction,
            "nan_count": nan_count,
            "initial_aabb": _aabb(initial_positions),
            "final_aabb": _aabb(final_positions),
            "initial_centroid": _centroid(initial_positions),
            "final_centroid": _centroid(final_positions),
            "max_displacement": max_displacement,
        },
        "evaluation_notes": {
            "readback_diagnostics_are_post_step_survival_evidence": runtime_step_executed,
            "readback_diagnostics_note": (
                "No-step static snapshot fields; not post-timeline survival evidence."
                if not runtime_step_executed
                else "Runtime timeline step executed; readback diagnostics compare initial and final positions."
            ),
            "warning_scan_status": (
                "not_run_due_to_raw_contract_stop"
                if step_skipped_reason == "raw_runtime_contract_incomplete"
                else "not_separately_scanned_by_this_runner"
            ),
        },
        "runtime_settings": {
            "update_to_usd_setting": settings.get(pb.SETTING_UPDATE_TO_USD),
            "update_particles_to_usd_setting": settings.get(pb.SETTING_UPDATE_PARTICLES_TO_USD),
            "update_velocities_to_usd_setting": settings.get(pb.SETTING_UPDATE_VELOCITIES_TO_USD),
            "suppress_readback_setting": settings.get(pb.SETTING_SUPPRESS_READBACK),
        },
        "classification": classification,
        "elapsed_seconds": time.monotonic() - start,
        "claim_boundary": {
            "allowed": [
                "This D0 audit reports whether the raw colleague USD, as authored, satisfies direct-step runtime gates.",
                "Readback/static schema failures may be reported for this raw USD audit.",
            ],
            "blocked": [
                "Do not claim B0 bounded overlay results are raw USD direct-step results.",
                "Do not claim the original 50k colleague USD is benchmark-ready unless classification passes.",
                "Do not claim S3 pouring, EBench score, policy score, or visual material parity.",
            ],
        },
    }
    _write_json(artifact_dir / "runtime_smoke_summary.json", summary)
    _write_json(Path(args.manifest), summary)
    return summary


def _run_runtime(args: argparse.Namespace) -> dict[str, Any]:
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": bool(args.headless), "width": args.width, "height": args.height})
    try:
        return _runtime_audit(args)
    except Exception as exc:  # pragma: no cover - runtime-only path.
        fatal_error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc(limit=30)}
        summary = {
            "schema_version": 1,
            "manifest_type": "fluid_spike_colleague_raw_usd_direct_step_audit",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "runtime": "isaacsim41",
            "mode": "raw_usd_direct_step_audit",
            "runtime_step_executed": False,
            "fatal_error": fatal_error,
            "classification": classify_raw_direct_step_audit(
                raw_runtime_contract_complete=False,
                readback_available=False,
                readback_position_changed=False,
                particle_count_initial=0,
                particle_count_final=0,
                nan_count=0,
                fatal_error=fatal_error,
                perf_budget_exceeded=False,
            ),
        }
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_json(out_dir / "runtime_smoke_summary.json", summary)
        _write_json(Path(args.manifest), summary)
        return summary
    finally:
        app.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", default=DEFAULT_USD)
    parser.add_argument("--out-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--trace-interval", type=int, default=10)
    parser.add_argument("--warmup-updates", type=int, default=5)
    parser.add_argument("--perf-budget-seconds", type=float, default=240.0)
    parser.add_argument("--force-step", action="store_true")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--headless", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = _run_runtime(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("runtime_step_executed") or summary.get("classification") else 1


if __name__ == "__main__":
    raise SystemExit(main())
