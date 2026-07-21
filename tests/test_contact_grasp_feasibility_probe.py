from __future__ import annotations

import json

import numpy as np
import pytest

from tools.labutopia_fluid import run_contact_grasp_feasibility_probe as probe


def test_velocity_probe_requires_nonzero_api_and_finite_difference_agreement():
    samples = [
        {
            "api_pad_velocity_m_s": [-0.0100, -0.0099],
            "finite_difference_pad_velocity_m_s": [-0.0101, -0.0098],
        },
        {
            "api_pad_velocity_m_s": [-0.0010, -0.0011],
            "finite_difference_pad_velocity_m_s": [-0.0011, -0.0010],
        },
    ]

    result = probe.summarize_pad_velocity_authority(
        samples,
        agreement_tolerance_m_s=0.0005,
    )

    assert result["nonzero_sample_count"] == 2
    assert result["maximum_absolute_error_m_s"] == pytest.approx(0.0001)
    assert result["passed"] is True

    samples[1]["finite_difference_pad_velocity_m_s"][1] = 0.01
    assert probe.summarize_pad_velocity_authority(
        samples,
        agreement_tolerance_m_s=0.0005,
    )["passed"] is False


def test_static_support_impulse_derives_robust_effective_payload_mass():
    impulses = [0.00980, 0.00981, 0.00982, 0.00979, 0.00981]

    result = probe.derive_effective_payload_mass_from_support(
        support_impulses_n_s=impulses,
        physics_dt=0.01,
        gravity_m_s2=9.81,
        minimum_samples=5,
    )

    assert result["sample_count"] == 5
    assert result["median_support_impulse_n_s"] == pytest.approx(0.00981)
    assert result["effective_payload_mass_kg"] == pytest.approx(0.1)
    assert result["passed"] is True


def test_static_support_mass_rejects_missing_or_unstable_load():
    with pytest.raises(ValueError, match="support_impulse_sample_count_insufficient"):
        probe.derive_effective_payload_mass_from_support(
            support_impulses_n_s=[0.01],
            physics_dt=0.01,
            gravity_m_s2=9.81,
            minimum_samples=2,
        )

    result = probe.derive_effective_payload_mass_from_support(
        support_impulses_n_s=[0.001, 0.02, 0.001, 0.02],
        physics_dt=0.01,
        gravity_m_s2=9.81,
        minimum_samples=4,
    )
    assert result["passed"] is False


def test_open_clearance_includes_both_offsets_tracking_and_margin():
    result = probe.evaluate_symmetric_open_clearance(
        open_inner_gap_m=0.080,
        source_width_m=0.069,
        source_contact_offset_m=0.002,
        finger_contact_offset_m=0.001,
        tracking_error_m=0.0005,
        numerical_margin_m=0.001,
    )

    assert result["per_side_open_clearance_m"] == pytest.approx(0.0055)
    assert result["required_per_side_clearance_m"] == pytest.approx(0.0045)
    assert result["passed"] is True

    blocked = probe.evaluate_symmetric_open_clearance(
        open_inner_gap_m=0.078,
        source_width_m=0.069,
        source_contact_offset_m=0.002,
        finger_contact_offset_m=0.001,
        tracking_error_m=0.0005,
        numerical_margin_m=0.001,
    )
    assert blocked["per_side_open_clearance_m"] == pytest.approx(0.0045)
    assert blocked["passed"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"open_inner_gap_m": np.nan},
        {"source_width_m": -1.0},
        {"source_contact_offset_m": -0.001},
        {"finger_contact_offset_m": True},
    ],
)
def test_open_clearance_rejects_invalid_measurements(kwargs):
    values = {
        "open_inner_gap_m": 0.080,
        "source_width_m": 0.069,
        "source_contact_offset_m": 0.002,
        "finger_contact_offset_m": 0.001,
        "tracking_error_m": 0.0005,
        "numerical_margin_m": 0.001,
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match="clearance_.*_invalid"):
        probe.evaluate_symmetric_open_clearance(**values)


def test_pre_sweep_clearance_fails_closed_with_unknown_budget_terms():
    result = probe.summarize_pre_sweep_clearance(
        open_inner_gap_m=0.07741653828466591,
        source_widths_m=[0.07096344, 0.07131712],
        source_contact_offset_m=0.002,
        finger_contact_offsets_m=[None, None],
        controller_tracking_error_m=None,
        numerical_margin_m=0.001,
    )

    assert result["measurement_complete"] is False
    assert result["passed"] is False
    assert result["unknown_budget_terms"] == [
        "finger_contact_offset_m",
        "controller_tracking_error_m",
    ]
    assert result["minimum_optimistic_remaining_margin_m"] == pytest.approx(
        0.000049709142332955
    )


def test_probe_prerequisites_require_every_cooked_body_and_clearance():
    report = {
        "frame_probe": {"passed": True},
        "velocity_probe": {"passed": True},
        "support_load_probe": {"passed": True},
        "cooked_collider_probe": {
            "bodies": {
                name: {"collider_count": 1, "colliders": [{}]}
                for name in (
                    "source",
                    "left_finger",
                    "right_finger",
                    "hand",
                    "table",
                )
            },
            "source_width_raycast": [{"source_width_y_m": 0.07}],
            "unresolved_contact_offset_paths": [],
            "pre_sweep_clearance": {
                "measurement_complete": True,
                "passed": True,
            },
        },
    }

    result = probe.evaluate_probe_prerequisites(report)

    assert result["passed"] is True
    assert result["failed_checks"] == []

    del report["cooked_collider_probe"]["bodies"]["table"]
    report["cooked_collider_probe"]["unresolved_contact_offset_paths"] = [
        "/finger"
    ]
    report["cooked_collider_probe"]["pre_sweep_clearance"]["passed"] = False
    blocked = probe.evaluate_probe_prerequisites(report)

    assert blocked["passed"] is False
    assert {
        "cooked_body_table",
        "contact_offsets_resolved",
        "pre_sweep_clearance",
    }.issubset(blocked["failed_checks"])


def test_probe_prerequisites_reject_collider_query_errors():
    body = {"collider_count": 1, "colliders": [{}]}
    report = {
        "frame_probe": {"passed": True},
        "velocity_probe": {"passed": True},
        "support_load_probe": {"passed": True},
        "cooked_collider_probe": {
            "bodies": {
                name: dict(body)
                for name in (
                    "source",
                    "left_finger",
                    "right_finger",
                    "hand",
                    "table",
                )
            },
            "source_width_raycast": [{"source_width_y_m": 0.07}],
            "unresolved_contact_offset_paths": [],
            "pre_sweep_clearance": {
                "measurement_complete": True,
                "passed": True,
            },
        },
    }
    report["cooked_collider_probe"]["bodies"]["hand"]["collider_errors"] = [
        "query_failed"
    ]

    result = probe.evaluate_probe_prerequisites(report)

    assert result["passed"] is False
    assert "cooked_body_hand" in result["failed_checks"]


def test_control_to_grasp_transform_uses_row_frame_composition():
    control_to_grasp = np.eye(4, dtype=np.float64)
    control_to_grasp[:3, :3] = np.diag([-1.0, -1.0, 1.0])
    control_to_grasp[3, 2] = -0.0034
    grasp_world = np.eye(4, dtype=np.float64)
    grasp_world[:3, :3] = np.asarray(
        [[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
    )
    grasp_world[3, :3] = [0.4, -0.2, 0.8]
    control_world = control_to_grasp @ grasp_world

    measured = probe.derive_control_to_target_row_matrix(
        control_world_matrix=control_world,
        target_world_matrix=grasp_world,
    )

    np.testing.assert_allclose(measured, control_to_grasp, rtol=0.0, atol=1.0e-12)


def test_row_world_matrix_converts_lula_column_rotation():
    column_rotation = np.asarray(
        [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
    )

    result = probe.row_world_matrix_from_lula_pose(
        position_world_m=[0.4, -0.2, 0.8],
        column_rotation_world=column_rotation,
    )

    np.testing.assert_array_equal(result[:3, :3], column_rotation.T)
    np.testing.assert_array_equal(result[3, :3], [0.4, -0.2, 0.8])
    np.testing.assert_array_equal(result[:, 3], [0.0, 0.0, 0.0, 1.0])


def test_provisional_report_is_parseable_before_application_close(tmp_path):
    output = tmp_path / "runtime_summary.pre_shutdown.json"
    report = {
        "schema_version": 1,
        "manifest_type": "contact_grasp_feasibility_probe_v1",
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "measurement_decision": "BLOCKED_SIDE_POSE_SWEEP_REQUIRED",
    }

    class TerminatingApplication:
        def close(self):
            persisted = json.loads(output.read_text(encoding="utf-8"))
            assert persisted == report
            raise SystemExit(0)

    with pytest.raises(SystemExit) as exc_info:
        probe._persist_provisional_before_shutdown(
            app=TerminatingApplication(),
            output_path=output,
            report=report,
        )

    assert exc_info.value.code == 0


def test_atomic_report_write_rejects_existing_output_and_serializes_strict_json(
    tmp_path,
):
    output = tmp_path / "report.json"

    probe._atomic_write_json(
        output,
        {"finite": 1.0, "nonfinite": np.asarray([np.nan, np.inf])},
    )

    raw = output.read_text(encoding="utf-8")
    parsed = json.loads(
        raw,
        parse_constant=lambda value: pytest.fail(
            f"non-strict JSON constant: {value}"
        ),
    )
    assert parsed == {
        "finite": 1.0,
        "nonfinite": ["NaN", "Infinity"],
    }
    with pytest.raises(FileExistsError, match="probe_output_exists"):
        probe._atomic_write_json(output, {"replacement": True})


def test_parent_seals_success_only_after_clean_child_exit():
    provisional = {
        "schema_version": 1,
        "manifest_type": "contact_grasp_feasibility_probe_v1",
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "measurement_decision": "BLOCKED_SIDE_POSE_SWEEP_REQUIRED",
        "prerequisites_passed": True,
    }

    final = probe._finalize_child_report(
        provisional,
        child_returncode=0,
        child_command=["python", "probe.py", "--runtime-child"],
    )

    assert final["decision"] == "BLOCKED_SIDE_POSE_SWEEP_REQUIRED"
    assert final["lifecycle_status"] == "completed"
    assert final["shutdown_status"] == "child_exit_0"
    assert final["child_process"]["returncode"] == 0


def test_parent_rejects_pre_shutdown_pass_after_nonzero_child_exit():
    provisional = {
        "schema_version": 1,
        "manifest_type": "contact_grasp_feasibility_probe_v1",
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "measurement_decision": "BLOCKED_SIDE_POSE_SWEEP_REQUIRED",
        "prerequisites_passed": True,
    }

    final = probe._finalize_child_report(
        provisional,
        child_returncode=9,
        child_command=["python", "probe.py", "--runtime-child"],
    )

    assert final["decision"] == "PROBE_RUNTIME_ERROR"
    assert final["lifecycle_status"] == "failed"
    assert final["shutdown_status"] == "child_exit_nonzero"
    assert final["pre_shutdown_decision"] == "BLOCKED_SIDE_POSE_SWEEP_REQUIRED"
    assert final["shutdown_error"]["returncode"] == 9


def test_parent_preserves_runtime_failure_when_shutdown_also_fails():
    fatal_error = {
        "phase": "runtime_measurement",
        "type": "RuntimeError",
        "message": "primary failure",
        "traceback": "primary traceback",
    }
    provisional = {
        "schema_version": 1,
        "manifest_type": "contact_grasp_feasibility_probe_v1",
        "lifecycle_status": "runtime_error_pending_application_close",
        "shutdown_status": "pending",
        "measurement_decision": "PROBE_RUNTIME_ERROR",
        "fatal_error": fatal_error,
    }

    final = probe._finalize_child_report(
        provisional,
        child_returncode=-11,
        child_command=["python", "probe.py", "--runtime-child"],
    )

    assert final["decision"] == "PROBE_RUNTIME_ERROR"
    assert final["fatal_error"] == fatal_error
    assert final["shutdown_error"]["returncode"] == -11
