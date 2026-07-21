#!/usr/bin/env python3
"""Run an immutable no-robot dry or filled passive-stability probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    REPO_ROOT / "config/level1_pour_online_fluid_native_expert_contact_v1.yaml"
)
MANIFEST_TYPE = "contact_grasp_passive_stability_probe_v1"
COMPARISON_MANIFEST_TYPE = "contact_grasp_passive_stability_comparison_v1"
SETTLE_AUDIT_MANIFEST_TYPE = "contact_grasp_extended_settle_audit_v1"
PARTITION_NAMES = (
    "source",
    "target",
    "transit",
    "tabletop_spill",
    "below_table",
    "nonfinite",
)
NON_SOURCE_PARTITION_NAMES = PARTITION_NAMES[1:]
SOURCE_TRACE_BASENAME = "source_trace.npz"
PARTICLE_TRACE_BASENAME = "particle_trace.npz"
PROVISIONAL_REPORT_BASENAME = "provisional_report.json"
FINAL_REPORT_BASENAME = "report.json"


def _finite_positive(value: Any, *, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
    ):
        raise ValueError(f"{name}_invalid")
    return float(value)


def _nonnegative_int(value: Any, *, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name}_invalid")
    return value


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_json_bytes(value: Any, *, indent: int | None = None) -> bytes:
    def native(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): native(candidate) for key, candidate in item.items()}
        if isinstance(item, (list, tuple)):
            return [native(candidate) for candidate in item]
        if isinstance(item, np.ndarray):
            return native(item.tolist())
        if isinstance(item, np.generic):
            return native(item.item())
        if isinstance(item, Path):
            return str(item)
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("passive_probe_json_nonfinite")
        return item

    try:
        encoded = json.dumps(
            native(value),
            allow_nan=False,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
            sort_keys=True,
        )
    except ValueError as exc:
        raise ValueError("passive_probe_json_nonfinite") from exc
    return (encoded + "\n").encode("utf-8")


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value).rstrip(b"\n")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _publish_temporary_file(temporary_path: Path, output_path: Path) -> None:
    try:
        os.link(temporary_path, output_path)
    except FileExistsError as exc:
        raise FileExistsError(f"passive_probe_output_exists:{output_path}") from exc
    directory_descriptor = os.open(output_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def atomic_create_json(path: str | os.PathLike[str], value: Mapping[str, Any]) -> None:
    """Publish a complete JSON object without ever replacing an existing path."""
    if not isinstance(value, Mapping):
        raise TypeError("passive_probe_json_mapping_required")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json_bytes(value, indent=2)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _publish_temporary_file(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_create_npz(
    path: str | os.PathLike[str],
    arrays: Mapping[str, Any],
) -> None:
    if not isinstance(arrays, Mapping) or not arrays:
        raise ValueError("passive_probe_npz_arrays_required")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            np.savez_compressed(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        _publish_temporary_file(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def validate_trace_schedule(
    records: Sequence[Mapping[str, Any]],
    *,
    physics_dt: Any,
    pre_roll_steps: int,
    hold_steps: int,
) -> dict[str, Any]:
    dt = _finite_positive(physics_dt, name="passive_trace_schedule_physics_dt")
    if type(pre_roll_steps) is not int or pre_roll_steps <= 0:
        raise ValueError("passive_trace_schedule_pre_roll_steps_invalid")
    if type(hold_steps) is not int or hold_steps <= 0:
        raise ValueError("passive_trace_schedule_hold_steps_invalid")
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise TypeError("passive_trace_schedule_records_invalid")
    expected_count = 1 + pre_roll_steps + hold_steps
    if len(records) != expected_count:
        raise ValueError("passive_trace_schedule_record_count_invalid")
    first = records[0]
    if not isinstance(first, Mapping):
        raise ValueError("passive_trace_schedule_record_invalid")
    first_world_step = _nonnegative_int(
        first.get("world_step"),
        name="passive_trace_schedule_world_step",
    )
    first_world_time = first.get("world_time_s")
    if (
        isinstance(first_world_time, bool)
        or not isinstance(first_world_time, (int, float, np.number))
        or not math.isfinite(float(first_world_time))
    ):
        raise ValueError("passive_trace_schedule_world_time_invalid")
    first_world_time = float(first_world_time)

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError("passive_trace_schedule_record_invalid")
        if record.get("local_step") != index:
            raise ValueError("passive_trace_schedule_local_step_invalid")
        if index == 0:
            expected_phase = "baseline"
            expected_phase_step = 0
        elif index <= pre_roll_steps:
            expected_phase = "pre_roll"
            expected_phase_step = index
        else:
            expected_phase = "hold"
            expected_phase_step = index - pre_roll_steps
        if (
            record.get("phase") != expected_phase
            or record.get("phase_step") != expected_phase_step
        ):
            raise ValueError("passive_trace_schedule_phase_invalid")
        if record.get("world_step") != first_world_step + index:
            raise ValueError("passive_trace_schedule_world_step_invalid")
        world_time = record.get("world_time_s")
        if (
            isinstance(world_time, bool)
            or not isinstance(world_time, (int, float, np.number))
            or not math.isfinite(float(world_time))
        ):
            raise ValueError("passive_trace_schedule_world_time_invalid")
        if index > 0 and not math.isclose(
            float(world_time) - float(records[index - 1]["world_time_s"]),
            dt,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            raise ValueError("passive_trace_schedule_world_time_invalid")
    return {
        "record_count": expected_count,
        "baseline_local_step": 0,
        "hold_reference_local_step": pre_roll_steps,
        "terminal_local_step": expected_count - 1,
        "first_world_step": first_world_step,
        "last_world_step": first_world_step + expected_count - 1,
        "first_world_time_s": first_world_time,
        "last_world_time_s": float(records[-1]["world_time_s"]),
        "physics_dt": dt,
        "valid": True,
    }


def summarize_motion_trace(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence) or not records:
        raise ValueError("passive_trace_motion_records_required")
    maximum_translation = 0.0
    maximum_tilt = 0.0
    first_translation_failure = None
    first_tilt_failure = None
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("passive_trace_motion_record_invalid")
        local_step = record.get("local_step")
        if type(local_step) is not int or local_step < 0:
            raise ValueError("passive_trace_motion_local_step_invalid")
        translation = record.get("translation_m")
        tilt = record.get("tilt_degrees")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float, np.number))
            or not math.isfinite(float(value))
            or float(value) < 0.0
            for value in (translation, tilt)
        ):
            raise ValueError("passive_trace_motion_value_invalid")
        translation_valid = record.get("translation_valid")
        tilt_valid = record.get("tilt_valid")
        if type(translation_valid) is not bool or type(tilt_valid) is not bool:
            raise ValueError("passive_trace_motion_validity_invalid")
        maximum_translation = max(maximum_translation, float(translation))
        maximum_tilt = max(maximum_tilt, float(tilt))
        if not translation_valid and first_translation_failure is None:
            first_translation_failure = local_step
        if not tilt_valid and first_tilt_failure is None:
            first_tilt_failure = local_step
    return {
        "status": "MEASURED",
        "valid": True,
        "passed": bool(
            first_translation_failure is None and first_tilt_failure is None
        ),
        "record_count": len(records),
        "maximum_translation_m": maximum_translation,
        "maximum_tilt_degrees": maximum_tilt,
        "first_translation_failure_local_step": first_translation_failure,
        "first_tilt_failure_local_step": first_tilt_failure,
    }


def summarize_filled_trace(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_particle_count: int,
) -> dict[str, Any]:
    if type(expected_particle_count) is not int or expected_particle_count <= 0:
        raise ValueError("passive_trace_expected_particle_count_invalid")
    motion = summarize_motion_trace(records)
    source_min = expected_particle_count
    non_source_max = {name: 0 for name in NON_SOURCE_PARTITION_NAMES}
    first_containment_failure = None
    first_partition_failures = {name: None for name in NON_SOURCE_PARTITION_NAMES}
    for record in records:
        local_step = record["local_step"]
        particle_count = record.get("particle_count")
        if type(particle_count) is not int or particle_count != expected_particle_count:
            raise ValueError("passive_trace_particle_count_invalid")
        if record.get("partition_complete") is not True:
            raise ValueError("passive_trace_particle_partition_invalid")
        counts: dict[str, int] = {}
        for name in PARTITION_NAMES:
            count = record.get(name)
            if type(count) is not int or count < 0:
                raise ValueError("passive_trace_particle_partition_invalid")
            counts[name] = count
        if sum(counts.values()) != expected_particle_count:
            raise ValueError("passive_trace_particle_partition_invalid")
        if counts["nonfinite"] != 0:
            raise ValueError("passive_trace_particle_nonfinite")
        if not _is_sha256(record.get("position_sha256")):
            raise ValueError("passive_trace_position_hash_invalid")
        source_pose_hash = record.get("source_pose_sha256")
        frame_pose_hash = record.get("source_frame_pose_sha256")
        if not _is_sha256(source_pose_hash) or not _is_sha256(frame_pose_hash):
            raise ValueError("passive_trace_source_frame_hash_invalid")
        if source_pose_hash != frame_pose_hash:
            raise ValueError("passive_trace_source_frame_stale")

        source_min = min(source_min, counts["source"])
        containment_failed = counts["source"] != expected_particle_count
        for name in NON_SOURCE_PARTITION_NAMES:
            non_source_max[name] = max(non_source_max[name], counts[name])
            if counts[name] != 0:
                containment_failed = True
                if first_partition_failures[name] is None:
                    first_partition_failures[name] = local_step
        if containment_failed and first_containment_failure is None:
            first_containment_failure = local_step
    containment_passed = first_containment_failure is None
    passed = bool(motion["passed"] and containment_passed)
    return {
        "status": "MEASURED",
        "valid": True,
        "passed": passed,
        "motion_passed": motion["passed"],
        "containment_passed": containment_passed,
        "record_count": len(records),
        "expected_particle_count": expected_particle_count,
        "pre_pour_source_min": source_min,
        "pre_pour_non_source_max": non_source_max,
        "first_containment_failure_local_step": first_containment_failure,
        "first_partition_failure_local_step": first_partition_failures,
        "first_translation_failure_local_step": motion[
            "first_translation_failure_local_step"
        ],
        "first_tilt_failure_local_step": motion[
            "first_tilt_failure_local_step"
        ],
        "maximum_translation_m": motion["maximum_translation_m"],
        "maximum_tilt_degrees": motion["maximum_tilt_degrees"],
    }


def audit_extended_settle_trace(
    *,
    records: Sequence[Mapping[str, Any]],
    source_world_matrices: Any,
    source_centers_world_m: Any,
    linear_velocities_m_s: Any,
    pre_roll_steps: int,
    hold_steps: int,
    vessel_axis_object: Any,
    translation_limit_m: Any,
    tilt_limit_degrees: Any,
    expected_particle_count: int,
    window_steps: int,
) -> dict[str, Any]:
    from utils.isaac_fluid_evaluation import evaluate_preclose_source_motion

    if type(pre_roll_steps) is not int or pre_roll_steps <= 0:
        raise ValueError("extended_settle_pre_roll_steps_invalid")
    if type(hold_steps) is not int or hold_steps <= 0:
        raise ValueError("extended_settle_hold_steps_invalid")
    if type(window_steps) is not int or window_steps <= 0:
        raise ValueError("extended_settle_window_steps_invalid")
    expected_records = 1 + pre_roll_steps + hold_steps
    if len(records) != expected_records:
        raise ValueError("extended_settle_record_count_invalid")
    matrices = np.asarray(source_world_matrices, dtype=np.float64)
    centers = np.asarray(source_centers_world_m, dtype=np.float64)
    velocities = np.asarray(linear_velocities_m_s, dtype=np.float64)
    if (
        matrices.shape != (expected_records, 4, 4)
        or centers.shape != (expected_records, 3)
        or velocities.shape != (expected_records, 3)
        or not np.isfinite(matrices).all()
        or not np.isfinite(centers).all()
        or not np.isfinite(velocities).all()
    ):
        raise ValueError("extended_settle_trace_arrays_invalid")

    reference_matrix = matrices[pre_roll_steps]
    reference_center = centers[pre_roll_steps]
    first_translation_failure = None
    first_tilt_failure = None
    maximum_translation = 0.0
    maximum_tilt = 0.0
    for local_step in range(pre_roll_steps + 1, expected_records):
        record = records[local_step]
        if (
            record.get("local_step") != local_step
            or record.get("motion_reference_local_step") != pre_roll_steps
        ):
            raise ValueError("extended_settle_hold_reference_invalid")
        motion = evaluate_preclose_source_motion(
            reference_center_world_m=reference_center,
            reference_source_world_matrix=reference_matrix,
            current_center_world_m=centers[local_step],
            current_source_world_matrix=matrices[local_step],
            vessel_axis_object=vessel_axis_object,
            translation_limit_m=translation_limit_m,
            tilt_limit_degrees=tilt_limit_degrees,
        )
        if (
            not math.isclose(
                float(record.get("translation_m")),
                motion["translation_m"],
                rel_tol=0.0,
                abs_tol=1.0e-12,
            )
            or not math.isclose(
                float(record.get("tilt_degrees")),
                motion["tilt_degrees"],
                rel_tol=0.0,
                abs_tol=1.0e-9,
            )
            or record.get("translation_valid") is not motion["translation_valid"]
            or record.get("tilt_valid") is not motion["tilt_valid"]
        ):
            raise ValueError("extended_settle_stored_motion_mismatch")
        maximum_translation = max(maximum_translation, motion["translation_m"])
        maximum_tilt = max(maximum_tilt, motion["tilt_degrees"])
        if not motion["translation_valid"] and first_translation_failure is None:
            first_translation_failure = local_step
        if not motion["tilt_valid"] and first_tilt_failure is None:
            first_tilt_failure = local_step

    pre_roll_translations = np.linalg.norm(
        centers[: pre_roll_steps + 1] - centers[0], axis=1
    )
    containment_summary = summarize_filled_trace(
        records,
        expected_particle_count=expected_particle_count,
    )
    total_steps = pre_roll_steps + hold_steps
    if total_steps % window_steps != 0:
        raise ValueError("extended_settle_window_partition_invalid")
    windows = []
    for start in range(0, total_steps, window_steps):
        end = start + window_steps
        horizontal_speeds = np.linalg.norm(
            velocities[start + 1 : end + 1, :2], axis=1
        )
        windows.append(
            {
                "start_local_step": start,
                "end_local_step": end,
                "endpoint_displacement_m": float(
                    np.linalg.norm(centers[end] - centers[start])
                ),
                "mean_horizontal_speed_m_s": float(
                    np.mean(horizontal_speeds)
                ),
                "terminal_horizontal_speed_m_s": float(
                    np.linalg.norm(velocities[end, :2])
                ),
            }
        )
    hold_passed = bool(
        first_translation_failure is None and first_tilt_failure is None
    )
    containment_passed = bool(containment_summary["containment_passed"])
    return {
        "valid": True,
        "passed": bool(hold_passed and containment_passed),
        "pre_roll": {
            "reference_local_step": 0,
            "terminal_local_step": pre_roll_steps,
            "endpoint_displacement_m": float(
                np.linalg.norm(centers[pre_roll_steps] - centers[0])
            ),
            "maximum_translation_m": float(np.max(pre_roll_translations)),
        },
        "hold_motion": {
            "reference_local_step": pre_roll_steps,
            "first_local_step": pre_roll_steps + 1,
            "terminal_local_step": pre_roll_steps + hold_steps,
            "record_count": hold_steps,
            "maximum_translation_m": maximum_translation,
            "maximum_tilt_degrees": maximum_tilt,
            "first_translation_failure_local_step": first_translation_failure,
            "first_tilt_failure_local_step": first_tilt_failure,
            "passed": hold_passed,
        },
        "containment": {
            "scope": "all_records",
            "record_count": expected_records,
            "first_failure_local_step": containment_summary[
                "first_containment_failure_local_step"
            ],
            "source_min": containment_summary["pre_pour_source_min"],
            "non_source_max": containment_summary["pre_pour_non_source_max"],
            "passed": containment_passed,
        },
        "fixed_windows": windows,
    }


def validate_treatment_contract(
    *,
    treatment: str,
    particle_path: str,
    active_particle_paths: Sequence[str],
    mutation_ledger: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if treatment not in {"dry", "filled"} or not particle_path.startswith("/"):
        raise ValueError("passive_treatment_contract_invalid")
    if isinstance(active_particle_paths, (str, bytes)) or isinstance(
        mutation_ledger, (str, bytes)
    ):
        raise ValueError("passive_treatment_contract_invalid")
    active = [str(path) for path in active_particle_paths]
    ledger = [dict(record) for record in mutation_ledger]
    dry_mutation = {
        "phase": "pre_world",
        "operation": "set_active",
        "path": particle_path,
        "value": False,
    }
    if treatment == "filled":
        valid = active == [particle_path] and ledger == []
        readback = "REQUIRED"
    else:
        valid = active == [] and ledger == [dry_mutation]
        readback = "NOT_APPLICABLE_BY_TREATMENT"
    if not valid:
        raise ValueError("passive_treatment_contract_invalid")
    return {
        "treatment": treatment,
        "particle_path": particle_path,
        "active_particle_paths": active,
        "mutation_ledger": ledger,
        "particle_readback": readback,
        "runtime_particle_mutation_count": 0,
        "valid": True,
    }


def compare_treatment_reports(
    dry_report: Mapping[str, Any],
    filled_report: Mapping[str, Any],
) -> dict[str, Any]:
    if dry_report.get("treatment") != "dry" or filled_report.get("treatment") != "filled":
        raise ValueError("passive_comparison_treatment_order_invalid")
    for report in (dry_report, filled_report):
        if (
            report.get("manifest_type") != MANIFEST_TYPE
            or report.get("lifecycle_status") != "completed"
        ):
            raise ValueError("passive_comparison_report_invalid")
        motion = report.get("motion_stability")
        support = report.get("support_load_authority")
        if (
            not isinstance(motion, Mapping)
            or motion.get("valid") is not True
            or type(motion.get("passed")) is not bool
            or not isinstance(support, Mapping)
            or support.get("status") != "UNSUPPORTED_BY_THIS_PROBE"
            or support.get("mass_claim_allowed") is not False
        ):
            raise ValueError("passive_comparison_authority_invalid")
    dry_contract = dry_report.get("comparison_contract")
    filled_contract = filled_report.get("comparison_contract")
    if (
        not isinstance(dry_contract, Mapping)
        or not isinstance(filled_contract, Mapping)
        or dict(dry_contract) != dict(filled_contract)
    ):
        raise ValueError("passive_comparison_contract_mismatch")

    dry_passed = bool(dry_report["motion_stability"]["passed"])
    filled_passed = bool(filled_report["motion_stability"]["passed"])
    classification = {
        (False, False): "COMMON_BARE_SCENE_INSTABILITY_CANDIDATE",
        (True, False): "PARTICLE_ASSOCIATED_DIFFERENTIAL_CANDIDATE",
        (False, True): "INCONCLUSIVE_DRY_ONLY_INSTABILITY",
        (True, True): "BARE_PASSIVE_FAILURE_NOT_REPRODUCED",
    }[(dry_passed, filled_passed)]
    return {
        "schema_version": 1,
        "manifest_type": COMPARISON_MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparable": True,
        "classification": classification,
        "dry_motion_passed": dry_passed,
        "filled_motion_passed": filled_passed,
        "filled_containment_passed": bool(
            filled_report.get("containment", {}).get("passed", False)
        ),
        "comparison_contract": dict(dry_contract),
        "comparison_contract_sha256": _canonical_json_sha256(dry_contract),
        "causal_claim_allowed": False,
        "filled_payload_mass_claim_allowed": False,
        "next_grasp_authorized": False,
    }


def finalize_child_report(
    provisional_report: Mapping[str, Any],
    *,
    expected_treatment: str,
    expected_run_nonce: str,
    child_command: Sequence[str],
    child_returncode: int,
    timed_out: bool,
    termination: str | None,
) -> dict[str, Any]:
    if (
        provisional_report.get("manifest_type") != MANIFEST_TYPE
        or provisional_report.get("treatment") != expected_treatment
        or provisional_report.get("run_nonce") != expected_run_nonce
    ):
        raise ValueError("passive_probe_provisional_identity_invalid")
    if type(child_returncode) is not int or type(timed_out) is not bool:
        raise ValueError("passive_probe_child_status_invalid")
    final = json.loads(_canonical_json_bytes(provisional_report).decode("utf-8"))
    measurement_decision = str(
        final.get("measurement_decision", "PROBE_RUNTIME_ERROR")
    )
    lifecycle = final.get("lifecycle_status")
    clean = bool(
        not timed_out
        and child_returncode == 0
        and lifecycle == "measurement_complete_pending_application_close"
        and measurement_decision
        in {"PASSIVE_STABILITY_PASS", "PASSIVE_STABILITY_FAIL"}
    )
    final["pre_shutdown_decision"] = measurement_decision
    final["finalized_at_utc"] = datetime.now(timezone.utc).isoformat()
    final["child_process"] = {
        "command": [str(value) for value in child_command],
        "returncode": child_returncode,
        "timed_out": timed_out,
        "termination": termination,
    }
    if clean:
        final["decision"] = measurement_decision
        final["lifecycle_status"] = "completed"
        final["shutdown_status"] = "child_exit_0"
    else:
        final["decision"] = "PROBE_RUNTIME_ERROR"
        final["lifecycle_status"] = "failed"
        final["shutdown_status"] = (
            "child_timeout"
            if timed_out
            else "child_exit_nonzero"
            if child_returncode != 0
            else "measurement_runtime_error"
        )
    return final


def _artifact_record(path: Path, *, relative_to: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(relative_to)),
        "byte_count": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _validate_artifacts(report: Mapping[str, Any], *, output_dir: Path) -> None:
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("passive_probe_artifacts_missing")
    expected_names = {"source_trace"}
    if report.get("treatment") == "filled":
        expected_names.add("particle_trace")
    if set(artifacts) != expected_names:
        raise ValueError("passive_probe_artifact_set_invalid")
    for record in artifacts.values():
        if not isinstance(record, Mapping):
            raise ValueError("passive_probe_artifact_record_invalid")
        relative_path = Path(str(record.get("path", "")))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("passive_probe_artifact_path_invalid")
        path = output_dir / relative_path
        if (
            not path.is_file()
            or type(record.get("byte_count")) is not int
            or path.stat().st_size != record["byte_count"]
            or not _is_sha256(record.get("sha256"))
            or _sha256_file(path) != record["sha256"]
        ):
            raise ValueError("passive_probe_artifact_hash_mismatch")


def _load_json_mapping(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"passive_probe_json_nonfinite:{value}")

    with path.open("r", encoding="utf-8") as stream:
        result = json.load(stream, parse_constant=reject_constant)
    if not isinstance(result, dict):
        raise TypeError("passive_probe_json_mapping_required")
    return result


def _absolute_dependency_path(value: Any, *, entry_path: Path) -> Path | None:
    raw = str(
        getattr(value, "realPath", "")
        or getattr(value, "resolvedPath", "")
        or getattr(value, "path", "")
        or getattr(value, "identifier", "")
        or value
    )
    if not raw or raw.startswith("anon:") or "://" in raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = entry_path.parent / path
    return path.resolve()


def build_usd_dependency_closure(entry_path: Path) -> dict[str, Any]:
    from pxr import UsdUtils

    entry = entry_path.resolve()
    layers, assets, unresolved = UsdUtils.ComputeAllDependencies(str(entry))
    paths = {entry}
    unresolved_values = [str(value) for value in unresolved]
    for value in (*layers, *assets):
        path = _absolute_dependency_path(value, entry_path=entry)
        if path is None:
            unresolved_values.append(str(value))
        elif path.is_file():
            paths.add(path)
        else:
            unresolved_values.append(str(path))
    files = [
        {
            "path": str(path),
            "byte_count": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(paths, key=str)
    ]
    payload = {
        "entry_path": str(entry),
        "files": files,
        "unresolved": sorted(set(unresolved_values)),
    }
    return {**payload, "sha256": _canonical_json_sha256(payload)}


def _active_particle_paths(stage: Any) -> list[str]:
    from pxr import Usd

    result = []
    for prim in Usd.PrimRange.Stage(stage):
        relationship = prim.GetRelationship("physxParticle:particleSystem")
        if relationship and relationship.IsValid() and prim.IsActive():
            result.append(str(prim.GetPath()))
    return sorted(result)


def _source_geometry_center(stage: Any, source_path: str) -> np.ndarray:
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(source_path)
    if not prim or not prim.IsValid():
        raise RuntimeError(f"passive_probe_source_missing:{source_path}")
    cache = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(),
        includedPurposes=[UsdGeom.Tokens.default_],
        useExtentsHint=True,
    )
    bound = cache.ComputeWorldBound(prim)
    extent = bound.GetRange()
    center = (
        np.asarray(extent.GetMin(), dtype=np.float64)
        + np.asarray(extent.GetMax(), dtype=np.float64)
    ) / 2.0
    world_center = np.append(center, 1.0) @ np.asarray(
        bound.GetMatrix(), dtype=np.float64
    )
    if not np.isfinite(world_center).all():
        raise RuntimeError("passive_probe_source_geometry_center_invalid")
    return world_center[:3]


def _world_counter(world: Any, name: str, *, integer: bool) -> int | float:
    value = getattr(world, name, None)
    value = value() if callable(value) else value
    if integer:
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
            raise RuntimeError(f"passive_probe_world_{name}_invalid")
        return int(value)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float, np.number))
        or not math.isfinite(float(value))
    ):
        raise RuntimeError(f"passive_probe_world_{name}_invalid")
    return float(value)


def _rigid_velocity(source_body: Any, method_name: str) -> np.ndarray:
    getter = getattr(source_body, method_name, None)
    if not callable(getter):
        raise RuntimeError(f"passive_probe_{method_name}_unavailable")
    value = np.asarray(getter(), dtype=np.float64)
    if value.shape != (3,) or not np.isfinite(value).all():
        raise RuntimeError(f"passive_probe_{method_name}_invalid")
    return value


def _runtime_error_report(
    exc: BaseException,
    *,
    treatment: str,
    run_nonce: str,
    phase: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "runtime_error_pending_application_close",
        "shutdown_status": "pending",
        "treatment": treatment,
        "run_nonce": run_nonce,
        "measurement_decision": "PROBE_RUNTIME_ERROR",
        "fatal_error": {
            "phase": phase,
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
    }


def _runtime_identity() -> dict[str, Any]:
    import omni.kit.app

    application = omni.kit.app.get_app()
    build_version = "NOT_AVAILABLE"
    for method_name in ("get_build_version", "get_version"):
        method = getattr(application, method_name, None)
        if callable(method) and (value := method()):
            build_version = str(value)
            break
    payload = {
        "kit_build_version": build_version,
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version.split()[0],
    }
    return {**payload, "runtime_id": _canonical_json_sha256(payload)}


def _gravity_vector(stage: Any, scene_path: str) -> list[float]:
    from pxr import UsdPhysics

    scene = UsdPhysics.Scene(stage.GetPrimAtPath(scene_path))
    direction = np.asarray(scene.GetGravityDirectionAttr().Get(), dtype=np.float64)
    magnitude = float(scene.GetGravityMagnitudeAttr().Get())
    if direction.shape != (3,) or not np.isfinite(direction).all() or not math.isfinite(
        magnitude
    ):
        raise RuntimeError("passive_probe_gravity_invalid")
    return (direction * magnitude).tolist()


def _write_trace_artifacts(
    *,
    output_dir: Path,
    records: Sequence[Mapping[str, Any]],
    source_matrices: Sequence[np.ndarray],
    source_centers: Sequence[np.ndarray],
    source_axes: Sequence[np.ndarray],
    linear_velocities: Sequence[np.ndarray],
    angular_velocities: Sequence[np.ndarray],
    particle_positions: Sequence[np.ndarray],
) -> dict[str, Any]:
    source_path = output_dir / SOURCE_TRACE_BASENAME
    atomic_create_npz(
        source_path,
        {
            "local_step": np.asarray(
                [record["local_step"] for record in records], dtype=np.int64
            ),
            "phase": np.asarray([record["phase"] for record in records]),
            "phase_step": np.asarray(
                [record["phase_step"] for record in records], dtype=np.int64
            ),
            "motion_reference_local_step": np.asarray(
                [record["motion_reference_local_step"] for record in records],
                dtype=np.int64,
            ),
            "world_step": np.asarray(
                [record["world_step"] for record in records], dtype=np.int64
            ),
            "world_time_s": np.asarray(
                [record["world_time_s"] for record in records], dtype=np.float64
            ),
            "source_world_matrix_m": np.asarray(source_matrices, dtype=np.float64),
            "source_geometry_center_world_m": np.asarray(
                source_centers, dtype=np.float64
            ),
            "source_axis_world": np.asarray(source_axes, dtype=np.float64),
            "linear_velocity_m_s": np.asarray(linear_velocities, dtype=np.float64),
            "angular_velocity_rad_s": np.asarray(
                angular_velocities, dtype=np.float64
            ),
            "translation_m": np.asarray(
                [record["translation_m"] for record in records], dtype=np.float64
            ),
            "tilt_degrees": np.asarray(
                [record["tilt_degrees"] for record in records], dtype=np.float64
            ),
            "translation_valid": np.asarray(
                [record["translation_valid"] for record in records], dtype=np.bool_
            ),
            "tilt_valid": np.asarray(
                [record["tilt_valid"] for record in records], dtype=np.bool_
            ),
            "source_pose_sha256": np.asarray(
                [record["source_pose_sha256"] for record in records]
            ),
        },
    )
    artifacts = {
        "source_trace": _artifact_record(source_path, relative_to=output_dir)
    }
    if particle_positions:
        particle_path = output_dir / PARTICLE_TRACE_BASENAME
        arrays: dict[str, Any] = {
            "positions_world_m": np.asarray(particle_positions, dtype=np.float64),
            "position_sha256": np.asarray(
                [record["position_sha256"] for record in records]
            ),
            "particle_count": np.asarray(
                [record["particle_count"] for record in records], dtype=np.int64
            ),
            "partition_complete": np.asarray(
                [record["partition_complete"] for record in records], dtype=np.bool_
            ),
            "source_frame_pose_sha256": np.asarray(
                [record["source_frame_pose_sha256"] for record in records]
            ),
        }
        for name in PARTITION_NAMES:
            arrays[name] = np.asarray(
                [record[name] for record in records], dtype=np.int64
            )
        atomic_create_npz(particle_path, arrays)
        artifacts["particle_trace"] = _artifact_record(
            particle_path, relative_to=output_dir
        )
    return artifacts


def _measure_runtime(args: argparse.Namespace) -> dict[str, Any]:
    import yaml

    from isaacsim_compat import install_legacy_isaacsim_aliases

    install_legacy_isaacsim_aliases()
    import omni.physx
    import omni.usd
    from isaacsim.core.api import World
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.utils.stage import add_reference_to_stage, get_stage_units

    from utils.isaac_fluid_evaluation import (
        AuthoredWrapperFrameReader,
        _single_rigid_world_matrix,
        _table_top_z,
        classify_transfer_positions,
        configure_fluid_world_timing,
        configure_particle_usd_readback,
        construct_single_rigid_prim,
        evaluate_preclose_source_motion,
        validate_dynamic_source_stage_contract,
    )
    from utils.online_fluid_surface import (
        canonical_position_sha256,
        read_strict_simulation_points,
    )

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if not isinstance(config, Mapping) or not isinstance(
        config.get("online_fluid"), Mapping
    ):
        raise ValueError("passive_probe_config_invalid")
    fluid = config["online_fluid"]
    usd_path = (REPO_ROOT / str(config["usd_path"])).resolve()
    if not usd_path.is_file():
        raise FileNotFoundError(f"passive_probe_usd_missing:{usd_path}")
    dependency_closure = build_usd_dependency_closure(usd_path)
    readback_settings = configure_particle_usd_readback()
    bootstrap_ledger = [
        "simulation_app_started",
        "legacy_isaacsim_aliases_installed",
        "particle_usd_readback_configured_pre_world",
        "production_usd_referenced",
        "treatment_authored_pre_world",
        "dynamic_source_stage_contract_validated",
        "world_constructed",
        "world_reset_complete",
        "source_readback_initialized",
        "authority_origin_captured",
    ]

    stage = omni.usd.get_context().get_stage()
    add_reference_to_stage(usd_path=str(usd_path), prim_path="/World")
    particle_path = str(fluid["particle_path"])
    mutation_ledger: list[dict[str, Any]] = []
    if args.treatment == "dry":
        previous_target = stage.GetEditTarget()
        stage.SetEditTarget(stage.GetSessionLayer())
        try:
            particle_prim = stage.GetPrimAtPath(particle_path)
            if not particle_prim or not particle_prim.IsValid():
                raise RuntimeError(f"passive_probe_particle_missing:{particle_path}")
            particle_prim.SetActive(False)
        finally:
            stage.SetEditTarget(previous_target)
        mutation_ledger.append(
            {
                "phase": "pre_world",
                "operation": "set_active",
                "path": particle_path,
                "value": False,
            }
        )
    treatment_contract = validate_treatment_contract(
        treatment=args.treatment,
        particle_path=particle_path,
        active_particle_paths=_active_particle_paths(stage),
        mutation_ledger=mutation_ledger,
    )
    stage_contract = validate_dynamic_source_stage_contract(
        stage,
        fluid,
        additional_required_paths=("/World/Cube", "/World/table"),
    )
    source_path = str(fluid["source_actor_path"])
    source_visual_path = str(fluid["source_visual_mesh_path"])
    source_center_authored = _source_geometry_center(stage, source_path)

    world = World(
        physics_dt=float(fluid["physics_dt"]),
        rendering_dt=float(fluid["rendering_dt"]),
        stage_units_in_meters=1.0,
        physics_prim_path=str(fluid["physics_scene_path"]),
        set_defaults=False,
        backend="numpy",
        device="cpu",
    )
    omni.physx.get_physx_interface().overwrite_gpu_setting(1)
    configure_fluid_world_timing(
        world,
        physics_dt=float(fluid["physics_dt"]),
        rendering_dt=float(fluid["rendering_dt"]),
    )
    world.reset()
    source_body = construct_single_rigid_prim(
        SingleRigidPrim,
        prim_path=source_path,
        name="passive_stability_source_vessel",
    )
    source_body.initialize()
    source_initial_world = _single_rigid_world_matrix(source_body)
    center_local = np.append(source_center_authored, 1.0) @ np.linalg.inv(
        source_initial_world
    )
    cached_source_world = source_initial_world.copy()
    source_frame = AuthoredWrapperFrameReader(
        stage,
        parent_path=source_path,
        visual_mesh_path=source_visual_path,
        parent_world_matrix=lambda: cached_source_world.copy(),
    )
    target_frame = AuthoredWrapperFrameReader(
        stage,
        parent_path=str(fluid["target_actor_path"]),
        visual_mesh_path=str(fluid["target_visual_mesh_path"]),
    )
    table_z = _table_top_z(stage, str(fluid["table_path"]))
    expected_particle_count = int(fluid["expected_particle_count"])
    physics_dt = float(fluid["physics_dt"])
    pre_roll_steps = int(fluid["dynamic_pre_roll_steps"])
    hold_steps = int(fluid["filled_static_hold_steps"])
    vessel_axis_object = tuple(float(value) for value in fluid["grasp_height_axis_object"])
    translation_limit = float(fluid["grasp_preclose_source_translation_limit_m"])
    tilt_limit = float(fluid["grasp_preclose_source_tilt_limit_degrees"])

    records: list[dict[str, Any]] = []
    source_matrices: list[np.ndarray] = []
    source_centers: list[np.ndarray] = []
    source_axes: list[np.ndarray] = []
    linear_velocities: list[np.ndarray] = []
    angular_velocities: list[np.ndarray] = []
    particle_positions: list[np.ndarray] = []
    baseline_world: np.ndarray | None = None
    baseline_center: np.ndarray | None = None
    hold_world: np.ndarray | None = None
    hold_center: np.ndarray | None = None

    def capture(local_step: int, phase: str, phase_step: int) -> None:
        nonlocal cached_source_world, baseline_world, baseline_center
        nonlocal hold_world, hold_center
        current_world = _single_rigid_world_matrix(source_body)
        cached_source_world = current_world.copy()
        linear_velocity = _rigid_velocity(source_body, "get_linear_velocity")
        angular_velocity = _rigid_velocity(source_body, "get_angular_velocity")
        current_center = np.ascontiguousarray(
            (center_local @ current_world)[:3], dtype=np.float64
        )
        if local_step == 0:
            baseline_world = current_world.copy()
            baseline_center = current_center.copy()
        if baseline_world is None or baseline_center is None:
            raise RuntimeError("passive_probe_baseline_missing")
        if local_step <= pre_roll_steps:
            reference_world = baseline_world
            reference_center = baseline_center
            reference_local_step = 0
        else:
            if hold_world is None or hold_center is None:
                raise RuntimeError("passive_probe_hold_reference_missing")
            reference_world = hold_world
            reference_center = hold_center
            reference_local_step = pre_roll_steps
        motion = evaluate_preclose_source_motion(
            reference_center_world_m=reference_center,
            reference_source_world_matrix=reference_world,
            current_center_world_m=current_center,
            current_source_world_matrix=current_world,
            vessel_axis_object=vessel_axis_object,
            translation_limit_m=translation_limit,
            tilt_limit_degrees=tilt_limit,
        )
        current_source_frame = source_frame()
        pose_hash = hashlib.sha256(
            np.ascontiguousarray(current_world, dtype="<f8").tobytes(order="C")
        ).hexdigest()
        record: dict[str, Any] = {
            "local_step": local_step,
            "phase": phase,
            "phase_step": phase_step,
            "motion_reference_local_step": reference_local_step,
            "world_step": _world_counter(
                world, "current_time_step_index", integer=True
            ),
            "world_time_s": _world_counter(world, "current_time", integer=False),
            "translation_m": motion["translation_m"],
            "tilt_degrees": motion["tilt_degrees"],
            "translation_valid": motion["translation_valid"],
            "tilt_valid": motion["tilt_valid"],
            "source_pose_sha256": pose_hash,
            "source_frame_pose_sha256": pose_hash,
            "source_frame_origin_world_m": [
                float(value) for value in current_source_frame.origin_world
            ],
            "source_frame_axis_world": [
                float(value) for value in current_source_frame.z_axis_world
            ],
        }
        if args.treatment == "filled":
            positions = read_strict_simulation_points(
                stage,
                particle_path,
                expected_particle_count=expected_particle_count,
            )
            classification = classify_transfer_positions(
                positions,
                source_frame=current_source_frame,
                target_frame=target_frame(),
                table_z=table_z,
                minimum_target_particles=int(fluid["minimum_target_particles"]),
                minimum_task_target_fraction=float(
                    fluid["minimum_task_target_fraction"]
                ),
                minimum_expert_target_fraction=float(
                    fluid["minimum_expert_target_fraction"]
                ),
            )
            record.update(
                {
                    name: int(classification[name]) for name in PARTITION_NAMES
                }
            )
            record.update(
                {
                    "particle_count": int(classification["particle_count"]),
                    "partition_complete": bool(
                        classification["partition_complete"]
                    ),
                    "position_sha256": canonical_position_sha256(positions),
                }
            )
            particle_positions.append(np.asarray(positions, dtype=np.float64).copy())
        records.append(record)
        source_matrices.append(current_world.copy())
        source_centers.append(current_center.copy())
        source_axes.append(
            np.asarray(motion["current_axis_world"], dtype=np.float64)
        )
        linear_velocities.append(linear_velocity)
        angular_velocities.append(angular_velocity)
        if local_step == pre_roll_steps:
            hold_world = current_world.copy()
            hold_center = current_center.copy()

    capture(0, "baseline", 0)
    for local_step in range(1, pre_roll_steps + hold_steps + 1):
        before_step = _world_counter(world, "current_time_step_index", integer=True)
        before_time = _world_counter(world, "current_time", integer=False)
        world.step(render=False)
        after_step = _world_counter(world, "current_time_step_index", integer=True)
        after_time = _world_counter(world, "current_time", integer=False)
        if after_step != before_step + 1:
            raise RuntimeError("passive_probe_world_step_advance_invalid")
        if not math.isclose(
            after_time,
            before_time + physics_dt,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            raise RuntimeError("passive_probe_world_time_advance_invalid")
        if local_step <= pre_roll_steps:
            capture(local_step, "pre_roll", local_step)
        else:
            capture(local_step, "hold", local_step - pre_roll_steps)

    schedule = validate_trace_schedule(
        records,
        physics_dt=physics_dt,
        pre_roll_steps=pre_roll_steps,
        hold_steps=hold_steps,
    )
    motion_stability = summarize_motion_trace(records)
    if args.treatment == "filled":
        filled_summary = summarize_filled_trace(
            records,
            expected_particle_count=expected_particle_count,
        )
        containment = {
            key: value
            for key, value in filled_summary.items()
            if key
            not in {
                "motion_passed",
                "maximum_translation_m",
                "maximum_tilt_degrees",
                "first_translation_failure_local_step",
                "first_tilt_failure_local_step",
            }
        }
        containment["passed"] = filled_summary["containment_passed"]
    else:
        containment = {
            "status": "NOT_APPLICABLE_BY_TREATMENT",
            "valid": True,
        }
    measurement_passed = bool(
        motion_stability["passed"]
        and (
            args.treatment == "dry"
            or containment.get("passed") is True
        )
    )
    artifacts = _write_trace_artifacts(
        output_dir=args.out_dir,
        records=records,
        source_matrices=source_matrices,
        source_centers=source_centers,
        source_axes=source_axes,
        linear_velocities=linear_velocities,
        angular_velocities=angular_velocities,
        particle_positions=particle_positions,
    )
    runtime = _runtime_identity()
    gravity = _gravity_vector(stage, str(fluid["physics_scene_path"]))
    comparison_contract = {
        "config_sha256": _sha256_file(args.config),
        "usd_dependency_closure_sha256": dependency_closure["sha256"],
        "runner_sha256": _sha256_file(Path(__file__).resolve()),
        "runtime_id": runtime["runtime_id"],
        "physics_dt": physics_dt,
        "gravity_world_m_s2": gravity,
        "stage_units_in_meters": float(get_stage_units()),
        "source_actor_path": source_path,
        "particle_path": particle_path,
        "pre_roll_steps": pre_roll_steps,
        "hold_steps": hold_steps,
        "classifier_epsilon_m": 5.0e-5,
        "common_bootstrap_contract": bootstrap_ledger,
    }
    return {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "treatment": args.treatment,
        "run_nonce": args.run_nonce,
        "measurement_decision": (
            "PASSIVE_STABILITY_PASS"
            if measurement_passed
            else "PASSIVE_STABILITY_FAIL"
        ),
        "config_path": str(args.config),
        "usd_path": str(usd_path),
        "usd_dependency_closure": dependency_closure,
        "runtime": runtime,
        "particle_usd_readback_settings": readback_settings,
        "bootstrap_ledger": bootstrap_ledger,
        "stage_contract": stage_contract,
        "treatment_contract": treatment_contract,
        "trace_schedule": schedule,
        "motion_stability": motion_stability,
        "containment": containment,
        "support_load_authority": {
            "status": "UNSUPPORTED_BY_THIS_PROBE",
            "mass_claim_allowed": False,
            "particle_support_contact_claim_allowed": False,
        },
        "no_action_contract": {
            "robot_constructed": False,
            "task_constructed": False,
            "controller_constructed": False,
            "camera_or_render_product_constructed": False,
            "render_call_count": 0,
            "source_pose_write_count": 0,
            "kinematic_target_update_count": 0,
            "mechanical_attachment_count": 0,
            "runtime_particle_mutation_count": 0,
            "grasp_authorized": False,
        },
        "comparison_contract": comparison_contract,
        "artifacts": artifacts,
    }


def _run_runtime_child(args: argparse.Namespace) -> int:
    provisional_path = args.out_dir / PROVISIONAL_REPORT_BASENAME
    app = None
    try:
        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "width": 64, "height": 64})
        try:
            report = _measure_runtime(args)
        except Exception as exc:
            report = _runtime_error_report(
                exc,
                treatment=args.treatment,
                run_nonce=args.run_nonce,
                phase="runtime_measurement",
            )
        atomic_create_json(provisional_path, report)
    except Exception as exc:
        if not provisional_path.exists():
            atomic_create_json(
                provisional_path,
                _runtime_error_report(
                    exc,
                    treatment=args.treatment,
                    run_nonce=args.run_nonce,
                    phase="application_bootstrap",
                ),
            )
        return 1
    finally:
        if app is not None:
            app.close()
    return 0


def _terminate_and_reap(process: subprocess.Popen[Any]) -> str:
    termination = "SIGTERM"
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30.0)
    except subprocess.TimeoutExpired:
        termination = "SIGKILL"
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    return termination


def _child_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "run",
        "--runtime-child",
        "--treatment",
        args.treatment,
        "--config",
        str(args.config),
        "--out-dir",
        str(args.out_dir),
        "--run-nonce",
        args.run_nonce,
    ]


def _run_parent(args: argparse.Namespace) -> int:
    try:
        args.out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(
            f"passive stability probe refused existing output: {args.out_dir}",
            file=sys.stderr,
            flush=True,
        )
        return 2
    command = _child_command(args)
    timed_out = False
    termination = None
    stdout_path = args.out_dir / "child.stdout.log"
    stderr_path = args.out_dir / "child.stderr.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            try:
                child_returncode = process.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                termination = _terminate_and_reap(process)
                child_returncode = int(process.returncode)
        except OSError as exc:
            child_returncode = 127
            launch_error = exc

    provisional_path = args.out_dir / PROVISIONAL_REPORT_BASENAME
    try:
        provisional = _load_json_mapping(provisional_path)
        if provisional.get("measurement_decision") != "PROBE_RUNTIME_ERROR":
            _validate_artifacts(provisional, output_dir=args.out_dir)
    except Exception as exc:
        provisional = _runtime_error_report(
            exc,
            treatment=args.treatment,
            run_nonce=args.run_nonce,
            phase="parent_artifact_validation",
        )
        if "launch_error" in locals():
            provisional["fatal_error"]["launch_error"] = str(launch_error)
    report = finalize_child_report(
        provisional,
        expected_treatment=args.treatment,
        expected_run_nonce=args.run_nonce,
        child_command=command,
        child_returncode=int(child_returncode),
        timed_out=timed_out,
        termination=termination,
    )
    final_path = args.out_dir / FINAL_REPORT_BASENAME
    atomic_create_json(final_path, report)
    print(
        f"passive stability probe treatment={args.treatment} "
        f"decision={report['decision']} out={final_path}",
        flush=True,
    )
    return 0 if report["lifecycle_status"] == "completed" else 2


def _run_comparison(args: argparse.Namespace) -> int:
    report = compare_treatment_reports(
        _load_json_mapping(args.dry_report),
        _load_json_mapping(args.filled_report),
    )
    atomic_create_json(args.out, report)
    print(
        f"passive stability comparison classification={report['classification']} "
        f"out={args.out}",
        flush=True,
    )
    return 0


def _run_settle_audit(args: argparse.Namespace) -> int:
    import yaml

    report = _load_json_mapping(args.report)
    if (
        report.get("manifest_type") != MANIFEST_TYPE
        or report.get("lifecycle_status") != "completed"
        or report.get("treatment") != "filled"
    ):
        raise ValueError("extended_settle_report_invalid")
    run_directory = args.report.parent
    _validate_artifacts(report, output_dir=run_directory)
    artifacts = report["artifacts"]
    source_path = run_directory / artifacts["source_trace"]["path"]
    particle_path = run_directory / artifacts["particle_trace"]["path"]
    with np.load(source_path, allow_pickle=False) as source, np.load(
        particle_path, allow_pickle=False
    ) as particles:
        record_count = len(source["local_step"])
        records = []
        for index in range(record_count):
            record = {
                "local_step": int(source["local_step"][index]),
                "motion_reference_local_step": int(
                    source["motion_reference_local_step"][index]
                ),
                "translation_m": float(source["translation_m"][index]),
                "tilt_degrees": float(source["tilt_degrees"][index]),
                "translation_valid": bool(source["translation_valid"][index]),
                "tilt_valid": bool(source["tilt_valid"][index]),
                "source_pose_sha256": str(source["source_pose_sha256"][index]),
                "source_frame_pose_sha256": str(
                    particles["source_frame_pose_sha256"][index]
                ),
                "particle_count": int(particles["particle_count"][index]),
                "partition_complete": bool(
                    particles["partition_complete"][index]
                ),
                "position_sha256": str(particles["position_sha256"][index]),
            }
            record.update(
                {
                    name: int(particles[name][index])
                    for name in PARTITION_NAMES
                }
            )
            records.append(record)
        config_path = Path(str(report["config_path"]))
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        fluid = config["online_fluid"]
        audit = audit_extended_settle_trace(
            records=records,
            source_world_matrices=source["source_world_matrix_m"],
            source_centers_world_m=source["source_geometry_center_world_m"],
            linear_velocities_m_s=source["linear_velocity_m_s"],
            pre_roll_steps=int(fluid["dynamic_pre_roll_steps"]),
            hold_steps=int(fluid["filled_static_hold_steps"]),
            vessel_axis_object=fluid["grasp_height_axis_object"],
            translation_limit_m=float(
                fluid["grasp_preclose_source_translation_limit_m"]
            ),
            tilt_limit_degrees=float(
                fluid["grasp_preclose_source_tilt_limit_degrees"]
            ),
            expected_particle_count=int(fluid["expected_particle_count"]),
            window_steps=args.window_steps,
        )
    result = {
        "schema_version": 1,
        "manifest_type": SETTLE_AUDIT_MANIFEST_TYPE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_report": {
            "path": str(args.report),
            "sha256": _sha256_file(args.report),
            "runner_decision": report.get("decision"),
        },
        "source_artifacts": artifacts,
        "audit": audit,
        "classification": (
            "HOLD_ONLY_PASS" if audit["passed"] else "HOLD_ONLY_FAIL"
        ),
        "settling_claim_allowed": False,
        "repeatability_claim_allowed": False,
        "next_grasp_authorized": False,
    }
    atomic_create_json(args.out, result)
    print(
        f"extended settle audit classification={result['classification']} "
        f"out={args.out}",
        flush=True,
    )
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run one isolated treatment")
    run.add_argument("--treatment", choices=("dry", "filled"), required=True)
    run.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    run.add_argument("--out-dir", type=Path, required=True)
    run.add_argument("--timeout-seconds", type=float, default=900.0)
    run.add_argument("--runtime-child", action="store_true", help=argparse.SUPPRESS)
    run.add_argument("--run-nonce", default="", help=argparse.SUPPRESS)
    compare = commands.add_parser("compare", help="compare completed dry and filled reports")
    compare.add_argument("--dry-report", type=Path, required=True)
    compare.add_argument("--filled-report", type=Path, required=True)
    compare.add_argument("--out", type=Path, required=True)
    audit = commands.add_parser(
        "audit-settle", help="audit a fixed post-pre-roll hold"
    )
    audit.add_argument("--report", type=Path, required=True)
    audit.add_argument("--out", type=Path, required=True)
    audit.add_argument("--window-steps", type=int, default=120)
    args = parser.parse_args(argv)
    if args.command == "run":
        args.config = args.config.resolve()
        args.out_dir = args.out_dir.resolve()
        if not args.config.is_file():
            parser.error(f"config not found: {args.config}")
        if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
            parser.error("timeout must be finite and positive")
        if args.runtime_child:
            if not args.run_nonce or not args.out_dir.is_dir():
                parser.error("runtime child requires reserved output and nonce")
        else:
            if args.run_nonce:
                parser.error("run nonce is parent-managed")
            args.run_nonce = secrets.token_hex(16)
    elif args.command == "compare":
        args.dry_report = args.dry_report.resolve()
        args.filled_report = args.filled_report.resolve()
        args.out = args.out.resolve()
    else:
        args.report = args.report.resolve()
        args.out = args.out.resolve()
        if not args.report.is_file():
            parser.error(f"report not found: {args.report}")
        if args.window_steps <= 0:
            parser.error("window steps must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "compare":
        return _run_comparison(args)
    if args.command == "audit-settle":
        return _run_settle_audit(args)
    return _run_runtime_child(args) if args.runtime_child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
