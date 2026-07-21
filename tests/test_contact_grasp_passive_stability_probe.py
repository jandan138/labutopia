from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from tools.labutopia_fluid import (
    run_contact_grasp_passive_stability_probe as probe,
)
from utils import isaac_fluid_evaluation as isaac_fluid


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    REPO_ROOT / "config/level1_pour_online_fluid_native_expert_contact_v1.yaml"
)
PARTICLE_PATH = "/World/InternDataParityFluid/Particles"


def _rotation_z(degrees: float) -> np.ndarray:
    angle = np.radians(degrees)
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = [
        [np.cos(angle), np.sin(angle), 0.0],
        [-np.sin(angle), np.cos(angle), 0.0],
        [0.0, 0.0, 1.0],
    ]
    return result


def _schedule_records(
    *,
    start_world_step: int = 900,
    start_time: float = 7.5,
    physics_dt: float = 1 / 120,
) -> list[dict]:
    records = [
        {
            "local_step": 0,
            "phase": "baseline",
            "phase_step": 0,
            "world_step": start_world_step,
            "world_time_s": start_time,
        }
    ]
    for local_step in range(1, 481):
        if local_step <= 120:
            phase = "pre_roll"
            phase_step = local_step
        else:
            phase = "hold"
            phase_step = local_step - 120
        records.append(
            {
                "local_step": local_step,
                "phase": phase,
                "phase_step": phase_step,
                "world_step": start_world_step + local_step,
                "world_time_s": start_time + local_step * physics_dt,
            }
        )
    return records


def _comparable_report(treatment: str, *, motion_passed: bool) -> dict:
    return {
        "schema_version": 1,
        "manifest_type": "contact_grasp_passive_stability_probe_v1",
        "lifecycle_status": "completed",
        "decision": "PASSIVE_STABILITY_PASS" if motion_passed else "PASSIVE_STABILITY_FAIL",
        "treatment": treatment,
        "comparison_contract": {
            "config_sha256": "a" * 64,
            "usd_dependency_closure_sha256": "b" * 64,
            "runner_sha256": "c" * 64,
            "runtime_id": "isaac-4.1-physx-106.0.20",
            "physics_dt": 1 / 120,
            "gravity_world_m_s2": [0.0, 0.0, -9.81],
            "source_actor_path": "/World/beaker2",
            "particle_path": PARTICLE_PATH,
            "pre_roll_steps": 120,
            "hold_steps": 360,
            "classifier_epsilon_m": 5e-5,
        },
        "motion_stability": {"valid": True, "passed": motion_passed},
        "containment": (
            {"status": "NOT_APPLICABLE_BY_TREATMENT", "valid": True}
            if treatment == "dry"
            else {"status": "MEASURED", "valid": True, "passed": motion_passed}
        ),
        "support_load_authority": {
            "status": "UNSUPPORTED_BY_THIS_PROBE",
            "mass_claim_allowed": False,
        },
    }


def _extended_audit_fixture(centers: list[float], *, pre_roll_steps: int):
    matrices = []
    records = []
    for local_step, center_x in enumerate(centers):
        matrix = np.eye(4, dtype=np.float64)
        matrix[3, 0] = center_x
        matrices.append(matrix)
        reference_step = 0 if local_step <= pre_roll_steps else pre_roll_steps
        reference = matrices[reference_step]
        motion = isaac_fluid.evaluate_preclose_source_motion(
            reference_center_world_m=reference[3, :3],
            reference_source_world_matrix=reference,
            current_center_world_m=matrix[3, :3],
            current_source_world_matrix=matrix,
            vessel_axis_object=[0.0, 1.0, 0.0],
            translation_limit_m=0.002,
            tilt_limit_degrees=1.0,
        )
        records.append(
            {
                "local_step": local_step,
                "motion_reference_local_step": reference_step,
                "translation_m": motion["translation_m"],
                "tilt_degrees": motion["tilt_degrees"],
                "translation_valid": motion["translation_valid"],
                "tilt_valid": motion["tilt_valid"],
                "particle_count": 3600,
                "partition_complete": True,
                "source": 3600,
                "target": 0,
                "transit": 0,
                "tabletop_spill": 0,
                "below_table": 0,
                "nonfinite": 0,
                "position_sha256": "d" * 64,
                "source_pose_sha256": "e" * 64,
                "source_frame_pose_sha256": "e" * 64,
            }
        )
    return (
        records,
        np.asarray(matrices),
        np.asarray([[value, 0.0, 0.0] for value in centers]),
        np.zeros((len(centers), 3), dtype=np.float64),
    )


def test_shared_preclose_metric_preserves_production_boundaries_and_local_y_axis():
    reference = np.eye(4, dtype=np.float64)
    current = _rotation_z(1.0)

    result = isaac_fluid.evaluate_preclose_source_motion(
        reference_center_world_m=[0.0, 0.0, 0.0],
        reference_source_world_matrix=reference,
        current_center_world_m=[0.002 + 1e-12, 0.0, 0.0],
        current_source_world_matrix=current,
        vessel_axis_object=[0.0, 1.0, 0.0],
        translation_limit_m=0.002,
        tilt_limit_degrees=1.0,
    )

    assert result["translation_m"] == pytest.approx(0.002 + 1e-12)
    assert result["tilt_degrees"] == pytest.approx(1.0)
    assert result["translation_valid"] is True
    assert result["tilt_valid"] is True
    assert result["passed"] is True
    np.testing.assert_allclose(result["reference_axis_world"], [0.0, 1.0, 0.0])
    np.testing.assert_allclose(
        result["current_axis_world"], [-np.sin(np.radians(1.0)), np.cos(np.radians(1.0)), 0.0]
    )

    moved = isaac_fluid.evaluate_preclose_source_motion(
        reference_center_world_m=[0.0, 0.0, 0.0],
        reference_source_world_matrix=reference,
        current_center_world_m=[0.002 + 1.1e-12, 0.0, 0.0],
        current_source_world_matrix=current,
        vessel_axis_object=[0.0, 1.0, 0.0],
        translation_limit_m=0.002,
        tilt_limit_degrees=1.0,
    )
    assert moved["translation_valid"] is False
    assert moved["passed"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("reference_center_world_m", [0.0, np.nan, 0.0]),
        ("vessel_axis_object", [0.0, 0.0, 0.0]),
        ("translation_limit_m", True),
        ("tilt_limit_degrees", float("inf")),
    ],
)
def test_shared_preclose_metric_rejects_invalid_authority(field, value):
    kwargs = {
        "reference_center_world_m": [0.0, 0.0, 0.0],
        "reference_source_world_matrix": np.eye(4),
        "current_center_world_m": [0.0, 0.0, 0.0],
        "current_source_world_matrix": np.eye(4),
        "vessel_axis_object": [0.0, 1.0, 0.0],
        "translation_limit_m": 0.002,
        "tilt_limit_degrees": 1.0,
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match="preclose_source_motion_.*_invalid"):
        isaac_fluid.evaluate_preclose_source_motion(**kwargs)


def test_trace_schedule_requires_baseline_120_preroll_and_360_hold_records():
    records = _schedule_records()

    summary = probe.validate_trace_schedule(
        records,
        physics_dt=1 / 120,
        pre_roll_steps=120,
        hold_steps=360,
    )

    assert summary == {
        "record_count": 481,
        "baseline_local_step": 0,
        "hold_reference_local_step": 120,
        "terminal_local_step": 480,
        "first_world_step": 900,
        "last_world_step": 1380,
        "first_world_time_s": 7.5,
        "last_world_time_s": pytest.approx(11.5),
        "physics_dt": pytest.approx(1 / 120),
        "valid": True,
    }

    for mutate in (
        lambda values: values.pop(120),
        lambda values: values[121].update(local_step=120),
        lambda values: values[300].update(world_step=values[299]["world_step"]),
        lambda values: values[400].update(world_time_s=values[399]["world_time_s"]),
    ):
        invalid = _schedule_records()
        mutate(invalid)
        with pytest.raises(ValueError, match="passive_trace_schedule_"):
            probe.validate_trace_schedule(
                invalid,
                physics_dt=1 / 120,
                pre_roll_steps=120,
                hold_steps=360,
            )


def test_trace_schedule_accepts_bounded_pairwise_clock_rounding():
    records = _schedule_records()
    current_time = records[0]["world_time_s"]
    for record in records[1:]:
        current_time += 1 / 120 + 5e-12
        record["world_time_s"] = current_time

    summary = probe.validate_trace_schedule(
        records,
        physics_dt=1 / 120,
        pre_roll_steps=120,
        hold_steps=360,
    )

    assert summary["valid"] is True
    assert summary["last_world_time_s"] == records[-1]["world_time_s"]


def test_filled_summary_latches_transient_containment_and_motion_failures():
    records = _schedule_records()
    for record in records:
        record.update(
            translation_m=0.0,
            tilt_degrees=0.0,
            translation_valid=True,
            tilt_valid=True,
            particle_count=3600,
            partition_complete=True,
            source=3600,
            target=0,
            transit=0,
            tabletop_spill=0,
            below_table=0,
            nonfinite=0,
            position_sha256="d" * 64,
            source_pose_sha256="e" * 64,
            source_frame_pose_sha256="e" * 64,
        )
    records[152].update(source=3599, tabletop_spill=1)
    records[154].update(
        translation_m=0.0020001,
        translation_valid=False,
    )

    result = probe.summarize_filled_trace(records, expected_particle_count=3600)

    assert result["valid"] is True
    assert result["passed"] is False
    assert result["first_containment_failure_local_step"] == 152
    assert result["first_translation_failure_local_step"] == 154
    assert result["first_tilt_failure_local_step"] is None
    assert result["pre_pour_source_min"] == 3599
    assert result["pre_pour_non_source_max"]["tabletop_spill"] == 1
    assert records[-1]["source"] == 3600


def test_filled_summary_rejects_stale_frame_or_invalid_particle_authority():
    records = _schedule_records()
    for record in records:
        record.update(
            translation_m=0.0,
            tilt_degrees=0.0,
            translation_valid=True,
            tilt_valid=True,
            particle_count=3600,
            partition_complete=True,
            source=3600,
            target=0,
            transit=0,
            tabletop_spill=0,
            below_table=0,
            nonfinite=0,
            position_sha256="d" * 64,
            source_pose_sha256="e" * 64,
            source_frame_pose_sha256="e" * 64,
        )
    records[17]["source_frame_pose_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="passive_trace_source_frame_stale"):
        probe.summarize_filled_trace(records, expected_particle_count=3600)

    records[17]["source_frame_pose_sha256"] = "e" * 64
    records[18]["particle_count"] = 3599
    with pytest.raises(ValueError, match="passive_trace_particle_count_invalid"):
        probe.summarize_filled_trace(records, expected_particle_count=3600)


def test_extended_settle_audit_ignores_pre_roll_motion_but_recomputes_hold():
    records, matrices, centers, velocities = _extended_audit_fixture(
        [0.0, 0.003, 0.004, 0.0045, 0.005],
        pre_roll_steps=2,
    )

    result = probe.audit_extended_settle_trace(
        records=records,
        source_world_matrices=matrices,
        source_centers_world_m=centers,
        linear_velocities_m_s=velocities,
        pre_roll_steps=2,
        hold_steps=2,
        vessel_axis_object=[0.0, 1.0, 0.0],
        translation_limit_m=0.002,
        tilt_limit_degrees=1.0,
        expected_particle_count=3600,
        window_steps=1,
    )

    assert result["pre_roll"]["maximum_translation_m"] == pytest.approx(0.004)
    assert result["hold_motion"]["passed"] is True
    assert result["hold_motion"]["record_count"] == 2
    assert result["containment"]["passed"] is True
    assert result["passed"] is True


def test_extended_settle_audit_latches_hold_motion_and_full_trace_containment():
    records, matrices, centers, velocities = _extended_audit_fixture(
        [0.0, 0.001, 0.0015, 0.002, 0.005],
        pre_roll_steps=2,
    )
    records[1].update(source=3599, tabletop_spill=1)

    result = probe.audit_extended_settle_trace(
        records=records,
        source_world_matrices=matrices,
        source_centers_world_m=centers,
        linear_velocities_m_s=velocities,
        pre_roll_steps=2,
        hold_steps=2,
        vessel_axis_object=[0.0, 1.0, 0.0],
        translation_limit_m=0.002,
        tilt_limit_degrees=1.0,
        expected_particle_count=3600,
        window_steps=1,
    )

    assert result["hold_motion"]["passed"] is False
    assert result["hold_motion"]["first_translation_failure_local_step"] == 4
    assert result["containment"]["passed"] is False
    assert result["containment"]["first_failure_local_step"] == 1
    assert result["passed"] is False


def test_treatment_contract_is_explicit_and_allows_only_pre_world_dry_deactivation():
    filled = probe.validate_treatment_contract(
        treatment="filled",
        particle_path=PARTICLE_PATH,
        active_particle_paths=[PARTICLE_PATH],
        mutation_ledger=[],
    )
    assert filled["particle_readback"] == "REQUIRED"

    dry_mutation = {
        "phase": "pre_world",
        "operation": "set_active",
        "path": PARTICLE_PATH,
        "value": False,
    }
    dry = probe.validate_treatment_contract(
        treatment="dry",
        particle_path=PARTICLE_PATH,
        active_particle_paths=[],
        mutation_ledger=[dry_mutation],
    )
    assert dry["particle_readback"] == "NOT_APPLICABLE_BY_TREATMENT"

    with pytest.raises(ValueError, match="passive_treatment_contract_invalid"):
        probe.validate_treatment_contract(
            treatment="filled",
            particle_path=PARTICLE_PATH,
            active_particle_paths=[],
            mutation_ledger=[],
        )
    with pytest.raises(ValueError, match="passive_treatment_contract_invalid"):
        probe.validate_treatment_contract(
            treatment="dry",
            particle_path=PARTICLE_PATH,
            active_particle_paths=[],
            mutation_ledger=[{**dry_mutation, "phase": "runtime"}],
        )


@pytest.mark.parametrize(
    "dry_passed,filled_passed,classification",
    [
        (False, False, "COMMON_BARE_SCENE_INSTABILITY_CANDIDATE"),
        (True, False, "PARTICLE_ASSOCIATED_DIFFERENTIAL_CANDIDATE"),
        (False, True, "INCONCLUSIVE_DRY_ONLY_INSTABILITY"),
        (True, True, "BARE_PASSIVE_FAILURE_NOT_REPRODUCED"),
    ],
)
def test_offline_comparison_has_four_noncausal_branches(
    dry_passed,
    filled_passed,
    classification,
):
    result = probe.compare_treatment_reports(
        _comparable_report("dry", motion_passed=dry_passed),
        _comparable_report("filled", motion_passed=filled_passed),
    )

    assert result["comparable"] is True
    assert result["classification"] == classification
    assert result["causal_claim_allowed"] is False
    assert result["filled_payload_mass_claim_allowed"] is False


def test_offline_comparison_rejects_swapped_or_mismatched_reports():
    dry = _comparable_report("dry", motion_passed=True)
    filled = _comparable_report("filled", motion_passed=False)
    with pytest.raises(ValueError, match="passive_comparison_treatment_order_invalid"):
        probe.compare_treatment_reports(filled, dry)

    filled["comparison_contract"]["physics_dt"] = 1 / 60
    with pytest.raises(ValueError, match="passive_comparison_contract_mismatch"):
        probe.compare_treatment_reports(dry, filled)


def test_create_only_json_publication_is_strict_and_never_replaces(tmp_path):
    output = tmp_path / "report.json"
    probe.atomic_create_json(output, {"finite": 1.0})
    assert json.loads(output.read_text(encoding="utf-8")) == {"finite": 1.0}

    with pytest.raises(FileExistsError, match="passive_probe_output_exists"):
        probe.atomic_create_json(output, {"replacement": True})
    assert json.loads(output.read_text(encoding="utf-8")) == {"finite": 1.0}

    with pytest.raises(ValueError, match="passive_probe_json_nonfinite"):
        probe.atomic_create_json(tmp_path / "nan.json", {"value": np.nan})


def test_parent_finalization_fails_closed_for_timeout_or_bad_child_exit():
    provisional = {
        "schema_version": 1,
        "manifest_type": "contact_grasp_passive_stability_probe_v1",
        "lifecycle_status": "measurement_complete_pending_application_close",
        "shutdown_status": "pending",
        "treatment": "dry",
        "run_nonce": "nonce-1",
        "measurement_decision": "PASSIVE_STABILITY_PASS",
    }

    clean = probe.finalize_child_report(
        provisional,
        expected_treatment="dry",
        expected_run_nonce="nonce-1",
        child_command=["python", "probe.py"],
        child_returncode=0,
        timed_out=False,
        termination=None,
    )
    assert clean["decision"] == "PASSIVE_STABILITY_PASS"
    assert clean["lifecycle_status"] == "completed"

    timed_out = probe.finalize_child_report(
        provisional,
        expected_treatment="dry",
        expected_run_nonce="nonce-1",
        child_command=["python", "probe.py"],
        child_returncode=-9,
        timed_out=True,
        termination="SIGKILL",
    )
    assert timed_out["decision"] == "PROBE_RUNTIME_ERROR"
    assert timed_out["lifecycle_status"] == "failed"
    assert timed_out["child_process"]["timed_out"] is True


def test_robot_independent_dynamic_stage_contract_accepts_exact_production_asset():
    Usd = pytest.importorskip("pxr.Usd")
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    stage = Usd.Stage.Open(str(REPO_ROOT / cfg["usd_path"]))

    result = isaac_fluid.validate_dynamic_source_stage_contract(
        stage,
        cfg["online_fluid"],
        additional_required_paths=("/World/Cube", "/World/table"),
    )

    assert result["source_ownership"] == "contact_friction_dynamic_v1"
    assert result["source_kinematic"] is False
    assert result["source_internal_wrapper_collider_count"] == 145
    assert "/World/Cube" in result["required_prim_paths"]
    assert all("Franka" not in path for path in result["required_prim_paths"])
