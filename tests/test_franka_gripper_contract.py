from __future__ import annotations

import numpy as np
import pytest

from utils.franka_gripper_contract import (
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
