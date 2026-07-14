from tools.labutopia_fluid.fluid_recipe import (
    PRESENTATION_RENDER_MODE_ISOSURFACE,
    PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS,
    RECIPE_DEFAULT_PARTICLE_COUNT,
    RECIPE_WRAPPER_VARIANT_ID,
    build_controlled_spawn_plan,
    build_fluid_recipe_claim_boundary,
    build_recipe_manifest,
    enable_isosurface_for_mode,
    enable_particle_omniglass_for_mode,
    presentation_video_enabled,
    resolve_presentation_render_mode,
)


def test_resolve_render_mode_back_compat_isosurface_flag():
    assert (
        resolve_presentation_render_mode(
            presentation_render_mode="none",
            presentation_isosurface_video=True,
        )
        == PRESENTATION_RENDER_MODE_ISOSURFACE
    )


def test_resolve_render_mode_explicit_particle_omniglass():
    assert (
        resolve_presentation_render_mode(
            presentation_render_mode="particle_omniglass",
            presentation_isosurface_video=False,
        )
        == PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS
    )


def test_particle_omniglass_does_not_enable_isosurface():
    mode = resolve_presentation_render_mode(
        presentation_render_mode="particle_omniglass",
        presentation_isosurface_video=True,  # ignored when mode is explicit
    )
    assert mode == PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS
    assert enable_isosurface_for_mode(mode) is False
    assert enable_particle_omniglass_for_mode(mode) is True
    assert presentation_video_enabled(mode) is True


def test_presentation_video_enabled_for_both_modes():
    assert presentation_video_enabled("isosurface") is True
    assert presentation_video_enabled("particle_omniglass") is True
    assert presentation_video_enabled("none") is False


def test_controlled_spawn_plan_4096_matches_g1_layout_family():
    plan = build_controlled_spawn_plan(4096, particle_seed=0)
    assert plan["controlled_spawn"] is True
    assert plan["raw_colleague_points_used"] is False
    assert plan["particle_count"] == 4096
    assert plan["spawn_layout"]["particle_spacing"] == 0.003
    assert plan["spawn_layout"]["grid_dims"] == (8, 8, 16)
    assert plan["spawn_layout"]["interior_inset"] >= 0.003
    assert plan["official_visual_a_compatible"] is False
    assert plan["wrapper_variant_id"] == RECIPE_WRAPPER_VARIANT_ID


def test_build_recipe_manifest_4096_defaults():
    manifest = build_recipe_manifest(particle_count=RECIPE_DEFAULT_PARTICLE_COUNT)
    assert manifest["recipe_id"] == "lab_001_fluid_recipe_v1"
    assert manifest["fluid_recipe_usd_exported"] is True
    assert manifest["wrapper_variant_id"] == "D4A_018"
    assert manifest["raw_colleague_points_used"] is False
    assert manifest["particle_count"] == 4096
    assert manifest["official_visual_a_compatible"] is False


def test_build_fluid_recipe_claim_boundary_blocks_leadership_overclaims():
    boundary = build_fluid_recipe_claim_boundary()
    assert "fluid_recipe_usd_exported=true" in boundary["allowed"]
    assert "controlled_spawn_not_raw_colleague_points=true" in boundary["allowed"]
    assert "recipe_not_g1_promotion_matrix=true" in boundary["allowed"]
    assert "leadership_video_equals_g1_promotion" in boundary["blocked"]
    assert "recipe_equals_g1_promotion_matrix" in boundary["blocked"]
    assert "recipe_equals_raw_colleague_50k_zero_leak" in boundary["blocked"]
    assert "omniglass_particle_equals_official_visual_a" in boundary["blocked"]
    assert "particle_omniglass_equals_liquid_ref_parity" in boundary["blocked"]
    assert "points_omniglass_equals_photoreal_water" in boundary["blocked"]
    assert "leadership_ready_without_human_visual_qa" in boundary["blocked"]


def test_g1_wrapper_bottom_overlap_matches_promotion():
    from tools.labutopia_fluid.fluid_recipe import g1_wrapper_bottom_overlap

    assert g1_wrapper_bottom_overlap(1024) == 0.012
    assert g1_wrapper_bottom_overlap(4096) == 0.012
    assert g1_wrapper_bottom_overlap(50000) == 0.016
