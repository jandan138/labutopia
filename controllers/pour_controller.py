import re
from collections.abc import Mapping
from typing import Any, Optional
from scipy.spatial.transform import Rotation as R
import numpy as np
from enum import Enum
from utils.task_utils import TaskUtils

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
        self._configure_online_fluid(online_fluid)
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
        if configured_pick_offset is not None:
            pick_offset = np.asarray(configured_pick_offset, dtype=np.float64)
            if pick_offset.shape != (3,) or not np.all(np.isfinite(pick_offset)):
                raise ValueError("expert_pick_gripper_offset_object_m_invalid")
            self._expert_pick_gripper_offset_object = pick_offset.copy()

        configured_pick_orientation = getattr(
            online_fluid, "expert_pick_target_orientation_wxyz", None
        )
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

        self.pick_controller = PickController(
            name="pick_controller",
            cspace_controller=self.rmp_controller,
            events_dt=[0.002, 0.002, 0.005, 0.02, 0.05, 0.01, 0.02]
        )

        self.pour_controller = PourController(
            name="pour_controller",
            cspace_controller=self.rmp_controller,
            events_dt=[0.006, 0.002, 0.009, 0.01, 0.009, 0.01],
            fixed_height_offsets=fixed_height_offsets,
            target_position_offset=target_position_offset,
            require_entry_orientation=(
                self._expert_pour_entry_orientation_required
            ),
            entry_orientation_threshold_degrees=(
                self._expert_pour_entry_orientation_threshold_degrees
            ),
        )
        self.active_controller = self.pick_controller

    def _init_infer_mode(self, cfg, robot=None):
        super()._init_infer_mode(cfg, robot)
        self.pick_controller = PickController(
            name="pick_controller",
            cspace_controller=self.rmp_controller,
            events_dt=[0.002, 0.002, 0.005, 0.02, 0.05, 0.01, 0.02]
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
        self._collection_episode_terminal = False
        self._collection_episode_finalized = False
        self.pick_controller.reset()
        if self.mode == "collect":
            self.active_controller = self.pick_controller
            self.pour_controller.reset()
        else:
            self.inference_engine.reset()

    def _check_phase_success(self):
        """Check if current phase is successful."""
        object_pos = self.state['object_position']
        self.last_error_info = None 
        
        if self.initial_position is None:
            raise ValueError("initial_position not set")

        if self.current_phase == Phase.PICKING:
            required_height = self.initial_position[2] + 0.12
            success = object_pos[2] > required_height
            if not success:
                self.last_error_info = {
                    'phase': 'PICKING',
                    'current_height': object_pos[2],
                    'required_height': required_height,
                    'height_diff': object_pos[2] - required_height
                }
            return success
            
        elif self.current_phase == Phase.POURING:
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
                success = self.return_timer >= 1.0
                if not success:
                    self.last_error_info = {
                        'phase': 'POURING',
                        'error': 'Waiting for return timer',
                        'return_timer': self.return_timer,
                        'required_time': 1.0
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
            self.initial_position = self.state['object_position']
        if self.initial_size is None:
            self.initial_size = self.state['object_size']
        if self.mode == "collect":
            return self._step_collect(state)
        else:
            return self._step_infer(state)

    def _pick_target(self, state, *, default_euler_degrees):
        picking_position = np.asarray(
            state['object_position'], dtype=np.float64
        ).copy()
        pick_orientation = R.from_euler(
            'xyz', np.radians(default_euler_degrees)
        ).as_quat()
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
        if self._expert_pick_target_orientation_wxyz is not None:
            pick_orientation = self._expert_pick_target_orientation_wxyz.copy()
        return picking_position, pick_orientation

    def _step_collect(self, state):
        """Execute collection mode step."""
        success = self._check_phase_success()
        if success:
            if self.current_phase == Phase.PICKING:
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
                    after_offset_z=0.5
                )
            else:
                pour_kwargs = {
                    "articulation_controller": self.robot.get_articulation_controller(),
                    "source_size": self.initial_size,
                    "target_position": state['target_position'],
                    "current_joint_velocities": self.robot.get_joint_velocities(),
                    "pour_speed": -1,
                    "source_name": state['object_name'],
                    "gripper_position": state['gripper_position'],
                    "source_position": (
                        state['object_position']
                        if self._online_fluid_enabled
                        else None
                    ),
                }
                if self._online_fluid_enabled:
                    pour_kwargs["target_end_effector_orientation"] = (
                        self._expert_pour_target_orientation_wxyz
                    )
                    if self._expert_pour_entry_orientation_required:
                        pour_kwargs["current_end_effector_orientation"] = (
                            self.rmp_controller.get_end_effector_orientation_wxyz()
                        )
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
        return {
            "mode": str(self.mode),
            "pick_gripper_offset_object_m": (
                self._expert_pick_gripper_offset_object.tolist()
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
        event = getattr(self.pick_controller, "_event", -1)
        return isinstance(event, int) and event >= 5

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

    def _step_infer(self, state):
        """Execute inference mode step."""
        if self.current_phase == Phase.FINISHED:
            self.reset_needed = True
            return None, True, self._last_success

        if not self.pick_controller.is_done():
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
