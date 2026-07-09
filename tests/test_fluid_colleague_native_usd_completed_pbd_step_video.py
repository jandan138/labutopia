import math
from pathlib import Path

from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
    DEFAULT_USD,
    EVIDENCE_PARTICLE_SET_PATH,
    EVIDENCE_PARTICLE_SYSTEM_PATH,
    ISAACSIM41_CORE_MDL_ROOT,
    LIQUID_PRESENTATION_CAMERA_PATH,
    LIQUID_PRESENTATION_LIGHT_PATH,
    LIQUID_PRESENTATION_MATERIAL_PATH,
    NATIVE_SCENE_COMPLETED_PBD_VARIANT_ID,
    PRESENTATION_WATER_MDL_ASSET,
    PRESENTATION_WATER_MDL_SUB_IDENTIFIER,
    NativeMaterialExpectation,
    _deactivate_original_fluid_prims,
    _define_liquid_presentation_camera,
    _author_liquid_presentation_lighting,
    _author_liquid_presentation_water_material,
    build_liquid_presentation_isosurface_contract,
    build_native_scene_claim_boundary,
    build_native_scene_video_summary,
    build_presentation_visual_contract,
    build_presentation_water_mdl_material_info,
    build_presentation_water_preview_fallback_info,
    build_isaacsim41_core_mdl_closure_plan,
    inspect_native_material_bindings,
    scan_mdl_compile_errors,
    scan_presentation_water_mdl_compile_errors,
)


def test_inspect_native_material_bindings_preserves_local_mdl_glass_contract():
    summary = inspect_native_material_bindings(Path(DEFAULT_USD))

    assert summary["native_scene_opened"] is True
    assert summary["beaker2"]["material_path"] == "/World/Looks/OmniSurface_Glass"
    assert summary["beaker2"]["source_asset"] == "OmniSurfacePresets.mdl"
    assert summary["beaker2"]["source_asset_resolved"] is True
    assert summary["beaker2"]["sub_identifier"] == "OmniSurface_Glass"
    assert summary["beaker1"]["material_path"] == "/World/Looks/OmniGlass"
    assert summary["beaker1"]["source_asset"] == "OmniGlass.mdl"
    assert summary["beaker1"]["source_asset_resolved"] is True
    assert summary["particle_system"]["material_path"] == "/World/Looks/OmniGlass_01"
    assert summary["particle_system"]["source_asset"] == "OmniGlass.mdl"
    assert summary["particle_system"]["source_asset_resolved"] is True


def test_native_material_expectation_rejects_preview_surface_override_strategy():
    expectation = NativeMaterialExpectation()

    assert expectation.minimal_native_slice_used is False
    assert expectation.native_beaker_material_override_used is False
    assert expectation.local_blue_glass_override_used is False
    assert expectation.visual_material_parity_claim_allowed is False


def test_build_native_scene_video_summary_records_four_video_slots_and_claim_boundary():
    summary = build_native_scene_video_summary(
        frame_sources={
            "camera1_native_material_frames/frame_0000.png": "native_camera_rgb",
            "camera2_native_material_frames/frame_0000.png": "native_camera_rgb",
            "beaker2_closeup_native_material_frames/frame_0000.png": "closeup_native_rgb",
            "beaker2_closeup_review_marker_frames/frame_0000.png": "review_marker_rgb",
        }
    )

    assert summary["native_camera_rgb_frame_count"] == 2
    assert summary["closeup_native_rgb_frame_count"] == 1
    assert summary["review_marker_rgb_frame_count"] == 1
    assert summary["native_scene_video_slots"] == [
        "camera1_native_material",
        "camera2_native_material",
        "beaker2_closeup_native_material",
        "beaker2_closeup_review_markers",
    ]

    boundary = build_native_scene_claim_boundary()
    assert "native_usd_scene_step_video_recorded=true" in boundary["allowed"]
    assert "native_scene_material_paths_preserved=true" in boundary["allowed"]
    assert (
        "native_scene_mdl_source_assets_retargeted_to_isaacsim41_local_mirror=true"
        in boundary["allowed"]
    )
    assert "native_scene_material_bindings_preserved=true" not in boundary["allowed"]
    assert "raw_usd_direct_step_passed" in boundary["blocked"]
    assert "review_marker_video_equals_native_material_video" in boundary["blocked"]


def test_scan_mdl_compile_errors_distinguishes_resolve_from_runtime_compile_failure():
    log_text = "\n".join(
        [
            "[Error] [rtx.neuraylib.plugin] [MDLC:COMPILER] comp error: file:/pkg/OmniGlass.mdl(246,5): C157 'OmniGlass_Opacity' has no parameter named 'geometry_normal_roughness_strength'",
            "[Error] [omni.hydra] Failed to create MDL shade node for prim '/World/Looks/OmniGlass_01/Shader'. createMdlModule failed.",
            "[Error] [rtx.neuraylib.plugin] [MDLC:COMPILER] comp error: file:/pkg/OmniSurfacePresets.mdl(38,8): C120 could not find module '.::OmniSurfaceLite' in module path",
        ]
    )

    summary = scan_mdl_compile_errors(log_text)

    assert summary["mdl_compile_status"] == "MDL_COMPILE_FAIL"
    assert summary["has_omniglass_compile_error"] is True
    assert summary["has_omnisurface_compile_error"] is True
    assert summary["error_count"] == 3


def test_scan_presentation_water_mdl_compile_errors_filters_to_presentation_shader():
    log_text = "\n".join(
        [
            "[Error] [omni.hydra] Failed to create MDL shade node for prim '/World/Looks/OmniGlass_01/Shader'. createMdlModule failed.",
            "[Error] [omni.hydra] Failed to create MDL shade node for prim '/World/Looks/LiquidPresentationWater/Shader'. createMdlModule failed.",
            "[Error] [rtx.neuraylib.plugin] [MDLC:COMPILER] comp error: file:/pkg/OmniSurfacePresets.mdl(5386,1): C120 could not find module for OmniSurface_ClearWater",
        ]
    )

    presentation = scan_presentation_water_mdl_compile_errors(log_text)
    all_errors = scan_mdl_compile_errors(log_text)

    assert all_errors["error_count"] == 3
    assert presentation["mdl_compile_status"] == "MDL_COMPILE_FAIL"
    assert presentation["error_count"] == 2
    assert presentation["has_presentation_water_compile_error"] is True
    assert all(
        LIQUID_PRESENTATION_MATERIAL_PATH in line or "omnisurface_clearwater" in line.lower()
        for line in presentation["errors"]
    )


def test_build_isaacsim41_core_mdl_closure_plan_includes_transitive_base_dependencies():
    plan = build_isaacsim41_core_mdl_closure_plan(
        ["OmniGlass.mdl", "OmniSurfacePresets.mdl", "OmniPBR.mdl"]
    )

    assert plan["material_closure_mode"] == "isaacsim41_core_mdl_local_mirror"
    assert "OmniGlass_Opacity.mdl" in plan["mdl_files"]
    assert "OmniSurfaceLite.mdl" in plan["mdl_files"]
    assert "OmniSurface.mdl" in plan["mdl_files"]
    assert "OmniPBR_ClearCoat.mdl" in plan["mdl_files"]
    assert plan["visual_material_parity_claim_allowed"] is False


def test_native_scene_completed_pbd_variant_id_is_not_bounded_smoke_label():
    assert NATIVE_SCENE_COMPLETED_PBD_VARIANT_ID == "COLLEAGUE_NATIVE_USD_FULL_50K_COMPLETED_PBD"
    assert NATIVE_SCENE_COMPLETED_PBD_VARIANT_ID != "COLLEAGUE_USD_BOUNDED"


def test_deactivate_original_fluid_keeps_prims_active_for_kit_stage_update():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/fluid")
    UsdGeom.Points.Define(stage, EVIDENCE_PARTICLE_SET_PATH)
    UsdGeom.Xform.Define(stage, EVIDENCE_PARTICLE_SYSTEM_PATH)

    summary = _deactivate_original_fluid_prims(stage)

    for path in ("/World/fluid", EVIDENCE_PARTICLE_SET_PATH, EVIDENCE_PARTICLE_SYSTEM_PATH):
        prim = stage.GetPrimAtPath(path)
        assert prim.IsActive() is True
        assert summary[path]["deactivated"] is False
        assert summary[path]["kept_active_to_avoid_physx_expired_prim"] is True
        assert prim.GetAttribute("visibility").Get() == "invisible"

    particle_system = stage.GetPrimAtPath(EVIDENCE_PARTICLE_SYSTEM_PATH)
    particle_set = stage.GetPrimAtPath(EVIDENCE_PARTICLE_SET_PATH)
    assert particle_system.GetAttribute("particleSystemEnabled").Get() is False
    assert particle_set.GetAttribute("physxParticle:selfCollision").Get() is False
    assert particle_set.GetAttribute("physxParticle:fluid").Get() is False


def test_build_liquid_presentation_isosurface_contract_uses_offsets():
    contract = build_liquid_presentation_isosurface_contract(
        fluid_rest_offset=0.0003207600535824895,
        particle_count=50000,
    )

    assert contract["enabled"] is True
    assert contract["api_path"] == "/World/CompletedPBD/ParticleSystem"
    assert math.isclose(contract["grid_spacing"], 0.00028868404822424055)
    assert math.isclose(contract["surface_distance"], 0.000304722050903365)
    assert math.isclose(contract["grid_smoothing_radius"], 0.0003207600535824895)
    assert contract["grid_filtering_passes"] == "GS"
    assert contract["num_mesh_smoothing_passes"] == 4
    assert contract["num_mesh_normal_smoothing_passes"] == 4
    assert contract["max_vertices"] >= 1_000_000
    assert contract["max_triangles"] >= 2_000_000
    assert contract["max_subgrids"] >= 4096
    assert contract["parameter_reference"] == "isaacsim41_fluid_isosurface_cup_demo_style"
    assert contract["claim_boundary"] == "visual_surface_reconstruction_only"


def test_build_presentation_visual_contract_separates_visual_video_from_gate():
    contract = build_presentation_visual_contract(
        variant_id="NATIVE_SDF_128",
        camera_info={
            "camera_path": LIQUID_PRESENTATION_CAMERA_PATH,
            "eye": [0.5, -0.2, 1.0],
            "target": [0.3, 0.09, 0.86],
            "up": [0.0, 0.0, 1.0],
        },
        lighting_info={"lighting_contract_hash": "abc123"},
        isosurface_contract={"enabled": True},
        material_path=LIQUID_PRESENTATION_MATERIAL_PATH,
        particle_count=50000,
    )

    assert contract["variant_id"] == "NATIVE_SDF_128"
    assert contract["camera_path"] == LIQUID_PRESENTATION_CAMERA_PATH
    assert contract["liquid_material_path"] == LIQUID_PRESENTATION_MATERIAL_PATH
    assert contract["particle_count"] == 50000
    assert contract["debug_particle_display_enabled"] is False
    assert contract["presentation_video_does_not_replace_particle_readback"] is True
    assert contract["visual_material_parity_claim_allowed"] is False
    assert "same simulated particle trajectory" in contract["claim_boundary_text"]
    assert "particle readback" in contract["claim_boundary_text"]
    assert "do not change the particle simulation" in contract["claim_boundary_text"]


def test_build_presentation_water_mdl_material_info_targets_clearwater():
    info = build_presentation_water_mdl_material_info(
        source_asset="/isaac-sim/kit/mdl/core/Base/OmniSurfacePresets.mdl"
    )

    assert info["mdl_bind_attempted"] is True
    assert info["material_backend"] == "MDL_WATER"
    assert info["mdl_compile_status"] == "PASS"
    assert info["preferred_backend"] == "MDL_WATER"
    assert info["source_asset_basename"] == PRESENTATION_WATER_MDL_ASSET
    assert info["sub_identifier"] == PRESENTATION_WATER_MDL_SUB_IDENTIFIER
    assert info["sub_identifier"] == "OmniSurface_ClearWater"
    assert info["visual_material_parity_claim_allowed"] is False


def test_build_presentation_water_preview_fallback_without_attempt_is_mdl_not_attempted():
    info = build_presentation_water_preview_fallback_info(mdl_bind_attempted=False)

    assert info["mdl_bind_attempted"] is False
    assert info["material_backend"] == "USD_PREVIEW_FALLBACK"
    assert info["mdl_compile_status"] == "MDL_NOT_ATTEMPTED"
    assert info["preferred_backend"] == "MDL_WATER"
    assert info["sub_identifier"] == PRESENTATION_WATER_MDL_SUB_IDENTIFIER
    assert info["emissive_color"] == [0.0, 0.0, 0.0]
    assert "pending_mdl_water_pass" not in str(info.get("fallback_reason", ""))
    assert info["visual_material_parity_claim_allowed"] is False


def test_build_presentation_water_preview_fallback_after_failed_attempt_is_fallback_used():
    info = build_presentation_water_preview_fallback_info(
        mdl_bind_attempted=True,
        fallback_reason="mdl_asset_missing",
    )

    assert info["mdl_bind_attempted"] is True
    assert info["material_backend"] == "USD_PREVIEW_FALLBACK"
    assert info["mdl_compile_status"] == "FALLBACK_USED"
    assert info["fallback_reason"] == "mdl_asset_missing"
    assert info["emissive_color"] == [0.0, 0.0, 0.0]


def test_presentation_material_preview_only_path_reports_mdl_not_attempted():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")

    material_info = _author_liquid_presentation_water_material(stage, attempt_mdl=False)

    assert material_info["mdl_bind_attempted"] is False
    assert material_info["mdl_compile_status"] == "MDL_NOT_ATTEMPTED"
    assert material_info["material_backend"] == "USD_PREVIEW_FALLBACK"
    assert material_info["sub_identifier"] == "OmniSurface_ClearWater"
    assert material_info["emissive_color"] == [0.0, 0.0, 0.0]
    assert material_info["visual_material_parity_claim_allowed"] is False
    assert stage.GetPrimAtPath(LIQUID_PRESENTATION_MATERIAL_PATH)
    assert stage.GetPrimAtPath(f"{LIQUID_PRESENTATION_MATERIAL_PATH}/PreviewSurface")


def test_presentation_material_mdl_success_authors_clearwater_shader():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    mdl_path = ISAACSIM41_CORE_MDL_ROOT / "Base" / PRESENTATION_WATER_MDL_ASSET
    assert mdl_path.exists()

    material_info = _author_liquid_presentation_water_material(
        stage,
        attempt_mdl=True,
        mdl_source_asset=mdl_path,
    )

    assert material_info["mdl_bind_attempted"] is True
    assert material_info["material_backend"] == "MDL_WATER"
    assert material_info["mdl_compile_status"] == "PASS"
    assert material_info["sub_identifier"] == "OmniSurface_ClearWater"
    assert material_info["source_asset_basename"] == "OmniSurfacePresets.mdl"
    assert material_info["visual_material_parity_claim_allowed"] is False
    shader = stage.GetPrimAtPath(f"{LIQUID_PRESENTATION_MATERIAL_PATH}/Shader")
    assert shader
    assert shader.GetAttribute("info:mdl:sourceAsset:subIdentifier").Get() == "OmniSurface_ClearWater"
    assert not stage.GetPrimAtPath(f"{LIQUID_PRESENTATION_MATERIAL_PATH}/PreviewSurface")


def test_presentation_material_and_lighting_are_authored_with_fixed_paths():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")

    material_info = _author_liquid_presentation_water_material(stage, attempt_mdl=False)
    lighting_info = _author_liquid_presentation_lighting(stage)

    assert stage.GetPrimAtPath(LIQUID_PRESENTATION_MATERIAL_PATH)
    assert stage.GetPrimAtPath(LIQUID_PRESENTATION_LIGHT_PATH)
    assert material_info["material_path"] == LIQUID_PRESENTATION_MATERIAL_PATH
    assert material_info["display_name"] == "presentation_water_unified_realistic"
    assert material_info["emissive_color"] == [0.0, 0.0, 0.0]
    assert material_info["opacity"] <= 0.38
    assert material_info["roughness"] <= 0.08
    assert min(material_info["diffuse_color"]) >= 0.70
    assert material_info["tint_policy"] == "near_clear_subtle_blue_green"
    assert material_info["unified_liquid_style"] is True
    assert material_info["state_specific_liquid_materials"] is False
    assert material_info["all_liquid_particles_visible"] is True
    assert material_info["visualization_only"] is True
    assert material_info["visual_material_parity_claim_allowed"] is False
    assert material_info["mdl_compile_status"] == "MDL_NOT_ATTEMPTED"
    assert lighting_info["light_path"] == LIQUID_PRESENTATION_LIGHT_PATH
    assert lighting_info["role"] == "leadership_presentation_key_light"


def test_define_presentation_camera_reuses_leadership_closeup_framing():
    from pxr import Usd, UsdGeom
    from tools.labutopia_fluid.run_beaker_collider_smoke import ColliderConfig

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    config = ColliderConfig(
        source_center=(0.31, 0.09, 0.80),
        target_center=(0.28, -0.22, 0.80),
        source_radius=0.06,
        target_radius=0.08,
        table_z=0.70,
        source_height=0.20,
        target_height=0.20,
        particle_count=50000,
        steps=120,
        trace_interval=10,
        tail_window_steps=30,
    )

    info = _define_liquid_presentation_camera(stage, config)

    assert info["camera_path"] == LIQUID_PRESENTATION_CAMERA_PATH
    assert info["role"] == "leadership_presentation_main"
    assert math.isclose(info["target"][0], 0.3016)
    assert math.isclose(info["target"][1], 0.0032)
    assert info["eye"][1] > config.source_center[1]
    assert info["source_side_y"] == 1.0
    assert info["pair_span"] > 0.40
    assert info["focus_source_weight"] == 0.72
    assert info["target"][2] > config.table_z
    assert info["eye"][2] - info["target"][2] > 0.25
    assert stage.GetPrimAtPath(LIQUID_PRESENTATION_CAMERA_PATH)


def test_native_step_video_parser_accepts_presentation_isosurface_video_flag():
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import build_arg_parser

    args = build_arg_parser().parse_args(
        [
            "--presentation-isosurface-video",
            "--disable-particle-debug-display",
        ]
    )

    assert args.presentation_isosurface_video is True
    assert args.disable_particle_debug_display is True


def test_build_native_scene_video_summary_records_presentation_slot():
    summary = build_native_scene_video_summary(
        frame_sources={
            "presentation_isosurface_frames/frame_0001.png": "presentation_isosurface_rgb",
            "beaker2_closeup_native_material_frames/frame_0001.png": "closeup_native_rgb",
        }
    )

    assert summary["presentation_isosurface_rgb_frame_count"] == 1
    assert "presentation_isosurface" in summary["native_scene_video_slots"]


def test_native_scene_claim_boundary_blocks_presentation_overclaims():
    boundary = build_native_scene_claim_boundary()

    assert "presentation_isosurface_video_recorded=true" in boundary["allowed"]
    assert "presentation_video_equals_physics_success" in boundary["blocked"]
    assert "isosurface_reconstruction_equals_zero_leak" in boundary["blocked"]
    assert "presentation_water_material_equals_labutopia51_visual_parity" in boundary["blocked"]
