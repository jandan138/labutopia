# SPDX-FileCopyrightText: Copyright (c) 2021-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import List, Optional

import carb
import numpy as np
from isaacsim.core.api.robots.robot import Robot
from isaacsim.core.prims import SingleRigidPrim
from isaacsim.core.utils.prims import get_prim_at_path
from isaacsim.core.utils.stage import add_reference_to_stage, get_stage_units
from isaacsim.robot.manipulators.grippers.parallel_gripper import ParallelGripper
from isaacsim.storage.native import get_assets_root_path
from isaacsim.sensors.physics import ContactSensor
from isaacsim.sensors.camera import Camera

from utils.object_utils import ObjectUtils
from utils.franka_gripper_contract import (
    gripper_pad_relative_velocities_m_s,
)


class Franka(Robot):
    """[summary]

    Args:
        prim_path (str): [description]
        name (str, optional): [description]. Defaults to "franka_robot".
        usd_path (Optional[str], optional): [description]. Defaults to None.
        position (Optional[np.ndarray], optional): [description]. Defaults to None.
        orientation (Optional[np.ndarray], optional): [description]. Defaults to None.
        end_effector_prim_name (Optional[str], optional): [description]. Defaults to None.
        gripper_dof_names (Optional[List[str]], optional): [description]. Defaults to None.
        gripper_open_position (Optional[np.ndarray], optional): [description]. Defaults to None.
        gripper_closed_position (Optional[np.ndarray], optional): [description]. Defaults to None.
    """

    def __init__(
        self,
        prim_path: str = "/World/Franka",
        name: str = "franka",
        usd_path: Optional[str] = None,
        position: Optional[np.ndarray] = None,
        orientation: Optional[np.ndarray] = None,
        end_effector_prim_name: Optional[str] = None,
        gripper_dof_names: Optional[List[str]] = None,
        gripper_open_position: Optional[np.ndarray] = None,
        gripper_closed_position: Optional[np.ndarray] = None,
        deltas: Optional[np.ndarray] = None,
        camera_frequency: int = 60,
    ) -> None:
        prim = get_prim_at_path(prim_path)
        self._end_effector = None
        self._gripper = None
        self._end_effector_prim_name = end_effector_prim_name
        self.prim_path_str = prim_path
        
        if not prim.IsValid():
            if usd_path:
                add_reference_to_stage(usd_path=usd_path, prim_path=prim_path)
            else:
                assets_root_path = get_assets_root_path()
                if assets_root_path is None:
                    carb.log_error("Could not find Isaac Sim assets folder")
                usd_path = assets_root_path + "/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd"
                add_reference_to_stage(usd_path=usd_path, prim_path=prim_path)
            if self._end_effector_prim_name is None:
                self._end_effector_prim_path = prim_path + "/panda_rightfinger"
            else:
                self._end_effector_prim_path = prim_path + "/" + end_effector_prim_name
            if gripper_dof_names is None:
                gripper_dof_names = ["panda_finger_joint1", "panda_finger_joint2"]
            if gripper_open_position is None:
                gripper_open_position = np.array([0.05, 0.05]) / get_stage_units()
            if gripper_closed_position is None:
                gripper_closed_position = np.array([0.0, 0.0])
        else:
            if self._end_effector_prim_name is None:
                self._end_effector_prim_path = prim_path + "/panda_rightfinger"
            else:
                self._end_effector_prim_path = prim_path + "/" + end_effector_prim_name
            if gripper_dof_names is None:
                gripper_dof_names = ["panda_finger_joint1", "panda_finger_joint2"]
            if gripper_open_position is None:
                gripper_open_position = np.array([0.05, 0.05]) / get_stage_units()
            if gripper_closed_position is None:
                gripper_closed_position = np.array([0.0, 0.0])
                
        self._gripper_dof_names = tuple(gripper_dof_names)
        super().__init__(
            prim_path=prim_path, name=name, position=position, orientation=orientation, articulation_controller=None
        )
        
        if gripper_dof_names is not None:
            if deltas is None:
                deltas = np.array([0.05, 0.05]) / get_stage_units()
            self._gripper = ParallelGripper(
                end_effector_prim_path=self._end_effector_prim_path,
                joint_prim_names=gripper_dof_names,
                joint_opened_positions=gripper_open_position,
                joint_closed_positions=gripper_closed_position,
                action_deltas=deltas,
            )
        
        self.left_contact_sensor = ContactSensor(
            prim_path=prim_path + "/panda_leftfinger" + "/contact_sensor",
            name="contact_sensor_{}".format(1),
            min_threshold=0,
            max_threshold=10000000,
            radius=0.1,
        )
        
        self.right_contact_sensor = ContactSensor(
            prim_path=prim_path + "/panda_rightfinger" + "/contact_sensor",
            name="contact_sensor_{}".format(0),
            min_threshold=0,
            max_threshold=10000000,
            radius=0.1,
        )
        self.hand_contact_sensor = ContactSensor(
            prim_path=prim_path + "/panda_hand/contact_sensor",
            name="contact_sensor_hand",
            min_threshold=0,
            max_threshold=10000000,
            radius=0.1,
        )
        self.camera = Camera(
            prim_path=prim_path + "/panda_hand/arm_camera",
            translation=np.array([-0.2, -0, -0.02]),
            frequency=camera_frequency,
            resolution=(256, 256),
            orientation=np.array([0.20083, 0.67799, -0.67799, -0.20083]),
        )
        self.camera.set_local_pose(orientation=np.array([0.20083, 0.67799, -0.67799, -0.20083]), camera_axes="usd")
        self.camera.set_clipping_range(near_distance=0.05)
        self.camera.set_focal_length(1.)
        return

    def get_contact_sensor(self):
        """Get contact sensors
        
        Returns:
            tuple: left finger, right finger, and hand contact sensors
        """
        return (
            self.left_contact_sensor,
            self.right_contact_sensor,
            self.hand_contact_sensor,
        )

    def initialize_contact_sensors(self, physics_dt: float) -> None:
        if not np.isfinite(physics_dt) or physics_dt <= 0.0:
            raise ValueError("contact_sensor_physics_dt_invalid")
        for sensor in self.get_contact_sensor():
            sensor.set_dt(float(physics_dt))
            sensor.initialize()
            sensor.add_raw_contact_data_to_frame()

    def read_contact_sensor_frames(self) -> dict:
        left, right, hand = self.get_contact_sensor()
        return {
            "left": dict(left.get_current_frame()),
            "right": dict(right.get_current_frame()),
            "hand": dict(hand.get_current_frame()),
        }

    def get_gripper_pad_relative_velocities_m_s(self) -> np.ndarray:
        indices = tuple(int(index) for index in self.gripper.joint_dof_indicies)
        return gripper_pad_relative_velocities_m_s(
            joint_velocities=self.get_joint_velocities(),
            dof_names=self.dof_names,
            dof_types=self._articulation_view.get_dof_types(),
            finger_joint_indices=indices,
            finger_dof_names=self._gripper_dof_names,
            meters_per_stage_unit=float(get_stage_units()),
        )

    def validate_gripper_dof_contract(
        self,
        expected_indices,
    ) -> tuple[int, int]:
        actual = tuple(int(index) for index in self.gripper.joint_dof_indicies)
        expected = tuple(int(index) for index in expected_indices)
        if actual != expected:
            raise RuntimeError(
                "franka_gripper_indices_mismatch:"
                f"expected={expected}:actual={actual}"
            )
        self.get_gripper_pad_relative_velocities_m_s()
        return actual
        
    @property
    def end_effector(self) -> SingleRigidPrim:
        """[summary]

        Returns:
            SingleRigidPrim: [description]
        """
        return self._end_effector

    @property
    def gripper(self) -> ParallelGripper:
        """[summary]

        Returns:
            ParallelGripper: [description]
        """
        return self._gripper

    def initialize(self, physics_sim_view=None) -> None:
        """[summary]"""
        super().initialize(physics_sim_view)
        self._end_effector = SingleRigidPrim(prim_path=self._end_effector_prim_path, name=self.name + "_end_effector")
        self._end_effector.initialize(physics_sim_view)
        self._gripper.initialize(
            physics_sim_view=physics_sim_view,
            articulation_apply_action_func=self.apply_action,
            get_joint_positions_func=self.get_joint_positions,
            set_joint_positions_func=self.set_joint_positions,
            dof_names=self.dof_names,
        )
        return

    def post_reset(self) -> None:
        """[summary]"""
        super().post_reset()
        self._gripper.post_reset()
        self._articulation_controller.switch_dof_control_mode(
            dof_index=self.gripper.joint_dof_indicies[0], mode="position"
        )
        self._articulation_controller.switch_dof_control_mode(
            dof_index=self.gripper.joint_dof_indicies[1], mode="position"
        )
        return

    def get_gripper_position(self) -> np.ndarray:
        """[summary]

        Returns:
            np.ndarray: [description]
        """
        return ObjectUtils.get_instance().get_object_xform_position(
                object_path=self.prim_path_str + "/panda_hand/tool_center"
            )
