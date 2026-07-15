from types import ModuleType

import pytest

import isaacsim_compat


def test_legacy_aliases_cover_online_fluid_runtime_imports():
    aliases = isaacsim_compat.LEGACY_MODULE_ALIASES

    assert aliases["isaacsim.core.api"] == "omni.isaac.core"
    assert aliases["isaacsim.core.prims"] == "omni.isaac.core.prims"
    assert aliases["isaacsim.sensors.camera"] == "omni.isaac.sensor"
    assert aliases["isaacsim.robot_motion.motion_generation"] == (
        "omni.isaac.motion_generation"
    )
    assert aliases["isaacsim.storage.native"] == "omni.isaac.nucleus"


def test_installer_registers_legacy_modules_and_parent_attributes():
    modules = {"isaacsim": ModuleType("isaacsim")}
    imported = {}

    def importer(name):
        if name == "isaacsim.core.api":
            raise ModuleNotFoundError(name)
        if name not in imported:
            imported[name] = ModuleType(name)
            if name == "omni.isaac.core.prims":
                imported[name].RigidPrim = type("RigidPrim", (), {})
            if name == "omni.isaac.core.articulations":
                imported[name].Articulation = type("Articulation", (), {})
        return imported[name]

    installed = isaacsim_compat.install_legacy_isaacsim_aliases(
        module_importer=importer,
        module_registry=modules,
    )

    assert installed is True
    assert modules["isaacsim.core.api"] is imported["omni.isaac.core"]
    assert modules["isaacsim.sensors.camera"] is imported["omni.isaac.sensor"]
    assert modules["isaacsim"].core is modules["isaacsim.core"]
    assert modules["isaacsim.core"].api is modules["isaacsim.core.api"]
    assert modules["isaacsim.core.prims"].SingleRigidPrim is (
        modules["isaacsim.core.prims"].RigidPrim
    )
    assert modules["isaacsim.core.prims"].SingleArticulation is (
        modules["isaacsim.core.api.articulations"].Articulation
    )


def test_installer_leaves_modern_isaac_modules_untouched():
    modern_api = ModuleType("isaacsim.core.api")
    modules = {"isaacsim.core.api": modern_api}

    installed = isaacsim_compat.install_legacy_isaacsim_aliases(
        module_importer=lambda name: modern_api,
        module_registry=modules,
    )

    assert installed is False
    assert modules == {"isaacsim.core.api": modern_api}


def test_installer_does_not_mask_a_modern_transitive_import_failure():
    missing = ModuleNotFoundError("No module named 'modern_dependency'")
    missing.name = "modern_dependency"

    with pytest.raises(ModuleNotFoundError) as caught:
        isaacsim_compat.install_legacy_isaacsim_aliases(
            module_importer=lambda name: (_ for _ in ()).throw(missing),
            module_registry={},
        )

    assert caught.value is missing
