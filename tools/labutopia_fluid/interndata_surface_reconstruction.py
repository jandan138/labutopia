#!/usr/bin/env python3
"""Build deterministic presentation meshes from accepted InternData readback."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "interndata_kinematic_pour_probe_final_inset_20260714"
)
DEFAULT_TRACE_PATH = RUN_ROOT / "kinematic_trace.jsonl"
DEFAULT_SCENE_PATH = RUN_ROOT / "authored_scene.usda"
DEFAULT_RUNTIME_SUMMARY_PATH = RUN_ROOT / "runtime_summary.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs/interndata_surface_replay_20260714/mesh_cache"

PINNED_TRACE_SHA256 = "0321dee981f3ca82e62018352ef66ca12772f75dda35f20330ef2124b552dfb7"
PINNED_SCENE_SHA256 = "e0c020fe44536406253a9bb14a89f0d2d2b6d415abd369e780e03ef0d1db347d"
PINNED_RUNTIME_SUMMARY_SHA256 = (
    "91e2c65dfcd96841e018975d772b4c2ace081d802fc4789d28b5251d7f2a1333"
)
EXPECTED_TRACE_STEPS = 691
EXPECTED_PARTICLE_COUNT = 3600
FRAME_STRIDE = 10


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def position_sha256(positions: Sequence[Sequence[float]] | np.ndarray) -> str:
    values = [[float(value) for value in point] for point in positions]
    return _json_sha256(values)


def default_reconstruction_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "axis_order": "XYZ",
        "field_dtype": "float32",
        "vertex_dtype": "float32",
        "face_dtype": "int32",
        "lattice_anchor_world_m": [0.0, 0.0, 0.0],
        "voxel_spacing_m": 0.00135,
        "padding_voxels": 16,
        "max_axis_voxels": 256,
        "max_total_voxels": 8_000_000,
        "splat": "trilinear_trace_order_unit_mass",
        "gaussian_sigma_voxels": 1.60,
        "gaussian_truncate": 4.0,
        "gaussian_mode": "constant",
        "gaussian_cval": 0.0,
        "density_gap_closing": "ellipsoidal_grey_closing_gravity_z",
        "density_gap_closing_radii_voxels": [3, 3, 8],
        "density_gap_closing_mode": "constant",
        "density_gap_closing_cval": 0.0,
        "iso_level": 0.02,
        "marching_cubes_method": "lewiner",
        "marching_cubes_step_size": 1,
        "gradient_direction": "descent",
        "allow_degenerate": False,
        "component_filter": "none",
        "float32_topology_cleanup": "exact_adjacent_edge_contraction",
        "float32_topology_max_component_volume_drift_fraction": 1.0e-5,
        "mesh_smoothing": "guarded_uniform_taubin",
        "mesh_smoothing_cycles": 10,
        "mesh_smoothing_lambda": 0.50,
        "mesh_smoothing_mu": -0.53,
        "mesh_smoothing_min_component_volume_m3": 1.0e-7,
        "mesh_smoothing_max_component_volume_drift_fraction": 0.01,
        "mesh_smoothing_max_total_volume_drift_fraction": 0.001,
        "mesh_smoothing_max_vertex_displacement_m": 0.001,
        "mesh_smoothing_max_outward_aabb_growth_m": 0.000125,
        "mesh_smoothing_guard_bisection_iterations": 24,
    }


def reconstruction_contract_sha256(contract: Mapping[str, Any]) -> str:
    return _json_sha256(dict(contract))


def validate_pinned_inputs(
    *,
    trace_path: str | Path = DEFAULT_TRACE_PATH,
    scene_path: str | Path = DEFAULT_SCENE_PATH,
    runtime_summary_path: str | Path = DEFAULT_RUNTIME_SUMMARY_PATH,
) -> dict[str, dict[str, Any]]:
    specs = {
        "trace": (Path(trace_path).resolve(strict=True), PINNED_TRACE_SHA256),
        "scene": (Path(scene_path).resolve(strict=True), PINNED_SCENE_SHA256),
        "runtime_summary": (
            Path(runtime_summary_path).resolve(strict=True),
            PINNED_RUNTIME_SUMMARY_SHA256,
        ),
    }
    result: dict[str, dict[str, Any]] = {}
    for name, (path, expected) in specs.items():
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError(f"pinned_{name}_sha256_invalid")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"pinned_{name}_sha256_mismatch:expected={expected}:actual={actual}"
            )
        result[name] = {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": actual,
            "expected_sha256": expected,
            "matches_pin": True,
        }
    return result


def _require_plain_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}_must_be_numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label}_must_be_finite")
    return result


def _validate_positions(
    value: Any,
    *,
    expected_particle_count: int,
    step_index: int,
) -> np.ndarray:
    if not isinstance(value, list) or len(value) != expected_particle_count:
        raise ValueError(
            f"positions_count_mismatch:step={step_index}:"
            f"expected={expected_particle_count}:actual="
            f"{len(value) if isinstance(value, list) else 'non_list'}"
        )
    converted = np.empty((expected_particle_count, 3), dtype=np.float64)
    for point_index, point in enumerate(value):
        if not isinstance(point, (list, tuple)) or len(point) != 3:
            raise ValueError(
                f"positions_ragged:step={step_index}:point={point_index}"
            )
        for axis, item in enumerate(point):
            converted[point_index, axis] = _require_plain_number(
                item,
                f"positions_step_{step_index}_point_{point_index}_axis_{axis}",
            )
    return converted


def _validate_source_parent_matrix(value: Any, *, step_index: int) -> list[list[float]]:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(not isinstance(row, list) or len(row) != 4 for row in value)
    ):
        raise ValueError(f"source_parent_matrix_shape_invalid:step={step_index}")
    matrix = np.asarray(
        [
            [
                _require_plain_number(item, f"source_parent_matrix_step_{step_index}")
                for item in row
            ]
            for row in value
        ],
        dtype=np.float64,
    )
    if not np.allclose(matrix[:3, 3], 0.0, atol=1e-6, rtol=0.0) or not np.allclose(
        matrix[3, 3], 1.0, atol=1e-6, rtol=0.0
    ):
        raise ValueError(f"source_parent_matrix_affine_invalid:step={step_index}")
    rotation = matrix[:3, :3]
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-4, rtol=0.0):
        raise ValueError(f"source_parent_matrix_rotation_invalid:step={step_index}")
    if not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-4):
        raise ValueError(f"source_parent_matrix_determinant_invalid:step={step_index}")
    return matrix.tolist()


def _require_count(counts: Mapping[str, Any], name: str, step_index: int) -> int:
    value = counts.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"counts_{name}_invalid:step={step_index}")
    return int(value)


def _validate_counts(
    value: Any,
    *,
    expected_particle_count: int,
    step_index: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"counts_missing:step={step_index}")
    counts = dict(value)
    particle_count = _require_count(counts, "particle_count", step_index)
    finite_total = _require_count(counts, "finite_partition_total", step_index)
    nonfinite = _require_count(counts, "nonfinite", step_index)
    finite_parts = sum(
        _require_count(counts, name, step_index)
        for name in ("source", "target", "transit", "tabletop_spill", "below_table")
    )
    if particle_count != expected_particle_count:
        raise ValueError(f"counts_particle_count_mismatch:step={step_index}")
    if finite_total != finite_parts or finite_total + nonfinite != particle_count:
        raise ValueError(f"counts_partition_mismatch:step={step_index}")
    if counts.get("partition_complete") is not True or counts.get("valid") is not True:
        raise ValueError(f"counts_partition_invalid:step={step_index}")
    return counts


def load_selected_trace_records(
    trace_path: str | Path,
    *,
    expected_step_count: int = EXPECTED_TRACE_STEPS,
    expected_particle_count: int = EXPECTED_PARTICLE_COUNT,
    frame_stride: int = FRAME_STRIDE,
    contract: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if expected_step_count <= 0:
        raise ValueError("expected_step_count_must_be_positive")
    if expected_particle_count <= 0:
        raise ValueError("expected_particle_count_must_be_positive")
    if frame_stride <= 0:
        raise ValueError("frame_stride_must_be_positive")
    selected: list[dict[str, Any]] = []
    path = Path(trace_path).resolve(strict=True)
    line_count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                raise ValueError(f"blank_trace_line:{line_number}")
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_trace_json:{line_number}:{exc.msg}") from exc
            if not isinstance(record, Mapping):
                raise ValueError(f"trace_record_must_be_object:{line_number}")
            expected_step = line_count
            step = record.get("step_index")
            if isinstance(step, bool) or not isinstance(step, int) or step != expected_step:
                raise ValueError(
                    f"trace_step_invalid:line={line_number}:"
                    f"expected={expected_step}:actual={step}"
                )
            particle_count = record.get("particle_count")
            if (
                isinstance(particle_count, bool)
                or not isinstance(particle_count, int)
                or particle_count != expected_particle_count
            ):
                raise ValueError(f"particle_count_mismatch:step={step}")
            positions = _validate_positions(
                record.get("positions"),
                expected_particle_count=expected_particle_count,
                step_index=step,
            )
            expected_position_hash = record.get("position_sha256")
            actual_position_hash = position_sha256(positions)
            if expected_position_hash != actual_position_hash:
                raise ValueError(
                    f"position_sha256_mismatch:step={step}:"
                    f"expected={expected_position_hash}:actual={actual_position_hash}"
                )
            matrix = _validate_source_parent_matrix(
                record.get("source_parent_matrix"), step_index=step
            )
            counts = _validate_counts(
                record.get("counts"),
                expected_particle_count=expected_particle_count,
                step_index=step,
            )
            if step % frame_stride == 0:
                selected_record = {
                    "step_index": step,
                    "phase": str(record.get("phase", "unknown")),
                    "particle_count": particle_count,
                    "position_sha256": actual_position_hash,
                    "source_parent_matrix": matrix,
                    "counts": counts,
                    "positions": positions,
                }
                if contract is not None:
                    compute_lattice_spec(positions, contract)
                selected.append(selected_record)
            line_count += 1
    if line_count != expected_step_count:
        raise ValueError(
            f"trace_record_count_mismatch:expected={expected_step_count}:actual={line_count}"
        )
    expected_steps = list(range(0, expected_step_count, frame_stride))
    if [record["step_index"] for record in selected] != expected_steps:
        raise ValueError("selected_trace_steps_mismatch")
    return selected


def compute_lattice_spec(
    positions: Sequence[Sequence[float]] | np.ndarray,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    values = np.asarray(positions, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3 or values.shape[0] == 0:
        raise ValueError("lattice_positions_shape_invalid")
    if not np.isfinite(values).all():
        raise ValueError("lattice_positions_nonfinite")
    cfg = dict(default_reconstruction_contract() if contract is None else contract)
    spacing = float(cfg["voxel_spacing_m"])
    padding = int(cfg["padding_voxels"])
    anchor = np.asarray(cfg["lattice_anchor_world_m"], dtype=np.float64)
    lower_index = np.floor((values.min(axis=0) - anchor) / spacing).astype(np.int64)
    upper_index = np.ceil((values.max(axis=0) - anchor) / spacing).astype(np.int64)
    lower_index -= padding
    upper_index += padding
    shape = upper_index - lower_index + 1
    if np.any(shape > int(cfg["max_axis_voxels"])):
        raise ValueError(f"lattice_axis_limit_exceeded:{shape.tolist()}")
    total_voxels = int(np.prod(shape, dtype=np.int64))
    if total_voxels > int(cfg["max_total_voxels"]):
        raise ValueError(f"lattice_total_limit_exceeded:{total_voxels}")
    origin = anchor + lower_index.astype(np.float64) * spacing
    maximum = anchor + upper_index.astype(np.float64) * spacing
    return {
        "axis_order": "XYZ",
        "origin_world_m": origin.tolist(),
        "maximum_world_m": maximum.tolist(),
        "lower_lattice_index": lower_index.tolist(),
        "upper_lattice_index": upper_index.tolist(),
        "shape": shape.astype(int).tolist(),
        "total_voxels": total_voxels,
        "voxel_spacing_m": spacing,
    }


def _splat_density_field(
    positions: np.ndarray,
    lattice: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> np.ndarray:
    origin = np.asarray(lattice["origin_world_m"], dtype=np.float64)
    spacing = float(contract["voxel_spacing_m"])
    coordinates = (positions - origin) / spacing
    base = np.floor(coordinates).astype(np.int64)
    fraction = coordinates - base.astype(np.float64)
    field = np.zeros(tuple(lattice["shape"]), dtype=np.float32)
    for ox in (0, 1):
        wx = fraction[:, 0] if ox else 1.0 - fraction[:, 0]
        for oy in (0, 1):
            wy = fraction[:, 1] if oy else 1.0 - fraction[:, 1]
            for oz in (0, 1):
                wz = fraction[:, 2] if oz else 1.0 - fraction[:, 2]
                indices = base + np.asarray([ox, oy, oz], dtype=np.int64)
                if np.any(indices < 0) or np.any(indices >= np.asarray(field.shape)):
                    raise ValueError("particle_splat_outside_lattice")
                weights = (wx * wy * wz).astype(np.float32)
                np.add.at(
                    field,
                    (indices[:, 0], indices[:, 1], indices[:, 2]),
                    weights,
                )
    return field


def build_density_gap_closing_footprint(
    contract: Mapping[str, Any],
) -> np.ndarray:
    radii = np.asarray(contract["density_gap_closing_radii_voxels"], dtype=np.int64)
    if radii.shape != (3,) or np.any(radii <= 0):
        raise ValueError("density_gap_closing_radii_invalid")
    axes = np.ogrid[
        tuple(slice(-int(radius), int(radius) + 1) for radius in radii)
    ]
    normalized_squared = sum(
        (axis.astype(np.float64) / float(radius)) ** 2
        for axis, radius in zip(axes, radii, strict=True)
    )
    return np.asarray(normalized_squared <= 1.0, dtype=np.bool_)


def _positive_support_bounds(values: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    occupied = np.argwhere(values > 0.0)
    if len(occupied) == 0:
        return None
    return occupied.min(axis=0), occupied.max(axis=0)


def apply_density_gap_closing(
    density: np.ndarray,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    values = np.ascontiguousarray(density, dtype=np.float32)
    if values.ndim != 3 or not np.isfinite(values).all():
        raise ValueError("density_gap_closing_field_invalid")
    method = str(contract["density_gap_closing"])
    before_bounds = _positive_support_bounds(values)
    if method == "none":
        return {
            "density": values.copy(),
            "diagnostics": {
                "method": method,
                "applied": False,
                "support_bounds_expanded": False,
            },
        }
    if method != "ellipsoidal_grey_closing_gravity_z":
        raise ValueError(f"density_gap_closing_method_invalid:{method}")

    from scipy.ndimage import grey_closing

    footprint = build_density_gap_closing_footprint(contract)
    closed = grey_closing(
        values,
        footprint=footprint,
        mode=str(contract["density_gap_closing_mode"]),
        cval=float(contract["density_gap_closing_cval"]),
        output=np.float32,
    )
    closed = np.ascontiguousarray(closed, dtype=np.float32)
    if not np.isfinite(closed).all():
        raise ValueError("density_gap_closing_created_nonfinite_values")
    after_bounds = _positive_support_bounds(closed)
    support_bounds_expanded = False
    if before_bounds is None:
        support_bounds_expanded = after_bounds is not None
    elif after_bounds is not None:
        support_bounds_expanded = bool(
            np.any(after_bounds[0] < before_bounds[0])
            or np.any(after_bounds[1] > before_bounds[1])
        )
    if support_bounds_expanded:
        raise ValueError("density_gap_closing_expanded_support_bounds")
    return {
        "density": closed,
        "diagnostics": {
            "method": method,
            "applied": True,
            "radii_voxels_xyz": [
                int(value)
                for value in contract["density_gap_closing_radii_voxels"]
            ],
            "footprint_shape": [int(value) for value in footprint.shape],
            "footprint_voxel_count": int(np.count_nonzero(footprint)),
            "mode": str(contract["density_gap_closing_mode"]),
            "cval": float(contract["density_gap_closing_cval"]),
            "support_bounds_before": (
                None
                if before_bounds is None
                else [before_bounds[0].astype(int).tolist(), before_bounds[1].astype(int).tolist()]
            ),
            "support_bounds_after": (
                None
                if after_bounds is None
                else [after_bounds[0].astype(int).tolist(), after_bounds[1].astype(int).tolist()]
            ),
            "support_bounds_expanded": support_bounds_expanded,
            "max_density_before": float(np.max(values)),
            "max_density_after": float(np.max(closed)),
        },
    }


def _canonical_array(array: np.ndarray, dtype: str) -> np.ndarray:
    target = np.dtype(dtype).newbyteorder("<")
    return np.ascontiguousarray(np.asarray(array, dtype=target))


def canonical_mesh_sha256(
    vertices: np.ndarray,
    faces: np.ndarray,
    normals: np.ndarray,
) -> str:
    digest = hashlib.sha256()
    arrays = (
        ("vertices", _canonical_array(vertices, "<f4")),
        ("faces", _canonical_array(faces, "<i4")),
        ("normals", _canonical_array(normals, "<f4")),
    )
    for name, array in arrays:
        digest.update(name.encode("ascii") + b"\0")
        digest.update(array.dtype.str.encode("ascii") + b"\0")
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
        digest.update(b"\0")
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _edge_diagnostics(faces: np.ndarray) -> tuple[int, int, int]:
    directed = np.concatenate(
        [faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=0
    )
    undirected = np.sort(directed, axis=1)
    unique, inverse, counts = np.unique(
        undirected, axis=0, return_inverse=True, return_counts=True
    )
    del unique
    direction = np.where(directed[:, 0] < directed[:, 1], 1, -1)
    direction_sum = np.zeros(len(counts), dtype=np.int64)
    np.add.at(direction_sum, inverse, direction)
    boundary = int(np.count_nonzero(counts == 1))
    nonmanifold = int(np.count_nonzero(counts > 2))
    inconsistent = int(np.count_nonzero((counts == 2) & (direction_sum != 0)))
    return boundary, nonmanifold, inconsistent


def _vertex_components(vertex_count: int, faces: np.ndarray) -> tuple[int, np.ndarray]:
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    edges = np.concatenate(
        [faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=0
    )
    rows = np.concatenate([edges[:, 0], edges[:, 1]])
    columns = np.concatenate([edges[:, 1], edges[:, 0]])
    graph = coo_matrix(
        (np.ones(len(rows), dtype=np.uint8), (rows, columns)),
        shape=(vertex_count, vertex_count),
    )
    return connected_components(graph, directed=False, return_labels=True)


def _signed_component_volume(
    vertices: np.ndarray,
    faces: np.ndarray,
    face_mask: np.ndarray,
) -> float:
    selected = faces[face_mask]
    used = np.unique(selected)
    center = vertices[used].astype(np.float64).mean(axis=0)
    v0 = vertices[selected[:, 0]].astype(np.float64) - center
    v1 = vertices[selected[:, 1]].astype(np.float64) - center
    v2 = vertices[selected[:, 2]].astype(np.float64) - center
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def _indexed_mesh_sha256(vertices: np.ndarray, faces: np.ndarray) -> str:
    digest = hashlib.sha256()
    for name, array in (
        ("vertices", np.ascontiguousarray(vertices)),
        ("faces", np.ascontiguousarray(faces)),
    ):
        digest.update(name.encode("ascii") + b"\0")
        digest.update(array.dtype.str.encode("ascii") + b"\0")
        digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
        digest.update(b"\0")
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _duplicate_unordered_face_count(faces: np.ndarray) -> int:
    canonical = np.sort(np.asarray(faces, dtype=np.int64), axis=1)
    return int(len(canonical) - len(np.unique(canonical, axis=0)))


def _component_euler_characteristics(
    faces: np.ndarray,
    vertex_labels: np.ndarray,
    component_count: int,
) -> list[int]:
    result: list[int] = []
    for label in range(component_count):
        mask = vertex_labels[faces[:, 0]] == label
        selected = faces[mask]
        if len(selected) == 0 or not np.all(vertex_labels[selected] == label):
            raise ValueError("mesh_component_face_assignment_invalid")
        vertex_count = len(np.unique(selected))
        edges = np.concatenate(
            [selected[:, [0, 1]], selected[:, [1, 2]], selected[:, [2, 0]]],
            axis=0,
        )
        edge_count = len(np.unique(np.sort(edges, axis=1), axis=0))
        result.append(int(vertex_count - edge_count + len(selected)))
    return result


def cleanup_float32_quantized_mesh(
    vertices_world_float64: np.ndarray,
    faces: np.ndarray,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    method = str(contract["float32_topology_cleanup"])
    if method != "exact_adjacent_edge_contraction":
        raise ValueError(f"float32_topology_cleanup_method_invalid:{method}")
    vertices64 = np.ascontiguousarray(vertices_world_float64, dtype=np.float64)
    source_faces = np.ascontiguousarray(faces, dtype=np.int32)
    if vertices64.ndim != 2 or vertices64.shape[1] != 3 or len(vertices64) == 0:
        raise ValueError("float32_cleanup_vertices_shape_invalid")
    if source_faces.ndim != 2 or source_faces.shape[1] != 3 or len(source_faces) == 0:
        raise ValueError("float32_cleanup_faces_shape_invalid")
    if not np.isfinite(vertices64).all():
        raise ValueError("float32_cleanup_vertices_nonfinite")
    if np.any(source_faces < 0) or np.any(source_faces >= len(vertices64)):
        raise ValueError("float32_cleanup_face_index_invalid")
    source_repeated_corner = (
        (source_faces[:, 0] == source_faces[:, 1])
        | (source_faces[:, 1] == source_faces[:, 2])
        | (source_faces[:, 2] == source_faces[:, 0])
    )
    source_cross = np.cross(
        vertices64[source_faces[:, 1]] - vertices64[source_faces[:, 0]],
        vertices64[source_faces[:, 2]] - vertices64[source_faces[:, 0]],
    )
    source_degenerate = source_repeated_corner | (
        np.linalg.norm(source_cross, axis=1) <= 0.0
    )
    if np.any(source_degenerate):
        raise ValueError("float32_cleanup_float64_mesh_degenerate")
    source_edges = _edge_diagnostics(source_faces)
    if any(source_edges):
        raise ValueError(f"float32_cleanup_source_mesh_not_closed:{source_edges}")
    if _duplicate_unordered_face_count(source_faces):
        raise ValueError("float32_cleanup_duplicate_source_faces")

    component_count_before, labels_before = _vertex_components(
        len(vertices64), source_faces
    )
    euler_before = _component_euler_characteristics(
        source_faces, labels_before, component_count_before
    )
    face_labels_before = labels_before[source_faces[:, 0]]
    volumes_before = np.asarray(
        [
            abs(
                _signed_component_volume(
                    vertices64,
                    source_faces,
                    face_labels_before == label,
                )
            )
            for label in range(component_count_before)
        ],
        dtype=np.float64,
    )
    if np.any(volumes_before <= 1.0e-15):
        raise ValueError("float32_cleanup_source_component_volume_invalid")

    quantized = vertices64.astype(np.float32)
    quantized[quantized == 0.0] = np.float32(0.0)
    if not np.isfinite(quantized).all():
        raise ValueError("float32_cleanup_quantized_vertices_nonfinite")
    quantized_cross = np.cross(
        quantized[source_faces[:, 1]].astype(np.float64)
        - quantized[source_faces[:, 0]].astype(np.float64),
        quantized[source_faces[:, 2]].astype(np.float64)
        - quantized[source_faces[:, 0]].astype(np.float64),
    )
    quantized_degenerate = source_repeated_corner | (
        np.linalg.norm(quantized_cross, axis=1) <= 0.0
    )
    quantized_volumes_before = np.asarray(
        [
            abs(
                _signed_component_volume(
                    quantized,
                    source_faces,
                    face_labels_before == label,
                )
            )
            for label in range(component_count_before)
        ],
        dtype=np.float64,
    )
    float64_to_float32_volume_drifts = (
        np.abs(quantized_volumes_before - volumes_before) / volumes_before
    ).tolist()

    _unique, inverse, counts = np.unique(
        quantized,
        axis=0,
        return_inverse=True,
        return_counts=True,
    )
    duplicate_group_ids = np.flatnonzero(counts > 1)
    remap = np.arange(len(quantized), dtype=np.int64)
    weld_pairs: list[list[int]] = []
    expected_collapsed_faces: set[int] = set()
    for group_id in duplicate_group_ids:
        members = np.flatnonzero(inverse == group_id)
        if len(members) != 2:
            raise ValueError("float32_cleanup_duplicate_group_size_invalid")
        keep, remove = (int(members[0]), int(members[1]))
        if labels_before[keep] != labels_before[remove]:
            raise ValueError("float32_cleanup_cross_component_weld")
        incident_mask = np.any(source_faces == keep, axis=1) & np.any(
            source_faces == remove, axis=1
        )
        incident = np.flatnonzero(incident_mask)
        if len(incident) != 2:
            raise ValueError("float32_cleanup_duplicate_vertices_not_manifold_edge")
        keep_neighbors = set(source_faces[np.any(source_faces == keep, axis=1)].flat)
        remove_neighbors = set(source_faces[np.any(source_faces == remove, axis=1)].flat)
        keep_neighbors.discard(keep)
        remove_neighbors.discard(remove)
        common_neighbors = keep_neighbors & remove_neighbors
        opposite_vertices = set(source_faces[incident].flat) - {keep, remove}
        if len(opposite_vertices) != 2 or common_neighbors != opposite_vertices:
            raise ValueError("float32_cleanup_edge_link_condition_failed")
        remap[remove] = keep
        weld_pairs.append([keep, remove])
        expected_collapsed_faces.update(int(value) for value in incident)

    remapped_faces = remap[source_faces]
    collapsed = (
        (remapped_faces[:, 0] == remapped_faces[:, 1])
        | (remapped_faces[:, 1] == remapped_faces[:, 2])
        | (remapped_faces[:, 2] == remapped_faces[:, 0])
    )
    collapsed_indices = np.flatnonzero(collapsed)
    if set(int(value) for value in collapsed_indices) != expected_collapsed_faces:
        raise ValueError("float32_cleanup_unexpected_collapsed_faces")
    distinct_corner_zero_area = quantized_degenerate & ~collapsed
    if np.any(distinct_corner_zero_area):
        raise ValueError("float32_cleanup_distinct_corner_zero_area_face")

    retained_faces = remapped_faces[~collapsed]
    if _duplicate_unordered_face_count(retained_faces):
        raise ValueError("float32_cleanup_duplicate_faces_after_weld")
    used_vertices = np.unique(retained_faces)
    compact_remap = np.full(len(quantized), -1, dtype=np.int64)
    compact_remap[used_vertices] = np.arange(len(used_vertices), dtype=np.int64)
    cleaned_vertices = np.ascontiguousarray(quantized[used_vertices], dtype=np.float32)
    cleaned_faces = np.ascontiguousarray(
        compact_remap[retained_faces], dtype=np.int32
    )
    if len(np.unique(cleaned_vertices, axis=0)) != len(cleaned_vertices):
        raise ValueError("float32_cleanup_duplicate_vertices_remain")
    cleaned_cross = np.cross(
        cleaned_vertices[cleaned_faces[:, 1]].astype(np.float64)
        - cleaned_vertices[cleaned_faces[:, 0]].astype(np.float64),
        cleaned_vertices[cleaned_faces[:, 2]].astype(np.float64)
        - cleaned_vertices[cleaned_faces[:, 0]].astype(np.float64),
    )
    if np.any(np.linalg.norm(cleaned_cross, axis=1) <= 0.0):
        raise ValueError("float32_cleanup_degenerate_faces_remain")
    cleaned_edges = _edge_diagnostics(cleaned_faces)
    if any(cleaned_edges):
        raise ValueError(f"float32_cleanup_result_not_closed:{cleaned_edges}")

    component_count_after, labels_after = _vertex_components(
        len(cleaned_vertices), cleaned_faces
    )
    if component_count_after != component_count_before:
        raise ValueError("float32_cleanup_component_count_changed")
    euler_after = _component_euler_characteristics(
        cleaned_faces, labels_after, component_count_after
    )
    if sorted(euler_after) != sorted(euler_before):
        raise ValueError("float32_cleanup_component_euler_changed")
    face_labels_after = labels_after[cleaned_faces[:, 0]]
    if np.any(quantized_volumes_before <= 1.0e-15):
        raise ValueError("float32_cleanup_quantized_component_volume_invalid")
    volume_drifts: list[float] = []
    mapped_source_labels: set[int] = set()
    for label in range(component_count_after):
        source_labels = np.unique(labels_before[used_vertices[labels_after == label]])
        if len(source_labels) != 1:
            raise ValueError("float32_cleanup_component_mapping_invalid")
        source_label = int(source_labels[0])
        mapped_source_labels.add(source_label)
        after_volume = abs(
            _signed_component_volume(
                cleaned_vertices,
                cleaned_faces,
                face_labels_after == label,
            )
        )
        if after_volume <= 1.0e-15:
            raise ValueError("float32_cleanup_result_component_volume_invalid")
        volume_drifts.append(
            abs(after_volume - quantized_volumes_before[source_label])
            / quantized_volumes_before[source_label]
        )
    if len(mapped_source_labels) != component_count_before:
        raise ValueError("float32_cleanup_component_removed")
    maximum_volume_drift = max(volume_drifts, default=0.0)
    if maximum_volume_drift > float(
        contract["float32_topology_max_component_volume_drift_fraction"]
    ):
        raise ValueError("float32_cleanup_component_volume_drift_exceeded")
    aabb_unchanged = bool(
        np.array_equal(quantized.min(axis=0), cleaned_vertices.min(axis=0))
        and np.array_equal(quantized.max(axis=0), cleaned_vertices.max(axis=0))
    )
    if not aabb_unchanged:
        raise ValueError("float32_cleanup_aabb_changed")

    diagnostics = {
        "method": method,
        "applied": bool(weld_pairs),
        "input_vertex_count": int(len(quantized)),
        "output_vertex_count": int(len(cleaned_vertices)),
        "input_face_count": int(len(source_faces)),
        "output_face_count": int(len(cleaned_faces)),
        "duplicate_coordinate_group_count": int(len(duplicate_group_ids)),
        "welded_vertex_count": int(len(quantized) - len(cleaned_vertices)),
        "weld_pairs_original_indices": weld_pairs,
        "float64_degenerate_face_count": 0,
        "float32_degenerate_face_count_before": int(
            np.count_nonzero(quantized_degenerate)
        ),
        "float32_degenerate_face_count_after": 0,
        "collapsed_face_count": int(len(collapsed_indices)),
        "collapsed_face_indices": [int(value) for value in collapsed_indices],
        "removed_float32_nonzero_area_face_count": 0,
        "component_count_before": int(component_count_before),
        "component_count_after": int(component_count_after),
        "component_removal_count": int(
            component_count_before - component_count_after
        ),
        "component_euler_characteristics_before": euler_before,
        "component_euler_characteristics_after": euler_after,
        "component_volume_drift_fractions": volume_drifts,
        "max_component_volume_drift_fraction": maximum_volume_drift,
        "float64_to_float32_component_volume_drift_fractions": (
            float64_to_float32_volume_drifts
        ),
        "aabb_unchanged": aabb_unchanged,
        "vertex_displacement_m": 0.0,
        "boundary_edge_count_after": int(cleaned_edges[0]),
        "nonmanifold_edge_count_after": int(cleaned_edges[1]),
        "inconsistent_winding_edge_count_after": int(cleaned_edges[2]),
        "quantized_input_topology_sha256": _indexed_mesh_sha256(
            quantized, source_faces
        ),
        "cleaned_topology_sha256": _indexed_mesh_sha256(
            cleaned_vertices, cleaned_faces
        ),
    }
    return {
        "vertices": cleaned_vertices,
        "faces": cleaned_faces,
        "diagnostics": diagnostics,
    }


def _orient_faces_outward(
    vertices: np.ndarray, faces: np.ndarray
) -> tuple[np.ndarray, list[float], int]:
    component_count, vertex_labels = _vertex_components(len(vertices), faces)
    face_labels = vertex_labels[faces[:, 0]]
    oriented = faces.copy()
    flipped = 0
    volumes: list[float] = []
    for label in range(component_count):
        mask = face_labels == label
        if not np.any(mask):
            continue
        volume = _signed_component_volume(vertices, oriented, mask)
        if volume < 0.0:
            selected = oriented[mask].copy()
            selected[:, [1, 2]] = selected[:, [2, 1]]
            oriented[mask] = selected
            flipped += 1
            volume = -volume
        volumes.append(volume)
    return oriented, volumes, flipped


def _compute_vertex_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    v0 = vertices[faces[:, 0]].astype(np.float64)
    v1 = vertices[faces[:, 1]].astype(np.float64)
    v2 = vertices[faces[:, 2]].astype(np.float64)
    face_normals = np.cross(v1 - v0, v2 - v0)
    normals = np.zeros((len(vertices), 3), dtype=np.float64)
    for corner in range(3):
        np.add.at(normals, faces[:, corner], face_normals)
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(lengths <= 1e-15):
        raise ValueError("surface_zero_vertex_normal")
    normals /= lengths[:, None]
    return normals.astype(np.float32)


def apply_guarded_taubin_smoothing(
    vertices: np.ndarray,
    faces: np.ndarray,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    source_vertices = np.ascontiguousarray(vertices, dtype=np.float32)
    source_faces = np.ascontiguousarray(faces, dtype=np.int32)
    cycles = int(contract["mesh_smoothing_cycles"])
    component_count, vertex_labels = _vertex_components(
        len(source_vertices), source_faces
    )
    face_labels = vertex_labels[source_faces[:, 0]]
    before_volumes = np.asarray(
        [
            abs(
                _signed_component_volume(
                    source_vertices,
                    source_faces,
                    face_labels == label,
                )
            )
            for label in range(component_count)
        ],
        dtype=np.float64,
    )
    minimum_volume = float(contract["mesh_smoothing_min_component_volume_m3"])
    eligible_components = before_volumes >= minimum_volume
    eligible_vertices = eligible_components[vertex_labels]
    working = source_vertices.astype(np.float64)
    edges = np.concatenate(
        [
            source_faces[:, [0, 1]],
            source_faces[:, [1, 2]],
            source_faces[:, [2, 0]],
        ],
        axis=0,
    )
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    degrees = np.zeros(len(working), dtype=np.int64)
    np.add.at(degrees, edges[:, 0], 1)
    np.add.at(degrees, edges[:, 1], 1)
    if np.any(degrees <= 0):
        raise ValueError("mesh_smoothing_isolated_vertex")

    def jacobi_pass(values: np.ndarray, factor: float) -> np.ndarray:
        neighbor_sum = np.zeros_like(values)
        np.add.at(neighbor_sum, edges[:, 0], values[edges[:, 1]])
        np.add.at(neighbor_sum, edges[:, 1], values[edges[:, 0]])
        candidate = values + factor * (
            neighbor_sum / degrees[:, None] - values
        )
        result = values.copy()
        result[eligible_vertices] = candidate[eligible_vertices]
        return result

    for _ in range(cycles):
        working = jacobi_pass(working, float(contract["mesh_smoothing_lambda"]))
        working = jacobi_pass(working, float(contract["mesh_smoothing_mu"]))

    eligible_before = before_volumes[eligible_components]
    source_float64 = source_vertices.astype(np.float64)
    proposed_float64 = working
    before_min = source_vertices.min(axis=0).astype(np.float64)
    before_max = source_vertices.max(axis=0).astype(np.float64)

    def evaluate_blend(scale: float) -> dict[str, Any]:
        blended = source_float64.copy()
        blended[eligible_vertices] += scale * (
            proposed_float64[eligible_vertices] - source_float64[eligible_vertices]
        )
        candidate_vertices = blended.astype(np.float32)
        candidate_vertices[~eligible_vertices] = source_vertices[~eligible_vertices]
        candidate_volumes = np.asarray(
            [
                abs(
                    _signed_component_volume(
                        candidate_vertices,
                        source_faces,
                        face_labels == label,
                    )
                )
                for label in range(component_count)
            ],
            dtype=np.float64,
        )
        eligible_after = candidate_volumes[eligible_components]
        if len(eligible_before):
            component_drift = np.abs(eligible_after - eligible_before) / eligible_before
            maximum_component_drift = float(np.max(component_drift))
            total_before = float(np.sum(eligible_before))
            total_after = float(np.sum(eligible_after))
            total_drift = abs(total_after - total_before) / total_before
        else:
            maximum_component_drift = 0.0
            total_drift = 0.0
        displacement = np.linalg.norm(
            candidate_vertices.astype(np.float64) - source_float64,
            axis=1,
        )
        after_min = candidate_vertices.min(axis=0).astype(np.float64)
        after_max = candidate_vertices.max(axis=0).astype(np.float64)
        outward_growth = float(
            max(
                0.0,
                float(np.max(before_min - after_min)),
                float(np.max(after_max - before_max)),
            )
        )
        maximum_displacement = float(np.max(displacement))
        gates = {
            "max_component_volume_drift_fraction": (
                maximum_component_drift
                <= float(
                    contract["mesh_smoothing_max_component_volume_drift_fraction"]
                )
            ),
            "total_volume_drift_fraction": (
                total_drift
                <= float(contract["mesh_smoothing_max_total_volume_drift_fraction"])
            ),
            "max_vertex_displacement_m": (
                maximum_displacement
                <= float(contract["mesh_smoothing_max_vertex_displacement_m"])
            ),
            "max_outward_aabb_growth_m": (
                outward_growth
                <= float(contract["mesh_smoothing_max_outward_aabb_growth_m"])
            ),
        }
        return {
            "vertices": candidate_vertices,
            "component_volumes": candidate_volumes,
            "max_component_volume_drift_fraction": maximum_component_drift,
            "total_volume_drift_fraction": total_drift,
            "max_vertex_displacement_m": maximum_displacement,
            "max_outward_aabb_growth_m": outward_growth,
            "gates": gates,
        }

    proposed = evaluate_blend(1.0)
    selected = proposed
    blend_scale = 1.0
    bisection_count = 0
    if not all(proposed["gates"].values()):
        selected = evaluate_blend(0.0)
        if not all(selected["gates"].values()):
            raise RuntimeError("mesh_smoothing_zero_blend_failed_guards")
        lower = 0.0
        upper = 1.0
        bisection_count = int(contract["mesh_smoothing_guard_bisection_iterations"])
        for _ in range(bisection_count):
            midpoint = 0.5 * (lower + upper)
            candidate = evaluate_blend(midpoint)
            if all(candidate["gates"].values()):
                lower = midpoint
                selected = candidate
            else:
                upper = midpoint
        blend_scale = lower

    result_vertices = selected["vertices"]
    after_volumes = selected["component_volumes"]
    maximum_component_drift = selected["max_component_volume_drift_fraction"]
    total_drift = selected["total_volume_drift_fraction"]
    maximum_displacement = selected["max_vertex_displacement_m"]
    outward_growth = selected["max_outward_aabb_growth_m"]
    gates = selected["gates"]
    skipped_mask = ~eligible_vertices
    if not np.array_equal(result_vertices[skipped_mask], source_vertices[skipped_mask]):
        raise RuntimeError("mesh_smoothing_modified_skipped_component")
    diagnostics = {
        "method": "guarded_uniform_taubin",
        "cycles": cycles,
        "lambda": float(contract["mesh_smoothing_lambda"]),
        "mu": float(contract["mesh_smoothing_mu"]),
        "component_count": int(component_count),
        "eligible_component_count": int(np.count_nonzero(eligible_components)),
        "skipped_component_count": int(np.count_nonzero(~eligible_components)),
        "minimum_component_volume_m3": minimum_volume,
        "before_component_volumes_m3": before_volumes.tolist(),
        "after_component_volumes_m3": after_volumes.tolist(),
        "max_component_volume_drift_fraction": maximum_component_drift,
        "total_volume_drift_fraction": total_drift,
        "max_vertex_displacement_m": maximum_displacement,
        "max_outward_aabb_growth_m": outward_growth,
        "guard_blend_scale": blend_scale,
        "guard_bisection_iterations": bisection_count,
        "proposed_max_component_volume_drift_fraction": proposed[
            "max_component_volume_drift_fraction"
        ],
        "proposed_total_volume_drift_fraction": proposed[
            "total_volume_drift_fraction"
        ],
        "proposed_max_vertex_displacement_m": proposed["max_vertex_displacement_m"],
        "proposed_max_outward_aabb_growth_m": proposed[
            "max_outward_aabb_growth_m"
        ],
        "topology_unchanged": True,
        "faces_sha256": hashlib.sha256(source_faces.tobytes(order="C")).hexdigest(),
        "gates": gates,
    }
    return {
        "vertices": result_vertices,
        "faces": source_faces.copy(),
        "diagnostics": diagnostics,
    }


def reconstruct_surface(
    positions: Sequence[Sequence[float]] | np.ndarray,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from scipy.ndimage import gaussian_filter
    from skimage.measure import marching_cubes

    cfg = dict(default_reconstruction_contract() if contract is None else contract)
    values = np.asarray(positions, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 3 or values.shape[0] == 0:
        raise ValueError("surface_positions_shape_invalid")
    if not np.isfinite(values).all():
        raise ValueError("surface_positions_nonfinite")
    lattice = compute_lattice_spec(values, cfg)
    splatted = _splat_density_field(values, lattice, cfg)
    density = gaussian_filter(
        splatted,
        sigma=float(cfg["gaussian_sigma_voxels"]),
        mode=str(cfg["gaussian_mode"]),
        cval=float(cfg["gaussian_cval"]),
        truncate=float(cfg["gaussian_truncate"]),
        output=np.float32,
    )
    gap_closing = apply_density_gap_closing(density, cfg)
    density = gap_closing["density"]
    level = float(cfg["iso_level"])
    boundary_max = max(
        float(np.max(density[0, :, :])),
        float(np.max(density[-1, :, :])),
        float(np.max(density[:, 0, :])),
        float(np.max(density[:, -1, :])),
        float(np.max(density[:, :, 0])),
        float(np.max(density[:, :, -1])),
    )
    if boundary_max >= level:
        raise ValueError(
            f"surface_density_touches_lattice_boundary:{boundary_max}:{level}"
        )
    if float(np.max(density)) <= level:
        raise ValueError(f"surface_iso_level_above_density:{level}")
    vertices, faces, _ignored_normals, _values = marching_cubes(
        density,
        level=level,
        spacing=(
            float(cfg["voxel_spacing_m"]),
            float(cfg["voxel_spacing_m"]),
            float(cfg["voxel_spacing_m"]),
        ),
        gradient_direction=str(cfg["gradient_direction"]),
        step_size=int(cfg["marching_cubes_step_size"]),
        allow_degenerate=bool(cfg["allow_degenerate"]),
        method=str(cfg["marching_cubes_method"]),
    )
    vertices = vertices.astype(np.float64)
    vertices += np.asarray(lattice["origin_world_m"], dtype=np.float64)
    faces = faces.astype(np.int32)
    if len(vertices) == 0 or len(faces) == 0:
        raise ValueError("surface_mesh_empty")
    topology_cleanup = cleanup_float32_quantized_mesh(vertices, faces, cfg)
    vertices = topology_cleanup["vertices"]
    faces = topology_cleanup["faces"]
    faces, component_volumes, flipped_components = _orient_faces_outward(
        vertices, faces
    )
    if not component_volumes or any(volume <= 1e-15 for volume in component_volumes):
        raise ValueError("surface_component_nonpositive_volume")
    smoothing = apply_guarded_taubin_smoothing(vertices, faces, cfg)
    vertices = smoothing["vertices"]
    faces = smoothing["faces"]
    component_count, vertex_labels = _vertex_components(len(vertices), faces)
    face_labels = vertex_labels[faces[:, 0]]
    component_volumes = [
        _signed_component_volume(vertices, faces, face_labels == label)
        for label in range(component_count)
    ]
    if any(volume <= 1e-15 for volume in component_volumes):
        raise ValueError("surface_smoothed_component_nonpositive_volume")
    face_cross = np.cross(
        vertices[faces[:, 1]].astype(np.float64)
        - vertices[faces[:, 0]].astype(np.float64),
        vertices[faces[:, 2]].astype(np.float64)
        - vertices[faces[:, 0]].astype(np.float64),
    )
    if np.any(np.linalg.norm(face_cross, axis=1) <= 0.0):
        raise ValueError("surface_smoothing_created_degenerate_face")
    boundary_edges, nonmanifold_edges, inconsistent_edges = _edge_diagnostics(faces)
    if boundary_edges or nonmanifold_edges or inconsistent_edges:
        raise ValueError(
            "surface_not_closed_manifold:"
            f"boundary={boundary_edges}:nonmanifold={nonmanifold_edges}:"
            f"inconsistent={inconsistent_edges}"
        )
    normals = _compute_vertex_normals(vertices, faces)
    local_vertices = (
        vertices.astype(np.float64)
        - np.asarray(lattice["origin_world_m"], dtype=np.float64)
    ) / float(cfg["voxel_spacing_m"])
    upper = np.asarray(lattice["shape"], dtype=np.float64) - 1.0
    boundary_touching_vertex_count = int(
        np.count_nonzero(
            np.any(local_vertices <= 1e-5, axis=1)
            | np.any(local_vertices >= upper - 1e-5, axis=1)
        )
    )
    if boundary_touching_vertex_count:
        raise ValueError(
            f"surface_mesh_touches_lattice_boundary:{boundary_touching_vertex_count}"
        )
    vertices = _canonical_array(vertices, "<f4")
    faces = _canonical_array(faces, "<i4")
    normals = _canonical_array(normals, "<f4")
    geometry_hash = canonical_mesh_sha256(vertices, faces, normals)
    diagnostics = {
        "particle_count": int(len(values)),
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        "component_count": int(len(component_volumes)),
        "removed_component_count": 0,
        "component_volumes_m3": component_volumes,
        "signed_volume_m3": float(sum(component_volumes)),
        "boundary_edge_count": boundary_edges,
        "nonmanifold_edge_count": nonmanifold_edges,
        "inconsistent_winding_edge_count": inconsistent_edges,
        "degenerate_face_count": 0,
        "flipped_component_count": flipped_components,
        "boundary_touching_vertex_count": 0,
        "max_boundary_density": boundary_max,
        "max_density": float(np.max(density)),
        "closed_manifold": True,
        "density_gap_closing": gap_closing["diagnostics"],
        "float32_topology_cleanup": topology_cleanup["diagnostics"],
        "mesh_smoothing": smoothing["diagnostics"],
        "bounds_min_world_m": vertices.min(axis=0).astype(float).tolist(),
        "bounds_max_world_m": vertices.max(axis=0).astype(float).tolist(),
        "lattice": lattice,
    }
    return {
        "vertices": vertices,
        "faces": faces,
        "normals": normals,
        "geometry_sha256": geometry_hash,
        "diagnostics": diagnostics,
    }


def _validate_mesh_arrays(
    vertices: np.ndarray, faces: np.ndarray, normals: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vertices = _canonical_array(vertices, "<f4")
    faces = _canonical_array(faces, "<i4")
    normals = _canonical_array(normals, "<f4")
    if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) == 0:
        raise ValueError("mesh_archive_vertices_shape_invalid")
    if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
        raise ValueError("mesh_archive_faces_shape_invalid")
    if normals.shape != vertices.shape:
        raise ValueError("mesh_archive_normals_shape_invalid")
    if not np.isfinite(vertices).all() or not np.isfinite(normals).all():
        raise ValueError("mesh_archive_nonfinite")
    if np.any(faces < 0) or np.any(faces >= len(vertices)):
        raise ValueError("mesh_archive_face_index_invalid")
    return vertices, faces, normals


def write_mesh_archive(path: str | Path, mesh: Mapping[str, Any]) -> dict[str, Any]:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    vertices, faces, normals = _validate_mesh_arrays(
        np.asarray(mesh["vertices"]),
        np.asarray(mesh["faces"]),
        np.asarray(mesh["normals"]),
    )
    geometry_hash = canonical_mesh_sha256(vertices, faces, normals)
    expected_geometry_hash = mesh.get("geometry_sha256")
    if expected_geometry_hash is not None and geometry_hash != expected_geometry_hash:
        raise ValueError("mesh_geometry_sha256_mismatch_before_write")
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("wb") as stream:
            np.savez_compressed(
                stream,
                vertices=vertices,
                faces=faces,
                normals=normals,
            )
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "path": str(destination),
        "file_sha256": sha256_file(destination),
        "geometry_sha256": geometry_hash,
        "size_bytes": destination.stat().st_size,
    }


def load_mesh_archive(
    path: str | Path,
    *,
    expected_file_sha256: str | None = None,
    expected_geometry_sha256: str | None = None,
) -> dict[str, Any]:
    source = Path(path).resolve(strict=True)
    actual_file_hash = sha256_file(source)
    if expected_file_sha256 is not None and actual_file_hash != expected_file_sha256:
        raise ValueError("mesh_archive_file_sha256_mismatch")
    try:
        with np.load(source, allow_pickle=False) as archive:
            if set(archive.files) != {"vertices", "faces", "normals"}:
                raise ValueError("mesh_archive_members_invalid")
            vertices, faces, normals = _validate_mesh_arrays(
                archive["vertices"], archive["faces"], archive["normals"]
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"mesh_archive_load_failed:{type(exc).__name__}") from exc
    geometry_hash = canonical_mesh_sha256(vertices, faces, normals)
    if (
        expected_geometry_sha256 is not None
        and geometry_hash != expected_geometry_sha256
    ):
        raise ValueError("mesh_archive_geometry_sha256_mismatch")
    return {
        "vertices": vertices,
        "faces": faces,
        "normals": normals,
        "file_sha256": actual_file_hash,
        "geometry_sha256": geometry_hash,
    }


def dependency_versions() -> dict[str, str]:
    import scipy
    import skimage

    return {
        "python": ".".join(str(value) for value in sys.version_info[:3]),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "scikit_image": skimage.__version__,
    }


def generate_surface_cache(
    *,
    trace_path: str | Path = DEFAULT_TRACE_PATH,
    scene_path: str | Path = DEFAULT_SCENE_PATH,
    runtime_summary_path: str | Path = DEFAULT_RUNTIME_SUMMARY_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    requested_steps: Sequence[int] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    pins = validate_pinned_inputs(
        trace_path=trace_path,
        scene_path=scene_path,
        runtime_summary_path=runtime_summary_path,
    )
    runtime_summary = json.loads(Path(runtime_summary_path).read_text(encoding="utf-8"))
    if runtime_summary.get("physics_pass") is not True:
        raise ValueError("pinned_runtime_summary_physics_pass_missing")
    contract = default_reconstruction_contract()
    records = load_selected_trace_records(
        trace_path,
        expected_step_count=EXPECTED_TRACE_STEPS,
        expected_particle_count=EXPECTED_PARTICLE_COUNT,
        frame_stride=FRAME_STRIDE,
        contract=contract,
    )
    if requested_steps is not None:
        requested = [int(value) for value in requested_steps]
        if len(set(requested)) != len(requested):
            raise ValueError("requested_steps_not_unique")
        by_step = {record["step_index"]: record for record in records}
        missing = [step for step in requested if step not in by_step]
        if missing:
            raise ValueError(f"requested_steps_not_selected:{missing}")
        records = [by_step[step] for step in requested]
    destination = Path(output_dir).resolve()
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"surface_cache_exists:{destination}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    frames: list[dict[str, Any]] = []
    implementation_hash = sha256_file(Path(__file__))
    versions = dependency_versions()
    try:
        for frame_index, record in enumerate(records):
            step = int(record["step_index"])
            mesh = reconstruct_surface(record["positions"], contract)
            relative_path = Path("meshes") / f"frame_{frame_index:04d}_step_{step:04d}.npz"
            archive = write_mesh_archive(temporary / relative_path, mesh)
            frames.append(
                {
                    "frame_index": frame_index,
                    "step_index": step,
                    "phase": record["phase"],
                    "particle_count": int(record["particle_count"]),
                    "source_position_sha256": record["position_sha256"],
                    "source_parent_matrix": record["source_parent_matrix"],
                    "physics_counts": record["counts"],
                    "mesh_path": relative_path.as_posix(),
                    "mesh_file_sha256": archive["file_sha256"],
                    "geometry_sha256": archive["geometry_sha256"],
                    "mesh_size_bytes": archive["size_bytes"],
                    "mesh_diagnostics": mesh["diagnostics"],
                }
            )
            print(
                f"reconstructed frame={frame_index + 1}/{len(records)} "
                f"step={step} vertices={mesh['diagnostics']['vertex_count']} "
                f"faces={mesh['diagnostics']['face_count']}",
                flush=True,
            )
        manifest = {
            "schema_version": 1,
            "manifest_type": "interndata_derived_surface_mesh_cache",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "presentation_only": True,
            "physics_rerun": False,
            "physics_pass_inherited": True,
            "inputs": pins,
            "reconstruction_contract": contract,
            "reconstruction_contract_sha256": reconstruction_contract_sha256(contract),
            "reconstruction_implementation_sha256": implementation_hash,
            "dependency_versions": versions,
            "frame_stride": FRAME_STRIDE,
            "selected_steps": [frame["step_index"] for frame in frames],
            "frame_count": len(frames),
            "component_filter": "none",
            "frames": frames,
        }
        manifest_path = temporary / "mesh_cache_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            shutil.rmtree(destination)
        temporary.replace(destination)
        return {
            **manifest,
            "output_dir": str(destination),
            "manifest_path": str(destination / manifest_path.name),
            "manifest_sha256": sha256_file(destination / manifest_path.name),
        }
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def _parse_steps(value: str | None) -> list[int] | None:
    if value is None:
        return None
    result = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not result:
        raise argparse.ArgumentTypeError("steps_must_not_be_empty")
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", default=str(DEFAULT_TRACE_PATH))
    parser.add_argument("--scene", default=str(DEFAULT_SCENE_PATH))
    parser.add_argument("--runtime-summary", default=str(DEFAULT_RUNTIME_SUMMARY_PATH))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--steps", default=None, help="Comma-separated selected trace steps")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    manifest = generate_surface_cache(
        trace_path=args.trace,
        scene_path=args.scene,
        runtime_summary_path=args.runtime_summary,
        output_dir=args.out_dir,
        requested_steps=_parse_steps(args.steps),
        overwrite=bool(args.overwrite),
    )
    print(
        json.dumps(
            {
                "output_dir": manifest["output_dir"],
                "manifest_path": manifest["manifest_path"],
                "manifest_sha256": manifest["manifest_sha256"],
                "frame_count": manifest["frame_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
