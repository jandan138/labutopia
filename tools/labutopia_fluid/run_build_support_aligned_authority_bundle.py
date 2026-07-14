#!/usr/bin/env python3
"""Build a fail-closed authority bundle for the support-aligned P4096_S2 run."""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import stat
import sys
import uuid
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.run_build_level1_pour_support_aligned_scene import (
    canonical_json_sha256_v1,
)


BUNDLE_BASENAME = "accepted_authority_bundle.json"
FULL_LOG_BASENAME = "source_kit_log.log"
LOG_SEGMENT_BASENAME = "run_scoped_kit_log_segment.log"
PARTICLE_GRAPH_BASENAME = "runtime_particle_graph_enumeration.json"
PUBLISH_COMPLETE_BASENAME = "PUBLISH_COMPLETE.json"
RUNTIME_EVIDENCE_SNAPSHOT_DIR = "runtime_evidence_snapshot"
FROZEN_BASELINE_DIR = "frozen_runner_baseline"
FROZEN_RUNNER_BASENAME = "run_colleague_native_usd_completed_pbd_step_video.py"
FROZEN_MATRIX_MANIFEST_BASENAME = "accepted_matrix_manifest.json"
FROZEN_RUNTIME_SUMMARY_BASENAME = "accepted_P4096_S2_runtime_summary.json"
SELF_REFERENCE_TOKEN = b"accepted_authority_bundle_sha256"
PASS_CLASSIFICATION = "PASS_VISIBLE_BEAKER_STATIC_HOLD"
LEGACY_PASS_CLASSIFICATION = "PASS_SOURCE_HOLD"
EXPECTED_PARTICLE_COUNT = 4096
EXPECTED_SEED = 2
EXPECTED_STEPS = 600
EXPECTED_TRACE_INTERVAL = 30
EXPECTED_LOGICAL_DT = 1.0 / 60.0
EXPECTED_INTEGRATION_DT = 1.0 / 600.0
EXPECTED_SUBSTEPS = 10
EXPECTED_RUNTIME_PARTICLE_SYSTEM_PATH = "/World/CompletedPBD/ParticleSystem"
EXPECTED_RUNTIME_PARTICLE_SET_PATH = "/World/CompletedPBD/ParticleSet"
EXPECTED_LEGACY_SAMPLER_PATH = "/World/fluid/Cylinder"
EXPECTED_LEGACY_PARTICLE_SET_PATH = "/World/ParticleSet"
EXPECTED_LEGACY_PARTICLE_SYSTEM_PATH = "/World/ParticleSystem"
EXPECTED_FROZEN_RUNNER_SHA256 = (
    "25f02f58e5a4d0adc11beaf503f8d5e74c5fcfafc7b1b7078e1a971ae50118e4"
)
EXPECTED_ACCEPTED_MATRIX_MANIFEST_SHA256 = (
    "582c8ee08a1025e71750782be8a6c8f6dbfaa3320eb8f73360b8608fdc26cf44"
)
EXPECTED_ACCEPTED_RUNTIME_SUMMARY_SHA256 = (
    "023290a49b9d1a7a0db6ecbe5dab2f4fd931e3f4948ceffc61866223bcc612cf"
)
ACCEPTED_MATRIX_MANIFEST_PATH = (
    REPO_ROOT
    / "docs"
    / "labutopia_lab_poc"
    / "evidence_manifests"
    / "fluid_spike_real_beaker_static_hold_matrix_si600_restoffset_20260711.json"
)
ACCEPTED_RUNTIME_SUMMARY_PATH = (
    REPO_ROOT
    / "docs"
    / "labutopia_lab_poc"
    / "evidence_manifests"
    / "fluid_spike_real_beaker_static_hold_matrix_si600_restoffset_20260711_001"
    / "P4096_S2"
    / "runtime_smoke_summary.json"
)
TRACE_SCHEMA_VERSION = 1
TRACE_RECORD_KEYS = (
    "aabb",
    "centroid",
    "nan_count",
    "particle_count",
    "positions",
    "region_counts",
    "step_index",
    "strict_visible_beaker_counts",
)
TRACE_REGION_KEYS = (
    "below_table_count",
    "finite_count",
    "source_count",
    "spill_count",
    "target_count",
    "total_count",
)
TRACE_STRICT_KEYS = (
    "above_visible_rim_count",
    "below_visible_floor_count",
    "canonical_axial_max",
    "canonical_axial_median",
    "canonical_axial_min",
    "finite_count",
    "inside_visible_interior_count",
    "legacy_source_region_count",
    "maximum_canonical_radius",
    "nonfinite_count",
    "outside_visible_radial_count",
    "particle_count",
    "strict_violating_point_count",
)
TRACE_SCHEMA_CONTRACT = {
    "schema_version": TRACE_SCHEMA_VERSION,
    "encoding": "utf-8-json-lines-newline-terminated",
    "duplicate_object_keys_allowed": False,
    "non_finite_numbers_allowed": False,
    "record_keys": list(TRACE_RECORD_KEYS),
    "region_count_keys": list(TRACE_REGION_KEYS),
    "strict_visible_count_keys": list(TRACE_STRICT_KEYS),
    "point_shape": [3],
    "aabb_keys": ["min", "max"],
    "aabb_vectors_are_finite_ordered_vec3": True,
    "centroid_is_finite_vec3": True,
    "count_fields_are_nonnegative_integers": True,
    "count_fields_match_particle_count": True,
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_sha256(name: str, value: Any) -> str:
    if not _is_sha256(value):
        raise ValueError(f"{name}_invalid")
    return str(value)


def _stable_identity(info: os.stat_result) -> dict[str, int]:
    return {
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "byte_count": int(info.st_size),
        "mtime_ns": int(info.st_mtime_ns),
    }


def _read_stable_regular_file(path: str | os.PathLike[str]) -> dict[str, Any]:
    target = Path(path).expanduser()
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags)
    except OSError as exc:
        raise ValueError(f"regular_file_open_failed:{target}:{exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"regular_file_required:{target}")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _stable_identity(before) != _stable_identity(after):
        raise ValueError(f"file_changed_during_read:{target}")
    payload = b"".join(chunks)
    if len(payload) != before.st_size:
        raise ValueError(f"file_size_changed_during_read:{target}")
    return {
        "path": str(target.resolve(strict=True)),
        "bytes": payload,
        "sha256": _sha256_bytes(payload),
        "identity": _stable_identity(before),
    }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"json_duplicate_key:{key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"json_non_finite_constant:{value}")


def _strict_json_bytes(payload: bytes) -> Any:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("json_bom_forbidden")
    return json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=_reject_constant,
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def reject_authority_self_reference(payloads: Mapping[str, bytes]) -> None:
    for name, payload in payloads.items():
        if SELF_REFERENCE_TOKEN in payload:
            raise ValueError(f"authority_bundle_self_reference_forbidden:{name}")


def snapshot_regular_tree(path: str | os.PathLike[str]) -> dict[str, Any]:
    root = Path(path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"runtime_evidence_root_not_directory:{root}")
    records: list[dict[str, Any]] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in sorted(directory_names):
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError(f"runtime_evidence_symlink_forbidden:{candidate}")
        for name in sorted(file_names):
            candidate = current_path / name
            if candidate.is_symlink():
                raise ValueError(f"runtime_evidence_symlink_forbidden:{candidate}")
            snapshot = _read_stable_regular_file(candidate)
            records.append(
                {
                    "path": candidate.relative_to(root).as_posix(),
                    "byte_count": snapshot["identity"]["byte_count"],
                    "sha256": snapshot["sha256"],
                }
            )
    records.sort(key=lambda item: item["path"])
    return {
        "schema_version": 1,
        "root_path": str(root),
        "file_count": len(records),
        "files": records,
        "tree_sha256": canonical_json_sha256_v1(records),
    }


def validate_frozen_runner_baseline(
    runner_path: str | os.PathLike[str],
    *,
    accepted_matrix_manifest_path: str | os.PathLike[str] = ACCEPTED_MATRIX_MANIFEST_PATH,
    accepted_runtime_summary_path: str | os.PathLike[str] = ACCEPTED_RUNTIME_SUMMARY_PATH,
) -> dict[str, Any]:
    runner = _read_stable_regular_file(runner_path)
    if runner["sha256"] != EXPECTED_FROZEN_RUNNER_SHA256:
        raise ValueError("frozen_runner_sha256_mismatch")
    matrix = _read_stable_regular_file(accepted_matrix_manifest_path)
    if matrix["sha256"] != EXPECTED_ACCEPTED_MATRIX_MANIFEST_SHA256:
        raise ValueError("accepted_matrix_manifest_sha256_mismatch")
    old_summary = _read_stable_regular_file(accepted_runtime_summary_path)
    if old_summary["sha256"] != EXPECTED_ACCEPTED_RUNTIME_SUMMARY_SHA256:
        raise ValueError("accepted_runtime_summary_sha256_mismatch")
    matrix_value = _strict_json_bytes(matrix["bytes"])
    summary_value = _strict_json_bytes(old_summary["bytes"])
    if not isinstance(matrix_value, Mapping) or not isinstance(
        summary_value, Mapping
    ):
        raise ValueError("frozen_runner_baseline_json_invalid")
    matches = [
        cell
        for cell in matrix_value.get("cells", [])
        if isinstance(cell, Mapping) and cell.get("cell_id") == "P4096_S2"
    ]
    if len(matches) != 1:
        raise ValueError("accepted_matrix_p4096_s2_record_invalid")
    cell = matches[0]
    cell_physical = cell.get("physical_authoring_identity")
    summary_physical = summary_value.get("physical_authoring_identity")
    if (
        cell.get("accepted") is not True
        or cell.get("strict_verified") is not True
        or cell.get("classification") != PASS_CLASSIFICATION
        or cell.get("artifact_hashes", {}).get("runtime_smoke_summary.json")
        != EXPECTED_ACCEPTED_RUNTIME_SUMMARY_SHA256
        or not isinstance(cell_physical, Mapping)
        or cell_physical.get("runner_script_sha256")
        != EXPECTED_FROZEN_RUNNER_SHA256
        or not isinstance(summary_physical, Mapping)
        or summary_physical.get("runner_script_sha256")
        != EXPECTED_FROZEN_RUNNER_SHA256
        or _classification_name(summary_value.get("strict_visible_classification"))
        != PASS_CLASSIFICATION
    ):
        raise ValueError("accepted_frozen_runner_record_invalid")
    return {
        "verified": True,
        "runner_script_path": runner["path"],
        "runner_script_sha256": runner["sha256"],
        "accepted_matrix_manifest_path": matrix["path"],
        "accepted_matrix_manifest_sha256": matrix["sha256"],
        "accepted_runtime_summary_path": old_summary["path"],
        "accepted_runtime_summary_sha256": old_summary["sha256"],
        "accepted_cell_id": "P4096_S2",
        "accepted_classification": PASS_CLASSIFICATION,
    }


def _finite_number(value: Any, *, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ValueError(f"trace_numeric_value_invalid:{name}")
    return float(value)


def _finite_vec3(value: Any, *, error: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(error)
    try:
        return [_finite_number(item, name=f"{error}.{index}") for index, item in enumerate(value)]
    except ValueError as exc:
        raise ValueError(error) from exc


def _nonnegative_int(value: Any, *, error: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(error)
    return value


def _strict_trace_records(payload: bytes) -> list[Mapping[str, Any]]:
    if not payload or not payload.endswith(b"\n"):
        raise ValueError("trace_newline_termination_invalid")
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError("trace_bom_forbidden")
    records: list[Mapping[str, Any]] = []
    for index, line in enumerate(payload.splitlines()):
        if not line:
            raise ValueError(f"trace_empty_record:{index}")
        value = _strict_json_bytes(line)
        if not isinstance(value, Mapping):
            raise ValueError(f"trace_record_not_object:{index}")
        records.append(value)
    return records


def recompute_strict_trace_identity(
    payload: bytes,
    *,
    source_usd_sha256: str,
    particle_count: int,
    seed: int,
    steps: int,
    trace_interval: int,
) -> dict[str, Any]:
    source_hash = _require_sha256("trace_source_usd_sha256", source_usd_sha256)
    if type(particle_count) is not int or particle_count <= 0:
        raise ValueError("trace_particle_count_invalid")
    if type(seed) is not int or seed < 0:
        raise ValueError("trace_seed_invalid")
    if type(steps) is not int or steps <= 0:
        raise ValueError("trace_steps_invalid")
    if type(trace_interval) is not int or not 0 < trace_interval <= steps:
        raise ValueError("trace_interval_invalid")
    expected_steps = list(range(0, steps + 1, trace_interval))
    if expected_steps[-1] != steps:
        expected_steps.append(steps)
    records = _strict_trace_records(payload)
    actual_steps: list[int] = []
    frame_counts: list[int] = []
    ordered_positions: list[Any] = []
    for index, record in enumerate(records):
        if tuple(sorted(record)) != tuple(sorted(TRACE_RECORD_KEYS)):
            raise ValueError(f"trace_record_schema_invalid:{index}")
        step_index = record["step_index"]
        count = record["particle_count"]
        positions = record["positions"]
        if type(step_index) is not int or type(count) is not int:
            raise ValueError(f"trace_record_index_or_count_invalid:{index}")
        if count != particle_count or not isinstance(positions, list) or len(positions) != count:
            raise ValueError(f"trace_particle_count_mismatch:{index}")
        for point_index, point in enumerate(positions):
            if not isinstance(point, list) or len(point) != 3:
                raise ValueError(f"trace_point_shape_invalid:{index}:{point_index}")
            for axis, value in enumerate(point):
                _finite_number(value, name=f"{index}.{point_index}.{axis}")
        centroid = _finite_vec3(
            record["centroid"], error=f"trace_centroid_invalid:{index}"
        )
        aabb = record["aabb"]
        if not isinstance(aabb, Mapping) or set(aabb) != {"min", "max"}:
            raise ValueError(f"trace_aabb_invalid:{index}")
        aabb_min = _finite_vec3(
            aabb["min"], error=f"trace_aabb_invalid:{index}"
        )
        aabb_max = _finite_vec3(
            aabb["max"], error=f"trace_aabb_invalid:{index}"
        )
        if any(
            aabb_min[axis] > aabb_max[axis]
            or centroid[axis] < aabb_min[axis]
            or centroid[axis] > aabb_max[axis]
            for axis in range(3)
        ):
            raise ValueError(f"trace_aabb_or_centroid_bounds_invalid:{index}")
        if type(record["nan_count"]) is not int or record["nan_count"] != 0:
            raise ValueError(f"trace_nan_count_nonzero:{index}")
        region = record["region_counts"]
        strict = record["strict_visible_beaker_counts"]
        if not isinstance(region, Mapping) or tuple(sorted(region)) != tuple(
            sorted(TRACE_REGION_KEYS)
        ):
            raise ValueError(f"trace_region_schema_invalid:{index}")
        if not isinstance(strict, Mapping) or tuple(sorted(strict)) != tuple(
            sorted(TRACE_STRICT_KEYS)
        ):
            raise ValueError(f"trace_strict_schema_invalid:{index}")
        for key in TRACE_REGION_KEYS:
            _nonnegative_int(
                region[key], error=f"trace_region_count_invalid:{index}:{key}"
            )
        strict_count_keys = (
            "above_visible_rim_count",
            "below_visible_floor_count",
            "finite_count",
            "inside_visible_interior_count",
            "legacy_source_region_count",
            "nonfinite_count",
            "outside_visible_radial_count",
            "particle_count",
            "strict_violating_point_count",
        )
        for key in strict_count_keys:
            _nonnegative_int(
                strict[key], error=f"trace_strict_count_invalid:{index}:{key}"
            )
        if (
            region["below_table_count"] != 0
            or region["spill_count"] != 0
            or region["target_count"] != 0
            or region["finite_count"] != particle_count
            or region["source_count"] != particle_count
            or region["total_count"] != particle_count
        ):
            raise ValueError(f"trace_region_containment_failed:{index}")
        if (
            strict["above_visible_rim_count"] != 0
            or strict["below_visible_floor_count"] != 0
            or strict["nonfinite_count"] != 0
            or strict["outside_visible_radial_count"] != 0
            or strict["strict_violating_point_count"] != 0
            or strict["finite_count"] != particle_count
            or strict["inside_visible_interior_count"] != particle_count
            or strict["legacy_source_region_count"] != particle_count
            or strict["particle_count"] != particle_count
        ):
            raise ValueError(f"trace_visible_containment_failed:{index}")
        for key in (
            "canonical_axial_max",
            "canonical_axial_median",
            "canonical_axial_min",
            "maximum_canonical_radius",
        ):
            _finite_number(strict[key], name=f"{index}.{key}")
        axial_min = float(strict["canonical_axial_min"])
        axial_median = float(strict["canonical_axial_median"])
        axial_max = float(strict["canonical_axial_max"])
        if (
            not axial_min <= axial_median <= axial_max
            or float(strict["maximum_canonical_radius"]) < 0.0
        ):
            raise ValueError(f"trace_strict_numeric_order_invalid:{index}")
        actual_steps.append(step_index)
        frame_counts.append(count)
        ordered_positions.append(positions)
    if actual_steps != expected_steps or len(actual_steps) != len(set(actual_steps)):
        raise ValueError("trace_frame_cadence_invalid")
    identity: dict[str, Any] = {
        "frame_indices": actual_steps,
        "frame_particle_counts": frame_counts,
        "frame_count": len(records),
        "source_usd_sha256": source_hash,
        "particle_count": particle_count,
        "seed": seed,
        "steps": steps,
        "trace_interval": trace_interval,
        "positions_sha256": canonical_json_sha256_v1(ordered_positions),
    }
    identity["physical_trace_sha256"] = canonical_json_sha256_v1(identity)
    identity["strict_trace_schema_version"] = TRACE_SCHEMA_VERSION
    identity["strict_trace_schema_sha256"] = canonical_json_sha256_v1(
        TRACE_SCHEMA_CONTRACT
    )
    return identity


def _runner_trace_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in identity.items()
        if key not in ("strict_trace_schema_version", "strict_trace_schema_sha256")
    }


def snapshot_declared_kit_log(
    path: str | os.PathLike[str], declared: Mapping[str, Any]
) -> dict[str, Any]:
    if (
        declared.get("cursor_captured") is not True
        or declared.get("diagnostic_scan_complete") is not True
    ):
        raise ValueError("kit_log_segment_not_complete")
    offset = declared.get("byte_offset")
    count = declared.get("segment_byte_count")
    expected_hash = _require_sha256(
        "kit_log_segment_sha256", declared.get("segment_sha256")
    )
    if type(offset) is not int or type(count) is not int or offset < 0 or count < 0:
        raise ValueError("kit_log_segment_range_invalid")
    snapshot = _read_stable_regular_file(path)
    full_payload = snapshot["bytes"]
    if offset + count > len(full_payload):
        raise ValueError("kit_log_segment_range_out_of_bounds")
    segment = full_payload[offset : offset + count]
    actual_hash = _sha256_bytes(segment)
    if actual_hash != expected_hash:
        raise ValueError("kit_log_segment_sha256_mismatch")
    return {
        "full_log_bytes": full_payload,
        "segment_bytes": segment,
        "provenance": {
            "source_log_path": snapshot["path"],
            "source_log_identity": snapshot["identity"],
            "source_log_byte_count": len(full_payload),
            "source_log_full_sha256": snapshot["sha256"],
            "byte_offset": offset,
            "segment_byte_count": count,
            "segment_sha256": actual_hash,
            "cursor_captured": True,
            "diagnostic_scan_complete": True,
        },
    }


def _classification_name(value: Any) -> str | None:
    if isinstance(value, Mapping):
        result = value.get("classification")
        return result if isinstance(result, str) else None
    return value if isinstance(value, str) else None


def validate_runtime_summary(
    summary: Mapping[str, Any],
    *,
    trace_identity: Mapping[str, Any],
    support_entry_path: Path,
    support_entry_sha256: str,
    runner_script_sha256: str,
) -> dict[str, Any]:
    entry_hash = _require_sha256(
        "support_entry_root_usd_sha256", support_entry_sha256
    )
    runner_hash = _require_sha256("runner_script_sha256", runner_script_sha256)
    if runner_hash != EXPECTED_FROZEN_RUNNER_SHA256:
        raise ValueError("frozen_runner_sha256_mismatch")
    classification = summary.get("classification")
    strict = summary.get("strict_visible_classification")
    legacy = summary.get("legacy_classification")
    if not isinstance(classification, Mapping) or not isinstance(strict, Mapping):
        raise ValueError("runtime_classification_missing")
    if (
        _classification_name(classification) != PASS_CLASSIFICATION
        or _classification_name(strict) != PASS_CLASSIFICATION
        or _classification_name(legacy) != LEGACY_PASS_CLASSIFICATION
        or strict.get("passed") is not True
        or summary.get("visible_beaker_containment_verified") is not True
        or summary.get("runtime_step_executed") is not True
        or summary.get("fatal_error") is not None
    ):
        raise ValueError("runtime_classification_not_accepted")
    zero_fields = (
        "max_below_floor",
        "max_outside_radius",
        "max_above_rim",
        "nonfinite_count",
    )
    if (
        strict.get("initial_count") != EXPECTED_PARTICLE_COUNT
        or strict.get("final_count") != EXPECTED_PARTICLE_COUNT
        or strict.get("final_inside") != EXPECTED_PARTICLE_COUNT
        or any(strict.get(name) != 0 for name in zero_fields)
        or strict.get("tail_leak_rate") != 0.0
        or strict.get("gpu_collider_unsupported") is not False
        or strict.get("cpu_collision_fallback_detected") is not False
        or strict.get("trace_schema_valid") is not True
        or strict.get("diagnostic_scan_complete") is not True
    ):
        raise ValueError("runtime_visible_containment_failed")
    frames = strict.get("frames")
    expected_steps = list(range(0, EXPECTED_STEPS + 1, EXPECTED_TRACE_INTERVAL))
    if not isinstance(frames, list) or [item.get("step_index") for item in frames] != expected_steps:
        raise ValueError("runtime_classification_frame_cadence_invalid")
    for index, frame in enumerate(frames):
        if (
            not isinstance(frame, Mapping)
            or frame.get("particle_count") != EXPECTED_PARTICLE_COUNT
            or frame.get("inside_visible_interior_count") != EXPECTED_PARTICLE_COUNT
            or frame.get("finite_count") != EXPECTED_PARTICLE_COUNT
            or any(
                frame.get(name) != 0
                for name in (
                    "above_visible_rim_count",
                    "below_visible_floor_count",
                    "nonfinite_count",
                    "outside_visible_radial_count",
                    "strict_violating_point_count",
                )
            )
        ):
            raise ValueError(f"runtime_classification_frame_failed:{index}")

    runner_identity = _runner_trace_identity(trace_identity)
    claimed_identities = (
        summary.get("physical_trace_identity"),
        classification.get("physical_trace_identity"),
        strict.get("physical_trace_identity"),
    )
    if any(
        not isinstance(value, Mapping) or dict(value) != runner_identity
        for value in claimed_identities
    ):
        raise ValueError("runtime_trace_identity_mismatch")
    source_path = Path(str(summary.get("source_usd_path"))).expanduser().resolve(
        strict=True
    )
    if source_path != support_entry_path.expanduser().resolve(strict=True):
        raise ValueError("runtime_source_path_mismatch")
    physical = summary.get("physical_authoring_identity")
    if not isinstance(physical, Mapping):
        raise ValueError("runtime_physical_authoring_identity_missing")
    if (
        physical.get("source_usd_sha256") != entry_hash
        or physical.get("runner_script_sha256") != runner_hash
        or physical.get("particle_count") != EXPECTED_PARTICLE_COUNT
        or physical.get("seed") != EXPECTED_SEED
    ):
        raise ValueError("runtime_source_identity_mismatch")
    if physical.get("schema_version") != 1 or not str(
        physical.get("isaacsim_version", "")
    ).startswith("4.1"):
        raise ValueError("runtime_version_contract_invalid")
    if (
        summary.get("steps") != EXPECTED_STEPS
        or summary.get("selected_particle_count") != EXPECTED_PARTICLE_COUNT
        or summary.get("logical_dt") != EXPECTED_LOGICAL_DT
        or summary.get("integration_dt") != EXPECTED_INTEGRATION_DT
        or summary.get("substeps_per_logical_step") != EXPECTED_SUBSTEPS
    ):
        raise ValueError("runtime_step_schedule_invalid")
    execution = summary.get("strict_physics_execution")
    if not isinstance(execution, Mapping) or (
        execution.get("requested_logical_steps") != EXPECTED_STEPS
        or execution.get("executed_logical_steps") != EXPECTED_STEPS
        or execution.get("requested_integration_steps")
        != EXPECTED_STEPS * EXPECTED_SUBSTEPS
        or execution.get("executed_integration_steps")
        != EXPECTED_STEPS * EXPECTED_SUBSTEPS
        or execution.get("exact_step_count_verified") is not True
        or execution.get("ordered_lifecycle_verified") is not True
        or execution.get("attach_verified") is not True
        or execution.get("detach_verified") is not True
    ):
        raise ValueError("runtime_execution_contract_invalid")
    spawn = summary.get("controlled_spawn_plan")
    if not isinstance(spawn, Mapping) or (
        spawn.get("controlled_spawn") is not True
        or spawn.get("particle_count") != EXPECTED_PARTICLE_COUNT
        or spawn.get("particle_seed") != EXPECTED_SEED
        or spawn.get("raw_colleague_points_used") is not False
        or spawn.get("wrapper_variant_id") != "D4A_018"
    ):
        raise ValueError("runtime_controlled_spawn_contract_invalid")
    authored = summary.get("authored_runtime_paths")
    if not isinstance(authored, Mapping) or (
        authored.get("particle_system_path")
        != EXPECTED_RUNTIME_PARTICLE_SYSTEM_PATH
        or authored.get("particle_set_path") != EXPECTED_RUNTIME_PARTICLE_SET_PATH
        or authored.get("source_particle_system_path")
        != EXPECTED_LEGACY_PARTICLE_SYSTEM_PATH
        or authored.get("source_particle_set_path")
        != EXPECTED_LEGACY_PARTICLE_SET_PATH
    ):
        raise ValueError("runtime_particle_authority_paths_invalid")
    isolation = (summary.get("original_fluid_deactivate_summary") or {}).get(
        "ownership_isolation"
    )
    sampling_api = summary.get("legacy_particle_sampling_api_removal")
    if not isinstance(isolation, Mapping) or (
        isolation.get("verified") is not True
        or isolation.get("sampler_targets_after") != []
        or isolation.get("particle_set_targets_after") != []
        or isolation.get("synchronization_required") is not False
    ):
        raise ValueError("runtime_legacy_graph_readback_invalid")
    if not isinstance(sampling_api, Mapping) or (
        sampling_api.get("verified") is not True
        or sampling_api.get("api_present_after") is not False
        or sampling_api.get("sampler_path") != EXPECTED_LEGACY_SAMPLER_PATH
    ):
        raise ValueError("runtime_sampling_api_readback_invalid")
    log_segment = summary.get("strict_kit_log_segment")
    log_summary = summary.get("isaac_log_summary")
    if not isinstance(log_segment, Mapping) or not isinstance(log_summary, Mapping):
        raise ValueError("runtime_kit_log_contract_missing")
    if (
        log_summary.get("run_segment_only") is not True
        or log_summary.get("diagnostic_scan_complete") is not True
        or log_summary.get("error_count") != 0
        or log_summary.get("mdl_compile_status") != "PASS"
        or any(
            log_summary.get(name) is not False
            for name in (
                "has_omniglass_compile_error",
                "has_omnipbr_compile_error",
                "has_omnisurface_compile_error",
            )
        )
        or any(
            log_summary.get(name) != log_segment.get(name)
            for name in (
                "byte_offset",
                "segment_byte_count",
                "segment_sha256",
                "diagnostic_scan_complete",
            )
        )
    ):
        raise ValueError("runtime_kit_log_contract_invalid")
    return {
        "same_run_legacy_graph_readback_verified": True,
        "same_run_sampler_api_absent": True,
        "controlled_particle_system_path": EXPECTED_RUNTIME_PARTICLE_SYSTEM_PATH,
        "controlled_particle_set_path": EXPECTED_RUNTIME_PARTICLE_SET_PATH,
        "runtime_contract_schema_version": physical["schema_version"],
        "isaacsim_version": physical["isaacsim_version"],
        "runner_script_sha256": runner_hash,
    }


def _api_schema_tokens(prim: Any) -> list[str]:
    tokens = set(str(value) for value in prim.GetAppliedSchemas())
    metadata = prim.GetMetadata("apiSchemas")
    if metadata is not None:
        try:
            tokens.update(str(value) for value in metadata.GetAppliedItems())
        except AttributeError:
            tokens.update(str(value) for value in metadata)
    return sorted(tokens)


def _compact_attr_value(attr: Any) -> Any:
    value = attr.Get()
    try:
        count = len(value)
    except TypeError:
        count = None
    if count is not None and not isinstance(value, str) and count > 256:
        converted = [[float(axis) for axis in item] for item in value]
        return {
            "value_count": count,
            "value_sha256": canonical_json_sha256_v1(converted),
        }
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    try:
        return [
            [float(axis) for axis in item]
            if not isinstance(item, (str, bool, int, float))
            else item
            for item in value
        ]
    except TypeError:
        return str(value)


def enumerate_runtime_particle_graph(
    *,
    runtime_scene_path: str | os.PathLike[str],
    support_entry_path: str | os.PathLike[str],
) -> dict[str, Any]:
    from pxr import Sdf, Usd, UsdGeom

    runtime_scene = Path(runtime_scene_path).expanduser().resolve(strict=True)
    support_entry = Path(support_entry_path).expanduser().resolve(strict=True)
    root = Sdf.Layer.CreateAnonymous("support_aligned_runtime_authority.usda")
    root.subLayerPaths = [str(runtime_scene), str(support_entry)]
    stage = Usd.Stage.Open(root, Usd.Stage.LoadAll)
    if stage is None:
        raise ValueError("runtime_particle_graph_stage_open_failed")
    records = []
    enabled_systems = []
    active_sets = []
    active_samplers = []
    for prim in stage.TraverseAll():
        properties = list(prim.GetProperties())
        property_names = [item.GetName() for item in properties]
        path = str(prim.GetPath())
        type_name = str(prim.GetTypeName())
        if not (
            "particle" in path.lower()
            or "particle" in type_name.lower()
            or any("particle" in name.lower() for name in property_names)
        ):
            continue
        relationships = {
            relationship.GetName(): [str(value) for value in relationship.GetTargets()]
            for relationship in prim.GetRelationships()
            if "particle" in relationship.GetName().lower()
        }
        attributes = {
            attr.GetName(): _compact_attr_value(attr)
            for attr in prim.GetAttributes()
            if "particle" in attr.GetName().lower()
            or attr.GetName() == "visibility"
        }
        schemas = _api_schema_tokens(prim)
        record = {
            "path": path,
            "type_name": type_name,
            "active": bool(prim.IsActive()),
            "visibility": UsdGeom.Imageable(prim).GetVisibilityAttr().Get(),
            "applied_schemas": schemas,
            "attributes": attributes,
            "relationships": relationships,
        }
        records.append(record)
        if "particlesystem" in type_name.lower() and prim.IsActive():
            enabled = prim.GetAttribute("particleSystemEnabled")
            if not enabled or enabled.Get() is not False:
                enabled_systems.append(path)
        particle_system_targets = relationships.get(
            "physxParticle:particleSystem", []
        )
        fluid_attr = prim.GetAttribute("physxParticle:fluid")
        if (
            prim.IsActive()
            and particle_system_targets
            and fluid_attr
            and fluid_attr.Get() is True
        ):
            active_sets.append(path)
        sampler_targets = relationships.get(
            "physxParticleSampling:particles", []
        )
        volume_attr = prim.GetAttribute("physxParticleSampling:volume")
        if (
            prim.IsActive()
            and sampler_targets
            and (not volume_attr or volume_attr.Get() is not False)
        ):
            active_samplers.append(path)
    records.sort(key=lambda item: item["path"])
    enabled_systems.sort()
    active_sets.sort()
    active_samplers.sort()

    def get_record(path: str) -> Mapping[str, Any]:
        matches = [record for record in records if record["path"] == path]
        if len(matches) != 1:
            raise ValueError(f"runtime_particle_graph_prim_missing:{path}")
        return matches[0]

    legacy_sampler = get_record(EXPECTED_LEGACY_SAMPLER_PATH)
    legacy_set = get_record(EXPECTED_LEGACY_PARTICLE_SET_PATH)
    legacy_system = get_record(EXPECTED_LEGACY_PARTICLE_SYSTEM_PATH)
    legacy_graph = {
        "sampler_targets": legacy_sampler["relationships"].get(
            "physxParticleSampling:particles", []
        ),
        "particle_system_targets": legacy_set["relationships"].get(
            "physxParticle:particleSystem", []
        ),
        "sampler_volume": legacy_sampler["attributes"].get(
            "physxParticleSampling:volume"
        ),
        "particle_set_fluid": legacy_set["attributes"].get(
            "physxParticle:fluid"
        ),
        "particle_set_self_collision": legacy_set["attributes"].get(
            "physxParticle:selfCollision"
        ),
        "particle_system_enabled": legacy_system["attributes"].get(
            "particleSystemEnabled"
        ),
        "sampling_api_present": "PhysxParticleSamplingAPI"
        in legacy_sampler["applied_schemas"],
    }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "runtime_scene_path": str(runtime_scene),
        "runtime_scene_sha256": _read_stable_regular_file(runtime_scene)["sha256"],
        "support_entry_path": str(support_entry),
        "support_entry_sha256": _read_stable_regular_file(support_entry)["sha256"],
        "particle_graph_records": records,
        "enabled_particle_system_paths": enabled_systems,
        "active_particle_set_paths": active_sets,
        "active_sampler_paths": active_samplers,
        "legacy_graph": legacy_graph,
    }
    payload["verified"] = (
        enabled_systems == [EXPECTED_RUNTIME_PARTICLE_SYSTEM_PATH]
        and active_sets == [EXPECTED_RUNTIME_PARTICLE_SET_PATH]
        and active_samplers == []
        and legacy_graph
        == {
            "sampler_targets": [],
            "particle_system_targets": [],
            "sampler_volume": False,
            "particle_set_fluid": False,
            "particle_set_self_collision": False,
            "particle_system_enabled": False,
            "sampling_api_present": False,
        }
    )
    if payload["verified"] is not True:
        raise ValueError("runtime_particle_authority_not_unique")
    payload["runtime_particle_graph_sha256"] = canonical_json_sha256_v1(payload)
    return payload


def _validate_support_manifest(
    manifest: Mapping[str, Any], manifest_sha256: str
) -> dict[str, Any]:
    if (
        manifest.get("schema_version") != 1
        or manifest.get("manifest_type") != "level1_pour_support_aligned_source"
        or manifest.get("support_alignment_verified") is not True
        or manifest.get("layout_semantics")
        != "config_range_midpoint_support_aligned"
        or manifest.get("exact_expert_episode_layout") is not False
    ):
        raise ValueError("support_manifest_contract_invalid")
    payload = dict(manifest)
    expected_manifest_hash = _require_sha256(
        "manifest_payload_sha256", payload.pop("manifest_payload_sha256", None)
    )
    if canonical_json_sha256_v1(payload) != expected_manifest_hash:
        raise ValueError("support_manifest_payload_sha256_mismatch")
    contract = manifest.get("support_alignment_contract")
    if not isinstance(contract, Mapping):
        raise ValueError("support_alignment_contract_missing")
    contract_payload = dict(contract)
    expected_contract_hash = _require_sha256(
        "support_aligned_source_contract_sha256",
        contract_payload.pop("support_aligned_source_contract_sha256", None),
    )
    if canonical_json_sha256_v1(contract_payload) != expected_contract_hash:
        raise ValueError("support_aligned_source_contract_sha256_mismatch")
    if (
        manifest.get("localized_source_usd_sha256")
        != contract.get("source_usd_sha256")
        or manifest.get("config_sha256") != contract.get("config_sha256")
    ):
        raise ValueError("support_manifest_source_contract_mismatch")
    paths = {
        "localized_source": Path(str(manifest["localized_source_usd_path"])),
        "support_overlay": Path(str(manifest["support_overlay_usd_path"])),
        "support_entry_root": Path(str(manifest["support_entry_root_usd_path"])),
        "config": Path(str(manifest["config_path"])),
        "support_builder": Path(str(manifest["builder_script_path"])),
    }
    hashes = {
        "localized_source": manifest["localized_source_usd_sha256"],
        "support_overlay": manifest["support_overlay_usd_sha256"],
        "support_entry_root": manifest["support_entry_root_usd_sha256"],
        "config": manifest["config_sha256"],
        "support_builder": manifest["builder_script_sha256"],
    }
    snapshots = {}
    for name, path in paths.items():
        snapshot = _read_stable_regular_file(path)
        expected = _require_sha256(f"{name}_sha256", hashes[name])
        if snapshot["sha256"] != expected:
            raise ValueError(f"support_manifest_file_sha256_mismatch:{name}")
        snapshots[name] = snapshot
    plain_reopen = manifest.get("plain_reopen_verification")
    if not isinstance(plain_reopen, Mapping) or (
        plain_reopen.get("support_alignment_verified") is not True
        or (plain_reopen.get("legacy_particle_graph_isolation") or {}).get(
            "verified"
        )
        is not True
    ):
        raise ValueError("support_manifest_plain_reopen_invalid")
    return {
        "manifest_sha256": manifest_sha256,
        "manifest_payload_sha256": expected_manifest_hash,
        "support_aligned_source_contract_sha256": expected_contract_hash,
        "config_layout_contract_sha256": contract[
            "config_layout_contract_sha256"
        ],
        "snapshots": snapshots,
    }


def _kernel_rename_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise RuntimeError("renameat2_noreplace_unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(destination),
        1,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in (errno.EEXIST, errno.ENOTEMPTY):
        raise ValueError(f"output_directory_already_exists:{destination}")
    raise OSError(error_number, os.strerror(error_number), str(destination))


def _detect_publish_mode(parent: Path) -> str:
    probe_id = uuid.uuid4().hex
    source = parent / f".authority-publish-probe-source-{probe_id}"
    destination = parent / f".authority-publish-probe-destination-{probe_id}"
    source.mkdir()
    try:
        try:
            _kernel_rename_noreplace(source, destination)
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP):
                raise
            return "atomic_mkdir_commit_marker"
        destination.rmdir()
        return "kernel_renameat2_noreplace"
    finally:
        if source.exists():
            source.rmdir()
        if destination.exists():
            destination.rmdir()


def _atomic_rename_noreplace(
    source: Path,
    destination: Path,
    *,
    publish_mode: str,
) -> None:
    if publish_mode == "kernel_renameat2_noreplace":
        _kernel_rename_noreplace(source, destination)
        return
    if publish_mode != "atomic_mkdir_commit_marker":
        raise ValueError(f"publish_mode_invalid:{publish_mode}")
    marker = source / PUBLISH_COMPLETE_BASENAME
    if not marker.is_file() or marker.is_symlink():
        raise ValueError("publish_complete_marker_missing_from_staging")
    try:
        destination.mkdir()
    except FileExistsError as exc:
        raise ValueError(f"output_directory_already_exists:{destination}") from exc
    _publish_staging_into_reserved_directory(source, destination)


def _publish_staging_into_reserved_directory(
    source: Path, destination: Path
) -> None:
    marker = source / PUBLISH_COMPLETE_BASENAME
    if not marker.is_file() or marker.is_symlink():
        raise ValueError("publish_complete_marker_missing_from_staging")
    if not destination.is_dir() or source.stat().st_dev != destination.stat().st_dev:
        raise ValueError("publish_requires_reserved_same_filesystem_directory")
    directories = sorted(
        (path for path in source.rglob("*") if path.is_dir()),
        key=lambda path: (len(path.relative_to(source).parts), path.as_posix()),
    )
    for directory in directories:
        relative = directory.relative_to(source)
        target = destination / relative
        try:
            target.mkdir()
        except FileExistsError as exc:
            raise ValueError(f"publish_destination_directory_exists:{relative}") from exc
    files = sorted(
        (
            path
            for path in source.rglob("*")
            if path.is_file() and path != marker
        ),
        key=lambda path: path.relative_to(source).as_posix(),
    )
    for path in files:
        if path.is_symlink():
            raise ValueError(f"publish_staging_artifact_invalid:{path}")
        relative = path.relative_to(source)
        target = destination / relative
        try:
            os.link(path, target, follow_symlinks=False)
        except FileExistsError as exc:
            raise ValueError(f"publish_destination_artifact_exists:{relative}") from exc
        path.unlink()
    try:
        os.link(marker, destination / marker.name, follow_symlinks=False)
    except FileExistsError as exc:
        raise ValueError("publish_destination_commit_marker_exists") from exc
    marker.unlink()
    for directory in reversed(directories):
        directory.rmdir()
    source.rmdir()


def _validate_output_artifacts(root: Path, bundle: Mapping[str, Any]) -> None:
    registry = bundle.get("bundle_artifacts")
    if not isinstance(registry, list):
        raise ValueError("bundle_artifact_registry_missing")
    registered_paths = [item.get("path") for item in registry]
    if (
        any(not isinstance(value, str) or not value for value in registered_paths)
        or len(registered_paths) != len(set(registered_paths))
    ):
        raise ValueError("bundle_artifact_registry_invalid")
    for item in registry:
        path = root / item["path"]
        snapshot = _read_stable_regular_file(path)
        if (
            snapshot["sha256"] != item.get("sha256")
            or snapshot["identity"]["byte_count"] != item.get("byte_count")
        ):
            raise ValueError(f"bundle_artifact_hash_mismatch:{item['path']}")
    if canonical_json_sha256_v1(registry) != bundle.get(
        "bundle_artifact_tree_sha256"
    ):
        raise ValueError("bundle_artifact_tree_sha256_mismatch")
    actual_paths = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"authority_output_symlink_forbidden:{path}")
        if path.is_file():
            actual_paths.add(path.relative_to(root).as_posix())
    expected_paths = set(registered_paths) | {
        BUNDLE_BASENAME,
        PUBLISH_COMPLETE_BASENAME,
    }
    if actual_paths != expected_paths:
        raise ValueError("authority_output_file_registry_mismatch")


def _validate_final_bundle(root: Path) -> dict[str, Any]:
    bundle_snapshot = _read_stable_regular_file(root / BUNDLE_BASENAME)
    bundle = _strict_json_bytes(bundle_snapshot["bytes"])
    if not isinstance(bundle, Mapping):
        raise ValueError("accepted_authority_bundle_not_object")
    payload = dict(bundle)
    expected_hash = _require_sha256(
        "accepted_authority_bundle_sha256",
        payload.pop("accepted_authority_bundle_sha256", None),
    )
    if canonical_json_sha256_v1(payload) != expected_hash:
        raise ValueError("accepted_authority_bundle_sha256_mismatch")
    marker_snapshot = _read_stable_regular_file(root / PUBLISH_COMPLETE_BASENAME)
    marker = _strict_json_bytes(marker_snapshot["bytes"])
    if not isinstance(marker, Mapping):
        raise ValueError("publish_complete_marker_not_object")
    marker_payload = dict(marker)
    expected_marker_hash = _require_sha256(
        "publish_commit_sha256", marker_payload.pop("publish_commit_sha256", None)
    )
    if canonical_json_sha256_v1(marker_payload) != expected_marker_hash:
        raise ValueError("publish_complete_marker_sha256_mismatch")
    publish_contract = bundle.get("publish_contract")
    if not isinstance(publish_contract, Mapping) or (
        marker.get("committed") is not True
        or marker.get("accepted_authority_bundle_sha256") != expected_hash
        or marker.get("accepted_authority_bundle_file_sha256")
        != bundle_snapshot["sha256"]
        or marker.get("publish_mode") != publish_contract.get("publish_mode")
        or publish_contract.get("commit_marker") != PUBLISH_COMPLETE_BASENAME
    ):
        raise ValueError("publish_complete_marker_contract_invalid")
    copied_runtime_tree = snapshot_regular_tree(root / RUNTIME_EVIDENCE_SNAPSHOT_DIR)
    if (
        copied_runtime_tree["tree_sha256"]
        != bundle.get("runtime_evidence_snapshot_tree_sha256")
        or copied_runtime_tree["tree_sha256"]
        != bundle.get("runtime_evidence_tree_sha256")
        or copied_runtime_tree["file_count"]
        != bundle.get("runtime_evidence_snapshot_file_count")
    ):
        raise ValueError("runtime_evidence_snapshot_contract_invalid")
    frozen_baseline = bundle.get("frozen_runner_baseline")
    if not isinstance(frozen_baseline, Mapping) or (
        frozen_baseline.get("verified") is not True
        or frozen_baseline.get("runner_script_sha256")
        != EXPECTED_FROZEN_RUNNER_SHA256
        or _read_stable_regular_file(
            root / FROZEN_BASELINE_DIR / FROZEN_RUNNER_BASENAME
        )["sha256"]
        != EXPECTED_FROZEN_RUNNER_SHA256
        or _read_stable_regular_file(
            root / FROZEN_BASELINE_DIR / FROZEN_MATRIX_MANIFEST_BASENAME
        )["sha256"]
        != EXPECTED_ACCEPTED_MATRIX_MANIFEST_SHA256
        or _read_stable_regular_file(
            root / FROZEN_BASELINE_DIR / FROZEN_RUNTIME_SUMMARY_BASENAME
        )["sha256"]
        != EXPECTED_ACCEPTED_RUNTIME_SUMMARY_SHA256
    ):
        raise ValueError("frozen_runner_snapshot_contract_invalid")
    _validate_output_artifacts(root, bundle)
    return dict(bundle)


def _acquire_output_lock(lock_path: Path) -> tuple[int, str]:
    token = uuid.uuid4().hex
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_RDWR,
            0o600,
        )
    except FileExistsError as exc:
        raise ValueError(f"output_directory_lock_exists:{lock_path}") from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        payload = f"pid={os.getpid()} token={token}\n".encode("ascii")
        os.write(descriptor, payload)
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return descriptor, token


def _verify_output_lock_owner(
    descriptor: int, lock_path: Path, token: str
) -> bool:
    descriptor_info = os.fstat(descriptor)
    try:
        path_info = lock_path.stat()
    except FileNotFoundError:
        return False
    payload = os.pread(descriptor, descriptor_info.st_size, 0)
    expected = f"pid={os.getpid()} token={token}\n".encode("ascii")
    return (
        descriptor_info.st_dev == path_info.st_dev
        and descriptor_info.st_ino == path_info.st_ino
        and payload == expected
    )


def _snapshot_runtime_evidence_into_staging(
    *,
    runtime_root: Path,
    runtime_tree: Mapping[str, Any],
    staging_root: Path,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    payloads: dict[str, bytes] = {}
    for record in runtime_tree["files"]:
        relative = Path(record["path"])
        source_snapshot = _read_stable_regular_file(runtime_root / relative)
        if (
            source_snapshot["sha256"] != record["sha256"]
            or source_snapshot["identity"]["byte_count"] != record["byte_count"]
        ):
            raise ValueError(f"runtime_evidence_snapshot_drift:{record['path']}")
        target = staging_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source_snapshot["bytes"])
        payloads[record["path"]] = source_snapshot["bytes"]
    copied_tree = snapshot_regular_tree(staging_root)
    if (
        copied_tree["files"] != runtime_tree["files"]
        or copied_tree["tree_sha256"] != runtime_tree["tree_sha256"]
    ):
        raise ValueError("runtime_evidence_snapshot_tree_mismatch")
    return payloads, copied_tree


def _staging_artifact_registry(root: Path) -> list[dict[str, Any]]:
    records = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"bundle_staging_symlink_forbidden:{path}")
        if not path.is_file():
            continue
        if path.name in (BUNDLE_BASENAME, PUBLISH_COMPLETE_BASENAME) and path.parent == root:
            continue
        snapshot = _read_stable_regular_file(path)
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "byte_count": snapshot["identity"]["byte_count"],
                "sha256": snapshot["sha256"],
            }
        )
    records.sort(key=lambda item: item["path"])
    return records


def build_accepted_authority_bundle(
    *,
    support_manifest_path: str | os.PathLike[str],
    runtime_summary_path: str | os.PathLike[str],
    trace_path: str | os.PathLike[str],
    runtime_scene_path: str | os.PathLike[str],
    runner_path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
) -> dict[str, Any]:
    output = Path(out_dir).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f"output_directory_already_exists:{output}")
    lock_path = output.with_name(f".{output.name}.lock")
    lock_descriptor, lock_token = _acquire_output_lock(lock_path)
    temp = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    try:
        if output.exists():
            raise ValueError(f"output_directory_already_exists:{output}")
        temp.mkdir(parents=False, exist_ok=False)
        publish_mode = _detect_publish_mode(output.parent)
        support_manifest_file = Path(support_manifest_path).expanduser().resolve(
            strict=True
        )
        runtime_summary_file = Path(runtime_summary_path).expanduser().resolve(
            strict=True
        )
        trace_file = Path(trace_path).expanduser().resolve(strict=True)
        runtime_scene_file = Path(runtime_scene_path).expanduser().resolve(strict=True)
        runner_file = Path(runner_path).expanduser().resolve(strict=True)
        runtime_root = runtime_summary_file.parent
        if trace_file.parent != runtime_root or runtime_scene_file.parent != runtime_root:
            raise ValueError("runtime_evidence_inputs_must_share_root")
        runtime_tree_before = snapshot_regular_tree(runtime_root)
        runtime_registry = {
            item["path"]: item for item in runtime_tree_before["files"]
        }
        required_runtime_names = {
            runtime_summary_file.name,
            trace_file.name,
            runtime_scene_file.name,
        }
        if not required_runtime_names.issubset(runtime_registry):
            raise ValueError("runtime_evidence_required_file_missing_from_tree")
        runtime_snapshot_root = temp / RUNTIME_EVIDENCE_SNAPSHOT_DIR
        runtime_payloads, copied_runtime_tree = (
            _snapshot_runtime_evidence_into_staging(
                runtime_root=runtime_root,
                runtime_tree=runtime_tree_before,
                staging_root=runtime_snapshot_root,
            )
        )

        support_manifest_snapshot = _read_stable_regular_file(
            support_manifest_file
        )
        summary_snapshot = _read_stable_regular_file(runtime_summary_file)
        trace_snapshot = _read_stable_regular_file(trace_file)
        runtime_scene_snapshot = _read_stable_regular_file(runtime_scene_file)
        runner_snapshot = _read_stable_regular_file(runner_file)
        frozen_runner_baseline = validate_frozen_runner_baseline(runner_file)
        accepted_matrix_snapshot = _read_stable_regular_file(
            ACCEPTED_MATRIX_MANIFEST_PATH
        )
        accepted_runtime_summary_snapshot = _read_stable_regular_file(
            ACCEPTED_RUNTIME_SUMMARY_PATH
        )
        for path, snapshot in (
            (runtime_summary_file, summary_snapshot),
            (trace_file, trace_snapshot),
            (runtime_scene_file, runtime_scene_snapshot),
        ):
            record = runtime_registry[path.name]
            if (
                snapshot["sha256"] != record["sha256"]
                or snapshot["identity"]["byte_count"] != record["byte_count"]
            ):
                raise ValueError(f"runtime_evidence_tree_snapshot_drift:{path.name}")
        support_manifest = _strict_json_bytes(support_manifest_snapshot["bytes"])
        summary = _strict_json_bytes(summary_snapshot["bytes"])
        if not isinstance(support_manifest, Mapping) or not isinstance(
            summary, Mapping
        ):
            raise ValueError("authority_input_json_root_invalid")
        support_validation = _validate_support_manifest(
            support_manifest, support_manifest_snapshot["sha256"]
        )
        support_snapshots = support_validation["snapshots"]
        entry_path = Path(support_snapshots["support_entry_root"]["path"])
        entry_hash = support_snapshots["support_entry_root"]["sha256"]
        if entry_hash != support_manifest["support_entry_root_usd_sha256"]:
            raise ValueError("support_entry_root_usd_sha256_mismatch")
        if Path(str(summary.get("trace_path"))).resolve(strict=True) != trace_file:
            raise ValueError("runtime_summary_trace_path_mismatch")
        if Path(str(summary.get("evidence_scene_path"))).resolve(
            strict=True
        ) != runtime_scene_file:
            raise ValueError("runtime_summary_scene_path_mismatch")

        trace_identity = recompute_strict_trace_identity(
            trace_snapshot["bytes"],
            source_usd_sha256=entry_hash,
            particle_count=EXPECTED_PARTICLE_COUNT,
            seed=EXPECTED_SEED,
            steps=EXPECTED_STEPS,
            trace_interval=EXPECTED_TRACE_INTERVAL,
        )
        runtime_summary_validation = validate_runtime_summary(
            summary,
            trace_identity=trace_identity,
            support_entry_path=entry_path,
            support_entry_sha256=entry_hash,
            runner_script_sha256=runner_snapshot["sha256"],
        )
        log_path = Path(str(summary["strict_kit_log_segment"]["log_path"]))
        log_snapshot = snapshot_declared_kit_log(
            log_path, summary["strict_kit_log_segment"]
        )
        particle_graph = enumerate_runtime_particle_graph(
            runtime_scene_path=runtime_scene_file,
            support_entry_path=entry_path,
        )

        self_reference_payloads = {
            "support_manifest": support_manifest_snapshot["bytes"],
            "runtime_summary": summary_snapshot["bytes"],
            "trace": trace_snapshot["bytes"],
            "runtime_scene": runtime_scene_snapshot["bytes"],
            "runner": runner_snapshot["bytes"],
            "kit_log": log_snapshot["full_log_bytes"],
            "accepted_matrix_manifest": accepted_matrix_snapshot["bytes"],
            "accepted_runtime_summary": accepted_runtime_summary_snapshot["bytes"],
        }
        for name, snapshot in support_snapshots.items():
            self_reference_payloads[f"support_{name}"] = snapshot["bytes"]
        for relative, payload in runtime_payloads.items():
            self_reference_payloads[f"runtime_tree:{relative}"] = payload
        reject_authority_self_reference(self_reference_payloads)

        full_log_path = temp / FULL_LOG_BASENAME
        segment_path = temp / LOG_SEGMENT_BASENAME
        particle_graph_path = temp / PARTICLE_GRAPH_BASENAME
        full_log_path.write_bytes(log_snapshot["full_log_bytes"])
        segment_path.write_bytes(log_snapshot["segment_bytes"])
        _write_json(particle_graph_path, particle_graph)
        frozen_baseline_root = temp / FROZEN_BASELINE_DIR
        frozen_baseline_root.mkdir()
        (frozen_baseline_root / FROZEN_RUNNER_BASENAME).write_bytes(
            runner_snapshot["bytes"]
        )
        (frozen_baseline_root / FROZEN_MATRIX_MANIFEST_BASENAME).write_bytes(
            accepted_matrix_snapshot["bytes"]
        )
        (frozen_baseline_root / FROZEN_RUNTIME_SUMMARY_BASENAME).write_bytes(
            accepted_runtime_summary_snapshot["bytes"]
        )
        frozen_runner_baseline = {
            **frozen_runner_baseline,
            "snapshot_directory": FROZEN_BASELINE_DIR,
            "runner_snapshot_path": (
                f"{FROZEN_BASELINE_DIR}/{FROZEN_RUNNER_BASENAME}"
            ),
            "accepted_matrix_manifest_snapshot_path": (
                f"{FROZEN_BASELINE_DIR}/{FROZEN_MATRIX_MANIFEST_BASENAME}"
            ),
            "accepted_runtime_summary_snapshot_path": (
                f"{FROZEN_BASELINE_DIR}/{FROZEN_RUNTIME_SUMMARY_BASENAME}"
            ),
        }
        copied_full_log = _read_stable_regular_file(full_log_path)
        copied_segment = _read_stable_regular_file(segment_path)
        if (
            copied_full_log["sha256"]
            != log_snapshot["provenance"]["source_log_full_sha256"]
            or copied_segment["sha256"]
            != log_snapshot["provenance"]["segment_sha256"]
        ):
            raise ValueError("kit_log_staging_copy_mismatch")
        artifact_records = _staging_artifact_registry(temp)
        lock_owner_verified_before_bundle = _verify_output_lock_owner(
            lock_descriptor, lock_path, lock_token
        )
        if not lock_owner_verified_before_bundle:
            raise ValueError("output_lock_owner_verification_failed")
        bundle: dict[str, Any] = {
            "schema_version": 1,
            "manifest_type": "support_aligned_p4096_s2_accepted_authority",
            "accepted": True,
            "layout_semantics": "config_range_midpoint_support_aligned",
            "exact_expert_episode_layout": False,
            "physics_authority_steps": EXPECTED_STEPS,
            "physics_authority_particle_count": EXPECTED_PARTICLE_COUNT,
            "physics_authority_seed": EXPECTED_SEED,
            "input_paths": {
                "support_manifest_path": str(support_manifest_file),
                "runtime_summary_path": str(runtime_summary_file),
                "particle_trace_path": str(trace_file),
                "runtime_scene_path": str(runtime_scene_file),
                "frozen_runner_path": str(runner_file),
            },
            "input_hashes": {
                "support_manifest_sha256": support_manifest_snapshot["sha256"],
                "runtime_summary_sha256": summary_snapshot["sha256"],
                "particle_trace_file_sha256": trace_snapshot["sha256"],
                "runtime_scene_sha256": runtime_scene_snapshot["sha256"],
                "frozen_runner_sha256": runner_snapshot["sha256"],
                "accepted_matrix_manifest_sha256": accepted_matrix_snapshot[
                    "sha256"
                ],
                "accepted_runtime_summary_sha256": (
                    accepted_runtime_summary_snapshot["sha256"]
                ),
                "localized_source_usd_sha256": support_snapshots[
                    "localized_source"
                ]["sha256"],
                "support_overlay_usd_sha256": support_snapshots[
                    "support_overlay"
                ]["sha256"],
                "support_entry_root_usd_sha256": entry_hash,
                "config_sha256": support_snapshots["config"]["sha256"],
                "support_builder_sha256": support_snapshots["support_builder"][
                    "sha256"
                ],
                "authority_builder_sha256": _read_stable_regular_file(__file__)[
                    "sha256"
                ],
            },
            "contract_hashes": {
                "support_manifest_payload_sha256": support_validation[
                    "manifest_payload_sha256"
                ],
                "config_layout_contract_sha256": support_validation[
                    "config_layout_contract_sha256"
                ],
                "support_aligned_source_contract_sha256": support_validation[
                    "support_aligned_source_contract_sha256"
                ],
                "strict_trace_schema_sha256": trace_identity[
                    "strict_trace_schema_sha256"
                ],
                "runtime_particle_graph_sha256": particle_graph[
                    "runtime_particle_graph_sha256"
                ],
            },
            "trace_contract": TRACE_SCHEMA_CONTRACT,
            "trace_identity": trace_identity,
            "frozen_runner_baseline": frozen_runner_baseline,
            "kit_log_provenance": log_snapshot["provenance"],
            "runtime_preflight": {
                **runtime_summary_validation,
                "offline_runtime_particle_graph_verified": particle_graph[
                    "verified"
                ],
                "unique_runtime_particle_authority": particle_graph["verified"],
                "enabled_particle_system_paths": particle_graph[
                    "enabled_particle_system_paths"
                ],
                "active_particle_set_paths": particle_graph[
                    "active_particle_set_paths"
                ],
                "active_sampler_paths": particle_graph["active_sampler_paths"],
            },
            "runtime_evidence_tree_sha256": runtime_tree_before["tree_sha256"],
            "runtime_evidence_tree_file_count": runtime_tree_before["file_count"],
            "runtime_evidence_snapshot_directory": RUNTIME_EVIDENCE_SNAPSHOT_DIR,
            "runtime_evidence_snapshot_tree_sha256": copied_runtime_tree[
                "tree_sha256"
            ],
            "runtime_evidence_snapshot_file_count": copied_runtime_tree[
                "file_count"
            ],
            "publish_contract": {
                "publish_mode": publish_mode,
                "cross_process_exclusive_lock": True,
                "kernel_advisory_lock": True,
                "lock_owner_verified_before_publish": (
                    lock_owner_verified_before_bundle
                ),
                "lock_owner_reverification_required_before_return": True,
                "destination_overwrite_allowed": False,
                "commit_marker": PUBLISH_COMPLETE_BASENAME,
                "missing_or_invalid_commit_marker_is_accepted": False,
                "partial_publish_is_fail_closed": True,
            },
            "bundle_artifacts": artifact_records,
            "bundle_artifact_tree_sha256": canonical_json_sha256_v1(
                artifact_records
            ),
            "claim_boundary": {
                "support_aligned_static_hold_authority": True,
                "visual_acceptance_authority": False,
                "pour_success_claim_allowed": False,
                "exact_expert_episode_claim_allowed": False,
            },
        }
        bundle["accepted_authority_bundle_sha256"] = canonical_json_sha256_v1(
            bundle
        )
        bundle_path = temp / BUNDLE_BASENAME
        _write_json(bundle_path, bundle)
        marker: dict[str, Any] = {
            "schema_version": 1,
            "manifest_type": "authority_bundle_publish_commit",
            "committed": True,
            "accepted_authority_bundle_sha256": bundle[
                "accepted_authority_bundle_sha256"
            ],
            "accepted_authority_bundle_file_sha256": _read_stable_regular_file(
                bundle_path
            )["sha256"],
            "publish_mode": publish_mode,
        }
        marker["publish_commit_sha256"] = canonical_json_sha256_v1(marker)
        _write_json(temp / PUBLISH_COMPLETE_BASENAME, marker)
        _validate_final_bundle(temp)

        log_after = snapshot_declared_kit_log(
            log_path, summary["strict_kit_log_segment"]
        )
        if log_after["provenance"] != log_snapshot["provenance"]:
            raise ValueError("kit_log_changed_during_bundle_build")
        runtime_tree_after = snapshot_regular_tree(runtime_root)
        if runtime_tree_after != runtime_tree_before:
            raise ValueError("runtime_evidence_tree_changed_during_bundle_build")
        if output.exists():
            raise ValueError(f"output_directory_already_exists:{output}")
        if not _verify_output_lock_owner(lock_descriptor, lock_path, lock_token):
            raise ValueError("output_lock_owner_verification_failed_before_publish")
        _atomic_rename_noreplace(
            temp,
            output,
            publish_mode=publish_mode,
        )
        final_bundle = _validate_final_bundle(output)
        if not _verify_output_lock_owner(lock_descriptor, lock_path, lock_token):
            raise ValueError("output_lock_owner_verification_failed_after_publish")
        return final_bundle
    finally:
        if temp.exists():
            shutil.rmtree(temp)
        lock_owned = _verify_output_lock_owner(
            lock_descriptor, lock_path, lock_token
        )
        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        os.close(lock_descriptor)
        if lock_owned:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--support-manifest", required=True)
    parser.add_argument("--runtime-summary", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--runtime-scene", required=True)
    parser.add_argument(
        "--runner",
        default=str(
            REPO_ROOT
            / "tools"
            / "labutopia_fluid"
            / "run_colleague_native_usd_completed_pbd_step_video.py"
        ),
    )
    parser.add_argument("--out-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    bundle = build_accepted_authority_bundle(
        support_manifest_path=args.support_manifest,
        runtime_summary_path=args.runtime_summary,
        trace_path=args.trace,
        runtime_scene_path=args.runtime_scene,
        runner_path=args.runner,
        out_dir=args.out_dir,
    )
    print(json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
