#!/usr/bin/env python3
"""Run a sealed static composition proof for the finite-offset calibration overlay.

This is a nonauthorizing USD-authoring treatment. It does not construct a
physics world, advance simulation, resolve native effective offsets, issue a
clearance certificate, or authorize G0 or Phase 3.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import secrets
import signal
import subprocess
import sys
import time
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils import nonformal_authored_offset_overlay_composition as composition


FORMAL_ISAAC41_PYTHON = Path(
    "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
    "embodied-eval-os-sim-isaacsim41-genmanip-py310/bin/python"
)
FORMAL_ISAAC41_PREFIX = FORMAL_ISAAC41_PYTHON.parent.parent
EXPECTED_TORCH_CUDA_VERSION = "12.1"
DEFAULT_ASSET = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_level1_pour_interndata_contact_grasp_rest_offset_zero_step600_layout_v1.usda"
)
ROBOT_ASSET = REPO_ROOT / "assets/robots/Franka.usd"
HIDDEN_CUBE_OVERLAY = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_disable_hidden_cube_collision_v1.usda"
)
CALIBRATION_OVERLAY = (
    REPO_ROOT
    / "assets/chemistry_lab/lab_001_fluid_eval/"
    "lab_001_g0_finite_target_offsets_calibration_v2.usda"
)
KIT_PROFILE_PATH = (
    REPO_ROOT
    / "tools/labutopia_fluid/profiles/"
    "isaac41_authored_offset_overlay_composition_experimental.kit"
)
RUNTIME_MODULE = (
    REPO_ROOT / "tools/labutopia_fluid/nonformal_authored_offset_overlay_composition_runtime.py"
)
PURE_MODULE = REPO_ROOT / "utils/nonformal_authored_offset_overlay_composition.py"
DEPENDENCY_RESOLUTION_MODULE = REPO_ROOT / "utils/nonformal_usd_dependency_resolution.py"
ATTESTATION_MODULE = REPO_ROOT / "tools/labutopia_fluid/attest_isaac41_effective_runtime.py"

AUTHORITY = "nonauthorizing_authored_offset_overlay_composition_runner_v1"
CLASSIFICATION = composition.CLASSIFICATION
OVERLAY_PROFILE_ID = composition.OVERLAY_PROFILE_ID
PASS = composition.PASS
NO_GO = composition.NO_GO
RUNTIME_BLOCKED = "RUNTIME_BLOCKED"
REQUEST_BASENAME = "authored_offset_composition_request.json"
EXECUTION_REQUEST_BASENAME = "execution_request.json"
RUNTIME_RECEIPT_BASENAME = "runtime_receipt.json"
CHILD_REPORT_BASENAME = "child_report.json"
OBSERVATION_BASENAME = "authored_offset_composition_observation.json"
REPORT_BASENAME = "report.json"
MANIFEST_BASENAME = "run_manifest.json"
STDOUT_BASENAME = "child.stdout.log"
STDERR_BASENAME = "child.stderr.log"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return composition.canonical_json_sha256(value)


def _attestation_json_sha256(value: Mapping[str, Any]) -> str:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    return attestation.canonical_json_sha256(value)


def _require_repo_regular(path: Path, *, field: str) -> Path:
    candidate = Path(path)
    if (
        candidate.is_symlink()
        or not candidate.is_file()
        or not candidate.is_relative_to(REPO_ROOT)
    ):
        raise ValueError(f"authored_offset_composition_{field}_invalid")
    return candidate.resolve()


def _artifact(path: Path) -> dict[str, str]:
    regular = _require_repo_regular(path, field="fixture_input")
    return {"path": str(regular), "sha256": _sha256_file(regular)}


def _overlay_profile() -> dict[str, Any]:
    stack = [
        {"id": OVERLAY_PROFILE_ID, **_artifact(CALIBRATION_OVERLAY)},
        {"id": "hidden_cube_collision_disable", **_artifact(HIDDEN_CUBE_OVERLAY)},
    ]
    return {
        "authority": composition.OVERLAY_PROFILE_AUTHORITY,
        "id": OVERLAY_PROFILE_ID,
        "overlay_stack": stack,
    }


def _kit_profile() -> dict[str, Any]:
    profile = _require_repo_regular(KIT_PROFILE_PATH, field="kit_profile")
    try:
        profile_text = profile.read_text(encoding="ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("authored_offset_composition_kit_profile_invalid") from exc
    if "pvd" in profile_text.lower():
        raise ValueError("authored_offset_composition_kit_profile_declares_pvd")
    return {
        "path": str(profile),
        "sha256": _sha256_file(profile),
        "pvd_extension_declared": False,
    }


def build_composition_request() -> dict[str, Any]:
    plan = composition.build_plan()
    overlay_profile = _overlay_profile()
    fixture = {
        "asset": _artifact(DEFAULT_ASSET),
        "robot_asset": _artifact(ROBOT_ASSET),
        "overlay_profile": overlay_profile,
        "overlay_profile_sha256": _canonical_sha256(overlay_profile),
    }
    payload = {
        "authority": AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "plan": plan,
        "plan_sha256": plan["sha256"],
        "fixture": fixture,
        "kit_profile": _kit_profile(),
        "authorization": dict(composition.AUTHORIZATION),
    }
    return {**payload, "sha256": _canonical_sha256(payload)}


def _validate_composition_request(value: Any) -> dict[str, Any]:
    expected = build_composition_request()
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise ValueError("authored_offset_composition_request_invalid")
    return expected


def source_paths() -> tuple[Path, ...]:
    """Return all repository inputs that are sealed before child bootstrap."""
    request = build_composition_request()
    paths = {
        Path(__file__),
        RUNTIME_MODULE,
        PURE_MODULE,
        DEPENDENCY_RESOLUTION_MODULE,
        ATTESTATION_MODULE,
        DEFAULT_ASSET,
        ROBOT_ASSET,
        KIT_PROFILE_PATH,
        *(Path(item["path"]) for item in request["fixture"]["overlay_profile"]["overlay_stack"]),
    }
    return tuple(sorted(_require_repo_regular(path, field="source_closure") for path in paths))


def expected_child_returncode(decision: str) -> int:
    if decision == RUNTIME_BLOCKED:
        return 2
    if decision in {PASS, NO_GO}:
        return 0
    raise ValueError("authored_offset_composition_child_decision_invalid")


def _collect_child_gpu_identity() -> dict[str, Any]:
    """Bind the GPU and driver used by the sealed Kit process."""
    import torch

    if os.environ.get("NVIDIA_VISIBLE_DEVICES") != "4" or "CUDA_VISIBLE_DEVICES" in os.environ:
        raise RuntimeError("authored_offset_composition_gpu_visibility_invalid")
    candidates = []
    try:
        for line in Path("/proc/self/maps").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) >= 6 and fields[-1].startswith("/"):
                path = Path(fields[-1])
                if path.name.startswith("libcuda.so") and path.is_file():
                    candidates.append(path)
    except OSError as exc:
        raise RuntimeError("authored_offset_composition_libcuda_maps_unavailable") from exc
    if not candidates:
        raise RuntimeError("authored_offset_composition_libcuda_unavailable")
    libcuda_path = sorted(set(candidates), key=str)[0]
    library = ctypes.CDLL(str(libcuda_path))

    def require_cuda(status: int, name: str) -> None:
        if status != 0:
            raise RuntimeError(f"authored_offset_composition_cuda_driver_error:{name}:{status}")

    require_cuda(library.cuInit(0), "cuInit")
    driver_version = ctypes.c_int()
    require_cuda(library.cuDriverGetVersion(ctypes.byref(driver_version)), "cuDriverGetVersion")
    device_count = ctypes.c_int()
    require_cuda(library.cuDeviceGetCount(ctypes.byref(device_count)), "cuDeviceGetCount")
    if device_count.value != 1:
        raise RuntimeError("authored_offset_composition_cuda_device_count_invalid")
    device = ctypes.c_int()
    require_cuda(library.cuDeviceGet(ctypes.byref(device), 0), "cuDeviceGet")
    name_buffer = ctypes.create_string_buffer(256)
    require_cuda(library.cuDeviceGetName(name_buffer, len(name_buffer), device), "cuDeviceGetName")
    uuid_buffer = (ctypes.c_ubyte * 16)()
    require_cuda(library.cuDeviceGetUuid(ctypes.byref(uuid_buffer), device), "cuDeviceGetUuid")
    pci_buffer = ctypes.create_string_buffer(32)
    require_cuda(library.cuDeviceGetPCIBusId(pci_buffer, len(pci_buffer), device), "cuDeviceGetPCIBusId")
    torch_path = Path(torch.__file__).resolve()
    torch_native_path = Path(torch._C.__file__).resolve()
    if (
        not torch_path.is_file()
        or not torch_native_path.is_file()
        or not torch_path.is_relative_to(FORMAL_ISAAC41_PREFIX)
        or not torch_native_path.is_relative_to(FORMAL_ISAAC41_PREFIX)
        or str(torch.version.cuda) != EXPECTED_TORCH_CUDA_VERSION
    ):
        raise RuntimeError("authored_offset_composition_torch_cuda_identity_invalid")
    device_name = name_buffer.value.decode("utf-8")
    device_uuid = bytes(uuid_buffer).hex()
    pci_bus_id = pci_buffer.value.decode("utf-8")
    if not device_name or not device_uuid or not pci_bus_id:
        raise RuntimeError("authored_offset_composition_cuda_device_identity_invalid")
    return {
        "authority": "nonauthorizing_authored_offset_overlay_gpu_identity_v1",
        "nvidia_visible_devices": "4",
        "cuda_visible_devices": None,
        "cuda_device_count": device_count.value,
        "cuda_device_0_name": device_name,
        "cuda_device_0_uuid": device_uuid,
        "cuda_device_0_pci_bus_id": pci_bus_id,
        "cuda_driver_api_version": driver_version.value,
        "torch_cuda_version": str(torch.version.cuda),
        "libcuda": {"path": str(libcuda_path), "sha256": _sha256_file(libcuda_path)},
        "torch": {"path": str(torch_path), "sha256": _sha256_file(torch_path)},
        "torch_native": {
            "path": str(torch_native_path),
            "sha256": _sha256_file(torch_native_path),
        },
    }


def _validate_child_gpu_identity(value: Any) -> dict[str, Any]:
    expected = {
        "authority",
        "nvidia_visible_devices",
        "cuda_visible_devices",
        "cuda_device_count",
        "cuda_device_0_name",
        "cuda_device_0_uuid",
        "cuda_device_0_pci_bus_id",
        "cuda_driver_api_version",
        "torch_cuda_version",
        "libcuda",
        "torch",
        "torch_native",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value.get("authority") != "nonauthorizing_authored_offset_overlay_gpu_identity_v1"
        or value.get("nvidia_visible_devices") != "4"
        or value.get("cuda_visible_devices") is not None
        or type(value.get("cuda_device_count")) is not int
        or value["cuda_device_count"] != 1
        or not isinstance(value.get("cuda_device_0_name"), str)
        or not value["cuda_device_0_name"]
        or not isinstance(value.get("cuda_device_0_uuid"), str)
        or len(value["cuda_device_0_uuid"]) != 32
        or any(character not in "0123456789abcdef" for character in value["cuda_device_0_uuid"])
        or not isinstance(value.get("cuda_device_0_pci_bus_id"), str)
        or not value["cuda_device_0_pci_bus_id"]
        or type(value.get("cuda_driver_api_version")) is not int
        or value["cuda_driver_api_version"] <= 0
        or value.get("torch_cuda_version") != EXPECTED_TORCH_CUDA_VERSION
    ):
        raise RuntimeError("authored_offset_composition_child_gpu_identity_invalid")
    normalized = {
        name: value[name]
        for name in (
            "authority",
            "nvidia_visible_devices",
            "cuda_visible_devices",
            "cuda_device_count",
            "cuda_device_0_name",
            "cuda_device_0_uuid",
            "cuda_device_0_pci_bus_id",
            "cuda_driver_api_version",
            "torch_cuda_version",
        )
    }
    for name in ("libcuda", "torch", "torch_native"):
        artifact = value[name]
        if (
            not isinstance(artifact, Mapping)
            or set(artifact) != {"path", "sha256"}
            or not isinstance(artifact.get("path"), str)
            or not artifact["path"].startswith("/")
            or not isinstance(artifact.get("sha256"), str)
        ):
            raise RuntimeError("authored_offset_composition_child_gpu_identity_invalid")
        path = Path(artifact["path"])
        if path.is_symlink() or not path.is_file() or _sha256_file(path) != artifact["sha256"]:
            raise RuntimeError("authored_offset_composition_child_gpu_identity_invalid")
        if name in {"torch", "torch_native"} and not path.is_relative_to(FORMAL_ISAAC41_PREFIX):
            raise RuntimeError("authored_offset_composition_child_gpu_identity_invalid")
        normalized[name] = {"path": str(path), "sha256": artifact["sha256"]}
    return normalized


def _runtime_error_report(
    error: BaseException,
    runtime: Mapping[str, Any] | None,
    request: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "decision": RUNTIME_BLOCKED,
        "request": dict(request) if isinstance(request, Mapping) else None,
        "runtime": dict(runtime) if isinstance(runtime, Mapping) else None,
        "fatal_error": {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        },
    }


def _child_marker(value: str) -> None:
    print(f"authored_offset_composition_child:{value}", file=sys.stderr, flush=True)


def _run_child(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    app = None
    runtime: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    report: dict[str, Any]
    close_failed = False
    try:
        _child_marker("begin")
        request = _validate_composition_request(
            attestation._read_canonical_json(args.composition_request)
        )
        execution_request = attestation._read_canonical_json(args.execution_request)
        closure = source_paths()
        execution_request = attestation.verify_execution_request(
            execution_request, source_paths=closure
        )
        pre_app_numpy_modules = sorted(
            name for name in sys.modules if name == "numpy" or name.startswith("numpy.")
        )
        from isaacsim import SimulationApp

        _child_marker("before_simulation_app")
        app = SimulationApp(
            {"headless": True, "width": 64, "height": 64},
            experience=str(KIT_PROFILE_PATH),
        )
        _child_marker("after_simulation_app")
        receipt = attestation.attest_existing_application(
            application=app,
            pre_app_numpy_modules=pre_app_numpy_modules,
            execution_request=execution_request,
            source_paths=closure,
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
            "execution_request_sha256": attestation.canonical_json_sha256(execution_request),
            "gpu": _collect_child_gpu_identity(),
        }
        from tools.labutopia_fluid import (
            nonformal_authored_offset_overlay_composition_runtime as runtime_probe,
        )

        observation = runtime_probe.compose_authored_offset_overlay(app=app, request=request)
        evaluation = composition.evaluate_observation(
            observation,
            plan=request["plan"],
            fixture=request["fixture"],
            kit_profile=request["kit_profile"],
        )
        source_after = attestation.capture_source_identity(closure)
        if source_after != execution_request["source"]:
            raise RuntimeError("authored_offset_composition_source_changed_during_run")
        attestation.write_canonical_json(args.observation_path, observation)
        report = {
            "authority": AUTHORITY,
            "schema_version": 1,
            "classification": CLASSIFICATION,
            "decision": evaluation["decision"],
            "request": request,
            "runtime": runtime,
            "composition": {
                "evaluation": evaluation,
                "observation_artifact": {
                    "path": OBSERVATION_BASENAME,
                    "sha256": _sha256_file(args.observation_path),
                    "observation_sha256": observation["sha256"],
                },
            },
            "authorization": dict(composition.AUTHORIZATION),
        }
    except BaseException as exc:
        _child_marker(f"error:{type(exc).__name__}:{exc}")
        report = _runtime_error_report(exc, runtime, request)
    finally:
        if not args.child_report_path.exists():
            attestation.write_canonical_json(args.child_report_path, report)
        if app is not None and report["decision"] != RUNTIME_BLOCKED:
            try:
                app.close()
            except BaseException:
                close_failed = True
    if close_failed:
        return 2
    return expected_child_returncode(str(report["decision"]))


def _regular_file(path: Path, *, field: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"authored_offset_composition_{field}_invalid")
    return path


def _safe_file_sha256(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    return _sha256_file(path)


def _artifact_record(path: Path, *, root: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        return {"path": str(path.relative_to(root)), "invalid_kind": "symlink_or_non_regular"}
    return {
        "path": str(path.relative_to(root)),
        "byte_count": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _require_process_group_quiescent(pgid: int, *, timeout_seconds: float = 15.0) -> None:
    if type(pgid) is not int or pgid <= 0:
        raise RuntimeError("authored_offset_composition_child_pgid_invalid")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise RuntimeError("authored_offset_composition_child_pgid_uninspectable") from exc
        if time.monotonic() >= deadline:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                return
            raise RuntimeError("authored_offset_composition_child_process_group_not_quiescent")
        time.sleep(0.05)


def _verify_child_report(
    *,
    child_report: Mapping[str, Any],
    request: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
    execution_request: Mapping[str, Any],
    execution_binding: Mapping[str, Any] | None,
    out_dir: Path,
) -> dict[str, Any]:
    if (
        child_report.get("authority") != AUTHORITY
        or child_report.get("schema_version") != 1
        or child_report.get("classification") != CLASSIFICATION
        or child_report.get("request") != dict(request)
    ):
        raise RuntimeError("authored_offset_composition_child_request_invalid")
    decision = child_report.get("decision")
    if decision == RUNTIME_BLOCKED:
        expected_blocked_fields = {
            "authority",
            "schema_version",
            "classification",
            "decision",
            "request",
            "runtime",
            "fatal_error",
        }
        fatal_error = child_report.get("fatal_error")
        if (
            set(child_report) != expected_blocked_fields
            or not isinstance(fatal_error, Mapping)
            or set(fatal_error) != {"type", "message", "traceback"}
            or not isinstance(fatal_error.get("type"), str)
            or not isinstance(fatal_error.get("message"), str)
            or not isinstance(fatal_error.get("traceback"), str)
        ):
            raise RuntimeError("authored_offset_composition_child_blocked_report_invalid")
        return dict(child_report)
    expected_fields = {
        "authority",
        "schema_version",
        "classification",
        "decision",
        "request",
        "runtime",
        "composition",
        "authorization",
    }
    if (
        decision not in {PASS, NO_GO}
        or set(child_report) != expected_fields
        or child_report.get("authorization") != dict(composition.AUTHORIZATION)
        or not isinstance(receipt, Mapping)
        or not isinstance(execution_binding, Mapping)
    ):
        raise RuntimeError("authored_offset_composition_child_decision_invalid")
    runtime = child_report.get("runtime")
    if (
        not isinstance(runtime, Mapping)
        or set(runtime) != {"receipt_sha256", "execution_binding", "execution_request_sha256", "gpu"}
        or runtime.get("receipt_sha256") != _attestation_json_sha256(receipt)
        or runtime.get("execution_binding") != dict(execution_binding)
        or runtime.get("execution_request_sha256") != _attestation_json_sha256(execution_request)
    ):
        raise RuntimeError("authored_offset_composition_child_runtime_binding_invalid")
    gpu = _validate_child_gpu_identity(runtime["gpu"])
    composition_report = child_report.get("composition")
    if (
        not isinstance(composition_report, Mapping)
        or set(composition_report) != {"evaluation", "observation_artifact"}
        or not isinstance(composition_report.get("observation_artifact"), Mapping)
    ):
        raise RuntimeError("authored_offset_composition_child_composition_invalid")
    artifact = composition_report["observation_artifact"]
    if (
        set(artifact) != {"path", "sha256", "observation_sha256"}
        or artifact.get("path") != OBSERVATION_BASENAME
        or not isinstance(artifact.get("sha256"), str)
        or not isinstance(artifact.get("observation_sha256"), str)
    ):
        raise RuntimeError("authored_offset_composition_observation_artifact_invalid")
    observation_path = out_dir / OBSERVATION_BASENAME
    if (
        observation_path.is_symlink()
        or not observation_path.is_file()
        or artifact["sha256"] != _sha256_file(observation_path)
    ):
        raise RuntimeError("authored_offset_composition_observation_artifact_invalid")
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    observation = attestation._read_canonical_json(observation_path)
    if observation.get("sha256") != artifact["observation_sha256"]:
        raise RuntimeError("authored_offset_composition_observation_hash_invalid")
    evaluation = composition.evaluate_observation(
        observation,
        plan=request["plan"],
        fixture=request["fixture"],
        kit_profile=request["kit_profile"],
    )
    if composition_report.get("evaluation") != evaluation or decision != evaluation["decision"]:
        raise RuntimeError("authored_offset_composition_child_evaluation_invalid")
    return {
        "authority": AUTHORITY,
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "decision": decision,
        "request": dict(request),
        "authorization": dict(composition.AUTHORIZATION),
        "runtime": {
            "receipt_sha256": runtime["receipt_sha256"],
            "execution_binding": dict(execution_binding),
            "execution_request_sha256": runtime["execution_request_sha256"],
            "gpu": gpu,
        },
        "composition": {
            "evaluation": evaluation,
            "observation_artifact": dict(artifact),
            "input_usd_dependency_closure_sha256": observation[
                "input_usd_dependency_closures"
            ]["before"]["sha256"],
        },
        "parent_evaluation": evaluation,
    }


def _run_parent(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    request = build_composition_request()
    request_path = args.out_dir / REQUEST_BASENAME
    attestation.write_canonical_json(request_path, request)
    closure = source_paths()
    source_before = attestation.capture_source_identity(closure)
    execution_request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    execution_request_path = args.out_dir / EXECUTION_REQUEST_BASENAME
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
        "--composition-request",
        str(request_path),
        "--execution-request",
        str(execution_request_path),
    ]
    stdout_path = args.out_dir / STDOUT_BASENAME
    stderr_path = args.out_dir / STDERR_BASENAME
    child_pid = None
    child_pgid = None
    child_returncode = None
    receipt = None
    source_after = None
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
            child_pgid = process.pid
            try:
                child_returncode = process.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                child_returncode = process.wait()
                raise RuntimeError("authored_offset_composition_child_timeout") from exc
        _require_process_group_quiescent(child_pgid)
        _regular_file(stdout_path, field="child_stdout")
        _regular_file(stderr_path, field="child_stderr")
        _regular_file(args.child_report_path, field="child_report")
        child_report = attestation._read_canonical_json(args.child_report_path)
        if child_report.get("decision") != RUNTIME_BLOCKED:
            _regular_file(args.runtime_receipt_path, field="runtime_receipt")
            receipt = attestation._read_canonical_json(args.runtime_receipt_path)
            binding = attestation.execution_binding_for_request(
                execution_request, child_pid=child_pid
            )
            attestation.require_matched_runtime_receipt(
                receipt, expected_execution_binding=binding
            )
        else:
            binding = None
            if args.runtime_receipt_path.is_file() and not args.runtime_receipt_path.is_symlink():
                receipt = attestation._read_canonical_json(args.runtime_receipt_path)
                attestation.validate_runtime_receipt(receipt)
        report = _verify_child_report(
            child_report=child_report,
            request=request,
            receipt=receipt,
            execution_request=execution_request,
            execution_binding=binding,
            out_dir=args.out_dir,
        )
        if child_returncode != expected_child_returncode(str(report["decision"])):
            raise RuntimeError("authored_offset_composition_child_exit_status_invalid")
        source_after = attestation.capture_source_identity(closure)
        if source_after != source_before:
            raise RuntimeError("authored_offset_composition_source_changed_during_run")
        report = {
            **report,
            "authority": "nonauthorizing_authored_offset_overlay_composition_parent_report_v1",
            "parent_verification": {
                "verified": report["decision"] != RUNTIME_BLOCKED,
                "child_pid": child_pid,
                "child_pgid": child_pgid,
                "child_returncode": child_returncode,
                "runtime_receipt_sha256": _attestation_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None,
                "child_report_sha256": _safe_file_sha256(args.child_report_path),
                "observation_sha256": _safe_file_sha256(args.observation_path),
                "stdout_sha256": _safe_file_sha256(stdout_path),
                "stderr_sha256": _safe_file_sha256(stderr_path),
                "gpu": report.get("runtime", {}).get("gpu")
                if isinstance(report.get("runtime"), Mapping)
                else None,
            },
        }
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        report = {
            "authority": "nonauthorizing_authored_offset_overlay_composition_parent_report_v1",
            "schema_version": 1,
            "classification": CLASSIFICATION,
            "decision": RUNTIME_BLOCKED,
            "request": request,
            "authorization": dict(composition.AUTHORIZATION),
            "fatal_error": verification_failure,
            "parent_verification": {
                "verified": False,
                "child_pid": child_pid,
                "child_pgid": child_pgid,
                "child_returncode": child_returncode,
                "runtime_receipt_sha256": _attestation_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None,
                "child_report_sha256": _safe_file_sha256(args.child_report_path),
                "observation_sha256": _safe_file_sha256(args.observation_path),
                "stdout_sha256": _safe_file_sha256(stdout_path),
                "stderr_sha256": _safe_file_sha256(stderr_path),
                "gpu": None,
            },
        }
    finally:
        if source_after is None:
            source_after = attestation.capture_source_identity(closure)
        report_path = args.out_dir / REPORT_BASENAME
        attestation.write_canonical_json(report_path, report)
        manifest = {
            "authority": AUTHORITY,
            "schema_version": 1,
            "classification": CLASSIFICATION,
            "decision": report["decision"],
            "command": command,
            "request_sha256": _sha256_file(request_path),
            "execution_request_sha256": _attestation_json_sha256(execution_request),
            "source_before": source_before,
            "source_after": source_after,
            "kit_profile": request["kit_profile"],
            "fixture": request["fixture"],
            "input_usd_dependency_closure_sha256": (
                report["composition"].get("input_usd_dependency_closure_sha256")
                if isinstance(report.get("composition"), Mapping)
                else None
            ),
            "sanitized_environment_sha256": _canonical_sha256(dict(sorted(environment.items()))),
            "child_pid": child_pid,
            "child_pgid": child_pgid,
            "child_returncode": child_returncode,
            "runtime_receipt_sha256": _attestation_json_sha256(receipt)
            if isinstance(receipt, Mapping)
            else None,
            "child_report": _artifact_record(args.child_report_path, root=args.out_dir),
            "observation": _artifact_record(args.observation_path, root=args.out_dir),
            "runtime_receipt": _artifact_record(args.runtime_receipt_path, root=args.out_dir),
            "stdout": _artifact_record(stdout_path, root=args.out_dir),
            "stderr": _artifact_record(stderr_path, root=args.out_dir),
            "report": _artifact_record(report_path, root=args.out_dir),
            "verification_failure": verification_failure,
        }
        attestation.write_canonical_json(args.out_dir / MANIFEST_BASENAME, manifest)
    print(
        f"authored offset composition decision={report['decision']} out={args.out_dir / REPORT_BASENAME}",
        flush=True,
    )
    return expected_child_returncode(str(report["decision"]))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--composition-request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.out_dir = args.out_dir.resolve()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("timeout-seconds must be positive")
    child_values = (args.composition_request, args.execution_request)
    if args.child:
        if any(value is None for value in child_values):
            parser.error("--child requires sealed request paths")
        args.composition_request = args.composition_request.resolve()
        args.execution_request = args.execution_request.resolve()
        if (
            not args.out_dir.is_dir()
            or not args.composition_request.is_file()
            or not args.execution_request.is_file()
        ):
            parser.error("child sealed inputs and out-dir must exist")
    else:
        if any(value is not None for value in child_values):
            parser.error("sealed child options are child-only")
        if args.out_dir.exists():
            parser.error("out-dir must not exist")
    args.runtime_receipt_path = args.out_dir / RUNTIME_RECEIPT_BASENAME
    args.child_report_path = args.out_dir / CHILD_REPORT_BASENAME
    args.observation_path = args.out_dir / OBSERVATION_BASENAME
    return args


def _write_parent_preflight_blocked(args: argparse.Namespace, exc: BaseException) -> None:
    if not args.out_dir.is_dir():
        return
    report_path = args.out_dir / REPORT_BASENAME
    manifest_path = args.out_dir / MANIFEST_BASENAME
    if report_path.exists() or manifest_path.exists():
        return
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    failure = {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
    report = {
        "authority": "nonauthorizing_authored_offset_overlay_composition_parent_report_v1",
        "schema_version": 1,
        "classification": CLASSIFICATION,
        "decision": RUNTIME_BLOCKED,
        "preflight_failure": failure,
    }
    attestation.write_canonical_json(report_path, report)
    attestation.write_canonical_json(
        manifest_path,
        {
            "authority": AUTHORITY,
            "schema_version": 1,
            "classification": CLASSIFICATION,
            "decision": RUNTIME_BLOCKED,
            "preflight_failure": failure,
            "report_sha256": _sha256_file(report_path),
        },
    )


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
        _write_parent_preflight_blocked(args, exc)
        print(
            f"authored offset composition decision={RUNTIME_BLOCKED} out={args.out_dir / REPORT_BASENAME}",
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
