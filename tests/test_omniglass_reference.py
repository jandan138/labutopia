import hashlib
import math

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
    from tools.labutopia_fluid.omniglass_reference import (
        PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        PRESENTATION_ONLY_VOLUME_DISCLAIMER,
        build_reference_candidates,
    )

    candidates = build_reference_candidates(interior_diameter=0.064)

    assert list(candidates) == [
        "OMNI_REF_FINE",
        "OMNI_REF_RATIO_15",
        "OMNI_REF_RATIO_12",
        "OMNI_REF_SURFACE",
        "OMNI_REF_DISPLAY_FILL",
    ]
    assert candidates["OMNI_REF_FINE"]["display_width"] == pytest.approx(0.002)
    assert candidates["OMNI_REF_RATIO_15"]["display_width"] == pytest.approx(0.064 / 15)
    assert candidates["OMNI_REF_RATIO_12"]["display_width"] == pytest.approx(0.064 / 12)
    assert all(
        candidate["voxel_size"] == candidate["display_width"]
        for candidate in candidates.values()
        if candidate["presentation_kind"] == "points"
    )
    surface = candidates["OMNI_REF_SURFACE"]
    assert surface["presentation_kind"] == "surface_mesh"
    assert surface["display_width"] == pytest.approx(0.002)
    assert surface["display_padding_xy"] == pytest.approx(0.001)
    assert surface["display_padding_z"] == pytest.approx(0.0005)
    assert surface["latitude_segments"] == 24
    assert surface["longitude_segments"] == 64
    assert surface["voxel_size"] is None
    display_fill = candidates["OMNI_REF_DISPLAY_FILL"]
    assert display_fill["presentation_kind"] == "surface_mesh"
    assert display_fill["display_width"] == pytest.approx(0.064 / 15)
    assert display_fill["surface_model_version"] == (
        "a18_display_proxy_rounded_cylinder_v1"
    )
    assert len(display_fill["surface_model_contract_sha256"]) == 64
    assert display_fill["radial_segments"] == 96
    assert display_fill["wall_clearance"] == pytest.approx((0.064 / 15) / 2)
    assert display_fill["floor_clearance"] == pytest.approx((0.064 / 15) / 8)
    assert display_fill["rim_clearance"] == pytest.approx((0.064 / 15) / 4)
    assert display_fill["edge_rounding"] == pytest.approx((0.064 / 15) / 4)
    assert display_fill["voxel_size"] is None
    for candidate in candidates.values():
        assert candidate["physical_volume_parity_claim_allowed"] is False
        assert candidate["free_surface_shape_claim_allowed"] is False
        assert candidate["fluid_dynamics_claim_allowed"] is False
        assert (
            candidate["presentation_only_volume_disclaimer"]
            == PRESENTATION_ONLY_VOLUME_DISCLAIMER
        )
        assert (
            candidate["presentation_only_shape_disclaimer"]
            == PRESENTATION_ONLY_SHAPE_DISCLAIMER
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
        PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        PRESENTATION_ONLY_VOLUME_DISCLAIMER,
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
    assert proxy["physical_volume_parity_claim_allowed"] is False
    assert proxy["free_surface_shape_claim_allowed"] is False
    assert proxy["fluid_dynamics_claim_allowed"] is False
    assert (
        proxy["presentation_only_volume_disclaimer"]
        == PRESENTATION_ONLY_VOLUME_DISCLAIMER
    )
    assert (
        proxy["presentation_only_shape_disclaimer"]
        == PRESENTATION_ONLY_SHAPE_DISCLAIMER
    )


def test_presentation_points_are_render_only_and_bind_requested_material():
    from tools.labutopia_fluid.omniglass_reference import (
        PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        PRESENTATION_ONLY_VOLUME_DISCLAIMER,
        author_presentation_points,
    )

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
    assert prim.GetAttribute("labutopia:presentationOnly").Get() is True
    assert prim.GetAttribute("labutopia:physicsSchemaAllowed").Get() is False
    assert (
        prim.GetAttribute("labutopia:physicalVolumeParityClaimAllowed").Get()
        is False
    )
    assert prim.GetAttribute("labutopia:freeSurfaceShapeClaimAllowed").Get() is False
    assert prim.GetAttribute("labutopia:fluidDynamicsClaimAllowed").Get() is False
    assert (
        prim.GetAttribute("labutopia:presentationOnlyVolumeDisclaimer").Get()
        == PRESENTATION_ONLY_VOLUME_DISCLAIMER
    )
    assert (
        prim.GetAttribute("labutopia:presentationOnlyShapeDisclaimer").Get()
        == PRESENTATION_ONLY_SHAPE_DISCLAIMER
    )
    points = UsdGeom.Points(prim)
    assert list(points.GetWidthsAttr().Get()) == pytest.approx([0.004])
    bound, _relationship = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    assert bound.GetPath() == material.GetPath()


def _surface_fixture_points(frame):
    canonical = [
        (-0.002, -0.004, 0.001),
        (0.006, -0.004, 0.005),
        (-0.002, 0.002, 0.005),
        (0.006, 0.002, 0.001),
        (0.001, -0.001, 0.003),
    ]
    return [frame.canonical_to_world(point) for point in canonical]


def _display_fill_fixture_points(frame, *, count=4096, layout="compact"):
    points = []
    for index in range(count):
        x_index = index % 16
        y_index = (index // 16) % 16
        z_index = (index // 256) % 16
        if layout == "compact":
            canonical = (
                (x_index - 7.5) * 0.001,
                (y_index - 7.5) * 0.001,
                0.002 + z_index * 0.001,
            )
        elif layout == "spread":
            angle = 2.0 * math.pi * ((index * 37) % count) / count
            ring = 0.010 + 0.008 * ((index % 17) / 16.0)
            canonical = (
                ring * math.cos(angle),
                ring * math.sin(angle),
                0.003 + 0.020 * ((index % 23) / 22.0),
            )
        else:
            raise AssertionError(f"unknown test layout: {layout}")
        points.append(frame.canonical_to_world(canonical))
    return points


def _independent_signed_mesh_volume(points, counts, indices):
    volume = 0.0
    cursor = 0
    for count in counts:
        face = indices[cursor : cursor + count]
        cursor += count
        for offset in range(1, count - 1):
            first = points[face[0]]
            second = points[face[offset]]
            third = points[face[offset + 1]]
            cross = (
                second[1] * third[2] - second[2] * third[1],
                second[2] * third[0] - second[0] * third[2],
                second[0] * third[1] - second[1] * third[0],
            )
            volume += (
                first[0] * cross[0]
                + first[1] * cross[1]
                + first[2] * cross[2]
            ) / 6.0
    return volume


def test_display_fill_uses_exact_a18_proxy_volume_and_closed_rounded_cylinder(
    real_frame,
):
    from tools.labutopia_fluid.omniglass_reference import (
        DISPLAY_FILL_MODEL_VERSION,
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    candidate = build_reference_candidates(0.064)["OMNI_REF_DISPLAY_FILL"]
    proxy = build_presentation_proxy_frame(
        _display_fill_fixture_points(real_frame),
        frame=real_frame,
        candidate=candidate,
        nominal_physical_particle_width=0.00045,
    )

    display_width = 0.064 / 15.0
    fill_radius = 0.032 - display_width / 2.0
    edge_rounding = display_width / 4.0
    cap_radius = fill_radius - edge_rounding
    coefficient = 0.5 * 96 * math.sin(2.0 * math.pi / 96)
    proxy_volume = 4096 * 4.0 * math.pi * (display_width / 2.0) ** 3 / 3.0
    edge_volume = (
        coefficient
        * edge_rounding
        * (fill_radius**2 + fill_radius * cap_radius + cap_radius**2)
        / 3.0
    )
    expected_height = (
        2.0 * edge_rounding
        + (proxy_volume - 2.0 * edge_volume)
        / (coefficient * fill_radius**2)
    )

    assert proxy["candidate_id"] == "OMNI_REF_DISPLAY_FILL"
    assert proxy["surface_model_version"] == DISPLAY_FILL_MODEL_VERSION
    assert proxy["display_width"] == pytest.approx(display_width)
    assert proxy["display_fill_radius_m"] == pytest.approx(fill_radius)
    assert proxy["display_fill_cap_radius_m"] == pytest.approx(cap_radius)
    assert proxy["display_fill_height_m"] == pytest.approx(expected_height, rel=2e-6)
    assert proxy["display_proxy_aggregate_sphere_volume_m3"] == pytest.approx(
        proxy_volume
    )
    assert proxy["mesh_enclosed_volume_m3"] == pytest.approx(proxy_volume, rel=5e-6)
    assert proxy["mesh_to_display_proxy_volume_relative_error"] <= 5e-6
    assert proxy["source_layout_affects_geometry"] is False
    assert proxy["nominal_physical_particle_width_affects_geometry"] is False
    assert proxy["vertex_count"] == 386
    assert proxy["face_count"] == 480
    assert proxy["topology"]["closed_two_face_edge_incidence"] is True
    assert proxy["topology"]["opposite_directed_edge_incidence"] is True
    assert proxy["topology"]["index_bounds_verified"] is True
    assert proxy["topology"]["euler_characteristic"] == 2
    assert proxy["topology"]["outward_winding_verified"] is True
    assert proxy["analytic_normal_contract_verified"] is True
    assert proxy["containment"]["all_source_points_inside"] is True
    assert proxy["containment"]["all_mesh_vertices_inside"] is True
    assert proxy["containment"]["minimum_mesh_z"] > real_frame.interior_floor
    assert proxy["containment"]["maximum_mesh_z"] < real_frame.rim_height
    independent_volume = _independent_signed_mesh_volume(
        proxy["positions_canonical"],
        proxy["face_vertex_counts"],
        proxy["face_vertex_indices"],
    )
    assert independent_volume == pytest.approx(proxy_volume, rel=5e-6)
    assert proxy["physical_volume_parity_claim_allowed"] is False
    assert proxy["free_surface_shape_claim_allowed"] is False
    assert proxy["fluid_dynamics_claim_allowed"] is False


def test_display_fill_geometry_depends_on_count_and_cup_not_layout_or_physical_width(
    real_frame,
):
    from tools.labutopia_fluid.omniglass_reference import (
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    candidate = build_reference_candidates(0.064)["OMNI_REF_DISPLAY_FILL"]
    compact = build_presentation_proxy_frame(
        _display_fill_fixture_points(real_frame, layout="compact"),
        frame=real_frame,
        candidate=candidate,
        nominal_physical_particle_width=0.00045,
    )
    spread = build_presentation_proxy_frame(
        _display_fill_fixture_points(real_frame, layout="spread"),
        frame=real_frame,
        candidate=candidate,
        nominal_physical_particle_width=0.0006,
    )

    assert compact["canonical_mesh_sha256"] == spread["canonical_mesh_sha256"]
    assert compact["surface_model_contract_sha256"] == spread[
        "surface_model_contract_sha256"
    ]
    assert compact["positions_canonical"] == spread["positions_canonical"]
    assert compact["display_fill_height_m"] == pytest.approx(
        spread["display_fill_height_m"]
    )
    assert compact["source_unique_canonical_position_set_sha256"] != spread[
        "source_unique_canonical_position_set_sha256"
    ]
    assert compact["nominal_disjoint_particle_volume_m3"] != spread[
        "nominal_disjoint_particle_volume_m3"
    ]


def test_display_fill_rejects_rounded_profile_underflow_and_one_count_overflow(
    real_frame,
):
    from tools.labutopia_fluid.omniglass_reference import (
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    candidate = build_reference_candidates(0.064)["OMNI_REF_DISPLAY_FILL"]
    with pytest.raises(ValueError, match="display_fill_proxy_volume_underflow"):
        build_presentation_proxy_frame(
            _surface_fixture_points(real_frame)[:4],
            frame=real_frame,
            candidate=candidate,
            nominal_physical_particle_width=0.00045,
        )

    display_width = candidate["display_width"]
    fill_radius = real_frame.interior_radius - candidate["wall_clearance"]
    edge = candidate["edge_rounding"]
    cap_radius = fill_radius - edge
    coefficient = candidate["regular_polygon_area_coefficient"]
    edge_volume = (
        coefficient
        * edge
        * (fill_radius**2 + fill_radius * cap_radius + cap_radius**2)
        / 3.0
    )
    available_height = (
        real_frame.rim_height
        - candidate["rim_clearance"]
        - real_frame.interior_floor
        - candidate["floor_clearance"]
    )
    maximum_volume = (
        coefficient * fill_radius**2 * (available_height - 2.0 * edge)
        + 2.0 * edge_volume
    )
    sphere_volume = 4.0 * math.pi * (display_width / 2.0) ** 3 / 3.0
    maximum_count = math.floor(maximum_volume / sphere_volume)

    accepted = build_presentation_proxy_frame(
        _display_fill_fixture_points(real_frame, count=maximum_count),
        frame=real_frame,
        candidate=candidate,
        nominal_physical_particle_width=0.00045,
    )
    assert accepted["containment"]["maximum_mesh_z"] <= (
        real_frame.rim_height - candidate["rim_clearance"] + 2e-7
    )
    with pytest.raises(ValueError, match="display_fill_overflow"):
        build_presentation_proxy_frame(
            _display_fill_fixture_points(real_frame, count=maximum_count + 1),
            frame=real_frame,
            candidate=candidate,
            nominal_physical_particle_width=0.00045,
        )


def test_display_fill_rejects_candidate_frame_diameter_mismatch(real_frame):
    from tools.labutopia_fluid.omniglass_reference import (
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    candidate = build_reference_candidates(0.063)["OMNI_REF_DISPLAY_FILL"]
    with pytest.raises(ValueError, match="display_fill_candidate_frame_diameter_mismatch"):
        build_presentation_proxy_frame(
            _display_fill_fixture_points(real_frame),
            frame=real_frame,
            candidate=candidate,
            nominal_physical_particle_width=0.00045,
        )


def test_display_fill_is_invariant_under_arbitrary_rigid_cup_transform(real_frame):
    from tools.labutopia_fluid.omniglass_reference import (
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    axis = (1.0, 2.0, 3.0)
    axis_length = math.sqrt(sum(value * value for value in axis))
    unit_axis = tuple(value / axis_length for value in axis)
    angle = 0.73

    def rotate(vector):
        cosine = math.cos(angle)
        sine = math.sin(angle)
        cross = (
            unit_axis[1] * vector[2] - unit_axis[2] * vector[1],
            unit_axis[2] * vector[0] - unit_axis[0] * vector[2],
            unit_axis[0] * vector[1] - unit_axis[1] * vector[0],
        )
        dot = sum(unit_axis[index] * vector[index] for index in range(3))
        return tuple(
            vector[index] * cosine
            + cross[index] * sine
            + unit_axis[index] * dot * (1.0 - cosine)
            for index in range(3)
        )

    tilted = CupInteriorFrame(
        origin_world=(-0.7, 1.3, 0.4),
        x_axis_world=rotate((1.0, 0.0, 0.0)),
        y_axis_world=rotate((0.0, 1.0, 0.0)),
        z_axis_world=rotate((0.0, 0.0, 1.0)),
        parent_local_axis="Y",
        outer_radius=real_frame.outer_radius,
        interior_radius=real_frame.interior_radius,
        outer_floor=real_frame.outer_floor,
        interior_floor=real_frame.interior_floor,
        rim_height=real_frame.rim_height,
        calibration_source="arbitrary_rigid_transform_fixture",
        axis_alignment_dot=1.0,
    )
    candidate = build_reference_candidates(0.064)["OMNI_REF_DISPLAY_FILL"]
    identity = build_presentation_proxy_frame(
        _display_fill_fixture_points(real_frame),
        frame=real_frame,
        candidate=candidate,
        nominal_physical_particle_width=0.00045,
    )
    transformed = build_presentation_proxy_frame(
        _display_fill_fixture_points(tilted),
        frame=tilted,
        candidate=candidate,
        nominal_physical_particle_width=0.00045,
    )

    assert identity["canonical_mesh_sha256"] == transformed[
        "canonical_mesh_sha256"
    ]
    assert identity["positions_canonical"] == transformed["positions_canonical"]
    assert identity["positions_world"] != transformed["positions_world"]
    for canonical_normal, world_normal in zip(
        transformed["normals_canonical"], transformed["normals_world"]
    ):
        recovered = tuple(
            sum(world_normal[index] * basis[index] for index in range(3))
            for basis in (
                tilted.x_axis_world,
                tilted.y_axis_world,
                tilted.z_axis_world,
            )
        )
        assert recovered == pytest.approx(canonical_normal, abs=2e-6)


def test_display_fill_authors_model_identity_and_right_handed_mesh(real_frame):
    from tools.labutopia_fluid.omniglass_reference import (
        author_presentation_surface,
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    proxy = build_presentation_proxy_frame(
        _display_fill_fixture_points(real_frame),
        frame=real_frame,
        candidate=build_reference_candidates(0.064)["OMNI_REF_DISPLAY_FILL"],
        nominal_physical_particle_width=0.00045,
    )
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, "/World/Looks/A18OmniGlass")

    prim = author_presentation_surface(
        stage,
        path="/World/CompletedPBD/PresentationSurface",
        surface_frame=proxy,
        material_path=str(material.GetPath()),
    )
    mesh = UsdGeom.Mesh(prim)

    assert mesh.GetOrientationAttr().Get() == UsdGeom.Tokens.rightHanded
    assert prim.GetAttribute("labutopia:surfaceModelVersion").Get() == proxy[
        "surface_model_version"
    ]
    assert prim.GetAttribute("labutopia:surfaceModelContractSha256").Get() == proxy[
        "surface_model_contract_sha256"
    ]
    assert prim.GetAttribute(
        "labutopia:displayProxyAggregateSphereVolumeM3"
    ).Get() == pytest.approx(proxy["display_proxy_aggregate_sphere_volume_m3"])
    assert prim.GetAttribute("labutopia:meshEnclosedVolumeM3").Get() == pytest.approx(
        proxy["mesh_enclosed_volume_m3"]
    )
    assert prim.GetAttribute("labutopia:displayFillHeightM").Get() == pytest.approx(
        proxy["display_fill_height_m"]
    )


def test_surface_envelope_is_deterministic_closed_and_cup_contained(real_frame):
    from tools.labutopia_fluid.omniglass_reference import (
        PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        PRESENTATION_ONLY_VOLUME_DISCLAIMER,
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    candidate = build_reference_candidates(0.064)["OMNI_REF_SURFACE"]
    points = _surface_fixture_points(real_frame)

    first = build_presentation_proxy_frame(
        points,
        frame=real_frame,
        candidate=candidate,
        nominal_physical_particle_width=0.00045,
    )
    reversed_input = build_presentation_proxy_frame(
        list(reversed(points)),
        frame=real_frame,
        candidate=candidate,
        nominal_physical_particle_width=0.00045,
    )

    assert first["presentation_kind"] == "surface_mesh"
    assert first["canonical_mesh_sha256"] == reversed_input[
        "canonical_mesh_sha256"
    ]
    assert first["canonical_center"] == pytest.approx([0.002, -0.001, 0.003])
    assert first["canonical_semi_axes"] == pytest.approx(
        [0.005, 0.004, 0.0025]
    )
    assert first["vertex_count"] == 1474
    assert first["face_count"] == 1536
    assert first["topology"]["closed_two_face_edge_incidence"] is True
    assert first["topology"]["euler_characteristic"] == 2
    assert first["topology"]["outward_winding_verified"] is True
    assert first["topology"]["minimum_triangle_area_m2"] > 1e-12
    assert first["containment"]["all_source_points_inside"] is True
    assert first["containment"]["all_mesh_vertices_inside"] is True
    assert first["physics_schema_allowed"] is False
    assert first["physical_volume_parity_claim_allowed"] is False
    assert first["presentation_only_volume_disclaimer"] == (
        PRESENTATION_ONLY_VOLUME_DISCLAIMER
    )
    assert first["presentation_only_shape_disclaimer"] == (
        PRESENTATION_ONLY_SHAPE_DISCLAIMER
    )
    assert first["free_surface_shape_claim_allowed"] is False
    assert first["fluid_dynamics_claim_allowed"] is False
    assert first["display_volume_m3"] > 0.0
    assert first["nominal_disjoint_particle_volume_m3"] > 0.0
    assert first["display_to_nominal_particle_volume_ratio"] > 1.0


def test_surface_envelope_canonical_hash_is_rigid_transform_invariant(real_frame):
    from tools.labutopia_fluid.omniglass_reference import (
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    rotated = CupInteriorFrame(
        origin_world=(-0.7, 1.2, 0.4),
        x_axis_world=(math.sqrt(0.5), math.sqrt(0.5), 0.0),
        y_axis_world=(-math.sqrt(0.5), math.sqrt(0.5), 0.0),
        z_axis_world=(0.0, 0.0, 1.0),
        parent_local_axis="Y",
        outer_radius=real_frame.outer_radius,
        interior_radius=real_frame.interior_radius,
        outer_floor=real_frame.outer_floor,
        interior_floor=real_frame.interior_floor,
        rim_height=real_frame.rim_height,
        calibration_source="rotated_test_fixture",
        axis_alignment_dot=1.0,
    )
    canonical = [real_frame.world_to_canonical(point) for point in _surface_fixture_points(real_frame)]
    candidate = build_reference_candidates(0.064)["OMNI_REF_SURFACE"]

    identity_mesh = build_presentation_proxy_frame(
        [real_frame.canonical_to_world(point) for point in canonical],
        frame=real_frame,
        candidate=candidate,
        nominal_physical_particle_width=0.00045,
    )
    rotated_mesh = build_presentation_proxy_frame(
        [rotated.canonical_to_world(point) for point in canonical],
        frame=rotated,
        candidate=candidate,
        nominal_physical_particle_width=0.00045,
    )

    assert identity_mesh["canonical_mesh_sha256"] == rotated_mesh[
        "canonical_mesh_sha256"
    ]
    for identity_point, rotated_point in zip(
        identity_mesh["positions_world"], rotated_mesh["positions_world"]
    ):
        assert rotated.world_to_canonical(rotated_point) == pytest.approx(
            real_frame.world_to_canonical(identity_point), abs=1e-6
        )


@pytest.mark.parametrize(
    "canonical_points,error_code",
    [
        ([], "surface_source_point_count_below_four"),
        (
            [(0.0, 0.0, 0.01)] * 4,
            "surface_unique_point_count_below_four",
        ),
        (
            [(0.0, 0.0, 0.01), (0.001, 0.001, 0.01), (0.002, 0.002, 0.01), (0.003, 0.003, 0.01)],
            "surface_footprint_degenerate",
        ),
        (
            [(0.0, 0.0, 0.01), (0.001, 0.0, 0.01), (0.0, 0.001, 0.01), (float("nan"), 0.0, 0.01)],
            "position_nonfinite",
        ),
        (
            [(0.0, 0.0, 0.01), (0.001, 0.0, 0.01), (0.0, 0.001, 0.01), (0.04, 0.0, 0.01)],
            "surface_source_point_outside_cup",
        ),
    ],
)
def test_surface_envelope_rejects_invalid_or_misleading_inputs(
    real_frame, canonical_points, error_code
):
    from tools.labutopia_fluid.omniglass_reference import (
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    candidate = build_reference_candidates(0.064)["OMNI_REF_SURFACE"]
    points = [real_frame.canonical_to_world(point) for point in canonical_points]

    with pytest.raises(ValueError, match=error_code):
        build_presentation_proxy_frame(
            points,
            frame=real_frame,
            candidate=candidate,
            nominal_physical_particle_width=0.00045,
        )


def test_presentation_surface_is_render_only_and_binds_requested_material(real_frame):
    from tools.labutopia_fluid.omniglass_reference import (
        PRESENTATION_ONLY_SHAPE_DISCLAIMER,
        author_presentation_surface,
        build_presentation_proxy_frame,
        build_reference_candidates,
    )

    frame = build_presentation_proxy_frame(
        _surface_fixture_points(real_frame),
        frame=real_frame,
        candidate=build_reference_candidates(0.064)["OMNI_REF_SURFACE"],
        nominal_physical_particle_width=0.00045,
    )
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, "/World/Looks/A18OmniGlass")

    prim = author_presentation_surface(
        stage,
        path="/World/CompletedPBD/PresentationSurface",
        surface_frame=frame,
        material_path=str(material.GetPath()),
    )

    assert prim.GetTypeName() == "Mesh"
    assert not any("physx" in token.lower() for token in prim.GetAppliedSchemas())
    assert not any(
        relationship.GetName().lower().startswith("physx")
        for relationship in prim.GetRelationships()
    )
    mesh = UsdGeom.Mesh(prim)
    assert len(mesh.GetPointsAttr().Get()) == frame["vertex_count"]
    assert len(mesh.GetFaceVertexCountsAttr().Get()) == frame["face_count"]
    assert mesh.GetNormalsInterpolation() == UsdGeom.Tokens.vertex
    bound, _relationship = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    assert bound.GetPath() == material.GetPath()
    assert prim.GetAttribute("labutopia:freeSurfaceShapeClaimAllowed").Get() is False
    assert prim.GetAttribute("labutopia:fluidDynamicsClaimAllowed").Get() is False
    assert prim.GetAttribute("labutopia:presentationOnlyShapeDisclaimer").Get() == (
        PRESENTATION_ONLY_SHAPE_DISCLAIMER
    )


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
