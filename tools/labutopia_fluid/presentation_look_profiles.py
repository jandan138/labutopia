"""Weekly OmniGlass presentation look profiles (visual-only; not official Visual A)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

PRESENTATION_LOOK_NONE = "none"
PRESENTATION_LOOK_WEEKLY_B = "weekly_omniglass_B"
PRESENTATION_LOOK_WEEKLY_C = "weekly_omniglass_C"

WEEKLY_OMNIGLASS_WATER_MATERIAL_PATH = "/World/Looks/LiquidPresentationOmniGlassWater"
WEEKLY_OMNIGLASS_BEAKER_MATERIAL_PATH = "/World/Looks/LiquidPresentationBeakerGlass"
WEEKLY_OMNIGLASS_WATER_HASH = "omniglass_water_tint_a18_v1"
# Keep aniso=2.0: aniso=1.0 smoke (002) caused FAIL_CONTAINER_LEAK on 1024 hold.
WEEKLY_OMNIGLASS_POSTPROCESS_HASH = "anisotropy_2_1_2_smoothing_0_65_v1"
# v3: keep official v1 eye height / focus weights (v2 eye_z=0.22 cropped to table void).
WEEKLY_OMNIGLASS_MAIN_CAMERA_HASH = "weekly_omniglass_main_camera_v3"
WEEKLY_OMNIGLASS_LIGHTING_B_HASH = "weekly_omniglass_intensity_v3"
WEEKLY_OMNIGLASS_LIGHTING_C_HASH = "weekly_omniglass_exposure_ct_v1"

# A18/C29 reference fluid tint
REF_OMNIGLASS_GLASS_COLOR = (0.73344165, 0.9498069, 0.94228774)
REF_OMNIGLASS_REFLECTION_COLOR = (0.6368421, 0.9266409, 0.88300306)

_NONE_PROFILE: dict[str, Any] = {
    "look_id": PRESENTATION_LOOK_NONE,
    "water_backend": "MDL_WATER",
    "water_mdl": "OmniSurfacePresets.mdl",
    "water_sub_identifier": "OmniSurface_ClearWater",
    "water_material_path": "/World/Looks/LiquidPresentationWater",
    "beaker_override": {"enabled": False},
    "lighting": {
        "mode": "intensity_v2",
        "key_intensity": 950.0,
        "dome_intensity": 400.0,
        "key_rotate_xyz": (55.0, 0.0, 35.0),
        "lighting_contract_hash": "liquid_presentation_dome_key_v2",
    },
    "camera": {
        "main_hash": "liquid_presentation_main_camera_v1",
        "eye_z_above_table": 0.34,
        "focus_source_weight": 0.72,
        "capture_closeup": False,
    },
    "postprocess": {
        "anisotropy_scale": 5.0,
        "anisotropy_min": 1.0,
        "anisotropy_max": 2.0,
        "smoothing_strength": 0.5,
        "postprocess_hash": "anisotropy_5_1_2_smoothing_0_5_v1",
    },
    "material_hash": "omnisurface_clearwater_mdl_v1",
    "official_visual_a_compatible": True,
}

_WEEKLY_B_PROFILE: dict[str, Any] = {
    "look_id": PRESENTATION_LOOK_WEEKLY_B,
    "water_backend": "MDL_OMNIGLASS_WATER",
    "water_mdl": "OmniGlass.mdl",
    "water_sub_identifier": "OmniGlass",
    "water_material_path": WEEKLY_OMNIGLASS_WATER_MATERIAL_PATH,
    "glass_color": REF_OMNIGLASS_GLASS_COLOR,
    "reflection_color": REF_OMNIGLASS_REFLECTION_COLOR,
    "beaker_override": {
        "enabled": True,
        "target_mesh": "/World/beaker2/mesh",
        "material_path": WEEKLY_OMNIGLASS_BEAKER_MATERIAL_PATH,
        "mdl": "OmniGlass.mdl",
        "sub_identifier": "OmniGlass",
        "glass_color": (0.85, 0.92, 0.95),
        "reflection_color": (0.90, 0.95, 0.98),
        "cutout_opacity": 0.72,
        "enable_opacity": True,
    },
    "lighting": {
        "mode": "intensity_v3",
        "key_intensity": 1200.0,
        "dome_intensity": 220.0,
        "key_rotate_xyz": (55.0, 0.0, 35.0),
        "lighting_contract_hash": WEEKLY_OMNIGLASS_LIGHTING_B_HASH,
    },
    "camera": {
        "main_hash": WEEKLY_OMNIGLASS_MAIN_CAMERA_HASH,
        # Match ClearWater leadership framing; readability comes from lighting/beaker override.
        "eye_z_above_table": 0.34,
        "focus_source_weight": 0.72,
        "capture_closeup": False,
    },
    "postprocess": {
        "anisotropy_scale": 2.0,
        "anisotropy_min": 1.0,
        "anisotropy_max": 2.0,
        "smoothing_strength": 0.65,
        "postprocess_hash": WEEKLY_OMNIGLASS_POSTPROCESS_HASH,
    },
    "material_hash": WEEKLY_OMNIGLASS_WATER_HASH,
    "official_visual_a_compatible": False,
}

_WEEKLY_C_OVERRIDES: dict[str, Any] = {
    "look_id": PRESENTATION_LOOK_WEEKLY_C,
    "lighting": {
        "mode": "exposure_ct_ref_v1",
        "key_intensity": 1.0,
        "key_exposure": 10.0,
        "key_color_temperature": 7250.0,
        "dome_intensity": 1.0,
        "dome_exposure": 9.0,
        "dome_color_temperature": 6150.0,
        "key_rotate_xyz": (55.0, 0.0, 135.0),
        "lighting_contract_hash": WEEKLY_OMNIGLASS_LIGHTING_C_HASH,
    },
    "camera": {
        "main_hash": WEEKLY_OMNIGLASS_MAIN_CAMERA_HASH,
        "eye_z_above_table": 0.34,
        "focus_source_weight": 0.72,
        "capture_closeup": True,
    },
    "official_visual_a_compatible": False,
}

_PRESETS: dict[str, dict[str, Any]] = {
    PRESENTATION_LOOK_NONE: _NONE_PROFILE,
    PRESENTATION_LOOK_WEEKLY_B: _WEEKLY_B_PROFILE,
    PRESENTATION_LOOK_WEEKLY_C: {
        **deepcopy(_WEEKLY_B_PROFILE),
        **{
            "look_id": PRESENTATION_LOOK_WEEKLY_C,
            "lighting": deepcopy(_WEEKLY_C_OVERRIDES["lighting"]),
            "camera": deepcopy(_WEEKLY_C_OVERRIDES["camera"]),
            "official_visual_a_compatible": False,
        },
    },
}


def is_weekly_omniglass_look(look_id: str | None) -> bool:
    return look_id in (PRESENTATION_LOOK_WEEKLY_B, PRESENTATION_LOOK_WEEKLY_C)


def resolve_presentation_look_profile(name: str | None) -> dict[str, Any]:
    """Return a deep-copied look profile. None / '' / 'none' → official ClearWater-compatible."""
    key = PRESENTATION_LOOK_NONE if name is None or str(name).strip() == "" else str(name).strip()
    if key not in _PRESETS:
        raise ValueError(f"unknown presentation look preset: {name!r}")
    return deepcopy(_PRESETS[key])
