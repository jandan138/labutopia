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
