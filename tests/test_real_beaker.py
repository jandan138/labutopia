import math
import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def real_stage():
    from pxr import Usd

    scene_path = Path(
        "outputs/usd_asset_packages/lab_001_localized_20260707/"
        "lab_001_level1_pour_tabletop_with_liquid.usd"
    )
    assert scene_path.is_file(), f"required localized scene is missing: {scene_path}"
    return Usd.Stage.Open(str(scene_path))


@pytest.fixture(scope="module")
def real_frame(real_stage):
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    return derive_cup_interior_frame(
        real_stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path="/World/ParticleSet",
    )


def _trace_record(step_index, positions):
    return {
        "step_index": step_index,
        "particle_count": len(positions),
        "positions": positions,
    }


def _classify_test_trace(real_frame, records, **overrides):
    from tools.labutopia_fluid.real_beaker import classify_visible_beaker_trace

    options = {
        "requested_count": len(records[0]["positions"]),
        "steps": records[-1]["step_index"],
        "cadence": 10,
        "tail_window_steps": 10,
        "source_usd_sha256": "a" * 64,
        "particle_seed": 0,
        "diagnostic_log_text": "run diagnostics clean",
        "diagnostic_scan_complete": True,
        "readback_available": True,
    }
    options.update(overrides)
    return classify_visible_beaker_trace(records, real_frame, **options)


def test_derive_cup_frame_maps_canonical_z_to_rotated_parent_local_y():
    import pytest
    from pxr import Gf, Usd, UsdGeom
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    cup = UsdGeom.Xform.Define(stage, "/World/beaker2")
    cup.AddTranslateOp().Set(Gf.Vec3d(0.295, 0.075, 0.87))
    cup.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 45.0))
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(x, y, z)
            for x in (-0.04, 0.04)
            for y in (-0.045, 0.045)
            for z in (-0.0375, 0.0375)
        ]
    )

    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path=None,
    )

    assert frame.parent_local_axis == "Y"
    assert frame.z_axis_world == pytest.approx((0.0, 0.0, 1.0), abs=1e-6)
    assert frame.axis_alignment_dot >= 0.999


def test_cup_frame_dot_product_transforms_round_trip():
    import pytest
    from pxr import Gf, Usd, UsdGeom
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    cup = UsdGeom.Xform.Define(stage, "/World/beaker2")
    cup.AddTranslateOp().Set(Gf.Vec3d(0.295, 0.075, 0.87))
    cup.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 45.0))
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(x, y, z)
            for x in (-0.04, 0.04)
            for y in (-0.045, 0.045)
            for z in (-0.0375, 0.0375)
        ]
    )

    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path=None,
    )
    point = (0.01, -0.02, 0.03)

    assert frame.world_to_canonical(frame.canonical_to_world(point)) == pytest.approx(point)


def test_derive_cup_frame_preserves_negative_parent_axis_sign():
    import pytest
    from pxr import Gf, Usd, UsdGeom
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    cup = UsdGeom.Xform.Define(stage, "/World/beaker2")
    cup.AddRotateXYZOp().Set(Gf.Vec3f(-90.0, 0.0, 0.0))
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(x, y, z)
            for x in (-0.04, 0.04)
            for y in (-0.045, 0.045)
            for z in (-0.0375, 0.0375)
        ]
    )

    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path=None,
    )

    assert frame.parent_local_axis == "-Y"
    assert frame.z_axis_world == pytest.approx((0.0, 0.0, 1.0), abs=1e-6)


def test_real_lab001_frame_uses_local_y_and_original_fluid_calibration():
    from pathlib import Path

    import pytest
    from pxr import Usd
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    scene_path = Path(
        "outputs/usd_asset_packages/lab_001_localized_20260707/"
        "lab_001_level1_pour_tabletop_with_liquid.usd"
    )
    assert scene_path.is_file(), f"required localized scene is missing: {scene_path}"
    stage = Usd.Stage.Open(str(scene_path))
    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path="/World/ParticleSet",
    )

    assert frame.parent_local_axis == "Y"
    assert frame.z_axis_world == pytest.approx((0.0, 0.0, 1.0), abs=1e-6)
    assert frame.outer_radius == pytest.approx(0.037666, abs=0.001)
    assert frame.interior_radius == pytest.approx(0.0330, abs=0.002)
    assert frame.calibration_source == "authored_particle_bounds"
    assert frame.as_dict()["parent_local_mesh_bounds"]["size"] == pytest.approx(
        (0.0811547, 0.0904004, 0.0753325),
        abs=1e-5,
    )
    assert frame.as_dict()["calibration"]["parent_local_mesh_bounds"]["size"] == pytest.approx(
        (0.0811547, 0.0904004, 0.0753325),
        abs=1e-5,
    )


def test_cup_frame_serialization_does_not_expose_mutable_measurements():
    import pytest
    from pxr import Gf, Usd, UsdGeom
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    cup = UsdGeom.Xform.Define(stage, "/World/beaker2")
    cup.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 0.0))
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(x, y, z)
            for x in (-0.04, 0.04)
            for y in (-0.045, 0.045)
            for z in (-0.0375, 0.0375)
        ]
    )
    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path=None,
    )

    serialized = frame.as_dict()
    serialized["calibration"]["parent_local_mesh_bounds"]["min"] = (999.0, 999.0, 999.0)

    with pytest.raises(TypeError):
        frame._measurements["calibration"]["parent_local_mesh_bounds"]["min"] = (999.0, 999.0, 999.0)

    assert frame.as_dict()["calibration"]["parent_local_mesh_bounds"]["min"] != (
        999.0,
        999.0,
        999.0,
    )


def test_cup_frame_fallback_records_exact_wall_clearance():
    import pytest
    from pxr import Gf, Usd, UsdGeom
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    cup = UsdGeom.Xform.Define(stage, "/World/beaker2")
    cup.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 0.0))
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(x, y, z)
            for x in (-0.04, 0.04)
            for y in (-0.045, 0.045)
            for z in (-0.0375, 0.0375)
        ]
    )
    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path=None,
    )
    calibration = frame.as_dict()["calibration"]

    assert frame.outer_radius - frame.interior_radius == pytest.approx(0.005)
    assert frame.calibration_source == "fallback_mesh_inscribed_radius"
    assert calibration["fallback_wall_clearance"] == pytest.approx(0.005)
    assert calibration["outer_to_calibrated_wall_clearance"] == pytest.approx(0.005)
    assert calibration["final_radius"] == pytest.approx(frame.interior_radius)


def test_cup_frame_clamps_oversized_calibration_and_records_provenance():
    import pytest
    from pxr import Gf, Usd, UsdGeom
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    cup = UsdGeom.Xform.Define(stage, "/World/beaker2")
    cup.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 0.0))
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(x, y, z)
            for x in (-0.04, 0.04)
            for y in (-0.045, 0.045)
            for z in (-0.0375, 0.0375)
        ]
    )
    particles = UsdGeom.Points.Define(stage, "/World/beaker2/calibration")
    particles.CreatePointsAttr([Gf.Vec3f(-0.2, 0.0, -0.2), Gf.Vec3f(0.2, 0.0, 0.2)])
    frame = derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path="/World/beaker2/calibration",
    )
    calibration = frame.as_dict()["calibration"]

    assert frame.interior_radius < frame.outer_radius
    assert calibration["raw_radial_envelope"] > frame.outer_radius
    assert calibration["final_radius"] == pytest.approx(frame.interior_radius)
    assert calibration["outer_to_calibrated_wall_clearance"] == pytest.approx(
        frame.outer_radius - frame.interior_radius
    )


def test_strict_classifier_rejects_below_floor_and_outside_radius(real_frame):
    from tools.labutopia_fluid.real_beaker import classify_visible_beaker_positions

    inside = real_frame.canonical_to_world((0.0, 0.0, real_frame.interior_floor + 0.01))
    below = real_frame.canonical_to_world((0.0, 0.0, real_frame.interior_floor - 0.001))
    outside = real_frame.canonical_to_world((real_frame.interior_radius + 0.001, 0.0, 0.03))
    result = classify_visible_beaker_positions([inside, below, outside], real_frame)
    assert result["inside_visible_interior_count"] == 1
    assert result["below_visible_floor_count"] == 1
    assert result["outside_visible_radial_count"] == 1


def test_old_false_pass_trace_fails_strict_visible_gate():
    from tools.labutopia_fluid.real_beaker import classify_visible_beaker_trace_from_files

    result = classify_visible_beaker_trace_from_files(
        manifest_path="docs/labutopia_lab_poc/evidence_manifests/"
        "fluid_spike_full_scene_controlled_spawn_hold_20260710_P4096.json"
    )
    assert result["classification"] == "FAIL_VISIBLE_BEAKER_CONTAINMENT"
    assert result["below_visible_floor_count"] >= 3926


@pytest.mark.parametrize(
    ("particle_count", "particle_width", "particle_contact_offset"),
    ((1024, 0.0006, 0.00054), (4096, 0.00045, 0.0005)),
)
def test_canonical_spawn_is_inside_real_visible_interior(
    real_frame,
    particle_count,
    particle_width,
    particle_contact_offset,
):
    from tools.labutopia_fluid.fluid_recipe import build_controlled_spawn_plan
    from tools.labutopia_fluid.real_beaker import (
        build_visible_beaker_spawn,
        classify_visible_beaker_positions,
    )

    spawn = build_visible_beaker_spawn(
        real_frame,
        build_controlled_spawn_plan(particle_count, particle_seed=0),
        physics_particle_width=particle_width,
        particle_contact_offset=particle_contact_offset,
    )
    counts = classify_visible_beaker_positions(spawn.positions_world, real_frame)
    assert len(spawn.positions_world) == particle_count
    assert counts["inside_visible_interior_count"] == particle_count
    assert counts["below_visible_floor_count"] == 0
    assert counts["outside_visible_radial_count"] == 0
    assert counts["above_visible_rim_count"] == 0
    assert spawn.canonical_bounds["max"][2] < real_frame.rim_height
    assert set(spawn.velocities_world) == {(0.0, 0.0, 0.0)}


@pytest.mark.parametrize(
    "malformed_point",
    ([0.0, 0.0], [0.0, 0.0, 0.0, 0.0], [0.0, "not-numeric", 0.0]),
)
def test_strict_trace_rejects_malformed_point_schema(real_frame, malformed_point):
    result = _classify_test_trace(real_frame, [_trace_record(0, [malformed_point])])

    assert result["classification"] == "STOP_INCOMPLETE_TRACE"
    assert result["trace_schema_valid"] is False


@pytest.mark.parametrize(
    "step_indices",
    ([0, 20], [0, 10, 10, 20]),
)
def test_strict_trace_rejects_missing_or_duplicate_cadence(real_frame, step_indices):
    inside = list(real_frame.canonical_to_world((0.0, 0.0, 0.01)))
    records = [_trace_record(step, [inside]) for step in step_indices]
    result = _classify_test_trace(real_frame, records, steps=20)

    assert result["classification"] == "STOP_INCOMPLETE_TRACE"
    assert result["trace_schema_valid"] is False


@pytest.mark.parametrize("nonfinite", [math.nan, math.inf, -math.inf])
def test_strict_trace_classifies_nonfinite_as_particle_explosion(real_frame, nonfinite):
    result = _classify_test_trace(
        real_frame,
        [_trace_record(0, [[nonfinite, 0.0, 0.0]])],
    )

    assert result["classification"] == "FAIL_PARTICLE_EXPLOSION"
    assert result["nonfinite_count"] == 1


def test_trace_identity_has_required_fields_and_stable_ordered_hash(real_frame):
    from tools.labutopia_fluid.real_beaker import validate_strict_trace_schema

    left = list(real_frame.canonical_to_world((-0.001, 0.0, 0.01)))
    right = list(real_frame.canonical_to_world((0.001, 0.0, 0.01)))
    records = [_trace_record(0, [left, right])]
    options = {
        "requested_count": 2,
        "steps": 0,
        "cadence": 10,
        "source_usd_sha256": "b" * 64,
        "particle_seed": 7,
    }
    first = validate_strict_trace_schema(records, **options)
    repeated = validate_strict_trace_schema(records, **options)
    reordered = validate_strict_trace_schema(
        [_trace_record(0, [right, left])], **options
    )

    assert set(first) == {
        "physical_trace_sha256",
        "source_usd_sha256",
        "particle_count",
        "seed",
        "steps",
        "trace_interval",
        "frame_indices",
        "frame_particle_counts",
        "frame_count",
        "positions_sha256",
    }
    assert first == repeated
    assert first["positions_sha256"] != reordered["positions_sha256"]
    assert first["physical_trace_sha256"] != reordered["physical_trace_sha256"]


def test_strict_trace_prioritizes_unavailable_readback_over_leak(real_frame):
    below = list(real_frame.canonical_to_world((0.0, 0.0, -0.001)))
    result = _classify_test_trace(
        real_frame,
        [_trace_record(0, [below])],
        readback_available=False,
    )

    assert result["classification"] == "FAIL_READBACK_UNAVAILABLE"


def test_strict_trace_prioritizes_incomplete_diagnostics_over_leak(real_frame):
    below = list(real_frame.canonical_to_world((0.0, 0.0, -0.001)))
    result = _classify_test_trace(
        real_frame,
        [_trace_record(0, [below])],
        diagnostic_scan_complete=False,
    )

    assert result["classification"] == "STOP_INCOMPLETE_DIAGNOSTICS"


def test_strict_trace_prioritizes_fatal_error_over_leak(real_frame):
    below = list(real_frame.canonical_to_world((0.0, 0.0, -0.001)))
    result = _classify_test_trace(
        real_frame,
        [_trace_record(0, [below])],
        fatal_error="simulation_failed",
    )

    assert result["classification"] == "FAIL_RUNTIME_FATAL_ERROR"


@pytest.mark.parametrize(
    ("log_text", "classification"),
    (
        ("CPU collision fallback", "FAIL_CPU_COLLISION_FALLBACK"),
        ("unsupported GPU collider", "FAIL_GPU_COLLIDER_UNSUPPORTED"),
    ),
)
def test_strict_trace_prioritizes_diagnostic_failures_over_leak(
    real_frame, log_text, classification
):
    below = list(real_frame.canonical_to_world((0.0, 0.0, -0.001)))
    result = _classify_test_trace(
        real_frame,
        [_trace_record(0, [below])],
        diagnostic_log_text=log_text,
    )

    assert result["classification"] == classification


@pytest.mark.parametrize("missing_gate", ["readback_available", "trace_schema_valid"])
def test_strict_static_hold_pass_requires_complete_evidence(real_frame, missing_gate):
    from tools.labutopia_fluid.real_beaker import strict_static_hold_pass

    inside = list(real_frame.canonical_to_world((0.0, 0.0, 0.01)))
    result = _classify_test_trace(real_frame, [_trace_record(0, [inside])])
    assert result["classification"] == "PASS_VISIBLE_BEAKER_STATIC_HOLD"

    result[missing_gate] = False
    assert strict_static_hold_pass(result) is False


def test_strict_trace_passes_only_when_every_gate_is_satisfied(real_frame):
    inside = list(real_frame.canonical_to_world((0.0, 0.0, 0.01)))
    records = [_trace_record(step, [inside]) for step in (0, 10, 20)]
    result = _classify_test_trace(real_frame, records)

    assert result["classification"] == "PASS_VISIBLE_BEAKER_STATIC_HOLD"
    assert result["passed"] is True
    assert result["trace_schema_valid"] is True
    assert result["readback_available"] is True


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("step_index", 0.0),
        ("step_index", "0"),
        ("step_index", False),
        ("particle_count", 1.0),
        ("particle_count", "1"),
        ("particle_count", True),
    ),
)
def test_strict_integer_record_metadata_rejects_coercible_types(
    real_frame, field, invalid_value
):
    inside = list(real_frame.canonical_to_world((0.0, 0.0, 0.01)))
    record = _trace_record(0, [inside])
    record[field] = invalid_value

    result = _classify_test_trace(real_frame, [record], steps=0)

    assert result["classification"] == "STOP_INCOMPLETE_TRACE"
    assert result["trace_schema_valid"] is False
    assert "physical_trace_identity" not in result


@pytest.mark.parametrize(
    ("field", "valid_value"),
    (
        ("requested_count", 1),
        ("steps", 0),
        ("cadence", 10),
        ("tail_window_steps", 10),
        ("particle_seed", 0),
    ),
)
@pytest.mark.parametrize("invalid_kind", ["float", "string", "bool"])
def test_strict_integer_contract_metadata_rejects_coercible_types(
    real_frame, field, valid_value, invalid_kind
):
    inside = list(real_frame.canonical_to_world((0.0, 0.0, 0.01)))
    invalid_value = {
        "float": float(valid_value),
        "string": str(valid_value),
        "bool": bool(valid_value),
    }[invalid_kind]

    result = _classify_test_trace(
        real_frame,
        [_trace_record(0, [inside])],
        **{field: invalid_value},
    )

    assert result["classification"] == "STOP_INCOMPLETE_TRACE"
    assert result["trace_schema_valid"] is False
    assert "physical_trace_identity" not in result


@pytest.mark.parametrize(
    ("field_path", "invalid_value", "remove"),
    (
        (("selected_particle_count",), None, True),
        (("selected_particle_count",), "4096", False),
        (("steps",), 120.0, False),
        (("region_config", "trace_interval"), False, False),
        (("region_config", "tail_window_steps"), "30", False),
        (("controlled_spawn_plan", "particle_seed"), None, True),
        (("controlled_spawn_plan", "particle_seed"), 0.0, False),
        (("source_usd_path",), None, True),
        (("source_usd_path",), False, False),
        (("trace_path",), None, True),
        (("trace_path",), 123, False),
    ),
)
def test_manifest_contract_failures_stop_incomplete_trace(
    tmp_path, field_path, invalid_value, remove
):
    from tools.labutopia_fluid.real_beaker import classify_visible_beaker_trace_from_files

    historical_path = Path(
        "docs/labutopia_lab_poc/evidence_manifests/"
        "fluid_spike_full_scene_controlled_spawn_hold_20260710_P4096.json"
    )
    manifest = json.loads(historical_path.read_text(encoding="utf-8"))
    parent = manifest
    for key in field_path[:-1]:
        parent = parent[key]
    if remove:
        del parent[field_path[-1]]
    else:
        parent[field_path[-1]] = invalid_value
    manifest_path = tmp_path / "invalid_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = classify_visible_beaker_trace_from_files(manifest_path=manifest_path)

    assert result["classification"] == "STOP_INCOMPLETE_TRACE"
    assert result["trace_schema_error"]


@pytest.mark.parametrize("malformed_region_counts", [[], "invalid", 1, True])
def test_strict_trace_rejects_malformed_region_counts(
    real_frame, malformed_region_counts
):
    inside = list(real_frame.canonical_to_world((0.0, 0.0, 0.01)))
    record = _trace_record(0, [inside])
    record["region_counts"] = malformed_region_counts

    result = _classify_test_trace(real_frame, [record])

    assert result["classification"] == "STOP_INCOMPLETE_TRACE"
    assert result["trace_schema_valid"] is False


@pytest.mark.parametrize("location", ["top_level", "region_counts"])
@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("finite_count", 1.0),
        ("finite_count", "1"),
        ("finite_count", True),
        ("nonfinite_count", 0.0),
        ("nonfinite_count", "0"),
        ("nonfinite_count", False),
    ),
)
def test_strict_trace_rejects_coercible_optional_declared_counts(
    real_frame, location, field, invalid_value
):
    inside = list(real_frame.canonical_to_world((0.0, 0.0, 0.01)))
    record = _trace_record(0, [inside])
    if location == "top_level":
        record[field] = invalid_value
    else:
        record["region_counts"] = {field: invalid_value}

    result = _classify_test_trace(real_frame, [record])

    assert result["classification"] == "STOP_INCOMPLETE_TRACE"
    assert result["trace_schema_valid"] is False
