from __future__ import annotations

from pathlib import Path

import pytest
from pxr import Usd, UsdGeom, UsdShade

from tools.labutopia_fluid import run_real_beaker_derived_water_film_probe as film


def _source_mesh_data() -> tuple[Usd.Stage, UsdGeom.Mesh]:
    stage = Usd.Stage.Open(str(film.SOURCE_STAGE), Usd.Stage.LoadNone)
    assert stage
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(film.SOURCE_SURFACE_PATH))
    assert mesh
    return stage, mesh


def test_fixed_source_and_treatment_contract_are_explicit() -> None:
    contract = film.verify_fixed_inputs(film.SOURCE_STAGE)

    assert contract["source_sha256"] == film.EXPECTED_SOURCE_SHA256
    assert contract["proxy_geometry_sha256"] == (
        "8905803d5177e9d2a194720f942c7558847046dffce6b084bc8b66aa36f4a70d"
    )
    assert contract["physical_trace_frame_index"] == 600
    assert contract["source_point_count"] == 386
    assert contract["source_face_count"] == 480
    assert film.FILM_MATERIAL_INPUTS == {
        "diffuseColor": [0.16, 0.52, 0.62],
        "emissiveColor": [0.0, 0.0, 0.0],
        "opacity": 0.72,
        "roughness": 0.06,
        "metallic": 0.0,
        "ior": 1.333,
    }


def test_extract_top_film_geometry_is_exact_and_deterministic() -> None:
    _stage, mesh = _source_mesh_data()
    kwargs = {
        "points": mesh.GetPointsAttr().Get(),
        "normals": mesh.GetNormalsAttr().Get(),
        "face_counts": mesh.GetFaceVertexCountsAttr().Get(),
        "face_indices": mesh.GetFaceVertexIndicesAttr().Get(),
    }

    first = film.extract_top_film_geometry(**kwargs)
    second = film.extract_top_film_geometry(**kwargs)

    assert first == second
    assert first["source_ring_indices"] == list(range(289, 385))
    assert first["source_center_index"] == 385
    assert first["vertex_count"] == 97
    assert first["face_count"] == 96
    assert first["face_vertex_counts"] == [3] * 96
    assert first["face_vertex_indices"][:6] == [96, 0, 1, 96, 1, 2]
    assert first["face_vertex_indices"][-3:] == [96, 95, 0]
    assert first["all_triangles_non_degenerate"] is True
    assert first["all_triangles_upward_wound"] is True
    assert first["total_area_m2"] > 0.0
    assert len(first["geometry_sha256"]) == 64

    corrupted_indices = list(kwargs["face_indices"])
    corrupted_indices[-1] = 383
    with pytest.raises(ValueError, match="source_topology_mismatch"):
        film.extract_top_film_geometry(
            **{**kwargs, "face_indices": corrupted_indices}
        )


def test_apply_treatment_authors_only_presentation_geometry_and_material() -> None:
    source_before = film.SOURCE_STAGE.read_bytes()
    stage, _mesh = _source_mesh_data()

    treatment = film.apply_derived_water_film_treatment(stage)

    assert treatment["verified"] is True
    assert treatment["layer_adds_physx_specs"] is False
    assert treatment["geometry"]["face_count"] == 96
    old_surface = UsdGeom.Imageable(
        stage.GetPrimAtPath(film.SOURCE_SURFACE_PATH)
    )
    assert old_surface.ComputeVisibility() == UsdGeom.Tokens.invisible
    new_prim = stage.GetPrimAtPath(film.FILM_PATH)
    assert new_prim and new_prim.IsA(UsdGeom.Mesh)
    assert not any("physx" in token.lower() for token in new_prim.GetAppliedSchemas())
    assert not any(
        relationship.GetName().lower().startswith("physx")
        for relationship in new_prim.GetRelationships()
    )
    material, _purpose = UsdShade.MaterialBindingAPI(
        new_prim
    ).ComputeBoundMaterial()
    assert material and str(material.GetPath()) == film.FILM_MATERIAL_PATH
    assert film.SOURCE_STAGE.read_bytes() == source_before


def test_validate_zero_step_checkpoints_requires_stopped_zero_state() -> None:
    checkpoints = {
        name: {"physics_step_events": 0, "timeline_stopped": True}
        for name in film.ZERO_STEP_CHECKPOINT_NAMES
    }

    result = film.validate_zero_step_checkpoints(checkpoints)

    assert result["verified"] is True
    assert result["physics_steps_executed"] == 0
    checkpoints["after_final_capture"]["physics_step_events"] = 1
    with pytest.raises(RuntimeError, match="zero_step_checkpoint_invalid"):
        film.validate_zero_step_checkpoints(checkpoints)


def test_validate_two_camera_capture_contract() -> None:
    frames = {
        role: {
            "path": f"/{role}.png",
            "shape": [540, 960, 4],
            "dtype": "uint8",
            "mean": 100.0,
            "std": 20.0,
            "sha256": character * 64,
        }
        for role, character in zip(film.CAMERA_PATHS, "ab")
    }

    result = film.validate_capture_contract({"frames": frames})

    assert result["verified"] is True
    assert result["camera_roles"] == list(film.CAMERA_PATHS)
    frames["pair_context"]["dtype"] = "float32"
    with pytest.raises(ValueError, match="capture_contract_invalid"):
        film.validate_capture_contract({"frames": frames})


def test_record_cleanup_preserves_failed_contract_before_raising() -> None:
    runtime_context: dict[str, object] = {}
    failed_cleanup = {
        "cleanup_complete": False,
        "cleanup_failures": {"pair_context:destroy": "failed"},
    }

    with pytest.raises(RuntimeError, match="replicator_resource_cleanup_failed"):
        film.record_replicator_cleanup(runtime_context, failed_cleanup)

    assert runtime_context["replicator_cleanup"] == failed_cleanup


def test_failure_manifest_is_technical_invalid() -> None:
    manifest = film.build_failure_manifest(RuntimeError("capture_failed"))

    assert manifest["probe_id"] == film.PROBE_ID
    assert manifest["status"] == "INVALID_DERIVED_WATER_FILM_PROBE"
    assert manifest["technically_valid"] is False
    assert manifest["fatal_error"]["message"] == "capture_failed"
