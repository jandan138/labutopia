from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_source_rest_offset_zero_600hz_step600_layout_v1.yaml"
)
CANDIDATE_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_close_only_600hz_step600_layout_v1.yaml"
)
SOURCE_CONFIG_SHA256 = (
    "c0f9d636f8cde61add964ee99f11bda0ac117b8512fc2db185209c52888b08a8"
)
CANDIDATE_CONFIG_SHA256 = (
    "467596cb03a7f822215647a44cc63d379c72910a5bbf36df66ce3382df31dffe"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deep_diff(
    source: Any,
    candidate: Any,
    path: tuple[str, ...] = (),
) -> dict[tuple[str, ...], tuple[Any, Any]]:
    if isinstance(source, Mapping) and isinstance(candidate, Mapping):
        differences: dict[tuple[str, ...], tuple[Any, Any]] = {}
        for key in sorted(set(source) | set(candidate), key=str):
            key_path = (*path, str(key))
            if key not in source:
                differences[key_path] = (None, candidate[key])
            elif key not in candidate:
                differences[key_path] = (source[key], None)
            else:
                differences.update(
                    _deep_diff(source[key], candidate[key], key_path)
                )
        return differences
    if source != candidate:
        return {path: (source, candidate)}
    return {}


def test_native_expert_close_only_config_has_exact_three_path_deep_diff():
    source = yaml.safe_load(SOURCE_CONFIG_PATH.read_text(encoding="utf-8"))
    candidate = yaml.safe_load(CANDIDATE_CONFIG_PATH.read_text(encoding="utf-8"))

    assert _deep_diff(source, candidate) == {
        ("name",): (
            "Diagnostic_level1_pour_source_rest_offset_zero_600hz_step600_layout_v1",
            "Diagnostic_level1_pour_native_expert_close_only_600hz_step600_layout_v1",
        ),
        ("online_fluid", "execution_mode"): (
            "production_pour_v1",
            "contact_acquisition_probe_v1",
        ),
        ("online_fluid", "performance_label"): (
            "native_expert_dynamic_contact_rest_offset_zero_600hz_step600_layout_diagnostic",
            "native_expert_close_only_dynamic_contact_rest_offset_zero_600hz_step600_layout_diagnostic",
        ),
    }


def test_native_expert_close_only_config_is_exact_text_clone_and_hash_pinned():
    source = SOURCE_CONFIG_PATH.read_bytes()
    replacements = (
        (
            b"name: Diagnostic_level1_pour_source_rest_offset_zero_600hz_step600_layout_v1",
            b"name: Diagnostic_level1_pour_native_expert_close_only_600hz_step600_layout_v1",
        ),
        (
            b'  execution_mode: "production_pour_v1"',
            b'  execution_mode: "contact_acquisition_probe_v1"',
        ),
        (
            b'  performance_label: "native_expert_dynamic_contact_rest_offset_zero_600hz_step600_layout_diagnostic"',
            b'  performance_label: "native_expert_close_only_dynamic_contact_rest_offset_zero_600hz_step600_layout_diagnostic"',
        ),
    )
    expected = source
    for old, new in replacements:
        assert expected.count(old) == 1
        expected = expected.replace(old, new)

    assert CANDIDATE_CONFIG_PATH.read_bytes() == expected
    assert _sha256(SOURCE_CONFIG_PATH) == SOURCE_CONFIG_SHA256
    assert _sha256(CANDIDATE_CONFIG_PATH) == CANDIDATE_CONFIG_SHA256


def test_native_expert_close_only_config_preserves_bounded_runtime_contract():
    config = yaml.safe_load(CANDIDATE_CONFIG_PATH.read_text(encoding="utf-8"))
    fluid = config["online_fluid"]

    assert config["mode"] == "collect"
    assert config["max_episodes"] == 1
    assert fluid["max_attempts"] == 1
    assert fluid["max_observations_per_episode"] == 2400
    assert fluid["expert_control_profile"] == "native_expert_v1"
    assert fluid["source_ownership"] == "contact_friction_dynamic_v1"
    assert fluid["physics_dt"] == 1 / 600
    assert fluid["rendering_dt"] == 1 / 30
    assert fluid["physics_substeps_per_observation"] == 20
    assert fluid["dynamic_pre_roll_steps"] == 600
    assert fluid["expected_particle_count"] == 3600
