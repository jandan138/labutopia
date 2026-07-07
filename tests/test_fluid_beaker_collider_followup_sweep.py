from pathlib import Path

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
    ]
    assert phases["S2F0_BASELINE_FREEZE"]["candidate_prefix"] == "S2"
    assert phases["S2F1_C2_PROXY_SWEEP"]["candidate_prefix"] == "C2A"
    assert phases["S2F3_C3_SDF_SWEEP"]["candidate_prefix"] == "C3A"
    assert phases["S2F4_C4_NATIVE_MESH_ISOLATION"]["candidate_prefix"] == "C4A"


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
    assert results[0]["variant_summary"].endswith("C2A_001/variant_summary.json")
