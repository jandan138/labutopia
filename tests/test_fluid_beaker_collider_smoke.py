import pytest

from tools.labutopia_fluid.run_beaker_collider_smoke import (
    BEAKER_COLLIDER_VARIANT_IDS,
    CLASSIFICATION_CONTRACT_VERSION,
    ColliderConfig,
    DIAGNOSTIC_PROJECTION_VERSION,
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
