from isaacsim.core.api.controllers import BaseController
from isaacsim.core.api.controllers.articulation_controller import ArticulationController
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.core.utils.stage import get_stage_units

import numpy as np
import typing
from scipy.spatial.transform import Rotation as R
from utils.fixed_frame_pose import FixedFramePoseAdapter
class PourController(BaseController):
    """
    PourController implements a state machine for pouring liquid. The state transitions are as follows:

    State 0: Move above the target position (with random height offset). When XY distance is close, proceed to next state.
    State 1: Further adjust height and position (considering object size and offset). When XY distance is close, proceed to next state.
    State 2: Switch joint 7 to velocity mode, start pouring (positive velocity).
    State 3: Hold joint 7 velocity at 0, pause pouring.
    State 4: Switch joint 7 to velocity mode, pour in reverse (negative velocity).
    State 5: Hold joint 7 velocity at 0, finish pouring.

    Each state's duration is controlled by self._events_dt. State transitions are managed by self._event and self._t.
    The control process is advanced step-by-step via the forward() method, and can be reset with the reset() method.
    """

    def __init__(
        self,
        name: str,
        cspace_controller: BaseController,
        events_dt: typing.Optional[typing.List[float]] = None,
        speed: float = 1,
        position_threshold: float = 0.006,
        fixed_height_offsets: typing.Optional[typing.Sequence[float]] = None,
        target_position_offset: typing.Optional[typing.Sequence[float]] = None,
        require_entry_orientation: bool = False,
        entry_orientation_threshold_degrees: float = 5.0,
        control_to_end_effector_matrix_m: typing.Optional[np.ndarray] = None,
        direct_control_frame_targets: bool = False,
        start_event: int = 0,
    ) -> None:
        BaseController.__init__(self, name=name)
        self._start_event = start_event
        self._event = start_event
        self._t = 0
        self._last_emitted_event = None
        self._events_dt = events_dt
        if self._events_dt is None:
            self._events_dt = [dt / speed for dt in [0.002, 0.01, 0.009, 0.005, 0.009, 0.5]]
        else:
            if not isinstance(self._events_dt, np.ndarray) and not isinstance(self._events_dt, list):
                raise Exception("events dt need to be list or numpy array")
            elif isinstance(self._events_dt, np.ndarray):
                self._events_dt = self._events_dt.tolist()
            assert len(self._events_dt) == 6, "events dt need have length of 6 or less"
        self._cspace_controller = cspace_controller
        self._frame_adapter = FixedFramePoseAdapter(
            control_to_end_effector_matrix_m
        )
        if type(direct_control_frame_targets) is not bool:
            raise TypeError("direct_control_frame_targets_must_be_bool")
        self._direct_control_frame_targets = direct_control_frame_targets

        self._pour_default_speed = - 120.0 / 180.0 * np.pi
        self._position_threshold = position_threshold
        if type(require_entry_orientation) is not bool:
            raise TypeError("require_entry_orientation_must_be_bool")
        if (
            isinstance(entry_orientation_threshold_degrees, bool)
            or not isinstance(
                entry_orientation_threshold_degrees,
                (int, float, np.number),
            )
            or not np.isfinite(entry_orientation_threshold_degrees)
            or not 0.0 < float(entry_orientation_threshold_degrees) <= 180.0
        ):
            raise ValueError("entry_orientation_threshold_degrees_invalid")
        self._require_entry_orientation = require_entry_orientation
        self._entry_orientation_threshold_degrees = float(
            entry_orientation_threshold_degrees
        )
        self._pour_forward_call_index = 0
        self._reset_orientation_evidence()

        self._height_range_1 = (0.3, 0.4)
        self._height_range_2 = (0.1, 0.2)
        if fixed_height_offsets is None:
            self._fixed_height_offsets = None
        else:
            offsets = np.asarray(fixed_height_offsets, dtype=np.float64)
            if offsets.shape != (2,) or not np.all(np.isfinite(offsets)):
                raise ValueError("fixed_height_offsets_must_be_two_finite_values")
            self._fixed_height_offsets = (float(offsets[0]), float(offsets[1]))
        position_offset = np.asarray(
            (0.0, 0.0, 0.0)
            if target_position_offset is None
            else target_position_offset,
            dtype=np.float64,
        )
        if position_offset.shape != (3,) or not np.all(np.isfinite(position_offset)):
            raise ValueError("target_position_offset_must_be_three_finite_values")
        self._target_position_offset = position_offset
        self._sample_height_offsets()
        
        return

    def forward(
        self,
        articulation_controller: ArticulationController,
        source_size: np.ndarray,
        target_position: np.ndarray,
        current_joint_velocities: np.ndarray,
        gripper_position: np.ndarray,
        source_name: str = None,
        pour_speed: float = None,
        target_end_effector_orientation=R.from_euler('xyz', np.radians([0, 90, 10])).as_quat(),
        source_position: typing.Optional[np.ndarray] = None,
        current_end_effector_orientation: typing.Optional[np.ndarray] = None,
    ) -> ArticulationAction:
        """
        Execute one step of the controller.

        Args:
            articulation_controller (ArticulationController): The articulation controller for the robot.
            source_size (np.ndarray): Size of the source object being poured.
            current_joint_velocities (np.ndarray): Current joint velocities of the robot.
            pour_speed (float, optional): Speed for the pouring action. Defaults to None.

        Returns:
            ArticulationAction: Action to be executed by the ArticulationController.
        """
        def finite_position(value, name):
            position = np.asarray(value, dtype=np.float64)
            if position.shape != (3,) or not np.all(np.isfinite(position)):
                raise ValueError(f"{name}_must_be_three_finite_values")
            return position

        pour_forward_call_index = self._pour_forward_call_index
        self._pour_forward_call_index += 1
        self.object_size = source_size
        target_position = finite_position(target_position, "target_position").copy()
        gripper_position = finite_position(gripper_position, "gripper_position")
        tracked_position = gripper_position
        source_position_value = None
        if source_position is not None:
            source_position_value = finite_position(
                source_position, "source_position"
            )
            tracked_position = source_position_value
        target_position += self._target_position_offset

        def gripper_target_for(desired_source_position):
            if source_position_value is None:
                return desired_source_position
            live_offset = source_position_value - gripper_position
            return desired_source_position - live_offset

        def control_target_for(desired_end_effector_position):
            if self._direct_control_frame_targets:
                orientation = np.asarray(
                    target_end_effector_orientation, dtype=np.float64
                )
                if orientation.shape != (4,) or not np.all(np.isfinite(orientation)):
                    raise ValueError("target_end_effector_orientation_invalid")
                return desired_end_effector_position.copy(), orientation.copy()
            return self._frame_adapter.map_target_pose(
                target_position_world=desired_end_effector_position,
                target_orientation_wxyz=target_end_effector_orientation,
                meters_per_stage_unit=float(get_stage_units()),
            )
        
        if pour_speed is None:
            self._pour_speed = self._pour_default_speed
        else:
            self._pour_speed = pour_speed
            
        if  self._event >= len(self._events_dt):
            articulation_controller.switch_dof_control_mode(dof_index=6, mode="velocity")
            target_joint_velocities = [None] * current_joint_velocities.shape[0]
            return ArticulationAction(joint_velocities=target_joint_velocities)

        self._last_emitted_event = self._event
        
        if self._event == 0:
            target_position[2] += self._random_height_1
            gripper_target = gripper_target_for(target_position)
            control_position, control_orientation = control_target_for(
                gripper_target
            )
            target_joints = self._cspace_controller.forward(
                target_end_effector_position=control_position,
                target_end_effector_orientation=control_orientation,
            )
            xy_distance = np.linalg.norm(
                tracked_position[:2] - target_position[:2]
            )
            if xy_distance < 0.08:
                self._event += 1
                self._t = 0
                return target_joints
                
        elif self._event == 1:
            target_position[2] += self._random_height_2 + self.object_size[2] / 2 + self.get_pickz_offset(source_name)
            target_position[1] -= self.object_size[2] / 2 - self.get_pickz_offset(source_name)
            gripper_target = gripper_target_for(target_position)
            control_position, control_orientation = control_target_for(
                gripper_target
            )
            target_joints = self._cspace_controller.forward(
                target_end_effector_position=control_position,
                target_end_effector_orientation=control_orientation,
            )
            xy_distance = np.linalg.norm(
                tracked_position[:2] - target_position[:2]
            )
            orientation_passed = True
            if self._require_entry_orientation:
                orientation_error = self._quaternion_error_degrees(
                    current_end_effector_orientation,
                    control_orientation,
                )
                orientation_valid = orientation_error is not None
                orientation_passed = bool(
                    orientation_valid
                    and orientation_error
                    <= self._entry_orientation_threshold_degrees + 1.0e-9
                )
                self._pour_entry_orientation_evidence = {
                    "enabled": True,
                    "threshold_degrees": self._entry_orientation_threshold_degrees,
                    "error_degrees": orientation_error,
                    "valid": orientation_valid,
                    "passed": orientation_passed,
                    "pour_forward_call_index": (
                        pour_forward_call_index if orientation_passed else None
                    ),
                }
            if xy_distance < self._position_threshold and orientation_passed:
                self._event += 1
                self._t = 0
                return target_joints
            if self._require_entry_orientation:
                return target_joints
        elif self._event == 2:
            articulation_controller.switch_dof_control_mode(dof_index=6, mode="velocity")
            target_joint_velocities = [None] * current_joint_velocities.shape[0]
            target_joint_velocities[6] = self._pour_speed
            target_joints = ArticulationAction(joint_velocities=target_joint_velocities)
        elif self._event == 3:
            articulation_controller.switch_dof_control_mode(dof_index=6, mode="velocity")
            target_joint_velocities = [None] * current_joint_velocities.shape[0]
            target_joint_velocities[6] = 0
            target_joints = ArticulationAction(joint_velocities=target_joint_velocities)
        elif self._event == 4:
            articulation_controller.switch_dof_control_mode(dof_index=6, mode="velocity")
            target_joint_velocities = [None] * current_joint_velocities.shape[0]
            target_joint_velocities[6] = -self._pour_speed
            target_joints = ArticulationAction(joint_velocities=target_joint_velocities)
        elif self._event == 5:
            articulation_controller.switch_dof_control_mode(dof_index=6, mode="velocity")
            target_joint_velocities = [None] * current_joint_velocities.shape[0]
            target_joint_velocities[6] = 0
            target_joints = ArticulationAction(joint_velocities=target_joint_velocities)

        self._t += self._events_dt[self._event]
        if self._t >= 1.0:
            self._event += 1
            self._t = 0

        return target_joints

    def reset(self, events_dt: typing.Optional[typing.List[float]] = None) -> None:
        """
        Reset the state machine to start from the first phase.

        Args:
            events_dt (list of float, optional): Time duration for each phase. Defaults to None.

        Raises:
            Exception: If 'events_dt' is not a list or numpy array.
            Exception: If 'events_dt' length is greater than 3.
        """
        BaseController.reset(self)
        self._cspace_controller.reset()
        self._event = getattr(self, '_start_event', 0)
        self._t = 0
        self._last_emitted_event = None
        self._pour_forward_call_index = 0
        self._reset_orientation_evidence()
        self._start = True
        self.object_size = None
        if events_dt is not None:
            self._events_dt = events_dt
            if not isinstance(self._events_dt, np.ndarray) and not isinstance(self._events_dt, list):
                raise Exception("events dt need to be list or numpy array")
            elif isinstance(self._events_dt, np.ndarray):
                self._events_dt = self._events_dt.tolist()
            if len(self._events_dt) > 3:
                raise Exception("events dt need have length of 3 or less")

        self._sample_height_offsets()
        return

    @staticmethod
    def _quaternion_error_degrees(current, target) -> typing.Optional[float]:
        if current is None or target is None:
            return None
        current_quaternion = np.asarray(current, dtype=np.float64)
        target_quaternion = np.asarray(target, dtype=np.float64)
        if (
            current_quaternion.shape != (4,)
            or target_quaternion.shape != (4,)
            or not np.all(np.isfinite(current_quaternion))
            or not np.all(np.isfinite(target_quaternion))
        ):
            return None
        current_norm = float(np.linalg.norm(current_quaternion))
        target_norm = float(np.linalg.norm(target_quaternion))
        if current_norm <= 1.0e-12 or target_norm <= 1.0e-12:
            return None
        current_quaternion /= current_norm
        target_quaternion /= target_norm
        dot = float(abs(np.dot(current_quaternion, target_quaternion)))
        return float(np.degrees(2.0 * np.arccos(np.clip(dot, 0.0, 1.0))))

    def _reset_orientation_evidence(self) -> None:
        self._pour_entry_orientation_evidence = {
            "enabled": self._require_entry_orientation,
            "threshold_degrees": self._entry_orientation_threshold_degrees,
            "error_degrees": None,
            "valid": False,
            "passed": False,
            "pour_forward_call_index": None,
        }

    @property
    def pour_entry_orientation_evidence(self) -> dict:
        return dict(self._pour_entry_orientation_evidence)

    def _sample_height_offsets(self) -> None:
        if self._fixed_height_offsets is not None:
            self._random_height_1, self._random_height_2 = self._fixed_height_offsets
            return
        self._random_height_1 = float(np.random.uniform(*self._height_range_1))
        self._random_height_2 = float(np.random.uniform(*self._height_range_2))

    def is_done(self) -> bool:
        """
        Check if the state machine has reached the last phase.

        Returns:
            bool: True if the last phase is reached, False otherwise.
        """
        return self._event >= len(self._events_dt)
    
    def get_pickz_offset(self, item_name):
        """Calculates the vertical offset for the final grasp position.

        Args:
            item_name (str): Name of the object to be picked.

        Returns:
            float: Vertical offset in meters.
        """
        offsets = {
            "conical_bottle02": 0.03,
            "conical_bottle03": 0.07,
            "conical_bottle04": 0.08,
            "beaker2": 0.02,
            "graduated_cylinder_01": 0.0,
            "graduated_cylinder_02": 0.0,
            "graduated_cylinder_03": 0.0,
            "graduated_cylinder_04": 0.0,
            "volume_flask": 0.05,
            "beaker": 0.02,
            "beaker_l": 0.02,
            
        }

        for key in offsets:
            if key in item_name.lower():
                return offsets[key]

        return self.object_size[2] * 2 / 5
