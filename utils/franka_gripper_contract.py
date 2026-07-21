from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np


def _translation_dof(value: Any) -> bool:
    name = getattr(value, "name", None)
    text = str(name if name is not None else value).rsplit(".", 1)[-1]
    return text.lower() == "translation"


def gripper_pad_relative_velocities_m_s(
    *,
    joint_velocities: Any,
    dof_names: Sequence[str],
    dof_types: Sequence[Any],
    finger_joint_indices: Sequence[int],
    finger_dof_names: Sequence[str],
    meters_per_stage_unit: float,
) -> np.ndarray:
    velocities = np.asarray(joint_velocities, dtype=np.float64)
    if velocities.ndim != 1 or not np.isfinite(velocities).all():
        raise ValueError("franka_gripper_joint_velocities_invalid")
    names = tuple(dof_names)
    types = tuple(dof_types)
    expected_names = tuple(finger_dof_names)
    indices = tuple(finger_joint_indices)
    if len(names) != len(velocities) or len(types) != len(velocities):
        raise ValueError("franka_gripper_dof_metadata_invalid")
    if (
        len(indices) != 2
        or len(set(indices)) != 2
        or any(type(index) is not int for index in indices)
        or any(index < 0 or index >= len(velocities) for index in indices)
    ):
        raise ValueError("franka_gripper_indices_invalid")
    if len(expected_names) != 2 or tuple(names[index] for index in indices) != expected_names:
        raise ValueError("franka_gripper_name_index_mismatch")
    if not all(_translation_dof(types[index]) for index in indices):
        raise ValueError("franka_gripper_dof_not_translation")
    if (
        isinstance(meters_per_stage_unit, bool)
        or not isinstance(meters_per_stage_unit, (int, float, np.number))
        or not math.isfinite(float(meters_per_stage_unit))
        or float(meters_per_stage_unit) <= 0.0
    ):
        raise ValueError("franka_gripper_stage_units_invalid")
    return np.ascontiguousarray(
        velocities[np.asarray(indices, dtype=np.int64)]
        * float(meters_per_stage_unit)
    )


def gripper_aperture_rate_m_s(pad_relative_velocities_m_s: Any) -> float:
    velocities = np.asarray(pad_relative_velocities_m_s, dtype=np.float64)
    if velocities.shape != (2,) or not np.isfinite(velocities).all():
        raise ValueError("franka_gripper_pad_velocities_invalid")
    return float(np.sum(velocities))
