from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import yaml

from tools.labutopia_fluid import build_step600_particle_layout_overlay as builder
from utils.online_fluid_surface import canonical_position_sha256


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG_PATH = (
    REPO_ROOT / "config/diagnostic_level1_pour_source_rest_offset_zero_600hz_v1.yaml"
)
CANDIDATE_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_source_rest_offset_zero_600hz_step600_layout_v1.yaml"
)
CANDIDATE_ASSET_PATH = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
BASE_ASSET_NAME = (
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_v1.usda"
)
EXPECTED_POINT_HASH = "eddddcb010e3078cf5d0ed60e369c7bd51470e94edb84cdc097b2b9ba60ff6ef"


def _row_matrix(degrees: float, translation: tuple[float, float, float]):
    angle = np.radians(degrees)
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = [
        [np.cos(angle), np.sin(angle), 0.0],
        [-np.sin(angle), np.cos(angle), 0.0],
        [0.0, 0.0, 1.0],
    ]
    matrix[3, :3] = translation
    return matrix


def test_rebase_particle_positions_uses_full_row_affine_transform():
    source_step = _row_matrix(31.0, (0.3, -0.2, 0.8))
    source_target = _row_matrix(-17.0, (-0.1, 0.4, 0.7))
    particle_authored_world = _row_matrix(9.0, (0.02, -0.03, 0.01))
    source_local = np.asarray(
        [[0.01, 0.02, 0.03], [-0.04, 0.05, 0.06], [0.07, -0.08, 0.09]],
        dtype=np.float64,
    )
    source_local_h = np.column_stack([source_local, np.ones(len(source_local))])
    positions_world = (source_local_h @ source_step)[:, :3]

    result = builder.rebase_particle_positions(
        positions_world,
        source_world_at_selected_step=source_step,
        target_source_world=source_target,
        particle_authored_world=particle_authored_world,
        expected_particle_count=3,
    )

    expected = (
        source_local_h @ source_target @ np.linalg.inv(particle_authored_world)
    )[:, :3]
    np.testing.assert_allclose(result, expected, rtol=0.0, atol=1e-12)
    reconstructed_world = (
        np.column_stack([result, np.ones(len(result))])
        @ particle_authored_world
        @ np.linalg.inv(source_target)
        @ source_step
    )[:, :3]
    np.testing.assert_allclose(
        reconstructed_world,
        positions_world,
        rtol=0.0,
        atol=1e-12,
    )


@pytest.mark.parametrize(
    "positions,expected_count",
    [
        ([[0.0, 0.0]], 1),
        ([[0.0, np.nan, 0.0]], 1),
        ([[0.0, 0.0, 0.0]], 2),
    ],
)
def test_rebase_particle_positions_rejects_invalid_input(positions, expected_count):
    with pytest.raises(ValueError, match="step600_particle_.*_invalid"):
        builder.rebase_particle_positions(
            positions,
            source_world_at_selected_step=np.eye(4),
            target_source_world=np.eye(4),
            particle_authored_world=np.eye(4),
            expected_particle_count=expected_count,
        )


def test_step600_candidate_config_diff_is_allowlisted():
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


def test_step600_overlay_changes_only_particle_position_arrays():
    Usd = pytest.importorskip("pxr.Usd")
    stage = Usd.Stage.Open(str(CANDIDATE_ASSET_PATH))
    root = stage.GetRootLayer()
    particle = stage.GetPrimAtPath("/World/InternDataParityFluid/Particles")
    points = np.asarray(particle.GetAttribute("points").Get(), dtype=np.float64)
    simulation = np.asarray(
        particle.GetAttribute("physxParticle:simulationPoints").Get(),
        dtype=np.float64,
    )
    velocities = np.asarray(
        particle.GetAttribute("velocities").Get(), dtype=np.float64
    )

    assert root.defaultPrim == "World"
    assert root.subLayerPaths == [BASE_ASSET_NAME]
    assert root.customLayerData["selected_local_step"] == 600
    text = root.ExportToString()
    assert text.count("point3f[]") == 2
    assert "velocities" not in text
    assert "widths" not in text
    assert "xformOp" not in text
    assert points.shape == simulation.shape == velocities.shape == (3600, 3)
    assert np.array_equal(points, simulation)
    assert len(np.unique(points, axis=0)) == 3600
    assert canonical_position_sha256(points) == EXPECTED_POINT_HASH
    assert np.count_nonzero(velocities) == 0
    assert all(
        spec.layer != root
        for spec in particle.GetAttribute("velocities").GetPropertyStack()
    )
