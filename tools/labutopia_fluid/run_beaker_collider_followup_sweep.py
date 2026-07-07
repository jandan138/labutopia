#!/usr/bin/env python3
"""Run S2F follow-up sweeps for PhysX/PBD beaker collider recovery."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import traceback
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.run_beaker_collider_smoke import (
    CLASSIFICATION_CONTRACT_VERSION,
    ColliderConfig,
    VariantSpec,
    _gpu_probe,
    _run_variant,
)
from tools.labutopia_fluid.run_standalone_particle_smoke import _write_json


DEFAULT_PARENT_MANIFEST = "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"
DEFAULT_BASELINE_FREEZE_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
)
DEFAULT_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_isaacsim41_ebench_s2_followup_c2_proxy_sweep_20260707_001"
)
DEFAULT_MANIFEST_PATH = (
    "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_c2_proxy_sweep_20260707.json"
)
DEFAULT_SCENE_DIR = "assets/chemistry_lab/lab_001_fluid_spike/colliders_s2f1"
DEFAULT_NATIVE_USD = "assets/chemistry_lab/lab_001/lab_001.usd"
FOLLOWUP_CONTRACT_VERSION = "s2f1_c2_proxy_sweep_v1"
FOLLOWUP_CLASSIFICATIONS = {
    "PASS_SOURCE_HOLD",
    "FAIL_CONTAINER_LEAK",
    "FAIL_GPU_COLLIDER_UNSUPPORTED",
    "FAIL_CPU_COLLISION_FALLBACK",
    "FAIL_PARTICLE_EXPLOSION",
    "FAIL_READBACK_UNAVAILABLE",
    "FAIL_PERF_BUDGET_EXCEEDED",
    "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE",
}


@dataclass(frozen=True)
class C2ProxyCandidate:
    candidate_id: str
    panel_count: int
    wall_thickness: float
    bottom_overlap: float
    particle_contact_offset: float
    collider_contact_offset: float
    collider_rest_offset: float
    initial_radial_velocity: float

    def to_config(self, *, base: ColliderConfig | None = None) -> ColliderConfig:
        config = base or ColliderConfig()
        return replace(
            config,
            wall_thickness=self.wall_thickness,
            bottom_overlap=self.bottom_overlap,
            particle_contact_offset=self.particle_contact_offset,
            collider_contact_offset=self.collider_contact_offset,
            collider_rest_offset=self.collider_rest_offset,
            initial_radial_velocity=self.initial_radial_velocity,
        )

    def to_variant_spec(self) -> VariantSpec:
        return VariantSpec(
            variant_id=self.candidate_id,
            name="c2_proxy_followup",
            description=(
                "S2F1 C2-derived segmented convex wall proxy with swept panel count, "
                "wall thickness, bottom overlap, and contact offsets."
            ),
            setup="s2f1_c2_proxy_sweep",
            collider_count=self.panel_count + 1,
            collision_approximation="convex_panel_boxes",
            source_kind="procedural_proxy",
            panel_count=self.panel_count,
        )


def followup_phase_specs() -> dict[str, dict[str, Any]]:
    return {
        "S2F0_BASELINE_FREEZE": {
            "candidate_prefix": "S2",
            "status": "COMPLETE",
            "description": "Frozen S2 collider matrix baseline.",
        },
        "S2F1_C2_PROXY_SWEEP": {
            "candidate_prefix": "C2A",
            "status": "ACTIVE",
            "description": "Bounded C2-derived segmented proxy sweep.",
        },
        "S2F2_VELOCITY_CONTACT_OFFSET": {
            "candidate_prefix": "C2A",
            "status": "PENDING",
            "description": "Velocity/contact-offset isolation after S2F1.",
        },
        "S2F3_C3_SDF_SWEEP": {
            "candidate_prefix": "C3A",
            "status": "PENDING",
            "description": "SDF open beaker cooking sweep.",
        },
        "S2F4_C4_NATIVE_MESH_ISOLATION": {
            "candidate_prefix": "C4A",
            "status": "PENDING",
            "description": "Native beaker mesh isolation.",
        },
        "S2F5_PROMOTION_REVIEW": {
            "candidate_prefix": "S2F",
            "status": "PENDING",
            "description": "Promotion review before S3 release.",
        },
    }


def build_c2_proxy_sweep(*, limit: int = 12) -> list[C2ProxyCandidate]:
    rows = [
        (24, 0.010, 0.000, 0.0045, 0.002, 0.000, 0.08),
        (24, 0.014, 0.003, 0.0060, 0.004, -0.001, 0.04),
        (24, 0.018, 0.006, 0.0075, 0.006, 0.000, 0.02),
        (32, 0.010, 0.003, 0.0075, 0.006, -0.001, 0.08),
        (32, 0.014, 0.006, 0.0045, 0.002, 0.000, 0.04),
        (32, 0.018, 0.000, 0.0060, 0.004, -0.001, 0.02),
        (48, 0.010, 0.006, 0.0060, 0.006, 0.000, 0.04),
        (48, 0.014, 0.000, 0.0075, 0.002, -0.001, 0.02),
        (48, 0.018, 0.003, 0.0045, 0.004, 0.000, 0.08),
        (32, 0.014, 0.003, 0.0060, 0.006, -0.001, 0.04),
        (48, 0.018, 0.006, 0.0075, 0.006, -0.001, 0.02),
        (24, 0.018, 0.006, 0.0075, 0.006, -0.001, 0.08),
    ]
    candidates: list[C2ProxyCandidate] = []
    for index, row in enumerate(rows[:limit], start=1):
        candidates.append(
            C2ProxyCandidate(
                candidate_id=f"C2A_{index:03d}",
                panel_count=row[0],
                wall_thickness=row[1],
                bottom_overlap=row[2],
                particle_contact_offset=row[3],
                collider_contact_offset=row[4],
                collider_rest_offset=row[5],
                initial_radial_velocity=row[6],
            )
        )
    return candidates


def build_velocity_contact_offset_sweep() -> list[C2ProxyCandidate]:
    base = build_c2_proxy_sweep(limit=1)[0]
    rows = [
        (0.02, 0.0045, 0.002, -0.001),
        (0.04, 0.0060, 0.004, 0.000),
        (0.08, 0.0075, 0.006, -0.001),
    ]
    return [
        C2ProxyCandidate(
            candidate_id=f"C2A_VEL_{index:03d}",
            panel_count=base.panel_count,
            wall_thickness=base.wall_thickness,
            bottom_overlap=base.bottom_overlap,
            particle_contact_offset=particle_contact_offset,
            collider_contact_offset=collider_contact_offset,
            collider_rest_offset=collider_rest_offset,
            initial_radial_velocity=initial_radial_velocity,
        )
        for index, (
            initial_radial_velocity,
            particle_contact_offset,
            collider_contact_offset,
            collider_rest_offset,
        ) in enumerate(rows, start=1)
    ]


def _pass_criteria(
    *,
    source_retention_fraction: float,
    particle_count_final_fraction: float,
    outside_source_count: int,
    target_count: int,
    spill_count: int,
    below_table_count: int,
    tail_leak_rate_fraction_per_second: float,
    cpu_collision_fallback_detected: bool,
    gpu_collider_unsupported: bool,
    nan_count: int,
    non_physical_parameter_dependence: bool,
) -> dict[str, bool]:
    return {
        "source_retention_fraction_ge_0_95": source_retention_fraction >= 0.95,
        "particle_count_final_fraction_ge_0_95": particle_count_final_fraction >= 0.95,
        "outside_source_count_eq_zero": outside_source_count == 0,
        "target_count_eq_zero": target_count == 0,
        "spill_count_eq_zero": spill_count == 0,
        "below_table_count_eq_zero": below_table_count == 0,
        "tail_leak_rate_lt_0_02": tail_leak_rate_fraction_per_second < 0.02,
        "cpu_collision_fallback_detected_false": not cpu_collision_fallback_detected,
        "gpu_collider_unsupported_false": not gpu_collider_unsupported,
        "nan_count_eq_zero": nan_count == 0,
        "non_physical_parameter_dependence_false": not non_physical_parameter_dependence,
    }


def classify_followup_candidate(
    *,
    candidate_id: str,
    source_retention_fraction: float,
    particle_count_final_fraction: float,
    outside_source_count: int,
    target_count: int,
    spill_count: int,
    below_table_count: int,
    tail_leak_rate_fraction_per_second: float,
    cpu_collision_fallback_detected: bool,
    gpu_collider_unsupported: bool,
    nan_count: int,
    non_physical_parameter_dependence: bool,
    fatal_error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    criteria = _pass_criteria(
        source_retention_fraction=source_retention_fraction,
        particle_count_final_fraction=particle_count_final_fraction,
        outside_source_count=outside_source_count,
        target_count=target_count,
        spill_count=spill_count,
        below_table_count=below_table_count,
        tail_leak_rate_fraction_per_second=tail_leak_rate_fraction_per_second,
        cpu_collision_fallback_detected=cpu_collision_fallback_detected,
        gpu_collider_unsupported=gpu_collider_unsupported,
        nan_count=nan_count,
        non_physical_parameter_dependence=non_physical_parameter_dependence,
    )
    if fatal_error is not None:
        classification = "FAIL_READBACK_UNAVAILABLE"
    elif gpu_collider_unsupported:
        classification = "FAIL_GPU_COLLIDER_UNSUPPORTED"
    elif cpu_collision_fallback_detected:
        classification = "FAIL_CPU_COLLISION_FALLBACK"
    elif nan_count != 0:
        classification = "FAIL_PARTICLE_EXPLOSION"
    elif non_physical_parameter_dependence:
        classification = "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE"
    elif all(criteria.values()):
        classification = "PASS_SOURCE_HOLD"
    else:
        classification = "FAIL_CONTAINER_LEAK"

    assert classification in FOLLOWUP_CLASSIFICATIONS
    return {
        "candidate_id": candidate_id,
        "classification": classification,
        "source_retention_fraction": source_retention_fraction,
        "particle_count_final_fraction": particle_count_final_fraction,
        "outside_source_count": outside_source_count,
        "target_count": target_count,
        "spill_count": spill_count,
        "below_table_count": below_table_count,
        "tail_leak_rate_fraction_per_second": tail_leak_rate_fraction_per_second,
        "cpu_collision_fallback_detected": bool(cpu_collision_fallback_detected),
        "gpu_collider_unsupported": bool(gpu_collider_unsupported),
        "nan_count": nan_count,
        "non_physical_parameter_dependence": bool(non_physical_parameter_dependence),
        "pass_criteria": criteria,
        "fatal_error": fatal_error,
    }


def rank_followup_candidates(candidate_results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    passed = [result for result in candidate_results if result.get("classification") == "PASS_SOURCE_HOLD"]
    passed.sort(
        key=lambda result: (
            -float(result.get("source_retention_fraction", 0.0)),
            int(result.get("outside_source_count", 999999)),
            int(result.get("spill_count", 999999)),
            int(result.get("below_table_count", 999999)),
            str(result.get("candidate_id", "")),
        )
    )
    best_for_s3 = [str(result["candidate_id"]) for result in passed]
    return {
        "best_for_s3": best_for_s3,
        "s2f1_status": "GO_NEXT" if best_for_s3 else "STOP_WITH_EVIDENCE",
        "reason": "at_least_one_c2a_candidate_passed" if best_for_s3 else "no_c2a_candidate_passed",
    }


def near_pass_candidates_for_s2f2(candidate_results: Sequence[dict[str, Any]]) -> list[str]:
    near_pass = [
        result
        for result in candidate_results
        if result.get("classification") == "FAIL_CONTAINER_LEAK"
        and float(result.get("source_retention_fraction", 0.0)) >= 0.95
        and not result.get("cpu_collision_fallback_detected")
        and not result.get("gpu_collider_unsupported")
        and not result.get("non_physical_parameter_dependence")
        and int(result.get("nan_count", 0)) == 0
    ]
    near_pass.sort(
        key=lambda result: (
            -float(result.get("source_retention_fraction", 0.0)),
            int(result.get("outside_source_count", 999999)),
            int(result.get("spill_count", 999999)),
            int(result.get("below_table_count", 999999)),
            str(result.get("candidate_id", "")),
        )
    )
    return [str(result["candidate_id"]) for result in near_pass]


def scan_runtime_warnings(artifact_dir: Path) -> dict[str, Any]:
    patterns = {
        "cpu_fallback": ("cpu collision fallback", "cpu fallback"),
        "gpu_unsupported": ("gpu collider unsupported", "gpu unsupported"),
        "physx_error": ("[error] [omni.physx", "physx error"),
        "headless_window_warning": ("glfw initialization failed", "failed to open the default display"),
        "material_binding_scope_warning": ("material:binding", "outside the scope of the reference"),
        "sdf_warning": ("sdf warning", "sdf error", "sdf cooking error", "sdf cooking warning"),
    }
    counts = {key: 0 for key in patterns}
    examples: dict[str, list[dict[str, Any]]] = {key: [] for key in patterns}
    warning_line_count = 0
    source_files = {
        "server_stdout": artifact_dir / "server.stdout.txt",
        "server_stderr": artifact_dir / "server.stderr.txt",
    }
    for source_name, path in source_files.items():
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            line_lower = line.lower()
            if "warning" in line_lower or "error" in line_lower:
                warning_line_count += 1
            for key, terms in patterns.items():
                if any(term in line_lower for term in terms):
                    counts[key] += 1
                    if len(examples[key]) < 8:
                        examples[key].append(
                            {
                                "source": source_name,
                                "line": line_number,
                                "text": line[:500],
                            }
                        )
    blocking = bool(counts["cpu_fallback"] or counts["gpu_unsupported"] or counts["physx_error"])
    return {
        "schema_version": 1,
        "manifest_type": "true_physx_pbd_fluid_spike_s2f1_runtime_warning_scan",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "blocking_runtime_warning_detected": blocking,
        "pattern_counts": counts,
        "pattern_examples": examples,
        "source_files": {key: str(path) for key, path in source_files.items()},
        "warning_line_count": warning_line_count,
        "notes": [
            "Artifact-level stdout/stderr warning scan is authoritative for S2F1 release review.",
            "Headless GLFW/display warnings are expected in no-window IsaacSim runs.",
        ],
    }


def _candidate_plan(candidates: Sequence[C2ProxyCandidate]) -> list[dict[str, Any]]:
    return [asdict(candidate) for candidate in candidates]


def _candidate_result_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    detail = summary["classification_detail"]
    result = classify_followup_candidate(
        candidate_id=summary["variant"]["variant_id"],
        source_retention_fraction=float(detail["source_retention_fraction"]),
        particle_count_final_fraction=float(detail["particle_count_final_fraction"]),
        outside_source_count=int(detail["outside_source_count"]),
        target_count=int(detail["target_count"]),
        spill_count=int(detail["spill_count"]),
        below_table_count=int(detail["below_table_count"]),
        tail_leak_rate_fraction_per_second=float(detail["tail_leak_rate_fraction_per_second"]),
        cpu_collision_fallback_detected=bool(detail["cpu_collision_fallback_detected"]),
        gpu_collider_unsupported=bool(detail["gpu_collider_unsupported"]),
        nan_count=int(detail["nan_count"]),
        non_physical_parameter_dependence=False,
        fatal_error=detail.get("fatal_error"),
    )
    result.update(
        {
            "artifact_dir": summary["artifact_dir"],
            "scene_path": summary["scene_path"],
            "variant_summary": str(Path(summary["artifact_dir"]) / "variant_summary.json"),
        }
    )
    return result


def load_candidate_results_from_artifacts(artifact_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for summary_path in sorted(artifact_dir.glob("C2A_*/variant_summary.json")):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        result = _candidate_result_from_summary(summary)
        result["variant_summary"] = str(summary_path)
        results.append(result)
    return results


def _load_existing_manifest(manifest_path: Path) -> dict[str, Any] | None:
    if not manifest_path.exists():
        return None
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _dedupe_commands(commands: Sequence[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for command in commands:
        if not command or command in seen:
            continue
        deduped.append(command)
        seen.add(command)
    return deduped


def _command_without_flag(command: str, flag: str) -> str:
    parts = command.split()
    return " ".join(part for part in parts if part != flag)


def _command_history(previous_manifest: dict[str, Any] | None, current_command: str) -> dict[str, list[str]]:
    previous_commands = []
    if previous_manifest:
        previous_commands = [str(command) for command in previous_manifest.get("commands", [])]

    current_kind = "runtime"
    if "--summarize-existing" in current_command:
        current_kind = "summary"
    elif "--plan-only" in current_command:
        current_kind = "plan"

    inferred_runtime_command = None
    if current_kind == "summary":
        inferred_runtime_command = _command_without_flag(current_command, "--summarize-existing")

    runtime_commands = _dedupe_commands(
        [
            *[command for command in previous_commands if "--summarize-existing" not in command and "--plan-only" not in command],
            inferred_runtime_command,
            current_command if current_kind == "runtime" else None,
        ]
    )
    plan_commands = _dedupe_commands(
        [
            *[command for command in previous_commands if "--plan-only" in command],
            current_command if current_kind == "plan" else None,
        ]
    )
    summary_commands = _dedupe_commands(
        [
            *[command for command in previous_commands if "--summarize-existing" in command],
            current_command if current_kind == "summary" else None,
        ]
    )
    return {
        "commands": [*runtime_commands, *plan_commands, *summary_commands],
        "runtime_commands": runtime_commands,
        "plan_commands": plan_commands,
        "summary_commands": summary_commands,
    }


def _runtime_warning_gate(runtime_warning_scan: dict[str, Any] | None) -> dict[str, Any]:
    blocking = bool(runtime_warning_scan and runtime_warning_scan.get("blocking_runtime_warning_detected"))
    return {
        "required_blocking_runtime_warning_detected": False,
        "blocking_runtime_warning_detected": blocking,
        "passed": not blocking,
    }


def write_followup_manifest(
    manifest_path: Path,
    *,
    phase: str,
    parent_manifest: Path,
    baseline_freeze_manifest: Path,
    artifact_dir: Path,
    candidates: Sequence[C2ProxyCandidate],
    candidate_results: Sequence[dict[str, Any]],
    command: str,
    runtime_warning_scan: dict[str, Any] | None,
    fatal_error: dict[str, Any] | None = None,
    previous_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ranking = rank_followup_candidates(candidate_results)
    near_pass_for_s2f2 = near_pass_candidates_for_s2f2(candidate_results)
    warning_gate = _runtime_warning_gate(runtime_warning_scan)
    if not warning_gate["passed"]:
        ranking = {
            "best_for_s3": [],
            "s2f1_status": "STOP_WITH_EVIDENCE",
            "reason": "blocking_runtime_warning_detected",
        }
    if not warning_gate["passed"]:
        status = "STOP_WITH_EVIDENCE"
    elif not candidate_results and fatal_error is None:
        status = "PLAN_READY"
    else:
        status = ranking["s2f1_status"]
    command_history = _command_history(previous_manifest, command)
    manifest = {
        "schema_version": 1,
        "manifest_type": "true_physx_pbd_fluid_spike_s2f1_c2_proxy_sweep",
        "stage": phase,
        "status": status,
        "reason": "candidate_plan_written" if status == "PLAN_READY" else ranking["reason"],
        "run_id": artifact_dir.name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract_version": FOLLOWUP_CONTRACT_VERSION,
        "classification_contract_version": CLASSIFICATION_CONTRACT_VERSION,
        "parent_s2_manifest": str(parent_manifest),
        "baseline_freeze_manifest": str(baseline_freeze_manifest),
        "artifact_dir": str(artifact_dir),
        "commands": command_history["commands"],
        "runtime_commands": command_history["runtime_commands"],
        "plan_commands": command_history["plan_commands"],
        "summary_commands": command_history["summary_commands"],
        "target_runtime": {
            "python": sys.executable,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "accept_eula": os.environ.get("ACCEPT_EULA"),
            "omni_kit_accept_eula": os.environ.get("OMNI_KIT_ACCEPT_EULA"),
            "gpu_probe": _gpu_probe(),
        },
        "phase_specs": followup_phase_specs(),
        "candidate_plan": _candidate_plan(candidates),
        "candidate_count": len(candidates),
        "candidate_results": list(candidate_results),
        "best_for_s3": ranking["best_for_s3"],
        "near_pass_for_s2f2": near_pass_for_s2f2,
        "s3_kinematic_pour_released": False,
        "runtime_warning_scan": runtime_warning_scan,
        "runtime_warning_gate": warning_gate,
        "pass_criteria": {
            "required_source_retention_fraction": 0.95,
            "required_particle_count_final_fraction": 0.95,
            "required_outside_source_count": 0,
            "required_target_count": 0,
            "required_spill_count": 0,
            "required_below_table_count": 0,
            "required_tail_leak_rate_fraction_per_second_lt": 0.02,
            "required_cpu_collision_fallback_detected": False,
            "required_gpu_collider_unsupported": False,
            "required_nan_count": 0,
            "required_non_physical_parameter_dependence": False,
            "required_blocking_runtime_warning_detected": False,
        },
        "allowed_claims": [
            "S2F1 C2 proxy sweep candidate set is bounded and recorded.",
            "S2F1 ran C2-derived proxy collider variants in standalone IsaacSim41."
            if candidate_results
            else "S2F1 candidate plan is ready before runtime launch.",
        ],
        "blocked_claims": [
            "S3 kinematic pour is released",
            "level1_pour has true fluid today",
            "fluid is EBench-scoreable",
            "policy score claim",
            "official leaderboard claim",
            "diagnostic projections equal product-quality render",
        ],
        "next_stage": {
            "id": "S2F5_PROMOTION_REVIEW" if ranking["best_for_s3"] else "S2F2_VELOCITY_CONTACT_OFFSET",
            "variants": ranking["best_for_s3"] if ranking["best_for_s3"] else near_pass_for_s2f2,
        },
        "fatal_error": fatal_error,
    }
    if runtime_warning_scan is not None:
        _write_json(artifact_dir / "runtime_warning_scan.json", runtime_warning_scan)
    _write_json(manifest_path, manifest)
    return manifest


def _run_c2_proxy_sweep(
    *,
    candidates: Sequence[C2ProxyCandidate],
    base_config: ColliderConfig,
    artifact_dir: Path,
    scene_dir: Path,
    native_usd: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        config = candidate.to_config(base=base_config)
        spec = candidate.to_variant_spec()
        scene_path = scene_dir / f"{candidate.candidate_id.lower()}_c2_proxy_followup.usda"
        try:
            summary = _run_variant(
                config=config,
                spec=spec,
                artifact_dir=artifact_dir,
                scene_path=scene_path,
                native_usd=native_usd,
            )
            result = _candidate_result_from_summary(summary)
        except Exception as exc:
            fatal_error = {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback_tail": traceback.format_exc()[-6000:],
            }
            candidate_dir = artifact_dir / candidate.candidate_id
            candidate_dir.mkdir(parents=True, exist_ok=True)
            result = classify_followup_candidate(
                candidate_id=candidate.candidate_id,
                source_retention_fraction=0.0,
                particle_count_final_fraction=0.0,
                outside_source_count=0,
                target_count=0,
                spill_count=0,
                below_table_count=0,
                tail_leak_rate_fraction_per_second=999.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=False,
                fatal_error=fatal_error,
            )
            result.update(
                {
                    "artifact_dir": str(candidate_dir),
                    "scene_path": str(scene_path),
                    "variant_summary": str(candidate_dir / "variant_summary.json"),
                }
            )
            _write_json(candidate_dir / "variant_summary.json", result)
        results.append(result)
    return results


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", default="S2F1_C2_PROXY_SWEEP")
    parser.add_argument("--parent-manifest", default=DEFAULT_PARENT_MANIFEST)
    parser.add_argument("--baseline-freeze-manifest", default=DEFAULT_BASELINE_FREEZE_MANIFEST)
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--manifest-path", default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--scene-dir", default=DEFAULT_SCENE_DIR)
    parser.add_argument("--native-usd", default=DEFAULT_NATIVE_USD)
    parser.add_argument("--candidate-limit", type=int, default=12)
    parser.add_argument("--particle-count", type=int, default=ColliderConfig.particle_count)
    parser.add_argument("--steps", type=int, default=ColliderConfig.steps)
    parser.add_argument("--width", type=int, default=ColliderConfig.render_width)
    parser.add_argument("--height", type=int, default=ColliderConfig.render_height)
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--summarize-existing", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.phase != "S2F1_C2_PROXY_SWEEP":
        raise SystemExit(f"unsupported phase for this runner: {args.phase}")

    candidates = build_c2_proxy_sweep(limit=args.candidate_limit)
    base_config = ColliderConfig(
        particle_count=args.particle_count,
        steps=args.steps,
        render_width=args.width,
        render_height=args.height,
    )
    artifact_dir = Path(args.artifact_dir)
    scene_dir = Path(args.scene_dir)
    manifest_path = Path(args.manifest_path)
    parent_manifest = Path(args.parent_manifest)
    baseline_freeze_manifest = Path(args.baseline_freeze_manifest)
    native_usd = Path(args.native_usd).resolve()
    command = " ".join([sys.executable, Path(__file__).as_posix(), *argv])
    previous_manifest = _load_existing_manifest(manifest_path)

    artifact_dir.mkdir(parents=True, exist_ok=True)
    scene_dir.mkdir(parents=True, exist_ok=True)
    if not args.summarize_existing:
        write_followup_manifest(
            manifest_path,
            phase=args.phase,
            parent_manifest=parent_manifest,
            baseline_freeze_manifest=baseline_freeze_manifest,
            artifact_dir=artifact_dir,
            candidates=candidates,
            candidate_results=[],
            command=command,
            runtime_warning_scan=None,
            previous_manifest=previous_manifest,
        )
    if args.plan_only:
        print(f"S2F1 candidate plan manifest={manifest_path}", flush=True)
        return 0
    if args.summarize_existing:
        candidate_results = load_candidate_results_from_artifacts(artifact_dir)
        manifest = write_followup_manifest(
            manifest_path,
            phase=args.phase,
            parent_manifest=parent_manifest,
            baseline_freeze_manifest=baseline_freeze_manifest,
            artifact_dir=artifact_dir,
            candidates=candidates,
            candidate_results=candidate_results,
            command=command,
            runtime_warning_scan=scan_runtime_warnings(artifact_dir),
            previous_manifest=previous_manifest,
        )
        print(
            "S2F1 C2 proxy sweep summary "
            f"status={manifest['status']} best_for_s3={manifest['best_for_s3']} "
            f"manifest={manifest_path}",
            flush=True,
        )
        return 0

    app = None
    fatal_error = None
    candidate_results: list[dict[str, Any]] = []
    final_manifest: dict[str, Any] | None = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": bool(args.headless), "width": args.width, "height": args.height})
        candidate_results = _run_c2_proxy_sweep(
            candidates=candidates,
            base_config=base_config,
            artifact_dir=artifact_dir,
            scene_dir=scene_dir,
            native_usd=native_usd,
        )
        final_manifest = write_followup_manifest(
            manifest_path,
            phase=args.phase,
            parent_manifest=parent_manifest,
            baseline_freeze_manifest=baseline_freeze_manifest,
            artifact_dir=artifact_dir,
            candidates=candidates,
            candidate_results=candidate_results,
            command=command,
            runtime_warning_scan=scan_runtime_warnings(artifact_dir),
            previous_manifest=_load_existing_manifest(manifest_path),
        )
        print(
            "S2F1 C2 proxy sweep "
            f"status={final_manifest['status']} best_for_s3={final_manifest['best_for_s3']} "
            f"manifest={manifest_path}",
            flush=True,
        )
    except Exception as exc:
        fatal_error = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback_tail": traceback.format_exc()[-6000:],
        }
    finally:
        if app is not None:
            app.close()

    if final_manifest is None:
        write_followup_manifest(
            manifest_path,
            phase=args.phase,
            parent_manifest=parent_manifest,
            baseline_freeze_manifest=baseline_freeze_manifest,
            artifact_dir=artifact_dir,
            candidates=candidates,
            candidate_results=candidate_results,
            command=command,
            runtime_warning_scan=scan_runtime_warnings(artifact_dir),
            fatal_error=fatal_error,
            previous_manifest=_load_existing_manifest(manifest_path),
        )
    return 0 if fatal_error is None else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
