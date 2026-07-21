from __future__ import annotations

import copy

import pytest

from utils.controlled_contact import canonical_json_sha256
from utils.real_pbd_grasp_v2 import (
    build_stage_artifact,
    build_stage_evidence,
    evaluate_g0_runtime_capability_audit,
    serialize_stage_artifact,
)


SOURCE = "/World/beaker2"
SHELL = "/World/beaker2/mesh"
WRAPPER = "/World/beaker2/FluidSafeWrapperCanonical/panel_000"


def _sha(character: str) -> str:
    return character * 64


def _profile_policy() -> dict:
    return {
        "authority": "real_pbd_g0_runtime_profile_extension_policy_v1",
        "schema_version": 1,
        "required_extensions": [
            {"name": "omni.physx", "version": "106.0.20"},
        ],
        "forbidden_extension_names": ["omni.physx.fabric"],
    }


def _profile_record(
    *, name: str = "omni.physx", version: str = "106.0.20"
) -> dict:
    return {
        "name": name,
        "id": f"{name}-{version}",
        "version": version,
        "path": f"/formal/isaac41/exts/{name}",
        "manifest_path": f"/formal/isaac41/exts/{name}/config/extension.toml",
        "manifest_sha256": _sha("d"),
    }


def _profile_closure(records: list[dict]) -> dict:
    normalized = sorted(copy.deepcopy(records), key=lambda record: record["id"])
    return {
        "authority": "real_pbd_g0_runtime_extension_closure_v1",
        "schema_version": 1,
        "capture_status": "COMPLETE",
        "records": normalized,
        "closure_sha256": canonical_json_sha256({"records": normalized}),
    }


def _profile_evidence() -> dict:
    policy = _profile_policy()
    before = _profile_closure([_profile_record()])
    after = copy.deepcopy(before)
    return {
        "authority": "real_pbd_g0_runtime_profile_extension_evidence_v1",
        "schema_version": 1,
        "policy": policy,
        "policy_sha256": canonical_json_sha256(policy),
        "before_query": before,
        "after_query": after,
        "query_update_closure_sha256es": [before["closure_sha256"]],
    }


def _snapshot() -> dict:
    collider_paths = [SHELL, WRAPPER]
    return {
        "authority": "real_pbd_g0_runtime_capability_snapshot_v2",
        "schema_version": 2,
        "run_id": "g0-audit-test",
        "parent_nonce_sha256": _sha("a"),
        "audit_spec_sha256": _sha("b"),
        "asset_sha256": _sha("b"),
        "fixture_identity_sha256": _sha("c"),
        "source_actor_path": SOURCE,
        "audit_status": "COMPLETE",
        "input_closure_before_sha256": _sha("d"),
        "input_closure_after_sha256": _sha("d"),
        "source_stage_before_sha256": _sha("e"),
        "source_stage_after_sha256": _sha("e"),
        "particle_stage_before_sha256": _sha("f"),
        "particle_stage_after_sha256": _sha("f"),
        "session_layer_before_sha256": _sha("a"),
        "session_layer_after_sha256": _sha("a"),
        "root_stage_before_sha256": _sha("b"),
        "root_stage_after_sha256": _sha("b"),
        "timeline_checkpoints": {
            "before_query": {"is_playing": False, "time_s": 0.0},
            "after_query": {"is_playing": False, "time_s": 0.0},
        },
        "no_motion_checks": {
            "world_constructed": False,
            "task_constructed": False,
            "controller_constructed": False,
            "robot_constructed": False,
            "world_reset_called": False,
            "world_step_called": False,
            "action_applied": False,
            "source_write_detected": False,
            "particle_write_detected": False,
        },
        "expected_source_collider_paths": collider_paths,
        "cooked_source_query": {
            "status": "COMPLETE",
            "query_mode": "QUERY_RIGID_BODY_WITH_COLLIDERS",
            "rigid_body_owner_path": SOURCE,
            "finished_callback_count": 1,
            "callback_errors": [],
            "colliders": [
                {
                    "path": path,
                    "aabb_local_min_m": [-0.01, -0.01, -0.01],
                    "aabb_local_max_m": [0.01, 0.01, 0.01],
                    "volume_m3": 1.0e-6,
                }
                for path in collider_paths
            ],
            "mass_kg": 0.02,
            "center_of_mass_local_m": [0.0, 0.0, 0.0],
            "diagonal_inertia_kg_m2": [1.0e-5, 1.0e-5, 1.0e-5],
        },
        "authored_offsets": [
            {
                "path": path,
                "contact_offset_m": None,
                "rest_offset_m": None,
                "contact_offset_authored": False,
                "rest_offset_authored": False,
            }
            for path in collider_paths
        ],
        "profile_extension_evidence": _profile_evidence(),
        "capability_status": {
            "robot_table_cooked_geometry": "UNAVAILABLE",
            "physx_effective_offsets": "UNAVAILABLE",
            "signed_swept_clearance": "UNAVAILABLE",
            "stable_particle_ids": "UNAVAILABLE",
            "filled_load_authority": "UNAVAILABLE",
        },
    }


def test_runtime_capability_audit_is_no_go_only_and_stage_sealable():
    snapshot = _snapshot()

    report = evaluate_g0_runtime_capability_audit(snapshot=snapshot)

    assert report["decision"] == "G0_NO_GO"
    assert report["g2_eligible"] is False
    assert report["g3_g4_filled_load_authorized"] is False
    assert "signed_swept_clearance_unavailable" in report["no_go_reasons"]
    assert report["checks"]["source_cooked_query_complete"] is True

    parent_report = {
        **{key: value for key, value in report.items() if key != "sha256"},
        "checks": {
            **report["checks"],
            "child_lifecycle_clean": True,
            "runtime_log_clean": True,
            "runtime_contract_matches": True,
        },
        "child_stdout_sha256": _sha("1"),
        "child_stderr_sha256": _sha("2"),
        "child_runtime_receipt_sha256": _sha("3"),
        "child_execution": {
            "authority": "real_pbd_g0_runtime_audit_child_execution_v1",
            "schema_version": 1,
            "parent_status": "COMPLETE",
            "returncode": 0,
            "stderr_diagnostic": {
                "authority": "real_pbd_g0_runtime_audit_stderr_diagnostic_v2",
                "schema_version": 2,
                "stderr_sha256": _sha("2"),
                "stderr_byte_count": 0,
                "scanner_policy": "ascii_line_severity_and_native_abi_v2",
                "marker_line_counts": {
                    "child_error_protocol": 0,
                    "kit_error": 0,
                    "kit_fatal": 0,
                    "native_abi_warning": 0,
                    "python_traceback": 0,
                },
                "runtime_log_clean": True,
            },
        },
        "runtime_receipt": {
            "authority": "real_pbd_g0_runtime_capability_runtime_receipt_v1",
            "schema_version": 1,
            "parent_nonce_sha256": snapshot["parent_nonce_sha256"],
            "audit_spec_sha256": snapshot["audit_spec_sha256"],
            "runtime_contract": {
                "authority": "real_pbd_g0_runtime_contract_v1",
                "schema_version": 1,
                "executable": "/formal/isaac41/bin/python",
                "prefix": "/formal/isaac41",
                "python_version": "3.10.20",
                "isaacsim_version": "4.1.0.0",
                "numpy_version": "1.26.4",
                "usd_version": "0.22.11",
                "experience_path": "/formal/isaac41/apps/minimal_property_query.kit",
                "experience_sha256": _sha("4"),
            },
            "observed_runtime": {
                "executable": "/formal/isaac41/bin/python",
                "prefix": "/formal/isaac41",
                "python_version": "3.10.20",
                "isaacsim_version": "4.1.0.0",
                "numpy_version": "1.26.4",
                "usd_version": "0.22.11",
                "experience_path": "/formal/isaac41/apps/minimal_property_query.kit",
                "experience_sha256": _sha("4"),
                "module_origins": {
                    "isaacsim": "/formal/isaac41/lib/python3.10/site-packages/isaacsim/__init__.py",
                    "numpy": "/formal/isaac41/lib/python3.10/site-packages/numpy/__init__.py",
                    "pxr_usd": "/formal/isaac41/lib/python3.10/site-packages/pxr/Usd.so",
                    "omni_physx": "/formal/isaac41/lib/python3.10/site-packages/isaacsim/extsPhysics/omni.physx/omni/physx/__init__.py",
                    "physx_bindings": "/formal/isaac41/lib/python3.10/site-packages/isaacsim/extsPhysics/omni.physx/omni/physx/bindings/_physx.so",
                },
            },
            "attestation_status": "MATCH",
        },
        "parent_recomputed": True,
    }
    parent_report["sha256"] = canonical_json_sha256(
        {key: value for key, value in parent_report.items() if key != "sha256"}
    )

    evidence = build_stage_evidence(
        stage="G0",
        decision="G0_NO_GO",
        fixture_identity_sha256=snapshot["fixture_identity_sha256"],
        treatment_sha256=snapshot["audit_spec_sha256"],
        source_evidence=parent_report,
    )
    artifact = build_stage_artifact(
        stage="G0",
        decision="G0_NO_GO",
        run_id=snapshot["run_id"],
        reset_epoch=0,
        fixture_identity_sha256=snapshot["fixture_identity_sha256"],
        treatment_sha256=snapshot["audit_spec_sha256"],
        stage_evidence=evidence,
        input_closure_sha256=snapshot["input_closure_before_sha256"],
        forbidden_frozen_v6_input_count=0,
        predecessor_byte_hashes={},
    )
    assert serialize_stage_artifact(artifact).endswith(b"\n")


def test_runtime_capability_audit_fails_closed_for_drift_or_incomplete_query():
    drifted = _snapshot()
    drifted["timeline_checkpoints"]["after_query"]["time_s"] = 1.0 / 600.0
    report = evaluate_g0_runtime_capability_audit(snapshot=drifted)
    assert report["checks"]["timeline_unchanged"] is False
    assert "timeline_changed_during_query" in report["no_go_reasons"]

    incomplete = _snapshot()
    incomplete["cooked_source_query"]["colliders"] = incomplete[
        "cooked_source_query"
    ]["colliders"][:1]
    report = evaluate_g0_runtime_capability_audit(snapshot=incomplete)
    assert report["checks"]["source_cooked_query_complete"] is False
    assert "source_cooked_collider_inventory_incomplete" in report["no_go_reasons"]


def test_runtime_capability_audit_fails_closed_for_profile_policy_or_closure_drift():
    forbidden = _snapshot()
    evidence = forbidden["profile_extension_evidence"]
    forbidden_records = [_profile_record(), _profile_record(name="omni.physx.fabric")]
    evidence["before_query"] = _profile_closure(forbidden_records)
    evidence["after_query"] = _profile_closure(forbidden_records)
    evidence["query_update_closure_sha256es"] = [
        evidence["before_query"]["closure_sha256"]
    ]
    report = evaluate_g0_runtime_capability_audit(snapshot=forbidden)
    assert report["checks"]["profile_extension_policy_satisfied"] is False
    assert "profile_extension_policy_unsatisfied" in report["no_go_reasons"]

    drifted = _snapshot()
    drifted_evidence = drifted["profile_extension_evidence"]
    drifted_evidence["after_query"] = _profile_closure(
        [_profile_record(version="106.0.21")]
    )
    drifted_evidence["query_update_closure_sha256es"] = [
        drifted_evidence["before_query"]["closure_sha256"],
        drifted_evidence["after_query"]["closure_sha256"],
    ]
    report = evaluate_g0_runtime_capability_audit(snapshot=drifted)
    assert report["checks"]["profile_extension_closure_unchanged"] is False
    assert "profile_extension_closure_changed" in report["no_go_reasons"]


def test_runtime_capability_audit_rejects_forged_go_and_noncanonical_statuses():
    forged = _snapshot()
    forged["decision"] = "G0_GO"
    with pytest.raises(ValueError, match="real_pbd_g0_runtime_capability_snapshot_fields_invalid"):
        evaluate_g0_runtime_capability_audit(snapshot=forged)

    invalid = _snapshot()
    invalid["capability_status"]["signed_swept_clearance"] = "GO"
    with pytest.raises(ValueError, match="real_pbd_g0_runtime_capability_status_invalid"):
        evaluate_g0_runtime_capability_audit(snapshot=invalid)


def test_runtime_capability_audit_rejects_duplicate_or_nonfinite_cooked_records():
    duplicate = _snapshot()
    duplicate["cooked_source_query"]["colliders"].append(
        copy.deepcopy(duplicate["cooked_source_query"]["colliders"][0])
    )
    report = evaluate_g0_runtime_capability_audit(snapshot=duplicate)
    assert report["checks"]["source_cooked_query_complete"] is False

    nonfinite = _snapshot()
    nonfinite["cooked_source_query"]["colliders"][0]["volume_m3"] = float("nan")
    with pytest.raises(ValueError, match="real_pbd_g0_runtime_capability_cooked_.*_invalid"):
        evaluate_g0_runtime_capability_audit(snapshot=nonfinite)


def test_runtime_capability_failure_never_claims_unchanged_or_no_motion():
    failed = _snapshot()
    failed["audit_status"] = "CHILD_FAILURE"
    failed["input_closure_after_sha256"] = _sha("1")
    failed["source_stage_after_sha256"] = _sha("1")
    failed["particle_stage_after_sha256"] = _sha("1")
    failed["session_layer_after_sha256"] = _sha("1")
    failed["root_stage_after_sha256"] = _sha("1")
    failed["timeline_checkpoints"]["after_query"] = {
        "is_playing": True,
        "time_s": 1.0,
    }
    failed["no_motion_checks"]["source_write_detected"] = True
    failed["cooked_source_query"] = {
        "status": "FAILED",
        "query_mode": "QUERY_RIGID_BODY_WITH_COLLIDERS",
        "rigid_body_owner_path": SOURCE,
        "finished_callback_count": 0,
        "callback_errors": ["child_failure"],
        "colliders": [],
        "mass_kg": None,
        "center_of_mass_local_m": None,
        "diagonal_inertia_kg_m2": None,
    }
    failed["authored_offsets"] = []

    report = evaluate_g0_runtime_capability_audit(snapshot=failed)

    assert report["checks"]["audit_completed"] is False
    assert report["checks"]["no_motion"] is False
    assert report["checks"]["input_closure_unchanged"] is False
    assert report["checks"]["source_stage_unchanged"] is False
    assert report["checks"]["particle_stage_unchanged"] is False
    assert "audit_status_child_failure" in report["no_go_reasons"]
