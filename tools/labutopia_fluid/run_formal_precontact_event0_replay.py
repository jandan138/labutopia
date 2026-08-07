#!/usr/bin/env python3
"""Run the authorized v7-native diagnostic prefix through PickController event 0.

This sealed diagnostic stops immediately after applying event-0. It never
integrates that arm target and cannot authorize grasp, attachment, lift, a
gate, or Phase 3.
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

from tools.labutopia_fluid import run_nonformal_controller_static_collision_screen as static
from tools.labutopia_fluid import (
    run_formal_precontact_usd_dependency_preflight as dependency_preflight,
)
from utils import formal_precontact_event0_replay as replay
from utils import formal_precontact_event0_snapshot_replay as snapshot_replay


AUTHORITY = replay.AUTHORITY
CLASSIFICATION = "FORMAL_PRECONTACT_EVENT0_REPLAY_ONLY"
TRACE_NAME = "precontact_trace.json"
PREFLIGHT_BINDING_NAME = "usd_dependency_preflight.json"
RUNTIME_MODULE = (
    REPO_ROOT / "tools/labutopia_fluid/formal_precontact_event0_replay_runtime.py"
).resolve()
PURE_MODULE = (REPO_ROOT / "utils/formal_precontact_event0_replay.py").resolve()
SNAPSHOT_PURE_MODULE = (
    REPO_ROOT / "utils/formal_precontact_event0_snapshot_replay.py"
).resolve()
FIXED_MOUNT_PROFILE_DEFAULT = (
    REPO_ROOT / "config/formal_precontact_fixed_mount_filter_v1.json"
).resolve()


def _runtime_module() -> Any:
    return importlib.import_module("tools.labutopia_fluid.formal_precontact_event0_replay_runtime")


def _replay_module(snapshot_v2: bool) -> Any:
    return snapshot_replay if snapshot_v2 else replay


def _authority(snapshot_v2: bool, *, fixed_mount: bool = False) -> str:
    if fixed_mount:
        return snapshot_replay.FIXED_MOUNT_AUTHORITY
    return snapshot_replay.AUTHORITY if snapshot_v2 else AUTHORITY


def _classification(snapshot_v2: bool, *, fixed_mount: bool = False) -> str:
    if fixed_mount:
        return snapshot_replay.FIXED_MOUNT_CLASSIFICATION
    return snapshot_replay.CLASSIFICATION if snapshot_v2 else CLASSIFICATION


def _manifest_type(*, child: bool, snapshot_v2: bool, fixed_mount: bool = False) -> str:
    lane = "fixed_mount_snapshot_replay_v3" if fixed_mount else "snapshot_replay_v2" if snapshot_v2 else "replay_v1"
    return f"formal_precontact_event0_{lane}_{'child' if child else 'parent'}"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _require_sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"precontact_replay_{field}_invalid")
    return value


def _fixed_mount_profile_from_path(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if (
        resolved.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(REPO_ROOT)
    ):
        raise ValueError("precontact_replay_fixed_mount_profile_invalid")
    try:
        raw = json.loads(resolved.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("precontact_replay_fixed_mount_profile_invalid") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("precontact_replay_fixed_mount_profile_invalid")
    profile = {
        **dict(raw),
        "profile_path": str(resolved.relative_to(REPO_ROOT)),
        "profile_sha256": static.sha256_file(resolved),
    }
    try:
        return snapshot_replay.validate_fixed_mount_profile(profile)
    except ValueError as exc:
        raise ValueError("precontact_replay_fixed_mount_profile_invalid") from exc


def _fixed_mount_profile_from_contract(contract: Mapping[str, Any]) -> dict[str, Any] | None:
    if contract.get("authority") != snapshot_replay.FIXED_MOUNT_AUTHORITY:
        return None
    profile = contract.get("fixed_mount_profile")
    try:
        return snapshot_replay.validate_fixed_mount_profile(profile)
    except ValueError as exc:
        raise ValueError("precontact_replay_fixed_mount_profile_invalid") from exc


def build_contract(
    frozen: Mapping[str, Any],
    *,
    snapshot_v2: bool = False,
    fixed_mount_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    diagnostic = static._frozen_diagnostic(frozen)
    local_scene = frozen.get("local_scene")
    local_franka = frozen.get("local_franka")
    native = static._native_module()
    pre_roll_steps = native.g0_source_settle_pre_roll_steps(diagnostic)
    if (
        not isinstance(local_scene, Mapping)
        or not isinstance(local_franka, Mapping)
        or type(pre_roll_steps) is not int
        or pre_roll_steps <= 0
        or diagnostic.get("protocol_id") != native.V7_PROTOCOL_ID
        or diagnostic.get("physics_dt") != 1.0 / 600.0
    ):
        raise ValueError("precontact_replay_contract_invalid")
    if fixed_mount_profile is not None:
        if not snapshot_v2:
            raise ValueError("precontact_replay_fixed_mount_requires_snapshot")
        return snapshot_replay.build_fixed_mount_contract(
            pre_roll_steps=pre_roll_steps,
            v7_config_sha256=_require_sha256(frozen.get("sha256"), field="config_sha256"),
            local_scene_sha256=_require_sha256(local_scene.get("sha256"), field="scene_sha256"),
            local_franka_sha256=_require_sha256(local_franka.get("sha256"), field="franka_sha256"),
            hidden_cube_overlay_sha256=static.sha256_file(static.HIDDEN_CUBE_OVERLAY),
            fixed_mount_profile=fixed_mount_profile,
        )
    if snapshot_v2:
        return snapshot_replay.build_contract(
            pre_roll_steps=pre_roll_steps,
            v7_config_sha256=_require_sha256(frozen.get("sha256"), field="config_sha256"),
            local_scene_sha256=_require_sha256(local_scene.get("sha256"), field="scene_sha256"),
            local_franka_sha256=_require_sha256(local_franka.get("sha256"), field="franka_sha256"),
            hidden_cube_overlay_sha256=static.sha256_file(static.HIDDEN_CUBE_OVERLAY),
        )
    payload = {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "pre_roll_steps": pre_roll_steps,
        "transition_count": 6,
        "v7_config_sha256": _require_sha256(frozen.get("sha256"), field="config_sha256"),
        "local_scene_sha256": _require_sha256(local_scene.get("sha256"), field="scene_sha256"),
        "local_franka_sha256": _require_sha256(local_franka.get("sha256"), field="franka_sha256"),
        "hidden_cube_overlay_sha256": static.sha256_file(static.HIDDEN_CUBE_OVERLAY),
        "forbidden_operations": [
            "close",
            "attachment",
            "lift",
            "contact_observer",
            "phase3",
            "gate",
        ],
    }
    return {**payload, "sha256": replay.canonical_json_sha256(payload)}


def source_paths(
    frozen: Mapping[str, Any],
    *,
    snapshot_v2: bool = False,
    fixed_mount_profile: Mapping[str, Any] | None = None,
    usd_dependency_manifest: Mapping[str, Any] | None = None,
) -> tuple[Path, ...]:
    profile = (
        None
        if fixed_mount_profile is None
        else snapshot_replay.validate_fixed_mount_profile(fixed_mount_profile)
    )
    if profile is not None and not snapshot_v2:
        raise ValueError("precontact_replay_fixed_mount_requires_snapshot")
    base_paths = set(static.source_paths(frozen))
    extra_paths = static._python_import_paths(
        [
            "tools/labutopia_fluid/run_formal_precontact_event0_replay.py",
            "tools/labutopia_fluid/formal_precontact_event0_replay_runtime.py",
            "utils/formal_precontact_event0_replay.py",
        ]
    )
    paths = {
        Path(__file__).resolve(),
        RUNTIME_MODULE,
        PURE_MODULE,
        *([SNAPSHOT_PURE_MODULE] if snapshot_v2 else []),
        *base_paths,
        *extra_paths,
    }
    if profile is not None:
        if usd_dependency_manifest is None:
            raise ValueError("precontact_replay_fixed_mount_dependency_closure_missing")
        profile_path = (REPO_ROOT / profile["profile_path"]).resolve()
        overlay_path = (REPO_ROOT / profile["filter"]["overlay_path"]).resolve()
        if (
            profile_path.is_symlink()
            or overlay_path.is_symlink()
            or not profile_path.is_file()
            or not overlay_path.is_file()
            or static.sha256_file(profile_path) != profile["profile_sha256"]
            or static.sha256_file(overlay_path) != profile["filter"]["overlay_sha256"]
        ):
            raise ValueError("precontact_replay_fixed_mount_profile_binding_invalid")
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
        raise ValueError("precontact_replay_dependency_closure_unexpected")
    if any(not path.is_file() or not path.is_relative_to(REPO_ROOT) for path in paths):
        raise ValueError("precontact_replay_source_closure_invalid")
    return tuple(sorted(paths))


def _request(
    contract: Mapping[str, Any],
    frozen_path: Path,
    frozen_sha256: str,
    *,
    snapshot_v2: bool,
    fixed_mount: bool = False,
) -> dict[str, Any]:
    contract_module = _replay_module(snapshot_v2)
    return {
        "authority": _authority(snapshot_v2, fixed_mount=fixed_mount),
        "classification": _classification(snapshot_v2, fixed_mount=fixed_mount),
        "schema_version": 3 if fixed_mount else 2 if snapshot_v2 else 1,
        "contract": dict(contract),
        "contract_sha256": contract_module.canonical_json_sha256(contract),
        "frozen_config_path": str(frozen_path),
        "frozen_config_sha256": frozen_sha256,
    }


def _validate_request_unbootstrapped(
    value: Any, *, snapshot_v2: bool, fixed_mount: bool = False
) -> dict[str, Any]:
    contract_module = _replay_module(snapshot_v2)
    if (
        (fixed_mount and not snapshot_v2)
        or not isinstance(value, Mapping)
        or set(value)
        != {
            "authority",
            "classification",
            "schema_version",
            "contract",
            "contract_sha256",
            "frozen_config_path",
            "frozen_config_sha256",
        }
        or value.get("authority") != _authority(snapshot_v2, fixed_mount=fixed_mount)
        or value.get("classification")
        != _classification(snapshot_v2, fixed_mount=fixed_mount)
        or value.get("schema_version") != (3 if fixed_mount else 2 if snapshot_v2 else 1)
        or not isinstance(value.get("contract"), Mapping)
        or value.get("contract_sha256")
        != contract_module.canonical_json_sha256(value["contract"])
        or not isinstance(value.get("frozen_config_path"), str)
        or not Path(value["frozen_config_path"]).is_absolute()
    ):
        raise ValueError("precontact_replay_request_invalid")
    return {
        **dict(value),
        "contract": dict(value["contract"]),
        "frozen_config_sha256": _require_sha256(value["frozen_config_sha256"], field="frozen_config_sha256"),
    }


def _blocked_report(
    runtime: Mapping[str, Any] | None,
    exc: BaseException,
    contract: Mapping[str, Any] | None,
    *,
    snapshot_v2: bool = False,
    fixed_mount: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 3 if fixed_mount else 2 if snapshot_v2 else 1,
        "manifest_type": _manifest_type(
            child=True, snapshot_v2=snapshot_v2, fixed_mount=fixed_mount
        ),
        "authority": _authority(snapshot_v2, fixed_mount=fixed_mount),
        "classification": _classification(snapshot_v2, fixed_mount=fixed_mount),
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
    fixed_mount = False
    try:
        frozen = static._read_canonical_line(args.frozen_config)
        if static.sha256_file(args.frozen_config) != args.expected_frozen_config_sha256:
            raise RuntimeError("precontact_replay_frozen_config_sha256_mismatch")
        raw_request = static._read_canonical_line(args.request)
        fixed_mount = (
            args.snapshot_v2
            and isinstance(raw_request.get("contract"), Mapping)
            and raw_request["contract"].get("authority")
            == snapshot_replay.FIXED_MOUNT_AUTHORITY
        )
        request = _validate_request_unbootstrapped(
            raw_request, snapshot_v2=args.snapshot_v2, fixed_mount=fixed_mount
        )
        contract = request["contract"]
        fixed_mount_profile = _fixed_mount_profile_from_contract(contract)
        if fixed_mount != (fixed_mount_profile is not None):
            raise RuntimeError("precontact_replay_fixed_mount_contract_invalid")
        dependency_binding = None
        dependency_manifest = None
        if fixed_mount:
            if (
                args.usd_dependency_preflight_binding is None
                or args.expected_usd_dependency_preflight_binding_sha256 is None
            ):
                raise RuntimeError("precontact_replay_dependency_preflight_missing")
            if (
                static.sha256_file(args.usd_dependency_preflight_binding)
                != args.expected_usd_dependency_preflight_binding_sha256
            ):
                raise RuntimeError("precontact_replay_dependency_preflight_sha256_mismatch")
            expected_input = dependency_preflight.build_input(
                frozen, fixed_mount_profile=fixed_mount_profile
            )
            verified_preflight = dependency_preflight.verify_preflight_binding(
                static._read_canonical_line(args.usd_dependency_preflight_binding),
                expected_input=expected_input,
            )
            dependency_binding = verified_preflight["binding"]
            dependency_manifest = verified_preflight["manifest"]
        elif (
            args.usd_dependency_preflight_binding is not None
            or args.expected_usd_dependency_preflight_binding_sha256 is not None
        ):
            raise RuntimeError("precontact_replay_dependency_preflight_unexpected")
        if (
            request["frozen_config_path"] != str(args.frozen_config)
            or request["frozen_config_sha256"] != args.expected_frozen_config_sha256
        ):
            raise RuntimeError("precontact_replay_child_request_binding_invalid")
        attestation = static._attestation_module()
        execution_request = attestation._read_canonical_json(args.execution_request)
        closure = source_paths(
            frozen,
            snapshot_v2=args.snapshot_v2,
            fixed_mount_profile=fixed_mount_profile,
            usd_dependency_manifest=dependency_manifest,
        )
        execution_request = attestation.verify_execution_request(execution_request, source_paths=closure)
        receipt, app = attestation.bootstrap_effective_runtime(
            execution_request=execution_request, source_paths=closure
        )
        attestation.write_canonical_json(args.runtime_receipt_path, receipt)
        binding = attestation.execution_binding_for_request(execution_request, child_pid=os.getpid())
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        if contract != build_contract(
            frozen,
            snapshot_v2=args.snapshot_v2,
            fixed_mount_profile=fixed_mount_profile,
        ):
            raise RuntimeError("precontact_replay_child_contract_mismatch")
        runtime = {
            "receipt_sha256": attestation.canonical_json_sha256(receipt),
            "execution_binding": binding,
            "runtime_identity": static._runtime_identity(
                receipt,
                contract=contract,
                frozen_config_sha256=args.expected_frozen_config_sha256,
            ),
        }
        report = _runtime_module().run_precontact_event0_replay(
            app=app,
            out_dir=args.out_dir,
            frozen_config=frozen,
            contract=contract,
            runtime=runtime,
        )
        if dependency_binding is not None:
            report["usd_dependency_preflight"] = dependency_binding
        source_after = attestation.capture_source_identity(closure)
        source_after_sha256 = attestation.canonical_json_sha256(source_after)
        if source_after_sha256 != execution_request["source_sha256"]:
            raise RuntimeError("precontact_replay_child_source_changed_during_run")
        report["runtime"]["source_after_sha256"] = source_after_sha256
        static._write_create_only(args.child_report_path, report)
        written = True
    except BaseException as exc:
        report = _blocked_report(
            runtime,
            exc,
            contract,
            snapshot_v2=args.snapshot_v2,
            fixed_mount=fixed_mount,
        )
        if not args.child_report_path.exists():
            static._write_create_only(args.child_report_path, report)
            written = True
    finally:
        if app is not None and isinstance(report, Mapping) and report.get("decision") != "RUNTIME_BLOCKED":
            app.close()
    if report is None:
        raise RuntimeError("precontact_replay_child_report_unavailable")
    if not written and not args.child_report_path.exists():
        static._write_create_only(args.child_report_path, report)
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def _verify_trace_artifact(
    value: Any,
    *,
    root: Path,
    contract: Mapping[str, Any],
    snapshot_v2: bool,
    fixed_mount: bool = False,
) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"path", "sha256"}
        or value.get("path") != TRACE_NAME
    ):
        raise RuntimeError("precontact_replay_trace_artifact_invalid")
    path = root / TRACE_NAME
    if path.is_symlink() or not path.is_file() or static.sha256_file(path) != value.get("sha256"):
        raise RuntimeError("precontact_replay_trace_artifact_invalid")
    try:
        raw = path.read_bytes()
        trace = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("precontact_replay_trace_artifact_invalid") from exc
    if not isinstance(trace, Mapping) or raw != _canonical_bytes(dict(trace)):
        raise RuntimeError("precontact_replay_trace_artifact_invalid")
    contract_module = _replay_module(snapshot_v2)
    evaluator = (
        contract_module.evaluate_precontact_event0_snapshot_replay
        if snapshot_v2
        else contract_module.evaluate_precontact_event0_replay
    )
    evaluation = evaluator(trace, contract)
    return {"trace": trace, "evaluation": evaluation}


def _verify_child_report(
    child: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    receipt_sha256: str,
    binding: Mapping[str, Any],
    out_dir: Path,
    snapshot_v2: bool,
    fixed_mount: bool = False,
    usd_dependency_preflight: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract_module = _replay_module(snapshot_v2)
    if (
        child.get("authority") != _authority(snapshot_v2, fixed_mount=fixed_mount)
        or child.get("classification")
        != _classification(snapshot_v2, fixed_mount=fixed_mount)
        or child.get("contract") != dict(contract)
        or not isinstance(child.get("runtime"), Mapping)
        or child["runtime"].get("receipt_sha256") != receipt_sha256
        or child["runtime"].get("execution_binding") != dict(binding)
        or (
            fixed_mount
            and (
                usd_dependency_preflight is None
                or child.get("usd_dependency_preflight") != dict(usd_dependency_preflight)
            )
        )
        or (not fixed_mount and child.get("usd_dependency_preflight") is not None)
    ):
        raise RuntimeError("precontact_replay_child_contract_invalid")
    if child.get("decision") == "RUNTIME_BLOCKED":
        return dict(child)
    if child["runtime"].get("source_after_sha256") != binding.get("source_sha256"):
        raise RuntimeError("precontact_replay_child_source_identity_invalid")
    if child.get("decision") not in {
        contract_module.PASS,
        contract_module.NO_GO,
        contract_module.SAFETY_ABORT,
    }:
        raise RuntimeError("precontact_replay_child_decision_invalid")
    trace_verification = _verify_trace_artifact(
        child.get("trace"),
        root=out_dir,
        contract=contract,
        snapshot_v2=snapshot_v2,
        fixed_mount=fixed_mount,
    )
    if child.get("evaluation") != trace_verification["evaluation"] or child["decision"] != trace_verification["evaluation"]["decision"]:
        raise RuntimeError("precontact_replay_child_trace_evaluation_invalid")
    scope = child.get("scope")
    if (
        not isinstance(scope, Mapping)
        or scope.get("close_command_emitted") is not False
        or scope.get("lift_command_emitted") is not False
        or scope.get("attachment_invocation_count") != 0
        or scope.get("contact_observer_invocation_count") != 0
        or scope.get("phase3_or_gate_evaluated") is not False
        or scope.get("event0_integrated") is not False
        or scope.get("event0_action_applied")
        != (child.get("decision") == contract_module.PASS)
    ):
        raise RuntimeError("precontact_replay_child_scope_invalid")
    verified = dict(child)
    verified["artifact_verification"] = {
        "trace_sha256": child["trace"]["sha256"],
        "evaluation": trace_verification["evaluation"],
    }
    return verified


def _run_parent(args: argparse.Namespace) -> int:
    args.out_dir.mkdir(parents=True, mode=0o700)
    native = static._native_module()
    frozen = static.build_sealed_child_input(native.freeze_diagnostic_config(args.config))
    fixed_mount_profile = (
        None
        if args.fixed_mount_profile is None
        else _fixed_mount_profile_from_path(args.fixed_mount_profile)
    )
    fixed_mount = fixed_mount_profile is not None
    dependency_input = None
    dependency_binding = None
    dependency_manifest = None
    if fixed_mount:
        dependency_input = dependency_preflight.build_input(
            frozen, fixed_mount_profile=fixed_mount_profile
        )
        verified_preflight = dependency_preflight.bind_preflight_run(
            args.usd_dependency_preflight_dir, expected_input=dependency_input
        )
        dependency_binding = verified_preflight["binding"]
        dependency_manifest = verified_preflight["manifest"]
    contract_module = _replay_module(args.snapshot_v2)
    contract = build_contract(
        frozen,
        snapshot_v2=args.snapshot_v2,
        fixed_mount_profile=fixed_mount_profile,
    )
    frozen_path = args.out_dir / "frozen_v7_config.json"
    static._write_create_only(frozen_path, frozen)
    frozen_sha256 = static.sha256_file(frozen_path)
    dependency_binding_path = None
    dependency_binding_sha256 = None
    if dependency_binding is not None:
        dependency_binding_path = args.out_dir / PREFLIGHT_BINDING_NAME
        static._write_create_only(dependency_binding_path, dependency_binding)
        dependency_binding_sha256 = static.sha256_file(dependency_binding_path)
    request_path = args.out_dir / "replay_request.json"
    static._write_create_only(
        request_path,
        _request(
            contract,
            frozen_path,
            frozen_sha256,
            snapshot_v2=args.snapshot_v2,
            fixed_mount=fixed_mount,
        ),
    )
    attestation = static._attestation_module()
    closure = source_paths(
        frozen,
        snapshot_v2=args.snapshot_v2,
        fixed_mount_profile=fixed_mount_profile,
        usd_dependency_manifest=dependency_manifest,
    )
    source_before = attestation.capture_source_identity(closure)
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
        str(static.FORMAL_ISAAC41_PYTHON), "-I", "-B", str(Path(__file__).resolve()), "--child",
        "--out-dir", str(args.out_dir), "--frozen-config", str(frozen_path),
        "--expected-frozen-config-sha256", frozen_sha256, "--request", str(request_path),
        "--execution-request", str(execution_request_path),
    ]
    if args.snapshot_v2:
        command.append("--snapshot-v2")
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
    verification_failure = None
    source_after = None
    gpu = None
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(command, cwd=REPO_ROOT, env=environment, stdout=stdout, stderr=stderr, start_new_session=True)
            child_pid = process.pid
            try:
                child_returncode = process.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                child_returncode = process.wait()
                raise RuntimeError("precontact_replay_child_timeout") from exc
        gpu = static._kit_gpu_identity(stdout_path, environment)
        child = attestation._read_canonical_json(args.child_report_path)
        receipt = attestation._read_canonical_json(args.runtime_receipt_path)
        binding = attestation.execution_binding_for_request(execution_request, child_pid=child_pid)
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        report = _verify_child_report(
            child,
            contract=contract,
            receipt_sha256=attestation.canonical_json_sha256(receipt),
            binding=binding,
            out_dir=args.out_dir,
            snapshot_v2=args.snapshot_v2,
            fixed_mount=fixed_mount,
            usd_dependency_preflight=dependency_binding,
        )
        if child_returncode != (2 if report["decision"] == "RUNTIME_BLOCKED" else 0):
            raise RuntimeError("precontact_replay_child_exit_status_invalid")
        source_after = attestation.capture_source_identity(closure)
        if source_after != source_before:
            raise RuntimeError("precontact_replay_source_changed_during_run")
        if dependency_binding is not None:
            verified_preflight = dependency_preflight.verify_preflight_binding(
                dependency_binding, expected_input=dependency_input
            )
            if verified_preflight["manifest"] != dependency_manifest:
                raise RuntimeError("precontact_replay_dependency_preflight_changed_during_run")
        report["parent_verification"] = {
            "verified": True,
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "runtime_receipt_sha256": attestation.canonical_json_sha256(receipt),
            "child_report_sha256": static.sha256_file(args.child_report_path),
            "stdout_sha256": static.sha256_file(stdout_path),
            "stderr_sha256": static.sha256_file(stderr_path),
            "gpu": gpu,
            "usd_dependency_preflight_reverified": dependency_binding is not None,
        }
    except BaseException as exc:
        verification_failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        report = _blocked_report(
            None,
            exc,
            contract,
            snapshot_v2=args.snapshot_v2,
            fixed_mount=fixed_mount,
        )
        report["parent_verification"] = {"verified": False, "child_pid": child_pid, "child_returncode": child_returncode, "gpu": gpu}
    finally:
        if source_after is None:
            source_after = attestation.capture_source_identity(closure)
        manifest = {
            "schema_version": 3 if fixed_mount else 2 if args.snapshot_v2 else 1,
            "manifest_type": _manifest_type(
                child=False, snapshot_v2=args.snapshot_v2, fixed_mount=fixed_mount
            ),
            "authority": _authority(args.snapshot_v2, fixed_mount=fixed_mount),
            "classification": _classification(args.snapshot_v2, fixed_mount=fixed_mount),
            "command": command,
            "contract_sha256": contract_module.canonical_json_sha256(contract),
            "usd_dependency_preflight": dependency_binding,
            "source_before": source_before,
            "source_after": source_after,
            "sanitized_environment_sha256": attestation.canonical_json_sha256(dict(sorted(environment.items()))),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "runtime_receipt_sha256": attestation.canonical_json_sha256(receipt) if isinstance(receipt, Mapping) else None,
            "stdout_sha256": static.sha256_file(stdout_path) if stdout_path.is_file() else None,
            "stderr_sha256": static.sha256_file(stderr_path) if stderr_path.is_file() else None,
            "gpu": gpu,
            "verification_failure": verification_failure,
        }
    static._write_bound_report_and_manifest(
        report_path=args.out_dir / "report.json", report=report,
        manifest_path=args.out_dir / "run_manifest.json", manifest=manifest,
        manifest_writer=attestation.write_canonical_json,
    )
    lane = " fixed-mount snapshot" if fixed_mount else " snapshot" if args.snapshot_v2 else ""
    print(f"precontact event0{lane} replay decision={report['decision']} out={args.out_dir / 'report.json'}", flush=True)
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=static.DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument(
        "--snapshot-v2",
        action="store_true",
        help="capture the formal event-0 source-collider closure required for static projection",
    )
    parser.add_argument(
        "--fixed-mount-profile",
        type=Path,
        help="formal-only fixed link0/table mount profile; requires --snapshot-v2",
    )
    parser.add_argument(
        "--usd-dependency-preflight-dir",
        type=Path,
        help="passing sealed USD dependency-preflight run; required for fixed-mount replay",
    )
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--frozen-config", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-frozen-config-sha256", help=argparse.SUPPRESS)
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
    if args.fixed_mount_profile is not None:
        args.fixed_mount_profile = args.fixed_mount_profile.resolve()
    if args.usd_dependency_preflight_dir is not None:
        args.usd_dependency_preflight_dir = args.usd_dependency_preflight_dir.resolve()
    if not args.config.is_file() or not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("config must exist and timeout must be positive")
    sealed = (args.frozen_config, args.expected_frozen_config_sha256, args.request, args.execution_request)
    preflight_sealed = (
        args.usd_dependency_preflight_binding,
        args.expected_usd_dependency_preflight_binding_sha256,
    )
    if args.child:
        if (
            args.fixed_mount_profile is not None
            or args.usd_dependency_preflight_dir is not None
            or any(value is None for value in sealed)
            or (preflight_sealed[0] is None) != (preflight_sealed[1] is None)
        ):
            parser.error("--child requires all sealed inputs")
        args.frozen_config = args.frozen_config.resolve()
        args.request = args.request.resolve()
        args.execution_request = args.execution_request.resolve()
        if not args.out_dir.is_dir() or not all(path.is_file() for path in (args.frozen_config, args.request, args.execution_request)):
            parser.error("sealed child inputs must exist")
        _require_sha256(args.expected_frozen_config_sha256, field="frozen_config_sha256")
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
        any(value is not None for value in sealed)
        or any(value is not None for value in preflight_sealed)
        or args.out_dir.exists()
        or (args.fixed_mount_profile is not None and not args.snapshot_v2)
    ):
        parser.error("parent out-dir must be new and sealed options are child-only")
    elif args.fixed_mount_profile is not None and not args.fixed_mount_profile.is_file():
        parser.error("fixed mount profile must exist")
    elif (args.fixed_mount_profile is not None) != (
        args.usd_dependency_preflight_dir is not None
    ):
        parser.error("fixed-mount replay requires exactly one dependency preflight run")
    elif (
        args.usd_dependency_preflight_dir is not None
        and not args.usd_dependency_preflight_dir.is_dir()
    ):
        parser.error("dependency preflight run must exist")
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
        fixed_mount = args.fixed_mount_profile is not None
        report = _blocked_report(
            None,
            exc,
            None,
            snapshot_v2=args.snapshot_v2,
            fixed_mount=fixed_mount,
        )
        if not (args.out_dir / "report.json").exists():
            static._write_create_only(args.out_dir / "report.json", report)
        lane = " fixed-mount snapshot" if fixed_mount else " snapshot" if args.snapshot_v2 else ""
        print(f"precontact event0{lane} replay decision=RUNTIME_BLOCKED out={args.out_dir / 'report.json'}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
