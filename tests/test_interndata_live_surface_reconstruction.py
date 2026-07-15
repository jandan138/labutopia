from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from tools.labutopia_fluid import interndata_surface_reconstruction as surface


RUN_ROOT = (
    Path(__file__).resolve().parents[1]
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "interndata_kinematic_pour_probe_final_inset_20260714"
)


def _grid_cloud(offset=(0.2, -0.1, 0.8)) -> np.ndarray:
    points = []
    for x in range(7):
        for y in range(7):
            for z in range(9):
                points.append(
                    [
                        offset[0] + x * 0.003,
                        offset[1] + y * 0.003,
                        offset[2] + z * 0.003,
                    ]
                )
    return np.asarray(points, dtype=np.float64)


def _trace_positions(step: int) -> np.ndarray:
    with (RUN_ROOT / "kinematic_trace.jsonl").open("r", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record["step_index"] == step:
                return np.asarray(record["positions"], dtype=np.float64)
    raise AssertionError(f"missing step {step}")


def _signed_volume(vertices: np.ndarray, faces: np.ndarray) -> float:
    return float(
        np.einsum(
            "ij,ij->i",
            vertices[faces[:, 0]].astype(np.float64),
            np.cross(
                vertices[faces[:, 1]].astype(np.float64),
                vertices[faces[:, 2]].astype(np.float64),
            ),
        ).sum()
        / 6.0
    )


def test_live_contract_is_explicit_and_does_not_change_offline_contract():
    offline = surface.default_reconstruction_contract()
    live = surface.default_live_reconstruction_contract()

    assert offline["density_gap_closing"] == "ellipsoidal_grey_closing_gravity_z"
    assert offline["mesh_smoothing"] == "guarded_uniform_taubin"
    assert live == {
        "schema_version": 1,
        "axis_order": "XYZ",
        "field_dtype": "float32",
        "vertex_dtype": "float32",
        "face_dtype": "int32",
        "lattice_anchor_world_m": [0.0, 0.0, 0.0],
        "voxel_spacing_m": 0.00135,
        "padding_voxels": 16,
        "max_axis_voxels": 512,
        "max_total_voxels": 24_000_000,
        "splat": "trilinear_trace_order_unit_mass",
        "gaussian_sigma_voxels": 1.60,
        "gaussian_truncate": 4.0,
        "gaussian_mode": "constant",
        "gaussian_cval": 0.0,
        "density_gap_closing": "rectangular_grey_closing_gravity_z",
        "density_gap_closing_size_voxels": [7, 7, 17],
        "density_gap_closing_mode": "constant",
        "density_gap_closing_cval": 0.0,
        "iso_level": 0.02,
        "marching_cubes_method": "lewiner",
        "marching_cubes_step_size": 1,
        "gradient_direction": "ascent",
        "allow_degenerate": False,
        "component_filter": "none",
        "mesh_coordinate_frame": "lattice_local_translation",
        "mesh_smoothing": "none_density_gradient_vertex_normals",
    }


def _two_point_cloud_for_lattice_shape(shape, spacing):
    maximum_indices = np.asarray(shape, dtype=np.int64) - 33
    return np.asarray(
        [[0.0, 0.0, 0.0], maximum_indices.astype(np.float64) * spacing],
        dtype=np.float64,
    )


def test_live_lattice_accepts_pour_span_without_changing_offline_limit():
    live = surface.default_live_reconstruction_contract()
    offline = surface.default_reconstruction_contract()
    points = _two_point_cloud_for_lattice_shape(
        [84, 216, 271], live["voxel_spacing_m"]
    )

    lattice = surface.compute_lattice_spec(points, live)

    assert lattice["shape"] == [84, 216, 271]
    assert lattice["total_voxels"] == 84 * 216 * 271
    assert live["max_axis_voxels"] == 512
    assert offline["max_axis_voxels"] == 256
    assert live["max_total_voxels"] == 24_000_000
    assert offline["max_total_voxels"] == 8_000_000
    with pytest.raises(ValueError, match="lattice_axis_limit_exceeded"):
        surface.compute_lattice_spec(points, offline)


def test_live_lattice_keeps_axis_and_total_voxel_guards():
    live = surface.default_live_reconstruction_contract()
    spacing = live["voxel_spacing_m"]

    assert surface.compute_lattice_spec(
        _two_point_cloud_for_lattice_shape([33, 33, 512], spacing), live
    )["shape"] == [33, 33, 512]
    with pytest.raises(ValueError, match="lattice_axis_limit_exceeded"):
        surface.compute_lattice_spec(
            _two_point_cloud_for_lattice_shape([33, 33, 513], spacing), live
        )
    observed_stream = _two_point_cloud_for_lattice_shape(
        [150, 243, 230], spacing
    )
    assert surface.compute_lattice_spec(
        observed_stream, live
    )["total_voxels"] == 8_383_500
    with pytest.raises(ValueError, match="lattice_total_limit_exceeded"):
        surface.compute_lattice_spec(
            observed_stream, surface.default_reconstruction_contract()
        )
    long_stream = _two_point_cloud_for_lattice_shape([205, 327, 247], spacing)
    assert surface.compute_lattice_spec(
        long_stream, live
    )["total_voxels"] == 16_557_645
    assert surface.compute_lattice_spec(
        _two_point_cloud_for_lattice_shape([250, 250, 384], spacing), live
    )["total_voxels"] == 24_000_000
    with pytest.raises(ValueError, match="lattice_total_limit_exceeded"):
        surface.compute_lattice_spec(
            _two_point_cloud_for_lattice_shape([251, 250, 384], spacing), live
        )


def test_live_lattice_accepts_the_observed_full_spill_span():
    live = surface.default_live_reconstruction_contract()
    spacing = live["voxel_spacing_m"]

    lattice = surface.compute_lattice_spec(
        _two_point_cloud_for_lattice_shape([229, 263, 334], spacing), live
    )

    assert lattice["total_voxels"] == 20_115_818


def test_live_lattice_accepts_the_source_center_probe_vertical_span():
    live = surface.default_live_reconstruction_contract()
    spacing = live["voxel_spacing_m"]

    observed = surface.compute_lattice_spec(
        _two_point_cloud_for_lattice_shape([121, 168, 382], spacing), live
    )
    next_vertical_cell = surface.compute_lattice_spec(
        _two_point_cloud_for_lattice_shape([121, 168, 385], spacing), live
    )

    assert observed["total_voxels"] == 7_765_296
    assert next_vertical_cell["total_voxels"] == 7_826_280


def test_live_reconstruction_is_deterministic_closed_and_lattice_local():
    points = _grid_cloud()

    first = surface.reconstruct_surface_live(points)
    second = surface.reconstruct_surface_live(points.copy())

    assert first["geometry_sha256"] == second["geometry_sha256"]
    np.testing.assert_array_equal(first["vertices"], second["vertices"])
    np.testing.assert_array_equal(first["faces"], second["faces"])
    np.testing.assert_array_equal(first["normals"], second["normals"])
    assert first["vertices"].dtype == np.float32
    assert first["faces"].dtype == np.int32
    assert first["normals"].dtype == np.float32
    assert len(first["vertices"]) > 0
    assert len(first["faces"]) > 0
    assert surface._edge_diagnostics(first["faces"]) == (0, 0, 0)
    assert _signed_volume(first["vertices"], first["faces"]) > 0.0
    assert first["diagnostics"]["mesh_coordinate_frame"] == (
        "lattice_local_translation"
    )
    assert len(first["origin_world_m"]) == 3
    assert first["diagnostics"]["max_boundary_density"] < 0.02


def test_live_geometry_hash_binds_world_origin_not_only_local_arrays():
    points = _grid_cloud()
    shift = np.asarray([0.0135, 0.0, 0.0])

    first = surface.reconstruct_surface_live(points)
    shifted = surface.reconstruct_surface_live(points + shift)

    np.testing.assert_allclose(first["vertices"], shifted["vertices"], atol=2e-6)
    np.testing.assert_array_equal(first["faces"], shifted["faces"])
    np.testing.assert_allclose(
        np.asarray(shifted["origin_world_m"]) - np.asarray(first["origin_world_m"]),
        shift,
        atol=1e-12,
    )
    assert first["geometry_sha256"] != shifted["geometry_sha256"]


def test_live_real_pour_frame_retains_all_components_and_closed_topology():
    mesh = surface.reconstruct_surface_live(_trace_positions(230))

    diagnostics = mesh["diagnostics"]
    assert diagnostics["particle_count"] == 3600
    assert diagnostics["component_filter"] == "none"
    assert diagnostics["component_count"] >= 1
    assert diagnostics["boundary_edge_count"] == 0
    assert diagnostics["nonmanifold_edge_count"] == 0
    assert diagnostics["inconsistent_winding_edge_count"] == 0
    assert diagnostics["density_gap_closing"]["support_bounds_expanded"] is False
    assert _signed_volume(mesh["vertices"], mesh["faces"]) > 0.0


def test_live_reconstruction_api_has_no_trace_cache_or_time_input():
    signature = inspect.signature(surface.reconstruct_surface_live)

    assert list(signature.parameters) == ["positions", "contract"]
    source = inspect.getsource(surface.reconstruct_surface_live)
    assert "trace" not in source.lower()
    assert ".npz" not in source.lower()
    assert "cache" not in source.lower()
    assert "time" not in source.lower()
