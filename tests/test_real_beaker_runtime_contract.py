import hashlib
import ctypes
import errno
import fcntl
import io
import json
import math
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import subprocess
import sys
import time
import types
import zipfile

import pytest
from PIL import Image
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

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


def test_replay_uses_a18_reference_exposure_lighting_for_nested_glass():
    assert replay.REPLAY_PRESENTATION_LOOK_ID == "weekly_omniglass_C"


def test_replay_a18_reference_lighting_authors_exact_exposure_temperature_and_rotation():
    from pxr import UsdLux

    from tools.labutopia_fluid.presentation_look_profiles import (
        resolve_presentation_look_profile,
    )

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    profile = resolve_presentation_look_profile(replay.REPLAY_PRESENTATION_LOOK_ID)

    info = runner._author_liquid_presentation_lighting(stage, profile)
    key = UsdLux.DistantLight(
        stage.GetPrimAtPath("/World/LiquidPresentationKeyLight")
    )
    dome = UsdLux.DomeLight(
        stage.GetPrimAtPath("/World/LiquidPresentationDomeLight")
    )

    assert info["mode"] == "exposure_ct_ref_v1"
    assert info["lighting_contract_hash"] == "weekly_omniglass_exposure_ct_v1"
    assert info["key_exposure"] == pytest.approx(10.0)
    assert info["dome_exposure"] == pytest.approx(9.0)
    assert info["key_color_temperature"] == pytest.approx(7250.0)
    assert info["dome_color_temperature"] == pytest.approx(6150.0)
    assert info["rotate_xyz"] == pytest.approx([55.0, 0.0, 135.0])
    assert key.GetIntensityAttr().Get() == pytest.approx(1.0)
    assert key.GetExposureAttr().Get() == pytest.approx(10.0)
    assert key.GetColorTemperatureAttr().Get() == pytest.approx(7250.0)
    assert dome.GetIntensityAttr().Get() == pytest.approx(1.0)
    assert dome.GetExposureAttr().Get() == pytest.approx(9.0)
    assert dome.GetColorTemperatureAttr().Get() == pytest.approx(6150.0)


def test_parser_exposes_display_particle_width():
    args = runner.build_arg_parser().parse_args(["--display-particle-width", "0.0043"])

    assert args.display_particle_width == pytest.approx(0.0043)


def test_strict_si_units_are_authored_on_runtime_root_and_verified():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    assert UsdGeom.GetStageMetersPerUnit(stage) == pytest.approx(0.01)
    assert stage.HasAuthoredMetadata("metersPerUnit") is False
    assert stage.HasAuthoredMetadata("kilogramsPerUnit") is False

    contract = runner.author_and_verify_strict_si_stage_units(stage)

    assert UsdGeom.GetStageMetersPerUnit(stage) == 1.0
    assert UsdPhysics.GetStageKilogramsPerUnit(stage) == 1.0
    assert stage.HasAuthoredMetadata("metersPerUnit") is True
    assert stage.HasAuthoredMetadata("kilogramsPerUnit") is True
    assert contract == {
        "source_meters_per_unit": 0.01,
        "source_kilograms_per_unit": 1.0,
        "source_meters_per_unit_authored": False,
        "source_kilograms_per_unit_authored": False,
        "effective_meters_per_unit": 1.0,
        "effective_kilograms_per_unit": 1.0,
        "meters_per_unit_authored": True,
        "kilograms_per_unit_authored": True,
        "unit_authoring_layer": stage.GetRootLayer().identifier,
        "strict_si_units_verified": True,
    }


def test_strict_si_density_contract_requires_authored_material_and_particle_density():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    material = UsdGeom.Scope.Define(stage, "/World/Looks/FluidPhysics").GetPrim()
    material.CreateAttribute(
        "physxPBDMaterial:density", Sdf.ValueTypeNames.Float
    ).Set(1000.0)
    particle_set = UsdGeom.Points.Define(stage, "/World/ParticleSet").GetPrim()
    particle_set.CreateAttribute("physics:mass", Sdf.ValueTypeNames.Float).Set(0.0)
    particle_set.CreateAttribute("physics:density", Sdf.ValueTypeNames.Float).Set(
        1000.0
    )

    contract = runner.verify_strict_si_density_authoring(
        stage,
        material_path="/World/Looks/FluidPhysics",
        particle_set_path="/World/ParticleSet",
    )

    assert contract == {
        "material_path": "/World/Looks/FluidPhysics",
        "particle_set_path": "/World/ParticleSet",
        "material_density_kg_m3": 1000.0,
        "particle_density_kg_m3": 1000.0,
        "particle_mass_kg": 0.0,
        "density_authority": "authored_density_with_zero_mass",
        "strict_si_density_verified": True,
    }


def test_strict_si_density_contract_rejects_missing_authored_density():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Scope.Define(stage, "/World/Looks/FluidPhysics")
    UsdGeom.Points.Define(stage, "/World/ParticleSet")

    with pytest.raises(RuntimeError, match="strict_si_density_authoring_failed"):
        runner.verify_strict_si_density_authoring(
            stage,
            material_path="/World/Looks/FluidPhysics",
            particle_set_path="/World/ParticleSet",
        )


def test_physical_authoring_identity_is_stable_and_binds_all_physics_inputs():
    kwargs = {
        "source_usd_sha256": "a" * 64,
        "runner_script_sha256": "b" * 64,
        "isaacsim_version": "4.1.0.0",
        "particle_count": 1024,
        "seed": 0,
        "spawn_positions_sha256": "c" * 64,
        "logical_dt": 1.0 / 60.0,
        "integration_dt": 1.0 / 600.0,
        "substeps_per_logical_step": 10,
        "stage_unit_contract": {
            "effective_meters_per_unit": 1.0,
            "effective_kilograms_per_unit": 1.0,
            "strict_si_units_verified": True,
            "numeric_geometry_invariant": True,
            "density_contract": {
                "material_density_kg_m3": 1000.0,
                "particle_density_kg_m3": 1000.0,
                "particle_mass_kg": 0.0,
                "strict_si_density_verified": True,
            },
        },
        "particle_system_collision_offsets": {
            "contact_offset": 0.001058508,
            "rest_offset": 0.000594,
            "particle_contact_offset": 0.000705672,
            "solid_rest_offset": 0.000594,
            "fluid_rest_offset": 0.000352836,
        },
        "canonical_wrapper_summary": {
            "enabled": True,
            "collider_count": 145,
            "panel_count": 72,
            "panel_ring_count": 2,
            "bottom_top_canonical_z": -0.237,
        },
        "physics_settings": {
            "strict_timestep_verified": True,
            "time_steps_per_second": 600,
            "effective_physics_dt": 1.0 / 600.0,
        },
    }

    first = runner.build_strict_physical_authoring_identity(**kwargs)
    second = runner.build_strict_physical_authoring_identity(**kwargs)
    changed_seed = runner.build_strict_physical_authoring_identity(
        **{**kwargs, "seed": 1}
    )

    assert first == second
    assert first["schema_version"] == 1
    assert first["particle_count"] == 1024
    assert first["seed"] == 0
    assert first["isaacsim_version"] == "4.1.0.0"
    assert len(first["wrapper_contract_sha256"]) == 64
    assert len(first["physics_authoring_sha256"]) == 64
    assert changed_seed["physics_authoring_sha256"] != first["physics_authoring_sha256"]


def test_replay_preflight_modules_do_not_import_pxr_before_simulation_app():
    code = """
import builtins

original_import = builtins.__import__

def reject_pxr(name, *args, **kwargs):
    if name == 'pxr' or name.startswith('pxr.'):
        raise RuntimeError('pxr_imported_before_simulation_app')
    return original_import(name, *args, **kwargs)

builtins.__import__ = reject_pxr
import tools.labutopia_fluid.real_beaker
import tools.labutopia_fluid.omniglass_reference
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


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


def test_strict_hold_rejects_negative_integration_trace_substeps():
    with pytest.raises(ValueError, match="integration_trace_substeps_must_be_nonnegative"):
        runner.validate_real_beaker_static_hold_args(
            _strict_args("--integration-trace-substeps", "-1")
        )


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
            captured["particle_mass"] = args[9]
            captured["particle_density"] = args[10]
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
        non_particle_rest_offset=widths["solid_rest_offset"],
    )

    assert captured["system"]["contact_offset"] == widths["particle_system_contact_offset"]
    assert captured["system"]["particle_contact_offset"] == widths["particle_contact_offset"]
    assert captured["system"]["solid_rest_offset"] == widths["solid_rest_offset"]
    assert captured["system"]["fluid_rest_offset"] == widths["fluid_rest_offset"]
    assert captured["system"]["rest_offset"] == widths["solid_rest_offset"]
    assert captured["point_widths"] == [expected_width, expected_width]
    assert captured["particle_mass"] == 0.0
    assert captured["particle_density"] == 1000.0


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
    assert float(argv[argv.index("--logical-dt") + 1]) == pytest.approx(1.0 / 60.0)
    assert float(argv[argv.index("--integration-dt") + 1]) == pytest.approx(1.0 / 600.0)
    assert int(argv[argv.index("--substeps-per-logical-step") + 1]) == 10
    assert int(argv[argv.index("--trace-interval") + 1]) <= 30
    assert float(argv[argv.index("--runtime-timeout-seconds") + 1]) >= 900.0
    assert "--capture-native-cameras" in argv
    assert "--capture-closeup-camera" in argv
    assert "--hard-exit-after-run" in argv


@pytest.mark.parametrize(
    "extra,match",
    [
        (("--steps", "599"), "exactly 600"),
        (("--logical-dt", "0.016666666667666666"), "logical dt must be exactly 1/60"),
        (("--integration-dt", "nan"), "integration dt must be exactly 1/600"),
        (("--substeps-per-logical-step", "9"), "substeps must be exactly 10"),
    ],
)
def test_matrix_rejects_unpinned_two_level_step_schedule(tmp_path, extra, match):
    with pytest.raises(ValueError, match=match):
        matrix.build_dry_plan(_matrix_args(tmp_path, *extra))


def test_matrix_rejects_next_float_after_required_integration_dt(tmp_path):
    near_equal = math.nextafter(matrix.REQUIRED_INTEGRATION_DT, math.inf)

    with pytest.raises(ValueError, match="exactly 1/600"):
        matrix.build_cell_argv(
            matrix.static_hold_cells()[0],
            out_dir=tmp_path,
            integration_dt=near_equal,
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


def _authoritative_pass_evidence(*, particle_count=1024, seed=0):
    physics_settings = {
        "strict_timestep_verified": True,
        "time_steps_per_second": 600,
        "effective_physics_dt": 1.0 / 600.0,
    }
    stage_unit_contract = {
        "effective_meters_per_unit": 1.0,
        "effective_kilograms_per_unit": 1.0,
        "meters_per_unit_authored": True,
        "kilograms_per_unit_authored": True,
        "strict_si_units_verified": True,
        "numeric_geometry_invariant": True,
        "density_contract": {
            "material_density_kg_m3": 1000.0,
            "particle_density_kg_m3": 1000.0,
            "particle_mass_kg": 0.0,
            "strict_si_density_verified": True,
        },
    }
    collision_offsets = {
        "contact_offset": 0.001058508,
        "rest_offset": 0.000594,
        "particle_contact_offset": 0.000705672,
        "solid_rest_offset": 0.000594,
        "fluid_rest_offset": 0.000352836,
    }
    identity = runner.build_strict_physical_authoring_identity(
        source_usd_sha256="a" * 64,
        runner_script_sha256="b" * 64,
        isaacsim_version="4.1.0.0",
        particle_count=particle_count,
        seed=seed,
        spawn_positions_sha256="c" * 64,
        logical_dt=1.0 / 60.0,
        integration_dt=1.0 / 600.0,
        substeps_per_logical_step=10,
        stage_unit_contract=stage_unit_contract,
        particle_system_collision_offsets=collision_offsets,
        canonical_wrapper_summary={"enabled": True, "collider_count": 145},
        physics_settings=physics_settings,
    )
    return {
        "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
        "visible_beaker_containment_verified": True,
        "strict_physics_execution": {
            "exact_step_count_verified": True,
            "exact_logical_step_count_verified": True,
            "exact_integration_step_count_verified": True,
            "requested_logical_steps": 600,
            "executed_logical_steps": 600,
            "requested_integration_steps": 6000,
            "executed_integration_steps": 6000,
            "logical_dt": 1.0 / 60.0,
            "integration_dt": 1.0 / 600.0,
            "substeps_per_logical_step": 10,
            "simulate_fetch_pair_count": 6000,
            "ordered_lifecycle_verified": True,
            "lifecycle_event_count": 12604,
            "lifecycle_event_sha256": "d" * 64,
            "attach_verified": True,
            "detach_verified": True,
            "render_updates_advance_physics": False,
            "render_invariance_checks": 2,
        },
        "physics_settings": physics_settings,
        "stage_unit_contract": stage_unit_contract,
        "authored_runtime_paths": {
            "particle_system_collision_offsets": collision_offsets
        },
        "physical_authoring_identity": identity,
    }


def test_matrix_closure_requires_exactly_six_accepted_cells():
    accepted = [
        {
            **cell,
            "accepted": True,
            **_authoritative_pass_evidence(
                particle_count=cell["particle_count"], seed=cell["seed"]
            ),
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
            **_authoritative_pass_evidence(
                particle_count=cell["particle_count"], seed=cell["seed"]
            ),
        }
        for cell in matrix.static_hold_cells()
    ]

    assert matrix.real_beaker_static_hold_closed(accepted, steps=599) is False
    assert matrix.real_beaker_static_hold_closed(
        accepted, logical_dt=(1.0 / 60.0) + 1e-12
    ) is False
    assert matrix.real_beaker_static_hold_closed(
        accepted, integration_dt=(1.0 / 600.0) + 1e-12
    ) is False
    assert matrix.real_beaker_static_hold_closed(
        accepted, substeps_per_logical_step=9
    ) is False


def test_matrix_closure_recomputes_acceptance_from_authoritative_summary():
    cells = [
        {
            **cell,
            "accepted": False,
            **_authoritative_pass_evidence(
                particle_count=cell["particle_count"], seed=cell["seed"]
            ),
        }
        for cell in matrix.static_hold_cells()
    ]

    assert matrix.real_beaker_static_hold_closed(cells) is True
    assert matrix.all_required_1024_accepted(cells) is True


def test_matrix_closure_rejects_out_of_order_canonical_cells():
    cells = [
        {
            **cell,
            **_authoritative_pass_evidence(
                particle_count=cell["particle_count"], seed=cell["seed"]
            ),
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
    particle_count = int(argv[argv.index("--controlled-spawn-count") + 1])
    seed = int(argv[argv.index("--controlled-spawn-seed") + 1])
    physics_settings = {
        "strict_timestep_verified": True,
        "time_steps_per_second": 600,
        "effective_physics_dt": 1.0 / 600.0,
    }
    stage_unit_contract = {
        "effective_meters_per_unit": 1.0,
        "effective_kilograms_per_unit": 1.0,
        "meters_per_unit_authored": True,
        "kilograms_per_unit_authored": True,
        "strict_si_units_verified": True,
        "numeric_geometry_invariant": True,
        "density_contract": {
            "material_density_kg_m3": 1000.0,
            "particle_density_kg_m3": 1000.0,
            "particle_mass_kg": 0.0,
            "strict_si_density_verified": True,
        },
    }
    collision_offsets = {
        "contact_offset": 0.001058508,
        "rest_offset": 0.000594,
        "particle_contact_offset": 0.000705672,
        "solid_rest_offset": 0.000594,
        "fluid_rest_offset": 0.000352836,
    }
    physical_authoring_identity = runner.build_strict_physical_authoring_identity(
        source_usd_sha256="a" * 64,
        runner_script_sha256="b" * 64,
        isaacsim_version="4.1.0.0",
        particle_count=particle_count,
        seed=seed,
        spawn_positions_sha256="c" * 64,
        logical_dt=1.0 / 60.0,
        integration_dt=1.0 / 600.0,
        substeps_per_logical_step=10,
        stage_unit_contract=stage_unit_contract,
        particle_system_collision_offsets=collision_offsets,
        canonical_wrapper_summary={"enabled": True, "collider_count": 145},
        physics_settings=physics_settings,
    )
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
                "strict_physics_execution": {
                    "requested_logical_steps": 600,
                    "executed_logical_steps": 600,
                    "requested_integration_steps": 6000,
                    "executed_integration_steps": 6000,
                    "logical_dt": 1.0 / 60.0,
                    "integration_dt": 1.0 / 600.0,
                    "substeps_per_logical_step": 10,
                    "simulated_seconds": 10.0,
                    "simulate_fetch_pair_count": 6000,
                    "ordered_lifecycle_verified": True,
                    "lifecycle_event_count": 12604,
                    "lifecycle_event_sha256": "d" * 64,
                    "exact_logical_step_count_verified": True,
                    "exact_integration_step_count_verified": True,
                    "exact_step_count_verified": True,
                    "stage_id": 1234,
                    "attach_verified": True,
                    "detach_verified": True,
                    "render_updates_advance_physics": False,
                    "render_invariance_checks": 2,
                },
                "physics_settings": physics_settings,
                "stage_unit_contract": stage_unit_contract,
                "authored_runtime_paths": {
                    "particle_system_collision_offsets": collision_offsets
                },
                "physical_authoring_identity": physical_authoring_identity,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return matrix.ChildResult(returncode=returncode, timed_out=False)


@pytest.fixture
def fake_matrix_isaac41_runtime(monkeypatch):
    contract = {
        "bootstrap_mode": "test_isaacsim41",
        "isaacsim_version": "4.1.0.0",
        "expected_usd_version": "0.22.11",
    }
    preflight = {
        "usd_version": "0.22.11",
        "validated_against_isaacsim_version": "4.1.0.0",
    }
    monkeypatch.setattr(matrix, "resolve_isaac_usd_runtime", lambda: contract)
    monkeypatch.setattr(
        matrix,
        "preflight_isaac_usd_runtime",
        lambda _env, _contract: preflight,
    )
    monkeypatch.setattr(matrix, "_isaac_version", lambda: "isaacsim=4.1.0.0")


def test_matrix_runs_all_1024_seeds_but_blocks_4096_after_failure(
    tmp_path, monkeypatch, fake_matrix_isaac41_runtime
):
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


def test_matrix_mocked_children_require_summary_pass_not_returncode(
    tmp_path, monkeypatch, fake_matrix_isaac41_runtime
):
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


def test_matrix_rejects_authoritative_pass_with_nonzero_returncode(
    tmp_path, monkeypatch, fake_matrix_isaac41_runtime
):
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

    assert manifest["real_beaker_static_hold_closed"] is False
    assert manifest["cells"][0]["accepted"] is False
    assert manifest["cells"][0]["returncode"] == 7
    assert manifest["cells"][0]["returncode_warning"] is not None


def test_matrix_mocked_six_passes_close_and_hash_artifacts(
    tmp_path, monkeypatch, fake_matrix_isaac41_runtime
):
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


def test_runtime_preserves_primary_traceback_when_strict_cleanup_fails(
    tmp_path, monkeypatch
):
    class FakeApp:
        def close(self):
            pytest.fail("skip-app-close contract was ignored")

    fake_isaacsim = types.ModuleType("isaacsim")
    fake_isaacsim.SimulationApp = lambda _config: FakeApp()
    monkeypatch.setitem(sys.modules, "isaacsim", fake_isaacsim)
    monkeypatch.setattr(runner, "validate_presentation_look_cli", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "validate_real_beaker_static_hold_args", lambda _args: None)
    monkeypatch.setattr(runner, "_capture_kit_log_cursor", lambda: None)
    monkeypatch.setattr(
        runner,
        "_native_stage_runtime",
        lambda _args: (_ for _ in ()).throw(ValueError("primary_failure")),
    )
    monkeypatch.setattr(
        runner,
        "_detach_strict_physics_stepper",
        lambda _args: (_ for _ in ()).throw(RuntimeError("cleanup_failure")),
    )
    monkeypatch.setattr(runner, "_latest_isaac_log_summary", lambda: {})
    args = runner.build_arg_parser().parse_args(
        [
            "--out-dir",
            str(tmp_path / "out"),
            "--manifest",
            str(tmp_path / "summary.json"),
            "--skip-app-close",
        ]
    )

    summary = runner._run_runtime(args)

    fatal = summary["fatal_error"]
    assert "ValueError: primary_failure" in fatal["traceback"]
    assert "RuntimeError: cleanup_failure" not in fatal["traceback"]
    assert fatal["strict_physics_cleanup_error"] == {
        "type": "RuntimeError",
        "message": "cleanup_failure",
    }


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
    def fixture_positions(*, settled):
        positions = []
        for index in range(256):
            x_index = index % 16
            y_index = (index // 16) % 16
            scale = 0.0012 if settled else 0.0008
            positions.append(
                [
                    0.3 + (x_index - 7.5) * scale,
                    0.1 + (y_index - 7.5) * scale,
                    (0.823 if settled else 0.838) + (index % 4) * 0.0005,
                ]
            )
        return positions

    records = [
        {
            "step_index": 0,
            "particle_count": 256,
            "positions": fixture_positions(settled=False),
        },
        {
            "step_index": 10,
            "particle_count": 256,
            "positions": fixture_positions(settled=True),
        },
    ]
    identity = validate_strict_trace_schema(
        records,
        requested_count=256,
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
        "selected_particle_count": 256,
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
            "--accepted-matrix-manifest",
            str(tmp_path / "accepted_matrix.json"),
            "--out-root",
            str(tmp_path / "renders"),
            *extra,
        ]
    )


def test_replay_accepts_exact_archived_diagnostic_segment_when_kit_log_rotated(
    tmp_path,
):
    summary_path, summary, _records = _write_accepted_replay_input(tmp_path)
    archive = tmp_path / "strict_kit_log_segment.bin"
    archive.write_bytes(b"clean run segment")
    Path(summary["strict_kit_log_segment"]["log_path"]).unlink()

    accepted = replay.load_and_validate_accepted_replay(
        summary_path,
        diagnostic_segment_archive=archive,
    )

    provenance = accepted.diagnostic_segment_provenance
    assert provenance["source_mode"] == "explicit_archive_override"
    assert provenance["archive_path"] == str(archive.resolve())
    assert provenance["segment_sha256"] == hashlib.sha256(
        b"clean run segment"
    ).hexdigest()
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_bytes(b"matrix")
    verified = replay.verify_replay_input_snapshots_unchanged(
        accepted,
        {
            "matrix_manifest_path": str(matrix_path),
            "matrix_manifest_sha256": hashlib.sha256(b"matrix").hexdigest(),
        },
    )
    assert verified["verified_sha256"]["accepted_diagnostic_segment_archive"] == (
        provenance["segment_sha256"]
    )


def test_replay_rejects_diagnostic_archive_with_wrong_declared_bytes(tmp_path):
    summary_path, summary, _records = _write_accepted_replay_input(tmp_path)
    archive = tmp_path / "strict_kit_log_segment.bin"
    archive.write_bytes(b"wrong segment")
    Path(summary["strict_kit_log_segment"]["log_path"]).unlink()

    with pytest.raises(ValueError, match="diagnostic_segment_sha256_mismatch"):
        replay.load_and_validate_accepted_replay(
            summary_path,
            diagnostic_segment_archive=archive,
        )


def test_replay_argv_requires_accepted_trace_and_five_candidates(tmp_path):
    args = _replay_args(tmp_path, tmp_path / "summary.json")

    assert args.accepted_summary.endswith("summary.json")
    assert args.accepted_matrix_manifest.endswith("accepted_matrix.json")
    assert args.candidates == (
        "OMNI_REF_FINE,OMNI_REF_RATIO_15,OMNI_REF_RATIO_12,"
        "OMNI_REF_SURFACE,OMNI_REF_DISPLAY_FILL"
    )


def test_execution_provenance_binds_code_argv_runtime_and_git_state(tmp_path):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    args = _replay_args(
        tmp_path,
        summary_path,
        "--width",
        "320",
        "--height",
        "180",
        "--video-fps",
        "12",
    )
    args._execution_argv = [
        str(Path(replay.__file__).resolve()),
        "--accepted-summary",
        str(summary_path),
    ]

    provenance = replay.build_execution_provenance(args)
    control_look = replay.build_effective_replay_look_contract()

    assert provenance["argv"] == args._execution_argv
    assert provenance["render_parameters"] == {
        "width": 320,
        "height": 180,
        "video_fps": 12.0,
        "warmup_updates": 8,
        "camera_warmup_updates": 8,
        "headless": False,
        "candidates": list(replay.REFERENCE_CANDIDATE_IDS),
        "visual_prototype_display_fill_only": False,
        "lighting_variant_id": "C_CONTROL",
        "effective_replay_look_contract_sha256": control_look[
            "effective_replay_look_contract_sha256"
        ],
    }
    assert provenance["source_file_sha256"][str(Path(replay.__file__).resolve())] == (
        _sha256_path(Path(replay.__file__))
    )
    assert provenance["source_file_sha256"][
        str((Path(replay.__file__).parent / "omniglass_reference.py").resolve())
    ] == _sha256_path(Path(replay.__file__).parent / "omniglass_reference.py")
    assert str(
        (Path(replay.__file__).parent / "run_colleague_liquid_usd_leak_smoke.py").resolve()
    ) in provenance["source_file_sha256"]
    assert len(provenance["git"]["head_commit"]) == 40
    assert len(provenance["git"]["porcelain_v1_z_sha256"]) == 64
    payload = dict(provenance)
    digest = payload.pop("provenance_sha256")
    assert digest == replay._json_sha256(payload)
    verification = replay.verify_execution_provenance_sources_unchanged(provenance)
    assert verification["verified"] is True
    assert verification["verified_file_count"] == len(
        provenance["source_file_sha256"]
    )
    assert verification["source_file_set_unchanged"] is True


def test_execution_provenance_source_verification_detects_midrun_change(tmp_path):
    source = tmp_path / "runtime_helper.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    provenance = {
        "source_file_sha256": {str(source.resolve()): _sha256_path(source)}
    }

    assert replay.verify_execution_provenance_sources_unchanged(provenance)[
        "verified"
    ] is True
    source.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="execution_source_file_changed"):
        replay.verify_execution_provenance_sources_unchanged(provenance)


def test_execution_provenance_source_verification_detects_added_python_file(tmp_path):
    source = tmp_path / "runtime_helper.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    provenance = {
        "source_file_set_policy": (
            "all_non_symlink_python_files_in_tools/labutopia_fluid_at_start"
        ),
        "source_directory": str(tmp_path.resolve()),
        "source_file_sha256": {str(source.resolve()): _sha256_path(source)},
    }

    assert replay.verify_execution_provenance_sources_unchanged(provenance)[
        "source_file_set_unchanged"
    ] is True
    (tmp_path / "added.py").write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="execution_source_file_set_changed"):
        replay.verify_execution_provenance_sources_unchanged(provenance)


def test_replay_input_selector_requires_complete_authority_mode():
    args = replay.build_arg_parser().parse_args(
        ["--accepted-summary", "summary.json"]
    )
    with pytest.raises(ValueError, match="replay_authority_input_missing"):
        replay.load_replay_inputs_from_args(args, recompute_closure=False)


def test_finalize_preclose_manifest_requires_zero_child_exit_and_source_stability(
    tmp_path,
):
    source = tmp_path / "runtime.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    out_root = tmp_path / "run"
    out_root.mkdir()
    preclose_path = out_root / "replay_preclose_manifest.json"
    custom_manifest = tmp_path / "custom" / "manifest.json"
    effective_look = replay.build_effective_replay_look_contract()
    preclose = {
        "classification": "RENDER_COMPLETE_PENDING_APPLICATION_CLOSE",
        "lighting_variant_id": effective_look["lighting_variant_id"],
        "effective_replay_look_contract": effective_look,
        "effective_replay_look_contract_sha256": effective_look[
            "effective_replay_look_contract_sha256"
        ],
        "candidate_manifests": {
            "OMNI_REF_FINE": {
                "lighting_variant_id": effective_look[
                    "lighting_variant_id"
                ],
                "effective_replay_look_contract": effective_look,
                "effective_replay_look_contract_sha256": effective_look[
                    "effective_replay_look_contract_sha256"
                ],
            }
        },
        "execution_provenance": {
            "source_file_sha256": {
                str(source.resolve()): _sha256_path(source)
            }
        },
        "runtime_contract": {"application_close_status": "PENDING"},
        "standalone_final_evidence_authority": False,
        "execution_source_end_verification_status": (
            "PENDING_CHILD_PROCESS_EXIT"
        ),
    }
    replay.atomic_write_json(preclose_path, preclose)

    finalized = replay.finalize_preclose_manifest_after_child_exit(
        preclose_path,
        child_exit_code=0,
        manifest_path=custom_manifest,
    )

    assert finalized["classification"] == (
        "RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
    )
    assert finalized["runtime_contract"]["application_close_status"] == (
        "PASS_CHILD_PROCESS_EXIT_ZERO_AFTER_SIMULATION_APP_CLOSE"
    )
    assert finalized["standalone_final_evidence_authority"] is True
    assert finalized["execution_source_end_verification_status"] == "PASS"
    assert finalized["effective_replay_look_contract"] == effective_look
    assert finalized["effective_replay_look_consistency_validation"][
        "validated"
    ] is True
    assert json.loads((out_root / "replay_manifest.json").read_text()) == finalized
    assert json.loads(custom_manifest.read_text()) == finalized

    with pytest.raises(ValueError, match="child_process_exit_nonzero"):
        replay.finalize_preclose_manifest_after_child_exit(
            preclose_path,
            child_exit_code=2,
            manifest_path=custom_manifest,
        )


def _write_replay_matrix_gate_fixture(tmp_path, *, selected_count=4096):
    source_path = tmp_path / "source.usda"
    summary_path = tmp_path / "runtime_smoke_summary.json"
    trace_path = tmp_path / "particle_readback_trace.jsonl"
    source_path.write_text("#usda 1.0\n", encoding="utf-8")
    summary_path.write_text("{}\n", encoding="utf-8")
    trace_path.write_text("{}\n", encoding="utf-8")
    source_hash = _sha256_path(source_path)
    physical_trace_identity = {
        "source_usd_sha256": source_hash,
        "particle_count": selected_count,
        "seed": 0,
        "steps": 600,
        "trace_interval": 30,
        "frame_indices": [0, 600],
        "frame_particle_counts": [selected_count, selected_count],
        "frame_count": 2,
        "positions_sha256": "a" * 64,
        "physical_trace_sha256": "b" * 64,
    }
    accepted = types.SimpleNamespace(
        source_usd_path=source_path.resolve(),
        summary_path=summary_path.resolve(),
        trace_path=trace_path.resolve(),
        source_usd_sha256=source_hash,
        summary_sha256=_sha256_path(summary_path),
        trace_sha256=_sha256_path(trace_path),
        physical_trace_identity=physical_trace_identity,
    )
    runner_hash = "c" * 64
    cells = []
    for cell in matrix.static_hold_cells():
        is_selected = cell["particle_count"] == selected_count and cell["seed"] == 0
        cells.append(
            {
                **cell,
                "returncode": 0,
                "classification": "PASS_VISIBLE_BEAKER_STATIC_HOLD",
                "visible_beaker_containment_verified": True,
                "summary_path": str(
                    summary_path.resolve()
                    if is_selected
                    else (tmp_path / f"{cell['cell_id']}_summary.json").resolve()
                ),
                "trace_path": str(
                    trace_path.resolve()
                    if is_selected
                    else (tmp_path / f"{cell['cell_id']}_trace.jsonl").resolve()
                ),
                "physical_trace_identity": (
                    physical_trace_identity
                    if is_selected
                    else {
                        **physical_trace_identity,
                        "particle_count": cell["particle_count"],
                        "seed": cell["seed"],
                    }
                ),
                "physical_authoring_identity": {
                    "source_usd_sha256": source_hash,
                    "runner_script_sha256": runner_hash,
                },
            }
        )
    matrix_manifest = {
        "schema_version": 1,
        "manifest_type": "fluid_spike_real_beaker_static_hold_matrix",
        "real_beaker_static_hold_closed": True,
        "run_identity": {
            "source_usd_path": str(source_path.resolve()),
            "source_usd_sha256": source_hash,
            "child_script_sha256": runner_hash,
        },
        "cells": cells,
    }
    matrix_path = tmp_path / "accepted_matrix.json"
    matrix_path.write_text(json.dumps(matrix_manifest), encoding="utf-8")
    return matrix_path, accepted, matrix_manifest


def test_replay_matrix_gate_recomputes_closure_and_binds_selected_4096_cell(
    tmp_path, monkeypatch
):
    matrix_path, accepted, matrix_manifest = _write_replay_matrix_gate_fixture(tmp_path)
    closure_calls = []

    def closed(cells):
        closure_calls.append(cells)
        return True

    monkeypatch.setattr(matrix, "real_beaker_static_hold_closed", closed)

    contract = replay.validate_authoritative_matrix_replay_input(
        matrix_path,
        accepted=accepted,
    )

    assert closure_calls == [matrix_manifest["cells"]]
    assert contract["matrix_closure_recomputed"] is True
    assert contract["selected_cell_id"] == "P4096_S0"
    assert contract["selected_particle_count"] == 4096
    assert contract["selected_seed"] == 0
    assert contract["accepted_summary_sha256"] == accepted.summary_sha256
    assert contract["accepted_trace_sha256"] == accepted.trace_sha256
    assert contract["accepted_source_usd_sha256"] == accepted.source_usd_sha256
    assert contract["matrix_manifest_sha256"] == _sha256_path(matrix_path)


def test_replay_matrix_preflight_binds_bytes_without_pxr_geometry_import(
    tmp_path, monkeypatch
):
    matrix_path, accepted, _matrix_manifest = _write_replay_matrix_gate_fixture(
        tmp_path
    )
    monkeypatch.setattr(
        matrix,
        "real_beaker_static_hold_closed",
        lambda _cells: pytest.fail("geometry closure ran before SimulationApp"),
    )

    contract = replay.validate_authoritative_matrix_replay_input(
        matrix_path,
        accepted=accepted,
        recompute_closure=False,
    )

    assert contract["matrix_closure_declared"] is True
    assert contract["matrix_closure_recomputed"] is False
    assert contract["selected_cell_id"] == "P4096_S0"


def test_replay_matrix_gate_rejects_summary_not_declared_by_closed_matrix(
    tmp_path, monkeypatch
):
    matrix_path, accepted, matrix_manifest = _write_replay_matrix_gate_fixture(tmp_path)
    matrix_manifest["cells"][3]["summary_path"] = str(
        (tmp_path / "different_summary.json").resolve()
    )
    matrix_path.write_text(json.dumps(matrix_manifest), encoding="utf-8")
    monkeypatch.setattr(matrix, "real_beaker_static_hold_closed", lambda _cells: True)

    with pytest.raises(ValueError, match="accepted_summary_not_unique_matrix_member"):
        replay.validate_authoritative_matrix_replay_input(
            matrix_path,
            accepted=accepted,
        )


def test_replay_matrix_gate_uses_accepted_4096_member_when_matrix_is_closed(
    tmp_path, monkeypatch
):
    matrix_path, accepted, _manifest = _write_replay_matrix_gate_fixture(
        tmp_path,
        selected_count=1024,
    )
    monkeypatch.setattr(matrix, "real_beaker_static_hold_closed", lambda _cells: True)

    with pytest.raises(ValueError, match="accepted_4096_matrix_member_required"):
        replay.validate_authoritative_matrix_replay_input(
            matrix_path,
            accepted=accepted,
        )


def test_replay_camera_capture_failure_preserves_sensor_diagnostics():
    message = replay.camera_capture_failure_message(
        candidate_id="OMNI_REF_FINE",
        role="context",
        frame_index=0,
        diagnostics={"status": "invalid_shape", "shape": [], "dtype": "object"},
    )

    assert message.startswith(
        "omniglass_replay_image_capture_failed:OMNI_REF_FINE:context:0:"
    )
    assert '"status":"invalid_shape"' in message
    assert '"shape":[]' in message


def test_replay_viewport_capture_writes_nonflat_frame_without_timeline_advance(
    tmp_path,
):
    from PIL import Image

    output = tmp_path / "frame.png"

    class Viewport:
        camera_path = None
        resolution = None
        resolution_scale = None

        def get_render_product_path(self):
            return "/Render/Product"

    class Timeline:
        def is_playing(self):
            return False

        def get_current_time(self):
            return 2.5

    class App:
        def __init__(self):
            self.update_count = 0

        def update(self):
            self.update_count += 1

    class Capture:
        def __init__(self):
            self.paths = []
            self.wait_count = 0

        def capture_to_file(self, viewport, *, file_path):
            assert viewport.get_render_product_path() == "/Render/Product"
            self.paths.append(file_path)
            image = Image.new("RGB", (4, 2))
            image.putdata(
                [
                    (0, 0, 0),
                    (255, 255, 255),
                    (255, 0, 0),
                    (0, 255, 0),
                    (0, 0, 255),
                    (255, 255, 0),
                    (0, 255, 255),
                    (255, 0, 255),
                ]
            )
            image.save(file_path)
            return object()

        def wait_async_capture(self):
            self.wait_count += 1

    viewport = Viewport()
    timeline = Timeline()
    app = App()
    capture = Capture()

    contract = replay.capture_static_viewport_png(
        viewport=viewport,
        capture_interface=capture,
        capture_to_file=capture.capture_to_file,
        app=app,
        timeline=timeline,
        camera_path="/World/Camera1",
        output_path=output,
        width=4,
        height=2,
        settle_updates=2,
    )

    assert viewport.camera_path == "/World/Camera1"
    assert viewport.resolution == (4, 2)
    assert viewport.resolution_scale == 1
    assert capture.paths == [str(output)]
    assert capture.wait_count == 1
    assert app.update_count == 4
    assert contract["status"] == "saved_static_viewport_rgb"
    assert contract["timeline_advanced"] is False
    assert contract["shape"] == [2, 4, 3]


def test_replay_camera_policy_uses_measured_pair_context_and_oblique_beaker_closeup():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    context = UsdGeom.Camera.Define(stage, "/World/Camera1")
    context.CreateFocalLengthAttr(5.0)
    pair = UsdGeom.Camera.Define(stage, "/World/BeakerPairContextCamera")
    pair.CreateFocalLengthAttr(28.0)
    closeup = UsdGeom.Camera.Define(
        stage, "/World/Beaker2CloseupNativeMaterialCamera"
    )
    closeup.CreateFocalLengthAttr(20.0)

    context_info, closeup_info = replay.apply_replay_camera_policy(
        stage,
        pair_context_info={
            "camera_path": "/World/BeakerPairContextCamera",
            "eye": [1.0, -0.1, 1.3],
            "target": [0.3, -0.1, 0.84],
            "up": [0.0, 0.0, 1.0],
            "focal_length": 28.0,
        },
        closeup_info={
            "camera_path": "/World/Beaker2CloseupNativeMaterialCamera",
            "eye": [0.5, -0.2, 1.0],
            "target": [0.3, 0.1, 0.86],
            "up": [0.0, 0.0, 1.0],
            "focal_length": 45.0,
        },
    )

    assert context_info["camera_path"] == "/World/BeakerPairContextCamera"
    assert context_info["camera_source"] == "measured_beaker_pair_context"
    assert context_info["focal_length"] == 28.0
    assert context_info["native_provenance_camera"] == {
        "camera_path": "/World/Camera1",
        "camera_source": "native_tabletop_camera",
        "focal_length": 5.0,
    }
    assert closeup_info["camera_source"] == "measured_source_beaker_closeup"
    assert closeup_info["focal_length"] == 45.0
    assert closeup.GetFocalLengthAttr().Get() == 45.0


def test_replay_closeup_camera_targets_measured_cup_center_and_fits_measured_size():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
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

    camera_info = replay.define_measured_beaker_closeup_camera(stage, frame=frame)

    camera = UsdGeom.Camera(stage.GetPrimAtPath(camera_info["camera_path"]))
    assert camera_info["target"] == pytest.approx([0.3, 0.1, 0.865])
    assert camera_info["eye"] == pytest.approx(
        [0.4928363, -0.1298133, 1.0048923], abs=1e-6
    )
    assert camera_info["measured_outer_diameter"] == pytest.approx(0.075)
    assert camera_info["measured_height"] == pytest.approx(0.09)
    assert camera_info["focal_length"] == pytest.approx(32.0)
    assert camera_info["view_elevation_degrees"] == pytest.approx(25.0, abs=0.1)
    assert camera_info["degrees_off_cup_axis"] == pytest.approx(65.0, abs=0.1)
    assert camera_info["base_table_contact_visible_intent"] is True
    assert camera_info["liquid_depth_visible_intent"] is True
    assert camera.GetFocalLengthAttr().Get() == pytest.approx(
        camera_info["focal_length"]
    )
    projection = camera_info["projection_contract"]
    assert projection["resolution"] == [960, 540]
    assert projection["complete_beaker_bounds_projected"] is True
    assert projection["table_surround_projected"] is True
    assert projection["all_required_points_in_frame"] is True
    assert projection["minimum_ndc_margin"] >= 0.05


def test_replay_pair_context_camera_is_measured_from_both_cups_and_table():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    region = {
        "source_center": [0.31, 0.09, 0.86],
        "target_center": [0.28, -0.22, 0.86],
        "source_radius": 0.055,
        "target_radius": 0.077,
        "table_z": 0.773,
        "source_height": 0.20,
        "target_height": 0.23,
    }

    info = replay.define_measured_pair_context_camera(stage, region_config=region)

    assert info["camera_path"] == "/World/BeakerPairContextCamera"
    assert info["camera_source"] == "measured_beaker_pair_context"
    assert info["target"] == pytest.approx([0.295, -0.065, 0.823])
    assert info["eye"] == pytest.approx([0.915, -0.185, 1.123])
    assert info["focal_length"] == pytest.approx(25.5)
    assert info["pair_span_with_radii"] > 0.44
    assert 0.7 <= info["projected_pair_occupancy"] <= 0.85
    assert info["base_table_contact_visible_intent"] is True
    assert info["both_complete_cup_bounds_required"] is True
    projection = info["projection_contract"]
    assert projection["resolution"] == [960, 540]
    assert projection["both_complete_cup_bounds_projected"] is True
    assert projection["base_surround_points_projected"] is True
    assert projection["all_required_points_in_frame"] is True
    assert projection["minimum_ndc_margin"] >= 0.05


def test_replay_camera_contracts_preflight_without_authoring_stage():
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
    region = {
        "source_center": [0.31, 0.09, 0.86],
        "target_center": [0.28, -0.22, 0.86],
        "source_radius": 0.055,
        "target_radius": 0.077,
        "source_height": 0.20,
        "target_height": 0.23,
        "table_z": 0.773,
    }

    contracts = replay.build_replay_camera_contracts(
        frame=frame,
        region_config=region,
        width=960,
        height=540,
    )

    assert set(contracts) == {"source_beaker_closeup", "context"}
    assert contracts["source_beaker_closeup"]["projection_contract"][
        "all_required_points_in_frame"
    ] is True
    assert contracts["context"]["projection_contract"][
        "all_required_points_in_frame"
    ] is True
    assert all(len(contract["camera_contract_sha256"]) == 64 for contract in contracts.values())


def test_replay_capture_writes_three_cameras_without_default_time_attr_change(
    tmp_path,
):
    context_path = tmp_path / "context.png"
    closeup_path = tmp_path / "closeup.png"

    class Timeline:
        def is_playing(self):
            return False

        def get_current_time(self):
            return 0.0

    class Orchestrator:
        def __init__(self):
            self.step_calls = []
            self.wait_count = 0

        def step(self, **kwargs):
            self.step_calls.append(kwargs)

        def wait_until_complete(self):
            self.wait_count += 1

    class Annotator:
        def __init__(self, pixels):
            self.pixels = pixels

        def get_data(self):
            return self.pixels

    pixels = [
        [[0, 0, 0, 255], [255, 255, 255, 255]],
        [[255, 0, 0, 255], [0, 255, 0, 255]],
    ]
    orchestrator = Orchestrator()
    hashes = iter(["stable", "stable"])

    contract = replay.capture_static_replicator_rgbs(
        orchestrator=orchestrator,
        timeline=Timeline(),
        annotators={
            "context": Annotator(pixels),
            "source_beaker_closeup": Annotator(pixels),
            "native_table_context": Annotator(pixels),
        },
        output_paths={
            "context": context_path,
            "source_beaker_closeup": closeup_path,
            "native_table_context": tmp_path / "native.png",
        },
        width=2,
        height=2,
        rt_subframes=1,
        observed_default_time_usd_point_attributes_hash=lambda: next(hashes),
    )

    assert context_path.is_file()
    assert closeup_path.is_file()
    assert orchestrator.step_calls == [
        {"rt_subframes": 1, "pause_timeline": True, "delta_time": 0.0}
    ]
    assert orchestrator.wait_count == 1
    assert contract["timeline_advanced"] is False
    assert contract["observed_default_time_usd_point_attributes_changed"] is False
    assert contract["replicator_orchestrator_steps_executed"] == 1
    assert contract["replicator_delta_time"] == 0.0
    assert contract["physics_step_count_instrumented"] is False
    assert contract["physics_steps_executed"] is None
    assert contract["frames"]["context"]["shape"] == [2, 2, 4]


def test_replay_capture_rejects_observed_default_time_usd_point_attribute_change(
    tmp_path,
):
    class Timeline:
        def is_playing(self):
            return False

        def get_current_time(self):
            return 0.0

    class Orchestrator:
        def step(self, **_kwargs):
            pass

        def wait_until_complete(self):
            pass

    hashes = iter(["before", "after"])

    with pytest.raises(
        RuntimeError,
        match="static_render_changed_observed_default_time_usd_point_attributes",
    ):
        replay.capture_static_replicator_rgbs(
            orchestrator=Orchestrator(),
            timeline=Timeline(),
            annotators={},
            output_paths={},
            width=2,
            height=2,
            rt_subframes=1,
            observed_default_time_usd_point_attributes_hash=lambda: next(hashes),
        )


def test_replay_capture_resource_creation_cleans_all_products_on_third_attach_failure():
    products = []

    class RenderProduct:
        def __init__(self, role):
            self.role = role
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    class Create:
        @staticmethod
        def render_product(camera_path, _resolution):
            product = RenderProduct(camera_path)
            products.append(product)
            return product

    class Annotator:
        def __init__(self, should_fail):
            self.should_fail = should_fail
            self.attached = False
            self.detach_called = False

        def attach(self, _render_product):
            if self.should_fail:
                raise RuntimeError("third attach failed")
            self.attached = True

        def detach(self, _render_products=None):
            self.detach_called = True
            self.attached = False

    class Registry:
        calls = 0
        annotators = []

        @classmethod
        def get_annotator(cls, _name):
            cls.calls += 1
            annotator = Annotator(should_fail=cls.calls == 3)
            cls.annotators.append(annotator)
            return annotator

    rep = types.SimpleNamespace(create=Create(), AnnotatorRegistry=Registry)
    cameras = {
        "context": {"camera_path": "/World/Context"},
        "source_beaker_closeup": {"camera_path": "/World/Closeup"},
        "native_table_context": {"camera_path": "/World/Camera1"},
    }

    with pytest.raises(RuntimeError, match="third attach failed") as error:
        replay.create_replicator_capture_resources(
            rep,
            cameras=cameras,
            resolution=(960, 540),
        )

    assert len(products) == 3
    assert all(product.destroyed for product in products)
    assert error.value.cleanup_contract["cleanup_complete"] is True
    assert error.value.cleanup_contract["detached_roles"] == [
        "context",
        "native_table_context",
        "source_beaker_closeup",
    ]
    assert error.value.cleanup_contract["detach_not_applicable_roles"] == []
    assert all(annotator.detach_called for annotator in Registry.annotators)
    assert error.value.cleanup_contract["destroyed_roles"] == [
        "context",
        "native_table_context",
        "source_beaker_closeup",
    ]


def test_replay_static_render_preparation_removes_legacy_sampler_and_graph(tmp_path):
    calls = []
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    UsdGeom.Xform.Define(source_stage, "/World/fluid")
    sampler = UsdGeom.Xform.Define(source_stage, "/World/fluid/Cylinder").GetPrim()
    particle_set = UsdGeom.Points.Define(
        source_stage, runner.EVIDENCE_PARTICLE_SET_PATH
    ).GetPrim()
    particle_system = UsdGeom.Xform.Define(
        source_stage, runner.EVIDENCE_PARTICLE_SYSTEM_PATH
    ).GetPrim()
    sampler.CreateRelationship("physxParticleSampling:particles").SetTargets(
        [Sdf.Path(runner.EVIDENCE_PARTICLE_SET_PATH)]
    )
    particle_set.CreateRelationship("physxParticle:particleSystem").SetTargets(
        [Sdf.Path(runner.EVIDENCE_PARTICLE_SYSTEM_PATH)]
    )
    particle_system.CreateAttribute(
        "particleSystemEnabled", Sdf.ValueTypeNames.Bool
    ).Set(True)
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    presentation = replay.begin_candidate_presentation_layer(
        stage, tmp_path / "presentation.usda"
    )

    class Native:
        @staticmethod
        def remove_legacy_particle_sampling_api(stage, *, execute_command):
            calls.append(("remove", stage, execute_command))
            return {"verified": True, "api_present_after": False}

    execute = object()

    contract = replay.prepare_static_render_physics_graph(
        stage,
        native=Native,
        execute_command=execute,
    )

    assert calls == [("remove", stage, execute)]
    assert stage.GetEditTarget().GetLayer().identifier == presentation.identifier
    assert stage.GetRootLayer().dirty is False
    assert stage.GetPrimAtPath("/World/fluid/Cylinder").GetRelationship(
        "physxParticleSampling:particles"
    ).GetTargets() == []
    assert stage.GetPrimAtPath(runner.EVIDENCE_PARTICLE_SET_PATH).GetRelationship(
        "physxParticle:particleSystem"
    ).GetTargets() == []
    assert contract["legacy_particle_sampling_removed"] is True
    assert contract["source_particle_graph_deactivated"] is True


def test_replay_capture_resource_cleanup_detaches_annotators_then_destroys_products():
    events = []

    class Annotator:
        def detach(self, render_products=None):
            events.append(("detach", render_products))

    class RenderProduct:
        destroyed = False

        def destroy(self):
            events.append(("destroy", self))
            self.destroyed = True

    render_product = RenderProduct()
    contract = replay.destroy_replicator_capture_resources(
        {
            "context": {
                "annotator": Annotator(),
                "render_product": render_product,
            }
        }
    )

    assert render_product.destroyed is True
    assert contract["cleanup_complete"] is True
    assert contract["cleanup_failures"] == {}
    assert contract["detached_roles"] == ["context"]
    assert events == [
        ("detach", None),
        ("destroy", render_product),
    ]


def test_replay_capture_resource_cleanup_preserves_detach_failure_and_still_destroys():
    class Annotator:
        def detach(self, _render_products=None):
            raise RuntimeError("detach failed")

    class RenderProduct:
        destroyed = False

        def destroy(self):
            self.destroyed = True

    render_product = RenderProduct()
    contract = replay.destroy_replicator_capture_resources(
        {
            "context": {
                "annotator": Annotator(),
                "render_product": render_product,
            }
        }
    )

    assert render_product.destroyed is True
    assert contract["cleanup_complete"] is False
    assert "context:detach" in contract["cleanup_failures"]


def test_replay_capture_resource_cleanup_detaches_shared_annotator_once_before_destroy():
    events = []

    class Annotator:
        def detach(self, render_products=None):
            events.append(("detach", render_products))

    class RenderProduct:
        def __init__(self, role):
            self.role = role

        def destroy(self):
            events.append(("destroy", self.role))

    annotator = Annotator()
    resources = {
        role: {
            "annotator": annotator,
            "annotator_detach_required": True,
            "render_product": RenderProduct(role),
        }
        for role in replay.CAPTURE_CAMERA_ROLES
    }

    contract = replay.destroy_replicator_capture_resources(resources)

    assert contract["cleanup_complete"] is True
    assert contract["detached_roles"] == sorted(replay.CAPTURE_CAMERA_ROLES)
    assert events[0] == ("detach", None)
    assert [event[0] for event in events].count("detach") == 1
    assert all(event[0] == "destroy" for event in events[1:])


def test_replay_capture_resource_cleanup_failure_is_not_silently_accepted():
    class RenderProduct:
        def destroy(self):
            raise RuntimeError("destroy failed")

    contract = replay.destroy_replicator_capture_resources(
        {
            "context": {
                "render_product": RenderProduct(),
            }
        }
    )

    assert contract["cleanup_complete"] is False
    with pytest.raises(RuntimeError, match="replicator_resource_cleanup_failed"):
        replay.require_replicator_cleanup(contract)


def test_capture_frame_binding_binds_trace_proxy_and_three_images(tmp_path):
    frame_index = 30
    image_paths = {}
    for role in replay.CAPTURE_CAMERA_ROLES:
        path = tmp_path / role / f"frame_{frame_index:04d}.png"
        path.parent.mkdir()
        path.write_bytes(f"{role}-image".encode("ascii"))
        image_paths[role] = path
    record = {
        "step_index": frame_index,
        "particle_count": 2,
        "positions": [[0.0, 0.0, 0.0], [0.1, 0.0, 0.0]],
    }
    proxy_update = {
        "physical_trace_frame_index": frame_index,
        "proxy_geometry_sha256": "a" * 64,
        "presentation_primitive_path": replay.PRESENTATION_POINTS_PATH,
        "presentation_kind": "points",
        "canonical_mesh_sha256": None,
        "usd_geometry_binding": {
            "verified": True,
            "actual_usd_geometry_sha256": "a" * 64,
        },
        "usd_geometry_binding_after_capture": {
            "verified": True,
            "actual_usd_geometry_sha256": "a" * 64,
        },
    }

    binding = replay.build_capture_frame_binding(
        candidate_id="OMNI_REF_FINE",
        frame_offset=1,
        record=record,
        physical_trace_sha256="b" * 64,
        proxy_update=proxy_update,
        image_paths=image_paths,
    )

    assert binding["physical_trace_frame_index"] == frame_index
    assert binding["trace_record_sha256"] == replay._json_sha256(record)
    assert binding["source_positions_sha256"] == replay._json_sha256(
        record["positions"]
    )
    assert binding["proxy_geometry_sha256"] == "a" * 64
    assert binding["actual_usd_geometry_sha256"] == "a" * 64
    assert binding["actual_usd_geometry_sha256_after_capture"] == "a" * 64
    assert set(binding["image_sha256"]) == set(replay.CAPTURE_CAMERA_ROLES)
    assert len(binding["frame_binding_sha256"]) == 64


def test_capture_frame_binding_hash_binds_effective_look(tmp_path):
    frame_index = 30
    image_paths = {}
    for role in replay.CAPTURE_CAMERA_ROLES:
        path = tmp_path / role / f"frame_{frame_index:04d}.png"
        path.parent.mkdir()
        path.write_bytes(f"{role}-image".encode("ascii"))
        image_paths[role] = path
    record = {
        "step_index": frame_index,
        "particle_count": 1,
        "positions": [[0.0, 0.0, 0.0]],
    }
    proxy_update = {
        "physical_trace_frame_index": frame_index,
        "proxy_geometry_sha256": "a" * 64,
        "presentation_primitive_path": replay.PRESENTATION_POINTS_PATH,
        "presentation_kind": "points",
        "canonical_mesh_sha256": None,
        "usd_geometry_binding": {
            "verified": True,
            "actual_usd_geometry_sha256": "a" * 64,
        },
        "usd_geometry_binding_after_capture": {
            "verified": True,
            "actual_usd_geometry_sha256": "a" * 64,
        },
    }

    control = replay.build_capture_frame_binding(
        candidate_id="OMNI_REF_FINE",
        frame_offset=1,
        record=record,
        physical_trace_sha256="b" * 64,
        proxy_update=proxy_update,
        image_paths=image_paths,
        effective_look_contract=replay.build_effective_replay_look_contract(
            "C_CONTROL"
        ),
    )
    treatment = replay.build_capture_frame_binding(
        candidate_id="OMNI_REF_FINE",
        frame_offset=1,
        record=record,
        physical_trace_sha256="b" * 64,
        proxy_update=proxy_update,
        image_paths=image_paths,
        effective_look_contract=replay.build_effective_replay_look_contract(
            "B_LIGHTING"
        ),
    )

    assert control["lighting_variant_id"] == "C_CONTROL"
    assert treatment["lighting_variant_id"] == "B_LIGHTING"
    assert control["frame_binding_sha256"] != treatment["frame_binding_sha256"]
    assert treatment["effective_replay_look_contract_sha256"] == treatment[
        "effective_replay_look_contract"
    ]["effective_replay_look_contract_sha256"]


def test_capture_frame_binding_rejects_proxy_trace_index_mismatch(tmp_path):
    image_paths = {}
    for role in replay.CAPTURE_CAMERA_ROLES:
        path = tmp_path / role / "frame_0030.png"
        path.parent.mkdir()
        path.write_bytes(b"image")
        image_paths[role] = path

    with pytest.raises(ValueError, match="proxy_trace_frame_index_mismatch"):
        replay.build_capture_frame_binding(
            candidate_id="OMNI_REF_FINE",
            frame_offset=1,
            record={
                "step_index": 30,
                "particle_count": 1,
                "positions": [[0.0, 0.0, 0.0]],
            },
            physical_trace_sha256="b" * 64,
            proxy_update={
                "physical_trace_frame_index": 0,
                "proxy_geometry_sha256": "a" * 64,
                "presentation_primitive_path": replay.PRESENTATION_POINTS_PATH,
                "presentation_kind": "points",
                "canonical_mesh_sha256": None,
                "usd_geometry_binding": {
                    "verified": True,
                    "actual_usd_geometry_sha256": "a" * 64,
                },
                "usd_geometry_binding_after_capture": {
                    "verified": True,
                    "actual_usd_geometry_sha256": "a" * 64,
                },
            },
            image_paths=image_paths,
        )


def test_capture_frame_binding_artifact_recomputes_every_binding_and_image(tmp_path):
    trace_sha256 = "b" * 64
    bindings = []
    images_by_role = {role: [] for role in replay.CAPTURE_CAMERA_ROLES}
    for offset, frame_index in enumerate((0, 30)):
        frame_paths = {}
        for role in replay.CAPTURE_CAMERA_ROLES:
            path = tmp_path / role / f"frame_{frame_index:04d}.png"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(f"{role}-{frame_index}".encode("ascii"))
            frame_paths[role] = path
            images_by_role[role].append(path)
        bindings.append(
            replay.build_capture_frame_binding(
                candidate_id="OMNI_REF_FINE",
                frame_offset=offset,
                record={
                    "step_index": frame_index,
                    "particle_count": 1,
                    "positions": [[float(offset), 0.0, 0.0]],
                },
                physical_trace_sha256=trace_sha256,
                proxy_update={
                    "physical_trace_frame_index": frame_index,
                    "proxy_geometry_sha256": ("a" if offset == 0 else "c") * 64,
                    "presentation_primitive_path": replay.PRESENTATION_POINTS_PATH,
                    "presentation_kind": "points",
                    "canonical_mesh_sha256": None,
                    "usd_geometry_binding": {
                        "verified": True,
                        "actual_usd_geometry_sha256": (
                            "a" if offset == 0 else "c"
                        )
                        * 64,
                    },
                    "usd_geometry_binding_after_capture": {
                        "verified": True,
                        "actual_usd_geometry_sha256": (
                            "a" if offset == 0 else "c"
                        )
                        * 64,
                    },
                },
                image_paths=frame_paths,
            )
        )
    artifact_path = tmp_path / "capture_frame_bindings.json"
    control_look = replay.build_effective_replay_look_contract()
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_id": "OMNI_REF_FINE",
                "physical_trace_sha256": trace_sha256,
                "frame_indices": [0, 30],
                "lighting_variant_id": control_look["lighting_variant_id"],
                "effective_replay_look_contract": control_look,
                "effective_replay_look_contract_sha256": control_look[
                    "effective_replay_look_contract_sha256"
                ],
                "bindings": bindings,
                "bindings_sha256": replay._json_sha256(bindings),
            }
        ),
        encoding="utf-8",
    )

    validation = replay.validate_capture_frame_bindings_artifact(
        artifact_path,
        candidate_id="OMNI_REF_FINE",
        physical_trace_sha256=trace_sha256,
        frame_indices=[0, 30],
        image_paths_by_role=images_by_role,
        expected_frame_contracts=[
            {
                "frame_index": binding["physical_trace_frame_index"],
                "trace_record_sha256": binding["trace_record_sha256"],
                "source_positions_sha256": binding["source_positions_sha256"],
                "source_physical_point_count": binding[
                    "source_physical_point_count"
                ],
                "presentation_kind": binding["presentation_kind"],
                "proxy_geometry_sha256": binding["proxy_geometry_sha256"],
                "canonical_mesh_sha256": binding["canonical_mesh_sha256"],
            }
            for binding in bindings
        ],
    )

    assert validation["validated"] is True
    assert validation["binding_count"] == 2
    images_by_role["context"][0].write_bytes(b"mutated")
    with pytest.raises(ValueError, match="capture_binding_image_sha256_mismatch"):
        replay.validate_capture_frame_bindings_artifact(
            artifact_path,
            candidate_id="OMNI_REF_FINE",
            physical_trace_sha256=trace_sha256,
            frame_indices=[0, 30],
            image_paths_by_role=images_by_role,
            expected_frame_contracts=[
                {
                    "frame_index": binding["physical_trace_frame_index"],
                    "trace_record_sha256": binding["trace_record_sha256"],
                    "source_positions_sha256": binding[
                        "source_positions_sha256"
                    ],
                    "source_physical_point_count": binding[
                        "source_physical_point_count"
                    ],
                    "presentation_kind": binding["presentation_kind"],
                    "proxy_geometry_sha256": binding[
                        "proxy_geometry_sha256"
                    ],
                    "canonical_mesh_sha256": binding[
                        "canonical_mesh_sha256"
                    ],
                }
                for binding in bindings
            ],
        )


def test_emergency_discard_active_capture_stage_closes_and_clears_root(tmp_path):
    root_path = tmp_path / "candidate_static.usda"
    root_path.write_text("#usda 1.0\n", encoding="utf-8")

    class RootLayer:
        realPath = str(root_path)

    class Stage:
        @staticmethod
        def GetRootLayer():
            return RootLayer()

    class Context:
        stage = Stage()

        def get_stage(self):
            return self.stage

        def close_stage(self):
            self.stage = None

    class Timeline:
        @staticmethod
        def is_playing():
            return False

    class App:
        updates = 0

        def update(self):
            self.updates += 1

    args = types.SimpleNamespace(_active_capture_stage_root=str(root_path))
    app = App()

    contract = replay.emergency_discard_active_capture_stage(
        args,
        context=Context(),
        app=app,
        timeline=Timeline(),
        flush_updates=3,
    )

    assert contract["emergency_discard_status"] == "PASS"
    assert contract["discarded"] is True
    assert app.updates == 3
    assert args._active_capture_stage_root is None


def test_emergency_discard_records_failure_without_masking_primary_error(tmp_path):
    root_path = tmp_path / "candidate_static.usda"
    root_path.write_text("#usda 1.0\n", encoding="utf-8")

    class Context:
        @staticmethod
        def get_stage():
            raise RuntimeError("context failed")

    args = types.SimpleNamespace(_active_capture_stage_root=str(root_path))
    contract = replay.emergency_discard_active_capture_stage(
        args,
        context=Context(),
        app=object(),
        timeline=object(),
    )

    assert contract["emergency_discard_status"] == "FAIL"
    assert contract["discarded"] is False
    assert "context failed" in contract["error"]
    assert args._active_capture_stage_root == str(root_path)


def test_replay_mdl_scan_requires_complete_clean_run_scoped_log_artifact(tmp_path):
    log_text = "clean render log\n"
    encoded = log_text.encode("utf-8")
    source_log = tmp_path / "kit.log"
    source_log.write_bytes(b"x" * 10 + encoded)

    class Native:
        MDL_COMPILE_STATUS_PASS = "PASS"

        @staticmethod
        def _read_kit_log_segment(_cursor):
            return {
                "log_path": str(source_log),
                "byte_offset": 10,
                "cursor_captured": True,
                "diagnostic_scan_complete": True,
                "segment_byte_count": len(encoded),
                "segment_sha256": hashlib.sha256(encoded).hexdigest(),
                "log_text": log_text,
            }

        @staticmethod
        def scan_mdl_compile_errors(log_text):
            assert log_text == "clean render log\n"
            return {
                "mdl_compile_status": "PASS",
                "error_count": 0,
                "errors": [],
            }

    log_artifact = tmp_path / "kit_log_segment.txt"
    contract = replay.validate_replay_mdl_log_segment(
        Native,
        cursor={"cursor_captured": True},
        log_artifact_path=log_artifact,
        mdl_source_sha256={"OmniGlass.mdl": "b" * 64},
    )

    assert contract["run_segment_only"] is True
    assert contract["diagnostic_scan_complete"] is True
    assert contract["mdl_error_scan_status"] == (
        "NO_MATCHING_MDL_ERRORS_OBSERVED"
    )
    assert contract["mdl_compile_status"] == "NOT_POSITIVELY_CONFIRMED"
    assert contract["mdl_compile_success_claim_allowed"] is False
    assert contract["mdl_source_sha256_context"] == {"OmniGlass.mdl": "b" * 64}
    assert log_artifact.read_text(encoding="utf-8") == log_text
    assert contract["kit_log_segment_artifact"]["sha256"] == hashlib.sha256(
        encoded
    ).hexdigest()
    assert "log_text" not in contract["strict_kit_log_segment"]
    assert "mdl_compile_status" not in contract["mdl_error_scan"]
    assert contract["known_mdl_compatibility_warning"]["count"] == 0


def test_replay_mdl_scan_records_known_compatibility_warning_without_false_failure(
    tmp_path,
):
    log_text = (
        "[Warning] [omni.hydra] Parameter 'specular_transmission_weight' "
        "of shade node 'water' not available in the MDL representation.\n"
    )
    encoded = log_text.encode("utf-8")
    source_log = tmp_path / "kit.log"
    source_log.write_bytes(encoded)

    class Native:
        MDL_COMPILE_STATUS_PASS = "PASS"

        @staticmethod
        def _read_kit_log_segment(_cursor):
            return {
                "log_path": str(source_log),
                "byte_offset": 0,
                "cursor_captured": True,
                "diagnostic_scan_complete": True,
                "segment_byte_count": len(encoded),
                "segment_sha256": hashlib.sha256(encoded).hexdigest(),
                "log_text": log_text,
            }

        @staticmethod
        def scan_mdl_compile_errors(_log_text):
            return {"mdl_compile_status": "PASS", "error_count": 0, "errors": []}

    contract = replay.validate_replay_mdl_log_segment(
        Native,
        cursor={"cursor_captured": True},
        log_artifact_path=tmp_path / "kit_log_segment.txt",
        mdl_source_sha256={"OmniGlass.mdl": "b" * 64},
    )

    warning = contract["known_mdl_compatibility_warning"]
    assert warning["count"] == 1
    assert warning["status"] == "OBSERVED_NON_FATAL_COMPATIBILITY_WARNING"
    assert warning["render_failure_inferred"] is False
    assert contract["mdl_error_scan_status"] == "NO_MATCHING_MDL_ERRORS_OBSERVED"


def test_replay_material_closure_snapshot_detects_any_file_mutation(tmp_path):
    closure_root = tmp_path / "closure"
    mdl_path = closure_root / "Base" / "OmniGlass.mdl"
    mdl_path.parent.mkdir(parents=True)
    mdl_path.write_text("mdl 1.0;\n", encoding="utf-8")
    closure = {
        "closure_root": str(closure_root),
        "copied_file_sha256": {
            "Base/OmniGlass.mdl": _sha256_path(mdl_path),
        },
    }

    verified = replay.verify_material_closure_snapshot_unchanged(closure)

    assert verified["material_closure_bytes_unchanged"] is True
    assert verified["verified_file_count"] == 1
    mdl_path.write_text("mdl 1.1;\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="material_closure_file_changed"):
        replay.verify_material_closure_snapshot_unchanged(closure)


@pytest.mark.parametrize(
    "segment,match",
    [
        (
            {
                "cursor_captured": False,
                "diagnostic_scan_complete": False,
                "log_text": None,
            },
            "replay_mdl_log_scan_incomplete",
        ),
        (
            {
                "cursor_captured": True,
                "diagnostic_scan_complete": True,
                "segment_byte_count": len(
                    "MDLC:COMPILER error OmniGlass failed\n".encode("utf-8")
                ),
                "segment_sha256": hashlib.sha256(
                    "MDLC:COMPILER error OmniGlass failed\n".encode("utf-8")
                ).hexdigest(),
                "log_text": "MDLC:COMPILER error OmniGlass failed\n",
            },
            "replay_mdl_compile_failed",
        ),
        (
            {
                "cursor_captured": True,
                "diagnostic_scan_complete": True,
                "segment_byte_count": 0,
                "segment_sha256": hashlib.sha256(b"").hexdigest(),
                "log_text": "",
            },
            "replay_mdl_log_segment_empty",
        ),
    ],
)
def test_replay_mdl_log_validation_fails_closed(tmp_path, segment, match):
    segment = dict(segment)
    if isinstance(segment.get("log_text"), str):
        payload = segment["log_text"].encode("utf-8")
        source_log = tmp_path / "kit.log"
        source_log.write_bytes(payload)
        segment.update(
            {
                "log_path": str(source_log),
                "byte_offset": 0,
                "segment_byte_count": len(payload),
                "segment_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    class Native:
        MDL_COMPILE_STATUS_PASS = "PASS"

        @staticmethod
        def _read_kit_log_segment(_cursor):
            return segment

        @staticmethod
        def scan_mdl_compile_errors(log_text):
            return {
                "mdl_compile_status": (
                    "MDL_COMPILE_FAIL" if "error" in log_text.lower() else "PASS"
                ),
                "error_count": int("error" in log_text.lower()),
                "errors": [log_text.strip()] if "error" in log_text.lower() else [],
            }

    with pytest.raises(RuntimeError, match=match):
        replay.validate_replay_mdl_log_segment(
            Native,
            cursor={"cursor_captured": True},
            log_artifact_path=tmp_path / "kit_log_segment.txt",
            mdl_source_sha256={"OmniGlass.mdl": "b" * 64},
        )


def test_replay_preserves_native_beaker_binding_after_version_matched_retarget():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    mesh = UsdGeom.Mesh.Define(stage, "/World/beaker2/mesh").GetPrim()
    material = UsdShade.Material.Define(stage, "/World/Looks/OmniSurface_Glass")
    shader = UsdShade.Shader.Define(
        stage, "/World/Looks/OmniSurface_Glass/Shader"
    )
    shader.GetImplementationSourceAttr().Set(UsdShade.Tokens.sourceAsset)
    shader.SetSourceAsset(Sdf.AssetPath("/closure/Base/OmniGlass.mdl"), "mdl")
    shader.SetSourceAssetSubIdentifier("OmniGlass", "mdl")
    material.CreateSurfaceOutput("mdl").ConnectToSource(
        shader.ConnectableAPI(), "out"
    )
    UsdShade.MaterialBindingAPI.Apply(mesh).Bind(material)

    contract = replay.verify_version_matched_native_beaker_material(
        stage,
        material_retarget={
            "retargeted_shaders": [
                {
                    "shader_path": "/World/Looks/OmniSurface_Glass/Shader",
                    "retargeted_source_asset_basename": "OmniGlass.mdl",
                    "retargeted_sub_identifier": "OmniGlass",
                    "compatibility_fallback": (
                        "OmniSurface_Glass_to_OmniGlass_for_isaacsim41"
                    ),
                }
            ]
        },
    )

    bound, _relationship = UsdShade.MaterialBindingAPI(mesh).ComputeBoundMaterial()
    assert bound.GetPath() == material.GetPath()
    assert contract["native_material_binding_preserved"] is True
    assert contract["beaker_override_used"] is False
    assert contract["material_path"] == "/World/Looks/OmniSurface_Glass"
    assert contract["mdl_source_asset"] == "/closure/Base/OmniGlass.mdl"


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
            "--accepted-matrix-manifest",
            str(tmp_path / "DRY_PLAN_MATRIX_NOT_READ"),
            "--out-root",
            str(tmp_path / "renders"),
            "--dry-plan",
        ]
    )
    plan = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert plan["accepted_summary_read"] is False
    assert plan["accepted_matrix_manifest_read"] is False
    assert plan["simulation_app_started"] is False
    assert plan["candidate_ids"] == [
        "OMNI_REF_FINE",
        "OMNI_REF_RATIO_15",
        "OMNI_REF_RATIO_12",
        "OMNI_REF_SURFACE",
        "OMNI_REF_DISPLAY_FILL",
    ]
    assert list(plan["candidate_contracts"]) == plan["candidate_ids"]
    assert plan["candidate_contracts"]["OMNI_REF_FINE"]["width_formula"] == (
        "clamp(interior_diameter/32,0.0015,0.0020)"
    )
    look_binding = {
        "lighting_variant_id": plan["lighting_variant_id"],
        "effective_replay_look_contract_sha256": plan[
            "effective_replay_look_contract_sha256"
        ],
    }
    assert plan["candidate_contracts"]["OMNI_REF_SURFACE"] == {
        "candidate_id": "OMNI_REF_SURFACE",
        **look_binding,
        "width_formula": "clamp(interior_diameter/32,0.0015,0.0020)",
        "voxel_size_formula": None,
        "proxy_mode": "deterministic_trace_bounds_uv_ellipsoid",
        "presentation_points_type": "UsdGeom.Mesh",
        "physx_api_applied": False,
        "cameras": ["context", "source_beaker_closeup", "native_table_context"],
    }
    assert plan["candidate_contracts"]["OMNI_REF_DISPLAY_FILL"] == {
        "candidate_id": "OMNI_REF_DISPLAY_FILL",
        **look_binding,
        "width_formula": "interior_diameter/15",
        "voxel_size_formula": None,
        "proxy_mode": "deterministic_a18_display_proxy_rounded_cylinder",
        "surface_model_version": "a18_display_proxy_rounded_cylinder_v1",
        "presentation_points_type": "UsdGeom.Mesh",
        "physx_api_applied": False,
        "cameras": ["context", "source_beaker_closeup", "native_table_context"],
    }


def test_runtime_child_main_does_not_duplicate_manifest_json_on_stdout(
    monkeypatch, capsys
):
    result = {
        "classification": "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW",
        "manifest_path": "/cell/replay_manifest.json",
    }
    monkeypatch.setattr(
        replay,
        "validate_runtime_child_invocation",
        lambda _args: {},
    )
    monkeypatch.setattr(replay, "run_replay", lambda _args: result)

    exit_code = replay.main(
        [
            "--runtime-child",
            "--runtime-parent-pid",
            str(os.getpid()),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_replay_display_fill_visual_prototype_is_explicit_and_single_candidate(
    tmp_path,
):
    args = replay.build_arg_parser().parse_args(
        [
            "--accepted-authority-bundle",
            str(tmp_path / "authority"),
            "--out-root",
            str(tmp_path / "renders"),
            "--candidates",
            "OMNI_REF_DISPLAY_FILL",
            "--visual-prototype-display-fill-only",
        ]
    )

    assert replay._candidate_ids_from_args(args) == ("OMNI_REF_DISPLAY_FILL",)
    plan = replay.build_dry_plan(args)
    assert plan["candidate_ids"] == ["OMNI_REF_DISPLAY_FILL"]
    assert plan["run_scope"] == "display_fill_normal_block_visual_prototype"
    assert plan["visual_prototype_only"] is True
    assert plan["formal_five_candidate_set_complete"] is False
    assert plan["colleague_delivery_ready"] is False


def test_effective_replay_look_contract_is_lighting_only_and_hash_bound():
    control = replay.build_effective_replay_look_contract("C_CONTROL")
    treatment = replay.build_effective_replay_look_contract("B_LIGHTING")

    assert control["base_profile_id"] == "weekly_omniglass_C"
    assert treatment["base_profile_id"] == "weekly_omniglass_C"
    assert control["lighting_source_profile_id"] == "weekly_omniglass_C"
    assert treatment["lighting_source_profile_id"] == "weekly_omniglass_B"
    assert control["effective_lighting"] != treatment["effective_lighting"]
    assert control["effective_replay_non_lighting_contract_sha256"] == treatment[
        "effective_replay_non_lighting_contract_sha256"
    ]
    assert control["effective_replay_look_contract_sha256"] != treatment[
        "effective_replay_look_contract_sha256"
    ]
    assert control["render_settings"]["ambient_occlusion_enabled"] is False
    assert treatment["render_settings"] == control["render_settings"]
    assert treatment["liquid_material"] == control["liquid_material"]
    assert treatment["native_beaker_material_retained"] is True
    assert treatment["profile_beaker_override_applied"] is False
    assert treatment["profile_camera_applied"] is False
    assert replay.validate_effective_replay_look_contract(control) == control
    assert replay.validate_effective_replay_look_contract(treatment) == treatment

    tampered = json.loads(json.dumps(treatment))
    tampered["effective_lighting"]["key_intensity"] = 999.0
    with pytest.raises(ValueError, match="effective_replay_look_contract_mismatch"):
        replay.validate_effective_replay_look_contract(tampered)


@pytest.mark.parametrize("variant", ["C_CONTROL", "B_LIGHTING"])
def test_effective_replay_authored_lighting_must_match_contract(variant):
    from tools.labutopia_fluid.presentation_look_profiles import (
        resolve_presentation_look_profile,
    )

    look = replay.build_effective_replay_look_contract(variant)
    profile = resolve_presentation_look_profile(look["base_profile_id"])
    profile["lighting"] = look["effective_lighting"]
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")

    authored = runner._author_liquid_presentation_lighting(stage, profile)
    validated = replay.validate_authored_effective_replay_lighting(
        authored,
        look,
    )

    assert validated["validated"] is True
    assert validated["lighting_variant_id"] == variant
    tampered = dict(authored)
    tampered["key_intensity"] = float(authored["key_intensity"]) + 1.0
    with pytest.raises(ValueError, match="authored_effective_lighting_mismatch"):
        replay.validate_authored_effective_replay_lighting(tampered, look)


def test_effective_replay_render_settings_are_explicit_and_verified():
    class FakeSettings:
        def __init__(self):
            self.values = {}

        def set(self, path, value):
            self.values[path] = value

        def set_bool(self, path, value):
            self.values[path] = bool(value)

        def get(self, path):
            return self.values.get(path)

    settings = FakeSettings()
    look = replay.build_effective_replay_look_contract("C_CONTROL")

    actual = replay.apply_and_validate_effective_replay_render_settings(
        settings,
        native=runner,
        effective_look_contract=look,
    )

    assert actual["validated"] is True
    assert actual["rt_subframes"] == replay.REPLAY_RT_SUBFRAMES
    assert actual["max_refraction_bounces"] == 12
    assert actual["ambient_occlusion_enabled"] is False
    assert actual["shadows_enabled"] is True
    assert settings.values[replay.REPLAY_AMBIENT_OCCLUSION_SETTING_PATH] is False
    assert settings.values[replay.REPLAY_SHADOWS_SETTING_PATH] is True


def test_effective_replay_authored_material_must_match_frozen_a18_values():
    look = replay.build_effective_replay_look_contract("B_LIGHTING")
    expected = look["liquid_material"]
    authored = {
        "preferred_backend": expected["backend"],
        "sub_identifier": expected["sub_identifier"],
        "material_hash": expected["material_hash"],
        "glass_color": expected["glass_color"],
        "reflection_color": expected["reflection_color"],
    }

    validation = replay.validate_authored_effective_replay_material(
        authored,
        look,
    )

    assert validation["validated"] is True
    tampered = json.loads(json.dumps(authored))
    tampered["glass_color"][0] = 0.0
    with pytest.raises(ValueError, match="authored_effective_material_mismatch"):
        replay.validate_authored_effective_replay_material(tampered, look)


@pytest.mark.parametrize("variant", ["C_CONTROL", "B_LIGHTING"])
def test_replay_visual_prototype_lighting_variant_parser_and_scope(variant, tmp_path):
    args = replay.build_arg_parser().parse_args(
        [
            "--accepted-authority-bundle",
            str(tmp_path / "authority"),
            "--out-root",
            str(tmp_path / "renders"),
            "--candidates",
            "OMNI_REF_DISPLAY_FILL",
            "--visual-prototype-display-fill-only",
            "--visual-prototype-lighting-variant",
            variant,
        ]
    )

    contract = replay._effective_look_contract_from_args(args)

    assert contract["lighting_variant_id"] == variant
    assert replay._candidate_ids_from_args(args) == ("OMNI_REF_DISPLAY_FILL",)


@pytest.mark.parametrize(
    "value",
    ["", " ", "B_LIGHTING ", "b_lighting", "weekly_omniglass_B", "UNKNOWN"],
)
def test_replay_lighting_variant_parser_rejects_noncanonical_values(value):
    with pytest.raises(SystemExit):
        replay.build_arg_parser().parse_args(
            ["--visual-prototype-lighting-variant", value]
        )


def test_replay_lighting_variant_parser_rejects_repeated_and_formal_b():
    with pytest.raises(SystemExit):
        replay.build_arg_parser().parse_args(
            [
                "--visual-prototype-lighting-variant",
                "C_CONTROL",
                "--visual-prototype-lighting-variant",
                "B_LIGHTING",
            ]
        )

    formal_b = replay.build_arg_parser().parse_args(
        ["--visual-prototype-lighting-variant", "B_LIGHTING"]
    )
    with pytest.raises(ValueError, match="b_lighting_requires_visual_prototype"):
        replay._effective_look_contract_from_args(formal_b)


def test_formal_b_lighting_fails_before_io_or_runtime(tmp_path, monkeypatch):
    args = replay.build_arg_parser().parse_args(
        [
            "--visual-prototype-lighting-variant",
            "B_LIGHTING",
            "--out-root",
            str(tmp_path / "must_not_exist"),
        ]
    )
    calls = []
    monkeypatch.setattr(
        replay,
        "_validate_output_scope",
        lambda *_args: calls.append("output_scope"),
    )
    monkeypatch.setattr(
        replay,
        "load_replay_inputs_from_args",
        lambda *_args, **_kwargs: calls.append("input_read"),
    )
    monkeypatch.setattr(
        replay,
        "_run_runtime",
        lambda *_args, **_kwargs: calls.append("runtime"),
    )

    with pytest.raises(ValueError, match="b_lighting_requires_visual_prototype"):
        replay.run_replay_parent_launcher([], args)
    with pytest.raises(ValueError, match="b_lighting_requires_visual_prototype"):
        replay.run_replay(args)

    assert calls == []
    assert not (tmp_path / "must_not_exist").exists()


def test_replay_dry_plan_and_provenance_bind_effective_look(tmp_path):
    args = replay.build_arg_parser().parse_args(
        [
            "--accepted-authority-bundle",
            str(tmp_path / "authority"),
            "--out-root",
            str(tmp_path / "renders"),
            "--candidates",
            "OMNI_REF_DISPLAY_FILL",
            "--visual-prototype-display-fill-only",
            "--visual-prototype-lighting-variant",
            "B_LIGHTING",
        ]
    )
    args._execution_argv = [str(Path(replay.__file__).resolve()), "<test>"]

    plan = replay.build_dry_plan(args)
    provenance = replay.build_execution_provenance(args)

    look_hash = plan["effective_replay_look_contract_sha256"]
    assert plan["lighting_variant_id"] == "B_LIGHTING"
    assert len(look_hash) == 64
    candidate = plan["candidate_contracts"]["OMNI_REF_DISPLAY_FILL"]
    assert candidate["lighting_variant_id"] == "B_LIGHTING"
    assert candidate["effective_replay_look_contract_sha256"] == look_hash
    assert provenance["render_parameters"]["lighting_variant_id"] == "B_LIGHTING"
    assert provenance["render_parameters"][
        "effective_replay_look_contract_sha256"
    ] == look_hash


@pytest.mark.parametrize(
    ("candidates", "prototype_only", "expected_error"),
    [
        (
            "OMNI_REF_DISPLAY_FILL",
            False,
            "replay_requires_all_five_candidates",
        ),
        (
            replay.DEFAULT_CANDIDATES,
            True,
            "visual_prototype_requires_exact_display_fill_candidate",
        ),
        (
            "OMNI_REF_SURFACE",
            True,
            "visual_prototype_requires_exact_display_fill_candidate",
        ),
    ],
)
def test_replay_candidate_gate_rejects_ambiguous_prototype_scopes(
    candidates,
    prototype_only,
    expected_error,
):
    with pytest.raises(ValueError, match=expected_error):
        replay._parse_candidate_ids(
            candidates,
            visual_prototype_only=prototype_only,
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
            "--accepted-matrix-manifest",
            "DRY_PLAN_MATRIX_NOT_READ",
            "--dry-plan",
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["simulation_app_started"] is False


def test_sealed_child_pipe_log_wrapper_preserves_allowed_fds_and_statuses(
    tmp_path,
):
    wrapper = (
        replay.REPO_ROOT
        / "tools/labutopia_fluid/run_sealed_child_with_pipe_log.sh"
    )
    nonce = f"{os.getpid()}-{time.time_ns()}"
    log_path = Path(f"/tmp/labutopia-wrapper-{nonce}.log")
    child_failure_log = Path(
        f"/tmp/labutopia-wrapper-child-failure-{nonce}.log"
    )
    tee_failure_log = Path(
        f"/tmp/labutopia-wrapper-tee-failure-{nonce}.log"
    )
    signal_probe_log = Path(
        f"/tmp/labutopia-wrapper-signal-probe-{nonce}.log"
    )
    symlink_log = Path(f"/tmp/labutopia-wrapper-symlink-{nonce}.log")
    allowed_probe = (
        "import json,os,stat;"
        "m=[os.fstat(i).st_mode for i in (0,1,2)];"
        "a=[stat.S_ISCHR(x) or stat.S_ISFIFO(x) or stat.S_ISSOCK(x) for x in m];"
        "print(json.dumps({'allowed':a,'all_allowed':all(a)}));"
        "raise SystemExit(0 if all(a) else 1)"
    )
    try:
        result = subprocess.run(
            [
                "bash",
                str(wrapper),
                "--log",
                str(log_path),
                "--",
                sys.executable,
                "-I",
                "-S",
                "-c",
                allowed_probe,
            ],
            check=False,
        )
        assert result.returncode == 0
        assert json.loads(log_path.read_text())["all_allowed"] is True

        child_marker = tmp_path / "preexisting-log-child-ran"
        preexisting = subprocess.run(
            [
                "bash",
                str(wrapper),
                "--log",
                str(log_path),
                "--",
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(child_marker)!r}).touch()",
            ],
            check=False,
        )
        assert preexisting.returncode == 64
        assert not child_marker.exists()

        symlink_log.symlink_to(tmp_path / "must-not-be-created")
        symlinked = subprocess.run(
            [
                "bash",
                str(wrapper),
                "--log",
                str(symlink_log),
                "--",
                sys.executable,
                "-c",
                "raise SystemExit('must not run')",
            ],
            check=False,
        )
        assert symlinked.returncode == 64
        assert not (tmp_path / "must-not-be-created").exists()

        signal_probe = subprocess.run(
            [
                "bash",
                str(wrapper),
                "--log",
                str(signal_probe_log),
                "--",
                "bash",
                "-c",
                "test -z \"$(trap -p XFSZ)\"",
            ],
            check=False,
        )
        assert signal_probe.returncode == 0

        child_failure = subprocess.run(
            [
                "bash",
                str(wrapper),
                "--log",
                str(child_failure_log),
                "--",
                sys.executable,
                "-c",
                "raise SystemExit(7)",
            ],
            check=False,
        )
        assert child_failure.returncode == 7

        def disable_file_writes():
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))

        tee_failure = subprocess.run(
            [
                "bash",
                str(wrapper),
                "--log",
                str(tee_failure_log),
                "--",
                sys.executable,
                "-c",
                "import os; os.write(1, b'x' * (1024 * 1024))",
            ],
            check=False,
            preexec_fn=disable_file_writes,
        )
        assert tee_failure.returncode == 74

        nested_log = tmp_path / "nested.log"
        invalid_path = subprocess.run(
            [
                "bash",
                str(wrapper),
                "--log",
                str(nested_log),
                "--",
                sys.executable,
                "-c",
                "print('must not run')",
            ],
            check=False,
        )
        assert invalid_path.returncode == 64
        assert not nested_log.exists()
    finally:
        log_path.unlink(missing_ok=True)
        child_failure_log.unlink(missing_ok=True)
        tee_failure_log.unlink(missing_ok=True)
        signal_probe_log.unlink(missing_ok=True)
        symlink_log.unlink(missing_ok=True)


def test_formal_003_orchestrator_prints_exact_balanced_sixteen_slot_plan():
    orchestrator = (
        replay.REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_003.sh"
    )
    result = subprocess.run(
        ["bash", str(orchestrator), "--print-plan"],
        cwd=replay.REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    rows = [line.split("\t") for line in result.stdout.splitlines()]
    expected = [
        (sequence, replicate, order_index, variant)
        for sequence, (replicate, order_index, variant) in enumerate(
            (
                (replicate, order_index, variant)
                for replicate in replay.RENDER_DIAGNOSTIC_REPLICATES
                for order_index, variant in enumerate(
                    replay.RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate]
                )
            )
        )
    ]
    assert len(rows) == 16
    historical_root = (
        replay.REPO_ROOT
        / "docs/labutopia_lab_poc/evidence_manifests"
        / "real_beaker_ao_rt_matrix_v3_20260712_003"
    )
    for row, (sequence, replicate, order_index, variant) in zip(rows, expected):
        cell_name = f"{replicate}_{order_index}_{variant}"
        assert row == [
            "PLAN",
            str(sequence),
            replicate,
            str(order_index),
            variant,
            str(historical_root / "cells" / cell_name),
            f"/tmp/labutopia-formal-003-{cell_name}.log",
        ]


@pytest.mark.parametrize("revision", ["005", "006", "007", "008"])
def test_formal_005_through_008_orchestrators_print_exact_balanced_sixteen_slot_plan(
    revision,
):
    experiment_id = f"real_beaker_ao_rt_matrix_v3_20260712_{revision}"
    orchestrator = (
        replay.REPO_ROOT
        / f"tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_{revision}.sh"
    )
    result = subprocess.run(
        ["bash", str(orchestrator), "--print-plan"],
        cwd=replay.REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    rows = [line.split("\t") for line in result.stdout.splitlines()]
    expected = [
        (sequence, replicate, order_index, variant)
        for sequence, (replicate, order_index, variant) in enumerate(
            (
                (replicate, order_index, variant)
                for replicate in replay.RENDER_DIAGNOSTIC_REPLICATES
                for order_index, variant in enumerate(
                    replay.RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate]
                )
            )
        )
    ]
    assert len(rows) == 16
    for row, (sequence, replicate, order_index, variant) in zip(rows, expected):
        cell_name = f"{replicate}_{order_index}_{variant}"
        assert row == [
            "PLAN",
            str(sequence),
            replicate,
            str(order_index),
            variant,
            str(
                replay.REPO_ROOT
                / "docs/labutopia_lab_poc/evidence_manifests"
                / experiment_id
                / "cells"
                / cell_name
            ),
            f"/tmp/labutopia-formal-{revision}-{cell_name}.log",
        ]


@pytest.mark.parametrize("revision", ["005", "006", "007", "008"])
def test_formal_005_through_008_orchestrator_preflight_is_side_effect_free_and_resumes(
    tmp_path, revision
):
    experiment_id = f"real_beaker_ao_rt_matrix_v3_20260712_{revision}"
    source = (
        replay.REPO_ROOT
        / f"tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_{revision}.sh"
    )
    tools_dir = tmp_path / "tools/labutopia_fluid"
    tools_dir.mkdir(parents=True)
    orchestrator = tools_dir / source.name
    shutil.copy2(source, orchestrator)
    (tools_dir / "run_real_beaker_omniglass_replay.py").write_text(
        "raise SystemExit('fake runner must not execute directly')\n",
        encoding="ascii",
    )
    marker = tmp_path / "wrapper-calls.log"
    wrapper = tools_dir / "run_sealed_child_with_pipe_log.sh"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> {str(marker)!r}\n",
        encoding="ascii",
    )
    wrapper.chmod(0o755)
    authority = (
        tmp_path
        / "docs/labutopia_lab_poc/evidence_manifests"
        / "fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712"
        / "accepted_authority_P4096_S2"
    )
    authority.mkdir(parents=True)

    missing = subprocess.run(
        ["bash", str(orchestrator)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing.returncode == 66
    assert not marker.exists()
    manifest_root = tmp_path / "docs/labutopia_lab_poc/evidence_manifests"
    assert not (
        manifest_root / f".{experiment_id}.aggregate.lock"
    ).exists()
    assert not (manifest_root / experiment_id).exists()

    (manifest_root / f"{experiment_id}_implementation_identity.json").write_text(
        "{}\n", encoding="ascii"
    )
    (manifest_root / f"{experiment_id}_protected_tree_freeze_pre.json").write_text(
        "{}\n", encoding="ascii"
    )
    invalid_freezes = subprocess.run(
        ["bash", str(orchestrator), "--from", "15"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert invalid_freezes.returncode == 66
    assert not marker.exists()
    assert not (
        manifest_root / f".{experiment_id}.aggregate.lock"
    ).exists()
    (tools_dir / "run_real_beaker_omniglass_replay.py").write_text(
        "import sys\n"
        "if sys.argv[1:] == ['--render-diagnostic-launch-preflight-only']:\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit('fake runner must not execute directly')\n",
        encoding="ascii",
    )
    resumed = subprocess.run(
        ["bash", str(orchestrator), "--from", "15"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    calls = marker.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert f"labutopia-formal-{revision}-D_3_AO0_RT12.log" in calls[0]
    assert f"--render-diagnostic-experiment-id {experiment_id}" in calls[0]
    assert "--render-diagnostic-replicate D" in calls[0]
    assert "--render-diagnostic-order-index 3" in calls[0]


def test_formal_007_launcher_differs_from_006_only_by_revision_references():
    launcher_006 = (
        replay.REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_006.sh"
    ).read_text(encoding="utf-8")
    launcher_007 = (
        replay.REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_007.sh"
    ).read_text(encoding="utf-8")

    expected_007 = launcher_006.replace(
        "real_beaker_ao_rt_matrix_v3_20260712_006",
        "real_beaker_ao_rt_matrix_v3_20260712_007",
    ).replace("labutopia-formal-006", "labutopia-formal-007")
    assert launcher_007 == expected_007


def test_formal_008_launcher_differs_from_007_only_by_revision_references():
    launcher_007 = (
        replay.REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_007.sh"
    ).read_text(encoding="utf-8")
    launcher_008 = (
        replay.REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_008.sh"
    ).read_text(encoding="utf-8")

    expected_008 = launcher_007.replace(
        "real_beaker_ao_rt_matrix_v3_20260712_007",
        "real_beaker_ao_rt_matrix_v3_20260712_008",
    ).replace("labutopia-formal-007", "labutopia-formal-008")
    assert launcher_008 == expected_008


def test_formal_003_orchestrator_preflights_freezes_and_resumes_exact_slot(
    tmp_path,
):
    source = (
        replay.REPO_ROOT
        / "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_003.sh"
    )
    tools_dir = tmp_path / "tools/labutopia_fluid"
    tools_dir.mkdir(parents=True)
    orchestrator = tools_dir / source.name
    shutil.copy2(source, orchestrator)
    (tools_dir / "run_real_beaker_omniglass_replay.py").write_text(
        "raise SystemExit('fake runner must not execute directly')\n",
        encoding="ascii",
    )
    marker = tmp_path / "wrapper-calls.log"
    fake_wrapper = tools_dir / "run_sealed_child_with_pipe_log.sh"
    fake_wrapper.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> {str(marker)!r}\n",
        encoding="ascii",
    )
    fake_wrapper.chmod(0o755)
    authority = (
        tmp_path
        / "docs/labutopia_lab_poc/evidence_manifests"
        / "fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712"
        / "accepted_authority_P4096_S2"
    )
    authority.mkdir(parents=True)

    missing_freezes = subprocess.run(
        ["bash", str(orchestrator)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_freezes.returncode == 66
    assert not marker.exists()
    assert not (
        tmp_path
        / "docs/labutopia_lab_poc/evidence_manifests"
        / ".real_beaker_ao_rt_matrix_v3_20260712_003.aggregate.lock"
    ).exists()

    manifest_root = tmp_path / "docs/labutopia_lab_poc/evidence_manifests"
    (manifest_root / "real_beaker_ao_rt_matrix_v3_20260712_003_implementation_identity.json").write_text(
        "{}\n", encoding="ascii"
    )
    (manifest_root / "real_beaker_ao_rt_matrix_v3_20260712_003_protected_tree_freeze_pre.json").write_text(
        "{}\n", encoding="ascii"
    )
    resumed = subprocess.run(
        ["bash", str(orchestrator), "--from", "15"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert resumed.returncode == 0, resumed.stderr
    calls = marker.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert "--render-diagnostic-replicate D" in calls[0]
    assert "--render-diagnostic-order-index 3" in calls[0]
    assert "--visual-prototype-render-diagnostic-variant AO0_RT12" in calls[0]

    for invalid in (("--from", "-1"), ("--from", "16"), ("--unknown",)):
        rejected = subprocess.run(
            ["bash", str(orchestrator), *invalid],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
        )
        assert rejected.returncode == 64
    assert marker.read_text(encoding="utf-8").splitlines() == calls
    assert "bin/python3.10\"" in source.read_text(encoding="utf-8")


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
            "--accepted-matrix-manifest",
            "DRY_PLAN_MATRIX_NOT_READ",
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
        "mdl/nvidia/core_definitions.mdl": "nvidia-core-4.1\n",
        "mdl/nvidia/support_definitions.mdl": "nvidia-support-4.1\n",
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
    assert "mdl/nvidia/core_definitions.mdl" in contract["source_file_sha256"]
    assert "mdl/nvidia/support_definitions.mdl" in contract["source_file_sha256"]
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


def test_replay_rejects_invalid_pair_camera_region_before_runtime_boot(
    tmp_path,
    monkeypatch,
):
    summary_path, summary, _records = _write_accepted_replay_input(tmp_path)
    summary["region_config"]["source_center"] = None
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    booted = []
    monkeypatch.setattr(replay, "_run_runtime", lambda *_args: booted.append(True))

    with pytest.raises(
        ValueError,
        match="accepted_summary_trace_contract_invalid",
    ):
        replay.run_replay(_replay_args(tmp_path, summary_path))

    assert booted == []


def test_runtime_failure_manifest_does_not_claim_unobserved_timeline_checkpoint(
    tmp_path,
):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    effective_look = replay.build_effective_replay_look_contract("B_LIGHTING")
    args = types.SimpleNamespace(
        _active_candidate_id=None,
        _completed_candidate_ids=[],
        _last_replicator_cleanup=None,
        _timeline_checkpoint_observed=False,
        _effective_replay_look_contract=effective_look,
    )

    failure = replay.build_replay_runtime_failure_manifest(
        args,
        accepted,
        RuntimeError("pre-checkpoint failure"),
        traceback_text="traceback",
    )

    assert failure["runtime_contract"][
        "timeline_checkpoint_observation_recorded"
    ] is False
    assert failure["runtime_contract"][
        "timeline_observed_stopped_at_recorded_checkpoints"
    ] is None
    assert failure["lighting_variant_id"] == "B_LIGHTING"
    assert failure["effective_replay_look_contract"] == effective_look
    assert failure["effective_replay_look_contract_sha256"] == effective_look[
        "effective_replay_look_contract_sha256"
    ]
    assert failure["runtime_failure_context"] == {
        "active_candidate_id": None,
        "completed_candidate_ids": [],
        "last_replicator_cleanup": None,
    }


def test_runtime_failure_manifest_preserves_structured_session_layer_diagnostics(
    tmp_path,
):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    args = types.SimpleNamespace(
        _active_candidate_id="OMNI_REF_FINE",
        _completed_candidate_ids=[],
        _last_replicator_cleanup={"cleanup_complete": True},
        _timeline_checkpoint_observed=True,
    )
    contract = {
        "validation_status": "FAIL",
        "unexpected_spec_paths": ["/World/Unexpected"],
    }
    error = replay.SessionLayerValidationError(
        "session_layer_scene_opinions_present_at_export",
        contract,
    )

    failure = replay.build_replay_runtime_failure_manifest(
        args,
        accepted,
        error,
        traceback_text="traceback",
    )

    assert failure["runtime_failure_context"]["session_layer_validation"] == contract


def test_runtime_failure_manifest_preserves_permission_recovery_contract(tmp_path):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    args = types.SimpleNamespace(
        _active_candidate_id="OMNI_REF_DISPLAY_FILL",
        _completed_candidate_ids=[],
        _last_replicator_cleanup=None,
        _timeline_checkpoint_observed=True,
    )
    contract = replay._new_presentation_permission_recovery_contract()
    contract["failure_stage"] = "IDENTITY_PREFLIGHT"
    error = replay.PresentationLayerPermissionRecoveryError(
        "permission recovery failed",
        contract,
    )

    failure = replay.build_replay_runtime_failure_manifest(
        args,
        accepted,
        error,
        traceback_text="traceback",
    )

    assert failure["runtime_failure_context"][
        "presentation_layer_export_permission_recovery"
    ] == contract


def test_run_runtime_close_failure_overwrites_both_scoped_and_custom_manifests(
    tmp_path,
    monkeypatch,
):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    contracts = replay.build_candidate_replay_contracts(accepted)
    args = _replay_args(tmp_path, summary_path)
    out_root = tmp_path / "runtime_out"
    custom_manifest = tmp_path / "custom" / "manifest.json"
    args._resolved_out_root = str(out_root)
    args._resolved_manifest = str(custom_manifest)
    args._matrix_authority_preflight = {}
    args._execution_provenance = {"provenance_sha256": "a" * 64}

    class SimulationApp:
        def __init__(self, _config):
            self.closed = False

        def close(self):
            self.closed = True
            raise RuntimeError("close failed")

    isaacsim = types.ModuleType("isaacsim")
    isaacsim.SimulationApp = SimulationApp
    monkeypatch.setitem(sys.modules, "isaacsim", isaacsim)
    monkeypatch.setattr(
        replay,
        "validate_authoritative_matrix_replay_input",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        replay,
        "verify_replay_input_snapshots_unchanged",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        replay,
        "_render_validated_replay",
        lambda *_args, **_kwargs: {
            "classification": "RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
        },
    )

    result = replay._run_runtime(args, accepted, contracts)

    assert result["classification"] == "STOP_RUNTIME_ERROR"
    for path in (out_root / "replay_manifest.json", custom_manifest):
        assert json.loads(path.read_text())["classification"] == "STOP_RUNTIME_ERROR"


def test_run_runtime_closes_app_even_when_failure_manifest_write_raises(
    tmp_path,
    monkeypatch,
):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    contracts = replay.build_candidate_replay_contracts(accepted)
    args = _replay_args(tmp_path, summary_path)
    args._resolved_out_root = str(tmp_path / "runtime_out")
    args._resolved_manifest = str(tmp_path / "custom_manifest.json")
    args._matrix_authority_preflight = {}
    args._execution_provenance = {"provenance_sha256": "a" * 64}

    class SimulationApp:
        instance = None

        def __init__(self, _config):
            self.closed = False
            SimulationApp.instance = self

        def close(self):
            self.closed = True

    isaacsim = types.ModuleType("isaacsim")
    isaacsim.SimulationApp = SimulationApp
    monkeypatch.setitem(sys.modules, "isaacsim", isaacsim)
    monkeypatch.setattr(
        replay,
        "validate_authoritative_matrix_replay_input",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        replay,
        "verify_replay_input_snapshots_unchanged",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        replay,
        "_render_validated_replay",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("render failed")),
    )
    monkeypatch.setattr(
        replay,
        "atomic_write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("write failed")),
    )

    with pytest.raises(RuntimeError, match="write failed"):
        replay._run_runtime(args, accepted, contracts)

    assert SimulationApp.instance.closed is True


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
        "OMNI_REF_SURFACE",
        "OMNI_REF_DISPLAY_FILL",
    ]
    assert accepted.summary_sha256 == _sha256_path(summary_path)
    assert accepted.trace_sha256 == _sha256_path(Path(summary["trace_path"]))
    assert accepted.source_usd_sha256 == _sha256_path(
        Path(summary["source_usd_path"])
    )
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
            "author_stage_opened_exact_accepted_source": True,
            "static_entry_frozen_before_replicator": True,
            "capture_stage_opens_frozen_static_entry": True,
            "capture_frame_updates_use_anonymous_overlay": True,
            "capture_stage_discarded_after_candidate": None,
            "physics_step_count_instrumented": False,
            "physics_steps_executed": None,
            "observed_default_time_usd_point_attributes_changed": None,
            "timeline_observed_stopped_at_all_checkpoints": None,
            "required_timeline_state_at_capture": "stopped",
            "cameras": [
                "context",
                "source_beaker_closeup",
                "native_table_context",
            ],
        }
        for manifest in manifests.values()
    )
    surface = manifests["OMNI_REF_SURFACE"]
    assert surface["presentation_kind"] == "surface_mesh"
    assert surface["presentation_primitive_path"] == (
        "/World/CompletedPBD/PresentationSurface"
    )
    assert surface["frames"][0]["canonical_mesh_sha256"]
    assert surface["frames"][0]["physical_volume_parity_claim_allowed"] is False
    display_fill = manifests["OMNI_REF_DISPLAY_FILL"]
    assert display_fill["presentation_kind"] == "surface_mesh"
    assert display_fill["surface_model_version"] == (
        "a18_display_proxy_rounded_cylinder_v1"
    )
    assert len(display_fill["surface_model_contract_sha256"]) == 64
    assert display_fill["display_proxy_volume_disclaimer"]
    assert {
        frame["proxy_geometry_sha256"] for frame in display_fill["frames"]
    } == {display_fill["frames"][0]["proxy_geometry_sha256"]}
    assert {
        frame["canonical_mesh_sha256"] for frame in display_fill["frames"]
    } == {display_fill["frames"][0]["canonical_mesh_sha256"]}
    assert len(
        {frame["source_positions_sha256"] for frame in display_fill["frames"]}
    ) == len(display_fill["frames"])
    assert all(
        frame["surface_model_contract_sha256"]
        == display_fill["surface_model_contract_sha256"]
        and frame["surface_model_version"]
        == display_fill["surface_model_version"]
        and frame["source_layout_affects_geometry"] is False
        and frame["nominal_physical_particle_width_affects_geometry"] is False
        and frame["display_proxy_volume_disclaimer"]
        for frame in display_fill["frames"]
    )
    for manifest in manifests.values():
        assert manifest["physical_volume_parity_claim_allowed"] is False
        assert manifest["free_surface_shape_claim_allowed"] is False
        assert manifest["fluid_dynamics_claim_allowed"] is False
        assert manifest["presentation_only_volume_disclaimer"]
        assert manifest["presentation_only_shape_disclaimer"]
        assert all(
            frame["physical_volume_parity_claim_allowed"] is False
            and frame["free_surface_shape_claim_allowed"] is False
            and frame["fluid_dynamics_claim_allowed"] is False
            and frame["presentation_only_volume_disclaimer"]
            and frame["presentation_only_shape_disclaimer"]
            for frame in manifest["frames"]
        )
        for frame_offset, frame in enumerate(manifest["frames"]):
            assert frame["trace_record_sha256"] == replay._json_sha256(
                accepted.records[frame_offset]
            )
            assert frame["source_positions_sha256"] == replay._json_sha256(
                accepted.records[frame_offset]["positions"]
            )
            assert frame["proxy_geometry_sha256"] == replay.proxy_geometry_sha256(
                accepted.proxy_frame(
                    manifest["candidate_id"], frame_offset=frame_offset
                )
            )


def test_candidate_frame_contract_validation_recomputes_from_accepted_trace(tmp_path):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    contract = replay.build_candidate_replay_contracts(accepted)["OMNI_REF_SURFACE"]

    validation = replay.validate_candidate_frame_contracts_against_accepted(
        contract,
        accepted,
    )

    assert validation["validated"] is True
    assert validation["frame_count"] == 2
    corrupted = dict(contract)
    corrupted["frames"] = [dict(frame) for frame in contract["frames"]]
    corrupted["frames"][0]["proxy_geometry_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="candidate_frame_contract_mismatch"):
        replay.validate_candidate_frame_contracts_against_accepted(
            corrupted,
            accepted,
        )

    display_fill = replay.build_candidate_replay_contracts(accepted)[
        "OMNI_REF_DISPLAY_FILL"
    ]
    corrupted_model = dict(display_fill)
    corrupted_model["surface_model_contract_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="candidate_descriptor_contract_mismatch"):
        replay.validate_candidate_frame_contracts_against_accepted(
            corrupted_model,
            accepted,
        )


def test_candidate_manifest_requires_both_image_sets_and_never_self_claims_visual_pass(
    tmp_path,
    monkeypatch,
):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    contract = replay.build_candidate_replay_contracts(accepted)["OMNI_REF_FINE"]
    contract["render_output_contract"] = {
        "width": 16,
        "height": 12,
        "fps": 7,
        "expected_frame_indices": [0, 10],
    }
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    static_usd = candidate_dir / "candidate_static.usda"
    static_usd.write_text("#usda 1.0\n", encoding="utf-8")
    presentation_layer = candidate_dir / "candidate_presentation.usda"
    presentation_layer.write_text("#usda 1.0\n", encoding="utf-8")
    kit_log_segment = candidate_dir / "kit_log_segment.txt"
    kit_log_segment.write_text("clean render log\n", encoding="utf-8")
    diagnostic_artifacts = {"kit_log_segment": kit_log_segment}
    fingerprint_roles = {
        "frozen_composed_world_fingerprint_json",
        "capture_composed_world_fingerprint_json",
        "reopened_composed_world_fingerprint_json",
    }
    for role in replay.CANDIDATE_DIAGNOSTIC_ARTIFACT_ROLES:
        if role == "kit_log_segment":
            continue
        suffix = ".usda" if role.endswith("_usda") else ".json"
        path = candidate_dir / f"{role}{suffix}"
        if role not in fingerprint_roles:
            path.write_text(f"{role}\n", encoding="utf-8")
        diagnostic_artifacts[role] = path
    fingerprint_stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(fingerprint_stage, "/World")
    fingerprint_summary = replay.composed_world_fingerprint(fingerprint_stage)
    for role in fingerprint_roles:
        replay.write_composed_world_fingerprint_artifact(
            fingerprint_stage,
            diagnostic_artifacts[role],
        )
    contract["replicator_resource_cleanup"] = {
        "cleanup_complete": True,
        "cleanup_failures": {},
    }
    contract["capture_stage_lifecycle"] = {
        "persistent_layers_after_capture": {
            "verified": True,
            "used_layer_set_unchanged": True,
        },
        "session_residue": {
            "classification_gate_status": "PASS",
            "composed_world_default_time_property_snapshot_equivalence_"
            "excluding_known_physx_runtime_status": "PASS",
            "full_render_entry_equivalence_status": "NOT_CLAIMED",
        },
        "capture_stage_discard": {"discarded": True},
        "capture_session_quiescence": {
            "quiescence_status": "PASS_STABLE_CONSECUTIVE_SNAPSHOTS"
        },
        "final_presentation_binding_after_quiescence": {"verified": True},
        "frozen_world_fingerprint": fingerprint_summary,
        "capture_world_fingerprint": fingerprint_summary,
        "reopened_world_fingerprint": fingerprint_summary,
    }
    contract["runtime_contract"] = {
        **contract["runtime_contract"],
        "capture_stage_discarded_after_candidate": True,
        "observed_default_time_usd_point_attributes_changed": False,
        "timeline_observed_stopped_at_all_checkpoints": True,
    }
    closeups = [
        candidate_dir / "source_beaker_closeup_frames" / f"frame_{index:04d}.png"
        for index in (0, 10)
    ]
    contexts = [
        candidate_dir / "context_frames" / f"frame_{index:04d}.png"
        for index in (0, 10)
    ]
    native_contexts = [
        candidate_dir / "native_table_context_frames" / f"frame_{index:04d}.png"
        for index in (0, 10)
    ]
    for index, path in enumerate([*closeups, *contexts, *native_contexts]):
        path.parent.mkdir(exist_ok=True)
        Image.new("RGB", (16, 12), (20 + index, 40, 80)).save(path)
    images_by_role = {
        "context": contexts,
        "source_beaker_closeup": closeups,
        "native_table_context": native_contexts,
    }
    frame_bindings = []
    for frame_offset, record in enumerate(accepted.records):
        frame_bindings.append(
            replay.build_capture_frame_binding(
                candidate_id="OMNI_REF_FINE",
                frame_offset=frame_offset,
                record=record,
                physical_trace_sha256=accepted.physical_trace_identity[
                    "physical_trace_sha256"
                    ],
                    proxy_update={
                        "physical_trace_frame_index": record["step_index"],
                        "proxy_geometry_sha256": contract["frames"][frame_offset][
                            "proxy_geometry_sha256"
                        ],
                        "presentation_primitive_path": replay.PRESENTATION_POINTS_PATH,
                        "presentation_kind": "points",
                            "canonical_mesh_sha256": contract["frames"][frame_offset].get(
                                "canonical_mesh_sha256"
                            ),
                            "usd_geometry_binding": {
                                "verified": True,
                                "actual_usd_geometry_sha256": contract["frames"][
                                    frame_offset
                                ]["proxy_geometry_sha256"],
                            },
                            "usd_geometry_binding_after_capture": {
                                "verified": True,
                                "actual_usd_geometry_sha256": contract["frames"][
                                    frame_offset
                                ]["proxy_geometry_sha256"],
                            },
                },
                image_paths={
                    role: paths[frame_offset]
                    for role, paths in images_by_role.items()
                },
            )
        )
    diagnostic_artifacts["capture_frame_bindings_json"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_id": "OMNI_REF_FINE",
                "physical_trace_sha256": accepted.physical_trace_identity[
                    "physical_trace_sha256"
                ],
                "frame_indices": [0, 10],
                "lighting_variant_id": contract["lighting_variant_id"],
                "effective_replay_look_contract": contract[
                    "effective_replay_look_contract"
                ],
                "effective_replay_look_contract_sha256": contract[
                    "effective_replay_look_contract_sha256"
                ],
                "bindings": frame_bindings,
                "bindings_sha256": replay._json_sha256(frame_bindings),
            }
        ),
        encoding="utf-8",
    )
    videos = {
        role: candidate_dir / f"{role}.mp4"
        for role in (
            "context",
            "source_beaker_closeup",
            "native_table_context",
        )
    }
    for path in videos.values():
        path.write_bytes(b"encoded video")
    monkeypatch.setattr(
        replay,
        "probe_mp4_against_png_frames",
        lambda _path, _frame_paths: {
            "frame_count": 2,
            "decodable": True,
            "frame_shape": [12, 16, 3],
            "width": 16,
            "height": 12,
            "fps": 7.0,
            "content_sequence_bound": True,
            "maximum_frame_mean_absolute_error": 2.0,
            "minimum_frame_psnr_db": 38.0,
        },
    )

    finalized = replay.finalize_candidate_manifest(
        contract,
        accepted_replay=accepted,
        candidate_dir=candidate_dir,
        static_usd_path=static_usd,
        presentation_layer_path=presentation_layer,
        closeup_image_paths=closeups,
        context_image_paths=contexts,
        native_context_image_paths=native_contexts,
        video_paths=videos,
        diagnostic_artifact_paths=diagnostic_artifacts,
    )

    assert finalized["render_artifact_set_complete"] is True
    assert finalized["runtime_evidence_gate"]["status"] == "PASS"
    assert finalized["portable_dependency_closure_complete"] is False
    assert finalized["colleague_delivery_ready"] is False
    assert finalized["visual_review_verdict"] == "PENDING_INDEPENDENT_REVIEW"
    assert finalized["omniglass_reference_particle_look_selected"] is False
    assert finalized["render_output_validation"]["all_images_decoded"] is True
    assert finalized["render_output_validation"]["all_videos_decoded"] is True
    assert finalized["render_output_validation"][
        "all_video_content_sequences_bound"
    ] is True
    assert (
        "deterministic_presentation_proxy_derived_from_accepted_trace_rendered=true"
        in finalized["claim_boundary"]["allowed"]
    )
    assert not any(
        "without_physics_steps" in claim
        for claim in finalized["claim_boundary"]["allowed"]
    )
    assert set(finalized["artifact_sha256"]) == {
        "candidate_static.usda",
        "candidate_presentation.usda",
        "source_beaker_closeup_frames/frame_0000.png",
        "source_beaker_closeup_frames/frame_0010.png",
        "context_frames/frame_0000.png",
        "context_frames/frame_0010.png",
        "native_table_context_frames/frame_0000.png",
        "native_table_context_frames/frame_0010.png",
        "context.mp4",
        "source_beaker_closeup.mp4",
        "native_table_context.mp4",
        "kit_log_segment.txt",
        *{
            path.name
            for role, path in diagnostic_artifacts.items()
            if role != "kit_log_segment"
        },
    }

    closeups[-1].unlink()
    with pytest.raises(ValueError, match="candidate_images_incomplete"):
        replay.finalize_candidate_manifest(
            contract,
            accepted_replay=accepted,
            candidate_dir=candidate_dir,
            static_usd_path=static_usd,
            presentation_layer_path=presentation_layer,
            closeup_image_paths=closeups,
            context_image_paths=contexts,
            native_context_image_paths=native_contexts,
            video_paths=videos,
            diagnostic_artifact_paths=diagnostic_artifacts,
        )

    Image.new("RGB", (16, 12), (20, 40, 80)).save(closeups[-1])
    with pytest.raises(ValueError, match="candidate_video_roles_invalid"):
        replay.finalize_candidate_manifest(
            contract,
            accepted_replay=accepted,
            candidate_dir=candidate_dir,
            static_usd_path=static_usd,
            presentation_layer_path=presentation_layer,
            closeup_image_paths=closeups,
            context_image_paths=contexts,
            native_context_image_paths=native_contexts,
            video_paths={},
            diagnostic_artifact_paths=diagnostic_artifacts,
        )


def test_mp4_probe_binds_decoded_content_to_ordered_png_frames(tmp_path):
    import cv2
    import numpy as np

    frame_paths = []
    colors = [(20, 40, 80), (90, 30, 10), (5, 120, 60)]
    for index, color in enumerate(colors):
        path = tmp_path / f"frame_{index:04d}.png"
        Image.new("RGB", (32, 24), color).save(path)
        frame_paths.append(path)
    video_path = tmp_path / "frames.mp4"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        7.0,
        (32, 24),
    )
    assert writer.isOpened()
    for color in colors:
        rgb = np.full((24, 32, 3), color, dtype=np.uint8)
        writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    writer.release()

    matched = replay.probe_mp4_against_png_frames(video_path, frame_paths)
    mismatched = replay.probe_mp4_against_png_frames(
        video_path,
        list(reversed(frame_paths)),
    )

    assert matched["content_sequence_bound"] is True
    assert matched["maximum_frame_mean_absolute_error"] <= 8.0
    assert matched["minimum_frame_psnr_db"] >= 28.0
    assert mismatched["content_sequence_bound"] is False


def test_candidate_presentation_layer_normalizes_private_file_mode(tmp_path):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    presentation_path = tmp_path / "presentation.usda"

    presentation = replay.begin_candidate_presentation_layer(
        stage,
        presentation_path,
    )

    assert stat.S_IMODE(presentation_path.stat().st_mode) == 0o600
    assert presentation.permissionToEdit is True
    assert presentation.permissionToSave is True


def test_static_entry_normalizes_private_file_mode_before_save(tmp_path):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    UsdGeom.Cube.Define(source_stage, "/World/SourceTable")
    source_stage.GetRootLayer().Save()
    source_bytes = source_path.read_bytes()
    stage = Usd.Stage.Open(str(source_path))
    baseline = replay.snapshot_session_layer(stage)
    presentation_path = tmp_path / "presentation.usda"
    presentation = replay.begin_candidate_presentation_layer(
        stage,
        presentation_path,
    )
    presentation_path.chmod(0o600)
    UsdGeom.Sphere.Define(stage, "/World/CompletedPBD/PresentationSurface")
    stage.GetRootLayer().SetPermissionToEdit(False)
    stage.GetRootLayer().SetPermissionToSave(False)
    static_path = tmp_path / "static.usda"

    exported = replay.export_static_candidate_entry(
        stage,
        presentation_layer=presentation,
        session_layer_baseline=baseline,
        source_usd_path=source_path,
        expected_source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        static_usd_path=static_path,
        required_presentation_prim_path=(
            "/World/CompletedPBD/PresentationSurface"
        ),
        required_source_prim_path="/World/SourceTable",
    )

    recovery = replay.validate_presentation_layer_export_permission_recovery_contract(
        exported["presentation_layer_export_permission_recovery"]
    )
    assert recovery["recovery_attempted"] is False
    assert recovery["set_edit_attempted"] is False
    assert recovery["set_save_attempted"] is False
    assert recovery["save_attempted"] is True
    assert recovery["save_succeeded"] is True
    assert recovery["relock_succeeded"] is True
    assert stat.S_IMODE(presentation_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(static_path.stat().st_mode) == 0o600
    assert source_path.read_bytes() == source_bytes
    assert stage.GetRootLayer().permissionToEdit is False
    assert stage.GetRootLayer().permissionToSave is False
    reopened = Usd.Stage.Open(str(static_path))
    assert reopened.GetPrimAtPath("/World/SourceTable")
    assert reopened.GetPrimAtPath("/World/CompletedPBD/PresentationSurface")


def test_candidate_presentation_layer_preserves_source_and_exports_composed_entry(
    tmp_path,
):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    world = UsdGeom.Xform.Define(source_stage, "/World")
    source_stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(source_stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(source_stage, 1.0)
    source_stage.SetStartTimeCode(10.0)
    source_stage.SetEndTimeCode(20.0)
    source_stage.SetTimeCodesPerSecond(60.0)
    source_stage.SetFramesPerSecond(30.0)
    UsdGeom.Cube.Define(source_stage, "/World/SourceTable")
    UsdGeom.Xform.Define(source_stage, "/World/ParticleSystem")
    source_stage.GetRootLayer().Save()
    source_bytes_before = source_path.read_bytes()

    stage = Usd.Stage.Open(str(source_path))
    session_layer_baseline = replay.snapshot_session_layer(stage)
    presentation_path = tmp_path / "candidate_presentation.usda"
    presentation_layer = replay.begin_candidate_presentation_layer(
        stage,
        presentation_path,
    )
    UsdGeom.Sphere.Define(stage, "/World/CompletedPBD/PresentationSurface")
    stage.GetRootLayer().SetPermissionToEdit(False)
    stage.GetRootLayer().SetPermissionToSave(False)
    entry_path = tmp_path / "candidate_static.usda"

    contract = replay.export_static_candidate_entry(
        stage,
        presentation_layer=presentation_layer,
        session_layer_baseline=session_layer_baseline,
        source_usd_path=source_path,
        expected_source_sha256=hashlib.sha256(source_bytes_before).hexdigest(),
        static_usd_path=entry_path,
        required_presentation_prim_path=(
            "/World/CompletedPBD/PresentationSurface"
        ),
        required_source_prim_path="/World/SourceTable",
    )

    assert source_path.read_bytes() == source_bytes_before
    assert stage.GetEditTarget().GetLayer().identifier == presentation_layer.identifier
    assert presentation_path.is_file()
    assert entry_path.is_file()
    assert contract["source_root_unchanged"] is True
    assert contract["presentation_layer_path"] == str(presentation_path.resolve())
    assert contract["static_entry_path"] == str(entry_path.resolve())
    assert len(contract["presentation_layer_sha256"]) == 64
    assert len(contract["static_entry_sha256"]) == 64
    recovery = replay.validate_presentation_layer_export_permission_recovery_contract(
        contract["presentation_layer_export_permission_recovery"]
    )
    assert recovery["status"] == "PASS"
    assert recovery["failure_stage"] is None
    assert recovery["recovery_attempted"] is False
    assert recovery["set_edit_attempted"] is False
    assert recovery["set_save_attempted"] is False
    assert recovery["save_attempted"] is True
    assert recovery["save_succeeded"] is True
    assert recovery["relock_attempted"] is True
    assert recovery["relock_succeeded"] is True
    assert recovery["presentation_permissions"]["after_relock"] == {
        "permission_to_edit": False,
        "permission_to_save": False,
    }
    assert presentation_layer.permissionToEdit is False
    assert presentation_layer.permissionToSave is False
    baseline = replay.validate_capture_persistent_layer_baseline(
        contract["capture_persistent_layer_baseline"]
    )
    assert {record["role"] for record in baseline["files"]} == {
        "presentation",
        "source",
        "static_entry",
    }
    assert baseline["files"] == sorted(
        baseline["files"], key=lambda record: record["path"]
    )
    assert all(record["link_count"] == 1 for record in baseline["files"])
    assert contract["source_sublayer_portable"] is True
    assert contract["source_sublayer_path_mode"] == "relative_cell_source_snapshot"
    assert not Path(contract["static_entry_source_sublayer_path"]).is_absolute()
    assert contract["requires_localization_before_colleague_delivery"] is False
    assert contract["stage_metadata_preserved"] is True
    assert contract["required_source_prim_resolved"] is True
    assert contract["source_root_layer_resolved"] is True
    session_contract = contract["session_layer_runtime_opinions"]
    assert session_contract["classification_gate_status"] == "PASS"
    assert session_contract["native_cleanup_status"] == (
        "NOT_APPLICABLE_AUTHOR_STAGE"
    )
    assert session_contract["session_delta_status"] == "CLEAN"
    assert session_contract["unexpected_spec_paths"] == []
    assert session_contract["presentation_sublayer_exact"] is True
    assert session_contract["physx_runtime_isosurface"]["present"] is False
    assert len(session_contract["baseline_snapshot_sha256"]) == 64
    assert len(session_contract["at_export_snapshot_sha256"]) == 64

    entry_layer = Sdf.Layer.FindOrOpen(str(entry_path))
    assert list(entry_layer.subLayerPaths) == [
        presentation_path.name,
        source_path.name,
    ]
    reopened = Usd.Stage.Open(str(entry_path))
    assert reopened.GetPrimAtPath("/World/SourceTable")
    assert reopened.GetPrimAtPath("/World/CompletedPBD/PresentationSurface")
    assert not reopened.GetPrimAtPath("/World/ParticleSystem/Isosurface")
    assert not reopened.GetPrimAtPath("/Orchestrator")
    assert not reopened.GetPrimAtPath("/Render/ReplicatorRuntime")
    assert reopened.GetDefaultPrim().GetPath() == Sdf.Path("/World")
    assert UsdGeom.GetStageUpAxis(reopened) == UsdGeom.Tokens.z
    assert UsdGeom.GetStageMetersPerUnit(reopened) == pytest.approx(1.0)
    assert reopened.GetStartTimeCode() == pytest.approx(10.0)
    assert reopened.GetEndTimeCode() == pytest.approx(20.0)
    assert reopened.GetTimeCodesPerSecond() == pytest.approx(60.0)
    assert reopened.GetFramesPerSecond() == pytest.approx(30.0)


def _permission_recovery_export_fixture(tmp_path):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    UsdGeom.Cube.Define(source_stage, "/World/SourceTable")
    source_stage.GetRootLayer().Save()
    source_bytes = source_path.read_bytes()
    stage = Usd.Stage.Open(str(source_path))
    baseline = replay.snapshot_session_layer(stage)
    presentation_path = tmp_path / "presentation.usda"
    presentation = replay.begin_candidate_presentation_layer(
        stage,
        presentation_path,
    )
    UsdGeom.Sphere.Define(stage, "/World/CompletedPBD/PresentationSurface")
    stage.GetRootLayer().SetPermissionToEdit(False)
    stage.GetRootLayer().SetPermissionToSave(False)
    return {
        "stage": stage,
        "source_path": source_path,
        "source_bytes": source_bytes,
        "baseline": baseline,
        "presentation": presentation,
        "presentation_path": presentation_path,
    }


@pytest.mark.parametrize(
    ("permission_to_edit", "permission_to_save"),
    [(False, True), (True, False), (False, False)],
)
def test_presentation_export_recovers_missing_permissions_and_relocks(
    tmp_path,
    permission_to_edit,
    permission_to_save,
):
    fixture = _permission_recovery_export_fixture(tmp_path)
    presentation = fixture["presentation"]
    presentation.SetPermissionToEdit(permission_to_edit)
    presentation.SetPermissionToSave(permission_to_save)
    identity_before = os.lstat(fixture["presentation_path"])

    contract = replay.export_static_candidate_entry(
        fixture["stage"],
        presentation_layer=presentation,
        session_layer_baseline=fixture["baseline"],
        source_usd_path=fixture["source_path"],
        expected_source_sha256=hashlib.sha256(
            fixture["source_bytes"]
        ).hexdigest(),
        expected_presentation_path=fixture["presentation_path"],
        static_usd_path=tmp_path / "static.usda",
        required_presentation_prim_path=(
            "/World/CompletedPBD/PresentationSurface"
        ),
        required_source_prim_path="/World/SourceTable",
    )

    recovery = replay.validate_presentation_layer_export_permission_recovery_contract(
        contract["presentation_layer_export_permission_recovery"]
    )
    identity_after = os.lstat(fixture["presentation_path"])
    assert recovery["status"] == "PASS"
    assert recovery["recovery_attempted"] is True
    assert recovery["set_edit_attempted"] is (not permission_to_edit)
    assert recovery["set_save_attempted"] is (not permission_to_save)
    assert recovery["set_edit_readback"] is (
        True if not permission_to_edit else None
    )
    assert recovery["set_save_readback"] is (
        True if not permission_to_save else None
    )
    assert recovery["presentation_path_identity"]["before_recovery"][
        "inode"
    ] == identity_before.st_ino
    assert recovery["presentation_path_identity"]["after_save"][
        "inode"
    ] == identity_after.st_ino
    assert recovery["presentation_path_identity"]["after_relock"] == recovery[
        "presentation_path_identity"
    ]["after_save"]
    assert fixture["source_path"].read_bytes() == fixture["source_bytes"]
    assert fixture["stage"].GetRootLayer().permissionToEdit is False
    assert fixture["stage"].GetRootLayer().permissionToSave is False
    assert presentation.permissionToEdit is False
    assert presentation.permissionToSave is False


def test_recovery_contract_validator_rejects_schema_and_state_mutations(tmp_path):
    fixture = _permission_recovery_export_fixture(tmp_path)
    fixture["presentation"].SetPermissionToSave(False)
    exported = replay.export_static_candidate_entry(
        fixture["stage"],
        presentation_layer=fixture["presentation"],
        session_layer_baseline=fixture["baseline"],
        source_usd_path=fixture["source_path"],
        expected_source_sha256=hashlib.sha256(
            fixture["source_bytes"]
        ).hexdigest(),
        expected_presentation_path=fixture["presentation_path"],
        static_usd_path=tmp_path / "static.usda",
        required_presentation_prim_path=(
            "/World/CompletedPBD/PresentationSurface"
        ),
        required_source_prim_path="/World/SourceTable",
    )
    valid = exported["presentation_layer_export_permission_recovery"]

    extra = json.loads(json.dumps(valid))
    extra["unexpected"] = True
    with pytest.raises(ValueError, match="permission_recovery.*schema"):
        replay.validate_presentation_layer_export_permission_recovery_contract(extra)

    inconsistent = json.loads(json.dumps(valid))
    inconsistent["relock_succeeded"] = False
    with pytest.raises(ValueError, match="permission_recovery.*invalid"):
        replay.validate_presentation_layer_export_permission_recovery_contract(
            inconsistent
        )

    impossible = replay._new_presentation_permission_recovery_contract()
    impossible["failure_stage"] = "SAVE"
    with pytest.raises(ValueError, match="permission_recovery.*invalid"):
        replay.validate_presentation_layer_export_permission_recovery_contract(
            impossible
        )


def test_relock_observation_failure_keeps_structured_recovery_error(
    tmp_path,
    monkeypatch,
):
    fixture = _permission_recovery_export_fixture(tmp_path)
    fixture["presentation"].SetPermissionToSave(False)
    original = replay._read_pinned_regular_file_evidence

    def fail_after_relock(path, *, label, expected_bytes=None):
        if label.endswith("_after_relock"):
            raise ValueError("injected_after_relock_observation_failure")
        return original(path, label=label, expected_bytes=expected_bytes)

    monkeypatch.setattr(
        replay,
        "_read_pinned_regular_file_evidence",
        fail_after_relock,
    )
    with pytest.raises(
        replay.PresentationLayerPermissionRecoveryError,
        match="permission_layer_permission_recovery_failed|permission_recovery_failed|presentation_layer_permission_recovery_failed",
    ) as error:
        replay.export_static_candidate_entry(
            fixture["stage"],
            presentation_layer=fixture["presentation"],
            session_layer_baseline=fixture["baseline"],
            source_usd_path=fixture["source_path"],
            expected_source_sha256=hashlib.sha256(
                fixture["source_bytes"]
            ).hexdigest(),
            expected_presentation_path=fixture["presentation_path"],
            static_usd_path=tmp_path / "static.usda",
            required_presentation_prim_path=(
                "/World/CompletedPBD/PresentationSurface"
            ),
            required_source_prim_path="/World/SourceTable",
        )

    contract = error.value.presentation_layer_export_permission_recovery
    assert contract["status"] == "FAIL"
    assert contract["failure_stage"] == "RELOCK"
    assert contract["relock_attempted"] is True
    assert contract["relock_succeeded"] is False
    assert contract["presentation_permissions"]["after_relock"] is None
    missing_relock = json.loads(json.dumps(contract))
    missing_relock["relock_attempted"] = False
    with pytest.raises(ValueError, match="permission_recovery.*invalid"):
        replay.validate_presentation_layer_export_permission_recovery_contract(
            missing_relock
        )
    contradictory = json.loads(json.dumps(contract))
    contradictory["relock_succeeded"] = True
    with pytest.raises(ValueError, match="permission_recovery.*invalid"):
        replay.validate_presentation_layer_export_permission_recovery_contract(
            contradictory
        )


def test_static_entry_export_rejects_late_session_scene_opinions(tmp_path):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    UsdGeom.Cube.Define(source_stage, "/World/SourceTable")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    session_layer_baseline = replay.snapshot_session_layer(stage)
    presentation = replay.begin_candidate_presentation_layer(
        stage,
        tmp_path / "presentation.usda",
    )
    UsdGeom.Sphere.Define(stage, "/World/CompletedPBD/PresentationSurface")
    stage.SetEditTarget(stage.GetSessionLayer())
    UsdGeom.Xform.Define(stage, "/LateSessionOpinion")
    stage.SetEditTarget(presentation)

    with pytest.raises(
        replay.SessionLayerValidationError,
        match="session_layer_scene_opinions_present_at_export",
    ) as error:
        replay.export_static_candidate_entry(
            stage,
            presentation_layer=presentation,
            session_layer_baseline=session_layer_baseline,
            source_usd_path=source_path,
            expected_source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
            static_usd_path=tmp_path / "static.usda",
            required_presentation_prim_path=(
                "/World/CompletedPBD/PresentationSurface"
            ),
            required_source_prim_path="/World/SourceTable",
        )

    assert "/LateSessionOpinion" in error.value.session_layer_contract[
        "unexpected_spec_paths"
    ]


def test_static_entry_export_rejects_arbitrary_world_sibling_beside_runtime_isosurface(
    tmp_path,
):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    UsdGeom.Xform.Define(source_stage, "/World/ParticleSystem")
    UsdGeom.Cube.Define(source_stage, "/World/SourceTable")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    session_layer_baseline = replay.snapshot_session_layer(stage)
    presentation = replay.begin_candidate_presentation_layer(
        stage,
        tmp_path / "presentation.usda",
    )
    UsdGeom.Sphere.Define(stage, "/World/CompletedPBD/PresentationSurface")
    stage.SetEditTarget(stage.GetSessionLayer())
    runtime_isosurface = UsdGeom.Mesh.Define(
        stage,
        "/World/ParticleSystem/Isosurface",
    )
    runtime_isosurface.CreateFaceVertexCountsAttr([3])
    runtime_isosurface.CreateFaceVertexIndicesAttr([0, 0, 0])
    runtime_isosurface.CreateNormalsAttr([(0.0, 0.0, 0.0)])
    runtime_isosurface.CreatePointsAttr([(0.0, 0.0, 0.0)])
    UsdGeom.Cube.Define(stage, "/World/UnexpectedSessionSceneEdit")
    stage.SetEditTarget(presentation)

    with pytest.raises(replay.SessionLayerValidationError) as error:
        replay.export_static_candidate_entry(
            stage,
            presentation_layer=presentation,
            session_layer_baseline=session_layer_baseline,
            source_usd_path=source_path,
            expected_source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
            static_usd_path=tmp_path / "static.usda",
            required_presentation_prim_path=(
                "/World/CompletedPBD/PresentationSurface"
            ),
            required_source_prim_path="/World/SourceTable",
        )

    assert any(
        path == "/World/UnexpectedSessionSceneEdit"
        or path.startswith("/World/UnexpectedSessionSceneEdit.")
        for path in error.value.session_layer_contract["unexpected_spec_paths"]
    )


def test_static_entry_export_rejects_external_source_byte_change_even_when_root_clean(
    tmp_path,
):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    UsdGeom.Cube.Define(source_stage, "/World/SourceTable")
    source_stage.GetRootLayer().Save()
    expected_source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    stage = Usd.Stage.Open(str(source_path))
    baseline = replay.snapshot_session_layer(stage)
    presentation = replay.begin_candidate_presentation_layer(
        stage,
        tmp_path / "presentation.usda",
    )
    UsdGeom.Sphere.Define(stage, "/World/CompletedPBD/PresentationSurface")
    source_path.write_text(
        source_path.read_text(encoding="utf-8") + "\n# external change\n",
        encoding="utf-8",
    )
    assert stage.GetRootLayer().dirty is False

    with pytest.raises(
        RuntimeError,
        match="source_file_sha256_changed_before_static_export",
    ):
        replay.export_static_candidate_entry(
            stage,
            presentation_layer=presentation,
            session_layer_baseline=baseline,
            source_usd_path=source_path,
            expected_source_sha256=expected_source_sha256,
            static_usd_path=tmp_path / "static.usda",
            required_presentation_prim_path=(
                "/World/CompletedPBD/PresentationSurface"
            ),
            required_source_prim_path="/World/SourceTable",
        )


def test_candidate_session_restore_returns_exact_baseline_for_next_candidate(
    tmp_path,
):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    stage.SetEditTarget(stage.GetSessionLayer())
    UsdGeom.Camera.Define(stage, "/OmniverseKit_Persp")
    stage.SetEditTarget(stage.GetRootLayer())
    baseline_snapshot = replay.snapshot_session_layer(stage)
    baseline_layer = replay.clone_session_layer(stage)
    presentation = replay.begin_candidate_presentation_layer(
        stage,
        tmp_path / "candidate_1_presentation.usda",
    )
    stage.SetEditTarget(stage.GetSessionLayer())
    UsdGeom.Scope.Define(stage, "/Orchestrator")
    UsdGeom.Scope.Define(stage, "/Render/ReplicatorRuntime")
    stage.SetEditTarget(presentation)

    restore = replay.restore_candidate_session_layer(
        stage,
        baseline_layer=baseline_layer,
        baseline_snapshot=baseline_snapshot,
    )

    assert restore["restored"] is True
    assert restore["restored_snapshot_sha256"] == baseline_snapshot[
        "snapshot_sha256"
    ]
    assert replay.snapshot_session_layer(stage) == baseline_snapshot
    assert stage.GetEditTarget().GetLayer().identifier == stage.GetRootLayer().identifier
    next_presentation = replay.begin_candidate_presentation_layer(
        stage,
        tmp_path / "candidate_2_presentation.usda",
    )
    assert stage.GetEditTarget().GetLayer().identifier == next_presentation.identifier


def test_disposable_capture_frame_layer_isolates_all_persistent_usd_files(tmp_path):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    source_stage.GetRootLayer().Save()

    presentation_path = tmp_path / "presentation.usda"
    presentation_stage = Usd.Stage.CreateNew(str(presentation_path))
    points = UsdGeom.Points.Define(
        presentation_stage,
        replay.PRESENTATION_POINTS_PATH,
    )
    points.CreatePointsAttr([(0.0, 0.0, 0.0)])
    points.CreateWidthsAttr([0.01])
    presentation_stage.GetRootLayer().Save()

    entry_path = tmp_path / "entry.usda"
    entry_layer = Sdf.Layer.CreateNew(str(entry_path))
    entry_layer.subLayerPaths = [presentation_path.name, source_path.name]
    entry_layer.Save()
    byte_hashes_before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (source_path, presentation_path, entry_path)
    }
    capture_stage = Usd.Stage.Open(str(entry_path))

    frame_layer = replay.begin_disposable_capture_frame_layer(
        capture_stage,
        candidate_id="OMNI_REF_FINE",
    )
    lock_contract = replay.lock_capture_persistent_layers(
        capture_stage,
        frame_layer=frame_layer,
        expected_file_sha256={
            str(path.resolve()): digest
            for path, digest in (
                (source_path, byte_hashes_before[source_path.name]),
                (presentation_path, byte_hashes_before[presentation_path.name]),
                (entry_path, byte_hashes_before[entry_path.name]),
            )
        },
    )
    capture_points = UsdGeom.Points(
        capture_stage.GetPrimAtPath(replay.PRESENTATION_POINTS_PATH)
    )
    capture_points.GetPointsAttr().Set([(0.1, 0.2, 0.3)])

    assert frame_layer.dirty is True
    assert capture_stage.GetEditTarget().GetLayer().identifier == frame_layer.identifier
    assert lock_contract["persistent_layer_count"] == 3
    assert lock_contract["all_persistent_layers_locked"] is True
    assert lock_contract["expected_file_sha256_verified"] is True
    assert capture_points.GetPointsAttr().Get() == [(0.1, 0.2, 0.3)]
    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (source_path, presentation_path, entry_path)
    } == byte_hashes_before
    assert all(
        not layer.dirty
        for layer in capture_stage.GetUsedLayers()
        if layer.realPath
    )


def test_capture_persistent_layer_verification_rejects_new_dependency(tmp_path):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    frame_layer = replay.begin_disposable_capture_frame_layer(
        stage,
        candidate_id="OMNI_REF_FINE",
    )
    lock_contract = replay.lock_capture_persistent_layers(
        stage,
        frame_layer=frame_layer,
    )
    late_layer = Sdf.Layer.CreateAnonymous("late_runtime_dependency")
    stage.GetSessionLayer().subLayerPaths.append(late_layer.identifier)

    with pytest.raises(
        RuntimeError,
        match="capture_used_layer_set_changed",
    ):
        replay.verify_capture_persistent_layers_unchanged(
            stage,
            lock_contract,
        )


def test_capture_lock_rejects_same_byte_replacement_against_export_baseline(tmp_path):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    source_stage.GetRootLayer().Save()
    presentation_path = tmp_path / "presentation.usda"
    presentation_stage = Usd.Stage.CreateNew(str(presentation_path))
    UsdGeom.Sphere.Define(presentation_stage, "/World/Surface")
    presentation_stage.GetRootLayer().Save()
    entry_path = tmp_path / "entry.usda"
    entry_layer = Sdf.Layer.CreateNew(str(entry_path))
    entry_layer.subLayerPaths = [presentation_path.name, source_path.name]
    entry_layer.Save()
    baseline = replay.build_capture_persistent_layer_baseline(
        source_path=source_path,
        presentation_path=presentation_path,
        static_entry_path=entry_path,
    )
    stage = Usd.Stage.Open(str(entry_path))
    frame_layer = replay.begin_disposable_capture_frame_layer(
        stage,
        candidate_id="OMNI_REF_FINE",
    )
    replacement = tmp_path / "replacement.usda"
    replacement.write_bytes(presentation_path.read_bytes())
    os.replace(replacement, presentation_path)

    with pytest.raises(
        RuntimeError,
        match="capture_persistent_layer_baseline_identity_mismatch",
    ):
        replay.lock_capture_persistent_layers(
            stage,
            frame_layer=frame_layer,
            expected_baseline=baseline,
        )


def test_capture_baseline_rejects_replacement_after_recovery_pin(tmp_path):
    source_path = tmp_path / "source.usda"
    presentation_path = tmp_path / "presentation.usda"
    entry_path = tmp_path / "entry.usda"
    for path, payload in (
        (source_path, b"source"),
        (presentation_path, b"presentation"),
        (entry_path, b"entry"),
    ):
        path.write_bytes(payload)
    source_evidence = replay._read_pinned_regular_file_evidence(
        source_path,
        label="test_source_pin",
    )
    presentation_evidence = replay._read_pinned_regular_file_evidence(
        presentation_path,
        label="test_presentation_pin",
    )
    replacement = tmp_path / "same-bytes.tmp"
    replacement.write_bytes(presentation_path.read_bytes())
    os.replace(replacement, presentation_path)

    with pytest.raises(
        ValueError,
        match="capture_persistent_layer_baseline_handoff_mismatch:presentation",
    ):
        replay.build_capture_persistent_layer_baseline(
            source_path=source_path,
            presentation_path=presentation_path,
            static_entry_path=entry_path,
            expected_source={
                **replay._path_identity_from_file_evidence(source_evidence),
                "sha256": source_evidence["sha256"],
            },
            expected_presentation={
                **replay._path_identity_from_file_evidence(presentation_evidence),
                "sha256": presentation_evidence["sha256"],
            },
        )


def test_pinned_evidence_read_rejects_intermediate_parent_swap(
    tmp_path,
    monkeypatch,
):
    live_parent = tmp_path / "live"
    replacement_parent = tmp_path / "replacement"
    moved_parent = tmp_path / "moved"
    live_parent.mkdir()
    replacement_parent.mkdir()
    target = live_parent / "evidence.bin"
    target.write_bytes(b"same-bytes")
    (replacement_parent / target.name).write_bytes(b"same-bytes")
    original_read = os.read
    swapped = False

    def swap_during_read(descriptor, size):
        nonlocal swapped
        if not swapped:
            swapped = True
            live_parent.rename(moved_parent)
            replacement_parent.rename(live_parent)
        return original_read(descriptor, size)

    monkeypatch.setattr(os, "read", swap_during_read)
    try:
        with pytest.raises(ValueError, match="component_changed"):
            replay._read_pinned_regular_file_evidence(
                target,
                label="parent_swap",
            )
    finally:
        if swapped:
            live_parent.rename(replacement_parent)
            moved_parent.rename(live_parent)


def test_capture_verifier_rejects_extra_hardlink_without_hash_change(tmp_path):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    frame_layer = replay.begin_disposable_capture_frame_layer(
        stage,
        candidate_id="OMNI_REF_FINE",
    )
    lock_contract = replay.lock_capture_persistent_layers(
        stage,
        frame_layer=frame_layer,
    )
    os.link(source_path, tmp_path / "same-inode-alias.usda")

    with pytest.raises(RuntimeError, match="capture_persistent_layer_identity_changed"):
        replay.verify_capture_persistent_layers_unchanged(stage, lock_contract)


def test_sdf_layer_snapshot_diff_detects_nested_field_changes():
    layer = Sdf.Layer.CreateAnonymous("session_audit")
    Sdf.CreatePrimInLayer(layer, "/Render/PostProcess")
    baseline = replay.snapshot_sdf_layer(layer)
    prim = layer.GetPrimAtPath("/Render/PostProcess")
    attribute = Sdf.AttributeSpec(
        prim,
        "runtimeValue",
        Sdf.ValueTypeNames.Int,
    )
    attribute.default = 1
    current = replay.snapshot_sdf_layer(layer)

    diff = replay.diff_layer_snapshots(baseline, current)

    assert diff["changed"] is True
    assert "/Render/PostProcess.runtimeValue" in diff["added_spec_paths"]
    assert diff["removed_spec_paths"] == []


def test_composed_world_fingerprint_persists_recomputable_scoped_payload(tmp_path):
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    cube = UsdGeom.Cube.Define(stage, "/World/Table")
    cube.CreateSizeAttr(1.25)
    inactive = UsdGeom.Xform.Define(stage, "/World/InactiveEvidence").GetPrim()
    inactive.SetActive(False)
    runtime_mesh = UsdGeom.Mesh.Define(
        stage,
        replay.PHYSX_RUNTIME_ISOSURFACE_PATH,
    )
    runtime_mesh.CreatePointsAttr([(9.0, 9.0, 9.0)])

    payload = replay.composed_world_fingerprint_payload(stage)
    summary = replay.composed_world_fingerprint(stage)
    artifact = replay.write_composed_world_fingerprint_artifact(
        stage,
        tmp_path / "world_fingerprint.json",
    )

    assert payload["algorithm"] == replay.COMPOSED_WORLD_FINGERPRINT_ALGORITHM
    assert payload["scope"]["root_prim_path"] == "/World"
    assert payload["scope"]["excluded_runtime_roots"] == [
        replay.PHYSX_RUNTIME_ISOSURFACE_PATH
    ]
    assert all(
        item["path"] != replay.PHYSX_RUNTIME_ISOSURFACE_PATH
        for item in payload["prims"]
    )
    assert any(item["path"] == "/World/InactiveEvidence" for item in payload["prims"])
    assert summary["sha256"] == replay._json_sha256(payload)
    assert replay.composed_world_fingerprint_from_payload(payload) == summary
    persisted = json.loads(Path(artifact["artifact_path"]).read_text())
    assert persisted["payload"] == payload
    assert persisted["payload_sha256"] == replay._json_sha256(payload)
    assert artifact["fingerprint"] == summary
    validation = replay.validate_composed_world_fingerprint_artifact(
        artifact["artifact_path"],
        expected_fingerprint=summary,
    )
    assert validation["validated"] is True
    compressed = replay.write_composed_world_fingerprint_artifact(
        stage,
        tmp_path / "world_fingerprint.json.gz",
    )
    assert Path(compressed["artifact_path"]).read_bytes().startswith(b"\x1f\x8b")
    assert replay.validate_composed_world_fingerprint_artifact(
        compressed["artifact_path"],
        expected_fingerprint=summary,
    )["validated"] is True


def test_disposable_capture_session_reports_residue_without_claiming_native_clean(
    tmp_path,
):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    UsdGeom.Xform.Define(source_stage, "/World/ParticleSystem")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    frame_layer = replay.begin_disposable_capture_frame_layer(
        stage,
        candidate_id="OMNI_REF_FINE",
    )
    baseline = replay.snapshot_session_layer(stage)
    stage.SetEditTarget(stage.GetSessionLayer())
    UsdGeom.Scope.Define(stage, "/Orchestrator")
    UsdGeom.Scope.Define(stage, "/Render/ReplicatorRuntime")
    runtime_isosurface = UsdGeom.Mesh.Define(
        stage,
        replay.PHYSX_RUNTIME_ISOSURFACE_PATH,
    )
    runtime_isosurface.CreateFaceVertexCountsAttr([3])
    runtime_isosurface.CreateFaceVertexIndicesAttr([0, 0, 0])
    runtime_isosurface.CreateNormalsAttr([(0.0, 0.0, 0.0)])
    runtime_isosurface.CreatePointsAttr([(0.0, 0.0, 0.0)])
    stage.SetEditTarget(frame_layer)

    contract = replay.build_capture_session_residue_contract(
        stage,
        baseline_snapshot=baseline,
        frame_layer=frame_layer,
    )

    assert contract["classification_gate_status"] == "PASS"
    assert contract["native_cleanup_status"] == "RESIDUAL"
    assert contract["session_delta_status"] == "RESIDUAL"
    assert contract["manual_restore_status"] == "NOT_RUN_DISPOSABLE_STAGE"
    assert contract["entry_isolation_status"] == (
        "PASS_STATIC_ENTRY_PREEXISTED_CAPTURE"
    )
    assert (
        contract[
            "composed_world_default_time_property_snapshot_equivalence_"
            "excluding_known_physx_runtime_status"
        ]
        == "PENDING"
    )
    assert contract["full_render_entry_equivalence_status"] == "NOT_CLAIMED"
    assert "render_entry_equivalence_status" not in contract
    assert contract["unclassified_scene_opinion_count"] == 0
    assert (
        "native_replicator_cleanup_removed_all_session_opinions=true"
        in contract["blocked_claims"]
    )


def test_capture_session_quiescence_requires_two_stable_post_cleanup_updates():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")

    class Timeline:
        @staticmethod
        def is_playing():
            return False

    class App:
        updates = 0

        def update(self):
            self.updates += 1
            if self.updates == 1:
                with Usd.EditContext(stage, stage.GetSessionLayer()):
                    prim = UsdGeom.Scope.Define(stage, "/Render/Settled")
                    prim.GetPrim().CreateAttribute(
                        "settled", Sdf.ValueTypeNames.Bool
                    ).Set(True)

    app = App()
    contract = replay.quiesce_capture_session(
        stage,
        app=app,
        timeline=Timeline(),
        minimum_updates=2,
        maximum_updates=4,
    )

    assert contract["quiescence_status"] == "PASS_STABLE_CONSECUTIVE_SNAPSHOTS"
    assert contract["stable_consecutive_snapshot_count"] >= 2
    assert contract["updates_executed"] >= 2
    assert contract["final_two_snapshot_sha256"][0] == (
        contract["final_two_snapshot_sha256"][1]
    )


def test_candidate_presentation_layer_rejects_preexisting_session_scene_opinions(
    tmp_path,
):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    stage.SetEditTarget(stage.GetSessionLayer())
    UsdGeom.Xform.Define(stage, "/SessionOnlySceneOpinion")

    with pytest.raises(RuntimeError, match="session_layer_scene_opinions_present"):
        replay.begin_candidate_presentation_layer(
            stage,
            tmp_path / "candidate_presentation.usda",
        )


def test_candidate_presentation_layer_allows_only_known_kit_runtime_session_roots(
    tmp_path,
):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    stage.SetEditTarget(stage.GetSessionLayer())
    for path in replay.ALLOWED_KIT_RUNTIME_SESSION_ROOT_PATHS:
        if path.startswith("/OmniverseKit_"):
            UsdGeom.Camera.Define(stage, path)
        else:
            UsdGeom.Scope.Define(stage, path)
    stage.SetEditTarget(stage.GetRootLayer())

    presentation = replay.begin_candidate_presentation_layer(
        stage,
        tmp_path / "presentation.usda",
    )

    assert stage.GetEditTarget().GetLayer().identifier == presentation.identifier


def test_native_mdl_retarget_respects_explicit_presentation_edit_target(tmp_path):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    shader = UsdShade.Shader.Define(source_stage, "/World/Looks/Glass/Shader")
    shader.GetPrim().CreateAttribute(
        "info:mdl:sourceAsset",
        Sdf.ValueTypeNames.Asset,
    ).Set(Sdf.AssetPath("OmniGlass.mdl"))
    shader.GetPrim().CreateAttribute(
        "info:mdl:sourceAsset:subIdentifier",
        Sdf.ValueTypeNames.Token,
    ).Set("OmniGlass")
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    presentation = replay.begin_candidate_presentation_layer(
        stage,
        tmp_path / "presentation.usda",
    )
    closure_base = tmp_path / "closure" / "Base"
    closure_base.mkdir(parents=True)
    (closure_base / "OmniGlass.mdl").write_text("mdl 1.0;\n", encoding="utf-8")

    guarded_stage = replay.presentation_layer_stage_proxy(stage, presentation)
    result = runner._retarget_stage_mdl_source_assets(
        guarded_stage,
        {"closure_base_dir": str(closure_base)},
    )

    assert result["retargeted_shader_count"] == 1
    assert stage.GetEditTarget().GetLayer().identifier == presentation.identifier
    assert stage.GetRootLayer().dirty is False
    assert presentation.dirty is True
    asset = stage.GetPrimAtPath("/World/Looks/Glass/Shader").GetAttribute(
        "info:mdl:sourceAsset"
    ).Get()
    assert Path(asset.path).resolve() == (closure_base / "OmniGlass.mdl").resolve()


def test_overlay_fluid_deactivation_blocks_weaker_source_relationship_targets(
    tmp_path,
):
    source_path = tmp_path / "source.usda"
    source_stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(source_stage, "/World")
    UsdGeom.Xform.Define(source_stage, "/World/fluid")
    sampler = UsdGeom.Xform.Define(
        source_stage, "/World/fluid/Cylinder"
    ).GetPrim()
    particle_set = UsdGeom.Points.Define(
        source_stage, runner.EVIDENCE_PARTICLE_SET_PATH
    ).GetPrim()
    UsdGeom.Xform.Define(source_stage, runner.EVIDENCE_PARTICLE_SYSTEM_PATH)
    sampler.CreateRelationship("physxParticleSampling:particles").SetTargets(
        [Sdf.Path(runner.EVIDENCE_PARTICLE_SET_PATH)]
    )
    particle_set.CreateRelationship("physxParticle:particleSystem").SetTargets(
        [Sdf.Path(runner.EVIDENCE_PARTICLE_SYSTEM_PATH)]
    )
    source_stage.GetRootLayer().Save()
    stage = Usd.Stage.Open(str(source_path))
    presentation = replay.begin_candidate_presentation_layer(
        stage,
        tmp_path / "presentation.usda",
    )

    result = replay.deactivate_source_fluid_prims_for_presentation(stage)

    assert result["ownership_isolation"]["verified"] is True
    assert stage.GetEditTarget().GetLayer().identifier == presentation.identifier
    assert stage.GetRootLayer().dirty is False
    assert presentation.dirty is True
    assert stage.GetPrimAtPath("/World/fluid/Cylinder").GetRelationship(
        "physxParticleSampling:particles"
    ).GetTargets() == []
    assert stage.GetPrimAtPath(runner.EVIDENCE_PARTICLE_SET_PATH).GetRelationship(
        "physxParticle:particleSystem"
    ).GetTargets() == []


def test_physical_particle_state_hash_covers_state_and_ignores_presentation_proxy():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    source = UsdGeom.Points.Define(stage, "/World/ParticleSet")
    source.CreatePointsAttr([(0.0, 0.0, 0.0), (0.1, 0.0, 0.0)])
    source.CreateVelocitiesAttr([(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)])
    source.CreateWidthsAttr([0.001, 0.001])
    ids = source.GetPrim().CreateAttribute("ids", Sdf.ValueTypeNames.Int64Array)
    ids.Set([1, 2])
    translate = UsdGeom.Xformable(source).AddTranslateOp()
    translate.Set((0.0, 0.0, 0.0))
    presentation = UsdGeom.Points.Define(
        stage,
        replay.PRESENTATION_POINTS_PATH,
    )
    presentation.CreatePointsAttr([(9.0, 9.0, 9.0)])

    baseline = replay.usd_observed_default_time_point_attributes_sha256(stage)
    presentation.GetPointsAttr().Set([(8.0, 8.0, 8.0)])
    assert replay.usd_observed_default_time_point_attributes_sha256(stage) == baseline

    mutations = [
        (source.GetPointsAttr(), [(0.0, 0.0, 0.0), (0.2, 0.0, 0.0)]),
        (source.GetVelocitiesAttr(), [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]),
        (source.GetWidthsAttr(), [0.001, 0.002]),
        (ids, [1, 3]),
        (translate.GetAttr(), (0.0, 0.0, 0.1)),
    ]
    for attribute, changed_value in mutations:
        original = attribute.Get()
        attribute.Set(changed_value)
        assert replay.usd_observed_default_time_point_attributes_sha256(stage) != baseline
        attribute.Set(original)
        assert replay.usd_observed_default_time_point_attributes_sha256(stage) == baseline


def test_physical_state_canonicalizer_hashes_nonfinite_usd_sentinels_stably():
    assert replay._canonical_usd_value(float("nan")) == {
        "nonfinite_float": "nan"
    }
    assert replay._canonical_usd_value(float("inf")) == {
        "nonfinite_float": "+inf"
    }
    assert replay._canonical_usd_value(float("-inf")) == {
        "nonfinite_float": "-inf"
    }
    first = replay._json_sha256(replay._canonical_usd_value([float("inf")]))
    second = replay._json_sha256(replay._canonical_usd_value([float("inf")]))
    assert first == second


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
    assert (
        presentation.GetPrim()
        .GetAttribute("labutopia:physicalTraceFrameIndex")
        .Get()
        == 10
    )
    assert (
        presentation.GetPrim().GetAttribute("labutopia:proxyGeometrySha256").Get()
        == replay.proxy_geometry_sha256(final_proxy)
    )

    initial_proxy = accepted.proxy_frame("OMNI_REF_RATIO_15", frame_offset=0)
    update = replay._set_presentation_frame(stage, initial_proxy, frame_index=0)
    assert update["physical_trace_frame_index"] == 0
    assert update["proxy_geometry_sha256"] == replay.proxy_geometry_sha256(
        initial_proxy
    )
    assert (
        presentation.GetPrim()
        .GetAttribute("labutopia:physicalTraceFrameIndex")
        .Get()
        == 0
    )
    assert (
        presentation.GetPrim().GetAttribute("labutopia:proxyGeometrySha256").Get()
        == update["proxy_geometry_sha256"]
    )
    verified = replay.verify_presentation_frame_binding(
        stage,
        initial_proxy,
        frame_index=0,
    )
    assert verified["actual_usd_geometry_sha256"] == update[
        "proxy_geometry_sha256"
    ]


def test_static_surface_candidate_authors_render_only_mesh_and_updates_stable_topology(
    tmp_path,
):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    contract = replay.build_candidate_replay_contracts(accepted)["OMNI_REF_SURFACE"]
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, "/World/Looks/A18OmniGlass")

    authored = replay.author_static_candidate_state(
        stage,
        accepted=accepted,
        candidate_contract=contract,
        material_path=str(material.GetPath()),
    )

    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(replay.PRESENTATION_SURFACE_PATH))
    assert mesh
    assert not stage.GetPrimAtPath(replay.PRESENTATION_POINTS_PATH)
    assert len(mesh.GetPointsAttr().Get()) == contract["frames"][-1]["proxy_count"]
    face_counts_before = list(mesh.GetFaceVertexCountsAttr().Get())
    face_indices_before = list(mesh.GetFaceVertexIndicesAttr().Get())
    final_points = list(mesh.GetPointsAttr().Get())

    initial_surface = accepted.proxy_frame("OMNI_REF_SURFACE", frame_offset=0)
    update = replay._set_presentation_frame(stage, initial_surface, frame_index=0)

    assert list(mesh.GetFaceVertexCountsAttr().Get()) == face_counts_before
    assert list(mesh.GetFaceVertexIndicesAttr().Get()) == face_indices_before
    assert list(mesh.GetPointsAttr().Get()) != final_points
    assert update["physical_trace_frame_index"] == 0
    assert update["proxy_geometry_sha256"] == replay.proxy_geometry_sha256(
        initial_surface
    )
    assert (
        mesh.GetPrim().GetAttribute("labutopia:physicalTraceFrameIndex").Get() == 0
    )
    assert (
        mesh.GetPrim().GetAttribute("labutopia:canonicalMeshSha256").Get()
        == initial_surface["canonical_mesh_sha256"]
    )
    assert (
        mesh.GetPrim().GetAttribute("labutopia:proxyGeometrySha256").Get()
        == update["proxy_geometry_sha256"]
    )
    verified = replay.verify_presentation_frame_binding(
        stage,
        initial_surface,
        frame_index=0,
    )
    assert verified["actual_usd_geometry_sha256"] == update[
        "proxy_geometry_sha256"
    ]
    assert authored["presentation_primitive_path"] == replay.PRESENTATION_SURFACE_PATH
    assert authored["physics_schema_applied_to_presentation"] is False
    assert authored["physical_volume_parity_claim_allowed"] is False


def test_static_display_fill_binds_model_identity_and_keeps_equal_count_geometry(
    tmp_path,
):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    contract = replay.build_candidate_replay_contracts(accepted)[
        "OMNI_REF_DISPLAY_FILL"
    ]
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Scope.Define(stage, "/World/Looks")
    material = UsdShade.Material.Define(stage, "/World/Looks/A18OmniGlass")

    authored = replay.author_static_candidate_state(
        stage,
        accepted=accepted,
        candidate_contract=contract,
        material_path=str(material.GetPath()),
    )
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(replay.PRESENTATION_SURFACE_PATH))
    final_points = list(mesh.GetPointsAttr().Get())
    final_proxy = accepted.proxy_frame("OMNI_REF_DISPLAY_FILL", frame_offset=-1)
    initial_proxy = accepted.proxy_frame("OMNI_REF_DISPLAY_FILL", frame_offset=0)

    assert initial_proxy["canonical_mesh_sha256"] == final_proxy[
        "canonical_mesh_sha256"
    ]
    assert replay.proxy_geometry_sha256(initial_proxy) == replay.proxy_geometry_sha256(
        final_proxy
    )
    update = replay._set_presentation_frame(stage, initial_proxy, frame_index=0)
    assert list(mesh.GetPointsAttr().Get()) == final_points
    assert update["surface_model_version"] == contract["surface_model_version"]
    assert update["surface_model_contract_sha256"] == contract[
        "surface_model_contract_sha256"
    ]
    assert mesh.GetPrim().GetAttribute("labutopia:surfaceModelVersion").Get() == (
        contract["surface_model_version"]
    )
    assert mesh.GetPrim().GetAttribute(
        "labutopia:surfaceModelContractSha256"
    ).Get() == contract["surface_model_contract_sha256"]
    verified = replay.verify_presentation_frame_binding(
        stage,
        initial_proxy,
        frame_index=0,
    )
    assert verified["surface_model_version"] == contract["surface_model_version"]
    assert verified["surface_model_contract_sha256"] == contract[
        "surface_model_contract_sha256"
    ]
    assert authored["surface_model_version"] == contract["surface_model_version"]
    assert authored["surface_model_contract_sha256"] == contract[
        "surface_model_contract_sha256"
    ]


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


def test_replay_render_step_forces_a_frame_without_advancing_timeline():
    class Timeline:
        def __init__(self):
            self.current_time = 3.25

        def is_playing(self):
            return False

        def get_current_time(self):
            return self.current_time

    class Orchestrator:
        def __init__(self):
            self.calls = []

        def step(self, **kwargs):
            self.calls.append(kwargs)

    timeline = Timeline()
    orchestrator = Orchestrator()

    contract = replay.step_static_render_frame(
        orchestrator=orchestrator,
        timeline=timeline,
        rt_subframes=1,
    )

    assert orchestrator.calls == [
        {"rt_subframes": 1, "pause_timeline": True, "delta_time": 0.0}
    ]
    assert contract == {
        "rt_subframes": 1,
        "timeline_time_before": 3.25,
        "timeline_time_after": 3.25,
        "timeline_advanced": False,
        "replicator_orchestrator_steps_executed": 1,
        "replicator_delta_time": 0.0,
        "physics_step_count_instrumented": False,
        "physics_steps_executed": None,
    }


def test_replay_render_step_rejects_any_timeline_advance():
    class Timeline:
        current_time = 1.0

        def is_playing(self):
            return False

        def get_current_time(self):
            return self.current_time

    timeline = Timeline()

    class AdvancingOrchestrator:
        def step(self, **_kwargs):
            timeline.current_time += 1.0 / 60.0

    with pytest.raises(RuntimeError, match="static_render_advanced_timeline"):
        replay.step_static_render_frame(
            orchestrator=AdvancingOrchestrator(),
            timeline=timeline,
            rt_subframes=1,
        )
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


def _write_beaker_normals_fixture(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source_path = tmp_path / "beaker_normals_source.usda"
    stage = Usd.Stage.CreateNew(str(source_path))
    UsdGeom.Xform.Define(stage, "/World")
    UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    material = UsdShade.Material.Define(stage, "/World/Looks/Glass")
    for index, name in enumerate(("beaker1", "beaker2")):
        parent = UsdGeom.Xform.Define(stage, f"/World/{name}")
        parent.AddTranslateOp().Set(Gf.Vec3d(0.2 + index * 0.1, 0.0, 0.8))
        parent.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 45.0))
        parent.AddScaleOp().Set(Gf.Vec3f(1.0, 1.0, 1.0))
        mesh = UsdGeom.Mesh.Define(stage, f"/World/{name}/mesh")
        mesh.CreatePointsAttr(
            [
                Gf.Vec3f(-0.03, -0.03, 0.0),
                Gf.Vec3f(0.03, -0.03, 0.0),
                Gf.Vec3f(0.03, 0.03, 0.0),
                Gf.Vec3f(-0.03, 0.03, 0.0),
                Gf.Vec3f(-0.03, -0.03, 0.08),
                Gf.Vec3f(0.03, -0.03, 0.08),
                Gf.Vec3f(0.03, 0.03, 0.08),
                Gf.Vec3f(-0.03, 0.03, 0.08),
            ]
        )
        mesh.CreateFaceVertexCountsAttr([4, 4, 4, 4, 4, 4])
        mesh.CreateFaceVertexIndicesAttr(
            [
                0,
                1,
                2,
                3,
                4,
                7,
                6,
                5,
                0,
                4,
                5,
                1,
                1,
                5,
                6,
                2,
                2,
                6,
                7,
                3,
                3,
                7,
                4,
                0,
            ]
        )
        mesh.CreateNormalsAttr(
            [Gf.Vec3f(0.0, 0.0, 1.0)] * 24
        )
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
        mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        mesh.CreateDoubleSidedAttr(True)
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
        UsdPhysics.RigidBodyAPI.Apply(mesh.GetPrim())
        UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
        mesh.GetPrim().CreateAttribute(
            "physxCollision:contactOffset", Sdf.ValueTypeNames.Float
        ).Set(0.002)
        mesh.GetPrim().CreateRelationship("physics:simulationOwner").SetTargets(
            [Sdf.Path("/World/PhysicsScene")]
        )
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    stage.GetRootLayer().Save()
    return source_path


def test_normal_value_block_scan_uses_explicit_default_time_code():
    from pxr import Usd

    observed = []

    class StrictPropertyStackAttribute:
        def GetPropertyStack(self, time_code):
            observed.append(time_code)
            return []

    assert replay._normal_value_block_layers(StrictPropertyStackAttribute()) == []
    assert len(observed) == 1
    assert observed[0] == Usd.TimeCode.Default()


def test_beaker_normals_block_is_presentation_only_and_hash_bound(tmp_path):
    source_path = _write_beaker_normals_fixture(tmp_path)
    source_bytes_before = source_path.read_bytes()
    stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)
    contract = replay.build_beaker_normals_block_contract(
        stage,
        source_usd_path=source_path,
        source_usd_sha256=hashlib.sha256(source_bytes_before).hexdigest(),
    )
    source_layers_before = contract["source_layer_stack"]
    presentation = replay.begin_candidate_presentation_layer(
        stage, tmp_path / "presentation.usda"
    )

    authored = replay.author_beaker_normals_block(
        stage,
        contract=contract,
        presentation_layer=presentation,
    )

    assert contract["normal_remediation_id"] == "beaker_normals_block_v1"
    assert contract["renderer_acceptance_scope"] == "isaacsim41_rtx"
    assert contract["mesh_paths"] == [
        "/World/beaker1/mesh",
        "/World/beaker2/mesh",
    ]
    assert contract["rtx_generated_normals_readback_claimed"] is False
    assert contract["rtx_generated_normals_hashed"] is False
    assert authored["verified"] is True
    assert authored["normal_remediation_id"] == "beaker_normals_block_v1"
    assert authored["source_layer_stack"] == source_layers_before
    assert source_path.read_bytes() == source_bytes_before
    for path in contract["mesh_paths"]:
        mesh = UsdGeom.Mesh(stage.GetPrimAtPath(path))
        assert mesh.GetNormalsAttr().Get() is None
        spec = presentation.GetAttributeAtPath(Sdf.Path(f"{path}.normals"))
        assert spec is not None
        assert isinstance(spec.default, Sdf.ValueBlock)
        signature = contract["source_mesh_signatures"][path]
        assert signature["normals_interpolation"] == "faceVarying"
        assert len(signature["points_sha256"]) == 64
        assert len(signature["topology_sha256"]) == 64
        assert len(signature["normals_sha256"]) == 64
        assert len(signature["physics_sha256"]) == 64

    verified = replay.verify_beaker_normals_block(stage, contract=contract)
    assert verified["verified"] is True
    assert verified["blocked_mesh_paths"] == contract["mesh_paths"]
    assert presentation.Save()
    entry_path = tmp_path / "static_entry.usda"
    entry = Sdf.Layer.CreateNew(str(entry_path))
    entry.defaultPrim = "World"
    entry.subLayerPaths = ["presentation.usda", source_path.name]
    assert entry.Save()
    reopened = Usd.Stage.Open(str(entry_path), Usd.Stage.LoadAll)
    reopened_verified = replay.verify_beaker_normals_block(
        reopened, contract=contract
    )
    assert reopened_verified["verified"] is True


def test_beaker_normals_block_rejects_wrong_edit_target(tmp_path):
    source_path = _write_beaker_normals_fixture(tmp_path)
    stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)
    contract = replay.build_beaker_normals_block_contract(
        stage,
        source_usd_path=source_path,
        source_usd_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )
    presentation = replay.begin_candidate_presentation_layer(
        stage, tmp_path / "presentation.usda"
    )
    stage.SetEditTarget(stage.GetRootLayer())

    with pytest.raises(RuntimeError, match="beaker_normals_block_edit_target_mismatch"):
        replay.author_beaker_normals_block(
            stage,
            contract=contract,
            presentation_layer=presentation,
        )


def test_beaker_normals_block_rejects_missing_or_preblocked_source_normals(tmp_path):
    source_path = _write_beaker_normals_fixture(tmp_path)
    stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)
    UsdGeom.Mesh(stage.GetPrimAtPath("/World/beaker1/mesh")).GetNormalsAttr().Clear()
    assert stage.GetRootLayer().Save()

    with pytest.raises(ValueError, match="beaker_source_normals_missing"):
        replay.build_beaker_normals_block_contract(
            stage,
            source_usd_path=source_path,
            source_usd_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        )

    source_path = _write_beaker_normals_fixture(tmp_path / "preblocked")
    stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)
    UsdGeom.Mesh(stage.GetPrimAtPath("/World/beaker1/mesh")).GetNormalsAttr().Block()
    assert stage.GetRootLayer().Save()
    with pytest.raises(ValueError, match="beaker_source_normals_preblocked"):
        replay.build_beaker_normals_block_contract(
            stage,
            source_usd_path=source_path,
            source_usd_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        )


def test_beaker_normals_block_rejects_changed_mesh_or_source_layer(tmp_path):
    source_path = _write_beaker_normals_fixture(tmp_path)
    stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)
    contract = replay.build_beaker_normals_block_contract(
        stage,
        source_usd_path=source_path,
        source_usd_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )
    presentation = replay.begin_candidate_presentation_layer(
        stage, tmp_path / "presentation.usda"
    )
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/World/beaker1/mesh"))
    changed_points = list(mesh.GetPointsAttr().Get())
    changed_points[0] = Gf.Vec3f(-0.04, -0.03, 0.0)
    mesh.GetPointsAttr().Set(changed_points)

    with pytest.raises(RuntimeError, match="beaker_normal_source_signature_changed"):
        replay.author_beaker_normals_block(
            stage,
            contract=contract,
            presentation_layer=presentation,
        )

    stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)
    contract = replay.build_beaker_normals_block_contract(
        stage,
        source_usd_path=source_path,
        source_usd_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )
    presentation = replay.begin_candidate_presentation_layer(
        stage, tmp_path / "presentation2.usda"
    )
    stage.GetRootLayer().SetPermissionToEdit(True)
    stage.SetEditTarget(stage.GetRootLayer())
    stage.GetPrimAtPath("/World").CreateAttribute(
        "test:sourceMutation", Sdf.ValueTypeNames.Bool, custom=True
    ).Set(True)
    stage.SetEditTarget(presentation)

    with pytest.raises(RuntimeError, match="beaker_normal_source_layers_changed"):
        replay.author_beaker_normals_block(
            stage,
            contract=contract,
            presentation_layer=presentation,
        )


def test_beaker_normals_block_rejects_partial_application(tmp_path):
    source_path = _write_beaker_normals_fixture(tmp_path)
    stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)
    contract = replay.build_beaker_normals_block_contract(
        stage,
        source_usd_path=source_path,
        source_usd_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )
    presentation = replay.begin_candidate_presentation_layer(
        stage, tmp_path / "presentation.usda"
    )
    replay.author_beaker_normals_block(
        stage,
        contract=contract,
        presentation_layer=presentation,
    )
    UsdGeom.Mesh(stage.GetPrimAtPath("/World/beaker1/mesh")).GetNormalsAttr().Clear()

    with pytest.raises(RuntimeError, match="beaker_normals_block_incomplete"):
        replay.verify_beaker_normals_block(stage, contract=contract)


def test_actual_support_aligned_source_has_required_face_varying_normals_contract():
    source_path = (
        Path(__file__).resolve().parents[1]
        / "outputs"
        / "usd_asset_packages"
        / "lab_001_level1_pour_support_aligned_v1_20260712"
        / "lab_001_level1_pour_support_aligned_v1.usda"
    )
    stage = Usd.Stage.Open(str(source_path), Usd.Stage.LoadAll)

    contract = replay.build_beaker_normals_block_contract(
        stage,
        source_usd_path=source_path,
        source_usd_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
    )

    assert contract["source_usd_sha256"] == (
        "3cd4f73913a600f2ac19c490080ac17ffcd395072a1e54101960803e8fa9939b"
    )
    assert all(
        signature["normals_interpolation"] == "faceVarying"
        for signature in contract["source_mesh_signatures"].values()
    )
    assert len(contract["beaker_normal_remediation_contract_sha256"]) == 64


HISTORICAL_BEAKER_NORMAL_CONTRACT_SHA256 = (
    "da174bdbe851d73346208c97babbc3f4a6ee09c1b4ee945afd7f15a36b6a8fcb"
)
RENDER_DIAGNOSTIC_EXPECTED_NORMAL_MATRIX_PROJECTION_SHA256 = (
    "7ac77839b4b9124fa07db5633998cf7512789f1fa7c79fbe81cd53ae98b33160"
)


def _load_recorded_beaker_normal_contract(relative_path: str) -> dict:
    manifest_path = Path(__file__).resolve().parents[1] / relative_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest["beaker_normal_remediation_contract"]


def _historical_beaker_normal_contract() -> dict:
    return _load_recorded_beaker_normal_contract(
        "docs/labutopia_lab_poc/evidence_manifests/"
        "real_beaker_display_fill_normal_block_support_aligned_20260712_002/"
        "OMNI_REF_DISPLAY_FILL/candidate_manifest.json"
    )


def _failed_005_beaker_normal_contract() -> dict:
    return _load_recorded_beaker_normal_contract(
        "docs/labutopia_lab_poc/evidence_manifests/"
        "real_beaker_ao_rt_matrix_v3_20260712_005/cells/"
        "A_0_AO0_RT4_CONTROL/OMNI_REF_DISPLAY_FILL/candidate_manifest.json"
    )


def _rebase_beaker_normal_contract(contract: dict, root: Path) -> dict:
    rebased = json.loads(json.dumps(contract, allow_nan=False))
    rebased["source_usd_path"] = str(root / "entry.usda")
    for index, layer in enumerate(rebased["source_layer_stack"]):
        layer_path = root / f"layer_{index}" / Path(layer["identifier"]).name
        layer["identifier"] = str(layer_path)
        layer["real_path"] = str(layer_path)
    rebased.pop("beaker_normal_remediation_contract_sha256")
    rebased["beaker_normal_remediation_contract_sha256"] = (
        replay.canonical_json_sha256_v1(rebased)
    )
    return rebased


def test_beaker_normal_matrix_projection_matches_historical_and_005_evidence():
    historical = _historical_beaker_normal_contract()
    failed_005 = _failed_005_beaker_normal_contract()

    assert historical["beaker_normal_remediation_contract_sha256"] == (
        HISTORICAL_BEAKER_NORMAL_CONTRACT_SHA256
    )
    assert failed_005["beaker_normal_remediation_contract_sha256"] != (
        HISTORICAL_BEAKER_NORMAL_CONTRACT_SHA256
    )
    historical_projection = (
        replay.build_beaker_normal_matrix_equivalence_projection(historical)
    )
    failed_005_projection = (
        replay.build_beaker_normal_matrix_equivalence_projection(failed_005)
    )

    assert historical_projection == failed_005_projection
    assert historical_projection["canonical_json_utf8_sha256"] == (
        RENDER_DIAGNOSTIC_EXPECTED_NORMAL_MATRIX_PROJECTION_SHA256
    )
    assert historical_projection["removed_json_pointers"] == [
        "/beaker_normal_remediation_contract_sha256",
        "/source_usd_path",
        "/source_layer_stack/*/identifier",
        "/source_layer_stack/*/real_path",
    ]


def test_beaker_normal_matrix_projection_is_stable_across_all_sixteen_cell_roots():
    historical = _historical_beaker_normal_contract()
    full_hashes = set()
    projection_hashes = set()
    for slot in replay.render_diagnostic_slots():
        rebased = _rebase_beaker_normal_contract(
            historical,
            Path("/matrix/cells") / slot["cell_name"] / "source_dependency_snapshot",
        )
        full_hashes.add(rebased["beaker_normal_remediation_contract_sha256"])
        projection_hashes.add(
            replay.build_beaker_normal_matrix_equivalence_projection(rebased)[
                "canonical_json_utf8_sha256"
            ]
        )

    assert len(full_hashes) == 16
    assert projection_hashes == {
        RENDER_DIAGNOSTIC_EXPECTED_NORMAL_MATRIX_PROJECTION_SHA256
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda contract: contract["source_layer_stack"][0].__setitem__(
            "content_sha256", "0" * 64
        ),
        lambda contract: contract["source_mesh_signatures"][
            "/World/beaker1/mesh"
        ].__setitem__("normals_sha256", "1" * 64),
        lambda contract: contract.__setitem__(
            "source_geometry_mutation_allowed", True
        ),
    ],
)
def test_beaker_normal_matrix_projection_rejects_stable_input_drift(mutation):
    changed = _historical_beaker_normal_contract()
    mutation(changed)
    changed.pop("beaker_normal_remediation_contract_sha256")
    changed["beaker_normal_remediation_contract_sha256"] = (
        replay.canonical_json_sha256_v1(changed)
    )

    projection = replay.build_beaker_normal_matrix_equivalence_projection(changed)

    assert projection["canonical_json_utf8_sha256"] != (
        RENDER_DIAGNOSTIC_EXPECTED_NORMAL_MATRIX_PROJECTION_SHA256
    )


def test_beaker_normal_matrix_projection_rejects_invalid_full_contract_self_hash():
    contract = _historical_beaker_normal_contract()
    contract["beaker_normal_remediation_contract_sha256"] = "0" * 64

    with pytest.raises(
        ValueError, match="beaker_normal_remediation_contract_sha256_mismatch"
    ):
        replay.build_beaker_normal_matrix_equivalence_projection(contract)


def _actual_support_aligned_authority_dir() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "labutopia_lab_poc"
        / "evidence_manifests"
        / "fluid_spike_real_beaker_static_hold_support_aligned_v1_20260712"
        / "accepted_authority_P4096_S2"
    )


def test_replay_loads_grounded_authority_only_from_committed_snapshot():
    accepted, authority_contract = (
        replay.load_and_validate_support_aligned_authority_bundle(
            _actual_support_aligned_authority_dir()
        )
    )

    assert authority_contract["authority_kind"] == (
        "support_aligned_p4096_s2_accepted_authority"
    )
    assert authority_contract["accepted_authority_bundle_sha256"] == (
        "edfbc37b108a5972d9ef6bbf3a306b4eea1ab71e872c9c58df8d51dfeda51605"
    )
    assert authority_contract["selected_cell_id"] == "P4096_S2"
    assert authority_contract["selected_particle_count"] == 4096
    assert authority_contract["selected_seed"] == 2
    assert authority_contract["layout_semantics"] == (
        "config_range_midpoint_support_aligned"
    )
    assert authority_contract["unique_runtime_particle_authority"] is True
    assert accepted.source_usd_sha256 == (
        "3cd4f73913a600f2ac19c490080ac17ffcd395072a1e54101960803e8fa9939b"
    )
    assert accepted.summary_path.parent.name == replay.RUNTIME_EVIDENCE_SNAPSHOT_DIR
    assert accepted.trace_path.parent == accepted.summary_path.parent
    assert accepted.accepted_authority_bundle_sha256 == authority_contract[
        "accepted_authority_bundle_sha256"
    ]
    assert accepted.accepted_authority_bundle_path == (
        _actual_support_aligned_authority_dir() / replay.AUTHORITY_BUNDLE_BASENAME
    ).resolve()


def test_replay_grounded_authority_identity_is_shared_by_all_five_candidates():
    accepted, authority_contract = (
        replay.load_and_validate_support_aligned_authority_bundle(
            _actual_support_aligned_authority_dir()
        )
    )

    contracts = replay.build_candidate_replay_contracts(accepted)

    assert tuple(contracts) == replay.REFERENCE_CANDIDATE_IDS
    assert all(
        contract["accepted_authority_bundle_sha256"]
        == authority_contract["accepted_authority_bundle_sha256"]
        for contract in contracts.values()
    )
    assert all(
        contract["layout_semantics"] == "config_range_midpoint_support_aligned"
        for contract in contracts.values()
    )
    assert all(
        contract["exact_expert_episode_layout"] is False
        for contract in contracts.values()
    )


def test_replay_prototype_candidate_contract_binds_b_lighting_effective_look():
    accepted, _authority_contract = (
        replay.load_and_validate_support_aligned_authority_bundle(
            _actual_support_aligned_authority_dir()
        )
    )
    look = replay.build_effective_replay_look_contract("B_LIGHTING")

    contracts = replay.build_candidate_replay_contracts(
        accepted,
        ("OMNI_REF_DISPLAY_FILL",),
        visual_prototype_only=True,
        effective_look_contract=look,
    )

    candidate = contracts["OMNI_REF_DISPLAY_FILL"]
    assert candidate["lighting_variant_id"] == "B_LIGHTING"
    assert candidate["effective_replay_look_contract"] == look
    assert candidate["effective_replay_look_contract_sha256"] == look[
        "effective_replay_look_contract_sha256"
    ]


def test_replay_effective_look_consistency_rejects_mixed_candidate_manifests():
    control = replay.build_effective_replay_look_contract("C_CONTROL")
    treatment = replay.build_effective_replay_look_contract("B_LIGHTING")
    manifest = {
        "lighting_variant_id": "C_CONTROL",
        "effective_replay_look_contract": control,
        "effective_replay_look_contract_sha256": control[
            "effective_replay_look_contract_sha256"
        ],
        "candidate_manifests": {
            "A": {
                "lighting_variant_id": "C_CONTROL",
                "effective_replay_look_contract": control,
                "effective_replay_look_contract_sha256": control[
                    "effective_replay_look_contract_sha256"
                ],
            }
        },
    }

    assert replay.validate_replay_effective_look_consistency(manifest)[
        "validated"
    ] is True
    manifest["candidate_manifests"]["B"] = {
        "lighting_variant_id": "B_LIGHTING",
        "effective_replay_look_contract": treatment,
        "effective_replay_look_contract_sha256": treatment[
            "effective_replay_look_contract_sha256"
        ],
    }
    with pytest.raises(ValueError, match="replay_effective_look_candidate_mismatch"):
        replay.validate_replay_effective_look_consistency(manifest)


def test_replay_parser_accepts_grounded_authority_without_old_matrix_inputs():
    args = replay.build_arg_parser().parse_args(
        ["--accepted-authority-bundle", str(_actual_support_aligned_authority_dir())]
    )

    assert args.accepted_authority_bundle == str(
        _actual_support_aligned_authority_dir()
    )
    assert args.accepted_summary is None
    assert args.accepted_matrix_manifest is None


def test_replay_grounded_authority_output_scope_is_supported_and_protected(
    tmp_path,
):
    authority_dir = tmp_path / "accepted_authority"
    authority_dir.mkdir()
    safe_args = replay.build_arg_parser().parse_args(
        [
            "--accepted-authority-bundle",
            str(authority_dir),
            "--out-root",
            str(tmp_path / "renders"),
        ]
    )

    out_root, manifest_path = replay._validate_output_scope(safe_args)

    assert out_root == (tmp_path / "renders").resolve()
    assert manifest_path == (tmp_path / "renders" / "replay_manifest.json").resolve()

    nested_args = replay.build_arg_parser().parse_args(
        [
            "--accepted-authority-bundle",
            str(authority_dir),
            "--out-root",
            str(authority_dir / "renders"),
        ]
    )
    with pytest.raises(ValueError, match="output_path_overlaps_accepted_authority"):
        replay._validate_output_scope(nested_args)


def test_replay_input_selector_rejects_mixed_or_missing_authority_modes():
    authority_path = str(_actual_support_aligned_authority_dir())
    mixed = replay.build_arg_parser().parse_args(
        [
            "--accepted-authority-bundle",
            authority_path,
            "--accepted-summary",
            "old-summary.json",
            "--accepted-matrix-manifest",
            "old-matrix.json",
        ]
    )
    with pytest.raises(ValueError, match="replay_authority_mode_ambiguous"):
        replay.load_replay_inputs_from_args(mixed, recompute_closure=False)

    missing = replay.build_arg_parser().parse_args([])
    with pytest.raises(ValueError, match="replay_authority_input_missing"):
        replay.load_replay_inputs_from_args(missing, recompute_closure=False)

    grounded = replay.build_arg_parser().parse_args(
        ["--accepted-authority-bundle", authority_path]
    )
    accepted, contract = replay.load_replay_inputs_from_args(
        grounded, recompute_closure=False
    )
    assert accepted.accepted_authority_bundle_sha256 == contract[
        "accepted_authority_bundle_sha256"
    ]


RENDER_DIAGNOSTIC_VARIANTS_FOR_TEST = (
    "AO0_RT4_CONTROL",
    "AO0_RT12",
    "AO1_RT4",
    "AO1_RT12",
)
RENDER_DIAGNOSTIC_EXPECTED_AUTHORITY_SHA256 = (
    "edfbc37b108a5972d9ef6bbf3a306b4eea1ab71e872c9c58df8d51dfeda51605"
)
RENDER_DIAGNOSTIC_EXPECTED_SOURCE_SHA256 = (
    "3cd4f73913a600f2ac19c490080ac17ffcd395072a1e54101960803e8fa9939b"
)
RENDER_DIAGNOSTIC_EXPECTED_TRACE_SHA256 = (
    "124492bbffa9cbc4134ba1ee3558f0e52eee9ea502797ed0fb8b32dd2ebda5fd"
)
RENDER_DIAGNOSTIC_EXPECTED_MATERIAL_ID = "omniglass_water_tint_a18_v1"
RENDER_DIAGNOSTIC_EXPECTED_MATERIAL_ID_SHA256 = (
    "1f14ab789f9372cc81a07ffd1bafdbc81355ced48cacd8f557003cc003c115d2"
)


def _render_diagnostic_args(variant="AO0_RT4_CONTROL", replicate="A", order=0):
    out_root = (
        replay.RENDER_DIAGNOSTIC_AGGREGATE_ROOT
        / "cells"
        / f"{replicate}_{order}_{variant}"
    )
    return replay.build_arg_parser().parse_args(
        [
            "--accepted-authority-bundle",
            str(replay.RENDER_DIAGNOSTIC_ACCEPTED_AUTHORITY_ROOT),
            "--out-root",
            str(out_root),
            "--candidates",
            "OMNI_REF_DISPLAY_FILL",
            "--visual-prototype-display-fill-only",
            "--visual-prototype-lighting-variant",
            "C_CONTROL",
            "--visual-prototype-render-diagnostic-variant",
            variant,
            "--render-diagnostic-experiment-id",
            replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
            "--render-diagnostic-replicate",
            replicate,
            "--render-diagnostic-order-index",
            str(order),
            "--headless",
        ]
    )


def test_render_diagnostic_matrix_constants_are_exact_and_balanced():
    assert replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID == (
        "real_beaker_ao_rt_matrix_v3_20260712_008"
    )
    evidence_root = (
        replay.REPO_ROOT
        / "docs/labutopia_lab_poc/evidence_manifests"
    )
    assert replay.RENDER_DIAGNOSTIC_AGGREGATE_ROOT == (
        evidence_root / replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID
    )
    assert replay.RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH == (
        evidence_root
        / "real_beaker_ao_rt_matrix_v3_20260712_008_implementation_identity.json"
    )
    assert replay.RENDER_DIAGNOSTIC_PRE_FREEZE_PATH == (
        evidence_root
        / "real_beaker_ao_rt_matrix_v3_20260712_008_protected_tree_freeze_pre.json"
    )
    assert replay.RENDER_DIAGNOSTIC_POST_FREEZE_PATH == (
        evidence_root
        / "real_beaker_ao_rt_matrix_v3_20260712_008_protected_tree_freeze_post.json"
    )
    assert replay.RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH == (
        evidence_root
        / ".real_beaker_ao_rt_matrix_v3_20260712_008.aggregate.lock"
    )
    assert replay.RENDER_DIAGNOSTIC_VARIANTS == RENDER_DIAGNOSTIC_VARIANTS_FOR_TEST
    assert replay.RENDER_DIAGNOSTIC_BALANCED_ORDER == {
        "A": (
            "AO0_RT4_CONTROL",
            "AO0_RT12",
            "AO1_RT4",
            "AO1_RT12",
        ),
        "B": (
            "AO1_RT12",
            "AO1_RT4",
            "AO0_RT12",
            "AO0_RT4_CONTROL",
        ),
        "C": (
            "AO0_RT12",
            "AO1_RT12",
            "AO0_RT4_CONTROL",
            "AO1_RT4",
        ),
        "D": (
            "AO1_RT4",
            "AO0_RT4_CONTROL",
            "AO1_RT12",
            "AO0_RT12",
        ),
    }
    for order_index in range(4):
        assert {
            replay.RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate][order_index]
            for replicate in ("A", "B", "C", "D")
        } == set(RENDER_DIAGNOSTIC_VARIANTS_FOR_TEST)


@pytest.mark.parametrize("variant", RENDER_DIAGNOSTIC_VARIANTS_FOR_TEST)
def test_render_diagnostic_parser_and_scope_bind_exact_cell_identity(variant):
    replicate, order = next(
        (replicate, order)
        for replicate, variants in replay.RENDER_DIAGNOSTIC_BALANCED_ORDER.items()
        for order, ordered_variant in enumerate(variants)
        if ordered_variant == variant
    )
    args = _render_diagnostic_args(variant, replicate, order)

    identity = replay.validate_render_diagnostic_cell_scope(args)
    look = replay._effective_look_contract_from_args(args)

    assert identity == {
        "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "render_diagnostic_variant_id": variant,
        "replicate": replicate,
        "execution_order_index": order,
        "cell_root": str(
            replay.RENDER_DIAGNOSTIC_AGGREGATE_ROOT
            / "cells"
            / f"{replicate}_{order}_{variant}"
        ),
    }
    assert look["schema_version"] == 2
    assert look["render_diagnostic_variant_id"] == variant
    assert look["normal_remediation_required"] is True
    assert look["normal_remediation_applied"] is True


@pytest.mark.parametrize(
    "value",
    ["", " ", "AO0_RT4_CONTROL ", "ao0_rt4_control", "AO2_RT4", "UNKNOWN"],
)
def test_render_diagnostic_parser_rejects_noncanonical_variant(value):
    with pytest.raises(SystemExit):
        replay.build_arg_parser().parse_args(
            ["--visual-prototype-render-diagnostic-variant", value]
        )


def test_render_diagnostic_parser_rejects_repeated_identity_options():
    repeated = (
        ("--visual-prototype-render-diagnostic-variant", "AO0_RT4_CONTROL"),
        ("--render-diagnostic-experiment-id", replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID),
        ("--render-diagnostic-replicate", "A"),
        ("--render-diagnostic-order-index", "0"),
    )
    for option, value in repeated:
        with pytest.raises(SystemExit):
            replay.build_arg_parser().parse_args([option, value, option, value])


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda args: setattr(args, "visual_prototype_display_fill_only", False), "scope"),
        (lambda args: setattr(args, "candidates", replay.DEFAULT_CANDIDATES), "scope"),
        (lambda args: setattr(args, "visual_prototype_lighting_variant", "B_LIGHTING"), "scope"),
        (lambda args: setattr(args, "render_diagnostic_experiment_id", "wrong"), "identity"),
        (lambda args: setattr(args, "render_diagnostic_order_index", 1), "order"),
        (lambda args: setattr(args, "out_root", "/tmp/wrong"), "cell_root"),
        (lambda args: setattr(args, "headless", False), "runtime_parameters"),
        (lambda args: setattr(args, "width", 959), "runtime_parameters"),
        (lambda args: setattr(args, "height", 539), "runtime_parameters"),
        (lambda args: setattr(args, "video_fps", 12.0), "runtime_parameters"),
        (lambda args: setattr(args, "warmup_updates", 7), "runtime_parameters"),
        (
            lambda args: setattr(args, "camera_warmup_updates", 7),
            "runtime_parameters",
        ),
    ],
)
def test_render_diagnostic_scope_rejects_mixed_or_wrong_tuple(mutate, error):
    args = _render_diagnostic_args()
    mutate(args)
    with pytest.raises(ValueError, match=f"render_diagnostic_.*{error}"):
        replay.validate_render_diagnostic_cell_scope(args)


def test_render_diagnostic_scope_fails_before_io_or_runtime(tmp_path, monkeypatch):
    args = _render_diagnostic_args()
    args.out_root = str(tmp_path / "wrong")
    calls = []
    monkeypatch.setattr(
        replay, "_validate_output_scope", lambda *_args: calls.append("output")
    )
    monkeypatch.setattr(
        replay,
        "load_replay_inputs_from_args",
        lambda *_args, **_kwargs: calls.append("input"),
    )
    monkeypatch.setattr(
        replay, "_run_runtime", lambda *_args, **_kwargs: calls.append("runtime")
    )

    with pytest.raises(ValueError, match="render_diagnostic_.*cell_root"):
        replay.run_replay_parent_launcher([], args)
    with pytest.raises(ValueError, match="render_diagnostic_.*cell_root"):
        replay.run_replay(args)
    assert calls == []
    assert not (tmp_path / "wrong").exists()


@pytest.mark.parametrize(
    ("variant", "ao_enabled", "rt_subframes"),
    [
        ("AO0_RT4_CONTROL", False, 4),
        ("AO0_RT12", False, 12),
        ("AO1_RT4", True, 4),
        ("AO1_RT12", True, 12),
    ],
)
def test_render_diagnostic_effective_look_binds_full_settings(
    variant, ao_enabled, rt_subframes
):
    look = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id=variant
    )
    settings = look["render_settings"]

    assert look["schema_version"] == 2
    assert look["render_diagnostic_variant_id"] == variant
    assert settings == {
        "rt_subframes": rt_subframes,
        "max_refraction_bounces": 12,
        "max_refraction_bounces_setting_path": (
            "/rtx/translucency/maxRefractionBounces"
        ),
        "ambient_occlusion_enabled": ao_enabled,
        "ambient_occlusion_setting_path": "/rtx/ambientOcclusion/enabled",
        "ambient_occlusion_ray_length": 5.0,
        "ambient_occlusion_ray_length_setting_path": (
            "/rtx/ambientOcclusion/rayLength"
        ),
        "ambient_occlusion_min_samples": 8,
        "ambient_occlusion_min_samples_setting_path": (
            "/rtx/ambientOcclusion/minSamples"
        ),
        "ambient_occlusion_max_samples": 16,
        "ambient_occlusion_max_samples_setting_path": (
            "/rtx/ambientOcclusion/maxSamples"
        ),
        "ambient_occlusion_denoiser_mode": 2,
        "ambient_occlusion_denoiser_mode_setting_path": (
            "/rtx/ambientOcclusion/denoiserMode"
        ),
        "shadows_enabled": True,
        "shadows_setting_path": "/rtx/shadows/enabled",
        "shadow_sample_count": 4,
        "shadow_sample_count_setting_path": "/rtx/shadows/sampleCount",
        "renderer_consumption_verification": "NOT_AVAILABLE_ISAACSIM41",
    }
    assert replay.validate_effective_replay_look_contract(look) == look


def test_render_diagnostic_projection_removes_exactly_five_json_pointers():
    projections = []
    for variant in RENDER_DIAGNOSTIC_VARIANTS_FOR_TEST:
        look = replay.build_effective_replay_look_contract(
            "C_CONTROL", render_diagnostic_variant_id=variant
        )
        projection = replay.build_effective_replay_look_matrix_projection(look)
        projections.append(projection)
        projected = projection["projected_contract"]
        assert "render_diagnostic_variant_id" not in projected
        assert "ambient_occlusion_enabled" not in projected["render_settings"]
        assert "rt_subframes" not in projected["render_settings"]
        assert "effective_replay_non_lighting_contract_sha256" not in projected
        assert "effective_replay_look_contract_sha256" not in projected

    assert len({item["canonical_json_utf8_sha256"] for item in projections}) == 1
    assert all(
        item["projected_contract"] == projections[0]["projected_contract"]
        for item in projections
    )

    missing = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id="AO0_RT4_CONTROL"
    )
    del missing["render_settings"]["rt_subframes"]
    with pytest.raises(ValueError, match="matrix_projection_pointer_missing"):
        replay.build_effective_replay_look_matrix_projection(missing)

    unexpected = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id="AO1_RT12"
    )
    unexpected["unexpected_retained_field"] = True
    retained = replay.build_effective_replay_look_matrix_projection(
        unexpected, validate_full_contract=False
    )
    assert retained["projected_contract"]["unexpected_retained_field"] is True


def test_render_diagnostic_kit_startup_arguments_are_canonical():
    look = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id="AO1_RT12"
    )
    assert replay.build_effective_replay_kit_startup_arguments(look) == [
        "--/rtx/ambientOcclusion/enabled=true",
        "--/rtx/ambientOcclusion/rayLength=5.0",
        "--/rtx/ambientOcclusion/minSamples=8",
        "--/rtx/ambientOcclusion/maxSamples=16",
        "--/rtx/ambientOcclusion/denoiserMode=2",
        "--/rtx/shadows/enabled=true",
        "--/rtx/shadows/sampleCount=4",
        "--/rtx/translucency/maxRefractionBounces=12",
    ]


def test_render_diagnostic_mdl_startup_arguments_pin_cell_local_closure(
    tmp_path,
):
    root = tmp_path / replay.VERSION_MATCHED_MDL_CLOSURE_DIRNAME
    base = root / "Base"
    module = root / "mdl" / "OmniSurface"
    base.mkdir(parents=True)
    module.mkdir(parents=True)
    closure = {
        "closure_root": str(root),
        "closure_base_dir": str(base),
        "closure_omnisurface_module_dir": str(module),
    }

    contract = replay.build_render_diagnostic_mdl_startup_arguments(closure)
    expected_paths = [str(root / "mdl"), str(base)]
    encoded_paths = json.dumps(expected_paths, separators=(",", ":"))

    assert contract == {
        "schema_version": 1,
        "search_paths": expected_paths,
        "startup_arguments": [
            f"--/app/mdl/additionalUserPaths={encoded_paths}",
            f"--/materialConfig/searchPaths/custom={encoded_paths}",
            f"--/renderer/mdl/searchPaths/custom={';'.join(expected_paths)}",
        ],
        "closure_paths_precede_default_paths": True,
    }
    argv = ["replay.py", "--runtime-child"]
    assert replay.install_render_diagnostic_mdl_startup_arguments(
        argv, closure
    ) == contract
    assert argv[-3:] == contract["startup_arguments"]
    with pytest.raises(ValueError, match="mdl_startup_argument_already_present"):
        replay.install_render_diagnostic_mdl_startup_arguments(argv, closure)


def test_render_diagnostic_mdl_search_path_readback_requires_closure_first(
    tmp_path,
):
    root = tmp_path / replay.VERSION_MATCHED_MDL_CLOSURE_DIRNAME
    base = root / "Base"
    module = root / "mdl" / "OmniSurface"
    base.mkdir(parents=True)
    module.mkdir(parents=True)
    contract = replay.build_render_diagnostic_mdl_startup_arguments(
        {
            "closure_root": str(root),
            "closure_base_dir": str(base),
            "closure_omnisurface_module_dir": str(module),
        }
    )

    class Settings:
        def __init__(self, *, prepend_live=False):
            paths = list(contract["search_paths"])
            if prepend_live:
                paths.insert(0, "/live/isaac/mdl")
            self.values = {
                "/app/mdl/additionalUserPaths": paths,
                "/materialConfig/searchPaths/custom": paths,
                "/renderer/mdl/searchPaths/custom": ";".join(paths),
            }

        def get(self, path):
            return self.values[path]

    verified = replay.validate_render_diagnostic_mdl_search_path_readback(
        Settings(), contract
    )
    assert verified["readback_verified"] is True
    assert verified["additional_user_paths_readback"][:2] == contract[
        "search_paths"
    ]
    with pytest.raises(
        RuntimeError, match="render_diagnostic_mdl_search_path_readback_mismatch"
    ):
        replay.validate_render_diagnostic_mdl_search_path_readback(
            Settings(prepend_live=True), contract
        )


def test_render_diagnostic_render_settings_require_exact_readback_types():
    class FakeSettings:
        def __init__(self):
            self.values = {}

        def set_bool(self, path, value):
            self.values[path] = value

        def set_int(self, path, value):
            self.values[path] = value

        def set_float(self, path, value):
            self.values[path] = value

        def get(self, path):
            return self.values.get(path)

    class FakeNative:
        @staticmethod
        def apply_presentation_render_settings(settings):
            settings.set_int(replay.REPLAY_REFRACTION_SETTING_PATH, 12)
            return {
                "setting_path": replay.REPLAY_REFRACTION_SETTING_PATH,
                "max_refraction_bounces": 12,
            }

    look = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id="AO1_RT12"
    )
    settings = FakeSettings()
    actual = replay.apply_and_validate_effective_replay_render_settings(
        settings, native=FakeNative, effective_look_contract=look
    )
    assert actual["validated"] is True
    assert actual["rt_subframes"] == 12
    assert actual["registry_readback"] == actual["requested_registry"]
    assert len(actual["registry_readback"]) == 8

    class WrongBoolSettings(FakeSettings):
        def get(self, path):
            value = super().get(path)
            if path == replay.REPLAY_AMBIENT_OCCLUSION_SETTING_PATH:
                return 1
            return value

    with pytest.raises(RuntimeError, match="render_settings_readback_type_mismatch"):
        replay.apply_and_validate_effective_replay_render_settings(
            WrongBoolSettings(), native=FakeNative, effective_look_contract=look
        )


def test_render_diagnostic_dry_plan_and_provenance_bind_full_identity():
    args = _render_diagnostic_args("AO1_RT12", "A", 3)
    args._execution_argv = [str(Path(replay.__file__).resolve()), "<test>"]

    plan = replay.build_dry_plan(args)
    provenance = replay.build_execution_provenance(args)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    look = plan["effective_replay_look_contract"]
    projection = replay.build_effective_replay_look_matrix_projection(look)

    assert plan["render_diagnostic_identity"] == identity
    assert plan["render_diagnostic_variant_id"] == "AO1_RT12"
    assert plan["effective_replay_look_matrix_projection"] == projection
    assert plan["kit_startup_arguments"] == (
        replay.build_effective_replay_kit_startup_arguments(look)
    )
    assert plan["diagnostic_lifecycle"] == {
        "standalone_final_evidence_authority": False,
        "exporter_admitted": False,
        "visual_selection_eligible": False,
        "formal_scope": False,
        "delivery_ready": False,
    }
    candidate = plan["candidate_contracts"]["OMNI_REF_DISPLAY_FILL"]
    assert candidate["render_diagnostic_variant_id"] == "AO1_RT12"
    assert candidate["effective_replay_look_matrix_projection_sha256"] == projection[
        "canonical_json_utf8_sha256"
    ]
    render_parameters = provenance["render_parameters"]
    assert render_parameters["render_diagnostic_identity"] == identity
    assert render_parameters["render_diagnostic_variant_id"] == "AO1_RT12"
    assert render_parameters["kit_startup_arguments"] == plan[
        "kit_startup_arguments"
    ]


def test_render_diagnostic_frame_binding_binds_variant_and_projection(tmp_path):
    frame_index = 30
    image_paths = {}
    for role in replay.CAPTURE_CAMERA_ROLES:
        path = tmp_path / role / f"frame_{frame_index:04d}.png"
        path.parent.mkdir()
        path.write_bytes(f"{role}-image".encode("ascii"))
        image_paths[role] = path
    record = {
        "step_index": frame_index,
        "particle_count": 1,
        "positions": [[0.0, 0.0, 0.0]],
    }
    proxy_update = {
        "physical_trace_frame_index": frame_index,
        "proxy_geometry_sha256": "a" * 64,
        "presentation_primitive_path": replay.PRESENTATION_SURFACE_PATH,
        "presentation_kind": "surface_mesh",
        "canonical_mesh_sha256": "c" * 64,
        "usd_geometry_binding": {
            "verified": True,
            "actual_usd_geometry_sha256": "a" * 64,
        },
        "usd_geometry_binding_after_capture": {
            "verified": True,
            "actual_usd_geometry_sha256": "a" * 64,
        },
    }
    look = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id="AO0_RT12"
    )

    binding = replay.build_capture_frame_binding(
        candidate_id="OMNI_REF_DISPLAY_FILL",
        frame_offset=1,
        record=record,
        physical_trace_sha256="b" * 64,
        proxy_update=proxy_update,
        image_paths=image_paths,
        effective_look_contract=look,
    )

    assert binding["render_diagnostic_variant_id"] == "AO0_RT12"
    assert binding["effective_replay_look_matrix_projection_sha256"] == (
        replay.build_effective_replay_look_matrix_projection(look)[
            "canonical_json_utf8_sha256"
        ]
    )


def test_render_diagnostic_consistency_rejects_mixed_direct_variant():
    look = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id="AO1_RT4"
    )
    projection = replay.build_effective_replay_look_matrix_projection(look)
    candidate = {
        "lighting_variant_id": "C_CONTROL",
        "render_diagnostic_variant_id": "AO1_RT4",
        "effective_replay_look_contract": look,
        "effective_replay_look_contract_sha256": look[
            "effective_replay_look_contract_sha256"
        ],
        "effective_replay_look_matrix_projection_sha256": projection[
            "canonical_json_utf8_sha256"
        ],
    }
    manifest = {
        **candidate,
        "candidate_manifests": {"OMNI_REF_DISPLAY_FILL": dict(candidate)},
    }
    assert replay.validate_replay_effective_look_consistency(manifest)[
        "render_diagnostic_variant_id"
    ] == "AO1_RT4"

    manifest["candidate_manifests"]["OMNI_REF_DISPLAY_FILL"][
        "render_diagnostic_variant_id"
    ] = "AO0_RT4_CONTROL"
    with pytest.raises(ValueError, match="replay_effective_look_candidate_mismatch"):
        replay.validate_replay_effective_look_consistency(manifest)


def test_render_diagnostic_runtime_failure_manifest_is_non_deliverable(tmp_path):
    summary_path, _summary, _records = _write_accepted_replay_input(tmp_path)
    accepted = replay.load_and_validate_accepted_replay(summary_path)
    look = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id="AO1_RT12"
    )
    args = types.SimpleNamespace(
        _active_candidate_id=None,
        _completed_candidate_ids=[],
        _last_replicator_cleanup=None,
        _timeline_checkpoint_observed=False,
        _effective_replay_look_contract=look,
        visual_prototype_render_diagnostic_variant="AO1_RT12",
        render_diagnostic_experiment_id=replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        render_diagnostic_replicate="A",
        render_diagnostic_order_index=3,
        out_root=str(
            replay.RENDER_DIAGNOSTIC_AGGREGATE_ROOT
            / "cells"
            / "A_3_AO1_RT12"
        ),
            manifest=None,
            accepted_authority_bundle=str(
                replay.RENDER_DIAGNOSTIC_ACCEPTED_AUTHORITY_ROOT
            ),
        visual_prototype_display_fill_only=True,
        candidates="OMNI_REF_DISPLAY_FILL",
        visual_prototype_lighting_variant="C_CONTROL",
        headless=True,
        width=960,
        height=540,
        video_fps=15.0,
        warmup_updates=8,
        camera_warmup_updates=8,
    )

    failure = replay.build_replay_runtime_failure_manifest(
        args,
        accepted,
        RuntimeError("diagnostic failure"),
        traceback_text="traceback",
    )

    assert failure["render_diagnostic_identity"][
        "render_diagnostic_variant_id"
    ] == "AO1_RT12"
    assert failure["render_diagnostic_variant_id"] == "AO1_RT12"
    assert failure["standalone_final_evidence_authority"] is False
    assert failure["exporter_admitted"] is False
    assert failure["visual_selection_eligible"] is False
    assert failure["formal_scope"] is False
    assert failure["delivery_ready"] is False


def test_render_diagnostic_startup_install_and_success_classification_are_closed():
    look = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id="AO1_RT12"
    )
    argv = ["replay.py", "--runtime-child"]
    installed = replay.install_effective_replay_kit_startup_arguments(argv, look)

    assert installed == replay.build_effective_replay_kit_startup_arguments(look)
    assert argv[-8:] == installed
    with pytest.raises(ValueError, match="kit_startup_argument_already_present"):
        replay.install_effective_replay_kit_startup_arguments(argv, look)
    assert replay.replay_success_classification(look) == (
        "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
    )
    assert replay.replay_success_classification(
        replay.build_effective_replay_look_contract("C_CONTROL")
    ) == "RENDER_COMPLETE_PENDING_VISUAL_REVIEW"


def _diagnostic_cell_evidence(variant, replicate, order_index, **overrides):
    ao_enabled, rt_subframes = replay.RENDER_DIAGNOSTIC_VARIANT_SETTINGS[variant]
    look = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id=variant
    )
    projection = replay.build_effective_replay_look_matrix_projection(look)
    payload = {
        "schema_version": 1,
        "manifest_type": "real_beaker_render_diagnostic_matrix_cell",
        "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "variant": variant,
        "replicate": replicate,
        "execution_order_index": order_index,
        "classification": "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW",
        "child_exit_code": 0,
        "cell_root": f"/matrix/cells/{replicate}_{order_index}_{variant}",
        "implementation_identity_sha256": "1" * 64,
        "source_usd_sha256": RENDER_DIAGNOSTIC_EXPECTED_SOURCE_SHA256,
        "authority_bundle_sha256": RENDER_DIAGNOSTIC_EXPECTED_AUTHORITY_SHA256,
        "physical_trace_sha256": RENDER_DIAGNOSTIC_EXPECTED_TRACE_SHA256,
        "normal_remediation_matrix_projection_sha256": (
            RENDER_DIAGNOSTIC_EXPECTED_NORMAL_MATRIX_PROJECTION_SHA256
        ),
        "liquid_material_sha256": RENDER_DIAGNOSTIC_EXPECTED_MATERIAL_ID_SHA256,
        "display_fill_geometry_sha256": "7" * 64,
        "camera_contract_sha256": "8" * 64,
        "effective_replay_look_contract_sha256": look[
            "effective_replay_look_contract_sha256"
        ],
        "effective_replay_look_matrix_projection_sha256": projection[
            "canonical_json_utf8_sha256"
        ],
        "render_settings_sha256": replay.canonical_json_sha256_v1(
            {"ao": ao_enabled, "rt": rt_subframes}
        ),
        "mdl_closure_sha256": "9" * 64,
        "runtime_identity_sha256": "a" * 64,
        "device_identity_sha256": "b" * 64,
        "process_identity_sha256": replay.canonical_json_sha256_v1(
            {"replicate": replicate, "order": order_index}
        ),
        "runtime_implementation_archive_sha256": "d" * 64,
        "runtime_bootstrap_sha256": "e" * 64,
        "source_dependency_closure_sha256": "f" * 64,
        "artifact_inventory_sha256": "0" * 64,
        "frame_bindings_sha256": "c" * 64,
        "media_index_sha256": replay.canonical_json_sha256_v1(
            {"variant": variant, "replicate": replicate}
        ),
        "stopped_timeline": True,
        "replicator_delta_time": 0.0,
        "default_time_points_unchanged": True,
        "standalone_final_evidence_authority": False,
        "exporter_admitted": False,
        "visual_selection_eligible": False,
        "formal_scope": False,
        "delivery_ready": False,
    }
    payload.update(overrides)
    return {
        **payload,
        "matrix_cell_evidence_sha256": replay.canonical_json_sha256_v1(payload),
    }


def _all_diagnostic_cell_evidence():
    return [
        _diagnostic_cell_evidence(variant, replicate, order_index)
        for replicate, ordered_variants in replay.RENDER_DIAGNOSTIC_BALANCED_ORDER.items()
        for order_index, variant in enumerate(ordered_variants)
    ]


def test_render_diagnostic_slots_are_exact_and_validate_cell_evidence():
    slots = replay.render_diagnostic_slots()
    assert len(slots) == 16
    assert slots[0] == {
        "variant": "AO0_RT4_CONTROL",
        "replicate": "A",
        "execution_order_index": 0,
        "cell_name": "A_0_AO0_RT4_CONTROL",
    }
    assert slots[-1] == {
        "variant": "AO0_RT12",
        "replicate": "D",
        "execution_order_index": 3,
        "cell_name": "D_3_AO0_RT12",
    }
    evidence = _diagnostic_cell_evidence("AO1_RT12", "A", 3)
    assert replay.validate_render_diagnostic_matrix_cell_evidence(evidence) == evidence

    tampered = dict(evidence)
    tampered["delivery_ready"] = True
    with pytest.raises(ValueError, match="matrix_cell_evidence_mismatch"):
        replay.validate_render_diagnostic_matrix_cell_evidence(tampered)


def test_render_diagnostic_matrix_closure_requires_exact_equal_sixteen_cells():
    cells = _all_diagnostic_cell_evidence()
    validation = replay.validate_render_diagnostic_matrix_closure(cells)
    assert validation["status"] == "PASS"
    assert validation["exact_slot_closure"] is True
    assert validation["all_cells_successful"] is True
    assert validation["projection_byte_equality"] is True
    assert all(check["status"] == "PASS" for check in validation["equality_checks"])

    missing = replay.validate_render_diagnostic_matrix_closure(cells[:-1])
    assert missing["status"] == "FAIL"
    assert missing["exact_slot_closure"] is False

    mixed = [dict(cell) for cell in cells]
    changed_material_id = "omniglass_water_tint_a18_v2"
    mixed[-1] = _diagnostic_cell_evidence(
        mixed[-1]["variant"],
        mixed[-1]["replicate"],
        mixed[-1]["execution_order_index"],
        liquid_material_sha256=replay.canonical_json_sha256_v1(
            changed_material_id
        ),
    )
    mismatch = replay.validate_render_diagnostic_matrix_closure(mixed)
    assert mismatch["status"] == "FAIL"
    assert next(
        check for check in mismatch["equality_checks"] if check["name"] == "liquid_material"
    )["status"] == "FAIL"


def test_render_diagnostic_launch_intent_is_create_exclusive(tmp_path, monkeypatch):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)

    intent = replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256="e" * 64,
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    intent_path = aggregate / "launch_intents" / "A_0_AO0_RT4_CONTROL.json"
    assert intent_path.is_file()
    assert intent["launch_intent_sha256"] == replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in intent.items()
            if key not in {"generated_at_utc", "launch_intent_sha256"}
        }
    )
    assert not Path(identity["cell_root"]).exists()
    with pytest.raises(FileExistsError):
        replay.write_render_diagnostic_launch_intent(
            identity,
            implementation_identity_sha256="e" * 64,
            pre_freeze_sha256="f" * 64,
            launcher_pid=123,
            generated_at_utc="2026-07-12T00:00:00+00:00",
        )


def _diagnostic_image_lookup(tmp_path, *, altered_key=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    base = tmp_path / "base.png"
    Image.new("RGB", (8, 8), (30, 180, 210)).save(base)
    altered = tmp_path / "altered.png"
    Image.new("RGB", (8, 8), (250, 0, 0)).save(altered)
    return {
        (variant, replicate, view, frame): (
            altered
            if altered_key == (variant, replicate, view, frame)
            else base
        )
        for variant in replay.RENDER_DIAGNOSTIC_VARIANTS
        for replicate in replay.RENDER_DIAGNOSTIC_REPLICATES
        for view in replay.RENDER_DIAGNOSTIC_REVIEW_VIEWS
        for frame in replay.RENDER_DIAGNOSTIC_REVIEW_FRAMES
    }


def test_render_diagnostic_repeat_stability_uses_all_144_pairs(tmp_path):
    stable = replay.compute_render_diagnostic_repeat_stability(
        _diagnostic_image_lookup(tmp_path)
    )
    assert stable["status"] == "PASS"
    assert len(stable["comparisons"]) == 144
    assert all(item["rgb_mae"] == 0.0 for item in stable["comparisons"])
    assert all(item["psnr_db"] == "INF" for item in stable["comparisons"])

    unstable = replay.compute_render_diagnostic_repeat_stability(
        _diagnostic_image_lookup(
            tmp_path,
            altered_key=("AO1_RT12", "D", "context", 600),
        )
    )
    assert unstable["status"] == "FAIL"
    assert any(item["status"] == "FAIL" for item in unstable["comparisons"])


def _blind_review_inputs(*, failing_panel_id=None):
    label_map = {
        "schema_version": 1,
        "labels": [
            {"blinded_label": f"L{index}", "variant": variant}
            for index, variant in enumerate(replay.RENDER_DIAGNOSTIC_VARIANTS)
        ],
    }
    panels = []
    verdicts = []
    for replicate in replay.RENDER_DIAGNOSTIC_REPLICATES:
        for view in replay.RENDER_DIAGNOSTIC_REVIEW_VIEWS:
            for frame in replay.RENDER_DIAGNOSTIC_REVIEW_FRAME_LABELS:
                for column, variant in enumerate(replay.RENDER_DIAGNOSTIC_VARIANTS):
                    label = f"L{column}"
                    panel_id = f"{replicate}/{view}/{frame}/column_{column}/{label}"
                    source_hash = replay.canonical_json_sha256_v1(
                        {"panel_id": panel_id}
                    )
                    panels.append(
                        {
                            "panel_id": panel_id,
                            "replicate": replicate,
                            "view": view,
                            "frame": frame,
                            "blinded_column": column,
                            "sheet_sha256": "f" * 64,
                            "blinded_label": label,
                            "source_png_path": f"/images/{variant}/{panel_id}.png",
                            "source_png_sha256": source_hash,
                        }
                    )
                    hard_flags = {
                        "top_is_nearly_black": panel_id == failing_panel_id,
                        "body_is_ink_like": False,
                        "cyan_top_not_readable": False,
                    }
                    verdicts.append(
                        {
                            "panel_id": panel_id,
                            "source_png_sha256": source_hash,
                            "material_verdict": (
                                "FAIL" if panel_id == failing_panel_id else "PASS"
                            ),
                            "hard_flags": hard_flags,
                            "containment_and_grounding": "PASS",
                            "external_liquid_visible": False,
                            "penetration_visible": False,
                            "starburst_visible": False,
                            "broken_normal_visible": False,
                            "framing_blocker_visible": False,
                            "visible_evidence": ["determinate panel"],
                        }
                    )
    return (
        {"schema_version": 1, "panels": panels},
        label_map,
        sorted(verdicts, key=lambda item: item["panel_id"]),
    )


def test_render_diagnostic_blind_unblinding_and_gate_derivation_are_exact():
    panel_map, label_map, verdicts = _blind_review_inputs()
    review = replay.derive_render_diagnostic_visual_gates(
        panel_map=panel_map,
        blinded_label_map=label_map,
        raw_blinded_verdicts=verdicts,
    )
    assert len(verdicts) == 96
    assert all(
        gate == "PASS" for gate in review["configuration_gates"].values()
    )
    assert review["verdicts"]["AO0_RT4_CONTROL"]["A"]["context"]["0000"][
        "material_verdict"
    ] == "PASS"

    failing_id = "A/context/0000/column_0/L0"
    panel_map, label_map, verdicts = _blind_review_inputs(
        failing_panel_id=failing_id
    )
    mixed = replay.derive_render_diagnostic_visual_gates(
        panel_map=panel_map,
        blinded_label_map=label_map,
        raw_blinded_verdicts=verdicts,
    )
    assert mixed["replicate_gates"]["AO0_RT4_CONTROL"]["A"] == "FAIL"
    assert mixed["configuration_gates"]["AO0_RT4_CONTROL"] == "INDETERMINATE"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"protected_inputs_match": False}, "STOP_PROTECTED_INPUT_MUTATION"),
        ({"all_launched_cells_successful": False}, "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"),
        ({"matrix_status": "FAIL"}, "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED"),
        ({"repeat_status": "FAIL"}, "INDETERMINATE_REPEAT"),
        ({"configuration_gates": None}, "INDETERMINATE_VISUAL_REVIEW"),
        (
            {"configuration_gates": {variant: "FAIL" for variant in RENDER_DIAGNOSTIC_VARIANTS_FOR_TEST}},
            "FAIL_NO_RENDER_SETTING_RECOVERY",
        ),
        (
            {
                "configuration_gates": {
                    **{variant: "FAIL" for variant in RENDER_DIAGNOSTIC_VARIANTS_FOR_TEST},
                    "AO0_RT12": "PASS",
                }
            },
            "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC",
        ),
    ],
)
def test_render_diagnostic_terminal_state_precedence(kwargs, expected):
    defaults = {
        "protected_inputs_match": True,
        "all_launched_cells_successful": True,
        "matrix_status": "PASS",
        "repeat_status": "PASS",
        "configuration_gates": {
            variant: "PASS" for variant in RENDER_DIAGNOSTIC_VARIANTS_FOR_TEST
        },
    }
    defaults.update(kwargs)
    decision = replay.resolve_render_diagnostic_terminal_state(**defaults)
    assert decision["code"] == expected
    assert len(decision["evaluated_predicates"]) == 7
    winner = decision["precedence_index"] - 2
    assert decision["evaluated_predicates"][winner]["result"] == "TRUE"
    assert all(
        item["result"] == "NOT_REACHED"
        for item in decision["evaluated_predicates"][winner + 1 :]
    )


def test_render_diagnostic_aggregate_parser_is_closed(tmp_path, monkeypatch):
    pre = tmp_path / "pre.json"
    post = tmp_path / "post.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", post)
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
    )
    args = replay.build_arg_parser().parse_args(
        [
            "--render-diagnostic-aggregate-only",
            "--render-diagnostic-experiment-root",
            str(replay.RENDER_DIAGNOSTIC_AGGREGATE_ROOT),
            "--render-diagnostic-pre-freeze",
            str(pre),
            "--render-diagnostic-post-freeze",
            str(post),
        ]
    )
    scope = replay.validate_render_diagnostic_aggregate_scope(args)
    assert scope["experiment_root"] == str(replay.RENDER_DIAGNOSTIC_AGGREGATE_ROOT)
    assert scope["review_record"] is None

    args.width = 123
    with pytest.raises(ValueError, match="aggregate_scope_mixed_option"):
        replay.validate_render_diagnostic_aggregate_scope(args)


def test_render_diagnostic_implementation_identity_has_exact_membership():
    identity = replay.build_matrix_implementation_identity_v1()
    paths = [record["path"] for record in identity["files"]]
    expected_tool_paths = sorted(
        [
            str(path.relative_to(replay.REPO_ROOT))
            for path in (replay.REPO_ROOT / "tools/labutopia_fluid").glob("*.py")
            if path.is_file() and not path.is_symlink()
        ]
        + [
            "tools/labutopia_fluid/run_sealed_child_with_pipe_log.sh",
            "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_003.sh",
            "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_004.sh",
            "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_005.sh",
            "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_006.sh",
            "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_007.sh",
            "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_008.sh",
        ]
    )

    assert identity["schema_version"] == 1
    assert identity["identity_id"] == "matrix_implementation_identity_v1"
    assert paths == sorted(paths)
    assert [path for path in paths if path.startswith("tools/labutopia_fluid/")] == (
        expected_tool_paths
    )
    assert {
        "tests/test_real_beaker_runtime_contract.py",
        "tests/test_omniglass_reference.py",
        "tests/test_real_beaker.py",
        "tests/test_real_beaker_matrix_isaac_runtime.py",
        "tests/test_real_beaker_strict_step_schedule.py",
        "tests/test_fluid_colleague_native_usd_completed_pbd_step_video.py",
        "tests/test_level1_pour_support_aligned_scene.py",
        "tests/test_support_aligned_authority_bundle.py",
        "docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-plan-v3.md",
        "docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-hardening-plan.md",
        "tools/labutopia_fluid/run_sealed_child_with_pipe_log.sh",
        "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_003.sh",
        "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_004.sh",
        "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_005.sh",
        "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_006.sh",
        "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_007.sh",
        "tools/labutopia_fluid/run_real_beaker_ao_rt_matrix_v3_008.sh",
        "docs/runs/2026-07-13-real-beaker-presentation-layer-save-recovery-plan.md",
        "docs/runs/2026-07-13-real-beaker-presentation-layer-file-mode-plan.md",
        "docs/runs/2026-07-13-real-beaker-normal-equivalence-projection-plan.md",
        "docs/runs/2026-07-13-real-beaker-material-id-hash-plan.md",
        "docs/runs/2026-07-13-real-beaker-parent-pxr-closure-plan.md",
    }.issubset(paths)
    assert identity["implementation_identity_sha256"] == (
        replay.canonical_json_sha256_v1(
            {
                "schema_version": 1,
                "identity_id": "matrix_implementation_identity_v1",
                "files": identity["files"],
            }
        )
    )
    verified = replay.verify_matrix_implementation_identity_unchanged(identity)
    assert verified["verified"] is True
    assert verified["implementation_identity_sha256"] == identity[
        "implementation_identity_sha256"
    ]


def test_render_diagnostic_008_constants_and_007_protection_are_exact():
    evidence_root = replay.REPO_ROOT / "docs/labutopia_lab_poc/evidence_manifests"
    historical_root = evidence_root / "real_beaker_ao_rt_matrix_v3_20260712_007"
    expected_historical_files = {
        evidence_root
        / "real_beaker_ao_rt_matrix_v3_20260712_007_implementation_identity.json",
        evidence_root
        / "real_beaker_ao_rt_matrix_v3_20260712_007_protected_tree_freeze_pre.json",
        evidence_root
        / "real_beaker_ao_rt_matrix_v3_20260712_007_protected_tree_freeze_post.json",
        evidence_root / ".real_beaker_ao_rt_matrix_v3_20260712_007.aggregate.lock",
    }

    assert replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID == (
        "real_beaker_ao_rt_matrix_v3_20260712_008"
    )
    assert replay.RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID == (
        "real_beaker_ao_rt_matrix_v3_protected_registry_v6"
    )
    assert historical_root in replay.RENDER_DIAGNOSTIC_PROTECTED_ROOTS
    assert expected_historical_files.issubset(
        set(replay.RENDER_DIAGNOSTIC_PROTECTED_FILES)
    )
    assert replay.RENDER_DIAGNOSTIC_AGGREGATE_ROOT == (
        evidence_root / replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID
    )
    assert "_008" in replay.RENDER_DIAGNOSTIC_PRE_FREEZE_PATH.name
    assert "_008" in replay.RENDER_DIAGNOSTIC_POST_FREEZE_PATH.name
    assert "_008" in replay.RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH.name


def test_historical_003_terminal_attestation_validates_exact_bytes_and_semantics():
    validated = replay.validate_historical_003_terminal_attestation()

    assert validated["experiment_id"] == (
        "real_beaker_ao_rt_matrix_v3_20260712_003"
    )
    assert validated["terminal_state"]["code"] == (
        "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
    )
    statuses = [item["status"] for item in validated["cell_status_index"]["cells"]]
    assert statuses.count("FAILED") == 1
    assert statuses.count("NOT_LAUNCHED") == 15
    assert len(validated["aggregate_tree_files"]) == 349


def test_historical_004_terminal_state_validates_exact_semantics():
    validated = replay.validate_historical_004_terminal_state()

    assert validated["experiment_id"] == (
        "real_beaker_ao_rt_matrix_v3_20260712_004"
    )
    assert validated["terminal_state"]["code"] == (
        "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
    )
    statuses = [item["status"] for item in validated["cell_status_index"]["cells"]]
    assert statuses.count("FAILED") == 1
    assert statuses.count("NOT_LAUNCHED") == 15


def test_historical_004_terminal_state_rejects_stale_decision_self_hash(
    monkeypatch,
):
    original = replay._load_json_object

    def load_with_mutated_decision(path, *, label):
        actual = original(path, label=label)
        if label == "historical_004_matrix_decision":
            actual["operational_preference"] = list(
                reversed(actual["operational_preference"])
            )
        return actual

    monkeypatch.setattr(replay, "_load_json_object", load_with_mutated_decision)
    with pytest.raises(ValueError, match="historical_004_terminal_state_invalid"):
        replay.validate_historical_004_terminal_state()


def test_historical_004_terminal_state_rejects_external_file_hash_drift(
    monkeypatch,
):
    original = replay._sha256_file

    def hash_with_lock_drift(path):
        if Path(path).name == (
            ".real_beaker_ao_rt_matrix_v3_20260712_004.aggregate.lock"
        ):
            return "0" * 64
        return original(path)

    monkeypatch.setattr(replay, "_sha256_file", hash_with_lock_drift)
    with pytest.raises(ValueError, match="historical_004_terminal_state_invalid"):
        replay.validate_historical_004_terminal_state()


def test_historical_005_terminal_state_validates_exact_parent_sidecar_failure():
    validated = replay.validate_historical_005_terminal_state()

    assert validated["experiment_id"] == (
        "real_beaker_ao_rt_matrix_v3_20260712_005"
    )
    assert validated["terminal_state"]["code"] == (
        "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
    )
    statuses = [item["status"] for item in validated["cell_status_index"]["cells"]]
    assert statuses.count("FAILED") == 1
    assert statuses.count("NOT_LAUNCHED") == 15
    assert validated["failed_cell_evidence"]["failure_stage"] == (
        "parent_launcher_sidecar_finalization"
    )
    assert validated["failed_cell_evidence"]["error_message"] == (
        "matrix_sidecar_established_input_mismatch"
    )


def test_historical_005_terminal_state_rejects_stale_decision_self_hash(
    monkeypatch,
):
    original = replay._load_json_object

    def load_with_mutated_decision(path, *, label):
        actual = original(path, label=label)
        if label == "historical_005_matrix_decision":
            actual["operational_preference"] = list(
                reversed(actual["operational_preference"])
            )
        return actual

    monkeypatch.setattr(replay, "_load_json_object", load_with_mutated_decision)
    with pytest.raises(ValueError, match="historical_005_terminal_state_invalid"):
        replay.validate_historical_005_terminal_state()


def test_historical_005_terminal_state_rejects_failure_stage_or_lock_drift(
    monkeypatch,
):
    original_load = replay._load_json_object

    def load_with_mutated_failure(path, *, label):
        actual = original_load(path, label=label)
        if label == "historical_005_failure_evidence":
            actual["failure_stage"] = "runtime_child"
        return actual

    monkeypatch.setattr(replay, "_load_json_object", load_with_mutated_failure)
    with pytest.raises(ValueError, match="historical_005_terminal_state_invalid"):
        replay.validate_historical_005_terminal_state()

    monkeypatch.setattr(replay, "_load_json_object", original_load)
    original_hash = replay._sha256_file

    def hash_with_lock_drift(path):
        if Path(path).name == (
            ".real_beaker_ao_rt_matrix_v3_20260712_005.aggregate.lock"
        ):
            return "0" * 64
        return original_hash(path)

    monkeypatch.setattr(replay, "_sha256_file", hash_with_lock_drift)
    with pytest.raises(ValueError, match="historical_005_terminal_state_invalid"):
        replay.validate_historical_005_terminal_state()


def test_historical_006_terminal_state_validates_exact_material_hash_failure():
    validated = replay.validate_historical_006_terminal_state()

    assert validated["experiment_id"] == (
        "real_beaker_ao_rt_matrix_v3_20260712_006"
    )
    assert validated["terminal_state"]["code"] == (
        "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
    )
    statuses = [item["status"] for item in validated["cell_status_index"]["cells"]]
    assert statuses.count("FAILED") == 1
    assert statuses.count("NOT_LAUNCHED") == 15
    assert validated["failed_cell_evidence"]["failure_stage"] == (
        "parent_launcher_sidecar_finalization"
    )
    assert validated["failed_cell_evidence"]["error_message"] == (
        "matrix_cell_evidence_mismatch:hash"
    )


def test_historical_006_terminal_state_rejects_decision_failure_or_lock_drift(
    monkeypatch,
):
    original_load = replay._load_json_object

    def load_with_mutated_decision(path, *, label):
        actual = original_load(path, label=label)
        if label == "historical_006_matrix_decision":
            actual["operational_preference"] = list(
                reversed(actual["operational_preference"])
            )
        return actual

    monkeypatch.setattr(replay, "_load_json_object", load_with_mutated_decision)
    with pytest.raises(ValueError, match="historical_006_terminal_state_invalid"):
        replay.validate_historical_006_terminal_state()

    def load_with_mutated_failure(path, *, label):
        actual = original_load(path, label=label)
        if label == "historical_006_failure_evidence":
            actual["failure_stage"] = "runtime_child"
        return actual

    monkeypatch.setattr(replay, "_load_json_object", load_with_mutated_failure)
    with pytest.raises(ValueError, match="historical_006_terminal_state_invalid"):
        replay.validate_historical_006_terminal_state()

    monkeypatch.setattr(replay, "_load_json_object", original_load)
    original_hash = replay._sha256_file

    def hash_with_lock_drift(path):
        if Path(path).name == (
            ".real_beaker_ao_rt_matrix_v3_20260712_006.aggregate.lock"
        ):
            return "0" * 64
        return original_hash(path)

    monkeypatch.setattr(replay, "_sha256_file", hash_with_lock_drift)
    with pytest.raises(ValueError, match="historical_006_terminal_state_invalid"):
        replay.validate_historical_006_terminal_state()


def test_historical_007_terminal_state_validates_exact_parent_pxr_stop():
    validated = replay.validate_historical_007_terminal_state()

    assert validated["experiment_id"] == (
        "real_beaker_ao_rt_matrix_v3_20260712_007"
    )
    assert validated["terminal_state"]["code"] == (
        "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED"
    )
    statuses = [item["status"] for item in validated["cell_status_index"]["cells"]]
    assert statuses.count("SUCCESS") == 1
    assert statuses.count("NOT_LAUNCHED") == 15
    successful = next(
        item
        for item in validated["cell_status_index"]["cells"]
        if item["status"] == "SUCCESS"
    )
    assert successful["variant"] == "AO0_RT4_CONTROL"
    assert successful["replicate"] == "A"
    assert successful["execution_order_index"] == 0


def test_historical_007_terminal_state_rejects_decision_or_lock_drift(
    monkeypatch,
):
    original_load = replay._load_json_object

    def load_with_mutated_decision(path, *, label):
        actual = original_load(path, label=label)
        if label == "historical_007_matrix_decision":
            actual["operational_preference"] = list(
                reversed(actual["operational_preference"])
            )
        return actual

    monkeypatch.setattr(replay, "_load_json_object", load_with_mutated_decision)
    with pytest.raises(ValueError, match="historical_007_terminal_state_invalid"):
        replay.validate_historical_007_terminal_state()

    monkeypatch.setattr(replay, "_load_json_object", original_load)
    original_hash = replay._sha256_file

    def hash_with_lock_drift(path):
        if Path(path).name == (
            ".real_beaker_ao_rt_matrix_v3_20260712_007.aggregate.lock"
        ):
            return "0" * 64
        return original_hash(path)

    monkeypatch.setattr(replay, "_sha256_file", hash_with_lock_drift)
    with pytest.raises(ValueError, match="historical_007_terminal_state_invalid"):
        replay.validate_historical_007_terminal_state()


def test_render_diagnostic_registry_includes_complete_source_dependency_root():
    localized = (
        replay.REPO_ROOT
        / "outputs/usd_asset_packages/lab_001_localized_20260707"
    )
    hardening_plan = (
        replay.REPO_ROOT
        / "docs/runs/2026-07-12-real-beaker-black-liquid-causal-matrix-hardening-plan.md"
    )

    assert localized in replay.RENDER_DIAGNOSTIC_PROTECTED_ROOTS
    assert (
        replay.RENDER_DIAGNOSTIC_VERSION_MATCHED_MDL_SOURCE_ROOT
        in replay.RENDER_DIAGNOSTIC_PROTECTED_ROOTS
    )
    assert hardening_plan in replay.RENDER_DIAGNOSTIC_PROTECTED_FILES
    evidence_root = (
        replay.REPO_ROOT / "docs/labutopia_lab_poc/evidence_manifests"
    )
    for name in (
        "real_beaker_ao_rt_matrix_v3_implementation_identity_20260712.json",
        "real_beaker_ao_rt_matrix_v3_protected_tree_freeze_pre_20260712.json",
        ".real_beaker_ao_rt_matrix_v3_20260712_001.aggregate.lock",
        "real_beaker_ao_rt_matrix_v3_20260712_001_first_root_publication_failure.json",
        "real_beaker_ao_rt_matrix_v3_20260712_002_cpfs_rename_probe.json",
    ):
        assert evidence_root / name in replay.RENDER_DIAGNOSTIC_PROTECTED_FILES
    assert (
        evidence_root / "real_beaker_ao_rt_matrix_v3_20260712_002"
        in replay.RENDER_DIAGNOSTIC_PROTECTED_ROOTS
    )
    assert (
        evidence_root / "real_beaker_ao_rt_matrix_v3_20260712_005"
        in replay.RENDER_DIAGNOSTIC_PROTECTED_ROOTS
    )
    assert (
        evidence_root / "real_beaker_ao_rt_matrix_v3_20260712_006"
        in replay.RENDER_DIAGNOSTIC_PROTECTED_ROOTS
    )
    assert (
        evidence_root / "real_beaker_ao_rt_matrix_v3_20260712_007"
        in replay.RENDER_DIAGNOSTIC_PROTECTED_ROOTS
    )
    for name in (
        "real_beaker_ao_rt_matrix_v3_20260712_002_implementation_identity.json",
        "real_beaker_ao_rt_matrix_v3_20260712_002_protected_tree_freeze_pre.json",
        ".real_beaker_ao_rt_matrix_v3_20260712_002.aggregate.lock",
    ):
        assert evidence_root / name in replay.RENDER_DIAGNOSTIC_PROTECTED_FILES
    for name in (
        "real_beaker_ao_rt_matrix_v3_20260712_005_implementation_identity.json",
        "real_beaker_ao_rt_matrix_v3_20260712_005_protected_tree_freeze_pre.json",
        "real_beaker_ao_rt_matrix_v3_20260712_005_protected_tree_freeze_post.json",
        ".real_beaker_ao_rt_matrix_v3_20260712_005.aggregate.lock",
    ):
        assert evidence_root / name in replay.RENDER_DIAGNOSTIC_PROTECTED_FILES
    for name in (
        "real_beaker_ao_rt_matrix_v3_20260712_006_implementation_identity.json",
        "real_beaker_ao_rt_matrix_v3_20260712_006_protected_tree_freeze_pre.json",
        "real_beaker_ao_rt_matrix_v3_20260712_006_protected_tree_freeze_post.json",
        ".real_beaker_ao_rt_matrix_v3_20260712_006.aggregate.lock",
    ):
        assert evidence_root / name in replay.RENDER_DIAGNOSTIC_PROTECTED_FILES
    for name in (
        "real_beaker_ao_rt_matrix_v3_20260712_007_implementation_identity.json",
        "real_beaker_ao_rt_matrix_v3_20260712_007_protected_tree_freeze_pre.json",
        "real_beaker_ao_rt_matrix_v3_20260712_007_protected_tree_freeze_post.json",
        ".real_beaker_ao_rt_matrix_v3_20260712_007.aggregate.lock",
    ):
        assert evidence_root / name in replay.RENDER_DIAGNOSTIC_PROTECTED_FILES


def test_render_diagnostic_source_dependency_discovery_is_closed():
    discovery = replay.build_render_diagnostic_source_dependency_discovery()
    validated = replay.validate_render_diagnostic_source_dependency_discovery(
        discovery
    )
    allowed = tuple(Path(path) for path in validated["allowed_roots"])

    assert validated["status"] == "PASS"
    assert validated["unresolved"] == []
    assert validated["layers"] == sorted(validated["layers"])
    assert validated["assets"] == sorted(validated["assets"])
    assert all(
        any(path == root or root in path.parents for root in allowed)
        for path in map(Path, [*validated["layers"], *validated["assets"]])
    )

    escaped = json.loads(json.dumps(validated))
    escaped["assets"].append(str(replay.REPO_ROOT / "outside.png"))
    escaped["assets"].sort()
    escaped["dependency_discovery_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in escaped.items()
            if key != "dependency_discovery_sha256"
        }
    )
    with pytest.raises(ValueError, match="source_dependency_discovery"):
        replay.validate_render_diagnostic_source_dependency_discovery(escaped)

    unresolved = json.loads(json.dumps(validated))
    unresolved["unresolved"] = ["missing.usd"]
    unresolved["status"] = "FAIL"
    unresolved["dependency_discovery_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in unresolved.items()
            if key != "dependency_discovery_sha256"
        }
    )
    with pytest.raises(ValueError, match="source_dependency_discovery"):
        replay.validate_render_diagnostic_source_dependency_discovery(unresolved)


def test_render_diagnostic_implementation_identity_detects_hash_drift(monkeypatch):
    identity = replay.build_matrix_implementation_identity_v1()
    original = replay._snapshot_pinned_direct_files

    def drift(path, *, suffix, label):
        root, records = original(path, suffix=suffix, label=label)
        changed = [dict(record) for record in records]
        next(
            record
            for record in changed
            if record["name"] == Path(replay.__file__).name
        )["sha256"] = "0" * 64
        return root, changed

    monkeypatch.setattr(replay, "_snapshot_pinned_direct_files", drift)
    with pytest.raises(RuntimeError, match="matrix_implementation_identity_changed"):
        replay.verify_matrix_implementation_identity_unchanged(identity)


_SYNTHETIC_RUNTIME_ARCHIVE_CACHE = {}


def _install_synthetic_runtime_evidence(cell_root):
    implementation = replay.build_matrix_implementation_identity_v1()
    implementation_hash = implementation["implementation_identity_sha256"]
    if implementation_hash not in _SYNTHETIC_RUNTIME_ARCHIVE_CACHE:
        _SYNTHETIC_RUNTIME_ARCHIVE_CACHE[implementation_hash] = (
            replay.build_render_diagnostic_runtime_implementation_archive(
                implementation
            )
        )
    archive_evidence, archive_bytes = _SYNTHETIC_RUNTIME_ARCHIVE_CACHE[
        implementation_hash
    ]
    archive_path = cell_root / "runtime_implementation_archive.zip"
    bootstrap_path = cell_root / "runtime_bootstrap.py"
    archive_path.write_bytes(archive_bytes)
    bootstrap_path.write_text(
        replay.RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE,
        encoding="utf-8",
    )
    snapshot_root = cell_root / replay.RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
    support_relative = (
        "lab_001_level1_pour_support_aligned_v1_20260712/"
        "lab_001_level1_pour_support_aligned_v1.usda"
    )
    localized_relative = "lab_001_localized_20260707/base.usda"
    support_path = snapshot_root / support_relative
    localized_path = snapshot_root / localized_relative
    support_path.parent.mkdir(parents=True)
    localized_path.parent.mkdir(parents=True)
    support_path.write_text('#usda 1.0\ndef Xform "World" {}\n', encoding="ascii")
    localized_path.write_text('#usda 1.0\ndef Scope "Looks" {}\n', encoding="ascii")
    files = []
    for relative, path in sorted(
        ((support_relative, support_path), (localized_relative, localized_path))
    ):
        files.append(
            {
                "path": relative,
                "byte_count": path.stat().st_size,
                "sha256": _sha256_path(path),
            }
        )
        path.chmod(0o444)
    for directory in sorted(
        [snapshot_root, *[path for path in snapshot_root.rglob("*") if path.is_dir()]],
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        directory.chmod(0o555)
    source_payload = {
        "schema_version": 1,
        "closure_id": "support_aligned_source_dependency_closure_v1",
        "source_roots": [
            {
                "source_root": str(replay.RENDER_DIAGNOSTIC_SOURCE_PACKAGE_ROOT),
                "snapshot_subdirectory": (
                    "lab_001_level1_pour_support_aligned_v1_20260712"
                ),
            },
            {
                "source_root": str(
                    replay.RENDER_DIAGNOSTIC_LOCALIZED_DEPENDENCY_ROOT
                ),
                "snapshot_subdirectory": "lab_001_localized_20260707",
            },
        ],
        "entry_source_usd_path": str(replay.RENDER_DIAGNOSTIC_SOURCE_ENTRY_PATH),
        "snapshot_entry_source_usd_path": support_relative,
        "files": files,
    }
    source_closure = {
        **source_payload,
        "source_dependency_closure_sha256": (
            replay.canonical_json_sha256_v1(source_payload)
        ),
    }
    (cell_root / replay.RENDER_DIAGNOSTIC_SOURCE_CLOSURE_BASENAME).write_text(
        json.dumps(source_closure, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    inherited_fd_contract = {
        "schema_version": 1,
        "standard_fds": [0, 1, 2],
        "lock_fd": 5,
        "archive_fd": 6,
        "lock_access_mode": "READ_WRITE",
        "archive_access_mode": "READ_ONLY",
        "archive_seals": sorted(
            ["F_SEAL_SEAL", "F_SEAL_SHRINK", "F_SEAL_GROW", "F_SEAL_WRITE"]
        ),
    }
    return {
        "runtime_implementation_archive": archive_evidence,
        "runtime_implementation_archive_artifact": {
            "path": str(archive_path),
            "sha256": archive_evidence["archive_sha256"],
        },
        "runtime_bootstrap_artifact": {
            "path": str(bootstrap_path),
            "sha256": replay.RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SHA256,
        },
        "runtime_bootstrap_sha256": (
            replay.RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SHA256
        ),
        "inherited_fd_contract": inherited_fd_contract,
        "source_dependency_closure": source_closure,
    }


def _synthetic_render_diagnostic_final_manifest(
    cell_root,
    variant="AO0_RT4_CONTROL",
    *,
    replicate="A",
    order_index=None,
    base_color=(20, 170, 210),
):
    if order_index is None:
        order_index = replay.RENDER_DIAGNOSTIC_BALANCED_ORDER[replicate].index(
            variant
        )
    candidate_root = cell_root / "OMNI_REF_DISPLAY_FILL"
    base_image = cell_root / "base.png"
    base_image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (960, 540), base_color).save(base_image)
    role_dirs = {
        "context": candidate_root / "context_frames",
        "source_beaker_closeup": candidate_root / "source_beaker_closeup_frames",
        "native_table_context": candidate_root / "native_table_context_frames",
    }
    paths_by_role = {role: [] for role in replay.CAPTURE_CAMERA_ROLES}
    bindings = []
    for frame in range(0, 601, 30):
        image_paths = {}
        image_hashes = {}
        for role in replay.CAPTURE_CAMERA_ROLES:
            path = role_dirs[role] / f"frame_{frame:04d}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base_image, path)
            paths_by_role[role].append(str(path.resolve()))
            image_paths[role] = str(path.resolve())
            image_hashes[role] = _sha256_path(path)
        bindings.append(
            {
                "physical_trace_frame_index": frame,
                "source_positions_sha256": replay.canonical_json_sha256_v1(
                    {"frame": frame, "kind": "points"}
                ),
                "proxy_geometry_sha256": replay.canonical_json_sha256_v1(
                    {"frame": frame, "kind": "geometry"}
                ),
                "image_paths": image_paths,
                "image_sha256": image_hashes,
            }
        )
    base_video = cell_root / "base.mp4"
    base_video.write_bytes(b"synthetic-video")
    video_paths = {}
    video_validation = {}
    for role in replay.CAPTURE_CAMERA_ROLES:
        path = candidate_root / f"{role}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base_video, path)
        video_paths[role] = str(path.resolve())
        video_validation[role] = {
            "decodable": True,
            "frame_count": 21,
            "width": 960,
            "height": 540,
            "fps": 15.0,
        }
    base_image.unlink()
    base_video.unlink()
    look = replay.build_effective_replay_look_contract(
        "C_CONTROL", render_diagnostic_variant_id=variant
    )
    projection = replay.build_effective_replay_look_matrix_projection(look)
    closure_root = cell_root / replay.VERSION_MATCHED_MDL_CLOSURE_DIRNAME
    closure_file = closure_root / "Base" / "OmniGlass.mdl"
    module_file = closure_root / "mdl" / "OmniSurface" / "OmniSurfaceBase.mdl"
    closure_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.parent.mkdir(parents=True)
    closure_file.write_text("mdl 1.0;\n", encoding="ascii")
    module_file.write_text("mdl 1.0;\n", encoding="ascii")
    closure_hashes = {
        "Base/OmniGlass.mdl": _sha256_path(closure_file),
        "mdl/OmniSurface/OmniSurfaceBase.mdl": _sha256_path(module_file),
    }
    mdl_search = replay.build_render_diagnostic_mdl_startup_arguments(
        {
            "closure_root": str(closure_root.resolve()),
            "closure_base_dir": str((closure_root / "Base").resolve()),
            "closure_omnisurface_module_dir": str(
                (closure_root / "mdl" / "OmniSurface").resolve()
            ),
        }
    )
    mdl_search = {
        **mdl_search,
        "additional_user_paths_readback": list(mdl_search["search_paths"]),
        "material_custom_paths_readback": list(mdl_search["search_paths"]),
        "renderer_custom_paths_readback": list(mdl_search["search_paths"]),
        "readback_verified": True,
    }
    normal_contract = _rebase_beaker_normal_contract(
        _historical_beaker_normal_contract(),
        cell_root / replay.RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME,
    )
    candidate = {
        "candidate_id": "OMNI_REF_DISPLAY_FILL",
        "beaker_normal_remediation_contract": normal_contract,
        "beaker_normal_remediation_contract_sha256": normal_contract[
            "beaker_normal_remediation_contract_sha256"
        ],
        "material": {"material_hash": RENDER_DIAGNOSTIC_EXPECTED_MATERIAL_ID},
        "frames": [
            {"proxy_geometry_sha256": item["proxy_geometry_sha256"]}
            for item in bindings
        ],
        "effective_replay_look_contract": look,
        "effective_replay_look_contract_sha256": look[
            "effective_replay_look_contract_sha256"
        ],
        "effective_replay_look_matrix_projection_sha256": projection[
            "canonical_json_utf8_sha256"
        ],
        "render_settings": {
            **look["render_settings"],
            "validated": True,
            "postboot_update_barrier_executed": True,
            "requested_registry": replay._effective_replay_registry_records(look),
            "registry_readback": replay._effective_replay_registry_records(look),
            "startup_arguments": replay.build_effective_replay_kit_startup_arguments(
                look
            ),
            "native_refraction_contract": {
                "setting_path": replay.REPLAY_REFRACTION_SETTING_PATH,
                "max_refraction_bounces": replay.REPLAY_MAX_REFRACTION_BOUNCES,
            },
            "effective_replay_look_contract_sha256": look[
                "effective_replay_look_contract_sha256"
            ],
        },
        "material_closure": {
            "closure_root": str(closure_root.resolve()),
            "closure_base_dir": str((closure_root / "Base").resolve()),
            "closure_omnisurface_module_dir": str(
                (closure_root / "mdl" / "OmniSurface").resolve()
            ),
            "copied_file_sha256": closure_hashes,
            "copied_tree_sha256": replay.canonical_json_sha256_v1(
                closure_hashes
            ),
        },
        "mdl_search_path_contract": mdl_search,
        "capture_frame_bindings": {
            "physical_trace_sha256": RENDER_DIAGNOSTIC_EXPECTED_TRACE_SHA256,
            "bindings": bindings,
            "bindings_sha256": replay.canonical_json_sha256_v1(bindings),
        },
        "context_image_paths": paths_by_role["context"],
        "closeup_image_paths": paths_by_role["source_beaker_closeup"],
        "native_context_image_paths": paths_by_role["native_table_context"],
        "video_paths": video_paths,
        "video_validation": video_validation,
        "static_replicator_capture": {
            "rt_subframes": look["render_settings"]["rt_subframes"],
            "replicator_delta_time": 0.0,
            "timeline_advanced": False,
            "observed_default_time_usd_point_attributes_changed": False,
        },
    }
    runtime_evidence = _install_synthetic_runtime_evidence(cell_root)
    dependency_payload = {
        "schema_version": 1,
        "resolver_runtime": "isaacsim41_post_simulation_app_boot",
        "entry_path": str(
            cell_root
            / replay.RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
            / runtime_evidence["source_dependency_closure"][
                "snapshot_entry_source_usd_path"
            ]
        ),
        "allowed_roots": [
            str(cell_root / replay.RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME),
            str(closure_root.resolve()),
        ],
        "layers": [
            str(
                cell_root
                / replay.RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
                / runtime_evidence["source_dependency_closure"][
                    "snapshot_entry_source_usd_path"
                ]
            )
        ],
        "assets": [str(closure_file.resolve()), str(module_file.resolve())],
        "unresolved": [],
        "outside_allowed_roots": [],
        "status": "PASS",
    }
    runtime_dependency_resolution = {
        **dependency_payload,
        "runtime_dependency_resolution_sha256": (
            replay.canonical_json_sha256_v1(dependency_payload)
        ),
    }
    candidate["runtime_dependency_resolution"] = runtime_dependency_resolution
    return {
        "schema_version": 1,
        "classification": "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW",
        "source_usd_sha256": RENDER_DIAGNOSTIC_EXPECTED_SOURCE_SHA256,
        "accepted_authority_input": {
            "accepted_authority_bundle_sha256": (
                RENDER_DIAGNOSTIC_EXPECTED_AUTHORITY_SHA256
            )
        },
        "physical_trace_identity": {
            "physical_trace_sha256": RENDER_DIAGNOSTIC_EXPECTED_TRACE_SHA256
        },
        "camera_contracts_preflight": {"camera": "frozen"},
        "effective_replay_look_contract": look,
        "effective_replay_look_contract_sha256": look[
            "effective_replay_look_contract_sha256"
        ],
        "render_diagnostic_variant_id": variant,
        "effective_replay_look_matrix_projection_sha256": projection[
            "canonical_json_utf8_sha256"
        ],
        "candidate_manifests": {"OMNI_REF_DISPLAY_FILL": candidate},
        "mdl_search_path_contract": mdl_search,
        "runtime_dependency_resolution": runtime_dependency_resolution,
        "child_process_contract": {"exit_code": 0},
        "execution_provenance": {
            "python": {"executable": "/isaac/python", "version": "3.10"},
            "runtime": {"isaacsim_version": "4.1.0"},
            "render_parameters": {"headless": True},
        },
        "runtime_contract": {
            "kit_version": "106.0",
            "render_delegate": "RayTracedLighting",
            "timeline_observed_stopped_at_all_checkpoints": True,
            "observed_default_time_usd_point_attributes_changed": False,
            "usd_dependency_closure_bytes_verified": True,
            "renderer_dependency_consumption_verification": (
                "NOT_AVAILABLE_ISAACSIM41"
            ),
        },
        **runtime_evidence,
        **replay.render_diagnostic_lifecycle_contract(),
    }


def test_render_diagnostic_real_006_candidate_anchors_material_id_hash():
    candidate_path = (
        replay.REPO_ROOT
        / "docs/labutopia_lab_poc/evidence_manifests"
        / "real_beaker_ao_rt_matrix_v3_20260712_006"
        / "cells/A_0_AO0_RT4_CONTROL/OMNI_REF_DISPLAY_FILL/candidate_manifest.json"
    )
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    material_id = candidate["material"]["material_hash"]

    assert material_id == RENDER_DIAGNOSTIC_EXPECTED_MATERIAL_ID
    assert replay.canonical_json_sha256_v1(material_id) == (
        RENDER_DIAGNOSTIC_EXPECTED_MATERIAL_ID_SHA256
    )


def test_render_diagnostic_builds_and_writes_exact_cell_sidecars(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    cell_root = Path(identity["cell_root"])
    implementation = replay.build_matrix_implementation_identity_v1()
    intent = replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    final_manifest = _synthetic_render_diagnostic_final_manifest(cell_root)
    device_payload = {
        "schema_version": 1,
        "gpu_uuid": "GPU-test",
        "gpu_name": "Test GPU",
        "driver_version": "test-driver",
    }
    device = {
        **device_payload,
        "device_identity_sha256": replay.canonical_json_sha256_v1(device_payload),
    }

    unexpected = cell_root / "unreferenced-before-sidecars.bin"
    unexpected.write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="artifact_inventory_unreferenced"):
        replay.build_render_diagnostic_cell_sidecar_payloads(
            final_manifest=final_manifest,
            identity=identity,
            implementation_identity=implementation,
            launch_intent=intent,
            launcher_pid=123,
            child_pid=456,
            device_identity=device,
        )
    unexpected.unlink()

    sidecars = replay.build_render_diagnostic_cell_sidecar_payloads(
        final_manifest=final_manifest,
        identity=identity,
        implementation_identity=implementation,
        launch_intent=intent,
        launcher_pid=123,
        child_pid=456,
        device_identity=device,
    )
    assert len(sidecars["frame_bindings"]["frames"]) == 21
    assert len(sidecars["media_index"]["images"]) == 63
    assert len(sidecars["media_index"]["videos"]) == 3
    assert sidecars["mdl_closure"]["mdl_search_path_contract"][
        "readback_verified"
    ] is True
    assert sidecars["mdl_closure"]["mdl_search_path_contract"][
        "search_paths"
    ][0].endswith("/mdl")
    assert sidecars["cell_evidence"][
        "normal_remediation_matrix_projection_sha256"
    ] == RENDER_DIAGNOSTIC_EXPECTED_NORMAL_MATRIX_PROJECTION_SHA256
    assert sidecars["cell_evidence"]["liquid_material_sha256"] == (
        RENDER_DIAGNOSTIC_EXPECTED_MATERIAL_ID_SHA256
    )
    assert replay.validate_render_diagnostic_matrix_cell_evidence(
        sidecars["cell_evidence"]
    ) == sidecars["cell_evidence"]

    mismatched_material = json.loads(json.dumps(final_manifest, allow_nan=False))
    mismatched_material["candidate_manifests"]["OMNI_REF_DISPLAY_FILL"][
        "material"
    ]["material_hash"] = "omniglass_water_tint_a18_v2"
    with pytest.raises(ValueError, match="matrix_sidecar_material_id_mismatch"):
        replay.build_render_diagnostic_cell_sidecar_payloads(
            final_manifest=mismatched_material,
            identity=identity,
            implementation_identity=implementation,
            launch_intent=intent,
            launcher_pid=123,
            child_pid=456,
            device_identity=device,
        )

    missing_contract = json.loads(json.dumps(final_manifest, allow_nan=False))
    missing_contract["candidate_manifests"]["OMNI_REF_DISPLAY_FILL"].pop(
        "beaker_normal_remediation_contract"
    )
    with pytest.raises(ValueError, match="matrix_sidecar_normal_contract_invalid"):
        replay.build_render_diagnostic_cell_sidecar_payloads(
            final_manifest=missing_contract,
            identity=identity,
            implementation_identity=implementation,
            launch_intent=intent,
            launcher_pid=123,
            child_pid=456,
            device_identity=device,
        )

    tampered_contract = json.loads(json.dumps(final_manifest, allow_nan=False))
    tampered_contract["candidate_manifests"]["OMNI_REF_DISPLAY_FILL"][
        "beaker_normal_remediation_contract"
    ]["normal_remediation_id"] = "tampered"
    with pytest.raises(
        ValueError, match="beaker_normal_remediation_contract_sha256_mismatch"
    ):
        replay.build_render_diagnostic_cell_sidecar_payloads(
            final_manifest=tampered_contract,
            identity=identity,
            implementation_identity=implementation,
            launch_intent=intent,
            launcher_pid=123,
            child_pid=456,
            device_identity=device,
        )

    mismatched_sibling = json.loads(json.dumps(final_manifest, allow_nan=False))
    mismatched_sibling["candidate_manifests"]["OMNI_REF_DISPLAY_FILL"][
        "beaker_normal_remediation_contract_sha256"
    ] = "0" * 64
    with pytest.raises(ValueError, match="matrix_sidecar_normal_contract_hash_mismatch"):
        replay.build_render_diagnostic_cell_sidecar_payloads(
            final_manifest=mismatched_sibling,
            identity=identity,
            implementation_identity=implementation,
            launch_intent=intent,
            launcher_pid=123,
            child_pid=456,
            device_identity=device,
        )

    written = replay.write_render_diagnostic_cell_sidecars(
        cell_root=cell_root,
        sidecars=sidecars,
    )
    assert set(written) == {
        "matrix_frame_bindings",
        "matrix_media_index",
        "matrix_cell_evidence",
        "matrix_implementation_identity",
        "runtime_identity",
        "device_identity",
        "process_identity",
        "matrix_mdl_closure",
        "matrix_source_dependency_closure",
        "matrix_cell_artifact_inventory",
    }
    assert all(Path(record["path"]).is_file() for record in written.values())
    with pytest.raises(FileExistsError):
        replay.write_render_diagnostic_cell_sidecars(
            cell_root=cell_root,
            sidecars=sidecars,
        )


@pytest.mark.parametrize(
    "material_id",
    [
        pytest.param("__MISSING__", id="missing"),
        pytest.param(None, id="none"),
        pytest.param("", id="empty"),
    ],
)
def test_render_diagnostic_sidecar_rejects_invalid_material_id_before_evidence(
    tmp_path, monkeypatch, material_id
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    cell_root = Path(identity["cell_root"])
    implementation = replay.build_matrix_implementation_identity_v1()
    intent = replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    final_manifest = _synthetic_render_diagnostic_final_manifest(cell_root)
    material = final_manifest["candidate_manifests"]["OMNI_REF_DISPLAY_FILL"][
        "material"
    ]
    if material_id == "__MISSING__":
        material.pop("material_hash")
    else:
        material["material_hash"] = material_id
    device_payload = {
        "schema_version": 1,
        "gpu_uuid": "GPU-test",
        "gpu_name": "Test GPU",
        "driver_version": "test-driver",
    }
    device = {
        **device_payload,
        "device_identity_sha256": replay.canonical_json_sha256_v1(
            device_payload
        ),
    }

    with pytest.raises(ValueError, match="matrix_sidecar_material_id_invalid"):
        replay.build_render_diagnostic_cell_sidecar_payloads(
            final_manifest=final_manifest,
            identity=identity,
            implementation_identity=implementation,
            launch_intent=intent,
            launcher_pid=123,
            child_pid=456,
            device_identity=device,
        )
    assert not (cell_root / "matrix_cell_evidence.json").exists()


def test_render_diagnostic_warmup_capture_is_hashed_then_discarded(tmp_path):
    calls = []

    def capture_function(**kwargs):
        calls.append(kwargs["rt_subframes"])
        for path in kwargs["output_paths"].values():
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (16, 8), (10, 120, 180)).save(path)
        return {
            "replicator_orchestrator_steps_executed": 1,
            "rt_subframes": kwargs["rt_subframes"],
            "timeline_advanced": False,
            "observed_default_time_usd_point_attributes_changed": False,
        }

    result = replay.capture_and_discard_render_diagnostic_warmup(
        capture_function=capture_function,
        output_root=tmp_path / "discarded",
        frame_index=0,
        orchestrator=object(),
        timeline=object(),
        annotators={role: object() for role in replay.CAPTURE_CAMERA_ROLES},
        width=16,
        height=8,
        rt_subframes=12,
        observed_default_time_usd_point_attributes_hash=lambda: "a" * 64,
    )

    assert calls == [12]
    assert result["discarded"] is True
    assert result["capture_contract"]["rt_subframes"] == 12
    assert len(result["discarded_image_sha256"]) == 3
    assert not (tmp_path / "discarded").exists()


def test_render_diagnostic_cell_status_distinguishes_launch_and_mixed(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    implementation = replay.build_matrix_implementation_identity_v1()
    launched_args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    launched_identity = replay.validate_render_diagnostic_cell_scope(launched_args)
    replay.write_render_diagnostic_launch_intent(
        launched_identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    mixed_slot = replay.render_diagnostic_slots()[4]
    (aggregate / "cells" / mixed_slot["cell_name"]).mkdir(parents=True)

    status = replay.build_render_diagnostic_cell_status_index(aggregate)
    by_name = {
        f"{cell['replicate']}_{cell['execution_order_index']}_{cell['variant']}": cell
        for cell in status["cells"]
    }
    assert by_name["A_0_AO0_RT4_CONTROL"]["status"] == (
        "LAUNCHED_EVIDENCE_MISSING"
    )
    assert by_name[mixed_slot["cell_name"]]["status"] == (
        "MIXED_UNREGISTERED_CELL_ROOT"
    )
    assert sum(cell["status"] == "NOT_LAUNCHED" for cell in status["cells"]) == 14


def test_render_diagnostic_protected_snapshot_is_exact_and_rejects_symlinks(
    tmp_path,
):
    root = tmp_path / "root"
    root.mkdir()
    (root / "b.bin").write_bytes(b"b")
    (root / "a.bin").write_bytes(b"a")
    protected_file = tmp_path / "single.txt"
    protected_file.write_text("single", encoding="ascii")

    snapshot = replay.snapshot_render_diagnostic_protected_registry(
        protected_roots=[root],
        protected_files=[protected_file],
        registry_id="test_registry",
    )
    assert snapshot["schema_version"] == 1
    assert snapshot["registry_id"] == "test_registry"
    assert [record["path"] for record in snapshot["protected_roots"][0]["files"]] == [
        "a.bin",
        "b.bin",
    ]
    assert snapshot == replay.validate_render_diagnostic_protected_snapshot(
        snapshot,
        protected_roots=[root],
        protected_files=[protected_file],
        registry_id="test_registry",
    )

    (root / "link").symlink_to(root / "a.bin")
    with pytest.raises(ValueError, match="protected_registry_symlink_rejected"):
        replay.snapshot_render_diagnostic_protected_registry(
            protected_roots=[root],
            protected_files=[protected_file],
            registry_id="test_registry",
        )


def test_render_diagnostic_protected_snapshot_rejects_ancestor_symlink(
    tmp_path,
):
    real_parent = tmp_path / "real"
    protected_root = real_parent / "protected"
    protected_root.mkdir(parents=True)
    (protected_root / "asset.bin").write_bytes(b"asset")
    alias = tmp_path / "alias"
    alias.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="protected_registry.*symlink"):
        replay.snapshot_render_diagnostic_protected_registry(
            protected_roots=[alias / "protected"],
            protected_files=[],
            registry_id="test_registry",
        )


def test_render_diagnostic_blind_assets_have_eight_sheets_and_96_panels(tmp_path):
    image_lookup = _diagnostic_image_lookup(tmp_path / "images")
    output = tmp_path / "review"
    assets = replay.create_render_diagnostic_blind_review_assets(
        image_paths=image_lookup,
        output_root=output,
        label_variant_order=replay.RENDER_DIAGNOSTIC_VARIANTS,
        column_label_orders={
            "A": ("L2", "L0", "L3", "L1"),
            "B": ("L1", "L3", "L0", "L2"),
            "C": ("L3", "L2", "L1", "L0"),
            "D": ("L0", "L1", "L2", "L3"),
        },
    )
    assert len(assets["sheets"]) == 8
    assert len(assets["panel_map"]["panels"]) == 96
    assert all(Path(sheet["path"]).is_file() for sheet in assets["sheets"])
    assert (output / "panel_map.json").is_file()
    assert (output / "blinded_label_map.json").is_file()
    assert assets["panel_map_sha256"] == replay.canonical_json_sha256_v1(
        assets["panel_map"]
    )
    assert assets["blinded_label_map_sha256"] == replay.canonical_json_sha256_v1(
        assets["blinded_label_map"]
    )
    labels = {
        record["blinded_label"]: record["variant"]
        for record in assets["blinded_label_map"]["labels"]
    }
    assert labels == dict(zip(("L0", "L1", "L2", "L3"), replay.RENDER_DIAGNOSTIC_VARIANTS))
    first_group = assets["panel_map"]["panels"][:4]
    assert [record["blinded_label"] for record in first_group] == [
        "L2",
        "L0",
        "L3",
        "L1",
    ]


def test_render_diagnostic_review_record_binds_independent_raw_verdicts(tmp_path):
    assets = replay.create_render_diagnostic_blind_review_assets(
        image_paths=_diagnostic_image_lookup(tmp_path / "images"),
        output_root=tmp_path / "review",
        label_variant_order=replay.RENDER_DIAGNOSTIC_VARIANTS,
        column_label_orders={
            replicate: ("L0", "L1", "L2", "L3")
            for replicate in replay.RENDER_DIAGNOSTIC_REPLICATES
        },
    )
    raw = []
    for panel in sorted(
        assets["panel_map"]["panels"], key=lambda record: record["panel_id"]
    ):
        raw.append(
            {
                "panel_id": panel["panel_id"],
                "source_png_sha256": panel["source_png_sha256"],
                "material_verdict": "PASS",
                "hard_flags": {
                    "top_is_nearly_black": False,
                    "body_is_ink_like": False,
                    "cyan_top_not_readable": False,
                },
                "containment_and_grounding": "PASS",
                "external_liquid_visible": False,
                "penetration_visible": False,
                "starburst_visible": False,
                "broken_normal_visible": False,
                "framing_blocker_visible": False,
                "visible_evidence": ["cyan liquid is readable"],
            }
        )
    reviewer = {
        "mechanism": "ephemeral_clean_room_visual_review",
        "session_id": "review-session",
        "forked_implementation_context": False,
        "repository_context_supplied": False,
        "condition_mapping_supplied_before_verdict": False,
    }
    record = replay.build_render_diagnostic_review_record(
        review_root=tmp_path / "review",
        review_id="review-v1",
        reviewer=reviewer,
        raw_blinded_verdicts=raw,
    )
    assert record["review_record_sha256"] == replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in record.items()
            if key != "review_record_sha256"
        }
    )
    assert replay.validate_render_diagnostic_review_record(record) == record
    assert all(
        gate == "PASS" for gate in record["configuration_gates"].values()
    )

    tampered = json.loads(json.dumps(record))
    tampered["reviewer"]["repository_context_supplied"] = True
    with pytest.raises(ValueError, match="reviewer_independence_invalid"):
        replay.validate_render_diagnostic_review_record(tampered)

    malformed_sheet = json.loads(json.dumps(record))
    malformed_sheet["sheets"][0] = {}
    malformed_sheet["review_record_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in malformed_sheet.items()
            if key != "review_record_sha256"
        }
    )
    with pytest.raises(ValueError, match="review_sheet"):
        replay.validate_render_diagnostic_review_record(malformed_sheet)


def test_render_diagnostic_aggregate_main_never_enters_replay_runtime(
    tmp_path, monkeypatch, capsys
):
    pre = tmp_path / "pre.json"
    post = tmp_path / "post.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", post)
    decision = {
        "manifest_type": "real_beaker_render_diagnostic_matrix_decision",
        "terminal_state": {"code": "INDETERMINATE_VISUAL_REVIEW"},
    }
    calls = []
    monkeypatch.setattr(
        replay,
        "run_render_diagnostic_aggregate",
        lambda args: calls.append("aggregate") or decision,
    )
    monkeypatch.setattr(
        replay,
        "run_replay",
        lambda *_args: pytest.fail("runtime child entered"),
    )
    monkeypatch.setattr(
        replay,
        "run_replay_parent_launcher",
        lambda *_args: pytest.fail("runtime parent entered"),
    )

    exit_code = replay.main(
        [
            "--render-diagnostic-aggregate-only",
            "--render-diagnostic-experiment-root",
            str(replay.RENDER_DIAGNOSTIC_AGGREGATE_ROOT),
            "--render-diagnostic-pre-freeze",
            str(pre),
            "--render-diagnostic-post-freeze",
            str(post),
        ]
    )
    assert exit_code == 0
    assert calls == ["aggregate"]
    assert json.loads(capsys.readouterr().out) == decision


def test_render_diagnostic_failure_sidecar_is_exact_and_create_exclusive(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    implementation = replay.build_matrix_implementation_identity_v1()
    intent = replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    cell_root = Path(identity["cell_root"])
    cell_root.mkdir(parents=True)
    partial = cell_root / "replay_failure.json"
    partial.write_text('{"classification":"STOP_RUNTIME_ERROR"}', encoding="utf-8")

    evidence = replay.build_render_diagnostic_cell_failure_evidence(
        identity=identity,
        implementation_identity=implementation,
        launch_intent=intent,
        classification="STOP_RUNTIME_ERROR",
        child_exit_code=1,
        failure_stage="runtime_child",
        error_type="RuntimeError",
        error_message="failed",
        partial_manifest_path=partial,
        generated_at_utc="2026-07-12T00:00:01+00:00",
    )
    written = replay.write_render_diagnostic_cell_failure_evidence(
        cell_root=cell_root,
        evidence=evidence,
    )
    assert Path(written["path"]).is_file()
    assert evidence["matrix_cell_failure_evidence_sha256"] == (
        replay.canonical_json_sha256_v1(
            {
                key: value
                for key, value in evidence.items()
                if key not in {
                    "generated_at_utc",
                    "matrix_cell_failure_evidence_sha256",
                }
            }
        )
    )
    with pytest.raises(FileExistsError):
        replay.write_render_diagnostic_cell_failure_evidence(
            cell_root=cell_root,
            evidence=evidence,
        )


def test_render_diagnostic_corrupt_or_external_cell_evidence_becomes_failure_status(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    implementation = replay.build_matrix_implementation_identity_v1()
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    cell_root = Path(identity["cell_root"])
    cell_root.mkdir(parents=True)
    (cell_root / "matrix_cell_evidence.json").write_text("{}", encoding="utf-8")
    status = replay.build_render_diagnostic_cell_status_index(aggregate)
    assert status["cells"][0]["status"] == "LAUNCHED_EVIDENCE_MISSING"

    (cell_root / "matrix_cell_evidence.json").unlink()
    external = _diagnostic_cell_evidence(
        "AO0_RT4_CONTROL",
        "A",
        0,
        cell_root="/external/cell",
    )
    (cell_root / "matrix_cell_evidence.json").write_text(
        json.dumps(external), encoding="utf-8"
    )
    status = replay.build_render_diagnostic_cell_status_index(aggregate)
    assert status["cells"][0]["status"] == "LAUNCHED_EVIDENCE_MISSING"


def test_render_diagnostic_artifact_closure_recomputes_sidecars_and_manifest(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    cell_root = Path(identity["cell_root"])
    implementation = replay.build_matrix_implementation_identity_v1()
    intent = replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    final_manifest = _synthetic_render_diagnostic_final_manifest(cell_root)
    device_payload = {
        "schema_version": 1,
        "gpu_uuid": "GPU-test",
        "gpu_name": "Test GPU",
        "driver_version": "test-driver",
    }
    device = {
        **device_payload,
        "device_identity_sha256": replay.canonical_json_sha256_v1(device_payload),
    }
    sidecars = replay.build_render_diagnostic_cell_sidecar_payloads(
        final_manifest=final_manifest,
        identity=identity,
        implementation_identity=implementation,
        launch_intent=intent,
        launcher_pid=123,
        child_pid=456,
        device_identity=device,
    )
    written = replay.write_render_diagnostic_cell_sidecars(
        cell_root=cell_root,
        sidecars=sidecars,
    )
    final_manifest["matrix_sidecars"] = written
    final_manifest["matrix_cell_evidence_sha256"] = sidecars["cell_evidence"][
        "matrix_cell_evidence_sha256"
    ]
    (cell_root / "replay_manifest.json").write_text(
        json.dumps(final_manifest), encoding="utf-8"
    )

    def missing_parent_pxr(*_args, **_kwargs):
        raise ModuleNotFoundError("No module named 'pxr'")

    monkeypatch.setattr(
        replay,
        "compute_usd_dependency_paths",
        missing_parent_pxr,
    )
    validation = replay.validate_render_diagnostic_cell_artifact_closure(
        cell_root=cell_root,
        expected_slot=replay.render_diagnostic_slots()[0],
        expected_implementation_identity=implementation,
        expected_launch_intent=intent,
    )
    assert validation["validated"] is True
    assert validation["cell_evidence"] == sidecars["cell_evidence"]

    snapshot_file = (
        cell_root
        / replay.RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
        / final_manifest["source_dependency_closure"]["files"][0]["path"]
    )
    original_snapshot_bytes = snapshot_file.read_bytes()
    snapshot_file.chmod(0o600)
    snapshot_file.write_bytes(original_snapshot_bytes + b"\n# tampered\n")
    snapshot_file.chmod(0o444)
    with pytest.raises(ValueError, match="matrix_artifact_closure"):
        replay.validate_render_diagnostic_cell_artifact_closure(
            cell_root=cell_root,
            expected_slot=replay.render_diagnostic_slots()[0],
            expected_implementation_identity=implementation,
            expected_launch_intent=intent,
        )
    snapshot_file.chmod(0o600)
    snapshot_file.write_bytes(original_snapshot_bytes)
    snapshot_file.chmod(0o444)

    mdl_path = (
        cell_root
        / replay.VERSION_MATCHED_MDL_CLOSURE_DIRNAME
        / "Base"
        / "OmniGlass.mdl"
    )
    original_mdl = mdl_path.read_bytes()
    mdl_path.write_bytes(b"tampered-mdl")
    with pytest.raises(ValueError, match="matrix_artifact_closure"):
        replay.validate_render_diagnostic_cell_artifact_closure(
            cell_root=cell_root,
            expected_slot=replay.render_diagnostic_slots()[0],
            expected_implementation_identity=implementation,
            expected_launch_intent=intent,
        )
    mdl_path.write_bytes(original_mdl)

    media_path = cell_root / "matrix_media_index.json"
    media = json.loads(media_path.read_text())
    media["images"][0]["sha256"] = "0" * 64
    media_path.write_text(json.dumps(media), encoding="utf-8")
    with pytest.raises(ValueError, match="matrix_artifact_closure"):
        replay.validate_render_diagnostic_cell_artifact_closure(
            cell_root=cell_root,
            expected_slot=replay.render_diagnostic_slots()[0],
            expected_implementation_identity=implementation,
            expected_launch_intent=intent,
        )


def test_render_diagnostic_invalid_intent_and_failure_json_do_not_abort_status(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    slot = replay.render_diagnostic_slots()[0]
    intent_path = aggregate / "launch_intents" / f"{slot['cell_name']}.json"
    intent_path.parent.mkdir(parents=True)
    intent_path.write_text("{}", encoding="utf-8")

    status = replay.build_render_diagnostic_cell_status_index(aggregate)
    assert status["cells"][0]["status"] == "LAUNCHED_EVIDENCE_MISSING"

    intent_path.unlink()
    intent_path.parent.rmdir()
    aggregate.rmdir()
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    implementation = replay.build_matrix_implementation_identity_v1()
    replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    cell_root = Path(identity["cell_root"])
    cell_root.mkdir(parents=True)
    (cell_root / "matrix_cell_failure_evidence.json").write_text(
        "{}", encoding="utf-8"
    )

    status = replay.build_render_diagnostic_cell_status_index(aggregate)
    assert status["cells"][0]["status"] == "LAUNCHED_EVIDENCE_MISSING"


def test_render_diagnostic_launch_intent_loader_enforces_exact_schema_and_root(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    slot = replay.render_diagnostic_slots()[0]
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    implementation = replay.build_matrix_implementation_identity_v1()
    intent = replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    intent_path = aggregate / "launch_intents" / f"{slot['cell_name']}.json"
    assert replay._load_launch_intent(intent_path, slot) == intent

    malformed = dict(intent)
    malformed["unexpected"] = True
    malformed["launch_intent_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in malformed.items()
            if key not in {"generated_at_utc", "launch_intent_sha256"}
        }
    )
    intent_path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(ValueError, match="launch_intent_invalid"):
        replay._load_launch_intent(intent_path, slot)

    malformed = dict(intent)
    malformed["cell_root"] = str(aggregate / "cells" / "external")
    malformed["launch_intent_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in malformed.items()
            if key not in {"generated_at_utc", "launch_intent_sha256"}
        }
    )
    intent_path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(ValueError, match="launch_intent_invalid"):
        replay._load_launch_intent(intent_path, slot)


def test_render_diagnostic_failure_evidence_validator_binds_slot_and_partial_file(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    slot = replay.render_diagnostic_slots()[0]
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    implementation = replay.build_matrix_implementation_identity_v1()
    intent = replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    cell_root = Path(identity["cell_root"])
    cell_root.mkdir(parents=True)
    partial = cell_root / "replay_failure.json"
    partial.write_text('{"classification":"STOP_RUNTIME_ERROR"}', encoding="utf-8")
    evidence = replay.build_render_diagnostic_cell_failure_evidence(
        identity=identity,
        implementation_identity=implementation,
        launch_intent=intent,
        classification="STOP_RUNTIME_ERROR",
        child_exit_code=7,
        failure_stage="runtime_child",
        error_type="RuntimeError",
        error_message="failed",
        partial_manifest_path=partial,
        generated_at_utc="2026-07-12T00:00:01+00:00",
    )

    assert replay.validate_render_diagnostic_cell_failure_evidence(
        evidence,
        expected_cell_root=cell_root,
        expected_slot=slot,
        expected_launch_intent=intent,
        expected_implementation_identity=implementation,
    ) == evidence

    tampered = dict(evidence)
    tampered["partial_manifest_sha256"] = "0" * 64
    tampered["matrix_cell_failure_evidence_sha256"] = (
        replay.canonical_json_sha256_v1(
            {
                key: value
                for key, value in tampered.items()
                if key
                not in {
                    "generated_at_utc",
                    "matrix_cell_failure_evidence_sha256",
                }
            }
        )
    )
    with pytest.raises(ValueError, match="matrix_cell_failure"):
        replay.validate_render_diagnostic_cell_failure_evidence(
            tampered,
            expected_cell_root=cell_root,
            expected_slot=slot,
            expected_launch_intent=intent,
            expected_implementation_identity=implementation,
        )


def test_render_diagnostic_protected_snapshot_defaults_reject_substituted_registry(
    tmp_path, monkeypatch
):
    protected_root = tmp_path / "protected"
    protected_root.mkdir()
    (protected_root / "asset.bin").write_bytes(b"asset")
    protected_file = tmp_path / "source.usda"
    protected_file.write_text("#usda 1.0\n", encoding="ascii")
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_PROTECTED_ROOTS",
        (protected_root.resolve(),),
    )
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_PROTECTED_FILES",
        (protected_file.resolve(),),
    )
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID",
        "matrix_registry_test",
    )
    snapshot = replay.snapshot_default_render_diagnostic_protected_registry()
    assert replay.validate_render_diagnostic_protected_snapshot(snapshot) == snapshot

    substitute = tmp_path / "substitute"
    substitute.mkdir()
    (substitute / "asset.bin").write_bytes(b"asset")
    self_described = replay.snapshot_render_diagnostic_protected_registry(
        protected_roots=[substitute],
        protected_files=[protected_file],
        registry_id="matrix_registry_test",
    )
    with pytest.raises(ValueError, match="protected_registry_snapshot_schema_invalid"):
        replay.validate_render_diagnostic_protected_snapshot(self_described)


def test_render_diagnostic_review_binds_panels_to_sheets_and_matrix_images(tmp_path):
    image_lookup = _diagnostic_image_lookup(tmp_path / "images")
    assets = replay.create_render_diagnostic_blind_review_assets(
        image_paths=image_lookup,
        output_root=tmp_path / "review",
        label_variant_order=replay.RENDER_DIAGNOSTIC_VARIANTS,
        column_label_orders={
            replicate: ("L0", "L1", "L2", "L3")
            for replicate in replay.RENDER_DIAGNOSTIC_REPLICATES
        },
    )
    raw = []
    for panel in sorted(
        assets["panel_map"]["panels"], key=lambda record: record["panel_id"]
    ):
        raw.append(
            {
                "panel_id": panel["panel_id"],
                "source_png_sha256": panel["source_png_sha256"],
                "material_verdict": "PASS",
                "hard_flags": {
                    "top_is_nearly_black": False,
                    "body_is_ink_like": False,
                    "cyan_top_not_readable": False,
                },
                "containment_and_grounding": "PASS",
                "external_liquid_visible": False,
                "penetration_visible": False,
                "starburst_visible": False,
                "broken_normal_visible": False,
                "framing_blocker_visible": False,
                "visible_evidence": ["determinate"],
            }
        )
    reviewer = {
        "mechanism": "ephemeral_clean_room_visual_review",
        "session_id": "review-session",
        "forked_implementation_context": False,
        "repository_context_supplied": False,
        "condition_mapping_supplied_before_verdict": False,
    }
    record = replay.build_render_diagnostic_review_record(
        review_root=tmp_path / "review",
        review_id="review-v1",
        reviewer=reviewer,
        raw_blinded_verdicts=raw,
    )
    assert replay.validate_render_diagnostic_review_record(
        record,
        expected_image_lookup=image_lookup,
        expected_review_root=tmp_path / "review",
    ) == record

    wrong_lookup = dict(image_lookup)
    replacement = tmp_path / "replacement.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(replacement)
    wrong_lookup[("AO0_RT4_CONTROL", "A", "source_beaker_closeup", 0)] = replacement
    with pytest.raises(ValueError, match="review_source_image_binding_invalid"):
        replay.validate_render_diagnostic_review_record(
            record,
            expected_image_lookup=wrong_lookup,
            expected_review_root=tmp_path / "review",
        )

    panel_map_path = tmp_path / "review" / "panel_map.json"
    panel_map = json.loads(panel_map_path.read_text())
    panel_map["panels"][0]["sheet_sha256"] = "0" * 64
    panel_map_path.write_text(json.dumps(panel_map), encoding="utf-8")
    tampered_record = dict(record)
    tampered_record["panel_map_sha256"] = replay.canonical_json_sha256_v1(
        panel_map
    )
    tampered_record["review_record_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in tampered_record.items()
            if key != "review_record_sha256"
        }
    )
    with pytest.raises(ValueError, match="review_panel_sheet_binding_invalid"):
        replay.validate_render_diagnostic_review_record(
            tampered_record,
            expected_image_lookup=image_lookup,
            expected_review_root=tmp_path / "review",
        )


def test_render_diagnostic_parent_records_nonzero_child_after_preclose(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    cell_root = aggregate / "cells" / "A_0_AO0_RT4_CONTROL"
    implementation = replay.build_matrix_implementation_identity_v1()
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
    )
    monkeypatch.setattr(
        replay,
        "verify_render_diagnostic_pre_freeze_unchanged",
        lambda: {"verified": True, "sha256": "f" * 64},
    )
    monkeypatch.setattr(
        replay,
        "build_render_diagnostic_device_identity",
        lambda: {
            "schema_version": 1,
            "gpu_uuid": "GPU-test",
            "gpu_name": "Test GPU",
            "driver_version": "test",
            "device_identity_sha256": "d" * 64,
        },
    )

    def fake_run(*_args, **_kwargs):
        cell_root.mkdir(parents=True, exist_ok=True)
        (cell_root / "replay_preclose_manifest.json").write_text(
            '{"classification":"RENDER_COMPLETE_PENDING_APPLICATION_CLOSE"}',
            encoding="utf-8",
        )
        return types.SimpleNamespace(returncode=9)

    monkeypatch.setattr(replay.subprocess, "run", fake_run)
    monkeypatch.setattr(
        replay,
        "finalize_preclose_manifest_after_child_exit",
        lambda *_args, **_kwargs: pytest.fail("nonzero child was finalized"),
    )
    result = replay.run_replay_parent_launcher([], args)

    assert result["classification"] == "STOP_RUNTIME_ERROR"
    failure_path = cell_root / "matrix_cell_failure_evidence.json"
    assert failure_path.is_file()
    failure = json.loads(failure_path.read_text())
    assert failure["child_exit_code"] == 9
    assert failure["failure_stage"] == "parent_launcher_nonzero_after_preclose"


def test_render_diagnostic_aggregate_creates_post_envelope_and_persists_state_three(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH",
        tmp_path / ".matrix.aggregate.lock",
        raising=False,
    )
    protected_root = tmp_path / "protected"
    protected_root.mkdir()
    (protected_root / "asset.bin").write_bytes(b"asset")
    protected_file = tmp_path / "source.usda"
    protected_file.write_text("#usda 1.0\n", encoding="ascii")
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_PROTECTED_ROOTS",
        (protected_root.resolve(),),
    )
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_PROTECTED_FILES",
        (protected_file.resolve(),),
    )
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID",
        "matrix_registry_test",
    )
    pre = tmp_path / "pre.json"
    pre_snapshot = replay.snapshot_default_render_diagnostic_protected_registry()
    pre.write_text(json.dumps(pre_snapshot), encoding="utf-8")
    post = tmp_path / "missing-post.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", post)
    args = replay.build_arg_parser().parse_args(
        [
            "--render-diagnostic-aggregate-only",
            "--render-diagnostic-experiment-root",
            str(aggregate),
            "--render-diagnostic-pre-freeze",
            str(pre),
            "--render-diagnostic-post-freeze",
            str(post),
        ]
    )
    implementation = {
        "schema_version": 1,
        "identity_id": "matrix_implementation_identity_v1",
        "files": [],
        "implementation_identity_sha256": "a" * 64,
    }
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
    )
    identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    intent = replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256="a" * 64,
        pre_freeze_sha256=replay.canonical_json_sha256_v1(pre_snapshot),
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    evidence_root = aggregate / "evidence"
    evidence_root.mkdir(parents=True)
    (evidence_root / "cell_status_index.json").write_text(
        '{"partial":true}', encoding="utf-8"
    )

    decision = replay.run_render_diagnostic_aggregate(args)
    assert decision["terminal_state"]["code"] == (
        "STOP_CELL_RUNTIME_OR_ARTIFACT_FAILURE"
    )
    assert decision["anchor_sha256"] == intent["anchor_sha256"]
    assert decision["post_freeze_sha256"] is not None
    assert decision["post_seal_sha256"] is None
    assert decision["closure_snapshot_sha256"] is None
    assert post.is_file()
    envelope = json.loads(post.read_text())
    assert envelope["anchor_sha256"] == intent["anchor_sha256"]
    assert envelope["last_launch_intent_sha256"] == intent[
        "launch_intent_sha256"
    ]
    assert envelope["last_cell_artifact_sha256"] is None
    assert json.loads((evidence_root / "cell_status_index.json").read_text())[
        "schema_version"
    ] == 1

    semantic_tamper = json.loads(json.dumps(decision))
    semantic_tamper["terminal_state"]["evaluated_predicates"][1][
        "result"
    ] = "FALSE"
    semantic_tamper["terminal_state"]["evidence_sha256"] = (
        replay.canonical_json_sha256_v1(
            semantic_tamper["terminal_state"]["evaluated_predicates"]
        )
    )
    semantic_tamper["matrix_decision_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in semantic_tamper.items()
            if key not in {"generated_at_utc", "matrix_decision_sha256"}
        }
    )
    with pytest.raises(ValueError, match="matrix_decision"):
        replay.validate_render_diagnostic_matrix_decision(semantic_tamper)

    early_visual_tamper = json.loads(json.dumps(decision))
    early_visual_tamper["descriptive_contrasts"] = [{"fake": True}]
    early_visual_tamper["matrix_decision_sha256"] = (
        replay.canonical_json_sha256_v1(
            {
                key: value
                for key, value in early_visual_tamper.items()
                if key not in {"generated_at_utc", "matrix_decision_sha256"}
            }
        )
    )
    with pytest.raises(ValueError, match="matrix_decision_noninterpretive"):
        replay.validate_render_diagnostic_matrix_decision(early_visual_tamper)

    assert replay.run_render_diagnostic_aggregate(args) == decision


def test_render_diagnostic_cell_evidence_pins_established_input_hashes():
    evidence = _diagnostic_cell_evidence("AO0_RT4_CONTROL", "A", 0)
    assert replay.validate_render_diagnostic_matrix_cell_evidence(evidence) == evidence

    tampered = dict(evidence)
    tampered["source_usd_sha256"] = "0" * 64
    tampered["matrix_cell_evidence_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in tampered.items()
            if key != "matrix_cell_evidence_sha256"
        }
    )
    with pytest.raises(ValueError, match="matrix_cell_evidence_mismatch:established"):
        replay.validate_render_diagnostic_matrix_cell_evidence(tampered)


def test_render_diagnostic_render_settings_evidence_revalidates_variant_readback(
    tmp_path,
):
    manifest = _synthetic_render_diagnostic_final_manifest(
        tmp_path / "cell",
        variant="AO1_RT12",
    )
    candidate = manifest["candidate_manifests"]["OMNI_REF_DISPLAY_FILL"]
    look = manifest["effective_replay_look_contract"]
    canonical = replay.build_render_diagnostic_render_settings_evidence(
        render_settings=candidate["render_settings"],
        effective_look_contract=look,
        static_capture=candidate["static_replicator_capture"],
    )
    assert set(canonical) == {
        "schema_version",
        "render_diagnostic_variant_id",
        "requested_registry",
        "startup_arguments",
        "registry_readback",
        "renderer_consumption_verification",
        "rt_subframes",
    }

    candidate["render_settings"]["registry_readback"][0]["value"] = False
    with pytest.raises(ValueError, match="render_diagnostic_render_settings"):
        replay.build_render_diagnostic_render_settings_evidence(
            render_settings=candidate["render_settings"],
            effective_look_contract=look,
            static_capture=candidate["static_replicator_capture"],
        )


def test_render_diagnostic_mdl_closure_recomputes_actual_files_and_rejects_symlink(
    tmp_path,
):
    root = tmp_path / "closure"
    mdl = root / "Base" / "OmniGlass.mdl"
    mdl.parent.mkdir(parents=True)
    mdl.write_text("mdl 1.0;\n", encoding="ascii")
    closure = replay.build_render_diagnostic_mdl_closure_evidence(root)
    assert closure["schema_version"] == 1
    assert closure["files"][0]["path"] == "Base/OmniGlass.mdl"
    assert closure["files"][0]["byte_count"] == mdl.stat().st_size

    link = root / "Base" / "linked.mdl"
    link.symlink_to(mdl)
    with pytest.raises(ValueError, match="mdl_closure_symlink"):
        replay.build_render_diagnostic_mdl_closure_evidence(root)


def test_render_diagnostic_frozen_implementation_identity_is_fixed_and_reverified(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_AGGREGATE_ROOT",
        tmp_path / "matrix",
        raising=False,
    )
    freeze_path = tmp_path / "implementation_identity.json"
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH",
        freeze_path,
        raising=False,
    )
    identity = replay.write_frozen_matrix_implementation_identity()
    assert freeze_path.is_file()
    assert replay.load_and_verify_frozen_matrix_implementation_identity() == identity

    changed = json.loads(json.dumps(identity))
    changed["implementation_identity_sha256"] = "0" * 64
    monkeypatch.setattr(
        replay,
        "build_matrix_implementation_identity_v1",
        lambda: changed,
    )
    with pytest.raises(RuntimeError, match="matrix_implementation_identity_changed"):
        replay.load_and_verify_frozen_matrix_implementation_identity()


def test_render_diagnostic_rejects_symlink_aggregate_and_out_of_order_launch(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    external = tmp_path / "external"
    external.mkdir()
    aggregate.symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    with pytest.raises(ValueError, match="aggregate_root_symlink"):
        replay.validate_render_diagnostic_cell_scope(args)

    aggregate.unlink()
    args = _render_diagnostic_args("AO0_RT12", "A", 1)
    identity = replay.validate_render_diagnostic_cell_scope(args)
    with pytest.raises(ValueError, match="launch_sequence"):
        replay.write_render_diagnostic_launch_intent(
            identity,
            implementation_identity_sha256="e" * 64,
            pre_freeze_sha256="f" * 64,
            launcher_pid=123,
            generated_at_utc="2026-07-12T00:00:00+00:00",
        )
    assert not aggregate.exists()


def test_render_diagnostic_cell_output_root_must_be_absent(tmp_path, monkeypatch):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    cell_root = aggregate / "cells" / "A_0_AO0_RT4_CONTROL"
    cell_root.mkdir(parents=True)
    with pytest.raises(ValueError, match="diagnostic_out_root_must_be_absent"):
        replay._validate_output_scope(args)


def test_render_diagnostic_parent_records_sidecar_finalization_failure(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    cell_root = aggregate / "cells" / "A_0_AO0_RT4_CONTROL"
    implementation = replay.build_matrix_implementation_identity_v1()
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
        raising=False,
    )
    monkeypatch.setattr(
        replay,
        "verify_render_diagnostic_pre_freeze_unchanged",
        lambda: {"verified": True, "sha256": "f" * 64},
        raising=False,
    )
    monkeypatch.setattr(
        replay,
        "build_render_diagnostic_device_identity",
        lambda: {
            "schema_version": 1,
            "gpu_uuid": "GPU-test",
            "gpu_name": "Test GPU",
            "driver_version": "test",
            "device_identity_sha256": "d" * 64,
        },
    )

    def fake_run(*_args, **_kwargs):
        cell_root.mkdir(parents=True, exist_ok=True)
        (cell_root / "replay_preclose_manifest.json").write_text(
            '{"classification":"RENDER_COMPLETE_PENDING_APPLICATION_CLOSE"}',
            encoding="utf-8",
        )
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(replay.subprocess, "run", fake_run)
    monkeypatch.setattr(
        replay,
        "finalize_preclose_manifest_after_child_exit",
        lambda *_args, **_kwargs: {
            "runtime_contract": {"runtime_child_pid": 456}
        },
    )
    monkeypatch.setattr(
        replay,
        "build_render_diagnostic_cell_sidecar_payloads",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("sidecar invalid")),
    )

    result = replay.run_replay_parent_launcher([], args)
    assert result["classification"] == "STOP_RUNTIME_ERROR"
    failure = json.loads(
        (cell_root / "matrix_cell_failure_evidence.json").read_text()
    )
    assert failure["failure_stage"] == "parent_launcher_sidecar_finalization"


def test_render_diagnostic_review_recomposes_sheet_pixels_from_bound_sources(
    tmp_path,
):
    image_lookup = _diagnostic_image_lookup(tmp_path / "images")
    assets = replay.create_render_diagnostic_blind_review_assets(
        image_paths=image_lookup,
        output_root=tmp_path / "review",
        label_variant_order=replay.RENDER_DIAGNOSTIC_VARIANTS,
        column_label_orders={
            replicate: ("L0", "L1", "L2", "L3")
            for replicate in replay.RENDER_DIAGNOSTIC_REPLICATES
        },
    )
    raw = []
    for panel in sorted(
        assets["panel_map"]["panels"], key=lambda record: record["panel_id"]
    ):
        raw.append(
            {
                "panel_id": panel["panel_id"],
                "source_png_sha256": panel["source_png_sha256"],
                "material_verdict": "PASS",
                "hard_flags": {
                    "top_is_nearly_black": False,
                    "body_is_ink_like": False,
                    "cyan_top_not_readable": False,
                },
                "containment_and_grounding": "PASS",
                "external_liquid_visible": False,
                "penetration_visible": False,
                "starburst_visible": False,
                "broken_normal_visible": False,
                "framing_blocker_visible": False,
                "visible_evidence": ["determinate"],
            }
        )
    reviewer = {
        "mechanism": "ephemeral_clean_room_visual_review",
        "session_id": "review-session",
        "forked_implementation_context": False,
        "repository_context_supplied": False,
        "condition_mapping_supplied_before_verdict": False,
    }
    record = replay.build_render_diagnostic_review_record(
        review_root=tmp_path / "review",
        review_id="review-v1",
        reviewer=reviewer,
        raw_blinded_verdicts=raw,
    )
    sheet_path = tmp_path / "review" / "sheets" / "A_source_beaker_closeup.png"
    Image.new("RGB", (2560, 1120), (255, 255, 255)).save(sheet_path)
    sheet_hash = _sha256_path(sheet_path)
    panel_map_path = tmp_path / "review" / "panel_map.json"
    panel_map = json.loads(panel_map_path.read_text())
    for panel in panel_map["panels"]:
        if panel["replicate"] == "A" and panel["view"] == "source_beaker_closeup":
            panel["sheet_sha256"] = sheet_hash
    panel_map_path.write_text(json.dumps(panel_map), encoding="utf-8")
    tampered = json.loads(json.dumps(record))
    for sheet in tampered["sheets"]:
        if Path(sheet["path"]).resolve() == sheet_path.resolve():
            sheet["sha256"] = sheet_hash
    tampered["panel_map_sha256"] = replay.canonical_json_sha256_v1(panel_map)
    tampered["review_record_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in tampered.items()
            if key != "review_record_sha256"
        }
    )
    with pytest.raises(ValueError, match="review_sheet_pixel_binding_invalid"):
        replay.validate_render_diagnostic_review_record(
            tampered,
            expected_image_lookup=image_lookup,
            expected_review_root=tmp_path / "review",
        )


def test_render_diagnostic_label_map_non_object_is_validation_error():
    panel_map, label_map, verdicts = _blind_review_inputs()
    label_map["labels"][0] = None
    with pytest.raises(ValueError, match="render_diagnostic_label_map_invalid"):
        replay.derive_render_diagnostic_visual_gates(
            panel_map=panel_map,
            blinded_label_map=label_map,
            raw_blinded_verdicts=verdicts,
        )


def test_json_create_exclusive_never_leaves_partial_target(tmp_path, monkeypatch):
    target = tmp_path / "evidence.json"

    def fail_fsync(_descriptor):
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(replay.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="simulated fsync failure"):
        replay._write_json_create_exclusive(target, {"schema_version": 1})
    assert not target.exists()


def test_json_create_exclusive_rolls_back_when_post_guard_fails(tmp_path):
    target = tmp_path / "decision.json"

    def fail_after_publish():
        raise ValueError("simulated post-publication drift")

    with pytest.raises(ValueError, match="post-publication drift"):
        replay._write_json_create_exclusive(
            target,
            {"schema_version": 1},
            post_publish_validator=fail_after_publish,
        )
    assert not target.exists()


def test_atomic_directory_publish_never_replaces_existing_destination(tmp_path):
    source = tmp_path / "staging"
    target = tmp_path / "published"
    source.mkdir()
    target.mkdir()
    source_inode = source.stat().st_ino
    target_inode = target.stat().st_ino

    with pytest.raises(FileExistsError):
        replay._atomic_rename_noreplace(source, target)

    assert source.stat().st_ino == source_inode
    assert target.stat().st_ino == target_inode


def test_atomic_directory_publish_noreplace_success(tmp_path):
    source = tmp_path / "staging"
    target = tmp_path / "published"
    source.mkdir()
    source_identity = (source.stat().st_dev, source.stat().st_ino)

    replay._atomic_rename_noreplace(source, target)

    assert not source.exists()
    assert (target.stat().st_dev, target.stat().st_ino) == source_identity


def _renameat2_failure_libc(error):
    class RenameAt2:
        argtypes = None
        restype = None

        def __call__(self, *_args):
            ctypes.set_errno(error)
            return -1

    return types.SimpleNamespace(renameat2=RenameAt2())


def test_atomic_directory_publish_falls_back_on_cpfs_einval(
    tmp_path, monkeypatch
):
    source = tmp_path / "staging"
    target = tmp_path / "published"
    source.mkdir()
    source_identity = (source.stat().st_dev, source.stat().st_ino)
    monkeypatch.setattr(
        replay.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: _renameat2_failure_libc(errno.EINVAL),
    )

    replay._atomic_rename_noreplace(source, target)

    assert not source.exists()
    assert target.is_dir()
    assert (target.stat().st_dev, target.stat().st_ino) == source_identity


def test_atomic_directory_publish_cpfs_fallback_never_replaces_target(
    tmp_path, monkeypatch
):
    source = tmp_path / "staging"
    target = tmp_path / "published"
    source.mkdir()
    target.mkdir()
    target_identity = (target.stat().st_dev, target.stat().st_ino)
    monkeypatch.setattr(
        replay.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: _renameat2_failure_libc(errno.EINVAL),
    )

    with pytest.raises(FileExistsError):
        replay._atomic_rename_noreplace(source, target)

    assert source.is_dir()
    assert (target.stat().st_dev, target.stat().st_ino) == target_identity


def test_atomic_directory_publish_does_not_fallback_on_unexpected_errno(
    tmp_path, monkeypatch
):
    source = tmp_path / "staging"
    target = tmp_path / "published"
    source.mkdir()
    monkeypatch.setattr(
        replay.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: _renameat2_failure_libc(errno.EPERM),
    )

    with pytest.raises(OSError) as error:
        replay._atomic_rename_noreplace(source, target)

    assert error.value.errno == errno.EPERM
    assert source.is_dir()
    assert not target.exists()


def test_atomic_directory_publish_cpfs_reservation_blocks_concurrent_content(
    tmp_path, monkeypatch
):
    source = tmp_path / "staging"
    target = tmp_path / "published"
    source.mkdir()
    real_rename = os.rename
    monkeypatch.setattr(
        replay.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: _renameat2_failure_libc(errno.EINVAL),
    )

    def add_content_then_rename(*args, **kwargs):
        assert target.is_dir()
        (target / "concurrent.bin").write_bytes(b"occupied")
        return real_rename(*args, **kwargs)

    monkeypatch.setattr(replay.os, "rename", add_content_then_rename)

    with pytest.raises(OSError):
        replay._atomic_rename_noreplace(source, target)

    assert source.is_dir()
    assert (target / "concurrent.bin").read_bytes() == b"occupied"


def test_atomic_directory_publish_cpfs_cleans_unchanged_empty_reservation(
    tmp_path, monkeypatch
):
    source = tmp_path / "staging"
    target = tmp_path / "published"
    source.mkdir()
    monkeypatch.setattr(
        replay.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: _renameat2_failure_libc(errno.EINVAL),
    )
    def fail_with_empty_reservation(*_args, **_kwargs):
        assert target.is_dir()
        assert list(target.iterdir()) == []
        raise OSError(errno.EIO, os.strerror(errno.EIO))

    monkeypatch.setattr(replay.os, "rename", fail_with_empty_reservation)

    with pytest.raises(OSError) as error:
        replay._atomic_rename_noreplace(source, target)

    assert error.value.errno == errno.EIO
    assert source.is_dir()
    assert not target.exists()


def test_pinned_file_read_cannot_be_redirected_by_parent_swap(
    tmp_path, monkeypatch
):
    live_parent = tmp_path / "live"
    replacement_parent = tmp_path / "replacement"
    moved_parent = tmp_path / "moved"
    live_parent.mkdir()
    replacement_parent.mkdir()
    target = live_parent / "evidence.bin"
    target.write_bytes(b"AAAA")
    (replacement_parent / "evidence.bin").write_bytes(b"BBBB")
    original_read_bytes = Path.read_bytes

    def swapped_read(path):
        if path == target:
            live_parent.rename(moved_parent)
            replacement_parent.rename(live_parent)
            try:
                return original_read_bytes(target)
            finally:
                live_parent.rename(replacement_parent)
                moved_parent.rename(live_parent)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", swapped_read)
    assert replay._read_regular_file_snapshot(target, label="pinned") == b"AAAA"


def test_render_diagnostic_aggregate_scope_rejects_nonfixed_freeze_paths(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    fixed_pre = tmp_path / "fixed-pre.json"
    fixed_post = tmp_path / "fixed-post.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH",
        fixed_pre,
        raising=False,
    )
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_POST_FREEZE_PATH",
        fixed_post,
        raising=False,
    )
    args = replay.build_arg_parser().parse_args(
        [
            "--render-diagnostic-aggregate-only",
            "--render-diagnostic-experiment-root",
            str(aggregate),
            "--render-diagnostic-pre-freeze",
            str(tmp_path / "substitute-pre.json"),
            "--render-diagnostic-post-freeze",
            str(fixed_post),
        ]
    )
    with pytest.raises(ValueError, match="aggregate_scope_freeze_path_mismatch"):
        replay.validate_render_diagnostic_aggregate_scope(args)


def test_render_diagnostic_aggregate_scope_rejects_nonfixed_review_path(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    fixed_pre = tmp_path / "fixed-pre.json"
    fixed_post = tmp_path / "fixed-post.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", fixed_pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", fixed_post)
    args = replay.build_arg_parser().parse_args(
        [
            "--render-diagnostic-aggregate-only",
            "--render-diagnostic-experiment-root",
            str(aggregate),
            "--render-diagnostic-pre-freeze",
            str(fixed_pre),
            "--render-diagnostic-post-freeze",
            str(fixed_post),
            "--render-diagnostic-review-record",
            str(tmp_path / "substitute-review.json"),
        ]
    )

    with pytest.raises(ValueError, match="aggregate_scope_review_path_mismatch"):
        replay.validate_render_diagnostic_aggregate_scope(args)


def test_render_diagnostic_aggregate_missing_pre_is_state_one_without_output(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    pre = tmp_path / "missing-pre.json"
    post = tmp_path / "post.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", post)
    args = replay.build_arg_parser().parse_args(
        [
            "--render-diagnostic-aggregate-only",
            "--render-diagnostic-experiment-root",
            str(aggregate),
            "--render-diagnostic-pre-freeze",
            str(pre),
            "--render-diagnostic-post-freeze",
            str(post),
        ]
    )
    with pytest.raises(ValueError, match="aggregate_(root|pre_freeze)"):
        replay.run_render_diagnostic_aggregate(args)
    assert not aggregate.exists()


def test_render_diagnostic_stale_protected_failure_cannot_coexist_with_later_pass(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    protected_root = tmp_path / "protected"
    protected_root.mkdir()
    (protected_root / "asset.bin").write_bytes(b"asset")
    protected_file = tmp_path / "source.usda"
    protected_file.write_text("#usda 1.0\n", encoding="ascii")
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH",
        tmp_path / ".matrix.aggregate.lock",
        raising=False,
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_PROTECTED_ROOTS", (protected_root,)
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_PROTECTED_FILES", (protected_file,)
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID", "matrix_registry_test"
    )
    pre = tmp_path / "pre.json"
    post = tmp_path / "post.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", post)
    snapshot = replay.snapshot_default_render_diagnostic_protected_registry()
    pre.write_text(json.dumps(snapshot), encoding="utf-8")
    implementation = replay.build_matrix_implementation_identity_v1()
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
        raising=False,
    )
    identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256=replay.canonical_json_sha256_v1(snapshot),
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    evidence_root = aggregate / "evidence"
    evidence_root.mkdir()
    stale = replay.build_render_diagnostic_protected_input_failure(
        failed_path=post,
        failure_kind="MISSING",
        expected_sha256="a" * 64,
        observed_sha256=None,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    (evidence_root / "protected_input_failure.json").write_text(
        json.dumps(stale), encoding="utf-8"
    )
    monkeypatch.setattr(
        replay,
        "build_render_diagnostic_machine_verification",
        lambda _root: {
            "cell_status_index": {
                "schema_version": 1,
                "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
                "cells": [],
            },
            "all_launched_cells_successful": True,
            "successful_cell_evidence": [],
            "matrix_validation": {
                "status": "PASS",
                "matrix_validation_evidence_sha256": "b" * 64,
            },
            "repeat_stability": {
                "status": "PASS",
                "repeat_stability_evidence_sha256": "c" * 64,
            },
            "image_lookup": {},
        },
    )
    args = replay.build_arg_parser().parse_args(
        [
            "--render-diagnostic-aggregate-only",
            "--render-diagnostic-experiment-root",
            str(aggregate),
            "--render-diagnostic-pre-freeze",
            str(pre),
            "--render-diagnostic-post-freeze",
            str(post),
        ]
    )
    decision = replay.run_render_diagnostic_aggregate(args)
    assert decision["terminal_state"]["code"] == "STOP_PROTECTED_INPUT_MUTATION"


def test_render_diagnostic_protected_failure_hash_nullability_is_exact(tmp_path):
    with pytest.raises(ValueError, match="protected_input_failure_contract_invalid"):
        replay.build_render_diagnostic_protected_input_failure(
            failed_path=tmp_path / "changed.bin",
            failure_kind="CONTENT_CHANGED",
            expected_sha256=None,
            observed_sha256="a" * 64,
        )
    missing = replay.build_render_diagnostic_protected_input_failure(
        failed_path=tmp_path / "missing.bin",
        failure_kind="MISSING",
        expected_sha256="a" * 64,
        observed_sha256=None,
    )
    assert replay.validate_render_diagnostic_protected_input_failure(missing) == missing


def test_render_diagnostic_aggregate_does_not_publish_post_after_registry_drift(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    protected_root = tmp_path / "protected"
    protected_root.mkdir()
    protected_asset = protected_root / "asset.bin"
    protected_asset.write_bytes(b"before")
    protected_file = tmp_path / "source.usda"
    protected_file.write_text("#usda 1.0\n", encoding="ascii")
    pre = tmp_path / "pre.json"
    post = tmp_path / "post.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH",
        tmp_path / ".matrix.aggregate.lock",
        raising=False,
    )
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", post)
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_PROTECTED_ROOTS", (protected_root,)
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_PROTECTED_FILES", (protected_file,)
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID", "matrix_registry_test"
    )
    snapshot = replay.snapshot_default_render_diagnostic_protected_registry()
    pre.write_text(json.dumps(snapshot), encoding="utf-8")
    implementation = replay.build_matrix_implementation_identity_v1()
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
    )
    identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256=implementation[
            "implementation_identity_sha256"
        ],
        pre_freeze_sha256=replay.canonical_json_sha256_v1(snapshot),
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    protected_asset.write_bytes(b"after")
    args = replay.build_arg_parser().parse_args(
        [
            "--render-diagnostic-aggregate-only",
            "--render-diagnostic-experiment-root",
            str(aggregate),
            "--render-diagnostic-pre-freeze",
            str(pre),
            "--render-diagnostic-post-freeze",
            str(post),
        ]
    )

    decision = replay.run_render_diagnostic_aggregate(args)
    assert decision["terminal_state"]["code"] == "STOP_PROTECTED_INPUT_MUTATION"
    assert not post.exists()


def test_render_diagnostic_aggregate_rejects_explicit_default_replay_option(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    pre = tmp_path / "pre.json"
    post = tmp_path / "post.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", post)
    args = replay.build_arg_parser().parse_args(
        [
            "--render-diagnostic-aggregate-only",
            "--render-diagnostic-experiment-root",
            str(aggregate),
            "--render-diagnostic-pre-freeze",
            str(pre),
            "--render-diagnostic-post-freeze",
            str(post),
            "--width",
            "960",
        ]
    )
    with pytest.raises(ValueError, match="aggregate_scope_mixed_option"):
        replay.validate_render_diagnostic_aggregate_scope(args)


def test_render_diagnostic_first_intent_publish_failure_leaves_root_absent(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    identity = replay.validate_render_diagnostic_cell_scope(args)

    def fail_rename(_source, _target):
        raise OSError("simulated atomic publish failure")

    monkeypatch.setattr(replay, "_atomic_rename_noreplace", fail_rename)
    with pytest.raises(OSError, match="atomic publish failure"):
        replay.write_render_diagnostic_launch_intent(
            identity,
            implementation_identity_sha256="e" * 64,
            pre_freeze_sha256="f" * 64,
            launcher_pid=123,
            generated_at_utc="2026-07-12T00:00:00+00:00",
        )
    assert not aggregate.exists()


def test_render_diagnostic_rejects_broken_symlink_cell_output(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    cell_root = aggregate / "cells" / "A_0_AO0_RT4_CONTROL"
    cell_root.parent.mkdir(parents=True)
    cell_root.symlink_to(tmp_path / "missing-external", target_is_directory=True)
    with pytest.raises(ValueError, match="output.*symlink"):
        replay._validate_output_scope(args)


def test_render_diagnostic_status_marks_broken_symlink_cell_root_as_mixed(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    slot = replay.render_diagnostic_slots()[0]
    cell_root = aggregate / "cells" / slot["cell_name"]
    cell_root.parent.mkdir(parents=True)
    cell_root.symlink_to(tmp_path / "missing-cell", target_is_directory=True)

    status = replay.build_render_diagnostic_cell_status_index(aggregate)
    assert status["cells"][0]["status"] == "MIXED_UNREGISTERED_CELL_ROOT"


def test_render_diagnostic_post_freeze_has_no_direct_writer():
    assert not hasattr(replay, "write_render_diagnostic_post_freeze")


def test_render_diagnostic_parent_passes_locked_descriptor_to_runtime_child(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    lock = tmp_path / ".matrix.aggregate.lock"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH", lock, raising=False
    )
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    implementation = replay.build_matrix_implementation_identity_v1()
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
    )
    monkeypatch.setattr(
        replay,
        "verify_render_diagnostic_pre_freeze_unchanged",
        lambda: {"verified": True, "sha256": "f" * 64},
    )
    monkeypatch.setattr(
        replay,
        "build_render_diagnostic_device_identity",
        lambda: {
            "schema_version": 1,
            "gpu_uuid": "GPU-test",
            "gpu_name": "Test GPU",
            "driver_version": "test",
            "device_identity_sha256": "d" * 64,
        },
    )
    observed = {}

    def fail_to_start(*_args, **kwargs):
        observed.update(kwargs)
        observed["command"] = list(_args[0])
        descriptor, archive_descriptor = kwargs["pass_fds"]
        observed["lock_identity"] = (
            os.fstat(descriptor).st_dev,
            os.fstat(descriptor).st_ino,
        )
        archive_path = Path(args.out_root) / "runtime_implementation_archive.zip"
        bootstrap_path = Path(args.out_root) / "runtime_bootstrap.py"
        observed["archive_sha256"] = hashlib.sha256(
            archive_path.read_bytes()
        ).hexdigest()
        observed["bootstrap_sha256"] = hashlib.sha256(
            bootstrap_path.read_bytes()
        ).hexdigest()
        observed["archive_fd"] = replay.validate_render_diagnostic_sealed_archive_fd(
            archive_descriptor,
            expected_archive_sha256=observed["archive_sha256"],
        )
        raise OSError("simulated child start failure")

    monkeypatch.setattr(replay.subprocess, "run", fail_to_start)
    result = replay.run_replay_parent_launcher([], args)

    assert result["classification"] == "STOP_RUNTIME_ERROR"
    assert observed["close_fds"] is True
    assert len(observed["pass_fds"]) == 2
    assert observed["lock_identity"] == (os.stat(lock).st_dev, os.stat(lock).st_ino)
    assert observed["archive_fd"]["access_mode"] == "READ_ONLY"
    assert observed["command"][:4] == [
        str(Path(sys.executable).resolve()),
        "-I",
        "-S",
        "-c",
    ]
    assert observed["command"][4] == replay.RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE
    assert "PYTHONPATH" not in observed["env"]
    assert observed["env"]["PYTHONNOUSERSITE"] == "1"
    assert observed["env"]["LABUTOPIA_REPO_ROOT"] == str(replay.REPO_ROOT)
    assert observed["env"]["LABUTOPIA_SEALED_RUNTIME"] == "1"
    assert (
        observed["archive_sha256"]
        in observed["command"]
    )
    assert (
        observed["bootstrap_sha256"]
        in observed["command"]
    )


def test_render_diagnostic_parent_persists_pre_spawn_setup_failure(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH",
        tmp_path / ".matrix.aggregate.lock",
        raising=False,
    )
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    implementation = replay.build_matrix_implementation_identity_v1()
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
    )
    monkeypatch.setattr(
        replay,
        "verify_render_diagnostic_pre_freeze_unchanged",
        lambda: {"verified": True, "sha256": "f" * 64},
    )
    monkeypatch.setattr(
        replay,
        "build_render_diagnostic_device_identity",
        lambda: {
            "schema_version": 1,
            "gpu_uuid": "GPU-test",
            "gpu_name": "Test GPU",
            "driver_version": "test",
            "device_identity_sha256": "d" * 64,
        },
    )
    monkeypatch.setattr(
        replay,
        "_write_regular_bytes_create_exclusive",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("injected runtime archive persistence failure")
        ),
    )
    monkeypatch.setattr(
        replay.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("runtime child was started"),
    )

    result = replay.run_replay_parent_launcher([], args)

    cell_root = aggregate / "cells" / "A_0_AO0_RT4_CONTROL"
    assert result["classification"] == "STOP_RUNTIME_ERROR"
    failure = json.loads(
        (cell_root / "matrix_cell_failure_evidence.json").read_text()
    )
    assert failure["failure_stage"] == "parent_launcher_pre_spawn_setup"
    assert failure["error_type"] == "OSError"
    assert "runtime archive persistence failure" in failure["error_message"]


def test_render_diagnostic_direct_runtime_child_requires_parent_contract():
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    args.runtime_child = True

    with pytest.raises(ValueError, match="runtime_child_parent_contract"):
        replay.validate_runtime_child_invocation(args)


def test_render_diagnostic_parent_rejects_root_replacement_after_child(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    moved = tmp_path / "moved-matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH",
        tmp_path / ".matrix.aggregate.lock",
        raising=False,
    )
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    implementation = replay.build_matrix_implementation_identity_v1()
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
    )
    monkeypatch.setattr(
        replay,
        "verify_render_diagnostic_pre_freeze_unchanged",
        lambda: {"verified": True, "sha256": "f" * 64},
    )
    monkeypatch.setattr(
        replay,
        "build_render_diagnostic_device_identity",
        lambda: {
            "schema_version": 1,
            "gpu_uuid": "GPU-test",
            "gpu_name": "Test GPU",
            "driver_version": "test",
            "device_identity_sha256": "d" * 64,
        },
    )

    def replace_root(*_args, **_kwargs):
        aggregate.rename(moved)
        aggregate.mkdir()
        return types.SimpleNamespace(returncode=9)

    monkeypatch.setattr(replay.subprocess, "run", replace_root)
    with pytest.raises(RuntimeError, match="parent_anchor_changed_after_child"):
        replay.run_replay_parent_launcher([], args)
    assert not (aggregate / "cells").exists()


def test_render_diagnostic_successful_post_seal_requires_complete_chain():
    cells = [
        {
            "status": "SUCCESS",
            "launch_intent_sha256": f"{index + 1:064x}",
            "cell_evidence_sha256": f"{index + 101:064x}",
        }
        for index in range(16)
    ]
    status = {
        "schema_version": 1,
        "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "cells": cells,
    }
    registry = {
        "schema_version": 1,
        "registry_id": "matrix_registry_test",
        "protected_roots": [],
        "protected_files": [],
    }
    anchor = {
        "anchor_sha256": "a" * 64,
        "pre_freeze_sha256": "b" * 64,
        "implementation_identity_sha256": "c" * 64,
    }
    envelope = replay.build_render_diagnostic_post_freeze_envelope(
        registry_snapshot=registry,
        anchor=anchor,
        cell_status_index=status,
        generated_at_utc="2026-07-12T00:02:00+00:00",
    )
    chain = {
        "completed_successful_sequence_length": 16,
        "last_launch_intent_sha256": cells[-1]["launch_intent_sha256"],
        "last_cell_artifact_sha256": cells[-1]["cell_evidence_sha256"],
    }
    seal = replay.build_render_diagnostic_successful_post_seal(
        anchor=anchor,
        post_freeze_envelope=envelope,
        cell_status_index=status,
        validated_launch_chain=chain,
        generated_at_utc="2026-07-12T00:03:00+00:00",
    )
    assert seal["completed_sequence_length"] == 16
    assert seal["final_launch_intent_sha256"] == cells[-1][
        "launch_intent_sha256"
    ]
    assert seal["final_cell_evidence_sha256"] == cells[-1][
        "cell_evidence_sha256"
    ]

    incomplete = {**status, "cells": cells[:-1]}
    with pytest.raises(ValueError, match="post_seal_complete_chain_required"):
        replay.build_render_diagnostic_successful_post_seal(
            anchor=anchor,
            post_freeze_envelope=envelope,
            cell_status_index=incomplete,
            validated_launch_chain=chain,
        )


def test_render_diagnostic_first_intent_atomically_publishes_anchor_and_lock(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    lock = tmp_path / ".matrix.aggregate.lock"
    pre = tmp_path / "pre.json"
    post = tmp_path / "post.json"
    implementation_path = tmp_path / "implementation.json"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH", lock, raising=False
    )
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", post)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH",
        implementation_path,
    )

    identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    intent = replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256="e" * 64,
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )

    anchor_path = aggregate / "experiment_anchor.json"
    assert aggregate.is_dir() and anchor_path.is_file() and lock.is_file()
    anchor = json.loads(anchor_path.read_text())
    root_stat = os.stat(aggregate)
    lock_stat = os.stat(lock)
    assert anchor["aggregate_root_device"] == root_stat.st_dev
    assert anchor["aggregate_root_inode"] == root_stat.st_ino
    assert anchor["lock_device"] == lock_stat.st_dev
    assert anchor["lock_inode"] == lock_stat.st_ino
    assert anchor["implementation_identity_path"] == str(implementation_path)
    assert anchor["pre_freeze_path"] == str(pre)
    assert anchor["post_freeze_path"] == str(post)
    assert len(anchor["canonical_slots"]) == 16
    assert intent["sequence_index"] == 0
    assert intent["anchor_sha256"] == anchor["anchor_sha256"]
    assert intent["predecessor_launch_intent_sha256"] is None
    assert intent["predecessor_cell_evidence_sha256"] is None
    lock_lines = lock.read_text(encoding="utf-8").splitlines()
    assert len(lock_lines) == 1
    binding = json.loads(lock_lines[0])
    assert binding["record_type"] == "EXPERIMENT_BINDING"
    assert binding["experiment_binding_sha256"] == anchor[
        "experiment_binding_sha256"
    ]
    assert replay.validate_render_diagnostic_lock_journal(
        lock,
        anchor=anchor,
        authority_required=False,
    )["experiment_binding"] == binding


def test_render_diagnostic_second_intent_hash_links_predecessor_cell(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH",
        tmp_path / ".matrix.aggregate.lock",
        raising=False,
    )
    first_identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    first_intent = replay.write_render_diagnostic_launch_intent(
        first_identity,
        implementation_identity_sha256="e" * 64,
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    first_root = Path(first_identity["cell_root"])
    first_root.mkdir(parents=True)
    first_evidence = _diagnostic_cell_evidence(
        "AO0_RT4_CONTROL",
        "A",
        0,
        cell_root=str(first_root),
        implementation_identity_sha256="e" * 64,
    )
    (first_root / "matrix_cell_evidence.json").write_text(
        json.dumps(first_evidence), encoding="utf-8"
    )

    second_identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT12", "A", 1)
    )
    second_intent = replay.write_render_diagnostic_launch_intent(
        second_identity,
        implementation_identity_sha256="e" * 64,
        pre_freeze_sha256="f" * 64,
        launcher_pid=124,
        generated_at_utc="2026-07-12T00:01:00+00:00",
    )

    assert second_intent["sequence_index"] == 1
    assert second_intent["anchor_sha256"] == first_intent["anchor_sha256"]
    assert second_intent["predecessor_launch_intent_sha256"] == first_intent[
        "launch_intent_sha256"
    ]
    assert second_intent["predecessor_cell_evidence_sha256"] == first_evidence[
        "matrix_cell_evidence_sha256"
    ]


def test_decision_files_are_authoritative_only_inside_atomic_directory(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    lock = tmp_path / ".matrix.aggregate.lock"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH", lock, raising=False
    )
    identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256="e" * 64,
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    anchor = json.loads((aggregate / "experiment_anchor.json").read_text())
    decision = {
        "schema_version": 1,
        "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "terminal_state": {"code": "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED"},
        "matrix_decision_sha256": "d" * 64,
    }
    semantic_validation_lock_line_counts = []

    def semantic_validator(candidate, closure_root, staging_root):
        assert candidate == decision
        assert closure_root is None
        if len(lock.read_text(encoding="utf-8").splitlines()) == 1:
            assert staging_root is not None and staging_root.is_dir()
        else:
            assert staging_root is None
        semantic_validation_lock_line_counts.append(
            len(lock.read_text(encoding="utf-8").splitlines())
        )
        return candidate

    with replay.acquire_render_diagnostic_experiment_lock() as descriptor:
        published = replay.publish_render_diagnostic_decision_authority(
            aggregate_root=aggregate,
            decision=decision,
            anchor=anchor,
            lock_descriptor=descriptor,
            closure_root=None,
            publication_nonce="1" * 64,
            generated_at_utc="2026-07-12T01:00:00+00:00",
            semantic_validator=semantic_validator,
        )

    authority = aggregate / replay.RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
    assert authority.is_dir()
    assert set(path.name for path in authority.iterdir()) == {
        "matrix_decision.json",
        "decision_commit.json",
        "publication_intent.json",
    }
    assert not (aggregate / "matrix_decision.json").exists()
    assert not (aggregate / "final_closure").exists()
    assert published["decision"] == decision
    validated = replay.validate_render_diagnostic_decision_authority(
        aggregate_root=aggregate,
        anchor=anchor,
        lock=lock,
        semantic_validator=semantic_validator,
    )
    assert validated["decision"] == decision
    assert len(lock.read_text(encoding="utf-8").splitlines()) == 2
    assert semantic_validation_lock_line_counts == [1, 2]


def test_decision_authority_semantic_failure_precedes_witness_and_cleans_staging(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    lock = tmp_path / ".matrix.aggregate.lock"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH", lock, raising=False
    )
    identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256="e" * 64,
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    anchor = json.loads((aggregate / "experiment_anchor.json").read_text())
    decision = {
        "schema_version": 1,
        "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "terminal_state": {"code": "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED"},
        "matrix_decision_sha256": "d" * 64,
    }

    def reject_semantics(_candidate, closure_root, staging_root):
        assert closure_root is None
        assert staging_root is not None and staging_root.is_dir()
        assert len(lock.read_text(encoding="utf-8").splitlines()) == 1
        raise ValueError("injected_semantic_rejection")

    with replay.acquire_render_diagnostic_experiment_lock() as descriptor:
        with pytest.raises(ValueError, match="injected_semantic_rejection"):
            replay.publish_render_diagnostic_decision_authority(
                aggregate_root=aggregate,
                decision=decision,
                anchor=anchor,
                lock_descriptor=descriptor,
                closure_root=None,
                publication_nonce="2" * 64,
                generated_at_utc="2026-07-12T01:00:00+00:00",
                semantic_validator=reject_semantics,
            )

    assert not (
        aggregate / replay.RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
    ).exists()
    assert not (
        aggregate / replay.RENDER_DIAGNOSTIC_AUTHORITY_JOURNAL_BASENAME
    ).exists()
    assert not list(aggregate.glob(".matrix_decision_authority.*.staging"))
    assert len(lock.read_text(encoding="utf-8").splitlines()) == 1


def test_decision_authority_recovers_authenticated_pre_witness_staging(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    lock = tmp_path / ".matrix.aggregate.lock"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH", lock, raising=False
    )
    identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256="e" * 64,
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    anchor = json.loads((aggregate / "experiment_anchor.json").read_text())
    nonce = "3" * 64
    generated = "2026-07-12T01:00:00+00:00"
    intent = replay._build_render_diagnostic_authority_publication_intent(
        aggregate_root=aggregate,
        publication_nonce=nonce,
        generated_at_utc=generated,
    )
    staging = Path(intent["staging_path"])
    staging.mkdir()
    replay._write_json_create_exclusive(
        staging / "publication_intent.json", intent
    )
    replay._write_render_diagnostic_authority_journal(aggregate, intent)
    decision = {
        "schema_version": 1,
        "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "terminal_state": {"code": "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED"},
        "matrix_decision_sha256": "d" * 64,
    }

    with replay.acquire_render_diagnostic_experiment_lock() as descriptor:
        published = replay.publish_render_diagnostic_decision_authority(
            aggregate_root=aggregate,
            decision=decision,
            anchor=anchor,
            lock_descriptor=descriptor,
            closure_root=None,
            publication_nonce=nonce,
            generated_at_utc=generated,
        )

    assert published["decision"] == decision
    assert (
        aggregate / replay.RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
    ).is_dir()
    assert not staging.exists()
    assert len(lock.read_text(encoding="utf-8").splitlines()) == 2


def test_decision_authority_post_witness_recovery_finishes_same_rename(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    lock = tmp_path / ".matrix.aggregate.lock"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH", lock, raising=False
    )
    identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    replay.write_render_diagnostic_launch_intent(
        identity,
        implementation_identity_sha256="e" * 64,
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    anchor = json.loads((aggregate / "experiment_anchor.json").read_text())
    nonce = "4" * 64
    generated = "2026-07-12T01:00:00+00:00"
    decision = {
        "schema_version": 1,
        "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "terminal_state": {"code": "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED"},
        "matrix_decision_sha256": "d" * 64,
    }
    guard_calls = 0

    def crash_after_witness():
        nonlocal guard_calls
        guard_calls += 1
        if guard_calls == 2:
            raise RuntimeError("injected post-witness crash")

    with replay.acquire_render_diagnostic_experiment_lock() as descriptor:
        with pytest.raises(RuntimeError, match="post-witness crash"):
            replay.publish_render_diagnostic_decision_authority(
                aggregate_root=aggregate,
                decision=decision,
                anchor=anchor,
                lock_descriptor=descriptor,
                closure_root=None,
                publication_nonce=nonce,
                generated_at_utc=generated,
                publication_guard=crash_after_witness,
            )

    staging = aggregate / (
        ".matrix_decision_authority." + nonce + ".staging"
    )
    assert staging.is_dir()
    assert not (
        aggregate / replay.RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
    ).exists()
    assert len(lock.read_text(encoding="utf-8").splitlines()) == 2
    staged_inode = os.stat(staging).st_ino

    with replay.acquire_render_diagnostic_experiment_lock() as descriptor:
        published = replay.publish_render_diagnostic_decision_authority(
            aggregate_root=aggregate,
            decision=decision,
            anchor=anchor,
            lock_descriptor=descriptor,
            closure_root=None,
            publication_nonce=nonce,
            generated_at_utc=generated,
            publication_guard=lambda: None,
        )

    authority = aggregate / replay.RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
    assert published["decision"] == decision
    assert authority.is_dir() and not staging.exists()
    assert os.stat(authority).st_ino == staged_inode
    assert len(lock.read_text(encoding="utf-8").splitlines()) == 2


def test_render_diagnostic_next_intent_requires_prior_artifact_closure(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH",
        tmp_path / ".matrix.aggregate.lock",
        raising=False,
    )
    first_identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    )
    replay.write_render_diagnostic_launch_intent(
        first_identity,
        implementation_identity_sha256="e" * 64,
        pre_freeze_sha256="f" * 64,
        launcher_pid=123,
        generated_at_utc="2026-07-12T00:00:00+00:00",
    )
    first_root = Path(first_identity["cell_root"])
    first_root.mkdir(parents=True)
    first_evidence = _diagnostic_cell_evidence(
        "AO0_RT4_CONTROL",
        "A",
        0,
        cell_root=str(first_root),
        implementation_identity_sha256="e" * 64,
    )
    (first_root / "matrix_cell_evidence.json").write_text(
        json.dumps(first_evidence), encoding="utf-8"
    )

    def reject_incomplete_prior(**_kwargs):
        raise ValueError("prior artifact missing")

    monkeypatch.setattr(
        replay,
        "validate_render_diagnostic_cell_artifact_closure",
        reject_incomplete_prior,
    )
    second_identity = replay.validate_render_diagnostic_cell_scope(
        _render_diagnostic_args("AO0_RT12", "A", 1)
    )
    with pytest.raises(
        ValueError, match="render_diagnostic_launch_sequence_prior_not_successful"
    ):
        replay.write_render_diagnostic_launch_intent(
            second_identity,
            implementation_identity_sha256="e" * 64,
            expected_implementation_identity={
                "implementation_identity_sha256": "e" * 64
            },
            pre_freeze_sha256="f" * 64,
            launcher_pid=124,
            generated_at_utc="2026-07-12T00:01:00+00:00",
        )


def test_render_diagnostic_aggregate_rejects_rehashed_broken_predecessor_chain(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH",
        tmp_path / ".matrix.aggregate.lock",
        raising=False,
    )
    intent_by_index = []
    evidence_by_index = []
    for sequence_index, (variant, generated) in enumerate(
        (
            ("AO0_RT4_CONTROL", "2026-07-12T00:00:00+00:00"),
            ("AO0_RT12", "2026-07-12T00:01:00+00:00"),
        )
    ):
        identity = replay.validate_render_diagnostic_cell_scope(
            _render_diagnostic_args(variant, "A", sequence_index)
        )
        intent = replay.write_render_diagnostic_launch_intent(
            identity,
            implementation_identity_sha256="e" * 64,
            pre_freeze_sha256="f" * 64,
            launcher_pid=123 + sequence_index,
            generated_at_utc=generated,
        )
        cell_root = Path(identity["cell_root"])
        cell_root.mkdir(parents=True)
        evidence = _diagnostic_cell_evidence(
            variant,
            "A",
            sequence_index,
            cell_root=str(cell_root),
            implementation_identity_sha256="e" * 64,
        )
        (cell_root / "matrix_cell_evidence.json").write_text(
            json.dumps(evidence), encoding="utf-8"
        )
        intent_by_index.append(intent)
        evidence_by_index.append(evidence)

    second_path = aggregate / "launch_intents" / "A_1_AO0_RT12.json"
    tampered = json.loads(second_path.read_text())
    tampered["predecessor_launch_intent_sha256"] = "0" * 64
    tampered["launch_intent_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in tampered.items()
            if key not in {"generated_at_utc", "launch_intent_sha256"}
        }
    )
    second_path.write_text(json.dumps(tampered), encoding="utf-8")
    intent_by_index[1] = tampered

    records = []
    for sequence_index, slot in enumerate(replay.render_diagnostic_slots()):
        cell_root = aggregate / "cells" / slot["cell_name"]
        record = {
            "variant": slot["variant"],
            "replicate": slot["replicate"],
            "execution_order_index": slot["execution_order_index"],
            "launch_intent_path": None,
            "launch_intent_sha256": None,
            "cell_root": str(cell_root),
            "cell_evidence_path": None,
            "cell_evidence_sha256": None,
            "classification": None,
            "child_exit_code": None,
            "status": "NOT_LAUNCHED",
        }
        if sequence_index < 2:
            evidence = evidence_by_index[sequence_index]
            record.update(
                {
                    "launch_intent_path": str(
                        aggregate
                        / "launch_intents"
                        / f"{slot['cell_name']}.json"
                    ),
                    "launch_intent_sha256": intent_by_index[sequence_index][
                        "launch_intent_sha256"
                    ],
                    "cell_evidence_path": str(
                        cell_root / "matrix_cell_evidence.json"
                    ),
                    "cell_evidence_sha256": evidence[
                        "matrix_cell_evidence_sha256"
                    ],
                    "classification": (
                        "DIAGNOSTIC_RENDER_COMPLETE_PENDING_VISUAL_REVIEW"
                    ),
                    "child_exit_code": 0,
                    "status": "SUCCESS",
                }
            )
        records.append(record)
    status = replay.validate_render_diagnostic_cell_status_index(
        {
            "schema_version": 1,
            "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
            "cells": records,
        }
    )

    with pytest.raises(ValueError, match="launch_chain_predecessor"):
        replay.validate_render_diagnostic_launch_chain(
            aggregate_root=aggregate,
            anchor_sha256=intent_by_index[0]["anchor_sha256"],
            expected_implementation_identity_sha256="e" * 64,
            expected_pre_freeze_sha256="f" * 64,
            cell_status_index=status,
            require_artifact_closure=False,
        )


def test_render_diagnostic_post_freeze_envelope_binds_current_chain():
    snapshot = {
        "schema_version": 1,
        "registry_id": "matrix_registry_test",
        "protected_roots": [],
        "protected_files": [],
    }
    anchor = {
        "anchor_sha256": "a" * 64,
    }
    status = {
        "schema_version": 1,
        "experiment_id": replay.RENDER_DIAGNOSTIC_EXPERIMENT_ID,
        "cells": [
            {
                "status": "SUCCESS",
                "launch_intent_sha256": "b" * 64,
                "cell_evidence_sha256": "c" * 64,
            },
            {
                "status": "LAUNCHED_EVIDENCE_MISSING",
                "launch_intent_sha256": "d" * 64,
                "cell_evidence_sha256": None,
            },
        ],
    }
    envelope = replay.build_render_diagnostic_post_freeze_envelope(
        registry_snapshot=snapshot,
        anchor=anchor,
        cell_status_index=status,
        generated_at_utc="2026-07-12T00:02:00+00:00",
    )
    assert envelope["completed_successful_sequence_length"] == 1
    assert envelope["last_launch_intent_sha256"] == "d" * 64
    assert envelope["last_cell_artifact_sha256"] is None
    assert replay.validate_render_diagnostic_post_freeze_envelope(
        envelope,
        expected_registry_snapshot=snapshot,
        expected_anchor_sha256="a" * 64,
        expected_cell_status_index=status,
    ) == envelope

    tampered = json.loads(json.dumps(envelope))
    tampered["completed_successful_sequence_length"] = 2
    tampered["post_freeze_sha256"] = replay.canonical_json_sha256_v1(
        {
            key: value
            for key, value in tampered.items()
            if key not in {"generated_at_utc", "post_freeze_sha256"}
        }
    )
    with pytest.raises(ValueError, match="post_freeze_envelope"):
        replay.validate_render_diagnostic_post_freeze_envelope(
            tampered,
            expected_registry_snapshot=snapshot,
            expected_anchor_sha256="a" * 64,
            expected_cell_status_index=status,
        )


def test_render_diagnostic_final_closure_is_independent_and_deterministic(
    tmp_path,
):
    aggregate = tmp_path / "matrix"
    (aggregate / "evidence").mkdir(parents=True)
    source = aggregate / "evidence" / "cell_status_index.json"
    source.write_text('{"schema_version":1}\n', encoding="utf-8")
    external = tmp_path / "pre.json"
    external.write_text('{"schema_version":1}\n', encoding="utf-8")

    manifest = replay.create_render_diagnostic_final_closure_snapshot(
        aggregate_root=aggregate,
        external_files={"external/pre_freeze.json": external},
    )
    manifest_path = aggregate / "final_closure" / "closure_manifest.json"
    copied = (
        aggregate
        / "final_closure"
        / "aggregate"
        / "evidence"
        / "cell_status_index.json"
    )
    assert manifest_path.is_file() and copied.is_file()
    assert manifest["snapshot_inode"] == os.stat(
        aggregate / "final_closure"
    ).st_ino
    assert all(
        record["logical_path"] == record["snapshot_path"]
        for record in manifest["files"]
    )
    assert copied.stat().st_ino != source.stat().st_ino
    original_copy = copied.read_bytes()
    source.write_text('{"tampered":true}\n', encoding="utf-8")
    assert copied.read_bytes() == original_copy
    assert replay.validate_render_diagnostic_final_closure_snapshot(
        aggregate / "final_closure"
    ) == manifest

    copied.parent.chmod(0o755)
    with pytest.raises(ValueError, match="closure_directory_mode"):
        replay.validate_render_diagnostic_final_closure_snapshot(
            aggregate / "final_closure"
        )
    copied.parent.chmod(0o555)


def test_render_diagnostic_unexpected_top_level_file_is_rejected(tmp_path):
    aggregate = tmp_path / "matrix"
    aggregate.mkdir()
    unexpected = aggregate / "unregistered.bin"
    unexpected.write_bytes(b"unexpected")

    assert str(unexpected) in replay._render_diagnostic_unexpected_paths(
        aggregate
    )


def test_render_diagnostic_runtime_implementation_archive_is_deterministic():
    implementation = replay.build_matrix_implementation_identity_v1()
    first_evidence, first_payload = (
        replay.build_render_diagnostic_runtime_implementation_archive(
            implementation
        )
    )
    second_evidence, second_payload = (
        replay.build_render_diagnostic_runtime_implementation_archive(
            implementation
        )
    )

    assert first_evidence == second_evidence
    assert first_payload == second_payload
    assert first_evidence["archive_id"] == (
        "matrix_runtime_implementation_archive_v1"
    )
    assert first_evidence["archive_sha256"] == hashlib.sha256(
        first_payload
    ).hexdigest()
    assert replay.validate_render_diagnostic_runtime_implementation_archive(
        first_evidence,
        archive_bytes=first_payload,
        implementation_identity=implementation,
    ) == first_evidence

    with zipfile.ZipFile(io.BytesIO(first_payload)) as archive:
        names = archive.namelist()
        expected = sorted(
            [record["path"] for record in first_evidence["source_files"]]
            + [record["path"] for record in first_evidence["synthetic_files"]]
        )
        assert names == expected
        assert archive.compression == zipfile.ZIP_STORED
        assert all(
            hashlib.sha256(archive.read(record["path"])).hexdigest()
            == record["sha256"]
            for record in [
                *first_evidence["source_files"],
                *first_evidence["synthetic_files"],
            ]
        )

    tampered = bytearray(first_payload)
    tampered[-1] ^= 1
    with pytest.raises(ValueError, match="runtime_implementation_archive"):
        replay.validate_render_diagnostic_runtime_implementation_archive(
            first_evidence,
            archive_bytes=bytes(tampered),
            implementation_identity=implementation,
        )


def test_render_diagnostic_runtime_archive_fd_is_readonly_and_sealed():
    implementation = replay.build_matrix_implementation_identity_v1()
    evidence, payload = replay.build_render_diagnostic_runtime_implementation_archive(
        implementation
    )
    descriptor = replay.create_render_diagnostic_sealed_archive_fd(payload)
    try:
        contract = replay.validate_render_diagnostic_sealed_archive_fd(
            descriptor,
            expected_archive_sha256=evidence["archive_sha256"],
        )
        assert contract["access_mode"] == "READ_ONLY"
        assert contract["seals"] == [
            "F_SEAL_GROW",
            "F_SEAL_SEAL",
            "F_SEAL_SHRINK",
            "F_SEAL_WRITE",
        ]
        with pytest.raises(OSError):
            os.write(descriptor, b"x")
    finally:
        os.close(descriptor)


def test_render_diagnostic_runtime_child_kwargs_inherit_exact_descriptors():
    kwargs = replay.render_diagnostic_runtime_child_subprocess_kwargs(
        lock_descriptor=37,
        archive_descriptor=41,
    )
    assert kwargs["pass_fds"] == (37, 41)
    assert kwargs["close_fds"] is True

    with pytest.raises(ValueError, match="descriptor"):
        replay.render_diagnostic_runtime_child_subprocess_kwargs(
            lock_descriptor=37,
            archive_descriptor=37,
        )


def test_render_diagnostic_runtime_child_rejects_unlocked_inherited_fd(tmp_path):
    lock = tmp_path / "matrix.lock"
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with pytest.raises(ValueError, match="inherited_lock_not_held"):
            replay.verify_render_diagnostic_inherited_lock_held(
                lock_descriptor=descriptor,
                lock_path=lock,
            )
        replay.fcntl.flock(descriptor, replay.fcntl.LOCK_EX)
        assert replay.verify_render_diagnostic_inherited_lock_held(
            lock_descriptor=descriptor,
            lock_path=lock,
        )["inode"] == os.fstat(descriptor).st_ino
        reopened = os.open(lock, os.O_RDWR)
        try:
            with pytest.raises(
                ValueError, match="inherited_lock_not_held_by_descriptor"
            ):
                replay.verify_render_diagnostic_inherited_lock_held(
                    lock_descriptor=reopened,
                    lock_path=lock,
                )
        finally:
            os.close(reopened)
    finally:
        replay.fcntl.flock(descriptor, replay.fcntl.LOCK_UN)
        os.close(descriptor)


def test_render_diagnostic_orphan_child_keeps_experiment_lock(
    tmp_path, monkeypatch
):
    aggregate = tmp_path / "matrix"
    lock = tmp_path / ".matrix.aggregate.lock"
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH", lock, raising=False
    )
    script = "\n".join(
        (
            "import fcntl, os, subprocess, sys",
            "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)",
            "fcntl.flock(fd, fcntl.LOCK_EX)",
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'], pass_fds=(fd,))",
            "print(child.pid, flush=True)",
            "os._exit(0)",
        )
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", script, str(lock)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert parent.stdout is not None
    child_pid = int(parent.stdout.readline().strip())
    assert parent.wait(timeout=5) == 0

    with pytest.raises(RuntimeError, match="aggregate_already_running"):
        with replay.acquire_render_diagnostic_experiment_lock():
            pass

    deadline = time.monotonic() + 5.0
    while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    with replay.acquire_render_diagnostic_experiment_lock():
        pass


def test_render_diagnostic_review_rebuilds_from_final_closure_after_originals_removed(
    tmp_path,
):
    aggregate = tmp_path / "matrix"
    image_lookup = _diagnostic_image_lookup(aggregate / "cells" / "images")
    review_root = aggregate / "review"
    assets = replay.create_render_diagnostic_blind_review_assets(
        image_paths=image_lookup,
        output_root=review_root,
        label_variant_order=replay.RENDER_DIAGNOSTIC_VARIANTS,
        column_label_orders={
            replicate: ("L0", "L1", "L2", "L3")
            for replicate in replay.RENDER_DIAGNOSTIC_REPLICATES
        },
    )
    raw = []
    for panel in sorted(
        assets["panel_map"]["panels"], key=lambda record: record["panel_id"]
    ):
        raw.append(
            {
                "panel_id": panel["panel_id"],
                "source_png_sha256": panel["source_png_sha256"],
                "material_verdict": "PASS",
                "hard_flags": {
                    "top_is_nearly_black": False,
                    "body_is_ink_like": False,
                    "cyan_top_not_readable": False,
                },
                "containment_and_grounding": "PASS",
                "external_liquid_visible": False,
                "penetration_visible": False,
                "starburst_visible": False,
                "broken_normal_visible": False,
                "framing_blocker_visible": False,
                "visible_evidence": ["determinate"],
            }
        )
    record = replay.build_render_diagnostic_review_record(
        review_root=review_root,
        review_id="review-v1",
        reviewer={
            "mechanism": "ephemeral_clean_room_visual_review",
            "session_id": "review-session",
            "forked_implementation_context": False,
            "repository_context_supplied": False,
            "condition_mapping_supplied_before_verdict": False,
        },
        raw_blinded_verdicts=raw,
    )
    (review_root / "review_record.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    replay.create_render_diagnostic_final_closure_snapshot(
        aggregate_root=aggregate,
        external_files={},
    )
    closure = aggregate / "final_closure"
    shutil.rmtree(aggregate / "cells")
    shutil.rmtree(review_root)

    def resolve(path):
        return replay.resolve_render_diagnostic_closure_authoritative_path(
            path,
            aggregate_root=aggregate,
            closure_root=closure,
        )

    loaded = json.loads(
        resolve(aggregate / "review" / "review_record.json").read_text()
    )
    assert replay.validate_render_diagnostic_review_record(
        loaded,
        expected_image_lookup=image_lookup,
        expected_review_root=review_root,
        authoritative_path_resolver=resolve,
    ) == record


@pytest.mark.parametrize(
    ("case", "expected_terminal"),
    (
        ("state4_incomplete", "INDETERMINATE_MATRIX_INCOMPLETE_OR_MIXED"),
        ("state5_repeat", "INDETERMINATE_REPEAT"),
        ("state6_no_review", "INDETERMINATE_VISUAL_REVIEW"),
        ("state7_all_fail", "FAIL_NO_RENDER_SETTING_RECOVERY"),
        ("state8_pass", "PASS_VISUALLY_PASSED_RENDER_DIAGNOSTIC"),
    ),
)
def test_render_diagnostic_aggregate_states_four_through_eight(
    tmp_path, monkeypatch, case, expected_terminal
):
    aggregate = tmp_path / "matrix"
    lock = tmp_path / ".matrix.aggregate.lock"
    pre = tmp_path / "pre.json"
    post = tmp_path / "post.json"
    implementation_path = tmp_path / "implementation.json"
    protected_root = tmp_path / "protected"
    protected_root.mkdir()
    (protected_root / "asset.bin").write_bytes(b"asset")
    protected_file = tmp_path / "source.usda"
    protected_file.write_text("#usda 1.0\n", encoding="ascii")
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_AGGREGATE_ROOT", aggregate)
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_AGGREGATE_LOCK_PATH", lock, raising=False
    )
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_PRE_FREEZE_PATH", pre)
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_POST_FREEZE_PATH", post)
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_IMPLEMENTATION_FREEZE_PATH",
        implementation_path,
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_PROTECTED_ROOTS", (protected_root,)
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_PROTECTED_FILES", (protected_file,)
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_PROTECTED_REGISTRY_ID", "matrix_registry_test"
    )
    implementation = replay.build_matrix_implementation_identity_v1()
    implementation_path.write_text(json.dumps(implementation), encoding="utf-8")
    monkeypatch.setattr(
        replay,
        "load_and_verify_frozen_matrix_implementation_identity",
        lambda: implementation,
    )
    pre_snapshot = replay.snapshot_default_render_diagnostic_protected_registry()
    pre.write_text(json.dumps(pre_snapshot), encoding="utf-8")
    successful = []
    image_lookup = {}
    pre_hash = replay.canonical_json_sha256_v1(pre_snapshot)
    device = {
        "schema_version": 1,
        "gpu_uuid": "GPU-test",
        "gpu_name": "Test GPU",
        "driver_version": "test",
    }
    device["device_identity_sha256"] = replay.canonical_json_sha256_v1(device)
    slots = replay.render_diagnostic_slots()
    if case == "state4_incomplete":
        slots = slots[:-1]
    for sequence_index, slot in enumerate(slots):
        identity = replay.validate_render_diagnostic_cell_scope(
            _render_diagnostic_args(
                slot["variant"],
                slot["replicate"],
                slot["execution_order_index"],
            )
        )
        intent = replay.write_render_diagnostic_launch_intent(
            identity,
            implementation_identity_sha256=implementation[
                "implementation_identity_sha256"
            ],
            expected_implementation_identity=implementation,
            pre_freeze_sha256=pre_hash,
            launcher_pid=123 + sequence_index,
            generated_at_utc=(
                f"2026-07-12T00:{sequence_index:02d}:00+00:00"
            ),
        )
        cell_root = aggregate / "cells" / slot["cell_name"]
        final_manifest = _synthetic_render_diagnostic_final_manifest(
            cell_root,
            slot["variant"],
            replicate=slot["replicate"],
            order_index=slot["execution_order_index"],
            base_color=(
                (240, 10, 10)
                if case == "state5_repeat" and sequence_index == 15
                else (20, 170, 210)
            ),
        )
        sidecars = replay.build_render_diagnostic_cell_sidecar_payloads(
            final_manifest=final_manifest,
            identity=identity,
            implementation_identity=implementation,
            launch_intent=intent,
            launcher_pid=123 + sequence_index,
            child_pid=1000 + sequence_index,
            device_identity=device,
        )
        written = replay.write_render_diagnostic_cell_sidecars(
            cell_root=cell_root,
            sidecars=sidecars,
        )
        final_manifest["matrix_sidecars"] = written
        final_manifest["matrix_cell_evidence_sha256"] = sidecars[
            "cell_evidence"
        ]["matrix_cell_evidence_sha256"]
        (cell_root / "replay_manifest.json").write_text(
            json.dumps(final_manifest), encoding="utf-8"
        )
        successful.append(sidecars["cell_evidence"])
        for image_record in sidecars["media_index"]["images"]:
            if (
                image_record["camera"] in replay.RENDER_DIAGNOSTIC_REVIEW_VIEWS
                and image_record["frame"]
                in replay.RENDER_DIAGNOSTIC_REVIEW_FRAMES
            ):
                image_lookup[
                    (
                        slot["variant"],
                        slot["replicate"],
                        image_record["camera"],
                        image_record["frame"],
                    )
                ] = image_record["path"]
    status_index = replay.build_render_diagnostic_cell_status_index(
        aggregate,
        expected_implementation_identity=implementation,
        expected_pre_freeze_sha256=pre_hash,
    )
    machine = replay.build_render_diagnostic_machine_verification(
        aggregate,
        expected_implementation_identity=implementation,
        expected_pre_freeze_sha256=pre_hash,
    )
    assert machine["launch_chain"][
        "completed_successful_sequence_length"
    ] == len(slots)
    original_build_machine = replay.build_render_diagnostic_machine_verification

    def build_machine_before_closure(*_args, **_kwargs):
        if (aggregate / replay.RENDER_DIAGNOSTIC_FINAL_CLOSURE_DIRNAME).exists():
            pytest.fail("terminal final guard reread mutable original machine")
        return original_build_machine(*_args, **_kwargs)

    monkeypatch.setattr(
        replay,
        "build_render_diagnostic_machine_verification",
        build_machine_before_closure,
    )

    review_path = None
    if case in {"state7_all_fail", "state8_pass"}:
        review_root = aggregate / "review"
        assets = replay.create_render_diagnostic_blind_review_assets(
            image_paths=image_lookup,
            output_root=review_root,
            label_variant_order=replay.RENDER_DIAGNOSTIC_VARIANTS,
            column_label_orders={
                replicate: ("L0", "L1", "L2", "L3")
                for replicate in replay.RENDER_DIAGNOSTIC_REPLICATES
            },
        )
        raw = []
        for panel in sorted(
            assets["panel_map"]["panels"],
            key=lambda record: record["panel_id"],
        ):
            raw.append(
                {
                    "panel_id": panel["panel_id"],
                    "source_png_sha256": panel["source_png_sha256"],
                    "material_verdict": (
                        "FAIL" if case == "state7_all_fail" else "PASS"
                    ),
                    "hard_flags": {
                        "top_is_nearly_black": False,
                        "body_is_ink_like": False,
                        "cyan_top_not_readable": False,
                    },
                    "containment_and_grounding": "PASS",
                    "external_liquid_visible": False,
                    "penetration_visible": False,
                    "starburst_visible": False,
                    "broken_normal_visible": False,
                    "framing_blocker_visible": False,
                    "visible_evidence": ["determinate"],
                }
            )
        review = replay.build_render_diagnostic_review_record(
            review_root=review_root,
            review_id="review-v1",
            reviewer={
                "mechanism": "ephemeral_clean_room_visual_review",
                "session_id": "review-session",
                "forked_implementation_context": False,
                "repository_context_supplied": False,
                "condition_mapping_supplied_before_verdict": False,
            },
            raw_blinded_verdicts=raw,
        )
        review_path = review_root / "review_record.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
    aggregate_argv = [
        "--render-diagnostic-aggregate-only",
        "--render-diagnostic-experiment-root",
        str(aggregate),
        "--render-diagnostic-pre-freeze",
        str(pre),
        "--render-diagnostic-post-freeze",
        str(post),
    ]
    if review_path is not None:
        aggregate_argv.extend(
            ["--render-diagnostic-review-record", str(review_path)]
        )
    args = replay.build_arg_parser().parse_args(aggregate_argv)
    decision = replay.run_render_diagnostic_aggregate(args)
    assert decision["terminal_state"]["code"] == expected_terminal
    if case == "state4_incomplete":
        assert decision["post_seal_sha256"] is None
    else:
        assert decision["post_seal_sha256"] is not None
    if case not in {"state7_all_fail", "state8_pass"}:
        assert decision["closure_snapshot_sha256"] is None
        assert not (aggregate / "final_closure").exists()
        assert replay.validate_render_diagnostic_matrix_decision(decision) == decision
        return
    assert decision["closure_snapshot_sha256"] is not None
    authority = aggregate / replay.RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME
    closure = authority / "final_closure"
    assert (closure / "closure_manifest.json").is_file()
    assert not (aggregate / "final_closure").exists()
    assert not (aggregate / "matrix_decision.json").exists()

    for child in list(aggregate.iterdir()):
        if child.name not in {
            replay.RENDER_DIAGNOSTIC_DECISION_AUTHORITY_DIRNAME,
            replay.RENDER_DIAGNOSTIC_AUTHORITY_JOURNAL_BASENAME,
        }:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    pre.unlink()
    post.unlink()
    implementation_path.unlink()
    monkeypatch.setattr(
        replay,
        "build_matrix_implementation_identity_v1",
        lambda: pytest.fail("snapshot validation read live implementation"),
    )
    assert replay.validate_render_diagnostic_matrix_decision(
        decision,
        closure_root_override=closure,
    ) == decision
    detached_closure = tmp_path / "detached-final-closure"
    closure.rename(detached_closure)
    shutil.rmtree(aggregate)
    lock.unlink()
    assert replay.validate_render_diagnostic_matrix_decision(
        decision,
        closure_root_override=detached_closure,
    ) == decision


def _source_snapshot_fixture(tmp_path, monkeypatch):
    support_root = (
        tmp_path / "lab_001_level1_pour_support_aligned_v1_20260712"
    )
    localized_root = tmp_path / "lab_001_localized_20260707"
    support_root.mkdir()
    localized_root.mkdir()
    entry = support_root / "lab_001_level1_pour_support_aligned_v1.usda"
    entry.write_text(
        "#usda 1.0\n(\n    subLayers = [@../lab_001_localized_20260707/base.usda@]\n)\n",
        encoding="ascii",
    )
    (localized_root / "base.usda").write_text(
        '#usda 1.0\ndef Xform "World" {}\n', encoding="ascii"
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_SOURCE_PACKAGE_ROOT", support_root
    )
    monkeypatch.setattr(
        replay, "RENDER_DIAGNOSTIC_LOCALIZED_DEPENDENCY_ROOT", localized_root
    )
    monkeypatch.setattr(replay, "RENDER_DIAGNOSTIC_SOURCE_ENTRY_PATH", entry)
    protected = replay.snapshot_render_diagnostic_protected_registry(
        protected_roots=(support_root, localized_root),
        protected_files=(),
        registry_id="test-source-snapshot",
    )
    return support_root, localized_root, entry, protected


def test_source_dependency_snapshot_is_portable_and_deterministic(
    tmp_path, monkeypatch
):
    _support, _localized, _entry, protected = _source_snapshot_fixture(
        tmp_path, monkeypatch
    )

    first = replay.publish_render_diagnostic_source_dependency_snapshot(
        tmp_path / "cell-a",
        protected_snapshot=protected,
        publication_nonce="a" * 64,
    )
    second = replay.publish_render_diagnostic_source_dependency_snapshot(
        tmp_path / "cell-b",
        protected_snapshot=protected,
        publication_nonce="b" * 64,
    )

    assert first == second
    assert first["snapshot_entry_source_usd_path"] == (
        "lab_001_level1_pour_support_aligned_v1_20260712/"
        "lab_001_level1_pour_support_aligned_v1.usda"
    )
    copied_entry = (
        tmp_path
        / "cell-a/source_dependency_snapshot"
        / first["snapshot_entry_source_usd_path"]
    )
    layers, assets, unresolved = replay.compute_usd_dependency_paths(copied_entry)
    assert unresolved == []
    assert copied_entry in layers
    snapshot_root = tmp_path / "cell-a/source_dependency_snapshot"
    assert all(
        snapshot_root in path.parents or path == snapshot_root
        for path in [*layers, *assets]
    )
    assert not (
        tmp_path / "cell-a/source_dependency_snapshot_intent.json"
    ).exists()


def test_source_dependency_snapshot_rejects_source_drift(tmp_path, monkeypatch):
    _support, localized, _entry, protected = _source_snapshot_fixture(
        tmp_path, monkeypatch
    )
    (localized / "base.usda").write_text(
        '#usda 1.0\ndef Xform "Changed" {}\n', encoding="ascii"
    )

    with pytest.raises(ValueError, match="source_dependency.*changed"):
        replay.publish_render_diagnostic_source_dependency_snapshot(
            tmp_path / "cell",
            protected_snapshot=protected,
            publication_nonce="c" * 64,
        )


def test_source_snapshot_defers_pxr_until_postboot_and_allows_only_cell_mdl(
    tmp_path, monkeypatch
):
    _support, _localized, _entry, protected = _source_snapshot_fixture(
        tmp_path, monkeypatch
    )
    cell = tmp_path / "cell"

    def preboot_pxr_forbidden(_entry):
        pytest.fail("preboot source publication invoked pxr dependency discovery")

    monkeypatch.setattr(
        replay,
        "compute_usd_dependency_paths",
        preboot_pxr_forbidden,
    )
    closure = replay.publish_render_diagnostic_source_dependency_snapshot(
        cell,
        protected_snapshot=protected,
        publication_nonce="c" * 64,
        verify_usd_dependencies=False,
    )

    snapshot_root = cell / replay.RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
    entry = snapshot_root / closure["snapshot_entry_source_usd_path"]
    mdl_root = cell / replay.VERSION_MATCHED_MDL_CLOSURE_DIRNAME
    mdl_asset = mdl_root / "Base" / "OmniGlass.mdl"
    mdl_asset.parent.mkdir(parents=True)
    mdl_asset.write_text("mdl 1.0;\n", encoding="ascii")
    outside = tmp_path / "live-conda" / "OmniGlass.mdl"
    outside.parent.mkdir()
    outside.write_text("mdl 1.0;\n", encoding="ascii")

    monkeypatch.setattr(
        replay,
        "compute_usd_dependency_paths",
        lambda _entry: ([entry], [mdl_asset], []),
    )
    assert replay.validate_render_diagnostic_source_dependency_snapshot(
        cell,
        closure,
        additional_allowed_dependency_roots=(mdl_root,),
    ) == closure

    monkeypatch.setattr(
        replay,
        "compute_usd_dependency_paths",
        lambda _entry: ([entry], [outside], []),
    )
    with pytest.raises(ValueError, match="source_dependency_snapshot_usd_closure"):
        replay.validate_render_diagnostic_source_dependency_snapshot(
            cell,
            closure,
            additional_allowed_dependency_roots=(mdl_root,),
        )


def test_exported_static_dependency_resolution_rejects_host_fallback(
    tmp_path, monkeypatch
):
    cell = tmp_path / "cell"
    candidate = cell / "OMNI_REF_DISPLAY_FILL"
    snapshot = cell / replay.RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
    material = cell / replay.VERSION_MATCHED_MDL_CLOSURE_DIRNAME
    static = candidate / "OMNI_REF_DISPLAY_FILL_static.usda"
    presentation = candidate / "OMNI_REF_DISPLAY_FILL_presentation.usda"
    local_mdl = material / "Base/OmniGlass.mdl"
    for path in (static, presentation, local_mdl):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# local\n", encoding="ascii")
    snapshot.mkdir(parents=True)

    monkeypatch.setattr(
        replay,
        "compute_usd_dependency_paths",
        lambda _entry: ([static, presentation], [local_mdl], []),
    )
    passed = replay.build_render_diagnostic_exported_static_dependency_resolution(
        static,
        cell_root=cell,
        candidate_root=candidate,
        material_closure_root=material,
    )
    assert passed["status"] == "PASS"
    assert passed["unresolved"] == []
    assert passed["outside_allowed_roots"] == []

    host_mdl = tmp_path / "host/omni/mdl/core/Base/OmniGlass.mdl"
    host_mdl.parent.mkdir(parents=True)
    host_mdl.write_text("mdl 1.0;\n", encoding="ascii")
    monkeypatch.setattr(
        replay,
        "compute_usd_dependency_paths",
        lambda _entry: ([static, presentation], [host_mdl], []),
    )
    failed = replay.build_render_diagnostic_exported_static_dependency_resolution(
        static,
        cell_root=cell,
        candidate_root=candidate,
        material_closure_root=material,
    )
    assert failed["status"] == "FAIL"
    assert failed["outside_allowed_roots"] == [str(host_mdl)]


def test_source_dependency_snapshot_rejects_target_symlink(tmp_path, monkeypatch):
    _support, _localized, _entry, protected = _source_snapshot_fixture(
        tmp_path, monkeypatch
    )
    cell = tmp_path / "cell"
    cell.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (cell / "source_dependency_snapshot").symlink_to(
        external, target_is_directory=True
    )

    with pytest.raises(ValueError, match="source_dependency.*target"):
        replay.publish_render_diagnostic_source_dependency_snapshot(
            cell,
            protected_snapshot=protected,
            publication_nonce="d" * 64,
        )
    assert list(external.iterdir()) == []


def test_source_dependency_snapshot_validation_rejects_extra_file(
    tmp_path, monkeypatch
):
    _support, _localized, _entry, protected = _source_snapshot_fixture(
        tmp_path, monkeypatch
    )
    cell = tmp_path / "cell"
    closure = replay.publish_render_diagnostic_source_dependency_snapshot(
        cell,
        protected_snapshot=protected,
        publication_nonce="e" * 64,
    )
    snapshot_root = cell / "source_dependency_snapshot"
    snapshot_root.chmod(0o700)
    extra_parent = snapshot_root / "lab_001_localized_20260707"
    extra_parent.chmod(0o700)
    (extra_parent / "extra.txt").write_text("unexpected", encoding="ascii")

    with pytest.raises(ValueError, match="source_dependency.*membership"):
        replay.validate_render_diagnostic_source_dependency_snapshot(
            cell,
            closure,
        )


def test_source_dependency_snapshot_validation_rejects_writable_mode(
    tmp_path, monkeypatch
):
    _support, _localized, _entry, protected = _source_snapshot_fixture(
        tmp_path, monkeypatch
    )
    cell = tmp_path / "cell"
    closure = replay.publish_render_diagnostic_source_dependency_snapshot(
        cell,
        protected_snapshot=protected,
        publication_nonce="7" * 64,
    )
    entry = (
        cell
        / replay.RENDER_DIAGNOSTIC_SOURCE_SNAPSHOT_DIRNAME
        / closure["snapshot_entry_source_usd_path"]
    )
    entry.chmod(0o644)

    with pytest.raises(ValueError, match="source_dependency_snapshot.*mode"):
        replay.validate_render_diagnostic_source_dependency_snapshot(
            cell,
            closure,
        )


def test_source_snapshot_publication_recovers_authenticated_partial_staging(
    tmp_path, monkeypatch
):
    _support, _localized, _entry, protected = _source_snapshot_fixture(
        tmp_path, monkeypatch
    )
    cell = tmp_path / "cell"
    original_copy = replay._copy_regular_file_create_exclusive
    calls = 0

    def fail_after_first(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected copy failure")
        return original_copy(*args, **kwargs)

    monkeypatch.setattr(
        replay,
        "_copy_regular_file_create_exclusive",
        fail_after_first,
    )
    with pytest.raises(OSError, match="injected copy failure"):
        replay.publish_render_diagnostic_source_dependency_snapshot(
            cell,
            protected_snapshot=protected,
            publication_nonce="9" * 64,
        )
    assert (cell / "source_dependency_snapshot_intent.json").is_file()
    assert (cell / (".source_dependency_snapshot." + "9" * 64 + ".staging")).is_dir()

    monkeypatch.setattr(
        replay,
        "_copy_regular_file_create_exclusive",
        original_copy,
    )
    closure = replay.publish_render_diagnostic_source_dependency_snapshot(
        cell,
        protected_snapshot=protected,
        publication_nonce="9" * 64,
    )
    assert replay.publish_render_diagnostic_source_dependency_snapshot(
        cell,
        protected_snapshot=protected,
        publication_nonce="9" * 64,
    ) == closure
    assert not (cell / "source_dependency_snapshot_intent.json").exists()


def test_diagnostic_authority_load_uses_source_snapshot_override(
    tmp_path, monkeypatch
):
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    snapshot_entry = tmp_path / "source_dependency_snapshot/entry.usda"
    args._runtime_source_snapshot_entry = str(snapshot_entry)
    observed = {}

    def fake_loader(path, *, source_usd_path_override=None):
        observed["path"] = path
        observed["source_usd_path_override"] = source_usd_path_override
        return "accepted", "authority"

    monkeypatch.setattr(
        replay,
        "load_and_validate_support_aligned_authority_bundle",
        fake_loader,
    )

    result = replay.load_replay_inputs_from_args(args, recompute_closure=False)

    assert result == ("accepted", "authority")
    assert observed["source_usd_path_override"] == snapshot_entry


def test_run_replay_publishes_source_snapshot_before_loading_inputs(
    tmp_path, monkeypatch
):
    args = _render_diagnostic_args("AO0_RT4_CONTROL", "A", 0)
    args.runtime_child = True
    out_root = Path(args.out_root)
    snapshot_entry = out_root / (
        "source_dependency_snapshot/"
        "lab_001_level1_pour_support_aligned_v1_20260712/"
        "lab_001_level1_pour_support_aligned_v1.usda"
    )
    closure = {
        "snapshot_entry_source_usd_path": str(
            snapshot_entry.relative_to(out_root / "source_dependency_snapshot")
        ),
        "source_dependency_closure_sha256": "c" * 64,
    }
    order = []

    monkeypatch.setattr(replay, "validate_runtime_child_invocation", lambda _args: {})
    monkeypatch.setattr(
        replay,
        "load_and_verify_render_diagnostic_pre_freeze_snapshot",
        lambda: {"protected_roots": []},
        raising=False,
    )

    def publish(cell_root, *, protected_snapshot, verify_usd_dependencies):
        order.append("publish")
        assert Path(cell_root) == out_root
        assert verify_usd_dependencies is False
        return closure

    monkeypatch.setattr(
        replay,
        "publish_render_diagnostic_source_dependency_snapshot",
        publish,
    )
    monkeypatch.setattr(replay, "build_execution_provenance", lambda _args: {})
    accepted = types.SimpleNamespace(
        accepted_authority_bundle_sha256=(
            replay.RENDER_DIAGNOSTIC_EXPECTED_AUTHORITY_SHA256
        ),
        source_usd_sha256=replay.RENDER_DIAGNOSTIC_EXPECTED_SOURCE_SHA256,
        physical_trace_identity={
            "physical_trace_sha256": replay.RENDER_DIAGNOSTIC_EXPECTED_TRACE_SHA256
        },
        frame=object(),
        summary={"region_config": {}},
    )

    def load(_args, *, recompute_closure):
        order.append("load")
        assert recompute_closure is False
        assert Path(_args._runtime_source_snapshot_entry) == snapshot_entry
        return accepted, {}

    monkeypatch.setattr(replay, "load_replay_inputs_from_args", load)
    monkeypatch.setattr(replay, "verify_replay_input_snapshots_unchanged", lambda *_: {})
    monkeypatch.setattr(replay, "build_candidate_replay_contracts", lambda *_a, **_k: {})
    monkeypatch.setattr(replay, "build_replay_camera_contracts", lambda **_k: {})
    monkeypatch.setattr(replay, "_validate_output_scope", lambda _args: (out_root, out_root / "replay_manifest.json"))

    mdl_closure = {"closure_root": str(out_root / "material_closure")}

    def mirror(_native, *, artifact_dir, protected_snapshot):
        order.append("mirror")
        assert artifact_dir == out_root
        assert protected_snapshot == {"protected_roots": []}
        return mdl_closure

    def run_runtime(runtime_args, *_unused):
        order.append("runtime")
        assert runtime_args._preboot_material_closure == mdl_closure
        return {"classification": "test"}

    monkeypatch.setattr(replay, "_mirror_version_matched_mdl_closure", mirror)
    monkeypatch.setattr(replay, "_run_runtime", run_runtime)

    result = replay.run_replay(args)

    assert result == {"classification": "test"}
    assert order == ["publish", "load", "mirror", "runtime"]
    assert args._source_dependency_closure == closure
    assert args._preboot_material_closure == mdl_closure


def test_version_matched_mdl_source_is_bound_to_protected_snapshot(
    tmp_path, monkeypatch
):
    source_root = tmp_path / "omni/mdl/core"
    source_file = source_root / "Base/OmniGlass.mdl"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"trusted-mdl")
    source_sha256 = hashlib.sha256(source_file.read_bytes()).hexdigest()
    monkeypatch.setattr(
        replay,
        "RENDER_DIAGNOSTIC_VERSION_MATCHED_MDL_SOURCE_ROOT",
        source_root,
    )
    protected = replay.snapshot_render_diagnostic_protected_registry(
        protected_roots=(source_root,),
        protected_files=(),
        registry_id="test-version-matched-mdl-source",
    )
    source = {
        "source_root": str(source_root),
        "source_file_sha256": {"Base/OmniGlass.mdl": source_sha256},
    }

    assert replay.validate_version_matched_mdl_source_against_protected_snapshot(
        source,
        protected,
    ) == {
        "protected_source_root": str(source_root),
        "protected_source_tree_verified": True,
        "protected_source_file_count": 1,
    }

    source["source_file_sha256"]["Base/OmniGlass.mdl"] = "0" * 64
    with pytest.raises(ValueError, match="version_matched_mdl_protected_file"):
        replay.validate_version_matched_mdl_source_against_protected_snapshot(
            source,
            protected,
        )


@pytest.mark.parametrize("attack", ["symlink", "hardlink"])
def test_mdl_copy_destination_link_attack(tmp_path, monkeypatch, attack):
    source_root = tmp_path / "source"
    source_file = source_root / "Base/OmniGlass.mdl"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"trusted-mdl")
    source_sha256 = hashlib.sha256(source_file.read_bytes()).hexdigest()
    monkeypatch.setattr(
        replay,
        "build_version_matched_mdl_source_contract",
        lambda _native: {
            "source_root": str(source_root),
            "runtime_prefix": "/runtime",
            "runtime_version": "4.1.0",
            "source_root_under_runtime_prefix": True,
            "required_file_sha256": {"Base/OmniGlass.mdl": source_sha256},
            "source_file_sha256": {"Base/OmniGlass.mdl": source_sha256},
            "source_tree_sha256": "a" * 64,
            "host_isaac_sim_root_allowed": False,
        },
    )
    artifact_dir = tmp_path / "cell"
    destination = (
        artifact_dir
        / replay.VERSION_MATCHED_MDL_CLOSURE_DIRNAME
        / "Base/OmniGlass.mdl"
    )
    destination.parent.mkdir(parents=True)
    authority = tmp_path / "authority.mdl"
    authority.write_bytes(b"do-not-change")
    if attack == "symlink":
        destination.symlink_to(authority)
    else:
        os.link(authority, destination)

    with pytest.raises((FileExistsError, ValueError)):
        replay._mirror_version_matched_mdl_closure(
            object(),
            artifact_dir=artifact_dir,
        )

    assert authority.read_bytes() == b"do-not-change"


def test_success_manifest_binds_runtime_archive_bootstrap_and_source_snapshot(
    tmp_path, monkeypatch
):
    _support, _localized, _entry, protected = _source_snapshot_fixture(
        tmp_path, monkeypatch
    )
    cell = tmp_path / "cell"
    closure = replay.publish_render_diagnostic_source_dependency_snapshot(
        cell,
        protected_snapshot=protected,
        publication_nonce="f" * 64,
    )
    implementation = replay.build_matrix_implementation_identity_v1()
    archive_evidence, archive_bytes = (
        replay.build_render_diagnostic_runtime_implementation_archive(
            implementation
        )
    )
    archive_path = cell / "runtime_implementation_archive.zip"
    bootstrap_path = cell / "runtime_bootstrap.py"
    archive_path.write_bytes(archive_bytes)
    bootstrap_path.write_text(
        replay.RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE,
        encoding="utf-8",
    )
    inherited = {
        "schema_version": 1,
        "standard_fds": [0, 1, 2],
        "lock_fd": 5,
        "archive_fd": 6,
        "lock_access_mode": "READ_WRITE",
        "archive_access_mode": "READ_ONLY",
        "archive_seals": sorted(
            ["F_SEAL_SEAL", "F_SEAL_SHRINK", "F_SEAL_GROW", "F_SEAL_WRITE"]
        ),
    }
    material_root = cell / replay.VERSION_MATCHED_MDL_CLOSURE_DIRNAME
    material_root.mkdir()
    dependency_resolution = (
        replay.build_render_diagnostic_runtime_dependency_resolution(
            cell,
            closure,
            additional_allowed_dependency_roots=(material_root,),
        )
    )
    args = types.SimpleNamespace(
        _runtime_implementation_archive=archive_evidence,
        _inherited_fd_contract=inherited,
        _source_dependency_closure=closure,
        _preboot_material_closure={"closure_root": str(material_root)},
        _runtime_dependency_resolution=dependency_resolution,
    )
    result = {"runtime_contract": {}}

    attached = replay.attach_render_diagnostic_runtime_evidence(
        result,
        args=args,
        cell_root=cell,
        implementation_identity=implementation,
    )

    assert attached["runtime_implementation_archive"] == archive_evidence
    assert attached["runtime_implementation_archive_artifact"] == {
        "path": str(archive_path),
        "sha256": archive_evidence["archive_sha256"],
    }
    assert attached["runtime_bootstrap_sha256"] == (
        replay.RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SHA256
    )
    assert attached["source_dependency_closure"] == closure
    assert attached["inherited_fd_contract"] == inherited
    assert attached["runtime_contract"][
        "usd_dependency_closure_bytes_verified"
    ] is True
    assert attached["runtime_contract"][
        "renderer_dependency_consumption_verification"
    ] == "NOT_AVAILABLE_ISAACSIM41"

    archive_path.write_bytes(archive_bytes + b"tamper")
    with pytest.raises(ValueError, match="runtime_implementation_archive_artifact"):
        replay.attach_render_diagnostic_runtime_evidence(
            {"runtime_contract": {}},
            args=args,
            cell_root=cell,
            implementation_identity=implementation,
        )


def test_runtime_artifact_inventory_is_exact_and_rejects_duplicate_inode(
    tmp_path,
):
    cell = tmp_path / "cell"
    (cell / "nested").mkdir(parents=True)
    (cell / "a.bin").write_bytes(b"a")
    (cell / "nested/b.bin").write_bytes(b"bb")
    (cell / "replay_manifest.json").write_text("{}", encoding="ascii")
    (cell / "matrix_cell_evidence.json").write_text("{}", encoding="ascii")

    inventory = replay.build_render_diagnostic_cell_artifact_inventory(cell)

    assert [record["path"] for record in inventory["files"]] == [
        "a.bin",
        "nested/b.bin",
    ]
    assert replay.validate_render_diagnostic_cell_artifact_inventory(
        inventory,
        cell_root=cell,
    ) == inventory

    (cell / "unreferenced.bin").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="artifact_inventory_unreferenced"):
        replay.build_render_diagnostic_cell_artifact_inventory(
            cell,
            expected_relative_paths={"a.bin", "nested/b.bin"},
        )
    (cell / "unreferenced.bin").unlink()

    os.link(cell / "a.bin", cell / "nested/alias.bin")
    with pytest.raises(ValueError, match="artifact_inventory_duplicate_inode"):
        replay.build_render_diagnostic_cell_artifact_inventory(cell)

    (cell / "nested/alias.bin").unlink()
    (cell / "unexpected-empty").mkdir()
    with pytest.raises(ValueError, match="artifact_inventory_directory_membership"):
        replay.build_render_diagnostic_cell_artifact_inventory(cell)


def _run_runtime_bootstrap_probe(
    tmp_path,
    *,
    archive_fd,
    archive_sha256,
    extra_fds=(),
    stdin=None,
    isolated=True,
):
    lock_path = tmp_path / "bootstrap.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    command = [
        str(Path(sys.executable).resolve()),
        *(["-I", "-S"] if isolated else []),
        "-c",
        replay.RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SOURCE,
        "--runtime-child",
        "--runtime-parent-pid",
        str(os.getpid()),
        "--runtime-parent-lock-fd",
        str(lock_fd),
        "--runtime-parent-archive-fd",
        str(archive_fd),
        "--runtime-parent-archive-sha256",
        archive_sha256,
        "--runtime-bootstrap-sha256",
        replay.RENDER_DIAGNOSTIC_RUNTIME_BOOTSTRAP_SHA256,
    ]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE"}
    }
    environment.update(
        {
            "PYTHONNOUSERSITE": "1",
            "LABUTOPIA_REPO_ROOT": str(replay.REPO_ROOT),
            "LABUTOPIA_SEALED_RUNTIME": "1",
        }
    )
    try:
        return subprocess.run(
            command,
            cwd=replay.REPO_ROOT,
            env=environment,
            pass_fds=(lock_fd, archive_fd, *extra_fds),
            close_fds=True,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def test_live_launcher_rejects_repository_root_environment_override(tmp_path):
    environment = os.environ.copy()
    environment.pop("LABUTOPIA_SEALED_RUNTIME", None)
    environment["LABUTOPIA_REPO_ROOT"] = str(tmp_path / "attacker-root")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import tools.labutopia_fluid.run_real_beaker_omniglass_replay",
        ],
        cwd=replay.REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "live_repo_root_environment_override" in result.stderr


def test_runtime_archive_bootstrap_contract_fault_matrix(tmp_path):
    implementation = replay.build_matrix_implementation_identity_v1()
    archive_evidence, archive_bytes = (
        replay.build_render_diagnostic_runtime_implementation_archive(
            implementation
        )
    )
    sealed_fd = replay.create_render_diagnostic_sealed_archive_fd(archive_bytes)
    try:
        valid = _run_runtime_bootstrap_probe(
            tmp_path,
            archive_fd=sealed_fd,
            archive_sha256=archive_evidence["archive_sha256"],
        )
        assert valid.returncode != 0
        assert "runtime_child_parent_contract_unexpected_lock" in valid.stderr
        assert "sealed_runtime_live_repo_on_sys_path" not in valid.stderr

        unisolated = _run_runtime_bootstrap_probe(
            tmp_path,
            archive_fd=sealed_fd,
            archive_sha256=archive_evidence["archive_sha256"],
            isolated=False,
        )
        assert "runtime_bootstrap_interpreter_flags_invalid" in (
            unisolated.stderr
        )

        wrong_hash = _run_runtime_bootstrap_probe(
            tmp_path,
            archive_fd=sealed_fd,
            archive_sha256="0" * 64,
        )
        assert "runtime_bootstrap_archive_hash_invalid" in wrong_hash.stderr

        expanded_buffer = io.BytesIO(archive_bytes)
        with zipfile.ZipFile(expanded_buffer, mode="a", compression=zipfile.ZIP_STORED) as expanded:
            info = zipfile.ZipInfo("tools/labutopia_fluid/extra_runtime.py")
            info.compress_type = zipfile.ZIP_STORED
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.create_system = 3
            info.external_attr = (0o100444) << 16
            expanded.writestr(info, b"raise RuntimeError('unexpected')\n")
        expanded_bytes = expanded_buffer.getvalue()
        expanded_fd = replay.create_render_diagnostic_sealed_archive_fd(
            expanded_bytes
        )
        try:
            expanded_result = _run_runtime_bootstrap_probe(
                tmp_path,
                archive_fd=expanded_fd,
                archive_sha256=hashlib.sha256(expanded_bytes).hexdigest(),
            )
        finally:
            os.close(expanded_fd)
        assert "runtime_bootstrap_archive_membership_invalid" in (
            expanded_result.stderr
        )

        extra_path = tmp_path / "extra.fd"
        extra_path.write_bytes(b"extra")
        extra_fd = os.open(extra_path, os.O_RDONLY)
        try:
            extra = _run_runtime_bootstrap_probe(
                tmp_path,
                archive_fd=sealed_fd,
                archive_sha256=archive_evidence["archive_sha256"],
                extra_fds=(extra_fd,),
            )
        finally:
            os.close(extra_fd)
        assert "runtime_bootstrap_unexpected_fd" in extra.stderr
    finally:
        os.close(sealed_fd)

    unsealed_path = tmp_path / "unsealed.zip"
    unsealed_path.write_bytes(archive_bytes)
    unsealed_fd = os.open(unsealed_path, os.O_RDWR)
    try:
        unsealed = _run_runtime_bootstrap_probe(
            tmp_path,
            archive_fd=unsealed_fd,
            archive_sha256=archive_evidence["archive_sha256"],
        )
    finally:
        os.close(unsealed_fd)
    assert (
        "runtime_bootstrap_archive_not_readonly" in unsealed.stderr
        or "runtime_bootstrap_archive_unsealed" in unsealed.stderr
    )

    unsafe_stdin_path = tmp_path / "unsafe.stdin"
    unsafe_stdin_path.write_bytes(b"")
    with unsafe_stdin_path.open("rb") as unsafe_stdin:
        sealed_fd = replay.create_render_diagnostic_sealed_archive_fd(archive_bytes)
        try:
            unsafe = _run_runtime_bootstrap_probe(
                tmp_path,
                archive_fd=sealed_fd,
                archive_sha256=archive_evidence["archive_sha256"],
                stdin=unsafe_stdin,
            )
        finally:
            os.close(sealed_fd)
    assert "runtime_bootstrap_standard_fd_invalid" in (
        (unsafe.stderr or "") + (unsafe.stdout or "")
    )
