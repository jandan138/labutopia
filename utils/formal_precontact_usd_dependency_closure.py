"""Pure contracts for a sealed USD dependency-closure preflight."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


AUTHORITY = "formal_precontact_usd_dependency_closure_v1"
PASS = "FORMAL_USD_DEPENDENCY_CLOSURE_PASS"
NO_GO = "FORMAL_USD_DEPENDENCY_CLOSURE_NO_GO"
PREFLIGHT_BINDING_AUTHORITY = "formal_usd_dependency_preflight_binding_v1"
RUNTIME_MDL_ROOT_PURPOSE = "kit_mdl_material_root"
RUNTIME_MDL_DEPENDENCY_PURPOSE = "kit_mdl_material_dependency"
ENTRY_ROLES = (
    "fixed_mount_filter_overlay",
    "hidden_cube_overlay",
    "local_franka",
    "local_scene",
)


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"formal_usd_dependency_closure_{field}_invalid")
    return value


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


def _relative_path(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError(f"formal_usd_dependency_closure_{field}_invalid")
    return value


def _entry(value: Any) -> dict[str, str]:
    expected = {"role", "path", "sha256"}
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value["role"] not in ENTRY_ROLES
    ):
        raise ValueError("formal_usd_dependency_closure_entry_invalid")
    return {
        "role": value["role"],
        "path": _relative_path(value["path"], field="entry_path"),
        "sha256": _sha256(value["sha256"], field="entry_sha256"),
    }


def _approved_runtime_mdl_dependency(value: Any) -> dict[str, str]:
    expected = {"purpose", "path", "sha256"}
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value["purpose"] != RUNTIME_MDL_ROOT_PURPOSE
        or not isinstance(value["path"], str)
        or not value["path"].startswith("/")
        or value["path"].endswith("/")
    ):
        raise ValueError("formal_usd_dependency_closure_runtime_mdl_invalid")
    return {
        "purpose": RUNTIME_MDL_ROOT_PURPOSE,
        "path": value["path"],
        "sha256": _sha256(value["sha256"], field="runtime_mdl_sha256"),
    }


def _input(value: Any) -> dict[str, Any]:
    expected = {
        "v7_config_sha256",
        "fixed_mount_profile_sha256",
        "approved_runtime_mdl_dependencies",
        "entries",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("formal_usd_dependency_closure_input_invalid")
    entries = [_entry(item) for item in value["entries"]] if isinstance(value["entries"], list) else []
    if (
        len(entries) != len(ENTRY_ROLES)
        or [entry["role"] for entry in entries] != list(ENTRY_ROLES)
        or len({entry["path"] for entry in entries}) != len(entries)
    ):
        raise ValueError("formal_usd_dependency_closure_input_invalid")
    raw_mdls = value["approved_runtime_mdl_dependencies"]
    if not isinstance(raw_mdls, list):
        raise ValueError("formal_usd_dependency_closure_input_invalid")
    approved_mdls = [_approved_runtime_mdl_dependency(item) for item in raw_mdls]
    if [record["path"] for record in approved_mdls] != sorted(
        record["path"] for record in approved_mdls
    ) or len({record["path"] for record in approved_mdls}) != len(approved_mdls):
        raise ValueError("formal_usd_dependency_closure_input_invalid")
    return {
        "v7_config_sha256": _sha256(value["v7_config_sha256"], field="config_sha256"),
        "fixed_mount_profile_sha256": _sha256(
            value["fixed_mount_profile_sha256"], field="profile_sha256"
        ),
        "approved_runtime_mdl_dependencies": approved_mdls,
        "entries": entries,
    }


def build_input(
    *,
    v7_config_sha256: str,
    fixed_mount_profile_sha256: str,
    approved_runtime_mdl_dependencies: Sequence[Mapping[str, Any]],
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _input(
        {
            "v7_config_sha256": v7_config_sha256,
            "fixed_mount_profile_sha256": fixed_mount_profile_sha256,
            "approved_runtime_mdl_dependencies": list(approved_runtime_mdl_dependencies),
            "entries": list(entries),
        }
    )


def validate_input(value: Any) -> dict[str, Any]:
    return _input(value)


def _preflight_binding(value: Any) -> dict[str, str | int]:
    expected = {
        "authority",
        "schema_version",
        "preflight_run_dir",
        "input_sha256",
        "closure_manifest_sha256",
        "closure_file_sha256",
        "preflight_report_sha256",
        "preflight_run_manifest_sha256",
        "preflight_runtime_receipt_sha256",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value["authority"] != PREFLIGHT_BINDING_AUTHORITY
        or value["schema_version"] != 1
    ):
        raise ValueError("formal_usd_dependency_preflight_binding_invalid")
    try:
        run_dir = _relative_path(value["preflight_run_dir"], field="preflight_run_dir")
    except ValueError as exc:
        raise ValueError("formal_usd_dependency_preflight_binding_invalid") from exc
    if not run_dir.startswith("artifacts/runs/"):
        raise ValueError("formal_usd_dependency_preflight_binding_invalid")
    return {
        "authority": PREFLIGHT_BINDING_AUTHORITY,
        "schema_version": 1,
        "preflight_run_dir": run_dir,
        "input_sha256": _sha256(value["input_sha256"], field="preflight_input_sha256"),
        "closure_manifest_sha256": _sha256(
            value["closure_manifest_sha256"], field="preflight_closure_manifest_sha256"
        ),
        "closure_file_sha256": _sha256(
            value["closure_file_sha256"], field="preflight_closure_file_sha256"
        ),
        "preflight_report_sha256": _sha256(
            value["preflight_report_sha256"], field="preflight_report_sha256"
        ),
        "preflight_run_manifest_sha256": _sha256(
            value["preflight_run_manifest_sha256"], field="preflight_run_manifest_sha256"
        ),
        "preflight_runtime_receipt_sha256": _sha256(
            value["preflight_runtime_receipt_sha256"],
            field="preflight_runtime_receipt_sha256",
        ),
    }


def build_preflight_binding(
    *,
    preflight_run_dir: str,
    input_sha256: str,
    closure_manifest_sha256: str,
    closure_file_sha256: str,
    preflight_report_sha256: str,
    preflight_run_manifest_sha256: str,
    preflight_runtime_receipt_sha256: str,
) -> dict[str, str | int]:
    return _preflight_binding(
        {
            "authority": PREFLIGHT_BINDING_AUTHORITY,
            "schema_version": 1,
            "preflight_run_dir": preflight_run_dir,
            "input_sha256": input_sha256,
            "closure_manifest_sha256": closure_manifest_sha256,
            "closure_file_sha256": closure_file_sha256,
            "preflight_report_sha256": preflight_report_sha256,
            "preflight_run_manifest_sha256": preflight_run_manifest_sha256,
            "preflight_runtime_receipt_sha256": preflight_runtime_receipt_sha256,
        }
    )


def validate_preflight_binding(value: Any) -> dict[str, str | int]:
    return _preflight_binding(value)


def _file_record(value: Any) -> dict[str, Any]:
    expected = {"path", "byte_count", "sha256"}
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or isinstance(value["byte_count"], bool)
        or not isinstance(value["byte_count"], int)
        or value["byte_count"] < 0
    ):
        raise ValueError("formal_usd_dependency_closure_file_invalid")
    return {
        "path": _relative_path(value["path"], field="file_path"),
        "byte_count": value["byte_count"],
        "sha256": _sha256(value["sha256"], field="file_sha256"),
    }


def _runtime_mdl_record(value: Any) -> dict[str, Any]:
    expected = {"purpose", "path", "byte_count", "sha256"}
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or isinstance(value["byte_count"], bool)
        or not isinstance(value["byte_count"], int)
        or value["byte_count"] < 0
    ):
        raise ValueError("formal_usd_dependency_closure_runtime_mdl_invalid")
    base = _approved_runtime_mdl_dependency(
        {key: value[key] for key in ("purpose", "path", "sha256")}
    ) if value.get("purpose") == RUNTIME_MDL_ROOT_PURPOSE else None
    if value.get("purpose") == RUNTIME_MDL_DEPENDENCY_PURPOSE:
        dependency = dict(value)
        if (
            not isinstance(dependency["path"], str)
            or not dependency["path"].startswith("/")
            or dependency["path"].endswith("/")
        ):
            raise ValueError("formal_usd_dependency_closure_runtime_mdl_invalid")
        return {
            "purpose": RUNTIME_MDL_DEPENDENCY_PURPOSE,
            "path": dependency["path"],
            "byte_count": dependency["byte_count"],
            "sha256": _sha256(dependency["sha256"], field="runtime_mdl_sha256"),
        }
    if base is None:
        raise ValueError("formal_usd_dependency_closure_runtime_mdl_invalid")
    return {**base, "byte_count": value["byte_count"]}


def _runtime_mdl_builtin_module(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("::")
        or value.endswith("::")
        or any(not part.isidentifier() for part in value[2:].split("::"))
    ):
        raise ValueError("formal_usd_dependency_closure_runtime_mdl_builtin_invalid")
    return value


def _manifest(value: Any) -> dict[str, Any]:
    expected = {
        "authority",
        "schema_version",
        "status",
        "input",
        "files",
        "approved_runtime_mdl_dependencies",
        "runtime_mdl_closure",
        "runtime_mdl_builtin_modules",
        "unresolved",
        "sha256",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError("formal_usd_dependency_closure_manifest_invalid")
    manifest = dict(value)
    if (
        manifest["authority"] != AUTHORITY
        or manifest["schema_version"] != 2
        or manifest["status"] not in {PASS, NO_GO}
        or manifest["sha256"]
        != canonical_json_sha256({key: item for key, item in manifest.items() if key != "sha256"})
        or not isinstance(manifest["files"], list)
        or not isinstance(manifest["approved_runtime_mdl_dependencies"], list)
        or not isinstance(manifest["runtime_mdl_closure"], list)
        or not isinstance(manifest["runtime_mdl_builtin_modules"], list)
        or not isinstance(manifest["unresolved"], list)
        or any(not isinstance(item, str) or not item for item in manifest["unresolved"])
    ):
        raise ValueError("formal_usd_dependency_closure_manifest_invalid")
    files = [_file_record(item) for item in manifest["files"]]
    if [record["path"] for record in files] != sorted(record["path"] for record in files):
        raise ValueError("formal_usd_dependency_closure_manifest_invalid")
    if len({record["path"] for record in files}) != len(files):
        raise ValueError("formal_usd_dependency_closure_manifest_invalid")
    input_record = _input(manifest["input"])
    approved_mdls = [
        _runtime_mdl_record(item) for item in manifest["approved_runtime_mdl_dependencies"]
    ]
    expected_roots = [
        {
            "purpose": item["purpose"],
            "path": item["path"],
            "byte_count": record["byte_count"],
            "sha256": item["sha256"],
        }
        for item, record in zip(
            input_record["approved_runtime_mdl_dependencies"], approved_mdls, strict=True
        )
    ]
    runtime_mdl_closure = [
        _runtime_mdl_record(item) for item in manifest["runtime_mdl_closure"]
    ]
    builtin_modules = [
        _runtime_mdl_builtin_module(item)
        for item in manifest["runtime_mdl_builtin_modules"]
    ]
    if (
        [record["path"] for record in approved_mdls]
        != sorted(record["path"] for record in approved_mdls)
        or approved_mdls != expected_roots
        or [record["path"] for record in runtime_mdl_closure]
        != sorted(record["path"] for record in runtime_mdl_closure)
        or len({record["path"] for record in runtime_mdl_closure})
        != len(runtime_mdl_closure)
        or builtin_modules != sorted(set(builtin_modules))
        or [
            record
            for record in runtime_mdl_closure
            if record["purpose"] == RUNTIME_MDL_ROOT_PURPOSE
        ]
        != approved_mdls
        or any(
            record["purpose"] != RUNTIME_MDL_DEPENDENCY_PURPOSE
            and record["purpose"] != RUNTIME_MDL_ROOT_PURPOSE
            for record in runtime_mdl_closure
        )
    ):
        raise ValueError("formal_usd_dependency_closure_manifest_invalid")
    file_by_path = {record["path"]: record for record in files}
    entries_bound = all(
        entry["path"] in file_by_path
        and file_by_path[entry["path"]]["sha256"] == entry["sha256"]
        for entry in input_record["entries"]
    )
    if not entries_bound or (manifest["status"] == PASS and manifest["unresolved"]):
        raise ValueError("formal_usd_dependency_closure_manifest_invalid")
    return {
        "authority": AUTHORITY,
        "schema_version": 2,
        "status": manifest["status"],
        "input": input_record,
        "files": files,
        "approved_runtime_mdl_dependencies": approved_mdls,
        "runtime_mdl_closure": runtime_mdl_closure,
        "runtime_mdl_builtin_modules": builtin_modules,
        "unresolved": sorted(set(manifest["unresolved"])),
        "sha256": _sha256(manifest["sha256"], field="manifest_sha256"),
    }


def build_manifest(
    *,
    input_record: Mapping[str, Any],
    files: Sequence[Mapping[str, Any]],
    unresolved: Sequence[str],
    approved_runtime_mdl_dependencies: Sequence[Mapping[str, Any]] = (),
    runtime_mdl_closure: Sequence[Mapping[str, Any]] = (),
    runtime_mdl_builtin_modules: Sequence[str] = (),
) -> dict[str, Any]:
    normalized_input = _input(input_record)
    normalized_files = sorted((_file_record(item) for item in files), key=lambda item: item["path"])
    normalized_mdls = sorted(
        (_runtime_mdl_record(item) for item in approved_runtime_mdl_dependencies),
        key=lambda item: item["path"],
    )
    normalized_runtime_mdl_closure = sorted(
        (_runtime_mdl_record(item) for item in runtime_mdl_closure),
        key=lambda item: item["path"],
    )
    normalized_builtin_modules = sorted(
        {_runtime_mdl_builtin_module(item) for item in runtime_mdl_builtin_modules}
    )
    normalized_unresolved = sorted(set(unresolved))
    payload = {
        "authority": AUTHORITY,
        "schema_version": 2,
        "status": PASS if not normalized_unresolved else NO_GO,
        "input": normalized_input,
        "files": normalized_files,
        "approved_runtime_mdl_dependencies": normalized_mdls,
        "runtime_mdl_closure": normalized_runtime_mdl_closure,
        "runtime_mdl_builtin_modules": normalized_builtin_modules,
        "unresolved": normalized_unresolved,
    }
    return _manifest({**payload, "sha256": canonical_json_sha256(payload)})


def validate_manifest(value: Any) -> dict[str, Any]:
    return _manifest(value)


def rebind_manifest(value: Any, *, expected_input: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _manifest(value)
    if manifest["status"] != PASS:
        raise ValueError("formal_usd_dependency_closure_manifest_not_pass")
    if manifest["input"] != _input(expected_input):
        raise ValueError("formal_usd_dependency_closure_input_binding_invalid")
    return manifest


def verify_manifest_files(value: Any, *, repo_root: Path) -> dict[str, Any]:
    manifest = _manifest(value)
    root = repo_root.resolve()
    for record in manifest["files"]:
        candidate = root / record["path"]
        path = candidate.resolve()
        if (
            not _is_regular_file_without_symlink_components(candidate)
            or not path.is_relative_to(root)
            or not path.is_file()
            or path.stat().st_size != record["byte_count"]
        ):
            raise ValueError("formal_usd_dependency_closure_file_binding_invalid")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record["sha256"]:
            raise ValueError("formal_usd_dependency_closure_file_binding_invalid")
    for record in manifest["runtime_mdl_closure"]:
        candidate = Path(record["path"])
        path = candidate.resolve()
        if (
            not _is_regular_file_without_symlink_components(candidate)
            or not path.is_file()
            or path.stat().st_size != record["byte_count"]
        ):
            raise ValueError("formal_usd_dependency_closure_runtime_mdl_binding_invalid")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record["sha256"]:
            raise ValueError("formal_usd_dependency_closure_runtime_mdl_binding_invalid")
    return manifest
