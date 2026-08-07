from __future__ import annotations

import socket
import subprocess
import sys

import numpy as np
import pytest

from tools.labutopia_fluid.fluid_benchmark_bridge import (
    BRIDGE_SCHEMA,
    MAX_SURFACE_VERTICES,
    RENDER_BRIDGE_SCHEMA,
    SharedFluidFrame,
    SharedFluidRenderFrame,
    receive_message,
    send_message,
)
from tools.labutopia_fluid.fluid_benchmark_contract import (
    EXPECTED_PARTICLE_COUNT,
    classify_positions,
    evaluate_quality_gate,
    evaluate_stability_gate,
    interpolate_pose_xyzw,
    retarget_source_poses,
    row_transform_points,
    summarize_milliseconds,
)
from tools.labutopia_fluid.run_newton140_mpm_benchmark import (
    parse_solver_diagnostics,
    precompute_substep_poses,
)


def test_row_transform_points_uses_usd_row_affine_convention() -> None:
    matrix = np.eye(4)
    matrix[3, :3] = [1.0, 2.0, 3.0]
    actual = row_transform_points([[0.25, -0.5, 1.0]], matrix)
    np.testing.assert_allclose(actual, [[1.25, 1.5, 4.0]])


def test_classify_positions_and_quality_gate() -> None:
    frame = np.eye(4)
    target = np.eye(4)
    target[3, :3] = [1.0, 0.0, 0.0]
    positions = np.repeat([[1.0, 0.0, 0.05]], EXPECTED_PARTICLE_COUNT, axis=0)
    score = classify_positions(
        positions,
        source_frame_world_matrix=frame,
        target_frame_world_matrix=target,
        source_interior_radius_m=0.03,
        target_interior_radius_m=0.03,
        source_floor_m=0.0,
        source_rim_m=0.1,
        target_floor_m=0.0,
        target_rim_m=0.1,
        table_top_z_m=-0.1,
    )
    assert score["target"] == EXPECTED_PARTICLE_COUNT
    quality = evaluate_quality_gate(
        [score] * 100,
        visual_liquid_passed=True,
    )
    assert quality["passed"] is True


def test_quality_gate_requires_visual_review() -> None:
    score = {
        "source": 0,
        "target": 3600,
        "below_table": 0,
        "tabletop_spill": 0,
        "transit": 0,
        "nonfinite": 0,
        "target_fraction": 1.0,
        "tabletop_spill_fraction": 0.0,
    }
    quality = evaluate_quality_gate(
        [score] * 100,
        visual_liquid_passed=None,
    )
    assert quality["passed"] is False
    assert quality["numeric_passed"] is True
    assert quality["visual_review_pending"] is True


def test_stability_gate_does_not_require_good_pour_quality() -> None:
    score = {
        "observation_index": 0,
        "source": 0,
        "target": 0,
        "below_table": 0,
        "tabletop_spill": EXPECTED_PARTICLE_COUNT,
        "transit": 0,
        "nonfinite": 0,
        "partition_total": EXPECTED_PARTICLE_COUNT,
        "valid": True,
        "target_fraction": 0.0,
        "tabletop_spill_fraction": 1.0,
    }
    stability = evaluate_stability_gate(
        [score], expected_particle_count=EXPECTED_PARTICLE_COUNT
    )
    assert stability["passed"] is True


def test_stability_gate_rejects_particle_partition_loss() -> None:
    score = {
        "observation_index": 7,
        "below_table": 0,
        "nonfinite": 0,
        "partition_total": EXPECTED_PARTICLE_COUNT - 1,
        "valid": False,
    }
    stability = evaluate_stability_gate(
        [score], expected_particle_count=EXPECTED_PARTICLE_COUNT
    )
    assert stability["passed"] is False
    assert stability["invalid_partition_frames"] == [7]


def test_timing_summary() -> None:
    result = summarize_milliseconds([1.0, 2.0, 3.0, 4.0])
    assert result["count"] == 4
    assert result["mean_ms"] == pytest.approx(2.5)
    assert result["median_ms"] == pytest.approx(2.5)


def test_pose_interpolation_uses_shortest_quaternion_arc() -> None:
    start = np.asarray([0, 0, 0, 0, 0, 0, 1], dtype=np.float64)
    end = np.asarray([4, 8, 12, 0, 0, 0, -1], dtype=np.float64)
    actual = interpolate_pose_xyzw(start, end, 0.25)
    np.testing.assert_allclose(actual[:3], [1, 2, 3])
    np.testing.assert_allclose(actual[3:], [0, 0, 0, 1])


def test_precompute_substep_poses_preserves_four_step_slerp_schedule() -> None:
    poses = np.asarray(
        [
            [0, 0, 0, 0, 0, 0, 1],
            [4, 8, 12, 0, 0, 0, -1],
        ],
        dtype=np.float64,
    )
    actual = precompute_substep_poses(
        poses,
        observation_count=2,
        substeps=4,
    )
    assert actual.shape == (8, 7)
    np.testing.assert_allclose(actual[:4, :3], 0.0)
    np.testing.assert_allclose(actual[4:, :3], [[1, 2, 3], [2, 4, 6], [3, 6, 9], [4, 8, 12]])
    np.testing.assert_allclose(
        actual[:, 3:],
        np.repeat([[0, 0, 0, 1]], len(actual), axis=0),
    )


def test_parse_solver_diagnostics_corrects_newton_cuda_counter_offset() -> None:
    parsed = parse_solver_diagnostics(
        "Gauss-Seidel terminated after 16 iterations with residuals 0.001, 0.002\n"
        "Gauss-Seidel terminated after 6 iterations with residuals 3e-4, 4e-4\n"
    )
    assert parsed["record_count"] == 2
    assert parsed["actual_iteration_histogram"] == {"15": 1, "5": 1}
    assert parsed["maximum_actual_iterations"] == 15
    assert parsed["final_residual_linf"] == pytest.approx(4.0e-4)


def test_newton_pour_retarget_blends_translation_only() -> None:
    poses = np.zeros((953, 7), dtype=np.float64)
    poses[:, 6] = 1.0
    actual = retarget_source_poses(
        poses,
        offset_m=(1.0, 2.0, 3.0),
        blend_observations=(10, 20),
    )
    np.testing.assert_allclose(actual[9, :3], 0.0)
    np.testing.assert_allclose(actual[15, :3], [0.5, 1.0, 1.5])
    np.testing.assert_allclose(actual[20, :3], [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(actual[:, 3:], poses[:, 3:])


def test_shared_frame_round_trip_and_socket_messages() -> None:
    frame = SharedFluidFrame.create()
    try:
        positions = np.arange(
            EXPECTED_PARTICLE_COUNT * 3,
            dtype=np.float32,
        ).reshape(EXPECTED_PARTICLE_COUNT, 3)
        checksum = frame.write(
            positions,
            frame_index=17,
            simulation_time_s=0.5,
        )
        attached = SharedFluidFrame.attach(frame.name)
        try:
            actual, metadata = attached.read(expected_frame_index=17)
            np.testing.assert_array_equal(actual, positions)
            assert metadata["schema"] == BRIDGE_SCHEMA
            assert metadata["checksum_crc32"] == checksum
        finally:
            attached.close()

        left, right = socket.socketpair()
        try:
            send_message(left, {"schema": BRIDGE_SCHEMA, "type": "hello"})
            assert receive_message(right) == {
                "schema": BRIDGE_SCHEMA,
                "type": "hello",
            }
        finally:
            left.close()
            right.close()
    finally:
        frame.close()
        frame.unlink()


def test_render_frame_v2_round_trips_particles_and_surface() -> None:
    frame = SharedFluidRenderFrame.create()
    try:
        particles = np.arange(
            EXPECTED_PARTICLE_COUNT * 3, dtype=np.float32
        ).reshape(EXPECTED_PARTICLE_COUNT, 3)
        particle_checksum = frame.write_particles(
            particles, frame_index=3, simulation_time_s=0.1
        )
        attached = SharedFluidRenderFrame.attach(frame.name)
        try:
            arrays, metadata = attached.read(expected_frame_index=3)
            np.testing.assert_array_equal(arrays["positions"], particles)
            assert metadata["schema"] == RENDER_BRIDGE_SCHEMA
            assert metadata["representation"] == "particles"
            assert metadata["checksum_crc32"] == particle_checksum

            vertices = np.asarray(
                [[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32
            )
            indices = np.asarray([0, 1, 2], dtype=np.int32)
            residuals = np.asarray([[2, 2, 2]], dtype=np.float32)
            surface_checksum = frame.write_surface(
                vertices,
                indices,
                residuals,
                frame_index=4,
                simulation_time_s=4.0 / 30.0,
            )
            arrays, metadata = attached.read(expected_frame_index=4)
            np.testing.assert_array_equal(arrays["vertices"], vertices)
            np.testing.assert_array_equal(arrays["indices"], indices)
            np.testing.assert_array_equal(arrays["residual_positions"], residuals)
            assert metadata["representation"] == "surface_gpu"
            assert metadata["checksum_crc32"] == surface_checksum
        finally:
            attached.close()
    finally:
        frame.close()
        frame.unlink()


def test_render_frame_v2_fails_closed_on_mesh_capacity_and_indices() -> None:
    frame = SharedFluidRenderFrame.create()
    try:
        with pytest.raises(ValueError, match="vertex_capacity"):
            frame.write_surface(
                np.zeros((MAX_SURFACE_VERTICES + 1, 3), dtype=np.float32),
                np.zeros((0,), dtype=np.int32),
                np.zeros((0, 3), dtype=np.float32),
                frame_index=0,
                simulation_time_s=0.0,
            )
        with pytest.raises(ValueError, match="indices_invalid"):
            frame.write_surface(
                np.zeros((3, 3), dtype=np.float32),
                np.asarray([0, 1, 3], dtype=np.int32),
                np.zeros((0, 3), dtype=np.float32),
                frame_index=0,
                simulation_time_s=0.0,
            )
    finally:
        frame.close()
        frame.unlink()


def test_shared_frame_attachment_process_does_not_unlink_owner_storage() -> None:
    frame = SharedFluidFrame.create()
    try:
        positions = np.zeros((EXPECTED_PARTICLE_COUNT, 3), dtype=np.float32)
        frame.write(positions, frame_index=3, simulation_time_s=0.1)
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from tools.labutopia_fluid.fluid_benchmark_bridge "
                    "import SharedFluidFrame; "
                    f"f=SharedFluidFrame.attach({frame.name!r}); "
                    "f.read(expected_frame_index=3); f.close()"
                ),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert completed.returncode == 0, completed.stderr
        assert "resource_tracker" not in completed.stderr
        actual, _ = frame.read(expected_frame_index=3)
        np.testing.assert_array_equal(actual, positions)
    finally:
        frame.close()
        frame.unlink()
