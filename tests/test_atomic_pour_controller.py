from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


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
