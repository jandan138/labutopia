from __future__ import annotations

from copy import deepcopy

import pytest
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

from tools.labutopia_fluid import run_real_beaker_preview_water_probe as probe


def _make_probe_stage() -> Usd.Stage:
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/CompletedPBD")
    mesh = UsdGeom.Mesh.Define(stage, probe.PRESENTATION_SURFACE_PATH)
    mesh.CreatePointsAttr(
        [
            Gf.Vec3f(-1.0, 0.0, 0.0),
            Gf.Vec3f(1.0, 0.0, 0.0),
            Gf.Vec3f(0.0, 1.0, 0.0),
        ]
    )
    mesh.CreateFaceVertexCountsAttr([3])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2])
    mesh.CreateNormalsAttr([Gf.Vec3f(0.0, 0.0, 1.0)] * 3)
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    prim = mesh.GetPrim()
    prim.CreateAttribute(
        "labutopia:physicalTraceFrameIndex", Sdf.ValueTypeNames.Int, custom=True
    ).Set(probe.EXPECTED_PHYSICAL_FRAME)
    prim.CreateAttribute(
        "labutopia:proxyGeometrySha256", Sdf.ValueTypeNames.String, custom=True
    ).Set(probe.EXPECTED_PROXY_GEOMETRY_SHA256)

    UsdGeom.Camera.Define(stage, probe.CAMERA_PATHS["source_beaker_closeup"])
    UsdGeom.Camera.Define(stage, probe.CAMERA_PATHS["pair_context"])
    old_material = UsdShade.Material.Define(stage, "/World/Looks/OldLiquid")
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(old_material)
    return stage


class _FakeSettings:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def set_bool(self, path: str, value: bool) -> None:
        self.values[path] = value

    def set_int(self, path: str, value: int) -> None:
        self.values[path] = value

    def set_float(self, path: str, value: float) -> None:
        self.values[path] = value

    def get(self, path: str) -> object:
        return self.values.get(path)


def test_fixed_probe_contract_matches_008_control() -> None:
    assert probe.EXPECTED_SOURCE_SHA256 == (
        "c05ec299524cb0d895412ee0c5a1efe7d45c93f7838e512ebd90b0b7bbcc511a"
    )
    assert probe.EXPECTED_PHYSICAL_FRAME == 600
    assert probe.EXPECTED_PROXY_GEOMETRY_SHA256 == (
        "8905803d5177e9d2a194720f942c7558847046dffce6b084bc8b66aa36f4a70d"
    )
    assert probe.CAPTURE_RESOLUTION == (960, 540)
    assert probe.RT_SUBFRAMES == 4
    assert probe.CONTROL_IMAGE_SHA256 == {
        "source_beaker_closeup": (
            "6f127941887c7f3b3175f06cfd78eadfd58b8b932305e48e20b71a72d36c8dbd"
        ),
        "pair_context": (
            "43b9b88f7f75cfc7b726b838a5efcea81ab1ea62797e291ec8af25adcbb90dec"
        ),
    }


def test_stage_contract_requires_frame_geometry_and_two_cameras() -> None:
    stage = _make_probe_stage()
    validated = probe.validate_stage_contract(stage)
    assert validated["physical_trace_frame_index"] == 600
    assert validated["proxy_geometry_sha256"] == probe.EXPECTED_PROXY_GEOMETRY_SHA256
    assert validated["camera_paths"] == probe.CAMERA_PATHS

    stage.GetPrimAtPath(probe.PRESENTATION_SURFACE_PATH).GetAttribute(
        "labutopia:physicalTraceFrameIndex"
    ).Set(599)
    with pytest.raises(ValueError, match="physical_trace_frame"):
        probe.validate_stage_contract(stage)


def test_preview_water_treatment_only_changes_session_material_binding() -> None:
    stage = _make_probe_stage()
    root_before = stage.GetRootLayer().ExportToString()
    geometry_before = probe.presentation_geometry_signature(stage)

    treatment = probe.apply_preview_water_treatment(stage)

    assert stage.GetRootLayer().ExportToString() == root_before
    assert probe.presentation_geometry_signature(stage) == geometry_before
    assert treatment["authored_spec_paths"] == probe.EXPECTED_TREATMENT_SPEC_PATHS
    assert treatment["material_inputs"] == probe.PREVIEW_WATER_INPUTS
    assert treatment["effective_material_path"] == probe.TREATMENT_MATERIAL_PATH
    assert probe.validate_preview_water_treatment(stage, treatment["layer"])[
        "verified"
    ] is True


def test_control_render_settings_are_applied_and_read_back_exactly() -> None:
    settings = _FakeSettings()
    expected = deepcopy(probe.CONTROL_RENDER_SETTINGS)

    result = probe.apply_and_validate_control_render_settings(settings)

    assert settings.values == expected
    assert result == {
        "registry_values": expected,
        "rt_subframes": 4,
        "resolution": [960, 540],
        "readback_verified": True,
    }
