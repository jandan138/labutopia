from __future__ import annotations

import hashlib
from dataclasses import replace

import numpy as np
import pytest

from utils import online_fluid_surface as online


def _positions(count: int = 4, *, offset: float = 0.0) -> np.ndarray:
    values = np.arange(count * 3, dtype=np.float64).reshape(count, 3) * 0.001
    values[:, 0] += offset
    return values


def _mesh(tag: str = "a", *, topology: int = 0) -> dict:
    if topology == 0:
        vertices = np.asarray(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32
        )
        faces = np.asarray([[0, 1, 2]], dtype=np.int32)
    else:
        vertices = np.asarray(
            [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
            dtype=np.float32,
        )
        faces = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    normals = np.tile(np.asarray([[0, 0, 1]], dtype=np.float32), (len(vertices), 1))
    return {
        "vertices": vertices,
        "faces": faces,
        "normals": normals,
        "geometry_sha256": hashlib.sha256(tag.encode("ascii")).hexdigest(),
        "diagnostics": {"component_count": 1},
    }


def _transition(
    observation_index: int,
    *,
    episode_id: str = "episode-1",
    base_logical_step: int = 20,
    base_integration_step: int = 80,
) -> online.ObservationTransition:
    if observation_index == 0:
        return online.ObservationTransition(
            episode_id=episode_id,
            observation_index=0,
            caused_by_action_index=None,
            logical_step_before=base_logical_step,
            logical_step_after=base_logical_step,
            integration_step_before=base_integration_step,
            integration_step_after=base_integration_step,
            simulation_time_before=base_integration_step / 120.0,
            simulation_time_after=base_integration_step / 120.0,
        )
    return online.ObservationTransition(
        episode_id=episode_id,
        observation_index=observation_index,
        caused_by_action_index=observation_index - 1,
        logical_step_before=base_logical_step + observation_index - 1,
        logical_step_after=base_logical_step + observation_index,
        integration_step_before=base_integration_step + 4 * (observation_index - 1),
        integration_step_after=base_integration_step + 4 * observation_index,
        simulation_time_before=(base_integration_step + 4 * (observation_index - 1))
        / 120.0,
        simulation_time_after=(base_integration_step + 4 * observation_index)
        / 120.0,
        action_sha256=hashlib.sha256(
            f"action-{observation_index - 1}".encode("ascii")
        ).hexdigest(),
    )


def _render_record(token: online.SurfaceFrameToken) -> dict:
    return {
        "render_token": f"render-{token.episode_id}-{token.observation_index}",
        "surface_token": token.identity,
        "logical_steps_before": token.logical_step_after,
        "logical_steps_after": token.logical_step_after,
        "integration_steps_before": token.integration_step_after,
        "integration_steps_after": token.integration_step_after,
        "timeline_time_before": token.simulation_time_after,
        "timeline_time_after": token.simulation_time_after,
    }


def _runtime(events: list[str], *, mesh_topologies: list[int] | None = None):
    topology_queue = list(mesh_topologies or [0, 0, 0])

    def reconstruct(positions):
        events.append("reconstruct")
        assert isinstance(positions, np.ndarray)
        return _mesh(chr(ord("a") + len(events)), topology=topology_queue.pop(0))

    def author(mesh, token):
        events.append("author")
        assert token.position_sha256 == online.canonical_position_sha256(
            token.positions
        )
        return {
            "vertex_count": len(mesh["vertices"]),
            "face_count": len(mesh["faces"]),
            "surface_token": token.identity,
        }

    def invalidate(reason):
        events.append(f"invalidate:{reason}")

    def render(token):
        events.append("render")
        return _render_record(token)

    def capture(token, render_record):
        events.append("capture")
        assert render_record["render_token"].endswith(
            str(token.observation_index)
        )
        value = 20 + token.observation_index
        return {
            "camera_1_rgb": np.full((4, 4, 3), value, dtype=np.uint8),
            "camera_2_rgb": np.full((4, 4, 3), value + 1, dtype=np.uint8),
        }

    return online.OnlineFluidSurfaceRuntime(
        expected_particle_count=4,
        physics_substeps_per_observation=4,
        physics_substep_dt=1.0 / 120.0,
        reconstruct=reconstruct,
        author_surface=author,
        invalidate_surface=invalidate,
        render_surface=render,
        capture_cameras=capture,
    )


class _Attribute:
    def __init__(self, value):
        self.value = value

    def Get(self):
        return self.value


class _Prim:
    def __init__(self, simulation_points=None, display_points=None):
        self.simulation_points = simulation_points
        self.display_points = display_points

    def IsValid(self):
        return True

    def GetAttribute(self, name):
        if name == "physxParticle:simulationPoints" and self.simulation_points is not None:
            return _Attribute(self.simulation_points)
        if name == "points" and self.display_points is not None:
            return _Attribute(self.display_points)
        return None


class _Stage:
    def __init__(self, prim):
        self.prim = prim

    def GetPrimAtPath(self, path):
        assert path == "/World/Fluid/Particles"
        return self.prim


def test_strict_reader_accepts_only_exact_finite_simulation_points():
    expected = _positions()
    stage = _Stage(_Prim(simulation_points=expected.tolist()))

    actual = online.read_strict_simulation_points(
        stage,
        "/World/Fluid/Particles",
        expected_particle_count=4,
    )

    assert actual.dtype == np.float64
    assert actual.flags.c_contiguous
    np.testing.assert_array_equal(actual, expected)


def test_strict_reader_never_falls_back_to_display_points():
    stage = _Stage(_Prim(display_points=_positions().tolist()))

    with pytest.raises(ValueError, match="simulation_points_missing"):
        online.read_strict_simulation_points(
            stage,
            "/World/Fluid/Particles",
            expected_particle_count=4,
        )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (np.zeros((3, 3)), "particle_count_mismatch"),
        (np.zeros((4, 2)), "simulation_points_shape_invalid"),
        (np.asarray([[0, 0, np.nan]] * 4), "simulation_points_nonfinite"),
    ],
)
def test_strict_particle_validation_rejects_malformed_values(values, message):
    with pytest.raises(ValueError, match=message):
        online.validate_simulation_points(values, expected_particle_count=4)


def test_reset_observation_and_action_transition_have_exact_online_order():
    events: list[str] = []
    runtime = _runtime(events)
    runtime.reset_episode("episode-1")

    reset_record = runtime.process_observation(_transition(0), _positions())
    action_record = runtime.process_observation(_transition(1), _positions(offset=0.1))

    assert events == [
        "invalidate:episode_reset",
        "reconstruct",
        "author",
        "render",
        "capture",
        "reconstruct",
        "author",
        "render",
        "capture",
    ]
    assert reset_record["caused_by_action_index"] is None
    assert action_record["caused_by_action_index"] == 0
    assert reset_record["action_sha256"] is None
    assert action_record["action_sha256"] == _transition(1).action_sha256
    assert action_record["position_sha256"] != reset_record["position_sha256"]
    assert reset_record["position_summary_world_m"] == {
        "min": pytest.approx(_positions().min(axis=0).tolist()),
        "max": pytest.approx(_positions().max(axis=0).tolist()),
        "centroid": pytest.approx(_positions().mean(axis=0).tolist()),
    }
    assert action_record["render"]["physics_and_timeline_unchanged"] is True
    assert sorted(action_record["cameras"]) == ["camera_1_rgb", "camera_2_rgb"]
    assert all(len(item["sha256"]) == 64 for item in action_record["cameras"].values())
    assert set(action_record["latency_seconds"]) == {
        "reconstruction",
        "usd_authoring",
        "render",
        "camera_read",
        "total",
    }


def test_unchanged_hold_particle_hash_is_valid_when_step_epoch_advances():
    events: list[str] = []
    runtime = _runtime(events)
    positions = _positions()
    runtime.reset_episode("episode-1")

    initial = runtime.process_observation(_transition(0), positions)
    held = runtime.process_observation(_transition(1), positions.copy())

    assert initial["position_sha256"] == held["position_sha256"]
    assert held["integration_step_after"] == initial["integration_step_after"] + 4
    assert held["observation_index"] == initial["observation_index"] + 1


def test_variable_topology_is_authored_for_each_current_observation():
    events: list[str] = []
    runtime = _runtime(events, mesh_topologies=[0, 1])
    runtime.reset_episode("episode-1")

    first = runtime.process_observation(_transition(0), _positions())
    second = runtime.process_observation(_transition(1), _positions(offset=0.1))

    assert first["surface"]["vertex_count"] == 3
    assert second["surface"]["vertex_count"] == 4
    assert first["surface"]["face_count"] == 1
    assert second["surface"]["face_count"] == 2


@pytest.mark.parametrize(
    "bad_transition",
    [
        _transition(1),
        replace(_transition(0), caused_by_action_index=0),
        replace(_transition(0), integration_step_after=81),
        replace(_transition(1), integration_step_after=83),
        replace(_transition(1), simulation_time_after=1.0),
    ],
)
def test_transition_identity_and_four_substeps_are_strict(bad_transition):
    events: list[str] = []
    runtime = _runtime(events)
    runtime.reset_episode("episode-1")

    with pytest.raises(ValueError):
        runtime.process_observation(bad_transition, _positions())

    assert any(item.startswith("invalidate:") for item in events)


def test_duplicate_observation_fails_and_requires_episode_reset():
    events: list[str] = []
    runtime = _runtime(events)
    runtime.reset_episode("episode-1")
    runtime.process_observation(_transition(0), _positions())

    with pytest.raises(ValueError, match="observation_index_out_of_sequence"):
        runtime.process_observation(_transition(0), _positions())
    with pytest.raises(RuntimeError, match="episode_runtime_failed_requires_reset"):
        runtime.process_observation(_transition(1), _positions())


def test_transition_counters_must_continue_from_previous_observation():
    events: list[str] = []
    runtime = _runtime(events)
    runtime.reset_episode("episode-1")
    runtime.process_observation(_transition(0), _positions())
    discontinuous = _transition(
        1,
        base_logical_step=21,
        base_integration_step=84,
    )

    with pytest.raises(ValueError, match="transition_counter_discontinuity"):
        runtime.process_observation(discontinuous, _positions(offset=0.1))


def test_nonreset_transition_requires_action_commitment():
    events: list[str] = []
    runtime = _runtime(events)
    runtime.reset_episode("episode-1")
    runtime.process_observation(_transition(0), _positions())

    with pytest.raises(ValueError, match="action_sha256_invalid"):
        runtime.process_observation(
            replace(_transition(1), action_sha256=None),
            _positions(offset=0.1),
        )


def test_surface_authoring_and_render_must_commit_current_frame_token():
    events: list[str] = []
    runtime = _runtime(events)
    runtime.author_surface = lambda mesh, token: {
        "surface_token": "stale-token",
        "vertex_count": len(mesh["vertices"]),
        "face_count": len(mesh["faces"]),
    }
    runtime.reset_episode("episode-1")

    with pytest.raises(RuntimeError, match="surface_authoring_token_mismatch"):
        runtime.process_observation(_transition(0), _positions())


def test_render_may_not_advance_physics_or_timeline():
    events: list[str] = []
    runtime = _runtime(events)
    runtime.render_surface = lambda token: {
        **_render_record(token),
        "integration_steps_after": token.integration_step_after + 1,
    }
    runtime.reset_episode("episode-1")

    with pytest.raises(RuntimeError, match="render_advanced_physics_or_timeline"):
        runtime.process_observation(_transition(0), _positions())

    assert events[-1].startswith("invalidate:")


def test_paused_render_timeline_is_independent_of_physx_simulation_time():
    events: list[str] = []
    runtime = _runtime(events)
    runtime.render_surface = lambda token: {
        **_render_record(token),
        "timeline_time_before": 0.0,
        "timeline_time_after": 0.0,
    }
    runtime.reset_episode("episode-1")
    runtime.process_observation(_transition(0), _positions())

    record = runtime.process_observation(_transition(1), _positions(offset=0.1))

    assert record["simulation_time_after"] > 0.0
    assert record["render"]["timeline_time_after"] == 0.0
    assert record["render"]["physics_and_timeline_unchanged"] is True


@pytest.mark.parametrize("failing_stage", ["reconstruct", "author", "render", "capture"])
def test_any_presentation_failure_invalidates_old_surface(failing_stage):
    events: list[str] = []
    runtime = _runtime(events)

    def fail(*_args, **_kwargs):
        events.append(failing_stage)
        raise RuntimeError(f"{failing_stage}_failed")

    setattr(
        runtime,
        {
            "reconstruct": "reconstruct",
            "author": "author_surface",
            "render": "render_surface",
            "capture": "capture_cameras",
        }[failing_stage],
        fail,
    )
    runtime.reset_episode("episode-1")

    with pytest.raises(RuntimeError, match=f"{failing_stage}_failed"):
        runtime.process_observation(_transition(0), _positions())

    assert events[-1].startswith("invalidate:observation_failed")
    with pytest.raises(RuntimeError, match="episode_runtime_failed_requires_reset"):
        runtime.process_observation(_transition(0), _positions())


def test_two_episode_resets_reuse_state_but_not_identity():
    events: list[str] = []
    runtime = _runtime(events)
    positions = _positions()

    runtime.reset_episode("episode-1")
    first = runtime.process_observation(_transition(0), positions)
    runtime.reset_episode("episode-2")
    second = runtime.process_observation(
        _transition(0, episode_id="episode-2"), positions
    )

    assert first["position_sha256"] == second["position_sha256"]
    assert first["frame_identity"] != second["frame_identity"]
    assert events.count("invalidate:episode_reset") == 2
