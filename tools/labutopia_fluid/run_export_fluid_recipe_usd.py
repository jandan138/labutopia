#!/usr/bin/env python3
"""Export A2 fluid recipe USD package from immutable colleague source scene."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.fluid_recipe import (
    RECIPE_DEFAULT_PARTICLE_COUNT,
    RECIPE_ID,
    RECIPE_MANIFEST_BASENAME,
    RECIPE_USD_BASENAME,
    RECIPE_WRAPPER_VARIANT_ID,
    SOURCE_USD_REL,
    build_controlled_spawn_plan,
    build_recipe_manifest,
    recipe_package_dir,
    source_usd_path,
)
from tools.labutopia_fluid.run_beaker_collider_smoke import ColliderConfig, build_source_particle_positions
from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import (
    BBox,
    _bbox_from_stage,
    _position_hash,
    apply_fluid_safe_wrapper_overlay,
)
from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import (
    _deactivate_original_fluid_prims,
)

CONTROLLED_SPAWN_POSITIONS_BASENAME = "controlled_spawn_positions.json"
FLUID_SAFE_WRAPPER_PATH = "/World/beaker2/FluidSafeWrapper"
COMPLETED_PBD_SCOPE_PATH = "/World/CompletedPBD"
RECIPE_SPAWN_POINTS_PATH = "/World/CompletedPBD/RecipeSpawnPoints"
FLUID_RECIPE_META_PATH = "/World/FluidRecipeMeta"

# Cached pour-tabletop bboxes for dry-run when pxr is unavailable.
_FALLBACK_SOURCE_BBOX = BBox(
    min=(0.2564758472940577, 0.03647585808365142, 0.8266558855450249),
    max=(0.36712894390182405, 0.1471289546914178, 0.917056322425485),
)
_FALLBACK_TARGET_BBOX = BBox(
    min=(0.2010661906964822, -0.29893379419808785, 0.8093182448089536),
    max=(0.3559805130656398, -0.1440194718289303, 0.9358788459176023),
)
_FALLBACK_TABLE_TOP_Z = 0.7727606155217077

_PXR_IMPORT_ERROR = (
    "pxr (OpenUSD) is required for fluid recipe USD export. "
    "Install OpenUSD or run with --dry-run to write manifest and positions JSON only."
)


def _require_pxr() -> Any:
    try:
        from pxr import Usd
    except ImportError as exc:
        raise ImportError(_PXR_IMPORT_ERROR) from exc
    return Usd


def _rel_repo_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _build_spawn_collider_config(
    *,
    plan: dict[str, Any],
    source_bbox: BBox,
    target_bbox: BBox,
    table_top_z: float,
) -> ColliderConfig:
    from tools.labutopia_fluid.full_scene_spawn_frame import build_controlled_spawn_collider_config

    return build_controlled_spawn_collider_config(
        source_bbox=source_bbox,
        target_bbox=target_bbox,
        table_top_z=table_top_z,
        plan=plan,
    )


def _build_wrapper_config(config: ColliderConfig, *, particle_count: int, mesh_floor_z: float | None = None) -> ColliderConfig:
    return ColliderConfig(
        source_center=config.source_center,
        source_radius=config.source_radius,
        wall_height=config.wall_height,
        table_z=float(mesh_floor_z) if mesh_floor_z is not None else float(config.table_z),
        wall_thickness=0.026,
        bottom_overlap=float(config.bottom_overlap),
        bottom_thickness=float(config.bottom_thickness),
        particle_contact_offset=config.particle_contact_offset,
        collider_contact_offset=max(config.collider_contact_offset, 0.004),
        collider_rest_offset=config.collider_rest_offset,
        particle_enable_ccd=True,
    )


def _read_tabletop_bboxes(usd_path: Path) -> tuple[BBox, BBox, float]:
    Usd = _require_pxr()
    stage = Usd.Stage.Open(str(usd_path), Usd.Stage.LoadAll)
    if stage is None:
        raise RuntimeError(f"usd_stage_open_failed:{usd_path}")
    source_bbox = _bbox_from_stage(stage, "/World/beaker2")
    target_bbox = _bbox_from_stage(stage, "/World/beaker1")
    table_bbox = _bbox_from_stage(stage, "/World/table")
    return source_bbox, target_bbox, float(table_bbox.max[2])


def _resolve_tabletop_bboxes(
    *,
    source_path: Path,
    dry_run: bool,
) -> tuple[BBox, BBox, float, str]:
    try:
        _require_pxr()
    except ImportError:
        if dry_run:
            return (
                _FALLBACK_SOURCE_BBOX,
                _FALLBACK_TARGET_BBOX,
                _FALLBACK_TABLE_TOP_Z,
                "fallback_cached_bboxes",
            )
        raise
    if not source_path.is_file():
        if dry_run:
            return (
                _FALLBACK_SOURCE_BBOX,
                _FALLBACK_TARGET_BBOX,
                _FALLBACK_TABLE_TOP_Z,
                "fallback_cached_bboxes",
            )
        raise FileNotFoundError(f"source_usd_missing:{source_path}")
    source_bbox, target_bbox, table_top_z = _read_tabletop_bboxes(source_path)
    return source_bbox, target_bbox, table_top_z, "source_usd_bbox_cache"


def _jsonable_positions(positions: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[float(p[0]), float(p[1]), float(p[2])] for p in positions]


def _derive_recipe_stage(*, source_path: Path, recipe_path: Path) -> Any:
    Usd = _require_pxr()
    if source_path.resolve() == recipe_path.resolve():
        raise ValueError("recipe_usd_must_not_equal_source_usd")
    source_stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)
    if source_stage is None:
        raise RuntimeError(f"usd_stage_open_failed:{source_path}")
    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    source_stage.Export(str(recipe_path), addSourceFileComment=False)
    recipe_stage = Usd.Stage.Open(str(recipe_path), Usd.Stage.LoadAll)
    if recipe_stage is None:
        raise RuntimeError(f"usd_stage_open_failed:{recipe_path}")
    return recipe_stage


def _author_recipe_usd_content(
    stage: Any,
    *,
    plan: dict[str, Any],
    spawn_config: ColliderConfig,
    positions: Sequence[Sequence[float]],
    mesh_floor_z: float | None = None,
) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom

    stage.SetEditTarget(stage.GetRootLayer())
    wrapper_config = _build_wrapper_config(
        spawn_config,
        particle_count=int(plan["particle_count"]),
        mesh_floor_z=mesh_floor_z,
    )

    wrapper_summary: dict[str, Any]
    if stage.GetPrimAtPath(FLUID_SAFE_WRAPPER_PATH):
        wrapper_summary = {"skipped": True, "reason": "existing_fluid_safe_wrapper"}
    else:
        wrapper_summary = {
            "skipped": False,
            "authoring": apply_fluid_safe_wrapper_overlay(
                stage,
                wrapper_config,
                parent_path="/World/beaker2",
                visual_mesh_path="/World/beaker2/mesh",
                panel_count=72,
                wall_thickness=0.026,
                bottom_overlap=float(wrapper_config.bottom_overlap),
                panel_arc_overlap_factor=1.35,
                panel_phase_offset_rad=math.pi / 72,
                panel_ring_count=2,
            ),
        }

    deactivate_summary = _deactivate_original_fluid_prims(stage)

    if not stage.GetPrimAtPath(COMPLETED_PBD_SCOPE_PATH):
        UsdGeom.Xform.Define(stage, COMPLETED_PBD_SCOPE_PATH)
    points = UsdGeom.Points.Define(stage, RECIPE_SPAWN_POINTS_PATH)
    points.CreatePointsAttr().Set([Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in positions])
    width = float(plan["spawn_layout"]["particle_width"])
    points.CreateWidthsAttr().Set([width] * len(positions))

    meta = UsdGeom.Scope.Define(stage, FLUID_RECIPE_META_PATH)
    meta_prim = meta.GetPrim()
    meta_prim.CreateAttribute("labutopia:recipeId", Sdf.ValueTypeNames.String).Set(RECIPE_ID)
    meta_prim.CreateAttribute("labutopia:particleCount", Sdf.ValueTypeNames.Int).Set(int(plan["particle_count"]))
    meta_prim.CreateAttribute("labutopia:wrapperVariantId", Sdf.ValueTypeNames.String).Set(RECIPE_WRAPPER_VARIANT_ID)
    meta_prim.CreateAttribute("labutopia:rawColleaguePointsUsed", Sdf.ValueTypeNames.Bool).Set(False)

    stage.GetRootLayer().Save()
    return {
        "wrapper": wrapper_summary,
        "original_fluid_deactivate": deactivate_summary,
        "completed_pbd_scope_path": COMPLETED_PBD_SCOPE_PATH,
        "recipe_spawn_points_path": RECIPE_SPAWN_POINTS_PATH,
        "fluid_recipe_meta_path": FLUID_RECIPE_META_PATH,
        "spawn_point_count": len(positions),
    }


def export_fluid_recipe_usd(
    *,
    particle_count: int = RECIPE_DEFAULT_PARTICLE_COUNT,
    particle_seed: int = 0,
    out_dir: Path | str | None = None,
    source_usd: Path | str | None = None,
    dry_run: bool = False,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    package_dir = Path(out_dir) if out_dir is not None else recipe_package_dir(root)
    source_path = Path(source_usd) if source_usd is not None else source_usd_path(root)
    recipe_path = package_dir / RECIPE_USD_BASENAME
    manifest_path = package_dir / RECIPE_MANIFEST_BASENAME
    positions_path = package_dir / CONTROLLED_SPAWN_POSITIONS_BASENAME

    if source_path.resolve() == recipe_path.resolve():
        raise ValueError("recipe_usd_must_not_equal_source_usd")

    plan = build_controlled_spawn_plan(particle_count, particle_seed=particle_seed)
    source_bbox, target_bbox, table_top_z, bbox_provenance = _resolve_tabletop_bboxes(
        source_path=source_path,
        dry_run=dry_run,
    )
    spawn_config = _build_spawn_collider_config(
        plan=plan,
        source_bbox=source_bbox,
        target_bbox=target_bbox,
        table_top_z=table_top_z,
    )
    positions = build_source_particle_positions(spawn_config)
    positions_hash = _position_hash(positions)

    package_dir.mkdir(parents=True, exist_ok=True)
    positions_path.write_text(
        json.dumps(_jsonable_positions(positions), indent=2),
        encoding="utf-8",
    )

    manifest = build_recipe_manifest(
        particle_count=particle_count,
        particle_seed=particle_seed,
        source_usd=_rel_repo_path(source_path, root),
        recipe_usd=_rel_repo_path(recipe_path, root),
        positions_hash=positions_hash,
        extra={
            "controlled_spawn_positions_json": _rel_repo_path(positions_path, root),
            "bbox_provenance": bbox_provenance,
            "fluid_recipe_usd_exported": False if dry_run else True,
            "dry_run": bool(dry_run),
        },
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    summary: dict[str, Any] = {
        "dry_run": bool(dry_run),
        "recipe_id": RECIPE_ID,
        "wrapper_variant_id": RECIPE_WRAPPER_VARIANT_ID,
        "particle_count": int(particle_count),
        "particle_seed": int(particle_seed),
        "raw_colleague_points_used": False,
        "controlled_spawn": True,
        "source_usd": str(source_path),
        "recipe_usd": str(recipe_path),
        "recipe_manifest": str(manifest_path),
        "controlled_spawn_positions_json": str(positions_path),
        "positions_hash": positions_hash,
        "spawn_point_count": len(positions),
        "bbox_provenance": bbox_provenance,
        "fluid_recipe_usd_exported": False,
    }

    if dry_run:
        return summary

    if not source_path.is_file():
        raise FileNotFoundError(f"source_usd_missing:{source_path}")

    stage = _derive_recipe_stage(source_path=source_path, recipe_path=recipe_path)
    authoring_summary = _author_recipe_usd_content(
        stage,
        plan=plan,
        spawn_config=spawn_config,
        positions=positions,
        mesh_floor_z=float(source_bbox.min[2]),
    )
    summary.update(
        {
            "fluid_recipe_usd_exported": True,
            **authoring_summary,
        }
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--particle-count", type=int, default=RECIPE_DEFAULT_PARTICLE_COUNT)
    parser.add_argument("--particle-seed", type=int, default=0)
    parser.add_argument("--out-dir", default=None, help="Recipe package directory.")
    parser.add_argument("--source-usd", default=SOURCE_USD_REL, help="Immutable source USD path.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write manifest and controlled_spawn_positions.json only; do not write recipe USD.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    source = Path(args.source_usd)
    if not source.is_absolute():
        source = REPO_ROOT / source
    out_dir = Path(args.out_dir) if args.out_dir else None
    summary = export_fluid_recipe_usd(
        particle_count=args.particle_count,
        particle_seed=args.particle_seed,
        out_dir=out_dir,
        source_usd=source,
        dry_run=args.dry_run,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
