import hashlib
import json
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = (
    REPO_ROOT
    / "docs/labutopia_lab_poc/evidence_manifests"
    / "interndata_kinematic_pour_probe_final_inset_20260714"
)


def _module():
    from tools.labutopia_fluid import interndata_surface_reconstruction as surface

    return surface


def _identity_matrix():
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _position_hash(positions):
    values = [[float(value) for value in point] for point in positions]
    payload = json.dumps(values, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _record(step_index, positions):
    particle_count = len(positions)
    return {
        "step_index": step_index,
        "phase": "test",
        "particle_count": particle_count,
        "position_sha256": _position_hash(positions),
        "source_parent_matrix": _identity_matrix(),
        "counts": {
            "particle_count": particle_count,
            "finite_partition_total": particle_count,
            "source": particle_count,
            "target": 0,
            "transit": 0,
            "tabletop_spill": 0,
            "below_table": 0,
            "nonfinite": 0,
            "partition_complete": True,
            "valid": True,
        },
        "positions": positions,
    }


def _write_trace(path, records):
    path.write_text(
        "".join(json.dumps(record, allow_nan=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _lattice_cloud(center, dimensions=(5, 5, 5), spacing=0.003):
    center = np.asarray(center, dtype=np.float64)
    axes = [
        (np.arange(count, dtype=np.float64) - 0.5 * (count - 1)) * spacing
        for count in dimensions
    ]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape((-1, 3))
    return grid + center


def test_pinned_inputs_have_valid_matching_sha256_digests():
    surface = _module()

    pins = surface.validate_pinned_inputs()

    assert pins["trace"]["sha256"] == (
        "0321dee981f3ca82e62018352ef66ca12772f75dda35f20330ef2124b552dfb7"
    )
    assert pins["scene"]["sha256"] == (
        "e0c020fe44536406253a9bb14a89f0d2d2b6d415abd369e780e03ef0d1db347d"
    )
    assert pins["runtime_summary"]["sha256"] == (
        "91e2c65dfcd96841e018975d772b4c2ace081d802fc4789d28b5251d7f2a1333"
    )
    assert all(
        len(item["sha256"]) == 64
        and set(item["sha256"]) <= set("0123456789abcdef")
        and item["matches_pin"]
        for item in pins.values()
    )


def test_default_reconstruction_contract_is_exact_and_versioned():
    surface = _module()

    contract = surface.default_reconstruction_contract()

    assert contract == {
        "schema_version": 1,
        "axis_order": "XYZ",
        "field_dtype": "float32",
        "vertex_dtype": "float32",
        "face_dtype": "int32",
        "lattice_anchor_world_m": [0.0, 0.0, 0.0],
        "voxel_spacing_m": pytest.approx(0.00135),
        "padding_voxels": 16,
        "max_axis_voxels": 256,
        "max_total_voxels": 8_000_000,
        "splat": "trilinear_trace_order_unit_mass",
        "gaussian_sigma_voxels": pytest.approx(1.60),
        "gaussian_truncate": pytest.approx(4.0),
        "gaussian_mode": "constant",
        "gaussian_cval": pytest.approx(0.0),
        "density_gap_closing": "ellipsoidal_grey_closing_gravity_z",
        "density_gap_closing_radii_voxels": [3, 3, 8],
        "density_gap_closing_mode": "constant",
        "density_gap_closing_cval": pytest.approx(0.0),
        "iso_level": pytest.approx(0.02),
        "marching_cubes_method": "lewiner",
        "marching_cubes_step_size": 1,
        "gradient_direction": "descent",
        "allow_degenerate": False,
        "component_filter": "none",
        "float32_topology_cleanup": "exact_adjacent_edge_contraction",
        "float32_topology_max_component_volume_drift_fraction": pytest.approx(1.0e-5),
        "mesh_smoothing": "guarded_uniform_taubin",
        "mesh_smoothing_cycles": 10,
        "mesh_smoothing_lambda": pytest.approx(0.50),
        "mesh_smoothing_mu": pytest.approx(-0.53),
        "mesh_smoothing_min_component_volume_m3": pytest.approx(1.0e-7),
        "mesh_smoothing_max_component_volume_drift_fraction": pytest.approx(0.01),
        "mesh_smoothing_max_total_volume_drift_fraction": pytest.approx(0.001),
        "mesh_smoothing_max_vertex_displacement_m": pytest.approx(0.001),
        "mesh_smoothing_max_outward_aabb_growth_m": pytest.approx(0.000125),
        "mesh_smoothing_guard_bisection_iterations": 24,
    }
    assert len(surface.reconstruction_contract_sha256(contract)) == 64


def test_strict_loader_validates_all_records_and_selects_exact_steps(tmp_path):
    surface = _module()
    positions = [[0.0, 0.0, 0.1], [0.003, 0.0, 0.1]]
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(trace_path, [_record(step, positions) for step in range(21)])

    selected = surface.load_selected_trace_records(
        trace_path,
        expected_step_count=21,
        expected_particle_count=2,
        frame_stride=10,
    )

    assert [record["step_index"] for record in selected] == [0, 10, 20]
    assert all(record["positions"].shape == (2, 3) for record in selected)
    assert all(record["positions"].dtype == np.float64 for record in selected)


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda rows: rows.__setitem__(1, {**rows[1], "step_index": 0}), "trace_step"),
        (
            lambda rows: rows[1].__setitem__("positions", [["NaN", 0.0, 0.1]]),
            "positions",
        ),
        (
            lambda rows: rows[1].__setitem__("position_sha256", "0" * 64),
            "position_sha256",
        ),
        (
            lambda rows: rows[1].__setitem__(
                "source_parent_matrix", [[1.0, 0.0], [0.0, 1.0]]
            ),
            "source_parent_matrix",
        ),
    ],
)
def test_strict_loader_rejects_malformed_records(tmp_path, mutate, match):
    surface = _module()
    positions = [[0.0, 0.0, 0.1], [0.003, 0.0, 0.1]]
    rows = [_record(step, positions) for step in range(3)]
    mutate(rows)
    trace_path = tmp_path / "bad.jsonl"
    _write_trace(trace_path, rows)

    with pytest.raises(ValueError, match=match):
        surface.load_selected_trace_records(
            trace_path,
            expected_step_count=3,
            expected_particle_count=2,
            frame_stride=1,
        )


def test_strict_loader_rejects_blank_jsonl_line(tmp_path):
    surface = _module()
    positions = [[0.0, 0.0, 0.1], [0.003, 0.0, 0.1]]
    trace_path = tmp_path / "blank.jsonl"
    trace_path.write_text(
        json.dumps(_record(0, positions))
        + "\n\n"
        + json.dumps(_record(1, positions))
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="blank_trace_line"):
        surface.load_selected_trace_records(
            trace_path,
            expected_step_count=2,
            expected_particle_count=2,
            frame_stride=1,
        )


def test_real_trace_selection_is_exactly_70_hash_valid_records():
    surface = _module()

    selected = surface.load_selected_trace_records(
        RUN_ROOT / "kinematic_trace.jsonl",
        expected_step_count=691,
        expected_particle_count=3600,
        frame_stride=10,
    )

    assert [record["step_index"] for record in selected] == list(range(0, 691, 10))
    assert len({record["position_sha256"] for record in selected}) > 20


def test_lattice_bounds_are_globally_anchored_and_padded():
    surface = _module()
    contract = surface.default_reconstruction_contract()
    positions = np.asarray(
        [[0.001, -0.0031, 0.1], [0.0062, 0.002, 0.109]], dtype=np.float64
    )

    lattice = surface.compute_lattice_spec(positions, contract)

    spacing = contract["voxel_spacing_m"]
    origin = np.asarray(lattice["origin_world_m"])
    assert np.allclose(origin / spacing, np.round(origin / spacing))
    assert all(size > 2 * contract["padding_voxels"] for size in lattice["shape"])
    assert np.all(positions.min(axis=0) - origin >= 16 * spacing - 1e-12)
    maximum = origin + spacing * (np.asarray(lattice["shape"]) - 1)
    assert np.all(maximum - positions.max(axis=0) >= 16 * spacing - 1e-12)


def test_density_gap_closing_is_deterministic_and_axially_bounded():
    surface = _module()
    contract = surface.default_reconstruction_contract()
    footprint = surface.build_density_gap_closing_footprint(contract)
    density = np.zeros((25, 25, 41), dtype=np.float32)
    density[9:16, 9:16, 6:10] = 1.0
    density[9:16, 9:16, 21:25] = 1.0

    first = surface.apply_density_gap_closing(density, contract)
    second = surface.apply_density_gap_closing(density, contract)

    assert footprint.shape == (7, 7, 17)
    assert footprint.dtype == np.bool_
    assert footprint[3, 3, 0]
    assert footprint[3, 3, 16]
    assert not footprint[0, 0, 0]
    assert np.array_equal(first["density"], second["density"])
    assert first["diagnostics"] == second["diagnostics"]
    assert np.all(first["density"][12, 12, 10:21] > 0.0)
    assert first["diagnostics"]["support_bounds_expanded"] is False
    assert first["diagnostics"]["footprint_shape"] == [7, 7, 17]


def test_density_gap_closing_does_not_bridge_large_lateral_gap():
    surface = _module()
    contract = surface.default_reconstruction_contract()
    density = np.zeros((31, 15, 15), dtype=np.float32)
    density[4:7, 7, 7] = 1.0
    density[20:23, 7, 7] = 1.0

    closed = surface.apply_density_gap_closing(density, contract)["density"]

    assert np.all(closed[10:17, 7, 7] == 0.0)


def test_reconstruction_closes_supported_vertical_liquid_gap():
    surface = _module()
    contract = surface.default_reconstruction_contract()
    points = np.concatenate(
        [
            _lattice_cloud((0.0, 0.0, 0.085), dimensions=(4, 4, 4)),
            _lattice_cloud((0.0, 0.0, 0.110), dimensions=(4, 4, 4)),
        ],
        axis=0,
    )

    raw = surface.reconstruct_surface(
        points,
        {**contract, "density_gap_closing": "none"},
    )
    closed = surface.reconstruct_surface(points, contract)

    assert raw["diagnostics"]["component_count"] == 2
    assert closed["diagnostics"]["component_count"] == 1
    assert closed["diagnostics"]["density_gap_closing"]["applied"] is True
    assert closed["diagnostics"]["density_gap_closing"]["support_bounds_expanded"] is False


def test_step_170_exact_float32_cleanup_is_deterministic():
    surface = _module()
    trace_path = RUN_ROOT / "kinematic_trace.jsonl"
    with trace_path.open("r", encoding="utf-8") as stream:
        record = next(
            json.loads(line)
            for line_index, line in enumerate(stream)
            if line_index == 170
        )
    positions = np.asarray(record["positions"], dtype=np.float64)

    first = surface.reconstruct_surface(positions)
    second = surface.reconstruct_surface(positions)

    cleanup = first["diagnostics"]["float32_topology_cleanup"]
    assert cleanup["applied"] is True
    assert cleanup["input_vertex_count"] == 13_288
    assert cleanup["output_vertex_count"] == 13_287
    assert cleanup["input_face_count"] == 26_572
    assert cleanup["output_face_count"] == 26_570
    assert cleanup["welded_vertex_count"] == 1
    assert cleanup["collapsed_face_indices"] == [2895, 2907]
    assert cleanup["removed_float32_nonzero_area_face_count"] == 0
    assert cleanup["component_count_before"] == cleanup["component_count_after"] == 1
    assert cleanup["component_euler_characteristics_before"] == [2]
    assert cleanup["component_euler_characteristics_after"] == [2]
    assert cleanup["component_removal_count"] == 0
    assert cleanup["vertex_displacement_m"] == pytest.approx(0.0)
    assert cleanup["aabb_unchanged"] is True
    assert cleanup["max_component_volume_drift_fraction"] <= 1.0e-5
    assert np.array_equal(first["vertices"], second["vertices"])
    assert np.array_equal(first["faces"], second["faces"])
    assert np.array_equal(first["normals"], second["normals"])
    assert first["geometry_sha256"] == second["geometry_sha256"]


def test_step_260_tiny_components_gate_cleanup_in_float32_space():
    surface = _module()
    trace_path = RUN_ROOT / "kinematic_trace.jsonl"
    with trace_path.open("r", encoding="utf-8") as stream:
        record = next(
            json.loads(line)
            for line_index, line in enumerate(stream)
            if line_index == 260
        )

    mesh = surface.reconstruct_surface(np.asarray(record["positions"], dtype=np.float64))

    cleanup = mesh["diagnostics"]["float32_topology_cleanup"]
    assert cleanup["applied"] is False
    assert cleanup["component_count_before"] == cleanup["component_count_after"] == 6
    assert cleanup["max_component_volume_drift_fraction"] <= 1.0e-5
    assert max(cleanup["float64_to_float32_component_volume_drift_fractions"]) > 1.0e-5
    assert cleanup["component_removal_count"] == 0


def test_float32_cleanup_rejects_weld_across_components():
    surface = _module()
    tetra_vertices = np.asarray(
        [[0.0, 0.0, 0.0], [0.01, 0.0, 0.0], [0.0, 0.01, 0.0], [0.0, 0.0, 0.01]],
        dtype=np.float64,
    )
    tetra_faces = np.asarray(
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int32
    )
    vertices = np.concatenate([tetra_vertices, tetra_vertices + [0.0, 0.0, 0.02]])
    vertices[4] = vertices[0]
    faces = np.concatenate([tetra_faces, tetra_faces + 4])

    with pytest.raises(ValueError, match="float32_cleanup_cross_component_weld"):
        surface.cleanup_float32_quantized_mesh(
            vertices,
            faces,
            surface.default_reconstruction_contract(),
        )


def test_float32_cleanup_rejects_contraction_that_creates_duplicate_faces():
    surface = _module()
    vertices = np.asarray(
        [
            [0.3, 0.0, 0.0],
            [0.3 + 1.0e-8, 0.0, 0.0],
            [0.3, 0.01, 0.0],
            [0.3, 0.0, 0.01],
        ],
        dtype=np.float64,
    )
    faces = np.asarray(
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int32
    )

    with pytest.raises(ValueError, match="float32_cleanup_duplicate_faces_after_weld"):
        surface.cleanup_float32_quantized_mesh(
            vertices,
            faces,
            surface.default_reconstruction_contract(),
        )


def test_reconstruction_is_deterministic_closed_and_outward():
    surface = _module()
    points = _lattice_cloud((0.0, 0.0, 0.1))

    first = surface.reconstruct_surface(points)
    second = surface.reconstruct_surface(points)

    assert np.array_equal(first["vertices"], second["vertices"])
    assert np.array_equal(first["faces"], second["faces"])
    assert np.array_equal(first["normals"], second["normals"])
    assert first["geometry_sha256"] == second["geometry_sha256"]
    diagnostics = first["diagnostics"]
    assert diagnostics["closed_manifold"] is True
    assert diagnostics["boundary_edge_count"] == 0
    assert diagnostics["nonmanifold_edge_count"] == 0
    assert diagnostics["degenerate_face_count"] == 0
    assert diagnostics["component_count"] == 1
    assert diagnostics["signed_volume_m3"] > 0.0
    assert diagnostics["max_boundary_density"] < 0.02
    assert np.isfinite(first["vertices"]).all()
    assert np.isfinite(first["normals"]).all()


def test_reconstruction_retains_two_separated_liquid_components():
    surface = _module()
    points = np.concatenate(
        [
            _lattice_cloud((-0.025, 0.0, 0.1), dimensions=(4, 4, 4)),
            _lattice_cloud((0.025, 0.0, 0.1), dimensions=(4, 4, 4)),
        ],
        axis=0,
    )

    mesh = surface.reconstruct_surface(points)

    assert mesh["diagnostics"]["component_count"] == 2
    assert mesh["diagnostics"]["removed_component_count"] == 0
    assert mesh["diagnostics"]["closed_manifold"] is True


def test_guarded_taubin_smoothing_is_deterministic_and_volume_bounded():
    surface = _module()
    contract = surface.default_reconstruction_contract()
    raw_contract = {**contract, "mesh_smoothing_cycles": 0}
    raw = surface.reconstruct_surface(
        _lattice_cloud((0.0, 0.0, 0.1), dimensions=(6, 6, 6)),
        raw_contract,
    )

    first = surface.apply_guarded_taubin_smoothing(
        raw["vertices"], raw["faces"], contract
    )
    second = surface.apply_guarded_taubin_smoothing(
        raw["vertices"], raw["faces"], contract
    )

    assert np.array_equal(first["vertices"], second["vertices"])
    assert np.array_equal(first["faces"], raw["faces"])
    assert first["diagnostics"] == second["diagnostics"]
    diagnostics = first["diagnostics"]
    assert diagnostics["eligible_component_count"] == 1
    assert diagnostics["max_component_volume_drift_fraction"] <= 0.01
    assert diagnostics["total_volume_drift_fraction"] <= 0.001
    assert diagnostics["max_vertex_displacement_m"] <= 0.001
    assert diagnostics["max_outward_aabb_growth_m"] <= 0.000125
    assert 0.0 < diagnostics["guard_blend_scale"] <= 1.0
    assert diagnostics["guard_bisection_iterations"] == 24
    assert diagnostics["proposed_total_volume_drift_fraction"] >= (
        diagnostics["total_volume_drift_fraction"]
    )
    assert diagnostics["topology_unchanged"] is True


def test_guarded_taubin_smoothing_leaves_tiny_component_byte_identical():
    surface = _module()
    contract = surface.default_reconstruction_contract()
    raw_contract = {**contract, "mesh_smoothing_cycles": 0}
    raw = surface.reconstruct_surface(
        _lattice_cloud((0.0, 0.0, 0.1), dimensions=(6, 6, 6)),
        raw_contract,
    )
    tiny_vertices = np.asarray(
        [
            [0.05, 0.0, 0.1],
            [0.053, 0.0, 0.1],
            [0.05, 0.003, 0.1],
            [0.05, 0.0, 0.103],
        ],
        dtype=np.float32,
    )
    tiny_faces = np.asarray(
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype=np.int32
    )
    tiny_start = len(raw["vertices"])
    vertices = np.concatenate([raw["vertices"], tiny_vertices], axis=0)
    faces = np.concatenate([raw["faces"], tiny_faces + tiny_start], axis=0)

    result = surface.apply_guarded_taubin_smoothing(vertices, faces, contract)

    assert np.array_equal(result["vertices"][tiny_start:], tiny_vertices)
    assert result["diagnostics"]["skipped_component_count"] == 1
    assert result["diagnostics"]["eligible_component_count"] == 1


def test_mesh_archive_round_trip_is_safe_and_hash_checked(tmp_path):
    surface = _module()
    mesh = surface.reconstruct_surface(_lattice_cloud((0.0, 0.0, 0.1)))
    path = tmp_path / "mesh.npz"

    written = surface.write_mesh_archive(path, mesh)
    loaded = surface.load_mesh_archive(
        path,
        expected_file_sha256=written["file_sha256"],
        expected_geometry_sha256=mesh["geometry_sha256"],
    )

    assert np.array_equal(loaded["vertices"], mesh["vertices"])
    assert np.array_equal(loaded["faces"], mesh["faces"])
    assert np.array_equal(loaded["normals"], mesh["normals"])
    path.write_bytes(path.read_bytes()[:-16] + b"corrupt-archive!!")
    with pytest.raises(ValueError, match="mesh_archive_file_sha256_mismatch"):
        surface.load_mesh_archive(
            path,
            expected_file_sha256=written["file_sha256"],
            expected_geometry_sha256=mesh["geometry_sha256"],
        )
