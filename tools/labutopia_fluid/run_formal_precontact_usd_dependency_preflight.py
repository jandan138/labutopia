#!/usr/bin/env python3
"""Attest the complete local USD dependency closure before a formal replay."""

from __future__ import annotations

import argparse
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

from tools.labutopia_fluid import run_nonformal_controller_static_collision_screen as legacy
from utils import formal_precontact_event0_snapshot_replay as snapshot_replay
from utils import formal_precontact_usd_dependency_closure as closure_contract


AUTHORITY = "formal_precontact_usd_dependency_preflight_v1"
CLASSIFICATION = "FORMAL_USD_DEPENDENCY_CLOSURE_PREFLIGHT_ONLY"
CLOSURE_NAME = "usd_dependency_closure.json"
INPUT_NAME = "usd_dependency_preflight_input.json"
PURE_MODULE = (REPO_ROOT / "utils/formal_precontact_usd_dependency_closure.py").resolve()
RUNTIME_MODULE = Path(__file__).resolve()
LEGACY_MODULE = Path(legacy.__file__).resolve()
SNAPSHOT_REPLAY_MODULE = Path(snapshot_replay.__file__).resolve()
APPROVED_RUNTIME_MDL_DEPENDENCIES = (
    {
        "purpose": "kit_mdl_material_root",
        "path": (
            "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
            "embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/"
            "site-packages/omni/mdl/core/Base/OmniGlass.mdl"
        ),
        "sha256": "d71555550deb30af245c0ec939c8647442df5709a2977549cad7f6ddcc8c1182",
    },
    {
        "purpose": "kit_mdl_material_root",
        "path": (
            "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
            "embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/"
            "site-packages/omni/mdl/core/Base/OmniPBR.mdl"
        ),
        "sha256": "e0591cdda9f21eb61360a39919a82bbff8b8a872344d89c67e6b245dae974c3b",
    },
    {
        "purpose": "kit_mdl_material_root",
        "path": (
            "/cpfs/shared/simulation/zhuzihou/dev/conda-managed/envs/"
            "embodied-eval-os-sim-isaacsim41-genmanip-py310/lib/python3.10/"
            "site-packages/omni/mdl/core/Base/OmniSurfacePresets.mdl"
        ),
        "sha256": "5c86c8545a1e215ec4b99e60eb66f9112ca5952cc66ca13ec0c26687dcfcb930",
    },
)
MDL_CORE_ROOT = Path(APPROVED_RUNTIME_MDL_DEPENDENCIES[0]["path"]).parents[1]
MDL_BASE_ROOT = MDL_CORE_ROOT / "Base"
MDL_LIBRARY_ROOT = MDL_CORE_ROOT / "mdl"
MDL_STANDARD_LIBRARY_MODULES = frozenset(
    {"::anno", "::base", "::debug", "::df", "::limits", "::math", "::state", "::tex"}
)
_MDL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_MDL_LINE_COMMENT = re.compile(r"//[^\n]*")
_MDL_IMPORT = re.compile(
    r"(?m)^\s*(?:export\s+)?(?:import|using)\s+((?:::|\.::)?[A-Za-z_][A-Za-z0-9_:]*)"
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_regular_file_without_symlink_components(path: Path) -> bool:
    candidate = Path(path)
    if not candidate.is_absolute():
        return False
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            return False
    try:
        return candidate.is_file() and candidate.resolve(strict=True) == candidate
    except OSError:
        return False


def _is_regular_file_under(path: Path, root: Path) -> bool:
    candidate = Path(path)
    try:
        return candidate.is_relative_to(root) and _is_regular_file_without_symlink_components(
            candidate
        )
    except ValueError:
        return False


def _profile_from_path(path: Path) -> dict[str, Any]:
    candidate = Path(path)
    resolved = candidate.resolve()
    if (
        candidate.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(REPO_ROOT)
    ):
        raise ValueError("formal_usd_dependency_profile_invalid")
    try:
        raw = json.loads(resolved.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("formal_usd_dependency_profile_invalid") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("formal_usd_dependency_profile_invalid")
    return snapshot_replay.validate_fixed_mount_profile(
        {
            **dict(raw),
            "profile_path": str(resolved.relative_to(REPO_ROOT)),
            "profile_sha256": _sha256_file(resolved),
        }
    )


def build_input(
    frozen: Mapping[str, Any], *, fixed_mount_profile: Mapping[str, Any]
) -> dict[str, Any]:
    profile = snapshot_replay.validate_fixed_mount_profile(fixed_mount_profile)
    diagnostic = legacy._frozen_diagnostic(frozen)
    local_scene = frozen.get("local_scene")
    local_franka = frozen.get("local_franka")
    hidden_cube = diagnostic.get("hidden_cube_treatment")
    if (
        not isinstance(local_scene, Mapping)
        or not isinstance(local_franka, Mapping)
        or not isinstance(hidden_cube, Mapping)
        or not isinstance(frozen.get("sha256"), str)
    ):
        raise ValueError("formal_usd_dependency_input_invalid")
    entries = [
        {
            "role": "fixed_mount_filter_overlay",
            "path": profile["filter"]["overlay_path"],
            "sha256": profile["filter"]["overlay_sha256"],
        },
        {
            "role": "hidden_cube_overlay",
            "path": hidden_cube.get("usd_path"),
            "sha256": hidden_cube.get("sha256"),
        },
        {
            "role": "local_franka",
            "path": local_franka.get("usd_path"),
            "sha256": local_franka.get("sha256"),
        },
        {
            "role": "local_scene",
            "path": local_scene.get("usd_path"),
            "sha256": local_scene.get("sha256"),
        },
    ]
    return closure_contract.build_input(
        v7_config_sha256=frozen["sha256"],
        fixed_mount_profile_sha256=profile["profile_sha256"],
        approved_runtime_mdl_dependencies=APPROVED_RUNTIME_MDL_DEPENDENCIES,
        entries=entries,
    )


def _input_paths(input_record: Mapping[str, Any]) -> tuple[Path, ...]:
    normalized = closure_contract.validate_input(input_record)
    paths = [REPO_ROOT / entry["path"] for entry in normalized["entries"]]
    if any(not _is_regular_file_under(path, REPO_ROOT) for path in paths):
        raise ValueError("formal_usd_dependency_input_files_invalid")
    return tuple(path.resolve() for path in paths)


def source_paths(input_record: Mapping[str, Any], *, profile_path: Path) -> tuple[Path, ...]:
    profile = Path(profile_path)
    paths = {
        RUNTIME_MODULE,
        PURE_MODULE,
        LEGACY_MODULE,
        SNAPSHOT_REPLAY_MODULE,
        legacy.ATTESTATION_MODULE,
        profile,
        *_input_paths(input_record),
    }
    if any(
        not _is_regular_file_under(path, REPO_ROOT)
        for path in paths
    ):
        raise ValueError("formal_usd_dependency_source_closure_invalid")
    return tuple(sorted(paths))


def repository_closure_paths(manifest: Mapping[str, Any]) -> tuple[Path, ...]:
    normalized = closure_contract.verify_manifest_files(manifest, repo_root=REPO_ROOT)
    if normalized["status"] != closure_contract.PASS:
        raise ValueError("formal_usd_dependency_closure_manifest_not_pass")
    paths = tuple((REPO_ROOT / record["path"]).resolve() for record in normalized["files"])
    if any(
        not path.is_file() or not path.is_relative_to(REPO_ROOT)
        for path in paths
    ):
        raise ValueError("formal_usd_dependency_closure_source_paths_invalid")
    return paths


def _run_dir(path: Path) -> Path:
    candidate = Path(path)
    root = candidate.resolve()
    if candidate.is_symlink() or not root.is_dir() or not root.is_relative_to(REPO_ROOT):
        raise ValueError("formal_usd_dependency_preflight_path_invalid")
    return root


def _artifact_file(root: Path, name: str) -> Path:
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("formal_usd_dependency_preflight_artifact_invalid")
    return path


def _command_value(command: Any, flag: str) -> str:
    if (
        not isinstance(command, list)
        or any(not isinstance(value, str) for value in command)
        or command.count(flag) != 1
    ):
        raise ValueError("formal_usd_dependency_preflight_command_invalid")
    index = command.index(flag)
    if index + 1 >= len(command):
        raise ValueError("formal_usd_dependency_preflight_command_invalid")
    return command[index + 1]


def _profile_from_run_manifest(
    run_manifest: Mapping[str, Any], *, expected_input: Mapping[str, Any]
) -> tuple[Path, dict[str, Any]]:
    raw_path = _command_value(run_manifest.get("command"), "--profile-path")
    candidate = Path(raw_path)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("formal_usd_dependency_preflight_command_invalid")
    path = REPO_ROOT / candidate
    profile = _profile_from_path(path)
    if profile["profile_sha256"] != expected_input["fixed_mount_profile_sha256"]:
        raise ValueError("formal_usd_dependency_preflight_profile_binding_invalid")
    return path.resolve(), profile


def _input_file_records(input_record: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = []
    for entry in closure_contract.validate_input(input_record)["entries"]:
        path = REPO_ROOT / entry["path"]
        if (
            not _is_regular_file_under(path, REPO_ROOT)
            or _sha256_file(path) != entry["sha256"]
        ):
            raise RuntimeError("formal_usd_dependency_input_drift")
        records.append(
            {
                "path": entry["path"],
                "byte_count": path.stat().st_size,
                "sha256": entry["sha256"],
            }
        )
    return records


def _resolved_dependency_path(value: Any) -> str:
    for field in ("realPath", "resolvedPath", "path", "identifier"):
        candidate = getattr(value, field, "")
        if candidate:
            return str(candidate)
    return str(value)


def _mdl_import_modules(path: Path) -> tuple[str, ...]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError("formal_usd_dependency_runtime_mdl_decode_invalid") from exc
    source = _MDL_LINE_COMMENT.sub("", _MDL_BLOCK_COMMENT.sub("", source))
    modules = set()
    for match in _MDL_IMPORT.finditer(source):
        module = match.group(1)
        while module.endswith("::"):
            module = module[:-2]
        if module:
            modules.add(module)
    return tuple(sorted(modules))


def _mdl_module_candidates(module: str, *, owner: Path) -> tuple[Path, ...]:
    relative = module.startswith(".::")
    absolute = module.startswith("::")
    if relative:
        parts = module[3:].split("::")
    elif absolute:
        parts = module[2:].split("::")
    else:
        parts = module.split("::")
    if any(not part.isidentifier() for part in parts):
        return ()
    bases = (
        (owner.parent,)
        if relative
        else (MDL_LIBRARY_ROOT,)
        if absolute
        else (owner.parent, MDL_BASE_ROOT)
    )
    candidates = []
    for base in bases:
        for count in range(len(parts), 0, -1):
            candidates.append(base.joinpath(*parts[:count]).with_suffix(".mdl"))
    return tuple(candidates)


def _discover_runtime_mdl_closure(
    root_paths: Sequence[Path],
) -> tuple[set[Path], set[str], list[str]]:
    roots = {Path(path) for path in root_paths}
    pending = list(sorted(roots, reverse=True))
    closure: set[Path] = set()
    builtin_modules: set[str] = set()
    unresolved: list[str] = []
    while pending:
        path = pending.pop()
        if path in closure:
            continue
        if not _is_regular_file_under(path, MDL_CORE_ROOT):
            unresolved.append(str(path))
            continue
        closure.add(path)
        for module in _mdl_import_modules(path):
            candidates = _mdl_module_candidates(module, owner=path)
            resolved = next(
                (
                    candidate
                    for candidate in candidates
                    if _is_regular_file_under(candidate, MDL_CORE_ROOT)
                ),
                None,
            )
            if resolved is not None:
                pending.append(resolved)
            elif module in MDL_STANDARD_LIBRARY_MODULES:
                builtin_modules.add(module)
            else:
                unresolved.append(f"{path}:{module}")
    return closure, builtin_modules, unresolved


def _discover_dependency_graph(input_record: Mapping[str, Any]) -> dict[str, Any]:
    from pxr import UsdUtils

    normalized = closure_contract.validate_input(input_record)
    paths: set[Path] = set()
    approved_mdl_paths = {
        Path(record["path"])
        for record in normalized["approved_runtime_mdl_dependencies"]
    }
    observed_mdl_paths: set[Path] = set()
    unresolved: list[str] = []
    if any(not _is_regular_file_under(path, MDL_CORE_ROOT) for path in approved_mdl_paths):
        raise RuntimeError("formal_usd_dependency_runtime_mdl_root_invalid")
    for entry in normalized["entries"]:
        entry_path = REPO_ROOT / entry["path"]
        if (
            not _is_regular_file_under(entry_path, REPO_ROOT)
            or _sha256_file(entry_path) != entry["sha256"]
        ):
            raise RuntimeError("formal_usd_dependency_entry_drift")
        paths.add(entry_path)
        layers, assets, missing = UsdUtils.ComputeAllDependencies(str(entry_path))
        unresolved.extend(str(item) for item in missing)
        for value in (*layers, *assets):
            raw = _resolved_dependency_path(value)
            if not raw or raw.startswith("anon:") or "://" in raw:
                unresolved.append(raw or "<empty>")
                continue
            candidate = Path(raw)
            if not candidate.is_absolute():
                unresolved.append(raw)
                continue
            if _is_regular_file_under(candidate, REPO_ROOT):
                paths.add(candidate)
            elif _is_regular_file_under(candidate, MDL_CORE_ROOT):
                if candidate in approved_mdl_paths:
                    observed_mdl_paths.add(candidate)
                else:
                    unresolved.append(raw)
            else:
                unresolved.append(raw)
    if observed_mdl_paths != approved_mdl_paths:
        unresolved.extend(
            str(path) for path in sorted(approved_mdl_paths - observed_mdl_paths)
        )
    runtime_mdl_closure, builtin_modules, mdl_unresolved = _discover_runtime_mdl_closure(
        tuple(sorted(approved_mdl_paths))
    )
    unresolved.extend(mdl_unresolved)
    return {
        "paths": tuple(sorted(paths)),
        "approved_mdl_paths": tuple(sorted(approved_mdl_paths)),
        "runtime_mdl_closure": tuple(sorted(runtime_mdl_closure)),
        "runtime_mdl_builtin_modules": tuple(sorted(builtin_modules)),
        "unresolved": tuple(sorted(set(unresolved))),
    }


def _graph_records(graph: Mapping[str, Any]) -> dict[str, Any]:
    paths = graph["paths"]
    approved_mdl_paths = set(graph["approved_mdl_paths"])
    runtime_mdl_closure = graph["runtime_mdl_closure"]
    files = [
        {
            "path": str(path.relative_to(REPO_ROOT)),
            "byte_count": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in paths
    ]
    runtime_mdls = [
        {
            "purpose": (
                closure_contract.RUNTIME_MDL_ROOT_PURPOSE
                if path in approved_mdl_paths
                else closure_contract.RUNTIME_MDL_DEPENDENCY_PURPOSE
            ),
            "path": str(path),
            "byte_count": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in runtime_mdl_closure
    ]
    return {"files": files, "runtime_mdls": runtime_mdls}


def _graph_identity(graph: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "paths": [str(path.relative_to(REPO_ROOT)) for path in graph["paths"]],
        "approved_mdl_paths": [str(path) for path in graph["approved_mdl_paths"]],
        "runtime_mdl_closure": [str(path) for path in graph["runtime_mdl_closure"]],
        "runtime_mdl_builtin_modules": list(graph["runtime_mdl_builtin_modules"]),
        "unresolved": list(graph["unresolved"]),
    }


def _discover_manifest(input_record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = closure_contract.validate_input(input_record)
    first_graph = _discover_dependency_graph(normalized)
    first_records = _graph_records(first_graph)
    second_graph = _discover_dependency_graph(normalized)
    second_records = _graph_records(second_graph)
    if (
        _graph_identity(first_graph) != _graph_identity(second_graph)
        or first_records != second_records
    ):
        raise RuntimeError("formal_usd_dependency_graph_changed_during_discovery")
    root_records = [
        record
        for record in first_records["runtime_mdls"]
        if record["purpose"] == closure_contract.RUNTIME_MDL_ROOT_PURPOSE
    ]
    return closure_contract.build_manifest(
        input_record=normalized,
        files=first_records["files"],
        approved_runtime_mdl_dependencies=root_records,
        runtime_mdl_closure=first_records["runtime_mdls"],
        runtime_mdl_builtin_modules=first_graph["runtime_mdl_builtin_modules"],
        unresolved=first_graph["unresolved"],
    )


def _blocked_report(
    runtime: Mapping[str, Any] | None,
    exc: BaseException,
    input_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "authority": AUTHORITY,
        "classification": CLASSIFICATION,
        "decision": "RUNTIME_BLOCKED",
        "input": dict(input_record) if isinstance(input_record, Mapping) else None,
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
    input_record = None
    report = None
    written = False
    try:
        input_record = closure_contract.validate_input(legacy._read_canonical_line(args.input))
        if _sha256_file(args.input) != args.expected_input_sha256:
            raise RuntimeError("formal_usd_dependency_input_sha256_mismatch")
        profile_path = REPO_ROOT / args.profile_path
        profile = _profile_from_path(profile_path)
        if profile["profile_sha256"] != input_record["fixed_mount_profile_sha256"]:
            raise RuntimeError("formal_usd_dependency_profile_binding_invalid")
        paths = source_paths(input_record, profile_path=profile_path)
        attestation = legacy._attestation_module()
        execution_request = attestation.verify_execution_request(
            attestation._read_canonical_json(args.execution_request), source_paths=paths
        )
        receipt, app = attestation.bootstrap_effective_runtime(
            execution_request=execution_request, source_paths=paths
        )
        attestation.write_canonical_json(args.runtime_receipt_path, receipt)
        binding = attestation.execution_binding_for_request(
            execution_request, child_pid=os.getpid()
        )
        attestation.require_matched_runtime_receipt(
            receipt, expected_execution_binding=binding
        )
        before = _input_file_records(input_record)
        manifest = _discover_manifest(input_record)
        after = _input_file_records(input_record)
        if before != after:
            raise RuntimeError("formal_usd_dependency_input_changed_during_discovery")
        closure_path = args.out_dir / CLOSURE_NAME
        legacy._write_create_only(closure_path, manifest)
        report = {
            "schema_version": 1,
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "decision": manifest["status"],
            "input": input_record,
            "runtime": {
                "receipt_sha256": attestation.canonical_json_sha256(receipt),
                "execution_binding": binding,
            },
            "closure": {"path": CLOSURE_NAME, "sha256": _sha256_file(closure_path)},
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        legacy._write_create_only(args.child_report_path, report)
        written = True
    except BaseException as exc:
        report = _blocked_report(runtime, exc, input_record)
        if not args.child_report_path.exists():
            legacy._write_create_only(args.child_report_path, report)
            written = True
    finally:
        if app is not None:
            app.close()
    if report is None:
        raise RuntimeError("formal_usd_dependency_child_report_unavailable")
    if not written and not args.child_report_path.exists():
        legacy._write_create_only(args.child_report_path, report)
    return 2 if report["decision"] == "RUNTIME_BLOCKED" else 0


def _verify_child(
    *,
    child: Mapping[str, Any],
    input_record: Mapping[str, Any],
    receipt: Mapping[str, Any],
    binding: Mapping[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    if (
        child.get("authority") != AUTHORITY
        or child.get("classification") != CLASSIFICATION
        or child.get("input") != dict(input_record)
        or not isinstance(child.get("runtime"), Mapping)
        or child["runtime"].get("receipt_sha256")
        != legacy._attestation_module().canonical_json_sha256(receipt)
        or child["runtime"].get("execution_binding") != dict(binding)
    ):
        raise RuntimeError("formal_usd_dependency_child_contract_invalid")
    if child.get("decision") not in {closure_contract.PASS, closure_contract.NO_GO}:
        raise RuntimeError("formal_usd_dependency_child_decision_invalid")
    closure = child.get("closure")
    if (
        not isinstance(closure, Mapping)
        or set(closure) != {"path", "sha256"}
        or closure.get("path") != CLOSURE_NAME
    ):
        raise RuntimeError("formal_usd_dependency_closure_artifact_invalid")
    path = out_dir / CLOSURE_NAME
    if not _is_regular_file_under(path, REPO_ROOT) or _sha256_file(path) != closure.get("sha256"):
        raise RuntimeError("formal_usd_dependency_closure_artifact_invalid")
    manifest = closure_contract.validate_manifest(legacy._read_canonical_line(path))
    if manifest["input"] != closure_contract.validate_input(input_record):
        raise RuntimeError("formal_usd_dependency_closure_input_binding_invalid")
    closure_contract.verify_manifest_files(manifest, repo_root=REPO_ROOT)
    if manifest["status"] != child["decision"]:
        raise RuntimeError("formal_usd_dependency_child_decision_invalid")
    return manifest


def run_preflight(
    *,
    frozen: Mapping[str, Any],
    fixed_mount_profile: Mapping[str, Any],
    out_dir: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    artifact_root = (REPO_ROOT / "artifacts/runs").resolve()
    if (
        out_dir.exists()
        or not out_dir.resolve().is_relative_to(artifact_root)
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0.0
    ):
        raise ValueError("formal_usd_dependency_preflight_arguments_invalid")
    out_dir.mkdir(parents=True, mode=0o700)
    input_record = build_input(frozen, fixed_mount_profile=fixed_mount_profile)
    profile = snapshot_replay.validate_fixed_mount_profile(fixed_mount_profile)
    profile_path = (REPO_ROOT / profile["profile_path"]).resolve()
    paths = source_paths(input_record, profile_path=profile_path)
    attestation = legacy._attestation_module()
    source_before = attestation.capture_source_identity(paths)
    input_path = out_dir / INPUT_NAME
    legacy._write_create_only(input_path, input_record)
    input_sha256 = _sha256_file(input_path)
    execution_request = attestation.create_execution_request(
        run_id=secrets.token_hex(16),
        parent_nonce_sha256=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        parent_pid=os.getpid(),
        source=source_before,
    )
    execution_request_path = out_dir / "execution_request.json"
    attestation.write_canonical_json(execution_request_path, execution_request)
    environment = attestation.sealed_child_environment(out_dir / "runtime")
    environment["NVIDIA_VISIBLE_DEVICES"] = "4"
    environment.pop("CUDA_VISIBLE_DEVICES", None)
    command = [
        str(legacy.FORMAL_ISAAC41_PYTHON),
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        "--child",
        "--out-dir",
        str(out_dir),
        "--input",
        str(input_path),
        "--expected-input-sha256",
        input_sha256,
        "--profile-path",
        profile["profile_path"],
        "--execution-request",
        str(execution_request_path),
    ]
    stdout_path = out_dir / "child.stdout.log"
    stderr_path = out_dir / "child.stderr.log"
    child_pid = None
    child_returncode = None
    receipt = None
    source_after = None
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
                child_returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                child_returncode = process.wait()
                raise RuntimeError("formal_usd_dependency_child_timeout") from exc
        child = legacy._read_canonical_line(out_dir / "child_report.json")
        receipt = attestation._read_canonical_json(out_dir / "runtime_receipt.json")
        binding = attestation.execution_binding_for_request(execution_request, child_pid=child_pid)
        attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
        manifest = _verify_child(
            child=child,
            input_record=input_record,
            receipt=receipt,
            binding=binding,
            out_dir=out_dir,
        )
        if child_returncode != 0:
            raise RuntimeError("formal_usd_dependency_child_exit_status_invalid")
        source_after = attestation.capture_source_identity(paths)
        if source_after != source_before:
            raise RuntimeError("formal_usd_dependency_source_changed_during_run")
        report = {
            "schema_version": 1,
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "decision": manifest["status"],
            "input": input_record,
            "closure": {"path": CLOSURE_NAME, "sha256": _sha256_file(out_dir / CLOSURE_NAME)},
            "parent_verification": {
                "verified": True,
                "child_pid": child_pid,
                "child_returncode": child_returncode,
                "child_report_sha256": _sha256_file(out_dir / "child_report.json"),
                "runtime_receipt_sha256": attestation.canonical_json_sha256(receipt),
            },
        }
    except BaseException as exc:
        verification_failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        manifest = None
        report = _blocked_report(None, exc, input_record)
        report["parent_verification"] = {
            "verified": False,
            "child_pid": child_pid,
            "child_returncode": child_returncode,
        }
    finally:
        if source_after is None:
            source_after = attestation.capture_source_identity(paths)
        run_manifest = {
            "schema_version": 1,
            "authority": AUTHORITY,
            "classification": CLASSIFICATION,
            "command": command,
            "input": input_record,
            "source_before": source_before,
            "source_after": source_after,
            "child_pid": child_pid,
            "child_returncode": child_returncode,
            "runtime_receipt_sha256": (
                attestation.canonical_json_sha256(receipt) if isinstance(receipt, Mapping) else None
            ),
            "closure_sha256": _sha256_file(out_dir / CLOSURE_NAME)
            if (out_dir / CLOSURE_NAME).is_file()
            else None,
            "stdout_sha256": _sha256_file(stdout_path) if stdout_path.is_file() else None,
            "stderr_sha256": _sha256_file(stderr_path) if stderr_path.is_file() else None,
            "verification_failure": verification_failure,
        }
    legacy._write_bound_report_and_manifest(
        report_path=out_dir / "report.json",
        report=report,
        manifest_path=out_dir / "run_manifest.json",
        manifest=run_manifest,
        manifest_writer=attestation.write_canonical_json,
    )
    if report["decision"] != closure_contract.PASS or manifest is None:
        raise RuntimeError("formal_usd_dependency_preflight_failed")
    return {
        "manifest": manifest,
        "manifest_path": out_dir / CLOSURE_NAME,
        "manifest_file_sha256": _sha256_file(out_dir / CLOSURE_NAME),
        "report_path": out_dir / "report.json",
        "run_manifest_path": out_dir / "run_manifest.json",
        "runtime_receipt_path": out_dir / "runtime_receipt.json",
    }


def verify_preflight_run(
    run_dir: Path, *, expected_input: Mapping[str, Any]
) -> dict[str, Any]:
    root = _run_dir(run_dir)
    normalized_input = closure_contract.validate_input(expected_input)
    attestation = legacy._attestation_module()
    report_path = _artifact_file(root, "report.json")
    child_path = _artifact_file(root, "child_report.json")
    run_manifest_path = _artifact_file(root, "run_manifest.json")
    receipt_path = _artifact_file(root, "runtime_receipt.json")
    execution_request_path = _artifact_file(root, "execution_request.json")
    stdout_path = _artifact_file(root, "child.stdout.log")
    stderr_path = _artifact_file(root, "child.stderr.log")
    closure_path = _artifact_file(root, CLOSURE_NAME)
    report = legacy._read_canonical_line(report_path)
    child = legacy._read_canonical_line(child_path)
    run_manifest = attestation._read_canonical_json(run_manifest_path)
    receipt = attestation._read_canonical_json(receipt_path)
    execution_request = attestation.validate_execution_request(
        attestation._read_canonical_json(execution_request_path)
    )
    profile_path, _ = _profile_from_run_manifest(
        run_manifest, expected_input=normalized_input
    )
    expected_source = attestation.capture_source_identity(
        source_paths(normalized_input, profile_path=profile_path)
    )
    child_pid = run_manifest.get("child_pid")
    if type(child_pid) is not int or child_pid <= 0:
        raise ValueError("formal_usd_dependency_preflight_invalid")
    binding = attestation.execution_binding_for_request(
        execution_request, child_pid=child_pid
    )
    receipt_sha256 = attestation.canonical_json_sha256(receipt)
    child_sha256 = _sha256_file(child_path)
    report_sha256 = _sha256_file(report_path)
    run_manifest_sha256 = _sha256_file(run_manifest_path)
    closure_file_sha256 = _sha256_file(closure_path)
    if (
        report.get("authority") != AUTHORITY
        or report.get("classification") != CLASSIFICATION
        or report.get("decision") != closure_contract.PASS
        or report.get("input") != normalized_input
        or report.get("parent_verification", {}).get("verified") is not True
        or report["parent_verification"].get("child_pid") != child_pid
        or report["parent_verification"].get("child_returncode") != 0
        or report["parent_verification"].get("child_report_sha256") != child_sha256
        or report["parent_verification"].get("runtime_receipt_sha256") != receipt_sha256
        or report.get("closure", {}).get("path") != CLOSURE_NAME
        or report["closure"].get("sha256") != closure_file_sha256
        or run_manifest.get("authority") != AUTHORITY
        or run_manifest.get("classification") != CLASSIFICATION
        or run_manifest.get("input") != normalized_input
        or run_manifest.get("report_sha256") != report_sha256
        or run_manifest.get("child_returncode") != 0
        or run_manifest.get("runtime_receipt_sha256") != receipt_sha256
        or run_manifest.get("closure_sha256") != closure_file_sha256
        or run_manifest.get("stdout_sha256") != _sha256_file(stdout_path)
        or run_manifest.get("stderr_sha256") != _sha256_file(stderr_path)
        or run_manifest.get("source_before") != run_manifest.get("source_after")
        or run_manifest.get("source_before") != execution_request["source"]
        or execution_request["source"] != expected_source
        or binding["source_sha256"]
        != attestation.canonical_json_sha256(run_manifest["source_before"])
    ):
        raise ValueError("formal_usd_dependency_preflight_invalid")
    attestation.require_matched_runtime_receipt(receipt, expected_execution_binding=binding)
    manifest = closure_contract.rebind_manifest(
        legacy._read_canonical_line(closure_path), expected_input=normalized_input
    )
    closure_contract.verify_manifest_files(manifest, repo_root=REPO_ROOT)
    if (
        child.get("authority") != AUTHORITY
        or child.get("classification") != CLASSIFICATION
        or child.get("decision") != closure_contract.PASS
        or child.get("input") != manifest["input"]
        or child.get("closure", {}).get("path") != CLOSURE_NAME
        or child["closure"].get("sha256") != closure_file_sha256
        or not isinstance(child.get("runtime"), Mapping)
        or child["runtime"].get("receipt_sha256") != receipt_sha256
        or child["runtime"].get("execution_binding") != binding
        or report.get("input") != manifest["input"]
    ):
        raise ValueError("formal_usd_dependency_preflight_invalid")
    return {
        "manifest": manifest,
        "manifest_path": closure_path,
        "manifest_file_sha256": closure_file_sha256,
        "report_sha256": report_sha256,
        "run_manifest_sha256": run_manifest_sha256,
        "runtime_receipt_sha256": receipt_sha256,
    }


def bind_preflight_run(
    run_dir: Path, *, expected_input: Mapping[str, Any]
) -> dict[str, Any]:
    root = _run_dir(run_dir)
    normalized_input = closure_contract.validate_input(expected_input)
    verification = verify_preflight_run(root, expected_input=normalized_input)
    binding = closure_contract.build_preflight_binding(
        preflight_run_dir=str(root.relative_to(REPO_ROOT)),
        input_sha256=closure_contract.canonical_json_sha256(normalized_input),
        closure_manifest_sha256=verification["manifest"]["sha256"],
        closure_file_sha256=verification["manifest_file_sha256"],
        preflight_report_sha256=verification["report_sha256"],
        preflight_run_manifest_sha256=verification["run_manifest_sha256"],
        preflight_runtime_receipt_sha256=verification["runtime_receipt_sha256"],
    )
    return {"binding": binding, "manifest": verification["manifest"]}


def verify_preflight_binding(
    binding: Mapping[str, Any], *, expected_input: Mapping[str, Any]
) -> dict[str, Any]:
    normalized_binding = closure_contract.validate_preflight_binding(binding)
    normalized_input = closure_contract.validate_input(expected_input)
    if normalized_binding["input_sha256"] != closure_contract.canonical_json_sha256(
        normalized_input
    ):
        raise ValueError("formal_usd_dependency_preflight_binding_invalid")
    verified = bind_preflight_run(
        REPO_ROOT / normalized_binding["preflight_run_dir"], expected_input=normalized_input
    )
    if verified["binding"] != normalized_binding:
        raise ValueError("formal_usd_dependency_preflight_binding_invalid")
    return verified


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=legacy.DEFAULT_CONFIG)
    parser.add_argument("--fixed-mount-profile", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--input", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expected-input-sha256", help=argparse.SUPPRESS)
    parser.add_argument("--profile-path", help=argparse.SUPPRESS)
    parser.add_argument("--execution-request", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    out_dir = args.out_dir
    if out_dir.is_symlink():
        parser.error("out-dir must not be a symlink")
    args.out_dir = out_dir.resolve()
    artifact_root = (REPO_ROOT / "artifacts/runs").resolve()
    if not args.out_dir.is_relative_to(artifact_root):
        parser.error("out-dir must be under artifacts/runs")
    if args.child:
        if (
            args.config != legacy.DEFAULT_CONFIG
            or args.fixed_mount_profile is not None
            or args.input is None
            or args.expected_input_sha256 is None
            or args.profile_path is None
            or args.execution_request is None
        ):
            parser.error("--child requires sealed inputs")
        args.input = args.input.resolve()
        args.execution_request = args.execution_request.resolve()
        if (
            not args.out_dir.is_dir()
            or not args.input.is_file()
            or not args.execution_request.is_file()
        ):
            parser.error("sealed child inputs must exist")
    else:
        config = args.config
        profile = args.fixed_mount_profile
        args.config = config.resolve()
        if profile is not None:
            if profile.is_symlink():
                parser.error("fixed mount profile must not be a symlink")
            args.fixed_mount_profile = profile.resolve()
        if (
            args.out_dir.exists()
            or not args.config.is_file()
            or args.fixed_mount_profile is None
            or not args.fixed_mount_profile.is_file()
            or not math.isfinite(args.timeout_seconds)
            or args.timeout_seconds <= 0.0
        ):
            parser.error("parent inputs invalid")
    args.child_report_path = args.out_dir / "child_report.json"
    args.runtime_receipt_path = args.out_dir / "runtime_receipt.json"
    return args


def _write_setup_blocked_evidence(out_dir: Path, exc: BaseException) -> None:
    out_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    report_path = out_dir / "report.json"
    if report_path.exists():
        return
    report = _blocked_report(None, exc, None)
    try:
        attestation = legacy._attestation_module()
        legacy._write_bound_report_and_manifest(
            report_path=report_path,
            report=report,
            manifest_path=out_dir / "run_manifest.json",
            manifest={
                "schema_version": 1,
                "authority": AUTHORITY,
                "classification": CLASSIFICATION,
                "command": None,
                "input": None,
                "source_before": None,
                "source_after": None,
                "child_pid": None,
                "child_returncode": None,
                "runtime_receipt_sha256": None,
                "closure_sha256": None,
                "stdout_sha256": None,
                "stderr_sha256": None,
                "verification_failure": report["fatal_error"],
            },
            manifest_writer=attestation.write_canonical_json,
        )
    except BaseException:
        if not report_path.exists():
            legacy._write_create_only(report_path, report)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.child:
        status = _run_child(args)
        if status != 0:
            os._exit(status)
        return 0
    try:
        native = legacy._native_module()
        frozen = legacy.build_sealed_child_input(native.freeze_diagnostic_config(args.config))
        profile = _profile_from_path(args.fixed_mount_profile)
        run_preflight(
            frozen=frozen,
            fixed_mount_profile=profile,
            out_dir=args.out_dir,
            timeout_seconds=args.timeout_seconds,
        )
    except BaseException as exc:
        _write_setup_blocked_evidence(args.out_dir, exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
