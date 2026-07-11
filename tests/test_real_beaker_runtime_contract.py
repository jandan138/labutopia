import json
import sys
import types

import pytest
from pxr import Usd, UsdGeom

from tools.labutopia_fluid import run_colleague_native_usd_completed_pbd_step_video as runner
from tools.labutopia_fluid import run_real_beaker_static_hold_matrix as matrix


def _strict_args(*extra: str):
    return runner.build_arg_parser().parse_args(
        ["--real-beaker-static-hold", "--controlled-spawn-count", "1024", *extra]
    )


def test_parser_exposes_real_beaker_static_hold_mode():
    args = runner.build_arg_parser().parse_args(["--real-beaker-static-hold"])

    assert args.real_beaker_static_hold is True


def test_parser_exposes_display_particle_width():
    args = runner.build_arg_parser().parse_args(["--display-particle-width", "0.0043"])

    assert args.display_particle_width == pytest.approx(0.0043)


def test_strict_hold_summary_requires_visible_classifier():
    summary = runner.build_real_beaker_summary_contract(
        visible_classification={
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "trace_schema_valid": True,
            "diagnostic_scan_complete": True,
            "physical_trace_identity": {"physical_trace_sha256": "a" * 64},
        },
        frame={"axis_alignment_dot": 1.0},
        physics_offsets={"particle_width": 0.00045},
        display_particle_width=0.0043,
    )

    assert summary["visible_beaker_containment_verified"] is True
    assert summary["physics_particle_offsets"]["particle_width"] == 0.00045
    assert summary["display_particle_width"] == 0.0043
    assert summary["physical_trace_identity"]["physical_trace_sha256"] == "a" * 64


def test_strict_hold_summary_rejects_incomplete_diagnostics():
    summary = runner.build_real_beaker_summary_contract(
        visible_classification={
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "trace_schema_valid": True,
            "diagnostic_scan_complete": False,
        },
        frame={"axis_alignment_dot": 1.0},
        physics_offsets={"particle_width": 0.00045},
        display_particle_width=0.0043,
    )

    assert summary["visible_beaker_containment_verified"] is False


def test_strict_hold_requires_controlled_spawn():
    args = runner.build_arg_parser().parse_args(["--real-beaker-static-hold"])

    with pytest.raises(ValueError, match="requires_controlled_spawn"):
        runner.validate_real_beaker_static_hold_args(args)


@pytest.mark.parametrize("cadence", [0, 31])
def test_strict_hold_rejects_invalid_trace_cadence(cadence):
    with pytest.raises(ValueError, match="trace_interval"):
        runner.validate_real_beaker_static_hold_args(_strict_args("--trace-interval", str(cadence)))


def test_strict_hold_rejects_particle_limit_path():
    with pytest.raises(ValueError, match="particle_limit"):
        runner.validate_real_beaker_static_hold_args(_strict_args("--particle-limit", "8"))


def test_strict_hold_rejects_legacy_wrapper_path():
    with pytest.raises(ValueError, match="fluid_safe_wrapper_overlay"):
        runner.validate_real_beaker_static_hold_args(_strict_args("--fluid-safe-wrapper-overlay"))


def test_strict_hold_rejects_native_approximation_path():
    with pytest.raises(ValueError, match="native_collider_approximation"):
        runner.validate_real_beaker_static_hold_args(
            _strict_args("--native-collider-approximation-variant", "NATIVE_BOUNDING_CUBE")
        )


def test_strict_hold_rejects_nonpositive_display_width():
    with pytest.raises(ValueError, match="display_particle_width"):
        runner.validate_real_beaker_static_hold_args(_strict_args("--display-particle-width", "0"))


@pytest.mark.parametrize("width", ["nan", "inf", "-inf"])
def test_strict_hold_rejects_nonfinite_display_width(width):
    with pytest.raises(ValueError, match="display_particle_width"):
        runner.validate_real_beaker_static_hold_args(
            _strict_args(f"--display-particle-width={width}")
        )


@pytest.mark.parametrize(
    "physics_offsets,display_width",
    [
        ({}, 0.0043),
        ({"particle_width": 0.00045}, None),
        ({"particle_width": 0.00045}, float("nan")),
        ({"particle_width": 0.00045}, float("inf")),
    ],
)
def test_strict_hold_summary_requires_evidence_for_physics_display_separation(
    physics_offsets, display_width
):
    summary = runner.build_real_beaker_summary_contract(
        visible_classification={
            "classification": "FAIL_VISIBLE_BEAKER_CONTAINMENT",
            "trace_schema_valid": True,
            "diagnostic_scan_complete": True,
        },
        frame={"axis_alignment_dot": 1.0},
        physics_offsets=physics_offsets,
        display_particle_width=display_width,
    )

    assert summary["physics_display_parameters_separated"] is False
    assert (
        summary["strict_hold_claim_boundary"][
            "display_particle_width_does_not_affect_physics_offsets"
        ]
        is False
    )


def test_strict_runtime_fatal_summary_is_explicit_and_authoritative():
    fatal_error = {"type": "RuntimeError", "message": "stage failed"}
    log_segment = {
        "log_path": "/tmp/kit.log",
        "byte_offset": 123,
        "cursor_captured": True,
        "diagnostic_scan_complete": True,
        "segment_byte_count": 17,
        "segment_sha256": "b" * 64,
        "log_text": "runtime failure\n",
    }

    summary = runner.build_real_beaker_runtime_fatal_summary(
        fatal_error=fatal_error,
        kit_log_segment=log_segment,
        display_particle_width=0.0043,
    )

    assert summary["classification"]["classification"] == "FAIL_RUNTIME_FATAL_ERROR"
    assert summary["strict_visible_classification"] == summary["classification"]
    assert summary["runtime_step_executed"] is False
    assert summary["cup_interior_frame"] is None
    assert summary["visible_beaker_spawn"] is None
    assert summary["canonical_wrapper"] is None
    assert summary["legacy_classification"] is None
    assert summary["physical_trace_identity"] is None
    assert summary["physics_particle_offsets"] is None
    assert summary["physics_display_parameters_separated"] is False
    assert summary["visible_beaker_containment_verified"] is False
    assert summary["strict_kit_log_segment"] == {
        key: value for key, value in log_segment.items() if key != "log_text"
    }


def test_strict_runtime_fatal_summary_uses_failure_only_claim_boundary():
    summary = runner.build_real_beaker_runtime_fatal_summary(
        fatal_error={"type": "RuntimeError", "message": "stage failed"},
        kit_log_segment={
            "log_path": None,
            "byte_offset": None,
            "cursor_captured": False,
            "diagnostic_scan_complete": False,
            "segment_byte_count": 0,
            "log_text": None,
        },
        display_particle_width=None,
    )

    assert summary["claim_boundary"]["allowed"] == [
        "runtime_fatal_error_recorded=true",
        "strict_visible_classification_recorded=true",
        "strict_kit_log_segment_provenance_recorded=true",
    ]
    assert set(summary["claim_boundary"]["blocked"]) >= {
        "runtime_video_recorded=true",
        "runtime_pbd_completion_overlay_used=true",
        "particles_stepped=true",
        "particle_readback_available=true",
        "leak_classification_passed=true",
        "visible_beaker_containment_verified=true",
        "physics_and_display_particle_widths_are_independent=true",
    }
    assert summary["strict_hold_claim_boundary"] == summary["claim_boundary"]


def test_kit_log_cursor_reads_only_bytes_appended_after_capture(tmp_path, monkeypatch):
    log_path = tmp_path / "kit.log"
    log_path.write_text("old fallback to cpu collision\n", encoding="utf-8")
    monkeypatch.setattr(
        "tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video._latest_isaac_log_path",
        lambda: log_path,
    )

    cursor = runner._capture_kit_log_cursor()
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write("current run clean\n")

    segment = runner._read_kit_log_segment(cursor)
    assert segment["diagnostic_scan_complete"] is True
    assert segment["log_text"] == "current run clean\n"
    assert segment["byte_offset"] == len("old fallback to cpu collision\n")


def test_missing_kit_log_segment_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video._latest_isaac_log_path",
        lambda: None,
    )

    segment = runner._read_kit_log_segment(runner._capture_kit_log_cursor())
    assert segment["diagnostic_scan_complete"] is False
    assert segment["log_text"] is None


@pytest.mark.parametrize("display_width,expected_width", [(0.0043, 0.0043), (None, 0.00045)])
def test_runtime_particle_authoring_separates_display_and_physics_widths(
    monkeypatch, display_width, expected_width
):
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Scope.Define(stage, "/World/Looks")
    captured = {}

    class ParticleUtils:
        @staticmethod
        def add_pbd_particle_material(**kwargs):
            captured["material"] = kwargs

        @staticmethod
        def add_physx_particle_system(**kwargs):
            captured["system"] = kwargs
            return UsdGeom.Xform.Define(stage, str(kwargs["particle_system_path"]))

        @staticmethod
        def add_physx_particle_isosurface(*args, **kwargs):
            return None

        @staticmethod
        def add_physx_particleset_points(*args):
            captured["point_widths"] = list(args[4])
            return UsdGeom.Points.Define(stage, str(args[1]))

    class PhysicsUtils:
        @staticmethod
        def add_physics_material_to_prim(*args):
            return None

    omni = types.ModuleType("omni")
    physx = types.ModuleType("omni.physx")
    scripts = types.ModuleType("omni.physx.scripts")
    scripts.particleUtils = ParticleUtils
    scripts.physicsUtils = PhysicsUtils
    monkeypatch.setitem(sys.modules, "omni", omni)
    monkeypatch.setitem(sys.modules, "omni.physx", physx)
    monkeypatch.setitem(sys.modules, "omni.physx.scripts", scripts)
    monkeypatch.setattr(
        "tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video._deactivate_original_fluid_prims",
        lambda _stage: {},
    )
    monkeypatch.setattr(
        "tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video._particle_isosurface_api_summary",
        lambda *_args: {},
    )
    monkeypatch.setattr(
        "tools.labutopia_fluid.run_colleague_native_usd_completed_pbd_step_video._particle_postprocess_api_summary",
        lambda *_args: {},
    )
    widths = {
        "particle_width": 0.00045,
        "particle_contact_offset": 0.0005,
        "particle_system_contact_offset": 0.00075,
        "solid_rest_offset": 0.0004455,
        "fluid_rest_offset": 0.000264627,
    }

    runner._author_completed_pbd_runtime_particles(
        stage=stage,
        positions=[(0.0, 0.0, 0.0), (0.0, 0.0, 0.001)],
        widths=widths,
        physics_scene_path="/World/PhysicsScene",
        visual_material_path="/World/Looks/Missing",
        display_particle_width=display_width,
    )

    assert captured["system"]["contact_offset"] == widths["particle_system_contact_offset"]
    assert captured["system"]["particle_contact_offset"] == widths["particle_contact_offset"]
    assert captured["system"]["solid_rest_offset"] == widths["solid_rest_offset"]
    assert captured["system"]["fluid_rest_offset"] == widths["fluid_rest_offset"]
    assert captured["point_widths"] == [expected_width, expected_width]


def test_static_hold_matrix_has_required_six_cells():
    cells = matrix.static_hold_cells(counts=(1024, 4096), seeds=(0, 1, 2))

    assert [(cell["particle_count"], cell["seed"]) for cell in cells] == [
        (1024, 0),
        (1024, 1),
        (1024, 2),
        (4096, 0),
        (4096, 1),
        (4096, 2),
    ]


def test_matrix_command_pins_strict_runtime_and_capture_contract(tmp_path):
    argv = matrix.build_cell_argv(matrix.static_hold_cells()[0], out_dir=tmp_path)

    assert argv[0] == sys.executable
    assert argv[1].endswith("run_colleague_native_usd_completed_pbd_step_video.py")
    assert "--real-beaker-static-hold" in argv
    assert argv[argv.index("--controlled-spawn-count") + 1] == "1024"
    assert argv[argv.index("--controlled-spawn-seed") + 1] == "0"
    assert argv[argv.index("--steps") + 1] == "600"
    assert float(argv[argv.index("--physics-dt") + 1]) == pytest.approx(1.0 / 60.0)
    assert int(argv[argv.index("--trace-interval") + 1]) <= 30
    assert float(argv[argv.index("--runtime-timeout-seconds") + 1]) >= 900.0
    assert "--capture-native-cameras" in argv
    assert "--capture-closeup-camera" in argv
    assert "--hard-exit-after-run" in argv


def test_matrix_closure_requires_exactly_six_accepted_cells():
    accepted = [
        {
            **cell,
            "accepted": True,
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "visible_beaker_containment_verified": True,
        }
        for cell in matrix.static_hold_cells()
    ]

    assert matrix.real_beaker_static_hold_closed(accepted) is True
    assert matrix.real_beaker_static_hold_closed(accepted[:-1]) is False
    assert matrix.real_beaker_static_hold_closed([*accepted, {**accepted[0], "seed": 99}]) is False


def test_matrix_append_rejects_run_identity_mismatch():
    manifest = {"run_identity": {"source_usd_sha256": "a" * 64}, "cells": []}

    with pytest.raises(ValueError, match="identity mismatch"):
        matrix.validate_append_manifest(
            manifest,
            run_identity={"source_usd_sha256": "b" * 64},
            requested_cells=matrix.static_hold_cells(counts=(1024,), seeds=(0,)),
        )


def test_matrix_append_rejects_duplicate_count_seed():
    identity = {"source_usd_sha256": "a" * 64}
    manifest = {
        "run_identity": identity,
        "cells": [{"particle_count": 1024, "seed": 0, "accepted": True}],
    }

    with pytest.raises(ValueError, match="duplicate cell"):
        matrix.validate_append_manifest(
            manifest,
            run_identity=identity,
            requested_cells=matrix.static_hold_cells(counts=(1024,), seeds=(0,)),
        )


def test_matrix_append_rejects_4096_without_three_accepted_1024_cells():
    identity = {"source_usd_sha256": "a" * 64}
    manifest = {
        "run_identity": identity,
        "cells": [
            {
                "particle_count": 1024,
                "seed": seed,
                "accepted": seed != 2,
                "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
                "visible_beaker_containment_verified": True,
            }
            for seed in (0, 1, 2)
        ],
    }

    with pytest.raises(ValueError, match="three accepted 1024"):
        matrix.validate_append_manifest(
            manifest,
            run_identity=identity,
            requested_cells=matrix.static_hold_cells(counts=(4096,), seeds=(0, 1, 2)),
        )


def _matrix_args(tmp_path, *extra):
    source_usd = tmp_path / "source.usd"
    source_usd.write_text("#usda 1.0\n", encoding="utf-8")
    return matrix.build_arg_parser().parse_args(
        [
            "--usd",
            str(source_usd),
            "--out-root",
            str(tmp_path / "cells"),
            "--manifest",
            str(tmp_path / "matrix.json"),
            *extra,
        ]
    )


def _write_mock_child_result(argv, *, classification, verified, returncode=0):
    out_dir = matrix.argv_path(argv, "--out-dir")
    summary_path = matrix.argv_path(argv, "--manifest")
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "particle_readback_trace.jsonl"
    scene_path = out_dir / "native_scene_completed_pbd_overlay.usda"
    frame_path = out_dir / "camera1_native_material_frames" / "frame_0000.png"
    video_path = out_dir / "camera1_native_material.mp4"
    trace_path.write_text("{}\n", encoding="utf-8")
    scene_path.write_text("#usda 1.0\n", encoding="utf-8")
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_bytes(b"png")
    video_path.write_bytes(b"mp4")
    summary_path.write_text(
        json.dumps(
            {
                "classification": {"classification": classification},
                "visible_beaker_containment_verified": verified,
                "physical_trace_identity": {"physical_trace_sha256": "c" * 64},
                "trace_path": str(trace_path),
                "evidence_scene_path": str(scene_path),
                "videos": {"context": {"path": str(video_path)}},
                "physics_particle_offsets": {"particle_width": 0.00045},
                "display_particle_width": 0.0043,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return matrix.ChildResult(returncode=returncode, timed_out=False)


def test_matrix_runs_all_1024_seeds_but_blocks_4096_after_failure(tmp_path, monkeypatch):
    launched = []

    def fake_child(argv, **_kwargs):
        count = int(argv[argv.index("--controlled-spawn-count") + 1])
        seed = int(argv[argv.index("--controlled-spawn-seed") + 1])
        launched.append((count, seed))
        classification = "FAIL_VISIBLE_BEAKER_CONTAINMENT" if seed == 1 else "PASS_VISIBLE_BEAKER_STATIC_HOLD"
        return _write_mock_child_result(
            argv,
            classification=classification,
            verified=classification == "PASS_VISIBLE_BEAKER_STATIC_HOLD",
        )

    monkeypatch.setattr(matrix, "execute_child", fake_child)
    manifest = matrix.run_matrix(_matrix_args(tmp_path))

    assert launched == [(1024, 0), (1024, 1), (1024, 2)]
    assert manifest["real_beaker_static_hold_closed"] is False
    assert manifest["blocked_before_4096"] is True


def test_matrix_mocked_children_require_summary_pass_not_returncode(tmp_path, monkeypatch):
    launched = []

    def fake_child(argv, **_kwargs):
        count = int(argv[argv.index("--controlled-spawn-count") + 1])
        seed = int(argv[argv.index("--controlled-spawn-seed") + 1])
        launched.append((count, seed))
        return _write_mock_child_result(
            argv,
            classification="STOP_RUNTIME_ERROR" if (count, seed) == (1024, 0) else "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            verified=(count, seed) != (1024, 0),
            returncode=0,
        )

    monkeypatch.setattr(matrix, "execute_child", fake_child)
    manifest = matrix.run_matrix(_matrix_args(tmp_path))

    assert manifest["cells"][0]["accepted"] is False
    assert launched == [(1024, 0), (1024, 1), (1024, 2)]


def test_matrix_mocked_six_passes_close_and_hash_artifacts(tmp_path, monkeypatch):
    def fake_child(argv, **_kwargs):
        return _write_mock_child_result(
            argv,
            classification="PASS_VISIBLE_BEAKER_STATIC_HOLD",
            verified=True,
        )

    monkeypatch.setattr(matrix, "execute_child", fake_child)
    manifest = matrix.run_matrix(_matrix_args(tmp_path, "--headless"))

    assert manifest["real_beaker_static_hold_closed"] is True
    assert len(manifest["cells"]) == 6
    assert all(cell["accepted"] for cell in manifest["cells"])
    assert all("summary_path" in cell and "trace_path" in cell for cell in manifest["cells"])
    assert all("stdout.log" in cell["artifact_hashes"] for cell in manifest["cells"])
    assert all("command.json" in cell["artifact_hashes"] for cell in manifest["cells"])
