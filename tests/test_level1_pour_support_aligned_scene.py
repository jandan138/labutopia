import copy
import hashlib
import json
from pathlib import Path

import pytest
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

from tools.labutopia_fluid import run_build_level1_pour_support_aligned_scene as aligned
from tools.labutopia_fluid import (
    run_colleague_native_usd_completed_pbd_step_video as frozen_runner,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "level1_pour.yaml"
SOURCE_PATH = (
    REPO_ROOT
    / "outputs"
    / "usd_asset_packages"
    / "lab_001_localized_20260707"
    / "lab_001_level1_pour_tabletop_with_liquid.usd"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _box_points(half_x: float, half_y: float, low_z: float, high_z: float):
    return [
        Gf.Vec3f(x, y, z)
        for x in (-half_x, half_x)
        for y in (-half_y, half_y)
        for z in (low_z, high_z)
    ]


def _define_fixture_mesh(stage: Usd.Stage, path: str, *, low_z: float, high_z: float):
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(_box_points(0.03, 0.03, low_z, high_z))
    mesh.CreateFaceVertexCountsAttr([4, 4, 4, 4, 4, 4])
    mesh.CreateFaceVertexIndicesAttr(
        [
            0,
            1,
            3,
            2,
            4,
            6,
            7,
            5,
            0,
            4,
            5,
            1,
            2,
            3,
            7,
            6,
            0,
            2,
            6,
            4,
            1,
            5,
            7,
            3,
        ]
    )
    mesh.CreateNormalsAttr([Gf.Vec3f(0.0, 0.0, 1.0)] * 24)
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
    UsdPhysics.RigidBodyAPI.Apply(mesh.GetPrim())
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    mesh.GetPrim().CreateAttribute(
        "physxCollision:contactOffset", Sdf.ValueTypeNames.Float
    ).Set(0.004)
    return mesh


def _fixture_stage(tmp_path: Path) -> tuple[Usd.Stage, Path]:
    path = tmp_path / "fixture_source.usda"
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.Xform.Define(stage, "/World")

    support = UsdGeom.Cube.Define(stage, "/World/Cube")
    support.CreateSizeAttr(0.06)
    support.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.75))
    support.AddScaleOp().Set(Gf.Vec3d(10.0, 10.0, 1.0))
    UsdPhysics.CollisionAPI.Apply(support.GetPrim())

    material = UsdShade.Material.Define(stage, "/World/Looks/Glass")
    for name, position, low_z, high_z in (
        ("beaker1", (0.255, -0.245, 0.87), -0.06, 0.07),
        ("beaker2", (0.295, 0.075, 0.87), -0.04, 0.05),
    ):
        parent = UsdGeom.Xform.Define(stage, f"/World/{name}")
        parent.AddTranslateOp().Set(Gf.Vec3d(*position))
        parent.AddRotateXYZOp().Set(Gf.Vec3f(0.0, 0.0, 0.0))
        parent.AddScaleOp().Set(Gf.Vec3f(1.0, 1.0, 1.0))
        mesh = _define_fixture_mesh(
            stage, f"/World/{name}/mesh", low_z=low_z, high_z=high_z
        )
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    particle_system = stage.DefinePrim("/World/ParticleSystem", "PhysxParticleSystem")
    particle_system.CreateAttribute(
        "particleSystemEnabled", Sdf.ValueTypeNames.Bool
    ).Set(True)

    particle_set = UsdGeom.Points.Define(stage, "/World/ParticleSet")
    particle_set.CreatePointsAttr(
        [
            Gf.Vec3f(0.295, 0.075, 0.845),
            Gf.Vec3f(0.300, 0.075, 0.850),
            Gf.Vec3f(0.295, 0.080, 0.855),
        ]
    )
    UsdPhysics.MassAPI.Apply(particle_set.GetPrim())
    particle_set.GetPrim().CreateAttribute(
        "physxParticle:selfCollision", Sdf.ValueTypeNames.Bool
    ).Set(True)
    particle_set.GetPrim().CreateAttribute(
        "physxParticle:fluid", Sdf.ValueTypeNames.Bool
    ).Set(True)
    particle_set.GetPrim().CreateRelationship(
        "physxParticle:particleSystem"
    ).SetTargets([Sdf.Path("/World/ParticleSystem")])

    UsdGeom.Xform.Define(stage, "/World/fluid")
    sampler = UsdGeom.Cylinder.Define(stage, "/World/fluid/Cylinder")
    sampler.CreateRadiusAttr(0.03)
    sampler.CreateHeightAttr(0.08)
    sampler.GetPrim().SetMetadata(
        "apiSchemas",
        Sdf.TokenListOp.Create(prependedItems=["PhysxParticleSamplingAPI"]),
    )
    sampler.GetPrim().CreateAttribute(
        "physxParticleSampling:volume", Sdf.ValueTypeNames.Bool
    ).Set(True)
    sampler.GetPrim().CreateRelationship(
        "physxParticleSampling:particles"
    ).SetTargets([Sdf.Path("/World/ParticleSet")])
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    stage.GetRootLayer().Save()
    return stage, path


def test_config_contract_recomputes_midpoints_and_forbids_exact_expert_claims():
    contract = aligned.load_config_midpoint_contract(CONFIG_PATH)

    assert contract["config_sha256"] == aligned.EXPECTED_CONFIG_SHA256
    assert contract["layout_semantics"] == "config_range_midpoint_support_aligned"
    assert contract["exact_expert_episode_layout"] is False
    assert contract["expert_episode_id"] is None
    assert contract["reset_z_from_config_m"] == pytest.approx(0.87)
    assert contract["beakers"]["beaker1"]["midpoint_xyz"] == pytest.approx(
        [0.255, -0.245, 0.87]
    )
    assert contract["beakers"]["beaker2"]["midpoint_xyz"] == pytest.approx(
        [0.295, 0.075, 0.87]
    )
    assert len(contract["config_layout_contract_sha256"]) == 64


def test_config_contract_rejects_any_changed_config_content(tmp_path):
    changed = tmp_path / "level1_pour.yaml"
    changed.write_text(CONFIG_PATH.read_text().replace("0.18", "0.19", 1))

    with pytest.raises(ValueError, match="config_sha256_mismatch"):
        aligned.load_config_midpoint_contract(changed)


@pytest.mark.parametrize(
    "replacement,error",
    [
        ("x: [0.33, 0.18]", "config_interval_reversed"),
        ("x: [.nan, 0.33]", "config_numeric_value_invalid"),
    ],
)
def test_config_contract_rejects_invalid_ranges_with_explicit_test_hash(
    tmp_path, replacement, error
):
    text = CONFIG_PATH.read_text().replace("x: [0.18, 0.33]", replacement, 1)
    changed = tmp_path / "level1_pour.yaml"
    changed.write_text(text)

    with pytest.raises(ValueError, match=error):
        aligned.load_config_midpoint_contract(
            changed, expected_sha256=_sha256(changed)
        )


def test_alignment_contract_uses_support_formula_and_beaker2_particle_ownership(
    tmp_path,
):
    stage, source = _fixture_stage(tmp_path)
    config = aligned.load_config_midpoint_contract(CONFIG_PATH)

    contract = aligned.build_support_alignment_contract(
        stage,
        config_contract=config,
        source_usd_sha256=_sha256(source),
        expected_source_usd_sha256=_sha256(source),
    )

    assert contract["support"]["prim_path"] == "/World/Cube"
    assert contract["support"]["bbox_max_z"] == pytest.approx(0.78)
    assert contract["support_clearance_m"] == 0.0
    assert contract["contact_tolerance_m"] == pytest.approx(1e-6)
    assert contract["beakers"]["beaker1"]["initial_bbox_bottom_z"] == pytest.approx(
        0.81
    )
    assert contract["beakers"]["beaker1"]["delta_z"] == pytest.approx(-0.03)
    assert contract["beakers"]["beaker2"]["initial_bbox_bottom_z"] == pytest.approx(
        0.83
    )
    assert contract["beakers"]["beaker2"]["delta_z"] == pytest.approx(-0.05)
    assert contract["particle_set"]["prim_path"] == "/World/ParticleSet"
    assert contract["particle_set"]["owner_beaker_path"] == "/World/beaker2"
    assert contract["particle_set"]["delta_source"] == "/World/beaker2"
    assert contract["particle_set"]["delta_z"] == pytest.approx(-0.05)
    assert contract["legacy_particle_graph"]["sampler_path"] == (
        "/World/fluid/Cylinder"
    )
    assert contract["legacy_particle_graph"]["particle_set_path"] == (
        "/World/ParticleSet"
    )
    assert contract["legacy_particle_graph"]["particle_system_path"] == (
        "/World/ParticleSystem"
    )
    assert contract["legacy_particle_graph"]["source_sampler_targets"] == [
        "/World/ParticleSet"
    ]
    assert contract["legacy_particle_graph"]["source_particle_system_targets"] == [
        "/World/ParticleSystem"
    ]
    assert contract["legacy_particle_graph"]["overlay_must_be_stronger_than_source"] is True
    assert contract["legacy_particle_graph"]["retained_as_inert_calibration_data"] is True
    assert len(contract["support_aligned_source_contract_sha256"]) == 64


def test_alignment_contract_requires_both_standard_mesh_paths(tmp_path):
    stage, source = _fixture_stage(tmp_path)
    stage.RemovePrim("/World/beaker1/mesh")

    with pytest.raises(ValueError, match="required_prim_missing:/World/beaker1/mesh"):
        aligned.build_support_alignment_contract(
            stage,
            config_contract=aligned.load_config_midpoint_contract(CONFIG_PATH),
            source_usd_sha256=_sha256(source),
            expected_source_usd_sha256=_sha256(source),
        )


def test_alignment_contract_rejects_source_hash_mismatch(tmp_path):
    stage, source = _fixture_stage(tmp_path)

    with pytest.raises(ValueError, match="source_usd_sha256_mismatch"):
        aligned.build_support_alignment_contract(
            stage,
            config_contract=aligned.load_config_midpoint_contract(CONFIG_PATH),
            source_usd_sha256=_sha256(source),
            expected_source_usd_sha256="0" * 64,
        )


def test_overlay_moves_real_beakers_and_owned_particle_set_without_mutating_authority(
    tmp_path,
):
    stage, source = _fixture_stage(tmp_path)
    config = aligned.load_config_midpoint_contract(CONFIG_PATH)
    contract = aligned.build_support_alignment_contract(
        stage,
        config_contract=config,
        source_usd_sha256=_sha256(source),
        expected_source_usd_sha256=_sha256(source),
    )
    root_before = stage.GetRootLayer().ExportToString()
    authority_before = aligned.snapshot_scene_authority(stage)
    particle_relation_before = aligned.particle_set_owner_canonical_sha256(stage)
    overlay = aligned.begin_support_alignment_layer(stage, tmp_path / "overlay.usda")

    authored = aligned.author_support_aligned_scene(
        stage, contract=contract, overlay_layer=overlay
    )

    assert stage.GetRootLayer().ExportToString() == root_before
    assert authored["support_alignment_verified"] is True
    assert authored["particle_set_owner_beaker_path"] == "/World/beaker2"
    assert authored["particle_set_delta_z"] == pytest.approx(-0.05)
    assert aligned.particle_set_owner_canonical_sha256(stage) == particle_relation_before
    authority_after = aligned.snapshot_scene_authority(stage)
    assert authority_after["mesh_geometry"] == authority_before["mesh_geometry"]
    assert authority_after["mesh_material_bindings"] == authority_before[
        "mesh_material_bindings"
    ]
    for path in ("/World/beaker1/mesh", "/World/beaker2/mesh", "/World/Cube"):
        assert authority_after["physics_contract"][path] == authority_before[
            "physics_contract"
        ][path]
    assert authority_after["particle_points_sha256"] == authority_before[
        "particle_points_sha256"
    ]
    assert authority_after["parent_transforms"] != authority_before[
        "parent_transforms"
    ]
    assert aligned.world_bbox(stage, "/World/beaker1")["min"][2] == pytest.approx(
        0.78, abs=1e-6
    )
    assert aligned.world_bbox(stage, "/World/beaker2")["min"][2] == pytest.approx(
        0.78, abs=1e-6
    )
    assert overlay.dirty is True
    assert "supportAligned" in overlay.ExportToString()


def test_overlay_isolates_legacy_particle_graph_and_preserves_calibration_data(
    tmp_path,
):
    stage, source = _fixture_stage(tmp_path)
    contract = aligned.build_support_alignment_contract(
        stage,
        config_contract=aligned.load_config_midpoint_contract(CONFIG_PATH),
        source_usd_sha256=_sha256(source),
        expected_source_usd_sha256=_sha256(source),
    )
    source_text_before = stage.GetRootLayer().ExportToString()
    bounds_before = aligned.particle_set_bounds(stage)
    canonical_before = aligned.particle_set_owner_canonical_sha256(stage)
    points_before = aligned.snapshot_scene_authority(stage)["particle_points_sha256"]
    overlay = aligned.begin_support_alignment_layer(stage, tmp_path / "overlay.usda")

    authored = aligned.author_support_aligned_scene(
        stage, contract=contract, overlay_layer=overlay
    )

    assert stage.GetRootLayer().ExportToString() == source_text_before
    isolation = authored["legacy_particle_graph_isolation"]
    assert isolation["verified"] is True
    assert isolation["sampler_targets"] == []
    assert isolation["particle_system_targets"] == []
    assert isolation["sampler_volume"] is False
    assert isolation["particle_set_self_collision"] is False
    assert isolation["particle_set_fluid"] is False
    assert isolation["particle_system_enabled"] is False
    assert isolation["sampling_api_present"] is False
    assert isolation["all_legacy_prims_active"] is True
    assert isolation["all_legacy_prims_hidden"] is True
    assert aligned.snapshot_scene_authority(stage)["particle_points_sha256"] == points_before
    assert aligned.particle_set_owner_canonical_sha256(stage) == canonical_before
    bounds_after = aligned.particle_set_bounds(stage)
    assert bounds_after["local"] == bounds_before["local"]
    assert bounds_after["world"]["min"] == pytest.approx(
        [
            bounds_before["world"]["min"][0],
            bounds_before["world"]["min"][1],
            bounds_before["world"]["min"][2]
            + contract["beakers"]["beaker2"]["delta_z"],
        ]
    )
    assert bounds_after["world"]["max"] == pytest.approx(
        [
            bounds_before["world"]["max"][0],
            bounds_before["world"]["max"][1],
            bounds_before["world"]["max"][2]
            + contract["beakers"]["beaker2"]["delta_z"],
        ]
    )
    overlay_text = overlay.ExportToString()
    assert 'delete apiSchemas = ["PhysxParticleSamplingAPI"]' in overlay_text
    assert "physxParticleSampling:particles = None" in overlay_text
    assert "physxParticle:particleSystem = None" in overlay_text


def test_verifier_rejects_partial_legacy_graph_isolation(tmp_path):
    stage, source = _fixture_stage(tmp_path)
    contract = aligned.build_support_alignment_contract(
        stage,
        config_contract=aligned.load_config_midpoint_contract(CONFIG_PATH),
        source_usd_sha256=_sha256(source),
        expected_source_usd_sha256=_sha256(source),
    )
    overlay = aligned.begin_support_alignment_layer(stage, tmp_path / "overlay.usda")
    aligned.author_support_aligned_scene(stage, contract=contract, overlay_layer=overlay)
    stage.GetPrimAtPath("/World/ParticleSet").GetRelationship(
        "physxParticle:particleSystem"
    ).SetTargets([Sdf.Path("/World/ParticleSystem")])

    with pytest.raises(RuntimeError, match="legacy_particle_graph_isolation_failed"):
        aligned.verify_support_aligned_scene(stage, contract=contract)


def test_frozen_runner_observes_preisolated_graph_without_sync_requirement(tmp_path):
    stage, source = _fixture_stage(tmp_path)
    contract = aligned.build_support_alignment_contract(
        stage,
        config_contract=aligned.load_config_midpoint_contract(CONFIG_PATH),
        source_usd_sha256=_sha256(source),
        expected_source_usd_sha256=_sha256(source),
    )
    overlay_path = tmp_path / "overlay.usda"
    overlay = aligned.begin_support_alignment_layer(stage, overlay_path)
    aligned.author_support_aligned_scene(stage, contract=contract, overlay_layer=overlay)
    assert overlay.Save()
    entry_path = tmp_path / "entry.usda"
    entry_layer = Sdf.Layer.CreateNew(str(entry_path))
    entry_layer.defaultPrim = "World"
    entry_layer.subLayerPaths = [overlay_path.name, source.name]
    assert entry_layer.Save()
    composed = Usd.Stage.Open(str(entry_path), Usd.Stage.LoadAll)

    summary = frozen_runner._deactivate_original_fluid_prims(composed)

    ownership = summary["ownership_isolation"]
    assert ownership["verified"] is True
    assert ownership["sampler_targets_after"] == []
    assert ownership["particle_set_targets_after"] == []
    assert ownership["synchronization_required"] is False


def test_overlay_rejects_wrong_edit_target(tmp_path):
    stage, source = _fixture_stage(tmp_path)
    contract = aligned.build_support_alignment_contract(
        stage,
        config_contract=aligned.load_config_midpoint_contract(CONFIG_PATH),
        source_usd_sha256=_sha256(source),
        expected_source_usd_sha256=_sha256(source),
    )
    overlay = aligned.begin_support_alignment_layer(stage, tmp_path / "overlay.usda")
    stage.SetEditTarget(stage.GetRootLayer())

    with pytest.raises(RuntimeError, match="support_alignment_edit_target_mismatch"):
        aligned.author_support_aligned_scene(
            stage, contract=contract, overlay_layer=overlay
        )


def test_verifier_rejects_particle_set_using_beaker1_delta(tmp_path):
    stage, source = _fixture_stage(tmp_path)
    contract = aligned.build_support_alignment_contract(
        stage,
        config_contract=aligned.load_config_midpoint_contract(CONFIG_PATH),
        source_usd_sha256=_sha256(source),
        expected_source_usd_sha256=_sha256(source),
    )
    overlay = aligned.begin_support_alignment_layer(stage, tmp_path / "overlay.usda")
    aligned.author_support_aligned_scene(stage, contract=contract, overlay_layer=overlay)
    particle_set = UsdGeom.Xformable(stage.GetPrimAtPath("/World/ParticleSet"))
    particle_set.GetOrderedXformOps()[0].Set(
        Gf.Vec3d(0.0, 0.0, contract["beakers"]["beaker1"]["delta_z"])
    )

    with pytest.raises(RuntimeError, match="particle_set_owner_relation_changed"):
        aligned.verify_support_aligned_scene(stage, contract=contract)


@pytest.mark.skipif(
    not SOURCE_PATH.is_file(), reason="requires local localized USD delivery"
)
def test_actual_source_contract_is_config_midpoint_and_support_aligned_formula():
    assert SOURCE_PATH.is_file()
    stage = Usd.Stage.Open(str(SOURCE_PATH), Usd.Stage.LoadAll)
    contract = aligned.build_support_alignment_contract(
        stage,
        config_contract=aligned.load_config_midpoint_contract(CONFIG_PATH),
        source_usd_sha256=_sha256(SOURCE_PATH),
    )

    assert contract["source_usd_sha256"] == aligned.EXPECTED_SOURCE_SHA256
    assert contract["support"]["prim_path"] == "/World/Cube"
    assert contract["support"]["bbox_max_z"] == pytest.approx(
        0.7799941121566101
    )
    assert contract["beakers"]["beaker1"]["delta_z"] < 0.0
    assert contract["beakers"]["beaker2"]["delta_z"] < 0.0
    assert contract["particle_set"]["delta_z"] == pytest.approx(
        contract["beakers"]["beaker2"]["delta_z"]
    )


@pytest.mark.skipif(
    not SOURCE_PATH.is_file(), reason="requires local localized USD delivery"
)
def test_build_support_aligned_entry_reopens_with_hash_bound_contact(tmp_path):
    out_dir = tmp_path / "support_aligned"

    manifest = aligned.build_support_aligned_entry(
        source_path=SOURCE_PATH,
        config_path=CONFIG_PATH,
        out_dir=out_dir,
    )

    entry = Path(manifest["entry_usd_path"])
    overlay = Path(manifest["overlay_usd_path"])
    assert entry.is_file()
    assert overlay.is_file()
    assert Path(manifest["manifest_path"]).is_file()
    assert manifest["layout_semantics"] == "config_range_midpoint_support_aligned"
    assert manifest["exact_expert_episode_layout"] is False
    assert manifest["support_alignment_verified"] is True
    assert manifest["entry_usd_sha256"] == _sha256(entry)
    assert manifest["overlay_usd_sha256"] == _sha256(overlay)
    assert manifest["localized_source_usd_sha256"] == _sha256(SOURCE_PATH)
    assert manifest["support_overlay_usd_sha256"] == _sha256(overlay)
    assert manifest["support_entry_root_usd_sha256"] == _sha256(entry)
    assert Path(manifest["manifest_path"]).stat().st_size < 2_000_000
    simulation_points = manifest["support_alignment_contract"][
        "source_authority_snapshot"
    ]["physics_contract"]["/World/ParticleSet"]["attributes"][
        "physxParticle:simulationPoints"
    ]
    assert simulation_points["value_count"] == 50000
    assert len(simulation_points["value_sha256"]) == 64
    assert "value" not in simulation_points
    entry_layer = Sdf.Layer.FindOrOpen(str(entry))
    assert entry_layer is not None
    assert entry_layer.subLayerPaths[0] == overlay.name
    assert all(not Path(item).is_absolute() for item in entry_layer.subLayerPaths)
    assert f"@{SOURCE_PATH}@" not in entry.read_text()
    assert f"@{SOURCE_PATH}@" not in overlay.read_text()

    reopened = Usd.Stage.Open(str(entry), Usd.Stage.LoadAll)
    verified = aligned.verify_support_aligned_scene(
        reopened, contract=manifest["support_alignment_contract"]
    )
    assert verified["support_alignment_verified"] is True
    assert verified["beakers"]["beaker1"]["contact_gap_m"] == pytest.approx(
        0.0, abs=1e-6
    )
    assert verified["beakers"]["beaker2"]["contact_gap_m"] == pytest.approx(
        0.0, abs=1e-6
    )
    assert verified["legacy_particle_graph_isolation"]["verified"] is True

    entry_layer.subLayerPaths = list(reversed(entry_layer.subLayerPaths))
    with pytest.raises(RuntimeError, match="support_overlay_layer_order_invalid"):
        aligned.verify_support_entry_layer_order(
            entry_layer,
            overlay_basename=overlay.name,
        )


def test_builder_refuses_to_overwrite_existing_output_directory(tmp_path):
    out_dir = tmp_path / "support_aligned"
    out_dir.mkdir()

    with pytest.raises(ValueError, match="output_directory_already_exists"):
        aligned.build_support_aligned_entry(
            source_path=SOURCE_PATH,
            config_path=CONFIG_PATH,
            out_dir=out_dir,
        )


def test_canonical_json_hash_rejects_non_finite_and_is_order_stable():
    assert aligned.canonical_json_sha256_v1({"b": 2, "a": 1.5}) == (
        aligned.canonical_json_sha256_v1({"a": 1.5, "b": 2})
    )
    with pytest.raises(ValueError, match="canonical_json_non_finite"):
        aligned.canonical_json_sha256_v1({"bad": float("nan")})
