"""Pure contract for a cube-only versus finite-offset-package contact contrast.

The comparison is diagnostic only. It can describe differing contact behavior
between two whole-fixture treatments, never native offsets, clearance, G0, or
Phase 3 readiness.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any


PLAN_AUTHORITY = "nonauthorizing_authored_offset_behavior_contrast_plan_v1"
OBSERVATION_AUTHORITY = "nonauthorizing_authored_offset_behavior_contrast_observation_v1"
EVALUATION_AUTHORITY = "nonauthorizing_authored_offset_behavior_contrast_evaluation_v1"
CLASSIFICATION = "NONAUTHORIZING_AUTHORED_OFFSET_BEHAVIOR_CONTRAST"
OBSERVED = "FINITE_TARGET_OFFSET_PACKAGE_BEHAVIOR_CONTRAST_OBSERVED_DIAGNOSTIC_ONLY"
INCONCLUSIVE = "FINITE_TARGET_OFFSET_PACKAGE_BEHAVIOR_CONTRAST_INCONCLUSIVE"
NO_GO = "FINITE_TARGET_OFFSET_PACKAGE_BEHAVIOR_CONTRAST_NO_GO"
RUNTIME_BLOCKED = "RUNTIME_BLOCKED"
AUTHORIZATION = {
    "effective_offsets_resolved": False,
    "clearance_certificate_authorized": False,
    "g0_go_authorized": False,
    "phase3_authorized": False,
}
_CELLS = (
    {"id": "cube_only_baseline", "profile_id": "cube_only_baseline_v1"},
    {
        "id": "cube_plus_finite_target_offsets",
        "profile_id": "finite_target_offsets_calibration_v2",
    },
)
_BEHAVIORAL_DECISIONS = {"OBSERVED", "PHYSICAL_FAIL"}
_CELL_DECISIONS = _BEHAVIORAL_DECISIONS | {"AUDIT_NO_GO", RUNTIME_BLOCKED}


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite_positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result > 0.0 else None


def _common(value: Any) -> dict[str, Any]:
    expected = {
        "config_closure_sha256",
        "asset_sha256",
        "robot_asset_sha256",
        "source_identity_sha256",
        "cube_only_profile_sha256",
        "finite_profile_sha256",
        "fixture_usd_dependency_closure_sha256",
        "cube_only_resolved_usd_dependency_closure_sha256",
        "finite_resolved_usd_dependency_closure_sha256",
        "fixture_usd_dependency_preflight_sha256",
        "seed",
        "max_control_steps",
        "physics_dt_s",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("authored_offset_behavior_common_invalid")
    common = dict(value)
    if (
        any(
            not _is_sha256(common[name])
            for name in (
                "config_closure_sha256",
                "asset_sha256",
                "robot_asset_sha256",
                "source_identity_sha256",
                "cube_only_profile_sha256",
                "finite_profile_sha256",
                "fixture_usd_dependency_closure_sha256",
                "cube_only_resolved_usd_dependency_closure_sha256",
                "finite_resolved_usd_dependency_closure_sha256",
                "fixture_usd_dependency_preflight_sha256",
            )
        )
        or type(common["seed"]) is not int
        or common["seed"] < 0
        or type(common["max_control_steps"]) is not int
        or common["max_control_steps"] <= 0
        or _finite_positive(common["physics_dt_s"]) is None
    ):
        raise ValueError("authored_offset_behavior_common_invalid")
    return {
        "config_closure_sha256": common["config_closure_sha256"],
        "asset_sha256": common["asset_sha256"],
        "robot_asset_sha256": common["robot_asset_sha256"],
        "source_identity_sha256": common["source_identity_sha256"],
        "cube_only_profile_sha256": common["cube_only_profile_sha256"],
        "finite_profile_sha256": common["finite_profile_sha256"],
        "fixture_usd_dependency_closure_sha256": common[
            "fixture_usd_dependency_closure_sha256"
        ],
        "cube_only_resolved_usd_dependency_closure_sha256": common[
            "cube_only_resolved_usd_dependency_closure_sha256"
        ],
        "finite_resolved_usd_dependency_closure_sha256": common[
            "finite_resolved_usd_dependency_closure_sha256"
        ],
        "fixture_usd_dependency_preflight_sha256": common[
            "fixture_usd_dependency_preflight_sha256"
        ],
        "seed": common["seed"],
        "max_control_steps": common["max_control_steps"],
        "physics_dt_s": float(common["physics_dt_s"]),
    }


def build_plan(common: Mapping[str, Any]) -> dict[str, Any]:
    normalized_common = _common(common)
    payload = {
        "authority": PLAN_AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "common": normalized_common,
        "cells": [dict(cell) for cell in _CELLS],
        "treatment_estimand": "cube_only_vs_finite_target_offset_package",
        "scope": {
            "fresh_sealed_child_per_cell": True,
            "close_only": True,
            "lift_allowed": False,
            "source_control_allowed": False,
            "native_offset_readback_claimed": False,
            "clearance_or_gate_claimed": False,
        },
        "authorization": dict(AUTHORIZATION),
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}


def validate_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("authored_offset_behavior_plan_invalid")
    plan = copy.deepcopy(dict(value))
    digest = plan.pop("sha256", None)
    try:
        expected = build_plan(plan["common"])
    except (KeyError, ValueError) as exc:
        raise ValueError("authored_offset_behavior_plan_invalid") from exc
    if (
        not _is_sha256(digest)
        or canonical_json_sha256(plan) != digest
        or plan != {key: item for key, item in expected.items() if key != "sha256"}
    ):
        raise ValueError("authored_offset_behavior_plan_invalid")
    return expected


def _validated_observation(value: Any, plan: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "authority",
        "schema_version",
        "classification",
        "plan_sha256",
        "authorization",
        "cells",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("authored_offset_behavior_observation_invalid")
    observation = copy.deepcopy(dict(value))
    digest = observation.pop("sha256")
    if (
        observation.get("authority") != OBSERVATION_AUTHORITY
        or observation.get("schema_version") != 1
        or observation.get("classification") != CLASSIFICATION
        or observation.get("plan_sha256") != plan["sha256"]
        or not _is_sha256(digest)
        or canonical_json_sha256(observation) != digest
        or not isinstance(observation.get("cells"), list)
    ):
        raise ValueError("authored_offset_behavior_observation_invalid")
    return {**observation, "sha256": digest}


def _cell_checks(value: Any, *, expected: Mapping[str, Any], common: Mapping[str, Any]) -> dict[str, Any]:
    expected_fields = {
        "id",
        "profile_id",
        "profile_sha256",
        "decision",
        "runtime_receipt_matched",
        "config_closure_sha256",
        "asset_sha256",
        "robot_asset_sha256",
        "source_identity_sha256",
        "seed",
        "max_control_steps",
        "physics_dt_s",
        "direct_report_trace",
        "report_layer",
        "treatment_audit",
        "source_writer_audit",
        "source_writer_audit_scope",
        "lift_action_applied",
        "metrics",
    }
    invalid = {
        "schema_valid": False,
        "identity_valid": False,
        "common_binding_valid": False,
        "runtime_matched": False,
        "trace_valid": False,
        "report_layer_stable": False,
        "treatment_audit_valid": False,
        "source_writer_clean": False,
        "no_lift": False,
        "metrics_valid": False,
        "decision": None,
        "metrics": None,
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        return invalid
    decision = value.get("decision")
    schema_valid = (
        _is_sha256(value.get("profile_sha256"))
        and decision in _CELL_DECISIONS
        and type(value.get("runtime_receipt_matched")) is bool
        and type(value.get("lift_action_applied")) is bool
    )
    expected_profile_sha256 = common[
        "cube_only_profile_sha256"
        if expected["id"] == "cube_only_baseline"
        else "finite_profile_sha256"
    ]
    identity_valid = (
        value.get("id") == expected["id"]
        and value.get("profile_id") == expected["profile_id"]
        and value.get("profile_sha256") == expected_profile_sha256
    )
    common_binding_valid = all(
        value.get(name) == common[name]
        for name in (
            "config_closure_sha256",
            "asset_sha256",
            "robot_asset_sha256",
            "source_identity_sha256",
            "seed",
            "max_control_steps",
        )
    ) and _finite_positive(value.get("physics_dt_s")) is not None and math.isclose(
        float(value["physics_dt_s"]), float(common["physics_dt_s"]), rel_tol=0.0, abs_tol=1.0e-15
    )
    trace = value.get("direct_report_trace")
    trace_valid = (
        isinstance(trace, Mapping)
        and set(trace) == {
            "complete",
            "record_count",
            "uncompressed_sha256",
            "compressed_sha256",
        }
        and trace.get("complete") is True
        and type(trace.get("record_count")) is int
        and trace["record_count"] > 0
        and _is_sha256(trace.get("uncompressed_sha256"))
        and _is_sha256(trace.get("compressed_sha256"))
    )
    report_layer = value.get("report_layer")
    report_layer_stable = (
        isinstance(report_layer, Mapping)
        and set(report_layer) == {"after_reset_sha256", "after_run_sha256", "unchanged"}
        and _is_sha256(report_layer.get("after_reset_sha256"))
        and report_layer.get("after_reset_sha256") == report_layer.get("after_run_sha256")
        and report_layer.get("unchanged") is True
    )
    treatment = value.get("treatment_audit")
    treatment_audit_valid = (
        isinstance(treatment, Mapping)
        and set(treatment)
        == {
            "cube_collision_disabled",
            "offset_snapshot_after_reset_sha256",
            "offset_snapshot_after_run_sha256",
            "offset_snapshot_unchanged",
            "usd_dependency_closure_after_reset_sha256",
            "usd_dependency_closure_after_run_sha256",
            "usd_dependency_closure_unchanged",
            "common_usd_dependency_closure_after_reset_sha256",
            "common_usd_dependency_closure_matches_preflight",
            "resolved_usd_dependency_closure_sha256",
            "resolved_usd_dependency_closure_unchanged",
            "resolved_usd_dependency_closure_matches_preflight",
            "profile_authoring_valid",
        }
        and treatment.get("cube_collision_disabled") is True
        and all(
            _is_sha256(treatment.get(name))
            for name in (
                "offset_snapshot_after_reset_sha256",
                "offset_snapshot_after_run_sha256",
                "usd_dependency_closure_after_reset_sha256",
                "usd_dependency_closure_after_run_sha256",
                "common_usd_dependency_closure_after_reset_sha256",
                "resolved_usd_dependency_closure_sha256",
            )
        )
        and treatment.get("offset_snapshot_after_reset_sha256")
        == treatment.get("offset_snapshot_after_run_sha256")
        and treatment.get("usd_dependency_closure_after_reset_sha256")
        == treatment.get("usd_dependency_closure_after_run_sha256")
        and treatment.get("offset_snapshot_unchanged") is True
        and treatment.get("usd_dependency_closure_unchanged") is True
        and treatment.get("common_usd_dependency_closure_matches_preflight") is True
        and treatment.get("resolved_usd_dependency_closure_unchanged") is True
        and treatment.get("resolved_usd_dependency_closure_matches_preflight") is True
        and treatment.get("profile_authoring_valid") is True
        and treatment.get("common_usd_dependency_closure_after_reset_sha256")
        == common["fixture_usd_dependency_closure_sha256"]
        and treatment.get("resolved_usd_dependency_closure_sha256")
        == common[
            "cube_only_resolved_usd_dependency_closure_sha256"
            if expected["id"] == "cube_only_baseline"
            else "finite_resolved_usd_dependency_closure_sha256"
        ]
    )
    writer = value.get("source_writer_audit")
    writer_fields = {
        "valid",
        "coverage_complete",
        "source_pose_write_count_after_play",
        "source_velocity_write_count_after_play",
        "object_utils_source_position_write_count_after_play",
        "kinematic_target_update_count",
    }
    source_writer_clean = (
        isinstance(writer, Mapping)
        and set(writer) == writer_fields
        and writer.get("valid") is True
        and writer.get("coverage_complete") is True
        and all(type(writer.get(name)) is int and writer[name] == 0 for name in writer_fields - {"valid", "coverage_complete"})
        and value.get("source_writer_audit_scope") == "instrumented_known_surfaces_only"
    )
    metrics = value.get("metrics")
    first = metrics.get("first_bilateral_current_physics_index") if isinstance(metrics, Mapping) else None
    sample_count = metrics.get("bilateral_current_sample_count") if isinstance(metrics, Mapping) else None
    longest = metrics.get("longest_bilateral_current_window") if isinstance(metrics, Mapping) else None
    metrics_valid = (
        isinstance(metrics, Mapping)
        and set(metrics)
        == {
            "first_bilateral_current_physics_index",
            "bilateral_current_sample_count",
            "longest_bilateral_current_window",
        }
        and (first is None or (type(first) is int and first >= 0))
        and type(sample_count) is int
        and sample_count >= 0
        and type(longest) is int
        and 0 <= longest <= sample_count
        and ((sample_count == 0) == (first is None))
    )
    return {
        "schema_valid": schema_valid,
        "identity_valid": identity_valid,
        "common_binding_valid": common_binding_valid,
        "runtime_matched": value.get("runtime_receipt_matched") is True,
        "trace_valid": trace_valid,
        "report_layer_stable": report_layer_stable,
        "treatment_audit_valid": treatment_audit_valid,
        "source_writer_clean": source_writer_clean,
        "no_lift": value.get("lift_action_applied") is False,
        "metrics_valid": metrics_valid,
        "common_usd_dependency_closure_after_reset_sha256": (
            treatment.get("common_usd_dependency_closure_after_reset_sha256")
            if treatment_audit_valid
            else None
        ),
        "decision": decision,
        "metrics": dict(metrics) if metrics_valid else None,
    }


def evaluate_observation(value: Any, *, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate only paired diagnostic integrity and treatment-level behavior."""
    expected_plan = validate_plan(plan)
    observation = _validated_observation(value, expected_plan)
    expected_cells = {cell["id"]: cell for cell in expected_plan["cells"]}
    records: dict[str, dict[str, Any]] = {}
    duplicate_or_unknown = False
    for cell in observation["cells"]:
        identifier = cell.get("id") if isinstance(cell, Mapping) else None
        if not isinstance(identifier, str) or identifier in records or identifier not in expected_cells:
            duplicate_or_unknown = True
            continue
        records[identifier] = _cell_checks(
            cell,
            expected=expected_cells[identifier],
            common=expected_plan["common"],
        )
    cell_set_complete = not duplicate_or_unknown and set(records) == set(expected_cells)
    cell_checks = list(records.values())
    runtime_blocked = any(record["decision"] == RUNTIME_BLOCKED for record in cell_checks)
    common_closure_hashes = {
        record["common_usd_dependency_closure_after_reset_sha256"] for record in cell_checks
    }
    checks = {
        "nonauthorizing_scope": observation.get("authorization") == AUTHORIZATION,
        "expected_two_cells_present": cell_set_complete,
        "cell_schemas_valid": cell_set_complete and all(record["schema_valid"] for record in cell_checks),
        "cell_profiles_bound": cell_set_complete and all(record["identity_valid"] for record in cell_checks),
        "common_inputs_bound": cell_set_complete and all(record["common_binding_valid"] for record in cell_checks),
        "runtime_receipts_matched": cell_set_complete and all(record["runtime_matched"] for record in cell_checks),
        "full_report_traces_complete": cell_set_complete and all(record["trace_valid"] for record in cell_checks),
        "report_layers_unchanged_post_reset": cell_set_complete and all(record["report_layer_stable"] for record in cell_checks),
        "treatment_audits_valid": cell_set_complete and all(record["treatment_audit_valid"] for record in cell_checks),
        "common_usd_dependency_closures_identical_across_cells": cell_set_complete
        and all(record["treatment_audit_valid"] for record in cell_checks)
        and len(common_closure_hashes) == 1,
        "source_write_audits_clean": cell_set_complete and all(record["source_writer_clean"] for record in cell_checks),
        "no_lift_action_applied": cell_set_complete and all(record["no_lift"] for record in cell_checks),
        "contact_metrics_valid": cell_set_complete and all(record["metrics_valid"] for record in cell_checks),
        "behavioral_outcomes_admissible": cell_set_complete
        and all(record["decision"] in _BEHAVIORAL_DECISIONS for record in cell_checks),
    }
    core_checks = {
        name: passed
        for name, passed in checks.items()
        if name != "behavioral_outcomes_admissible"
    }
    behavior_difference = False
    if cell_set_complete and all(record["metrics_valid"] for record in cell_checks):
        control = records["cube_only_baseline"]
        finite = records["cube_plus_finite_target_offsets"]
        behavior_difference = (
            control["decision"], control["metrics"]
        ) != (finite["decision"], finite["metrics"])
    if runtime_blocked:
        decision = RUNTIME_BLOCKED
    elif not all(core_checks.values()) or not checks["behavioral_outcomes_admissible"]:
        decision = NO_GO
    elif behavior_difference:
        decision = OBSERVED
    else:
        decision = INCONCLUSIVE
    payload = {
        "authority": EVALUATION_AUTHORITY,
        "classification": CLASSIFICATION,
        "decision": decision,
        "checks": checks,
        "behavior_difference_observed": behavior_difference if decision in {OBSERVED, INCONCLUSIVE} else False,
        "authorization": dict(AUTHORIZATION),
        "plan_sha256": expected_plan["sha256"],
        "observation_sha256": observation["sha256"],
    }
    return {**payload, "sha256": canonical_json_sha256(payload)}
