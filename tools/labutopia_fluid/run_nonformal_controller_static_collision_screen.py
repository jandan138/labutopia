#!/usr/bin/env python3
"""Run a sealed, diagnostic-only static screen of the v7 pick prefix.

The child derives native PickController outputs through the first close command,
teleports the paused Franka articulation to those configurations, and evaluates
conservative cooked-AABB pair results.  It does not advance physics, attach or
lift the source, observe contacts, or authorize G0 or any gate.
"""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import importlib
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils import nonformal_controller_static_collision_screen as screen


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
G0_GEOMETRY_MODULE = (
    REPO_ROOT / "tools/labutopia_fluid/run_real_pbd_grasp_v2_g0_geometry.py"
).resolve()
RUNTIME_IMPLEMENTATION_MODULE = (
    REPO_ROOT
    / "tools/labutopia_fluid/"
    "nonformal_controller_static_collision_screen_runtime.py"
).resolve()
SCREEN_CONTRACT_MODULE = (
    REPO_ROOT / "utils/nonformal_controller_static_collision_screen.py"
).resolve()

AUTHORITY = "nonformal_controller_static_collision_screen_v1"
CLASSIFICATION = "NON_FORMAL_STATIC_SCREEN_ONLY"
CANDIDATE_ID = "v7-native-pick-prefix-to-first-close"
CONTROLLER_CONFIGURATION_INVALID = "SCREEN_CONTROLLER_CONFIGURATION_INVALID"
SEMANTICS_ARTIFACT_NAME = "controller_semantics.json"
SEMANTICS_BLOCKED_DECISIONS = frozenset(
    (
        "NATIVE_TARGET_CONTRACT_INVALID",
        "DIRECT_STATIC_PROJECTION_UNSUPPORTED",
        "RAW_NATIVE_POSITION_TARGET_OUT_OF_LIMIT",
    )
)
EXPECTED_COLLIDER_INVENTORY = {
    "beaker1": 145,
    "full_robot": 11,
    "source_mesh": 1,
    "source_wrapper": 145,
    "table": 1,
}
AABB_NUMERICAL_MARGIN_M = 1.0e-6
NATIVE_PICK_FORWARD_PARAMETERS = {
    "pre_offset_x": 0.05,
    "pre_offset_z": 0.05,
    "after_offset_z": 0.5,
}


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


def _runtime_canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


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


def _write_bound_report_and_manifest(
    *,
    report_path: Path,
    report: Mapping[str, Any],
    manifest_path: Path,
    manifest: Mapping[str, Any],
    manifest_writer: Any,
) -> None:
    _write_create_only(report_path, report)
    bound_manifest = dict(manifest)
    bound_manifest["report_sha256"] = sha256_file(report_path)
    manifest_writer(manifest_path, bound_manifest)


def _read_canonical_line(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    if not payload.endswith(b"\n") or b"\r" in payload:
        raise ValueError("controller_static_screen_canonical_input_invalid")
    try:
        value = json.loads(payload[:-1].decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("controller_static_screen_canonical_input_invalid") from exc
    if not isinstance(value, Mapping) or _canonical_json_bytes(dict(value)) != payload:
        raise ValueError("controller_static_screen_canonical_input_invalid")
    return dict(value)


def _require_sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"controller_static_screen_{field}_invalid")
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
        "tools.labutopia_fluid.nonformal_controller_static_collision_screen_runtime"
    )


def _frozen_diagnostic(frozen: Mapping[str, Any]) -> Mapping[str, Any]:
    config = frozen.get("config")
    if not isinstance(config, Mapping):
        raise ValueError("controller_static_screen_frozen_config_invalid")
    diagnostic = config.get("diagnostic")
    if not isinstance(diagnostic, Mapping):
        raise ValueError("controller_static_screen_frozen_diagnostic_invalid")
    return diagnostic


def build_sealed_child_input(frozen: Mapping[str, Any]) -> dict[str, Any]:
    """Retain only JSON serializable, pre-bootstrap closure metadata."""
    if not isinstance(frozen, Mapping):
        raise ValueError("controller_static_screen_frozen_config_invalid")
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
        raise ValueError("controller_static_screen_frozen_config_fields_invalid")
    config = frozen["config"]
    canonical_bytes = frozen["canonical_bytes"]
    if (
        not isinstance(config, Mapping)
        or not isinstance(canonical_bytes, bytes)
        or canonical_bytes != _canonical_json_bytes(dict(config))
        or hashlib.sha256(canonical_bytes).hexdigest() != frozen["sha256"]
    ):
        raise ValueError("controller_static_screen_frozen_config_integrity_invalid")
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


def build_static_screen_contract(frozen: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the diagnostic screen to the exact v7 assets and pick treatment."""
    if not isinstance(frozen, Mapping):
        raise ValueError("controller_static_screen_frozen_config_invalid")
    diagnostic = _frozen_diagnostic(frozen)
    treatment = diagnostic.get("g0_native_pick_treatment")
    hidden_cube = diagnostic.get("hidden_cube_treatment")
    local_scene = frozen.get("local_scene")
    local_franka = frozen.get("local_franka")
    if (
        not isinstance(treatment, Mapping)
        or treatment.get("authority") != "g0_native_expert_pick_v9"
        or not isinstance(hidden_cube, Mapping)
        or not isinstance(local_scene, Mapping)
        or not isinstance(local_franka, Mapping)
    ):
        raise ValueError("controller_static_screen_v7_treatment_invalid")
    if hidden_cube.get("usd_path") != (
        "assets/chemistry_lab/lab_001_fluid_eval/"
        "lab_001_g0_disable_hidden_cube_collision_v1.usda"
    ) or hidden_cube.get("sha256") != sha256_file(HIDDEN_CUBE_OVERLAY):
        raise ValueError("controller_static_screen_hidden_cube_binding_invalid")
    payload = {
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "schema_version": 1,
        "v7_config_sha256": _require_sha256(frozen.get("sha256"), field="v7_config_sha256"),
        "local_scene_sha256": _require_sha256(
            local_scene.get("sha256"), field="local_scene_sha256"
        ),
        "local_franka_sha256": _require_sha256(
            local_franka.get("sha256"), field="local_franka_sha256"
        ),
        "hidden_cube_overlay_sha256": sha256_file(HIDDEN_CUBE_OVERLAY),
        "native_pick_treatment": dict(treatment),
        "native_pick_forward_parameters": dict(NATIVE_PICK_FORWARD_PARAMETERS),
        "candidate_ids": [CANDIDATE_ID],
        "expected_collider_inventory": dict(EXPECTED_COLLIDER_INVENTORY),
        "aabb_numerical_margin_m": AABB_NUMERICAL_MARGIN_M,
        "g0_or_gate_authorized": False,
        "post_reset_physics_steps_allowed": 0,
    }
    return {**payload, "sha256": screen.canonical_json_sha256(payload)}


def _internal_module_path(module: str) -> Path | None:
    if not module or module.split(".", 1)[0] not in {
        "factories",
        "tasks",
        "controllers",
        "robots",
        "utils",
        "data_collectors",
        "isaacsim_compat",
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
        if not isinstance(relative, str):
            raise ValueError("controller_static_screen_source_closure_invalid")
        path = (REPO_ROOT / relative).resolve()
        if not path.is_file() or not path.is_relative_to(REPO_ROOT):
            raise ValueError("controller_static_screen_source_closure_invalid")
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
            raise ValueError("controller_static_screen_source_closure_invalid") from exc
        package = path.relative_to(REPO_ROOT).with_suffix("").parts[:-1]
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    prefix = package[: max(0, len(package) - node.level + 1)]
                    suffix = tuple(node.module.split(".")) if node.module else ()
                    modules.append(".".join((*prefix, *suffix)))
                elif node.module:
                    modules.append(node.module)
            for module in modules:
                candidate = _internal_module_path(module)
                if candidate is not None:
                    queue.append(candidate.resolve())
    return visited


def _asset_dependency_paths(entry_path: Path) -> set[Path]:
    entry = entry_path.resolve()
    if not entry.is_file():
        raise ValueError("controller_static_screen_asset_closure_invalid")
    queue = [entry]
    visited: set[Path] = set()
    unresolved = []
    reference_pattern = re.compile(r"@([^@]+)@")
    while queue:
        path = queue.pop()
        if path in visited:
            continue
        visited.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for reference in reference_pattern.findall(text):
            if "://" in reference or reference.startswith("${"):
                unresolved.append(reference)
                continue
            target = (path.parent / reference).resolve()
            if target.is_file():
                queue.append(target)
            else:
                unresolved.append(reference)
    if unresolved or any(not path.is_file() for path in visited):
        raise ValueError("controller_static_screen_asset_closure_invalid")
    return visited


def source_paths(frozen: Mapping[str, Any]) -> tuple[Path, ...]:
    """Return the source and asset closure rehashed by the attested child."""
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
        raise ValueError("controller_static_screen_source_closure_invalid")
    source_seeds = [
        *required_files,
        "tools/labutopia_fluid/attest_isaac41_effective_runtime.py",
        "tools/labutopia_fluid/run_native_expert_empty_beaker_unbound_lift_probe.py",
        "tools/labutopia_fluid/run_real_pbd_grasp_v2_g0_geometry.py",
        "tools/labutopia_fluid/run_nonformal_controller_static_collision_screen.py",
        "tools/labutopia_fluid/nonformal_controller_static_collision_screen_runtime.py",
        "utils/nonformal_controller_static_collision_screen.py",
    ]
    python_closure = _python_import_paths(source_seeds)
    scene_closure = _asset_dependency_paths(
        Path(str(local_scene.get("absolute_usd_path"))).resolve()
    )
    robot_closure = _asset_dependency_paths(
        Path(str(local_franka.get("absolute_usd_path"))).resolve()
    )
    overlay_closure = _asset_dependency_paths(HIDDEN_CUBE_OVERLAY)
    candidates = {
        Path(__file__).resolve(),
        ATTESTATION_MODULE,
        NATIVE_RUNNER_MODULE,
        G0_GEOMETRY_MODULE,
        RUNTIME_IMPLEMENTATION_MODULE,
        SCREEN_CONTRACT_MODULE,
        Path(source_path).resolve(),
        Path(str(frozen.get("production_path", ""))).resolve(),
        HIDDEN_CUBE_OVERLAY,
        *python_closure,
        *scene_closure,
        *robot_closure,
        *overlay_closure,
    }
    if any(not path.is_file() for path in candidates):
        raise ValueError("controller_static_screen_source_closure_missing")
    return tuple(sorted(candidates))


def _screen_request(
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
        "contract_sha256": screen.canonical_json_sha256(contract),
        "frozen_config_path": str(frozen_config_path),
        "frozen_config_sha256": frozen_config_sha256,
    }


def _validate_screen_request(
    value: Any, *, frozen: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("controller_static_screen_request_invalid")
    request = dict(value)
    expected_fields = {
        "authority",
        "classification",
        "schema_version",
        "contract",
        "contract_sha256",
        "frozen_config_path",
        "frozen_config_sha256",
    }
    if set(request) != expected_fields:
        raise ValueError("controller_static_screen_request_fields_invalid")
    expected_contract = build_static_screen_contract(frozen)
    if (
        request["authority"] != AUTHORITY
        or request["classification"] != CLASSIFICATION
        or request["schema_version"] != 1
        or request["contract"] != expected_contract
        or request["contract_sha256"] != screen.canonical_json_sha256(expected_contract)
        or not isinstance(request["frozen_config_path"], str)
        or not Path(request["frozen_config_path"]).is_absolute()
    ):
        raise ValueError("controller_static_screen_request_contract_invalid")
    return {
        **request,
        "contract": expected_contract,
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
        raise ValueError("controller_static_screen_runtime_identity_invalid")
    payload = {
        "runtime_contract": dict(runtime_contract),
        "observed_runtime": dict(observed_runtime),
        "contract_sha256": screen.canonical_json_sha256(contract),
        "frozen_config_sha256": frozen_config_sha256,
    }
    return {"payload": payload, "sha256": screen.canonical_json_sha256(payload)}


def _blocked_report(
    runtime: Mapping[str, Any] | None,
    exc: BaseException,
    *,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "nonformal_controller_static_collision_screen_child_v1",
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
    runtime: dict[str, Any] | None = None
    contract: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    report_written = False
    try:
        frozen = _read_canonical_line(args.frozen_config)
        if sha256_file(args.frozen_config) != args.expected_frozen_config_sha256:
            raise RuntimeError("controller_static_screen_child_frozen_config_sha256_mismatch")
        request = _validate_screen_request(
            _read_canonical_line(args.screen_request), frozen=frozen
        )
        contract = request["contract"]
        if request["frozen_config_path"] != str(args.frozen_config):
            raise RuntimeError("controller_static_screen_child_frozen_config_path_mismatch")
        if request["frozen_config_sha256"] != args.expected_frozen_config_sha256:
            raise RuntimeError("controller_static_screen_child_frozen_config_binding_mismatch")
        attestation = _attestation_module()
        execution_request = attestation._read_canonical_json(args.execution_request)
        closure = source_paths(frozen)
        execution_request = attestation.verify_execution_request(
            execution_request, source_paths=closure
        )
        receipt, app = attestation.bootstrap_effective_runtime(
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
            "receipt_path": str(args.runtime_receipt_path),
            "receipt_sha256": attestation.canonical_json_sha256(receipt),
            "execution_binding": binding,
            "execution_request_sha256": attestation.canonical_json_sha256(
                execution_request
            ),
            "runtime_identity": _runtime_identity(
                receipt,
                contract=contract,
                frozen_config_sha256=args.expected_frozen_config_sha256,
            ),
        }
        report = _runtime_module().run_static_screen(
            app=app,
            out_dir=args.out_dir,
            frozen_config=frozen,
            contract=contract,
            runtime=runtime,
        )
        _write_create_only(args.child_report_path, report)
        report_written = True
    except BaseException as exc:
        report = _blocked_report(runtime, exc, contract=contract)
        if not args.child_report_path.exists():
            _write_create_only(args.child_report_path, report)
            report_written = True
    finally:
        if (
            app is not None
            and isinstance(report, Mapping)
            and report.get("decision") != "RUNTIME_BLOCKED"
        ):
            app.close()
    if report is None:
        raise RuntimeError("controller_static_screen_child_report_unavailable")
    if not report_written and not args.child_report_path.exists():
        _write_create_only(args.child_report_path, report)
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def _artifact_path(
    value: Any, *, root: Path, expected_name: str, minimum_record_count: int = 1
) -> tuple[Path, Mapping[str, Any]]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"path", "sha256", "stream_sha256", "record_count"}
        or value.get("path") != expected_name
        or type(value.get("record_count")) is not int
        or value["record_count"] < minimum_record_count
    ):
        raise RuntimeError("controller_static_screen_child_artifact_invalid")
    path = root / expected_name
    if path.is_symlink() or not path.is_file() or sha256_file(path) != value.get("sha256"):
        raise RuntimeError("controller_static_screen_child_artifact_invalid")
    _require_sha256(value.get("stream_sha256"), field="artifact_stream_sha256")
    return path, value


def _verify_controller_semantics_artifact(
    value: Any, *, root: Path
) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value)
        not in (
            {"artifact", "evaluation"},
            {"artifact", "evaluation", "qdot_counterfactual_evaluation"},
        )
        or not isinstance(value.get("artifact"), Mapping)
        or set(value["artifact"]) != {"path", "sha256"}
        or value["artifact"].get("path") != SEMANTICS_ARTIFACT_NAME
    ):
        raise RuntimeError("controller_static_screen_semantics_artifact_invalid")
    artifact_path = root / SEMANTICS_ARTIFACT_NAME
    if (
        artifact_path.is_symlink()
        or not artifact_path.is_file()
        or sha256_file(artifact_path) != value["artifact"].get("sha256")
    ):
        raise RuntimeError("controller_static_screen_semantics_artifact_invalid")
    try:
        raw = artifact_path.read_bytes()
        payload = json.loads(raw.decode("ascii"))
        canonical = _runtime_canonical_json_bytes(dict(payload))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError("controller_static_screen_semantics_artifact_invalid") from exc
    if not isinstance(payload, Mapping) or raw != canonical:
        raise RuntimeError("controller_static_screen_semantics_artifact_invalid")
    expected_payload_fields = {"schema_version", "manifest_type", "capture", "evaluation"}
    has_qdot_counterfactual = payload.get("schema_version") == 2
    if has_qdot_counterfactual:
        expected_payload_fields.update(
            {"qdot_counterfactual", "qdot_counterfactual_evaluation"}
        )
    if (
        set(payload) != expected_payload_fields
        or (
            not has_qdot_counterfactual
            and (
                payload.get("schema_version") != 1
                or payload.get("manifest_type")
                != "nonformal_native_pick_controller_semantics_v1"
            )
        )
        or (
            has_qdot_counterfactual
            and payload.get("manifest_type")
            != "nonformal_native_pick_controller_semantics_v2"
        )
        or not isinstance(payload.get("capture"), Mapping)
        or not isinstance(payload.get("evaluation"), Mapping)
    ):
        raise RuntimeError("controller_static_screen_semantics_artifact_invalid")
    evaluation = screen.evaluate_native_pick_semantics(payload["capture"])
    if payload["evaluation"] != evaluation or value.get("evaluation") != evaluation:
        raise RuntimeError("controller_static_screen_semantics_evaluation_invalid")
    decision = evaluation.get("decision")
    if decision not in {
        *SEMANTICS_BLOCKED_DECISIONS,
        "STATIC_PROJECTION_ELIGIBLE",
    } or not isinstance(evaluation.get("static_projection_authorized"), bool):
        raise RuntimeError("controller_static_screen_semantics_evaluation_invalid")
    qdot_counterfactual_evaluation = None
    if has_qdot_counterfactual:
        qdot_counterfactual_evaluation = screen.evaluate_rmp_qdot_counterfactual(
            payload["capture"], payload["qdot_counterfactual"]
        )
        if (
            payload["qdot_counterfactual_evaluation"]
            != qdot_counterfactual_evaluation
            or value.get("qdot_counterfactual_evaluation")
            != qdot_counterfactual_evaluation
            or decision != "RAW_NATIVE_POSITION_TARGET_OUT_OF_LIMIT"
        ):
            raise RuntimeError("controller_static_screen_qdot_counterfactual_invalid")
    elif decision == "RAW_NATIVE_POSITION_TARGET_OUT_OF_LIMIT":
        raise RuntimeError("controller_static_screen_qdot_counterfactual_missing")
    return {
        "artifact_sha256": value["artifact"]["sha256"],
        "decision": decision,
        "static_projection_authorized": evaluation["static_projection_authorized"],
        "raw_event0_action_sha256": evaluation.get("raw_event0_action_sha256"),
        "resolved_position_target_sha256": evaluation.get(
            "resolved_position_target_sha256"
        ),
        "joint_limit_violation_count": len(
            evaluation.get("position_limit_violations", [])
        ),
        "qdot_counterfactual_decision": (
            qdot_counterfactual_evaluation.get("decision")
            if isinstance(qdot_counterfactual_evaluation, Mapping)
            else None
        ),
    }


def _kit_gpu_identity(stdout_path: Path, environment: Mapping[str, str]) -> dict[str, Any]:
    if environment.get("NVIDIA_VISIBLE_DEVICES") != "4" or "CUDA_VISIBLE_DEVICES" in environment:
        raise RuntimeError("controller_static_screen_gpu_visibility_invalid")
    try:
        text = stdout_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("controller_static_screen_gpu_log_invalid") from exc
    driver = re.search(r"\|\s*Driver Version:\s*([^|]+?)\s*\|", text)
    gpu_rows = re.findall(
        r"^\|\s*(\d+)\s+\|\s*(.*?)\s+\|\s*Yes:\s*\d+\s*\|",
        text,
        flags=re.MULTILINE,
    )
    if driver is None or len(gpu_rows) != 1:
        raise RuntimeError("controller_static_screen_gpu_log_invalid")
    logical_index, name = gpu_rows[0]
    payload = {
        "authority": "kit_startup_gpu_identity_v1",
        "nvidia_visible_devices": environment["NVIDIA_VISIBLE_DEVICES"],
        "kit_logical_gpu_index": int(logical_index),
        "name": name.strip(),
        "driver_version": driver.group(1).strip(),
        "stdout_sha256": sha256_file(stdout_path),
    }
    return {**payload, "sha256": screen.canonical_json_sha256(payload)}


def _iter_canonical_gzip_records(
    path: Path,
    *,
    counter: dict[str, Any],
    trace_summaries: dict[int, tuple[int, tuple[float, ...], str]] | None = None,
    numerical_margin_m: float | None = None,
) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rb") as stream:
        for line in stream:
            if not line.endswith(b"\n") or b"\r" in line:
                raise RuntimeError("controller_static_screen_child_trace_invalid")
            try:
                value = json.loads(line[:-1].decode("ascii"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("controller_static_screen_child_trace_invalid") from exc
            if not isinstance(value, Mapping) or _canonical_json_bytes(dict(value)) != line:
                raise RuntimeError("controller_static_screen_child_trace_invalid")
            if trace_summaries is not None:
                sample_index = value.get("sample_index")
                event = value.get("controller_event")
                positions = value.get("joint_positions")
                action_sha256 = value.get("action_sha256")
                pair_results = value.get("pair_results")
                if (
                    type(sample_index) is not int
                    or type(event) is not int
                    or not isinstance(positions, list)
                    or not isinstance(action_sha256, str)
                    or not isinstance(pair_results, list)
                    or sample_index in trace_summaries
                    or numerical_margin_m is None
                ):
                    raise RuntimeError("controller_static_screen_child_trace_invalid")
                for result in pair_results:
                    lower_bound = (
                        result.get("lower_bound_m") if isinstance(result, Mapping) else None
                    )
                    if (
                        isinstance(lower_bound, bool)
                        or not isinstance(lower_bound, (int, float))
                        or not math.isfinite(float(lower_bound))
                        or float(lower_bound) < 0.0
                        or result.get("status")
                        != (
                            "CLEAR"
                            if float(lower_bound) > numerical_margin_m
                            else "POTENTIAL_OVERLAP_OR_MARGIN"
                        )
                    ):
                        raise RuntimeError("controller_static_screen_child_trace_numeric_invalid")
                trace_summaries[sample_index] = (
                    event,
                    tuple(float(item) for item in positions),
                    action_sha256,
                )
            counter["count"] += 1
            counter["digest"].update(line)
            yield dict(value)


def _verify_screen_artifacts(
    screen_report: Mapping[str, Any],
    *,
    collision_scope: Mapping[str, Any],
    numerical_margin_m: float,
    root: Path,
) -> dict[str, Any]:
    required = {
        "candidate_id",
        "controller",
        "object_geometry",
        "evaluation",
        "selection",
        "configuration_pair_trace",
        "controller_action_ledger",
    }
    if set(screen_report) != required or screen_report.get("candidate_id") != CANDIDATE_ID:
        raise RuntimeError("controller_static_screen_child_screen_invalid")
    screen_scope = {
        "blocking_pairs": collision_scope.get("blocking_pairs"),
        "allowed_source_shell_pairs": collision_scope.get("allowed_source_shell_pairs"),
    }
    trace_path, trace_record = _artifact_path(
        screen_report["configuration_pair_trace"],
        root=root,
        expected_name="configuration_pair_trace.jsonl.gz",
    )
    trace_counter = {"count": 0, "digest": hashlib.sha256()}
    trace_summaries: dict[int, tuple[int, tuple[float, ...], str]] = {}
    evaluation = screen.evaluate_configuration_trace(
        screen_scope,
        _iter_canonical_gzip_records(
            trace_path,
            counter=trace_counter,
            trace_summaries=trace_summaries,
            numerical_margin_m=numerical_margin_m,
        ),
    )
    if (
        trace_counter["count"] != trace_record["record_count"]
        or trace_counter["digest"].hexdigest() != trace_record["stream_sha256"]
        or screen_report.get("evaluation") != evaluation
    ):
        raise RuntimeError("controller_static_screen_child_trace_verification_invalid")
    selection = screen.select_candidate(
        [{"candidate_id": CANDIDATE_ID, **evaluation}]
    )
    if screen_report.get("selection") != selection:
        raise RuntimeError("controller_static_screen_child_selection_invalid")

    action_path, action_record = _artifact_path(
        screen_report["controller_action_ledger"],
        root=root,
        expected_name="controller_action_ledger.jsonl.gz",
    )
    action_counter = {"count": 0, "digest": hashlib.sha256()}
    events = []
    bound_sample_indices = set()
    for expected_ordinal, record in enumerate(
        _iter_canonical_gzip_records(action_path, counter=action_counter)
    ):
        if (
            record.get("action_ordinal") != expected_ordinal
            or type(record.get("controller_event")) is not int
            or record["controller_event"] < -1
            or record["controller_event"] > 4
            or not isinstance(record.get("action"), Mapping)
            or record.get("action_sha256")
            != screen.canonical_json_sha256(record["action"])
            or type(record.get("screen_sample_index")) is not int
            or record["screen_sample_index"] not in trace_summaries
            or trace_summaries[record["screen_sample_index"]]
            != (
                record["controller_event"],
                tuple(float(item) for item in record.get("joint_positions_after", [])),
                record["action_sha256"],
            )
        ):
            raise RuntimeError("controller_static_screen_child_action_ledger_invalid")
        events.append(record["controller_event"])
        bound_sample_indices.add(record["screen_sample_index"])
    if (
        action_counter["count"] != action_record["record_count"]
        or action_counter["digest"].hexdigest() != action_record["stream_sha256"]
        or not events
        or events[-1] != 4
        or events.count(4) != 1
        or bound_sample_indices != set(trace_summaries)
    ):
        raise RuntimeError("controller_static_screen_child_action_ledger_invalid")
    return {
        "evaluation": evaluation,
        "selection": selection,
        "trace_record_count": trace_counter["count"],
        "action_record_count": action_counter["count"],
    }


def _finite_float_vector(
    value: Any, *, field: str, length: int | None = None
) -> list[float]:
    if (
        not isinstance(value, list)
        or (length is not None and len(value) != length)
        or not value
    ):
        raise RuntimeError(f"controller_static_screen_child_{field}_invalid")
    normalized = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise RuntimeError(f"controller_static_screen_child_{field}_invalid")
        number = float(item)
        if not math.isfinite(number):
            raise RuntimeError(f"controller_static_screen_child_{field}_invalid")
        normalized.append(number)
    return normalized


def _verify_partial_trace_pair_coverage(
    record: Mapping[str, Any], *, collision_scope: Mapping[str, Any]
) -> None:
    try:
        normalized_scope = screen._normalized_scope(collision_scope)
    except ValueError as exc:
        raise RuntimeError("controller_static_screen_child_trace_coverage_invalid") from exc
    expected_pairs = {
        tuple(pair): "BLOCKING" for pair in normalized_scope["blocking_pairs"]
    }
    expected_pairs.update(
        {
            tuple(pair): "ALLOWED_SOURCE_SHELL_FINGER"
            for pair in normalized_scope["allowed_source_shell_pairs"]
        }
    )
    _finite_float_vector(
        record.get("joint_positions"), field="trace_joint_positions", length=9
    )
    results = record.get("pair_results")
    if not isinstance(results, list):
        raise RuntimeError("controller_static_screen_child_trace_coverage_invalid")
    observed: dict[tuple[str, str], str] = {}
    for result in results:
        pair = result.get("pair") if isinstance(result, Mapping) else None
        if (
            not isinstance(result, Mapping)
            or set(result) != {"pair", "classification", "status", "lower_bound_m"}
            or not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(path, str) for path in pair)
            or tuple(pair) not in expected_pairs
            or tuple(pair) in observed
            or result.get("classification") != expected_pairs[tuple(pair)]
        ):
            raise RuntimeError("controller_static_screen_child_trace_coverage_invalid")
        observed[tuple(pair)] = str(result["status"])
    if set(observed) != set(expected_pairs):
        raise RuntimeError("controller_static_screen_child_trace_coverage_invalid")


def _verify_invalid_controller_action(
    action: Mapping[str, Any], *, controller: Mapping[str, Any]
) -> None:
    required = {
        "action_ordinal",
        "controller_event_before",
        "controller_event",
        "action",
        "discarded_joint_velocities",
        "action_sha256",
        "joint_positions_before",
        "resolved_joint_positions",
        "changed_joint_indices",
        "is_hold",
        "joint_limit_violations",
        "outcome",
    }
    if (
        set(action) != required
        or action.get("outcome") != "JOINT_LIMIT_REJECTED"
        or type(action.get("action_ordinal")) is not int
        or action["action_ordinal"] < 0
        or type(action.get("controller_event_before")) is not int
        or action["controller_event_before"] < 0
        or action["controller_event_before"] > 4
        or type(action.get("controller_event")) is not int
        or action["controller_event"] < -1
        or action["controller_event"] > 4
        or not isinstance(action.get("action"), Mapping)
        or action.get("action_sha256")
        != screen.canonical_json_sha256(action["action"])
        or action.get("is_hold") is not False
        or not isinstance(action.get("changed_joint_indices"), list)
        or any(type(index) is not int for index in action["changed_joint_indices"])
        or not isinstance(action.get("joint_limit_violations"), list)
        or not action["joint_limit_violations"]
    ):
        raise RuntimeError("controller_static_screen_child_invalid_action_invalid")
    discarded = action["discarded_joint_velocities"]
    if discarded is not None:
        _finite_float_vector(discarded, field="discarded_joint_velocities")
    before = _finite_float_vector(
        action["joint_positions_before"], field="joint_positions_before", length=9
    )
    resolved_positions = _finite_float_vector(
        action["resolved_joint_positions"], field="resolved_joint_positions", length=9
    )
    try:
        resolved = screen.resolve_joint_configuration(before, action["action"])
    except ValueError as exc:
        raise RuntimeError("controller_static_screen_child_invalid_action_invalid") from exc
    if (
        resolved["joint_positions"] != resolved_positions
        or resolved["changed_joint_indices"] != action["changed_joint_indices"]
        or resolved["is_hold"] is not False
    ):
        raise RuntimeError("controller_static_screen_child_invalid_action_invalid")
    lower = _finite_float_vector(
        controller.get("joint_lower_limits"), field="joint_lower_limits", length=9
    )
    upper = _finite_float_vector(
        controller.get("joint_upper_limits"), field="joint_upper_limits", length=9
    )
    if any(lower_value >= upper_value for lower_value, upper_value in zip(lower, upper)):
        raise RuntimeError("controller_static_screen_child_invalid_action_invalid")
    seen_indices = set()
    for violation in action["joint_limit_violations"]:
        if (
            not isinstance(violation, Mapping)
            or set(violation) != {"index", "target", "lower", "upper"}
            or type(violation.get("index")) is not int
            or violation["index"] < 0
            or violation["index"] >= len(resolved_positions)
            or violation["index"] in seen_indices
        ):
            raise RuntimeError("controller_static_screen_child_invalid_action_invalid")
        seen_indices.add(violation["index"])
        values = []
        for field in ("target", "lower", "upper"):
            value = violation[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise RuntimeError("controller_static_screen_child_invalid_action_invalid")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise RuntimeError("controller_static_screen_child_invalid_action_invalid")
            values.append(numeric)
        target, lower_value, upper_value = values
        index = violation["index"]
        if (
            target != resolved_positions[index]
            or lower_value != lower[index]
            or upper_value != upper[index]
            or not (target < lower_value or target > upper_value)
        ):
            raise RuntimeError("controller_static_screen_child_invalid_action_invalid")


def _verify_controller_configuration_invalid_artifacts(
    screen_report: Mapping[str, Any],
    *,
    collision_scope: Mapping[str, Any],
    numerical_margin_m: float,
    root: Path,
) -> dict[str, Any]:
    required = {
        "candidate_id",
        "controller",
        "object_geometry",
        "invalid_controller_action",
        "selection",
        "configuration_pair_trace",
        "controller_action_ledger",
    }
    selection = {
        "decision": CONTROLLER_CONFIGURATION_INVALID,
        "selected_candidate_id": None,
        "passing_candidate_ids": [],
    }
    if (
        set(screen_report) != required
        or screen_report.get("candidate_id") != CANDIDATE_ID
        or not isinstance(screen_report.get("controller"), Mapping)
        or screen_report.get("selection") != selection
        or not isinstance(screen_report.get("invalid_controller_action"), Mapping)
    ):
        raise RuntimeError("controller_static_screen_child_invalid_configuration_invalid")
    trace_path, trace_record = _artifact_path(
        screen_report["configuration_pair_trace"],
        root=root,
        expected_name="configuration_pair_trace.jsonl.gz",
        minimum_record_count=0,
    )
    trace_counter = {"count": 0, "digest": hashlib.sha256()}
    trace_summaries: dict[int, tuple[int, tuple[float, ...], str]] = {}
    for record in _iter_canonical_gzip_records(
        trace_path,
        counter=trace_counter,
        trace_summaries=trace_summaries,
        numerical_margin_m=numerical_margin_m,
    ):
        _verify_partial_trace_pair_coverage(record, collision_scope=collision_scope)
    if (
        trace_counter["count"] != trace_record["record_count"]
        or trace_counter["digest"].hexdigest() != trace_record["stream_sha256"]
    ):
        raise RuntimeError("controller_static_screen_child_invalid_trace_verification_invalid")
    action_path, action_record = _artifact_path(
        screen_report["controller_action_ledger"],
        root=root,
        expected_name="controller_action_ledger.jsonl.gz",
    )
    action_counter = {"count": 0, "digest": hashlib.sha256()}
    bound_sample_indices = set()
    events = []
    rejected_actions = []
    normal_required = {
        "action_ordinal",
        "controller_event_before",
        "controller_event",
        "action",
        "discarded_joint_velocities",
        "action_sha256",
        "joint_positions_before",
        "joint_positions_after",
        "changed_joint_indices",
        "is_hold",
        "screen_sample_index",
    }
    for expected_ordinal, record in enumerate(
        _iter_canonical_gzip_records(action_path, counter=action_counter)
    ):
        if (
            record.get("action_ordinal") != expected_ordinal
            or type(record.get("controller_event")) is not int
            or record["controller_event"] < -1
            or record["controller_event"] > 4
        ):
            raise RuntimeError("controller_static_screen_child_invalid_action_ledger_invalid")
        events.append(record["controller_event"])
        if record.get("outcome") == "JOINT_LIMIT_REJECTED":
            rejected_actions.append(record)
            continue
        if (
            set(record) != normal_required
            or not isinstance(record.get("action"), Mapping)
            or record.get("action_sha256")
            != screen.canonical_json_sha256(record["action"])
            or type(record.get("screen_sample_index")) is not int
            or record["screen_sample_index"] not in trace_summaries
            or trace_summaries[record["screen_sample_index"]]
            != (
                record["controller_event"],
                tuple(
                    _finite_float_vector(
                        record.get("joint_positions_after"),
                        field="action_joint_positions_after",
                        length=9,
                    )
                ),
                record["action_sha256"],
            )
        ):
            raise RuntimeError("controller_static_screen_child_invalid_action_ledger_invalid")
        bound_sample_indices.add(record["screen_sample_index"])
    invalid_action = screen_report["invalid_controller_action"]
    if (
        action_counter["count"] != action_record["record_count"]
        or action_counter["digest"].hexdigest() != action_record["stream_sha256"]
        or len(rejected_actions) != 1
        or rejected_actions[0] != invalid_action
        or rejected_actions[0].get("action_ordinal") != action_counter["count"] - 1
        or bound_sample_indices != set(trace_summaries)
        or screen_report["controller"].get("event_sequence") != events
        or screen_report["controller"].get("lift_command_emitted") is not False
        or not isinstance(screen_report["controller"].get("first_close_emitted"), bool)
    ):
        raise RuntimeError("controller_static_screen_child_invalid_action_ledger_invalid")
    _verify_invalid_controller_action(
        invalid_action, controller=screen_report["controller"]
    )
    return {
        "selection": selection,
        "trace_record_count": trace_counter["count"],
        "action_record_count": action_counter["count"],
        "invalid_action_ordinal": invalid_action["action_ordinal"],
        "joint_limit_violation_count": len(invalid_action["joint_limit_violations"]),
    }


def _verify_child_report(
    child_report: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    runtime_receipt_sha256: str,
    expected_binding: Mapping[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    if (
        child_report.get("authority") != AUTHORITY
        or child_report.get("classification") != CLASSIFICATION
        or child_report.get("contract") != dict(contract)
    ):
        raise RuntimeError("controller_static_screen_child_contract_invalid")
    runtime = child_report.get("runtime")
    if not isinstance(runtime, Mapping):
        raise RuntimeError("controller_static_screen_child_runtime_missing")
    if (
        runtime.get("receipt_sha256") != runtime_receipt_sha256
        or runtime.get("execution_binding") != dict(expected_binding)
    ):
        raise RuntimeError("controller_static_screen_child_runtime_binding_invalid")
    decision = child_report.get("decision")
    if decision == "RUNTIME_BLOCKED":
        return dict(child_report)
    if decision not in {
        "SCREEN_SELECTED_DIAGNOSTIC_ONLY",
        "SCREEN_NO_CANDIDATE",
        "SCREEN_AMBIGUOUS_CANDIDATES",
        CONTROLLER_CONFIGURATION_INVALID,
        *SEMANTICS_BLOCKED_DECISIONS,
    }:
        raise RuntimeError("controller_static_screen_child_decision_invalid")
    scope = child_report.get("scope")
    timeline = child_report.get("timeline")
    collision_scope = child_report.get("collision_scope")
    controller_semantics = child_report.get("controller_semantics")
    screen_report = child_report.get("screen")
    post_reset_advance = (
        scope.get("post_reset_physics_advance")
        if isinstance(scope, Mapping)
        else None
    )
    reset_bootstrap_advance = (
        scope.get("reset_bootstrap_advance") if isinstance(scope, Mapping) else None
    )
    if (
        not isinstance(scope, Mapping)
        or scope.get("reset_bootstrap_permitted") is not True
        or not isinstance(reset_bootstrap_advance, Mapping)
        or type(reset_bootstrap_advance.get("world_index_delta")) is not int
        or reset_bootstrap_advance["world_index_delta"] < 0
        or scope.get("post_reset_physics_steps_allowed") != 0
        or not isinstance(post_reset_advance, Mapping)
        or post_reset_advance.get("verified_zero") is not True
        or scope.get("source_attachment_or_lift") is not False
        or scope.get("runtime_contact_observer") is not False
        or scope.get("g0_or_gate_evaluated") is not False
        or not isinstance(timeline, Mapping)
        or timeline.get("unchanged") is not True
        or not isinstance(timeline.get("pre_reset_cooked_query"), Mapping)
        or timeline["pre_reset_cooked_query"].get("is_playing") is not False
        or timeline["pre_reset_cooked_query"].get("is_stopped") is not True
        or not isinstance(timeline.get("baseline"), Mapping)
        or not isinstance(timeline.get("final"), Mapping)
        or timeline["baseline"] != timeline["final"]
        or timeline["baseline"].get("is_playing") is not False
        or timeline["baseline"].get("is_stopped") is not False
        or not isinstance(collision_scope, Mapping)
        or len(collision_scope.get("allowed_source_shell_pairs", [])) != 2
        or len(collision_scope.get("blocking_pairs", [])) != 3210
        or not isinstance(controller_semantics, Mapping)
        or (
            decision in SEMANTICS_BLOCKED_DECISIONS and screen_report is not None
        )
        or (
            decision not in SEMANTICS_BLOCKED_DECISIONS
            and not isinstance(screen_report, Mapping)
        )
    ):
        raise RuntimeError("controller_static_screen_child_scope_invalid")
    numerical_margin_m = contract.get("aabb_numerical_margin_m")
    if (
        isinstance(numerical_margin_m, bool)
        or not isinstance(numerical_margin_m, (int, float))
        or not math.isfinite(float(numerical_margin_m))
        or float(numerical_margin_m) < 0.0
    ):
        raise RuntimeError("controller_static_screen_child_margin_invalid")
    semantics_verification = _verify_controller_semantics_artifact(
        controller_semantics, root=out_dir
    )
    if scope.get("controller_semantics_gate") != semantics_verification["decision"]:
        raise RuntimeError("controller_static_screen_child_semantics_gate_invalid")
    if decision in SEMANTICS_BLOCKED_DECISIONS:
        if (
            semantics_verification["decision"] != decision
            or semantics_verification["static_projection_authorized"] is not False
        ):
            raise RuntimeError("controller_static_screen_child_semantics_decision_invalid")
        verified = dict(child_report)
        verified["artifact_verification"] = {
            "controller_semantics": semantics_verification
        }
        return verified
    if (
        semantics_verification["decision"] != "STATIC_PROJECTION_ELIGIBLE"
        or semantics_verification["static_projection_authorized"] is not True
    ):
        raise RuntimeError("controller_static_screen_child_semantics_gate_invalid")
    controller_report = screen_report.get("controller")
    if (
        not isinstance(controller_report, Mapping)
        or controller_report.get("audited_event0_raw_action_sha256")
        != semantics_verification["raw_event0_action_sha256"]
    ):
        raise RuntimeError("controller_static_screen_child_semantics_action_binding_invalid")
    if decision == CONTROLLER_CONFIGURATION_INVALID:
        artifact_verification = _verify_controller_configuration_invalid_artifacts(
            screen_report,
            collision_scope={
                "blocking_pairs": collision_scope["blocking_pairs"],
                "allowed_source_shell_pairs": collision_scope[
                    "allowed_source_shell_pairs"
                ],
            },
            numerical_margin_m=float(numerical_margin_m),
            root=out_dir,
        )
    else:
        artifact_verification = _verify_screen_artifacts(
            screen_report,
            collision_scope=collision_scope,
            numerical_margin_m=float(numerical_margin_m),
            root=out_dir,
        )
    if decision != artifact_verification["selection"]["decision"]:
        raise RuntimeError("controller_static_screen_child_decision_mismatch")
    artifact_verification["controller_semantics"] = semantics_verification
    verified = dict(child_report)
    verified["artifact_verification"] = artifact_verification
    return verified


def _run_parent(args: argparse.Namespace) -> int:
    args.out_dir.mkdir(parents=True, mode=0o700)
    native = _native_module()
    frozen = native.freeze_diagnostic_config(args.config)
    sealed_frozen = build_sealed_child_input(frozen)
    contract = build_static_screen_contract(sealed_frozen)
    frozen_config_path = args.out_dir / "frozen_v7_config.json"
    _write_create_only(frozen_config_path, sealed_frozen)
    frozen_config_sha256 = sha256_file(frozen_config_path)
    if _read_canonical_line(frozen_config_path) != sealed_frozen:
        raise RuntimeError("controller_static_screen_frozen_config_publish_mismatch")
    screen_request = _screen_request(
        contract=contract,
        frozen_config_path=frozen_config_path,
        frozen_config_sha256=frozen_config_sha256,
    )
    screen_request_path = args.out_dir / "screen_request.json"
    _write_create_only(screen_request_path, screen_request)

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
        "--screen-request",
        str(screen_request_path),
        "--execution-request",
        str(execution_request_path),
    ]
    stdout_path = args.out_dir / "child.stdout.log"
    stderr_path = args.out_dir / "child.stderr.log"
    child_pid: int | None = None
    child_returncode: int | None = None
    receipt: Mapping[str, Any] | None = None
    verification_failure = None
    source_after = None
    gpu_identity = None
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
                raise RuntimeError("controller_static_screen_child_timeout") from exc
        gpu_identity = _kit_gpu_identity(stdout_path, environment)
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
            out_dir=args.out_dir,
        )
        expected_returncode = 2 if report.get("decision") == "RUNTIME_BLOCKED" else 0
        if child_returncode != expected_returncode:
            raise RuntimeError("controller_static_screen_child_exit_status_invalid")
        source_after = attestation.capture_source_identity(closure)
        if source_after != source_before:
            raise RuntimeError("controller_static_screen_source_changed_during_run")
        report["parent_verification"] = {
            "verified": True,
            "execution_request_sha256": attestation.canonical_json_sha256(
                execution_request
            ),
            "screen_request_sha256": sha256_file(screen_request_path),
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "child_report_sha256": sha256_file(args.child_report_path),
            "runtime_receipt_sha256": attestation.canonical_json_sha256(receipt),
            "stdout_sha256": sha256_file(stdout_path),
            "stderr_sha256": sha256_file(stderr_path),
            "gpu": gpu_identity,
        }
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        report = _blocked_report(None, exc, contract=contract)
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
            "gpu": gpu_identity,
        }
    finally:
        if source_after is None:
            source_after = attestation.capture_source_identity(closure)
        manifest = {
            "schema_version": 1,
            "manifest_type": "nonformal_controller_static_collision_screen_parent_v1",
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "command": command,
            "contract_sha256": screen.canonical_json_sha256(contract),
            "execution_request_sha256": attestation.canonical_json_sha256(
                execution_request
            ),
            "screen_request_sha256": sha256_file(screen_request_path),
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
            "gpu": gpu_identity,
            "child_report_sha256": (
                sha256_file(args.child_report_path)
                if args.child_report_path.is_file()
                else None
            ),
            "verification_failure": verification_failure,
        }
    _write_bound_report_and_manifest(
        report_path=args.out_dir / "report.json",
        report=report,
        manifest_path=args.out_dir / "run_manifest.json",
        manifest=manifest,
        manifest_writer=attestation.write_canonical_json,
    )
    print(
        f"controller static screen decision={report['decision']} "
        f"out={args.out_dir / 'report.json'}",
        flush=True,
    )
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--frozen-config", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-frozen-config-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--screen-request", type=Path, help=argparse.SUPPRESS)
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
        args.screen_request,
        args.execution_request,
    )
    if args.child:
        if any(value is None for value in child_values):
            parser.error("--child requires all sealed request paths")
        args.frozen_config = args.frozen_config.resolve()
        args.screen_request = args.screen_request.resolve()
        args.execution_request = args.execution_request.resolve()
        if (
            not args.out_dir.is_dir()
            or not args.frozen_config.is_file()
            or not args.screen_request.is_file()
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
    else:
        if any(value is not None for value in child_values):
            parser.error("sealed child options are child-only")
        if args.out_dir.exists():
            parser.error("out-dir must not exist")
    args.child_report_path = args.out_dir / "child_report.json"
    args.runtime_receipt_path = args.out_dir / "runtime_receipt.json"
    return args


def _write_parent_preflight_blocked(args: argparse.Namespace, exc: BaseException) -> None:
    if not args.out_dir.is_dir():
        return
    report_path = args.out_dir / "report.json"
    manifest_path = args.out_dir / "run_manifest.json"
    failure = {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
    if not report_path.exists():
        _write_create_only(
            report_path,
            {
                "schema_version": 1,
                "manifest_type": "nonformal_controller_static_collision_screen_parent_v1",
                "authority": AUTHORITY,
                "classification": CLASSIFICATION,
                "decision": "RUNTIME_BLOCKED",
                "contract": None,
                "runtime": None,
                "preflight_failure": failure,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
    if not manifest_path.exists():
        _write_create_only(
            manifest_path,
            {
                "schema_version": 1,
                "manifest_type": "nonformal_controller_static_collision_screen_parent_v1",
                "authority": AUTHORITY,
                "classification": CLASSIFICATION,
                "decision": "RUNTIME_BLOCKED",
                "preflight_failure": failure,
                "report_sha256": sha256_file(report_path),
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
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
            f"controller static screen decision=RUNTIME_BLOCKED "
            f"out={args.out_dir / 'report.json'}",
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
