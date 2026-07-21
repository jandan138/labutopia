from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG_PATH = (
    REPO_ROOT / "config/level1_pour_online_fluid_native_expert_contact_v1.yaml"
)
CANDIDATE_CONFIG_PATH = (
    REPO_ROOT / "config/diagnostic_level1_pour_source_rest_offset_zero_v1.yaml"
)
EXTENDED_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_source_rest_offset_zero_extended_settle_v1.yaml"
)
HZ600_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_source_rest_offset_zero_600hz_v1.yaml"
)
BASE_ASSET_NAME = "lab_001_level1_pour_interndata_contact_grasp_v1.usda"
CANDIDATE_ASSET_PATH = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_v1.usda"
)


def test_rest_offset_candidate_overlay_has_one_physics_opinion():
    assert CANDIDATE_ASSET_PATH.read_text(encoding="utf-8") == f"""#usda 1.0
(
    defaultPrim = "World"
    subLayers = [
        @{BASE_ASSET_NAME}@
    ]
)

over "World"
{{
    over "beaker2"
    {{
        over "mesh"
        {{
            float physxCollision:restOffset = 0
        }}
    }}
}}
"""


def test_rest_offset_candidate_config_diff_is_allowlisted():
    baseline = yaml.safe_load(BASE_CONFIG_PATH.read_text(encoding="utf-8"))
    candidate = yaml.safe_load(CANDIDATE_CONFIG_PATH.read_text(encoding="utf-8"))

    normalized = deepcopy(candidate)
    normalized["name"] = baseline["name"]
    normalized["usd_path"] = baseline["usd_path"]
    normalized["online_fluid"]["performance_label"] = baseline["online_fluid"][
        "performance_label"
    ]

    assert normalized == baseline
    assert candidate["usd_path"].endswith(CANDIDATE_ASSET_PATH.name)
    assert not CANDIDATE_CONFIG_PATH.name.startswith("level1_pour_online_fluid")


def test_rest_offset_candidate_composes_zero_over_inherited_negative_offset():
    Usd = pytest.importorskip("pxr.Usd")
    stage = Usd.Stage.Open(str(CANDIDATE_ASSET_PATH))
    root = stage.GetRootLayer()
    shell = stage.GetPrimAtPath("/World/beaker2/mesh")
    rest_offset = shell.GetAttribute("physxCollision:restOffset")
    contact_offset = shell.GetAttribute("physxCollision:contactOffset")

    assert root.subLayerPaths == [BASE_ASSET_NAME]
    assert rest_offset.Get() == 0.0
    rest_stack = rest_offset.GetPropertyStack()
    assert rest_stack[0].layer == root
    assert rest_stack[0].default == 0.0
    assert any(spec.default == pytest.approx(-0.001) for spec in rest_stack[1:])
    assert contact_offset.Get() == pytest.approx(0.002)
    assert all(spec.layer != root for spec in contact_offset.GetPropertyStack())


def test_extended_settle_config_changes_only_pre_roll_and_labels():
    baseline = yaml.safe_load(CANDIDATE_CONFIG_PATH.read_text(encoding="utf-8"))
    candidate = yaml.safe_load(EXTENDED_CONFIG_PATH.read_text(encoding="utf-8"))

    normalized = deepcopy(candidate)
    normalized["name"] = baseline["name"]
    normalized["online_fluid"]["performance_label"] = baseline["online_fluid"][
        "performance_label"
    ]
    normalized["online_fluid"]["dynamic_pre_roll_steps"] = baseline[
        "online_fluid"
    ]["dynamic_pre_roll_steps"]

    assert normalized == baseline
    assert candidate["online_fluid"]["dynamic_pre_roll_steps"] == 1200
    assert candidate["online_fluid"]["filled_static_hold_steps"] == 360
    assert candidate["online_fluid"]["physics_dt"] == 1 / 120


def test_600hz_config_changes_only_duration_preserving_timing_and_labels():
    baseline = yaml.safe_load(CANDIDATE_CONFIG_PATH.read_text(encoding="utf-8"))
    candidate = yaml.safe_load(HZ600_CONFIG_PATH.read_text(encoding="utf-8"))

    normalized = deepcopy(candidate)
    normalized["name"] = baseline["name"]
    for name in (
        "performance_label",
        "physics_dt",
        "physics_substeps_per_observation",
        "dynamic_pre_roll_steps",
        "filled_static_hold_steps",
    ):
        normalized["online_fluid"][name] = baseline["online_fluid"][name]

    assert normalized == baseline
    fluid = candidate["online_fluid"]
    assert fluid["physics_dt"] == 1 / 600
    assert fluid["physics_substeps_per_observation"] == 20
    assert fluid["physics_dt"] * fluid["physics_substeps_per_observation"] == (
        fluid["rendering_dt"]
    )
    assert fluid["physics_dt"] * fluid["dynamic_pre_roll_steps"] == 1.0
    assert fluid["physics_dt"] * fluid["filled_static_hold_steps"] == 3.0
    assert 1 + fluid["dynamic_pre_roll_steps"] + fluid[
        "filled_static_hold_steps"
    ] == 2401
