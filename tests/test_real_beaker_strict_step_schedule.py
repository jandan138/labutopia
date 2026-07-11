from __future__ import annotations

import pytest

from tools.labutopia_fluid import (
    run_colleague_native_usd_completed_pbd_step_video as runner,
)


class _FakePhysxSimulation:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def simulate(self, dt: float, current_time: float) -> None:
        self.calls.append(("simulate", dt, current_time))

    def fetch_results(self) -> None:
        self.calls.append(("fetch_results",))


class _FakeTimeline:
    def __init__(self, playing: bool) -> None:
        self.playing = playing

    def is_playing(self) -> bool:
        return self.playing


class _FakeApp:
    def __init__(self) -> None:
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1


def test_strict_stepper_executes_exact_dt_and_monotonic_simulation_time():
    interface = _FakePhysxSimulation()
    stepper = runner.StrictPhysicsStepper(interface=interface, physics_dt=1.0 / 60.0)

    for _ in range(3):
        stepper.step()

    assert interface.calls == [
        ("simulate", 1.0 / 60.0, 0.0),
        ("fetch_results",),
        ("simulate", 1.0 / 60.0, 1.0 / 60.0),
        ("fetch_results",),
        ("simulate", 1.0 / 60.0, 2.0 / 60.0),
        ("fetch_results",),
    ]
    assert stepper.summary(requested_steps=3) == {
        "requested_steps": 3,
        "executed_steps": 3,
        "physics_dt": 1.0 / 60.0,
        "simulated_seconds": 3.0 / 60.0,
        "exact_step_count_verified": True,
        "render_updates_advance_physics": False,
    }


def test_paused_render_update_rejects_timeline_that_is_still_playing():
    app = _FakeApp()

    with pytest.raises(RuntimeError, match="strict_render_update_while_timeline_playing"):
        runner.paused_render_update(app, _FakeTimeline(playing=True))

    runner.paused_render_update(app, _FakeTimeline(playing=False))
    assert app.update_count == 1


def test_physics_scene_timestep_requires_an_exact_reciprocal_integer():
    assert runner.physics_steps_per_second(1.0 / 60.0) == 60
    with pytest.raises(ValueError, match="physics_dt_must_have_integer_frequency"):
        runner.physics_steps_per_second(0.017)
