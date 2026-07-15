from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config/level1_pour_online_fluid.yaml"
V2_CONFIG_PATH = REPO_ROOT / "config/level1_pour_online_fluid_v2.yaml"


def _config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_online_fluid_config_uses_tracked_self_contained_asset():
    cfg = _config()
    usd_path = Path(cfg["usd_path"])

    assert not usd_path.is_absolute()
    assert usd_path.parts[0] == "assets"
    assert "outputs" not in usd_path.parts
    assert (REPO_ROOT / usd_path).is_file()
    assert cfg["online_fluid"]["enabled"] is True
    assert cfg["online_fluid"]["fixed_layout"] is True


def test_online_fluid_config_pins_physics_and_particle_authority():
    cfg = _config()
    fluid = cfg["online_fluid"]

    assert fluid["physics_scene_path"] == "/World/PhysicsScene"
    assert fluid["physics_dt"] == 1 / 120
    assert fluid["rendering_dt"] == 1 / 30
    assert fluid["physics_substeps_per_observation"] == 4
    assert fluid["particle_path"] == "/World/InternDataParityFluid/Particles"
    assert fluid["particle_system_path"] == (
        "/World/InternDataParityFluid/ParticleSystem"
    )
    assert fluid["expected_particle_count"] == 3600
    assert fluid["minimum_target_particles"] == 150
    assert fluid["minimum_task_target_fraction"] == 0.5
    assert fluid["minimum_expert_target_fraction"] == 0.9
    assert fluid["metric_policy_id"] == "level1_pour_transfer_v1"
    assert fluid["max_attempts"] == 6
    assert fluid["source_ownership"] == "gripper_attached_kinematic_vessel"
    assert cfg["controller_type"] == "pour"
    assert fluid["expert_pour_height_offsets_m"] == [0.4, 0.2]
    assert fluid["expert_pour_target_offset_m"] == [0.0, 0.05, 0.0]
    assert fluid["attachment_matrix_policy"] == (
        "captured_translation_then_recaptured_full_at_scripted_pour"
    )
    assert fluid["expert_pour_position_control"] == (
        "source_center_live_offset_v1"
    )
    assert "expert_attachment" not in fluid


def test_online_fluid_config_has_one_explicit_model_camera_contract():
    cfg = _config()
    fluid = cfg["online_fluid"]

    assert fluid["camera_contract"] == "level1_pour_rgb_v1_legacy_5mm"
    assert fluid["model_camera_keys"] == ["camera_1_rgb", "camera_2_rgb"]
    assert [camera["name"] for camera in cfg["cameras"]] == [
        "camera_1",
        "camera_2",
    ]
    assert all(camera["resolution"] == [256, 256] for camera in cfg["cameras"])
    assert all(camera["focal_length"] == 5 for camera in cfg["cameras"])


def test_v2_liquid_aware_camera_contract_is_separate_and_explicit():
    cfg = yaml.safe_load(V2_CONFIG_PATH.read_text(encoding="utf-8"))
    fluid = cfg["online_fluid"]

    assert cfg["usd_path"] == _config()["usd_path"]
    assert cfg["controller_type"] == "pour"
    assert fluid["camera_contract"] == "level1_pour_rgb_v2_liquid_aware"
    assert fluid["camera_contract_compatibility"] == "requires_v2_data_or_model"
    assert fluid["model_camera_keys"] == ["camera_1_rgb", "camera_2_rgb"]
    assert [camera["prim_path"] for camera in cfg["cameras"]] == [
        "/World/InternDataParityCamera",
        "/World/InternDataParityCloseupCamera",
    ]
    assert [camera["name"] for camera in cfg["cameras"]] == [
        "camera_1",
        "camera_2",
    ]
    assert all(camera["resolution"] == [256, 256] for camera in cfg["cameras"])
    assert [camera["focal_length"] for camera in cfg["cameras"]] == [16, 22]
    assert all(camera["clipping_range"] == [0.01, 100.0] for camera in cfg["cameras"])
