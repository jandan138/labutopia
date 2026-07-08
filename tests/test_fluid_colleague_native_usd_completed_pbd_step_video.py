from pathlib import Path

from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
    DEFAULT_USD,
    EVIDENCE_PARTICLE_SET_PATH,
    EVIDENCE_PARTICLE_SYSTEM_PATH,
    NATIVE_SCENE_COMPLETED_PBD_VARIANT_ID,
    NativeMaterialExpectation,
    _deactivate_original_fluid_prims,
    build_native_scene_claim_boundary,
    build_native_scene_video_summary,
    build_isaacsim41_core_mdl_closure_plan,
    inspect_native_material_bindings,
    scan_mdl_compile_errors,
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
