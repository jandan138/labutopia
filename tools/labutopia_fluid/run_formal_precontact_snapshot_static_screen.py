#!/usr/bin/env python3
"""Run a sealed no-step static projection of a formal v2 event-0 snapshot.

The formal source-settle prefix and this static child remain isolated.  This
child consumes only a create-only, hash-bound handoff and never replays a
controller, applies an action, moves the source, or advances post-reset
physics.  Its AABB result is diagnostic-only and cannot authorize a gate or
Phase 3.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import traceback
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import run_formal_precontact_event0_replay as formal_runner
from tools.labutopia_fluid import (
    run_formal_precontact_usd_dependency_preflight as dependency_preflight,
)
from tools.labutopia_fluid import run_nonformal_controller_static_collision_screen as legacy
from utils import formal_precontact_snapshot_static_screen as static_screen
from utils import formal_precontact_event0_snapshot_replay as snapshot_replay


AUTHORITY = "formal_precontact_snapshot_static_screen_v1"
CLASSIFICATION = "FORMAL_PRECONTACT_SNAPSHOT_STATIC_SCREEN_ONLY"
RUNTIME_MODULE = (
    REPO_ROOT / "tools/labutopia_fluid/formal_precontact_snapshot_static_screen_runtime.py"
).resolve()
PURE_MODULE = (REPO_ROOT / "utils/formal_precontact_snapshot_static_screen.py").resolve()
SNAPSHOT_PURE_MODULE = (
    REPO_ROOT / "utils/formal_precontact_event0_snapshot_replay.py"
).resolve()
FORMAL_RUNNER_MODULE = Path(formal_runner.__file__).resolve()
FORMAL_V1_PURE_MODULE = (
    REPO_ROOT / "utils/formal_precontact_event0_replay.py"
).resolve()
FORMAL_RUNTIME_MODULE = (
    REPO_ROOT / "tools/labutopia_fluid/formal_precontact_event0_replay_runtime.py"
).resolve()
HANDOFF_NAME = "formal_precontact_snapshot_handoff.json"
PROJECTION_NAME = "event0_snapshot_projection.json"


def _runtime_module() -> Any:
    return importlib.import_module(
        "tools.labutopia_fluid.formal_precontact_snapshot_static_screen_runtime"
    )


def _require_sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"formal_snapshot_static_{field}_invalid")
    return value


def _g0_scope_sha256(value: Mapping[str, Any]) -> str:
    payload = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def source_paths(
    frozen: Mapping[str, Any],
    *,
    fixed_mount_profile: Mapping[str, Any] | None = None,
    usd_dependency_manifest: Mapping[str, Any] | None = None,
) -> tuple[Path, ...]:
    profile = (
        None
        if fixed_mount_profile is None
        else snapshot_replay.validate_fixed_mount_profile(fixed_mount_profile)
    )
    base = set(legacy.source_paths(frozen))
    extra = legacy._python_import_paths(
        [
            "tools/labutopia_fluid/run_formal_precontact_snapshot_static_screen.py",
            "tools/labutopia_fluid/formal_precontact_snapshot_static_screen_runtime.py",
            "utils/formal_precontact_snapshot_static_screen.py",
            "utils/formal_precontact_event0_snapshot_replay.py",
        ]
    )
    paths = {
        Path(__file__).resolve(),
        RUNTIME_MODULE,
        PURE_MODULE,
        SNAPSHOT_PURE_MODULE,
        FORMAL_RUNNER_MODULE,
        FORMAL_V1_PURE_MODULE,
        FORMAL_RUNTIME_MODULE,
        *base,
        *extra,
    }
    if profile is not None:
        if usd_dependency_manifest is None:
            raise ValueError("formal_snapshot_static_fixed_mount_dependency_closure_missing")
        profile_path = (REPO_ROOT / profile["profile_path"]).resolve()
        overlay_path = (REPO_ROOT / profile["filter"]["overlay_path"]).resolve()
        if (
            profile_path.is_symlink()
            or overlay_path.is_symlink()
            or not profile_path.is_file()
            or not overlay_path.is_file()
            or legacy.sha256_file(profile_path) != profile["profile_sha256"]
            or legacy.sha256_file(overlay_path) != profile["filter"]["overlay_sha256"]
        ):
            raise ValueError("formal_snapshot_static_fixed_mount_profile_binding_invalid")
        paths.update(
            (
                profile_path,
                overlay_path,
                dependency_preflight.RUNTIME_MODULE,
                dependency_preflight.PURE_MODULE,
                *dependency_preflight.repository_closure_paths(usd_dependency_manifest),
            )
        )
    elif usd_dependency_manifest is not None:
        raise ValueError("formal_snapshot_static_dependency_closure_unexpected")
    if any(not path.is_file() or not path.is_relative_to(REPO_ROOT) for path in paths):
        raise ValueError("formal_snapshot_static_source_closure_invalid")
    return tuple(sorted(paths))


def _formal_file(run_dir: Path, name: str) -> Path:
    path = run_dir / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("formal_snapshot_static_formal_artifact_missing")
    return path


def _command_value(command: Any, flag: str) -> str:
    if (
        not isinstance(command, list)
        or any(not isinstance(value, str) for value in command)
        or command.count(flag) != 1
    ):
        raise ValueError("formal_snapshot_static_formal_command_invalid")
    index = command.index(flag)
    if index + 1 >= len(command):
        raise ValueError("formal_snapshot_static_formal_command_invalid")
    return command[index + 1]


def _verify_formal_run(run_dir: Path) -> dict[str, Any]:
    if run_dir.is_symlink() or not run_dir.is_dir() or not run_dir.is_relative_to(REPO_ROOT):
        raise ValueError("formal_snapshot_static_formal_run_path_invalid")
    attestation = legacy._attestation_module()
    report_path = _formal_file(run_dir, "report.json")
    manifest_path = _formal_file(run_dir, "run_manifest.json")
    child_path = _formal_file(run_dir, "child_report.json")
    receipt_path = _formal_file(run_dir, "runtime_receipt.json")
    execution_request_path = _formal_file(run_dir, "execution_request.json")
    frozen_path = _formal_file(run_dir, "frozen_v7_config.json")
    replay_request_path = _formal_file(run_dir, "replay_request.json")
    trace_path = _formal_file(run_dir, "precontact_trace.json")
    report = legacy._read_canonical_line(report_path)
    child = legacy._read_canonical_line(child_path)
    manifest = attestation._read_canonical_json(manifest_path)
    receipt = attestation._read_canonical_json(receipt_path)
    execution_request = attestation.validate_execution_request(
        attestation._read_canonical_json(execution_request_path)
    )
    formal_frozen = legacy._read_canonical_line(frozen_path)
    raw_replay_request = legacy._read_canonical_line(replay_request_path)
    fixed_mount = (
        isinstance(raw_replay_request.get("contract"), Mapping)
        and raw_replay_request["contract"].get("authority")
        == snapshot_replay.FIXED_MOUNT_AUTHORITY
    )
    replay_request = formal_runner._validate_request_unbootstrapped(
        raw_replay_request, snapshot_v2=True, fixed_mount=fixed_mount
    )
    fixed_mount_profile = formal_runner._fixed_mount_profile_from_contract(
        replay_request["contract"]
    )
    if fixed_mount != (fixed_mount_profile is not None):
        raise ValueError("formal_snapshot_static_formal_request_binding_invalid")
    dependency_binding = None
    dependency_manifest = None
    dependency_binding_path = None
    if fixed_mount:
        dependency_binding_path = _formal_file(run_dir, formal_runner.PREFLIGHT_BINDING_NAME)
        dependency_binding = legacy._read_canonical_line(dependency_binding_path)
        expected_dependency_input = dependency_preflight.build_input(
            formal_frozen, fixed_mount_profile=fixed_mount_profile
        )
        verified_preflight = dependency_preflight.verify_preflight_binding(
            dependency_binding, expected_input=expected_dependency_input
        )
        dependency_binding = verified_preflight["binding"]
        dependency_manifest = verified_preflight["manifest"]
    elif (run_dir / formal_runner.PREFLIGHT_BINDING_NAME).exists():
        raise ValueError("formal_snapshot_static_formal_request_binding_invalid")
    required_authority = formal_runner._authority(True, fixed_mount=fixed_mount)
    required_classification = formal_runner._classification(True, fixed_mount=fixed_mount)
    expected_formal_source = attestation.capture_source_identity(
        formal_runner.source_paths(
            formal_frozen,
            snapshot_v2=True,
            fixed_mount_profile=fixed_mount_profile,
            usd_dependency_manifest=dependency_manifest,
        )
    )
    if (
        report.get("authority") != required_authority
        or report.get("classification") != required_classification
        or report.get("decision") != "FORMAL_PRECONTACT_EVENT0_PASS"
        or child.get("authority") != required_authority
        or child.get("classification") != required_classification
        or child.get("decision") != "FORMAL_PRECONTACT_EVENT0_PASS"
        or child.get("contract") != report.get("contract")
        or child.get("evaluation") != report.get("evaluation")
        or manifest.get("authority") != required_authority
        or manifest.get("classification") != required_classification
        or manifest.get("report_sha256") != legacy.sha256_file(report_path)
        or manifest.get("child_returncode") != 0
        or report.get("parent_verification", {}).get("verified") is not True
        or report["parent_verification"].get("child_returncode") != 0
        or report["parent_verification"].get("child_report_sha256")
        != legacy.sha256_file(child_path)
        or report["parent_verification"].get("runtime_receipt_sha256")
        != attestation.canonical_json_sha256(receipt)
        or manifest.get("runtime_receipt_sha256")
        != attestation.canonical_json_sha256(receipt)
        or (
            fixed_mount
            and (
                report.get("usd_dependency_preflight") != dependency_binding
                or child.get("usd_dependency_preflight") != dependency_binding
                or manifest.get("usd_dependency_preflight") != dependency_binding
                or report["parent_verification"].get(
                    "usd_dependency_preflight_reverified"
                )
                is not True
            )
        )
        or (
            not fixed_mount
            and (
                report.get("usd_dependency_preflight") is not None
                or child.get("usd_dependency_preflight") is not None
                or manifest.get("usd_dependency_preflight") is not None
            )
        )
    ):
        raise ValueError("formal_snapshot_static_formal_report_invalid")
    runtime = child.get("runtime")
    child_pid = manifest.get("child_pid")
    if (
        not isinstance(runtime, Mapping)
        or isinstance(child_pid, bool)
        or not isinstance(child_pid, int)
        or child_pid <= 0
        or report["parent_verification"].get("child_pid") != child_pid
    ):
        raise ValueError("formal_snapshot_static_formal_runtime_invalid")
    binding = attestation.execution_binding_for_request(
        execution_request, child_pid=child_pid
    )
    if (
        runtime.get("receipt_sha256") != attestation.canonical_json_sha256(receipt)
        or runtime.get("execution_binding") != binding
        or runtime.get("source_after_sha256")
        != binding["source_sha256"]
    ):
        raise ValueError("formal_snapshot_static_formal_runtime_invalid")
    attestation.require_matched_runtime_receipt(
        receipt, expected_execution_binding=binding
    )
    if (
        manifest.get("source_before") != manifest.get("source_after")
        or manifest.get("source_before") != execution_request["source"]
        or execution_request["source"] != dict(expected_formal_source)
        or binding["source_sha256"] != execution_request["source_sha256"]
        or binding["source_sha256"]
        != attestation.canonical_json_sha256(manifest["source_before"])
    ):
        raise ValueError("formal_snapshot_static_formal_source_compatibility_invalid")
    if (
        replay_request["frozen_config_path"] != str(frozen_path)
        or replay_request["frozen_config_sha256"] != legacy.sha256_file(frozen_path)
        or replay_request["contract"] != report["contract"]
        or report["contract"]
        != formal_runner.build_contract(
            formal_frozen,
            snapshot_v2=True,
            fixed_mount_profile=fixed_mount_profile,
        )
        or formal_frozen.get("sha256") != report["contract"].get("v7_config_sha256")
        or formal_frozen.get("local_scene", {}).get("sha256")
        != report["contract"].get("local_scene_sha256")
        or formal_frozen.get("local_franka", {}).get("sha256")
        != report["contract"].get("local_franka_sha256")
        or _command_value(manifest.get("command"), "--frozen-config") != str(frozen_path)
        or _command_value(manifest.get("command"), "--request") != str(replay_request_path)
        or _command_value(manifest.get("command"), "--execution-request")
        != str(execution_request_path)
        or "--snapshot-v2" not in manifest.get("command", [])
        or (
            fixed_mount
            and (
                _command_value(
                    manifest.get("command"), "--usd-dependency-preflight-binding"
                )
                != str(dependency_binding_path)
                or _command_value(
                    manifest.get("command"),
                    "--expected-usd-dependency-preflight-binding-sha256",
                )
                != legacy.sha256_file(dependency_binding_path)
            )
        )
    ):
        raise ValueError("formal_snapshot_static_formal_request_binding_invalid")
    trace_verification = formal_runner._verify_trace_artifact(
        child.get("trace"),
        root=run_dir,
        contract=report["contract"],
        snapshot_v2=True,
        fixed_mount=fixed_mount,
    )
    if (
        trace_verification["evaluation"] != report["evaluation"]
        or report.get("artifact_verification", {}).get("trace_sha256")
        != legacy.sha256_file(trace_path)
        or report["artifact_verification"].get("evaluation")
        != trace_verification["evaluation"]
        or child.get("scope", {}).get("event0_integrated") is not False
        or child["scope"].get("close_command_emitted") is not False
        or child["scope"].get("lift_command_emitted") is not False
        or child["scope"].get("attachment_invocation_count") != 0
        or child["scope"].get("contact_observer_invocation_count") != 0
        or child["scope"].get("phase3_or_gate_evaluated") is not False
    ):
        raise ValueError("formal_snapshot_static_formal_trace_invalid")
    provenance = {
        "formal_decision": report["decision"],
        "report_sha256": legacy.sha256_file(report_path),
        "manifest_sha256": legacy.sha256_file(manifest_path),
        "child_report_sha256": legacy.sha256_file(child_path),
        "runtime_receipt_sha256": legacy.sha256_file(receipt_path),
        "execution_request_sha256": legacy.sha256_file(execution_request_path),
        "trace_sha256": legacy.sha256_file(trace_path),
        "source_sha256": binding["source_sha256"],
    }
    if dependency_binding is not None:
        provenance["usd_dependency_preflight"] = dependency_binding
    handoff = static_screen.build_static_handoff(
        formal_contract=report["contract"],
        formal_trace=trace_verification["trace"],
        formal_evaluation=report["evaluation"],
        formal_provenance=provenance,
    )
    return {
        "handoff": handoff,
        "provenance": provenance,
        "fixed_mount_profile": fixed_mount_profile,
        "usd_dependency_preflight": dependency_binding,
        "usd_dependency_manifest": dependency_manifest,
    }


def build_contract(frozen: Mapping[str, Any], handoff: Mapping[str, Any]) -> dict[str, Any]:
    diagnostic = legacy._frozen_diagnostic(frozen)
    local_scene = frozen.get("local_scene")
    local_franka = frozen.get("local_franka")
    normalized_handoff = static_screen.normalize_static_handoff(handoff)
    if not isinstance(local_scene, Mapping) or not isinstance(local_franka, Mapping):
        raise ValueError("formal_snapshot_static_frozen_config_invalid")
    payload = {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "v7_config_sha256": _require_sha256(frozen.get("sha256"), field="config_sha256"),
        "local_scene_sha256": _require_sha256(local_scene.get("sha256"), field="scene_sha256"),
        "local_franka_sha256": _require_sha256(local_franka.get("sha256"), field="franka_sha256"),
        "hidden_cube_overlay_sha256": legacy.sha256_file(legacy.HIDDEN_CUBE_OVERLAY),
        "handoff_sha256": normalized_handoff["sha256"],
        "expected_collider_inventory": dict(legacy.EXPECTED_COLLIDER_INVENTORY),
        "aabb_numerical_margin_m": legacy.AABB_NUMERICAL_MARGIN_M,
        "g0_or_gate_authorized": False,
        "post_reset_physics_steps_allowed": 0,
    }
    formal_contract = normalized_handoff["formal_contract"]
    for field in (
        "v7_config_sha256",
        "local_scene_sha256",
        "local_franka_sha256",
        "hidden_cube_overlay_sha256",
    ):
        if formal_contract.get(field) != payload[field]:
            raise ValueError("formal_snapshot_static_fixture_contract_invalid")
    if formal_contract.get("authority") == snapshot_replay.FIXED_MOUNT_AUTHORITY:
        profile = snapshot_replay.validate_fixed_mount_profile(
            formal_contract.get("fixed_mount_profile")
        )
        payload["fixed_mount_profile_sha256"] = profile["profile_sha256"]
    return {**payload, "sha256": static_screen.canonical_json_sha256(payload)}


def _request(
    *,
    contract: Mapping[str, Any],
    frozen_path: Path,
    frozen_sha256: str,
    handoff_path: Path,
    handoff_file_sha256: str,
) -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "contract": dict(contract),
        "contract_sha256": static_screen.canonical_json_sha256(contract),
        "frozen_config_path": str(frozen_path),
        "frozen_config_sha256": frozen_sha256,
        "handoff_path": str(handoff_path),
        "handoff_file_sha256": handoff_file_sha256,
    }


def _validate_request(
    value: Any,
    *,
    frozen: Mapping[str, Any],
    handoff: Mapping[str, Any],
    handoff_file_sha256: str,
) -> dict[str, Any]:
    expected = {
        "authority",
        "classification",
        "schema_version",
        "contract",
        "contract_sha256",
        "frozen_config_path",
        "frozen_config_sha256",
        "handoff_path",
        "handoff_file_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("formal_snapshot_static_request_invalid")
    contract = build_contract(frozen, handoff)
    if (
        value["authority"] != AUTHORITY
        or value["classification"] != CLASSIFICATION
        or value["schema_version"] != 1
        or value["contract"] != contract
        or value["contract_sha256"] != static_screen.canonical_json_sha256(contract)
        or not isinstance(value["frozen_config_path"], str)
        or not Path(value["frozen_config_path"]).is_absolute()
        or not isinstance(value["handoff_path"], str)
        or not Path(value["handoff_path"]).is_absolute()
        or value["handoff_file_sha256"] != handoff_file_sha256
    ):
        raise ValueError("formal_snapshot_static_request_invalid")
    return {
        **dict(value),
        "contract": contract,
        "frozen_config_sha256": _require_sha256(
            value["frozen_config_sha256"], field="frozen_config_sha256"
        ),
        "handoff_file_sha256": _require_sha256(
            value["handoff_file_sha256"], field="handoff_file_sha256"
        ),
    }


def _blocked_report(
    runtime: Mapping[str, Any] | None,
    exc: BaseException,
    contract: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "formal_precontact_snapshot_static_screen_child_v1",
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "decision": "RUNTIME_BLOCKED",
        "contract": dict(contract) if isinstance(contract, Mapping) else None,
        "runtime": dict(runtime) if isinstance(runtime, Mapping) else None,
        "fatal_error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _run_child(args: argparse.Namespace) -> int:
    app = None
    runtime = None
    contract = None
    report = None
    written = False
    try:
        frozen = legacy._read_canonical_line(args.frozen_config)
        handoff = legacy._read_canonical_line(args.handoff)
        if (
            legacy.sha256_file(args.frozen_config) != args.expected_frozen_config_sha256
            or legacy.sha256_file(args.handoff)
            != args.expected_handoff_file_sha256
        ):
            raise RuntimeError("formal_snapshot_static_child_input_sha256_mismatch")
        request = _validate_request(
            legacy._read_canonical_line(args.request),
            frozen=frozen,
            handoff=handoff,
            handoff_file_sha256=args.expected_handoff_file_sha256,
        )
        contract = request["contract"]
        if (
            request["frozen_config_path"] != str(args.frozen_config)
            or request["frozen_config_sha256"] != args.expected_frozen_config_sha256
            or request["handoff_path"] != str(args.handoff)
            or request["handoff_file_sha256"]
            != args.expected_handoff_file_sha256
        ):
            raise RuntimeError("formal_snapshot_static_child_request_binding_invalid")
        attestation = legacy._attestation_module()
        execution_request = attestation._read_canonical_json(args.execution_request)
        normalized_handoff = static_screen.normalize_static_handoff(handoff)
        fixed_mount_profile = formal_runner._fixed_mount_profile_from_contract(
            normalized_handoff["formal_contract"]
        )
        dependency_binding = None
        dependency_manifest = None
        if fixed_mount_profile is not None:
            if (
                args.usd_dependency_preflight_binding is None
                or args.expected_usd_dependency_preflight_binding_sha256 is None
            ):
                raise RuntimeError("formal_snapshot_static_dependency_preflight_missing")
            if (
                legacy.sha256_file(args.usd_dependency_preflight_binding)
                != args.expected_usd_dependency_preflight_binding_sha256
            ):
                raise RuntimeError("formal_snapshot_static_dependency_preflight_sha256_mismatch")
            expected_dependency_input = dependency_preflight.build_input(
                frozen, fixed_mount_profile=fixed_mount_profile
            )
            verified_preflight = dependency_preflight.verify_preflight_binding(
                legacy._read_canonical_line(args.usd_dependency_preflight_binding),
                expected_input=expected_dependency_input,
            )
            dependency_binding = verified_preflight["binding"]
            dependency_manifest = verified_preflight["manifest"]
            if (
                normalized_handoff["formal_provenance"].get("usd_dependency_preflight")
                != dependency_binding
            ):
                raise RuntimeError("formal_snapshot_static_dependency_preflight_handoff_invalid")
        elif (
            args.usd_dependency_preflight_binding is not None
            or args.expected_usd_dependency_preflight_binding_sha256 is not None
        ):
            raise RuntimeError("formal_snapshot_static_dependency_preflight_unexpected")
        closure = source_paths(
            frozen,
            fixed_mount_profile=fixed_mount_profile,
            usd_dependency_manifest=dependency_manifest,
        )
        execution_request = attestation.verify_execution_request(
            execution_request, source_paths=closure
        )
        receipt, app = attestation.bootstrap_effective_runtime(
            execution_request=execution_request, source_paths=closure
        )
        attestation.write_canonical_json(args.runtime_receipt_path, receipt)
        binding = attestation.execution_binding_for_request(
            execution_request, child_pid=os.getpid()
        )
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=binding
        )
        runtime = {
            "receipt_sha256": attestation.canonical_json_sha256(receipt),
            "execution_binding": binding,
            "runtime_identity": legacy._runtime_identity(
                receipt,
                contract=contract,
                frozen_config_sha256=args.expected_frozen_config_sha256,
            ),
        }
        report = _runtime_module().run_formal_precontact_snapshot_static_screen(
            app=app,
            out_dir=args.out_dir,
            frozen_config=frozen,
            contract=contract,
            runtime=runtime,
            handoff=handoff,
        )
        if dependency_binding is not None:
            report["usd_dependency_preflight"] = dependency_binding
        source_after = attestation.capture_source_identity(closure)
        source_after_sha256 = attestation.canonical_json_sha256(source_after)
        if source_after_sha256 != execution_request["source_sha256"]:
            raise RuntimeError("formal_snapshot_static_child_source_changed_during_run")
        report["runtime"]["source_after_sha256"] = source_after_sha256
        legacy._write_create_only(args.child_report_path, report)
        written = True
    except BaseException as exc:
        report = _blocked_report(runtime, exc, contract)
        if not args.child_report_path.exists():
            legacy._write_create_only(args.child_report_path, report)
            written = True
    finally:
        if app is not None and isinstance(report, Mapping) and report.get("decision") != "RUNTIME_BLOCKED":
            app.close()
    if report is None:
        raise RuntimeError("formal_snapshot_static_child_report_unavailable")
    if not written and not args.child_report_path.exists():
        legacy._write_create_only(args.child_report_path, report)
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def _verify_projection_artifact(
    value: Any,
    *,
    root: Path,
    collision_scope: Mapping[str, Any],
    expected_handoff: Mapping[str, Any],
    expected_margin_m: float,
) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"path", "sha256", "evaluation"}
        or value.get("path") != PROJECTION_NAME
    ):
        raise RuntimeError("formal_snapshot_static_projection_artifact_invalid")
    path = root / PROJECTION_NAME
    if path.is_symlink() or not path.is_file() or legacy.sha256_file(path) != value.get("sha256"):
        raise RuntimeError("formal_snapshot_static_projection_artifact_invalid")
    raw = path.read_bytes()
    try:
        projection = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("formal_snapshot_static_projection_artifact_invalid") from exc
    if not isinstance(projection, Mapping) or raw != json.dumps(
        dict(projection), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8"):
        raise RuntimeError("formal_snapshot_static_projection_artifact_invalid")
    evaluation = static_screen.evaluate_event0_static_projection(
        {
            "blocking_pairs": collision_scope["blocking_pairs"],
            "allowed_source_shell_pairs": collision_scope["allowed_source_shell_pairs"],
        },
        projection,
    )
    if (
        evaluation.get("decision") == static_screen.SAFETY_ABORT
        or value.get("evaluation") != evaluation
        or projection.get("resolved_position_target_sha256")
        != expected_handoff["event0"]["resolved_position_target_sha256"]
        or projection.get("source_collider_closure_sha256")
        != expected_handoff["source_collider_closure"]["sha256"]
        or projection.get("aabb_numerical_margin_m") != expected_margin_m
    ):
        raise RuntimeError("formal_snapshot_static_projection_artifact_invalid")
    return evaluation


def _verify_collision_scope(
    value: Any, *, handoff: Mapping[str, Any]
) -> dict[str, Any]:
    expected = {
        "authority",
        "full_robot_collider_paths",
        "designated_finger_collider_paths",
        "non_designated_robot_collider_paths",
        "source_shell_paths",
        "source_wrapper_paths",
        "table_paths",
        "beaker1_paths",
        "allowed_source_shell_pairs",
        "blocking_pairs",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise RuntimeError("formal_snapshot_static_collision_scope_invalid")
    payload = {key: item for key, item in value.items() if key != "sha256"}
    if (
        value["authority"] != "real_pbd_g0_full_robot_static_collision_scope_v1"
        or value["sha256"] != _g0_scope_sha256(payload)
    ):
        raise RuntimeError("formal_snapshot_static_collision_scope_invalid")

    def paths(field: str, *, count: int, root: str | None = None) -> list[str]:
        raw = value[field]
        if (
            not isinstance(raw, list)
            or len(raw) != count
            or raw != sorted(raw)
            or len(raw) != len(set(raw))
            or any(not isinstance(path, str) or not path.startswith("/") for path in raw)
            or (
                root is not None
                and any(path != root and not path.startswith(f"{root}/") for path in raw)
            )
        ):
            raise RuntimeError("formal_snapshot_static_collision_scope_invalid")
        return list(raw)

    closure = handoff["source_collider_closure"]
    expected_shell = sorted(
        record["path"] for record in closure["colliders"] if record["role"] == "external_shell"
    )
    expected_wrappers = sorted(
        record["path"] for record in closure["colliders"] if record["role"] == "internal_wrapper"
    )
    robot = paths("full_robot_collider_paths", count=11, root="/World/Franka")
    designated = paths("designated_finger_collider_paths", count=2, root="/World/Franka")
    non_designated = paths("non_designated_robot_collider_paths", count=9, root="/World/Franka")
    shell = paths("source_shell_paths", count=1, root="/World/beaker2")
    wrappers = paths("source_wrapper_paths", count=145, root="/World/beaker2")
    table = paths("table_paths", count=1, root="/World/table")
    beaker1 = paths("beaker1_paths", count=145, root="/World/beaker1")
    if (
        shell != expected_shell
        or wrappers != expected_wrappers
        or not set(designated) <= set(robot)
        or non_designated != sorted(set(robot) - set(designated))
    ):
        raise RuntimeError("formal_snapshot_static_collision_scope_invalid")

    def pairs(left: Sequence[str], right: Sequence[str]) -> list[list[str]]:
        return [list(sorted((first, second))) for first in left for second in right]

    expected_allowed = sorted(pairs(designated, shell))
    expected_blocking = {
        tuple(pair)
        for target_paths in (wrappers, table, beaker1)
        for pair in pairs(robot, target_paths)
    }
    expected_blocking.update(tuple(pair) for pair in pairs(non_designated, shell))
    if (
        value["allowed_source_shell_pairs"] != expected_allowed
        or value["blocking_pairs"] != [list(pair) for pair in sorted(expected_blocking)]
    ):
        raise RuntimeError("formal_snapshot_static_collision_scope_invalid")
    return dict(value)


def _verify_active_screen_scope(
    value: Any,
    *,
    full_collision_scope: Mapping[str, Any],
    handoff: Mapping[str, Any],
) -> dict[str, list[list[str]]]:
    full_scope = {
        "blocking_pairs": full_collision_scope["blocking_pairs"],
        "allowed_source_shell_pairs": full_collision_scope["allowed_source_shell_pairs"],
    }
    formal_contract = handoff["formal_contract"]
    fixed_mount = formal_contract.get("authority") == snapshot_replay.FIXED_MOUNT_AUTHORITY
    if not fixed_mount:
        if value is not None or "fixed_mount_filter" in handoff:
            raise RuntimeError("formal_snapshot_static_active_scope_invalid")
        return full_scope
    profile = snapshot_replay.validate_fixed_mount_profile(
        formal_contract.get("fixed_mount_profile")
    )
    filter_record = snapshot_replay.validate_fixed_mount_filter_record(
        handoff.get("fixed_mount_filter"), fixed_mount_profile=profile
    )
    expected = static_screen.build_fixed_mount_filtered_screen_scope(
        full_scope,
        fixed_mount_profile=profile,
        fixed_mount_filter=filter_record,
    )
    if value != expected:
        raise RuntimeError("formal_snapshot_static_active_scope_invalid")
    return {
        "blocking_pairs": expected["blocking_pairs"],
        "allowed_source_shell_pairs": expected["allowed_source_shell_pairs"],
    }


def _verify_child_report(
    child: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    handoff: Mapping[str, Any],
    receipt_sha256: str,
    binding: Mapping[str, Any],
    out_dir: Path,
    usd_dependency_preflight: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if (
        child.get("authority") != AUTHORITY
        or child.get("classification") != CLASSIFICATION
        or child.get("contract") != dict(contract)
        or not isinstance(child.get("runtime"), Mapping)
        or child["runtime"].get("receipt_sha256") != receipt_sha256
        or child["runtime"].get("execution_binding") != dict(binding)
        or (
            handoff["formal_contract"].get("authority")
            == snapshot_replay.FIXED_MOUNT_AUTHORITY
            and (
                usd_dependency_preflight is None
                or child.get("usd_dependency_preflight") != dict(usd_dependency_preflight)
            )
        )
        or (
            handoff["formal_contract"].get("authority")
            != snapshot_replay.FIXED_MOUNT_AUTHORITY
            and child.get("usd_dependency_preflight") is not None
        )
    ):
        raise RuntimeError("formal_snapshot_static_child_contract_invalid")
    if child.get("decision") == "RUNTIME_BLOCKED":
        return dict(child)
    if child["runtime"].get("source_after_sha256") != binding.get("source_sha256"):
        raise RuntimeError("formal_snapshot_static_child_source_identity_invalid")
    if child.get("decision") not in {static_screen.CLEAR, static_screen.NO_GO}:
        raise RuntimeError("formal_snapshot_static_child_decision_invalid")
    scope = child.get("scope")
    timeline = child.get("timeline")
    collision_scope = child.get("collision_scope")
    handoff_report = child.get("handoff")
    verified_collision_scope = _verify_collision_scope(collision_scope, handoff=handoff)
    active_screen_scope = _verify_active_screen_scope(
        child.get("active_screen_scope"),
        full_collision_scope=verified_collision_scope,
        handoff=handoff,
    )
    fixed_mount = handoff["formal_contract"].get("authority") == snapshot_replay.FIXED_MOUNT_AUTHORITY
    if fixed_mount:
        profile = snapshot_replay.validate_fixed_mount_profile(
            handoff["formal_contract"].get("fixed_mount_profile")
        )
        fixed_mount_filter = snapshot_replay.validate_fixed_mount_filter_record(
            child.get("fixed_mount_filter"), fixed_mount_profile=profile
        )
        if fixed_mount_filter != handoff.get("fixed_mount_filter"):
            raise RuntimeError("formal_snapshot_static_fixed_mount_filter_invalid")
    elif child.get("fixed_mount_filter") is not None:
        raise RuntimeError("formal_snapshot_static_fixed_mount_filter_invalid")
    baseline_report = child.get("baseline_comparison")
    if (
        not isinstance(baseline_report, Mapping)
        or set(baseline_report) != {"record", "evaluation"}
    ):
        raise RuntimeError("formal_snapshot_static_baseline_comparison_invalid")
    baseline_evaluation = static_screen.evaluate_fixed_mount_baseline_comparison(
        baseline_report["record"]
    )
    if (
        baseline_evaluation.get("decision") == static_screen.SAFETY_ABORT
        or baseline_report["evaluation"] != baseline_evaluation
    ):
        raise RuntimeError("formal_snapshot_static_baseline_comparison_invalid")
    geometry_audit_report = child.get("geometry_audit")
    if (
        not isinstance(geometry_audit_report, Mapping)
        or set(geometry_audit_report) != {"record", "evaluation"}
    ):
        raise RuntimeError("formal_snapshot_static_geometry_audit_invalid")
    geometry_evaluation = static_screen.evaluate_link0_table_geometry_audit(
        geometry_audit_report["record"]
    )
    if (
        geometry_evaluation.get("decision") == static_screen.SAFETY_ABORT
        or geometry_audit_report["evaluation"] != geometry_evaluation
    ):
        raise RuntimeError("formal_snapshot_static_geometry_audit_invalid")
    mounting_alignment_report = child.get("mounting_alignment")
    if (
        not isinstance(mounting_alignment_report, Mapping)
        or set(mounting_alignment_report) != {"record", "evaluation"}
    ):
        raise RuntimeError("formal_snapshot_static_mounting_alignment_invalid")
    mounting_evaluation = static_screen.evaluate_link0_table_mounting_alignment(
        mounting_alignment_report["record"]
    )
    if (
        mounting_evaluation.get("decision") == static_screen.SAFETY_ABORT
        or mounting_alignment_report["evaluation"] != mounting_evaluation
    ):
        raise RuntimeError("formal_snapshot_static_mounting_alignment_invalid")
    if (
        not isinstance(scope, Mapping)
        or scope.get("event0_only") is not True
        or scope.get("controller_forwarded") is not False
        or scope.get("event0_action_applied_in_static") is not False
        or scope.get("robot_pose_injection")
        != "paused_direct_joint_positions_with_readback"
        or scope.get("event0_integrated") is not False
        or scope.get("source_pose_materialized") is not False
        or scope.get("source_collider_matrices") != "formal_v2_analytic_override_only"
        or scope.get("link0_table_baseline_comparison")
        != baseline_evaluation["decision"]
        or scope.get("link0_table_geometry_audit") != geometry_evaluation["decision"]
        or scope.get("link0_table_mounting_alignment") != mounting_evaluation["decision"]
        or scope.get("fixed_mount_filter_applied") is not fixed_mount
        or scope.get("attachment") is not False
        or scope.get("close") is not False
        or scope.get("lift") is not False
        or scope.get("contact_observer") is not False
        or scope.get("g0_or_gate_evaluated") is not False
        or scope.get("post_reset_physics_steps_allowed") != 0
        or not isinstance(scope.get("post_reset_physics_advance"), Mapping)
        or scope["post_reset_physics_advance"].get("verified_zero") is not True
        or not isinstance(timeline, Mapping)
        or timeline.get("unchanged") is not True
        or timeline.get("baseline") != timeline.get("final")
        or collision_scope != verified_collision_scope
        or not isinstance(handoff_report, Mapping)
        or handoff_report.get("sha256") != handoff["sha256"]
        or handoff_report.get("formal_contract_sha256") != handoff["formal_contract_sha256"]
        or handoff_report.get("formal_provenance") != handoff["formal_provenance"]
        or handoff_report.get("event0_resolved_position_target_sha256")
        != handoff["event0"]["resolved_position_target_sha256"]
        or handoff_report.get("source_collider_closure_sha256")
        != handoff["source_collider_closure"]["sha256"]
        or handoff_report.get("fixed_mount_filter") != handoff.get("fixed_mount_filter")
    ):
        raise RuntimeError("formal_snapshot_static_child_scope_invalid")
    evaluation = _verify_projection_artifact(
        child.get("projection"),
        root=out_dir,
        collision_scope=active_screen_scope,
        expected_handoff=handoff,
        expected_margin_m=float(contract["aabb_numerical_margin_m"]),
    )
    if child.get("decision") != evaluation["decision"]:
        raise RuntimeError("formal_snapshot_static_child_decision_mismatch")
    verified = dict(child)
    verified["artifact_verification"] = {
        "projection": evaluation,
        "baseline_comparison": baseline_evaluation,
        "geometry_audit": geometry_evaluation,
        "mounting_alignment": mounting_evaluation,
        "active_screen_scope": active_screen_scope,
    }
    return verified


def _run_parent(args: argparse.Namespace) -> int:
    args.out_dir.mkdir(parents=True, mode=0o700)
    native = legacy._native_module()
    frozen = legacy.build_sealed_child_input(native.freeze_diagnostic_config(args.config))
    attestation = legacy._attestation_module()
    formal = _verify_formal_run(args.formal_run_dir)
    dependency_binding = formal["usd_dependency_preflight"]
    dependency_manifest = formal["usd_dependency_manifest"]
    closure = source_paths(
        frozen,
        fixed_mount_profile=formal["fixed_mount_profile"],
        usd_dependency_manifest=dependency_manifest,
    )
    source_before = attestation.capture_source_identity(closure)
    handoff = formal["handoff"]
    contract = build_contract(frozen, handoff)
    frozen_path = args.out_dir / "frozen_v7_config.json"
    handoff_path = args.out_dir / HANDOFF_NAME
    legacy._write_create_only(frozen_path, frozen)
    legacy._write_create_only(handoff_path, handoff)
    frozen_sha256 = legacy.sha256_file(frozen_path)
    handoff_sha256 = legacy.sha256_file(handoff_path)
    dependency_binding_path = None
    dependency_binding_sha256 = None
    if dependency_binding is not None:
        dependency_binding_path = args.out_dir / formal_runner.PREFLIGHT_BINDING_NAME
        legacy._write_create_only(dependency_binding_path, dependency_binding)
        dependency_binding_sha256 = legacy.sha256_file(dependency_binding_path)
    if handoff["sha256"] != contract["handoff_sha256"]:
        raise RuntimeError("formal_snapshot_static_handoff_publish_mismatch")
    request_path = args.out_dir / "static_screen_request.json"
    legacy._write_create_only(
        request_path,
        _request(
            contract=contract,
            frozen_path=frozen_path,
            frozen_sha256=frozen_sha256,
            handoff_path=handoff_path,
            handoff_file_sha256=handoff_sha256,
        ),
    )
    execution_request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    execution_request_path = args.out_dir / "execution_request.json"
    attestation.write_canonical_json(execution_request_path, execution_request)
    environment = attestation.sealed_child_environment(args.out_dir / "runtime")
    environment["NVIDIA_VISIBLE_DEVICES"] = "4"
    environment.pop("CUDA_VISIBLE_DEVICES", None)
    command = [
        str(legacy.FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--out-dir",
        str(args.out_dir),
        "--frozen-config",
        str(frozen_path),
        "--expected-frozen-config-sha256",
        frozen_sha256,
        "--handoff",
        str(handoff_path),
        "--expected-handoff-file-sha256",
        handoff_sha256,
        "--request",
        str(request_path),
        "--execution-request",
        str(execution_request_path),
    ]
    if dependency_binding_path is not None and dependency_binding_sha256 is not None:
        command.extend(
            (
                "--usd-dependency-preflight-binding",
                str(dependency_binding_path),
                "--expected-usd-dependency-preflight-binding-sha256",
                dependency_binding_sha256,
            )
        )
    stdout_path = args.out_dir / "child.stdout.log"
    stderr_path = args.out_dir / "child.stderr.log"
    child_pid = None
    child_returncode = None
    receipt = None
    source_after = None
    gpu = None
    verification_failure = None
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            child_pid = process.pid
            try:
                child_returncode = process.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                child_returncode = process.wait()
                raise RuntimeError("formal_snapshot_static_child_timeout") from exc
        gpu = legacy._kit_gpu_identity(stdout_path, environment)
        child = legacy._read_canonical_line(args.child_report_path)
        receipt = attestation._read_canonical_json(args.runtime_receipt_path)
        binding = attestation.execution_binding_for_request(
            execution_request, child_pid=child_pid
        )
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=binding
        )
        report = _verify_child_report(
            child,
            contract=contract,
            handoff=handoff,
            receipt_sha256=attestation.canonical_json_sha256(receipt),
            binding=binding,
            out_dir=args.out_dir,
            usd_dependency_preflight=dependency_binding,
        )
        if child_returncode != (2 if report["decision"] == "RUNTIME_BLOCKED" else 0):
            raise RuntimeError("formal_snapshot_static_child_exit_status_invalid")
        source_after = attestation.capture_source_identity(closure)
        if source_after != source_before:
            raise RuntimeError("formal_snapshot_static_source_changed_during_run")
        if dependency_binding is not None:
            expected_dependency_input = dependency_preflight.build_input(
                frozen, fixed_mount_profile=formal["fixed_mount_profile"]
            )
            verified_preflight = dependency_preflight.verify_preflight_binding(
                dependency_binding, expected_input=expected_dependency_input
            )
            if verified_preflight["manifest"] != dependency_manifest:
                raise RuntimeError(
                    "formal_snapshot_static_dependency_preflight_changed_during_run"
                )
        report["parent_verification"] = {
            "verified": True,
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "child_report_sha256": legacy.sha256_file(args.child_report_path),
            "runtime_receipt_sha256": attestation.canonical_json_sha256(receipt),
            "stdout_sha256": legacy.sha256_file(stdout_path),
            "stderr_sha256": legacy.sha256_file(stderr_path),
            "gpu": gpu,
            "usd_dependency_preflight_reverified": dependency_binding is not None,
        }
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        report = _blocked_report(None, exc, contract)
        report["parent_verification"] = {
            "verified": False,
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "gpu": gpu,
        }
    finally:
        if source_after is None:
            source_after = attestation.capture_source_identity(closure)
        manifest = {
            "schema_version": 1,
            "manifest_type": "formal_precontact_snapshot_static_screen_parent_v1",
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "command": command,
            "contract_sha256": static_screen.canonical_json_sha256(contract),
            "handoff_sha256": handoff["sha256"],
            "formal_provenance": handoff["formal_provenance"],
            "usd_dependency_preflight": dependency_binding,
            "source_before": source_before,
            "source_after": source_after,
            "sanitized_environment_sha256": attestation.canonical_json_sha256(
                dict(sorted(environment.items()))
            ),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "runtime_receipt_sha256": (
                attestation.canonical_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None
            ),
            "stdout_sha256": legacy.sha256_file(stdout_path) if stdout_path.is_file() else None,
            "stderr_sha256": legacy.sha256_file(stderr_path) if stderr_path.is_file() else None,
            "gpu": gpu,
            "verification_failure": verification_failure,
        }
    legacy._write_bound_report_and_manifest(
        report_path=args.out_dir / "report.json",
        report=report,
        manifest_path=args.out_dir / "run_manifest.json",
        manifest=manifest,
        manifest_writer=attestation.write_canonical_json,
    )
    print(
        f"formal precontact snapshot static screen decision={report['decision']} "
        f"out={args.out_dir / 'report.json'}",
        flush=True,
    )
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=legacy.DEFAULT_CONFIG)
    parser.add_argument("--formal-run-dir", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--frozen-config", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-frozen-config-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--handoff", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-handoff-file-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--usd-dependency-preflight-binding", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--expected-usd-dependency-preflight-binding-sha256",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.config.is_file() or not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("config must exist and timeout must be positive")
    child_inputs = (
        args.frozen_config,
        args.expected_frozen_config_sha256,
        args.handoff,
        args.expected_handoff_file_sha256,
        args.request,
        args.execution_request,
    )
    preflight_sealed = (
        args.usd_dependency_preflight_binding,
        args.expected_usd_dependency_preflight_binding_sha256,
    )
    if args.child:
        if (
            args.formal_run_dir is not None
            or any(value is None for value in child_inputs)
            or (preflight_sealed[0] is None) != (preflight_sealed[1] is None)
        ):
            parser.error("--child requires sealed inputs and cannot read the formal run directory")
        args.frozen_config = args.frozen_config.resolve()
        args.handoff = args.handoff.resolve()
        args.request = args.request.resolve()
        args.execution_request = args.execution_request.resolve()
        if (
            not args.out_dir.is_dir()
            or not all(
                path.is_file()
                for path in (args.frozen_config, args.handoff, args.request, args.execution_request)
            )
        ):
            parser.error("sealed child inputs must exist")
        _require_sha256(args.expected_frozen_config_sha256, field="frozen_config_sha256")
        _require_sha256(
            args.expected_handoff_file_sha256, field="handoff_file_sha256"
        )
        if args.usd_dependency_preflight_binding is not None:
            args.usd_dependency_preflight_binding = (
                args.usd_dependency_preflight_binding.resolve()
            )
            if not args.usd_dependency_preflight_binding.is_file():
                parser.error("sealed dependency preflight binding must exist")
            _require_sha256(
                args.expected_usd_dependency_preflight_binding_sha256,
                field="usd_dependency_preflight_binding_sha256",
            )
    elif (
        args.formal_run_dir is None
        or any(value is not None for value in child_inputs)
        or any(value is not None for value in preflight_sealed)
        or args.out_dir.exists()
    ):
        parser.error("parent requires --formal-run-dir, a new out-dir, and no sealed child options")
    else:
        args.formal_run_dir = args.formal_run_dir.resolve()
    args.child_report_path = args.out_dir / "child_report.json"
    args.runtime_receipt_path = args.out_dir / "runtime_receipt.json"
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.child:
        status = _run_child(args)
        if status != 0:
            os._exit(status)
        return 0
    try:
        return _run_parent(args)
    except BaseException as exc:
        args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        report = _blocked_report(None, exc, None)
        if not (args.out_dir / "report.json").exists():
            legacy._write_create_only(args.out_dir / "report.json", report)
        print(
            f"formal precontact snapshot static screen decision=RUNTIME_BLOCKED "
            f"out={args.out_dir / 'report.json'}",
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
