import json
import subprocess
from copy import deepcopy
from pathlib import Path

from tools.labutopia_fluid.run_colleague_native_collider_approx_sweep import (
    DEFAULT_NATIVE_STEP_RUNNER,
    DEFAULT_NATIVE_MESH_PATH,
    NEVER_PROMOTABLE_VARIANT_IDS,
    apply_native_collider_approximation,
    build_claim_boundary,
    build_native_approximation_sweep,
    build_native_variant_runtime_command,
    classify_native_approximation_summary,
    run_native_variant_runtime_sweep,
    write_runtime_aggregate_manifest,
    summarize_native_mesh_collision_state,
    write_dry_run_authoring_artifacts,
)


def test_native_sweep_declares_builtin_modes_and_excludes_proxy_route():
    candidates = build_native_approximation_sweep()
    ids = [candidate.variant_id for candidate in candidates]

    assert ids == [
        "RAW_AS_IS",
        "NATIVE_NONE",
        "NATIVE_MESH_SIMPLIFICATION",
        "NATIVE_CONVEX_HULL",
        "NATIVE_CONVEX_DECOMPOSITION",
        "NATIVE_SDF_64",
        "NATIVE_SDF_128",
        "NATIVE_SDF_256",
        "NATIVE_BOUNDING_CUBE",
        "NATIVE_BOUNDING_SPHERE",
    ]
    assert all(candidate.route != "native_render_mesh_plus_proxy_collision" for candidate in candidates)
    assert NEVER_PROMOTABLE_VARIANT_IDS == {"NATIVE_NONE", "NATIVE_BOUNDING_CUBE", "NATIVE_BOUNDING_SPHERE"}


def test_claim_boundary_separates_allowed_and_blocked_claims():
    boundary = build_claim_boundary()

    assert "built-in/native Isaac/PhysX mesh collision approximation modes" in boundary["allowed_claims"][0]
    assert any("Render/video appearance alone" in claim for claim in boundary["blocked_claims"])
    assert boundary["s3_kinematic_pour_released"] is False
    assert boundary["benchmark_ready_claim_allowed"] is False


def _passing_runtime_summary():
    return {
        "runtime_step_executed": True,
        "readback_diagnostics": {"readback_available": True, "readback_position_changed": True},
        "classification": {
            "classification": "PASS_SOURCE_HOLD",
            "particle_count_final_fraction": 1.0,
            "source_retention_fraction": 1.0,
            "outside_source_count": 0,
            "target_count": 0,
            "spill_count": 0,
            "below_table_count": 0,
            "tail_leak_rate_fraction_per_second": 0.0,
            "cpu_collision_fallback_detected": False,
            "gpu_collider_unsupported": False,
            "nan_count": 0,
            "fatal_error": None,
        },
    }


def test_static_hold_classifier_requires_zero_leak_and_promotable_candidate():
    result = classify_native_approximation_summary(_passing_runtime_summary(), variant_id="NATIVE_SDF_128")

    assert result["native_approximation_static_hold_passed"] is True
    assert result["promotable_to_repeat_review"] is True


def test_static_hold_classifier_never_promotes_negative_controls():
    result = classify_native_approximation_summary(_passing_runtime_summary(), variant_id="NATIVE_BOUNDING_CUBE")

    assert result["native_approximation_static_hold_passed"] is True
    assert result["promotable_to_repeat_review"] is False
    assert result["promotion_block_reason"] == "diagnostic_or_negative_control"


def test_static_hold_classifier_requires_explicit_false_fallback_diagnostics():
    missing_cpu = deepcopy(_passing_runtime_summary())
    del missing_cpu["classification"]["cpu_collision_fallback_detected"]
    missing_gpu = deepcopy(_passing_runtime_summary())
    del missing_gpu["classification"]["gpu_collider_unsupported"]

    cpu_result = classify_native_approximation_summary(missing_cpu, variant_id="NATIVE_SDF_128")
    gpu_result = classify_native_approximation_summary(missing_gpu, variant_id="NATIVE_SDF_128")

    assert cpu_result["native_approximation_static_hold_passed"] is False
    assert cpu_result["gate_checks"]["cpu_collision_fallback_detected"] is False
    assert gpu_result["native_approximation_static_hold_passed"] is False
    assert gpu_result["gate_checks"]["gpu_collider_unsupported"] is False


def test_apply_native_collider_approximation_authors_mesh_collision_api():
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    mesh = UsdGeom.Mesh.Define(stage, DEFAULT_NATIVE_MESH_PATH)

    candidate = next(c for c in build_native_approximation_sweep() if c.variant_id == "NATIVE_CONVEX_HULL")
    result = apply_native_collider_approximation(stage, candidate)

    assert result["mesh_path"] == DEFAULT_NATIVE_MESH_PATH
    assert result["authored_collision_enabled"] is True
    assert UsdPhysics.MeshCollisionAPI(mesh.GetPrim()).GetApproximationAttr().Get() == "convexHull"


def test_apply_native_sdf_authors_sdf_settings_when_schema_available():
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    mesh = UsdGeom.Mesh.Define(stage, DEFAULT_NATIVE_MESH_PATH)

    candidate = next(c for c in build_native_approximation_sweep() if c.variant_id == "NATIVE_SDF_128")
    result = apply_native_collider_approximation(stage, candidate)

    assert result["approximation"] == "sdf"
    assert result["sdf_resolution"] == 128
    assert UsdPhysics.MeshCollisionAPI(mesh.GetPrim()).GetApproximationAttr().Get() == "sdf"


def test_raw_as_is_authoring_reports_actual_collision_without_new_sweep_authors():
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    mesh = UsdGeom.Mesh.Define(stage, DEFAULT_NATIVE_MESH_PATH)
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim()).CreateCollisionEnabledAttr().Set(True)

    candidate = next(c for c in build_native_approximation_sweep() if c.variant_id == "RAW_AS_IS")
    result = apply_native_collider_approximation(stage, candidate)

    assert result["authored_collision_enabled"] is True
    assert result["sweep_authored_collision_enabled"] is False


def test_summarize_native_mesh_collision_state_handles_missing_mesh():
    from pxr import Usd

    stage = Usd.Stage.CreateInMemory()

    summary = summarize_native_mesh_collision_state(stage, "/World/missing")

    assert summary["mesh_path"] == "/World/missing"
    assert summary["exists"] is False


def test_dry_run_authoring_writes_manifest_and_overlays(tmp_path):
    from pxr import Usd, UsdGeom

    source = tmp_path / "source.usda"
    stage = Usd.Stage.CreateNew(str(source))
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Mesh.Define(stage, DEFAULT_NATIVE_MESH_PATH)
    stage.GetRootLayer().Save()

    manifest = write_dry_run_authoring_artifacts(
        usd_path=source,
        out_dir=tmp_path / "artifacts",
        manifest_path=tmp_path / "manifest.json",
        variant_ids=["NATIVE_CONVEX_DECOMPOSITION", "NATIVE_SDF_64"],
    )

    assert manifest["manifest_type"] == "fluid_spike_native_collider_approximation_sweep"
    assert manifest["dry_run_authoring_only"] is True
    assert manifest["source_usd_path"] == str(source)
    assert [item["variant_id"] for item in manifest["candidate_results"]] == [
        "NATIVE_CONVEX_DECOMPOSITION",
        "NATIVE_SDF_64",
    ]
    assert all(item["overlay_usda"] for item in manifest["candidate_results"])


def test_dry_run_authoring_starts_each_variant_from_clean_source_layer(tmp_path):
    from pxr import Usd, UsdGeom, UsdPhysics

    source = tmp_path / "source.usda"
    stage = Usd.Stage.CreateNew(str(source))
    UsdGeom.Xform.Define(stage, "/World")
    mesh = UsdGeom.Mesh.Define(stage, DEFAULT_NATIVE_MESH_PATH)
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim()).CreateCollisionEnabledAttr().Set(True)
    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr().Set("convexDecomposition")
    stage.GetRootLayer().Save()

    manifest = write_dry_run_authoring_artifacts(
        usd_path=source,
        out_dir=tmp_path / "artifacts",
        manifest_path=tmp_path / "manifest.json",
        variant_ids=["NATIVE_NONE", "NATIVE_CONVEX_HULL"],
    )

    pre_states = [item["authoring"]["pre_state"]["approximation"] for item in manifest["candidate_results"]]
    assert pre_states == ["convexDecomposition", "convexDecomposition"]


def test_native_step_video_parser_accepts_collider_approximation_variant():
    from tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video import build_arg_parser

    args = build_arg_parser().parse_args(
        ["--native-collider-approximation-variant", "NATIVE_CONVEX_DECOMPOSITION"]
    )

    assert args.native_collider_approximation_variant == "NATIVE_CONVEX_DECOMPOSITION"


def test_runtime_aggregate_manifest_summarizes_variant_gate_results(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    passing = _passing_runtime_summary()
    passing["native_collider_approximation"] = {"candidate": {"variant_id": "NATIVE_SDF_128"}}
    passing["videos"] = {"beaker2_closeup_native_material": {"path": "sdf128.mp4", "written": True, "frame_count": 12}}
    failing = _passing_runtime_summary()
    failing["native_collider_approximation"] = {"candidate": {"variant_id": "NATIVE_CONVEX_HULL"}}
    failing["classification"]["classification"] = "FAIL_CONTAINER_LEAK"
    failing["classification"]["below_table_count"] = 4
    failing["classification"]["source_retention_fraction"] = 0.75
    failing["videos"] = {"beaker2_closeup_native_material": {"path": "hull.mp4", "written": True, "frame_count": 12}}
    (runtime_dir / "NATIVE_SDF_128_runtime_512.json").write_text(json.dumps(passing), encoding="utf-8")
    (runtime_dir / "NATIVE_CONVEX_HULL_runtime_512.json").write_text(json.dumps(failing), encoding="utf-8")

    manifest = write_runtime_aggregate_manifest(
        runtime_dir=runtime_dir,
        manifest_path=tmp_path / "aggregate.json",
        variant_ids=["NATIVE_SDF_128", "NATIVE_CONVEX_HULL"],
    )

    assert manifest["manifest_type"] == "fluid_spike_native_collider_approximation_runtime_sweep"
    assert manifest["runtime_step_executed_count"] == 2
    assert manifest["static_hold_pass_count"] == 1
    assert manifest["promotable_variant_ids"] == ["NATIVE_SDF_128"]
    assert manifest["candidate_results"][0]["variant_id"] == "NATIVE_SDF_128"
    assert manifest["candidate_results"][0]["gate"]["promotable_to_repeat_review"] is True
    assert manifest["candidate_results"][1]["classification"] == "FAIL_CONTAINER_LEAK"
    assert manifest["candidate_results"][1]["below_table_count"] == 4


def test_runtime_aggregate_does_not_claim_all_tested_when_runtime_did_not_step(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    failed_to_run = _passing_runtime_summary()
    failed_to_run["runtime_step_executed"] = False
    failed_to_run["native_collider_approximation"] = {"candidate": {"variant_id": "NATIVE_SDF_128"}}
    (runtime_dir / "NATIVE_SDF_128_runtime_512.json").write_text(json.dumps(failed_to_run), encoding="utf-8")

    manifest = write_runtime_aggregate_manifest(
        runtime_dir=runtime_dir,
        manifest_path=tmp_path / "aggregate.json",
        variant_ids=["NATIVE_SDF_128"],
    )

    assert manifest["runtime_step_executed_count"] == 0
    assert manifest["failed_to_execute_variant_ids"] == ["NATIVE_SDF_128"]
    assert manifest["all_tested_candidates_failed_static_hold"] is False


def test_runtime_aggregate_flags_variant_identity_mismatches(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    mismatched = _passing_runtime_summary()
    mismatched["native_collider_approximation"] = {"candidate": {"variant_id": "NATIVE_CONVEX_HULL"}}
    (runtime_dir / "NATIVE_SDF_128_runtime_512.json").write_text(json.dumps(mismatched), encoding="utf-8")

    manifest = write_runtime_aggregate_manifest(
        runtime_dir=runtime_dir,
        manifest_path=tmp_path / "aggregate.json",
        variant_ids=["NATIVE_SDF_128"],
    )

    result = manifest["candidate_results"][0]
    assert result["variant_identity_matches"] is False
    assert result["runtime_summary_variant_id"] == "NATIVE_CONVEX_HULL"
    assert manifest["mismatched_variant_ids"] == ["NATIVE_SDF_128"]
    assert manifest["promotable_variant_ids"] == []
    assert manifest["all_tested_candidates_failed_static_hold"] is False


def test_runtime_aggregate_manifest_reports_presentation_video_status(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    summary = _passing_runtime_summary()
    summary["native_collider_approximation"] = {"candidate": {"variant_id": "NATIVE_SDF_128"}}
    summary["videos"] = {
        "presentation_isosurface": {"path": "presentation_isosurface.mp4", "written": True, "frame_count": 120},
        "beaker2_closeup_native_material": {"path": "closeup.mp4", "written": True, "frame_count": 120},
    }
    summary["presentation_visual_contract"] = {
        "presentation_video_does_not_replace_particle_readback": True,
        "debug_particle_display_enabled": False,
    }
    (runtime_dir / "NATIVE_SDF_128_runtime_512.json").write_text(json.dumps(summary), encoding="utf-8")

    manifest = write_runtime_aggregate_manifest(
        runtime_dir=runtime_dir,
        manifest_path=tmp_path / "aggregate.json",
        variant_ids=["NATIVE_SDF_128"],
    )

    result = manifest["candidate_results"][0]
    assert result["presentation_video"]["written"] is True
    assert result["presentation_video"]["frame_count"] == 120
    assert result["presentation_visual_contract"]["debug_particle_display_enabled"] is False
    assert manifest["presentation_video_written_count"] == 1
    assert manifest["all_presentation_videos_written"] is True


def test_runtime_aggregate_defaults_presentation_fields_for_missing_result(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    manifest = write_runtime_aggregate_manifest(
        runtime_dir=runtime_dir,
        manifest_path=tmp_path / "aggregate.json",
        variant_ids=["RAW_AS_IS"],
    )

    result = manifest["candidate_results"][0]
    assert result["classification"] == "MISSING_RUNTIME_RESULT"
    assert result["presentation_video"] == {"path": None, "written": False, "frame_count": 0}
    assert result["presentation_visual_contract"] == {}
    assert manifest["presentation_video_written_count"] == 0
    assert manifest["all_presentation_videos_written"] is False


def test_build_native_variant_runtime_command_adds_presentation_video_flags(tmp_path):
    candidate = next(c for c in build_native_approximation_sweep() if c.variant_id == "NATIVE_SDF_128")

    cmd = build_native_variant_runtime_command(
        python_executable="/isaac/python",
        runner_path=DEFAULT_NATIVE_STEP_RUNNER,
        usd_path="scene.usd",
        runtime_dir=tmp_path / "runtime",
        candidate=candidate,
        runtime_suffix="_runtime_512.json",
        particle_limit=512,
        steps=120,
        trace_interval=10,
        presentation_isosurface_videos=True,
        headless=True,
        hard_exit_after_run=True,
    )

    assert cmd[0] == "/isaac/python"
    assert str(DEFAULT_NATIVE_STEP_RUNNER) in cmd
    assert cmd[cmd.index("--native-collider-approximation-variant") + 1] == "NATIVE_SDF_128"
    assert cmd[cmd.index("--out-dir") + 1].endswith("NATIVE_SDF_128_runtime_512")
    assert cmd[cmd.index("--manifest") + 1].endswith("NATIVE_SDF_128_runtime_512.json")
    assert "--presentation-isosurface-video" in cmd
    assert "--disable-particle-debug-display" in cmd
    assert "--headless" in cmd
    assert "--hard-exit-after-run" in cmd


def test_run_native_variant_runtime_sweep_invokes_each_candidate_and_aggregates(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, cwd, env, check):
        calls.append(cmd)
        variant_id = cmd[cmd.index("--native-collider-approximation-variant") + 1]
        manifest_path = Path(cmd[cmd.index("--manifest") + 1])
        summary = _passing_runtime_summary()
        summary["native_collider_approximation"] = {"candidate": {"variant_id": variant_id}}
        summary["videos"] = {
            "presentation_isosurface": {
                "path": str(manifest_path.with_suffix("").parent / "presentation_isosurface.mp4"),
                "written": True,
                "frame_count": 31,
            }
        }
        summary["presentation_visual_contract"] = {
            "presentation_video_does_not_replace_particle_readback": True,
            "debug_particle_display_enabled": False,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(summary), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    manifest = run_native_variant_runtime_sweep(
        usd_path="scene.usd",
        runtime_dir=tmp_path / "runtime",
        manifest_path=tmp_path / "aggregate.json",
        variant_ids=["RAW_AS_IS", "NATIVE_SDF_128"],
        python_executable="/isaac/python",
        runner_path=DEFAULT_NATIVE_STEP_RUNNER,
        particle_limit=512,
        steps=120,
        trace_interval=10,
        presentation_isosurface_videos=True,
        headless=True,
    )

    assert len(calls) == 2
    assert all("--presentation-isosurface-video" in cmd for cmd in calls)
    assert manifest["runtime_step_executed_count"] == 2
    assert manifest["presentation_video_written_count"] == 2
    assert manifest["runtime_launcher_success_count"] == 2
