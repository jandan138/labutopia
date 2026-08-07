#!/usr/bin/env python3
"""Run a sealed, diagnostic-only OmniPVD effective-offset capability capture.

The disposable one-step capture tests whether the pinned Isaac 4.1 PVD stack can
read the three un-authored G0 targets. It is intentionally not a clearance,
collision, motion, G0, or Phase 3 authority.
"""

from __future__ import annotations

import argparse
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

from tools.labutopia_fluid import run_real_pbd_g0_full_robot_fk_capability as fk_runner
from tools.labutopia_fluid import run_real_pbd_grasp_v2_g0_geometry as geometry
from utils import real_pbd_g0_effective_offset_capability as capability


FORMAL_ISAAC41_PYTHON = fk_runner.FORMAL_ISAAC41_PYTHON
FORMAL_ISAAC41_PREFIX = fk_runner.FORMAL_ISAAC41_PREFIX
EXPECTED_TORCH_CUDA_VERSION = fk_runner.EXPECTED_TORCH_CUDA_VERSION
DEFAULT_ASSET = fk_runner.DEFAULT_ASSET
ROBOT_ASSET = fk_runner.ROBOT_ASSET
HIDDEN_CUBE_OVERLAY = fk_runner.HIDDEN_CUBE_OVERLAY
CUBE_ONLY_OVERLAY_PROFILE = fk_runner.CUBE_ONLY_OVERLAY_PROFILE
PVD_CAPABILITY_PLAN_PATH = REPO_ROOT / "config/real_pbd_g0_effective_offset_capability_v1.json"
PVD_CAPABILITY_PROFILE_PATH = (
    REPO_ROOT
    / "tools/labutopia_fluid/profiles/"
    "isaac41_g0_effective_offset_capability_experimental.kit"
)
PVD_EXTENSION_ROOT = (
    FORMAL_ISAAC41_PREFIX
    / "lib/python3.10/site-packages/isaacsim/extsPhysics/omni.physx.pvd"
)
PVD_RUNTIME_ARTIFACT_PATHS = {
    "extension_toml": PVD_EXTENSION_ROOT / "config/extension.toml",
    "extension_python": PVD_EXTENSION_ROOT / "omni/physxpvd/scripts/extension.py",
    "converter_python": (
        PVD_EXTENSION_ROOT
        / "omni/physxpvd/scripts/omniusd_to_physxusd/omniusd_to_physxusd.py"
    ),
    "binding": (
        PVD_EXTENSION_ROOT
        / "omni/physxpvd/bindings/_physxPvd.cpython-310-x86_64-linux-gnu.so"
    ),
    "plugin": PVD_EXTENSION_ROOT / "bin/libomni.physx.pvd.plugin.so",
    "runtime_library": PVD_EXTENSION_ROOT / "bin/libPVDRuntime_64.so",
}
PVD_EXTENSION_VERSION = "106.0.20"

AUTHORITY = "real_pbd_g0_effective_offset_capability_runner_v1"
CLASSIFICATION = capability.CLASSIFICATION
CAPABILITY_PASS = capability.PASS
CAPABILITY_NO_GO = capability.NO_GO
RUNTIME_BLOCKED = "RUNTIME_BLOCKED"
REQUEST_BASENAME = "pvd_offset_capability_request.json"
EXECUTION_REQUEST_BASENAME = "execution_request.json"
RUNTIME_RECEIPT_BASENAME = "runtime_receipt.json"
CHILD_REPORT_BASENAME = "child_report.json"
OBSERVATION_BASENAME = "effective_offset_observation.json"
PVD_ACTOR_INVENTORY_BASENAME = "pvd_actor_inventory.json"
REPORT_BASENAME = "report.json"
MANIFEST_BASENAME = "run_manifest.json"
STDOUT_BASENAME = "child.stdout.log"
STDERR_BASENAME = "child.stderr.log"


def _sha256_file(path: Path) -> str:
    return fk_runner._sha256_file(path)


def _canonical_sha256(value: Any) -> str:
    return capability.canonical_json_sha256(value)


def _attestation_json_sha256(value: Mapping[str, Any]) -> str:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    return attestation.canonical_json_sha256(value)


def _require_repo_regular(path: Path, *, field: str) -> Path:
    return fk_runner._require_repo_regular(path, field=f"pvd_capability_{field}")


def _require_formal_runtime_regular(path: Path, *, field: str) -> Path:
    candidate = Path(path)
    if (
        candidate.is_symlink()
        or not candidate.is_file()
        or not candidate.is_relative_to(FORMAL_ISAAC41_PREFIX)
    ):
        raise ValueError(f"g0_pvd_capability_{field}_invalid")
    return candidate.resolve()


def _pvd_runtime_artifacts() -> dict[str, dict[str, str]]:
    if set(PVD_RUNTIME_ARTIFACT_PATHS) != set(capability.PVD_RUNTIME_ARTIFACT_NAMES):
        raise ValueError("g0_pvd_capability_runtime_artifact_names_invalid")
    return {
        name: {
            "path": str(_require_formal_runtime_regular(path, field=name)),
            "sha256": _sha256_file(_require_formal_runtime_regular(path, field=name)),
        }
        for name, path in PVD_RUNTIME_ARTIFACT_PATHS.items()
    }


def _pvd_extension_closure() -> dict[str, Any]:
    """Hash every regular PVD extension file before Kit can import the extension."""
    root = PVD_EXTENSION_ROOT
    if root.is_symlink() or not root.is_dir() or not root.is_relative_to(FORMAL_ISAAC41_PREFIX):
        raise ValueError("g0_pvd_capability_extension_root_invalid")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("g0_pvd_capability_extension_closure_symlink")
        if path.is_dir():
            continue
        if not path.is_file() or not path.is_relative_to(root):
            raise ValueError("g0_pvd_capability_extension_closure_invalid")
        files.append(
            {
                "relative_path": str(path.relative_to(root)),
                "byte_count": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    if not files:
        raise ValueError("g0_pvd_capability_extension_closure_empty")
    payload = {"root": str(root), "files": files}
    return {**payload, "sha256": _canonical_sha256(payload)}


def _load_plan() -> dict[str, Any]:
    path = _require_repo_regular(PVD_CAPABILITY_PLAN_PATH, field="plan_path")
    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("g0_pvd_capability_plan_invalid") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("g0_pvd_capability_plan_invalid")
    canonical = (
        json.dumps(
            raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    if raw_bytes != canonical:
        raise ValueError("g0_pvd_capability_plan_not_canonical")
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
            "path": str(_require_repo_regular(PVD_CAPABILITY_PROFILE_PATH, field="profile")),
            "sha256": _sha256_file(PVD_CAPABILITY_PROFILE_PATH),
        },
        "pvd_runtime_artifacts": _pvd_runtime_artifacts(),
        "pvd_extension_closure": _pvd_extension_closure(),
        "fixture": {
            "asset": {"path": str(DEFAULT_ASSET), "sha256": _sha256_file(DEFAULT_ASSET)},
            "robot_asset": {
                "path": str(ROBOT_ASSET),
                "sha256": _sha256_file(ROBOT_ASSET),
            },
            "overlay_profile": overlay_profile,
            "overlay_profile_sha256": _canonical_sha256(overlay_profile),
        },
        "authorization": dict(plan["authorization"]),
    }
    return {**payload, "sha256": _canonical_sha256(payload)}


def _validate_capability_request(value: Any) -> dict[str, Any]:
    expected = build_capability_request()
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise ValueError("g0_pvd_capability_request_invalid")
    return expected


def source_paths() -> tuple[Path, ...]:
    """Return repository inputs locked before the sealed PVD child launches."""
    request = build_capability_request()
    source_seeds = (
        "tools/labutopia_fluid/run_real_pbd_g0_effective_offset_capability.py",
        "tools/labutopia_fluid/real_pbd_g0_effective_offset_capability_runtime.py",
        "tools/labutopia_fluid/run_real_pbd_g0_full_robot_fk_capability.py",
        "tools/labutopia_fluid/real_pbd_g0_full_robot_fk_capability_runtime.py",
        "tools/labutopia_fluid/run_real_pbd_grasp_v2_g0_geometry.py",
        "tools/labutopia_fluid/run_real_pbd_grasp_v2_preflight.py",
        "tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py",
        "tools/labutopia_fluid/nonformal_controller_static_collision_screen_runtime.py",
        "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        "utils/real_pbd_g0_effective_offset_capability.py",
        "utils/real_pbd_g0_full_robot_fk_capability.py",
    )
    python_closure = fk_runner._python_import_paths(source_seeds)
    candidates = {
        Path(__file__),
        PVD_CAPABILITY_PLAN_PATH,
        PVD_CAPABILITY_PROFILE_PATH,
        DEFAULT_ASSET,
        ROBOT_ASSET,
        HIDDEN_CUBE_OVERLAY,
        *python_closure,
    }
    candidates.update(Path(item["path"]) for item in request["fixture"]["overlay_profile"]["overlay_stack"])
    return tuple(
        sorted(_require_repo_regular(path, field="source_closure") for path in candidates)
    )


def expected_child_returncode(decision: str) -> int:
    if decision == RUNTIME_BLOCKED:
        return 2
    if decision in {CAPABILITY_PASS, CAPABILITY_NO_GO}:
        return 0
    raise ValueError("g0_pvd_capability_child_decision_invalid")


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


def _child_marker(value: str) -> None:
    print(f"g0_pvd_capability_child:{value}", file=sys.stderr, flush=True)


def _require_target_scope(plan: Mapping[str, Any], role_paths: Mapping[str, Any]) -> None:
    full_robot = set(role_paths.get("full_robot_collider_paths", []))
    support = set(role_paths.get("support_collider_paths", []))
    for target in plan["targets"]:
        collider_path = target["collider_path"]
        if collider_path not in full_robot | support:
            raise RuntimeError(f"g0_pvd_capability_target_not_in_runtime_scope:{collider_path}")


def _run_child(args: argparse.Namespace) -> int:
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    app = None
    runtime: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    report: dict[str, Any]
    close_failed = False
    try:
        _child_marker("begin")
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

        _child_marker("before_simulation_app")
        app = SimulationApp(
            {"headless": True, "width": 64, "height": 64},
            experience=str(PVD_CAPABILITY_PROFILE_PATH),
        )
        _child_marker("after_simulation_app")
        _child_marker("before_runtime_attestation")
        receipt = attestation.attest_existing_application(
            application=app,
            pre_app_numpy_modules=pre_app_numpy_modules,
            execution_request=execution_request,
            source_paths=closure,
        )
        _child_marker("after_runtime_attestation")
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
            "gpu": fk_runner._collect_child_gpu_identity(),
        }
        from tools.labutopia_fluid import (
            real_pbd_g0_effective_offset_capability_runtime as runtime_probe,
        )

        stage, timeline, topology, role_paths, stage_report = fk_runner._stage_fixture(
            app=app, request=request
        )
        _require_target_scope(request["plan"], role_paths)
        _child_marker("fixture_composed")
        target_manifest = runtime_probe.build_source_target_manifest(stage, request["plan"])
        # The fixture is composed first; PVD is enabled immediately before World creates PhysX.
        runtime_probe.configure_pvd_recording_before_scene(
            recording_dir=args.recording_dir,
            conversion_dir=args.conversion_dir,
            out_dir=args.out_dir,
            runtime_artifacts=request["pvd_runtime_artifacts"],
        )
        result = runtime_probe.run_pvd_offset_capability(
            app=app,
            stage=stage,
            timeline=timeline,
            plan=request["plan"],
            target_manifest=target_manifest,
            recording_dir=args.recording_dir,
            conversion_dir=args.conversion_dir,
            out_dir=args.out_dir,
            runtime_artifacts=request["pvd_runtime_artifacts"],
        )
        _child_marker("capture_completed")
        if (
            fk_runner._fixture_usd_dependency_closures(request["fixture"])
            != stage_report["fixture"]["input_usd_dependency_closures"]
        ):
            raise RuntimeError("g0_pvd_capability_input_usd_closure_changed_during_run")
        stage_report["fixture"]["input_usd_dependency_closure_stable"] = True
        observation = result["observation"]
        attestation.write_canonical_json(args.observation_path, observation)
        inventory = result["pvd_actor_inventory"]
        attestation.write_canonical_json(args.pvd_actor_inventory_path, inventory)
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
                "observation_artifact": {
                    "path": OBSERVATION_BASENAME,
                    "sha256": _sha256_file(args.observation_path),
                    "observation_sha256": observation["sha256"],
                },
                "pvd_actor_inventory_artifact": {
                    "path": PVD_ACTOR_INVENTORY_BASENAME,
                    "sha256": _sha256_file(args.pvd_actor_inventory_path),
                    "inventory_sha256": inventory["sha256"],
                },
                "native_pvd_artifacts_loaded": result["native_pvd_artifacts_loaded"],
                "capture_runtime": result["capture_runtime"],
                "source_state_before": result["source_state_before"],
                "source_state_after": result["source_state_after"],
                "source_reader": result["source_reader"],
            },
            "authorization": request["authorization"],
        }
    except BaseException as exc:
        _child_marker(f"error:{type(exc).__name__}:{exc}")
        report = _runtime_error_report(exc, runtime, request)
    finally:
        if not args.child_report_path.exists():
            _child_marker("writing_child_report")
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
        raise RuntimeError(f"g0_pvd_capability_{field}_invalid")
    return path


def _require_process_group_quiescent(pgid: int, *, timeout_seconds: float = 15.0) -> None:
    if type(pgid) is not int or pgid <= 0:
        raise RuntimeError("g0_pvd_capability_child_pgid_invalid")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        except PermissionError as exc:
            raise RuntimeError("g0_pvd_capability_child_pgid_uninspectable") from exc
        if time.monotonic() >= deadline:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                return
            raise RuntimeError("g0_pvd_capability_child_process_group_not_quiescent")
        time.sleep(0.05)


def _safe_file_sha256(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    return _sha256_file(path)


def _has_output_symlink_component(path: Path, *, out_dir: Path) -> bool:
    try:
        relative = path.relative_to(out_dir)
    except ValueError:
        return True
    current = out_dir
    if current.is_symlink():
        return True
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            return True
    return False


def _output_regular_file(path: Path, *, out_dir: Path) -> Path:
    if (
        _has_output_symlink_component(path, out_dir=out_dir)
        or not path.is_file()
        or path.stat().st_nlink != 1
    ):
        raise RuntimeError("g0_pvd_capability_output_artifact_invalid")
    return path


def _child_log_diagnostic(stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    marker_counts = {
        "kit_error": 0,
        "kit_fatal": 0,
        "native_abi_warning": 0,
        "python_traceback": 0,
        "pvd_failure": 0,
    }
    payloads = {}
    for name, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        raw = _output_regular_file(path, out_dir=path.parent).read_bytes()
        payloads[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "byte_count": len(raw)}
        for line in raw.splitlines():
            lower = line.lower()
            if line.startswith(b"[Error] ") or b" [Error] " in line:
                marker_counts["kit_error"] += 1
            if line.startswith(b"[Fatal] ") or b" [Fatal] " in line:
                marker_counts["kit_fatal"] += 1
            if (
                b"Possible version incompatibility. Attempting to load omni::" in line
                and b" against v" in line
            ):
                marker_counts["native_abi_warning"] += 1
            if b"Traceback (most recent call last):" in line:
                marker_counts["python_traceback"] += 1
            if b"omnipvd" in lower and (b"failed" in lower or b"error" in lower):
                marker_counts["pvd_failure"] += 1
    return {
        "authority": "real_pbd_g0_pvd_child_log_diagnostic_v1",
        "stdout": payloads["stdout"],
        "stderr": payloads["stderr"],
        "marker_counts": marker_counts,
        "runtime_log_clean": not any(marker_counts.values()),
    }


def _artifact(path: Path, *, root: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        return {"path": str(path.relative_to(root)), "invalid_kind": "symlink_or_non_regular"}
    return {
        "path": str(path.relative_to(root)),
        "byte_count": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _verify_observation_artifact(
    value: Any,
    *,
    out_dir: Path,
    allowed_prefix: str,
) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"path", "byte_count", "sha256"}
        or not isinstance(value.get("path"), str)
        or not value["path"].startswith(allowed_prefix)
        or ".." in value["path"].split("/")
        or type(value.get("byte_count")) is not int
        or value["byte_count"] <= 0
        or not isinstance(value.get("sha256"), str)
    ):
        raise RuntimeError("g0_pvd_capability_observation_artifact_invalid")
    path = out_dir / value["path"]
    if (
        not path.is_relative_to(out_dir)
        or _has_output_symlink_component(path, out_dir=out_dir)
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size != value["byte_count"]
        or _sha256_file(path) != value["sha256"]
    ):
        raise RuntimeError("g0_pvd_capability_observation_artifact_invalid")
    return dict(value)


def _verify_pvd_artifact_tree(observation: Mapping[str, Any], *, out_dir: Path) -> None:
    recording = observation.get("recording")
    if not isinstance(recording, Mapping):
        raise RuntimeError("g0_pvd_capability_recording_invalid")
    finalized = _verify_observation_artifact(
        recording.get("finalized_ovd"), out_dir=out_dir, allowed_prefix="pvd-recording/"
    )
    converted = recording.get("conversion_artifacts")
    if (
        not isinstance(converted, Sequence)
        or isinstance(converted, (str, bytes, bytearray))
        or len(converted) != 3
    ):
        raise RuntimeError("g0_pvd_capability_conversion_artifacts_invalid")
    verified_conversion = [
        _verify_observation_artifact(item, out_dir=out_dir, allowed_prefix="pvd-converted/")
        for item in converted
    ]
    expected_paths = {
        finalized["path"],
        *(item["path"] for item in verified_conversion),
    }
    actual_paths = set()
    for root in (out_dir / "pvd-recording", out_dir / "pvd-converted"):
        if _has_output_symlink_component(root, out_dir=out_dir) or not root.is_dir():
            raise RuntimeError("g0_pvd_capability_artifact_tree_invalid")
        for path in root.rglob("*"):
            if _has_output_symlink_component(path, out_dir=out_dir) or path.is_dir() or not path.is_file():
                if path.is_dir():
                    continue
                raise RuntimeError("g0_pvd_capability_artifact_tree_invalid")
            if path.stat().st_nlink != 1:
                raise RuntimeError("g0_pvd_capability_artifact_tree_invalid")
            actual_paths.add(str(path.relative_to(out_dir)))
    if actual_paths != expected_paths:
        raise RuntimeError("g0_pvd_capability_artifact_tree_drift")


def _verify_pvd_extension_provenance(
    value: Any, *, runtime_artifacts: Mapping[str, Mapping[str, str]]
) -> None:
    expected_fields = {
        "extension_id",
        "extension_version",
        "extension_path",
        "module_origins",
    }
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise RuntimeError("g0_pvd_capability_extension_provenance_invalid")
    expected_root = str(Path(runtime_artifacts["extension_toml"]["path"]).parent)
    origins = value.get("module_origins")
    if (
        not isinstance(value.get("extension_id"), str)
        or not value["extension_id"]
        or value.get("extension_version") != PVD_EXTENSION_VERSION
        or value.get("extension_path") != expected_root
        or not isinstance(origins, Mapping)
        or dict(origins)
        != {
            name: runtime_artifacts[name]["path"]
            for name in ("extension_python", "converter_python", "binding")
        }
    ):
        raise RuntimeError("g0_pvd_capability_extension_provenance_invalid")


def _verify_inventory_matches_observation(
    inventory: Mapping[str, Any], observation: Mapping[str, Any]
) -> None:
    if (
        inventory.get("authority") != "real_pbd_g0_pvd_actor_inventory_v2"
        or inventory.get("pvd_scene") != observation.get("pvd_scene")
        or not isinstance(inventory.get("actors"), list)
        or inventory.get("sha256")
        != _canonical_sha256(
            {"pvd_scene": inventory.get("pvd_scene"), "actors": inventory.get("actors")}
        )
    ):
        raise RuntimeError("g0_pvd_capability_inventory_invalid")
    actors = {}
    for actor in inventory["actors"]:
        if (
            not isinstance(actor, Mapping)
            or not isinstance(actor.get("pvd_actor_path"), str)
            or actor["pvd_actor_path"] in actors
            or not isinstance(actor.get("shapes"), list)
            or actor.get("shape_count") != len(actor["shapes"])
        ):
            raise RuntimeError("g0_pvd_capability_inventory_invalid")
        actors[actor["pvd_actor_path"]] = actor
    for target in observation.get("target_offsets", []):
        if not isinstance(target, Mapping):
            raise RuntimeError("g0_pvd_capability_inventory_target_invalid")
        actor = actors.get(target.get("pvd_actor_path"))
        if (
            actor is None
            or actor.get("actor_name") != target.get("actor_name")
            or actor.get("actor_type") != target.get("actor_type")
            or actor.get("pvd_actor_class") != target.get("pvd_actor_class")
            or actor.get("pvd_scene_path") != target.get("pvd_scene_path")
            or actor.get("shape_count") != target.get("pvd_actor_shape_count")
        ):
            raise RuntimeError("g0_pvd_capability_inventory_target_invalid")
        matched = [
            shape
            for shape in actor["shapes"]
            if isinstance(shape, Mapping) and shape.get("pvd_shape_path") == target.get("pvd_shape_path")
        ]
        if (
            len(matched) != 1
            or matched[0].get("raw_contact_offset_pvd") != target.get("raw_contact_offset_pvd")
            or matched[0].get("raw_rest_offset_pvd") != target.get("raw_rest_offset_pvd")
            or matched[0].get("shape_flags") != target.get("shape_flags")
            or target.get("pvd_geometry_class") not in matched[0].get("pvd_geometry_classes", [])
        ):
            raise RuntimeError("g0_pvd_capability_inventory_target_invalid")


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
        raise RuntimeError("g0_pvd_capability_child_request_invalid")
    decision = child_report.get("decision")
    if decision == RUNTIME_BLOCKED:
        return dict(child_report)
    expected_fields = {
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
        or set(child_report) != expected_fields
        or child_report.get("authorization") != dict(request["authorization"])
    ):
        raise RuntimeError("g0_pvd_capability_child_decision_invalid")
    runtime = child_report.get("runtime")
    if (
        not isinstance(runtime, Mapping)
        or set(runtime) != {"receipt_sha256", "execution_binding", "execution_request_sha256", "gpu"}
        or runtime.get("receipt_sha256") != _attestation_json_sha256(receipt)
        or runtime.get("execution_binding") != dict(execution_binding)
        or runtime.get("execution_request_sha256") != _attestation_json_sha256(execution_request)
    ):
        raise RuntimeError("g0_pvd_capability_child_runtime_binding_invalid")
    gpu = fk_runner._validate_child_gpu_identity(runtime["gpu"])
    fixture = child_report.get("fixture")
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
        not isinstance(fixture, Mapping)
        or set(fixture) != expected_fixture_fields
        or fixture.get("stage_units_in_meters") != 1.0
        or fixture.get("stage_up_axis") != "Z"
    ):
        raise RuntimeError("g0_pvd_capability_child_fixture_invalid")
    fixture_closures = fk_runner._verify_child_fixture(fixture, request)
    role_paths = child_report.get("role_paths")
    scope = child_report.get("full_robot_static_collision_scope")
    if not isinstance(role_paths, Mapping) or not isinstance(scope, Mapping):
        raise RuntimeError("g0_pvd_capability_child_scope_invalid")
    _require_target_scope(request["plan"], role_paths)
    expected_scope = geometry.build_full_robot_static_collision_scope(role_paths)
    if (
        scope != expected_scope
        or len(scope["full_robot_collider_paths"]) != 11
        or len(scope["blocking_pairs"]) != 3210
    ):
        raise RuntimeError("g0_pvd_capability_child_scope_invalid")
    capability_report = child_report.get("capability")
    expected_capability_fields = {
        "plan",
        "evaluation",
        "observation_artifact",
        "pvd_actor_inventory_artifact",
        "native_pvd_artifacts_loaded",
        "capture_runtime",
        "source_state_before",
        "source_state_after",
        "source_reader",
    }
    if (
        not isinstance(capability_report, Mapping)
        or set(capability_report) != expected_capability_fields
        or capability_report.get("plan") != dict(request["plan"])
        or capability_report.get("native_pvd_artifacts_loaded")
        != {
            name: request["pvd_runtime_artifacts"][name]
            for name in ("binding", "plugin", "runtime_library")
        }
    ):
        raise RuntimeError("g0_pvd_capability_child_capability_invalid")
    observation_artifact = capability_report.get("observation_artifact")
    if (
        not isinstance(observation_artifact, Mapping)
        or set(observation_artifact) != {"path", "sha256", "observation_sha256"}
        or observation_artifact.get("path") != OBSERVATION_BASENAME
    ):
        raise RuntimeError("g0_pvd_capability_observation_artifact_invalid")
    observation_path = out_dir / OBSERVATION_BASENAME
    if (
        observation_path.is_symlink()
        or not observation_path.is_file()
        or observation_artifact.get("sha256") != _sha256_file(observation_path)
    ):
        raise RuntimeError("g0_pvd_capability_observation_artifact_invalid")
    from tools.labutopia_fluid import attest_isaac41_effective_runtime as attestation

    observation = attestation._read_canonical_json(observation_path)
    if observation.get("sha256") != observation_artifact.get("observation_sha256"):
        raise RuntimeError("g0_pvd_capability_observation_hash_invalid")
    evaluation = capability.evaluate_observation(observation, plan=request["plan"])
    if capability_report.get("evaluation") != evaluation or decision != evaluation["decision"]:
        raise RuntimeError("g0_pvd_capability_child_evaluation_invalid")
    if observation.get("pvd_runtime_artifacts") != request["pvd_runtime_artifacts"]:
        raise RuntimeError("g0_pvd_capability_runtime_artifact_binding_invalid")
    _verify_pvd_extension_provenance(
        observation.get("pvd_extension_provenance"),
        runtime_artifacts=request["pvd_runtime_artifacts"],
    )
    _verify_pvd_artifact_tree(observation, out_dir=out_dir)
    inventory_artifact = capability_report.get("pvd_actor_inventory_artifact")
    if (
        not isinstance(inventory_artifact, Mapping)
        or set(inventory_artifact) != {"path", "sha256", "inventory_sha256"}
        or inventory_artifact.get("path") != PVD_ACTOR_INVENTORY_BASENAME
    ):
        raise RuntimeError("g0_pvd_capability_inventory_artifact_invalid")
    inventory_path = out_dir / PVD_ACTOR_INVENTORY_BASENAME
    if (
        inventory_path.is_symlink()
        or not inventory_path.is_file()
        or inventory_artifact.get("sha256") != _sha256_file(inventory_path)
    ):
        raise RuntimeError("g0_pvd_capability_inventory_artifact_invalid")
    inventory = attestation._read_canonical_json(inventory_path)
    if inventory.get("sha256") != inventory_artifact.get("inventory_sha256"):
        raise RuntimeError("g0_pvd_capability_inventory_invalid")
    _verify_inventory_matches_observation(inventory, observation)
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
            "gpu": gpu,
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
            "observation_artifact": dict(observation_artifact),
            "pvd_actor_inventory_artifact": dict(inventory_artifact),
        },
        "parent_evaluation": evaluation,
    }


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
    child_pgid = None
    child_returncode = None
    receipt = None
    source_after = None
    verification_failure = None
    log_diagnostic = None
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
                raise RuntimeError("g0_pvd_capability_child_timeout") from exc
        _require_process_group_quiescent(child_pgid)
        _regular_file(stdout_path, field="child_stdout")
        _regular_file(stderr_path, field="child_stderr")
        _regular_file(args.child_report_path, field="child_report")
        _regular_file(args.runtime_receipt_path, field="runtime_receipt")
        log_diagnostic = _child_log_diagnostic(stdout_path, stderr_path)
        if not log_diagnostic["runtime_log_clean"]:
            raise RuntimeError("g0_pvd_capability_child_log_not_clean")
        child_report = attestation._read_canonical_json(args.child_report_path)
        receipt = attestation._read_canonical_json(args.runtime_receipt_path)
        binding = attestation.execution_binding_for_request(execution_request, child_pid=child_pid)
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
        if child_returncode != expected_child_returncode(str(report["decision"])):
            raise RuntimeError("g0_pvd_capability_child_exit_status_invalid")
        source_after = attestation.capture_source_identity(closure)
        if source_after != source_before:
            raise RuntimeError("g0_pvd_capability_source_changed_during_run")
        report = {
            **report,
            "authority": "real_pbd_g0_effective_offset_capability_parent_report_v1",
            "parent_verification": {
                "verified": True,
                "child_pid": child_pid,
                "child_pgid": child_pgid,
                "child_returncode": child_returncode,
                "runtime_receipt_sha256": _attestation_json_sha256(receipt),
                "child_report_sha256": _safe_file_sha256(args.child_report_path),
                "observation_sha256": _safe_file_sha256(args.observation_path),
                "pvd_actor_inventory_sha256": _safe_file_sha256(args.pvd_actor_inventory_path),
                "stdout_sha256": _safe_file_sha256(stdout_path),
                "stderr_sha256": _safe_file_sha256(stderr_path),
                "gpu": report["runtime"]["gpu"],
                "child_log_diagnostic": log_diagnostic,
            },
        }
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        report = {
            "authority": "real_pbd_g0_effective_offset_capability_parent_report_v1",
            "classification": CLASSIFICATION,
            "schema_version": 1,
            "decision": RUNTIME_BLOCKED,
            "request": request,
            "authorization": request["authorization"],
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
                "pvd_actor_inventory_sha256": _safe_file_sha256(args.pvd_actor_inventory_path),
                "stdout_sha256": _safe_file_sha256(stdout_path),
                "stderr_sha256": _safe_file_sha256(stderr_path),
                "child_log_diagnostic": log_diagnostic,
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
            "pvd_runtime_artifacts": request["pvd_runtime_artifacts"],
            "fixture": request["fixture"],
            "sanitized_environment_sha256": _canonical_sha256(dict(sorted(environment.items()))),
            "child_pid": child_pid,
            "child_pgid": child_pgid,
            "child_returncode": child_returncode,
            "runtime_receipt_sha256": _attestation_json_sha256(receipt)
            if isinstance(receipt, Mapping)
            else None,
            "child_report": _artifact(args.child_report_path, root=args.out_dir),
            "observation": _artifact(args.observation_path, root=args.out_dir),
            "pvd_actor_inventory": _artifact(args.pvd_actor_inventory_path, root=args.out_dir),
            "runtime_receipt": _artifact(args.runtime_receipt_path, root=args.out_dir),
            "stdout": _artifact(stdout_path, root=args.out_dir),
            "stderr": _artifact(stderr_path, root=args.out_dir),
            "report": _artifact(report_path, root=args.out_dir),
            "verification_failure": verification_failure,
            "child_log_diagnostic": log_diagnostic,
        }
        attestation.write_canonical_json(args.out_dir / MANIFEST_BASENAME, manifest)
    print(
        f"PVD effective-offset capability decision={report['decision']} out={args.out_dir / REPORT_BASENAME}",
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
    args.pvd_actor_inventory_path = args.out_dir / PVD_ACTOR_INVENTORY_BASENAME
    args.recording_dir = args.out_dir / "pvd-recording"
    args.conversion_dir = args.out_dir / "pvd-converted"
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
        "authority": "real_pbd_g0_effective_offset_capability_parent_report_v1",
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
            f"PVD effective-offset capability decision={RUNTIME_BLOCKED} out={args.out_dir / REPORT_BASENAME}",
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
