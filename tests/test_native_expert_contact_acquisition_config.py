from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_close_only_600hz_step600_layout_v1.yaml"
)
CANDIDATE_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_contact_acquisition_600hz_step600_layout_v1.yaml"
)
SENSOR_CADENCE_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_contact_acquisition_fast_preroll1_sensor_cadence_v1.yaml"
)


def test_contact_acquisition_config_is_an_exact_g2_clone():
    source = SOURCE_CONFIG_PATH.read_bytes()
    replacements = (
        (
            b"name: Diagnostic_level1_pour_native_expert_close_only_600hz_step600_layout_v1",
            b"name: Diagnostic_level1_pour_native_expert_contact_acquisition_600hz_step600_layout_v1",
        ),
        (
            b'  execution_mode: "close_contact_allowed_v1"',
            b'  execution_mode: "contact_acquisition_probe_v1"',
        ),
        (
            b'  performance_label: "native_expert_close_only_dynamic_contact_rest_offset_zero_600hz_step600_layout_diagnostic"',
            b'  performance_label: "native_expert_contact_acquisition_dynamic_contact_rest_offset_zero_600hz_step600_layout_diagnostic"',
        ),
    )
    expected = source
    for old, new in replacements:
        assert expected.count(old) == 1
        expected = expected.replace(old, new)

    assert CANDIDATE_CONFIG_PATH.read_bytes() == expected


def test_native_sensor_cadence_overlay_is_one_step_diagnostic_only():
    config = yaml.safe_load(SENSOR_CADENCE_CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["defaults"] == [
        "diagnostic_level1_pour_native_expert_contact_acquisition_600hz_step600_layout_v1",
        "_self_",
    ]
    assert config["name"] == (
        "Diagnostic_level1_pour_native_expert_contact_acquisition_"
        "fast_preroll1_sensor_cadence_v1"
    )
    assert config["online_fluid"]["dynamic_pre_roll_steps"] == 1
    assert "sensor_cadence" in config["online_fluid"]["performance_label"]
