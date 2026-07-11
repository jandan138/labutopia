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
