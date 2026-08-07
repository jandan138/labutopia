from __future__ import annotations

from pathlib import Path

from tools.labutopia_fluid import run_real_pbd_g0_effective_offset_capability as runner


def test_pvd_capability_request_is_bound_to_cube_only_fixture_and_diagnostic_only_authorization():
    request = runner.build_capability_request()

    assert request["fixture"]["overlay_profile"]["id"] == runner.CUBE_ONLY_OVERLAY_PROFILE
    assert [item["id"] for item in request["fixture"]["overlay_profile"]["overlay_stack"]] == [
        "hidden_cube_collision_disable"
    ]
    assert request["authorization"] == {
        "effective_offsets_resolved": False,
        "g0_go_authorized": False,
        "phase3_authorized": False,
    }
    assert set(request["pvd_runtime_artifacts"]) == set(runner.PVD_RUNTIME_ARTIFACT_PATHS)
    closure = request["pvd_extension_closure"]
    assert closure["root"] == str(runner.PVD_EXTENSION_ROOT)
    assert closure["files"]
    assert {"relative_path", "byte_count", "sha256"} == set(closure["files"][0])


def test_pvd_capability_profile_and_source_closure_are_hash_bound():
    request = runner.build_capability_request()
    closure = set(runner.source_paths())
    profile = runner.PVD_CAPABILITY_PROFILE_PATH.read_text(encoding="utf-8")

    assert '"omni.physx.pvd" = { version = "106.0.20", exact = true }' in profile
    assert runner.PVD_CAPABILITY_PROFILE_PATH.resolve() in closure
    assert runner.PVD_CAPABILITY_PLAN_PATH.resolve() in closure
    assert request["kit_profile"]["sha256"] == runner._sha256_file(
        runner.PVD_CAPABILITY_PROFILE_PATH
    )
    assert "physics.updateToUsd = false" in profile
    assert "physics.updateParticlesToUsd = false" in profile
    assert "physics.updateVelocitiesToUsd = false" in profile
    assert 'exts."omni.kit.viewport.window".startup.disableWindowOnLoad = true' in profile


def test_pvd_capability_runner_has_an_isolated_create_only_output_contract(tmp_path):
    args = runner.parse_args(["--out-dir", str(tmp_path / "pvd-capability")])

    assert args.out_dir == (tmp_path / "pvd-capability").resolve()
    assert args.recording_dir == args.out_dir / "pvd-recording"
    assert args.conversion_dir == args.out_dir / "pvd-converted"
    assert runner.expected_child_returncode(runner.CAPABILITY_PASS) == 0
    assert runner.expected_child_returncode(runner.CAPABILITY_NO_GO) == 0
    assert runner.expected_child_returncode(runner.RUNTIME_BLOCKED) == 2


def test_child_publishes_pvd_observation_before_kit_shutdown():
    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert source.index("attestation.write_canonical_json(args.observation_path, observation)") < source.index(
        "app.close()"
    )


def test_child_emits_bootstrap_markers_around_attestation():
    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert source.index('_child_marker("before_simulation_app")') < source.index("app = SimulationApp(")
    assert source.index('_child_marker("after_simulation_app")') < source.index(
        '_child_marker("before_runtime_attestation")'
    )
    assert source.index('_child_marker("after_runtime_attestation")') < source.index(
        "attestation.write_canonical_json(args.runtime_receipt_path, receipt)"
    )


def test_pvd_is_enabled_after_fixture_composition_but_before_world_construction():
    source = Path(runner.__file__).read_text(encoding="utf-8")

    assert source.index("stage, timeline, topology, role_paths, stage_report = fk_runner._stage_fixture(") < source.index(
        "runtime_probe.configure_pvd_recording_before_scene("
    )
    assert source.index("runtime_probe.configure_pvd_recording_before_scene(") < source.index(
        "result = runtime_probe.run_pvd_offset_capability("
    )
