from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np


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
        or (np.zeros(3), rotation)
    )

    result = controller.get_end_effector_orientation_wxyz()

    np.testing.assert_array_equal(calls, [active_positions])
    np.testing.assert_array_equal(result, [0.5, 0.5, 0.5, 0.5])
