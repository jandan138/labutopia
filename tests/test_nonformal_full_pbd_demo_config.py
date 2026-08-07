from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_nonformal_full_pbd_demo_v1.yaml"
)


def test_nonformal_full_pbd_demo_uses_native_pick_without_attachment():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    fluid = config["online_fluid"]

    assert config["task_type"] == "pickpour"
    assert config["controller_type"] == "pour"
    assert config["max_episodes"] == 1
    assert fluid["expert_control_profile"] == "native_expert_v1"
    assert fluid["execution_mode"] == "nonformal_full_pbd_demo_v1"
    assert fluid["source_ownership"] == "contact_friction_dynamic_v1"
    assert fluid["source_pose_authority"] == "physx_dynamic_readback_v1"
    assert fluid["source_actor_path"] == "/World/beaker2"
    assert fluid["expected_particle_count"] == 3600
    assert fluid["grasp_finger_joint_target_m"] == 0.012
    assert fluid["expert_pick_lift_height_m"] == 0.5
    assert fluid["expert_pour_height_offsets_m"] == [0.4, 0.14]
    assert fluid["model_camera_keys"] == ["camera_1_rgb", "camera_2_rgb"]
    assert "attachment_matrix_policy" not in fluid
    assert "synthetic_attachment_collision_filter_root_path" not in fluid
    assert "gripper_frame_path" not in fluid
