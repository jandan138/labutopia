from __future__ import annotations

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config/level1_pour_online_fluid.yaml"
V2_CONFIG_PATH = REPO_ROOT / "config/level1_pour_online_fluid_v2.yaml"
CONTACT_PICK_CONFIG_PATH = (
    REPO_ROOT / "config/level1_pour_online_fluid_contact_grasp_v1.yaml"
)
NATIVE_EXPERT_CONFIG_PATH = (
    REPO_ROOT / "config/level1_pour_online_fluid_native_expert_contact_v1.yaml"
)
REAL_GRASP_SOURCE_OWNERSHIP = "contact_friction_dynamic_v1"
LEGACY_ATTACHMENT_KEYS = {
    "attachment_matrix_policy",
    "expert_attachment",
    "gripper_frame_path",
    "synthetic_attachment_collision_filter_root_path",
}


def _config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _real_grasp_configs():
    matches = []
    for path in sorted((REPO_ROOT / "config").glob("level1_pour_online_fluid*.yaml")):
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        fluid = cfg.get("online_fluid", {})
        if fluid.get("source_ownership") == REAL_GRASP_SOURCE_OWNERSHIP:
            matches.append((path, cfg))
    return matches


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
    assert fluid["expert_control_profile"] == "stabilized_online_fluid_v1"
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


def test_all_online_fluid_configs_declare_an_explicit_control_profile():
    for path in sorted((REPO_ROOT / "config").glob("level1_pour_online_fluid*.yaml")):
        fluid = yaml.safe_load(path.read_text(encoding="utf-8"))["online_fluid"]
        assert fluid["expert_control_profile"] in {
            "stabilized_online_fluid_v1",
            "contact_pick_v1",
            "native_expert_v1",
        }


def test_contact_pick_config_uses_strict_dynamic_contact_contract():
    matches = _real_grasp_configs()

    assert len(matches) == 2
    path, cfg = next(item for item in matches if item[0] == CONTACT_PICK_CONFIG_PATH)
    fluid = cfg["online_fluid"]

    assert path not in {CONFIG_PATH, V2_CONFIG_PATH}
    assert fluid["source_ownership"] == REAL_GRASP_SOURCE_OWNERSHIP
    assert fluid["expert_control_profile"] == "contact_pick_v1"
    assert LEGACY_ATTACHMENT_KEYS.isdisjoint(fluid)
    assert fluid["grasp_finger_joint_target_m"] == 0.037
    assert fluid["expert_pick_target_orientation_wxyz"] == [
        0.0,
        0.0,
        1.0,
        0.0,
    ]
    assert fluid["physics_dt"] * fluid["physics_substeps_per_observation"] == (
        fluid["rendering_dt"]
    )
    assert fluid["grasp_target_frame_name"] == "tool_center"
    assert fluid["rmpflow_control_frame_name"] == "right_gripper"
    assert fluid["finger_joint_indices"] == [7, 8]
    assert fluid["grasp_contact_max_pad_relative_speed_mps"] == 0.002
    assert fluid["grasp_preclose_source_translation_limit_m"] == 0.002
    assert fluid["grasp_preclose_source_tilt_limit_degrees"] == 1.0
    assert fluid["grasp_height_axis_object"] == [0.0, 1.0, 0.0]
    assert fluid["grasp_height_band_m"] == [-0.02, 0.02]
    assert fluid["grasp_contact_max_bilateral_height_difference_m"] == 0.005
    assert fluid["grasp_contact_min_inward_normal_cosine"] == 0.8
    assert fluid["grasp_contact_min_opposing_normal_cosine"] == 0.8
    assert fluid["grasp_effective_payload_mass_kg"] == 0.02
    assert fluid["grasp_effective_friction"] == 1.0
    assert fluid["grasp_payload_mass_authority"] == (
        "authored_dry_vessel_only_v1"
    )
    assert fluid["rmpflow_control_to_grasp_matrix_m"] == [
        [-1.0, 0.0, 0.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, -0.0034, 1.0],
    ]


def test_native_expert_dynamic_config_preserves_original_command_policy():
    cfg = yaml.safe_load(NATIVE_EXPERT_CONFIG_PATH.read_text(encoding="utf-8"))
    fluid = cfg["online_fluid"]

    assert cfg["usd_path"] == (
        "assets/chemistry_lab/lab_001_fluid_eval/"
        "lab_001_level1_pour_interndata_contact_grasp_v1.usda"
    )
    assert cfg["max_episodes"] == 1
    assert fluid["max_attempts"] == 1
    assert fluid["source_ownership"] == REAL_GRASP_SOURCE_OWNERSHIP
    assert fluid["expert_control_profile"] == "native_expert_v1"
    assert LEGACY_ATTACHMENT_KEYS.isdisjoint(fluid)
    assert fluid["grasp_finger_joint_target_m"] == 0.028
    assert fluid["expert_pick_lift_height_m"] == 0.5
    assert fluid["expert_pour_speed_rad_s"] == -1.0
    assert fluid["expert_pour_target_offset_m"] == [0.0, 0.0, 0.0]
    assert fluid["expert_pour_position_control"] == "gripper_tracked_native_v1"
    assert "expert_pick_gripper_offset_object_m" not in fluid
    assert "expert_pick_target_orientation_wxyz" not in fluid
    assert "expert_pour_target_orientation_wxyz" not in fluid
    assert "expert_pour_entry_orientation_required" not in fluid
    assert "expert_pour_height_offsets_m" not in fluid
    assert fluid["grasp_height_axis_object"] == [0.0, 1.0, 0.0]
    assert fluid["grasp_payload_mass_authority"] == (
        "authored_dry_vessel_only_v1"
    )


def test_dynamic_grasp_axis_matches_the_authored_wrapper_vessel_axis():
    Usd = pytest.importorskip("pxr.Usd")
    from tools.labutopia_fluid.real_beaker import (
        derive_authored_fluid_wrapper_frame,
    )

    cfg = yaml.safe_load(NATIVE_EXPERT_CONFIG_PATH.read_text(encoding="utf-8"))
    stage = Usd.Stage.Open(str(REPO_ROOT / cfg["usd_path"]))
    frame = derive_authored_fluid_wrapper_frame(
        stage,
        parent_path=cfg["online_fluid"]["source_actor_path"],
        visual_mesh_path=cfg["online_fluid"]["source_visual_mesh_path"],
    )

    assert frame.parent_local_axis == "Y"
    assert cfg["online_fluid"]["grasp_height_axis_object"] == [0.0, 1.0, 0.0]
    contact_cfg = yaml.safe_load(
        CONTACT_PICK_CONFIG_PATH.read_text(encoding="utf-8")
    )
    assert contact_cfg["online_fluid"]["grasp_height_axis_object"] == [
        0.0,
        1.0,
        0.0,
    ]


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
    assert all("frequency" not in camera for camera in cfg["cameras"])


def test_v2_final_online_contract_is_separate_and_explicit():
    cfg = yaml.safe_load(V2_CONFIG_PATH.read_text(encoding="utf-8"))
    fluid = cfg["online_fluid"]

    assert cfg["usd_path"] == _config()["usd_path"]
    assert cfg["controller_type"] == "pour"
    assert fluid["expert_control_profile"] == "stabilized_online_fluid_v1"
    assert fluid["camera_contract"] == "level1_pour_rgb_v4_full_action_30hz"
    assert fluid["camera_contract_compatibility"] == "requires_v4_data_or_model"
    assert len(fluid["camera_contract_sha256"]) == 64
    assert fluid["presentation_video"] == {
        "camera_names": ["camera_1", "camera_2"],
        "resolution": [1280, 720],
        "fps": 30,
        "framing": "preserve_vertical_fov",
    }
    assert fluid["initial_render_warmup_updates"] == 64
    assert cfg["max_episodes"] == 1
    assert fluid["max_observations_per_episode"] == 1200
    assert fluid["synthetic_attachment_collision_filter_root_path"] == (
        "/World/Franka"
    )
    assert cfg["robot"]["usd_path"] == "assets/robots/Franka.usd"
    assert cfg["robot"]["camera_frequency"] == 30
    assert fluid["expert_pour_height_offsets_m"] == [0.4, 0.14]
    assert fluid["expert_pour_entry_orientation_required"] is True
    assert fluid["expert_pour_entry_orientation_threshold_degrees"] == 5.0
    assert fluid["expert_pick_target_orientation_wxyz"] == [
        0.041126549288126785,
        0.7652732142089947,
        0.2961095276677087,
        0.5700742602348328,
    ]
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
    assert [camera["focal_length"] for camera in cfg["cameras"]] == [16, 16]
    assert all(camera["clipping_range"] == [0.01, 100.0] for camera in cfg["cameras"])
    assert all(camera["frequency"] == 30 for camera in cfg["cameras"])
