from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import numpy as np
import pytest

from utils import fluid_evaluation_loop as fluid_loop
from utils.controlled_contact import build_arm_target_token, build_finger_target_token


def _positions(offset: float = 0.0) -> np.ndarray:
    values = np.arange(12, dtype=np.float64).reshape(4, 3) * 0.001
    values[:, 0] += offset
    return values


def _mesh(positions: np.ndarray) -> dict:
    del positions
    return {
        "vertices": np.asarray(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32
        ),
        "faces": np.asarray([[0, 1, 2]], dtype=np.int32),
        "normals": np.asarray(
            [[0, 0, 1], [0, 0, 1], [0, 0, 1]], dtype=np.float32
        ),
        "geometry_sha256": hashlib.sha256(b"mesh").hexdigest(),
    }


def _containment(
    *,
    source: int = 0,
    target: int = 0,
    transit: int = 0,
    tabletop_spill: int = 0,
    below_table: int = 0,
    nonfinite: int = 0,
    pour_started: bool | None = None,
) -> dict:
    result = {
        "source": source,
        "target": target,
        "transit": transit,
        "tabletop_spill": tabletop_spill,
        "below_table": below_table,
        "nonfinite": nonfinite,
        "particle_count": 4,
        "partition_complete": (
            source
            + target
            + transit
            + tabletop_spill
            + below_table
            + nonfinite
            == 4
        ),
    }
    if pour_started is not None:
        result["pour_started"] = pour_started
    return result


def _terminal_score(*, source: int, target: int, transit: int = 0) -> dict:
    counts = _containment(source=source, target=target, transit=transit)
    target_fraction = target / 4.0
    return {
        **counts,
        "valid": True,
        "fluid_transfer_passed": True,
        "strict_zero_spill_transfer_passed": True,
        "task_transfer_passed": True,
        "expert_transfer_passed": True,
        "target_fraction": target_fraction,
    }


class _World:
    def __init__(self, events: list[str], *, render_advances: bool = False):
        self.events = events
        self.current_time_step_index = 40
        self.current_time = 40 / 120.0
        self.render_advances = render_advances

    def step(self, *, render: bool) -> None:
        self.events.append(f"world.step:{render}")
        self.current_time_step_index += 1
        self.current_time += 1 / 120.0

    def render(self) -> None:
        self.events.append("world.render")
        if self.render_advances:
            self.current_time_step_index += 1
            self.current_time += 1 / 120.0


class _ControlledWorld(_World):
    def __init__(self, events):
        super().__init__(events)
        self.playing = False

    def play(self):
        self.events.append("world.play")
        self.playing = True

    def pause(self):
        self.events.append("world.pause")
        self.playing = False

    def is_playing(self):
        return self.playing


class _Task:
    def __init__(self, events: list[str]):
        self.events = events
        self.calls = 0
        self.camera_1 = np.full((3, 4, 4), 17, dtype=np.uint8)
        self.camera_2 = np.full((3, 4, 4), 31, dtype=np.uint8)
        self.state = {
            "camera_data": {
                "Camera1_rgb": self.camera_1,
                "Camera2_rgb": self.camera_2,
            },
            "joint_positions": np.zeros(9, dtype=np.float32),
        }

    def step(self):
        self.events.append("task.step")
        self.calls += 1
        return self.state


class _Attachment:
    def __init__(self, events: list[str]):
        self.events = events
        self.reset_calls = 0
        self.maybe_attach_calls = 0

    def reset(self) -> None:
        self.events.append("attachment.reset")
        self.reset_calls += 1

    def maybe_attach(self, controller, state) -> bool:
        self.events.append("attachment.maybe_attach")
        self.maybe_attach_calls += 1
        return bool(controller == "pouring" and state is not None)

    def update_before_substep(self) -> None:
        self.events.append("attachment.update")

    def record(self) -> dict:
        return {
            "mode": "gripper_attached_kinematic_vessel",
            "attached": self.maybe_attach_calls > 0,
            "expert_attachment_valid": True,
        }


class _ControlledAttachment(_Attachment):
    def __init__(self, events, *, contact_slot=2):
        super().__init__(events)
        self.contact_slot = contact_slot
        self.after_calls = 0
        self.latch_calls = []

    def update_before_substep(self) -> None:
        self.events.append("controlled.before")

    def set_controlled_effective_phase(self, phase):
        self.effective_phase = phase

    def update_after_substep(self):
        self.after_calls += 1
        self.events.append(f"controlled.after:{self.after_calls}")
        if self.after_calls != self.contact_slot:
            return {"kind": "CONTINUE"}
        return {
            "kind": "INTENDED_PRECONTACT",
            "evidence": {
                "authority": "controlled_contact_complete_manifold_v1",
                "physics_step": 40 + self.after_calls,
                "sides": ["left"],
                "records": [
                    {"class": "INTENDED_PRECONTACT", "side": "left"}
                ],
                "evidence_sha256": "d" * 64,
            },
        }

    def latch_intended_precontact(self, evidence):
        self.events.append("controlled.latch")
        self.latch_calls.append(deepcopy(evidence))
        return True

    def validate_controlled_preaction_authority(self):
        return {"kind": "CONTINUE"}


class _TerminalControlledAttachment(_ControlledAttachment):
    def __init__(self, events, *, terminal_slot=2):
        super().__init__(events, contact_slot=100)
        self.terminal_slot = terminal_slot

    def update_after_substep(self):
        self.after_calls += 1
        self.events.append(f"controlled.after:{self.after_calls}")
        if self.after_calls == self.terminal_slot:
            return {
                "kind": "TERMINAL",
                "terminal_kind": "PHYSICAL_CONTACT_FAILURE",
                "failure_reason": "prohibited_contact",
                "classification": {"class_counts": {"PROHIBITED_CONTACT": 1}},
            }
        return {"kind": "CONTINUE"}


class _BaselineFailureControlledAttachment(_ControlledAttachment):
    def validate_controlled_preaction_authority(self):
        return {
            "kind": "TERMINAL",
            "terminal_kind": "PROTOCOL_FAILURE",
            "failure_reason": "contact_report_baseline_pair_mismatch",
        }


class _PrephysicsFailureControlledAttachment(_ControlledAttachment):
    def __init__(self, events):
        super().__init__(events, contact_slot=100)
        self.failed = False

    def maybe_attach(self, controller, state):
        del controller, state
        self.events.append("attachment.maybe_attach")
        self.failed = True
        return False

    def validate_controlled_preaction_authority(self):
        if not self.failed:
            return {"kind": "CONTINUE"}
        return {
            "kind": "TERMINAL",
            "terminal_kind": "PROTOCOL_FAILURE",
            "failure_reason": "contact_sensor_authority_changed",
        }

    def record(self):
        return {
            "mode": "contact_friction_dynamic_v1",
            "mechanical_attachment_used": False,
            "failure_reason": (
                "contact_sensor_authority_changed" if self.failed else None
            ),
        }


class _DeadlineControlledAttachment(_ControlledAttachment):
    def validate_controlled_action_phase(self, phase):
        if phase == "INSERT":
            return {
                "kind": "TERMINAL",
                "terminal_kind": "PHYSICAL_TIMEOUT",
                "failure_reason": "INSERT_timeout",
            }
        return {"kind": "CONTINUE"}


class _UnalignedDeadlineExitAttachment(_ControlledAttachment):
    def update_after_substep(self):
        self.after_calls += 1
        self.events.append(f"controlled.after:{self.after_calls}")
        decision = {"kind": "CONTINUE"}
        if self.after_calls == 2:
            decision["phase_deadline_exit_grace"] = {
                "phase": "ALIGN",
                "controller_phase": "INSERT",
                "phase_elapsed_steps": 3,
                "phase_deadline_steps": 3,
            }
        return decision


class _PhaseAwarePersistentContactAttachment(_ControlledAttachment):
    def __init__(self, events):
        super().__init__(events, contact_slot=100)
        self.effective_phases = []
        self.effective_phase = None

    def set_controlled_effective_phase(self, phase):
        self.effective_phase = phase
        self.effective_phases.append(phase)

    def update_after_substep(self):
        self.after_calls += 1
        self.events.append(f"controlled.after:{self.after_calls}")
        if self.effective_phase == "PRECONTACT_SETTLE":
            return {"kind": "CONTINUE"}
        return {
            "kind": "INTENDED_PRECONTACT",
            "evidence": {
                "authority": "controlled_contact_complete_manifold_v1",
                "physics_step": 40 + self.after_calls,
                "sides": ["left"],
                "records": [
                    {"class": "INTENDED_PRECONTACT", "side": "left"}
                ],
                "evidence_sha256": "d" * 64,
            },
        }

def _make_loop(
    events: list[str],
    *,
    world: _World | None = None,
    task: _Task | None = None,
    adapt_state=None,
    sync_source_visual_state=None,
    initial_render_warmup_updates: int = 0,
    reset_pre_roll_substeps: int = 0,
    sample_containment_after_substep=None,
    camera_contract=None,
    expected_source_ownership=None,
    attachment=None,
    controlled_contact_interlock: bool = False,
):
    world = world or _World(events)
    task = task or _Task(events)
    attachment = attachment or _Attachment(events)
    particle_reads = 0
    scored_arrays: list[np.ndarray] = []
    reconstructed_arrays: list[np.ndarray] = []

    def read_particles():
        nonlocal particle_reads
        events.append("read_particles")
        result = _positions(offset=particle_reads * 0.01)
        particle_reads += 1
        return result

    def score_particles(positions):
        events.append("score_particles")
        scored_arrays.append(positions)
        return {
            "source": 4 if particle_reads == 1 else 0,
            "target": 0 if particle_reads == 1 else 4,
            "transit": 0,
            "tabletop_spill": 0,
            "below_table": 0,
            "nonfinite": 0,
            "particle_count": 4,
            "partition_complete": True,
            "valid": True,
            "fluid_transfer_passed": particle_reads > 1,
            "strict_zero_spill_transfer_passed": particle_reads > 1,
            "task_transfer_passed": particle_reads > 1,
            "expert_transfer_passed": particle_reads > 1,
            "target_fraction": 0.0 if particle_reads == 1 else 1.0,
        }

    def reconstruct(positions):
        events.append("reconstruct")
        reconstructed_arrays.append(positions)
        return _mesh(positions)

    def author(mesh, token):
        events.append("author")
        return {
            "surface_token": token.identity,
            "vertex_count": len(mesh["vertices"]),
            "face_count": len(mesh["faces"]),
        }

    def invalidate(reason):
        events.append(f"invalidate:{reason}")

    loop = fluid_loop.FluidEvaluationLoop(
        world=world,
        task=task,
        expected_particle_count=4,
        physics_substeps_per_observation=4,
        physics_substep_dt=1 / 120.0,
        read_particles=read_particles,
        score_particles=score_particles,
        reconstruct=reconstruct,
        author_surface=author,
        invalidate_surface=invalidate,
        attachment=attachment,
        adapt_state=adapt_state,
        sync_source_visual_state=sync_source_visual_state,
        expected_camera_keys=("Camera1_rgb", "Camera2_rgb"),
        expected_camera_shape=(3, 4, 4),
        camera_contract=camera_contract
        or {
            "id": "test_camera_contract_v1",
            "sha256": "a" * 64,
        },
        initial_render_warmup_updates=initial_render_warmup_updates,
        reset_pre_roll_substeps=reset_pre_roll_substeps,
        expected_source_ownership=expected_source_ownership,
        controlled_contact_interlock=controlled_contact_interlock,
        **(
            {"sample_containment_after_substep": sample_containment_after_substep}
            if sample_containment_after_substep is not None
            else {}
        ),
    )
    return loop, world, task, attachment, scored_arrays, reconstructed_arrays


def test_reset_then_action_observation_has_exact_model_facing_order():
    events: list[str] = []
    loop, world, task, attachment, scored, reconstructed = _make_loop(events)

    loop.reset_episode("episode-1")
    reset_observation = loop.observe()
    loop.commit_action({"joint_positions": np.asarray([0.1, 0.2])})
    assert loop.maybe_attach("pouring", reset_observation["state"])
    action_observation = loop.observe()

    assert events == [
        "attachment.reset",
        "invalidate:episode_reset",
        "read_particles",
        "score_particles",
        "reconstruct",
        "author",
        "world.render",
        "task.step",
        "attachment.maybe_attach",
        "attachment.update",
        "world.step:False",
        "attachment.update",
        "world.step:False",
        "attachment.update",
        "world.step:False",
        "attachment.update",
        "world.step:False",
        "read_particles",
        "score_particles",
        "reconstruct",
        "author",
        "world.render",
        "task.step",
    ]
    assert world.current_time_step_index == 44
    assert task.calls == 2
    assert reset_observation["record"]["caused_by_action_index"] is None
    assert action_observation["record"]["caused_by_action_index"] == 0
    assert action_observation["record"]["integration_step_after"] == 4
    assert action_observation["state"] is task.state
    assert action_observation["state"]["camera_data"]["Camera1_rgb"] is task.camera_1
    assert action_observation["record"]["cameras"]["Camera1_rgb"]["shape"] == [3, 4, 4]
    assert action_observation["record"]["camera_contract"] == {
        "id": "test_camera_contract_v1",
        "sha256": "a" * 64,
    }
    assert (
        action_observation["record"]["latency_seconds"]["model_ready_total"]
        >= action_observation["record"]["latency_seconds"]["total"]
    )
    assert action_observation["score"]["fluid_transfer_passed"] is True
    np.testing.assert_array_equal(scored[1], reconstructed[1])
    assert action_observation["attachment"]["mode"] == (
        "gripper_attached_kinematic_vessel"
    )


def test_monitor_start_is_distinct_from_mechanical_attachment_use():
    events: list[str] = []

    class MonitoringAttachment(_Attachment):
        def record(self) -> dict:
            return {
                "mode": "contact_friction_dynamic_v1",
                "monitoring": self.maybe_attach_calls > 0,
                "mechanical_attachment_used": False,
            }

    loop, _, _, _, _, _ = _make_loop(
        events,
        attachment=MonitoringAttachment(events),
        expected_source_ownership="contact_friction_dynamic_v1",
    )
    loop.reset_episode("episode-monitoring")

    assert loop.maybe_attach("pouring", {}) is True
    assert loop.mechanical_attachment_used is False


def test_controlled_reset_pauses_active_timeline_before_pre_roll():
    events: list[str] = []
    world = _ControlledWorld(events)
    world.playing = True
    attachment = _ControlledAttachment(events, contact_slot=100)
    loop, _, _, _, _, _ = _make_loop(
        events,
        world=world,
        attachment=attachment,
        reset_pre_roll_substeps=1,
        controlled_contact_interlock=True,
    )

    loop.reset_episode("episode-controlled-pause")

    assert events.index("world.pause") < events.index("controlled.before")
    assert world.current_time_step_index == 41
    assert world.is_playing() is False


@pytest.mark.parametrize("failure_mode", ["advance", "raise"])
def test_controlled_play_failure_still_pauses_before_propagating(failure_mode):
    events: list[str] = []

    class FailingPlayWorld(_ControlledWorld):
        def play(self):
            super().play()
            if failure_mode == "advance":
                self.current_time_step_index += 1
                self.current_time += 1 / 120.0
            else:
                raise RuntimeError("play_failed")

    world = FailingPlayWorld(events)
    loop, _, _, _, _, _ = _make_loop(
        events,
        world=world,
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-play-failure")
    loop.observe()
    _commit_controlled_test_action(loop, [])

    with pytest.raises(RuntimeError):
        loop.observe()

    assert world.is_playing() is False
    assert events[-1] == "world.pause"


def test_dynamic_pre_roll_and_contact_sampling_are_owned_by_the_fluid_loop():
    events: list[str] = []
    loop, world, _, attachment, *_ = _make_loop(
        events,
        reset_pre_roll_substeps=3,
    )
    attachment.update_after_substep = lambda: events.append(
        "attachment.update_after"
    )

    loop.reset_episode("episode-1")
    observation = loop.observe()
    loop.commit_action(None)
    loop.observe()

    assert events[:11] == [
        "attachment.reset",
        "invalidate:episode_reset",
        "attachment.update",
        "world.step:False",
        "attachment.update_after",
        "attachment.update",
        "world.step:False",
        "attachment.update_after",
        "attachment.update",
        "world.step:False",
        "attachment.update_after",
    ]
    assert events.count("attachment.update_after") == 7
    assert world.current_time_step_index == 47
    assert observation["record"]["reset_pre_roll_substeps"] == 3
    assert observation["record"]["integration_step_after"] == 0


def test_control_dt_is_derived_from_and_matches_the_fluid_schedule():
    assert fluid_loop.fluid_control_dt(
        physics_dt=1 / 120,
        physics_substeps_per_observation=4,
        rendering_dt=1 / 30,
    ) == pytest.approx(1 / 30)

    with pytest.raises(ValueError, match="fluid_control_dt_rendering_mismatch"):
        fluid_loop.fluid_control_dt(
            physics_dt=1 / 120,
            physics_substeps_per_observation=3,
            rendering_dt=1 / 30,
        )


def test_containment_callback_follows_every_pre_roll_and_action_substep():
    events: list[str] = []

    def sample_containment():
        events.append("containment.sample")
        return _containment(source=4)

    loop, _, _, attachment, *_ = _make_loop(
        events,
        reset_pre_roll_substeps=2,
        sample_containment_after_substep=sample_containment,
    )
    attachment.update_after_substep = lambda: events.append(
        "attachment.update_after"
    )

    loop.reset_episode("episode-1")
    loop.observe()
    loop.commit_action(None)
    observation = loop.observe()

    sample_indices = [
        index for index, event in enumerate(events) if event == "containment.sample"
    ]
    assert len(sample_indices) == 6
    assert all(events[index - 1] == "attachment.update_after" for index in sample_indices)
    summary = observation["record"]["cumulative_containment"]
    assert summary["expected_substep_sample_count"] == 6
    assert summary["substep_sample_count"] == 6
    assert summary["substep_sampling_complete"] is True


def test_state_adapter_runs_after_task_step_and_preserves_exact_camera_arrays():
    events: list[str] = []

    def adapt_state(state):
        events.append("adapt_state")
        adapted = dict(state)
        adapted["object_position"] = np.asarray([0.2, -0.1, 1.1])
        adapted["object_quaternion"] = np.asarray([0.0, 0.0, 0.0, 1.0])
        return adapted

    loop, _, task, *_ = _make_loop(events, adapt_state=adapt_state)
    loop.reset_episode("episode-1")

    observation = loop.observe()

    assert events[-3:] == ["world.render", "task.step", "adapt_state"]
    assert observation["state"] is not task.state
    assert observation["state"]["camera_data"] is task.state["camera_data"]
    assert observation["state"]["camera_data"]["Camera1_rgb"] is task.camera_1
    assert "object_position" not in task.state
    np.testing.assert_allclose(observation["state"]["object_position"], [0.2, -0.1, 1.1])
    assert observation["record"]["model_state_pose"] == {
        "object_position": [0.2, -0.1, 1.1],
        "object_quaternion_xyzw": [0.0, 0.0, 0.0, 1.0],
    }


def test_invalid_state_adapter_result_fails_episode_until_reset():
    events: list[str] = []
    loop, *_ = _make_loop(events, adapt_state=lambda state: None)
    loop.reset_episode("episode-1")

    with pytest.raises(ValueError, match="adapted_task_state_mapping_required"):
        loop.observe()
    with pytest.raises(RuntimeError, match="episode_runtime_failed_requires_reset"):
        loop.observe()


def test_pending_action_is_required_and_cannot_be_overwritten():
    events: list[str] = []
    loop, *_ = _make_loop(events)
    loop.reset_episode("episode-1")
    loop.observe()

    with pytest.raises(RuntimeError, match="pending_action_required"):
        loop.observe()

    loop.commit_action(None)
    with pytest.raises(RuntimeError, match="pending_action_already_committed"):
        loop.commit_action(None)


def test_render_that_advances_physics_invalidates_observation():
    events: list[str] = []
    world = _World(events, render_advances=True)
    loop, *_ = _make_loop(events, world=world)
    loop.reset_episode("episode-1")

    with pytest.raises(RuntimeError, match="render_advanced_physics_or_timeline"):
        loop.observe()

    assert any(item.startswith("invalidate:observation_failed") for item in events)


def test_initial_render_warmup_is_unobserved_and_runs_once_per_episode():
    events: list[str] = []
    loop, world, task, *_ = _make_loop(
        events,
        initial_render_warmup_updates=3,
    )
    loop.reset_episode("episode-1")

    first = loop.observe()
    loop.commit_action(None)
    second = loop.observe()

    assert events.count("world.render") == 5
    assert task.calls == 2
    assert world.current_time_step_index == 44
    assert first["record"]["observation_index"] == 0
    assert second["record"]["observation_index"] == 1
    assert first["record"]["render"]["initial_warmup_updates"] == 3
    assert first["record"]["render"]["render_call_count"] == 4
    assert second["record"]["render"]["initial_warmup_updates"] == 0
    assert second["record"]["render"]["render_call_count"] == 1
    assert first["record"]["render"]["physics_and_timeline_unchanged"] is True
    assert second["record"]["render"]["physics_and_timeline_unchanged"] is True


def test_full_camera_contract_is_retained_for_episode_metadata():
    contract = {
        "schema_version": 2,
        "id": "test_camera_contract_v2",
        "compatibility": "requires_v2_data_or_model",
        "rendering_dt": 1.0 / 30.0,
        "cameras": [{"name": "camera_1", "frequency": 30}],
        "sha256": "b" * 64,
    }
    loop, *_ = _make_loop([], camera_contract=contract)

    assert loop.camera_contract == contract
    assert loop.camera_contract is not contract


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_initial_render_warmup_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="initial_render_warmup_updates_invalid"):
        _make_loop([], initial_render_warmup_updates=value)


@pytest.mark.parametrize(
    ("camera_data", "message"),
    [
        (
            {"Camera1_rgb": np.zeros((3, 4, 4), dtype=np.uint8)},
            "model_camera_keys_mismatch",
        ),
        (
            {
                "Camera1_rgb": np.zeros((4, 4, 3), dtype=np.uint8),
                "Camera2_rgb": np.zeros((3, 4, 4), dtype=np.uint8),
            },
            "model_camera_shape_mismatch",
        ),
        (
            {
                "Camera1_rgb": np.zeros((3, 4, 4), dtype=np.float32),
                "Camera2_rgb": np.zeros((3, 4, 4), dtype=np.uint8),
            },
            "model_camera_dtype_mismatch",
        ),
    ],
)
def test_exact_model_camera_contract_is_strict(camera_data, message):
    events: list[str] = []
    task = _Task(events)
    task.state = {"camera_data": camera_data}
    loop, *_ = _make_loop(events, task=task)
    loop.reset_episode("episode-1")

    with pytest.raises(ValueError, match=message):
        loop.observe()


def test_two_episode_resets_clear_pending_action_and_keep_distinct_tokens():
    events: list[str] = []
    loop, _, _, attachment, *_ = _make_loop(events)

    loop.reset_episode("episode-1")
    first = loop.observe()
    loop.commit_action(None)
    loop.reset_episode("episode-2")
    second = loop.observe()

    assert attachment.reset_calls == 2
    assert first["record"]["episode_id"] == "episode-1"
    assert second["record"]["episode_id"] == "episode-2"
    assert first["record"]["frame_identity"] != second["record"]["frame_identity"]
    assert second["record"]["observation_index"] == 0
    assert second["record"]["integration_step_after"] == 0


def test_repeated_episode_names_get_unique_attempt_and_process_sample_identity():
    first_loop, *_ = _make_loop([])
    first_loop.reset_episode("episode-reused")
    first = first_loop.observe()["record"]

    second_loop, *_ = _make_loop([])
    second_loop.reset_episode("episode-reused")
    second = second_loop.observe()["record"]

    assert first["run_id"] == second["run_id"]
    assert first["attempt_id"] != second["attempt_id"]
    assert first["sample_index"] < second["sample_index"]
    assert first["attempt_status"] == "active"
    assert second["attempt_status"] == "active"


def test_reset_seals_unfinished_attempt_as_interrupted_without_erasing_summary():
    loop, *_ = _make_loop([])
    loop.reset_episode("episode-reused")
    first = loop.observe()
    first_attempt_id = first["record"]["attempt_id"]
    first_summary = deepcopy(first["record"]["cumulative_containment"])

    loop.reset_episode("episode-reused")

    sealed = loop.automatically_sealed_attempts[-1]
    assert sealed["attempt_id"] == first_attempt_id
    assert sealed["attempt_status"] == "interrupted"
    assert sealed["reason"] == "episode_reset_before_finalize"
    assert sealed["cumulative_containment"] == first_summary
    assert loop.attempt_id != first_attempt_id


def test_failed_substep_callback_can_be_explicitly_sealed_with_partial_summary():
    def fail_sample():
        raise RuntimeError("sample_failed")

    loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=fail_sample,
    )
    loop.reset_episode("episode-1")
    loop.observe()
    loop.commit_action(None)

    with pytest.raises(RuntimeError, match="sample_failed"):
        loop.observe()

    sealed = loop.seal_attempt(status="failed", reason="substep_sampling_failed")
    assert sealed["attempt_status"] == "failed"
    assert sealed["reason"] == "substep_sampling_failed"
    assert loop.attempt_sealed is True
    assert sealed["cumulative_containment"][
        "expected_substep_sample_count"
    ] == 1
    assert sealed["cumulative_containment"]["substep_sample_count"] == 0
    assert sealed["cumulative_containment"]["substep_sampling_complete"] is False


def test_action_hash_is_stable_for_equivalent_arrays_and_noop_is_explicit():
    first = fluid_loop.canonical_action_sha256(
        {"joint_positions": np.asarray([1.0, 2.0], dtype=np.float32)}
    )
    second = fluid_loop.canonical_action_sha256(
        {"joint_positions": np.asarray([1.0, 2.0], dtype=np.float32)}
    )
    noop = fluid_loop.canonical_action_sha256(None)

    assert first == second
    assert first != noop
    assert len(noop) == 64


@pytest.mark.parametrize(
    ("phase", "semantic_kind", "action"),
    [
        (
            "PREGRASP",
            "GRIPPER_OPEN",
            {"joint_positions": [None] * 7 + [0.04, 0.04]},
        ),
        (
            "PREGRASP",
            "ARM_PREGRASP",
            {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        ),
        (
            "ALIGN",
            "ARM_ALIGN",
            {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        ),
        (
            "INSERT",
            "ARM_INSERT",
            {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        ),
        (
            "SETTLE",
            "ARM_SETTLE",
            {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        ),
        (
            "PRECONTACT_SETTLE",
            "ARM_PRECONTACT_SETTLE",
            {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        ),
        (
            "CLOSE",
            "GRIPPER_CLOSE",
            {"joint_positions": [None] * 7 + [0.037, 0.037]},
        ),
        (
            "CONTACT_SETTLE",
            "GRIPPER_CONTACT_SETTLE",
            {"joint_positions": [None] * 7 + [0.031, 0.031]},
        ),
    ],
)
def test_controlled_action_gate_validates_before_articulation_mutation(
    phase,
    semantic_kind,
    action,
):
    applied = []
    expected_hash = fluid_loop.canonical_action_sha256(deepcopy(action))

    record = fluid_loop.apply_controlled_action(
        action=action,
        phase=phase,
        semantic_action_kind=semantic_kind,
        terminal_latched=False,
        finger_joint_indices=(7, 8),
        apply_action=lambda value: (
            applied.append(value),
            value["joint_positions"].__setitem__(0, 99.0),
        ),
    )

    assert applied == [action]
    assert record["validated_before_apply"] is True
    assert record["applied"] is True
    assert record["action_sha256"] == expected_hash


def _controlled_arm_target_token():
    return build_arm_target_token(
        tool_position_stage_units=[0.1, 0.2, 0.3],
        tool_orientation_wxyz=[1.0, 0.0, 0.0, 0.0],
        control_position_stage_units=[0.1, 0.2, 0.2966],
        control_orientation_wxyz=[1.0, 0.0, 0.0, 0.0],
        tool_frame="tool_center",
        control_frame="right_gripper",
        stage_units_m=1.0,
    )


def test_controlled_action_transaction_requires_validate_commit_apply_receipt():
    events = []
    loop, world, *_ = _make_loop(events)
    loop.reset_episode("episode-1")
    loop.observe()
    action = {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))}

    proposal = fluid_loop.validate_controlled_action_proposal(
        action=action,
        phase="INSERT",
        semantic_action_kind="ARM_INSERT",
        terminal_latched=False,
        finger_joint_indices=(7, 8),
        target_token=_controlled_arm_target_token(),
        control_index=0,
        interval_index=0,
    )
    assert proposal["validated_before_commit"] is True
    assert world.current_time_step_index == 40

    commit = loop.commit_controlled_action(action, proposal)
    applied = []
    receipt = fluid_loop.apply_controlled_action(
        action=action,
        proposal=proposal,
        commit_record=commit,
        apply_action=applied.append,
    )
    assert applied == [action]
    assert receipt["authority"] == "controlled_action_applied_receipt_v1"
    assert receipt["action_index"] == 0
    assert receipt["apply_index"] == 0
    assert receipt["target_token_sha256"] == proposal["target_token_sha256"]

    with pytest.raises(RuntimeError, match="controlled_action_receipt_required"):
        loop.observe()
    assert world.current_time_step_index == 40

    loop.confirm_controlled_action_applied(receipt)
    loop.observe()
    assert world.current_time_step_index == 44


def test_controlled_action_proposal_rejects_before_commit_or_apply():
    applied = []
    with pytest.raises(RuntimeError, match="controlled_action_channel_invalid"):
        fluid_loop.validate_controlled_action_proposal(
            action={"joint_positions": [0.1] * 9},
            phase="INSERT",
            semantic_action_kind="ARM_INSERT",
            terminal_latched=False,
            finger_joint_indices=(7, 8),
            target_token=_controlled_arm_target_token(),
            control_index=0,
            interval_index=0,
        )
    assert applied == []


def _commit_controlled_test_action(loop, applied, *, target_token=None):
    action = {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))}
    proposal = fluid_loop.validate_controlled_action_proposal(
        action=action,
        phase="INSERT",
        semantic_action_kind="ARM_INSERT",
        terminal_latched=False,
        finger_joint_indices=(7, 8),
        target_token=target_token or _controlled_arm_target_token(),
        control_index=0,
        interval_index=0,
    )
    commit = loop.commit_controlled_action(action, proposal)
    receipt = fluid_loop.apply_controlled_action(
        action=action,
        proposal=proposal,
        commit_record=commit,
        apply_action=applied.append,
    )
    loop.confirm_controlled_action_applied(receipt)
    return action, receipt


def test_controlled_substeps_play_step_pause_and_latch_without_reapply():
    events = []
    world = _ControlledWorld(events)
    attachment = _ControlledAttachment(events, contact_slot=2)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=attachment,
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-1")
    loop.observe()
    events.clear()
    applied = []
    _action, receipt = _commit_controlled_test_action(loop, applied)

    observation = loop.observe()

    assert events[:13] == [
        "controlled.before",
        "world.play",
        "world.step:False",
        "world.pause",
        "controlled.after:1",
        "controlled.before",
        "world.play",
        "world.step:False",
        "world.pause",
        "controlled.after:2",
        "controlled.latch",
        "controlled.before",
        "world.play",
    ]
    assert world.is_playing() is False
    assert applied == [_action]
    assert len(attachment.latch_calls) == 1
    assert attachment.latch_calls[0]["applied_receipt"] == receipt
    interlock = observation["record"]["controlled_contact_interlock"]
    assert interlock["precontact_latched"] is True
    assert interlock["continuation_lease"]["remaining_substep_slots"] == [3, 4]
    assert [item["effective_phase"] for item in interlock["substeps"]] == [
        "INSERT",
        "INSERT",
        "PRECONTACT_SETTLE",
        "PRECONTACT_SETTLE",
    ]


def test_controlled_terminal_returns_partial_interval_without_render_or_padding():
    events = []
    world = _ControlledWorld(events)
    attachment = _TerminalControlledAttachment(events, terminal_slot=2)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=attachment,
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-terminal")
    loop.observe()
    events.clear()
    _action, receipt = _commit_controlled_test_action(loop, [])

    result = loop.observe()

    assert result["kind"] == "CONTROLLED_TERMINAL_TRANSITION"
    terminal = result["terminal"]
    assert terminal["variant"] == "applied_interval"
    assert terminal["terminal_kind"] == "PHYSICAL_CONTACT_FAILURE"
    assert terminal["applied_receipt"] == receipt
    assert terminal["executed_substep_slots"] == [1, 2]
    assert terminal["omitted_substep_slots"] == [3, 4]
    assert terminal["observation_index"] is None
    assert terminal["frame_index"] is None
    assert terminal["timeline_state_after"] == "paused"
    assert world.current_time_step_index == 42
    assert world.is_playing() is False
    assert "world.render" not in events
    assert "task.step" not in events
    assert events.count("world.step:False") == 2


def test_unaligned_movement_deadline_exit_stops_without_d_plus_one_step():
    events = []
    world = _ControlledWorld(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_UnalignedDeadlineExitAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-unaligned-deadline")
    loop.observe()
    events.clear()
    _commit_controlled_test_action(loop, [])

    result = loop.observe()

    terminal = result["terminal"]
    assert terminal["terminal_kind"] == "PHYSICAL_TIMEOUT"
    assert terminal["failure_reason"] == "ALIGN_timeout_unaligned_exit"
    assert terminal["executed_substep_slots"] == [1, 2]
    assert terminal["omitted_substep_slots"] == [3, 4]
    assert events.count("world.step:False") == 2


def test_controlled_baseline_failure_returns_no_action_terminal_before_render():
    events = []
    world = _ControlledWorld(events)
    attachment = _BaselineFailureControlledAttachment(events, contact_slot=100)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=attachment,
        reset_pre_roll_substeps=1,
        controlled_contact_interlock=True,
    )

    loop.reset_episode("episode-baseline-failure")
    result = loop.observe()

    assert result["kind"] == "CONTROLLED_TERMINAL_TRANSITION"
    terminal = result["terminal"]
    assert terminal["variant"] == "no_action_step"
    assert terminal["terminal_kind"] == "PROTOCOL_FAILURE"
    assert terminal["control_index"] is None
    assert terminal["action_index"] is None
    assert terminal["apply_index"] is None
    assert terminal["interval_index"] is None
    assert terminal["observation_index"] is None
    assert terminal["frame_index"] is None
    assert world.current_time_step_index == 41
    assert world.is_playing() is False
    assert "world.render" not in events
    assert "task.step" not in events


def test_controlled_monitor_failure_queues_prephysics_terminal_with_zero_steps():
    events = []
    world = _ControlledWorld(events)
    attachment = _PrephysicsFailureControlledAttachment(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=attachment,
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-prephysics-failure")
    initial = loop.observe()
    before = world.current_time_step_index

    assert loop.maybe_attach("controller", initial["state"]) is False
    assert loop.controlled_terminal_pending is True
    result = loop.observe()

    assert result["kind"] == "CONTROLLED_TERMINAL_TRANSITION"
    terminal = result["terminal"]
    assert terminal["variant"] == "prephysics_transaction"
    assert terminal["terminal_kind"] == "PROTOCOL_FAILURE"
    assert terminal["executed_substep_slots"] == []
    assert terminal["world_counter_before"] == terminal["world_counter_after"]
    assert world.current_time_step_index == before
    assert world.is_playing() is False


def _controlled_insert_action_context():
    return {
        "phase": "INSERT",
        "controller_phase": "INSERT",
        "semantic_action_kind": "ARM_INSERT",
        "terminal_latched": False,
        "finger_joint_indices": [7, 8],
        "target_token": _controlled_arm_target_token(),
        "control_index": 0,
    }


def test_controlled_prephysics_failure_is_absorbing_but_drainable():
    events = []
    world = _ControlledWorld(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-transaction-failure")
    loop.observe()
    events.clear()
    before = (world.current_time_step_index, world.current_time)

    loop.queue_controlled_prephysics_failure(
        stage="proposal_validation",
        error=RuntimeError("invalid proposal"),
        application_outcome="not_invoked",
    )

    assert loop.controlled_terminal_pending is True
    assert loop.controlled_loop_active is True
    assert loop.ready_for_action is False
    with pytest.raises(RuntimeError, match="controlled_terminal_pending"):
        loop.commit_action({"joint_positions": [0.0] * 7})
    with pytest.raises(RuntimeError, match="controlled_terminal_pending"):
        loop.reset_episode("must-not-replace-terminal")
    with pytest.raises(RuntimeError, match="controlled_terminal_already_pending"):
        loop.queue_controlled_prephysics_failure(
            stage="proposal_validation",
            error=RuntimeError("replacement"),
            application_outcome="not_invoked",
        )

    result = loop.observe()

    terminal = result["terminal"]
    assert terminal["variant"] == "prephysics_transaction"
    assert terminal["terminal_kind"] == "PROTOCOL_FAILURE"
    assert terminal["decision"]["transaction"]["stage"] == "proposal_validation"
    assert terminal["decision"]["transaction"]["application_outcome"] == "not_invoked"
    assert terminal["world_counter_before"] == terminal["world_counter_after"]
    assert (world.current_time_step_index, world.current_time) == before
    assert terminal["executed_substep_slots"] == []
    assert terminal["omitted_substep_slots"] == []
    assert not any(event.startswith("world.step") for event in events)
    assert "world.render" not in events
    assert "task.step" not in events


def test_controlled_prephysics_failure_rejects_contradictory_apply_state():
    events = []
    loop, *_ = _make_loop(
        events,
        world=_ControlledWorld(events),
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-invalid-transaction-evidence")
    loop.observe()

    with pytest.raises(ValueError, match="controlled_application_outcome_mismatch"):
        loop.queue_controlled_prephysics_failure(
            stage="apply",
            error=RuntimeError("contradictory evidence"),
            application_outcome="not_invoked",
            apply_callback_entered=True,
        )

    assert loop.controlled_terminal_pending is False


def test_controlled_transaction_rejects_expired_phase_before_commit_or_apply():
    events = []
    world = _ControlledWorld(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_DeadlineControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-expired-phase")
    loop.observe()
    events.clear()
    applied = []

    transaction = fluid_loop.execute_controlled_action_transaction(
        fluid_loop=loop,
        action={"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        read_action_context=_controlled_insert_action_context,
        apply_action=applied.append,
    )

    assert transaction is None
    assert applied == []
    terminal = loop.observe()["terminal"]
    assert terminal["variant"] == "prephysics_transaction"
    assert terminal["terminal_kind"] == "PHYSICAL_TIMEOUT"
    assert terminal["failure_reason"] == "INSERT_timeout"
    assert terminal["command_phase"] == "INSERT"
    assert terminal["control_index"] == 0
    assert terminal["interval_index"] == 0
    assert terminal["action_index"] is None
    assert terminal["omitted_substep_slots"] == []
    assert world.current_time_step_index == 40
    assert not any(event.startswith("world.step") for event in events)


def test_controlled_transaction_apply_exception_records_unknown_application():
    events = []
    world = _ControlledWorld(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-apply-failure")
    loop.observe()
    events.clear()
    action = {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))}
    apply_calls = []

    def mutate_then_raise(value):
        apply_calls.append(deepcopy(value))
        value["joint_positions"][0] = 99.0
        raise RuntimeError("articulation callback failed")

    transaction = fluid_loop.execute_controlled_action_transaction(
        fluid_loop=loop,
        action=action,
        read_action_context=_controlled_insert_action_context,
        apply_action=mutate_then_raise,
    )

    assert transaction is None
    assert len(apply_calls) == 1
    assert loop.controlled_terminal_pending is True
    terminal = loop.observe()["terminal"]
    evidence = terminal["decision"]["transaction"]
    assert evidence["stage"] == "apply"
    assert evidence["apply_callback_entered"] is True
    assert evidence["apply_callback_normal_return"] is False
    assert evidence["application_outcome"] == "invoked_outcome_unknown"
    assert evidence["requires_world_termination"] is True
    assert terminal["control_index"] == 0
    assert terminal["action_index"] == 0
    assert terminal["apply_index"] is None
    assert terminal["interval_index"] == 0
    assert terminal["applied_receipt"] is None
    assert terminal["executed_substep_slots"] == []
    assert terminal["omitted_substep_slots"] == [1, 2, 3, 4]
    assert world.current_time_step_index == 40
    assert world.is_playing() is False
    assert not any(event.startswith("world.step") for event in events)
    assert "world.render" not in events
    assert "task.step" not in events
    assert fluid_loop.validate_controlled_terminal_transition(terminal) == {
        "requires_world_termination": True,
    }


def test_controlled_transaction_commit_exception_preserves_durable_commit(
    monkeypatch,
):
    events = []
    world = _ControlledWorld(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-commit-failure")
    loop.observe()
    original_commit = loop.commit_controlled_action

    def commit_then_raise(action, proposal):
        original_commit(action, proposal)
        raise RuntimeError("commit wrapper failed")

    monkeypatch.setattr(loop, "commit_controlled_action", commit_then_raise)
    applied = []
    transaction = fluid_loop.execute_controlled_action_transaction(
        fluid_loop=loop,
        action={"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        read_action_context=_controlled_insert_action_context,
        apply_action=applied.append,
    )

    assert transaction is None
    assert applied == []
    terminal = loop.observe()["terminal"]
    evidence = terminal["decision"]["transaction"]
    assert evidence["stage"] == "commit"
    assert evidence["application_outcome"] == "not_invoked"
    assert evidence["commit_record"]["action_index"] == 0
    assert terminal["action_index"] == 0
    assert terminal["omitted_substep_slots"] == [1, 2, 3, 4]
    assert evidence["requires_world_termination"] is False
    assert world.current_time_step_index == 40


def test_controlled_transaction_confirmation_failure_preserves_candidate_receipt(
    monkeypatch,
):
    events = []
    world = _ControlledWorld(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-confirm-failure")
    loop.observe()
    events.clear()
    applied = []

    def reject_receipt(_receipt):
        raise RuntimeError("receipt rejected")

    monkeypatch.setattr(loop, "confirm_controlled_action_applied", reject_receipt)
    transaction = fluid_loop.execute_controlled_action_transaction(
        fluid_loop=loop,
        action={"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        read_action_context=_controlled_insert_action_context,
        apply_action=applied.append,
    )

    assert transaction is None
    assert len(applied) == 1
    terminal = loop.observe()["terminal"]
    evidence = terminal["decision"]["transaction"]
    assert evidence["stage"] == "receipt_confirmation"
    assert evidence["application_outcome"] == "normal_return_unconfirmed"
    assert evidence["candidate_receipt"]["authority"] == (
        "controlled_action_applied_receipt_v1"
    )
    assert evidence["requires_world_termination"] is True
    assert terminal["applied_receipt"] is None
    assert terminal["apply_index"] == 0
    assert world.current_time_step_index == 40
    assert not any(event.startswith("world.step") for event in events)


def test_controlled_transaction_logging_failure_records_confirmed_application():
    events = []
    world = _ControlledWorld(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-log-failure")
    loop.observe()
    events.clear()
    applied = []

    transaction = fluid_loop.execute_controlled_action_transaction(
        fluid_loop=loop,
        action={"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        read_action_context=_controlled_insert_action_context,
        apply_action=applied.append,
        log_action=lambda _action: (_ for _ in ()).throw(
            RuntimeError("action log failed")
        ),
    )

    assert transaction is None
    terminal = loop.observe()["terminal"]
    evidence = terminal["decision"]["transaction"]
    assert evidence["stage"] == "action_logging"
    assert evidence["application_outcome"] == "confirmed_applied"
    assert terminal["applied_receipt"]["authority"] == (
        "controlled_action_applied_receipt_v1"
    )
    assert terminal["apply_index"] == 0
    assert evidence["requires_world_termination"] is True
    assert len(applied) == 1
    assert world.current_time_step_index == 40


def test_controlled_transaction_logs_preapply_action_snapshot_and_marks_interval_pending():
    events = []
    world = _ControlledWorld(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-successful-transaction")
    loop.observe()
    action = {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))}
    logged = []

    def mutate_on_apply(value):
        value["joint_positions"][0] = 99.0

    transaction = fluid_loop.execute_controlled_action_transaction(
        fluid_loop=loop,
        action=action,
        read_action_context=_controlled_insert_action_context,
        apply_action=mutate_on_apply,
        log_action=lambda value: logged.append(deepcopy(value)),
    )

    assert transaction is not None
    assert transaction["proposal"]["controller_phase"] == "INSERT"
    assert transaction["commit_record"]["controller_phase"] == "INSERT"
    assert transaction["applied_receipt"]["controller_phase"] == "INSERT"
    assert logged[0]["joint_positions"][0] == pytest.approx(0.1)
    assert loop.controlled_interval_pending is True
    with pytest.raises(RuntimeError, match="controlled_interval_pending"):
        loop.reset_episode("must-not-skip-confirmed-interval")
    observation = loop.observe()
    assert loop.controlled_interval_pending is False
    assert {
        step["controller_phase"]
        for step in observation["record"]["controlled_contact_interlock"]["substeps"]
    } == {"INSERT"}


def test_controlled_terminal_validator_rejects_semantic_tamper_even_with_new_hash():
    events = []
    loop, *_ = _make_loop(
        events,
        world=_ControlledWorld(events),
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-terminal-tamper")
    loop.observe()
    fluid_loop.execute_controlled_action_transaction(
        fluid_loop=loop,
        action={"joint_positions": [0.1] * 7, "joint_indices": list(range(7))},
        read_action_context=_controlled_insert_action_context,
        apply_action=lambda _value: (_ for _ in ()).throw(RuntimeError("apply")),
    )
    terminal = loop.observe()["terminal"]
    tampered = deepcopy(terminal)
    tampered["decision"]["transaction"]["application_outcome"] = "not_invoked"
    tampered["decision"]["transaction"]["requires_world_termination"] = False
    payload = dict(tampered)
    payload.pop("sha256")
    tampered["sha256"] = fluid_loop.canonical_json_sha256(payload)

    with pytest.raises(ValueError, match="controlled_terminal_transaction_invalid"):
        fluid_loop.validate_controlled_terminal_transition(tampered)


def test_controlled_particle_excursion_stops_applied_interval_same_step():
    events = []
    world = _ControlledWorld(events)
    samples = iter(
        [
            _containment(source=4),
            _containment(source=3, transit=1),
        ]
    )
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_ControlledAttachment(events, contact_slot=100),
        controlled_contact_interlock=True,
        sample_containment_after_substep=lambda: next(samples),
    )
    loop.reset_episode("episode-particle-terminal")
    loop.observe()
    _commit_controlled_test_action(loop, [])

    result = loop.observe()

    assert result["kind"] == "CONTROLLED_TERMINAL_TRANSITION"
    terminal = result["terminal"]
    assert terminal["variant"] == "applied_interval"
    assert terminal["terminal_kind"] == "PHYSICAL_PARTICLE_FAILURE"
    assert terminal["executed_substep_slots"] == [1, 2]
    assert terminal["omitted_substep_slots"] == [3, 4]
    assert world.current_time_step_index == 42
    assert events.count("world.step:False") == 2


def test_controlled_pre_roll_particle_excursion_stops_without_remaining_steps():
    events = []
    world = _ControlledWorld(events)
    samples = iter(
        [
            _containment(source=4),
            _containment(source=3, transit=1),
        ]
    )
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=_ControlledAttachment(events, contact_slot=100),
        reset_pre_roll_substeps=4,
        controlled_contact_interlock=True,
        sample_containment_after_substep=lambda: next(samples),
    )

    loop.reset_episode("episode-pre-roll-particle-terminal")
    result = loop.observe()

    assert result["kind"] == "CONTROLLED_TERMINAL_TRANSITION"
    assert result["terminal"]["variant"] == "no_action_step"
    assert result["terminal"]["terminal_kind"] == (
        "PHYSICAL_PARTICLE_FAILURE"
    )
    assert world.current_time_step_index == 42
    assert events.count("world.step:False") == 2


def test_controlled_latch_requires_same_target_on_next_action():
    events = []
    world = _ControlledWorld(events)
    attachment = _ControlledAttachment(events, contact_slot=4)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=attachment,
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-1")
    loop.observe()
    _commit_controlled_test_action(loop, [])
    loop.observe()

    action = {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))}
    changed = build_arm_target_token(
        tool_position_stage_units=[0.1, 0.2, 0.29],
        tool_orientation_wxyz=[1.0, 0.0, 0.0, 0.0],
        control_position_stage_units=[0.1, 0.2, 0.2866],
        control_orientation_wxyz=[1.0, 0.0, 0.0, 0.0],
        tool_frame="tool_center",
        control_frame="right_gripper",
        stage_units_m=1.0,
    )
    proposal = fluid_loop.validate_controlled_action_proposal(
        action=action,
        phase="PRECONTACT_SETTLE",
        semantic_action_kind="ARM_PRECONTACT_SETTLE",
        terminal_latched=False,
        finger_joint_indices=(7, 8),
        target_token=changed,
        control_index=1,
        interval_index=1,
    )
    with pytest.raises(
        RuntimeError,
        match="controlled_precontact_next_target_mismatch",
    ):
        loop.commit_controlled_action(action, proposal)


def test_persistent_precontact_uses_effective_phase_without_second_latch():
    events = []
    world = _ControlledWorld(events)
    attachment = _PhaseAwarePersistentContactAttachment(events)
    loop, *_ = _make_loop(
        events,
        world=world,
        attachment=attachment,
        controlled_contact_interlock=True,
    )
    loop.reset_episode("episode-persistent-precontact")
    loop.observe()
    token = _controlled_arm_target_token()
    _commit_controlled_test_action(loop, [], target_token=token)
    loop.observe()

    action = {"joint_positions": [0.1] * 7, "joint_indices": list(range(7))}
    proposal = fluid_loop.validate_controlled_action_proposal(
        action=action,
        phase="PRECONTACT_SETTLE",
        semantic_action_kind="ARM_PRECONTACT_SETTLE",
        terminal_latched=False,
        finger_joint_indices=(7, 8),
        target_token=token,
        control_index=1,
        interval_index=1,
    )
    commit = loop.commit_controlled_action(action, proposal)
    receipt = fluid_loop.apply_controlled_action(
        action=action,
        proposal=proposal,
        commit_record=commit,
        apply_action=lambda _action: None,
    )
    loop.confirm_controlled_action_applied(receipt)

    observation = loop.observe()

    assert observation["record"]["observation_index"] == 2
    assert len(attachment.latch_calls) == 1
    assert attachment.effective_phases == [
        "INSERT",
        "PRECONTACT_SETTLE",
        "PRECONTACT_SETTLE",
        "PRECONTACT_SETTLE",
        "PRECONTACT_SETTLE",
        "PRECONTACT_SETTLE",
        "PRECONTACT_SETTLE",
        "PRECONTACT_SETTLE",
    ]


@pytest.mark.parametrize(
    ("phase", "semantic_kind", "terminal_latched", "error"),
    [
        ("INSERT", "LIFT", False, "controlled_action_kind_invalid"),
        ("INSERT", "ARM_ALIGN", False, "controlled_action_phase_mismatch"),
        ("INSERT", "ARM_INSERT", True, "controlled_action_terminal_latched"),
        ("POURING", "POUR", False, "controlled_action_phase_invalid"),
    ],
)
def test_controlled_action_gate_rejects_before_apply_and_has_zero_physics_steps(
    phase,
    semantic_kind,
    terminal_latched,
    error,
):
    applied = []
    physics_steps = []

    with pytest.raises(RuntimeError, match=error):
        fluid_loop.apply_controlled_action(
            action={"joint_positions": [0.1] * 7},
            phase=phase,
            semantic_action_kind=semantic_kind,
            terminal_latched=terminal_latched,
            finger_joint_indices=(7, 8),
            apply_action=lambda value: applied.append(value),
        )

    assert applied == []
    assert physics_steps == []


def test_controlled_action_gate_rejects_wrong_arm_and_finger_channels():
    applied = []
    with pytest.raises(RuntimeError, match="controlled_action_channel_invalid"):
        fluid_loop.apply_controlled_action(
            action={"joint_positions": [0.1] * 9},
            phase="INSERT",
            semantic_action_kind="ARM_INSERT",
            terminal_latched=False,
            finger_joint_indices=(7, 8),
            apply_action=applied.append,
        )
    with pytest.raises(RuntimeError, match="controlled_action_channel_invalid"):
        fluid_loop.apply_controlled_action(
            action={"joint_positions": [None] * 6 + [0.02, 0.03, 0.03]},
            phase="CLOSE",
            semantic_action_kind="GRIPPER_CLOSE",
            terminal_latched=False,
            finger_joint_indices=(7, 8),
            apply_action=applied.append,
        )
    assert applied == []


def test_controlled_action_accepts_real_rmpflow_numpy_position_velocity_subset():
    action = {
        "joint_positions": np.linspace(0.1, 0.7, 7, dtype=np.float64),
        "joint_velocities": np.linspace(0.01, 0.07, 7, dtype=np.float64),
        "joint_efforts": None,
        "joint_indices": np.arange(7, dtype=np.int64),
    }

    proposal = fluid_loop.validate_controlled_action_proposal(
        action=action,
        phase="INSERT",
        semantic_action_kind="ARM_INSERT",
        terminal_latched=False,
        finger_joint_indices=(7, 8),
        target_token=_controlled_arm_target_token(),
        control_index=0,
        interval_index=0,
    )

    assert proposal["channel"] == "arm"


def test_controlled_action_rejects_implicit_arm_vector_that_reaches_finger_joint():
    with pytest.raises(RuntimeError, match="controlled_action_channel_invalid"):
        fluid_loop.validate_controlled_action_proposal(
            action={
                "joint_positions": np.linspace(0.1, 0.8, 8),
                "joint_velocities": np.zeros(8),
            },
            phase="INSERT",
            semantic_action_kind="ARM_INSERT",
            terminal_latched=False,
            finger_joint_indices=(7, 8),
            target_token=_controlled_arm_target_token(),
            control_index=0,
            interval_index=0,
        )


def test_controlled_finger_action_must_match_target_token_bytes():
    positions = [None] * 9
    positions[7:] = [0.03, 0.03]
    token = build_finger_target_token(
        joint_indices=(7, 8),
        joint_targets=(0.02, 0.02),
    )

    with pytest.raises(RuntimeError, match="controlled_action_target_value_mismatch"):
        fluid_loop.validate_controlled_action_proposal(
            action={"joint_positions": positions},
            phase="CLOSE",
            semantic_action_kind="GRIPPER_CLOSE",
            terminal_latched=False,
            finger_joint_indices=(7, 8),
            target_token=token,
            control_index=0,
            interval_index=0,
        )


def test_substep_spill_before_pour_cannot_be_hidden_by_terminal_transfer():
    samples = iter(
        [
            _containment(source=4),
            _containment(source=3, transit=1),
            _containment(source=4, pour_started=True),
            _containment(target=4),
        ]
    )
    loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: next(samples),
    )
    loop.reset_episode("episode-1")
    loop.observe()
    loop.commit_action(None)
    loop.observe()

    result = loop.finalize_episode(controller_completed=True)
    summary = result["cumulative_containment"]

    assert result["terminal_expert_transfer_passed"] is True
    assert result["cumulative_containment_valid"] is False
    assert result["expert_episode_accepted"] is False
    assert summary["substep_sample_count"] == 4
    assert summary["substep_sampling_complete"] is True
    assert summary["source_min"] == 0
    assert summary["non_source_max"]["target"] == 4
    assert summary["pre_pour_source_min"] == 3
    assert summary["pre_pour_non_source_max"]["transit"] == 1
    assert summary["first_spill_physics_step"] == 42
    assert summary["ever_spilled"] is True


def test_reset_starts_fresh_cumulative_summary_without_mutating_sealed_attempt():
    samples = iter(
        [
            _containment(source=3, transit=1),
            _containment(source=4),
            _containment(source=4, pour_started=True),
            _containment(target=4),
        ]
    )
    loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: next(samples),
    )
    loop.reset_episode("episode-1")
    loop.observe()
    loop.commit_action(None)
    loop.observe()
    first = loop.finalize_episode(controller_completed=True)
    first_summary = deepcopy(first["cumulative_containment"])

    loop.score_particles = lambda positions: _terminal_score(source=4, target=0)
    loop.reset_episode("episode-2")
    second = loop.observe()

    assert first["cumulative_containment"] == first_summary
    assert first_summary["pre_pour_source_min"] == 3
    assert second["record"]["cumulative_containment"]["source_min"] == 4
    assert second["record"]["cumulative_containment"][
        "first_spill_physics_step"
    ] is None


def test_cumulative_below_table_and_nonfinite_reject_recovered_terminal_frame():
    samples = iter(
        [
            _containment(target=3, below_table=1),
            _containment(target=3, nonfinite=1),
            _containment(target=4),
            _containment(target=4),
        ]
    )
    loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: next(samples),
    )
    loop.reset_episode("episode-1")
    loop.observe()
    loop.mark_pour_started()
    loop.commit_action(None)
    loop.observe()

    result = loop.finalize_episode(controller_completed=True)

    assert result["cumulative_containment"]["below_table_max"] == 1
    assert result["cumulative_containment"]["nonfinite_max"] == 1
    assert result["cumulative_containment_valid"] is False
    assert result["expert_episode_accepted"] is False


def test_post_pour_tabletop_splash_is_reported_but_not_alone_rejected():
    samples = iter(
        [
            _containment(target=3, tabletop_spill=1),
            _containment(target=4),
            _containment(target=4),
            _containment(target=4),
        ]
    )
    loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: next(samples),
    )
    loop.reset_episode("episode-1")
    loop.observe()
    loop.mark_pour_started()
    loop.commit_action(None)
    loop.observe()

    result = loop.finalize_episode(controller_completed=True)

    assert result["cumulative_containment"]["non_source_max"][
        "tabletop_spill"
    ] == 1
    assert result["cumulative_containment"]["ever_spilled"] is True
    assert result["cumulative_containment_valid"] is True
    assert result["expert_episode_accepted"] is True


def test_expert_acceptance_requires_substep_sampling_authority():
    loop, *_ = _make_loop([])
    loop.reset_episode("episode-1")
    loop.observe()
    loop.mark_pour_started()
    loop.commit_action(None)
    loop.observe()

    result = loop.finalize_episode(controller_completed=True)

    assert result["terminal_expert_transfer_passed"] is True
    assert result["cumulative_containment"][
        "substep_sampling_configured"
    ] is False
    assert result["cumulative_containment_valid"] is False
    assert result["expert_episode_accepted"] is False


def test_expert_acceptance_requires_ninety_percent_terminal_target():
    loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: _containment(source=4),
    )
    loop.score_particles = lambda positions: _terminal_score(source=1, target=3)
    loop.reset_episode("episode-1")
    loop.mark_pour_started()
    loop.observe()

    result = loop.finalize_episode(controller_completed=True)

    assert result["terminal_expert_transfer_passed"] is True
    assert result["minimum_expert_target_particles"] == 4
    assert result["final_target_particles"] == 3
    assert result["expert_episode_accepted"] is False


def test_expert_acceptance_requires_fixed_partition_total():
    loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: _containment(source=4),
    )
    mismatched = _terminal_score(source=0, target=4, transit=1)
    mismatched["partition_complete"] = True
    loop.score_particles = lambda positions: mismatched
    loop.reset_episode("episode-1")
    loop.mark_pour_started()
    loop.observe()

    result = loop.finalize_episode(controller_completed=True)

    assert result["cumulative_containment"]["partition_total_max"] == 5
    assert result["cumulative_containment"]["partition_integrity_valid"] is False
    assert result["expert_episode_accepted"] is False


def test_final_success_keeps_controller_and_raw_fluid_gates_separate():
    before_loop, *_ = _make_loop([])
    before_loop.reset_episode("episode-before-transfer")
    before_loop.observe()
    before_transfer = before_loop.finalize_episode(controller_completed=True)

    assert before_transfer["controller_completed"] is True
    assert before_transfer["task_transfer_passed"] is False
    assert before_transfer["terminal_expert_transfer_passed"] is False
    assert before_transfer["expert_episode_accepted"] is False
    assert before_transfer["success"] is False
    assert before_transfer["attempt_status"] == "completed"

    after_loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: _containment(target=4),
    )
    after_loop.reset_episode("episode-after-transfer")
    after_loop.observe()
    after_loop.mark_pour_started()
    after_loop.commit_action(None)
    after_loop.observe()
    after_transfer = after_loop.finalize_episode(controller_completed=True)

    assert after_transfer["controller_completed"] is True
    assert after_transfer["fluid_transfer_passed"] is True
    assert after_transfer["task_transfer_passed"] is True
    assert after_transfer["terminal_expert_transfer_passed"] is True
    assert after_transfer["expert_attachment_valid"] is True
    assert after_transfer["source_visual_sync_valid"] is True
    assert after_transfer["cumulative_containment_valid"] is True
    assert after_transfer["expert_episode_accepted"] is True
    assert after_transfer["success"] is True
    assert after_transfer["attempt_status"] == "completed"

    failed_loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: _containment(target=4),
    )
    failed_loop.reset_episode("episode-controller-failed")
    failed_loop.observe()
    failed_loop.mark_pour_started()
    failed_loop.commit_action(None)
    failed_loop.observe()
    controller_failed = failed_loop.finalize_episode(controller_completed=False)

    assert controller_failed["task_transfer_passed"] is True
    assert controller_failed["success"] is False
    assert controller_failed["expert_episode_accepted"] is False
    assert controller_failed["attempt_status"] == "failed"


def _probe_control_evidence(profile="native_expert_v1"):
    if profile == "native_expert_v1":
        pick = {
            "event": 5,
            "last_emitted_event": 4,
            "close_command_emitted": True,
            "lift_command_emitted": False,
        }
    else:
        pick = {
            "phase": "CONTACT_SETTLE",
            "phase_history": ["PREGRASP", "CLOSE", "CONTACT_SETTLE"],
            "close_command_emitted": True,
            "probe_completed": True,
        }
    return {
        "mode": "collect",
        "source_ownership": "contact_friction_dynamic_v1",
        "expert_control_profile": profile,
        "execution_mode": "contact_acquisition_probe_v1",
        "contact_acquisition_probe": True,
        "contact_grasp_required": True,
        "native_pick": deepcopy(pick) if profile == "native_expert_v1" else None,
        "contact_pick": deepcopy(pick) if profile == "contact_pick_v1" else None,
        "pour_forward_invocation_count": 0,
    }


def _probe_attachment_evidence():
    return {
        "mode": "contact_friction_dynamic_v1",
        "attached": True,
        "source_dynamic": True,
        "mechanical_attachment_used": False,
        "source_pose_write_count_after_play": 0,
        "kinematic_target_update_count": 0,
        "close_command_observed": True,
        "lift_command_observed": False,
        "probe_qualified_now": True,
        "qualified": True,
        "expert_grasp_valid": True,
        "failure_reason": None,
        "source_writer_audit": {
            "coverage_complete": True,
            "valid": True,
            "call_count": 0,
        },
    }


def _finalize_contact_probe(
    *,
    control_evidence=None,
    attachment_evidence=None,
    terminal_phase="FINISHED",
    terminal_action=None,
    containment_samples=None,
    sync_source_visual_state=None,
):
    samples = None if containment_samples is None else iter(containment_samples)
    loop, _, _, attachment, *_ = _make_loop(
        [],
        sample_containment_after_substep=(
            (lambda: _containment(source=4))
            if samples is None
            else (lambda: next(samples))
        ),
        sync_source_visual_state=sync_source_visual_state,
        expected_source_ownership="contact_friction_dynamic_v1",
    )
    loop.score_particles = lambda positions: {
        **_terminal_score(source=4, target=0),
        "fluid_transfer_passed": False,
        "strict_zero_spill_transfer_passed": False,
        "task_transfer_passed": False,
        "expert_transfer_passed": False,
    }
    attachment_record = deepcopy(
        _probe_attachment_evidence()
        if attachment_evidence is None
        else attachment_evidence
    )
    attachment.record = lambda: deepcopy(attachment_record)
    loop.reset_episode("contact-probe")
    loop.observe()
    loop.commit_action(None)
    loop.observe()
    return loop.finalize_episode(
        controller_completed=True,
        acceptance_mode="contact_acquisition_probe_v1",
        controller_evidence=deepcopy(
            _probe_control_evidence()
            if control_evidence is None
            else control_evidence
        ),
        terminal_phase=terminal_phase,
        terminal_action=terminal_action,
    )


@pytest.mark.parametrize("profile", ["native_expert_v1", "contact_pick_v1"])
def test_contact_acquisition_probe_accepts_supported_combined_contract(profile):
    result = _finalize_contact_probe(
        control_evidence=_probe_control_evidence(profile)
    )

    assert result["acceptance_mode"] == "contact_acquisition_probe_v1"
    assert result["contact_acquisition_probe_accepted"] is True
    assert result["task_transfer_passed"] is False
    assert result["expert_episode_accepted"] is False
    assert result["success"] is True
    assert result["attempt_status"] == "completed"
    assert result["probe_control_contract"]["id"] == (
        "contact_acquisition_probe_control_v1"
    )
    assert result["probe_control_contract"]["schema_version"] == 1
    assert result["probe_control_contract"]["valid"] is True
    assert all(result["probe_control_contract"]["checks"].values())


@pytest.mark.parametrize("evidence_source", ["controller", "attachment"])
def test_contact_acquisition_probe_rejects_each_missing_close(evidence_source):
    control = _probe_control_evidence()
    attachment = _probe_attachment_evidence()
    if evidence_source == "controller":
        control["native_pick"].pop("close_command_emitted")
    else:
        attachment.pop("close_command_observed")

    result = _finalize_contact_probe(
        control_evidence=control,
        attachment_evidence=attachment,
    )

    assert result["contact_acquisition_probe_accepted"] is False
    assert result["success"] is False


@pytest.mark.parametrize("evidence_source", ["controller", "attachment"])
def test_contact_acquisition_probe_rejects_each_lift_signal(evidence_source):
    control = _probe_control_evidence()
    attachment = _probe_attachment_evidence()
    if evidence_source == "controller":
        control["native_pick"]["lift_command_emitted"] = True
    else:
        attachment["lift_command_observed"] = True

    result = _finalize_contact_probe(
        control_evidence=control,
        attachment_evidence=attachment,
    )

    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_acquisition_probe_rejects_stale_latched_qualification():
    attachment = _probe_attachment_evidence()
    attachment["probe_qualified_now"] = False
    assert attachment["qualified"] is True
    assert attachment["expert_grasp_valid"] is True

    result = _finalize_contact_probe(attachment_evidence=attachment)

    assert result["dynamic_grasp_contract_valid"] is True
    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_acquisition_probe_rejects_observed_writer_call():
    attachment = _probe_attachment_evidence()
    attachment["source_writer_audit"]["call_count"] = 1

    result = _finalize_contact_probe(attachment_evidence=attachment)

    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_acquisition_probe_rejects_incomplete_writer_audit():
    attachment = _probe_attachment_evidence()
    attachment["source_writer_audit"]["coverage_complete"] = False

    result = _finalize_contact_probe(attachment_evidence=attachment)

    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_acquisition_probe_rejects_invalid_writer_audit():
    attachment = _probe_attachment_evidence()
    attachment["source_writer_audit"]["valid"] = False

    result = _finalize_contact_probe(attachment_evidence=attachment)

    assert result["contact_acquisition_probe_accepted"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "infer"),
        ("expert_control_profile", "stabilized_online_fluid_v1"),
        ("execution_mode", "production_pour_v1"),
        ("source_ownership", "gripper_attached_kinematic_vessel"),
    ],
)
def test_contact_acquisition_probe_rejects_wrong_mode_or_profile(field, value):
    control = _probe_control_evidence()
    control[field] = value

    result = _finalize_contact_probe(control_evidence=control)

    assert result["contact_acquisition_probe_accepted"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [("pour_forward_invocation_count", 1)],
)
def test_contact_acquisition_probe_rejects_pour_forward_or_emission(field, value):
    control = _probe_control_evidence()
    control[field] = value

    result = _finalize_contact_probe(control_evidence=control)

    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_specific_probe_rejects_lift_phase_history():
    control = _probe_control_evidence("contact_pick_v1")
    control["contact_pick"]["phase_history"].append("LIFT")

    result = _finalize_contact_probe(control_evidence=control)

    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_specific_probe_rejects_missing_phase_history():
    control = _probe_control_evidence("contact_pick_v1")
    control["contact_pick"].pop("phase_history")

    result = _finalize_contact_probe(control_evidence=control)

    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_acquisition_probe_rejects_terminal_action():
    result = _finalize_contact_probe(terminal_action={"joint_positions": [0.0]})

    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_acquisition_probe_rejects_nonfinished_outer_phase():
    result = _finalize_contact_probe(terminal_phase="PICKING")

    assert result["contact_acquisition_probe_accepted"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "gripper_attached_kinematic_vessel"),
        ("source_dynamic", False),
        ("mechanical_attachment_used", True),
        ("kinematic_target_update_count", 1),
    ],
)
def test_contact_acquisition_probe_rejects_non_dynamic_contract(field, value):
    attachment = _probe_attachment_evidence()
    attachment[field] = value

    result = _finalize_contact_probe(attachment_evidence=attachment)

    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_acquisition_probe_rejects_invalid_visual_sync():
    result = _finalize_contact_probe(
        sync_source_visual_state=lambda: {"valid": False}
    )

    assert result["contact_acquisition_probe_accepted"] is False


def test_contact_acquisition_probe_rejects_recovered_substep_containment():
    result = _finalize_contact_probe(
        containment_samples=[
            _containment(source=4),
            _containment(source=3, transit=1),
            _containment(source=4),
            _containment(source=4),
        ]
    )

    assert result["cumulative_containment"]["pre_pour_source_min"] == 3
    assert result["cumulative_containment"]["pre_pour_non_source_max"][
        "transit"
    ] == 1
    assert result["cumulative_containment_valid"] is False
    assert result["contact_acquisition_probe_accepted"] is False


def test_production_acceptance_ignores_probe_only_terminal_contract():
    loop, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: _containment(target=4),
    )
    loop.reset_episode("production-pour")
    loop.observe()
    loop.mark_pour_started()
    loop.commit_action(None)
    loop.observe()

    result = loop.finalize_episode(
        controller_completed=True,
        acceptance_mode="production_pour_v1",
        controller_evidence={},
        terminal_phase="PICKING",
        terminal_action=object(),
    )

    assert result["expert_episode_accepted"] is True
    assert result["success"] is True
    assert "probe_control_contract" not in result


def test_invalid_expert_attachment_rejects_h5_without_changing_task_score():
    events: list[str] = []
    loop, _, _, attachment, *_ = _make_loop(events)
    loop.reset_episode("episode-1")
    loop.observe()
    loop.commit_action(None)
    loop.observe()
    attachment.record = lambda: {
        "mode": "gripper_attached_kinematic_vessel",
        "attached": True,
        "expert_attachment_valid": False,
    }

    result = loop.finalize_episode(controller_completed=True)

    assert result["task_transfer_passed"] is True
    assert result["success"] is True
    assert result["expert_transfer_passed"] is True
    assert result["expert_attachment_valid"] is False
    assert result["expert_episode_accepted"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "gripper_attached_kinematic_vessel"),
        ("source_dynamic", False),
        ("mechanical_attachment_used", True),
        ("source_pose_write_count_after_play", 1),
        ("kinematic_target_update_count", 1),
        ("qualified", False),
        ("expert_grasp_valid", False),
        ("failure_reason", "grasp_lost"),
    ],
)
def test_dynamic_expert_acceptance_requires_exact_terminal_physics_record(
    field,
    value,
):
    loop, _, _, attachment, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: _containment(target=4),
        expected_source_ownership="contact_friction_dynamic_v1",
    )
    record = {
        "mode": "contact_friction_dynamic_v1",
        "source_dynamic": True,
        "mechanical_attachment_used": False,
        "source_pose_write_count_after_play": 0,
        "kinematic_target_update_count": 0,
        "qualified": True,
        "expert_grasp_valid": True,
        "failure_reason": None,
    }
    record[field] = value
    attachment.record = lambda: dict(record)
    loop.reset_episode("dynamic-episode")
    loop.observe()
    loop.mark_pour_started()
    loop.commit_action(None)
    loop.observe()

    result = loop.finalize_episode(controller_completed=True)

    assert result["dynamic_grasp_contract_valid"] is False
    assert result["expert_grasp_valid"] is False
    assert result["expert_episode_accepted"] is False
    assert result["task_transfer_passed"] is True


def test_dynamic_expert_acceptance_accepts_exact_terminal_physics_record():
    loop, _, _, attachment, *_ = _make_loop(
        [],
        sample_containment_after_substep=lambda: _containment(target=4),
        expected_source_ownership="contact_friction_dynamic_v1",
    )
    attachment.record = lambda: {
        "mode": "contact_friction_dynamic_v1",
        "source_dynamic": True,
        "mechanical_attachment_used": False,
        "source_pose_write_count_after_play": 0,
        "kinematic_target_update_count": 0,
        "qualified": True,
        "expert_grasp_valid": True,
        "failure_reason": None,
    }
    loop.reset_episode("dynamic-episode")
    loop.observe()
    loop.mark_pour_started()
    loop.commit_action(None)
    loop.observe()

    result = loop.finalize_episode(controller_completed=True)

    assert result["dynamic_grasp_contract_valid"] is True
    assert result["expert_grasp_valid"] is True
    assert result["expert_episode_accepted"] is True


def test_invalid_source_visual_sync_rejects_expert_episode_without_changing_task_score():
    events: list[str] = []
    sync_records = [
        {"policy": "visual_mesh_parent_delta_v1", "valid": True},
        {"policy": "visual_mesh_parent_delta_v1", "valid": False},
    ]

    def sync_source_visual_state():
        events.append("sync_source_visual")
        return sync_records.pop(0)

    loop, *_ = _make_loop(
        events,
        sync_source_visual_state=sync_source_visual_state,
    )
    loop.reset_episode("episode-1")
    first = loop.observe()
    loop.commit_action(None)
    second = loop.observe()

    result = loop.finalize_episode(controller_completed=True)

    assert first["record"]["source_visual_sync"]["valid"] is True
    assert second["record"]["source_visual_sync"]["valid"] is False
    sync_indices = [
        index
        for index, event in enumerate(events)
        if event == "sync_source_visual"
    ]
    read_indices = [
        index for index, event in enumerate(events) if event == "read_particles"
    ]
    last_physics_step = max(
        index
        for index, event in enumerate(events)
        if event == "world.step:False"
    )
    assert sync_indices[0] < read_indices[0]
    assert last_physics_step < sync_indices[1] < read_indices[1]
    assert result["task_transfer_passed"] is True
    assert result["success"] is True
    assert result["source_visual_sync_valid"] is False
    assert result["expert_episode_accepted"] is False


def test_visual_sync_failure_cannot_be_hidden_by_a_later_valid_frame():
    sync_records = iter(
        [
            {"policy": "visual_mesh_parent_delta_v1", "valid": False},
            {"policy": "visual_mesh_parent_delta_v1", "valid": True},
        ]
    )
    loop, *_ = _make_loop(
        [],
        sync_source_visual_state=lambda: next(sync_records),
    )
    loop.reset_episode("episode-1")
    loop.observe()
    loop.commit_action(None)
    loop.observe()

    result = loop.finalize_episode(controller_completed=True)

    assert result["source_visual_sync_valid"] is False
    assert result["expert_episode_accepted"] is False


def test_attempt_limit_is_separate_from_accepted_episode_count():
    assert fluid_loop.attempt_limit_reached(0, 3) is False
    assert fluid_loop.attempt_limit_reached(2, 3) is False
    assert fluid_loop.attempt_limit_reached(3, 3) is True
    with pytest.raises(ValueError, match="maximum_attempts_invalid"):
        fluid_loop.attempt_limit_reached(0, 0)


def test_online_fluid_run_completion_counts_collect_acceptance_and_infer_attempts():
    assert fluid_loop.online_fluid_run_complete(
        mode="collect",
        completed_attempts=1,
        accepted_episodes=0,
        maximum_episodes=1,
        maximum_attempts=3,
    ) is False
    assert fluid_loop.online_fluid_run_complete(
        mode="collect",
        completed_attempts=1,
        accepted_episodes=1,
        maximum_episodes=1,
        maximum_attempts=3,
    ) is True
    assert fluid_loop.online_fluid_run_complete(
        mode="infer",
        completed_attempts=1,
        accepted_episodes=0,
        maximum_episodes=1,
        maximum_attempts=3,
    ) is True
    assert fluid_loop.online_fluid_run_complete(
        mode="collect",
        completed_attempts=3,
        accepted_episodes=0,
        maximum_episodes=1,
        maximum_attempts=3,
    ) is True


def test_observation_limit_reason_terminalizes_global_or_episode_limit():
    assert fluid_loop.observation_limit_failure_reason(
        per_episode_limit_hit=False,
        global_limit_hit=False,
    ) is None
    assert fluid_loop.observation_limit_failure_reason(
        per_episode_limit_hit=True,
        global_limit_hit=False,
    ) == "max_observations_per_episode_reached"
    assert fluid_loop.observation_limit_failure_reason(
        per_episode_limit_hit=False,
        global_limit_hit=True,
    ) == "max_fluid_observations_reached"


def test_observation_limit_boundary_is_distinct_from_actual_termination():
    assert fluid_loop.observation_limit_termination_reason(
        controller_done=True,
        per_episode_limit_hit=True,
        global_limit_hit=False,
    ) is None
    assert fluid_loop.observation_limit_termination_reason(
        controller_done=False,
        per_episode_limit_hit=True,
        global_limit_hit=False,
    ) == "max_observations_per_episode_reached"
    assert fluid_loop.observation_limit_termination_reason(
        controller_done=False,
        per_episode_limit_hit=False,
        global_limit_hit=False,
    ) is None


def test_task_reset_precedes_controller_creation_and_later_controller_reset():
    events = []

    class Resettable:
        def __init__(self, name):
            self.name = name

        def reset(self):
            events.append(f"{self.name}.reset")

    task = Resettable("task")
    controller = fluid_loop.initialize_controller_after_task_reset(
        task,
        lambda: events.append("controller.create") or Resettable("controller"),
    )
    assert events == ["task.reset", "controller.create"]

    events.clear()
    fluid_loop.reset_task_then_controller(task, controller)
    assert events == ["task.reset", "controller.reset"]


def test_append_observation_evidence_writes_compact_jsonl(tmp_path):
    events: list[str] = []
    loop, *_ = _make_loop(events)
    loop.reset_episode("episode-1")
    observation = loop.observe()

    path = tmp_path / "observations.jsonl"
    payload = fluid_loop.append_fluid_observation_evidence(path, observation)

    assert payload == {
        "record": observation["record"],
        "score": observation["score"],
        "attachment": observation["attachment"],
    }
    assert "state" not in payload
    assert json.loads(path.read_text(encoding="utf-8")) == payload

    with pytest.raises(RuntimeError, match="fluid_evidence_duplicate"):
        fluid_loop.append_fluid_observation_evidence(path, observation)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1

    conflicting_sample = deepcopy(observation)
    conflicting_sample["record"]["sample_index"] += 1000
    with pytest.raises(RuntimeError, match="fluid_evidence_duplicate"):
        fluid_loop.append_fluid_observation_evidence(path, conflicting_sample)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_observation_ledger_accepts_reused_episode_only_for_unique_attempt(tmp_path):
    first_loop, *_ = _make_loop([])
    first_loop.reset_episode("episode-reused")
    first = first_loop.observe()
    second_loop, *_ = _make_loop([])
    second_loop.reset_episode("episode-reused")
    second = second_loop.observe()
    path = tmp_path / "observations.jsonl"

    fluid_loop.append_fluid_observation_evidence(path, first)
    reused_sample = deepcopy(second)
    reused_sample["record"]["sample_index"] = first["record"]["sample_index"]
    with pytest.raises(RuntimeError, match="fluid_evidence_duplicate"):
        fluid_loop.append_fluid_observation_evidence(path, reused_sample)
    fluid_loop.append_fluid_observation_evidence(path, second)

    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 2
    assert records[0]["record"]["attempt_id"] != records[1]["record"][
        "attempt_id"
    ]


def test_evidence_ledger_rejects_malformed_existing_jsonl_without_appending(tmp_path):
    path = tmp_path / "observations.jsonl"
    original = "{not-json}\n"
    path.write_text(original, encoding="utf-8")
    loop, *_ = _make_loop([])
    loop.reset_episode("episode-1")
    observation = loop.observe()

    with pytest.raises(RuntimeError, match="fluid_evidence_jsonl_invalid"):
        fluid_loop.append_fluid_observation_evidence(path, observation)

    assert path.read_text(encoding="utf-8") == original


def test_append_episode_evidence_preserves_terminal_evaluation(tmp_path):
    loop, *_ = _make_loop([])
    loop.reset_episode("episode-0000")
    loop.observe()
    evaluation = {
        **loop.finalize_episode(controller_completed=False),
        "episode_id": "episode-0000",
        "performance": {"episode_wall_fps": 2.5},
    }
    path = tmp_path / "episodes.jsonl"

    payload = fluid_loop.append_fluid_episode_evidence(path, evaluation)

    assert payload == evaluation
    assert json.loads(path.read_text(encoding="utf-8")) == evaluation

    with pytest.raises(RuntimeError, match="fluid_evidence_duplicate"):
        fluid_loop.append_fluid_episode_evidence(path, evaluation)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_prepare_evidence_directory_claims_empty_and_rejects_any_reuse(tmp_path):
    new_path = tmp_path / "new-evidence"
    claimed = fluid_loop.prepare_fluid_evidence_directory(new_path)
    assert claimed == new_path
    assert claimed.is_dir()
    assert any(claimed.iterdir())

    empty_path = tmp_path / "empty-evidence"
    empty_path.mkdir()
    assert fluid_loop.prepare_fluid_evidence_directory(empty_path) == empty_path

    reused_path = tmp_path / "reused-evidence"
    reused_path.mkdir()
    (reused_path / ".hidden").write_text("existing", encoding="utf-8")
    with pytest.raises(RuntimeError, match="fluid_evidence_directory_not_empty"):
        fluid_loop.prepare_fluid_evidence_directory(reused_path)

    file_path = tmp_path / "not-a-directory"
    file_path.write_text("existing", encoding="utf-8")
    with pytest.raises(RuntimeError, match="fluid_evidence_path_not_directory"):
        fluid_loop.prepare_fluid_evidence_directory(file_path)


@pytest.mark.parametrize("maximum", [0, -1, True, 1.5])
def test_observation_limit_rejects_invalid_values(maximum):
    with pytest.raises(ValueError, match="maximum_observations_invalid"):
        fluid_loop.observation_limit_reached(1, maximum)


def test_observation_limit_is_disabled_or_exact():
    assert fluid_loop.observation_limit_reached(100, None) is False
    assert fluid_loop.observation_limit_reached(1, 2) is False
    assert fluid_loop.observation_limit_reached(2, 2) is True


def test_model_camera_video_frame_uses_exact_hashed_arrays_not_display_aliases():
    camera_1 = np.full((3, 4, 5), 17, dtype=np.uint8)
    camera_2 = np.full((3, 4, 5), 31, dtype=np.uint8)
    state = {
        "camera_data": {
            "camera_1_rgb": camera_1,
            "camera_2_rgb": camera_2,
        },
        "camera_display": {
            "camera_1": np.full((3, 4, 5), 99, dtype=np.uint8),
            "camera_2": np.full((3, 4, 5), 101, dtype=np.uint8),
        },
    }

    frame = fluid_loop.model_camera_video_rgb(
        state,
        camera_keys=("camera_1_rgb", "camera_2_rgb"),
        expected_shape=(3, 4, 5),
    )

    assert frame.shape == (4, 10, 3)
    assert frame.dtype == np.uint8
    assert np.all(frame[:, :5] == 17)
    assert np.all(frame[:, 5:] == 31)
    np.testing.assert_array_equal(camera_1, np.full((3, 4, 5), 17, dtype=np.uint8))


def test_video_fps_matches_observation_rate():
    assert fluid_loop.observation_video_fps(1 / 30) == 30.0
    with pytest.raises(ValueError, match="rendering_dt_invalid"):
        fluid_loop.observation_video_fps(0.0)
