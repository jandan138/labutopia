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
    assert args.camera_policy == "trajectory-follow"
    assert args.width == 256
    assert args.height == 256
    assert args.save_full_video is False
    assert args.source_driver == "physx-kinematic-target"
    assert args.integration_hz == 120
    assert args.aa_mode == "dlss"
    assert args.capture_mode == "zero-copy-async"
    assert args.scheduler_mode == "continuous"
    assert args.diagnostic_visibility == "full"
    assert args.pose_render_settle_frames == 0
    assert args.rt_subframes == 1
    assert args.freeze_physics_index is None
    assert args.freeze_render_frames == 96
    assert args.output_schedule == "trajectory-50hz"
    assert args.capture_start_physics_index == 0
    assert args.save_flicker_audit is False


def test_frozen_render_schedule_repeats_one_completed_physics_state() -> None:
    args = benchmark.build_parser().parse_args(
        [
            "--max-observations",
            "480",
            "--freeze-physics-index",
            "448",
            "--freeze-render-frames",
            "96",
        ]
    )
    benchmark._validate_args(args)
    assert benchmark._render_schedule(args) == {
        "mode": "frozen-state-diagnostic",
        "render_count": 96,
        "expected_physics_count": 449,
        "freeze_physics_index": 448,
        "encoded_fps": 50,
        "mapping": "physics_index=448 for every captured frame",
    }


def test_stable_30hz_schedule_captures_one_settled_frame_per_state() -> None:
    args = benchmark.build_parser().parse_args(
        [
            "--max-observations",
            "480",
            "--output-schedule",
            "stable-30hz",
            "--capture-start-physics-index",
            "448",
            "--scheduler-mode",
            "step-wait",
            "--pose-render-settle-frames",
            "1",
        ]
    )
    benchmark._validate_args(args)
    assert benchmark._render_schedule(args) == {
        "mode": "stable-30hz",
        "render_count": 32,
        "expected_physics_count": 480,
        "capture_start_physics_index": 448,
        "encoded_fps": 30,
        "mapping": "physics_index=render_index+448",
    }


def test_capture_mode_contract_marks_managed_copy_as_safe_async() -> None:
    managed = benchmark._capture_mode_contract("managed-cuda-copy")
    assert managed == {
        "mode": "managed-cuda-copy",
        "backend": "replicator_ldr_annotator",
        "annotator_device": "cuda",
        "annotator_do_array_copy": True,
        "sink_blocking_copy": False,
        "retain_source_until_cuda_event": True,
        "intended_use": "safe_async_candidate",
    }
    cpu = benchmark._capture_mode_contract("cpu-copy-reference")
    assert cpu["annotator_device"] == "cpu"
    assert cpu["sink_blocking_copy"] is True


def test_viewport_reference_contract_is_explicitly_cpu_readback() -> None:
    reference = benchmark._capture_mode_contract("viewport-byte-reference")
    assert reference["backend"] == "viewport_byte_capture"
    assert reference["annotator_do_array_copy"] is None
    assert reference["annotator_device"] == "cpu"


def test_viewport_reference_requires_matching_lane_and_scheduler() -> None:
    import pytest

    args = benchmark.build_parser().parse_args(
        ["--capture-mode", "viewport-byte-reference"]
    )
    with pytest.raises(
        ValueError, match="viewport_capture_mode_and_scheduler_must_match"
    ):
        benchmark._validate_args(args)

    args = benchmark.build_parser().parse_args(
        [
            "--capture-mode",
            "viewport-byte-reference",
            "--scheduler-mode",
            "viewport-capture",
            "--lane",
            "headless-product",
        ]
    )
    with pytest.raises(ValueError, match="viewport_capture_requires"):
        benchmark._validate_args(args)


def test_root_cause_classifier_localizes_zero_copy_lifetime() -> None:
    cells = {
        "zero-copy-async__continuous__full": {"passed": False},
        "zero-copy-blocking__continuous__full": {"passed": True},
        "managed-cuda-copy__continuous__full": {"passed": True},
        "cpu-copy-reference__continuous__full": {"passed": True},
    }
    result = benchmark._classify_flicker_root_cause(cells)
    assert result["status"] == "localized"
    assert result["cause"] == (
        "asynchronous_source_buffer_lifetime_or_cuda_stream_ordering"
    )
    assert result["selected_capture_mode"] == "managed-cuda-copy"


def test_root_cause_classifier_distinguishes_scheduler_and_transparency() -> None:
    scheduler = benchmark._classify_flicker_root_cause(
        {
            "zero-copy-async__continuous__full": {"passed": False},
            "zero-copy-blocking__continuous__full": {"passed": False},
            "managed-cuda-copy__continuous__full": {"passed": False},
            "cpu-copy-reference__continuous__full": {"passed": False},
            "managed-cuda-copy__step-wait__full": {"passed": True},
        }
    )
    assert scheduler["cause"] == "continuous_scheduler_render_state_coherence"

    glass = benchmark._classify_flicker_root_cause(
        {
            "zero-copy-async__continuous__full": {"passed": False},
            "zero-copy-blocking__continuous__full": {"passed": False},
            "managed-cuda-copy__continuous__full": {"passed": False},
            "cpu-copy-reference__continuous__full": {"passed": False},
            "managed-cuda-copy__step-wait__full": {"passed": False},
            "managed-cuda-copy__step-wait__hide-liquid": {"passed": False},
            "managed-cuda-copy__step-wait__marker-only": {"passed": True},
        }
    )
    assert glass["cause"] == "original_glass_transparency_or_refraction_path"


def test_root_cause_composer_requires_full_video(tmp_path) -> None:
    import json
    import pytest

    path = tmp_path / "result.json"
    path.write_text(
        json.dumps(
            {
                "configuration": {
                    "capture": {"mode": "managed-cuda-copy"},
                    "scheduler_mode": "continuous",
                },
                "diagnostic_visibility": {"mode": "full"},
                "artifacts": {"full_video": None},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="root_cause_cell_missing_full_video"):
        benchmark.compose_root_cause_audit([path])


def test_flicker_audit_passes_stable_same_state_pairs() -> None:
    frames = np.zeros((4, 32, 32, 3), dtype=np.uint8)
    records = [
        {
            "render_index": index,
            "physics_index": index // 2,
            "source_center_px": [16.0, 16.0],
            "source_moving": index >= 2,
        }
        for index in range(4)
    ]
    result = benchmark._evaluate_flicker_frames(frames, records)
    assert result["passed"] is True
    assert result["pair_count"] == 1


def test_flicker_audit_rejects_alternating_source_appearance() -> None:
    frames = np.zeros((4, 32, 32, 3), dtype=np.uint8)
    frames[3, 8:24, 8:24] = 64
    records = [
        {
            "render_index": index,
            "physics_index": index // 2,
            "source_center_px": [16.0, 16.0],
            "source_moving": index >= 2,
        }
        for index in range(4)
    ]
    result = benchmark._evaluate_flicker_frames(frames, records)
    assert result["passed"] is False
    assert result["summary"]["changed_fraction_max"] > 0.01


def test_flicker_audit_requires_full_video() -> None:
    args = benchmark.build_parser().parse_args(["--save-flicker-audit"])
    import pytest

    with pytest.raises(ValueError, match="flicker_audit_requires_full_video"):
        benchmark._validate_args(args)


def test_trajectory_camera_contract_covers_complete_motion_and_target() -> None:
    source_bounds = {
        "minimum": (0.25, 0.03, 0.76),
        "maximum": (0.37, 0.15, 0.90),
        "center": (0.31, 0.09, 0.83),
        "extent": (0.12, 0.12, 0.14),
    }
    target_bounds = {
        "minimum": (0.20, -0.30, 0.76),
        "maximum": (0.36, -0.14, 0.92),
        "center": (0.28, -0.22, 0.84),
        "extent": (0.16, 0.16, 0.16),
    }
    poses = np.asarray(
        [
            [0.31, 0.09, 0.83, 0, 0, 0, 1],
            [0.26, -0.09, 1.11, 0, 0, 0, 1],
            [0.28, -0.19, 1.05, 0, 0, 0, 1],
        ],
        dtype=np.float64,
    )
    contract = benchmark._trajectory_envelope_camera_contract(
        source_bounds=source_bounds,
        target_bounds=target_bounds,
        source_poses_xyzw=poses,
        table_z=0.772,
    )
    framing = contract["framing_contract"]
    assert framing["all_source_pose_centers_inside_envelope"] is True
    assert framing["target_bounds_inside_envelope"] is True
    assert framing["tabletop_inside_envelope"] is True
    assert contract["envelope"]["source_pose_count"] == 3
    assert contract["envelope"]["padding_fraction"] == 0.08
    assert contract["envelope"]["maximum"][2] > 1.15
    assert framing["sphere_angular_radius_degrees"] <= (
        framing["limiting_fov_degrees"] / 2.0
    )


def test_follow_camera_adapts_to_each_physics_state_without_touching_physics() -> None:
    source_bounds = {
        "minimum": (0.25, 0.03, 0.76),
        "maximum": (0.37, 0.15, 0.90),
        "center": (0.31, 0.09, 0.83),
        "extent": (0.12, 0.12, 0.14),
    }
    target_bounds = {
        "minimum": (0.20, -0.30, 0.76),
        "maximum": (0.36, -0.14, 0.92),
        "center": (0.28, -0.22, 0.84),
        "extent": (0.16, 0.16, 0.16),
    }
    poses = np.asarray(
        [
            [0.31, 0.09, 0.83, 0, 0, 0, 1],
            [0.26, -0.09, 1.11, 0, 0, 0, 1],
            [0.28, -0.19, 1.05, 0, 0, 0, 1],
        ],
        dtype=np.float64,
    )
    contract = benchmark._source_follow_camera_contract(
        source_bounds=source_bounds,
        target_bounds=target_bounds,
        source_poses_xyzw=poses,
        table_z=0.772,
    )
    assert contract["source_pose_count"] == 3
    assert contract["physics_changes"] is False
    assert contract["same_physics_state_reuses_camera_pose"] is True
    assert len(contract["frame_poses"]) == 3
    assert contract["frame_poses"][0] != contract["frame_poses"][1]
    assert contract["maximum_camera_distance_m"] >= contract["minimum_camera_distance_m"]


def test_full_video_cuda_store_size_is_bounded() -> None:
    render_count = benchmark._target_render_count(benchmark.EXPECTED_OBSERVATIONS)
    byte_count = render_count * 3 * benchmark.DEFAULT_WIDTH * benchmark.DEFAULT_HEIGHT
    assert byte_count == 312_410_112
    assert byte_count < 300 * 1024 * 1024


def test_visible_sync_audit_selects_four_continuous_nine_state_windows() -> None:
    poses = np.tile(
        np.asarray([0, 0, 0, 0, 0, 0, 1], dtype=np.float64),
        (benchmark.EXPECTED_OBSERVATIONS, 1),
    )
    poses[:, 0] = np.linspace(0.0, 0.4, len(poses))
    poses[300, 0] += 0.02
    angles = np.linspace(0.0, np.pi / 2.0, len(poses) - 500)
    poses[500:, 5] = np.sin(angles / 2.0)
    poses[500:, 6] = np.cos(angles / 2.0)

    windows = benchmark._sync_audit_physics_indices(poses)

    assert list(windows) == ["static", "translation_lift", "mid_tilt", "final_settle"]
    assert windows["static"] == list(range(9))
    assert windows["final_settle"] == list(range(944, 953))
    assert all(
        len(indices) == 9 and indices == list(range(indices[0], indices[0] + 9))
        for indices in windows.values()
    )


def test_visible_sync_audit_rejects_a_frozen_visible_source() -> None:
    stage_names = ("static", "translation_lift", "mid_tilt", "final_settle")
    records = []
    for stage_index, stage_name in enumerate(stage_names):
        for sample in range(9):
            records.append(
                {
                    "stage": stage_name,
                    "physics_index": stage_index * 9 + sample,
                    "mask_pixel_count": 100,
                    "mask_centroid_px": [20.0, 20.0],
                    "projected_center_px": [20.0 + stage_index * 20.0, 20.0],
                }
            )

    audit = benchmark._evaluate_visible_sync_records(records)

    assert audit["passed"] is False
    assert any(not item["passed"] for item in audit["displacements"])


def test_projection_places_camera_target_at_image_center() -> None:
    projected = benchmark._project_world_point(
        [0.0, 0.0, 0.0],
        eye=[1.0, 0.0, 0.0],
        target=[0.0, 0.0, 0.0],
        width=256,
        height=256,
        focal_length_mm=26.0,
        horizontal_aperture_mm=24.0,
        vertical_aperture_mm=16.0,
    )
    assert projected == (128.0, 128.0)


def test_instance_id_lookup_supports_isaac41_label_mapping() -> None:
    ids = benchmark._source_instance_ids(
        {
            "idToLabels": {
                "0": "BACKGROUND",
                "7": {"class": benchmark.SOURCE_SEMANTIC_LABEL},
            }
        }
    )
    assert ids == [7]


def test_kinematic_driver_interpolates_four_targets_at_120hz(monkeypatch) -> None:
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
    monkeypatch.setattr(baseline, "_prim_world_matrix", lambda _stage, _path: identity)
    monkeypatch.setattr(baseline, "_mirror_physx_pose_to_usd", lambda *_args: None)
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
        {
            "pose_error": {"position_m": 0.0, "rotation_degrees": 0.0},
            "usd_pose_error": {"position_m": 0.0, "rotation_degrees": 0.0},
            "mesh_pose_error": {"position_m": 0.0, "rotation_degrees": 0.0},
        }
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
