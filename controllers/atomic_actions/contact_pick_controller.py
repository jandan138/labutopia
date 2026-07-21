from enum import IntEnum
import copy
import math
import typing

from isaacsim.core.api.controllers import BaseController
from isaacsim.core.utils.stage import get_stage_units
from isaacsim.core.utils.types import ArticulationAction
import numpy as np

from utils.fixed_frame_pose import FixedFramePoseAdapter
from utils.controlled_contact import (
    build_arm_target_token,
    build_finger_target_token,
    validate_target_token,
)


class ContactPickEvent(IntEnum):
    PREGRASP = 0
    ALIGN = 1
    INSERT = 2
    SETTLE = 3
    PRECONTACT_SETTLE = 4
    CLOSE = 5
    CONTACT_SETTLE = 6
    LIFT = 7
    HOLD = 8


_SEMANTIC_ACTION_KINDS = {
    (ContactPickEvent.PREGRASP, "finger"): "GRIPPER_OPEN",
    (ContactPickEvent.PREGRASP, "arm"): "ARM_PREGRASP",
    (ContactPickEvent.ALIGN, "arm"): "ARM_ALIGN",
    (ContactPickEvent.INSERT, "arm"): "ARM_INSERT",
    (ContactPickEvent.SETTLE, "arm"): "ARM_SETTLE",
    (ContactPickEvent.PRECONTACT_SETTLE, "arm"): "ARM_PRECONTACT_SETTLE",
    (ContactPickEvent.CLOSE, "finger"): "GRIPPER_CLOSE",
    (ContactPickEvent.CONTACT_SETTLE, "finger"): "GRIPPER_CONTACT_SETTLE",
    (ContactPickEvent.LIFT, "arm"): "ARM_LIFT",
    (ContactPickEvent.HOLD, "arm"): "ARM_HOLD",
}


class ContactPickController(BaseController):
    """Contact-only pick controller with a frozen grasp frame.

    ``approach_direction`` is a world-space unit vector pointing from the
    pregrasp waypoint toward the grasp. ``grasp_offset`` is expressed in the
    source object frame. Source orientations use SciPy's ``xyzw`` convention;
    end-effector orientations are passed through in the RMP controller's
    convention.
    """

    def __init__(
        self,
        name: str,
        cspace_controller: BaseController,
        control_dt: float = 1.0 / 30.0,
        position_threshold: float = 0.005,
        open_position: float = 0.040,
        open_position_tolerance: float = 0.0002,
        pregrasp_distance: float = 0.10,
        insert_distance: float = 0.03,
        approach_speed: float = 0.03,
        close_speed: float = 0.01,
        lift_speed: float = 0.05,
        settle_duration: float = 0.10,
        precontact_settle_duration: float = 0.10,
        contact_settle_duration: float = 0.10,
        hold_duration: float = 2.0,
        contact_timeout: float = 1.5,
        source_translation_limit: float = 0.002,
        source_tilt_limit_degrees: float = 1.0,
        orientation_threshold_degrees: float = 5.0,
        control_to_end_effector_matrix_m: typing.Optional[np.ndarray] = None,
        end_effector_frame: str = "tool_center",
        control_frame: str = "right_gripper",
        finger_joint_indices: typing.Sequence[int] = (7, 8),
        terminate_after_contact_settle: bool = False,
        require_external_phase_certificates: bool = False,
    ) -> None:
        super().__init__(name=name)
        positive = {
            "control_dt": control_dt,
            "position_threshold": position_threshold,
            "pregrasp_distance": pregrasp_distance,
            "insert_distance": insert_distance,
            "approach_speed": approach_speed,
            "close_speed": close_speed,
            "lift_speed": lift_speed,
            "contact_timeout": contact_timeout,
            "source_translation_limit": source_translation_limit,
            "source_tilt_limit_degrees": source_tilt_limit_degrees,
            "orientation_threshold_degrees": orientation_threshold_degrees,
        }
        for field, value in positive.items():
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"contact_pick_{field}_invalid")
        if not math.isfinite(open_position) or not 0.0 < open_position <= 0.04:
            raise ValueError("contact_pick_open_position_invalid")
        if (
            not math.isfinite(open_position_tolerance)
            or not 0.0 < open_position_tolerance <= open_position
        ):
            raise ValueError("contact_pick_open_position_tolerance_invalid")
        if orientation_threshold_degrees > 180.0:
            raise ValueError("contact_pick_orientation_threshold_degrees_invalid")
        if insert_distance > pregrasp_distance:
            raise ValueError("contact_pick_insert_distance_exceeds_pregrasp")
        for field, value in {
            "settle_duration": settle_duration,
            "precontact_settle_duration": precontact_settle_duration,
            "contact_settle_duration": contact_settle_duration,
            "hold_duration": hold_duration,
        }.items():
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"contact_pick_{field}_invalid")

        self._cspace_controller = cspace_controller
        self._control_dt = float(control_dt)
        self._position_threshold_m = float(position_threshold)
        self._open_position_m = float(open_position)
        self._open_position_tolerance_m = float(open_position_tolerance)
        self._pregrasp_distance_m = float(pregrasp_distance)
        self._insert_distance_m = float(insert_distance)
        self._approach_speed_m_s = float(approach_speed)
        self._close_speed_m_s = float(close_speed)
        self._lift_speed_m_s = float(lift_speed)
        self._settle_duration_s = float(settle_duration)
        self._precontact_settle_duration_s = float(precontact_settle_duration)
        self._contact_settle_duration_s = float(contact_settle_duration)
        self._hold_duration_s = float(hold_duration)
        self._contact_timeout_s = float(contact_timeout)
        self._source_translation_limit_m = float(source_translation_limit)
        self._source_tilt_limit_degrees = float(source_tilt_limit_degrees)
        self._orientation_threshold_degrees = float(
            orientation_threshold_degrees
        )
        if not isinstance(end_effector_frame, str) or not end_effector_frame:
            raise ValueError("contact_pick_end_effector_frame_invalid")
        if not isinstance(control_frame, str) or not control_frame:
            raise ValueError("contact_pick_control_frame_invalid")
        self._end_effector_frame = end_effector_frame
        self._control_frame = control_frame
        self._frame_adapter = FixedFramePoseAdapter(
            control_to_end_effector_matrix_m
        )
        self._finger_joint_indices = tuple(finger_joint_indices)
        if (
            len(self._finger_joint_indices) != 2
            or len(set(self._finger_joint_indices)) != 2
            or any(type(index) is not int for index in self._finger_joint_indices)
            or any(index < 0 for index in self._finger_joint_indices)
        ):
            raise ValueError("contact_pick_finger_joint_indices_invalid")
        if type(terminate_after_contact_settle) is not bool:
            raise TypeError("contact_pick_terminate_after_contact_settle_bool_required")
        if type(require_external_phase_certificates) is not bool:
            raise TypeError(
                "contact_pick_external_phase_certificates_bool_required"
            )
        self._terminate_after_contact_settle = terminate_after_contact_settle
        self._require_external_phase_certificates = (
            require_external_phase_certificates
        )
        self._reset_attempt_state()

    @staticmethod
    def _finite_vector(value, *, shape, error):
        vector = np.asarray(value, dtype=np.float64)
        if vector.shape != shape or not np.all(np.isfinite(vector)):
            raise ValueError(error)
        return vector.copy()

    @classmethod
    def _unit_vector(cls, value, *, shape, error):
        vector = cls._finite_vector(value, shape=shape, error=error)
        norm = float(np.linalg.norm(vector))
        if norm <= 1.0e-12:
            raise ValueError(error)
        return vector / norm

    @staticmethod
    def _rotate_xyzw(quaternion: np.ndarray, vector: np.ndarray) -> np.ndarray:
        imaginary = quaternion[:3]
        return vector + 2.0 * np.cross(
            imaginary,
            np.cross(imaginary, vector) + quaternion[3] * vector,
        )

    @staticmethod
    def _quaternion_angle_degrees(
        first_xyzw: np.ndarray,
        second_xyzw: np.ndarray,
    ) -> float:
        dot = float(abs(np.dot(first_xyzw, second_xyzw)))
        return math.degrees(2.0 * math.acos(float(np.clip(dot, -1.0, 1.0))))

    @staticmethod
    def _stage_units() -> float:
        units = float(get_stage_units())
        if not math.isfinite(units) or units <= 0.0:
            raise ValueError("contact_pick_stage_units_invalid")
        return units

    def _reset_attempt_state(self) -> None:
        self._event = ContactPickEvent.PREGRASP
        self._phase_history = [self._event.name]
        self._phase_elapsed_s = 0.0
        self._contact_wait_elapsed_s = 0.0
        self._attempt_latched = False
        self._open_command_emitted = False
        self._open_command_count = 0
        self._open_position_ready = False
        self._open_confirmed_control_index = None
        self._close_command_emitted = False
        self._close_action_control_index = None
        self._lift_command_emitted = False
        self._contact_acquired = False
        self._probe_completed = False
        self._done = False
        self._terminal_failure_reason = None
        self._control_invocation_count = 0
        self._first_arm_command_control_index = None
        self._arm_before_open_violation = False
        self._arm_action_count = 0
        self._finger_action_count = 0
        self._noop_action_count = 0
        self._last_emitted_phase = None
        self._last_emitted_action_kind = None
        self._last_emitted_semantic_action_kind = None
        self._last_emitted_control_index = None
        self._pending_target_token = None
        self._last_emitted_target_token = None
        self._latched_source_position = None
        self._latched_source_orientation_xyzw = None
        self._latched_end_effector_orientation = None
        self._latched_control_orientation = None
        self._latched_approach_direction = None
        self._latched_grasp_offset = None
        self._grasp_position = None
        self._pregrasp_position = None
        self._align_position = None
        self._insert_waypoint = None
        self._insert_target = None
        self._lift_waypoint = None
        self._lift_target = None
        self._lift_height_m = None
        self._gripper_distance_m = None
        self._contact_hold_distances = None
        self._alignment_error_degrees = None
        self._precontact_latched = False
        self._precontact_physics_step = None
        self._precontact_sides = []
        self._precontact_records = []
        self._precontact_evidence_sha256 = None
        self._precontact_applied_receipt = None
        self._precontact_target_token_sha256 = None
        self._precontact_applied_phase = None
        self._precontact_latch_control_index = None
        self._precontact_hold_target = None
        self._precontact_duplicate_count = 0

    def _set_event(self, event: ContactPickEvent) -> None:
        if event == self._event:
            return
        self._event = event
        self._phase_elapsed_s = 0.0
        self._phase_history.append(event.name)

    def latch_intended_precontact(
        self, evidence: typing.Mapping[str, typing.Any]
    ) -> bool:
        if self._precontact_latched:
            self._precontact_duplicate_count += 1
            return False
        if self._close_command_emitted:
            raise RuntimeError("contact_pick_precontact_after_close")
        if self._terminal_failure_reason is not None or self._done:
            raise RuntimeError("contact_pick_precontact_terminal")
        if not isinstance(evidence, typing.Mapping):
            raise TypeError("contact_pick_precontact_evidence_mapping_required")
        physics_step = evidence.get("physics_step")
        sides = evidence.get("sides")
        records = evidence.get("records")
        evidence_sha256 = evidence.get("evidence_sha256")
        if (
            evidence.get("authority")
            != "controlled_contact_complete_manifold_v1"
            or type(physics_step) is not int
            or physics_step < 0
            or not isinstance(sides, typing.Sequence)
            or isinstance(sides, (str, bytes))
            or not sides
            or any(side not in {"left", "right"} for side in sides)
            or len(sides) != len(set(sides))
            or not isinstance(records, typing.Sequence)
            or isinstance(records, (str, bytes))
            or not records
            or any(
                not isinstance(record, typing.Mapping)
                or record.get("class") != "INTENDED_PRECONTACT"
                or record.get("side") not in sides
                for record in records
            )
            or not isinstance(evidence_sha256, str)
            or len(evidence_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in evidence_sha256
            )
        ):
            raise ValueError("contact_pick_precontact_evidence_invalid")
        applied_phase = self._last_emitted_phase
        if (
            not self._attempt_latched
            or applied_phase not in {"INSERT", "SETTLE"}
            or self._insert_waypoint is None
        ):
            raise RuntimeError("contact_pick_precontact_phase_invalid")

        applied_event = ContactPickEvent[applied_phase]
        if self._event != applied_event:
            if not self._phase_history or self._phase_history[-1] != self._event.name:
                raise RuntimeError("contact_pick_precontact_transition_invalid")
            self._phase_history.pop()
            self._event = applied_event
        receipt = evidence.get("applied_receipt")
        if not isinstance(receipt, typing.Mapping):
            raise ValueError("contact_pick_precontact_applied_receipt_required")
        expected_semantic_kind = {
            "INSERT": "ARM_INSERT",
            "SETTLE": "ARM_SETTLE",
        }[applied_phase]
        if (
            receipt.get("authority")
            != "controlled_action_applied_receipt_v1"
            or receipt.get("phase") != applied_phase
            or receipt.get("semantic_action_kind") != expected_semantic_kind
            or receipt.get("channel") != "arm"
            or receipt.get("applied") is not True
        ):
            raise ValueError("contact_pick_precontact_applied_receipt_invalid")
        receipt_token = validate_target_token(receipt.get("target_token"))
        if (
            self._last_emitted_target_token is None
            or receipt.get("target_token_sha256") != receipt_token["sha256"]
            or receipt_token != self._last_emitted_target_token
        ):
            raise RuntimeError("contact_pick_precontact_target_token_mismatch")
        self._precontact_latched = True
        self._precontact_physics_step = physics_step
        self._precontact_sides = sorted(sides)
        self._precontact_records = copy.deepcopy(list(records))
        self._precontact_evidence_sha256 = evidence_sha256
        self._precontact_applied_receipt = copy.deepcopy(dict(receipt))
        self._precontact_target_token_sha256 = receipt_token["sha256"]
        self._precontact_applied_phase = applied_phase
        self._precontact_latch_control_index = self._control_invocation_count
        self._precontact_hold_target = self._insert_waypoint.copy()
        self._set_event(ContactPickEvent.PRECONTACT_SETTLE)
        return True

    def _latch_attempt(
        self,
        *,
        source_position: np.ndarray,
        source_orientation_xyzw: np.ndarray,
        end_effector_orientation: np.ndarray,
        approach_direction: np.ndarray,
        grasp_offset: np.ndarray,
        lift_height: float,
        gripper_distance: float,
    ) -> None:
        if not math.isfinite(lift_height) or lift_height <= 0.0:
            raise ValueError("contact_pick_lift_height_invalid")
        if not math.isfinite(gripper_distance) or not 0.0 <= gripper_distance <= 0.04:
            raise ValueError("contact_pick_gripper_distance_invalid")

        units = self._stage_units()
        self._latched_source_position = source_position.copy()
        self._latched_source_orientation_xyzw = source_orientation_xyzw.copy()
        self._latched_end_effector_orientation = end_effector_orientation.copy()
        self._latched_approach_direction = approach_direction.copy()
        self._latched_grasp_offset = grasp_offset.copy()
        rotated_offset = self._rotate_xyzw(
            source_orientation_xyzw,
            grasp_offset / units,
        )
        self._grasp_position = source_position + rotated_offset
        self._pregrasp_position = (
            self._grasp_position
            - approach_direction * (self._pregrasp_distance_m / units)
        )
        self._align_position = (
            self._grasp_position
            - approach_direction * (self._insert_distance_m / units)
        )
        self._insert_waypoint = self._align_position.copy()
        self._insert_target = self._align_position.copy()
        self._insert_target[2] = self._grasp_position[2]
        self._lift_waypoint = self._grasp_position.copy()
        self._lift_height_m = float(lift_height)
        self._lift_target = self._grasp_position + np.asarray(
            [0.0, 0.0, lift_height / units], dtype=np.float64
        )
        self._gripper_distance_m = float(gripper_distance)
        _, self._latched_control_orientation = self._frame_adapter.map_target_pose(
            target_position_world=self._grasp_position,
            target_orientation_wxyz=self._latched_end_effector_orientation,
            meters_per_stage_unit=units,
        )
        self._attempt_latched = True

    def _noop_action(self, joint_count: int) -> ArticulationAction:
        self._pending_target_token = None
        return ArticulationAction(joint_positions=[None] * joint_count)

    def _gripper_action(
        self,
        joint_count: int,
        left_target: float,
        right_target: typing.Optional[float] = None,
    ) -> ArticulationAction:
        if joint_count <= max(self._finger_joint_indices):
            raise ValueError("contact_pick_joint_positions_too_short")
        targets = [None] * joint_count
        left_index, right_index = self._finger_joint_indices
        targets[left_index] = left_target
        targets[right_index] = left_target if right_target is None else right_target
        self._pending_target_token = build_finger_target_token(
            joint_indices=self._finger_joint_indices,
            joint_targets=(targets[left_index], targets[right_index]),
        )
        return ArticulationAction(joint_positions=targets)

    def _move_action(self, target: np.ndarray) -> ArticulationAction:
        stage_units = self._stage_units()
        control_position, control_orientation = self._frame_adapter.map_target_pose(
            target_position_world=target,
            target_orientation_wxyz=self._latched_end_effector_orientation,
            meters_per_stage_unit=stage_units,
        )
        self._pending_target_token = build_arm_target_token(
            tool_position_stage_units=target,
            tool_orientation_wxyz=self._latched_end_effector_orientation,
            control_position_stage_units=control_position,
            control_orientation_wxyz=control_orientation,
            tool_frame=self._end_effector_frame,
            control_frame=self._control_frame,
            stage_units_m=stage_units,
        )
        return self._cspace_controller.forward(
            target_end_effector_position=control_position,
            target_end_effector_orientation=control_orientation,
        )

    def _position_reached(
        self,
        current_position: np.ndarray,
        target_position: np.ndarray,
    ) -> bool:
        threshold = self._position_threshold_m / self._stage_units()
        return bool(np.linalg.norm(current_position - target_position) <= threshold)

    def _orientation_reached(
        self,
        current_orientation: typing.Optional[np.ndarray],
    ) -> bool:
        self._alignment_error_degrees = None
        if current_orientation is None:
            return False
        self._alignment_error_degrees = self._quaternion_angle_degrees(
            self._latched_control_orientation,
            current_orientation,
        )
        if self._orientation_threshold_degrees == 180.0:
            return True
        minimum_dot = math.cos(
            math.radians(self._orientation_threshold_degrees) / 2.0
        )
        dot = float(
            abs(
                np.dot(
                    self._latched_control_orientation,
                    current_orientation,
                )
            )
        )
        return bool(dot >= minimum_dot)

    def _duration_reached(self, duration_s: float) -> bool:
        self._phase_elapsed_s += self._control_dt
        return self._phase_elapsed_s + 1.0e-12 >= duration_s

    @staticmethod
    def _step_toward(
        current: np.ndarray,
        target: np.ndarray,
        maximum_step: float,
    ) -> np.ndarray:
        delta = target - current
        distance = float(np.linalg.norm(delta))
        if distance <= maximum_step:
            return target.copy()
        return current + delta * (maximum_step / distance)

    @staticmethod
    def _step_world_z(
        current: np.ndarray,
        target: np.ndarray,
        maximum_step: float,
    ) -> np.ndarray:
        result = current.copy()
        delta_z = float(target[2] - current[2])
        roundoff = 64.0 * np.finfo(np.float64).eps * max(
            1.0,
            abs(float(current[2])),
            abs(float(target[2])),
            abs(float(maximum_step)),
        )
        if abs(delta_z) <= maximum_step + roundoff:
            result[2] = target[2]
        else:
            result[2] += math.copysign(maximum_step, delta_z)
        result[:2] = target[:2]
        return result

    def _emit_action(
        self,
        action: ArticulationAction,
        *,
        phase: ContactPickEvent,
        action_kind: str,
        open_command: bool = False,
        close_command: bool = False,
        lift_command: bool = False,
    ) -> ArticulationAction:
        self._last_emitted_phase = phase.name
        self._last_emitted_action_kind = action_kind
        self._last_emitted_semantic_action_kind = (
            "NOOP"
            if action_kind == "noop"
            else _SEMANTIC_ACTION_KINDS.get((phase, action_kind))
        )
        if self._last_emitted_semantic_action_kind is None:
            raise ValueError("contact_pick_semantic_action_kind_invalid")
        self._last_emitted_control_index = self._control_invocation_count - 1
        self._last_emitted_target_token = copy.deepcopy(
            self._pending_target_token
        )
        self._pending_target_token = None
        if action_kind == "arm":
            self._arm_action_count += 1
            if self._first_arm_command_control_index is None:
                self._first_arm_command_control_index = (
                    self._control_invocation_count
                )
                self._arm_before_open_violation = not bool(
                    self._open_confirmed_control_index is not None
                    and self._open_confirmed_control_index
                    < self._first_arm_command_control_index
                )
        elif action_kind == "finger":
            self._finger_action_count += 1
        elif action_kind == "noop":
            self._noop_action_count += 1
        else:
            raise ValueError("contact_pick_action_kind_invalid")
        if open_command:
            self._open_command_emitted = True
            self._open_command_count += 1
        if close_command:
            self._close_command_emitted = True
            if self._close_action_control_index is None:
                self._close_action_control_index = self._control_invocation_count
        if lift_command:
            self._lift_command_emitted = True
        return action

    def _fail(self, reason: str, joint_count: int) -> ArticulationAction:
        if self._terminal_failure_reason is None:
            self._terminal_failure_reason = reason
        return self._emit_action(
            self._noop_action(joint_count),
            phase=self._event,
            action_kind="noop",
        )

    def _check_precontact_source_motion(
        self,
        source_position: np.ndarray,
        source_orientation_xyzw: np.ndarray,
        joint_count: int,
    ) -> typing.Optional[ArticulationAction]:
        if self._close_command_emitted:
            return None
        units = self._stage_units()
        translation_m = float(
            np.linalg.norm(source_position - self._latched_source_position) * units
        )
        if translation_m > self._source_translation_limit_m + 1.0e-12:
            return self._fail(
                "source_translation_exceeded_before_contact",
                joint_count,
            )
        tilt_degrees = self._quaternion_angle_degrees(
            self._latched_source_orientation_xyzw,
            source_orientation_xyzw,
        )
        if tilt_degrees > self._source_tilt_limit_degrees + 1.0e-9:
            return self._fail("source_tilt_exceeded_before_contact", joint_count)
        return None

    def _external_phase_certificate_ready(
        self,
        phase: str,
        certificates: typing.Optional[typing.Mapping[str, typing.Any]],
    ) -> typing.Optional[bool]:
        if not self._require_external_phase_certificates:
            return None
        if not isinstance(certificates, typing.Mapping):
            raise ValueError("contact_pick_phase_certificates_required")
        certificate = certificates.get(phase)
        if not isinstance(certificate, typing.Mapping):
            raise ValueError("contact_pick_phase_certificate_missing")
        consecutive = certificate.get("consecutive_steps")
        required = certificate.get("required_steps")
        ready = certificate.get("ready")
        if (
            type(consecutive) is not int
            or consecutive < 0
            or type(required) is not int
            or required <= 0
            or type(ready) is not bool
            or ready != (consecutive >= required)
        ):
            raise ValueError("contact_pick_phase_certificate_invalid")
        return ready

    def forward(
        self,
        source_position: np.ndarray,
        source_orientation_xyzw: np.ndarray,
        current_joint_positions: np.ndarray,
        gripper_position: np.ndarray,
        end_effector_orientation: np.ndarray,
        approach_direction: np.ndarray,
        grasp_offset: np.ndarray,
        current_end_effector_orientation: typing.Optional[np.ndarray] = None,
        lift_height: float = 0.10,
        gripper_distance: float = 0.028,
        contact_qualified: bool = False,
        contact_failure_reason: typing.Optional[str] = None,
        phase_certificates: typing.Optional[
            typing.Mapping[str, typing.Any]
        ] = None,
    ) -> ArticulationAction:
        self._control_invocation_count += 1
        joint_positions = self._finite_vector(
            current_joint_positions,
            shape=(len(current_joint_positions),),
            error="contact_pick_joint_positions_invalid",
        )
        joint_count = joint_positions.shape[0]
        if self._terminal_failure_reason is not None or self._done:
            return self._emit_action(
                self._noop_action(joint_count),
                phase=self._event,
                action_kind="noop",
            )
        if joint_count <= max(self._finger_joint_indices):
            raise ValueError("contact_pick_joint_positions_too_short")
        if type(contact_qualified) is not bool:
            raise TypeError("contact_pick_contact_qualified_bool_required")
        if contact_failure_reason is not None:
            if not isinstance(contact_failure_reason, str) or not contact_failure_reason:
                raise ValueError("contact_pick_failure_reason_invalid")
            return self._fail(contact_failure_reason, joint_count)

        source = self._finite_vector(
            source_position,
            shape=(3,),
            error="contact_pick_source_position_invalid",
        )
        source_orientation = self._unit_vector(
            source_orientation_xyzw,
            shape=(4,),
            error="contact_pick_source_orientation_xyzw_invalid",
        )
        gripper = self._finite_vector(
            gripper_position,
            shape=(3,),
            error="contact_pick_gripper_position_invalid",
        )
        current_orientation = None
        if current_end_effector_orientation is not None:
            current_orientation = self._unit_vector(
                current_end_effector_orientation,
                shape=(4,),
                error="contact_pick_current_end_effector_orientation_invalid",
            )

        if not self._attempt_latched:
            target_orientation = self._unit_vector(
                end_effector_orientation,
                shape=(4,),
                error="contact_pick_end_effector_orientation_invalid",
            )
            first_nonzero = next(
                (float(value) for value in target_orientation if value != 0.0),
                0.0,
            )
            if first_nonzero < 0.0:
                target_orientation = -target_orientation
            target_orientation[target_orientation == 0.0] = 0.0
            direction = self._unit_vector(
                approach_direction,
                shape=(3,),
                error="contact_pick_approach_direction_invalid",
            )
            offset = self._finite_vector(
                grasp_offset,
                shape=(3,),
                error="contact_pick_grasp_offset_invalid",
            )
            self._latch_attempt(
                source_position=source,
                source_orientation_xyzw=source_orientation,
                end_effector_orientation=target_orientation,
                approach_direction=direction,
                grasp_offset=offset,
                lift_height=float(lift_height),
                gripper_distance=float(gripper_distance),
            )

        failed_action = self._check_precontact_source_motion(
            source,
            source_orientation,
            joint_count,
        )
        if failed_action is not None:
            return failed_action

        contact_phase = self._close_command_emitted and self._event in (
            ContactPickEvent.CLOSE,
            ContactPickEvent.CONTACT_SETTLE,
            ContactPickEvent.LIFT,
            ContactPickEvent.HOLD,
        )
        if self._event == ContactPickEvent.CLOSE:
            close_certificate = self._external_phase_certificate_ready(
                "CLOSE",
                phase_certificates,
            )
            if close_certificate is not None:
                contact_qualified = bool(
                    contact_qualified and close_certificate
                )
        if contact_phase:
            if not self._contact_acquired and contact_qualified:
                self._contact_acquired = True
                self._contact_hold_distances = joint_positions[
                    list(self._finger_joint_indices)
                ].copy()
            elif self._contact_acquired and not contact_qualified:
                return self._fail("grasp_lost", joint_count)
            if not self._contact_acquired:
                self._contact_wait_elapsed_s += self._control_dt
                if (
                    self._contact_wait_elapsed_s + 1.0e-12
                    >= self._contact_timeout_s
                ):
                    return self._fail("contact_timeout", joint_count)

        if self._event == ContactPickEvent.PREGRASP:
            open_target = self._open_position_m / self._stage_units()
            if not self._open_command_emitted:
                return self._emit_action(
                    self._gripper_action(joint_count, open_target),
                    phase=ContactPickEvent.PREGRASP,
                    action_kind="finger",
                    open_command=True,
                )
            if not self._open_position_ready:
                tolerance = (
                    self._open_position_tolerance_m / self._stage_units()
                )
                current_fingers = joint_positions[
                    list(self._finger_joint_indices)
                ]
                if np.all(
                    (current_fingers >= open_target - tolerance)
                    & (current_fingers <= open_target + tolerance)
                ):
                    self._open_position_ready = True
                    self._open_confirmed_control_index = (
                        self._control_invocation_count
                    )
                return self._emit_action(
                    self._gripper_action(joint_count, open_target),
                    phase=ContactPickEvent.PREGRASP,
                    action_kind="finger",
                    open_command=True,
                )
            action = self._move_action(self._pregrasp_position)
            if self._position_reached(gripper, self._pregrasp_position):
                self._set_event(ContactPickEvent.ALIGN)
            return self._emit_action(
                action,
                phase=ContactPickEvent.PREGRASP,
                action_kind="arm",
            )

        if self._event == ContactPickEvent.ALIGN:
            action = self._move_action(self._align_position)
            orientation_reached = self._orientation_reached(
                current_orientation
            )
            if (
                self._position_reached(gripper, self._align_position)
                and orientation_reached
            ):
                self._insert_waypoint = self._align_position.copy()
                self._set_event(ContactPickEvent.INSERT)
            return self._emit_action(
                action,
                phase=ContactPickEvent.ALIGN,
                action_kind="arm",
            )

        if self._event == ContactPickEvent.INSERT:
            maximum_step = (
                self._approach_speed_m_s
                * self._control_dt
                / self._stage_units()
            )
            self._insert_waypoint = self._step_world_z(
                self._insert_waypoint,
                self._insert_target,
                maximum_step,
            )
            action = self._move_action(self._insert_waypoint)
            if (
                np.array_equal(self._insert_waypoint, self._insert_target)
                and self._position_reached(gripper, self._insert_target)
            ):
                self._set_event(ContactPickEvent.SETTLE)
            return self._emit_action(
                action,
                phase=ContactPickEvent.INSERT,
                action_kind="arm",
            )

        if self._event == ContactPickEvent.SETTLE:
            action = self._move_action(self._insert_target)
            position_reached = self._position_reached(
                gripper,
                self._insert_target,
            )
            orientation_reached = self._orientation_reached(
                current_orientation
            )
            pose_reached = bool(position_reached and orientation_reached)
            external_ready = self._external_phase_certificate_ready(
                "SETTLE",
                phase_certificates,
            )
            if external_ready is None:
                if not pose_reached:
                    self._phase_elapsed_s = 0.0
                elif self._duration_reached(self._settle_duration_s):
                    self._set_event(ContactPickEvent.CLOSE)
                return self._emit_action(
                    action,
                    phase=ContactPickEvent.SETTLE,
                    action_kind="arm",
                )
            ready = bool(pose_reached and external_ready)
            if ready:
                self._set_event(ContactPickEvent.CLOSE)
            else:
                if not pose_reached:
                    self._phase_elapsed_s = 0.0
                return self._emit_action(
                    action,
                    phase=ContactPickEvent.SETTLE,
                    action_kind="arm",
                )

        if self._event == ContactPickEvent.PRECONTACT_SETTLE:
            if self._precontact_hold_target is None:
                return self._fail("precontact_hold_target_missing", joint_count)
            action = self._move_action(self._precontact_hold_target)
            position_reached = self._position_reached(
                gripper,
                self._precontact_hold_target,
            )
            orientation_reached = self._orientation_reached(
                current_orientation
            )
            pose_reached = bool(position_reached and orientation_reached)
            external_ready = self._external_phase_certificate_ready(
                "PRECONTACT_SETTLE",
                phase_certificates,
            )
            if external_ready is None:
                if not pose_reached:
                    self._phase_elapsed_s = 0.0
                elif self._duration_reached(self._precontact_settle_duration_s):
                    self._set_event(ContactPickEvent.CLOSE)
                return self._emit_action(
                    action,
                    phase=ContactPickEvent.PRECONTACT_SETTLE,
                    action_kind="arm",
                )
            ready = bool(pose_reached and external_ready)
            if ready:
                self._set_event(ContactPickEvent.CLOSE)
            else:
                if not pose_reached:
                    self._phase_elapsed_s = 0.0
                return self._emit_action(
                    action,
                    phase=ContactPickEvent.PRECONTACT_SETTLE,
                    action_kind="arm",
                )

        target_distance = self._gripper_distance_m / self._stage_units()
        if self._event == ContactPickEvent.CLOSE:
            if self._contact_acquired:
                self._set_event(ContactPickEvent.CONTACT_SETTLE)
                return self._emit_action(
                    self._gripper_action(
                        joint_count,
                        float(self._contact_hold_distances[0]),
                        float(self._contact_hold_distances[1]),
                    ),
                    phase=(
                        ContactPickEvent.CONTACT_SETTLE
                        if self._require_external_phase_certificates
                        else ContactPickEvent.CLOSE
                    ),
                    action_kind="finger",
                    close_command=True,
                )
            close_step = (
                self._close_speed_m_s * self._control_dt / self._stage_units()
            )
            current_fingers = joint_positions[list(self._finger_joint_indices)]
            commanded = np.maximum(
                target_distance,
                current_fingers - close_step,
            )
            action = self._gripper_action(
                joint_count,
                float(commanded[0]),
                float(commanded[1]),
            )
            return self._emit_action(
                action,
                phase=ContactPickEvent.CLOSE,
                action_kind="finger",
                close_command=True,
            )

        if self._event == ContactPickEvent.CONTACT_SETTLE:
            hold_distances = self._contact_hold_distances
            if hold_distances is None:
                hold_distances = np.full(
                    2, target_distance, dtype=np.float64
                )
            external_ready = self._external_phase_certificate_ready(
                "CONTACT_SETTLE",
                phase_certificates,
            )
            if external_ready is None:
                action = self._gripper_action(
                    joint_count,
                    float(hold_distances[0]),
                    float(hold_distances[1]),
                )
                if self._contact_acquired and self._duration_reached(
                    self._contact_settle_duration_s
                ):
                    if self._terminate_after_contact_settle:
                        self._probe_completed = True
                        self._done = True
                    else:
                        self._lift_waypoint = gripper.copy()
                        self._set_event(ContactPickEvent.LIFT)
                return self._emit_action(
                    action,
                    phase=ContactPickEvent.CONTACT_SETTLE,
                    action_kind="finger",
                )
            settled = (
                self._contact_acquired and external_ready
            )
            if settled:
                if self._terminate_after_contact_settle:
                    self._probe_completed = True
                    self._done = True
                else:
                    self._lift_waypoint = gripper.copy()
                    self._set_event(ContactPickEvent.LIFT)
            action = (
                self._noop_action(joint_count)
                if self._done
                else self._gripper_action(
                    joint_count,
                    float(hold_distances[0]),
                    float(hold_distances[1]),
                )
            )
            return self._emit_action(
                action,
                phase=ContactPickEvent.CONTACT_SETTLE,
                action_kind="noop" if self._done else "finger",
            )

        if self._event == ContactPickEvent.LIFT:
            maximum_step = (
                self._lift_speed_m_s * self._control_dt / self._stage_units()
            )
            self._lift_waypoint = self._step_toward(
                self._lift_waypoint,
                self._lift_target,
                maximum_step,
            )
            action = self._move_action(self._lift_waypoint)
            if (
                np.array_equal(self._lift_waypoint, self._lift_target)
                and self._position_reached(gripper, self._lift_target)
            ):
                self._set_event(ContactPickEvent.HOLD)
            return self._emit_action(
                action,
                phase=ContactPickEvent.LIFT,
                action_kind="arm",
                lift_command=True,
            )

        action = self._move_action(self._lift_target)
        if self._position_reached(gripper, self._lift_target) and self._duration_reached(
            self._hold_duration_s
        ):
            self._done = True
        return self._emit_action(
            action,
            phase=ContactPickEvent.HOLD,
            action_kind="arm",
        )

    @property
    def current_event(self) -> ContactPickEvent:
        return self._event

    @property
    def terminal_failure_reason(self) -> typing.Optional[str]:
        return self._terminal_failure_reason

    def grasp_contact_requested(self) -> bool:
        return bool(
            self._terminal_failure_reason is None
            and self._close_command_emitted
        )

    def lift_command_emitted(self) -> bool:
        return bool(self._lift_command_emitted)

    def is_done(self) -> bool:
        return bool(self._done or self._terminal_failure_reason is not None)

    def control_evidence(self) -> dict:
        def optional_list(value):
            return None if value is None else value.tolist()

        return {
            "phase": self._event.name,
            "phase_index": int(self._event),
            "phase_history": list(self._phase_history),
            "attempt_latched": self._attempt_latched,
            "end_effector_frame": self._end_effector_frame,
            "control_frame": self._control_frame,
            "control_to_end_effector_matrix_m": (
                self._frame_adapter.matrix_m.tolist()
            ),
            "finger_joint_indices": list(self._finger_joint_indices),
            "contact_acquired": self._contact_acquired,
            "open_command_emitted": self._open_command_emitted,
            "open_command_count": self._open_command_count,
            "open_position_m": self._open_position_m,
            "open_position_tolerance_m": self._open_position_tolerance_m,
            "open_position_ready": self._open_position_ready,
            "open_confirmed_control_index": (
                self._open_confirmed_control_index
            ),
            "close_command_emitted": self._close_command_emitted,
            "close_action_control_index": self._close_action_control_index,
            "lift_command_emitted": self._lift_command_emitted,
            "control_invocation_count": self._control_invocation_count,
            "first_arm_command_control_index": (
                self._first_arm_command_control_index
            ),
            "arm_before_open_violation": self._arm_before_open_violation,
            "arm_action_count": self._arm_action_count,
            "finger_action_count": self._finger_action_count,
            "noop_action_count": self._noop_action_count,
            "last_emitted_phase": self._last_emitted_phase,
            "last_emitted_action_kind": self._last_emitted_action_kind,
            "last_emitted_semantic_action_kind": (
                self._last_emitted_semantic_action_kind
            ),
            "last_emitted_control_index": self._last_emitted_control_index,
            "last_emitted_target_token": copy.deepcopy(
                self._last_emitted_target_token
            ),
            "terminate_after_contact_settle": (
                self._terminate_after_contact_settle
            ),
            "probe_completed": self._probe_completed,
            "done": self._done,
            "terminal_failure_reason": self._terminal_failure_reason,
            "latched_source_position": optional_list(
                self._latched_source_position
            ),
            "latched_source_orientation_xyzw": optional_list(
                self._latched_source_orientation_xyzw
            ),
            "latched_end_effector_orientation_wxyz": optional_list(
                self._latched_end_effector_orientation
            ),
            "latched_control_orientation_wxyz": optional_list(
                self._latched_control_orientation
            ),
            "grasp_position": optional_list(self._grasp_position),
            "pregrasp_position": optional_list(self._pregrasp_position),
            "align_position": optional_list(self._align_position),
            "insert_waypoint": optional_list(self._insert_waypoint),
            "insert_target": optional_list(self._insert_target),
            "approach_direction": optional_list(
                self._latched_approach_direction
            ),
            "grasp_offset": optional_list(self._latched_grasp_offset),
            "contact_hold_distances_m": optional_list(
                None
                if self._contact_hold_distances is None
                else self._contact_hold_distances * self._stage_units()
            ),
            "precontact_latched": self._precontact_latched,
            "precontact_physics_step": self._precontact_physics_step,
            "precontact_sides": list(self._precontact_sides),
            "precontact_records": copy.deepcopy(self._precontact_records),
            "precontact_evidence_sha256": self._precontact_evidence_sha256,
            "precontact_applied_receipt": copy.deepcopy(
                self._precontact_applied_receipt
            ),
            "precontact_target_token_sha256": (
                self._precontact_target_token_sha256
            ),
            "precontact_applied_phase": self._precontact_applied_phase,
            "precontact_latch_control_index": (
                self._precontact_latch_control_index
            ),
            "precontact_hold_target": optional_list(
                self._precontact_hold_target
            ),
            "precontact_duplicate_count": self._precontact_duplicate_count,
            "precontact_settle_duration_s": (
                self._precontact_settle_duration_s
            ),
            "lift_waypoint": optional_list(self._lift_waypoint),
            "lift_target": optional_list(self._lift_target),
            "lift_speed_m_s": self._lift_speed_m_s,
            "approach_speed_m_s": self._approach_speed_m_s,
            "close_speed_m_s": self._close_speed_m_s,
            "pregrasp_distance_m": self._pregrasp_distance_m,
            "insert_distance_m": self._insert_distance_m,
            "position_threshold_m": self._position_threshold_m,
            "control_dt_s": self._control_dt,
            "contact_timeout_s": self._contact_timeout_s,
            "source_translation_limit_m": self._source_translation_limit_m,
            "source_tilt_limit_degrees": self._source_tilt_limit_degrees,
            "orientation_threshold_degrees": (
                self._orientation_threshold_degrees
            ),
            "alignment_error_degrees": self._alignment_error_degrees,
        }

    def reset(self) -> None:
        super().reset()
        self._cspace_controller.reset()
        self._reset_attempt_state()
