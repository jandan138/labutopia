"""Strict model-facing orchestration for online physics-driven liquid surfaces."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

import numpy as np

from utils.online_fluid_surface import (
    ObservationTransition,
    OnlineFluidSurfaceRuntime,
    SurfaceFrameToken,
    validate_simulation_points,
)


_NO_PENDING_ACTION = object()
_ACTION_FIELDS = (
    "joint_positions",
    "joint_velocities",
    "joint_efforts",
    "joint_indices",
)


def _action_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("action_nonfinite")
        return value
    if isinstance(value, np.generic):
        return _action_json_value(value.item())
    if isinstance(value, np.ndarray):
        if np.issubdtype(value.dtype, np.number) and not np.isfinite(value).all():
            raise ValueError("action_nonfinite")
        contiguous = np.ascontiguousarray(value)
        return {
            "dtype": contiguous.dtype.str,
            "shape": list(contiguous.shape),
            "values": contiguous.tolist(),
        }
    if isinstance(value, Mapping):
        return {
            str(key): _action_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_action_json_value(item) for item in value]

    fields = {
        name: _action_json_value(getattr(value, name))
        for name in _ACTION_FIELDS
        if hasattr(value, name)
    }
    if fields:
        return {
            "action_type": f"{type(value).__module__}.{type(value).__qualname__}",
            "fields": fields,
        }
    raise TypeError(f"action_not_canonicalizable:{type(value).__qualname__}")


def canonical_action_sha256(action: Any) -> str:
    payload = {"kind": "noop"} if action is None else {
        "kind": "action",
        "value": _action_json_value(action),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def append_fluid_observation_evidence(
    path: str | Path,
    observation: Mapping[str, Any],
) -> dict[str, Any]:
    """Append the compact provenance for one exact model-facing observation."""
    if not isinstance(observation, Mapping):
        raise TypeError("fluid_observation_mapping_required")
    payload: dict[str, Any] = {}
    for key in ("record", "score", "attachment"):
        value = observation.get(key)
        if not isinstance(value, Mapping):
            raise ValueError(f"fluid_observation_{key}_mapping_required")
        payload[key] = dict(value)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as stream:
        stream.write(encoded)
        stream.write("\n")
    return payload


def observation_limit_reached(
    completed_observations: int,
    maximum_observations: int | None,
) -> bool:
    if type(completed_observations) is not int or completed_observations < 0:
        raise ValueError("completed_observations_invalid")
    if maximum_observations is None:
        return False
    if type(maximum_observations) is not int or maximum_observations <= 0:
        raise ValueError("maximum_observations_invalid")
    return completed_observations >= maximum_observations


def attempt_limit_reached(completed_attempts: int, maximum_attempts: int) -> bool:
    if type(completed_attempts) is not int or completed_attempts < 0:
        raise ValueError("completed_attempts_invalid")
    if type(maximum_attempts) is not int or maximum_attempts <= 0:
        raise ValueError("maximum_attempts_invalid")
    return completed_attempts >= maximum_attempts


def initialize_controller_after_task_reset(
    task: Any,
    controller_factory: Callable[[], Any],
) -> Any:
    task.reset()
    return controller_factory()


def reset_task_then_controller(task: Any, controller: Any) -> None:
    task.reset()
    controller.reset()


def observation_video_fps(rendering_dt: float) -> float:
    if (
        isinstance(rendering_dt, bool)
        or not isinstance(rendering_dt, (int, float, np.number))
        or not math.isfinite(float(rendering_dt))
        or float(rendering_dt) <= 0.0
    ):
        raise ValueError("rendering_dt_invalid")
    frames_per_second = 1.0 / float(rendering_dt)
    rounded = float(round(frames_per_second))
    return rounded if math.isclose(frames_per_second, rounded, abs_tol=1.0e-10) else frames_per_second


def model_camera_video_rgb(
    state: Mapping[str, Any],
    *,
    camera_keys: Sequence[str],
    expected_shape: Sequence[int],
) -> np.ndarray:
    if not isinstance(state, Mapping):
        raise ValueError("task_state_mapping_required")
    camera_data = state.get("camera_data")
    if not isinstance(camera_data, Mapping):
        raise ValueError("model_camera_data_mapping_required")
    keys = tuple(camera_keys)
    shape = tuple(int(value) for value in expected_shape)
    if set(camera_data) != set(keys):
        raise ValueError("model_camera_keys_mismatch")
    frames = []
    for key in keys:
        array = np.asarray(camera_data[key])
        if array.shape != shape:
            raise ValueError(f"model_camera_shape_mismatch:{key}")
        if array.dtype != np.uint8:
            raise ValueError(f"model_camera_dtype_mismatch:{key}")
        frames.append(np.transpose(array, (1, 2, 0)))
    return np.ascontiguousarray(np.concatenate(frames, axis=1))


class _NullAttachment:
    def reset(self) -> None:
        return None

    def maybe_attach(self, controller: Any, state: Mapping[str, Any]) -> bool:
        del controller, state
        return False

    def update_before_substep(self) -> None:
        return None

    def record(self) -> dict[str, Any]:
        return {"mode": "none", "attached": False}


class FluidEvaluationLoop:
    """Own one action-to-observation transition in the fluid evaluation mode."""

    def __init__(
        self,
        *,
        world: Any,
        task: Any,
        expected_particle_count: int,
        physics_substeps_per_observation: int,
        physics_substep_dt: float,
        read_particles: Callable[[], Any],
        score_particles: Callable[[np.ndarray], Mapping[str, Any]],
        reconstruct: Callable[[np.ndarray], Mapping[str, Any]],
        author_surface: Callable[[Mapping[str, Any], SurfaceFrameToken], Mapping[str, Any]],
        invalidate_surface: Callable[[str], None],
        expected_camera_keys: Sequence[str],
        expected_camera_shape: Sequence[int],
        camera_contract: Mapping[str, Any],
        attachment: Any | None = None,
        adapt_state: Callable[[Mapping[str, Any]], Any] | None = None,
    ) -> None:
        if type(expected_particle_count) is not int or expected_particle_count <= 0:
            raise ValueError("expected_particle_count_invalid")
        if (
            type(physics_substeps_per_observation) is not int
            or physics_substeps_per_observation <= 0
        ):
            raise ValueError("physics_substeps_per_observation_invalid")
        if not math.isfinite(physics_substep_dt) or physics_substep_dt <= 0.0:
            raise ValueError("physics_substep_dt_invalid")
        camera_keys = tuple(expected_camera_keys)
        if not camera_keys or len(camera_keys) != len(set(camera_keys)):
            raise ValueError("expected_camera_keys_invalid")
        camera_shape = tuple(int(value) for value in expected_camera_shape)
        if len(camera_shape) != 3 or any(value <= 0 for value in camera_shape):
            raise ValueError("expected_camera_shape_invalid")
        if not isinstance(camera_contract, Mapping):
            raise ValueError("camera_contract_mapping_required")
        camera_contract_id = camera_contract.get("id")
        camera_contract_sha256 = camera_contract.get("sha256")
        if not isinstance(camera_contract_id, str) or not camera_contract_id:
            raise ValueError("camera_contract_id_invalid")
        if (
            not isinstance(camera_contract_sha256, str)
            or len(camera_contract_sha256) != 64
            or any(character not in "0123456789abcdef" for character in camera_contract_sha256)
        ):
            raise ValueError("camera_contract_sha256_invalid")
        if not hasattr(world, "step") or not hasattr(world, "render"):
            raise TypeError("world_step_and_render_required")
        if not hasattr(task, "step"):
            raise TypeError("task_step_required")

        self.world = world
        self.task = task
        self.expected_particle_count = expected_particle_count
        self.physics_substeps_per_observation = physics_substeps_per_observation
        self.physics_substep_dt = float(physics_substep_dt)
        self.read_particles = read_particles
        self.score_particles = score_particles
        self.expected_camera_keys = camera_keys
        self.expected_camera_shape = camera_shape
        self.camera_contract = {
            "id": camera_contract_id,
            "sha256": camera_contract_sha256,
        }
        self.attachment = attachment if attachment is not None else _NullAttachment()
        self.adapt_state = adapt_state

        self._episode_id: str | None = None
        self._observation_index = 0
        self._logical_steps = 0
        self._integration_steps = 0
        self._pending_action: object | Any = _NO_PENDING_ACTION
        self._pending_action_sha256: str | None = None
        self._authority_origin: tuple[int, float] | None = None
        self._last_authority: tuple[int, float] | None = None
        self._last_state: Mapping[str, Any] | None = None
        self._last_score: dict[str, Any] | None = None
        self._failed = False
        self._render_index = 0

        self._surface_runtime = OnlineFluidSurfaceRuntime(
            expected_particle_count=expected_particle_count,
            physics_substeps_per_observation=physics_substeps_per_observation,
            physics_substep_dt=physics_substep_dt,
            reconstruct=reconstruct,
            author_surface=author_surface,
            invalidate_surface=invalidate_surface,
            render_surface=self._render_surface,
            capture_cameras=self._capture_model_cameras,
        )

    @staticmethod
    def _read_world_value(world: Any, name: str) -> Any:
        value = getattr(world, name, None)
        return value() if callable(value) else value

    def _authority_snapshot(self) -> tuple[int, float]:
        step = self._read_world_value(self.world, "current_time_step_index")
        current_time = self._read_world_value(self.world, "current_time")
        if isinstance(step, bool) or not isinstance(step, (int, np.integer)):
            raise RuntimeError("world_step_counter_unavailable")
        if not isinstance(current_time, (int, float, np.number)):
            raise RuntimeError("world_time_unavailable")
        result = (int(step), float(current_time))
        if result[0] < 0 or not math.isfinite(result[1]) or result[1] < 0.0:
            raise RuntimeError("world_authority_invalid")
        return result

    def reset_episode(self, episode_id: str) -> None:
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError("episode_id_invalid")
        self.attachment.reset()
        self._surface_runtime.reset_episode(episode_id)
        authority = self._authority_snapshot()
        self._episode_id = episode_id
        self._observation_index = 0
        self._logical_steps = 0
        self._integration_steps = 0
        self._pending_action = _NO_PENDING_ACTION
        self._pending_action_sha256 = None
        self._authority_origin = authority
        self._last_authority = authority
        self._last_state = None
        self._last_score = None
        self._failed = False
        self._render_index = 0

    def commit_action(self, action: Any) -> str:
        if self._episode_id is None:
            raise RuntimeError("episode_not_reset")
        if self._failed:
            raise RuntimeError("episode_runtime_failed_requires_reset")
        if self._observation_index == 0:
            raise RuntimeError("reset_observation_required_before_action")
        if self._pending_action is not _NO_PENDING_ACTION:
            raise RuntimeError("pending_action_already_committed")
        digest = canonical_action_sha256(action)
        self._pending_action = action
        self._pending_action_sha256 = digest
        return digest

    def maybe_attach(self, controller: Any, state: Mapping[str, Any]) -> bool:
        if self._episode_id is None:
            raise RuntimeError("episode_not_reset")
        return bool(self.attachment.maybe_attach(controller, state))

    def _verify_authority_delta(
        self,
        before: tuple[int, float],
        after: tuple[int, float],
    ) -> None:
        actual_steps = after[0] - before[0]
        if actual_steps != self.physics_substeps_per_observation:
            raise RuntimeError(
                "world_integration_step_delta_invalid:"
                f"expected={self.physics_substeps_per_observation}:actual={actual_steps}"
            )
        expected_time = self.physics_substeps_per_observation * self.physics_substep_dt
        actual_time = after[1] - before[1]
        if not math.isclose(actual_time, expected_time, rel_tol=0.0, abs_tol=1.0e-8):
            raise RuntimeError(
                "world_time_delta_invalid:"
                f"expected={expected_time}:actual={actual_time}"
            )

    def _render_surface(self, token: SurfaceFrameToken) -> dict[str, Any]:
        before = self._authority_snapshot()
        self.world.render()
        after = self._authority_snapshot()
        raw_step_delta = after[0] - before[0]
        self._render_index += 1
        render_token = hashlib.sha256(
            f"{token.identity}:{self._render_index}".encode("ascii")
        ).hexdigest()
        return {
            "render_token": render_token,
            "surface_token": token.identity,
            "logical_steps_before": token.logical_step_after,
            "logical_steps_after": token.logical_step_after + raw_step_delta,
            "integration_steps_before": token.integration_step_after,
            "integration_steps_after": token.integration_step_after + raw_step_delta,
            "timeline_time_before": token.simulation_time_after,
            "timeline_time_after": token.simulation_time_after + (after[1] - before[1]),
        }

    def _capture_model_cameras(
        self,
        token: SurfaceFrameToken,
        render_record: Mapping[str, Any],
    ) -> Mapping[str, np.ndarray]:
        del token, render_record
        state = self.task.step()
        if not isinstance(state, Mapping):
            raise ValueError("task_state_mapping_required")
        if self.adapt_state is not None:
            state = self.adapt_state(state)
            if not isinstance(state, Mapping):
                raise ValueError("adapted_task_state_mapping_required")
        camera_data = state.get("camera_data")
        if not isinstance(camera_data, Mapping):
            raise ValueError("model_camera_data_mapping_required")
        if set(camera_data) != set(self.expected_camera_keys):
            raise ValueError(
                "model_camera_keys_mismatch:"
                f"expected={sorted(self.expected_camera_keys)}:"
                f"actual={sorted(str(key) for key in camera_data)}"
            )
        for name in self.expected_camera_keys:
            array = np.asarray(camera_data[name])
            if array.shape != self.expected_camera_shape:
                raise ValueError(
                    f"model_camera_shape_mismatch:{name}:"
                    f"expected={self.expected_camera_shape}:actual={array.shape}"
                )
            if array.dtype != np.uint8:
                raise ValueError(
                    f"model_camera_dtype_mismatch:{name}:actual={array.dtype}"
                )
        self._last_state = state
        return {name: camera_data[name] for name in self.expected_camera_keys}

    @staticmethod
    def _model_state_pose_record(state: Mapping[str, Any]) -> dict[str, Any] | None:
        if "object_position" not in state or "object_quaternion" not in state:
            return None
        position = np.asarray(state["object_position"], dtype=np.float64)
        quaternion = np.asarray(state["object_quaternion"], dtype=np.float64)
        if position.shape != (3,) or not np.isfinite(position).all():
            raise ValueError("model_state_object_position_invalid")
        if quaternion.shape != (4,) or not np.isfinite(quaternion).all():
            raise ValueError("model_state_object_quaternion_invalid")
        return {
            "object_position": position.tolist(),
            "object_quaternion_xyzw": quaternion.tolist(),
        }

    def _validate_score(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError("fluid_score_mapping_required")
        score = dict(value)
        if int(score.get("particle_count", -1)) != self.expected_particle_count:
            raise ValueError("fluid_score_particle_count_mismatch")
        if score.get("partition_complete") is not True or score.get("valid") is not True:
            raise ValueError("fluid_score_invalid")
        if type(score.get("fluid_transfer_passed")) is not bool:
            raise ValueError("fluid_transfer_passed_missing")
        for field in (
            "strict_zero_spill_transfer_passed",
            "task_transfer_passed",
            "expert_transfer_passed",
        ):
            if type(score.get(field)) is not bool:
                raise ValueError(f"{field}_missing")
        target_fraction = score.get("target_fraction")
        if (
            isinstance(target_fraction, bool)
            or not isinstance(target_fraction, (int, float, np.number))
            or not math.isfinite(float(target_fraction))
            or not 0.0 <= float(target_fraction) <= 1.0
        ):
            raise ValueError("target_fraction_invalid")
        if (
            score["fluid_transfer_passed"]
            != score["strict_zero_spill_transfer_passed"]
        ):
            raise ValueError("strict_transfer_compatibility_alias_mismatch")
        return score

    def observe(self) -> dict[str, Any]:
        if self._episode_id is None:
            raise RuntimeError("episode_not_reset")
        if self._failed:
            raise RuntimeError("episode_runtime_failed_requires_reset")
        is_reset = self._observation_index == 0
        if is_reset:
            if self._pending_action is not _NO_PENDING_ACTION:
                raise RuntimeError("reset_observation_must_not_have_action")
            before = self._authority_snapshot()
            if before != self._last_authority:
                raise RuntimeError("reset_observation_authority_changed")
            after = before
            action_hash = None
            caused_by_action_index = None
            logical_before = self._logical_steps
            integration_before = self._integration_steps
        else:
            if self._pending_action is _NO_PENDING_ACTION:
                raise RuntimeError("pending_action_required")
            before = self._authority_snapshot()
            if before != self._last_authority:
                raise RuntimeError("world_authority_changed_outside_fluid_loop")
            logical_before = self._logical_steps
            integration_before = self._integration_steps
            for _ in range(self.physics_substeps_per_observation):
                self.attachment.update_before_substep()
                self.world.step(render=False)
            after = self._authority_snapshot()
            self._verify_authority_delta(before, after)
            action_hash = self._pending_action_sha256
            caused_by_action_index = self._observation_index - 1

        logical_after = logical_before + (0 if is_reset else 1)
        integration_after = integration_before + (
            0 if is_reset else self.physics_substeps_per_observation
        )
        transition = ObservationTransition(
            episode_id=self._episode_id,
            observation_index=self._observation_index,
            caused_by_action_index=caused_by_action_index,
            logical_step_before=logical_before,
            logical_step_after=logical_after,
            integration_step_before=integration_before,
            integration_step_after=integration_after,
            simulation_time_before=integration_before * self.physics_substep_dt,
            simulation_time_after=integration_after * self.physics_substep_dt,
            action_sha256=action_hash,
        )

        try:
            positions = validate_simulation_points(
                self.read_particles(),
                expected_particle_count=self.expected_particle_count,
            )
            score = self._validate_score(self.score_particles(positions))
            self._last_state = None
            record = self._surface_runtime.process_observation(transition, positions)
            if self._last_state is None:
                raise RuntimeError("model_state_not_captured")
            model_state_pose = self._model_state_pose_record(self._last_state)
            if model_state_pose is not None:
                record["model_state_pose"] = model_state_pose
            record["camera_contract"] = dict(self.camera_contract)
        except Exception:
            self._failed = True
            raise

        self._logical_steps = logical_after
        self._integration_steps = integration_after
        self._last_authority = after
        self._last_score = score
        self._observation_index += 1
        self._pending_action = _NO_PENDING_ACTION
        self._pending_action_sha256 = None
        return {
            "state": self._last_state,
            "record": record,
            "score": score,
            "attachment": dict(self.attachment.record()),
        }

    def finalize_episode(self, *, controller_completed: bool) -> dict[str, bool]:
        if type(controller_completed) is not bool:
            raise TypeError("controller_completed_bool_required")
        if self._last_score is None:
            raise RuntimeError("fluid_observation_required_before_finalize")
        strict_passed = bool(
            self._last_score["strict_zero_spill_transfer_passed"]
        )
        task_passed = bool(self._last_score["task_transfer_passed"])
        expert_passed = bool(self._last_score["expert_transfer_passed"])
        attachment_record = self.attachment.record()
        expert_attachment_valid = attachment_record.get(
            "expert_attachment_valid", True
        )
        if type(expert_attachment_valid) is not bool:
            raise ValueError("expert_attachment_valid_bool_required")
        return {
            "controller_completed": controller_completed,
            "fluid_transfer_passed": strict_passed,
            "strict_zero_spill_transfer_passed": strict_passed,
            "task_transfer_passed": task_passed,
            "expert_transfer_passed": expert_passed,
            "expert_attachment_valid": expert_attachment_valid,
            "expert_episode_accepted": (
                controller_completed
                and expert_passed
                and expert_attachment_valid
            ),
            "success": controller_completed and task_passed,
        }
