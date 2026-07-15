from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from utils import fluid_evaluation_loop as fluid_loop


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


def _make_loop(
    events: list[str],
    *,
    world: _World | None = None,
    task: _Task | None = None,
    adapt_state=None,
    sync_source_visual_state=None,
):
    world = world or _World(events)
    task = task or _Task(events)
    attachment = _Attachment(events)
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
        camera_contract={
            "id": "test_camera_contract_v1",
            "sha256": "a" * 64,
        },
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
    assert action_observation["score"]["fluid_transfer_passed"] is True
    np.testing.assert_array_equal(scored[1], reconstructed[1])
    assert action_observation["attachment"]["mode"] == (
        "gripper_attached_kinematic_vessel"
    )


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


def test_final_success_keeps_controller_and_raw_fluid_gates_separate():
    events: list[str] = []
    loop, *_ = _make_loop(events)
    loop.reset_episode("episode-1")
    loop.observe()

    before_transfer = loop.finalize_episode(controller_completed=True)
    assert before_transfer == {
        "controller_completed": True,
        "fluid_transfer_passed": False,
        "strict_zero_spill_transfer_passed": False,
        "task_transfer_passed": False,
        "expert_transfer_passed": False,
        "expert_attachment_valid": True,
        "source_visual_sync_valid": True,
        "expert_episode_accepted": False,
        "success": False,
    }

    loop.commit_action(None)
    loop.observe()
    after_transfer = loop.finalize_episode(controller_completed=True)
    assert after_transfer == {
        "controller_completed": True,
        "fluid_transfer_passed": True,
        "strict_zero_spill_transfer_passed": True,
        "task_transfer_passed": True,
        "expert_transfer_passed": True,
        "expert_attachment_valid": True,
        "source_visual_sync_valid": True,
        "expert_episode_accepted": True,
        "success": True,
    }

    controller_failed = loop.finalize_episode(controller_completed=False)
    assert controller_failed["task_transfer_passed"] is True
    assert controller_failed["success"] is False
    assert controller_failed["expert_episode_accepted"] is False


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


def test_attempt_limit_is_separate_from_accepted_episode_count():
    assert fluid_loop.attempt_limit_reached(0, 3) is False
    assert fluid_loop.attempt_limit_reached(2, 3) is False
    assert fluid_loop.attempt_limit_reached(3, 3) is True
    with pytest.raises(ValueError, match="maximum_attempts_invalid"):
        fluid_loop.attempt_limit_reached(0, 0)


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

    fluid_loop.append_fluid_observation_evidence(path, observation)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


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
