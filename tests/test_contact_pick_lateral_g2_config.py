from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_600hz_step600_layout_v1.yaml"
)
FAST_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_fast_preroll120_v1.yaml"
)
SENSOR_HEALTH_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_fast_preroll20_sensor_health_v1.yaml"
)
SENSOR_TOPOLOGY_CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_fast_preroll1_sensor_topology_v1.yaml"
)


def test_lateral_g2_candidate_is_controlled_and_cannot_enter_lift_or_pour():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    fluid = config["online_fluid"]

    assert config["mode"] == "collect"
    assert config["max_episodes"] == 1
    assert fluid["expert_control_profile"] == "contact_pick_v1"
    assert fluid["execution_mode"] == "contact_acquisition_probe_v1"
    assert fluid["source_ownership"] == "contact_friction_dynamic_v1"
    assert fluid["expert_pick_approach_direction_world"] == [1.0, 0.0, 0.0]
    assert fluid["expert_pick_gripper_offset_object_m"] == [0.0, 0.0, 0.0]
    assert fluid["expert_pick_pregrasp_distance_m"] > fluid[
        "expert_pick_insert_distance_m"
    ]
    assert fluid["controlled_contact_close_required_steps"] >= 5
    assert fluid["controlled_contact_contact_settle_required_steps"] >= 60
    assert fluid["controlled_contact_baseline_collider_pairs"] == [
        ["/World/beaker2/mesh", "/World/Cube"]
    ]
    assert fluid["controlled_contact_maximum_source_angular_speed_degrees_s"] == 2.0
    assert "synthetic_attachment_collision_filter_root_path" not in fluid
    assert "attachment_matrix_policy" not in fluid


def test_fast_lateral_g2_overlay_is_explicitly_diagnostic_only():
    config = yaml.safe_load(FAST_CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["defaults"] == [
        "diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_600hz_step600_layout_v1",
        "_self_",
    ]
    assert config["name"] == (
        "Diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_fast_preroll120_v1"
    )
    assert config["online_fluid"]["dynamic_pre_roll_steps"] == 120
    assert "fast_preroll120" in config["online_fluid"]["performance_label"]


def test_sensor_health_overlay_stops_after_the_minimum_readiness_window():
    config = yaml.safe_load(SENSOR_HEALTH_CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["defaults"] == [
        "diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_600hz_step600_layout_v1",
        "_self_",
    ]
    assert config["name"] == (
        "Diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_"
        "fast_preroll20_sensor_health_v1"
    )
    assert config["online_fluid"]["dynamic_pre_roll_steps"] == 20
    assert "sensor_health" in config["online_fluid"]["performance_label"]


def test_sensor_topology_overlay_stops_before_any_controller_action():
    config = yaml.safe_load(SENSOR_TOPOLOGY_CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["defaults"] == [
        "diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_600hz_step600_layout_v1",
        "_self_",
    ]
    assert config["name"] == (
        "Diagnostic_level1_pour_contact_pick_lateral_x_positive_g2_"
        "fast_preroll1_sensor_topology_v1"
    )
    assert config["online_fluid"]["dynamic_pre_roll_steps"] == 1
    assert "sensor_topology" in config["online_fluid"]["performance_label"]
