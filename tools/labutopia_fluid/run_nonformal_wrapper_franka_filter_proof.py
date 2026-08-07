#!/usr/bin/env python3
"""Run an isolated, non-formal A/B wrapper-to-Franka collision-filter proof.

This runner intentionally does not execute a controller, lift, G0, Gate 1, or
Gate 2. Its only possible positive result is an observation that the authored
collision-group treatment changed runtime contact behavior while the external
mesh remained a positive control.
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

from utils import nonformal_collision_filter_proof as proof


FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
DEFAULT_CONFIG = (
    REPO_ROOT / "config/diagnostic_level1_pour_native_empty_unbound_lift_v7.yaml"
).resolve()
HIDDEN_CUBE_OVERLAY = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_disable_hidden_cube_collision_v1.usda"
).resolve()
ATTESTATION_MODULE = (
    REPO_ROOT / "tools/labutopia_fluid/attest_isaac41_effective_runtime.py"
).resolve()
NATIVE_RUNNER_MODULE = (
    REPO_ROOT / "tools/labutopia_fluid/"
    "run_native_expert_empty_beaker_unbound_lift_probe.py"
).resolve()
RUNTIME_IMPLEMENTATION_MODULE = (
    REPO_ROOT / "tools/labutopia_fluid/nonformal_wrapper_franka_filter_runtime.py"
).resolve()
PROOF_MODULE = (REPO_ROOT / "utils/nonformal_collision_filter_proof.py").resolve()

AUTHORITY = "nonformal_wrapper_franka_collision_filter_proof_v1"
CLASSIFICATION = "NON_FORMAL_OBSERVATION_ONLY"
HAND_BODY_PATH = "/World/Franka/panda_hand"
SOURCE_MESH_PATH = "/World/beaker2/mesh"
WRAPPER_ROOT_PATH = "/World/beaker2/FluidSafeWrapperCanonical"
ENVIRONMENT_GROUP_PATH = "/World/ContactGraspCollisionGroups/Environment"
PROBE_GROUP_PATH = "/World/ContactGraspCollisionGroups/ABProbeFranka"
UNFILTERED_VARIANT = "scoped_unfiltered_qualification"
AUTHORED_VARIANT = "authored_filter_confirmation"
VARIANTS = (UNFILTERED_VARIANT, AUTHORED_VARIANT)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _write_create_only(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_json_bytes(dict(payload)))
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _read_canonical_line(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or b"\r" in payload:
        raise ValueError("filter_proof_canonical_input_invalid")
    try:
        value = json.loads(payload[:-1].decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("filter_proof_canonical_input_invalid") from exc
    if not isinstance(value, Mapping) or _canonical_json_bytes(dict(value)) != payload:
        raise ValueError("filter_proof_canonical_input_invalid")
    return dict(value)


def _require_sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"filter_proof_{field}_invalid")
    return value


def _native_module() -> Any:
    return importlib.import_module(
        "tools.labutopia_fluid.run_native_expert_empty_beaker_unbound_lift_probe"
    )


def _attestation_module() -> Any:
    return importlib.import_module(
        "tools.labutopia_fluid.attest_isaac41_effective_runtime"
    )


def _runtime_module() -> Any:
    return importlib.import_module(
        "tools.labutopia_fluid.nonformal_wrapper_franka_filter_runtime"
    )


def _frozen_diagnostic(frozen: Mapping[str, Any]) -> Mapping[str, Any]:
    config = frozen.get("config")
    if not isinstance(config, Mapping):
        raise ValueError("filter_proof_frozen_config_invalid")
    diagnostic = config.get("diagnostic")
    if not isinstance(diagnostic, Mapping):
        raise ValueError("filter_proof_frozen_diagnostic_invalid")
    return diagnostic


def build_sealed_child_input(frozen: Mapping[str, Any]) -> dict[str, Any]:
    """Remove non-JSON helpers while retaining the pre-bootstrap closure data."""
    if not isinstance(frozen, Mapping):
        raise ValueError("filter_proof_frozen_config_invalid")
    required = {
        "config",
        "canonical_bytes",
        "sha256",
        "source_path",
        "source_sha256",
        "production_path",
        "production_sha256",
        "production_projection_sha256",
        "local_franka",
        "local_scene",
    }
    if not required.issubset(frozen):
        raise ValueError("filter_proof_frozen_config_fields_invalid")
    config = frozen["config"]
    canonical_bytes = frozen["canonical_bytes"]
    if (
        not isinstance(config, Mapping)
        or not isinstance(canonical_bytes, bytes)
        or canonical_bytes != _canonical_json_bytes(dict(config))
        or hashlib.sha256(canonical_bytes).hexdigest() != frozen["sha256"]
    ):
        raise ValueError("filter_proof_frozen_config_integrity_invalid")
    sealed = {
        field: frozen[field]
        for field in (
            "config",
            "sha256",
            "source_path",
            "source_sha256",
            "production_path",
            "production_sha256",
            "production_projection_sha256",
            "local_franka",
            "local_scene",
        )
    }
    _frozen_diagnostic(sealed)
    return sealed


def build_filter_proof_contract(frozen: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the diagnostic to the exact v7 assets without importing Isaac."""
    if not isinstance(frozen, Mapping):
        raise ValueError("filter_proof_frozen_config_invalid")
    diagnostic = _frozen_diagnostic(frozen)
    config_sha256 = _require_sha256(frozen.get("sha256"), field="v7_config_sha256")
    local_scene = frozen.get("local_scene")
    local_franka = frozen.get("local_franka")
    if not isinstance(local_scene, Mapping) or not isinstance(local_franka, Mapping):
        raise ValueError("filter_proof_frozen_asset_invalid")
    local_scene_sha256 = _require_sha256(
        local_scene.get("sha256"), field="local_scene_sha256"
    )
    local_franka_sha256 = _require_sha256(
        local_franka.get("sha256"), field="local_franka_sha256"
    )
    hidden_cube = diagnostic.get("hidden_cube_treatment")
    if not isinstance(hidden_cube, Mapping):
        raise ValueError("filter_proof_hidden_cube_treatment_invalid")
    if hidden_cube.get("usd_path") != (
        "assets/chemistry_lab/lab_001_fluid_eval/"
        "lab_001_g0_disable_hidden_cube_collision_v1.usda"
    ):
        raise ValueError("filter_proof_hidden_cube_path_invalid")
    cube_overlay_sha256 = sha256_file(HIDDEN_CUBE_OVERLAY)
    if cube_overlay_sha256 != hidden_cube.get("sha256"):
        raise ValueError("filter_proof_hidden_cube_hash_mismatch")
    payload = {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "v7_config_sha256": config_sha256,
        "local_scene_sha256": local_scene_sha256,
        "local_franka_sha256": local_franka_sha256,
        "cube_overlay_sha256": cube_overlay_sha256,
        "selected_hand_body_path": HAND_BODY_PATH,
        "source_mesh_path": SOURCE_MESH_PATH,
        "wrapper_root_path": WRAPPER_ROOT_PATH,
        "variants": list(VARIANTS),
    }
    contract = {**payload, "sha256": proof.canonical_json_sha256(payload)}
    return proof.validate_filter_proof_contract(contract)


def build_variant_policy(variant: str, selected_hand_collider: str) -> dict[str, Any]:
    """Return the only permitted runtime topology edit for one variant."""
    if variant not in VARIANTS:
        raise ValueError("filter_proof_variant_invalid")
    if (
        not isinstance(selected_hand_collider, str)
        or not selected_hand_collider.startswith(f"{HAND_BODY_PATH}/")
        or selected_hand_collider.endswith("/")
        or "//" in selected_hand_collider
    ):
        raise ValueError("filter_proof_hand_collider_invalid")
    session_group_edit = None
    if variant == UNFILTERED_VARIANT:
        session_group_edit = {
            "environment_exclude_path": selected_hand_collider,
            "probe_group_path": PROBE_GROUP_PATH,
            "probe_group_include_path": selected_hand_collider,
        }
    return {
        "variant": variant,
        "selected_hand_collider": selected_hand_collider,
        "session_group_edit": session_group_edit,
    }


def source_paths(frozen: Mapping[str, Any]) -> tuple[Path, ...]:
    """Return the exact source and asset closure that the child must re-hash."""
    if not isinstance(frozen, Mapping):
        raise ValueError("filter_proof_frozen_config_invalid")
    diagnostic = _frozen_diagnostic(frozen)
    local_scene = frozen.get("local_scene")
    local_franka = frozen.get("local_franka")
    source_path = frozen.get("source_path")
    required_files = diagnostic.get("required_implementation_files")
    if (
        not isinstance(local_scene, Mapping)
        or not isinstance(local_franka, Mapping)
        or not isinstance(source_path, str)
        or not isinstance(required_files, list)
        or any(not isinstance(item, str) for item in required_files)
    ):
        raise ValueError("filter_proof_source_closure_invalid")
    candidates = {
        Path(__file__).resolve(),
        ATTESTATION_MODULE,
        NATIVE_RUNNER_MODULE,
        RUNTIME_IMPLEMENTATION_MODULE,
        PROOF_MODULE,
        Path(source_path).resolve(),
        HIDDEN_CUBE_OVERLAY,
        Path(str(local_scene.get("absolute_usd_path"))).resolve(),
        Path(str(local_franka.get("absolute_usd_path"))).resolve(),
        *{(REPO_ROOT / item).resolve() for item in required_files},
    }
    if any(not path.is_file() for path in candidates):
        raise ValueError("filter_proof_source_closure_missing")
    return tuple(sorted(candidates))


def _filter_request(
    *,
    contract: Mapping[str, Any],
    frozen_config_path: Path,
    frozen_config_sha256: str,
) -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "contract": dict(contract),
        "contract_sha256": proof.canonical_json_sha256(contract),
        "frozen_config_path": str(frozen_config_path),
        "frozen_config_sha256": frozen_config_sha256,
        "variants": list(VARIANTS),
    }


def _validate_filter_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("filter_proof_request_invalid")
    request = dict(value)
    expected = {
        "authority",
        "classification",
        "schema_version",
        "contract",
        "contract_sha256",
        "frozen_config_path",
        "frozen_config_sha256",
        "variants",
    }
    if set(request) != expected:
        raise ValueError("filter_proof_request_fields_invalid")
    if (
        request["authority"] != AUTHORITY
        or request["classification"] != CLASSIFICATION
        or request["schema_version"] != 1
        or request["variants"] != list(VARIANTS)
    ):
        raise ValueError("filter_proof_request_contract_invalid")
    contract = proof.validate_filter_proof_contract(request["contract"])
    if request["contract_sha256"] != proof.canonical_json_sha256(contract):
        raise ValueError("filter_proof_request_contract_sha256_invalid")
    frozen_config_path = request["frozen_config_path"]
    if not isinstance(frozen_config_path, str) or not Path(frozen_config_path).is_absolute():
        raise ValueError("filter_proof_request_frozen_config_path_invalid")
    return {
        **request,
        "contract": contract,
        "frozen_config_sha256": _require_sha256(
            request["frozen_config_sha256"], field="frozen_config_sha256"
        ),
    }


def _runtime_identity(
    receipt: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    frozen_config_sha256: str,
) -> dict[str, Any]:
    runtime_contract = receipt.get("runtime_contract")
    observed_runtime = receipt.get("observed_runtime")
    if not isinstance(runtime_contract, Mapping) or not isinstance(observed_runtime, Mapping):
        raise ValueError("filter_proof_runtime_identity_invalid")
    payload = {
        "runtime_contract": dict(runtime_contract),
        "observed_runtime": dict(observed_runtime),
        "contract_sha256": proof.canonical_json_sha256(contract),
        "frozen_config_sha256": frozen_config_sha256,
    }
    return {"payload": payload, "sha256": proof.canonical_json_sha256(payload)}


def _blocked_report(runtime: Mapping[str, Any] | None, exc: BaseException) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "nonformal_wrapper_franka_filter_proof_child_v1",
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "decision": "RUNTIME_BLOCKED",
        "runtime": dict(runtime) if isinstance(runtime, Mapping) else None,
        "fatal_error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _child_source_paths_from_frozen(frozen: Mapping[str, Any]) -> tuple[Path, ...]:
    return source_paths(frozen)


def _run_child(args: argparse.Namespace) -> int:
    app = None
    runtime: dict[str, Any] | None = None
    report_written = False
    try:
        frozen = _read_canonical_line(args.frozen_config)
        if sha256_file(args.frozen_config) != args.expected_frozen_config_sha256:
            raise RuntimeError("filter_proof_child_frozen_config_sha256_mismatch")
        filter_request = _validate_filter_request(
            _read_canonical_line(args.filter_request)
        )
        if filter_request["frozen_config_path"] != str(args.frozen_config):
            raise RuntimeError("filter_proof_child_frozen_config_path_mismatch")
        if filter_request["frozen_config_sha256"] != args.expected_frozen_config_sha256:
            raise RuntimeError("filter_proof_child_frozen_config_binding_mismatch")
        attestation = _attestation_module()
        execution_request = attestation._read_canonical_json(args.execution_request)
        source_closure = _child_source_paths_from_frozen(frozen)
        execution_request = attestation.verify_execution_request(
            execution_request, source_paths=source_closure
        )
        receipt, app = attestation.bootstrap_effective_runtime(
            execution_request=execution_request,
            source_paths=source_closure,
        )
        attestation.write_canonical_json(args.runtime_receipt_path, receipt)
        binding = attestation.execution_binding_for_request(
            execution_request, child_pid=os.getpid()
        )
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=binding
        )
        runtime_identity = _runtime_identity(
            receipt,
            contract=filter_request["contract"],
            frozen_config_sha256=args.expected_frozen_config_sha256,
        )
        runtime = {
            "receipt_path": str(args.runtime_receipt_path),
            "receipt_sha256": attestation.canonical_json_sha256(receipt),
            "execution_binding": binding,
            "execution_request_sha256": attestation.canonical_json_sha256(
                execution_request
            ),
            "runtime_identity": runtime_identity,
        }
        report = _runtime_module().run_filter_proof(
            app=app,
            out_dir=args.out_dir,
            frozen_config=frozen,
            contract=filter_request["contract"],
            runtime=runtime,
            build_variant_policy=build_variant_policy,
        )
        _write_create_only(args.child_report_path, report)
        report_written = True
    except BaseException as exc:
        report = _blocked_report(runtime, exc)
    finally:
        if app is not None:
            app.close()
    if not report_written and not args.child_report_path.exists():
        _write_create_only(args.child_report_path, report)
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def _verify_child_report(
    child_report: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    runtime_receipt_sha256: str,
    expected_binding: Mapping[str, Any],
) -> dict[str, Any]:
    if child_report.get("authority") != AUTHORITY:
        raise RuntimeError("filter_proof_child_authority_invalid")
    if child_report.get("classification") != CLASSIFICATION:
        raise RuntimeError("filter_proof_child_classification_invalid")
    if child_report.get("contract") != dict(contract):
        raise RuntimeError("filter_proof_child_contract_mismatch")
    runtime = child_report.get("runtime")
    if not isinstance(runtime, Mapping):
        raise RuntimeError("filter_proof_child_runtime_missing")
    if runtime.get("receipt_sha256") != runtime_receipt_sha256:
        raise RuntimeError("filter_proof_child_receipt_mismatch")
    if runtime.get("execution_binding") != dict(expected_binding):
        raise RuntimeError("filter_proof_child_execution_binding_mismatch")
    return dict(child_report)


def _run_parent(args: argparse.Namespace) -> int:
    args.out_dir.mkdir(parents=True, mode=0o700)
    native = _native_module()
    frozen = native.freeze_diagnostic_config(args.config)
    sealed_frozen = build_sealed_child_input(frozen)
    contract = build_filter_proof_contract(sealed_frozen)
    frozen_config_path = args.out_dir / "frozen_v7_config.json"
    _write_create_only(frozen_config_path, sealed_frozen)
    frozen_config_sha256 = sha256_file(frozen_config_path)
    if _read_canonical_line(frozen_config_path) != sealed_frozen:
        raise RuntimeError("filter_proof_frozen_config_publish_mismatch")
    filter_request = _filter_request(
        contract=contract,
        frozen_config_path=frozen_config_path,
        frozen_config_sha256=frozen_config_sha256,
    )
    filter_request_path = args.out_dir / "filter_request.json"
    _write_create_only(filter_request_path, filter_request)

    attestation = _attestation_module()
    closure = source_paths(sealed_frozen)
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
        str(FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--out-dir",
        str(args.out_dir),
        "--frozen-config",
        str(frozen_config_path),
        "--expected-frozen-config-sha256",
        frozen_config_sha256,
        "--filter-request",
        str(filter_request_path),
        "--execution-request",
        str(execution_request_path),
    ]
    stdout_path = args.out_dir / "child.stdout.log"
    stderr_path = args.out_dir / "child.stderr.log"
    child_pid = None
    child_returncode = None
    receipt = None
    verification_failure = None
    report: dict[str, Any]
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
                raise RuntimeError("filter_proof_child_timeout") from exc
        child_report = attestation._read_canonical_json(args.child_report_path)
        receipt = attestation._read_canonical_json(args.runtime_receipt_path)
        expected_binding = attestation.execution_binding_for_request(
            execution_request, child_pid=child_pid
        )
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=expected_binding
        )
        report = _verify_child_report(
            child_report,
            contract=contract,
            runtime_receipt_sha256=attestation.canonical_json_sha256(receipt),
            expected_binding=expected_binding,
        )
        expected_returncode = 2 if report.get("decision") == "RUNTIME_BLOCKED" else 0
        if child_returncode != expected_returncode:
            raise RuntimeError("filter_proof_child_exit_status_invalid")
        report["parent_verification"] = {
            "verified": True,
            "execution_request_sha256": attestation.canonical_json_sha256(
                execution_request
            ),
            "filter_request_sha256": sha256_file(filter_request_path),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "child_report_sha256": sha256_file(args.child_report_path),
            "runtime_receipt_sha256": attestation.canonical_json_sha256(receipt),
            "stdout_sha256": sha256_file(stdout_path),
            "stderr_sha256": sha256_file(stderr_path),
        }
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        report = _blocked_report(None, exc)
        report["contract"] = contract
        report["parent_verification"] = {
            "verified": False,
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "child_report_sha256": (
                sha256_file(args.child_report_path)
                if args.child_report_path.is_file()
                else None
            ),
            "runtime_receipt_sha256": (
                attestation.canonical_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None
            ),
            "stdout_sha256": sha256_file(stdout_path) if stdout_path.is_file() else None,
            "stderr_sha256": sha256_file(stderr_path) if stderr_path.is_file() else None,
        }
    finally:
        source_after = attestation.capture_source_identity(closure)
        manifest = {
            "schema_version": 1,
            "manifest_type": "nonformal_wrapper_franka_filter_proof_parent_v1",
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "command": command,
            "contract_sha256": proof.canonical_json_sha256(contract),
            "execution_request_sha256": attestation.canonical_json_sha256(
                execution_request
            ),
            "filter_request_sha256": sha256_file(filter_request_path),
            "frozen_config_sha256": frozen_config_sha256,
            "source_before": source_before,
            "source_after": source_after,
            "sanitized_environment_sha256": attestation.canonical_json_sha256(
                dict(sorted(environment.items()))
            ),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "stdout_sha256": sha256_file(stdout_path) if stdout_path.is_file() else None,
            "stderr_sha256": sha256_file(stderr_path) if stderr_path.is_file() else None,
            "runtime_receipt_sha256": (
                attestation.canonical_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None
            ),
            "child_report_sha256": (
                sha256_file(args.child_report_path)
                if args.child_report_path.is_file()
                else None
            ),
            "verification_failure": verification_failure,
        }
        attestation.write_canonical_json(args.out_dir / "run_manifest.json", manifest)
    _write_create_only(args.out_dir / "report.json", report)
    print(
        f"wrapper-franka filter proof decision={report['decision']} "
        f"out={args.out_dir / 'report.json'}",
        flush=True,
    )
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--frozen-config", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--expected-frozen-config-sha256", help=argparse.SUPPRESS
    )
    parser.add_argument("--filter-request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.out_dir = args.out_dir.resolve()
    if not args.config.is_file():
        parser.error("config must exist")
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("timeout-seconds must be positive")
    child_values = (
        args.frozen_config,
        args.expected_frozen_config_sha256,
        args.filter_request,
        args.execution_request,
    )
    if args.child:
        if any(value is None for value in child_values):
            parser.error("--child requires all sealed request paths")
        args.frozen_config = args.frozen_config.resolve()
        args.filter_request = args.filter_request.resolve()
        args.execution_request = args.execution_request.resolve()
        if (
            not args.out_dir.is_dir()
            or not args.frozen_config.is_file()
            or not args.filter_request.is_file()
            or not args.execution_request.is_file()
        ):
            parser.error("child sealed inputs and out-dir must exist")
        try:
            _require_sha256(
                args.expected_frozen_config_sha256,
                field="expected_frozen_config_sha256",
            )
        except ValueError:
            parser.error("expected-frozen-config-sha256 must be a SHA-256 digest")
        args.child_report_path = args.out_dir / "child_report.json"
        args.runtime_receipt_path = args.out_dir / "runtime_receipt.json"
    else:
        if any(value is not None for value in child_values):
            parser.error("sealed child options are child-only")
        if args.out_dir.exists():
            parser.error("out-dir must not exist")
        args.child_report_path = args.out_dir / "child_report.json"
        args.runtime_receipt_path = args.out_dir / "runtime_receipt.json"
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return _run_child(args) if args.child else _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
