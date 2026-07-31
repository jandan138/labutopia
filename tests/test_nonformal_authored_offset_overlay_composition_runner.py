from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from tools.labutopia_fluid import run_nonformal_authored_offset_overlay_composition as runner


def test_composition_request_binds_only_cube_disable_and_finite_offset_overlay():
    request = runner.build_composition_request()

    assert request["fixture"]["overlay_profile"]["id"] == runner.OVERLAY_PROFILE_ID
    assert [item["id"] for item in request["fixture"]["overlay_profile"]["overlay_stack"]] == [
        runner.OVERLAY_PROFILE_ID,
        "hidden_cube_collision_disable",
    ]
    assert request["authorization"] == {
        "effective_offsets_resolved": False,
        "clearance_certificate_authorized": False,
        "g0_go_authorized": False,
        "phase3_authorized": False,
    }
    assert request["kit_profile"]["pvd_extension_declared"] is False


def test_composition_runner_seals_the_overlay_and_uses_create_only_output():
    request = runner.build_composition_request()
    closure = set(runner.source_paths())
    with TemporaryDirectory(dir="/tmp/opencode") as directory:
        output = Path(directory) / "authored-offsets"
        args = runner.parse_args(["--out-dir", str(output)])

    assert runner.CALIBRATION_OVERLAY.resolve() in closure
    assert runner.HIDDEN_CUBE_OVERLAY.resolve() in closure
    assert runner.KIT_PROFILE_PATH.resolve() in closure
    assert args.out_dir == output.resolve()
    assert runner.expected_child_returncode(runner.PASS) == 0
    assert runner.expected_child_returncode(runner.NO_GO) == 0
    assert runner.expected_child_returncode(runner.RUNTIME_BLOCKED) == 2
    assert request["fixture"]["overlay_profile_sha256"] == runner._canonical_sha256(
        request["fixture"]["overlay_profile"]
    )


def test_composition_lane_has_no_pvd_or_world_construction_path():
    runner_source = Path(runner.__file__).read_text(encoding="utf-8")
    runtime_source = runner.RUNTIME_MODULE.read_text(encoding="utf-8")

    assert "from omni.isaac.core import World" not in runtime_source
    assert "World(" not in runtime_source
    assert "run_real_pbd_grasp_v2_g0_geometry" not in runner_source
    assert "get_enabled_extension_id" in runtime_source
    assert "pvd" not in runner.KIT_PROFILE_PATH.read_text(encoding="ascii").lower()
    assert "input_usd_dependency_closure_sha256" in runner_source
