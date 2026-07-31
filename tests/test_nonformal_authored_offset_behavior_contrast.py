from __future__ import annotations

import copy

from utils import nonformal_authored_offset_behavior_contrast as contrast


def _common() -> dict:
    return {
        "config_closure_sha256": "a" * 64,
        "asset_sha256": "b" * 64,
        "robot_asset_sha256": "c" * 64,
        "source_identity_sha256": "d" * 64,
        "cube_only_profile_sha256": "e" * 64,
        "finite_profile_sha256": "f" * 64,
        "fixture_usd_dependency_closure_sha256": "a" * 64,
        "cube_only_resolved_usd_dependency_closure_sha256": "b" * 64,
        "finite_resolved_usd_dependency_closure_sha256": "b" * 64,
        "fixture_usd_dependency_preflight_sha256": "b" * 64,
        "seed": 20260730,
        "max_control_steps": 600,
        "physics_dt_s": 1.0 / 600.0,
    }


def _cell(plan: dict, *, identifier: str, profile_id: str, offset: int = 0) -> dict:
    return {
        "id": identifier,
        "profile_id": profile_id,
        "profile_sha256": (
            plan["common"]["cube_only_profile_sha256"]
            if identifier == "cube_only_baseline"
            else plan["common"]["finite_profile_sha256"]
        ),
        "decision": "OBSERVED",
        "runtime_receipt_matched": True,
        "config_closure_sha256": plan["common"]["config_closure_sha256"],
        "asset_sha256": plan["common"]["asset_sha256"],
        "robot_asset_sha256": plan["common"]["robot_asset_sha256"],
        "source_identity_sha256": plan["common"]["source_identity_sha256"],
        "seed": plan["common"]["seed"],
        "max_control_steps": plan["common"]["max_control_steps"],
        "physics_dt_s": plan["common"]["physics_dt_s"],
        "direct_report_trace": {
            "complete": True,
            "record_count": 10,
            "uncompressed_sha256": "1" * 64,
            "compressed_sha256": "2" * 64,
        },
        "report_layer": {
            "after_reset_sha256": "3" * 64,
            "after_run_sha256": "3" * 64,
            "unchanged": True,
        },
        "treatment_audit": {
            "cube_collision_disabled": True,
            "offset_snapshot_after_reset_sha256": "4" * 64,
            "offset_snapshot_after_run_sha256": "4" * 64,
            "offset_snapshot_unchanged": True,
            "usd_dependency_closure_after_reset_sha256": "5" * 64,
            "usd_dependency_closure_after_run_sha256": "5" * 64,
            "usd_dependency_closure_unchanged": True,
            "common_usd_dependency_closure_after_reset_sha256": "a" * 64,
            "common_usd_dependency_closure_matches_preflight": True,
            "resolved_usd_dependency_closure_sha256": "b" * 64,
            "resolved_usd_dependency_closure_unchanged": True,
            "resolved_usd_dependency_closure_matches_preflight": True,
            "profile_authoring_valid": True,
        },
        "source_writer_audit": {
            "valid": True,
            "coverage_complete": True,
            "source_pose_write_count_after_play": 0,
            "source_velocity_write_count_after_play": 0,
            "object_utils_source_position_write_count_after_play": 0,
            "kinematic_target_update_count": 0,
        },
        "source_writer_audit_scope": "instrumented_known_surfaces_only",
        "lift_action_applied": False,
        "metrics": {
            "first_bilateral_current_physics_index": 5 + offset,
            "bilateral_current_sample_count": 3 + offset,
            "longest_bilateral_current_window": 2 + offset,
        },
    }


def _observation(plan: dict, *, changed: bool = True) -> dict:
    control = _cell(
        plan,
        identifier="cube_only_baseline",
        profile_id="cube_only_baseline_v1",
    )
    finite = _cell(
        plan,
        identifier="cube_plus_finite_target_offsets",
        profile_id="finite_target_offsets_calibration_v2",
        offset=1 if changed else 0,
    )
    payload = {
        "authority": contrast.OBSERVATION_AUTHORITY,
        "schema_version": 1,
        "classification": contrast.CLASSIFICATION,
        "plan_sha256": plan["sha256"],
        "authorization": dict(contrast.AUTHORIZATION),
        "cells": [control, finite],
    }
    return {**payload, "sha256": contrast.canonical_json_sha256(payload)}


def _rehash(observation: dict) -> dict:
    payload = {key: value for key, value in observation.items() if key != "sha256"}
    observation["sha256"] = contrast.canonical_json_sha256(payload)
    return observation


def test_plan_pins_cube_only_against_the_full_finite_offset_package():
    plan = contrast.build_plan(_common())

    assert plan["cells"] == [
        {"id": "cube_only_baseline", "profile_id": "cube_only_baseline_v1"},
        {
            "id": "cube_plus_finite_target_offsets",
            "profile_id": "finite_target_offsets_calibration_v2",
        },
    ]
    assert plan["treatment_estimand"] == "cube_only_vs_finite_target_offset_package"
    assert plan["authorization"] == contrast.AUTHORIZATION
    assert contrast.validate_plan(plan) == plan


def test_behavior_contrast_reports_a_treatment_level_difference_without_authority_upgrade():
    plan = contrast.build_plan(_common())
    observation = _observation(plan, changed=True)

    evaluation = contrast.evaluate_observation(observation, plan=plan)

    assert evaluation["decision"] == contrast.OBSERVED
    assert evaluation["behavior_difference_observed"] is True
    assert evaluation["authorization"] == contrast.AUTHORIZATION
    assert "effective_offsets_m" not in evaluation


def test_identical_contact_summaries_are_inconclusive_not_equivalent():
    plan = contrast.build_plan(_common())
    observation = _observation(plan, changed=False)

    evaluation = contrast.evaluate_observation(observation, plan=plan)

    assert evaluation["decision"] == contrast.INCONCLUSIVE
    assert evaluation["behavior_difference_observed"] is False


def test_behavior_contrast_fails_closed_for_audit_or_authorization_drift():
    plan = contrast.build_plan(_common())
    observation = _observation(plan)
    observation["cells"][0]["source_writer_audit"]["source_pose_write_count_after_play"] = 1
    observation["authorization"]["g0_go_authorized"] = True
    _rehash(observation)

    evaluation = contrast.evaluate_observation(observation, plan=plan)

    assert evaluation["decision"] == contrast.NO_GO
    assert evaluation["checks"]["nonauthorizing_scope"] is False
    assert evaluation["checks"]["source_write_audits_clean"] is False


def test_behavior_contrast_propagates_runtime_blocked_without_relabeling_it():
    plan = contrast.build_plan(_common())
    observation = _observation(plan)
    observation["cells"][1]["decision"] = contrast.RUNTIME_BLOCKED
    _rehash(observation)

    evaluation = contrast.evaluate_observation(observation, plan=plan)

    assert evaluation["decision"] == contrast.RUNTIME_BLOCKED


def test_behavior_contrast_fails_closed_when_composed_common_usd_closures_differ():
    plan = contrast.build_plan(_common())
    observation = _observation(plan)
    observation["cells"][1]["treatment_audit"][
        "common_usd_dependency_closure_after_reset_sha256"
    ] = "7" * 64
    _rehash(observation)

    evaluation = contrast.evaluate_observation(observation, plan=plan)

    assert evaluation["decision"] == contrast.NO_GO
    assert evaluation["checks"]["common_usd_dependency_closures_identical_across_cells"] is False
