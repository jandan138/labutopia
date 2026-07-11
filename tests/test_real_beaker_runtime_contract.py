import sys
import types

import pytest
from pxr import Usd, UsdGeom

from tools.labutopia_fluid import run_colleague_native_usd_completed_pbd_step_video as runner


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
