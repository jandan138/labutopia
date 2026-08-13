from argparse import Namespace

import numpy as np

from tools.labutopia_fluid import run_isaac41_liquid0812_async_rtx_benchmark as benchmark
from tools.labutopia_fluid import run_isaac41_liquid0812_benchmark as baseline


def test_50hz_render_schedule_covers_all_30hz_physics_states() -> None:
    render_count = benchmark._target_render_count(benchmark.EXPECTED_OBSERVATIONS)
    assert render_count == 1589
    mapping = [benchmark._physics_index_for_render(index) for index in range(render_count)]
    assert mapping[0] == 0
    assert mapping[-1] == benchmark.EXPECTED_OBSERVATIONS - 1
    assert set(mapping) == set(range(benchmark.EXPECTED_OBSERVATIONS))
    assert all(right >= left for left, right in zip(mapping, mapping[1:]))


def test_benchmark_defaults_to_reproducible_session_camera() -> None:
    args = benchmark.build_parser().parse_args([])
    assert args.camera_policy == "benchmark"
    assert args.width == 256
    assert args.height == 256
    assert args.save_full_video is False
    assert args.source_driver == "physx-kinematic-target"
    assert args.integration_hz == 120


def test_full_video_cuda_store_size_is_bounded() -> None:
    render_count = benchmark._target_render_count(benchmark.EXPECTED_OBSERVATIONS)
    byte_count = render_count * 3 * benchmark.DEFAULT_WIDTH * benchmark.DEFAULT_HEIGHT
    assert byte_count == 312_410_112
    assert byte_count < 300 * 1024 * 1024


def test_kinematic_driver_interpolates_four_targets_at_120hz() -> None:
    class View:
        def __init__(self) -> None:
            self.pose = np.asarray([[0, 0, 0, 0, 0, 0, 1]], dtype=np.float32)
            self.targets: list[np.ndarray] = []

        def set_kinematic_targets(self, targets, _indices) -> None:
            self.pose = np.asarray(targets, dtype=np.float32)
            self.targets.append(self.pose.copy())

        def get_transforms(self):
            return self.pose.copy()

    class Stepper:
        def __init__(self) -> None:
            self.steps = 0

        def step(self) -> None:
            self.steps += 1

    view = View()
    stepper = Stepper()
    identity = np.eye(4, dtype=np.float64)
    action = baseline._advance_source_interval(
        np=np,
        args=Namespace(
            source_driver="physx-kinematic-target", integration_hz=120
        ),
        stage=None,
        stepper=stepper,
        source_view=view,
        source_indices=np.asarray([0], dtype=np.uint32),
        alignment={"rigid_from_packet": identity, "usd_from_packet": identity},
        previous_packet_pose=np.asarray([0, 0, 0, 0, 0, 0, 1], dtype=np.float32),
        current_packet_pose=np.asarray([0.04, 0, 0, 0, 0, 0, 1], dtype=np.float32),
        source_matrix_time_code=None,
        simulation=None,
    )
    assert stepper.steps == 4
    assert len(view.targets) == 4
    assert [round(float(target[0, 0]), 3) for target in view.targets] == [
        0.01,
        0.02,
        0.03,
        0.04,
    ]
    assert action["integration_steps"] == 4
    assert action["pose_error"]["position_m"] == 0.0


def test_motion_acceptance_rejects_legacy_driver_and_visible_numeric_leak() -> None:
    poses = np.tile(
        np.asarray([0, 0, 0, 0, 0, 0, 1], dtype=np.float64), (3, 1)
    )
    scores = [
        {"source": 548, "nonfinite": 0, "below_table": 0},
        {"source": 530, "nonfinite": 0, "below_table": 0},
        {"source": 548, "nonfinite": 0, "below_table": 0},
    ]
    actions = [
        {"pose_error": {"position_m": 0.0, "rotation_degrees": 0.0}}
        for _ in scores
    ]
    result = baseline._motion_acceptance(
        np,
        scores=scores,
        action_records=actions,
        source_poses=poses,
        source_driver="legacy-usd-teleport",
    )
    assert result["pre_tilt_retention"]["maximum_allowed_outside_source_count"] == 10
    assert result["pre_tilt_retention"]["passed"] is False
    assert result["source_pose_tracking"]["passed"] is False


def test_gpu_preflight_rejects_a_low_utilization_compute_process(monkeypatch) -> None:
    monkeypatch.setattr(
        baseline,
        "_gpu_snapshot",
        lambda: {
            "gpus": [{"utilization_percent": 0.0}],
            "compute_processes": [{"pid": 123, "used_memory_mib": 567.0}],
        },
    )
    result = baseline._sample_gpu(seconds=1)
    assert result["maximum_utilization_percent"] == 0.0
    assert result["no_compute_processes"] is False
    assert result["idle_enough"] is False


def test_gpu_preflight_accepts_an_empty_low_utilization_gpu(monkeypatch) -> None:
    monkeypatch.setattr(
        baseline,
        "_gpu_snapshot",
        lambda: {
            "gpus": [{"utilization_percent": 4.0}],
            "compute_processes": [],
        },
    )
    result = baseline._sample_gpu(seconds=1)
    assert result["no_compute_processes"] is True
    assert result["idle_enough"] is True
