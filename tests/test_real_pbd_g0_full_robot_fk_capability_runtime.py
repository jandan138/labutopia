from __future__ import annotations

import inspect
import numpy as np

from tools.labutopia_fluid import real_pbd_g0_full_robot_fk_capability_runtime as runtime
from utils import real_pbd_g0_full_robot_fk_capability as capability


class _World:
    def step(self):
        return "step"

    def reset(self):
        return "reset"


class _Timeline:
    def play(self):
        return "play"

    def pause(self):
        return "pause"

    def stop(self):
        return "stop"

    def set_current_time(self, _value):
        return "time"


class _Controller:
    def apply_action(self, _value):
        return "action"


class _ArticulationView:
    def set_joint_velocities(self, _value):
        return "view-velocity"


class _Robot:
    def __init__(self):
        self.controller = _Controller()
        self._articulation_view = _ArticulationView()

    def get_articulation_controller(self):
        return self.controller

    def apply_action(self, _value):
        return "robot-action"

    def set_joint_velocities(self, _value):
        return "velocity"

    def set_joint_positions(self, _value):
        return "position"


class _SimulationView:
    def step(self):
        return "simulation-step"

    def update_articulations_kinematic(self):
        return "refresh"


class _SourceView:
    def __init__(self):
        self._physics_view = _SourcePhysicsView()

    def set_world_poses(self, _value):
        return "pose"

    def set_linear_velocities(self, _value):
        return "velocity"

    def apply_forces(self, _value):
        return "force"


class _SourcePhysicsView:
    def set_transforms(self, _value):
        return "transform"

    def set_velocities(self, _value):
        return "velocity"

    def apply_forces(self, _value):
        return "force"


class _SourceReader:
    def __init__(self, view):
        self._view = view


class _TimelineEventAudit:
    active = True


class _EventStream:
    def __init__(self):
        self.callback = None

    def create_subscription_to_pop(self, callback):
        self.callback = callback
        return object()

    def emit(self, event_type):
        self.callback(type("Event", (), {"type": event_type})())


class _TimelineWithEvents:
    def __init__(self):
        self.stream = _EventStream()

    def get_timeline_event_stream(self):
        return self.stream


class _Attribute:
    def __init__(self, value):
        self._value = value

    def IsValid(self):
        return True

    def Get(self):
        return self._value


class _Prim:
    def __init__(self, attributes):
        self._attributes = attributes

    def IsValid(self):
        return True

    def GetTypeName(self):
        return "Points"

    def GetAttribute(self, name):
        return self._attributes.get(name)


class _Stage:
    def __init__(self, attributes):
        self._prim = _Prim(attributes)

    def GetPrimAtPath(self, path):
        assert path == runtime.PARTICLE_PATH
        return self._prim


def _guarded_objects(source_view=None):
    world = _World()
    timeline = _Timeline()
    robot = _Robot()
    simulation_view = _SimulationView()
    source_reader = _SourceReader(source_view or _SourceView())
    counts, coverage, restore = runtime._instrument_operations(
        world=world,
        timeline_event_audit=_TimelineEventAudit(),
        robot=robot,
        simulation_view=simulation_view,
        source_reader=source_reader,
        required_coverage=capability.OPERATION_GUARD_COVERAGE_FIELDS,
    )
    return world, timeline, robot, simulation_view, source_reader, counts, coverage, restore


def test_runtime_guards_block_post_baseline_reset_step_and_writers():
    world, timeline, robot, simulation_view, source_reader, counts, coverage, restore = (
        _guarded_objects()
    )

    for method, args, counter in (
        (world.reset, (), "world_reset"),
        (world.step, (), "world_step"),
        (simulation_view.step, (), "simulation_view_step"),
        (robot.controller.apply_action, (None,), "apply_action"),
        (source_reader._view.apply_forces, (None,), "source_force_writer"),
    ):
        try:
            method(*args)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{counter} was not blocked")
        assert counts[counter] == 1

    robot.set_joint_positions([0.0] * 9)
    simulation_view.update_articulations_kinematic()
    assert counts["direct_joint_position_materialization"] == 1
    assert counts["tensor_kinematic_refresh"] == 1
    assert set(coverage) == set(capability.OPERATION_GUARD_COVERAGE_FIELDS)
    assert all(coverage.values())
    restore()
    assert world.reset() == "reset"
    assert source_reader._view.apply_forces(None) == "force"


def test_runtime_guard_setup_rolls_back_on_missing_force_writer_surface():
    class _NoForceSourceView:
        def set_world_poses(self, _value):
            return "pose"

        def set_linear_velocities(self, _value):
            return "velocity"

    world = _World()
    try:
        runtime._instrument_operations(
            world=world,
            timeline_event_audit=_TimelineEventAudit(),
            robot=_Robot(),
            simulation_view=_SimulationView(),
            source_reader=_SourceReader(_NoForceSourceView()),
            required_coverage=capability.OPERATION_GUARD_COVERAGE_FIELDS,
        )
    except RuntimeError as exc:
        assert "source_force_writer" in str(exc)
    else:
        raise AssertionError("missing force writer surface unexpectedly accepted")
    assert world.step() == "step"
    assert world.reset() == "reset"


def test_timeline_event_audit_records_post_baseline_state_changes():
    timeline = _TimelineWithEvents()
    audit = runtime._TimelineEventAudit(
        timeline,
        {1: "timeline_play", 2: "timeline_time_set"},
    )
    timeline.stream.emit(1)
    timeline.stream.emit(2)

    assert audit.active is True
    assert audit.operation_counts() == {"timeline_play": 1, "timeline_time_set": 1}
    assert audit.events() == [
        {"counter": "timeline_play", "event_type": 1},
        {"counter": "timeline_time_set", "event_type": 2},
    ]
    audit.close()
    assert audit.active is False


def test_particle_snapshot_requires_authoritative_simulation_points():
    visual_only = runtime._particle_usd_snapshot(
        np,
        _Stage({"points": _Attribute(np.asarray([[0.0, 0.0, 0.0]]))}),
    )
    authoritative = runtime._particle_usd_snapshot(
        np,
        _Stage(
            {
                runtime.SIMULATION_POINTS_ATTRIBUTE: _Attribute(
                    np.asarray([[0.0, 0.0, 0.0]])
                )
            }
        ),
    )

    assert visual_only["complete"] is False
    assert authoritative["complete"] is True
    assert runtime.SIMULATION_POINTS_ATTRIBUTE in authoritative["attributes"]


def test_capability_passes_its_own_float32_readback_tolerance_to_static_helper():
    from tools.labutopia_fluid import (
        nonformal_controller_static_collision_screen_runtime as static_runtime,
    )

    assert "joint_readback_atol" in inspect.signature(
        static_runtime._materialize_configuration
    ).parameters
    assert runtime.CAPABILITY_JOINT_READBACK_ATOL > 1.3e-8
