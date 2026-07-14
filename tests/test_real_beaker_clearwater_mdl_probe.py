from __future__ import annotations

from pathlib import Path

import pytest
from pxr import Gf, Usd, UsdGeom, UsdShade

from tools.labutopia_fluid import run_real_beaker_clearwater_mdl_probe as probe


def _make_stage() -> Usd.Stage:
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
    old = UsdShade.Material.Define(stage, "/World/Looks/OldLiquid")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(old)
    return stage


def test_clearwater_mdl_input_and_search_roots_are_pinned() -> None:
    verified = probe.verify_clearwater_mdl_input()
    contract = probe.build_mdl_search_contract()

    assert verified == {
        "source_asset": str(probe.MDL_SOURCE_ASSET),
        "source_asset_sha256": (
            "5c86c8545a1e215ec4b99e60eb66f9112ca5952cc66ca13ec0c26687dcfcb930"
        ),
        "sub_identifier": "OmniSurface_ClearWater",
    }
    assert contract["search_paths"] == [
        str(probe.MATERIAL_CLOSURE_ROOT / "mdl"),
        str(probe.MATERIAL_CLOSURE_ROOT / "Base"),
    ]
    assert contract["source_asset"] == str(probe.MDL_SOURCE_ASSET)
    assert len(contract["startup_arguments"]) == 3


def test_clearwater_treatment_authors_only_mdl_material_and_target_binding() -> None:
    stage = _make_stage()
    geometry_before = probe.presentation_geometry_signature(stage)
    root_before = stage.GetRootLayer().ExportToString()

    treatment = probe.apply_clearwater_treatment(stage)

    assert stage.GetRootLayer().ExportToString() == root_before
    assert probe.presentation_geometry_signature(stage) == geometry_before
    assert treatment["authored_spec_paths"] == probe.EXPECTED_TREATMENT_SPEC_PATHS
    assert treatment["source_asset_path"] == str(probe.MDL_SOURCE_ASSET)
    assert treatment["source_asset_resolved_path"] == str(probe.MDL_SOURCE_ASSET)
    assert treatment["sub_identifier"] == "OmniSurface_ClearWater"
    assert treatment["effective_material_path"] == probe.TREATMENT_MATERIAL_PATH
    assert not stage.GetPrimAtPath(
        f"{probe.TREATMENT_MATERIAL_PATH}/PreviewSurface"
    )
    assert probe.validate_clearwater_treatment(stage, treatment["layer"])[
        "verified"
    ] is True


def test_clearwater_treatment_rejects_missing_asset_without_fallback(
    tmp_path: Path,
) -> None:
    stage = _make_stage()
    with pytest.raises(FileNotFoundError, match="clearwater_mdl_source_missing"):
        probe.apply_clearwater_treatment(
            stage,
            source_asset=tmp_path / "missing.mdl",
        )
    assert not stage.GetPrimAtPath(probe.TREATMENT_MATERIAL_PATH)


def test_clearwater_log_validation_fails_closed() -> None:
    with pytest.raises(ValueError, match="log_segment_invalid"):
        probe.validate_clearwater_log_segment(
            {
                "cursor_captured": True,
                "diagnostic_scan_complete": True,
                "segment_byte_count": 0,
                "log_text": "",
            }
        )

    with pytest.raises(RuntimeError, match="clearwater_mdl_compile_failed"):
        probe.validate_clearwater_log_segment(
            {
                "cursor_captured": True,
                "diagnostic_scan_complete": True,
                "segment_byte_count": 80,
                "log_text": (
                    "[Error] [MDLC:COMPILER] OmniSurface_ClearWater "
                    "createMdlModule failed"
                ),
            }
        )

    valid = probe.validate_clearwater_log_segment(
        {
            "cursor_captured": True,
            "diagnostic_scan_complete": True,
            "segment_byte_count": 24,
            "segment_sha256": "a" * 64,
            "log_text": "ClearWater material compiled",
        }
    )
    assert valid["mdl_compile_status"] == "PASS"
    assert valid["diagnostic_scan_complete"] is True
