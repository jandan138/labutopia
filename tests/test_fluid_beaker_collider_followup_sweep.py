import json
from pathlib import Path

import pytest

from tools.labutopia_fluid.run_beaker_collider_smoke import ColliderConfig, VariantSpec


def test_followup_matrix_names_do_not_collide_with_s2_baseline():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import followup_phase_specs

    phases = followup_phase_specs()
    assert list(phases) == [
        "S2F0_BASELINE_FREEZE",
        "S2F1_C2_PROXY_SWEEP",
        "S2F2_VELOCITY_CONTACT_OFFSET",
        "S2F3_C3_SDF_SWEEP",
        "S2F4_C4_NATIVE_MESH_ISOLATION",
        "S2F5_PROMOTION_REVIEW",
        "D4_WRAPPER_SWEEP",
    ]
    assert phases["S2F0_BASELINE_FREEZE"]["candidate_prefix"] == "S2"
    assert phases["S2F1_C2_PROXY_SWEEP"]["candidate_prefix"] == "C2A"
    assert phases["S2F3_C3_SDF_SWEEP"]["candidate_prefix"] == "C3A"
    assert phases["S2F4_C4_NATIVE_MESH_ISOLATION"]["candidate_prefix"] == "C4A"
    assert phases["D4_WRAPPER_SWEEP"]["candidate_prefix"] == "D4A"


def test_build_c2_proxy_sweep_is_bounded_and_covers_planned_ranges():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_c2_proxy_sweep

    candidates = build_c2_proxy_sweep()

    assert len(candidates) == 12
    assert [candidate.candidate_id for candidate in candidates] == [f"C2A_{index:03d}" for index in range(1, 13)]
    assert {candidate.panel_count for candidate in candidates} == {24, 32, 48}
    assert {candidate.wall_thickness for candidate in candidates} == {0.010, 0.014, 0.018}
    assert {candidate.bottom_overlap for candidate in candidates} == {0.000, 0.003, 0.006}
    assert {candidate.particle_contact_offset for candidate in candidates} == {0.0045, 0.0060, 0.0075}
    assert {candidate.collider_contact_offset for candidate in candidates} == {0.002, 0.004, 0.006}
    assert {candidate.collider_rest_offset for candidate in candidates} == {-0.001, 0.000}
    assert {candidate.initial_radial_velocity for candidate in candidates} == {0.02, 0.04, 0.08}
    assert [
        (
            candidate.candidate_id,
            candidate.panel_count,
            candidate.wall_thickness,
            candidate.bottom_overlap,
            candidate.particle_contact_offset,
            candidate.collider_contact_offset,
            candidate.collider_rest_offset,
            candidate.initial_radial_velocity,
        )
        for candidate in candidates
    ] == [
        ("C2A_001", 24, 0.010, 0.000, 0.0045, 0.002, 0.000, 0.08),
        ("C2A_002", 24, 0.014, 0.003, 0.0060, 0.004, -0.001, 0.04),
        ("C2A_003", 24, 0.018, 0.006, 0.0075, 0.006, 0.000, 0.02),
        ("C2A_004", 32, 0.010, 0.003, 0.0075, 0.006, -0.001, 0.08),
        ("C2A_005", 32, 0.014, 0.006, 0.0045, 0.002, 0.000, 0.04),
        ("C2A_006", 32, 0.018, 0.000, 0.0060, 0.004, -0.001, 0.02),
        ("C2A_007", 48, 0.010, 0.006, 0.0060, 0.006, 0.000, 0.04),
        ("C2A_008", 48, 0.014, 0.000, 0.0075, 0.002, -0.001, 0.02),
        ("C2A_009", 48, 0.018, 0.003, 0.0045, 0.004, 0.000, 0.08),
        ("C2A_010", 32, 0.014, 0.003, 0.0060, 0.006, -0.001, 0.04),
        ("C2A_011", 48, 0.018, 0.006, 0.0075, 0.006, -0.001, 0.02),
        ("C2A_012", 24, 0.018, 0.006, 0.0075, 0.006, -0.001, 0.08),
    ]


def test_c2a_candidate_materializes_config_and_variant_spec():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import C2ProxyCandidate

    candidate = C2ProxyCandidate(
        candidate_id="C2A_999",
        panel_count=32,
        wall_thickness=0.014,
        bottom_overlap=0.003,
        particle_contact_offset=0.006,
        collider_contact_offset=0.004,
        collider_rest_offset=-0.001,
        initial_radial_velocity=0.04,
    )

    config = candidate.to_config(base=ColliderConfig(steps=12))
    spec = candidate.to_variant_spec()

    assert config.steps == 12
    assert config.wall_thickness == 0.014
    assert config.bottom_overlap == 0.003
    assert config.particle_contact_offset == 0.006
    assert config.collider_contact_offset == 0.004
    assert config.collider_rest_offset == -0.001
    assert config.initial_radial_velocity == 0.04
    assert isinstance(spec, VariantSpec)
    assert spec.variant_id == "C2A_999"
    assert spec.panel_count == 32
    assert spec.collision_approximation == "convex_panel_boxes"


def test_s2f2_sweep_targets_only_near_pass_candidates_and_keeps_geometry_fixed():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_velocity_contact_offset_sweep

    candidates = build_velocity_contact_offset_sweep(
        s2f1_manifest_path=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_followup_c2_proxy_sweep_20260707.json"
        )
    )

    parents = {candidate.parent_candidate_id for candidate in candidates}
    assert parents == {"C2A_005", "C2A_009", "C2A_007"}
    assert len(candidates) == 18

    by_parent = {parent: [candidate for candidate in candidates if candidate.parent_candidate_id == parent] for parent in parents}
    for parent, group in by_parent.items():
        assert [candidate.variable_group for candidate in group] == [
            "baseline_repeat",
            "velocity_020",
            "particle_contact",
            "collider_contact_rest",
            "ccd_enabled",
            "max_velocity_guardrail",
        ]
        baseline = group[0]
        for candidate in group:
            assert candidate.panel_count == baseline.panel_count
            assert candidate.wall_thickness == baseline.wall_thickness
            assert candidate.bottom_overlap == baseline.bottom_overlap
            assert candidate.spawn_particle_contact_offset == baseline.particle_contact_offset

    assert [candidate.candidate_id for candidate in by_parent["C2A_005"]] == [
        "C2A_005_S2F2_BASE",
        "C2A_005_S2F2_VEL020",
        "C2A_005_S2F2_PCO060",
        "C2A_005_S2F2_CCO004_RN001",
        "C2A_005_S2F2_CCD1",
        "C2A_005_S2F2_VMAX010",
    ]
    assert next(c for c in candidates if c.candidate_id == "C2A_009_S2F2_VEL020").initial_radial_velocity == 0.02
    assert next(c for c in candidates if c.candidate_id == "C2A_005_S2F2_PCO060").particle_contact_offset == 0.006
    assert next(c for c in candidates if c.candidate_id == "C2A_007_S2F2_PCO045").particle_contact_offset == 0.0045
    capped = next(c for c in candidates if c.candidate_id == "C2A_007_S2F2_VMAX010")
    assert capped.non_physical_parameter_dependence_risk is True
    assert capped.particle_max_velocity == 0.10


def test_s2f2_candidate_materializes_particle_system_tuning():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import C2ProxyCandidate

    candidate = C2ProxyCandidate(
        candidate_id="C2A_005_S2F2_PCO060",
        parent_candidate_id="C2A_005",
        phase="S2F2_VELOCITY_CONTACT_OFFSET",
        variable_group="particle_contact",
        panel_count=32,
        wall_thickness=0.014,
        bottom_overlap=0.006,
        particle_contact_offset=0.006,
        spawn_particle_contact_offset=0.0045,
        particle_system_contact_offset=0.0072,
        fluid_rest_offset=0.0036,
        solid_rest_offset=0.0036,
        collider_contact_offset=0.002,
        collider_rest_offset=0.0,
        initial_radial_velocity=0.04,
        particle_max_velocity=5.0,
    )

    config = candidate.to_config(base=ColliderConfig(steps=12))
    spec = candidate.to_variant_spec()

    assert config.particle_contact_offset == 0.006
    assert config.spawn_particle_contact_offset == 0.0045
    assert config.particle_system_contact_offset == 0.0072
    assert config.fluid_rest_offset == 0.0036
    assert config.solid_rest_offset == 0.0036
    assert config.collider_contact_offset == 0.002
    assert config.collider_rest_offset == 0.0
    assert config.particle_enable_ccd is None
    assert config.particle_max_velocity == 5.0
    assert config.particle_max_depenetration_velocity is None
    assert spec.variant_id == "C2A_005_S2F2_PCO060"
    assert spec.setup == "s2f2_velocity_contact_offset"
    assert spec.panel_count == 32


def test_followup_pass_criteria_require_zero_outside_source():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import classify_followup_candidate

    result = classify_followup_candidate(
        candidate_id="C2A_001",
        source_retention_fraction=1.0,
        particle_count_final_fraction=1.0,
        outside_source_count=1,
        target_count=0,
        spill_count=0,
        below_table_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        nan_count=0,
        non_physical_parameter_dependence=False,
    )

    assert result["classification"] == "FAIL_CONTAINER_LEAK"
    assert result["pass_criteria"]["outside_source_count_eq_zero"] is False


def test_non_physical_parameter_dependence_cannot_promote_candidate():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        classify_followup_candidate,
        rank_followup_candidates,
    )

    result = classify_followup_candidate(
        candidate_id="C2A_001",
        source_retention_fraction=1.0,
        particle_count_final_fraction=1.0,
        outside_source_count=0,
        target_count=0,
        spill_count=0,
        below_table_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        nan_count=0,
        non_physical_parameter_dependence=True,
    )
    ranked = rank_followup_candidates([result])

    assert result["classification"] == "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE"
    assert ranked["best_for_s3"] == []
    assert ranked["s2f1_status"] == "STOP_WITH_EVIDENCE"


def test_s2f2_diagnosis_classifies_velocity_contact_geometry_and_nonphysical():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import analyze_s2f2_diagnosis

    base_fail = {
        "candidate_id": "C2A_005_S2F2_BASE",
        "parent_candidate_id": "C2A_005",
        "variable_group": "baseline_repeat",
        "classification": "FAIL_CONTAINER_LEAK",
        "source_retention_fraction": 0.9921875,
        "outside_source_count": 2,
        "spill_count": 2,
        "below_table_count": 0,
    }
    velocity_pass = {
        **base_fail,
        "candidate_id": "C2A_005_S2F2_VEL_ZERO",
        "variable_group": "velocity_020",
        "classification": "PASS_SOURCE_HOLD",
        "outside_source_count": 0,
        "spill_count": 0,
    }
    contact_pass = {
        **base_fail,
        "candidate_id": "C2A_005_S2F2_PCO060",
        "variable_group": "particle_contact",
        "classification": "PASS_SOURCE_HOLD",
        "outside_source_count": 0,
        "spill_count": 0,
    }
    nonphysical_only = {
        **base_fail,
        "candidate_id": "C2A_005_S2F2_VMAX010",
        "variable_group": "max_velocity_guardrail",
        "classification": "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE",
        "outside_source_count": 0,
        "spill_count": 0,
    }

    assert analyze_s2f2_diagnosis([base_fail, velocity_pass])["conclusion"] == "INITIAL_RADIAL_VELOCITY_SENSITIVITY"
    assert analyze_s2f2_diagnosis([base_fail, contact_pass])["conclusion"] == "PARTICLE_CONTACT_OFFSET_SENSITIVITY"
    assert analyze_s2f2_diagnosis([base_fail])["conclusion"] == "RESIDUAL_PROXY_GEOMETRY_GAP_SUSPECTED"
    assert analyze_s2f2_diagnosis([base_fail, nonphysical_only])["conclusion"] == "NON_PHYSICAL_DAMPING_ONLY"


def test_s2f2_diagnosis_marks_velocity_pass_with_hash_mismatch_as_coupled():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import analyze_s2f2_diagnosis

    base_fail = {
        "candidate_id": "C2A_009_S2F2_BASE",
        "parent_candidate_id": "C2A_009",
        "variable_group": "baseline_repeat",
        "classification": "FAIL_CONTAINER_LEAK",
        "source_retention_fraction": 0.9921875,
        "outside_source_count": 2,
        "spill_count": 2,
        "below_table_count": 0,
        "initial_particle_positions_hash": "hash-base",
    }
    velocity_pass = {
        **base_fail,
        "candidate_id": "C2A_009_S2F2_VEL020",
        "variable_group": "velocity_020",
        "classification": "PASS_SOURCE_HOLD",
        "outside_source_count": 0,
        "spill_count": 0,
        "initial_particle_positions_hash": "hash-vel020",
    }

    diagnosis = analyze_s2f2_diagnosis([base_fail, velocity_pass])

    assert diagnosis["conclusion"] == "VELOCITY_INITIAL_LAYOUT_COUPLED_SENSITIVITY"
    assert diagnosis["velocity_pass_candidates_with_initial_hash_mismatch"] == ["C2A_009_S2F2_VEL020"]
    assert diagnosis["root_cause_confidence"] == "COUPLED_DIAGNOSTIC"


def test_s2f3_builds_required_sdf_grid():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_s2f3_sdf_sweep

    candidates = build_s2f3_sdf_sweep()

    assert len(candidates) == 24
    assert [candidate.candidate_id for candidate in candidates] == [f"C3A_{index:03d}" for index in range(1, 25)]
    assert {candidate.phase for candidate in candidates} == {"S2F3_C3_SDF_SWEEP"}
    assert {candidate.variable_group for candidate in candidates} == {"sdf_cooking_sweep"}
    assert {candidate.sdf_resolution for candidate in candidates} == {64, 96, 128}
    assert {candidate.sdf_subgrid_resolution for candidate in candidates} == {4, 8}
    assert {candidate.sdf_margin for candidate in candidates} == {0.002, 0.005}
    assert {candidate.sdf_narrow_band_thickness for candidate in candidates} == {0.01, 0.02}
    assert {candidate.mesh_bottom_fan_closure for candidate in candidates} == {True}
    assert {candidate.normals_winding_audit for candidate in candidates} == {"pass"}
    assert [
        (
            candidate.candidate_id,
            candidate.sdf_resolution,
            candidate.sdf_subgrid_resolution,
            candidate.sdf_margin,
            candidate.sdf_narrow_band_thickness,
        )
        for candidate in candidates[:4]
    ] == [
        ("C3A_001", 64, 4, 0.002, 0.01),
        ("C3A_002", 64, 4, 0.002, 0.02),
        ("C3A_003", 64, 4, 0.005, 0.01),
        ("C3A_004", 64, 4, 0.005, 0.02),
    ]


def test_s2f3_candidate_materializes_sdf_config_and_spec():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_s2f3_sdf_sweep

    candidate = build_s2f3_sdf_sweep(limit=1)[0]

    config = candidate.to_config(base=ColliderConfig(steps=12))
    spec = candidate.to_variant_spec()

    assert config.steps == 12
    assert config.sdf_resolution == 64
    assert config.sdf_subgrid_resolution == 4
    assert config.sdf_margin == 0.002
    assert config.sdf_narrow_band_thickness == 0.01
    assert isinstance(spec, VariantSpec)
    assert spec.variant_id == "C3A_001"
    assert spec.setup == "s2f3_sdf_open_concave_mesh"
    assert spec.collision_approximation == "sdf"
    assert spec.source_kind == "procedural_mesh"
    assert spec.sdf_resolution == 64
    assert spec.sdf_subgrid_resolution == 4
    assert spec.sdf_margin == 0.002
    assert spec.sdf_narrow_band_thickness == 0.01


def test_s2f4_builds_native_mesh_isolation_candidates():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_s2f4_native_mesh_isolation

    candidates = build_s2f4_native_mesh_isolation()

    assert [candidate.candidate_id for candidate in candidates] == [
        "C4A_convexDecomposition_reference_scope_closed",
        "C4A_sdf_reference_scope_closed",
        "C4A_native_render_mesh_plus_proxy_collision",
    ]
    assert {candidate.phase for candidate in candidates} == {"S2F4_C4_NATIVE_MESH_ISOLATION"}
    assert [candidate.native_collision_route for candidate in candidates] == [
        "convexDecomposition",
        "sdf",
        "render_mesh_plus_proxy_collision",
    ]
    assert {candidate.native_reference_scope for candidate in candidates} == {"parent_scope"}
    assert {candidate.native_material_binding_strategy for candidate in candidates} == {
        "local_blue_glass_override"
    }
    assert {candidate.native_material_binding_scope_closed for candidate in candidates} == {True}
    assert {candidate.native_pose_alignment for candidate in candidates} == {"bbox_recenter_to_source_region"}
    assert [candidate.native_mesh_collision_enabled for candidate in candidates] == [True, True, False]
    assert [candidate.proxy_collision_enabled for candidate in candidates] == [False, False, True]


def test_s2f4_candidate_materializes_native_variant_spec():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_s2f4_native_mesh_isolation

    candidate = build_s2f4_native_mesh_isolation()[1]
    config = candidate.to_config(base=ColliderConfig(steps=12))
    spec = candidate.to_variant_spec()

    assert config.steps == 12
    assert config.sdf_resolution == 128
    assert spec.variant_id == "C4A_sdf_reference_scope_closed"
    assert spec.setup == "s2f4_native_beaker_mesh_isolation"
    assert spec.source_kind == "native_mesh_reference"
    assert spec.native_source_path == "/World/beaker2"
    assert spec.native_mesh_source_path == "/World/beaker2/mesh"
    assert spec.collision_approximation == "sdf"
    assert spec.native_material_binding_scope_closed is True
    assert spec.native_pose_alignment == "bbox_recenter_to_source_region"


def test_write_s2f4_manifest_promotes_native_candidate_to_s2f5_not_s3(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f4_native_mesh_isolation,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidates = build_s2f4_native_mesh_isolation()
    candidate_results = [
        {
            **classify_followup_candidate(
                candidate_id="C4A_convexDecomposition_reference_scope_closed",
                source_retention_fraction=1.0,
                particle_count_final_fraction=1.0,
                outside_source_count=0,
                target_count=0,
                spill_count=0,
                below_table_count=0,
                tail_leak_rate_fraction_per_second=0.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=False,
            ),
            "parent_candidate_id": "C4",
            "phase": "S2F4_C4_NATIVE_MESH_ISOLATION",
            "variable_group": "convexDecomposition",
            "native_collision_route": "convexDecomposition",
            "native_mesh_collision_enabled": True,
            "proxy_collision_enabled": False,
            "readback_available": True,
            "evidence_files_complete": True,
        }
    ]
    for candidate in candidates[1:]:
        candidate_results.append(
            {
                **classify_followup_candidate(
                    candidate_id=candidate.candidate_id,
                    source_retention_fraction=0.0,
                    particle_count_final_fraction=1.0,
                    outside_source_count=256,
                    target_count=0,
                    spill_count=256,
                    below_table_count=0,
                    tail_leak_rate_fraction_per_second=0.5,
                    cpu_collision_fallback_detected=False,
                    gpu_collider_unsupported=False,
                    nan_count=0,
                    non_physical_parameter_dependence=False,
                ),
                "parent_candidate_id": "C4",
                "phase": "S2F4_C4_NATIVE_MESH_ISOLATION",
                "variable_group": candidate.variable_group,
                "native_collision_route": candidate.native_collision_route,
                "native_mesh_collision_enabled": candidate.native_mesh_collision_enabled,
                "proxy_collision_enabled": candidate.proxy_collision_enabled,
                "readback_available": True,
                "evidence_files_complete": True,
            }
        )

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F4_C4_NATIVE_MESH_ISOLATION",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F4_C4_NATIVE_MESH_ISOLATION",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
        source_s2f1_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json"
        ),
    )

    assert manifest["stage"] == "S2F4_C4_NATIVE_MESH_ISOLATION"
    assert manifest["status"] == "GO_NEXT"
    assert manifest["reason"] == "at_least_one_c4a_native_candidate_passed"
    assert manifest["best_for_s2f5"] == ["C4A_convexDecomposition_reference_scope_closed"]
    assert manifest["best_for_s3"] == []
    assert manifest["native_beaker_fluid_safe_collider_status"] == (
        "NATIVE_BEAKER_FLUID_SAFE_COLLIDER_CANDIDATE_FOUND"
    )
    assert manifest["s3_kinematic_pour_released"] is False
    assert manifest["next_stage"]["id"] == "S2F5_PROMOTION_REVIEW"
    assert manifest["next_stage"]["not_s3_release"] is True
    assert manifest["phase_specs"]["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] == "COMPLETE_GO_NEXT"
    assert manifest["phase_specs"]["S2F5_PROMOTION_REVIEW"]["status"] == "NEXT"


def test_write_s2f4_manifest_marks_proxy_wrapper_pass_as_wrapped_route_not_native_collider(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f4_native_mesh_isolation,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidates = build_s2f4_native_mesh_isolation()
    candidate_results = [
        {
            **classify_followup_candidate(
                candidate_id="C4A_native_render_mesh_plus_proxy_collision",
                source_retention_fraction=1.0,
                particle_count_final_fraction=1.0,
                outside_source_count=0,
                target_count=0,
                spill_count=0,
                below_table_count=0,
                tail_leak_rate_fraction_per_second=0.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=False,
            ),
            "parent_candidate_id": "C4",
            "phase": "S2F4_C4_NATIVE_MESH_ISOLATION",
            "variable_group": "render_mesh_plus_proxy_collision",
            "native_collision_route": "render_mesh_plus_proxy_collision",
            "native_mesh_collision_enabled": False,
            "proxy_collision_enabled": True,
            "readback_available": True,
            "evidence_files_complete": True,
        }
    ]
    for candidate in candidates[:2]:
        candidate_results.append(
            {
                **classify_followup_candidate(
                    candidate_id=candidate.candidate_id,
                    source_retention_fraction=0.0,
                    particle_count_final_fraction=1.0,
                    outside_source_count=256,
                    target_count=0,
                    spill_count=256,
                    below_table_count=0,
                    tail_leak_rate_fraction_per_second=0.5,
                    cpu_collision_fallback_detected=False,
                    gpu_collider_unsupported=False,
                    nan_count=0,
                    non_physical_parameter_dependence=False,
                ),
                "parent_candidate_id": "C4",
                "phase": "S2F4_C4_NATIVE_MESH_ISOLATION",
                "variable_group": candidate.variable_group,
                "native_collision_route": candidate.native_collision_route,
                "native_mesh_collision_enabled": candidate.native_mesh_collision_enabled,
                "proxy_collision_enabled": candidate.proxy_collision_enabled,
                "readback_available": True,
                "evidence_files_complete": True,
            }
        )

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F4_C4_NATIVE_MESH_ISOLATION",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F4_C4_NATIVE_MESH_ISOLATION",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
        source_s2f1_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json"
        ),
    )

    assert manifest["status"] == "GO_NEXT"
    assert manifest["best_for_s2f5"] == ["C4A_native_render_mesh_plus_proxy_collision"]
    assert manifest["best_for_s3"] == []
    assert manifest["native_beaker_fluid_safe_collider_status"] == "NATIVE_BEAKER_REQUIRES_PROXY_WRAPPER"
    assert manifest["native_issue_partition"] == "native_render_mesh_plus_proxy_collision_passed"
    assert manifest["allowed_claims"] == [
        "S2F4 found a native render mesh plus proxy collision route for S2F5 review."
    ]
    assert manifest["blocked_claims"]
    assert "native beaker mesh itself is fluid-safe" in manifest["blocked_claims"]


def test_write_s2f4_manifest_signs_native_beaker_not_fluid_safe_when_all_fail(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f4_native_mesh_isolation,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidates = build_s2f4_native_mesh_isolation()
    candidate_results = []
    for candidate in candidates:
        candidate_results.append(
            {
                **classify_followup_candidate(
                    candidate_id=candidate.candidate_id,
                    source_retention_fraction=0.0,
                    particle_count_final_fraction=1.0,
                    outside_source_count=256,
                    target_count=0,
                    spill_count=256,
                    below_table_count=0,
                    tail_leak_rate_fraction_per_second=0.5,
                    cpu_collision_fallback_detected=False,
                    gpu_collider_unsupported=False,
                    nan_count=0,
                    non_physical_parameter_dependence=False,
                ),
                "parent_candidate_id": "C4",
                "phase": "S2F4_C4_NATIVE_MESH_ISOLATION",
                "variable_group": candidate.variable_group,
                "native_collision_route": candidate.native_collision_route,
                "native_mesh_collision_enabled": candidate.native_mesh_collision_enabled,
                "proxy_collision_enabled": candidate.proxy_collision_enabled,
                "readback_available": True,
                "evidence_files_complete": True,
            }
        )

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F4_C4_NATIVE_MESH_ISOLATION",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F4_C4_NATIVE_MESH_ISOLATION",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
        source_s2f1_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f3_c3_sdf_sweep_20260708.json"
        ),
    )

    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["reason"] == "native_beaker_not_fluid_safe_collider"
    assert manifest["native_beaker_fluid_safe_collider_status"] == "NATIVE_BEAKER_NOT_FLUID_SAFE_COLLIDER"
    assert manifest["best_for_s2f5"] == []
    assert manifest["best_for_s3"] == []
    assert manifest["s3_kinematic_pour_released"] is False
    assert manifest["next_stage"]["id"] == "S2_PROXY_WRAPPER_DESIGN_FOLLOW_UP"
    assert manifest["next_stage"]["not_s3_release"] is True


def test_write_s2f4_manifest_does_not_sign_native_no_go_for_partial_results(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f4_native_mesh_isolation,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidates = build_s2f4_native_mesh_isolation()
    candidate_results = [
        {
            **classify_followup_candidate(
                candidate_id="C4A_convexDecomposition_reference_scope_closed",
                source_retention_fraction=0.0,
                particle_count_final_fraction=1.0,
                outside_source_count=256,
                target_count=0,
                spill_count=0,
                below_table_count=256,
                tail_leak_rate_fraction_per_second=0.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=False,
            ),
            "parent_candidate_id": "C4",
            "phase": "S2F4_C4_NATIVE_MESH_ISOLATION",
            "variable_group": "convexDecomposition",
            "native_collision_route": "convexDecomposition",
            "native_mesh_collision_enabled": True,
            "proxy_collision_enabled": False,
            "readback_available": True,
            "evidence_files_complete": True,
        }
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F4_C4_NATIVE_MESH_ISOLATION",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F4_C4_NATIVE_MESH_ISOLATION",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
    )

    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["reason"] == "s2f4_incomplete_candidate_results"
    assert manifest["native_beaker_fluid_safe_collider_status"] == "INCOMPLETE_C4A_EVIDENCE"
    assert manifest["native_issue_partition"] == "incomplete_c4a_runtime_results"
    assert manifest["best_for_s2f5"] == []
    assert manifest["best_for_s3"] == []
    assert manifest["next_stage"]["id"] == "S2F4_C4_NATIVE_MESH_ISOLATION"
    assert manifest["phase_specs"]["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] == "ACTIVE"
    assert manifest["next_stage"]["variants"] == [
        "C4A_sdf_reference_scope_closed",
        "C4A_native_render_mesh_plus_proxy_collision",
    ]


def test_write_s2f4_manifest_does_not_promote_partial_pass(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f4_native_mesh_isolation,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidates = build_s2f4_native_mesh_isolation()
    candidate_results = [
        {
            **classify_followup_candidate(
                candidate_id="C4A_convexDecomposition_reference_scope_closed",
                source_retention_fraction=1.0,
                particle_count_final_fraction=1.0,
                outside_source_count=0,
                target_count=0,
                spill_count=0,
                below_table_count=0,
                tail_leak_rate_fraction_per_second=0.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=False,
            ),
            "parent_candidate_id": "C4",
            "phase": "S2F4_C4_NATIVE_MESH_ISOLATION",
            "variable_group": "convexDecomposition",
            "native_collision_route": "convexDecomposition",
            "native_mesh_collision_enabled": True,
            "proxy_collision_enabled": False,
            "readback_available": True,
            "evidence_files_complete": True,
        }
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F4_C4_NATIVE_MESH_ISOLATION",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F4_C4_NATIVE_MESH_ISOLATION",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
    )

    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["reason"] == "s2f4_incomplete_candidate_results"
    assert manifest["native_beaker_fluid_safe_collider_status"] == "INCOMPLETE_C4A_EVIDENCE"
    assert manifest["best_for_s2f5"] == []
    assert manifest["best_for_s3"] == []
    assert manifest["next_stage"]["id"] == "S2F4_C4_NATIVE_MESH_ISOLATION"
    assert manifest["phase_specs"]["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] == "ACTIVE"


def test_write_s2f4_manifest_clears_promotion_on_blocking_runtime_warning(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f4_native_mesh_isolation,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidates = build_s2f4_native_mesh_isolation()
    candidate_results = [
        {
            **classify_followup_candidate(
                candidate_id="C4A_convexDecomposition_reference_scope_closed",
                source_retention_fraction=1.0,
                particle_count_final_fraction=1.0,
                outside_source_count=0,
                target_count=0,
                spill_count=0,
                below_table_count=0,
                tail_leak_rate_fraction_per_second=0.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=False,
            ),
            "parent_candidate_id": "C4",
            "phase": "S2F4_C4_NATIVE_MESH_ISOLATION",
            "variable_group": "convexDecomposition",
            "native_collision_route": "convexDecomposition",
            "native_mesh_collision_enabled": True,
            "proxy_collision_enabled": False,
            "readback_available": True,
            "evidence_files_complete": True,
        }
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F4_C4_NATIVE_MESH_ISOLATION",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F4_C4_NATIVE_MESH_ISOLATION",
        runtime_warning_scan={
            "blocking_runtime_warning_detected": True,
            "pattern_counts": {"physx_error": 1},
        },
    )

    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["reason"] == "blocking_runtime_warning_detected"
    assert manifest["best_for_s2f5"] == []
    assert manifest["best_for_s3"] == []
    assert manifest["next_stage"]["id"] == "S2F4_C4_NATIVE_MESH_ISOLATION"
    assert manifest["next_stage"]["not_s3_release"] is True
    assert manifest["phase_specs"]["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] == "ACTIVE"


def test_s2f4_material_binding_scope_warning_is_blocking(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import _runtime_warning_gate

    gate = _runtime_warning_gate(
        {
            "blocking_runtime_warning_detected": False,
            "pattern_counts": {
                "cpu_fallback": 0,
                "gpu_unsupported": 0,
                "physx_error": 0,
                "sdf_warning": 0,
                "material_binding_scope_warning": 1,
            },
        },
        phase="S2F4_C4_NATIVE_MESH_ISOLATION",
    )

    assert gate["passed"] is False
    assert gate["blocking_runtime_warning_detected"] is True
    assert gate["blocking_warning_reasons"] == ["material_binding_scope_warning"]


def test_s2f4_plan_only_cli_writes_native_mesh_isolation_manifest(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import main

    manifest_path = tmp_path / "s2f4.json"
    artifact_dir = tmp_path / "artifacts"
    scene_dir = tmp_path / "scenes"

    exit_code = main(
        [
            "--phase",
            "S2F4_C4_NATIVE_MESH_ISOLATION",
            "--manifest-path",
            str(manifest_path),
            "--artifact-dir",
            str(artifact_dir),
            "--scene-dir",
            str(scene_dir),
            "--plan-only",
        ]
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert manifest["stage"] == "S2F4_C4_NATIVE_MESH_ISOLATION"
    assert manifest["status"] == "PLAN_READY"
    assert manifest["candidate_count"] == 3
    assert [candidate["candidate_id"] for candidate in manifest["candidate_plan"]] == [
        "C4A_convexDecomposition_reference_scope_closed",
        "C4A_sdf_reference_scope_closed",
        "C4A_native_render_mesh_plus_proxy_collision",
    ]
    assert manifest["next_stage"]["id"] == "S2F4_C4_NATIVE_MESH_ISOLATION"


def test_s2f4_cli_rejects_candidate_limit_for_evidence_integrity(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import main

    with pytest.raises(SystemExit, match="S2F4_C4_NATIVE_MESH_ISOLATION does not support --candidate-limit"):
        main(
            [
                "--phase",
                "S2F4_C4_NATIVE_MESH_ISOLATION",
                "--manifest-path",
                str(tmp_path / "s2f4.json"),
                "--artifact-dir",
                str(tmp_path / "artifacts"),
                "--scene-dir",
                str(tmp_path / "scenes"),
                "--candidate-limit",
                "1",
                "--plan-only",
            ]
        )


def test_write_s2f2_manifest_records_promotion_caveat_when_hashes_are_coupled(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_velocity_contact_offset_sweep,
        classify_followup_candidate,
        write_followup_manifest,
    )

    base_fail = {
        **classify_followup_candidate(
            candidate_id="C2A_009_S2F2_BASE",
            source_retention_fraction=0.9921875,
            particle_count_final_fraction=1.0,
            outside_source_count=2,
            target_count=0,
            spill_count=2,
            below_table_count=0,
            tail_leak_rate_fraction_per_second=0.0,
            cpu_collision_fallback_detected=False,
            gpu_collider_unsupported=False,
            nan_count=0,
            non_physical_parameter_dependence=False,
        ),
        "parent_candidate_id": "C2A_009",
        "phase": "S2F2_VELOCITY_CONTACT_OFFSET",
        "variable_group": "baseline_repeat",
        "initial_particle_positions_hash": "hash-base",
        "spawn_position_pinned": True,
        "initial_region_counts": {"source_count": 256, "spill_count": 0},
    }
    velocity_pass = {
        **classify_followup_candidate(
            candidate_id="C2A_009_S2F2_VEL020",
            source_retention_fraction=1.0,
            particle_count_final_fraction=1.0,
            outside_source_count=0,
            target_count=0,
            spill_count=0,
            below_table_count=0,
            tail_leak_rate_fraction_per_second=0.0,
            cpu_collision_fallback_detected=False,
            gpu_collider_unsupported=False,
            nan_count=0,
            non_physical_parameter_dependence=False,
        ),
        "parent_candidate_id": "C2A_009",
        "phase": "S2F2_VELOCITY_CONTACT_OFFSET",
        "variable_group": "velocity_020",
        "initial_particle_positions_hash": "hash-vel020",
        "spawn_position_pinned": True,
        "initial_region_counts": {"source_count": 256, "spill_count": 0},
    }

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F2_VELOCITY_CONTACT_OFFSET",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=build_velocity_contact_offset_sweep(limit=1),
        candidate_results=[base_fail, velocity_pass],
        command="runner --phase S2F2_VELOCITY_CONTACT_OFFSET",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
    )

    assert manifest["next_stage"]["id"] == "S2F5_PROMOTION_REVIEW"
    assert manifest["next_stage"]["not_s3_release"] is True
    assert manifest["next_stage"]["requires_initial_layout_hash_stability_check"] is True
    assert manifest["next_stage"]["promotion_caveat"] == "COUPLED_DIAGNOSTIC_REQUIRES_INITIAL_LAYOUT_RETEST"


def test_write_followup_manifest_records_parent_baseline_and_candidates(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_c2_proxy_sweep,
        write_followup_manifest,
    )

    manifest_path = tmp_path / "manifest.json"
    candidates = build_c2_proxy_sweep(limit=2)

    manifest = write_followup_manifest(
        manifest_path,
        phase="S2F1_C2_PROXY_SWEEP",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=[],
        command="runner --phase S2F1_C2_PROXY_SWEEP",
        runtime_warning_scan=None,
    )

    assert manifest_path.exists()
    assert manifest["stage"] == "S2F1_C2_PROXY_SWEEP"
    assert manifest["status"] == "PLAN_READY"
    assert manifest["run_id"] == "artifacts"
    assert manifest["s3_kinematic_pour_released"] is False
    assert manifest["best_for_s3"] == []
    assert manifest["parent_s2_manifest"].endswith("fluid_spike_s2_collider_matrix_20260707.json")
    assert manifest["baseline_freeze_manifest"].endswith("fluid_spike_s2f0_baseline_freeze_20260707.json")
    assert [candidate["candidate_id"] for candidate in manifest["candidate_plan"]] == ["C2A_001", "C2A_002"]


def test_write_followup_manifest_records_near_pass_candidates_for_s2f2(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_c2_proxy_sweep,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidate_results = [
        classify_followup_candidate(
            candidate_id="C2A_005",
            source_retention_fraction=0.9921875,
            particle_count_final_fraction=1.0,
            outside_source_count=2,
            target_count=0,
            spill_count=2,
            below_table_count=0,
            tail_leak_rate_fraction_per_second=0.0,
            cpu_collision_fallback_detected=False,
            gpu_collider_unsupported=False,
            nan_count=0,
            non_physical_parameter_dependence=False,
        ),
        classify_followup_candidate(
            candidate_id="C2A_006",
            source_retention_fraction=0.53125,
            particle_count_final_fraction=1.0,
            outside_source_count=120,
            target_count=0,
            spill_count=57,
            below_table_count=63,
            tail_leak_rate_fraction_per_second=0.0,
            cpu_collision_fallback_detected=False,
            gpu_collider_unsupported=False,
            nan_count=0,
            non_physical_parameter_dependence=False,
        ),
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F1_C2_PROXY_SWEEP",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=build_c2_proxy_sweep(limit=2),
        candidate_results=candidate_results,
        command="runner --phase S2F1_C2_PROXY_SWEEP",
        runtime_warning_scan=None,
    )

    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["near_pass_for_s2f2"] == ["C2A_005"]
    assert manifest["next_stage"]["id"] == "S2F2_VELOCITY_CONTACT_OFFSET"
    assert manifest["next_stage"]["variants"] == ["C2A_005"]


def test_write_s2f2_manifest_records_s2f5_candidates_and_keeps_s3_closed(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_velocity_contact_offset_sweep,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidate_results = [
        {
            **classify_followup_candidate(
                candidate_id="C2A_009_S2F2_VEL020",
                source_retention_fraction=1.0,
                particle_count_final_fraction=1.0,
                outside_source_count=0,
                target_count=0,
                spill_count=0,
                below_table_count=0,
                tail_leak_rate_fraction_per_second=0.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=False,
            ),
            "parent_candidate_id": "C2A_009",
            "phase": "S2F2_VELOCITY_CONTACT_OFFSET",
            "variable_group": "velocity_020",
            "initial_particle_positions_hash": "hash-vel020",
            "spawn_position_pinned": True,
            "initial_region_counts": {"source_count": 256, "spill_count": 0},
        }
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F2_VELOCITY_CONTACT_OFFSET",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=build_velocity_contact_offset_sweep(limit=1),
        candidate_results=candidate_results,
        command="runner --phase S2F2_VELOCITY_CONTACT_OFFSET",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
    )

    assert manifest["status"] == "GO_NEXT"
    assert manifest["best_for_s2f5"] == ["C2A_009_S2F2_VEL020"]
    assert manifest["best_for_s3"] == []
    assert manifest["s2f5_promotion_review_next"] is True
    assert manifest["s3_kinematic_pour_released"] is False
    assert manifest["s2f2_diagnosis"]["conclusion"] == "INITIAL_RADIAL_VELOCITY_SENSITIVITY"
    assert manifest["s2f2_initial_layout_hash_audit"]["parents"]["C2A_009"]["hash_count"] == 1
    assert manifest["s2f2_initial_layout_hash_audit"]["parents"]["C2A_009"]["spawn_position_pinned_all"] is True
    assert manifest["next_stage"]["id"] == "S2F5_PROMOTION_REVIEW"
    assert manifest["next_stage"]["variants"] == ["C2A_009_S2F2_VEL020"]
    assert manifest["next_stage"]["not_s3_release"] is True
    assert manifest["next_stage"]["requires_initial_layout_hash_stability_check"] is False
    assert manifest["phase_specs"]["S2F1_C2_PROXY_SWEEP"]["status"] == "COMPLETE_STOP_WITH_EVIDENCE"
    assert manifest["phase_specs"]["S2F2_VELOCITY_CONTACT_OFFSET"]["status"] == "COMPLETE_GO_NEXT"
    assert manifest["phase_specs"]["S2F5_PROMOTION_REVIEW"]["status"] == "NEXT"


def test_write_s2f3_manifest_promotes_to_s2f5_not_s3(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f3_sdf_sweep,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidates = build_s2f3_sdf_sweep(limit=1)
    candidate_results = [
        {
            **classify_followup_candidate(
                candidate_id="C3A_001",
                source_retention_fraction=1.0,
                particle_count_final_fraction=1.0,
                outside_source_count=0,
                target_count=0,
                spill_count=0,
                below_table_count=0,
                tail_leak_rate_fraction_per_second=0.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=False,
            ),
            "parent_candidate_id": None,
            "phase": "S2F3_C3_SDF_SWEEP",
            "variable_group": "sdf_cooking_sweep",
            "readback_available": True,
            "evidence_files_complete": True,
        }
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F3_C3_SDF_SWEEP",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F3_C3_SDF_SWEEP",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
        source_s2f1_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f5_promotion_review_20260708.json"
        ),
    )

    assert manifest["stage"] == "S2F3_C3_SDF_SWEEP"
    assert manifest["manifest_type"] == "true_physx_pbd_fluid_spike_s2f3_c3_sdf_sweep"
    assert manifest["status"] == "GO_NEXT"
    assert manifest["reason"] == "at_least_one_c3a_sdf_candidate_passed"
    assert manifest["best_for_s2f5"] == ["C3A_001"]
    assert manifest["best_for_s3"] == []
    assert manifest["s2f5_promotion_review_next"] is True
    assert manifest["s3_kinematic_pour_released"] is False
    assert manifest["next_stage"]["id"] == "S2F5_PROMOTION_REVIEW"
    assert manifest["next_stage"]["variants"] == ["C3A_001"]
    assert manifest["next_stage"]["not_s3_release"] is True
    assert manifest["phase_specs"]["S2F3_C3_SDF_SWEEP"]["status"] == "COMPLETE_GO_NEXT"
    assert manifest["phase_specs"]["S2F5_PROMOTION_REVIEW"]["status"] == "NEXT"


def test_write_s2f3_manifest_moves_to_s2f4_when_sdf_fails(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f3_sdf_sweep,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidates = build_s2f3_sdf_sweep(limit=1)
    candidate_results = [
        {
            **classify_followup_candidate(
                candidate_id="C3A_001",
                source_retention_fraction=0.99,
                particle_count_final_fraction=1.0,
                outside_source_count=1,
                target_count=0,
                spill_count=1,
                below_table_count=0,
                tail_leak_rate_fraction_per_second=0.0,
                cpu_collision_fallback_detected=False,
                gpu_collider_unsupported=False,
                nan_count=0,
                non_physical_parameter_dependence=False,
            ),
            "parent_candidate_id": None,
            "phase": "S2F3_C3_SDF_SWEEP",
            "variable_group": "sdf_cooking_sweep",
            "readback_available": True,
            "evidence_files_complete": True,
        }
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F3_C3_SDF_SWEEP",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F3_C3_SDF_SWEEP",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
        source_s2f1_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f5_promotion_review_20260708.json"
        ),
    )

    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["reason"] == "no_c3a_sdf_candidate_passed"
    assert manifest["best_for_s2f5"] == []
    assert manifest["best_for_s3"] == []
    assert manifest["s3_kinematic_pour_released"] is False
    assert manifest["next_stage"]["id"] == "S2F4_C4_NATIVE_MESH_ISOLATION"
    assert manifest["next_stage"]["diagnostic_routes"] == ["S2F4_C4_NATIVE_MESH_ISOLATION"]
    assert manifest["next_stage"]["not_s3_release"] is True
    assert manifest["phase_specs"]["S2F3_C3_SDF_SWEEP"]["status"] == "COMPLETE_STOP_WITH_EVIDENCE"
    assert manifest["phase_specs"]["S2F4_C4_NATIVE_MESH_ISOLATION"]["status"] == "NEXT"


def test_s2f3_plan_only_cli_writes_full_sdf_grid_manifest(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import main

    manifest_path = tmp_path / "s2f3.json"
    artifact_dir = tmp_path / "artifacts"
    scene_dir = tmp_path / "scenes"

    exit_code = main(
        [
            "--phase",
            "S2F3_C3_SDF_SWEEP",
            "--manifest-path",
            str(manifest_path),
            "--artifact-dir",
            str(artifact_dir),
            "--scene-dir",
            str(scene_dir),
            "--plan-only",
        ]
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert manifest["stage"] == "S2F3_C3_SDF_SWEEP"
    assert manifest["status"] == "PLAN_READY"
    assert manifest["candidate_count"] == 24
    assert {candidate["candidate_id"][:3] for candidate in manifest["candidate_plan"]} == {"C3A"}
    assert manifest["next_stage"]["id"] == "S2F3_C3_SDF_SWEEP"


def test_s2f5_builds_only_promoted_vel020_trials():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_s2f5_promotion_review_sweep

    candidates = build_s2f5_promotion_review_sweep()

    assert len(candidates) == 6
    assert {candidate.parent_candidate_id for candidate in candidates} == {"C2A_009_S2F2_VEL020"}
    assert {candidate.particle_count for candidate in candidates} == {256, 1024}
    assert {candidate.particle_seed for candidate in candidates} == {0, 1, 2}
    assert all(candidate.phase == "S2F5_PROMOTION_REVIEW" for candidate in candidates)
    assert all(candidate.variable_group == "promotion_review" for candidate in candidates)
    assert [candidate.candidate_id for candidate in candidates] == [
        "C2A_009_S2F2_VEL020_S2F5_P0256_SEED000",
        "C2A_009_S2F2_VEL020_S2F5_P0256_SEED001",
        "C2A_009_S2F2_VEL020_S2F5_P0256_SEED002",
        "C2A_009_S2F2_VEL020_S2F5_P1024_SEED000",
        "C2A_009_S2F2_VEL020_S2F5_P1024_SEED001",
        "C2A_009_S2F2_VEL020_S2F5_P1024_SEED002",
    ]


def test_s2f5_builds_trials_for_s2f3_promoted_c3a_candidate(tmp_path):
    from dataclasses import asdict

    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f3_sdf_sweep,
        build_s2f5_promotion_review_sweep,
    )

    s2f3_candidate = build_s2f3_sdf_sweep(limit=1)[0]
    source_manifest = tmp_path / "s2f3_pass.json"
    source_manifest.write_text(
        json.dumps(
            {
                "stage": "S2F3_C3_SDF_SWEEP",
                "best_for_s2f5": ["C3A_001"],
                "candidate_plan": [asdict(s2f3_candidate)],
            }
        ),
        encoding="utf-8",
    )

    candidates = build_s2f5_promotion_review_sweep(s2f2_manifest_path=source_manifest)

    assert len(candidates) == 6
    assert {candidate.parent_candidate_id for candidate in candidates} == {"C3A_001"}
    assert {candidate.phase for candidate in candidates} == {"S2F5_PROMOTION_REVIEW"}
    assert {candidate.sdf_resolution for candidate in candidates} == {64}
    assert {candidate.sdf_subgrid_resolution for candidate in candidates} == {4}
    assert {candidate.sdf_margin for candidate in candidates} == {0.002}
    assert {candidate.sdf_narrow_band_thickness for candidate in candidates} == {0.01}
    assert candidates[0].candidate_id == "C3A_001_S2F5_P0256_SEED000"


def test_s2f5_builds_trials_for_s2f4_promoted_c4a_candidate(tmp_path):
    from dataclasses import asdict

    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f4_native_mesh_isolation,
        build_s2f5_promotion_review_sweep,
    )

    s2f4_candidate = build_s2f4_native_mesh_isolation()[2]
    source_manifest = tmp_path / "s2f4_proxy_pass.json"
    source_manifest.write_text(
        json.dumps(
            {
                "stage": "S2F4_C4_NATIVE_MESH_ISOLATION",
                "best_for_s2f5": ["C4A_native_render_mesh_plus_proxy_collision"],
                "candidate_plan": [asdict(s2f4_candidate)],
            }
        ),
        encoding="utf-8",
    )

    candidates = build_s2f5_promotion_review_sweep(s2f2_manifest_path=source_manifest)

    assert len(candidates) == 6
    assert {candidate.parent_candidate_id for candidate in candidates} == {
        "C4A_native_render_mesh_plus_proxy_collision"
    }
    assert {candidate.phase for candidate in candidates} == {"S2F5_PROMOTION_REVIEW"}
    assert {candidate.native_source_path for candidate in candidates} == {"/World/beaker2"}
    assert {candidate.native_mesh_source_path for candidate in candidates} == {"/World/beaker2/mesh"}
    assert {candidate.native_reference_scope for candidate in candidates} == {"parent_scope"}
    assert {candidate.native_collision_route for candidate in candidates} == {
        "render_mesh_plus_proxy_collision"
    }
    assert {candidate.native_mesh_collision_enabled for candidate in candidates} == {False}
    assert {candidate.proxy_collision_enabled for candidate in candidates} == {True}
    assert {candidate.panel_count for candidate in candidates} == {24}
    assert candidates[0].candidate_id == "C4A_native_render_mesh_plus_proxy_collision_S2F5_P0256_SEED000"


def test_s2f5_aggregation_promotes_only_when_all_required_trials_pass():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import aggregate_s2f5_promotion_review

    results = [
        {
            "candidate_id": f"C2A_009_S2F2_VEL020_S2F5_P{particle_count:04d}_SEED{seed:03d}",
            "parent_candidate_id": "C2A_009_S2F2_VEL020",
            "classification": "PASS_SOURCE_HOLD",
            "particle_count": particle_count,
            "particle_seed": seed,
            "readback_available": True,
            "evidence_files_complete": True,
            "non_physical_parameter_dependence": False,
        }
        for particle_count in (256, 1024)
        for seed in (0, 1, 2)
    ]

    aggregate = aggregate_s2f5_promotion_review(results)

    assert aggregate["status"] == "GO_NEXT"
    assert aggregate["best_for_s3"] == ["C2A_009_S2F2_VEL020"]
    assert aggregate["required_trial_count"] == 6
    assert aggregate["passed_trial_count"] == 6
    assert aggregate["failed_trials"] == []


def test_s2f5_aggregation_keeps_s3_closed_on_any_trial_failure():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import aggregate_s2f5_promotion_review

    results = [
        {
            "candidate_id": f"C2A_009_S2F2_VEL020_S2F5_P{particle_count:04d}_SEED{seed:03d}",
            "parent_candidate_id": "C2A_009_S2F2_VEL020",
            "classification": "PASS_SOURCE_HOLD",
            "particle_count": particle_count,
            "particle_seed": seed,
            "readback_available": True,
            "evidence_files_complete": True,
            "non_physical_parameter_dependence": False,
        }
        for particle_count in (256, 1024)
        for seed in (0, 1, 2)
    ]
    results[-1]["classification"] = "FAIL_CONTAINER_LEAK"

    aggregate = aggregate_s2f5_promotion_review(results)

    assert aggregate["status"] == "STOP_WITH_EVIDENCE"
    assert aggregate["best_for_s3"] == []
    assert aggregate["failed_trials"] == [results[-1]["candidate_id"]]


def test_write_s2f5_manifest_promotes_c3a_parent_after_all_trials_pass(tmp_path):
    from dataclasses import asdict

    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f3_sdf_sweep,
        build_s2f5_promotion_review_sweep,
        write_followup_manifest,
    )

    s2f3_candidate = build_s2f3_sdf_sweep(limit=1)[0]
    source_manifest = tmp_path / "s2f3_pass.json"
    source_manifest.write_text(
        json.dumps(
            {
                "stage": "S2F3_C3_SDF_SWEEP",
                "best_for_s2f5": ["C3A_001"],
                "candidate_plan": [asdict(s2f3_candidate)],
            }
        ),
        encoding="utf-8",
    )
    candidates = build_s2f5_promotion_review_sweep(s2f2_manifest_path=source_manifest)
    candidate_results = [
        {
            "candidate_id": candidate.candidate_id,
            "parent_candidate_id": candidate.parent_candidate_id,
            "phase": "S2F5_PROMOTION_REVIEW",
            "variable_group": "promotion_review",
            "classification": "PASS_SOURCE_HOLD",
            "source_retention_fraction": 1.0,
            "particle_count_final_fraction": 1.0,
            "outside_source_count": 0,
            "target_count": 0,
            "spill_count": 0,
            "below_table_count": 0,
            "tail_leak_rate_fraction_per_second": 0.0,
            "cpu_collision_fallback_detected": False,
            "gpu_collider_unsupported": False,
            "nan_count": 0,
            "non_physical_parameter_dependence": False,
            "particle_count": candidate.particle_count,
            "particle_seed": candidate.particle_seed,
            "readback_available": True,
            "evidence_files_complete": True,
        }
        for candidate in candidates
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F5_PROMOTION_REVIEW",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F5_PROMOTION_REVIEW",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
        source_s2f1_manifest=source_manifest,
    )

    assert manifest["status"] == "GO_NEXT"
    assert manifest["best_for_s3"] == ["C3A_001"]
    assert manifest["s3_kinematic_pour_released"] is True
    assert manifest["s2f5_promotion_review"]["promotion_candidate_id"] == "C3A_001"


def test_write_s2f5_manifest_promotes_after_all_trials_pass(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        aggregate_s2f5_promotion_review,
        build_s2f5_promotion_review_sweep,
        write_followup_manifest,
    )

    candidate_results = [
        {
            "candidate_id": candidate.candidate_id,
            "parent_candidate_id": candidate.parent_candidate_id,
            "phase": "S2F5_PROMOTION_REVIEW",
            "variable_group": "promotion_review",
            "classification": "PASS_SOURCE_HOLD",
            "source_retention_fraction": 1.0,
            "particle_count_final_fraction": 1.0,
            "outside_source_count": 0,
            "target_count": 0,
            "spill_count": 0,
            "below_table_count": 0,
            "tail_leak_rate_fraction_per_second": 0.0,
            "cpu_collision_fallback_detected": False,
            "gpu_collider_unsupported": False,
            "nan_count": 0,
            "non_physical_parameter_dependence": False,
            "particle_count": candidate.particle_count,
            "particle_seed": candidate.particle_seed,
            "readback_available": True,
            "evidence_files_complete": True,
            "initial_particle_positions_hash": f"hash-{candidate.particle_count}-{candidate.particle_seed}",
            "final_particle_positions_hash": f"final-{candidate.particle_count}-{candidate.particle_seed}",
        }
        for candidate in build_s2f5_promotion_review_sweep()
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F5_PROMOTION_REVIEW",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=build_s2f5_promotion_review_sweep(),
        candidate_results=candidate_results,
        command="runner --phase S2F5_PROMOTION_REVIEW",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
        source_s2f1_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f2_velocity_contact_offset_20260708.json"
        ),
    )

    assert aggregate_s2f5_promotion_review(candidate_results)["status"] == "GO_NEXT"
    assert manifest["stage"] == "S2F5_PROMOTION_REVIEW"
    assert manifest["status"] == "GO_NEXT"
    assert manifest["best_for_s3"] == ["C2A_009_S2F2_VEL020"]
    assert manifest["s2f5_promotion_review_complete"] is True
    assert manifest["s3_kinematic_pour_released"] is True
    assert manifest["phase_specs"]["S2F5_PROMOTION_REVIEW"]["status"] == "COMPLETE_GO_NEXT"


def test_write_s2f5_manifest_blocks_on_single_trial_failure(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f5_promotion_review_sweep,
        write_followup_manifest,
    )

    candidates = build_s2f5_promotion_review_sweep()
    candidate_results = [
        {
            "candidate_id": candidate.candidate_id,
            "parent_candidate_id": candidate.parent_candidate_id,
            "phase": "S2F5_PROMOTION_REVIEW",
            "variable_group": "promotion_review",
            "classification": "PASS_SOURCE_HOLD",
            "source_retention_fraction": 1.0,
            "particle_count_final_fraction": 1.0,
            "outside_source_count": 0,
            "target_count": 0,
            "spill_count": 0,
            "below_table_count": 0,
            "tail_leak_rate_fraction_per_second": 0.0,
            "cpu_collision_fallback_detected": False,
            "gpu_collider_unsupported": False,
            "nan_count": 0,
            "non_physical_parameter_dependence": False,
            "particle_count": candidate.particle_count,
            "particle_seed": candidate.particle_seed,
            "readback_available": True,
            "evidence_files_complete": True,
        }
        for candidate in candidates
    ]
    candidate_results[-1]["classification"] = "FAIL_CONTAINER_LEAK"

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F5_PROMOTION_REVIEW",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=candidates,
        candidate_results=candidate_results,
        command="runner --phase S2F5_PROMOTION_REVIEW",
        runtime_warning_scan={"blocking_runtime_warning_detected": False},
        source_s2f1_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f2_velocity_contact_offset_20260708.json"
        ),
    )

    assert manifest["stage"] == "S2F5_PROMOTION_REVIEW"
    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["best_for_s3"] == []
    assert manifest["s2f5_promotion_review_complete"] is False
    assert manifest["s3_kinematic_pour_released"] is False
    assert manifest["s2f5_promotion_review"]["failed_trials"] == [candidate_results[-1]["candidate_id"]]
    assert manifest["next_stage"]["id"] == "S2F3_C3_SDF_SWEEP"
    assert manifest["next_stage"]["diagnostic_routes"] == [
        "S2F3_C3_SDF_SWEEP",
        "S2F4_C4_NATIVE_MESH_ISOLATION",
    ]
    assert manifest["next_stage"]["not_s3_release"] is True


def test_s2f5_plan_only_cli_writes_six_trial_manifest(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import main

    manifest_path = tmp_path / "s2f5.json"
    artifact_dir = tmp_path / "artifacts"
    scene_dir = tmp_path / "scenes"

    exit_code = main(
        [
            "--phase",
            "S2F5_PROMOTION_REVIEW",
            "--manifest-path",
            str(manifest_path),
            "--artifact-dir",
            str(artifact_dir),
            "--scene-dir",
            str(scene_dir),
            "--plan-only",
        ]
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert manifest["stage"] == "S2F5_PROMOTION_REVIEW"
    assert manifest["status"] == "PLAN_READY"
    assert manifest["candidate_count"] == 6
    assert {candidate["parent_candidate_id"] for candidate in manifest["candidate_plan"]} == {
        "C2A_009_S2F2_VEL020"
    }


def test_s2f5_cli_rejects_candidate_limit(tmp_path):
    import pytest

    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import main

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--phase",
                "S2F5_PROMOTION_REVIEW",
                "--manifest-path",
                str(tmp_path / "s2f5.json"),
                "--artifact-dir",
                str(tmp_path / "artifacts"),
                "--scene-dir",
                str(tmp_path / "scenes"),
                "--candidate-limit",
                "1",
                "--plan-only",
            ]
        )

    assert "does not support --candidate-limit" in str(exc_info.value)


def test_write_followup_manifest_preserves_runtime_command_when_summarizing(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_c2_proxy_sweep,
        write_followup_manifest,
    )

    runtime_command = "python runner.py --phase S2F1_C2_PROXY_SWEEP --headless"
    summary_command = "python runner.py --phase S2F1_C2_PROXY_SWEEP --headless --summarize-existing"

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F1_C2_PROXY_SWEEP",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=build_c2_proxy_sweep(limit=1),
        candidate_results=[],
        command=summary_command,
        runtime_warning_scan=None,
        previous_manifest={"commands": [runtime_command]},
    )

    assert manifest["commands"] == [runtime_command, summary_command]
    assert manifest["runtime_commands"] == [runtime_command]
    assert manifest["summary_commands"] == [summary_command]


def test_runtime_warning_scan_blocks_promotion_even_if_candidate_passes(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_c2_proxy_sweep,
        classify_followup_candidate,
        write_followup_manifest,
    )

    candidate_results = [
        classify_followup_candidate(
            candidate_id="C2A_005",
            source_retention_fraction=1.0,
            particle_count_final_fraction=1.0,
            outside_source_count=0,
            target_count=0,
            spill_count=0,
            below_table_count=0,
            tail_leak_rate_fraction_per_second=0.0,
            cpu_collision_fallback_detected=False,
            gpu_collider_unsupported=False,
            nan_count=0,
            non_physical_parameter_dependence=False,
        )
    ]

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F1_C2_PROXY_SWEEP",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=build_c2_proxy_sweep(limit=1),
        candidate_results=candidate_results,
        command="runner --phase S2F1_C2_PROXY_SWEEP",
        runtime_warning_scan={"blocking_runtime_warning_detected": True},
    )

    assert candidate_results[0]["classification"] == "PASS_SOURCE_HOLD"
    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["reason"] == "blocking_runtime_warning_detected"
    assert manifest["best_for_s3"] == []
    assert manifest["runtime_warning_gate"]["passed"] is False
    assert manifest["next_stage"]["id"] == "S2F2_VELOCITY_CONTACT_OFFSET"


def test_runtime_warning_scan_blocks_even_without_candidate_results(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_c2_proxy_sweep,
        write_followup_manifest,
    )

    manifest = write_followup_manifest(
        tmp_path / "manifest.json",
        phase="S2F1_C2_PROXY_SWEEP",
        parent_manifest=Path("docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2_collider_matrix_20260707.json"),
        baseline_freeze_manifest=Path(
            "docs/labutopia_lab_poc/evidence_manifests/fluid_spike_s2f0_baseline_freeze_20260707.json"
        ),
        artifact_dir=tmp_path / "artifacts",
        candidates=build_c2_proxy_sweep(limit=1),
        candidate_results=[],
        command="runner --phase S2F1_C2_PROXY_SWEEP",
        runtime_warning_scan={"blocking_runtime_warning_detected": True},
    )

    assert manifest["status"] == "STOP_WITH_EVIDENCE"
    assert manifest["reason"] == "blocking_runtime_warning_detected"
    assert manifest["best_for_s3"] == []
    assert manifest["runtime_warning_gate"]["passed"] is False


def test_scan_runtime_warnings_detects_blocking_patterns(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import scan_runtime_warnings

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "server.stdout.txt").write_text(
        "\n".join(
            [
                "[Warning] [carb.windowing-glfw.plugin] GLFW initialization failed.",
                "[Error] [omni.physx.plugin] PhysX error: GPU collider unsupported",
                "[Warning] CPU collision fallback detected for particle collider",
            ]
        ),
        encoding="utf-8",
    )
    (artifact_dir / "server.stderr.txt").write_text("", encoding="utf-8")

    scan = scan_runtime_warnings(artifact_dir)

    assert scan["blocking_runtime_warning_detected"] is True
    assert scan["pattern_counts"]["headless_window_warning"] == 1
    assert scan["pattern_counts"]["physx_error"] == 1
    assert scan["pattern_counts"]["gpu_unsupported"] == 1
    assert scan["pattern_counts"]["cpu_fallback"] == 1


def test_scan_runtime_warnings_does_not_count_extension_startup_as_sdf_warning(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import scan_runtime_warnings

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "server.stdout.txt").write_text(
        "[17.202s] [ext: omni.physx.cooking-106.0.20] startup\n",
        encoding="utf-8",
    )
    (artifact_dir / "server.stderr.txt").write_text("", encoding="utf-8")

    scan = scan_runtime_warnings(artifact_dir)

    assert scan["blocking_runtime_warning_detected"] is False
    assert scan["pattern_counts"]["sdf_warning"] == 0


def test_scan_runtime_warnings_blocks_sdf_cooking_warning(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import scan_runtime_warnings

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "server.stdout.txt").write_text(
        "[Warning] SDF cooking warning: narrow band invalid for mesh\n",
        encoding="utf-8",
    )
    (artifact_dir / "server.stderr.txt").write_text("", encoding="utf-8")

    scan = scan_runtime_warnings(artifact_dir)

    assert scan["pattern_counts"]["sdf_warning"] == 1
    assert scan["blocking_runtime_warning_detected"] is True


def test_load_candidate_results_from_artifacts_rebuilds_manifest_inputs(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import load_candidate_results_from_artifacts

    variant_dir = tmp_path / "C2A_001"
    variant_dir.mkdir()
    (variant_dir / "variant_summary.json").write_text(
        """
{
  "artifact_dir": "artifacts/C2A_001",
  "classification_detail": {
    "below_table_count": 0,
    "cpu_collision_fallback_detected": false,
    "gpu_collider_unsupported": false,
    "nan_count": 0,
    "outside_source_count": 0,
    "particle_count_final_fraction": 1.0,
    "source_retention_fraction": 1.0,
    "spill_count": 0,
    "tail_leak_rate_fraction_per_second": 0.0,
    "target_count": 0
  },
  "final_region_counts": {"source_count": 256, "spill_count": 0},
  "initial_particle_positions_hash": "abc123",
  "initial_region_counts": {"source_count": 256, "spill_count": 0},
  "spawn_position_pinned": true,
  "scene_path": "scenes/c2a_001.usda",
  "variant": {"variant_id": "C2A_001"}
}
""",
        encoding="utf-8",
    )

    results = load_candidate_results_from_artifacts(tmp_path)

    assert len(results) == 1
    assert results[0]["candidate_id"] == "C2A_001"
    assert results[0]["classification"] == "PASS_SOURCE_HOLD"
    assert results[0]["initial_particle_positions_hash"] == "abc123"
    assert results[0]["spawn_position_pinned"] is True
    assert results[0]["initial_region_counts"] == {"source_count": 256, "spill_count": 0}
    assert results[0]["variant_summary"].endswith("C2A_001/variant_summary.json")


def test_load_candidate_results_requires_complete_expected_evidence_set(tmp_path, monkeypatch):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import load_candidate_results_from_artifacts

    monkeypatch.chdir(tmp_path)
    artifact_root = tmp_path / "artifacts"
    variant_dir = artifact_root / "C2A_001"
    variant_dir.mkdir(parents=True)
    existing_file = variant_dir / "initial_frame.png"
    existing_file.write_bytes(b"png")
    (variant_dir / "variant_summary.json").write_text(
        """
{
  "artifact_dir": "artifacts/C2A_001",
  "classification_detail": {
    "below_table_count": 0,
    "cpu_collision_fallback_detected": false,
    "gpu_collider_unsupported": false,
    "nan_count": 0,
    "outside_source_count": 0,
    "particle_count_final_fraction": 1.0,
    "source_retention_fraction": 1.0,
    "spill_count": 0,
    "tail_leak_rate_fraction_per_second": 0.0,
    "target_count": 0
  },
  "evidence_files": {
    "initial_frame": "artifacts/C2A_001/initial_frame.png"
  },
  "readback_available": true,
  "scene_path": "scenes/c2a_001.usda",
  "variant": {"variant_id": "C2A_001"}
}
""",
        encoding="utf-8",
    )

    results = load_candidate_results_from_artifacts(artifact_root)

    assert results[0]["readback_available"] is True
    assert results[0]["evidence_files_complete"] is False


def test_load_candidate_results_from_artifacts_rejects_unplanned_summaries(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_velocity_contact_offset_sweep,
        load_candidate_results_from_artifacts,
    )

    variant_dir = tmp_path / "C2A_999_STALE"
    variant_dir.mkdir()
    (variant_dir / "variant_summary.json").write_text(
        """
{
  "artifact_dir": "artifacts/C2A_999_STALE",
  "classification_detail": {
    "below_table_count": 0,
    "cpu_collision_fallback_detected": false,
    "gpu_collider_unsupported": false,
    "nan_count": 0,
    "outside_source_count": 0,
    "particle_count_final_fraction": 1.0,
    "source_retention_fraction": 1.0,
    "spill_count": 0,
    "tail_leak_rate_fraction_per_second": 0.0,
    "target_count": 0
  },
  "final_region_counts": {"source_count": 256, "spill_count": 0},
  "initial_particle_positions_hash": "stale",
  "initial_region_counts": {"source_count": 256, "spill_count": 0},
  "spawn_position_pinned": true,
  "scene_path": "scenes/stale.usda",
  "variant": {"variant_id": "C2A_999_STALE"}
}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unplanned_variant_summaries"):
        load_candidate_results_from_artifacts(tmp_path, candidates=build_velocity_contact_offset_sweep(limit=1))


def test_load_candidate_results_from_artifacts_accepts_c3a_sdf_summaries(tmp_path):
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        build_s2f3_sdf_sweep,
        load_candidate_results_from_artifacts,
    )

    artifact_root = tmp_path / "artifacts"
    variant_dir = artifact_root / "C3A_001"
    variant_dir.mkdir(parents=True)
    evidence_files = {
        "particle_readback_trace": variant_dir / "particle_readback_trace.jsonl",
        "physics_scene_settings": variant_dir / "physics_scene_settings.json",
        "initial_frame": variant_dir / "initial_frame.png",
        "mid_frame": variant_dir / "mid_frame.png",
        "terminal_frame": variant_dir / "terminal_frame.png",
        "top_collision_overlay": variant_dir / "top_collision_overlay.png",
        "side_collision_overlay": variant_dir / "side_collision_overlay.png",
    }
    for path in evidence_files.values():
        path.write_bytes(b"evidence")
    (variant_dir / "variant_summary.json").write_text(
        json.dumps(
            {
                "artifact_dir": str(variant_dir),
                "classification_detail": {
                    "below_table_count": 0,
                    "cpu_collision_fallback_detected": False,
                    "gpu_collider_unsupported": False,
                    "nan_count": 0,
                    "outside_source_count": 0,
                    "particle_count_final_fraction": 1.0,
                    "source_retention_fraction": 1.0,
                    "spill_count": 0,
                    "tail_leak_rate_fraction_per_second": 0.0,
                    "target_count": 0,
                },
                "evidence_files": {key: str(path) for key, path in evidence_files.items()},
                "readback_available": True,
                "scene_path": "scenes/c3a_001.usda",
                "variant": {"variant_id": "C3A_001"},
            }
        ),
        encoding="utf-8",
    )

    results = load_candidate_results_from_artifacts(artifact_root, candidates=build_s2f3_sdf_sweep(limit=1))

    assert len(results) == 1
    assert results[0]["candidate_id"] == "C3A_001"
    assert results[0]["phase"] == "S2F3_C3_SDF_SWEEP"
    assert results[0]["classification"] == "PASS_SOURCE_HOLD"
    assert results[0]["evidence_files_complete"] is True


def test_d4_wrapper_sweep_covers_spec_geometry_ranges_with_pinned_init():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import build_d4_wrapper_sweep
    from tools.labutopia_fluid.run_beaker_collider_smoke import (
        FLUID_SAFE_WRAPPER_FRAME,
        PROMOTION_INITIAL_RADIAL_VELOCITY,
        PROMOTION_PARTICLE_MAX_VELOCITY,
    )

    candidates = build_d4_wrapper_sweep()

    assert len(candidates) >= 9
    assert [c.candidate_id for c in candidates] == [f"D4A_{i:03d}" for i in range(1, len(candidates) + 1)]
    assert {c.phase for c in candidates} == {"D4_WRAPPER_SWEEP"}
    assert {c.panel_count for c in candidates} == {48, 64, 72}
    assert {c.wall_thickness for c in candidates} == {0.014, 0.018, 0.022}
    assert {c.bottom_overlap for c in candidates} == {0.003, 0.005, 0.008}
    assert {c.panel_arc_overlap_factor for c in candidates} == {1.08, 1.14, 1.20}
    assert all(c.initial_radial_velocity == PROMOTION_INITIAL_RADIAL_VELOCITY for c in candidates)
    assert all(c.particle_max_velocity == PROMOTION_PARTICLE_MAX_VELOCITY for c in candidates)
    assert all(c.wrapper_frame == FLUID_SAFE_WRAPPER_FRAME for c in candidates)
    assert all(c.native_mesh_collision_enabled is False for c in candidates)
    assert all(c.interior_inset >= c.particle_contact_offset for c in candidates)
    assert any(
        c.panel_count == 48 and c.wall_thickness == 0.018 and c.bottom_overlap == 0.003
        for c in candidates
    )

    start = next(
        c
        for c in candidates
        if c.panel_count == 48 and c.wall_thickness == 0.018 and c.bottom_overlap == 0.003
    )
    config = start.to_config()
    spec = start.to_variant_spec()
    assert config.initial_radial_velocity == 0.08
    assert config.particle_max_velocity == 5.0
    assert config.wall_thickness == 0.018
    assert config.bottom_overlap == 0.003
    assert isinstance(spec, VariantSpec)
    assert spec.setup == "fluid_safe_wrapper"
    assert spec.panel_count == 48
    assert spec.collision_approximation == "convex_panel_boxes"
    assert spec.native_mesh_collision_enabled is False
    assert spec.wrapper_frame == FLUID_SAFE_WRAPPER_FRAME
    assert spec.panel_arc_overlap_factor == start.panel_arc_overlap_factor
    assert spec.interior_inset == start.interior_inset


def test_evaluate_d4_init_pin_dependence_flags_velocity_crutches():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import evaluate_d4_init_pin_dependence

    assert (
        evaluate_d4_init_pin_dependence(
            initial_radial_velocity=0.02,
            particle_max_velocity=5.0,
        )
        is True
    )
    assert (
        evaluate_d4_init_pin_dependence(
            initial_radial_velocity=0.08,
            particle_max_velocity=0.10,
        )
        is True
    )
    assert (
        evaluate_d4_init_pin_dependence(
            initial_radial_velocity=0.08,
            particle_max_velocity=5.0,
        )
        is False
    )


def test_classify_d4_wrapper_trial_composes_hold_and_non_physical_gate():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import classify_d4_wrapper_trial

    pass_result = classify_d4_wrapper_trial(
        variant_id="D4A_001",
        config=ColliderConfig(initial_radial_velocity=0.08, particle_max_velocity=5.0),
        initial_count=512,
        final_count=512,
        source_count=512,
        target_count=0,
        spill_count=0,
        below_table_count=0,
        nan_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        fatal_error=None,
        particle_motion_observed=True,
        readback_position_changed=True,
        blocking_runtime_warning_detected=False,
    )
    assert pass_result["classification"] == "PASS_SOURCE_HOLD"
    assert pass_result["contract"] == "s2_no_outside_source_v2+d4_followup"
    assert pass_result["non_physical_parameter_dependence"] is False

    crutch = classify_d4_wrapper_trial(
        variant_id="D4A_BAD_VEL",
        config=ColliderConfig(initial_radial_velocity=0.02, particle_max_velocity=5.0),
        initial_count=512,
        final_count=512,
        source_count=512,
        target_count=0,
        spill_count=0,
        below_table_count=0,
        nan_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        fatal_error=None,
        particle_motion_observed=True,
        readback_position_changed=True,
        blocking_runtime_warning_detected=False,
    )
    assert crutch["classification"] == "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE"
    assert crutch["non_physical_parameter_dependence"] is True

    gpu_fail = classify_d4_wrapper_trial(
        variant_id="D4A_GPU",
        config=ColliderConfig(),
        initial_count=512,
        final_count=512,
        source_count=512,
        target_count=0,
        spill_count=0,
        below_table_count=0,
        nan_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=True,
        fatal_error=None,
        particle_motion_observed=True,
        readback_position_changed=True,
        blocking_runtime_warning_detected=False,
    )
    assert gpu_fail["classification"] == "FAIL_GPU_COLLIDER_UNSUPPORTED"

    leak = classify_d4_wrapper_trial(
        variant_id="D4A_LEAK",
        config=ColliderConfig(),
        initial_count=512,
        final_count=512,
        source_count=500,
        target_count=0,
        spill_count=12,
        below_table_count=0,
        nan_count=0,
        tail_leak_rate_fraction_per_second=0.0,
        cpu_collision_fallback_detected=False,
        gpu_collider_unsupported=False,
        fatal_error=None,
        particle_motion_observed=True,
        readback_position_changed=True,
        blocking_runtime_warning_detected=False,
    )
    assert leak["classification"] == "FAIL_CONTAINER_LEAK"


def test_aggregate_d4_wrapper_sweep_incomplete_and_crutch_stop_taxonomy():
    from tools.labutopia_fluid.run_beaker_collider_followup_sweep import (
        D4_MATRIX_STOP_CLASSIFICATIONS,
        aggregate_d4_wrapper_sweep,
        build_d4_wrapper_sweep,
    )

    expected_ids = [c.candidate_id for c in build_d4_wrapper_sweep()]
    assert "STOP_WITH_EVIDENCE" in D4_MATRIX_STOP_CLASSIFICATIONS
    assert "STOP_NON_PHYSICAL_PARAMETER_DEPENDENCE" in D4_MATRIX_STOP_CLASSIFICATIONS
    assert "STOP_WRAPPER_NOT_FLUID_SAFE" in D4_MATRIX_STOP_CLASSIFICATIONS

    incomplete = [
        {
            "candidate_id": "D4A_001",
            "classification": "PASS_SOURCE_HOLD",
            "evidence_files_complete": True,
            "non_physical_parameter_dependence": False,
            "wrapper_frame": "local_to_beaker2",
        }
    ]
    agg_incomplete = aggregate_d4_wrapper_sweep(incomplete, expected_candidate_ids=expected_ids)
    assert agg_incomplete["status"] == "STOP_WITH_EVIDENCE"
    assert agg_incomplete["best_for_promotion"] == []
    assert agg_incomplete["missing_candidate_ids"]

    crutch_only = [
        {
            "candidate_id": candidate_id,
            "classification": "FAIL_NON_PHYSICAL_PARAMETER_DEPENDENCE",
            "evidence_files_complete": True,
            "non_physical_parameter_dependence": True,
            "wrapper_frame": "local_to_beaker2",
        }
        for candidate_id in expected_ids
    ]
    agg_crutch = aggregate_d4_wrapper_sweep(crutch_only, expected_candidate_ids=expected_ids)
    assert agg_crutch["status"] == "STOP_NON_PHYSICAL_PARAMETER_DEPENDENCE"
    assert agg_crutch["best_for_promotion"] == []

    leaking = [
        {
            "candidate_id": candidate_id,
            "classification": "FAIL_CONTAINER_LEAK",
            "evidence_files_complete": True,
            "non_physical_parameter_dependence": False,
            "wrapper_frame": "local_to_beaker2",
        }
        for candidate_id in expected_ids
    ]
    agg_leak = aggregate_d4_wrapper_sweep(leaking, expected_candidate_ids=expected_ids)
    assert agg_leak["status"] in {"STOP_WRAPPER_NOT_FLUID_SAFE", "STOP_STATIC_HOLD_LEAK"}
    assert agg_leak["best_for_promotion"] == []
