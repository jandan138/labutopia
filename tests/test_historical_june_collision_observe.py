from __future__ import annotations

import sys
import types

import pytest
from omegaconf import OmegaConf

from tools.labutopia_fluid import attest_isaac41_effective_runtime as attester
from tools.labutopia_fluid import run_historical_june_collision_observe as runner


def test_historical_runner_binds_its_helper_sources(tmp_path):
    paths = set(
        runner._source_paths(
            attester.__file__,
            tmp_path,
            "localized",
        )
    )

    names = {path.name for path in paths}
    assert "nonformal_collision_observe.py" in names
    assert "run_nonformal_pbd_direct_contact_probe.py" in names
    assert "isaacsim_compat.py" in names
    assert runner.LOCALIZED_SCENE_PATH in paths
    assert runner.LOCALIZED_LIQUID_SCENE_PATH in paths
    assert any(path.name == "sektion_cabinet_visuals.usd" for path in paths)


def test_historical_completion_uses_terminal_controller_events():
    records = [
        {
            "pick_event": None,
            "pick_current_event": 7,
            "pour_event": None,
            "pour_current_event": 6,
        }
    ]

    assert runner.command_sequence_completed(records) is True


def test_historical_completion_rejects_incomplete_pour_event():
    records = [{"pick_current_event": 7, "pour_current_event": 5}]

    assert runner.command_sequence_completed(records) is False


def test_historical_task_termination_is_reported_separately_from_atomic_events():
    records = [
        {
            "phase_after": "FINISHED",
            "done": True,
            "success": True,
            "pick_current_event": 5,
            "pour_current_event": 5,
        }
    ]

    assert runner.historical_task_terminated(records) is True
    assert runner.command_sequence_completed(records) is False


def test_historical_asset_paths_require_the_local_scene_and_robot(tmp_path):
    root = tmp_path / "historical"
    scene = root / "assets/chemistry_lab/lab_001/lab_001.usd"
    robot = root / "assets/robots/Franka.usd"
    scene.parent.mkdir(parents=True)
    robot.parent.mkdir(parents=True)
    scene.write_bytes(b"scene")
    robot.write_bytes(b"robot")

    paths = runner.historical_asset_paths(root, asset_source="historical_raw")

    assert paths == {"scene": scene, "robot": robot}


def test_collect_mode_inference_shim_fails_if_inference_is_invoked():
    modules = {}
    shim = runner._HistoricalCollectModeInferenceShim(module_table=modules)

    shim.install()

    factory = modules[
        "controllers.inference_engines.inference_engine_factory"
    ].InferenceEngineFactory
    with pytest.raises(RuntimeError, match="historical_collect_mode_inference_unsupported"):
        factory.create_inference_engine()
    assert shim.record()["installed"] is True

    shim.close()
    assert modules == {}


def test_runtime_blocked_report_allows_kit_shutdown_exit_zero():
    assert runner.child_returncode_matches_decision("RUNTIME_BLOCKED", 0) is True
    assert runner.child_returncode_matches_decision("RUNTIME_BLOCKED", 2) is True
    assert runner.child_returncode_matches_decision("RUNTIME_BLOCKED", 1) is False
    assert runner.child_returncode_matches_decision(
        "HISTORICAL_COMMAND_TRAJECTORY_INCOMPLETE", 0
    ) is True


def test_historical_bounds_overlay_does_not_require_hydra_config(tmp_path):
    cfg = OmegaConf.create(
        {
            "max_episodes": 100,
            "task": {"max_steps": 1500},
            "multi_run": {"run_dir": "old-output"},
        }
    )

    runner.apply_historical_diagnostic_bounds(
        cfg,
        max_task_steps=12,
        out_dir=tmp_path,
    )

    assert cfg.max_episodes == 1
    assert cfg.task.max_steps == 12
    assert cfg.multi_run.run_dir == str(tmp_path / "historical_controller_output")
    assert "hydra" not in cfg


def test_historical_bounds_overlay_selects_localized_scene(tmp_path):
    cfg = OmegaConf.create(
        {
            "max_episodes": 100,
            "task": {"max_steps": 1500},
            "multi_run": {"run_dir": "old-output"},
            "usd_path": "raw/historical.usd",
        }
    )

    runner.apply_historical_diagnostic_bounds(
        cfg,
        max_task_steps=12,
        out_dir=tmp_path,
        scene_path=runner.LOCALIZED_SCENE_PATH,
    )

    assert cfg.usd_path == str(runner.LOCALIZED_SCENE_PATH.resolve())


def test_historical_runner_defaults_to_localized_asset_source(tmp_path):
    args = runner.parse_args(["--out-dir", str(tmp_path / "new-run")])

    assert args.asset_source == "localized"


def test_historical_runner_exposes_a_separate_localized_liquid_scene(tmp_path):
    args = runner.parse_args(
        [
            "--asset-source",
            "localized_liquid",
            "--out-dir",
            str(tmp_path / "liquid-run"),
        ]
    )

    assert args.asset_source == "localized_liquid"
    assert runner.historical_asset_paths(
        args.historical_root,
        asset_source=args.asset_source,
    )["scene"] == runner.LOCALIZED_LIQUID_SCENE_PATH


def test_localized_liquid_enables_only_presentation_water_overlay():
    assert runner.presentation_liquid_overlay_enabled("localized_liquid") is True
    assert runner.presentation_liquid_overlay_enabled("localized") is False
    assert runner.presentation_liquid_overlay_enabled("historical_raw") is False
    assert runner.PRESENTATION_LIQUID_OVERLAY_PARENT_PATH == "/World/beaker2/mesh"
    assert runner.PRESENTATION_LIQUID_OVERLAY_FRAME_PARENT_PATH == "/World/beaker2"


def test_localized_liquid_binds_presentation_overlay_sources(tmp_path):
    paths = set(
        runner._source_paths(
            attester.__file__,
            tmp_path,
            "localized_liquid",
        )
    )

    assert runner.REPO_ROOT / "tools/labutopia_fluid/omniglass_reference.py" in paths
    assert runner.REPO_ROOT / "tools/labutopia_fluid/real_beaker.py" in paths


def test_physical_pbd_mode_defaults_to_controlled_4096_particles(tmp_path):
    args = runner.parse_args(
        [
            "--asset-source",
            "localized_liquid",
            "--physical-pbd",
            "--out-dir",
            str(tmp_path / "physical-run"),
        ]
    )

    assert args.physical_pbd is True
    assert args.controlled_particle_count == 4096
    assert args.controlled_particle_seed == 0


def test_physical_pbd_mode_binds_pbd_helper_sources(tmp_path):
    paths = set(
        runner._source_paths(
            attester.__file__,
            tmp_path,
            "localized_liquid",
            physical_pbd=True,
        )
    )

    assert runner.REPO_ROOT / "tools/labutopia_fluid/fluid_recipe.py" in paths
    assert (
        runner.REPO_ROOT / "tools/labutopia_fluid/run_interndata_pour_parity_probe.py"
        in paths
    )
    assert (
        runner.REPO_ROOT
        / "tools/labutopia_fluid/run_colleague_native_usd_completed_pbd_step_video.py"
        in paths
    )


def test_physical_controller_recorder_bounds_a_failed_attempt(monkeypatch, tmp_path):
    class FakePourTaskController:
        def reset(self):
            return None

        def step(self, _state):
            return None, False, False

    package = types.ModuleType("controllers")
    package.__path__ = []
    module = types.ModuleType("controllers.pour_controller")
    module.PourTaskController = FakePourTaskController
    monkeypatch.setitem(sys.modules, "controllers", package)
    monkeypatch.setitem(sys.modules, "controllers.pour_controller", module)

    recorder = runner._HistoricalControllerRecorder(
        tmp_path,
        single_attempt_bound=True,
    )
    recorder.install()
    controller = types.SimpleNamespace(
        cfg=types.SimpleNamespace(max_episodes=1),
        data_collector=types.SimpleNamespace(episode_count=0),
    )

    FakePourTaskController.reset(controller)
    assert controller.data_collector.episode_count == 0
    FakePourTaskController.reset(controller)

    summary = recorder.close()
    assert controller.data_collector.episode_count == 1
    assert summary["forced_episode_bound_applied"] is True
    assert summary["controller_reset_count"] == 2


def test_historical_application_proxy_defers_only_shutdown():
    class Application:
        def __init__(self):
            self.closed = False

        def is_running(self):
            return True

        def close(self):
            self.closed = True

    application = Application()
    proxy = runner._HistoricalApplicationProxy(application)

    assert proxy.is_running() is True
    proxy.close()

    assert application.closed is False
    assert proxy.close_request_count == 1


def test_stage_closure_records_unresolved_remote_layers(tmp_path):
    local = tmp_path / "scene.usd"
    local.write_bytes(b"scene")

    class Layer:
        def __init__(self, identifier, real_path, anonymous=False):
            self.identifier = identifier
            self.realPath = real_path
            self.anonymous = anonymous

    class Stage:
        def GetUsedLayers(self):
            return [
                Layer(str(local), str(local)),
                Layer("http://example.invalid/remote.usd", ""),
                Layer("anon:session", "", anonymous=True),
            ]

    closure = runner._stage_input_closure(Stage())

    assert closure["complete"] is False
    assert closure["files"] == {str(local): runner._sha256_file(local)}
    assert closure["unresolved_layers"] == [
        {
            "identifier": "http://example.invalid/remote.usd",
            "reason": "remote_or_virtual_layer",
        }
    ]
