import math
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCENE = (
    REPO_ROOT
    / "outputs/usd_asset_packages/lab_001_level1_pour_support_aligned_v1_20260712"
    / "lab_001_level1_pour_support_aligned_v1.usda"
)


def _require_source_scene():
    if not SOURCE_SCENE.is_file():
        pytest.skip(f"requires local support-aligned delivery: {SOURCE_SCENE}")


def _module():
    from tools.labutopia_fluid import run_interndata_pour_parity_probe as probe

    return probe


def _real_source_frame():
    _require_source_scene()
    from pxr import Usd
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    stage = Usd.Stage.Open(str(SOURCE_SCENE), Usd.Stage.LoadAll)
    assert stage is not None
    return derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        calibration_points_path="/World/ParticleSet",
    )


def _real_target_frame():
    _require_source_scene()
    from pxr import Usd
    from tools.labutopia_fluid.real_beaker import derive_cup_interior_frame

    stage = Usd.Stage.Open(str(SOURCE_SCENE), Usd.Stage.LoadAll)
    assert stage is not None
    return derive_cup_interior_frame(
        stage,
        parent_path="/World/beaker1",
        visual_mesh_path="/World/beaker1/mesh",
        calibration_points_path=None,
    )


def test_public_recipe_matches_intern_data_source_contract():
    probe = _module()

    recipe = probe.build_public_fluid_recipe()

    assert recipe["evidence_label"] == "public_fluid_recipe"
    assert recipe["grid_dims"] == [12, 12, 25]
    assert recipe["particle_count"] == 3600
    assert recipe["particle_contact_offset"] == pytest.approx(0.003)
    assert recipe["particle_spacing"] == pytest.approx(0.003)
    assert recipe["point_width"] == pytest.approx(0.003)
    assert recipe["physics_dt"] == pytest.approx(1.0 / 30.0)
    assert recipe["physics_substeps_per_frame"] == 4
    assert recipe["integration_dt"] == pytest.approx(1.0 / 120.0)
    assert recipe["setup_steps"] == 1
    assert recipe["pre_fluid_steps"] == 20
    assert recipe["post_fluid_steps"] == 150
    assert recipe["enable_ccd"] is True
    assert recipe["solver_position_iterations"] == 16
    assert recipe["max_neighborhood"] == 96
    assert recipe["neighborhood_scale"] == pytest.approx(1.01)
    assert recipe["max_velocity"] == pytest.approx(0.8)
    assert recipe["global_self_collision_enabled"] is True
    assert recipe["simulation_owner"] == "/World/PhysicsScene"
    assert recipe["isosurface"]["enabled"] is True
    assert recipe["isosurface"]["parameter_reference"] == "isaacsim41_cup_demo"
    assert recipe["smoothing"] == {"enabled": True, "strength": 50.0}
    assert recipe["runtime_smoothing_strength"] == pytest.approx(50.0)
    assert recipe["runtime_smoothing_strength"] == recipe["smoothing"]["strength"]
    assert recipe["anisotropy"] == {
        "enabled": True,
        "scale": 5.0,
        "minimum": 1.0,
        "maximum": 2.0,
    }
    assert recipe["pbd_material"] == {
        "cohesion": 0.01,
        "drag": 0.0,
        "lift": 0.0,
        "damping": 0.0,
        "friction": 0.1,
        "surface_tension": 0.0074,
        "viscosity": 0.0000017,
        "vorticity_confinement": 0.0,
    }
    assert recipe["visual_material"] == {
        "diffuse_color": [1.0, 1.0, 1.0],
        "emissive_color": [0.0, 0.0, 0.0],
        "metallic": 0.0,
        "roughness": 0.4,
        "opacity": 0.05,
    }
    assert recipe["runtime_visual_material_path"] == "/World/Looks/LiquidPresentationWater"
    assert recipe["runtime_visual_strategy"] == "offline_physx_readback_points_replay"
    assert recipe["delivery_visual_strategy"] == "physical_particle_prim"
    assert len(recipe["source_commit"]) == 40
    assert recipe["source_commit"].startswith("2a0a21f2")


def test_isosurface_contract_uses_isaacsim41_cup_demo_parameters():
    probe = _module()

    contract = probe.build_isosurface_contract(
        particle_contact_offset=0.003,
        particle_count=3600,
    )

    assert contract == {
        "enabled": True,
        "reference_fluid_rest_offset": pytest.approx(0.0015),
        "grid_spacing": pytest.approx(0.00135),
        "surface_distance": pytest.approx(0.001425),
        "grid_filtering_passes": "GS",
        "grid_smoothing_radius": pytest.approx(0.0015),
        "num_mesh_smoothing_passes": 4,
        "num_mesh_normal_smoothing_passes": 4,
        "max_vertices": 1024 * 1024,
        "max_triangles": 2 * 1024 * 1024,
        "max_subgrids": 4 * 1024,
        "parameter_reference": "isaacsim41_cup_demo",
        "affects_particle_physics": False,
    }


def test_visual_particle_proxy_contract_is_modest_and_physics_decoupled():
    probe = _module()

    contract = probe.build_visual_particle_proxy_contract(physical_width=0.003)

    assert contract == {
        "path": "/World/InternDataParityFluid/VisualParticles",
        "material_path": "/World/Looks/InternDataParticleWater",
        "physical_width": pytest.approx(0.003),
        "display_width": pytest.approx(0.003),
        "display_to_physical_ratio": pytest.approx(1.0),
        "position_source": "strict_physx_readback",
        "physics_coupled": False,
        "reference": "local_liquid_usd_points_style",
    }


def test_visual_particle_proxy_authors_render_only_points_from_physics_positions():
    probe = _module()
    from pxr import Usd, UsdGeom, UsdShade

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    positions = [(0.0, 0.0, 0.1), (0.003, 0.0, 0.1)]
    contract = probe.build_visual_particle_proxy_contract(physical_width=0.003)

    summary = probe.author_visual_particle_proxy(stage, positions, contract=contract)

    prim = stage.GetPrimAtPath(contract["path"])
    points = UsdGeom.Points(prim)
    assert prim.GetTypeName() == "Points"
    assert list(points.GetPointsAttr().Get()) == pytest.approx(positions)
    assert list(points.GetWidthsAttr().Get()) == pytest.approx([0.003, 0.003])
    assert points.GetPurposeAttr().Get() == UsdGeom.Tokens.render
    assert "PhysxParticleSetAPI" not in prim.GetAppliedSchemas()
    assert UsdShade.MaterialBindingAPI(prim).GetDirectBinding().GetMaterialPath() == contract[
        "material_path"
    ]
    assert summary["particle_count"] == 2
    assert summary["physics_coupled"] is False
    shader = UsdShade.Shader(
        stage.GetPrimAtPath("/World/Looks/InternDataParticleWater/PreviewSurface")
    )
    assert shader.GetIdAttr().Get() == "UsdPreviewSurface"
    assert shader.GetInput("opacity").Get() == pytest.approx(0.06)
    assert summary["material"]["backend"] == "USD_PREVIEW_SMALL_PARTICLE_WATER"
    assert summary["material"]["reference_material"] == "OmniGlass.mdl:OmniGlass"


def test_complete_public_grid_fits_real_beaker_with_contact_clearance():
    probe = _module()
    from tools.labutopia_fluid.real_beaker import classify_visible_beaker_positions

    frame = _real_source_frame()
    grid = probe.build_centered_public_grid(frame)

    assert len(grid["positions_world"]) == 3600
    assert len(grid["positions_canonical"]) == 3600
    assert grid["grid_dims"] == [12, 12, 25]
    assert grid["center_span_m"] == pytest.approx([0.033, 0.033, 0.072])
    assert grid["point_width_envelope_m"] == pytest.approx([0.036, 0.036, 0.075])
    assert grid["contact_clearance_envelope_m"] == pytest.approx([0.039, 0.039, 0.078])
    expected_z_mid = 0.5 * (frame.interior_floor + frame.rim_height) - 0.0005
    actual_z_mid = sum(point[2] for point in grid["positions_canonical"]) / len(
        grid["positions_canonical"]
    )
    assert grid["vertical_bias_m"] == pytest.approx(-0.0005)
    assert actual_z_mid == pytest.approx(expected_z_mid)
    assert grid["fit"]["fits"] is True
    assert grid["fit"]["radial_margin_m"] > 0.004
    assert grid["fit"]["floor_margin_m"] > 0.005
    assert grid["fit"]["rim_margin_m"] > 0.006
    assert grid["positions_sha256"]
    counts = classify_visible_beaker_positions(grid["positions_world"], frame)
    assert counts["inside_visible_interior_count"] == 3600
    assert counts["strict_violating_point_count"] == 0


def test_grid_preflight_rejects_beaker_that_cannot_hold_contact_envelope():
    probe = _module()
    from tools.labutopia_fluid.real_beaker import CupInteriorFrame

    frame = CupInteriorFrame(
        origin_world=(0.0, 0.0, 0.0),
        x_axis_world=(1.0, 0.0, 0.0),
        y_axis_world=(0.0, 1.0, 0.0),
        z_axis_world=(0.0, 0.0, 1.0),
        parent_local_axis="Z",
        outer_radius=0.021,
        interior_radius=0.020,
        outer_floor=0.0,
        interior_floor=0.0,
        rim_height=0.076,
        calibration_source="test",
        axis_alignment_dot=1.0,
    )

    with pytest.raises(ValueError, match="public_grid_contact_envelope_does_not_fit"):
        probe.build_centered_public_grid(frame)


def test_collider_contract_is_single_inferred_public_preprocess_hypothesis():
    probe = _module()

    contract = probe.build_inferred_collider_contract()

    assert contract == {
        "evidence_label": "inferred_collider_hypothesis",
        "approximation": "convexDecomposition",
        "max_convex_hulls": 64,
        "hull_vertex_limit": 64,
        "min_thickness": 0.001,
        "shrink_wrap": True,
        "error_percentage": 0.1,
        "static_friction": 1.0,
        "dynamic_friction": 1.0,
        "overlay_existing_prim": True,
        "second_collider_allowed": False,
    }


def test_collider_overlay_authors_exact_attributes_without_second_collider():
    probe = _module()
    from pxr import Usd, UsdGeom, UsdPhysics, UsdShade

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/beaker2")
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr([(0.0, 0.0, 0.0)])
    visual = UsdShade.Material.Define(stage, "/World/Looks/Glass")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(visual)
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim()).CreateCollisionEnabledAttr(True)
    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr(
        "convexDecomposition"
    )
    before_visual_targets = list(
        mesh.GetPrim().GetRelationship("material:binding").GetTargets()
    )

    result = probe.author_inferred_collider_overlay(
        stage,
        mesh_path="/World/beaker2/mesh",
        material_path="/World/PhysicsMaterials/InternDataCollider",
    )

    prim = mesh.GetPrim()
    assert result["mesh_path"] == "/World/beaker2/mesh"
    assert result["enabled_collision_prim_paths"] == ["/World/beaker2/mesh"]
    assert prim.GetAttribute("physics:approximation").Get() == "convexDecomposition"
    assert prim.GetAttribute(
        "physxConvexDecompositionCollision:maxConvexHulls"
    ).Get() == 64
    assert prim.GetAttribute(
        "physxConvexDecompositionCollision:hullVertexLimit"
    ).Get() == 64
    assert prim.GetAttribute(
        "physxConvexDecompositionCollision:minThickness"
    ).Get() == pytest.approx(0.001)
    assert prim.GetAttribute(
        "physxConvexDecompositionCollision:shrinkWrap"
    ).Get() is True
    assert prim.GetAttribute(
        "physxConvexDecompositionCollision:errorPercentage"
    ).Get() == pytest.approx(0.1)
    physics_material = stage.GetPrimAtPath("/World/PhysicsMaterials/InternDataCollider")
    material_api = UsdPhysics.MaterialAPI(physics_material)
    assert material_api.GetStaticFrictionAttr().Get() == pytest.approx(1.0)
    assert material_api.GetDynamicFrictionAttr().Get() == pytest.approx(1.0)
    assert list(prim.GetRelationship("material:binding").GetTargets()) == before_visual_targets
    assert list(prim.GetRelationship("material:binding:physics").GetTargets()) == [
        physics_material.GetPath()
    ]


def test_inner_wall_proxy_is_static_canonical_compound_for_hold():
    probe = _module()
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    parent = UsdGeom.Xform.Define(stage, "/World/beaker2")
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr([(0.0, 0.0, 0.0)])
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim()).CreateCollisionEnabledAttr(True)
    UsdPhysics.RigidBodyAPI.Apply(mesh.GetPrim()).CreateRigidBodyEnabledAttr(True)

    result = probe.author_inner_wall_collision_proxy(
        stage,
        frame=_test_frame((0.0, 0.0, 0.0)),
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
    )

    assert result["evidence_label"] == "explicit_open_inner_wall_proxy"
    assert result["shape"] == "gpu_native_boxes"
    assert result["panel_count"] == 72
    assert result["panel_ring_count"] == 2
    assert result["wall_thickness"] == pytest.approx(0.026)
    assert result["bottom_thickness"] == pytest.approx(0.012)
    assert result["bottom_overlap"] == pytest.approx(0.018)
    assert result["center_inset"] == pytest.approx(0.0015)
    assert result["visual_interior_radius"] == pytest.approx(0.05)
    assert result["panel_inner_radius"] == pytest.approx(0.0485)
    assert result["collider_count"] == 145
    assert result["open_top"] is True
    assert result["actor_path"] is None
    assert result["actor_paths"] == []
    assert result["actor_root_path"] is None
    assert result["actor_strategy"] == "static_canonical_compound_shapes"
    assert result["collider_paths"][0].endswith("/Bottom")
    assert not any("Top" in path for path in result["collider_paths"])
    assert mesh.GetPrim().GetAttribute("physics:collisionEnabled").Get() is False
    assert mesh.GetPrim().HasAPI(UsdPhysics.RigidBodyAPI)
    assert mesh.GetPrim().GetAttribute("physics:rigidBodyEnabled").Get() is True
    assert mesh.GetPrim().GetAttribute("physics:kinematicEnabled").Get() is True
    assert not parent.GetPrim().HasAPI(UsdPhysics.RigidBodyAPI)
    wrapper = stage.GetPrimAtPath(result["wrapper_path"])
    assert not wrapper.HasAPI(UsdPhysics.RigidBodyAPI)
    for path in result["collider_paths"]:
        collider = stage.GetPrimAtPath(path)
        assert not collider.HasAPI(UsdPhysics.RigidBodyAPI)
    assert probe._enabled_collision_paths(stage, "/World/beaker2") == sorted(
        result["collider_paths"]
    )


def test_inner_wall_proxy_uses_one_parent_compound_actor_for_kinematic_mode():
    probe = _module()
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    parent = UsdGeom.Xform.Define(stage, "/World/beaker2")
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    mesh.CreatePointsAttr([(0.0, 0.0, 0.0)])
    UsdPhysics.RigidBodyAPI.Apply(mesh.GetPrim()).CreateRigidBodyEnabledAttr(True)
    result = probe.author_inner_wall_collision_proxy(
        stage,
        frame=_test_frame((0.0, 0.0, 0.0)),
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        kinematic_actor=True,
    )

    assert result["actor_path"] == "/World/beaker2"
    assert result["actor_paths"] == ["/World/beaker2"]
    assert len(result["collider_paths"]) == 145
    assert result["actor_strategy"] == "parent_compound_kinematic_actor"
    assert result["kinematic_actor_enabled"] is True
    assert parent.GetPrim().HasAPI(UsdPhysics.RigidBodyAPI)
    assert parent.GetPrim().GetAttribute("physics:kinematicEnabled").Get() is True
    assert not mesh.GetPrim().HasAPI(UsdPhysics.RigidBodyAPI)


def test_kinematic_overlay_authors_only_source_as_actor_and_keeps_target_static(
    tmp_path,
):
    _require_source_scene()
    probe = _module()
    from pxr import Usd, UsdPhysics

    overlay_path = tmp_path / "kinematic_overlay.usda"
    result = probe._prepare_overlay(
        source_scene=SOURCE_SCENE,
        overlay_path=overlay_path,
        mode="kinematic",
        collider_mode="inner-wall",
    )
    stage = Usd.Stage.Open(str(overlay_path), Usd.Stage.LoadAll)

    assert stage is not None
    assert [
        collider["actor_path"]
        for collider in result["colliders"]
        if collider["actor_path"] is not None
    ] == ["/World/beaker2"]
    assert stage.GetPrimAtPath("/World/beaker2").HasAPI(UsdPhysics.RigidBodyAPI)
    assert not stage.GetPrimAtPath("/World/beaker1").HasAPI(
        UsdPhysics.RigidBodyAPI
    )
    target_collider = next(
        item
        for item in result["colliders"]
        if item["visual_mesh_path"] == "/World/beaker1/mesh"
    )
    assert target_collider["actor_path"] is None
    assert target_collider["actor_strategy"] == "static_canonical_compound_shapes"
    assert all(
        not stage.GetPrimAtPath(path).HasAPI(UsdPhysics.RigidBodyAPI)
        for path in target_collider["collider_paths"]
    )


def test_static_overlay_includes_same_static_target_proxy_as_kinematic_scene(
    tmp_path,
):
    _require_source_scene()
    probe = _module()

    result = probe._prepare_overlay(
        source_scene=SOURCE_SCENE,
        overlay_path=tmp_path / "static_overlay.usda",
        mode="static",
        collider_mode="inner-wall",
    )

    assert [item["visual_mesh_path"] for item in result["colliders"]] == [
        "/World/beaker2/mesh",
        "/World/beaker1/mesh",
    ]
    assert all(item["actor_path"] is None for item in result["colliders"])


def test_runtime_kinematic_rigid_paths_include_only_source_parent():
    probe = _module()

    assert probe.runtime_kinematic_rigid_paths(
        mode="kinematic",
        collider_mode="inner-wall",
    ) == ("/World/beaker2",)


def test_parent_actor_transform_consolidation_preserves_compound_actor_ownership():
    probe = _module()
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    parent = UsdGeom.Xform.Define(stage, "/World/beaker2")
    parent.AddTranslateOp().Set(Gf.Vec3d(0.2, 0.3, 0.4))
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh")
    UsdPhysics.RigidBodyAPI.Apply(mesh.GetPrim()).CreateRigidBodyEnabledAttr(True)

    result = probe._consolidate_parent_actor_transform(stage, "/World/beaker2")

    assert result["actor_path"] == "/World/beaker2"
    assert result["compound_child_colliders"] is True
    assert parent.GetPrim().HasAPI(UsdPhysics.RigidBodyAPI)
    assert parent.GetPrim().GetAttribute("physics:kinematicEnabled").Get() is True
    assert not mesh.GetPrim().HasAPI(UsdPhysics.RigidBodyAPI)
    assert result["initial_matrix"][3][:3] == pytest.approx([0.2, 0.3, 0.4])


def test_uniform_mesh_scale_bake_preserves_world_points_and_sets_unit_scale():
    probe = _module()
    from pxr import Gf, Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    parent = UsdGeom.Xform.Define(stage, "/World")
    parent.AddTranslateOp().Set(Gf.Vec3d(2.0, 3.0, 4.0))
    mesh = UsdGeom.Mesh.Define(stage, "/World/mesh")
    mesh.CreatePointsAttr([(2.0, 4.0, 6.0), (-2.0, 0.0, 2.0)])
    mesh.CreateExtentAttr([(-2.0, 0.0, 2.0), (2.0, 4.0, 6.0)])
    mesh.AddScaleOp().Set(Gf.Vec3f(0.5, 0.5, 0.5))
    before_transform = UsdGeom.XformCache().GetLocalToWorldTransform(mesh.GetPrim())
    before = [
        tuple(before_transform.Transform(Gf.Vec3d(*point)))
        for point in mesh.GetPointsAttr().Get()
    ]

    result = probe.bake_uniform_mesh_scale(stage, mesh_path="/World/mesh")

    after_transform = UsdGeom.XformCache().GetLocalToWorldTransform(mesh.GetPrim())
    after = [
        tuple(after_transform.Transform(Gf.Vec3d(*point)))
        for point in mesh.GetPointsAttr().Get()
    ]
    assert result["scale_baked"] is True
    assert result["uniform_scale"] == pytest.approx(0.5)
    assert before == pytest.approx(after)
    assert mesh.GetPrim().GetAttribute("xformOp:scale").Get() == Gf.Vec3f(1.0)
    assert mesh.GetPointsAttr().Get()[0] == Gf.Vec3f(1.0, 2.0, 3.0)
    assert mesh.GetExtentAttr().Get()[1] == Gf.Vec3f(1.0, 2.0, 3.0)


def test_public_material_binding_sequence_separates_physics_and_visual_purposes():
    probe = _module()
    from pxr import Usd, UsdGeom, UsdShade

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    system = UsdGeom.Xform.Define(stage, "/World/ParticleSystem")
    existing_visual = UsdShade.Material.Define(stage, "/World/Looks/Visual")
    shader = UsdShade.Shader.Define(stage, "/World/Looks/Visual/Shader")
    shader.CreateIdAttr("OmniGlass")

    summary = probe.author_public_material_binding_sequence(
        stage,
        prim=system.GetPrim(),
        pbd_material_path="/World/Looks/PBD",
        visual_material_path="/World/Looks/Visual",
    )

    assert summary["binding_order"] == [
        "/World/Looks/PBD",
        "/World/Looks/Visual",
    ]
    assert summary["effective_default_binding_targets"] == ["/World/Looks/Visual"]
    assert summary["effective_physics_binding_targets"] == ["/World/Looks/PBD"]
    assert summary["pbd_effective_physics_binding"] is True
    assert summary["visual_material_source"] == "existing_stage_material"
    assert not stage.GetPrimAtPath("/World/Looks/Visual/PreviewSurface")
    assert existing_visual.GetPrim().IsValid()


def test_physics_point_readback_prefers_simulation_points_over_smoothed_display_points():
    probe = _module()
    from pxr import Sdf, Usd, UsdGeom, Vt

    stage = Usd.Stage.CreateInMemory()
    points = UsdGeom.Points.Define(stage, "/World/Particles")
    points.CreatePointsAttr([(9.0, 9.0, 9.0)])
    points.GetPrim().CreateAttribute(
        "physxParticle:simulationPoints",
        Sdf.ValueTypeNames.Point3fArray,
        custom=False,
    ).Set(Vt.Vec3fArray([(1.0, 2.0, 3.0)]))

    result = probe.read_physics_particle_points(stage, "/World/Particles")

    assert result == [(1.0, 2.0, 3.0)]


def test_physics_point_readback_falls_back_before_simulation_points_exist():
    probe = _module()
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    points = UsdGeom.Points.Define(stage, "/World/Particles")
    points.CreatePointsAttr([(4.0, 5.0, 6.0)])

    result = probe.read_physics_particle_points(stage, "/World/Particles")

    assert result == [(4.0, 5.0, 6.0)]


def test_initial_simulation_points_are_authored_for_runtime_particle_insertion():
    probe = _module()
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    points = UsdGeom.Points.Define(stage, "/World/Particles")

    result = probe.author_initial_simulation_points(
        points.GetPrim(), [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]
    )

    assert result == {"authored": True, "particle_count": 2}
    assert probe.read_physics_particle_points(stage, "/World/Particles") == [
        (1.0, 2.0, 3.0),
        (4.0, 5.0, 6.0),
    ]


def test_replay_positions_restore_simulation_and_display_arrays():
    probe = _module()
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    points = UsdGeom.Points.Define(stage, "/World/Particles")
    points.CreatePointsAttr([(0.0, 0.0, 0.0)])
    probe.author_initial_simulation_points(points.GetPrim(), [(0.0, 0.0, 0.0)])

    result = probe.author_replay_particle_positions(
        stage,
        "/World/Particles",
        [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
    )

    assert result == {"particle_count": 2, "display_and_simulation_points_match": True}
    assert [tuple(point) for point in points.GetPointsAttr().Get()] == [
        (1.0, 2.0, 3.0),
        (4.0, 5.0, 6.0),
    ]
    simulation_points = points.GetPrim().GetAttribute(
        "physxParticle:simulationPoints"
    ).Get()
    assert [tuple(point) for point in simulation_points] == [
        (1.0, 2.0, 3.0),
        (4.0, 5.0, 6.0),
    ]

    points.GetPrim().RemoveProperty("points")
    points.GetPrim().RemoveProperty("physxParticle:simulationPoints")
    restored = probe.author_replay_particle_positions(
        stage, "/World/Particles", [(7.0, 8.0, 9.0)]
    )

    assert restored["display_and_simulation_points_match"] is True
    assert [tuple(point) for point in points.GetPointsAttr().Get()] == [
        (7.0, 8.0, 9.0)
    ]


def test_replay_positions_updates_runtime_point_instancer_canonical_positions():
    probe = _module()
    from pxr import Sdf, Usd, UsdGeom, Vt

    stage = Usd.Stage.CreateInMemory()
    instancer = UsdGeom.PointInstancer.Define(stage, "/World/Particles")
    UsdGeom.Sphere.Define(stage, "/World/Particles/pointPrototype")
    instancer.CreatePrototypesRel().SetTargets(
        [Sdf.Path("/World/Particles/pointPrototype")]
    )
    instancer.CreateProtoIndicesAttr().Set(Vt.IntArray([0, 0]))
    instancer.CreatePositionsAttr().Set(
        Vt.Vec3fArray([(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)])
    )
    instancer.GetPrim().CreateAttribute(
        "points", Sdf.ValueTypeNames.Point3fArray, custom=True
    ).Set(Vt.Vec3fArray([(9.0, 9.0, 9.0), (9.0, 9.0, 9.0)]))

    result = probe.author_replay_particle_positions(
        stage,
        "/World/Particles",
        [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
    )

    expected = [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]
    assert result["display_and_simulation_points_match"] is True
    assert [tuple(point) for point in instancer.GetPositionsAttr().Get()] == expected
    assert [
        tuple(point)
        for point in instancer.GetPrim()
        .GetAttribute("physxParticle:simulationPoints")
        .Get()
    ] == expected
    assert [
        tuple(point) for point in instancer.GetPrim().GetAttribute("points").Get()
    ] == expected


def test_delivery_visual_authority_uses_physical_particles_only():
    probe = _module()
    from pxr import Sdf, Usd, UsdGeom, UsdShade

    stage = Usd.Stage.CreateInMemory()
    world = UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Scope.Define(stage, probe.PARTICLE_SCOPE_PATH)
    system = stage.DefinePrim(probe.PARTICLE_SYSTEM_PATH, "PhysxParticleSystem")
    system.CreateAttribute(
        "physxParticleIsosurface:isosurfaceEnabled",
        Sdf.ValueTypeNames.Bool,
        custom=False,
    ).Set(True)
    physical = UsdGeom.Points.Define(stage, probe.PARTICLE_SET_PATH)
    physical.CreatePointsAttr([(1.0, 2.0, 3.0)])
    physical.CreateWidthsAttr([probe.PUBLIC_POINT_WIDTH])
    proxy = UsdGeom.Points.Define(stage, probe.VISUAL_PARTICLE_SET_PATH)
    proxy.CreatePointsAttr([(1.0, 2.0, 3.0)])
    probe._author_visual_particle_material(
        stage, probe.VISUAL_PARTICLE_MATERIAL_PATH
    )

    result = probe.configure_delivery_particle_visual_authority(stage)

    assert result["authority"] == "physical_particle_prim"
    assert result["physical_prim_type"] == "Points"
    assert result["offline_proxy_removed"] is True
    assert result["isosurface_disabled"] is True
    assert stage.GetDefaultPrim() == world.GetPrim()
    assert UsdGeom.Imageable(physical.GetPrim()).GetPurposeAttr().Get() == "render"
    assert not stage.GetPrimAtPath(probe.VISUAL_PARTICLE_SET_PATH).IsValid()
    assert (
        UsdShade.MaterialBindingAPI(physical.GetPrim())
        .GetDirectBinding()
        .GetMaterialPath()
        == probe.VISUAL_PARTICLE_MATERIAL_PATH
    )
    assert (
        system.GetAttribute("physxParticleIsosurface:isosurfaceEnabled").Get()
        is False
    )
    scope = stage.GetPrimAtPath(probe.PARTICLE_SCOPE_PATH)
    assert scope.GetAttribute("labutopia:deliverySnapshotOnly").Get() is True
    assert (
        scope.GetAttribute("labutopia:containsPrescribedPourAnimation").Get()
        is False
    )
    assert scope.GetAttribute("labutopia:externalControllerRequired").Get() is True
    assert (
        scope.GetAttribute("labutopia:sourceActorPath").Get()
        == "/World/beaker2"
    )


def test_delivery_visual_authority_normalizes_runtime_instancer_to_points():
    probe = _module()
    from pxr import Gf, Sdf, Usd, UsdGeom, Vt

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Scope.Define(stage, probe.PARTICLE_SCOPE_PATH)
    system = stage.DefinePrim(probe.PARTICLE_SYSTEM_PATH, "PhysxParticleSystem")
    system.CreateAttribute(
        "physxParticleIsosurface:isosurfaceEnabled",
        Sdf.ValueTypeNames.Bool,
        custom=False,
    ).Set(True)
    instancer = UsdGeom.PointInstancer.Define(stage, probe.PARTICLE_SET_PATH)
    expected = Vt.Vec3fArray(
        [Gf.Vec3f(1.0, 2.0, 3.0), Gf.Vec3f(4.0, 5.0, 6.0)]
    )
    instancer.CreatePositionsAttr().Set(expected)
    instancer.CreateProtoIndicesAttr().Set(Vt.IntArray([0, 0]))
    prototype = UsdGeom.Sphere.Define(
        stage, f"{probe.PARTICLE_SET_PATH}/pointPrototype"
    )
    instancer.CreatePrototypesRel().SetTargets([prototype.GetPath()])
    instancer.GetPrim().CreateAttribute(
        "physxParticle:simulationPoints",
        Sdf.ValueTypeNames.Point3fArray,
        custom=False,
    ).Set(expected)
    probe._author_visual_particle_material(
        stage, probe.VISUAL_PARTICLE_MATERIAL_PATH
    )

    result = probe.configure_delivery_particle_visual_authority(stage)

    physical = stage.GetPrimAtPath(probe.PARTICLE_SET_PATH)
    assert result["normalized_from_point_instancer"] is True
    assert physical.IsA(UsdGeom.Points)
    assert not physical.IsA(UsdGeom.PointInstancer)
    assert [tuple(point) for point in UsdGeom.Points(physical).GetPointsAttr().Get()] == [
        (1.0, 2.0, 3.0),
        (4.0, 5.0, 6.0),
    ]
    assert list(UsdGeom.Points(physical).GetWidthsAttr().Get()) == pytest.approx([
        probe.PUBLIC_POINT_WIDTH,
        probe.PUBLIC_POINT_WIDTH,
    ])
    assert not physical.GetAttribute("positions")
    assert not physical.GetAttribute("protoIndices")
    assert not physical.GetRelationship("prototypes")
    assert not stage.GetPrimAtPath(prototype.GetPath()).IsValid()


def test_delivery_snapshot_export_clears_dangling_material_bindings(tmp_path):
    probe = _module()
    from pxr import Sdf, Usd, UsdGeom, UsdShade

    source = tmp_path / "source.usda"
    target = tmp_path / "delivery.usda"
    stage = Usd.Stage.CreateNew(str(source))
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Scope.Define(stage, probe.PARTICLE_SCOPE_PATH)
    system = stage.DefinePrim(probe.PARTICLE_SYSTEM_PATH, "PhysxParticleSystem")
    system.CreateAttribute(
        "physxParticleIsosurface:isosurfaceEnabled",
        Sdf.ValueTypeNames.Bool,
        custom=False,
    ).Set(True)
    physical = UsdGeom.Points.Define(stage, probe.PARTICLE_SET_PATH)
    physical.CreatePointsAttr([(1.0, 2.0, 3.0)])
    physical.CreateWidthsAttr([probe.PUBLIC_POINT_WIDTH])
    proxy = UsdGeom.Points.Define(stage, probe.VISUAL_PARTICLE_SET_PATH)
    proxy.CreatePointsAttr([(1.0, 2.0, 3.0)])
    probe._author_visual_particle_material(
        stage, probe.VISUAL_PARTICLE_MATERIAL_PATH
    )
    mesh = UsdGeom.Mesh.Define(stage, "/World/Object")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).GetDirectBindingRel().SetTargets(
        [Sdf.Path("/World/Looks/Missing")]
    )
    stage.GetRootLayer().Save()

    result = probe.export_delivery_snapshot(source, target)
    reopened = Usd.Stage.Open(str(target), Usd.Stage.LoadAll)

    assert result["visual_authority"]["authority"] == "physical_particle_prim"
    assert result["dangling_material_bindings_removed"] == 1
    assert reopened.GetDefaultPrim().GetPath() == Sdf.Path("/World")
    assert not reopened.GetPrimAtPath(probe.VISUAL_PARTICLE_SET_PATH).IsValid()
    assert (
        UsdShade.MaterialBindingAPI(reopened.GetPrimAtPath("/World/Object"))
        .GetDirectBindingRel()
        .GetTargets()
        == []
    )


def test_particle_state_layer_export_uses_stabilized_display_and_physics_points(
    tmp_path,
):
    probe = _module()
    from pxr import Usd, UsdGeom

    source = tmp_path / "source.usda"
    target = tmp_path / "stabilized.usda"
    stage = Usd.Stage.CreateNew(str(source))
    UsdGeom.Xform.Define(stage, "/World")
    particles = UsdGeom.Points.Define(stage, probe.PARTICLE_SET_PATH)
    particles.CreatePointsAttr([(0.0, 0.0, 1.0)])
    stage.GetRootLayer().Save()
    stabilized = [(1.0, 2.0, 0.1), (4.0, 5.0, 0.2)]

    result = probe.export_particle_state_layer(stage, target, stabilized)
    reopened = Usd.Stage.Open(str(target), Usd.Stage.LoadAll)
    reopened_particles = UsdGeom.Points(
        reopened.GetPrimAtPath(probe.PARTICLE_SET_PATH)
    )

    assert result["particle_count"] == 2
    assert result["display_and_simulation_points_match"] is True
    assert result["source_stage_unchanged"] is True
    display_points = [
        tuple(point) for point in reopened_particles.GetPointsAttr().Get()
    ]
    simulation_points = [
        tuple(point)
        for point in reopened_particles.GetPrim()
        .GetAttribute("physxParticle:simulationPoints")
        .Get()
    ]
    assert len(display_points) == len(simulation_points) == len(stabilized)
    for display, simulation, expected in zip(
        display_points, simulation_points, stabilized
    ):
        assert display == pytest.approx(expected)
        assert simulation == pytest.approx(expected)
    assert [tuple(point) for point in particles.GetPointsAttr().Get()] == [
        (0.0, 0.0, 1.0)
    ]


def test_static_sampling_plan_records_authored_state_then_exactly_150_physx_steps():
    probe = _module()

    plan = probe.build_static_sampling_plan()

    assert [item["state_index"] for item in plan] == list(range(151))
    assert plan[0] == {
        "state_index": 0,
        "advance_physics_before_read": False,
        "readback_source": "authored_usd_points",
    }
    assert all(item["advance_physics_before_read"] for item in plan[1:])
    assert all(item["readback_source"] == "physx" for item in plan[1:])
    assert sum(item["advance_physics_before_read"] for item in plan) == 150


def test_capture_record_selection_uses_live_final_state_for_static_mode():
    probe = _module()
    records = [{"step_index": index} for index in range(151)]

    selected = probe.select_capture_records("static", records, frame_stride=10)

    assert selected == [records[-1]]


def test_capture_record_selection_samples_kinematic_trace_and_keeps_final_state():
    probe = _module()
    records = [{"step_index": index} for index in range(26)]

    selected = probe.select_capture_records("kinematic", records, frame_stride=10)

    assert [record["step_index"] for record in selected] == [0, 10, 20, 25]


def test_render_barrier_proves_timeline_and_strict_step_counts_are_unchanged():
    probe = _module()

    class Timeline:
        def get_current_time(self):
            return 7.0

    class Stepper:
        executed_logical_steps = 12
        executed_integration_steps = 48

    class Orchestrator:
        def step(self, **kwargs):
            self.kwargs = kwargs

        def wait_until_complete(self):
            pass

    class Rep:
        orchestrator = Orchestrator()

    result = probe._replicator_render_barrier(
        Rep(), Timeline(), rt_subframes=2, stepper=Stepper()
    )

    assert result["timeline_unchanged"] is True
    assert result["strict_step_counts_unchanged"] is True
    assert result["logical_steps_before"] == result["logical_steps_after"] == 12
    assert result["integration_steps_before"] == result["integration_steps_after"] == 48


def test_render_barrier_rejects_hidden_strict_physics_step():
    probe = _module()

    class Timeline:
        def get_current_time(self):
            return 0.0

    class Stepper:
        executed_logical_steps = 3
        executed_integration_steps = 12

    stepper = Stepper()

    class Orchestrator:
        def step(self, **kwargs):
            stepper.executed_integration_steps += 1

        def wait_until_complete(self):
            pass

    class Rep:
        orchestrator = Orchestrator()

    with pytest.raises(RuntimeError, match="replicator_render_advanced_physics"):
        probe._replicator_render_barrier(
            Rep(), Timeline(), rt_subframes=1, stepper=stepper
        )


def test_strict_phase_summaries_combine_prefluid_and_fluid_execution():
    probe = _module()
    prefluid = {
        "requested_logical_steps": 21,
        "executed_logical_steps": 21,
        "requested_integration_steps": 84,
        "executed_integration_steps": 84,
        "exact_step_count_verified": True,
        "ordered_lifecycle_verified": True,
        "attach_verified": True,
        "detach_verified": True,
        "render_invariance_checks": 0,
        "simulate_fetch_pair_count": 84,
        "simulated_seconds": 0.7,
    }
    fluid = {
        "requested_logical_steps": 150,
        "executed_logical_steps": 150,
        "requested_integration_steps": 600,
        "executed_integration_steps": 600,
        "exact_step_count_verified": True,
        "ordered_lifecycle_verified": True,
        "attach_verified": True,
        "detach_verified": True,
        "render_invariance_checks": 17,
        "simulate_fetch_pair_count": 600,
        "simulated_seconds": 5.0,
    }

    result = probe.combine_strict_phase_summaries(
        {"prefluid": prefluid, "fluid": fluid}, requested_logical_steps=171
    )

    assert result["requested_logical_steps"] == 171
    assert result["executed_logical_steps"] == 171
    assert result["executed_integration_steps"] == 684
    assert result["exact_step_count_verified"] is True
    assert result["ordered_lifecycle_verified"] is True
    assert result["attach_verified"] is True
    assert result["detach_verified"] is True
    assert result["render_invariance_checks"] == 17
    assert result["phases"] == {"prefluid": prefluid, "fluid": fluid}


def _test_frame(origin):
    from tools.labutopia_fluid.real_beaker import CupInteriorFrame

    return CupInteriorFrame(
        origin_world=origin,
        x_axis_world=(1.0, 0.0, 0.0),
        y_axis_world=(0.0, 1.0, 0.0),
        z_axis_world=(0.0, 0.0, 1.0),
        parent_local_axis="Z",
        outer_radius=0.06,
        interior_radius=0.05,
        outer_floor=0.0,
        interior_floor=0.0,
        rim_height=0.10,
        calibration_source="test",
        axis_alignment_dot=1.0,
    )


def test_two_beaker_accounting_is_mutually_exclusive_and_source_first():
    probe = _module()
    source = _test_frame((0.0, 0.0, 0.0))
    target = _test_frame((0.0, 0.0, 0.0))
    positions = [
        (0.0, 0.0, 0.05),
        (0.20, 0.0, -0.01),
        (0.20, 0.0, 0.001),
        (0.20, 0.0, 0.20),
    ]

    result = probe.classify_two_beaker_positions(
        positions,
        source_frame=source,
        target_frame=target,
        table_z=0.0,
        epsilon=1e-6,
    )

    assert result["source"] == 1
    assert result["target"] == 0
    assert result["below_table"] == 1
    assert result["tabletop_spill"] == 1
    assert result["transit"] == 1
    assert result["nonfinite"] == 0
    assert result["finite_partition_total"] == 4
    assert result["partition_complete"] is True


def test_default_containment_tolerance_absorbs_only_sub_particle_numeric_jitter():
    probe = _module()
    source = _test_frame((0.0, 0.0, 0.0))
    target = _test_frame((1.0, 0.0, 0.0))

    result = probe.classify_two_beaker_positions(
        [(0.050025, 0.0, 0.05), (0.0502, 0.0, 0.05)],
        source_frame=source,
        target_frame=target,
        table_z=0.0,
    )

    assert result["epsilon_m"] == pytest.approx(0.00005)
    assert result["source"] == 1
    assert result["transit"] == 1

    hold = probe.classify_source_hold_positions(
        [(0.050025, 0.0, 0.05), (0.0502, 0.0, 0.05)],
        source,
    )
    assert hold["inside_visible_interior_count"] == 1
    assert hold["strict_violating_point_count"] == 1
    assert hold["classification_epsilon_m"] == pytest.approx(0.00005)


def test_two_beaker_accounting_rejects_nonfinite_as_invalid():
    probe = _module()
    frame = _test_frame((0.0, 0.0, 0.0))

    result = probe.classify_two_beaker_positions(
        [(math.nan, 0.0, 0.0)],
        source_frame=frame,
        target_frame=frame,
        table_z=0.0,
    )

    assert result["nonfinite"] == 1
    assert result["valid"] is False
    assert result["partition_complete"] is True


def test_static_verdict_requires_zero_violation_at_every_post_fluid_step():
    probe = _module()
    passing = [
        {
            "step_index": step,
            "particle_count": 3600,
            "position_sha256": f"runtime-{min(step, 10)}",
            "strict_counts": {
                "inside_visible_interior_count": 3600,
                "strict_violating_point_count": 0,
                "nonfinite_count": 0,
            },
        }
        for step in range(151)
    ]

    assert probe.classify_static_hold_records(passing)["physics_pass"] is True
    failing = [dict(record) for record in passing]
    failing[73] = {
        **failing[73],
        "strict_counts": {
            "inside_visible_interior_count": 3599,
            "strict_violating_point_count": 1,
            "nonfinite_count": 0,
        },
    }
    failed = probe.classify_static_hold_records(failing)
    assert failed["physics_pass"] is False
    assert failed["first_failing_step"] == 73


def test_static_verdict_rejects_particles_not_advanced_by_physx():
    probe = _module()
    frozen = [
        {
            "step_index": step,
            "particle_count": 3600,
            "position_sha256": "authored" if step == 0 else "float32-only",
            "strict_counts": {
                "inside_visible_interior_count": 3600,
                "strict_violating_point_count": 0,
                "nonfinite_count": 0,
            },
        }
        for step in range(151)
    ]

    result = probe.classify_static_hold_records(frozen)

    assert result["physics_pass"] is False
    assert result["runtime_unique_position_hash_count"] == 1
    assert "particle_dynamics_not_observed" in result["failure_reasons"]


def test_fixed_kinematic_schedule_has_one_hashed_690_step_treatment():
    probe = _module()

    schedule = probe.build_fixed_kinematic_schedule()

    assert len(schedule["states"]) == 691
    assert schedule["physics_steps"] == 690
    assert schedule["segment_steps"] == {
        "approach": 120,
        "tilt": 120,
        "hold": 120,
        "untilt": 120,
        "return": 60,
        "settle": 150,
    }
    assert max(state["tilt_degrees"] for state in schedule["states"]) == pytest.approx(
        100.0
    )
    assert schedule["states"][0]["translation_progress"] == pytest.approx(0.0)
    assert schedule["states"][-1]["translation_progress"] == pytest.approx(0.0)
    assert schedule["states"][-1]["tilt_degrees"] == pytest.approx(0.0)
    assert len(schedule["trace_sha256"]) == 64


def test_full_tilt_keeps_floor_pivot_and_places_source_mouth_over_target_opening():
    _require_source_scene()
    probe = _module()
    from pxr import Gf, Usd, UsdGeom

    stage = Usd.Stage.Open(str(SOURCE_SCENE), Usd.Stage.LoadAll)
    assert stage is not None
    source = _real_source_frame()
    target = _real_target_frame()
    initial_parent = UsdGeom.XformCache().GetLocalToWorldTransform(
        stage.GetPrimAtPath("/World/beaker2")
    )
    schedule = probe.build_fixed_kinematic_schedule()
    full_tilt_step = (
        schedule["segment_steps"]["approach"] + schedule["segment_steps"]["tilt"]
    )
    state = schedule["states"][full_tilt_step]

    current_parent = probe._kinematic_parent_matrix(
        state=state,
        initial_parent=initial_parent,
        source_frame=source,
        target_frame=target,
    )
    current_source = probe._frame_at_parent_matrix(
        source,
        initial_parent,
        current_parent,
    )
    target_origin = Gf.Vec3d(*target.origin_world)
    floor = Gf.Vec3d(*current_source.origin_world)
    mouth = floor + Gf.Vec3d(*current_source.z_axis_world) * source.rim_height
    mouth_delta = mouth - target_origin
    mouth_x = float(mouth_delta * Gf.Vec3d(*target.x_axis_world))
    mouth_y = float(mouth_delta * Gf.Vec3d(*target.y_axis_world))
    mouth_z = float(mouth_delta * Gf.Vec3d(*target.z_axis_world))
    opening_vertical = float(
        Gf.Vec3d(*current_source.z_axis_world) * Gf.Vec3d(*target.z_axis_world)
    )
    rim_vertical_extent = source.outer_radius * math.sqrt(
        max(0.0, 1.0 - opening_vertical * opening_vertical)
    )

    assert math.dist(
        current_source.origin_world,
        probe._kinematic_approach_floor(source, target),
    ) < 1e-8
    assert math.hypot(mouth_x, mouth_y) < target.interior_radius * 0.5
    assert mouth_z - rim_vertical_extent >= (
        target.rim_height + probe.KINEMATIC_MOUTH_CLEARANCE_M - 1e-7
    )
    assert opening_vertical < 0.0


def test_physx_pose_round_trips_world_matrix_with_xyzw_quaternion_order():
    probe = _module()
    from pxr import Gf

    matrix = Gf.Matrix4d(1.0)
    matrix.SetRotate(Gf.Rotation(Gf.Vec3d(1.0, 2.0, 3.0), 37.0))
    matrix.SetTranslateOnly(Gf.Vec3d(0.25, -0.4, 0.9))

    pose = probe.matrix_to_physx_pose(matrix)
    restored = probe.physx_pose_to_matrix(pose)

    assert pose[:3] == pytest.approx([0.25, -0.4, 0.9])
    assert len(pose) == 7
    for row in range(4):
        assert list(restored[row]) == pytest.approx(list(matrix[row]), abs=1e-7)


def test_read_matrix_restores_serialized_world_transform_instead_of_identity():
    probe = _module()

    payload = [
        [0.70710678, 0.70710678, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.70710678, -0.70710678, 0.0, 0.0],
        [0.295, 0.075, 0.82333823, 1.0],
    ]

    restored = probe._read_matrix(payload)

    for row in range(4):
        assert list(restored[row]) == pytest.approx(payload[row], abs=1e-8)


def test_kinematic_pose_error_treats_quaternion_signs_as_same_rotation():
    probe = _module()
    target = [0.1, 0.2, 0.3, 0.0, 0.0, 0.38268343, 0.92387953]
    actual = [0.1, 0.2, 0.3, -0.0, -0.0, -0.38268343, -0.92387953]

    error = probe.kinematic_pose_error(target, actual)

    assert error["position_m"] == pytest.approx(0.0)
    assert error["rotation_degrees"] == pytest.approx(0.0, abs=1e-6)
    assert error["within_tolerance"] is True


def test_offline_replay_teleports_rigid_actor_and_verifies_tensor_readback():
    probe = _module()
    import numpy as np

    class RigidBodyView:
        def __init__(self):
            self.transforms = np.zeros((1, 7), dtype=np.float32)
            self.indices = None

        def set_transforms(self, transforms, indices):
            self.transforms = np.asarray(transforms, dtype=np.float32)
            self.indices = np.asarray(indices)

        def get_transforms(self):
            return self.transforms

    view = RigidBodyView()
    target = [0.25, -0.4, 0.9, 0.0, 0.0, 0.38268343, 0.92387953]

    result = probe.replay_kinematic_actor_pose(
        view=view,
        pose_xyzw=target,
        indices=np.asarray([0], dtype=np.uint32),
        np_module=np,
    )

    assert view.indices.tolist() == [0]
    assert result["actual_pose_xyzw"] == pytest.approx(target, abs=1e-6)
    assert result["pose_error"]["within_tolerance"] is True


def test_kinematic_verdict_requires_zero_loss_zero_final_transit_and_transfer_floor():
    probe = _module()
    final_step = probe.build_fixed_kinematic_schedule()["physics_steps"]
    records = [
        {
            "step_index": step,
            "kinematic_pose_error": {
                "position_m": 0.0,
                "rotation_degrees": 0.0,
                "within_tolerance": True,
            },
            "counts": {
                "source": 3600 if step < final_step else 3400,
                "target": 0 if step < final_step else 200,
                "below_table": 0,
                "tabletop_spill": 0,
                "transit": 0,
                "nonfinite": 0,
                "partition_complete": True,
            },
        }
        for step in range(final_step + 1)
    ]

    records[100]["counts"]["source"] = 3590
    records[100]["counts"]["transit"] = 10
    passing = probe.classify_kinematic_records(records)
    assert passing["physics_pass"] is True
    assert passing["final_counts"]["source"] == 3400
    assert passing["final_counts"]["target"] == 200
    assert passing["transit_particle_state_count"] == 10
    assert passing["maximum_transit_count"] == 10
    records[-1]["counts"]["target"] = 149
    records[-1]["counts"]["source"] = 3451
    failed = probe.classify_kinematic_records(records)
    assert failed["physics_pass"] is False
    assert "target_transfer_below_150" in failed["failure_reasons"]

    records[-1]["counts"]["target"] = 200
    records[-1]["counts"]["source"] = 3400
    records[100]["kinematic_pose_error"] = {
        "position_m": 0.01,
        "rotation_degrees": 0.0,
        "within_tolerance": False,
    }
    pose_failed = probe.classify_kinematic_records(records)
    assert pose_failed["physics_pass"] is False
    assert "kinematic_pose_readback_failed_at_100" in pose_failed["failure_reasons"]


def test_parser_defaults_to_static_fixed_recipe_and_supports_kinematic_mode():
    probe = _module()

    parser = probe.build_arg_parser()
    static = parser.parse_args([])
    kinematic = parser.parse_args(["--mode", "kinematic"])

    assert static.mode == "static"
    assert static.usd == str(probe.DEFAULT_SOURCE_SCENE)
    assert static.width == 960
    assert static.height == 540
    assert static.headless is True
    assert static.collider_mode == "inner-wall"
    assert kinematic.mode == "kinematic"


def test_runtime_validity_keeps_physics_execution_separate_from_rgb_capture():
    probe = _module()

    result = probe.classify_runtime_validity(
        step_summary={
            "exact_step_count_verified": True,
            "ordered_lifecycle_verified": True,
        },
        stage_contract={"valid": True},
        collider_log={"failure_detected": False},
        record_count=151,
        required_video_valid=False,
    )

    assert result["technical_valid"] is True
    assert result["physics_evidence_valid"] is True
    assert result["visual_capture_valid"] is False
    assert result["visual_capture_failure_reasons"] == ["required_video_capture_missing"]


def test_closeup_camera_centers_the_target_pour_region_not_source_start_pose():
    probe = _module()
    source = _real_source_frame()
    target = _real_target_frame()

    closeup = probe._camera_specs(source, target)["closeup"]
    table_z = min(source.origin_world[2], target.origin_world[2])
    expected_target = [
        target.origin_world[0],
        target.origin_world[1],
        table_z + 0.11,
    ]

    assert closeup["target"] == pytest.approx(expected_target)
    assert math.dist(closeup["target"], target.origin_world) < math.dist(
        closeup["target"], source.origin_world
    )
    assert closeup["eye"][2] > closeup["target"][2]


def test_rgb_frame_normalization_accepts_float_rgba_and_rejects_empty_data():
    probe = _module()
    import numpy as np

    rgb = probe.normalize_rgb_frame(
        np.full((2, 3, 4), 0.5, dtype=np.float32),
        expected_width=3,
        expected_height=2,
    )

    assert rgb.shape == (2, 3, 3)
    assert rgb.dtype == np.uint8
    assert np.all(rgb == 127)
    with pytest.raises(ValueError, match="rgb_capture_shape_mismatch"):
        probe.normalize_rgb_frame(
            np.asarray([]),
            expected_width=3,
            expected_height=2,
        )


def test_replicator_cleanup_detaches_shared_annotator_once():
    probe = _module()

    class Annotator:
        def __init__(self):
            self.detach_calls = 0

        def detach(self):
            self.detach_calls += 1

    class RenderProduct:
        def __init__(self):
            self.destroy_calls = 0

        def destroy(self):
            self.destroy_calls += 1

    annotator = Annotator()
    products = [RenderProduct(), RenderProduct()]
    resources = {
        "context": {"annotator": annotator, "render_product": products[0]},
        "closeup": {"annotator": annotator, "render_product": products[1]},
    }

    result = probe._destroy_replicator_capture_resources(resources)

    assert result["complete"] is True
    assert annotator.detach_calls == 1
    assert [product.destroy_calls for product in products] == [1, 1]
    assert result["detached"] == ["closeup", "context"]


def test_terminal_combined_verdict_keeps_physics_and_visual_separate():
    probe = _module()

    assert probe.combine_terminal_verdict(
        mode="static", technical_valid=True, physics_pass=True, visual_pass=True
    ) == "STATIC_ELIGIBLE_FOR_KINEMATIC"
    assert probe.combine_terminal_verdict(
        mode="static", technical_valid=True, physics_pass=True, visual_pass=False
    ) == "STATIC_VISUAL_FAIL"
    assert probe.combine_terminal_verdict(
        mode="static", technical_valid=True, physics_pass=False, visual_pass=True
    ) == "STATIC_PHYSICS_FAIL"
    assert probe.combine_terminal_verdict(
        mode="kinematic", technical_valid=False, physics_pass=False, visual_pass=False
    ) == "INVALID_KINEMATIC_POUR"
