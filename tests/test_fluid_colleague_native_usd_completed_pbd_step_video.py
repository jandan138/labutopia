import math
from pathlib import Path

from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
    DEFAULT_USD,
    EVIDENCE_PARTICLE_SET_PATH,
    EVIDENCE_PARTICLE_SYSTEM_PATH,
    ISAACSIM41_CORE_MDL_ROOT,
    LIQUID_PRESENTATION_CAMERA_PATH,
    LIQUID_PRESENTATION_DOME_LIGHT_PATH,
    LIQUID_PRESENTATION_LIGHT_PATH,
    LIQUID_PRESENTATION_LIGHTING_HASH,
    LIQUID_PRESENTATION_MATERIAL_PATH,
    LIQUID_PRESENTATION_RTX_HASH,
    NATIVE_SCENE_COMPLETED_PBD_VARIANT_ID,
    PRESENTATION_MAX_REFRACTION_BOUNCES,
    PRESENTATION_POSTPROCESS_HASH,
    PRESENTATION_WATER_MDL_ASSET,
    PRESENTATION_WATER_MDL_SUB_IDENTIFIER,
    PRODUCT_WATER_FX_HASH,
    RUNTIME_PARTICLE_SET_PATH,
    RUNTIME_PARTICLE_SYSTEM_PATH,
    VLA_FALLBACK_MATERIAL_HASH,
    VLA_MDL_MATERIAL_HASH,
    VISUAL_ACCEPTANCE_SCENARIO_A_STATIC_CLEAR_WATER,
    NativeMaterialExpectation,
    _deactivate_original_fluid_prims,
    _define_liquid_presentation_camera,
    _author_liquid_presentation_lighting,
    _author_liquid_presentation_water_material,
    apply_presentation_render_settings,
    author_product_water_fx,
    build_liquid_presentation_isosurface_contract,
    build_native_scene_claim_boundary,
    build_native_scene_video_summary,
    build_presentation_postprocess_contract,
    build_presentation_render_settings_contract,
    build_presentation_visual_contract,
    build_presentation_water_mdl_material_info,
    build_presentation_water_preview_fallback_info,
    build_product_water_fx_contract,
    build_isaacsim41_core_mdl_closure_plan,
    build_visual_acceptance_provenance,
    build_vla_water_overlay,
    inspect_native_material_bindings,
    official_visual_a_claim_allowed,
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


def test_build_presentation_postprocess_contract_matches_spec_anisotropy_and_smoothing():
    contract = build_presentation_postprocess_contract()

    assert contract["enabled"] is True
    assert contract["api_path"] == "/World/CompletedPBD/ParticleSystem"
    assert contract["anisotropy"]["enabled"] is True
    assert contract["anisotropy"]["scale"] == 5.0
    assert contract["anisotropy"]["min"] == 1.0
    assert contract["anisotropy"]["max"] == 2.0
    assert contract["smoothing"]["enabled"] is True
    assert contract["smoothing"]["strength"] == 0.5
    assert contract["postprocess_hash"] == PRESENTATION_POSTPROCESS_HASH
    assert contract["postprocess_hash"] == "anisotropy_5_1_2_smoothing_0_5_v1"
    assert contract["claim_boundary"] == "visual_surface_reconstruction_only"
    assert contract["affects_leak_classification"] is False


def test_build_presentation_visual_contract_separates_visual_video_from_gate():
    postprocess_contract = build_presentation_postprocess_contract()
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
        postprocess_contract=postprocess_contract,
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
    assert contract["postprocess"] == postprocess_contract
    assert contract["postprocess"]["anisotropy"]["scale"] == 5.0
    assert contract["postprocess"]["smoothing"]["strength"] == 0.5
    assert contract["postprocess"]["claim_boundary"] == "visual_surface_reconstruction_only"
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
    assert lighting_info["role"] == "leadership_presentation_dome_key"
    assert lighting_info["lighting_contract_hash"] == "liquid_presentation_dome_key_v2"


def test_presentation_lighting_authors_dome_and_key_with_v2_contract_hash():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")

    lighting_info = _author_liquid_presentation_lighting(stage)

    key_prim = stage.GetPrimAtPath(LIQUID_PRESENTATION_LIGHT_PATH)
    dome_prim = stage.GetPrimAtPath(LIQUID_PRESENTATION_DOME_LIGHT_PATH)
    assert key_prim
    assert key_prim.GetTypeName() == "DistantLight"
    assert dome_prim
    assert dome_prim.GetTypeName() == "DomeLight"
    assert lighting_info["light_path"] == LIQUID_PRESENTATION_LIGHT_PATH
    assert lighting_info["key_light_path"] == LIQUID_PRESENTATION_LIGHT_PATH
    assert lighting_info["dome_light_path"] == LIQUID_PRESENTATION_DOME_LIGHT_PATH
    assert lighting_info["role"] == "leadership_presentation_dome_key"
    assert lighting_info["lighting_contract_hash"] == LIQUID_PRESENTATION_LIGHTING_HASH
    assert lighting_info["lighting_contract_hash"] == "liquid_presentation_dome_key_v2"


def test_build_presentation_render_settings_contract_records_refraction_bounces():
    contract = build_presentation_render_settings_contract()

    assert contract["rtx_hash"] == LIQUID_PRESENTATION_RTX_HASH
    assert contract["rtx_hash"] == "liquid_presentation_rtx_v1"
    assert contract["max_refraction_bounces"] == PRESENTATION_MAX_REFRACTION_BOUNCES
    assert contract["max_refraction_bounces"] >= 12
    assert contract["setting_path"] == "/rtx/translucency/maxRefractionBounces"
    assert contract["claim_boundary"] == "presentation_render_settings_only"


def test_apply_presentation_render_settings_records_actual_rtx_value():
    recorded: dict[str, object] = {}

    class _FakeSettings:
        def set(self, path: str, value: object) -> None:
            recorded[path] = value

        def get(self, path: str) -> object:
            return recorded.get(path)

    contract = apply_presentation_render_settings(_FakeSettings())

    assert recorded["/rtx/translucency/maxRefractionBounces"] == 12
    assert contract["max_refraction_bounces"] == 12
    assert contract["max_refraction_bounces"] >= 12
    assert contract["rtx_hash"] == "liquid_presentation_rtx_v1"
    assert contract["setting_path"] == "/rtx/translucency/maxRefractionBounces"


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
    assert info["camera_contract_hash"] == "liquid_presentation_main_camera_v1"
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
    assert "official_visual_a_rubric_pass_without_physics_a_provenance" in boundary["blocked"]
    assert "visual_a_static_clear_water_accepted_without_pass_source_hold" in boundary["blocked"]

def test_build_product_water_fx_contract_is_always_disabled_stub():
    contract = build_product_water_fx_contract()

    assert contract["enabled"] is False
    assert contract["schema_version"] == 1
    assert contract["affects_particle_dynamics"] is False
    assert contract["affects_leak_classification"] is False
    assert contract["affects_vla_overlay"] is False
    assert contract["apply_to_particle_system_prim"] == RUNTIME_PARTICLE_SYSTEM_PATH
    assert contract["apply_to_particle_set_prim"] == RUNTIME_PARTICLE_SET_PATH
    assert contract["diffuse_particles"]["enabled"] is False
    assert contract["diffuse_particles"]["api"] == "PhysxDiffuseParticlesAPI"
    assert contract["diffuse_particles"]["roles"] == ["splash", "foam", "spray", "bubbles"]
    assert contract["diffuse_particles"]["params"] == {}
    assert contract["flow_composite"]["enabled"] is False
    assert contract["flow_composite"]["extension"] == "omni.flowusd"
    assert contract["flow_composite"]["optional_gate"] == "cli:--product-water-fx-flow"
    assert contract["wetting"]["enabled"] is False
    assert contract["wetting"]["mode"] == "reserved"
    assert contract["wetting"]["native_api_available"] is None
    assert contract["wetting"]["probe_at_runtime"] is True
    assert contract["reserved_keys_ok"] is True
    assert contract["product_fx_hash"] == PRODUCT_WATER_FX_HASH
    assert contract["product_fx_hash"] == "product_water_fx_disabled_v1"


def test_author_product_water_fx_is_noop():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    before = [str(p.GetPath()) for p in stage.Traverse()]

    result = author_product_water_fx(stage, enabled=True)

    after = [str(p.GetPath()) for p in stage.Traverse()]
    assert result["authored"] is False
    assert result["enabled"] is False
    assert result["noop"] is True
    assert after == before


def test_build_vla_water_overlay_material_hash_valid_only_on_mdl_pass():
    pass_overlay = build_vla_water_overlay(
        material_backend="MDL_WATER",
        mdl_compile_status="PASS",
        lighting_hash="liquid_presentation_dome_key_v2",
        postprocess_hash=PRESENTATION_POSTPROCESS_HASH,
    )
    assert pass_overlay["material_hash"] == VLA_MDL_MATERIAL_HASH
    assert pass_overlay["material_hash"] == "omnisurface_clearwater_mdl_v1"
    assert pass_overlay["fallback_material_hash"] == VLA_FALLBACK_MATERIAL_HASH
    assert pass_overlay["fallback_material_hash"] == "usd_preview_near_clear_v1"
    assert pass_overlay["product_fx_hash"] == PRODUCT_WATER_FX_HASH
    assert pass_overlay["active_material_hash_must_match_backend"] is True
    assert pass_overlay["isosurface_hash"] == "isaacsim41_fluid_isosurface_cup_demo_style_v1"
    assert pass_overlay["postprocess_hash"] == PRESENTATION_POSTPROCESS_HASH
    assert pass_overlay["lighting_hash"] == "liquid_presentation_dome_key_v2"
    assert pass_overlay["rtx_hash"] == "liquid_presentation_rtx_v1"

    fallback_overlay = build_vla_water_overlay(
        material_backend="USD_PREVIEW_FALLBACK",
        mdl_compile_status="FALLBACK_USED",
        lighting_hash="liquid_presentation_key_light_v1",
        postprocess_hash=PRESENTATION_POSTPROCESS_HASH,
    )
    assert fallback_overlay["material_hash"] is None
    assert fallback_overlay["fallback_material_hash"] == VLA_FALLBACK_MATERIAL_HASH
    assert fallback_overlay["product_fx_hash"] == PRODUCT_WATER_FX_HASH
    assert fallback_overlay["active_material_hash_must_match_backend"] is True


def test_build_presentation_visual_contract_includes_product_fx_and_vla_overlay():
    postprocess_contract = build_presentation_postprocess_contract()
    material_info = build_presentation_water_preview_fallback_info(mdl_bind_attempted=False)
    contract = build_presentation_visual_contract(
        variant_id="NATIVE_SDF_128",
        camera_info={
            "camera_path": LIQUID_PRESENTATION_CAMERA_PATH,
            "camera_contract_hash": "liquid_presentation_main_camera_v1",
            "eye": [0.5, -0.2, 1.0],
            "target": [0.3, 0.09, 0.86],
            "up": [0.0, 0.0, 1.0],
        },
        lighting_info={"lighting_contract_hash": "liquid_presentation_key_light_v1"},
        isosurface_contract={"enabled": True},
        postprocess_contract=postprocess_contract,
        material_path=LIQUID_PRESENTATION_MATERIAL_PATH,
        particle_count=50000,
        material_info=material_info,
    )

    assert contract["product_water_fx"]["enabled"] is False
    assert contract["product_water_fx"]["affects_leak_classification"] is False
    assert contract["product_water_fx"]["diffuse_particles"]["roles"] == [
        "splash",
        "foam",
        "spray",
        "bubbles",
    ]
    assert contract["product_water_fx"]["wetting"]["mode"] == "reserved"
    overlay = contract["vla_water_visual_contract"]["water_overlay"]
    assert overlay["material_hash"] is None
    assert overlay["fallback_material_hash"] == "usd_preview_near_clear_v1"
    assert overlay["product_fx_hash"] == "product_water_fx_disabled_v1"
    assert overlay["active_material_hash_must_match_backend"] is True
    assert contract["vla_water_visual_contract"]["schema_version"] == 1
    assert contract["vla_water_visual_contract"]["physics_authority"] == "particle_readback"


def test_native_step_video_parser_product_water_fx_defaults_off():
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import build_arg_parser

    default_args = build_arg_parser().parse_args([])
    assert default_args.product_water_fx is False

    enabled_args = build_arg_parser().parse_args(["--product-water-fx"])
    assert enabled_args.product_water_fx is True

    orthogonal = build_arg_parser().parse_args(
        ["--presentation-isosurface-video", "--product-water-fx"]
    )
    assert orthogonal.presentation_isosurface_video is True
    assert orthogonal.product_water_fx is True


def test_missing_visual_a_provenance_blocks_official_claim():
    provenance = build_visual_acceptance_provenance(
        visual_acceptance_scenario=VISUAL_ACCEPTANCE_SCENARIO_A_STATIC_CLEAR_WATER,
    )

    assert provenance["visual_acceptance_scenario"] == "A_static_clear_water"
    assert provenance["physics_trajectory_id"] is None
    assert provenance["physics_manifest_path"] is None
    assert provenance["seed"] is None
    assert provenance["particle_count"] is None
    assert provenance["wrapper_variant_id"] is None
    assert provenance["physics_classification"] is None
    assert provenance["required_for_official_visual_a"] is True
    assert provenance["missing_fields"]
    assert "physics_trajectory_id_or_manifest_path" in provenance["missing_fields"]
    assert "seed" in provenance["missing_fields"]
    assert "particle_count" in provenance["missing_fields"]
    assert "wrapper_variant_id" in provenance["missing_fields"]
    assert "physics_classification_pass_source_hold" in provenance["missing_fields"]
    assert provenance["official_visual_a_claim_allowed"] is False
    assert official_visual_a_claim_allowed(provenance) is False


def test_complete_visual_a_provenance_with_pass_source_hold_allows_official_claim():
    provenance = build_visual_acceptance_provenance(
        visual_acceptance_scenario=VISUAL_ACCEPTANCE_SCENARIO_A_STATIC_CLEAR_WATER,
        physics_trajectory_id="fluid_spike_d4_wrapper_g1_seed0_50k",
        seed=0,
        particle_count=50000,
        wrapper_variant_id="D4_WRAPPER_PANEL5_T008",
        physics_classification="PASS_SOURCE_HOLD",
    )

    assert provenance["visual_acceptance_scenario"] == "A_static_clear_water"
    assert provenance["physics_trajectory_id"] == "fluid_spike_d4_wrapper_g1_seed0_50k"
    assert provenance["seed"] == 0
    assert provenance["particle_count"] == 50000
    assert provenance["wrapper_variant_id"] == "D4_WRAPPER_PANEL5_T008"
    assert provenance["physics_classification"] == "PASS_SOURCE_HOLD"
    assert provenance["missing_fields"] == []
    assert provenance["official_visual_a_claim_allowed"] is True
    assert official_visual_a_claim_allowed(provenance) is True


def test_visual_a_provenance_accepts_manifest_path_instead_of_trajectory_id():
    provenance = build_visual_acceptance_provenance(
        visual_acceptance_scenario=VISUAL_ACCEPTANCE_SCENARIO_A_STATIC_CLEAR_WATER,
        physics_manifest_path=(
            "docs/labutopia_lab_poc/evidence_manifests/"
            "fluid_spike_s2_proxy_wrapper_design_20260709.json"
        ),
        seed=1,
        particle_count=1024,
        wrapper_variant_id="D4_WRAPPER_PANEL5_T008",
        physics_classification="PASS_SOURCE_HOLD",
    )

    assert provenance["physics_trajectory_id"] is None
    assert provenance["physics_manifest_path"].endswith(
        "fluid_spike_s2_proxy_wrapper_design_20260709.json"
    )
    assert "physics_trajectory_id_or_manifest_path" not in provenance["missing_fields"]
    assert provenance["official_visual_a_claim_allowed"] is True
    assert official_visual_a_claim_allowed(provenance) is True


def test_non_pass_physics_classification_blocks_official_visual_a():
    provenance = build_visual_acceptance_provenance(
        visual_acceptance_scenario=VISUAL_ACCEPTANCE_SCENARIO_A_STATIC_CLEAR_WATER,
        physics_trajectory_id="traj_fail",
        seed=0,
        particle_count=512,
        wrapper_variant_id="D4_WRAPPER_PANEL5_T008",
        physics_classification="FAIL_OUTSIDE_SOURCE",
    )

    assert provenance["physics_classification"] == "FAIL_OUTSIDE_SOURCE"
    assert "physics_classification_pass_source_hold" in provenance["missing_fields"]
    assert provenance["official_visual_a_claim_allowed"] is False
    assert official_visual_a_claim_allowed(provenance) is False


def test_build_presentation_visual_contract_embeds_visual_acceptance_provenance():
    postprocess_contract = build_presentation_postprocess_contract()
    provenance = build_visual_acceptance_provenance(
        visual_acceptance_scenario=VISUAL_ACCEPTANCE_SCENARIO_A_STATIC_CLEAR_WATER,
        physics_trajectory_id="traj_ok",
        seed=2,
        particle_count=4096,
        wrapper_variant_id="D4_WRAPPER_PANEL5_T008",
        physics_classification="PASS_SOURCE_HOLD",
    )
    contract = build_presentation_visual_contract(
        variant_id="NATIVE_SDF_128",
        camera_info={
            "camera_path": LIQUID_PRESENTATION_CAMERA_PATH,
            "camera_contract_hash": "liquid_presentation_main_camera_v1",
            "eye": [0.5, -0.2, 1.0],
            "target": [0.3, 0.09, 0.86],
            "up": [0.0, 0.0, 1.0],
        },
        lighting_info={"lighting_contract_hash": LIQUID_PRESENTATION_LIGHTING_HASH},
        isosurface_contract={"enabled": True},
        postprocess_contract=postprocess_contract,
        material_path=LIQUID_PRESENTATION_MATERIAL_PATH,
        particle_count=4096,
        visual_acceptance=provenance,
    )

    assert contract["visual_acceptance"]["visual_acceptance_scenario"] == "A_static_clear_water"
    assert contract["visual_acceptance"]["official_visual_a_claim_allowed"] is True
    assert contract["visual_acceptance"]["physics_trajectory_id"] == "traj_ok"
    assert contract["visual_acceptance"]["wrapper_variant_id"] == "D4_WRAPPER_PANEL5_T008"
    assert contract["official_visual_a_claim_allowed"] is True


def test_build_presentation_visual_contract_blocks_official_a_without_provenance():
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
        visual_acceptance_scenario=VISUAL_ACCEPTANCE_SCENARIO_A_STATIC_CLEAR_WATER,
    )

    assert contract["visual_acceptance"]["official_visual_a_claim_allowed"] is False
    assert contract["official_visual_a_claim_allowed"] is False
    assert official_visual_a_claim_allowed(contract["visual_acceptance"]) is False


def test_native_step_video_parser_accepts_visual_a_provenance_args():
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import build_arg_parser

    args = build_arg_parser().parse_args(
        [
            "--visual-acceptance-scenario",
            "A_static_clear_water",
            "--physics-trajectory-id",
            "traj_ok",
            "--physics-seed",
            "0",
            "--physics-particle-count",
            "50000",
            "--wrapper-variant-id",
            "D4_WRAPPER_PANEL5_T008",
            "--physics-classification",
            "PASS_SOURCE_HOLD",
        ]
    )
    assert args.visual_acceptance_scenario == "A_static_clear_water"
    assert args.physics_trajectory_id == "traj_ok"
    assert args.physics_seed == 0
    assert args.physics_particle_count == 50000
    assert args.wrapper_variant_id == "D4_WRAPPER_PANEL5_T008"
    assert args.physics_classification == "PASS_SOURCE_HOLD"
    assert args.physics_manifest_path is None
