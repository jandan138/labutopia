#!/usr/bin/env python3
"""Newton-native Franka dynamics, IK replay, and fixed-grasp cup model."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from tools.labutopia_fluid.fluid_benchmark_contract import sha256_file


@dataclass(frozen=True)
class FrankaIkTrajectory:
    joint_targets: np.ndarray
    position_residual_m: np.ndarray
    rotation_residual_rad: np.ndarray
    timing_ms: dict[str, float]
    passed: bool


def _row_matrix_from_pose_xyzw(pose_xyzw: np.ndarray) -> np.ndarray:
    from scipy.spatial.transform import Rotation

    pose = np.asarray(pose_xyzw, dtype=np.float64)
    if pose.shape != (7,) or not np.isfinite(pose).all():
        raise ValueError("pose_xyzw_invalid")
    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = Rotation.from_quat(pose[3:]).as_matrix().T
    matrix[3, :3] = pose[:3]
    return matrix


def _pose_xyzw_from_row_matrix(matrix: np.ndarray) -> np.ndarray:
    from scipy.spatial.transform import Rotation

    value = np.asarray(matrix, dtype=np.float64)
    if value.shape != (4, 4) or not np.isfinite(value).all():
        raise ValueError("row_matrix_invalid")
    pose = np.empty(7, dtype=np.float64)
    pose[:3] = value[3, :3]
    pose[3:] = Rotation.from_matrix(value[:3, :3].T).as_quat()
    return pose


def _wp_transform(wp: Any, pose_xyzw: Sequence[float]) -> Any:
    pose = np.asarray(pose_xyzw, dtype=np.float32)
    return wp.transform(
        wp.vec3(pose[0], pose[1], pose[2]),
        wp.quat(pose[3], pose[4], pose[5], pose[6]),
    )


def _rotation_error(left_xyzw: np.ndarray, right_xyzw: np.ndarray) -> float:
    dot = abs(float(np.dot(left_xyzw, right_xyzw)))
    return 2.0 * math.acos(float(np.clip(dot, -1.0, 1.0)))


def verify_robot_asset_closure(scene_pack: Mapping[str, Any]) -> dict[str, Any]:
    robot = scene_pack.get("robot_asset")
    if not isinstance(robot, Mapping):
        raise ValueError("scene_pack_robot_asset_missing")
    path = Path(str(robot.get("path", ""))).resolve(strict=True)
    if sha256_file(path) != robot.get("sha256"):
        raise ValueError("robot_asset_hash_mismatch")
    closure = robot.get("layer_closure")
    if not isinstance(closure, list) or not closure:
        raise ValueError("robot_asset_closure_missing")
    verified = []
    for record in closure:
        if not isinstance(record, Mapping):
            raise ValueError("robot_asset_closure_record_invalid")
        layer = Path(str(record.get("path", ""))).resolve(strict=True)
        actual = sha256_file(layer)
        if actual != record.get("sha256"):
            raise ValueError(f"robot_asset_closure_hash_mismatch:{layer}")
        verified.append({"path": str(layer), "sha256": actual})
    return {
        "robot_path": str(path),
        "robot_sha256": robot["sha256"],
        "closure": verified,
    }


class FrankaDynamicsController:
    """A separate Newton articulation that supplies the dynamic cup transform.

    IK is precomputed outside measured frame timing. Measured stepping includes
    target upload, Featherstone articulation dynamics, and the fixed cup joint.
    """

    def __init__(
        self,
        *,
        robot_usd_path: str | Path,
        initial_source_pose_xyzw: np.ndarray,
        source_box_poses_xyzw: np.ndarray,
        source_box_half_extents: np.ndarray,
        source_to_gripper_row_matrix: np.ndarray,
        base_position_m: Sequence[float] = (-0.4, 0.0, 0.71),
        cup_mass_kg: float = 0.2,
        device: str = "cuda:0",
        ik_iterations: int = 24,
    ) -> None:
        import newton
        import warp as wp
        from newton import ik

        robot_path = Path(robot_usd_path).resolve(strict=True)
        self.wp = wp
        self.newton = newton
        self.ik = ik
        self.device = wp.get_device(device)
        # Newton 1.4 retains a legacy DOF-layout target mode for backward
        # compatibility.  This scene contains a free-coordinate padding slot,
        # so an IK result has ``joint_coord_count`` values while a legacy
        # Control buffer has only ``joint_dof_count`` values.  Use Newton's
        # reviewed coordinate-layout API so IK output can be bound directly to
        # position targets without dropping or reinterpreting coordinates.
        newton.use_coord_layout_targets = True
        self.ik_iterations = int(ik_iterations)
        if self.ik_iterations < 1:
            raise ValueError("ik_iterations_invalid")
        source_to_gripper = np.asarray(source_to_gripper_row_matrix, dtype=np.float64)
        if source_to_gripper.shape != (4, 4) or not np.isfinite(source_to_gripper).all():
            raise ValueError("source_to_gripper_matrix_invalid")
        self.source_to_gripper = source_to_gripper
        builder = newton.ModelBuilder(up_axis=newton.Axis.Z)
        builder.add_usd(
            str(robot_path),
            xform=wp.transform(wp.vec3(*base_position_m), wp.quat_identity()),
            floating=False,
            collapse_fixed_joints=False,
            enable_self_collisions=False,
            force_position_velocity_actuation=True,
            skip_mesh_approximation=True,
        )
        self.hand_body = next(
            index
            for index, label in enumerate(builder.body_label)
            if str(label).endswith("/panda_hand")
        )
        # The cup is rigidly grasped by construction.  Attaching its collision
        # shapes to panda_hand avoids creating an unintended second free base
        # and a loop constraint.  The LabUtopia attachment helper defines the
        # historical row transform as
        # ``source_to_gripper = source_world @ inverse(gripper_world)`` and
        # reconstructs ``source_world = source_to_gripper @ gripper_world``.
        # Transposition into Warp's column-transform convention therefore
        # makes that same matrix the hand-local source transform.
        source_in_hand_pose = _pose_xyzw_from_row_matrix(source_to_gripper)
        self.source_in_hand = _wp_transform(wp, source_in_hand_pose)
        box_poses = np.asarray(source_box_poses_xyzw, dtype=np.float64)
        box_extents = np.asarray(source_box_half_extents, dtype=np.float64)
        if box_poses.ndim != 2 or box_poses.shape[1] != 7:
            raise ValueError("source_box_poses_invalid")
        if box_extents.shape != (len(box_poses), 3):
            raise ValueError("source_box_extents_invalid")
        wrapper_volume = float(np.sum(8.0 * np.prod(box_extents, axis=1)))
        if not math.isfinite(wrapper_volume) or wrapper_volume <= 0.0:
            raise ValueError("source_wrapper_volume_invalid")
        shape_cfg = newton.ModelBuilder.ShapeConfig(
            density=float(cup_mass_kg) / wrapper_volume,
            mu=0.2,
            margin=0.0005,
        )
        for index, (pose, extent) in enumerate(
            zip(box_poses, box_extents, strict=True)
        ):
            builder.add_shape_box(
                body=self.hand_body,
                xform=wp.transform_multiply(
                    self.source_in_hand,
                    _wp_transform(wp, pose),
                ),
                hx=float(extent[0]),
                hy=float(extent[1]),
                hz=float(extent[2]),
                cfg=shape_cfg,
                label=f"/LabUtopia/source_wrapper_{index:03d}",
            )
        self.model = builder.finalize(device=self.device)
        self.model.set_gravity((0.0, 0.0, -9.81))
        self.state_0 = self.model.state()
        self.state_1 = self.model.state()
        newton.eval_fk(
            self.model,
            self.model.joint_q,
            self.model.joint_qd,
            self.state_0,
        )
        self.contacts = self.model.contacts()
        self.control = self.model.control()
        if len(self.control.joint_target_q) != self.model.joint_coord_count:
            raise RuntimeError(
                "newton_coordinate_target_layout_not_active:"
                f"control={len(self.control.joint_target_q)}:"
                f"coords={self.model.joint_coord_count}"
            )
        self.solver = newton.solvers.SolverFeatherstone(
            self.model,
            update_mass_matrix_interval=1,
            fuse_cholesky=True,
        )
        hand_pose = self.state_0.body_q.numpy()[self.hand_body]
        self.position_objective = ik.IKObjectivePosition(
            link_index=self.hand_body,
            link_offset=wp.vec3(0.0, 0.0, 0.0),
            target_positions=wp.array([hand_pose[:3]], dtype=wp.vec3, device=self.device),
        )
        self.rotation_objective = ik.IKObjectiveRotation(
            link_index=self.hand_body,
            link_offset_rotation=wp.quat_identity(),
            target_rotations=wp.array([hand_pose[3:]], dtype=wp.vec4, device=self.device),
        )
        self.limit_objective = ik.IKObjectiveJointLimit(
            joint_limit_lower=self.model.joint_limit_lower,
            joint_limit_upper=self.model.joint_limit_upper,
        )
        self.ik_solver = ik.IKSolver(
            model=self.model,
            n_problems=1,
            objectives=[
                self.position_objective,
                self.rotation_objective,
                self.limit_objective,
            ],
            lambda_initial=0.1,
            jacobian_mode=ik.IKJacobianType.ANALYTIC,
        )
        self.joint_q_ik = wp.array(
            self.model.joint_q,
            shape=(1, self.model.joint_coord_count),
            device=self.device,
        )
        from tools.labutopia_fluid.newton_gpu_pose_bridge import (
            compose_body_local_pose,
        )

        self._compose_body_local_pose = compose_body_local_pose
        self._source_pose = wp.empty(1, dtype=wp.transform, device=self.device)
        self._update_source_pose_device()

    def _update_source_pose_device(self) -> None:
        self.wp.launch(
            self._compose_body_local_pose,
            dim=1,
            inputs=[self.state_0.body_q, self.hand_body, self.source_in_hand],
            outputs=[self._source_pose],
            device=self.device,
        )

    def _gripper_target_pose(self, source_pose_xyzw: np.ndarray) -> np.ndarray:
        source_world = _row_matrix_from_pose_xyzw(source_pose_xyzw)
        gripper_world = np.linalg.inv(self.source_to_gripper) @ source_world
        return _pose_xyzw_from_row_matrix(gripper_world)

    def precompute_ik(
        self,
        source_poses_xyzw: np.ndarray,
        *,
        maximum_position_residual_m: float = 0.005,
        maximum_rotation_residual_rad: float = math.radians(3.0),
    ) -> FrankaIkTrajectory:
        poses = np.asarray(source_poses_xyzw, dtype=np.float64)
        if poses.ndim != 2 or poses.shape[1] != 7 or not np.isfinite(poses).all():
            raise ValueError("ik_source_trajectory_invalid")
        targets = np.empty(
            (len(poses), self.model.joint_coord_count),
            dtype=np.float32,
        )
        position_residuals = np.empty(len(poses), dtype=np.float64)
        rotation_residuals = np.empty(len(poses), dtype=np.float64)
        started = time.perf_counter()
        for index, source_pose in enumerate(poses):
            target = self._gripper_target_pose(source_pose)
            self.position_objective.set_target_positions(
                self.wp.array([target[:3]], dtype=self.wp.vec3, device=self.device)
            )
            self.rotation_objective.set_target_rotations(
                self.wp.array([target[3:]], dtype=self.wp.vec4, device=self.device)
            )
            self.ik_solver.step(
                self.joint_q_ik,
                self.joint_q_ik,
                iterations=self.ik_iterations,
            )
            q = self.joint_q_ik.numpy()[0]
            targets[index] = q
            state = self.model.state()
            self.newton.eval_fk(
                self.model,
                self.wp.array(q, dtype=self.wp.float32, device=self.device),
                self.model.joint_qd,
                state,
            )
            actual = state.body_q.numpy()[self.hand_body]
            position_residuals[index] = float(np.linalg.norm(actual[:3] - target[:3]))
            rotation_residuals[index] = _rotation_error(actual[3:], target[3:])
        self.wp.synchronize_device(self.device)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        passed = bool(
            np.max(position_residuals, initial=0.0) <= maximum_position_residual_m
            and np.max(rotation_residuals, initial=0.0) <= maximum_rotation_residual_rad
        )
        return FrankaIkTrajectory(
            joint_targets=targets,
            position_residual_m=position_residuals,
            rotation_residual_rad=rotation_residuals,
            timing_ms={
                "total_ms": elapsed_ms,
                "mean_per_observation_ms": elapsed_ms / len(poses),
            },
            passed=passed,
        )

    def reset(self, joint_configuration: np.ndarray | None = None) -> None:
        self.state_0 = self.model.state()
        self.state_1 = self.model.state()
        if joint_configuration is not None:
            q = np.asarray(joint_configuration, dtype=np.float32)
            if q.shape != (self.model.joint_coord_count,):
                raise ValueError("reset_joint_configuration_shape_invalid")
            self.state_0.joint_q.assign(q)
            self.state_1.joint_q.assign(q)
        self.newton.eval_fk(
            self.model,
            self.state_0.joint_q,
            self.state_0.joint_qd,
            self.state_0,
        )
        self._update_source_pose_device()

    def step(self, joint_target: np.ndarray, dt_s: float) -> float:
        target = np.asarray(joint_target, dtype=np.float32)
        if target.shape != (self.model.joint_coord_count,):
            raise ValueError("joint_target_shape_invalid")
        started = time.perf_counter()
        self.control.joint_target_q.assign(target)
        self.solver.step(
            self.state_0,
            self.state_1,
            self.control,
            self.contacts,
            float(dt_s),
        )
        self.state_0, self.state_1 = self.state_1, self.state_0
        self._update_source_pose_device()
        self.wp.synchronize_device(self.device)
        return (time.perf_counter() - started) * 1000.0

    def source_pose_device(self) -> tuple[Any, int]:
        return self._source_pose, 0

    def source_pose_numpy(self) -> np.ndarray:
        return self._source_pose.numpy()[0].copy()

    def grasp_residual(self) -> dict[str, float]:
        body_q = self.state_0.body_q.numpy()
        hand = _row_matrix_from_pose_xyzw(body_q[self.hand_body])
        source = _row_matrix_from_pose_xyzw(self.source_pose_numpy())
        expected_source = self.source_to_gripper @ hand
        actual_pose = _pose_xyzw_from_row_matrix(source)
        expected_pose = _pose_xyzw_from_row_matrix(expected_source)
        return {
            "translation_m": float(np.linalg.norm(actual_pose[:3] - expected_pose[:3])),
            "rotation_rad": _rotation_error(actual_pose[3:], expected_pose[3:]),
        }

    def dynamics_capability_preflight(self) -> dict[str, Any]:
        """Fail closed before stepping an ill-conditioned USD translation.

        The current Franka USD imports very large drive gains together with
        link inertias several orders of magnitude smaller than expected for
        kilogram-scale links.  Featherstone and XPBD both become non-finite
        when this tuple is stepped.  The preflight records the exact imported
        values and requires a reviewed unit/inertia translation before the
        full-dynamics lane is allowed to produce performance evidence.
        """
        stiffness = np.asarray(self.model.joint_target_ke.numpy(), dtype=np.float64)
        damping = np.asarray(self.model.joint_target_kd.numpy(), dtype=np.float64)
        body_mass = np.asarray(self.model.body_mass.numpy(), dtype=np.float64)
        body_inertia = np.asarray(self.model.body_inertia.numpy(), dtype=np.float64)
        diagonal = np.diagonal(body_inertia, axis1=1, axis2=2)
        positive_diagonal = diagonal[diagonal > 0.0]
        maximum_stiffness = float(np.max(stiffness, initial=0.0))
        minimum_inertia = float(np.min(positive_diagonal, initial=math.inf))
        suspicious_drive_units = maximum_stiffness >= 1.0e8
        suspicious_inertia = minimum_inertia <= 1.0e-8
        passed = not (suspicious_drive_units or suspicious_inertia)
        return {
            "passed": passed,
            "decision": "GO" if passed else "NO_GO_REVIEWED_TRANSLATION_REQUIRED",
            "checks": {
                "joint_drive_stiffness_below_1e8": not suspicious_drive_units,
                "minimum_positive_body_inertia_above_1e-8_kg_m2": not suspicious_inertia,
                "finite_imported_arrays": bool(
                    np.isfinite(stiffness).all()
                    and np.isfinite(damping).all()
                    and np.isfinite(body_mass).all()
                    and np.isfinite(body_inertia).all()
                ),
            },
            "observed": {
                "joint_target_ke": stiffness.tolist(),
                "joint_target_kd": damping.tolist(),
                "body_mass_kg": body_mass.tolist(),
                "body_inertia_kg_m2": body_inertia.tolist(),
                "maximum_joint_target_ke": maximum_stiffness,
                "minimum_positive_body_inertia_kg_m2": minimum_inertia,
            },
            "reason": (
                None
                if passed
                else "raw_newton_usd_drive_and_inertia_translation_is_ill_conditioned"
            ),
            "required_action": (
                None
                if passed
                else (
                    "review_and_attest_degree_radian_drive_conversion_and_link_"
                    "inertia_materialization_before_any_dynamics_or_timing_run"
                )
            ),
        }


def save_ik_trajectory(
    path: str | Path,
    trajectory: FrankaIkTrajectory,
    *,
    source_trajectory_sha256: str,
) -> dict[str, Any]:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"ik_trajectory_exists:{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        joint_targets=trajectory.joint_targets,
        position_residual_m=trajectory.position_residual_m,
        rotation_residual_rad=trajectory.rotation_residual_rad,
    )
    return {
        "path": str(output.resolve()),
        "sha256": sha256_file(output),
        "source_trajectory_sha256": source_trajectory_sha256,
        "passed": trajectory.passed,
        "timing_ms": trajectory.timing_ms,
        "maximum_position_residual_m": float(
            np.max(trajectory.position_residual_m, initial=0.0)
        ),
        "maximum_rotation_residual_rad": float(
            np.max(trajectory.rotation_residual_rad, initial=0.0)
        ),
    }
