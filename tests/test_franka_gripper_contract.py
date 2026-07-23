from __future__ import annotations

import numpy as np
import pytest

from utils.franka_gripper_contract import (
    franka_contact_sensor_prim_paths,
    gripper_aperture_rate_m_s,
    gripper_pad_relative_velocities_m_s,
)


def test_gripper_qdot_is_name_mapped_and_converted_to_meters_per_second():
    result = gripper_pad_relative_velocities_m_s(
        joint_velocities=[10.0, 1.5, -2.0],
        dof_names=["arm", "right", "left"],
        dof_types=["rotation", "translation", "translation"],
        finger_joint_indices=[2, 1],
        finger_dof_names=["left", "right"],
        meters_per_stage_unit=0.01,
    )

    np.testing.assert_allclose(result, [-0.02, 0.015])
    assert gripper_aperture_rate_m_s(result) == pytest.approx(-0.005)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("dof_names", ["arm", "left", "right"], "name_index_mismatch"),
        ("dof_types", ["rotation", "rotation", "translation"], "not_translation"),
        ("finger_joint_indices", [2, 2], "indices_invalid"),
    ],
)
def test_gripper_qdot_contract_fails_closed(field, replacement, message):
    kwargs = {
        "joint_velocities": [10.0, 1.5, -2.0],
        "dof_names": ["arm", "right", "left"],
        "dof_types": ["rotation", "translation", "translation"],
        "finger_joint_indices": [2, 1],
        "finger_dof_names": ["left", "right"],
        "meters_per_stage_unit": 0.01,
    }
    kwargs[field] = replacement

    with pytest.raises(ValueError, match=message):
        gripper_pad_relative_velocities_m_s(**kwargs)


def test_contact_sensors_are_parented_under_collision_geometry():
    assert franka_contact_sensor_prim_paths("/World/Franka") == {
        "left": (
            "/World/Franka/panda_leftfinger/geometry/panda_leftfinger/"
            "contact_sensor"
        ),
        "right": (
            "/World/Franka/panda_rightfinger/geometry/panda_rightfinger/"
            "contact_sensor"
        ),
        "hand": "/World/Franka/panda_hand/geometry/panda_hand/contact_sensor",
    }


@pytest.mark.parametrize("robot_prim_path", ("World/Franka", "/", "/World/Franka/"))
def test_contact_sensor_paths_reject_invalid_robot_root(robot_prim_path):
    with pytest.raises(ValueError, match="franka_contact_sensor_robot_path_invalid"):
        franka_contact_sensor_prim_paths(robot_prim_path)
