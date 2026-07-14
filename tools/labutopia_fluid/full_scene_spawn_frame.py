"""Full-scene controlled-spawn frame aligned to beaker mesh / G1 wrapper (not table padding)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from tools.labutopia_fluid.run_beaker_collider_smoke import ColliderConfig
from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import BBox

# Weekly OmniGlass PASS seal on the full colleague USD (thicker than isolated
# G1 ≤4096: 0.008+0.012). Dense controlled stacks punch through the thinner seal.
FULL_SCENE_BOTTOM_THICKNESS = 0.012
FULL_SCENE_BOTTOM_OVERLAP = 0.018
FULL_SCENE_PARTICLE_WIDTH_CAP = 0.0006
FULL_SCENE_PARTICLE_WIDTH_CAP_4096 = 0.00045
FULL_SCENE_INTERIOR_INSET_FLOOR_4096 = 0.008
FULL_SCENE_SPAWN_EXTRA_LIFT = 0.015
FULL_SCENE_INITIAL_RADIAL_VELOCITY = 0.0


def build_full_scene_spawn_frame(
    *,
    source_bbox: BBox,
    target_bbox: BBox,
    table_top_z: float,
    particle_count: int = 1024,
) -> dict[str, Any]:
    """Derive spawn frame from beaker mesh AABB (G1-compatible on full lab USD).

    Unlike ``build_tabletop_region_config``, this does **not** inflate radius by
    +0.005. Spawn Z is anchored to the mesh floor, but classification
    ``table_z`` stays at the lab table top so ``below_table`` means under-table.

    Extra spawn lift keeps particle centers clear of the FluidSafeWrapper bottom
    plate. Wrapper Bottom itself is mesh-AABB anchored when ``visual_mesh_path``
    is set; ``mesh_floor_z`` is still the correct wrapper ``table_z`` fallback.
    """
    source_size = source_bbox.size
    target_size = target_bbox.size
    source_center = source_bbox.center
    target_center = target_bbox.center
    spawn_radius = round(max(source_size[0], source_size[1]) / 2.0, 6)
    classification_radius = round(spawn_radius + 0.005, 6)
    mesh_floor_z = round(float(source_bbox.min[2]), 6)
    table_top = round(float(table_top_z), 6)
    bottom_thickness = FULL_SCENE_BOTTOM_THICKNESS
    bottom_overlap = FULL_SCENE_BOTTOM_OVERLAP
    # Raise spawn reference clear of wrapper bottom plate top:
    # plate top ≈ mesh_floor + bottom_thickness + bottom_overlap/2.
    spawn_table_z = round(mesh_floor_z + bottom_overlap + FULL_SCENE_SPAWN_EXTRA_LIFT, 6)
    return {
        "spawn_radius": spawn_radius,
        "classification_radius": classification_radius,
        "mesh_floor_z": mesh_floor_z,
        "spawn_table_z": spawn_table_z,
        "classification_table_z": table_top,
        "table_top_z": table_top,
        "source_center_xy": (round(source_center[0], 6), round(source_center[1], 6)),
        "target_center_xy": (round(target_center[0], 6), round(target_center[1], 6)),
        "target_radius": round(max(target_size[0], target_size[1]) / 2.0, 6),
        "source_height": round(max(source_bbox.max[2] - mesh_floor_z + 0.02, source_size[2] + 0.02), 6),
        "target_height": round(max(target_bbox.max[2] - mesh_floor_z + 0.02, target_size[2] + 0.02), 6),
        "radius_padding_removed": True,
        "spawn_z_anchored_to_mesh_floor": True,
        "classification_z_is_table_top": True,
        "wall_thickness": 0.026,
        "bottom_thickness": bottom_thickness,
        "bottom_overlap": bottom_overlap,
        "wrapper_table_z": mesh_floor_z,
    }


def build_controlled_spawn_collider_config(
    *,
    source_bbox: BBox,
    target_bbox: BBox,
    table_top_z: float,
    plan: dict[str, Any],
    steps: int = 0,
    trace_interval: int = 1,
    tail_window_steps: int = 1,
    render_width: int = 512,
    render_height: int = 512,
    physics_dt: float = 1.0 / 60.0,
) -> ColliderConfig:
    """ColliderConfig for G1 controlled spawn on the full colleague scene.

    ``table_z`` here is the **spawn** reference (mesh floor + overlap lift).
    Use ``build_classification_collider_config`` for region/leak classification.
    """
    frame = build_full_scene_spawn_frame(
        source_bbox=source_bbox,
        target_bbox=target_bbox,
        table_top_z=table_top_z,
        particle_count=int(plan["particle_count"]),
    )
    layout = dict(plan["spawn_layout"])
    # Full-scene PhysX: G1 widths punch through wrapper bottom. Weekly PASS uses
    # ~0.0006. Cap toward that scale while keeping G1 spacing/inset/grid.
    spacing = float(layout["particle_spacing"])
    count = int(plan["particle_count"])
    width_cap = (
        FULL_SCENE_PARTICLE_WIDTH_CAP_4096
        if count >= 4096
        else FULL_SCENE_PARTICLE_WIDTH_CAP
    )
    width = min(float(layout["particle_width"]), width_cap)
    pco = min(float(layout["particle_contact_offset"]), max(width * 0.9, 0.0005))
    inset = float(layout["interior_inset"])
    if count >= 4096:
        inset = max(
            inset,
            FULL_SCENE_INTERIOR_INSET_FLOOR_4096,
            pco * 2.0,
            spacing * 2.0,
        )
    layout["particle_width"] = width
    layout["particle_contact_offset"] = pco
    layout["interior_inset"] = inset
    cx, cy = frame["source_center_xy"]
    tx, ty = frame["target_center_xy"]
    return ColliderConfig(
        particle_count=count,
        particle_seed=int(plan.get("particle_seed") or 0),
        grid_dims=tuple(layout["grid_dims"]),
        particle_spacing=spacing,
        particle_width=width,
        particle_contact_offset=pco,
        spawn_particle_contact_offset=pco,
        particle_system_contact_offset=pco * 1.5,
        solid_rest_offset=width * 0.99,
        fluid_rest_offset=width * 0.99 * 0.99 * 0.6,
        source_center=(cx, cy, float(frame["spawn_table_z"])),
        target_center=(tx, ty, float(frame["spawn_table_z"])),
        source_radius=float(frame["spawn_radius"]),
        target_radius=float(frame["target_radius"]),
        source_height=float(frame["source_height"]),
        target_height=float(frame["target_height"]),
        wall_height=0.12,
        wall_thickness=float(frame["wall_thickness"]),
        bottom_thickness=float(frame["bottom_thickness"]),
        bottom_overlap=float(frame["bottom_overlap"]),
        interior_inset=inset,
        collider_contact_offset=float(layout["collider_contact_offset"]),
        table_z=float(frame["spawn_table_z"]),
        steps=int(steps),
        physics_dt=float(physics_dt),
        trace_interval=int(trace_interval),
        tail_window_steps=int(tail_window_steps),
        render_width=int(render_width),
        render_height=int(render_height),
        particle_enable_ccd=True,
        # Full-scene hold: G1 default 0.08 radial kick is unused on the video
        # path (velocities authored as zero), but keep the pin explicit.
        initial_radial_velocity=FULL_SCENE_INITIAL_RADIAL_VELOCITY,
        spawn_prefer_interior=True,
    )


def build_classification_collider_config(
    spawn_config: ColliderConfig,
    *,
    classification_table_z: float,
) -> ColliderConfig:
    """Region/leak classifier config: below_table uses lab table top, not cup floor."""
    # Spawn table_z is raised above the lab table; keep the same world cup roof by
    # extending source/target height so the classification cylinder still covers
    # the particle stack.
    lift = float(spawn_config.table_z) - float(classification_table_z)
    return replace(
        spawn_config,
        table_z=float(classification_table_z),
        source_height=float(spawn_config.source_height) + max(lift, 0.0),
        target_height=float(spawn_config.target_height) + max(lift, 0.0),
    )


def spawn_frame_summary(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "spawn_radius": frame["spawn_radius"],
        "classification_radius": frame["classification_radius"],
        "mesh_floor_z": frame["mesh_floor_z"],
        "spawn_table_z": frame["spawn_table_z"],
        "classification_table_z": frame["classification_table_z"],
        "table_top_z": frame["table_top_z"],
        "wrapper_table_z": frame.get("wrapper_table_z", frame["mesh_floor_z"]),
        "radius_padding_removed": bool(frame["radius_padding_removed"]),
        "spawn_z_anchored_to_mesh_floor": bool(frame["spawn_z_anchored_to_mesh_floor"]),
        "classification_z_is_table_top": bool(frame["classification_z_is_table_top"]),
        "wall_thickness": frame["wall_thickness"],
        "bottom_thickness": frame["bottom_thickness"],
        "bottom_overlap": frame["bottom_overlap"],
    }
