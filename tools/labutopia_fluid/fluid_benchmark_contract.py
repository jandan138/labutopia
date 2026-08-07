#!/usr/bin/env python3
"""Pure-data contracts shared by the LabUtopia fluid benchmarks.

This module deliberately does not import Isaac Sim, USD, Newton, or Warp.  It
can therefore be used by the parent orchestrator and by either sealed runtime
child without crossing simulator process boundaries.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


PACKET_SCHEMA = "labutopia.fluid_benchmark_packet.v2"
RESULT_SCHEMA = "labutopia.fluid_benchmark_result.v1"
EXPECTED_PARTICLE_COUNT = 3600
EXPECTED_OBSERVATION_COUNT = 953
LOGICAL_DT_S = 1.0 / 30.0
INTEGRATION_DT_S = 1.0 / 120.0
SUBSTEPS_PER_OBSERVATION = 4
NEWTON_POUR_RETARGET_OFFSET_M = (0.0187, -0.1310, 0.0)
NEWTON_POUR_RETARGET_BLEND = (500, 550)

QUALITY_GATE = {
    "minimum_target_fraction": 0.90,
    "maximum_tabletop_spill_fraction": 0.02,
    "maximum_below_table": 0,
    "maximum_nonfinite": 0,
    "stable_tail_observations": 100,
}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label}_sha256_invalid")
    return value


def _plain_finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{label}_must_be_numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label}_must_be_finite")
    return result


def _matrix44(value: Any, label: str) -> np.ndarray:
    matrix = np.asarray(value, dtype=np.float64)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError(f"{label}_matrix_invalid")
    if not np.allclose(matrix[:3, 3], 0.0, atol=1.0e-7, rtol=0.0):
        raise ValueError(f"{label}_matrix_not_row_affine")
    if not math.isclose(float(matrix[3, 3]), 1.0, abs_tol=1.0e-7):
        raise ValueError(f"{label}_matrix_not_row_affine")
    return matrix


def row_transform_points(points: Any, matrix: Any) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("points_shape_invalid")
    transform = _matrix44(matrix, "row_transform")
    homogeneous = np.concatenate(
        [values, np.ones((values.shape[0], 1), dtype=np.float64)],
        axis=1,
    )
    transformed = homogeneous @ transform
    if not np.allclose(transformed[:, 3], 1.0, atol=1.0e-6, rtol=0.0):
        raise ValueError("row_transform_homogeneous_invalid")
    return transformed[:, :3]


def retarget_source_poses(
    poses_xyzw: Any,
    *,
    offset_m: Sequence[float] = NEWTON_POUR_RETARGET_OFFSET_M,
    blend_observations: Sequence[int] = NEWTON_POUR_RETARGET_BLEND,
) -> np.ndarray:
    """Apply the declared Newton-specific controller alignment correction.

    Newton's implicit MPM transfers kinematic cup momentum differently from
    PhysX PBD.  The correction is blended in before the pour and then held; it
    preserves every recorded orientation and the 953-observation timing.
    """
    poses = np.asarray(poses_xyzw, dtype=np.float64)
    if poses.shape != (EXPECTED_OBSERVATION_COUNT, 7) or not np.isfinite(poses).all():
        raise ValueError("retarget_source_poses_invalid")
    offset = np.asarray(offset_m, dtype=np.float64)
    if offset.shape != (3,) or not np.isfinite(offset).all():
        raise ValueError("retarget_offset_invalid")
    blend = tuple(int(value) for value in blend_observations)
    if len(blend) != 2 or blend[0] < 0 or blend[1] <= blend[0]:
        raise ValueError("retarget_blend_invalid")
    start, end = blend
    if end >= EXPECTED_OBSERVATION_COUNT:
        raise ValueError("retarget_blend_out_of_range")
    weights = np.zeros(EXPECTED_OBSERVATION_COUNT, dtype=np.float64)
    weights[start : end + 1] = np.linspace(0.0, 1.0, end - start + 1)
    weights[end + 1 :] = 1.0
    result = poses.copy()
    result[:, :3] += weights[:, None] * offset[None, :]
    return result


def interpolate_pose_xyzw(
    start_pose: Any,
    end_pose: Any,
    alpha: float,
) -> np.ndarray:
    """Interpolate translation and the shortest quaternion arc in xyzw order."""
    start = np.asarray(start_pose, dtype=np.float64)
    end = np.asarray(end_pose, dtype=np.float64)
    if start.shape != (7,) or end.shape != (7,):
        raise ValueError("pose_interpolation_shape_invalid")
    if not math.isfinite(alpha) or alpha < 0.0 or alpha > 1.0:
        raise ValueError("pose_interpolation_alpha_invalid")
    result = np.empty(7, dtype=np.float64)
    result[:3] = (1.0 - alpha) * start[:3] + alpha * end[:3]
    q0 = start[3:] / np.linalg.norm(start[3:])
    q1 = end[3:] / np.linalg.norm(end[3:])
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        quaternion = q0 + alpha * (q1 - q0)
        quaternion /= np.linalg.norm(quaternion)
    else:
        angle = float(np.arccos(np.clip(dot, -1.0, 1.0)))
        sine = float(np.sin(angle))
        quaternion = (
            np.sin((1.0 - alpha) * angle) / sine * q0
            + np.sin(alpha * angle) / sine * q1
        )
    result[3:] = quaternion
    return result.astype(np.float32)


@dataclass(frozen=True)
class FluidBenchmarkPacket:
    manifest_path: Path
    arrays_path: Path
    manifest: dict[str, Any]
    arrays: Mapping[str, np.ndarray]

    @property
    def particle_count(self) -> int:
        return int(self.manifest["particle_count"])

    @property
    def observation_count(self) -> int:
        return int(self.manifest["observation_count"])

    def array(self, name: str, shape: tuple[int, ...]) -> np.ndarray:
        if name not in self.arrays:
            raise ValueError(f"packet_array_missing:{name}")
        value = np.asarray(self.arrays[name])
        if value.shape != shape or not np.isfinite(value).all():
            raise ValueError(
                f"packet_array_invalid:{name}:expected={shape}:actual={value.shape}"
            )
        return value


def load_packet(path: str | Path) -> FluidBenchmarkPacket:
    manifest_path = Path(path).resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != PACKET_SCHEMA:
        raise ValueError("packet_schema_mismatch")
    expected_content_hash = _require_sha256(
        manifest.get("content_sha256"),
        "packet_content",
    )
    content_document = dict(manifest)
    del content_document["content_sha256"]
    actual_content_hash = canonical_json_sha256(content_document)
    if actual_content_hash != expected_content_hash:
        raise ValueError(
            "packet_content_sha256_mismatch:"
            f"expected={expected_content_hash}:actual={actual_content_hash}"
        )
    if manifest.get("particle_count") != EXPECTED_PARTICLE_COUNT:
        raise ValueError("packet_particle_count_mismatch")
    if manifest.get("observation_count") != EXPECTED_OBSERVATION_COUNT:
        raise ValueError("packet_observation_count_mismatch")
    timing = manifest.get("timing")
    if not isinstance(timing, Mapping):
        raise ValueError("packet_timing_missing")
    expected_timing = {
        "logical_dt_s": LOGICAL_DT_S,
        "integration_dt_s": INTEGRATION_DT_S,
        "substeps_per_observation": SUBSTEPS_PER_OBSERVATION,
    }
    for name, expected in expected_timing.items():
        actual = timing.get(name)
        if isinstance(expected, int):
            if actual != expected:
                raise ValueError(f"packet_timing_{name}_mismatch")
        elif not math.isclose(
            _plain_finite(actual, f"packet_timing_{name}"),
            expected,
            abs_tol=1.0e-12,
        ):
            raise ValueError(f"packet_timing_{name}_mismatch")

    arrays_record = manifest.get("arrays")
    if not isinstance(arrays_record, Mapping):
        raise ValueError("packet_arrays_record_missing")
    relative_path = arrays_record.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("packet_arrays_path_invalid")
    arrays_path = (manifest_path.parent / relative_path).resolve(strict=True)
    try:
        arrays_path.relative_to(manifest_path.parent)
    except ValueError as error:
        raise ValueError("packet_arrays_path_escapes_packet_directory") from error
    expected_hash = _require_sha256(arrays_record.get("sha256"), "packet_arrays")
    actual_hash = sha256_file(arrays_path)
    if actual_hash != expected_hash:
        raise ValueError(
            "packet_arrays_sha256_mismatch:"
            f"expected={expected_hash}:actual={actual_hash}"
        )

    archive = np.load(arrays_path, allow_pickle=False)
    arrays = {name: archive[name] for name in archive.files}
    packet = FluidBenchmarkPacket(
        manifest_path=manifest_path,
        arrays_path=arrays_path,
        manifest=manifest,
        arrays=arrays,
    )
    packet.array(
        "initial_particle_positions",
        (EXPECTED_PARTICLE_COUNT, 3),
    )
    packet.array(
        "source_poses_xyzw",
        (EXPECTED_OBSERVATION_COUNT, 7),
    )
    packet.array("source_box_poses_xyzw", (int(manifest["source_box_count"]), 7))
    packet.array(
        "source_box_half_extents",
        (int(manifest["source_box_count"]), 3),
    )
    packet.array("target_box_poses_xyzw", (int(manifest["target_box_count"]), 7))
    packet.array(
        "target_box_half_extents",
        (int(manifest["target_box_count"]), 3),
    )
    packet.array("source_frame_local_matrix", (4, 4))
    packet.array("target_frame_world_matrix", (4, 4))
    _matrix44(packet.arrays["source_frame_local_matrix"], "source_frame_local")
    _matrix44(packet.arrays["target_frame_world_matrix"], "target_frame_world")
    source_poses = packet.array(
        "source_poses_xyzw",
        (EXPECTED_OBSERVATION_COUNT, 7),
    )
    quaternion_norms = np.linalg.norm(source_poses[:, 3:], axis=1)
    if not np.allclose(quaternion_norms, 1.0, atol=1.0e-5, rtol=0.0):
        raise ValueError("packet_source_pose_quaternion_invalid")

    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("packet_inputs_missing")
    file_records: list[tuple[str, Mapping[str, Any]]] = []
    for name in ("scene", "observations", "config"):
        record = inputs.get(name)
        if not isinstance(record, Mapping):
            raise ValueError(f"packet_input_record_missing:{name}")
        file_records.append((name, record))
    layer_records = inputs.get("usd_layer_closure")
    if not isinstance(layer_records, list) or not layer_records:
        raise ValueError("packet_usd_layer_closure_missing")
    for index, record in enumerate(layer_records):
        if not isinstance(record, Mapping):
            raise ValueError(f"packet_usd_layer_record_invalid:{index}")
        file_records.append((f"usd_layer_{index}", record))
    for name, record in file_records:
        input_path_value = record.get("path")
        if not isinstance(input_path_value, str) or not input_path_value:
            raise ValueError(f"packet_input_path_invalid:{name}")
        input_path = Path(input_path_value).resolve(strict=True)
        expected_input_hash = _require_sha256(
            record.get("sha256"),
            f"packet_input_{name}",
        )
        actual_input_hash = sha256_file(input_path)
        if actual_input_hash != expected_input_hash:
            raise ValueError(
                "packet_input_sha256_mismatch:"
                f"name={name}:expected={expected_input_hash}:"
                f"actual={actual_input_hash}"
            )
    return packet


def classify_positions(
    positions_world: Any,
    *,
    source_frame_world_matrix: Any,
    target_frame_world_matrix: Any,
    source_interior_radius_m: float,
    target_interior_radius_m: float,
    source_floor_m: float,
    source_rim_m: float,
    target_floor_m: float,
    target_rim_m: float,
    table_top_z_m: float,
    epsilon_m: float = 5.0e-5,
    tabletop_spill_band_m: float = 0.02,
) -> dict[str, Any]:
    positions = np.asarray(positions_world, dtype=np.float64)
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("score_positions_shape_invalid")
    source_inverse = np.linalg.inv(_matrix44(source_frame_world_matrix, "source_frame"))
    target_inverse = np.linalg.inv(_matrix44(target_frame_world_matrix, "target_frame"))
    finite_mask = np.isfinite(positions).all(axis=1)
    source_local = np.full_like(positions, np.nan)
    target_local = np.full_like(positions, np.nan)
    source_local[finite_mask] = row_transform_points(
        positions[finite_mask],
        source_inverse,
    )
    target_local[finite_mask] = row_transform_points(
        positions[finite_mask],
        target_inverse,
    )

    def inside(values: np.ndarray, radius: float, floor: float, rim: float) -> np.ndarray:
        return (
            np.hypot(values[:, 0], values[:, 1]) <= float(radius) + epsilon_m
        ) & (values[:, 2] >= float(floor) - epsilon_m) & (
            values[:, 2] < float(rim) - epsilon_m
        )

    source_mask = finite_mask & inside(
        source_local,
        source_interior_radius_m,
        source_floor_m,
        source_rim_m,
    )
    target_mask = finite_mask & ~source_mask & inside(
        target_local,
        target_interior_radius_m,
        target_floor_m,
        target_rim_m,
    )
    below_mask = (
        finite_mask
        & ~source_mask
        & ~target_mask
        & (positions[:, 2] < float(table_top_z_m) - epsilon_m)
    )
    tabletop_mask = (
        finite_mask
        & ~source_mask
        & ~target_mask
        & ~below_mask
        & (
            positions[:, 2]
            <= float(table_top_z_m) + float(tabletop_spill_band_m)
        )
    )
    transit_mask = (
        finite_mask
        & ~source_mask
        & ~target_mask
        & ~below_mask
        & ~tabletop_mask
    )
    counts = {
        "source": int(source_mask.sum()),
        "target": int(target_mask.sum()),
        "below_table": int(below_mask.sum()),
        "tabletop_spill": int(tabletop_mask.sum()),
        "transit": int(transit_mask.sum()),
        "nonfinite": int((~finite_mask).sum()),
    }
    total = int(positions.shape[0])
    counts["particle_count"] = total
    counts["partition_total"] = sum(
        counts[name]
        for name in (
            "source",
            "target",
            "below_table",
            "tabletop_spill",
            "transit",
            "nonfinite",
        )
    )
    for name in (
        "source",
        "target",
        "below_table",
        "tabletop_spill",
        "transit",
        "nonfinite",
    ):
        counts[f"{name}_fraction"] = counts[name] / total if total else 0.0
    counts["valid"] = counts["partition_total"] == total
    return counts


def evaluate_quality_gate(
    score_history: Sequence[Mapping[str, Any]],
    *,
    visual_liquid_passed: bool | None,
) -> dict[str, Any]:
    if not score_history:
        raise ValueError("score_history_empty")
    final = dict(score_history[-1])
    tail_length = int(QUALITY_GATE["stable_tail_observations"])
    tail = list(score_history[-tail_length:])
    vectors = [
        tuple(
            int(record[name])
            for name in (
                "source",
                "target",
                "below_table",
                "tabletop_spill",
                "transit",
                "nonfinite",
            )
        )
        for record in tail
    ]
    stable_tail = len(tail) == tail_length and len(set(vectors)) == 1
    checks = {
        "target_fraction": float(final["target_fraction"])
        >= float(QUALITY_GATE["minimum_target_fraction"]),
        "tabletop_spill_fraction": float(final["tabletop_spill_fraction"])
        <= float(QUALITY_GATE["maximum_tabletop_spill_fraction"]),
        "below_table": int(final["below_table"])
        <= int(QUALITY_GATE["maximum_below_table"]),
        "nonfinite": int(final["nonfinite"])
        <= int(QUALITY_GATE["maximum_nonfinite"]),
        "stable_tail": stable_tail,
        "visual_liquid": visual_liquid_passed is True,
    }
    numeric_passed = all(
        value for name, value in checks.items() if name != "visual_liquid"
    )
    return {
        "gate": dict(QUALITY_GATE),
        "checks": checks,
        "numeric_passed": numeric_passed,
        "passed": all(checks.values()),
        "visual_review_pending": visual_liquid_passed is None,
        "final_score": final,
        "stable_tail_count": len(tail),
        "stable_tail_partition_vector": list(vectors[-1]),
    }


def evaluate_stability_gate(
    score_history: Sequence[Mapping[str, Any]],
    *,
    expected_particle_count: int,
) -> dict[str, Any]:
    """Evaluate whether a run is valid for performance comparison.

    Task quality (how much liquid reaches the target and how much spills) is
    deliberately excluded.  A stable-but-leaky liquid run remains useful for
    measuring solver cost; non-finite state, particle loss, or penetration
    below the sealed tabletop does not.
    """
    if not score_history:
        raise ValueError("score_history_empty")
    if expected_particle_count < 1:
        raise ValueError("expected_particle_count_invalid")
    invalid_partition_frames: list[int] = []
    nonfinite_frames: list[int] = []
    below_table_frames: list[int] = []
    maximum_nonfinite = 0
    maximum_below_table = 0
    for fallback_index, record in enumerate(score_history):
        index = int(record.get("observation_index", fallback_index))
        partition_total = int(record.get("partition_total", -1))
        valid = bool(record.get("valid", False))
        nonfinite = int(record.get("nonfinite", -1))
        below_table = int(record.get("below_table", -1))
        if not valid or partition_total != expected_particle_count:
            invalid_partition_frames.append(index)
        if nonfinite != 0:
            nonfinite_frames.append(index)
        if below_table != 0:
            below_table_frames.append(index)
        maximum_nonfinite = max(maximum_nonfinite, nonfinite)
        maximum_below_table = max(maximum_below_table, below_table)
    checks = {
        "particle_count_conserved": not invalid_partition_frames,
        "finite_positions": not nonfinite_frames,
        "no_below_table_penetration": not below_table_frames,
    }
    return {
        "policy": (
            "hard_gate_for_performance_validity_only;target_fraction_and_"
            "tabletop_spill_fraction_are_diagnostic_not_gating"
        ),
        "checks": checks,
        "passed": all(checks.values()),
        "expected_particle_count": expected_particle_count,
        "maximum_nonfinite_count": maximum_nonfinite,
        "maximum_below_table_count": maximum_below_table,
        "invalid_partition_frames": invalid_partition_frames,
        "nonfinite_frames": nonfinite_frames,
        "below_table_frames": below_table_frames,
    }


def summarize_milliseconds(values: Sequence[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
        raise ValueError("timing_values_invalid")
    return {
        "count": int(array.size),
        "mean_ms": float(array.mean()),
        "median_ms": float(np.median(array)),
        "p95_ms": float(np.percentile(array, 95)),
        "min_ms": float(array.min()),
        "max_ms": float(array.max()),
    }


def validate_result_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if result.get("schema") != RESULT_SCHEMA:
        raise ValueError("result_schema_mismatch")
    if result.get("particle_count") != EXPECTED_PARTICLE_COUNT:
        raise ValueError("result_particle_count_mismatch")
    if result.get("observation_count") not in (
        EXPECTED_OBSERVATION_COUNT,
        result.get("requested_observation_count"),
    ):
        raise ValueError("result_observation_count_invalid")
    status = result.get("status")
    if status not in {"passed", "failed_quality", "blocked_runtime", "failed_runtime"}:
        raise ValueError("result_status_invalid")
    return result
