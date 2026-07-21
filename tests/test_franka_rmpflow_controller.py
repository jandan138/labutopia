from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _module(name, **attributes):
    result = ModuleType(name)
    for key, value in attributes.items():
        setattr(result, key, value)
    return result


def test_rmpflow_reports_current_orientation_in_isaac_wxyz(monkeypatch):
    class MotionPolicyController:
        pass

    modules = {
        "isaacsim": _module("isaacsim"),
        "isaacsim.robot_motion": _module("isaacsim.robot_motion"),
        "isaacsim.robot_motion.motion_generation": _module(
            "isaacsim.robot_motion.motion_generation",
            MotionPolicyController=MotionPolicyController,
        ),
        "isaacsim.core": _module("isaacsim.core"),
        "isaacsim.core.prims": _module(
            "isaacsim.core.prims", SingleArticulation=object
        ),
        "isaacsim.core.utils": _module("isaacsim.core.utils"),
        "isaacsim.core.utils.rotations": _module(
            "isaacsim.core.utils.rotations",
            rot_matrix_to_quat=lambda matrix: np.asarray(
                [0.5, 0.5, 0.5, 0.5], dtype=np.float64
            ),
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "franka_rmpflow_controller_under_test",
        REPO_ROOT / "robots/franka/rmpflow_controller.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    active_positions = np.arange(7, dtype=np.float64)
    position = np.asarray([0.1, 0.2, 0.3], dtype=np.float64)
    rotation = np.eye(3, dtype=np.float64)
    controller = module.RMPFlowController.__new__(module.RMPFlowController)
    controller.articulation_rmp = SimpleNamespace(
        get_active_joints_subset=lambda: SimpleNamespace(
            get_joint_positions=lambda: active_positions
        )
    )
    calls = []
    controller.rmp_flow = SimpleNamespace(
        get_end_effector_pose=lambda joints: calls.append(np.asarray(joints).copy())
        or (position, rotation)
    )

    pose_position, pose_rotation = controller.get_end_effector_pose_world()
    orientation = controller.get_end_effector_orientation_wxyz()

    np.testing.assert_array_equal(calls, [active_positions, active_positions])
    np.testing.assert_array_equal(pose_position, position)
    np.testing.assert_array_equal(pose_rotation, rotation)
    np.testing.assert_array_equal(orientation, [0.5, 0.5, 0.5, 0.5])


def test_rmpflow_forwards_the_explicit_policy_frame_dt(monkeypatch):
    captured = {}

    class MotionPolicyController:
        def __init__(self, *, name, articulation_motion_policy):
            captured["name"] = name
            self._articulation_motion_policy = articulation_motion_policy
            self._motion_policy = articulation_motion_policy.motion_policy

    class ArticulationMotionPolicy:
        def __init__(self, robot, motion_policy, physics_dt):
            captured["physics_dt"] = physics_dt
            self._robot_articulation = robot
            self.motion_policy = motion_policy

    class RmpFlow:
        def __init__(self, **config):
            captured["config"] = config

        def set_robot_base_pose(self, **_kwargs):
            return None

    mg = _module(
        "isaacsim.robot_motion.motion_generation",
        MotionPolicyController=MotionPolicyController,
        ArticulationMotionPolicy=ArticulationMotionPolicy,
        interface_config_loader=SimpleNamespace(
            load_supported_motion_policy_config=lambda *_args: {
                "end_effector_frame_name": "right_gripper"
            }
        ),
        lula=SimpleNamespace(
            motion_policies=SimpleNamespace(RmpFlow=RmpFlow)
        ),
    )
    modules = {
        "isaacsim": _module("isaacsim"),
        "isaacsim.robot_motion": _module("isaacsim.robot_motion"),
        "isaacsim.robot_motion.motion_generation": mg,
        "isaacsim.core": _module("isaacsim.core"),
        "isaacsim.core.prims": _module(
            "isaacsim.core.prims", SingleArticulation=object
        ),
        "isaacsim.core.utils": _module("isaacsim.core.utils"),
        "isaacsim.core.utils.rotations": _module(
            "isaacsim.core.utils.rotations",
            rot_matrix_to_quat=lambda matrix: matrix,
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "franka_rmpflow_controller_dt_under_test",
        REPO_ROOT / "robots/franka/rmpflow_controller.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    robot = SimpleNamespace(
        get_world_pose=lambda: (np.zeros(3), np.asarray([1.0, 0.0, 0.0, 0.0]))
    )

    controller = module.RMPFlowController(
        name="test",
        robot_articulation=robot,
        physics_dt=1 / 30,
    )

    assert captured["physics_dt"] == pytest.approx(1 / 30)
    assert controller.physics_dt == pytest.approx(1 / 30)
    with pytest.raises(ValueError, match="rmpflow_physics_dt_invalid"):
        module.RMPFlowController(
            name="test",
            robot_articulation=robot,
            physics_dt=0.0,
        )
