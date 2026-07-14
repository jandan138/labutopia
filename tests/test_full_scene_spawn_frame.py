from tools.labutopia_fluid.fluid_recipe import build_controlled_spawn_plan
from tools.labutopia_fluid.full_scene_spawn_frame import (
    build_classification_collider_config,
    build_controlled_spawn_collider_config,
    build_full_scene_spawn_frame,
)
from tools.labutopia_fluid.run_beaker_collider_smoke import (
    build_source_particle_positions,
    compute_region_counts,
    source_particle_lower,
)
from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import BBox

# Cached colleague beaker2 / beaker1 / table from RECIPE_P1024 evidence.
_SOURCE_BBOX = BBox(
    min=(0.2564758472940577, 0.03647585808365142, 0.8266558855450249),
    max=(0.36712894390182405, 0.1471289546914178, 0.917056322425485),
)
_TARGET_BBOX = BBox(
    min=(0.2010661906964822, -0.29893379419808785, 0.8093182448089536),
    max=(0.3559805130656398, -0.1440194718289303, 0.9358788459176023),
)
_TABLE_TOP_Z = 0.7727606155217077


def test_spawn_radius_drops_bbox_padding():
    frame = build_full_scene_spawn_frame(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        particle_count=1024,
    )
    mesh_half = max(_SOURCE_BBOX.size[0], _SOURCE_BBOX.size[1]) / 2.0
    assert frame["spawn_radius"] == round(mesh_half, 6)
    assert frame["spawn_radius"] < round(mesh_half + 0.005, 6)
    assert frame["classification_radius"] == round(mesh_half + 0.005, 6)
    assert frame["mesh_floor_z"] == round(float(_SOURCE_BBOX.min[2]), 6)
    assert frame["classification_table_z"] == round(_TABLE_TOP_Z, 6)
    assert frame["spawn_table_z"] > frame["mesh_floor_z"]
    assert frame["spawn_table_z"] > frame["classification_table_z"]
    assert frame["radius_padding_removed"] is True
    assert frame["classification_z_is_table_top"] is True


def test_spawn_lower_clears_wrapper_bottom_plate():
    plan = build_controlled_spawn_plan(1024, particle_seed=0)
    config = build_controlled_spawn_collider_config(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        plan=plan,
    )
    frame = build_full_scene_spawn_frame(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        particle_count=1024,
    )
    lower_z = source_particle_lower(config)[2]
    plate_top = frame["mesh_floor_z"] + frame["bottom_thickness"] + frame["bottom_overlap"] / 2.0
    assert lower_z > plate_top + 0.003


def test_full_scene_caps_particle_width_vs_g1_layout():
    plan = build_controlled_spawn_plan(1024, particle_seed=0)
    config = build_controlled_spawn_collider_config(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        plan=plan,
    )
    assert config.particle_width <= 0.0006
    assert config.particle_width < plan["spawn_layout"]["particle_width"]
    assert config.bottom_overlap == 0.018
    assert config.bottom_thickness == 0.012
    assert config.initial_radial_velocity == 0.0
    assert config.spawn_prefer_interior is True


def test_full_scene_4096_uses_thicker_seal_and_inset_floor():
    plan = build_controlled_spawn_plan(4096, particle_seed=0)
    config = build_controlled_spawn_collider_config(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        plan=plan,
    )
    assert config.particle_width <= 0.00045
    assert config.interior_inset >= 0.008
    assert config.bottom_overlap == 0.018
    assert config.bottom_thickness == 0.012
    assert config.spawn_prefer_interior is True
    frame = build_full_scene_spawn_frame(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        particle_count=4096,
    )
    assert frame["wrapper_table_z"] == frame["mesh_floor_z"]
    assert frame["spawn_table_z"] > frame["wrapper_table_z"]


def test_full_scene_prefer_interior_keeps_stack_near_axis():
    plan = build_controlled_spawn_plan(4096, particle_seed=0)
    config = build_controlled_spawn_collider_config(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        plan=plan,
    )
    positions = build_source_particle_positions(config)
    cx, cy = config.source_center[0], config.source_center[1]
    radii = [((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5 for p in positions]
    # Outer-preferring G1 would pack near usable_radius; interior prefer should
    # keep the mean well inside half of source_radius.
    assert sum(radii) / len(radii) < config.source_radius * 0.55
    assert max(radii) <= config.source_radius - float(config.interior_inset) + 1e-9


def test_controlled_positions_step0_spill_zero_offline_1024():
    plan = build_controlled_spawn_plan(1024, particle_seed=0)
    spawn_config = build_controlled_spawn_collider_config(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        plan=plan,
    )
    frame = build_full_scene_spawn_frame(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        particle_count=1024,
    )
    classify_config = build_classification_collider_config(
        spawn_config,
        classification_table_z=frame["classification_table_z"],
    )
    positions = build_source_particle_positions(spawn_config)
    assert len(positions) == 1024
    counts = compute_region_counts(positions, classify_config)
    assert counts["spill_count"] == 0
    assert counts["below_table_count"] == 0
    assert counts["source_count"] == 1024


def test_controlled_positions_step0_spill_zero_offline_4096():
    plan = build_controlled_spawn_plan(4096, particle_seed=0)
    spawn_config = build_controlled_spawn_collider_config(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        plan=plan,
    )
    frame = build_full_scene_spawn_frame(
        source_bbox=_SOURCE_BBOX,
        target_bbox=_TARGET_BBOX,
        table_top_z=_TABLE_TOP_Z,
        particle_count=4096,
    )
    classify_config = build_classification_collider_config(
        spawn_config,
        classification_table_z=frame["classification_table_z"],
    )
    positions = build_source_particle_positions(spawn_config)
    assert len(positions) == 4096
    counts = compute_region_counts(positions, classify_config)
    assert counts["spill_count"] == 0
    assert counts["below_table_count"] == 0
