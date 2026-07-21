from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from utils.controlled_contact import (
    build_arm_target_token,
    build_finger_target_token,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class _StubArticulationAction:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _StubIsaacBaseController:
    def __init__(self, name):
        self.name = name

    def reset(self):
        pass


class _StubCspaceController:
    def __init__(self):
        self.calls = []
        self.reset_count = 0

    def forward(self, **kwargs):
        self.calls.append(
            {
                key: np.asarray(value).copy() if isinstance(value, np.ndarray) else value
                for key, value in kwargs.items()
            }
        )
        return _StubArticulationAction(**kwargs)

    def reset(self):
        self.reset_count += 1


class _StubArticulationController:
    def __init__(self):
        self.mode_switches = []

    def switch_dof_control_mode(self, **kwargs):
        self.mode_switches.append(dict(kwargs))


def _module(name, **attributes):
    result = ModuleType(name)
    for key, value in attributes.items():
        setattr(result, key, value)
    return result


def _right_gripper_to_tool_center_matrix_m():
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = np.diag([-1.0, -1.0, 1.0])
    result[3, 2] = -0.0034
    return result


def _load_atomic_pour_controller(monkeypatch):
    modules = {
        "isaacsim": _module("isaacsim"),
        "isaacsim.core": _module("isaacsim.core"),
        "isaacsim.core.api": _module("isaacsim.core.api"),
        "isaacsim.core.api.controllers": _module(
            "isaacsim.core.api.controllers", BaseController=_StubIsaacBaseController
        ),
        "isaacsim.core.api.controllers.articulation_controller": _module(
            "isaacsim.core.api.controllers.articulation_controller",
            ArticulationController=object,
        ),
        "isaacsim.core.utils": _module("isaacsim.core.utils"),
        "isaacsim.core.utils.stage": _module(
            "isaacsim.core.utils.stage", get_stage_units=lambda: 1.0
        ),
        "isaacsim.core.utils.types": _module(
            "isaacsim.core.utils.types", ArticulationAction=_StubArticulationAction
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(
        "atomic_pour_controller_under_test",
        REPO_ROOT / "controllers/atomic_actions/pour_controller.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_atomic_pick_controller(monkeypatch):
    modules = {
        "isaacsim": _module("isaacsim"),
        "isaacsim.core": _module("isaacsim.core"),
        "isaacsim.core.api": _module("isaacsim.core.api"),
        "isaacsim.core.api.controllers": _module(
            "isaacsim.core.api.controllers", BaseController=_StubIsaacBaseController
        ),
        "isaacsim.core.utils": _module("isaacsim.core.utils"),
        "isaacsim.core.utils.rotations": _module(
            "isaacsim.core.utils.rotations",
            euler_angles_to_quat=lambda _angles: np.asarray(
                [1.0, 0.0, 0.0, 0.0], dtype=np.float64
            ),
        ),
        "isaacsim.core.utils.stage": _module(
            "isaacsim.core.utils.stage", get_stage_units=lambda: 1.0
        ),
        "isaacsim.core.utils.types": _module(
            "isaacsim.core.utils.types", ArticulationAction=_StubArticulationAction
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(
        "atomic_pick_controller_under_test",
        REPO_ROOT / "controllers/atomic_actions/pick_controller.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _forward(
    controller,
    target_position,
    *,
    gripper_position=None,
    source_position=None,
    target_end_effector_orientation=None,
    current_end_effector_orientation=None,
):
    kwargs = {
        "articulation_controller": _StubArticulationController(),
        "source_size": np.asarray([0.1, 0.1, 0.2], dtype=np.float64),
        "target_position": target_position,
        "current_joint_velocities": np.zeros(9, dtype=np.float64),
        "gripper_position": np.asarray(
            [10.0, 10.0, 10.0]
            if gripper_position is None
            else gripper_position,
            dtype=np.float64,
        ),
        "source_name": "beaker2",
        "source_position": source_position,
        "current_end_effector_orientation": current_end_effector_orientation,
    }
    if target_end_effector_orientation is not None:
        kwargs["target_end_effector_orientation"] = target_end_effector_orientation
    return controller.forward(
        **kwargs,
    )


def test_fixed_pour_heights_are_stable_and_forward_does_not_mutate_target(
    monkeypatch,
):
    module = _load_atomic_pour_controller(monkeypatch)
    monkeypatch.setattr(
        module.np.random,
        "uniform",
        lambda *_args, **_kwargs: pytest.fail("fixed mode must not sample RNG"),
    )
    cspace = _StubCspaceController()
    controller = module.PourController(
        name="pour",
        cspace_controller=cspace,
        events_dt=[0.01] * 6,
        fixed_height_offsets=(0.4, 0.2),
        target_position_offset=(0.0, 0.05, 0.0),
    )
    target = np.asarray([0.3, -0.2, 0.8], dtype=np.float32)
    original = target.copy()

    _forward(controller, target)
    _forward(controller, target)

    np.testing.assert_array_equal(target, original)
    assert target.dtype == original.dtype
    np.testing.assert_allclose(
        cspace.calls[-1]["target_end_effector_position"], [0.3, -0.15, 1.2]
    )
    controller._event = 1
    _forward(controller, target)
    np.testing.assert_array_equal(target, original)
    np.testing.assert_allclose(
        cspace.calls[-1]["target_end_effector_position"], [0.3, -0.23, 1.12]
    )
    controller.reset()


def test_random_pour_heights_sample_once_per_episode(monkeypatch):
    module = _load_atomic_pour_controller(monkeypatch)
    samples = iter([0.31, 0.11, 0.32, 0.12])
    calls = []

    def sample(*args):
        calls.append(args)
        return next(samples)

    monkeypatch.setattr(module.np.random, "uniform", sample)
    controller = module.PourController(
        name="pour",
        cspace_controller=_StubCspaceController(),
        events_dt=[0.01] * 6,
    )
    target = np.asarray([0.3, -0.2, 0.8], dtype=np.float64)

    assert len(calls) == 2
    _forward(controller, target)
    _forward(controller, target)
    controller._event = 1
    _forward(controller, target)
    assert len(calls) == 2
    controller.reset()
    assert len(calls) == 4


@pytest.mark.parametrize(
    "event,desired_source",
    [
        (0, [0.3, -0.15, 1.2]),
        (1, [0.3, -0.23, 1.12]),
    ],
)
def test_online_pour_compensates_live_source_to_gripper_offset_each_frame(
    monkeypatch,
    event,
    desired_source,
):
    module = _load_atomic_pour_controller(monkeypatch)
    cspace = _StubCspaceController()
    controller = module.PourController(
        name="pour",
        cspace_controller=cspace,
        events_dt=[0.0] * 6,
        fixed_height_offsets=(0.4, 0.2),
        target_position_offset=(0.0, 0.05, 0.0),
    )
    controller._event = event
    target = np.asarray([0.3, -0.2, 0.8], dtype=np.float64)
    source = np.asarray([0.1, 0.2, 0.9], dtype=np.float64)
    gripper = np.asarray([0.0, 0.1, 1.0], dtype=np.float64)
    target_before = target.copy()
    source_before = source.copy()
    gripper_before = gripper.copy()

    _forward(
        controller,
        target,
        source_position=source,
        gripper_position=gripper,
    )

    expected = np.asarray(desired_source) - (source - gripper)
    np.testing.assert_allclose(
        cspace.calls[-1]["target_end_effector_position"], expected
    )
    np.testing.assert_array_equal(target, target_before)
    np.testing.assert_array_equal(source, source_before)
    np.testing.assert_array_equal(gripper, gripper_before)

    source += [0.02, -0.03, 0.01]
    _forward(
        controller,
        target,
        source_position=source,
        gripper_position=gripper,
    )
    np.testing.assert_allclose(
        cspace.calls[-1]["target_end_effector_position"],
        np.asarray(desired_source) - (source - gripper),
    )


def test_atomic_pour_maps_tool_center_target_to_rmp_control_frame(monkeypatch):
    module = _load_atomic_pour_controller(monkeypatch)
    cspace = _StubCspaceController()
    controller = module.PourController(
        name="pour",
        cspace_controller=cspace,
        events_dt=[0.1] * 6,
        fixed_height_offsets=[0.4, 0.14],
        control_to_end_effector_matrix_m=(
            _right_gripper_to_tool_center_matrix_m()
        ),
    )
    tool_orientation = np.asarray([0.0, 0.0, 1.0, 0.0])

    _forward(
        controller,
        np.asarray([0.5, -0.2, 0.8]),
        gripper_position=np.asarray([0.3, 0.1, 0.9]),
        source_position=np.asarray([0.3, 0.1, 0.8]),
        target_end_effector_orientation=tool_orientation,
    )

    call = cspace.calls[-1]
    np.testing.assert_allclose(
        call["target_end_effector_position"],
        [0.5, -0.2, 1.3034],
        atol=1.0e-12,
    )
    np.testing.assert_allclose(
        np.abs(call["target_end_effector_orientation"]),
        [0.0, 1.0, 0.0, 0.0],
        atol=1.0e-12,
    )


def test_atomic_pour_can_preserve_native_direct_control_frame_targets(monkeypatch):
    module = _load_atomic_pour_controller(monkeypatch)
    cspace = _StubCspaceController()
    controller = module.PourController(
        name="pour",
        cspace_controller=cspace,
        events_dt=[0.1] * 6,
        fixed_height_offsets=[0.4, 0.14],
        direct_control_frame_targets=True,
    )
    legacy_orientation_bytes = np.asarray([0.0, 0.0, 1.0, 0.0])

    _forward(
        controller,
        np.asarray([0.5, -0.2, 0.8]),
        gripper_position=np.asarray([0.3, 0.1, 0.9]),
        target_end_effector_orientation=legacy_orientation_bytes,
    )

    call = cspace.calls[-1]
    np.testing.assert_allclose(
        call["target_end_effector_position"], [0.5, -0.2, 1.2]
    )
    np.testing.assert_array_equal(
        call["target_end_effector_orientation"], legacy_orientation_bytes
    )


def test_legacy_pick_latches_actual_close_and_lift_actions(monkeypatch):
    module = _load_atomic_pick_controller(monkeypatch)
    controller = module.PickController(
        name="pick",
        cspace_controller=_StubCspaceController(),
        events_dt=[0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0],
    )
    controller._start = False
    controller._event = 4
    position = np.asarray([0.3, 0.1, 0.84], dtype=np.float64)
    joints = np.zeros(9, dtype=np.float64)
    gripper = SimpleNamespace(add_object_to_gripper=lambda *_args: None)

    close_action = controller.forward(
        picking_position=position.copy(),
        current_joint_positions=joints,
        object_name="beaker2",
        object_size=np.asarray([0.08, 0.08, 0.12]),
        gripper_control=gripper,
        gripper_position=position,
        after_offset_z=0.5,
    )

    assert controller._event == 5
    assert close_action.kwargs["joint_positions"][7:9] == [0.028, 0.028]
    assert controller.grasp_contact_requested() is True
    assert controller.lift_command_emitted() is False
    assert controller.lift_is_next_action() is True
    evidence = controller.control_evidence()
    assert evidence["event"] == 5
    assert evidence["last_emitted_event"] == 4

    controller.forward(
        picking_position=position.copy(),
        current_joint_positions=joints,
        object_name="beaker2",
        object_size=np.asarray([0.08, 0.08, 0.12]),
        gripper_control=gripper,
        gripper_position=position,
        after_offset_z=0.5,
    )

    assert controller.lift_command_emitted() is True
    evidence = controller.control_evidence()
    assert evidence["last_emitted_event"] == 5
    assert evidence["close_command_emitted"] is True
    assert evidence["lift_command_emitted"] is True
    controller.reset()
    assert controller.grasp_contact_requested() is False
    assert controller.lift_command_emitted() is False
    assert controller.control_evidence()["last_emitted_event"] is None


def test_online_pour_phase_transition_uses_source_not_gripper_position(monkeypatch):
    module = _load_atomic_pour_controller(monkeypatch)
    cspace = _StubCspaceController()
    controller = module.PourController(
        name="pour",
        cspace_controller=cspace,
        events_dt=[0.0] * 6,
        fixed_height_offsets=(0.4, 0.2),
        target_position_offset=(0.0, 0.05, 0.0),
    )
    target = np.asarray([0.3, -0.2, 0.8], dtype=np.float64)
    desired_source = np.asarray([0.3, -0.15, 1.2], dtype=np.float64)

    _forward(
        controller,
        target,
        source_position=np.asarray([0.5, 0.2, 1.2]),
        gripper_position=desired_source,
    )
    assert controller._event == 0

    source = desired_source.copy()
    gripper = source - np.asarray([0.1, -0.04, 0.03])
    _forward(
        controller,
        target,
        source_position=source,
        gripper_position=gripper,
    )
    assert controller._event == 1


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_online_pour_waits_for_end_effector_orientation_before_pouring(
    monkeypatch,
    sign,
):
    module = _load_atomic_pour_controller(monkeypatch)
    controller = module.PourController(
        name="pour",
        cspace_controller=_StubCspaceController(),
        events_dt=[2.0] * 6,
        fixed_height_offsets=(0.4, 0.2),
        target_position_offset=(0.0, 0.05, 0.0),
        require_entry_orientation=True,
        entry_orientation_threshold_degrees=5.0,
    )
    controller._event = 1
    target = np.asarray([0.3, -0.2, 0.8], dtype=np.float64)
    desired_source = np.asarray([0.3, -0.23, 1.12], dtype=np.float64)
    target_quaternion = np.asarray([1.0, 0.0, 0.0, 0.0])
    six_degrees = np.radians(6.0) / 2.0

    _forward(
        controller,
        target,
        source_position=desired_source,
        gripper_position=desired_source,
        target_end_effector_orientation=target_quaternion,
        current_end_effector_orientation=np.asarray(
            [np.cos(six_degrees), np.sin(six_degrees), 0.0, 0.0]
        ),
    )

    # The event timer must not bypass the orientation gate.
    assert controller._event == 1

    five_degrees = np.radians(5.0) / 2.0
    _forward(
        controller,
        target,
        source_position=desired_source,
        gripper_position=desired_source,
        target_end_effector_orientation=target_quaternion,
        current_end_effector_orientation=sign
        * np.asarray([np.cos(five_degrees), np.sin(five_degrees), 0.0, 0.0]),
    )

    assert controller._event == 2
    assert controller.pour_entry_orientation_evidence == {
        "enabled": True,
        "threshold_degrees": 5.0,
        "error_degrees": pytest.approx(5.0),
        "valid": True,
        "passed": True,
        "pour_forward_call_index": 1,
    }


@pytest.mark.parametrize(
    "current_orientation",
    [None, [0.0, 0.0, 0.0, 0.0], [1.0, 0.0, np.nan, 0.0]],
)
def test_online_pour_invalid_orientation_fails_closed(
    monkeypatch,
    current_orientation,
):
    module = _load_atomic_pour_controller(monkeypatch)
    controller = module.PourController(
        name="pour",
        cspace_controller=_StubCspaceController(),
        events_dt=[2.0] * 6,
        fixed_height_offsets=(0.4, 0.2),
        target_position_offset=(0.0, 0.05, 0.0),
        require_entry_orientation=True,
        entry_orientation_threshold_degrees=5.0,
    )
    controller._event = 1
    target = np.asarray([0.3, -0.2, 0.8], dtype=np.float64)
    desired_source = np.asarray([0.3, -0.23, 1.12], dtype=np.float64)

    _forward(
        controller,
        target,
        source_position=desired_source,
        gripper_position=desired_source,
        target_end_effector_orientation=np.asarray([1.0, 0.0, 0.0, 0.0]),
        current_end_effector_orientation=current_orientation,
    )

    assert controller._event == 1
    assert controller.pour_entry_orientation_evidence["valid"] is False
    assert controller.pour_entry_orientation_evidence["passed"] is False


def test_pour_controller_latches_the_event_that_emitted_each_action(monkeypatch):
    module = _load_atomic_pour_controller(monkeypatch)
    controller = module.PourController(
        name="pour",
        cspace_controller=_StubCspaceController(),
        events_dt=[0.0] * 6,
        fixed_height_offsets=(0.4, 0.2),
        target_position_offset=(0.0, 0.05, 0.0),
    )
    target = np.asarray([0.3, -0.2, 0.8], dtype=np.float64)
    desired_source = np.asarray([0.3, -0.23, 1.12], dtype=np.float64)
    controller._event = 1

    _forward(
        controller,
        target,
        source_position=desired_source,
        gripper_position=desired_source,
    )

    assert controller._event == 2
    assert controller._last_emitted_event == 1

    action = _forward(
        controller,
        target,
        source_position=desired_source,
        gripper_position=desired_source,
    )

    assert controller._last_emitted_event == 2
    assert action.kwargs["joint_velocities"][6] == controller._pour_speed
    controller.reset()
    assert controller._last_emitted_event is None


@pytest.mark.parametrize(
    "source_position",
    [[1.0, 2.0], [1.0, np.nan, 3.0]],
)
def test_online_pour_rejects_invalid_source_position(monkeypatch, source_position):
    module = _load_atomic_pour_controller(monkeypatch)
    controller = module.PourController(
        name="pour",
        cspace_controller=_StubCspaceController(),
        events_dt=[0.0] * 6,
        fixed_height_offsets=(0.4, 0.2),
    )

    with pytest.raises(ValueError, match="source_position_must_be_three_finite_values"):
        _forward(
            controller,
            np.asarray([0.3, -0.2, 0.8]),
            source_position=np.asarray(source_position),
            gripper_position=np.asarray([0.0, 0.0, 0.0]),
        )


def test_active_pour_task_controller_receives_online_fixed_offsets(monkeypatch):
    captured = []
    forward_calls = []
    pick_forward_calls = []
    infer_forward_calls = []

    class StubBaseController:
        def __init__(self, cfg, robot):
            self.mode = cfg.mode
            self.robot = robot
            self.control_dt = 1.0 / 30.0
            self.gripper_control = object()
            self.rmp_controller = SimpleNamespace(
                get_end_effector_orientation_wxyz=lambda: np.asarray(
                    [0.5, 0.5, 0.5, 0.5], dtype=np.float64
                )
            )
            if self.mode == "collect":
                self._init_collect_mode(cfg, robot)
            else:
                self._init_infer_mode(cfg, robot)

        def _init_collect_mode(self, cfg, robot):
            del cfg, robot

        def _init_infer_mode(self, cfg, robot):
            del cfg, robot
            self.inference_engine = SimpleNamespace(
                step_inference=lambda state: infer_forward_calls.append(state)
                or _StubArticulationAction(infer=True),
                reset=lambda: None,
            )

    class StubPickController:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self._event = 0
            self.done = False

        def is_done(self):
            return self.done

        def forward(self, **kwargs):
            pick_forward_calls.append(kwargs)
            return _StubArticulationAction(**kwargs)

    class StubPourController:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured.append(kwargs)
            self.pour_entry_orientation_evidence = {
                "enabled": True,
                "threshold_degrees": 5.0,
                "error_degrees": 4.5,
                "valid": True,
                "passed": True,
                "pour_forward_call_index": 19,
            }

        def is_done(self):
            return False

        def forward(self, **kwargs):
            forward_calls.append(kwargs)
            return _StubArticulationAction(**kwargs)

        def reset(self):
            pass

    class StubRobot:
        def get_articulation_controller(self):
            return object()

        def get_joint_velocities(self):
            return np.zeros(9, dtype=np.float64)

    class StubTaskUtils:
        @classmethod
        def get_instance(cls):
            return cls()

        def get_pour_threshold(self, _item_name, _source_size):
            return 0.05

    package_modules = {
        "controllers": _module("controllers"),
        "controllers.atomic_actions": _module("controllers.atomic_actions"),
        "controllers.atomic_actions.contact_pick_controller": _module(
            "controllers.atomic_actions.contact_pick_controller",
            ContactPickController=StubPickController,
        ),
        "controllers.atomic_actions.pick_controller": _module(
            "controllers.atomic_actions.pick_controller",
            PickController=StubPickController,
        ),
        "controllers.atomic_actions.pour_controller": _module(
            "controllers.atomic_actions.pour_controller",
            PourController=StubPourController,
        ),
        "controllers.base_controller": _module(
            "controllers.base_controller", BaseController=StubBaseController
        ),
        "utils.task_utils": _module(
            "utils.task_utils", TaskUtils=StubTaskUtils
        ),
    }
    package_modules["controllers"].__path__ = []
    package_modules["controllers.atomic_actions"].__path__ = []
    for name, module in package_modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "controllers.pour_controller_contract_test",
        REPO_ROOT / "controllers/pour_controller.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    cfg = SimpleNamespace(
        mode="collect",
        online_fluid=SimpleNamespace(
            enabled=True,
            expert_control_profile="stabilized_online_fluid_v1",
            expert_pour_height_offsets_m=[0.4, 0.14],
            expert_pour_target_offset_m=[0.0, 0.05, 0.0],
            expert_pour_entry_orientation_required=True,
            expert_pour_entry_orientation_threshold_degrees=5.0,
            expert_pour_target_orientation_wxyz=[
                -0.061628416716219346,
                0.7044160264027586,
                0.06162841671621935,
                0.7044160264027587,
            ],
            expert_pick_gripper_offset_object_m=[
                -0.03296920435460227,
                0.11768984929933282,
                -0.030909867065350535,
            ],
            expert_pick_target_orientation_wxyz=[
                0.041126549288126785,
                0.7652732142089947,
                0.2961095276677087,
                0.5700742602348328,
            ],
        ),
    )

    robot = StubRobot()
    controller = module.PourTaskController(cfg, robot=robot)

    assert captured[0]["fixed_height_offsets"] == (0.4, 0.14)
    assert captured[0]["target_position_offset"] == (0.0, 0.05, 0.0)
    assert captured[0]["require_entry_orientation"] is True
    assert captured[0]["entry_orientation_threshold_degrees"] == 5.0

    object_position = np.asarray([0.3118024, 0.0918024, 0.8251943])
    object_quaternion = np.asarray(
        [0.6532814, 0.2705981, 0.2705981, 0.6532815]
    )
    object_position_before = object_position.copy()
    object_quaternion_before = object_quaternion.copy()
    pick_state = {
        "object_position": object_position,
        "object_quaternion": object_quaternion,
        "object_name": "beaker2",
        "object_size": np.asarray([0.1, 0.1, 0.1]),
        "joint_positions": np.zeros(9, dtype=np.float64),
        "gripper_position": np.asarray([0.1, -0.1, 1.0]),
        "target_position": np.asarray([0.0, -0.2, 0.8]),
    }
    original_check_phase_success = controller._check_phase_success
    controller._check_phase_success = lambda: False
    controller.current_phase = module.Phase.PICKING
    controller.active_controller = controller.pick_controller
    controller._step_collect(pick_state)

    local_offset = np.asarray(
        [-0.03296920435460227, 0.11768984929933282, -0.030909867065350535]
    )
    expected_anchor = object_position + module.R.from_quat(
        object_quaternion / np.linalg.norm(object_quaternion)
    ).apply(local_offset)
    np.testing.assert_allclose(
        pick_forward_calls[-1]["picking_position"], expected_anchor
    )
    np.testing.assert_allclose(
        pick_forward_calls[-1]["end_effector_orientation"],
        [0.041126549288126785, 0.7652732142089947,
         0.2961095276677087, 0.5700742602348328],
    )
    np.testing.assert_array_equal(object_position, object_position_before)
    np.testing.assert_array_equal(object_quaternion, object_quaternion_before)
    controller._check_phase_success = original_check_phase_success

    target_position = np.asarray([0.0, -0.2, 0.8], dtype=np.float64)
    original_target = target_position.copy()
    controller.current_phase = module.Phase.POURING
    controller.initial_position = np.asarray([0.0, 0.0, 0.0])
    controller.initial_quaternion = np.asarray([0.0, 0.0, 0.0, 1.0])
    controller.pour_complete = True
    controller.return_complete = True
    controller.return_timer = 0.99
    controller.state = {
        "object_position": np.asarray([0.0, -0.050001, 0.1]),
        "object_quaternion": np.asarray([0.0, 0.0, 0.0, 1.0]),
        "object_name": "beaker2",
        "object_size": np.asarray([0.1, 0.1, 0.1]),
        "target_position": target_position,
    }

    assert controller._check_phase_success() is True
    np.testing.assert_array_equal(target_position, original_target)

    controller.return_timer = 0.99
    controller.state["object_position"][1] = -0.049
    assert controller._check_phase_success() is False

    infer_cfg = SimpleNamespace(mode="infer", online_fluid=cfg.online_fluid)
    infer_controller = module.PourTaskController(infer_cfg, robot=object())
    infer_controller._check_phase_success = lambda: False
    infer_controller._step_infer(pick_state)
    np.testing.assert_allclose(
        pick_forward_calls[-1]["picking_position"], expected_anchor
    )
    np.testing.assert_allclose(
        pick_forward_calls[-1]["end_effector_orientation"],
        [0.041126549288126785, 0.7652732142089947,
         0.2961095276677087, 0.5700742602348328],
    )
    infer_controller.pick_controller._event = 5
    assert infer_controller.online_fluid_grasp_attachment_requested() is True
    infer_controller.current_phase = module.Phase.POURING
    assert infer_controller.online_fluid_rotation_handoff_requested() is True
    assert infer_controller.online_fluid_control_evidence()["mode"] == "infer"
    assert (
        infer_controller.online_fluid_control_evidence()[
            "pour_entry_orientation"
        ]
        is None
    )
    infer_controller.pick_controller.done = True
    infer_controller.state = pick_state
    infer_controller._check_phase_success = lambda: True
    _action, infer_done, infer_success = infer_controller._step_infer(pick_state)
    assert infer_done is True
    assert infer_success is True
    assert infer_forward_calls[-1] is pick_state
    assert infer_controller.current_phase == module.Phase.FINISHED
    infer_controller._check_phase_success = (
        module.PourTaskController._check_phase_success.__get__(
            infer_controller, module.PourTaskController
        )
    )

    aborted_infer = module.PourTaskController(infer_cfg, robot=object())
    assert aborted_infer.abort_online_fluid_episode("evaluation_timeout") == (
        None,
        True,
        False,
    )
    assert aborted_infer.current_phase == module.Phase.FINISHED
    assert aborted_infer._last_failure_reason == "evaluation_timeout"
    infer_controller.current_phase = module.Phase.POURING
    infer_controller.initial_position = np.asarray([0.0, 0.0, 0.0])
    infer_controller.initial_quaternion = np.asarray([0.0, 0.0, 0.0, 1.0])
    infer_controller.pour_complete = True
    infer_controller.return_complete = True
    infer_controller.return_timer = 0.99
    infer_controller.state = {
        **controller.state,
        "object_position": np.asarray([0.0, -0.05, 0.1]),
    }

    assert infer_controller._check_phase_success() is False

    controller._check_phase_success = lambda: False
    controller.current_phase = module.Phase.POURING
    controller.active_controller = controller.pour_controller
    controller.initial_size = np.asarray([0.1, 0.1, 0.2])
    online_state = {
        **controller.state,
        "joint_positions": np.zeros(9, dtype=np.float64),
        "gripper_position": np.asarray([0.1, -0.1, 1.0]),
    }
    controller._step_collect(online_state)
    np.testing.assert_array_equal(
        forward_calls[-1]["source_position"], online_state["object_position"]
    )
    target_wxyz = np.asarray(
        [-0.061628416716219346, 0.7044160264027586,
         0.06162841671621935, 0.7044160264027587]
    )
    np.testing.assert_allclose(
        forward_calls[-1]["target_end_effector_orientation"],
        target_wxyz,
    )
    np.testing.assert_array_equal(
        forward_calls[-1]["current_end_effector_orientation"],
        [0.5, 0.5, 0.5, 0.5],
    )
    control_evidence = controller.online_fluid_control_evidence()
    np.testing.assert_allclose(
        control_evidence["pick_gripper_offset_object_m"], local_offset
    )
    np.testing.assert_allclose(
        control_evidence["pick_target_orientation_wxyz"],
        [0.041126549288126785, 0.7652732142089947,
         0.2961095276677087, 0.5700742602348328],
    )
    assert control_evidence["pour_entry_orientation"]["passed"] is True
    np.testing.assert_allclose(
        control_evidence["target_end_effector_orientation_wxyz"],
        target_wxyz,
    )

    legacy_cfg = SimpleNamespace(mode="collect", online_fluid=None)
    legacy = module.PourTaskController(legacy_cfg, robot=robot)
    legacy._check_phase_success = lambda: False
    legacy.current_phase = module.Phase.POURING
    legacy.active_controller = legacy.pour_controller
    legacy.initial_size = np.asarray([0.1, 0.1, 0.2])
    legacy._step_collect(online_state)
    assert forward_calls[-1]["source_position"] is None
    assert "current_end_effector_orientation" not in forward_calls[-1]


def test_online_fluid_collection_commits_only_after_combined_expert_acceptance(
    monkeypatch,
):
    captured = []

    class StubCollector:
        def __init__(self):
            self.writes = []
            self.clear_count = 0
            self.properties = []

        def write_cached_data(self, final_joint_positions):
            self.writes.append(np.asarray(final_joint_positions).copy())

        def clear_cache(self):
            self.clear_count += 1

        def set_task_properties(self, properties):
            self.properties.append(dict(properties))

    class StubBaseController:
        def __init__(self, cfg, robot):
            self.mode = cfg.mode
            self.rmp_controller = object()
            self._last_success = False
            self._init_collect_mode(cfg, robot)

        def _init_collect_mode(self, cfg, robot):
            del cfg, robot

    class StubPickController:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class StubPourController:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured.append(kwargs)

    class StubTaskUtils:
        @classmethod
        def get_instance(cls):
            return cls()

    package_modules = {
        "controllers": _module("controllers"),
        "controllers.atomic_actions": _module("controllers.atomic_actions"),
        "controllers.atomic_actions.contact_pick_controller": _module(
            "controllers.atomic_actions.contact_pick_controller",
            ContactPickController=StubPickController,
        ),
        "controllers.atomic_actions.pick_controller": _module(
            "controllers.atomic_actions.pick_controller",
            PickController=StubPickController,
        ),
        "controllers.atomic_actions.pour_controller": _module(
            "controllers.atomic_actions.pour_controller",
            PourController=StubPourController,
        ),
        "controllers.base_controller": _module(
            "controllers.base_controller", BaseController=StubBaseController
        ),
        "utils.task_utils": _module("utils.task_utils", TaskUtils=StubTaskUtils),
    }
    package_modules["controllers"].__path__ = []
    package_modules["controllers.atomic_actions"].__path__ = []
    for name, module in package_modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "controllers.pour_controller_finalize_test",
        REPO_ROOT / "controllers/pour_controller.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    cfg = SimpleNamespace(
        mode="collect",
        online_fluid=SimpleNamespace(
                enabled=True,
                expert_control_profile="stabilized_online_fluid_v1",
                expert_pour_height_offsets_m=[0.4, 0.14],
                expert_pour_target_offset_m=[0.0, 0.05, 0.0],
                expert_pour_target_orientation_wxyz=[
                    -0.061628416716219346,
                    0.7044160264027586,
                    0.06162841671621935,
                    0.7044160264027587,
                ],
            ),
        )
    controller = module.PourTaskController(cfg, robot=object())
    np.testing.assert_array_equal(
        controller._expert_pick_gripper_offset_object, np.zeros(3)
    )
    assert controller._expert_pick_target_orientation_wxyz is None
    collector = StubCollector()
    controller.data_collector = collector
    controller.current_phase = module.Phase.POURING
    controller._check_phase_success = lambda: True
    state = {"joint_positions": np.arange(9, dtype=np.float64)}

    _action, done, controller_success = controller._step_collect(state)

    assert done is True
    assert controller_success is True
    assert collector.writes == []
    evaluation = {
        "metric_policy_id": "level1_pour_transfer_v1",
        "camera_contract": {"id": "v2", "sha256": "a" * 64},
        "expert_episode_accepted": True,
        "final_particle_counts": {"target": 3557, "tabletop_spill": 14},
    }
    controller.finalize_collection_episode(
        accepted=True,
        final_joint_positions=state["joint_positions"][:-1],
        evaluation=evaluation,
    )
    assert len(collector.writes) == 1
    np.testing.assert_array_equal(collector.writes[0], np.arange(8))
    assert collector.properties == [{"online_fluid_evaluation": evaluation}]
    with pytest.raises(RuntimeError, match="collection_episode_already_finalized"):
        controller.finalize_collection_episode(
            accepted=True,
            final_joint_positions=state["joint_positions"][:-1],
            evaluation=evaluation,
        )

    rejected = module.PourTaskController(cfg, robot=object())
    rejected_collector = StubCollector()
    rejected.data_collector = rejected_collector
    rejected.current_phase = module.Phase.POURING
    rejected._check_phase_success = lambda: True
    rejected._step_collect(state)
    rejected.finalize_collection_episode(
        accepted=False,
        final_joint_positions=state["joint_positions"][:-1],
        evaluation={**evaluation, "expert_episode_accepted": False},
    )
    assert rejected_collector.writes == []
    assert rejected_collector.clear_count == 1

    timed_out = module.PourTaskController(cfg, robot=object())
    timed_out_collector = StubCollector()
    timed_out.data_collector = timed_out_collector
    action, done, success = timed_out.abort_online_fluid_collection_episode(
        "max_observations_per_episode_reached"
    )
    assert (action, done, success) == (None, True, False)
    assert timed_out.current_phase == module.Phase.FINISHED
    assert timed_out._last_failure_reason == "max_observations_per_episode_reached"
    timed_out.finalize_collection_episode(
        accepted=False,
        final_joint_positions=np.arange(8),
        evaluation={**evaluation, "expert_episode_accepted": False},
    )
    assert timed_out_collector.clear_count == 1


def _load_contact_pick_controller(monkeypatch):
    modules = {
        "isaacsim": _module("isaacsim"),
        "isaacsim.core": _module("isaacsim.core"),
        "isaacsim.core.api": _module("isaacsim.core.api"),
        "isaacsim.core.api.controllers": _module(
            "isaacsim.core.api.controllers", BaseController=_StubIsaacBaseController
        ),
        "isaacsim.core.utils": _module("isaacsim.core.utils"),
        "isaacsim.core.utils.rotations": _module(
            "isaacsim.core.utils.rotations",
            euler_angles_to_quat=lambda _angles: np.asarray(
                [1.0, 0.0, 0.0, 0.0], dtype=np.float64
            ),
        ),
        "isaacsim.core.utils.stage": _module(
            "isaacsim.core.utils.stage", get_stage_units=lambda: 1.0
        ),
        "isaacsim.core.utils.types": _module(
            "isaacsim.core.utils.types", ArticulationAction=_StubArticulationAction
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(
        "atomic_contact_pick_controller_test",
        REPO_ROOT / "controllers/atomic_actions/contact_pick_controller.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _contact_pick_controller(module, **overrides):
    kwargs = {
        "name": "contact_pick",
        "cspace_controller": _StubCspaceController(),
        "control_dt": 1.0 / 30.0,
        "pregrasp_distance": 0.10,
        "insert_distance": 0.02,
        "approach_speed": 3.0,
        "close_speed": 3.0,
        "settle_duration": 0.0,
        "contact_settle_duration": 0.0,
        "hold_duration": 0.0,
        "contact_timeout": 10.0,
    }
    kwargs.update(overrides)
    return module.ContactPickController(
        **kwargs,
    )


def _forward_contact_pick(
    controller,
    *,
    contact_qualified=False,
    contact_failure_reason=None,
    source_position=None,
    source_orientation_xyzw=None,
    gripper_position=None,
    current_joint_positions=None,
    end_effector_orientation=None,
    current_end_effector_orientation=None,
    approach_direction=None,
    grasp_offset=None,
    lift_height=0.10,
    phase_certificates=None,
):
    source = np.asarray(
        [0.30, 0.10, 0.84]
        if source_position is None
        else source_position,
        dtype=np.float64,
    )
    return controller.forward(
        source_position=source,
        source_orientation_xyzw=np.asarray(
            [0.0, 0.0, 0.0, 1.0]
            if source_orientation_xyzw is None
            else source_orientation_xyzw,
            dtype=np.float64,
        ),
        current_joint_positions=np.asarray(
            np.zeros(9, dtype=np.float64)
            if current_joint_positions is None
            else current_joint_positions,
            dtype=np.float64,
        ),
        gripper_position=np.asarray(
            source if gripper_position is None else gripper_position,
            dtype=np.float64,
        ),
        end_effector_orientation=np.asarray(
            [1.0, 0.0, 0.0, 0.0]
            if end_effector_orientation is None
            else end_effector_orientation,
            dtype=np.float64,
        ),
        current_end_effector_orientation=(
            None
            if current_end_effector_orientation is None
            else np.asarray(
                current_end_effector_orientation, dtype=np.float64
            )
        ),
        approach_direction=np.asarray(
            [0.0, 0.0, -1.0]
            if approach_direction is None
            else approach_direction,
            dtype=np.float64,
        ),
        grasp_offset=np.asarray(
            [0.0, 0.0, 0.0] if grasp_offset is None else grasp_offset,
            dtype=np.float64,
        ),
        lift_height=lift_height,
        gripper_distance=0.028,
        contact_qualified=contact_qualified,
        contact_failure_reason=contact_failure_reason,
        phase_certificates=phase_certificates,
    )


def _phase_certificates(phase, *, ready):
    required = {"SETTLE": 60, "PRECONTACT_SETTLE": 60, "CLOSE": 5, "CONTACT_SETTLE": 60}
    return {
        name: {
            "consecutive_steps": (
                count if ready else count - 1
            ) if name == phase else 0,
            "required_steps": count,
            "ready": ready if name == phase else False,
        }
        for name, count in required.items()
    }


def _contact_pick_open_joints(controller, *, joint_count=9):
    evidence = controller.control_evidence()
    joints = np.zeros(joint_count, dtype=np.float64)
    for index in evidence["finger_joint_indices"]:
        joints[index] = evidence["open_position_m"]
    return joints


def _advance_contact_pick_to_align(module, controller, *, source_position=None):
    source = np.asarray(
        [0.30, 0.10, 0.84]
        if source_position is None
        else source_position,
        dtype=np.float64,
    )
    pregrasp = source + np.asarray([0.0, 0.0, 0.10])
    target_orientation = np.asarray([1.0, 0.0, 0.0, 0.0])
    open_joints = _contact_pick_open_joints(controller)

    _forward_contact_pick(
        controller,
        source_position=source,
        gripper_position=source,
    )
    assert controller.current_event == module.ContactPickEvent.PREGRASP
    _forward_contact_pick(
        controller,
        source_position=source,
        gripper_position=source,
        current_joint_positions=open_joints,
        current_end_effector_orientation=target_orientation,
    )
    assert controller.current_event == module.ContactPickEvent.PREGRASP
    _forward_contact_pick(
        controller,
        source_position=source,
        gripper_position=pregrasp,
        current_joint_positions=open_joints,
        current_end_effector_orientation=target_orientation,
    )
    assert controller.current_event == module.ContactPickEvent.ALIGN
    return source


def _advance_contact_pick_to_close(module, controller):
    source = _advance_contact_pick_to_align(module, controller)
    align = source + np.asarray([0.0, 0.0, 0.02])
    target_orientation = np.asarray([1.0, 0.0, 0.0, 0.0])

    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=target_orientation,
    )
    assert controller.current_event == module.ContactPickEvent.INSERT
    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=target_orientation,
    )
    assert controller.current_event == module.ContactPickEvent.SETTLE
    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=target_orientation,
    )
    assert controller.current_event == module.ContactPickEvent.CLOSE
    return source


def test_contact_pick_waits_for_external_settle_certificate_before_close(
    monkeypatch,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        require_external_phase_certificates=True,
    )
    source = _advance_contact_pick_to_align(module, controller)
    align = source + np.asarray([0.0, 0.0, 0.02])
    orientation = np.asarray([1.0, 0.0, 0.0, 0.0])

    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.INSERT
    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.SETTLE

    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=orientation,
        phase_certificates=_phase_certificates("SETTLE", ready=False),
    )
    assert controller.current_event == module.ContactPickEvent.SETTLE
    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=orientation,
        phase_certificates=_phase_certificates("SETTLE", ready=True),
    )

    assert controller.current_event == module.ContactPickEvent.CLOSE
    assert controller.control_evidence()["last_emitted_phase"] == "CLOSE"


def test_contact_pick_exposes_controlled_contact_evidence_phases(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)

    assert [event.name for event in module.ContactPickEvent] == [
        "PREGRASP",
        "ALIGN",
        "INSERT",
        "SETTLE",
        "PRECONTACT_SETTLE",
        "CLOSE",
        "CONTACT_SETTLE",
        "LIFT",
        "HOLD",
    ]
    evidence = controller.control_evidence()
    assert evidence["phase"] == "PREGRASP"
    assert evidence["open_position_m"] == pytest.approx(0.040)


def _intended_precontact_evidence(
    *,
    physics_step=120,
    sides=("left",),
    controller=None,
):
    if controller is None:
        phase = "INSERT"
        target_token = build_arm_target_token(
            tool_position_stage_units=[0.0, 0.0, 0.0],
            tool_orientation_wxyz=[1.0, 0.0, 0.0, 0.0],
            control_position_stage_units=[0.0, 0.0, 0.0],
            control_orientation_wxyz=[1.0, 0.0, 0.0, 0.0],
            tool_frame="tool_center",
            control_frame="right_gripper",
            stage_units_m=1.0,
        )
        control_index = 0
    else:
        control = controller.control_evidence()
        phase = control["last_emitted_phase"]
        target_token = copy.deepcopy(control["last_emitted_target_token"])
        control_index = control["last_emitted_control_index"]
    semantic_kind = {"INSERT": "ARM_INSERT", "SETTLE": "ARM_SETTLE"}.get(
        phase,
        "ARM_INSERT",
    )
    return {
        "authority": "controlled_contact_complete_manifold_v1",
        "physics_step": physics_step,
        "sides": list(sides),
        "records": [
            {
                "class": "INTENDED_PRECONTACT",
                "side": side,
                "pair": {
                    "body_paths": [
                        f"/World/Franka/panda_{side}finger",
                        "/World/beaker2",
                    ]
                },
            }
            for side in sides
        ],
        "evidence_sha256": "d" * 64,
        "applied_receipt": {
            "authority": "controlled_action_applied_receipt_v1",
            "phase": phase,
            "semantic_action_kind": semantic_kind,
            "channel": "arm",
            "action_sha256": "a" * 64,
            "target_token": target_token,
            "target_token_sha256": target_token["sha256"],
            "control_index": control_index,
            "action_index": control_index,
            "apply_index": control_index,
            "interval_index": control_index,
            "applied": True,
        },
    }


def test_contact_pick_latches_first_insert_contact_and_holds_current_target(
    monkeypatch,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        insert_distance=0.001,
        approach_speed=0.006,
        precontact_settle_duration=2.0 / 30.0,
    )
    source = _advance_contact_pick_to_align(module, controller)
    align = source + [0.0, 0.0, 0.001]
    orientation = np.asarray([1.0, 0.0, 0.0, 0.0])
    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.INSERT
    controller._cspace_controller.calls.clear()

    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=orientation,
    )
    emitted_target = controller._cspace_controller.calls[-1][
        "target_end_effector_position"
    ].copy()
    assert emitted_target[2] == pytest.approx(align[2] - 0.0002)

    evidence = _intended_precontact_evidence(controller=controller)
    assert controller.latch_intended_precontact(evidence) is True
    assert controller.latch_intended_precontact(
        _intended_precontact_evidence(
            physics_step=121,
            sides=("right",),
            controller=controller,
        )
    ) is False
    assert controller.current_event == module.ContactPickEvent.PRECONTACT_SETTLE
    latched = controller.control_evidence()
    assert latched["precontact_latched"] is True
    assert latched["precontact_physics_step"] == 120
    assert latched["precontact_sides"] == ["left"]
    assert latched["precontact_applied_phase"] == "INSERT"
    assert latched["last_emitted_semantic_action_kind"] == "ARM_INSERT"
    np.testing.assert_array_equal(latched["precontact_hold_target"], emitted_target)
    assert latched["contact_acquired"] is False

    controller._cspace_controller.calls.clear()
    _forward_contact_pick(
        controller,
        gripper_position=emitted_target,
        current_end_effector_orientation=orientation,
    )
    np.testing.assert_array_equal(
        controller._cspace_controller.calls[-1]["target_end_effector_position"],
        emitted_target,
    )
    assert controller.current_event == module.ContactPickEvent.PRECONTACT_SETTLE
    assert controller.control_evidence()["last_emitted_semantic_action_kind"] == (
        "ARM_PRECONTACT_SETTLE"
    )
    _forward_contact_pick(
        controller,
        gripper_position=emitted_target,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.CLOSE
    assert controller.control_evidence()["close_command_emitted"] is False


def test_contact_pick_precontact_latch_handles_insert_and_settle_transition_edges(
    monkeypatch,
):
    module = _load_contact_pick_controller(monkeypatch)
    orientation = np.asarray([1.0, 0.0, 0.0, 0.0])

    insert_edge = _contact_pick_controller(module)
    source = _advance_contact_pick_to_align(module, insert_edge)
    align = source + [0.0, 0.0, 0.02]
    _forward_contact_pick(
        insert_edge,
        gripper_position=align,
        current_end_effector_orientation=orientation,
    )
    _forward_contact_pick(
        insert_edge,
        gripper_position=source,
        current_end_effector_orientation=orientation,
    )
    assert insert_edge.current_event == module.ContactPickEvent.SETTLE
    assert insert_edge.control_evidence()["last_emitted_phase"] == "INSERT"
    assert insert_edge.latch_intended_precontact(
        _intended_precontact_evidence(controller=insert_edge)
    ) is True
    assert insert_edge.control_evidence()["phase_history"][-2:] == [
        "INSERT",
        "PRECONTACT_SETTLE",
    ]

    settle_edge = _contact_pick_controller(module)
    source = _advance_contact_pick_to_close(module, settle_edge)
    assert settle_edge.current_event == module.ContactPickEvent.CLOSE
    assert settle_edge.control_evidence()["last_emitted_phase"] == "SETTLE"
    assert settle_edge.latch_intended_precontact(
        _intended_precontact_evidence(
            physics_step=130,
            controller=settle_edge,
        )
    ) is True
    evidence = settle_edge.control_evidence()
    assert evidence["phase_history"][-2:] == ["SETTLE", "PRECONTACT_SETTLE"]
    assert evidence["close_command_emitted"] is False


def test_contact_pick_precontact_rejects_target_token_mismatch(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = _advance_contact_pick_to_align(module, controller)
    align = source + [0.0, 0.0, 0.02]
    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=np.asarray([1.0, 0.0, 0.0, 0.0]),
    )
    _forward_contact_pick(controller, gripper_position=source)
    evidence = _intended_precontact_evidence(controller=controller)
    wrong = build_arm_target_token(
        tool_position_stage_units=[0.0, 0.0, 99.0],
        tool_orientation_wxyz=[1.0, 0.0, 0.0, 0.0],
        control_position_stage_units=[0.0, 0.0, 99.0],
        control_orientation_wxyz=[1.0, 0.0, 0.0, 0.0],
        tool_frame="tool_center",
        control_frame="right_gripper",
        stage_units_m=1.0,
    )
    evidence["applied_receipt"]["target_token"] = wrong
    evidence["applied_receipt"]["target_token_sha256"] = wrong["sha256"]

    with pytest.raises(
        RuntimeError,
        match="contact_pick_precontact_target_token_mismatch",
    ):
        controller.latch_intended_precontact(evidence)


def test_contact_pick_precontact_requires_applied_insert_or_settle_before_close(
    monkeypatch,
):
    module = _load_contact_pick_controller(monkeypatch)
    before_insert = _contact_pick_controller(module)
    with pytest.raises(RuntimeError, match="contact_pick_precontact_phase_invalid"):
        before_insert.latch_intended_precontact(_intended_precontact_evidence())

    after_close = _contact_pick_controller(module)
    source = _advance_contact_pick_to_close(module, after_close)
    _forward_contact_pick(after_close, gripper_position=source)
    assert after_close.control_evidence()["close_command_emitted"] is True
    with pytest.raises(RuntimeError, match="contact_pick_precontact_after_close"):
        after_close.latch_intended_precontact(_intended_precontact_evidence())


def test_contact_pick_precontact_does_not_seed_bilateral_success_and_reset_clears(
    monkeypatch,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        precontact_settle_duration=0.0,
        terminate_after_contact_settle=True,
    )
    source = _advance_contact_pick_to_align(module, controller)
    align = source + [0.0, 0.0, 0.02]
    orientation = np.asarray([1.0, 0.0, 0.0, 0.0])
    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.INSERT
    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=orientation,
    )
    assert controller.control_evidence()["last_emitted_phase"] == "INSERT"
    controller.latch_intended_precontact(
        _intended_precontact_evidence(controller=controller)
    )
    hold_target = np.asarray(
        controller.control_evidence()["precontact_hold_target"], dtype=np.float64
    )
    _forward_contact_pick(
        controller,
        gripper_position=hold_target,
        current_end_effector_orientation=orientation,
        contact_qualified=False,
    )
    assert controller.current_event == module.ContactPickEvent.CLOSE
    assert controller.control_evidence()["contact_acquired"] is False

    _forward_contact_pick(
        controller,
        gripper_position=hold_target,
        contact_qualified=False,
    )
    assert controller.current_event == module.ContactPickEvent.CLOSE
    _forward_contact_pick(
        controller,
        gripper_position=hold_target,
        contact_qualified=True,
    )
    assert controller.current_event == module.ContactPickEvent.CONTACT_SETTLE

    controller.reset()
    evidence = controller.control_evidence()
    assert evidence["precontact_latched"] is False
    assert evidence["precontact_physics_step"] is None
    assert evidence["precontact_sides"] == []
    assert evidence["precontact_hold_target"] is None


def test_contact_pick_confirms_later_bilateral_open_before_any_arm_action(
    monkeypatch,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        open_position=0.039,
        open_position_tolerance=0.0003,
    )
    indices = (7, 8)
    already_open = np.zeros(9, dtype=np.float64)
    already_open[list(indices)] = 0.039

    first = _forward_contact_pick(
        controller,
        current_joint_positions=already_open,
    )

    assert first.kwargs["joint_positions"][7:9] == [0.039, 0.039]
    assert controller._cspace_controller.calls == []
    evidence = controller.control_evidence()
    assert evidence["open_command_count"] == 1
    assert evidence["open_position_ready"] is False
    assert evidence["open_confirmed_control_index"] is None
    assert evidence["first_arm_command_control_index"] is None

    asymmetric = already_open.copy()
    asymmetric[8] = 0.039 - 0.0003 - 1.0e-9
    repeated = _forward_contact_pick(
        controller,
        current_joint_positions=asymmetric,
    )

    assert repeated.kwargs["joint_positions"][7:9] == [0.039, 0.039]
    assert controller._cspace_controller.calls == []
    assert controller.control_evidence()["open_position_ready"] is False

    exact_boundary = already_open.copy()
    exact_boundary[7] = 0.039 - 0.0003
    exact_boundary[8] = 0.039 + 0.0003
    confirmed = _forward_contact_pick(
        controller,
        current_joint_positions=exact_boundary,
    )

    assert confirmed.kwargs["joint_positions"][7:9] == [0.039, 0.039]
    assert controller._cspace_controller.calls == []
    evidence = controller.control_evidence()
    assert evidence["open_command_count"] == 3
    assert evidence["open_position_ready"] is True
    assert evidence["open_confirmed_control_index"] == 3
    assert evidence["first_arm_command_control_index"] is None

    source = np.asarray([0.30, 0.10, 0.84], dtype=np.float64)
    pregrasp = source + np.asarray([0.0, 0.0, 0.10])
    arm_action = _forward_contact_pick(
        controller,
        gripper_position=pregrasp,
        current_joint_positions=already_open,
        current_end_effector_orientation=[1.0, 0.0, 0.0, 0.0],
    )

    assert arm_action.kwargs["target_end_effector_position"] is not None
    evidence = controller.control_evidence()
    assert evidence["open_command_count"] >= 2
    assert evidence["first_arm_command_control_index"] == 4
    assert (
        evidence["open_confirmed_control_index"]
        < evidence["first_arm_command_control_index"]
    )
    assert evidence["arm_before_open_violation"] is False
    assert evidence["arm_action_count"] == 1
    assert evidence["finger_action_count"] == 3
    assert evidence["noop_action_count"] == 0
    assert evidence["last_emitted_phase"] == "PREGRASP"
    assert evidence["last_emitted_action_kind"] == "arm"


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"position_threshold": np.nan}, "contact_pick_position_threshold_invalid"),
        ({"open_position": 0.0}, "contact_pick_open_position_invalid"),
        ({"open_position": 0.0400001}, "contact_pick_open_position_invalid"),
        (
            {"open_position_tolerance": 0.0},
            "contact_pick_open_position_tolerance_invalid",
        ),
        (
            {"open_position": 0.01, "open_position_tolerance": 0.0100001},
            "contact_pick_open_position_tolerance_invalid",
        ),
        (
            {"orientation_threshold_degrees": 180.0001},
            "contact_pick_orientation_threshold_degrees_invalid",
        ),
    ],
)
def test_contact_pick_rejects_invalid_geometry_thresholds(
    monkeypatch,
    overrides,
    error,
):
    module = _load_contact_pick_controller(monkeypatch)

    with pytest.raises(ValueError, match=error):
        _contact_pick_controller(module, **overrides)


def test_contact_pick_latches_grasp_frame_on_first_observation(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = np.asarray([0.30, 0.10, 0.84], dtype=np.float64)
    pregrasp = source + np.asarray([0.0, 0.0, 0.10])
    latched_orientation = np.asarray([0.5, 0.5, 0.5, 0.5])

    _forward_contact_pick(
        controller,
        source_position=source,
        end_effector_orientation=latched_orientation,
    )
    _forward_contact_pick(
        controller,
        source_position=source,
        current_joint_positions=_contact_pick_open_joints(controller),
        end_effector_orientation=np.asarray([1.0, 0.0, 0.0, 0.0]),
    )
    moved_source = source + np.asarray([0.002, 0.0, 0.0])
    _forward_contact_pick(
        controller,
        source_position=moved_source,
        gripper_position=pregrasp,
        end_effector_orientation=np.asarray([1.0, 0.0, 0.0, 0.0]),
    )

    call = controller._cspace_controller.calls[-1]
    np.testing.assert_allclose(call["target_end_effector_position"], pregrasp)
    np.testing.assert_allclose(
        call["target_end_effector_orientation"], latched_orientation
    )
    assert controller.terminal_failure_reason is None


def test_contact_pick_maps_frozen_tool_pose_to_right_gripper(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        control_to_end_effector_matrix_m=(
            _right_gripper_to_tool_center_matrix_m()
        ),
    )
    source = np.asarray([0.30, 0.10, 0.84], dtype=np.float64)
    pregrasp = source + np.asarray([0.0, 0.0, 0.10])
    tool_orientation = np.asarray([0.0, 0.0, 1.0, 0.0])

    _forward_contact_pick(
        controller,
        source_position=source,
        end_effector_orientation=tool_orientation,
    )
    _forward_contact_pick(
        controller,
        source_position=source,
        current_joint_positions=_contact_pick_open_joints(controller),
        end_effector_orientation=tool_orientation,
    )
    _forward_contact_pick(
        controller,
        source_position=source,
        gripper_position=pregrasp,
        end_effector_orientation=tool_orientation,
    )

    call = controller._cspace_controller.calls[-1]
    np.testing.assert_allclose(
        call["target_end_effector_position"],
        pregrasp + [0.0, 0.0, 0.0034],
        atol=1.0e-12,
    )
    np.testing.assert_allclose(
        np.abs(call["target_end_effector_orientation"]),
        [0.0, 1.0, 0.0, 0.0],
        atol=1.0e-12,
    )
    evidence = controller.control_evidence()
    assert evidence["end_effector_frame"] == "tool_center"
    assert evidence["control_frame"] == "right_gripper"


def test_contact_pick_uses_configured_finger_joint_indices(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        finger_joint_indices=(2, 4),
    )
    joints = np.zeros(5, dtype=np.float64)
    source = _advance_contact_pick_to_close(module, controller)

    action = _forward_contact_pick(
        controller,
        gripper_position=source,
        current_joint_positions=joints,
    )

    assert action.kwargs["joint_positions"][2] == pytest.approx(0.028)
    assert action.kwargs["joint_positions"][4] == pytest.approx(0.028)
    assert controller.control_evidence()["finger_joint_indices"] == [2, 4]


@pytest.mark.parametrize(
    "position,orientation,reason",
    [
        (
            [0.30201, 0.10, 0.84],
            [0.0, 0.0, 0.0, 1.0],
            "source_translation_exceeded_before_contact",
        ),
        (
            [0.30, 0.10, 0.84],
            [
                0.0,
                0.0,
                np.sin(np.radians(1.01) / 2.0),
                np.cos(np.radians(1.01) / 2.0),
            ],
            "source_tilt_exceeded_before_contact",
        ),
    ],
)
def test_contact_pick_fails_closed_on_precontact_source_motion(
    monkeypatch,
    position,
    orientation,
    reason,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    _forward_contact_pick(controller)
    controller._cspace_controller.calls.clear()

    action = _forward_contact_pick(
        controller,
        source_position=position,
        source_orientation_xyzw=orientation,
    )

    assert controller.is_done() is True
    assert controller.terminal_failure_reason == reason
    assert controller._cspace_controller.calls == []
    assert action.kwargs["joint_positions"] == [None] * 9


def test_contact_pick_supports_explicit_side_body_approach(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = np.asarray([0.30, 0.10, 0.84], dtype=np.float64)
    approach = np.asarray([1.0, 0.0, 0.0])
    offset = np.asarray([0.0, 0.02, 0.0])
    expected_pregrasp = source + offset - 0.10 * approach

    _forward_contact_pick(
        controller,
        source_position=source,
        approach_direction=approach,
        grasp_offset=offset,
    )
    _forward_contact_pick(
        controller,
        source_position=source,
        current_joint_positions=_contact_pick_open_joints(controller),
        approach_direction=approach,
        grasp_offset=offset,
    )
    _forward_contact_pick(
        controller,
        source_position=source,
        gripper_position=expected_pregrasp,
        approach_direction=approach,
        grasp_offset=offset,
    )

    np.testing.assert_allclose(
        controller._cspace_controller.calls[-1][
            "target_end_effector_position"
        ],
        expected_pregrasp,
    )


def test_contact_pick_align_waits_for_frozen_orientation(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = np.asarray([0.30, 0.10, 0.84], dtype=np.float64)
    pregrasp = source + np.asarray([0.0, 0.0, 0.10])
    align = source + np.asarray([0.0, 0.0, 0.02])
    target = np.asarray([1.0, 0.0, 0.0, 0.0])

    _forward_contact_pick(
        controller,
        end_effector_orientation=target,
        current_end_effector_orientation=target,
    )
    _forward_contact_pick(
        controller,
        current_joint_positions=_contact_pick_open_joints(controller),
        end_effector_orientation=target,
        current_end_effector_orientation=target,
    )
    _forward_contact_pick(
        controller,
        gripper_position=pregrasp,
        current_end_effector_orientation=target,
    )
    six_degrees = np.radians(6.0) / 2.0
    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=[
            np.cos(six_degrees),
            np.sin(six_degrees),
            0.0,
            0.0,
        ],
    )
    assert controller.current_event == module.ContactPickEvent.ALIGN
    assert controller.control_evidence()["alignment_error_degrees"] == pytest.approx(
        6.0
    )

    five_degrees = np.radians(5.0) / 2.0
    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=-np.asarray(
            [np.cos(five_degrees), np.sin(five_degrees), 0.0, 0.0]
        ),
    )
    assert controller.current_event == module.ContactPickEvent.INSERT


@pytest.mark.parametrize("quaternion_sign", [1.0, -1.0])
def test_contact_pick_align_exact_position_and_orientation_boundaries_pass(
    monkeypatch,
    quaternion_sign,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        position_threshold=0.005,
        orientation_threshold_degrees=5.0,
    )
    source = np.zeros(3, dtype=np.float64)
    _advance_contact_pick_to_align(
        module,
        controller,
        source_position=source,
    )
    half_angle = np.radians(5.0) / 2.0

    _forward_contact_pick(
        controller,
        source_position=source,
        gripper_position=[0.005, 0.0, 0.02],
        current_end_effector_orientation=quaternion_sign
        * np.asarray([np.cos(half_angle), np.sin(half_angle), 0.0, 0.0]),
    )

    assert controller.current_event == module.ContactPickEvent.INSERT


@pytest.mark.parametrize("outside_gate", ["position", "orientation"])
def test_contact_pick_align_epsilon_outside_boundaries_does_not_advance(
    monkeypatch,
    outside_gate,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        position_threshold=0.005,
        orientation_threshold_degrees=5.0,
    )
    source = np.zeros(3, dtype=np.float64)
    _advance_contact_pick_to_align(
        module,
        controller,
        source_position=source,
    )
    position = np.asarray([0.0, 0.0, 0.02])
    angle_degrees = 0.0
    if outside_gate == "position":
        position[0] = np.nextafter(0.005, np.inf)
    else:
        angle_degrees = 5.0 + 1.0e-8
    half_angle = np.radians(angle_degrees) / 2.0

    _forward_contact_pick(
        controller,
        source_position=source,
        gripper_position=position,
        current_end_effector_orientation=[
            np.cos(half_angle),
            np.sin(half_angle),
            0.0,
            0.0,
        ],
    )

    assert controller.current_event == module.ContactPickEvent.ALIGN


def test_contact_pick_align_missing_current_orientation_does_not_advance(
    monkeypatch,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = _advance_contact_pick_to_align(module, controller)
    align = source + np.asarray([0.0, 0.0, 0.02])

    _forward_contact_pick(
        controller,
        source_position=source,
        gripper_position=align,
        current_end_effector_orientation=None,
    )

    assert controller.current_event == module.ContactPickEvent.ALIGN
    assert controller.control_evidence()["alignment_error_degrees"] is None


def test_contact_pick_insert_starts_at_frozen_align_and_moves_world_z_only(
    monkeypatch,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        position_threshold=0.001,
        insert_distance=0.00045,
        approach_speed=0.006,
    )
    source = _advance_contact_pick_to_align(module, controller)
    align = source + np.asarray([0.0, 0.0, 0.00045])
    measured_align = align + np.asarray([0.0005, -0.0005, 0.0])
    target_orientation = np.asarray([1.0, 0.0, 0.0, 0.0])

    _forward_contact_pick(
        controller,
        source_position=source,
        gripper_position=measured_align,
        current_end_effector_orientation=target_orientation,
    )
    assert controller.current_event == module.ContactPickEvent.INSERT
    controller._cspace_controller.calls.clear()

    moved_source = source + np.asarray([0.001, 0.0, 0.0])
    for _ in range(3):
        _forward_contact_pick(
            controller,
            source_position=moved_source,
            gripper_position=source,
            current_end_effector_orientation=target_orientation,
        )

    targets = np.asarray(
        [
            call["target_end_effector_position"]
            for call in controller._cspace_controller.calls
        ]
    )
    expected_z = np.asarray(
        [align[2] - 0.0002, align[2] - 0.0004, source[2]]
    )
    np.testing.assert_array_equal(targets[:, :2], np.tile(align[:2], (3, 1)))
    np.testing.assert_allclose(targets[:, 2], expected_z, atol=1.0e-15)
    steps = np.abs(np.diff(np.concatenate(([align[2]], targets[:, 2]))))
    assert np.all(steps <= 0.006 / 30.0 + 1.0e-15)
    assert targets[-1, 2] == source[2]
    assert controller.current_event == module.ContactPickEvent.SETTLE
    evidence = controller.control_evidence()
    np.testing.assert_array_equal(evidence["align_position"], align)
    np.testing.assert_array_equal(evidence["insert_waypoint"], source)


def test_contact_pick_sixty_millimeter_insert_emits_exactly_300_arm_commands(
    monkeypatch,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        insert_distance=0.060,
        approach_speed=0.006,
    )
    source = _advance_contact_pick_to_align(module, controller)
    align = source + np.asarray([0.0, 0.0, 0.060])
    orientation = np.asarray([1.0, 0.0, 0.0, 0.0])
    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.INSERT
    controller._cspace_controller.calls.clear()
    initial_arm_count = controller.control_evidence()["arm_action_count"]
    emitted = []

    for _ in range(301):
        if controller.current_event != module.ContactPickEvent.INSERT:
            break
        _forward_contact_pick(
            controller,
            gripper_position=source,
            current_end_effector_orientation=orientation,
        )
        evidence = controller.control_evidence()
        emitted.append(
            (
                evidence["last_emitted_phase"],
                evidence["last_emitted_action_kind"],
                controller._cspace_controller.calls[-1][
                    "target_end_effector_position"
                ].copy(),
            )
        )

    assert controller.current_event == module.ContactPickEvent.SETTLE
    assert len(emitted) == 300
    assert all(
        phase == "INSERT" and action_kind == "arm"
        for phase, action_kind, _target in emitted
    )
    assert (
        controller.control_evidence()["arm_action_count"] - initial_arm_count
        == 300
    )
    np.testing.assert_array_equal(emitted[299][2], source)
    assert len(controller._cspace_controller.calls) == 300


@pytest.mark.parametrize("drift", ["position", "orientation", "missing_orientation"])
def test_contact_pick_settle_drift_resets_timer_and_cannot_emit_close(
    monkeypatch,
    drift,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        settle_duration=2.0 / 30.0,
        position_threshold=0.005,
        orientation_threshold_degrees=5.0,
    )
    source = _advance_contact_pick_to_align(module, controller)
    align = source + np.asarray([0.0, 0.0, 0.02])
    orientation = np.asarray([1.0, 0.0, 0.0, 0.0])
    _forward_contact_pick(
        controller,
        gripper_position=align,
        current_end_effector_orientation=orientation,
    )
    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.SETTLE

    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.SETTLE

    drifted_position = source.copy()
    drifted_orientation = orientation.copy()
    if drift == "position":
        drifted_position[0] += 0.005 + 1.0e-8
    elif drift == "orientation":
        half_angle = np.radians(5.0 + 1.0e-6) / 2.0
        drifted_orientation = np.asarray(
            [np.cos(half_angle), np.sin(half_angle), 0.0, 0.0]
        )
    else:
        drifted_orientation = None

    action = _forward_contact_pick(
        controller,
        gripper_position=drifted_position,
        current_end_effector_orientation=drifted_orientation,
    )

    assert "target_end_effector_position" in action.kwargs
    assert controller.current_event == module.ContactPickEvent.SETTLE
    assert controller.control_evidence()["close_command_emitted"] is False

    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.SETTLE
    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_end_effector_orientation=orientation,
    )
    assert controller.current_event == module.ContactPickEvent.CLOSE


def test_contact_pick_close_cannot_bypass_pending_contact_gate(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = _advance_contact_pick_to_close(module, controller)
    controller._cspace_controller.calls.clear()

    for _ in range(3):
        action = _forward_contact_pick(
            controller,
            gripper_position=source,
            contact_qualified=False,
        )

        assert controller.current_event == module.ContactPickEvent.CLOSE
        assert action.kwargs["joint_positions"][7] == pytest.approx(0.028)
        assert action.kwargs["joint_positions"][8] == pytest.approx(0.028)

    assert controller.grasp_contact_requested() is True
    assert "CONTACT_SETTLE" not in controller.control_evidence()["phase_history"]
    assert controller._cspace_controller.calls == []


def test_contact_request_starts_on_first_actual_close_command(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = _advance_contact_pick_to_close(module, controller)

    assert controller.current_event == module.ContactPickEvent.CLOSE
    assert controller.grasp_contact_requested() is False

    _forward_contact_pick(controller, gripper_position=source)

    assert controller.grasp_contact_requested() is True
    evidence = controller.control_evidence()
    assert evidence["close_command_emitted"] is True
    assert evidence["close_action_control_index"] == (
        evidence["control_invocation_count"]
    )
    assert evidence["last_emitted_phase"] == "CLOSE"
    assert evidence["last_emitted_action_kind"] == "finger"


def test_contact_pick_qualified_close_holds_measured_aperture(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = _advance_contact_pick_to_close(module, controller)
    joints = np.zeros(9, dtype=np.float64)
    joints[7:9] = 0.031

    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_joint_positions=joints,
        contact_qualified=False,
    )

    acquired_action = _forward_contact_pick(
        controller,
        gripper_position=source,
        current_joint_positions=joints,
        contact_qualified=True,
    )

    assert controller.current_event == module.ContactPickEvent.CONTACT_SETTLE
    assert acquired_action.kwargs["joint_positions"][7] == pytest.approx(0.031)
    settled_action = _forward_contact_pick(
        controller,
        gripper_position=source,
        current_joint_positions=joints,
        contact_qualified=True,
    )
    assert settled_action.kwargs["joint_positions"][7] == pytest.approx(0.031)
    assert controller.current_event == module.ContactPickEvent.LIFT


def test_contact_pick_probe_completes_at_contact_settle_without_lift(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        terminate_after_contact_settle=True,
    )
    source = _advance_contact_pick_to_close(module, controller)
    _forward_contact_pick(controller, gripper_position=source)
    assert controller.current_event == module.ContactPickEvent.CLOSE
    closed_joints = np.zeros(9, dtype=np.float64)
    closed_joints[7:9] = 0.028
    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_joint_positions=closed_joints,
        contact_qualified=True,
    )
    assert controller.current_event == module.ContactPickEvent.CONTACT_SETTLE
    controller._cspace_controller.calls.clear()

    action = _forward_contact_pick(
        controller,
        gripper_position=source,
        current_joint_positions=closed_joints,
        contact_qualified=True,
    )

    assert action.kwargs["joint_positions"][7] == pytest.approx(0.028)
    assert controller.is_done() is True
    assert controller.current_event == module.ContactPickEvent.CONTACT_SETTLE
    assert controller.grasp_contact_requested() is True
    evidence = controller.control_evidence()
    assert evidence["terminate_after_contact_settle"] is True
    assert evidence["probe_completed"] is True
    assert evidence["lift_command_emitted"] is False
    assert "LIFT" not in evidence["phase_history"]
    assert "HOLD" not in evidence["phase_history"]
    assert evidence["last_emitted_phase"] == "CONTACT_SETTLE"
    assert evidence["last_emitted_action_kind"] == "finger"
    assert controller._cspace_controller.calls == []
    assert controller.lift_command_emitted() is False


def test_contact_pick_lift_uses_rate_limited_waypoints(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = _advance_contact_pick_to_close(module, controller)
    _forward_contact_pick(controller, gripper_position=source)
    assert controller.current_event == module.ContactPickEvent.CLOSE
    closed_joints = np.zeros(9, dtype=np.float64)
    closed_joints[7:9] = 0.028
    _forward_contact_pick(
        controller,
        gripper_position=source,
        current_joint_positions=closed_joints,
        contact_qualified=True,
    )
    assert controller.current_event == module.ContactPickEvent.CONTACT_SETTLE

    close_action = _forward_contact_pick(
        controller,
        gripper_position=source,
        current_joint_positions=closed_joints,
        contact_qualified=True,
    )

    assert controller.current_event == module.ContactPickEvent.LIFT
    assert close_action.kwargs["joint_positions"][7] == pytest.approx(0.028)
    assert controller.lift_command_emitted() is False
    controller._cspace_controller.calls.clear()

    for _ in range(3):
        _forward_contact_pick(
            controller,
            gripper_position=source,
            contact_qualified=True,
            lift_height=0.10,
        )

    assert controller.lift_command_emitted() is True
    evidence = controller.control_evidence()
    assert evidence["lift_command_emitted"] is True
    assert evidence["last_emitted_phase"] == "LIFT"
    assert evidence["last_emitted_action_kind"] == "arm"
    lift_targets = np.asarray(
        [call["target_end_effector_position"] for call in controller._cspace_controller.calls]
    )
    increments = np.diff(
        np.concatenate(([source[2]], lift_targets[:, 2]))
    )
    assert np.all(increments > 0.0)
    assert np.all(increments <= 0.05 / 30.0 + 1.0e-12)
    assert lift_targets[-1, 2] < source[2] + 0.10


def test_contact_pick_reset_clears_all_ordered_action_evidence(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = _advance_contact_pick_to_close(module, controller)
    _forward_contact_pick(controller, gripper_position=source)
    _forward_contact_pick(
        controller,
        gripper_position=source,
        contact_qualified=True,
    )
    _forward_contact_pick(
        controller,
        gripper_position=source,
        contact_qualified=True,
    )
    assert controller.current_event == module.ContactPickEvent.LIFT
    _forward_contact_pick(
        controller,
        gripper_position=source,
        contact_qualified=True,
    )
    assert controller.lift_command_emitted() is True

    controller.reset()

    evidence = controller.control_evidence()
    assert controller.current_event == module.ContactPickEvent.PREGRASP
    assert controller.grasp_contact_requested() is False
    assert controller.lift_command_emitted() is False
    assert evidence["phase_history"] == ["PREGRASP"]
    assert evidence["attempt_latched"] is False
    assert evidence["control_invocation_count"] == 0
    assert evidence["open_command_count"] == 0
    assert evidence["open_position_ready"] is False
    assert evidence["open_confirmed_control_index"] is None
    assert evidence["first_arm_command_control_index"] is None
    assert evidence["arm_before_open_violation"] is False
    assert evidence["arm_action_count"] == 0
    assert evidence["finger_action_count"] == 0
    assert evidence["noop_action_count"] == 0
    assert evidence["close_action_control_index"] is None
    assert evidence["close_command_emitted"] is False
    assert evidence["lift_command_emitted"] is False
    assert evidence["last_emitted_phase"] is None
    assert evidence["last_emitted_action_kind"] is None
    assert controller._cspace_controller.reset_count == 1


@pytest.mark.parametrize(
    "terminal_reason,qualify_first",
    [
        ("contact_timeout", False),
        ("grasp_lost", True),
    ],
)
def test_contact_pick_timeout_or_grasp_loss_is_latched_terminal(
    monkeypatch,
    terminal_reason,
    qualify_first,
):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(module)
    source = _advance_contact_pick_to_close(module, controller)
    _forward_contact_pick(controller, gripper_position=source)
    if qualify_first:
        closed_joints = np.zeros(9, dtype=np.float64)
        closed_joints[7:9] = 0.028
        _forward_contact_pick(
            controller,
            gripper_position=source,
            current_joint_positions=closed_joints,
            contact_qualified=True,
        )
        _forward_contact_pick(
            controller,
            gripper_position=source,
            current_joint_positions=closed_joints,
            contact_qualified=True,
        )
        assert controller.current_event == module.ContactPickEvent.LIFT

    controller._cspace_controller.calls.clear()
    _forward_contact_pick(
        controller,
        gripper_position=source,
        contact_qualified=False,
        contact_failure_reason=terminal_reason,
    )

    assert controller.is_done() is True
    assert controller.terminal_failure_reason == terminal_reason
    assert controller._cspace_controller.calls == []

    _forward_contact_pick(
        controller,
        gripper_position=source,
        contact_qualified=True,
    )
    assert controller.is_done() is True
    assert controller.terminal_failure_reason == terminal_reason
    assert controller._cspace_controller.calls == []


def test_contact_pick_has_internal_terminal_contact_timeout(monkeypatch):
    module = _load_contact_pick_controller(monkeypatch)
    controller = _contact_pick_controller(
        module,
        contact_timeout=2.0 / 30.0,
    )
    source = _advance_contact_pick_to_close(module, controller)

    _forward_contact_pick(controller, gripper_position=source)
    assert controller.is_done() is False
    assert controller.current_event == module.ContactPickEvent.CLOSE
    _forward_contact_pick(controller, gripper_position=source)
    assert controller.is_done() is False
    assert controller.current_event == module.ContactPickEvent.CLOSE
    _forward_contact_pick(controller, gripper_position=source)

    assert controller.is_done() is True
    assert controller.terminal_failure_reason == "contact_timeout"
    evidence = controller.control_evidence()
    assert "CONTACT_SETTLE" not in evidence["phase_history"]
    assert evidence["noop_action_count"] == 1
    assert evidence["last_emitted_phase"] == "CLOSE"
    assert evidence["last_emitted_action_kind"] == "noop"


def _load_contact_pour_task_controller(monkeypatch):
    legacy_pick_init_calls = []
    legacy_pick_forward_calls = []
    contact_pick_init_calls = []
    contact_pick_forward_calls = []
    contact_pick_precontact_latch_calls = []
    pour_init_calls = []
    pour_forward_calls = []

    class StubBaseController:
        def __init__(self, cfg, robot):
            self.mode = cfg.mode
            self.robot = robot
            self.control_dt = 1.0 / 30.0
            self.gripper_control = object()
            self._last_success = False
            self.rmp_controller = SimpleNamespace(
                get_end_effector_orientation_wxyz=lambda: np.asarray(
                    [1.0, 0.0, 0.0, 0.0], dtype=np.float64
                )
            )
            self._init_collect_mode(cfg, robot)

        def _init_collect_mode(self, cfg, robot):
            del cfg, robot

    class StubLegacyPickController:
        def __init__(self, **kwargs):
            legacy_pick_init_calls.append(dict(kwargs))
            self._event = 0
            self._last_emitted_event = None
            self.close_emitted = False
            self.lift_emitted = False

        def is_done(self):
            return False

        def forward(self, **kwargs):
            legacy_pick_forward_calls.append(dict(kwargs))
            self._last_emitted_event = self._event
            if self._event == 4:
                self.close_emitted = True
            elif self._event == 5:
                self.lift_emitted = True
            return _StubArticulationAction(**kwargs)

        def grasp_contact_requested(self):
            return self.close_emitted

        def lift_command_emitted(self):
            return self.lift_emitted

        def lift_is_next_action(self):
            return self._event == 5 and not self.lift_emitted

        def control_evidence(self):
            return {
                "event": self._event,
                "last_emitted_event": self._last_emitted_event,
                "close_command_emitted": self.close_emitted,
                "lift_command_emitted": self.lift_emitted,
            }

    class StubContactPickController:
        def __init__(self, **kwargs):
            contact_pick_init_calls.append(dict(kwargs))
            self.contact_requested = False
            self.terminal_failure_reason = None
            self.last_semantic_action_kind = None
            self.last_control_index = None
            self.last_target_token = None

        def is_done(self):
            return self.terminal_failure_reason is not None

        def forward(self, **kwargs):
            contact_pick_forward_calls.append(dict(kwargs))
            self.last_semantic_action_kind = "GRIPPER_OPEN"
            self.last_control_index = len(contact_pick_forward_calls) - 1
            self.last_target_token = build_finger_target_token(
                joint_indices=(7, 8),
                joint_targets=(0.04, 0.04),
            )
            if kwargs.get("contact_failure_reason") is not None:
                self.terminal_failure_reason = kwargs["contact_failure_reason"]
            return _StubArticulationAction(**kwargs)

        def grasp_contact_requested(self):
            return self.contact_requested

        def lift_command_emitted(self):
            return False

        def latch_intended_precontact(self, evidence):
            contact_pick_precontact_latch_calls.append(copy.deepcopy(evidence))
            return True

        def control_evidence(self):
            return {
                "phase": "PREGRASP",
                "last_emitted_phase": "PREGRASP",
                "last_emitted_semantic_action_kind": self.last_semantic_action_kind,
                "last_emitted_control_index": self.last_control_index,
                "last_emitted_target_token": copy.deepcopy(
                    self.last_target_token
                ),
                "lift_command_emitted": False,
                "done": False,
                "terminal_failure_reason": self.terminal_failure_reason,
            }

    class StubPourController:
        def __init__(self, **kwargs):
            pour_init_calls.append(dict(kwargs))
            self.pour_entry_orientation_evidence = None

        def is_done(self):
            return False

        def forward(self, **kwargs):
            pour_forward_calls.append(dict(kwargs))
            return _StubArticulationAction(**kwargs)

    class StubTaskUtils:
        @classmethod
        def get_instance(cls):
            return cls()

        def get_pour_threshold(self, _item_name, _source_size):
            return 0.05

    package_modules = {
        "controllers": _module("controllers"),
        "controllers.atomic_actions": _module("controllers.atomic_actions"),
        "controllers.atomic_actions.contact_pick_controller": _module(
            "controllers.atomic_actions.contact_pick_controller",
            ContactPickController=StubContactPickController,
        ),
        "controllers.atomic_actions.pick_controller": _module(
            "controllers.atomic_actions.pick_controller",
            PickController=StubLegacyPickController,
        ),
        "controllers.atomic_actions.pour_controller": _module(
            "controllers.atomic_actions.pour_controller",
            PourController=StubPourController,
        ),
        "controllers.base_controller": _module(
            "controllers.base_controller", BaseController=StubBaseController
        ),
        "utils.task_utils": _module(
            "utils.task_utils", TaskUtils=StubTaskUtils
        ),
    }
    package_modules["controllers"].__path__ = []
    package_modules["controllers.atomic_actions"].__path__ = []
    for name, module in package_modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "controllers.contact_pour_controller_contract_test",
        REPO_ROOT / "controllers/pour_controller.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    calls = SimpleNamespace(
        legacy_pick_init=legacy_pick_init_calls,
        legacy_pick_forward=legacy_pick_forward_calls,
        contact_pick_init=contact_pick_init_calls,
        contact_pick_forward=contact_pick_forward_calls,
        contact_pick_precontact_latch=contact_pick_precontact_latch_calls,
        pour_init=pour_init_calls,
        pour_forward=pour_forward_calls,
    )
    return module, calls


def _contact_pour_cfg():
    return SimpleNamespace(
        mode="collect",
        online_fluid=SimpleNamespace(
            enabled=True,
            expert_control_profile="contact_pick_v1",
            source_ownership="contact_friction_dynamic_v1",
            execution_mode="production_pour_v1",
            expert_pick_gripper_offset_object_m=[0.0, 0.0, 0.0],
            expert_pick_lift_height_m=0.10,
            expert_pick_position_threshold_m=0.001,
            expert_pick_open_position_m=0.039,
            expert_pick_open_position_tolerance_m=0.0003,
            expert_pick_orientation_threshold_degrees=2.0,
            grasp_finger_joint_target_m=0.037,
            finger_joint_indices=[7, 8],
            grasp_target_frame_name="tool_center",
            rmpflow_control_frame_name="right_gripper",
            rmpflow_control_to_grasp_matrix_m=(
                _right_gripper_to_tool_center_matrix_m().tolist()
            ),
            expert_pour_speed_rad_s=-0.35,
            expert_pour_height_offsets_m=[0.4, 0.14],
            expert_pour_target_offset_m=[0.0, 0.05, 0.0],
        ),
    )


def _native_pour_cfg(*, execution_mode="production_pour_v1", mode="collect"):
    cfg = _contact_pour_cfg()
    cfg.mode = mode
    fluid = cfg.online_fluid
    fluid.expert_control_profile = "native_expert_v1"
    fluid.execution_mode = execution_mode
    fluid.expert_pick_lift_height_m = 0.5
    fluid.grasp_finger_joint_target_m = 0.028
    fluid.expert_pour_speed_rad_s = -1.0
    del fluid.expert_pick_gripper_offset_object_m
    del fluid.grasp_target_frame_name
    del fluid.rmpflow_control_frame_name
    del fluid.rmpflow_control_to_grasp_matrix_m
    return cfg


def _contact_pour_state():
    return {
        "object_position": np.asarray([0.30, 0.10, 0.84], dtype=np.float64),
        "object_quaternion": np.asarray(
            [0.0, 0.0, 0.0, 1.0], dtype=np.float64
        ),
        "object_name": "beaker2",
        "object_size": np.asarray([0.08, 0.08, 0.12], dtype=np.float64),
        "joint_positions": np.zeros(9, dtype=np.float64),
        "gripper_position": np.asarray([0.30, 0.10, 0.84], dtype=np.float64),
        "target_position": np.asarray([0.50, -0.20, 0.84], dtype=np.float64),
    }


def test_contact_mode_selects_sibling_and_passes_explicit_grasp_geometry(
    monkeypatch,
):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _contact_pour_cfg()
    controller = module.PourTaskController(cfg, robot=object())
    controller._check_phase_success = lambda: False
    state = _contact_pour_state()
    object_position_before = state["object_position"].copy()

    controller._step_collect(state)

    assert calls.legacy_pick_init == []
    assert len(calls.contact_pick_init) == 1
    assert calls.contact_pick_init[0]["control_dt"] == pytest.approx(1 / 30)
    assert calls.contact_pick_init[0]["position_threshold"] == pytest.approx(
        cfg.online_fluid.expert_pick_position_threshold_m
    )
    assert calls.contact_pick_init[0]["open_position"] == pytest.approx(
        cfg.online_fluid.expert_pick_open_position_m
    )
    assert calls.contact_pick_init[0]["open_position_tolerance"] == pytest.approx(
        cfg.online_fluid.expert_pick_open_position_tolerance_m
    )
    assert calls.contact_pick_init[0][
        "orientation_threshold_degrees"
    ] == pytest.approx(
        cfg.online_fluid.expert_pick_orientation_threshold_degrees
    )
    np.testing.assert_array_equal(
        calls.contact_pick_init[0]["control_to_end_effector_matrix_m"],
        _right_gripper_to_tool_center_matrix_m(),
    )
    assert calls.contact_pick_init[0]["finger_joint_indices"] == (7, 8)
    assert calls.contact_pick_init[0]["terminate_after_contact_settle"] is False
    np.testing.assert_array_equal(
        calls.pour_init[0]["control_to_end_effector_matrix_m"],
        _right_gripper_to_tool_center_matrix_m(),
    )
    forward = calls.contact_pick_forward[-1]
    np.testing.assert_array_equal(forward["source_position"], object_position_before)
    np.testing.assert_array_equal(
        forward["source_orientation_xyzw"], state["object_quaternion"]
    )
    np.testing.assert_array_equal(state["object_position"], object_position_before)
    assert forward["lift_height"] == pytest.approx(
        cfg.online_fluid.expert_pick_lift_height_m
    )
    assert forward["gripper_distance"] == pytest.approx(
        cfg.online_fluid.grasp_finger_joint_target_m
    )
    np.testing.assert_allclose(forward["approach_direction"], [0.0, 0.0, -1.0])
    np.testing.assert_array_equal(forward["grasp_offset"], np.zeros(3))
    assert "vertical_approach" not in forward
    assert "picking_position" not in forward
    assert controller.online_fluid_grasp_attachment_requested() is False
    assert controller.online_fluid_grasp_contact_requested() is False
    controller.pick_controller.contact_requested = True
    assert controller.online_fluid_grasp_contact_requested() is True


def test_pour_task_delegates_controlled_precontact_to_existing_pick_controller(
    monkeypatch,
):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    controller = module.PourTaskController(_contact_pour_cfg(), robot=object())
    evidence = _intended_precontact_evidence(physics_step=321, sides=("left", "right"))

    assert controller.latch_intended_precontact(evidence) is True
    assert calls.contact_pick_precontact_latch == [evidence]
    assert calls.contact_pick_precontact_latch[0] is not evidence


def test_pour_task_exposes_preapply_controlled_contact_action_context(monkeypatch):
    module, _calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _contact_pour_cfg()
    cfg.online_fluid.execution_mode = "contact_acquisition_probe_v1"
    controller = module.PourTaskController(cfg, robot=object())
    controller._check_phase_success = lambda: False
    controller.step(_contact_pour_state())

    context = controller.controlled_contact_action_context()

    assert context == {
        "phase": "PREGRASP",
        "controller_phase": "PREGRASP",
        "semantic_action_kind": "GRIPPER_OPEN",
        "control_index": 0,
        "target_token": build_finger_target_token(
            joint_indices=(7, 8),
            joint_targets=(0.04, 0.04),
        ),
        "terminal_latched": False,
        "finger_joint_indices": [7, 8],
    }


@pytest.mark.parametrize(
    "field,value,error",
    [
        (
            "expert_pick_position_threshold_m",
            np.nan,
            "expert_pick_position_threshold_m_invalid",
        ),
        (
            "expert_pick_position_threshold_m",
            0.0,
            "expert_pick_position_threshold_m_invalid",
        ),
        (
            "expert_pick_open_position_m",
            np.inf,
            "expert_pick_open_position_m_invalid",
        ),
        (
            "expert_pick_open_position_m",
            0.040001,
            "expert_pick_open_position_m_invalid",
        ),
        (
            "expert_pick_open_position_tolerance_m",
            np.nan,
            "expert_pick_open_position_tolerance_m_invalid",
        ),
        (
            "expert_pick_open_position_tolerance_m",
            0.039001,
            "expert_pick_open_position_tolerance_m_invalid",
        ),
        (
            "expert_pick_orientation_threshold_degrees",
            np.inf,
            "expert_pick_orientation_threshold_degrees_invalid",
        ),
        (
            "expert_pick_orientation_threshold_degrees",
            180.0001,
            "expert_pick_orientation_threshold_degrees_invalid",
        ),
    ],
)
def test_contact_mode_rejects_invalid_geometry_threshold_config(
    monkeypatch,
    field,
    value,
    error,
):
    module, _calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _contact_pour_cfg()
    setattr(cfg.online_fluid, field, value)

    with pytest.raises(ValueError, match=error):
        module.PourTaskController(cfg, robot=object())


def test_contact_acquisition_probe_finishes_without_entering_pour(monkeypatch):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _contact_pour_cfg()
    cfg.online_fluid.execution_mode = "contact_acquisition_probe_v1"
    controller = module.PourTaskController(cfg, robot=object())
    state = _contact_pour_state()
    state["online_fluid_grasp"] = {
        "qualified": True,
        "probe_qualified_now": True,
        "failure_reason": None,
    }
    controller.pick_controller.is_done = lambda: True

    action, done, success = controller.step(state)

    assert calls.contact_pick_init[0]["terminate_after_contact_settle"] is True
    assert (action, done, success) == (None, True, True)
    assert controller.current_phase == module.Phase.FINISHED
    assert calls.contact_pick_forward == []
    assert calls.pour_forward == []
    evidence = controller.online_fluid_control_evidence()
    assert evidence["execution_mode"] == "contact_acquisition_probe_v1"
    assert evidence["contact_acquisition_probe"] is True
    assert evidence["pour_forward_invocation_count"] == 0
    assert evidence["contact_pick"]["lift_command_emitted"] is False
    assert controller.online_fluid_grasp_lift_requested() is False


@pytest.mark.parametrize(
    "execution_mode,qualified,probe_qualified_now,expected",
    [
        ("contact_acquisition_probe_v1", True, False, False),
        ("contact_acquisition_probe_v1", False, True, True),
        ("production_pour_v1", True, False, True),
    ],
)
def test_contact_pick_input_uses_current_contact_only_in_probe_mode(
    monkeypatch,
    execution_mode,
    qualified,
    probe_qualified_now,
    expected,
):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _contact_pour_cfg()
    cfg.online_fluid.execution_mode = execution_mode
    controller = module.PourTaskController(cfg, robot=object())
    controller._check_phase_success = lambda: False
    state = _contact_pour_state()
    state["online_fluid_grasp"] = {
        "qualified": qualified,
        "probe_qualified_now": probe_qualified_now,
        "failure_reason": None,
    }

    action, done, success = controller.step(state)

    assert action is not None
    assert (done, success) == (False, False)
    assert calls.contact_pick_forward[-1]["contact_qualified"] is expected


def test_contact_probe_outer_success_rejects_stale_latched_contact(monkeypatch):
    module, _calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _contact_pour_cfg()
    cfg.online_fluid.execution_mode = "contact_acquisition_probe_v1"
    controller = module.PourTaskController(cfg, robot=object())
    state = _contact_pour_state()
    controller.initial_position = state["object_position"].copy()
    controller.pick_controller.is_done = lambda: True
    state["online_fluid_grasp"] = {
        "qualified": True,
        "probe_qualified_now": False,
        "failure_reason": None,
    }
    controller.state = state

    assert controller._check_phase_success() is False
    assert controller.last_error_info["grasp_qualified"] is False


def test_contact_acquisition_probe_is_collect_only(monkeypatch):
    module, _calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _native_pour_cfg(
        execution_mode="contact_acquisition_probe_v1",
        mode="infer",
    )

    with pytest.raises(
        ValueError, match="contact_acquisition_probe_requires_collect_mode"
    ):
        module.PourTaskController(cfg, robot=object())


def _qualified_native_probe_state(**grasp_overrides):
    state = _contact_pour_state()
    grasp = {
        "qualified": True,
        "failure_reason": None,
        "probe_qualified_now": True,
        "close_command_observed": True,
        "lift_command_observed": False,
    }
    grasp.update(grasp_overrides)
    state["online_fluid_grasp"] = grasp
    return state


@pytest.mark.parametrize("pending_event", [4, 5])
def test_qualified_native_probe_finishes_before_another_pick_forward(
    monkeypatch,
    pending_event,
):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    controller = module.PourTaskController(
        _native_pour_cfg(execution_mode="contact_acquisition_probe_v1"),
        robot=object(),
    )
    controller.pick_controller._event = pending_event
    controller.pick_controller._last_emitted_event = 4
    controller.pick_controller.close_emitted = True

    action, done, success = controller.step(_qualified_native_probe_state())

    assert (action, done, success) == (None, True, True)
    assert controller.current_phase == module.Phase.FINISHED
    assert calls.legacy_pick_forward == []
    assert calls.pour_forward == []
    evidence = controller.online_fluid_control_evidence()
    assert evidence["native_pick"]["event"] == pending_event
    assert evidence["native_pick"]["last_emitted_event"] == 4
    assert evidence["pour_forward_invocation_count"] == 0


@pytest.mark.parametrize(
    "grasp_overrides,controller_close,missing_grasp_key",
    [
        ({"probe_qualified_now": False}, True, None),
        ({"close_command_observed": False}, True, None),
        ({}, False, None),
        ({}, True, "lift_command_observed"),
    ],
)
def test_native_probe_does_not_pass_without_current_contact_and_both_closes(
    monkeypatch,
    grasp_overrides,
    controller_close,
    missing_grasp_key,
):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    controller = module.PourTaskController(
        _native_pour_cfg(execution_mode="contact_acquisition_probe_v1"),
        robot=object(),
    )
    controller.pick_controller._event = 4
    controller.pick_controller._last_emitted_event = 4 if controller_close else 3
    controller.pick_controller.close_emitted = controller_close

    state = _qualified_native_probe_state(**grasp_overrides)
    if missing_grasp_key is not None:
        del state["online_fluid_grasp"][missing_grasp_key]

    action, done, success = controller.step(state)

    assert action is not None
    assert (done, success) == (False, False)
    assert controller.current_phase == module.Phase.PICKING
    assert len(calls.legacy_pick_forward) == 1


def test_native_probe_cannot_fall_back_to_legacy_done_success(monkeypatch):
    module, _calls = _load_contact_pour_task_controller(monkeypatch)
    controller = module.PourTaskController(
        _native_pour_cfg(execution_mode="contact_acquisition_probe_v1"),
        robot=object(),
    )
    controller.pick_controller._event = 5
    controller.pick_controller._last_emitted_event = 4
    controller.pick_controller.close_emitted = True
    controller.pick_controller.is_done = lambda: True
    state = _qualified_native_probe_state(close_command_observed=False)
    controller.initial_position = state["object_position"].copy()
    controller.state = state

    assert controller._check_phase_success() is False


@pytest.mark.parametrize(
    "controller_lift,monitor_lift",
    [(True, False), (False, True)],
)
def test_native_probe_aborts_if_lift_was_applied_or_observed(
    monkeypatch,
    controller_lift,
    monitor_lift,
):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    controller = module.PourTaskController(
        _native_pour_cfg(execution_mode="contact_acquisition_probe_v1"),
        robot=object(),
    )
    controller.pick_controller._event = 5
    controller.pick_controller._last_emitted_event = 5 if controller_lift else 4
    controller.pick_controller.close_emitted = True
    controller.pick_controller.lift_emitted = controller_lift

    action, done, success = controller.step(
        _qualified_native_probe_state(lift_command_observed=monitor_lift)
    )

    assert (action, done, success) == (None, True, False)
    assert "lift" in controller._last_failure_reason
    assert calls.legacy_pick_forward == []
    assert calls.pour_forward == []


def test_native_probe_never_applies_pending_lift_after_stale_qualification(
    monkeypatch,
):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    controller = module.PourTaskController(
        _native_pour_cfg(execution_mode="contact_acquisition_probe_v1"),
        robot=object(),
    )
    controller.pick_controller._event = 5
    controller.pick_controller._last_emitted_event = 4
    controller.pick_controller.close_emitted = True
    state = _qualified_native_probe_state(probe_qualified_now=False)
    assert state["online_fluid_grasp"]["qualified"] is True

    action, done, success = controller.step(state)

    assert (action, done, success) == (None, True, False)
    assert "lift" in controller._last_failure_reason
    assert calls.legacy_pick_forward == []


def test_only_exact_contact_ownership_selects_contact_pick_sibling(monkeypatch):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _contact_pour_cfg()
    cfg.online_fluid.source_ownership = "gripper_attached_kinematic_vessel"
    cfg.online_fluid.expert_control_profile = "stabilized_online_fluid_v1"

    controller = module.PourTaskController(cfg, robot=object())
    controller._check_phase_success = lambda: False
    controller._step_collect(_contact_pour_state())

    assert len(calls.legacy_pick_init) == 1
    assert calls.contact_pick_init == []
    assert len(calls.legacy_pick_forward) == 1
    assert calls.contact_pick_forward == []


def test_native_expert_profile_uses_legacy_pick_under_dynamic_ownership(
    monkeypatch,
):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _native_pour_cfg()

    controller = module.PourTaskController(cfg, robot=object())
    controller._check_phase_success = lambda: False
    state = _contact_pour_state()
    original_position = state["object_position"].copy()

    controller._step_collect(state)

    assert len(calls.legacy_pick_init) == 1
    assert calls.contact_pick_init == []
    forward = calls.legacy_pick_forward[-1]
    np.testing.assert_array_equal(forward["picking_position"], original_position)
    np.testing.assert_allclose(
        forward["end_effector_orientation"],
        module.R.from_euler("xyz", np.radians([0, 90, 30])).as_quat(),
    )
    assert forward["pre_offset_x"] == pytest.approx(0.05)
    assert forward["pre_offset_z"] == pytest.approx(0.05)
    assert forward["after_offset_z"] == pytest.approx(0.5)
    assert "gripper_distances" not in forward
    assert calls.pour_init[0]["direct_control_frame_targets"] is True
    np.testing.assert_array_equal(
        calls.pour_init[0]["control_to_end_effector_matrix_m"], np.eye(4)
    )
    assert controller.online_fluid_grasp_attachment_requested() is False
    assert controller.online_fluid_grasp_contact_requested() is False
    controller.pick_controller.close_emitted = True
    assert controller.online_fluid_grasp_contact_requested() is True
    evidence = controller.online_fluid_control_evidence()
    assert evidence["expert_control_profile"] == "native_expert_v1"
    assert evidence["native_pick"]["close_command_emitted"] is True


def test_native_expert_pour_omits_online_pose_overrides(monkeypatch):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _native_pour_cfg()

    class StubRobot:
        def get_articulation_controller(self):
            return object()

        def get_joint_velocities(self):
            return np.zeros(9, dtype=np.float64)

    controller = module.PourTaskController(cfg, robot=StubRobot())
    controller._check_phase_success = lambda: False
    controller.current_phase = module.Phase.POURING
    controller.active_controller = controller.pour_controller
    controller.initial_size = np.asarray([0.08, 0.08, 0.12], dtype=np.float64)

    controller._step_collect(_contact_pour_state())

    forward = calls.pour_forward[-1]
    assert forward["pour_speed"] == pytest.approx(-1.0)
    assert "source_position" not in forward
    assert "target_end_effector_orientation" not in forward
    assert "current_end_effector_orientation" not in forward
    assert (
        controller.online_fluid_control_evidence()[
            "pour_forward_invocation_count"
        ]
        == 1
    )


def test_production_native_mode_still_emits_pending_lift(monkeypatch):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    controller = module.PourTaskController(_native_pour_cfg(), robot=object())
    controller.pick_controller._event = 5
    controller.pick_controller._last_emitted_event = 4
    controller.pick_controller.close_emitted = True
    state = _contact_pour_state()
    state["online_fluid_grasp"] = {
        "qualified": True,
        "failure_reason": None,
    }

    action, done, success = controller.step(state)

    assert action is not None
    assert (done, success) == (False, False)
    assert len(calls.legacy_pick_forward) == 1
    assert controller.pick_controller._last_emitted_event == 5
    assert controller.pick_controller.lift_emitted is True


def test_native_expert_rejects_lift_before_bilateral_acquisition(monkeypatch):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _native_pour_cfg()
    controller = module.PourTaskController(cfg, robot=object())
    controller._check_phase_success = lambda: False
    controller.pick_controller._event = 5
    state = _contact_pour_state()
    state["online_fluid_grasp"] = {"qualified": False, "failure_reason": None}

    action, done, success = controller._step_collect(state)

    assert (action, done, success) == (None, True, False)
    assert controller._last_failure_reason == (
        "lift_started_before_contact_acquisition"
    )
    assert calls.legacy_pick_forward == []


def test_dynamic_monitor_failure_aborts_native_pour_before_action(monkeypatch):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _native_pour_cfg()
    controller = module.PourTaskController(cfg, robot=object())
    controller._check_phase_success = lambda: False
    controller.current_phase = module.Phase.POURING
    controller.active_controller = controller.pour_controller
    state = _contact_pour_state()
    state["online_fluid_grasp"] = {
        "qualified": False,
        "failure_reason": "grasp_lost",
    }

    action, done, success = controller._step_collect(state)

    assert (action, done, success) == (None, True, False)
    assert controller._last_failure_reason == "grasp_lost"
    assert calls.pour_forward == []


def test_contact_pick_success_requires_qualified_completed_physical_grasp(
    monkeypatch,
):
    module, _calls = _load_contact_pour_task_controller(monkeypatch)
    controller = module.PourTaskController(_contact_pour_cfg(), robot=object())
    controller.initial_position = np.asarray(
        [0.30, 0.10, 0.84], dtype=np.float64
    )
    controller.state = _contact_pour_state()
    controller.state["object_position"] = np.asarray(
        [0.30, 0.10, 0.95], dtype=np.float64
    )

    controller.state["online_fluid_grasp"] = {"qualified": False}
    assert controller._check_phase_success() is False

    controller.state["online_fluid_grasp"] = {"qualified": True}
    assert controller._check_phase_success() is False

    controller.pick_controller.is_done = lambda: True
    controller.state["object_position"][2] = (
        controller.initial_position[2]
        + 0.8 * controller._expert_pick_lift_height_m
    )
    assert controller._check_phase_success() is True


def test_contact_failure_delivered_by_state_terminates_same_control_cycle(
    monkeypatch,
):
    module, _calls = _load_contact_pour_task_controller(monkeypatch)
    controller = module.PourTaskController(_contact_pour_cfg(), robot=object())
    controller._check_phase_success = lambda: False
    state = _contact_pour_state()
    state["online_fluid_grasp"] = {
        "qualified": False,
        "failure_reason": "unexpected_contact_before_close",
    }

    action, done, success = controller._step_collect(state)

    assert action is None
    assert done is True
    assert success is False
    assert controller._last_failure_reason == "unexpected_contact_before_close"


def test_contact_mode_configured_pour_speed_reaches_atomic_pour(monkeypatch):
    module, calls = _load_contact_pour_task_controller(monkeypatch)
    cfg = _contact_pour_cfg()

    class StubRobot:
        def get_articulation_controller(self):
            return object()

        def get_joint_velocities(self):
            return np.zeros(9, dtype=np.float64)

    controller = module.PourTaskController(cfg, robot=StubRobot())
    controller._check_phase_success = lambda: False
    controller.current_phase = module.Phase.POURING
    controller.active_controller = controller.pour_controller
    controller.initial_size = np.asarray([0.08, 0.08, 0.12], dtype=np.float64)

    controller._step_collect(_contact_pour_state())

    assert calls.pour_forward[-1]["pour_speed"] == pytest.approx(
        cfg.online_fluid.expert_pour_speed_rad_s
    )
