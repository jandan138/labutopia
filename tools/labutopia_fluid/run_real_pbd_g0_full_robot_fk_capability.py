#!/usr/bin/env python3
"""Run a sealed, diagnostic-only paused full-robot FK capability probe.

This runner exercises tensor kinematic refresh for every Franka degree of
freedom after one bootstrap reset. It never samples clearance, observes contact,
or authorizes a recovery phase.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import secrets
import signal
import subprocess
import sys
import traceback
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.labutopia_fluid import run_real_pbd_grasp_v2_g0_geometry as geometry
from utils import real_pbd_g0_full_robot_fk_capability as capability


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
FK_CAPABILITY_PLAN_PATH = REPO_ROOT / "config/real_pbd_g0_full_robot_fk_capability_v1.json"
FK_CAPABILITY_PROFILE_PATH = (
    REPO_ROOT
    / "tools/labutopia_fluid/profiles/"
    "isaac41_g0_full_robot_fk_capability_experimental.kit"
)
CUBE_ONLY_OVERLAY_PROFILE = geometry.V7_CUBE_ONLY_OVERLAY_PROFILE

AUTHORITY = "real_pbd_g0_full_robot_fk_capability_runner_v1"
CLASSIFICATION = "NON_FORMAL_FK_CAPABILITY_DIAGNOSTIC_ONLY"
CAPABILITY_PASS = capability.PASS
CAPABILITY_NO_GO = capability.NO_GO
RUNTIME_BLOCKED = "RUNTIME_BLOCKED"
REQUEST_BASENAME = "fk_capability_request.json"
EXECUTION_REQUEST_BASENAME = "execution_request.json"
RUNTIME_RECEIPT_BASENAME = "runtime_receipt.json"
CHILD_REPORT_BASENAME = "child_report.json"
OBSERVATION_BASENAME = "full_robot_fk_observation.json"
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


def _validate_child_gpu_identity(
    value: Any,
    *,
    formal_prefix: Path = FORMAL_ISAAC41_PREFIX,
) -> dict[str, Any]:
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
        or value.get("authority") != "sealed_child_gpu_identity_v1"
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
        raise RuntimeError("g0_fk_capability_child_gpu_identity_invalid")
    normalized = {
        "authority": value["authority"],
        "nvidia_visible_devices": value["nvidia_visible_devices"],
        "cuda_visible_devices": None,
        "cuda_device_count": value["cuda_device_count"],
        "cuda_device_0_name": value["cuda_device_0_name"],
        "cuda_device_0_uuid": value["cuda_device_0_uuid"],
        "cuda_device_0_pci_bus_id": value["cuda_device_0_pci_bus_id"],
        "cuda_driver_api_version": value["cuda_driver_api_version"],
        "torch_cuda_version": value["torch_cuda_version"],
    }
    for field in ("libcuda", "torch", "torch_native"):
        artifact = value[field]
        if (
            not isinstance(artifact, Mapping)
            or set(artifact) != {"path", "sha256"}
            or not isinstance(artifact.get("path"), str)
            or not isinstance(artifact.get("sha256"), str)
        ):
            raise RuntimeError("g0_fk_capability_child_gpu_identity_invalid")
        path = Path(artifact["path"])
        if path.is_symlink() or not path.is_file() or _sha256_file(path) != artifact["sha256"]:
            raise RuntimeError("g0_fk_capability_child_gpu_identity_invalid")
        if field in {"torch", "torch_native"} and not path.is_relative_to(formal_prefix):
            raise RuntimeError("g0_fk_capability_child_gpu_identity_invalid")
        normalized[field] = {"path": str(path), "sha256": artifact["sha256"]}
    return normalized


def _collect_child_gpu_identity() -> dict[str, Any]:
    """Collect the CUDA driver/device identity inside the already attested child."""
    import ctypes

    import torch

    if os.environ.get("NVIDIA_VISIBLE_DEVICES") != "4" or "CUDA_VISIBLE_DEVICES" in os.environ:
        raise RuntimeError("g0_fk_capability_gpu_visibility_invalid")
    candidates = []
    try:
        for line in Path("/proc/self/maps").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) >= 6 and fields[-1].startswith("/"):
                path = Path(fields[-1])
                if path.name.startswith("libcuda.so") and path.is_file():
                    candidates.append(path)
    except OSError as exc:
        raise RuntimeError("g0_fk_capability_libcuda_maps_unavailable") from exc
    if not candidates:
        raise RuntimeError("g0_fk_capability_libcuda_unavailable")
    libcuda_path = sorted(set(candidates), key=str)[0]
    library = ctypes.CDLL(str(libcuda_path))

    def require_cuda(status: int, name: str) -> None:
        if status != 0:
            raise RuntimeError(f"g0_fk_capability_cuda_driver_error:{name}:{status}")

    require_cuda(library.cuInit(0), "cuInit")
    driver_version = ctypes.c_int()
    require_cuda(library.cuDriverGetVersion(ctypes.byref(driver_version)), "cuDriverGetVersion")
    device_count = ctypes.c_int()
    require_cuda(library.cuDeviceGetCount(ctypes.byref(device_count)), "cuDeviceGetCount")
    if device_count.value != 1:
        raise RuntimeError("g0_fk_capability_cuda_device_count_invalid")
    device = ctypes.c_int()
    require_cuda(library.cuDeviceGet(ctypes.byref(device), 0), "cuDeviceGet")
    name_buffer = ctypes.create_string_buffer(256)
    require_cuda(library.cuDeviceGetName(name_buffer, len(name_buffer), device), "cuDeviceGetName")
    device_name = name_buffer.value.decode("utf-8")
    if not device_name:
        raise RuntimeError("g0_fk_capability_cuda_device_name_invalid")
    uuid_buffer = (ctypes.c_ubyte * 16)()
    require_cuda(library.cuDeviceGetUuid(ctypes.byref(uuid_buffer), device), "cuDeviceGetUuid")
    device_uuid = bytes(uuid_buffer).hex()
    pci_buffer = ctypes.create_string_buffer(32)
    require_cuda(
        library.cuDeviceGetPCIBusId(pci_buffer, len(pci_buffer), device),
        "cuDeviceGetPCIBusId",
    )
    pci_bus_id = pci_buffer.value.decode("utf-8")
    if not device_uuid or not pci_bus_id:
        raise RuntimeError("g0_fk_capability_cuda_device_identity_invalid")
    torch_path = Path(torch.__file__).resolve()
    torch_native_path = Path(torch._C.__file__).resolve()
    if not torch_path.is_file() or not torch_native_path.is_file() or not torch.version.cuda:
        raise RuntimeError("g0_fk_capability_torch_cuda_identity_invalid")
    return {
        "authority": "sealed_child_gpu_identity_v1",
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


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return capability.canonical_json_sha256(value)


def _attestation_json_sha256(value: Mapping[str, Any]) -> str:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    return attestation.canonical_json_sha256(value)


def _has_symlink_component(path: Path) -> bool:
    candidate = Path(path)
    try:
        relative = candidate.relative_to(REPO_ROOT)
    except ValueError:
        return True
    current = REPO_ROOT
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            return True
    return False


def _require_repo_regular(path: Path, *, field: str) -> Path:
    candidate = Path(path)
    if (
        _has_symlink_component(candidate)
        or not candidate.is_file()
        or not candidate.is_relative_to(REPO_ROOT)
    ):
        raise ValueError(f"g0_fk_capability_{field}_invalid")
    return candidate.resolve()


def _load_plan() -> dict[str, Any]:
    path = _require_repo_regular(FK_CAPABILITY_PLAN_PATH, field="plan_path")
    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("g0_fk_capability_plan_invalid") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("g0_fk_capability_plan_invalid")
    canonical = json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    if raw_bytes != canonical:
        raise ValueError("g0_fk_capability_plan_not_canonical")
    return capability.validate_plan(raw)


def build_capability_request() -> dict[str, Any]:
    plan = _load_plan()
    overlay_profile = geometry.resolve_overlay_profile(CUBE_ONLY_OVERLAY_PROFILE)
    payload = {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "plan": plan,
        "plan_sha256": plan["sha256"],
        "kit_profile": {
            "path": str(_require_repo_regular(FK_CAPABILITY_PROFILE_PATH, field="profile")),
            "sha256": _sha256_file(FK_CAPABILITY_PROFILE_PATH),
        },
        "fixture": {
            "asset": {
                "path": str(DEFAULT_ASSET),
                "sha256": _sha256_file(DEFAULT_ASSET),
            },
            "robot_asset": {
                "path": str(ROBOT_ASSET),
                "sha256": _sha256_file(ROBOT_ASSET),
            },
            "overlay_profile": overlay_profile,
            "overlay_profile_sha256": _canonical_sha256(overlay_profile),
        },
        "allowed_operations": {
            "bootstrap_world_resets": 1,
            "post_reset_world_steps": 0,
            "direct_joint_position_materializations": len(capability.DOF_NAMES) * 2,
            "tensor_kinematic_refreshes": len(capability.DOF_NAMES) * 2,
        },
        "authorization": {
            "clearance_certificate_authorized": False,
            "g0_go_authorized": False,
            "phase3_authorized": False,
        },
    }
    return {**payload, "sha256": _canonical_sha256(payload)}


def _validate_capability_request(value: Any) -> dict[str, Any]:
    expected = build_capability_request()
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise ValueError("g0_fk_capability_request_invalid")
    return expected


def _internal_module_path(module: str) -> Path | None:
    if not module:
        return None
    root = module.split(".", 1)[0]
    if root not in {
        "controllers",
        "data_collectors",
        "isaacsim_compat",
        "robots",
        "tasks",
        "tools",
        "utils",
    }:
        return None
    base = REPO_ROOT.joinpath(*module.split("."))
    candidate = base.with_suffix(".py")
    if candidate.is_file():
        return candidate
    package = base / "__init__.py"
    return package if package.is_file() else None


def _python_import_paths(seed_files: Sequence[str]) -> set[Path]:
    queue = []
    for relative in seed_files:
        path = REPO_ROOT / relative
        if _has_symlink_component(path) or not path.is_file() or not path.is_relative_to(REPO_ROOT):
            raise ValueError("g0_fk_capability_source_closure_invalid")
        queue.append(path)
    visited: set[Path] = set()
    while queue:
        path = queue.pop()
        if path in visited:
            continue
        visited.add(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            raise ValueError("g0_fk_capability_source_closure_invalid") from exc
        package = path.relative_to(REPO_ROOT).with_suffix("").parts[:-1]
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = None
                if node.level:
                    prefix = package[: max(0, len(package) - node.level + 1)]
                    suffix = tuple(node.module.split(".")) if node.module else ()
                    base = ".".join((*prefix, *suffix))
                elif node.module:
                    base = node.module
                if base:
                    modules.append(base)
                    modules.extend(f"{base}.{alias.name}" for alias in node.names)
            for module in modules:
                candidate = _internal_module_path(module)
                if candidate is not None:
                    queue.append(candidate.resolve())
    return visited


def source_paths() -> tuple[Path, ...]:
    """Return the code and direct roots rehashed before sealed-child bootstrap."""
    request = build_capability_request()
    source_seeds = (
        "tools/labutopia_fluid/run_real_pbd_g0_full_robot_fk_capability.py",
        "tools/labutopia_fluid/real_pbd_g0_full_robot_fk_capability_runtime.py",
        "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        "tools/labutopia_fluid/run_real_pbd_grasp_v2_g0_geometry.py",
        "tools/labutopia_fluid/run_real_pbd_grasp_v2_preflight.py",
        "tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py",
        "tools/labutopia_fluid/nonformal_controller_static_collision_screen_runtime.py",
        "utils/real_pbd_g0_full_robot_fk_capability.py",
    )
    python_closure = _python_import_paths(source_seeds)
    candidates = {
        Path(__file__),
        FK_CAPABILITY_PLAN_PATH,
        FK_CAPABILITY_PROFILE_PATH,
        DEFAULT_ASSET,
        ROBOT_ASSET,
        HIDDEN_CUBE_OVERLAY,
        *python_closure,
    }
    profile = request["fixture"]["overlay_profile"]
    candidates.update(Path(item["path"]) for item in profile["overlay_stack"])
    return tuple(
        sorted(_require_repo_regular(path, field="source_closure") for path in candidates)
    )


def expected_child_returncode(decision: str) -> int:
    if decision == RUNTIME_BLOCKED:
        return 2
    if decision in {CAPABILITY_PASS, CAPABILITY_NO_GO}:
        return 0
    raise ValueError("g0_fk_capability_child_decision_invalid")


def _runtime_error_report(
    error: BaseException,
    runtime: Mapping[str, Any] | None,
    request: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "decision": RUNTIME_BLOCKED,
        "request": dict(request) if isinstance(request, Mapping) else None,
        "runtime": dict(runtime) if isinstance(runtime, Mapping) else None,
        "fatal_error": {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        },
    }


def _fixture_usd_dependency_closures(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the actual binary/text USD closures only inside the sealed child."""
    from tools.labutopia_fluid.run_real_pbd_grasp_v2_preflight import usd_dependency_closure

    return {
        "asset": usd_dependency_closure(fixture["asset"]["path"]),
        "robot_asset": usd_dependency_closure(fixture["robot_asset"]["path"]),
        "hidden_cube_overlay": usd_dependency_closure(str(HIDDEN_CUBE_OVERLAY)),
    }


def _stage_fixture(
    *,
    app: Any,
    request: Mapping[str, Any],
) -> tuple[Any, Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    import omni.timeline
    import omni.usd
    from pxr import Gf, UsdGeom

    from tools.labutopia_fluid.run_real_pbd_grasp_v2_preflight import _static_grasp_topology

    fixture = request["fixture"]
    overlay_profile = fixture["overlay_profile"]
    input_usd_dependency_closures = _fixture_usd_dependency_closures(fixture)
    timeline = omni.timeline.get_timeline_interface()
    context = omni.usd.get_context()
    context.new_stage()
    stage = context.get_stage()
    stage.GetRootLayer().Clear()
    stage.GetSessionLayer().Clear()
    session_overlay_paths = [item["path"] for item in overlay_profile["overlay_stack"]]
    for overlay_path in session_overlay_paths:
        stage.GetSessionLayer().subLayerPaths.append(overlay_path)
    if list(stage.GetSessionLayer().subLayerPaths) != session_overlay_paths:
        raise RuntimeError("g0_fk_capability_overlay_stack_mismatch")
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    world_root = stage.DefinePrim("/World", "Xform")
    world_root.GetReferences().AddReference(fixture["asset"]["path"])
    franka = stage.DefinePrim("/World/Franka", "Xform")
    franka.GetReferences().AddReference(fixture["robot_asset"]["path"])
    translate = franka.GetAttribute("xformOp:translate")
    if translate and translate.IsValid():
        translate.Set(Gf.Vec3d(-0.4, 0.0, 0.71))
    else:
        UsdGeom.Xformable(franka).AddTranslateOp().Set(Gf.Vec3d(-0.4, 0.0, 0.71))
    baseline = {
        "is_playing": bool(timeline.is_playing()),
        "time_s": float(timeline.get_current_time()),
    }
    for _ in range(60):
        app.update()
        if timeline.is_playing() or float(timeline.get_current_time()) != baseline["time_s"]:
            raise RuntimeError("g0_fk_capability_timeline_changed_while_loading")
    if _fixture_usd_dependency_closures(fixture) != input_usd_dependency_closures:
        raise RuntimeError("g0_fk_capability_input_usd_closure_changed_while_loading")
    topology = _static_grasp_topology(stage)
    role_paths = geometry._role_paths(stage, topology)
    collision_scope = geometry.build_full_robot_static_collision_scope(role_paths)
    if (
        len(collision_scope["full_robot_collider_paths"]) != 11
        or len(collision_scope["blocking_pairs"]) != 3210
    ):
        raise RuntimeError("g0_fk_capability_full_robot_scope_unexpected")
    cube = stage.GetPrimAtPath("/World/Cube")
    if cube.GetAttribute("physics:collisionEnabled").Get() is not False:
        raise RuntimeError("g0_fk_capability_hidden_cube_collision_enabled")
    fixture_report = {
        "asset": dict(fixture["asset"]),
        "robot_asset": dict(fixture["robot_asset"]),
        "overlay_profile": dict(overlay_profile),
        "overlay_profile_sha256": fixture["overlay_profile_sha256"],
        "hidden_cube_treatment": geometry.audit_hidden_cube_collision_treatment(
            HIDDEN_CUBE_OVERLAY
        ),
        "stage_units_in_meters": float(UsdGeom.GetStageMetersPerUnit(stage)),
        "stage_up_axis": str(UsdGeom.GetStageUpAxis(stage)),
        "input_usd_dependency_closures": input_usd_dependency_closures,
    }
    return stage, timeline, topology, role_paths, {
        "fixture": fixture_report,
        "collision_scope": collision_scope,
    }


def _run_child(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    app = None
    runtime: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    report: dict[str, Any]
    close_failed = False
    try:
        request = _validate_capability_request(
            attestation._read_canonical_json(args.capability_request)
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

        app = SimulationApp(
            {"headless": True, "width": 64, "height": 64},
            experience=str(FK_CAPABILITY_PROFILE_PATH),
        )
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
            "execution_request_sha256": attestation.canonical_json_sha256(
                execution_request
            ),
            "gpu": _collect_child_gpu_identity(),
        }
        stage, timeline, topology, role_paths, stage_report = _stage_fixture(
            app=app, request=request
        )
        from tools.labutopia_fluid import real_pbd_g0_full_robot_fk_capability_runtime as runtime_probe

        result = runtime_probe.run_full_robot_fk_capability(
            app=app,
            stage=stage,
            timeline=timeline,
            plan=request["plan"],
            full_robot_collider_paths=stage_report["collision_scope"][
                "full_robot_collider_paths"
            ],
        )
        if (
            _fixture_usd_dependency_closures(request["fixture"])
            != stage_report["fixture"]["input_usd_dependency_closures"]
        ):
            raise RuntimeError("g0_fk_capability_input_usd_closure_changed_during_run")
        stage_report["fixture"]["input_usd_dependency_closure_stable"] = True
        observation = result["observation"]
        attestation.write_canonical_json(args.observation_path, observation)
        observation_artifact = {
            "path": OBSERVATION_BASENAME,
            "sha256": _sha256_file(args.observation_path),
            "observation_sha256": observation["sha256"],
        }
        report = {
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "schema_version": 1,
            "decision": result["evaluation"]["decision"],
            "request": request,
            "runtime": runtime,
            "fixture": stage_report["fixture"],
            "topology": topology,
            "role_paths": role_paths,
            "full_robot_static_collision_scope": stage_report["collision_scope"],
            "capability": {
                "plan": result["plan"],
                "evaluation": result["evaluation"],
                "observation_artifact": observation_artifact,
                "guard_coverage": result["guard_coverage"],
                "reset_bootstrap_advance": result["reset_bootstrap_advance"],
                "baseline_state": result["baseline_state"],
                "final_state": result["final_state"],
                "source_reader": result["source_reader"],
                "collision_inventory_before_sha256": result[
                    "collision_inventory_before_sha256"
                ],
                "collision_inventory_after_sha256": result[
                    "collision_inventory_after_sha256"
                ],
                "mutation_ledger": result["mutation_ledger"],
            },
            "authorization": request["authorization"],
        }
    except BaseException as exc:
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


def _kit_gpu_identity(stdout_path: Path, environment: Mapping[str, str]) -> dict[str, Any]:
    if environment.get("NVIDIA_VISIBLE_DEVICES") != "4" or "CUDA_VISIBLE_DEVICES" in environment:
        raise RuntimeError("g0_fk_capability_gpu_visibility_invalid")
    try:
        text = stdout_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("g0_fk_capability_gpu_log_invalid") from exc
    driver = re.search(r"\|\s*Driver Version:\s*([^|]+?)\s*\|", text)
    gpu_rows = re.findall(
        r"^\|\s*(\d+)\s+\|\s*(.*?)\s+\|\s*Yes:\s*\d+\s*\|",
        text,
        flags=re.MULTILINE,
    )
    if driver is None or len(gpu_rows) != 1:
        raise RuntimeError("g0_fk_capability_gpu_log_invalid")
    logical_index, name = gpu_rows[0]
    payload = {
        "authority": "kit_startup_gpu_identity_v1",
        "nvidia_visible_devices": environment["NVIDIA_VISIBLE_DEVICES"],
        "kit_logical_gpu_index": int(logical_index),
        "name": name.strip(),
        "driver_version": driver.group(1).strip(),
        "stdout_sha256": _sha256_file(stdout_path),
    }
    return {**payload, "sha256": _canonical_sha256(payload)}


def _usd_closure_sha256(layers: Sequence[Mapping[str, Any]]) -> str:
    payload = {"layers": [dict(layer) for layer in layers]}
    return hashlib.sha256(
        (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode("utf-8")
    ).hexdigest()


def _verify_usd_dependency_closure(
    value: Any,
    *,
    entry_path: Path,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "usd_dependency_closure_sha256",
        "usd_dependency_layers",
    }:
        raise RuntimeError(f"g0_fk_capability_{field}_closure_invalid")
    layers = value["usd_dependency_layers"]
    if not isinstance(layers, list) or not layers:
        raise RuntimeError(f"g0_fk_capability_{field}_closure_invalid")
    normalized_layers = []
    for raw in layers:
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"identifier", "real_path", "sha256"}
            or not isinstance(raw["identifier"], str)
            or not isinstance(raw["real_path"], str)
        ):
            raise RuntimeError(f"g0_fk_capability_{field}_closure_invalid")
        path = _require_repo_regular(Path(raw["real_path"]), field=f"{field}_closure_path")
        if raw["sha256"] != _sha256_file(path):
            raise RuntimeError(f"g0_fk_capability_{field}_closure_hash_invalid")
        normalized_layers.append(
            {
                "identifier": raw["identifier"],
                "real_path": str(path),
                "sha256": raw["sha256"],
            }
        )
    if normalized_layers != sorted(normalized_layers, key=lambda item: item["real_path"]):
        raise RuntimeError(f"g0_fk_capability_{field}_closure_order_invalid")
    if (
        value["usd_dependency_closure_sha256"] != _usd_closure_sha256(normalized_layers)
        or str(_require_repo_regular(entry_path, field=f"{field}_entry"))
        not in {item["real_path"] for item in normalized_layers}
    ):
        raise RuntimeError(f"g0_fk_capability_{field}_closure_invalid")
    return {
        "usd_dependency_closure_sha256": value["usd_dependency_closure_sha256"],
        "usd_dependency_layers": normalized_layers,
    }


def _verify_child_fixture(value: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError("g0_fk_capability_child_fixture_invalid")
    fixture = request["fixture"]
    if (
        value.get("asset") != fixture["asset"]
        or value.get("robot_asset") != fixture["robot_asset"]
        or value.get("overlay_profile") != fixture["overlay_profile"]
        or value.get("overlay_profile_sha256") != fixture["overlay_profile_sha256"]
        or value.get("input_usd_dependency_closure_stable") is not True
    ):
        raise RuntimeError("g0_fk_capability_child_fixture_invalid")
    closures = value.get("input_usd_dependency_closures")
    if not isinstance(closures, Mapping) or set(closures) != {
        "asset",
        "robot_asset",
        "hidden_cube_overlay",
    }:
        raise RuntimeError("g0_fk_capability_child_fixture_closure_invalid")
    return {
        "asset": _verify_usd_dependency_closure(
            closures["asset"], entry_path=DEFAULT_ASSET, field="asset"
        ),
        "robot_asset": _verify_usd_dependency_closure(
            closures["robot_asset"], entry_path=ROBOT_ASSET, field="robot_asset"
        ),
        "hidden_cube_overlay": _verify_usd_dependency_closure(
            closures["hidden_cube_overlay"],
            entry_path=HIDDEN_CUBE_OVERLAY,
            field="hidden_cube_overlay",
        ),
    }


def _verify_child_report(
    *,
    child_report: Mapping[str, Any],
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
    execution_request: Mapping[str, Any],
    execution_binding: Mapping[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    if (
        child_report.get("authority") != AUTHORITY
        or child_report.get("classification") != CLASSIFICATION
        or child_report.get("schema_version") != 1
        or child_report.get("request") != dict(request)
    ):
        raise RuntimeError("g0_fk_capability_child_request_invalid")
    decision = child_report.get("decision")
    if decision == RUNTIME_BLOCKED:
        return dict(child_report)
    expected_child_fields = {
        "authority",
        "classification",
        "schema_version",
        "decision",
        "request",
        "runtime",
        "fixture",
        "topology",
        "role_paths",
        "full_robot_static_collision_scope",
        "capability",
        "authorization",
    }
    if (
        decision not in {CAPABILITY_PASS, CAPABILITY_NO_GO}
        or child_report.get("authorization") != dict(request["authorization"])
        or set(child_report) != expected_child_fields
    ):
        raise RuntimeError("g0_fk_capability_child_decision_invalid")
    runtime = child_report.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != {
        "receipt_sha256",
        "execution_binding",
        "execution_request_sha256",
        "gpu",
    } or (
        runtime.get("receipt_sha256") != _attestation_json_sha256(receipt)
        or runtime.get("execution_binding") != dict(execution_binding)
        or runtime.get("execution_request_sha256")
        != _attestation_json_sha256(execution_request)
    ):
        raise RuntimeError("g0_fk_capability_child_runtime_binding_invalid")
    gpu_identity = _validate_child_gpu_identity(runtime["gpu"])
    child_fixture = child_report.get("fixture")
    expected_fixture_fields = {
        "asset",
        "robot_asset",
        "overlay_profile",
        "overlay_profile_sha256",
        "hidden_cube_treatment",
        "stage_units_in_meters",
        "stage_up_axis",
        "input_usd_dependency_closures",
        "input_usd_dependency_closure_stable",
    }
    if (
        not isinstance(child_fixture, Mapping)
        or set(child_fixture) != expected_fixture_fields
        or child_fixture.get("stage_units_in_meters") != 1.0
        or child_fixture.get("stage_up_axis") != "Z"
    ):
        raise RuntimeError("g0_fk_capability_child_fixture_invalid")
    fixture_closures = _verify_child_fixture(child_fixture, request)
    role_paths = child_report.get("role_paths")
    scope = child_report.get("full_robot_static_collision_scope")
    if not isinstance(role_paths, Mapping) or not isinstance(scope, Mapping):
        raise RuntimeError("g0_fk_capability_child_scope_invalid")
    expected_scope = geometry.build_full_robot_static_collision_scope(role_paths)
    if (
        scope != expected_scope
        or len(scope["full_robot_collider_paths"]) != 11
        or len(scope["blocking_pairs"]) != 3210
    ):
        raise RuntimeError("g0_fk_capability_child_scope_invalid")
    capability_report = child_report.get("capability")
    expected_capability_fields = {
        "plan",
        "evaluation",
        "observation_artifact",
        "guard_coverage",
        "reset_bootstrap_advance",
        "baseline_state",
        "final_state",
        "source_reader",
        "collision_inventory_before_sha256",
        "collision_inventory_after_sha256",
        "mutation_ledger",
    }
    if (
        not isinstance(capability_report, Mapping)
        or set(capability_report) != expected_capability_fields
        or capability_report.get("plan") != request["plan"]
    ):
        raise RuntimeError("g0_fk_capability_child_capability_invalid")
    artifact = capability_report.get("observation_artifact")
    if (
        not isinstance(artifact, Mapping)
        or set(artifact) != {"path", "sha256", "observation_sha256"}
        or artifact.get("path") != OBSERVATION_BASENAME
    ):
        raise RuntimeError("g0_fk_capability_child_observation_artifact_invalid")
    observation_path = out_dir / OBSERVATION_BASENAME
    if (
        observation_path.is_symlink()
        or not observation_path.is_file()
        or artifact.get("sha256") != _sha256_file(observation_path)
    ):
        raise RuntimeError("g0_fk_capability_child_observation_artifact_invalid")
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    observation = attestation._read_canonical_json(observation_path)
    if observation.get("sha256") != artifact.get("observation_sha256"):
        raise RuntimeError("g0_fk_capability_child_observation_hash_invalid")
    evaluation = capability.evaluate_observation(
        observation,
        plan=request["plan"],
        expected_collider_paths=scope["full_robot_collider_paths"],
    )
    if (
        capability_report.get("evaluation") != evaluation
        or decision != evaluation["decision"]
        or observation.get("full_robot_collider_paths")
        != scope["full_robot_collider_paths"]
    ):
        raise RuntimeError("g0_fk_capability_child_evaluation_invalid")
    coverage = capability_report.get("guard_coverage")
    if (
        not isinstance(coverage, Mapping)
        or set(coverage) != set(capability.OPERATION_GUARD_COVERAGE_FIELDS)
        or any(value is not True for value in coverage.values())
        or coverage != observation.get("operation_guard_coverage")
    ):
        raise RuntimeError("g0_fk_capability_child_guard_coverage_invalid")
    return {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "decision": decision,
        "request": dict(request),
        "authorization": dict(request["authorization"]),
        "runtime": {
            "receipt_sha256": runtime["receipt_sha256"],
            "execution_binding": dict(execution_binding),
            "execution_request_sha256": runtime["execution_request_sha256"],
            "gpu": gpu_identity,
        },
        "fixture": {
            "asset": dict(request["fixture"]["asset"]),
            "robot_asset": dict(request["fixture"]["robot_asset"]),
            "overlay_profile": dict(request["fixture"]["overlay_profile"]),
            "overlay_profile_sha256": request["fixture"]["overlay_profile_sha256"],
            "input_usd_dependency_closures": fixture_closures,
            "input_usd_dependency_closure_stable": True,
        },
        "full_robot_static_collision_scope": expected_scope,
        "capability": {
            "plan": dict(request["plan"]),
            "evaluation": evaluation,
            "observation_artifact": dict(artifact),
            "guard_coverage": dict(coverage),
        },
        "parent_evaluation": evaluation,
    }


def _artifact(path: Path, *, root: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        return {
            "path": str(path.relative_to(root)),
            "invalid_kind": "symlink_or_non_regular",
        }
    return {
        "path": str(path.relative_to(root)),
        "byte_count": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _regular_file(path: Path, *, field: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"g0_fk_capability_{field}_invalid")
    return path


def _safe_file_sha256(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    return _sha256_file(path)


def _run_parent(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    args.out_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    request = build_capability_request()
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
        "--capability-request",
        str(request_path),
        "--execution-request",
        str(execution_request_path),
    ]
    stdout_path = args.out_dir / STDOUT_BASENAME
    stderr_path = args.out_dir / STDERR_BASENAME
    child_pid = None
    child_returncode = None
    receipt = None
    gpu = None
    verification_failure = None
    source_after = None
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
                raise RuntimeError("g0_fk_capability_child_timeout") from exc
        _regular_file(stdout_path, field="child_stdout")
        _regular_file(stderr_path, field="child_stderr")
        _regular_file(args.child_report_path, field="child_report")
        _regular_file(args.runtime_receipt_path, field="runtime_receipt")
        child_report = attestation._read_canonical_json(args.child_report_path)
        receipt = attestation._read_canonical_json(args.runtime_receipt_path)
        binding = attestation.execution_binding_for_request(
            execution_request, child_pid=child_pid
        )
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=binding
        )
        report = _verify_child_report(
            child_report=child_report,
            request=request,
            receipt=receipt,
            execution_request=execution_request,
            execution_binding=binding,
            out_dir=args.out_dir,
        )
        if report["decision"] != RUNTIME_BLOCKED:
            gpu = report["runtime"]["gpu"]
        else:
            child_runtime = report.get("runtime")
            child_gpu = child_runtime.get("gpu") if isinstance(child_runtime, Mapping) else None
            try:
                gpu = _validate_child_gpu_identity(child_gpu)
            except RuntimeError:
                gpu = {
                "authority": "kit_startup_gpu_identity_v1",
                "status": "NOT_AVAILABLE_RUNTIME_BLOCKED",
                "nvidia_visible_devices": environment["NVIDIA_VISIBLE_DEVICES"],
                "stdout_sha256": _safe_file_sha256(stdout_path),
            }
        if child_returncode != expected_child_returncode(str(report["decision"])):
            raise RuntimeError("g0_fk_capability_child_exit_status_invalid")
        source_after = attestation.capture_source_identity(closure)
        if source_after != source_before:
            raise RuntimeError("g0_fk_capability_source_changed_during_run")
        report = {
            **report,
            "authority": "real_pbd_g0_full_robot_fk_capability_parent_report_v1",
            "parent_verification": {
                "verified": True,
                "child_pid": child_pid,
                "child_returncode": child_returncode,
                "runtime_receipt_sha256": _attestation_json_sha256(receipt),
                "child_report_sha256": _safe_file_sha256(args.child_report_path),
                "observation_sha256": _safe_file_sha256(args.observation_path),
                "stdout_sha256": _safe_file_sha256(stdout_path),
                "stderr_sha256": _safe_file_sha256(stderr_path),
                "gpu": gpu,
            },
        }
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        report = {
            "authority": "real_pbd_g0_full_robot_fk_capability_parent_report_v1",
            "classification": CLASSIFICATION,
            "schema_version": 1,
            "decision": RUNTIME_BLOCKED,
            "request": request,
            "authorization": request["authorization"],
            "fatal_error": verification_failure,
            "parent_verification": {
                "verified": False,
                "child_pid": child_pid,
                "child_returncode": child_returncode,
                "runtime_receipt_sha256": _attestation_json_sha256(receipt)
                if isinstance(receipt, Mapping)
                else None,
                "child_report_sha256": _safe_file_sha256(args.child_report_path),
                "observation_sha256": _safe_file_sha256(args.observation_path),
                "stdout_sha256": _safe_file_sha256(stdout_path),
                "stderr_sha256": _safe_file_sha256(stderr_path),
                "gpu": gpu,
            },
        }
    finally:
        if source_after is None:
            source_after = attestation.capture_source_identity(closure)
        report_path = args.out_dir / REPORT_BASENAME
        attestation.write_canonical_json(report_path, report)
        manifest = {
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "schema_version": 1,
            "decision": report["decision"],
            "command": command,
            "request_sha256": _sha256_file(request_path),
            "execution_request_sha256": _attestation_json_sha256(execution_request),
            "source_before": source_before,
            "source_after": source_after,
            "kit_profile": request["kit_profile"],
            "fixture": request["fixture"],
            "sanitized_environment_sha256": _canonical_sha256(
                dict(sorted(environment.items()))
            ),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "runtime_receipt_sha256": _attestation_json_sha256(receipt)
            if isinstance(receipt, Mapping)
            else None,
            "gpu": gpu,
            "child_report": _artifact(args.child_report_path, root=args.out_dir),
            "observation": _artifact(args.observation_path, root=args.out_dir),
            "runtime_receipt": _artifact(args.runtime_receipt_path, root=args.out_dir),
            "stdout": _artifact(stdout_path, root=args.out_dir),
            "stderr": _artifact(stderr_path, root=args.out_dir),
            "report": _artifact(report_path, root=args.out_dir),
            "verification_failure": verification_failure,
        }
        attestation.write_canonical_json(args.out_dir / MANIFEST_BASENAME, manifest)
    print(
        f"full-robot FK capability decision={report['decision']} out={args.out_dir / REPORT_BASENAME}",
        flush=True,
    )
    return expected_child_returncode(str(report["decision"]))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--capability-request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.out_dir = args.out_dir.resolve()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0.0:
        parser.error("timeout-seconds must be positive")
    child_values = (args.capability_request, args.execution_request)
    if args.child:
        if any(value is None for value in child_values):
            parser.error("--child requires sealed request paths")
        args.capability_request = args.capability_request.resolve()
        args.execution_request = args.execution_request.resolve()
        if (
            not args.out_dir.is_dir()
            or not args.capability_request.is_file()
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
        "authority": "real_pbd_g0_full_robot_fk_capability_parent_report_v1",
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "decision": RUNTIME_BLOCKED,
        "preflight_failure": failure,
    }
    attestation.write_canonical_json(report_path, report)
    attestation.write_canonical_json(
        manifest_path,
        {
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "schema_version": 1,
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
            f"full-robot FK capability decision={RUNTIME_BLOCKED} out={args.out_dir / REPORT_BASENAME}",
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
