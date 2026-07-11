import hashlib
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import types

import pytest
from pxr import Usd, UsdGeom

from tools.labutopia_fluid import run_colleague_native_usd_completed_pbd_step_video as runner
from tools.labutopia_fluid import run_real_beaker_omniglass_replay as replay
from tools.labutopia_fluid import run_real_beaker_static_hold_matrix as matrix
from tools.labutopia_fluid.real_beaker import CupInteriorFrame, validate_strict_trace_schema


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


def test_static_hold_matrix_declares_one_canonical_global_key_sequence():
    assert matrix.CANONICAL_CELL_KEYS == (
        (1024, 0),
        (1024, 1),
        (1024, 2),
        (4096, 0),
        (4096, 1),
        (4096, 2),
    )


def test_static_hold_matrix_canonicalizes_count_and_seed_order():
    cells = matrix.static_hold_cells(counts=(4096, 1024), seeds=(2, 0, 1))

    assert [(cell["particle_count"], cell["seed"]) for cell in cells] == [
        (1024, 0),
        (1024, 1),
        (1024, 2),
        (4096, 0),
        (4096, 1),
        (4096, 2),
    ]


@pytest.mark.parametrize(
    "counts,seeds",
    [
        ((512,), (0,)),
        ((1024, 1024), (0,)),
        ((1024.5,), (0,)),
        ((1024,), (3,)),
        ((1024,), (1.5,)),
        ((1024,), (0, 0)),
    ],
)
def test_static_hold_matrix_rejects_noncanonical_or_duplicate_cells(counts, seeds):
    with pytest.raises(ValueError, match="counts|seeds"):
        matrix.static_hold_cells(counts=counts, seeds=seeds)


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


@pytest.mark.parametrize(
    "extra,match",
    [
        (("--steps", "599"), "exactly 600"),
        (("--physics-dt", "0.016666666667666666"), "exactly 1/60"),
        (("--physics-dt", "nan"), "exactly 1/60"),
    ],
)
def test_matrix_rejects_unpinned_steps_and_physics_dt(tmp_path, extra, match):
    with pytest.raises(ValueError, match=match):
        matrix.build_dry_plan(_matrix_args(tmp_path, *extra))


def test_matrix_rejects_next_float_after_required_physics_dt(tmp_path):
    near_equal = math.nextafter(matrix.REQUIRED_PHYSICS_DT, math.inf)

    with pytest.raises(ValueError, match="exactly 1/60"):
        matrix.build_cell_argv(
            matrix.static_hold_cells()[0],
            out_dir=tmp_path,
            physics_dt=near_equal,
        )


@pytest.mark.parametrize(
    "extra",
    [
        ("--counts", "4096", "--seeds", "0"),
        ("--counts", "1024", "--seeds", "1", "2"),
        ("--counts", "1024", "--seeds", "0", "2"),
    ],
)
def test_matrix_fresh_run_requires_canonical_prefix_from_zero(tmp_path, extra):
    with pytest.raises(ValueError, match="canonical prefix"):
        matrix.build_dry_plan(_matrix_args(tmp_path, *extra))


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


def test_matrix_closure_rejects_noncanonical_runtime_config():
    accepted = [
        {
            **cell,
            "accepted": True,
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "visible_beaker_containment_verified": True,
        }
        for cell in matrix.static_hold_cells()
    ]

    assert matrix.real_beaker_static_hold_closed(accepted, steps=599) is False
    assert matrix.real_beaker_static_hold_closed(accepted, physics_dt=(1.0 / 60.0) + 1e-12) is False


def test_matrix_closure_recomputes_acceptance_from_authoritative_summary():
    cells = [
        {
            **cell,
            "accepted": False,
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "visible_beaker_containment_verified": True,
        }
        for cell in matrix.static_hold_cells()
    ]

    assert matrix.real_beaker_static_hold_closed(cells) is True
    assert matrix.all_required_1024_accepted(cells) is True


def test_matrix_closure_rejects_out_of_order_canonical_cells():
    cells = [
        {
            **cell,
            "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
            "visible_beaker_containment_verified": True,
        }
        for cell in matrix.static_hold_cells()
    ]
    cells[0], cells[1] = cells[1], cells[0]

    assert matrix.real_beaker_static_hold_closed(cells) is False


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
                "classification": (
                    "FAIL_VISIBLE_BEAKER_CONTAINMENT"
                    if seed == 2
                    else "PASS_VISIBLE_BEAKER_STATIC_HOLD"
                ),
                "visible_beaker_containment_verified": seed != 2,
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


def test_matrix_append_rejects_existing_cells_that_are_not_exact_prefix():
    identity = {"source_usd_sha256": "a" * 64}
    manifest = {
        "run_identity": identity,
        "cells": [
            {
                "particle_count": 1024,
                "seed": 1,
                "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
                "visible_beaker_containment_verified": True,
            }
        ],
    }

    with pytest.raises(ValueError, match="exact canonical prefix"):
        matrix.validate_append_manifest(
            manifest,
            run_identity=identity,
            requested_cells=matrix.static_hold_cells(counts=(1024,), seeds=(2,)),
        )


def test_matrix_append_requires_immediate_next_canonical_segment():
    identity = {"source_usd_sha256": "a" * 64}
    manifest = {
        "run_identity": identity,
        "cells": [
            {
                "particle_count": 1024,
                "seed": 0,
                "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
                "visible_beaker_containment_verified": True,
            }
        ],
    }

    with pytest.raises(ValueError, match="immediate next canonical segment"):
        matrix.validate_append_manifest(
            manifest,
            run_identity=identity,
            requested_cells=matrix.static_hold_cells(counts=(1024,), seeds=(2,)),
        )


def test_matrix_append_dry_plan_validates_immediate_next_segment(tmp_path):
    args = _matrix_args(
        tmp_path,
        "--append",
        "--counts",
        "1024",
        "--seeds",
        "2",
    )
    manifest_path = matrix._resolve_manifest_path(args.manifest)
    manifest_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "particle_count": 1024,
                        "seed": 0,
                        "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
                        "visible_beaker_containment_verified": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="immediate next canonical segment"):
        matrix.build_dry_plan(args)


def test_matrix_watchdog_requires_sixty_second_runtime_margin(tmp_path):
    with pytest.raises(ValueError, match="at least 60 seconds"):
        matrix.build_dry_plan(
            _matrix_args(
                tmp_path,
                "--runtime-timeout-seconds",
                "900",
                "--process-timeout-seconds",
                "959.999",
            )
        )


@pytest.mark.parametrize("option", ["--runtime-timeout-seconds", "--process-timeout-seconds"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_matrix_rejects_nonfinite_runtime_and_process_timeouts(tmp_path, option, value):
    with pytest.raises(ValueError, match="finite"):
        matrix.build_dry_plan(_matrix_args(tmp_path, f"{option}={value}"))


@pytest.mark.parametrize("append", [False, True])
@pytest.mark.parametrize("legacy_relative", matrix.SUPERSEDED_FALSE_POSITIVE_MANIFESTS)
def test_matrix_rejects_immutable_legacy_manifest_before_dry_or_append(
    tmp_path, monkeypatch, append, legacy_relative
):
    legacy_path = (matrix.REPO_ROOT / legacy_relative).resolve()
    before = legacy_path.read_bytes() if legacy_path.exists() else None
    extra = ["--manifest", str(legacy_path)]
    if append:
        extra.append("--append")
        monkeypatch.setattr(matrix, "build_run_identity", lambda _args: pytest.fail("identity reached"))
        call = matrix.run_matrix
    else:
        call = matrix.build_dry_plan

    with pytest.raises(ValueError, match="immutable legacy manifest"):
        call(_matrix_args(tmp_path, *extra))

    after = legacy_path.read_bytes() if legacy_path.exists() else None
    assert after == before


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


def test_matrix_accepts_authoritative_pass_with_nonzero_returncode(tmp_path, monkeypatch):
    def fake_child(argv, **_kwargs):
        count = int(argv[argv.index("--controlled-spawn-count") + 1])
        seed = int(argv[argv.index("--controlled-spawn-seed") + 1])
        return _write_mock_child_result(
            argv,
            classification="PASS_VISIBLE_BEAKER_STATIC_HOLD",
            verified=True,
            returncode=7 if (count, seed) == (1024, 0) else 0,
        )

    monkeypatch.setattr(matrix, "execute_child", fake_child)
    manifest = matrix.run_matrix(_matrix_args(tmp_path))

    assert manifest["real_beaker_static_hold_closed"] is True
    assert manifest["cells"][0]["accepted"] is True
    assert manifest["cells"][0]["returncode"] == 7
    assert manifest["cells"][0]["returncode_warning"] is not None


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


class _FatalChildWait(BaseException):
    pass


@pytest.mark.parametrize(
    "wait_exception,reraised",
    [
        (subprocess.TimeoutExpired("child", 1), None),
        (KeyboardInterrupt(), KeyboardInterrupt),
        (_FatalChildWait(), _FatalChildWait),
    ],
)
def test_matrix_execute_child_terminates_reaps_and_persists_logs(
    tmp_path, monkeypatch, wait_exception, reraised
):
    processes = []
    signals = []

    class FakeProcess:
        pid = 4321
        returncode = None

        def __init__(self, **kwargs):
            self.wait_calls = 0
            kwargs["stdout"].write(b"available stdout\n")
            kwargs["stderr"].write(b"available stderr\n")

        def wait(self, timeout=None):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise wait_exception
            self.returncode = -signal.SIGTERM
            return self.returncode

    def fake_popen(*_args, **kwargs):
        process = FakeProcess(**kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(matrix.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(matrix.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"

    if reraised is None:
        result = matrix.execute_child(
            ["child"],
            cwd=tmp_path,
            env={},
            timeout_seconds=1,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        assert result.timed_out is True
    else:
        with pytest.raises(reraised):
            matrix.execute_child(
                ["child"],
                cwd=tmp_path,
                env={},
                timeout_seconds=1,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )

    assert signals == [(4321, signal.SIGTERM)]
    assert processes[0].wait_calls == 2
    assert stdout_path.read_text(encoding="utf-8") == "available stdout\n"
    assert stderr_path.read_text(encoding="utf-8") == "available stderr\n"


def test_matrix_isaac_version_falls_back_to_version_file(tmp_path, monkeypatch):
    version_path = tmp_path / "VERSION"
    version_path.write_text("4.1.0.0\n", encoding="utf-8")

    def missing_metadata(_distribution):
        raise matrix.importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(matrix.importlib.metadata, "version", missing_metadata)
    monkeypatch.setattr(matrix, "ISAAC_VERSION_FILES", (version_path,))

    version = matrix._isaac_version()

    assert version != "unavailable"
    assert "4.1.0.0" in version
    assert str(version_path.resolve()) in version
    assert matrix._sha256_file(version_path) in version


def test_matrix_isaac_root_fingerprint_changes_with_install_content(tmp_path, monkeypatch):
    install_root = tmp_path / "isaac-sim"
    artifact = install_root / "apps" / "isaacsim.exp.full.kit"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("[package]\nversion = '4.1.0'\n", encoding="utf-8")

    def missing_metadata(_distribution):
        raise matrix.importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(matrix.importlib.metadata, "version", missing_metadata)
    monkeypatch.setattr(matrix, "ISAAC_VERSION_FILES", ())
    monkeypatch.setattr(matrix, "ISAAC_INSTALL_ROOTS", (install_root,), raising=False)
    monkeypatch.setattr(matrix.importlib.util, "find_spec", lambda _name: None)

    first = matrix._isaac_version()
    artifact.write_text("[package]\nversion = '4.1.0-fixed'\n", encoding="utf-8")
    second = matrix._isaac_version()

    assert first != second
    assert str(install_root.resolve()) in first
    assert "installation_fingerprint_sha256=" in first


def test_matrix_isaac_version_fails_closed_without_real_install(tmp_path, monkeypatch):
    def missing_metadata(_distribution):
        raise matrix.importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(matrix.importlib.metadata, "version", missing_metadata)
    monkeypatch.setattr(matrix, "ISAAC_VERSION_FILES", ())
    monkeypatch.setattr(matrix, "ISAAC_INSTALL_ROOTS", (tmp_path / "missing",), raising=False)
    monkeypatch.setattr(matrix.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.delenv("ISAAC_SIM_ROOT", raising=False)
    monkeypatch.delenv("ISAAC_PATH", raising=False)

    with pytest.raises(RuntimeError, match="Isaac installation"):
        matrix._isaac_version()


def _sha256_path(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_accepted_replay_input(tmp_path):
    source_path = tmp_path / "localized_lab_scene.usda"
    source_path.write_text("#usda 1.0\n", encoding="utf-8")
    source_hash = _sha256_path(source_path)
    records = [
        {
            "step_index": 0,
            "particle_count": 2,
            "positions": [[0.3, 0.1, 0.84], [0.301, 0.1, 0.841]],
        },
        {
            "step_index": 10,
            "particle_count": 2,
            "positions": [[0.3, 0.1, 0.85], [0.302, 0.1, 0.851]],
        },
    ]
    identity = validate_strict_trace_schema(
        records,
        requested_count=2,
        steps=10,
        cadence=10,
        source_usd_sha256=source_hash,
        particle_seed=7,
    )
    trace_path = tmp_path / "particle_readback_trace.jsonl"
    trace_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    frame = CupInteriorFrame(
        origin_world=(0.3, 0.1, 0.82),
        x_axis_world=(1.0, 0.0, 0.0),
        y_axis_world=(0.0, 1.0, 0.0),
        z_axis_world=(0.0, 0.0, 1.0),
        parent_local_axis="Y",
        outer_radius=0.0375,
        interior_radius=0.032,
        outer_floor=0.0,
        interior_floor=0.0,
        rim_height=0.09,
        calibration_source="authored_particle_bounds",
        axis_alignment_dot=1.0,
    )
    strict = {
        "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
        "trace_schema_valid": True,
        "diagnostic_scan_complete": True,
        "physical_trace_identity": identity,
    }
    log_path = tmp_path / "kit.log"
    log_prefix = b"x" * 123
    log_bytes = b"clean run segment"
    log_path.write_bytes(log_prefix + log_bytes)
    log_segment = {
        "log_path": str(log_path),
        "byte_offset": len(log_prefix),
        "cursor_captured": True,
        "diagnostic_scan_complete": True,
        "segment_byte_count": len(log_bytes),
        "segment_sha256": hashlib.sha256(log_bytes).hexdigest(),
    }
    summary = {
        "source_usd_path": str(source_path),
        "source_usd_sha256": source_hash,
        "trace_path": str(trace_path),
        "steps": 10,
        "selected_particle_count": 2,
        "controlled_spawn_plan": {"particle_seed": 7},
        "region_config": {
            "trace_interval": 10,
            "source_center": [0.3, 0.1, 0.82],
            "target_center": [0.1, 0.1, 0.82],
            "table_z": 0.82,
            "source_radius": 0.032,
            "target_radius": 0.032,
            "source_height": 0.09,
            "target_height": 0.09,
        },
        "cup_interior_frame": frame.as_dict(),
        "strict_visible_classification": strict,
        "classification": strict,
        "visible_beaker_containment_verified": True,
        "physical_trace_identity": identity,
        "strict_kit_log_segment": log_segment,
        "isaac_log_summary": {
            **log_segment,
            "isaac_log_path": log_segment["log_path"],
            "isaac_log_available": True,
            "run_segment_only": True,
        },
        "physics_particle_offsets": {"particle_width": 0.00045},
        "display_particle_width": 0.0043,
    }
    summary_path = tmp_path / "accepted_summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    return summary_path, summary, records


def _replay_args(tmp_path, summary_path, *extra):
    return replay.build_arg_parser().parse_args(
        [
            "--accepted-summary",
            str(summary_path),
            "--out-root",
            str(tmp_path / "renders"),
            *extra,
        ]
    )


def test_replay_argv_requires_accepted_trace_and_three_candidates(tmp_path):
    args = _replay_args(tmp_path, tmp_path / "summary.json")

    assert args.accepted_summary.endswith("summary.json")
    assert args.candidates == "OMNI_REF_FINE,OMNI_REF_RATIO_15,OMNI_REF_RATIO_12"


def test_replay_dry_plan_reads_no_summary_and_lists_all_candidate_contracts(
    tmp_path, monkeypatch, capsys
):
    sentinel = tmp_path / "DRY_PLAN_ACCEPTED_SUMMARY_NOT_READ"

    def fail_read(_self, *args, **kwargs):
        pytest.fail("dry-plan attempted to read a filesystem input")

    monkeypatch.setattr(Path, "read_text", fail_read)
    monkeypatch.setattr(replay, "_run_runtime", lambda *_args: pytest.fail("runtime booted"))

    exit_code = replay.main(
        [
            "--accepted-summary",
            str(sentinel),
            "--out-root",
            str(tmp_path / "renders"),
            "--dry-plan",
        ]
    )
    plan = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert plan["accepted_summary_read"] is False
    assert plan["simulation_app_started"] is False
    assert plan["candidate_ids"] == [
        "OMNI_REF_FINE",
        "OMNI_REF_RATIO_15",
        "OMNI_REF_RATIO_12",
    ]
    assert list(plan["candidate_contracts"]) == plan["candidate_ids"]
    assert plan["candidate_contracts"]["OMNI_REF_FINE"]["width_formula"] == (
        "clamp(interior_diameter/32,0.0015,0.0020)"
    )


def test_replay_direct_script_dry_plan_bootstraps_repo_imports():
    script = Path(replay.__file__).resolve()
    repo_root = script.parents[2]

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--accepted-summary",
            "DRY_PLAN_ACCEPTED_SUMMARY_NOT_READ",
            "--dry-plan",
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["simulation_app_started"] is False


def test_replay_isaac41_dry_plan_needs_no_pxr_or_runtime_boot():
    isaac_python = Path(
        "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
        "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
    )
    if not isaac_python.is_file():
        pytest.skip(f"Isaac 4.1 interpreter missing: {isaac_python}")
    script = Path(replay.__file__).resolve()

    result = subprocess.run(
        [
            str(isaac_python),
            str(script),
            "--accepted-summary",
            "DRY_PLAN_ACCEPTED_SUMMARY_NOT_READ",
            "--dry-plan",
        ],
        cwd=script.parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["accepted_summary_read"] is False
    assert plan["isaac_runtime_imported"] is False
    assert plan["simulation_app_started"] is False
    assert plan["out_root"].endswith(
        "docs/labutopia_lab_poc/evidence_manifests/"
        "real_beaker_omniglass_reference_20260711_001"
    )


def _fake_native_mdl_contract(root):
    return types.SimpleNamespace(
        PRESENTATION_WATER_MDL_ROOT=root,
        CORE_MDL_DIRECT_ASSETS=("OmniGlass.mdl", "OmniSurfacePresets.mdl"),
        CORE_MDL_TRANSITIVE_DEPENDENCIES=("OmniGlass_Opacity.mdl",),
    )


def test_replay_rejects_host_isaac_mdl_root_for_target_conda_runtime(tmp_path):
    runtime_prefix = tmp_path / "isaacsim41-conda"
    runtime_prefix.mkdir()
    native = _fake_native_mdl_contract(Path("/isaac-sim/kit/mdl/core"))

    with pytest.raises(ValueError, match="version_matched_conda_mdl_root_required"):
        replay.build_version_matched_mdl_source_contract(
            native,
            runtime_prefix=runtime_prefix,
            runtime_version="4.1.0.0",
        )


def test_replay_version_matched_mdl_contract_hashes_required_conda_files(tmp_path):
    runtime_prefix = tmp_path / "isaacsim41-conda"
    root = runtime_prefix / "lib/python3.10/site-packages/omni/mdl/core"
    required = {
        "Base/OmniGlass.mdl": "omniglass-4.1\n",
        "Base/OmniGlass_Opacity.mdl": "opacity-4.1\n",
        "Base/OmniSurfacePresets.mdl": "presets-4.1\n",
        "mdl/OmniSurface/OmniSurfaceBase.mdl": "surface-base-4.1\n",
    }
    for relative, content in required.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    native = _fake_native_mdl_contract(root)

    contract = replay.build_version_matched_mdl_source_contract(
        native,
        runtime_prefix=runtime_prefix,
        runtime_version="4.1.0.0",
    )

    assert Path(contract["source_root"]).is_relative_to(runtime_prefix)
    assert contract["runtime_version"] == "4.1.0.0"
    assert contract["source_root_under_runtime_prefix"] is True
    assert set(contract["required_file_sha256"]) == set(required)
    assert all(len(value) == 64 for value in contract["required_file_sha256"].values())
    assert len(contract["source_tree_sha256"]) == 64


def test_replay_missing_summary_fails_before_runtime_boot(tmp_path, monkeypatch):
    booted = []
    monkeypatch.setattr(replay, "_run_runtime", lambda *_args: booted.append(True))

    with pytest.raises(FileNotFoundError, match="accepted_summary_missing"):
        replay.run_replay(_replay_args(tmp_path, tmp_path / "missing.json"))

    assert booted == []


def test_replay_nonpass_summary_fails_before_runtime_boot(tmp_path, monkeypatch):
    summary_path, summary, _records = _write_accepted_replay_input(tmp_path)
    summary["strict_visible_classification"]["classification"] = (
        "FAIL_VISIBLE_BEAKER_CONTAINMENT"
    )
    summary["classification"] = summary["strict_visible_classification"]
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    booted = []
    monkeypatch.setattr(replay, "_run_runtime", lambda *_args: booted.append(True))

    with pytest.raises(ValueError, match="accepted_static_hold_required"):
        replay.run_replay(_replay_args(tmp_path, summary_path))

    assert booted == []


def test_replay_incomplete_run_scoped_diagnostics_fail_before_runtime_boot(
    tmp_path, monkeypatch
):
    summary_path, summary, _records = _write_accepted_replay_input(tmp_path)
    summary.pop("strict_kit_log_segment")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    booted = []
    monkeypatch.setattr(replay, "_run_runtime", lambda *_args: booted.append(True))

    with pytest.raises(ValueError, match="run_scoped_diagnostics_incomplete"):
        replay.run_replay(_replay_args(tmp_path, summary_path))

    assert booted == []


def test_replay_invalid_strict_trace_schema_fails_before_runtime_boot(tmp_path, monkeypatch):
    summary_path, summary, records = _write_accepted_replay_input(tmp_path)
    records[-1]["step_index"] = 9
    Path(summary["trace_path"]).write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    booted = []
    monkeypatch.setattr(replay, "_run_runtime", lambda *_args: booted.append(True))

    with pytest.raises(ValueError, match="strict_trace_schema_invalid"):
        replay.run_replay(_replay_args(tmp_path, summary_path))

    assert booted == []


def test_replay_requires_exact_full_recomputed_trace_identity_before_runtime_boot(
    tmp_path, monkeypatch
):
    summary_path, summary, _records = _write_accepted_replay_input(tmp_path)
    mismatched = {**summary["physical_trace_identity"], "summary_only_field": "forbidden"}
    summary["physical_trace_identity"] = mismatched
    summary["strict_visible_classification"]["physical_trace_identity"] = mismatched
    summary["classification"] = summary["strict_visible_classification"]
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    booted = []
    monkeypatch.setattr(replay, "_run_runtime", lambda *_args: booted.append(True))

    with pytest.raises(ValueError, match="physical_trace_identity_mismatch"):
        replay.run_replay(_replay_args(tmp_path, summary_path))

    assert booted == []


def test_replay_candidate_manifests_share_complete_input_identity(tmp_path):
    summary_path, summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)

    manifests = replay.build_candidate_replay_contracts(accepted)

    required_identity_fields = {
        "source_usd_sha256",
        "particle_count",
        "seed",
        "steps",
        "trace_interval",
        "frame_indices",
        "frame_particle_counts",
        "frame_count",
        "positions_sha256",
        "physical_trace_sha256",
    }
    assert list(manifests) == [
        "OMNI_REF_FINE",
        "OMNI_REF_RATIO_15",
        "OMNI_REF_RATIO_12",
    ]
    assert all(
        manifest["physical_trace_identity"] == summary["physical_trace_identity"]
        for manifest in manifests.values()
    )
    assert all(
        manifest["input_identity"] == summary["physical_trace_identity"]
        for manifest in manifests.values()
    )
    assert all(
        set(manifest["input_identity"]) == required_identity_fields
        for manifest in manifests.values()
    )
    assert all(
        manifest["static_presentation_frame_index"] == 10
        and manifest["hidden_physical_initial_state_frame_index"] == 0
        for manifest in manifests.values()
    )
    assert all(
        manifest["runtime_contract"]
        == {
            "source_usd_path": str(Path(summary["source_usd_path"]).resolve()),
            "open_exact_accepted_source": True,
            "physics_steps_executed": 0,
            "timeline_play_called": False,
            "cameras": ["context", "source_beaker_closeup"],
        }
        for manifest in manifests.values()
    )


def test_candidate_manifest_requires_both_image_sets_and_never_self_claims_visual_pass(
    tmp_path,
):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    contract = replay.build_candidate_replay_contracts(accepted)["OMNI_REF_FINE"]
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    static_usd = candidate_dir / "candidate_static.usda"
    static_usd.write_text("#usda 1.0\n", encoding="utf-8")
    closeups = [candidate_dir / f"closeup_{index}.png" for index in range(2)]
    contexts = [candidate_dir / f"context_{index}.png" for index in range(2)]
    for path in [*closeups, *contexts]:
        path.write_bytes(b"\x89PNG\r\n\x1a\nrendered")

    finalized = replay.finalize_candidate_manifest(
        contract,
        candidate_dir=candidate_dir,
        static_usd_path=static_usd,
        closeup_image_paths=closeups,
        context_image_paths=contexts,
        video_paths=[],
    )

    assert finalized["render_artifacts_complete"] is True
    assert finalized["visual_review_verdict"] == "PENDING_INDEPENDENT_REVIEW"
    assert finalized["omniglass_reference_particle_look_selected"] is False
    assert set(finalized["artifact_sha256"]) == {
        "candidate_static.usda",
        "closeup_0.png",
        "closeup_1.png",
        "context_0.png",
        "context_1.png",
    }

    closeups[-1].unlink()
    with pytest.raises(ValueError, match="candidate_images_incomplete"):
        replay.finalize_candidate_manifest(
            contract,
            candidate_dir=candidate_dir,
            static_usd_path=static_usd,
            closeup_image_paths=closeups,
            context_image_paths=contexts,
            video_paths=[],
        )


def test_static_candidate_stage_uses_final_proxy_and_hides_physical_initial_state(tmp_path):
    summary_path, _summary, records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    contract = replay.build_candidate_replay_contracts(accepted)["OMNI_REF_RATIO_15"]
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    original = UsdGeom.Points.Define(stage, "/World/ParticleSet")
    original.CreatePointsAttr([(9.0, 9.0, 9.0)])

    authored = replay.author_static_candidate_state(
        stage,
        accepted=accepted,
        candidate_contract=contract,
        material_path=None,
    )

    presentation = UsdGeom.Points(
        stage.GetPrimAtPath("/World/CompletedPBD/PresentationParticleSet")
    )
    hidden_initial = UsdGeom.Points(
        stage.GetPrimAtPath("/World/CompletedPBD/AcceptedPhysicalInitialState")
    )
    final_proxy = accepted.proxy_frame("OMNI_REF_RATIO_15", frame_offset=-1)
    for actual, expected in zip(
        presentation.GetPointsAttr().Get(), final_proxy["positions_world"]
    ):
        assert tuple(actual) == pytest.approx(expected, abs=1e-6)
    for actual, expected in zip(hidden_initial.GetPointsAttr().Get(), records[0]["positions"]):
        assert tuple(actual) == pytest.approx(expected, abs=1e-6)
    assert UsdGeom.Imageable(original).ComputeVisibility() == UsdGeom.Tokens.invisible
    assert UsdGeom.Imageable(hidden_initial).ComputeVisibility() == UsdGeom.Tokens.invisible
    assert UsdGeom.Imageable(presentation).ComputeVisibility() != UsdGeom.Tokens.invisible
    assert authored["static_presentation_frame_index"] == 10
    assert authored["hidden_physical_initial_state_frame_index"] == 0
    assert authored["physics_schema_applied_to_presentation"] is False


def test_replay_hides_source_fluid_root_and_debug_visuals():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    fluid_root = UsdGeom.Xform.Define(stage, "/World/fluid")
    debug_mesh = UsdGeom.Mesh.Define(stage, "/World/CompletedPBD/DebugSurface")
    physical_points = UsdGeom.Points.Define(stage, "/World/CompletedPBD/ParticleSet")

    hidden = replay.hide_physical_and_debug_points(stage)

    for schema in (fluid_root, debug_mesh, physical_points):
        assert UsdGeom.Imageable(schema).ComputeVisibility() == UsdGeom.Tokens.invisible
    assert set(hidden["hidden_paths"]) >= {
        "/World/fluid",
        "/World/CompletedPBD/DebugSurface",
        "/World/CompletedPBD/ParticleSet",
    }


def test_replay_refuses_to_render_while_timeline_is_playing():
    class Timeline:
        def __init__(self, playing):
            self.playing = playing
            self.play_calls = 0

        def is_playing(self):
            return self.playing

        def play(self):
            self.play_calls += 1

    stopped = Timeline(False)
    replay.require_stopped_timeline(stopped)
    assert stopped.play_calls == 0

    playing = Timeline(True)
    with pytest.raises(RuntimeError, match="timeline_must_remain_stopped"):
        replay.require_stopped_timeline(playing)
    assert playing.play_calls == 0


def test_replay_reloads_exact_disk_layer_before_each_candidate(tmp_path):
    source_path = (tmp_path / "localized_scene.usda").resolve()
    source_path.write_text("#usda 1.0\n", encoding="utf-8")

    class RootLayer:
        realPath = str(source_path)

    class Stage:
        def __init__(self):
            self.reload_calls = 0

        def Reload(self):
            self.reload_calls += 1

        def GetRootLayer(self):
            return RootLayer()

    stage = Stage()

    class Context:
        def open_stage(self, path):
            assert Path(path).resolve() == source_path
            return True

        def get_stage(self):
            return stage

    class Timeline:
        @staticmethod
        def is_playing():
            return False

    opened = replay._open_exact_stage(
        context=Context(),
        app=types.SimpleNamespace(update=lambda: pytest.fail("unexpected update")),
        timeline=Timeline(),
        source_path=source_path,
        warmup_updates=1,
    )

    assert opened is stage
    assert stage.reload_calls == 1


def test_replay_atomic_json_write_leaves_no_partial_file(tmp_path):
    target = tmp_path / "nested" / "manifest.json"

    replay.atomic_write_json(target, {"candidate_id": "OMNI_REF_FINE"})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "candidate_id": "OMNI_REF_FINE"
    }
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []
