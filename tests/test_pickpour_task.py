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


def _load_pickpour_task(monkeypatch):
    class StubBaseTask:
        pass

    tasks_package = _module("tasks")
    tasks_package.__path__ = []
    modules = {
        "tasks": tasks_package,
        "tasks.base_task": _module("tasks.base_task", BaseTask=StubBaseTask),
        "isaacsim": _module("isaacsim"),
        "isaacsim.core": _module("isaacsim.core"),
        "isaacsim.core.utils": _module("isaacsim.core.utils"),
        "isaacsim.core.utils.prims": _module(
            "isaacsim.core.utils.prims", set_prim_visibility=lambda **_kwargs: None
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(
        "tasks.pickpour_task_under_test", REPO_ROOT / "tasks/pickpour_task.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_pickpour_state_uses_source_root_world_orientation(monkeypatch):
    module = _load_pickpour_task(monkeypatch)
    root_orientation = np.asarray([0.0, 0.0, 0.5, 0.8660254])
    mesh_orientation = np.asarray([0.0, 0.0, 0.0, 1.0])
    world_paths = []
    local_paths = []

    class ObjectUtils:
        def get_world_transform_quat(self, *, object_path):
            world_paths.append(object_path)
            return root_orientation

        def get_transform_quat(self, *, object_path):
            local_paths.append(object_path)
            return mesh_orientation

    task = module.PickPourTask.__new__(module.PickPourTask)
    task.cfg = SimpleNamespace(online_fluid=None)
    task.frame_idx = 4
    task.current_obj_path = "/World/beaker2"
    task.target_path = "/World/beaker1"
    task.object_utils = ObjectUtils()
    task.check_frame_limits = lambda: True
    task.get_basic_state_info = lambda **kwargs: kwargs

    state = task.step()

    assert world_paths == ["/World/beaker2"]
    assert local_paths == []
    np.testing.assert_array_equal(state["additional_info"]["object_quaternion"], root_orientation)
