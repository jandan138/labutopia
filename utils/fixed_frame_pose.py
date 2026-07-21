from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.spatial.transform import Rotation


class FixedFramePoseAdapter:
    """Map a desired target-frame world pose to a fixed control frame."""

    def __init__(self, control_to_target_matrix_m: Any | None = None) -> None:
        matrix = np.eye(4, dtype=np.float64)
        if control_to_target_matrix_m is not None:
            matrix = np.asarray(control_to_target_matrix_m, dtype=np.float64)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
            raise ValueError("fixed_frame_control_to_target_matrix_invalid")
        if not np.allclose(
            matrix[:, 3],
            [0.0, 0.0, 0.0, 1.0],
            rtol=0.0,
            atol=1.0e-12,
        ):
            raise ValueError("fixed_frame_control_to_target_matrix_not_row_affine")
        rotation = matrix[:3, :3]
        if not np.allclose(
            rotation @ rotation.T,
            np.eye(3),
            rtol=0.0,
            atol=1.0e-8,
        ) or not math.isclose(
            float(np.linalg.det(rotation)),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-8,
        ):
            raise ValueError("fixed_frame_control_to_target_matrix_not_rigid")
        self._matrix_m = np.ascontiguousarray(matrix)

    @property
    def matrix_m(self) -> np.ndarray:
        return self._matrix_m.copy()

    def map_target_pose(
        self,
        *,
        target_position_world: Any,
        target_orientation_wxyz: Any,
        meters_per_stage_unit: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        position = np.asarray(target_position_world, dtype=np.float64)
        quaternion = np.asarray(target_orientation_wxyz, dtype=np.float64)
        if position.shape != (3,) or not np.isfinite(position).all():
            raise ValueError("fixed_frame_target_position_invalid")
        if (
            quaternion.shape != (4,)
            or not np.isfinite(quaternion).all()
            or float(np.linalg.norm(quaternion)) <= 1.0e-12
        ):
            raise ValueError("fixed_frame_target_orientation_invalid")
        if (
            isinstance(meters_per_stage_unit, bool)
            or not isinstance(meters_per_stage_unit, (int, float, np.number))
            or not math.isfinite(float(meters_per_stage_unit))
            or float(meters_per_stage_unit) <= 0.0
        ):
            raise ValueError("fixed_frame_stage_units_invalid")

        quaternion = quaternion / np.linalg.norm(quaternion)
        target_world = np.eye(4, dtype=np.float64)
        target_world[:3, :3] = Rotation.from_quat(
            quaternion[[1, 2, 3, 0]]
        ).as_matrix().T
        target_world[3, :3] = position

        control_to_target = self._matrix_m.copy()
        control_to_target[3, :3] /= float(meters_per_stage_unit)
        control_world = control_to_target @ target_world
        control_xyzw = Rotation.from_matrix(
            control_world[:3, :3].T
        ).as_quat()
        control_wxyz = control_xyzw[[3, 0, 1, 2]]
        return (
            np.ascontiguousarray(control_world[3, :3]),
            np.ascontiguousarray(control_wxyz),
        )
