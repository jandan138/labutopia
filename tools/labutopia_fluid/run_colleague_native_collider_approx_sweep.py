#!/usr/bin/env python3
"""Sweep built-in/native collider approximations on colleague LabUtopia beaker2."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.run_beaker_collider_smoke import _apply_static_collision

DEFAULT_USD = (
    "outputs/usd_asset_packages/lab_001_localized_20260707/"
    "lab_001_level1_pour_tabletop_with_liquid.usd"
)
DEFAULT_NATIVE_MESH_PATH = "/World/beaker2/mesh"
DEFAULT_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_native_collider_approximation_sweep_20260708_001"
)
DEFAULT_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_native_collider_approximation_sweep_20260708.json"
)
DEFAULT_RUNTIME_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_native_collider_approximation_runtime_sweep_20260708.json"
)
NEVER_PROMOTABLE_VARIANT_IDS = {"NATIVE_NONE", "NATIVE_BOUNDING_CUBE", "NATIVE_BOUNDING_SPHERE"}


@dataclass(frozen=True)
class NativeApproximationCandidate:
    variant_id: str
    approximation: str | None
    description: str
    role: str
    sdf_resolution: int | None = None
    sdf_subgrid_resolution: int | None = None
    sdf_margin: float | None = None
    sdf_narrow_band_thickness: float | None = None
    contact_offset: float = 0.002
    rest_offset: float = -0.001

    @property
    def route(self) -> str:
        return self.approximation or "raw_as_is"

    @property
    def promotable(self) -> bool:
        return self.variant_id not in NEVER_PROMOTABLE_VARIANT_IDS


def build_native_approximation_sweep() -> list[NativeApproximationCandidate]:
    return [
        NativeApproximationCandidate("RAW_AS_IS", None, "Audit current authored native collision state.", "baseline"),
        NativeApproximationCandidate("NATIVE_NONE", "none", "Direct/none mesh diagnostic.", "diagnostic"),
        NativeApproximationCandidate(
            "NATIVE_MESH_SIMPLIFICATION", "meshSimplification", "Built-in mesh simplification route.", "candidate"
        ),
        NativeApproximationCandidate("NATIVE_CONVEX_HULL", "convexHull", "Built-in convex hull route.", "candidate"),
        NativeApproximationCandidate(
            "NATIVE_CONVEX_DECOMPOSITION",
            "convexDecomposition",
            "Built-in convex decomposition route, baseline regression.",
            "candidate",
        ),
        NativeApproximationCandidate(
            "NATIVE_SDF_64", "sdf", "Built-in SDF mesh collision, resolution 64.", "candidate", sdf_resolution=64
        ),
        NativeApproximationCandidate(
            "NATIVE_SDF_128", "sdf", "Built-in SDF mesh collision, resolution 128.", "candidate", sdf_resolution=128
        ),
        NativeApproximationCandidate(
            "NATIVE_SDF_256", "sdf", "Built-in SDF mesh collision, resolution 256.", "candidate", sdf_resolution=256
        ),
        NativeApproximationCandidate("NATIVE_BOUNDING_CUBE", "boundingCube", "Bounding cube negative control.", "diagnostic"),
        NativeApproximationCandidate(
            "NATIVE_BOUNDING_SPHERE", "boundingSphere", "Bounding sphere negative control.", "diagnostic"
        ),
    ]


def build_claim_boundary() -> dict[str, Any]:
    return {
        "allowed_claims": [
            "We tested built-in/native Isaac/PhysX mesh collision approximation modes before custom wrapper design.",
            "The test used the full colleague native USD scene, completed-PBD runtime particles, and particle readback.",
            (
                "If all candidates fail, the tested native approximation modes did not produce a fluid-safe native "
                "beaker collider under this IsaacSim41/PBD setup."
            ),
            "If one candidate passes smoke, it is only a static-hold candidate for promotion review.",
        ],
        "blocked_claims": [
            "level1_pour is benchmark-ready with true fluid.",
            "Raw colleague 50k USD directly steps as true PBD fluid without runtime completion.",
            "Render/video appearance alone proves physics correctness.",
            "Native beaker mesh is generally fluid-safe.",
            "S3 kinematic pour, S4 replay, EBench score, policy score, or leaderboard readiness is released.",
        ],
        "s3_kinematic_pour_released": False,
        "benchmark_ready_claim_allowed": False,
        "visual_only_evidence_allowed_for_physics": False,
    }


def summarize_native_mesh_collision_state(stage: Any, mesh_path: str = DEFAULT_NATIVE_MESH_PATH) -> dict[str, Any]:
    prim = stage.GetPrimAtPath(mesh_path)
    if not prim:
        return {"mesh_path": mesh_path, "exists": False}
    return {
        "mesh_path": mesh_path,
        "exists": True,
        "type_name": prim.GetTypeName(),
        "applied_schemas": list(prim.GetAppliedSchemas()),
        "collision_enabled": _read_attr(prim, "physics:collisionEnabled"),
        "approximation": _read_attr(prim, "physics:approximation"),
        "rigid_body_enabled": _read_attr(prim, "physics:rigidBodyEnabled"),
        "kinematic_enabled": _read_attr(prim, "physics:kinematicEnabled"),
        "contact_offset": _read_attr(prim, "physxCollision:contactOffset"),
        "rest_offset": _read_attr(prim, "physxCollision:restOffset"),
        "sdf_resolution": _read_attr(prim, "physxSDFMeshCollision:sdfResolution"),
    }


def apply_native_collider_approximation(
    stage: Any,
    candidate: NativeApproximationCandidate,
    *,
    mesh_path: str = DEFAULT_NATIVE_MESH_PATH,
) -> dict[str, Any]:
    from pxr import UsdPhysics

    prim = stage.GetPrimAtPath(mesh_path)
    if not prim:
        raise ValueError(f"native_mesh_not_found:{mesh_path}")
    pre_state = summarize_native_mesh_collision_state(stage, mesh_path)
    if candidate.variant_id != "RAW_AS_IS":
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            rigid_body = UsdPhysics.RigidBodyAPI.Apply(prim)
            rigid_body.CreateRigidBodyEnabledAttr().Set(False)
            rigid_body.CreateKinematicEnabledAttr().Set(False)
        _apply_static_collision(
            prim,
            approximation=candidate.approximation,
            contact_offset=candidate.contact_offset,
            rest_offset=candidate.rest_offset,
            sdf_resolution=candidate.sdf_resolution,
            sdf_subgrid_resolution=candidate.sdf_subgrid_resolution or 4,
            sdf_margin=candidate.sdf_margin if candidate.sdf_margin is not None else 0.002,
            sdf_narrow_band_thickness=candidate.sdf_narrow_band_thickness or 0.01,
        )
    post_state = summarize_native_mesh_collision_state(stage, mesh_path)
    return {
        "variant_id": candidate.variant_id,
        "mesh_path": mesh_path,
        "approximation": candidate.approximation,
        "sdf_resolution": candidate.sdf_resolution,
        "authored_collision_enabled": bool(post_state.get("collision_enabled")),
        "sweep_authored_collision_enabled": candidate.variant_id != "RAW_AS_IS",
        "pre_state": pre_state,
        "post_state": post_state,
    }


def classify_native_approximation_summary(summary: dict[str, Any], *, variant_id: str) -> dict[str, Any]:
    detail = summary.get("classification") or {}
    readback = summary.get("readback_diagnostics") or {}
    checks = {
        "runtime_step_executed": bool(summary.get("runtime_step_executed")),
        "readback_available": bool(readback.get("readback_available")),
        "readback_position_changed": bool(readback.get("readback_position_changed")),
        "particle_count_final_fraction": _detail_float_at_least(detail, "particle_count_final_fraction", 0.95),
        "source_retention_fraction": _detail_float_at_least(detail, "source_retention_fraction", 0.95),
        "outside_source_count": _detail_int_equals(detail, "outside_source_count", 0),
        "target_count": _detail_int_equals(detail, "target_count", 0),
        "spill_count": _detail_int_equals(detail, "spill_count", 0),
        "below_table_count": _detail_int_equals(detail, "below_table_count", 0),
        "tail_leak_rate_fraction_per_second": _detail_float_less_than(
            detail, "tail_leak_rate_fraction_per_second", 0.02
        ),
        "cpu_collision_fallback_detected": detail.get("cpu_collision_fallback_detected") is False,
        "gpu_collider_unsupported": detail.get("gpu_collider_unsupported") is False,
        "nan_count": _detail_int_equals(detail, "nan_count", 0),
        "fatal_error": "fatal_error" in detail and detail.get("fatal_error") is None,
    }
    static_hold_passed = all(checks.values())
    never_promotable = variant_id in NEVER_PROMOTABLE_VARIANT_IDS
    return {
        "variant_id": variant_id,
        "classification": detail.get("classification"),
        "native_approximation_static_hold_passed": static_hold_passed,
        "promotable_to_repeat_review": bool(static_hold_passed and not never_promotable),
        "promotion_block_reason": "diagnostic_or_negative_control" if static_hold_passed and never_promotable else None,
        "gate_checks": checks,
        "particle_count_final_fraction": float(detail.get("particle_count_final_fraction", 0.0) or 0.0),
        "source_retention_fraction": float(detail.get("source_retention_fraction", 0.0) or 0.0),
        "outside_source_count": int(detail.get("outside_source_count", 0) or 0),
        "target_count": int(detail.get("target_count", 0) or 0),
        "spill_count": int(detail.get("spill_count", 0) or 0),
        "below_table_count": int(detail.get("below_table_count", 0) or 0),
        "tail_leak_rate_fraction_per_second": float(
            detail.get("tail_leak_rate_fraction_per_second", 0.0) or 0.0
        ),
    }


def write_dry_run_authoring_artifacts(
    *,
    usd_path: str | Path,
    out_dir: str | Path,
    manifest_path: str | Path,
    variant_ids: Sequence[str] | None = None,
    mesh_path: str = DEFAULT_NATIVE_MESH_PATH,
) -> dict[str, Any]:
    source = _repo_path(usd_path).resolve()
    out = _repo_path(out_dir).resolve()
    manifest = _repo_path(manifest_path).resolve()
    candidates = _select_candidates(variant_ids)
    candidate_results = []
    for candidate in candidates:
        stage, overlay_layer = _open_variant_overlay_stage(source)
        authoring = apply_native_collider_approximation(stage, candidate, mesh_path=mesh_path)
        variant_dir = out / candidate.variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        overlay_path = variant_dir / "native_collider_approximation_overlay.usda"
        overlay_layer.Export(str(overlay_path))
        result = {
            "variant_id": candidate.variant_id,
            "candidate": asdict(candidate),
            "runtime_step_executed": False,
            "dry_run_authoring_only": True,
            "overlay_usda": str(overlay_path),
            "authoring": authoring,
        }
        _write_json(variant_dir / "variant_summary.json", result)
        candidate_results.append(result)
    payload = {
        "schema_version": 1,
        "manifest_type": "fluid_spike_native_collider_approximation_sweep",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_usd_path": str(source),
        "mesh_path": mesh_path,
        "dry_run_authoring_only": True,
        "candidate_results": candidate_results,
        "candidate_ids": [candidate.variant_id for candidate in candidates],
        "claim_boundary": build_claim_boundary(),
    }
    _write_json(manifest, payload)
    return payload


def write_runtime_aggregate_manifest(
    *,
    runtime_dir: str | Path,
    manifest_path: str | Path,
    variant_ids: Sequence[str] | None = None,
    runtime_suffix: str = "_runtime_512.json",
) -> dict[str, Any]:
    runtime_root = _repo_path(runtime_dir).resolve()
    manifest = _repo_path(manifest_path).resolve()
    candidates = _select_candidates(variant_ids)
    candidate_results = []
    missing_result_paths = []
    for candidate in candidates:
        result_path = runtime_root / f"{candidate.variant_id}{runtime_suffix}"
        if not result_path.exists():
            missing_result_paths.append(str(result_path))
            candidate_results.append(
                {
                    "variant_id": candidate.variant_id,
                    "candidate": asdict(candidate),
                    "runtime_result_path": str(result_path),
                    "runtime_step_executed": False,
                    "runtime_summary_variant_id": None,
                    "variant_identity_matches": None,
                    "classification": "MISSING_RUNTIME_RESULT",
                    "gate": classify_native_approximation_summary({}, variant_id=candidate.variant_id),
                    "closeup_video": {"path": None, "written": False, "frame_count": 0},
                }
            )
            continue
        summary = json.loads(result_path.read_text(encoding="utf-8"))
        runtime_variant_id = (
            ((summary.get("native_collider_approximation") or {}).get("candidate") or {}).get("variant_id")
        )
        variant_identity_matches = runtime_variant_id == candidate.variant_id
        gate = classify_native_approximation_summary(summary, variant_id=candidate.variant_id)
        if not variant_identity_matches:
            gate = {**gate, "native_approximation_static_hold_passed": False, "promotable_to_repeat_review": False}
        classification = summary.get("classification") or {}
        videos = summary.get("videos") or {}
        closeup_video = videos.get("beaker2_closeup_native_material") or {}
        particle_scope = summary.get("particle_scope") or {}
        native_authoring = (summary.get("native_collider_approximation") or {}).get("authoring")
        candidate_results.append(
            {
                "variant_id": candidate.variant_id,
                "candidate": asdict(candidate),
                "runtime_result_path": str(result_path),
                "runtime_step_executed": bool(summary.get("runtime_step_executed")),
                "runtime_summary_variant_id": runtime_variant_id,
                "variant_identity_matches": variant_identity_matches,
                "readback_diagnostics": summary.get("readback_diagnostics") or {},
                "selected_particle_count": particle_scope.get("selected_particle_count")
                or summary.get("selected_particle_count"),
                "source_particle_count": particle_scope.get("original_particle_count")
                or summary.get("source_particle_count"),
                "steps": summary.get("steps"),
                "classification": classification.get("classification"),
                "source_retention_fraction": classification.get("source_retention_fraction"),
                "outside_source_count": classification.get("outside_source_count"),
                "target_count": classification.get("target_count"),
                "spill_count": classification.get("spill_count"),
                "below_table_count": classification.get("below_table_count"),
                "tail_leak_rate_fraction_per_second": classification.get("tail_leak_rate_fraction_per_second"),
                "cpu_collision_fallback_detected": classification.get("cpu_collision_fallback_detected"),
                "gpu_collider_unsupported": classification.get("gpu_collider_unsupported"),
                "nan_count": classification.get("nan_count"),
                "fatal_error": classification.get("fatal_error"),
                "gate": gate,
                "closeup_video": {
                    "path": closeup_video.get("path"),
                    "written": bool(closeup_video.get("written")),
                    "frame_count": int(closeup_video.get("frame_count") or 0),
                },
                "native_collider_authoring": native_authoring,
            }
        )
    static_hold_pass_ids = [
        item["variant_id"] for item in candidate_results if item["gate"]["native_approximation_static_hold_passed"]
    ]
    promotable_ids = [item["variant_id"] for item in candidate_results if item["gate"]["promotable_to_repeat_review"]]
    failed_to_execute_ids = [item["variant_id"] for item in candidate_results if not item["runtime_step_executed"]]
    mismatched_variant_ids = [
        item["variant_id"] for item in candidate_results if item.get("variant_identity_matches") is False
    ]
    payload = {
        "schema_version": 1,
        "manifest_type": "fluid_spike_native_collider_approximation_runtime_sweep",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_dir": str(runtime_root),
        "runtime_suffix": runtime_suffix,
        "source_usd_path": DEFAULT_USD,
        "mesh_path": DEFAULT_NATIVE_MESH_PATH,
        "candidate_results": candidate_results,
        "candidate_ids": [candidate.variant_id for candidate in candidates],
        "runtime_step_executed_count": sum(1 for item in candidate_results if item["runtime_step_executed"]),
        "failed_to_execute_variant_ids": failed_to_execute_ids,
        "static_hold_pass_count": len(static_hold_pass_ids),
        "static_hold_pass_variant_ids": static_hold_pass_ids,
        "promotable_variant_ids": promotable_ids,
        "missing_result_paths": missing_result_paths,
        "mismatched_variant_ids": mismatched_variant_ids,
        "all_runtime_results_executed": len(failed_to_execute_ids) == 0,
        "all_runtime_variant_identities_match": len(mismatched_variant_ids) == 0,
        "all_tested_candidates_failed_static_hold": (
            len(static_hold_pass_ids) == 0
            and not missing_result_paths
            and len(failed_to_execute_ids) == 0
            and len(mismatched_variant_ids) == 0
        ),
        "claim_boundary": build_claim_boundary(),
    }
    _write_json(manifest, payload)
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", default=DEFAULT_USD)
    parser.add_argument("--out-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--mesh-path", default=DEFAULT_NATIVE_MESH_PATH)
    parser.add_argument("--variant", action="append", dest="variants", default=None)
    parser.add_argument("--dry-run-authoring", action="store_true")
    parser.add_argument("--aggregate-runtime", action="store_true")
    parser.add_argument("--runtime-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--runtime-suffix", default="_runtime_512.json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.aggregate_runtime:
        manifest = args.manifest
        if manifest == DEFAULT_MANIFEST:
            manifest = DEFAULT_RUNTIME_MANIFEST
        payload = write_runtime_aggregate_manifest(
            runtime_dir=args.runtime_dir,
            manifest_path=manifest,
            variant_ids=args.variants,
            runtime_suffix=args.runtime_suffix,
        )
        print(json.dumps(_json_safe(payload), indent=2, sort_keys=True))
        return 0
    if not args.dry_run_authoring:
        raise SystemExit("runtime_sweep_cli_requires_--dry-run-authoring_or_use_native_runner_variant_arg")
    payload = write_dry_run_authoring_artifacts(
        usd_path=args.usd,
        out_dir=args.out_dir,
        manifest_path=args.manifest,
        variant_ids=args.variants,
        mesh_path=args.mesh_path,
    )
    print(json.dumps(_json_safe(payload), indent=2, sort_keys=True))
    return 0


def _read_attr(prim: Any, attr_name: str) -> Any:
    attr = prim.GetAttribute(attr_name)
    return attr.Get() if attr else None


def _select_candidates(variant_ids: Sequence[str] | None) -> list[NativeApproximationCandidate]:
    candidates = build_native_approximation_sweep()
    if not variant_ids:
        return candidates
    allowed = {candidate.variant_id: candidate for candidate in candidates}
    missing = [variant_id for variant_id in variant_ids if variant_id not in allowed]
    if missing:
        raise ValueError(f"unknown_native_approximation_variants:{','.join(missing)}")
    return [allowed[variant_id] for variant_id in variant_ids]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _detail_float_at_least(detail: dict[str, Any], key: str, threshold: float) -> bool:
    if key not in detail:
        return False
    try:
        return float(detail[key]) >= threshold
    except (TypeError, ValueError):
        return False


def _detail_float_less_than(detail: dict[str, Any], key: str, threshold: float) -> bool:
    if key not in detail:
        return False
    try:
        return float(detail[key]) < threshold
    except (TypeError, ValueError):
        return False


def _detail_int_equals(detail: dict[str, Any], key: str, expected: int) -> bool:
    if key not in detail:
        return False
    try:
        return int(detail[key]) == expected
    except (TypeError, ValueError):
        return False


def _open_variant_overlay_stage(source: Path) -> tuple[Any, Any]:
    from pxr import Sdf, Usd

    overlay_layer = Sdf.Layer.CreateAnonymous("native_collider_approximation_overlay.usda")
    overlay_layer.subLayerPaths.append(str(source))
    stage = Usd.Stage.Open(overlay_layer, Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError(f"usd_stage_open_failed:{source}")
    stage.SetEditTarget(overlay_layer)
    return stage, overlay_layer


def _repo_path(path: str | Path) -> Path:
    normalized = Path(path)
    return normalized if normalized.is_absolute() else REPO_ROOT / normalized


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


if __name__ == "__main__":
    raise SystemExit(main())
