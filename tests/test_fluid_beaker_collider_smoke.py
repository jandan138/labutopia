import pytest
import sys
from pathlib import Path
from types import SimpleNamespace

from tools.labutopia_fluid.run_beaker_collider_smoke import (
    BEAKER_COLLIDER_VARIANT_IDS,
    CLASSIFICATION_CONTRACT_VERSION,
    ColliderConfig,
    DIAGNOSTIC_PROJECTION_VERSION,
    PROMOTION_INITIAL_RADIAL_VELOCITY,
    PROMOTION_PARTICLE_MAX_VELOCITY,
    VariantSpec,
    _add_colliders,
    _add_fluid_safe_wrapper,
    _build_manifest,
    _write_diagnostic_png,
    build_source_particle_initial_velocities,
    build_source_particle_positions,
    classify_collider_hold,
    compute_region_counts,
    rank_collider_variants,
)


def test_s2_matrix_declares_all_required_collider_variants():
    assert BEAKER_COLLIDER_VARIANT_IDS == ("C0", "C1", "C2", "C3", "C4", "C5")


def test_promotion_init_defaults_are_pinned_on_collider_config():
    config = ColliderConfig()

    assert PROMOTION_INITIAL_RADIAL_VELOCITY == 0.08
    assert PROMOTION_PARTICLE_MAX_VELOCITY == 5.0
    assert config.initial_radial_velocity == PROMOTION_INITIAL_RADIAL_VELOCITY
    assert config.particle_max_velocity == PROMOTION_PARTICLE_MAX_VELOCITY


def _author_beaker2_fixture(stage, *, translate=(0.0, 0.0, 0.0), with_mesh=True):
    from pxr import Gf, UsdGeom, UsdPhysics

    UsdGeom.Xform.Define(stage, "/World")
    parent = UsdGeom.Xform.Define(stage, "/World/beaker2")
    parent.AddTranslateOp().Set(Gf.Vec3d(*translate))
    mesh_prim = None
    if with_mesh:
        mesh = UsdGeom.Cube.Define(stage, "/World/beaker2/mesh")
        mesh.CreateSizeAttr(0.1)
        mesh_prim = mesh.GetPrim()
        collision_api = UsdPhysics.CollisionAPI.Apply(mesh_prim)
        collision_api.CreateCollisionEnabledAttr().Set(True)
    return parent.GetPrim(), mesh_prim


def test_add_fluid_safe_wrapper_authors_invisible_local_box_panels():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    _author_beaker2_fixture(stage, translate=(0.0, 0.0, 0.0), with_mesh=True)
    config = ColliderConfig(wall_thickness=0.018, bottom_overlap=0.003)

    result = _add_fluid_safe_wrapper(
        stage,
        config,
        parent_path="/World/beaker2",
        visual_mesh_path="/World/beaker2/mesh",
        panel_count=48,
    )

    wrapper = stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapper")
    bottom = stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapper/Bottom")
    wall0 = stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapper/Wall_00")
    mesh_prim = stage.GetPrimAtPath("/World/beaker2/mesh")

    assert wrapper.IsValid()
    assert UsdGeom.Imageable(wrapper).ComputeVisibility() == UsdGeom.Tokens.invisible
    assert wrapper.GetAttribute("labutopia:fluidSafeWrapper").Get() is True
    assert wrapper.GetAttribute("labutopia:wrapperFrame").Get() == "local_to_beaker2"
    assert mesh_prim.GetAttribute("physics:collisionEnabled").Get() is False
    assert bottom.IsValid()
    assert wall0.IsValid()
    assert stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapper/Wall_47").IsValid()
    assert not stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapper/Wall_48").IsValid()
    assert result["wrapper_path"] == "/World/beaker2/FluidSafeWrapper"
    assert result["wrapper_frame"] == "local_to_beaker2"
    assert result["motion_contract"] == "static_collision_inherits_beaker2_xform"
    assert result["wrapper_parent_path"] == "/World/beaker2"
    assert result["native_mesh_collision_enabled"] is False
    assert "/World/beaker2/FluidSafeWrapper/Bottom" in result["collider_paths"]
    assert any(path.endswith("/Wall_00") for path in result["collider_paths"])
    assert bottom.GetAttribute("labutopia:fluidSafeWrapper").Get() is True
    assert wall0.GetAttribute("labutopia:fluidSafeWrapper").Get() is True


def test_add_fluid_safe_wrapper_uses_parent_local_frame_not_world_pose():
    from pxr import Gf, Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    parent_translate = (10.0, -3.0, 1.5)
    _author_beaker2_fixture(stage, translate=parent_translate, with_mesh=False)
    config = ColliderConfig(source_center=(0.0, 0.0, 0.0), wall_thickness=0.018, bottom_overlap=0.003)

    result = _add_fluid_safe_wrapper(
        stage,
        config,
        parent_path="/World/beaker2",
        panel_count=8,
    )

    bottom = UsdGeom.Xformable(stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapper/Bottom"))
    wall0 = UsdGeom.Xformable(stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapper/Wall_00"))
    bottom_translate = bottom.GetOrderedXformOps()[0].Get()
    wall_translate = wall0.GetOrderedXformOps()[0].Get()

    # Local-frame authoring: panel translates stay near the cup local origin, not
    # the parent's world translation (which would double-apply under beaker2).
    assert abs(float(bottom_translate[0])) < 1.0
    assert abs(float(bottom_translate[1])) < 1.0
    assert abs(float(wall_translate[0])) < 1.0
    assert abs(float(wall_translate[1])) < 1.0
    assert abs(float(bottom_translate[0]) - parent_translate[0]) > 5.0
    assert result["wrapper_frame"] == "local_to_beaker2"
    assert result["motion_contract"] == "static_collision_inherits_beaker2_xform"

    purpose_attr = stage.GetPrimAtPath("/World/beaker2/FluidSafeWrapper").GetAttribute("purpose")
    if purpose_attr and purpose_attr.HasAuthoredValueOpinion():
        assert purpose_attr.Get() == UsdGeom.Tokens.proxy


def test_c3a_followup_variants_route_to_sdf_open_beaker(monkeypatch):
    import tools.labutopia_fluid.run_beaker_collider_smoke as smoke

    calls = []

    class FakeXform:
        @staticmethod
        def Define(stage, path):
            calls.append(("xform", stage, path))

    def fake_add_sdf_open_beaker(stage, config, spec):
        calls.append(("sdf", stage, config, spec.variant_id))
        return ["/World/SourceContainer/SDFOpenBeaker"]

    monkeypatch.setitem(sys.modules, "pxr", SimpleNamespace(UsdGeom=SimpleNamespace(Xform=FakeXform)))
    monkeypatch.setattr(smoke, "_add_sdf_open_beaker", fake_add_sdf_open_beaker)

    paths = _add_colliders(
        stage=object(),
        config=ColliderConfig(),
        spec=VariantSpec(
            variant_id="C3A_001",
            name="sdf_cooking_sweep",
            description="SDF follow-up",
            setup="s2f3_sdf_open_concave_mesh",
            collider_count=1,
            collision_approximation="sdf",
            source_kind="procedural_mesh",
            sdf_resolution=64,
            sdf_subgrid_resolution=4,
            sdf_margin=0.002,
            sdf_narrow_band_thickness=0.01,
        ),
        native_usd=None,
    )

    assert paths == ["/World/SourceContainer/SDFOpenBeaker"]
    assert calls[0][0] == "xform"
    assert calls[1][0] == "sdf"
    assert calls[1][3] == "C3A_001"


def _c4a_variant_spec(
    *,
    variant_id: str,
    native_collision_route: str,
    native_mesh_collision_enabled: bool,
    proxy_collision_enabled: bool,
) -> VariantSpec:
    return VariantSpec(
        variant_id=variant_id,
        name="native_mesh_isolation",
        description="S2F4 native mesh isolation test spec.",
        setup="s2f4_native_beaker_mesh_isolation",
        collider_count=25 if proxy_collision_enabled else 1,
        collision_approximation=native_collision_route,
        source_kind="native_render_mesh_with_proxy_collision"
        if proxy_collision_enabled
        else "native_mesh_reference",
        native_source_path="/World/beaker2",
        native_mesh_source_path="/World/beaker2/mesh",
        native_reference_scope="parent_scope",
        native_material_binding_strategy="local_blue_glass_override",
        native_material_binding_scope_closed=True,
        native_pose_alignment="bbox_recenter_to_source_region",
        native_collision_route=native_collision_route,
        native_mesh_collision_enabled=native_mesh_collision_enabled,
        proxy_collision_enabled=proxy_collision_enabled,
        sdf_resolution=128 if native_collision_route == "sdf" else None,
        sdf_subgrid_resolution=8 if native_collision_route == "sdf" else None,
        sdf_margin=0.002 if native_collision_route == "sdf" else None,
        sdf_narrow_band_thickness=0.01 if native_collision_route == "sdf" else None,
        panel_count=24 if proxy_collision_enabled else None,
    )


def test_c4a_native_parent_reference_scope_closed_authoring():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    native_usd = Path("assets/chemistry_lab/lab_001/lab_001.usd").resolve()

    for variant_id, route in (
        ("C4A_convexDecomposition_reference_scope_closed", "convexDecomposition"),
        ("C4A_sdf_reference_scope_closed", "sdf"),
    ):
        paths = _add_colliders(
            stage=stage,
            config=ColliderConfig(),
            spec=_c4a_variant_spec(
                variant_id=variant_id,
                native_collision_route=route,
                native_mesh_collision_enabled=True,
                proxy_collision_enabled=False,
            ),
            native_usd=native_usd,
        )
        mesh_prim = stage.GetPrimAtPath("/World/SourceContainer/NativeBeaker2/mesh")

        assert "/World/SourceContainer/NativeBeaker2/mesh" in paths
        assert mesh_prim.GetAttribute("labutopia:nativeMaterialBindingScopeClosed").Get() is True
        assert mesh_prim.GetAttribute("labutopia:nativePoseAlignment").Get() == "bbox_recenter_to_source_region"
        assert mesh_prim.GetAttribute("labutopia:nativeCollisionRoute").Get() == route
        assert mesh_prim.GetAttribute("labutopia:nativeReferenceScope").Get() == "parent_scope"


def test_c4a_native_render_mesh_plus_proxy_disables_native_collision():
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    native_usd = Path("assets/chemistry_lab/lab_001/lab_001.usd").resolve()

    paths = _add_colliders(
        stage=stage,
        config=ColliderConfig(),
        spec=_c4a_variant_spec(
            variant_id="C4A_native_render_mesh_plus_proxy_collision",
            native_collision_route="render_mesh_plus_proxy_collision",
            native_mesh_collision_enabled=False,
            proxy_collision_enabled=True,
        ),
        native_usd=native_usd,
    )
    mesh_prim = stage.GetPrimAtPath("/World/SourceContainer/NativeBeaker2/mesh")

    assert "/World/SourceContainer/NativeBeaker2/mesh" in paths
    assert mesh_prim.GetAttribute("physics:collisionEnabled").Get() is False
    assert mesh_prim.GetAttribute("labutopia:nativeCollisionRoute").Get() == "render_mesh_plus_proxy_collision"
    assert mesh_prim.GetAttribute("labutopia:nativeMaterialBindingScopeClosed").Get() is True
    assert any(path.startswith("/World/SourceContainer/ProxyCollision") for path in paths)


def test_region_counts_split_source_target_spill_and_below_table():
    config = ColliderConfig()
    positions = [
        (0.0, 0.0, 0.08),
        (0.015, 0.0, 0.09),
        (0.24, 0.0, 0.08),
        (0.18, 0.18, 0.08),
        (0.0, 0.0, -0.02),
    ]

    counts = compute_region_counts(positions, config)

    assert counts["total_count"] == 5
    assert counts["source_count"] == 2
    assert counts["target_count"] == 1
    assert counts["spill_count"] == 1
    assert counts["below_table_count"] == 1


def test_source_particle_positions_cover_near_wall_while_starting_inside_source_region():
    config = ColliderConfig()

    positions = build_source_particle_positions(config)
    counts = compute_region_counts(positions, config)
    max_radius = max((x**2 + y**2) ** 0.5 for x, y, _ in positions)

    assert len(positions) == config.particle_count
    assert counts["source_count"] == config.particle_count
    assert counts["spill_count"] == 0
    assert counts["below_table_count"] == 0
    assert max_radius >= config.source_radius * 0.75


def test_source_particle_positions_are_deterministic_for_same_seed():
    config = ColliderConfig(particle_count=64, particle_seed=7)

    assert build_source_particle_positions(config) == build_source_particle_positions(config)


def test_source_particle_positions_vary_across_seed_without_changing_count():
    seed_7 = build_source_particle_positions(ColliderConfig(particle_count=64, particle_seed=7))
    seed_8 = build_source_particle_positions(ColliderConfig(particle_count=64, particle_seed=8))

    assert len(seed_7) == 64
    assert len(seed_8) == 64
    assert seed_7 != seed_8


def test_source_particle_velocities_apply_radial_wall_stress_without_vertical_launch():
    config = ColliderConfig(initial_radial_velocity=0.08)
    positions = build_source_particle_positions(config)
    velocities = build_source_particle_initial_velocities(positions, config)
    edge_index = max(range(len(positions)), key=lambda i: positions[i][0] ** 2 + positions[i][1] ** 2)
    x, y, _ = positions[edge_index]
    vx, vy, vz = velocities[edge_index]

    assert len(velocities) == len(positions)
    assert x * vx + y * vy > 0
    assert vz == 0.0
    assert max((vx**2 + vy**2 + vz**2) ** 0.5 for vx, vy, vz in velocities) == pytest.approx(
        config.initial_radial_velocity
    )


def test_side_diagnostic_projection_shows_below_table_leak_points(tmp_path):
    config = ColliderConfig()
    image_path = tmp_path / "leak_side.png"

    _write_diagnostic_png(
        image_path,
        [(0.0, 0.0, -0.05), (0.01, 0.0, -0.052)],
        config,
        title="leak test",
        view="side",
    )

    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    red_pixels = sum(1 for r, g, b in image.getdata() if r > 150 and g < 100 and b < 100)

    assert red_pixels > 0


def test_classify_collider_hold_requires_retention_count_nan_gpu_and_tail_leak():
    config = ColliderConfig(steps=240, physics_dt=1.0 / 60.0)
    good = classify_collider_hold(
        variant_id="C1",
        config=config,
        initial_count=100,
        final_count=99,
        source_count=99,
        target_count=0,
        spill_count=0,
        below_table_count=0,
        nan_count=0,
        tail_leak_rate_fraction_per_second=0.01,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        fatal_error=None,
    )

    assert good["classification"] == "PASS_SOURCE_HOLD"
    assert good["pass_criteria"]["source_retention_fraction_ge_0_95"] is True
    assert good["pass_criteria"]["outside_source_count_eq_zero"] is True
    assert good["pass_criteria"]["spill_count_eq_zero"] is True
    assert good["pass_criteria"]["tail_leak_rate_lt_0_02"] is True

    leak = classify_collider_hold(
        variant_id="C1",
        config=config,
        initial_count=100,
        final_count=100,
        source_count=80,
        target_count=0,
        spill_count=20,
        below_table_count=0,
        nan_count=0,
        tail_leak_rate_fraction_per_second=0.01,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        fatal_error=None,
    )

    assert leak["classification"] == "FAIL_CONTAINER_LEAK"
    assert leak["outside_source_count"] == 20
    assert leak["pass_criteria"]["spill_count_eq_zero"] is False

    above_table_spill = classify_collider_hold(
        variant_id="C1",
        config=config,
        initial_count=100,
        final_count=100,
        source_count=97,
        target_count=0,
        spill_count=3,
        below_table_count=0,
        nan_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        fatal_error=None,
    )

    assert above_table_spill["classification"] == "FAIL_CONTAINER_LEAK"
    assert above_table_spill["pass_criteria"]["outside_source_count_eq_zero"] is False

    unsupported = classify_collider_hold(
        variant_id="C5",
        config=config,
        initial_count=100,
        final_count=100,
        source_count=100,
        target_count=0,
        spill_count=0,
        below_table_count=0,
        nan_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=True,
        fatal_error=None,
    )

    assert unsupported["classification"] == "FAIL_GPU_COLLIDER_UNSUPPORTED"

    stale_readback = classify_collider_hold(
        variant_id="C1",
        config=config,
        initial_count=100,
        final_count=100,
        source_count=100,
        target_count=0,
        spill_count=0,
        below_table_count=0,
        nan_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        fatal_error=None,
        particle_motion_observed=False,
    )

    assert stale_readback["classification"] == "FAIL_READBACK_UNAVAILABLE"


def test_side_diagnostic_projection_returns_versioned_source_label(tmp_path):
    config = ColliderConfig()
    image_path = tmp_path / "side.png"

    source = _write_diagnostic_png(
        image_path,
        [(0.0, 0.0, -0.05)],
        config,
        title="source label",
        view="side",
    )

    assert source == "diagnostic_side_projection_v2_dynamic_z"
    assert DIAGNOSTIC_PROJECTION_VERSION == "v2_dynamic_z_shows_below_table_leaks"


def test_rank_variants_prefers_passes_with_highest_retention_and_never_promotes_c5():
    ranked = rank_collider_variants(
        [
            {
                "variant_id": "C0",
                "classification": "PASS_SOURCE_HOLD",
                "source_retention_fraction": 0.96,
                "tail_leak_rate_fraction_per_second": 0.005,
            },
            {
                "variant_id": "C1",
                "classification": "PASS_SOURCE_HOLD",
                "source_retention_fraction": 0.99,
                "tail_leak_rate_fraction_per_second": 0.01,
            },
            {
                "variant_id": "C5",
                "classification": "PASS_SOURCE_HOLD",
                "source_retention_fraction": 1.0,
                "tail_leak_rate_fraction_per_second": 0.0,
            },
            {
                "variant_id": "C3",
                "classification": "FAIL_CONTAINER_LEAK",
                "source_retention_fraction": 0.5,
                "tail_leak_rate_fraction_per_second": 0.2,
            },
        ]
    )

    assert ranked["best_for_s3"] == ["C1", "C0"]
    assert ranked["s2_status"] == "GO_NEXT"


def test_rank_variants_stops_when_no_non_negative_control_passes():
    ranked = rank_collider_variants(
        [
            {
                "variant_id": "C0",
                "classification": "FAIL_CONTAINER_LEAK",
                "source_retention_fraction": 0.7,
                "tail_leak_rate_fraction_per_second": 0.2,
            },
            {
                "variant_id": "C5",
                "classification": "PASS_SOURCE_HOLD",
                "source_retention_fraction": 1.0,
                "tail_leak_rate_fraction_per_second": 0.0,
            },
        ]
    )

    assert ranked["best_for_s3"] == []
    assert ranked["s2_status"] == "STOP_WITH_EVIDENCE"
    assert ranked["reason"] == "no_non_negative_control_variant_passed"


def test_manifest_distinguishes_full_matrix_from_selected_subset(tmp_path):
    config = ColliderConfig()
    subset_matrix = {
        "selected_variant_ids": ["C2"],
        "full_matrix_executed": False,
        "variant_summaries": [],
        "variant_results": [],
        "ranking": {
            "best_for_s3": [],
            "native_beaker_status": "NOT_RUN",
            "negative_control_status": "NOT_RUN",
            "s2_status": "STOP_WITH_EVIDENCE",
            "reason": "no_non_negative_control_variant_passed",
        },
    }

    manifest = _build_manifest(
        config=config,
        artifact_dir=tmp_path / "artifacts",
        scene_dir=tmp_path / "scenes",
        native_usd=tmp_path / "native.usd",
        matrix=subset_matrix,
        command="runner --variants C2",
        fatal_error=None,
    )

    assert manifest["selected_variant_ids"] == ["C2"]
    assert manifest["classification_contract_version"] == CLASSIFICATION_CONTRACT_VERSION
    assert manifest["full_matrix_executed"] is False
    assert "selected beaker collider subset" in manifest["allowed_claims"][0]
    assert manifest["pass_criteria"]["required_outside_source_count"] == 0
    assert manifest["runtime_warning_evidence_mode"].startswith("artifact-level")
