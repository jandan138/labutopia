"""Helpers for LabUtopia fluid recipe USD (A2) and dual presentation render modes (B2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PRESENTATION_RENDER_MODE_NONE = "none"
PRESENTATION_RENDER_MODE_ISOSURFACE = "isosurface"
PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS = "particle_omniglass"
PRESENTATION_RENDER_MODES = (
    PRESENTATION_RENDER_MODE_NONE,
    PRESENTATION_RENDER_MODE_ISOSURFACE,
    PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS,
)

RECIPE_PACKAGE_DIRNAME = "lab_001_fluid_recipe_v1"
RECIPE_USD_BASENAME = "lab_001_level1_pour_tabletop_fluid_recipe_v1.usd"
RECIPE_MANIFEST_BASENAME = "recipe_manifest.json"
RECIPE_DEFAULT_PARTICLE_COUNT = 4096
RECIPE_ID = "lab_001_fluid_recipe_v1"
RECIPE_WRAPPER_VARIANT_ID = "D4A_018"
SOURCE_USD_REL = (
    "outputs/usd_asset_packages/lab_001_localized_20260707/"
    "lab_001_level1_pour_tabletop_with_liquid.usd"
)


def recipe_package_dir(repo_root: Path | str | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    return root / "outputs" / "usd_asset_packages" / RECIPE_PACKAGE_DIRNAME


def recipe_usd_path(repo_root: Path | str | None = None) -> Path:
    return recipe_package_dir(repo_root) / RECIPE_USD_BASENAME


def source_usd_path(repo_root: Path | str | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    return root / SOURCE_USD_REL


def resolve_presentation_render_mode(
    *,
    presentation_render_mode: str | None,
    presentation_isosurface_video: bool,
) -> str:
    """Resolve render mode with back-compat for --presentation-isosurface-video."""
    mode = (presentation_render_mode or PRESENTATION_RENDER_MODE_NONE).strip()
    if mode not in PRESENTATION_RENDER_MODES:
        raise ValueError(f"unknown presentation_render_mode:{mode}")
    if mode == PRESENTATION_RENDER_MODE_NONE and presentation_isosurface_video:
        return PRESENTATION_RENDER_MODE_ISOSURFACE
    return mode


def presentation_video_enabled(render_mode: str) -> bool:
    return render_mode in (
        PRESENTATION_RENDER_MODE_ISOSURFACE,
        PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS,
    )


def enable_isosurface_for_mode(render_mode: str) -> bool:
    return render_mode == PRESENTATION_RENDER_MODE_ISOSURFACE


def enable_particle_omniglass_for_mode(render_mode: str) -> bool:
    return render_mode == PRESENTATION_RENDER_MODE_PARTICLE_OMNIGLASS


def build_controlled_spawn_plan(particle_count: int, *, particle_seed: int = 0) -> dict[str, Any]:
    """G1-style controlled spawn plan for recipe / leadership holds."""
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import d4_promotion_spawn_layout

    layout = d4_promotion_spawn_layout(int(particle_count))
    return {
        "controlled_spawn": True,
        "raw_colleague_points_used": False,
        "particle_count": int(particle_count),
        "particle_seed": int(particle_seed),
        "wrapper_variant_id": RECIPE_WRAPPER_VARIANT_ID,
        "spawn_layout": dict(layout),
        "recipe_id": RECIPE_ID,
        "official_visual_a_compatible": False,
    }


def build_recipe_manifest(
    *,
    particle_count: int = RECIPE_DEFAULT_PARTICLE_COUNT,
    particle_seed: int = 0,
    source_usd: str | None = None,
    recipe_usd: str | None = None,
    positions_hash: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = build_controlled_spawn_plan(particle_count, particle_seed=particle_seed)
    manifest: dict[str, Any] = {
        "recipe_id": RECIPE_ID,
        "fluid_recipe_usd_exported": True,
        "source_usd": source_usd or SOURCE_USD_REL,
        "recipe_usd": recipe_usd
        or f"outputs/usd_asset_packages/{RECIPE_PACKAGE_DIRNAME}/{RECIPE_USD_BASENAME}",
        "wrapper_variant_id": RECIPE_WRAPPER_VARIANT_ID,
        "controlled_spawn": True,
        "raw_colleague_points_used": False,
        "particle_count": int(particle_count),
        "particle_seed": int(particle_seed),
        "spawn_layout": plan["spawn_layout"],
        "positions_hash": positions_hash,
        "official_visual_a_compatible": False,
        "leadership_default_density": RECIPE_DEFAULT_PARTICLE_COUNT,
        "claim_boundary": build_fluid_recipe_claim_boundary(),
    }
    if extra:
        manifest.update(extra)
    return manifest


def build_fluid_recipe_claim_boundary() -> dict[str, list[str]]:
    return {
        "allowed": [
            "fluid_recipe_usd_exported=true",
            "controlled_spawn_not_raw_colleague_points=true",
            "leadership_look_candidate_recorded=true",
            "readback_classification_honest=true",
            "presentation_render_mode=particle_omniglass",
            "presentation_render_mode=isosurface",
            "recipe_not_g1_promotion_matrix=true",
        ],
        "blocked": [
            "recipe_equals_raw_colleague_50k_zero_leak",
            "leadership_video_equals_g1_promotion",
            "recipe_equals_g1_promotion_matrix",
            "omniglass_particle_equals_official_visual_a",
            "particle_omniglass_equals_liquid_ref_parity",
            "points_omniglass_equals_photoreal_water",
            "presentation_video_equals_physics_success",
            "isosurface_reconstruction_equals_zero_leak",
            "leadership_ready_without_human_visual_qa",
            "真实水",
            "photoreal",
            "video=physics success",
        ],
    }


def g1_wrapper_bottom_overlap(particle_count: int) -> float:
    """Match D4 promotion: 0.012 for ≤4096, 0.016 for 50k rung."""
    return 0.016 if int(particle_count) >= 50000 else 0.012



def merge_claim_boundaries(*boundaries: dict[str, list[str]]) -> dict[str, list[str]]:
    allowed: list[str] = []
    blocked: list[str] = []
    seen_allowed: set[str] = set()
    seen_blocked: set[str] = set()
    for boundary in boundaries:
        for item in boundary.get("allowed", []):
            if item not in seen_allowed:
                seen_allowed.add(item)
                allowed.append(item)
        for item in boundary.get("blocked", []):
            if item not in seen_blocked:
                seen_blocked.add(item)
                blocked.append(item)
    return {"allowed": allowed, "blocked": blocked}
