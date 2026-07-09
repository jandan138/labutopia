#!/usr/bin/env python3
"""Record completed-PBD particle step videos in the colleague native USD scene."""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import shutil
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import (
    BBox,
    EVIDENCE_PARTICLE_SET_PATH,
    EVIDENCE_PARTICLE_SYSTEM_PATH,
    _aabb,
    _bbox_from_stage,
    _centroid,
    _finite_positions,
    _make_review_camera_sensor,
    _nan_count,
    _position_hash,
    _read_points,
    _read_width,
    _tail_leak_rate,
    _try_write_camera_png_with_diagnostics,
    _update_review_markers,
    _write_mp4_from_frames,
    build_particle_scope_summary,
    build_tabletop_region_config,
    classify_colleague_trace,
    compute_region_counts,
    resolve_particle_runtime_offsets,
    select_particle_subset,
)


DEFAULT_USD = (
    "outputs/usd_asset_packages/lab_001_localized_20260707/"
    "lab_001_level1_pour_tabletop_with_liquid.usd"
)
DEFAULT_ARTIFACT_DIR = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708_001"
)
DEFAULT_MANIFEST = (
    "docs/labutopia_lab_poc/evidence_manifests/"
    "fluid_spike_colleague_native_usd_50k_completed_pbd_step_video_20260708.json"
)
NATIVE_CAMERA_PATHS = {
    "camera1_native_material": "/World/Camera1",
    "camera2_native_material": "/World/Camera2",
}
CLOSEUP_CAMERA_PATH = "/World/Beaker2CloseupNativeMaterialCamera"
LIQUID_PRESENTATION_CAMERA_PATH = "/World/LiquidPresentationMainCamera"
LIQUID_PRESENTATION_MATERIAL_PATH = "/World/Looks/LiquidPresentationWater"
LIQUID_PRESENTATION_LIGHT_PATH = "/World/LiquidPresentationKeyLight"
REVIEW_MARKER_ROOT = "/World/D3ReviewLeakMarkers"
RUNTIME_PBD_SCOPE_PATH = "/World/CompletedPBD"
RUNTIME_PARTICLE_SYSTEM_PATH = f"{RUNTIME_PBD_SCOPE_PATH}/ParticleSystem"
RUNTIME_PARTICLE_SET_PATH = f"{RUNTIME_PBD_SCOPE_PATH}/ParticleSet"
NATIVE_SCENE_COMPLETED_PBD_VARIANT_ID = "COLLEAGUE_NATIVE_USD_FULL_50K_COMPLETED_PBD"
ISAACSIM41_CORE_MDL_ROOT = Path("/isaac-sim/kit/mdl/core")
MATERIAL_CLOSURE_DIRNAME = "material_closure_isaacsim41_core"
CORE_MDL_DIRECT_ASSETS = ("OmniGlass.mdl", "OmniSurfacePresets.mdl", "OmniPBR.mdl")
CORE_MDL_TRANSITIVE_DEPENDENCIES = (
    "OmniGlass_Opacity.mdl",
    "OmniPBRBase.mdl",
    "OmniPBR_ClearCoat.mdl",
    "OmniSurface.mdl",
    "OmniSurfaceLite.mdl",
)
PRESENTATION_WATER_MDL_ASSET = "OmniSurfacePresets.mdl"
PRESENTATION_WATER_MDL_SUB_IDENTIFIER = "OmniSurface_ClearWater"
PRESENTATION_WATER_PREVIEW_DIFFUSE_COLOR = [0.74, 0.94, 1.0]
PRESENTATION_WATER_PREVIEW_EMISSIVE_COLOR = [0.0, 0.0, 0.0]
PRESENTATION_WATER_PREVIEW_OPACITY = 0.34
PRESENTATION_WATER_PREVIEW_ROUGHNESS = 0.02
PRESENTATION_WATER_PREVIEW_IOR = 1.333
MDL_COMPILE_STATUS_PASS = "PASS"
MDL_COMPILE_STATUS_FAIL = "MDL_COMPILE_FAIL"
MDL_COMPILE_STATUS_FALLBACK_USED = "FALLBACK_USED"
MDL_COMPILE_STATUS_NOT_ATTEMPTED = "MDL_NOT_ATTEMPTED"


@dataclass(frozen=True)
class NativeMaterialExpectation:
    minimal_native_slice_used: bool = False
    native_beaker_material_override_used: bool = False
    local_blue_glass_override_used: bool = False
    visual_material_parity_claim_allowed: bool = False


def scan_mdl_compile_errors(log_text: str, *, max_errors: int = 40) -> dict[str, Any]:
    """Summarize Isaac/MDL runtime compiler errors without treating path resolve as render success."""
    error_lines = []
    for raw_line in log_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        is_mdl_error = (
            "mdlc:compiler" in lower
            or "createmdlmodule failed" in lower
            or "failed to create mdl" in lower
        )
        if is_mdl_error and ("error" in lower or "failed" in lower or "comp error" in lower):
            error_lines.append(line)
    joined = "\n".join(error_lines).lower()
    return {
        "mdl_compile_status": MDL_COMPILE_STATUS_FAIL if error_lines else MDL_COMPILE_STATUS_PASS,
        "error_count": len(error_lines),
        "has_omniglass_compile_error": "omniglass" in joined,
        "has_omnisurface_compile_error": "omnisurface" in joined,
        "has_omnipbr_compile_error": "omnipbr" in joined,
        "errors": error_lines[:max_errors],
        "errors_truncated": len(error_lines) > max_errors,
    }


def scan_presentation_water_mdl_compile_errors(
    log_text: str,
    *,
    material_path: str = LIQUID_PRESENTATION_MATERIAL_PATH,
    max_errors: int = 40,
) -> dict[str, Any]:
    """Scan MDL compile errors scoped to the presentation-water shader path / ClearWater."""
    all_errors = scan_mdl_compile_errors(log_text, max_errors=10_000)
    material_token = material_path.lower()
    material_name = Path(material_path).name.lower()
    presentation_lines = []
    for line in all_errors["errors"]:
        lower = line.lower()
        if (
            material_token in lower
            or material_name in lower
            or "omnisurface_clearwater" in lower
            or (
                "omnisurfacepresets.mdl" in lower
                and ("clearwater" in lower or material_name in lower)
            )
        ):
            presentation_lines.append(line)
    joined = "\n".join(presentation_lines).lower()
    return {
        "mdl_compile_status": (
            MDL_COMPILE_STATUS_FAIL if presentation_lines else MDL_COMPILE_STATUS_PASS
        ),
        "error_count": len(presentation_lines),
        "has_presentation_water_compile_error": bool(presentation_lines),
        "has_omnisurface_compile_error": "omnisurface" in joined,
        "presentation_material_path": material_path,
        "errors": presentation_lines[:max_errors],
        "errors_truncated": len(presentation_lines) > max_errors,
        "native_scene_error_count": int(all_errors["error_count"]),
    }


def _presentation_water_common_fields() -> dict[str, Any]:
    return {
        "material_path": LIQUID_PRESENTATION_MATERIAL_PATH,
        "display_name": "presentation_water_unified_realistic",
        "preferred_backend": "MDL_WATER",
        "source_asset_basename": PRESENTATION_WATER_MDL_ASSET,
        "sub_identifier": PRESENTATION_WATER_MDL_SUB_IDENTIFIER,
        "tint_policy": "near_clear_subtle_blue_green",
        "unified_liquid_style": True,
        "state_specific_liquid_materials": False,
        "all_liquid_particles_visible": True,
        "visualization_only": True,
        "visual_material_parity_claim_allowed": False,
    }


def build_presentation_water_mdl_material_info(
    *,
    source_asset: str | Path,
    shader_path: str | None = None,
    bind_method: str = "usd_mdl_shader",
) -> dict[str, Any]:
    """Pure metadata builder for a successful OmniSurface_ClearWater MDL bind."""
    resolved = Path(source_asset)
    return {
        **_presentation_water_common_fields(),
        "shader_path": shader_path or f"{LIQUID_PRESENTATION_MATERIAL_PATH}/Shader",
        "material_backend": "MDL_WATER",
        "mdl_bind_attempted": True,
        "mdl_compile_status": MDL_COMPILE_STATUS_PASS,
        "fallback_reason": None,
        "source_asset": str(resolved),
        "bind_method": bind_method,
        "emissive_color": list(PRESENTATION_WATER_PREVIEW_EMISSIVE_COLOR),
    }


def build_presentation_water_preview_fallback_info(
    *,
    mdl_bind_attempted: bool,
    fallback_reason: str | None = None,
    shader_path: str | None = None,
) -> dict[str, Any]:
    """Pure metadata builder for UsdPreviewSurface fallback (honest MDL status)."""
    if mdl_bind_attempted:
        status = MDL_COMPILE_STATUS_FALLBACK_USED
        reason = fallback_reason or "mdl_bind_failed"
    else:
        status = MDL_COMPILE_STATUS_NOT_ATTEMPTED
        reason = fallback_reason or "preview_surface_without_mdl_bind_attempt"
    return {
        **_presentation_water_common_fields(),
        "shader_path": shader_path or f"{LIQUID_PRESENTATION_MATERIAL_PATH}/PreviewSurface",
        "material_backend": "USD_PREVIEW_FALLBACK",
        "mdl_bind_attempted": bool(mdl_bind_attempted),
        "mdl_compile_status": status,
        "fallback_reason": reason,
        "diffuse_color": list(PRESENTATION_WATER_PREVIEW_DIFFUSE_COLOR),
        "emissive_color": list(PRESENTATION_WATER_PREVIEW_EMISSIVE_COLOR),
        "opacity": PRESENTATION_WATER_PREVIEW_OPACITY,
        "roughness": PRESENTATION_WATER_PREVIEW_ROUGHNESS,
        "ior": PRESENTATION_WATER_PREVIEW_IOR,
        "bind_method": "usd_preview_surface",
    }


def resolve_presentation_water_mdl_source_asset(
    mdl_source_asset: str | Path | None = None,
    *,
    closure_base_dir: str | Path | None = None,
) -> Path | None:
    """Resolve OmniSurfacePresets.mdl from explicit path, local mirror, or Isaac core root."""
    candidates: list[Path] = []
    if mdl_source_asset is not None:
        candidates.append(Path(mdl_source_asset))
    if closure_base_dir is not None:
        candidates.append(Path(closure_base_dir) / PRESENTATION_WATER_MDL_ASSET)
    candidates.append(ISAACSIM41_CORE_MDL_ROOT / "Base" / PRESENTATION_WATER_MDL_ASSET)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def build_isaacsim41_core_mdl_closure_plan(source_asset_basenames: Sequence[str]) -> dict[str, Any]:
    requested = {Path(name).name for name in source_asset_basenames}
    mdl_files = sorted(requested.union(CORE_MDL_TRANSITIVE_DEPENDENCIES))
    return {
        "material_closure_mode": "isaacsim41_core_mdl_local_mirror",
        "source_root": str(ISAACSIM41_CORE_MDL_ROOT),
        "source_base_dir": str(ISAACSIM41_CORE_MDL_ROOT / "Base"),
        "source_omnisurface_module_dir": str(ISAACSIM41_CORE_MDL_ROOT / "mdl" / "OmniSurface"),
        "shader_asset_basenames": sorted(requested),
        "mdl_files": mdl_files,
        "copies_full_base_mdl_dir": True,
        "copies_omnisurface_module_dir": True,
        "visual_material_parity_claim_allowed": False,
    }


def _mirror_isaacsim41_core_mdl_closure(artifact_dir: Path) -> dict[str, Any]:
    source_base = ISAACSIM41_CORE_MDL_ROOT / "Base"
    source_omnisurface = ISAACSIM41_CORE_MDL_ROOT / "mdl" / "OmniSurface"
    if not source_base.exists():
        raise FileNotFoundError(f"missing_isaacsim41_core_mdl_base:{source_base}")
    closure_root = artifact_dir / MATERIAL_CLOSURE_DIRNAME
    closure_base = closure_root / "Base"
    closure_omnisurface = closure_root / "mdl" / "OmniSurface"
    closure_base.mkdir(parents=True, exist_ok=True)
    copied_base_files = []
    for source_path in sorted(source_base.glob("*.mdl")):
        target_path = closure_base / source_path.name
        shutil.copy2(source_path, target_path)
        copied_base_files.append(source_path.name)
    copied_omnisurface_files = []
    if source_omnisurface.exists():
        shutil.copytree(source_omnisurface, closure_omnisurface, dirs_exist_ok=True)
        copied_omnisurface_files = sorted(path.name for path in closure_omnisurface.glob("*.mdl"))
    return {
        **build_isaacsim41_core_mdl_closure_plan(CORE_MDL_DIRECT_ASSETS),
        "closure_root": str(closure_root),
        "closure_base_dir": str(closure_base),
        "closure_omnisurface_module_dir": str(closure_omnisurface),
        "copied_base_file_count": len(copied_base_files),
        "copied_base_files": copied_base_files,
        "copied_omnisurface_file_count": len(copied_omnisurface_files),
        "copied_omnisurface_files": copied_omnisurface_files,
    }


def _retarget_stage_mdl_source_assets(stage: Any, closure_summary: dict[str, Any]) -> dict[str, Any]:
    from pxr import Sdf

    closure_base = Path(closure_summary["closure_base_dir"])
    retargetable = set(CORE_MDL_DIRECT_ASSETS)
    retargeted = []
    stage.SetEditTarget(stage.GetRootLayer())
    for prim in stage.Traverse():
        attr = prim.GetAttribute("info:mdl:sourceAsset")
        if not attr:
            continue
        asset = attr.Get()
        basename = _source_asset_basename(asset)
        if basename not in retargetable:
            continue
        sub_identifier_attr = prim.GetAttribute("info:mdl:sourceAsset:subIdentifier")
        sub_identifier = sub_identifier_attr.Get() if sub_identifier_attr else None
        compatibility_fallback = None
        target_basename = basename
        target_sub_identifier = sub_identifier
        if basename == "OmniSurfacePresets.mdl" and sub_identifier == "OmniSurface_Glass":
            target_basename = "OmniGlass.mdl"
            target_sub_identifier = "OmniGlass"
            compatibility_fallback = "OmniSurface_Glass_to_OmniGlass_for_isaacsim41"
        target_path = closure_base / target_basename
        if not target_path.exists():
            continue
        attr.Set(Sdf.AssetPath(str(target_path)))
        if target_sub_identifier and sub_identifier_attr:
            sub_identifier_attr.Set(target_sub_identifier)
        retargeted.append(
            {
                "shader_path": str(prim.GetPath()),
                "source_asset_basename": basename,
                "source_sub_identifier": sub_identifier,
                "retargeted_source_asset_basename": target_basename,
                "retargeted_source_asset": str(target_path),
                "retargeted_sub_identifier": target_sub_identifier,
                "compatibility_fallback": compatibility_fallback,
            }
        )
    return {
        "retarget_enabled": True,
        "retargeted_shader_count": len(retargeted),
        "retargeted_shaders": retargeted,
    }


def _latest_isaac_log_path() -> Path | None:
    env_root = Path(sys.executable).resolve().parent.parent
    candidates = sorted(
        glob.glob(str(env_root / "lib/python*/site-packages/omni/logs/Kit/Isaac-Sim/4.1/kit_*.log")),
        key=lambda value: Path(value).stat().st_mtime if Path(value).exists() else 0.0,
    )
    return Path(candidates[-1]) if candidates else None


def _latest_isaac_log_summary() -> dict[str, Any]:
    log_path = _latest_isaac_log_path()
    if log_path is None or not log_path.exists():
        return {
            "isaac_log_path": None,
            "isaac_log_available": False,
            **scan_mdl_compile_errors(""),
        }
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "isaac_log_path": str(log_path),
            "isaac_log_available": False,
            "isaac_log_read_error": str(exc),
            **scan_mdl_compile_errors(""),
        }
    return {
        "isaac_log_path": str(log_path),
        "isaac_log_available": True,
        **scan_mdl_compile_errors(log_text),
    }


def _repo_path(path: str | Path) -> Path:
    normalized = Path(path)
    return normalized if normalized.is_absolute() else REPO_ROOT / normalized


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), allow_nan=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_trace_line(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_safe(payload), allow_nan=False, sort_keys=True) + "\n")


def _jsonable_positions(positions: Sequence[Sequence[float]]) -> list[list[float]]:
    return [[float(p[0]), float(p[1]), float(p[2])] for p in positions]


def _source_asset_basename(value: Any) -> str | None:
    if value is None:
        return None
    asset_path = getattr(value, "path", None) or getattr(value, "authoredPath", None)
    if asset_path is None:
        text = str(value)
        if "authoredPath='" in text:
            asset_path = text.split("authoredPath='", 1)[1].split("'", 1)[0]
        else:
            asset_path = text
    return Path(str(asset_path)).name


def _source_asset_resolved(value: Any) -> bool:
    resolved = getattr(value, "resolvedPath", None)
    return bool(resolved) and Path(str(resolved)).exists()


def _material_summary(stage: Any, prim_path: str) -> dict[str, Any]:
    from pxr import UsdShade

    prim = stage.GetPrimAtPath(prim_path)
    result: dict[str, Any] = {
        "prim_path": prim_path,
        "prim_exists": bool(prim),
        "material_path": None,
        "source_asset": None,
        "source_asset_resolved": False,
        "source_asset_resolved_path": None,
        "sub_identifier": None,
    }
    if not prim:
        return result
    material, binding_rel = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
    result["binding_relationship"] = binding_rel.GetName() if binding_rel else None
    if not material:
        return result
    result["material_path"] = str(material.GetPath())
    shader_prim = next(iter(material.GetPrim().GetChildren()), None)
    if not shader_prim:
        return result
    source_asset_attr = shader_prim.GetAttribute("info:mdl:sourceAsset")
    source_asset = source_asset_attr.Get() if source_asset_attr else None
    resolved_path = getattr(source_asset, "resolvedPath", None)
    result.update(
        {
            "source_asset": _source_asset_basename(source_asset),
            "source_asset_resolved": _source_asset_resolved(source_asset),
            "source_asset_resolved_path": str(resolved_path) if resolved_path else None,
            "sub_identifier": (
                shader_prim.GetAttribute("info:mdl:sourceAsset:subIdentifier").Get()
                if shader_prim.GetAttribute("info:mdl:sourceAsset:subIdentifier")
                else None
            ),
            "implementation_source": (
                shader_prim.GetAttribute("info:implementationSource").Get()
                if shader_prim.GetAttribute("info:implementationSource")
                else None
            ),
        }
    )
    return result


def inspect_native_material_bindings(usd_path: str | Path = DEFAULT_USD) -> dict[str, Any]:
    from pxr import Usd

    resolved_usd = _repo_path(usd_path)
    stage = Usd.Stage.Open(str(resolved_usd), Usd.Stage.LoadAll)
    if stage is None:
        return {
            "native_scene_opened": False,
            "usd_path": str(resolved_usd),
            "material_resolve_status": "STAGE_OPEN_FAIL",
        }
    summary = {
        "native_scene_opened": True,
        "usd_path": str(resolved_usd),
        "beaker2": _material_summary(stage, "/World/beaker2/mesh"),
        "beaker1": _material_summary(stage, "/World/beaker1/mesh"),
        "particle_system": _material_summary(stage, "/World/ParticleSystem"),
    }
    all_resolved = all(
        bool(summary[key]["source_asset_resolved"]) for key in ("beaker2", "beaker1", "particle_system")
    )
    summary["material_resolve_status"] = "PASS" if all_resolved else "MATERIAL_RESOLVE_FAIL"
    summary["all_native_mdl_resolved"] = all_resolved
    return summary


def build_liquid_presentation_isosurface_contract(
    *,
    fluid_rest_offset: float,
    particle_count: int,
) -> dict[str, Any]:
    spacing = float(fluid_rest_offset) * 0.9
    return {
        "enabled": True,
        "api_path": RUNTIME_PARTICLE_SYSTEM_PATH,
        "grid_spacing": spacing,
        "surface_distance": float(fluid_rest_offset) * 0.95,
        "grid_filtering_passes": "GS",
        "grid_smoothing_radius": float(fluid_rest_offset) * 1.0,
        "num_mesh_smoothing_passes": 4,
        "num_mesh_normal_smoothing_passes": 4,
        "max_vertices": max(1_000_000, int(particle_count) * 64),
        "max_triangles": max(2_000_000, int(particle_count) * 128),
        "max_subgrids": max(8192, int(math.ceil(max(int(particle_count), 1) / 4.0))),
        "parameter_reference": "isaacsim41_fluid_isosurface_cup_demo_style",
        "claim_boundary": "visual_surface_reconstruction_only",
    }


def build_presentation_visual_contract(
    *,
    variant_id: str | None,
    camera_info: dict[str, Any],
    lighting_info: dict[str, Any],
    isosurface_contract: dict[str, Any],
    material_path: str,
    particle_count: int,
) -> dict[str, Any]:
    claim_boundary_text = (
        "This video is a presentation render of the same simulated particle trajectory used for "
        "the diagnostic verdict. Leak classification and spike assessment are based on particle "
        "readback, not on visual appearance. Rendering choices including PhysX Isosurface "
        "reconstruction, material color/opacity, lighting, and camera framing were adjusted only "
        "to improve human readability for review. These adjustments do not change the particle "
        "simulation, collider setup, leak classifier, or benchmark claims."
    )
    return {
        "variant_id": variant_id,
        "camera_path": camera_info.get("camera_path"),
        "camera": dict(camera_info),
        "lighting": dict(lighting_info),
        "isosurface": dict(isosurface_contract),
        "liquid_material_path": material_path,
        "particle_count": int(particle_count),
        "debug_particle_display_enabled": False,
        "presentation_video_does_not_replace_particle_readback": True,
        "visual_material_parity_claim_allowed": False,
        "claim_boundary": "presentation_lane_only_particle_readback_remains_gate",
        "claim_boundary_text": claim_boundary_text,
    }


def _ensure_looks_scope(stage: Any) -> None:
    from pxr import Sdf, UsdGeom

    looks_path = Sdf.Path("/World/Looks")
    if not stage.GetPrimAtPath(looks_path):
        UsdGeom.Scope.Define(stage, looks_path)


def _author_presentation_water_preview_surface(stage: Any) -> str:
    from pxr import Gf, Sdf, UsdShade

    _ensure_looks_scope(stage)
    material_path = Sdf.Path(LIQUID_PRESENTATION_MATERIAL_PATH)
    material = UsdShade.Material.Define(stage, material_path)
    preview_path = material_path.AppendChild("PreviewSurface")
    mdl_shader = stage.GetPrimAtPath(material_path.AppendChild("Shader"))
    if mdl_shader:
        stage.RemovePrim(mdl_shader.GetPath())
    shader = UsdShade.Shader.Define(stage, preview_path)
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*PRESENTATION_WATER_PREVIEW_DIFFUSE_COLOR)
    )
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*PRESENTATION_WATER_PREVIEW_EMISSIVE_COLOR)
    )
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(PRESENTATION_WATER_PREVIEW_OPACITY)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(PRESENTATION_WATER_PREVIEW_ROUGHNESS)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(PRESENTATION_WATER_PREVIEW_IOR)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return str(preview_path)


def _author_presentation_water_mdl_shader(stage: Any, source_asset: Path) -> str:
    from pxr import Sdf, UsdShade

    _ensure_looks_scope(stage)
    material_path = Sdf.Path(LIQUID_PRESENTATION_MATERIAL_PATH)
    material = UsdShade.Material.Define(stage, material_path)
    preview = stage.GetPrimAtPath(material_path.AppendChild("PreviewSurface"))
    if preview:
        stage.RemovePrim(preview.GetPath())
    shader_path = material_path.AppendChild("Shader")
    shader = UsdShade.Shader.Define(stage, shader_path)
    shader.GetImplementationSourceAttr().Set(UsdShade.Tokens.sourceAsset)
    shader.SetSourceAsset(Sdf.AssetPath(str(source_asset)), "mdl")
    shader.SetSourceAssetSubIdentifier(PRESENTATION_WATER_MDL_SUB_IDENTIFIER, "mdl")
    shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    material.CreateDisplacementOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    material.CreateVolumeOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    return str(shader_path)


def _try_create_and_bind_mdl_material_from_library(
    *,
    material_path: str = LIQUID_PRESENTATION_MATERIAL_PATH,
    mdl_name: str = PRESENTATION_WATER_MDL_ASSET,
    mtl_name: str = PRESENTATION_WATER_MDL_SUB_IDENTIFIER,
) -> dict[str, Any]:
    """Best-effort Isaac kit bind; returns success=false when kit/command is unavailable."""
    try:
        import omni.kit.commands
        import omni.usd
        from pxr import Sdf
    except Exception as exc:  # pragma: no cover - depends on Isaac runtime
        return {
            "success": False,
            "bind_method": "CreateAndBindMdlMaterialFromLibrary",
            "error": f"kit_unavailable:{exc}",
        }

    created: list[str] = []
    try:
        omni.kit.commands.execute(
            "CreateAndBindMdlMaterialFromLibrary",
            mdl_name=mdl_name,
            mtl_name=mtl_name,
            mtl_created_list=created,
            select_new_prim=False,
        )
    except Exception as exc:  # pragma: no cover - depends on Isaac runtime
        return {
            "success": False,
            "bind_method": "CreateAndBindMdlMaterialFromLibrary",
            "error": f"command_failed:{exc}",
            "mtl_created_list": list(created),
        }
    if not created:
        return {
            "success": False,
            "bind_method": "CreateAndBindMdlMaterialFromLibrary",
            "error": "mtl_created_list_empty",
            "mtl_created_list": [],
        }
    created_path = created[0]
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        return {
            "success": False,
            "bind_method": "CreateAndBindMdlMaterialFromLibrary",
            "error": "stage_unavailable",
            "mtl_created_list": list(created),
        }
    moved = False
    if created_path != material_path:
        try:
            if stage.GetPrimAtPath(material_path):
                stage.RemovePrim(Sdf.Path(material_path))
            omni.kit.commands.execute(
                "MovePrim",
                path_from=created_path,
                path_to=material_path,
            )
            moved = bool(stage.GetPrimAtPath(material_path))
        except Exception as exc:
            return {
                "success": False,
                "bind_method": "CreateAndBindMdlMaterialFromLibrary",
                "error": f"move_prim_failed:{exc}",
                "mtl_created_list": list(created),
                "created_path": created_path,
            }
    return {
        "success": True,
        "bind_method": "CreateAndBindMdlMaterialFromLibrary",
        "mtl_created_list": list(created),
        "material_path": material_path if moved or created_path == material_path else created_path,
        "created_path": created_path,
        "moved_to_canonical_path": moved or created_path == material_path,
    }


def _author_liquid_presentation_water_material(
    stage: Any,
    *,
    attempt_mdl: bool = True,
    mdl_source_asset: str | Path | None = None,
    closure_base_dir: str | Path | None = None,
    prefer_kit_bind: bool = False,
) -> dict[str, Any]:
    """Author presentation liquid material; attempt OmniSurface_ClearWater when possible."""
    if not attempt_mdl:
        shader_path = _author_presentation_water_preview_surface(stage)
        return build_presentation_water_preview_fallback_info(
            mdl_bind_attempted=False,
            shader_path=shader_path,
        )

    kit_bind: dict[str, Any] | None = None
    if prefer_kit_bind:
        kit_bind = _try_create_and_bind_mdl_material_from_library()
        if kit_bind.get("success"):
            resolved = resolve_presentation_water_mdl_source_asset(
                mdl_source_asset,
                closure_base_dir=closure_base_dir,
            )
            return build_presentation_water_mdl_material_info(
                source_asset=resolved
                or (ISAACSIM41_CORE_MDL_ROOT / "Base" / PRESENTATION_WATER_MDL_ASSET),
                bind_method="CreateAndBindMdlMaterialFromLibrary",
            )

    resolved = resolve_presentation_water_mdl_source_asset(
        mdl_source_asset,
        closure_base_dir=closure_base_dir,
    )
    if resolved is None:
        shader_path = _author_presentation_water_preview_surface(stage)
        reason = "mdl_asset_missing"
        if kit_bind and not kit_bind.get("success"):
            reason = f"mdl_asset_missing_after_kit_bind_fail:{kit_bind.get('error')}"
        return build_presentation_water_preview_fallback_info(
            mdl_bind_attempted=True,
            fallback_reason=reason,
            shader_path=shader_path,
        )

    try:
        shader_path = _author_presentation_water_mdl_shader(stage, resolved)
    except Exception as exc:
        shader_path = _author_presentation_water_preview_surface(stage)
        return build_presentation_water_preview_fallback_info(
            mdl_bind_attempted=True,
            fallback_reason=f"mdl_shader_author_failed:{exc}",
            shader_path=shader_path,
        )

    return build_presentation_water_mdl_material_info(
        source_asset=resolved,
        shader_path=shader_path,
        bind_method="usd_mdl_shader",
    )


def _author_liquid_presentation_lighting(stage: Any) -> dict[str, Any]:
    from pxr import Gf, UsdLux

    light = UsdLux.DistantLight.Define(stage, LIQUID_PRESENTATION_LIGHT_PATH)
    light.CreateIntensityAttr(950.0)
    light.AddRotateXYZOp().Set(Gf.Vec3f(55.0, 0.0, 35.0))
    return {
        "light_path": LIQUID_PRESENTATION_LIGHT_PATH,
        "role": "leadership_presentation_key_light",
        "intensity": 950.0,
        "rotate_xyz": [55.0, 0.0, 35.0],
        "lighting_contract_hash": "liquid_presentation_key_light_v1",
    }


def _define_liquid_presentation_camera(stage: Any, config: Any) -> dict[str, Any]:
    from pxr import Gf, UsdGeom

    focus_source_weight = 0.72
    focus_target_weight = 1.0 - focus_source_weight
    focus_x = config.source_center[0] * focus_source_weight + config.target_center[0] * focus_target_weight
    focus_y = config.source_center[1] * focus_source_weight + config.target_center[1] * focus_target_weight
    pair_span = max(
        abs(config.source_center[0] - config.target_center[0]) + config.source_radius + config.target_radius,
        abs(config.source_center[1] - config.target_center[1]) + config.source_radius + config.target_radius,
    )
    source_side_y = 1.0 if config.source_center[1] >= config.target_center[1] else -1.0
    target = (
        focus_x,
        focus_y,
        config.table_z + min(max(config.source_height * 0.34, 0.055), 0.085),
    )
    eye = (
        focus_x + max(0.25, pair_span * 0.48),
        focus_y + source_side_y * max(0.40, pair_span * 0.90),
        config.table_z + 0.34,
    )
    up = (0.0, 0.0, 1.0)
    camera = UsdGeom.Camera.Define(stage, LIQUID_PRESENTATION_CAMERA_PATH)
    transform = Gf.Matrix4d(1).SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(*up)).GetInverse()
    camera.ClearXformOpOrder()
    camera.AddTransformOp().Set(transform)
    camera.CreateFocalLengthAttr(24.0)
    camera.CreateHorizontalApertureAttr(24.0)
    camera.CreateVerticalApertureAttr(16.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
    return {
        "camera_path": LIQUID_PRESENTATION_CAMERA_PATH,
        "role": "leadership_presentation_main",
        "eye": list(eye),
        "target": list(target),
        "up": list(up),
        "source_side_y": source_side_y,
        "pair_span": pair_span,
        "focus_source_weight": focus_source_weight,
        "camera_contract_hash": "liquid_presentation_main_camera_v1",
    }


def _particle_isosurface_api_summary(stage: Any, particle_system_path: str) -> dict[str, Any]:
    prim = stage.GetPrimAtPath(particle_system_path)
    if not prim:
        return {"api_path": particle_system_path, "prim_exists": False, "api_applied": False}
    applied_schemas = list(prim.GetAppliedSchemas())
    return {
        "api_path": particle_system_path,
        "prim_exists": True,
        "api_applied": "PhysxParticleIsosurfaceAPI" in applied_schemas,
        "applied_schemas": applied_schemas,
        "enabled": _read_prim_attr(prim, "physxParticleIsosurface:isosurfaceEnabled"),
        "grid_spacing": _read_prim_attr(prim, "physxParticleIsosurface:gridSpacing"),
        "surface_distance": _read_prim_attr(prim, "physxParticleIsosurface:surfaceDistance"),
        "grid_filtering_passes": _read_prim_attr(prim, "physxParticleIsosurface:gridFilteringPasses"),
        "grid_smoothing_radius": _read_prim_attr(prim, "physxParticleIsosurface:gridSmoothingRadius"),
        "num_mesh_smoothing_passes": _read_prim_attr(prim, "physxParticleIsosurface:numMeshSmoothingPasses"),
        "num_mesh_normal_smoothing_passes": _read_prim_attr(
            prim, "physxParticleIsosurface:numMeshNormalSmoothingPasses"
        ),
        "max_vertices": _read_prim_attr(prim, "physxParticleIsosurface:maxVertices"),
        "max_triangles": _read_prim_attr(prim, "physxParticleIsosurface:maxTriangles"),
        "max_subgrids": _read_prim_attr(prim, "physxParticleIsosurface:maxSubgrids"),
    }


def _read_prim_attr(prim: Any, attr_name: str) -> Any:
    attr = prim.GetAttribute(attr_name)
    return attr.Get() if attr else None


def build_native_scene_video_summary(frame_sources: dict[str, str]) -> dict[str, Any]:
    presentation_count = sum(1 for value in frame_sources.values() if value == "presentation_isosurface_rgb")
    slots = [
        "camera1_native_material",
        "camera2_native_material",
        "beaker2_closeup_native_material",
        "beaker2_closeup_review_markers",
    ]
    if presentation_count:
        slots.insert(0, "presentation_isosurface")
    return {
        "native_scene_video_slots": slots,
        "native_camera_rgb_frame_count": sum(1 for value in frame_sources.values() if value == "native_camera_rgb"),
        "presentation_isosurface_rgb_frame_count": presentation_count,
        "closeup_native_rgb_frame_count": sum(1 for value in frame_sources.values() if value == "closeup_native_rgb"),
        "review_marker_rgb_frame_count": sum(1 for value in frame_sources.values() if value == "review_marker_rgb"),
        "frame_sources": dict(sorted(frame_sources.items())),
    }


def build_native_scene_claim_boundary() -> dict[str, list[str]]:
    return {
        "allowed": [
            "native_usd_scene_step_video_recorded=true",
            "native_scene_material_paths_preserved=true",
            "native_scene_mdl_source_assets_retargeted_to_isaacsim41_local_mirror=true",
            "pbd_completion_overlay_used_for_runtime_step=true",
            "isaacsim41_core_mdl_local_mirror_can_be_used_for_runtime_material_closure=true",
            "50k_colleague_particles_stepped_in_native_scene=true",
            "leak_status_supported_by_particle_readback=true",
            "presentation_isosurface_video_recorded=true",
        ],
        "blocked": [
            "raw_usd_direct_step_passed",
            "raw_50k_colleague_liquid_usd_can_direct_step_as_true_pbd_fluid",
            "completed_pbd_static_leak_equals_benchmark_ready_fluid",
            "presentation_video_equals_physics_success",
            "isosurface_reconstruction_equals_zero_leak",
            "presentation_water_material_equals_labutopia51_visual_parity",
            "review_markers_are_physical_fluid_mesh",
            "review_marker_video_equals_native_material_video",
            "isaacsim41_core_mdl_local_mirror_equals_labutopia51_native_visual_parity",
            "ebench_score_or_policy_claim_allowed",
            "s3_kinematic_pour_released",
        ],
    }


def _define_closeup_camera(stage: Any, config: Any) -> dict[str, Any]:
    from pxr import Gf, UsdGeom

    target = (
        config.source_center[0],
        config.source_center[1],
        config.table_z + min(max(config.source_height * 0.58, 0.08), 0.12),
    )
    eye = (
        config.source_center[0] + 0.20,
        config.source_center[1] - 0.34,
        config.table_z + 0.25,
    )
    up = (0.0, 0.0, 1.0)
    camera = UsdGeom.Camera.Define(stage, CLOSEUP_CAMERA_PATH)
    transform = Gf.Matrix4d(1).SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(*up)).GetInverse()
    camera.ClearXformOpOrder()
    camera.AddTransformOp().Set(transform)
    camera.CreateFocalLengthAttr(20.0)
    camera.CreateHorizontalApertureAttr(22.0)
    camera.CreateVerticalApertureAttr(16.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))
    return {
        "camera_path": CLOSEUP_CAMERA_PATH,
        "eye": list(eye),
        "target": list(target),
        "up": list(up),
    }


def _make_camera_sensor(prim_path: str, *, name: str, width: int, height: int) -> Any | None:
    try:
        from omni.isaac.sensor import Camera

        camera = Camera(prim_path=prim_path, name=name, resolution=(width, height))
        camera.initialize()
        return camera
    except Exception:
        return None


def _make_positioned_camera_sensor(
    prim_path: str,
    *,
    name: str,
    width: int,
    height: int,
    eye: Sequence[float],
    target: Sequence[float],
    up: Sequence[float],
) -> Any | None:
    try:
        import numpy as np
        from omni.isaac.sensor import Camera
        from tools.labutopia_fluid.run_colleague_liquid_usd_leak_smoke import world_camera_quat_look_at

        camera = Camera(prim_path=prim_path, name=name, resolution=(width, height))
        camera.initialize()
        orientation = world_camera_quat_look_at(eye=eye, target=target, up=up)
        camera.set_world_pose(
            position=np.array(eye, dtype=float),
            orientation=np.array(orientation, dtype=float),
            camera_axes="world",
        )
        return camera
    except Exception:
        return None


def _set_review_markers_visible(stage: Any, visible: bool) -> None:
    prim = stage.GetPrimAtPath(REVIEW_MARKER_ROOT)
    if prim:
        prim.SetActive(bool(visible))


def _deactivate_original_fluid_prims(stage: Any) -> dict[str, Any]:
    from pxr import Sdf, UsdGeom

    stage.SetEditTarget(stage.GetRootLayer())
    results = {}
    for path in ("/World/fluid", EVIDENCE_PARTICLE_SET_PATH, EVIDENCE_PARTICLE_SYSTEM_PATH):
        prim = stage.GetPrimAtPath(path)
        results[path] = {
            "existed": bool(prim),
            "deactivated": False,
            "kept_active_to_avoid_physx_expired_prim": bool(prim),
            "disabled_attrs": {},
        }
        if prim:
            imageable = UsdGeom.Imageable(prim)
            imageable.MakeInvisible()
            if path == EVIDENCE_PARTICLE_SYSTEM_PATH:
                attr = prim.GetAttribute("particleSystemEnabled")
                if not attr:
                    attr = prim.CreateAttribute("particleSystemEnabled", Sdf.ValueTypeNames.Bool)
                attr.Set(False)
                results[path]["disabled_attrs"]["particleSystemEnabled"] = False
            if path == EVIDENCE_PARTICLE_SET_PATH:
                for attr_name in ("physxParticle:selfCollision", "physxParticle:fluid"):
                    attr = prim.GetAttribute(attr_name)
                    if not attr:
                        attr = prim.CreateAttribute(attr_name, Sdf.ValueTypeNames.Bool)
                    attr.Set(False)
                    results[path]["disabled_attrs"][attr_name] = False
    return results


def _configure_physics_scene_for_pbd(stage: Any, physics_scene_path: str) -> dict[str, Any]:
    from pxr import Gf, PhysxSchema, UsdPhysics

    physics_scene = UsdPhysics.Scene.Get(stage, physics_scene_path)
    if not physics_scene:
        physics_scene = UsdPhysics.Scene.Define(stage, physics_scene_path)
    physics_scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
    physics_scene.CreateGravityMagnitudeAttr().Set(9.81)
    physx_scene_api = PhysxSchema.PhysxSceneAPI.Apply(physics_scene.GetPrim())
    physx_scene_api.CreateEnableGPUDynamicsAttr().Set(True)
    physx_scene_api.CreateBroadphaseTypeAttr().Set("GPU")
    physx_scene_api.CreateSolverTypeAttr().Set("TGS")
    physx_scene_api.CreateGpuMaxParticleContactsAttr().Set(1_048_576)
    return {
        "physics_scene_path": physics_scene_path,
        "gpu_dynamics_enabled": True,
        "broadphase_type": "GPU",
        "solver_type": "TGS",
        "gravity_direction": [0.0, 0.0, -1.0],
        "gravity_magnitude": 9.81,
        "gpu_max_particle_contacts": 1_048_576,
    }


def _author_completed_pbd_runtime_particles(
    *,
    stage: Any,
    positions: Sequence[Sequence[float]],
    widths: dict[str, float],
    physics_scene_path: str,
    visual_material_path: str,
    presentation_isosurface_video: bool = False,
    presentation_visual_material_path: str | None = None,
) -> dict[str, Any]:
    from omni.physx.scripts import particleUtils, physicsUtils
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    stage.SetEditTarget(stage.GetRootLayer())
    pre_deactivate_summary = _deactivate_original_fluid_prims(stage)
    if not stage.GetPrimAtPath(RUNTIME_PBD_SCOPE_PATH):
        UsdGeom.Xform.Define(stage, RUNTIME_PBD_SCOPE_PATH)

    looks_path = Sdf.Path("/World/Looks")
    if not stage.GetPrimAtPath(looks_path):
        UsdGeom.Scope.Define(stage, looks_path)
    physics_material_path = looks_path.AppendChild("PBDRuntimeFluidPhysics")
    particleUtils.add_pbd_particle_material(
        stage=stage,
        path=physics_material_path,
        cohesion=0.01,
        damping=0.0,
        friction=0.1,
        surface_tension=0.0074,
        viscosity=0.0000017,
        density=1000.0,
    )

    particle_system = particleUtils.add_physx_particle_system(
        stage=stage,
        particle_system_path=Sdf.Path(RUNTIME_PARTICLE_SYSTEM_PATH),
        particle_system_enabled=True,
        simulation_owner=Sdf.Path(physics_scene_path),
        contact_offset=widths["particle_system_contact_offset"],
        rest_offset=0.0,
        particle_contact_offset=widths["particle_contact_offset"],
        solid_rest_offset=widths["solid_rest_offset"],
        fluid_rest_offset=widths["fluid_rest_offset"],
        solver_position_iterations=4,
        max_velocity=5.0,
        max_neighborhood=96,
        global_self_collision_enabled=True,
        non_particle_collision_enabled=True,
    )
    isosurface_contract = {"enabled": False, "api_path": RUNTIME_PARTICLE_SYSTEM_PATH}
    if presentation_isosurface_video:
        isosurface_contract = build_liquid_presentation_isosurface_contract(
            fluid_rest_offset=widths["fluid_rest_offset"],
            particle_count=len(positions),
        )
        particleUtils.add_physx_particle_isosurface(
            stage,
            Sdf.Path(RUNTIME_PARTICLE_SYSTEM_PATH),
            enabled=True,
            max_vertices=isosurface_contract["max_vertices"],
            max_triangles=isosurface_contract["max_triangles"],
            max_subgrids=isosurface_contract["max_subgrids"],
            grid_spacing=isosurface_contract["grid_spacing"],
            surface_distance=isosurface_contract["surface_distance"],
            grid_filtering_passes=isosurface_contract["grid_filtering_passes"],
            grid_smoothing_radius=isosurface_contract["grid_smoothing_radius"],
            num_mesh_smoothing_passes=isosurface_contract["num_mesh_smoothing_passes"],
            num_mesh_normal_smoothing_passes=isosurface_contract["num_mesh_normal_smoothing_passes"],
        )
    else:
        particleUtils.add_physx_particle_isosurface(stage, Sdf.Path(RUNTIME_PARTICLE_SYSTEM_PATH), enabled=False)
    physicsUtils.add_physics_material_to_prim(stage, particle_system.GetPrim(), physics_material_path)

    render_material_path = presentation_visual_material_path or visual_material_path
    visual_material = UsdShade.Material(stage.GetPrimAtPath(render_material_path))
    if visual_material:
        UsdShade.MaterialBindingAPI.Apply(particle_system.GetPrim()).Bind(visual_material)

    velocities = [Gf.Vec3f(0.0, 0.0, 0.0)] * len(positions)
    particle_widths = [widths["particle_width"]] * len(positions)
    points = [Gf.Vec3f(float(p[0]), float(p[1]), float(p[2])) for p in positions]
    particle_set = particleUtils.add_physx_particleset_points(
        stage,
        Sdf.Path(RUNTIME_PARTICLE_SET_PATH),
        points,
        velocities,
        particle_widths,
        Sdf.Path(RUNTIME_PARTICLE_SYSTEM_PATH),
        True,
        True,
        0,
        0.001,
        1000.0,
    )
    physicsUtils.add_physics_material_to_prim(stage, particle_set.GetPrim(), physics_material_path)
    if visual_material:
        UsdShade.MaterialBindingAPI.Apply(particle_set.GetPrim()).Bind(visual_material)
    return {
        "particle_system_path": RUNTIME_PARTICLE_SYSTEM_PATH,
        "particle_set_path": RUNTIME_PARTICLE_SET_PATH,
        "source_particle_system_path": EVIDENCE_PARTICLE_SYSTEM_PATH,
        "source_particle_set_path": EVIDENCE_PARTICLE_SET_PATH,
        "physics_material_path": str(physics_material_path),
        "visual_material_path": render_material_path,
        "source_visual_material_path": visual_material_path,
        "presentation_visual_material_path": presentation_visual_material_path,
        "visual_material_preserved": bool(visual_material),
        "isosurface_contract": isosurface_contract,
        "particle_isosurface_api_summary": _particle_isosurface_api_summary(stage, RUNTIME_PARTICLE_SYSTEM_PATH),
        "pre_deactivate_summary": pre_deactivate_summary,
    }


def _physx_visualizer_mode_none(pb: Any) -> Any:
    return getattr(pb.VisualizerMode, "NONE", 0)


def _native_stage_runtime(args: argparse.Namespace) -> dict[str, Any]:
    import carb
    import omni.kit.app
    import omni.timeline
    import omni.usd
    import omni.physx.bindings._physx as pb
    from pxr import Gf, Usd, UsdLux

    usd_path = _repo_path(args.usd).resolve()
    artifact_dir = Path(args.out_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    trace_path = artifact_dir / "particle_readback_trace.jsonl"
    trace_path.write_text("", encoding="utf-8")

    material_summary = inspect_native_material_bindings(usd_path)
    expectation = NativeMaterialExpectation()
    static_stage = Usd.Stage.Open(str(usd_path), Usd.Stage.LoadAll)
    if static_stage is None:
        raise RuntimeError(f"usd_stage_static_open_failed:{usd_path}")
    source_bbox: BBox = _bbox_from_stage(static_stage, "/World/beaker2")
    target_bbox: BBox = _bbox_from_stage(static_stage, "/World/beaker1")
    table_bbox: BBox = _bbox_from_stage(static_stage, "/World/table")
    config = build_tabletop_region_config(
        source_bbox=source_bbox,
        target_bbox=target_bbox,
        table_top_z=float(table_bbox.max[2]),
    )
    original_positions = _read_points(static_stage, EVIDENCE_PARTICLE_SET_PATH)
    selected_positions = select_particle_subset(original_positions, limit=args.particle_limit)
    authored_width = _read_width(static_stage, EVIDENCE_PARTICLE_SET_PATH)
    offsets = resolve_particle_runtime_offsets(
        authored_width=authored_width,
        particle_width_override=args.particle_width_override,
        particle_contact_offset_override=args.particle_contact_offset_override,
    )
    config = config.__class__(
        **{
            **asdict(config),
            "particle_count": len(selected_positions),
            "particle_width": offsets["particle_width"],
            "particle_contact_offset": offsets["particle_contact_offset"],
            "spawn_particle_contact_offset": offsets["particle_contact_offset"],
            "particle_system_contact_offset": offsets["particle_system_contact_offset"],
            "solid_rest_offset": offsets["solid_rest_offset"],
            "fluid_rest_offset": offsets["fluid_rest_offset"],
            "steps": args.steps,
            "trace_interval": args.trace_interval,
            "tail_window_steps": min(args.steps, max(1, args.trace_interval * 3)),
            "render_width": args.width,
            "render_height": args.height,
            "physics_dt": args.physics_dt,
        }
    )

    settings = carb.settings.get_settings()
    settings.set(pb.SETTING_UPDATE_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)
    if args.presentation_isosurface_video or args.disable_particle_debug_display:
        settings.set(pb.SETTING_DISPLAY_PARTICLES, _physx_visualizer_mode_none(pb))
    else:
        settings.set(pb.SETTING_DISPLAY_PARTICLES, pb.VisualizerMode.ALL)
    settings.set_bool(pb.SETTING_SUPPRESS_READBACK, False)
    settings.set_bool("/physics/suppressReadback", False)

    context = omni.usd.get_context()
    opened = bool(context.open_stage(str(usd_path)))
    stage = context.get_stage()
    open_updates = 0
    while stage is None and open_updates < max(1, args.warmup_updates):
        omni.kit.app.get_app().update()
        open_updates += 1
        stage = context.get_stage()
    if not opened or stage is None:
        raise RuntimeError(f"open_stage_failed:{usd_path}")
    if args.material_closure_mode == "isaacsim41-core-local-mirror":
        material_closure_summary = _mirror_isaacsim41_core_mdl_closure(artifact_dir)
        material_retarget_summary = _retarget_stage_mdl_source_assets(stage, material_closure_summary)
    else:
        material_closure_summary = {
            "material_closure_mode": "preserve_native_source_assets",
            "visual_material_parity_claim_allowed": False,
        }
        material_retarget_summary = {"retarget_enabled": False, "retargeted_shader_count": 0, "retargeted_shaders": []}
    native_collider_approximation_summary = {"enabled": False}
    native_collider_variant_id = getattr(args, "native_collider_approximation_variant", None)
    if native_collider_variant_id:
        from tools.labutopia_fluid.run_colleague_native_collider_approx_sweep import (
            apply_native_collider_approximation,
            build_native_approximation_sweep,
        )

        candidates = {candidate.variant_id: candidate for candidate in build_native_approximation_sweep()}
        if native_collider_variant_id not in candidates:
            raise ValueError(f"unknown_native_collider_approximation_variant:{native_collider_variant_id}")
        candidate = candidates[native_collider_variant_id]
        native_collider_approximation_summary = {
            "enabled": True,
            "candidate": asdict(candidate),
            "authoring": apply_native_collider_approximation(stage, candidate),
        }
    original_fluid_deactivate_summary = _deactivate_original_fluid_prims(stage)
    for _ in range(args.warmup_updates):
        omni.kit.app.get_app().update()
    settings.set_bool(pb.SETTING_SUPPRESS_READBACK, False)
    settings.set_bool("/physics/suppressReadback", False)
    settings.set(pb.SETTING_UPDATE_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)

    physics_settings = _configure_physics_scene_for_pbd(stage, "/World/PhysicsScene")

    if not stage.GetPrimAtPath("/World/DistantLight"):
        light = UsdLux.DistantLight.Define(stage, "/World/DistantLight")
        light.CreateIntensityAttr(700.0)
        light.AddRotateXYZOp().Set(Gf.Vec3f(55.0, 0.0, 35.0))

    closeup_camera_info = _define_closeup_camera(stage, config)
    presentation_material_info: dict[str, Any] = {}
    presentation_lighting_info: dict[str, Any] = {}
    presentation_camera_info: dict[str, Any] = {}
    presentation_visual_contract: dict[str, Any] = {}
    presentation_visual_material_path = None
    if args.presentation_isosurface_video:
        presentation_material_info = _author_liquid_presentation_water_material(
            stage,
            attempt_mdl=True,
            closure_base_dir=material_closure_summary.get("closure_base_dir"),
            prefer_kit_bind=False,
        )
        presentation_lighting_info = _author_liquid_presentation_lighting(stage)
        presentation_camera_info = _define_liquid_presentation_camera(stage, config)
        presentation_visual_material_path = LIQUID_PRESENTATION_MATERIAL_PATH
    authored = _author_completed_pbd_runtime_particles(
        stage=stage,
        positions=selected_positions,
        widths=offsets,
        physics_scene_path="/World/PhysicsScene",
        visual_material_path="/World/Looks/OmniGlass_01",
        presentation_isosurface_video=bool(args.presentation_isosurface_video),
        presentation_visual_material_path=presentation_visual_material_path,
    )
    if args.presentation_isosurface_video:
        presentation_visual_contract = build_presentation_visual_contract(
            variant_id=native_collider_variant_id or NATIVE_SCENE_COMPLETED_PBD_VARIANT_ID,
            camera_info=presentation_camera_info,
            lighting_info=presentation_lighting_info,
            isosurface_contract=authored.get("isosurface_contract") or {},
            material_path=LIQUID_PRESENTATION_MATERIAL_PATH,
            particle_count=len(selected_positions),
        )
    evidence_scene_path = artifact_dir / "native_scene_completed_pbd_overlay.usda"
    stage.GetRootLayer().Export(str(evidence_scene_path))

    timeline = omni.timeline.get_timeline_interface()
    timeline.play()
    for _ in range(args.camera_warmup_updates):
        omni.kit.app.get_app().update()
    settings.set_bool(pb.SETTING_SUPPRESS_READBACK, False)
    settings.set_bool("/physics/suppressReadback", False)
    settings.set(pb.SETTING_UPDATE_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_PARTICLES_TO_USD, True)
    settings.set(pb.SETTING_UPDATE_VELOCITIES_TO_USD, True)

    cameras: dict[str, Any | None] = {}
    if args.capture_native_cameras:
        for slot, prim_path in NATIVE_CAMERA_PATHS.items():
            cameras[slot] = _make_camera_sensor(
                prim_path,
                name=slot,
                width=args.width,
                height=args.height,
            )
    if args.capture_closeup_camera or args.capture_review_markers:
        cameras["beaker2_closeup_native_material"] = _make_positioned_camera_sensor(
            CLOSEUP_CAMERA_PATH,
            name="beaker2_closeup_native_material_camera",
            width=args.width,
            height=args.height,
            eye=closeup_camera_info["eye"],
            target=closeup_camera_info["target"],
            up=closeup_camera_info["up"],
        )
    if args.presentation_isosurface_video:
        cameras["presentation_isosurface"] = _make_positioned_camera_sensor(
            LIQUID_PRESENTATION_CAMERA_PATH,
            name="liquid_presentation_main_camera",
            width=args.width,
            height=args.height,
            eye=presentation_camera_info["eye"],
            target=presentation_camera_info["target"],
            up=presentation_camera_info["up"],
        )

    frame_dirs = {
        "camera1_native_material": artifact_dir / "camera1_native_material_frames",
        "camera2_native_material": artifact_dir / "camera2_native_material_frames",
        "beaker2_closeup_native_material": artifact_dir / "beaker2_closeup_native_material_frames",
        "beaker2_closeup_review_markers": artifact_dir / "beaker2_closeup_review_marker_frames",
    }
    if args.presentation_isosurface_video:
        frame_dirs["presentation_isosurface"] = artifact_dir / "presentation_isosurface_frames"
    frame_paths: dict[str, list[Path]] = {slot: [] for slot in frame_dirs}
    frame_sources: dict[str, str] = {}
    camera_diagnostics: dict[str, dict[str, Any]] = {}
    marker_updates: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    start = time.monotonic()

    for step_index in range(args.steps + 1):
        positions = _read_points(stage, RUNTIME_PARTICLE_SET_PATH)
        if step_index % args.trace_interval == 0 or step_index in (0, args.steps):
            record = {
                "step_index": step_index,
                "particle_count": len(positions),
                "aabb": _aabb(positions),
                "centroid": _centroid(positions),
                "region_counts": compute_region_counts(positions, config),
                "nan_count": _nan_count(positions),
                "positions": _jsonable_positions(positions),
            }
            records.append(record)
            _write_trace_line(trace_path, record)
        if step_index % args.video_stride == 0 or step_index in (0, args.steps):
            _set_review_markers_visible(stage, False)
            omni.kit.app.get_app().update()
            native_slots = []
            if args.capture_native_cameras:
                native_slots.extend(["camera1_native_material", "camera2_native_material"])
            if args.capture_closeup_camera:
                native_slots.append("beaker2_closeup_native_material")
            if args.presentation_isosurface_video:
                native_slots.insert(0, "presentation_isosurface")
            for slot in native_slots:
                camera = cameras.get(slot)
                frame_path = frame_dirs[slot] / f"frame_{step_index:04d}.png"
                source, diagnostics = _try_write_camera_png_with_diagnostics(camera, frame_path)
                camera_diagnostics[str(frame_path.relative_to(artifact_dir))] = diagnostics
                if source is not None:
                    frame_paths[slot].append(frame_path)
                    if slot == "presentation_isosurface":
                        frame_source = "presentation_isosurface_rgb"
                    elif slot == "beaker2_closeup_native_material":
                        frame_source = "closeup_native_rgb"
                    else:
                        frame_source = "native_camera_rgb"
                    frame_sources[str(frame_path.relative_to(artifact_dir))] = frame_source
            if args.capture_review_markers:
                _set_review_markers_visible(stage, True)
                marker_update = _update_review_markers(
                    stage=stage,
                    positions=positions,
                    marker_limit=args.review_marker_limit,
                    marker_width=args.review_marker_width,
                )
                marker_updates[f"step_{step_index:04d}"] = marker_update
                omni.kit.app.get_app().update()
                slot = "beaker2_closeup_review_markers"
                frame_path = frame_dirs[slot] / f"frame_{step_index:04d}.png"
                source, diagnostics = _try_write_camera_png_with_diagnostics(
                    cameras.get("beaker2_closeup_native_material"),
                    frame_path,
                )
                camera_diagnostics[str(frame_path.relative_to(artifact_dir))] = diagnostics
                if source is not None:
                    frame_paths[slot].append(frame_path)
                    frame_sources[str(frame_path.relative_to(artifact_dir))] = "review_marker_rgb"
        if step_index < args.steps:
            if args.runtime_timeout_seconds > 0 and (time.monotonic() - start) > args.runtime_timeout_seconds:
                raise TimeoutError(
                    f"native_usd_completed_pbd_step_timeout:{time.monotonic() - start:.1f}s"
                )
            omni.kit.app.get_app().update()

    classification = classify_colleague_trace(records, config)
    classification["variant_id"] = NATIVE_SCENE_COMPLETED_PBD_VARIANT_ID
    initial_positions = records[0].get("positions", []) if records else []
    final_positions = records[-1].get("positions", []) if records else []
    videos: dict[str, dict[str, Any]] = {}
    for slot, paths in frame_paths.items():
        video_path = artifact_dir / f"{slot}.mp4"
        written = _write_mp4_from_frames(paths, video_path, fps=args.video_fps)
        videos[slot] = {
            "path": str(video_path) if written else None,
            "written": written,
            "frame_count": len(paths),
        }
    material_post_summary = {
        "beaker2": _material_summary(stage, "/World/beaker2/mesh"),
        "beaker1": _material_summary(stage, "/World/beaker1/mesh"),
        "source_particle_system": _material_summary(stage, EVIDENCE_PARTICLE_SYSTEM_PATH),
        "runtime_particle_system": _material_summary(stage, RUNTIME_PARTICLE_SYSTEM_PATH),
    }
    particle_scope = build_particle_scope_summary(
        original_particle_count=len(original_positions),
        selected_particle_count=len(selected_positions),
        particle_limit=args.particle_limit,
    )
    summary = {
        "schema_version": 1,
        "manifest_type": "fluid_spike_colleague_native_usd_completed_pbd_step_video",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": "isaacsim41",
        "mode": "native_usd_scene_completed_pbd_step_video",
        "source_usd_path": str(usd_path),
        "artifact_dir": str(artifact_dir),
        "native_scene_opened": True,
        "minimal_native_slice_used": expectation.minimal_native_slice_used,
        "native_beaker_material_override_used": expectation.native_beaker_material_override_used,
        "local_blue_glass_override_used": expectation.local_blue_glass_override_used,
        "visual_material_parity_claim_allowed": expectation.visual_material_parity_claim_allowed,
        "runtime_pbd_completion_overlay_used": True,
        "raw_usd_direct_step_claim_allowed": False,
        "steps": args.steps,
        "physics_dt": args.physics_dt,
        "particle_scope": particle_scope,
        "source_particle_count": len(original_positions),
        "selected_particle_count": len(selected_positions),
        "runtime_particle_offsets": offsets,
        "runtime_step_executed": True,
        "readback_diagnostics": {
            "readback_available": bool(initial_positions) and bool(final_positions),
            "readback_position_changed": (
                bool(initial_positions)
                and bool(final_positions)
                and _position_hash(initial_positions) != _position_hash(final_positions)
            ),
            "initial_position_hash": _position_hash(initial_positions) if initial_positions else None,
            "final_position_hash": _position_hash(final_positions) if final_positions else None,
            "max_displacement": max(
                (
                    math.sqrt(sum((float(after[i]) - float(before[i])) ** 2 for i in range(3)))
                    for before, after in zip(initial_positions, final_positions)
                    if all(math.isfinite(float(v)) for v in list(before) + list(after))
                ),
                default=0.0,
            ),
        },
        "material_contract_pre": material_summary,
        "material_contract_post": material_post_summary,
        "material_resolve_status": material_summary.get("material_resolve_status"),
        "material_closure": material_closure_summary,
        "material_retarget": material_retarget_summary,
        "native_collider_approximation": native_collider_approximation_summary,
        "authored_runtime_paths": authored,
        "presentation_material": presentation_material_info,
        "presentation_lighting": presentation_lighting_info,
        "presentation_visual_contract": presentation_visual_contract,
        "presentation_video_enabled": bool(args.presentation_isosurface_video),
        "presentation_isosurface_enabled": bool(args.presentation_isosurface_video),
        "debug_particle_display_enabled": not bool(
            args.disable_particle_debug_display or args.presentation_isosurface_video
        ),
        "region_config": asdict(config),
        "source_bbox": asdict(source_bbox),
        "target_bbox": asdict(target_bbox),
        "table_bbox": asdict(table_bbox),
        "classification": classification,
        "trace_path": str(trace_path),
        "evidence_scene_path": str(evidence_scene_path),
        "videos": videos,
        "video_summary": build_native_scene_video_summary(frame_sources),
        "camera_capture_diagnostics": camera_diagnostics,
        "closeup_camera": closeup_camera_info,
        "review_markers": {
            "enabled": bool(args.capture_review_markers),
            "review_markers_are_physics": False,
            "review_marker_source": "particle_readback_positions",
            "updates": marker_updates,
        },
        "elapsed_seconds": time.monotonic() - start,
        "claim_boundary": build_native_scene_claim_boundary(),
        "original_fluid_deactivate_summary": original_fluid_deactivate_summary,
        "physics_settings": physics_settings,
        "isaac_log_summary": _latest_isaac_log_summary(),
    }
    _write_json(artifact_dir / "runtime_smoke_summary.json", summary)
    _write_json(Path(args.manifest), summary)
    timeline.stop()
    return summary


def _run_runtime(args: argparse.Namespace) -> dict[str, Any]:
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": bool(args.headless), "width": args.width, "height": args.height})
    try:
        return _native_stage_runtime(args)
    except Exception as exc:  # pragma: no cover - runtime-only path.
        fatal_error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc(limit=30)}
        summary = {
            "schema_version": 1,
            "manifest_type": "fluid_spike_colleague_native_usd_completed_pbd_step_video",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "runtime": "isaacsim41",
            "mode": "native_usd_scene_completed_pbd_step_video",
            "runtime_step_executed": False,
            "material_closure_mode": args.material_closure_mode,
            "fatal_error": fatal_error,
            "classification": {"classification": "STOP_RUNTIME_ERROR", "fatal_error": fatal_error},
            "claim_boundary": build_native_scene_claim_boundary(),
            "isaac_log_summary": _latest_isaac_log_summary(),
        }
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_json(out_dir / "runtime_smoke_summary.json", summary)
        _write_json(Path(args.manifest), summary)
        return summary
    finally:
        if not args.skip_app_close:
            app.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", default=DEFAULT_USD)
    parser.add_argument("--out-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--particle-limit", type=int, default=0)
    parser.add_argument("--particle-width-override", type=float, default=None)
    parser.add_argument("--particle-contact-offset-override", type=float, default=None)
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--physics-dt", type=float, default=1.0 / 60.0)
    parser.add_argument("--trace-interval", type=int, default=10)
    parser.add_argument("--video-stride", type=int, default=4)
    parser.add_argument("--video-fps", type=float, default=15.0)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--capture-native-cameras", action="store_true")
    parser.add_argument("--capture-closeup-camera", action="store_true")
    parser.add_argument("--capture-review-markers", action="store_true")
    parser.add_argument("--review-marker-limit", type=int, default=512)
    parser.add_argument("--review-marker-width", type=float, default=0.02)
    parser.add_argument("--warmup-updates", type=int, default=5)
    parser.add_argument("--camera-warmup-updates", type=int, default=8)
    parser.add_argument("--runtime-timeout-seconds", type=float, default=300.0)
    parser.add_argument(
        "--material-closure-mode",
        choices=("isaacsim41-core-local-mirror", "preserve-native-source-assets"),
        default="isaacsim41-core-local-mirror",
    )
    parser.add_argument("--skip-app-close", action="store_true")
    parser.add_argument("--hard-exit-after-run", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--native-collider-approximation-variant", default=None)
    parser.add_argument(
        "--presentation-isosurface-video",
        action="store_true",
        help=(
            "Enable PhysX Isosurface visual reconstruction, fixed presentation camera, "
            "presentation water material, and MP4 capture."
        ),
    )
    parser.add_argument("--disable-particle-debug-display", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = _run_runtime(args)
    print(json.dumps(_json_safe(summary), indent=2, sort_keys=True))
    exit_code = 0 if summary.get("runtime_step_executed") else 1
    if args.hard_exit_after_run:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
