import hashlib

import pytest
from pxr import Sdf, Usd, UsdGeom, UsdShade

from tools.labutopia_fluid.real_beaker import CupInteriorFrame


@pytest.fixture
def real_frame():
    return CupInteriorFrame(
        origin_world=(0.3, 0.1, 0.82),
        x_axis_world=(0.0, 1.0, 0.0),
        y_axis_world=(-1.0, 0.0, 0.0),
        z_axis_world=(0.0, 0.0, 1.0),
        parent_local_axis="Y",
        outer_radius=0.0375,
        interior_radius=0.032,
        outer_floor=0.0,
        interior_floor=0.0,
        rim_height=0.09,
        calibration_source="test_fixture",
        axis_alignment_dot=1.0,
    )


def test_reference_candidates_scale_and_clamp_from_interior_diameter():
    from tools.labutopia_fluid.omniglass_reference import build_reference_candidates

    candidates = build_reference_candidates(interior_diameter=0.064)

    assert list(candidates) == [
        "OMNI_REF_FINE",
        "OMNI_REF_RATIO_15",
        "OMNI_REF_RATIO_12",
    ]
    assert candidates["OMNI_REF_FINE"]["display_width"] == pytest.approx(0.002)
    assert candidates["OMNI_REF_RATIO_15"]["display_width"] == pytest.approx(0.064 / 15)
    assert candidates["OMNI_REF_RATIO_12"]["display_width"] == pytest.approx(0.064 / 12)
    assert all(
        candidate["voxel_size"] == candidate["display_width"]
        for candidate in candidates.values()
    )

    assert build_reference_candidates(0.032)["OMNI_REF_FINE"][
        "display_width"
    ] == pytest.approx(0.0015)
    assert build_reference_candidates(0.056)["OMNI_REF_FINE"][
        "display_width"
    ] == pytest.approx(0.056 / 32)


@pytest.mark.parametrize("diameter", [0.0, -0.064, float("nan"), float("inf")])
def test_reference_candidates_reject_invalid_interior_diameter(diameter):
    from tools.labutopia_fluid.omniglass_reference import build_reference_candidates

    with pytest.raises(ValueError, match="interior_diameter"):
        build_reference_candidates(diameter)


def test_voxel_proxy_is_deterministic_in_canonical_lexicographic_order(real_frame):
    from tools.labutopia_fluid.omniglass_reference import voxel_cluster_world_positions

    canonical_points = [
        (0.010, 0.010, 0.030),
        (0.0015, 0.0015, 0.0205),
        (0.001, 0.001, 0.020),
        (-0.001, 0.009, 0.010),
    ]
    points = [real_frame.canonical_to_world(point) for point in canonical_points]

    first = voxel_cluster_world_positions(points, frame=real_frame, voxel_size=0.004)
    reversed_input = voxel_cluster_world_positions(
        list(reversed(points)), frame=real_frame, voxel_size=0.004
    )

    assert first == reversed_input
    assert len(first) == 3
    canonical_centroids = [real_frame.world_to_canonical(point) for point in first]
    expected = [
        (-0.001, 0.009, 0.010),
        (0.00125, 0.00125, 0.02025),
        (0.010, 0.010, 0.030),
    ]
    for actual, target in zip(canonical_centroids, expected):
        assert actual == pytest.approx(target)


def test_proxy_frame_reports_presentation_and_source_counts(real_frame):
    from tools.labutopia_fluid.omniglass_reference import (
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    points = [
        real_frame.canonical_to_world((0.001, 0.001, 0.02)),
        real_frame.canonical_to_world((0.0015, 0.0015, 0.0205)),
        real_frame.canonical_to_world((0.010, 0.010, 0.03)),
    ]
    candidate = build_reference_candidates(0.064)["OMNI_REF_RATIO_15"]

    proxy = build_presentation_proxy_frame(
        points,
        frame=real_frame,
        candidate=candidate,
    )

    assert proxy["proxy_count"] == 2
    assert proxy["source_physical_point_count"] == 3
    assert proxy["display_width"] == pytest.approx(0.064 / 15)
    assert proxy["voxel_size"] == pytest.approx(0.064 / 15)
    assert proxy["width_to_interior_ratio"] == pytest.approx(1 / 15)
    assert len(proxy["positions_world"]) == proxy["proxy_count"]


def test_presentation_points_are_render_only_and_bind_requested_material():
    from tools.labutopia_fluid.omniglass_reference import author_presentation_points

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, "/World/Looks/A18OmniGlass")

    prim = author_presentation_points(
        stage,
        path="/World/CompletedPBD/PresentationParticleSet",
        positions=[(0.0, 0.0, 0.02)],
        display_width=0.004,
        material_path=str(material.GetPath()),
    )

    assert prim.GetTypeName() == "Points"
    assert not any("physx" in token.lower() for token in prim.GetAppliedSchemas())
    assert not any(
        relationship.GetName().lower().startswith("physx")
        for relationship in prim.GetRelationships()
    )
    assert not prim.HasRelationship("physxParticle:particleSystem")
    assert not prim.GetAttribute("velocities").HasAuthoredValueOpinion()
    points = UsdGeom.Points(prim)
    assert list(points.GetWidthsAttr().Get()) == pytest.approx([0.004])
    bound, _relationship = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    assert bound.GetPath() == material.GetPath()


def test_hiding_source_visuals_does_not_author_physics_attributes():
    from tools.labutopia_fluid import run_real_beaker_omniglass_replay as replay

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    physical_points = UsdGeom.Points.Define(
        stage, "/World/CompletedPBD/ParticleSet"
    ).GetPrim()
    unrelated_points = UsdGeom.Points.Define(stage, "/World/DecorationPoints")
    enabled = physical_points.CreateAttribute(
        "particleSystemEnabled", Sdf.ValueTypeNames.Bool
    )
    enabled.Set(True)
    contact_offset = physical_points.CreateAttribute(
        "physxParticleSystem:particleContactOffset", Sdf.ValueTypeNames.Float
    )
    contact_offset.Set(0.001)

    result = replay.hide_physical_and_debug_points(stage)

    assert UsdGeom.Imageable(physical_points).ComputeVisibility() == "invisible"
    assert unrelated_points.ComputeVisibility() == "inherited"
    assert enabled.Get() is True
    assert contact_offset.Get() == pytest.approx(0.001)
    assert result["physics_attributes_authored"] is False


def _diagnostic_summary(log_path, *, byte_offset, payload):
    segment = {
        "log_path": str(log_path),
        "byte_offset": byte_offset,
        "cursor_captured": True,
        "diagnostic_scan_complete": True,
        "segment_byte_count": len(payload),
        "segment_sha256": hashlib.sha256(payload).hexdigest(),
    }
    return {
        "strict_kit_log_segment": segment,
        "isaac_log_summary": {
            **segment,
            "isaac_log_path": str(log_path),
            "isaac_log_available": True,
            "run_segment_only": True,
        },
    }


def test_diagnostic_validation_reads_exact_declared_relative_log_segment(tmp_path):
    from tools.labutopia_fluid import run_real_beaker_omniglass_replay as replay

    prefix = b"previous run\n"
    payload = b"accepted run diagnostics\n"
    log_path = tmp_path / "kit.log"
    log_path.write_bytes(prefix + payload + b"later run\n")
    summary = _diagnostic_summary("kit.log", byte_offset=len(prefix), payload=payload)

    replay._validate_run_scoped_diagnostics(
        summary, summary_path=tmp_path / "accepted_summary.json"
    )


@pytest.mark.parametrize("failure", ["missing", "truncated", "hash_mismatch"])
def test_diagnostic_validation_fails_closed_for_unverifiable_segment(
    tmp_path, failure
):
    from tools.labutopia_fluid import run_real_beaker_omniglass_replay as replay

    payload = b"accepted run diagnostics\n"
    log_path = tmp_path / "kit.log"
    summary = _diagnostic_summary("kit.log", byte_offset=0, payload=payload)
    if failure == "truncated":
        log_path.write_bytes(payload[:-1])
    elif failure == "hash_mismatch":
        log_path.write_bytes(b"X" + payload[1:])

    with pytest.raises(
        (FileNotFoundError, ValueError),
        match="diagnostic|kit_log|missing",
    ):
        replay._validate_run_scoped_diagnostics(
            summary, summary_path=tmp_path / "accepted_summary.json"
        )
