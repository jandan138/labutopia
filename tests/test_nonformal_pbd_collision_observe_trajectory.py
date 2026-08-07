from __future__ import annotations

from tools.labutopia_fluid import attest_isaac41_effective_runtime as attester
from tools.labutopia_fluid import run_nonformal_pbd_collision_observe_trajectory as runner


def test_collision_observe_runner_defaults_to_a_separate_diagnostic_config(tmp_path):
    args = runner.parse_args(["--out-dir", str(tmp_path / "new-run")])

    assert args.config == runner.DEFAULT_CONFIG.resolve()
    assert args.max_control_steps == 1200
    assert args.child is False


def test_collision_observe_runner_binds_controller_and_helper_sources():
    paths = set(runner._source_paths(attester.__file__))

    assert runner.__file__ in {str(path) for path in paths}
    assert any(path.name == "pick_controller.py" for path in paths)
    assert any(path.name == "pour_controller.py" for path in paths)
    assert any(path.name == "nonformal_collision_observe.py" for path in paths)
