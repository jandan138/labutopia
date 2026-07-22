import copy
import re
from collections.abc import Mapping
from typing import Any, Optional
from scipy.spatial.transform import Rotation as R
import numpy as np
from enum import Enum
from utils.task_utils import TaskUtils

from .atomic_actions.contact_pick_controller import ContactPickController
from .atomic_actions.pick_controller import PickController
from .atomic_actions.pour_controller import PourController
from .base_controller import BaseController

class Phase(Enum):
    PICKING = "picking"
    POURING = "pouring"
    FINISHED = "finished"

class PourTaskController(BaseController):
    def __init__(self, cfg, robot):
        online_fluid = getattr(cfg, "online_fluid", None)
        self._online_fluid_enabled = bool(
            online_fluid and getattr(online_fluid, "enabled", False)
        )
        self._expert_pour_height_offsets = None
        self._expert_pour_target_offset = (0.0, 0.0, 0.0)
        self._expert_pour_target_orientation_wxyz = None
        self._expert_pour_entry_orientation_required = False
        self._expert_pour_entry_orientation_threshold_degrees = 5.0
        self._expert_pick_gripper_offset_object = np.zeros(3, dtype=np.float64)
        self._expert_pick_target_orientation_wxyz = None
        self._source_ownership = None
        self._expert_control_profile = None
        self._contact_grasp_required = False
        self._use_contact_pick_controller = False
        self._native_expert_profile = False
        self._execution_mode = "production_pour_v1"
        self._contact_acquisition_probe = False
        self._expert_pick_lift_height_m = 0.5
        self._expert_pour_speed_rad_s = -1.0
        self._grasp_finger_joint_target_m = 0.028
        self._contact_pick_approach_direction = np.asarray(
            [0.0, 0.0, -1.0], dtype=np.float64
        )
        self._contact_pick_position_threshold_m = 0.005
        self._contact_pick_open_position_m = 0.040
        self._contact_pick_open_position_tolerance_m = 0.0002
        self._contact_pick_pregrasp_distance_m = 0.10
        self._contact_pick_insert_distance_m = 0.03
        self._contact_pick_approach_speed_m_s = 0.03
        self._contact_pick_close_speed_m_s = 0.01
        self._contact_pick_lift_speed_m_s = 0.05
        self._contact_pick_orientation_threshold_degrees = 5.0
        self._contact_pick_contact_timeout_s = 1.5
        self._contact_pick_source_translation_limit_m = 0.002
        self._contact_pick_source_tilt_limit_degrees = 1.0
        self._end_effector_target_frame = "tool_center"
        self._rmpflow_control_frame = "right_gripper"
        self._control_to_end_effector_matrix_m = np.eye(4, dtype=np.float64)
        self._finger_joint_indices = (7, 8)
        self._pour_forward_invocation_count = 0
        self._configure_online_fluid(online_fluid)
        if (
            self._contact_acquisition_probe
            and getattr(cfg, "mode", None) != "collect"
        ):
            raise ValueError("contact_acquisition_probe_requires_collect_mode")
        super().__init__(cfg, robot)
        self._collection_episode_terminal = False
        self._collection_episode_finalized = False
        self.initial_position = None
        self.initial_size = None
        self.task_utils = TaskUtils.get_instance()
        self.initial_quaternion = None
        self.pour_timer = 0
        self.pour_complete = False
        self.return_complete = False
        self.return_timer = 0
        self.last_error_info = None
        self.current_phase = Phase.PICKING

    @staticmethod
    def _normalized_vector(value, *, shape, error):
        vector = np.asarray(value, dtype=np.float64)
        if vector.shape != shape or not np.all(np.isfinite(vector)):
            raise ValueError(error)
        norm = float(np.linalg.norm(vector))
        if norm <= 1.0e-12:
            raise ValueError(error)
        return vector / norm

    def _configure_online_fluid(self, online_fluid):
        if not self._online_fluid_enabled:
            return

        self._source_ownership = str(
            getattr(online_fluid, "source_ownership", "")
        )
        self._expert_control_profile = str(
            getattr(online_fluid, "expert_control_profile", "")
        )
        if self._expert_control_profile not in (
            "stabilized_online_fluid_v1",
            "contact_pick_v1",
            "native_expert_v1",
        ):
            raise ValueError("online_fluid_expert_control_profile_unsupported")
        self._contact_grasp_required = (
            self._source_ownership == "contact_friction_dynamic_v1"
        )
        self._use_contact_pick_controller = (
            self._expert_control_profile == "contact_pick_v1"
        )
        self._native_expert_profile = (
            self._expert_control_profile == "native_expert_v1"
        )
        if (
            self._use_contact_pick_controller or self._native_expert_profile
        ) and not self._contact_grasp_required:
            raise ValueError("dynamic_expert_profile_requires_contact_ownership")
        if (
            self._expert_control_profile == "stabilized_online_fluid_v1"
            and self._contact_grasp_required
        ):
            raise ValueError("stabilized_profile_requires_kinematic_ownership")
        self._execution_mode = str(
            getattr(online_fluid, "execution_mode", "production_pour_v1")
        )
        if self._execution_mode not in (
            "production_pour_v1",
            "contact_acquisition_probe_v1",
            "close_contact_allowed_v1",
        ):
            raise ValueError("online_fluid_execution_mode_unsupported")
        self._contact_acquisition_probe = (
            self._execution_mode
            in {"contact_acquisition_probe_v1", "close_contact_allowed_v1"}
        )
        if self._contact_acquisition_probe and not self._contact_grasp_required:
            raise ValueError("contact_acquisition_probe_requires_contact_ownership")
        self._expert_pick_lift_height_m = float(
            getattr(online_fluid, "expert_pick_lift_height_m", 0.5)
        )
        self._expert_pour_speed_rad_s = float(
            getattr(online_fluid, "expert_pour_speed_rad_s", -1.0)
        )
        self._grasp_finger_joint_target_m = float(
            getattr(online_fluid, "grasp_finger_joint_target_m", 0.028)
        )
        if not 0.0 < self._expert_pick_lift_height_m <= 0.5:
            raise ValueError("expert_pick_lift_height_m_invalid")
        if not np.isfinite(self._expert_pour_speed_rad_s):
            raise ValueError("expert_pour_speed_rad_s_invalid")
        if not 0.0 <= self._grasp_finger_joint_target_m <= 0.04:
            raise ValueError("grasp_finger_joint_target_m_invalid")

        if self._use_contact_pick_controller:
            self._end_effector_target_frame = str(
                getattr(online_fluid, "grasp_target_frame_name", "")
            )
            self._rmpflow_control_frame = str(
                getattr(online_fluid, "rmpflow_control_frame_name", "")
            )
            if self._end_effector_target_frame != "tool_center":
                raise ValueError("grasp_target_frame_name_unsupported")
            if self._rmpflow_control_frame != "right_gripper":
                raise ValueError("rmpflow_control_frame_name_unsupported")
            self._control_to_end_effector_matrix_m = np.asarray(
                getattr(
                    online_fluid,
                    "rmpflow_control_to_grasp_matrix_m",
                    None,
                ),
                dtype=np.float64,
            )
            if (
                self._control_to_end_effector_matrix_m.shape != (4, 4)
                or not np.all(np.isfinite(self._control_to_end_effector_matrix_m))
            ):
                raise ValueError("rmpflow_control_to_grasp_matrix_m_invalid")
            configured_finger_indices = tuple(
                getattr(online_fluid, "finger_joint_indices", ())
            )
            if (
                len(configured_finger_indices) != 2
                or len(set(configured_finger_indices)) != 2
                or any(type(index) is not int for index in configured_finger_indices)
                or any(index < 0 for index in configured_finger_indices)
            ):
                raise ValueError("finger_joint_indices_invalid")
            self._finger_joint_indices = configured_finger_indices
            configured_approach_direction = getattr(
                online_fluid, "expert_pick_approach_direction_world", None
            )
            if configured_approach_direction is not None:
                self._contact_pick_approach_direction = self._normalized_vector(
                    configured_approach_direction,
                    shape=(3,),
                    error="expert_pick_approach_direction_world_invalid",
                )

            contact_scalars = {
                "_contact_pick_position_threshold_m": (
                    "expert_pick_position_threshold_m",
                    self._contact_pick_position_threshold_m,
                ),
                "_contact_pick_pregrasp_distance_m": (
                    "expert_pick_pregrasp_distance_m",
                    self._contact_pick_pregrasp_distance_m,
                ),
                "_contact_pick_insert_distance_m": (
                    "expert_pick_insert_distance_m",
                    self._contact_pick_insert_distance_m,
                ),
                "_contact_pick_approach_speed_m_s": (
                    "expert_pick_approach_speed_m_s",
                    self._contact_pick_approach_speed_m_s,
                ),
                "_contact_pick_close_speed_m_s": (
                    "expert_pick_close_speed_m_s",
                    self._contact_pick_close_speed_m_s,
                ),
                "_contact_pick_lift_speed_m_s": (
                    "expert_pick_lift_speed_m_s",
                    self._contact_pick_lift_speed_m_s,
                ),
                "_contact_pick_orientation_threshold_degrees": (
                    "expert_pick_orientation_threshold_degrees",
                    self._contact_pick_orientation_threshold_degrees,
                ),
            }
            for attribute, (config_name, default) in contact_scalars.items():
                value = float(getattr(online_fluid, config_name, default))
                if not np.isfinite(value) or value <= 0.0:
                    raise ValueError(f"{config_name}_invalid")
                setattr(self, attribute, value)
            if self._contact_pick_orientation_threshold_degrees > 180.0:
                raise ValueError(
                    "expert_pick_orientation_threshold_degrees_invalid"
                )
            self._contact_pick_open_position_m = float(
                getattr(
                    online_fluid,
                    "expert_pick_open_position_m",
                    self._contact_pick_open_position_m,
                )
            )
            if (
                not np.isfinite(self._contact_pick_open_position_m)
                or not 0.0 < self._contact_pick_open_position_m <= 0.04
            ):
                raise ValueError("expert_pick_open_position_m_invalid")
            self._contact_pick_open_position_tolerance_m = float(
                getattr(
                    online_fluid,
                    "expert_pick_open_position_tolerance_m",
                    self._contact_pick_open_position_tolerance_m,
                )
            )
            if (
                not np.isfinite(
                    self._contact_pick_open_position_tolerance_m
                )
                or not 0.0
                < self._contact_pick_open_position_tolerance_m
                <= self._contact_pick_open_position_m
            ):
                raise ValueError(
                    "expert_pick_open_position_tolerance_m_invalid"
                )
            if (
                self._contact_pick_insert_distance_m
                > self._contact_pick_pregrasp_distance_m
            ):
                raise ValueError("expert_pick_insert_distance_exceeds_pregrasp")
            self._contact_pick_contact_timeout_s = float(
                getattr(
                    online_fluid,
                    "grasp_contact_timeout_s",
                    self._contact_pick_contact_timeout_s,
                )
            )
            if (
                not np.isfinite(self._contact_pick_contact_timeout_s)
                or self._contact_pick_contact_timeout_s <= 0.0
            ):
                raise ValueError("grasp_contact_timeout_s_invalid")
            self._contact_pick_source_translation_limit_m = float(
                getattr(
                    online_fluid,
                    "grasp_preclose_source_translation_limit_m",
                    self._contact_pick_source_translation_limit_m,
                )
            )
            self._contact_pick_source_tilt_limit_degrees = float(
                getattr(
                    online_fluid,
                    "grasp_preclose_source_tilt_limit_degrees",
                    self._contact_pick_source_tilt_limit_degrees,
                )
            )
            if (
                not np.isfinite(self._contact_pick_source_translation_limit_m)
                or self._contact_pick_source_translation_limit_m <= 0.0
            ):
                raise ValueError(
                    "grasp_preclose_source_translation_limit_m_invalid"
                )
            if (
                not np.isfinite(self._contact_pick_source_tilt_limit_degrees)
                or self._contact_pick_source_tilt_limit_degrees <= 0.0
            ):
                raise ValueError(
                    "grasp_preclose_source_tilt_limit_degrees_invalid"
                )

        configured_offsets = getattr(
            online_fluid, "expert_pour_height_offsets_m", None
        )
        if configured_offsets is not None:
            self._expert_pour_height_offsets = tuple(
                float(value) for value in configured_offsets
            )

        configured_target_offset = getattr(
            online_fluid, "expert_pour_target_offset_m", None
        )
        if configured_target_offset is not None:
            offset = np.asarray(configured_target_offset, dtype=np.float64)
            if offset.shape != (3,) or not np.all(np.isfinite(offset)):
                raise ValueError(
                    "target_position_offset_must_be_three_finite_values"
                )
            self._expert_pour_target_offset = tuple(
                float(value) for value in offset
            )

        self._expert_pour_entry_orientation_required = bool(
            getattr(
                online_fluid,
                "expert_pour_entry_orientation_required",
                False,
            )
        )
        self._expert_pour_entry_orientation_threshold_degrees = float(
            getattr(
                online_fluid,
                "expert_pour_entry_orientation_threshold_degrees",
                5.0,
            )
        )

        configured_target_orientation = getattr(
            online_fluid, "expert_pour_target_orientation_wxyz", None
        )
        if configured_target_orientation is not None:
            self._expert_pour_target_orientation_wxyz = self._normalized_vector(
                configured_target_orientation,
                shape=(4,),
                error="expert_pour_target_orientation_wxyz_invalid",
            )
        elif self._expert_pour_entry_orientation_required:
            raise ValueError("expert_pour_target_orientation_wxyz_required")

        configured_pick_offset = getattr(
            online_fluid, "expert_pick_gripper_offset_object_m", None
        )
        if self._native_expert_profile and configured_pick_offset is not None:
            raise ValueError("native_expert_pick_position_override_forbidden")
        if configured_pick_offset is not None:
            pick_offset = np.asarray(configured_pick_offset, dtype=np.float64)
            if pick_offset.shape != (3,) or not np.all(np.isfinite(pick_offset)):
                raise ValueError("expert_pick_gripper_offset_object_m_invalid")
            self._expert_pick_gripper_offset_object = pick_offset.copy()

        configured_pick_orientation = getattr(
            online_fluid, "expert_pick_target_orientation_wxyz", None
        )
        if self._native_expert_profile and configured_pick_orientation is not None:
            raise ValueError("native_expert_pick_orientation_override_forbidden")
        if configured_pick_orientation is not None:
            self._expert_pick_target_orientation_wxyz = self._normalized_vector(
                configured_pick_orientation,
                shape=(4,),
                error="expert_pick_target_orientation_wxyz_invalid",
            )
            
    def _init_collect_mode(self, cfg, robot):
        super()._init_collect_mode(cfg, robot)
        """Initialize controller for data collection mode."""
        fixed_height_offsets = (
            self._expert_pour_height_offsets
            if self._online_fluid_enabled
            else None
        )
        target_position_offset = (
            self._expert_pour_target_offset
            if self._online_fluid_enabled
            else None
        )

        self.pick_controller = self._create_pick_controller()

        self.pour_controller = PourController(
            name="pour_controller",
            cspace_controller=self.rmp_controller,
            events_dt=[
                0.05, 0.05, 0.05, 0.05, 0.05, 0.05,
            ] if self._native_expert_profile
            else [
                0.006, 0.002, 0.009, 0.01, 0.009, 0.01,
            ],
            fixed_height_offsets=fixed_height_offsets,
            target_position_offset=target_position_offset,
            require_entry_orientation=(
                self._expert_pour_entry_orientation_required
            ),
            entry_orientation_threshold_degrees=(
                self._expert_pour_entry_orientation_threshold_degrees
            ),
            control_to_end_effector_matrix_m=(
                self._control_to_end_effector_matrix_m
            ),
            direct_control_frame_targets=(
                not self._online_fluid_enabled or self._native_expert_profile
            ),
        )
        self.active_controller = self.pick_controller

    def _init_infer_mode(self, cfg, robot=None):
        super()._init_infer_mode(cfg, robot)
        self.pick_controller = self._create_pick_controller()

    def _create_pick_controller(self):
        if self._use_contact_pick_controller:
            return ContactPickController(
                name="contact_pick_controller",
                cspace_controller=self.rmp_controller,
                control_dt=self.control_dt,
                position_threshold=self._contact_pick_position_threshold_m,
                open_position=self._contact_pick_open_position_m,
                open_position_tolerance=(
                    self._contact_pick_open_position_tolerance_m
                ),
                pregrasp_distance=self._contact_pick_pregrasp_distance_m,
                insert_distance=self._contact_pick_insert_distance_m,
                approach_speed=self._contact_pick_approach_speed_m_s,
                close_speed=self._contact_pick_close_speed_m_s,
                lift_speed=self._contact_pick_lift_speed_m_s,
                orientation_threshold_degrees=(
                    self._contact_pick_orientation_threshold_degrees
                ),
                contact_timeout=self._contact_pick_contact_timeout_s,
                control_to_end_effector_matrix_m=(
                    self._control_to_end_effector_matrix_m
                ),
                end_effector_frame=self._end_effector_target_frame,
                control_frame=self._rmpflow_control_frame,
                finger_joint_indices=self._finger_joint_indices,
                source_translation_limit=(
                    self._contact_pick_source_translation_limit_m
                ),
                source_tilt_limit_degrees=(
                    self._contact_pick_source_tilt_limit_degrees
                ),
                terminate_after_contact_settle=(
                    self._contact_acquisition_probe
                ),
                require_external_phase_certificates=(
                    self._contact_acquisition_probe
                ),
            )
        pick_events_dt = (
            [0.002, 0.002, 0.005, 0.05, 0.05, 0.01, 0.05]
            if self._native_expert_profile
            else [0.002, 0.002, 0.005, 0.02, 0.05, 0.01, 0.02]
        )
        return PickController(
            name="pick_controller",
            cspace_controller=self.rmp_controller,
            events_dt=pick_events_dt,
        )

    def reset(self):
        if (
            self.mode == "collect"
            and self._online_fluid_enabled
            and self._collection_episode_terminal
            and not self._collection_episode_finalized
        ):
            raise RuntimeError("online_fluid_collection_requires_finalization")
        super().reset()
        self.current_phase = Phase.PICKING
        self.initial_position = None
        self.initial_size = None
        self.initial_quaternion = None
        self.pour_timer = 0
        self.pour_complete = False
        self.return_complete = False
        self.return_timer = 0
        self.last_error_info = None
        self._pour_forward_invocation_count = 0
        self._collection_episode_terminal = False
        self._collection_episode_finalized = False
        self.pick_controller.reset()
        if self.mode == "collect":
            self.active_controller = self.pick_controller
            self.pour_controller.reset()
        else:
            self.inference_engine.reset()

    def _native_contact_acquisition_probe_active(self) -> bool:
        return bool(
            self.mode == "collect"
            and self._execution_mode == "contact_acquisition_probe_v1"
            and self._native_expert_profile
            and self.current_phase == Phase.PICKING
        )

    def _native_contact_acquisition_probe_complete(self) -> bool:
        if not self._native_contact_acquisition_probe_active():
            return False
        grasp_record = self.state.get("online_fluid_grasp")
        return bool(
            isinstance(grasp_record, Mapping)
            and self.online_fluid_grasp_contact_requested()
            and grasp_record.get("probe_qualified_now") is True
            and grasp_record.get("close_command_observed") is True
            and grasp_record.get("lift_command_observed") is False
            and not self.online_fluid_grasp_lift_requested()
        )

    def _native_contact_acquisition_probe_lift_failure(self, state) -> bool:
        if not self._native_contact_acquisition_probe_active():
            return False
        grasp_record = state.get("online_fluid_grasp")
        monitor_lift_observed = bool(
            isinstance(grasp_record, Mapping)
            and grasp_record.get("lift_command_observed", False)
        )
        return bool(
            monitor_lift_observed
            or self.online_fluid_grasp_lift_requested()
            or getattr(self.pick_controller, "_last_emitted_event", None) == 5
        )

    def _check_phase_success(self):
        """Check if current phase is successful."""
        object_pos = self.state['object_position']
        self.last_error_info = None 
        
        if self.initial_position is None:
            raise ValueError("initial_position not set")

        if self.current_phase == Phase.PICKING:
            if self._native_contact_acquisition_probe_active():
                return self._native_contact_acquisition_probe_complete()
            if self._contact_grasp_required:
                if self._contact_acquisition_probe:
                    required_height = self.initial_position[2]
                    height_reached = True
                else:
                    required_lift = 0.8 * self._expert_pick_lift_height_m
                    required_height = self.initial_position[2] + required_lift
                    gripper_z = self.state.get("gripper_position", object_pos)[2]
                    height_reached = bool(gripper_z >= required_height)
            else:
                required_height = self.initial_position[2] + 0.12
                height_reached = bool(object_pos[2] > required_height)
            grasp_qualified = True
            controller_done = True
            grasp_failure_reason = None
            if self._contact_grasp_required:
                grasp_record = self.state.get("online_fluid_grasp")
                qualification_field = (
                    "probe_qualified_now"
                    if self._contact_acquisition_probe
                    else "qualified"
                )
                grasp_qualified = bool(
                    isinstance(grasp_record, Mapping)
                    and grasp_record.get(qualification_field, False)
                )
                controller_done = bool(self.pick_controller.is_done())
                if isinstance(grasp_record, Mapping):
                    grasp_failure_reason = grasp_record.get("failure_reason")
                if grasp_failure_reason is None:
                    grasp_failure_reason = getattr(
                        self.pick_controller,
                        "terminal_failure_reason",
                        None,
                    )
                if (
                    self._native_expert_profile
                    and not self._contact_acquisition_probe
                ):
                    controller_done = self.pick_controller.is_done()
                    if controller_done:
                        grasp_qualified = True
            success = height_reached and grasp_qualified and controller_done
            if not success:
                self.last_error_info = {
                    'phase': 'PICKING',
                    'current_height': object_pos[2],
                    'required_height': required_height,
                    'height_diff': object_pos[2] - required_height,
                    'grasp_qualified': grasp_qualified,
                    'pick_controller_done': controller_done,
                    'grasp_failure_reason': grasp_failure_reason,
                }
            return success
            
        elif self.current_phase == Phase.POURING:
            if (
                self._native_expert_profile
                and not self._contact_acquisition_probe
            ):
                return bool(self.pour_controller.is_done())

            if self.initial_quaternion is None:
                self.initial_quaternion = self.state['object_quaternion']
                self.last_error_info = {
                    'phase': 'POURING',
                    'error': 'Initial quaternion not set yet'
                }
                return False
                
            current_quat = self.state['object_quaternion']
            
            # First check if we're close enough to target for pouring
            expert_target_position = np.asarray(
                self.state['target_position'], dtype=np.float64
            ) + np.asarray(self._expert_pour_target_offset, dtype=np.float64)
            xy_dist = np.linalg.norm(object_pos[:2] - expert_target_position[:2])
            pour_threshold = self.task_utils.get_pour_threshold(self.state['object_name'], self.state['object_size']) + 0.05
            
            if xy_dist > pour_threshold:
                self.last_error_info = {
                    'phase': 'POURING',
                    'current_distance': xy_dist,
                    'required_distance': pour_threshold,
                    'distance_diff': xy_dist - pour_threshold
                }
                return False
            
            if not self.pour_complete:
                # print(self.initial_quaternion, current_quat)
                self.pour_complete = self.task_utils.check_rotation_angle(
                    self.initial_quaternion, 
                    current_quat,
                    threshold_degrees=50
                )
                if not self.pour_complete:
                    self.last_error_info = {
                        'phase': 'POURING',
                        'error': 'Pour rotation not complete yet',
                        'pour_complete': self.pour_complete
                    }
                return False
                
            # After pour complete, check if returned to original orientation
            if not self.return_complete:
                rotation_diff = self.task_utils.check_rotation_angle(
                    self.initial_quaternion,
                    current_quat,
                    threshold_degrees=30  # smaller threshold for return position
                )
                if not rotation_diff:
                    self.return_complete = True
                    self.return_timer = 0
                else:
                    self.last_error_info = {
                        'phase': 'POURING',
                        'error': 'Return rotation not complete yet',
                        'return_complete': self.return_complete
                    }
                return False
                
            # Wait for 2 seconds in return position
            if self.return_complete and object_pos[2] > self.initial_position[2] + 0.05:
                self.return_timer += 0.012
                pour_controller_done = bool(
                    not self._native_expert_profile
                    or self.pour_controller.is_done()
                )
                success = self.return_timer >= 1.0 and pour_controller_done
                if not success:
                    self.last_error_info = {
                        'phase': 'POURING',
                        'error': 'Waiting for return timer',
                        'return_timer': self.return_timer,
                        'required_time': 1.0,
                        'pour_controller_done': pour_controller_done,
                    }
                return success
            else:
                self.last_error_info = {
                    'phase': 'POURING',
                    'error': 'Object not in correct position for return timer',
                    'current_height': object_pos[2],
                    'required_height': self.initial_position[2] + 0.05,
                    'return_complete': self.return_complete
                }
                return False
        
        return False
    def step(self, state):
        """Execute one step of control.
        
        Args:
            state: Current state dictionary containing sensor data and robot state
            
        Returns:
            Tuple containing action, done flag, and success flag
        """
        self.state = state
        if self.initial_position is None:
            if self._contact_grasp_required:
                self.initial_position = np.asarray(
                    self.state['object_position'], dtype=np.float64
                ).copy()
            else:
                self.initial_position = self.state['object_position']
        if self.initial_size is None:
            self.initial_size = self.state['object_size']
        if self.mode == "collect":
            return self._step_collect(state)
        else:
            return self._step_infer(state)

    def _pick_orientation(self, *, default_euler_degrees):
        pick_orientation = R.from_euler(
            'xyz', np.radians(default_euler_degrees)
        ).as_quat()
        if self._expert_pick_target_orientation_wxyz is not None:
            pick_orientation = self._expert_pick_target_orientation_wxyz.copy()
        return pick_orientation

    def _pick_target(self, state, *, default_euler_degrees):
        picking_position = np.asarray(
            state['object_position'], dtype=np.float64
        ).copy()
        pick_orientation = self._pick_orientation(
            default_euler_degrees=default_euler_degrees
        )
        if not self._online_fluid_enabled:
            return picking_position, pick_orientation

        object_quaternion = np.asarray(
            state['object_quaternion'], dtype=np.float64
        )
        if (
            object_quaternion.shape != (4,)
            or not np.all(np.isfinite(object_quaternion))
            or float(np.linalg.norm(object_quaternion)) <= 1.0e-12
        ):
            raise ValueError("online_fluid_object_quaternion_invalid")
        object_quaternion = object_quaternion / np.linalg.norm(object_quaternion)
        picking_position += R.from_quat(object_quaternion).apply(
            self._expert_pick_gripper_offset_object
        )
        return picking_position, pick_orientation

    def _contact_pick_action(self, state, pick_orientation):
        if self._expert_pick_target_orientation_wxyz is None:
            pick_orientation = pick_orientation[[3, 0, 1, 2]]
        grasp_record = state.get("online_fluid_grasp")
        if not isinstance(grasp_record, Mapping):
            grasp_record = {}
        qualification_field = (
            "probe_qualified_now"
            if self._contact_acquisition_probe
            else "qualified"
        )
        return self.pick_controller.forward(
            source_position=state['object_position'],
            source_orientation_xyzw=state['object_quaternion'],
            current_joint_positions=state['joint_positions'],
            gripper_position=state['gripper_position'],
            end_effector_orientation=pick_orientation,
            current_end_effector_orientation=(
                self.rmp_controller.get_end_effector_orientation_wxyz()
            ),
            approach_direction=self._contact_pick_approach_direction.copy(),
            grasp_offset=self._expert_pick_gripper_offset_object.copy(),
            lift_height=self._expert_pick_lift_height_m,
            gripper_distance=self._grasp_finger_joint_target_m,
            contact_qualified=bool(
                grasp_record.get(qualification_field, False)
            ),
            contact_failure_reason=grasp_record.get("failure_reason"),
            phase_certificates=grasp_record.get(
                "controlled_phase_certificates"
            ),
        )

    def latch_intended_precontact(self, evidence: Mapping[str, Any]) -> bool:
        if not self._online_fluid_enabled or not self._use_contact_pick_controller:
            raise RuntimeError("controlled_precontact_controller_unavailable")
        latch = getattr(self.pick_controller, "latch_intended_precontact", None)
        if not callable(latch):
            raise RuntimeError("controlled_precontact_latch_interface_missing")
        result = latch(evidence)
        if type(result) is not bool:
            raise TypeError("controlled_precontact_latch_result_bool_required")
        return result

    def controlled_contact_action_context(self) -> dict[str, Any]:
        if (
            not self._online_fluid_enabled
            or not self._use_contact_pick_controller
            or not self._contact_acquisition_probe
        ):
            raise RuntimeError("controlled_contact_action_context_unavailable")
        evidence = self.pick_controller.control_evidence()
        if not isinstance(evidence, Mapping):
            raise TypeError("controlled_contact_evidence_mapping_required")
        phase = evidence.get("last_emitted_phase")
        controller_phase = evidence.get("phase")
        semantic_kind = evidence.get("last_emitted_semantic_action_kind")
        control_index = evidence.get("last_emitted_control_index")
        target_token = evidence.get("last_emitted_target_token")
        if not isinstance(phase, str) or not phase:
            raise RuntimeError("controlled_contact_emitted_phase_missing")
        if not isinstance(controller_phase, str) or not controller_phase:
            raise RuntimeError("controlled_contact_controller_phase_missing")
        if not isinstance(semantic_kind, str) or not semantic_kind:
            raise RuntimeError("controlled_contact_semantic_action_missing")
        if type(control_index) is not int or control_index < 0:
            raise RuntimeError("controlled_contact_control_index_missing")
        if not isinstance(target_token, Mapping):
            raise RuntimeError("controlled_contact_target_token_missing")
        return {
            "phase": phase,
            "controller_phase": controller_phase,
            "semantic_action_kind": semantic_kind,
            "control_index": control_index,
            "target_token": copy.deepcopy(dict(target_token)),
            "terminal_latched": bool(
                evidence.get("done") is True
                or evidence.get("terminal_failure_reason") is not None
            ),
            "finger_joint_indices": list(self._finger_joint_indices),
        }

    def _step_collect(self, state):
        """Execute collection mode step."""
        monitor_failure = self._online_fluid_monitor_failure_reason(state)
        if monitor_failure is not None:
            return self.abort_online_fluid_episode(monitor_failure)
        if self._native_contact_acquisition_probe_lift_failure(state):
            return self.abort_online_fluid_episode(
                "contact_acquisition_probe_lift_observed"
            )
        success = self._check_phase_success()
        if success:
            if self.current_phase == Phase.PICKING:
                if self._contact_acquisition_probe:
                    print("Contact acquisition probe success!")
                    self._collection_episode_terminal = True
                    self._last_success = True
                    self.current_phase = Phase.FINISHED
                    return None, True, True
                print("Pick task success! Switching to pour...")
                self.current_phase = Phase.POURING
                self.active_controller = self.pour_controller
                return None, False, False
            elif self.current_phase == Phase.POURING:
                print("Pour task success!")
                if self._online_fluid_enabled:
                    self._collection_episode_terminal = True
                else:
                    self.data_collector.write_cached_data(
                        state['joint_positions'][:-1]
                    )
                self._last_success = True
                self.current_phase = Phase.FINISHED
                return None, True, True
        
        if self.current_phase == Phase.FINISHED:
            self.reset_needed = True
            return None, True, self._last_success

        if not self.active_controller.is_done():
            action = None
            if self.current_phase == Phase.PICKING:
                if self._native_lift_would_precede_acquisition(state):
                    return self.abort_online_fluid_episode(
                        "lift_started_before_contact_acquisition"
                    )
                if self._use_contact_pick_controller:
                    pick_orientation = self._pick_orientation(
                        default_euler_degrees=[0, 90, 30]
                    )
                    action = self._contact_pick_action(
                        state,
                        pick_orientation,
                    )
                    failure_reason = self.pick_controller.terminal_failure_reason
                    if failure_reason is not None:
                        return self.abort_online_fluid_episode(failure_reason)
                    if (
                        self._contact_acquisition_probe
                        and self.pick_controller.is_done()
                    ):
                        self._collection_episode_terminal = True
                        self._last_success = True
                        self.current_phase = Phase.FINISHED
                        return None, True, True
                else:
                    picking_position, pick_orientation = self._pick_target(
                        state,
                        default_euler_degrees=[0, 90, 30],
                    )
                    action = self.pick_controller.forward(
                        picking_position=picking_position,
                        current_joint_positions=state['joint_positions'],
                        object_size=state['object_size'],
                        object_name=state['object_name'],
                        gripper_control=self.gripper_control,
                        gripper_position=state['gripper_position'],
                        end_effector_orientation=pick_orientation,
                        pre_offset_x=0.05,
                        pre_offset_z=0.05,
                        after_offset_z=0.5,
                    )
            else:
                pour_kwargs = {
                    "articulation_controller": self.robot.get_articulation_controller(),
                    "source_size": self.initial_size,
                    "target_position": state['target_position'],
                    "current_joint_velocities": self.robot.get_joint_velocities(),
                    "pour_speed": self._expert_pour_speed_rad_s,
                    "source_name": state['object_name'],
                    "gripper_position": state['gripper_position'],
                }
                if not self._online_fluid_enabled:
                    pour_kwargs["source_position"] = None
                elif not self._native_expert_profile:
                    pour_kwargs["source_position"] = state['object_position']
                    pour_kwargs["target_end_effector_orientation"] = (
                        self._expert_pour_target_orientation_wxyz
                    )
                    if self._expert_pour_entry_orientation_required:
                        pour_kwargs["current_end_effector_orientation"] = (
                            self.rmp_controller.get_end_effector_orientation_wxyz()
                        )
                self._pour_forward_invocation_count += 1
                action = self.pour_controller.forward(
                    **pour_kwargs,
                )
                
                if 'camera_data' in state:
                    self.data_collector.cache_step(
                        camera_images=state['camera_data'],
                        joint_angles=state['joint_positions'][:-1],
                        language_instruction=self.get_language_instruction()
                    )
            
            return action, False, False

        print(f"{self.current_phase.value} task failed!")
        if self.last_error_info is not None:
            print(f"Phase failure details: {self.last_error_info}")
        if self._online_fluid_enabled:
            self._collection_episode_terminal = True
        else:
            self.data_collector.clear_cache()
        if self._contact_grasp_required:
            failure_reason = getattr(
                self.pick_controller, "terminal_failure_reason", None
            )
            if failure_reason is not None:
                self._last_failure_reason = failure_reason
        self._last_success = False
        self.current_phase = Phase.FINISHED
        return None, True, False

    def finalize_collection_episode(
        self,
        *,
        accepted: bool,
        final_joint_positions: np.ndarray,
        evaluation: Mapping[str, Any],
    ) -> None:
        if not self._online_fluid_enabled or self.mode != "collect":
            raise RuntimeError("online_fluid_collection_not_enabled")
        if not self._collection_episode_terminal:
            raise RuntimeError("collection_episode_not_terminal")
        if self._collection_episode_finalized:
            raise RuntimeError("collection_episode_already_finalized")
        if type(accepted) is not bool:
            raise TypeError("collection_episode_accepted_bool_required")
        if not isinstance(evaluation, Mapping):
            raise TypeError("collection_episode_evaluation_mapping_required")

        if accepted:
            payload = dict(evaluation)
            self.data_collector.set_task_properties(
                {"online_fluid_evaluation": payload}
            )
            self.data_collector.write_cached_data(
                np.asarray(final_joint_positions).copy()
            )
        else:
            self.data_collector.clear_cache()
        self._collection_episode_finalized = True

    def online_fluid_control_evidence(self) -> dict[str, Any]:
        if not self._online_fluid_enabled:
            raise RuntimeError("online_fluid_collection_not_enabled")
        target_orientation = self._expert_pour_target_orientation_wxyz
        pick_orientation = self._expert_pick_target_orientation_wxyz
        pour_controller = getattr(self, "pour_controller", None)
        contact_pick_evidence = None
        native_pick_evidence = None
        if self._use_contact_pick_controller:
            evidence = getattr(self.pick_controller, "control_evidence", None)
            if callable(evidence):
                contact_pick_evidence = evidence()
        elif self._native_expert_profile:
            evidence = getattr(self.pick_controller, "control_evidence", None)
            if callable(evidence):
                native_pick_evidence = evidence()
        return {
            "mode": str(self.mode),
            "pick_gripper_offset_object_m": (
                self._expert_pick_gripper_offset_object.tolist()
            ),
            "source_ownership": self._source_ownership,
            "expert_control_profile": self._expert_control_profile,
            "execution_mode": self._execution_mode,
            "contact_acquisition_probe": self._contact_acquisition_probe,
            "pour_forward_invocation_count": (
                self._pour_forward_invocation_count
            ),
            "contact_grasp_required": self._contact_grasp_required,
            "pick_lift_height_m": self._expert_pick_lift_height_m,
            "pour_speed_rad_s": self._expert_pour_speed_rad_s,
            "control_dt_s": self.control_dt,
            "control_frequency_hz": 1.0 / self.control_dt,
            "end_effector_target_frame": self._end_effector_target_frame,
            "rmpflow_control_frame": self._rmpflow_control_frame,
            "rmpflow_control_to_end_effector_matrix_m": (
                self._control_to_end_effector_matrix_m.tolist()
            ),
            "finger_joint_indices": list(self._finger_joint_indices),
            "contact_pick": contact_pick_evidence,
            "native_pick": native_pick_evidence,
            "contact_pick_approach_direction_world": (
                self._contact_pick_approach_direction.tolist()
            ),
            "pick_target_orientation_wxyz": (
                None
                if pick_orientation is None
                else pick_orientation.tolist()
            ),
            "target_end_effector_orientation_wxyz": (
                None
                if target_orientation is None
                else target_orientation.tolist()
            ),
            "pour_entry_orientation": (
                None
                if pour_controller is None
                else pour_controller.pour_entry_orientation_evidence
            ),
        }

    def online_fluid_grasp_attachment_requested(self) -> bool:
        if not self._online_fluid_enabled:
            return False
        if self._contact_grasp_required:
            return False
        event = getattr(self.pick_controller, "_event", -1)
        return isinstance(event, int) and event >= 4

    def online_fluid_grasp_contact_requested(self) -> bool:
        if not self._online_fluid_enabled or not self._contact_grasp_required:
            return False
        requested = getattr(self.pick_controller, "grasp_contact_requested", None)
        if not callable(requested):
            raise RuntimeError("pick_controller_contact_request_interface_missing")
        result = requested()
        if type(result) is not bool:
            raise TypeError("grasp_contact_requested_must_return_bool")
        return result

    def online_fluid_grasp_lift_requested(self) -> bool:
        if not self._online_fluid_enabled or not self._contact_grasp_required:
            return False
        requested = getattr(self.pick_controller, "lift_command_emitted", None)
        if not callable(requested):
            return False
        result = requested()
        if type(result) is not bool:
            raise TypeError("lift_command_emitted_must_return_bool")
        return result

    def online_fluid_rotation_handoff_requested(self) -> bool:
        if (
            not self._online_fluid_enabled
            or self.current_phase != Phase.POURING
        ):
            return False
        if self.mode == "infer":
            return True
        pour_controller = getattr(self, "pour_controller", None)
        return getattr(pour_controller, "_last_emitted_event", None) == 2

    def abort_online_fluid_episode(self, reason: str):
        if not self._online_fluid_enabled:
            raise RuntimeError("online_fluid_not_enabled")
        if not isinstance(reason, str) or not reason:
            raise ValueError("online_fluid_abort_reason_required")
        if self.mode == "collect":
            self._collection_episode_terminal = True
        self._last_success = False
        self._last_failure_reason = reason
        self.current_phase = Phase.FINISHED
        return None, True, False

    def abort_online_fluid_collection_episode(self, reason: str):
        if not self._online_fluid_enabled or self.mode != "collect":
            raise RuntimeError("online_fluid_collection_not_enabled")
        return self.abort_online_fluid_episode(reason)

    def _online_fluid_monitor_failure_reason(self, state) -> Optional[str]:
        if not self._contact_grasp_required:
            return None
        grasp_record = state.get("online_fluid_grasp")
        if not isinstance(grasp_record, Mapping):
            return None
        reason = grasp_record.get("failure_reason")
        if reason is None:
            return None
        if not isinstance(reason, str) or not reason:
            raise ValueError("online_fluid_grasp_failure_reason_invalid")
        return reason

    def _native_lift_would_precede_acquisition(self, state) -> bool:
        if not self._native_expert_profile or self.current_phase != Phase.PICKING:
            return False
        pending = getattr(self.pick_controller, "lift_is_next_action", None)
        if not callable(pending) or not pending():
            return False
        if not self._contact_acquisition_probe:
            return False
        grasp_record = state.get("online_fluid_grasp")
        return not bool(
            isinstance(grasp_record, Mapping)
            and grasp_record.get("qualified", False)
        )

    def _step_infer(self, state):
        """Execute inference mode step."""
        if self.current_phase == Phase.FINISHED:
            self.reset_needed = True
            return None, True, self._last_success

        monitor_failure = self._online_fluid_monitor_failure_reason(state)
        if monitor_failure is not None:
            return self.abort_online_fluid_episode(monitor_failure)

        contact_failure_reason = getattr(
            self.pick_controller, "terminal_failure_reason", None
        )
        if self._contact_grasp_required and contact_failure_reason is not None:
            self._last_failure_reason = contact_failure_reason
            self._last_success = False
            self.current_phase = Phase.FINISHED
            return None, True, False

        if not self.pick_controller.is_done():
            if self._native_lift_would_precede_acquisition(state):
                return self.abort_online_fluid_episode(
                    "lift_started_before_contact_acquisition"
                )
            if self._use_contact_pick_controller:
                pick_orientation = self._pick_orientation(
                    default_euler_degrees=[0, 90, 15]
                )
                action = self._contact_pick_action(
                    state,
                    pick_orientation,
                )
                failure_reason = self.pick_controller.terminal_failure_reason
                if failure_reason is not None:
                    return self.abort_online_fluid_episode(failure_reason)
            else:
                picking_position, pick_orientation = self._pick_target(
                    state,
                    default_euler_degrees=[0, 90, 15],
                )
                action = self.pick_controller.forward(
                    picking_position=picking_position,
                    current_joint_positions=state['joint_positions'],
                    object_size=state['object_size'],
                    object_name=state['object_name'],
                    gripper_control=self.gripper_control,
                    gripper_position=state['gripper_position'],
                    end_effector_orientation=pick_orientation,
                )
            
        else:
            state['language_instruction'] = self.get_language_instruction()

            action = self.inference_engine.step_inference(state)
        success = self._check_phase_success()
        if success and self.current_phase == Phase.PICKING:
            print("Pick task success! Switching to pour...")
            self.current_phase = Phase.POURING
        elif success and self.current_phase == Phase.POURING:
            print("Pour task success!")
            self._last_success = True
            self.current_phase = Phase.FINISHED
            return None, True, True
               
        return action, False, False

    def get_language_instruction(self) -> Optional[str]:
        object_name = re.sub(r'\d+', '', self.state['object_name']).replace('_', ' ').lower()
        self.language_instruction = f"Pick up the {object_name} from the table and pour it into the target".replace("  ", " ")
        return self.language_instruction
