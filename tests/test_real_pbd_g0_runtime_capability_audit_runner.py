from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from tools.labutopia_fluid import run_real_pbd_grasp_v2_runtime_capability_audit as audit
from utils.real_pbd_grasp_v2 import build_stage_evidence


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


def _profile_record() -> dict:
    return {
        "name": "omni.physx",
        "id": "omni.physx-106.0.20",
        "version": "106.0.20",
        "path": "/formal/isaac41/exts/omni.physx",
        "manifest_path": "/formal/isaac41/exts/omni.physx/config/extension.toml",
        "manifest_sha256": _sha("d"),
    }


def _profile_closure(records: list[dict]) -> dict:
    normalized = sorted(copy.deepcopy(records), key=lambda record: record["id"])
    return {
        "authority": "real_pbd_g0_runtime_extension_closure_v1",
        "schema_version": 1,
        "capture_status": "COMPLETE",
        "records": normalized,
        "closure_sha256": audit.canonical_json_sha256({"records": normalized}),
    }


def _profile_evidence() -> dict:
    policy = _profile_policy()
    before = _profile_closure([_profile_record()])
    return {
        "authority": "real_pbd_g0_runtime_profile_extension_evidence_v1",
        "schema_version": 1,
        "policy": policy,
        "policy_sha256": audit.canonical_json_sha256(policy),
        "before_query": before,
        "after_query": copy.deepcopy(before),
        "query_update_closure_sha256es": [before["closure_sha256"]],
    }


def _spec() -> dict:
    return {
        "authority": "real_pbd_g0_runtime_capability_audit_spec_v3",
        "schema_version": 3,
        "asset_path": "/tmp/fixture.usda",
        "asset_sha256": _sha("a"),
        "source_actor_path": "/World/beaker2",
        "particle_path": "/World/InternDataParityFluid/Particles",
        "wrapper_path": "/World/beaker2/FluidSafeWrapperCanonical",
        "query_mode": "QUERY_RIGID_BODY_WITH_COLLIDERS",
        "no_action_policy": "audited_read_only_no_world_v1",
        "profile_extension_policy": _profile_policy(),
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
            "experience_sha256": _sha("d"),
        },
    }


def _snapshot(spec: dict, nonce: str = _sha("c")) -> dict:
    paths = [
        "/World/beaker2/FluidSafeWrapperCanonical/panel_000",
        "/World/beaker2/mesh",
    ]
    return {
        "authority": "real_pbd_g0_runtime_capability_snapshot_v2",
        "schema_version": 2,
        "run_id": "child-run",
        "parent_nonce_sha256": nonce,
        "audit_spec_sha256": audit.canonical_json_sha256(spec),
        "asset_sha256": spec["asset_sha256"],
        "fixture_identity_sha256": _sha("b"),
        "source_actor_path": spec["source_actor_path"],
        "audit_status": "COMPLETE",
        "input_closure_before_sha256": _sha("b"),
        "input_closure_after_sha256": _sha("b"),
        "source_stage_before_sha256": _sha("d"),
        "source_stage_after_sha256": _sha("d"),
        "particle_stage_before_sha256": _sha("e"),
        "particle_stage_after_sha256": _sha("e"),
        "session_layer_before_sha256": _sha("f"),
        "session_layer_after_sha256": _sha("f"),
        "root_stage_before_sha256": _sha("a"),
        "root_stage_after_sha256": _sha("a"),
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
        "expected_source_collider_paths": paths,
        "cooked_source_query": {
            "status": "COMPLETE",
            "query_mode": spec["query_mode"],
            "rigid_body_owner_path": spec["source_actor_path"],
            "finished_callback_count": 1,
            "callback_errors": [],
            "colliders": [
                {
                    "path": path,
                    "aabb_local_min_m": [-0.01, -0.01, -0.01],
                    "aabb_local_max_m": [0.01, 0.01, 0.01],
                    "volume_m3": 1.0e-6,
                }
                for path in paths
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
            for path in paths
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


def _runtime_receipt(spec: dict, nonce: str = _sha("c")) -> dict:
    contract = spec["runtime_contract"]
    prefix = contract["prefix"]
    return {
        "authority": "real_pbd_g0_runtime_capability_runtime_receipt_v1",
        "schema_version": 1,
        "parent_nonce_sha256": nonce,
        "audit_spec_sha256": audit.canonical_json_sha256(spec),
        "runtime_contract": copy.deepcopy(contract),
        "observed_runtime": {
            "executable": contract["executable"],
            "prefix": prefix,
            "python_version": contract["python_version"],
            "isaacsim_version": contract["isaacsim_version"],
            "numpy_version": contract["numpy_version"],
            "usd_version": contract["usd_version"],
            "experience_path": contract["experience_path"],
            "experience_sha256": contract["experience_sha256"],
            "module_origins": {
                "isaacsim": f"{prefix}/lib/python3.10/site-packages/isaacsim/__init__.py",
                "numpy": f"{prefix}/lib/python3.10/site-packages/numpy/__init__.py",
                "pxr_usd": f"{prefix}/lib/python3.10/site-packages/pxr/Usd.so",
                "omni_physx": f"{prefix}/lib/python3.10/site-packages/isaacsim/extsPhysics/omni.physx/omni/physx/__init__.py",
                "physx_bindings": f"{prefix}/lib/python3.10/site-packages/isaacsim/extsPhysics/omni.physx/omni/physx/bindings/_physx.so",
            },
        },
        "attestation_status": "MATCH",
    }


def test_finalize_child_snapshot_binds_spec_nonce_and_no_go_only():
    spec = _spec()
    snapshot = _snapshot(spec)

    report = audit.finalize_child_snapshot(
        snapshot=snapshot,
        audit_spec=spec,
        parent_nonce_sha256=_sha("c"),
        child_stdout=b"child stdout\n",
        child_stderr=b"2026-07-21 [Warning] [omni.example] benign startup noise\n",
        child_execution_status="COMPLETE",
        child_returncode=0,
        runtime_receipt=_runtime_receipt(spec),
    )

    assert report["decision"] == "G0_NO_GO"
    assert report["g2_eligible"] is False
    assert report["audit_spec_sha256"] == audit.canonical_json_sha256(spec)
    assert report["checks"]["runtime_log_clean"] is True
    assert report["checks"]["runtime_contract_matches"] is True
    assert report["runtime_receipt"]["attestation_status"] == "MATCH"
    assert "child_runtime_errors_observed" not in report["no_go_reasons"]

    stale = copy.deepcopy(snapshot)
    stale["parent_nonce_sha256"] = _sha("d")
    with pytest.raises(ValueError, match="real_pbd_g0_runtime_audit_nonce_invalid"):
        audit.finalize_child_snapshot(
            snapshot=stale,
            audit_spec=spec,
            parent_nonce_sha256=_sha("c"),
            child_stdout=b"",
            child_stderr=b"",
            child_execution_status="COMPLETE",
            child_returncode=0,
            runtime_receipt=_runtime_receipt(spec),
        )

    swapped_asset = copy.deepcopy(snapshot)
    swapped_asset["asset_sha256"] = _sha("d")
    with pytest.raises(ValueError, match="real_pbd_g0_runtime_audit_spec_binding_invalid"):
        audit.finalize_child_snapshot(
            snapshot=swapped_asset,
            audit_spec=spec,
            parent_nonce_sha256=_sha("c"),
            child_stdout=b"",
            child_stderr=b"",
            child_execution_status="COMPLETE",
            child_returncode=0,
            runtime_receipt=_runtime_receipt(spec),
        )


def test_finalize_child_snapshot_rejects_profile_policy_not_bound_to_spec():
    spec = _spec()
    snapshot = _snapshot(spec)
    snapshot["profile_extension_evidence"]["policy"]["forbidden_extension_names"] = []
    snapshot["profile_extension_evidence"]["policy_sha256"] = audit.canonical_json_sha256(
        snapshot["profile_extension_evidence"]["policy"]
    )

    with pytest.raises(ValueError, match="real_pbd_g0_runtime_audit_spec_binding_invalid"):
        audit.finalize_child_snapshot(
            snapshot=snapshot,
            audit_spec=spec,
            parent_nonce_sha256=_sha("c"),
            child_stdout=b"",
            child_stderr=b"",
            child_execution_status="COMPLETE",
            child_returncode=0,
            runtime_receipt=_runtime_receipt(spec),
        )

def test_finalize_child_snapshot_binds_error_log_diagnostics_to_captured_bytes():
    spec = _spec()
    stderr = b"2026-07-21 [Error] [omni.example] extension startup failed\n"

    report = audit.finalize_child_snapshot(
        snapshot=_snapshot(spec),
        audit_spec=spec,
        parent_nonce_sha256=_sha("c"),
        child_stdout=b"",
        child_stderr=stderr,
        child_execution_status="COMPLETE",
        child_returncode=0,
        runtime_receipt=_runtime_receipt(spec),
    )

    assert report["audit_status"] == "COMPLETE"
    assert report["checks"]["source_cooked_query_complete"] is True
    assert report["checks"]["child_lifecycle_clean"] is True
    assert report["checks"]["runtime_log_clean"] is False
    assert "child_runtime_errors_observed" in report["no_go_reasons"]
    assert report["child_stderr_sha256"] == hashlib.sha256(stderr).hexdigest()
    assert report["child_execution"]["stderr_diagnostic"] == {
        "authority": "real_pbd_g0_runtime_audit_stderr_diagnostic_v2",
        "schema_version": 2,
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stderr_byte_count": len(stderr),
        "scanner_policy": "ascii_line_severity_and_native_abi_v2",
        "marker_line_counts": {
            "child_error_protocol": 0,
            "kit_error": 1,
            "kit_fatal": 0,
            "native_abi_warning": 0,
            "python_traceback": 0,
        },
        "runtime_log_clean": False,
    }


def test_finalize_child_snapshot_fails_closed_for_native_abi_warning():
    spec = _spec()
    report = audit.finalize_child_snapshot(
        snapshot=_snapshot(spec),
        audit_spec=spec,
        parent_nonce_sha256=_sha("c"),
        child_stdout=b"",
        child_stderr=(
            b"Warning: Possible version incompatibility. Attempting to load "
            b"omni::fabric::IPath with version v0.2 against v0.1.\n"
        ),
        child_execution_status="COMPLETE",
        child_returncode=0,
        runtime_receipt=_runtime_receipt(spec),
    )

    assert report["checks"]["runtime_log_clean"] is False
    assert report["child_execution"]["stderr_diagnostic"]["marker_line_counts"] == {
        "child_error_protocol": 0,
        "kit_error": 0,
        "kit_fatal": 0,
        "native_abi_warning": 1,
        "python_traceback": 0,
    }
    assert "child_runtime_errors_observed" not in report["no_go_reasons"]
    assert (
        "native_abi_version_incompatibility_warning_observed"
        in report["no_go_reasons"]
    )


def test_stage_evidence_rejects_native_abi_warning_reason_mismatches():
    spec = _spec()
    report = audit.finalize_child_snapshot(
        snapshot=_snapshot(spec),
        audit_spec=spec,
        parent_nonce_sha256=_sha("c"),
        child_stdout=b"",
        child_stderr=(
            b"2026-07-21 [Warning] [carb] Possible version incompatibility. "
            b"Attempting to load omni::fabric::IPath with version v0.2 against v0.1.\n"
        ),
        child_execution_status="COMPLETE",
        child_returncode=0,
        runtime_receipt=_runtime_receipt(spec),
    )
    fixture_identity_sha256 = report["fixture_identity_sha256"]
    treatment_sha256 = audit.canonical_json_sha256(spec)

    build_stage_evidence(
        stage="G0",
        decision="G0_NO_GO",
        fixture_identity_sha256=fixture_identity_sha256,
        treatment_sha256=treatment_sha256,
        source_evidence=report,
    )

    missing_reason = copy.deepcopy(report)
    missing_reason["no_go_reasons"].remove(
        "native_abi_version_incompatibility_warning_observed"
    )
    missing_reason["sha256"] = audit.canonical_json_sha256(
        {key: value for key, value in missing_reason.items() if key != "sha256"}
    )
    with pytest.raises(ValueError, match="real_pbd_stage_source_evidence_binding_invalid"):
        build_stage_evidence(
            stage="G0",
            decision="G0_NO_GO",
            fixture_identity_sha256=fixture_identity_sha256,
            treatment_sha256=treatment_sha256,
            source_evidence=missing_reason,
        )

    spurious_reason = copy.deepcopy(report)
    spurious_reason["child_execution"]["stderr_diagnostic"]["marker_line_counts"][
        "native_abi_warning"
    ] = 0
    spurious_reason["checks"]["runtime_log_clean"] = True
    spurious_reason["child_execution"]["stderr_diagnostic"]["runtime_log_clean"] = True
    spurious_reason["sha256"] = audit.canonical_json_sha256(
        {key: value for key, value in spurious_reason.items() if key != "sha256"}
    )
    with pytest.raises(ValueError, match="real_pbd_stage_source_evidence_binding_invalid"):
        build_stage_evidence(
            stage="G0",
            decision="G0_NO_GO",
            fixture_identity_sha256=fixture_identity_sha256,
            treatment_sha256=treatment_sha256,
            source_evidence=spurious_reason,
        )

    legacy_policy = copy.deepcopy(report)
    legacy_policy["child_execution"]["stderr_diagnostic"] = {
        **legacy_policy["child_execution"]["stderr_diagnostic"],
        "authority": "real_pbd_g0_runtime_audit_stderr_diagnostic_v1",
        "schema_version": 1,
        "scanner_policy": "ascii_line_severity_v1",
        "marker_line_counts": {
            "child_error_protocol": 0,
            "kit_error": 0,
            "kit_fatal": 0,
            "python_traceback": 0,
        },
        "runtime_log_clean": True,
    }
    legacy_policy["checks"]["runtime_log_clean"] = True
    legacy_policy["no_go_reasons"].remove(
        "native_abi_version_incompatibility_warning_observed"
    )
    legacy_policy["sha256"] = audit.canonical_json_sha256(
        {key: value for key, value in legacy_policy.items() if key != "sha256"}
    )
    with pytest.raises(ValueError, match="real_pbd_stage_source_evidence_binding_invalid"):
        build_stage_evidence(
            stage="G0",
            decision="G0_NO_GO",
            fixture_identity_sha256=fixture_identity_sha256,
            treatment_sha256=treatment_sha256,
            source_evidence=legacy_policy,
        )


def test_finalize_child_snapshot_fails_closed_for_runtime_contract_mismatch():
    spec = _spec()
    receipt = _runtime_receipt(spec)
    receipt["observed_runtime"]["numpy_version"] = "2.2.6"
    receipt["attestation_status"] = "MISMATCH"

    report = audit.finalize_child_snapshot(
        snapshot=_snapshot(spec),
        audit_spec=spec,
        parent_nonce_sha256=_sha("c"),
        child_stdout=b"",
        child_stderr=b"",
        child_execution_status="COMPLETE",
        child_returncode=0,
        runtime_receipt=receipt,
    )

    assert report["checks"]["runtime_contract_matches"] is False
    assert "runtime_contract_mismatch" in report["no_go_reasons"]


def test_parent_retains_valid_snapshot_when_child_exit_is_dirty(tmp_path, monkeypatch):
    spec = _spec()

    class FakeProcess:
        pid = 999_999
        returncode = 2

        def communicate(self, timeout=None):
            del timeout
            return b"", b"real_pbd_g0_runtime_audit_child_error:RuntimeError:close failed\n"

        def poll(self):
            return self.returncode

    def fake_popen(command, **kwargs):
        del kwargs
        snapshot_path = Path(command[command.index("--snapshot-out") + 1])
        receipt_path = Path(command[command.index("--runtime-receipt-out") + 1])
        nonce = command[command.index("--nonce-sha256") + 1]
        audit.atomic_create_bytes(snapshot_path, audit._canonical_json_bytes(_snapshot(spec, nonce)))
        audit.atomic_create_bytes(receipt_path, audit._canonical_json_bytes(_runtime_receipt(spec, nonce)))
        return FakeProcess()

    monkeypatch.setattr(audit, "build_audit_spec", lambda **kwargs: spec)
    monkeypatch.setattr(audit, "runtime_python_executable", lambda: "/fake/isaac-python")
    monkeypatch.setattr(audit.subprocess, "Popen", fake_popen)

    out_dir = tmp_path / "dirty-exit"
    assert audit.run_parent(asset_path=tmp_path / "fixture.usda", out_dir=out_dir, timeout_s=1.0) == 2

    report = audit._read_canonical_json(out_dir / audit.REPORT_BASENAME)[0]
    persisted_snapshot = audit._read_canonical_json(out_dir / audit.SNAPSHOT_BASENAME)[0]
    assert persisted_snapshot["audit_status"] == "COMPLETE"
    assert report["audit_status"] == "COMPLETE"
    assert report["checks"]["source_cooked_query_complete"] is True
    assert report["checks"]["child_lifecycle_clean"] is False
    assert report["checks"]["runtime_log_clean"] is False
    assert "child_lifecycle_not_clean" in report["no_go_reasons"]
    assert "child_runtime_errors_observed" in report["no_go_reasons"]


def test_parent_error_log_returns_nonzero_and_preserves_complete_snapshot(tmp_path, monkeypatch):
    spec = _spec()

    class FakeProcess:
        pid = 999_999
        returncode = 0

        def communicate(self, timeout=None):
            del timeout
            return b"", b"2026-07-21 [Error] [omni.example] extension startup failed\n"

        def poll(self):
            return self.returncode

    def fake_popen(command, **kwargs):
        del kwargs
        snapshot_path = Path(command[command.index("--snapshot-out") + 1])
        receipt_path = Path(command[command.index("--runtime-receipt-out") + 1])
        nonce = command[command.index("--nonce-sha256") + 1]
        audit.atomic_create_bytes(snapshot_path, audit._canonical_json_bytes(_snapshot(spec, nonce)))
        audit.atomic_create_bytes(receipt_path, audit._canonical_json_bytes(_runtime_receipt(spec, nonce)))
        return FakeProcess()

    def process_group_absent(*args):
        del args
        raise ProcessLookupError

    monkeypatch.setattr(audit, "build_audit_spec", lambda **kwargs: spec)
    monkeypatch.setattr(audit, "runtime_python_executable", lambda: "/fake/isaac-python")
    monkeypatch.setattr(audit.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(audit.os, "killpg", process_group_absent)

    out_dir = tmp_path / "error-log"
    assert audit.run_parent(asset_path=tmp_path / "fixture.usda", out_dir=out_dir, timeout_s=1.0) == 2

    report = audit._read_canonical_json(out_dir / audit.REPORT_BASENAME)[0]
    assert (out_dir / audit.SNAPSHOT_BASENAME).is_file()
    assert report["audit_status"] == "COMPLETE"
    assert report["checks"]["source_cooked_query_complete"] is True
    assert report["checks"]["child_lifecycle_clean"] is True
    assert report["checks"]["runtime_log_clean"] is False
    assert "child_runtime_errors_observed" in report["no_go_reasons"]


def test_parent_publishes_effective_fallback_snapshot_after_raw_snapshot_rejection(
    tmp_path, monkeypatch
):
    spec = _spec()

    class FakeProcess:
        pid = 999_999
        returncode = 0

        def communicate(self, timeout=None):
            del timeout
            return b"", b""

        def poll(self):
            return self.returncode

    def fake_popen(command, **kwargs):
        del kwargs
        snapshot_path = Path(command[command.index("--snapshot-out") + 1])
        receipt_path = Path(command[command.index("--runtime-receipt-out") + 1])
        nonce = command[command.index("--nonce-sha256") + 1]
        rejected = _snapshot(spec, nonce)
        rejected["asset_sha256"] = _sha("d")
        audit.atomic_create_bytes(snapshot_path, audit._canonical_json_bytes(rejected))
        audit.atomic_create_bytes(receipt_path, audit._canonical_json_bytes(_runtime_receipt(spec, nonce)))
        return FakeProcess()

    monkeypatch.setattr(audit, "build_audit_spec", lambda **kwargs: spec)
    monkeypatch.setattr(audit, "runtime_python_executable", lambda: "/fake/isaac-python")
    monkeypatch.setattr(audit.subprocess, "Popen", fake_popen)

    out_dir = tmp_path / "raw-snapshot-rejected"
    assert audit.run_parent(asset_path=tmp_path / "fixture.usda", out_dir=out_dir, timeout_s=1.0) == 2

    report = audit._read_canonical_json(out_dir / audit.REPORT_BASENAME)[0]
    published_snapshot = audit._read_canonical_json(out_dir / audit.SNAPSHOT_BASENAME)[0]
    assert published_snapshot["audit_status"] == "CHILD_FAILURE"
    assert report["raw_snapshot_sha256"] == audit.canonical_json_sha256(
        published_snapshot
    )


def test_stage_evidence_rejects_missing_parent_runtime_diagnostics():
    spec = _spec()
    report = audit.finalize_child_snapshot(
        snapshot=_snapshot(spec),
        audit_spec=spec,
        parent_nonce_sha256=_sha("c"),
        child_stdout=b"",
        child_stderr=b"",
        child_execution_status="COMPLETE",
        child_returncode=0,
        runtime_receipt=_runtime_receipt(spec),
    )
    incomplete = copy.deepcopy(report)
    del incomplete["child_execution"]
    incomplete["sha256"] = audit.canonical_json_sha256(
        {key: value for key, value in incomplete.items() if key != "sha256"}
    )

    with pytest.raises(ValueError, match="real_pbd_stage_source_evidence_binding_invalid"):
        audit.build_stage_evidence(
            stage="G0",
            decision="G0_NO_GO",
            fixture_identity_sha256=_snapshot(spec)["fixture_identity_sha256"],
            treatment_sha256=audit.canonical_json_sha256(spec),
            source_evidence=incomplete,
        )


def test_audit_spec_and_runner_forbid_world_or_action_runtime_paths(tmp_path):
    spec = _spec()
    assert audit.validate_audit_spec(spec)["no_action_policy"] == "audited_read_only_no_world_v1"
    assert audit.runtime_python_executable() == str(audit.FORMAL_ISAAC41_PYTHON)
    environment = audit._sealed_child_environment(tmp_path)
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["ACCEPT_EULA"] == "Y"
    assert environment["OMNI_KIT_ACCEPT_EULA"] == "YES"
    for forbidden in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "CARB_APP_PATH",
        "EXP_PATH",
        "ISAAC_PATH",
        "OMNI_SERVER",
        "LD_PRELOAD",
    ):
        assert forbidden not in environment

    source = Path(audit.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "from isaacsim.core.api import World",
        "create_robot(",
        "create_task(",
        "world.step(",
        "world.reset(",
    ):
        assert forbidden not in source


def test_experimental_profile_smoke_is_explicit_and_hash_bound(tmp_path):
    asset = tmp_path / "fixture.usda"
    asset.write_text("#usda 1.0\n", encoding="utf-8")

    spec = audit.build_audit_spec(
        asset_path=asset,
        experience_path=audit.EXPERIMENTAL_PROPERTY_QUERY_EXPERIENCE,
    )

    assert spec["runtime_contract"]["experience_path"] == str(
        audit.EXPERIMENTAL_PROPERTY_QUERY_EXPERIENCE
    )
    assert spec["runtime_contract"]["experience_sha256"] == audit._sha256_file(
        audit.EXPERIMENTAL_PROPERTY_QUERY_EXPERIENCE
    )
    assert {record["name"]: record["version"] for record in spec[
        "profile_extension_policy"
    ]["required_extensions"]}["omni.usd"] == "1.11.2"
    assert spec["profile_extension_policy"]["forbidden_extension_names"] == [
        "omni.physx.fabric",
        "omni.physxfabric",
    ]
    args = audit.parse_args(
        ["--out-dir", str(tmp_path / "out"), "--experimental-profile-smoke"]
    )
    assert args.experimental_profile_smoke is True

    unapproved = tmp_path / "unapproved.kit"
    unapproved.write_text("[package]\nversion = \"4.1.0\"\n", encoding="utf-8")
    with pytest.raises(
        ValueError, match="real_pbd_g0_runtime_audit_experience_unapproved"
    ):
        audit.build_audit_spec(asset_path=asset, experience_path=unapproved)


def test_parent_setup_failure_still_publishes_typed_no_go(tmp_path):
    out_dir = tmp_path / "missing-asset-audit"

    assert audit.run_parent(
        asset_path=tmp_path / "missing.usda", out_dir=out_dir, timeout_s=1.0
    ) == 2

    report = audit._read_canonical_json(out_dir / audit.REPORT_BASENAME)[0]
    artifact = audit._read_canonical_json(out_dir / audit.ARTIFACT_BASENAME)[0]
    assert report["decision"] == "G0_NO_GO"
    assert report["audit_status"] == "CHILD_FAILURE"
    assert artifact["decision"] == "G0_NO_GO"
