"""Import aliases for running the current code on Isaac Sim 4.1."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Callable, MutableMapping


LEGACY_MODULE_ALIASES = {
    "isaacsim.core.api": "omni.isaac.core",
    "isaacsim.core.api.robots": "omni.isaac.core.robots",
    "isaacsim.core.api.robots.robot": "omni.isaac.core.robots.robot",
    "isaacsim.core.api.articulations": "omni.isaac.core.articulations",
    "isaacsim.core.api.controllers": "omni.isaac.core.controllers",
    "isaacsim.core.api.controllers.articulation_controller": (
        "omni.isaac.core.controllers.articulation_controller"
    ),
    "isaacsim.core.prims": "omni.isaac.core.prims",
    "isaacsim.core.prims.impl": "omni.isaac.core.articulations",
    "isaacsim.core.utils": "omni.isaac.core.utils",
    "isaacsim.core.utils.extensions": "omni.isaac.core.utils.extensions",
    "isaacsim.core.utils.numpy": "omni.isaac.core.utils.numpy",
    "isaacsim.core.utils.numpy.rotations": (
        "omni.isaac.core.utils.numpy.rotations"
    ),
    "isaacsim.core.utils.prims": "omni.isaac.core.utils.prims",
    "isaacsim.core.utils.rotations": "omni.isaac.core.utils.rotations",
    "isaacsim.core.utils.semantics": "omni.isaac.core.utils.semantics",
    "isaacsim.core.utils.stage": "omni.isaac.core.utils.stage",
    "isaacsim.core.utils.types": "omni.isaac.core.utils.types",
    "isaacsim.robot.manipulators": "omni.isaac.manipulators",
    "isaacsim.robot.manipulators.grippers": "omni.isaac.manipulators.grippers",
    "isaacsim.robot.manipulators.grippers.gripper": (
        "omni.isaac.manipulators.grippers.gripper"
    ),
    "isaacsim.robot.manipulators.grippers.parallel_gripper": (
        "omni.isaac.manipulators.grippers.parallel_gripper"
    ),
    "isaacsim.robot_motion.motion_generation": "omni.isaac.motion_generation",
    "isaacsim.sensors.camera": "omni.isaac.sensor",
    "isaacsim.sensors.physics": "omni.isaac.sensor",
    "isaacsim.storage.native": "omni.isaac.nucleus",
}

_LEGACY_PARENT_PACKAGES = (
    "isaacsim.core",
    "isaacsim.robot",
    "isaacsim.robot_motion",
    "isaacsim.sensors",
    "isaacsim.storage",
)


def _bind_to_parent(
    name: str,
    module: ModuleType,
    registry: MutableMapping[str, ModuleType],
) -> None:
    parent_name, _, child_name = name.rpartition(".")
    parent = registry.get(parent_name)
    if parent is not None:
        setattr(parent, child_name, module)


def install_legacy_isaacsim_aliases(
    *,
    module_importer: Callable[[str], ModuleType] = importlib.import_module,
    module_registry: MutableMapping[str, ModuleType] | None = None,
) -> bool:
    """Install 4.1 namespace aliases; return False on modern Isaac Sim."""
    registry = sys.modules if module_registry is None else module_registry
    modern_api_name = "isaacsim.core.api"
    try:
        module_importer(modern_api_name)
        return False
    except ModuleNotFoundError as error:
        missing_name = getattr(error, "name", None)
        requested_module_missing = (
            missing_name is None and str(error) == modern_api_name
        ) or (
            bool(missing_name)
            and (
                modern_api_name == missing_name
                or modern_api_name.startswith(f"{missing_name}.")
            )
        )
        if not requested_module_missing:
            raise

    if "isaacsim" not in registry:
        registry["isaacsim"] = module_importer("isaacsim")

    for package_name in _LEGACY_PARENT_PACKAGES:
        package = ModuleType(package_name)
        package.__path__ = []
        registry[package_name] = package
        _bind_to_parent(package_name, package, registry)

    for alias, target in LEGACY_MODULE_ALIASES.items():
        module = module_importer(target)
        registry[alias] = module
        _bind_to_parent(alias, module, registry)

    legacy_prims = registry["isaacsim.core.prims"]
    legacy_articulations = registry["isaacsim.core.api.articulations"]
    legacy_prims.SingleRigidPrim = legacy_prims.RigidPrim
    legacy_prims.SingleArticulation = legacy_articulations.Articulation
    return True
