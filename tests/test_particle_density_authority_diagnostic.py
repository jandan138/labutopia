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
    REPO_ROOT / "config/diagnostic_level1_pour_particle_density_explicit_v1.yaml"
)
BASE_ASSET_NAME = "lab_001_level1_pour_interndata_contact_grasp_v1.usda"
CANDIDATE_ASSET_PATH = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_density_explicit_v1.usda"
)


def test_density_candidate_overlay_has_one_physics_opinion():
    assert CANDIDATE_ASSET_PATH.read_text(encoding="utf-8") == f"""#usda 1.0
(
    defaultPrim = "World"
    subLayers = [
        @{BASE_ASSET_NAME}@
    ]
)

over "World"
{{
    over "InternDataParityFluid"
    {{
        over "Particles"
        {{
            float physics:density = 1000
        }}
    }}
}}
"""


def test_density_candidate_config_diff_is_allowlisted():
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


def test_density_candidate_composes_explicit_density_only():
    Usd = pytest.importorskip("pxr.Usd")
    stage = Usd.Stage.Open(str(CANDIDATE_ASSET_PATH))
    root = stage.GetRootLayer()

    assert root.subLayerPaths == [BASE_ASSET_NAME]
    particle = stage.GetPrimAtPath("/World/InternDataParityFluid/Particles")
    density = particle.GetAttribute("physics:density")
    mass = particle.GetAttribute("physics:mass")
    material_density = stage.GetPrimAtPath(
        "/World/InternDataParityFluid/PbdMaterial"
    ).GetAttribute("physxPBDMaterial:density")

    assert density.Get() == 1000.0
    assert density.HasAuthoredValueOpinion() is True
    assert density.GetPropertyStack()[0].layer == root
    assert mass.Get() == 0.0
    assert all(spec.layer != root for spec in mass.GetPropertyStack())
    assert material_density.HasAuthoredValueOpinion() is False
