import pytest

from tools.labutopia_fluid.run_beaker_collider_smoke import ColliderConfig
from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import (
    BBox,
    apply_fluid_safe_wrapper_overlay,
    build_colleague_variant_spec,
    build_particle_scope_summary,
    build_review_camera_summary,
    build_review_marker_summary,
    build_source_grid_positions,
    build_tabletop_region_config,
    classify_colleague_trace,
    resolve_particle_runtime_offsets,
    select_particle_subset,
    world_camera_quat_look_at,
)


def test_select_particle_subset_is_deterministic_and_preserves_bounds():
    points = [(float(i), float(i % 7), float(i % 3)) for i in range(100)]

    selected = select_particle_subset(points, limit=10)

    assert selected == select_particle_subset(points, limit=10)
    assert len(selected) == 10
    assert selected[0] == points[0]
    assert selected[-1] == points[-1]


def test_build_particle_scope_summary_marks_zero_limit_as_full_original_50k():
    summary = build_particle_scope_summary(original_particle_count=50000, selected_particle_count=50000, particle_limit=0)

    assert summary["particle_scope"] == "full_original_50k"
    assert summary["full_original_50k_completed_pbd_overlay"] is True
    assert summary["sampled_overlay"] is False


def test_build_review_camera_summary_requires_real_rgb_frames_for_d3():
    summary = build_review_camera_summary(
        {
            "rgb_frames/frame_0000.png": "camera_rgb",
            "rgb_frames/frame_0060.png": "camera_rgb",
            "projection_frames/frame_0000.png": "diagnostic_projection",
        }
    )

    assert summary["real_rgb_camera_frame_count"] == 2
    assert summary["diagnostic_projection_frame_count"] == 1
    assert summary["d3_real_isaacsim41_rgb_camera_passed"] is True


def test_build_review_marker_summary_marks_markers_as_visual_only():
    summary = build_review_marker_summary(marker_limit=2500, marker_width=0.006)

    assert summary["d3_review_markers_enabled"] is True
    assert summary["d3_review_markers_are_physics"] is False
    assert summary["d3_review_marker_source"] == "particle_readback_positions"


def test_world_camera_quat_look_at_identity_when_forward_is_positive_x():
    quat = world_camera_quat_look_at(eye=(0.0, 0.0, 0.0), target=(1.0, 0.0, 0.0), up=(0.0, 0.0, 1.0))

    assert quat == pytest.approx((1.0, 0.0, 0.0, 0.0))


def test_build_tabletop_region_config_uses_beaker_bboxes():
    source = BBox(min=(0.25, 0.03, 0.82), max=(0.37, 0.15, 0.92))
    target = BBox(min=(0.20, -0.30, 0.81), max=(0.36, -0.14, 0.94))
    table_top_z = 0.77

    config = build_tabletop_region_config(source_bbox=source, target_bbox=target, table_top_z=table_top_z)

    assert config.source_center == (0.31, 0.09, table_top_z)
    assert config.target_center == (0.28, -0.22, table_top_z)
    assert config.source_radius == 0.065
    assert config.target_radius == 0.085
    assert config.table_z == table_top_z
    assert config.source_height > 0.14


def test_build_source_grid_positions_places_regular_grid_inside_source_region():
    source = BBox(min=(0.25, 0.03, 0.82), max=(0.37, 0.15, 0.92))
    target = BBox(min=(0.20, -0.30, 0.81), max=(0.36, -0.14, 0.94))
    config = build_tabletop_region_config(source_bbox=source, target_bbox=target, table_top_z=0.77)

    positions = build_source_grid_positions(config=config, count=16)

    assert len(positions) == 16
    assert min(pos[2] for pos in positions) > config.table_z
    assert max(abs(pos[0] - config.source_center[0]) for pos in positions) < config.source_radius
    assert max(abs(pos[1] - config.source_center[1]) for pos in positions) < config.source_radius


def test_resolve_particle_runtime_offsets_keeps_authored_width_by_default():
    offsets = resolve_particle_runtime_offsets(
        authored_width=0.000594,
        particle_width_override=None,
        particle_contact_offset_override=None,
    )

    assert offsets["particle_width"] == 0.000594
    assert offsets["particle_contact_offset"] == 0.0005346
    assert offsets["particle_system_contact_offset"] == pytest.approx(0.00064152)


def test_resolve_particle_runtime_offsets_allows_s2_normalized_diagnostic_size():
    offsets = resolve_particle_runtime_offsets(
        authored_width=0.000594,
        particle_width_override=0.0035,
        particle_contact_offset_override=0.0045,
    )

    assert offsets["particle_width"] == 0.0035
    assert offsets["particle_contact_offset"] == 0.0045
    assert offsets["particle_system_contact_offset"] == pytest.approx(0.0054)


def test_build_colleague_variant_spec_distinguishes_native_and_proxy_modes():
    native = build_colleague_variant_spec("native-convex")
    proxy = build_colleague_variant_spec("native-proxy-wrapper")

    assert native.native_collision_route == "convexDecomposition"
    assert native.native_mesh_collision_enabled is True
    assert native.proxy_collision_enabled is False
    assert proxy.native_collision_route == "render_mesh_plus_proxy_collision"
    assert proxy.native_mesh_collision_enabled is False
    assert proxy.proxy_collision_enabled is True


def test_build_colleague_variant_spec_fluid_safe_wrapper_mode():
    spec = build_colleague_variant_spec("fluid-safe-wrapper")

    assert spec.variant_id == "COLLEAGUE_FLUID_SAFE_WRAPPER"
    assert spec.setup == "fluid_safe_wrapper"
    assert spec.source_kind == "fluid_safe_wrapper"
    assert spec.native_source_path == "/World/beaker2"
    assert spec.native_mesh_source_path == "/World/beaker2/mesh"
    assert spec.native_mesh_collision_enabled is False
    assert spec.proxy_collision_enabled is False
    assert spec.wrapper_parent_path == "/World/beaker2"
    assert spec.wrapper_frame == "local_to_beaker2"
    assert spec.native_collision_route == "render_mesh_plus_fluid_safe_wrapper"
    assert spec.panel_count == 48


def _author_full_scene_beaker2_fixture(stage, *, translate=(0.31, 0.09, 0.85)):
    from pxr import Gf, UsdGeom, UsdPhysics

    UsdGeom.Xform.Define(stage, "/World")
    parent = UsdGeom.Xform.Define(stage, "/World/beaker2")
    parent.AddTranslateOp().Set(Gf.Vec3d(*translate))
    mesh = UsdGeom.Cube.Define(stage, "/World/beaker2/mesh")
    mesh.CreateSizeAttr(0.12)
    mesh_prim = mesh.GetPrim()
    collision_api = UsdPhysics.CollisionAPI.Apply(mesh_prim)
    collision_api.CreateCollisionEnabledAttr().Set(True)
    return parent.GetPrim(), mesh_prim


def test_apply_fluid_safe_wrapper_overlay_disables_mesh_and_authors_wrapper():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    _author_full_scene_beaker2_fixture(stage)
    config = ColliderConfig(wall_thickness=0.018, bottom_overlap=0.003)

    result = apply_fluid_safe_wrapper_overlay(
        stage,
        config,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        panel_count=8,
    )

    wrapper = stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapper")
    mesh_prim = stage.GetPrimAtPath("/World/beaker2/mesh")

    assert wrapper.IsValid()
    assert UsdGeom.Imageable(wrapper).ComputeVisibility() == UsdGeom.Tokens.invisible
    assert wrapper.GetAttribute("labutopia:fluidSafeWrapper").Get() is True
    assert wrapper.GetAttribute("labutopia:wrapperFrame").Get() == "local_to_beaker2"
    assert mesh_prim.GetAttribute("physics:collisionEnabled").Get() is False
    assert result["wrapper_path"] == "/World/beaker2/FluidSafeWrapper"
    assert result["wrapper_frame"] == "local_to_beaker2"
    assert result["motion_contract"] == "static_collision_inherits_beaker2_xform"
    assert result["wrapper_parent_path"] == "/World/beaker2"
    assert result["native_mesh_collision_enabled"] is False
    assert result["overlay_mode"] == "fluid-safe-wrapper"
    assert "/World/beaker2/FluidSafeWrapper/Bottom" in result["collider_paths"]


def test_build_fluid_safe_wrapper_isaac_smoke_command_documents_512p_entrypoint():
    from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import (
        build_fluid_safe_wrapper_isaac_smoke_command,
    )

    cmd = build_fluid_safe_wrapper_isaac_smoke_command(particle_limit=512, steps=120)

    assert "--collider-mode" in cmd
    assert "fluid-safe-wrapper" in cmd
    assert "--particle-limit" in cmd
    assert "512" in cmd
    assert "--headless" in cmd


def test_classify_colleague_trace_marks_any_source_escape_as_leak():
    source = BBox(min=(0.25, 0.03, 0.82), max=(0.37, 0.15, 0.92))
    target = BBox(min=(0.20, -0.30, 0.81), max=(0.36, -0.14, 0.94))
    config = build_tabletop_region_config(source_bbox=source, target_bbox=target, table_top_z=0.77)
    records = [
        {
            "step_index": 0,
            "particle_count": 4,
            "positions": [
                (0.30, 0.09, 0.85),
                (0.31, 0.09, 0.86),
                (0.32, 0.09, 0.87),
                (0.33, 0.09, 0.88),
            ],
        },
        {
            "step_index": 60,
            "particle_count": 4,
            "positions": [
                (0.30, 0.09, 0.85),
                (0.31, 0.09, 0.86),
                (0.90, 0.50, 0.84),
                (0.32, 0.09, 0.50),
            ],
        },
    ]

    result = classify_colleague_trace(records, config)

    assert result["classification"] == "FAIL_CONTAINER_LEAK"
    assert result["outside_source_count"] == 2
    assert result["spill_count"] == 1
    assert result["below_table_count"] == 1
