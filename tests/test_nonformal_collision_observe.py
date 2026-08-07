from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tools.labutopia_fluid import nonformal_collision_observe as observe


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    REPO_ROOT
    / "config/diagnostic_level1_pour_native_expert_collision_observe_full_pbd_v1.yaml"
)


def _config() -> dict:
    base = yaml.safe_load(
        (
            REPO_ROOT
            / "config/diagnostic_level1_pour_native_expert_nonformal_full_pbd_demo_v1.yaml"
        ).read_text(encoding="utf-8")
    )
    base["online_fluid"].update(
        {
            "diagnostic_trajectory_mode": observe.TRAJECTORY_MODE,
            "collision_policy": observe.COLLISION_POLICY,
        }
    )
    return base


def test_collision_observe_config_is_a_native_dynamic_nonformal_route():
    config = _config()

    assert observe.validate_current_trajectory_config(config) == config
    overlay = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert overlay["online_fluid"] == {
        "diagnostic_trajectory_mode": observe.TRAJECTORY_MODE,
        "collision_policy": observe.COLLISION_POLICY,
    }


def test_collision_observe_config_rejects_attachment_or_noncontinuation():
    config = _config()
    config["online_fluid"]["collision_policy"] = "abort"
    with pytest.raises(ValueError, match="collision_observe_config_invalid"):
        observe.validate_current_trajectory_config(config)

    config = _config()
    config["online_fluid"]["expert_attachment"] = True
    with pytest.raises(ValueError, match="collision_observe_config_invalid"):
        observe.validate_current_trajectory_config(config)


def test_collision_observe_classifies_source_hand_and_robot_environment():
    kwargs = {
        "source_body_path": "/World/beaker2",
        "robot_body_paths": (
            "/World/Franka/panda_hand",
            "/World/Franka/panda_leftfinger",
            "/World/Franka/panda_rightfinger",
        ),
        "left_finger_body_path": "/World/Franka/panda_leftfinger",
        "right_finger_body_path": "/World/Franka/panda_rightfinger",
        "hand_body_path": "/World/Franka/panda_hand",
    }
    hand_header = {
        "actor0": "/World/beaker2",
        "actor1": "/World/Franka/panda_hand",
        "collider0": "/World/beaker2/mesh",
        "collider1": "/World/Franka/panda_hand/collision",
    }
    environment_header = {
        "actor0": "/World/Franka/panda_rightfinger",
        "actor1": "/World/Cube",
        "collider0": "/World/Franka/panda_rightfinger/collision",
        "collider1": "/World/Cube",
    }

    assert observe.classify_contact_header(hand_header, **kwargs) == "SOURCE_HAND"
    assert (
        observe.classify_contact_header(environment_header, **kwargs)
        == "ROBOT_ENVIRONMENT"
    )


def test_collision_observe_summary_keeps_the_first_relevant_collision():
    summary = observe.collision_summary(
        [
            {"contact_class": "NONROBOT", "physics_step": 1},
            {"contact_class": "SOURCE_HAND", "physics_step": 2},
            {"contact_class": "ROBOT_ENVIRONMENT", "physics_step": 3},
        ]
    )

    assert summary["contact_class_counts"] == {
        "NONROBOT": 1,
        "ROBOT_ENVIRONMENT": 1,
        "SOURCE_HAND": 1,
    }
    assert summary["first_robot_or_source_collision"] == {
        "contact_class": "SOURCE_HAND",
        "physics_step": 2,
    }
